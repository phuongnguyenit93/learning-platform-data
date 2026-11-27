# Taints, Tolerations, and Specialized Workload Placement

## 1. Why Control Which Nodes Workloads Run On?

A Kubernetes cluster can consist of multiple node groups with different characteristics: standard CPU nodes, GPU nodes, high-memory nodes, I/O-optimized nodes, interruptible nodes, or nodes dedicated to a specific service group. If the scheduler looks only at free CPU and memory, workloads can land on unsuitable nodes or consume resources needed by another group.

Kubernetes provides several mechanisms to control workload placement. **Taints** mark a node to repel disallowed or unsuitable pods. **Tolerations** declare that a pod accepts one or more taints. **Node selectors and node affinity** let a pod choose nodes with matching labels. **Pod affinity/anti-affinity** and **topology spread constraints** govern relationships between pods and how they are distributed across nodes, zones, or failure domains.

These mechanisms complement one another. A toleration only allows a pod past the barrier created by a taint; it does not select a node by itself. To ensure GPU workloads land on GPU nodes, you need both a toleration for the node's taint and a selector or affinity choosing GPU nodes. To keep dedicated nodes exclusive to one team's workloads, combine taints with matching labels and affinity.

In the **CLOUD_CORE_SERVICES_COMPUTE** module, workload placement directly impacts CPU, memory, GPU, networking, availability, and cost choices. This lesson covers how to use taints, tolerations, and placement rules to run specialized workloads safely, scalably, and cleanly.

After this lesson, learners will be able to:

- Distinguish taints, tolerations, node selectors, node affinity, and pod affinity.
- Explain the three effects: `NoSchedule`, `PreferNoSchedule`, and `NoExecute`.
- Read and write tolerations using `key`, `value`, `operator`, `effect`, and `tolerationSeconds`.
- Dedicate nodes for GPU, high-memory, stateful, batch/Spot, or tenant-specific workloads.
- Coordinate placement with resource requests/limits, topology spread, and autoscaling.
- Handle taints during maintenance, node pressure, eviction, and node failures.
- Investigate why pods enter Pending or get evicted.

## 2. How Do Taints and Tolerations Work?

### 2.1. Taints Attached to Nodes

A taint is a property on a node with the structure:

```text
key=value:effect
```

Example:

```text
workload-class=gpu:NoSchedule
```

This taint marks the node for GPU workloads and requires pods to carry a matching toleration if they want the scheduler to place them on that node.

A taint has three parts:

- `key`: attribute name, such as `workload-class`, `dedicated`, or `capacity-type`.
- `value`: descriptive value, such as `gpu`, `payments`, or `spot`.
- `effect`: behavior applied to pods that do not tolerate the taint.

A node can carry multiple taints at once. A pod must tolerate all taints whose effects block scheduling, unless a toleration is written broadly enough to match multiple taints.

### 2.2. Tolerations Declared on Pods

Tolerations live in `spec.template.spec.tolerations` of a Pod or workload template. They describe which taints the pod accepts.

Example:

```yaml
tolerations:
  - key: workload-class
    operator: Equal
    value: gpu
    effect: NoSchedule
```

This toleration matches the taint `workload-class=gpu:NoSchedule`. It does not force the pod to run on GPU nodes; the pod can still be placed on other nodes if those nodes have no untolerated taints and satisfy other scheduling conditions.

### 2.3. A Taint Is Not a Node Selector

This is the most important rule:

- A taint says: "Any pod that does not accept this condition cannot be placed on this node."
- A toleration says: "This pod accepts that condition."
- A node selector/affinity says: "This pod requires or prefers nodes with these labels."

Therefore, to dedicate nodes for GPUs, attach a taint to keep unrelated workloads out, while also using labels and node affinity so GPU workloads find the right nodes.

## 3. The Three Taint Effects

### 3.1. `NoSchedule`

`NoSchedule` prevents the scheduler from placing new pods onto the node if they lack a matching toleration. Pods already running on the node before the taint was added normally keep running.

Use `NoSchedule` when dedicating nodes to a workload group, for example:

```bash
kubectl taint nodes gpu-node-01 accelerator=nvidia:NoSchedule
```

A pod needs a toleration for `accelerator=nvidia:NoSchedule` to be scheduled onto that node. If the pod lacks the toleration, the scheduler searches for other eligible nodes.

### 3.2. `PreferNoSchedule`

`PreferNoSchedule` is a soft constraint. The scheduler tries to avoid placing non-tolerating pods onto the tainted node, but can still use the node if no better option exists.

Use this effect when you want to prefer reserving nodes for a workload while still allowing capacity sharing when the cluster runs tight. Do not use it when hard isolation or strict compliance is required.

### 3.3. `NoExecute`

`NoExecute` has two effects:

- New pods without a matching toleration will not be scheduled onto the node.
- Already running pods on the node without a matching toleration will be evicted.

A pod can declare `tolerationSeconds` to remain on the node for a grace period after a `NoExecute` taint appears. Once that duration expires, the pod is evicted if the taint is still present.

Example:

```yaml
tolerations:
  - key: node.kubernetes.io/unreachable
    operator: Exists
    effect: NoExecute
    tolerationSeconds: 60
```

The pod tolerates the `node.kubernetes.io/unreachable` taint for up to 60 seconds before taint-based eviction kicks in. This is an example of the behavior; evaluate workload type, storage, and recovery mechanisms before choosing a specific duration.

`NoExecute` is commonly used when handling not-ready or unreachable nodes, or in scenarios requiring pods to be cleared from a node. It has a stronger impact than `NoSchedule`, so test carefully with stateful workloads and long-running jobs.

### 3.4. Comparison Table

| Effect | New Pod Without Toleration | Running Pod Without Toleration | Purpose |
|---|---|---|---|
| `NoSchedule` | Will not be scheduled onto the node | Continues running | Reserve nodes for a workload group |
| `PreferNoSchedule` | Scheduler tries to avoid, may still place | Continues running | Soft preference during allocation |
| `NoExecute` | Will not be scheduled onto the node | Evicted; `tolerationSeconds` can delay | Remove pods from a node or react to node conditions |

### 3.5. Multiple Taints on the Same Node

If a node carries multiple taints, the scheduler evaluates all taints and ignores those tolerated by the pod. Any remaining taints with scheduling-blocking effects influence the decision.

For example, a node has:

```text
accelerator=nvidia:NoSchedule
capacity-type=spot:NoSchedule
```

A pod wanting to run on this node must tolerate both taints. However, the pod still needs matching node affinity or selectors to target nodes with the desired GPU and capacity type.

## 4. Toleration Matching Rules

### 4.1. `operator: Equal`

`Equal` requires key, value, and effect to match the toleration. Example:

```yaml
tolerations:
  - key: dedicated
    operator: Equal
    value: analytics
    effect: NoSchedule
```

This toleration matches `dedicated=analytics:NoSchedule`. It does not match `dedicated=payments:NoSchedule` or `dedicated=analytics:NoExecute`.

If `operator` is omitted, it defaults to `Equal`.

### 4.2. `operator: Exists`

`Exists` only requires the key to be present; no specific value is needed. Example:

```yaml
tolerations:
  - key: capacity-type
    operator: Exists
    effect: NoSchedule
```

This toleration matches taints with key `capacity-type` and effect `NoSchedule`, regardless of value. It is useful when a workload accepts multiple capacity values within the same policy group.

With `operator: Exists`, the `value` field must be empty. If you need to match a specific value, use `operator: Equal`.

Avoid using overly broad `Exists` rules if different values carry distinct security or operational meanings.

### 4.3. Omitting Key or Effect

When `operator: Exists` and `key` is empty, the toleration matches any key; this is a very broad toleration. If `effect` is empty, the toleration matches all effects for the matching key/value.

Wildcard toleration example:

```yaml
tolerations:
  - operator: Exists
```

This allows the pod to tolerate every taint under Kubernetes wildcard rules. Use this only with a clear justification, such as infrastructure DaemonSets that must run on nearly every node. Do not grant wildcard tolerations broadly to regular applications because it weakens placement boundaries.

### 4.4. `tolerationSeconds`

`tolerationSeconds` only applies to the `NoExecute` effect. It specifies how long a pod may stay on a node after the corresponding taint is added.

- `tolerationSeconds` omitted: a pod tolerating `NoExecute` can remain on the node indefinitely while the taint persists.
- Numeric seconds specified: the pod is kept for that duration, then evicted if the taint remains.
- Do not use this field expecting to delay `NoSchedule`; that effect does not evict running pods.

### 4.5. A Pod Can Have Multiple Tolerations

A pod can declare multiple tolerations to accept multiple node groups, such as Spot GPU nodes in a specific zone or nodes labeled dedicated. Every toleration should have a clear purpose and owner. Avoid accumulating stale tolerations after a workload changes architecture.

## 5. Node Labels, Selectors, and Affinity

### 5.1. Labels on Nodes

Labels describe node attributes, for example:

```bash
kubectl label nodes gpu-node-01 accelerator=nvidia
kubectl label nodes gpu-node-01 workload-class=ml
kubectl label nodes gpu-node-01 topology.kubernetes.io/zone=zone-a
```

Labels are used by node selectors, node affinity, topology spread, and various controllers. Apply labels only after attributes are verified; wrong labels can route workloads onto incompatible nodes.

### 5.2. `nodeSelector`

`nodeSelector` is a simple way to require pods to run only on nodes with specific key/value labels.

```yaml
spec:
  nodeSelector:
    accelerator: nvidia
    workload-class: ml
```

Every condition in `nodeSelector` must match. This is easy to read, though it cannot express complex boolean rules or soft preferences.

### 5.3. Required Node Affinity

`requiredDuringSchedulingIgnoredDuringExecution` is a mandatory constraint during scheduling. If no node matches, the pod remains Pending.

```yaml
affinity:
  nodeAffinity:
    requiredDuringSchedulingIgnoredDuringExecution:
      nodeSelectorTerms:
        - matchExpressions:
            - key: accelerator
              operator: In
              values:
                - nvidia
            - key: workload-class
              operator: In
              values:
                - ml
```

Expressions inside the same `nodeSelectorTerm` are combined with AND. Multiple terms inside `nodeSelectorTerms` are combined with OR.

### 5.4. Preferred Node Affinity

`preferredDuringSchedulingIgnoredDuringExecution` is a preference, not a hard requirement. The scheduler adds score points for matching nodes, but can pick another node if overall scoring or other constraints dictate.

```yaml
affinity:
  nodeAffinity:
    preferredDuringSchedulingIgnoredDuringExecution:
      - weight: 80
        preference:
          matchExpressions:
            - key: capacity-type
              operator: In
              values:
                - spot
```

The `weight` field ranges from 1–100. Use preferred affinity when a workload can run on multiple node types but prefers a specific class, such as Spot to save cost.

### 5.5. What Does `IgnoredDuringExecution` Mean?

The node affinity types above are evaluated at scheduling time. If node labels change after a pod is already running, Kubernetes does not automatically evict the pod simply because the affinity rule is no longer satisfied. If runtime changes require reaction, a separate mechanism such as taint-based eviction, a controller, or an operational runbook is needed.

### 5.6. Taints Do Not Replace Affinity

For example, a node has:

```text
accelerator=nvidia:NoSchedule
```

A pod tolerating this taint can be scheduled onto the GPU node, yet it can also land on a standard CPU node if no placement constraint is added. To guarantee the pod only runs on GPU nodes, add a `nodeSelector` or required node affinity for `accelerator=nvidia`.

## 6. Pod Affinity, Anti-Affinity, and Topology Spread

### 6.1. Pod Affinity

Pod affinity lets you place a pod near other pods matching a label, such as placing a helper service or cache worker in the same zone as the application to lower latency. Constraints can be required or preferred.

Do not apply pod affinity just because two workloads belong to the same app. Co-locating them increases correlated failure risk if both land on the same node or zone.

### 6.2. Pod Anti-Affinity

Pod anti-affinity keeps pods of the same group out of the same topology domain. For example, avoid placing two API replicas on the same node to reduce the blast radius of a single node failure.

```yaml
affinity:
  podAntiAffinity:
    preferredDuringSchedulingIgnoredDuringExecution:
      - weight: 100
        podAffinityTerm:
          topologyKey: kubernetes.io/hostname
          labelSelector:
            matchLabels:
              app: orders-api
```

This example prefers spreading pods labeled `app=orders-api` across distinct hostnames. Using `requiredDuringSchedulingIgnoredDuringExecution` may prevent the cluster from scheduling all replicas if the node count is insufficient.

### 6.3. Topology Spread Constraints

Topology spread constraints distribute pods evenly across domains such as zones or hostnames. Example:

```yaml
topologySpreadConstraints:
  - maxSkew: 1
    topologyKey: topology.kubernetes.io/zone
    whenUnsatisfiable: DoNotSchedule
    labelSelector:
      matchLabels:
        app: orders-api
```

`maxSkew: 1` requires the difference in pod count across eligible topology domains not to exceed 1 according to scheduler calculations. With `DoNotSchedule`, new pods remain Pending if distribution cannot be maintained. `ScheduleAnyway` allows scheduling while preferring nodes that reduce skew.

Topology spread differs from anti-affinity: spread governs count skew across multiple domains; anti-affinity expresses avoidance rules between pods. They can be combined, but avoid overly tight constraints that starve schedulability.

### 6.4. Multi-Layer Placement Combinations

A workload may simultaneously require:

- A toleration to enter GPU nodes.
- Required node affinity to select a compatible GPU model.
- Resource request `nvidia.com/gpu` to claim an accelerator.
- Topology spread to distribute replicas across zones.
- Pod anti-affinity to avoid placing two replicas on the same node.
- Separate node affinity or taints for Spot vs. stable capacity.

The scheduler must find a node that satisfies every mandatory condition and has sufficient resources. If any condition fails, pods can stay Pending even if CPU/RAM remain free on other nodes.

## 7. Dedicated Node Placement for GPUs

### 7.1. Applying Labels and Taints

GPU nodes should carry labels describing the accelerator type and taints so unrelated workloads do not occupy them:

```bash
kubectl label nodes gpu-node-01 accelerator=nvidia
kubectl label nodes gpu-node-01 accelerator-model=a100
kubectl taint nodes gpu-node-01 accelerator=nvidia:NoSchedule
```

Label names and values are illustrative. In production, follow consistent naming conventions and leverage information managed by Node Feature Discovery or the cloud node controller where appropriate.

### 7.2. Declaring a GPU Pod

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: image-inference
  labels:
    app: image-inference
spec:
  nodeSelector:
    accelerator: nvidia
    accelerator-model: a100
  tolerations:
    - key: accelerator
      operator: Equal
      value: nvidia
      effect: NoSchedule
  containers:
    - name: inference
      image: registry.example.com/ml/inference@sha256:0123456789abcdef...
      resources:
        limits:
          nvidia.com/gpu: 1
        requests:
          cpu: "4"
          memory: "16Gi"
```

Illustrative manifest. GPU resources are typically advertised via a device plugin or vendor equivalent. The pod must explicitly request the extended resource; tolerating a taint alone does not grant a GPU to a container. The image digest is a placeholder to replace with a real digest.

### 7.3. Verifying Compatibility

Beyond GPU count, verify:

- GPU model and VRAM capacity.
- Driver, CUDA/runtime, and framework versions.
- Required NVLink/PCIe topology or interconnect.
- Sufficient CPU/RAM for data loaders and preprocessing.
- Network throughput for multi-node distributed jobs.
- Storage throughput for loading models and datasets.
- Whether the node device plugin advertises healthy GPUs.

If a pod is Pending, inspect the `nvidia.com/gpu` resource, taints, labels, node affinity, and device plugin events. A node with a physical GPU but a broken plugin may fail to advertise the resource to the scheduler.

## 8. Placing High-Memory, High-CPU, and I/O Workloads

### 8.1. High-Memory Workloads

Workloads such as in-memory analytics, large JVMs, or caches may need high-RAM nodes. Label nodes by memory class and apply a taint to keep small pods from filling dedicated nodes.

```text
instance-class=memory-optimized
workload-class=high-memory:NoSchedule
```

Here `instance-class` is a custom label describing the hardware group; `workload-class=high-memory:NoSchedule` is the actual taint on the node.

Pods need matching tolerations and affinity, plus appropriate memory requests/limits. Using only labels without a taint still lets other workloads consume the node. Using only taints and tolerations without affinity may allow the pod to run on nodes without enough RAM.

### 8.2. CPU-Intensive Workloads

Batch compute, compression, or compilers may require high-core-count nodes. Check CPU generation, core counts, NUMA, clock speeds, throttling, and networking. Resource requests help the scheduler place pods based on expected CPU demand; CPU limits set too low can throttle latency-sensitive workloads.

A taint like `workload-class=compute-intensive:NoSchedule` can reserve nodes for these jobs. Still include affinity targeting the matching label and CPU requests so the scheduler evaluates capacity fit.

### 8.3. Storage- and I/O-Intensive Workloads

Databases, search indexes, or stream processors may require nodes with local NVMe, high-performance network-attached volumes, or specialized networking. Labels should reflect verified capabilities, such as `storage-tier=nvme` or `network-tier=high-throughput`.

Taints keep unsuitable workloads off the node, but they do not guarantee storage performance. Verify CSI drivers, volume topology, IOPS, throughput, zones, and instance limits. Local ephemeral storage requires planning for data loss when a node is replaced.

### 8.4. Latency-Sensitive Workloads

Latency-sensitive workloads may need CPU pinning, topology manager alignment, huge pages, low-latency NICs, or dedicated node pools. Taints and affinity only govern node-level placement; they do not configure CPU Manager, NUMA alignment, or real-time kernels on their own.

Set matching resource specs and runtime policies, benchmark latency percentiles, and avoid excessive overcommitment on dedicated nodes.

## 9. Placing Workloads on Spot/Interruptible Nodes

### 9.1. Separating Node Pools

Interruptible nodes should be clearly marked with labels and taints:

```bash
kubectl label nodes spot-node-01 capacity-type=spot
kubectl taint nodes spot-node-01 capacity-type=spot:NoSchedule
```

Batch workloads can tolerate this taint. Critical workloads without the toleration avoid Spot nodes.

### 9.2. Example Worker with Fallback

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: batch-worker
spec:
  replicas: 5
  selector:
    matchLabels:
      app: batch-worker
  template:
    metadata:
      labels:
        app: batch-worker
    spec:
      tolerations:
        - key: capacity-type
          operator: Equal
          value: spot
          effect: NoSchedule
      affinity:
        nodeAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
            - weight: 80
              preference:
                matchExpressions:
                  - key: capacity-type
                    operator: In
                    values:
                      - spot
      containers:
        - name: worker
          image: registry.example.com/batch/worker@sha256:0123456789abcdef...
          resources:
            requests:
              cpu: "2"
              memory: "4Gi"
```

This example allows workers to run on Spot nodes and prefers Spot. Because affinity is `preferred`, workers can still run on non-Spot nodes if those nodes fit the pod and have no blocking taints. This expresses fallback placement; in production, ensure stable nodes have headroom and workers implement checkpointing/retries.

### 9.3. Handling Node Reclamation

Taints and tolerations do not handle the full interruption lifecycle on their own. You need a node termination handler or cloud provider integration to receive interruption events, cordon/drain the node, stop workers from picking up new tasks, and checkpoint state. Designs must still tolerate sudden node disappearance.

### 9.4. Preventing Critical Workloads from Landing on Spot Accidentally

Do not attach the `capacity-type=spot` toleration broadly across namespaces or service accounts. Use admission policies to restrict which workloads may carry this toleration. Critical workloads should define explicit node affinity or placement policies and stay off Spot unless they tolerate interruptions.

## 10. Dedicating Nodes to Tenants or Service Groups

### 10.1. Tenant Taints and Labels

Example node dedicated to the payments team:

```bash
kubectl label nodes payments-node-01 tenant=payments
kubectl taint nodes payments-node-01 dedicated=payments:NoSchedule
```

Payments pods need both a toleration and required node affinity:

```yaml
spec:
  tolerations:
    - key: dedicated
      operator: Equal
      value: payments
      effect: NoSchedule
  affinity:
    nodeAffinity:
      requiredDuringSchedulingIgnoredDuringExecution:
        nodeSelectorTerms:
          - matchExpressions:
              - key: tenant
                operator: In
                values:
                  - payments
```

The taint keeps unauthorized workloads off the node; affinity ensures pods carrying the toleration only select nodes with the matching tenant label. Adding only the toleration could allow pods to schedule onto non-tenant nodes.

### 10.2. Taints Are Not a Complete Security Boundary

Taints/tolerations are a scheduling mechanism, not an authentication or data isolation boundary. Anyone permitted to create pods can declare a toleration unless an admission policy blocks it. Tenant isolation therefore requires combining:

- RBAC limiting who can create workloads and edit nodes.
- Admission policies restricting tolerations, node selectors, and host-level privileges.
- Separate namespaces, service accounts, and workload identities.
- `NetworkPolicy` or network segmentation mechanisms.
- Pod Security Standards, seccomp, capabilities, and filesystem restrictions.
- Protected node labels and restricted node administration permissions.
- Appropriate storage classes, volume permissions, and encryption.

Do not rely on taints as sole proof that tenant data is isolated.

Additionally, `spec.nodeName` lets a pod specify a node directly and bypass the scheduler's selection phase. Do not grant arbitrary permission to set `nodeName` to tenants or regular workloads; enforce admission policies restricting this field. `NoExecute` can still affect a pod after the kubelet accepts it on the node.

### 10.3. Protected Node Labels

For sensitive placement boundaries, prevent kubelets from self-labeling to spoof node eligibility. Kubernetes includes the Node authorizer and `NodeRestriction` admission plugin to restrict certain kubelet actions. You can use protected label prefixes such as `node-restriction.kubernetes.io/` per Kubernetes documentation and cluster configuration.

Example label:

```text
example.com.node-restriction.kubernetes.io/pci-dss=true
```

Specific prefixes must follow Kubernetes label rules and cluster protection mechanisms. Using prefixed labels does not replace RBAC, admission, and node governance controls.

## 11. System Nodes and DaemonSets

### 11.1. Reserving Nodes for System Components

A cluster can dedicate nodes for ingress, monitoring, logging, storage daemons, or control-plane workloads. A taint such as:

```text
node-role.kubernetes.io/control-plane:NoSchedule
```

keeps regular application workloads off control plane nodes. System components carry corresponding tolerations depending on how the cluster is installed.

Do not arbitrarily delete control-plane or system-node taints just to clear Pending pods. First determine which pods belong there and verify cluster policy.

### 11.2. DaemonSets

DaemonSets typically need to run one pod on every eligible node, such as log collectors, node exporters, CNI, or storage agents. Kubernetes automatically adds certain default tolerations to DaemonSets so they continue operating under specific node conditions; exact behavior depends on taint type and Kubernetes version.

DaemonSets can still be blocked by custom taints. If an agent must run on GPU, Spot, or dedicated nodes, define the matching tolerations. Avoid wildcard tolerations if the agent does not need access to every node.

### 11.3. Checking DaemonSet Coverage

After adding a new taint, verify the desired node count versus ready DaemonSet pods. If a log collector or network agent fails to run on a new node, monitoring and networking may be broken even when application workloads schedule successfully.

## 12. Automatic Taints from Node Conditions

### 12.1. Common Taints

Kubernetes can add taints based on node state, for example:

- `node.kubernetes.io/not-ready`
- `node.kubernetes.io/unreachable`
- `node.kubernetes.io/memory-pressure`
- `node.kubernetes.io/disk-pressure`
- `node.kubernetes.io/pid-pressure`
- `node.kubernetes.io/unschedulable`
- `node.kubernetes.io/network-unavailable`

Exact effects and timing depend on controllers, node conditions, and cluster configuration. These taints keep the scheduler from placing new pods onto unhealthy nodes or trigger handling of running pods when a node loses connectivity.

### 12.2. Do Not Remove Pressure Taints Instead of Fixing Root Causes

If a node has `memory-pressure` or `disk-pressure`, manually removing the taint does not give the node more RAM or disk space. The kubelet/controller can reapply the taint, while new pods may be placed onto an already resource-starved node.

Fix the root cause: reclaim disk space per runbooks, adjust resource requests/limits, expand node capacity, or replace the unhealthy node. Then verify node conditions and taints clear naturally.

### 12.3. `not-ready` and `unreachable` Taints

When a node is NotReady or unreachable by the controller, `NoExecute` taints can trigger eviction after the toleration timeout. Kubernetes typically adds default tolerations for certain `not-ready`/`unreachable` taints onto pods; the default duration is commonly 300 seconds unless configured otherwise. Inspect actual manifests and your cluster version before relying on this number.

For stateful workloads or workloads with local data, eviction and rescheduling can affect consistency. Use storage with appropriate semantics, fencing, and application recovery mechanisms; do not merely extend `tolerationSeconds` to mask disconnected nodes.

## 13. Combining Taints with Autoscaling and Node Pools

### 13.1. Autoscalers Need to Know Node Group Labels and Taints

When a pod is Pending because no matching node exists, the cluster autoscaler can scale up a node group if that group can satisfy the pod's scheduling requirements. Node groups must declare or provide the exact labels, taints, resources, and topology the pod requests.

If a pod tolerates `accelerator=nvidia:NoSchedule` but the GPU node group lacks consistent taint/label configuration, the autoscaler may mispredict schedulability or newly provisioned nodes may still fail placement.

### 13.2. Scale-to-Zero and Specialized Workloads

GPU or high-memory node pools can scale to zero to save cost. When a pod requests a GPU, the autoscaler must identify the matching node group and provision a node. Boot time, driver loading, device plugins, and image pulls can take significant time; account for this in startup latency and deadlines.

If a pod has required affinity for a label absent from the node group, or its toleration fails to match the group's taint, the pod stays Pending even with available quota. Verify node group templates before enabling scale-to-zero.

### 13.3. Coordinating with HPA

HPA increases replicas based on workload metrics; it does not provision nodes. If all matching nodes run out of CPU/GPU or are tainted, new replicas can sit Pending. The cluster autoscaler handles node capacity at a separate layer.

Align replica min/max, node pool min/max, and cloud quotas together. For GPUs, factor in accelerator count, VRAM, zone capacity, and quotas. For Spot pools, keep a stable fallback if workloads cannot tolerate interruptions.

### 13.4. Resource Requests Are Essential Placement Criteria

The scheduler relies on resource requests to evaluate whether a node has enough capacity. A toleration never bypasses CPU, memory, ephemeral storage, or extended resource limits. If a GPU request uses the wrong resource name compared to what the device plugin advertises, the pod remains Pending even when tolerations and affinity match.

Set requests close to actual demand, monitor overcommitment, and track utilization. Requests set too high reduce bin-packing efficiency; requests set too low invite resource contention.

## 14. Node Maintenance and Controlled Eviction

### 14.1. Cordon and Drain

`kubectl cordon` marks a node unschedulable so the scheduler stops placing new pods on it. `kubectl drain` performs controlled pod eviction, respecting objects and policies such as PodDisruptionBudgets (PDBs).

Examples:

```bash
kubectl cordon worker-01
kubectl drain worker-01 --ignore-daemonsets
```

`drain` may require extra flags depending on pod types and storage. Do not add `--delete-emptydir-data` or `--force` without assessing data loss and workload impact. DaemonSets are normally skipped by drain and handled according to appropriate operational guidance.

### 14.2. Tainting to Mark Maintenance

You can add a `NoSchedule` taint before draining to stop new pods from entering the node:

```bash
kubectl taint nodes worker-01 maintenance=true:NoSchedule
```

After maintenance, verify the node is Ready and resources and agents are healthy, then remove the taint:

```bash
kubectl taint nodes worker-01 maintenance-
```

Removing a taint uses the key with a trailing `-`; if multiple taints share the same key with different effects/values, specify the exact taint to remove per `kubectl` syntax and verify the result.

### 14.3. PDBs and Protection Limits

A PDB bounds how many pods can be disrupted by supported voluntary evictions via the Eviction API. A PDB does not prevent sudden node failures, create additional replicas, or guarantee that every form of taint-based eviction is delayed. Size PDBs appropriately for replica count, topology, and application recovery.

If a PDB blocks a drain, check ready replicas, selectors, `minAvailable`/`maxUnavailable`, and whether replacement pods can be scheduled. Do not arbitrarily delete a PDB just to finish maintenance.

### 14.4. `NoExecute` Is Not the Default Drain Tool

Adding `NoExecute` evicts non-tolerating pods and causes faster disruption than a controlled drain. For routine maintenance, cordon and drain generally provide safer control. Use `NoExecute` only with clear intent and an understanding of `tolerationSeconds`.

## 15. Troubleshooting Pending or Evicted Pods

### 15.1. Inspecting Pods and Events

```bash
kubectl get pods -A -o wide
kubectl describe pod <pod-name> -n <namespace>
kubectl get events -A --sort-by=.lastTimestamp
```

In `describe`, check the `Events` section for messages such as `untolerated taint`, `didn't match node selector/affinity`, `Insufficient cpu`, `Insufficient memory`, or missing extended resources.

### 15.2. Inspecting Node Taints and Labels

```bash
kubectl get nodes
kubectl describe node <node-name>
kubectl get nodes --show-labels
```

Compare `Taints`, `Labels`, `Conditions`, `Allocatable`, and currently allocated resource requests. Verify the node actually matches the accelerator, memory class, zone, or capacity type requested by the pod.

### 15.3. Inspecting Tolerations in PodSpec

```bash
kubectl get pod <pod-name> -n <namespace> -o yaml
```

Check key, value, operator, effect, and `tolerationSeconds`. A `NoSchedule` toleration does not match a `NoExecute` taint; `Exists` with a specific key does not automatically match another key.

### 15.4. Classifying Pending Causes

| Event/Symptom | Common Cause | How to Check |
|---|---|---|
| `untolerated taint` | Pod lacks toleration or effect/value mismatches | Compare node taints with pod tolerations |
| `didn't match node selector` | Label missing or wrong value | Check node labels and selector |
| `node(s) didn't match Pod's node affinity` | Required affinity too restrictive | Check `matchExpressions` and node group templates |
| `Insufficient nvidia.com/gpu` | Out of GPUs or device plugin not advertising | Check allocatable, plugin, and GPU health |
| `Insufficient memory/cpu` | Node out of requested resources | Check requests, allocatable, and autoscaler |
| Pod evicted after taint | `NoExecute` and expired/mismatched toleration | Inspect node events, taints, and `tolerationSeconds` |
| Pod unscheduled after scale-out | New node lacks expected labels/taints or quota hit | Inspect node group, cloud quota, and autoscaler events |

### 15.5. Do Not Fix Immediately with Wildcard Tolerations

When a pod is Pending due to a taint, adding an unrestricted `operator: Exists` toleration might make the pod schedule, but it hides placement errors. First determine which nodes are meant to run the workload and why the taint exists. Add narrow tolerations specifying exact key/value/effect and pair them with affinity if needed.

## 16. Common Mistakes

- **Thinking tolerations select nodes:** a pod accepting a taint without affinity can still run on other nodes.
- **Using labels alone to reserve nodes:** unrelated workloads can still be scheduled onto those nodes without a taint.
- **Using taints without affinity:** workloads are allowed on the dedicated nodes but may still land elsewhere.
- **Confusing the three effects:** `NoSchedule`, `PreferNoSchedule`, and `NoExecute` behave differently.
- **Using wildcard tolerations:** accidentally letting apps land on control-plane, Spot, or unhealthy nodes.
- **Forgetting a second taint:** a node carries multiple taints, leaving the pod Pending.
- **Using `NoExecute` for routine maintenance:** unexpectedly evicting running pods.
- **Ignoring resource requests:** the pod tolerates the taint properly yet still lacks CPU, RAM, or GPU capacity.
- **Untrusted labels:** workloads placed onto nodes without real hardware capabilities or with spoofed labels.
- **Autoscaler unaware of node templates:** newly provisioned nodes lack matching taints/labels for the pod.
- **Forgetting DaemonSet coverage:** new nodes lack logging, networking, or security agents.
- **Treating taints as tenant security:** users able to create pods can add tolerations unless blocked by admission policy.
- **Manually removing pressure taints:** masks symptoms without resolving resource exhaustion.
- **Skipping scale-to-zero tests:** specialized workloads stall in Pending because the node pool cannot initialize the expected configuration.

## 17. Placement Design Checklist

### Node Pools and Metadata

- [ ] Every node pool has a clear purpose, owner, and capacity class.
- [ ] Labels reflect verified capabilities: CPU, GPU, memory, storage, zone, or Spot.
- [ ] Taints use consistent key/value/effect conventions and are managed via automation.
- [ ] Sensitive labels are protected against unauthorized changes.
- [ ] Essential infrastructure DaemonSets carry appropriate tolerations.

### Workload Policies

- [ ] Tolerations include only the key/value/effect required by the workload.
- [ ] `nodeSelector` or node affinity is declared when targeting specific nodes.
- [ ] Resource requests/limits reflect CPU, RAM, GPU, and ephemeral storage demand.
- [ ] Pod affinity/anti-affinity and topology spread align with HA goals.
- [ ] Spot workloads implement checkpointing, retries, and a stable fallback.
- [ ] Tenant/dedicated workloads are backed by admission policies and RBAC.

### Autoscaling and Operations

- [ ] Node group templates declare accurate labels, taints, and resources.
- [ ] HPA and cluster autoscaler min/max bounds align with quotas.
- [ ] Scale-to-zero has been tested with realistic startup latencies.
- [ ] Maintenance workflows use cordon/drain with planned PDBs.
- [ ] `NoExecute` taints and `tolerationSeconds` are tested before production use.
- [ ] Dashboards track Pending pods, taints, node conditions, and autoscaler events.
- [ ] Runbooks document handling and placement rollback for each event category.

## 18. Conclusion

Taints and tolerations establish scheduling boundaries from both the node and pod sides: taints repel unsuitable workloads, while tolerations allow workloads to accept those conditions. The three effects behave differently: `NoSchedule` blocks new pods, `PreferNoSchedule` expresses a soft preference to avoid the node, and `NoExecute` can also evict running pods.

For accurate workload placement, combine tolerations with node selectors or node affinity, resource requests, topology spread, and security policies. GPU, high-memory, storage-intensive, Spot, and tenant-specific workloads each need matching labels/taints/affinity alongside tailored operational practices. Finally, testing autoscaling, maintenance, interruptions, and Pending pod scenarios ensures placement meets performance targets while preserving cluster availability and cost control.
