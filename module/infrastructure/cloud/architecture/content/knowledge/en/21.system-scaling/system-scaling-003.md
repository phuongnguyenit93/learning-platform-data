# Scaling Lag, Minimum Capacity, and Stabilization Windows

## 1. Autoscaling Does Not Increase Capacity Instantaneously

When traffic surges rapidly, a system needs more instances, pods, tasks, or workers to keep serving requests. Autoscaling adjusts resource counts to match load, yet there is always a delay between when load rises and when new capacity can actually serve traffic. This window can include metric collection time, policy evaluation, capacity API calls, compute provisioning, machine boot, image pull, application initialization, cache warm-up, and passing readiness checks.

If the system only starts scaling once latency has already breached its threshold, new capacity may arrive too late. While waiting, queues grow, requests time out, retries amplify load, and dependencies can overload. Conversely, if scale-in happens too fast as soon as metrics dip, resources may be reclaimed right before the next wave of traffic arrives or while requests are still in flight.

Three concepts in this lesson are directly connected:

- **Scaling lag / scale-out delay:** the time from when a signal indicates more capacity is needed until the new capacity is genuinely usable.
- **Minimum capacity / baseline capacity:** the lowest level of resources maintained to serve baseline load, survive failures, and meet latency targets during autoscaling.
- **Stabilization window:** the period used to observe and smooth scaling decisions, particularly to avoid scaling in immediately after a brief dip or overreacting to noisy metrics.

In the **CLOUD_ARCHITECTURE** module, this is an architectural decision affecting reliability, performance, scalability, cost, and operations. The goal is not to keep excess machines or scale fast at any cost; the goal is to maintain enough capacity for the required duration based on SLOs and real load patterns.

### Learning Objectives

After this lesson, you will be able to:

1. Break down scaling lag into measurable components.
2. Calculate baseline/minimum capacity from baseline load, headroom, and fault tolerance.
3. Choose appropriate metrics and scale-out/scale-in thresholds.
4. Design stabilization windows, cooldowns, and warm pools to curb oscillation.
5. Distinguish provisioned capacity from genuinely ready-to-serve capacity.
6. Assess autoscaling's impact on databases, queues, networks, and downstream dependencies.
7. Define SLOs, dashboards, and test cases for bursts, ramp-ups, spikes, and sustained load.

## 2. Lifecycle of a Scale-Out Decision

A policy might detect rising CPU quickly, yet the workload does not gain serving capacity immediately. You must examine the entire chain:

~~~mermaid
flowchart LR
    A["Traffic / backlog increases"] --> B["Metric collection"]
    B --> C["Autoscaler evaluation"]
    C --> D["Capacity request"]
    D --> E["Provision compute"]
    E --> F["Boot / schedule"]
    F --> G["Image pull / init"]
    G --> H["Readiness / warm-up"]
    H --> I["Usable capacity"]
~~~

Total scaling lag can be modeled as:

\[
T_{usable} =
T_{observe} + T_{decision} + T_{provision}
+ T_{startup} + T_{ready}
\]

Where:

- **Observe:** waiting for metric scrape, aggregation, or event ingestion.
- **Decision:** autoscaler computing the delta while applying min/max and policy rules.
- **Provision:** cloud provider allocating the VM/node or scheduler finding compute.
- **Startup:** booting OS/runtime, pulling images, mounting volumes, loading models, and starting the process.
- **Ready:** health/readiness probes passing, caches or connection pools sufficiently warmed.

This is an analytical model, not a claim that every stage is strictly sequential. Some steps run in parallel or are cached; measure actual durations by percentile.

### 2.1. Intervals to Measure

| Component | Start/End Points | Causes of Delay |
|---|---|---|
| Metric delay | Load changes → metric reflects it | Scrape interval, aggregation window, telemetry pipeline |
| Evaluation delay | Metric available → policy decides | Controller sync interval, thresholds, scaling policy |
| Provision delay | Request → VM/node/task allocated | Cloud quotas, capacity shortages, node provisioning |
| Scheduling delay | Pod/task pending → placed on compute | Insufficient CPU/memory, affinity, taints, resource fragmentation |
| Startup delay | Allocated → process starts | OS boot, image pull, dependency initialization |
| Readiness delay | Process starts → accepts traffic | Health checks, warm cache, model loading, connection setup |
| Routing delay | Ready → traffic actually arrives | Endpoint propagation, load balancer health, DNS/service discovery |

Do not measure only the time until the autoscaler API returns success. An instance may already exist without receiving traffic; a pod may be `Running` while its readiness probe is still failing.

## 3. Load Changing Faster Than Scaling Speed

### 3.1. Burst Example

Suppose an API normally receives 1,000 requests/second. A campaign pushes traffic to 4,000 requests/second within 20 seconds. Each replica safely handles 250 requests/second; the system starts with 6 replicas.

- Initial capacity: 6 × 250 = 1,500 requests/second.
- Capacity needed to serve 4,000 requests/second: at least 16 replicas by theoretical division.
- Immediate deficit during the burst: 2,500 requests/second.
- If scale-out takes 90 seconds, the system endures a severe deficit for a substantial window.

The figure 16 does not yet account for headroom, uneven traffic distribution, p99 latency, replica failures, or dependency limits. If you target at most 70% capacity utilization under normal conditions, required capacity is even higher:

\[
N = \left\lceil \frac{4000}{250 \times 0.70} \right\rceil = 23
\]

This example shows why reacting after a burst starts may not suffice. Depending on workload type, you need a higher baseline, scheduled/predictive scaling, warm pools, or buffering mechanisms such as queues.

### 3.2. Load Patterns

| Load Pattern | Characteristics | Typically Suitable Response |
|---|---|---|
| **Steady growth** | Gradual increase over minutes/hours | Reactive autoscaling usually suffices if lag is measured |
| **Sharp spike** | Steep jump within seconds | Baseline/headroom, pre-scaling, queues, or admission control |
| **Predictable peak** | Clear daily or campaign schedule | Scheduled scaling paired with reactive scaling |
| **Bursty arrivals** | Short, irregular traffic bursts | Buffer queues, concurrency caps, backlog-based scaling |
| **Long-running growth** | Sustained high load | Scale capacity, verify quotas, optimize bottlenecks and cost |
| **Sudden drop** | Rapid traffic decline | Scale-in stabilization, draining, and protecting in-flight requests |

No single policy is optimal for every load pattern. For interactive APIs, latency during bursts is critical. For batch queues, temporary backlogs may be acceptable if message age stays within SLA.

## 4. Baseline and Minimum Capacity

**Minimum capacity** is the lowest resource level a system maintains even when current metrics are low. It prevents the application from starting from zero or waiting too long to restore minimal serving capability.

Minimum capacity can be expressed as:

- Minimum number of instances/replicas.
- Minimum number of nodes or workers in a cluster.
- Number of warm execution environments or warm pool entries.
- Provisioned concurrency level for functions.
- Minimum number of connections/partitions/consumers.
- Reserve capacity for failure domains or maintenance.

### 4.1. Minimum Does Not Necessarily Equal One

Running a single replica may work in dev, but production must account for:

- Fault tolerance when a replica, node, or zone goes down.
- Whether rolling deployments need extra capacity to replace old instances.
- Whether the workload binds sessions/state to instances.
- Minimum baseline traffic and latency targets.
- Whether warm-up takes a long time.
- Whether at least one instance is required per zone.

Minimum capacity can be determined by availability and topology requirements, not just average traffic.

### 4.2. Calculating Baseline From Throughput

Suppose:

- Expected peak traffic: 2,400 requests/second.
- Safe throughput per replica: 300 requests/second.
- Maximum target utilization: 60%.
- Must survive losing one replica while still carrying target load.

Capacity per replica at target utilization:

\[
300 \times 0.60 = 180 \text{ requests/second}
\]

Active replicas required:

\[
N_{active} = \left\lceil \frac{2400}{180} \right\rceil = 14
\]

To survive the loss of one replica:

\[
N_{total} = N_{active} + 1 = 15
\]

This is an illustrative calculation; multi-zone systems may require different redundancy allocations. Always load test to establish safe throughput rather than taking peak benchmark numbers.

### 4.3. Minimum, Desired, and Maximum

| Parameter | Meaning | Design Question |
|---|---|---|
| **Minimum** | Never scale below this floor | Enough for baseline load and single failures? |
| **Desired** | Current level the autoscaler targets | Does it accurately reflect metrics and policy? |
| **Maximum** | Autoscaling ceiling | Enough headroom without breaching DB/quota/cost limits? |

Maximum is not just a compute limit. If replicas scale from 20 to 100 while the database only tolerates 40 new connections, autoscaling can worsen an outage.

## 5. Warm Pools, Pre-Warming, and Provisioned Capacity

To shorten scaling lag, a system can maintain partially initialized or pre-allocated resources.

| Mechanism | Meaning | Best Suited For |
|---|---|---|
| **Baseline replicas** | Always keep a set of processes/replicas running | APIs and workers needing fast response |
| **Warm pool** | Keep VMs booted or partially initialized for fast handoff | VMs/compute with slow startup |
| **Provisioned concurrency** | Pre-warm execution environments for functions per service config | Cold-start-sensitive serverless functions |
| **Scheduled pre-scale** | Raise desired capacity ahead of predicted peaks | Ticketing drops, campaigns, scheduled reports |
| **Predictive scaling** | Forecast load and provision capacity ahead | Workloads with stable historical patterns |
| **Image/model prefetch** | Pre-download images, packages, or models | Large containers, inference workloads |
| **Connection/cache warm-up** | Pre-populate pools and caches before heavy load | DB-bound APIs or cache-dependent apps |

Warm resources carry idle cost and can become stale if code or config changes. Define refresh cycles, health checks, expiration, and credential protection.

### 5.1. When Is a Warm Pool Unnecessary?

- Workloads can scale from zero and still satisfy SLOs.
- Background tasks tolerate startup delays.
- Cold starts are negligible relative to the latency budget.
- The cost of maintaining warm capacity outweighs the latency benefit.
- Traffic is unpredictable and already backed by an appropriate buffer.

## 6. Selecting Metrics for Autoscaling

Good metrics reflect actual busyness or demand, correlate with the bottleneck, and shift early enough for the policy to react.

| Metric | When Useful | Limitations |
|---|---|---|
| CPU utilization | CPU-bound workloads where request load tracks CPU | Misses I/O waits, queueing, or memory pressure |
| Memory utilization | Workloads with clear memory pressure | Scale-out does not fix leaks; metric may stay high when idle due to caches |
| Request rate | APIs with relatively consistent per-request cost | Does not reflect request complexity |
| Concurrent requests / in-flight | Each instance has a concurrency ceiling | Must measure request duration and per-instance capacity accurately |
| Queue depth | Asynchronous workers | Raw depth ignores processing rate and message age |
| Queue age / oldest message | Directly tied to freshness/SLA | Needs reliable metrics and drain-rate-aware scaling |
| Latency p95/p99 | Detects when users start feeling impact | Lagging signal; may trigger after SLO is already breached |
| DB connections/CPU/locks | Detects data-layer bottlenecks | May indicate a need to throttle/cap app scaling rather than scale further |
| Custom business metric | Workloads with variable cost/request | Requires instrumentation and metric quality governance |

Do not autoscale solely on CPU if the true bottleneck is database connections or external API quotas. Adding replicas increases concurrent requests and can collapse downstream services.

### 6.1. Queue Backlog and Processing Rate

For queues, current message count alone is insufficient. Estimate:

- Backlog \(B\): waiting messages.
- Arrival rate \(\lambda\): incoming messages per second.
- Service rate per worker \(\mu\): messages processed per second.
- Worker count \(N\): total processing capacity roughly \(N\mu\).

Backlog shrinks when:

\[
N\mu > \lambda
\]

To drain the backlog within time \(T\), required capacity is approximately:

\[
N\mu \geq \lambda + \frac{B}{T}
\]

This simple model assumes steady rates, ignoring retries, batch sizes, and processing time distributions. Use it as an initial estimate, then validate against real workloads.

## 7. Stabilization Windows, Cooldowns, and Hysteresis

An autoscaler can oscillate if a metric crosses a threshold and immediately drops right after scaling. Rapidly scaling out and back in increases cost, causes connection churn, triggers cache misses, and destabilizes deployments.

A **stabilization window** looks back over recent recommendations/metrics before executing a scaling move, especially scale-in. A **cooldown** is a post-scaling waiting period during which the policy restricts or defers subsequent decisions. **Hysteresis** uses separate thresholds for scale-out and scale-in to prevent constant toggling around a single boundary.

### 7.1. Hysteresis Illustration

~~~mermaid
flowchart TD
    M["Observe utilization"] --> High{"Above scale-out threshold?"}
    High -->|Yes| Out["Scale out"]
    High -->|No| Low{"Below scale-in threshold long enough?"}
    Low -->|Yes| Stable{"Minimum capacity and drain safe?"}
    Stable -->|Yes| In["Scale in gradually"]
    Stable -->|No| Keep["Keep capacity"]
    Low -->|No| Keep
    Out --> Window["Stabilization / cooldown"]
    In --> Window
    Keep --> M
    Window --> M
~~~

For example, scale out when CPU stays above 65% for 2 continuous minutes, but only scale in when CPU stays below 35% for 10 continuous minutes with no rise in queue age or latency. Two distinct thresholds and two time windows create a buffer zone.

### 7.2. Do Not Use Cooldowns to Mask Bad Metrics

An overly long cooldown prevents the system from adding capacity fast enough for the next traffic wave. An overly short cooldown invites oscillation. Rely on well-grounded metric windows and policies; separate fast scale-out from cautious scale-in when supported by your tooling.

### 7.3. Scale-In Requires Draining

Before removing capacity:

- Stop routing new requests or delivering new messages to the terminating instance.
- Wait for in-flight requests and active tasks to finish within a grace period.
- Ensure unacknowledged queue messages can be safely redelivered.
- Execute `preStop`/graceful shutdown hooks where the platform supports them.
- Avoid terminating too many replicas simultaneously or all replicas in a single zone.

Unsafe scale-in causes failed requests, duplicate messages, or interrupted transactions. Idempotency and graceful termination are core parts of scaling architecture.

## 8. Choosing Thresholds and Metric Windows

Scaling thresholds should be derived from capacity tests, latency SLOs, error budgets, and load-to-capacity relationships. A structured process:

1. Load test to establish safe single-instance throughput at target latency.
2. Measure scale-out time from metric signal to usable capacity at p50/p95/p99.
3. Determine headroom required to absorb load during scaling lag.
4. Set thresholds below the saturation zone rather than waiting for 100% CPU or latency.
5. Pick an aggregation window long enough to filter noise without delaying reaction too much.
6. Set a lower scale-in threshold and a longer stabilization window.
7. Validate across scenarios: ramp-up, spike, short burst, sustained load, and sudden drop.

### 8.1. How Metric Windows Affect Responsiveness

| Window | Advantage | Risk |
|---|---|---|
| Very short | Reacts rapidly to spikes | Noisy, over-scaling |
| Medium | Smooths minor fluctuations | Can lag during very sharp bursts |
| Long | Stable, few false triggers | System can overload before a decision is made |

There is no universal default duration. Choose based on sampling interval, scaling lag, load profile, and the cost of delayed reactions.

## 9. Sizing Headroom to Survive Scaling Lag

Baseline capacity must sustain load while waiting for new capacity. If load grows faster than instances can start, headroom or buffers must absorb the shortfall.

Example:

- Current capacity: 2,000 requests/second.
- Baseline load: 1,200 requests/second.
- Load can ramp linearly by an extra 1,000 requests/second over 60 seconds.
- Scaling lag p95: 90 seconds.

For the first 90 seconds, the system gets no new capacity. If load rises steadily by 1,000 requests/second over 60 seconds and holds at 2,200, 2,000 capacity falls short by the end of the ramp-up. You must raise the baseline or add buffers/admission control because scale-out only becomes ready after the deficit has already occurred.

One way to model this is comparing **cumulative demand** against **cumulative capacity** across the scaling lag window, rather than only comparing final load against final capacity.

In queue-based systems, backlogs can absorb temporary gaps as long as message age stays within SLA. For synchronous APIs, gateway queues do not always exist; controlled load shedding, 429/503 responses, or concurrency limits may be required.

## 10. Do Not Scale Applications Past Downstream Limits

Scaling out increases concurrent callers hitting databases, caches, payment providers, object storage, and internal APIs. Without caps, autoscaling simply shifts the bottleneck from the app to dependencies.

### 10.1. Connection Amplification

Suppose each replica opens up to 40 DB connections. When scaling from 10 to 50 replicas:

\[
Connections_{max} = 50 \times 40 = 2000
\]

If the database only safely supports 600 connections for this workload, scaling out can exhaust DB connections and take down the entire application.

Mitigations include:

- Smaller, properly sized connection pools.
- Database proxies/poolers.
- Application-level concurrency caps.
- Queues to smooth write rates.
- Read/write separation or controlled caching.
- Workload isolation and per-tenant/per-priority quotas.

### 10.2. Multi-Tier Scaling Policies

| Component | Scaling Mechanism | Guardrail |
|---|---|---|
| API replicas | Request rate, concurrency, CPU | Max replicas, connection pools, and rate limits |
| Workers | Queue age/backlog | Concurrent job caps and downstream quotas |
| Database | Vertical/read replicas/partitioning by engine | Connections, IOPS, locks, replication lag |
| Cache | Nodes/shards/replicas | Memory, evictions, hot keys, and failover |
| External API consumers | Worker concurrency | Provider quotas, `Retry-After`, and circuit breakers |

Autoscaling must be designed as a multi-layered system, not just a single policy on the web tier.

## 11. Scale-to-Zero and Cold Starts

Some serverless or container platforms support scaling to zero to avoid holding idle capacity. This lowers idle cost, but the first request absorbs startup time.

Scale-to-zero fits when:

- The workload does not require immediate low-latency responses on the first request.
- Traffic is sparse or has long idle gaps.
- Queues or asynchronous APIs absorb incoming requests.
- Cold starts fit within SLA or a processing status can be returned.

Not suitable when:

- APIs have strict latency SLOs even on the first request.
- Initialization loads large models or connects to slow dependencies.
- Traffic is unpredictable with massive bursts.
- Consumers must maintain persistent sessions/connections.

You can combine minimum instances, provisioned concurrency, or scheduled pre-warming. Measure cold-start latency separately from steady-state latency.

## 12. Scheduled and Predictive Scaling

When load is predictable from history, business calendars, or known events, capacity can be staged before reactive metrics cross thresholds.

Examples:

- Raise baseline 30 minutes before ticket sales open.
- Prepare worker and database capacity before batch settlement.
- Warm caches and scale edge/application tiers before livestreams or campaigns.

Predictive scaling requires:

- Reliable schedules or sufficient historical data.
- Distinguishing weekdays, weekends, and special events.
- Cost bounds and maximum capacity caps.
- Reactive scaling as a safety net when forecasts miss.
- Stabilized scale-in after peaks subside.

Forecasting never replaces reactive control. If a campaign unexpectedly brings double the projected traffic, the system still needs to react or shed load.

## 13. Kubernetes HPA, Cluster Autoscaler, and Node Provisioning

In Kubernetes, scaling happens across multiple layers:

- **Horizontal Pod Autoscaler (HPA):** adjusts workload replica counts based on metrics.
- **Cluster Autoscaler / node autoscaling:** adds or removes nodes when pods cannot be scheduled or capacity sits idle per policy.
- **Vertical Pod Autoscaler (VPA):** recommends or adjusts CPU/memory requests depending on tool configuration and mode.

HPA increasing pod counts does not mean nodes exist to run them. Pods can stay `Pending` if the cluster lacks CPU/memory or placement constraints fail. Node autoscalers need time to create VMs, boot, join the cluster, and become ready; image pulls and readiness add further delay.

~~~mermaid
flowchart TD
    Metric["CPU / memory / custom metric"] --> HPA["HPA increases desired pods"]
    HPA --> Pending{"Enough schedulable node capacity?"}
    Pending -->|Yes| Schedule["Scheduler places pods"]
    Pending -->|No| NodeAuto["Node autoscaler requests nodes"]
    NodeAuto --> Boot["Provision and join node"]
    Boot --> Schedule
    Schedule --> Pull["Pull image and initialize"]
    Pull --> Ready["Readiness passes"]
    Ready --> Serve["Pods serve traffic"]
~~~

Measure HPA decision time, pod scheduling, node provisioning, and readiness independently. If HPA reacts fast while node provisioning takes 3 minutes, latency-sensitive workloads need baseline node capacity, overprovisioning, or warm node pools.

## 14. Functions/Serverless: Concurrency and Provisioned Capacity

Serverless reduces instance management overhead, but does not mean infinite capacity or instantaneous readiness.

Key limits:

- Account/region concurrency quotas.
- Per-function reserved/provisioned concurrency.
- Platform burst scaling behavior and ramp rates.
- Execution duration, memory, payload, and connection quotas.
- Downstream DB/API concurrency.
- Cold starts and package/model initialization.

For latency-sensitive APIs, provisioned concurrency or minimum instances can curb cold starts. For event consumers, scale on queue age while capping batch sizes and concurrency so DBs/providers are not overwhelmed.

If scaling rapidly from zero is essential, an asynchronous architecture can return accepted/job IDs, enqueue work, and process it once workers spin up. Clients poll status instead of holding open connections while workers initialize.

## 15. Load Shedding and Graceful Degradation

When demand exceeds maximum capacity or dependencies cannot keep up, the system needs mechanisms to protect critical paths.

- Rate limit per tenant/client to distribute capacity fairly.
- Reject non-critical or expensive requests early.
- Prioritize critical transactions over reporting/analytics.
- Cache read-only paths or serve stale responses where business rules allow.
- Queue deferrable work for later processing.
- Toggle off secondary features via feature flags when needed.
- Apply circuit breakers and timeouts so requests do not hang indefinitely on dependencies.

Load shedding is not a failure of autoscaling; it is a guardrail protecting the system when physical limits, quotas, or downstream constraints prevent scaling further.

## 16. Observing Scaling Lag and Policy Effectiveness

Measure from the moment a metric crosses its threshold until capacity is actually serving traffic.

| Metric | Meaning |
|---|---|
| Desired vs current replicas | How many the autoscaler wants vs how many exist |
| Pending pods/tasks | Demand awaiting placement |
| Provisioning duration | Time for the cloud to allocate compute |
| Startup duration | Time for the process to start |
| Readiness duration | Time until ready to accept traffic |
| Scale-out lag p50/p95/p99 | Actual end-to-end scaling delay |
| CPU/memory/request utilization | Resource consumption level |
| Queue depth and oldest age | Backlog and work delay |
| Latency/error/timeout | User experience during scaling |
| Scale-in churn | Frequency of creating/destroying capacity |
| Downstream saturation | DB connections, cache, API quotas |
| Cost per served request/job | Cost per unit of genuinely served capacity |

### 16.1. Questions Dashboards Should Answer

1. Which metric triggered scaling?
2. How long did it take from trigger to updated desired capacity?
3. When was new compute provisioned?
4. When did instances/pods become ready?
5. When did the load balancer begin routing traffic to them?
6. During the wait, how did latency and queue age change?
7. After scaling out, did the bottleneck shift to the database or a dependency?
8. Did scale-in cause request resets, queue redeliveries, or churn?

### 16.2. Alerts Based on SLOs and Saturation

Useful alerts include:

- Latency/error budget burn rising while current capacity trails desired capacity.
- Pending pods/tasks exceeding duration thresholds.
- Oldest queue message age approaching SLA.
- Scaling lag p95 exceeding established baselines.
- Maximum replicas or node quota reached while demand keeps climbing.
- Database connection/CPU/lock saturation during app scale-out.
- High warm/minimum capacity running at persistently low utilization.

## 17. Case Study: Booking API During a Promotional Campaign

**Context:** A booking API normally receives 500 requests/second, ramping to 3,000 requests/second within minutes when a campaign launches. One replica safely serves 200 requests/second at target latency. Scale-out from metric trigger to readiness has a p95 of 75 seconds. The database supports at most 800 application connections. Target API p95 is under 300 ms with zero double-bookings.

### 17.1. Baseline Analysis

At 65% target utilization, each replica should handle at most:

\[
200 \times 0.65 = 130 \text{ requests/second}
\]

Replicas needed to serve 500 requests/second:

\[
N_{base} = \left\lceil \frac{500}{130} \right\rceil = 4
\]

This is only the theoretical throughput baseline. You must add fault tolerance, zone distribution, and headroom for the 75-second scaling lag. If most of the peak must be served immediately at launch, you need scheduled pre-scaling or buffering rather than scaling solely on CPU after the campaign starts.

### 17.2. Database Connection Analysis

If each replica opens up to 30 DB connections across 24 replicas, maximum connections hit:

\[
24 \times 30 = 720
\]

This sits dangerously close to the 800 limit, before accounting for maintenance, migration jobs, and other services. Smaller pools, a proxy/pooler, or strict connection quotas are needed, validated by peak load testing.

### 17.3. Proposed Policy for Testing

| Component | Initial Proposal | Verification Method |
|---|---|---|
| API minimum replicas | Maintain baseline for steady load and failure domains | Load tests, zone failure tests |
| Scheduled pre-scale | Scale up before promotional start times | Compare cost vs latency against reactive-only |
| Reactive scale-out | Use request concurrency and utilization, not CPU alone | Short burst and ramp-up tests |
| Scale-in | Lower threshold, longer window, request draining | Oscillation load tests around thresholds |
| DB pool | Cap total connections across all replicas | Verify 800-connection ceiling and headroom |
| Admission control | Rate limit per request/tenant at maximum capacity | Ensure no invalid bookings are confirmed |
| Booking writes | Conditional updates/transactions protecting availability | Concurrent booking tests |

Parameters must be calibrated through testing; this table is an initial design proposal, not a production-ready config.

### 17.4. Acceptance Criteria

- Measured p50/p95/p99 scaling lag from metric trigger to usable capacity.
- Campaign ramp-up does not breach p95 latency SLO beyond the allowed error budget.
- Database connections stay within allocated capacity.
- Scale-in never drops in-flight requests or loses messages.
- Maximum capacity and load shedding behave deterministically.
- Zero double-bookings occur for identical inventory under concurrency tests.
- Baseline/pre-scale cost is weighed against incident and latency-degradation costs.

## 18. Testing Autoscaling

Do not test solely by artificially spiking CPU. Simulate realistic load shapes and measure the full lifecycle.

| Test | Scenario | What to Verify |
|---|---|---|
| Ramp-up | Steady traffic increase | Are thresholds and lag fast enough? |
| Spike | Steep jump within seconds | Do baseline/buffers hold up? |
| Sustained peak | Prolonged high load | Do maximum bounds and dependencies have enough capacity? |
| Oscillation | Load bouncing around thresholds | Do stabilization/hysteresis prevent churn? |
| Sudden drop | Rapid traffic decline | Does scale-in drain safely? |
| Node/zone failure | Loss of one failure domain | Do minimum/headroom hold up? |
| Cold start | Scaling from zero or low minimum | Do first requests meet SLA? |
| Dependency throttle | DB/API returning 429/timeouts | Is scaling capped and backpressure applied? |
| Quota exhaustion | Cloud quota or maximum ceiling hit | Are alerts, degradation, and recovery clear? |

In every test, record traffic, metric signals, desired/current capacity, pod/node state, readiness, latency, errors, queue age, downstream saturation, and cost.

## 19. Common Mistakes

| Mistake | Consequence | Improvement |
|---|---|---|
| Assuming autoscaling adds capacity instantly | Bursts exceed capacity before instances are ready | Measure scaling lag and keep headroom |
| Setting minimum too low | Cold starts and latency spikes | Size baseline for steady load, failures, and warm-up |
| Scaling out on CPU alone | Misses backlog/I/O or overloads DB | Combine metrics tied to actual bottlenecks |
| Same threshold for scale-in and scale-out | Continuous oscillation | Use hysteresis and stabilization windows |
| Cooldown too long | Fails to scale in time for the next wave | Separate fast scale-out from cautious scale-in |
| Checking only Running state | Capacity is not ready or receiving traffic | Measure readiness and routing delays |
| HPA scales pods without node provisioning | Pending pods with no real compute | Coordinate pod/node autoscaling and warm node capacity |
| Scaling apps unboundedly | DB/partner APIs overload | Max capacity, pool limits, backpressure, and admission control |
| Skipping drain before scale-in | Interrupted requests/messages | Graceful shutdown and idempotency |
| Predictive scaling with no reactive fallback | Forecast errors cause under- or over-provisioning | Pair scheduled/predictive scaling with reactive guardrails |
| Never testing peaks and failures | Policy only works under normal traffic | Run load, spike, oscillation, and zone failure tests |

## 20. Scaling Policy Review Checklist

### Measurement and Capacity

- [ ] Measured p50/p95/p99 scaling lag from trigger to usable capacity.
- [ ] Separated metric delay, decision, provisioning, startup, readiness, and routing.
- [ ] Baseline/minimum based on safe throughput, target utilization, and failure domains.
- [ ] Maximum bounded by compute, cloud quotas, and downstream capacity.
- [ ] Headroom suffices to absorb demand during scaling lag, or buffers/load shedding exist.

### Policy

- [ ] Scaling metrics reflect real bottlenecks.
- [ ] Scale-out thresholds and aggregation windows grounded in load tests/SLOs.
- [ ] Scale-in threshold is lower and guarded by a stabilization window.
- [ ] Cooldowns do not block necessary scale-out.
- [ ] Warm pools/pre-scaling/provisioned capacity evaluated for cost vs latency.
- [ ] Scale-in drains/gracefully shuts down and protects in-flight work.

### Dependencies and Operations

- [ ] Database connections, caches, queues, and external APIs have concurrency guardrails.
- [ ] Dashboards expose desired/current/ready capacity, lag, queue age, and SLOs.
- [ ] Alerts configured for pending pods, max capacity, quotas, downstream saturation, and scale-in churn.
- [ ] Load tests cover spikes, ramp-ups, sustained load, oscillation, cold starts, and failures.
- [ ] Runbooks exist for autoscalers failing to scale, over-scaling, or hitting maximums.
- [ ] Baseline/warm capacity cost and cost per served request/job are tracked.

## 21. Hands-On Exercise

**Context:** A booking processing API has a baseline load of 300 requests/second and typically jumps to 2,000 requests/second within the first 30 seconds of a campaign. One instance safely serves 150 requests/second at target p95; p95 time from metric trigger to readiness is 60 seconds. Each instance can open 20 DB connections; the database tolerates at most 500 connections across the entire application. Currently, the system scales out when CPU exceeds 75% and scales in when CPU drops below 75%.

Redesign the policy:

1. Calculate minimum instances from baseline load and your chosen target utilization.
2. Calculate capacity needed for peak load plus spare instances to survive losing one instance.
3. Analyze the capacity deficit during the 60-second scaling lag under rapid ramp-up.
4. Propose baseline, scheduled pre-scaling, warm pool, or queue buffering strategies.
5. Select metrics beyond CPU and distinct scale-out/scale-in thresholds.
6. Design stabilization windows, cooldowns, and graceful scale-in.
7. Check connection amplification against the 500 DB connection cap.
8. Define behavior when maximum capacity hits its ceiling.
9. Design load tests for ramp-up, spike, oscillation, and sudden drop.
10. Specify dashboards/alerts and acceptance criteria for p95 latency, errors, ready capacity, and cost.

**Self-Check Hint:** Do not size instances only for peak while ignoring the 60 seconds without new capacity. Do not allow each instance to open unbounded connections. Scale-in must never drop requests. If maintaining full baseline for peak is impractical, define the buffers, admission control, or graceful degradation acceptable to the product.

## 22. Key Takeaways

Scaling lag is the gap between recognizing the need for more capacity and when new capacity actually serves traffic. Minimum capacity and headroom help the system survive that wait; warm pools, scheduled/predictive scaling, and provisioned capacity cut reaction time at the cost of holding standby resources.

Stabilization windows, cooldowns, and hysteresis prevent autoscaling from oscillating; scale-in requires draining requests and protecting in-flight work. Policies must rely on metrics reflecting actual bottlenecks, downstream limits, SLOs, and testing across real traffic shapes. A well-scaled system does not just spin up replicas quickly—it keeps databases, queues, and dependencies within safe limits while providing clear load shedding once maximum capacity is reached.
