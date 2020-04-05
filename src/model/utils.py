import os
import pickle
import re

import nibabel
import numpy as np
import torch
import tqdm
from matplotlib import pyplot as plt
from skimage.segmentation import mark_boundaries
from skimage.util import img_as_float
from sklearn.metrics import pairwise_distances

import const
import utils
from utils import get_single_image_slice_gen


def evaluate_net(
        net, data_gen, metrics, total_samples_cnt,
        device, tqdm_description=None
):
    """
    Evaluate the net

    :param net: model
    :param data_gen: data generator
    :param metrics: dict(metric name: metric function)
    :param total_samples_cnt: max_valid_samples or len(indices_valid)
    :param device: device to perform evaluation
    :param tqdm_description: string to print in tqdm progress bar

    :return: dict: key - metric name, value - {'list': [tuple(slice_ix, value)], 'mean': float}
    """
    net.eval()
    metrics_res = {m_name: {'list': [], 'mean': 0} for m_name, m_func in metrics.items()}

    with torch.no_grad():
        with tqdm.tqdm(total=total_samples_cnt, desc=tqdm_description,
                       unit='scan', leave=True) as pbar:
            for ix, (slice, labels, slice_ix) in enumerate(data_gen, start=1):
                x = torch.tensor(slice, dtype=torch.float, device=device).unsqueeze(0).unsqueeze(0)
                y = torch.tensor(labels, dtype=torch.float, device=device).unsqueeze(0).unsqueeze(0)
                out = net(x)

                for m_name, m_func in metrics.items():
                    m_value = m_func(out, y).item()
                    metrics_res[m_name]['mean'] += m_value
                    metrics_res[m_name]['list'].append((slice_ix, m_value))

                pbar.update()

    for m_name, m_dict in metrics_res.items():
        m_dict['mean'] /= total_samples_cnt

    return metrics_res


#
# def evaluate_segmentation(
#         net, loss_func, state_dict_fp, indices_valid, scans_dp,
#         labels_dp, max_top_losses_cnt=8, device='cuda', dir='results'
# ):
#     """
#     Find slices that have highest loss values for specified loss function.
#     Store indices of such slices to visualize results for the for networks with other weights.
#     Pass the same loss function that the model was trained with.
#     """
#     net.to(device=device)
#     state_dict = torch.load(state_dict_fp)
#     net.load_state_dict(state_dict)
#
#     loss_name = type(loss_func).__name__
#
#     gen = utils.get_scans_and_labels_batches(indices_valid, scans_dp, labels_dp, None, to_shuffle=False)
#     evaluation_res = evaluate_net(net, gen, {'loss': loss_func}, len(indices_valid), device,
#                                   f'evaluation for top losses')
#     top_losses = sorted(evaluation_res['loss']['list'], key=lambda x: x[1], reverse=True)
#     top_losses_indices = [x[0] for x in top_losses[:max_top_losses_cnt]]
#
#     # store top losses slice indices
#     top_losses_indices_fp = f'{dir}/top_losses_indices_{loss_name}.pickle'
#     print(f'storing top losses indices under "{top_losses_indices_fp}"')
#     with open(top_losses_indices_fp, 'wb') as fout:
#         pickle.dump(top_losses_indices, fout)
#
#     visualize_segmentation(net, top_losses_indices, scans_dp,
#                            labels_dp, dir=f'{dir}/top_{loss_name}_values_slices/{loss_name}/')
#
#     return top_losses_indices


def hausdorff_distance(input_bin, target, max_ahd=np.inf):
    """
    Compute the Averaged Hausdorff Distance function
    :param input_bin: HxW tensor
    :param target: HxW tensor
    :param max_ahd: Maximum AHD possible to return if any set is empty. Default: inf.
    """

    # convert to numpy
    v1 = input_bin.cpu().detach().numpy()
    v2 = target.cpu().detach().numpy()

    # get coordinates of class 1 points
    p1 = np.argwhere(v1 == 1)
    p2 = np.argwhere(v2 == 1)

    if len(p1) == 0 or len(p2) == 0:
        return max_ahd

    d = pairwise_distances(p1, p2, metric='euclidean')
    hd1 = np.max(np.min(d, axis=0))
    hd2 = np.max(np.min(d, axis=1))
    res = max(hd1, hd2)

    return res


def average_hausdorff_distance(input_bin, target, max_ahd=np.inf):
    """
    Compute the Averaged Hausdorff Distance function
    :param input_bin: HxW tensor
    :param target: HxW tensor
    :param max_ahd: Maximum AHD possible to return if any set is empty. Default: inf.
    """

    # convert to numpy
    v1 = input_bin.cpu().detach().numpy()
    v2 = target.cpu().detach().numpy()

    # get coordinates of class 1 points
    p1 = np.argwhere(v1 == 1)
    p2 = np.argwhere(v2 == 1)

    if len(p1) == 0 or len(p2) == 0:
        return max_ahd

    d = pairwise_distances(p1, p2, metric='euclidean')
    hd1 = np.mean(np.min(d, axis=0))
    hd2 = np.mean(np.min(d, axis=1))
    res = max(hd1, hd2)

    return res


def get_hd_for_valid_slices(net, device, loss_name, indices_valid, scans_dp, labels_dp, dir='results'):
    """
    :param checkpoints: dict(loss_name: checkpoint_path)
    """
    net.eval()
    n_valid = len(indices_valid)

    valid_gen = utils.get_scans_and_masks_batches(
        indices_valid, scans_dp, labels_dp, None, aug_cnt=0, to_shuffle=False)
    hd = []
    hd_avg = []
    with torch.no_grad():
        with tqdm.tqdm(total=n_valid, desc=f'{loss_name} model: hausdorff distance',
                       unit='scan', leave=True) as pbar:
            for ix, (slice, labels, slice_ix) in enumerate(valid_gen, start=1):
                x = torch.tensor(slice, dtype=torch.float, device=device).unsqueeze(0).unsqueeze(0)
                y = torch.tensor(labels, dtype=torch.float, device=device).unsqueeze(0).unsqueeze(0)
                out = net(x)
                out_bin = (out > 0.5).float().squeeze(0).squeeze(0)
                y_squeezed = y.squeeze(0).squeeze(0)

                val = hausdorff_distance(out_bin, y_squeezed)
                hd.append((slice_ix, val))

                val_avg = average_hausdorff_distance(out_bin, y_squeezed)
                hd_avg.append((slice_ix, val_avg))

                pbar.update()

    # store hausdorff distance metric values to .pickle and .txt

    hd = sorted(hd, key=lambda x: x[1], reverse=True)
    with open(f'{dir}/{loss_name}_hd_valid.pickle', 'wb') as fout:
        pickle.dump(hd, fout)
    with open(f'{dir}/{loss_name}_hd_valid.txt', 'w') as fout:
        fout.writelines('\n'.join(map(str, hd)))

    hd_avg = sorted(hd_avg, key=lambda x: x[1], reverse=True)
    with open(f'{dir}/{loss_name}_hd_avg_valid.pickle', 'wb') as fout:
        pickle.dump(hd_avg, fout)
    with open(f'{dir}/{loss_name}_hd_avg_valid.txt', 'w') as fout:
        fout.writelines('\n'.join(map(str, hd_avg)))

    return hd, hd_avg


def build_hd_boxplot(hd_values, average, loss_name, dir='results', ax=None):
    """
    build Hausdorff distances box plot
    """
    store = True if ax is None else False
    if not ax:
        fig, ax = plt.subplots(1, 1, figsize=(5, 5))
        fig.suptitle(('average ' if average else '') + 'hausdorff values')
    else:
        fig = ax.get_figure()
    if not isinstance(hd_values, np.ndarray):
        hd_values = np.array(hd_values)
    ax.boxplot(hd_values, showfliers=False)
    hd_mean = np.mean(hd_values[np.isfinite(hd_values)])
    ax.set_title(f'{loss_name}. mean: {hd_mean : .3f}')
    if store:
        fig.savefig(f'{dir}/{loss_name}_hd_{"avg_" if average else ""}boxplot.png', dpi=200)


def build_multiple_hd_boxplots(metrics_hd, average, loss_names_list, dir='results'):
    """
    build Hausdorff distances box plot for multiple metrics on the same figure
    """
    n = len(metrics_hd)
    fig, ax = plt.subplots(1, n, figsize=(5 * n, 5), squeeze=False)
    for hd_tuples_list, loss_name, a in zip(metrics_hd, loss_names_list, ax.flatten()):
        build_hd_boxplot([x[1] for x in hd_tuples_list], average, loss_name, dir=dir, ax=a)
    fig.suptitle(f'total {"avg " if average else ""}Hausdorff distances boxplot')
    fig.savefig(f'{dir}/total_hd_{"avg_" if average else ""}boxplot.png', dpi=200)


def visualize_worst_best(net, scan_ix_and_hd, average, scans_dp, labels_dp, device, loss_name, dir='results'):
    hd_sorted = sorted(scan_ix_and_hd, key=lambda x: x[1])

    cnt = 8
    worst = hd_sorted[:-cnt - 1:-1]
    worst_ix = [x[0] for x in worst]
    worst_values = [x[1] for x in worst]

    best = hd_sorted[:cnt]
    best_ix = [x[0] for x in best]
    best_values = [x[1] for x in best]

    for slice_indices, values, title in zip([worst_ix, best_ix], [worst_values, best_values], ['Worst', 'Best']):
        gen = utils.get_scans_and_masks_batches(slice_indices, scans_dp, labels_dp, None, aug_cnt=0, to_shuffle=False)
        fig, ax = plt.subplots(2, cnt // 2, figsize=(5 * cnt // 2, 5 * 2), squeeze=False)
        net.eval()
        with torch.no_grad():
            for (slice, labels, scan_ix), v, _ax in zip(gen, values, ax.flatten()):
                x = torch.tensor(slice, dtype=torch.float, device=device).unsqueeze(0).unsqueeze(0)
                out = net(x)
                out_bin = (out > 0.5).float()
                out_bin_np = utils.squeeze_and_to_numpy(out_bin).astype(np.int)

                slice_f = img_as_float((slice - np.min(slice)).astype(np.int))
                b_true = mark_boundaries(slice_f, labels)
                b_pred = mark_boundaries(slice_f, out_bin_np.astype(np.int), color=(1, 0, 0))
                b = np.max([b_true, b_pred], axis=0)
                _ax.imshow(slice_f, origin='lower')
                _ax.imshow(b, alpha=.4, origin='lower')
                _ax.set_title(f'{scan_ix}: {v : .3f}')

        fig.tight_layout()
        fig.subplots_adjust(top=0.85)
        fig.suptitle(f'{loss_name}. {title} {"Average " if average else ""}Hausdorff distances')
        fig.savefig(f'{dir}/{loss_name}_hd_{"avg_" if average else ""}{title}.png', dpi=200)


def segment_scan(fns, net, device, scans_dp, labels_dp, dir='results'):
    cp_fp = 'results/existing_checkpoints/cp_BCELoss_epoch_9.pth'

    print(const.SEPARATOR)
    print(f'loading existing model from "{cp_fp}"')
    net.to(device=device)
    state_dict = torch.load(cp_fp)
    net.load_state_dict(state_dict)

    net.eval()
    with torch.no_grad():
        for fn in fns:

            os.makedirs(f'{dir}/bce/{fn}', exist_ok=True)
            scan = np.load(f'{scans_dp}/{fn}', allow_pickle=False)
            labels = np.load(f'{labels_dp}/{fn}', allow_pickle=False)

            with tqdm.tqdm(total=scan.shape[2]) as pbar:
                for z_ix in range(scan.shape[2]):
                    x = scan[:, :, z_ix]
                    y = labels[:, :, z_ix]
                    x_t = torch.tensor(x, dtype=torch.float, device=device).unsqueeze(0).unsqueeze(0)
                    preds = net(x_t)
                    mask = (preds > 0.5).float()
                    mask = utils.squeeze_and_to_numpy(mask).astype(np.int)

                    slice_f = img_as_float((x - np.min(x)).astype(np.int))
                    b_true = mark_boundaries(slice_f, y)
                    b_pred = mark_boundaries(slice_f, mask.astype(np.int), color=(1, 0, 0))
                    b = np.max([b_true, b_pred], axis=0)
                    fig, ax = plt.subplots(1, 1, figsize=(5, 5))
                    ax.imshow(slice_f, origin='lower')
                    ax.imshow(b, alpha=.4, origin='lower')
                    ax.set_title(f'{fn}. z = {z_ix}')
                    ax.axis('off')
                    fig.savefig(f'{dir}/bce/{fn}/{z_ix}.png', dpi=150)
                    plt.close(fig)

                    pbar.update()


def segment_scans(filenames: str, net, device, dataset_dp, segmented_masks_dp):
    scans_dp = const.get_numpy_scans_dp(dataset_dp)
    nifti_dp = const.get_nifti_dp(dataset_dp)

    with tqdm.tqdm(total=len(filenames)) as pbar:
        for fn in filenames:
            pbar.set_description(fn)

            gen = get_single_image_slice_gen(os.path.join(scans_dp, fn))

            outs = []

            net.eval()
            with torch.no_grad():
                for scan_slices in gen:
                    x = torch.tensor(scan_slices, dtype=torch.float, device=device).unsqueeze(1)
                    out = net(x)
                    out = utils.squeeze_and_to_numpy(out)
                    out = (out > 0.5).astype(np.uint8)

                    if len(out.shape) == 2:
                        # `out` is an array of shape (H, W)
                        outs.append(out)
                    elif len(out.shape) == 3:
                        # `out` is an array of shape (N, H, W)
                        outs.extend(out)

            out_combined = np.stack(outs, axis=2)

            # load corresponding nifti image to extract header and store `out_combined` data as nifti
            file_id = re.match(r'(id[\d]+)\.npy', fn).groups()[0]
            nifti_fn = os.path.join(nifti_dp, f'{file_id}_autolungs.nii.gz')
            nifti = nibabel.load(nifti_fn)
            out_combined_nifti = utils.change_nifti_data(out_combined, nifti, is_scan=False)

            out_fp = os.path.join(segmented_masks_dp, f'{file_id}_autolungs.nii.gz')
            utils.store_nifti_to_file(out_combined_nifti, out_fp)

            pbar.update()