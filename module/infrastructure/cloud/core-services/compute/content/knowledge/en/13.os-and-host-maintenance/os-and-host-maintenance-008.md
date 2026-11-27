# Verifying Health and Recovering After a Failed Update

Updating the operating system, kernel, drivers, or base libraries gives servers security patches and improves stability. However, a package installer exiting with a zero return code does not prove the server is healthy. Services may fail to restart, a new kernel may be incompatible with a driver, partitions may fill up, network connectivity may shift, or the application may fail only under live traffic.

In cloud environments, a single failing host can also impact autoscaling groups, container clusters, load balancers, and dependent services. Therefore, verify across multiple layers, compare against pre-update baselines, halt rollouts at early signs of trouble, and keep tested recovery options ready.

This lesson explains how to verify host health after an update and select the right recovery path. After this lesson, you will be able to:

- Establish a baseline and identify metrics to check before and after updates.
- Inspect cloud instance state, OS, kernel, services, networking, storage, and applications.
- Distinguish package installation failures, boot failures, driver failures, and load-dependent failures.
- Decide whether to proceed, pause, roll back, or replace a host.
- Recover using a previous kernel, package version, snapshot, backup, or known-good image.
- Record outcomes, verify post-recovery state, and safely return the host to service.

## 1. Why Verify After an Update?

An update cycle can alter multiple interconnected components:

- Kernel and kernel modules, affecting network, storage, GPU, and virtual device drivers.
- System libraries such as glibc, OpenSSL, or application runtimes.
- Background services, systemd units, monitoring agents, security agents, and configuration managers.
- Firmware or drivers supplied via provider images or packages.
- Boot components such as initramfs, bootloader, and mount configurations.

Failures can surface immediately during installation, on the next reboot, or only when the application takes traffic. For instance, a service may show active while failing to bind its port; a host may respond to ping while DNS fails; a filesystem may remount read-only after an I/O error; or a new GPU driver may stop inference processes from initializing.

Distinguish three distinct states:

1. **Installation complete:** the package manager and update tool report no unhandled errors.
2. **Host healthy:** the machine boots cleanly, and resources and background services function properly.
3. **Workload healthy:** the application passes functional checks, SLOs, and representative load.

Only the third state permits concluding the host is ready to return to full service.

## 2. Preparing a Pre-Update Baseline

A baseline captures normal operating state prior to changes. Without a baseline, operations teams struggle to separate newly introduced failures from pre-existing issues.

Before updating, record:

- OS, kernel, critical package, driver, and runtime versions.
- Uptime, reboot-required state, running services, and failed services.
- CPU, memory, swap, filesystem usage, inodes, and I/O health.
- IP addresses, routes, DNS, firewalls, security groups, and listening service ports.
- Recent error logs, monitoring alerts, application error rates, latency, and throughput.
- Cluster, load balancer, replica, queue, and dependency health.
- Latest snapshot or backup, expected recovery time, and accountable owner.

Useful Linux baseline commands:

~~~bash
date -Is
hostnamectl
uname -a
uptime
systemctl --failed
df -h
df -i
free -h
ip addr
ip route
ss -lntup
~~~

To retain records for a maintenance run, capture command output into your change management system or a controlled log store. Never store the baseline solely on a disk that could fail or be replaced.

### Identifying Scope and Blast Radius

Before starting, know the host's group and role:

- Is it a standalone machine or a cluster node?
- Does it take traffic directly or behind a load balancer?
- Does it hold stateful data, local volumes, or unprocessed queues?
- Are standby nodes and enough capacity available when removing the host from the cluster?
- Does it depend on custom kernel modules, GPUs, storage drivers, or specialized agents?

For critical services, test updates in staging or a canary group first. Phased small-batch rollouts catch defects before the entire fleet is impacted.

## 3. Layered Health Verification Workflow

Verify from the infrastructure layer up to the application layer. A healthy lower layer does not guarantee the layer above is healthy.

### Layer 1: Infrastructure and Instance State

In the cloud console or API, verify:

- The instance is `running` with no active host maintenance events or virtual hardware faults.
- Both system status checks and instance status checks pass where the platform provides them.
- Boot and data volumes are attached properly with no capacity warnings or I/O errors.
- Network interfaces, IP addresses, routes, and security groups remain accurate.
- Load balancers or platform health checks recognize the instance in the expected state.

If the console shows the instance `running` but you cannot connect, check the serial console, boot diagnostics, or rescue console supported by your provider. `running` only indicates the VM is allocated and powered on; it does not prove the OS finished booting.

### Layer 2: Operating System and Kernel

Check the running kernel, boot time, kernel errors, and reboot status:

~~~bash
uname -r
uptime -s
who -b
sudo journalctl -b -p err
sudo dmesg --level=err,warn
~~~

Compare the running kernel against the target post-update version. If the new kernel package is installed but the host has not rebooted, `uname -r` still reports the old kernel. If it rebooted yet fell back to the old kernel, inspect the bootloader, initramfs, GRUB configuration, and boot logs.

On Ubuntu/Debian, the following file indicates whether the system requires a reboot:

~~~bash
test -f /var/run/reboot-required && cat /var/run/reboot-required
~~~

On some RHEL-based systems, tools from `dnf-utils` or `dnf-plugins-core` check for packages/processes needing restarts, for example:

~~~bash
sudo needs-restarting -r
~~~

Commands and supporting packages vary by distribution version. Consult your OS documentation.

### Layer 3: Services and Processes

List failed units and inspect critical services:

~~~bash
systemctl --failed
systemctl status sshd
systemctl status orders-api
journalctl -u orders-api -b --no-pager -n 200
~~~

The service name may be **ssh** instead of **sshd** depending on the distribution. For each service, verify:

- Is the unit active and stable, or crash-looping?
- Is the process running the expected version and startup flags?
- Are sockets listening on the expected addresses and ports?
- Were config files read cleanly with valid file permissions?
- Are dependencies such as databases, DNS, message brokers, and secret managers reachable?

An **active (running)** state is only one signal. Combine it with logs, sockets, and functional service checks.

### Layer 4: CPU, Memory, and Storage

Post-update, a process may leak memory, spike CPU, or fill filesystems with logs, caches, or temp files. Check:

~~~bash
free -h
vmstat 1 5
df -h
df -i
lsblk
findmnt
sudo journalctl -k -b | grep -Ei 'oom|I/O error|read-only|filesystem|nvme|scsi'
~~~

Watch for warning signs:

- Sharp drops in available memory or continuous swap usage.
- The OOM killer terminating critical processes.
- Filesystems or inodes approaching exhaustion.
- Filesystems unexpectedly remounted read-only.
- Kernel-logged I/O errors, timeouts, or device resets.
- Markedly higher read/write latency compared to baseline.

Do not look solely at CPU or RAM percentages. A host with low CPU can still stall applications if blocked on I/O or network waits.

### Layer 5: Networking and Name Resolution

Verify addresses, routes, DNS, and listening ports:

~~~bash
ip addr
ip route
getent hosts database.internal
resolvectl status
ss -lntup
~~~

`resolvectl` is not present on every distribution; inspect resolvers in `/etc/resolv.conf` or the appropriate tool. From the host under test, test connectivity to dependencies using the actual protocol and port. For example:

~~~bash
curl -fsS --max-time 5 http://127.0.0.1:8080/health
nc -vz database.internal 5432
~~~

Do not conclude networking is healthy merely because ping succeeds. ICMP may be blocked or permitted while TCP, TLS, DNS, or routes to real services are broken.

### Layer 6: Application and Dependencies

Check health endpoints, smoke tests, and representative transactions. Verify:

- The application returns expected status codes within timeout bounds.
- Sign-ins, queries, and core business actions still succeed.
- Connections to databases, caches, queues, object storage, and external services work.
- Logs and traces show no abnormal error spikes.
- The runtime, native libraries, and drivers loaded by the app match expectations.

For multi-replica applications, test individual instances as well as the aggregate load-balanced endpoint. A shared endpoint may return 200 OK thanks to other healthy nodes even while a newly updated node is failing.

### Layer 7: Security and Management Agents

Confirm monitoring agents, endpoint protection, log forwarders, backup agents, and configuration management tools still work. Check:

- Agents reconnected to their control planes and send heartbeats.
- Firewall rules, SELinux/AppArmor policies, and file permissions were not unexpectedly altered.
- Audit logs continue writing and forwarding to central storage.
- No unplanned accounts, SSH keys, services, or open ports appeared.
- Intended security patches are installed and the running versions are accurate.

## 4. Evaluating Metrics Before and After Updates

A single point-in-time check can miss latent issues. Observe the host over an interval matching your workload's traffic cycle.

| Metric Group | What to Compare | Anomaly Indicators |
|---|---|---|
| Availability | Health check pass rate, ready instance count | Nodes repeatedly ejected from pool |
| Error rate | HTTP 5xx, application errors, connection errors | Rising compared to baseline or SLO |
| Latency | p50, p95, p99 | Latency climbing despite unchanged throughput |
| Saturation | CPU, memory, swap, I/O, network | Resources hitting limits or queues backing up |
| Stability | Restart count, kernel errors, OOMs | Repeated process restarts or kernel warnings |
| Dependencies | DB pools, DNS, queue lag, storage errors | Rising timeouts or retries |
| Security telemetry | Agent heartbeats, audit events, policy state | Missing logs or silent agents |

Do not apply one global threshold to every host. Base thresholds on SLOs, load profiles, and baselines. For instance, 85% CPU may be normal for a batch worker yet dangerous for an interactive service already near latency limits.

A straightforward decision rule:

- **Continue rollout:** all critical checks pass, metrics stay within SLOs, and no negative trends appear.
- **Pause rollout:** an ambiguous check, degrading metrics, or a new error with unclear blast radius.
- **Roll back or replace host:** service-impacting failures, signs of data loss, boot failures, or inability to recover within the allowed window.

## 5. Verifying the Package Manager Post-Update

Package managers can report partial failures, unconfigured dependencies, or interrupted transactions. Inspect according to your OS.

### Ubuntu and Debian

~~~bash
sudo dpkg --audit
sudo apt-get check
sudo apt list --upgradable
~~~

`dpkg --audit` spots packages left in an incomplete installation state; `apt-get check` validates dependencies. If packages remain half-configured, read logs and diagnose the root cause before running repair commands. Never automate dependency-repair commands across the entire fleet without testing first.

Logs typically reside in:

~~~text
/var/log/apt/history.log
/var/log/apt/term.log
/var/log/dpkg.log
~~~

### RHEL, Rocky Linux, AlmaLinux, and Fedora

~~~bash
sudo dnf check
sudo dnf history
sudo rpm -qa --last | head -n 20
~~~

You can inspect details of a specific transaction:

~~~bash
sudo dnf history info <transaction-id>
~~~

DNF history can support undoing or rolling back certain transactions, though not all changes are safely reversible. Packages removed from repositories, scriptlets with side effects, migrated data, or out-of-band edits can leave an undo incomplete. Inspect the transaction, verify dependencies, and test in a matching environment before applying.

## 6. Recovering When an Update Causes Failures

Select a recovery path based on the failing layer and severity. No single rollback command fits every scenario.

### Scenario A: Host Boots, Single Service Fails

1. Keep the host out of the load balancer or reduce traffic to it.
2. Inspect service logs, dependencies, and configuration.
3. Identify the package or change that triggered the failure.
4. Restore the known-good configuration or package version per OS procedure.
5. Restart the affected service and run smoke tests.
6. Return the host to the pool only once readiness and metrics pass.

If a configuration edit caused the error, prefer restoring from version control or a backup. If a package caused it, check whether the prior version remains in the repository/cache and whether dependencies align. Avoid arbitrarily downgrading core libraries, as that can break other packages.

### Scenario B: New Kernel Fails to Boot or Driver Breaks

Many distributions retain prior kernels in the bootloader. If the new kernel fails to boot or a critical module fails to load:

1. Use the serial console or boot diagnostics to inspect the error.
2. When available, select the previous known-good kernel from the bootloader menu.
3. Verify the host operates stably on the old kernel, drivers, and filesystems.
4. Collect logs and keep the broken kernel for investigation; do not immediately delete the old kernel.
5. Build a tested image or updated package before retrying.

On some virtual machines, physical-style boot menus or consoles are not exposed. Know in advance how to enter rescue mode, detach the boot volume, or boot from your provider's rescue image. If Secure Boot is enabled, out-of-tree kernel modules may need signing with the proper key.

### Scenario C: Host Unreachable After Reboot

Do not reboot repeatedly, as that can destroy evidence or worsen state. Proceed in order:

1. Check instance status and system checks in the cloud console.
2. Open the serial console or boot logs if available.
3. Identify whether boot stalled at the bootloader, initramfs, filesystem mount, or network services.
4. If possible, enter rescue mode to inspect the boot volume, filesystems, fstab, initramfs, and logs.
5. If a quick fix isn't viable, restore the boot volume from snapshot or launch a replacement from a known-good image.
6. Reattach persistent data per procedure, verifying ownership and consistency before opening traffic.

Before detaching or attaching volumes, follow platform procedures and ensure the filesystem is no longer mounted read-write on the old host. For actively writing filesystems or databases, follow clean shutdown or consistent snapshot steps.

### Scenario D: Host Is Healthy, Application Degrades

If the OS and background services look fine while the application fails, inspect runtime compatibility, native libraries, TLS, database drivers, sidecar agents, and remote dependencies. You can roll back just the application artifact if OS changes were not the cause. If multiple nodes fail after updating a shared library, halt the rollout and consider replacing hosts from the pre-update image.

## 7. Recovery Options and Limitations

| Option | When to Use | Advantages | Limitations / Risks |
|---|---|---|---|
| Restart service | Process failed while OS is healthy | Fast, minimal change | Cannot fix config errors or broken dependencies |
| Restore configuration | Config file was misconfigured | Exact reversal if a baseline copy exists | Must identify changed files and verify secrets |
| Downgrade package | New package broke something and old version is available | Small scope of change | Dependencies and install scripts may not reverse cleanly |
| Boot previous kernel | New kernel or module failed | Restores bootability quickly | Doesn't fix user-space bugs; old kernel may lack patches |
| Snapshot/restore volume | Boot volume or filesystem corrupted | Restores volume state at snapshot time | Loses post-snapshot writes; consistency must be verified |
| Backup/restore data | Data lost or corrupted | Restores data to a point in time | RTO/RPO depend on backups and restore workflow |
| Replace instance from good image | Host won't boot or drifted badly | Fast recreation, predictable state | Requires capacity, externalized data, and managed config |
| Rolling fleet rebuild | Outage spans multiple nodes | Returns entire group to standard state | Needs orchestration, monitoring, and spare capacity |

### Snapshots Do Not Replace Backups

A boot volume snapshot helps revert to pre-update state, but is not automatically a complete backup. Snapshots may only be crash-consistent; actively writing applications may need filesystem freezing or quiescing for consistency. Snapshots in the same region or account also may not protect against regional outages or accidental deletion.

For databases and business data, follow backup policies, verify restore capability, and define RPO (maximum acceptable data loss) and RTO (target recovery time). Snapshots and backups require retention, access controls, and cross-fault-domain copies when service requirements demand them.

## 8. Controlled Recovery Workflow

A standard workflow divides into clear phases:

~~~mermaid
flowchart TD
    A["Detect post-update failure"] --> B["Isolate node from traffic"]
    B --> C["Collect logs, state, and blast radius"]
    C --> D{"Is host still booting and accessible?"}
    D -- "Yes" --> E["Inspect OS, packages, services, network, and app"]
    D -- "No" --> F["Console / rescue mode / boot volume"]
    E --> G{"Can it be safely fixed within RTO?"}
    F --> H{"Can boot or volume be recovered?"}
    G -- "Yes" --> I["Fix config, service, or roll back package/kernel"]
    G -- "No" --> J["Replace from known-good image and attach data"]
    H -- "Yes" --> I
    H -- "No" --> J
    I --> K["Run health checks and smoke tests"]
    J --> K
    K --> L{"SLOs met and data consistent?"}
    L -- "No" --> M["Keep isolated, continue recovery/escalate"]
    L -- "Yes" --> N["Return node to pool under control"]
    N --> O["Monitor post-recovery and record"]
~~~

Follow steps in sequence:

1. **Isolate:** mark the node unhealthy, stop new traffic, and protect data.
2. **Assess:** determine failure time, recently deployed changes, affected node count, and service impact.
3. **Preserve evidence:** save logs, console output, package transactions, kernel versions, and metrics.
4. **Choose path:** fix in place, boot prior kernel, restore volume, restore data, or replace instance.
5. **Verify:** re-run checks across all layers and execute business smoke tests.
6. **Return to service:** raise traffic only once criteria pass; start with a small slice where appropriate.
7. **Monitor:** observe across a sufficient window, check for recurring errors, and document results.

## 9. Canary and Rolling Updates to Limit Blast Radius

For multi-host fleets, never update all nodes simultaneously if availability is required. A common approach:

1. Update a test machine or representative canary group.
2. Reboot if needed; thoroughly verify OS and workload.
3. Monitor through a representative traffic cycle.
4. If criteria pass, update the next small batch.
5. Maintain enough ready nodes and capacity to carry the load.
6. Halt rollout immediately if new errors, latency spikes, or health check failures appear.

For instance, a 10-node cluster needs at least 8 healthy nodes. Never pull 3 nodes for maintenance at once without spare capacity. Update one node or pair at a time, waiting for refreshed nodes to become ready before proceeding. Batch size must reflect live load, autoscaling responsiveness, and startup time.

In Kubernetes, node draining must account for PodDisruptionBudgets, workloads with local storage, DaemonSets, and graceful termination periods. Draining moves Pods, but does not automatically guarantee sufficient cluster capacity or protected local data. In VM scale sets or autoscaling groups, replace instances via instance refresh once the new image is tested.

## 10. Real-World Example: Kernel Update Prevents API Startup

Suppose a team runs an order API on 6 VMs behind a load balancer. After updating the kernel and rebooting one VM, health checks fail. The other 5 VMs remain healthy.

**Step 1: Isolate the failing node.** The load balancer marks the VM unhealthy; the team confirms the remaining 5 VMs handle traffic and pauses batch rollout.

**Step 2: Check infrastructure.** The console shows the VM `running`, yet instance status checks fail. Opening the serial console shows boot stalling right after loading initramfs.

**Step 3: Check the kernel.** Logs show the storage driver module failed to load on the new kernel. Instead of rebooting repeatedly, the team uses the boot menu or rescue console to select the prior kernel.

**Step 4: Verify on the old kernel.** The VM boots cleanly, volumes mount properly, and no filesystem is read-only. The team verifies services, port 8080, database connectivity, and the health endpoint.

**Step 5: Return the node.** After smoke tests and an observation window, the VM rejoins the load balancer with limited traffic, then returns to the full pool once metrics pass.

**Step 6: Investigate and fix the image.** The team archives logs, package transactions, and kernel versions; identifies a compatible driver; tests in staging; and builds a new image. Remaining VMs are updated only after a fresh canary passes checks.

This example highlights the need to verify bootability, drivers, volumes, and applications. Instance `running` status or a successful package install command does not prove an update is safe.

## 11. Runbooks and Information to Record

Every recovery should produce an auditable record:

| Field | Details to Record |
|---|---|
| Incident/change ID | Related incident or change ticket ID |
| Host/instance | Hostname, instance ID, region/zone, and role |
| Timestamps | Update start, reboot, failure detection, recovery, and completion |
| Versions | OS, kernel, packages, drivers, and image before/after |
| Symptoms | Health checks, logs, user errors, and anomalous metrics |
| Blast radius | Affected nodes, services, users, and data |
| Actions | Isolation, rollback, restore, replacement, and operator |
| Verification results | OS, service, network, application, security telemetry |
| Data | Snapshot/backup used, timestamp, and verification result |
| Decision | Resume rollout, halt, roll back, or close incident |

Never write private keys, passwords, tokens, or sensitive data into runbooks. When saving logs for investigation, enforce read permissions, retention limits, and storage independent of the failing host.

Post-incident, conduct a post-incident review: determine root cause, why canaries or pre-release checks missed it, detection/recovery times, and preventive actions. Update runbooks, health check criteria, image builds, or rollout procedures based on findings.

## 12. Common Mistakes

1. **Checking only the package manager exit code:** packages install cleanly while services or drivers still break.
2. **Skipping baseline comparisons:** easy to miss elevated latency, memory leaks, or new error logs.
3. **Rebooting repeatedly when a host fails to come up:** destroys evidence without fixing root cause.
4. **Bulk-downgrading without identifying the culprit package:** introduces further dependency conflicts.
5. **Restoring snapshots without checking consistency:** can revert actively written data into an inconsistent state.
6. **Returning nodes to traffic too early:** defects may emerge only under live load.
7. **Updating the entire fleet at once:** maximizes blast radius and eliminates spare capacity.
8. **Deleting old kernels or good images too soon:** removes the recovery path if a new kernel fails to boot.
9. **Ignoring security and monitoring agents:** the app may serve requests while flying blind or unprotected.
10. **Failing to record versions and actions:** makes reproducing and fixing future incidents much harder.

## 13. Post-Update Verification Checklist

- [ ] Update transaction left no broken or half-configured packages.
- [ ] Running kernel and drivers match expected versions.
- [ ] Host boots cleanly and cloud status checks pass.
- [ ] No unexplained new kernel errors, OOMs, or I/O errors appeared.
- [ ] Filesystems, inodes, memory, CPU, and I/O sit within normal bounds.
- [ ] Routes, DNS, firewalls, and service ports operate properly.
- [ ] Critical systemd units are active and not crash-looping.
- [ ] Applications, dependencies, and business smoke tests pass.
- [ ] Latency, error rates, and throughput sit within SLOs.
- [ ] Monitoring, security, backup, and log-forwarding agents report heartbeats.
- [ ] Snapshots/backups and rollback options remain viable.
- [ ] Node returns to traffic only after checks and observation window pass.
- [ ] Outcomes, versions, and actions logged in the change/incident record.

## 14. Practice Exercise

A 12-VM cluster runs a payment processing service. Every VM received a kernel and TLS library update in the same batch. After rebooting, 2 VMs fail health checks, 1 VM shows doubled p95 latency, and 9 VMs behave normally. The cluster requires at least 9 ready VMs.

1. What first action should the team take to keep the service stable?
2. List the verification layers to inspect on the two unhealthy VMs.
3. For the high-latency VM, which metrics should be collected to distinguish CPU, memory, I/O, network, and TLS issues?
4. If the new kernel fails to boot on the two VMs, propose a recovery path and criteria before returning them to the pool.
5. Why should the team halt rollout on the remaining 9 VMs (if any weren't finalized) until root cause is understood?

Hint: isolate the two failing VMs and assess remaining capacity before making further changes. Check cloud status, boot logs, kernel/modules, filesystems, services, networking, and application health. For the high-latency VM, compare p50/p95/p99, error rates, CPU, memory, swap, I/O wait, network retransmits, and TLS logs against the baseline. If the new kernel won't boot, fall back to the prior kernel or follow rescue/restore procedures, verify thoroughly, and then rejoin the pool. Halt the rollout to avoid expanding the blast radius when the root cause may lie in a shared kernel or library.

## Conclusion

Post-update verification must progress from infrastructure, OS, kernel, services, resources, networking, and applications through to security and monitoring agents. Baselines and SLOs expose regressions; canary and batched rollouts contain blast radius. When incidents strike, isolate the node, preserve evidence, choose the proper recovery path, and return hosts to service only after both health and data integrity pass. Snapshots, backups, previous kernels, and known-good images are complementary recovery layers, each with limitations that must be tested in advance.
