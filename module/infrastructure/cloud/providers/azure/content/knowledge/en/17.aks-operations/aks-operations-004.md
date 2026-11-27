# Scheduling with Affinity, Taints, and Tolerations

In Azure Kubernetes Service (AKS), a Deployment with three replicas does not mean Kubernetes will automatically place those three Pods on three different nodes. By default, the Kubernetes scheduler (kube-scheduler) tries to find eligible nodes based on resources, constraints, node conditions, and active policies. Without deliberately designing scheduling rules, critical workloads may end up co-located on a single node, CPU-heavy jobs may contend with latency-sensitive services, or Pods may land on an unsuitable node pool.

Kubernetes provides several tools to control this:

- **Node selector and node affinity:** Pods require or prefer running on nodes with matching labels.
- **Pod affinity and pod anti-affinity:** Pods tend to be placed near or separated from other Pods based on labels and topology.
- **Taints and tolerations:** Nodes can repel or evict Pods that do not accept a node's condition; Pods declare tolerations to be considered for those nodes.
- **Topology spread constraints:** require or encourage spreading replicas across topology domains such as nodes or availability zones.

In the **AKS Operations** chapter of the CLOUD_PROVIDERS_AZURE module, this topic connects directly to Azure VM Scale Sets/node pools, Availability Zones, network topology, Azure Monitor, Kubernetes governance permissions, and operational cost. Scheduling rules help place applications in the right locations, but they must work alongside **resource requests, node counts, autoscaling, and monitoring**.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Describe how kube-scheduler filters and scores nodes before placing a Pod.
2. Use `nodeSelector` and `nodeAffinity` in required or preferred modes.
3. Use `podAffinity` and `podAntiAffinity` to co-locate or spread replicas.
4. Distinguish the taint effects `NoSchedule`, `PreferNoSchedule`, and `NoExecute`.
5. Write tolerations with the proper key, operator, value, effect, and `tolerationSeconds`.
6. Combine node taints and node affinity to create dedicated pools on AKS.
7. Apply `topologySpreadConstraints` and evaluate their impact on zone-level HA.
8. Configure node labels and taints at the AKS node pool level and understand interactions with Cluster Autoscaler.
9. Analyze Pending Pods using `kubectl describe`, Events, labels, taints, and resource requests.
10. Build testing checklists, cost controls, and safe change plans for production.

Prerequisites: Kubernetes Pods, Deployments, nodes, namespaces, labels/selectors, Azure Kubernetes Service, AKS node pools, `kubectl`, Azure CLI, and CPU/memory request concepts. Examples that create node pools may incur charges; run them only on authorized lab clusters.

## 2. How Does Kube-Scheduler Choose a Node?

### 2.1. What Steps Does a Pod Go Through During Scheduling?

When a Deployment controller creates a new Pod, the Pod initially lacks `spec.nodeName`. The scheduler finds eligible nodes, scores feasible candidates, and binds the Pod to a chosen node.

~~~mermaid
flowchart TD
    P["New Pod without a node"] --> F["Filter nodes: can it run here?"]
    F --> R{"Any valid nodes?"}
    R -->|No| E["Pod Pending / FailedScheduling"]
    R -->|Yes| S["Score eligible nodes"]
    S --> B["Bind Pod to selected node"]
    B --> K["Kubelet pulls image, creates containers"]
    K --> H["Pod Running / Ready if successful"]
~~~

A node can be filtered out because:

- Insufficient CPU/memory **according to declared requests**.
- The node is cordoned (`spec.unschedulable`), not Ready, or fails another condition.
- It has a `NoSchedule` taint that the Pod does not tolerate.
- It does not satisfy `nodeSelector` or required `nodeAffinity`.
- It violates required `podAntiAffinity` or topology spread set to `DoNotSchedule`.
- It fails volume, topology, port, runtime, or other active scheduler plugin constraints.

After filtering, the scheduler runs scoring plugins, including preferred affinity, resource balancing, and other policies. **Preferred does not guarantee selection**: it contributes points to the overall decision.

### 2.2. Scheduling Differs from Container Runtime

Keep these stages distinct:

| Stage | Primary Component | Question |
|---|---|---|
| Scheduling | kube-scheduler | Which node will the Pod be bound to? |
| Pod admission/placement constraints | Scheduler and configured policies | Does this node satisfy requirements and allow this Pod? |
| Container startup | kubelet/container runtime | Can it pull the image, mount volumes, and start the process? |
| Readiness | Kubelet and health probes | Is the Pod ready to receive traffic? |
| Eviction/rescheduling | Controllers, node controller, scheduler, and eviction mechanisms | When a node fails or taints change, what happens to the Pod? |

A Pod already bound to a node will not automatically move to another node simply because a **preferred affinity** becomes a better match elsewhere. Even **requiredDuringSchedulingIgnoredDuringExecution** includes `IgnoredDuringExecution`: if node labels change after the Pod is running, Kubernetes does not automatically evict the Pod solely because that constraint no longer matches.

Conversely, a taint with the `NoExecute` effect can affect already-running Pods depending on their tolerations. Do not confuse `NoSchedule` with eviction.

### 2.3. The Scheduler Does Not Rely Directly on Instantaneous CPU Usage

The scheduler generally evaluates placement capacity using **resource requests**, allocatable capacity, and active constraints; current CPU usage does not replace requests.

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

This Pod asks the scheduler to reserve 0.5 vCPU and 512 MiB for the container. Without realistic requests, placement and node scaling decisions may mismatch actual load. Conversely, overly large requests leave Pods Pending even when actual CPU is idle.

Affinity and tolerations **do not create extra CPU or RAM**. They only affect where Pods are permitted or preferred to run.

## 3. Labels and nodeSelector: The Foundation of Scheduling

### 3.1. Labels Are Key/Value Metadata

Nodes can carry labels describing their attributes:

~~~text
kubernetes.io/os=linux
kubernetes.io/arch=amd64
topology.kubernetes.io/zone=southeastasia-1
kubernetes.azure.com/agentpool=batchpool
workload=batch
team=data
~~~

The labels above are examples only. System-managed label prefixes should not be edited arbitrarily; custom labels like `workload=batch` require organizational conventions and management via appropriate AKS/node pool processes.

Inspect nodes and labels:

~~~bash
kubectl get nodes --show-labels

kubectl get nodes \
  -L workload,topology.kubernetes.io/zone,kubernetes.azure.com/agentpool

kubectl describe node <NODE_NAME>
~~~

Do not assume a node is secured simply because a label is named `secure` or `dedicated`. Labels are metadata for scheduling and organization, **not an authentication or security boundary**.

### 3.2. nodeSelector: Simple Mandatory Condition

Example of a Pod constrained to run only on nodes labeled `workload=batch`:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: batch-reader
  namespace: jobs
spec:
  nodeSelector:
    workload: batch
  containers:
    - name: worker
      image: nginx:1.27
      resources:
        requests:
          cpu: "100m"
          memory: "128Mi"
~~~

The scheduler only considers nodes matching every key/value declared in `nodeSelector`. If no node has `workload=batch`, the Pod remains Pending.

`nodeSelector` does not support soft preferences or expressive operators; for those, use node affinity.

### 3.3. When Is nodeSelector Enough?

Use `nodeSelector` when constraints are simple and mandatory, such as:

- Workload only runs on Linux.
- Workload requires a node pool labeled `workload=etl`.
- Software is certified only on a specific CPU architecture.
- Pod must run on nodes provisioned with specialized drivers/devices.

If you need "prefer node pool A, but allow running on B if A is full," `nodeSelector` is not enough; evaluate preferred node affinity and other constraints.

## 4. Node Affinity: Required and Preferred

### 4.1. Two Main Types

| Type | Effect When Scheduling a Pod | When Node Labels Change Later |
|---|---|---|
| `requiredDuringSchedulingIgnoredDuringExecution` | Hard requirement: non-matching nodes are excluded | Running Pods are not automatically evicted just because a label changed |
| `preferredDuringSchedulingIgnoredDuringExecution` | Soft preference: matching nodes gain score by weight | Does not migrate Pods after placement |

Most workloads should avoid hard constraints on mutable labels unless truly necessary, such as nodes with mandatory hardware or compliance isolation.

### 4.2. Required Node Affinity

Example running only on Linux nodes labeled `workload=payments`:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: payments-api
  namespace: payments
spec:
  replicas: 2
  selector:
    matchLabels:
      app: payments-api
  template:
    metadata:
      labels:
        app: payments-api
    spec:
      affinity:
        nodeAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            nodeSelectorTerms:
              - matchExpressions:
                  - key: workload
                    operator: In
                    values: ["payments"]
                  - key: kubernetes.io/os
                    operator: In
                    values: ["linux"]
      containers:
        - name: api
          image: "<REGISTRY>/payments-api:<VERSION>"
          resources:
            requests:
              cpu: "300m"
              memory: "256Mi"
            limits:
              cpu: "1"
              memory: "1Gi"
~~~

Expressions within **a single** `nodeSelectorTerm` are combined with AND; multiple `nodeSelectorTerms` are combined with OR. Therefore, this example requires `workload=payments` **and** `os=linux`.

If no eligible node exists, the Pod **will not** bypass the required rule to temporarily run on another pool.

### 4.3. matchExpressions Operators

| Operator | Meaning |
|---|---|
| `In` | Label value is in the specified values list |
| `NotIn` | Value is not in the list (following selector semantics) |
| `Exists` | Label key exists |
| `DoesNotExist` | Label key does not exist |
| `Gt` | Integer comparison on string values per selector semantics |
| `Lt` | Integer comparison on string values per selector semantics |

Example:

~~~yaml
nodeSelectorTerms:
  - matchExpressions:
      - key: disk
        operator: In
        values: ["ssd", "nvme"]
      - key: workload
        operator: Exists
  - matchExpressions:
      - key: workload
        operator: In
        values: ["fallback-batch"]
~~~

The snippet above selects nodes matching (`disk` is `ssd`/`nvme` **and** `workload` label exists) **or** `workload=fallback-batch`. Use it only as a fragment inside `requiredDuringSchedulingIgnoredDuringExecution`, not as a standalone manifest.

The `NotIn` operator is not equivalent to proving a node belongs to a trusted tier; when you need assurance that a node belongs to a trusted group, use managed and protected labels.

### 4.4. Preferred Node Affinity

Example preferring nodes labeled `performance=high` or `workload=shared` while still allowing other nodes if necessary:

~~~yaml
affinity:
  nodeAffinity:
    preferredDuringSchedulingIgnoredDuringExecution:
      - weight: 80
        preference:
          matchExpressions:
            - key: performance
              operator: In
              values: ["high"]
      - weight: 20
        preference:
          matchExpressions:
            - key: workload
              operator: In
              values: ["shared"]
~~~

`weight` typically takes values from 1 to 100 per preferred term. Matching nodes receive added score in the corresponding plugin; this score is combined with other scheduler scoring factors.

**Do not interpret `weight: 80` as "80% of Pods will be placed on that node type."** It is a scoring weight, not a traffic split ratio or probability target.

### 4.5. Combining nodeSelector and nodeAffinity

If a Pod specifies both `nodeSelector` and required `nodeAffinity`, a node must satisfy **both**. Other constraints such as taints, resources, and topology still apply.

A very common contradiction:

~~~yaml
nodeSelector:
  workload: payments
affinity:
  nodeAffinity:
    requiredDuringSchedulingIgnoredDuringExecution:
      nodeSelectorTerms:
        - matchExpressions:
            - key: workload
              operator: In
              values: ["batch"]
~~~

A node cannot simultaneously hold `workload=payments` and `workload=batch` for the same key, so the Pod stays Pending. Before deploying, check that hard conditions do not contradict each other.

## 5. Pod Affinity and Pod Anti-Affinity

### 5.1. When Pods Should Be Placed Close Together

**Pod affinity** allows a Pod to require or prefer running in the same topology domain as Pods matching specific labels.

For example, a batch workload wants to run on the same node as a cache helper labeled `app=cache-local`:

~~~yaml
affinity:
  podAffinity:
    preferredDuringSchedulingIgnoredDuringExecution:
      - weight: 80
        podAffinityTerm:
          labelSelector:
            matchLabels:
              app: cache-local
          topologyKey: kubernetes.io/hostname
~~~

Here the topology domain is the **node** (`hostname`). With a preferred rule, the scheduler can pick another node if nodes near the cache are ineligible. To make it mandatory, use `requiredDuringSchedulingIgnoredDuringExecution` with a list of `PodAffinityTerm` per Kubernetes schema.

Co-locating Pods on the same node can reduce latency when node-local locality matters, but it also creates a shared failure domain: losing one node loses both Pods. Evaluate whether this is truly required.

### 5.2. Pod Anti-Affinity for High Availability

**Pod anti-affinity** tries to separate Pods sharing labels across different topology domains. For example, two `orders-api` replicas should not share a node.

~~~yaml
affinity:
  podAntiAffinity:
    preferredDuringSchedulingIgnoredDuringExecution:
      - weight: 100
        podAffinityTerm:
          labelSelector:
            matchLabels:
              app: orders-api
          topologyKey: kubernetes.io/hostname
~~~

This configuration **prefers** separate nodes, yet still allows co-location if the cluster lacks nodes or other priorities dominate. It helps avoid Pending Pods in smaller environments.

Hard configuration:

~~~yaml
affinity:
  podAntiAffinity:
    requiredDuringSchedulingIgnoredDuringExecution:
      - labelSelector:
          matchLabels:
            app: orders-api
        topologyKey: kubernetes.io/hostname
~~~

If there are three replicas but only two eligible nodes, each already hosting one replica, the third replica will remain Pending. That is the intended behavior of hard anti-affinity, not a random scheduler bug.

### 5.3. topologyKey and the Scope of Matched Pods

Common `topologyKey` values:

- **`kubernetes.io/hostname`:** per node.
- **`topology.kubernetes.io/zone`:** per Availability Zone when nodes actually carry the corresponding label.
- **`topology.kubernetes.io/region`:** per region, usually less useful within a single-region AKS cluster.

Pod affinity/anti-affinity uses `labelSelector` to select reference Pods; the namespace scope of those Pods can be configured via `namespaces` or `namespaceSelector` based on needs and feature support.

If namespace scope is omitted, default semantics generally only inspect the current Pod's namespace. When you need to match or avoid Pods across multiple namespaces, explicitly declare the scope rather than expecting the scheduler to scan all namespaces automatically.

### 5.4. Required Anti-Affinity Does Not Always Mean Better HA

Hard constraints separate replicas but can hurt recovery when nodes are lost. For example:

- An outage leaves the cluster with only one node.
- Required anti-affinity forbids running a second replica on the surviving node.
- The workload drops to a single Ready replica, increasing risk if that node is overloaded.

When the goal is "try to spread" while prioritizing availability, **preferred anti-affinity** or **topology spread constraints with appropriate policies** is usually more resilient.

## 6. Taints and Tolerations: Nodes Repel, Pods Tolerate

### 6.1. Taints Are Placed on Nodes

A taint is a node property typically expressed as:

~~~text
key=value:Effect
~~~

Examples:

~~~text
workload=payments:NoSchedule
dedicated=gpu:NoSchedule
maintenance=true:PreferNoSchedule
draining=true:NoExecute
~~~

The scheduler and controllers evaluate taints when deciding whether a Pod may be placed on or remain on a node.

**Tolerations belong on the Pod**, declaring that the Pod accepts a specific taint. A toleration **is not a placement directive**, grants no extra CPU, and adds no security privileges. It merely removes the blocking effect of the matching taint for that Pod.

### 6.2. Three Effects to Remember

| Effect | Pod Without Matching Toleration | Effect on Already-Running Pods |
|---|---|---|
| `NoSchedule` | Will not be newly scheduled onto the node | Does not automatically evict running Pods just because `NoSchedule` was added |
| `PreferNoSchedule` | Scheduler tries to avoid, but may still schedule if needed | Not an eviction mechanism |
| `NoExecute` | Will not be newly scheduled and can be evicted | Can evict existing Pods that do not tolerate it |

For `NoExecute` in particular, eviction timing and behavior also depend on node/taint management controllers and runtime state. Do not equate every eviction event with instant container termination or guaranteed graceful shutdown regardless of whether the node is still reachable.

### 6.3. Equal Toleration

Example of a Pod tolerating taint `workload=payments:NoSchedule`:

~~~yaml
tolerations:
  - key: workload
    operator: Equal
    value: payments
    effect: NoSchedule
~~~

The Pod **may** be scheduled onto that node if all other conditions are met. It can also run on nodes **without that taint** unless another placement constraint restricts it.

Counterexample:

~~~text
Node A: workload=payments:NoSchedule
Node B: no taint

Pod has payments toleration, no nodeAffinity.
→ Pod can be placed on either A or B.
~~~

Conclusion: to dedicate a `payments` pool, you normally combine **taint on the pool + toleration in the Pod + required nodeAffinity/nodeSelector**.

### 6.4. Toleration with Exists

A toleration that does not compare a specific value can use `Exists`:

~~~yaml
tolerations:
  - key: dedicated
    operator: Exists
    effect: NoSchedule
~~~

This allows the Pod to tolerate `NoSchedule` taints with key `dedicated`, regardless of value. Understand the scope thoroughly before using it.

An overly broad `Exists` toleration without key/effect bounds can let a Pod bypass unintended taints and land on reserved or unhealthy nodes. **Do not use broad wildcard tolerations on production applications** unless genuinely justified and reviewed for security/operations.

### 6.5. Multiple Taints Must All Be Accounted For

If a node has:

~~~text
workload=payments:NoSchedule
compliance=restricted:NoSchedule
~~~

and a Pod only tolerates `workload=payments`, the node is still blocked by `compliance=restricted`. Every taint **with a relevant blocking effect** must be tolerated for the node to be a candidate.

Having "at least one toleration" is not enough: each taint acts as an independent barrier.

### 6.6. NoExecute and tolerationSeconds

`NoExecute` is especially useful for modeling how long a Pod is allowed to **stay** on a node when conditions change.

~~~yaml
tolerations:
  - key: node.kubernetes.io/not-ready
    operator: Exists
    effect: NoExecute
    tolerationSeconds: 120
~~~

Meaning: when the corresponding `NotReady` taint is applied, the Pod can tolerate it for the specified duration per system semantics; once expired and the condition persists, the Pod may be evicted.

If a Pod has a matching `NoExecute` toleration **without** `tolerationSeconds`, in principle it can tolerate that taint indefinitely. This does not mean the Pod can still serve traffic if the node is actually dead or partitioned.

Many standard Pods automatically receive default tolerations for `not-ready` and `unreachable` conditions via Kubernetes admission defaults; the default window is commonly around 300 seconds in typical setups, though admission controllers and specialized workloads may differ. Inspect live Pods with:

~~~bash
kubectl get pod <POD_NAME> -n <NAMESPACE> \
  -o jsonpath='{.spec.tolerations}'
~~~

### 6.7. Taints Are Not an Absolute Security Mechanism

Anyone with permission to edit a Pod manifest can add a toleration to their Pod. Therefore, taints are appropriate for **workload placement governance**; do not treat taints as a replacement for RBAC, admission policies, NetworkPolicies, Pod Security, node isolation, or data access controls.

For nodes hosting high-compliance workloads, add admission/policy controls so unauthorized users cannot create Pods with labels, affinities, or tolerations that route them onto isolated pools.

## 7. Comparing nodeAffinity, podAntiAffinity, and Taints

| Tool | Where Declared? | Primary Question | Mandatory? |
|---|---|---|---|
| `nodeSelector` | Pod spec | Which node labels must the Pod run on? | Yes |
| required `nodeAffinity` | Pod spec | Which nodes qualify via label expressions? | Yes |
| preferred `nodeAffinity` | Pod spec | Which node types are preferred? | No |
| `podAffinity` | Pod spec | Which Pods should/must this Pod sit near? | Depends on required/preferred |
| `podAntiAffinity` | Pod spec | Which Pods should/must this Pod avoid? | Depends on required/preferred |
| Node taint | Node / AKS node pool | Should non-matching Pods be blocked or evicted? | Depends on effect |
| Pod toleration | Pod spec | Which taints does the Pod accept? | Does not force placement on its own |
| `topologySpreadConstraints` | Pod spec | How are replicas spread across nodes/zones? | Depends on `whenUnsatisfiable` |

Remember in one sentence:

**Affinity attracts or binds Pods to a set of nodes/Pods; taints repel non-matching Pods from a set of nodes; tolerations merely allow bypassing the barrier created by a taint.**

## 8. AKS Node Pools: Where Labels and Taints Are Managed

### 8.1. System Node Pools and User Node Pools

AKS organizes worker nodes into **node pools**, typically backed by VM Scale Sets. Node pools run in `System` or `User` mode:

- **System pool:** dedicated to hosting critical cluster system workloads per AKS operational guidance.
- **User pool:** dedicated to application workloads; can be separated by CPU/memory/GPU, Spot, or security requirements.

**`Mode=System` is not an absolute scheduling boundary.** Without corresponding taints/affinities, other workloads may still be scheduled onto system nodes depending on cluster configuration. To protect system workloads or carve out dedicated pools, evaluate labels, taints, resource requests, and capacity.

Do not carelessly taint a system pool without verifying that all add-ons, DaemonSets, and system workloads carry the required tolerations. Blocking system Pods can break DNS, networking, or monitoring.

### 8.2. Creating a User Node Pool with Labels and Taints

Suppose the lab cluster `aks-scheduling-lab` exists with sufficient quota. We want a dedicated pool for batch workers:

~~~bash
az account show --output table

az aks nodepool add \
  --resource-group rg-aks-lab \
  --cluster-name aks-scheduling-lab \
  --name batchpool \
  --mode User \
  --node-count 2 \
  --node-vm-size Standard_D4s_v5 \
  --labels workload=batch team=data \
  --node-taints workload=batch:NoSchedule
~~~

Expected effects:

- Nodes in `batchpool` carry the label `workload=batch`.
- Nodes carry the taint `workload=batch:NoSchedule`.
- Pods that do not tolerate the taint are prevented from newly scheduling into the pool.
- Batch workloads with the matching toleration and node affinity can land in the pool, provided resources and other constraints are satisfied.

Verify parameters, quotas, node pool name limits, VM size/region availability, and label/taint flags against your current Azure CLI/AKS version. If production uses an autoscaler, pick min/max counts and autoscaler settings accordingly rather than keeping an expensive static pool just because the example shows `node-count 2`.

### 8.3. Why Configure Labels and Taints at the Node Pool Level?

You can modify an individual node with `kubectl`:

~~~bash
kubectl label node <NODE_NAME> workload=batch --overwrite

kubectl taint node <NODE_NAME> workload=batch:NoSchedule
~~~

However, in AKS, nodes can be replaced during upgrades, autoscaling, or repairs. Labels/taints applied manually to a single node may not persist on replacement nodes. Therefore, declare them in the **AKS node pool configuration** or supported durable governance tools.

Before changing taints on an active production pool, assess risks of Pending Pods, DaemonSets, node replacement/rolling operations, and rollback steps. Never add `NoExecute` to a production pool merely as an experiment.

### 8.4. Listing Node Pools and Labels

~~~bash
az aks nodepool list \
  --resource-group rg-aks-lab \
  --cluster-name aks-scheduling-lab \
  --output table

az aks nodepool show \
  --resource-group rg-aks-lab \
  --cluster-name aks-scheduling-lab \
  --name batchpool \
  --output json

kubectl get nodes \
  -L workload,kubernetes.azure.com/agentpool

kubectl describe node <NODE_NAME>
~~~

Verify both the **Azure node pool configuration** and the **live Kubernetes node objects**. An Azure task reporting `Succeeded` does not guarantee all nodes are Ready or Pods have scheduled properly.

## 9. Hands-On: Combining Affinity and Toleration on AKS

### 9.1. Problem Statement

A Data Engineering team needs to run data-processing Jobs/Deployments on `batchpool`. Goals:

1. Other application workloads must not be newly scheduled onto `batchpool` without permission.
2. Batch Pods must be placed **on `batchpool`**, never on `systempool`.
3. When `batchpool` runs out of nodes/capacity, Pods should remain Pending so the autoscaler or operators add capacity—never silently spill onto the wrong pool.
4. Workers declare explicit CPU/memory requests for the scheduler and autoscaler to evaluate.

Assume the node pool already has:

~~~text
Label: workload=batch
Taint: workload=batch:NoSchedule
~~~

### 9.2. Complete Deployment

Example worker application assuming an existing image:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: batch-worker
  namespace: jobs
  labels:
    app: batch-worker
spec:
  replicas: 2
  selector:
    matchLabels:
      app: batch-worker
  template:
    metadata:
      labels:
        app: batch-worker
    spec:
      affinity:
        nodeAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            nodeSelectorTerms:
              - matchExpressions:
                  - key: workload
                    operator: In
                    values: ["batch"]
        podAntiAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
            - weight: 100
              podAffinityTerm:
                labelSelector:
                  matchLabels:
                    app: batch-worker
                topologyKey: kubernetes.io/hostname
      tolerations:
        - key: workload
          operator: Equal
          value: batch
          effect: NoSchedule
      containers:
        - name: worker
          image: "<REGISTRY>/batch-worker:<VERSION>"
          resources:
            requests:
              cpu: "500m"
              memory: "512Mi"
            limits:
              cpu: "1"
              memory: "1Gi"
~~~

Before applying, create the `jobs` namespace via an authorized process, replace the image with a valid one, and verify security contexts, configs, secrets, probes, and volumes as required by the app.

**Explanation:**

- Required `nodeAffinity` forces Pods onto `workload=batch` nodes.
- The toleration allows Pods past the `workload=batch:NoSchedule` taint.
- Preferred `podAntiAffinity` tries to place replicas on different nodes without blocking scheduling when only one node has capacity.
- `resources.requests` lets the scheduler and autoscaler size capacity accurately.

If the **toleration** is missing, Pods will be blocked by the taint despite matching labels.

If **`nodeAffinity`** is missing, Pods may run on ordinary untainted nodes, violating dedicated pool isolation.

If only **`podAntiAffinity`** is present, Pods try to separate from sibling Pods but are not guaranteed to land in the right node pool.

### 9.3. Deploy and Verify

Suppose the development team saved the manifest as `batch-worker.yaml` in a test environment:

~~~bash
kubectl apply -f batch-worker.yaml

kubectl get pods -n jobs -o wide

kubectl describe pod <POD_NAME> -n jobs

kubectl get nodes \
  -L workload,kubernetes.azure.com/agentpool
~~~

The `NODE` column from `kubectl get pods -o wide` shows which node actually runs each Pod. Compare that node's labels and taints against the rules in the Pod spec.

In production, manage manifests via GitOps or CI/CD pipelines with policy checks and approvals rather than ad-hoc manual edits without an audit trail.

### 9.4. Testing Misplacement Risk

Create a Pod without a toleration but with `nodeSelector: workload=batch` in the lab. Expect it to remain Pending if all nodes matching `workload=batch` carry the corresponding taint.

Event messages may resemble:

~~~text
0/5 nodes are available:
2 node(s) had untolerated taint {workload: batch},
3 node(s) didn't match Pod's node affinity/selector.
~~~

This is an illustrative example, not real cluster output. It shows two distinct filtering reasons; the scheduler can aggregate multiple reasons.

Do not leave test Pods Pending indefinitely in production if monitoring and autoscalers might interpret them as real demand requiring additional nodes.

## 10. Spreading Replicas with Topology Spread Constraints

### 10.1. Why Is Topology Spread Needed?

Pod anti-affinity helps prevent co-location, but with multiple replicas and multiple availability zones, **`topologySpreadConstraints`** is purpose-built to control distribution skew.

Suppose three `orders-api` replicas should spread across AKS cluster zones. This is effective when the corresponding zones and nodes **actually exist** and are visible to the scheduler via node labels.

### 10.2. Meaning of maxSkew and whenUnsatisfiable

| Field | Meaning |
|---|---|
| `topologyKey` | Node label defining the spread domain, e.g., `topology.kubernetes.io/zone` |
| `maxSkew` | Maximum allowed difference in matching Pod counts across domains per scheduler semantics |
| `whenUnsatisfiable=DoNotSchedule` | Rejects scheduling the Pod if placement violates the spread constraint |
| `whenUnsatisfiable=ScheduleAnyway` | Still schedules the Pod, using spread as a scoring preference |
| `labelSelector` | Selects the set of Pods counted in the distribution |
| `minDomains` | Optional field with specific semantics when fewer than required eligible domains exist; use only when needed |

Do not confuse `maxSkew=1` with "exactly one Pod per zone" in every scenario: results depend on replica count, number of eligible domains, existing Pods, node capacity, and other placement constraints.

### 10.3. Availability Zone Spread Example

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
  namespace: orders
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
      topologySpreadConstraints:
        - maxSkew: 1
          topologyKey: topology.kubernetes.io/zone
          whenUnsatisfiable: DoNotSchedule
          labelSelector:
            matchLabels:
              app: orders-api
      containers:
        - name: api
          image: "<REGISTRY>/orders-api:<VERSION>"
          resources:
            requests:
              cpu: "250m"
              memory: "256Mi"
~~~

This illustrative scenario assumes the pool spans multiple zones with Ready nodes and sufficient capacity. If the cluster sits in a single zone, this config will not conjure extra zones; multi-zone HA requires multi-zone node pools, regional zone support, and real capacity.

For systems prioritizing availability over strict spread, consider `ScheduleAnyway` paired with preferred `podAntiAffinity` to reduce Pending risk if one zone loses nodes.

### 10.4. Combining Zone and Hostname Spread

You can combine multiple constraints, such as spreading replicas across both zones and nodes. However, **all constraints must be satisfied** when set to `DoNotSchedule`, so stacking overly rigid rules can leave the cluster with zero eligible nodes.

When using advanced options like `nodeAffinityPolicy` and `nodeTaintsPolicy`, understand which nodes count as eligible domains in the skew calculation. If taints and affinities exclude nodes/zones, looking solely at raw Pod counts may not explain scheduler decisions.

### 10.5. Topology Alone Does Not Guarantee Self-Healing

Spreading Pods across zones is not sufficient for application HA if:

- The database has only a single instance/zone.
- A PersistentVolume has zone affinity locked to one zone.
- The load balancer or DNS/ingress does not meet HA requirements.
- Pods lack readiness/liveness probes.
- Replicas or node capacity are insufficient.
- Deployment rollouts or PDBs prevent Pod replacement as expected.

Scheduling is one piece of HA, not a substitute for data-tier and dependency architecture.

## 11. Scheduling and AKS Cluster Autoscaler

### 11.1. Pending Pods Can Trigger Scaling Demand

AKS can run **Cluster Autoscaler** on supported, configured node pools. When Pods remain Pending due to insufficient matching nodes, the autoscaler evaluates adding nodes to pools compatible with the Pod's constraints.

Example:

~~~text
Pod requires:
  nodeAffinity: workload=batch
  toleration: workload=batch:NoSchedule
  cpu request: 500m

AKS batchpool:
  label: workload=batch
  taint: workload=batch:NoSchedule
  autoscaler: enabled, min=1, max=5
~~~

When the pool is full, the autoscaler can consider scaling up `batchpool` if quotas, max count, VM provisioning capacity, and other conditions allow.

If the Pod requires a label **not present on any scalable pool**, scaling up `systempool` will not help; the Pod stays Pending. Similarly, a Pod missing a required toleration will not be unblocked merely by adding more nodes carrying that same taint.

### 11.2. Limitations to Understand

- The autoscaler does not provision nodes instantaneously; Azure VM provisioning takes time.
- Max node count, subscription quotas, regional capacity, and network IP space can block scaling.
- Scaling from zero requires node pool templates/labels/taints to match so the autoscaler knows Pods can run on new nodes.
- Narrow hard constraints may leave zero pools eligible.
- A workload whose resource requests exceed any single node's capacity in the pool still cannot schedule even if more nodes are added.
- PVCs with zone affinity or node constraints can restrict pool choices.
- Drain/scale-down is also constrained by PodDisruptionBudgets, workload state, and system Pods.

Do not fix a Pending Pod by blindly raising `maxCount` on every pool when the placement rules themselves are wrong.

### 11.3. HPA and Cluster Autoscaler Operate at Two Layers

| Mechanism | Adjusts | Prerequisite |
|---|---|---|
| Horizontal Pod Autoscaler (HPA) | Pod replica count based on metrics/policies | Valid metrics, proper requests, and schedulability |
| Cluster Autoscaler | Node count in pools to meet Pod demand | Scalable pool and valid Pod placement constraints |
| Manual node pool scaling | Operator adjusts capacity | Quotas, budget, approval, and monitoring |

For example, HPA scales `orders-api` from 3 to 9 replicas. If required anti-affinity demands one Pod per node while only three nodes exist and the autoscaler cannot add nodes, the new Pods stay Pending even though HPA worked properly.

### 11.4. Node Auto Provisioning

AKS may offer **Node Auto Provisioning** modes depending on feature support, using a capacity selection and provisioning model distinct from traditional per-pool autoscaling. When using it, verify compatibility of labels, taints, disruption behavior, and policies with the active provisioner. Do not carry over all Cluster Autoscaler parameters and assumptions verbatim onto a cluster using a different node auto-provisioning mode.

## 12. Spot Node Pools: Leveraging Cost Savings Without Risking Critical Workloads

AKS supports **Spot node pool** scenarios subject to VM availability and service policies. Spot offers attractive pricing for interruptible jobs, but Azure can evict Spot capacity at any time.

### 12.1. Designing Batch Workloads to Tolerate Interruption

For batch/CI jobs that do not require strict uptime:

- Use a dedicated pool with Spot-identifying labels and taints managed by AKS or added by organizational policy.
- Workloads targeting Spot need the matching toleration plus affinity if hard placement is desired.
- Jobs must be idempotent, use checkpoints/retries, and persist outputs to durable storage.
- Do not rely on local ephemeral disks as the sole source of truth.
- Keep an on-demand fallback pool if business SLAs require it, designing soft/hard rules accordingly.
- Monitor evictions, completion rates, and actual costs.

Some AKS Spot node pool configurations include a system taint such as:

~~~text
kubernetes.azure.com/scalesetpriority=spot:NoSchedule
~~~

Do not manually edit or remove platform-managed taints. Verify live values using `kubectl describe node` and AKS documentation for your pool type.

### 12.2. Tolerations Do Not Prevent Spot Eviction

Tolerating the Spot taint only permits scheduling onto Spot nodes. **It does not stop Azure from reclaiming Spot VMs due to capacity or pricing.** Pods can be interrupted regardless of tolerations.

For payment APIs or transactional systems needing high availability, do not rely solely on Spot nodes. Combine on-demand pools, priorities, and HA controls as needed.

### 12.3. Fallback Fails If Hard Affinity Locks Onto Spot

Suppose a Pod has `nodeSelector: spot=true` and a Spot toleration. When the Spot pool runs out of capacity, the Pod cannot spill over to an on-demand pool even if spare capacity exists there.

To allow fallback, consider preferred `nodeAffinity` and pool-specific conditions while ensuring the Pod can handle the relevant taints and cost/availability policies are governed. Note that `preferred` does not guarantee the scheduler will pick Spot first in every situation.

## 13. Priority, Preemption, and PodDisruptionBudgets

### 13.1. PriorityClass and Preemption

Kubernetes supports Pod priority. When a high-priority Pod cannot be scheduled due to resource shortages, preemption may evict lower-priority Pods in certain situations.

However, **preemption does not bypass every constraint**:

- It will not make a node with the wrong label satisfy required `nodeAffinity`.
- It will not add missing tolerations to a Pod.
- It will not create nodes in a non-existent zone.
- It will not move a PVC bound to another zone.
- It will not override network or security policies.

Do not overuse high `PriorityClass` across all workloads; a cluster where every Pod is top priority cannot distinguish truly critical tasks.

### 13.2. PodDisruptionBudget (PDB)

A PDB limits **voluntary disruptions**, such as drains/evictions executed through supported procedures, to maintain a minimum number of available Pods.

~~~yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: orders-api-pdb
  namespace: orders
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: orders-api
~~~

A PDB does not turn the scheduler into an automatic Pod spreader. Nor can it prevent unexpected node failures, infrastructure-level Spot VM evictions, or application crashes. With three replicas and `minAvailable=2`, verify node drain behavior, readiness, and actual replica distribution.

An overly strict PDB in a small cluster can stall maintenance or upgrades. Test PDBs, affinities, and autoscaling together rather than configuring them in isolation.

## 14. Security and Governance for Scheduling

### 14.1. Who Can Modify Taints, Labels, or Affinity?

These operations can heavily impact production:

- Modifying labels/taints on nodes or AKS node pools.
- Editing Deployments/DaemonSets/Jobs and affinity rules.
- Attaching broad tolerations to unauthorized workloads.
- Creating Pods with very high priority.
- Creating privileged Pods or Pods with host access on dedicated nodes.

Enforce permissions using Kubernetes RBAC and Azure RBAC at appropriate scopes. Do not allow every application team to modify Node objects or production AKS node pools.

### 14.2. Labels Are Not a Hard Security Layer

Kubernetes includes mechanisms restricting kubelets from self-modifying protected node label prefixes such as **`node-restriction.kubernetes.io/`** when the Node authorizer and `NodeRestriction` admission plugin are configured properly. This is worth checking when labels are used for trusted **node isolation**.

In AKS, verify which mechanisms are platform-managed and supported; do not assume you can alter control-plane admission flags directly. For high-compliance node isolation, combine protected labels, admission policies, node/pod RBAC, network segmentation, and runtime controls.

Taints and affinities do not hide secrets, block Pod-to-Pod network traffic, or replace Pod Security Admission or Kubernetes NetworkPolicies.

### 14.3. Configuration Control via GitOps/IaC

A reliable model:

1. AKS node pools, labels, and taints are defined in Bicep/Terraform or supported governance tooling.
2. Workloads declare affinity/tolerations in reviewed Helm/Kustomize/YAML.
3. CI validates schemas, policies, resource requests, and pool-to-workload compatibility.
4. Changes require approval for production.
5. After deployment, verify Pod distribution, Pending events, node health, and budgets.
6. Monitor for configuration drift from manual node/pod edits.

Separating permissions to modify node pool infrastructure from permissions to release applications reduces the risk of unintended scheduling changes.

## 15. Diagnosing Pending Pods and FailedScheduling

### 15.1. Start from the Right Pod

~~~bash
kubectl get pods -A -o wide

kubectl describe pod <POD_NAME> -n <NAMESPACE>

kubectl get events -n <NAMESPACE> \
  --sort-by=.metadata.creationTimestamp
~~~

Look for events with reason **`FailedScheduling`** and read the scheduler message. The unavailable node count and rejection reasons help separate resource, taint, affinity, topology, and volume issues.

Illustrative messages:

~~~text
0/4 nodes are available:
2 node(s) had untolerated taint {dedicated: gpu},
2 node(s) didn't match Pod's node affinity/selector.

0/5 nodes are available:
3 Insufficient cpu,
2 Insufficient memory.

0/3 nodes are available:
3 node(s) didn't match pod topology spread constraints.

0/4 nodes are available:
2 node(s) had volume node affinity conflict.
~~~

Do not rush to fix things by deleting all constraints. Each message points to a different root cause.

### 15.2. Inspect Node Labels and Taints

~~~bash
kubectl get nodes -o wide

kubectl get nodes \
  -L workload,topology.kubernetes.io/zone,kubernetes.azure.com/agentpool

kubectl describe node <NODE_NAME>
~~~

Under Taints and Labels, compare against the Pod spec:

- Does the node have the exact expected label value?
- Does the node have one or more taints the Pod does not tolerate?
- Is the node in the right zone and network segment?
- Is the node Ready and uncordoned?
- What are the node's allocatable resources and current reserved requests?

### 15.3. Inspect the Live Pod Spec

~~~bash
kubectl get pod <POD_NAME> -n <NAMESPACE> \
  -o yaml
~~~

Inspect:

- `spec.nodeSelector`.
- `spec.affinity.nodeAffinity`, `podAffinity`, `podAntiAffinity`.
- `spec.tolerations`.
- `spec.topologySpreadConstraints`.
- `spec.containers[].resources`.
- `spec.volumes` and PVCs.
- `spec.priorityClassName`.
- Metadata labels used in selectors.

Source manifests may differ from live Pods after admission/mutating webhooks or Helm templating. When investigating, compare the **live deployed Pod object**, not just the file in Git.

### 15.4. Check Capacity from AKS

~~~bash
az aks nodepool list \
  --resource-group rg-aks-lab \
  --cluster-name aks-scheduling-lab \
  --output table

az aks nodepool show \
  --resource-group rg-aks-lab \
  --cluster-name aks-scheduling-lab \
  --name batchpool \
  --output json
~~~

If the autoscaler is enabled, inspect min/max bounds, node pool labels/taints, quotas, and related events. A Pod too large for any VM SKU in the pool will not be fixed by adding more nodes.

### 15.5. Categorize and Remediate

| Primary Error | Sensible Remediation | What Not to Do |
|---|---|---|
| Untolerated taint | Confirm whether the Pod belongs in that pool; add specific toleration if valid | Add wildcard `Exists` to all Pods |
| No node matches affinity | Check labels/pools/zones; fix rule or provision right capacity | Remove required policies representing compliance boundaries |
| Insufficient cpu/memory | Review requests and node capacity; optimize workload or scale pool | Shrink requests below actual demand |
| Overly strict pod anti-affinity | Add nodes/zones or switch to preferred if aligned with HA goals | Delete spreading rules without evaluation |
| Topology spread hard block | Check domain labels, node count, and skew; adjust `whenUnsatisfiable`/scale | Forge zone labels to bypass rules |
| PVC zone conflict | Inspect StorageClass, volume binding, and zone topology | Force Pod into a zone that cannot reach its storage |
| Nodes NotReady / cordoned | Restore node/cluster health; investigate taints and kubelet | Add tolerations for all unhealthy node states |
| Scaling does not occur | Inspect autoscaler bounds, quotas, and node templates | Raise `maxCount` endlessly or spawn uncontrolled pools |

## 16. Monitoring AKS Scheduling in Practice

### 16.1. Observation Sources

| Signal | Source | Meaning |
|---|---|---|
| Prolonged Pending Pods | `kubectl`, Kubernetes Events, Container insights | Workload lacks eligible nodes or hits scheduling errors |
| `FailedScheduling` | Kubernetes Events / collected diagnostic logs | Why nodes were rejected |
| Node Ready/NotReady | `kubectl`, Azure Monitor, AKS monitoring | Capacity health |
| Node pool count | Azure CLI, Azure Monitor metrics | Does the pool have enough nodes / can it scale? |
| CPU/memory requests and usage | `kubectl describe node`, metrics server/Container insights | Risk of capacity shortage or overcommit |
| Pod distribution across nodes/zones | `kubectl get pods -o wide`, labels/metrics | Concentration risk and HA posture |
| Evictions/Spot interruptions | Events, AKS logs, Azure/VM signals | Stability of workloads on Spot |
| Changes to taints/labels/Deployments | Kubernetes audit and Azure Activity Log per scope | Trace scheduling policy modifications |
| Node pool costs | Azure Cost Management | Are dedicated/Spot/on-demand pools cost-effective? |

Kube-scheduler runs inside the AKS-managed control plane, so you may not always have direct access to all scheduler logs. Use Kubernetes Events and AKS-supported diagnostic categories per your cluster configuration.

### 16.2. Illustrative KQL for Kubernetes Events

If Azure Monitor/Container insights sends data to a Log Analytics workspace with the `KubeEvents` table:

~~~kusto
KubeEvents
| where TimeGenerated > ago(1h)
| where Reason == "FailedScheduling"
| summarize Events=count() by bin(TimeGenerated, 5m), Namespace
| order by TimeGenerated asc
~~~

Table and column names depend on your active schema and ingestion config. Verify against your live workspace, and never treat an empty query result as proof of zero scheduling errors if Event collection is not enabled.

Some setups require extracting PodName, ObjectName, or event messages from different columns depending on integration. Never build alerts against an assumed schema without testing against real events.

### 16.3. Recommended Alerts

- Pods Pending longer than the workload SLA tolerance.
- Spike in `FailedScheduling` events following a deployment.
- Dedicated pool out of capacity or autoscaler hitting max count.
- Node `NotReady`, Spot evictions, or workload losing Ready replicas.
- Pod distribution concentrating onto a single zone/node contrary to design.
- Changes to node taints, node labels, or priority/affinity outside change windows.
- Dedicated node pool incurring high cost with sustained low utilization.

Monitoring should tie **scheduling signals to application impact**: a low-priority Pod Pending briefly may be acceptable; a payment API replica Pending during a zone outage can be a critical incident.

## 17. Real-World Scenario: Combining Order API, Batch, and System Workloads

An enterprise runs AKS on Azure with three workload tiers:

1. **System:** CoreDNS and critical cluster components.
2. **Orders API:** customer-facing service needing multiple replicas and high availability.
3. **Nightly batch:** heavy reporting jobs that can wait and run on a separate pool to avoid resource contention.

### 17.1. Node Pool Planning

| Pool | Type | Labels/Taints | Intended Workloads |
|---|---|---|---|
| `systempool` | System | AKS-managed labels/taints and vetted system policies | Add-ons and system components |
| `apppool` | User, on-demand, multi-zone if supported | `workload=frontend`, optional taint for dedication | Orders API and transactional services |
| `batchpool` | User, on-demand or Spot per workload | `workload=batch`; `workload=batch:NoSchedule` | Nightly batch workers |

Verify that system DaemonSets and monitoring/security agents carry necessary tolerations across all pools. Do not blindly block all system Pods from user pools; some DaemonSets must run on application nodes to provide networking, storage, or monitoring.

### 17.2. Placement Rules for Orders API

Orders API can use:

- Well-measured requests.
- Required `nodeAffinity` or `nodeSelector` targeting `apppool` if design requires dedicated placement.
- Matching toleration if `apppool` is tainted.
- Preferred `podAntiAffinity` by hostname.
- Zone `topologySpreadConstraints` when multiple zones are available.
- HPA on validated metrics and autoscaler on `apppool`.
- PodDisruptionBudget to protect against voluntary disruptions.

If `apppool` lives in a single zone, topology spread cannot manufacture zone fault tolerance. Proactively design multi-zone node pools where regions/SKUs support them.

### 17.3. Placement Rules for Batch

Batch workers:

- Enter only `batchpool` via required `nodeAffinity`.
- Accept the batch taint via toleration.
- Declare CPU/memory requests reflecting real load.
- Never access production data outside authorized scope.
- Implement retries/idempotency; use Spot only if jobs tolerate interruption.
- Have completion/deadline behavior; do not keep a permanent Deployment if the task is a periodic one-off—consider CronJob/Job.

### 17.4. When a Zone Is Lost

Suppose Zone A loses several nodes:

1. Affected nodes transition to `NotReady` or report unhealthy conditions.
2. Impacted Pods lose readiness or are evicted per Kubernetes mechanics.
3. Deployment controllers attempt to create replacement replicas.
4. The scheduler evaluates affinity, taints, spread, PVC topology, and resources on surviving nodes.
5. The autoscaler may add nodes if eligible pools have capacity.
6. If hard rules are overly rigid, some Pods stay Pending, lengthening recovery time.
7. Teams monitor p95 API latency, error rate, Ready replicas, and overall application health.

Operational lesson: **good spread must go hand-in-hand with recovery resilience under node loss**, not just look tidy on a dashboard while all zones are healthy.

## 18. Change and Rollback Procedures for Scheduling Policies

### 18.1. Before Changing a Node Pool Taint

1. Inventory all workloads currently running on the pool, including DaemonSets.
2. Identify Pods lacking a matching toleration.
3. Evaluate `NoSchedule` vs `NoExecute`; `NoExecute` can evict existing Pods.
4. Check spare capacity elsewhere and autoscaler bounds.
5. Test on lab/staging or a new pool first.
6. Back up IaC/manifest configs and prepare a rollback plan.
7. Enable alerts for Pending Pods, Ready replicas, and node health during the change window.
8. Follow change approval; avoid altering multiple constraints at once unnecessarily.

### 18.2. Before Changing Deployment Affinity

1. Compare existing node labels against the new rule.
2. Check replica counts against eligible nodes/zones.
3. Estimate requests and pool capacity to absorb new Pods.
4. For rolling updates, check `maxSurge`/`maxUnavailable` and PDBs.
5. Deploy a single test replica or appropriate canary first.
6. Watch `FailedScheduling`, rollout status, and Ready Pods.
7. If the policy is too restrictive, roll back the Deployment manifest to the previous rule.

Note: editing a Deployment's Pod template creates a new ReplicaSet; old Pods do not magically move nodes just because a new manifest changed `nodeAffinity`. Verify the live rollout and actual Pod placement rather than reading applied YAML alone.

### 18.3. Lab Cleanup

After testing, delete only resources you are certain were created for the lab and contain no workloads/data to keep. Before deleting a node pool, check running Pods, drain behavior, and whether deletion removes essential cluster system capacity.

For VM Scale Set-backed node pools, deleting a pool deletes its underlying nodes. This is a destructive operation—**never perform it in production just to clean up an exercise**.

## 19. Pre-Production Checklist

### Placement Design

- [ ] Classified workloads by SLA, data sensitivity, CPU/memory, GPU, and interruption tolerance.
- [ ] System/User, on-demand/Spot node pools and zones are clearly architected.
- [ ] Labels follow consistent conventions; mutable labels are not used for critical trust decisions.
- [ ] Distinguished required vs preferred affinity.
- [ ] Taints block unsuitable Pods, and tolerations are granted only when needed.
- [ ] Workloads needing dedicated placement carry both matching affinity and tolerations.
- [ ] HA replicas use appropriate anti-affinity or topology spread.
- [ ] PVCs, node storage/zones, and network topology do not conflict with placement.
- [ ] Resource requests/limits reflect actual load; affinity is not used to mask resource shortages.

### Testing

- [ ] Verified actual node labels/taints via `kubectl`.
- [ ] Verified `FailedScheduling` events when deliberately omitting a toleration in lab.
- [ ] Confirmed Pods actually land on expected pools/zones.
- [ ] Tested scale-out when a pool fills up, including quotas and `maxCount`.
- [ ] Rehearsed node/zone loss per approved test plan.
- [ ] Verified rollouts/PDBs/evictions and application readiness.
- [ ] Alerts configured for Pending Pods or insufficient node/pool capacity.
- [ ] Rollback plan ready if labels/taints or required affinity are misconfigured.

### Operations and Cost

- [ ] Clear owners assigned for node pools and scheduling manifests.
- [ ] Taint/label/affinity changes managed via IaC/GitOps with peer review.
- [ ] Least-privilege permissions enforced on node and node pool edits.
- [ ] Pod distribution and node pool utilization monitored over time.
- [ ] Budgets set for dedicated pools and autoscalers.
- [ ] Spot is never used for workloads that cannot tolerate eviction.
- [ ] Hard rules periodically audited to prevent Pending states or overprovisioning.

## 20. Self-Check Questions

1. **How do `nodeSelector` and `nodeAffinity` differ?** `nodeSelector` is a simple mandatory label match; `nodeAffinity` supports expressive required or preferred rules.
2. **What does `requiredDuringSchedulingIgnoredDuringExecution` mean?** Nodes must match at scheduling time; running Pods are not automatically evicted if labels change later.
3. **What percentage of Pods does preferred affinity guarantee on preferred nodes?** No percentage guarantee; `weight` only contributes points to scheduler scoring.
4. **Within a single `nodeSelectorTerm`, are `matchExpressions` combined with AND or OR?** AND; separate terms are combined with OR.
5. **What does `podAntiAffinity` by hostname do?** Prefers or requires matching Pods not to share the same node, depending on required vs preferred.
6. **Why can required anti-affinity leave a Pod Pending?** Because there are not enough distinct topology domains/nodes to place all replicas.
7. **What is a taint?** A condition attached to a node to repel, discourage, or evict Pods that do not tolerate it.
8. **How does `NoSchedule` differ from `NoExecute`?** `NoSchedule` blocks new scheduling; `NoExecute` can also evict existing Pods lacking a matching toleration.
9. **Does a toleration force a Pod onto the tainted node?** No. It only allows the Pod to be considered on that node.
10. **What should you combine for a dedicated node pool?** Pool labels + taints, Pod required `nodeAffinity`/`nodeSelector` + toleration, and RBAC/policy controls.
11. **What does `NoExecute` `tolerationSeconds` mean?** How long the Pod tolerates the matching taint before it may be evicted.
12. **Why should unbounded `Exists` tolerations be avoided?** They can allow Pods onto unintended or unhealthy nodes.
13. **What do `TopologySpreadConstraints` do?** Control replica skew across domains such as nodes or zones.
14. **How do `DoNotSchedule` and `ScheduleAnyway` differ?** One is a hard constraint, the other a soft preference when spread skew would be exceeded.
15. **Does a `System` mode node pool automatically isolate itself from all user Pods?** No. Placement still depends on scheduling rules, taints, and affinities.
16. **Can Cluster Autoscaler fix a Pod requiring a label missing from all pools?** Generally no; adding nodes to the wrong pool will not satisfy required placement.
17. **Why does the scheduler use requests instead of current CPU usage alone?** To reserve declared capacity and calculate placement deterministically.
18. **Does a Spot toleration prevent a Spot VM from being evicted?** No. Spot capacity can still be reclaimed by the underlying infrastructure.
19. **Does a PodDisruptionBudget ensure Pods sit across two zones?** No. It governs voluntary disruptions; placement is handled separately.
20. **What is the first step to diagnose a Pending Pod?** `kubectl describe pod` and `FailedScheduling` events, then compare node labels/taints, requests, topology, and volumes.
21. **Are taints a security boundary against all unauthorized Pods?** No; anyone able to edit a Pod spec can add a toleration, so RBAC/admission/network controls are needed.
22. **After changing affinity in a Deployment, do running Pods immediately move nodes?** No. New Pods/a new rollout must be created for the scheduler to apply the updated rule; old Pods do not migrate solely due to manifest/label changes.

## 21. References

- [Kubernetes: Assigning Pods to Nodes](https://kubernetes.io/docs/concepts/scheduling-eviction/assign-pod-node/) — `nodeSelector`, node affinity, pod affinity, and anti-affinity.
- [Kubernetes: Taints and Tolerations](https://kubernetes.io/docs/concepts/scheduling-eviction/taint-and-toleration/) — `NoSchedule`, `PreferNoSchedule`, `NoExecute`, and `tolerationSeconds`.
- [Kubernetes: Pod Topology Spread Constraints](https://kubernetes.io/docs/concepts/scheduling-eviction/topology-spread-constraints/) — `maxSkew` and `whenUnsatisfiable`.
- [Kubernetes: Scheduling Framework](https://kubernetes.io/docs/concepts/scheduling-eviction/scheduling-framework/) — filtering/scoring and extension points.
- [Kubernetes: Resource Management for Pods and Containers](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/) — CPU/memory requests and limits.
- [Kubernetes: Pod Priority and Preemption](https://kubernetes.io/docs/concepts/scheduling-eviction/pod-priority-preemption/) — workload priority.
- [Kubernetes: Pod Disruption Budgets](https://kubernetes.io/docs/concepts/workloads/pods/disruptions/) — voluntary disruptions and HA.
- [AKS: Node Pools](https://learn.microsoft.com/azure/aks/create-node-pools) — managing node pools, labels, taints, and modes.
- [AKS: Use Availability Zones](https://learn.microsoft.com/azure/aks/availability-zones) — zone-aware node pools and HA design.
- [AKS: Cluster Autoscaler](https://learn.microsoft.com/azure/aks/cluster-autoscaler) — scaling nodes for unschedulable Pods.
- [AKS: Spot node pools](https://learn.microsoft.com/azure/aks/spot-node-pool) — Spot terms and eviction behavior.
- [Monitor AKS](https://learn.microsoft.com/azure/aks/monitor-aks) — Events, Container insights, and Azure Monitor.
- [Azure Cost Management](https://learn.microsoft.com/azure/cost-management-billing/costs/) — controlling node pool and infrastructure costs.

**Conclusion:** good scheduling is not simply "pinning a Pod to a node." You must understand **`nodeAffinity` for choosing nodes**, **`podAffinity`/anti-affinity and topology spread for organizing replicas**, **taints for reserving node pools by purpose**, and **tolerations for permitting Pods into those pools**. In AKS, rules only work effectively when node pools, CPU/memory requests, zone capacity, autoscalers, storage topology, and security are aligned. Prioritize explicit design, verify via Kubernetes Events, and test failure scenarios before rolling out to production.
