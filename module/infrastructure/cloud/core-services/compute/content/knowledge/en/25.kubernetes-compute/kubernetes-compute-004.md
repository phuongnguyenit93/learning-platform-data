# Affinity, Anti-Affinity, and Topology Spread for Pods

In Kubernetes, the scheduler decides which node a pod will run on based on available resources, workload constraints, and cluster state. Relying solely on CPU/RAM can cause replicas of the same application to land on a single node or concentrate inside one zone. If that node or zone fails, many replicas can become unavailable simultaneously.

**Affinity** expresses where a pod should or must be placed based on labels of nodes or other pods. **Anti-affinity** expresses where a pod should or must not be co-located with another group of pods. **Topology spread constraints** help distribute similar pods relatively evenly across topology domains such as zones or hostnames.

In **CLOUD_CORE_SERVICES_COMPUTE**, these mechanisms help align workload placement with hardware capabilities, reduce single points of failure, and balance replicas across failure domains. You must choose the right constraint level: overly soft rules may fail to protect availability; overly strict rules can leave pods Pending even when the cluster still has spare CPU/RAM.

## 1. Scheduling and Topology in Kubernetes

The Kubernetes scheduler selects a node for unassigned pods. At a high level, the scheduler filters out nodes that fail mandatory requirements, scores the remaining nodes, and selects a node with a suitable score. Constraints around resources, taints/tolerations, affinity, topology spread, volumes, and policies can all influence the result.

### 1.1. Nodes, Pods, and Topology Domains

- **Node:** a worker machine running pods.
- **Pod:** the smallest deployable unit in Kubernetes, containing one or more containers.
- **Topology domain:** a group of nodes sharing the same value for a topology label.
- **Topology key:** the label name used to partition nodes into domains.
- **Replica:** a copy of a workload managed by a Deployment, StatefulSet, or another controller.

Common topology keys:

| Topology Key | Distribution Scope | Examples |
| --- | --- | --- |
| `kubernetes.io/hostname` | Individual node | `node-a`, `node-b`, `node-c` |
| `topology.kubernetes.io/zone` | Availability zone | `zone-a`, `zone-b`, `zone-c` |
| `topology.kubernetes.io/region` | Region | `region-1`, `region-2` |
| Custom label | Organization-defined domain | `rack`, `power-domain`, `node-pool` |

Nodes must carry the corresponding label for the scheduler to use it when determining topology. If some nodes lack `topology.kubernetes.io/zone`, they may not be counted as valid domains for zone-based constraints.

### 1.2. Why Pod Placement Matters

Suppose a Deployment has 6 replicas. If all 6 pods run on one node, that node becomes a single point of failure. If they are distributed across 3 zones, a single zone failure is far less likely to take down all replicas.

~~~mermaid
flowchart TB
    subgraph A["Concentrated distribution"]
      N1["Zone A / Node 1"]
      P1["Pod 1 · Pod 2 · Pod 3 · Pod 4"]
      N1 --> P1
    end
    subgraph B["Distribution across failure domains"]
      Z1["Zone A"] --> B1["Node A1: Pod 1, 2"]
      Z2["Zone B"] --> B2["Node B1: Pod 3, 4"]
      Z3["Zone C"] --> B3["Node C1: Pod 5, 6"]
    end
~~~

This is an illustration of placement. Topology spread does not create additional nodes or zones; the cluster must already have enough nodes, resources, quotas, and networking to place pods according to policy.

## 2. Types of Affinity and Anti-Affinity

Kubernetes provides three main categories:

1. **Node affinity:** selects nodes based on node labels.
2. **Pod affinity:** places a pod near or in the same topology domain as other pods matching a label selector.
3. **Pod anti-affinity:** avoids placing a pod in the same topology domain as other pods matching a label selector.

Node affinity inspects node attributes. Pod affinity and anti-affinity inspect the locations of existing pods or pods currently considered by the scheduler.

### 2.1. Required and Preferred

Affinity mechanisms offer two common constraint modes:

| Mode | Configuration Field | Meaning |
| --- | --- | --- |
| Required during scheduling | `requiredDuringSchedulingIgnoredDuringExecution` | The node must satisfy the rule; otherwise, the pod is not scheduled |
| Preferred during scheduling | `preferredDuringSchedulingIgnoredDuringExecution` | The scheduler adds preference score weight; if no node matches, the pod can still be placed elsewhere |

The **IgnoredDuringExecution** portion means the scheduler evaluates the rule at scheduling time. If labels change after the pod is already running, Kubernetes does not automatically evict the pod simply because the affinity rule no longer holds.

With preferred affinity, each preference carries a **weight** from 1 to 100. A higher weight contributes more points during scoring; it is not a percentage and does not guarantee the pod will always land on the preferred node.

## 3. Node Affinity: Selecting Nodes by Attributes

Node affinity fits when a workload needs a group of nodes with specific traits, such as:

- CPU-optimized or memory-optimized hardware.
- GPUs/accelerators.
- Local SSDs or specialized devices.
- Node pools dedicated to trusted workloads.
- Supported CPU architectures or operating systems.

Labels may be attached by the cloud provider, Kubernetes, or platform teams. Some standard labels include:

- `kubernetes.io/arch`
- `kubernetes.io/os`
- `node.kubernetes.io/instance-type`
- `topology.kubernetes.io/zone`
- `topology.kubernetes.io/region`

### 3.1. Required Node Affinity

Example where a pod can only run on nodes with the label `workload-tier=compute`:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: cpu-worker
  labels:
    app: cpu-worker
spec:
  affinity:
    nodeAffinity:
      requiredDuringSchedulingIgnoredDuringExecution:
        nodeSelectorTerms:
          - matchExpressions:
              - key: workload-tier
                operator: In
                values:
                  - compute
  containers:
    - name: worker
      image: example.invalid/cpu-worker:v1
      resources:
        requests:
          cpu: "1"
          memory: "1Gi"
~~~

This is a structural YAML example; replace the image with a real image before deploying. If no node carries `workload-tier=compute` or those nodes lack sufficient resources, the pod will remain Pending.

### 3.2. Node Selector Expressions

Common operators in `matchExpressions`:

| Operator | Meaning |
| --- | --- |
| `In` | Label value must be in the list |
| `NotIn` | Label value must not be in the list |
| `Exists` | Node must have a label with that key |
| `DoesNotExist` | Node must not have that label key |
| `Gt` | Numeric label value must be greater than the comparison value |
| `Lt` | Numeric label value must be less than the comparison value |

Within a single `nodeSelectorTerm`, expressions are combined with AND. Multiple `nodeSelectorTerms` are combined with OR. You can combine multiple expressions to require a node belonging to the `compute` pool with a compatible CPU architecture.

Example:

~~~yaml
nodeAffinity:
  requiredDuringSchedulingIgnoredDuringExecution:
    nodeSelectorTerms:
      - matchExpressions:
          - key: workload-tier
            operator: In
            values: ["compute"]
          - key: kubernetes.io/arch
            operator: In
            values: ["amd64"]
      - matchExpressions:
          - key: workload-tier
            operator: In
            values: ["compute"]
          - key: kubernetes.io/arch
            operator: In
            values: ["arm64"]
~~~

The two terms above allow nodes in the `compute` pool with either `amd64` or `arm64` architecture. The application image must support both architectures if you intend to use both node groups.

### 3.3. Preferred Node Affinity

When a workload can run across multiple node types but prefers a particular group, use `preferred`:

~~~yaml
affinity:
  nodeAffinity:
    preferredDuringSchedulingIgnoredDuringExecution:
      - weight: 80
        preference:
          matchExpressions:
            - key: storage-tier
              operator: In
              values: ["ssd"]
      - weight: 30
        preference:
          matchExpressions:
            - key: node-pool
              operator: In
              values: ["batch"]
~~~

The scheduler favors nodes with higher matching scores while retaining the option to pick other nodes if necessary. If the workload strictly requires SSDs for correctness or SLO compliance, use `required` instead of relying only on `preferred`.

### 3.4. Node Affinity and nodeSelector

`nodeSelector` is a simple way to require nodes with a set of key/value labels. `nodeAffinity` expresses richer rules, including multiple operators and weighted preferences.

Both can be used together; in that case, a node must satisfy both `nodeSelector` and `nodeAffinity`. If the rules conflict, the pod cannot be scheduled.

## 4. Pod Affinity: Placing Pods Near Other Pods

Pod affinity lets the scheduler locate nodes in topology domains already hosting pods matching a label selector. Examples:

- Placing workers in the same zone as cache replicas to reduce network latency.
- Placing helper sidecars/services on the same node or zone as the workload that depends on them.
- Placing data-processing pods near pods holding data shards.

Pod affinity does not mean two pods must sit on the exact same node. The scope is determined by `topologyKey`:

- `kubernetes.io/hostname`: same node.
- `topology.kubernetes.io/zone`: same zone.
- Rack or failure domain label: same custom domain.

### 4.1. Required Pod Affinity

Example where a worker must run in the same zone as `cache` pods in the `platform` namespace:

~~~yaml
affinity:
  podAffinity:
    requiredDuringSchedulingIgnoredDuringExecution:
      - labelSelector:
          matchLabels:
            app: cache
        namespaces:
          - platform
        topologyKey: topology.kubernetes.io/zone
~~~

The scheduler finds topology domains containing `app=cache` pods in namespace `platform`, then considers only nodes in matching domains. If no matching cache pod exists or nodes lack the required topology label, the rule cannot be satisfied.

### 4.2. Preferred Pod Affinity

If you want to prefer the same zone while still allowing placement elsewhere when nodes are scarce:

~~~yaml
affinity:
  podAffinity:
    preferredDuringSchedulingIgnoredDuringExecution:
      - weight: 60
        podAffinityTerm:
          labelSelector:
            matchLabels:
              app: cache
          namespaces:
            - platform
          topologyKey: topology.kubernetes.io/zone
~~~

Pod affinity can create startup ordering dependencies. If one workload must be co-located in the same topology as a pod from another workload that has not been created or scheduled yet, the pod may wait. Kubernetes has special handling for certain self-affinity cases so the first pod of a group can start; however, do not rely on that mechanism to resolve dependencies between two independent workloads. For replica groups that should bootstrap independently, consider topology spread or preferred affinity.

### 4.3. Namespaces and Label Selectors

Pod affinity/anti-affinity can scope which pods are matched using:

- `labelSelector`: selects pods by labels.
- `namespaces`: list of namespaces to consider.
- `namespaceSelector`: selects namespaces by labels.

If no namespace scope is declared, the selector defaults to pods in the namespace of the pod being scheduled. Specify namespaces explicitly to avoid accidentally creating affinity relationships with unrelated workloads.

## 5. Pod Anti-Affinity: Keeping Replicas Out of the Same Failure Domain

Pod anti-affinity specifies where a pod should not or must not be placed alongside pods matching a label selector. This is an essential mechanism for spreading a service's replicas.

For example, if two pods of the same application must not run on the same hostname, you can use:

~~~yaml
affinity:
  podAntiAffinity:
    requiredDuringSchedulingIgnoredDuringExecution:
      - labelSelector:
          matchLabels:
            app: checkout
        topologyKey: kubernetes.io/hostname
~~~

This rule prevents the scheduler from placing a new pod on a node already hosting an `app=checkout` pod within the same topology domain. When the topology key is hostname, each node hosts at most one pod matching the selector under that constraint.

### 5.1. Required Anti-Affinity

Required anti-affinity is a hard constraint. It is useful when non-colocation is mandatory, such as:

- Replicas requiring node independence to limit the blast radius of a node failure.
- Workloads requiring per-host separation due to licensing or resource limits.
- Components with severe resource-contention risks if placed on the same node.

In return, the maximum runnable pod count is bounded by the number of eligible topology domains. If a Deployment has 5 replicas but only 4 eligible nodes and requires at most one replica per hostname, at least one pod will remain Pending.

### 5.2. Preferred Anti-Affinity

If spreading is desirable but not absolute, use `preferred`:

~~~yaml
affinity:
  podAntiAffinity:
    preferredDuringSchedulingIgnoredDuringExecution:
      - weight: 100
        podAffinityTerm:
          labelSelector:
            matchLabels:
              app: checkout
          topologyKey: kubernetes.io/hostname
~~~

The scheduler tries to select nodes without pods of the same application, yet when options are scarce, it can still place multiple replicas on one node. This improves schedulability and capacity utilization.

### 5.3. Anti-Affinity by Zone

You can set `topologyKey` to `topology.kubernetes.io/zone` to avoid sharing a zone. However, required anti-affinity by zone means pods matching the selector cannot share a zone at all. With 3 replicas and 3 zones, each zone can host only one replica. With 4 replicas, the fourth replica cannot be scheduled under this constraint.

To achieve balanced distribution across zones, topology spread is generally a better fit than hard anti-affinity. Zone-level anti-affinity should only be used when you genuinely need each pod isolated in a different zone.

### 5.4. Scheduler Limits and Overhead

Pod anti-affinity requires the scheduler to evaluate relationships between pods and topology domains. In large clusters with many pods and broad selectors, this evaluation can increase scheduling latency. Use narrow selectors, only the necessary topology keys, and `required` rules only when business requirements truly demand them.

Some clusters also enforce admission policies restricting which topology keys can be used with required pod anti-affinity. Check cluster policies if a valid manifest is rejected at creation time.

## 6. Topology Spread Constraints

Topology spread constraints distribute pods matching a selector more evenly across topology domains. Instead of completely forbidding two pods in the same domain like required anti-affinity, spread bounds the difference in pod counts across domains.

For example, 7 replicas across 3 zones can be distributed as 3-2-2. The skew between the domain with the most pods and the domain with the fewest is 1.

### 6.1. Key Fields

| Field | Meaning |
| --- | --- |
| `maxSkew` | Maximum permitted difference between domains with the most and fewest pods per scheduler calculation |
| `topologyKey` | Node label used to partition topology domains |
| `whenUnsatisfiable` | Action to take if placement would exceed `maxSkew` |
| `labelSelector` | Selects the group of pods counted in each domain |
| `minDomains` | Minimum desired number of topology domains in certain spread scenarios |
| `nodeAffinityPolicy` | Determines whether node affinity/selector applies when computing eligible domains, if supported by the cluster version |
| `nodeTaintsPolicy` | Determines whether taints/tolerations are considered when computing eligible domains, if supported by the cluster version |

`maxSkew` is a positive integer, minimum 1. `topologyKey` must exist on relevant nodes. `labelSelector` should accurately select the pods belonging to the workload you want to spread.

### 6.2. DoNotSchedule and ScheduleAnyway

`whenUnsatisfiable` has two options:

- **DoNotSchedule:** if placing the pod into a domain would cause skew to exceed `maxSkew`, the scheduler will not place the pod on that node. The pod may remain Pending until a suitable domain or capacity becomes available.
- **ScheduleAnyway:** the scheduler can still place the pod even if skew exceeds the target, while prioritizing nodes that improve balance. This is a preference, not an absolute distribution guarantee.

Choose `DoNotSchedule` when distribution is a hard availability requirement and the organization accepts Pending pods if domains are lacking. Choose `ScheduleAnyway` when good distribution is desired while prioritizing keeping workloads runnable.

### 6.3. Understanding maxSkew

Suppose there are 3 eligible zones and 6 pods matching the selector:

| Zone | Pod Count |
| --- | ---: |
| `zone-a` | 2 |
| `zone-b` | 2 |
| `zone-c` | 2 |

The skew is 2 - 2 = 0. With 7 pods, a 3-2-2 distribution has a skew of 1.

With `maxSkew: 1`, the scheduler aims to keep the difference at most 1 when using `DoNotSchedule`. If only two zones remain eligible while `minDomains: 3` is set, the global minimum calculation can prevent the scheduler from adding another pod to a domain that already has pods if doing so exceeds the skew threshold. This helps avoid concentrating replicas into fewer zones than intended, though it can reduce runnable capacity when a zone fails.

### 6.4. minDomains

`minDomains` specifies the minimum number of eligible domains for spread calculation. When the count of eligible domains is lower than `minDomains`, the global minimum is treated as 0 for skew calculation. This field is only used with `whenUnsatisfiable: DoNotSchedule` and requires a supporting cluster version.

For example, `minDomains: 3` expresses the intent to require at least three eligible domains to satisfy the spread policy. If only two zones remain, pods may stay Pending rather than concentrating into the remaining two zones. This is an explicit availability/capacity trade-off.

If the goal is to keep serving when one zone fails, evaluate `minDomains`, replica count, remaining capacity, and whether temporary skew is acceptable.

### 6.5. Eligible Topology Domains

The scheduler does not blindly count every node in the cluster. The set of eligible nodes can be affected by:

- The pod's `nodeSelector` and node affinity.
- Taints/tolerations according to the topology spread policy.
- Whether nodes carry the required topology key label.
- Other constraints preventing nodes from accepting the pod.

If a zone has no nodes matching the pod's node affinity, that zone is not necessarily counted as a domain capable of receiving pods. When debugging, check node labels and eligibility rules rather than looking solely at the zone list in a cloud console.

## 7. Deployment Example Spreading Replicas Across Zones and Nodes

The following manifest illustrates an API with 6 replicas:

- Runs only on the `workload-tier=compute` node pool.
- Must spread relatively evenly across at least 3 zones.
- Prefers spreading across different hostnames.

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: checkout
  labels:
    app: checkout
spec:
  replicas: 6
  selector:
    matchLabels:
      app: checkout
  template:
    metadata:
      labels:
        app: checkout
    spec:
      affinity:
        nodeAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            nodeSelectorTerms:
              - matchExpressions:
                  - key: workload-tier
                    operator: In
                    values:
                      - compute
      topologySpreadConstraints:
        - maxSkew: 1
          minDomains: 3
          topologyKey: topology.kubernetes.io/zone
          whenUnsatisfiable: DoNotSchedule
          labelSelector:
            matchLabels:
              app: checkout
        - maxSkew: 1
          topologyKey: kubernetes.io/hostname
          whenUnsatisfiable: ScheduleAnyway
          labelSelector:
            matchLabels:
              app: checkout
      containers:
        - name: api
          image: registry.example.invalid/checkout:v3
          ports:
            - name: http
              containerPort: 8080
          resources:
            requests:
              cpu: "500m"
              memory: "512Mi"
            limits:
              cpu: "2"
              memory: "2Gi"
~~~

The image registry in this example is a placeholder; replace it with a valid image before applying. `minDomains` requires a Kubernetes version that supports this field. If the cluster does not support it yet, omit the field or adjust the policy to match the actual cluster version.

With three zones containing eligible nodes, 6 replicas can distribute 2-2-2. The hostname constraint in `ScheduleAnyway` mode lets the scheduler prefer distinct nodes while still allowing extra replicas on the same node if choices are limited.

If you strictly require at most one replica per node, replace the hostname spread with required pod anti-affinity. However, whenever the replica count exceeds the number of eligible nodes, excess pods will remain Pending.

## 8. Combining Node Affinity, Pod Anti-Affinity, and Topology Spread

Each mechanism answers a different question:

| Mechanism | Question |
| --- | --- |
| Node affinity | Which type of node can the pod run on? |
| Pod affinity | Which group of pods should the pod stay near? |
| Pod anti-affinity | Which group of pods should or must the pod avoid sharing a domain with? |
| Topology spread | How evenly should replicas be distributed across domains? |

Multiple mechanisms can be combined in the same pod spec. The scheduler must find a node that satisfies all mandatory constraints; preferences only influence scoring.

Design example:

- Required node affinity picks a node pool with the right CPU profile.
- Preferred pod anti-affinity reduces the chance of two replicas sharing a node.
- `DoNotSchedule` topology spread limits replica skew across zones.

Avoid stacking multiple hard constraints that target the same goal at conflicting scopes. For example, required hostname anti-affinity alongside `DoNotSchedule` hostname topology spread can be redundant; required zone anti-affinity combined with `minDomains` can make a workload unschedulable when a zone goes down.

## 9. How Affinity and Topology Spread Affect Autoscaling

The scheduler only chooses among existing eligible nodes. Cluster Autoscaler or node provisioning mechanisms can add nodes when pods are Pending due to insufficient resources, but not every constraint can be solved by adding nodes.

### 9.1. When the Autoscaler Can Help

- The node pool is allowed to scale out.
- The cloud provider has remaining quota and capacity.
- Pod resource requests fit within node pool machine limits.
- New topology domains can be provisioned with matching labels.
- Affinity/spread constraints can be satisfied by new nodes.

### 9.2. When the Autoscaler Cannot Solve It

- Required anti-affinity demands a dedicated node/domain, but the node pool has hit its maximum size.
- Pods require a zone that has no remaining capacity.
- Node affinity selects labels absent from every node pool.
- A PVC is bound to a different zone from where the pod is permitted to run.
- A node taint has no matching toleration.
- Quotas or IP subnet space are exhausted.
- `minDomains` requires more domains than can be provisioned.

An autoscaler cannot invent a new physical topology domain if the cloud region does not offer that zone or the provider lacks capacity.

## 10. Interactions with Deployment, HPA, and PodDisruptionBudget

### 10.1. Deployment Rollouts

During a Deployment rolling update, the scheduler may need to place new pods while old pods are still running. If you use required hostname anti-affinity allowing only one replica per node, and `maxSurge` creates new pods before old pods terminate, new pods can go Pending because no free node exists.

Solutions:

- Ensure spare nodes/capacity exist for rollout surge.
- Choose appropriate `maxSurge` and `maxUnavailable` settings.
- Use preferred anti-affinity if the constraint does not need to be absolute.
- Use topology spread to balance replicas while keeping placement controlled.
- Test rollouts at minimum node count, not only when the cluster has excess capacity.

### 10.2. Horizontal Pod Autoscaler

HPA adjusts replica counts based on metrics. When replicas scale up, topology spread and affinity determine where new pods can run.

If HPA scales from 3 to 12 while only 3 eligible nodes exist and required anti-affinity allows one pod per hostname, at most 3 pods can run. HPA may still show desired replicas as 12 while many pods sit Pending.

Monitor together:

- HPA desired/current replicas.
- Deployment available/ready replicas.
- Pending pods and scheduler events.
- Node pool desired/actual capacity.
- Topology distribution by zone and hostname.

### 10.3. PodDisruptionBudget

A PodDisruptionBudget (PDB) limits how many pods can be disrupted during supported voluntary disruptions, such as node drains. A PDB does not determine where pods are placed and does not replace affinity or topology spread.

A PDB also does not protect against involuntary disruptions such as node crashes or zone outages. Design must combine replicas, placement, readiness, autoscaling, and PDBs.

## 11. Stateful Workloads and Volume Topology

For StatefulSets or pods using PersistentVolumes, placement is also constrained by storage topology.

- Some block volumes can only attach within a single zone.
- A PersistentVolume may carry node affinity or topology constraints.
- Pods may be pinned to run in the same zone as their volume.
- Database replicas may require a separate volume per pod.

If topology spread requires distributing pods across three zones while a volume exists only in `zone-a`, the scheduler cannot move the pod attached to that volume into `zone-b` or `zone-c`. Use an appropriate `StorageClass` and volume binding mode, such as `WaitForFirstConsumer` when suitable, so volumes are provisioned where pods are scheduled.

Do not arbitrarily relocate StatefulSet pods just to balance zones. Verify replication, quorum, consistency, volume attachment, and database failover procedures before changing placement.

## 12. Label Security and Node Isolation

Node affinity can separate sensitive workloads from general node pools. However, if workload users can attach labels to nodes themselves or alter trusted labels, they can defeat isolation goals.

For security requirements:

- Restrict via RBAC who can modify node labels.
- Use admission policies to govern pod affinity and `nodeSelector`.
- Use dedicated labels for node isolation under appropriate protection mechanisms.
- Consider the `NodeRestriction` admission plugin and labels with domains ending in `.node-restriction.kubernetes.io`, such as `example.com.node-restriction.kubernetes.io/fips`, when the plugin is enabled and properly configured.
- Combine taints/tolerations, namespace policies, and network policies.
- Never treat node affinity as the sole security boundary.

Taints/tolerations and affinity serve different roles: a taint with `NoSchedule` or `NoExecute` blocks pods lacking a matching toleration; `PreferNoSchedule` is only a preference to avoid the node. A toleration lets a pod be considered on a tainted node but does not make the pod prefer that node. Affinity is the mechanism that selects or prefers placement.

## 13. Inspecting Topology and Placement in a Cluster

Before applying policies, inspect node labels:

~~~bash
kubectl get nodes --show-labels

kubectl get nodes \
  -L topology.kubernetes.io/zone,kubernetes.io/hostname,workload-tier
~~~

Inspect pod placement:

~~~bash
kubectl get pods -n production -l app=checkout -o wide
kubectl get deployment checkout -n production
kubectl rollout status deployment/checkout -n production
~~~

If pods are Pending, inspect descriptions and events:

~~~bash
kubectl describe pod POD_NAME -n production
kubectl get events -n production --sort-by=.lastTimestamp
~~~

Common messages:

| Event/Reason | Cause to Check |
| --- | --- |
| `didn't match Pod's node affinity/selector` | Nodes lack the label or fail node affinity |
| `didn't match pod anti-affinity rules` | Required anti-affinity could not find an eligible node |
| `didn't match pod topology spread constraints` | Placement would violate `maxSkew` with `DoNotSchedule` |
| `Insufficient cpu` / `Insufficient memory` | Eligible nodes lack enough remaining resource requests |
| `untolerated taint` | Pod lacks a toleration or node pool does not match |
| `Volume node affinity conflict` | Pod and persistent volume require incompatible topologies |

Do not strip away every constraint the moment you see a Pending pod. First identify which constraint prevented scheduling and why that constraint was put in place.

## 14. Scenario-Based Troubleshooting

### 14.1. Pod Pending Despite Free CPU in the Cluster

Free CPU/RAM on a node does not mean the node is eligible. Check node affinity, taints/tolerations, pod anti-affinity, topology spread, volume topology, and resource requests.

### 14.2. Replicas Concentrated in One Zone

Check:

- Do nodes consistently have `topology.kubernetes.io/zone` labels?
- Does `labelSelector` accurately match the pod template labels?
- Is `whenUnsatisfiable` set to `ScheduleAnyway`?
- Is node affinity excluding the other zones?
- Do the other zones have eligible nodes and sufficient resources?
- Is `minDomains` set and appropriate when a zone fails?

When using `ScheduleAnyway`, skewed distribution is permitted if the scheduler has no better option.

### 14.3. Deployment Rollout Stalled

If new pods are Pending due to anti-affinity, check eligible node counts, `maxSurge`, `maxUnavailable`, and current replica counts. You may need to temporarily increase node capacity or switch to preferred anti-affinity if a hard constraint is unnecessary.

### 14.4. Pods Do Not Shift to Other Zones During a Zone Outage

Check whether surviving zones have enough nodes, CPU/RAM, IPs, and storage. If `minDomains` requires three domains while only two remain, `DoNotSchedule` can keep pods Pending. That is policy behavior, not necessarily a scheduler bug.

### 14.5. Pod Affinity Creates a Startup Dependency

If a pod requires another pod that does not exist yet, required affinity can block scheduling. Consider starting the dependency first, using preferred affinity, or switching to topology spread if the goal is replica distribution rather than co-location.

## 15. Choosing the Right Mechanism for Each Goal

| Goal | Recommended Mechanism | Notes |
| --- | --- | --- |
| Run only on GPU nodes | Required node affinity | Combine with resource requests/extended resources and taints/tolerations |
| Prefer nodes with SSDs | Preferred node affinity | Use required if SSDs are mandatory |
| Co-locate workers in the same zone as cache | Zone-level pod affinity | Manage namespace scope and startup dependencies |
| Never place two replicas on the same node | Required hostname pod anti-affinity | Needs at least as many eligible nodes as replicas |
| Prefer spreading replicas across nodes | Preferred pod anti-affinity | Lets the scheduler use remaining capacity when needed |
| Balance replicas across zones | Zone topology spread | `DoNotSchedule` is strict; `ScheduleAnyway` is flexible |
| Balance across nodes within each zone | Hostname topology spread | Combine with zone spread when needed |
| Pin sensitive workloads to trusted nodes | Required node affinity with protected labels | Combine with RBAC, admission policies, and taints |

## 16. Placement Policy Design Process

1. **Define the goal:** performance, hardware, isolation, or availability.
2. **Choose failure domains:** node, rack, zone, or region.
3. **Verify labels:** confirm topology keys and node pool labels.
4. **Select hard/soft constraints:** `required` when non-compliance must block execution; `preferred` for scoring preference.
5. **Write exact selectors:** `labelSelector` must target the right pod group, and namespaces must be properly scoped.
6. **Size capacity:** replica counts, eligible nodes, CPU/RAM requests, max nodes, and quotas.
7. **Evaluate failure modes:** if one node or one zone is lost, how many domains remain?
8. **Check rollouts/HPA:** verify surge and scale-out will not create unexpected Pending pods.
9. **Check storage:** verify volume topology aligns with placement.
10. **Test and observe:** deploy pods, scale replicas, drain nodes, and simulate zone unavailability in staging.
11. **Measure results:** actual distribution, Pending duration, cross-node/zone latency, and resource utilization.
12. **Tune:** update policies based on SLOs, capacity, and test results.

## 17. Common Mistakes

- Applying required anti-affinity to every replica without enough nodes.
- Using hard zone anti-affinity when the goal is simply balanced distribution.
- Using `ScheduleAnyway` and expecting perfectly even distribution at all times.
- Setting `maxSkew` too low without spare capacity.
- Setting `minDomains` higher than the number of domains available during failure scenarios.
- Mismatching `labelSelector` against pod template labels so the scheduler counts the wrong pod group.
- Nodes missing topology labels or having inconsistent labels.
- Node affinity accidentally filtering out every node in a zone.
- Overlooking taints/tolerations and volume topology.
- Using affinity as a substitute for network policies or security boundaries.
- Ignoring `maxSurge` during rolling updates with hard anti-affinity.
- Assuming an autoscaler can always add nodes in every zone.
- Ignoring events and looking only at CPU/RAM when pods stay Pending.

## 18. Pre-Production Placement Policy Checklist

**Topology**

- [ ] Nodes carry required and consistent zone/hostname labels.
- [ ] Target failure domains for spreading are clearly defined.
- [ ] Enough eligible nodes exist across domains.
- [ ] Single-node and single-zone loss scenarios are accounted for.

**Affinity**

- [ ] Node affinity selects the intended node pools and architectures.
- [ ] Pod affinity uses exact selectors and namespace scopes.
- [ ] Required pod anti-affinity is used only when strictly necessary.
- [ ] Preferred weights reflect actual priority.
- [ ] Security-sensitive labels cannot be tampered with by untrusted workloads.

**Topology Spread**

- [ ] `maxSkew` fits the replica count and domain count.
- [ ] `topologyKey` exists on eligible nodes.
- [ ] `labelSelector` selects the exact workload.
- [ ] `DoNotSchedule` vs. `ScheduleAnyway` is chosen deliberately.
- [ ] `minDomains` aligns with the zone-failure strategy.
- [ ] Optional fields are supported by the cluster version.

**Operations**

- [ ] Pending events and scheduler behavior have been verified.
- [ ] Rolling updates/HPA have adequate capacity.
- [ ] PVC/PV topology is compatible.
- [ ] Autoscalers and quotas support the required node pools.
- [ ] PDBs, readiness probes, and disruption plans are configured separately.
- [ ] Dashboards track pod distribution by zone and hostname.

## 19. Operational Principles

1. **Use node affinity to select hardware and node pools:** distinguish mandatory requirements from preferences.
2. **Use pod affinity for targeted co-location:** only when proximity yields measurable benefit.
3. **Use pod anti-affinity to separate workloads:** `required` when non-colocation is a hard rule; `preferred` when flexibility is needed.
4. **Use topology spread to balance replicas:** select zone or hostname as the topology key.
5. **Understand `maxSkew` and `minDomains`:** they directly govern schedulability when domains are missing.
6. **Ensure accurate labels:** selectors and topology labels dictate which domains the scheduler counts and chooses.
7. **Calculate capacity before enforcing hard constraints:** node/domain counts must accommodate replicas and rollouts.
8. **Coordinate with autoscaling and storage:** the scheduler cannot bypass quotas, invent zones, or move volumes beyond platform capabilities.
9. **Inspect Pending events and actual distribution:** free CPU does not guarantee a node is eligible.
10. **Test failure scenarios:** verify workloads keep serving when a node or zone goes down.

Affinity, anti-affinity, and topology spread control placement at complementary levels. Node affinity selects node types, pod affinity/anti-affinity expresses relationships between workloads, and topology spread regulates balance across domains. By choosing appropriate topology keys, selectors, and constraint strictness—while accounting for capacity, storage, autoscaling, and rollouts—Kubernetes can place pods in closer alignment with application performance and fault-tolerance goals.
