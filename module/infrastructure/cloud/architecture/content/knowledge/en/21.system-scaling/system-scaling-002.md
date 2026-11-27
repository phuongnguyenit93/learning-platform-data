# Choosing Autoscaling Signals by Traffic, Latency, and Queue Depth

## 1. Autoscaling Must React to Demand Before Experience Degrades

Autoscaling is the mechanism that automatically adjusts compute capacity to match demand. For cloud applications, demand can shift by time of day, marketing campaigns, traffic spikes, background processing backlogs, or incidents in a dependency. With fixed capacity, a system wastes resources during low load and runs short of resources when load surges.

The hardest part is not adding machines or replicas, but **choosing the right signal to know when to scale, how much to scale, and when to scale in**. High CPU can indicate compute shortage, but it can also stem from a buggy query or an infinite loop. Low CPU does not mean the system is healthy: the API may be waiting on the database, the thread pool may be exhausted, queues may be growing rapidly, and users may be waiting a long time.

Three groups of signals are commonly useful:

- **Traffic/demand:** request rate, event rate, connection count, invocation count, or incoming task rate.
- **Latency and service quality (latency/SLO):** p50/p95/p99 latency, timeouts, error rate, pool wait time.
- **Queue depth and age:** number of pending jobs and how long the oldest job has been waiting in the queue.

Each signal looks at a different slice of demand. Request rate reflects incoming work; latency shows what users or consuming systems are experiencing; queue metrics reflect unfinished work and how fast a backlog is accumulating. Signal selection must account for workload type, SLOs, per-replica processing capacity, downstream limits, and capacity startup time.

In the **CLOUD_ARCHITECTURE** module, autoscaling is a decision spanning scalability, performance, reliability, cost, and operations. A sound design does not merely add compute when a metric crosses a threshold; it models demand, measures processing capacity, prevents oscillation, protects dependencies, and tests under realistic load using Well-Architected thinking.

After this lesson, you will be able to:

- Distinguish between demand, saturation, latency, and backlog signals.
- Choose appropriate metrics for synchronous APIs, asynchronous workers, and scheduled workloads.
- Estimate capacity from request rate, concurrency, queue arrival/processing rate, and target utilization.
- Design target tracking, step scaling, scheduled scaling, and predictive scaling.
- Configure scale-out/scale-in, cooldown, stabilization, and minimum/maximum capacity.
- Recognize when scaling compute will not resolve bottlenecks in databases, caches, networks, or quotas.
- Evaluate cost, SLOs, fairness, and autoscaling behavior when metrics fail.

## 2. Demand and Processing Capacity Model

Autoscaling can be viewed as a control loop:

1. Collect metrics describing incoming work and processing state.
2. Compare against capacity/SLO targets.
3. Calculate the number of instances, Pods, tasks, or workers to add or remove.
4. Provision or terminate compute.
5. Re-measure results and adjust.

~~~mermaid
flowchart LR
    Demand["Traffic / Events / Queue"] --> Service["Application / Worker"]
    Service --> Metrics["Metrics: RPS, latency, queue, CPU"]
    Metrics --> Policy["Autoscaling policy"]
    Policy --> Capacity["Desired capacity"]
    Capacity --> Runtime["Pods / Tasks / VM instances"]
    Runtime --> Service
    Service --> SLO["SLO: latency, errors, throughput"]
    SLO --> Metrics
~~~

### 2.1. Demand Is Not Equal to Utilization

| Group | Example Signals | Question Answered |
| --- | --- | --- |
| Demand | Requests/s, messages/s, active sessions | How much work is arriving? |
| Utilization | CPU, memory, worker slots, connection pool use | How busy are current resources? |
| Saturation | Thread pool queue, connection waiters, run queue, disk queue | Is work waiting because resources are full? |
| Latency | p95/p99 request duration, queue age, DB wait | How slowly is the system serving? |
| Quality | Error rate, timeout, throttling, rejected requests | Is load breaking user experience or SLOs? |
| Backlog | Queue depth, oldest message age, pending jobs | How much work remains unfinished? |

Utilization is usually a good signal when a workload consumes resources fairly consistently with work volume. For I/O-bound workloads, CPU may stay low while threads wait on the database or network. For queue workers, queue age often reflects business demand more directly than CPU.

### 2.2. Determining the Capacity of One Replica

Before picking metrics, measure how much work one instance or Pod can serve while still meeting SLOs.

For example, an API instance maintains p95 under 200 ms while stably handling 120 requests/second under the tested workload. If the system needs 600 requests/second and wants headroom, do not assume 5 instances are enough. You must factor in target utilization, bursts, request distribution, cache hit ratio, downstream capacity, and instance failures.

Capacity must be measured under production-like conditions: identical CPU/memory limits, network, dependencies, request types, and concurrency levels. A simple benchmark on a lightweight endpoint does not represent the whole application.

## 3. Request Rate and Incoming Traffic Signals

Request rate is the number of incoming requests per unit of time, typically requests per second (RPS), requests per minute, or event rate. It is a direct demand signal and is usually effective for stateless APIs, gateways, web frontends, and services with relatively predictable per-request processing cost.

### 3.1. When to Scale on Request Rate

Suitable when:

- Each request has a relatively stable processing cost.
- Reliable request rate metrics are available from a gateway, load balancer, or application.
- Sustainable capacity per replica is known.
- Replica count scales reasonably linearly with throughput within the operating range.

For instance, an image metadata API handles an average of 100 requests/second per Pod within approved latency bounds. When traffic rises to 800 requests/second, the autoscaler can compute desired replicas from target capacity.

### 3.2. Capacity Formula Based on Request Rate

Let:

- R be the expected total request rate.
- C be the sustainable throughput per replica while meeting SLOs.
- U be the target utilization, between 0 and 1.
- N be the required number of replicas.

Estimate:

**N >= ceil(R / (C × U)).**

For example, R = 800 requests/s, each replica serves C = 100 requests/s within SLO, and target U = 0.7:

**N >= ceil(800 / 70) = 12 replicas.**

The result 12 is initial sizing; add headroom or spare capacity for rollouts, node/AZ loss, and load fluctuations. U should not be set too high if traffic bursts are large or scale-out takes a long time.

### 3.3. Beware of Requests With Varying Costs

A cache read request can be very cheap, while a report-generation request or multi-service call can be hundreds of times heavier. Aggregate RPS can hide shifts in traffic mix.

You can improve accuracy by:

- Tracking RPS per endpoint, operation class, or workload queue.
- Using weighted request units when a reliable cost model exists.
- Splitting heavy workloads into separate worker pools to scale independently.
- Using concurrency, latency, and saturation alongside RPS to confirm.

Do not add instances just because a lightweight endpoint has high RPS if the real bottleneck lies in a heavy operation.

### 3.4. Measure Traffic at the Right Point

Load balancer metrics may count incoming requests including those rejected or failing before reaching the app. Application metrics may miss requests dropped by gateway throttling. Distinguish between offered load, admitted load, successful throughput, and completed throughput.

If an app returns 429 when overloaded, completed RPS can drop while offered RPS climbs. Scaling solely on successful RPS can backfire and worsen the outage. Capture demand before admission control alongside error and throttle metrics.

## 4. Concurrency and In-Flight Work Signals

Concurrency is the number of requests, invocations, or jobs actively being processed at the same time. It is useful when work holds resources over a duration and concurrent tasks correlate directly with threads, connections, or worker slots.

### 4.1. Relationship Between RPS, Concurrency, and Processing Time

By Little's Law in a stable system:

**L = λ × W**

Where:

- L is the average number of requests inside the system.
- λ is the average arrival/completion rate.
- W is the average time a request spends in the system.

For example, 200 requests/s with an average processing time of 0.25 seconds corresponds to about 50 concurrent requests. If processing time increases to 1 second while RPS stays constant, average concurrency rises to around 200.

This is a steady-state average relationship; do not use it to infer p99 or precisely describe short bursts. When a system is unstable and backlogs grow continuously, equilibrium assumptions no longer hold.

### 4.2. When Is Concurrency a Good Signal?

- Serverless functions with concurrent execution limits.
- API servers with bounded in-flight requests or worker threads.
- Long-running requests, WebSockets, or streaming sessions that hold resources for a long time.
- Workers with a fixed number of parallel job slots.

A concurrency cap can also act as a safeguard. When downstream only tolerates 300 concurrent operations, do not autoscale the frontend to generate 2,000 concurrent requests to the database.

### 4.3. Risks of Relying Solely on Concurrency

Concurrency can spike because requests are hanging. If you scale purely on active requests, the system may keep adding instances while every request waits on an outaged dependency. Total connections or requests to that dependency climb, widening the incident.

Combine concurrency with latency, timeouts, pool wait times, and dependency health. Cap concurrency per replica and service-wide, and apply circuit breakers or admission control when downstream is unhealthy.

## 5. Latency and SLO Signals

Latency describes the time to complete an operation from a caller's perspective or across a defined span. For autoscaling, p95/p99 are usually more useful than the average because they capture the experience of slower requests.

### 5.1. Why p95/p99 Matter

Suppose 95% of requests finish in 100 ms, while 5% take 3 seconds. The average may still look acceptable, even though a subset of users suffers poor experience and rising timeouts. SLOs are usually defined as the percentage of requests completing below a threshold, making tail latency an essential signal.

Rising latency can be caused by:

- Compute saturation or CPU throttling.
- Exhausted thread/connection pools.
- Database locks, slow queries, or storage latency.
- Network congestion, DNS, or external dependencies.
- Cache misses, garbage collection, or cold starts.
- Queueing in gateways, service meshes, or load balancers.

Latency is a service-quality signal, not always an indicator that more compute is needed. Break down request duration across queue wait, application processing, and dependency spans.

### 5.2. Latency-Based Scaling Has Reaction Lag

Latency typically degrades after the system has already started running short of capacity. If an autoscaler waits until p99 breaches the SLO before scaling, users are already impacted before new replicas become ready.

Latency can be used to:

- Trigger scale-out earlier than an SLO threshold, with hysteresis.
- Pair with request rate to predict additional capacity needed.
- Verify that target tracking has returned utilization to the desired range.
- Adjust concurrency limits when a dependency slows down.

Do not scale in just because latency is briefly low; latency may dip due to a temporary drop in traffic or higher cache hit rates.

### 5.3. Latency Metrics Must Be Properly Scoped

Measure latency for specific operations and populations. A service with a fast health-check endpoint but a slow business API cannot be considered healthy. Aggregating across multiple endpoints can mask critical routes. In multi-tenant systems, per-tenant or per-workload-class latency helps uncover noisy neighbors.

When using percentiles for autoscaling, verify the metric window and sample count. At low traffic, p99 can fluctuate wildly due to small sample sizes; combine it with minimum sample counts, traffic signals, or saturation metrics.

## 6. Queue Depth and Queue Age for Asynchronous Workloads

Workers handling messages, video, email, reports, or batches usually do not need to return an immediate synchronous response to the sender. Queues absorb bursts and decouple producer speed from consumer speed. In this model, queue depth and queue age are primary demand signals.

### 6.1. Queue Depth

Queue depth is the number of pending messages/jobs not yet processed or acknowledged according to the queue's semantics. If message count keeps rising, arrival rate exceeds completion rate.

Advantages:

- Reflects backlog directly.
- Useful for workers with varying processing times where job count is meaningful.
- Easy to use as a metric for KEDA, queue-based autoscalers, or custom policies.

Limitations:

- 1,000 lightweight jobs differ from 1,000 heavy jobs.
- One queue may mix multiple priorities or tenants.
- Some queue metrics include in-flight messages; understand the exact definition.
- Batch sizes and retries can cause depth to fluctuate without reflecting true throughput.

### 6.2. Queue Age / Oldest Message Age

Queue age is how long the oldest message or a message has waited in the queue. This is often closer to business experience than queue depth. A large backlog may be fine if workers drain it rapidly; a queue with only a few dozen jobs can still breach SLA if one job waits too long.

For example, notification emails must start sending within 2 minutes; if oldest age exceeds 90 seconds, the system is close to breaching SLA even if queue depth is small. For video transcoding, queue age and completion time per resolution profile reflect service quality better than CPU.

### 6.3. Arrival Rate and Processing Rate

Let:

- λ be the job arrival rate to the queue (jobs/s).
- μ be the completion rate of the entire worker pool (jobs/s).
- Q be the queue depth.

If λ > μ persists, backlog grows. If λ < μ, the queue drains. A simple model:

**Backlog change per second ≈ λ − μ.**

For example, a queue receives 150 jobs/s while the worker pool processes 100 jobs/s; backlog grows by roughly 50 jobs per second while these rates hold. Scale-out must raise μ enough to exceed λ and drain the backlog within the SLA window.

When jobs vary in duration or weight, measure processing throughput by job type or estimated work units rather than raw job count.

### 6.4. Calculating Worker Count From Queue Target

If one worker stably processes r jobs/s, then n workers yield μ ≈ n × r under linear scaling. To drain a backlog Q within deadline T, the worker pool needs throughput:

**μ_target >= λ + Q / T.**

For example, a queue holds 12,000 jobs, continues receiving 40 jobs/s, and must clear the backlog in 120 seconds:

**μ_target >= 40 + 12,000 / 120 = 140 jobs/s.**

If one worker processes 10 jobs/s, the minimum estimate is 14 workers. Add headroom, and account for retries, downstream limits, and worker startup time. This calculation assumes homogeneous jobs and near-linear processing rates.

## 7. Choosing Signals by Workload Type

| Workload | Primary Signal | Supporting Signals | Rationale |
| --- | --- | --- | --- |
| Stateless HTTP API | RPS or concurrent requests | p95/p99 latency, CPU, error/throttle | Direct demand and SLOs reflect user experience |
| Variable-cost API | Weighted RPS or concurrency | Endpoint latency, CPU, downstream wait | Total RPS hides per-request cost differences |
| Queue worker | Queue age or queue depth | Arrival/processing rate, active jobs, CPU | Backlog represents unfinished demand |
| Serverless event consumer | Queue/event backlog and concurrent executions | Throttling, duration, downstream errors | Must cap concurrency to protect dependencies |
| Scheduled batch | Scheduled capacity or batch task queue | Job duration, CPU/memory, deadline | Demand is known ahead of time and jobs have deadlines |
| Streaming processor | Lag/age per partition or stream shard | Processing rate, CPU, partition skew | Lag indicates data falling behind |
| Stateful database | Do not scale purely on CPU/RPS | Connections, IOPS, locks, storage, replication lag | Scaling requires data semantics and engine limits |
| WebSocket/session service | Active sessions and resources/session | Network throughput, memory, message rate | Sessions hold resources longer than short requests |

No single metric should be forced onto every service. A system can scale APIs by RPS, workers by oldest queue age, and stream processors by consumer lag; databases are scaled by capacity/storage/IO with dedicated procedures.

## 8. Calculating Desired Capacity and Target Utilization

An autoscaler typically needs a target: requests per replica, CPU utilization, messages per worker, or a target latency/queue age.

### 8.1. General Utilization Formula

For a utilization metric with a roughly linear relationship, you can estimate:

**Desired replicas = ceil(current replicas × current metric / target metric).**

For example, with 4 Pods currently running at 80% average CPU and a 60% target:

**Desired = ceil(4 × 80 / 60) = 6 Pods.**

This is the conceptual formula commonly used in target tracking; actual controllers also factor in tolerance, missing metrics, readiness, min/max bounds, and stabilization windows.

### 8.2. Target Should Never Be 100%

Setting target utilization to 100% leaves zero headroom for bursts, GC, rollouts, or node failures. Targets usually need to sit well below saturation to leave time for scale-out. The right value should come from load tests and capacity provisioning speed.

Headroom is not waste: it is part of the availability and performance budget. However, excessive headroom inflates cost. Compare cost per request and latency curves as you tune the target.

### 8.3. Combining Multiple Metrics

When multiple metrics are configured, the autoscaler's evaluation semantics matter. A policy may pick the highest desired capacity across metrics so one low metric does not pull down another; other systems use composite metrics or custom controllers. Always read the behavior of your deployment tool.

Example:

- RPS recommends 12 Pods.
- CPU recommends 9 Pods.
- Queue age recommends 15 Pods.

If the policy takes the maximum, desired is 15 Pods to satisfy the most demanding signal. However, if queue age is rising because of a database outage, adding workers can worsen pressure. Use health gates or downstream-aware concurrency caps.

## 9. Autoscaling Strategies

### 9.1. Target Tracking

Target tracking tries to keep a metric near a target value, such as 60% CPU, 100 requests/second per instance, or a set number of messages per worker. It is convenient for workloads with a clear capacity-to-metric relationship.

Its strength is self-adjusting capacity against a metric; its limitation is that the metric must accurately reflect demand/capacity and the controller needs time to converge. CPU target tracking alone does not resolve queue backlogs or downstream bottlenecks.

### 9.2. Step Scaling

Step scaling adjusts capacity in discrete steps as a metric crosses threshold bands. Example:

| Queue age signal | Worker change |
| --- | --- |
| Under 20 seconds | No scale-out |
| 20–45 seconds | Add 2 workers |
| 45–90 seconds | Add 5 workers |
| Over 90 seconds | Add 10 workers and inspect downstream |

These tiers are illustrative only. If workers take a long time to start, larger steps help catch bursts faster; if downstream has hard limits, adding 10 workers at once can overload it.

### 9.3. Scheduled Scaling

Scheduled scaling adjusts capacity ahead of known demand shifts, such as daily traffic peaks at 9:00 AM or midnight batch runs. It helps pre-warm capacity before an event starts rather than reacting after metrics spike.

Scheduled scaling should not completely replace metric-based scaling because real schedules shift. Combine scheduled baselines with reactive scaling and min/max bounds.

### 9.4. Predictive Scaling

Predictive scaling uses historical data to forecast demand and provision capacity ahead of expected peaks. It fits workloads with strong periodicity and sufficient history. It can fail during sudden behavior shifts, new campaigns, or unexpected incidents.

Keep reactive scaling as a guardrail for forecast errors; monitor forecast accuracy and the cost of early provisioning.

### 9.5. Event-Driven Scaling

For queues or event streams, an autoscaler can read queue depth, oldest message age, consumer lag, or pending events. Tools like KEDA provide event-source scalers to adjust Kubernetes workload replicas; verify the exact metric and scaling semantics of each scaler.

Scale-to-zero saves cost when idle, but cold starts increase processing time for the first message. For strict SLOs, maintaining a minimum number of warm workers may make more sense.

## 10. Scale-Out, Scale-In, Cooldown, and Stabilization

Autoscaling is a control loop with lag. Metrics take time to collect, controllers take time to decide, clouds take time to provision compute, and applications take time to start, warm caches, register with service discovery, and become Ready.

### 10.1. Scale Out Faster Than Scale In

Scale-out usually needs to react quickly to protect SLOs. Scale-in should be more conservative to avoid removing capacity during brief dips in load.

- Add capacity when demand exceeds target over a short window or on reliable burst forecasts.
- Hold capacity after scale-out long enough for metrics to stabilize.
- Reduce capacity in small steps when metrics stay consistently low over a longer window.
- Never scale in below the minimum capacity required for availability, warm caches, or baseline throughput.

If scale-out and scale-in share the same threshold, metric oscillation around that line causes continuous creation and termination of instances—known as flapping.

### 10.2. Cooldown and Stabilization Windows

Cooldown is the waiting period after a scaling action before taking another action or re-evaluating, depending on the autoscaler's semantics. A stabilization window inspects recent metric/recommendation history to avoid reacting to short spikes or scaling in prematurely.

Do not pick durations arbitrarily. Measure VM/Pod/task provisioning time, health check and startup probe durations, cache/connection pool warm-up time, metric scrape/aggregation intervals, and the time needed to observe the effect of the previous scaling action.

If a worker takes 90 seconds to boot while the policy re-evaluates every 10 seconds and keeps adding capacity aggressively, the system can spawn excess workers before any of them start draining the backlog. Conversely, an overly long cooldown makes the system sluggish when traffic genuinely surges.

### 10.3. Hysteresis

Hysteresis uses separate thresholds for scale-out and scale-in. Example:

| Utilization metric | Action |
| --- | --- |
| Above 70% continuously for 2 minutes | Scale-out |
| Between 40–70% | Hold capacity |
| Below 40% continuously for 10 minutes | Allow scale-in |

These thresholds are illustrative. Hysteresis creates a deadband between actions, preventing flapping when load fluctuates around a single point.

## 11. Provisioning Delay and Capacity Buffers

Autoscaling reacts after demand is observed; new capacity does not appear instantaneously. If the time from metric detection to a Ready replica exceeds how long the system can tolerate under-capacity, reactive scaling alone is insufficient.

### 11.1. Components of Scaling Delay

**Scaling delay = detection + decision + provisioning + startup + readiness + warm-up.**

Example:

| Step | Assumed Duration |
| --- | ---: |
| Metric window and scrape | 30 seconds |
| Controller decision | 10 seconds |
| VM/Pod provisioning | 45 seconds |
| Application startup | 25 seconds |
| Readiness and warm-up | 20 seconds |
| Approximate total | 130 seconds |

During those 130 seconds, the system must have sufficient headroom, queue buffers, or admission control to keep user experience acceptable.

### 11.2. Minimum Capacity and Headroom

Minimum capacity establishes a baseline for steady load and absorbs part of the scaling delay. Headroom is unused capacity at any given moment reserved for bursts, rollouts, or instance losses.

Do not calculate minimum replicas solely from average traffic. Account for off-peak load, bursts before the autoscaler reacts, potential node/zone losses, rolling deployments requiring extra capacity, and whether a warm pool is viable.

### 11.3. Warm Pools and Pre-Warming

For VMs or slow-starting workloads, a warm pool keeps pre-initialized instances ready without serving live traffic yet. Scheduled scaling can raise capacity before campaigns; image caching, pre-pulled container images, and connection warm-up also shorten time-to-ready.

Warm capacity must be accounted for in cost. It still needs health checks, patching, rotation, and configuration verification so instances do not grow stale or error-prone.

## 12. Protecting Downstream: Autoscaling Can Make Incidents Worse

Scaling compute does not add capacity to every dependency. If each API replica opens 20 DB connections and the autoscaler scales from 10 to 100 replicas, potential connections jump from 200 to 2,000. If the database only safely handles 500 connections, scaling out the API turns a compute shortage into a database outage.

### 12.1. End-to-End Capacity Budget

Before increasing replicas, determine the capacity of database connections/query throughput/transaction locks, cache connections/command rate/memory, message broker partitions/consumer quotas, third-party API rate limits/concurrency, NAT gateway/IP/network bandwidth, and shared storage IOPS/throughput.

### 12.2. Downstream-Aware Scaling

- Scale out APIs on RPS while capping request concurrency per replica.
- Scale out workers on queue age while capping total consumer concurrency.
- Pause or throttle workers when DB connections or latency exceed protective thresholds.
- Use bulkheads to isolate connection pools by workload class.
- Use circuit breakers, rate limiters, or queues to absorb demand when a dependency fails.

Do not configure a scaling policy to tear down compute just because the database is failing if doing so worsens backlogs and SLAs. Choose controlled graceful degradation: throttle, defer, reject with informative errors, or serve read-only/cached responses depending on business rules.

### 12.3. Autoscaling and Databases

Databases rarely scale like stateless applications. Adding read replicas can help read load; increasing storage or IOPS can lift storage limits; vertical scaling changes compute capacity; sharding changes the data architecture. Each option has its own limits, lead times, and consistency trade-offs.

Do not rely on database CPU as the sole signal. Monitor active connections, pool waits, lock waits, IOPS, storage latency, replication lag, cache hit rates, and query p95/p99. Scaling out application replicas while the database is saturated typically increases error rates.

## 13. Queue-Based Scaling and Backpressure

Queue workers allow the system to accept work faster than immediate processing capacity. However, queues do not make backlogs vanish. If arrival rate exceeds processing rate for a sustained period, queue age climbs and business SLAs can expire.

### 13.1. Producer, Queue, and Consumer Relationship

~~~mermaid
flowchart LR
    Producer["Producers"] --> Q[("Queue / Stream")]
    Q --> W1["Worker 1"]
    Q --> W2["Worker 2"]
    Q --> W3["Worker N"]
    W1 --> Down["Database / External API"]
    W2 --> Down
    W3 --> Down
    Q -. "Depth / age / lag" .-> Scale["Autoscaler"]
    Scale --> W1
~~~

### 13.2. Backpressure

Backpressure regulates the rate at which work is admitted or pulled when downstream cannot process safely. You can reduce consumer concurrency or prefetch counts, pause new batches when workers hold many in-flight jobs, throttle producers to match downstream quotas, use priority/deadline queues, and reject or defer tasks that can no longer meet SLAs.

Queue depth can grow because of worker bugs, poison messages, dependency outages, or genuine throughput shortages. Before scaling out, check error/retry rates, dead-letter counts, and downstream saturation.

### 13.3. Visibility Timeout, Ack, and Retries

In queues with visibility timeouts, consumers must finish and ack within an appropriate window or extend the lease according to service semantics. If the timeout is too short, messages are redelivered while workers are still processing them, causing duplicate execution. If it is too long, a crashed worker delays redelivery significantly.

Autoscaling increases consumer count, but does not replace idempotency. Operations writing to DBs, sending emails, or charging payments must carry idempotency keys/operation IDs so retries do not duplicate side effects.

### 13.4. Queue Age by SLO

| Work Type | Sample SLO | Primary Signal |
| --- | --- | --- |
| Confirmation email | Start sending within 60 seconds | Oldest message age |
| Thumbnail processing | Complete within 3 minutes | Age + job completion duration |
| Video encoding | Complete within 20 minutes per profile | Age by job type + processing rate |
| Reconciliation batch | Complete before 06:00 | Remaining work + deadline |

Queue age should be segmented by priority or queue if jobs have different SLAs. A single shared queue lets low-priority jobs starve critical jobs without fairness policies.

## 14. Event Streams and Consumer-Lag Autoscaling

In Kafka or partitioned streams, a consumer group's traditional parallelism is bounded by partition count. Consumer lag is the gap between the latest offset and the offset processed/committed by the consumer, per the platform's metric definition.

### 14.1. Lag Is More Than One Number

Track:

- Lag per partition, not just group totals.
- Age of the oldest unprocessed event.
- Ingress bytes/records and consumer processing rate.
- Partition skew and hot keys.
- Rebalance frequency, processing errors, and downstream latency.

If one hot partition accounts for most of the lag, adding consumers cannot split that single partition within the same consumer group. Address key skew, optimize the consumer, or plan a topology change.

### 14.2. Scaling Limit by Partition Count

With P partitions in a traditional consumer group:

**Maximum active consumers <= P.**

If there are 8 partitions and the autoscaler spins up 20 consumers, at least 12 consumers sit idle with no partition assigned. Excess capacity adds cost without speeding up processing.

Some platforms support cooperative rebalancing, static membership, or other mechanisms to reduce reassignment overhead; none of them remove the fundamental partition parallelism ceiling.

### 14.3. Is Adding Partitions the Way to Scale?

Adding partitions can increase future parallelism, but changing partition counts can alter key mapping and break per-entity ordering. Evaluate the producer partitioner, key distribution, consumer state, retention, and migration plan before increasing partitions.

## 15. Kubernetes: HPA, KEDA, and Node Autoscaling

Kubernetes has multiple scaling layers; distinguish between Pod scaling and node scaling.

### 15.1. Horizontal Pod Autoscaler (HPA)

HPA adjusts replica counts for workloads such as Deployments or StatefulSets based on resource, custom, or external metrics. CPU/memory utilization typically requires resource requests to calculate ratios. Custom metrics can be request rate, active requests, or queue metrics supplied through a metrics adapter.

Example HPA manifest:

~~~yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: checkout-api
  namespace: commerce
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: checkout-api
  minReplicas: 3
  maxReplicas: 30
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
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
        - type: Percent
          value: 20
          periodSeconds: 60
~~~

This is an illustrative manifest, not a universal template. Verify `metrics-server`/custom metrics adapters, requests/limits, readiness probes, Pod startup times, node capacity, and Kubernetes version. `maxReplicas` must also align with cloud quotas and database capacity.

### 15.2. KEDA and Event-Driven Autoscaling

KEDA enables event-driven scaling for Kubernetes workloads via scalers for supported queues, streams, databases, or event sources. KEDA integrates with HPA and supports scale-to-zero depending on the workload.

Before adopting it, verify what queue depth, lag, or rate the scaler metric actually represents; authentication/secrets and metric query permissions; polling intervals, cooldowns, and activation thresholds; whether maximum replicas protect downstream; behavior when the metric source is unreachable; and whether consumer concurrency is bounded by partition/queue quotas.

### 15.3. Cluster/Node Autoscaling

HPA/KEDA can increase Pod counts, but Pods stay Pending if the cluster lacks CPU/RAM or matching nodes. A node autoscaler adds or removes nodes to satisfy scheduling demand. Node provisioning is usually slower than creating Pods on existing nodes; plan headroom, appropriate node pools, and cloud quotas.

Design both layers together:

1. Pod scaling driven by demand and SLOs.
2. Node scaling driven by Pending Pods, resource requests, and node constraints.

If a Pod requests a GPU while the node pool has exhausted GPU quota, autoscaling cannot provision capacity. Monitor quotas, subnet IP availability, instance availability, and provider limits.

## 16. Serverless and Platform-Managed Autoscaling

Serverless platforms automatically scale execution environments or concurrency within configuration and quota bounds. You still must choose concurrency caps, provisioned/warm capacity, event batch sizes, and downstream limits.

### 16.1. Signals to Monitor

- Concurrent executions and throttles.
- Invocation/request rate and duration.
- Queue/event source age, backlog, or iterator/consumer lag.
- Error rate, timeouts, and retry counts.
- Database connections, proxy saturation, and API quotas.

Never assume serverless scales infinitely. Provider quotas, region capacity, concurrency limits, VPC/network attachments, and downstream quotas can all constrain scaling.

### 16.2. Provisioned Concurrency / Warm Capacity

For latency-sensitive APIs or workloads with noticeable cold starts, you can keep a baseline of execution environments warm/provisioned. This cuts startup latency but incurs continuous cost even during low traffic. Base the baseline on traffic forecasts and SLOs, leaving reactive capacity for bursts.

### 16.3. Batch Size and Event Source Mapping

Large batch sizes reduce invocation overhead but increase processing time, memory usage, and retry blast radius. Small batches increase invocations and connection churn. Tune batch size alongside concurrency, visibility timeouts, partial batch failure handling, and idempotency.

## 17. Observing and Controlling Autoscaling

Autoscaling must be observed as a control system, not just by looking at final replica counts.

### 17.1. Minimum Dashboard

| Group | Metrics |
| --- | --- |
| Demand | Offered RPS, admitted RPS, event arrival rate, queue depth |
| Service level | p50/p95/p99 latency, success/error rate, timeouts, throttling |
| Saturation | CPU/memory, thread/connection wait, disk/network, active worker slots |
| Queue/stream | Oldest age, lag per partition, arrival vs completion rate, retry/DLQ |
| Scaling controller | Desired/current replicas, scaling events, decision reasons, stabilization/cooldown |
| Provisioning | Pending pods, launch time, readiness time, node capacity, quota errors |
| Downstream | DB connections/latency, cache saturation, external API rate limits |
| Cost | Instance/Pod hours, cost per request/job, idle capacity, scale churn |

### 17.2. Correlation and Metric Hygiene

Log scaling event timestamps and correlate them with traffic, latency, queue, error, and downstream metrics using aligned time windows. Metrics with excessive label cardinality or missing samples can emit bad signals. Autoscaler metrics require proper aggregation and explicit handling for missing/NaN/stale data.

When a metric source disconnects, never let the controller interpret "no metric" as "zero load" and dangerously scale in. Configure tool-specific fail-safe behaviors.

### 17.3. Scaling Policies Are Code That Needs Review

Version-control min/max bounds, targets, cooldowns, scheduled windows, metric queries, auth, and downstream caps in IaC. Review changes just like capacity architecture changes. Audit who changed max replicas from 30 to 300 or target CPU from 60% to 95%.

## 18. Cost, Fairness, and Resource Limits

Autoscaling optimizes cost when capacity tracks demand, but can produce huge bills from noisy metrics, retry storms, or overly high minimum capacity.

### 18.1. Measuring Cost Efficiency

Useful metrics:

- Cost per successful request or transaction.
- Cost per completed job/video/report.
- Idle capacity ratio and wait time for new capacity.
- Frequency of scaling events and instances launched before becoming Ready.
- Cost of retries, duplicate processing, and queue retention.
- Cost of data transfer, NAT, logging, and downstream usage at scale.

Do not set target utilization overly low just to chase better latency if cost exceeds budget. Compare cost-latency curves and pick a point aligned with SLOs.

### 18.2. Fairness Across Tenants and Workloads

One tenant can burst and monopolize all workers or connections. If you scale purely on aggregate queue depth, a large tenant can starve smaller tenants' workloads.

Mitigations include:

- Separate queues or logical partitions per tenant/priority where needed.
- Per-tenant rate limits and concurrency quotas.
- Weighted fair scheduling or dedicated worker pools for critical workloads.
- Queue age metrics per tenant/priority to detect starvation.
- Concurrency caps on heavy jobs and export/report quotas.

Fairness is a product and operational requirement, not just a CPU problem.

## 19. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Scaling solely on CPU | Misses I/O wait, queue backlog, and latency | Combine demand, latency, saturation, and queue signals |
| Scaling on successful RPS | Rejected traffic lowers metric, triggering scale-in | Measure offered/admitted load and throttling |
| Using only average latency | Bad tail latency is hidden | Track p95/p99 and sample counts |
| Scaling on queue depth ignoring job cost | Heavy and light jobs treated identically | Use queue age, work units, and job classes |
| No max replicas cap | Downstream or cost exceeds limits | Cap against end-to-end capacity budget |
| Cooldown too short | Flapping and constant instance churn | Use hysteresis, stabilization, and measured startup times |
| Scaling in too fast | In-flight requests/jobs interrupted | Graceful shutdown, draining, and scale-in stabilization |
| Scaling consumers past partition count | Idle consumers with no throughput gain | Account for parallelism limits and fix key skew |
| Scaling APIs overloads the DB | Connection storms, query latency, cascade failures | Downstream-aware concurrency caps and pool budgets |
| Ignoring node quota/IP limits | Pods stay Pending despite HPA scaling | Check quotas, subnet IPs, node pools, and headroom |
| Blindly trusting predictive scaling | Under-capacity when traffic patterns shift | Keep reactive guardrails and monitor forecast accuracy |
| Treating missing metrics as zero | Erroneous scale-in during monitoring outages | Safe missing-data policies and telemetry alerts |

## 20. Hands-On Exercise: Choosing Autoscaling Signals for an Ordering Platform

An e-commerce platform has:

- Checkout API handling synchronous requests, requiring p95 under 250 ms.
- Workers sending emails and generating invoices via queues.
- Workers processing product images with varying durations based on image size.
- Consumers reading an event stream with 24 partitions.
- Managed PostgreSQL with an approved connection budget that cannot scale instantaneously.

During a campaign, offered traffic grows 5x in 3 minutes. API CPU only reaches 55%, yet p99 latency spikes; the email queue grows from 500 to 18,000 messages and oldest age hits 110 seconds. Stream consumer lag concentrates on 2 hot partitions. Database connections have reached 85% of their safe budget.

**Exercise Tasks:**

1. Choose scaling signals for the checkout API and explain why 55% CPU does not prove spare capacity remains.
2. Separate offered RPS, admitted RPS, p95/p99, in-flight requests, pool wait, and database latency on a dashboard.
3. Estimate API replica count from per-replica benchmark capacity; pick target utilization and headroom.
4. Choose between queue depth and oldest age for the email worker; calculate worker throughput needed to drain the backlog within the stated SLA.
5. Choose signals for the image worker when job costs vary; propose work units or class-separated queues.
6. Explain why raising consumers from 24 to 40 does not fix hot partitions; propose how to address key skew.
7. Set concurrency caps so PostgreSQL stays within its connection budget; describe backpressure when DB nears saturation.
8. Propose cooldowns, stabilization, min/max replicas, warm capacity, and scale-in behavior.
9. Define behavior when the metric source stops updating or the downstream database fails.
10. Design load tests and chaos tests to prove SLOs, queue age, recovery, and cost.

### Evaluation Notes

A strong design uses multiple workload-specific signals: demand/concurrency paired with p99 and downstream saturation for the API; oldest age/depth and processing rate for the email worker; estimated work units or class-separated queues for the image worker; per-partition lag and bounded parallelism for the stream consumer.

The database sitting at 85% of its connection budget is the critical constraint. Unbounded API/worker scale-out will raise connections and worsen latency. The plan requires concurrency caps, smaller pools, backpressure or task deferral, and fixing the two hot partitions rather than just adding consumers.

## 21. Production Readiness Checklist for Autoscaling

- [ ] Define SLOs, offered load, traffic mix, and sustainable capacity per replica.
- [ ] Select metrics matching true demand: RPS, concurrency, queue depth/age, lag, or work units.
- [ ] Monitor p95/p99 latency, error rate, timeouts, and saturation alongside utilization.
- [ ] Measure provisioning delay from detection to Ready/warm capacity.
- [ ] Calculate target capacity with headroom for bursts, rollouts, and failure domains.
- [ ] Configure min/max replicas, node quotas, IP quotas, and downstream concurrency caps.
- [ ] Enable fast scale-out and conservative scale-in with appropriate hysteresis/stabilization.
- [ ] Calculate queue arrival/processing rates and backlog drain times against SLAs.
- [ ] Implement backpressure, rate limits, priority/fairness, and worker idempotency.
- [ ] For streams, track per-partition lag, hot keys, and consumer parallelism ceilings.
- [ ] Verify metric windows, sample counts, stale/missing data handling, and fail-safe behaviors.
- [ ] Ensure graceful shutdown/draining before scale-in so no requests/jobs are lost.
- [ ] Assess dependency capacity: DB, cache, broker, API quotas, network, storage, and NAT.
- [ ] Version scaling policies in IaC and audit scaling changes.
- [ ] Load test steady state, ramps, spikes, sustained peaks, scale-in, and cold starts.
- [ ] Chaos test metric outages, node failures, downstream slowdowns, and queue retry storms.
- [ ] Track cost per successful request/job and idle capacity.
- [ ] Maintain dashboards, alerts, runbooks, and clear owners for scaling policies.

**Key Takeaway:** Effective autoscaling chooses signals that reflect incoming work and completion capacity, not a single utilization metric. RPS shows incoming demand, concurrency shows work currently holding resources, latency shows user experience, and queue age/depth shows backlog. Combine them by workload type, size capacity from benchmarks, enforce headroom and downstream limits, and govern scale-out/scale-in with cooldowns, stabilization, and backpressure. The ultimate goal is meeting SLOs at a reasonable cost without shifting bottlenecks to databases, brokers, or downstream dependencies.
