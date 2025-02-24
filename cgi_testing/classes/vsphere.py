import requests
from pyVim.task import WaitForTask
from pyVim.connect import SmartConnect, Disconnect

from pyVmomi import vim


class Vsphere:

	def __init__(self, host, user, pwd):

		self.host = host
		self.user = user
		self.pwd = pwd

	def __enter__(self):

		self.si = Vsphere.Connect(self.host, self.user, self.pwd)

		return self.si

	def __exit__(self, *args):

		return Vsphere.Disconnect(self.si)

	def Connect(host, user, pwd):

		try:
			return SmartConnect(
				host=host,
				user=user,
				pwd=pwd,
				disableSslCertValidation=True
			)

		except Exception as e:
			return False

	def Disconnect(si):

		try:
			return Disconnect(si)

		except Exception as e:

			return False

	def GetObject(si, vimtype, name=None):

		try:
			container = si.content.viewManager.CreateContainerView(
				si.content.rootFolder,
				[vimtype],
				True
			)

		except Exception as e:
			return False

		if not name:
			return container.view

		for x in container.view:
			if x.name.lower() == name.lower():
				return x

		return False

	def ConvertSICookieToDict(si_cookie):

		cookie_name = si_cookie.split('=', 1)[0]
		cookie_value = si_cookie.split('=', 1)[1].split(';', 1)[0]
		cookie_path = si_cookie.split('=', 1)[1].split(';', 1)[1].split(';', 1)[0].lstrip()
		cookie_text = f' {cookie_value}; ${cookie_path}'

		return {cookie_name: cookie_text}

	def UploadFileToDatastore(si, cloud_url, datastore_name, file, upload_folder, upload_file):

		datastore = Vsphere.GetObject(si, vim.Datastore, datastore_name)
		if not datastore:
			return False

		datacenter = datastore.parent.parent.parent

		response = requests.put(
			url=f'https://{cloud_url}:443/folder/{upload_folder}/{upload_file}',
			params={
				'dsName': datastore.info.name,
				'dcPath': datacenter.name
			},
			data=file,
			headers={'Content-Type': 'application/octet-stream'},
			cookies=Vsphere.ConvertSICookieToDict(si._stub.cookie),
			verify=False
		)

		return response.status_code in [200, 201]

	def GetVirtualCDSpec(virtual_cdrom_device, iso_path=None):

		virtual_cd_spec = vim.vm.device.VirtualDeviceSpec(
			operation=vim.vm.device.VirtualDeviceSpec.Operation.edit,
			device=vim.vm.device.VirtualCdrom(
				controllerKey=virtual_cdrom_device.controllerKey,
				key=virtual_cdrom_device.key,
				connectable=vim.vm.device.VirtualDevice.ConnectInfo(
					allowGuestControl=True,
					connected=bool(iso_path),
					startConnected=bool(iso_path)
				)
			)
		)
		if iso_path:
			virtual_cd_spec.device.backing = vim.vm.device.VirtualCdrom.IsoBackingInfo(fileName=iso_path)
		else:
			virtual_cd_spec.device.backing = vim.vm.device.VirtualCdrom.RemotePassthroughBackingInfo()

		return virtual_cd_spec

	def AttachISOToVirtualMachine(si, vm_name, cdrom_number, datastore_name, iso_path):

		cdrom_label = f'CD/DVD drive {cdrom_number}'
		virtual_cdrom_device = None
		vm_obj = Vsphere.GetObject(si, vim.VirtualMachine, vm_name)

		for dev in vm_obj.config.hardware.device:
			if isinstance(dev, vim.vm.device.VirtualCdrom) and dev.deviceInfo.label == cdrom_label:
				virtual_cdrom_device = dev

		virtual_cd_spec = Vsphere.GetVirtualCDSpec(virtual_cdrom_device, f'[{datastore_name}] {iso_path}')

		dev_changes = [virtual_cd_spec]
		spec = vim.vm.ConfigSpec()
		spec.deviceChange = dev_changes

		return Vsphere._ExecuteTask(vm_obj.ReconfigVM_Task, spec=spec)

	def PowerOnVM(si, vm_name):
		vm = Vsphere.GetObject(si, vim.VirtualMachine, vm_name)
		return Vsphere._ChangeVMPowerState(vm, vim.VirtualMachinePowerState.poweredOn, vm.PowerOn) if vm else False

	def PowerOffVM(si, vm_name):
		vm = Vsphere.GetObject(si, vim.VirtualMachine, vm_name)
		return Vsphere._ChangeVMPowerState(vm, vim.VirtualMachinePowerState.poweredOff, vm.PowerOff) if vm else False

	def RebootVM(si, vm_name):
		vm = Vsphere.GetObject(si, vim.VirtualMachine, vm_name)

		if not vm:
			return False

		try:
			result = Vsphere._ExecuteTask(vm.RebootGuest)
		except:
			result = Vsphere._ExecuteTask(vm.ResetVM_Task)

		return result


	def DeleteVm(si, vm_name):
		vm = Vsphere.GetObject(si, vim.VirtualMachine, vm_name)

		if vm.runtime.powerState == vim.VirtualMachinePowerState.poweredOn:
			if not Vsphere.PowerOffVM(si, vm_name):
				return False

		return Vsphere._ExecuteTask(vm.Destroy_Task)

	def _ChangeVMPowerState(vm, target_state, power_method):
		if vm.runtime.powerState == target_state:
			return True
		return Vsphere._ExecuteTask(power_method)


	def _ExecuteTask(task_method, *args, **kwargs):
		task = task_method(*args, **kwargs)
		completion_status = WaitForTask(task)
		return completion_status == 'success'


	def SnapshotVM(si, vm_name, snapshot_name, description):
		vm = Vsphere.GetObject(si, vim.VirtualMachine, vm_name)
		if not vm:
			return False

		return Vsphere._ExecuteTask(
			vm.CreateSnapshot,
			name=snapshot_name,
			description=description,
			memory=True,
			quiesce=False
		)

	def RestoreVMFromSnapshot(si, vm_name, snapshot_name):
		vm = Vsphere.GetObject(si, vim.VirtualMachine, vm_name)
		if not vm:
			return False

		snapshot = None
		for snap in vm.snapshot.rootSnapshotList:
			if snap.name == snapshot_name:
				snapshot = snap.snapshot
				break

		if not snapshot:
			return False

		return Vsphere._ExecuteTask(snapshot.RevertToSnapshot_Task)

	def DeleteVMSnapshot(si, vm_name, snapshot_name):
		vm = Vsphere.GetObject(si, vim.VirtualMachine, vm_name)
		if not vm:
			return False

		snapshot = None
		for snap in vm.snapshot.rootSnapshotList:
			if snap.name == snapshot_name:
				snapshot = snap.snapshot
				break

		if not snapshot:
			return False

		return Vsphere._ExecuteTask(snapshot.RemoveSnapshot_Task, removeChildren=False)

	def ListVMSnapshots(si, vm_name):
		vm = Vsphere.GetObject(si, vim.VirtualMachine, vm_name)
		if not vm:
			return False

		snapshots = []

		if vm.snapshot:
			for snapshot in vm.snapshot.rootSnapshotList:
				snapshots.append({
					"Name": snapshot.name,
					"Date": snapshot.createTime.strftime("%Y-%m-%d %H:%M:%S")
				})

		return snapshots

	def GetVMs(si):

		vms = Vsphere.GetObject(si, vim.VirtualMachine)
		return [vm.name for vm in vms]

	def GetVmMeta(si, vm_name):
		vm = Vsphere.GetObject(si, vim.VirtualMachine, vm_name)
		if not vm:
			return False

		return Vsphere._VmMeta(si, vm)
	
	def GetVmMetasByName(si, vm_names):
		if not vm_names:
			return []

		vms = Vsphere.GetObject(si, vim.VirtualMachine)
		vm_metas = []
		for vm_name in vm_names:
			vm = next((vm for vm in vms if vm.name == vm_name), None)
			if not vm: # If the VM is not found, return False
				return False
			meta = Vsphere._VmMeta(si, vm)
			vm_metas.append(meta)
		return vm_metas

	def ResizeVM(si, vm_name, new_cpu_count=None, new_ram_gb=None):
		vm = Vsphere.GetObject(si, vim.VirtualMachine, vm_name)
		if not vm:
			return False

		spec = vim.vm.ConfigSpec()
		downsizing = False

		original_power_state = vm.runtime.powerState

		if new_cpu_count is not None:
			current_cpu = vm.config.hardware.numCPU
			spec.numCPUs = int(new_cpu_count)
			downsizing = int(new_cpu_count) < current_cpu

		if new_ram_gb is not None:
			current_ram = vm.config.hardware.memoryMB / 1024  # Convert to GB
			new_ram_mb = int(new_ram_gb) * 1024  # Convert GB to MB
			spec.memoryMB = new_ram_mb
			downsizing = downsizing or int(new_ram_gb) < current_ram

		try:
			if downsizing and vm.runtime.powerState == vim.VirtualMachinePowerState.poweredOn:
				if not Vsphere.PowerOffVM(si, vm_name):
					raise Exception("Failed to power off VM for downsizing")

			try:
				task = vm.Reconfigure(spec)
				completion_status = WaitForTask(task)
			except vim.fault.CpuHotPlugNotSupported:
				if vm.runtime.powerState == vim.VirtualMachinePowerState.poweredOn:
					if not Vsphere.PowerOffVM(si, vm_name):
						raise Exception("Failed to power off VM for resizing")
					task = vm.Reconfigure(spec)
					completion_status = WaitForTask(task)
				else:
					raise

			if completion_status != 'success':
				raise Exception("Failed to resize VM")

			if vm.runtime.powerState == vim.VirtualMachinePowerState.poweredOff and original_power_state == vim.VirtualMachinePowerState.poweredOn:
				if not Vsphere.PowerOnVM(si, vm_name):
					raise Exception("Failed to power on VM after resizing")

			return True

		except Exception as e:
			return False

	def RenameVM(si, vm_name, new_vm_name):
		vm = Vsphere.GetObject(si, vim.VirtualMachine, vm_name)
		if not vm:
			return False

		return Vsphere._ExecuteTask(vm.Rename_Task, new_vm_name.upper())


	def SetVMCustomAttributes(
			si,
			vm_name,
			bl_name,
			cdm,
			category,
			maintenance_window,
			patch_week
	):

		vm = Vsphere.GetObject(si, vim.VirtualMachine, vm_name)

		attributes = {
			'BLName': bl_name.lower() + '.' + bl_name.lower() if bl_name else None,
			'CDM': cdm,
			'Category': category,
			'Maint.Window': maintenance_window,
			'PatchWeek': patch_week
		}
		try:
			for key, value in attributes.items():
				if value is not None:
					vm.SetCustomValue(key=key, value=value)

			completion_status = 'success'

		except Exception:
			completion_status = 'failed'

		return True if completion_status == 'success' else False

	def GetVMCustomAttributes(si, vm_name):

		vm = Vsphere.GetObject(si, vim.VirtualMachine, vm_name)
		custom_fields = si.content.customFieldsManager.field
		field_map = {field.key: field.name for field in custom_fields}
		vm_custom_values = {field_map[custom_value.key]: custom_value.value for custom_value in vm.customValue}

		return vm_custom_values

	def ListVMHardDisks(si, vm_name):
		vm = Vsphere.GetObject(si, vim.VirtualMachine, vm_name)
		if not vm:
			return None

		hard_disks = []
		for device in vm.config.hardware.device:
			if isinstance(device, vim.vm.device.VirtualDisk):
				disk_info = {
					'Label': device.deviceInfo.label,
					'CapacityGB': device.capacityInKB / (1024 * 1024),
					'UnitNumber': device.unitNumber,
					'BusNumber': device.controllerKey
				}
				hard_disks.append(disk_info)

		return hard_disks

	def AddDiskToVM(si, vm_name, disk_size_gb):

		vm = Vsphere.GetObject(si, vim.VirtualMachine, vm_name)
		if not vm:
			return False

		disk_spec = Vsphere._CreateDiskSpec(vm, disk_size_gb)
		spec = vim.vm.ConfigSpec(deviceChange=[disk_spec])

		return Vsphere._ExecuteTask(vm.ReconfigVM_Task, spec=spec)

	def RemoveDiskFromVM(si, vm_name, disk_label):
		vm = Vsphere.GetObject(si, vim.VirtualMachine, vm_name)
		if not vm:
			return False

		disk_to_remove = None
		for device in vm.config.hardware.device:
			if isinstance(device, vim.vm.device.VirtualDisk) and device.deviceInfo.label == disk_label:
				disk_to_remove = device
				break

		if not disk_to_remove:
			return False

		disk_spec = vim.vm.device.VirtualDeviceSpec()
		disk_spec.operation = vim.vm.device.VirtualDeviceSpec.Operation.remove
		disk_spec.device = disk_to_remove
		disk_spec.fileOperation = vim.vm.device.VirtualDeviceSpec.FileOperation.destroy

		spec = vim.vm.ConfigSpec(deviceChange=[disk_spec])

		return Vsphere._ExecuteTask(vm.ReconfigVM_Task, spec=spec)

	def _CreateDiskSpec(vm, disk_size_gb):

		disk_spec = vim.vm.device.VirtualDeviceSpec()
		disk_spec.operation = vim.vm.device.VirtualDeviceSpec.Operation.add
		disk_spec.fileOperation = vim.vm.device.VirtualDeviceSpec.FileOperation.create

		disk_backing = vim.vm.device.VirtualDisk.FlatVer2BackingInfo()
		disk_backing.diskMode = 'persistent'
		disk_backing.thinProvisioned = False

		new_disk = vim.vm.device.VirtualDisk()
		new_disk.backing = disk_backing
		new_disk.capacityInKB = disk_size_gb * 1024 * 1024
		new_disk.key = -1
		new_disk.unitNumber = len([dev for dev in vm.config.hardware.device if isinstance(dev, vim.vm.device.VirtualDisk)]) + 1
		new_disk.controllerKey = next(dev.key for dev in vm.config.hardware.device if isinstance(dev, vim.vm.device.VirtualSCSIController))

		disk_spec.device = new_disk

		return disk_spec

	def ExtendVMHardDisk(si, vm_name, disk_name, disk_size_gb):
		vm = Vsphere.GetObject(si, vim.VirtualMachine, vm_name)
		vdisk = Vsphere.FindVirtualDisk(vm, disk_name)

		if not vdisk:
			raise ValueError(f'Failed to find virtual disk "{disk_name}" for VM "{vm_name}"')

		vdisk.capacityInKB = disk_size_gb * 1024 * 1024
		spec = Vsphere.CreateVirtualDiskConfigSpec(vdisk)

		return Vsphere._ExecuteTask(vm.Reconfigure, spec)

	def FindVirtualDisk(vm, disk_name):
		for device in vm.config.hardware.device:
			if isinstance(device, vim.vm.device.VirtualDisk) and device.deviceInfo.label == disk_name:
				return device
		return None

	def CreateVirtualDiskConfigSpec(vdisk):
		return vim.vm.ConfigSpec(
			deviceChange=[
				vim.vm.device.VirtualDeviceSpec(
					device=vdisk,
					operation=vim.vm.device.VirtualDeviceSpec.Operation.edit,
				)
			]
		)

	def GetClusters(si):

		datacenter = Vsphere.GetObject(si, vim.Datacenter)[0]

		return [childEntity.name for childEntity in datacenter.hostFolder.childEntity if isinstance(childEntity, vim.ClusterComputeResource)]

	def GetClusterInfo(si, name):
		cluster = Vsphere.GetObject(si, vim.ClusterComputeResource, name)

		return {
			"TotalClusterCPU": cluster.summary.usageSummary.totalCpuCapacityMhz,
			"TotalClusterMemory": cluster.summary.usageSummary.totalMemCapacityMB,
			"CPUInUse": cluster.summary.usageSummary.cpuDemandMhz,
			"MemoryInUse": cluster.summary.usageSummary.memDemandMB,
			"CPUReserved": cluster.summary.usageSummary.cpuReservationMhz,
			"MemoryReserved": cluster.summary.usageSummary.memReservationMB,
		}

	def CreatePortGroup(si, name, dvs_name, vlan_id, num_ports=8):

		dvs = Vsphere.GetObject(si, vim.DistributedVirtualSwitch, dvs_name)

		dv_pg_spec = vim.dvs.DistributedVirtualPortgroup.ConfigSpec(
			name=name,
			numPorts=num_ports,
			type=vim.dvs.DistributedVirtualPortgroup.PortgroupType.earlyBinding,
			defaultPortConfig=vim.dvs.VmwareDistributedVirtualSwitch.VmwarePortConfigPolicy(
				securityPolicy=vim.dvs.VmwareDistributedVirtualSwitch.SecurityPolicy(
					allowPromiscuous=vim.BoolPolicy(value=False),
					forgedTransmits=vim.BoolPolicy(value=True),
					macChanges=vim.BoolPolicy(value=True)
				),
				vlan=vim.dvs.VmwareDistributedVirtualSwitch.VlanIdSpec(vlanId=vlan_id)
			)
		)

		return Vsphere._ExecuteTask(dvs.AddDVPortgroup_Task, [dv_pg_spec])

	def SearchPort(dvs, portgroup_key):

		criteria = vim.dvs.PortCriteria(connected=False, inside=True, portgroupKey=portgroup_key)
		ports = dvs.FetchDVPorts(criteria=criteria)

		return ports[0].key if ports else None

	def GetPortByPortgroup(si, dv_pg_name):

		portgroup = Vsphere.GetObject(si, vim.dvs.DistributedVirtualPortgroup, dv_pg_name)
		dvs = portgroup.config.distributedVirtualSwitch
		port_key = Vsphere.SearchPort(dvs, portgroup.key)
		criteria = vim.dvs.PortCriteria(portKey=port_key)
		ports = dvs.FetchDVPorts(criteria=criteria)

		return ports[0] if ports else None

	def AttachPortgroupToVM(si, vm_name, dv_pg_name, vm_port):

		vm = Vsphere.GetObject(si, vim.VirtualMachine, vm_name)
		port = Vsphere.GetPortByPortgroup(si, dv_pg_name)
		nic_label = f'Network adapter {vm_port}'
		virtual_nic_device = None

		for dev in vm.config.hardware.device:
			if isinstance(dev, vim.vm.device.VirtualEthernetCard) and dev.deviceInfo.label == nic_label:
				virtual_nic_device = dev

		virtual_nic_spec = vim.vm.device.VirtualDeviceSpec(
			operation=vim.vm.device.VirtualDeviceSpec.Operation.edit,
			device=type(virtual_nic_device)(
				key=virtual_nic_device.key,
				macAddress=virtual_nic_device.macAddress,
				wakeOnLanEnabled=virtual_nic_device.wakeOnLanEnabled,
				connectable=virtual_nic_device.connectable,
				backing=vim.vm.device.VirtualEthernetCard.DistributedVirtualPortBackingInfo(
					port=vim.dvs.PortConnection(
						portgroupKey=port.portgroupKey,
						switchUuid=port.dvsUuid,
						portKey=port.key
					)
				)
			)
		)

		dev_changes = [virtual_nic_spec]
		spec = vim.vm.ConfigSpec()
		spec.deviceChange = dev_changes

		return Vsphere._ExecuteTask(vm.ReconfigVM_Task, spec=vim.vm.ConfigSpec(deviceChange=[virtual_nic_spec]))

	def FindFreeIDEController(vm):

		for dev in vm.config.hardware.device:
			if isinstance(dev, vim.vm.device.VirtualIDEController) and len(dev.device) < 2:
				return dev

		return None

	def GetNewCDRomSpec(controller_key, backing):

		connectable = vim.vm.device.VirtualDevice.ConnectInfo()
		connectable.allowGuestControl = True
		connectable.startConnected = True
		connectable.connected = True

		cdrom = vim.vm.device.VirtualCdrom()
		cdrom.controllerKey = controller_key
		cdrom.key = -1
		cdrom.connectable = connectable
		cdrom.backing = backing

		return cdrom

	def AttachCDRomToVM(si, vm_name, datastore, iso_path):
		vm = Vsphere.GetObject(si, vim.VirtualMachine, vm_name)
		ide_controller = Vsphere.FindFreeIDEController(vm)
		cdrom_operation = vim.vm.device.VirtualDeviceSpec.Operation
		device_spec = vim.vm.device.VirtualDeviceSpec()

		backing = vim.vm.device.VirtualCdrom.IsoBackingInfo(fileName=f'[{datastore}] {iso_path}')
		cdrom = Vsphere.GetNewCDRomSpec(ide_controller.key, backing)

		cdrom.connectable.connected = True
		cdrom.connectable.startConnected = True

		device_spec.operation = cdrom_operation.add
		device_spec.device = cdrom
		config_spec = vim.vm.ConfigSpec(deviceChange=[device_spec])
		WaitForTask(vm.Reconfigure(config_spec))

		return True






