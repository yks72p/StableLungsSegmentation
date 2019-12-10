import datetime
import os
import pickle
import shutil
import sys

import matplotlib.pyplot as plt
import nibabel
import numpy as np
import torch
import tqdm
from tabulate import tabulate

separator = f'\n{"=" * 20}'


def show_slices(
        slices, titles=None,
        cols=4, width=5, height=5, to_show_axis=False
):
    rows = len(slices) // cols + (1 if len(slices) % cols > 0 else 0)
    fig, ax = plt.subplots(
        rows, cols, figsize=(width * cols, height * rows), squeeze=False)
    ax_flatten = ax.flatten()

    if titles is not None:
        if not len(slices) == len(titles):
            raise ValueError('slices and title must have the same len')

    for i in range(len(slices)):
        ax_flatten[i].imshow(slices[i], origin='lower', cmap='gray')
        if not to_show_axis: ax_flatten[i].axis('off')
        if titles is not None: ax_flatten[i].set_title(titles[i])
    for i in range(len(slices), len(ax_flatten)):
        ax_flatten[i].set_visible(False)
    fig.tight_layout()
    fig.subplots_adjust(top=(0.85 if titles is not None else 0.95))
    return fig, ax


def diagonal_abs(matrix):
    if matrix.shape[0] != matrix.shape[1]:
        raise ValueError('matrix must be square. shape: %s' % str(matrix.shape))
    new = matrix.copy()
    for i in range(len(matrix)):
        new[i, i] = np.abs(new[i, i])
    return new


def print_np_stats(obj, description=None, k=1):
    sz = sys.getsizeof(obj) / 1024 / 1024
    description = '%s: ' % description if description is not None else ''
    s = sorted(np.unique(obj))
    print(f'{description}shape: {obj.shape} dtype: {obj.dtype} min: {s[:k]} max: {s[-k:]} MB: {sz:.3g}')


def get_some_slices_from_img(data):
    z_max = data.shape[2]
    slices = [data[:, :, (z_max // 5 * x)] for x in range(1, 5)]
    return slices


def get_mid_slice(arr, matrix_axis=2):
    if matrix_axis not in [0, 1, 2]:
        raise ValueError('matrix_axis must be in [0, 1, 2]')
    data = arr[:, :, arr.shape[2] // 2] if matrix_axis == 2 \
        else arr[arr.shape[0] // 2, :, :] if matrix_axis == 0 \
        else arr[:, arr.shape[1] // 2, :]
    return data


def copy_checkpoints_to_gdrive(checkpoints_dp):
    date_str = datetime.date.today().strftime('%m.%d.%y')
    gdrive_dest = f'/gdrive/My Drive/datasets/kursavaja_7_sem/{date_str}'
    print(f'store checkpoints to {gdrive_dest}')

    if os.path.isdir(gdrive_dest):
        print('removed old dir')
        shutil.rmtree(gdrive_dest)

    shutil.copytree(checkpoints_dp, gdrive_dest)


def plot_learning_curves(epoch_metrics):
    metrics = np.unique([x.split('_')[0] for x in epoch_metrics.keys()])
    n_epochs = max([len(l) for l in epoch_metrics.values()])
    x = np.arange(1, n_epochs + 1)
    fig, ax = plt.subplots(1, len(metrics), figsize=(6 * len(metrics), 5), squeeze=False)

    for m, _ax in zip(metrics, ax.flatten()):
        if len(epoch_metrics[f'{m}_train']) == len(x):
            _ax.plot(x, epoch_metrics[f'{m}_train'], marker='o', label='train')
        _ax.plot(x, epoch_metrics[f'{m}_valid'], marker='o', label='valid')
        _ax.set_title(m)
        _ax.grid()
        _ax.legend()

    return fig, ax


def squeeze_and_to_numpy(tz):
    return tz.squeeze().cpu().detach().numpy()


def get_scans_z_dimensions(scans_fns, scans_dp, restore_prev=True):
    """extract z-dimension for each scan"""

    scans_z_fp = os.path.realpath(f'{scans_dp}/../scans_z.pickle')

    if restore_prev:
        if not os.path.isfile(scans_z_fp):
            raise ValueError(f'no file found at {scans_z_fp}')
        print(f'reading from {scans_z_fp}')
        with open(scans_z_fp, 'rb') as fin:
            scans_z = pickle.load(fin)
    else:
        scans_z = {}
        for fn in tqdm.tqdm(scans_fns):
            scan = np.load(os.path.join(scans_dp, fn), allow_pickle=False)
            scans_z[fn] = scan.shape[2]
        print(f'storing scans_z to {scans_z_fp}')
        with open(scans_z_fp, 'wb') as fout:
            pickle.dump(scans_z, fout)

    return scans_z


def get_scans_and_labels_batches(indices, scans_dp, labels_dp, batch_size, to_shuffle=True):
    '''
    indices: tuple (filename, z_index)
    '''

    if to_shuffle:
        np.random.shuffle(indices)

    foo = lambda indices, dp: (
        np.load(os.path.join(dp, x[0]), allow_pickle=False)[:, :, x[1]]
        for x in indices
    )
    scans_gen = foo(indices, scans_dp)
    labels_gen = foo(indices, labels_dp)

    if batch_size is not None and batch_size > 0:
        # yield by batches
        scans_batch, labels_batch, ix_batch = [], [], []
        for en_ix, (s, l, ix) in enumerate(zip(scans_gen, labels_gen, indices)):
            scans_batch.append(s)
            labels_batch.append(l)
            ix_batch.append(ix)
            if (en_ix + 1) % batch_size == 0:
                yield (scans_batch, labels_batch, ix_batch)
                scans_batch, labels_batch, ix_batch = [], [], []
        if len(scans_batch) > 0:
            yield (scans_batch, labels_batch, ix_batch)
    else:
        # yield by one item
        for s, l, ix in zip(scans_gen, labels_gen, indices):
            yield (s, l, ix)


def print_cuda_memory_stats():
    print(
        f'allocated: {torch.cuda.memory_allocated("cuda") / 1024 / 1024 : .2f} '
        f'(max: {torch.cuda.max_memory_allocated("cuda") / 1024 / 1024 : .2f}), '
        f'cached: {torch.cuda.memory_cached("cuda") / 1024 / 1024 : .2f} '
        f'(max: {torch.cuda.max_memory_cached("cuda") / 1024 / 1024 : .2f})'
    )


######### unused #########

def compare_pair(pair):
    initial = nibabel.load(pair['initial'])
    resegm = nibabel.load(pair['resegm'])
    transformed = np.flip(resegm.get_data(), axis=0)

    print(affine_tables_to_str([initial, resegm]))

    slices = [get_mid_slice(x, a) for a in [2, 1] for x in [initial.dataobj, resegm.dataobj, transformed]]
    titles = [x for x in ['initial', 'resegm', 'transformed']]
    titles.extend(titles)
    show_slices(slices, titles, cols=3)


def vec2str(vec):
    return ('{:+9.3f}' * len(vec)).format(*vec)


def affine_tables_to_str(nibabel_images):
    headers = [os.path.basename(x.get_filename()) for x in nibabel_images]
    table = [[vec2str(x.affine[i]) for x in nibabel_images] for i in range(4)]
    return tabulate(table, headers=headers, tablefmt='pipe', stralign='center')


def get_unique_signs_for_diag_elements(nibabel_fps):
    diag_initial = []
    for fn in tqdm.tqdm(nibabel_fps):
        nii = nibabel.load(fn)
        diag_initial.append(np.sign(np.diag(nii.affine)))
    unique = np.unique(diag_initial, axis=0)
    return unique


def get_lower_intensities(img_dicts_list, img_type):
    if not img_type in ['initial', 'fixed']:
        raise ValueError("img_type must be in ['initial', 'fixed']")
    lower_intensities = []
    with tqdm.tqdm(total=len(img_dicts_list)) as pbar:
        for k, v in img_dicts_list.items():
            img = nibabel.load(v[img_type])
            m = sorted(np.unique(img.get_data()))
            lower_intensities.append({k: m})
            pbar.update()
    return lower_intensities


def show_pixel_intensities_hist(img_dicts_list, img_ids, columns=4, width=5, height=4):
    rows = len(img_ids) // columns + (1 if len(img_ids) % columns > 0 else 0)
    fig, ax = plt.subplots(rows, columns, figsize=(width * columns, height * rows), squeeze=False)
    ax_flatten = ax.flatten()
    with tqdm.tqdm(total=len(img_ids)) as pbar:
        for i in range(len(img_ids)):
            img = nibabel.load(img_dicts_list[img_ids[i]]['initial'])
            ax_flatten[i].hist(img.get_data().flatten())
            ax_flatten[i].set_title(img_ids[i])
            pbar.update()
    for i in range(len(img_ids), len(ax_flatten)):
        ax_flatten[i].set_visible(False)
    fig.tight_layout()
    fig.subplots_adjust(top=0.9)
    return fig, ax