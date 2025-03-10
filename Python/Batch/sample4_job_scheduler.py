# sample4_job_scheduler.py Code Sample
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
Create a job schedule to run a task 30 minutes into the future
"""

from configparser import ConfigParser

import datetime
import os

from azure.core.exceptions import ResourceNotFoundError

from azure.storage.blob import BlobServiceClient

from azure.batch import BatchServiceClient
from azure.batch.batch_auth import SharedKeyCredentials
import azure.batch.models as batchmodels

import common.helpers

_CONTAINER_NAME = 'jobscheduler'
_SIMPLE_TASK_NAME = 'simple_task.py'
_SIMPLE_TASK_PATH = os.path.join('resources', 'simple_task.py')
_PYTHON_DOWNLOAD = \
    'https://www.python.org/ftp/python/3.7.3/python-3.7.3-amd64.exe'
_PYTHON_INSTALL = \
    r'.\python373.exe /passive InstallAllUsers=1 PrependPath=1 Include_test=0'
_USER_ELEVATION_LEVEL = 'admin'
_START_TIME = datetime.datetime.utcnow()
_END_TIME = _START_TIME + datetime.timedelta(minutes=30)


def create_job_schedule(
    batch_client: BatchServiceClient,
    job_schedule_id: str,
    vm_size: str,
    vm_count: int,
    blob_service_client: BlobServiceClient
):
    """Creates an Azure Batch pool and job schedule with the specified ids.

    :param batch_client: The batch client to use.
    :param job_schedule_id: The id of the job schedule to create
    :param vm_size: vm size (sku)
    :param vm_count: number of vms to allocate
    :param blob_service_client: The storage block blob client to use.
    """
    vm_config = batchmodels.VirtualMachineConfiguration(
        image_reference=batchmodels.ImageReference(
            publisher="microsoftwindowsserver",
            offer="windowsserver",
            sku="2019-datacenter-core"
        ),
        node_agent_sku_id="batch.node.windows amd64"
    )

    user_id = batchmodels.UserIdentity(
        auto_user=batchmodels.AutoUserSpecification(
            elevation_level=_USER_ELEVATION_LEVEL))

    python_download = batchmodels.ResourceFile(
        http_url=_PYTHON_DOWNLOAD,
        file_path='python373.exe')

    pool_info = batchmodels.PoolInformation(
        auto_pool_specification=batchmodels.AutoPoolSpecification(
            auto_pool_id_prefix="JobScheduler",
            pool=batchmodels.PoolSpecification(
                vm_size=vm_size,
                target_dedicated_nodes=vm_count,
                virtual_machine_configuration=vm_config,
                start_task=batchmodels.StartTask(
                    command_line=common.helpers.wrap_commands_in_shell(
                        'windows', [f'{_PYTHON_INSTALL}']),
                    resource_files=[python_download],
                    wait_for_success=True,
                    user_identity=user_id)),
            keep_alive=False,
            pool_lifetime_option=batchmodels.PoolLifetimeOption.job))

    sas_url = common.helpers.upload_blob_and_create_sas(
        blob_service_client,
        _CONTAINER_NAME,
        _SIMPLE_TASK_NAME,
        _SIMPLE_TASK_PATH,
        datetime.datetime.utcnow() + datetime.timedelta(minutes=30))

    job_spec = batchmodels.JobSpecification(
        pool_info=pool_info,
        # Terminate job once all tasks under it are complete to allow for a new
        # job to be created under the schedule
        on_all_tasks_complete=batchmodels.OnAllTasksComplete.terminate_job,
        job_manager_task=batchmodels.JobManagerTask(
            id="JobManagerTask",
            command_line=common.helpers.wrap_commands_in_shell(
                'windows', [f'python {_SIMPLE_TASK_NAME}']),
            resource_files=[batchmodels.ResourceFile(
                file_path=_SIMPLE_TASK_NAME,
                http_url=sas_url)]))

    do_not_run_after = datetime.datetime.utcnow() \
        + datetime.timedelta(minutes=30)

    schedule = batchmodels.Schedule(
        do_not_run_after=do_not_run_after,
        recurrence_interval=datetime.timedelta(minutes=10))

    scheduled_job = batchmodels.JobScheduleAddParameter(
        id=job_schedule_id,
        schedule=schedule,
        job_specification=job_spec)

    batch_client.job_schedule.add(cloud_job_schedule=scheduled_job)


def execute_sample(global_config: ConfigParser, sample_config: ConfigParser):
    """Executes the sample with the specified configurations.

    :param global_config: The global configuration to use.
    :type global_config: `configparser.ConfigParser`
    :param sample_config: The sample specific configuration to use.
    :type sample_config: `configparser.ConfigParser`
    """
    # Set up the configuration
    batch_account_key = global_config.get('Batch', 'batchaccountkey')
    batch_account_name = global_config.get('Batch', 'batchaccountname')
    batch_service_url = global_config.get('Batch', 'batchserviceurl')

    storage_account_key = global_config.get('Storage', 'storageaccountkey')
    storage_account_url = global_config.get('Storage', 'storageaccounturl')

    should_delete_container = sample_config.getboolean(
        'DEFAULT',
        'shoulddeletecontainer')
    should_delete_job_schedule = sample_config.getboolean(
        'DEFAULT',
        'shoulddeletejobschedule')
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
    # FIXME:
    storage_account_url = 'https://perssto.blob.core.windows.net'
    blob_service_client = BlobServiceClient(
        account_url=storage_account_url,
        credential=storage_account_key)

    batch_client.config.retry_policy.retries = 5
    job_schedule_id = common.helpers.generate_unique_resource_name(
        "JobScheduler")

    try:
        create_job_schedule(
            batch_client,
            job_schedule_id,
            pool_vm_size,
            pool_vm_count,
            blob_service_client)

        print("Start time: ", _START_TIME)
        print("Delete time: ", _END_TIME)

        recent_job = common.helpers.wait_for_job_under_job_schedule(
            batch_client,
            job_schedule_id,
            datetime.timedelta(minutes=5))

        common.helpers.wait_for_tasks_to_complete(
            batch_client,
            recent_job,
            datetime.timedelta(minutes=25))

        tasks = batch_client.task.list(recent_job)
        task_ids = [task.id for task in tasks]

        common.helpers.print_task_output(
            batch_client,
            recent_job,
            task_ids)

        common.helpers.wait_for_job_schedule_to_complete(
            batch_client,
            job_schedule_id,
            _END_TIME + datetime.timedelta(minutes=10))

    except batchmodels.BatchErrorException as err:
        for value in err.error.values:
            print("BatchErrorException: ", value)

    finally:
        if should_delete_job_schedule:
            print("Deleting job schedule: ", job_schedule_id)
            batch_client.job_schedule.delete(job_schedule_id)
        if should_delete_container:
            try:
                blob_service_client.delete_container(_CONTAINER_NAME)
            except ResourceNotFoundError:
                pass


if __name__ == '__main__':
    global_cfg = ConfigParser()
    global_cfg.read(common.helpers.SAMPLES_CONFIG_FILE_NAME)

    sample_cfg = ConfigParser()
    sample_cfg.read(
        os.path.splitext(os.path.basename(__file__))[0] + '.cfg')

    execute_sample(global_cfg, sample_cfg)
