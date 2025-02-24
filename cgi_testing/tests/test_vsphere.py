import pytest
from unittest.mock import patch, MagicMock, call
from pyVmomi import vim

from cgi_testing.classes.vsphere import Vsphere


@pytest.fixture(scope="function")
def mock_si():
    mock = MagicMock()
    mock.content = MagicMock()
    mock.content.viewManager = MagicMock()
    mock.content.rootFolder = MagicMock()

    return mock


@pytest.fixture(scope="function")
def mock_vm():
    return MagicMock()


@pytest.fixture(scope="function")
def vsphere_instance():
    return Vsphere(
        host="test-host",
        user="test-user",
        pwd="test-pwd",
    )


class TestVsphereConnections:
    def test_init(self):
        vsphere = Vsphere("test-host", "test-user", "test-pwd")

        assert vsphere.host == "test-host"
        assert vsphere.user == "test-user"
        assert vsphere.pwd == "test-pwd"

    @patch("cgi_testing.classes.vsphere.SmartConnect")
    def test_connection(self, mock_smart_connect):
        mock_smart_connect.return_value = MagicMock()

        result = Vsphere.Connect("test-host", "test-user", "test-pwd")

        mock_smart_connect.assert_called_once_with(
            host="test-host",
            user="test-user",
            pwd="test-pwd",
            disableSslCertValidation=True,
        )

        assert result is not False

    @patch("cgi_testing.classes.vsphere.SmartConnect")
    def test_connection_failure(self, mock_smart_connect):
        mock_smart_connect.side_effect = Exception("Failed to connect")

        result = Vsphere.Connect("test-host", "test-user", "test-pwd")

        assert result is False


class TestVsphereGetObject:
    def test_get_object_no_name(self, mock_si):
        mock_vm_object_1 = MagicMock()
        mock_vm_object_2 = MagicMock()

        mock_vm_object_1.name = "vm1"
        mock_vm_object_2.name = "vm2"

        mock_container = MagicMock(view=[mock_vm_object_1, mock_vm_object_2])
        mock_si.content.viewManager.CreateContainerView.return_value = mock_container

        result = Vsphere.GetObject(mock_si, vim.VirtualMachine)

        assert result == [mock_vm_object_1, mock_vm_object_2]

    def test_get_object(self, mock_si):
        mock_vm_object_1 = MagicMock()
        mock_vm_object_2 = MagicMock()

        mock_vm_object_1.name = "vm1"
        mock_vm_object_2.name = "vm2"

        mock_container = MagicMock()
        mock_container.view = [mock_vm_object_1, mock_vm_object_2]

        mock_si.content.viewManager.CreateContainerView.return_value = mock_container

        result = Vsphere.GetObject(mock_si, vim.VirtualMachine, "vm1")

        assert result == mock_vm_object_1

    def test_get_object_error(self, mock_si):
        mock_si.content.viewManager.CreateContainerView.side_effect = Exception(
            "Unable to create container view"
        )

        result = Vsphere.GetObject(mock_si, vim.Datastore, "vm1")

        assert result is False


class TestVsphereUploadToDatastore:
    def test_convert_si_cookie_to_dict(self):
        test_cookie = "VMware_CSRF_TOKEN=41234123; Path=/sdk; Secure; HttpOnly"
        expected_result = {"VMware_CSRF_TOKEN": " 41234123; $Path=/sdk"}

        result = Vsphere.ConvertSICookieToDict(test_cookie)

        assert result == expected_result

    @pytest.mark.parametrize(
        "cookie",
        [
            "",  # Empty string
            "invalid_cookie",  # No equals sign
            "name=",  # No value
            "=value",  # No name
            None,  # None value
        ],
    )
    def test_convert_cookie_error_handling(self, cookie):
        with pytest.raises(Exception):
            Vsphere.ConvertSICookieToDict(cookie)

    @patch("cgi_testing.classes.vsphere.Vsphere.GetObject")
    @patch("cgi_testing.classes.vsphere.requests.put")
    def test_upload_to_datastore(self, mock_put, mock_get_object, mock_si):
        mock_si._stub.cookie = "VMware_CSRF_TOKEN=41234123; Path=/sdk"

        mock_datastore = MagicMock()
        mock_datastore.info.name = "test-datastore"
        mock_datastore.parent.parent.parent.name = "test-datacenter"
        mock_get_object.return_value = mock_datastore

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_put.return_value = mock_response

        test_file = b"test file content"

        result = Vsphere.UploadFileToDatastore(
            si=mock_si,
            cloud_url="test-cloud.com",
            datastore_name="test-datastore",
            file=test_file,
            upload_folder="test-folder",
            upload_file="test.iso",
        )

        assert result is True
        mock_put.assert_called_once_with(
            url="https://test-cloud.com:443/folder/test-folder/test.iso",
            params={"dsName": "test-datastore", "dcPath": "test-datacenter"},
            data=test_file,
            headers={"Content-Type": "application/octet-stream"},
            cookies={"VMware_CSRF_TOKEN": " 41234123; $Path=/sdk"},
            verify=False,
        )

    @patch("cgi_testing.classes.vsphere.Vsphere.GetObject")
    @patch("cgi_testing.classes.vsphere.requests.put")
    def test_upload_to_datastore(self, mock_put, mock_get_object, mock_si):
        mock_si._stub.cookie = "VMware_CSRF_TOKEN=41234123; Path=/sdk"

        mock_datastore = MagicMock()
        mock_datastore.info.name = "test-datastore"
        mock_datastore.parent.parent.parent.name = "test-datacenter"
        mock_get_object.return_value = mock_datastore

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_put.return_value = mock_response

        test_file = b"test file content"

        result = Vsphere.UploadFileToDatastore(
            si=mock_si,
            cloud_url="test-cloud.com",
            datastore_name="test-datastore",
            file=test_file,
            upload_folder="test-folder",
            upload_file="test.iso",
        )

        assert result is False


class TestVsphereVirtualCDSpec:
    # Can be parametrized but with negative outcome of additional branching
    def test_get_virtual_cd_spec_with_iso(self):
        mock_cdrom = MagicMock()
        mock_cdrom.controllerKey = 200
        mock_cdrom.key = 3000

        iso_path = "[datastore1] folder/test.iso"

        result = Vsphere.GetVirtualCDSpec(mock_cdrom, iso_path)

        assert isinstance(result, vim.vm.device.VirtualDeviceSpec)
        assert result.operation == vim.vm.device.VirtualDeviceSpec.Operation.edit
        assert result.device.controllerKey == 200
        assert result.device.key == 3000
        assert result.device.connectable.allowGuestControl is True
        assert result.device.connectable.connected is True
        assert result.device.connectable.startConnected is True
        assert isinstance(
            result.device.backing, vim.vm.device.VirtualCdrom.IsoBackingInfo
        )
        assert result.device.backing.fileName == iso_path

    def test_get_virtual_cd_spec_without_iso(self):
        mock_cdrom = MagicMock()
        mock_cdrom.controllerKey = 200
        mock_cdrom.key = 3000

        result = Vsphere.GetVirtualCDSpec(mock_cdrom)

        assert isinstance(result, vim.vm.device.VirtualDeviceSpec)
        assert result.operation == vim.vm.device.VirtualDeviceSpec.Operation.edit
        assert result.device.controllerKey == 200
        assert result.device.key == 3000
        assert result.device.connectable.allowGuestControl is True
        assert result.device.connectable.connected is False
        assert result.device.connectable.startConnected is False
        assert isinstance(
            result.device.backing,
            vim.vm.device.VirtualCdrom.RemotePassthroughBackingInfo,
        )


class TestVsphereAttachISO:
    @patch("cgi_testing.classes.vsphere.Vsphere.GetObject")
    @patch("cgi_testing.classes.vsphere.Vsphere._ExecuteTask")
    def test_attach_iso_success(
        self, mock_execute_task, mock_get_object, mock_si, mock_vm
    ):
        mock_vm.ReconfigVM_Task = MagicMock(return_value="fake_task")

        mock_cdrom = MagicMock(spec=vim.vm.device.VirtualCdrom)
        mock_cdrom.deviceInfo = MagicMock()
        mock_cdrom.deviceInfo.label = "CD/DVD drive 1"
        mock_cdrom.controllerKey = 200
        mock_cdrom.key = 3000

        mock_vm.config.hardware.device = [mock_cdrom]
        mock_get_object.return_value = mock_vm

        mock_execute_task.return_value = True

        result = Vsphere.AttachISOToVirtualMachine(
            si=mock_si,
            vm_name="test-vm",
            cdrom_number=1,
            datastore_name="test-datastore",
            iso_path="folder/test.iso",
        )

        assert result is True


class TestVspherePowerOperations:
    @patch("cgi_testing.classes.vsphere.Vsphere.GetObject")
    @patch("cgi_testing.classes.vsphere.Vsphere._ChangeVMPowerState")
    def test_vm_power_on_success(
        self, mock_change_power_state, mock_get_object, mock_si, mock_vm
    ):
        mock_vm.PowerOn = MagicMock()
        mock_get_object.return_value = mock_vm
        mock_change_power_state.return_value = True

        result = Vsphere.PowerOnVM(mock_si, "test-vm")

        assert result is True
        mock_get_object.assert_called_once_with(mock_si, vim.VirtualMachine, "test-vm")
        mock_change_power_state.assert_called_once_with(
            mock_vm, vim.VirtualMachinePowerState.poweredOn, mock_vm.PowerOn
        )

    @patch("cgi_testing.classes.vsphere.Vsphere.GetObject")
    def test_vm_power_on_not_found(self, mock_get_object, mock_si):
        mock_get_object.return_value = False

        result = Vsphere.PowerOnVM(mock_si, "test-vm-1")

        assert result is False

    @patch("cgi_testing.classes.vsphere.Vsphere.GetObject")
    @patch("cgi_testing.classes.vsphere.Vsphere._ChangeVMPowerState")
    def test_power_on_vm_failure(
        self, mock_change_power_state, mock_get_object, mock_vm
    ):
        mock_vm.PowerOn = MagicMock()
        mock_get_object.return_value = mock_vm
        mock_change_power_state.return_value = False

        result = Vsphere.PowerOnVM(MagicMock(), "test-vm")

        assert result is False

    @patch("cgi_testing.classes.vsphere.Vsphere.GetObject")
    @patch("cgi_testing.classes.vsphere.Vsphere._ChangeVMPowerState")
    def test_vm_power_off_success(
        self, mock_change_power_state, mock_get_object, mock_si, mock_vm
    ):
        mock_vm.PowerOff = MagicMock()
        mock_get_object.return_value = mock_vm
        mock_change_power_state.return_value = True

        result = Vsphere.PowerOffVM(mock_si, "test-vm")

        assert result is True
        mock_get_object.assert_called_once_with(mock_si, vim.VirtualMachine, "test-vm")
        mock_change_power_state.assert_called_once_with(
            mock_vm, vim.VirtualMachinePowerState.poweredOff, mock_vm.PowerOff
        )

    @patch("cgi_testing.classes.vsphere.Vsphere.GetObject")
    def test_vm_power_off_not_found(self, mock_get_object, mock_si):
        mock_get_object.return_value = False

        result = Vsphere.PowerOffVM(mock_si, "test-vm-1")

        assert result is False

    @patch("cgi_testing.classes.vsphere.Vsphere.GetObject")
    @patch("cgi_testing.classes.vsphere.Vsphere._ChangeVMPowerState")
    def test_power_off_vm_failure(
        self, mock_change_power_state, mock_get_object, mock_vm
    ):
        mock_vm.PowerOff = MagicMock()
        mock_get_object.return_value = mock_vm
        mock_change_power_state.return_value = False

        result = Vsphere.PowerOffVM(MagicMock(), "test-vm")

        assert result is False

    @patch("cgi_testing.classes.vsphere.Vsphere.GetObject")
    @patch("cgi_testing.classes.vsphere.Vsphere._ExecuteTask")
    def test_reboot_vm_guest_success(
        self, mock_execute_task, mock_get_object, mock_si, mock_vm
    ):
        mock_vm.RebootGuest = MagicMock()
        mock_vm.RebootGuest.return_value = "fake_task"
        mock_get_object.return_value = mock_vm
        mock_execute_task.return_value = True

        result = Vsphere.RebootVM(MagicMock(), "test-vm")

        assert result is True
        mock_get_object.assert_called_once()
        mock_execute_task.assert_called_once_with(mock_vm.RebootGuest)

    @patch("cgi_testing.classes.vsphere.Vsphere.GetObject")
    @patch("cgi_testing.classes.vsphere.Vsphere._ExecuteTask")
    def test_reboot_vm_reset_success(
        self, mock_execute_task, mock_get_object, mock_si, mock_vm
    ):
        mock_vm.RebootGuest = MagicMock()
        mock_vm.RebootGuest.side_effect = Exception("Unable to reboot")

        mock_vm.ResetGuest = MagicMock()
        mock_vm.ResetGuest.return_value = "fake_task"

        mock_get_object.return_value = mock_vm
        mock_execute_task.side_effect = [Exception("RebootGuest failed"), True]

        result = Vsphere.RebootVM(MagicMock(), "test-vm")

        assert result is True
        mock_get_object.assert_called_once()

        assert mock_execute_task.call_count == 2
        mock_execute_task.assert_has_calls(
            [call(mock_vm.RebootGuest), call(mock_vm.ResetVM_Task)]
        )

    def test_change_vm_power_same_state(self, mock_vm):
        mock_vm.runtime.powerState = vim.VirtualMachinePowerState.poweredOff

        result = Vsphere._ChangeVMPowerState(
            mock_vm, vim.VirtualMachinePowerState.poweredOff, mock_vm.PowerOff
        )

        assert result is True

    @patch("cgi_testing.classes.vsphere.Vsphere._ExecuteTask")
    def test_change_vm_power_different_state(self, mock_execute_task, mock_vm):
        mock_vm.runtime.powerState = vim.VirtualMachinePowerState.poweredOff
        mock_execute_task.return_value = True

        result = Vsphere._ChangeVMPowerState(
            mock_vm, vim.VirtualMachinePowerState.poweredOn, mock_vm.PowerOn
        )

        assert result is True
        mock_execute_task.assert_called_once()


class TestVsphereDeleteVm:
    @patch("cgi_testing.classes.vsphere.Vsphere.GetObject")
    @patch("cgi_testing.classes.vsphere.Vsphere._ExecuteTask")
    def test_delete_vm_powered_off(
        self, mock_execute_task, mock_get_object, mock_vm, mock_si
    ):
        mock_vm.runtime = MagicMock()
        mock_vm.runtime.powerState = vim.VirtualMachinePowerState.poweredOff

        mock_get_object.return_value = mock_vm

        mock_execute_task.return_value = True

        result = Vsphere.DeleteVm(mock_si, mock_vm)

        assert result is True
        mock_execute_task.assert_called_once()
        mock_get_object.assert_called_once()

    @patch("cgi_testing.classes.vsphere.Vsphere.GetObject")
    @patch("cgi_testing.classes.vsphere.Vsphere.PowerOffVM")
    @patch("cgi_testing.classes.vsphere.Vsphere._ExecuteTask")
    def test_delete_vm_powered_on(
        self, mock_execute_task, mock_power_off_vm, mock_get_object, mock_vm, mock_si
    ):
        mock_vm.runtime = MagicMock()
        mock_vm.runtime.powerState = vim.VirtualMachinePowerState.poweredOn

        mock_get_object.return_value = mock_vm

        mock_execute_task.return_value = True
        mock_power_off_vm.return_value = True

        result = Vsphere.DeleteVm(mock_si, mock_vm)

        assert result is True
        mock_execute_task.assert_called_once()
        mock_get_object.assert_called_once()
        mock_power_off_vm.assert_called_once_with(mock_si, mock_vm)


class TestVsphereExecuteTask:
    @patch("cgi_testing.classes.vsphere.WaitForTask")
    def test_execute_task_success(self, mock_wait_task):
        mock_task = MagicMock()
        mock_task_method = MagicMock()

        mock_task_method.return_value = mock_task
        mock_wait_task.return_value = "success"

        result = Vsphere._ExecuteTask(mock_task_method, arg1="test", arg2="test2")

        assert result is True
        mock_task_method.assert_called_once_with(arg1="test", arg2="test2")
        mock_wait_task.assert_called_once_with(mock_task)

    @patch("cgi_testing.classes.vsphere.WaitForTask")
    def test_execute_task_failure(self, mock_wait_task):
        mock_task = MagicMock()
        mock_task_method = MagicMock()

        mock_task_method.return_value = mock_task
        mock_wait_task.return_value = "failure"

        result = Vsphere._ExecuteTask(mock_task_method, arg1="test", arg2="test2")

        assert result is False
        mock_task_method.assert_called_once_with(arg1="test", arg2="test2")
        mock_wait_task.assert_called_once_with(mock_task)

    @patch("cgi_testing.classes.vsphere.WaitForTask")
    def test_execute_task_with_args(self, mock_wait_task):
        mock_task = MagicMock()
        mock_task_method = MagicMock(return_value=mock_task)
        mock_wait_task.return_value = "success"

        test_args = ("arg1", "arg2")
        test_kwargs = {"kwarg1": "value1", "kwarg2": "value2"}

        result = Vsphere._ExecuteTask(mock_task_method, *test_args, **test_kwargs)

        assert result is True
        mock_task_method.assert_called_once_with(*test_args, **test_kwargs)
        mock_wait_task.assert_called_once_with(mock_task)


class TestVsphereSnapshots:
    @patch("cgi_testing.classes.vsphere.Vsphere.GetObject")
    @patch("cgi_testing.classes.vsphere.Vsphere._ExecuteTask")
    def test_make_snapshot_vm_success(
        self, mock_execute_task, mock_get_object, mock_vm, mock_si
    ):
        mock_get_object.return_value = mock_vm
        mock_execute_task.return_value = True

        result = Vsphere.SnapshotVM(
            mock_si, "test-vm", "test-snapshot", "test-description"
        )

        assert result is True
        mock_get_object.assert_called_once()
        mock_execute_task.assert_called_once_with(
            mock_vm.CreateSnapshot,
            name="test-snapshot",
            description="test-description",
            memory=True,
            quiesce=False,
        )

    @patch("cgi_testing.classes.vsphere.Vsphere.GetObject")
    @patch("cgi_testing.classes.vsphere.Vsphere._ExecuteTask")
    def test_make_snapshot_vm_failure(
        self, mock_execute_task, mock_get_object, mock_vm, mock_si
    ):
        mock_get_object.return_value = mock_vm
        mock_execute_task.return_value = False

        result = Vsphere.SnapshotVM(
            mock_si, "test-vm", "test-snapshot", "test-description"
        )

        assert result is False
        mock_get_object.assert_called_once()
        mock_execute_task.assert_called_once_with(
            mock_vm.CreateSnapshot,
            name="test-snapshot",
            description="test-description",
            memory=True,
            quiesce=False,
        )

    @patch("cgi_testing.classes.vsphere.Vsphere.GetObject")
    def test_make_snapshot_vm_not_found(self, mock_get_object, mock_vm, mock_si):
        mock_get_object.return_value = False

        result = Vsphere.SnapshotVM(
            mock_si, "test-vm", "test-snapshot", "test-description"
        )

        assert result is False
        mock_get_object.assert_called_once()

    @patch("cgi_testing.classes.vsphere.Vsphere.GetObject")
    @patch("cgi_testing.classes.vsphere.Vsphere._ExecuteTask")
    def test_restore_snapshot(
        self, mock_execute_task, mock_get_object, mock_vm, mock_si
    ):
        snapshot1 = MagicMock()
        snapshot1.name = "snapshot1"

        snapshot2 = MagicMock()
        snapshot2.name = "snapshot2"

        mock_vm.snapshot = MagicMock()
        mock_vm.snapshot.rootSnapshotList = []

        mock_get_object.return_value = mock_vm
        mock_execute_task.return_value = True

        result = Vsphere.SnapshotVM(
            mock_si, "test-vm", "test-snapshot", "test-description"
        )

        assert result is True
        mock_get_object.assert_called_once()
