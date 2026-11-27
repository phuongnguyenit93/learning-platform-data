# PodDisruptionBudget, Draining, and Safe Node Upgrades

## Lesson Objectives

Kubernetes frequently needs to relocate or terminate Pods during node maintenance, OS upgrades, kubelet version updates, Spot instance reclamation, or resource rebalancing. A deleted Pod can be recreated by its controller, but the replacement Pod takes time to schedule, pull images, start up, and pass its readiness probe. If too many Pods of the same application are disrupted at once, the service can lose availability even while healthy nodes remain in the cluster.

A PodDisruptionBudget (PDB) limits how many healthy Pods can be disrupted by voluntary actions via the Kubernetes Eviction API. Combining PDBs with proper draining, graceful shutdown, topology spread, and spare capacity enables controlled node maintenance.

After this lesson, you will be able to:

- Distinguish voluntary disruptions from involuntary disruptions.
- Explain PDBs, `minAvailable`, `maxUnavailable`, and `disruptionsAllowed` status.
- Create appropriate PDBs for a Deployment or StatefulSet.
- Understand how `kubectl cordon` and `kubectl drain` operate.
- Identify when a drain is blocked by a PDB and handle it safely.
- Design readiness probes, graceful termination, and topology to preserve availability.
- Build a step-by-step node pool upgrade procedure.
- Monitor and test maintenance without exceeding your disruption budget.

## 1. Why Control Pod Disruptions?

Pods are ephemeral. Kubernetes can spawn replacement Pods to maintain the desired replica count, but replacement is not instantaneous. Between when an old Pod exits and a new Pod turns Ready, serving capacity drops.

Common reasons Pods get disrupted:

- An operator drains a node for maintenance or upgrades.
- A managed node group replaces nodes via a rolling update strategy.
- Cluster Autoscaler removes a node after consolidating workloads onto other nodes.
- A node pool switches instance types or OS images.
- A node needs a reboot for a kernel security patch.
- A workload is evicted from a node to rebalance resources.
- Pods are intentionally deleted by automation or operational tooling.

If an application has three replicas and all three sit on one node, draining that node wipes out all serving capacity simultaneously. The Deployment creates three new Pods, but they still need nodes with enough CPU/RAM, image pulls, volume attachments, and startup time.

A PDB is one piece of an availability plan. It must be paired with an appropriate replica count, readiness probes, distribution across failure domains, spare capacity, and applications capable of graceful shutdown.

## 2. Voluntary vs. Involuntary Disruptions

Kubernetes distinguishes two categories of disruptions.

**Voluntary disruptions** are disruptions caused by intentional actions from an operator or controller, for example:

- `kubectl drain` using the Eviction API.
- Node maintenance operations or node management tools using eviction.
- Automation intentionally evicting Pods through the API.

**Involuntary disruptions** are unintended disruptions outside the controller's or operator's intent, for example:

- Node power loss or host hardware failure.
- Kernel panic or node network loss.
- Pod OOM kill.
- Node memory/disk pressure causing kubelet to evict Pods.
- Hardware or infrastructure failures halting processes.

PDBs primarily govern voluntary disruptions via the Eviction API. A PDB cannot prevent a node from failing, keep a Pod alive when the kernel halts, or prevent OOM kills. Involuntary disruptions can push healthy Pod counts below the configured budget; when that happens, the PDB normally blocks further voluntary evictions until the workload recovers.

| Disruption Type | Example | Directly Controlled by PDB? |
|---|---|---|
| Voluntary via Eviction API | `kubectl drain` | Yes |
| Voluntary via Eviction API tooling | Node maintenance controller | Yes, if the tool respects the API |
| Direct Pod deletion | `kubectl delete pod` | Not necessarily; direct deletion bypasses the Eviction API |
| Node/host failure | Machine or power loss | No |
| OOM or node pressure | Kernel/kubelet terminates Pod | Does not protect against this cause |
| Deployment rolling update | Controller replaces Pods per workload strategy | PDB does not govern this rollout mechanism |

Never treat a PDB as a firewall preventing every Pod deletion. It is a budget for a specific class of action within the eviction workflow.

## 3. How PodDisruptionBudget Works

PodDisruptionBudget is a resource in the `policy/v1` API group, created in the workload's namespace. A PDB selects a group of Pods via a label selector and specifies the count or percentage of Pods that must remain healthy during voluntary disruptions.

PDB supports two main declarations:

- **`minAvailable`:** minimum number or percentage of Pods that must stay healthy.
- **`maxUnavailable`:** maximum number or percentage of Pods permitted to be unavailable.

Declare only one of the two fields. Do not set both `minAvailable` and `maxUnavailable` in the same PDB.

When a client requests an eviction, Kubernetes checks the matching PDB. If evicting the Pod would drop healthy Pods below budget, the API can reject the request with a `Too Many Requests` error. Drain tooling waits or retries according to its behavior; operators must restore the budget or wait for other Pods to become healthy before continuing.

~~~mermaid
flowchart TD
    A["Pod Eviction Request"] --> B["Find PDB matching selector"]
    B --> C["Read healthy and desired healthy counts"]
    C --> D{"disruptionsAllowed > 0?"}
    D -->|Yes| E["Allow eviction"]
    D -->|No| F["Reject / wait"]
    E --> G["Controlled Pod termination"]
    F --> H["Restore replicas or capacity"]
    H --> C
~~~

### 3.1. PDB Calculates Budget from Workload State

The PDB tracks expected Pods and healthy Pods. Common status fields include:

| Status Field | Meaning |
|---|---|
| `currentHealthy` | Number of Pods currently considered healthy |
| `desiredHealthy` | Minimum healthy Pods that must be maintained |
| `disruptionsAllowed` | Number of voluntary disruptions still permitted |
| `expectedPods` | Total Pods expected based on workload scale |
| `disruptedPods` | Pods recorded as currently undergoing disruption |

`disruptionsAllowed` is a key operational metric. If it is `0`, drain operations will block when trying to evict Pods covered by that PDB.

A PDB's selector must accurately match the Pods to protect. If the selector matches nothing, the PDB protects nothing. If the selector is too broad, it can lump Pods from components with independent lifecycles into one shared budget and make maintenance difficult.

### 3.2. `minAvailable` Example

A Deployment has three replicas and needs at least two Pods healthy during node maintenance:

~~~yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: orders-api-pdb
  namespace: production
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: orders-api
~~~

This PDB allows at most one Pod in the group to undergo voluntary disruption at a time, provided all three Pods are healthy and other conditions hold.

If only two Pods remain healthy, `disruptionsAllowed` drops to `0`. A drain must wait until the workload recovers or the budget is adjusted under an evaluated maintenance plan.

### 3.3. `maxUnavailable` Example

An equivalent way to express allowing at most one unavailable Pod for a four-replica workload:

~~~yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: catalog-pdb
  namespace: production
spec:
  maxUnavailable: 1
  selector:
    matchLabels:
      app: catalog
~~~

`maxUnavailable` fits well when you want to cap unavailable Pods rather than fix a minimum count. For workloads whose replica count scales dynamically, integer counts vs. percentages behave differently as scale changes.

### 3.4. Using Percentages

PDBs accept percentages for `minAvailable` or `maxUnavailable`. When converting percentages to Pod counts, Kubernetes rounds up.

For example, with five replicas:

- `minAvailable: 80%` requires at least four healthy Pods.
- `maxUnavailable: 20%` allows at most one unavailable Pod.
- `maxUnavailable: 30%` rounds up to two Pods.

Verify actual resulting Pod counts at minimum, normal, and peak replica levels. A percentage-based PDB yields different disruption allowances as replicas scale.

## 4. Choosing PDBs Based on Replicas and SLOs

There is no single right PDB value for every application. Base your choice on availability targets, fault tolerance, replacement Pod startup time, and cluster capacity.

| Replica Count | Illustrative PDB | Impact |
|---:|---|---|
| 1 | `minAvailable: 1` | Blocks voluntary eviction; requires planned downtime or scaling up replicas first |
| 2 | `minAvailable: 1` | Permits one Pod disruption while both are healthy |
| 3 | `minAvailable: 2` | Permits at most one Pod disruption |
| 4 | `maxUnavailable: 1` | Permits one unavailable Pod |
| 5 | `minAvailable: 80%` | Requires at least four healthy Pods |

For a single-replica application, `minAvailable: 1` prevents drains from completing. That is not a Kubernetes bug; the PDB is enforcing the policy against voluntary disruption. To perform zero-downtime maintenance, increase replicas, implement failover, or schedule an approved maintenance window.

A PDB does not create replicas on its own. It only limits evictions. If a workload is missing replicas, restore healthy replicas before proceeding with maintenance.

### 4.1. Accounting for Recovery Time

Suppose a Pod takes 90 seconds to schedule, pull its image, start, and pass readiness. Draining multiple nodes back-to-back without waiting for replacement Pods to turn healthy can quickly drop the budget to 0 or reduce serving capacity below requirements.

Maintenance workflows should wait for:

- Replacement Pods to be scheduled.
- Containers to start.
- Readiness probes to succeed.
- Endpoints to update.
- Application latency and error rates to stabilize.
- PDB `disruptionsAllowed` to recover before starting the next batch.

For applications with long warm-up phases, readiness checks must reflect true serving capability. Never water down health checks just to make drains faster.

## 5. PDBs and Deployment/StatefulSet Rollouts Are Separate Mechanisms

A common misconception is thinking a PDB controls how many Pods are replaced during a Deployment rolling update. In reality, Deployment rollouts are governed by the Deployment's `strategy`, such as `maxUnavailable` and `maxSurge`.

A PDB governs voluntary evictions via the Eviction API. It does not replace a Deployment's rolling update strategy.

Deployment example:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
  namespace: production
spec:
  replicas: 3
  selector:
    matchLabels:
      app: orders-api
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 0
      maxSurge: 1
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      terminationGracePeriodSeconds: 60
      containers:
        - name: app
          image: registry.example.com/orders-api:2.4.1
          ports:
            - containerPort: 8080
          readinessProbe:
            httpGet:
              path: /health/ready
              port: 8080
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 3
~~~

In this example, the Deployment creates a new Pod before terminating an old Pod and prevents rollouts from dropping available replicas below the configured strategy. This requires spare capacity for surge Pods; if the cluster lacks resources, rollouts slow down or new Pods stay Pending.

A PDB remains valuable during node drains, but it is not a substitute for `maxUnavailable`/`maxSurge`. Configure both so application rollouts and infrastructure maintenance stay within SLOs.

### 5.1. StatefulSets and Quorum

For StatefulSets, a PDB restricts voluntary evictions, but does not guarantee quorum or data consistency. Verify:

- Database/cluster replica count and quorum rules.
- Which Pod is currently leader or primary.
- Failover order and leader election duration.
- Which AZ each PersistentVolume is attached to.
- Where replacement Pods can be scheduled.
- Whether the application supports graceful shutdown and cluster rejoin.

Never drain multiple nodes hosting quorum members simultaneously. A PDB should reflect the workload's disruption tolerance, yet upgrade procedures must still respect topology and distributed protocols.

## 6. Designing Accurate Selectors

A PDB uses a label selector to identify protected Pods. The selector must match the labels the controller applies to the target workload.

Example:

~~~yaml
selector:
  matchLabels:
    app: orders-api
    component: backend
~~~

Before applying a PDB, inspect the actual Pod list:

~~~bash
kubectl get pods -n production -l app=orders-api,component=backend --show-labels
~~~

Common mistakes:

- Selector matches zero Pods.
- Selector matches workers, APIs, and migration jobs together in the same namespace.
- Multiple PDBs have overlapping selectors covering the same Pods.
- Labels change during a release without updating the PDB.
- The PDB is deployed into a different namespace from the Pods.

Design each budget for a group of Pods sharing the same availability requirements and maintenance behavior. Avoid overly broad selectors such as `app=platform` if that encompasses multiple independent components.

## 7. How `cordon` and `drain` Differ

These two commands are typically paired during node maintenance, but they do different things.

**Cordon** marks a node as unschedulable. The scheduler will not place normal new Pods onto that node, while existing Pods continue running.

**Drain** requests removing workloads from the node. Drain tooling typically cordons the node first, then evicts eligible Pods via the Eviction API, waits for Pods to terminate, and checks relevant constraints.

| Command | Effect | Running Pods |
|---|---|---|
| `kubectl cordon` | Prevents new Pods from scheduling onto the node | Continue running |
| `kubectl drain` | Cordons and evicts movable workloads | Terminated cleanly per eviction/grace period |
| `kubectl uncordon` | Re-enables scheduling onto the node | Does not automatically restart previously evicted Pods |

Cordon is not drain. If you only cordon, existing Pods keep running and the node is not ready for safe upgrades. If you drain, controller-managed Pods are normally recreated on other nodes when resources are available.

## 8. `kubectl drain` and the Eviction API

`kubectl drain` is the standard tool for preparing a node for maintenance. It inspects Pods on the node and handles them according to Kubernetes rules.

Basic workflow:

~~~bash
# Inspect current nodes and workloads
kubectl get nodes -o wide
kubectl get pods -A -o wide --field-selector spec.nodeName=node-a

# Mark node unschedulable for new Pods
kubectl cordon node-a

# Drain node, keeping DaemonSets and confirming emptyDir data deletion
kubectl drain node-a \
  --ignore-daemonsets \
  --delete-emptydir-data \
  --timeout=20m
~~~

The commands above are examples; verify node names, workloads, and data before running in a live environment.

Key details:

- `drain` uses the Eviction API to evict Pods and respects PDBs unless eviction is disabled.
- DaemonSet-managed Pods normally stay on the node; use `--ignore-daemonsets` so drain can proceed.
- Mirror/static Pods cannot be removed via normal drain eviction.
- Standalone Pods without a controller may require `--force` and risk permanent workload loss.
- Pods using `emptyDir` lose local data on deletion; `--delete-emptydir-data` explicitly acknowledges that risk.
- Pods attached to local storage or node-bound volumes may prevent drain from completing as expected.
- Drain waits if a PDB disallows eviction.

Never use `--disable-eviction` as a routine workaround when a drain is blocked. That flag bypasses the Eviction API and overrides PDB protections. Consider it only after risk assessment, service continuity planning, and explicit operational approval.

### 8.1. Drain Blocked by a PDB

Common messages indicate zero disruptions allowed or eviction rejected due to budget. Before taking further action, check:

~~~bash
kubectl get pdb -A
kubectl describe pdb orders-api-pdb -n production
kubectl get pods -n production -l app=orders-api -o wide
kubectl get deploy orders-api -n production
kubectl get nodes
~~~

Read `currentHealthy`, `desiredHealthy`, and `disruptionsAllowed`. Then determine:

- Are any Pods NotReady or crashing?
- Has the Deployment reached its full replica count?
- Are replacement Pods Pending due to insufficient CPU/RAM or affinity rules?
- Do other nodes have enough remaining resources?
- Is a prior eviction still in progress?
- Does the PDB selector match unintended workloads?
- Are multiple nodes being drained concurrently?

Restore healthy replicas or add capacity before continuing. If a budget was misconfigured relative to availability needs, update it through change review and testing—never hot-edit a PDB just to force a drain through.

## 9. Pods Requiring Special Handling During Drain

Not all Pods can be relocated identically.

| Pod Type | What to Check |
|---|---|
| Deployment/ReplicaSet | Controller creates replacement Pods; requires capacity and readiness |
| StatefulSet | Ordinals, quorum, volume topology, and startup order |
| DaemonSet | Normally stays on the node; node replacement spawns DaemonSet Pods on new nodes |
| Static/mirror Pod | Managed by kubelet from node manifests; drain cannot delete them normally |
| Unmanaged Pod (no controller) | Will not be recreated automatically; inspect before forcing |
| Job/CronJob | Verify idempotency/retryability and data state |
| Pod using `emptyDir` | Local data is lost when the Pod is deleted |
| Pod using local PersistentVolume | Bound to a specific node; cannot simply move to another node |
| Pod with extended resources/GPU | Replacement nodes must carry compatible accelerators |

Before draining, check for Pods without owner references, local volumes, `hostPath`, GPUs, and node-local state. Never assume every Pod will be safely recreated by a controller.

## 10. Graceful Termination and Pod Shutdown Timing

When a Pod is evicted, Kubernetes sets a deletion timestamp and begins termination. Containers may run a `preStop` hook, then receive a termination signal such as `SIGTERM`. Once `terminationGracePeriodSeconds` expires, the runtime forcibly kills remaining processes.

The grace period is a finite budget for the entire shutdown sequence. If `preStop` runs long, less time remains for the application to handle `SIGTERM`.

Applications should:

1. Flip readiness to false or stop accepting new traffic.
2. Stop pulling new messages or jobs.
3. Wait for in-flight requests to finish within limits.
4. Commit active transactions or checkpoints.
5. Close connection pools and consumers.
6. Flush required logs and metrics.
7. Exit before the grace period ends.

Readiness, EndpointSlices, and load balancers need propagation time to update. Applications must drain requests cleanly and handle keep-alive/long-lived connections properly.

### 10.1. Termination Configuration Example

~~~yaml
spec:
  terminationGracePeriodSeconds: 90
  containers:
    - name: app
      image: registry.example.com/orders-api:2.4.1
      lifecycle:
        preStop:
          exec:
            command: ["/app/bin/begin-drain"]
~~~

The `begin-drain` command must exist inside the image, be idempotent, and exit promptly. The application must still handle `SIGTERM`; `preStop` does not replace a signal handler.

Do not set an excessively long grace period without factoring in node drain durations and upgrade windows. Conversely, too short a grace period cuts off requests or forces message reprocessing.

## 11. Ensuring Replacement Pods Have Somewhere to Run

A PDB may allow evicting a Pod, yet does not guarantee the scheduler will find an eligible node for the replacement Pod. If the cluster lacks headroom, replacement Pods can remain Pending for extended periods.

Before maintenance, verify:

- Total CPU and memory requests of Pods on the node about to be drained.
- Available capacity on remaining nodes.
- Node selectors, node affinity, and taints/tolerations.
- Topology spread and pod anti-affinity.
- GPUs, local storage, and extended resources.
- Namespace quotas and cloud provider limits.
- Node pool scale-up ability and provisioning latency.
- PodDisruptionBudgets and replica counts.

Maintain spare capacity sufficient to absorb workloads from a draining node. For large node pools, upgrade in small batches so workloads reschedule and stabilize before proceeding.

### 11.1. Topology Spread

If every replica sits in the same zone or on the same node, a PDB may still allow one disruption while leaving the application vulnerable if that failure domain goes down.

Topology spread constraints distribute Pods across zones or nodes:

~~~yaml
spec:
  topologySpreadConstraints:
    - maxSkew: 1
      topologyKey: topology.kubernetes.io/zone
      whenUnsatisfiable: DoNotSchedule
      labelSelector:
        matchLabels:
          app: orders-api
~~~

`DoNotSchedule` forces the scheduler to respect the spread threshold, though Pods can go Pending if zones or capacity are lacking. `ScheduleAnyway` prefers spreading while allowing skewed placement if capacity is tight. Choose based on SLOs and per-zone node availability.

### 11.2. Pod Anti-Affinity

Pod anti-affinity avoids placing multiple replicas of the same application on the same node or in the same zone. This improves fault tolerance, though overly strict hard rules can block scheduling when nodes are scarce.

Balance hard constraints with soft preferences. For critical workloads, test losing a node or zone to verify surviving replicas still serve load.

## 12. Safe Node Upgrade Procedure

Node upgrades typically involve changing the OS image, kernel, kubelet, container runtime, or node configuration. A safe procedure breaks work into small steps with verification checkpoints.

~~~mermaid
flowchart TD
    A["Plan and check PDBs"] --> B["Verify replacement capacity"]
    B --> C["Select one node / small batch"]
    C --> D["Cordon node"]
    D --> E["Drain via Eviction API"]
    E --> F{"Pods exited node safely?"}
    F -->|No| G["Investigate PDB, readiness, storage, capacity"]
    G --> E
    F -->|Yes| H["Upgrade or replace node"]
    H --> I["Node Ready and verify runtime"]
    I --> J["Uncordon if reusing node"]
    J --> K["Verify workloads and SLOs"]
    K --> L{"Continue next batch?"}
    L -->|Yes| C
    L -->|No| M["Complete maintenance"]
~~~

### 12.1. Before Upgrading

- Identify the target node pool, target version, and rollback plan.
- Check version compatibility across Kubernetes, kubelet, and the container runtime.
- Check PDBs across all relevant namespaces.
- Check Deployment/StatefulSet replicas and readiness.
- Identify Pods with local data, local PVs, `hostPath`, or GPUs.
- Verify remaining capacity on surviving nodes.
- Verify quotas, subnet IPs, instance availability, and image pulls.
- Verify backups, replication, and quorum for stateful services.
- Choose a maintenance window and notify relevant operational teams.
- Set up dashboards and abort thresholds.

### 12.2. Upgrading a Single Node

For manually managed nodes or manual node replacement workflows:

~~~bash
# Verify node and workloads
kubectl get node node-a
kubectl get pods -A -o wide --field-selector spec.nodeName=node-a

# Cordon
kubectl cordon node-a

# Drain, respecting PDBs
kubectl drain node-a \
  --ignore-daemonsets \
  --delete-emptydir-data \
  --timeout=20m
~~~

Once drain completes, upgrade or replace the node per platform procedures. If reusing the node, verify kubelet, runtime, CNI, CSI, node conditions, and version before uncordoning.

~~~bash
# Once node is verified Ready and eligible for workloads
kubectl get node node-a
kubectl uncordon node-a
~~~

With managed node groups, the provider may provision new nodes, cordon/drain old nodes, and replace them via a rolling strategy. Verify how the managed upgrade engine respects PDBs, bounds unavailable nodes, and handles Pod disruptions.

### 12.3. Upgrading in Batches

Never drain an entire node pool at once unless the architecture and maintenance plan explicitly support it.

A typical batch workflow:

1. Test on a single canary node.
2. Confirm Pods reschedule cleanly and SLOs remain stable.
3. Upgrade a small batch.
4. Wait for PDB `disruptionsAllowed` and healthy replicas to recover.
5. Verify capacity and node health.
6. Proceed to the next batch.
7. Pause the rollout if readiness failures, Pending Pods, PDB blocks, or latency spikes appear.

Size batches to align with PDBs, replica counts, spare capacity, and workload startup times.

## 13. Managed Node Pools, Surge, and `maxUnavailable`

Managed Kubernetes services usually provide built-in node pool upgrade strategies with terms such as surge, `maxUnavailable`, `maxSurge`, or rolling replacement.

- **Surge:** provisions new nodes before removing old nodes, preserving capacity during upgrades.
- **`maxUnavailable`:** caps how many nodes can be unavailable simultaneously.
- **`maxSurge`:** caps how many extra nodes can exist above desired size during replacement.
- **Batch size:** number of nodes processed per wave.
- **Upgrade strategy:** how the provider replaces nodes, drains workloads, and validates new nodes.

Distinguish node pool `maxUnavailable` from Deployment or PDB `maxUnavailable`. They govern different layers:

| Setting | Target Governed |
|---|---|
| PDB `minAvailable`/`maxUnavailable` | Voluntary Pod evictions |
| Deployment `maxUnavailable`/`maxSurge` | ReplicaSet/Pod rolling updates |
| Node pool `maxUnavailable`/`maxSurge` | Nodes replaced or added during node pool upgrades |
| Topology spread | Pod distribution across failure domains |

A node pool `maxUnavailable` larger than a workload's disruption tolerance can stall multiple PDBs at once. Conversely, too small a `maxUnavailable` drags out maintenance. Coordinate all three layers together.

### 13.1. Do Not Assume Every Provider Drains Identically

Some managed services use the Eviction API and respect PDBs; others enforce specific timeouts, retries, or fallback behaviors when a PDB blocks eviction. Read provider documentation and test on a staging node pool.

If the provider lets you configure timeouts or PDB-block handling, align them with SLOs and incident playbooks. Never assume a provider will silently bypass PDBs if maintenance stalls.

## 14. PDBs and Cluster Autoscaler / Node Autoscalers

A node autoscaler may try to remove a node once workloads consolidate elsewhere. If removing that node requires evicting Pods, a PDB can block or delay scale-down.

This protects availability, though it can prevent nodes from scaling in. Watch for:

- Nodes marked unneeded yet never terminated.
- PDB `disruptionsAllowed` sitting at `0`.
- Pods pinned by local storage or affinity.
- Pods with special priority or daemon behavior.
- Node drain timeouts.
- Surplus node cost due to blocked scale-down.

If a PDB persistently blocks scale-down, revisit replica counts, selectors, workload topology, and availability requirements. Never weaken a PDB solely to save compute cost without evaluating service risk.

## 15. Observability and Diagnostics During Maintenance

Useful commands:

~~~bash
# List PDBs across the cluster
kubectl get pdb -A

# Inspect a specific PDB
kubectl describe pdb orders-api-pdb -n production

# Inspect Pods by node
kubectl get pods -A -o wide

# Inspect node conditions and taints
kubectl describe node node-a

# Watch Deployment rollout
kubectl rollout status deployment/orders-api -n production

# Inspect namespace events
kubectl get events -n production --sort-by=.lastTimestamp

# Inspect Pending/NotReady Pods
kubectl get pods -n production
~~~

Dashboards should monitor:

- PDB `currentHealthy`, `desiredHealthy`, and `disruptionsAllowed`.
- Desired, ready, and available replicas.
- Pending, NotReady Pods, and restart counts.
- Node Ready/NotReady, cordoned, and unschedulable states.
- CPU/memory requests, allocatable capacity, and headroom.
- Volume attach/detach operations and mount errors.
- Image pull duration and application startup time.
- Request rate, p95/p99 latency, and error rate.
- Queue backlog, active connections, and job retries.
- Nodes currently upgrading and unavailable node count.

During maintenance, watch both infrastructure metrics and application SLOs. Nodes may report Ready while workloads are still warming up; Pods may be Running yet failing readiness; PDBs may stay satisfied while latency spikes because remaining capacity is overloaded.

## 16. Common Mistakes

**Setting `minAvailable` to 100% on low-replica workloads:** drains can block indefinitely. Align PDBs with replica counts and downtime/failover plans.

**Treating a PDB as protection against all failures:** PDBs do not prevent node failures, OOMs, or direct deletions. Use replicas, topology spread, and recovery plans.

**Draining multiple nodes simultaneously:** too many Pods of a workload can be evicted before replacements turn healthy. Limit batch size and wait for budgets to recover.

**Using `--disable-eviction` to bypass PDBs:** can take down multiple Pods at once. Only use under an approved, risk-assessed exception procedure.

**Wrong selector:** the PDB protects zero Pods or groups unrelated workloads together. Verify label selectors before maintenance.

**Lacking capacity to reschedule:** evicted Pods sit Pending. Check requests, affinity, quotas, node pools, and storage.

**Confusing PDBs with Deployment rollout strategies:** PDBs do not replace Deployment `maxUnavailable`/`maxSurge`. Configure both.

**Liveness probes coupled to databases:** dependency hiccups trigger mass container restarts. Separate liveness from readiness.

**Grace periods too short:** in-flight requests or transactions get terminated with `SIGKILL`. Design graceful shutdown and appropriate drain durations.

**Overlooking `emptyDir` and local volumes:** temporary data is lost or Pods cannot move between nodes. Check storage before draining.

**Assuming PDBs stop providers from reclaiming nodes:** PDBs cannot hold a host that a cloud provider stops. Rely on multiple replicas, multi-zone placement, and spare capacity.

**Ignoring `disruptionsAllowed`:** maintenance starts when budget is already `0` and immediately stalls. Check PDB status before each batch.

## 17. PDB and Node Drain Testing Procedure

Before applying in production, build a staging environment with realistic replica counts, topology, and resource requests.

### 17.1. Testing PDBs

1. Deploy the workload with expected replicas.
2. Apply readiness probes and the PDB.
3. Verify the selector matches the intended Pods.
4. Check `currentHealthy`, `desiredHealthy`, and `disruptionsAllowed`.
5. Attempt to evict one Pod in staging.
6. Confirm eviction is rejected once budget reaches zero.
7. Scale replicas or restore healthy Pods.
8. Confirm budget recovers and eviction is permitted again.

### 17.2. Testing Drains

1. Pick a node hosting representative workloads.
2. Inspect Pods, owners, volumes, and local data.
3. Cordon the node.
4. Drain with an appropriate timeout without disabling eviction.
5. Watch Pod replacement, PDB status, and readiness.
6. Verify traffic continues serving cleanly.
7. Inspect graceful shutdown behavior and old Pod logs.
8. Uncordon if the node is being reused.
9. Confirm the workload returns to steady state.

### 17.3. Failure Testing

Safely simulate:

- A Pod already NotReady before draining starts.
- A node suddenly losing connectivity.
- A Pod with a zone-bound volume.
- Insufficient CPU/RAM in the cluster to schedule new Pods.
- A mismatched PDB selector.
- Two nodes requested to drain back-to-back.
- A Pod shutdown exceeding `terminationGracePeriodSeconds`.

Evaluate not only whether the drain command completes, but also request errors, latency, queue backlog, data integrity, and recovery time.

## 18. Safe Node Upgrade Checklist

- [ ] PDB is created in the right namespace and its selector matches the target workload.
- [ ] `minAvailable` or `maxUnavailable` aligns with SLOs and replica counts.
- [ ] `disruptionsAllowed` is checked before every batch.
- [ ] Deployment rolling update strategy is configured independently of the PDB.
- [ ] Stateful workloads have verified quorum, leadership, and volume topology.
- [ ] Unmanaged Pods, `emptyDir`, `hostPath`, and local PVs have been audited.
- [ ] Readiness probes reflect true serving readiness.
- [ ] Applications handle `SIGTERM` and execute graceful shutdown.
- [ ] `terminationGracePeriodSeconds` gives enough time to drain requests/jobs.
- [ ] Remaining cluster capacity can schedule all Pods from draining nodes.
- [ ] Affinity, taints, topology spread, and GPU/storage constraints have been verified.
- [ ] Node pool upgrades use appropriate `maxUnavailable`/`maxSurge`.
- [ ] Managed provider drain semantics and timeouts have been verified.
- [ ] Maintenance executes via canary nodes and small batches.
- [ ] `--disable-eviction` is not used to bypass PDBs in routine operations.
- [ ] Dashboards monitor PDBs, Pod readiness, node health, capacity, and SLOs.
- [ ] Clear stop/rollback criteria exist for Pending Pods, exhausted budgets, or SLO breaches.
- [ ] Drain and node replacement workflows have been tested in staging.

PDBs cap voluntary disruptions through the Eviction API; `cordon` blocks new Pods from scheduling onto a node; `drain` relocates workloads off a node; and node pool upgrades roll infrastructure in waves. Safe maintenance requires combining all of these mechanisms with readiness probes, graceful shutdown, topology spread, and spare capacity. Checking `disruptionsAllowed` before each drain, waiting for replacement Pods to turn healthy, and validating SLOs after every batch keeps node upgrades controlled while preserving service stability.
