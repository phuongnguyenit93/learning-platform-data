# Mapping VM Concepts Across Amazon EC2, Azure Virtual Machines, and Compute Engine

A virtual machine (VM) is a unit of compute capacity with an operating system, virtual CPUs, memory, network interfaces, and storage disks configured to run workloads. All three major cloud platforms provide VMs, but their service names, network organization, size catalogs, machine identities, and automation tools differ.

In AWS, the VM service is **Amazon EC2**, and an individual machine is called an EC2 instance. In Microsoft Azure, the corresponding service is **Azure Virtual Machines** (Azure VM). In Google Cloud, the VM service is **Compute Engine**, and an individual machine is called a Compute Engine instance. Concepts can be mapped at an architectural level, but specifications and behaviors are not always one-to-one equivalents.

When migrating workloads across clouds, you need to map compute configuration, images, availability zones, networking, disks, identity, machine initialization, scaling, and pricing models. Simply picking a VM with roughly the same vCPU and RAM counts as the old machine is not enough to guarantee equivalent performance, availability, or security.

After this lesson, you will be able to:

- Identify corresponding VM concepts across EC2, Azure Virtual Machines, and Compute Engine.
- Map machine families, images, zones, networking, disks, identities, and autoscaling mechanisms.
- Build equivalent configurations based on workload requirements rather than matching SKU names.
- Inspect VM configurations using the CLI and build a verification checklist for cross-cloud migrations.

## 1. General Concept Map

| Concept | Amazon EC2 | Azure Virtual Machines | Google Compute Engine |
|---|---|---|---|
| Running virtual machine | EC2 instance | Virtual machine (VM) | VM instance |
| Machine family/size | Instance type, e.g., m7i.large | VM size, e.g., a size in the D-series family | Machine type, e.g., n2-standard-2 |
| Boot image | Amazon Machine Image (AMI) | Image or image version in Azure Compute Gallery | Image or image family |
| Geographic region | Region | Region | Region |
| Availability area within a region | Availability Zone (AZ) | Availability Zone (where supported by the region) | Zone |
| Logical private network | VPC | Virtual Network (VNet) | VPC network |
| Subnet | Subnet tied to a single AZ | Subnet within a VNet | Subnet belonging to a region in a VPC network |
| Network interface | Elastic Network Interface (ENI) | Network Interface (NIC) | Network interface |
| Traffic filtering rules | Security Group and Network ACL | Network Security Group (NSG), Azure Firewall, and related network layers | VPC firewall rules, Cloud NGFW, and related network layers |
| Persistent block disk | Amazon EBS volume | Azure Managed Disk | Persistent Disk or Hyperdisk |
| Workload identity on the machine | IAM role via instance profile | Managed Identity | Service account attached to the VM |
| Boot-time initialization | User data, cloud-init | Custom Data, cloud-init, VM extensions | Startup scripts, metadata, and guest agent |
| Auto-scaling VM group | EC2 Auto Scaling group | Virtual Machine Scale Sets (VMSS) | Managed Instance Group (MIG) |

This map helps you locate the right concepts when reading documentation or designing multi-cloud architectures. Continue checking the scope and behavior of each service: for example, a Google Cloud VPC has global scope while its subnets belong to a region; an AWS VPC has regional scope and its subnets are placed in a single AZ. Similar names do not mean identical resource boundaries.

## 2. Mapping CPU and Memory Capacity

Each provider organizes its machine catalog by families and sizes. They can be grouped by purpose:

| Purpose | Amazon EC2 | Azure VM | Compute Engine |
|---|---|---|---|
| General purpose | M families, some T families for burstable loads | D families, B families for burstable loads | E2, N2, and other general-purpose families |
| Compute optimized | C families | F families | C families and certain CPU-optimized families |
| Memory optimized | R, X families, and related variants | E, M families | M families and memory-optimized families |
| Accelerated/GPU | P, G, Trn families, and other accelerator types | GPU-enabled N-series families | Machine types with attached GPUs or supported accelerators |

Family names and generations vary by region, CPU architecture, and product catalog. The table above serves as an initial orientation, not an exact SKU conversion chart. An EC2 M-family VM does not necessarily have the same CPU, memory bandwidth, network performance, or price as an Azure D-family or Google Cloud N2 VM.

### Comparison by Workload Characteristics

- **General purpose:** suitable for web/API servers, application services, utility servers, and workloads with a balanced CPU-to-memory ratio.
- **Compute optimized:** suitable for numerical processing, batch jobs, builds, encryption, and applications requiring high CPU per GB of RAM.
- **Memory optimized:** suitable for large caches, in-memory data analytics, databases, and applications keeping a large working set in RAM.
- **Accelerated:** suitable for AI training or inference, graphics processing, simulations, and workloads leveraging GPUs/accelerators.
- **Burstable:** suitable for workloads with low baseline CPU usage and occasional spikes. You need to understand the credit or baseline CPU mechanism of the exact machine family.

### How to Choose an Equivalent Configuration

During migration, collect at minimum:

1. CPU architecture: x86-64 or Arm64; whether instruction sets and native libraries are supported.
2. vCPU count and actual CPU utilization; one vCPU does not always equate to the same amount of performance across generations.
3. RAM, memory bandwidth, and peak utilization—not just the average.
4. Network performance and limits: bandwidth, packet rate, connection/flow count, and burst behavior.
5. Storage performance: IOPS, throughput, latency, and the number of attachable disks.
6. GPU or accelerator: model, device memory, drivers, runtime, and compatibility.
7. Regional availability, account quotas, reservation availability, and pricing of the target configuration.

For example, if a workload currently runs on a general-purpose EC2 instance with 2 vCPUs and 8 GiB of RAM, you can select an Azure VM or Compute Engine machine type with roughly equivalent capacity as a test candidate. Then benchmark CPU, RAM, network, and disk on both environments. Do not conclude that two machines are equivalent solely because their vCPU and RAM counts match.

For CPU-bound workloads, inspect the CPU generation and single-threaded performance. For memory-bound workloads, measure memory bandwidth and cache misses. For network- or storage-bound workloads, compare actual throughput and latency. Picking a larger machine may resolve bottlenecks, but it also increases cost; sometimes splitting the workload across multiple smaller VMs or moving to a more suitable service is more effective.

## 3. Images, Operating Systems, and VM Initialization

An image is a template for creating the boot disk and initial operating system. All three platforms provide provider-supplied images, marketplace images, and custom images, though their formats and management workflows differ.

| Aspect | EC2 | Azure VM | Compute Engine |
|---|---|---|---|
| Base image | AMI by region and architecture | Platform image, Marketplace image, or custom image | Public image project, image family, or custom image |
| Creating custom images | Create an AMI from an instance or snapshot per workflow | Capture an image or build images in Azure Compute Gallery | Create a custom image from a disk or image pipeline |
| Boot-time configuration | User data; typically cloud-init on Linux | Custom Data; cloud-init on Linux; VM extensions | Startup script via metadata; cloud-init/guest agent depending on image |
| OS updates | Manage patches with OS tools and appropriate AWS services | Azure Update Manager or other management tools | OS patch management and appropriate OS tools |

You should not copy a binary image across clouds and assume the machine will boot. Images can depend on provider-specific drivers, firmware, boot modes, agents, network configurations, disk controllers, and identity provisioning mechanisms. When moving across clouds, it is usually best to rebuild images from standardized OS configurations, install the appropriate agents, and deploy applications using automation.

### User Data, Custom Data, and Startup Scripts

Bootstrap mechanisms let you pass scripts or configurations so the machine automatically installs packages, retrieves settings, registers with monitoring systems, and starts the application. They serve similar roles, though field names, size limits, execution timing, and data storage differ.

For example, a Linux bootstrap script might perform steps conceptually like:

```bash
#!/bin/bash
set -euo pipefail

install_runtime_packages
fetch_configuration_from_secret_manager
configure_monitoring_agent
enable_application_service
```

The function names in the example are placeholders illustrating sequence; replace them with commands matching your OS and organization's configuration tools. Design bootstrap scripts to be idempotent so re-running them does not corrupt state. Avoid embedding passwords, private keys, or long-lived tokens in user data, Custom Data, or metadata, as this data may be persisted or readable by anyone with access to VM metadata/configuration.

## 4. Regions, Zones, and High-Availability Architecture

A region is a geographic area where a provider operates infrastructure. A zone/AZ is an isolated fault domain within a region, enabling deployment of replicas in locations with more independent fault tolerance.

| Provider | Location Concept | Design Considerations |
|---|---|---|
| AWS | Region and Availability Zone | A subnet is created in a single AZ. AZ names like us-east-1a can map differently across accounts; AZ IDs provide more consistent location identification across accounts. |
| Azure | Region and Availability Zone | Only certain regions/SKUs support zones. Verify that the chosen VM size, disk, and network services support the selected zones. |
| Google Cloud | Region and Zone | A VM is created in a single zone. A VPC network is global, while subnets are regional; check machine type availability and quotas in the specific zone. |

For HA deployments, you typically need at least two application replicas in different zones, a load balancer distributing traffic, and a health check mechanism. Verify that databases, disks, NAT, firewalls, DNS, and other dependencies have corresponding fault-tolerant designs. Two VMs in two zones sharing a single disk or a non-fault-tolerant database can still experience outages.

Key differences to note:

- An EC2 Auto Scaling group can distribute instances across multiple AZs within a region.
- Azure VM Scale Sets can be deployed zonally or zone-redundantly depending on configuration and regional capabilities.
- A Compute Engine Managed Instance Group can be zonal or regional; a regional MIG supports distributing VMs across multiple zones in a region.

During migration, preserve your fault-domain and RTO/RPO objectives rather than simply copying the VM count. Verify behavior when a zone loses connectivity, when an instance is replaced, and when the load balancer removes an unhealthy backend.

## 5. Networking and Security Mapping

Networking is one of the areas where cross-cloud differences easily cause migration errors. You must map network architecture and access policies, not just rename VPC to VNet.

| Component | AWS | Azure | Google Cloud |
|---|---|---|---|
| Private network | VPC | VNet | VPC network |
| Subnet | Belongs to a single AZ | Subnet inside a VNet | Subnet belonging to a region |
| Network interface | ENI | NIC | Network interface |
| VM traffic filtering | Security Group attached to ENI/instance | NSG attached to subnet or NIC | VPC firewall rules applied by network and target |
| Routing | Route table attached to subnet | Route table attached to subnet | VPC routes and dynamic routing per configuration |
| Private access to services | VPC endpoints/PrivateLink | Private Endpoint/Service Endpoint | Private Service Connect and private access mechanisms |

### Security Groups, NSGs, and VPC Firewall Rules

- **AWS Security Groups** are stateful firewalls attached to an instance's network interface. Network ACLs can add stateless filtering at the subnet level.
- **Azure NSGs** contain inbound/outbound rules and can be attached to a subnet or NIC; Azure Firewall and other components can add network-level controls.
- **Google Cloud VPC firewall rules** apply at the VPC network level and select targets using network tags or service accounts in appropriate models. Check rule priority order, implied rules, and hierarchical firewall policies if used.

For example, a requirement to "allow HTTPS only from the Internet, SSH only from the management network, and application access to the database over a private port" must be translated into corresponding rules on each platform. You cannot directly translate a Security Group into an NSG or firewall rule without checking source/destination, traffic direction, connection statefulness, priority, and attachment scope.

### IP Addresses and Connectivity

Private IP addresses are typically attached to a NIC or network interface. A public IP may be a separate resource attached to a NIC or instance depending on the platform's model. When stopping/deallocating or replacing a VM, dynamic IP addresses may change; if you need stable addresses, use the appropriate static IP resource and check pricing as well as attachment lifecycle.

Do not expose administrative ports publicly just for convenience. Prefer VPNs, bastions, or controlled remote management solutions using individual identities and session logging. Restrict egress as needed, encrypt traffic, and segment networks across web, application, and database tiers.

## 6. Disks, Snapshots, and Persistent Data

VMs typically have an OS disk and one or more data disks. Persistent block disks decouple data lifecycle from compute lifecycle:

| Need | EC2 | Azure VM | Compute Engine |
|---|---|---|---|
| Persistent block storage | EBS volume | Azure Managed Disk | Persistent Disk or Hyperdisk |
| Snapshot | EBS snapshot | Managed Disk snapshot | Disk snapshot |
| Local/ephemeral disk | Instance store (if supported by instance type) | Temporary disk/local temporary storage depending on size | Local SSD (if supported by machine type) |
| Attaching disk to VM | EBS attach | Managed disk attach | Disk attach |

Local disks typically offer low latency and are suited for cache or scratch data, though data may be lost when the VM stops, is replaced, or fails, depending on the machine type and provisioning mechanism. Do not store unique data or data requiring recovery on ephemeral disks.

When comparing disks, evaluate capacity, performance tiers, max IOPS, max throughput, latency, encryption, resizing capabilities, multi-attach support, snapshot consistency, and the maximum number of disks per VM. Also check whether IOPS/throughput limits come from the disk, the VM size, or both combined.

Snapshots are useful for backups or creating images, but they do not replace a consistent backup strategy for write-heavy applications. For databases, use appropriate backup mechanisms or quiesce/flush the application before snapshotting following supported procedures. Test restores periodically instead of only checking that snapshots were created successfully.

When migrating, determine which data needs to be copied, which can be regenerated, the final sync cutoff time, and how to prevent concurrent writes to both environments. Do not attach the same block volume across multiple VMs or different clouds unless the disk type and filesystem explicitly support that sharing mode.

## 7. VM Identity and Service Access Permissions

A VM often needs to call object storage, secret managers, registries, monitoring, or internal APIs. Each cloud provides a workload identity mechanism so machines receive short-lived credentials instead of storing static access keys:

- EC2 uses an IAM role attached via an instance profile.
- Azure VMs use a system-assigned or user-assigned Managed Identity.
- Compute Engine VMs use a service account attached to the instance.

Grant least-privilege permissions scoped to the exact resources and actions required. For example, a VM that only needs to read objects in a specific bucket/container should not be granted account-wide administrative privileges. Check both the identity used by the application and the permissions of operators creating/modifying VMs.

Items to verify:

1. Does the VM have the right role, managed identity, or service account attached?
2. Is the identity scoped to the right resources without excessive administrative permissions?
3. Does the application obtain credentials via a supported SDK or metadata service?
4. Are untrusted applications prevented from accessing the metadata endpoint or obtaining another workload's credentials?
5. Do logs capture critical API activity for investigation and auditing?

When migrating across clouds, do not copy the old platform's access keys into environment variables on the new machine. Create a new workload identity, assign corresponding permissions, and test the credential retrieval flow before cutover.

## 8. Automation, Scaling, and VM Lifecycle

All platforms offer VM group services to maintain desired instance counts and replace unhealthy machines:

| Capability | AWS | Azure | Google Cloud |
|---|---|---|---|
| VM group | Auto Scaling group | Virtual Machine Scale Sets | Managed Instance Group |
| Scaling | Metric-based, scheduled, or conditional policies | Metric/schedule-based autoscale | Metric/schedule-based autoscaler |
| Health check | EC2 health checks, ELB health checks per configuration | VMSS health extension/load balancer probe per design | MIG autohealing health check |
| Group updates | Launch template/version and instance refresh | VMSS model/upgrade policy | Instance template and rolling update |

VM groups help standardize configurations and replace instances, but they do not automatically make an application stateless or ensure data is stored in the right place. Critical data should reside on persistent storage services; newly launched VMs must be able to boot from standardized images and configurations.

Lifecycle states must also be understood per provider:

- **Stop/deallocate:** the VM is not running compute, though persistent disks and some related resources may continue incurring charges. On Azure, deallocating releases compute allocation; some dynamic IP addresses may be released. On EC2, stopping an instance generally retains EBS volumes, while instance store does not retain data. On Compute Engine, stopping a VM preserves persistent disks; ephemeral external IPs may be released if not static.
- **Delete/terminate:** deleting a VM may retain or delete disks depending on settings and default resource behavior. Always verify disk deletion policies and backups before executing.
- **Resize:** changing machine size may require stopping the VM, and changes can be constrained by zone, quota, CPU architecture, or disk/network capabilities.

For interruptible workloads like batch jobs, consider Spot/Preemptible capacity:

- AWS offers EC2 Spot Instances.
- Azure offers Azure Spot Virtual Machines.
- Google Cloud offers Spot VMs.

These capacity types can be reclaimed according to provider conditions and typically cost less than on-demand capacity. Workloads need checkpointing, retry handling, and must not depend on a single VM. Do not use Spot instances as the sole location for data storage or to run tasks that cannot be restarted.

## 9. Cost Models in Cross-Cloud Comparisons

Do not compare VMs solely by hourly list price. Total cost can include:

`Total cost = compute + disk + snapshot/backup + network + IP/load balancer + license + monitoring + support`

Key factors:

- **On-demand/pay-as-you-go:** suitable for experimentation and unpredictable loads, though unit costs can be higher than long-term commitments.
- **Commitment/discount:** AWS Savings Plans or Reserved Instances, Azure Reservations/Savings Plans, and Google Cloud committed use discounts differ in terms and application rules. Read coverage scope, term length, resource types, and billing conditions carefully.
- **Spot/preemptible:** cost-saving for interruptible workloads; factor in checkpointing, retries, and capacity wait times.
- **Storage:** provisioned disks can incur charges even when the VM is stopped. Snapshots, provisioned capacity, disk performance tiers, and I/O transactions may be billed separately.
- **Network:** cross-region/cross-cloud egress traffic, NAT, load balancers, public IPs, and private connectivity can generate substantial charges.
- **Licensing:** Windows, SQL Server, or commercial software can carry different costs and BYOL terms.

For a fair comparison, use the same region or closely comparable locations, the same measurement period, the same redundancy level, the same target performance, and the same scope of accompanying services. Include HA redundancy and operational overhead, not just the price of a single VM.

## 10. Workflow for Mapping a Workload Across the Three Clouds

Suppose an internal API currently runs on a Linux EC2 instance. The team wants to evaluate moving to an Azure VM or Compute Engine. You can follow this workflow:

1. **Document current configuration:** instance type, CPU architecture, AMI, region/AZ, subnet, security groups, EBS, IAM role, user data, monitoring, and backup approach.
2. **Measure baseline:** CPU, RAM, network, disk IOPS/throughput/latency, request rate, response time, and peak utilization.
3. **Select candidates:** choose an Azure VM size or Compute Engine machine type with matching CPU architecture and capacity close to target; verify GPU, network, disk, and quotas if applicable.
4. **Design placement and networking:** choose region/zone, subnet, private IP, firewall/NSG, routes, DNS, load balancer, and connectivity paths to dependencies.
5. **Build image and bootstrap:** use a supported image, install agents, apply hardening, configure the application, and fetch secrets via workload identity.
6. **Migrate data:** create disks/snapshots or synchronize data using an appropriate mechanism; define the final sync point and rollback plan.
7. **Test:** run the same representative workload and dataset, measuring CPU, memory, network, disk, latency, and cost.
8. **Cut over:** shift traffic in a controlled manner, monitor errors and performance, and keep rollback options ready until stability is confirmed.

You do not have to move every component at once. You can keep the database on the old cloud during testing, though you must account for cross-cloud latency and data transfer costs. If the goal is to evaluate pure compute capacity, isolate network and storage factors so benchmark results remain comparable.

## 11. Inspecting VM Configuration via CLI

The following commands only read existing VM information. Replace placeholders with actual IDs, resource group names, and zones; your CLI account must be logged in and have read permissions on the resources.

**AWS CLI — view instance type, AZ, and state:**

```bash
aws ec2 describe-instances \
  --instance-ids i-0123456789abcdef0 \
  --query 'Reservations[].Instances[].{ID:InstanceId,Type:InstanceType,AZ:Placement.AvailabilityZone,State:State.Name}' \
  --output table
```

**Azure CLI — view VM size, region, zone, and OS disk:**

```bash
az vm show \
  --resource-group rg-app \
  --name app-vm \
  --query '{name:name,size:hardwareProfile.vmSize,location:location,zones:zones,osDisk:storageProfile.osDisk.managedDisk.id}' \
  --output yaml
```

**gcloud CLI — view machine type, zone, status, network, and disks:**

```bash
gcloud compute instances describe app-vm \
  --zone=us-central1-a \
  --format='yaml(name,machineType,zone,status,networkInterfaces,disks)'
```

After reading the configuration, verify additional details that cannot be concluded solely from a VM describe command: workload identity permissions, effective firewall rules, performance metrics, backup policies, autoscaling, and costs. You can use the console, specialized CLIs, or internal management systems to inspect those layers.

## 12. Multi-Cloud VM Mapping Checklist

- [ ] Identified workload, CPU architecture, operating system, and licensing requirements.
- [ ] Compared vCPU, RAM, CPU performance, memory bandwidth, network, and disk via benchmarks.
- [ ] Selected the right image, boot mode, drivers, agents, and bootstrap for the target platform.
- [ ] Mapped region/zone and fault domains according to HA objectives.
- [ ] Redesigned VPC/VNet, subnets, NICs, routes, firewalls, and IPs.
- [ ] Selected appropriate persistent disks, local scratch, snapshots, and backups.
- [ ] Created IAM role, Managed Identity, or service account with least privilege.
- [ ] Configured VM groups, health checks, autoscaling, and rolling updates if needed.
- [ ] Evaluated Spot/preemptible capacity only for interruptible workloads.
- [ ] Accounted for compute, storage, network, licensing, monitoring, and commitments in total cost.
- [ ] Verified metrics, backup restore, failover, rollback, and access permissions before cutover.

When mapping VMs across EC2, Azure Virtual Machines, and Compute Engine, keep the workload's objectives intact and redesign how to achieve them using the corresponding services. A good configuration is one that meets the measured performance, security, availability, and cost targets in the destination environment—not one whose naming resembles the source platform.
