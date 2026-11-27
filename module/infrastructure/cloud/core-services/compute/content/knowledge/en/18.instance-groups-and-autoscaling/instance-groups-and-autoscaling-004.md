# Choosing Metrics by CPU, Latency, Queue Depth, or Concurrency

Autoscaling adjusts machine or worker counts based on signals reflecting demand and the system's ability to serve. Choosing an unsuitable metric can cause the machine group to scale too late, oscillate continuously, or pile extra load onto an overloaded dependency. CPU utilization is a common signal, but it does not represent every workload. An API may be constrained by database latency; workers may build a queue backlog despite low CPU; a service holding many connections may exhaust concurrency before CPU hits its threshold.

A good metric ties directly to service objectives, indicates whether adding or removing capacity is needed, is measured reliably, and behaves clearly as instance counts change. This lesson covers how to choose and combine CPU, latency, queue depth, and concurrency for instance groups, VM workers, and cloud compute models.

## 1. What does autoscaling need to measure?

Autoscaling typically controls the desired capacity of a machine group within min/max bounds. The controller collects metrics, compares them against targets or thresholds, and decides whether to scale out or scale in.

A system should monitor three dimensions:

- **Demand:** incoming work volume, such as requests/second, messages/second, sessions, or jobs.
- **Saturation:** resource utilization that can constrain throughput, such as CPU, memory, connection pools, or concurrency.
- **Service quality:** response time, error rate, queue wait time, and SLOs.

Demand metrics show how much work is arriving. Saturation metrics show whether current capacity is nearing its limits. Service quality metrics show how users or downstream systems are impacted. An effective policy usually combines at least one demand or saturation signal with quality guardrails.

### Metrics are not synonymous with autoscaling goals

For example, the goal may be keeping p95 latency below the SLO. CPU is merely one signal to add capacity when CPU-bound. If latency rises because a database is slow, adding web VMs can increase database connections and worsen the outage. Therefore, choose metrics based on bottlenecks that adding compute can actually resolve.

## 2. Commonly used metric groups

| Metric | Reflects | Best suited for | Risk when used alone |
|---|---|---|---|
| CPU utilization | How busy the CPU is | CPU-bound workloads, compute-heavy web/APIs | Poor at detecting I/O wait, queue backlogs, or concurrency limits |
| Memory utilization / working set | RAM consumption | Workloads whose footprint grows with requests or caches | RAM may not drop when load falls; scale-in will not fix memory leaks |
| Request rate | Incoming request demand | APIs/web tiers with relatively uniform per-request cost | Requests vary in complexity; rate alone does not show backend saturation |
| p95/p99 latency | Tail user experience | Synchronous services with latency SLOs | Can rise due to dependencies, network, or errors; often a lagging signal |
| Queue depth / backlog | Unprocessed work | Async workers, batch jobs, event consumers | Message count hides message age and per-message cost |
| Age of oldest message | Wait time of oldest pending job | Queues that must meet deadlines/SLOs | Can react slowly if updated infrequently or skewed by poison messages |
| Concurrency / in-flight requests | Simultaneously processed work units | APIs, proxies, stateful-session servers, workers | Needs normalization against per-instance capacity and runtime limits |
| Active connections | Open connections | Long-lived connection services, WebSockets, DB proxies | Idle connections may consume very little compute |
| Custom work per instance | Capacity-normalized demand | Workloads with variable per-job cost | Requires building custom telemetry and ensuring accuracy |

Do not collect every metric and feed all of them into one policy without clear roles. Every metric should have a justification, owner, unit, reporting interval, and corresponding action.

## 3. CPU utilization: easy to use, not sufficient for all workloads

CPU utilization measures the fraction of time the CPU spends executing work during a sampling interval. For CPU-bound workloads, when CPU remains high while latency or queues also climb, adding instances usually increases aggregate processing power.

### When CPU is an appropriate metric

- Application code performs significant computation per request.
- Workers handle image processing, encryption, compression, or data calculation.
- Per-request CPU cost is relatively consistent.
- Throughput scales nearly linearly with vCPUs or instance count within a verified range.

### When CPU can be misleading

- Applications waiting on databases, networks, or storage: CPU stays low while latency is high.
- A single thread saturates on a multi-core machine: overall CPU looks low even though the app is bottlenecked.
- Containers experiencing CPU throttling from limits: node-level utilization may hide container-level constraints.
- Burstable instances exhausting CPU credits: performance degrades without average metrics reflecting the state accurately.
- GPU-heavy workloads: low CPU does not mean the GPU has spare capacity.

When using CPU, measure at the exact scope being scaled: per-instance or per-container rather than just group totals. Group averages can mask a hot instance while others sit idle.

### Choosing a CPU target

There is no single universal threshold for every application. Pick targets through load testing: step traffic upward while observing CPU, latency, error rate, and throughput; find the region where the app still has headroom for bursts and new instance startup times. Autoscaling targets usually sit below saturation so the group scales out before queues or latency spike sharply.

## 4. Latency: the metric closest to user experience

Latency measures the time to complete a request or task. For synchronous services, p95/p99 is usually more informative than the mean because it captures the slow tail users actually notice.

### Why use percentiles?

Suppose 95% of requests finish in 200 ms while the remaining 5% take 4 seconds. The mean may look acceptable even though a subset of users suffers a terrible experience. p95 indicates the threshold within which 95% of requests complete; p99 is more sensitive to the slow tail, though noisier when sample sizes are small.

### When is latency suitable?

- Backends can increase throughput when instances are added.
- Requests are distributed fairly evenly across the load balancer.
- Latency can be measured at the right scaling boundary, such as backend processing time rather than total time including external DNS/client/network hops.
- Dependencies have sufficient capacity to serve additional requests.

### Limitations of scaling on latency

Latency is often a trailing indicator after the system is already under stress. By the time p95 climbs, queueing, lock contention, or database overload may already be occurring. If a shared dependency is the cause, scaling out the frontend can raise concurrency and slow the dependency down even further.

Break down latency components using distributed tracing: time spent in the application, database, cache, queue, and external APIs. Use backend latency to scale compute when the backend itself is the bottleneck; use alerts or circuit breakers for failing dependencies.

### Using latency with guardrails

You can scale out when latency exceeds targets alongside rising request rate or CPU. However, to protect SLOs, do not wait for every metric to breach simultaneously before scaling out: a single clear saturation signal can be enough to add capacity. Scale-in should be more conservative and happen only after latency remains stable for a sustained window.

## 5. Queue depth and backlog for asynchronous workloads

Workers typically pull messages from a queue, process them, and acknowledge completion. If arrival rate exceeds processing rate, backlog grows. Queue depth indicates how much work is waiting and serves as a direct demand signal for workers.

### Queue depth

Queue depth is useful when:

- Work can wait in a queue rather than requiring synchronous execution.
- Workers can scale horizontally and independently.
- Messages are distributed fairly uniformly and can be processed in parallel.
- Each worker has a clear concurrency cap on simultaneous jobs.

Looking solely at raw message counts can mislead. A thousand lightweight messages may clear quickly; a hundred heavy messages may take minutes. Supplement with message age, arrival rate, completion rate, and job complexity.

### Backlog per worker

A useful metric is pending messages divided by active workers:

\[
\text{Backlog per worker} =
\frac{\text{Visible queue messages}}{\text{Healthy active workers}}
\]

For example, 1,200 messages across 6 healthy workers gives a backlog of roughly 200 messages per worker. If the target is 50 messages/worker, capacity needs to increase. This is a simple estimate; adjust if workers vary in size or messages differ in processing cost.

Do not divide by desired capacity if some instances are not healthy yet. Use the count of workers actually pulling and processing jobs to avoid underestimating backlog during scale-out.

### Age of oldest message

Age of oldest message measures how long the oldest queued item has been waiting. This metric fits deadlines and SLA/SLO targets well. A queue can have high depth yet low message age if workers drain fast; conversely, a small queue depth can still hide a message stuck for far too long.

If oldest age keeps climbing even as worker count rises, suspect poison messages, hot partitions, failing consumers, or choked dependencies. Simply adding workers may not fix the issue.

### Estimating worker count

Suppose each worker averages 10 messages/second, arrival rate is 80 messages/second, and you want 25% headroom. Target capacity per worker should sit below measured maximum throughput. Worker count can be estimated as arrival rate divided by safe target throughput per worker, rounded up with a reserve margin.

\[
N_{workers} \approx
\left\lceil \frac{\lambda_{in}}{\mu_{target}} \right\rceil
\]

Where \(\lambda_{in}\) is the incoming message rate and \(\mu_{target}\) is the safe processing rate per worker. This formula does not directly factor in existing backlog; to drain an accumulated backlog within a target window, add the throughput required to clear that backlog.

A complementary estimate:

\[
\text{Required processing rate} =
\text{Incoming rate} +
\frac{\text{Current backlog}}{\text{Desired drain time}}
\]

For example, a queue holds 6,000 messages, incoming rate is 40 messages/second, and the goal is clearing backlog in 300 seconds. The system needs to process roughly 40 + 6,000/300 = 60 messages/second. If one worker safely handles 10 messages/second, roughly 6 workers are needed before adding headroom and checking dependency limits.

## 6. Concurrency and active in-flight work

Concurrency is the number of requests, tasks, or connections being processed simultaneously. It fits applications whose serving limit relates to execution slots rather than CPU.

Examples:

- An API server capped at 200 in-flight requests per VM.
- A worker limited to at most 8 concurrent jobs due to high per-job RAM.
- A function runtime with per-instance or per-service concurrency limits.
- A proxy holding many long-lived connections while consuming minimal CPU per connection.

### Normalizing concurrency by capacity

Group-wide total concurrency is insufficient for scaling decisions while instance counts change. Use average concurrency per instance:

\[
\text{Concurrency per instance} =
\frac{\text{Total in-flight work}}{\text{Healthy instances}}
\]

If the target is keeping under 120 in-flight requests per instance and 4 healthy instances are running, target total concurrency is around 480. As instance counts shift, per-instance metrics keep per-node load relatively steady.

### Concurrency does not always equal compute load

An idle WebSocket can stay open for hours while consuming negligible CPU; a request running a heavy query consumes substantial CPU and RAM. Distinguish active connections from in-flight requests or active jobs. Choose the metric closest to the resource actually being constrained.

### Connection pool and dependency limits

During scale-out, total database connections typically scale as instance count multiplied by pool size. If a database supports only 1,000 connections, running 20 instances with a pool of 100 can exhaust the database even while VMs have spare CPU. Factor dependency capacity into autoscaling caps and use pools, proxies, or queues as needed.

## 7. Aggregate, per-instance, and normalized metrics

A common mistake is using an aggregate metric to drive instance counts without accounting for the current number of instances.

| Metric type | Example | When appropriate | Risks |
|---|---|---|---|
| Aggregate | Total CPU, total queue depth, total requests | Measuring overall system demand or total backlog | Changes naturally with instance count; hard to set a static target |
| Average per instance | Average CPU, requests/instance | Target tracking matched to per-machine capacity | Averages hide a hot target or load imbalance |
| Maximum per instance | Peak CPU or peak latency | Detecting hotspots | A single faulty target can trigger unnecessary scale-out |
| Normalized work | Backlog/worker, requests/instance, active jobs/worker | Comparing against active capacity | Requires an accurate, non-stale denominator |
| Rate | Requests/second, messages/second | Measuring demand velocity | Does not reflect request complexity or existing backlog |

When using per-instance metrics, count only healthy instances ready to take load. When using aggregates, be explicit about whether the policy should scale on total demand or average utilization.

## 8. Target tracking, step scaling, and scheduled scaling

Autoscaling services offer several policy styles. Names and exact behaviors vary, yet they generally fall into these categories:

### Target tracking

Target tracking holds a metric around a target value. For instance, keeping average CPU around a tested level or holding backlog per worker below a threshold. The controller calculates capacity changes from the gap between current metric and target.

Best when the metric directly reflects load per capacity unit and can be measured reliably. Avoid metrics that change with instance count in ways that prevent the controller from converging.

### Step scaling

Step scaling uses metric bands to step instance counts up or down. For example, add 1 worker when backlog/worker crosses the first threshold; add 3 workers if it breaches a higher band. This fits systems needing stronger responses as overload worsens.

### Simple scaling

Simple scaling executes a single capacity adjustment per alarm and enforces a cooldown before acting again. It is simple to reason about, though it can react slowly to rapidly shifting load.

### Scheduled or predictive scaling

Scheduled scaling suits predictable calendars, such as pre-scaling before business hours or campaigns. Predictive scaling uses historical patterns to forecast demand if supported by the platform. Even with solid forecasting, keep reactive policies active to handle forecast errors.

## 9. Combining multiple metrics

A workload can be constrained by more than one resource. Relying on a single metric can miss bottlenecks; combining too many metrics with complex rules can make policies unpredictable.

### Asymmetric scale-out and scale-in rules

Scale-out should prioritize protecting SLOs: if any critical saturation metric breaches its threshold, add capacity. Scale-in should be more conservative: reduce capacity only when all key metrics stay low over a sustained window and no backlog remains.

API example:

- Scale out when per-instance CPU is high **or** requests per instance exceed benchmarked capacity.
- Alert when p95 latency breaches the SLO.
- Halt further scale-out if the database connection pool is saturated; instead protect the database and investigate the dependency.
- Scale in only when CPU, requests per instance, and latency are all stably low.

Worker example:

- Scale out on backlog per worker or age of oldest message.
- Cap worker count according to downstream database/API capacity.
- Block scale-in while long jobs are running or queue age exceeds target.
- Use checkpointing and graceful shutdown to prevent losing work during scale-in.

### Limiting policy conflicts

If multiple policies manage the same group, one policy may request scale-out while another requests scale-in. Understand how the provider reconciles policies—typically favoring capacity increases or taking the largest change—but never rely on vague assumptions. Design one clear policy or define explicit precedence and test combined behavior.

## 10. Measurement intervals, cooldowns, and autoscaling stability

Metric reporting intervals must match how fast the workload changes. If metrics update every 5 minutes while bursts happen in 30 seconds, autoscaling reacts too late. If metrics are noisy and evaluated every few seconds, the group can thrash up and down.

### Timing windows to coordinate

- **Metric period:** the aggregation interval for metric datapoints.
- **Evaluation window:** the number of datapoints or duration used to evaluate alarms.
- **Instance warm-up:** time for a VM to boot, bootstrap, and become healthy.
- **Cooldown/stabilization:** wait period after a change so metrics reflect new capacity.
- **Health check grace period:** startup grace time before evaluating instance health under policy.
- **Scale-in stabilization:** duration load must remain low before reducing capacity.

If scaling out takes 2 minutes to produce a healthy target, the policy must react early enough so backlogs do not breach SLOs while waiting. Use scheduled/predictive scaling or capacity buffers for fast-bursting workloads.

### Hysteresis

Hysteresis uses separate thresholds for scale-out and scale-in to prevent oscillation. For example, scale out when CPU crosses a higher threshold; scale in only when CPU stays below a lower threshold for a longer duration. This creates a stable deadband rather than toggling capacity around a single point.

### Warm-up and post-scale-out metrics

New instances may not accept traffic immediately, causing group-wide average CPU to drop right after adding machines. If a policy reacts too quickly to that drop, it may scale back in immediately after scaling out. Configure warm-up periods or metrics scoped to active serving targets, and verify how the autoscaling service treats newly launched instances.

## 11. Avoiding harmful scaling when dependencies are constrained

Compute autoscaling does not automatically add capacity to databases, caches, network gateways, or external APIs. When a dependency is the bottleneck, adding workers can make matters worse.

Guardrails to consider:

- Cap max instances based on safe database connection limits.
- Use connection pools, proxies, or semaphores to cap downstream concurrency.
- Scale workers on backlog while capping max concurrency at dependency throughput.
- Use circuit breakers and backoff to shed load when dependencies fail.
- Monitor queue age and error rates alongside CPU/concurrency.
- Isolate pools by workload priority so one job class cannot starve all capacity.

If latency climbs alongside database CPU, lock waits, or connection counts, do not just add web instances. Fix queries, pooling, caching, or dependency capacity.

## 12. Building high-quality custom metrics

Some workloads need domain-specific metrics like job weight, remaining bytes to process, queued inference tokens, or active sessions. Custom metrics can outperform CPU when they directly represent units of work.

### Design principles

1. **Clear units:** messages, requests, job-seconds, bytes, tokens, or work units.
2. **Explicit denominator:** per instance, per healthy worker, or system total.
3. **Frequent enough updates:** aligned with scaling speed and job duration.
4. **No stale values:** distinguish zero values from missing data.
5. **Bounds and sanity checks:** catch negative values, invalid spikes, or telemetry loss.
6. **Tied to capacity:** benchmark how many work units one instance safely handles.

### Custom metric example

A document-processing worker can emit `pending_work_units` instead of merely counting files. A small PDF might count as 1 work unit, while a large multi-page scan maps to multiple units by file size or page count. Scaling on pending work units per worker reflects real load much better if the weighting correlates with processing time.

Avoid putting user IDs, request IDs, or high-cardinality labels into metric dimensions if your telemetry system charges per series or caps cardinality. Use coarse tags/labels such as service, environment, queue, and worker pool.

## 13. Metric selection examples across workloads

| Workload | Primary metric | Secondary/guardrail metric | Rationale |
|---|---|---|---|
| CPU-bound API | CPU per instance or requests per instance | p95 latency, error rate | CPU tracks saturation; latency protects SLOs |
| DB-waiting API | In-flight requests or capped requests per instance | DB connections, query latency, error rate | Low CPU misses pool or dependency saturation |
| Message worker | Backlog per worker | Oldest message age, processing rate, downstream capacity | Tracks pending work volume and deadlines |
| Batch jobs | Pending work units / estimated remaining duration | Job age, completion deadline | Individual jobs can vary widely in cost |
| WebSocket service | Active sessions per instance | Memory, network throughput, reconnect rate | Long-lived sessions consume connections and RAM |
| GPU inference | Requests or tokens per GPU/instance | GPU utilization, VRAM, p95 latency | CPU does not reflect accelerator saturation |
| Video transcoding | Queue work units or job duration estimate | GPU/CPU utilization, storage throughput | Per-job cost depends on codec, resolution, and duration |
| Serverless worker | Concurrency and queue age | Throttles, duration, downstream connections | Runtime may hit concurrency caps before CPU bottlenecks |

### Web API example

An API runs on 4 VMs. Benchmarks show each VM stably serves roughly 150 requests/second below the p95 latency target. To preserve headroom, the team sets a target of 100 requests/second per VM. When total traffic reaches 700 requests/second, roughly 7 VMs are required under that target. A target tracking policy on requests per healthy instance scales capacity, while CPU and p95 latency serve as guardrails to validate assumptions.

These are illustrative figures. Real capacity must be benchmarked against actual request mixes, dependencies, cache hit ratios, and machine types.

### Queue worker example

A queue holds 9,000 messages. Target backlog is 300 messages per worker; with 10 healthy workers active, backlog/worker is 900. The autoscaler needs to add workers. However, if each worker opens 20 database connections and the database only allows 100 more connections, workers cannot scale unrestrictedly. Cap workers, shrink pools, or scale the database first.

### GPU inference service example

VM CPU sits at 25%, yet GPU utilization is near saturation, free VRAM is low, and p95 latency is rising. Scaling on CPU will never trigger. Better metrics are requests/tokens per GPU, GPU utilization, or queue age, paired with VRAM and latency. If model loading takes 3 minutes, configure warm-up periods and buffer capacity for bursts.

## 14. Testing and tuning policies

Never pick targets solely from rules of thumb. Test under representative load:

1. Define SLOs, request mixes, message sizes, and dependencies.
2. Measure safe throughput for one instance/worker/GPU.
3. Step load upward while recording CPU, latency, queues, concurrency, memory, and errors.
4. Identify which metrics move before SLOs degrade.
5. Choose targets and thresholds with headroom for machine startup times.
6. Test bursts, gradual ramps, load drops, slow dependencies, and single-zone loss.
7. Verify scale-out adds capacity in time and scale-in does not interrupt jobs.
8. Tune cooldowns, warm-up times, min/max capacity, and scale-in protection.

Track the total elapsed time from metric breach until a new target becomes healthy. If that lag exceeds the time it takes backlogs to breach limits, add capacity buffers, scheduled scaling, or optimize boot/bootstrap speed.

## 15. Troubleshooting autoscaling metrics

| Symptom | Possible causes | Investigation steps |
|---|---|---|
| High CPU but no scale-out | Misconfigured alarm/policy, metric not published, max capacity reached | Check alarm state, policy bindings, quotas, and max size |
| Continuous scale-out despite flat latency | Aggregate metric grows with instance count or wrong target | Verify metric normalization and denominator |
| Large queue yet workers stay flat | Stale queue metric, missing publish permissions, or policy detached | Inspect metric timestamps, IAM permissions, and scaling activity |
| Workers scale up yet oldest message age stays high | Stuck jobs, hot partitions, or slow dependencies | Check consumer errors, poison messages, and downstream latency |
| Immediate scale-in right after scale-out | Misconfigured warm-up/cooldown, metric dilution | Check instance warm-up, stabilization windows, and hysteresis |
| High p95 latency with no scaling | Wrong collection scope or overly long alarm window | Inspect percentile math, sample counts, and evaluation periods |
| Scale-out worsens database errors | Downstream concurrency exceeds capacity | Cap pools, max workers, and add circuit breakers |
| One VM runs hot while average stays low | Averages hide hotspots or skewed traffic | Inspect per-instance/max metrics, stickiness, and target health |
| Scale-in drops active jobs | Missing draining/checkpoints or premature termination | Check lifecycle hooks and graceful shutdown |
| Missing metric data treated as 0 | Wrong missing-data policy | Distinguish no-data from zero and alert on telemetry loss |

When investigating, correlate metrics against autoscaling activity history, instance lifecycle events, target health, and application logs on the same timeline.

## 16. Metric selection checklist

**Understand the workload:**

- [ ] Defined the unit of work and arrival rate.
- [ ] Identified common bottlenecks: CPU, RAM, I/O, network, GPU, connections, or dependencies.
- [ ] Defined SLOs for latency, throughput, queue age, or completion time.
- [ ] Measured safe capacity per instance/worker.

**Metric design:**

- [ ] Chose a primary metric tied to the bottleneck or demand.
- [ ] Decided between aggregate vs. per-instance/per-worker metrics.
- [ ] Used healthy capacity as the denominator when normalizing.
- [ ] Added secondary metrics to watch dependencies and service quality.
- [ ] Defined units, reporting intervals, missing-data handling, and an owner.

**Policy configuration:**

- [ ] Selected target tracking, step, scheduled, or predictive scaling appropriately.
- [ ] Set min/max capacity aligned with quotas and dependencies.
- [ ] Configured warm-up, cooldown, stabilization, and hysteresis.
- [ ] Protected long-running jobs and active connections during scale-in.
- [ ] Verified how multiple policies combine if using more than one metric.

**Testing:**

- [ ] Tested rapid spikes, gradual ramps, and load drops.
- [ ] Tested slow or unavailable dependencies.
- [ ] Verified scale-out finishes before SLOs breach.
- [ ] Verified scale-in causes zero lost requests or jobs.
- [ ] Measured costs and idle capacity ratios after tuning.

## Conclusion

CPU suits compute-bound workloads; latency reflects serving quality but can lag; queue depth and oldest message age suit asynchronous workers; concurrency fits when simultaneous work slots are the main constraint. Normalize metrics by healthy instances or workers, and pair them with dependency guardrails and SLOs. Benchmark safe capacity, pick policies with proper warm-up/cooldown and hysteresis, and test both scale-out and scale-in. A good policy adds machines when extra capacity genuinely improves serving capability and removes machines when headroom is safe without disrupting active work.
