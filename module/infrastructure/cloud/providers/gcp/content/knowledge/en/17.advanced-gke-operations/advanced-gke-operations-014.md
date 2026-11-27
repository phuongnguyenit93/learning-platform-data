# GKE Cluster Resource and Cost Optimization

> **Chapter:** Advanced GKE and Operations  
> **Module:** **CLOUD_PROVIDERS_GCP** — Exploring Google Cloud from project organization, IAM, and VPCs to Compute Engine, GKE, Cloud Run, storage services, and databases. Through deployment scenarios, learners select services, protect resources, automate releases, and monitor reliability and cost.

A GKE cluster can simultaneously **waste money on idle capacity** and **fail during load spikes**. True optimization is not slashing CPU and node counts at all costs: you must measure real consumption, set grounded resource requests, autoscale at the right layer, pick the right infrastructure tier, and verify **SLOs/RTO/RPO** after every change.

This lesson focuses on practical GKE operations: **measure → analyze → change with guardrails → verify both cost and reliability**. Examples use a Java API and a batch worker; mutating commands apply strictly to authorized environments.

## Learning Objectives

After this lesson, learners will be able to:

1. Distinguish GKE **Standard**, **Autopilot Pod-based**, and **Autopilot node-based** billing models.
2. Interpret requests, limits, actual usage, node allocatable capacity, Cloud Billing, and cost allocation.
3. Select and coordinate **HPA**, **VPA**, **Cluster Autoscaler**, **node pool auto-creation**, and **ComputeClass**.
4. Optimize node pools and choose On-demand, Spot, or CUDs without breaking SLOs.
5. Uncover hidden costs from storage, Load Balancers, cross-zone/region traffic, logs, and container images.
6. Design rightsizing experiments, validate autoscaling, and measure verified savings.
7. Diagnose Pending Pods, OOMKilled containers, CPU throttling, and nodes refusing to scale down.

## 1. Understand the Bill Before Optimizing

| Component | What is typically billed | Optimization lever |
|---|---|---|
| **GKE Standard** | Compute Engine VM nodes, disks, supporting infra, and cluster management fee | Eliminate idle node-hours; rightsize Pods and nodes |
| **Autopilot general-purpose** | Many workloads use **Pod-based billing** based on valid Pod resource requests | Accurate requests, HPA, suitable ComputeClass |
| **Autopilot specialized hardware** | Machine-series/accelerator workloads may use **node-based billing** plus node management premium | Match hardware to real demand; improve packing |
| **Cluster management** | Management fee per cluster tier/policy; free-tier credits where eligible | Inventory unused clusters; consolidate architecture |
| **PersistentVolumes / disks / snapshots** | Capacity, provisioned IOPS/throughput where applicable, snapshots | Delete verified orphans; rightsize volumes |
| **Load Balancers, external IPs, egress, NAT** | Forwarding rules, IPs, network traffic, and related SKUs | Remove unused LBs; cut unnecessary cross-zone traffic |
| **Artifact Registry, Logging, Monitoring** | Storage, egress, log/metric ingestion, and retention per terms | Trim low-value telemetry with guardrails |

**Note on Autopilot:** the "Autopilot" label alone is not enough to infer pricing. General-purpose Pods in supported ComputeClasses are typically billed per Pod request, whereas Pods requesting specialized hardware like GPUs, specific machine series, or certain ComputeClasses use **node-based billing**. Verify the **ComputeClass, hardware, and actual SKUs** before comparing options—never assume one flat CPU rate across every cluster.

~~~mermaid
flowchart LR
    BILL["Cloud Billing\nProject, Service, SKU"] --> MODE{"Mode + ComputeClass?"}
    MODE -->|"Standard"| NODES["Node VMs / disks / network"]
    MODE -->|"Autopilot general-purpose"| PODS["Pod-based requests"]
    MODE -->|"Autopilot specialized"| HARDWARE["Node-based hardware + premium"]
    NODES --> EXTRA["Shared fees: LB, IP, storage, logs"]
    PODS --> EXTRA
    HARDWARE --> EXTRA
~~~

### 1.1. Three Quantities to Distinguish

- **Actual usage:** CPU/memory actively consumed by the container; drives profiling and SLOs.
- **Requests:** capacity reserved by the scheduler for Pod placement; also drives autoscaling and cost allocation.
- **Limits:** runtime caps, where exceeding memory can trigger **OOMKilled** and hitting CPU limits causes **throttling**.

On **Standard**, lowering requests does not shrink the node bill immediately: Cluster Autoscaler must **actually remove nodes** or workloads must move onto smaller node types. On **Autopilot Pod-based**, requests directly affect billed resources after GKE applies defaults, minimums, and CPU:memory ratios.

## 2. Establish a Cost and Reliability Baseline

Optimizing without a baseline often yields changes that look cheaper for a few hours yet cause scale-outs, retries, slow responses, or outages later.

**Recommended measurement window:** at least **7 days** capturing both peak traffic and quiet hours; for monthly batch jobs, include a representative batch cycle. Capture the exact pre-change baseline and compare against an equivalent post-change window.

| Metric group | What to observe |
|---|---|
| Cost | Project/cluster/namespace/Service/SKU, credits, cost per request/job |
| Workload | Requests vs. CPU/memory usage p50/p95/p99, OOMs/restarts, queue lag |
| Node | Allocatable vs. requested, hourly node count, Pending Pods |
| User experience | Throughput, HTTP error rate, p95/p99 latency, availability |
| Scaling | HPA desired/current replicas; autoscaler scale-up/down events |
| Ancillary | PVC disk capacity, cross-zone egress, LBs, log volume |

### 2.1. Read-Only Inventory Commands

~~~bash
PROJECT_ID="YOUR_PROJECT_ID"
CLUSTER="YOUR_GKE_CLUSTER"
LOCATION="asia-southeast1"
NAMESPACE="checkout"

gcloud container clusters describe "$CLUSTER" \
  --project="$PROJECT_ID" --location="$LOCATION" \
  --format="yaml(name,location,currentMasterVersion,autopilot,autoscaling,costManagementConfig)"

gcloud container node-pools list \
  --project="$PROJECT_ID" --cluster="$CLUSTER" --location="$LOCATION"

# Run ONLY after verifying you are connected to the right cluster.
kubectl config current-context
kubectl get nodes -o wide
kubectl get deployments,hpa,vpa,pdb -n "$NAMESPACE"
kubectl get pods -n "$NAMESPACE" -o wide

# Depends on metrics API; may not be available in every setup.
kubectl top pods -n "$NAMESPACE" --containers
kubectl top nodes
~~~

`kubectl get vpa` may return an error if the VPA CRD/feature is disabled or you lack RBAC—never assume VPA is enabled everywhere. `kubectl top` shows only point-in-time samples, not historical trends or p95/p99 distributions.

Inspect requests and why the scheduler cannot place Pods:

~~~bash
kubectl describe deployment checkout-api -n "$NAMESPACE"
kubectl describe nodes
kubectl get events -n "$NAMESPACE" \
  --sort-by=.metadata.creationTimestamp
~~~

**Node capacity does not equal allocatable:** Kubernetes reserves resources for the OS, system daemons, and eviction thresholds. Always calculate Pod density against **allocatable**, checking CPU, memory, ephemeral storage, Pod IPs, topology, and GPU/TPU requirements.

### 2.2. KPIs to Avoid Blind Optimization

Every optimization experiment needs at least **two KPIs**:

- **Efficiency:** cost/request, cost/job, or total cost at equivalent traffic; node-hours and unallocated ratio.
- **Reliability:** p95 latency, HTTP 5xx, OOMs/restarts, job completion time, and availability.

If cost drops 15% while p95 latency breaches your SLO, that is **not a successful optimization**.

## 3. Rightsize Requests and Limits Before Adding or Removing Nodes

The scheduler places Pods based on **requests** and placement constraints, not idle CPU usage. A Pod requesting 2 vCPU while averaging 150m still reserves 2 vCPU and can force the cluster to spin up extra nodes.

### 3.1. Common Units

| Declaration | Meaning |
|---|---|
| `cpu: 100m` | 0.1 vCPU |
| `cpu: 500m` | 0.5 vCPU |
| `cpu: "2"` | 2 vCPU |
| `memory: 256Mi` | 256 MiB |
| `memory: 1Gi` | 1 GiB |

Suppose a Java API runs 8 replicas, each requesting **1000m CPU and 2Gi RAM**: total requests equal **8 vCPU + 16Gi** before system overhead. After profiling, if evidence justifies reducing CPU requests to **500m**, total CPU requests drop to **4 vCPU**. Real dollar savings appear only if the app maintains latency/throughput and billing or node bin-packing actually reflects the lower requests.

### 3.2. Reference Manifest

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: checkout-api
  namespace: checkout
spec:
  replicas: 3
  selector:
    matchLabels:
      app: checkout-api
  template:
    metadata:
      labels:
        app: checkout-api
    spec:
      terminationGracePeriodSeconds: 45
      containers:
        - name: app
          # Replace with a real verified image digest.
          image: asia-southeast1-docker.pkg.dev/PROJECT/REPO/checkout-api@sha256:ACTUAL_DIGEST
          ports:
            - name: http
              containerPort: 8080
          resources:
            requests:
              cpu: "500m"
              memory: "1Gi"
            limits:
              memory: "1Gi"
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 15
~~~

This is an **illustrative manifest**, not ready to run verbatim: it requires a real image digest, live Java health endpoints, namespace, and permissions. In some environments omitting CPU limits prevents CFS throttling, though only when isolation/quota policies allow it; Autopilot may enforce or adjust limits per ComputeClass.

**For JVMs:** measure **heap + non-heap + direct buffers + thread stacks + native memory**. Setting memory limit equal to heap size risks OOMKilled. Load-test and observe p99 latency and GC pauses before shrinking memory requests or limits. Google Cloud notes VPA is often unsuitable for automated JVM memory sizing due to how JVM memory usage behaves—always combine with application profiling.

### 3.3. Choosing New Values

1. Measure peak/percentile usage for each workload over a representative cycle.
2. Separate steady-state load from cold starts, batch spikes, and incidents.
3. Choose requests with enough **headroom** for autoscaling startup lag per SLO policy.
4. Test memory limits including JVM/OS overhead; watch for OOMs, throttling, and evictions.
5. Roll out incrementally, monitor, and then expand.
6. If metrics regress, roll back the Pod template/IaC—never slash limits in bulk.

Never treat **100% utilization** as a mandatory goal. Headroom is essential for bursts, node maintenance, Pod rescheduling, and capacity provisioning delays.

## 4. Four Autoscaling Mechanisms Acting on Different Layers

| Mechanism | What it changes | Signal / trigger | Watch out for |
|---|---|---|--- |
| **HPA** (Horizontal Pod Autoscaler) | Number of **Pod replicas** | CPU, memory, custom/external metrics | Metric availability, min/max bounds, cooldown |
| **VPA** (Vertical Pod Autoscaler) | **Requests/limits** per container | Historical resource usage | May recreate Pods; conflicts with HPA on the same metric |
| **Cluster Autoscaler** | Number of **nodes** in a Standard pool | Pending/unschedulable Pods by requests, node consolidation | Min/max, PDBs, affinity, local storage, capacity |
| **Node pool auto-creation** | New **node pools** tailored to workloads | Pod specs, ComputeClasses/hardware constraints | Version support, quotas, pool count, fragmentation |

~~~mermaid
flowchart TD
    LOAD["Traffic / queue rises"] --> HPA["HPA increases replicas"]
    HPA --> PENDING["New Pods need scheduling"]
    PENDING --> CA["Cluster Autoscaler\nadds nodes if short on space"]
    CA --> READY["Pods Ready / serving"]
    HIST["Usage history"] --> VPA["VPA recommends requests"]
    VPA -. "Update requests after testing" .-> PENDING
    CLASS["ComputeClass + node pool auto-creation"] --> CA
~~~

On Autopilot, GKE manages nodes per mode and ComputeClass, so never apply Standard node pool adjustment steps mechanically to Autopilot.

### 4.1. HPA Calculates Against Requests, Not CPU Limits

For HPA CPU utilization, the ratio is typically **CPU usage / CPU request**. If a Pod uses 400m against a 500m request → 80%; with a 60% target, HPA proposes scaling up replicas (adjusted by tolerance, stabilization, and missing metrics).

Intuitive single-metric formula:

\[
\text{desired replicas} \approx
\left\lceil\text{current replicas}\times
\frac{\text{current utilization}}{\text{target utilization}}\right\rceil
\]

The actual controller also factors in readiness, missing metrics, and scaling policies. Cutting CPU request from 1000m to 500m without changing actual usage **raises HPA utilization**, prompting HPA to add more Pods. That is why shrinking a request never guarantees a lower bill by itself.

### 4.2. VPA and HPA Can Conflict

VPA alters CPU requests; HPA uses usage/request ratios to choose replica counts. If both independently adjust the **same CPU or memory metric**, they can oscillate against each other.

Safe practices:

- Run **VPA in `Off` mode** to collect recommendations and review across at least one full traffic cycle.
- With CPU-based HPA, enable automated VPA adjustments only via supported GKE coordination features such as **HPA rightsizing with VPA (Preview)** or multidimensional autoscaling after testing.
- Or use VPA on workloads that do not run HPA on the same metric.
- HPA can pair with VPA when HPA scales on suitable **custom/external metrics**, though monitoring is still required.
- For JVMs, prioritize app-level memory profiling before trusting automated request changes.

### 4.3. Cluster Autoscaler Does Not Look Directly at "Idle CPU"

A node with low active CPU usage hosting high-memory-request Pods may **still be ineligible for scale-down**. Cluster Autoscaler checks whether Pods on that node can move elsewhere without violating PDBs, affinities, taints/tolerations, volumes/topology, requests, or node pool minimums.

Specifically, **never enable standalone Compute Engine autoscaling** on Managed Instance Groups backing GKE node pools: two competing controllers will fight GKE Cluster Autoscaler.

## 5. Controlled Lab: HPA, Requests, and Namespace Budgets

**Prerequisites:** use an authorized lab cluster where namespace **`checkout`** and Deployment **`checkout-api`** already exist with valid images and health endpoints. Never apply these changes in production without load tests, owner approval, and a rollout plan.

### 5.1. Illustrative HPA (`autoscaling/v2`)

~~~yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: checkout-api
  namespace: checkout
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: checkout-api
  minReplicas: 2
  maxReplicas: 8
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 65
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 300
    scaleUp:
      stabilizationWindowSeconds: 0
~~~

The bounds **2–8** are technical HPA limits, **not a financial budget**. If each Pod declares a large CPU request, `maxReplicas=8` can still force new nodes. Conversely, too low a `maxReplicas` causes latency spikes even when the cluster has spare capacity.

Check before applying:

~~~bash
kubectl config current-context
kubectl get deployment checkout-api -n checkout
kubectl get hpa -n checkout
kubectl apply --dry-run=client -f hpa.yaml
~~~

After approval, if **`hpa.yaml`** holds the manifest above in the right context:

~~~bash
# MODIFIES: creates/updates the lab HPA.
kubectl apply -f hpa.yaml

# READ-ONLY; requires a working metrics API.
kubectl get hpa checkout-api -n checkout -w
kubectl describe hpa checkout-api -n checkout
kubectl top pods -n checkout --containers
~~~

Without traffic or CPU load, HPA **will not scale up** to 8 automatically. To observe scale-up, run a **bounded load test** in the authorized lab, tracking p95 latency and error rates—never point an unbounded stress script at production.

### 5.2. ResourceQuota as a Capacity Boundary

~~~yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  name: checkout-budget-guard
  namespace: checkout
spec:
  hard:
    requests.cpu: "8"
    requests.memory: 16Gi
    limits.memory: 24Gi
    pods: "30"
~~~

`ResourceQuota` blocks new Pods once aggregate requests/limits hit the cap, keeping one namespace from starving the cluster. It **does not cap your total cloud bill**: networking, disks, node overhead, cluster fees, and resources outside the namespace still accrue charges.

**Risk:** an overly tight quota can block rolling updates and legitimate HPA scale-ups; leave headroom for **`maxSurge`, crash recovery, and batch peaks**. Edit quotas only after auditing active workloads.

### 5.3. Experiment Sequence

1. **Baseline:** snapshot Deployment, HPA, events, CPU/memory usage, Cloud Billing, and SLOs.
2. **Predict:** calculate new requests, peak replicas, and required node capacity.
3. **Dry-run:** validate manifests and admission policies.
4. **Low-risk rollout:** canary or a single lab namespace/workload—never flip all Deployments at once.
5. **Load test:** verify scale-up, readiness, p95 latency, retries, and downstream DB limits.
6. **Scale down:** stop load, watch HPA stabilization, then observe node autoscaler consolidation.
7. **Reconcile:** compare node-hours/Pod-request-hours, recorded Cloud Billing, and errors.
8. **Roll back** if SLOs degrade, or commit to IaC/GitOps if goals hold.

Changing HPA targets and editing CPU requests are **coupled changes**; apply them in separate steps so cause and effect stay clear.

## 6. Optimizing Node Pools in GKE Standard

### 6.1. Why "Low CPU Usage" Isn't Enough to Remove a Node

Suppose 6 nodes share a 4 vCPU / 16 GiB machine type: theoretical total **24 vCPU + 96 GiB**, with lower allocatable capacity after system reservations. If total Pod requests are 10 vCPU and 60 GiB RAM, CPU looks heavily underutilized while memory and topology leave very little true consolidation room.

Evaluate **bin packing** across CPU, memory, Pod/IP limits, topology, storage, taints, affinities, and PDBs together. Never compute **10/24 vCPU ≈ 42%** and assume you can cut 58% of node costs.

### 6.2. Node Pool Autoscaling and Min/Max Bounds

~~~bash
# READ-ONLY: node pools and cluster settings.
gcloud container node-pools list \
  --project="$PROJECT_ID" --cluster="$CLUSTER" \
  --location="$LOCATION"

gcloud container node-pools describe "NODE_POOL_NAME" \
  --project="$PROJECT_ID" --cluster="$CLUSTER" \
  --location="$LOCATION" --format=yaml
~~~

On Standard:

- Choose **`min` nodes** large enough to survive incidents and maintenance; setting `min` too high leaves idle nodes running.
- **`Max` nodes** should accommodate peak demand, yet never replace Cloud Billing Budgets and Alerts.
- Cluster Autoscaler scales up when **Pods are unschedulable** and scales down when Pods can move safely.
- Node pools in **different zones, GPU types, or CPU architectures** do not automatically accept arbitrary Pods; scheduling constraints must match.
- Some **newer GKE versions** support **scaling Standard clusters down to 0 nodes when idle** under specific prerequisites; never assume older Standard clusters scale to zero automatically. Verify GKE version and feature support before relying on overnight scale-to-zero for dev clusters.

Example updating cluster autoscaling profile **only after approval**:

~~~bash
# MODIFIES INFRASTRUCTURE — example only, never copy blindly to prod.
gcloud container clusters update "$CLUSTER" \
  --project="$PROJECT_ID" --location="$LOCATION" \
  --autoscaling-profile=optimize-utilization
~~~

The **`optimize-utilization`** profile packs Pods tighter and scales down more aggressively than **`balanced`** (Standard default). It can increase Pod rescheduling churn and scale-up wait times; monitor readiness, PDBs, and SLOs after switching. Never flip profiles assuming "it must save money" without inspecting real cluster usage.

### 6.3. Node Pool Auto-Creation and ComputeClass

**Node pool auto-creation** lets GKE Standard provision tailored node pools matching requests or accelerators instead of pre-creating every pool manually. Two primary approaches exist:

- **Workload-level ComputeClass** (recommended on supported GKE versions): Pods select a ComputeClass and GKE creates matching pools automatically.
- **Cluster-level node auto-provisioning:** cluster-wide configuration with its own resource limits and version rules.

Per current docs, on GKE **1.33.3-gke.1136000+**, ComputeClass enables node pool auto-creation without needing cluster-level node auto-provisioning. Older releases require the cluster-level setting. This is **version-dependent**—never copy policies across clusters without checking versions.

When using multiple ComputeClasses or node pools, watch out for fragmentation: pools serving only 1–2 Pods or overly narrow affinities block scale-down and inflate costs. Selectors and taints provide isolation, not free bin-packing.

### 6.4. Balancing Packing and Availability

| Adjustment | Benefit | Risk |
|---|---|---|
| Fewer node pools, right-sized machines | Tighter bin-packing | Less workload isolation or hardware specialization |
| Multi-zone node pools | Higher zone fault tolerance | Higher cross-zone traffic and overhead |
| Strict anti-affinity | Prevents co-locating replicas on one node | Can strand idle nodes |
| `TopologySpreadConstraints` | Even replica spread across nodes/zones | Can block scheduling if constraints are too rigid |
| PDBs | Limits voluntary disruption | Blocks drains/scale-downs if overly tight |
| Node auto-creation | Matches hardware to workload demand | Pool sprawl and churn if workloads fragment |
| `optimize-utilization` | Cuts idle nodes faster | More scale-down churn and slower scale-up |

Never disable a **PDB** or cut critical service replicas just to force the autoscaler to remove nodes. Optimize requests and scheduling constraints while keeping rollout headroom intact.

## 7. Compute Choices: On-Demand, Spot, CUDs, and Autopilot

### 7.1. Choosing by Disruption Tolerance

| Workload type | Option to evaluate | Prerequisites |
|---|---|---|
| Critical always-on APIs | On-demand / CUDs for baseline | Multi-zone, readiness, SLOs, PDBs |
| Retryable batch processing | **Spot nodes / Spot Pods** | Checkpointing, retries, idempotency, graceful shutdown |
| Queue workers with large bursts | HPA/KEDA-compatible + Spot for burst capacity | Never store queue durability inside Pods alone |
| Spiky load with minimal node ops | Autopilot general-purpose | Verify Pod-based vs. node-based billing |
| GPU inference/training | Matching ComputeClass/hardware | Optimize accelerator utilization, quotas, images, batch size |
| Steady long-term baseline | CUDs or appropriate commitments | Accurate baseline forecast; never buy commitments for peak |

Spot VMs/Pods carry **lower prices** yet can be preempted at any time with none of On-demand's availability guarantees. On Autopilot, Spot Pods are managed on Spot VMs; on Standard, node pools or ComputeClasses can opt into Spot per config. Never place a primary database or disruption-intolerant payment service on Spot purely for lower unit prices.

### 7.2. Illustrative Spot Manifest

On **Autopilot** using supported Spot Pod selection, add to the Pod template:

~~~yaml
spec:
  template:
    spec:
      nodeSelector:
        cloud.google.com/gke-spot: "true"
      containers:
        - name: worker
          image: asia-southeast1-docker.pkg.dev/PROJECT/REPO/worker@sha256:ACTUAL_DIGEST
          resources:
            requests:
              cpu: "500m"
              memory: "1Gi"
~~~

This is a **Pod template snippet**, not a complete Deployment. Check GKE/ComputeClass docs for your cluster; Autopilot injects matching Spot taints/tolerations automatically, whereas Standard requires a compatible Spot node pool or ComputeClass plus matching scheduling rules.

Applications must handle **`SIGTERM`**, checkpoint progress, and retry safely—never assume a job will always finish inside the preemption notice window.

### 7.3. CUDs, Reservations, Architecture, and Image Versions

- **Committed Use Discounts (CUDs)** lower bills for predictable steady baselines under contract, yet financial obligations continue even if workload demand drops. Never commit for unverified short-term peaks.
- **Reservations** assure zonal capacity under eligibility terms without making resources free; inspect billing and GKE consumption rules.
- Compare **E2/N2/C4/ARM-based** families by workload CPU:memory ratio and benchmarked throughput—not just list price per vCPU.
- When migrating to ARM64, verify **multi-arch** container images, Java native/JNI libraries, and dependencies have compatible builds.
- Measure **cost per transaction** and SLOs after changing machine families rather than comparing hourly node rates alone.

## 8. Costs Beyond CPU and RAM

| Cost source | How to spot it | Remediation |
|---|---|---|
| Unused **`LoadBalancer` Services** | List Services and Google Cloud forwarding rules | Delete orphaned Services by owner; avoid deleting shared LBs |
| Stranded **PVCs/PVs** after workload deletion | PVC/PV reclaim policy, disk list, Billing | Confirm backups, owners, and retention before deleting |
| **Cross-zone/region traffic** | Network egress SKUs, topology metrics | Co-locate chatty tiers where safe without breaking HA |
| **Cloud NAT / external IPs** | NAT metrics, IP address inventory, SKUs | Optimize topology/IPs without breaking image pulls |
| **Bloated container images** | Artifact Registry storage and pull volume | Multi-stage builds, slim base images, digest cleanup |
| **High log verbosity / metric cardinality** | Logging ingestion, custom metrics | Filter noisy debug logs, cap label cardinality, keep audit trails |
| **GKE system / DaemonSet overhead** | Per-node allocatable and DaemonSet requests | Never delete critical agents; tune node/pool counts |
| **Idle GPUs / Local SSDs** | Accelerator and device metrics | Restrict specialized hardware strictly to workloads needing it |
| **Always-on dev clusters** | Off-hours node-hours | Scheduled shutdown/scale-down when no dependencies require 24/7 uptime |

A **`ClusterIP`** Service does not provision a Google Cloud L4 load balancer; a **`LoadBalancer`** Service incurs forwarding-rule and IP charges even at zero traffic. **`Ingress`/`Gateway`** resources can provision Application Load Balancers and backend resources. Inventory Google Cloud infrastructure created by controllers—not just Kubernetes objects.

For PersistentVolumes, understand **`reclaimPolicy=Retain/Delete`**, backups, and ownership; never wipe volumes via a blanket search script assuming data is expendable.

## 9. GKE Cost Allocation and Cloud Billing BigQuery Export

In multi-team clusters, total Compute Engine spend alone cannot reveal **which namespace drives the bill**. **GKE cost allocation** (on supported clusters/modes) tags Cloud Billing records with cluster, namespace, and workload metadata, though it does not cover every SKU or compute per-request cost directly.

### 9.1. Check Before Enabling

~~~bash
gcloud container clusters describe "$CLUSTER" \
  --project="$PROJECT_ID" --location="$LOCATION" \
  --format="yaml(costManagementConfig)"
~~~

On eligible **Standard** clusters, an administrator can enable it:

~~~bash
# MODIFIES CLUSTER — run ONLY when approved.
gcloud container clusters update "$CLUSTER" \
  --project="$PROJECT_ID" --location="$LOCATION" \
  --enable-cost-allocation
~~~

Data may take **up to a few days** to appear in Cloud Billing and does not retroactively allocate historical charges. Do not assume Standard enablement flags and constraints match every Autopilot cluster.

### 9.2. Allocation Labels

| Label in billing export | Meaning |
|---|---|
| **`goog-k8s-cluster-name`** | Cluster name |
| **`k8s-namespace`** | Namespace |
| **`k8s-workload-type` / `k8s-workload-name`** | Workload kind and name |
| **`k8s-label/KEY`** | Supported Kubernetes labels |
| **`kube:unallocated`** | Unallocated cluster capacity not claimed by workloads |
| **`kube:system-overhead`** | Node capacity reserved for system overhead |

Values like **`goog-k8s-unsupported-sku`**, **`goog-k8s-unknown`**, or null should be reported separately. An unattributed row **is not free**. PVs/PVCs and certain workload types have allocation caveats. GKE cost allocation can also increase BigQuery export row volume and storage fees across many namespace/label combinations.

### 9.3. SQL: Net Cost by Namespace

Use a configured **Cloud Billing detailed export** with BigQuery read permissions. Replace project, dataset, table, and dates. Querying incurs BigQuery scan fees.

~~~sql
-- READ-ONLY. Avoid directly UNNESTing labels in FROM to prevent duplicating cost rows.
WITH bill_rows AS (
  SELECT
    project.id AS project_id,
    COALESCE(
      (SELECT l.value FROM UNNEST(labels) AS l
       WHERE l.key = 'goog-k8s-cluster-name' LIMIT 1),
      'unattributed'
    ) AS cluster_name,
    COALESCE(
      (SELECT l.value FROM UNNEST(labels) AS l
       WHERE l.key = 'k8s-namespace' LIMIT 1),
      'unattributed'
    ) AS namespace,
    cost + COALESCE(
      (SELECT SUM(c.amount) FROM UNNEST(credits) AS c), 0
    ) AS net_cost
  FROM `YOUR_BILLING_PROJECT.YOUR_DATASET.gcp_billing_export_resource_v1_XXXX`
  WHERE usage_start_time >= TIMESTAMP('2026-11-01')
    AND usage_start_time < TIMESTAMP('2026-12-01')
)
SELECT project_id, cluster_name, namespace,
       ROUND(SUM(net_cost), 2) AS net_cost
FROM bill_rows
GROUP BY project_id, cluster_name, namespace
ORDER BY net_cost DESC;
~~~

**Explanation:** scalar subqueries extract labels and sum credits per billing row without multiplying rows across multiple labels. **`credits.amount`** can be negative. Taxes, adjustments, and invoice cycles follow specific semantics—reconcile invoices using the **Cost table** and exact invoice month. Pair net cost with throughput/request counts over the same window to measure unit efficiency.

Never embed user IDs or transaction IDs into Kubernetes Pod labels for cost attribution: high cardinality bloats Cloud Billing exports.

### 9.4. Minimal FinOps Dashboard

| KPI | How to compute |
|---|---|
| Cost per successful request/job | Net workload cost / successful requests or jobs over same window |
| Node-hours | Total VM node hours by pool and machine type |
| Requests / allocatable | Total CPU or memory requests / node allocatable |
| Unallocated share | Unallocated cost / total scoped cluster cost |
| Scaling health | Pending Pods, HPA/CA errors, scale-down blockers |
| Reliability | p95/p99 latency, 5xx rate, OOMs, retries |

**Requests/allocatable is not actual utilization.** Track CPU and memory ratios separately instead of collapsing them into one combined percentage.

## 10. Rollback-Safe Optimization Runbook

~~~mermaid
flowchart TD
    B["Baseline: Billing + usage + SLOs"] --> D["Pick one measurable hypothesis"]
    D --> P["Check Pods, nodes, PDBs, and rollback"]
    P --> C["Canary/lab change"]
    C --> V{"Do SLOs and efficiency pass?"}
    V -- "No" --> R["Roll back, document root cause"]
    V -- "Yes" --> E["Roll out via IaC/GitOps"]
    E --> M["Measure 7-14 days, reconcile Billing"]
    M --> B
~~~

1. **Prioritize** top high-cost workloads, pools, or SKUs and confirm owners.
2. **Baseline** 7 days or a matching batch cycle: usage percentiles, requests, events, Billing, and SLOs.
3. **Hypothesis:** define a specific, testable change, e.g., trimming CPU requests 1000m → 600m improves packing while keeping p95 latency within SLO.
4. **Guardrails:** canary scope, PDBs, pinned image digests, IaC versioning, and rollback path.
5. **Change one variable at a time**—never simultaneously alter CPU requests, HPA targets, node pools, and topology.
6. **Verify** scale-up, scale-down, OOMs, retries, latency, and job completion.
7. **Reconcile** cost/request or cost/job at comparable traffic after billing lag settles.
8. **Finalize or roll back** and record results in the change ticket.

Minimal change-ticket template:

~~~text
WORKLOAD / OWNER / PROJECT / CLUSTER:
HYPOTHESIS:
BASELINE_WINDOW:
CURRENT_REQUESTS / PROPOSED_REQUESTS:
HPA / VPA / NODE_POOL_SETTINGS:
SLO_GUARDRAILS: p95, 5xx, OOM, Pending Pods
ROLLBACK: GitOps revision + image digest
COST_METRIC / TRAFFIC_WINDOW:
RESULT / APPROVER:
~~~

## 11. Diagnosing Why Costs Aren't Dropping

| Symptom | Common cause | What to check |
|---|---|---|
| Low CPU usage, nodes don't shrink | High memory requests, PDBs, pool `min`, affinity, or volumes | `describe nodes`; autoscaler logs |
| Pods stuck **`Pending`** long | Quotas, IP ranges, `max` nodes, hardware/taints | `describe pod`, cluster constraints |
| HPA shows **`unknown` CPU** | Metrics API broken or missing CPU requests | `describe hpa`, metrics server |
| HPA and VPA oscillate | Both adjusting the same metric | VPA mode, HPA metrics |
| Pods scale out, app stays slow | DB pool exhaustion, queues, throttling, cold starts | Tracing, p99, DB metrics |
| OOMKilled after rightsizing | JVM heap + native memory exceeds limit | Pod `lastState`, `logs --previous` |
| Batch finishes, nodes stay up | PDBs, PVs/local storage, DaemonSets, or pool `min` | `get pods -A`, autoscaler visibility |
| Spot batch retries spike | Frequent preemption or scarce capacity | Checkpoint interval, Pod events |
| Bill stays high after cutting replicas | Standard nodes, LBs, disks, IPs, and logs still bill | Billing breakdown by SKU |
| Cross-zone egress climbs | Pod/DB placement and chatty traffic | Network SKUs, zone topology |

~~~bash
# READ-ONLY.
kubectl get pods -A -o wide
kubectl describe hpa checkout-api -n checkout
kubectl describe deployment checkout-api -n checkout
kubectl get pdb -A
kubectl get pvc -A
kubectl get pv
kubectl get events -A --sort-by=.metadata.creationTimestamp
~~~

When nodes refuse to scale down, inspect **Cluster Autoscaler Visibility Logs** in Cloud Logging for `noScaleDown` reasons and blockers. Never delete nodes manually while GKE manages the node pool.

**Example:** 6 nodes sit at 20% CPU usage, yet high-memory Pods plus a PDB with **`minAvailable=6`** block Pod eviction. Dropping the PDB to force scale-down risks breaking SLOs; instead, audit memory requests, node allocatable capacity, topology, and consolidation feasibility.

## 12. Case Study: Java API and Nightly Batch

**Hypothetical context:** a GKE Standard regional cluster runs:

- **`checkout-api`:** 6 replicas requesting 1 vCPU and 2Gi each; HPA CPU target 60%.
- **Nightly batch:** 10 Pods requesting 500m CPU and 1Gi RAM, running a few hours nightly.
- **Node pools:** 3 nearly identical hardware pools with relatively high `min` node counts.
- **Billing:** most spend comes from VM nodes, persistent disks, and network egress.

### 12.1. From Observation to Decision

| Observation | Hypothesis to test | Safety condition |
|---|---|---|
| Java CPU requests exceed representative usage | Lower requests in small steps to tighten packing | p99, GC, OOM, and HPA stability hold |
| Batch reads/writes Cloud Storage | Move retry-safe jobs onto Spot | Checkpointing, idempotency, and job deadlines |
| Fragmented node pools with high `min` | Tune `min` and evaluate auto-creation | PDBs, topology, and surge headroom hold |
| Deleted Pods leave PVCs behind | Inventory disks/snapshots by owner | Verify backups, retention, and `reclaimPolicy` |
| Cross-zone DB traffic drives egress | Evaluate zone-aware locality | Maintain HA and DR guarantees |
| Excessive batch debug logs | Trim low-value verbosity | Preserve audit trails and error diagnostics |

### 12.2. Illustrative Calculation (Not Actual Google Cloud Pricing)

Suppose 12 nodes cost an illustrative **10 units/day/node** and fixed ancillary charges are **50 units/day**. After verifying the workload maintains SLOs on 9 nodes with ancillary fees unchanged:

\[
\begin{aligned}
C_{\text{before}} &= 12 \times 10+50=170\\
C_{\text{after}} &= 9 \times 10+50=140\\
\text{Savings} &= (170-140)/170 \approx 17.6\%
\end{aligned}
\]

Cutting node count by 25% here yields only **17.6% total bill reduction**—before accounting for any Spot retries, egress shifts, logging changes, or CUD adjustments. **Claim real savings only after comparing actual bills at equal traffic.**

### 12.3. Acceptance Criteria

- Cost/request or cost/job drops at comparable traffic.
- p95/p99 latency, error rate, and availability remain inside SLO.
- Batch completes ahead of deadlines and recovers cleanly from Spot preemptions.
- Zero OOMs or prolonged Pending Pods.
- Multi-zone spread, PDBs, IAM, and backup policies remain intact.
- IaC/GitOps commits and dashboards are ready for immediate rollback if needed.

## 13. Exercises and Self-Check Questions

### 13.1. Pick the Right Mechanism

| Scenario | Guided answer |
|---|---|
| API CPU load rises and needs more Pods | HPA |
| Need CPU/memory request recommendations | VPA `Off`/recommendation |
| Standard cluster lacks nodes to schedule Pods | Cluster Autoscaler |
| Need GKE to provision a new pool matching a ComputeClass | Node pool auto-creation |
| Checkpointed batch tolerating interruptions | Spot |
| Steady, predictable long-term baseline | Evaluate CUDs |
| Multi-team cost attribution by namespace | GKE cost allocation / BigQuery export |
| LB/IP charges persist at zero traffic | Inventory LBs, external IPs, forwarding rules |

### 13.2. Calculations

1. A Deployment has 5 Pods requesting **800m** CPU each. What is the total CPU request?
2. An HPA has 4 replicas, current utilization **90%**, target **60%**. Roughly how many replicas does the formula propose?
3. Each Pod uses **300m** CPU; its request drops from **600m** to **300m**. How does HPA utilization change?
4. Daily spend drops from **200 units** to **175 units** at equal traffic and SLOs. What is the percentage savings?
5. Why doesn't 10% actual CPU usage guarantee Cluster Autoscaler can delete a node?

**Answers:** (1) 4 vCPU; (2) roughly 6 replicas before controller constraints; (3) jumps from 50% to 100%, potentially triggering HPA scale-up; (4) 12.5%; (5) due to memory/CPU requests, pool minimums, PDBs, topology/affinity, attached volumes, or inability to reschedule Pods elsewhere.

### 13.3. Design Questions

- Why doesn't cutting CPU requests on **Standard** always lower bills right away?
- On Autopilot, what determines Pod-based vs. node-based billing?
- When do HPA and VPA conflict, and how do you prevent it?
- Is Spot suitable for a primary transactional database? Why or why not?
- Should all **`kube:unallocated`** costs be billed to a single team without an agreed FinOps rule?
- Which metrics prove an optimization actually lowered cost per successful request?

**Answer guidance:** evaluate billing mechanics, scheduler/controller behavior, durability, SLOs, and pre/post usage at equal traffic. Never infer dollar savings from reducing one isolated request number.

## 14. Official Documentation and Checklist

- [GKE best practices: Cost optimization](https://docs.cloud.google.com/kubernetes-engine/docs/best-practices/cost-optimization)
- [GKE pricing](https://cloud.google.com/kubernetes-engine/pricing)
- [Autopilot overview and billing modes](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/autopilot-overview)
- [Autopilot resource requests](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/autopilot-resource-requests)
- [Horizontal Pod autoscaling](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/horizontalpodautoscaler)
- [Vertical Pod autoscaling](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/verticalpodautoscaler)
- [Cluster autoscaler](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/cluster-autoscaler)
- [Node pool auto-creation](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/node-auto-provisioning)
- [GKE cost allocation](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/cost-allocations)
- [Autopilot Spot Pods](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/autopilot-spot-pods)
- [Standard Spot VMs](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/spot-vms)
- [Troubleshoot cluster autoscaler scale-down](https://docs.cloud.google.com/kubernetes-engine/docs/troubleshooting/cluster-autoscaler-scale-down)

**Execution checklist:** verify cluster/context/owners → baseline Billing and SLOs → rightsize requests/limits → configure HPA/VPA → optimize node packing/ComputeClasses → adopt Spot/CUDs safely → audit storage/network/logging → run canary test → measure SLOs and invoices → commit or roll back.

**Connecting to the CLOUD_PROVIDERS_GCP track:** optimizing GKE draws on Compute Engine, IAM/Artifact Registry, VPCs, storage, Cloud Billing, and Cloud Monitoring. The ultimate goal is **sensible cost per successfully completed unit of work**—never trading away availability, security, or recoverability.







