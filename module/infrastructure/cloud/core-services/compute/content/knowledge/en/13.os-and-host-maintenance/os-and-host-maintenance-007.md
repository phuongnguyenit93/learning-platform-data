# Tracking Operating System, Kernel, and Supporting Software Lifecycles

A virtual machine may run stably for years, yet its operating system, kernel, libraries, drivers, and agents each follow their own lifecycle. A Linux or Windows Server version can reach end of security support; a newer kernel may break compatibility with older drivers; a backup or monitoring agent may drop support for a distribution. Monitoring only VM uptime without tracking these components leaves an organization running active workloads that are unpatched or unsupported by the vendor.

**OS and supporting software lifecycle management** is the process of identifying active versions, tracking support milestones, assessing compatibility, planning updates or upgrades, testing, and replacing outdated components. This applies to VMs, bare-metal servers, container nodes, and images used to provision new machines.

In the **CLOUD_CORE_SERVICES_COMPUTE** module, this lesson focuses on tracking OS, kernel, and supporting software lifecycles to maintain security, compatibility, and availability across compute infrastructure. Topics include EOL/EOS milestones, LTS, kernels, drivers, runtimes, agents, inventory, patch management, live patching, reboots, image lifecycles, and upgrade planning.

## 1. Why Manage Lifecycles?

A cloud system is more than CPU, RAM, storage, and networking. Each VM carries a software dependency chain:

- Operating system and release version.
- Kernel and kernel modules.
- Firmware, drivers, and guest tools.
- System libraries, packages, and application runtimes.
- Monitoring, backup, security, management, and update agents.
- Applications, frameworks, and database engines.

These components are released, patched, and retired on different schedules. For example, a Windows Server release may remain supported while the installed .NET version or backup agent has reached end of support. Conversely, an application may stay compatible with a distribution while the running kernel lacks critical security patches.

Lifecycle management pursues these objectives:

1. Know the exact OS, kernel, package, and agent versions running on each host.
2. Detect versions approaching end of support before they become risks.
3. Maintain security patches and bug fixes prioritized by risk.
4. Ensure drivers, agents, and applications are compatible with target OS versions.
5. Schedule reboots or host replacements in a controlled manner.
6. Standardize images so new hosts never launch from outdated foundations.
7. Reduce incident troubleshooting time and emergency upgrade costs.

A machine responding to pings or serving requests does not prove its OS is still supported. Operational status and lifecycle status must be tracked separately.

## 2. Lifecycle Milestones to Distinguish

Vendors use different terms for support phases. Exact names and policies vary by product, edition, and release channel.

| Term | Typical Meaning | Action Required |
|---|---|---|
| Release / General Availability | Version becomes broadly available | Evaluate compatibility and timing for standardization |
| Mainstream support | Primary support phase, typically covering security updates and bug fixes per policy | Stay on supported versions and track end dates |
| Extended support | Extended phase where update scope may narrow or carry extra conditions | Confirm entitlements, cost, and migration plan |
| End of maintenance / End of updates | Vendor stops issuing maintenance updates or patches on that channel | Switch to another support channel or upgrade |
| End of life (EOL) | Version reaches end of lifecycle as defined by the vendor | Migrate off the version unless under a controlled exception |
| End of support (EOS) | Vendor ends support under published policy | Stop treating as a standard platform for new workloads |

Do not assume EOL, EOS, end of maintenance, and end of standard support fall on the same date. Look up the official lifecycle for the exact product, edition, release, and subscription in use.

### 2.1. LTS and Release Cycles

LTS (Long-Term Support) commonly denotes releases with longer support windows than standard releases. Ubuntu provides LTS releases; enterprise products like RHEL and SLES publish their own release and support lifecycles. Windows Server also defines support milestones by version and edition.

LTS does not mean every package on the system is supported indefinitely. Individual packages may have separate lifecycles, fall outside distribution support scope, or require add-on subscriptions. Check:

- Standard support expiration for the release.
- Terms for extended support or Extended Security Maintenance if applicable.
- Which repositories or update channels hosts are consuming.
- Which packages are vendor-supported versus third-party.
- Whether application versions are certified on that LTS release.

### 2.2. Versions and Support Branches

An OS can have multiple active branches concurrently, such as stable, LTS, maintenance updates, and newer releases. Record the full version and release channel, not merely "Linux" or "Windows."

For instance, "Ubuntu Server" does not reveal which LTS release is running; "Windows Server" omits release, edition, and build. When planning, record product name, release, build or version, CPU architecture, and support channel.

## 3. Kernel Lifecycle

The kernel is the core component managing processes, memory, devices, filesystems, and the network stack. Kernels receive security patches, bug fixes, new hardware support, and behavioral changes. Tracking kernel versions is therefore a critical part of host maintenance.

### 3.1. Kernel Version Is Not the Entire Support Picture

On Linux, `uname -r` reports the running kernel version. However, that version string alone cannot prove a host has received all security patches. A distribution can backport fixes into its kernel package without changing the upstream version number in the way users might expect.

For example, an enterprise distribution's kernel may stay on a stable version branch while the vendor backports tested fixes. Check package releases, vendor advisories, and update status rather than merely comparing `uname -r` against the latest version on kernel.org.

On Windows, the kernel ships alongside OS updates and builds. Track the OS build, cumulative updates, and servicing status for your Windows Server release.

### 3.2. Installed Kernel Package vs. Running Kernel

After installing a kernel update, a host may have the new kernel on disk while still running the old kernel until rebooted. Keep this distinction clear:

- **Installed kernel:** kernel package installed on the filesystem.
- **Running kernel:** kernel currently controlling the system.
- **Boot default:** kernel the bootloader will load on the next boot.

Checking only installed packages without checking the running kernel can mislead teams into thinking a patch is active when the machine has never rebooted.

### 3.3. Kernel Modules and Drivers

Device drivers, filesystem modules, network modules, and security modules may depend on specific kernel versions or distribution ABIs. Out-of-tree drivers—such as certain GPU, storage, or security agent modules—may require rebuilding when the kernel changes.

Before updating a kernel, check:

- Does the driver support the target kernel?
- Does Secure Boot require module signing?
- Do DKMS or module-build mechanisms work properly?
- Do security or backup agents rely on custom kernel modules?
- Are passthrough devices, GPUs, accelerated NICs, or storage controllers compatible?
- Is a fallback kernel available to roll back if the new kernel fails to boot?

Never upgrade kernels across hosts with specialized GPU or storage drivers without testing on a representative machine first.

## 4. Lifecycle of Packages, Runtimes, and Agents

An OS may remain supported while software running on top of it is already outdated. Each component needs its own version, publisher source, and support schedule tracked.

| Component | Examples | Risks When Outdated |
|---|---|---|
| System libraries | glibc, OpenSSL, systemd | Security vulnerabilities, application incompatibilities |
| Language runtimes | Java, .NET, Node.js, Python | Unsupported runtime, missing patches, package install failures |
| Web/database engines | NGINX, Apache, PostgreSQL, SQL Server | Vulnerabilities, data bugs, or end of vendor support |
| Container runtimes | containerd, CRI-O, Docker Engine | Runtime bugs, kernel or orchestrator incompatibility |
| Guest tools | Cloud guest agents, VM tools | Loss of management, networking, or storage functionality |
| Monitoring agents | Metrics/logging agents | Missing telemetry/logs, excessive agent resource usage |
| Backup agents | Snapshot/file backup agents | Failed backups or unusable restores |
| Security agents | EDR, vulnerability scanners | Missing signatures/patches or incompatibility with newer kernels |
| Database connectors | ODBC/JDBC drivers | Connection failures or behavioral regressions |

### 4.1. Package Sources and Repositories

Package managers install software from configured repositories. If hosts point to unsupported repositories, untrusted mirrors, or mixed distribution sources, updates may fail or install incompatible versions.

Manage:

- Approved repository lists.
- GPG signatures or equivalent package verification mechanisms.
- Stable, LTS, security, or vendor-specific channels.
- Pinned package versions and pinning rationale.
- Whether packages originate from the OS vendor or third parties.
- Processes for retiring old repositories and expired keys.

Version pinning may be needed for compatibility, but must never become a way to delay patches indefinitely. Every pin exception needs an owner, justification, review date, and exit plan.

### 4.2. Runtime and Application Compatibility

Upgrading an OS can alter system libraries, TLS defaults, compiler runtimes, filesystem behavior, or default permissions. Older applications might depend on a removed library or a disabled protocol.

Before upgrading, consult the application vendor's support matrix:

- Certified OS versions and architectures.
- Kernel and base library versions.
- Java/.NET/Node.js/Python or other runtime versions.
- Database engines and connector drivers.
- Security, backup, monitoring agents, and deployment tools.
- TLS configurations, ciphers, certificates, and authentication.

Do not merely verify that the application starts. Run business tests, representative load, backup/restore, and operational procedures.

## 5. Firmware, Guest Tools, and Cloud Supporting Software

Cloud VMs rely on virtual devices, paravirtualized drivers, and integrated agents to interact with the platform. Capabilities such as high network throughput, block storage, shutdown signals, time sync, serial consoles, and remote administration depend on drivers and guest agents.

Components to track:

- Guest agents or cloud-init/Windows bootstrap agents.
- NIC and storage drivers.
- Configuration management or patch management agents.
- Monitoring and log collection agents.
- Backup and snapshot-consistency agents.
- Security and vulnerability scanning agents.
- Provider-managed host firmware or microcode.

In the cloud, the provider usually manages physical host firmware and the hypervisor, while the customer remains responsible for the guest OS and software inside the VM under the shared responsibility model. Exact boundaries depend on whether the service is IaaS, PaaS, or managed compute.

Never install drivers from unverified sources or download guest agents from unofficial sites. Use official repositories or images and verify compatibility with your OS release.

## 6. Building a Lifecycle Inventory

To manage lifecycles, you first need to know which hosts exist and what they run. Inventory must cover running VMs, stopped VMs, templates, golden images, container nodes, bare-metal hosts, and any workload with a customer-managed OS.

Minimum fields to record:

| Field | Contents |
|---|---|
| Asset ID | VM, instance, host, or node ID |
| Owner | Accountable technical team |
| Application | Application or service using the host |
| Environment | Development, staging, production |
| OS product | Operating system name and distribution |
| OS version/build | Release, edition, build, and architecture |
| Kernel | Running kernel and installed kernel packages |
| Image ID | Source image and build version |
| Runtime | Java/.NET/Node.js/Python or relevant runtimes |
| Agents | Monitoring, backup, security, guest tools |
| Support date | Mainstream, extended, and EOL milestones |
| Patch state | Last update date and missing patches |
| Maintenance window | Approved timeframe for maintenance |
| Criticality | Criticality tier and associated SLO/RTO/RPO |

Inventory can be gathered from cloud APIs, Systems Manager, Azure Arc, OS configuration management, endpoint management, or CMDB tools. Sync periodically and flag hosts that stop reporting.

### 6.1. Do Not Scan Only Running Hosts

Old images in catalogs, snapshots, templates, and autoscaling launch configurations can spin up outdated VMs in the future. Therefore, inventory must cover provisioning sources as well as active instances.

For example, a production fleet might be patched while the launch template still references an old image. During scale-out or incident recovery, new instances could boot from the unpatched image. Lifecycle processes must update images and deployment templates together.

### 6.2. Detecting Unmanaged Hosts

A VM lacking an owner, agent, or inventory reporting poses risk because its support status is unknown. Alert on:

- Hosts overdue on inventory reporting.
- Undetermined OS or agent versions.
- Hosts missing owner or application tags.
- Hosts running unapproved OS versions.
- Images lacking build dates or sources.
- Production hosts lacking maintenance windows.

## 7. Tracking Support Milestones and Prioritizing Upgrades

Not every unsupported host carries equal risk. A public-facing VM holding sensitive data demands faster action than an isolated lab machine with no critical data. Nonetheless, every unsupported system requires an owner and a clear remediation plan.

Classifications you can use:

| Status | Meaning | Action |
|---|---|---|
| Supported | Within standard support window | Maintain patches and review periodically |
| Extended support | Under extended support or conditional update channel | Confirm entitlement, cost, and upgrade plan |
| Near EOL | Approaching end of support | Test replacement version and schedule migration |
| Unsupported | Past end of support or no longer receiving standard patches | Prioritize isolation, upgrade, or replacement |
| Exception | Cannot upgrade yet due to technical/business dependencies | Record owner, compensating controls, and deadline |

### 7.1. Risk Ranking

Risk assessment should consider:

- Time remaining until EOL/EOS.
- Severity of unpatched vulnerabilities.
- Network exploitability and Internet exposure.
- Data sensitivity.
- Workload criticality.
- Application and agent compatibility.
- Backup, rollback, and recovery capabilities.

Do not prioritize solely by EOL date. An actively exploited flaw on a supported OS may require remediation ahead of an isolated machine nearing EOL with no sensitive data.

### 7.2. Lifecycle Exceptions

Sometimes legacy applications cannot upgrade OS immediately due to driver, runtime, or vendor certification dependencies. Exceptions require:

- Business and technical owners.
- Specific reason preventing upgrade.
- Exception duration and review date.
- Restricted network scope.
- Narrowed access permissions and identities.
- Enhanced monitoring and tested backups.
- Replacement or modernization roadmap.

Exceptions must never become permanent states without an end date.

## 8. Operating System Patch Management

Patch management is the process of gathering, assessing, testing, deploying, and verifying updates. Patches address security vulnerabilities, stability bugs, driver defects, or compatibility issues.

A basic workflow:

1. Collect advisories and patch lists.
2. Identify affected hosts, packages, and workloads.
3. Prioritize by severity, exploitability, and exposure.
4. Test in a representative environment.
5. Create appropriate backups or recovery points.
6. Deploy in groups/rings.
7. Reboot if required for patches to take effect.
8. Verify packages, kernel, services, and applications.
9. Record failed hosts and manage exceptions.

### 8.1. Security Patches vs. Feature Updates

Security patches typically require risk-based prioritization. Feature updates can alter behavior, APIs, or configurations and require broader testing. Never bundle all update types into one cycle without distinguishing impact.

For production systems, use rings:

- Ring 0: internal test machines.
- Ring 1: development and staging.
- Ring 2: a small production group with fast recovery.
- Ring 3: the remainder of production.

If an error appears in an early ring, pause the rollout to investigate. Never continue automatically just because a scheduled window arrived.

### 8.2. Automated Updates and Controls

Automated updates reduce vulnerability exposure time, while uncontrolled updates can trigger unscheduled reboots or unexpected version shifts. For production hosts, use patch management with maintenance windows, risk-based approvals, and result reporting.

Hosts may use automated update policies when:

- Criticality and recovery capability are defined.
- Updates come from trusted sources.
- An appropriate maintenance window is configured.
- Applications support restarts or failover.
- Post-update monitoring and failure-handling processes exist.

## 9. Live Kernel Patching and Reboot Requirements

Some Linux distributions and platforms support live kernel patching: applying select kernel fixes to a running kernel without an immediate reboot. This helps reduce downtime, though it does not cover every type of change.

Examples you may encounter:

- Canonical Livepatch on Ubuntu within supported versions and terms.
- kpatch or live-patching mechanisms in the RHEL ecosystem.
- SUSE kGraft/live patching per version and subscription.
- Cloud services or management platforms offering kernel patch orchestration.

### 9.1. Limitations of Live Patching

Live patching applies only patches built and supported by the vendor for that mechanism. It does not replace all kernel updates, driver updates, firmware updates, or feature changes. Certain changes still require a reboot to:

- Load a full new kernel.
- Update modules or drivers that cannot be hot-swapped.
- Apply firmware or microcode needing a boot cycle.
- Complete updates to system libraries or user-space components.
- Return the host to a vendor-supported state.

Track live-patch status and reboot-required status separately. A live-patched host may still need a reboot in the next maintenance window.

### 9.2. Determining Whether a Reboot Is Required

On Linux, depending on the distribution, use tools like `needs-restarting -r` (if supported by the package), check `/var/run/reboot-required` on Ubuntu/Debian, or query your patch management agent. No single command works identically across all distributions.

On Windows Server, some updates require a restart to finish. Check pending reboot status via endpoint/patch management tools or system indicators like Component-Based Servicing and Windows Update. Registry-checking scripts should follow Microsoft documentation and not rely on a single registry key as absolute proof.

### 9.3. Scheduling Reboots

Reboots must coordinate with:

- Load balancers and traffic draining.
- Clusters, replication, and quorum.
- Database failover or service shutdown ordering.
- Batch jobs and checkpoints.
- Maintenance windows and owner notifications.
- Backups/restores and post-reboot checks.

For multi-node clusters, reboot sequentially or via rolling reboots to preserve capacity. For stateful clusters, follow database or distributed system procedures; never reboot multiple nodes concurrently if doing so threatens quorum.

## 10. OS Upgrades: In-Place vs. Host Replacement?

When a release nears end of support, two main paths exist.

### 10.1. In-Place Upgrade

An in-place upgrade upgrades the OS directly on the existing host. This can preserve local configuration and data, reducing infrastructure recreation effort. However, upgrades can be blocked by legacy packages, third-party repositories, drivers, bootloaders, or incompatible applications.

Before executing:

- Verify a vendor-supported upgrade path exists.
- Check disk space, filesystems, and packages.
- Test on a clone or staging environment.
- Back up data and configuration.
- Verify drivers, agents, runtimes, and applications.
- Prepare console or rescue access if the host fails to boot.
- Define rollback criteria and expected downtime.

Not every release supports direct upgrades from every older version. You may need an intermediate hop or a fresh host deployment.

### 10.2. Immutable Images and Instance Replacement

With immutable infrastructure, instead of patching an aging OS in place, teams build a fresh, patched, and tested image, launch new VMs, and migrate traffic or workloads onto them. Old hosts are retired once new ones are confirmed healthy.

Advantages:

- New environments launch from clearly versioned images.
- Eliminates drift accumulated over years of manual edits.
- Enables rolling replacement or blue/green cutovers.
- Rollback can be simpler when images and data are properly decoupled.

Prerequisites:

- Critical data resides on persistent or replicated storage.
- Configuration and secrets are injected outside the image.
- Applications support running dual versions during cutover.
- Sufficient capacity exists to run old and new hosts concurrently.
- Load balancers, DNS, or schedulers support workload shifting.

### 10.3. Choosing a Strategy

| Criterion | In-Place Upgrade | Replace Instance/Image |
|---|---|---|
| Keeps existing host | Yes | No, creates new host |
| Risk of legacy config carryover | Can persist | Eliminated via standard image |
| Temporary capacity needed | Usually lower | May need side-by-side capacity |
| Rollback | Can be complex if upgrade alters data | Usually shifts traffic back if data remains compatible |
| Best fit | Stateful or hard-to-recreate hosts with supported upgrade paths | Stateless fleets, autoscaling, mature image pipelines |

No single strategy fits every machine. Weigh data architecture, downtime tolerance, reproducibility, application support, and operational readiness.

## 11. Machine Image Lifecycle Management

Images are the source of VMs. If outdated images remain in catalogs or launch templates, teams can inadvertently spin up hosts running obsolete OS versions.

An image lifecycle workflow:

1. Select an official, supported base image.
2. Install OS, kernel, and foundational package patches.
3. Install approved agent versions.
4. Apply security baselines and logging configurations.
5. Scan vulnerabilities and verify compatibility.
6. Tag version/build ID and record the package manifest.
7. Publish the new image.
8. Update launch templates, autoscaling groups, and pipelines.
9. Mark older images deprecated.
10. Delete or restrict old images per retention policy.

### 11.1. Golden Images Must Not Contain Secrets

Never embed private keys, passwords, tokens, or personal credentials in images. Each instance needs its own identity and should fetch secrets at runtime via a secret manager or supported identity mechanism.

Before capturing an image, generalize/clean machine IDs, host keys, temporary logs, sensitive package caches, and source-host data per OS and cloud provider instructions. Cloning machine identities can cause management systems to confuse multiple hosts as a single asset.

### 11.2. Image Versioning and Deprecation

Images should carry immutable versions or build identifiers. Record:

- OS release and kernel package.
- Build date and source image.
- Package/agent list with versions.
- Applied security baseline.
- Test and scan outcomes.
- Expiration or review date.

When releasing a new image, locate every launch template, autoscaling policy, and pipeline still referencing the old image. Marking an image deprecated does not automatically stop deployment configs from using it.

## 12. Tracking Agent and Driver Lifecycles

Agents pose risks comparable to outdated OS versions. A security agent incompatible with a new kernel can prevent booting or leave the host unprotected. An outdated backup agent might report success yet fail to restore data.

For each agent, track:

- Vendor and product name.
- Installed version.
- Supported OS releases and kernels.
- Latest organization-approved version.
- End-of-support milestone.
- Update and service restart method.
- CPU/RAM/network overhead consumed by the agent.
- Heartbeat status and last check-in timestamp.

When upgrading an OS, upgrade agents in compatibility order. Sometimes the agent must update before the OS; other times the new OS must come first before the newer agent installs. Follow the vendor's compatibility matrix rather than guessing.

### 12.1. Drivers and Accelerators

GPUs, accelerated NICs, storage controllers, and passthrough devices often require specialized drivers. For high-performance compute workloads, coordinate versions across:

- OS image.
- Kernel.
- GPU/NIC/storage drivers.
- CUDA or acceleration libraries if using GPUs.
- Container runtime and device plugins.
- Application or framework versions.

Upgrading a single layer independently can break the compatibility chain. Test the full version stack on a representative host group.

## 13. Linux Inventory and Inspection Examples

The following commands collect partial OS and kernel details. Feed outputs into inventory or configuration management rather than viewing them manually alone.

~~~bash
# Identify distribution and version
cat /etc/os-release

# Check running kernel
uname -r

# Check CPU architecture
uname -m

# Check system uptime
uptime

# Ubuntu/Debian: list installed kernel packages
dpkg-query -W 'linux-image*' 2>/dev/null

# Debian/Ubuntu: check reboot-required flag if present
if [ -f /var/run/reboot-required ]; then
  cat /var/run/reboot-required
fi

# RHEL-like: list installed kernel packages
rpm -q kernel

# RHEL-like: list available security advisories
sudo dnf updateinfo list --security
~~~

Package commands depend on the distribution. A system may run a kernel package with backported fixes; cross-reference vendor advisories and update status. `uname -r` shows only the running kernel and does not prove all patches are installed.

### 13.1. Checking Services and Agents

~~~bash
# List running services
systemctl --type=service --state=running

# Check an agent's version if supported by the binary
/opt/vendor-agent/bin/agent --version

# Check agent service status
systemctl status vendor-agent

# View recent agent logs
journalctl -u vendor-agent --since "24 hours ago"
~~~

Replace example paths and service names with the actual installed products. Never bulk-restart agents without knowing the impact on workloads.

## 14. Windows Server Inspection Examples

PowerShell can gather OS, build, and installed update details:

~~~powershell
# Product name, version, and build
Get-ComputerInfo |
  Select-Object WindowsProductName, WindowsVersion, OsBuildNumber, OsArchitecture

# OS details via CIM
Get-CimInstance Win32_OperatingSystem |
  Select-Object Caption, Version, BuildNumber, LastBootUpTime

# Recently installed hotfixes
Get-HotFix |
  Sort-Object InstalledOn -Descending |
  Select-Object -First 20 HotFixID, InstalledOn, Description

# List agent services by name pattern
Get-Service |
  Where-Object { $_.Name -match "agent|backup|monitor|security" } |
  Select-Object Name, Status, StartType
~~~

`Get-HotFix` is not a complete list of every serviced component; combine it with update management tools and Windows Update/endpoint management reports. Service names may not match the example keywords, so production inventory should track an explicit list of managed agents.

## 15. Fleet Maintenance Scheduling

A fleet may comprise hundreds or thousands of VMs. Updating hosts manually one by one is error-prone and hard to track. Group hosts by application, environment, criticality, OS, and maintenance window.

### 15.1. Grouping by Role

Examples:

- Stateless web tier: rolling replacement behind a load balancer.
- Workers: stop accepting new jobs, complete or checkpoint, then update.
- Databases: follow failover order, replication checks, and engine procedures.
- GPU hosts: test drivers and frameworks on a new image.
- Legacy hosts: dedicated maintenance windows and owner approval.

### 15.2. Rolling Maintenance

For multi-node clusters, update one node or a small batch at a time:

1. Verify the cluster is healthy with sufficient capacity.
2. Select an eligible node for maintenance.
3. Drain workloads and shift traffic.
4. Update OS/agents/drivers.
5. Reboot if needed.
6. Verify node, application, and metrics.
7. Return the node to the cluster.
8. Move to the next node.

Never update so many nodes concurrently that quorum or minimum capacity is lost. For stateful systems, follow database and cluster platform guidelines.

### 15.3. Maintenance Windows and Notifications

Maintenance windows should specify:

- Start/end times and timezone.
- In-scope workloads and assets.
- Approvers and on-call engineers.
- Expected downtime or impact.
- Rollout stop conditions.
- Rollback/restore plan.
- Post-maintenance verification tests.

Never schedule reboots without notifying application owners. A patch may require service restarts or alter the network stack, disrupting long-lived connections.

## 16. Planning Upgrades Before EOL

When an OS approaches end of support, start from your inventory and dependency map. Never wait until the final week to search for a replacement version.

Sample roadmap:

~~~mermaid
flowchart TD
    A["Inventory OS, kernel, runtime, and agents"] --> B["Cross-check official support milestones"]
    B --> C["Identify workloads near EOL or unsupported"]
    C --> D["Verify compatibility matrix"]
    D --> E["Choose in-place upgrade or image replacement"]
    E --> F["Build image / test environment"]
    F --> G["Test application, drivers, backups, and security"]
    G --> H{"Criteria met?"}
    H -- "No" --> I["Fix dependencies or file time-bound exception"]
    I --> F
    H -- "Yes" --> J["Deploy via rings / rolling"]
    J --> K["Verify and update inventory"]
    K --> L["Retire old images and OS"]
~~~

### 16.1. Compatibility Testing

Testing should cover:

- Boot and shutdown.
- Networking, DNS, routes, and firewalls.
- Storage mounts, filesystems, and I/O.
- GPU/NIC/storage drivers.
- Runtimes, libraries, and applications.
- Workload identity and cloud service permissions.
- Monitoring, logging, backups, and restores.
- Performance under representative load.
- Failover, reboots, and failure recovery.

### 16.2. Rollback Planning

Rollback does not always mean downgrading the OS to an earlier version. Once database schemas, filesystems, or data formats change, older hosts may not read newer data. Determine:

- Can traffic shift back to old instances?
- Is data compatible between old and new versions?
- Can snapshots/backups be restored?
- Should old images be retained temporarily?
- When must rollback stop in favor of restoring from backup?

With immutable deployments, keeping the old host group during validation is helpful, provided shared data remains compatible and two versions do not write conflictingly.

## 17. Cloud Provider vs. Customer Responsibilities

In IaaS, cloud providers typically manage data centers, physical servers, firmware, hypervisors, and parts of underlying networking/storage. Customers typically manage guest OS, kernels, packages, applications, identities, guest networking, and data.

In PaaS or managed compute services, the provider may assume greater responsibility for the underlying OS and runtime. Still, customers must track service-provided runtime versions, deprecation deadlines, compatibility notices, and application upgrade requirements.

| Component | IaaS VM | Managed Compute / PaaS |
|---|---|---|
| Physical host and firmware | Typically provider-managed | Provider-managed |
| Hypervisor | Provider-managed | Provider-managed |
| Guest OS | Typically customer-managed | May be provider-managed or abstracted |
| Guest kernel | Typically customer-managed | Depends on service |
| Base runtime | Customer installs and patches if self-managed | Provider may manage partially |
| Application and dependencies | Customer-managed | Customer still manages code and in-scope dependencies |
| Data and access control | Customer-responsible | Customer-responsible |

Always check the responsibility model for each specific service. Never assume "running in the cloud" means the provider patches everything inside the VM.

## 18. Lifecycle Metrics and Reporting

A maintenance program needs metrics to measure compliance and risk. Useful metrics include:

| Metric | Interpretation |
|---|---|
| OS support coverage | Percentage of assets running supported versions |
| EOL exposure | Count of hosts past or nearing end of support |
| Patch compliance | Percentage of hosts meeting the patch baseline |
| Reboot pending | Count of hosts with installed kernel/updates awaiting required reboot |
| Agent coverage | Percentage of hosts with mandatory agents and valid heartbeats |
| Image freshness | Image age and time since last build/patch |
| Upgrade lead time | Time from detecting EOL to completing migration |
| Exception aging | Age of unresolved lifecycle exceptions |
| Patch failure rate | Percentage of hosts failing updates |

Do not optimize for a single metric. For instance, high patch compliance does not mean the system is safe if outdated images still provision new VMs or security agents are down.

## 19. Real-World Example: API Fleet Approaching OS End of Support

An enterprise runs 60 API VMs on an aging Linux LTS release. The OS still serves requests fine, but standard support ends in a few months. The fleet also includes monitoring agents, security agents, storage drivers, and a Java runtime.

The operations team executes:

1. Collect OS release, kernel, package, and agent versions across all 60 VMs.
2. Confirm end-of-support dates and extended support options.
3. Verify that the Java runtime, TLS libraries, agents, and drivers support the new LTS distro.
4. Build a new golden image with the approved kernel and agents.
5. Run integration tests, vulnerability scans, backup/restore, and representative load tests.
6. Launch a small canary group behind the load balancer.
7. Monitor error rates, latency, CPU, memory, disk, and agent logs.
8. Rolling-replace the remaining VM groups.
9. Update launch templates and pipelines so no new VMs spawn from the old image.
10. Deprecate the old image, track exceptions, and delete it after the retention period.

Upgrading the 60 running VMs while forgetting the launch template would cause the next scale-out to spawn VMs from the obsolete image. Replacing images without checking agents and drivers could leave new hosts booting without monitoring or backup coverage. Lifecycle management must cover both running hosts and provisioning sources.

## 20. Common Mistakes

- **Tracking only the OS name:** omits release, build, edition, and support channel.
- **Checking only kernel version:** misses package releases and backported patches.
- **Assuming LTS means indefinite support:** ignores support end dates and subscription terms.
- **Installing a new kernel without rebooting:** the host still runs the old kernel without reboot-required fixes.
- **Upgrading kernels without checking drivers:** can break networking, storage, or GPU access.
- **Forgetting third-party agents:** newer OS versions may break backup, EDR, or monitoring compatibility.
- **Updating only running VMs:** stale images or launch templates continue spawning outdated hosts.
- **Rebooting the entire fleet at once:** risks capacity exhaustion or losing quorum.
- **Relying on live patching for all updates:** certain changes still require reboots.
- **Never testing rollback:** newer data or schemas may be incompatible with older hosts.
- **No owner for EOL exceptions:** unsupported hosts linger indefinitely without a remediation plan.
- **Treating patch compliance as the sole proof:** overlooks dead agents, stale images, and unsupported applications.

## 21. Recommended Lifecycle Operations Workflow

Apply the following workflow for each OS family and workload:

1. **Inventory:** collect assets, OS, kernels, runtimes, drivers, agents, and images.
2. **Lifecycle mapping:** compare versions against official support calendars.
3. **Risk assessment:** prioritize by EOL proximity, vulnerabilities, exposure, and criticality.
4. **Compatibility review:** confirm target OS supports applications, drivers, and agents.
5. **Patch/upgrade design:** choose in-place updates, live patching, reboots, or image replacement.
6. **Test:** validate functionality, performance, backup/restore, and recovery.
7. **Rollout:** deploy via rings or rolling maintenance.
8. **Verification:** verify running kernel, build, agent heartbeats, and application health.
9. **Inventory update:** record new versions, maintenance dates, and exceptions.
10. **Retirement:** remove old OS/images/agents and clean up obsolete configurations.

## 22. Key Takeaways

The lifecycles of OS, kernels, drivers, runtimes, and agents do not end at the same time. Keeping compute secure requires complete inventory, tracking official support milestones, checking compatibility, patching by risk, and scheduling controlled reboots or host replacements.

Live patching reduces disruption for certain kernel fixes but does not eliminate all reboot requirements. In-place upgrades suit some hard-to-recreate hosts; replacing instances from fresh images standardizes fleets and curbs drift where infrastructure supports it. Update running VMs, golden images, launch templates, agents, and pipelines together so outdated foundations are never re-deployed. Lifecycle management is a continuous activity throughout a workload's lifetime in the cloud.
