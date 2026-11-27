# Zonal Clusters, Regional Clusters, and Availability Design

An application can run three Pods on Kubernetes and still go down when a single Google Cloud zone experiences an outage: the scheduler may have placed all three Pods on nodes in that same zone. Conversely, a cluster with nodes spread across multiple zones can still fail to create, update, or schedule new Pods if **the control plane lives only in the zone that just failed**. That is why availability design in Google Kubernetes Engine (**GKE**) must evaluate **two separate concerns**: the location of the **control plane** and the location of **worker nodes/workloads**.

Within the **GKE Fundamentals** chapter of the **CLOUD_PROVIDERS_GCP** module, this lesson examines the differences between **zonal clusters** and **regional clusters**, how nodes and Pods are distributed across zones, the impact of a zone outage, data availability, and network access paths. Those decisions connect directly to projects, IAM, VPC, Compute Engine, Cloud Storage, databases, release automation, reliability monitoring, and cost optimization on Google Cloud.

**After this lesson, you will be able to:**

1. Explain the control plane and node pool structure of GKE Standard zonal, GKE Standard regional, and GKE Autopilot clusters.
2. Distinguish a **zonal cluster** with a **single-zone node pool** from a **regional cluster** with a **multi-zone node pool**.
3. Evaluate failure scenarios across the control plane, nodes, zones, regions, load balancers, networking, and storage.
4. Choose configurations that meet service **SLO, RTO, and RPO** targets rather than relying solely on the "regional" label.
5. Use Deployment replicas, topology spread constraints, PodDisruptionBudgets, probes, and autoscaling to improve availability for eligible applications.
6. Create and inspect a Standard regional cluster in a lab environment, contrast it with zonal creation, and clean up resources safely.
7. Account for quotas, per-zone node costs, inter-zone traffic, security mechanisms, and data recovery capabilities.

## 1. Two Critical Layers: Control Plane and Worker Nodes

A GKE cluster consists of the following logical components:

- **Control plane:** runs the Kubernetes API, state store, and control components needed to monitor the cluster, make scheduling decisions, and reconcile desired state. GKE manages the control plane infrastructure.
- **Worker nodes:** Compute Engine VMs or GKE-managed node infrastructure that run containers inside Pods and connect networking/storage as configured.
- **Node pool:** a group of nodes sharing related configuration (in Standard), such as machine type, image, pool size, zone locations, and autoscaling.
- **Kubernetes workloads:** Deployments, StatefulSets, DaemonSets, Jobs, and other objects that create Pods on eligible nodes.
- **Services and Ingress/Gateway:** organize service discovery and distribute traffic to ready endpoints; depending on type, GKE can integrate with Google Cloud load balancing.

~~~mermaid
flowchart TB
    USERS["Users"] --> LB["Load balancer / Gateway"]
    subgraph CP["GKE-managed control plane"]
      API["Kubernetes API and controllers"]
    end
    subgraph NODES["Worker nodes in node pools"]
      N1["Node zone A<br/>Pod API replica 1"]
      N2["Node zone B<br/>Pod API replica 2"]
      N3["Node zone C<br/>Pod API replica 3"]
    end
    API -. "Desired state / scheduling" .-> N1
    API -.-> N2
    API -.-> N3
    LB --> N1
    LB --> N2
    LB --> N3
~~~

The control plane is not a mandatory HTTP data-path hop between users and a running Pod. When the Kubernetes API is temporarily unavailable, **existing Pods on surviving nodes can continue serving traffic**, though actions such as creating/editing resources, scheduling, handling new nodes, and coordinating recovery may be affected. Whether the application continues serving still depends on node health, load balancers, application configuration, and data dependencies.

### 1.1. Region and Zone Scope in Google Cloud

- **Region**: a geographical area containing one or more zones; for example, `asia-southeast1`.
- **Zone**: an isolated failure domain within a region, such as `asia-southeast1-a`, `asia-southeast1-b`, and `asia-southeast1-c`.
- **VPC network**: a global resource; VPC subnets, however, are **regional**, allowing VMs/nodes across zones in the same region to share a subnet as configured.
- **GKE cluster location**: when creating Standard zonal, choose one **zone** for the control plane; when creating regional, choose one **region** for the control plane.

**A global VPC does not automatically make Pods, nodes, or data multi-zone.** A cluster can still place all nodes in a single zone. Accessing resources over private IP within the same VPC also does not create a zone-failure recovery process by itself.

## 2. Zonal Clusters, Regional Clusters, and Node Locations

Two design axes should always be documented in your architecture:

1. **Where is the control plane?** Single zone, or multiple replicas across zones in a region?
2. **Where do node pools run?** Single zone, or multiple zones in the same region?

With **GKE Standard**, these two axes can be combined in several ways. With a **GKE Autopilot cluster**, the control plane is always **regional** and GKE manages many node placement and resource choices based on workload configuration.

### 2.1. GKE Standard Zonal Cluster

A **zonal cluster** has **a single control plane in one zone**. By default when creating a zonal cluster, nodes also reside in one zone, though operators **can configure node locations across multiple zones in the same region**. That second configuration is often called a *multi-zonal zonal cluster*.

~~~mermaid
flowchart TB
    subgraph REGION["Region"]
      subgraph ZA["Zone A"]
        CPA["Single control plane"]
        NA["Node/Pod A"]
      end
      subgraph ZB["Zone B"]
        NB["Node/Pod B"]
      end
      subgraph ZC["Zone C"]
        NC["Node/Pod C"]
      end
    end
    CPA -. "Manages nodes when control plane is available" .-> NA
    CPA -.-> NB
    CPA -.-> NC
~~~

If **zone A** (hosting the control plane) becomes unavailable:

- The Kubernetes API/control plane may become unreachable; cluster changes, scheduling, and certain orchestration loops cannot operate normally until the control plane recovers.
- Nodes and Pods already running in zones B/C **can continue serving** while their dependencies remain healthy.
- Pods/VMs/volumes in zone A are affected according to the outage scope; remaining capacity depends on replicas in B/C.

If a zonal cluster only has nodes in zone A, a zone A outage can take down **all workloads**. If nodes span multiple zones, the data serving path may survive, yet **the control plane remains a single-zone dependency**.

Zonal clusters are typically suitable for **dev/test environments**, training, or workloads whose budget and availability targets allow single-zone control plane risk. Do not pick a zonal control plane for critical production just because you created three nodes in one zone.

### 2.2. GKE Standard Regional Cluster

A **regional cluster** runs multiple control plane replicas across multiple zones in **one region**, making the Kubernetes API more resilient to a single-zone failure and during maintenance/upgrades. By default in Standard, node pools are distributed across **three zones** in the region (when supported); you can select fewer zones or even a **single zone** for a node pool if needed.

~~~mermaid
flowchart TB
    subgraph REGION["GKE Standard regional cluster"]
      subgraph A["Zone A"]
        CPA["Control plane replica A"]
        NA["Node + Pod A"]
      end
      subgraph B["Zone B"]
        CPB["Control plane replica B"]
        NB["Node + Pod B"]
      end
      subgraph C["Zone C"]
        CPC["Control plane replica C"]
        NC["Node + Pod C"]
      end
    end
    CPA <--> CPB
    CPB <--> CPC
    CPA <--> CPC
~~~

With a regionally managed GKE control plane, losing one zone **normally does not interrupt Kubernetes API access**. Even so, the application only tolerates a zone failure if **there are sufficient healthy nodes and ready Pods in the remaining zones**.

A regional cluster with a node pool **only in zone A** still has an HA control plane, yet the workload can go completely offline if zone A fails. Therefore:

> **Regional control plane ≠ multi-zone workload ≠ multi-region application.**

After cluster creation, **you cannot convert the control plane type from zonal to regional or vice versa** with an ordinary update command. Changing control plane type requires creating a new cluster and migrating workloads; by contrast, node locations of a Standard cluster can be modified where supported, though doing so can add/remove nodes and cause disruption.

### 2.3. Comparison Table of the Four Standard Combinations

| Control plane | Node locations | Survives single-zone control plane failure? | Survives single-zone workload failure? | Use Case |
| --- | --- | --- | --- | --- |
| **Zonal** | Single zone | **No** guarantee that Kubernetes API stays up | **No**, if all nodes are in the failed zone | Lab/dev/test |
| **Zonal** | Multi-zone | **No**; API still depends on one zone | **Possibly**, if enough Pod replicas run in surviving zones | Workloads needing a multi-zone data plane while accepting a single-zone control plane |
| **Regional** | Single zone | **Capable** of surviving a single-zone failure per control plane design | **No**, if the sole zone hosting nodes fails | Dev/test needing control plane HA while optimizing node cost |
| **Regional** | Multi-zone | **Capable** of surviving a single-zone failure per control plane design | **Possibly**, if scheduling, replicas, storage, and traffic are designed properly | Default baseline to consider for critical production |

The word "possibly" is intentional. A multi-zone node cluster where an application has only **one replica**, or where all three replicas land in zone A, **does not** automatically protect the service when zone A fails. The table describes infrastructure properties, not application SLAs.

### 2.4. How Do Autopilot and Standard Differ in Availability Options?

**GKE Autopilot clusters are always regional**: the control plane is replicated across multiple zones in the region. Google Cloud manages most node configuration, autoscaling, security, and infrastructure operations; users declare Pod resources, scheduling requirements, and workload policies.

**GKE Standard** lets you choose zonal or regional, machine types, node pool locations, and deeper node administration settings. Some Standard clusters can also run **Autopilot workloads** depending on supported features and versions; that does not change the control plane type of the underlying cluster.

| Topic | Autopilot cluster | Standard cluster |
| --- | --- | --- |
| Control plane | Always regional | Choose zonal or regional at creation |
| Node management | Mostly managed by GKE | Operators create/manage node pools and advanced settings |
| Workload placement | GKE manages node provisioning within the region subject to Pod constraints | Depends on node locations, capacity, autoscaler, and scheduling constraints |
| Cost optimization | Autopilot resource and billing model | Node/cluster and resource billing per Standard configuration |
| Best fit | Reduce node administration and use managed defaults | Need control over machines, zones, node pools, and deep customization |

Autopilot **does not guarantee** application replicas exist in every zone if Pod configuration or replica count is unsuitable. You must still verify Pod placement, requests, data persistence, readiness, and load balancing.

## 3. Failure Domain Analysis: Node, Zone, Control Plane, and Region

No architecture is "high availability" merely because it has many components. Enumerate each **failure domain** and its impact on the real system.

### 3.1. Failure Matrix and Serving Expectations

| Incident | Zonal control plane | Regional control plane | Conditions for Application to Keep Serving |
| --- | --- | --- | --- |
| One Pod crashes | Control plane typically continues managing cluster | Same | Other replicas exist, plus probes and ability to recreate the Pod |
| One node fails | Scheduler/controllers must operate to replace replicas | Same | Other nodes have CPU/RAM/IPs, storage, and quota |
| Zone **hosting the control plane** fails | Kubernetes API may be interrupted; app data plane in other zones may keep working | Control plane typically maintains availability via other replicas | Nodes/Pods outside the failed zone, healthy services and data |
| Zone **hosting only worker nodes** fails | API remains up if control plane is in another zone | API remains up per cluster state | Replicas outside the failed zone and traffic properly routed away |
| All nodes in one zone fail | Depends on control plane location | Control plane may stay up, but workload stops | Must have nodes and Pods in other zones |
| Entire **region** fails | Loss of most/all regional components | Control plane replicas are also in the **same region** | Requires standby cluster and data in another region |
| Dependency outside GKE fails | Not solved by cluster type alone | Not solved by cluster type alone | Database, DNS, load balancer, networking, IAM, and backends need independent resilience |

For a **zonal cluster with nodes across multiple zones**, do not confuse "API unreachable" with "all containers stopped." Running Pods can continue serving traffic; however, if another node fails while the API is down, controllers/scheduler cannot replace replicas normally.

For a **regional cluster**, also do not assume networking, clients, and databases automatically keep working during a zone failure. End-to-end availability must include the user request path and every dependency capable of causing an outage.

### 3.2. Kubernetes API Availability Differs from Application API Availability

Suppose a sales API runs three replicas load-balanced by a Service:

- When the **Kubernetes API** is temporarily unavailable, replicas on healthy nodes can keep serving HTTP requests.
- When **all nodes hosting replicas** become unavailable, there are no application backends even though the Kubernetes API is healthy.
- When a database placed in a single zone fails, the HTTP frontend may still return errors even with all three API replicas running.
- When health checks mark a replica `NotReady`, Kubernetes or the load balancer can remove the Pod from endpoints; requests may fail if too few healthy replicas remain.

Therefore, separate monitoring across:

1. **Control plane/API availability:** can the cluster be reached and administered?
2. **Workload availability:** `Ready` replica counts, endpoints, HTTP p95/p99 latency, error rate.
3. **Data availability:** database queries, read/write latency, replicas/backups, and consistency.
4. **Network availability:** DNS, load balancing, firewalls, VPC, egress, and connectivity to dependencies.

### 3.3. SLO, RTO, and RPO

| Concept | Design Question | Illustrative Example |
| --- | --- | --- |
| **SLO (Service Level Objective)** | Over a measurement window, what quality level must the service meet? | 99.9% successful requests over a month, per defined measurement. |
| **RTO (Recovery Time Objective)** | If an incident occurs, how long can recovery take? | Restore service within 30 minutes. |
| **RPO (Recovery Point Objective)** | How much data created before an incident can we tolerate losing? | Maximum 5 minutes of data loss. |
| **Error budget** | Within the SLO window, how much degradation is allowable? | Used to balance release velocity against operational risk. |

For example, a **99.9% availability** target over a 30-day month equals roughly **43.2 minutes** of downtime under a simple continuous model. That is a mathematical conversion, **not an SLA guaranteed by creating a regional cluster**. An application with a single-zone database or a faulty deployment can still blow through its error budget.

## 4. Ensuring Pods Truly Span Multiple Zones

A regional control plane is only the foundation. To improve availability for **stateless workloads**, control replica counts, Pod placement, application health, node scaling capacity, and rollout strategy.

### 4.1. Deployment Replicas Alone Do Not Imply Zonal Distribution

A Deployment:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: catalog-api
  template:
    metadata:
      labels:
        app: catalog-api
    spec:
      containers:
        - name: app
          image: nginx:stable-alpine
          ports:
            - containerPort: 80
~~~

This YAML requests three Pods, but **it does not force one Pod per zone**. The scheduler may place Pods on nodes/zones that satisfy resource and cluster state conditions. You cannot rely on `replicas: 3` alone to prove single-zone fault tolerance.

### 4.2. Zone-Based Topology Spread Constraints

Kubernetes provides `topologySpreadConstraints` to guide the scheduler in spreading Pods across topology labels. Each GKE node typically carries the zone label `topology.kubernetes.io/zone`.

Example of a Deployment with **three replicas** requiring the Pod count skew across eligible zones not to exceed one:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog-ha
  labels:
    app: catalog-ha
spec:
  replicas: 3
  revisionHistoryLimit: 5
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 0
      maxSurge: 1
  selector:
    matchLabels:
      app: catalog-ha
  template:
    metadata:
      labels:
        app: catalog-ha
    spec:
      topologySpreadConstraints:
        - maxSkew: 1
          topologyKey: topology.kubernetes.io/zone
          whenUnsatisfiable: DoNotSchedule
          labelSelector:
            matchLabels:
              app: catalog-ha
      containers:
        - name: web
          image: nginx:stable-alpine
          ports:
            - containerPort: 80
          resources:
            requests:
              cpu: 100m
              memory: 64Mi
            limits:
              memory: 128Mi
          readinessProbe:
            httpGet:
              path: /
              port: 80
            initialDelaySeconds: 2
            periodSeconds: 5
          livenessProbe:
            httpGet:
              path: /
              port: 80
            initialDelaySeconds: 10
            periodSeconds: 10
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: catalog-ha-pdb
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: catalog-ha
~~~

**Use this template only for stateless workloads** and adapt it to your application. `nginx:stable-alpine` is fine for demos; in production, pin the image version/digest, size resources via load testing, and restrict container privileges.

Explanation:

- `replicas: 3`: Kubernetes targets three replicas.
- `topologyKey: topology.kubernetes.io/zone`: uses zone as the spread domain.
- `maxSkew: 1`: the difference in Pod counts across eligible domains considered by the scheduler cannot exceed one.
- `whenUnsatisfiable: DoNotSchedule`: if the constraint cannot be met, the Pod stays **Pending** rather than stacking all replicas into one zone.
- `readinessProbe`: ensures Pods receive traffic only after readiness checks succeed.
- `livenessProbe`: restarts unhealthy containers per condition; **does not replace a startup probe** for slow-starting apps.
- `maxUnavailable: 0`, `maxSurge: 1`: during a rolling update with sufficient resources, avoids reducing desired Pod count under normal update strategy; does not protect against zone failures.
- `PodDisruptionBudget minAvailable: 2`: limits **voluntary evictions** via supported mechanisms like `kubectl drain`; does not prevent VM failures or zone outages.

### 4.3. Conditions for Topology Spread to Actually Work

1. There must be **eligible nodes in multiple zones**. A regional cluster whose nodes are only in zone A cannot physically schedule Pods into zones B/C via YAML.
2. CPU/RAM/IPs and quotas must be sufficient in each zone. Lack of capacity can leave Pods `Pending`.
3. Node selectors, affinity, taints/tolerations, GPU availability, PVC topology, or other constraints can reduce eligible zones.
4. `topologySpreadConstraints` guides scheduling across eligible domains, **not guaranteeing exactly one Pod per zone in every state**. To verify, inspect which zone's nodes the Pods are actually running on.
5. When a zone is lost, remaining serving replicas may drop. The autoscaler, quotas, and Pod constraints determine whether replacement replicas can schedule in surviving zones.
6. If the application requires a strict minimum of two or three zones **at all costs**, add stronger topology rules, node sizing, policies, and alerts; a basic spread rule does not guarantee that across all cluster states.

### 4.4. Pod Anti-Affinity and How It Differs from Spread

**Pod anti-affinity** can prevent identical Pods from landing on the same node, or even in the same zone via topology labels. However, a strict `requiredDuringSchedulingIgnoredDuringExecution` rule can render Pods unschedulable when capacity is tight.

In many cases, topology spread constraints express a "balanced distribution" goal more cleanly, while pod anti-affinity fits cases where you explicitly want to **avoid co-location** among replicas. They can be combined when needed, but must be tested under node shortage and rollout scenarios.

### 4.5. Replicas, HPA, Cluster Autoscaler, and PodDisruptionBudget Do Not Replace Each Other

| Mechanism | What Does It Control? | What It Does Not Solve Alone |
| --- | --- | --- |
| **Deployment replicas** | Desired Pod count. | Zone placement, readiness, data, and quotas. |
| **Topology spread / affinity** | Scheduler rules for selecting nodes/zones. | Creating nodes when capacity is missing. |
| **Horizontal Pod Autoscaler (HPA)** | Adjusts Pod count by metrics/conditions. | Creating VMs when nodes are full. |
| **Cluster Autoscaler / node auto-provisioning** | Adds/removes nodes or pools per GKE capabilities/rules. | Always finding capacity in a zone or guaranteeing perfectly even Pod spread. |
| **PodDisruptionBudget** | Limits certain voluntary eviction scenarios. | Involuntary node/zone failures or application bugs. |
| **Readiness/liveness/startup probes** | Determines serving readiness and container recovery. | Creating replicas in another zone or rescuing a database. |
| **Rolling update / surge** | How replicas are replaced when resources permit. | Protecting against broken images or bad configs. |

To survive a zone failure, you need **headroom**: when part of the node fleet is lost, remaining zones must have enough capacity to serve at least critical load or scale up within RTO. Cluster Autoscaler takes time to provision VMs and can hit quota/capacity limits; do not treat it as instantaneous recovery.

## 5. Stateful Workloads: Storage Location Is Also a Failure Domain

A stateless Deployment can recreate Pods from a container image. However, for workloads using a **PersistentVolumeClaim (PVC)**, starting a Pod in another zone also depends on whether the volume can attach, mount, and preserve data. Placing a database in a regional cluster **does not automatically turn zonal data into regional data**.

### 5.1. Zonal Persistent Disk and Pod Placement

Suppose a StatefulSet uses a PVC backed by a **zonal Persistent Disk** provisioned in zone A. When the Pod is rescheduled onto a node in zone B, the zonal volume **cannot attach** due to location constraints. The Kubernetes scheduler considers PV topology, but after a zone outage you cannot assume a volume in zone A becomes available in zone B.

~~~mermaid
flowchart LR
    A["Zone A<br/>Stateful Pod + zonal disk"] -->|Zone A lost| X["Cannot automatically attach zonal disk<br/>in zone B"]
    B["Zone B<br/>Surviving node"] -. "Requires appropriate volume/replica" .-> C["Stateful Pod can recover"]
~~~

Verify:

- StorageClass, CSI driver, `volumeBindingMode`, access mode, and topology.
- Physical location of the persistent volume and the node where the Pod is scheduled.
- Recovery procedures when a node/zone fails; never force attach/mount against storage rules.
- Backups and application-consistent restore procedures.

### 5.2. Regional Persistent Disk and Other Options

**Regional Persistent Disk** replicates data synchronously between two zones within a region per product capabilities. With GKE and supported configurations, it improves stateful resilience during a single-zone failure. However:

- You still need appropriate **StorageClass/CSI topology, attach permissions, and failover** configuration.
- Having a volume with data does not automatically guarantee the **database process** restarts or fails over roles safely.
- Evaluate RPO/RTO impact if a link/replica is lost or the volume enters a degraded state.
- If the entire region fails, regional PD does not solve cross-region recovery.

For certain supported workloads, Google Cloud provides capabilities such as the **Stateful HA Operator** and matching storage types to manage part of the recovery workflow; review product prerequisites and test thoroughly before relying on them.

| Data Type | Options to Evaluate | Key Conditions |
| --- | --- | --- |
| Stateless API | Keep no durable state on Pod filesystems | Requests can be handled across replicas/zones. |
| Uploads/videos/large files | Cloud Storage with appropriate bucket location and policies | Apps avoid keeping sole file copies on local node disks. |
| Database using a managed service | Cloud SQL HA or an appropriate managed data service | Multi-zone HA, connectivity, backups, and failover must be configured/tested. |
| Database running inside Kubernetes | StatefulSet + suitable storage/replication/operator | Consistency, leader election, failover, and backups managed by app/tooling. |
| Rebuildable cache | Clustered or managed Redis/cache | Confirm whether cache misses during a zone outage are acceptable. |
| Shared filesystem | Filestore or supported file storage solutions | NFS semantics and failure domain differ from PD. |

### 5.3. Readiness and Graceful Shutdown During Rolling Upgrades

A Pod must not receive traffic the instant its container starts if its database connection pool, config, and caches are not ready yet. **Readiness probes** should reflect actual readiness to serve; **startup probes** can protect slow-starting apps from being killed prematurely by liveness checks.

During rolling updates, set `terminationGracePeriodSeconds` and handle `SIGTERM` so the app stops accepting new requests, finishes in-flight requests, and exits cleanly. For database writers, account for transactions and leader handoff.

**A PDB helps limit voluntary evictions, but it does not replace** readiness probes, graceful shutdown, backups, or replication.

## 6. Connectivity, Load Balancing, and External Dependencies

### 6.1. Regional VPC/Subnets in a Multi-Zone Cluster

GKE nodes run on Google Cloud networking. In a **VPC-native** cluster, Pod IPs are managed via subnet secondary ranges per GKE configuration. Because subnets are regional, nodes in different zones of the **same region** can use the configured network/subnet per cluster design.

However:

- Pod IP ranges must be large enough for scaling and replacing nodes after a zone failure.
- Firewall rules, NetworkPolicies, and Dataplane mechanisms affect Pod-to-Pod, Pod-to-service, and Pod-to-database traffic.
- GPU/accelerator nodes may only be available in certain zones; node locations must match actual hardware availability.
- **Control plane location** does not mean all client traffic flows through the control plane zone; application traffic follows its own data path.

### 6.2. Inspecting the User Traffic Path

A multi-zone HTTP application can be exposed via an External Application Load Balancer / GKE Gateway or Ingress as configured. The design must ensure:

1. The load balancer receives traffic and has appropriate health checks.
2. Backends/NEGs or endpoint groups contain **`Ready` Pods** in available zones.
3. When a zone fails, unhealthy endpoints are removed from the serving path after health check convergence.
4. Surviving zones have enough capacity to handle the shifted traffic.
5. HTTPS/certificates, Cloud Armor, and secret access do not depend on a self-managed VM/proxy in the failed zone.

Do not assume "GKE Service type LoadBalancer" is sufficient for every HTTP and DR requirement. Choose the proper load balancer type and scope based on protocol, ingress pattern, security, and multi-backend needs.

### 6.3. Database Dependencies

Suppose three API replicas sit in three different zones, yet all connect to **a single non-HA Cloud SQL instance** in zone A. If the database goes down during a zone outage, all three APIs may return errors or serve only non-DB paths. A regional cluster does not automatically make Cloud SQL highly available.

For Cloud SQL, select appropriate **high availability / regional** capabilities, design secure connectivity, retry with backoff, use idempotent transactions, and configure backups/PITR per product support. If database replication has lag, account for RPO and verify what staleness the application tolerates.

### 6.4. Distinguishing Multi-Zone from Multi-Region

A **regional cluster** has its control plane replicated **within a single region**. If the entire region experiences an outage, you do not have a second regional cluster merely because the cluster is called "regional."

To tolerate an **entire region failure**, consider a **multi-cluster, multi-region** design where each cluster and data store can serve independently:

~~~mermaid
flowchart TB
    USER["Users"] --> G["Global traffic routing / load balancing"]
    G --> CL1["Cluster A<br/>region 1, multi-zone"]
    G --> CL2["Cluster B<br/>region 2, multi-zone"]
    CL1 --> DATA1[("Region 1 data")]
    CL2 --> DATA2[("Region 2 data")]
    DATA1 <-.->|"Replication / backup with RPO"| DATA2
~~~

Multi-region architecture also requires defining:

- **Traffic failover:** load balancer/Gateway/DNS, health checks, and actual convergence time.
- **Data:** synchronous/asynchronous replication, write conflicts, leader election, restore, and backups/PITR.
- **Deployment:** keeping images, manifests, IAM, secrets, and configs consistent across both clusters.
- **Security:** VPCs, firewalls, Workload Identity Federation for GKE, service accounts, and per-environment permissions.
- **Quotas/capacity:** standby region has sufficient resources while the primary region is down.
- **Cost and residency:** cross-region traffic, storage, logs, backups, and data residency rules.
- **Drills:** testing failover/failback and measuring actual RTO/RPO, not just drawing an architecture diagram.

This is a **disaster recovery** problem broader than choosing zonal or regional for a single cluster.

## 7. Cost, Quotas, Capacity, and Operational Safety

### 7.1. One Flag Can Multiply Node Counts

In a GKE Standard **regional cluster with a node pool spanning three zones**, `--num-nodes` at pool creation is typically **the number of nodes per zone**, not the total node count across the region.

For example:

| Node locations | `--num-nodes` | Initial Total Nodes in Example |
| --- | ---: | ---: |
| One zone | 1 | 1 |
| Two zones | 2 | 4 |
| Three zones | 1 | 3 |
| Three zones | 3 | 9 |

This explains why a default regional Standard cluster can create **9 nodes (3 nodes/zone × 3 zones)** if you do not override the node count. For labs, **explicitly set the node count** and check total VMs, quotas, and costs.

With node pool **autoscaling**, distinguish **per-zone** limits from **total-node** limits, such as `--min-nodes`/`--max-nodes` versus `--total-min-nodes`/`--total-max-nodes` as supported. Do not treat 3 as total autoscaler capacity when you actually configured 3 per zone.

### 7.2. Cost Categories

| Category | What to Measure or Estimate |
| --- | --- |
| Cluster management | GKE management fees by mode/configuration and current free-tier policy. |
| Worker nodes | Compute Engine vCPU/RAM, boot disks, extra nodes across zones, and uptime hours. |
| Network traffic | Inter-zone Pod/VM traffic, Internet egress, cross-region traffic to remote dependencies. |
| Load balancing | Forwarding rules, request processing, backends, health checks, and IPs per pricing. |
| Storage | PVCs/Persistent Disks, regional disks, snapshots/backups, cross-zone replication data. |
| Logging/Monitoring | Log volume, metrics, retention, alerting, and enabled observability backends. |
| Operations/DR | Standby clusters, image registries, secrets, CI/CD, and spare capacity reserved for zone failures. |

**Do not assume a regional cluster always costs three times a zonal cluster just because the control plane has multiple replicas**: actual cost depends on node counts, cluster management model, networking, and data services. Conversely, running nodes in three zones often costs more if total node count increases and cross-zone traffic occurs.

### 7.3. Quotas and Provisioning Capacity During Incidents

A regional cluster consumes Compute Engine and regional quotas per configuration; clusters with nodes in multiple zones may need more public/in-use IP quota, vCPUs, disks, and subnet IPs. GPUs/TPUs may not be available in every zone.

Before committing to a zone-fault-tolerant design, verify:

1. **Aggregate and regional/zonal quotas** cover both steady state and replacement nodes.
2. **Subnet primary/secondary IP ranges** have room for new nodes and Pods.
3. **Node auto-provisioning and Cluster Autoscaler** can select eligible zones and machine series.
4. **Image registries and egress paths** remain reachable when new nodes join.
5. Applications declare **resource requests** close to real load so the scheduler and autoscaler make accurate decisions.
6. **Spare capacity** or controlled load-shedding plans exist when a zone goes down.

In a Standard regional cluster, GKE recommends multi-zone node pools for higher availability, though the autoscaler **does not guarantee** nodes remain evenly balanced across zones at every moment.

### 7.4. Upgrades and Maintenance

A regional control plane keeps the Kubernetes API available better during upgrades/resizing than a zonal one, yet **node pool upgrades can still disrupt Pods**. To limit risk:

- Choose a release channel and maintenance windows/exclusions aligned with organizational process.
- Use **surge or blue-green upgrades** on node pools where supported.
- Configure sensible PodDisruptionBudgets, adequate replicas, and resource headroom.
- Verify workload readiness, graceful termination, and dependencies.
- Perform canary rollouts, monitor SLOs, and keep an application rollback plan ready.

An overly strict PDB paired with a low replica count can block maintenance operations. Assess the risk beforehand rather than disabling all protections during updates.

## 8. Hands-On: Creating a Standard Regional Cluster with Nodes in Three Zones

**Objective:** create a Standard **regional** cluster in a test project starting with one node per zone, deploy three sample Pods, verify actual placement, and clean up resources. This lab focuses on **observation** and **does not induce a real zone outage**.

> **Cost and permission warning:** the commands in this section can create **billable** clusters, Compute Engine VMs, disks, networking, and logs. Run them only in a lab project with Cloud Billing and an approved budget. Never use a production project or another team's shared cluster. Reading this Markdown does not execute any commands.

### 8.1. Preparation and Scoping

Prerequisites:

- A lab project with permissions to enable the Kubernetes Engine/Compute Engine APIs and create VPCs, subnets, service accounts, IAM bindings, and GKE clusters.
- `gcloud` and `kubectl` installed and authenticated with the proper account; examples run in **Bash/Cloud Shell**.
- A region with at least three eligible zones and `e2-standard-2` available in the chosen zones.
- Quotas for vCPUs, in-use IPs, disks, secondary IP ranges, and networking sufficient for **three concurrent nodes**.
- CIDR ranges `10.90.0.0/20`, `10.91.0.0/16`, and `10.92.0.0/20` do not overlap with other VPCs or hybrid/peered networks.
- Organizational policies allow cluster/node network configuration, node image pulls, control plane connectivity, and Google Cloud API access. In environments enforcing private nodes, plan egress/Cloud NAT or supported API paths separately.

Define variables in Bash:

~~~bash
export PROJECT_ID="YOUR_LAB_PROJECT_ID"
export REGION="asia-southeast1"
export ZONE_A="asia-southeast1-a"
export ZONE_B="asia-southeast1-b"
export ZONE_C="asia-southeast1-c"
export NETWORK="gke-ha-lab-vpc"
export SUBNET="gke-ha-lab-subnet"
export CLUSTER="gke-regional-ha-lab"
export NODE_SA="gke-ha-node-lab@$PROJECT_ID.iam.gserviceaccount.com"

gcloud config set project "$PROJECT_ID"
gcloud config get-value project

# Read-only: verify region/zones, machine type, and related quotas
gcloud compute zones list --filter="region:$REGION"
gcloud compute machine-types describe e2-standard-2 --zone="$ZONE_A"
gcloud compute machine-types describe e2-standard-2 --zone="$ZONE_B"
gcloud compute machine-types describe e2-standard-2 --zone="$ZONE_C"
~~~

If the region/zone or machine type is unavailable, pick locations permitted by your organization rather than guessing zone names. The three Singapore zones are only **examples**, not a universal data-residency recommendation.

### 8.2. Enable APIs and Create a Minimal Node Service Account

Run only with authorized permissions in the lab project:

~~~bash
gcloud services enable \
  container.googleapis.com \
  compute.googleapis.com \
  iam.googleapis.com

# Dedicated node service account rather than sharing a broad admin account
gcloud iam service-accounts create gke-ha-node-lab \
  --display-name="GKE HA lab node"

# Minimal role for GKE node logging/monitoring system tasks
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$NODE_SA" \
  --role="roles/container.defaultNodeServiceAccount"
~~~

`roles/container.defaultNodeServiceAccount` is the GKE-recommended role for basic node system tasks. Depending on where images live and workload needs, review **Artifact Registry read permissions**, project quotas, logging policies, and *specific* extra roles. Never grant project-wide Owner or Editor just to bypass image pull errors.

A node service account is distinct from an application's **Kubernetes ServiceAccount**. When Pods need to call Google Cloud APIs, prefer **Workload Identity Federation for GKE** with workload-scoped IAM rather than granting database or Secret Manager permissions to entire nodes.

### 8.3. Create a Custom VPC and Regional Subnet

The lab uses a dedicated VPC with a primary IP range for nodes and secondary ranges for Pods/Services:

~~~bash
gcloud compute networks create "$NETWORK" \
  --subnet-mode=custom

gcloud compute networks subnets create "$SUBNET" \
  --network="$NETWORK" \
  --region="$REGION" \
  --range=10.90.0.0/20 \
  --secondary-range=gke-ha-pods=10.91.0.0/16,gke-ha-services=10.92.0.0/20

gcloud compute networks subnets describe "$SUBNET" \
  --region="$REGION" \
  --format="yaml(name,region,ipCidrRange,secondaryIpRanges)"
~~~

Subnets are **regional** resources: the same subnet can serve nodes across all three zones in the region. Secondary ranges are allocated for GKE Pod/Service IP aliasing. Avoid ranges that conflict with on-premises or connected networks.

### 8.4. Create a Regional Cluster with One Node per Zone

~~~bash
gcloud container clusters create "$CLUSTER" \
  --region="$REGION" \
  --node-locations="$ZONE_A,$ZONE_B,$ZONE_C" \
  --num-nodes=1 \
  --machine-type=e2-standard-2 \
  --enable-ip-alias \
  --network="$NETWORK" \
  --subnetwork="$SUBNET" \
  --cluster-secondary-range-name=gke-ha-pods \
  --services-secondary-range-name=gke-ha-services \
  --release-channel=regular \
  --service-account="$NODE_SA"
~~~

Explanation:

- `--region` selects a **regional control plane**, unlike `--zone` for a zonal cluster.
- `--node-locations` specifies three zones for nodes, all within the **same region**.
- `--num-nodes=1` means **one node per zone** in this initial setup, totaling **3 nodes**.
- `--enable-ip-alias` and secondary range names enable the VPC-native IP model.
- `--service-account` attaches the dedicated node identity; it does not grant application Pods automatic access to all services.
- `--release-channel=regular` selects a release channel; production governance also requires maintenance windows, security hardening, and version management.

Cluster creation takes several minutes and requires multiple permissions; if it fails, read the error details and resolve **quota, networking, IAM, or node capacity**. Do not randomly switch zones/regions or escalate to Owner without identifying the root cause.

### 8.5. Verify Control Plane and Node Locations

~~~bash
gcloud container clusters describe "$CLUSTER" \
  --region="$REGION" \
  --format="yaml(name,location,locations,status,nodePools)"

gcloud container clusters get-credentials "$CLUSTER" \
  --region="$REGION" \
  --project="$PROJECT_ID"

# Include zone labels in node listing output
kubectl get nodes -L topology.kubernetes.io/zone

# Cluster and node pool overview
kubectl cluster-info
kubectl get nodes -o wide
~~~

With capacity across all three zones and successful creation, you expect to see **3 nodes**, one each in zones A/B/C. Inspect the actual label column rather than relying only on VM names. If only two nodes appear or a node stays NotReady, check events, quotas, node pool status, and node creation timestamps.

`gcloud container clusters describe` confirms cluster location at the **region level**; `kubectl get nodes -L topology.kubernetes.io/zone` shows which zones actually host the nodes.

### 8.6. Compare with the Zonal Cluster Creation Command

**Do not run the command below at the same time as the regional lab** unless additional resources and costs are approved. This is only a **comparison example** for control plane type:

~~~bash
# ILLUSTRATIVE ONLY: zonal control plane in zone A, nodes across A/B/C
gcloud container clusters create gke-zonal-multizone-example \
  --zone="$ZONE_A" \
  --node-locations="$ZONE_A,$ZONE_B,$ZONE_C" \
  --num-nodes=1 \
  --machine-type=e2-standard-2 \
  --enable-ip-alias \
  --network="$NETWORK" \
  --subnetwork="$SUBNET" \
  --release-channel=regular \
  --service-account="$NODE_SA"
~~~

The core difference is **`--zone="$ZONE_A"`**: the control plane resides only in zone A even though nodes span three zones. When secondary ranges are already in use by another regional cluster, a second cluster needs **separate IP ranges**; therefore, do not copy this comparison snippet directly to create a second cluster in the same subnet without IP planning. Running it for real requires dedicated ranges, quotas, and cleanup.

If the goal is a **single-zone zonal cluster**, omit `--node-locations` or pass only zone A; both the control plane and nodes then default to zone A.

### 8.7. Deploy a Sample Workload and PodDisruptionBudget

From a shell where `kubectl` points to the **correct lab cluster**, run:

~~~bash
kubectl create namespace gke-ha-lab

kubectl apply -n gke-ha-lab -f - <<'YAML'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ha-demo
spec:
  replicas: 3
  selector:
    matchLabels:
      app: ha-demo
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  template:
    metadata:
      labels:
        app: ha-demo
    spec:
      topologySpreadConstraints:
        - maxSkew: 1
          topologyKey: topology.kubernetes.io/zone
          whenUnsatisfiable: DoNotSchedule
          labelSelector:
            matchLabels:
              app: ha-demo
      containers:
        - name: web
          image: nginx:stable-alpine
          ports:
            - containerPort: 80
          resources:
            requests:
              cpu: 100m
              memory: 64Mi
            limits:
              memory: 128Mi
          readinessProbe:
            httpGet:
              path: /
              port: 80
            initialDelaySeconds: 2
            periodSeconds: 5
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: ha-demo-pdb
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: ha-demo
YAML

kubectl rollout status deployment/ha-demo -n gke-ha-lab
kubectl get pods -n gke-ha-lab -l app=ha-demo -o wide
kubectl get pdb -n gke-ha-lab
~~~

When all three nodes across the three zones are eligible and Pods become Ready, you **expect** one Pod placed in each zone. If a Pod stays `Pending`, run:

~~~bash
kubectl describe pod -n gke-ha-lab \
  "$(kubectl get pods -n gke-ha-lab -l app=ha-demo \
     -o jsonpath='{.items[0].metadata.name}')"

kubectl get events -n gke-ha-lab \
  --sort-by=.lastTimestamp
~~~

This inspects a single sample Pod; do not draw cluster-wide conclusions from one instance alone. To gather full evidence, match every Pod from `-o wide` against its node and zone label from `kubectl get nodes -L topology.kubernetes.io/zone`.

### 8.8. Testing a Safe Rolling Update in the Lab

Instead of inducing a real zone outage, perform a **voluntary** operation and observe replica availability:

~~~bash
# Run only in the test namespace / cluster
kubectl rollout restart deployment/ha-demo -n gke-ha-lab
kubectl rollout status deployment/ha-demo -n gke-ha-lab

kubectl get pods -n gke-ha-lab -l app=ha-demo -o wide
kubectl get pdb -n gke-ha-lab
~~~

This test only exercises Deployment update behavior and **is not equivalent to testing a zone outage**. PDBs govern eligible eviction requests; Deployment rolling updates primarily follow the Deployment's `maxUnavailable`/`maxSurge` strategy, so do not use this result to claim the PDB protects against outages.

To truly validate zone-failure resilience, run an approved **resilience/chaos test** in an isolated environment with a rollback plan and data-plane/dependency monitoring. Never delete production nodes/zones or break production links just to test a theoretical example.

### 8.9. Verify Distribution Quality, Not Just Pod Count

| Check | Command or Source | Pass Criterion |
| --- | --- | --- |
| Cluster type | `gcloud container clusters describe` | `location` is a region and matches the intended cluster. |
| Node zones | `kubectl get nodes -L topology.kubernetes.io/zone` | Ready nodes exist across A/B/C as expected. |
| Pod zones | `kubectl get pods -o wide` cross-referenced with node labels | Three replicas are distributed across zones as designed. |
| Pod readiness | `kubectl get pods`, `kubectl describe pod` | All desired replicas are Ready, no CrashLoopBackOff. |
| PDB | `kubectl get pdb` | `minAvailable` and allowed disruptions match after rollout. |
| Deployment rollout | `kubectl rollout status` | Update completes cleanly with no capacity shortage. |
| Quotas/IPs and node capacity | Cloud Console, `gcloud`, cluster events | Headroom remains for node replacement or extra replicas. |
| Real application health | Health checks, SLO dashboard | p95/p99 latency, error rate, and dependency connectivity meet targets. |

If nodes or Pods are missing, do not "fix" it by immediately removing topology constraints. First identify which zone lacks CPU/RAM/IPs or which scheduling/quota constraint is blocking placement, then decide whether to add capacity, switch zones, or adjust constraints per approved availability levels.

### 8.10. Clean Up All Lab Resources

From the **correct kubecontext and project**, verify the namespace and cluster before deleting:

~~~bash
kubectl config current-context
gcloud config get-value project
gcloud container clusters list --filter="name=$CLUSTER"

# Delete only the test namespace; never delete a shared namespace
kubectl delete namespace gke-ha-lab

# Delete the lab regional cluster
gcloud container clusters delete "$CLUSTER" \
  --region="$REGION" \
  --quiet
~~~

Wait for cluster deletion to finish. Then **verify no networking resources remain dependent on the cluster**, and delete the subnet and VPC created in this lab:

~~~bash
gcloud container clusters list --filter="name=$CLUSTER"
gcloud compute networks subnets describe "$SUBNET" \
  --region="$REGION"

gcloud compute networks subnets delete "$SUBNET" \
  --region="$REGION" --quiet

gcloud compute networks delete "$NETWORK" --quiet
~~~

Delete the service account and IAM binding only when no other workloads use them:

~~~bash
gcloud projects remove-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$NODE_SA" \
  --role="roles/container.defaultNodeServiceAccount"

gcloud iam service-accounts delete "$NODE_SA" --quiet
~~~

**Do not disable project APIs, delete other networks/namespaces, or delete shared projects.** If the subnet/VPC still reports dependencies, read the error to identify lab-owned resources; never force-delete components you did not create. Check for lingering disks, external IPs, logs, and extra services if you extended the lab beyond the examples.

GKE control planes, Compute Engine nodes, and remaining resources can continue incurring charges. Cloud Billing reports may lag; never assume closing Cloud Shell cleans up the lab.

## 9. Troubleshooting GKE Availability Incidents

When users report errors, isolate whether the issue sits in the **control plane, worker/data plane, application, networking, data layer, or quotas**. Do not conclude a regional cluster "lost HA" simply because one HTTP request failed.

### 9.1. Start from the Right Cluster

From an authenticated gcloud session:

~~~bash
# Read-only: confirm project and cluster
gcloud config get-value project
gcloud container clusters list

# Target the right cluster/location to investigate
gcloud container clusters get-credentials "$CLUSTER" \
  --region="$REGION" \
  --project="$PROJECT_ID"

kubectl config current-context
kubectl get nodes -L topology.kubernetes.io/zone
kubectl get pods -A -o wide
~~~

The example uses lab variables. In real operations, verify the project, cluster, and location, and view only authorized namespaces/data. `kubectl get pods -A` can expose infrastructure details across teams; do not share its output outside authorized channels.

### 9.2. Symptoms and Investigation Paths

| Symptom | Possible Causes | How to Verify |
| --- | --- | --- |
| `kubectl` cannot reach Kubernetes API | Zonal control plane outage; endpoint/IAM/RBAC/DNS/certificate issue | Check cluster type, endpoint, API status, and permissions; do not assume all nodes died. |
| `kubectl` works, but app returns 5xx | Pods not Ready, load balancer issue, database failure, or bad code | Inspect Deployment, endpoints, health checks, dependencies, and app logs. |
| Zone lost, Pods do not reschedule elsewhere | Insufficient nodes/CPU/RAM/IPs/quotas; zonal PVC; strict topology/affinity | Check `Pending` events, PV topology, autoscaler, and node pool locations. |
| Regional cluster, yet all Pods land in one zone | Single-zone node pool or unconstrained scheduler | Check node zone labels, Pod placement, and topology spread rules. |
| Cluster created more VMs than budgeted | `--num-nodes` is **per zone** | Check node locations, pool size, quotas, and billing. |
| Upgrade triggers 503s | Too few replicas, broken readiness probe, insufficient surge capacity | Inspect Deployment strategy, PDB, events, and headroom requirements. |
| Pods `Pending` after scaling | No nodes with enough resources, or blocked by taints/PVCs/scheduling | `kubectl describe pod`, events, quotas, autoscaler. |
| Node `NotReady` | VM/network issue, node service account, GKE components, or zone capacity | Inspect node conditions, GKE node pool status, node IAM, and logs. |
| HPA adds replicas, yet API remains slow | Cluster Autoscaler hasn't added nodes yet, or database/CPU is bottlenecked | Check HPA, node capacity, p99 latency, queues, and dependencies. |
| Multi-zone Pods, yet data fails | Database/PV is single-zone without HA | Check StorageClass, database replication, backups, and failover. |
| External traffic cannot enter | DNS, LB, Cloud Armor, VPC/firewalls, certificates | Trace hop by hop; do not assume a control plane failure. |

### 9.3. Read-Only Investigation Commands

~~~bash
kubectl get deploy,rs,pods -n gke-ha-lab -o wide
kubectl get pdb -n gke-ha-lab
kubectl describe deployment ha-demo -n gke-ha-lab
kubectl get events -n gke-ha-lab --sort-by=.lastTimestamp
kubectl describe nodes

gcloud container clusters describe "$CLUSTER" \
  --region="$REGION"
gcloud container node-pools list \
  --cluster="$CLUSTER" --region="$REGION"
~~~

These commands read configuration and status without modifying resources. If API connectivity is down, use Cloud Console, Cloud Monitoring, GKE operations/logs, and infrastructure telemetry to diagnose without relying on `kubectl`.

### 9.4. Decision Tree

~~~mermaid
flowchart TD
    INC["Degraded SLO / failing requests"] --> API{"Kubernetes API reachable?"}
    API -->|No| CP["Inspect control plane,<br/>location, endpoint, IAM, network"]
    API -->|Yes| POD{"Pods and endpoints Ready?"}
    POD -->|No| NODE["Check events, node zones,<br/>quotas, PVCs, and autoscaler"]
    POD -->|Yes| DEP["Inspect LB, DNS, database,<br/>secrets, and application"]
    CP --> TEST["Correlate failure domain;<br/>do not guess fixes"]
    NODE --> TEST
    DEP --> TEST
    TEST --> REC["Recover per runbook;<br/>re-measure SLO/RTO/RPO"]
~~~

**Rule:** only make a change when you know which layer it fixes. Raising replicas to 10 does not help if all 10 Pods sit `Pending` for lack of capacity. Creating another regional control plane will not repair a corrupted database.

## 10. Design Scenario: Online Course Platform

An online Java course business deploys payment APIs, lesson catalogs, and learning progress tracking on GKE. Learners are mainly in Southeast Asia; the system uses a transactional database and Cloud Storage for video assets. The team evaluates:

- **A:** Standard zonal cluster with control plane and nodes in zone A.
- **B:** Standard zonal cluster with control plane in A and nodes in A/B/C.
- **C:** Standard regional cluster with multi-zone control plane and nodes in A/B/C.

### 10.1. Evaluating the Options

| Requirement | A | B | C |
| --- | --- | --- | --- |
| Cost savings for small lab/dev | Suitable | May increase node count | Can use a single/few-zone node pool |
| Kubernetes API independent of one zone | No | No | Better suited |
| Pods can keep serving if one zone fails | No if all nodes are in one zone | Possibly if replicas are spread | Possibly if replicas are spread |
| Built-in whole-region fault tolerance | No | No | **No** |
| Database HA included | Must be designed separately | Must be designed separately | Must be designed separately |
| Node locations changeable later | Yes under Standard rules | Yes | Yes |
| Control plane type directly convertible | No | No | No |

**Recommendation:** choose C for critical production within **one region**, provided the organization ensures multi-zone nodes, Pod placement, resilient dependencies, and valid traffic paths. Choose A for dev/test when budget and downtime tolerance allow. B only improves workload survival across zones while leaving the Kubernetes API exposed to a single-zone failure.

### 10.2. Architecture Decision Record

~~~yaml
service: course-platform
environment: production
gke:
  mode: Standard
  control_plane: regional
  region: "<approved-region>"
  node_locations:
    - "<zone-a>"
    - "<zone-b>"
    - "<zone-c>"
  workload:
    replicas: 3
    topology_spread_by: topology.kubernetes.io/zone
    readiness_probe: true
    pdb_min_available: 2
  scaling:
    enabled: true
    capacity_after_one_zone_loss: "<load-to-maintain>"
dependencies:
  database: "<approved-HA-mechanism>"
  objects: "<bucket-and-location>"
  traffic: "<load-balancer-health-check>"
reliability:
  availability_slo: "<target>"
  rto: "<target>"
  rpo: "<target>"
security:
  node_service_account: "<least-privilege>"
  workload_identity: "<per-policy>"
observability:
  - ready_replicas_by_zone
  - request_error_rate
  - latency_p99
  - database_availability
~~~

This template is a decision record, **not a deployment manifest**. Placeholders must be replaced with evidence-backed data, owners, and approval dates; never infer SLO/RTO/RPO directly from the cluster type.

### 10.3. Simulated Zone A Outage Walkthrough

Initially, three API Pods run across A/B/C, all `Ready`. When zone A fails:

1. Nodes and Pods in A stop serving.
2. The regional control plane likely maintains Kubernetes API availability via replicas in other zones.
3. Endpoints and health checks must remove unhealthy Pods from the traffic path after convergence time.
4. If the remaining Pods can handle only 60% of peak load, users will still see errors or elevated p99 latency even though the service is not completely down.
5. Cluster Autoscaler can add nodes in B/C **if quotas, capacity, IPs, and time allow**; it is not instantaneous.
6. If the database exists only in A, the API may fail all data-dependent operations.
7. Upon recovery, verify rebalancing, data consistency, billing, and conduct a postmortem.

**Takeaway:** a regional control plane is one protective layer, yet **post-failure capacity and dependency survival** ultimately determine end-to-end SLOs.

### 10.4. Quantitative Exercise

Assume the API requires at least **6 allocatable vCPUs for workloads** at peak hours. Each node is a **2 nominal vCPU** machine, though the OS, Kubernetes system components, and resource reservations consume part of that capacity.

Answer the following:

1. Are three nodes—one per zone—enough to serve peak traffic after losing one zone?
2. To retain at least 6 **allocatable** vCPUs after a single-zone failure, how many spare nodes/vCPUs do you need across the two surviving zones?
3. If relying on Cluster Autoscaler, will VM provisioning time meet your RTO?
4. Between pre-provisioned headroom and post-incident scaling, which fits your cost and error budget better?

**Hint:** never multiply `2 nodes × 2 vCPU` and claim you have 6 vCPUs. Always measure `allocatable`, resource requests, real traffic load, and incident scaling behavior.

## 11. Self-Check Questions

**1. Must all nodes in a zonal cluster reside in one zone?**  
No. Standard zonal has a single-zone control plane, while nodes can span multiple zones in the region.

**2. Must a regional cluster spread its node pool across three zones?**  
No. A regional control plane has multi-zone replicas; Standard node pools can run in one or more zones, typically defaulting to three.

**3. Can a control plane be switched from zonal to regional via an update?**  
No. You must create a new cluster and migrate workloads per plan.

**4. Do Autopilot clusters have a zonal control plane option?**  
No. GKE Autopilot clusters are regional.

**5. Are three Pods in a Deployment automatically placed across three zones?**  
No. You need appropriate node locations, capacity, and scheduling constraints, and you should verify actual placement.

**6. Does a PodDisruptionBudget prevent unexpected zone or VM outages?**  
No. A PDB limits eligible voluntary evictions; it does not stop infrastructure failures.

**7. Why can a website keep working while the Kubernetes API is down?**  
Nodes and Pods running in healthy zones can continue serving traffic; however, orchestration, scheduling, and cluster updates are impacted.

**8. Does a regional cluster let a zonal Persistent Disk immediately run in another zone?**  
No. You must use appropriate storage, replication, topology, and recovery procedures.

**9. Across three zones, how many initial nodes does `--num-nodes=2` typically create in a regional Standard pool?**  
Six nodes: two per zone × three zones, assuming the command succeeds and no other setting overrides node count.

**10. Does one regional cluster automatically survive a full-region outage?**  
No. You need standby clusters, data, and traffic routing in another region.

**11. Why might increasing HPA replicas still fail to improve capacity?**  
HPA only requests more Pods; if nodes/quotas are exhausted or PVCs/affinity block scheduling, new Pods will not run.

**12. Why must p99 latency and database availability be monitored alongside Pod Ready state?**  
Pod Ready does not prove end-to-end transactions succeed; networking, load balancers, databases, and application logic also determine success.

## 12. Google Cloud and Kubernetes Reference Documentation

- [GKE cluster configuration choices](https://cloud.google.com/kubernetes-engine/docs/concepts/configuration-overview) — control plane/node locations and settings immutable after creation.
- [Regional clusters](https://cloud.google.com/kubernetes-engine/docs/concepts/regional-clusters) — control plane, node zones, quotas, and storage.
- [Creating a regional Standard cluster](https://cloud.google.com/kubernetes-engine/docs/how-to/creating-a-regional-cluster) — `--num-nodes`, `--node-locations`, and settings.
- [Creating a zonal Standard cluster](https://cloud.google.com/kubernetes-engine/docs/how-to/creating-a-zonal-cluster) — zonal and multi-zonal configurations.
- [Creating an Autopilot cluster](https://cloud.google.com/kubernetes-engine/docs/how-to/creating-an-autopilot-cluster) — Autopilot's regional control plane.
- [Managing GKE clusters](https://cloud.google.com/kubernetes-engine/docs/how-to/managing-clusters) — changing node locations and impact on running nodes.
- [GKE scalability best practices](https://cloud.google.com/kubernetes-engine/docs/concepts/planning-scalability) — capacity and multi-zone operation.
- [Create a VPC-native cluster](https://cloud.google.com/kubernetes-engine/docs/how-to/alias-ips) — node/Pod/Service subnet and secondary ranges.
- [Service accounts in GKE](https://cloud.google.com/kubernetes-engine/docs/how-to/service-accounts) — node and workload identities.
- [Configure GKE node service accounts](https://cloud.google.com/kubernetes-engine/security/configure-node-service-accounts) — the `roles/container.defaultNodeServiceAccount` role.
- [GKE persistent volumes](https://cloud.google.com/kubernetes-engine/docs/concepts/persistent-volumes) — PVCs, StorageClasses, and data topology.
- [Kubernetes topology spread constraints](https://kubernetes.io/docs/concepts/scheduling-eviction/topology-spread-constraints/) — spreading Pods across zones/nodes.
- [Kubernetes PodDisruptionBudgets](https://kubernetes.io/docs/tasks/run-application/configure-pdb/) — voluntary evictions.
- [Kubernetes liveness, readiness and startup probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/) — reflecting Pod health.
- [GKE pricing](https://cloud.google.com/kubernetes-engine/pricing) — current pricing structure.
- [Google Cloud disaster recovery planning](https://cloud.google.com/architecture/disaster-recovery) — RTO, RPO, and multi-region recovery.

Cluster types, GKE versions, pricing, quotas, and node provisioning behaviors can change. Before creating a production cluster, verify documentation against your actual **mode, region, zones, machine types, networking, and workloads**. Availability does not come from the "regional" label alone: **control plane, Pod placement, node capacity, data, load balancing, security, and recovery runbooks** must operate together as a system.
