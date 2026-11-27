# Managing OS, Software, and BYOL Licensing

Virtual machines, physical servers, containers, and cloud services can all carry licensing obligations for the operating system or software running inside them. Compute charges shown on a bill do not necessarily include rights to run Windows Server, SQL Server, commercial operating systems, databases, middleware, or specialized software. Without clearly establishing whether a license is included in the service price or must be supplied separately, an organization risks paying twice, lacking usage rights, or failing audit requirements.

BYOL (Bring Your Own License) is a model where customers apply software licenses they already own or purchased under a software vendor agreement, instead of buying licenses bundled with cloud resources. BYOL can lower costs when an organization holds eligible entitlements, yet eligibility depends on version, license type, purchase date, Software Assurance or subscription status, per-core/user/device metrics, execution location, and terms from both the software vendor and the cloud provider.

After this lesson, you will be able to:

- Distinguish license-included, BYOL, and usage-based payment models.
- Identify licensing metrics and usage rights for operating systems, databases, and commercial software.
- Compare licensing options across Amazon EC2, Azure Virtual Machines, and Google Compute Engine.
- Design inventories, tags, deployment controls, and audit evidence for licensed resources.
- Assess how scaling, resizing, host placement, DR, and containers affect licensing obligations.

## 1. Three Common Licensing Models

### License-Included

The cloud provider bundles software usage rights into the VM or service price. For example, certain Windows Server or SQL Server images are offered under a license-included model. Customers pay per image or VM type rate, and the provider handles licensing under the service terms.

Advantages include fast deployment, predictable hourly or per-unit estimation, and no need to bring existing entitlements into the cloud. Verify that the software, edition, version, region, and machine type fall within the license-included catalog. License-included pricing can differ substantially between standard images and images bundling commercial software.

### BYOL (Bring Your Own License)

The customer supplies existing licenses under an agreement with the software vendor. The organization must prove valid entitlement and satisfy deployment conditions—such as licensed core counts, versions, term lengths, workload mobility rights, active Software Assurance/subscription requirements, or dedicated hardware mandates.

BYOL does not mean possessing a product key permits installing software on any VM. Product keys, installers, and usage rights are separate things. An activation key may work technically without proving the organization holds sufficient contractual rights.

### Pay-as-You-Go or Usage-Based Subscription

Some commercial software or operating systems are billed by runtime, cores, users, devices, requests, or subscription tiers. This model may be sold through a cloud marketplace or directly by the software vendor. Determine whether fees are baked into the VM rate, billed separately on the cloud invoice, or invoiced independently by the software vendor.

| Model | Who Supplies Usage Rights? | Common Billing Mechanism | Responsibilities to Verify |
|---|---|---|---|
| License-included | Cloud provider or marketplace per offer | Hourly or per-unit VM/image rate | Select the right image/edition, region, and machine type; verify included scope |
| BYOL | Organization via existing vendor agreement | Purchased license or separate subscription cost | Prove entitlement, calculate required quantity, obey cloud/host conditions |
| Pay-as-you-go | Cloud marketplace or vendor | Hourly, per core, user, device, or usage | Track usage, subscriptions, invoices, and termination terms |

## 2. Identifying Licensing Metrics

Before choosing a VM, read the contract or Product Terms to see which metric governs the software. Common models include:

- **Per core or vCPU:** licensed core count may depend on physical host cores, VM vCPUs, conversion ratios, or per-VM minimums. Never assume one vCPU always equals one licensed core.
- **Per processor/socket:** licenses based on physical CPUs, sockets, or vendor-specific processor definitions. This condition may require knowing the physical host running the VM.
- **Per server/VM:** one license covers one server or VM within contractual bounds. Determine whether cloning, scaling out, or spawning replacement machines consumes extra licenses.
- **Per user or device:** the number of users or devices accessing the software determines license count. Include indirect users, service accounts, and shared devices if required by contract.
- **Per concurrent user/session:** number of simultaneous users or sessions. Requires telemetry and session-capping mechanisms.
- **Per subscription or usage:** billed by duration, requests, transactions, capacity, nodes, or recurring entitlement tiers.

One product may offer multiple options—such as per-core versus per-server plus Client Access Licenses (CALs). Different editions and versions can also carry different terms. Never infer licensing metrics from a product name or from how the cloud bills VMs.

### Rough Core-Based Calculation Example

Suppose a software agreement requires licensing 8 cores per VM regardless of whether the VM has fewer cores. If deploying 6 VMs, the quantity to provision is:

\[
6 \times 8 = 48 \text{ core license}
\]

This is purely an illustrative calculation for a hypothetical "minimum 8 cores per VM" rule. In practice, contracts may count physical host cores, virtual cores, different multipliers, or different minimums. Always apply the exact contractual definition before budgeting.

If autoscaling can scale from 6 to 12 VMs, account for the maximum concurrent VMs, staging environments, standby nodes, and machines spun up during rolling updates if they concurrently run licensed software. A group with a desired capacity of 6 VMs does not mean maximum VM count is always 6.

## 3. Operating System and Application Software Licensing

### Operating Systems

Linux distributions vary in licensing and subscription models. A free Linux image does not mean every support tier, security patch feed, or commercial repository is free. For Red Hat Enterprise Linux (RHEL) or SUSE Linux Enterprise Server (SLES), determine whether the image is cloud-billed PAYG or BYOS (Bring Your Own Subscription) using existing subscriptions. Verify registration, update, support, and cross-environment subscription transfer rights.

Windows Server typically offers license-included options and, in certain cases, allows using existing rights under Microsoft terms. Verify edition, version, core count, host type, license purchase date, and attached Software Assurance or subscription rights. Never install Windows from a private ISO onto a VM assuming the compute price covers the license.

### Databases, Middleware, and Applications

SQL Server, Oracle Database, SAP, commercial middleware, security software, backup agents, and management tools can each have distinct terms. One VM may simultaneously require licenses for OS, database, and applications. For example, a Windows license-included VM price does not automatically include SQL Server; select a SQL Server license-included image or supply valid SQL Server rights under contract.

For core- or socket-licensed software, record VM type, host placement, core count, and vendor counting rules. For user/device-licensed software, maintain user lists and access permissions. For subscription software, track start dates, expiration dates, renewals, and seat counts.

### Containers and Application Images

Packaging software inside a container does not automatically eliminate licensing obligations. Determine whether licenses bind to hosts, nodes, cores, container instances, users, or workloads. If a container scales to 20 replicas, the contract may count it differently from a single instance on a VM.

Container images can include libraries, runtimes, database clients, or commercial software. Check image redistribution terms, library licenses, and copying images to other registries or clouds. License scanners can detect packages and versions, but scan results do not replace reading the contract.

## 4. License-Included and BYOL Across Clouds

All three major clouds offer mechanisms to choose license-included images or deploy software with existing entitlements. Service names and eligibility vary by product, region, license purchase date, and vendor agreement.

| Platform | License-Included Options | BYOL or Entitlement Management Mechanisms |
|---|---|---|
| AWS | AMIs/instances bundling Windows Server or commercial software per offer | AWS License Manager for inventory and rules; EC2 Dedicated Hosts may be required for licenses bound to physical servers |
| Azure | Certain Windows Server, SQL Server, and marketplace images include license pricing | Azure Hybrid Benefit for eligible licenses; Azure Dedicated Host provides isolated physical hosts where host control is required |
| Google Cloud | Certain public/marketplace images bill software fees by usage | Sole-tenant nodes can satisfy certain BYOL scenarios requiring dedicated hardware; verify product-specific license terms |

### AWS

Amazon EC2 offers images and pricing options that can include licenses for certain operating systems or software. When using BYOL, the organization must confirm whether the license permits running in the cloud and on the intended host type.

AWS License Manager supports creating license configurations, tracking usage, and enforcing rules on integrated resources. It is useful for inventory management, though it does not independently validate every vendor contractual clause. For licenses tied to physical servers or requiring hardware placement control, EC2 Dedicated Hosts may be part of the architecture. A Dedicated Host provides a physical host dedicated to your account; review instance types, host allocation, affinity, and related license terms.

Distinguish EC2 Dedicated Hosts from Dedicated Instances. Dedicated Instances run on single-tenant hardware under the service model yet do not expose the same host visibility and control as Dedicated Hosts. Do not pick Dedicated Instances assuming they automatically satisfy every BYOL requirement.

### Microsoft Azure

Azure can provide VM images with OS or software licenses bundled in the rate. For eligible licenses, Azure Hybrid Benefit allows applying existing rights to reduce or waive eligible license fees within Azure service pricing. Eligibility may require qualifying Windows Server or SQL Server licenses with active Software Assurance or qualifying subscriptions.

Azure Hybrid Benefit is not a universal BYOL right for every product. Verify the exact product, version, edition, core count, subscription type, dual-use rights during migration windows, and term limits. Azure Dedicated Host provides a dedicated physical server for the customer; it can support host-based licensing scenarios, though owning a dedicated host does not by itself create entitlement.

### Google Cloud

Google Cloud provides public and marketplace images that can charge software license fees based on usage. For software requiring dedicated hardware or physical host visibility, sole-tenant nodes let VMs run on hardware nodes dedicated to a single customer within the service scope. BYOL eligibility still must be confirmed against the license agreement and Google Cloud guidance for the specific product.

Do not assume every Windows, database, or commercial software product can use BYOL on sole-tenant nodes. Check the product, license purchase date, cloud mobility rights, machine type, host maintenance behavior, and vendor core-counting rules.

## 5. BYOL, Software Assurance, and License Mobility

Some contracts allow moving licenses from on-premises servers to the cloud or between environments, subject to conditions. Terms such as Software Assurance, subscriptions, License Mobility, Flexible Virtualization Benefit, or dedicated host usage rights carry specific meanings depending on the product and contract signing date.

Before applying BYOL, verify:

1. Does the license match the exact product, edition, version, and metric required?
2. Does the contract allow deployment on public cloud?
3. Does it require Software Assurance, an active subscription, or License Mobility?
4. Are there restrictions by region, country, host type, shared tenancy, or dedicated tenancy?
5. Is there a minimum reassignment period after assigning a license to a server before moving it?
6. Is running old and new versions concurrently allowed during migration, DR, or rolling upgrades?
7. Must licenses be registered with the cloud provider or physical host records retained?

Never assume one vendor's terms apply to another vendor. For instance, License Mobility on a Microsoft product does not automatically apply to Oracle Database, RHEL, backup software, or third-party applications. When terms are ambiguous, obtain written confirmation from the software vendor or contract management team before deploying.

## 6. Inventory Management and Licensing Evidence

A sound inventory links three datasets: purchased entitlements, running resources, and license calculation rules. Storing only product keys or image names makes it hard to prove entitlement coverage or spot over-deployment.

### Recommended Data Fields

| Group | Suggested Fields | Purpose |
|---|---|---|
| Product | Vendor, product, edition, version | Precisely identify the software |
| Usage rights | License model, metric, entitlement quantity, agreement reference | Know available rights and counting rules |
| Conditions | Purchase date, SA/subscription status, mobility rights, territory, host requirements | Verify validity and permitted deployment targets |
| Resources | Cloud, account/subscription/project, region, zone, VM ID, instance type, host ID | Link licenses to live workloads |
| Scale | vCPUs, physical cores if available, VM count, max scale, user/device count | Compute required license count |
| Accountability | Service owner, license owner, cost center, review date | Identify accountable owners |
| Evidence | Contract reference, invoice reference, vendor confirmation, audit reports | Support audits without putting secret keys in tags |

Governance tags/labels can be attached to VMs or resource groups, for example:

| Tag | Example Value |
|---|---|
| `license-model` | `BYOL` |
| `license-product` | `SQL-Server-Standard` |
| `license-owner` | `data-platform-team` |
| `license-metric` | `core` |
| `license-contract-ref` | `AGR-2026-014` |
| `license-review-date` | `2027-03-31` |

The values above are illustrative. Never store product keys, passwords, license files, or sensitive contract details directly in tags because tags are broadly visible and can appear in logs, reports, or APIs. Store only reference IDs pointing to an access-controlled record repository.

### Periodic Reconciliation Process

1. Gather purchased license records from contracts, invoices, and asset management systems.
2. Pull inventories of running VMs, images, disks, hosts, container nodes, and applications across cloud accounts.
3. Identify the license model of each image and installed software package.
4. Compute demand using the exact metric: core, VM, host, user, device, subscription, or usage.
5. Compare demand against active entitlements; flag deficits, surpluses, upcoming expirations, or unclear rights.
6. Assign owners to resolve discrepancies and record decision evidence.
7. Repeat on VM creation, resize, scaling, image cloning, host changes, or region/cloud moves—not just at audit time.

## 7. Controlling Licensing Across the Compute Lifecycle

### Before VM Creation

- Allow only approved images from catalogs or pipelines.
- Explicitly declare `license-included` or `BYOL` in deployment configs.
- Verify entitlements and host conditions before granting quotas or creating machines.
- Select compliant machine types, regions, zones, and tenancy per vendor terms.
- Account for maximum counts generated by autoscaling or rolling deployments.

### During Resizing, Cloning, or Autoscaling

Resizing a VM can change vCPU count or host placement, affecting licensing metrics. Cloning images or launching new VMs increases the number of machines running the software. Auto Scaling can spawn more replicas than expected if you look only at desired capacity while ignoring max capacity.

For core-based licenses, recalculate upon size changes. For VM-based licenses, cap concurrent instances. For physical-host licenses, track which host each VM lands on and license-assignment rules. For user/device licenses, update access lists whenever users or devices are added.

### During Stop, Termination, or Environment Moves

Stopping a VM does not necessarily end licensing obligations. Subscriptions may continue recurring billing; licenses may stay bound to a machine or host for a cooling-off window. Terminating a VM may not immediately free entitlements if the contract specifies waiting periods or reassignment workflows.

During migrations, establish transfer dates, permitted dual-run days, data sync methods, old-machine shutdown timing, and termination or reassignment evidence. For DR, verify whether standby nodes can run concurrently, whether active/passive rules apply, and how failover affects license counts.

## 8. Controlling Software Inside Images and Containers

VM and container images should be built in controlled pipelines. Pipelines can store SBOMs (Software Bill of Materials), package scan results, base image versions, and license origins. When updating images, detect newly introduced commercial packages or edition changes.

A basic workflow:

1. Select a base image from an approved source.
2. Scan packages and generate an SBOM.
3. Cross-check packages against approved software catalogs and the license inventory.
4. Attach product/version/license-model metadata to the artifact or registry record.
5. Release the image only after the owner confirms usage rights.
6. Re-scan periodically and whenever CVEs or vendor term changes occur.

For Kubernetes or container platforms, inventories must include node hosts, replica counts, and autoscaling behavior. If a vendor licenses by node cores, count total cores across every node pool capable of scheduling the software. If licensed per container or instance, track concurrent replicas and contractual counting rules. Never rely on a single point-in-time running Pod count if workloads autoscale rapidly or shift across nodes.

## 9. Practical Example: Choosing Licenses for Windows VMs and SQL Server

A team needs to run an internal application across 4 Windows VMs and a SQL Server database. The team has two options:

**Option A — license-included:** choose Windows/SQL Server images with bundled license pricing if the required product and edition are offered. Cloud bills reflect the image or configuration surcharge. This is straightforward for experiments or workloads lacking eligible BYOL entitlements.

**Option B — BYOL/Hybrid Benefit:** inspect Windows Server and SQL Server contracts, versions/editions, core counts, Software Assurance or subscription rights, cloud mobility rights, and tenancy conditions. If eligible, select permitted VM types and deployment models, register entitlements per provider guidance, attach inventory metadata, and archive evidence.

To compare, do not merely multiply the 4-VM license-included rate against a past license purchase price. Factor in:

- How much unused entitlement remains and which workloads already claim it.
- Whether additional licenses or active Software Assurance/subscriptions must be purchased.
- Whether SQL Server is licensed per core or under server/CAL.
- How high VM counts can rise under autoscaling or DR activation.
- Whether dedicated hosts, reassignment cooldowns, or migration dual-run limits apply.
- Whether compute, disk, backup, network, and support costs differ between options.

License-included may turn out cheaper and simpler for short-lived workloads, whereas BYOL wins when the organization holds sufficient entitlements and steady workloads. Always base decisions on current live entitlements and pricing.

## 10. Checking Inventory via CLI

The commands below gather partial infrastructure details for reconciliation against license records. They do not fully establish software usage rights; combine them with image offers, contracts, Software Assurance/subscriptions, host placement, and application inventories.

**AWS CLI — inspect instances, images, machine types, and tenancy:**

```bash
aws ec2 describe-instances --query 'Reservations[].Instances[].{ID:InstanceId,Type:InstanceType,Image:ImageId,Platform:PlatformDetails,Tenancy:Placement.Tenancy,State:State.Name}' --output table
```

**Azure CLI — list VMs and selected deployment attributes:**

```bash
az vm list --show-details --query '[].{Name:name,ResourceGroup:resourceGroup,Location:location,Size:hardwareProfile.vmSize,OS:storageProfile.osDisk.osType,LicenseType:licenseType}' --output table
```

**Google Cloud CLI — list VMs, machine types, zones, and labels:**

```bash
gcloud compute instances list --format='table(name,zone,machineType,status,labels)'
```

After collecting output, cross-reference each VM against its image ID/offer, package inventory, running applications, and entitlement records. API license or platform detail fields may omit licenses for software installed post-provisioning.

## 11. Audits and Handling Discrepancies

A license audit typically requires proving both purchased rights and how those rights are deployed. Records should include:

- Contracts, purchase orders, invoices, and applicable product/version terms.
- Entitlement quantities, licensing metrics, and effective dates.
- Proof of Software Assurance, subscriptions, or License Mobility rights where required.
- Inventories of VMs, hosts, cores, users/devices, containers, and installed software.
- Image/marketplace offers, license models, and dedicated tenancy configs where relevant.
- History of creation, resizing, cloning, scaling, stopping, termination, and workload moves.
- Reconciliation results, approved exceptions, and remediation plans.

When an unverified-license resource is discovered, first identify the owner, software, version, and licensing metric. Pause scaling or additional deployments if there is risk of exceeding entitlements. Next, verify contracts, consult the vendor or license management team, switch to license-included images where suitable, or procure additional entitlements. Record decisions and remediation timestamps.

Never delete VMs or swap images merely to erase audit trails. Retain logs, inventory snapshots, and configuration evidence per organizational retention policies. Never paste product keys or license files into tickets, logs, or broadly accessible reports.

## Licensing Management Checklist

- [ ] OS/software product, edition, version, and vendor identified.
- [ ] Classified as license-included, BYOL, or pay-as-you-go/subscription.
- [ ] Licensing metric verified: core, processor, VM, host, user, device, or usage.
- [ ] Cloud mobility, Software Assurance/subscription, and dedicated host terms verified where applicable.
- [ ] Correct image/offer and tenancy type selected for the workload.
- [ ] Maximum concurrent counts calculated for autoscaling, rolling updates, DR, and parallel migrations.
- [ ] Inventory links entitlements to VMs, hosts, applications, and owners.
- [ ] Governance tags applied with secure record references; no product keys in tags.
- [ ] Images/containers scanned, SBOMs stored, and commercial software reconciled.
- [ ] Expiration dates, remaining entitlements, costs, and discrepancies reviewed periodically.
- [ ] Audit evidence and exception-handling workflows maintained.

License management is an integral part of compute resource governance. Decide the licensing model before deployment, tie entitlements to live inventories, and re-check whenever VMs change size, count, host, or environment. BYOL pays off only when entitlements fit and the organization can prove compliant usage under contract terms.
