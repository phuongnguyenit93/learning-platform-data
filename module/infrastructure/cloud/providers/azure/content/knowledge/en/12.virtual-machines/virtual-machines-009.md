# Patching and Update Management with Azure Update Manager

When an application runs on Azure Virtual Machines (VMs), operators remain responsible for updating the operating system and software components within their management scope. Creating a VM in a subscription, placing it in a virtual network (VNet), enabling encryption, and configuring Network Security Groups (NSGs) **does not mean the VM is patched against newly discovered OS vulnerabilities**. Delaying updates too long exposes VMs to security risks; updating without controls can cause VMs to reboot during peak traffic, lose database connectivity, or run incompatible package versions.

**Azure Update Manager** (AUM) assesses and orchestrates OS update installations across supported machines, including Azure VMs and servers connected via **Azure Arc**. The service provides patch assessment insights, on-demand installation capabilities, and maintenance scheduling via corresponding Azure mechanisms. AUM **is not a universal repository hosting every patch**, **does not fix all application vulnerabilities**, and **does not guarantee zero downtime with a single switch**.

This lesson belongs to the **Azure Virtual Machines** chapter in the **CLOUD_PROVIDERS_AZURE** module. It connects subscription/resource group and Microsoft Entra ID concepts with VM infrastructure, virtual networking, data services, monitoring, security, and cost control for an Azure application system. The focus is building a verifiable patching process safe for real workloads rather than blindly clicking **Install updates**.

After this lesson, you will be able to:

- Explain *assessment*, *patch installation*, *maintenance window*, *reboot*, and *compliance* in Azure Update Manager.
- Distinguish guest OS patching from Azure host maintenance, application software patches, image/container updates, and vulnerability scanners.
- Design patch rollout rings across test, canary, and production groups with appropriate schedules and scopes.
- Perform on-demand assessments/installations, configure update schedules via the Azure interface, and verify results.
- Combine AUM with backups, health probes, Load Balancers, alerts, least-privilege permissions, and incident response workflows.
- Investigate cases where VMs fail to appear, fail to assess updates, fail installation, or require reboots.

## 1. Why Is a Centralized Patching Process Needed?

Suppose a company operates 40 VMs running Windows Server and Ubuntu across three subscriptions: development, testing, and production. Some VMs serve APIs, some run batch jobs, and others connect to on-premises systems over VPN/ExpressRoute. If admins sign into every VM to check and install updates manually:

- It is hard to tell which critical patches are missing across the fleet.
- It is hard to track which VMs succeeded, which failed, and who owns remediation.
- It is easy to patch multiple backends simultaneously, causing outages even behind a load balancer.
- Reboot-requiring patches may be postponed indefinitely or trigger outside maintenance hours.
- Powered-off VMs, network-isolated VMs, or end-of-support OSes can slip through the cracks.
- Audit and risk-governance evidence becomes difficult to compile.

AUM establishes a **centralized management plane** for assessing, grouping, scheduling, and tracking updates. Still, operations teams need policies for patch selection, validated update sources, compatibility testing, backup/rollback, and exception handling.

### Patching Is More Than Installing Packages

A complete patching cycle:

~~~mermaid
flowchart LR
    INVENTORY[Inventory VMs and owners] --> ASSESS[Assess updates]
    ASSESS --> RISK[Classify risk and prioritize]
    RISK --> TEST[Test / canary]
    TEST --> SCHED[Schedule, approve]
    SCHED --> INSTALL[Install updates]
    INSTALL --> REBOOT[Reboot if needed]
    REBOOT --> VERIFY[Verify OS and application]
    VERIFY --> REPORT[Reconcile, handle exceptions]
    REPORT --> ASSESS
~~~

An “installation succeeded” report only reflects the patching operation within its reported scope. Confirming a healthy service requires health probes, business transaction checks, application logs, and proof that data flows properly.

## 2. What Can and Cannot Azure Update Manager Manage?

| Scope | How Azure Update Manager supports it | What remains the ops team's responsibility |
|---|---|---|
| Supported Azure VM guest OS | Assess, install updates, schedule, and view history | Selecting policies, testing, reboots, workload validation |
| Eligible Azure Arc-enabled servers | Brings non-Azure machines into supported assessment/patching flows | Arc onboarding, networking, agents/extensions, licensing, update sources |
| Windows Update / WSUS and Linux repositories | Orchestrates through the OS's native update mechanism | Package sources, proxies, repositories, service health, GPOs |
| VM Scale Sets / autoscale architectures | Certain VM types/scenarios supported depending on mode | Checking orchestration mode, image updates, rolling upgrades, managed targets |
| Self-installed apps on VMs | Does not automatically resolve all app dependencies/CVEs | CI/CD, app package managers, restarts, regression tests |
| Container images, managed PaaS, managed DB engines | Does not replace each platform's native update flow | Image rebuild pipelines, AKS node/cluster upgrades, PaaS maintenance |
| Azure host, hypervisor, and datacenter infra | Not a customer tool to patch Azure-managed platform layers | Monitoring Azure maintenance advisories and SLA expectations |

The **Guest OS** is the OS inside the VM. The **Host OS/hypervisor** belongs to the underlying infrastructure. Azure manages most physical infrastructure under the shared responsibility model, while workload owners manage guest OS patching aside from specifically configured automatic platform-orchestrated mechanisms.

### Logical Architecture

~~~mermaid
flowchart TB
    ADMIN[Operations team] --> PORTAL[Azure Update Manager]
    PORTAL --> ASSESS[Assessment / Install]
    PORTAL --> MAINT[Maintenance configuration / Update schedule]
    ASSESS --> VM1[Azure VM Windows]
    ASSESS --> VM2[Azure VM Linux]
    ASSESS --> ARC[Azure Arc-enabled server]
    MAINT -. Selects schedule and scope .-> VM1
    MAINT -. Selects schedule and scope .-> VM2
    MAINT -. Selects schedule and scope .-> ARC
    VM1 --> WU[Windows Update / WSUS]
    VM2 --> REPO[apt / dnf / yum / zypper repository]
    ARC --> SOURCE[OS update source]
    PORTAL --> HISTORY[Run history and reports]
~~~

This diagram shows conceptual relationships. How AUM interacts with machines, extensions, and patch sources depends on machine type, OS, and service version; do not assume Azure Update Manager hosts installers for every product itself. Guest OS schedules integrate with **Azure Maintenance** components where supported.

## 3. Core Concepts to Distinguish

| Concept | Meaning | Practical example |
|---|---|---|
| **Patch assessment** | Scans for missing updates using OS/repository metadata | VM is missing 2 security updates and 1 critical update |
| **Periodic assessment** | Automated recurring assessment on configured, supported machines | Updated report generated on platform cadence |
| **On-demand assessment** | Manually triggered assessment at inspection time | Re-scan right before a patch window |
| **One-time update installation** | Ad-hoc update install without a recurring schedule | Applying an emergency CVE fix on a lab VM |
| **Scheduled patching** | Applying updates inside scheduled maintenance windows | Canary group Tuesday, production Thursday |
| **Maintenance configuration** | Resource defining schedule window, scope, and maintenance settings | Weekend window for a VM group |
| **Dynamic scoping** | Automatically selecting machines matching supported criteria | All production VMs of App X with matching tags |
| **Patch classification** | Update categories defined by OS and update source | Security, Critical, Updates, Update Rollups per OS |
| **Reboot setting** | Policy governing restarts per supported options | If required / Always / Never |
| **Patch compliance** | Assessment state regarding missing updates per policy and timestamp | “No missing patches detected in selected scope” |

**Assessment differs from installation.** A VM showing missing updates does not mean they are installed or scheduled. Conversely, a past successful install does not guarantee no new updates appeared after the last scan.

**Compliance is a point-in-time snapshot.** It depends on scan freshness, patch catalogs, repo/WSUS sync state, and policy scope; never treat a green status as a certificate that a VM has zero CVEs.

### Illustrative Timeline

~~~text
T1: Assessment → detects 4 missing updates
T2: Maintenance schedule → installs 3 updates matching filter; 1 excluded from scope
T3: Reboot → completes restart step if required
T4: Fresh assessment → re-verifies current state
T5: Health check → confirms application and dependencies work
~~~

Installing the three selected updates **does not make the fourth update disappear**. Track excluded patches, failed updates, and pending reboot states.

## 4. Azure VM Patch Orchestration Modes

Before scheduling with Update Manager, know **who controls when patches get installed**. Azure VMs offer different patching modes/settings by OS, image, and support status. UI labels in the portal or API may vary across versions.

| Orchestration mode | Concept | Operational notes |
|---|---|---|
| **OS-orchestrated / Automatic by OS** | The OS and internal update policies decide timing | Windows Update/GPO, `unattended-upgrades`, or OS timers can affect timing |
| **Azure-orchestrated / Automatic by platform** | Azure platform orchestrates guest OS updates where VM type/config supports it | Uses platform safety controls; do not equate with customer-defined schedules |
| **Customer Managed Schedules** | Customer defines maintenance windows and Azure Update Manager orchestrates installs | Requires matching patch orchestration, OS/image support, and maintenance configuration |
| **Manual** | Workload owner controls installs, optionally using custom tools or on-demand flows | Avoid running uncoordinated internal automation alongside another patch schedule |

**A VM should never be subject to two competing, uncoordinated patching/reboot engines.** For example, enabling Windows Server automatic updates via Group Policy while also attaching an AUM schedule can trigger unexpected installs. On Linux, inspect `unattended-upgrades` or distro auto-update timers.

### Picking a Mode by Goal

- If a sensitive workload requires **fixed maintenance windows**, evaluate **Customer Managed Schedules** with maintenance configurations and Azure-supported prerequisites.
- If a workload tolerates platform-managed rollout cadence, inspect **Azure-orchestrated** behavior and safe-deployment controls before choosing it.
- If your team operates its own patch engine, standardize on one orchestration source and govern it under change control.

Never change patch mode on a production VM without verifying compatibility, existing OS tasks, rollback plans, and schedule impact. **Reconcile the mode shown in the Azure Portal with actual in-guest configuration**, especially after migrations or IaC changes.

## 5. Prerequisites: VM, OS, Permissions, Agents, and Networking

Before installing patches, verify machines can be managed and can reach updates.

### 5.1. Azure VMs and Azure Arc

Azure VMs must use a supported image/OS, be in a scannable state, and have supported guest orchestration components. Operations may rely on the **VM agent / patch extension** or equivalent platform integration; inspect extension status whenever assessment/installation fails.

For non-Azure machines, **Azure Arc-enabled Servers** must be onboarded and actively connected before using supported Update Manager features. Arc servers carry distinct OS, connectivity, networking, agent/extension, and licensing/cost constraints; simply having a hostname record in Azure does not make it patchable.

### 5.2. Which Update Sources Do Windows and Linux Use?

| Operating system | Common update sources | Common failure causes |
|---|---|---|
| Windows Server | Windows Update or WSUS per org policy | Unreachable WSUS, GPO conflicts, broken Windows Update Agent, pending reboot |
| Ubuntu / Debian | APT repositories and distro update policies | Unreachable repo, stale cache, `apt`/`dpkg` locks, EOL release |
| RHEL and RPM distros | DNF/YUM with matching subscriptions/repos | Repo entitlement issues, mirror/proxy errors, dependency conflicts |
| SUSE and similar distros | Zypper / configured repositories | Invalid repo, entitlement, dependency, or metadata errors |

Update Manager **uses the OS's configured update source**—it cannot supply a patch if your repository or WSUS has not published or approved it. On Linux, classifications like Security/Critical rely on distro metadata, and not all distros expose classifications matching Windows. Always validate on your exact distribution and version.

### 5.3. Required Network Connectivity

For VMs inside private VNets or hub-spoke topologies:

1. Machines and extensions/agents must reach required **Azure control/monitoring endpoints**.
2. The guest OS must reach **Windows Update/WSUS or package repositories** as configured; many repositories sit outside Azure.
3. Firewalls, NSGs, proxies, and User Defined Routes must not block required flows.
4. DNS must resolve service endpoints, repositories, and proxy servers.
5. Machines need enough disk space, CPU/RAM, and uptime to complete scans and installs.

**Having a Private Endpoint to Storage or a private VM IP does not mean the VM can automatically reach Windows Update.** If forced tunneling sends all outbound traffic through Azure Firewall or on-premises, network teams must allow the exact destinations/ports and configure DNS. Never open unrestricted Internet access from every VM just to fix one repo error.

### 5.4. Azure RBAC Permissions

Separate at least three permission tiers:

- **Viewers:** inspect patch posture/assessment and installation history.
- **Patch operators:** assess and install updates on assigned machine groups and manage maintenance assignments/schedules.
- **Platform administrators:** manage policies, RBAC, subscriptions, networking, and shared configurations.

Use built-in or custom roles scoped strictly to required Update Manager, Azure Compute, Azure Maintenance, and Azure Arc actions at supported scopes; never grant subscription-wide **Owner** to someone who only installs patches. Verify permissions both to create maintenance configurations **and** to assign them to VMs or create dynamic scopes.

## 6. Assessment: From “Missing” to Patching Decisions

### 6.1. On-Demand Assessment

An Azure Portal workflow:

1. Open **Azure Update Manager** or the VM's Updates blade.
2. Filter by subscription, resource group, region, or machine.
3. Inspect the machine list, support status, and last assessment timestamp.
4. Trigger **Check for updates / Assess updates** on authorized VMs.
5. Wait for completion and review **Available updates**, classifications, pending reboot state, and any errors.
6. Record the report as a pre-change baseline.

Menu names can shift across Azure Portal versions. What matters is selecting the exact **VM resource ID**—never rely solely on display name, since two subscriptions can have identically named VMs.

### 6.2. How to Read Assessment Results

Example for a Windows VM:

| Observed field | Illustrative value | Operational question |
|---|---|---|
| Machine | `vm-orders-prod-01` | Right subscription and owner? |
| Last assessed | 2026-11-20 09:00 UTC | Is the scan fresh enough? |
| Critical | 1 | Active exploit or elevated urgency? |
| Security | 3 | Which updates need compatibility testing? |
| Update Rollups / Updates | 2 | Within current policy scope? |
| Pending reboot | Yes | Still waiting on a reboot from an earlier install? |
| Assessment status | Succeeded | Scan succeeded—does not mean patches are installed |

Never select patches by classification alone. Combine severity, exploitability, affected assets, compliance mandates, machine role, and vendor advisory urgency.

### 6.3. Periodic Assessment

Periodic assessment refreshes patch posture automatically on supported machines. Refresh cadence and availability depend on service policies, VM uptime, agent health, and network connectivity. **Do not treat periodic assessment as a real-time clock**: results can lag or go stale on newly deployed, stopped, or disconnected VMs.

For urgent CVEs, run an on-demand assessment or inspect OS update sources directly per runbook rather than waiting for dashboards to refresh.

## 7. Selecting Patch Classifications, Include/Exclude Rules, and Policies

Installations typically filter patches by **classifications** or **package/KB identifiers**, subject to platform support. Remember that “Security” on Linux does not always map 1:1 to Windows categories.

| Policy | Example | Risk |
|---|---|---|
| Security + Critical | Production VMs prioritizing security/critical updates | May miss necessary fixes if distro repos omit classifications |
| Explicit include | Selecting only specific KBs/packages for emergency remediation | Easy to miss dependencies or superseding updates |
| Explicit exclude | Deferring a patch with a known compatibility bug plus an expiry date | Prolonged exclusions leave vulnerabilities exposed |
| All applicable updates | Suitable for labs or tightly controlled hosts | May pull functional or kernel changes outside planned scope |

On Windows, filters typically align with Windows Update/WSUS taxonomy such as Critical, Security, Update Rollups, or Updates. On Linux, verify how your distro populates severity/classification metadata and how Update Manager maps it; where metadata lacks precision, build policies around specific repos or package lists.

**Never assume entering a CVE ID into Update Manager installs “just that one CVE.”** An advisory may span multiple packages/KBs, dependencies, and superseding updates. Identify exact target updates/packages from trusted advisories and verify outcomes post-install.

### Exception Policy

When deferring a patch due to an application conflict, document:

- Affected update/package or KB, OS, and VM/group.
- Business justification and unmitigated risk level.
- Approver, exception expiration date, and compensating controls.
- Plan to retest or upgrade the application.

Never treat `exclude` as a permanent switch disabling all security updates on a critical server.

## 8. One-Time Patch Installation (On-Demand)

One-time installation fits patching a lab VM, applying an approved emergency CVE fix, or validating before rolling out recurring schedules. **Installing patches modifies the operating system**—it can restart services, update kernels, or require reboots. Never test CLI syntax for the first time on production machines.

### 8.1. Steps via the Azure Portal

1. Select the VM in the target subscription/resource group and open **Azure Update Manager**.
2. Check the latest assessment and `Pending reboot` state.
3. Click **Install one-time updates** (or equivalent), confirming the VM name and update scope.
4. Select classifications or KBs/packages matching the OS and approved policy.
5. Choose the **reboot setting**: if required, always reboot, or never reboot (per supported options).
6. Set a **maximum duration / maintenance window** within service limits, leaving time for installation and verification.
7. Review selections, execute, and monitor **installation status** until completion.
8. Re-assess the VM and run application health checks afterward.

A run finishing with “Completed” must still be inspected for **succeeded, failed, and not-applicable update counts, reboot status, and termination details**. If a package requires restarting an application that does not auto-restart, operators must handle it explicitly.

### 8.2. Azure CLI Example for Azure VMs

The Bash snippet below targets an **existing test VM**; `assess-patches` is read-only/diagnostic, while `install-patches` modifies the guest OS. Never run in production without change approval and a recovery plan.

~~~bash
az login

SUBSCRIPTION_ID="<lab-subscription-id>"
RG="rg-ops-lab"
VM="vm-patch-lab-01"

az account set --subscription "$SUBSCRIPTION_ID"
az account show --query "{id:id, name:name}" -o table

# Check VM and state before assessment
az vm show \
  --resource-group "$RG" \
  --name "$VM" \
  --show-details \
  --query "{id:id, os:storageProfile.osDisk.osType, power:powerState}" \
  --output json

# Trigger assessment for missing updates
az vm assess-patches \
  --resource-group "$RG" \
  --name "$VM" \
  --output json
~~~

Example installing **Critical** and **Security** patches with a bounded duration and rebooting only when needed:

~~~bash
# RUN ONLY on a lab VM after reviewing changes.
# Verify supported commands/values with: az vm install-patches --help
az vm install-patches \
  --resource-group "$RG" \
  --name "$VM" \
  --classifications-to-include Critical Security \
  --maximum-duration "PT2H" \
  --reboot-setting IfRequired \
  --output json
~~~

`PT2H` is ISO 8601 duration notation for two hours. Classifications, flags, and support vary by Azure CLI version, OS, image, and patch mode; **check `az vm install-patches --help` before running**. This targets only the named VM, not every VM automatically. For Arc-enabled servers, use Arc-specific APIs/workflows rather than assuming `az vm` applies.

### 8.3. When to Use One-Time vs. Scheduled Patching

| Context | Appropriate approach |
|---|---|
| One test VM validating a specific patch | Assessment → one-time installation → reboot/health check |
| Urgent high-risk CVE needing immediate fix | Emergency change flow, narrow scope, active monitoring and verification |
| Hundreds of production VMs needing regular patching | Scheduled maintenance configurations and rollout rings |
| VMs running apps with complex dependencies | Approved grouped maintenance windows with tested rollback plans |

Do not repeat manual “one-time” runs every month across the company if auditable governance is the goal. Schedules and inventory prevent newly provisioned machines from being missed.

## 9. Scheduled Patching: Maintenance Configurations and Dynamic Scope

**Scheduled patching** pairs installation policies with a **maintenance configuration** defining the time window and target machines. Where supported, Azure Maintenance provides the scheduling resource with the **InGuestPatch** scope for guest OS updates—do not confuse this with Azure host/platform maintenance.

### 9.1. What Information Does a Maintenance Schedule Need?

| Attribute | Illustrative example | Why it matters |
|---|---|---|
| Name / owner | `mc-guestpatch-orders-canary` / platform team | Tracks schedule purpose and ownership |
| Maintenance scope | In-guest patching (`InGuestPatch`) | Distinguishes from platform-level host maintenance |
| Time zone | `Asia/Ho_Chi_Minh` | Prevents accidentally applying UTC during local business hours |
| Start time / recurrence | Tuesdays 23:00, weekly | Defines predictable rollout timing |
| Maintenance duration | e.g., 3 hours if permitted | Allows time for install, reboot, and verification |
| Patch classification | Security, Critical per OS | Controls scope of change |
| Include / exclude | Approved KBs/packages | Controls known exceptions |
| Reboot setting | `IfRequired` | Governs restart behavior |
| Target scope | Canary group; explicit VM IDs or dynamic scope | Prevents accidentally targeting all of production |

Watch time zones closely across geographies. If using a zone with Daylight Saving Time (DST), test schedule shifts around transitions; Vietnam does not observe DST, though global fleets may span DST zones.

### 9.2. Scheduling via the Azure Portal

Typical workflow:

1. Open **Azure Update Manager → Schedule updates** or **Maintenance configurations**.
2. Create a configuration with the **maintenance scope** set for in-guest patching.
3. Configure start time, time zone, recurrence, and an adequate maintenance window.
4. Set update filters by OS/classification/KB/package and choose the reboot setting.
5. Configure **Machines / Dynamic scoping** to link authorized VMs.
6. Verify **patch orchestration = Customer Managed Schedules** on target Azure VMs as supported; switch modes only through an approved change process.
7. Review the exact count and list of **actually matched VMs**, especially across multiple subscriptions.
8. Save, check the next scheduled run, monitor the first wave, and verify run history.

Screen labels may change; certain VM/OS types carry extra restrictions. Never assume creating a maintenance configuration **automatically** ensures every machine is eligible or will run on time if prerequisites fail.

### 9.3. Dynamic Scoping: Benefits and Risks

Dynamic scoping automatically includes VMs matching criteria such as subscription, resource group, region, resource type, OS type, or tags (depending on supported filter capabilities). Example:

~~~text
Subscription      = app-production
Resource type     = Azure Virtual Machines
Tag application   = orders
Tag patchRing     = canary
Tag patchManaged  = true
~~~

These criteria represent an **illustrative policy model**, not literal machine-readable Azure Update Manager syntax. In the actual portal/API, configure exact supported field names and filters.

**Benefit:** newly deployed VMs following the tag convention enter scope automatically on evaluation, reducing manual VM-by-VM assignment.

**Risk:** a wrong tag edit or overly broad filter can pull production machines into a canary window or drop machines out of all schedules. Mitigate by:

- Governing tags via Azure Policy/IaC and pull-request approvals.
- Checking preview membership and monitoring the first run after any scope edit.
- Requiring explicit environment and ring filters rather than relying solely on `patchManaged=true`.
- Auditing VMs **in zero schedules** and VMs **overlapping multiple schedules**.
- Checking powered-off VMs, disconnected Arc machines, or unsupported patch modes.

### 9.4. Combining Azure Policy and IaC

Azure Policy can evaluate or deploy baseline configurations and enforce tagging/governance standards; IaC (Bicep, ARM templates, Terraform) codifies VMs, tags, maintenance configurations, and assignments in peer-reviewed code. However, **policy compliance does not prove the guest OS actually installed patches**. Measure assessment/installation results alongside configuration compliance.

## 10. Designing Patch Rings: Avoiding Updating All VMs at Once

Organize VMs into ordered test and rollout waves. Example for an ordering system with six app VMs behind Azure Standard Load Balancer spread across Availability Zones:

| Ring | VMs | Illustrative timing | Gate to proceed |
|---|---|---|---|
| `lab` | Isolated test VMs | Monday 21:00 | OS boots, dependency/CI tests pass |
| `canary` | One low-impact production VM | Tuesday 23:00 | Probe healthy, no abnormal API errors/latency |
| `prod-a` | Two production VMs | Thursday 23:00 | Canary remains stable over observation window |
| `prod-b` | Remaining production VMs | Saturday 23:00 | Sufficient capacity remains while rebooting |

This is a **sample schedule**, not an Azure Update Manager default. Canary machines can be low-traffic production nodes or nodes sharing identical OS/image/dependencies with production for realistic validation; choose so a canary failure causes minimal blast radius.

### 10.1. Avoiding Downtime Behind a Load Balancer

Suppose an API runs across four backend VMs. If AUM patches and reboots **all four simultaneously**, the Load Balancer cannot keep the service alive. Therefore:

1. Determine the minimum healthy backends required for peak/window load (`N_min`).
2. Partition maintenance groups so at least `N_min` healthy backends always remain active.
3. Before patching, verify readiness/health probes and load capacity on remaining VMs.
4. Coordinate connection draining, graceful shutdown, and app restarts—never assume AUM coordinates directly with application-level health probes.
5. After reboot, return a VM to rotation only after OS, app, and dependency checks pass.
6. If canary fails, **halt subsequent rings** and execute the remediation runbook.

~~~mermaid
sequenceDiagram
    participant OPS as Operations
    participant LB as Azure Load Balancer
    participant VMA as VM-A (canary)
    participant VMB as VM-B (active)
    OPS->>LB: Verify other healthy backends exist
    OPS->>VMA: Set readiness to maintenance (if needed)
    LB-->>OPS: Stop sending new flows to VM-A after probe threshold
    OPS->>VMA: Install patches / reboot in window
    VMB-->>LB: Continue serving traffic
    OPS->>VMA: Verify OS, services, and application
    VMA-->>LB: Return readiness 200 when healthy
    OPS->>OPS: Evaluate SLOs before approving next ring
~~~

**Health probes do not instantly terminate existing long-lived connections.** Stateful apps or persistent connections require explicit draining and graceful shutdown. Patching a DB/queue node differs from a stateless web tier; never apply the same concurrency count blindly across every workload type.

### 10.2. Differences Across Availability Sets, Zones, and Scale Sets

- **Availability Sets** distribute VMs across fault/update domains, yet guest patch schedules do not automatically honor those domains according to your rollout intent.
- **Availability Zones** separate physical infrastructure in supported regions; a maintenance configuration targeting an entire zone at once can still create broad disruption.
- **VM Scale Sets** require evaluating orchestration mode (Flexible/Uniform), upgrade/patch behavior, and image-based replacement strategies. Teams using golden images often prefer building a patched image and rolling-replacing instances over in-place node patching.
- **Ephemeral OS disks** and stateless workloads especially favor image/replace workflows; never assume in-place patches survive reimaging.

## 11. Reboots: Distinguishing “Installed” from “Active”

Many OS, driver, and kernel patches take full effect only after a reboot. AUM allows configuring reboot behavior via supported policies; exact display names and eligibility depend on OS and operation type.

| Reboot setting | Expected behavior | Considerations |
|---|---|---|
| `IfRequired` | Reboots when patches/OS indicate it is needed | Can interrupt service; budget time inside the maintenance window |
| `Never` | Avoids proactive reboot by policy | Updates may stay pending; risk may not yet be mitigated |
| `Always` | Reboots after installation per policy | Reboots even if patches did not require it; requires approval |

**Never treat `Never` as a safe way to “avoid downtime.”** If a Linux kernel updates without rebooting, the running kernel remains the old vulnerable version. On Windows, reboot-pending updates may not take full effect either.

### Before Rebooting

- Confirm a valid **backup/recovery point** exists and restore procedures are tested.
- Check load, dependencies, active transactions, and draining readiness.
- For DBs/stateful services, verify replication/quorum, backup state, leader/primary role, and failover readiness.
- Check whether the VM needs manual post-reboot steps (decryption, unlock, mount, licensing, reconnect).
- Ensure the window covers OS boot, app warm-up, and health validation.

### After Rebooting

- OS boots, networking, DNS, disks, mount points, and core services are up.
- Required Windows services or `systemd` units are active.
- Running kernel/package/KB version matches target updates.
- Application health probes, business transactions, and connections to data stores/queues/external APIs pass.
- Agents, logs, and alerts remain operational with no abnormal error spikes.

### Unexpected Reboots Outside Windows

Check existing Windows/WSUS and Linux OS auto-update configurations. AUM is only one potential trigger; OS-orchestrated updates, app self-updaters, extensions, or other automation can trigger independent restarts. If an unscheduled reboot happens, trace the **actual initiator** in OS event logs, package manager history, and Azure Activity Log before blaming a maintenance configuration.

## 12. Testing and Rollback Plans Before Production Patching

Patching is a change with risk, especially on VMs hosting middleware, drivers, or legacy apps. A solid patch strategy answers: **if the app fails to come up after reboot, how do we restore service?**

### 12.1. Preparing Recovery Points

- For standard VMs, use **Azure Backup** or an RPO/RTO-compliant backup tool, confirming usable recovery points.
- For VMs with databases, plan **application-consistent backups** and separate data restoration steps; raw disk snapshots do not guarantee transactional consistency everywhere.
- Capture a pre-patch **image/config/manifest** recording OS version, package inventory, service configs, and app release.
- For IaC/image-built VMs, consider building a fresh patched image and rolling-replacing instances instead of hard-to-revert in-place edits.
- Define maximum rollback time and who is authorized to trigger recovery.

**Rollback does not always mean “uninstall patch.”** Some updates cannot be uninstalled cleanly or break dependencies if removed. Depending on context, recovery may mean restoring a backup, redeploying the prior image, failing over traffic, or restoring the application tier.

### 12.2. Success Criteria

| Verification layer | Example |
|---|---|
| OS | VM boots cleanly, disks mounted, no unexpected pending reboot |
| Security | Target patch present, vulnerable version no longer active per advisory |
| Network | DNS, NSGs, firewalls, private endpoints, routes, and outbound paths intact |
| Application | Health probes, sign-in/API, test transaction, and queue processing succeed |
| Data | DB/Storage reachable; backup/replication healthy |
| SLO | Error rates, latency, CPU/RAM, and throughput return within thresholds |
| Observability | Agents, logs, alerts, and dashboards continue cleanly after reboot |

If canary fails, never let the next production ring run simply because its scheduled hour arrived. Enforce an explicit **hold/approval** gate between rings suited to your tooling and process.

## 13. Monitoring, Reporting, and Measuring Patch Compliance

Operating across multiple subscriptions requires consistent per-machine records: **who owns it, which policy applies, when it was last assessed, what installed, any errors, and post-patch app health**.

### 13.1. Breaking Technical Status into Dimensions

| Status | Meaning | Evidence to retain |
|---|---|---|
| Assessment succeeded | Scan retrieved update metadata at timestamp | Scan timestamp, OS, missing patches, resource ID |
| Assessment failed | Unable to determine patch state | Error code, extension/agent status, update source, logs |
| Installation succeeded | Installation completed within run scope | Run ID, installed patches, outcome, duration |
| Installation partially succeeded/failed | Some patches errored, skipped, or failed | Per-package/KB error, reboot status, remediation owner |
| Pending reboot | Changes require restart to take effect | OS state, next maintenance window, owner |
| Workload verified | App passes functional readiness checks | Health checks, synthetic tests, SLOs, owner sign-off |
| Exception approved | One or more patches deferred under governance | Risk note, compensating controls, expiry date, approver |

If a VM's last assessment is older than 10 days, **do not count it as “compliant” merely because that stale scan showed zero missing patches**. Classify it as `unknown/stale` until a fresh scan succeeds.

### 13.2. Available Data Sources

- **Azure Update Manager:** dashboards, assessment details, run history, and managed machine lists.
- **Azure Resource Graph:** queries resource/patch status across data types and authorized scopes, valuable across multi-subscription fleets.
- **Azure Monitor / Log Analytics:** collects system/application telemetry and triggers alerts.
- **Azure Activity Log:** audits control-plane changes such as maintenance configs, assignments, VM edits, and RBAC within supported scopes.
- **Microsoft Defender for Cloud:** surfaces security posture, CVEs, and recommendations per enabled plans.
- **ITSM / change management:** links patch runs to change tickets, approvals, regression evidence, and incidents.

Do not assume AUM data automatically exports into a specific Log Analytics table. Record formats, schemas, and query APIs differ across **Azure Resource Graph**, AUM, and agent-based logs; verify actual available tables and schemas before authoring dashboards or KQL.

### 13.3. Meaningful KPIs

| KPI | Suggested measurement | Notes |
|---|---|---|
| **Coverage** | Managed VMs / total VMs requiring patching | Separate approved exceptions and unsupported OSes |
| **Freshness** | VMs with successful scans inside policy window | Avoid counting stale scans as healthy |
| **Critical patch latency** | Time from patch availability/approval to install and reboot completion | Tier targets by application risk |
| **Installation success** | Successful VM runs / total attempted VM runs | Inspect per-update outcomes too |
| **Pending reboot age** | VMs stuck in pending reboot past threshold | Patches may not yet be effective |
| **Unmanaged machines** | VMs lacking policies/schedules or scans | Catches newly created or Arc VMs |
| **Application regression** | Post-patch error/latency delta vs. baseline | Measures service quality, not just OS task completion |
| **Exception aging** | Deferred patches past approval expiry | Prevents indefinite security bypasses |

KPIs need **explicit denominators**—do not pad “patched %” by quietly mixing in permanently retired or un-onboarded machines. A team can boast a high install rate while leaving its most exposed Internet-facing servers unpatched; report by **risk tier**, not averages alone.

### 13.4. Alerts and Runbooks

Create actionable alerts for:

1. New VMs lacking owner, ring, or patch schedule past grace period.
2. Repeated assessment failures across consecutive cycles.
3. Critical security updates missing past organizational SLA.
4. Failed installation runs or runs aborted by maintenance window timeout.
5. Prolonged pending reboots.
6. Application health probe or availability drops after a patch window.
7. Unexpected edits to maintenance configurations or sudden dynamic scope expansion.

Every alert should include **VM resource ID, subscription, ring, latest run ID, on-call owner, response SLA, and instructions to pause the next ring**. Never emit bare `VM non-compliant` alerts without an owner or remediation path.

## 14. Troubleshooting: When Update Manager Behaves Unexpectedly

### 14.1. VM Missing or Unable to Assess

Common causes include:

- Subscription, resource group, or region excluded by filters, or viewer lacks permissions.
- VM is stopped/deallocated, deleted, recreated with a new resource ID, or moved subscriptions.
- OS/image or patch orchestration mode is incompatible with the requested action.
- Agent/extension is broken, unsupported, or unready.
- Windows Update/WSUS or Linux repositories are unreachable.
- Arc server lost Azure connectivity, is ineligible, or has an unhealthy agent.
- DNS, proxy, or egress firewalls block update/management endpoints.
- Stale assessment has not refreshed, or another operation is currently running.

Diagnostic sequence:

1. Verify **Azure resource ID**, onboarding source, and OS/version.
2. Inspect power/Arc connectivity state and agent/extension health.
3. Check patch mode, periodic assessment setting, schedule assignments, and RBAC roles.
4. Verify DNS/network reachability to service endpoints and OS update sources.
5. Review OS logs and detailed AUM error messages.
6. Run an on-demand assessment in lab/test after fixing root cause to confirm.

### 14.2. Windows Update Errors

Inside the Windows guest, from PowerShell with read privileges:

~~~powershell
# OS version and latest boot timestamp
Get-CimInstance Win32_OperatingSystem |
  Select-Object Caption, Version, BuildNumber, LastBootUpTime

# List recent hotfixes reported via the corresponding API
Get-HotFix | Sort-Object InstalledOn -Descending |
  Select-Object -First 15

# Check Windows Update service status
Get-Service wuauserv
~~~

`Get-HotFix` **does not reliably list every installed update/package type**. Cross-check Update History, Windows Update logs, OS build numbers, and native OS tooling to confirm target patches. If the machine uses WSUS, check GPOs, WSUS reachability, patch approvals, and catalog sync; never force-switch directly to public Windows Update if corporate policy requires WSUS.

Common issues:

- Pending reboot left over from a prior update.
- Corrupted Windows Update Agent, service, or servicing stack.
- Low free space on the OS drive.
- Conflicting GPO/WSUS settings and AUM schedules.
- Update superseded, unapproved in WSUS, or inapplicable to the running image.

Record exact **Windows Update error codes** and inspect official logs rather than running mass Windows Update Agent reset scripts over a single failed patch.

### 14.3. Linux Repositories, Package Locks, and Kernels

On Ubuntu/Debian:

~~~bash
# Distro info and active running kernel
cat /etc/os-release
uname -r

# List upgradable packages from local metadata
apt list --upgradable

# Disk space and DNS resolution check
df -h /
getent hosts archive.ubuntu.com
~~~

On RPM/DNF distros, check:

~~~bash
cat /etc/os-release
uname -r

# Read-only status check, does not install patches
sudo dnf check-update
sudo dnf history list
~~~

`dnf check-update` returns **exit code 100 when updates are available**, which is not an error—read the full output. On SUSE, use `zypper` and enterprise-configured repos. Illustrative commands do not fix every distro automatically and may need adjusted privileges.

Common Linux issues:

- Unreachable repository, broken DNS/proxy/firewall, or CA/TLS errors.
- OS past end-of-life or repositories no longer publishing valid metadata.
- APT/DPKG/DNF lock held by another running update job.
- Dependency conflicts, full disk/inodes, or held/pinned packages.
- New kernel installed while `uname -r` still shows the old kernel before reboot.
- Security patch lacks distro classification metadata expected by Update Manager.

Never delete package manager lock files or `kill -9` an active update process before knowing what it is doing; doing so can corrupt the package database.

### 14.4. Azure VM Agent, Extensions, and Machine State

**Read-only** Azure VM checks:

~~~bash
az account set --subscription "$SUBSCRIPTION_ID"

az vm get-instance-view \
  --resource-group "$RG" \
  --name "$VM" \
  --output json

az vm extension list \
  --resource-group "$RG" \
  --vm-name "$VM" \
  --output table
~~~

Do not assume a single named extension must appear identically across every OS and SKU. Verify required patch extensions for your exact machine type and read **substatus/error messages** before reinstalling extensions. Reinstalling or repairing extensions modifies the system and requires change review.

### 14.5. Installation Exceeds Maintenance Window or Reboot Stalls

If installation runs longer than expected, determine:

- Were there large packages, servicing stack dependencies, or slow repositories?
- Was the machine throttled on disk/CPU/network, or did multi-stage updates run?
- Did the window genuinely leave room for **install + reboot + app verification**?
- Did AUM time out while the guest OS was still finishing installs or waiting on a reboot?
- Was a separate independent update job running concurrently?

**Do not blindly inflate maintenance windows** chasing “100% run success” without diagnosing root cause. For downtime-sensitive VMs, split rings smaller or adopt rolling image replacement.

## 15. Administrative Security and Cost Management

### 15.1. Permission Model

An app dev team may need read access to check patch posture on their VMs without having permission to alter production maintenance schedules. Security teams may need reporting and SLA tracking while platform teams own creating maintenance configurations and schedules.

Recommended guardrails:

- **Azure RBAC** at narrowest scopes, preferring Microsoft Entra groups for assignments.
- **Privileged Identity Management (PIM)** for elevated roles where licensed/supported.
- **Azure Policy** to inventory, tag, and audit posture per deployed definitions.
- **Azure Activity Log** for config edits plus **change tickets** for patch approvals.
- **Private networking / controlled egress** so guests reach only approved update sources/endpoints.
- Protect proxy/repo secrets—never log tokens or credentials.

Patch management should never become an excuse to grant broad subscription permissions to automation scripts. Give pipeline managed identities or service principals strictly required actions, separating lab and production.

### 15.2. Azure Update Manager Costs

Look beyond AUM's direct service meter when budgeting:

| Item | What to verify |
|---|---|
| **Azure VMs** | Eligibility and current pricing terms for Update Manager on Azure VMs |
| **Azure Arc-enabled servers** | Per-server management fees may apply unless covered by eligible licenses/rights |
| **Microsoft Defender for Servers** | Certain plans may include AUM entitlements; verify plan, scope, and terms |
| **Bandwidth and proxies** | Traffic downloading from Windows Update/WSUS or Linux repos, NAT/Firewalls, hybrid links |
| **Log Analytics / Monitor** | Ingestion, retention, alerts, and report exports at scale |
| **Backups / snapshots** | Pre-patch recovery points and extra retention storage |
| **Availability overhead** | Redundant VMs, extra zones/instances, on-call staffing, maintenance windows |

Never hardcode fixed dollar prices into infrastructure docs, as terms and regional rates change. Use current Azure subscription pricing and Azure Cost Management to verify **which machines incur charges and which qualify for entitlements**, especially for Arc-connected servers.

### 15.3. Balancing Risk vs. Cost

Weekly patching shrinks CVE exposure windows yet increases reboot frequency, disruption risk, and on-call hours. Conversely, quarterly patching leaves critical exploited vulnerabilities open too long.

A balanced model:

- **Emergency patches:** expedited workflow driven by real exploit risk rather than waiting for regular cycles.
- **Routine security patches:** relatively short cadence with canary validation and monitoring.
- **Non-security updates:** applied after compatibility testing or during platform refresh cycles.
- **End-of-support OSes:** schedule upgrades/migrations, since AUM cannot conjure patches vendors no longer ship.

Optimize for **time-to-remediate**, install success rate, downtime impact, and operational toil—not merely reducing patch frequency.

## 16. Complete Example: Multi-Subscription Ordering System

**Hypothetical enterprise scenario:**

- Subscription `platform-management` hosts shared monitoring, policies, and operational tooling.
- Subscription `app-orders-prod` hosts six web/API VMs distributed across Availability Zones behind an Azure Standard Load Balancer.
- Subscription `app-orders-test` hosts a production-like staging environment.
- Two separate Windows VMs run batch jobs connected to Azure SQL; the six Linux VMs above serve a stateless API.
- One on-premises Windows server connected via Azure Arc relies on internal WSUS over VPN.
- The ordering service requires low RTO; every maintenance window must keep at least four healthy backends active.

**Goal:** apply security updates on schedule, avoid simultaneous reboots, and maintain auditable post-patch proof.

### 16.1. Orchestration Architecture

~~~mermaid
flowchart TB
    AUM[Azure Update Manager]
    AUM --> MC1[Maintenance config - Lab/Test]
    AUM --> MC2[Maintenance config - Canary]
    AUM --> MC3[Maintenance config - Prod A]
    AUM --> MC4[Maintenance config - Prod B]
    MC1 --> TEST[Test VMs]
    MC2 --> CANARY[1 canary VM]
    MC3 --> PROD1[2 prod VMs]
    MC4 --> PROD2[3 prod VMs]
    CANARY --> LB[Health probes / Application monitoring]
    PROD1 --> LB
    PROD2 --> LB
    AUM -. Reports results .-> OPS[Operations / ITSM]
    OPS -. Approves rollout .-> MC3
    OPS -. Approves rollout .-> MC4
    ARC[Arc server using WSUS] --> AUM
~~~

This diagram shows decision flow. **Never assume AUM automatically inserts manual approval gates between separate maintenance configurations.** Independent schedules fire at their configured times even if canary fails. Build explicit manual or automated “hold/release” controls between rings.

### 16.2. Day-by-Day Rollout Plan

| Illustrative day/time | Activity | Owner | Control gate |
|---|---|---|---|
| Monday 09:00 | Assess all VMs and export baseline | Platform/Security | Any unscanned or EOL VMs? |
| Monday 22:00 | Patch test, reboot, smoke test | QA/Operations | Synthetic transactions pass |
| Tuesday 23:00 | Patch one production canary VM | Operations | At least 5 healthy backends; stable error rate |
| Wednesday 09:00 | Review canary, decide proceed/halt | Service owner | Review logs, latency, and DB health |
| Thursday 23:00 | Patch production group A | Operations | At least 4 healthy backends during maintenance |
| Saturday 23:00 | Patch production group B | Operations | Group A stable post-patch |
| Sunday 09:00 | Re-assess, audit, close change | Security/Operations | Evidence complete or incidents/exceptions logged |

Timestamps are illustrative; adapt to local business hours, Azure time zones, SLAs, and traffic curves. Batch and Arc servers likely need **separate schedules** due to dependencies, WSUS availability, and differing downtime windows.

### 16.3. Architectural Decisions

**One:** never group VMs for patching solely by resource group location. Tag `application`, `environment`, `patchRing`, and `owner` to scope rings precisely, and verify matched VM lists on every schedule change.

**Two:** never rely on a trivial HTTP `200` probe alone. After rebooting, verify Load Balancer routing, API auth, SQL access via Private Endpoint, a synthetic order transaction, and partner integrations.

**Three:** for Windows batch VMs, verify WSUS/GPO allows scheduled installs and confirm batch jobs can pause/resume safely across reboots.

**Four:** for Linux API VMs, track running kernel versions and pending reboots. If repos lack security metadata, security teams must cross-check vendor advisories outside the dashboard.

**Five:** Arc servers can share AUM governance, yet require verifying Arc connectivity, WSUS health, and licensing—never lump them into a ring assuming identical reboot behavior to Azure VMs.

## 17. Pre-, During-, and Post-Wave Operational Checklist

### Before Starting

- [ ] Identified owner, criticality, and patch ring for every VM.
- [ ] Fresh assessment completed and target patch list approved.
- [ ] VMs, OSes, images, extensions, and Arc agents meet operational prerequisites.
- [ ] Windows Update/WSUS or Linux repos are reachable from VM networks.
- [ ] Patch orchestration mode and schedules do not conflict with other automation.
- [ ] Maintenance configurations specify exact scope, time zone, duration, and reboot policy.
- [ ] Backups/recovery points and tested rollback plans are ready.
- [ ] Canaries, concurrent maintenance limits, and on-call owners are confirmed.
- [ ] Monitoring, health probes, and log pipelines are active.

### During the Maintenance Window

- [ ] Monitor installation progress and per-KB/package errors.
- [ ] Watch CPU, disk, network, response times, and VM state.
- [ ] Coordinate draining/quorum and planned reboots.
- [ ] Monitor SLOs, app alerts, data connectivity, and client experience.
- [ ] Pause subsequent rings immediately if canary or a core dependency fails.

### After Maintenance

- [ ] Confirm machines booted cleanly, services run, and network/DNS work.
- [ ] Verify target updates took effect and check pending reboot status.
- [ ] Run synthetic transactions/smoke tests across DB, queue, and API paths.
- [ ] Run a fresh assessment; reconcile missing, failed, and excluded patches.
- [ ] Archive logs, run history, change tickets, and service owner sign-off.
- [ ] Open incidents or time-bound exceptions for incomplete VMs.
- [ ] Review incurred costs and tune schedules/capacity for the next cycle.

Embed this checklist into live runbooks. “Success” must mean **target patches are active and the workload continues serving within SLOs**, not merely that an API call returned success.

## 18. Commonly Misunderstood Advanced Scenarios

### 18.1. Assessment Is Green Yet Defender Still Reports CVEs

The two tools do not evaluate identical scopes:

- Update Manager reports **missing OS updates** per configured catalog/repository at scan time.
- Defender for Cloud or vulnerability scanners can evaluate **CVEs, third-party apps, configs, or artifacts** against independent advisory feeds.
- Vendors may not have shipped a package for an OS version, the OS may be EOL, or a package may be held/pinned.
- Updates may be installed awaiting reboot, or scanners may fingerprint OS build/state differently.

When reports disagree, compare **resource ID, OS version, package/KB, supported release status, scan timestamp, and reboot state**. Never dismiss findings as false positives or assume Update Manager missed patches without checking.

### 18.2. Patch Succeeded Yet the Application Is Unhealthy

Suppose an OS update alters runtime, driver, or TLS behavior, causing HTTP 500 errors. AUM reports installation succeeded because the package installed cleanly, yet users hit errors. Therefore:

1. Link **patch run IDs** directly to **application deployment / change tickets**.
2. Compare pre- and post-patch latency, error rates, restarts, and dependency failures.
3. Halt rollout and drain traffic away from the failing VM if topology permits.
4. Restore from recovery point/image or adjust application config per runbook.
5. After recovery, re-check patch posture to identify any vulnerabilities reopened by rollback.

### 18.3. VM Powered Off Throughout the Maintenance Window

Never assume a maintenance configuration automatically boots a stopped VM, installs all patches, and shuts it back down cleanly. Behavior on stopped/deallocated VMs depends on operations and platform support; if a VM is offline during its window, check run history and maintain a **catch-up process**. Some teams run tested automation to start VMs beforehand, patch, assess, and return them to their desired state.

Frequently powered-off VMs must still meet patch SLAs: scan and patch them before rejoining production networks so unpatched machines never expose stale vulnerabilities.

### 18.4. Does Hotpatching Eliminate All Reboots?

Certain Windows Server editions and Linux mechanisms support **hotpatching / live patching** within narrow scopes. Availability depends on OS support, image type, update content, and licensing terms. Never generalize that “enabling AUM” makes all patches rebootless.

Even when hotpatching handles selected security fixes, platform updates, major kernels, drivers, or baseline changes still require reboots. Maintenance windows and fault tolerance remain essential.

### 18.5. If Golden Images Are Patched, Do VMs Still Need Patch Management?

Yes. A golden image reflects state **at build time**. Once instances run for weeks or months, new patches arrive. Two main models exist:

- **In-place patching:** patch running VMs and track their compliance.
- **Image-based replacement:** build/test a freshly patched image in a pipeline and rolling-replace instances.

Systems can combine both, provided you define the source of truth, rollback paths, persistent data handling, and schedules. For VM Scale Sets and stateless workloads, image-based replacement is often cleaner; for stateful/legacy servers, in-place patching fits well alongside strong recovery plans.

### 18.6. Can Azure Arc Servers Share the Same Schedule as Azure VMs?

In supported scenarios, teams manage both Azure VMs and Arc servers in Update Manager, but **networking, extensions, OS behavior, pricing, and reboot semantics still differ**. For instance, an Arc Windows Server using internal WSUS only pulls patches while VPN and WSUS are healthy, whereas an Azure Linux VM might reach private repos via firewall rules.

Separate runbooks by machine class, verify connectivity/update sources first, and validate prerequisites before placing both in a single schedule.

## 19. Hands-On Lab: Planning Patching for an Azure Architecture

**Scenario:** An enterprise operates 12 VMs:

- 6 Linux VMs serving web/API in subscription `prod-orders` behind a Standard Load Balancer across Availability Zones.
- 2 Windows Server VMs running batch jobs that must finish payment tasks before rebooting.
- 2 VMs in subscription `test-orders` used to validate updates prior to production.
- 2 on-premises Windows servers onboarded to Azure Arc using internal WSUS.

An emergency critical CVE requires remediation within 72 hours under policy. Developers note an earlier patch once broke TLS calls to a payment API. Business rules demand at least four healthy web backends throughout maintenance, zero lost order data, and auditable compliance evidence.

### Tasks

1. **Inventory:** tabulate all 12 machines with resource/Arc ID, OS/version, subscription, owner, app, environment, patch ring, update source, and criticality.
2. **Assessment:** pick the right assessment flow and explain why you must log scan timestamp, patch classification, pending reboot, update source, and agent errors.
3. **Grouping:** separate test, canary, `prod-a`/`prod-b`, Windows batch, and Arc. Decide which groups must never reboot together.
4. **Scheduling:** design maintenance configurations, time zones, recurrence, durations, reboot settings, and tightly scoped dynamic tag filters.
5. **Patch policy:** explain how to identify the exact KB/package fixing the CVE; describe handling Linux repos lacking Security classification metadata.
6. **Pre-checks:** outline backups, recovery points, load checks, batch draining, and health probes prior to patching.
7. **Canary:** describe validating payment API TLS calls, DB connectivity, and halt criteria after canary.
8. **Arc:** explain verifying WSUS and Arc connectivity before patching on-premises servers.
9. **Post-patch:** outline verifying patches took effect post-reboot, monitoring app errors, and reporting to security owners.
10. **Incident:** write a runbook for two VMs rebooting simultaneously and healthy backends dropping below threshold.
11. **Cost and permissions:** identify potential AUM/Arc, monitoring/backup fees, and least-privilege roles for patch operators.
12. **Exceptions:** suppose one Windows batch VM cannot install the patch due to compatibility; write mandatory fields for a time-bound risk exception.

### Sample Answer Framework

| Machine / group | Scope and patch mode to verify | Window | Post-patch evidence |
|---|---|---|---|
| Linux test | Azure VM, mode supporting scheduled installs | Monday 21:00 | Kernel/package versions, smoke test, API TLS |
| One Linux prod canary | `patchRing=canary`, keep other backends up | Tuesday 23:00 | Probe 200, stable SLOs, target patch active |
| Next two Linux prod | `patchRing=prod-a`, sufficient active backends | After canary sign-off | No error/latency spike, fresh assessment |
| Final three Linux prod | `patchRing=prod-b` | Controlled next wave | Back in pool, zero pending reboots |
| Two Windows batch | Separate schedule aligned to batch/DB completion | Approved post-batch window | Windows build/hotfix, job integrity |
| Two Arc Windows | Arc connectivity + WSUS + licensing | Dedicated on-premises window | Patch history, reboot state, internal health |

*Note:* With six web VMs, if three VMs patch simultaneously while four healthy backends are required, `prod-b` **cannot patch all three VMs at once**. Split waves to **at most two VMs** (or fewer if any instance is already unhealthy), or scale capacity beforehand. That is an intentional lesson of this exercise: **schedules must verify `N_min`, not merely apply ring labels**.

### Example Availability Calculation

Assuming six healthy backends before maintenance:

~~~text
N_total = 6 backends
N_min   = 4 backends must remain ready
N_max_maintenance = N_total - N_min = 2 backends

Before each wave:
- Count truly HEALTHY backends (not just VM Running).
- If 1 backend is already unhealthy: 5 healthy remain -> patch at most 1 VM.
- If 2 backends are already unhealthy: 4 healthy remain -> pause patching completely.
~~~

This simple math works when backends share equal capacity and balanced traffic. With uneven capacities, measure **actual load capacity** rather than VM counts alone. Also verify failover limits on databases and shared services.

### Self-Evaluation Criteria

The exercise is complete when you can explain:

- **Which machines** are patched, **when**, **by whom**, and **under which policy**.
- Where Windows Update/WSUS or Linux repositories serve updates from.
- Why successful assessment, successful install, and healthy workload are **three distinct states**.
- How to avoid rebooting too many backends concurrently, including when one VM is already unhealthy pre-window.
- How to handle canary failures, pending reboots, failed installs, or unscannable machines.
- How to retain completion evidence and exceptions without exposing credentials or sensitive data.

## 20. Key Takeaways

**Azure Update Manager** helps **assess, orchestrate on-demand or scheduled installs, and track guest OS patching** on supported Azure and Azure Arc machines. It **does not replace** Windows Update/WSUS/Linux repositories, application CI/CD, container/image management, or workload recovery plans.

A reliable patching process relies on five protective layers:

1. **Accurate inventory and assessment:** know which machines lack patches, their update sources, and scan freshness.
2. **Tailored policy and scope:** align updates/KBs/packages, patch modes, scopes, maintenance windows, and reboot policies per OS/workload.
3. **Controlled rollout:** validate in test/canary, preserve healthy capacity, and never update all VMs at once.
4. **Post-reboot verification:** verify kernels/KBs, apps, data, networking, logs, and user experience.
5. **Continuous operations:** track missed machines, stale reports, expired exceptions, install errors, costs, and recovery readiness.

When evaluating any Azure deployment, never stop at **“Did the VM install the patch?”**—also answer **“Which patches are active, is the service still healthy, and does the organization have evidence to remediate what remains?”**
