# Boot Diagnostics, Serial Console, and Troubleshooting Boot Failures

An Azure virtual machine can report **Running** yet still fail to accept SSH or RDP connections. The cause might simply be a Network Security Group (NSG) blocking the port, or the operating system could be stuck at the bootloader, unable to locate the system partition, hitting a kernel update error, running out of disk space, or failing to start networking services. Blindly opening more ports or rebooting repeatedly prolongs outages and can destroy evidence needed for root-cause analysis.

**Boot Diagnostics** and **Azure Serial Console** are two essential tools for inspecting and interacting with a virtual machine when normal administrative paths fail. Boot Diagnostics captures a **VM screenshot** and **serial port log output**; Serial Console provides a text-based command interface over the VM's serial port without requiring SSH or RDP to work. Combining them with VM status data, snapshots/backups, and offline repair workflows helps you pinpoint the real cause instead of guessing.

This lesson belongs to the **Azure Virtual Machines** chapter of the **CLOUD_PROVIDERS_AZURE** module. The module explores Azure from subscriptions, resource groups, and Microsoft Entra ID to virtual networking, compute, storage, and data, alongside deployment, monitoring, protection, and cost control. Here, the focus is **diagnosing and recovering boot failures on Windows or Linux Azure VMs** within organization-approved permissions and data protection boundaries.

After this lesson, you will be able to:

- Distinguish **Azure control-plane** issues, **guest OS boot** failures, and **SSH/RDP connectivity** issues.
- Enable and read Boot Diagnostics using managed storage or a custom storage account.
- Understand prerequisites, permissions, and limitations of Azure Serial Console.
- Use Serial Console to inspect login prompts, Linux serial terminals, or the Windows Special Administration Console (SAC).
- Recognize common failures such as kernel panics, GRUB/initramfs errors, filesystem/mount issues, BCD errors, and `INACCESSIBLE_BOOT_DEVICE`.
- Design recovery workflows when the OS cannot reach an administrative session: snapshots, Azure VM repair, and repair VMs.
- Build risk-tiered troubleshooting runbooks, preserve evidence, validate fixes, and avoid unnecessary costs.

## 1. Identifying the Exact Failure Layer

A VM spans multiple operational layers. “Unreachable” alone does not tell you which layer broke.

~~~text
Azure control plane
  VM resource, provisioning, power state, quota, host
             |
             v
Virtual hardware
  CPU, memory, virtual NIC, OS disk, firmware
             |
             v
Guest boot process
  Bootloader -> kernel -> initramfs/driver -> OS services
             |
             v
Guest networking and identity
  NIC config, firewall, SSH/RDP, user credentials
             |
             v
Application
  Web/API/database/service health
~~~

| Symptom | Possible cause group | First tools to check |
|---|---|---|
| VM resource reports provisioning failed | Deployment, extension, resource config, or platform error | Activity Log, deployment operations, instance view |
| VM Stopped/Deallocated | Machine is not running, due to manual action or policy | VM Overview, Activity Log |
| VM Running yet Boot Diagnostics shows GRUB/emergency mode | Bootloader, filesystem, or guest OS config | Boot Diagnostics, Serial Console |
| VM Running, screenshot shows login screen, SSH times out | NSG, UDR, firewall, IP/DNS, `sshd`, routing | Network Watcher, Serial Console, guest logs |
| Windows shows Recovery screen / BSOD | BCD, driver, filesystem, update, or boot device | Boot screenshot, SAC if available, repair workflow |
| Can sign into VM yet website returns 502 | App/backend health, port listener, dependent service | Application logs, systemd/Windows services, load balancer logs |

**Power state = Running** usually only indicates compute resources are active—**it does not prove the OS booted successfully**. Conversely, if an extension reports a provisioning error, the OS might still be running; verify with independent evidence.

### Three Initial Questions

1. Is the VM **Running** or **Stopped/Deallocated**? Are there resource-management errors?
2. At which stage does Boot Diagnostics show the latest screenshot/log?
3. If the OS appears booted, is this a **network/authentication** issue or an **application** issue?

Before answering these three questions, **do not swap the OS disk, reset all network rules, or format filesystems**.

## 2. What Is Boot Diagnostics?

**Azure Boot Diagnostics** collects boot diagnostic artifacts and VM display state, especially valuable when SSH/RDP is down.

Two primary evidence types:

| Data | Typical contents | What it is used for |
|---|---|---|
| **Screenshot** | Snapshot of the VM's virtual display | Seeing bootloaders, Windows recovery, login prompts, boot errors, or blank screens |
| **Serial log** | Guest OS output sent to the serial port during boot/runtime | Finding kernel messages, service init failures, filesystem, mount, and boot steps |

The screenshot is a **point-in-time capture**, not a continuous video of the entire boot. The serial log only contains messages the OS/bootloader actually wrote to the serial port; if a custom image lacks serial console configuration, logs may be incomplete or empty even during failures.

Boot Diagnostics **does not require the Azure VM Agent to be healthy inside the guest OS** to capture screenshots and serial output. That makes it invaluable when a VM fails before reaching agent startup or extension execution.

### How Boot Diagnostics Differs from Azure Monitor

| Service / tool | Observation layer | When to use |
|---|---|---|
| Boot Diagnostics | VM screenshots and serial output | Inspect boot progress and screen state when SSH/RDP fails |
| Serial Console | Interactive text session over serial port | Repair guest OS config when normal connectivity is broken |
| Azure Monitor / VM Insights | Metrics, logs, guest telemetry when configured | CPU/memory/disk trends, app health, and alerts |
| Azure Activity Log | Management-plane actions | See who restarted, resized, changed disks/networks, or updated VMs |
| Network Watcher | Network paths, next hop, security rules, reachability | When guest runs fine yet network traffic fails |
| Run Command / VM extensions | Command/code execution via guest agent | When VM agent is healthy and features are supported |

Never treat Boot Diagnostics as a substitute for full system logs or backups. It helps **diagnose root causes**; recovery still depends on disk integrity, backups, and repair procedures.

## 3. Managed Boot Diagnostics vs. Custom Storage Account

When creating an Azure VM in the Portal, Boot Diagnostics is often enabled by default under current flows using an Azure-managed **managed storage account**. When deploying via automation/IaC, verify the VM's actual diagnostics configuration.

| Diagnostics storage option | Strengths | Considerations |
|---|---|---|
| **Managed boot diagnostics storage** | Simple; no need to provision a storage account just for screenshots/serial logs | Service-managed account—not accessed directly like a regular storage account; subject to service retention/capacity limits |
| **Custom storage account** | Meets legacy operational mandates or specific org requirements | Must configure compatible account, region/subscription, permissions, and storage firewalls |

With a custom storage account, Microsoft requires the Boot Diagnostics storage account to sit in the **same subscription and region** as the VM per supported models. Enabling a storage firewall can block screenshots/logs from displaying unless Azure platform access and viewer permissions are properly allowed.

Choose managed mode for most exercises and standard workloads if policy permits. Do not spin up custom storage accounts merely because older examples mention storage URIs; doing so adds cost and operational complexity.

**Distinction:** the Boot Diagnostics storage account **is not the VM's OS disk**, nor is it a full VM backup vault.

### Key Limitations to Remember

- Boot Diagnostics must be enabled before or during evidence capture; enabling it after a failure **cannot retroactively reconstruct logs/screenshots not previously recorded**.
- Screenshots and logs can lag slightly; avoid assuming an old screenshot reflects the exact live screen when you open the Portal.
- Managed boot diagnostics enforce service storage/log limits; do not treat them as unlimited archives.
- Custom storage eligibility, account types, firewalls, and support prerequisites must be checked against current Azure docs.
- Serial logs can contain sensitive text printed by the OS or operators; restrict read access and retention per policy.

## 4. Enabling Boot Diagnostics in the Azure Portal

### For a New VM

1. Open the [Azure Portal](https://portal.azure.com) and choose your subscription and resource group.
2. Configure the VM per approved standards.
3. On the **Management** tab, locate **Boot diagnostics**.
4. Enable Boot Diagnostics and choose **managed storage account** if appropriate.
5. Review settings and create the VM.
6. After startup, verify Boot Diagnostics displays a valid screenshot and serial log.

### For an Existing VM

1. Open the target VM in the Azure Portal.
2. Under **Help** or **Support + troubleshooting**, open **Boot diagnostics**.
3. If disabled, open **Settings**.
4. Enable Boot Diagnostics, preferring managed storage where appropriate.
5. Save and inspect **Screenshot** / **Serial log**.

Menu groupings can shift across Portal updates. **Avoid switching to a custom storage account mid-incident unless required**, as storage permissions or firewalls can delay diagnostics.

### Pre-Troubleshooting Verification

- Correct subscription, resource group, VM name, and region?
- Is Boot Diagnostics Enabled?
- Are the screenshot and serial output recent?
- Did symptoms start before or after a restart/update?
- Are there recent Activity Log actions or config changes near the incident timestamp?

Capture timestamps, error codes, and relevant log lines for the incident record. Redact sensitive identifiers or data before sharing outside authorized responders.

## 5. Enabling and Reading Boot Diagnostics via Azure CLI

Commands below use **Azure CLI** and target only VMs you are authorized to manage. For hands-on practice, use a lab VM—never run unapproved commands on production VMs.

Sign in and select the subscription:

~~~bash
az login
az account list --output table
az account set --subscription "<SUBSCRIPTION_ID>"
az account show --output table
~~~

Define VM variables:

~~~bash
RG="rg-vm-lab"
VM="vm-boot-lab"
~~~

Check VM state before making changes:

~~~bash
az vm get-instance-view \
  --resource-group "$RG" \
  --name "$VM" \
  --output json
~~~

To enable **managed Boot Diagnostics** on an existing VM, omit the storage URI parameter:

~~~bash
az vm boot-diagnostics enable \
  --resource-group "$RG" \
  --name "$VM"
~~~

Retrieve the serial boot log once available:

~~~bash
az vm boot-diagnostics get-boot-log \
  --resource-group "$RG" \
  --name "$VM"
~~~

Use **az vm boot-diagnostics get-boot-log-uris** when service-generated links are needed under supported permissions. Those temporary URIs can embed SAS/authorization tokens: **never paste them into tickets, logs, or public repositories**.

Example inspecting Boot Diagnostics configuration on the VM resource:

~~~bash
az vm show \
  --resource-group "$RG" \
  --name "$VM" \
  --query "{vm:name,bootDiagnostics:diagnosticsProfile.bootDiagnostics}" \
  --output json
~~~

**Note:** resource configuration alone does not prove the VM booted. Combine **instance view**, screenshots, serial logs, and app checks. If CLI reports insufficient permissions, never grab storage account keys or bypass organizational policies to read data.

## 6. Interpreting Screenshots and Serial Logs

Suppose you open Boot Diagnostics and observe one of these states:

| Symptom | Initial hypothesis | Next step |
|---|---|---|
| Linux shows GRUB menu or GRUB rescue prompt | Bootloader, filesystem, or boot config issue | Collect logs, check disks, use Serial Console/repair per docs |
| Linux reports kernel panic | Kernel/driver/initramfs, root filesystem, or system fault | Record exact panic string, check kernel/update version |
| Linux enters emergency mode | Mount failure, bad `fstab`, filesystem, or boot dependency | Serial Console, inspect mounts and `systemd` logs |
| Linux shows login prompt | Boot likely completed to sign-in stage | Investigate SSH, networking, auth, and apps |
| Windows shows Automatic Repair / Recovery | BCD, Windows update, driver, or boot failure | Capture error code, evaluate SAC / repair VM |
| Windows reports `INACCESSIBLE_BOOT_DEVICE` | OS cannot access boot device/partition during startup | Check drivers, BCD, partitions, disk attachment |
| Windows shows sign-in screen | OS likely booted; RDP may still be blocked | Network Watcher, NSG, firewall, RDP services |
| Black screenshot and empty serial log | Very early hang, guest lacks serial output, stale image, or broken Boot Diagnostics config | Check VM power state, log source, serial config, and timestamp |

**One screenshot cannot prove root cause.** Always correlate **exact error lines, recent change timestamps, and signals from other layers**.

### Example Linux Serial Log

~~~text
[  OK  ] Started Network Manager.
[FAILED] Failed to mount /data.
You are in emergency mode.
~~~

This is an illustrative snippet. If it happens right after editing **/etc/fstab**, your first suspect should be an invalid UUID, device path, or mount option. Never jump to “Azure lost my disk” before inspecting configuration and managed disk attachment state.

### Example Windows Recovery Screen

~~~text
Recovery
Your PC/Device needs to be repaired
Error code: 0xc000000f
~~~

Error codes are **clues**, not a complete diagnosis: this can relate to BCD/boot files or other issues. Verify VM generation, partition layout, and disk state before running BCD repair commands.

## 7. Azure Serial Console: Access When SSH/RDP Fails

**Azure Serial Console** opens a text terminal directly to the VM's serial port through an Azure service. It **does not require working SSH/RDP or a public IP**, nor does it rely on NSGs allowing ports 22/3389. It is especially useful when an in-guest firewall change or network misconfiguration locks out normal admin access.

~~~text
Authorized Azure operator
       |
       | Azure Portal / serial-console service
       v
  Azure Serial Console
       |
       | VM virtual serial port
       v
Linux: ttyS0 / getty / bootloader
Windows: EMS / SAC if configured in image
~~~

Serial Console **is not an always-available magical shell**. The VM must be in a compatible state, feature prerequisites must be met, and the guest OS must configure serial output. If the guest hangs very early or emits no serial console output, the screen may stay blank.

### Typical Prerequisites

- An **Azure Resource Manager** VM in a connectable state; a **deallocated** VM cannot host an active serial session.
- Boot Diagnostics enabled per service requirements.
- Azure account with **appropriate VM/Serial Console permissions**; Microsoft docs commonly require **Virtual Machine Contributor** or equivalent, plus access to the boot diagnostics storage when custom storage is used.
- Serial Console is not disabled at the subscription/VM policy level; the operator's browser/network can reach the Serial Console service.
- Custom Linux images need serial console output and **getty** on **ttyS0**; Windows requires supported **Emergency Management Services / Special Administration Console (EMS/SAC)**.
- Signing into the guest still requires **valid guest OS credentials/auth**. Azure permissions do not replace OS passwords.

Exact permission and storage-connectivity rules for Serial Console evolve over time, particularly around managed vs. custom boot diagnostics storage; consult official docs and actual error messages if access fails.

**Security:** Serial Console provides deep in-guest recovery access—restrict RBAC tightly, audit sessions, and follow break-glass procedures. Never type secrets or print tokens in console commands, as output can be captured in serial logs.

## 8. Opening Serial Console from Portal and CLI

### In the Azure Portal

1. Sign into the Portal with an identity authorized to operate the VM.
2. Open the target VM and confirm it is **Running**.
3. Ensure Boot Diagnostics is Enabled.
4. Select **Serial console** under Help / Support + troubleshooting.
5. Wait for connection; on Linux you may need to press **Enter** to reveal the login prompt.
6. If supported by the guest OS, sign in with valid credentials and run only approved diagnostic steps.

With **Virtual Machine Scale Sets**, you typically select a **specific instance** rather than the scale set overview; the model/instance must meet feature prerequisites.

### Azure CLI (Optional)

Azure CLI provides the **serial-console** extension with:

~~~bash
az serial-console connect \
  --resource-group "<RESOURCE_GROUP>" \
  --name "<VM_NAME>"
~~~

This opens an interactive session, not a passive log reader. Check **az serial-console connect --help** for your CLI/extension version. During incidents, if corporate networks block WebSockets, Portal/CLI connections can fail even while the VM runs normally.

**Never fire reset/NMI/SysRq commands** just to test connectivity; those signals can disrupt workloads, lose unflushed data, or alter guest OS state. Any restart signal requires explicit intent and approval.

## 9. Serial Console on Linux: ttyS0 and Boot Signals

On Linux, Azure Serial Console typically attaches to **ttyS0**. Most Azure-endorsed Linux images preconfigure serial console output; for custom images, ensure:

- Kernel/bootloader emit messages to the serial console as appropriate.
- A login prompt spawns via **serial-getty@ttyS0** or your distro's equivalent service.
- Guest accounts have an allowed authentication method for serial terminal login.
- Password, PAM, `sudo`, and audit policies comply with organizational standards.

Once signed into Linux over Serial Console, relatively safe **read-only status** commands include:

~~~bash
uname -a
cat /etc/os-release
systemctl --failed
systemctl status ssh --no-pager
journalctl -b -p err --no-pager
lsblk -f
findmnt -a
df -h
~~~

Not every command works if the VM dropped into rescue/emergency mode. Some distros name the SSH service **sshd** instead of **ssh**, and during incomplete early boots the journal may not yet hold full logs.

### Diagnosing `/etc/fstab` Failures

**/etc/fstab** defines filesystems mounted at boot. A wrong UUID, a detached disk, or strict mandatory mount options can drop Linux into **emergency mode**.

Read-only comparison commands:

~~~bash
cat /etc/fstab
lsblk -f
blkid
findmnt -a
systemctl --failed
~~~

Compare UUIDs and actual block devices before editing. **Never format, run `mkfs`, or delete partitions** simply because a mount point is missing; those actions destroy data.

If a secondary data disk is non-critical, **nofail** or appropriate mount options can be evaluated, but only after understanding the consequences: which apps depend on that disk, whether starting without it is safe, and how mount failures are alerted.

### Diagnosing a Full Root Filesystem

A full disk can block apps, logging, or startup steps:

~~~bash
df -h
df -i
du -sh /var/log /var/cache 2>/dev/null
journalctl --disk-usage
~~~

Before deleting files, check **whether a file holds business data, transaction logs, or forensic evidence**. Never blindly wipe **/var/log**, journals, or database files; use backups, retention policies, and controlled cleanup.

### GRUB, initramfs, and Kernel Panics

Very early boot errors can involve:

- **GRUB/bootloader:** altered menu config or missing boot files.
- **initramfs:** missing drivers/metadata needed to mount the root filesystem.
- **Kernel panic:** kernel, driver, or root filesystem fault halting OS startup.
- **Filesystem corruption:** following unclean shutdowns, storage/partition faults, or interrupted updates.
- **Kernel/OS update:** an update incompatible with the image, drivers, or VM generation.

Boot Diagnostics captures the error lines, and Serial Console may allow bootloader interaction where supported by the image. **Never copy random GRUB/dracut/fsck commands from the Internet** before verifying distro, version, disk layout, UEFI/BIOS mode, and taking a safe backup.

## 10. Serial Console on Windows: EMS and SAC

On Windows, Azure Serial Console exposes the **Special Administration Console (SAC)** when **Emergency Management Services (EMS)** is configured. Many Azure-endorsed Windows Server images enable it by default; custom or older images may need it enabled beforehand.

SAC is a **text-based emergency administration console**, not a graphical RDP desktop. Depending on setup, SAC lets you open a command channel and inspect system info using valid guest credentials.

| Windows state | Approach |
|---|---|
| SAC prompt appears | Authenticate inside the guest and inspect services, networking, and logs per privileges |
| Health info appears without a SAC prompt | Verify whether EMS/SAC is enabled on the image |
| VM fails before SAC initializes | Use screenshots, error codes, and offline repair workflows |
| Windows boots yet RDP fails | Check RDP service, Windows Firewall, NSG/UDR, IP, and credentials |

Inside an authorized SAC command prompt, **read-only inspection** commands include:

~~~powershell
hostname
whoami
ipconfig /all
sc.exe query TermService
bcdedit /enum all
wevtutil qe System /c:20 /rd:true /f:text
~~~

These commands are illustrative and depend on privileges, Windows version, and console mode. **Never run `bcdedit /set`, `bcdboot`, `bootrec`, or partition-modifying commands** without diagnosing Gen1/Gen2, BIOS/UEFI, and exact BCD paths first.

### Common Windows Boot Errors

| Symptom | Investigation focus |
|---|---|
| **`INACCESSIBLE_BOOT_DEVICE`** | Boot disk, storage drivers, OS config, image/partition changes |
| **`0xc000000f` / `0xc000000e`** | Boot configuration, device paths, or missing boot files |
| **Automatic Repair loop** | Recent updates, drivers, BCD, system files, or filesystem corruption |
| **Continuous Windows Update rollback** | Update history, servicing logs, and recovery state |
| **Login screen visible yet RDP times out** | Networking, firewall, TermService listener, NSG, routes, DNS |

Never assume one error code always maps to one identical fix. For instance, `0xc000000f` can require different recovery steps between Generation 1 and Generation 2 VMs. Microsoft publishes specific runbooks per boot failure type and VM generation.

## 11. Separating Boot Failures from Network Connectivity Failures

A common mistake is assuming **cannot SSH/RDP ⇒ VM failed to boot**. These are distinct problems.

### When the Screenshot Shows a Sign-In Screen

If Boot Diagnostics displays a Linux or Windows login prompt, the OS almost certainly booted to sign-in. Next, check:

1. Is the NIC attached to the intended subnet, IP, and route table?
2. Does the VM have a public IP or an approved internal access path? Not every VM should have a public IP.
3. Do NSGs allow admin traffic from the approved source?
4. Is a User Defined Route steering traffic astray? Network Watcher **Next hop** or Connection Troubleshoot helps here.
5. Is the guest firewall blocking port 22/3389?
6. Is `sshd` / `TermService` running and listening on the expected address?
7. Are the SSH key, password, and logon permissions correct?

**Never open SSH/RDP to the entire Internet just to test.** Use Azure Bastion, VPN, private networks, and approved admin sources. Serial Console can inspect guest firewalls without loosening NSGs.

### Azure VM Agent, Run Command, and Extensions

**Run Command** and most **VM extensions** depend on a healthy VM Agent and guest services. If the kernel has not booted, root filesystem failed to mount, or the agent crashed, those tools will not respond. In that case, Boot Diagnostics and Serial Console remain the right diagnostic channels.

If Run Command succeeds, that is strong evidence the guest OS booted far enough to run the agent; do not keep chasing bootloader errors without contradictory evidence.

## 12. Risk-Tiered Remediation Workflow

Not every outage requires offline repair. A good runbook starts with **read-only diagnosis**:

~~~mermaid
flowchart TD
    A[VM unreachable] --> B{Is VM Running?}
    B -- No --> C[Check power state, Activity Log, provisioning]
    B -- Yes --> D[Read Boot Diagnostics screenshot and serial log]
    D --> E{Did OS reach login or service state?}
    E -- Yes --> F[Check network, SSH/RDP, auth, and services]
    E -- No --> G{Does Serial Console work?}
    G -- Yes --> H[Collect logs, inspect guest, apply narrow fix]
    G -- No --> I[Evaluate repair workflow and disk copy]
    H --> J[Smoke test, monitor, and write RCA]
    I --> J
    F --> J
    C --> J
~~~

### Intervention Tiers

| Tier | Action | Relative risk |
|---|---|---|
| 1 | Read VM instance view, Activity Log, Boot Diagnostics | Low, purely observational |
| 2 | Read Serial Console and guest logs; inspect permissions/network | Low to moderate, if read-only |
| 3 | Apply a targeted guest config fix backed by evidence; record diff | Moderate, requires backup/rollback |
| 4 | Restart VM, change boot settings, or restart OS services | Moderate to high, incurs downtime |
| 5 | Repair OS disk offline, swap OS disk, fix BCD/GRUB/filesystem | High, requires snapshots, approval, and exact runbook |
| 6 | Restore VM/disk from backup, fail over to standby | High, governed by RPO/RTO and data state |

Every intervention must specify **target resource, expected change, success criteria, data risk, and rollback plan**. For production, log timeline and approvals before intervening.

## 13. When Are a Repair VM and Offline OS Disk Repair Needed?

If the guest cannot reach an admin session even via Serial Console, or the fault sits inside OS boot configs or partitions, **offline repair** may be required:

1. Confirm the root cause and repair procedure matching **Windows/Linux**, VM generation, and disk type.
2. Take a **snapshot/backup or safe copy** of the OS disk before any mutation; verify permissions and retention policies.
3. Use Microsoft's **Azure VM repair** tooling or create a repair VM running a compatible OS.
4. Attach a **copy of the broken OS disk** to the repair VM safely. Never format the disk.
5. Inspect partitions, filesystems, boot configurations, and logs once mounted properly.
6. Apply only targeted, verified fixes, logging every step and output.
7. Complete the **restore/rebuild/swap** flow per the chosen tool.
8. Boot the original VM, check fresh Boot Diagnostics, and run smoke tests.
9. Verify data integrity and clean up repair resources once approved.

### Azure VM Repair Commands

Microsoft provides the **az vm repair** Azure CLI extension workflow to assist Windows/Linux VM repairs. It can provision a **repair VM**, attach a copy of the OS disk, run repair scripts, and swap/restore the repaired disk back. Exact capabilities and flags vary by OS, deployment mode, and disk encryption type.

**There is no single universal repair command safe for every boot failure.** Before running anything, read official OS-specific repair docs and `az vm repair --help`; confirm backups, RBAC, costs, downtime, and rollback plans.

### Critical Offline Repair Warnings

- **Disk identity:** clearly distinguish the original disk, snapshot, copied disk, and repair VM's own disks. Mixing up disks can destroy data.
- **Encryption:** if the OS disk uses Azure Disk Encryption, BitLocker, customer-managed keys, or specialized modes, follow supported unlock/mount docs—never disable encryption blindly.
- **VM generation:** BIOS/MBR (Gen1) vs. UEFI/GPT (Gen2) changes bootloader/BCD repair commands completely.
- **Multi-disk workloads:** repairing the OS disk alone does not recover a database sitting on data disks.
- **Repair VM locality:** confirm region/zone, SKU, permissions, and network support; extra VMs, storage, and copies incur charges.
- **Recovery points:** snapshots do not guarantee application consistency, and restoring discards changes written after the recovery point.

Never delete the original OS disk or source VM to “make room” for repair before a verified fallback exists.

## 14. Linux: Boot Failure Analysis by Category

### Scenario A — Broken `/etc/fstab` After Adding a Data Disk

**Context:** an administrator appended a mount entry using **/dev/sdc** and rebooted. Linux drops into emergency mode because device names shifted or the disk is absent.

**Approach:**

1. Read the screenshot and serial log to identify the exact failing mount unit.
2. Sign in via Serial Console if accessible, or use a repair VM if the root filesystem fails to mount.
3. Compare **/etc/fstab**, **lsblk -f**, UUIDs, and partitions.
4. Fix **only the broken line** on a backed-up system; prefer UUIDs over mutable `/dev/sd*` names.
5. Test filesystem/mount config, then reboot per procedure.
6. Verify data and dependent apps work properly.

**Never run `mkfs`** to “fix a mount failure” when you do not know what data resides on the disk.

### Scenario B — Kernel Update Causes a Panic

**Context:** a new kernel was installed right before the outage; console prints root-mount failure or kernel panic.

**Approach:**

- Record the last working kernel version and current panic text.
- Check whether selecting the previous kernel from the bootloader is possible per distro/setup.
- If bootloader/console are inaccessible, follow distro/Azure offline repair docs.
- Inspect `initramfs`, drivers, and filesystems; edit only with backups and a rollback path.

Booting an older kernel is **useful diagnostic evidence**, not proof the underlying cause is solved. Audit your patching pipeline and image compatibility.

### Scenario C — Root Filesystem Full

**Context:** after a log spike, SSH stops responding and several `systemd` services fail to start.

**Approach:**

- Inspect `df`/`du`/journal usage via Serial Console or recovery mode.
- Identify safe files to clean under policy—never delete transaction logs or unique business data.
- Investigate why logs spiked, fix log rotation/retention, and evaluate disk sizing.
- Restart affected services or the VM if needed, then monitor utilization.

### Scenario D — Network Misconfiguration Breaks SSH

**Context:** VM booted cleanly, yet editing network config/firewall causes SSH timeouts.

**Approach:** Boot Diagnostics shows the login prompt; use Serial Console to inspect network interfaces, routes, firewall rules, and `sshd`. This is a **connectivity issue**, requiring no bootloader repair or OS disk swap.

## 15. Windows: Boot Failure Analysis by Category

### Scenario A — BCD / Windows Boot Manager Error

**Context:** Boot Diagnostics screenshot shows `0xc000000f`, `0xc000000e`, or OS not found.

**Approach:**

1. Record the error code and recent changes: disk swap, resize, Windows update, driver, image capture.
2. Verify the OS disk resource and VM generation.
3. Follow Microsoft's runbook for that exact error code and UEFI/BIOS setup.
4. If offline repair is needed, snapshot and attach a copy of the OS disk to a repair VM per docs.
5. Repair BCD/boot files **only on the appropriate copy per approved runbook**; verify after swapping back.

### Scenario B — `INACCESSIBLE_BOOT_DEVICE`

The OS cannot access its boot volume under current configuration. Investigate disk attachment, storage drivers, VM image/generation changes, and recent edits. **Never format or repartition** simply because Windows could not find the boot device.

### Scenario C — Windows Update or Driver Triggers Recovery Loop

After an update, the VM loops in Automatic Repair. Capture error screens, identify the update/driver, and evaluate Windows recovery options or offline repair. If a valid application-consistent Azure Backup exists, consider restoring per RPO/RTO targets. Do not power-cycle blindly hoping it fixes itself.

### Scenario D — Windows Boots to Login Yet RDP Fails

Inspect `TermService`, Windows Firewall, NSGs, Bastion/VPN, IP routes, and credentials. If SAC works, inspect services/networking without opening 3389 to the Internet. Never run commands disabling all Windows Firewalls in production to test.

## 16. Boot Diagnostics, Serial Console, and Operational Security

Both tools expose more sensitive system details than many teams realize:

- Screenshots can reveal usernames, hostnames, internal file paths in errors, or operational context.
- Serial logs can contain kernel arguments, file paths, app messages, command output, or accidentally printed secrets.
- Anyone authorized to open Serial Console can act as if physically at the OS console once holding valid guest credentials.
- If another user could view or take over an active Serial Console session, interactive logins must follow strict session governance.

**Safety rules:**

1. Grant minimal Azure RBAC strictly to the VM operations team.
2. Require policy-compliant guest OS authentication; never share one long-lived root/Administrator password.
3. Govern break-glass accounts with strict lifecycle, access controls, and auditing.
4. Never type secrets into commands that could appear in serial logs.
5. Never store screenshots/logs in public shares; redact sensitive data in tickets.
6. Verify storage permissions and firewalls when using custom boot diagnostics storage.
7. Log who used Serial Console, when, what actions were taken, and why.

### Corporate Networks May Block Serial Console

If the Portal reports a **WebSocket connection** error or sessions open and immediately close, first check whether the block sits between your browser and the service or on the VM. Some corporate networks must allow current Serial Console service hostnames—such as **`*.serialconsole.azure.com`**—per Microsoft docs and network policy. Never immediately alter the VM's NSG, because Serial Console traffic is not a traditional RDP/SSH flow.

## 17. Cost and Operational Limits

Boot Diagnostics with managed storage keeps setup simple, yet total remediation costs involve additional resources:

| Resource / action | Cost risk |
|---|---|
| Primary VM | Continues incurring compute charges while allocated/running per SKU |
| Custom boot diagnostics storage | Storage, transactions, and related fees per configuration |
| Snapshots / copied OS disks | Storage charges while snapshots/copies remain |
| Repair VM | Compute, OS disk, networking, public IP, and temp storage per config |
| Backup / restore | Retention, backup vault storage, and restore services |
| Logging / monitoring | Log ingestion, retention, and analytics if enabled |

A **Stopped (Deallocated)** VM generally stops VM compute billing per service rules, yet **managed disks, public IPs, and other resources can still incur charges**. During an active incident, never deallocate a VM solely to save cents if doing so destroys volatile evidence or blocks recovery.

After repair completes, audit repair VMs, snapshots, cloned disks, NICs/public IPs, and scratch resources. **Never delete backups or copies until recovery is fully verified.**

## 18. Real-World Scenario: Linux VM Loses SSH After Update

A Linux VM serves an API in a private subnet. After an update window at 01:00, monitoring alerts on SSH timeout. The Azure Portal reports the VM **Running**.

### Step 1 — Isolate the Layer

- Check Activity Log: were there VM restarts, disk edits, NSG edits, or deployments?
- Check Boot Diagnostics: does the screenshot show a login prompt or emergency mode?
- Read serial log: any kernel panic, failed `systemd` units, or mount failures?

Suppose the serial log prints:

~~~text
Dependency failed for /data.
Failed to mount /data.
You are in emergency mode.
~~~

The strongest hypothesis points to a data disk mount failure—**not an NSG block**.

### Step 2 — Gather Evidence and Inspect

If Serial Console allows sign-in:

~~~bash
lsblk -f
cat /etc/fstab
systemctl --failed
journalctl -b -p err --no-pager
~~~

Compare the broken mount line's UUID against actual device UUIDs. If a disk was detached in Azure, inspect VM Data Disks configuration too. Back up `/etc/fstab` before making any critical edits.

### Step 3 — Targeted Fix and Retest

Instead of creating new disks or formatting, the operator fixes the exact mount reference per runbook, verifies permissions and data, and reboots. Next, verify:

- Boot Diagnostics shows the login prompt and serial logs show zero mount errors.
- SSH works over the approved private/Bastion channel.
- Volume **/data** matches the expected UUID and contains intact data.
- The API responds normally and database connectivity succeeds.
- Monitoring, backups, and mount configs remain stable.

### Step 4 — Prevention

Going forward, enforce approved UUIDs and mount options, test reboots in staging, and add synthetic health checks. Document root-cause analysis (RCA) covering mount configuration rather than writing only “VM restarted successfully.”

## 19. Real-World Scenario: Windows VM Enters Recovery

A Windows Server VM stores business data on a data disk. After an update, the Portal reports Running while RDP times out; Boot Diagnostics screenshot shows **Recovery** with a boot configuration error code.

**Recommended runbook:**

1. Record the error code, OS disk state, and recent changes; resist hammering restart repeatedly.
2. Check Serial Console/SAC if supported by the VM/image. If Windows hung before initializing SAC, do not treat an empty Serial Console as an Azure outage.
3. Verify backups/snapshots, VM Generation, and OS disk encryption settings.
4. Consult Microsoft's exact troubleshooting guide for the error code; prepare a repair VM and disk copy if needed.
5. Repair BCD/boot files **on the copied disk per approved runbook**.
6. Swap the repaired OS disk back per procedure and start the VM.
7. Verify Boot Diagnostics, Windows services, secure RDP path, and data disk access.
8. Verify business data integrity, event logs, and ongoing backup jobs.

If the OS disk cannot be reliably repaired, evaluate restoring from Azure Backup or rebuilding the VM from a golden image and reattaching/restoring data per policy. Choose based on RPO/RTO and unbacked-up data—not merely whichever rebuild seems fastest.

## 20. Safe Hands-On Lab: Observing a Lab VM

**Goal:** learn to enable Boot Diagnostics, inspect screenshots/logs, compare Serial Console against SSH/RDP, and plan boot-failure triage **without intentionally breaking a VM**.

### Preparation

- An authorized Linux or Windows lab VM with no critical data.
- Account with Boot Diagnostics read access, plus Serial Console access if practicing interactive sessions.
- Approved budget, region/VM size, and compute/disk/network costs.
- Never open RDP/SSH to the Internet just to test Serial Console.

### Part A — Read State Before Intervening

1. Record subscription, resource group, VM name, OS image, and power state.
2. Open **Boot diagnostics** in the Portal.
3. Record the timestamp, screenshot description, and key messages in the Serial log.
4. Run read-only CLI commands:

~~~bash
RG="<LAB_RESOURCE_GROUP>"
VM="<LAB_VM_NAME>"

az vm get-instance-view --resource-group "$RG" --name "$VM" --output json
az vm boot-diagnostics get-boot-log --resource-group "$RG" --name "$VM"
~~~

5. Compare logs against guest state once signed in over your normal admin channel.

If Boot Diagnostics is off, enable it per sections 4/5 **once authorized**; log this as a configuration change so incident timelines remain accurate.

### Part B — Inspect Serial Console

1. Open Serial console in the Portal and confirm the session connects.
2. If a Linux VM displays a login prompt, sign in with the lab account and run `uname -a`, `lsblk -f`, and `systemctl --failed`.
3. If a Windows VM supports SAC, inspect initial output; open a command prompt only with valid guest credentials and a clear objective.
4. Note down: does Serial Console require a public IP? Does it depend directly on NSG ports 22/3389?
5. Sign out and close the session cleanly—never leave privileged shells open.

Never intentionally trigger kernel panics, corrupt `/etc/fstab`, delete boot files, or send hard resets to “simulate a lab fault.” Use **observed evidence and tabletop scenarios** to avoid data risk.

### Part C — Analyze Hypothetical Scenarios

| Evidence | Question to answer |
|---|---|
| VM Running; screenshot shows Linux emergency mode; log shows `"Failed to mount /data"` | What is the primary suspect and which files/devices must you inspect? |
| VM Running; Windows login screenshot; RDP times out | Why can you not conclude a boot failure yet? |
| Black boot screenshot; empty serial log; VM freshly built from custom image | Which console/boot diagnostics prerequisites should be checked? |
| VM deallocated; Serial Console fails to connect | Is this an NSG issue? Which state must be checked? |
| Azure VM Agent unresponsive; VM has not reached login | Why might Run Command fail to help? |
| OS disk snapshot exists yet consistency is uncertain | What must you verify before swapping disks in production? |

### Deliverables

| Item | Evidence |
|---|---|
| VM and state | Resource ID, OS, power state, inspection timestamp |
| Boot Diagnostics | Screenshot/logs reviewed, relevant messages (redacting sensitive data) |
| Serial Console | Connection status, prerequisites/permissions, guest console type |
| Diagnosis | Cause category, 2–3 hypotheses, verification steps |
| Safety | Backup/snapshot details, intervention risk, rollback criteria |
| Conclusion | Priority remediation plan, owners, smoke tests |

## 21. Common Error Matrix

| Symptom | Possible causes | Reasonable next check |
|---|---|---|
| Boot diagnostics blade missing or access denied | Insufficient RBAC, disabled diagnostics, unsupported VM type, or policy | Check IAM, diagnostics settings, VM model |
| Screenshot not updating | Diagnostics newly enabled, stale source, or VM not running | Check timestamp, power state, and settings |
| Serial Console prompts to enable Boot Diagnostics | Diagnostics disabled or config state stale | Enable per instructions and retest |
| Serial Console says VM must be Running | VM Stopped/Deallocated | Check VM power state; start if approved |
| Serial Console connects yet screen stays blank | Guest serial output/`getty`/EMS unconfigured, or early hang | Check image, boot log, try pressing Enter on Linux |
| Serial Console WebSocket error | Client-side proxy/firewall or service connectivity | Verify Serial Console service hostnames per docs |
| Linux emergency mode | `/etc/fstab`, UUID, mount unit, filesystem, missing disk | Inspect serial logs, `lsblk`, `fstab`; do not format |
| Linux kernel panic after update | Kernel/initramfs/driver/root filesystem | Capture kernel messages; try prior kernel or offline repair |
| Windows shows Recovery / BCD error | Boot config, disk/driver, or update | Match error code and Gen1/Gen2; snapshot then repair |
| Windows login visible yet RDP broken | Network/NSG/firewall/`TermService` | Network Watcher, SAC, and guest logs |
| Run Command / extension times out | Guest agent unhealthy or OS never booted | Use Boot Diagnostics/Serial Console instead of waiting on agent |
| VM repaired yet app data missing | Data disk detached/unmounted, dependent services down | Check data disks, filesystems, DBs, and app services |
| Unexpected costs after repair | Leftover repair VM, snapshots, copied disks | Inventory resources, confirm recovery, then clean up |

Never conclude “Azure platform outage” solely from an SSH timeout or blank screenshot. Platform issues require verification via Service Health, instance view, and correlated evidence.

## 22. Pre-Closure Incident Checklist

- [ ] Identified exact VM, subscription, region, OS, and incident timeline.
- [ ] Inspected Boot Diagnostics screenshot and serial log, distinguishing fresh vs. stale data.
- [ ] Reconciled VM Running/Provisioning state against actual guest OS state.
- [ ] Isolated boot, connectivity, authentication, or application failure clearly.
- [ ] For Serial Console usage, governed Azure RBAC and guest credentials; logged no secrets.
- [ ] Documented all config edits and took safe backups/copies before risky mutations.
- [ ] For offline OS disk repair, verified VM generation, encryption, exact disk copy, and restore flow.
- [ ] Verified clean reboot/login, application services, and data post-repair.
- [ ] Checked Azure Monitor, guest logs, and alerts for recurring errors.
- [ ] Recorded root cause, rollback conditions, and preventive actions.
- [ ] Cleaned up repair VMs, snapshots, and test resources **only after formal sign-off**.
- [ ] Reviewed incurred costs and updated operational runbooks.

## 23. Self-Check Questions

1. Why can a VM report `Running` while still suffering a boot failure?
2. What two evidence types does Boot Diagnostics collect? Is the screenshot a full boot video?
3. How does managed boot diagnostics storage differ from a custom storage account?
4. Does Serial Console require opening port 22 or 3389 in the NSG?
5. Why does an active Serial Console session not automatically grant root/Administrator privileges?
6. On Linux, what roles do `ttyS0`, `getty`, and serial boot messages play?
7. On Windows, when do SAC/EMS help, and why might a custom image lack SAC?
8. Linux drops to emergency mode after attaching a data disk: why check UUIDs and `/etc/fstab` first?
9. A VM shows the Windows login screen yet RDP times out: which layers should you inspect?
10. Why should you never format a disk attached to a repair VM just because no mount point appears?
11. Is an OS disk snapshot always application-consistent for a live running database?
12. When is offline disk repair needed versus simply fixing NSG/firewall or guest services?
13. Why must you check encryption and VM generation before repairing BCD or GRUB?
14. After fixing a boot failure, what smoke tests and cleanup steps are required?

## 24. References

- [Azure boot diagnostics](https://learn.microsoft.com/azure/virtual-machines/boot-diagnostics) — screenshots, serial logs, and managed/custom diagnostics storage.
- [Boot diagnostics: troubleshooting Azure VMs](https://learn.microsoft.com/troubleshoot/azure/virtual-machines/windows/boot-diagnostics) — using screenshots/console output to investigate.
- [Azure Serial Console overview](https://learn.microsoft.com/troubleshoot/azure/virtual-machines/windows/serial-console-overview) — prerequisites, permissions, and access limits.
- [Azure Serial Console for Linux](https://learn.microsoft.com/troubleshoot/azure/virtual-machines/linux/serial-console-linux) — `ttyS0` and Linux diagnostics.
- [Azure Serial Console for Windows](https://learn.microsoft.com/troubleshoot/azure/virtual-machines/windows/serial-console-windows) — EMS/SAC and Windows boot troubleshooting.
- [Common Azure Serial Console errors](https://learn.microsoft.com/troubleshoot/azure/virtual-machines/windows/serial-console-errors) — permission, WebSocket, and configuration errors.
- [Repair a Linux VM using VM repair commands](https://learn.microsoft.com/troubleshoot/azure/virtual-machines/linux/repair-linux-vm-using-azure-virtual-machine-repair-commands) — offline Linux OS disk repair workflow.
- [Repair a Windows VM using VM repair commands](https://learn.microsoft.com/troubleshoot/azure/virtual-machines/windows/repair-windows-vm-using-azure-virtual-machine-repair-commands) — offline Windows OS disk repair workflow.
- [Azure CLI: az vm boot-diagnostics](https://learn.microsoft.com/cli/azure/vm/boot-diagnostics) — enable, disable, and retrieve logs.
- [Azure CLI: az serial-console](https://learn.microsoft.com/cli/azure/serial-console) — connect via CLI.

**Conclusion:** When an Azure VM becomes unreachable, **inspect VM state and Boot Diagnostics first**, use **Serial Console** when guest OS interaction is needed while SSH/RDP fails, and only then decide between configuration fixes or offline OS disk repair. Separating boot failures from network issues, preserving evidence, protecting data, and maintaining rollback paths enable faster recovery without introducing extra risk.
