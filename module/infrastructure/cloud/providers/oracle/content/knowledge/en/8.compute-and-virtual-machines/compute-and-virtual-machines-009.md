# Schedule-Based and Metric-Based Autoscaling

## Lesson Objectives

Autoscaling is a mechanism that automatically adjusts resources according to a defined policy. In the context of OCI Compute, this lesson focuses on changing the instance count of an **instance pool**: adding instances when more processing capacity is needed and removing instances when demand drops.

This lesson belongs to the **Compute and Virtual Machines** chapter of the **CLOUD_PROVIDERS_ORACLE** module. Learners need to connect autoscaling with IAM, VCN, Compute, monitoring, cost, and fault tolerance across the entire OCI system.

After this lesson, you will be able to:

- Distinguish schedule-based and metric-based autoscaling and select a mechanism based on traffic characteristics.
- Explain the relationship among instance configurations, instance pools, autoscaling policies, and load balancers.
- Set scale limits, scale-out/scale-in thresholds, and stabilization intervals based on test data.
- Read schedules in UTC, account for instance provisioning time, and catch timezone offset errors.
- Plan tests for scale-out, scale-in, capacity shortages, and metric gaps.
- Assess impacts on databases, application data, availability, and cost.

Numbers in this lesson are illustrative assumptions. Shape support, OS support, policies, and exact limits must be verified in the target OCI deployment environment. Policy tables represent design specs, not schemas to submit directly to the API.

## 1. What Does Instance Pool Autoscaling Do?

### 1.1. Scale-Out and Scale-In

- **Scale-out**: increases instance count to distribute load across more machines.
- **Scale-in**: decreases instance count when the system can serve with fewer machines.
- **Scale-up/scale-down**: increases/decreases resources of an individual machine, such as CPU or RAM; this is a different operation from resizing an instance pool.

Do not assume "enabling autoscaling" means OCI will automatically choose shapes, tune JVM heaps, optimize queries, or expand database capacity. A scaling policy controls only the resource scope it is configured to manage.

For example, a Java API runs on two instances. Scaling out to four instances creates two additional runtime nodes. If every request still waits on a slow query on the same database, adding application hosts may not improve latency.

### 1.2. Components in OCI

| Component | Role | What to Prepare |
| --- | --- | --- |
| Instance configuration | Describes how to create instances | Image, shape, initialization config, networking, and related parameters |
| Instance pool | Manages a group of instances by configuration and placement | Size, placement, lifecycle, and application integration |
| Autoscaling configuration and policy | Defines conditions or schedule for resizing | Policy type, limits, actions, and active schedule |
| Monitoring and metric source | Supplies performance signals for metric-based policies | Appropriate agents/plugins, complete data, and exact scope |
| Load balancer, if required by the app | Distributes requests to eligible backends | Association with pool, backend set, and proper health checks |
| IAM | Governs who configures and operates resources | Least-privilege policies per compartment and operational model |

New instances must self-initialize from saved configuration. If every launch still requires SSHing in to copy files or manually edit host addresses, the scale-out workflow is incomplete.

Do not assume updating an instance configuration automatically upgrades running instances. Manage configuration versions and replacement plans for existing instances separately from policies that adjust instance count.

## 2. Two Mechanisms: Schedule-Based and Metric-Based

| Mechanism | Decision Signal | Best Suited For | Limitations to Remember |
| --- | --- | --- | --- |
| Schedule-based | Configured time points | Business hours, recurring batch jobs, known events | Does not detect unexpected real-time load changes |
| Metric-based | Performance metric crossing a condition | Variable load where metrics correlate clearly with demand | Has latency for sampling, evaluation, provisioning, and startup |

Schedules can prepare capacity ahead of peaks. Metric-based scaling reacts once the system observes the defined condition. Both require time for new instances to become ready and are constrained by permissions, configuration, limits/quotas, and actual capacity.

Do not assume both policy types can be placed together in one autoscaling configuration or freely control the same pool simultaneously. Before designing a combined approach, verify OCI constraints on policy types and instance pool associations. The two examples in this lesson are evaluated independently; they do not instruct attaching two controllers to one pool concurrently.

## 3. Conditions for Autoscaling to Deliver Real Serving Capacity

### 3.1. The Application Must Tolerate Adding and Losing Instances

Applications scale horizontally smoothly when requests do not depend on a specific host. Critical state must be managed in an appropriate store, such as a database or shared state service, with designed concurrency and recovery mechanisms.

Examples that hinder scaling:

- Sessions stored only in one instance's memory.
- User-uploaded files residing only on the local disk of the receiving host.
- Workers claiming jobs without acknowledgment, retry, or deduplication mechanisms.
- Scheduled jobs running on every new host and duplicating work meant to run once.
- Instance IP addresses hardcoded in other components.

Sticky sessions do not protect sessions when a machine is terminated or fails. For workers, "re-claiming tasks" is safe only when the processing model supports retries and controls side effects.

### 3.2. A Running Machine Does Not Mean the Application Is Ready

A typical scale-out sequence:

```text
Policy requests pool increase
  -> OCI provisions and boots instance
  -> OS, agents, and bootstrap run
  -> Application fetches config, starts, and connects to dependencies
  -> Backend registered; health check confirms readiness
  -> New instance receives requests
```

Provisioning lead time is the sum of all stages, not just how fast the instance enters running state. For Java, application loading, JVM/JIT warm-up, connection pool creation, and cache warming can add extra time.

Health checks should reflect designed readiness to serve requests. An open TCP port does not prove the application finished initializing. Conversely, an overly heavy check or one tied to every non-essential service can unnecessarily mark healthy backends down.

### 3.3. Permissions and Network Paths Must Work at Bootstrap

New instances must perform required actions using their assigned identity and permissions rather than credentials manually copied from an old host. Distinguish permissions of the person configuring autoscaling from runtime permissions of the application on the instance.

In the VCN, verify paths to artifact sources, configuration, secrets, and dependent services. An instance in a private subnet does not gain Internet egress automatically just by belonging to an instance pool; design routes, gateways, or private access paths for each destination.

Separate permissions by compartment and function. Enabling autoscaling is never a reason to grant tenancy-wide admin rights to operators or to every instance.

## 4. Metric-Based Autoscaling

### 4.1. Choosing a Signal Correlated with Processing Capacity

For OCI Compute metric-based autoscaling, standard signals are CPU or memory utilization on the instance pool as supported. Do not assume any arbitrary custom Monitoring metric can be used directly as a trigger in a standard policy.

Metric selection must start from workload testing:

| Symptom | Is CPU Likely a Good Signal? | Additional Checks Needed |
| --- | --- | --- |
| Requests are compute-bound and CPU rises with throughput | Potentially yes | Load distribution and the point where latency rises |
| Requests wait mainly on the database | Usually insufficient | Queries, connection pools, DB limits, and network latency |
| Memory rises with concurrent tasks | May consider memory | Off-heap memory, GC, and actual reclamation after load drops |
| Workers wait on a queue while CPU stays low | Not necessarily | Queue depth/task age as operational signals and policy support |
| One instance runs hotter than others | Pool average may hide the issue | Load balancing, sessions, skewed tasks, and per-instance metrics |

If a system needs scaling by queue depth or business signals, identify a supported control solution instead of assuming any metric plugs into a standard policy. That is a different architectural decision, not a default property of metric-based autoscaling.

### 4.2. Verify Metrics Are Actually Being Collected

For agent-provided Compute metrics, verify Oracle Cloud Agent and the **Compute Instance Monitoring** plugin for the supported image/OS. Confirm data actually arrives for live instances, rather than merely seeing the plugin marked enabled in config.

A useful preflight check:

1. Verify the exact instance pool and managed instance list.
2. Confirm the target CPU or memory metric shows recent timestamps.
3. Check compartment, namespace, and resource scope when viewing Monitoring.
4. Correlate metric timestamps with bootstrap and load-test windows.
5. Confirm permissions and network paths needed for monitoring telemetry to flow.

**No data does not mean 0% utilization.** When metrics drop out, investigate the data source and check how the OCI policy behaves under missing data rather than concluding the workload is idle.

### 4.3. Scale-Out and Scale-In Thresholds Need Separation

Design example for a CPU-bound API:

| Parameter | Illustrative Value | Meaning |
| --- | --- | --- |
| Minimum size | 2 instances | Baseline floor, still checked against fault-tolerance needs |
| Initial size | 2 instances | Starting size for the test |
| Maximum size | 8 instances | Caps expansion within planned bounds |
| Scale-out condition | Pool CPU exceeds 65% per policy evaluation | Indicates need for more CPU capacity |
| Scale-out action | Add 1 instance | Initial step size for testing |
| Scale-in condition | Pool CPU below 30% per policy evaluation | Indicates potential excess capacity |
| Scale-in action | Remove 1 instance | Initial step-down size for testing |

These thresholds are not universal recommendations for every application. Verify how OCI aggregates metrics, evaluates thresholds, and supports actions before translating a table into live configuration.

Using the same threshold for scaling out and in causes oscillation around that point. The gap between thresholds is **hysteresis**: the signal must cross a clear deadband before reversing direction.

For example, CPU dropping from 67% to 50% after scale-out should not immediately trigger scale-in. A lower scale-in threshold creates a stability band, though observation windows and other conditions must still fit.

### 4.4. Cooldown and Reaction Latency

Cooldown is a control wait period between scaling actions as supported by the policy mechanism. It prevents repeated resizing before the impact of the previous action has materialized.

Distinguish these time intervals:

- Metric sampling and aggregation interval.
- Condition evaluation window.
- Controller cooldown.
- Instance provisioning and boot time.
- Application readiness and workload stabilization time.

Do not treat cooldown as a guarantee that the application finished warming up. Nor should you assume every interval above is a user-configurable parameter. Read the exact fields supported by OCI policies.

If new instances take several minutes to serve, an overly aggressive control cadence can launch multiple instances before seeing any effect. Conversely, an overly slow reaction can cause high latency or errors before extra capacity arrives. Decisions must balance load ramp rate against measured readiness time.

### 4.5. JVM Memory Can Delay Scale-In

An expanded heap, caches, or memory reclamation behavior can keep memory utilization high even after traffic drops. An application may serve few requests while still holding substantial allocated memory.

Therefore, do not choose memory merely because the metric exists. Determine what the metric measures, how it varies with workload, and whether removing instances pushes remaining hosts into GC pressure or out-of-memory conditions.

## 5. Schedule-Based Autoscaling

### 5.1. Use Schedules When Demand Is Predictable

For example, an internal system sees high traffic from 08:00 to 18:00 on weekdays. The team can scale out the pool before work starts and scale in after end-of-day jobs finish.

Schedules fit more than business hours. They also serve recurring batch runs or events with known start times. However, schedules cannot detect if an event runs late or if user concurrency spikes unexpectedly.

This lesson examines schedules that change instance count. Other lifecycle actions, if supported by OCI for the policy and pool type, must be evaluated separately; reducing instance count and stopping instances have different consequences.

### 5.2. Converting Business Hours to UTC

OCI schedule-based autoscaling uses UTC schedules. Designers must convert business hours to UTC before entering schedule expressions in the service-supported format.

Example for Vietnam timezone, UTC+7:

| Activity | Vietnam Time | UTC Time | Illustrative Target Size |
| --- | --- | --- | --- |
| Pre-business-hours ramp, Monday to Friday | 07:45 | 00:45 same day | 6 instances |
| Post-business-hours scale-down, Monday to Friday | 18:30 | 11:30 same day | 2 instances |

This is a requirements table, not a cron expression ready to paste into OCI. Do not assume Linux cron syntax works everywhere in service schedule fields. When entering a schedule, verify OCI's required format and preview the upcoming execution times displayed.

If business hours fall near midnight, the UTC day may be the previous or next day. For users in timezones with daylight saving time, a fixed UTC schedule shifts relative to local time when seasons change. Holidays and special events must be handled explicitly rather than inferred from "Monday to Friday".

### 5.3. Scale Out Before Peak, Scale In After Work Completes

Suppose requesting an instance through backend readiness normally takes 6 minutes, and the team wants a 5-minute buffer. Scaling right at 08:00 is too late if users start hitting the system immediately. The 07:45 schedule in the example builds prep time, though it must still be verified against actual timing and capacity variability.

Similarly, scaling in at 18:00 might cut off a running end-of-day aggregation batch. Distinguish "time new tasks stop arriving" from "time all tasks have finished".

A scheduled target size does not guarantee that exact number of healthy backends at the exact trigger minute. After a scheduled action fires, monitor pool progress, bootstrap, health checks, and ready backend count.

### 5.4. Checking for Control Conflicts

Do not schedule two policies with conflicting goals at the same time. If manual size overrides occur, understand how the next scheduled execution will apply its configured target.

Document both business hours and UTC schedules in operational runbooks alongside an owner. That avoids an on-call engineer thinking "the system unexpectedly dropped machines" when a preconfigured schedule simply ran.

## 6. Choosing Min/Max and Step Sizes from Data

### 6.1. Min Is Baseline Capacity, Not Just the Cheapest Number

Suppose tests show one instance safely serves 150 requests/second at the chosen latency target. For a baseline load of 600 requests/second:

```text
Minimum serving instances for load
  = ceil(600 / 150)
  = 4
```

If the system must also survive losing one instance at that exact load, at least 5 serving instances are required in the example's ideal load-balancing model. The four remaining machines after a failure can then handle 600 requests/second.

This is not yet a complete model for losing an entire availability domain or for uneven load distribution. Nor can you replace 5 with 2 merely because you have two placement zones: fault domain count and remaining post-failure capacity are two separate problems.

### 6.2. Max Must Respect Downstream Systems

Adding application instances also multiplies connections, requests, and load on downstream services.

For example, if each instance allows up to 30 DB connections, eight instances can open up to 240 connections from that application group alone. Add other service groups, admin sessions, and deployment overlap when old and new versions run concurrently.

Compare maximum scale against:

- Related service limits and compartment quotas.
- Shape capacity in the deployment location.
- Subnet IP capacity and related network resources.
- Oracle database connection limits and capacity.
- Load balancers, storage services, queues, and other dependencies.
- Budget and operational policies.

Max is a control limit, not a hard budget cap. A pricier shape, larger volumes, higher network traffic, or longer runtime hours can still raise costs even if instance count stays within max. Budget alerts are also not an automatic resource-stopping mechanism.

### 6.3. Small or Large Step Sizes?

Small steps reduce over-provisioning risk but take more cycles to catch a steep load spike. Large steps react faster but increase pressure on capacity, bootstrap, and dependent services.

If workload peaks rise faster than instance startup time, changing step size alone may be insufficient. You may need higher baseline capacity, scheduled pre-warming, faster initialization, or a burst-handling design. Combining mechanisms must follow platform-supported policy rules.

## 7. Scale-In Is a Planned Instance Loss Event

When a pool shrinks, some instances may be terminated. Do not rely on always knowing which instance will be picked or treat scale-in as safely pausing all processes.

For APIs, verify in practice:

- How backends are removed from receiving new requests via the pool/load-balancer integration.
- Whether in-flight requests get enough time to finish or are dropped.
- Whether the application supports graceful shutdown and whether it is actually invoked on the instance termination path.
- Whether clients have sensible timeouts/retries and whether requests with side effects prevent duplicate execution.

Do not assume OCI automatically provides a lifecycle hook or arbitrary drain window for your app just because an autoscaling policy exists. Verify each component's capabilities and timeouts. Even with graceful shutdown, the application must tolerate sudden host loss.

For queue workers, design around the queue system's claim, acknowledge, and retry-on-failure semantics. Persist needed progress durably; handle duplicates with idempotency or business-appropriate transactions.

Data on an instance's local drive does not persist by default after scale-in. Boot volumes and attached volumes also have lifecycle policies to check, including the possibility of leaving billable volumes behind after instances terminate.

## 8. Two Illustrative Deployment Scenarios

### 8.1. Java API with Unpredictable Load: Metric-Based Evaluation

Context: stateless application, CPU scales fairly linearly with traffic; the Oracle database has spare headroom across the tested scaling range.

Design sequence:

1. Select an image and shape verified with the JDK, libraries, and agents.
2. Build a repeatable bootstrap requiring no manual SSH after each launch.
3. Configure the instance pool, placement, and network path to the database.
4. Attach the load balancer and confirm backends are healthy before taking traffic.
5. Verify CPU metrics actually appear for instances in the pool.
6. Choose min/max, scale-out/in thresholds, step size, and cooldown from tests.
7. Apply controlled load and observe from threshold breach until new instances serve traffic.
8. Reduce load and verify scale-in drops no transactions and stays within remaining instances' capacity.

If CPU is low while p95 keeps climbing due to a slow DB, stop tuning thresholds blindly. Identify the bottleneck; scaling out application hosts in that situation can push even more connections onto the database.

### 8.2. Internal System with Stable Business Hours: Schedule-Based Evaluation

Context: traffic is predictable by workday, morning ramps are steady, and off-hours still serve background tasks.

Design sequence:

1. Measure new-instance readiness time and actual start/end-of-day traffic.
2. Choose business-hours and off-hours sizes, checking remaining capacity on failure.
3. Convert business hours to UTC and check weekdays.
4. Schedule scale-out early enough ahead of the ramp.
5. Schedule scale-in after trailing work completes.
6. Test a near-term schedule in a test environment to observe behavior.
7. Check weekends, holidays, and exceptional surge events.
8. Document how to override the policy temporarily, restore standard schedules, and verify current size.

Do not set off-hours scale to 0 solely to cut costs if health checks, background tasks, or access requests must still be served. Allowed specific pool sizes must also be confirmed for your OCI configuration.

## 9. Pre-Production Test Plan

The table below is a test plan for an authorized test environment; it is not an instruction to test directly on a live user-facing system.

| Scenario | What to Observe | Expected Result |
| --- | --- | --- |
| Gradual load increase | Metrics, policy trigger time, instance count, and healthy backends | Scale increases and latency returns to target within acceptable window |
| Sudden load spike | Error rate and wait time for new instances | Reveals reaction limits and baseline capacity needs |
| Load drop | Scale-in condition, cooldown, in-flight requests | Controlled scale-in with no loss of acknowledged work |
| Load oscillating near threshold | Sequence of scale-out/in actions and before/after metrics | No continuous flapping causing instability |
| Bootstrap failure | Initialization logs, instance state, and health checks | Failing machines are not counted as healthy serving capacity |
| Metric gap | Timestamps, agent/plugin status, and policy behavior | Alert triggers; missing data is not interpreted as zero load |
| Capacity shortage or limit reached | Operation events and actual pool size | Uncompleted action detected with clear remediation path |
| Scheduled time reached | UTC time, day of week, and target size | Action fires on schedule; ready backend count verified |
| Scale-in during active tasks | Requests, queue acks, and transaction state | Tasks finish or are safely re-claimed per design |
| Loss of one instance | Remaining capacity and latency | Meets committed fault-tolerance requirements |

Record the elapsed time from trigger to latency recovery. Seeing instance count increase alone does not prove autoscaling achieved its goal.

## 10. Monitoring and Handling Anomalies

### 10.1. Three Observation Layers to Correlate

- **Control**: whether the policy is enabled or disabled, which schedule/thresholds apply, when resize requests fire.
- **Infrastructure**: requested pool size, actual instances, provisioning state, capacity, and healthy backends.
- **Application**: throughput, error rate, latency, queues, query times, and DB connection count.

These three layers can diverge. A policy may request six instances while only four serve traffic because two failed bootstrap. CPU metrics may drop while users still see slowness due to a database issue.

### 10.2. Diagnostic Table

| Symptom | First Direction to Check |
| --- | --- |
| High CPU but pool does not scale out | Policy state, evaluation conditions, cooldown, max size, and pool metrics |
| Scale-out requested but new instances missing | Limits/quotas, capacity, placement, image/shape, and work/operation events |
| New instances exist but take no requests | Bootstrap, networking, backend registration, and health checks |
| Pool keeps growing yet latency stays high | Non-Compute bottleneck, load distribution, or metric not reflecting demand |
| Load drops yet pool does not scale in | Scale-in threshold, lingering usage, cooldown, min size, and policy state |
| Schedule fires at wrong time | UTC conversion, day of week, schedule expression, and DST shifts in local time |
| Costs rise unexpectedly | Duration at high scale, shape, volumes, network, and leftover resources after scale-in |
| Scale-in drops sessions or tasks | Local state, retry/idempotency mechanisms, and shutdown path |

If autoscaling must be paused for investigation, follow approved operational procedures, pick a safe static size, and assign an owner to re-enable it. Pausing a policy does not fix capacity shortages or application bugs, nor does it revert actions already in progress.

## 11. Design Sheet and Self-Check Questions

Complete the following sheet before translating the design into deployment config:

| Item | Result to Record |
| --- | --- |
| Workload and targets | Throughput, p95/p99, error rate, task duration |
| Selected mechanism | Schedule-based or metric-based, rationale, and verified OCI constraints |
| Instance pool | Compartment, instance config, shape, image, and placement |
| Repeatability | Bootstrap method, application version, and runtime permissions |
| Sizing | Min/initial/max or scheduled target sizes valid for the policy |
| Trigger | Metric/thresholds/actions or UTC schedule and corresponding business hours |
| Timing | Observation delay, cooldown if applicable, instance readiness time |
| Data and scale-in | Sessions, files, queues, transactions, retries, and recovery |
| Dependencies | Database, load balancer, subnet, limits/quotas, and capacity |
| Operations and cost | Metrics, alerts, owner, cost estimate, and exception handling |
| Evidence | Results from ramp-up, ramp-down, instance loss, and bootstrap-failure tests |

Self-check:

1. Why might an instance in running state still fail to add API serving capacity?
2. When is a scheduled scale-out before 08:00 more effective than waiting for CPU to cross a threshold?
3. If pool CPU is low while p95 is high and the DB is overloaded, what can adding application instances cause?
4. What problem does spacing out scale-out and scale-in thresholds solve, and why must reaction time still be considered?
5. What UTC time corresponds to 07:45 Vietnam time? Why must you still preview upcoming scheduled runs?
6. Why must a metric with missing data never be treated as 0% CPU?
7. With 600 requests/second and safe capacity of 150 requests/second per instance, how many instances are needed to survive losing one instance under the lesson's assumptions?
8. Which data is at risk if it exists only on an instance chosen for scale-in?
9. Why do max instance count and budget alerts not create a hard cost ceiling?
10. What must you verify before attempting to combine schedule-based and metric-based control on the same pool?

The output of this exercise is a policy with clear objectives alongside evidence that adding and removing instances preserves service quality, data safety, and planned cost bounds.
