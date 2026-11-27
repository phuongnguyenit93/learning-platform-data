# Spot Nodes and Capacity Maintenance Strategies for Critical Workloads

## Lesson Objectives

After this lesson, you will be able to:

- Explain how Spot nodes lower costs and why their capacity is not continuously guaranteed.
- Classify workloads by criticality to decide where each should run.
- Design node pools combining On-Demand and Spot capacity to sustain serving capacity.
- Configure Kubernetes scheduling using labels, taints, tolerations, node affinity, PodDisruptionBudgets, and topology spread.
- Prepare applications for node interruptions, verify recovery, and monitor capacity in operations.

## 1. What Is a Spot Node?

Cloud providers can offer Spot virtual machines from spare data center capacity. Their price is typically lower than On-Demand instances, but the provider retains the right to reclaim them when capacity is needed elsewhere or market conditions shift. Naming varies by platform—such as EC2 Spot Instances on AWS, Spot VMs on Google Cloud, and Spot Virtual Machines on Azure.

In Kubernetes, a Spot node is a worker node backed by a Spot VM. Pods schedule onto it like any other node, except the node's lifecycle can end abruptly. An interruption notice may arrive before reclamation, though lead times and notice delivery depend on the provider, instance type, and reclamation event. Applications must always assume a node can disappear and never treat notices as a guarantee.

Spot fits workloads that can restart, distribute work, or resume from checkpoints, such as:

- Image, video, or data batch processing.
- Queue workers with retry mechanisms.
- Retryable CI/CD, testing, or data-analysis tasks.
- Supplemental replicas for stateless services when a baseline set of replicas stays on stable capacity.

Spot is unsuitable as the sole home for uninterruptible components, single stateful Pods holding critical state, or services requiring guaranteed capacity over a fixed window.

### 1.1. Comparing Spot and On-Demand

| Criterion | Spot | On-Demand |
|---|---|---|
| Price | Typically lower; fluctuates with market demand and instance type | Higher, yet more predictable to budget |
| Longevity | Can be reclaimed when the provider needs capacity | Not subject to Spot reclamation |
| Provisionability | Can face shortages in specific zones or machine types | Generally easier to obtain, though still subject to quotas and capacity |
| Best fit | Fault-tolerant, retryable, or distributed workloads | Baseline workloads, critical services, components needing stability |
| Required design | Instance/zone diversification, interruption handling, restarts | Reserves, autoscaling, and budget caps |

On-Demand reduces Spot reclamation risk, though it is not an absolute guarantee against all infrastructure failures. Workloads with strict capacity commitments may still require capacity reservations, multiple availability zones, or SLA-aligned recovery plans.

## 2. Classifying Workloads Before Choosing Nodes

Do not choose Spot merely because a Pod stores no local data. Evaluate the impact of Pod termination, recovery time, retryability, and dependencies on other services.

| Workload Group | Example | Capacity Strategy |
|---|---|---|
| Mission-critical, synchronous serving | Payment API, authentication, order orchestration | Keep baseline replicas on On-Demand; spread across zones; consider capacity reservations |
| Important and horizontally scalable | Read APIs, multi-replica stateless services | Maintain minimum replicas on On-Demand; use Spot for elastic capacity if replica loss is tolerable |
| Asynchronous and retryable | Invoice workers, notification senders, media transcoding | Can run on Spot if messages are durably queued, processing is idempotent, and retries exist |
| Retryable batch | ETL, report aggregation, batch training | Prefer Spot, checkpoint frequently, and design resumable jobs |
| Stateful or local-data workloads | Single-instance databases, un-replicated caches, node-disk file servers | Never run the sole copy on Spot; use durable storage, replication, and failover |

For a critical service, determine upfront the minimum number of Pods that must keep serving if every Spot node is reclaimed. Those baseline Pods must fit onto On-Demand nodes without relying on Spot availability.

A clean approach is splitting baseline and burst capacity into two Deployments serving the same Service:

- A baseline Deployment with minimum replicas and required node affinity targeting On-Demand.
- An elastic Deployment scaling on Spot that can shrink or restart as capacity fluctuates.
- A Service matching a shared application label to route requests across ready Pods from both Deployments.

This separation governs baseline capacity independently from low-cost elastic capacity. Using a single Deployment with preferred On-Demand affinity still lets Pods spill onto Spot when On-Demand fills up, which fails to guarantee a protected baseline.

## 3. Designing Mixed Node Pools

A node pool groups nodes sharing policies for machine types, zones, labels, taints, and autoscaling behavior. A cluster typically maintains at least two groups:

- **On-Demand pool:** holds baseline capacity for critical services and system components needing stability.
- **Spot pool:** hosts interruption-tolerant workloads and disposable elastic capacity.

Example for an order-processing cluster:

| Node Pool | Illustrative Configuration | Workloads |
|---|---|---|
| **system-ondemand** | On-Demand, minimum 2 nodes, multi-zone | DNS, ingress, autoscalers, and platform components |
| **critical-ondemand** | On-Demand, minimum sized for baseline replicas plus headroom | Payment API, order API |
| **elastic-spot** | Spot, minimum 0 nodes, max bounded by quotas and budget; diverse instance types | Workers, batch jobs, supplemental replicas |

These figures are illustrative. Size pools from CPU/memory requests, baseline Pod counts, zone counts, node fault tolerance, and required reserves. Never set the On-Demand minimum size equal solely to normal steady-state node count; leave room for Pods to reschedule during node maintenance or disconnects.

### 3.1. Diversifying Spot Capacity

A Spot pool restricted to a single machine type in one zone can fail to find capacity as provider demand shifts. You should:

- Allow multiple instance families and sizes with equivalent capabilities.
- Spread nodes across multiple availability zones when applications and storage support it.
- Avoid tying to a single CPU model or hardware architecture if applications run across multiple types.
- Cap aggregate CPU, memory, node counts, and budgets so autoscalers cannot expand unboundedly.
- Track Spot fulfillment rates and how long Pods wait to schedule.

Diversification improves fulfillment odds, though it cannot eliminate region-wide Spot scarcity. Always preserve a path to run critical workloads on On-Demand.

### 3.2. Cluster Autoscaler and Capacity Buffers

The Kubernetes scheduler only picks existing eligible nodes. When Pods sit Pending due to insufficient resources, Cluster Autoscaler or node pool autoscaling can request more nodes. Karpenter is another option on supported clusters, selecting machine types dynamically from Pod requirements and `NodePool` policies.

An autoscaler cannot conjure Spot capacity if the cloud provider has none available. When a Spot pool cannot provision machines, the system needs one of several pre-planned responses:

- Let fault-tolerant workloads wait if SLAs allow.
- Shift On-Demand-capable workloads onto a stable pool via a fallback policy.
- Expand into additional instance types or zones.
- Retain an On-Demand capacity buffer large enough for minimum critical workloads.

For critical workloads, pre-allocate headroom on On-Demand rather than waiting for a node reclamation before requesting new instances. Node provisioning, image pulls, and application startup all add recovery latency.

## 4. Controlling Pods with Labels, Taints, and Affinity

Scheduling controls determine which workloads may run on which nodes.

- **Label:** attaches attributes to nodes, such as **capacity.example.com/type=on-demand** or **capacity.example.com/type=spot**.
- **Taint:** marks nodes so Pods without matching tolerations cannot schedule onto them.
- **Toleration:** lets a Pod accept a taint; tolerations alone do not force Pods onto tainted nodes.
- **Node affinity / `nodeSelector`:** restricts or prefers nodes based on labels.
- **Topology spread constraint:** distributes Pods across zones or nodes to prevent piling replicas into one failure domain.

Configure labels and taints from node pool or node provisioning templates so new nodes inherit identical attributes. Never rely on manual labeling after a node joins the cluster.

### 4.1. Baseline Deployment Running on On-Demand

Example payment API requiring at least three replicas restricted to nodes carrying the On-Demand label. The On-Demand node pool must have sufficient resources across multiple zones to place all three Pods.

    apiVersion: apps/v1
    kind: Deployment
    metadata:
      name: payment-api-core
    spec:
      replicas: 3
      selector:
        matchLabels:
          app: payment-api
          tier: core
      template:
        metadata:
          labels:
            app: payment-api
            tier: core
        spec:
          affinity:
            nodeAffinity:
              requiredDuringSchedulingIgnoredDuringExecution:
                nodeSelectorTerms:
                  - matchExpressions:
                      - key: capacity.example.com/type
                        operator: In
                        values:
                          - on-demand
          topologySpreadConstraints:
            - maxSkew: 1
              topologyKey: topology.kubernetes.io/zone
              whenUnsatisfiable: DoNotSchedule
              labelSelector:
                matchLabels:
                  app: payment-api
                  tier: core
          containers:
            - name: api
              image: example.invalid/payment-api:v1
              resources:
                requests:
                  cpu: 500m
                  memory: 512Mi
                limits:
                  cpu: "1"
                  memory: 1Gi
              readinessProbe:
                httpGet:
                  path: /ready
                  port: 8080
                periodSeconds: 5
                failureThreshold: 3

Required affinity ensures baseline Pods only schedule onto On-Demand nodes with matching labels. **topologySpreadConstraints** spreads Pods across zones; the cluster must have enough matching zones and nodes, or Pods will stay Pending. In real environments, replace the illustrative image with a valid image and configure probes, ports, security contexts, and secrets for your application.

Create a PodDisruptionBudget to cap how many baseline replicas can be disrupted during controlled eviction operations:

    apiVersion: policy/v1
    kind: PodDisruptionBudget
    metadata:
      name: payment-api-core-pdb
    spec:
      minAvailable: 2
      selector:
        matchLabels:
          app: payment-api
          tier: core

With three replicas, **minAvailable: 2** permits at most one Pod to undergo voluntary eviction at a time via the Eviction API. A PDB protects during node drains or controlled maintenance. A PDB does not stop a provider from reclaiming a Spot node, does not guard against involuntary node failures, and does not replace running replicas across multiple failure domains.

### 4.2. Interruption-Tolerant Workers Running on Spot

Message-processing workers can run on Spot when messages sit in a durable broker, workers acknowledge only after completion, and messages can be redelivered if a Pod stops mid-flight.

Example worker Deployment:

    apiVersion: apps/v1
    kind: Deployment
    metadata:
      name: invoice-worker
    spec:
      replicas: 4
      selector:
        matchLabels:
          app: invoice-worker
      template:
        metadata:
          labels:
            app: invoice-worker
        spec:
          terminationGracePeriodSeconds: 60
          tolerations:
            - key: dedicated
              operator: Equal
              value: spot
              effect: NoSchedule
          affinity:
            nodeAffinity:
              requiredDuringSchedulingIgnoredDuringExecution:
                nodeSelectorTerms:
                  - matchExpressions:
                      - key: capacity.example.com/type
                        operator: In
                        values:
                          - spot
          containers:
            - name: worker
              image: example.invalid/invoice-worker:v1
              resources:
                requests:
                  cpu: 500m
                  memory: 512Mi
              env:
                - name: QUEUE_NAME
                  value: invoices
              lifecycle:
                preStop:
                  exec:
                    command: ["/app/worker", "drain"]

The **preStop** command illustrates a drain interface exposed by the application; the real binary must support it. Upon receiving a termination signal, the worker should stop pulling new messages, finish in-flight work if time permits, or let the broker redeliver unacknowledged messages. **terminationGracePeriodSeconds** only sets how long Kubernetes waits before killing the Pod; it does not extend the cloud provider's reclamation window.

For workers, ensure:

- Idempotent processing so redelivered messages never create duplicate transactions or invoices.
- Acknowledging messages only after results are durably persisted.
- Bounded retries, backoff, and a dead-letter queue for persistently failing messages.
- Compatible processing times, visibility/ack timeouts, and graceful shutdown durations.
- Periodic checkpointing if long-running tasks cannot restart from scratch.

If workers run solely on Spot, mass Spot reclamations can sharply drop processing throughput. Keep a baseline group of workers on On-Demand and use Spot for elastic workers, especially when backlogs must drain within a defined SLA.

## 5. Maintaining Capacity for Critical Workloads

Capacity strategy starts with service objectives. For example, an order API must retain at least six ready Pods during a zone failure or full Spot reclamation. From that goal, work backward to size On-Demand resources.

An estimation process:

1. Determine the minimum replicas required to keep serving.
2. Sum each Pod's CPU and memory requests, plus DaemonSets and system workloads.
3. Verify Pod schedulability after losing one node or one zone per your fault model.
4. Add headroom for rolling updates, scale-outs, and new Pod startups.
5. Check quotas, instance limits, and capacity reservations if SLAs require them.
6. Validate by simulating node loss in a test environment.

Example: a service needs six baseline Pods, each requesting `500m` CPU and `512 MiB` memory. Raw application demand is at least 3 vCPUs and 3 GiB memory. Real required capacity is higher because nodes also run DaemonSets, `system-reserved`, `kube-reserved`, and need headroom. To survive losing one node, verify remaining capacity after subtracting that entire node's resources.

### 5.1. On-Demand Baseline and Spot Burst

A common pattern for critical services:

- Keep enough On-Demand capacity for baseline replicas and system Pods.
- Use Spot for supplemental replicas or retryable workers.
- As load climbs, HPA adds Pods and the node autoscaler scales the corresponding node pool.
- When Spot is scarce, elastic workloads wait or fall back according to policy.
- When Spot nodes are reclaimed, baseline replicas keep serving while supplemental replicas recreate once capacity returns.

For APIs serving live requests, baseline replicas should always sit on On-Demand. Elastic capacity can live in a separate Deployment so all replicas of a critical Deployment are never accidentally scheduled onto Spot.

### 5.2. Zone and Node Redundancy

Running multiple replicas on one node gives zero node fault tolerance. Likewise, placing all nodes in one zone leaves you exposed to zone outages.

Use topology spread or pod anti-affinity to distribute replicas. Watch for scheduling rules that can leave Pods Pending if one zone runs out of capacity. For zone-bound storage, account for PersistentVolume topology and detach/attach behavior when Pods reschedule.

For stateful systems, prefer application-layer replication or managed data services. A single-replica StatefulSet on Spot with a volume does not become highly available on its own. With zone-locked volumes, rescheduling a Pod into another zone may be impossible without an appropriate data recovery mechanism.

### 5.3. PriorityClass and PDBs

`PriorityClass` lets the scheduler favor critical Pods when Pods compete for resources. High-priority Pods can preempt lower-priority Pods inside the cluster to free space. This does not make Spot nodes less likely to be reclaimed, nor does it create extra hardware capacity.

A PDB governs voluntary evictions via the Kubernetes Eviction API. It helps during node drains and planned maintenance, but is not a shield against sudden node loss. Never make a PDB so tight that routine maintenance stalls; at the same time, keep enough live replicas to satisfy **minAvailable**.

For retryable Spot workloads, PDBs can allow disruptions aligned with the design. For critical workloads, apply PDBs to On-Demand baseline replicas alongside readiness probes, multi-zone placement, and spare capacity.

## 6. Handling Spot Reclamation Events

When a node receives a reclamation notice, the goal is moving workloads off before the node vanishes. You need mechanisms to detect provider events, cordon the node, drain Pods, and let the scheduler/autoscaler supply replacement capacity.

Depending on the platform, this may involve:

- AWS: AWS Node Termination Handler or built-in interruption/rebalance event handling with node provisioning.
- GKE: platform Spot VM lifecycle handling paired with workload interruption tolerance.
- Azure: integrating Spot VM eviction notices with node drain and workload rescheduling.

Exact tool names and capabilities vary by cloud service, cluster version, and node provisioning model. Check provider documentation for your running version. Never assume Kubernetes automatically catches every VM reclamation notice.

### 6.1. Sequence When a Node Is About to Be Reclaimed

1. Receive the notice from the metadata service, event stream, or node lifecycle monitor.
2. Mark the node unschedulable with `cordon`.
3. Drain Pods via the Kubernetes Eviction API if remaining lead time allows.
4. Applications receive termination signals, stop pulling new work, and flush/checkpoint required state.
5. The scheduler places replacement Pods onto nodes with spare capacity.
6. The autoscaler adds nodes per policy; if Spot is unavailable, use fallback capacity or let workloads queue/wait.
7. Monitor until replicas reach Ready and service capacity returns to target.

Notice lead times can be brief or absent in some scenarios. Application design must tolerate sudden node disappearance. Draining improves orderly shutdown when notices arrive, but never replaces retries, replication, and durable storage.

### 6.2. Graceful Shutdown in Applications

For APIs, upon receiving `SIGTERM`:

- Stop accepting new requests or flip readiness to unready.
- Wait for the load balancer to stop routing new requests per platform behavior.
- Complete in-flight requests within the time budget.
- Close connections, flush telemetry, and exit cleanly.

For workers:

- Stop polling or accepting new messages.
- Finish in-progress work if possible.
- Write checkpoints or let unacknowledged messages redeliver.
- Close broker connections and exit.

Coordinate **preStop**, **terminationGracePeriodSeconds**, and `SIGTERM` handling. If shutdown takes longer than the actual reclamation window, Pods will still be forcibly terminated before finishing.

## 7. Autoscaling and Fallback

HPA adjusts Pod counts from application or resource metrics; the node autoscaler provisions nodes when Pods cannot schedule. Both layers must be configured in sync.

Example:

- Baseline API HPA holds at least six replicas on On-Demand.
- Worker HPA scales Pods based on queue depth.
- Spot node pool has min size 0 and max size bounded by quotas.
- On-Demand node pool maintains baseline capacity with room for critical workloads.
- When Spot cannot provision instances, workers wait or shift to On-Demand per fallback policy.

Never set HPA `maxReplicas` higher than node provisioning limits and downstream capacity without safeguards. If HPA spawns Pods quickly while node provisioning takes minutes, Pods remain Pending and SLOs suffer.

With Karpenter or Cluster Autoscaler, verify:

- `NodePool`/node groups include machine types and zones matching Pod requests.
- Taints, labels, and affinity on node pools match Pods.
- Aggregate resource limits and provider quotas are adequate.
- Consolidation/scale-down policies will not strip away baseline capacity.
- Spot fallback is permitted and prioritizes On-Demand as designed.

When mixing Spot and On-Demand in one node pool or `NodePool` policy, verify priority order, allowed instance types, and behavior during Spot stockouts. Never assume fallback works automatically until configured and tested.

## 8. Monitoring and Alerting

Monitor node health, Pod status, and service quality together. A cluster can still show Ready nodes while lacking usable capacity for workloads due to taints, affinity, or quotas.

Signals to watch:

| Group | Metrics/Events | Meaning |
|---|---|---|
| Spot lifecycle | Interruptions, rebalance/eviction notices, reclaimed nodes | Reveals disruption frequency |
| Node capacity | CPU/memory allocatable, Pending/NotReady nodes, nodes per pool/zone | Detects capacity deficits or skew |
| Scheduling | Pending Pods, `FailedScheduling`, time from Pending to Ready | Measures capacity provisioning latency |
| Workloads | Desired/available replicas, restarts, evictions, rollouts | Confirms services retain sufficient copies |
| Queues/batch | Queue depth, message age, retries, checkpoints, job duration | Evaluates interruption impact on work |
| SLOs | p95/p99 latency, error rate, availability, request throughput | Confirms user-facing service health |

Alert when:

- On-Demand baseline replicas drop below required minimums.
- Critical Pods stay Pending or fail to reach target readiness within SLA windows.
- Spot interruptions spike or the Spot pool repeatedly fails to provision nodes.
- Worker backlog or message age exceeds SLAs.
- The On-Demand pool runs out of headroom to absorb Pods during Spot reclamations.

Track costs per pool. Spot carries lower unit pricing, yet frequent fallback onto On-Demand can shift total spend far from initial estimates. Weigh cost against availability, processing time, and incident-response overhead.

## 9. Pre-Production Verification Workflow

Test in staging or a controlled cluster:

1. **Record baseline:** confirm baseline replicas, On-Demand nodes, zones, CPU/memory requests, and SLO metrics.
2. **Verify scheduling:** deploy test baseline and Spot Pods; confirm labels, taints, tolerations, affinity, and topology spread behave as expected.
3. **Verify PDBs:** drain an On-Demand node under controlled conditions; confirm minimum Pods and eviction behavior.
4. **Simulate Spot interruption:** terminate a Spot node using your platform's test mechanism. Observe notices, cordon, drain, Pod rescheduling, and recovery time.
5. **Test Spot capacity exhaustion:** cap or temporarily disable the Spot pool in testing; verify critical workloads keep running on On-Demand while fault-tolerant workloads wait or fall back per policy.
6. **Test node/zone loss:** verify topology spread, replicas, and surviving capacity when one failure domain goes offline.
7. **Verify applications:** confirm APIs do not drop requests beyond SLOs; workers lose zero messages, handle duplicates safely, and resume from checkpoints.
8. **Verify autoscalers:** confirm HPA and the node autoscaler coordinate without creating runaway Pending Pods or breaching quotas.
9. **Reconcile costs:** compare Spot share, On-Demand baseline, fallback frequency, and operational cost against budget.

Never test node reclamation by randomly deleting production nodes. Use staging environments, controlled disruption drills, and scenarios agreed upon with operations teams.

## 10. Common Scenarios and Troubleshooting

| Symptom | Possible Cause | What to Check |
|---|---|---|
| Critical Pod Pending while Spot nodes have room | Pod requires On-Demand label while available nodes are Spot | Check node labels, affinity, and On-Demand capacity |
| Workers fail to schedule onto Spot | Missing toleration or label/taint mismatch | Run `kubectl describe pod` and `kubectl describe node` |
| Spot reclaimed yet Pods fail to recreate | Node autoscaler lacks capacity, quotas, or matching machine types | Check autoscaler events, quotas, instance types, and zones |
| PDB blocks node drain | `minAvailable` too high or insufficient healthy replicas | Check PDB status, available replicas, and drain plan |
| API errors persist after scaling replicas | Downstream, database, or network bottleneck | Correlate latency, connection pools, error rate, and throughput |
| Workers duplicate messages after interruption | Acked before persisting results or missing idempotency | Check commit/ack order, retries, and idempotency keys |
| Pods fail to drain in time | Slow shutdown handler or mismatched timeouts | Check `SIGTERM`, `preStop`, grace period, and interruption lead time |
| On-Demand pool runs out of room when Spot drops | Baseline capacity/headroom sized too low | Recalculate N+1, quotas, zone capacity, and reservations |

## 11. Implementation Checklist

- [ ] Classified workloads by criticality, retryability, and recovery time.
- [ ] Defined baseline replicas required when all Spot capacity disappears.
- [ ] Provisioned enough On-Demand capacity for baseline replicas, system components, and headroom.
- [ ] Separated Spot and On-Demand node pools with consistent node-level labels and taints.
- [ ] Applied required affinity for workloads guaranteed to run on On-Demand.
- [ ] Applied matching tolerations and affinity for interruption-tolerant workloads.
- [ ] Spread replicas across nodes and zones via topology spread or anti-affinity.
- [ ] Configured appropriate PDBs while understanding PDB limits during node failures.
- [ ] Ensured workers are idempotent, retry safely, ack at the right step, and checkpoint when needed.
- [ ] Integrated interruption handling, cordon/drain, and graceful shutdown.
- [ ] Configured autoscalers, quotas, node pool limits, and Spot-shortage fallbacks.
- [ ] Monitored interruptions, Pending Pods, per-zone capacity, available replicas, and SLOs.
- [ ] Tested Spot node loss, Spot capacity shortages, On-Demand drains, and workload recovery.
- [ ] Compared actual spend against availability and budget targets.

## Conclusion

Spot nodes reduce compute costs for interruption-tolerant workloads, but Spot capacity is never continuously guaranteed. Keep baseline replicas and headroom on On-Demand for critical workloads, separate node pools with labels/taints/affinity, spread replicas across failure domains, and design applications to drain, retry, or recover cleanly. Only place workloads onto Spot after validating both node reclamation and Spot capacity exhaustion scenarios.
