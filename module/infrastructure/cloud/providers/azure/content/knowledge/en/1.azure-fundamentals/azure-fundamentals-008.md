# Quotas, Service Limits, and Limit Increase Requests

## 1. Why Check Quotas Before Deploying on Azure?

An application can be properly designed, have valid network configuration, and hold full access permissions, yet still fail to create new resources due to insufficient quota. This commonly occurs when increasing VM counts, expanding test environments, deploying a new version alongside an old one, or activating standby systems.

In the **Azure Fundamentals** chapter, quota management connects knowledge of subscriptions, resource groups, and Microsoft Entra ID with deployment, monitoring, and cost control. Operators need to identify exactly which resource is limited, where the limit applies, and how it can be changed.

After this lesson, you will be able to:

- Distinguish quotas from capacity, performance limits, and throttling.
- Identify the scope of a limit rather than looking only at the service name.
- Read usage and limit values to calculate remaining headroom.
- Plan limits for scaling, deployments, and recovery.
- Prepare, submit, and verify a quota increase request.
- Incorporate quota checks into Azure application operations workflows.

Numbers in the examples below are fabricated to illustrate calculations, **not Azure default limits**. Actual limits must be checked in the specific subscription, region, and documentation for the service in use.

## 2. Easily Confused Concepts

### 2.1. Quota, Usage, and Limit

A **quota** is a mechanism that limits the amount of a resource or consumption within a defined scope. The **limit** is the current ceiling applied to that quota. **Usage** is the amount counted against the meter at the time of observation.

For example, a vCPU quota with usage of 24 and a limit of 32:

```text
Remaining = limit - usage = 32 - 24 = 8 vCPUs
Utilization rate = usage / limit × 100% = 75%
```

The 75% figure here is the **limit** utilization rate, not CPU utilization inside the virtual machine. An idle VM still consumes quota according to its resource size.

Azure has quotas for many resource types; there is no single quota number representing an entire subscription. An overview of the mechanism and access points is described in [Azure Quotas overview](https://learn.microsoft.com/en-us/azure/quotas/quotas-overview).

### 2.2. Types of Limits and How to Handle Them

| Concept | Practical meaning | Appropriate approach |
| --- | --- | --- |
| Adjustable quota | Current ceiling has a process to request an increase | Determine required level and submit a request per service |
| Fixed maximum limit | Constraint without a standard increase mechanism | Change how resources are partitioned or adjust architecture |
| SKU or tier limit | Capability of the selected service plan | Evaluate upgrading tier, changing SKU, or sharding load |
| Capacity | Physical Azure resources available to allocate at the target location | Consider an appropriate alternative size, zone, or region |
| Request rate limit | Number of operations accepted within a time window | Reduce concurrency, throttle traffic, and retry properly |
| Performance limit | Ceiling on throughput, IOPS, connections, or processing capacity | Measure bottlenecks and optimize or scale the right component |

The term **soft limit** usually refers to a ceiling you can request to adjust; **hard limit** usually refers to a maximum ceiling. However, labels in the UI are not enough to draw conclusions. You must read the conditions of the specific service. An item not allowing direct increases in Quotas may mean going through support; it does not prove every fixed limit can be raised. Cross-check [Azure subscription and service limits, quotas, and constraints](https://learn.microsoft.com/en-us/azure/azure-resource-manager/management/azure-subscription-service-limits).

### 2.3. Quotas, Access Permissions, and Cost Are Three Separate Things

Azure RBAC permissions answer which identity is allowed to perform an operation. Quotas answer how many more resources that scope is still allowed to allocate. Someone with permission to create a VM can still be blocked due to lacking vCPU quota.

Increasing a quota does not itself create extra resources and does not make an application scale automatically. Requesting a quota increase incurs no charge; charges arise from resources consumed and their associated billing models. Refer to the [cost notes in Azure Quotas](https://learn.microsoft.com/en-us/azure/quotas/quotas-overview).

Therefore, govern simultaneously:

- Permissions to deploy and modify resources.
- Sufficient limits for forecasted demand.
- Scaling bounds on the application and cost-tracking processes.

Do not use vCPU quota numbers as a direct conversion into monetary budget: SKUs, disks, storage, data transfer, and accompanying services are priced differently.

## 3. Identify the Exact Scope of a Limit

A limit only has meaning when paired with its scope and unit. An inspection record should capture at minimum:

```text
Subscription:
Resource provider or service:
Region or global scope:
Quota / counter name:
VM family, SKU, or tier if applicable:
Unit:
Usage:
Limit:
Timestamp of measurement:
```

Azure enforces quotas at different scopes depending on resource type; limits exist per subscription, region, or resource group. When an error occurs, read the counter name and scope in the message. See [how to identify exceeded quotas](https://learn.microsoft.com/en-us/azure/azure-resource-manager/troubleshooting/error-resource-quota).

### 3.1. A Resource Group Does Not Create New Subscription Quota

Suppose `rg-orders-prod` and `rg-orders-test` share one subscription and both deploy VMs in one region. If blocked by a subscription-level regional vCPU quota, creating another resource group will not create an independent quota allowance for that quota type.

Similarly, moving a VM to another availability zone in the same region does not change the scope of a regional vCPU quota. Changing zones may relate to allocation availability, which is a capacity issue.

This follows directly from the quota's scope: the mitigation must change an element inside the counter's scope or raise the limit of that exact counter.

### 3.2. List the Application's Dependencies

For a web application running on Azure, build a checklist of components to inspect before scaling:

| Planned component | Details to look up |
| --- | --- |
| VMs or VM Scale Sets | vCPUs, VM family, VM count, and temporary deployment needs |
| AKS using VM nodes | Node pool vCPUs, surge nodes during upgrades, and networking resources |
| Virtual Network and connectivity | Network resource counters and remaining IP address space |
| Storage | Account counts, capacity, and performance targets for the storage kind |
| Database service | SKU, capacity, connections, throughput, and corresponding scaling steps |
| Application identity | Required Azure RBAC permissions and relevant identity service limits |
| Deployment tooling | API call frequency, concurrency level, and retry policy |

This table is a design checklist and does not assert that all items can be raised via a single Quotas request. For instance, running out of IP addresses in a subnet requires revisiting network design; increasing vCPU quota will not solve that issue.

## 4. Understand Compute's Two Layers of vCPU Quota

For standard VMs, Azure checks vCPU quota across two tiers within each subscription and region:

1. **Total Regional vCPUs**: total vCPUs in the region.
2. **VM-family vCPUs**: vCPUs belonging to the corresponding VM family.

A new VM must fit within both limits. Raising the regional total quota while the VM family remains short will still block VM creation. When a VM-family quota increase request is approved, Azure has a mechanism to raise the associated regional total quota; afterward, still re-verify both values. See [Increase VM-family vCPU quotas](https://learn.microsoft.com/en-us/azure/quotas/per-vm-quota-requests).

### 4.1. Example Where Regional Total Is Sufficient but VM Family Is Short

Suppose a subscription has the following numbers:

| Counter | Current usage | Limit | Remaining |
| --- | ---: | ---: | ---: |
| Total Regional vCPUs | 48 | 64 | 16 |
| A target VM family | 24 | 32 | 8 |

The application wants to add four VMs, each with 4 vCPUs:

```text
Additional demand = 4 × 4 = 16 vCPUs

Regional total after deployment = 48 + 16 = 64
VM family after deployment      = 24 + 16 = 40

64 <= 64: satisfies regional total condition
40 > 32: fails VM family condition
```

You cannot conclude deployment will succeed merely because Total Regional vCPUs still has 16 remaining. You must raise the VM family limit, reduce the number of new VMs, or evaluate another VM family that meets application requirements.

### 4.2. Additional Points to Check

- **Spot has separate quotas.** Do not use remaining standard quota to infer ability to create Spot VMs. Look up [Spot vCPU quotas](https://learn.microsoft.com/en-us/azure/quotas/spot-quota).
- **VM count and vCPU count are different counters.** Read the unit of each row carefully.
- **Do not assume deallocating frees vCPU quota.** Compute documentation counts both allocated and deallocated VMs against quota. Check actual usage before and after changes; delete unneeded VMs only after reviewing data, configuration, and recovery procedures. Refer to [Check vCPU quotas](https://learn.microsoft.com/en-us/azure/virtual-machines/quotas).

A VM with low CPU utilization does not automatically return vCPU quota. To reduce provisioned quota consumption, evaluate resizing or removing excess resources according to operational procedures.

## 5. Check Usage and Limits Before Making Changes

### 5.1. Checking in the Azure Portal

A common inspection flow is:

1. Confirm you are in the right Microsoft Entra directory and subscription.
2. Search for **Quotas** in the portal and choose the appropriate resource provider.
3. Open **My quotas**, filtering by subscription and region.
4. Locate the counter to check; record usage, limit, unit, and whether an increase can be requested.
5. For Compute, read both the regional total and the intended VM family.
6. Cross-check services that do not appear in this view using their dedicated usage or limits pages.

Button names and layouts may vary by provider. The request submission flow is documented by Microsoft in [Request a quota increase in the Azure portal](https://learn.microsoft.com/en-us/azure/quotas/quickstart-increase-quota-portal).

Capture full-scope figures rather than jotting down a bare number like "8 left." That number must be accompanied by quota name, unit, subscription, region, and inspection timestamp.

### 5.2. Read-Only Azure CLI Examples

The commands below are for PowerShell with the Azure CLI signed in. Replace the subscription ID with an actual value and pick the region of the environment to inspect:

```powershell
$subscriptionId = '<subscription-id>'
$region = 'southeastasia'

az account show --subscription $subscriptionId --query "{Subscription:name,SubscriptionId:id,TenantId:tenantId}" --output table

az vm list-usage --subscription $subscriptionId --location $region --output table

az vm list-usage --subscription $subscriptionId --location $region --query "[].{Quota:name.localizedValue,Key:name.value,Used:currentValue,Limit:limit,Unit:unit}" --output table
```

The `az vm list-usage` command retrieves Compute usage data in the specified region and does not represent every limit in Azure. Refer to [Azure CLI: az vm list-usage](https://learn.microsoft.com/en-us/cli/azure/vm#az-vm-list-usage).

In the output:

- `name.localizedValue` is the readable display name.
- `name.value` is the counter's identifier name, useful when saving check configurations.
- `currentValue` is the returned usage.
- `limit` is the currently enforced ceiling.
- `unit` helps avoid confusing resource count with vCPU count.

These fields are described in the [Compute Usage REST API](https://learn.microsoft.com/en-us/rest/api/compute/usage/list).

When checking network resource usage in the same region:

```powershell
az network list-usages --subscription $subscriptionId --location $region --output table
```

Refer to [Check Azure network resource usage against limits](https://learn.microsoft.com/en-us/azure/networking/check-usage-against-limits). This command also does not replace checking IP address capacity inside subnets or detailed limits of individual network configurations.

### 5.3. Read Numbers in Context

Usage is a point-in-time snapshot of the system. In a shared environment, another pipeline could allocate resources after you check.

Therefore, pre-deployment checks catch shortages early but do not reserve quota exclusively for a single run. For large change waves, coordinate deployment schedules and sum the demand of teams sharing the subscription.

If a limit is 0, do not calculate percentages with ordinary division. Record the status clearly and check usage conditions for that quota and the service's support workflow before incorporating it into a plan.

## 6. Calculate Limits for Peak Demand

A common planning error is calculating only steady-state resources. Limits must accommodate temporary peaks during changes.

Sources of extra demand include:

- Autoscale reaching its maximum designed level.
- Old and new resources coexisting simultaneously during a blue-green deployment.
- Additional VMs or nodes during a rolling upgrade.
- Test environments running in parallel.
- Recovery or failover traffic arriving from an impaired environment.

### 6.1. Planning Formula

For a specific counter:

```text
Peak demand =
    usage of retained resources
  + new resources coexisting at peak time
  + other concurrent demand within the same scope
```

Do not double-count old resources already included in current usage. If a new workload replaces an old workload, model the window when both versions coexist.

A target utilization ratio can be used to create operational headroom:

```text
Target limit >= ceil(peak demand / target utilization ratio)
```

For example, choosing an 80% target utilization ratio means wanting peak demand to consume at most 80% of the limit. This is a planning choice in the example, not a mandatory Azure rule. For resources provisioned in groups, also round up appropriately to match VM sizes or service-supported increment units.

### 6.2. Example with Temporary Resources During Deployment

Continuing the example from section 4:

- The target VM family currently uses 24 vCPUs.
- Other VM families use 24 vCPUs and remain unchanged.
- The application will grow to 10 VMs of the same family, 4 vCPUs each.
- During updates, the rollout may create up to two temporary VMs.
- Unused old VMs are removed following proper procedures.

Calculate demand:

```text
VM family in steady state   = 10 × 4 = 40 vCPUs
Temporary update portion    =  2 × 4 =  8 vCPUs
VM family peak              = 40 + 8 = 48 vCPUs

Regional total peak         = 24 + 48 = 72 vCPUs

If using an 80% target level:
Minimum VM family limit     = ceil(48 / 0.8) = 60 vCPUs
Minimum regional limit      = ceil(72 / 0.8) = 90 vCPUs
```

The result shows that a regional total quota of 64 suffices for steady state `24 + 40`, yet is insufficient for the update peak of 72. The VM family quota of 32 is not even enough for steady state.

The values 60 and 90 are planning inputs. Submit requests using the actual units and options Azure provides, then verify the approved limits satisfy both conditions. Do not enter 28 meaning "increase from 32 to 60" when a form asks for **new limit**; in that field, enter the desired total limit of 60.

### 6.3. Standby in Another Region

If an application has a recovery strategy in a second region, calculate quotas separately for the destination subscription and region. An increase in the primary region does not automatically raise all other regions. This behavior is noted in [Increase regional vCPU quotas](https://learn.microsoft.com/en-us/azure/quotas/regional-quota-requests).

In the recovery plan, document the load the destination region must absorb, workloads already running there, and resources needed during recovery. A standby region with almost zero usage can still lack quota for a large failover wave.

## 7. Prepare a Limit Increase Request

### 7.1. Conditions and Permissions

Per the Azure Quotas quickstart, the portal request flow applies to paid subscriptions and requires an account with the Contributor role or a role containing equivalent permissions. Do not infer that Owner is the only option; with custom authorization models, governance teams should map the exact actions and scope required. See [quota increase request prerequisites](https://learn.microsoft.com/en-us/azure/quotas/quickstart-increase-quota-portal).

Ability to create support requests is a separate permission to verify when handling escalates to support. A missing action button may stem from permissions, subscription type, or the selected quota itself, rather than a single cause.

### 7.2. Data to Have Ready Before Submitting

| Information | Purpose |
| --- | --- |
| Subscription ID and associated tenant | Identify the exact environment and administrative identity |
| Service, region, quota name, unit | Identify the exact counter to modify |
| Current usage and limit | Show actual current state |
| Desired total limit | Avoid confusing with incremental amount |
| Relevant VM family or SKU | Avoid submitting for the wrong VM family |
| Steady-state and peak demand | Explain how the requested level was calculated |
| Target date of use | Help coordinate deployment |
| Alternative option | Prepare in case the desired level is not granted |

Example request content using the calculated figures:

```text
Purpose: scale order-processing application and perform updates with temporary VMs.
Subscription: <subscription-id>
Region: southeastasia
Resource type: standard VM
VM family quota: <actual VM family name/identifier>
Current: usage 24 vCPUs, limit 32 vCPUs
Proposed total VM family limit: 60 vCPUs

Expected VM family peak:
10 VMs x 4 vCPUs + 2 temporary VMs x 4 vCPUs = 48 vCPUs.

Regional total:
Other families use 24 vCPUs.
Expected peak 72 vCPUs; regional planning target limit is 90 vCPUs.

Required by date: <target date>
Fallback option: <compatibility-evaluated size/region>
```

Do not include passwords, access tokens, connection strings, or customer information in the justification text. Subscription IDs and request IDs should be handled according to organizational information-handling procedures.

### 7.3. Submit and Track

General workflow:

1. Open Quotas and select the right subscription, provider, and region.
2. Select the quota; if a direct adjustment flow is available, enter the desired total limit.
3. Review the information and submit the request.
4. Save the request ID and status.
5. If the quota lacks a direct increase flow or the request is not fulfilled, use the provided support flow.
6. Wait for the outcome and re-read usage/limit at the right scope.
7. Proceed with deployment per the approved plan only after actual values align.

Some requests are processed quickly, though approval time should not be treated as a constant across all services or regions. Quota grants depend on review; having a limit also does not guarantee capacity. Microsoft describes these conditions in [Quotas overview](https://learn.microsoft.com/en-us/azure/quotas/quotas-overview).

A successfully submitted request does not mean the limit has changed yet. Distinguish these states:

```text
Submitted -> Processing -> Approved or Not fulfilled
                                  |
                                  v
                        Re-read actual limit
                                  |
                                  v
                        Verify deployment plan
```

If an outcome only partially fulfills the request, recalculate headroom and peak demand. Avoid submitting multiple duplicate requests without tracking relationships between request IDs.

## 8. Distinguish Quota Errors, Capacity Errors, and Throttling

Increasing the right quota is a valid fix; reflexively requesting a quota increase for every deployment error often slows down resolution.

### 8.1. Diagnostic Table

| Symptom | What to check next | Initial mitigation |
| --- | --- | --- |
| Error details mention quota, usage, limit, or additional vCPUs needed | Exceeded scope and counter | Reduce demand, free eligible resources, or request an increase for the right quota |
| Quota is sufficient but error says size cannot be allocated at chosen location | SKU, region, zone, and deployment constraints | Evaluate alternative allocation options |
| HTTP 429 | Nested error code, headers, and related operation | Handle by root cause; throttle and retry appropriately |
| Authorization or permission denied | Identity, Azure RBAC, and operation scope | Adjust permissions following process |
| Policy blocks configuration | Policy assignment and denial reason | Choose compliant configuration or process a valid exception |
| SKU does not support required property | Service documentation and configuration | Switch SKU, tier, or deployment approach |

Specific error names may vary by provider. Do not rely on a single outer error code as sole evidence. For deployment errors, inspect inner errors, target resource, region, correlation ID, and timestamp.

### 8.2. Quotas Do Not Reserve Capacity

A quota permits a subscription to provision resources up to an approved limit; capacity is Azure's actual available hardware at the allocation site. You can still hit capacity shortages while holding sufficient quota.

If evaluating an alternative size, zone, or region, also verify application compatibility, performance, networking, data, and recovery requirements. When a resource reservation mechanism is needed, examine **On-demand Capacity Reservation** with its specific support conditions and costs. Refer to [Quota and capacity](https://learn.microsoft.com/en-us/azure/virtual-machines/quotas#quota-and-capacity).

Do not switch regions solely to bypass an error while overlooking latency to databases, network paths, and data residency requirements.

### 8.3. Throttling Requires Pacing Calls

When Azure Resource Manager rate-limits requests, the response may be HTTP `429 Too Many Requests` with `Retry-After`. Read details carefully because some providers also use 429 for other transient conditions. See [Azure Resource Manager throttling](https://learn.microsoft.com/en-us/azure/azure-resource-manager/management/request-limits-and-throttling).

Guidance for clients and pipelines:

- Honor `Retry-After` when returned.
- Use bounded exponential backoff with jitter so multiple clients do not retry in lockstep.
- Limit concurrent operations and reduce unnecessary polling.
- Check built-in SDK retry mechanisms to avoid stacking multiple retry layers.
- For state-changing operations, check state before repeating to avoid creating duplicate work.

Increasing vCPU quota does not increase API call rate limits. Conversely, retrying continuously does not solve an exhausted resource quota: the condition where usage exceeds limit has not changed.

## 9. Monitor Quotas as Part of Operations

### 9.1. Track Both Percentage and Remaining Amount

Two quotas both at 80% utilization can mean very different things:

```text
Quota A: usage 8, limit 10     -> 2 remaining
Quota B: usage 800, limit 1000 -> 200 remaining
```

If a scaling event requires 16 units, percentage-based alerting alone is not enough to determine deployability. Track simultaneously:

- Usage/limit ratio.
- Absolute headroom.
- Incremental demand in the next deployment wave.
- Rate of usage growth.
- Status and target need-by date of pending quota increase requests.

A practical pre-deployment signal is:

```text
Current headroom < peak incremental demand of the change
=> current plan does not meet quota requirements.
```

This condition must be evaluated for each relevant counter, not only total vCPUs.

### 9.2. Alerts with Clear Ownership

Example of internal thresholds chosen by a team:

| Situation | Action |
| --- | --- |
| Usage exceeds team's early warning level | Review growth forecast and deployment schedule |
| Remaining amount is below upcoming scale wave demand | Adjust plan or submit increase request |
| Recovery region lacks planned quota | Log recovery risk and resolve before drills |
| Increase request nears need-by date without resolution | Activate pre-evaluated fallback option |

Azure provides a workflow to create quota alerts for supported quotas. Verify permissions to create alerts, read permissions of managed identities, and data scope. Do not generalize near-real-time monitoring capabilities across every provider; documentation states support limitations for quota data. Refer to [Create alerts for quotas](https://learn.microsoft.com/en-us/azure/quotas/how-to-guide-monitoring-alerting).

An alert is only useful when the team knows who responds, what action to take, and when to escalate. After creating an alert, test notification delivery, rule status, and the identity's data read access.

### 9.3. Put Quota Checks into Pre-Deployment Gates

For pipelines that need to provision additional resources, a check step can be designed:

```text
Read subscription and region from target configuration
    -> Retrieve usage/limit of relevant quotas
    -> Calculate peak demand according to change plan
    -> Compare each quota
    -> Clearly report insufficient quotas and minimum required level
    -> Proceed only when deployment conditions are met
```

Check output should be structured:

```text
Quota: <counter identifier>
Scope: <subscription + region + family if applicable>
Used: 24
Limit: 32
AdditionalPeakRequired: 24
ProjectedPeak: 48
Result: INSUFFICIENT
```

Do not treat this step as a reservation transaction. Before large provisioning actions, still coordinate with other pipelines sharing the same scope. If quota increases are automated, clearly separate the **submit request** action from the **limit is in effect** condition.

## 10. Choose Solutions When a Limit Cannot Be Increased

Depending on the cause, options may include:

1. **Remove resources no longer needed.** Verify owners, data, and dependencies before deleting; then re-read usage.
2. **Reduce over-provisioning.** Use measurements to evaluate resizing, replica counts, or test-environment schedules.
3. **Reduce temporary deployment surge.** Balance against update duration and availability levels required by the application.
4. **Choose another VM family or SKU.** Verify CPU, RAM, processor architecture, disk capabilities, networking, and real-world performance.
5. **Partition workloads sensibly.** Change subscriptions or regions only when governance, networking, data, and operational models allow it.
6. **Adjust the design.** For fixed limits, review partitioning, splitting accounts, or distributing load according to service documentation.

No option fits every application by default. For example, reducing temporary VMs lowers quota demand but lengthens update time; changing regions may add latency and data synchronization requirements.

When hitting a fixed maximum limit, a support request can help clarify supported alternatives. Do not build plans on the assumption that support can always raise a technical ceiling.

## 11. Read-Only Quota Inspection Practice Exercise

The goal of this exercise is to produce a quota assessment for an environment without creating VMs or submitting an increase request.

### Preparation

Have a subscription you are permitted to view, relevant read permissions, and a signed-in Azure CLI or Azure portal access.

### Execution

1. Record the subscription, tenant, and region to evaluate.
2. Run `az vm list-usage` or view Compute under Quotas.
3. Select a VM family the application plans to use; record both the VM-family quota and regional total.
4. Calculate hypothetical demand for three new VMs, 4 vCPUs each.
5. Add a scenario with one temporary VM during updates.
6. For each counter, record usage, limit, additional demand, and post-change value.
7. Draft an increase request if insufficient; stop before submitting.

A results table can use the following format:

| Quota | Observed usage | Observed limit | Expected peak increase | After change | Sufficient/Short |
| --- | ---: | ---: | ---: | ---: | --- |
| Total regional vCPUs | Fill from environment | Fill from environment | 16 | Usage + 16 | Compare with limit |
| Target VM family | Fill from environment | Fill from environment | 16 | Usage + 16 | Compare with limit |

Here 16 vCPUs consists of `3 × 4` for the three new VMs and `1 × 4` for the temporary VM. If the real workflow replaces old VMs, build a timeline to compute the true number of coexisting VMs.

The result meets expectations when someone else can trace the exact scope, follow the calculation, and identify which quota needs adjustment from your record.

## 12. Principles to Remember

- Always pair a quota with its scope, unit, and inspection timestamp.
- For standard VMs, read both Total Regional vCPUs and VM-family quotas.
- Calculate peak demand across scaling, updates, and recovery.
- Enter the desired total limit when a form asks for a new limit.
- Wait for the outcome and re-read the actual limit before treating a request as fulfilled.
- Distinguish quota exhaustion, capacity shortage, and throttling to select the right fix.
- Combine limit monitoring with deployment permissions, cost plans, and operational ownership.
