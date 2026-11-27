# Start, Stop, Deallocate Lifecycle and Cost Impact

In Azure, a virtual machine (**Azure Virtual Machine — VM**) can be running, have its OS shut down while still holding compute allocation, or be **deallocated** so Azure releases the compute capacity assigned to it. All three states can look like “the machine is not serving the application” to users, yet their effects on **billing**, **network addresses**, **restart behavior**, and **temporary data** differ significantly.

For instance, a development team has a test VM used only during business hours. If an engineer signs into Windows and clicks **Shut down**, the VM can transition to **Stopped (allocated)**: the guest OS powers off, while compute resources remain allocated and **VM compute charges typically continue**. If the team stops the VM via the Azure Portal's deallocation flow or runs **az vm deallocate**, the VM enters **Stopped (deallocated)**: standard hourly compute usage charges stop accruing, whereas **OS disks, data disks, and many supporting resources keep incurring charges**.

This lesson belongs to the **Azure Virtual Machines** chapter of the **CLOUD_PROVIDERS_AZURE** module. Across your Azure learning path—from subscriptions and resource groups, identity, virtual networking, compute, and storage to monitoring, security, and cost control—understanding the VM lifecycle prevents waste while ensuring systems recover safely.

> **Key takeaway:** **Stopped does not necessarily mean deallocated; deallocated does not mean zero total cost; and deallocated does not mean the VM is deleted.**

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish **PowerState/running**, **PowerState/stopped**, and **PowerState/deallocated**, without confusing them with provisioning state.
2. Explain the effects of **Start**, **Stop**, **Deallocate**, **Restart**, and **Delete** on compute resources, data, and billing.
3. Explain why shutting down from inside the guest OS differs from deallocating through Azure.
4. Use the Azure Portal, Azure CLI, and PowerShell to check status, start, stop, deallocate, and verify outcomes.
5. Plan after-hours shutdown schedules for dev/test VMs without disrupting production or application constraints.
6. Identify costs that continue when a VM is deallocated: managed disks, backups/snapshots, IPs, networking, monitoring, or active pricing commitments.
7. Assess risks for **dynamic IPs**, **temporary disks**, **ephemeral OS disks**, capacity availability, and startup schedules.
8. Track costs in Cost Management, design automation schedules, and implement safeguards.
9. Diagnose cases where a VM fails to start, still generates charges, or loses application connectivity after starting.

## 2. Two Key Concepts: Power State and Provisioning State

Azure tracks VMs across multiple layers. To understand the lifecycle, first separate:

- **Power state:** indicates whether the VM is running, stopped while holding compute, or deallocated.
- **Provisioning state:** indicates whether a control-plane operation on the Azure resource is in progress, succeeded, or failed—such as **Creating**, **Updating**, **Succeeded**, or **Failed** depending on API and timing.

These two concepts **do not replace each other**. A VM with provisioning state **Succeeded** and power state **VM deallocated** is completely valid: the VM resource exists and its latest management operation succeeded, even though the machine is powered off.

### 2.1. Core Power States

| Common power state | Guest OS running? | Compute still allocated to VM? | Standard VM compute usage billing |
|---|---|---|---|
| **Running** | Yes, if guest is healthy | Yes | Yes |
| **Stopped / Stopped (allocated)** | No | **Yes** | **Usually yes** |
| **Stopped (deallocated)** | No | **No longer holds standard compute allocation** | **VM compute usage billing stops** |
| **Starting / Stopping / Deallocating** | Transitioning | Depends on stage | Depends on allocation timing and actual metering rules |
| **Deleted** | VM resource removed | No | No compute charges for deleted VM, though other resources may remain |

Display names in the Azure Portal, Azure CLI output, and API responses can vary slightly. Check the **actual power state** rather than guessing based on whether Start/Stop buttons are clickable.

A VM in **Stopped (allocated)** still retains its compute allocation so it can boot without undergoing full reallocation like a deallocated VM. That explains why a VM “not running Windows/Linux” can still incur compute charges.

### 2.2. State Transition Diagram

~~~mermaid
flowchart LR
    R["Running<br/>Compute allocated"]
    S["Stopped (allocated)<br/>Guest OS off, compute held"]
    D["Stopped (deallocated)<br/>Compute released"]
    R -->|"Stop from guest OS or az vm stop"| S
    S -->|"az vm start"| R
    R -->|"az vm deallocate"| D
    S -->|"az vm deallocate"| D
    D -->|"az vm start / Portal Start"| R
    R -->|"az vm restart"| R
~~~

This model covers the core states. Any transition can pass through intermediate states and fail due to quotas, capacity, permissions, or infrastructure errors. VMs configured with **hibernation** are a special case: verify support prerequisites, memory preservation, and specific billing rules; do not treat hibernation as standard deallocation.

### 2.3. “Stopped” Can Be Misleading

Consider two status lines:

~~~text
PowerState/stopped      → VM stopped (allocated)
PowerState/deallocated  → VM deallocated
~~~

Neither state serves application requests, yet they are **not equivalent** for compute billing. On dashboards or operations tickets, record the exact Azure state rather than merely writing “VM off.”

## 3. Start Operation: Allocating Compute and Booting the Guest

**Start** instructs Azure to run the VM, including securing compute allocation, booting the operating system, and starting guest services.

### 3.1. Starting from Stopped (allocated)

Compute is already held; Azure boots the OS on the allocated resources. Even so, the application is only ready once the guest OS, dependent processes, networking, and health checks finish initializing.

### 3.2. Starting from Stopped (deallocated)

Azure must allocate suitable compute capacity before running the VM. This can introduce:

- Startup duration varying with capacity, VM configuration, OS, and extensions.
- Risk of insufficient capacity for that VM size in the region/zone at that time.
- Placement changes on underlying hosts, meaning **temporary/local disk** contents are not preserved.
- Possible changes to dynamically assigned IP addresses, depending on NIC/Public IP SKU and allocation settings.
- Once compute is allocated and the VM runs, **compute charges resume** per service billing rules.

**Never promise** that a deallocated VM will always start instantly or keep its dynamic IP. When strict start deadlines matter, incorporate warm-up and application checks into operations plans.

### 3.3. Start Does Not Equal a Healthy Application

Power state **Running** only means Azure reports the VM is powered on. Web servers, databases, message consumers, or scheduled jobs may not be ready yet.

Post-start checklist:

1. VM reaches Running state.
2. Guest OS, Azure VM Agent, and required extensions are operational.
3. Required data disks are mounted or assigned the expected drive letters.
4. Network interfaces, DNS, firewalls, NSGs, and routes are working.
5. Applications can reach databases, Key Vault, and dependencies.
6. Health endpoints, readiness/liveness probes, or a business smoke test pass.
7. Logs and telemetry show no critical startup errors.

For multi-tier workloads, start components in **dependency order** rather than firing Start on everything at once and assuming power state means success.

## 4. Stop: Shutting Down the OS While Potentially Retaining Compute

**Stop**, in the context of Azure CLI **az vm stop** or a guest OS shutdown, typically transitions the VM to **Stopped (allocated)**.

### 4.1. Shutting Down from Inside the Guest OS

Examples:

On Linux:

~~~bash
sudo shutdown -h now
~~~

On Windows, administrators can select **Shut down** from the Start menu or run appropriate PowerShell:

~~~powershell
Stop-Computer -Force
~~~

This shuts down the operating system. It **does not instruct Azure to release compute allocation** in the deallocate sense. Therefore, **never treat an inside-Windows/Linux shutdown as proof of compute cost savings**.

The PowerShell **-Force** flag merely illustrates guest shutdown behavior and can disrupt active processes; avoid running it carelessly on transactional workloads.

### 4.2. Stop from Azure CLI

~~~bash
az vm stop \
  --resource-group "<resource-group>" \
  --name "<vm-name>"
~~~

This performs a VM **power off/stop**, not a deallocate. For standard VMs, the resulting state is **VM stopped** with compute still allocated.

Use this when you need to halt the OS while intentionally keeping compute resources reserved; the organization must accept the ongoing compute charges.

### 4.3. Stop in the Azure Portal May Differ from CLI Stop

Remember this critical difference: clicking **Stop** in the **Azure Portal** normally stops and **deallocates** the VM, unlike shutting down inside the OS or running **az vm stop**.

Because UIs, intermediate transitions, and service defaults can evolve, the reliable verification sequence is:

1. Run the chosen action.
2. Wait for the transition to complete.
3. Inspect the **Power state** via Portal/CLI/API.
4. Confirm **VM deallocated** is reported if the goal is stopping compute charges.

**Never assume “money saved” simply from seeing the word Stop in activity history.**

## 5. Deallocate: Releasing Compute Allocation

**Deallocate** is the primary action when halting VM compute usage and reducing after-hours costs.

~~~bash
az vm deallocate \
  --resource-group "<resource-group>" \
  --name "<vm-name>"
~~~

Once deallocation finishes, the VM typically enters **Stopped (deallocated)** or **VM deallocated**.

### 5.1. What Changes?

- **Compute:** compute capacity is released from the VM; standard compute usage stops accruing while deallocated.
- **VM resource:** the VM resource, size configuration, image reference, metadata, tags, and references to disks/NICs persist.
- **Managed OS/data disks:** normally **persist and retain their data**; disk charges continue per configuration.
- **Temporary/local disk:** contents **are not guaranteed to persist**; treat any data there as volatile across deallocate/redeploy.
- **Ephemeral OS disk:** a special case backed by local host storage; understand data loss or reimage behavior on deallocation or host replacement.
- **Dynamic IP addresses:** may change across a deallocate/start cycle; verify allocation settings per IP type.
- **Capacity:** subsequent starts may encounter capacity shortages for that VM size/zone during reallocation.

### 5.2. What Does Not Change Automatically?

Deallocating **does not** automatically:

- Delete managed disks or snapshots.
- Delete backups or retention policies.
- Delete Network Interfaces, Public IPs, Load Balancers, NAT Gateways, or Azure Bastion.
- Purge Azure Monitor logs or collected telemetry.
- Cancel Reserved VM Instances, Savings Plans, or active commitments.
- Wipe data or secrets from external services.
- Stop other Azure services used by the app, such as Azure SQL Database, Storage Accounts, or Key Vault.
- Revoke RBAC permissions, reset passwords, or close security vulnerabilities.

Thus, deallocating is a **compute cost-reduction tool**, not a procedure for **completely retiring a system and zeroing out the bill**.

### 5.3. Should You Stop Before Deallocating?

For workloads actively writing data, **quiesce** the application first: stop accepting new requests, finish or cleanly abort in-flight transactions, flush buffers to disk, and shut down services in order.

Then trigger deallocation via Azure. Whether an explicit guest shutdown precedes Azure deallocate depends on your application and runbook; either way, the final verification must confirm **VM deallocated**.

Never rely on deallocation as an application-consistent database snapshot mechanism. Use proper backup or checkpoint tools when application consistency is required.

## 6. Restart, Redeploy, Reimage, and Delete Are Different Operations

Operations frequently confused with Start/Stop:

| Operation | Goal | Key considerations |
|---|---|---|
| **Restart** | Reboot the VM/guest OS | VM retains compute; not a cost-saving action |
| **Stop (allocated)** | Shut down guest while retaining allocation | Compute billing usually continues |
| **Deallocate** | Stop VM and release compute | Halts compute usage; other resource charges remain |
| **Redeploy** | Move VM to another host to resolve certain platform faults | Causes downtime; temporary disk data and placement may change |
| **Reimage** | Recreate the OS disk per VM model behavior | Can wipe OS disk customizations; requires data protection plan |
| **Delete VM** | Remove the VM resource | Disks, NICs, Public IPs may persist or delete depending on delete options and workflow |

If your goal is lowering dev/test VM bills, **deallocate** is usually right rather than delete. If retiring a service permanently to eliminate disk charges, follow an approved **backup/export → retention verification → resource and dependency deletion** workflow.

**Delete** carries far higher data and configuration risk than deallocate. Never use delete for ad-hoc cost experiments before verifying exactly which dependent resources are marked for deletion.

## 7. Summary Table: VM States and Costs

For a standard pay-as-you-go VM:

| Cost / resource type | Running | Stopped (allocated) | Stopped (deallocated) |
|---|---|---|---|
| **VM compute usage** | Yes | **Yes** | **No**, per deallocation behavior |
| **Managed OS disk** | Yes | Yes | **Yes** |
| **Managed data disk** | Yes | Yes | **Yes** |
| **Snapshots / backups** | If configured | May still apply | **May still apply** |
| **Standard Public IP** | Per SKU and IP resource state | Per SKU/configuration | **May still incur charges** while IP resource exists |
| **Load Balancer / NAT Gateway / Bastion / Firewall** | Per service | May still incur charges | **May still incur charges** |
| **Azure Monitor / Log Analytics** | By ingestion and retention | By stored/ingested data | Previously ingested data can still incur retention charges |
| **Reserved Instance / Savings Plan commitment** | Per purchased commitment | Commitment remains | **Commitment remains** |

This is a conceptual table, not an invoice or single universal pricing rule. Certain VM plans/licenses, Dedicated Hosts, Capacity Reservations, or Marketplace offers carry distinct billing models. Review SKU terms, contracts, and usage meters in Cost Management.

### 7.1. Why Do Managed Disks Keep Billing?

A managed disk is a **storage resource independent** of VM compute. When deallocating, Azure does not wipe OS or data disks. Retaining that data so the VM can start later consumes persistent storage capacity.

Disk charges depend on:

- Disk tier: Standard HDD, Standard SSD, Premium SSD, Premium SSD v2, Ultra Disk, etc.
- Provisioned capacity and SKU billing model.
- Separately provisioned IOPS/throughput where configurable.
- Redundancy (LRS/ZRS), region, snapshots, and backup configurations.
- Any other enabled service billing features.

Consequently, a VM left deallocated for months can still accumulate **significant storage bills** if attached to large disks.

### 7.2. Public IPs and Network Addresses

Evaluate IP addresses across two dimensions:

1. **Stability:** a dynamically allocated IP may change after deallocation/reallocation depending on resource type and configuration. Static IPs preserve addresses while the resource exists within SKU rules.
2. **Cost:** a Public IP resource can incur its own charges even while the VM is stopped, depending on SKU and pricing model.

Never assume static IPs are free, and never assume every dynamic IP stays unchanged across starts. Inspect NIC IP configurations, Public IP resources, and DNS policies.

Ideally, production apps use DNS names and proper load balancing rather than hardcoding a VM's dynamic public IP.

### 7.3. VM Reservations, Savings Plans, and Licensing

**Azure Reservations** and **Savings Plans** are conditional pricing/usage commitments. If a target VM is deallocated:

- Specific pay-as-you-go compute usage for that VM stops accruing.
- The **purchased commitment** continues under the contract terms.
- Commitment benefits may apply to other eligible running resources or go partially unused.

Thus, **a drop in one VM's visible cost** does not guarantee **the organization's total invoice** drops by that exact hourly compute rate in every case. With Windows Server, SQL Server, Dedicated Hosts, or Marketplace software, verify licensing terms separately.

### 7.4. Deallocated Does Not Mean Fully Secured

A stopped VM remains a cloud resource with disks, configs, network interfaces, and management permissions. Authorized principals can still inspect disks, take snapshots, alter role assignments, etc.

While a VM is off:

- Maintain least-privilege RBAC.
- Protect disks with appropriate encryption.
- Govern snapshots/backups and identity access.
- Keep network rules and NSGs in their intended state.
- Continue monitoring control-plane operations via Activity Log.

Never equate Stop/Deallocate with deleting encryption keys or revoking credentials.

## 8. Illustrative Scenario: Development VM Needed Only During Business Hours

A team uses a test VM running on average **8 hours per day**, **22 days in a 30-day month**. Outside those hours, there are no users and no batch jobs required.

For illustration, assume a **hypothetical compute rate of $0.25/hour**. This is a placeholder number for math practice, **not official Azure pricing**. A 30-day month has 720 hours.

| Option | Example compute hours | Hypothetical compute cost |
|---|---:|---:|
| Running / keeping compute allocated all month | 720 | $180 |
| Deallocated after hours; running 8 hrs × 22 days | 176 | $44 |
| Avoided compute usage | **544** | **$136** |

Simple calculation:

~~~text
Required compute hours = 8 hours/day × 22 days = 176 hours
Full-month hours       = 30 days × 24 hours    = 720 hours
Avoided compute hours  = 720 - 176             = 544 hours

Estimated continuous compute usage = 720 × 0.25 = $180
On-demand scheduled compute usage  = 176 × 0.25 =  $44
Compute usage difference           = $136
~~~

**Excludes** warm-up time, ad-hoc manual runs, disks, Public IPs, backups, monitoring, networking, licensing, or pricing commitments. Real prices vary substantially by region, VM size, and purchasing model.

### 8.1. Total Cost Does Not Equal Compute Cost

An easy-to-follow estimate model:

~~~text
Total cost =
    VM compute usage
  + Managed OS/data disks
  + Backups and snapshots
  + Public IP / Load Balancer / related network services
  + Monitoring and log retention
  + Licensing / Marketplace / contractual commitments
  + Other workload services
~~~

Deallocation affects **compute usage** most directly; every other line item must be evaluated separately.

### 8.2. Technical Savings vs. Cash Savings

If the team already purchased a Savings Plan or Reservation with a fixed recurring commitment, stopping one VM **reduces usage attributed to that VM**, yet total cash outlay for the period may not fall proportionally unless another eligible workload absorbs the unused commitment.

In FinOps reporting, distinguish:

- **Usage reduction:** fewer allocated compute hours.
- **Billed compute reduction:** actual change in billed charges.
- **Commitment utilization:** how effectively purchased commitments are consumed.
- **Total workload cost:** sum of compute, storage, networking, logging, and related services.

## 9. Checking VM State in the Azure Portal

In the Azure Portal:

1. Open **Virtual machines**.
2. Select the right subscription, resource group, and VM.
3. Inspect **Status / Power state** on the Overview blade.
4. Optionally open **Properties** or **Activity Log** to review recent operations.
5. When managing fleets, filter by resource group, tag, or power state as supported.
6. Confirm **Stopped (deallocated)** on VMs meant to save compute usage.

State transitions take time after clicking Stop or Start. Avoid hammering buttons repeatedly merely because the Portal view has not refreshed yet.

### 9.1. Using Start and Stop Buttons

- **Start:** powers on the VM and allocates compute as needed.
- **Stop in the Portal:** typically stops and deallocates, though you should verify the final Power state.
- **Restart:** reboots the VM; does not deallocate.

Button placement shifts across Portal updates; **verify the resulting state**, not just the UI button label.

### 9.2. Inspecting Related Resources

Before deallocating an important VM, check:

- OS/data disks and disk tiers.
- NICs, private IPs, Public IPs, and allocation methods.
- VM size, availability zone/set, and capacity constraints.
- Backup, monitoring, and alert status.
- Dependent resources like Load Balancers, Application Gateways, or databases.
- Owner tags and operating schedules.

A VM with no active interactive users may still run background jobs, agents, scheduled tasks, or maintenance routines. Never deallocate solely because CPU looks low at one moment.

## 10. Azure CLI: Checking Status, Start, Stop, and Deallocate

The examples below use **Bash** in Azure Cloud Shell or a shell with Azure CLI installed. Replace placeholders with real resources. **Operate only on VMs you are authorized to manage, preferably in a lab environment.**

### 10.1. Select Subscription and VM

~~~bash
az login
az account set --subscription "<subscription-id>"
az account show --output table

RG="rg-vm-lab"
VM="vm-demo-01"
~~~

Check that the VM exists and read its status:

~~~bash
az vm show \
  --resource-group "$RG" \
  --name "$VM" \
  --show-details \
  --query "{name:name,location:location,provisioningState:provisioningState,powerState:powerState,size:hardwareProfile.vmSize}" \
  --output json
~~~

**Power state** via **--show-details** is a convenient summary. You can also query instance view directly:

~~~bash
az vm get-instance-view \
  --resource-group "$RG" \
  --name "$VM" \
  --query "statuses[?starts_with(code, 'PowerState/')].{code:code,status:displayStatus}" \
  --output table
~~~

Returned statuses may look like:

~~~text
PowerState/running       VM running
PowerState/stopped       VM stopped
PowerState/deallocated   VM deallocated
~~~

These are **illustrative values**, not output captured from a live subscription. If a command returns empty results, check permissions, VM name, instance view state, and CLI version.

### 10.2. Start a VM

~~~bash
az vm start \
  --resource-group "$RG" \
  --name "$VM"
~~~

Verify after completion:

~~~bash
az vm show \
  --resource-group "$RG" \
  --name "$VM" \
  --show-details \
  --query "powerState" \
  --output tsv
~~~

Expect **VM running** once settled. Continue verifying application health; the command returning does not guarantee all guest services are ready.

### 10.3. Stop While Keeping Compute Allocated

~~~bash
az vm stop \
  --resource-group "$RG" \
  --name "$VM"
~~~

Check status again:

~~~bash
az vm show \
  --resource-group "$RG" \
  --name "$VM" \
  --show-details \
  --query "powerState" \
  --output tsv
~~~

Normally expect **VM stopped**, **not VM deallocated**. Therefore, this is **not an after-hours compute cost-saving command**.

### 10.4. Deallocate to Release Compute

~~~bash
az vm deallocate \
  --resource-group "$RG" \
  --name "$VM"
~~~

After completion:

~~~bash
az vm get-instance-view \
  --resource-group "$RG" \
  --name "$VM" \
  --query "statuses[?starts_with(code, 'PowerState/')].{code:code,status:displayStatus}" \
  --output table
~~~

Expect **PowerState/deallocated**. Only after confirming the deallocated state should you record that compute release is technically complete.

### 10.5. List States Across a Resource Group

~~~bash
az vm list \
  --resource-group "$RG" \
  --show-details \
  --query "[].{name:name,powerState:powerState,vmSize:hardwareProfile.vmSize,location:location}" \
  --output table
~~~

Run this before building auto-shutdown schedules so no VM is overlooked. To inspect across multiple subscriptions, ensure appropriate permissions and scope; do not assume one resource group represents the entire organization.

### 10.6. Using `--no-wait`

Some commands accept **--no-wait** to return shell control immediately before the operation completes. Example:

~~~bash
az vm deallocate \
  --resource-group "$RG" \
  --name "$VM" \
  --no-wait
~~~

At this point the request has been submitted—**it does not prove the VM is already deallocated**. Schedulers/runbooks must poll final state and handle timeouts, failures, or duplicate triggers.

Specifically, never fire Start immediately after an unfinished Deallocate request without checking state; rapid conflicting power operations can fail.

## 11. Azure PowerShell and Guest OS Operations

In environments using the **Az PowerShell** module, typical commands include:

~~~powershell
Connect-AzAccount
Set-AzContext -SubscriptionId "<subscription-id>"

$rg = "rg-vm-lab"
$vm = "vm-demo-01"

# Read VM info and instance status
Get-AzVM -ResourceGroupName $rg -Name $vm -Status

# Start VM
Start-AzVM -ResourceGroupName $rg -Name $vm

# Stop and deallocate per standard Stop-AzVM behavior
Stop-AzVM -ResourceGroupName $rg -Name $vm
~~~

In **Az PowerShell**, **Stop-AzVM** deallocates the VM by default. Pass **-StayProvisioned** when you want the VM stopped while **keeping compute allocated**:

~~~powershell
Stop-AzVM -ResourceGroupName $rg -Name $vm -StayProvisioned
~~~

Hence, **Stop-AzVM is not equivalent by default to Azure CLI's az vm stop**. This is a crucial distinction when translating scripts between Bash/Azure CLI and PowerShell.

Comparison:

| Action method | Typical target state | Deallocates? |
|---|---|---|
| Linux **shutdown -h now** inside VM | Stopped (allocated) | No |
| Windows **Shut down** inside guest | Stopped (allocated) | No |
| **az vm stop** (Azure CLI) | Stopped (allocated) | No |
| **az vm deallocate** (Azure CLI) | Stopped (deallocated) | Yes |
| **Stop** in Azure Portal | Usually Stopped (deallocated) | Usually yes; verify state |
| **Stop-AzVM** without `-StayProvisioned` | Usually Stopped (deallocated) | Yes |
| **Stop-AzVM -StayProvisioned** | Stopped (allocated) | No |

Always verify behavior against the **exact tool version and VM type** rather than guessing from the word “stop.”

## 12. Data Warnings: OS Disk, Data Disk, and Temporary Disk

Because start/deallocate cycles can shift underlying compute resources, distinguish three storage tiers.

### 12.1. Managed OS Disk

A VM using a **managed OS disk** stores its OS on a managed storage resource independent of the compute host. Upon deallocation, the OS disk persists unless explicitly deleted.

Examples:

- Application configs on the OS disk survive standard deallocate/start cycles.
- Temporary logs/secrets on the OS disk also survive, so **deallocation does not erase sensitive data**.
- OS disk billing continues.

### 12.2. Managed Data Disk

**Managed data disks** hold attached data volumes and typically persist across deallocation. However:

- For databases, ensure writes are flushed before stopping.
- After VM start, verify disk attachment, drive letters, mount points, and dependent services.
- Deleting a VM involves separate delete options for data disks.
- Disk persistence alone does not replace snapshots, backups, and restore testing.

### 12.3. Temporary/Local Disk

Many VM sizes provide a local temporary disk tied to the physical host. Contents on this disk **are not guaranteed to survive** deallocate, redeploy, host replacement, or certain platform operations.

Therefore:

- Never place primary databases or non-reproducible data on the temporary disk.
- Never use the temporary volume as the sole home for recoverable files.
- Use temporary disks only for disposable caches or scratch space designed to be recreated.
- On startup, verify applications recreate required temp directories, permissions, and cache state.

### 12.4. Ephemeral OS Disk Is a Special Case

An **ephemeral OS disk** runs the OS on local host storage where supported by VM size/deployment type, giving it lifecycle and durability rules distinct from managed OS disks. Never apply the “OS disk persists on deallocate” rule to ephemeral OS disks.

If workloads use ephemeral OS disks, design machines to be **statelessly rebuildable from images**, avoid storing unique data on the OS disk, and review exact deallocate/reimage/redeploy constraints in documentation.

## 13. IP Addresses, DNS, and Networking After Restart

After deallocation, network resources persist as ARM objects, though runtime addresses may change depending on configuration.

### 13.1. Private IP

Azure NICs support **dynamic private IP allocation** or static private IP assignment within a subnet. When workloads require predictable IPs, evaluate static private IPs or internal DNS as appropriate.

Do not hardcode an application to a dynamic IP assuming it never changes across deallocate/start cycles. Conversely, avoid assigning arbitrary static private IPs outside your organization's IP address management plan.

### 13.2. Public IP

Check the VM's **Public IP resource** and its **allocation method/SKU**:

- Certain dynamic IP configurations may release their address upon deallocation.
- Static Public IPs generally retain their address while the resource exists within SKU rules.
- Public IP resources can continue incurring charges even while the VM is deallocated.
- For VMs behind a Load Balancer or NAT Gateway, client-facing addresses belong to those services rather than the VM's NIC.

In production, prefer DNS names, private endpoints, load balancers, or dedicated ingress rather than relying on a VM's direct dynamic public IP.

### 13.3. NSGs and Firewalls

Deallocation does not strip NSG rules or firewall policies. When the VM restarts, connectivity may be blocked by policy edits made while the VM was off.

Common post-start issues:

- NSG permits only the old IP.
- DNS records still point to a stale pre-deallocation IP.
- Load balancer backend pool / health probe has not returned to Healthy.
- UDR/NVA/firewall blocks VM flows.
- Guest firewall or app service is not listening on the port.

Never fix issues by temporarily opening **Any/Any** in production. Trace source–destination–port flows along with effective rules and routes.

## 14. VM Start Can Fail After Deallocation

Because deallocate releases compute allocation, a subsequent Start requires Azure to reallocate capacity on compatible infrastructure.

### 14.1. Common Causes

| Symptom | Possible causes | Remediation |
|---|---|---|
| Start fails due to capacity | Target VM size/zone currently lacks allocation capacity | Check exact error, retry later, or switch size/zone per approved plan |
| Start blocked by policy | Azure Policy, deny assignment, or missing permissions | Inspect Azure Activity Log, RBAC scope, and policies |
| VM runs yet app fails | Service/dependency unready, IP/DNS shifted | Check guest boot, service logs, health probes, IPs, and DNS |
| Startup takes too long | OS updates, extensions, disk mounts, warm-up | Set realistic timeouts and monitor boot progress |
| Disk/mount unavailable | Attachment error, filesystem fault, or guest config | Inspect instance view, OS logs, and disk config |
| Scheduler fails to start VM | Managed identity, scope, permission, or schedule bug | Check runbook execution, auth, timezone, and permissions |
| Costs remain after deallocate | Disks, IPs, backups, licenses/commitments, or Cost Management lag | Break down usage meters and compare timestamps |
| VM turns back on unexpectedly | Another automation, script, ops policy, or operator | Audit Activity Log and all automation triggers |

### 14.2. Capacity and Availability

If a critical workload must serve requests at any moment, nightly deallocation is usually unsuitable because:

- Identical host/placement is not guaranteed.
- Starting incurs latency and occasional capacity failures.
- Systems require health checks and warm-up handling.
- Availability SLAs apply only when VMs/instances meet service deployment criteria.

If compute availability or guaranteed startup readiness is mandatory, consider budget-appropriate designs such as Reserved Capacity / On-Demand Capacity Reservations where supported—noting that capacity reservations **continue incurring charges**.

Never promise instant recovery with `RTO=0` from a deallocated VM.

## 15. Automated Start/Stop Schedules for Dev/Test VMs

A common FinOps pattern is automatically **deallocating after hours** and **starting before work hours**.

Example schedule for a development team:

~~~text
Monday – Friday:
    08:15  Start VM
    08:30  Verify application readiness
    18:00  Notify / check running jobs
    18:30  Deallocate VM

Weekends:
    Keep VM Deallocated unless an approved exception exists
~~~

Times are illustrative. Explicitly define the timezone (e.g., `Asia/Ho_Chi_Minh`) and verify how your scheduling tool handles UTC, daylight saving time, or public holidays if applicable.

### 15.1. Azure Portal Auto-Shutdown

For supported VMs and configs, the Azure Portal includes a built-in **Auto-shutdown** feature at a specified time. It is a handy safeguard against forgotten dev/test VMs.

Verify:

- Which VMs and subscriptions have it enabled.
- Shutdown time, timezone, and pre-shutdown notifications if configured.
- Whether Auto-shutdown actually places the VM into **Stopped (deallocated)**.
- Whether overnight jobs, patch windows, or late users require access.
- Who is allowed to modify or disable the schedule.

Auto-shutdown **does not handle scheduled auto-start**. Combining scheduled starts and deallocations requires an external automation solution.

### 15.2. Azure Automation, Logic Apps, Functions, or Schedulers

A clean automation architecture might look like:

~~~mermaid
flowchart TD
    S["Work-hours scheduler"] --> I["Managed identity / execution principal"]
    I --> Q{"Approved tag and scope?"}
    Q -->|Yes| A["Runbook: start or deallocate"]
    Q -->|No| E["Skip + log reason"]
    A --> V["Verify Power state"]
    V --> H["Health check / alert"]
    H --> L["Logs and cost reporting"]
~~~

Design principles:

1. Use a **managed identity** or governed service principal—never embed passwords/secrets in code.
2. Grant only required permissions scoped to exact VMs or resource groups.
3. Target only VMs whose owners explicitly **opt in**, e.g., via standardized tags.
4. Maintain explicit exclusions for production, overnight runners, backups, and critical jobs.
5. Send pre-shutdown notices and provide a snooze/override mechanism.
6. Bound retries and avoid duplicate or conflicting schedule runs.
7. Log every action, final state, error, and responsible owner.
8. Run post-start health checks; never treat `Running` power state as done.
9. Account for costs of Automation, Logic Apps, or monitoring if applicable.

### 15.3. Avoid “Sweep and Shut Down Everything”

A scheduler that blindly deallocates every VM in a subscription at 18:00 is hazardous. It can disrupt:

- Production web/API VMs.
- Active databases or batch processing jobs.
- CI/CD runners mid-build.
- VMs serving public users in other timezones.
- Scheduled backup/restore or maintenance VMs.
- Machines supporting live customer sessions.

Enforce an **explicit opt-in** policy, such as tag `Schedule=office-hours` alongside `Owner`, `Environment`, `Timezone`, and an approved schedule. Even then, tags are editable metadata—pair schedulers with strict RBAC and exclusion guardrails.

## 16. Safe Manual Runbook Example with Azure CLI

Before automating, test the workflow on **a single VM**. The example below targets one exact lab VM/scope—never scan an entire subscription blindly.

### 16.1. Inspect State Before Acting

~~~bash
az login
az account set --subscription "<subscription-id>"

RG="rg-vm-lab"
VM="vm-demo-01"

az vm show \
  --resource-group "$RG" \
  --name "$VM" \
  --show-details \
  --query "{name:name,powerState:powerState}" \
  --output json
~~~

### 16.2. Deallocate After Hours

Before running, confirm no critical batch jobs, backups, or transactions are active, the app is gracefully quiesced, and the owner agrees.

~~~bash
az vm deallocate \
  --resource-group "$RG" \
  --name "$VM"

az vm show \
  --resource-group "$RG" \
  --name "$VM" \
  --show-details \
  --query "powerState" \
  --output tsv
~~~

Expect **VM deallocated**. If it remains Running/Stopping or errors out, **do not mark the runbook step successful**.

### 16.3. Start Before Business Hours

~~~bash
az vm start \
  --resource-group "$RG" \
  --name "$VM"

az vm show \
  --resource-group "$RG" \
  --name "$VM" \
  --show-details \
  --query "powerState" \
  --output tsv
~~~

Next verify the application—for example, if a web service runs on the VM:

~~~bash
# Illustrative check only; use actual DNS/service name and TLS
curl --fail --show-error --max-time 10 https://app.example.internal/health
~~~

The hostname is an example. Also verify DNS, network path, certificates, firewalls, and dependencies. If your workstation lacks network reachability to the service, use an organization-approved health check channel instead of exposing a new public endpoint.

### 16.4. Criteria for Production Scripts

A production automation script must enforce these **non-negotiable steps**:

- Verify the VM exists with the right subscription/resource ID and approved opt-in tags.
- Skip any VM outside the scheduler's governed scope.
- Check current state to avoid redundant commands.
- Enforce bounded timeouts, retries, and concurrency limits.
- Before deallocating, confirm maintenance, backup, and active-job safety.
- Wait for final power state and log exact outcomes/exceptions.
- After starting, execute an application-level health check.
- Alert if a VM fails to deallocate on schedule or fails readiness after start.

Illustrative pseudo-code:

~~~text
for each approved VM in schedule:
    if maintenance exception or outside approved scope:
        SKIP and LOG

    if action == deallocate:
        confirm quiesce conditions
        request deallocate if appropriate
        verify PowerState/deallocated
        alert if not reached

    if action == start:
        request start if appropriate
        verify PowerState/running
        run application health check
        alert if not healthy
~~~

This pseudo-code illustrates logic flow and **is not a ready-to-run script**.

## 17. Access Control for Schedulers

An automation allowed to start/deallocate VMs controls live infrastructure, so enforce **least privilege**.

### 17.1. Scopes to Distinguish

| Scope | Blast radius |
|---|---|
| Single VM | Only that specific VM |
| Resource group containing VMs | Can affect multiple VMs in the group depending on role |
| Subscription | Broad impact across subscription resources |
| Management group | Multi-subscription scope; use only when strictly required |

For a lab, scoping permissions to a dedicated resource group can work. In production, use a custom role containing only needed actions such as **Microsoft.Compute/virtualMachines/start/action**, **deallocate/action**, and appropriate read permissions—never grant subscription-wide Owner.

Rights to edit Automation accounts, manage role assignments, and operate VMs are distinct responsibilities. When a scheduler uses a managed identity, explicitly grant the role assignment to that identity; creating an identity alone grants zero VM permissions.

### 17.2. Auditing and Guarding Against Unintended Schedules

- Retain logs identifying which user/identity triggered Start/Stop/Deallocate.
- Inspect Azure Activity Log for resource-level actions.
- Alert if any production VM is deallocated outside approved change windows.
- Restrict who can edit schedule tags, runbooks, and role assignments.
- Include a kill switch to pause automation during incidents or overtime work.
- Monitor drift: actual power state diverging from expected schedule state.

Never decide whether to stop a VM by parsing substrings like **-prod** or **-test** in its name. Use governed metadata and owner registries.

## 18. Verifying Cost Impact After Deallocation

To validate FinOps outcomes, checking power state alone is not enough—reconcile against billing/usage data.

### 18.1. Azure Cost Management

In the Azure Portal:

1. Open **Cost Management + Billing** or **Cost Management** at an authorized scope.
2. Navigate to **Cost analysis**.
3. Select the exact subscription/resource group or filter by resource ID/tag as available.
4. Pick date ranges before and after enabling the schedule.
5. Group by **service name**, **resource**, **meter**, or available dimensions.
6. Separate **Virtual Machines compute** charges from **Managed Disks**, **Backup**, **Networking**, and other services.
7. Review how Reservations or Savings Plans affect amortized vs. actual cost allocation.
8. Record the baseline and compare once usage data settles.

Cost data has **ingestion latency**. Never conclude “deallocation failed to save money” immediately after stopping a VM just because charts still show earlier hours.

### 18.2. Minimal KPI Dashboard Example

| KPI | How measured | Meaning |
|---|---|---|
| After-hours dev/test deallocation rate | Compliant VMs / scheduled VMs | Policy adherence |
| Reduced compute hours | Allocated hours before vs. after | Technical efficiency |
| Actual compute spend | Billed charges by meter and period | Financial impact |
| Remaining disk spend | OS/data disk charges | Why total bill does not hit zero |
| Start success rate | Healthy starts / total start attempts | User experience reliability |
| Time from Start to Healthy | Application/health logs | Readiness before workday begins |
| Unscheduled VM starts | Activity Log / scheduler events | Unexpected cost risk |

KPIs are meaningful only with an explicit **in-scope VM inventory** and **observation window**. Never judge success from an entire subscription's total bill while other services fluctuate.

### 18.3. If a VM Is Deallocated Yet the Bill Barely Drops

Check in order:

1. Was the VM truly in **PowerState/deallocated** during the expected hours?
2. Did the scheduler restart it early due to a timezone bug or another Automation rule?
3. Are other VMs in the same resource group still running 24/7?
4. Are you looking at **compute usage**, **commitments**, or total cost?
5. Do managed disks, snapshots, Public IPs, Load Balancers, Bastion, or log retention still exist?
6. Are there Marketplace/licensing fees or fixed Reserved Instance/Savings Plan commitments?
7. Has Cost Management finished ingesting the full period?
8. Was the VM resized larger or shifted in workload so fewer hours cost more per hour?

Never claim a VM is still burning compute just because the resource group's total spend is non-zero.

## 19. Production, HA, and Automatically Managed VMs

### 19.1. High-SLA Production

If a VM serves a 24/7 application, nightly deallocation is generally inappropriate. Instead consider:

- Multi-instance architectures with health probes and appropriate zone fault tolerance.
- Autoscaling out/in based on load using supported platforms rather than abruptly stopping standalone VMs.
- Right-sizing VMs, optimizing disks, and choosing pricing commitments after measuring load.
- Moving non-persistent tasks to managed services or serverless compute.
- Planning maintenance windows and controlled failover.

Never sacrifice production RTO/SLO and availability solely to shave off running hours.

### 19.2. Virtual Machine Scale Sets (VMSS)

VMSS governs **desired instance counts**, autoscaling, health repair, and upgrades centrally. Manually changing power state on individual instances can conflict with controller/autoscale actions.

With VMSS:

- Decide whether you want to scale **instance count** down or pause a specific instance.
- Inspect orchestration mode, autoscale rules, and health policies.
- Account for persistent disks, images, networking, and surviving resources.
- Never blindly run standalone-VM deallocate scripts across all VMSS instances.

### 19.3. Batch Workloads, CI/CD, and On-Demand VMs

For VMs dedicated to scheduled pipelines or batch jobs, you can:

- Start ahead of the job window.
- Wait for guest agents and health checks.
- Run the job, verify completion status, and upload durable artifacts/logs.
- Stop services cleanly.
- Deallocate.
- Verify final power state and alert on failures.

This prevents **killing a machine mid-job**, though schedules must still handle retries or jobs running overtime.

### 19.4. Hibernation Differs from Standard Deallocation

Certain VM sizes and OSes support **hibernation**, preserving memory state via platform mechanisms before the VM stops running. This is not enabled by default on every VM.

To resume sessions faster than a cold application boot, verify:

- Supported VM size, OS, and disk types.
- Storage requirements and disk capacity for memory state.
- Actual power state and billing rules.
- Restrictions on resizing or modifying hibernated VMs.
- Resume workflow and data security controls.

Do not equate hibernation with **az vm deallocate** regarding in-memory state.

## 20. Common Errors and Fixes

| Symptom | Common mistake / cause | Fix |
|---|---|---|
| VM shut down inside Windows yet compute charges continue | VM sits in **Stopped (allocated)** | Deallocate via Azure and confirm `PowerState/deallocated` |
| `az vm stop` finishes yet compute keeps billing | Stop does not release allocation | Run `az vm deallocate` when cost savings are desired |
| Portal says Stopped and billing is unclear | Confusing UI label with underlying state | Query power state via instance view or CLI |
| `az vm deallocate` returns early before VM deallocates | Used `--no-wait` or transitional state | Poll until final state and inspect any errors |
| VM fails to start again | Capacity, quota, permissions, policy, or deployment error | Check error message, Activity Log, and VM size/zone limits |
| VM starts yet SSH/RDP fails | IP/DNS changed, NSG, firewall, or boot incomplete | Check NIC/Public IP, effective rules, and boot diagnostics |
| VM Running yet web/API unhealthy | Service not up or dependency unready | Check guest logs and health probes |
| Cache data vanished after deallocate | Stored on temporary disk or ephemeral OS disk | Move persistent data to durable storage; rebuild cache on start |
| Disk charges persist | Managed disks/snapshots still exist | Review storage costs and data lifecycle |
| Public IP charges persist | IP resource still allocated | Check SKU, address retention need, and safe deletion rules |
| After-hours VM turns back on | Competing automation, operator, or wrong schedule | Audit Activity Log, runbook logs, timezone, and RBAC |
| Scheduler accidentally stops production | Faulty scope/tag/owner or missing exclusion policy | Halt automation, restore VMs, enforce opt-in and guardrails |
| Savings Plan does not lower total bill immediately | Commitment spend remains constant | Analyze commitment utilization and amortized cost |
| Backups/monitoring fail after deallocation | Services depend on guest agent / VM online | Review platform support, backup schedules, and alert tuning |
| VM starts slowly | Extensions, OS boot, capacity, or app warm-up | Measure time-to-healthy, streamline startup, start earlier |

### 20.1. When Commands Return Errors

Never hammer Start/Stop/Deallocate in rapid loops. Follow a safe sequence:

1. Read the complete error message from CLI/Portal.
2. Check if another management operation is still in progress.
3. Inspect instance view and provisioning state.
4. Check Activity Log around the failure timestamp.
5. Verify Azure RBAC permissions/scope and Azure Policies.
6. Check quotas/capacity/region if an allocation error appears.
7. Apply approved runbook actions—never delete disks or VMs blindly to clear unknown errors.
8. After recovery, verify final power state, health, and billing.

## 21. Data Protection and Safe Shutdown Procedures

Deallocation affects the entire workload, not just the invoice. For VMs hosting databases or transactional systems:

### 21.1. Pre-Shutdown Checklist

- [ ] Notified users or entered an approved maintenance window.
- [ ] Stopped accepting new write requests if required by the app.
- [ ] Completed or safely terminated in-flight jobs and transactions.
- [ ] Flushed buffers and taken checkpoints/backups per app procedure.
- [ ] Confirmed no restore, patching, or deployment is running.
- [ ] Confirmed critical data does not reside solely on the temporary disk.
- [ ] Recorded VM ID, power state, IPs, and operator.
- [ ] Prepared a recovery plan if restart fails.

### 21.2. Post-Start Checklist

- [ ] Power state is Running and provisioning reports no critical errors.
- [ ] OS/data disks, drive letters, and mounts match expectations.
- [ ] DNS/IPs and network connectivity are valid.
- [ ] Identity, secrets, and authentication work properly.
- [ ] Databases, queues, and file services accept traffic.
- [ ] Business health checks pass.
- [ ] Logs and alerts show no continuous errors.
- [ ] Backup, monitoring, and automation schedules resume normally.

**Emphasis:** disk persistence does not equal application consistency; always perform workload-level data protection steps.

## 22. Team-Wide VM Cost Optimization Checklist

- [ ] Classified VMs across production, dev, test, sandbox, and scheduled workloads.
- [ ] Documented clear owners, SLAs, operating windows, and system dependencies.
- [ ] Operators clearly distinguish Stopped (allocated) from Stopped (deallocated).
- [ ] Verified Portal Stop, CLI stop, PowerShell, and guest OS shutdown behaviors.
- [ ] Cost-saving target VMs are **deallocated**, not merely shut down inside the guest.
- [ ] Scripts wait for final power state and log errors rather than trusting async submission exit codes.
- [ ] Disks, Public IPs, backups, logging, licensing, and commitments are accounted for separately.
- [ ] Dynamic IPs and temporary/ephemeral disks are evaluated prior to deallocation.
- [ ] Post-start health checks and capacity-failure fallbacks exist.
- [ ] Schedulers act strictly on opt-in VMs with least privilege and explicit production exclusions.
- [ ] Timezones, holidays, batch jobs, and maintenance windows are factored in.
- [ ] Baseline compute hours and before/after Cost Management reports exist.
- [ ] Critical data has backups, tested restores, and shutdown runbooks.
- [ ] Unexpected state changes trigger Activity Log alerts.
- [ ] Right-sizing and alternative compute purchasing models are evaluated for 24/7 VMs.

## 23. Hands-On Exercises

### Exercise 1: Explain the Difference

A Linux VM is shut down using:

~~~bash
sudo shutdown -h now
~~~

The VM stops responding to SSH. Answer:

1. Which power state is most likely shown?
2. Is VM compute usage billing guaranteed to have stopped?
3. Which Azure CLI command is needed to deallocate it?
4. Which two commands can verify the final state?
5. Which charges continue after deallocation?

### Exercise 2: Practice the Three States

In a lab resource group containing a VM with a **managed OS disk** and no critical data on the temporary disk:

1. Inspect state with **az vm show --show-details**.
2. Start and wait for Running.
3. Run **az vm stop** and inspect the state.
4. Run **az vm deallocate** and inspect the state.
5. Start again and verify data on the managed OS disk.
6. Explain why temporary disk data must not be used to prove persistence.

Never run this on production VMs or machines with active jobs.

### Exercise 3: Calculate Avoided Compute Hours

A VM is used 10 hours/day, 20 days/month. Assume a 30-day month:

- How many allocated compute hours occur if the VM runs continuously?
- How many compute usage hours occur if started only during usage hours and deallocated otherwise?
- At a hypothetical compute rate of 0.30 USD/hour, what is the compute difference?
- Why does that difference not equal total net bill savings when Managed Disks and a Savings Plan exist?

### Exercise 4: Design an Automation Schedule

A QA team manages 6 test VMs. Design:

- Tags for schedule opt-in, owner, and timezone.
- Start schedule before business hours and Deallocate schedule after hours.
- Safeguards preventing stopping a VM mid-test run.
- Least-privilege RBAC for the managed identity.
- PowerState verification and health check steps.
- Alerts if a VM fails to deallocate on schedule or fails to start.

### Exercise 5: Diagnose a Bill

After scheduling Stop at 18:00, Cost Management still shows sizable total spend in the resource group. Build a breakdown across meters: VM compute, OS/data disks, Public IPs, backups, logs, and commitments. Propose how to prove the VM actually deallocated on schedule.

### Exercise 6: Evaluate Start Failure Risk

An internal app must be ready by 08:30. The VM is deallocated each evening, but one morning Azure reports insufficient capacity for the VM size/zone. Outline immediate mitigation and a long-term design balancing cost with SLOs without promising instant startup from deallocation.

### Self-Check Questions

1. Can a VM have provisioning state Succeeded and power state Deallocated at the same time?
2. Does stopping from inside the guest OS stop standard VM compute billing?
3. How does Azure CLI **az vm stop** differ from **az vm deallocate**?
4. What states do Azure Portal Stop and default `Stop-AzVM` typically produce?
5. Are managed disks deleted when a VM is deallocated?
6. Why must critical data never live on the temporary disk?
7. Why can a static Public IP still incur charges while a VM is deallocated?
8. Why is Running insufficient as the sole proof an application is ready?
9. Why might a deallocated VM fail to Start later?
10. Why do Reservations and Savings Plans complicate cost-saving calculations?
11. When should you prefer scheduled automation over manual Stop actions?
12. Does deleting a VM behave like deallocating regarding data and costs?

## 24. References

- [Azure Virtual Machines — States and billing](https://learn.microsoft.com/azure/virtual-machines/states-billing)
- [Azure CLI: az vm command reference](https://learn.microsoft.com/cli/azure/vm)
- [Azure PowerShell: Start-AzVM](https://learn.microsoft.com/powershell/module/az.compute/start-azvm)
- [Azure PowerShell: Stop-AzVM](https://learn.microsoft.com/powershell/module/az.compute/stop-azvm)
- [Azure VM ephemeral OS disks](https://learn.microsoft.com/azure/virtual-machines/ephemeral-os-disks)
- [Azure Managed Disks overview](https://learn.microsoft.com/azure/virtual-machines/managed-disks-overview)
- [Azure Cost Management overview](https://learn.microsoft.com/azure/cost-management-billing/costs/overview-cost-management)
- [Azure Reservations overview](https://learn.microsoft.com/azure/cost-management-billing/reservations/save-compute-costs-reservations)
- [Azure Virtual Machines pricing](https://azure.microsoft.com/pricing/details/virtual-machines/)
