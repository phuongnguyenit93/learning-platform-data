# PodDisruptionBudget and Controlled Disruption Strategies

An application on **Google Kubernetes Engine (GKE)** has three healthy Pods. During node maintenance, if multiple Pods are moved simultaneously, users may see errors even though Kubernetes will recreate the Pods. A **PodDisruptionBudget (PDB)** sets limits on *voluntary evictions*, letting maintenance tooling know when to wait so the application keeps enough ready Pods.

Within the **Advanced GKE and Operations** chapter of the **CLOUD_PROVIDERS_GCP** module, this lesson focuses on using PDBs properly with **Deployments, StatefulSets, node drains, and GKE node upgrades**, combined with readiness probes, capacity, rollouts, and monitoring to preserve reliability. The broader context spans projects/IAM, VPCs, and Compute Engine through GKE, Cloud Run, data services, and cost; a PDB is one piece of availability design rather than a substitute for those layers.

After this lesson, you will be able to:

1. Distinguish **voluntary disruptions**, **involuntary disruptions**, the Eviction API, and direct Pod deletion.
2. Choose `minAvailable` or `maxUnavailable`, interpret `disruptionsAllowed`, and avoid configurations that stall drains.
3. Author PDBs aligned with replica counts, quorum requirements, and minimum serving levels.
4. Plan node maintenance on GKE with surge/blue-green upgrades, spare capacity, graceful shutdown, and rollback.
5. Test safely in a lab namespace/node, diagnose rejected evictions, and monitor SLOs.

## 1. What Does a PDB Protect?

A PDB is a Kubernetes resource under the `policy/v1` API. It selects a set of Pods via a **label selector** and declares how many or what percentage of Pods must stay healthy during a *controlled eviction*. A PDB does not create Pods, provision nodes, decide Pod placement, or prevent every kind of outage.

~~~mermaid
flowchart LR
    O["Node maintenance / drain"] --> E["Kubernetes Eviction API"]
    E --> P{"Does PDB allow<br/>more disruption?"}
    P -->|"Yes"| DEL["Evict Pod, wait for shutdown<br/>per grace period"]
    P -->|"No"| WAIT["Temporarily reject;<br/>investigate or retry"]
    DEL --> C["Controller creates replacement Pod<br/>on eligible node"]
    C --> R["Pod Ready, budget updated"]
~~~

### 1.1. Voluntary vs. Involuntary Disruptions

| Scenario | Type | Does a PDB directly limit it? |
| --- | --- | --- |
| `kubectl drain` performs eviction for node maintenance | Voluntary | **Yes**, via the Eviction API, if Pods match a PDB. |
| Node upgrade tooling drains nodes via eviction | Voluntary initially | **Conditionally**; GKE enforces a wait timeout. |
| Hardware node failure or zone outage | Involuntary | **No**, cannot prevent it. |
| Container crash or OOMKilled | Involuntary | **No**, cannot prevent it. |
| Direct `kubectl delete pod` | Direct deletion, bypassing Eviction API | **No**, does not enforce PDB budget like an eviction. |
| Deployment rolling update replacing Pods per strategy | Controller rollout change | **Not directly gated by PDB**; governed by Deployment `maxUnavailable`/`maxSurge`. |
| Admin force-deletes Pod/node | Can bypass normal eviction | **No protection guaranteed**; risks downtime. |

**Key point:** a PDB paces *how* planned disruptions occur; it does not guarantee an application always maintains N healthy Pods. Node crashes, bad rollout updates, single-zone database dependencies, or capacity shortages can still take a service down.

### 1.2. Why the Eviction API Matters

When a tool requests to **evict** a Pod, the Kubernetes API server evaluates the PDB before allowing it. Possible responses include:

- `200 OK`: eviction allowed; the Pod enters termination.
- `429 Too Many Requests`: the PDB currently blocks further eviction or the API is rate-limiting; usually wait, add capacity, or fix unready Pods.
- `500 Internal Server Error`: invalid configuration, such as multiple PDBs matching the same Pod.

`kubectl drain` uses the Eviction API by default when supported by the API server. Never pass flags that **bypass eviction** just to force a drain to "succeed," unless following an approved exception runbook after assessing impact.

## 2. Configuration and Disruption Budget Math

In a PDB, specify **one** of `minAvailable` or `maxUnavailable`:

- `minAvailable`: number or percentage of Pods that **must remain Ready** after eviction.
- `maxUnavailable`: number or percentage of Pods **permitted to be unavailable** relative to the controller's desired replicas.

Percentages are always written as strings, such as `"50%"`. Kubernetes **rounds up** for both `minAvailable` and `maxUnavailable` percentages; consequently, a `maxUnavailable` percentage can allow more disruption than expected at small replica counts.

### 2.1. Quick Calculation Examples

| Desired replicas | PDB | Minimum healthy Pods to stay in budget | `disruptionsAllowed` when all Ready |
| ---: | --- | ---: | ---: |
| 3 | `minAvailable: 2` | 2 | 1 |
| 3 | `maxUnavailable: 1` | 2 | 1 |
| 5 | `minAvailable: 4` | 4 | 1 |
| 5 | `maxUnavailable: "40%"` | 3 (`ceil(40% × 5) = 2` unavailable) | 2 |
| 7 | `minAvailable: "50%"` | 4 (`ceil(3.5)`) | 3 |
| 7 | `maxUnavailable: "30%"` | 4 (`ceil(2.1) = 3` unavailable) | 3 |
| 1 | `maxUnavailable: "30%"` | 0 | 1 — **can lose 100% of service** |
| 1 | `minAvailable: 1` | 1 | 0 — **drain can be blocked** |

The rightmost column assumes all replicas are **Ready**, no eviction is in flight, and the selector matches a controller-managed workload. In practice, the budget fluctuates with healthy Pods, desired replicas, and active evictions.

For three Pods with `minAvailable: 2`: when all three are Ready, one Pod can be evicted. While only two remain healthy, the next eviction waits until a replacement Pod turns Ready or healthy replicas increase.

### 2.2. Manifest for a Three-Replica Deployment

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

An equivalent option **when the Deployment has three replicas** is:

~~~yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: orders-api-pdb
  namespace: orders
spec:
  maxUnavailable: 1
  selector:
    matchLabels:
      app: orders-api
~~~

**Never create both PDBs targeting the same Pods.** The two manifests above are **alternatives**, not additive protection layers. `maxUnavailable` works well when replica counts scale dynamically via HPA, provided Pods belong to a controller supporting the `scale` subresource; verify selectors and controller types before choosing.

### 2.3. Reading PDB Status

~~~bash
kubectl get pdb -n orders
kubectl describe pdb orders-api-pdb -n orders
kubectl get pdb orders-api-pdb -n orders -o yaml
~~~

| `status` field | Meaning |
| --- | --- |
| `currentHealthy` | Number of Pods the PDB sees as healthy (**Ready**). |
| `desiredHealthy` | Minimum healthy Pods required by the budget. |
| `expectedPods` | Total Pods/replicas expected per the controller. |
| `disruptionsAllowed` | New evictions currently permitted. |
| `disruptedPods` | Pods whose eviction was accepted but have not yet finished terminating within the window. |
| `observedGeneration` | Configuration generation observed by the PDB controller. |

When `disruptionsAllowed: 0`, **do not immediately loosen the budget**. Check Ready Pods, desired replicas, startup progress, and whether another eviction is already underway. A PDB adds zero capacity to an app; it only checks live state to decide if another disruption is safe.

**Selector note:** an empty selector `{}` in `policy/v1` matches **every Pod in the namespace**, which can inadvertently stall drains across unrelated workloads. Use specific labels and verify matched Pods before applying.

## 3. When Does a PDB Stall Maintenance?

### 3.1. Unready Pods and `unhealthyPodEvictionPolicy`

Kubernetes counts **Ready** Pods as healthy for `currentHealthy`. If Pods enter `CrashLoopBackOff` or stay Running without becoming Ready, the budget can drop to 0 even before maintenance starts.

`spec.unhealthyPodEvictionPolicy` governs how eviction handles **Running but unhealthy Pods**:

| Policy | Behavior | Trade-off |
| --- | --- | --- |
| `IfHealthyBudget` (default) | Evicts Running/NotReady Pods only if the workload still meets its minimum healthy count. | If the app already lacks healthy Pods, a stuck Pod can stall node drains. |
| `AlwaysAllow` | Permits evicting Running/NotReady Pods even when healthy budget isn't met. | Helps clear nodes with broken Pods, though it may evict a Pod that was about to recover. |

This field is **stable since Kubernetes 1.31**; check your cluster version before using it on older environments. It **never permits exceeding the budget for Ready Pods**.

Example:

~~~yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: orders-api-pdb
spec:
  maxUnavailable: 1
  unhealthyPodEvictionPolicy: AlwaysAllow
  selector:
    matchLabels:
      app: orders-api
~~~

In production, enable `AlwaysAllow` only after verifying Pod recovery, probes, replacement scheduling, and data safety. It cannot fix bad images, registry outages, or broken dependencies leaving every Pod NotReady.

### 3.2. Single Replica and Cluster Upgrades

With **one Ready Pod**, `minAvailable: 1` allows **0 voluntary evictions**. A node hosting that Pod may fail to drain cleanly. That is the PDB working as designed—not a Kubernetes malfunction.

Options to evaluate in order:

1. If the app is **stateless and horizontally runnable**, scale to at least two replicas—ideally spread across nodes/zones—and wait until new replicas are Ready.
2. Confirm **capacity** exists for replacement Pods and startup/readiness probes work.
3. If parallel execution is impossible (e.g., a single writer without leader election), schedule a **maintenance window with accepted downtime**, backups, and a recovery plan.
4. If the PDB must be relaxed, make the minimal approved change and document before/after states.

**Never** set `maxUnavailable: "30%"` on a single replica thinking it caps downtime at 30%: Kubernetes rounds up to **one eviction**, risking a full outage.

### 3.3. Quorum-Based Databases

A five-member cluster needs at least **three members available** for write quorum. Mathematically, `minAvailable: 3` allows up to two evictions when all five are Ready. Yet if an involuntary node failure happens at the same time, quorum is lost.

Therefore, for consensus systems, **`maxUnavailable: 1`** is often safer, paired with anti-affinity/topology spread, health checks, and leader/follower-aware orchestration. A PDB only counts Ready Pods; **it does not prove data is synced, a member can vote, or business quorum holds**.

### 3.4. Other Sources of Stalled Drains

| Symptom | Check before relaxing the PDB |
| --- | --- |
| `disruptionsAllowed=0` despite enough replicas | Are Pods NotReady, terminating, mid-rollout, or is status stale? |
| Repeated `429` on eviction | Desired vs. current healthy, PDB, readiness, and API throttling. |
| Replacement Pod stuck `Pending` | Missing CPU/RAM/IPs, quotas, node affinity, topology spread, taints, or PVC topology. |
| One Pod matches multiple PDBs | Fix overlapping selectors; Eviction API may return errors. |
| Drain hangs for a long time | Container `preStop`/`terminationGracePeriodSeconds`, slow app readiness, or slow storage detach. |
| DaemonSets or controllerless Pods | Check `kubectl drain` flags and GKE upgrade behavior; PDBs do not replace workload controllers. |

As a rule, **increase healthy Pods and spare capacity first**—never make deleting the PDB your knee-jerk reaction.

## 4. PDBs in GKE Node Upgrade Strategies

### 4.1. Surge and Blue-Green Upgrades

On GKE Standard node pools, the upgrade strategy strongly affects how reliably PDBs are honored:

| Strategy | Core mechanism | Role of PDB |
| --- | --- | --- |
| **Surge upgrade** | Adds extra nodes up to `maxSurge`, then cordons/drains old nodes. | Gives new Pods room to turn Ready before more evictions proceed. |
| **Pool upgrade with `maxUnavailable`** | Allows some nodes to go unavailable concurrently during upgrade. | Needs enough spare workload headroom not to breach PDBs or SLOs. |
| **Blue-green upgrade** | Provisions a new node pool, moves workloads, and keeps the old pool for a configured soak period. | Offers extra validation headroom and rollback window per product limits. |

A **node pool upgrade's** `maxUnavailable` counts **nodes**, whereas a **PDB's** `maxUnavailable` counts **Pods**. Same field name, completely different units.

### 4.2. GKE PDB Wait Limit During Node Upgrades

Per current GKE documentation, during standard node upgrades GKE honors **PDBs and Pod termination grace periods** for up to roughly **one hour per node**. If a node still cannot drain after that limit, GKE may **force the upgrade forward** to maintain node lifecycle hygiene. With blue-green, configured soak phases can allow longer transition periods.

**Consequence:** a PDB is **not an eternal lock** preventing node upgrades forever. An overly strict PDB can drag out upgrades and still result in forced disruption once GKE hits its timeout. To prevent this:

- Verify replica counts and spare node capacity before maintenance.
- Ensure replacement Pods can schedule and turn Ready in other zones where appropriate.
- Audit `disruptionsAllowed=0`, NotReady Pods, and storage affinity before maintenance.
- Use GKE maintenance windows/exclusions where supported, and schedule sensitive stateful components.
- Choose a node upgrade strategy matching your RTO, surge quota, and rollback validation needs.

This timeout behavior applies to **GKE-managed node upgrades**; do not assume manual `kubectl drain` commands automatically skip PDBs after one hour.

### 4.3. PDBs Do Not Directly Govern Deployment Rollouts

When you run `kubectl rollout restart deployment/orders-api`, the Deployment controller replaces Pods using `spec.strategy.rollingUpdate.maxUnavailable` and `maxSurge`. A PDB does not gate every Pod deletion triggered by a Deployment rollout.

Align **three independent settings**:

| Setting | What it protects |
| --- | --- |
| **Deployment `maxUnavailable/maxSurge`** | Bounds Pod replacement pace during application rolling updates. |
| **PDB `minAvailable/maxUnavailable`** | Bounds voluntary evictions through the Eviction API. |
| **GKE node pool upgrade `maxSurge/maxUnavailable`** | Governs node creation/removal pace and spare capacity during upgrades. |

Additionally, **Pod readiness, graceful termination, topology spread, and autoscaling** determine whether those bounds run smoothly or trigger Pending Pods and 503s.

### 4.4. Designing Drains with Graceful Shutdown

An HTTP API should coordinate:

1. Accurate `readinessProbe` so unready Pods stop receiving traffic.
2. On `SIGTERM`, stop accepting new connections, drain in-flight requests, and close connections cleanly.
3. Set `terminationGracePeriodSeconds` long enough for active requests without stalling maintenance excessively.
4. If using `preStop`, time it carefully; hook execution counts inside the termination grace budget.
5. Ensure load balancers / EndpointSlices remove unready backends per platform mechanisms; measure actual convergence delay.

A PDB only checks conditions **before allowing eviction**; it cannot fix apps that crash immediately, ignore `SIGTERM`, or run only a single replica.

## 5. Controlled Node Maintenance Runbook

This runbook applies to **GKE Standard** with operator-managed node pools. On Autopilot, GKE manages nodes; never perform manual node drains disallowed by product or organizational policy. Always verify **the right project, cluster, context, and namespace** rather than trusting whatever terminal context is active.

### 5.1. Before Maintenance

1. **Confirm scope:** node name, zone, node pool, app owners, and approved maintenance window.
2. **Check SLOs:** error rates, latency, Ready endpoints, database health, and spare capacity.
3. **Inspect all Pods on the node**, including other namespaces, DaemonSets, standalone Pods, and workloads using local storage or PVCs.
4. **Read PDBs:** `currentHealthy`, `desiredHealthy`, `disruptionsAllowed`, NotReady Pods, and selectors.
5. **Confirm destination capacity:** CPU, memory, Pod IPs, quotas, taints/affinities, topology spread, volume attachment, and image-pull access.
6. **Prepare rollback:** designated owner, abort criteria, live drain monitoring, uncordon steps, and app recovery plan.

**Read-only** checks in the verified context:

~~~bash
kubectl config current-context
kubectl get nodes -L topology.kubernetes.io/zone
kubectl get pdb -A
kubectl get pods -A -o wide

# Pick a node ONLY AFTER confirming ownership
NODE="APPROVED_NODE_NAME"
kubectl get pods -A --field-selector "spec.nodeName=$NODE" -o wide
kubectl describe node "$NODE"
~~~

If another team's Pods sit on the node, **stop and coordinate with the owners**. Never pass `--force`, `--disable-eviction`, or `--delete-emptydir-data` just to clear errors: those flags risk data loss or bypass safety controls.

### 5.2. During Maintenance

If the node is dedicated to a lab or approved in a production runbook:

~~~bash
# Write operation: prevent new Pods from scheduling onto the node
kubectl cordon "$NODE"

# Run ONLY after verifying all Pods and spare capacity elsewhere
# Never use --disable-eviction to bypass a PDB
kubectl drain "$NODE" --ignore-daemonsets --timeout=2m
~~~

`kubectl drain` may pause due to a PDB, controllerless Pod, or `emptyDir` Pod; that is diagnostic information to investigate, **not an invitation to force-delete**. The `2m` timeout keeps a lab from hanging indefinitely, not a recommended production RTO setting.

During the maintenance window, monitor:

~~~bash
kubectl get pdb -A
kubectl get pods -A -o wide
kubectl get nodes
~~~

In a test setup with `minAvailable: 2` and three Ready Pods, the first eviction is allowed. The next eviction waits until enough healthy Pods exist per budget; if no node can schedule the new Pod, the drain remains blocked.

### 5.3. After Maintenance or Abort

If **the node remains healthy** and should return to scheduling workloads:

~~~bash
# Write operation: remove the unschedulable taint
kubectl uncordon "$NODE"

kubectl get nodes
kubectl get pods -A -o wide
kubectl get pdb -A
~~~

Never `uncordon` a broken or non-compliant node just to give Pods somewhere to run. If GKE replaced/deleted the node during an upgrade, the old node name may no longer exist; inspect the node pool and new nodes instead of trying to restore a deleted object.

Close the change only after verifying **applications serve within SLO**, zero unexpected Pending Pods remain, PVCs/leaders recovered if applicable, and pre/post error and latency telemetry looks clean.

## 6. Hands-On Exercise on a Test Cluster

**Goal:** observe PDB status changing with Ready Pods and test a controlled rollout without intentionally inducing outages. The first part creates only a **Deployment, PDB, and namespace** inside an **existing lab cluster**—never a new GKE cluster or node pool. Node draining is **optional and advanced**, permitted only on an isolated authorized node.

### 6.1. Verify Context and Deploy Three Replicas

On a workstation with `kubectl` authorized for the lab cluster:

~~~bash
kubectl config current-context
kubectl get nodes -o wide

# Create only inside a verified test cluster
kubectl create namespace pdb-lab

kubectl apply -n pdb-lab -f - <<'YAML'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web-lab
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 0
      maxSurge: 1
  selector:
    matchLabels:
      app: web-lab
  template:
    metadata:
      labels:
        app: web-lab
    spec:
      terminationGracePeriodSeconds: 30
      containers:
        - name: nginx
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
            periodSeconds: 5
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: web-lab-pdb
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: web-lab
YAML

kubectl rollout status deployment/web-lab -n pdb-lab
kubectl get pods -n pdb-lab -o wide
kubectl get pdb web-lab-pdb -n pdb-lab -o yaml
~~~

When all three Pods are Ready, expect `currentHealthy: 3`, `desiredHealthy: 2`, and `disruptionsAllowed: 1`. If a Pod isn't Ready, inspect events or image-pull status and evaluate only once stable.

### 6.2. Observe Rollout vs. Eviction

In one terminal, watch Pods:

~~~bash
kubectl get pods -n pdb-lab -w
~~~

In another terminal:

~~~bash
# Replaces Pods via rolling update: this is NOT an Eviction API / PDB test
kubectl rollout restart deployment/web-lab -n pdb-lab
kubectl rollout status deployment/web-lab -n pdb-lab
kubectl get pdb web-lab-pdb -n pdb-lab
~~~

A clean rollout reflects **Deployment strategy and Pod readiness**, not proof that the PDB allowed or denied eviction. In production, pin image digests and monitor rollouts rather than relying on mutable tags like `stable-alpine`.

### 6.3. Optional: Test Draining on a Dedicated Lab Node

Run only if **the cluster has at least two nodes**, the chosen node **runs only lab workloads and compatible system DaemonSets**, is not shared with other teams, and spare capacity exists for replacement Pods.

~~~bash
# Replace with a LAB node approved by the administrator
NODE="LAB_NODE_NAME"

# MANDATORY: carefully inspect running Pods before draining
kubectl get pods -A --field-selector "spec.nodeName=$NODE" -o wide
kubectl get pdb -n pdb-lab

# Only after confirming the node is safe to drain
kubectl cordon "$NODE"
kubectl drain "$NODE" --ignore-daemonsets --timeout=2m

# If drain blocks or times out: STOP and inspect Pods/PDBs/events
# Once the test finishes and the node is healthy:
kubectl uncordon "$NODE"
~~~

If a Pod stays unevictable, inspect `kubectl describe pdb web-lab-pdb -n pdb-lab` and `kubectl describe pod`. **Do not rerun drain with `--disable-eviction` or `--force` to hide the error.** Never run this test on a shared or single-node cluster.

### 6.4. Clean Up Resources

~~~bash
# Verify the right context and test namespace
kubectl config current-context
kubectl get all,pdb -n pdb-lab

# Delete only the namespace created for this lab
kubectl delete namespace pdb-lab
~~~

If you cordoned a lab node and haven't uncordoned it yet, handle it per **actual node state** and permissions; deleting a namespace never uncordons a node. This lab never deletes or modifies node pools, clusters, VPCs, or Google Cloud resources outside the exercise scope.

## 7. Monitoring and Incident Response

### 7.1. Signals Before, During, and After Disruption

| Signal | Practical meaning |
| --- | --- |
| PDB `disruptionsAllowed` and `currentHealthy` | Whether safe eviction headroom exists and whether Pods are unready. |
| Deployment/StatefulSet desired, ready, available replicas | Whether the controller maintains required serving Pods. |
| Pod `Pending`, `Terminating`, and events | Node shortages, scheduling issues, PVCs, image pulls, or slow graceful shutdown. |
| Node Ready/cordoned status; autoscaler events | Whether spare capacity exists or nodes are unschedulable. |
| HTTP 5xx, p95/p99 latency, request success rate | Whether the app truly meets SLOs beyond raw Pod counts. |
| Database quorum/replication lag, PVC attach status | Whether stateful services have healthy data and leaders to serve. |
| Upgrade duration, remaining nodes, drain wait time | Whether maintenance risks hitting GKE's wait timeout. |

Alert when **`disruptionsAllowed=0` persists** on workloads needing routine maintenance, correlated with Pod readiness and upgrade events. Do not alert instantly when budget hits 0 during a normal eviction in progress—require a duration threshold and context.

### 7.2. When a Drain Is Rejected, Follow This Order

1. **Halt further actions** and read `kubectl get pdb -A`, `kubectl get pods -A -o wide`, and `kubectl describe pdb`.
2. Identify Pods on the node and which PDBs match them; watch for overlapping PDB selectors.
3. Compare desired/current/Ready replicas, readiness probes, HPA activity, and active rollouts.
4. Check remaining nodes' capacity: CPU, RAM, Pod IPs, quotas, affinities/taints, topology spread, and volumes.
5. If **Running/NotReady** Pods block drain, evaluate `unhealthyPodEvictionPolicy`; never enable `AlwaysAllow` if a Pod still protects critical business state.
6. With only one replica, decide between **scaling out** or scheduling maintenance downtime per app requirements.
7. Apply approved changes, test on one node, verify endpoints and SLOs, and only then proceed to remaining nodes.

On GKE, watch **drain wait times**, because managed upgrades may force-continue past the timeout noted in section 4.2. Never let a PDB stall an entire node pool upgrade silently without alerting on-call engineers.

### 7.3. Cost of Low-Disruption Strategies

A PDB is a Kubernetes configuration object with no separate billing SKU. **Indirect costs** come from standby replicas/nodes, surge nodes during upgrades, per-zone capacity, cross-zone traffic, disks/backups, and monitoring. Sound decisions weigh:

\[
\text{Post-disruption serving capacity}
=\text{Remaining healthy replicas}
\times\text{actual throughput per replica}
\]

This is a simplified capacity heuristic, not a substitute for load testing; when a database saturates or traffic skews unevenly, effective throughput drops lower. To meet SLOs, measure **peak load**, **error budgets**, node/quota ceilings, and Pod readiness time before picking `minAvailable`.

## 8. Scenario Exercises

### Scenario A — API with 5 Replicas

Deployment `payments-api` runs five Ready Pods across three zones. The SLO requires at least four Pods serving during routine maintenance.

**Task:** write the PDB, calculate initial allowed evictions, and recalculate once one Pod becomes NotReady.

**Hint:** `minAvailable: 4` or `maxUnavailable: 1` fits when desired replicas equal five. Initially `disruptionsAllowed=1`; once only four healthy Pods remain, further eviction budget drops to **0**. If the real requirement is serving throughput rather than Pod count alone, verify four Pods can carry peak load within SLO.

### Scenario B — StatefulSet with 3 Replicas

A database cluster requires a **two-member quorum** to accept writes. During maintenance, one member loses connection to the leader and reports `NotReady`.

**Task:** can you safely evict another Ready member? What does `AlwaysAllow` solve, and what does it NOT solve?

**Hint:** with `minAvailable: 2`, two Ready Pods leave a remaining eviction budget of **0**. `AlwaysAllow` permits evicting the **unhealthy** member, but must never be used to bypass quorum or evict a Ready member. Verify data sync, leader election, and database operator runbooks before moving members.

### Scenario C — Prolonged Node Upgrade

GKE Standard is surge-upgrading a node pool. Several Pods sit `Pending` because their PVs are attached in another zone; the matching PDB shows `disruptionsAllowed=0`, and upgrade duration keeps climbing.

**Task:** order the investigation steps and propose the lowest-risk action.

**Hint:** check PVC topology, node locations, capacity, and Pod events first; if no node can attach the volume, raising `maxUnavailable` on the PDB still won't schedule new Pods. Fix the storage/failover topology, mind the GKE wait timeout, protect data, and reschedule the change once the root cause is resolved.

### Self-Check

1. **Does a PDB protect against a zone outage?** No; you need replicas in surviving zones and resilient data replication.
2. **Does `kubectl delete pod` always respect a PDB?** No; direct deletion does not go through Eviction API PDB checks.
3. **Why is `maxUnavailable: "30%"` dangerous for a single replica?** Percentages round up, allowing eviction of the sole Pod.
4. **Is `disruptionsAllowed=0` always a misconfiguration?** No; the budget may simply be in active use or Pods may be NotReady.
5. **Does a PDB directly control Deployment rollouts?** No; check the Deployment's rolling update strategy.
6. **Can you rely on GKE waiting indefinitely on a PDB during node upgrades?** No; GKE caps wait times and may force the upgrade onward.
7. **How do you minimize real user disruption?** Combine PDBs, enough replicas/nodes, accurate readiness, graceful shutdown, topology spread, and upgrade strategies—then verify against SLOs.

## 9. Official References

- [Kubernetes — Configure a PodDisruptionBudget](https://kubernetes.io/docs/tasks/run-application/configure-pdb/): selectors, `minAvailable`/`maxUnavailable`, rounding, and unhealthy Pod eviction.
- [Kubernetes — API-initiated Eviction](https://kubernetes.io/docs/concepts/scheduling-eviction/api-eviction/): Eviction API, response codes, and differences from direct deletion.
- [Kubernetes — Safely Drain a Node](https://kubernetes.io/docs/tasks/administer-cluster/safely-drain-node/): cordon/drain usage and operational limits.
- [GKE — Node pool upgrade strategies](https://cloud.google.com/kubernetes-engine/docs/concepts/node-pool-upgrade-strategies): surge, blue-green, and PDB wait limits.
- [GKE — Manually upgrade a cluster](https://cloud.google.com/kubernetes-engine/docs/how-to/upgrading-a-cluster): upgrade ordering and Pod impact.
- [GKE — Troubleshoot cluster upgrades](https://cloud.google.com/kubernetes-engine/docs/troubleshooting/upgrades): stuck PDBs, termination grace, PVCs, and capacity.
- [Kubernetes — Deployment](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/): `maxSurge`, `maxUnavailable`, and rolling updates.
- [Kubernetes — Pod lifecycle](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/): readiness, termination, and Pod conditions.

**Conclusion:** a well-designed PDB permits **enough maintenance** to keep the cluster patched and upgraded while preventing too many healthy Pods from being evicted simultaneously. Its value is proven only when paired with spare capacity, safe data flows, SLO monitoring, and clear runbooks—never when every drain grinds to a halt.
