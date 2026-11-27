# Decommissioning Lab Resources and Checking Ongoing Costs

After a cloud lab, stopping virtual machines or deleting an application does not necessarily end charges. Disks, snapshots, static IP addresses, NAT gateways, load balancers, databases, backups, logs, registries, clusters, and networking resources can continue existing after the main workload stops. Certain usage commitments, licenses, or support plans also continue billing under contract even after resources are deleted.

**Decommissioning lab resources** is the process of accurately scoping the lab, stopping load-generating sources, deleting resources in dependency order, and verifying what remains. **Checking ongoing costs** is the step of reconciling post-cleanup inventory against billing reports, usage data, and billing commitments to spot continuing charges.

The goal of this lab is to cleanly shut down a lab environment, retain required data as requested, avoid accidentally deleting shared resources, and confirm which charges have stopped, which are awaiting billing updates, and which continue under contracts.

## 1. Why Deleting the Workload Does Not Always Stop Costs

A lab environment usually consists of resources created across different layers: application, compute, storage, networking, identity, and managed services. Deleting the first visible component can leave behind independent or automatically provisioned resources.

For example, deleting a VM may not delete its data disk if disk retention is enabled. Deleting a Kubernetes cluster may leave behind persistent volumes, snapshots, IP addresses, or load balancers created by controllers. Stopping a database may reduce compute fees while storage and backup fees keep accruing. Disabling autoscaling does not delete already-provisioned nodes.

Common lingering cost categories:

| Category | Resources that may remain | Why charges continue |
|---|---|---|
| Compute | Stopped/deallocated VMs, node pools, dedicated hosts, GPU instances | Some resource types still bill when stopped; hosts or reservations may bill by term |
| Storage | Persistent disks, block volumes, snapshots, backups, object versions | Billed by stored capacity, copy count, or retention duration |
| Network | NAT gateways, load balancers, public IPs, VPN gateways, private endpoints | Billed hourly, by capacity, by address, or by traffic |
| Database | Stopped instances, storage, read replicas, automated backups | Storage, backups, or standbys may continue billing |
| Container | Clusters, nodes, persistent volumes, registry images | Cluster control planes, nodes, volumes, and image storage have separate lifecycles |
| Observability | Logs, metrics, traces, dashboards, alerts, log archives | Ingested data continues incurring retention charges |
| Data transfer | Egress, cross-region replication, CDN, NAT processing | Previously incurred traffic posts later; replication may keep running |
| Serverless and events | Schedulers, triggers, queues, workflows, subscriptions | New events keep invoking workloads or generating calls |
| Commitments and licenses | Savings plans, reserved capacity, committed use, marketplace subscriptions, support plans | Contractual or license obligations do not end automatically when workloads are deleted |

Therefore, treat cleanup as a resource-and-billing lifecycle workflow, not merely an application deletion command.

## 2. Scoping the Lab Before Decommissioning

Before deleting anything, list the resources belonging to that specific lab session. Resource names, tags/labels, and projects/resource groups help distinguish the lab from shared environments.

A useful metadata set:

| Field | Example | Purpose |
|---|---|---|
| Environment | lab | Identify environment |
| LabId | compute-lab-2026-11-22 | Group resources from a single lab session |
| Owner | learner-team-a | Identify responsible owner |
| ExpiresAt | 2026-11-23T18:00:00Z | Time to review/decommission |
| CostCenter | training | Cost allocation |
| KeepUntil | 2026-12-01 | Mark data that must be retained until a deadline |

Apply tags/labels at resource creation time. If a service does not support tags, record its ID and relationships in a lab manifest. Never infer ownership solely from similar names; cross-check project, subscription, account, region, owner, and creation timestamp.

Example resource manifest for a lab:

~~~yaml
lab:
  id: compute-lab-2026-11-22
  environment: lab
  owner: learner-team-a
  expiresAt: "2026-11-23T18:00:00Z"
  resources:
    - provider: cloud-a
      type: virtual-machine
      id: vm-compute-demo
      region: region-1
    - provider: cloud-a
      type: persistent-disk
      id: disk-compute-demo
      region: region-1
    - provider: cloud-a
      type: public-ip
      id: ip-compute-demo
      region: region-1
  retainedData:
    - id: lab-results
      keepUntil: "2026-12-01"
~~~

This is an illustrative manifest for tracking, not a provider command schema. A real manifest should store exact IDs and the decommission state of each resource.

### 2.1. Verifying Permissions and Ownership

Before acting, confirm:

- You are in the right cloud account, project, or subscription.
- You are in the right region/zone and lab environment.
- Resources carry the lab tag/label or appear in the manifest.
- Resources are not shared with another lab, team, or production service.
- You know who has authority to approve deleting data and shared resources.
- You have sufficient billing and inventory read permissions to verify outcomes.

If ownership or dependencies are unclear, put the resource on a verification list instead of deleting by guesswork.

## 3. Building an Inventory and Dependency Graph

Good cleanup starts with a complete inventory. Search for resources by tag/label, project/resource group, creation timestamp, attachment relationships, and deployed services.

Check at least:

- VMs, instance groups, autoscaling groups, node pools, GPUs, and dedicated hosts.
- Container clusters, services, tasks, jobs, persistent volumes, and volume attachments.
- Disks, snapshots, machine images, backups, and object storage.
- Databases, replicas, caches, queues, topics, and workflows.
- Load balancers, NAT gateways, public IPs, VPNs, firewall attachments, private endpoints, and DNS.
- Registries, artifacts, log groups, metrics, traces, and backup archives.
- Schedulers, event rules, triggers, subscriptions, and serverless deployments.
- Secrets, certificates, service accounts, and roles after workloads have stopped.

Map dependencies before deleting:

~~~mermaid
flowchart TD
    A["Scheduler / event trigger"] --> B["Application / container service"]
    B --> C["Compute node / VM"]
    B --> D["Load balancer"]
    C --> E["Persistent disk"]
    C --> F["Network interface"]
    D --> G["Public IP"]
    C --> H["NAT / route"]
    B --> I["Database"]
    B --> J["Object storage"]
    B --> K["Queue"]
    I --> L["Backup / snapshot"]
    J --> M["Versioned objects"]
~~~

Decommissioning order must respect dependencies. For instance, stop triggers first so no new jobs spawn; stop workloads before deleting databases or queues; delete services attached to load balancers before deleting load balancers; verify volumes and snapshots before deleting clusters.

Run the inventory again after cleanup. Never rely solely on the initial creation list, because controllers or managed services can create extra resources during the lab.

## 4. Safe Step-by-Step Decommissioning Procedure

You can follow this sequence for a typical lab:

### Step 1: Freeze Resource Creation

- Stop pipelines or automation scripts that could recreate the lab.
- Disable schedulers, crons, event triggers, and autoscaling policies that spawn new workloads.
- Stop sending traffic or messages into the environment.
- Mark the lab in cleanup status so others do not keep using it.
- Record counts of active jobs, replicas, instances, and queued messages.

If you delete VMs while autoscaling or deployment controllers remain active, controllers may launch replacement VMs. If queues still hold messages and consumers remain running, workloads may keep generating charges.

### Step 2: Preserve Required Data

Identify data required to be kept per lesson or team needs:

- Lab outputs, investigation logs, or reports.
- Database dumps or snapshots needed for the next session.
- Input/output files subject to retention periods.
- Manifests, configurations, and metadata needed to reproduce the lab.

Verify backups can be read/restored before deleting sources if data is critical. Record owner, location, encryption, retention, and expiration date. Never create indefinite snapshots just "in case"; snapshots also incur storage costs.

### Step 3: Stop and Delete Workloads

- Stop applications, services, tasks, jobs, and workers.
- Cancel pending or running jobs if permitted.
- Scale replicas to 0 or delete workload controllers.
- Confirm no triggers, schedulers, or autoscalers are recreating replicas.
- Check queues, workflows, and subscriptions to prevent events from continuing to fire.

In Kubernetes, deleting a Deployment does not automatically delete every PersistentVolume or cloud resource provisioned by controllers. Inspect PVCs, PVs, reclaim policies, LoadBalancer-type Services, and resources created by CSI/CNI plugins.

### Step 4: Decommission Compute and Networking

Once workloads stop, delete VMs, node pools, clusters, or compute environments in dependency order. Then inspect:

- Load balancers and target groups/backend pools.
- Unattached public/static IPs.
- NAT gateways, VPN gateways, and private endpoints.
- Lab-specific network interfaces, routes, peerings, or attachments.
- DNS records and zones created specifically for the lab.

Not every networking component bills hourly; however, they can incur fixed fees, data processing fees, or query charges. Use the specific service's pricing page and billing reports to confirm.

### Step 5: Handle Storage, Backups, and Registries

Inspect detached disks, snapshots, images, backups, object versions, incomplete multipart uploads, and old artifacts/images. Clarify which data must be deleted and which must be kept per retention.

Commonly missed items:

- Detached disks still incur capacity charges.
- Incremental snapshots still retain required blocks and continue billing.
- Object versions or delete markers can keep older data stored.
- Lifecycle policies may not have reached their deletion date yet.
- Container registries keep storing images even after clusters are deleted.
- Automated database backups carry separate retention periods.

### Step 6: Revoke Identities and Auxiliary Configurations

Once workloads no longer need permissions, review service accounts, roles, access keys, certificates, secrets, policies, and test accounts. Revoke unused credentials and delete secrets per policy.

Retain audit logs, manifests, and cleanup evidence for the required retention window. Never delete shared roles or secrets merely because their names contain the word "lab".

### Step 7: Check for Leftover Resources

Re-run inventory across all relevant regions/zones. Compare against the manifest and classify every item:

- Deleted: deleted and confirmed by API.
- Retained: kept intentionally with an owner and expiration date.
- Pending: deletion in progress or waiting on detached devices.
- Failed: deletion errored, with cause and assignee recorded.
- Shared: shared resource kept intentionally with a clear owner.

Do not mark a lab closed while any resource remains in an unknown state.

## 5. Charges That Commonly Continue After a Lab Ends

### 5.1. Compute and Usage Commitments

Stopping an instance may halt compute charges depending on service billing rules, but does not necessarily halt disk, IP, or license charges. Resources such as dedicated hosts or reservations may bill by term even with no workloads running on them.

Savings plans, reserved instances, or committed use discounts are financial or usage commitments already purchased. Deleting a VM does not cancel a commitment. Check terms, end dates, and reassignment rules per provider policy.

### 5.2. Storage, Snapshots, and Backups

Storage typically keeps billing by capacity and retention duration. Check primary disks, snapshots, backups, object versions, and registry storage.

For databases, automated backups may persist after instance deletion. Some services retain a final backup depending on options selected at deletion. Read retention/delete-final-backup choices carefully before confirming deletion.

### 5.3. Networking and Data Transfer

NAT gateways, load balancers, VPN gateways, public IPs, or private endpoints can incur fixed or processing fees. Egress and cross-region transfers can appear on bills after traffic has stopped.

Deleting a route or firewall rule does not delete a gateway. Deleting a service does not always release dedicated static IPs. Verify exact attachments and resource IDs.

### 5.4. Observability and Archived Data

Logs, metrics, traces, and archives can keep billing by ingested volume and retention. Dashboards or alert rules may be free on some tiers, yet the underlying data they query may still incur charges.

Inspect log groups, log buckets, workspaces, archives, audit trails, and storage exports. Keep mandatory compliance data, set appropriate retention, and delete expired lab data.

### 5.5. Managed Services, Serverless, and Events

Some services bill by requests, execution duration, workflow transitions, messages, queries, or storage. If a trigger remains active, workloads can keep getting invoked long after the lab seemed finished.

Check event source mappings, subscriptions, scheduled jobs, webhooks, queue redrives, and pending workflows. Ensure no producers emit events or background consumers remain running unintentionally.

### 5.6. Licenses, Marketplace, and Support

Marketplace software may bill hourly, per instance, per user, or by contract. Deleting a VM does not always terminate a subscription or license. Cloud support plans usually apply at the account/organization level and may keep billing even when no labs remain.

Review billing accounts, marketplace subscriptions, support plans, and contractual commitments. Only personnel with billing authority should confirm or modify these obligations.

## 6. Hands-On Example: Decommissioning a Kubernetes Lab

Suppose a lab created a namespace containing an API Deployment, a LoadBalancer-type Service, a PVC, a Secret, and several controller-provisioned cloud resources.

First, verify the right namespace and workloads:

~~~bash
kubectl get all -n compute-lab
kubectl get pvc,pv -n compute-lab
kubectl get svc -n compute-lab
kubectl get events -n compute-lab --sort-by=.metadata.creationTimestamp
~~~

Save required logs or lab outputs. Next, stop controllers from creating new workloads, delete unneeded CronJobs/Jobs, and scale Deployments to 0 or delete workloads per lab instructions:

~~~bash
kubectl get cronjobs,jobs -n compute-lab
kubectl get deployments,statefulsets -n compute-lab
kubectl scale deployment --all --replicas=0 -n compute-lab
~~~

After confirming the application has stopped, inspect Services and volumes:

~~~bash
kubectl get svc,pvc -n compute-lab
kubectl get pv
kubectl describe pv PV_NAME
~~~

LoadBalancer-type Services can provision cloud load balancers and public IPs. Delete the Service after confirming the right lab and recording related resource IDs:

~~~bash
kubectl delete service LAB_SERVICE -n compute-lab
~~~

PVCs/PVs must be handled according to their reclaim policy. With a Retain policy, deleting a PVC can leave the PV and underlying cloud disk intact. With a Delete policy, the controller may delete underlying storage when conditions are met; still verify cloud inventory afterward.

Once required data has been archived or deleted, delete the lab namespace:

~~~bash
kubectl delete namespace compute-lab
~~~

Finally, inspect clusters, node pools, disks, snapshots, load balancers, public IPs, NATs, and logs on the cloud provider. If the cluster is shared, never delete the cluster merely because the lab namespace finished.

## 7. Cloud-Specific Resource Inspection Command Examples

The commands below illustrate inventory and inspection; substitute real project, account, subscription, region, and tag values from your environment. Run read commands first, review results, and only then run delete commands against verified resource IDs.

### 7.1. AWS

List EC2 instances by lab tag:

~~~bash
aws ec2 describe-instances \
  --filters "Name=tag:Environment,Values=lab" \
  --query "Reservations[].Instances[].[InstanceId,State.Name,Placement.AvailabilityZone]"
~~~

Check EBS volumes in `available` state, typically detached volumes:

~~~bash
aws ec2 describe-volumes \
  --filters Name=status,Values=available \
  --query "Volumes[].[VolumeId,Size,AvailabilityZone,Tags]"
~~~

Check Elastic IPs and NAT gateways:

~~~bash
aws ec2 describe-addresses
aws ec2 describe-nat-gateways --filter Name=state,Values=available,pending,deleting
~~~

After verifying IDs and dependencies, terminate specific instances or delete specific volumes. Illustrative syntax examples:

~~~bash
aws ec2 terminate-instances --instance-ids i-0123456789abcdef0
aws ec2 delete-volume --volume-id vol-0123456789abcdef0
~~~

Terminating an instance may preserve EBS volumes depending on delete-on-termination settings. Inspect volumes after instance termination completes. For NAT gateways, delete the gateway and handle Elastic IPs according to service status and procedures.

Cost Explorer can inspect costs by service and time if enabled with proper permissions:

~~~bash
aws ce get-cost-and-usage \
  --time-period Start=2026-11-01,End=2026-12-01 \
  --granularity DAILY \
  --metrics UnblendedCost \
  --group-by Type=DIMENSION,Key=SERVICE
~~~

The end date of the time period is exclusive. Billing data lags behind real time, so reports checked immediately after cleanup may not yet reflect all latest usage.

### 7.2. Azure

List resources in a lab resource group and filter by tags:

~~~bash
az resource list \
  --resource-group rg-compute-lab \
  --query "[].{name:name,type:type,location:location,id:id}" \
  --output table
~~~

List VMs in the resource group:

~~~bash
az vm list \
  --resource-group rg-compute-lab \
  --show-details \
  --output table
~~~

If the resource group was created exclusively for a single lab and verified to contain no shared resources, you can deliberately delete the entire group:

~~~bash
az group delete --name rg-compute-lab --yes
~~~

Deleting a resource group is a broad-impact operation. Before running it, inspect every resource in the group, backups, disks, public IPs, and data needing retention. For shared resource groups, delete verified individual resources instead of the whole group.

Deallocating a VM releases only VM compute charges; disks, IPs, backups, or other resources may remain. Check Cost Management by subscription/resource group/service over an appropriate timeframe to verify charges.

### 7.3. Google Cloud

List VMs by label:

~~~bash
gcloud compute instances list \
  --filter="labels.environment=lab" \
  --format="table(name,zone,status,labels)"
~~~

List disks:

~~~bash
gcloud compute disks list \
  --format="table(name,zone,status,sizeGb)"
~~~

Inspect project resources with Cloud Asset Inventory if the API and permissions are enabled:

~~~bash
gcloud asset search-all-resources \
  --scope=projects/PROJECT_ID \
  --query="labels.environment=lab"
~~~

After verifying zone and ID, delete the specific VM:

~~~bash
gcloud compute instances delete LAB_VM \
  --zone=ZONE
~~~

Check disks after VM deletion because disks may remain depending on auto-delete settings. Review Cloud Billing Reports or billing exports to reconcile costs by project, service, SKU, and date. Exporting billing data to BigQuery helps when performing granular breakdowns by label or resource.

The commands above are examples for common services. Each cloud includes additional managed resources and retention nuances; never treat a single VM list command as a complete inventory.

## 8. Checking Billing After Decommissioning

Review billing from two perspectives: remaining resources and recorded usage. These two perspectives complement each other.

### 8.1. Reconciling Inventory and Billing

Build a post-cleanup verification table:

| Category | Post-cleanup inventory | Billing/usage to verify |
|---|---|---|
| VM/compute | No running lab instances remain | Instance hours, vCPU/GPU hours, dedicated hosts |
| Disk/snapshot | No disks/snapshots outside retention list | GB-months, snapshot storage, backup storage |
| Network | No unexpected lab NAT/LB/IP/VPN resources | Gateway hours, IP hours, data processing, egress |
| Database | No lab instances/replicas remain | DB instance hours, storage, backups, I/O |
| Kubernetes | No dedicated lab clusters/node pools remain | Cluster fees, node compute, volumes, and load balancers |
| Object/registry | Expired data deleted, required data retained | Storage bytes, requests, replication, registry storage |
| Observability | Retention configured or lab data deleted | Log ingestion, archives, metric/trace storage |
| Event/serverless | Triggers, schedulers, and workflows stopped | Invocations, messages, workflow transitions |
| Commitment/license | Contracts and subscriptions reviewed | Commitment charges, licenses, support plans |

If inventory is clean yet billing keeps rising, check billing lag, usage-billed charges already incurred, usage commitments, licenses, and account-level services. If billing drops while inventory still shows resources, those resources may be free-tier or idle; still decide whether to retain or delete them per policy.

### 8.2. Choosing a Comparison Time Window

Compare daily or hourly costs before and after cleanup using the same timezone and metric type. Specifically:

1. Record the cleanup start timestamp.
2. Capture baseline usage/cost metrics before deletion.
3. Record when resources actually transitioned to deleted state.
4. Wait for billing reports to refresh per the provider's reporting cycle.
5. Compare by service, SKU, region, project/resource group, and tag/label.
6. Investigate any line item that does not drop or continues climbing.

Do not immediately conclude cleanup failed just because the bill has not dropped within minutes. Billing aggregates periodically and can post late. Conversely, do not conclude all charges stopped simply because today's dashboard lacks data yet.

### 8.3. Distinguishing Lagging Charges from Ongoing Charges

- **Lagging charges:** Usage that occurred prior to deletion but gets recorded or billed afterward.
- **Ongoing charges:** Resources still existing, triggers still firing, data still stored, or commitments still billing.
- **Billing adjustments:** Credits, refunds, taxes, discounts, or invoice adjustments changing totals without reflecting new resources.
- **Shared costs:** Account/organization-level resources or shared networks that cannot be attributed solely to one lab.

Use usage dates and service/SKU fields to separate pre-cleanup from post-cleanup usage. For shared resources, rely on cost allocation tags or organizational allocation rules.

## 9. Setting Up Guardrails So Labs Terminate Automatically

Forgotten resources can be minimized by designing lifecycle controls right at lab creation:

- Enforce tags/labels for owner, lab ID, environment, cost center, and expiry.
- Provision labs in dedicated projects, subscriptions, or resource groups where appropriate.
- Configure budgets or alerts per lab/project and spend threshold.
- Set TTLs on temporary environments via tested automation.
- Use IaC to track which resources belong to a stack and destroy them cleanly.
- Save resource ID manifests and deployment outputs.
- Set default retention policies for logs, snapshots, and temporary objects.
- Restrict quotas and permissions for costly resources like GPUs, NATs, public IPs, and large databases.
- Use policies to detect unowned or expired resources.
- Define an exception process when a lab needs to retain resources past expiry.

TTL automation must never delete shared data or resources without owner confirmation. Cleanup automation requires dry-run modes, allowlists/denylists, audit logs, scope boundaries, and fail-safes when encountering unidentified resources.

## 10. Hands-On Lab: Cleaning Up a Compute Lab Environment

Suppose you built a lab containing an API VM, a data disk, a static public IP, a load balancer, a small database, a results bucket, and a log workspace.

Follow these steps:

### 10.1. Record Pre-Cleanup State

- Record account/project/subscription and region.
- Record LabId, owner, start time, and resource IDs.
- Export lists of VMs, disks, IPs, load balancers, databases, buckets, and log workspaces.
- Record storage capacity, snapshot counts, object version counts, and backup status.
- Record baseline usage/cost by service/SKU over a defined period.
- Mark data to retain and its expiration date.

### 10.2. Stop Workloads

- Stop incoming API traffic.
- Disable schedulers and triggers capable of generating requests.
- Stop applications and workers.
- Confirm no active write connections from workloads remain on the database.
- Save final logs and outputs needing retention.

### 10.3. Decommission Resources in Dependency Order

- Delete services or workloads attached to the load balancer.
- Delete the lab load balancer and target/backend attachments.
- Decommission VMs after confirming data on disks has been handled.
- Inspect remaining detached disks and delete if retention is not required.
- Release static IPs once no longer attached to resources.
- Delete the database after backups or exports are verified.
- Delete expired objects, old versions, and logs per retention.
- Delete NAT/VPNs or network components created solely for the lab.
- Revoke roles, keys, and secrets used exclusively by the lab.

### 10.4. Post-Cleanup Verification

Re-run inventory and confirm every resource in the manifest is Deleted, Retained, or Pending with a valid reason. Verify no unexpected VMs, disks, IPs, LBs, databases, snapshots, triggers, or log retentions remain.

Wait for billing updates and compare costs by service/SKU. If charges remain, classify whether they are lagging usage, retained storage, network resources, licenses, commitments, or shared costs. Record an assignee and next review date for all unresolved items.

## 11. Cleanup Report Template

The template below helps preserve evidence and handoff records:

~~~yaml
cleanup:
  labId: compute-lab-2026-11-22
  owner: learner-team-a
  completedAt: "2026-11-22T17:30:00Z"
  scope:
    account: training-account
    project: compute-training
    region: region-1
  resources:
    deleted:
      - vm-compute-demo
      - lb-compute-demo
      - ip-compute-demo
    retained:
      - id: lab-results-bucket
        reason: "Retain results until expiration date"
        expiresAt: "2026-12-01"
    pending:
      - id: snapshot-demo-01
        reason: "Verifying retention requirement"
  billing:
    baselineCaptured: true
    lastReviewedAt: "2026-11-22"
    status: pending_provider_data
    remainingItems:
      - "Snapshot storage awaiting decision"
      - "Pre-cleanup compute usage may be billed with delay"
  evidence:
    inventoryExport: cleanup-inventory.csv
    billingExport: lab-cost-review.csv
    operator: learner-team-a
~~~

Never put credentials, access keys, or sensitive payment details in the report. Store evidence files in a location with proper access controls and clear retention.

## 12. Handling Common Scenarios

| Scenario | Possible cause | Resolution |
|---|---|---|
| VM deleted but storage fees remain | Disk or snapshot retained | List detached disks, snapshots, images, and backups |
| Cluster deleted but load balancer remains | Controller provisioned independent cloud resources | Search by tags, cluster ID, service annotations, or manifest |
| Instance stopped but compute cost is nonzero | Instance type or commitment still bills | Check pricing model, dedicated hosts, reservations, and commitments |
| Resource not found in current region | Resource lives in another region or global scope | Scan all relevant regions and global resources |
| Billing keeps rising after cleanup | Billing lag, egress, storage, or active triggers | Cross-check usage dates, SKUs, resource IDs, and event sources |
| Resource lacks tags | Created manually or incomplete tag propagation | Cross-check IDs, owner, audit logs, and creation timestamps |
| Namespace deleted but disk remains | PV reclaim policy is Retain | Inspect PVs, volume attachments, and cloud disks |
| Bucket objects deleted but storage unchanged | Versioning, delete markers, or retention locks | Inspect object versions, lifecycle rules, and retention policies |
| Cannot delete public IP | IP still attached to NIC, LB, or NAT | Remove dependencies in order, then release IP |
| Commitment charges remain after deleting entire lab | Reservations, savings plans, or contracts | Review billing agreements and expiration dates |

If a charge cannot be mapped to a resource ID, the billing operations team or cloud administrator may need to query detailed usage exports and check account-level commitments. Record SKU, usage date, region, and billing scope so investigation can continue.

## 13. Lab Closure Checklist

- [ ] Confirmed exact account/project/subscription, region, owner, and LabId.
- [ ] Stopped pipelines, schedulers, triggers, autoscaling, and workload producers.
- [ ] Archived or deleted data per requirements; verified necessary backups.
- [ ] Stopped services, jobs, tasks, workers, and workloads.
- [ ] Decommissioned lab VMs, nodes, clusters, or compute environments.
- [ ] Checked disks, volumes, snapshots, images, backups, and object versions.
- [ ] Decommissioned unused load balancers, NATs, public IPs, VPNs, and network resources.
- [ ] Checked databases, caches, queues, registries, and event subscriptions.
- [ ] Reviewed logs, metrics, traces, archives, and retention settings.
- [ ] Revoked lab-only secrets, keys, roles, and credentials.
- [ ] Checked reservations, commitments, marketplace licenses, and support plans.
- [ ] Re-ran inventory across all regions and classified Deleted/Retained/Pending.
- [ ] Compared billing by usage date, service, SKU, and tag/label after reporting delay.
- [ ] Every remaining charge has an identified cause, owner, and next review date.
- [ ] Archived cleanup report and inventory/billing evidence per policy.

A lab is considered operationally decommissioned only when workloads have stopped, resources outside retention scope have been handled, and post-cleanup inventory fully accounts for everything remaining. Billing verification requires extra time for usage data to refresh and must account for storage, networking, backups, licenses, and commitments. Clearly distinguishing lagging charges from ongoing charges prevents confusing delayed invoices with resources still actively spending money.