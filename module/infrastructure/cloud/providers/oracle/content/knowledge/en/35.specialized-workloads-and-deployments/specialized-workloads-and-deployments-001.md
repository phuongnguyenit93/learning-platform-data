# Oracle Cloud VMware Solution and SDDC Organization

Oracle Cloud VMware Solution (OCVS) enables you to deploy a **Software-Defined Data Center (SDDC)** on dedicated bare metal infrastructure in Oracle Cloud Infrastructure (OCI). It is an approach for moving a VMware environment to OCI while continuing to use many existing administration skills and tools. [Oracle: OCVS overview](https://docs.oracle.com/en-us/iaas/Content/VMware/Concepts/ocvsoverview.htm).

In the **Specialized Workloads and Deployments** chapter of the **CLOUD_PROVIDERS_ORACLE** module, this lesson focuses on how to organize an SDDC within the picture of OCI tenancy, compartments, IAM, VCN, Compute, and storage. An operable SDDC requires VMware design, connectivity to Oracle services, access control, observability, redundancy, and cost management.

After this lesson, learners can:

- Distinguish OCI resources from administrative objects inside VMware.
- Choose boundaries for SDDCs, clusters, resource pools, and networks for each workload group.
- Plan IP addressing, storage, and capacity for host failures or maintenance.
- Describe deployment, virtual machine migration, operations, and recovery flows with verifiable criteria.

## 1. What Problem Does OCVS Solve?

An enterprise is running ERP applications, integration services, and business servers on VMware in a private data center. The applications still meet business needs, but the hardware is due for refresh. The enterprise wants to move workloads to OCI, leverage connectivity to Oracle database and storage services, and keep application changes within an acceptable timeframe.

OCVS is an option for that infrastructure transition phase. However, the decision should be based on the actual dependencies of each application:

| Deployment approach | Suitable characteristics | Work requiring evaluation |
| --- | --- | --- |
| Run VMs on OCVS | Need to continue using the VMware ecosystem, backup tools, or current administration model | Cluster capacity, software compatibility, networking, and VMware operational responsibilities |
| Migrate to OCI Compute | Can standardize servers and management processes around OCI | Image conversion, drivers, bootstrap, backup, and automation |
| Refactor to containers or managed services | Applications allow changes to architecture and release processes | Data, state, service communication, observability, and team skills |

This table is an architecture evaluation guide, not a claim that every workload can migrate the same way. For example, moving application VMs to OCVS and moving a database to a separate Oracle database service are two distinct changes. Each change needs compatibility testing and its own rollback plan.

Do not assume that "keeping the VMs" means "keeping the entire environment unchanged." Network addresses, paths to DNS, certificates, latency between tiers, and licensing systems can still change.

## 2. Components and Two Administrative Scopes

### 2.1. Components Inside an SDDC

A VMware environment combines components that serve compute, management, networking, storage, and workload migration:

| Component | Role | What to identify during operations |
| --- | --- | --- |
| ESXi | Hypervisor running on each bare metal host | Which host runs which VM; which host still has sufficient resources |
| vCenter Server | Centralized management point of the vSphere environment | Inventory, clusters, administrative permissions, tasks, and alarms |
| NSX | Virtual networking and SDDC network security functions | Segments, gateways, Edges, routes, and traffic policies |
| vSAN | Distributed storage when using a vSAN-enabled configuration | Storage policies, capacity, object health, and resynchronization |
| HCX, when deployed | Supports workload migration between environments | Site connectivity and migration method prerequisites |

Do not assume every shape uses the same storage model. Datastore design is covered separately in a later section. Software components and supported capabilities must be verified against the selected OCVS configuration. [Oracle: VMware software components](https://docs.oracle.com/en-us/iaas/Content/VMware/Concepts/ocvsoverview.htm).

### 2.2. OCI and VMware Have Different Administrative Permissions

**The OCI scope** includes SDDC service resources, hosts provisioned by OCVS, VCN networking, VLANs, Block Volumes, IAM, and related services. The Console, API, CLI, and infrastructure-as-code tools interact with this scope.

**The VMware scope** includes vCenter inventory, VMs, resource pools, datastores, and NSX configuration. Users need accounts, roles, and connectivity to VMware tools to operate here.

Someone with permission to view an SDDC in OCI does not necessarily have permission to log in to vCenter. Conversely, someone who administers VMs in vCenter is not necessarily allowed to add hosts in OCI. Identity integration can help centralize account management, but permissions must still be designed for each system.

Provider and customer responsibilities must also be separated. Oracle secures the physical infrastructure, while the customer is responsible for securely configuring and updating their VMware components. [Oracle: OCVS security responsibilities](https://docs.oracle.com/en-us/iaas/Content/Security/Reference/vmware_security.htm).

The practical consequence is that the operations team must maintain maintenance schedules, compatibility checks, configuration backups, and VMware incident response procedures. Provisioning an SDDC through a cloud service does not automatically replace those tasks.

## 3. Organizing SDDCs, Clusters, and Workloads

### 3.1. Hierarchy to Understand

You can view the organizational model as two parallel branches:

~~~text
OCI
Tenancy
└── Compartment for the VMware platform
    ├── SDDC resources and associated clusters/hosts
    ├── VCN, VLANs, route tables, and NSGs
    └── Storage resources and operational integrations

VMware
SDDC vCenter
└── Datacenter in inventory
    ├── Unified management cluster
    │   ├── Management appliances
    │   └── Workloads permitted by design
    └── Workload cluster
        ├── Resource pools
        └── Application virtual machines
~~~

This diagram illustrates an administrative view and does not mean all related resources must reside in the same compartment. For example, the networking team might manage a shared VCN in a separate compartment and grant required permissions to the platform team.

**An OCI compartment is not equivalent to a vCenter folder or resource pool.** Placing two VMs in two folders does not give them two different OCI IAM scopes. Conversely, placing an SDDC in a separate compartment does not automatically create isolation policies between VMs.

### 3.2. Unified Management Cluster and Workload Cluster

The first cluster created is the **unified management cluster**, which hosts shared SDDC management components, including vCenter, NSX Manager, and NSX Edge. This cluster can also run workloads. Additional clusters are **workload clusters** and do not receive a separate set of SDDC management components simply by being created. [Oracle: cluster types in an SDDC](https://docs.oracle.com/en-us/iaas/Content/VMware/Tasks/clusters.htm).

This creates a trade-off:

- Using the management cluster for applications as well helps utilize resources, but you must protect the capacity reserved for management.
- Dedicating a separate workload cluster to applications makes capacity planning and maintenance clearer.
- Even when workloads reside in another cluster, the dependency on the SDDC's shared management services remains.

If vCenter encounters an issue, many running VMs may continue operating, but centralized management operations are affected. If a networking component encounters an issue, the impact depends on that component's role and redundancy configuration. Do not use "VMs are still powered on" as proof that the entire platform is healthy.

### 3.3. Choosing Appropriate Boundaries

The table below is a design guide and should be adapted to organizational requirements:

| Boundary | When to consider | Limitation of the boundary |
| --- | --- | --- |
| vCenter folders and tags | Categorizing applications, owners, lifecycle, and permission assignment scope | Does not automatically reserve CPU/RAM or create network isolation |
| Resource pools | Allocating shares, reservations, and limits for workload groups | Does not replace network policies or SDDC administrative boundaries |
| Separate cluster | Different hardware needs, maintenance windows, redundancy levels, or workload placement rules | Still shares the SDDC's common management components |
| Separate SDDC | Need to separate management domains, reduce blast radius, or manage independent lifecycles | Increases platform, operational, and connectivity costs |
| Separate compartment | OCI access control, resource governance, and cost tracking | Does not automatically divide permissions inside VMware |

A requirement such as "the testing team must not interfere with production" must be translated into concrete controls: vCenter permissions, NSX permissions, OCI permissions, management access networking, and secrets protection. Simply naming folders `prod` and `test` does not meet the requirement.

Do not hardcode maximum cluster or host counts in long-term design documents. Limits depend on cluster type, shape, version, and tenancy quotas; verify them before deployment. [Oracle: managing an SDDC and configuration limits](https://docs.oracle.com/en-us/iaas/Content/VMware/Tasks/ocvsmanagingsddc.htm).

### 3.4. Example Organization for a Production Environment

Suppose you need to move 40 business VMs to OCI, divided into 24 ERP VMs, 10 integration VMs, and 6 supporting service VMs. Databases are evaluated separately to be placed on an Oracle database service with private connectivity.

An initial design option:

| Object | Illustrative name | Purpose |
| --- | --- | --- |
| Compartment | `cmp-vmware-prod` | Manage production platform resources |
| SDDC | `sddc-prod01` | Production VMware management domain |
| Unified management cluster | `prod-unified01` | Management appliances and their failover capacity |
| Workload cluster | `prod-erp01` | Run ERP, integration, and supporting service workloads |
| Resource pools | `rp-erp`, `rp-integration`, `rp-shared` | Allocate resources according to defined priority levels |
| NSX security groups | By web, app, and service roles | Apply communication policies between tiers |

Host counts are finalized only after calculating load, redundancy headroom, and verifying configurations supported by OCVS. In this example, the management cluster is planned with three hosts; the workload cluster will be sized in the capacity section. This is hypothetical data for learning design, not a standard configuration for every system.

## 4. Network Design: VCN, VLANs, and NSX Overlay

### 4.1. Separating Underlay Networking and Virtual Machine Networking

At the OCI layer, the SDDC requires network resources for platform provisioning and operation. At the VMware layer, NSX creates segments to connect VMs and control application flows.

Some VLAN functional groups to identify:

| Functional group | Traffic type |
| --- | --- |
| vSphere | Management of SDDC components |
| vMotion | Live migration of VM state between hosts |
| vSAN | vSAN storage traffic when used |
| NSX VTEP and NSX Edge VTEP | Overlay network data plane traffic |
| NSX Edge Uplink | Connectivity between the SDDC and OCI networking |
| Provisioning and version-specific VLANs | Certain provisioning, cloning, or migration operations |
| HCX, if enabled | Traffic serving HCX |

The exact list depends on the version and deployment workflow. Do not infer uplink purposes or delete service-created VLANs based solely on their names. [Oracle: SDDC VLAN functions](https://docs.oracle.com/en-us/iaas/Content/VMware/Tasks/vlan-create.htm).

An NSX segment containing application VMs **does not automatically become a VCN subnet**. Nor does a VM automatically appear as an OCI Compute instance to which you can attach an NSG directly like a standard OCI virtual machine.

### 4.2. Address Planning Before Creating an SDDC

The example below uses non-overlapping private CIDR ranges:

| Scope | Illustrative range | Meaning |
| --- | --- | --- |
| Existing data center | `10.10.0.0/16` | On-premises network |
| VCN for OCVS | `10.60.0.0/16` | OCI underlay network address space |
| Reserved range for management cluster | `10.60.0.0/21` | For the workflow to carve subnets/VLANs per design |
| Reserved range for workload cluster | `10.60.8.0/21` | Planned for network resources of additional clusters |
| Database service VCN | `10.80.0.0/16` | Contains appropriate service subnets |
| NSX segment for web | `172.20.10.0/24` | Web-tier VM network |
| NSX segment for app | `172.20.20.0/24` | Application-tier VM network |

The two `/21` blocks are **reserved address allocations**, not a requirement to turn each entire block into a single subnet. Actual sizing and subnetting must match the planned host count, the network resources required by the workflow, and expansion plans. Oracle allows the workflow to create networks or use prepared network resources. [Oracle: preparing and creating an SDDC](https://docs.oracle.com/en-us/iaas/Content/VMware/Tasks/ocvssettingupsddc.htm).

When planning, also cross-check user VPN ranges, partner networks, DR sites, and NSX ranges currently used on-premises. Two networks that do not overlap when creating the SDDC can still conflict when connecting additional partners later.

Do not fix CIDR overlaps by adding arbitrary routes. Choose a deliberate addressing or NAT approach, documenting the impact on DNS, logging, security, and migration.

### 4.3. Understanding Forward and Return Paths

For example, an application VM needs to connect to a database in another VCN:

~~~mermaid
flowchart LR
    VM["Application VM"]
    SEG["NSX segment"]
    GW["NSX T1 / T0 Gateway"]
    EDGE["NSX Edge Uplink"]
    OCI["OCI Network and DRG"]
    DB["Database service subnet"]

    VM --> SEG --> GW --> EDGE --> OCI --> DB
    DB -. "Return path must reach overlay CIDR" .-> OCI
    OCI -.-> EDGE
    EDGE -.-> GW
    GW -.-> VM
~~~

This is a logical flow diagram; T1/T0 and Edge do not necessarily correspond to separate physical devices.

When connecting to another VCN, check the destination subnet's route table, DRG routes, and OCVS-side configuration so the overlay CIDR is reachable. Oracle documentation illustrates declaring routes to NSX networks via DRG and the SDDC connectivity workflow. [Oracle: connecting NSX overlay to another VCN](https://docs.oracle.com/en/learn/oci-connect-ocvs-nsxt-overlay/index.html).

For on-premises networks, DRG combined with FastConnect or Site-to-Site VPN establishes private connectivity. The OCVS workflow can assist with routing and security resources between the DRG and NSX Edge Uplink. You must still verify configuration and return paths on the data center side. [Oracle: connecting an SDDC to an on-premises network](https://docs.oracle.com/en-us/iaas/Content/VMware/Tasks/ocvsconfigconnectivity_topic-Configuring_Connectivity_to_Your_Onpremises_Network.htm).

A successful connection requires all of the following simultaneously:

1. Non-conflicting source and destination addresses.
2. DNS returning the address matching the intended access path.
3. Routes in both directions.
4. Security policies permitting the exact protocol and port.
5. The target service actively listening.
6. MTU and path characteristics suited to the traffic type.

For example, a successful ping does not prove database connectivity works. You must test against the actual listener, then verify authentication and a simple business transaction.

### 4.4. Security Segmentation by Business Flow

Do not open the entire network just to complete a migration. Document the required flows:

| Source | Destination | Illustrative flow | Purpose |
| --- | --- | --- | --- |
| Controlled management network | VMware management endpoints | HTTPS and strictly required admin ports | Platform operations |
| Application entry point | Web group | TCP 443 | Web access |
| Web group | App group | TCP 8443, if used by the application | Business processing |
| App group | Database listener | Configured port, e.g., TCP 1521 | Data connectivity |
| VMs and appliances | Selected DNS/NTP | Protocols serving DNS/NTP | Name resolution and time synchronization |
| Backup components | Protected targets | Per backup product | Backup and recovery |

Ports in the table are design examples; replace them with the protocols of the actual system. In particular, the listener port alone does not prove the database transport is encrypted.

Assign enforcement points clearly: NSGs and OCI network controls protect appropriate OCI boundaries; NSX policies control flows inside the SDDC; OS firewalls protect target hosts. To prove a test VM cannot reach a production VM, test that exact flow between those two VMs, even when traffic never leaves the SDDC.

## 5. Organizing Storage and Calculating Fault-Tolerant Capacity

### 5.1. Choosing a Datastore Model by Shape

Dense shapes include local NVMe storage for vSAN; Standard shapes do not provide that local NVMe storage and use OCI Block Volume for appropriate storage needs. Therefore, choose the shape together with the datastore model, rather than looking only at CPU and RAM. [Oracle: OCVS shapes and storage FAQ](https://www.oracle.com/cloud/compute/vmware/faq/).

| Aspect | vSAN with local storage | VMFS datastore on OCI Block Volume |
| --- | --- | --- |
| Capacity source | Storage devices of participating hosts | Block Volumes provisioned and attached per supported configuration |
| Relationship to host scaling | Adding hosts can add both compute and storage | Storage capacity can be planned independently from compute |
| What to monitor | Policies, object health, free space, and resync | Datastores, access paths, volume capacity, and performance |
| Design risk | Confusing raw capacity with usable capacity | Confusing OCI volume creation with completed VMware configuration |

OCVS provides **Datastore Management** to manage the OCI side of Block Volume-based datastores and datastore clusters. This feature does not manage all block storage configuration inside vCenter; the operations team must still verify the VMware side. [Oracle: Datastore Management and scope of responsibility](https://docs.oracle.com/en-us/iaas/Content/VMware/Tasks/datastores.htm).

### 5.2. Raw Capacity Differs from Usable Capacity

With vSAN, the storage policy determines data protection and capacity consumption. A preliminary calculation can be written as:

~~~text
Capacity for application data
≈ (Raw capacity / data protection multiplier)
  × (1 - slack space ratio)
  - other overhead consumers
~~~

Assume an example independent of the ERP configuration: four hosts provide a total of 60 TB raw. If using a two-copy mirroring model, the preliminary multiplier is 2:

~~~text
60 TB / 2 = 30 TB

If 20% of this is further reserved as slack space:
30 TB × 0.8 = 24 TB
~~~

24 TB is only an illustrative estimate. Metadata, specific policies, snapshots, management data, and rebuild capability further alter the result. Nor should this mirroring multiplier be applied to every RAID configuration or every vSAN generation.

The storage plan must answer: after a host failure, can the system still serve data, is there enough space to re-establish protection levels, and how does that rebuild process affect latency?

### 5.3. Sizing for Degraded State

Low normal utilization is not enough to prove fault tolerance. A preliminary RAM check:

~~~text
(N - F) × R × U ≥ D + M
~~~

Where:

- N: number of hosts in the cluster.
- F: number of hosts expected to be unavailable simultaneously due to failure or maintenance.
- R: RAM per host in a homogeneous model.
- U: target maximum utilization ratio on the remaining hosts.
- D: workload RAM demand.
- M: overhead allowance for system and related components not included in D.

Suppose the ERP workload requires 620 GiB, system overhead allowance is 64 GiB, each host has 256 GiB, and the target maximum utilization is 80%. To tolerate losing one host:

~~~text
N = 4:
(4 - 1) × 256 × 0.8 = 614.4 GiB
D + M = 620 + 64 = 684 GiB
=> Does not pass.

N = 5:
(5 - 1) × 256 × 0.8 = 819.2 GiB
=> Passes preliminary RAM check.
~~~

Thus, the illustrative design selects at least five hosts for the workload cluster under these assumptions. This result does not finalize the configuration: you must still check CPU, large VM placement, reservations, storage latency, bandwidth, shape limits, and growth.

Do not convert vCPUs directly to OCPUs using a fixed ratio and conclude resources are sufficient. CPU ready time, concurrent load, processor architecture, and large VM requirements can all change the outcome.

If the requirement is "one host under maintenance while another host fails," you must calculate with F = 2 and re-verify both compute and storage. N+1 does not automatically satisfy N+2.

### 5.4. Protecting Management Resources

For a unified management cluster, reserve sufficient resources for appliances during host failures, upgrades, and heavy management operations. When allowing applications to share this cluster, apply appropriate priority and limit policies.

Avoid setting limits too low, which can starve management appliances even when the cluster still has idle RAM or CPU. Also avoid unfounded reservations that reduce VM placement flexibility during failures.

## 6. Identity, Permissions, and Operational Metadata

### 6.1. Proposed Responsibility Matrix

| Group | Task-based OCI permissions | Task-based VMware permissions |
| --- | --- | --- |
| Platform team | Manage assigned OCVS resources | Administer clusters, hosts, and platform lifecycle |
| Network team | Manage VCN, VLANs, routes, NSGs, or DRG within assigned scope | Administer NSX networking if assigned |
| Application team | View required OCI resources | Administer application VMs within granted scope |
| Monitoring team | Read permitted status, metrics, and logs | Read inventory, alarms, and required operational data |
| Audit team | Read appropriate evidence and logs | View configuration and events within audit scope |

This is a design matrix, not a complete policy set ready to copy and apply. Actual policies must account for group names, identity domains, compartments holding dependent resources, and individual API permissions.

Prefer named individual accounts for day-to-day work. Privileged accounts for emergency recovery must be controlled, stored in a secrets manager, and audited when used. Do not place appliance passwords, SSH keys, or tokens in design documents, repositories, or log pipelines.

Permission to view resource metadata also requires consideration: endpoints, hostnames, and infrastructure layout can be sensitive even without directly containing passwords.

### 6.2. Tagging and Ownership Tracking

Illustrative design tags:

~~~yaml
environment: prod
owner: platform-team
cost-center: erp
application: shared-vmware-platform
recovery-tier: critical
data-classification: internal
~~~

This is an illustrative convention, not direct input syntax for the OCVS API. When deploying, translate it into appropriate defined tags or free-form tags in OCI and corresponding labels in VMware.

Tags on an SDDC do not automatically allocate exact costs to individual VMs. For internal chargeback, you need inventory data and allocation rules such as provisioned resources, actual consumption, or reserved capacity. Document clearly how shared platform costs are split.

## 7. Verifiable SDDC Deployment Workflow

### 7.1. Preparing Inputs

Before creating resources, finalize the following decisions:

1. **Location and capacity:** region, availability domain, shape, supported version, quotas, and host provisioning availability.
2. **Organization:** compartment, owner, and how SDDCs and clusters are divided.
3. **Networking:** CIDRs, DNS, NTP, management paths, on-premises connectivity, and dependent services.
4. **Storage:** datastores, protection policies, usable capacity, and target performance.
5. **Operations:** access permissions, secrets storage, monitoring, backups, and incident escalation contacts.
6. **Cost:** shape, commitment term, networking and storage costs, and decommissioning plan for test environments.

For configurations using Standard shapes, prepare the datastore cluster according to current SDDC creation workflow requirements. Do not assume volume creation procedures from older guides still apply. [Oracle: prerequisites before creating an SDDC](https://docs.oracle.com/en-us/iaas/Content/VMware/Tasks/ocvssettingupsddc.htm).

### 7.2. Execution Sequence and Evidence

| Phase | Activity | Required evidence |
| --- | --- | --- |
| OCI preparation | Configure compartments, policies, networking, addressing, and required storage | Resource inventory, CIDR overlap check results, and permissions |
| SDDC provisioning | Select initial cluster, shape, hosts, networking, and software | Completed work request, resources in appropriate lifecycle state |
| Management verification | Access vCenter, NSX, and hosts via management path | Successful login using role-assigned accounts |
| Platform verification | Inspect cluster health, datastores, networking, and appliances | No blocking platform errors |
| Workload preparation | Create resource pools, segments, policies, and sample VM | VM receives expected network, DNS, and configuration |
| Service testing | Test applications, monitoring, backup, and restore | Evidence of connectivity, alerting, and data recovery |

OCI resource availability is only one condition. Platform acceptance also requires tests on the VMware and application sides.

### 7.3. Observing with OCI CLI

The following PowerShell snippet only illustrates reading metadata. You need OCI CLI installed, a configured profile, and appropriate permissions; replace sample values with your environment's values:

~~~powershell
$ociRegion = "REGION_NAME"
$sddcId = "ocid1.sddc.REPLACE_WITH_REAL_OCID"

oci ocvs sddc get --sddc-id $sddcId --profile TRAINING --region $ociRegion --query 'data.{Name:"display-name",State:"lifecycle-state",Id:id}' --output table

oci ocvs cluster list --sddc-id $sddcId --all --profile TRAINING --region $ociRegion --query 'data[].{Name:"display-name",State:"lifecycle-state",Id:id}' --output table
~~~

The first command reads the selected SDDC; the second lists clusters belonging to that SDDC. The query filters select a few fields for inventory. This is information from the OCI API, not a list of all VMs in vCenter. See [get SDDC command](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/ocvs/sddc/get.html) and [list clusters command](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/ocvs/cluster/list.html).

If output is empty or access is denied, check the profile, region, OCID, and policies before concluding the resource is gone. Do not resolve read failures by defaulting to tenancy-wide admin permissions.

### 7.4. Automation with Clear Scope

Automation flows can be separated into three parts:

- **OCI infrastructure:** compartments, networking, SDDC, clusters, and storage resources supported by tooling.
- **VMware configuration:** inventory, resource pools, segments, policies, and VMs through appropriate tools.
- **Application configuration:** OS, agents, service configuration, and software releases.

Clearly define what acts as the source of truth and what the OCVS service creates and manages. If two pipelines modify the same route or NSX configuration, state can drift back and forth unexpectedly.

For infrastructure provisioning pipelines, save plans for review, protect state containing sensitive data, track work requests, and design for resuming after a failed stage. An API returning success upon accepting a request does not prove the asynchronous operation has completed.

## 8. Migrating Workloads with HCX and Organizing Cutover Waves

HCX supports migrating applications and workloads between source environments and OCVS. Specific capabilities depend on version, license type, and migration method. HCX also requires connectivity for operation, activation, and updates per solution requirements. [Oracle: HCX in OCVS](https://docs.oracle.com/en-us/iaas/Content/VMware/Concepts/ocvsoverview.htm).

### 8.1. Preparing by Application Dependency Group

Do not group VMs into waves solely by count. For example, an ERP wave might include order-processing servers, inventory integration servers, and the authentication service they depend on.

For each group, document:

| Information | Details required |
| --- | --- |
| Owner | Person who signs off pass or fail for the application |
| Dependencies | DNS, time, identity, file shares, queues, databases, and partners |
| Data | Primary write location, replication method, and consistency point |
| Outage window | Maximum downtime and cutover schedule |
| Testing | Representative transactions, performance criteria, and integration checks |
| Rollback | Trigger conditions, decision maker, and how newly generated data is handled |

### 8.2. Estimating Transfer Time

A minimum estimate can be calculated as:

~~~text
Transfer time
≈ Data volume to transfer / Effective bandwidth
~~~

For example, data to transfer is 2 TiB, nominal link speed is 500 Mbit/s, and effective throughput is assumed to be 65%:

~~~text
Effective bandwidth = 500 × 0.65 = 325 Mbit/s

Time ≈ (2 × 1024^4 × 8) / (325 × 10^6)
     ≈ 54,130 seconds
     ≈ 15 hours
~~~

This calculates initial data transfer, not application downtime. Source write rates, final delta sync, concurrent streams, and storage limits can extend the duration.

If data changes faster than effective replication speed, the system may fail to converge before cutover. Measure this in testing using representative workloads.

### 8.3. Executing a Controlled Cutover

A cutover wave should progress through these milestones:

1. Verify backups and source recoverability.
2. Confirm connectivity, target capacity, and operational permissions.
3. Replicate or transfer data using the selected method.
4. Quiesce or coordinate writes according to the consistency plan.
5. Complete the final sync and switch traffic flows.
6. Run acceptance transactions and monitor errors and performance.
7. Close the rollback window only after application owner approval.

If workloads require Layer 2 network extension during a transition phase, document its purpose and end date. A VM retaining its IP does not prove paths to databases, DNS, or external systems are optimal.

The rollback plan must address data written at the target. Once the application has written new data, powering the source VM back on from an older state can create split-brain data conflicts. Know which copy is authoritative and how to sync back if needed.

## 9. Availability, Backup, and Disaster Recovery

### 9.1. Distinguishing Protection Layers

| Mechanism | Failure addressed | What still needs to be solved |
| --- | --- | --- |
| vSphere HA | Host fails and VMs must restart on remaining hosts | Restart time and application recovery |
| Network redundancy | A network component or path fails | Convergence, return paths, and session state |
| Storage data protection policies | Loss of certain components per supported policy | Accidental deletion, logical corruption, or ransomware encryption |
| Backup | Restore to an earlier point in time | Restore duration, consistency, and data loss window |
| Cross-site DR | Outage exceeding primary site protection scope | Target capacity, replication, DNS, recovery order, and failback |

HA typically restarts VMs; this is different from continuous application availability without session loss. A resilient application also requires multiple instances, state management, and appropriate retry handling.

### 9.2. Fault Domains, Availability Domains, and Regions

In a single-AD design, distributing hosts across fault domains reduces the impact of certain localized hardware failures. It does not automatically provide coverage if an entire availability domain or region experiences an outage.

OCVS also offers Multi-AD capabilities under specific eligibility criteria; do not assume every shape, region, and tenancy uses them identically. Stretched designs must additionally evaluate latency, storage traffic, and Oracle-supported requirements. [Oracle: host distribution and Multi-AD capabilities](https://docs.oracle.com/en-us/iaas/Content/VMware/Concepts/ocvsoverview.htm).

For cross-region DR requirements, you need an independent design covering recovery site, data, connectivity, and capacity. Replicating VM files alone is insufficient if DNS, identity services, decryption keys, or database connectivity are missing.

### 9.3. RPO, RTO, and Recovery Evidence

- **RPO** describes acceptable data loss, typically expressed as a time interval.
- **RTO** describes the target time to restore service after an outage.

For example, a 15-minute RPO and 2-hour RTO are business objectives. To prove compliance, record the latest recoverable data timestamp and the time when application transactions succeed again.

Backups must cover both application data and platform rebuild information: vCenter/NSX configuration using supported methods, inventory, network policies, secrets, and recovery runbooks. VM snapshots depend on the VM's disk chain, so do not rely on snapshots alone as a long-term protection strategy.

When testing restores, pick representative data or VMs and an appropriate isolated environment. Verify integrity, access permissions, and business transactions, rather than merely checking that the VM boots.

### 9.4. Single-Host SDDC Has a Separate Scope

A single-host SDDC is intended for short-term testing or development; Oracle does not support production workloads on this configuration. It lacks the host fault tolerance of a multi-host cluster and cannot be upgraded directly into a multi-cluster SDDC. When production is needed, plan to migrate workloads to a suitable environment. [Oracle: single-host SDDC limitations](https://docs.oracle.com/en-us/iaas/Content/VMware/Tasks/ocvsmanagingsddc.htm).

Do not use "the application runs on one host" as evidence of production availability or fault-tolerant capacity.

## 10. Lifecycle Monitoring and Maintenance

### 10.1. Multi-Layer Observability

An operational metrics suite should report both platform health and service quality:

| Layer | Signals to monitor | Alert-driven action |
| --- | --- | --- |
| OCI | Failed work requests, resource state, network connectivity | Identify affected OCI operation or component |
| Hosts and clusters | CPU contention, memory pressure, lost host, remaining capacity | Assess risk of breaching redundancy headroom |
| Storage | Free capacity, latency, path errors, protection health | Prevent out-of-space conditions, identify affected VMs |
| NSX and connectivity | Edge status, tunnels, drops, route changes | Inspect the specific failing network segment |
| VMs and applications | Service errors, response times, transaction success rate | Measure actual business impact |
| Backup | Failed jobs, backup age, latest restore test result | Ensure data remains recoverable |

Do not set thresholds based solely on average utilization percentages. For a five-host cluster, know the load after losing one host and expected growth before the next expansion.

If deploying the VMware Solution Management Appliance, you can configure ESXi metrics to be sent to OCI Monitoring through the vSphere integration. You must configure the appliance, connectivity, and metric selection; do not assume all data is collected automatically. [Oracle: configuring metric export](https://docs.oracle.com/en-us/iaas/Content/VMware/Tasks/ocvs-management-app-metrics.htm).

Oracle Log Analytics provides a solution to ingest and analyze VMware events, logs, and operational signals when configured. It is a centralized logging option that requires estimating both ingestion volume and retention duration. [Oracle: VMware Monitoring Solution](https://docs.oracle.com/en-us/iaas/log-analytics/doc/vmware-monitoring-solution.html).

OCI Audit and VMware logs serve different scopes. To investigate who changed a VM configuration or NSX policy, you need data from the corresponding VMware tool, not just OCI API history.

### 10.2. Sequential Host Maintenance

A typical maintenance procedure:

1. Verify cluster health, backups, and ability to continue serving without that host.
2. Check compatibility across ESXi, vCenter, NSX, storage, HCX, and add-on tools.
3. Ensure sufficient resources to migrate or stop workloads as planned.
4. Place the host into maintenance mode using a supported workflow; handle vSAN data appropriately for the situation.
5. Apply changes and confirm the host and related components operate properly.
6. Wait for required resynchronization to finish, then verify applications.
7. Proceed to the next host once health criteria are met.

If using OCVS automation tools to add, replace, or upgrade hosts, still check which steps the tool performed. Do not assume every OCI-side operation has completed all steps inside VMware.

Do not directly delete underlying Compute or storage resources of an SDDC to replace OCVS-supported lifecycle operations. Provisioning new hosts also requires checking actual capacity, not just quota limits.

## 11. Controlling SDDC Costs

### 11.1. Calculating Platform-Level Costs

Preliminary cost model:

~~~text
Total cost
= hosts and associated usage entitlements per contract model
+ additional storage
+ connectivity and data transfer
+ backup and recovery site
+ monitoring, logging, and data retention
+ add-on tools
+ operational effort
~~~

Stopping a VM does not stop billing for provisioned bare metal hosts. Therefore, distinguish savings from VM optimization from actual savings achieved by changing host count, shape, or storage model.

Billing periods may be tied to usage commitments. Deleting a host before a commitment ends does not automatically terminate payment obligations for that term. Before creating or modifying hosts, read the commitment term conditions applicable to that configuration. [Oracle: OCVS billing options](https://docs.oracle.com/en-us/iaas/Content/VMware/Concepts/billing-options.htm).

Do not treat a minimal configuration as a complete production estimate. For example, ERP also requires fault-tolerant headroom, growth buffer, backups, and recovery capability.

### 11.2. Practical Measures

- Measure load before migration and after each wave to calibrate sizing.
- Consolidate workloads according to resource requirements and permitted policies while preserving headroom.
- Compare adding hosts versus adding storage when storage is the bottleneck.
- Track resources used for migration, temporary backups, and testing to decommission them on schedule.
- Assign an owner, purpose, and review date to each environment.
- Set up budgets and alerts for responsible teams; alerts do not replace provisioning controls.
- Recalculate capacity after removing resources to avoid losing required protection levels.

Verify licensing entitlements for VMware software, add-on tools, and Oracle software running in the environment under applicable agreements. In particular, connecting to a database service versus running a database inside a VM are different operational and licensing models. Do not infer entitlement solely from a cloud service name.

## 12. Design Planning and Acceptance Lab

This lab uses the ERP example above. You can complete the design portion without provisioning an SDDC. Hands-on operations are performed in a training environment or an environment authorized by your organization.

### Step 1: Complete the Design Document

Specify:

- Boundaries for compartments, SDDCs, management cluster, and workload cluster.
- Account groups for OCI, vCenter, and NSX along with task scopes.
- VCN address space, space reserved for cluster networks, and application segments.
- Management flows, on-premises flows, and database service flows.
- CPU, RAM, storage, headroom, and growth assumptions.
- Backup plan, RPO/RTO, and how results are proven.

With the RAM assumptions in this lesson, recognize that four workload hosts fail the single-host loss check, while five hosts pass the preliminary RAM check. If application demand or shape changes, recalculate instead of keeping host counts out of habit.

### Step 2: Inventory the Existing Environment

Use the Console or the two CLI commands in the deployment section to verify the exact SDDC and clusters. Then use vCenter to inspect hosts, datastores, networks, and sample VMs.

The expected outcome is explaining whether each observed object belongs to the OCI or VMware scope, who manages it, and which resources it depends on.

### Step 3: Verify Permitted and Blocked Flows

On a sample VM and authorized test endpoints:

1. Verify DNS resolution to the target service.
2. Test connectivity to the declared service port.
3. Run a simple transaction to confirm the application path.
4. Test a flow designed to be blocked and record appropriate evidence.
5. Check logs or diagnostic tools to identify the policy enforcement layer.

If the database flow fails, trace in order: target address, VM gateway, NSX policy, Edge, OCI/DRG routes, database-side policy, and target service. Change only one identified cause per test iteration.

### Step 4: Verify Observability and Recovery

Confirm a controlled test event is logged in the right place and reaches an alert recipient. Perform a restore of a representative object using the environment's procedure, then verify data and application functionality.

Host failure or link disconnection tests should only be run within windows and scopes authorized by the organization. For a design exercise, you can simulate using capacity numbers and document the recovery sequence.

### Step 5: Record Acceptance Results

An acceptance record should include:

| Evidence | Criteria |
| --- | --- |
| Diagrams and inventory | Match actual resources or stated assumptions |
| Permission matrix | Users can perform only assigned tasks |
| Route tables and network flows | Required flows work; prohibited flows are blocked |
| Sizing | Includes headroom and explicitly states calculation limits |
| Monitoring | Data, alerts, and designated responders exist |
| Restore | Data is usable, with measured recovery time |
| Cost | Has an owner, cost estimate model, and verified commitment terms |

If temporary resources were created, end the lab by reviewing them through a supported lifecycle process. Before deleting, confirm data to retain, network/storage dependencies, and commitment terms; afterward verify remaining resources and ongoing charges.

## 13. Design Mistakes to Watch For

| Misconception | Consequence | How to address |
| --- | --- | --- |
| Granting OCI permissions assumes vCenter permissions are granted | Users cannot perform tasks, or are over-privileged to fix errors | Design and test permissions separately for each scope |
| Creating a workload cluster makes it completely independent | Underestimates shared management dependencies | Document shared components and blast radius |
| Using NSGs in place of all VM-to-VM policies | Certain internal flows are not controlled as intended | Design NSX policies and test exact flows |
| Checking only the outbound route | Connectivity fails or behaves unstably | Trace return paths for overlay CIDRs |
| Using raw capacity to finalize application space | Insufficient room for data protection and rebuilds | Account for policies, slack space, and failure scenarios |
| Sizing only for full host availability | Insufficient resources during maintenance or failures | Calculate degraded-host states and check admission control |
| Treating snapshots, HA, and backups as equivalent | Inability to recover data when needed | Choose mechanisms by failure type and test restores |
| Assuming powering off VMs or deleting hosts stops all costs | Inaccurate platform and commitment cost estimates | Check billed resources and commitment term conditions |

An implementable OCVS design must clearly show where workloads run, how data traverses network layers, who has authority to change the system, and evidence of recoverability. Those decisions must be maintained when adding clusters, scaling hosts, changing storage, or migrating additional applications.
