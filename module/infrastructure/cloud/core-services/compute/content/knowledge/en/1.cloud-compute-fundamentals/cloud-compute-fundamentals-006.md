# Regions, Availability Zones, and Failure Domains of Compute Resources

When deploying compute resources in the cloud, choosing a virtual machine type, vCPU count, or memory size solves only part of the problem. Placing resources in **regions** and **availability zones (AZs)** determines user latency, the ability to keep serving during infrastructure failures, how data is protected, and data transfer costs across locations.

A system with multiple virtual machines can still suffer a complete outage if every machine sits in the same failure domain. Conversely, spreading resources across multiple AZs without redesigning data, networking, and dependent services still does not achieve end-to-end availability. Therefore, you must understand the scope of each resource and determine which failures your architecture must withstand.

This lesson belongs to the **Cloud Compute Fundamentals** chapter of the **CLOUD_CORE_SERVICES_COMPUTE** module. The module focuses on cloud compute models—from virtual machines and containers to serverless—how to choose CPU, memory, networking, and security configurations, and how to deploy applications, scale loads, ensure availability, and optimize operating costs. Within that scope, regions, AZs, and failure domains form the foundation for deciding where compute resources are placed and how redundancy should be designed.

## 1. What Is a Failure Domain?

A **failure domain** is a segment of a system within which a fault can impact the resources residing inside it. If a single fault causes multiple components to stop working together, those components may be sharing a failure domain.

Several common failure domains include:

- **Physical server or host:** Hardware, power, memory, storage controller, or hypervisor failures can impact the virtual machines running on that host.
- **Rack or infrastructure cluster:** Power, network, or shared equipment failures can affect multiple hosts.
- **Availability zone:** An outage at an independent infrastructure site can render resources in that AZ unreachable.
- **Region:** A broad outage can impact multiple AZs and services deployed within the region.
- **Shared services or shared configurations:** Errors in DNS, identity and access management, secret distribution systems, network configs, or bad change rollouts can affect multiple regions simultaneously.

Failure domains are not strictly geographic boundaries. A configuration error can cross AZ or region boundaries. For example, if servers across multiple AZs share the same faulty firewall rule, distributing servers does not prevent the outage. Similarly, if an application runs in two regions but relies on a single authentication service without failover, that authentication service can still become a single point of failure.

**Blast radius** is the actual impact scope of an incident. Good design seeks to limit blast radius: a host failure does not bring down the entire application; an AZ disconnect does not eliminate all serving capacity; a regional outage does not cause unrecoverable business data loss.

## 2. Regions and Availability Zones

### 2.1. Region

A **region** is a geographic area where a cloud provider builds and operates infrastructure to deliver services. A region typically comprises multiple AZs interconnected by networking and maintains its own catalog of services, machine types, capacity, and quotas.

Regions can be hundreds or thousands of kilometers apart. This distance drives differences in network latency, connectivity options, data residency compliance, and data transfer costs.

When selecting a region, consider:

- Where users and calling systems are located, and what latency is acceptable.
- Whether data must be stored or processed in a specific country, territory, or jurisdiction.
- Whether required services, VM types, GPUs, operating systems, and features are available in that region.
- Whether resource quotas, spare capacity, and scaling headroom meet demand.
- Whether connectivity to on-premises systems, partners, or other cloud services is suitable.
- Pricing for compute, storage, data transfer, and related charges.

Region names often correspond to a geographic place or provider-defined code. However, a region name alone is insufficient to infer exact legal scope, national boundaries, or data-processing location guarantees. For compliance requirements, verify documentation and terms for each specific service.

### 2.2. Availability Zone

An **Availability Zone (AZ)** is an infrastructure location designed to maintain a degree of independence from other AZs in the same region. Providers generally equip AZs with separate power, cooling, and network connectivity to reduce the likelihood that a localized failure impacts all AZs simultaneously.

An AZ may consist of one or more data centers. Therefore, do not assume one AZ always equates to exactly one building or one data center.

AZs within the same region typically feature high-speed, low-latency network links to support distributed deployments. Even so, cross-AZ data transfer can still incur charges and latency; check your provider's pricing policies.

Naming and representation of AZs differ across platforms:

| Platform | Common Organization |
|---|---|
| AWS | A Region contains multiple Availability Zones; each AZ is one or more discrete infrastructure locations. |
| Microsoft Azure | A Region may support Availability Zones; zones are physically separate locations within the region. |
| Google Cloud | A Region contains multiple zones; a zone is a deployment scope for resources within the region. |

These concepts share similar intent, though they do not always carry identical semantics, service catalogs, or SLA commitments. When translating architectures across providers, re-verify how each specific service implements availability.

### 2.3. Distinguishing Regional, Zonal, and Global Scope

You can visualize the deployment hierarchy as follows:

~~~mermaid
flowchart TB
    G["Global scope<br/>Global services or global control planes"]
    R1["Region A"]
    R2["Region B"]
    Z11["AZ A1"]
    Z12["AZ A2"]
    Z13["AZ A3"]
    Z21["AZ B1"]
    Z22["AZ B2"]
    G --> R1
    G --> R2
    R1 --> Z11
    R1 --> Z12
    R1 --> Z13
    R2 --> Z21
    R2 --> Z22
~~~

- **Global scope:** Resources or control planes can be managed across multiple regions. A service labeled global may still have limits, dependencies, or data components anchored in a specific scope.
- **Regional scope:** Resources are created within one region and can generally serve across multiple AZs in that region.
- **AZ (zonal) scope:** Resources are tied to a specific AZ. If that AZ fails, the resources may be unusable from other AZs.

Resource scope is a property of each individual service. You cannot assume all networking resources are regional or all storage resources are zonal based solely on naming. Check service documentation, especially creation scope, attachment scope, and recovery behavior during AZ or regional outages.

## 3. Scope of Commonly Used Cloud Resources

A compute application typically combines multiple resource types. Each type has its own scope and failure behavior.

| Resource | Typical Scope | Things to Verify |
|---|---|---|
| Virtual machine (VM/instance) | Typically placed in a specific AZ within a region | Whether it can be recreated in another AZ; whether images, quotas, and machine types exist there. |
| VM image | Typically managed or replicated regionally | Whether the image is replicated to a backup region and compatible with machine types there. |
| Block volume/disk | May be zonal or offer regional replication mechanisms | Whether it can attach to a VM in another AZ; whether snapshots, replication, or restores are needed to move zones. |
| Object storage | Typically selected by region or storage location tier | Across what scope data is replicated; whether cross-region copies exist. |
| VPC/VNet and subnets | Scope varies by provider; virtual networks may be regional while subnets are AZ-bound or regional | Subnet scope, route tables, gateways, firewalls, and cross-zone connectivity. |
| Load balancer | May be zonal, regional, or global | Health checks, cross-AZ load distribution, ability to keep receiving traffic when one AZ fails. |
| IP addresses and NAT gateways | May be bound to one AZ or one region | Traffic path when an AZ fails; ability to reassign IPs or provision backup gateways. |
| Kubernetes cluster/node pool | Control plane and node pools may have different scopes | Which AZs host nodes; how the control plane, persistent volumes, and scheduler handle failures. |
| Serverless function | Typically deployed regionally, with underlying infrastructure managed by the provider | Redundancy guarantees committed by the service; concurrency limits, quotas, and scope of dependent services. |
| Managed database | May support single-AZ, multi-AZ, or cross-region replication | Failover mechanisms, data sync, RPO/RTO, and control over replica locations. |

This table illustrates common patterns, not universal rules across every provider. For instance, one disk type may attach only to VMs in the same AZ, while another supports replication or broader attachment scope. Similar service names do not guarantee identical capabilities.

### 3.1. Virtual Machines and Images

Virtual machines are typically created in one region and one AZ. When a host or AZ fails, the VM may go down. To recover in another AZ, the system needs all ingredients to recreate the machine: image, startup configuration, networking, access permissions, data, and quota.

Images can be replicated across AZs or regions depending on the platform. Manage images by version and automate VM creation so recovery does not depend on manual steps or configuration trapped on an old machine.

### 3.2. Containers and Kubernetes

In container systems, a cluster can span multiple AZs. Node pools can reside in one or multiple zones; the scheduler distributes pods based on available nodes, topology labels, and configured constraints.

To survive an AZ failure, you need:

- Sufficient nodes and CPU/memory capacity in remaining AZs.
- Multiple replicas for workloads requiring availability.
- Topology spread constraints or pod anti-affinity to avoid placing all replicas on the same node or in the same AZ.
- Assurance that load balancers and network paths continue routing traffic to healthy surviving pods.
- Verification of whether persistent volumes are bound to a single zone.

The Deployment example below illustrates distributing pods by zone label. This is a Kubernetes configuration; actual effectiveness also depends on node counts, topology labels, and cluster scheduling policies.

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      topologySpreadConstraints:
        - maxSkew: 1
          topologyKey: topology.kubernetes.io/zone
          whenUnsatisfiable: DoNotSchedule
          labelSelector:
            matchLabels:
              app: api
      containers:
        - name: api
          image: registry.example.com/api:1.0.0
          ports:
            - containerPort: 8080
~~~

With the `DoNotSchedule` constraint, the scheduler may refuse to schedule pods if it cannot satisfy the required distribution skew. Consider this behavior when one zone loses nodes or lacks capacity. Operations teams must choose the right trade-off between strict spreading and continuing to schedule when a zone becomes unavailable.

### 3.3. Serverless and Managed Services

Serverless spares users from managing hosts or selecting individual physical servers. However, provider-managed infrastructure does not mean every dependency automatically has multi-AZ or multi-region redundancy.

A function deployed in a region can still depend on a database, queue, object storage, secrets manager, or API available only within a narrower scope. Read the availability commitments of each service and architect critical dependencies accordingly.

## 4. Deployment Patterns by Failure Domain

### 4.1. Single AZ

All primary compute instances reside in a single AZ. This pattern is simple, easy to operate, and can fit development, testing, retryable tasks, or interruption-tolerant workloads.

The drawback is that an AZ outage can bring down the entire workload. Running multiple VMs in the same AZ reduces dependence on one VM or host, but does not protect against a failure affecting the entire AZ.

### 4.2. Multi-AZ Within One Region

The application is deployed across at least two AZs within one region. If one AZ fails, replicas in the remaining AZs can continue serving traffic.

~~~mermaid
flowchart TB
    U["User"] --> LB["Regional load balancer"]
    LB --> A1
    LB --> A2
    subgraph R["Region"]
      subgraph Z1["AZ 1"]
        A1["API replica 1"]
        W1["Worker replica 1"]
      end
      subgraph Z2["AZ 2"]
        A2["API replica 2"]
        W2["Worker replica 2"]
      end
      DB["Database with multi-AZ redundancy"]
      A1 --> DB
      A2 --> DB
    end
~~~

For this pattern to work properly:

1. **Distribute compute:** Place replicas in distinct AZs. If all replicas remain concentrated in one AZ, the system is not AZ-fault-tolerant.
2. **Maintain spare capacity:** Surviving AZs must have sufficient CPU, memory, nodes, quotas, and bandwidth to absorb traffic when one AZ goes down.
3. **Route traffic properly:** The load balancer must health-check backends and stop sending traffic to failed components.
4. **Protect data:** Databases, caches, queues, and volumes must have matching redundancy. A multi-AZ stateless application will still go down if its database has only a single copy sitting in the failed AZ.
5. **Handle sessions and state:** Do not store sessions or critical files solely on one replica's local disk. Use shared stores or services with matching availability scope.
6. **Test recovery:** Simulate losing one AZ, measuring detection time, traffic shifting, and stabilization.

Two common deployment modes:

- **Active-active:** Multiple AZs handle normal traffic simultaneously. Ensure data and state can be shared or synchronized safely.
- **Active-standby:** One AZ or standby resource group waits to take over when the primary component fails. Define failure detection, failover triggers, and split-brain prevention so both sides do not unintentionally write conflicting data.

### 4.3. Multi-Region

Multi-region deploys applications or data replicas across multiple regions. This pattern can mitigate broad regional outages, serve users across geographically dispersed areas, or satisfy disaster recovery requirements.

~~~mermaid
flowchart TB
    U["User"] --> G["Global DNS / traffic manager"]
    G --> R1
    G --> R2
    subgraph R1["Primary region"]
      A1["Application"]
      D1["Database primary"]
      A1 --> D1
    end
    subgraph R2["Backup region"]
      A2["Standby or active application"]
      D2["Database replica"]
      A2 --> D2
    end
    D1 -. "Replication" .-> D2
~~~

Multi-region carries higher cost and complexity than multi-AZ. Teams must solve cross-region data synchronization, traffic routing, secrets and configuration distribution, quotas in backup regions, and write-conflict risks if two regions write simultaneously.

Do not assume a multi-region system always runs active-active. You can choose:

- **Active-passive:** The primary region handles load, while the backup region is prepared to take over.
- **Active-active:** Multiple regions serve users simultaneously; data requires appropriate partitioning, synchronization, or conflict resolution mechanisms.

Distinguish clearly:

- **High availability (HA):** Maintaining or rapidly restoring service during common failures, such as host or AZ faults.
- **Disaster recovery (DR):** Restoring service after major catastrophes such as losing an entire region, data corruption, or widespread outages.

Multi-AZ typically underpins HA within a region. Multi-region is typically considered for DR or global serving requirements. A system may need both, but the decision must stem from business objectives and acceptable disruption levels.

## 5. RPO, RTO, and Availability

When designing redundancy, translate business requirements into measurable targets.

- **RTO (Recovery Time Objective):** Maximum acceptable time to restore service after an outage.
- **RPO (Recovery Point Objective):** Maximum acceptable amount of data loss, typically expressed as a time interval.

For example, a system with a 30-minute RTO and a 5-minute RPO must be capable of restoring service within 30 minutes and losing at most roughly 5 minutes of data per its targets. These are illustrative design targets; actual outcomes depend on replication mechanisms, backups, failover procedures, and drill results.

Synchronous replication generally reduces the risk of losing acknowledged writes, but can increase latency and tighten connectivity dependencies. Asynchronous replication generally fits longer distances better, but introduces replication lag, resulting in RPO greater than zero. Backups support data recovery, but do not automatically replace HA mechanisms since restoration takes time.

A provider's SLA is a commitment under specific service conditions. An SLA does not guarantee that a customer's architecture meets desired RTO or RPO targets. Read eligibility conditions, measurement scope, exclusions, and required service configurations.

## 6. How to Choose Regions and AZs

Base location choices on workload requirements and the services the workload depends on.

### Step 1: Identify Users and Latency

Place compute close to users or calling systems to reduce latency. For applications serving multiple geographies, you can use multiple regions or global distribution layers. However, measure end-to-end latency rather than geographic distance alone: DNS, networking, databases, and dependent APIs all affect response times.

### Step 2: Identify Data and Compliance Requirements

Clarify where data is allowed to be stored, processed, and replicated. Check locations of backups, logs, snapshots, encryption keys, and data generated by managed services. Picking a region for compute does not automatically ensure all related data remains within that same boundary.

### Step 3: Set Availability and Recovery Targets

Define which failures the workload must survive:

- Only needs recovery when a single VM or host fails.
- Needs to keep serving when an AZ fails.
- Needs recovery if an entire region becomes unavailable.
- Needs continuous operation across multiple geographic regions.

Higher targets typically demand more replicas, greater spare capacity, more frequent testing, and higher operational costs.

### Step 4: Verify Services, Machine Types, and Quotas

Not every region offers every instance type, GPU, managed service, or feature. Check quotas for VMs, vCPUs, IP addresses, load balancers, disks, nodes, and dependent services. For critical workloads, verify that backup regions or AZs can provision sufficient resources during failover—not just under normal conditions.

### Step 5: Evaluate Data and Dependencies

Inventory databases, caches, queues, object storage, DNS, IAM, KMS, secrets managers, registries, monitoring, and external APIs. Identify the failure domain of each component. A dependency with a narrower scope than the application can become a single point of failure.

### Step 6: Calculate Total Cost

Costs go beyond VM pricing. Account for:

- Always-on or pre-provisioned standby resources.
- Multi-copy storage and snapshots.
- Data transfer across AZs or regions.
- Load balancers, gateways, NAT, and cross-region links.
- Database replication and backups.
- Logging, monitoring, and DR testing.
- Engineering effort for operations, automation, and incident response.

Multi-AZ typically increases costs due to extra capacity and potential cross-AZ data transfer fees. Multi-region typically costs even more because compute, data, and networking must be duplicated across locations. In return, these investments can reduce losses caused by service outages. Compare against the business impact of downtime rather than comparing compute bills in isolation.

### Selection Guide Table

| Requirement | Commonly Suitable Model | Things to Verify |
|---|---|---|
| Development, testing, retryable tasks | Single AZ | Can recreate quickly; test data is not the sole copy. |
| API or service needing to keep serving if an AZ fails | Multi-AZ within one region | Replicas, load balancer, data, quotas, and failover capacity. |
| System needing recovery if the primary region fails | Multi-AZ combined with cross-region DR | RPO/RTO, data replicas, DNS/traffic failover, and drills. |
| Application serving global users | Multi-region or globally distributed architecture | Latency, data sync, routing, compliance, and cost. |
| Retryable batch jobs or workers | Single or multi-AZ depending on completion deadlines | Retry logic, checkpoints, queues, and processing duration limits. |

## 7. Design Examples

### Example A: Stateless API Needing AZ Fault Tolerance

A customer-facing API can deploy three replicas across three AZs in the same region. A regional load balancer routes traffic only to healthy replicas. Auto scaling can add replicas in surviving AZs.

The database is configured with multi-AZ redundancy. Sessions and user files are stored in services with matching availability scope. Monitoring tracks errors per AZ so operations teams know when a zone stops accepting traffic.

During design, test losing an AZ and verify:

- Whether the two remaining AZs have enough capacity to handle peak load.
- Whether replicas spread properly and self-heal.
- Whether the load balancer removes failed backends within an acceptable time.
- Whether the database continues reading/writing without losing data beyond the configured RPO.
- Whether components like NAT, DNS, secrets manager, and queues keep operating.

### Example B: VM with a Disk Bound to One AZ

A VM runs an application with data stored on a zonal disk. If the AZ hosting the VM and disk fails, spinning up a new VM in another AZ may not allow directly attaching the old disk. Recovery may require snapshots, disk replicas, or replication mechanisms supported by the storage service.

The lesson here is to design both compute and data together. Having a VM image in another AZ without an appropriate data copy still cannot restore the application in a valid state.

### Example C: DR to a Second Region

A transaction system designates region A as primary and prepares region B for recovery. Data replicates asynchronously to B. When region A experiences an outage, the DR procedure verifies replica status, shifts workloads to B, and updates user traffic routing.

Before declaring the system DR-ready, the team must rehearse the entire sequence: provisioning compute, opening network links, fetching secrets, validating data, shifting traffic, running functional checks, and recording recovery duration. Also define the failback procedure to return to the primary region after recovery without simultaneous split-brain writes on both sides.

## 8. Common Mistakes

**Running multiple VMs in the same AZ and calling it multi-AZ.** Multiple VMs reduce single-machine failure risk, yet still share the AZ's failure domain. Verify the actual placement of every instance.

**Spreading only the application tier.** The app may span multiple AZs while the database, queue, disk, NAT, or authentication service exists at only one deployment point. When that point fails, the whole system is still impacted.

**Assuming autoscaling automatically handles AZ outages.** Autoscaling creates new resources only if quotas, capacity, configurations, and startup times permit. If all node pools live solely in the failed AZ, autoscaling cannot spin up capacity in another AZ.

**Equating multi-AZ with multi-region.** Multiple AZs in one region help against localized failures. They do not protect against outages affecting the entire region.

**Treating same-region backups as sufficient for every scenario.** Same-region backups help for data corruption or resource errors, but may fall short if the entire region becomes unreachable. Scope backups to your recovery scenarios.

**Reading SLAs without testing failover.** Service commitments do not replace testing your application's architecture, runbooks, and data. Only drills prove whether procedures meet RTO/RPO.

**Ignoring cross-zone and cross-region costs.** Data replication, cross-AZ service calls, and cross-region routing can inflate bills. Monitor traffic and design appropriate data paths.

**Letting shared configurations become a shared failure point.** A bad change in IAM, DNS, firewalls, secrets, or deployment pipelines can impact multiple AZs or regions simultaneously. Enforce change management, access control, and rollback capability.

## 9. Pre-Deployment Checklist

- [ ] Selected region based on users, latency, data requirements, service availability, and cost.
- [ ] Defined whether the workload must survive host, AZ, or full-region failures.
- [ ] Documented scopes of VMs, disks, networks, load balancers, and managed services.
- [ ] Distributed replicas across appropriate AZs; verified topology spread and anti-affinity.
- [ ] Verified quotas and capacity in backup AZs or regions.
- [ ] Checked databases, caches, queues, object storage, and data protection mechanisms.
- [ ] Defined relevant RTO, RPO, SLA, and SLO targets.
- [ ] Automated deployment, configuration, recovery, and traffic shifting.
- [ ] Monitored health and traffic per region/AZ.
- [ ] Rehearsed AZ failure and DR procedures; recorded actual timings and outcomes.
- [ ] Estimated costs for compute, storage, data transfer, backups, and operations.

## 10. Key Takeaways

- A **region** is a geographic area delivering cloud services; region selection impacts latency, data residency, service availability, and cost.
- An **availability zone** is a relatively independent infrastructure domain within a region; multi-AZ deployment reduces the blast radius of localized failures.
- **Resource scope** can be zonal, regional, or global and must be verified per individual service.
- **End-to-end availability** depends on the entire chain of compute, networking, storage, identity, and dependent services.
- **Multi-AZ** typically serves HA within a region; **multi-region** typically serves DR or global distribution needs.
- An architecture is only resilient once RTO/RPO are defined, failover capacity is verified, and it has been tested under realistic failure scenarios.

## Glossary

| Term | Meaning |
|---|---|
| Region | Geographic area where a cloud provider offers a suite of services and infrastructure. |
| Availability zone (AZ) | Relatively independent infrastructure location within a region used to distribute resources. |
| Zone | Zone-level deployment scope; exact naming and semantics vary by provider. |
| Failure domain | Scope within which a single fault can impact co-located components. |
| Blast radius | Actual impact scope of an incident on the system. |
| Zonal resource | Resource bound to a specific AZ or zone. |
| Regional resource | Resource managed within the scope of a single region. |
| Multi-AZ | Architecture distributing resources across multiple AZs within the same region. |
| Multi-region | Architecture spanning multiple regions. |
| HA | High availability; ability to maintain or rapidly restore service upon failure. |
| DR | Disaster recovery; ability to recover a system after a major catastrophe. |
| RTO | Maximum target duration to restore service. |
| RPO | Maximum acceptable data loss, typically measured in time. |
