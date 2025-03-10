# sample2_pools_and_resourcefiles.py Code Sample
#
# Copyright (c) Microsoft Corporation
#
# All rights reserved.
#
# MIT License
#
# Permission is hereby granted, free of charge, to any person obtaining a
# copy of this software and associated documentation files (the "Software"),
# to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense,
# and/or sell copies of the Software, and to permit persons to whom the
# Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED *AS IS*, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# DEALINGS IN THE SOFTWARE.

"""
Create a pool and submit a task which use resource files.
"""

import datetime
import os
from configparser import ConfigParser

from azure.core.exceptions import ResourceExistsError

from azure.storage.blob import BlobServiceClient
from azure.batch import BatchServiceClient
from azure.batch.batch_auth import SharedKeyCredentials
import azure.batch.models as batchmodels

import common.helpers

_CONTAINER_NAME = 'poolsandresourcefiles'
_SIMPLE_TASK_NAME = 'simple_task.py'
_SIMPLE_TASK_PATH = os.path.join('resources', 'simple_task.py')


def create_pool(
        batch_client: BatchServiceClient,
        blob_service_client: BlobServiceClient,
        pool_id: str,
        vm_size: str,
        vm_count: int):
    """Creates an Azure Batch pool with the specified id.

    :param batch_client: The batch client to use.
    :param blob_service_client: The storage block blob client to use.
    :param pool_id: The id of the pool to create.
    :param vm_size: vm size (sku)
    :param vm_count: number of vms to allocate
    """
    # pick the latest supported 16.04 sku for UbuntuServer
    sku_to_use, image_ref_to_use = \
        common.helpers.select_latest_verified_vm_image_with_node_agent_sku(
            batch_client, 'canonical', 'ubuntuserver', '18.04')

    try:
        blob_service_client.create_container(_CONTAINER_NAME)
    except ResourceExistsError:
        pass

    sas_url = common.helpers.upload_blob_and_create_sas(
        blob_service_client,
        _CONTAINER_NAME,
        _SIMPLE_TASK_NAME,
        _SIMPLE_TASK_PATH,
        datetime.datetime.utcnow() + datetime.timedelta(hours=1))

    pool = batchmodels.PoolAddParameter(
        id=pool_id,
        virtual_machine_configuration=batchmodels.VirtualMachineConfiguration(
            image_reference=image_ref_to_use,
            node_agent_sku_id=sku_to_use),
        vm_size=vm_size,
        target_dedicated_nodes=vm_count,
        start_task=batchmodels.StartTask(
            # command_line=helpers.wrap_commands_in_shell('linux',
            #                                             task_commands)
            command_line="python " + _SIMPLE_TASK_NAME,
            resource_files=[batchmodels.ResourceFile(
                            file_path=_SIMPLE_TASK_NAME,
                            http_url=sas_url)]))

    common.helpers.create_pool_if_not_exist(batch_client, pool)


def submit_job_and_add_task(
        batch_client: BatchServiceClient,
        blob_service_client: BlobServiceClient,
        job_id: str,
        pool_id: str):
    """Submits a job to the Azure Batch service and adds
    a task that runs a python script.

    :param batch_client: The batch client to use.
    :param blob_service_client: The storage block blob client to use.
    :param job_id: The id of the job to create.
    :param pool_id: The id of the pool to use.
    """
    job = batchmodels.JobAddParameter(
        id=job_id,
        pool_info=batchmodels.PoolInformation(pool_id=pool_id))

    batch_client.job.add(job)

    try:
        blob_service_client.create_container(_CONTAINER_NAME)
    except ResourceExistsError:
        pass

    sas_url = common.helpers.upload_blob_and_create_sas(
        blob_service_client,
        _CONTAINER_NAME,
        _SIMPLE_TASK_NAME,
        _SIMPLE_TASK_PATH,
        datetime.datetime.utcnow() + datetime.timedelta(hours=1))

    task = batchmodels.TaskAddParameter(
        id="MyPythonTask",
        command_line="python " + _SIMPLE_TASK_NAME,
        resource_files=[batchmodels.ResourceFile(
                        file_path=_SIMPLE_TASK_NAME,
                        http_url=sas_url)])

    batch_client.task.add(job_id=job.id, task=task)


def execute_sample(global_config: ConfigParser, sample_config: ConfigParser):
    """Executes the sample with the specified configurations.

    :param global_config: The global configuration to use.
    :param sample_config: The sample specific configuration to use.
    """
    # Set up the configuration
    batch_account_key = global_config.get('Batch', 'batchaccountkey')
    batch_account_name = global_config.get('Batch', 'batchaccountname')
    batch_service_url = global_config.get('Batch', 'batchserviceurl')

    storage_account_url = global_config.get('Storage', 'storageaccounturl')
    storage_account_key = global_config.get('Storage', 'storageaccountkey')

    should_delete_container = sample_config.getboolean(
        'DEFAULT',
        'shoulddeletecontainer')
    should_delete_job = sample_config.getboolean(
        'DEFAULT',
        'shoulddeletejob')
    should_delete_pool = sample_config.getboolean(
        'DEFAULT',
        'shoulddeletepool')
    pool_vm_size = sample_config.get(
        'DEFAULT',
        'poolvmsize')
    pool_vm_count = sample_config.getint(
        'DEFAULT',
        'poolvmcount')

    # Print the settings we are running with
    common.helpers.print_configuration(global_config)
    common.helpers.print_configuration(sample_config)

    credentials = SharedKeyCredentials(
        batch_account_name,
        batch_account_key)

    batch_client = BatchServiceClient(
        credentials,
        batch_url=batch_service_url)

    # Retry 5 times -- default is 3
    batch_client.config.retry_policy.retries = 5
    # FIXME: this url does not calculate right and is a little different than dashboard advice
    storage_account_url = 'https://perssto.blob.core.windows.net'
    blob_service_client = BlobServiceClient(
        account_url=storage_account_url,
        credential=storage_account_key)

    job_id = common.helpers.generate_unique_resource_name(
        "PoolsAndResourceFilesJob")
    pool_id = "PoolsAndResourceFilesPool"
    try:
        create_pool(
            batch_client,
            blob_service_client,
            pool_id,
            pool_vm_size,
            pool_vm_count)

        submit_job_and_add_task(
            batch_client,
            blob_service_client,
            job_id, pool_id)

        common.helpers.wait_for_tasks_to_complete(
            batch_client,
            job_id,
            datetime.timedelta(minutes=25))

        tasks = batch_client.task.list(job_id)
        task_ids = [task.id for task in tasks]

        common.helpers.print_task_output(batch_client, job_id, task_ids)
    finally:
        # clean up
        if should_delete_container:
            blob_service_client.delete_container(_CONTAINER_NAME)
        if should_delete_job:
            print("Deleting job: ", job_id)
            batch_client.job.delete(job_id)
        if should_delete_pool:
            print("Deleting pool: ", pool_id)
            batch_client.pool.delete(pool_id)


if __name__ == '__main__':
    global_cfg = ConfigParser()
    global_cfg.read(common.helpers.SAMPLES_CONFIG_FILE_NAME)

    sample_cfg = ConfigParser()
    sample_cfg.read(
        os.path.splitext(os.path.basename(__file__))[0] + '.cfg')

    execute_sample(global_cfg, sample_cfg)
