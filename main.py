import sys

sys.path.append('./src')

import click
import os

import utils
import const
from data.datasets import NiftiDataset, NumpyDataset
from model.losses import *
from pipeline import Pipeline, METRICS_DICT


@click.group()
def cli():
    pass


@cli.command()
@click.option('--launch', help='launch location',
              type=click.Choice(['local', 'server']), default='local')
@click.option('--device', help='device to use',
              type=click.Choice(['cpu', 'cuda:0', 'cuda:1']), default='cuda:0')
@click.option('--dataset', 'dataset_type', help='dataset type',
              type=click.Choice(['nifti', 'numpy']), default='numpy')
@click.option('--epochs', 'n_epochs', help='max number of epochs to train',
              type=click.INT, required=True)
@click.option('--max-batches', help='max number of batches to process. use as sanity check. '
                                    'if no value passed than will process the whole dataset.',
              type=click.INT, default=None)
@click.option('--checkpoint', 'initial_checkpoint_fp', help='path to initial .pth checkpoint for warm start',
              type=click.STRING, default=None)
def train(
        launch: str, device: str, dataset_type: str,
        n_epochs: int, max_batches: int, initial_checkpoint_fp: str
):
    loss_func = METRICS_DICT['NegDiceLoss']
    metrics = [
        METRICS_DICT['BCELoss'],
        METRICS_DICT['NegDiceLoss'],
        METRICS_DICT['FocalLoss']
    ]

    const.set_launch_type_env_var(launch == 'local')
    data_paths = const.DataPaths()

    split = utils.load_split_from_yaml(const.TRAIN_VALID_SPLIT_FP)

    if dataset_type == 'nifti':
        train_dataset = NiftiDataset(data_paths.scans_dp, data_paths.masks_dp, split['train'])
        valid_dataset = NiftiDataset(data_paths.scans_dp, data_paths.masks_dp, split['valid'])
    elif dataset_type == 'numpy':
        ndp = const.NumpyDataPaths(data_paths.default_numpy_dataset_dp)
        train_dataset = NumpyDataset(ndp.scans_dp, ndp.masks_dp, ndp.shapes_fp, split['train'])
        valid_dataset = NumpyDataset(ndp.scans_dp, ndp.masks_dp, ndp.shapes_fp, split['valid'])
    else:
        raise ValueError(f'dataset_type must be in ["nifti", "numpy"]. got {dataset_type}')

    device_t = torch.device(device)
    pipeline = Pipeline(device=device_t)

    pipeline.train(
        train_dataset=train_dataset, valid_dataset=valid_dataset,
        n_epochs=n_epochs, loss_func=loss_func, metrics=metrics,
        train_orig_img_per_batch=4, train_aug_cnt=1, valid_batch_size=4,
        max_batches=max_batches, initial_checkpoint_fp=initial_checkpoint_fp
    )


@cli.command()
@click.option('--launch', help='launch location',
              type=click.Choice(['local', 'server']), default='local')
@click.option('--device', help='device to use',
              type=click.Choice(['cpu', 'cuda:0', 'cuda:1']), default='cuda:0')
@click.option('--checkpoint', 'checkpoint_fn',
              help='checkpoint .pth filename with model parameters. '
                   'the file is searched for under "results/model_checkpoints" dir',
              type=click.STRING, default=None)
@click.option('--scans', 'scans_dp', help='path to directory with nifti scans',
              type=click.STRING, default=None)
@click.option('--subset', help='what scans to segment under --scans dir: '
                               'either all, or the ones from "validation" dataset',
              type=click.Choice(['all', 'validation']), default='validation')
@click.option('--out', 'output_dp', help='path to output directory with segmented masks',
              type=click.STRING, default=None)
@click.option('--postfix', help='postfix to set for segmented masks',
              type=click.STRING, default=None)
def segment_scans(
        launch: str, device: str,
        checkpoint_fn: str, scans_dp: str, subset: str,
        output_dp: str, postfix: str
):
    const.set_launch_type_env_var(launch == 'local')
    data_paths = const.DataPaths()

    device_t = torch.device(device)
    pipeline = Pipeline(device=device_t)

    checkpoint_fn = checkpoint_fn or 'cp_NegDiceLoss_epoch_18.pth'
    checkpoint_fp = os.path.join(const.MODEL_CHECKPOINTS_DP, checkpoint_fn)

    scans_dp = scans_dp or data_paths.scans_dp

    ids_list = None
    if subset == 'validation':
        split = utils.load_split_from_yaml(const.TRAIN_VALID_SPLIT_FP)
        ids_list = split['valid']

        # TODO
        # ids_list = ['id00502', 'id00521', 'id00527', 'id00668']

    pipeline.segment_scans(
        checkpoint_fp=checkpoint_fp, scans_dp=scans_dp,
        ids_list=ids_list, output_dp=output_dp, postfix=postfix
    )


@cli.command()
@click.option('--launch', help='launch location',
              type=click.Choice(['local', 'server']), default='local')
@click.option('--scans', 'scans_dp', help='path to directory with nifti scans',
              type=click.STRING, default=None)
@click.option('--masks', 'masks_dp', help='path to directory with nifti binary masks',
              type=click.STRING, default=None)
@click.option('--zoom', 'zoom_factor', help='zoom factor for output images',
              type=click.FLOAT, default=0.25)
@click.option('--out', 'output_dp', help='path to output directory with numpy dataset',
              type=click.STRING, default=None)
def create_numpy_dataset(
        launch: str, scans_dp: str, masks_dp: str, zoom_factor: float, output_dp: str
):
    const.set_launch_type_env_var(launch == 'local')
    data_paths = const.DataPaths()

    scans_dp = scans_dp or data_paths.scans_dp
    masks_dp = masks_dp or data_paths.masks_dp

    numpy_data_root_dp = data_paths.get_numpy_data_root_dp(zoom_factor=zoom_factor)
    output_dp = output_dp or numpy_data_root_dp

    ds = NiftiDataset(scans_dp, masks_dp)
    ds.store_as_numpy_dataset(output_dp, zoom_factor)


if __name__ == '__main__':
    cli()