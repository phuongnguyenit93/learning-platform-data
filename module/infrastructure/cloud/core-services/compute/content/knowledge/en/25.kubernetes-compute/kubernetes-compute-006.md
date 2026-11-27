# Horizontal Pod Autoscaler, Vertical Pod Autoscaler, and Node Scaling

In Kubernetes, application serving capacity depends simultaneously on Pod count, the resources each Pod requires, and the number of nodes available to run those Pods. Horizontal Pod Autoscaler (HPA) adjusts replica counts based on load; Vertical Pod Autoscaler (VPA) recommends or updates container CPU and memory requests; and a node autoscaler adds or removes nodes so the cluster has sufficient scheduling capacity. These three mechanisms address three different layers and must be coordinated to avoid scenarios where Pods scale up without nodes, or resource request changes trigger unexpected scaling reactions.

HPA fits when an application can scale horizontally, such as stateless APIs or workers. VPA is useful when container CPU and memory consumption is initially misestimated or shifts over time. A node autoscaler addresses underlying infrastructure capacity when Pods cannot be scheduled due to resource shortages or when nodes sit idle. None of these mechanisms on its own can fix an application that cannot distribute load, severely misconfigured requests, or a saturated downstream dependency.

This lesson explains how the three autoscaling layers operate, how to choose metrics, how to configure and test them, and the critical interactions among HPA, VPA, the scheduler, and node pools. After this lesson, you will be able to:

- Distinguish horizontal Pod scaling, per-Pod resource adjustment, and node scaling.
- Explain how HPA calculates replica counts from metrics and resource requests.
- Understand the VPA recommender, updater, admission controller, and update modes.
- Identify conflicts when both HPA and VPA control CPU or memory.
- Understand how a node autoscaler responds to Pending Pods and scale-in conditions.
- Design requests/limits, metrics, policies, and capacity bounds aligned with SLOs.
- Test scale-up, scale-down, rescheduling, disruption, and cost on a real cluster.

## 1. Three Scaling Layers in Kubernetes

Kubernetes has multiple components participating in capacity adjustment. Distinguish what each mechanism modifies:

| Mechanism | Target Modified | Question It Answers | Example |
|---|---|---|---|
| HPA | Workload replica count | How many Pods are needed to handle current load? | Scale an API from 3 to 10 Pods |
| VPA | CPU/memory requests and optionally limits per policy | How many resources should each Pod be allocated? | Adjust memory request from 512 MiB to 1 GiB |
| Node autoscaler | Number of nodes or node pool size | Does the cluster need more or fewer machines to run Pods? | Add nodes when Pods go Pending due to insufficient CPU |

~~~mermaid
flowchart TD
    M["Metrics and workload status"] --> H["HPA"]
    H --> P["Pod count / replicas"]
    P --> S["Kubernetes scheduler"]
    V["VPA recommender / policy"] --> R["CPU and memory requests"]
    R --> S
    S --> Q{"Can Pod be scheduled?"}
    Q -- "Yes" --> N["Existing nodes"]
    Q -- "No" --> C["Node autoscaler"]
    C --> X["Provision node / node pool"]
    X --> S
    N --> W["App runs and emits metrics"]
    W --> M
~~~

HPA and VPA act on Pod templates or Pod specs; the node autoscaler acts on cluster infrastructure. HPA can create more Pods, but it does not provision nodes itself. A node autoscaler can add nodes, but it does not raise application replicas itself. VPA can increase Pod requests, requiring existing Pods to be recreated or updated in place depending on cluster capabilities; higher requests can also make Pods harder to schedule.

### Foundational Prerequisites

Before deploying autoscaling, ensure:

- Workloads are managed by a Deployment, StatefulSet, or appropriate controller.
- Resource requests are declared for containers; limits are chosen based on policy and application behavior.
- A metrics pipeline is operational and provides sufficiently fresh data.
- Readiness/liveness probes accurately reflect application health.
- Node pools can expand with sufficient capacity, quotas, and suitable instance types.
- Pods can restart or move safely in line with data durability and availability policies.

Autoscaling does not replace high-availability design. Applications still need enough replicas, distribution across failure domains, and downstream dependencies capable of absorbing increased load.

## 2. Resource Requests and Limits as the Foundation of Scheduling

The Kubernetes scheduler uses resource requests to decide which node can host a Pod. A CPU request typically represents the CPU capacity guaranteed in scheduling plans; a memory request represents the memory reserved on a node. Requests are not hard ceilings on runtime usage.

Limits define runtime usage boundaries enforced by the container runtime:

- CPU limits are typically enforced via throttling when a container attempts to exceed its quota.
- Memory limits are harder boundaries; a container can be OOMKilled if it exceeds its limit.

Example:

~~~yaml
resources:
  requests:
    cpu: "500m"
    memory: "512Mi"
  limits:
    cpu: "1"
    memory: "1Gi"
~~~

The container requests 0.5 CPU and 512 MiB for scheduler capacity accounting. It can consume up to 1 CPU per quota and up to 1 GiB memory before risking OOM termination. Actual values should be based on load distribution and peak behavior.

### How Do Requests Affect HPA?

When HPA uses CPU utilization as a percentage of request, CPU usage is divided by the Pod's CPU request. For instance, if a container has a `500m` request and averages `250m` usage, CPU utilization is roughly 50% of request. If the request rises to `1` CPU while usage stays `250m`, utilization drops to roughly 25%.

Therefore, changing CPU requests via VPA alters the signal HPA observes, even when application traffic has not changed. This is a critical reason to be careful when HPA and VPA both manage CPU.

### Requests Too Low or Too High

Requests set too low cause the scheduler to pack too many Pods onto one node, increasing CPU/memory contention and feeding distorted signals to HPA or the node autoscaler. Requests set too high reduce Pod density, inflate node count requirements, and can leave Pods Pending despite low actual usage.

Start by benchmarking under representative load, tracking usage percentiles, and checking peaks. For memory, watch peak working set and leak behavior; for CPU, inspect throttling, latency, and concurrency as well.

## 3. Horizontal Pod Autoscaler (HPA)

HPA is a controller that monitors workload metrics and adjusts the replica count of a scale target, typically a Deployment or StatefulSet. HPA is commonly configured via the `autoscaling/v2` API.

### How HPA Calculates Replica Counts

Given a metric's current value and target value, the core calculation is:

\[
desiredReplicas =
\left\lceil currentReplicas \times
\frac{currentMetricValue}{desiredMetricValue} \right\rceil
\]

For example, a Deployment currently has 4 Pods. Average CPU utilization is 90%, while the target is 60%:

\[
\left\lceil 4 \times \frac{90}{60} \right\rceil
= \lceil 6 \rceil = 6
\]

HPA proposes 6 replicas before applying bounds, tolerance, and behavior policies. The full calculation also accounts for missing metrics, starting Pods, readiness, scale stabilization, and safety conditions.

With multiple metrics, HPA computes the desired replica count for each metric independently and typically picks the largest value so one low metric does not mask demand signaled by another.

### HPA Metric Types

| Metric Type | Source | Example Usage |
|---|---|---|
| Resource | Metrics API | CPU or memory utilization / average value |
| Container resource | Metrics API per container | Application container CPU, ignoring sidecars where appropriate |
| Pods metric | Custom metrics adapter | Average in-flight requests per Pod |
| Object metric | Custom metrics adapter | Metric on a Kubernetes object such as an Ingress or queue proxy |
| External metric | External metrics adapter | Queue backlog, message age, or metrics from outside the cluster |

CPU is easy to start with, but does not fit every workload. Workers may need to scale on queue age; APIs may need requests per Pod; streaming systems may need connection count or consumer lag. Metrics must correlate with processing capacity and update fast enough.

### Metrics Server and Custom Metrics

Metrics Server supplies resource metrics such as CPU and memory to the Kubernetes Metrics API. It is commonly used for resource-utilization-based HPA and `kubectl top`. Metrics Server is not a historical metrics store or a full observability platform.

For custom/external metrics, the cluster needs an adapter to expose metrics into the API HPA queries. For instance, Prometheus Adapter maps Prometheus metrics into custom metrics. Verify metric names, labels, units, aggregation, and API permissions.

If HPA reports missing metrics or fails to retrieve values, inspect the `APIService`, adapter, metrics pipeline, RBAC permissions, and endpoint health before changing targets.

## 4. Configuring HPA with `autoscaling/v2`

Example API Deployment with CPU requests and an HPA targeting 60% average CPU utilization between 2 and 20 replicas:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      containers:
        - name: api
          image: registry.example.com/orders-api:1.4.0
          ports:
            - containerPort: 8080
          resources:
            requests:
              cpu: "500m"
              memory: "512Mi"
            limits:
              cpu: "1"
              memory: "1Gi"
          readinessProbe:
            httpGet:
              path: /ready
              port: 8080
            periodSeconds: 5
            failureThreshold: 3
~~~

~~~yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: orders-api
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: orders-api
  minReplicas: 2
  maxReplicas: 20
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 60
  behavior:
    scaleUp:
      stabilizationWindowSeconds: 0
      policies:
        - type: Percent
          value: 100
          periodSeconds: 60
        - type: Pods
          value: 4
          periodSeconds: 60
      selectPolicy: Max
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
        - type: Percent
          value: 25
          periodSeconds: 60
      selectPolicy: Max
~~~

In this example, HPA scales up faster and scales down more gradually. Scale-down keeps a 5-minute stabilization window and caps the rate of reduction to avoid cutting capacity immediately on brief metric dips. These numbers are illustrative; tune them to Pod startup time, SLOs, load patterns, and node pool capabilities.

### Inspecting HPA

~~~bash
kubectl get hpa
kubectl describe hpa orders-api
kubectl get deployment orders-api
kubectl get pods -l app=orders-api
kubectl top pods -l app=orders-api
~~~

The `TARGETS` column displays current metric values against targets when available. If you see `<unknown>` or metric retrieval errors, check `Events` and the health of the Metrics API/adapter.

## 5. HPA Scale-Up and Scale-Down Behavior

HPA provides `behavior` policies to tune replica change velocity. Common fields:

- `stabilizationWindowSeconds`: observation window to avoid reacting to short fluctuations.
- `policies`: caps change by Pod count or percentage over a time period.
- `selectPolicy`: chooses the largest change (`Max`), smallest change (`Min`), or disables scaling (`Disabled`).

Scale-up usually needs to be responsive to absorb rising load. Scale-down should generally be conservative because new Pods may require warm-up time, while removing replicas increases load on remaining Pods.

### Readiness and Startup

Pods that are not Ready should not receive Service traffic. If a readiness probe fires too early or is overly sensitive, Pods can flap in and out of endpoints. A startup probe helps slow-starting apps by giving containers time to initialize before normal liveness/readiness checks take effect.

HPA has special handling for starting Pods or Pods missing metrics to avoid overly optimistic scaling calculations. Even so, applications need accurate probes and measured startup durations.

### HPA Cannot Scale Beyond Bounds

If replicas hit `maxReplicas` while metrics stay elevated, HPA cannot add more Pods. Alert when approaching or hitting max and consider:

- Raising max if node pools, quotas, and dependencies have capacity.
- Optimizing the application or lowering per-request processing cost.
- Using queues, backpressure, or rate limiting to shed or smooth load.
- Checking whether the metric accurately reflects load.
- Checking whether Pods are Pending due to missing nodes, quotas, or constraints.

## 6. Vertical Pod Autoscaler (VPA)

VPA analyzes container resource history and usage to generate CPU/memory request recommendations. Depending on its update mode and VPA version, it can apply recommendations at Pod creation, trigger Pod replacement, or perform in-place resource updates if supported by the platform.

VPA is typically installed as an add-on rather than a default built-in controller in every cluster. A VPA deployment usually comprises:

- **Recommender:** collects usage and computes resource recommendations.
- **Updater:** identifies Pods needing updates and can evict Pods per policy.
- **Admission controller:** injects recommended requests when new Pods are created.

These components can be deployed via manifests or Helm charts depending on the distribution. Verify VPA compatibility with your Kubernetes cluster version.

### What Does VPA Recommend?

VPA can compute fields such as:

- `target`: recommended request value.
- `lowerBound`: lower bound of the reasonable resource range.
- `upperBound`: upper bound.
- `uncappedTarget`: recommendation before applying resource policy caps.

These values are derived from historical usage, statistical models, and policies. They serve as inputs for tuning, not substitutes for checking SLOs, peaks, and node limits.

### Common Update Modes

Exact mode names and capabilities depend on the VPA version:

| Mode | Behavior |
|---|---|
| `Off` | Generates recommendations only; does not apply them to Pods |
| `Initial` | Applies recommendations when a Pod is created; does not update running Pods |
| `Recreate` | Can evict and recreate Pods to apply updated resources |
| `InPlaceOrRecreate` | Prefers in-place updates if Kubernetes/runtime supports it, otherwise falls back to recreate |

Not every cluster supports every mode. Check the installed CRD and VPA release. When rolling out VPA initially, `Off` mode is usually the safest starting point to observe recommendations before enabling automated changes.

## 7. Configuring VPA in Recommendation-Only Mode

Example VPA tracking the `orders-api` Deployment and outputting recommendations only:

~~~yaml
apiVersion: autoscaling.k8s.io/v1
kind: VerticalPodAutoscaler
metadata:
  name: orders-api
spec:
  targetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: orders-api
  updatePolicy:
    updateMode: "Off"
  resourcePolicy:
    containerPolicies:
      - containerName: api
        controlledResources:
          - cpu
          - memory
        minAllowed:
          cpu: "100m"
          memory: "128Mi"
        maxAllowed:
          cpu: "2"
          memory: "4Gi"
        controlledValues: RequestsOnly
~~~

The policy bounds the request range VPA may recommend and limits control to requests in this example. Exact field names and valid values must be verified against the CRD of the installed VPA version. Do not apply manifests before confirming the CRD exists.

### Inspecting Recommendations

~~~bash
kubectl get vpa
kubectl describe vpa orders-api
kubectl get vpa orders-api -o yaml
~~~

Inspect recommendations per container and compare against current requests, peak usage, OOM events, and throttling. If VPA recommends overly high memory or overly low CPU, review metric history, observation window length, and whether workload traffic was representative.

### When to Keep VPA in Recommendation Mode

- The cluster recently installed VPA and recommendation distributions are not yet understood.
- Workloads have strict SLOs or Pods are expensive to restart.
- Applications hold local state, large caches, or long startup warm-ups.
- Resource changes must be reviewed before rollout.
- Teams want to feed recommendations into GitOps manifests.

Recommendation mode lets operations teams evaluate and apply resource updates in a controlled manner without letting VPA evict Pods automatically.

## 8. Automated VPA Updates and Impact on Pods

When an updating mode is active, VPA can modify container requests. With `Recreate`, Pods can be evicted so the controller creates replacement Pods with updated requests. This creates brief disruptions if replica counts are small or applications do not gracefully handle session recovery.

Before enabling automated updates, verify:

- Sufficient replicas and an appropriate PodDisruptionBudget are in place.
- Readiness probes only mark Pods ready once they can genuinely serve traffic.
- Stateful data is stored durably with safe detach/attach behavior.
- Node pools have enough capacity to schedule Pods with increased requests.
- `ResourceQuota` and `LimitRange` permit the updated values.
- OOMs, throttling, restarts, and latency are monitored.
- A rollback plan exists if recommendations are wrong.

VPA cannot make a small node fit a Pod whose updated request exceeds node allocatable capacity. If requests grow, new Pods may sit Pending until the node autoscaler adds nodes or the workload is adjusted.

### Resource Bounds and QoS

Changing requests/limits can alter a Pod's QoS class:

- `Guaranteed` typically requires CPU and memory requests to equal limits for every container in the Pod.
- `Burstable` applies when requests/limits are present without satisfying `Guaranteed`.
- `BestEffort` applies when no CPU/memory requests or limits are declared.

QoS class influences how the kubelet handles resource pressure and eviction. Never change requests/limits without understanding the impact on QoS, scheduling, and eviction priority.

## 9. Conflicts When Combining HPA and VPA

An important interaction: HPA can scale on CPU utilization measured as a percentage of CPU request, while VPA changes the CPU request. If both control CPU, the denominator of HPA's metric shifts even when actual CPU consumption by the application is unchanged.

Example:

- Pod requests `500m` and uses `300m` CPU: utilization is 60%.
- VPA raises the request to `1` CPU while usage stays `300m`: utilization drops to 30%.
- HPA sees utilization drop and may scale down, even though actual traffic did not decrease.

Conversely, VPA lowering requests can spike utilization and cause HPA to scale out. This creates an unpredictable feedback loop.

### Safer Combinations

1. **HPA on CPU, VPA recommendation-only:** use VPA recommendations to review requests without letting VPA mutate them while HPA depends on CPU utilization.
2. **HPA on custom/external metrics, VPA managing CPU and memory:** HPA relies on request rate, queue depth, or workload metrics unaffected by VPA request changes.
3. **Separate controlled resources:** depending on workload and version, HPA may use CPU while VPA manages only memory; still verify indirect effects.
4. **Separate workloads or controllers:** if an application has components with distinct scaling needs, split them into separate Deployments/workers with explicit policies.

Do not enable CPU-utilization HPA alongside VPA auto-updating CPU requests on the same container without evaluating the interaction. Some configurations explicitly disallow or warn against combining them that way.

## 10. How Node Autoscaling Works

A node autoscaler adjusts node counts or node pool sizes so the cluster has enough capacity to run Pods. A common trigger is when Pods are created but the scheduler finds no eligible node due to insufficient CPU, memory, GPUs, or placement constraints. Pods in `Pending`/`Unschedulable` state can trigger the node autoscaler to provision suitable nodes.

Common implementations:

- **Cluster Autoscaler:** watches unschedulable Pods and underutilized nodes; scales node groups up/down via cloud provider APIs.
- **Node auto-provisioning or Karpenter-style provisioners:** dynamically selects instance types and provisions flexible nodes tailored to Pod requirements, depending on controller and platform.
- **Managed node pool autoscaling:** the cloud provider manages node groups and adjusts min/max or desired node counts through cluster integration.

Not every platform uses the same algorithm or configuration. Identify the exact controller, cloud provider integration, node groups, and permitted capacity types.

### Why Might a Pending Pod Not Trigger Scale-Up?

A node autoscaler only provisions a node if it determines that a new node in configured pools could run that Pod. A Pod may fail to schedule due to:

- Node selectors or node affinity matching no configured node pool.
- Taints lacking a matching toleration.
- A PVC requiring an incompatible zone or topology.
- Pod requests for GPUs or devices unavailable in the node pool.
- `ResourceQuota`, admission policies, or namespace limits blocking Pod creation.
- Pod requests exceeding the maximum capacity of configured node types.
- Node groups already at max size or cloud quotas exhausted.

If no eligible node template exists, blindly adding nodes will not resolve the issue.

## 11. Node Scale-Up and Scale-Down

### Scale-Up

Typical flow:

1. HPA increases Pods or a new workload is deployed.
2. The scheduler attempts to place Pods onto existing nodes.
3. Some Pods cannot be scheduled and receive `Unschedulable` status.
4. The node autoscaler identifies a node group or instance type capable of running the Pods.
5. The cloud provider provisions new machines.
6. Nodes boot, join the control plane, and report `Ready`.
7. The scheduler places Pods onto the new nodes.
8. Pods start and pass readiness before serving traffic.

The total time from HPA's decision until the application gains usable capacity includes metric collection delay, Pod creation, Pending detection, machine provisioning, node boot, image pulls, and app warm-up. If traffic spikes arrive faster than this cycle, maintain baseline headroom or use scheduled scaling.

### Scale-Down

The node autoscaler can remove empty or underutilized nodes if Pods running on them can move to other nodes. Before deleting a node, the controller evaluates:

- Can Pods be safely evicted?
- Do PodDisruptionBudgets permit the disruption?
- Are any Pods using local storage or node-bound data?
- Do Pod affinity/anti-affinity or topology constraints prevent relocation?
- Does the node host DaemonSets, system Pods, or immovable workloads?
- Is scale-down disabled or annotated as blocked on the node?

Scale-down is normally slower and more conservative than scale-up to prevent constant churn. Monitor drained node counts, drain durations, and Pods turning Pending after node removal.

## 12. Configuring and Inspecting the Node Autoscaler

Cluster Autoscaler is typically configured with min/max sizes per node group and cloud provider integration. Exact flags depend on the platform; do not copy flags from another environment without verifying versions.

Details to verify:

- Which node groups are allowed to scale and their min/max sizes.
- Instance types, CPU architectures, GPUs, zones, and capacity types.
- Cloud quotas, subnet IP space, and provisioning limits.
- Node allocatable resources after subtracting system/DaemonSet overhead.
- Labels, taints, and topology of each node pool.
- Scale-down rules, unneeded duration thresholds, and disruption limits.

Basic inspection commands:

~~~bash
kubectl get nodes -o wide
kubectl describe node <node-name>
kubectl get pods -A --field-selector=status.phase=Pending
kubectl describe pod <pod-name>
kubectl get events -A --sort-by=.lastTimestamp
~~~

For Cluster Autoscaler, check controller logs and events related to scale-up/scale-down. For other provisioners, inspect that controller's logs, configuration objects, and events. Never conclude the node autoscaler is broken solely from Pending status; read scheduler events to see the exact reason.

## 13. Combining HPA, VPA, and Node Autoscaler

A common coordination sequence:

1. Request rate rises.
2. HPA increases replicas.
3. The scheduler looks for space for new Pods.
4. If capacity is lacking, the node autoscaler adds nodes.
5. Pods are scheduled, start up, and become Ready.
6. VPA continues analyzing usage to recommend appropriate requests.

~~~mermaid
sequenceDiagram
    participant Load as Application load
    participant HPA as HPA
    participant S as Scheduler
    participant NA as Node autoscaler
    participant Cloud as Cloud provider
    participant VPA as VPA
    Load->>HPA: Metrics increase
    HPA->>S: Increase Pod count
    S-->>NA: Pods unschedulable
    NA->>Cloud: Request matching node
    Cloud-->>NA: New node provisioned
    NA-->>S: Node Ready
    S->>S: Schedule Pods
    VPA->>VPA: Observe usage and update recommendations
~~~

HPA can scale out faster than a node autoscaler can provision nodes. Pods sitting Pending for a few minutes may be expected transient behavior, yet still require monitoring. If wait times breach SLOs, retain spare capacity or shorten node startup time.

### VPA and Node Capacity

When VPA raises requests, Pods may no longer fit on their current nodes. If VPA uses `Recreate`, new Pods with higher requests can stay Pending and trigger the node autoscaler. Conversely, VPA lowering requests can allow tighter bin packing and enable node scale-down.

This is a potential benefit, though it can also cause churn if recommendations shift frequently. Constrain `minAllowed`/`maxAllowed`, review resource policies, and enforce stabilization windows before applying updates.

### Avoiding Uncontrolled Feedback Loops

- HPA scales Pods on CPU utilization.
- VPA increases the CPU request.
- CPU utilization drops even though usage is unchanged.
- HPA scales down.
- Fewer Pods raise load per remaining Pod.
- HPA scales back up.

To avoid this, drive HPA with metrics independent of VPA-adjusted requests, or run VPA in recommendation-only mode when HPA uses CPU utilization.

## 14. PodDisruptionBudget and Pod Mobility

Node scale-down, VPA recreate, and node maintenance can all trigger evictions. A PodDisruptionBudget (PDB) limits how many Pods can undergo voluntary disruption at one time.

Example:

~~~yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: orders-api-pdb
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: orders-api
~~~

This PDB requires keeping at least two Pods available during voluntary disruptions. It does not prevent involuntary failures, guarantee new Pods can schedule, or replace replicas, readiness probes, or stateful design. An overly strict PDB can block node autoscaler scale-down.

For workloads with local storage, StatefulSets, single replicas, or strict anti-affinity, verify migration paths before enabling automatic scale-in.

## 15. Designing Resource Requests and Bounds for Multi-Layer Autoscaling

Requests are a shared input across the scheduler, HPA utilization, and VPA. Manage them as part of your capacity contract.

### A Practical Workflow

1. Measure CPU/memory per container under baseline and peak load.
2. Choose initial requests sufficient for scheduler placement and sensible HPA utilization math.
3. Set limits per policy and load tolerance; avoid overly low CPU limits causing throttling.
4. Run VPA in `Off` mode to observe recommendations.
5. Compare recommendations against usage, OOMs, throttling, and SLOs.
6. Update manifests via GitOps or test controlled update modes.
7. Verify updated Pods can schedule on existing node pools.
8. Confirm the node autoscaler provisions suitable nodes when capacity runs short.

### Be Careful with Memory

Memory cannot be compressed or borrowed flexibly like CPU in most cases. When a container exceeds its memory limit, the kernel may OOM-kill it. Memory requests set too low allow the scheduler to overcommit nodes; under memory pressure, the kubelet may evict Pods by QoS and priority.

VPA memory recommendations should consider peak working set, startup spikes, caches, heaps, and observation windows. Do not use a low average to set requests for spiky applications.

### CPU Throttling

CPU limits can throttle containers even when nodes have spare CPU capacity, depending on CFS quota configuration. If latency climbs while CPU usage never approaches node capacity, inspect throttling metrics before adding replicas. Adding Pods can mask CPU-limit throttling while inflating overhead.

## 16. End-to-End Example: API Load Spike on a Kubernetes Cluster

An API has a baseline load of 100 requests/second and peaks at 600 requests/second. Benchmarks show each Pod safely handles around 100 requests/second with p95 latency under 200 ms. Each Pod requests `500m` CPU and `512 MiB` memory. Nodes in the pool provide 4 CPUs and 16 GiB memory allocatable after system overhead.

### Initial Design

- HPA `minReplicas = 2`, `maxReplicas = 12`.
- HPA scales on requests per Pod or benchmarked CPU utilization.
- VPA runs in `Off` mode during observation to surface request recommendations.
- The node autoscaler manages the node pool with min/max aligned to quotas.
- A PDB preserves the minimum required Pods during drains.
- Readiness probes only route traffic to Pods after API warm-up finishes.

At 600 requests/second peak load, raw capacity math requires 6 Pods. The team keeps additional headroom to survive one Pod failure and request variance. On a 4-CPU node, `500m` CPU requests theoretically fit up to 8 Pods, yet memory, DaemonSets, topology, anti-affinity, and co-located workloads must also fit. Never divide allocatable CPU by request alone and assume a node can hold that many Pods.

### When Load Increases

1. Requests per Pod or CPU rises.
2. HPA raises desired replicas.
3. The scheduler places new Pods if nodes have room.
4. If Pods go Pending due to insufficient CPU/memory, the node autoscaler adds matching nodes.
5. New Pods pass startup/readiness probes and begin serving traffic.
6. VPA continues collecting usage and produces recommendations for review.

### When Load Decreases

1. HPA holds metrics across the stabilization window before scaling down.
2. Replicas decrease gradually per policy.
3. Pods shut down gracefully and stop receiving new requests.
4. The node autoscaler evaluates surplus nodes and drains movable Pods.
5. Nodes are removed only when PDBs, local storage, affinity, and remaining capacity allow.

This example shows HPA, VPA, and node autoscalers do not replace each other. HPA adjusts Pod count; VPA refines per-Pod requests; and the node autoscaler ensures underlying infrastructure can schedule them.

## 17. Troubleshooting Autoscaling

| Symptom | Possible Causes | What to Check |
|---|---|---|
| HPA does not increase replicas | Missing metrics, wrong target, `maxReplicas` reached, or controller error | `describe` HPA, Events, Metrics API, adapter |
| HPA adds Pods but Pods stay Pending | Insufficient nodes, quotas, selector/taint mismatch, or oversized requests | `describe` Pod, scheduler events, node pools |
| CPU HPA oscillates after VPA updates | CPU request changed, shifting utilization percentage | VPA update history, current requests, and HPA metric |
| VPA produces no recommendations | Recommender lacks data, wrong `targetRef`, or component failure | VPA status, recommender logs, CRD, and selector |
| VPA recreate causes outages | Inadequate replicas, PDB, or readiness probes | Pod events, PDB status, readiness, and update mode |
| Node autoscaler does not scale up | No matching node group, max/quota reached, or Pod constraints | Controller logs, unschedulable reasons, cloud quotas |
| Nodes do not scale down | Non-evictable Pods, PDBs, local storage, or affinity | `describe` node/pod, PDBs, scale-down events |
| New node Ready but Pod stays Pending | Node labels/taints, allocatable, or topology mismatch | `describe` node and Pod scheduling events |
| Memory OOM despite VPA raising requests | Limit still low, unobserved peaks, or memory leak | Container limits, OOM events, working set |
| High CPU or latency stays high after scaling | Saturated dependency or bottleneck outside Pods | DB, queues, network, downstream metrics |

### Common Inspection Commands

~~~bash
kubectl get hpa,vpa
kubectl describe hpa <hpa-name>
kubectl describe vpa <vpa-name>
kubectl get nodes
kubectl get pods -A -o wide
kubectl get events -A --sort-by=.lastTimestamp
kubectl top nodes
kubectl top pods -A
~~~

VPA resources and CRDs may not be installed on every cluster; `kubectl get vpa` only works when the VPA API is registered. Node autoscalers also have their own logs and configuration resources depending on the implementation.

## 18. Observability, SLOs, and Cost

To evaluate autoscaling, track both control decisions and real outcomes.

| Layer | Metrics to Monitor |
|---|---|
| Application | p50/p95/p99 latency, successful throughput, error rate |
| HPA | Desired/current replicas, current/target metrics, scaling events |
| VPA | Target/lowerBound/upperBound, current requests, update/eviction events |
| Pod | Pending, startup time, readiness, restarts, OOMKilled, throttling |
| Node | Node count, allocatable, utilization, Pending duration, scaling activity |
| Dependencies | DB connections, queue age, cache, storage, and network |
| Cost | Node-hours, cost per request/job, idle capacity, and warm-up overhead |

A policy might meet a CPU target while still breaching SLOs due to a slow database. Conversely, low CPU does not necessarily warrant scaling down if the workload needs reserve capacity to absorb bursts or survive a zone outage.

### Setting Bounds and Protecting Budgets

- Cap HPA `maxReplicas`.
- Set min/max node counts and allowed instance types per node pool.
- Enforce `ResourceQuota` per namespace and `LimitRange` per workload.
- Alert when HPA hits max, Pods remain Pending too long, or the node autoscaler hits quotas.
- Track VPA eviction/recreation frequency.
- Monitor cross-zone, storage, and IP costs as node pools expand.

Optimize autoscaling for cost per unit of completed work while meeting SLOs, rather than solely minimizing node count.

## 19. Common Mistakes

1. **Treating HPA as a node autoscaler:** increasing replicas with no nodes available to schedule them.
2. **Omitting requests:** HPA CPU utilization cannot be calculated properly and the scheduler lacks capacity signals.
3. **Using VPA auto-updating CPU alongside CPU-utilization HPA:** changing the denominator triggers unexpected HPA reactions.
4. **Enabling VPA update mode too early:** Pods get evicted before recommendations are understood.
5. **Relying solely on CPU:** workloads may be bottlenecked by queues, memory, I/O, or GPUs.
6. **Setting requests too high:** Pods stay Pending and the node autoscaler provisions extra machines unnecessarily.
7. **Setting requests too low:** nodes become overcommitted, driving evictions and higher latency.
8. **Ignoring PDBs:** VPA or node scale-down can disrupt too many Pods at once.
9. **Overlooking max bounds/quotas:** HPA or the node autoscaler cannot expand when needed.
10. **Ignoring startup/readiness times:** new nodes and Pods fail to deliver usable capacity on time.
11. **Failing to protect downstream systems:** scaling Pods overwhelms databases or dependent services.
12. **Skipping scale-in tests:** stateful Pods or long-running jobs get evicted unsafely.

## 20. HPA, VPA, and Node Autoscaling Implementation Checklist

- [ ] Workloads can scale horizontally and maintain appropriate baseline replicas.
- [ ] CPU/memory requests are declared and measured under representative load.
- [ ] Metrics Server is operational for resource metrics.
- [ ] Custom/external metrics adapters are configured if HPA relies on external signals.
- [ ] HPA specifies appropriate metrics, targets, min/max bounds, and behavior policies.
- [ ] VPA CRDs/controllers match the cluster Kubernetes version.
- [ ] VPA starts in recommendation-only mode for observation.
- [ ] No HPA/VPA conflict exists on the same CPU utilization metric.
- [ ] Resource policies set appropriate `minAllowed`/`maxAllowed` and `controlledResources`.
- [ ] The node autoscaler has node pools compatible with Pod requests, labels, and taints.
- [ ] Cloud quotas, subnet IPs, and instance limits support maximum capacity.
- [ ] PodDisruptionBudgets, readiness probes, and graceful shutdown are verified.
- [ ] Stateful/local storage and topology constraints are checked before enabling scale-in.
- [ ] Alerts exist for Pending Pods, `maxReplicas`, node quotas, and scaling failures.
- [ ] Scale-up, scale-down, VPA recommendation/update, and node drains have been tested.
- [ ] SLOs, dependencies, and costs are monitored over a sufficient observation period.

## 21. Applied Exercise

An API Deployment runs 4 Pods. Each Pod declares a `500m` CPU request and `512 MiB` memory request. HPA targets 60% CPU utilization with `maxReplicas` of 20. VPA is running in auto-update mode and recommends increasing the CPU request to `1` CPU. Meanwhile, traffic increases so average actual CPU usage reaches `300m` per Pod. The cluster has little remaining allocatable CPU, so new Pods enter Pending state.

1. Before VPA changes the request, what is the Pod's CPU utilization percentage?
2. After the CPU request increases to `1` CPU while usage stays `300m`, how does utilization change?
3. How might HPA alter its scaling decision when utilization drops?
4. Why does HPA create additional Pods while the node autoscaler is the component responsible for adding nodes?
5. Propose how to coordinate HPA, VPA, and the node autoscaler to prevent unintended feedback loops.
6. Which events and metrics should be inspected to determine why Pods are Pending?

Hint: before the update, `300m` over a `500m` request equals 60%; after the request increases to `1` CPU, `300m` usage equals 30%. If HPA relies on CPU utilization, the drop in signal can reduce desired replicas even though traffic has not decreased. You can switch VPA to `Off` mode to review recommendations or switch HPA to an independent metric such as requests per Pod. HPA adjusts replicas; the scheduler detects insufficient capacity; and the node autoscaler needs a matching node pool to run the Pending Pods. Inspect `kubectl describe pod`, scheduler events, node allocatable capacity, taints/affinity, node pool max limits, and cloud quotas.

## Conclusion

HPA adjusts Pod count based on metrics, VPA recommends or updates per-container resources, and the node autoscaler adds or removes nodes to meet scheduling demand. All three mechanisms must work together through resource requests, metrics, readiness probes, PDBs, node pools, and quota limits. Start by measuring workloads and observing VPA recommendations, choose HPA metrics tied to capacity, maintain headroom for scale-up, and test scale-in carefully. Only by monitoring SLOs, Pending Pods, node capacity, dependencies, and cost together can autoscaling sustain performance without introducing oscillation or wasted capacity.
