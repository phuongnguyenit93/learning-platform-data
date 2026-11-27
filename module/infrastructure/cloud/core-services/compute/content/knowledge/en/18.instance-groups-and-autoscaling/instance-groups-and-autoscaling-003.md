# Target Tracking, Step Scaling, and Scaling Schedules

Autoscaling adjusts compute resource counts based on workload demand. When traffic rises, the system adds virtual machines, containers, or workers to preserve performance; when demand drops, it shrinks the machine group to avoid paying for idle capacity. For autoscaling to behave reliably, you must choose the right load signals, set capacity bounds, and coordinate startup times, health checks, load balancing, and instance termination.

Three common control strategies are **target tracking**, **step scaling**, and **scheduled scaling**. Target tracking tries to hold a metric near a target value; step scaling reacts according to alarm breach magnitudes; scheduled scaling changes capacity on a known schedule. Each fits a different demand pattern and can be combined when designed clearly.

This lesson places these policies in the context of cloud machine groups, from VM instance groups to container services and background workers. After this lesson, you will be able to:

- Distinguish the mechanisms and use cases of target tracking, step scaling, and scheduled scaling.
- Choose metrics that accurately reflect load and per-instance capacity.
- Calculate minimum, target, and maximum capacity based on SLOs.
- Design thresholds, step increments/decrements, warm-up times, and cooldowns.
- Combine scaling schedules with dynamic policies without causing oscillation or conflicts.
- Verify scale-out, scale-in, health checks, draining, and costs after deployment.

## 1. Machine groups and capacity limits

An instance group or autoscaling group manages a collection of machines with similar configuration and roles. The controller can create or terminate instances to bring the machine count to the desired level.

Three fundamental values:

- **Minimum capacity (min):** the minimum number of instances to maintain.
- **Desired capacity (desired):** the number of instances the group is currently targeting.
- **Maximum capacity (max):** the maximum number of instances allowed to run.

This relationship always holds:

\[
min \le desired \le max
\]

For example, a web group has **min = 2**, **desired = 4**, **max = 12**. The group starts with four instances, can scale up to twelve during high load, and never drops below two to preserve baseline capacity.

~~~mermaid
flowchart TD
    M["Min capacity: 2"] --> D["Desired capacity: 4"]
    D --> X["Max capacity: 12"]
    D --> P["Autoscaling controller"]
    P --> A["Launch instances when needed"]
    P --> R["Remove instances when capacity is excessive"]
~~~

These values are control bounds and target states, not proof that the application has enough capacity. If each instance handles 50 requests/second within the required SLO, a group of four instances may be insufficient for 500 requests/second even though desired capacity is met.

### How does desired capacity change?

An autoscaling policy observes a metric or schedule and asks the controller to adjust desired capacity. The platform handles creating or removing instances, but actual realization time depends on quotas, capacity availability, boot images, agent installation, application startup, and readiness checks.

Autoscaling generally operates in two directions:

- **Scale-out:** increasing the number of instances to absorb load.
- **Scale-in:** reducing the number of instances when load decreases.

Scaling out too slowly can cause the service to breach SLOs before new machines are ready. Scaling in too aggressively can terminate instances still serving requests or running jobs. Policies must therefore account for both capacity change speed and workload lifecycle.

## 2. Choosing metrics that reflect true load

A policy is only as good as the metric representing the problem to solve. CPU is a common metric, yet not every workload is CPU-bound.

| Workload type | Candidate metrics | When useful |
|---|---|---|
| Web/API | CPU utilization, request count per instance/target, concurrent requests, response time | When request load drives CPU, request volume, or latency |
| Queue worker | Backlog per worker, age of oldest message, job arrival rate, job completion rate | When the queue grows faster than processing capacity |
| Batch compute | Pending job count, estimated completion time, busy worker count | When the goal is clearing backlog within a deadline |
| Memory-bound service | Memory utilization, working set, page faults, or swap | When memory limits session count or causes paging |
| GPU inference | GPU utilization, VRAM, request queue, tokens/s, or requests per accelerator | When accelerators are the bottleneck |
| Container service | Per-pod or per-task CPU/memory utilization, request rate, queue depth | When adjusting replicas or node capacity |

### Metrics must correlate with capacity

Target tracking works best when changing instance counts has a predictable relationship with the metric. For example, if total request rate stays constant and instance count doubles, average requests per instance roughly halve when load is evenly distributed.

Some aggregate metrics do not automatically drop when instances are added. For instance, total queue depth may remain high right after scale-out because of existing backlog. For workers, **messages per worker** or **backlog per capacity unit** helps the policy better understand load per compute unit. If only total queue depth is available, design step scaling or an appropriate derived metric.

For APIs, **requests per target** is usually more meaningful than total system request count. However, requests can vary in processing cost; 100 cache-read requests are not equivalent to 100 heavy query requests.

### Latency and lagging metrics

Latency is closely tied to user experience, but it often rises after capacity is already exhausted. If an autoscaler only scales when p95 breaches the SLO, the system may react too late. Combine leading load metrics such as request rate, queue depth, or CPU with latency as a validation and alerting signal.

Metrics need:

- Sufficient resolution and reporting frequency.
- Stable data with minimal missing points and low reporting lag.
- Scope aligned accurately to the machine group or workload.
- Consistent units and aggregation methods.
- Clear distinction between genuine load and telemetry errors.

Do not use a metric influenced by other policies without understanding the feedback loop. For example, cache hit ratio may drop during scale-out because new instances start with cold caches; this metric alone should not trigger unbounded scale-out.

## 3. Target tracking: keeping a metric near a target

Target tracking is a policy that automatically adjusts desired capacity to keep a metric close to a target value. Think of it as a feedback controller:

1. Collect the current metric.
2. Compare the metric against the target.
3. Estimate the capacity to add or remove.
4. Adjust desired capacity within min/max bounds.
5. Wait for instances to start and the metric to reflect the new state.
6. Continue adjusting as load changes.

For example, a web group sets an average CPU target of 55%. When CPU stays above target, the policy adds instances; when CPU stays below target stably enough, the policy can reduce capacity.

### Choosing the target value

The target value should be derived from benchmarks and SLOs. If each instance handles 100 requests/second with p95 under 200 ms, yet at 130 requests/second p95 spikes rapidly, do not set the target at the 130 ceiling. Leave headroom to absorb bursts and variance across instances.

For CPU utilization, a 50–60% target can be a reasonable starting point for some web workloads, though it is not a universal rule. Batch workers can run higher CPU; latency-sensitive services need larger headroom. Measure under representative load and test what happens when one instance fails.

### Target tracking example for an API

Suppose benchmarks show one instance stably handles 100 requests/second within SLO. Expected traffic is 600 requests/second. The baseline throughput-based instance count is:

\[
N = \left\lceil \frac{600}{100} \right\rceil = 6
\]

If you need redundancy for one failed instance plus burst headroom, the group can set minimum or target capacity higher than the pure throughput calculation. Target tracking on request count per target will adjust capacity as load shifts, while min/max constrain the range.

The 100 requests/second figure is an assumed benchmark result. Always measure using actual request distributions, payloads, dependencies, and SLOs.

### Advantages and limitations

**Advantages:**

- Minimizes the need to manually define multiple scale-out/scale-in thresholds.
- Continuously adapts to fluctuating load.
- Fits metrics that correlate clearly with capacity.
- Reduces operational toil when demand shifts constantly.

**Limitations:**

- Metrics can lag or fail to reflect the true bottleneck.
- Instance startup time slows down system reaction.
- Setting the target too high leaves no headroom; setting it too low raises costs.
- If the metric does not decrease when instances are added, the policy may keep scaling despite sufficient capacity.
- Scale-in can be unsafe for stateful workloads or long-running jobs.

Target tracking is not an instantaneous switch. Account for metric collection intervals, policy evaluation, provisioning, booting, warm-up, and load balancer registration.

## 4. Step scaling: reacting by breach magnitude

Step scaling uses metric alarms to trigger tiered capacity adjustments. Instead of holding a metric at one target, operators define breach bands and corresponding capacity changes.

Example using CPU utilization:

| Alarm breach severity | Illustrative adjustment |
|---|---:|
| Slight CPU breach | Add 1 instance |
| Moderate CPU breach | Add 2 instances |
| High CPU breach | Add 4 instances |

Actual bands must follow the platform's syntax without overlapping or leaving unintended gaps. Some services evaluate step adjustments based on how far the metric exceeds the alarm threshold; always read the provider's exact semantics before configuring.

### Designing alarms and step adjustments

A step scaling policy needs to specify:

- Metric and statistic, such as average CPU or maximum queue age.
- Alarm threshold and number of consecutive breaching periods.
- Sampling interval and evaluation period.
- Breach bands and how many instances to add/remove in each band.
- Min/max capacity and rate-of-change limits.
- Cooldown or warm-up periods to avoid repeated actions before new instances are ready.

Illustrative example for queue workers:

- If backlog age exceeds 30 seconds for 2 periods, add 1 worker.
- If backlog age exceeds 60 seconds, add 3 workers.
- If backlog age exceeds 120 seconds, add 5 workers, up to max capacity.
- Scale in only when backlog age is low and busy worker counts have dropped steadily.

Do not scale solely on raw message counts in a queue while ignoring per-worker processing speed. If new jobs arrive faster than processing capacity, the queue keeps growing even after adding a few workers.

### When is step scaling appropriate?

- Traffic surges abruptly and requires aggressive reactions proportional to overload severity.
- Clear operational thresholds exist from SLOs or alerting rules.
- Workloads have distinct priority levels or processing cost tiers.
- You want explicit control over capacity step sizes rather than letting a target policy compute them.
- Queue workers need larger batches of consumers when backlogs cross specific milestones.

Step scaling is straightforward to reason about, though it requires tuning. Overly sensitive alarms cause repeated scaling; requiring too many evaluation periods slows reaction. Large step increases can also overwhelm databases or downstream dependencies.

## 5. Scheduled scaling: preparing capacity on a schedule

Scheduled scaling adjusts capacity at predetermined times. This suits workloads with recurring patterns or known events:

- Online stores with predictable midday or evening traffic peaks.
- Reporting systems running morning batch jobs.
- Online classes or live events with fixed start times.
- Internal services active only during business hours.
- Data import runs with an explicit deployment schedule.

Example schedule for a service peaking at 09:00:

| Time | Capacity setting |
|---|---|
| 08:40 | Raise minimum/desired so new machines begin starting |
| 09:00 | Service enters peak hours |
| 12:00 | Maintain scheduled capacity if demand remains high |
| 18:00 | Lower minimum to baseline; dynamic policies continue protecting if load stays high |
| 22:00 | Maintain overnight minimum |

Schedules must start ahead of load arrival to cover provisioning, booting, agent setup, image pulls, cache warm-up, and health checks. If a VM takes 6 minutes to become ready, scheduling right at 09:00 may be too late.

### Timezones and schedule changes

Clarify whether schedules use UTC or local timezones. Local timezones with daylight saving time (DST) can shift execution times seasonally. Some platforms support timezone names and handle DST automatically; others accept only UTC cron expressions.

Schedules must also be updated when operating hours change, on holidays, or for special events. Avoid creating overlapping schedules without understanding precedence rules and how they overwrite desired/min/max.

### Scheduled scaling does not replace dynamic scaling

Schedules prepare capacity ahead of known demand. If actual traffic is higher or lower than forecast, target tracking or step scaling may still be needed to adjust. A common pattern is:

- Scheduled scaling raises the baseline or minimum ahead of peak hours.
- Target tracking adjusts dynamically to actual load during that window.
- Step scaling handles unexpected backlogs or threshold overloads.

When combining policies, explicitly verify which policy controls desired capacity, which adjusts min/max, and how the platform resolves concurrent policies.

## 6. Comparing the three strategies

| Criterion | Target tracking | Step scaling | Scheduled scaling |
|---|---|---|---|
| Control signal | Metric relative to target | Alarms and breach magnitude | Time/schedule |
| Behavior | Continuously self-adjusts to metric | Adjusts in predefined steps | Changes capacity at scheduled times |
| Best suited for | Continuously varying load where metric scales with capacity | Bursts, backlogs, or clear thresholds | Periodic load or known events |
| Tuning effort | Picking a good metric and target | Designing alarms, bands, and steps | Forecasting schedules and lead times |
| Main risk | Wrong metric or slow reaction | Oscillating thresholds, over/under-stepping | Schedule mismatch with actual demand |
| How to combine | Adjusts around baseline capacity | Adds fast reaction on severe breaches | Sets baseline ahead of load arrival |

No single policy fits every workload. Many systems use scheduled scaling to prepare the baseline, then rely on target tracking for fluctuations. Step scaling is added when a decisive response to a threshold breach is needed.

## 7. Warm-up, cooldown, and control loop stability

After scale-out, new instances do not immediately deliver useful capacity. They may need to:

1. Be provisioned by the cloud provider.
2. Boot the OS or start containers.
3. Install/start agents and fetch configuration.
4. Load models, caches, or initial data.
5. Register with the load balancer.
6. Pass readiness checks.

**Instance warm-up** is the time needed for a new instance to become ready and for metrics to reflect its added capacity. If the autoscaler ignores this period, it may keep scaling out because the metric has not dropped yet, leading to over-provisioning.

**Cooldown** or stabilization windows prevent consecutive adjustments immediately after a scaling action. Naming and semantics differ across platforms. Some services apply warm-up per new instance and cooldown between policy actions; do not treat them as identical parameters.

### Avoiding scale-out/scale-in oscillation

*Flapping* happens when a group repeatedly adds and removes capacity. Common causes include:

- Scale-out and scale-in thresholds set too close together.
- Noisy or slow-updating metrics.
- Long instance startup times paired with overly frequent policy evaluations.
- Scale-in pushing load onto remaining instances, immediately triggering scale-out again.
- Multiple policies controlling the same group without clear precedence.

Measures to reduce oscillation:

- Use more conservative thresholds for scale-in than for scale-out.
- Set stabilization windows aligned with workload response times.
- Smooth metrics or require multiple consecutive confirmation periods.
- Keep minimum capacity with sufficient headroom.
- Scale in only when queues, latency, and utilization are all stable.
- Monitor scaling event frequency and time-to-ready.

## 8. Safe scale-in: draining and workload protection

Scale-in can cause disruptions if instances are serving requests or running long jobs. Before termination:

- Stop sending new requests to the instance.
- Use connection draining or deregistration delays on backends.
- Allow in-flight requests to complete within a time limit.
- For workers, stop pulling new jobs and finish or return uncompleted jobs.
- Save checkpoints if tasks can resume after instance replacement.
- Ensure durable data is not stored solely on ephemeral instance disks.

Some platforms support scale-in protection or instance protection. Use it to retain machines running critical jobs, but ensure protection is cleared once the job finishes; otherwise, the group cannot scale in and costs rise.

In container orchestration, combine readiness probes, termination grace periods, `preStop` hooks, `PodDisruptionBudget`, and `SIGTERM` handling. In VM groups, use lifecycle hooks or equivalent mechanisms to drain before terminating machines.

## 9. Integrating autoscaling with load balancers and queues

### Web/API

The load balancer routes requests to healthy backends. The autoscaler adds instances when CPU, requests per target, or another chosen metric exceeds its target. New instances should receive traffic only after passing readiness checks. During scale-in, backends are deregistered and drained before termination.

### Queue workers

Queues buffer jobs when workers cannot keep up. Autoscalers can track backlog per worker or age of oldest message. When adding workers, ensure dependencies like databases, external APIs, and object storage can handle increased consumer concurrency. If workers scale too fast, downstream systems can overload even as the queue drains.

### Container services

Replica autoscaling at the pod/task layer and node autoscaling are two separate layers. If replicas scale up when the cluster lacks node capacity, pods stay pending. If nodes scale up while workload replicas stay flat, new machines sit idle. Coordinate service-level scaling with cluster/node autoscaling and configure accurate resource requests/limits.

### Serverless

Serverless platforms automatically scale execution instances based on concurrency or request rate, yet quotas and concurrency caps still apply. Check account limits, cold starts, downstream connection pools, and retries. If a function scales rapidly and opens too many database connections, the database can quickly become the bottleneck.

## 10. Calculating capacity and headroom

A rough calculation helps establish min/target/max bounds:

\[
N_{required} = \left\lceil \frac{L_{peak}}{C_{safe}} \right\rceil
\]

Where:

- \(L_{peak}\) is expected peak load.
- \(C_{safe}\) is the safe capacity of one instance while meeting SLOs.
- \(N_{required}\) is the minimum instance count for that load.

If you need to survive one instance failure, add reserve capacity:

\[
N_{with\ failure} = N_{required} + N_{failure\ reserve}
\]

For example, an API expects 800 requests/second. Benchmarks show each instance safely handles 100 requests/second within SLO:

\[
N_{required} = \lceil 800 / 100 \rceil = 8
\]

To tolerate one failed instance without breaching the SLO, capacity equivalent to at least 9 instances is needed under this assumption. Min can be set based on baseline load and availability requirements; max must be high enough to absorb peaks without exceeding quotas, budgets, or dependency limits.

This is an initial calculation. In practice, performance does not always scale linearly with instance count due to network overhead, databases, caches, contention, and uneven load distribution. Verify with load tests while one or more instances are removed.

## 11. Example configuration combining all three policies

An order-processing service has these characteristics:

- Baseline load of roughly 150 requests/second.
- Known peak hours from 09:00 to 11:00, reaching up to 600 requests/second.
- Each instance safely processes 100 requests/second within SLO.
- An instance takes about 5 minutes to boot, load configuration, and pass readiness checks.

An illustrative design:

| Component | Reference setting | Purpose |
|---|---|---|
| Min capacity | 2 | Maintain baseline availability |
| Initial desired | 2–3 depending on current load | Start the service |
| Max capacity | 12 | Cap by quota and budget |
| Scheduled scaling | At 08:50 raise min/desired to 7 or 8 | Pre-warm before 09:00 peak |
| Target tracking | Request per target aiming around 80–90 requests/second | Adapt to actual load |
| Step scaling | When errors/queues or load metrics breach severe levels for a confirmation window, add a capacity batch | React to bursts beyond forecast |
| Scale-in | Reduce only after peak hours when metrics stay low stably and backends are drained | Avoid cutting capacity prematurely |

These values are illustrative design examples, not rigid formulas. If the scheduled policy raises minimum to 8, target tracking can still scale higher if load demands it. After the peak, the schedule lowers minimum back to 2, while target tracking keeps desired higher if real load has not subsided. Always check platform semantics on whether schedules set desired or min/max and how other policies interact.

## 12. Autoscaling implementation and testing workflow

1. **Measure the workload:** collect baseline, peak, burst, job duration, and SLO data.
2. **Benchmark instances:** determine safe capacity for each machine type.
3. **Set min/max:** calculate from baseline load, fault tolerance, quotas, and budget.
4. **Select metrics:** choose metrics correlated with capacity and with appropriate latency.
5. **Configure policies:** set up target, step, or scheduled policies; document who controls min/max/desired.
6. **Configure warm-up and scale-in:** set startup times, draining, and job protection.
7. **Test scale-out:** ramp load up, measure time until instances are ready and metrics drop.
8. **Test scale-in:** reduce load, verify requests/jobs finish and instances terminate cleanly.
9. **Test failure modes:** exhausted quotas, failed instance boots, missing metric data, or saturated dependencies.
10. **Monitor and tune:** review SLOs, scaling frequency, spare capacity, and cost.

### Test scenarios to include

- Gradual and sudden load increases.
- Rapid load drops after peak hours.
- An instance becoming unhealthy or terminating unexpectedly.
- New instances starting more slowly than usual.
- Delayed or missing metric datapoints.
- Load continuing to rise after reaching max capacity.
- Scheduled events firing on time and respecting timezones.
- Scale-in while backends hold long-lived connections or workers hold active jobs.

## 13. Observing and optimizing policies

Monitor not only instance counts, but also service quality and cost:

| Category | Metrics |
|---|---|
| Capacity | Desired, current, min/max, pending, healthy, and unhealthy instances |
| Scaling activity | Trigger time, reason, instances added/removed, provisioning errors |
| Performance | p50/p95/p99 latency, successful throughput, error rate |
| Resources | CPU, memory, network, disk, GPU utilization |
| Queues | Backlog, age of oldest message, arrival/completion rates |
| Readiness | Boot time, warm-up duration, backend registration time |
| Cost | Instance-hours, idle cost, peak cost, and cost per request/job |

Questions to ask after every test:

- When did scale-out begin relative to when SLOs started degrading?
- How long did it take for new instances to actually receive traffic?
- Did the target metric drop after capacity increased?
- Did scaling hit max capacity or run into quotas?
- Did scale-in cause latency, errors, or queue age to climb again?
- Are any instances running without serving work due to health check or registration errors?
- Is the cost of spare capacity proportional to the availability improvement?

If scale-out happens too late, switch to earlier leading metrics, add schedules, or raise the baseline. If scale-out overshoots, adjust step sizes, targets, or stabilization windows. If scale-in causes errors, tighten safety thresholds, extend draining, or improve stateless/checkpointing design.

## 14. Common mistakes

1. **Using CPU for every workload:** queues, memory, I/O, or GPUs may be the real bottleneck.
2. **Setting the target equal to max benchmark capacity:** leaves zero headroom for bursts or instance failures.
3. **Using metrics that do not scale with capacity:** adding instances does not reduce the metric, causing the autoscaler to keep scaling.
4. **Scheduling right at load start time:** instances lack time to boot and warm up.
5. **Omitting timezone configuration:** schedules drift across timezones or DST transitions.
6. **Overly sensitive alarms:** step scaling fires repeatedly and causes oscillation.
7. **Scaling in immediately on a single-period metric dip:** load may bounce back or backends may still hold active requests.
8. **Leaving max capacity unset:** costs or downstream load can grow unchecked.
9. **Forgetting quotas and capacity supply:** policies request machines the cloud cannot provision.
10. **Scaling workers without protecting downstream services:** databases or external APIs get overloaded.
11. **Multiple policies driving the same metric without clear precedence:** desired capacity shifts unpredictably.
12. **Never testing scale-in:** machines are killed mid-job or while holding local state.

## 15. Production readiness checklist for autoscaling

- [ ] Baseline, peak, burst patterns, and SLOs are documented.
- [ ] Safe per-instance capacity has been benchmarked.
- [ ] Selected metrics reflect the true bottleneck and correlate with capacity.
- [ ] Min, desired, and max align with availability, quotas, and budget.
- [ ] Target tracking has validated targets and headroom.
- [ ] Step scaling has non-overlapping bands, alarms, and evaluation periods.
- [ ] Scheduled scaling uses the right timezone and starts ahead of load arrival.
- [ ] Interactions between schedules and dynamic policies are defined.
- [ ] Warm-up, cooldown/stabilization, and scale-in protection are configured.
- [ ] Load balancer routes traffic only to ready instances.
- [ ] Connection draining and graceful shutdown are tested.
- [ ] Workers have appropriate checkpointing/acknowledgement/retry logic.
- [ ] Downstream systems can sustain scale-out capacity.
- [ ] Alerts exist for hitting max, quota exhaustion, or scaling activity failures.
- [ ] Tested scale-out, scale-in, bursts, instance failures, and missing metrics.
- [ ] Dashboards track SLOs, capacity, scaling activity, and costs.

## 16. Practice exercise

An image-processing worker group receives an average of 300 jobs/minute, but for roughly 10 minutes at the top of each hour the backlog surges to 1,200 jobs/minute. Each worker reliably processes 60 jobs/minute and takes 3 minutes to start up. The system requires the oldest job age to stay under 2 minutes during peak periods. Overnight, a minimum of 2 workers suffices for occasional tasks.

1. Estimate the number of workers needed for a load of 1,200 jobs/minute before adding headroom.
2. Which metric should target tracking use to reflect load per worker?
3. What backlog age or job arrival rate tiers could step scaling use to react to bursts?
4. How far ahead of the burst should scheduled scaling start, and why?
5. When load drops, what should be verified before scaling workers in?
6. What max capacity limits should be set to protect downstream storage?

Hint: pure capacity worker count is \(1200/60 = 20\), then add headroom based on SLOs and real variance. You can use backlog per worker or age of oldest job as the metric; the target must be benchmarked. Because workers take 3 minutes to warm up, the schedule should start early enough for workers to be ready before load arrives. Before scale-in, stop pulling new jobs, complete or return uncompleted jobs, and inspect queue age alongside storage capacity.

## Conclusion

Target tracking works well when a metric clearly correlates with capacity and needs continuous self-adjustment. Step scaling is useful when reacting proportionally to specific threshold breaches. Scheduled scaling prepares capacity ahead of known cycles or events. To keep all three operating smoothly, choose the right metrics, size min/max and headroom, account for warm-up time, safeguard scale-in, coordinate with load balancers and dependencies, and test both scale-out and scale-in before going to production.
