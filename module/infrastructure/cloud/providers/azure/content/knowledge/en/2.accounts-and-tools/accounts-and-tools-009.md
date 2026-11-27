# Cleaning Up Resources and Checking Costs After Practice

When practicing on Microsoft Azure, you frequently create virtual machines, virtual networks, public IP addresses, storage accounts, databases, or monitoring workspaces. These resources can continue incurring charges after the lab ends, even when the application is no longer used. Therefore, finishing a lab must include identifying created resources, cleaning up within the right scope, and checking incurred costs.

This lesson belongs to the **Accounts and Tools** chapter of the `CLOUD_PROVIDERS_AZURE` module. The module helps you explore the Microsoft Azure ecosystem from subscriptions, resource groups, and Microsoft Entra ID to virtual networks, compute services, storage, and data; while learning how to deploy, monitor, protect, and control costs for an application architecture. Good cleanup and cost-tracking habits keep lab environments clear, reduce orphaned resources, and avoid unnecessary charges.

## Learning Objectives

After this lesson, you will be able to:

- List resources created during a lab and identify the exact subscription, resource group, and owner.
- Choose between deleting an entire resource group or deleting only individual resources within a safe scope.
- Recognize dependent resources, orphaned resources, and services that can still incur charges when idle.
- Verify that deletion has completed and understand what data may still be retained.
- Use Azure Cost Management to analyze costs by time, resource group, resource, and service.
- Set up budgets, alerts, and a repeatable lab wrap-up workflow.

## 1. Why Clean Up After Practice?

Azure bills by service type and usage pattern. Some resources bill by provisioned duration, some by storage capacity, transaction count, data transfer volume, runtime hours, or ingested data volume. Consequently, not using an application does not mean all charges have stopped.

For example:

- A running virtual machine incurs compute charges. When you only shut down the OS from inside or leave it in the stopped (allocated) state, compute charges may still apply. Deallocating a VM generally stops the compute charges, but managed disks, snapshots, IP addresses, or related networking resources can still incur charges.
- Managed disks, snapshots, and backups can continue billing by capacity or retention policy even after the VM has been deleted.
- Public IPs, NAT Gateways, Azure Firewall, Application Gateway, and other networking services may charge by allocated time or usage.
- Storage accounts can incur capacity, transaction, replication, blob versioning, or soft-deleted data charges.
- Log Analytics workspaces and monitoring services can bill by ingested data volume and retention period.
- Databases can bill by compute, storage, provisioned redundancy, or uptime, depending on the service model.

Therefore, you need to inspect every resource belonging to the lab, including supporting resources. Proper cleanup reduces costs while also limiting exposure of test data, access keys, endpoints, or unneeded configurations.

## 2. Preparing Before Deletion

Before running delete commands, clearly determine the scope and purpose of each resource. A subscription may host multiple learners' environments or shared services; do not assume every resource in the subscription belongs to your lab.

### Verifying the subscription and resource group

In Azure CLI, check the currently selected subscription:

```bash
az account show --output table
```

If you need to switch to the subscription assigned for the lab:

```bash
az account set --subscription "<subscription-id-or-name>"
```

Check the subscription again after switching. Then inspect the resource group details:

```bash
az group show \
  --name rg-lab-demo \
  --query "{name:name, location:location, tags:tags, id:id}" \
  --output json
```

The name `rg-lab-demo` is only an example. Replace it with your lab's actual resource group name.

### Listing resources inside the resource group

The following command displays the name, type, region, and Resource ID of resources in the group:

```bash
az resource list \
  --resource-group rg-lab-demo \
  --query "[].{Name:name, Type:type, Location:location, Id:id}" \
  --output table
```

If the lab used tags to mark resources, you can filter by tag:

```bash
az resource list \
  --tag "purpose=training" \
  --query "[].{Name:name, ResourceGroup:resourceGroup, Type:type, Id:id}" \
  --output table
```

Tags are just metadata for classification and search. Tags do not automatically delete resources, prevent costs, or prove that the tagger is the sole owner. Cross-check tags against lab instructions, creation time, owner, and shared components.

A helpful convention is to attach tags upon resource creation, for example:

| Tag | Example value | Purpose |
|---|---|---|
| `owner` | `student01` | Identify the responsible owner |
| `purpose` | `training` | Distinguish practice resources |
| `environment` | `lab` | Distinguish lab environments from dev, staging, or production |
| `expiresOn` | `2026-11-30` | Record the planned end-of-use date |
| `project` | `azure-basics` | Group resources by lesson or project |

An expiration date in a tag is merely informational unless an automated process reads and acts on that tag.

### Checking shared resources and delete locks

Before deleting a resource group, confirm that the group was created exclusively for the lab and does not contain resources used by another team. If only a few lab resources reside inside a shared resource group, delete those identified resources individually rather than deleting the whole group.

Resource locks can block delete or modify operations. Check locks at the resource group level:

```bash
az lock list \
  --resource-group rg-lab-demo \
  --output table
```

A `CanNotDelete` lock prevents deleting resources; a `ReadOnly` lock also restricts update operations. If a lock exists, determine who manages it and why it is protected before making changes. Never remove a lock just to make a cleanup command succeed without authorization.

## 3. Choosing the Right Cleanup Method

There are two common approaches: deleting an entire dedicated lab resource group, or deleting only individual lab resources. Choose based on ownership boundaries and usage scope.

### Deleting a dedicated lab resource group

If the resource group was created solely for a lab and you have confirmed no resources need to be kept, deleting the whole group is the cleanest approach. This operation instructs Azure to delete the resources inside that resource group.

```bash
az group delete \
  --name rg-lab-demo \
  --subscription "<subscription-id>" \
  --yes \
  --no-wait
```

In the command above:

- `--name` specifies the resource group to delete.
- `--subscription` scopes the command to the right subscription, avoiding mistakes when an account has multiple subscriptions.
- `--yes` confirms the operation in the CLI.
- `--no-wait` lets the command return without waiting for the entire deletion process to finish.

Deleting a resource group is a high-impact operation: all resources inside the group can be deleted along with it. Data or configurations to keep must be backed up or moved beforehand. Resources referenced from the group that reside in another resource group are not automatically deleted; they must be checked separately.

### Deleting individual resources

In a shared environment, list and confirm each resource to delete. You can delete by Resource ID:

```bash
az resource delete \
  --ids "/subscriptions/<subscription-id>/resourceGroups/rg-shared-lab/providers/Microsoft.Network/publicIPAddresses/pip-lab-temp"
```

Take the Resource ID from `az resource list` output to avoid mistyping paths. When deleting individual resources, check dependencies first. For example, a network interface may be attached to a VM; a public IP may be attached to a network interface or load balancer; a disk may remain after a VM is deleted. Deleting a parent resource may be rejected if associations or child resources have not been handled.

### Temporary stop or delete?

If you need to resume the lab in the next session, you can stop or deallocate certain resources instead of deleting them. For a virtual machine, for example:

```bash
az vm deallocate \
  --resource-group rg-lab-demo \
  --name vm-lab-demo
```

Deallocating releases the VM's compute capacity and generally stops compute billing while the VM remains deallocated. Managed disks, snapshots, backups, IP addresses, and related services may still incur charges. Check the VM state and the billing model of each service.

| Option | When suitable | Points to note |
|---|---|---|
| Delete resource group | Group was created solely for a completed lab | Deletes all resources in the group; check data and shared resources first |
| Delete individual resources | Resource group holds resources from multiple labs or teams | Must identify exact Resource IDs and handle dependencies |
| Deallocate or pause | Will resume using the resources later | Some components still incur charges; not all services have a stopped state |
| Keep temporarily | Need to save results or await review | Assign an owner and concrete cleanup date; monitor costs while kept |

## 4. Verifying After Deletion

Successfully submitting a delete request does not always mean every resource vanishes immediately. Some operations run asynchronously; services may take time to finish releasing resources.

Check whether the resource group still exists:

```bash
az group exists --name rg-lab-demo
```

A `false` result indicates the resource group no longer exists in the subscription currently targeted by the CLI. If deletion was run with `--no-wait`, check again after some time. If the group still exists, inspect its status and error messages:

```bash
az group show --name rg-lab-demo --output json
```

If you need to check a specific resource:

```bash
az resource show --ids "<resource-id>" --output json
```

The query command may return an error if the resource was deleted or read permissions no longer apply. Combine the result with the resource list in the resource group and the status in the Azure Portal to confirm.

### Looking for leftover resources

After deleting a resource group, scan for related resources that may have been created at another scope or configured to persist independently. Common items to check include:

- Managed disks, snapshots, and images retained after VM deletion.
- Public IPs, network interfaces, load balancers, NAT Gateways, or network security resources no longer attached to a workload.
- Storage accounts, containers, blob versions, and soft-deleted data.
- Backup vaults, recovery points, and backup retention policies.
- Log Analytics workspaces, Application Insights, or diagnostic settings sending data to another workspace.
- Private DNS zones, DNS records, route tables, or networking resources in a separate resource group.
- Services or resources created by another lab that remain linked to the deleted environment.

Not every item above is guaranteed to remain after deleting a resource group; this list serves as a checklist based on actual architecture. Verify the Resource ID, dependencies, and owner before deleting remaining items.

### Data and retention policies

Deleting a management resource does not always mean data is permanently erased immediately. Some services support soft delete, immutable retention, backups, or data retention periods. Key Vault, storage, backup vaults, and data services may have their own protection mechanisms. Review service policies and organizational retention requirements before concluding data has been completely purged.

If the lab created test secrets, access keys, certificates, or credentials, check their lifecycle and revoke or rotate them per appropriate procedures. Never write secrets into report files, logs, or lesson materials.

## 5. Checking Costs with Azure Cost Management

After cleanup, use Azure Cost Management to view incurred costs and identify which resources contributed the most. Users need permissions to view cost data at the corresponding scope; resource management permissions do not necessarily include billing visibility.

### Opening Cost Analysis

In the Azure Portal:

1. Open **Cost Management + Billing**.
2. Select the billing scope, subscription, or resource group matching the lab scope.
3. Open **Cost analysis**.
4. Choose a date range covering the lab's start and end times.
5. Choose grouping options such as Resource, Resource group, Service name, or Meter.
6. Apply filters by subscription, resource group, resource, service, or tag if supported by the data.

When analyzing, inspect at least two views:

- **Cost by resource group or tag:** helps isolate the lab's costs, especially when each lab has its own resource group or tags.
- **Cost by resource or service:** helps identify VMs, disks, storage, networking services, databases, or monitoring consuming most of the budget.

For example, if resource group `rg-lab-demo` was dedicated to one lab, filter Cost Analysis by that resource group and group by Resource to inspect individual resources. Next, group by Service name or Meter to understand whether charges come from compute, storage, networking, or transactions.

### Understanding cost views

Cost Analysis can offer different cost views depending on the scope and agreement type:

- **Actual cost** shows costs recorded in billing data for the period. This view is useful for reconciling charges appearing on an invoice or actual cost data.
- **Amortized cost** spreads the cost of certain upfront commitments, such as reservations or savings plans, across usage over the corresponding period. This view helps analyze usage costs by resource and workload.

When comparing two charts, check the cost type, date range, currency, scope, and filters. Never add or compare charts with different scopes or allocation methods without understanding the differences.

### Why don't costs drop to 0 immediately after deletion?

Cost Management data may update with latency relative to resource creation or deletion actions. Charges displayed after cleanup may reflect the time the resource was still active, unaggregated usage data, or an independent component still running.

When seeing charges after the deletion timestamp:

1. Expand the date range to see which day the charges began.
2. Inspect by Resource, Service name, and Meter to pinpoint the source.
3. Cross-check the Resource ID and creation/deletion timestamps in the activity history or deployment logs.
4. Check for remaining supporting resources, including in other resource groups.
5. Wait for billing data to update and recheck; if anomalous charges persist, examine usage details and contact billing administration.

Do not conclude there is a billing error from a single point-in-time chart. Consider the billing period, data latency, and committed charges or services with separate billing cycles.

## 6. Budgets, Alerts, and Cost Controls

Azure Cost Management supports creating budgets at supported scopes, such as subscriptions or resource groups. A budget sets a cost-tracking threshold over a period, such as monthly.

A budget can configure:

- Scope: subscription or resource group to monitor.
- Amount: expected budget amount.
- Reset period: tracking cycle, typically monthly, quarterly, or annually as needed.
- Start and end date: active duration.
- Alert threshold: alert triggers, such as 50%, 80%, or 100% of budget.
- Action group or notification recipients: where alerts are delivered per supported configuration.

A budget is a tracking and notification tool. **Budget alerts do not automatically stop VMs, delete resources, or block spending** when thresholds are exceeded. If automated action is desired, you must build a separate controlled workflow with appropriate permissions and protections for shared resources.

Additional control measures:

- Use Azure Policy to require tags, restrict regions, or control SKU types suited for learning environments.
- Create separate resource groups per lab or learner group, establishing naming conventions and expiration dates.
- Estimate costs before deployment using the Azure Pricing Calculator; this is an estimate based on input assumptions, not a guaranteed invoice.
- Review Azure Advisor cost optimization recommendations if the subscription has relevant data.
- Periodically review costs in Cost Analysis and use Cost Management exports if long-term analytical data storage is needed.
- Limit uptime for VMs, databases, or fixed-cost networking services; delete resources when the lab is complete.
- Set retention periods for logs, backups, snapshots, and test data strictly according to need.

## 7. Repeatable Lab Wrap-Up Workflow

Apply the following workflow at the end of every practice session:

| Step | Action | Expected outcome |
|---|---|---|
| 1. Confirm scope | Verify tenant, subscription, resource group, and owner | Know the exact environment being operated on |
| 2. Inventory | List resources, Resource IDs, tags, and dependencies | Have a list of resources to keep or delete |
| 3. Preserve needed data | Export configs, save learning outputs, and back up allowed data | No loss of results needed later |
| 4. Clean up | Delete dedicated resource group or delete confirmed individual resources | Temporary resources removed |
| 5. Verify | Check resource group, leftover resources, locks, and deletion status | No unexpected lab resources remain |
| 6. Check costs | Open Cost Analysis, filter by scope and timeframe, view cost by resource | Identify charges from the lab session |
| 7. Record | Log cleanup timestamp, verification results, and observed costs | Have a trail for reference and future improvement |

For example, a team of learners deploys a VM, virtual network, and storage account in `rg-lab-demo`. At the end of the session, the team verifies the right subscription, lists the three resources along with supporting components, confirms no data needs to be kept, and deletes the resource group. After `az group exists` returns `false`, the team filters Cost Analysis by the resource group and session timeframe. If charges still appear, the team checks usage dates, disks, or IPs in other scopes and waits for billing data to update before reporting results.

## 8. Common Issues When Cleaning Up and Checking Costs

| Scenario | Possible cause | How to resolve |
|---|---|---|
| Deleted the wrong resource group | Wrong subscription or group name selected | Run `az account show`, verify name and Resource ID before deleting |
| Delete command rejected | Resource lock present, insufficient permissions, or remaining dependencies | Inspect locks, role assignments, and specific error messages |
| Resource group still exists after delete command | Deletion running asynchronously or a resource failed to delete | Recheck status, open error details, and handle the blocked resource |
| VM deleted but charges continue | Disks, snapshots, backups, IPs, or related resources remain | Inventory supporting resources and inspect costs by Resource/Meter |
| Cleaned up yet Cost Analysis still shows costs | Billing data updated with delay or charges accrued before deletion | Check timeframe, cost type, and wait for data to update |
| Cannot view Cost Analysis | Missing Cost Management permissions or wrong billing scope selected | Request cost-reading permissions at the appropriate scope or select the right scope |
| High costs despite light resource usage | Large SKU, time-billed service, storage, or data transfer | Inspect Meter details, service configuration, and choose an appropriate SKU |

## 9. Self-Check

**Question 1.** Why can a stopped virtual machine still be associated with Azure costs?

**Answer:** If the VM has not been deallocated, compute charges may still apply. Even when deallocated or deleted, managed disks, snapshots, backups, IPs, and related networking services can still incur charges.

**Question 2.** When should you delete an entire resource group?

**Answer:** When the resource group was created solely for the lab, confirmed to contain no shared resources or data to preserve, and the right subscription has been verified. If the group contains resources belonging to multiple people or other workloads, delete only the resources confirmed to belong to the lab.

**Question 3.** Does `az group delete --no-wait` guarantee deletion has completed as soon as the command returns?

**Answer:** No. `--no-wait` lets the CLI return without waiting for deletion to finish. You must verify afterward using `az group exists` or the Azure Portal.

**Question 4.** Do budget alerts automatically stop a subscription from incurring further costs?

**Answer:** No. Budgets generate alerts when thresholds are reached. Automatically stopping or handling resources requires building a separate controlled workflow.

**Question 5.** Why might Cost Analysis still display charges after a resource group has been deleted?

**Answer:** Billing data may update with latency, and displayed charges may belong to the period when resources were still active. You should also check supporting resources in other scopes or charges with separate billing cycles.

## Conclusion

An Azure lab truly ends only when resources are inventoried, cleaned up within the right scope, deletion status is verified, and costs are reconciled. Confirm the subscription and ownership before deleting; inspect supporting resources, retained data, and services that may continue billing; then use Cost Analysis, budgets, and alerts to track usage. Maintaining this routine for every lab keeps your Azure environment clearer, reduces leftover resources, and controls your budget effectively.
