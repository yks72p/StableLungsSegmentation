import sys

sys.path.append('./src')

import click

import const
import os
import utils
from data.datasets import NumpyDataset, NiftiDataset
from data.train_valid_split import load_split_from_json
from model.losses import *
from pipeline import Pipeline, METRICS_DICT


@click.group()
def cli():
    pass


@cli.command()
@click.option('--launch', help='launch location',
              type=click.Choice(['local', 'server']), default='local')
@click.option('--launch', help='launch location',
              type=click.Choice(['local', 'server']), default='local')
@click.option('--device', help='device to use',
              type=click.Choice(['cpu', 'cuda:0', 'cuda:1']), default='cuda:0')
def train(launch: str, device: str):
    print(const.SEPARATOR)
    print('train_pipeline()')

    loss_func = METRICS_DICT['NegDiceLoss']
    metrics = [
        METRICS_DICT['BCELoss'],
        METRICS_DICT['NegDiceLoss'],
        METRICS_DICT['FocalLoss']
    ]

    const.set_launch_type_env_var(launch == 'local')
    data_paths = const.DataPaths()
    dataset_dp = data_paths.get_processed_dataset_dp(zoom_factor=0.25, mark_as_new=False)

    device = torch.device('cuda:0')
    split = load_split_from_json(data_paths.get_train_valid_split_fp())

    train_dataset = NumpyDataset(dataset_dp, split['train'])
    valid_dataset = NumpyDataset(dataset_dp, split['valid'])
    # pipeline = Pipeline(
    #     train_dataset=train_dataset, valid_dataset=valid_dataset,
    #     loss_func=loss_func, metrics=metrics,
    #     device=device
    # )
    #
    # # TODO: add as option
    # to_train = True
    #
    # if to_train:
    #     pipeline.train(n_epochs=8, train_orig_img_per_batch=4, train_aug_cnt=0, valid_batch_size=4)
    # else:
    #     checkpoint_fp = f'results/model_checkpoints/cp_NegDiceLoss_best.pth'
    #     pipeline.load_net_from_weights(checkpoint_fp)
    #
    # # pipeline.evaluate_model()
    # utils.print_cuda_memory_stats(device)


@cli.command()
@click.option('--launch', help='launch location',
              type=click.Choice(['local', 'server']), default='local')
@click.option('--device', help='device to use',
              type=click.Choice(['cpu', 'cuda:0', 'cuda:1']), default='cuda:0')
def sanity_check(launch: str, device: str):
    # TODO: move to `train` function as an option
    loss_func = METRICS_DICT['NegDiceLoss']
    metrics = [
        METRICS_DICT['BCELoss'],
        METRICS_DICT['NegDiceLoss'],
        METRICS_DICT['FocalLoss']
    ]

    const.set_launch_type_env_var(launch == 'local')
    data_paths = const.DataPaths()

    split = load_split_from_json(data_paths.get_train_valid_split_fp())
    scans_dp = data_paths.scans_dp
    masks_dp = data_paths.masks_dp
    train_dataset = NiftiDataset(scans_dp, masks_dp, split['train'])
    valid_dataset = NiftiDataset(scans_dp, masks_dp, split['valid'])

    device_t = torch.device(device)
    pipeline = Pipeline(device=device_t)

    pipeline.train(
        train_dataset=train_dataset, valid_dataset=valid_dataset,
        n_epochs=50, loss_func=loss_func, metrics=metrics,
        train_orig_img_per_batch=4, train_aug_cnt=0, valid_batch_size=4,
        max_batches=10
    )
    utils.print_cuda_memory_stats(device)


@cli.command()
@click.option('--launch', help='launch location',
              type=click.Choice(['local', 'server']), default='local')
@click.option('--device', help='device to use',
              type=click.Choice(['cpu', 'cuda:0', 'cuda:1']), default='cuda:0')
@click.option('--checkpoint', 'checkpoint_fn',
              help='checkpoint .pth filename with model parameters. '
                   'the file is searched for under "results/model_checkpoints" dir',
              type=click.STRING, default=None)
@click.option('--out', 'output_dp', help='path to output directory with segmented masks',
              type=click.STRING, default=None)
@click.option('--postfix', help='postfix to set for segmented masks',
              type=click.STRING, default=None)
def segment_valid_scans(
        launch: str, device: str, checkpoint_fn: str, output_dp: str, postfix: str
):
    const.set_launch_type_env_var(launch == 'local')
    data_paths = const.DataPaths()
    split = load_split_from_json(data_paths.get_train_valid_split_fp())

    device_t = torch.device(device)
    pipeline = Pipeline(device=device_t)

    checkpoint_fn = checkpoint_fn or 'cp_NegDiceLoss_best.pth'
    checkpoint_fp = os.path.join(f'results', 'model_checkpoints', checkpoint_fn)
    pipeline.segment_scans(
        checkpoint_fp=checkpoint_fp, scans_dp=data_paths.scans_dp,
        ids_list=split['valid'], output_dp=output_dp, postfix=postfix
    )
    utils.print_cuda_memory_stats(device)


if __name__ == '__main__':
    cli()
