# Machine Fails to Boot: Boot Logs, Serial Console, and Rescue Disk

A virtual machine that fails to boot can take applications offline, lock operations teams out of SSH/RDP access, or prevent new workloads from launching. Typical symptoms include a VM stuck in the Starting state, failing health checks, a console screen frozen at the bootloader, kernel panic, root filesystem mount errors, or an OS that boots while services remain unavailable.

To troubleshoot systematically, determine whether the failure lies in the provider's control plane, virtual hardware configuration, boot chain, operating system, storage, or startup services. **Boot logs** show which steps the system executed; the **serial console** provides an observation channel and sometimes interactive access when networking is down; and a **rescue disk** lets you attach the OS disk to a helper machine for offline inspection and repair.

In **CLOUD_CORE_SERVICES_COMPUTE**, these techniques help recover virtual machines safely and reduce downtime. The procedure must protect data, preserve diagnostic evidence, verify the exact disk before editing, and re-verify boot capability after recovery.

## 1. Identify what exact failure the machine is experiencing

"Fails to boot" can describe several distinct states. Before altering configuration or repairing a disk, distinguish whether the VM failed to provision, failed during the boot process, booted the guest OS with broken networking, or simply has an unready application.

### 1.1. Distinguish control plane vs. guest OS

| Observation | Possible layer at fault | First check to perform |
| --- | --- | --- |
| API/console cannot create VM, reporting quota or capacity | Control plane, quota, zone, machine type | Operations/events, quotas, availability, and policies |
| VM stuck in provisioning/starting for a long time | Control plane or host | Operation status, provider health, boot diagnostics |
| VM is running but SSH/RDP cannot connect | Guest OS, network, firewall, or access service | Health checks, serial console, boot logs, and network path |
| Console stops at firmware or bootloader | Boot mode, boot order, disk, or bootloader | Screenshot/serial output, UEFI/BIOS settings, and boot disk |
| Kernel panic or initramfs error | Kernel, driver, initramfs, or root filesystem | Kernel logs, recent patches, and storage mapping |
| OS allows login but application is not running | systemd/services, application config, or dependencies | Journal, application logs, and health endpoint |

A `running` state in the control plane usually only indicates that the hypervisor powered on the VM. It does not prove that the guest OS finished booting, that networking is ready, or that the application is serving traffic.

### 1.2. Record context before investigating

Collect the following details:

- VM ID, region/zone, instance type, and failure start time.
- Image ID, OS version, CPU architecture, and boot mode if known.
- Boot disk ID, related data disks, and encryption configuration.
- Most recent changes: kernel updates, drivers, fstab, bootloader, disk resize, instance type change, security policy, or startup scripts.
- Health check status, events, operations, and provider alerts.
- Errors observed from the console, serial output, screenshots, or monitoring.
- Last reboot time and whether the VM ever booted successfully after that change.

The timeline is critical. If the machine stopped booting right after installing a new kernel, that change is a hypothesis to test. However, do not conclude causation from temporal correlation alone.

## 2. Boot chain of a virtual machine

Understanding the boot stages helps map error messages to the component that needs inspection.

~~~mermaid
flowchart TD
    A["Provider creates VM and attaches boot disk"] --> B["BIOS/UEFI firmware"]
    B --> C["Boot device and bootloader"]
    C --> D["Load kernel and initramfs/initrd"]
    D --> E["Kernel initializes drivers and devices"]
    E --> F["Locate and mount root filesystem"]
    F --> G["Init system: systemd or equivalent"]
    G --> H["Network, cloud agent, and background services"]
    H --> I["Application and health checks"]
~~~

The stages can be understood as follows:

1. **Provisioning:** the platform allocates the VM, connects NICs and the boot disk, and applies virtual firmware settings.
2. **Firmware:** BIOS or UEFI locates a bootable device according to the boot order.
3. **Bootloader:** GRUB or the corresponding bootloader reads its configuration and selects a kernel.
4. **Kernel/initramfs:** the kernel loads alongside initramfs to initialize drivers and prepare required devices.
5. **Root filesystem:** the OS locates the right root device, verifies the filesystem, and mounts root.
6. **Init system:** systemd or an equivalent init system starts targets and background services.
7. **Cloud initialization:** cloud-init or a guest agent applies metadata, networking, and initial configuration.
8. **Workload:** the application starts, health checks pass, and the machine is ready to serve.

Early-stage failures usually prevent the VM from reaching a login prompt. Late-stage failures can leave the VM booted yet still failing health checks.

### 2.1. BIOS/UEFI and boot mode

BIOS and UEFI are two different boot firmware types. An image built for UEFI may not boot properly if the VM is configured for legacy BIOS, or vice versa. Boot mode, Secure Boot, and partition table type must match the image.

When changing machine types or migrating images, check:

- Does the VM support the boot mode required by the image?
- Does the boot disk contain an EFI System Partition if UEFI is used?
- Does the firmware see the correct boot device?
- Is Secure Boot rejecting an unsigned bootloader or kernel?
- Does the boot order prioritize the wrong disk or network boot?

Do not arbitrarily toggle BIOS/UEFI mode on a machine holding data. Doing so can prevent firmware from recognizing the existing bootloader.

### 2.2. Bootloader, kernel, and initramfs

The bootloader is responsible for selecting the kernel and passing boot parameters. If the GRUB configuration is corrupted, an entry points to a missing kernel, or the bootloader is not in the expected location, the machine can halt before the kernel starts.

Initramfs holds the minimal drivers and tools the kernel needs to access devices before mounting the root filesystem. If storage drivers, encryption modules, LVM, or UUID settings are missing or wrong, the kernel may fail to locate the root device.

Messages such as **VFS: Unable to mount root fs**, **ALERT! UUID does not exist**, or **dracut-initqueue timeout** typically point to errors in accessing the root filesystem. Cross-check UUIDs, initramfs, drivers, and disk mappings before making changes.

## 3. Reading boot logs and boot diagnostics

Boot logs are an essential source of evidence when the machine lacks networking or cannot be logged into. Depending on the platform, logs may be surfaced via boot diagnostics, console screenshots, serial output, instance screenshots, or VM management service logs.

### 3.1. Common log sources

| Source | Visible contents | Limitations |
| --- | --- | --- |
| Provider operations/events | Provisioning, disk attach, host, quota, or policy errors | Does not necessarily include logs inside the guest |
| Boot diagnostics screenshot | Firmware, bootloader, kernel, or login screen | A point-in-time capture |
| Serial console output | Boot, kernel, init system messages, and certain errors | Requires console enabled/supported; output may be truncated or not fully retained |
| OS journal/system logs | Service, kernel, and filesystem errors after OS boot | May be inaccessible if the root disk fails to mount |
| Application logs | Application and dependency errors | Useful only after the application or logging agent starts |

Collect logs from the provider before rebooting again. A fresh boot can overwrite earlier output in the console buffer or alter state, making the failure harder to reproduce.

### 3.2. Finding errors in logs

Do not look only at the final line. Boot logs may contain many unrelated warnings; the first error that halts boot progression is usually more informative than subsequent timeout errors.

Common indicators:

| Message or symptom | Hypothesis to check |
| --- | --- |
| No bootable device | Boot disk unattached, wrong boot order, firmware mode mismatch, or corrupted bootloader |
| grub rescue prompt | GRUB cannot find the required partition/configuration |
| Kernel panic | Kernel, driver, module, boot parameter, or filesystem issue |
| VFS: Unable to mount root fs | Root device, UUID, initramfs, storage driver, or filesystem |
| dracut-initqueue timeout | Root device did not appear; LVM/RAID/encryption not ready |
| Dependency failed for /data | Dependent mount failed, wrong UUID, or volume not attached |
| Entering emergency mode | Filesystem check, fstab, mount, or systemd dependency |
| cloud-init failed | Metadata/network, user-data, or initialization script |
| Login prompt appears but SSH fails | Network, firewall, sshd, or route |

Exact messages vary by distribution and version. Use the full log to confirm a hypothesis before applying a fix.

### 3.3. Collecting logs once the OS can boot

If you can log in via SSH or a rescue environment, common Linux commands include:

~~~bash
# Current boot and previous boot
sudo journalctl -b
sudo journalctl -b -1

# Errors at level err or higher in the current boot
sudo journalctl -b -p err

# Kernel messages
sudo dmesg -T

# Failed services
systemctl --failed

# cloud-init status if installed
cloud-init status --long
~~~

The **journalctl -b -1** command only returns data if the journal is stored persistently and the previous boot was retained. If the journal is volatile only, logs can disappear after a reboot.

On systems using traditional log files, inspect **/var/log/syslog**, **/var/log/messages**, **/var/log/boot.log**, or distribution-specific logs. Do not assume every path exists on every OS.

## 4. Serial console: observing when networking is not ready

The serial console provides a virtual console channel analogous to a physical machine's serial port. It can display boot messages and allow interaction with the guest OS even when the NIC, IP, routes, or SSH/RDP are not working.

### 4.1. When should you use the serial console?

The serial console is useful when:

- SSH/RDP cannot connect even though the VM is provisioned.
- Firewalls or network configuration block management access.
- The kernel boots partway and then stalls.
- You need to inspect GRUB, emergency mode, or the login prompt.
- You need to fix boot or network configuration from the console.

The serial console does not replace boot diagnostics. If the host has not started the VM or firmware cannot see the boot disk, the console may not provide enough information to fix the problem; in that case, check operations/events and disk attachments.

### 4.2. Prerequisites for use

Serial console availability depends on the provider, VM type, region, image, and guest configuration. It may require:

- Enabling boot diagnostics or serial console in the VM configuration.
- Granting dedicated IAM/RBAC permissions to read or connect to the console.
- Configuring the guest OS to send console output to the serial port.
- A valid console account and password if interactive login is needed.
- Network/control-plane access to the provider's console service.

Do not grant broad serial console access to all users. The console can allow privileged shell access, so enforce auditing, MFA, or administrative access controls required by your organization.

### 4.3. Linux: configuring console output

On Linux, the kernel can be configured to send messages to the serial console using kernel parameters such as **console=ttyS0** or the platform's corresponding serial device. Device names and baud rates depend on the virtual machine.

Example kernel command line configuration:

~~~text
console=tty0 console=ttyS0,115200n8
~~~

Parameter ordering can affect which device receives primary output. Do not copy this configuration without checking your VM's serial device and provider documentation.

On systemd-based systems, you can enable getty on the appropriate serial TTY if interactive login is required:

~~~bash
sudo systemctl enable serial-getty@ttyS0.service
sudo systemctl start serial-getty@ttyS0.service
~~~

Only enable a login prompt on the console when proper access controls are in place. Never use weak passwords or leave administrative consoles open to unauthorized users.

### 4.4. Windows: serial console and recovery

Windows VMs may support a serial console or boot diagnostics depending on the platform, though interactivity depends on boot configuration, SAC/EMS, Windows version, and provider services. If no useful output is available, use boot diagnostics screenshots, Windows Recovery Environment (WinRE), Safe Mode, or the provider's supported rescue workflow.

Do not apply Linux commands or assume Windows shares the same boot chain. For Windows, inspect BCD, the EFI System Partition, boot files, storage drivers, and volume status with the appropriate recovery tools.

## 5. Diagnosing by boot stage

### 5.1. VM does not finish provisioning

If the VM does not transition to the running state:

1. Inspect the operation ID and events for the create/start attempt.
2. Check quotas for CPUs, VM count, disks, and IP addresses.
3. Verify zone, instance type, and capacity.
4. Check policies, encryption keys, and boot disk access permissions.
5. Verify that the boot disk is attached to the right VM and in a ready state.
6. Check provider health or zonal incidents if multiple VMs are affected together.

Do not repair filesystems when the provider has not yet provisioned the VM or attached the disk. Control-plane failures must be resolved at that layer first.

### 5.2. Firmware cannot find a boot device

If you see No bootable device or firmware cannot locate a boot drive:

- Verify the exact volume ID and correct boot disk.
- Check whether the disk is in the required zone/region.
- Check boot order and device mapping.
- Verify that the BIOS/UEFI firmware mode matches the image.
- Check that the boot/EFI System Partition still exists.
- Check whether the disk was detached, restored from the wrong snapshot, or replaced with a volume lacking a bootloader.

If the disk is properly attached yet the bootloader is corrupted, consider a rescue disk to inspect partitions and boot files.

### 5.3. Bootloader appears but fails to load the kernel

Check:

- Does the GRUB entry point to an existing kernel and initramfs?
- Does the root UUID in kernel parameters match the volume?
- Was the GRUB configuration file edited incorrectly?
- Is the new kernel compatible with the machine type, architecture, and drivers?
- Is Secure Boot rejecting the bootloader/kernel?

If the failure started right after a kernel update, try selecting an older kernel from GRUB if its entry and package still exist. After booting successfully, inspect the new kernel's packages, modules, and initramfs before restoring it as the boot default.

### 5.4. Kernel cannot mount the root filesystem

Common causes:

- Boot disk is not attached or device path changed.
- Incorrect UUID in GRUB, initramfs, or /etc/fstab.
- Storage driver missing from initramfs.
- LVM, RAID, or disk encryption not activated in the right order.
- Corrupted filesystem or volume I/O errors.

Cross-check lsblk, blkid, lvm pvs/vgs/lvs, kernel logs, and mount configuration. If the root filesystem is corrupted, stop write operations and evaluate snapshots/backups before running repair tools.

### 5.5. OS enters emergency mode

Systemd can drop the machine into emergency mode when a critical filesystem fails to mount or a required dependency fails. Messages typically identify the failing mount unit or device UUID.

If a secondary volume such as /data no longer exists, inspect /etc/fstab. Non-essential mounts can use an appropriate option such as nofail, whereas mounts holding application data must be handled explicitly so the application does not write into an empty directory on the root disk.

Do not delete an fstab line just to make the machine boot quickly without verifying whether the application depends on data at that mount point.

### 5.6. OS finishes booting but health checks fail

When the login prompt appears yet the application is unready, pivot to checking:

- NICs, DHCP/static IP, routes, DNS, and firewalls.
- Cloud-init, guest agent, and startup scripts.
- systemd units, dependencies, and service timeouts.
- Full disk, exhausted inodes, or wrong mount points.
- Secrets, IAM identity, and database/queue connectivity.
- Whether the application binds to the right interface/port.
- Whether health checks target an appropriate endpoint with a reasonable timeout.

A rescue disk is unnecessary if the guest OS is already running and can be investigated via console/SSH. Use offline methods only when internal fixes are impossible or safe disk inspection is required.

## 6. What is a rescue disk?

A rescue disk is a technique that uses a separate helper environment to access the disk of a broken VM. For cloud VMs, the typical workflow is:

1. Stop the failing VM.
2. Detach the boot disk from that VM if the platform permits.
3. Attach the boot disk to a rescue VM in the same zone or within provider constraints.
4. Mount the filesystem to inspect logs and configuration.
5. Apply evidence-based fixes, then cleanly unmount and detach.
6. Reattach the boot disk to the original VM and attempt to boot.

A rescue disk can be an ISO/recovery image, a rescue disk, or a helper VM running a compatible OS. Exact steps depend on the provider; not every platform allows detaching boot disks or attaching disks across all machine types.

### 6.1. When should you use a rescue disk?

Consider a rescue disk when:

- The guest OS does not boot far enough to allow login.
- The root filesystem can be mounted offline to repair configuration.
- You need to read logs or inspect fstab, GRUB, initramfs, or system files.
- You need to copy data to a safe location before attempting repairs.
- You need to run a filesystem check while the volume is unmounted.

Do not use a rescue disk just because SSH is blocked if the serial console still lets you fix networking or firewalls. Every detach/attach cycle can alter device mappings and introduce risk if the wrong volume is modified.

## 7. Safe rescue disk procedure

Before making repairs, preserve the ability to return to the initial state.

### 7.1. Preparation

1. Identify the exact VM and boot disk ID.
2. Check encryption, KMS keys, attach permissions, and zone restrictions.
3. Take a snapshot or backup per policy before editing.
4. Record boot mode, disk mapping, and VM state settings.
5. Announce downtime and stop workloads according to procedure.
6. Choose a helper VM with a compatible OS/architecture and sufficient disk access permissions.

A snapshot is a useful recovery point but does not replace a verified backup. For critical data, verify restore capability before performing risky repairs.

### 7.2. Stop the VM and attach the disk to a helper

Conceptual flow:

~~~text
Failing VM
  -> Stop/Deallocate per provider guidelines
  -> Snapshot boot disk
  -> Detach boot disk
  -> Attach disk to rescue VM
  -> Verify volume ID and device serial
~~~

Some providers require the VM to be stopped/deallocated before detaching the OS disk. Some disk types have attachment limits or do not support sharing. Always wait for control-plane operations to finish before operating inside the guest OS.

### 7.3. Identify the correct disk on a Linux helper

After attaching, do not assume the rescue disk is always /dev/sdb. Device names can vary by instance type, NVMe usage, and attach order.

~~~bash
lsblk -o NAME,SIZE,TYPE,FSTYPE,LABEL,UUID,MOUNTPOINTS
sudo blkid
sudo dmesg | tail -n 80
~~~

Match capacity, partitions, filesystem UUIDs, and serial/volume IDs against the recorded boot disk. If you cannot positively identify the device, stop; never run fsck, mount read-write, or run mkfs on an unverified disk.

### 7.4. Mount the filesystem safely

If you only need to inspect logs and configuration, prefer mounting read-only. Example for a standard Linux filesystem:

~~~bash
sudo mkdir -p /mnt/rescue
sudo mount -o ro /dev/ROOT_PARTITION /mnt/rescue
~~~

Note: for some journaled filesystems, read-only mode may still attempt journal replay on mount. If you must strictly preserve the source state, work on a snapshot/clone and use the filesystem-appropriate no-recovery option (for example, ext4 or XFS each have specific options). No-recovery mode can leave the filesystem inconsistent and must not be used for continued production operation; its purpose is controlled offline inspection.

If the filesystem uses LVM, discover and activate volume groups properly before mounting logical volumes. Example:

~~~bash
sudo pvs
sudo vgs
sudo lvs
sudo vgchange -ay
~~~

Volume group names may collide with a VG on the helper VM. Check carefully to avoid activating the wrong volume or causing name conflicts. Do not blindly mount all volume groups if the helper runs its own LVM workloads.

Filesystems such as XFS may require special mount options when a volume is cloned or shares a UUID with another filesystem. Do not apply UUID-changing or log-replay flags without understanding their impact. When writes are required, perform them on a snapshot/clone or after securing an appropriate backup.

## 8. Fixing Linux issues from a rescue environment

### 8.1. Inspect logs and configuration

After mounting the root filesystem at /mnt/rescue, you can inspect:

~~~bash
sudo less /mnt/rescue/var/log/syslog
sudo less /mnt/rescue/var/log/messages
sudo less /mnt/rescue/var/log/boot.log
sudo less /mnt/rescue/etc/fstab
sudo ls -la /mnt/rescue/boot
~~~

Log paths depend on the distribution and journald configuration. If persistent journaling is enabled, data may reside under /var/log/journal inside the mounted filesystem.

Check common failure points:

- Do UUIDs in /etc/fstab appear in blkid output?
- Do mount points match the right filesystems and devices?
- Are there invalid mount options or filesystem types?
- Do the kernel and initramfs referenced by GRUB exist?
- Does network config reference an old NIC name after a machine-type change?
- Does a startup script contain an infinite loop or blocking wait?

### 8.2. Fix fstab

If you confirm an fstab UUID is stale, cross-check against the volume's actual UUID and update the exact entry. Never replace UUIDs by guessing.

Example configuration to review:

~~~fstab
UUID=ROOT_UUID  /      ext4  defaults  0  1
UUID=DATA_UUID  /data  xfs   defaults,nofail  0  2
~~~

This is an example only. Root mounts are typically handled by initramfs/boot configuration before systemd reads fstab; do not add nofail to the root filesystem. For mandatory data mounts, ensure applications depend on the mount unit rather than silently writing to an empty /data directory on the root disk.

After editing, you can check syntax and UUIDs in the rescue environment, but note that commands like mount -a will mount into the helper environment rather than the broken machine's root filesystem. Run checks only inside a properly prepared chroot and mount namespace.

### 8.3. Check and repair the filesystem

If there are signs of filesystem corruption, first verify the partition is unmounted and no process is using it. Running filesystem check tools on a mounted filesystem can corrupt data.

Example for ext filesystems:

~~~bash
# Run only when the filesystem is unmounted and the exact device is verified
sudo e2fsck -f -n /dev/ROOT_PARTITION
~~~

The -n option checks without writing repairs. If repairs are needed, review the output, verify backups/snapshots, and use an appropriate repair mode per organizational procedure. Do not use this command for XFS.

For XFS, the check tool is xfs_repair, and the filesystem must be unmounted. Some situations require journal replay before repair, and xfs_repair -L can discard journal metadata. Do not run log-destroying options as a first step. Back up or clone the volume and consult experienced personnel when corruption is severe.

### 8.4. Rebuild initramfs or GRUB

If logs show initramfs is missing drivers or bootloader config is broken, you may need to rebuild initramfs or reinstall GRUB from the rescue environment. Exact steps depend on the distribution, firmware mode, and partitioning layout.

Before proceeding:

- Identify the root filesystem, boot partition, and EFI System Partition.
- Determine whether the VM uses UEFI or BIOS.
- Mount all required filesystems into the rescue tree.
- Bind-mount /dev, /proc, /sys, and /run if required by the chroot workflow.
- Ensure necessary kernel/GRUB packages and matching repositories are available.

Example Linux chroot preparation scaffold:

~~~bash
sudo mount /dev/ROOT_PARTITION /mnt/rescue
sudo mount /dev/BOOT_PARTITION /mnt/rescue/boot
sudo mount /dev/EFI_PARTITION /mnt/rescue/boot/efi
sudo mount --bind /dev /mnt/rescue/dev
sudo mount --bind /proc /mnt/rescue/proc
sudo mount --bind /sys /mnt/rescue/sys
sudo mount --bind /run /mnt/rescue/run
sudo chroot /mnt/rescue
~~~

Not every system has separate /boot or EFI partitions; mount only filesystems that actually exist. Commands to rebuild initramfs/GRUB differ between Debian/Ubuntu and RHEL-family distributions and must align with BIOS/UEFI. Follow distribution and provider documentation for your exact image before reinstalling the bootloader.

### 8.5. Unmount and return the disk to the original VM

After repairing:

1. Save changes and verify configuration files.
2. Exit chroot if you entered one.
3. Unmount bind mounts in reverse order.
4. Unmount boot, EFI, and root filesystems.
5. Verify no mounts or processes still hold the disk.
6. Detach the disk from the helper VM and wait for the operation to complete.
7. Reattach the disk to the original VM with its prior device mapping and boot mode.
8. Start the VM and observe boot diagnostics/serial console.

Do not detach while a filesystem remains mounted or unflushed I/O is pending. If repairs fail, keep the snapshot/clone and record the state before trying another approach.

## 9. Fixing Windows issues with a recovery environment

Windows VMs typically use Windows Boot Manager and Boot Configuration Data (BCD). If the machine fails to boot, identify whether the fault lies in boot files, the EFI System Partition, storage drivers, updates, or the filesystem.

Supporting tools and sources:

- Boot diagnostics screenshots and serial output if supported by the provider.
- Windows Recovery Environment (WinRE) or a recovery ISO.
- Safe Mode or Startup Repair when accessible.
- Disk Management, DiskPart, and filesystem check utilities.
- Logs under Windows folders such as Windows\System32\winevt\Logs if readable offline.

Conceptual workflow:

1. Snapshot the boot disk and stop the VM.
2. Attach the disk to a Windows helper VM or boot from recovery media per provider instructions.
3. Identify the exact disk and volume letters inside the recovery environment; drive letters may differ from normal boot.
4. Inspect the filesystem and logs before modifying anything.
5. Verify the EFI System Partition, boot files, and BCD.
6. Check storage/network drivers and recent updates.
7. Repair using Startup Repair or appropriate tools, then cleanly detach the disk.
8. Reattach the disk and attempt to boot, verifying event logs and services.

Commands such as chkdsk, sfc, DISM, or bcdboot have distinct scopes and preconditions. Run them only against the right volume and in the right offline/online mode. Never format the EFI partition or rewrite BCD by guesswork.

If the failure started immediately after a Windows Update or driver update, WinRE can be used to uninstall quality/feature updates or roll back drivers if supported. First ensure a snapshot exists and check compatibility with the image/provider.

## 10. Common causes and remediation paths

| Cause | Indicators | Remediation path |
| --- | --- | --- |
| Boot disk unattached or wrong mapping | Firmware reports no bootable device | Verify disk ID, attachment, boot order, and zone |
| BIOS/UEFI mismatch | Firmware cannot find bootloader | Restore boot mode compatible with the image |
| Corrupted GRUB/BCD | Halts at bootloader or boot manager | Use rescue/recovery to inspect and repair boot files |
| Faulty kernel or driver | Kernel panic, device errors | Boot an older kernel, inspect drivers, and rebuild initramfs |
| Incorrect UUID/fstab | Root mount failure or emergency mode | Cross-check UUIDs and fix entries with evidence |
| Filesystem corruption | I/O errors, journal/check failures | Snapshot, unmount, and check with the filesystem-specific tool |
| Disk full | Service or boot step fails | Check space/inodes, clean up carefully, or expand disk |
| Cloud-init/startup script error | OS boots but provisioning fails | Read cloud-init logs, metadata, and scripts |
| Misconfigured network | VM runs but SSH/RDP is unreachable | Use serial console or rescue to fix NIC, routes, and firewall |
| Permission/SELinux error | Service cannot read files or is denied | Check ownership, mode, labels, and audit logs |
| KMS/key permission | Boot disk cannot decrypt/attach | Check key state, IAM/RBAC, and policies |

Multiple faults can occur together. For example, changing VM machine type can rename the NIC so networking fails to come up, while cloud-init waits on metadata and health checks time out. Read logs in boot order rather than changing all configurations at once.

## 11. Preventing boot incidents

To reduce the risk of VMs failing to boot after changes:

- Use images tested against the target machine type, architecture, and firmware mode.
- Retain at least one known-good kernel entry when applying kernel updates, if supported by the distribution.
- Validate initramfs, GRUB/BCD, and boot files in image build pipelines.
- Use UUIDs or persistent identifiers for mounts; validate fstab before rebooting.
- Avoid relying on device names that can shift after changing instance types.
- Take policy-compliant snapshots/backups before modifying boot disks or filesystems.
- Roll out changes via canary VM groups before fleet-wide deployment.
- Enable boot diagnostics and retain serial output per policy.
- Maintain console access and tested rescue runbooks.
- Monitor disk health, capacity, I/O errors, and provider events.
- Verify KMS keys, IAM, and attach permissions when changing identities or accounts.

## 12. Runbook for handling an unbootable VM

A concise runbook helps on-call teams act in a consistent order:

1. **Confirm scope:** one VM or multiple VMs in the same zone/image group.
2. **Check control plane:** operations, provider health, quotas, host, and disk status.
3. **Collect evidence:** boot screenshots, serial output, events, timestamps, and recent changes.
4. **Identify boot stage:** firmware, bootloader, kernel, root mount, init system, or application.
5. **Select access channel:** SSH/RDP if OS is running; serial console if network is down; rescue disk if offline repair is needed.
6. **Protect data:** snapshot/backup and verify disk ID before any write operation.
7. **Fix one evidence-backed cause:** avoid changing multiple settings at once.
8. **Return disk to the right VM:** unmount, detach, reattach with the proper mapping, and boot.
9. **Verify:** boot completion, networking, agent, filesystems, services, and health checks.
10. **Document:** root cause, changes made, recovery time, and preventive actions.

### 12.1. Quick decision tree

~~~mermaid
flowchart TD
    A["VM fails to boot"] --> B{"Control plane reports running?"}
    B -- "No" --> C["Check operations, quota, host, zone, disk, and KMS"]
    B -- "Yes" --> D{"Is there boot output?"}
    D -- "No" --> E["Check boot diagnostics, firmware, and serial support"]
    D -- "Yes" --> F{"Reached login prompt?"}
    F -- "Yes" --> G["Check network, agent, services, and health checks"]
    F -- "No" --> H{"Failure at bootloader/kernel/root mount?"}
    H -- "Yes" --> I["Snapshot then use rescue/recovery environment"]
    H -- "Unclear" --> J["Read full logs and identify boot stage"]
    I --> K["Repair, unmount, reattach, and test boot"]
    K --> L["Verify OS, network, and application"]
    C --> M["Restart once control plane is stable"]
    E --> J
    J --> H
~~~

## 13. Example: Linux VM fails to boot after editing fstab

A Linux VM runs a data-processing service. Operations recently added a data volume and edited /etc/fstab to mount it at /data. After rebooting, the VM enters emergency mode and health checks fail.

Investigation flow:

1. Confirm the control plane reports the VM as provisioned and boot diagnostics show the kernel ran.
2. Open the serial console and read systemd messages indicating the /data mount unit failed.
3. Verify the data volume is still attached and has the expected ID.
4. If the guest cannot reach a shell, snapshot the boot disk and use a helper VM to mount the root filesystem.
5. Read /etc/fstab and discover the UUID in the /data entry does not match the data volume's actual UUID.
6. Verify volume data still exists; update the entry with the correct UUID and keep mount options suited to the data's role.
7. Check mount config, cleanly unmount, and detach the boot disk from the helper.
8. Reattach the boot disk to the original VM, start it, and observe serial output.
9. Verify /data mounts properly, the application has access permissions, and health checks pass.
10. Update the runbook to validate UUIDs and mount dependencies before future reboots.

If /data holds mandatory application data, configure the service to depend on the mount unit. Adding nofail alone may let the OS finish booting, yet also allow the application to run against an empty /data directory on the root filesystem, writing data in the wrong place.

## 14. Common mistakes

- Looking only at the provider's running state and assuming the guest OS is ready.
- Rebooting repeatedly before saving boot logs and serial output.
- Confusing network/SSH errors with boot filesystem failures.
- Switching BIOS/UEFI mode without checking the image and partition layout.
- Running mkfs or filesystem repair on the wrong disk.
- Mounting a boot disk read-write without taking a snapshot or assessing filesystem state.
- Detaching a disk while a filesystem is still mounted or I/O is unflushed.
- Relying on fixed /dev/sdX device paths even though mappings can change.
- Running fsck on a mounted filesystem.
- Using journal-destroying repair flags without a recovery copy.
- Deleting or editing fstab entries to bypass emergency mode without checking application dependencies.
- Attaching a boot disk to a helper in a different zone or without KMS key permissions.
- Failing to verify the application and health checks after the VM boots successfully.

## 15. Operational principles

1. **Separate control plane from guest:** determine whether the VM was not provisioned or the guest OS failed to boot.
2. **Collect logs early:** save operations/events, boot diagnostics, and serial output before rebooting again.
3. **Isolate the boot stage:** firmware, bootloader, kernel, root filesystem, init system, or application.
4. **Use serial console appropriately:** observe or access when networking is down, under controlled permissions.
5. **Snapshot before repair:** preserve recoverability and evidence.
6. **Identify disks by ID/UUID:** never rely on mutable device names.
7. **Read-only first:** inspect logs and configuration before writing; run filesystem repairs only under proper conditions.
8. **Clean detach:** unmount and flush before detaching a volume from a helper.
9. **Post-recovery testing:** verify boot, networking, cloud agent, mounts, services, and health checks.
10. **Update images/runbooks:** feed root causes and preventive measures back into pipelines to avoid recurrence.

Boot logs reveal where the machine stopped; the serial console helps observe when networking is down; and a rescue disk provides an offline repair environment when the guest OS cannot boot on its own. Combining these three tools at the right stage—alongside snapshots and careful disk verification—enables controlled VM recovery while protecting data throughout the incident.
