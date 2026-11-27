# Configuring Autoscaling and Observing Behavior During Load Increase and Decrease

Autoscaling enables a system to automatically adjust its number of virtual machines to actual demand rather than maintaining a fixed size all day. When load rises, the system adds instances to preserve serving capacity; when load drops, the system removes instances to avoid paying for unneeded capacity. However, merely turning on a scaling policy is not enough. A sound configuration must pick the right signals, set reasonable thresholds and evaluation windows, protect in-flight requests during scale-in, enforce resource limits, and provide end-to-end visibility from when a metric changes until instances actually receive or stop receiving traffic.

In the **CLOUD_CORE_SERVICES_COMPUTE** module, this lesson guides you through configuring autoscaling for a virtual machine group and observing scale-out/scale-in behavior in operations. Topics include metric selection, policy design, configuring min/desired/max capacity, warm-up, cooldown, health checks, connection draining, dashboards, alerting, and a hands-on load-generation lab. The examples use a mock web/API service with a load balancer, an application VM group, and a queue worker; the concepts apply to equivalent mechanisms across multiple cloud platforms.

## Learning Objectives

After this lesson, you will be able to:

- Explain autoscaling and distinguish scale-out, scale-in, vertical scaling, and scheduled/predictive scaling.
- Identify metrics suited to the workload type instead of relying solely on CPU.
- Design min, desired, max capacity, and headroom based on load, SLOs, quotas, and budgets.
- Configure target tracking, step scaling, scheduled scaling, and safe scale-in policies.
- Understand the role of instance warm-up, cooldown, stabilization windows, and health checks.
- Combine load balancers, readiness, lifecycle hooks, and connection draining so in-flight requests are never severed.
- Build dashboards tracking infrastructure metrics, application metrics, scaling activities, and costs.
- Run a lab increasing load to observe scale-out and decreasing load to observe scale-in.
- Diagnose scenarios where autoscaling fails to trigger, scales too aggressively, or overloads dependencies.
- Define alerts, acceptance criteria, and a production readiness checklist for autoscaling.

## 1. What Is Autoscaling?

Autoscaling is a mechanism that automatically adjusts workload capacity based on metrics, schedules, or demand forecasts. For virtual machine groups, capacity is typically adjusted by increasing or decreasing the number of instances in a VM group/instance group/scale set.

### 1.1. Directions of Capacity Change

- **Scale-out:** Increasing the number of instances to handle additional requests, connections, or jobs.
- **Scale-in:** Decreasing the number of instances when demand drops, while ensuring removed instances no longer hold active critical work.
- **Vertical scaling:** Changing an instance to a larger CPU, memory, network, or storage configuration. Typically requires resizing/restarting and does not fully replace scale-out.
- **Scheduled scaling:** Adjusting capacity on a known schedule—for instance, scaling up before opening hours or batch windows.
- **Predictive scaling:** Using historical trends or forecasts to provision capacity ahead of arriving load, when supported by the platform and workload.

Autoscaling does not mean all underlying resources scale automatically. Databases, IP subnets, quotas, NATs, load balancers, disk IOPS, and connection limits may remain fixed. If only application VMs scale up while the database cannot handle the new connections, autoscaling can worsen an incident.

### 1.2. Why Autoscaling Is Needed

1. **Maintain user experience:** Add capacity when request rates or concurrency rise.
2. **Optimize costs:** Remove instances when load drops instead of running peak capacity around the clock.
3. **Support availability:** Replace unhealthy instances and maintain a minimum count across multiple failure domains.
4. **Reduce manual intervention:** React to metrics consistently and auditably.
5. **Support fluctuating workloads:** Web/APIs, queue workers, batch processing, and systems with cyclical load.

### 1.3. Limits of Autoscaling

Autoscaling can only react after a signal appears, a policy is evaluated, and new instances finish initializing. If booting a VM and starting the application takes several minutes, the system may breach its SLO before new capacity is ready. Therefore, combine an adequate baseline, headroom, scheduled forecasts, startup optimization, and backpressure.

Autoscaling also does not fix code bugs, slow queries, lock contention, memory leaks, or unavailable downstream services. Adding more instances in those situations can increase pressure on dependencies.

## 2. Reference Architecture for the Lab

This lab uses a simulated web/API service:

- Clients generate HTTPS requests.
- A load balancer distributes requests to an application VM group.
- Each VM runs the same image/template and service version.
- An autoscaling controller monitors metrics and updates desired capacity.
- Monitoring collects infrastructure metrics, application metrics, and scaling events.
- A queue worker group serves as an additional example showing how background-job metrics differ from web/API metrics.

~~~mermaid
flowchart TB
    CLIENT[Client / Load Generator] --> LB[Load Balancer]
    LB --> APP[Application VM Group]
    APP --> DB[(Database)]
    APP --> CACHE[(Cache)]
    APP --> QUEUE[(Job Queue)]
    QUEUE --> WORKER[Worker VM Group]
    AS[Autoscaling Controller] --> APP
    AS --> WORKER
    METRICS[Metrics / Logs / Traces] --> DASH[Dashboard and Alerts]
    LB -. request and target metrics .-> METRICS
    APP -. host and app metrics .-> METRICS
    WORKER -. queue and job metrics .-> METRICS
    AS -. scaling activities .-> METRICS
~~~

In real deployments, the autoscaling controller and monitoring are typically cloud control-plane/managed services. The diagram illustrates the logical flow and does not require building a custom controller.

### 2.1. Scale-Out Flow

1. Traffic or queue depth increases.
2. Metrics exceed the target/threshold across the evaluation window.
3. The scaling policy calculates the additional capacity needed.
4. Desired capacity increases without exceeding max.
5. New VMs are provisioned from the image/template.
6. Instances start agents and the application, then report readiness.
7. Health checks succeed, and the load balancer adds the instances to the backend pool.
8. Dashboards confirm healthy target count rises and latency/errors return to target.

### 2.2. Scale-In Flow

1. Metrics remain below the scale-in threshold long enough.
2. The policy determines how many instances can be removed without falling below min.
3. The system selects eligible instances and starts lifecycle termination/draining.
4. The load balancer stops sending new requests to those instances.
5. Applications finish in-flight requests/jobs, flush logs, and close connections.
6. Instances are terminated/deallocated per group configuration.
7. Dashboards confirm capacity drops while SLOs, healthy target counts, and queue age stay within limits.

## 3. Before Configuring: Understanding the Workload and Goals

Never pick thresholds by guesswork. First understand load behavior, rate of change, startup time, single-instance capacity, and service objectives.

### 3.1. Collecting a Baseline

Measure at least one representative load cycle covering off-peak hours, peak hours, and batch windows if present:

- Requests per second and request mix.
- Concurrent connections and in-flight requests.
- p50, p95, and p99 latency.
- Request success rates, 4xx/5xx rates, and timeouts.
- CPU, memory working set, disk IOPS/latency, and network throughput.
- Thread/worker pool saturation and connection pool wait times.
- Database connections, query latency, locks, and replication lag.
- Queue depth, oldest message age, job duration, and retry counts.
- VM boot time, application bootstrap time, and create-to-healthy-target duration.

An average metric can hide short spikes or tail latency. Observe percentiles, peaks, and per-instance/per-zone distributions rather than relying solely on group-wide averages.

### 3.2. Measuring Safe Single-Instance Throughput

Load-test a single VM with a representative request mix. Record throughput at the point where latency and errors still meet targets. Do not use maximum throughput right before 100% CPU as your rated capacity; leave headroom for bursts, GC, background tasks, and request variance.

Suppose one VM safely handles 120 requests/second with p95 under 250 ms. If the target utilization is 65%, the planning capacity is:

~~~text
Capacity planning per VM = 120 × 0.65
                         = 78 requests/second
~~~

If peak traffic is 780 requests/second:

~~~text
N = ceil(780 / 78)
  = 10 VMs
~~~

This is an initial estimate. Add capacity for zone failures, deployment surges, autoscaling reaction time, and downstream constraints.

### 3.3. Defining SLOs and Scaling Targets

Example internal SLOs for an API:

- Request-success availability: 99.9% over a monthly window.
- p95 latency: under 250 ms at target load.
- p99 latency: under 600 ms at target load.
- System error rate: under 0.5%.
- Healthy application targets: always at least 2 across two zones.
- Queue workers: oldest message age under 60 seconds under normal conditions.

These are hypothetical numbers for the lab. Real systems must select SLOs driven by business requirements rather than copying illustrative thresholds.

## 4. Choosing Metrics to Trigger Autoscaling

A good metric reflects capacity demand and correlates with the bottleneck. It needs a fast enough collection interval, low noise, and the ability to distinguish genuine load from dependency outages.

### 4.1. CPU Utilization

CPU suits CPU-bound workloads such as encryption, computation, compression, image processing, or logic-heavy APIs. For example, target tracking keeps group average CPU around 60%.

Limitations:

- Requests waiting on databases/networks keep CPU low despite high latency.
- Group-average CPU can mask a single hot instance.
- CPU can spike from background tasks unrelated to incoming requests.
- Scaling out can raise total CPU as instances are added, even as per-instance CPU drops.

Monitor CPU per instance and per group, and compare against throughput and latency.

### 4.2. Request Count per Target

For web/API workloads behind a load balancer, requests per target often track processing demand closer than CPU. For example, a target of 300 requests/second per healthy target, validated via load testing.

Ensure the metric counts targets actually receiving traffic and aligns with request types. A lightweight cache read and a heavy report generation request do not cost the same; if the request mix shifts, raw request count alone may be insufficient.

### 4.3. Concurrent Connections and In-Flight Requests

Useful for WebSockets, long polling, streaming, long-running API requests, or high-concurrency workloads. Pair with latency and connection pool metrics to avoid scaling merely due to idle connections.

### 4.4. Memory Utilization

Memory suits JVMs, large-heap runtimes, in-process caches, or OOM-prone workloads. However, memory is not always a default hypervisor metric; a guest OS agent or custom metric may be required.

Distinguish allocated memory, working set, caches/buffers, swap, and memory pressure. Do not scale merely because the OS uses RAM for filesystem cache if the workload can safely reclaim that cache.

### 4.5. Queue Depth and Oldest Message Age

For background workers, queue depth shows how many jobs are waiting; oldest message age shows how long the oldest job has waited. Age often reflects user impact better than depth when job durations vary.

Example:

- Scale out when oldest message age exceeds 30 seconds across 3 consecutive evaluations.
- Maintain at least 2 workers.
- Scale in when the queue is nearly empty and no jobs are running over a stabilization period.

Account for per-worker throughput, visibility timeouts, retries, and downstream concurrency limits.

### 4.6. Latency and Error Rate Metrics

p95/p99 latency is a critical signal confirming SLO pressure. Latency can serve as a secondary or custom metric, but root causes must be filtered:

- If latency rises due to insufficient application capacity, scaling out can help.
- If latency rises due to a slow database, adding API VMs increases query volume and overloads the DB further.
- If error rates rise due to a dependency outage, scaling out is not the fix.

Do not use error rate as a sole scale-out trigger. Combine dependency health, saturation, request rates, and circuit breakers.

### 4.7. Metric Selection Table by Workload

| Workload | Primary metric | Confirming metrics | Risks to control |
|---|---|---|---|
| CPU-bound Web/API | CPU/instance or requests/target | p95/p99, error rate | Group CPU average hides hotspots |
| I/O-bound API | In-flight requests or requests/target | Dependency latency, connection wait | Scaling increases database load |
| WebSocket/streaming | Concurrent connections | Network throughput, memory | Connections do not always equal active request work |
| Memory-heavy JVM/service | Memory pressure/working set | GC pauses, OOM, latency | Guest metrics require an agent |
| Queue worker | Oldest message age or queue depth | Job duration, retries, busy workers | Rapid worker growth overloads downstream |
| Batch/HPC worker | Pending task count, scheduler backlog | Job completion time, CPU/GPU | Long jobs require checkpointing and draining |

## 5. Designing Scaling Policies

A scaling policy defines which metric is tracked, the target or threshold, the capacity change step, and the evaluation window. Policies must have separately engineered scale-out and scale-in behavior; avoid using a single threshold that makes the group oscillate up and down around a boundary.

### 5.1. Target Tracking

Target tracking attempts to keep a metric near a target value. Examples:

- Group average CPU target of 60%.
- Request count per target of 300 requests/second.
- Queue worker target of 20 pending messages per worker.

The controller observes the metric and calculates how many instances to add or remove. This is usually the simplest starting option for workloads with a relatively stable relationship between capacity and the metric.

Notes:

- Choose a metric that responds predictably as instances are added or removed.
- Do not place the target right next to the saturation point.
- Allow warm-up time so metrics are not misinterpreted right as new instances boot.
- Avoid having multiple independent policies control the same group without understanding how they interact.

### 5.2. Step Scaling

Step scaling divides a metric into ranges and changes capacity proportionally to how far the threshold is breached. Example for average CPU:

| Average CPU in evaluation window | Illustrative action |
|---:|---|
| 60–70% | Add 1 VM |
| Over 70–85% | Add 2 VMs |
| Over 85% | Add 4 VMs and trigger capacity alert |
| 35–45% | May remove 1 VM if all other scale-in conditions pass |
| Under 35% | May remove 2 VMs if group retains min/headroom |

The ranges above only illustrate tiered scaling. Benchmark metric delay, boot speed, and the impact of each scaling step. When metrics surge rapidly, step scaling can react faster than adding one VM at a time, though it can also create large capacity surges.

### 5.3. Simple Scaling and Cooldown

Simple scaling typically executes a fixed action when an alarm changes state, followed by a cooldown to avoid continuous triggers. This model is easy to understand but less flexible than target tracking/step scaling for volatile workloads.

Cooldown is not an identical mandatory pause after every scale action across all platforms. Each cloud has distinct semantics for cooldown, warm-up, instance initialization, and policy evaluation. Read the exact service documentation before mapping configurations across providers.

### 5.4. Scheduled Scaling

If load follows predictable cycles, add capacity before peak hours:

- Increase min/desired capacity before opening hours.
- Hold capacity through the peak period.
- Lower the baseline after load subsides.

Scheduled scaling avoids waiting for metrics to breach thresholds before booting VMs. Do not schedule a capacity drop right at closing time if long requests, queue backlogs, or post-peak traffic remain.

### 5.5. Predictive Scaling

Predictive scaling uses historical data to forecast demand and pre-provision capacity. It fits only when patterns repeat reliably, metric quality is solid, and workloads do not shift abruptly. Forecasting does not replace reactive scaling because unexpected events can still occur.

### 5.6. Combining Policies

A common configuration:

- Scheduled/predictive scaling prepares the baseline ahead of peak hours.
- Target tracking keeps metrics near target during normal operations.
- Step scaling handles major spikes or urgent queue backlogs.
- Health-based replacement maintains healthy instance counts when VMs fail.

Prevent conflicting policies—such as scheduled scaling setting a low desired count while target tracking needs to scale up. Clearly document which policy modifies min, desired, or max, and the precedence when multiple signals fire together.

## 6. Min, Desired, Max, and Headroom

A VM group typically has three capacity parameters:

- **Min capacity:** Minimum number of instances maintained.
- **Desired capacity:** Number of instances the controller currently aims to maintain.
- **Max capacity:** Upper bound of the group.

### 6.1. Choosing Min Capacity

Min must cover baseline load and availability requirements. For production services needing to tolerate a single VM failure, `min=1` is usually insufficient. When serving across two zones, ensure enough instances remain in the surviving zone if one zone fails.

For example, a group with min 4 VMs distributed across two zones. Do not look only at the total of 4; check placement policies and how many instances survive if one zone is lost.

### 6.2. Choosing Max Capacity

Max must be based on:

- Expected peak demand and bursts.
- vCPU/GPU quotas per account/subscription/project and region/family.
- Capacity reservations or SKU availability in the zone.
- Subnet IPs, NICs, load balancer targets, and API limits.
- Database connections, cache throughput, and downstream rate limits.
- Budget and cost limits.

Setting max too low prevents autoscaling from serving peaks. Setting max too high risks huge bills or overwhelming databases/queue consumers.

### 6.3. Initial Desired Capacity

Initial desired capacity must cover the baseline before autoscaling can react. If a group starts with one VM while baseline traffic already requires four VMs, the system will continuously breach SLOs while scaling out.

### 6.4. Headroom and N-1 Capacity

Headroom is spare capacity reserved to absorb bursts, instance failures, boot times, and deployments. In multi-zone architectures, verify N-1 capacity: after losing one zone or a portion of instances, do the remaining VMs still meet minimum load?

For example, 12 VMs split evenly across two zones, each safely handling 80 requests/second at target utilization. If one zone is lost, 6 VMs remain:

~~~text
Capacity after zone failure = 6 × 80 = 480 requests/second
~~~

If critical load requires 700 requests/second, the current baseline fails N-1. Increase the baseline, optimize throughput, spread across more zones, or define a degraded mode. Post-failure autoscaling does not guarantee sufficient capacity if another zone lacks hosts or quota.

## 7. Warm-Up, Cooldown, and Oscillation Prevention

A newly launched VM does not immediately become usable capacity. It must be provisioned, boot, fetch configuration, start the application, warm caches, and pass readiness.

### 7.1. Instance Warm-Up

Warm-up is the period after an instance launches during which its metrics should not yet count as steady-state group metrics or the instance should not yet factor into subsequent scale decisions, depending on autoscaler semantics.

During warm-up:

- Do not count the new instance as a healthy backend before readiness passes.
- Do not interpret low CPU while the app is not yet receiving traffic as excess group capacity.
- Avoid triggering additional batches merely because new instances have not started taking requests yet.
- Track create-to-running, running-to-ready, and ready-to-first-request durations separately.

Warm-up should be measured empirically. Do not pick an arbitrarily huge value that slows controller responsiveness, nor one too short that causes continuous scaling.

### 7.2. Cooldown and Stabilization Windows

Cooldown/stabilization prevents the controller from reacting to short fluctuations. For example, scale down capacity only when a metric stays below threshold for 10 consecutive minutes rather than immediately when CPU dips for one minute.

Scale-out and scale-in may require different timings:

- Scale-out prioritizes fast enough reaction to protect SLOs.
- Scale-in is more conservative to avoid removing capacity right before another load wave.

### 7.3. Hysteresis

Hysteresis uses separate thresholds for scale-out and scale-in. Example:

- Scale out when CPU exceeds 65% for 3 minutes.
- Consider scale-in only when CPU stays below 35% for 10 minutes.

The gap between the two thresholds reduces oscillation when a metric fluctuates around one point. Choose thresholds from measured baselines and loads rather than treating 65/35 as a universal standard.

### 7.4. Limiting Rate of Change

Cap the number of VMs added or removed per interval if supported by the platform. This shields downstream systems from sudden connection surges and gives operators time to observe. However, overly tight caps can prevent scale-out from keeping pace with bursts.

## 8. Health Checks and Safe Scale-In

Autoscaling must coordinate with the load balancer and application lifecycle. Instances should receive traffic only when ready, and should be removed only after stopping acceptance of new work.

### 8.1. Distinguishing Liveness, Readiness, and Target Health

- **Liveness:** Whether the process is still running or stuck in an unrecoverable state.
- **Readiness:** Whether the application has finished initializing and can serve assigned requests.
- **Load balancer target health:** The load balancer's check deciding whether to send traffic to an instance.
- **Auto-repair health:** The signal used to replace unhealthy instances inside a VM group.

Not all health checks need to be identical. Overly sensitive liveness checks can trigger restart loops; readiness depending on every dependency can remove the entire group during a shared database outage.

### 8.2. Graceful Shutdown

Upon receiving a termination signal, the application should:

1. Mark readiness false or instruct the load balancer to stop sending new requests.
2. Stop pulling new jobs from queues.
3. Finish in-flight requests within a bounded timeout.
4. Commit/checkpoint or return job leases to the queue.
5. Flush logs/metrics and close connections.
6. Exit the process before the termination deadline.

If requests take longer than the termination grace period, implement checkpointing, retries, or offload work to queues; you cannot simply raise timeouts indefinitely.

### 8.3. Connection Draining

The load balancer needs a drain window long enough for open requests and connections. Set drain timeouts based on request duration distributions and protocol types. WebSockets/streaming may require separate reconnect mechanisms.

### 8.4. Scale-In Protection and Lifecycle Hooks

For stateful workloads or long jobs, use scale-in protection, lifecycle hooks, or equivalent mechanisms to defer termination while an instance still holds work. Include a hard deadline and timeout mechanism so instances are not kept alive forever.

Do not enable protection indefinitely on every instance; that prevents the group from scaling in and drives uncontrolled costs.

### 8.5. Selecting Instances for Termination

Where possible, prefer terminating instances with fewer active sessions/connections/jobs or those matching placement/age policies. However, instance selection algorithms depend on the platform. Applications must still tolerate any instance being replaced.

## 9. Multi-Tier Autoscaling Configuration

A system may contain multiple independent VM groups. Each group must scale on signals aligned with its responsibilities.

### 9.1. Web/API Group

Suggested metrics:

- Request count per target.
- Concurrent connections.
- Per-instance CPU/memory.
- p95/p99 latency and error rate as confirming metrics.

Set min to maintain HA, and max based on quotas and database connection limits. Calculate maximum total connection pools:

~~~text
Max database connections from app
= Max application VMs × connection pool per VM
~~~

If group max is 30 VMs and each VM opens a pool of up to 40 connections, the database could face up to 1,200 connections from the application tier alone. Cap pools or use appropriate proxies/pooling so autoscaling does not turn into a connection storm.

### 9.2. Worker Group

Workers should scale on queue backlog, oldest message age, or active job counts. Do not use CPU as the sole signal if jobs spend long periods waiting on I/O.

Set per-worker concurrency, max workers, and downstream rate limits. When the queue empties, scale in only after no jobs are running or leases can be safely returned.

### 9.3. Databases and Caches

Databases generally should not scale under the same policy as application VMs. Expanding application capacity can grow connection/query volume faster than the database can absorb. Use connection limits, pooling, backpressure, caching, and read replicas under a separate strategy.

Caches may require more memory or sharding when the working set exceeds capacity. Dropping cache hit ratios may signal changes in capacity, TTL, or key distribution—not necessarily a need for more API VMs.

### 9.4. Scaling Order and Backpressure

If both applications and workers scale up together, verify downstream capacity:

- Does the database have sufficient connections and IOPS?
- Does the queue have publish/consume limits?
- Do external APIs enforce rate limits?
- Can the cache absorb connection churn?
- Do networks/NATs have sufficient connections/throughput?

When downstream saturates, lowering concurrency or enabling backpressure can be safer than scaling out further. Autoscaling should work alongside rate limiting, circuit breakers, and queue buffering.

## 10. Observing Autoscaling

Observability for autoscaling must answer four questions:

1. **Why did it scale?** Which metric triggered the policy and how did its value change?
2. **What did the controller do?** How did desired capacity, scaling activities, and API errors change?
3. **Is the new capacity useful yet?** How many instances are healthy and serving traffic?
4. **What was the service outcome?** Did latency, errors, queue age, availability, and costs improve?

Merely seeing VM counts rise does not prove autoscaling succeeded. Correlate scaling events with application metrics and user experience.

### 10.1. Infrastructure Metrics

- Current, desired, min, and max instance counts.
- Instance states per zone: pending, running, healthy, draining, terminating, unhealthy.
- Per-instance CPU, memory pressure, disk latency/IOPS, and network throughput.
- Create-to-running, running-to-ready, and ready-to-first-request durations.
- Scaling activities: policy, reason, old/new desired capacity, activity outcome.
- Quota usage, allocation failures, subnet IPs, and API throttling.

### 10.2. Load Balancer Metrics

- Request count and requests/target.
- Healthy/unhealthy target counts.
- Active/new connections.
- Backend response time or target latency.
- 4xx/5xx counts, timeouts, and rejected connections.
- Connection draining duration and deregistration events if provided by the platform.

### 10.3. Application and Dependency Metrics

- Request rate, success/error rates, and p50/p95/p99 latency.
- In-flight requests, thread pools, worker pools, and queue waits.
- Database connection pool waits, active connections, query latency, and locks.
- Cache hit ratios, evictions, and memory pressure.
- Queue depth, oldest message age, job duration, retries, and dead-letter counts.
- External dependency latency, timeouts, and rate-limit responses.

### 10.4. Logs and Traces

Logs should include timestamp, service, environment, instance ID, zone, deployment version, trace/correlation ID, and event type. Record lifecycle events such as startup completion, readiness pass/fail, drain start/end, and shutdown reason.

Distributed traces help pinpoint whether latency rose at the edge, web tier, application, database, or external dependencies. When new instances scale out, traces reveal whether traffic actually balances evenly or one target still absorbs most requests.

Never log passwords, access tokens, session cookies, or sensitive payloads. Use centralized logging because local logs disappear when instances terminate.

### 10.5. Minimal Operational Dashboard

An operational dashboard should include these rows:

| Row | Charts | Question |
|---|---|---|
| User impact | Request rate, success/errors, p95/p99 latency | Are users being affected? |
| Capacity | Desired/current/min/max and healthy targets | Is there enough actual capacity? |
| Scaling | Scaling activities, trigger metrics, cooldown/warm-up | Why did the group change? |
| Host | Per-instance CPU, memory, disk, network | Which resource is the bottleneck? |
| Dependency | DB connections/latency, cache hits, queue age | Did scaling overload downstream? |
| Cost | Instance-hours, VM types, scale-out/in events | Is capacity used efficiently? |

Align trigger metrics, scaling activities, healthy target counts, and latency on the same timeline to compare before and after each scaling event.

### 10.6. Actionable Alerts

| Alert | Illustrative condition | Initial action |
|---|---|---|
| Missing healthy targets | Healthy count below min for several minutes | Check health checks, startup, quotas, and allocation |
| Group at max | Desired capacity equals max while metric stays above target | Check max/quotas/capacity and downstream |
| Scale-out failure | Activity reports insufficient capacity/quota/API error | Identify error scope, zone/SKU, and retry policy |
| Scale thrashing | Repeated scale-out and scale-in within a short window | Check hysteresis, evaluation window, and metric noise |
| Latency breaching SLO | p95/p99 continuously above threshold | Identify bottleneck; do not blindly add VMs |
| Growing queue backlog | Oldest message age exceeds SLO | Check worker capacity and downstream rate limits |
| Saturated connection pool | Pool waits/timeouts rising | Check DB capacity, pool sizes, and concurrency |
| Excessive drain duration | Drain duration exceeds threshold | Check long requests/jobs, shutdown hooks, and grace periods |

Alerts should specify severity, owner, dashboard, runbook, and first diagnostic step. Avoid alerting solely on a few seconds of elevated CPU without service impact.

## 11. Conceptual Policy Configuration Example

The YAML example below describes configuration intent for an application VM group. This is a provider-agnostic illustrative structure, not a manifest directly executable via AWS, Azure, or Google Cloud CLI/APIs.

~~~yaml
service:
  name: orders-api
  tier: application

vmGroup:
  zones:
    - zone-a
    - zone-b
  minCapacity: 4
  desiredCapacity: 4
  maxCapacity: 20
  instanceTemplate: orders-api-image-v12
  loadBalancerTarget: orders-api-targets

scaling:
  metric:
    name: requests_per_healthy_target
    target: 300
    unit: requests_per_second
  evaluation:
    period: 60s
    scaleOutDatapoints: 2
    scaleInDatapoints: 10
  behavior:
    scaleOut:
      warmup: 180s
      maxStep: 4
    scaleIn:
      stabilizationWindow: 600s
      maxStep: 1
      requireHealthyCapacity: true
  scheduled:
    - time: "08:45"
      desiredCapacity: 8
    - time: "20:30"
      desiredCapacity: 4

health:
  startupProbe: /startup
  readinessProbe: /ready
  loadBalancerDrain: 90s
  terminationGracePeriod: 120s

observability:
  dimensions:
    - service
    - environment
    - instance_id
    - zone
    - deployment_version
  alerts:
    - no_healthy_targets
    - group_at_max_capacity
    - scaling_activity_failed
    - p95_latency_breaches_slo
~~~

Values like 300 requests/second, 180s warm-up, 600s stabilization, and 90s drain are examples only. Replace them with benchmark measurements, request durations, startup times, SLOs, and actual platform semantics.

### 11.1. Mapping Points Across Cloud Providers

| Concept | AWS | Azure | Google Cloud |
|---|---|---|---|
| VM group | EC2 Auto Scaling group | Virtual Machine Scale Set | Managed Instance Group |
| Template | Launch template | VM/scale set model | Instance template |
| Scale metric | CloudWatch metric/alarm or integrated metric | Azure Monitor metric/alert | Cloud Monitoring metric |
| Scale policy | Target tracking, step, scheduled | Autoscale rules, schedule | Autoscaler policy, schedule |
| Load balancer health | Target group health check | Load Balancer/Backend health probe | Backend service health check |
| Activity history | Scaling activities/CloudTrail/CloudWatch | Activity Log/Autoscale history | Instance group operations/Audit Logs |

Feature names, limits, and configuration mechanics vary by group type, region, and service. Consult official provider documentation when translating conceptual settings into real resources.

## 12. Lab: Configuring and Observing Scale-Out/Scale-In

### 12.1. Lab Objective

Create an application VM group behind a load balancer, enable autoscaling on request count or CPU, generate controlled load, observe capacity increasing, stop load, and observe capacity decreasing. Never use a production account or workloads holding critical data.

### 12.2. Prerequisites

- Sandbox permissions to create VMs, VM groups, load balancers, monitoring metrics, and scaling policies.
- An image/template pre-installed with a sample web/API application and monitoring agent if custom metrics are needed.
- Subnets across at least two zones with enough IP addresses for max capacity.
- Health/readiness endpoints and access logs configured.
- A load generator running independently of the VM group under test.
- Appropriate budget/quotas and an explicit max instance limit.

### 12.3. Initial Configuration

Example:

| Parameter | Lab value |
|---|---:|
| Min capacity | 2 VMs |
| Desired capacity | 2 VMs |
| Max capacity | 8 VMs |
| Zones | 2 zones |
| Scale-out target | 200 requests/second/healthy target |
| Evaluation period | 60 seconds |
| Scale-in stabilization | 10 minutes |
| Estimated warm-up | 3 minutes |
| Drain timeout | 90 seconds |

Adjust thresholds if VMs are smaller/larger, startup differs, or the request mix is heavier. Ensure max 8 VMs stays within quotas and the database connection budget.

### 12.4. Execution Steps

1. **Create VM template:** Use an image with a fixed application version, metric/log agents, and an idempotent startup script.
2. **Create load balancer:** Configure listener, backend group, health checks, and timeouts.
3. **Create VM group:** Set min=2, desired=2, max=8; distribute instances across two zones.
4. **Register backends:** Admit instances to the pool only after readiness/health checks pass.
5. **Create scaling policy:** Pick request count per healthy target as the primary metric; use CPU as a confirming metric.
6. **Configure scale-in:** Set stabilization window, drain timeout, and graceful shutdown.
7. **Build dashboard:** Display request rate, requests/target, CPU, latency, errors, desired/current capacity, healthy target count, and scaling activities.
8. **Verify baseline:** Send low load for several minutes, confirming the group stays steady at 2 VMs with no alerts.
9. **Ramp load in steps:** Increase concurrency or request rate every 2–3 minutes; do not jump straight to maximum load.
10. **Observe scale-out:** Record when the metric crosses target, policy triggers, instances launch, readiness passes, and the first request is served.
11. **Hold steady-state:** Maintain load at the elevated level long enough for metrics and latency to stabilize.
12. **Ramp load down gradually:** Lower the request rate back to baseline, then stop the load generator.
13. **Observe scale-in:** Track stabilization, draining, termination, and healthy capacity after each decrement.
14. **Final check:** Confirm the group returns to baseline, SLOs hold, no requests/jobs were dropped, and no orphaned lab instances or disks remain.

### 12.5. Results Recording Table

| Milestone | Applied load | Desired VMs | Healthy VMs | p95 latency | CPU/VM | Notes |
|---|---:|---:|---:|---:|---:|---|
| Baseline | 100 req/s | 2 | 2 | Record measurement | Record measurement | Initial state |
| Ramp 1 | 250 req/s | Record measurement | Record measurement | Record measurement | Record measurement | Metric starts rising |
| Ramp 2 | 450 req/s | Record measurement | Record measurement | Record measurement | Record measurement | Check scale-out |
| Peak | 700 req/s | Record measurement | Record measurement | Record measurement | Record measurement | Hold steady load |
| Ramp down | 250 req/s | Record measurement | Record measurement | Record measurement | Record measurement | Observe stabilization |
| Baseline | 100 req/s | Record measurement | Record measurement | Record measurement | Record measurement | Confirm scale-in |

Never enter fabricated measurements into lab reports. Record timestamps and dashboard screenshots/links for each milestone to correlate with scaling activities.

### 12.6. Lab Acceptance Criteria

- The group never drops below min or exceeds max.
- New instances receive traffic only after passing healthy/readiness checks.
- Scale-out occurs when metrics breach target according to policy.
- After scale-out, requests/target or CPU settles back into the stable range.
- p95/p99 and error rates do not sustain SLO breaches.
- When load drops, the group does not immediately scale in or oscillate continuously.
- Removed instances are drained; no requests/jobs are severed or duplicated.
- The dashboard explains why scaling happened and what changed afterward.
- Scaling activities show no quota, capacity, subnet IP, or API throttling errors.

## 13. Practicing Reading Dashboards and Timelines

A good analysis practice is constructing a unified timeline:

| Time | Event | Metrics to inspect | Question |
|---|---|---|---|
| T0 | Load starts rising | Request rate, CPU, latency | Where is the load increase coming from? |
| T1 | Target exceeded | Trigger metric, evaluation window | Has the policy met trigger conditions? |
| T2 | Desired increases | Scaling activity, quotas, API result | How many additional VMs did the controller request? |
| T3 | VMs created | Pending/running, boot duration | Is provisioning slow or failing? |
| T4 | Readiness passes | Healthy target count | Are the VMs truly ready? |
| T5 | Latency recovers | p95/p99, errors, requests/target | Did new capacity resolve the bottleneck? |
| T6 | Load drops | Metrics, stabilization timer | Is scale-in eligible yet? |
| T7 | Drain/terminate | Active connections, in-flight jobs | Were any requests or jobs lost? |
| T8 | Returns to baseline | Current/desired, SLOs, cost | Is the group stable and more cost-efficient? |

### 13.1. Calculating Scale-Out Delay

Measure the time from when a metric crosses the threshold until the new instance begins serving requests:

~~~text
Scale-out delay
= policy evaluation delay
  + provisioning time
  + guest boot and bootstrap time
  + application startup time
  + readiness and load balancer registration time
~~~

For example, measuring 60s evaluation, 45s provisioning, 50s boot/bootstrap, 35s application startup, and 20s readiness/registration:

~~~text
Scale-out delay = 60 + 45 + 50 + 35 + 20
                = 210 seconds
                = 3 minutes 30 seconds
~~~

During this window, existing instances must absorb the increased load. If headroom is insufficient, raise the baseline, reduce startup time, use a warm pool, or apply scheduled/predictive scaling.

### 13.2. Calculating Scale-In Duration

Scale-in can take longer than scale-out due to stabilization, instance selection, request draining, and termination:

~~~text
Scale-in completion
= stabilization window
  + target deregistration/drain
  + graceful shutdown
  + provider termination time
~~~

This is an observational timing for planning, not a provider SLA. Distinguish policy wait times from actual lifecycle execution times.

### 13.3. Comparing Before and After Scaling

Do not compare only CPU before and after. Compare:

- Total throughput and throughput/instance.
- p95/p99 latency.
- Error/timeout rates.
- Requests/target and active connections.
- DB connection/query latency.
- Queue age/job completion.
- Instance-hours and cost per successful request.

If adding VMs fails to improve latency, look for another bottleneck instead of continuing to raise max capacity.

## 14. Troubleshooting: When Autoscaling Does Not Behave as Expected

### 14.1. Metric Exceeds Threshold but Desired Capacity Does Not Rise

Check in order:

1. Is the metric collected under the right namespace, dimensions, unit, and period?
2. Have enough datapoints arrived in the alarm/evaluation window?
3. Is the scaling policy disabled, suspended, or overridden by another schedule?
4. Is the group already at max capacity?
5. Are quotas, policies, IAM permissions, or API rate limits blocking the action?
6. Is the metric missing data or using an unsuitable statistic?
7. Does scaling activity history report a specific reason/error?

Do not blindly raise max before knowing the cause. If the failure stems from missing permissions or misconfigured metrics, raising max will not help.

### 14.2. Desired Increases but No New Instances Launch

Common causes:

- vCPU/GPU or instance-family quota exhausted.
- Zone/SKU out of capacity.
- Subnet out of IP addresses.
- Template references a deleted image or wrong version.
- IAM/instance profile lacks permissions.
- Incompatible disk, NIC, placement group, or accelerator.
- Provider API throttling.

Cross-check scaling activities, compute provisioning events, audit logs, and quota usage. If a zone lacks capacity, consider multiple equivalent instance types or additional zones if the workload permits.

### 14.3. Instance Runs but Never Becomes Healthy

Check:

- Did the startup script fail or take too long?
- Are secrets/configs/identities reachable?
- Is the application binding to the right interface/port?
- Do security groups/firewalls permit health checks?
- Is the health endpoint timing out or blocked on a database/cache?
- Is the runtime hitting OOM, crash loops, or certificate errors?
- Are clocks/DNS/networking valid?

Never just raise the health check timeout to hide a broken startup. Use startup logs and readiness reasons to find the root cause.

### 14.4. Group Scales Out Repeatedly Without Lowering Latency

The bottleneck likely lies outside the VMs:

- Database queries/locks or saturated connection pools.
- Sudden surge in cache misses.
- External API rate limiting.
- Network/NAT/egress congestion.
- One shard/partition receiving most traffic.
- Requests serialized on a shared lock or single-threaded worker.

Action: limit concurrency, enable backpressure, optimize queries/caches, balance load, or scale dependencies under a separate policy. Do not keep blindly scaling the application group.

### 14.5. Scale-In Does Not Happen

Check:

- Has the metric remained below threshold long enough?
- Are stabilization/cooldown timers still active?
- Has min capacity already been reached?
- Are scale-in protection or incomplete lifecycle hooks holding instances?
- Is a scheduled policy holding desired high?
- Does the group have placement or zone-distribution constraints?
- Do instances hold long sessions/jobs or fail draining?

If instances remain protected indefinitely, follow a runbook to release protection safely instead of force-terminating.

### 14.6. Immediate Scale-Out After Scale-In

This indicates oscillation/thrashing. Possible causes:

- Scale-in threshold is too close to the scale-out threshold.
- Evaluation window is too short.
- Metric is noisy or skewed by warm-up.
- Traffic exhibits repeated short bursts.
- Scale-in concentrates load onto remaining instances, pushing the metric back over target.

Fix with hysteresis, longer scale-in stabilization, smaller step sizes, an appropriate minimum capacity, and per-instance metric inspection.

## 15. Common Design Mistakes

| Mistake | Impact | Remediation |
|---|---|---|
| Scaling solely on CPU | Misses I/O or queue bottlenecks | Select workload-aligned metrics and measure dependencies |
| Using group-average CPU | One instance can overload while average looks low | Monitor per-instance metrics and requests/target |
| Scaling out too late | SLOs breach before new VMs become ready | Maintain headroom, warm pools, or scheduled scaling |
| Scaling in too aggressively | Severs requests/jobs, triggers thrashing | Use stabilization, draining, and graceful shutdown |
| Min capacity too low | Insufficient HA or baseline | Calculate baseline and N-1 capacity |
| Unbounded max capacity | Large bills, DB connection storms | Cap max per quotas, budget, and downstream limits |
| Ignoring quotas/zones | Desired rises while provisioning fails | Track quotas, SKU availability, and subnet IPs |
| Shallow readiness checks | Instances receive traffic before ready | Verify genuine application readiness |
| Readiness depending on every dependency | One shared outage removes all targets | Check only mandatory request-serving dependencies |
| No scaling activity dashboard | Cannot explain why scaling occurred | Correlate metrics, policy events, and capacity |
| Not measuring startup time | Misconfigured warm-up/cooldown | Measure every create-to-ready stage |
| Scaling workers only on queue depth | Adds workers while jobs block downstream | Combine oldest age, busy workers, and dependency health |
| Scaling APIs when DB slows down | Overloads the database further | Use pooling, rate limits, caching, and backpressure |
| Not separating 4xx from 5xx | Scales on client errors needing no capacity | Classify errors by source and impact |
| Mixing metrics across environments | Load tests trigger production policies | Isolate dimensions and alarms per environment |

## 16. Autoscaling Security and Governance

Autoscaling automatically creates and deletes resources, so permissions and auditing must be designed upfront.

### 16.1. Least Privilege

- The scaling controller may modify only its designated VM group and associated resources.
- Instance roles may read only required configs/secrets and emit required metrics/logs.
- Load generators must never use cloud administrative credentials.
- Operators may view scaling activities; permission to change max capacity should be controlled.
- Separate deployment, runtime, and audit permissions.

### 16.2. Images and Bootstrapping

Images must be scanned, hardened, and versioned. Startup scripts must be idempotent and never write secrets into logs or easily accessible user data. Fetch secrets from a secret manager using short-lived identities.

Avoid downloading unpinned packages from the Internet on every VM boot if it destabilizes startup. Prefer tested images/artifacts and trusted repositories.

### 16.3. Auditing and Traceability

Record:

- Who modified min/max or scaling policies.
- Which policy version was applied.
- Which metric/alarm triggered.
- Desired capacity before and after.
- Instance IDs, zones, image versions, and create/delete timestamps.
- Activity failures, permission denials, and quota errors.

Combine cloud audit logs with deployment logs and application events to reconstruct timelines.

## 17. Autoscaling Cost and Efficiency

Autoscaling optimizes cost when capacity tracks demand without sacrificing SLOs. Do not evaluate success solely by the number of VMs scaled in.

### 17.1. Cost Components

- VM instance-hours and instance types.
- Idle boot/warm pool capacity.
- Disk, snapshot, and image storage.
- Load balancers, NATs, public IPs, and network egress.
- Cross-zone data transfer.
- Monitoring metrics, log ingestion, retention, and traces.
- Database/cache/queue capacity scaling alongside application scale.
- Licensing and support plans.

### 17.2. Efficiency Metrics

- Cost per successful request.
- Cost per completed job.
- Average/peak instance count.
- Idle capacity ratio.
- Scale-out frequency and scale-in frequency.
- Time spent at max capacity.
- Failed request/job rate during scaling transitions.

If scaling in saves 20% of VM-hours yet doubles timeouts or retries, total operational cost may rise. Weigh cost against service quality and downstream expenses.

### 17.3. Setting Min/Max Based on Budget

Set budget alerts and max capacity caps. Scheduled scaling can be used in non-production environments, but shut down VMs only when data and jobs can be recovered cleanly. Do not scale in or stop databases solely because business hours ended if background work continues.

### 17.4. Spot/Interruptible Capacity

Stateless workers with checkpointing and retries can use Spot/interruptible VMs to lower costs. Do not rely solely on interruptible capacity as the baseline for high-availability workloads. Maintain fallback capacity, queue retries, and interruption-event monitoring.

## 18. Extending the Lab: Test Scenarios

Run only inside an authorized sandbox. Never intentionally overload production or shared dependencies.

### 18.1. Short Burst Test

- Ramp load rapidly to 3x baseline within 1–2 minutes.
- Record when metrics cross target, desired rises, and healthy targets increase.
- Inspect p95/p99 while new VMs boot.
- Determine whether headroom absorbed the burst.

### 18.2. Sustained Load Test

- Hold high load for 15–30 minutes.
- Confirm the group stabilizes without launching instances continuously.
- Monitor CPU/memory, connection pools, and database latency.
- Confirm the policy does not exceed max.

### 18.3. Load Reduction Test

- Step down load, then stop it completely.
- Track stabilization and when scale-in begins.
- Verify instances drain before termination.
- Confirm the group does not drop below min.

### 18.4. Instance Failure Test

- In the lab environment, intentionally terminate one VM.
- Confirm the load balancer removes the unhealthy target.
- Confirm the group replaces the instance if required by health policy.
- Measure replacement duration and request errors.

### 18.5. Dependency Bottleneck Test

- Use a test stub or isolated environment to inject simulated database latency.
- Observe CPU, application latency, connection waits, and errors.
- Confirm autoscaling does not expand unboundedly when the DB is the bottleneck.
- Test rate limiting/backpressure and compare results.

### 18.6. Quota/Capacity Limit Test

- Set a low group max in the lab or use a quota-limited sandbox.
- Confirm the group-at-max alert fires.
- Confirm scaling activities state a clear reason.
- Verify the application degrades gracefully or queues hold backlogs safely.
- Never exhaust quotas shared with critical workloads.

## 19. Practice Exercises

### Exercise 1: Selecting Metrics

An API shows 35% average CPU, p95 rising from 180 ms to 900 ms, sharply increasing database connection wait times, and unchanged request rate. Should you immediately add application VMs?

**Hint:** Do not scale out solely on latency. Inspect database connection pools, query latency, locks, and DB limits. Adding VMs can increase connection count and worsen the problem.

### Exercise 2: Calculating Capacity

One instance safely processes 90 requests/second. Target utilization is 60%. Peak load is 540 requests/second. Calculate the minimum instance count based on throughput.

~~~text
Capacity planning per VM = 90 × 0.60 = 54 req/s
N = ceil(540 / 54) = 10 VMs
~~~

Then add headroom for zone failure and deployment surges. Do not treat 10 VMs as the final production figure if N-1 requirements are not yet satisfied.

### Exercise 3: Safe Scale-In

Workers process jobs averaging 4 minutes. Scale-in stabilization is 2 minutes and termination grace period is 60 seconds. Is this configuration sufficient to guarantee job completion?

**Hint:** No, it cannot be assumed sufficient. Jobs outlast the grace period; you must stop pulling new jobs, checkpoint, or return leases to the queue. You may extend the grace period within platform limits, but that does not replace job recovery mechanisms.

### Exercise 4: Group at Max

Desired capacity equals max at 20 VMs, requests/target remain high, and p99 breaches SLO. List the investigation steps.

**Hint:** Inspect healthy target count, quotas, zone capacity, startup times, request distribution, per-VM CPU/memory, database/cache/network bottlenecks, and budget. Increase max only after confirming downstream services and quotas can handle the load.

### Exercise 5: Detecting Thrashing

A group repeatedly scales from 4 to 6 VMs and back down to 4 in 5-minute cycles. Name three causes and fixes.

**Hint:** Thresholds too close together, evaluation window too short, warm-up unaccounted for, or bursty load. Increase hysteresis/stabilization, measure metrics accurately, and reduce the scale-in step.

## 20. Production Readiness Checklist

**Workloads and Policies**

- [ ] Measured baseline, peak, request mix, and safe throughput per VM.
- [ ] Defined SLOs, headroom, and N-1 capacity.
- [ ] Scaling metric reflects the primary bottleneck; confirming metrics are configured.
- [ ] Targets/thresholds, evaluation windows, and scale-in stabilization are benchmarked.
- [ ] Min/desired/max align with quotas, subnet IPs, budget, and downstream capacity.
- [ ] Scheduled/predictive scaling is used only where patterns are reliable.

**Lifecycle and Health**

- [ ] Images/templates are versioned and hardened.
- [ ] Startup scripts are idempotent and contain no secrets.
- [ ] Readiness passes only when the app is genuinely ready.
- [ ] Instance warm-up is measured from creation to first request.
- [ ] Scale-in uses connection draining, graceful shutdown, and timeouts.
- [ ] Long jobs support checkpoint/retry or lease release.
- [ ] Scale-in protection/lifecycle hooks have deadlines and runbooks.

**Observability**

- [ ] Dashboards show desired/current/min/max and healthy target counts.
- [ ] Metrics cover request rate, requests/target, p95/p99, and error rates.
- [ ] Per-instance and per-zone CPU/memory/disk/network metrics are available.
- [ ] Scaling activities, trigger metrics, and provisioning failures are tracked.
- [ ] DB/cache/queue/external dependency metrics are included.
- [ ] Centralized logs/traces include instance ID, zone, and correlation ID.
- [ ] Alerts specify owner, severity, dashboard, and runbook.

**Resilience and Cost**

- [ ] Tested bursts, steady load, scale-in, and instance failures.
- [ ] Tested group-at-max and quota/capacity failures in sandbox.
- [ ] Backpressure/rate limiting protects downstream dependencies.
- [ ] Budgets/max capacity are set and cost per successful request/job is tracked.
- [ ] Verified multi-zone distribution and failover.
- [ ] Cleaned up lab resources after testing.

## 21. Conclusion

Effective autoscaling combines capacity planning, right-sized metrics, stable policies, safe lifecycle handling, and end-to-end observability. Scale-out must be fast enough to add capacity before SLOs degrade; scale-in must be conservative enough to avoid dropping requests/jobs or inducing oscillation. Min, desired, and max must reflect load, availability, quotas, subnets, budget, and dependency capacity.

In operations, always correlate trigger metrics with scaling activities, healthy target counts, and application outcomes. If adding VMs does not lower latency or queue age, look for bottlenecks in databases, caches, networks, or external services rather than scaling capacity indefinitely. Running load tests, inspecting timelines, testing failures, and measuring cost per successful request turn autoscaling from a configuration toggle into a verifiable operational mechanism.

## Key Terms to Remember

| Term | Meaning |
|---|---|
| Autoscaling | Automatically adjusting capacity based on metrics, schedules, or forecasts. |
| Scale-out | Increasing the number of instances to add capacity. |
| Scale-in | Decreasing the number of instances when demand drops. |
| Target tracking | A policy keeping a metric close to a target value. |
| Step scaling | Adjusting capacity in tiers based on threshold breach magnitude. |
| Scheduled scaling | Adjusting capacity on a defined schedule. |
| Predictive scaling | Using historical data to forecast and pre-provision capacity. |
| Min/desired/max | Minimum, desired, and maximum instance counts for a group. |
| Headroom | Spare capacity reserved for bursts, startup delays, and failures. |
| Warm-up | Time a new instance takes to become effective serving capacity. |
| Cooldown | Period restricting subsequent scaling evaluations/actions per policy semantics. |
| Stabilization window | Observation window before altering capacity, especially critical for scale-in. |
| Hysteresis | Using distinct scale-out and scale-in thresholds to prevent oscillation. |
| Readiness | Application state indicating readiness to accept traffic. |
| Connection draining | Stopping new requests while allowing in-flight requests to finish. |
| Lifecycle hook | Intervention point in an instance lifecycle before termination/transition proceeds. |
| Queue depth | Number of messages/jobs waiting in a queue. |
| Oldest message age | Age of the oldest queued message/job still waiting. |
| Thrashing | Continuous scale-up/scale-down oscillation due to policy or metric fluctuations. |
| Backpressure | Mechanism limiting incoming work when downstream lacks capacity. |
| SLO | Service Level Objective set by the operations team. |
| Cost per successful request | Cost incurred to successfully process one request. |