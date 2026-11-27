# Load Testing, Capacity Testing, and Verifying Autoscaling

An API may perform well with a few dozen users yet slow down or return errors when traffic increases tenfold. An Auto Scaling Group may add EC2 instances exactly as configured, yet users still experience high latency because the database connection pool is exhausted, queues are backing up, or the load balancer has not yet placed new instances into service. Therefore, performance testing must measure the entire workload and verify that the system scales out, stays stable, and scales in properly.

In AWS, load testing measures application behavior under realistic load; capacity testing determines sustainable load and component limits; and autoscaling testing verifies policies that adjust compute as demand changes. These tests combine CloudWatch, Application Load Balancer, EC2 Auto Scaling, Application Auto Scaling, ECS, Lambda, database metrics, and distributed load generators.

In the **CLOUD_PROVIDERS_AWS** ecosystem, learners must know how to translate business requirements into measurable SLOs, generate production-like workloads, calculate capacity from benchmark data, locate bottlenecks, verify scale-out/scale-in, and control quotas and costs. The ultimate goal is to prove the application meets throughput, latency, error rate, and availability targets under normal, peak, and sudden spike loads.

## 1. Distinguishing Load Testing, Capacity Testing, and Autoscaling Testing

These three tests are related yet answer different questions.

| Test | Primary Question | Required Findings |
|---|---|---|
| Load test | How does the application behave under expected workload? | Throughput, latency, error rate, and dependency behavior |
| Capacity test | How much load can the workload sustain before breaching SLOs? | Sustainable capacity, bottlenecks, and breaking points |
| Autoscaling test | Does the system add/remove capacity at the right time and scale? | Scale-out delay, scale-in behavior, stability, and SLOs during scaling |

A load test may pass even without autoscaling if capacity is pre-provisioned. Conversely, autoscaling may adjust instance counts as configured yet react too slowly for a traffic spike. Evaluate application performance and scaling behavior separately.

## 2. Defining SLOs and Acceptance Criteria Before Generating Load

Do not start by asking "how many requests per second can it handle?". First determine what user experience is required and which conditions the system must meet.

Example SLOs for an order API:

| Metric | Illustrative Criterion |
|---|---|
| Throughput | 800 requests/second for 30 minutes |
| Latency | p95 under 250 ms, p99 under 700 ms |
| Error rate | HTTP 5xx and application errors under 0.5% |
| Availability | No total service loss when one instance/AZ fails |
| Recovery | Additional capacity ready within 3 minutes |
| Data correctness | No duplicate orders or lost transactions |

These numbers are only examples. Real SLOs must derive from service agreements, user behavior, business impact, and workload benchmarks.

Distinguish:

- **SLO:** internal reliability or performance objective.
- **SLI:** actual measured indicator, such as p95 latency or request success rate.
- **SLA:** customer-facing service commitment, potentially with remedies/credits.
- **Test threshold:** pass/fail condition for a specific test run.

Set thresholds for every critical user journey, not just the health-check endpoint. A page might return HTTP 200 while dropping data, mishandling business rules, or omitting response fields.

## 3. Types of Performance Testing

| Test Type | Description | Purpose |
|---|---|---|
| Smoke test | Very low load for a short duration | Verify scripts, test data, and endpoints work |
| Load test | Representative load for expected traffic | Verify SLOs at normal/peak load |
| Stress test | Ramp load beyond expected capacity | Find breaking points and degradation modes |
| Spike test | Rapidly ramp load up then down | Test response to traffic bursts |
| Soak/endurance test | Sustain steady load over a long period | Uncover memory leaks, connection leaks, queue growth, and degradation |
| Capacity test | Increase load under control until limits | Measure sustainable throughput and required resources |
| Scalability test | Vary load and/or capacity across multiple levels | Validate scale-up/scale-out efficiency |
| Failover/resilience test | Combine load with instance, AZ, or dependency faults | Verify the workload maintains SLOs and recovers |

A test program typically runs smoke tests first, followed by load, spike, soak, and capacity tests. Run stress tests only after safety thresholds and safe stop mechanisms are established.

## 4. Workload Models: Virtual Users and Arrival Rate

Two common ways to simulate users:

- **Closed workload model:** fixed number of virtual users; each user sends a request, waits for a response and think time, then sends the next request. When the system slows down, request generation rate drops automatically.
- **Open workload model:** the test specifies a target arrival rate, e.g., 500 requests/second, independent of response time. If the system slows down, in-flight/queued requests grow.

Closed models fit interactive users who pause between actions. Open models fit verifying whether the system can sustain a fixed incoming request rate.

If you use a closed model to test an overloaded system, rising latency can cause the load generator to throttle itself and mask bottlenecks. Choose the workload model based on the test objective and always record the actual request rate.

### Little's Law

For a stable system, the average number of concurrent in-flight requests can be estimated by:

\[
L = \lambda \times W
\]

Where:

- \(L\): average number of in-flight requests (average concurrency).
- \(\lambda\): arrival rate, in requests/second.
- \(W\): average response time, in seconds.

For example, 300 requests/second at an average response time of 0.4 seconds corresponds to roughly 120 in-flight requests. This formula helps estimate concurrency, connection pools, and worker counts; it does not replace real benchmarking.

## 5. Designing User Journeys and Traffic Distribution

A production workload typically spans multiple endpoints and operation types. Calling only a health-check endpoint does not reflect real load.

Example request mix for an e-commerce application:

| User Journey | Share | Characteristics |
|---|---:|---|
| Browse catalog/products | 45% | Read-heavy; caching can help significantly |
| Search | 20% | Can drive CPU or search cluster load |
| Login/authentication | 10% | Depends on identity provider and token validation |
| Add to cart | 15% | Involves writes, concurrency, and consistency |
| Create order/simulated payment | 10% | Multiple dependencies; requires idempotency |

Test design must simulate:

- Read/write ratio.
- Request/response payload sizes.
- Think time and retry behavior.
- Cache hit/miss ratio.
- Tenant/user/product distribution.
- Concurrent requests per user.
- Authentication and session behavior.
- Dependencies such as databases, queues, payment sandboxes, and external APIs.

Never call live payment systems or third-party services with test data without a sandbox environment and explicit approval.

## 6. Preparing a Production-Like Environment

Test results are valid only when the environment sufficiently resembles production across performance-sensitive factors:

- Instance/task sizes, AZ count, and load balancers.
- Container images, runtimes, and application configuration.
- Database engine/version, parameter groups, storage, and connection pools.
- Caches, queues, network paths, and security groups.
- Autoscaling policies, min/max capacity, and warmup settings.
- Data volume, data distribution, and indexes.
- TLS, authentication, logging, and tracing.

If testing on a smaller environment than production, do not linearly extrapolate results by CPU or instance count. Caches, networking, database contention, shards/partitions, and quotas can scale non-linearly.

Prefer provisioning environments with Infrastructure as Code so test and production configurations remain comparable. Document every difference such as instance family, storage class, dataset size, and service quotas.

## 7. Data Safety and Testing Scope

Use synthetic data or production copies stripped of sensitive information. Attach a test run ID in headers, records, or partitions to separate test data from real business reports.

Before running:

1. Identify the target endpoint and account/Region.
2. Confirm the workload owner and test window.
3. Check service quotas and load generator limits.
4. Set caps on request rate, duration, and virtual users.
5. Prepare alarms, dashboards, and an on-call observer.
6. Define immediate stop conditions if production is affected.
7. Check current AWS policies if traffic patterns could resemble DoS/DDoS or originate externally.

AWS Well-Architected recommends testing in a production-like environment, using synthetic/sanitized data, and measuring the entire workload. If load testing in production, limit blast radius, avoid impacting users, and tag test data so reporting is not skewed. https://docs.aws.amazon.com/wellarchitected/2024-06-27/framework/perf_process_culture_load_test.html

## 8. Load Generation Tools

| Tool | Strengths | Best Fit |
|---|---|---|
| k6 | JavaScript scripts, thresholds, easy CI/CD integration | API and HTTP workloads |
| Apache JMeter | Broad protocol/plugin support, GUI, and distributed mode | HTTP, JDBC, JMS, and legacy workloads |
| Locust | Python, customizable user behavior | Simulating complex user journeys |
| Artillery | Concise scripts, HTTP/WebSocket, and cloud execution | APIs, real-time, and CI performance checks |
| Distributed Load Testing on AWS | Managed distributed runners, dashboards, and baselines | High load, multi-Region, and repeatable tests |

**Distributed Load Testing on AWS** is an open-source solution provided by AWS. Current documentation supports JMeter, k6, Locust, and HTTP endpoint testing; it can distribute runners across multiple Regions, schedule runs, and compare baselines. Dashboards provide latency percentiles, error analysis, and artifacts. https://docs.aws.amazon.com/solutions/latest/distributed-load-testing-on-aws/solution-overview.html

Never assume a single load generator can produce unlimited requests. Generator CPU, network, file descriptors, ephemeral ports, DNS, and worker counts can all become bottlenecks.

## 9. Preventing the Load Generator from Becoming the Bottleneck

When a generator saturates, results may indicate the application is slow while the real bottleneck sits on the load-generating machine.

Monitor the generator:

- CPU, memory, and network utilization.
- Active virtual users and actual arrival rate.
- Dropped iterations or request scheduling delays.
- Socket/connection errors.
- DNS resolution and TLS handshake rates.
- File descriptor and ephemeral port usage.
- Number of active workers/containers generating load.

If the generator hits 100% CPU or fails to achieve the scripted request rate, add more runners or distribute across multiple AZs/Regions. Record runner counts and actual total arrival rates in the report.

## 10. Defining Repeatable Test Scenarios

A test scenario should specify:

- Test ID and script version.
- Endpoint/base URL and Region.
- Workload model: closed or open.
- Ramp-up, steady-state, spike, and ramp-down durations.
- Target virtual users or arrival rate.
- Request mix and test data.
- Latency/error/throughput thresholds.
- Tags distinguishing the test run and environment.
- Stop conditions and responsible owner.

Keep scripts and test data versions in source control. When comparing two runs, change only one set of variables at a time so causes of differences remain clear.

## 11. k6 Example: Ramp-Up, Steady-State, and Thresholds

The example below sends requests to a catalog API, ramps up from low load to 300 virtual users, holds load, and ramps down. Replace URLs, endpoint paths, and thresholds with real SLOs.

~~~javascript
import http from "k6/http";
import { check, sleep } from "k6";

export const options = {
  stages: [
    { duration: "2m", target: 50 },
    { duration: "3m", target: 150 },
    { duration: "10m", target: 150 },
    { duration: "3m", target: 300 },
    { duration: "5m", target: 300 },
    { duration: "2m", target: 0 }
  ],
  thresholds: {
    http_req_failed: ["rate<0.005"],
    http_req_duration: ["p(95)<250", "p(99)<700"],
    checks: ["rate>0.995"]
  }
};

export default function () {
  const response = http.get(
    __ENV.BASE_URL + "/catalog",
    {
      headers: {
        "X-Test-Run": __ENV.TEST_RUN_ID || "load-test"
      },
      tags: { journey: "catalog" }
    }
  );

  check(response, {
    "status is 200": (r) => r.status === 200,
    "body is not empty": (r) => r.body && r.body.length > 0
  });

  sleep(1);
}
~~~

Run:

~~~bash
BASE_URL=https://test.example.internal \
TEST_RUN_ID=release-2026-11-20 \
k6 run catalog-load.js
~~~

Thresholds in k6 determine pass/fail based on aggregated metrics. `sleep(1)` adds think time; if a fixed arrival rate is needed, use `constant-arrival-rate` or `ramping-arrival-rate` executors instead of solely increasing VUs.

## 12. Determining Capacity by Benchmarking Individual Components

Before testing the whole system, benchmark high-impact components:

- API/application servers.
- Database read/write paths.
- Cache hit/miss behavior.
- Queue producers/consumers.
- External APIs or service quotas.
- Serialization, compression, and TLS.
- Storage throughput and IOPS.

The goal is to find each component's sustainable throughput while still meeting SLOs. Never use peak throughput observed after latency has spiked or error rates breached thresholds as production capacity.

For example, an ECS task stably handles 120 requests/second with p95 under 250 ms and error rate below 0.1%. If latency jumps to 1.2 seconds at 150 requests/second, safe capacity should be calculated around 120 or lower based on chosen headroom.

## 13. Estimating Required Instances/Tasks

An initial estimate:

\[
N = \left\lceil \frac{\lambda_{peak} \times (1 + H)}{C_{safe}} \right\rceil
\]

Where:

- \(\lambda_{peak}\): expected peak request rate.
- \(H\): headroom ratio.
- \(C_{safe}\): sustainable throughput per instance/task while meeting SLOs.
- \(N\): number of instances/tasks needed at peak.

Example:

- Peak demand: 900 requests/second.
- Headroom: 25%.
- Safe benchmark: 90 requests/second/task.

\[
N = \left\lceil \frac{900 \times 1.25}{90} \right\rceil
  = \lceil 12.5 \rceil = 13
\]

You might set the ECS service to `minCapacity=3`, `desiredCapacity=3`, `maxCapacity=16`, then verify autoscaling reaches at least 13 tasks at peak load. Also account for losing an AZ, Fargate/EC2 quotas, subnet IP space, database connections, and dependency capacity.

This is an initial capacity planning model. If requests span multiple types with differing CPU/I/O costs, calculate using the workload mix and user journey benchmarks rather than one average RPS.

## 14. Choosing the Right Metric for Autoscaling

Scaling metrics must reflect how busy the scalable target is and vary proportionally with capacity.

| Workload | Candidate Metric | Notes |
|---|---|---|
| EC2 Auto Scaling Group | ASGAverageCPUUtilization | Suitable when CPU scales with traffic |
| EC2 ASG behind ALB | ALBRequestCountPerTarget | Measures requests per target, not total load balancer requests |
| ECS service | ECSServiceAverageCPUUtilization | Average CPU across tasks |
| ECS service | ECSServiceAverageMemoryUtilization | Useful when memory is the primary constraint |
| ECS service behind ALB | ALBRequestCountPerTarget | Target is average requests per task |
| Lambda | LambdaProvisionedConcurrencyUtilization for target tracking provisioned concurrency; ConcurrentExecutions and Throttles for monitoring | Monitor concurrency quotas, request rate, duration, and cold starts |
| DynamoDB provisioned | Read/Write capacity utilization | Monitor partition-level throttling and burst behavior |
| Queue workers | Backlog per worker/task | Raw queue depth alone may not scale inversely with worker count |

With target tracking, the metric should decrease as capacity increases. For instance, doubling ECS task count typically halves requests per task when load is evenly distributed. Total ALB `RequestCount` does not drop when adding targets, so never use that total metric for EC2 ASG target tracking.

Latency and error rates remain vital SLIs, yet they are better used for SLO evaluation/alarms and bottleneck investigation than directly as target tracking metrics if they do not scale proportionally with capacity.

## 15. Types of Autoscaling on AWS

| Scaling Type | How It Works | Best Fit |
|---|---|---|
| Target tracking | Keeps a metric close to a target value | Continuously fluctuating workloads |
| Step scaling | Applies tiered increases/decreases based on alarm breach magnitude | Need fine control over adjustments per overload level |
| Scheduled scaling | Sets min/max/desired capacity on a schedule | Known hourly/daily peaks |
| Predictive scaling | Forecasts demand from history and provisions capacity ahead of time | Workloads with recurring patterns |
| Simple scaling | Adjusts capacity per alarm and cooldown | Legacy systems or simple needs; target/step are usually preferred |

Target tracking is usually a strong starting point for ECS services and EC2 ASGs. Scheduled or predictive scaling can pre-warm capacity before peak hours; dynamic scaling handles actual variance.

Never enable multiple policies controlling the same metric in conflicting ways. In ECS, multiple target tracking policies can coexist if they use different metrics: scale-out occurs when any policy requests it; scale-in occurs only when all policies with scale-in enabled agree. https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service-autoscaling-targettracking.html

## 16. Target Tracking for EC2 Auto Scaling

EC2 Auto Scaling supports predefined metrics such as:

- ASGAverageCPUUtilization.
- ASGAverageCPUUtilizationHighResolution.
- ASGAverageNetworkIn.
- ASGAverageNetworkOut.
- ALBRequestCountPerTarget.

For custom metrics, ensure the metric reflects utilization per unit of capacity. Use one-minute or finer metric intervals where supported and when workloads require fast reactions. EC2 basic monitoring defaults to 5-minute intervals; detailed monitoring provides 1-minute intervals.

Target tracking creates and manages its own CloudWatch alarms. Do not edit or delete policy-managed alarms directly; modify policies through the Auto Scaling API/console.

## 17. Target Tracking for ECS Services

ECS Service Auto Scaling adjusts desired task count via Application Auto Scaling.

Common metrics:

- ECSServiceAverageCPUUtilization.
- ECSServiceAverageMemoryUtilization.
- ALBRequestCountPerTarget.

Example registering a scalable target and a CPU target tracking policy:

~~~bash
aws application-autoscaling register-scalable-target \
  --service-namespace ecs \
  --resource-id service/production-cluster/catalog-api \
  --scalable-dimension ecs:service:DesiredCount \
  --min-capacity 3 \
  --max-capacity 16
~~~

~~~bash
aws application-autoscaling put-scaling-policy \
  --policy-name catalog-cpu-target-55 \
  --service-namespace ecs \
  --resource-id service/production-cluster/catalog-api \
  --scalable-dimension ecs:service:DesiredCount \
  --policy-type TargetTrackingScaling \
  --target-tracking-scaling-policy-configuration '{
    "TargetValue": 55.0,
    "PredefinedMetricSpecification": {
      "PredefinedMetricType": "ECSServiceAverageCPUUtilization"
    },
    "ScaleOutCooldown": 60,
    "ScaleInCooldown": 180,
    "DisableScaleIn": false
  }'
~~~

A 55% target is just an example. Choose the target from benchmarks, task startup time, and required headroom. Monitor ECS service events, task placement, Fargate/EC2 capacity, and subnet IP space during scale-out.

## 18. Scale-Out Delay: Why New Instances Do Not Serve Immediately

Scale-out involves multiple stages:

1. Metrics are collected and alarms/policies evaluate.
2. The scaling service updates desired capacity.
3. EC2/Fargate capacity is provisioned.
4. Instances/tasks boot, pull images, and run bootstrap scripts.
5. The application loads models/caches/configuration.
6. Health checks pass.
7. Targets register and begin receiving traffic.

The total duration is the scale-out delay. If an application takes 4 minutes to boot, a policy reacting only after CPU exceeds target will be too late for a 1-minute spike.

Solutions:

- Maintain sufficient min capacity for baseline plus initial bursts.
- Use scheduled/predictive scaling for predictable peaks.
- Reduce container image size and startup work.
- Preload caches or model artifacts where appropriate.
- Choose metrics that react ahead of saturation.
- Use queues to absorb bursts if latency requirements permit.
- Evaluate warm pools or provisioned capacity when workloads require it.

## 19. Distinguishing Instance Warmup, Health-Check Grace Period, and Cooldown

Three commonly confused settings:

| Setting | Purpose |
|---|---|
| Default instance warmup | Time a new instance needs to stabilize before contributing to aggregated metrics and allowing dynamic scale-in |
| Health check grace period | Prevents marking a new instance unhealthy prematurely while the application is still initializing |
| Cooldown | Primarily throttles simple scaling policy activities between capacity changes |

EC2 Auto Scaling recommends configuring default instance warmup for target tracking and step scaling. Measure this value from actual startup duration; 300 seconds can serve as an initial placeholder without data, not a universally correct number.

Default health check grace periods vary by how the ASG was created: the console typically sets 300 seconds, while CLI/SDK defaults to 0 seconds. Do not set grace periods excessively long, as it delays replacing genuinely broken instances.

Target tracking and step scaling do not wait for simple scaling cooldowns before scaling out; they use instance warmup to avoid overreacting. Simple scaling is generally not the preferred choice for modern systems.

## 20. Safe Scale-In

Scale-in can disrupt traffic if it terminates an instance/task handling long-running requests or holding local state.

Verify:

- ALB deregistration delay/connection draining.
- ECS deployment/termination behavior.
- Application graceful shutdown and signal handling.
- Queue visibility timeouts and message acknowledgments.
- Lifecycle hooks if work must finish prior to termination.
- Externalizing sessions/state into caches/databases.
- Scale-in protection if specific instances must be preserved.

Scale-in should generally be slower than scale-out to prevent oscillation. After traffic drops, monitor latency, error rates, and queue backlogs before concluding capacity can safely shrink.

## 21. Testing Autoscaling by Phases

A test scenario can include:

| Phase | Load | Expected Behavior |
|---|---|---|
| Baseline | 20% peak | Min capacity serves stably |
| Ramp-up | Gradually ramp to 100% peak | Scale-out begins before sustained SLO breaches |
| Steady state | Hold peak 20–30 minutes | Capacity stabilizes; p95/p99 and errors within thresholds |
| Spike | Rapidly surge to 150% peak | No total service loss; queueing/overload stays controlled |
| Ramp-down | Drop back to 20% peak | Scale-in causes no errors or availability dips |
| Idle | Zero traffic | Capacity returns to min per policy |
| Repeat | Repeat 2–3 cycles | No resource leaks or scaling oscillation |

Record timestamps when load starts, metrics cross targets, scaling triggers, tasks/instances become ready, traffic balances, and SLOs normalize. These timestamps reveal real-world scale-out delay.

## 22. Verifying Autoscaling with Evidence

Do not just glance at instance counts in the console. Correlate multiple telemetry sources:

- Application and infrastructure CloudWatch metrics.
- CloudWatch alarms and scaling activity history.
- EC2 Auto Scaling activity history or ECS service events.
- ALB target health and request distribution.
- Test runner metrics: actual RPS, VUs, dropped iterations.
- Application logs, distributed traces, and database metrics.
- Service Quotas and throttling metrics.

A passing test must prove:

1. Actual load reached the defined level.
2. SLOs were met during steady-state phases.
3. Scale-out completed within the target window.
4. New instances/tasks actually became healthy and received traffic.
5. No new bottlenecks emerged in databases, queues, or downstream services.
6. Scale-in did not trigger error spikes or abnormal latency.
7. Post-test capacity returned to appropriate min/desired levels.

## 23. CloudWatch Metrics by Layer

| Layer | Metrics to Monitor | Signals to Watch |
|---|---|---|
| ALB | RequestCount, TargetResponseTime, HTTPCode_Target_5XX_Count, HealthyHostCount, TargetConnectionErrorCount | Slow, unhealthy, or connection-failing targets |
| EC2 | CPUUtilization, NetworkIn, NetworkOut, EBS IOPS/throughput | CPU/network/storage saturation |
| ECS | CPUUtilization, MemoryUtilization, RunningTaskCount, task placement failures | Tasks starved for CPU/memory or failing placement |
| Lambda | Invocations, Duration, Errors, Throttles, ConcurrentExecutions, ProvisionedConcurrencyUtilization | Concurrency/RPS quotas and cold starts |
| API Gateway | Count, Latency, IntegrationLatency, 4XXError, 5XXError | Throttling or slow backend integrations |
| RDS/Aurora | CPUUtilization, DatabaseConnections, read/write latency, IOPS, and free storage | DB becoming the bottleneck |
| DynamoDB | ConsumedRead/WriteCapacityUnits, Read/WriteThrottleEvents, latency | Partition hot spots or throughput limits |
| SQS | ApproximateNumberOfMessagesVisible, ApproximateAgeOfOldestMessage, in-flight messages | Consumers falling behind producers |

Exact metrics and dimensions depend on the service, engine, Region, and monitoring mode. Use percentile statistics for latency where supported; averages hide tail latency.

## 24. Interpreting Latency Percentiles Properly

Average latency can stay low even while a small fraction of requests are very slow. For example:

- p50 = 80 ms: half of requests finish in 80 ms or faster.
- p95 = 240 ms: 95% of requests finish in 240 ms or faster.
- p99 = 900 ms: 1% of requests are slower than 900 ms.

If an API serves 1 million requests/day, p99 represents roughly 10,000 requests slower than the p99 threshold. That can significantly impact user experience.

Track latency by endpoint, status code, request size, tenant, and dependency. Do not lump health checks, static assets, and checkout endpoints into a single percentile if those journeys have different requirements.

## 25. Testing Lambda Concurrency and Throttling

On-demand Lambda automatically scales execution environments yet remains subject to concurrency quotas, requests-per-second quotas, and concurrency scaling rates. Application Auto Scaling can adjust provisioned concurrency based on utilization metrics. Therefore, tests must monitor both concurrency and RPS; do not confuse observational metrics like `ConcurrentExecutions`/`Throttles` with the predefined target-tracking metric for provisioned concurrency.

Estimating concurrency:

\[
\text{Concurrency} \approx \text{RPS} \times \text{Average Duration (seconds)}
\]

For instance, 400 RPS with an average duration of 0.25 seconds requires roughly 100 concurrent executions. If duration rises to 1 second, the same RPS requires roughly 400 concurrency.

Verify:

- Account concurrency quotas and reserved concurrency.
- Provisioned concurrency if cold-start reduction is needed.
- Throttles and concurrent executions.
- Duration p95/p99 and memory utilization.
- Event source mapping batch size, maximum concurrency, and queue age.
- Whether downstream databases/APIs can withstand higher concurrency.

Never increase Lambda concurrency without checking RDS connection pools or external API quotas. Rapid Lambda scaling can overwhelm dependencies before Lambda hits its own limits.

## 26. Testing Queues and Worker Autoscaling

For asynchronous workloads, queues absorb bursts yet do not eliminate capacity limits.

Monitor:

- ApproximateNumberOfMessagesVisible.
- ApproximateAgeOfOldestMessage.
- Number of messages received/deleted.
- Worker concurrency/task count.
- Processing duration and retry rates.
- Dead-letter queue depth.

A useful metric for worker scaling is backlog per worker:

\[
\text{Backlog per worker} =
\frac{\text{Visible messages}}{\max(\text{Active workers}, 1)}
\]

Total queue depth may be unsuitable as a target tracking metric because it does not decrease proportionally as workers are added. Use a backlog-per-worker metric or step scaling based on queue age/depth.

Also test stopping producers while a large backlog remains to verify the system drains the queue and scales in cleanly afterward.

## 27. Testing Databases and Downstream Limits

Autoscaling the application tier can overload databases. As task count increases, database connections often scale proportionally.

Example:

- 10 ECS tasks × 30 database connections/task = 300 connections.
- Scaling to 25 tasks can open 750 connections.
- If the database safely supports only 500 connections for this workload, application scale-out can cause the database to reject connections.

Verify:

- Connection pool sizing and connection reuse.
- Query latency, lock waits, deadlocks, and slow queries.
- Read/write IOPS, throughput, and storage latency.
- CPU, memory, and database connection count.
- Read replica lag and failover duration.
- Cache hit ratio and hot keys.
- Retry storms when the database slows down.

Max task/instance limits must align with database capacity. Consider RDS Proxy, caching, read replicas, queues, or application-tier concurrency caps.

## 28. Checking Service Quotas Before Capacity Testing

Service quotas often act as the real ceiling before compute or application code reaches saturation.

Check quotas for:

- EC2 instance vCPUs by family and Region.
- Fargate vCPUs, ECS tasks, and ENIs/subnet IPs.
- Lambda concurrency and request rate.
- API Gateway throttling.
- NAT Gateway connections/throughput.
- ALB target counts and connection behavior.
- RDS database connections/storage/IOPS.
- DynamoDB throughput and partition behavior.
- Kinesis shards/throughput or on-demand limits.
- SQS API throughput and message sizes.

If quota increases are needed, submit requests early enough before testing to allow processing. A test throttled by quotas does not mean application code reached its true breaking point.

## 29. Testing Resilience Under Load

Autoscaling does not replace high availability. Fault testing under load uncovers insufficient capacity headroom.

Scenarios:

- Terminating an EC2 instance or ECS task.
- An Availability Zone unable to accept traffic.
- A database reader failover.
- Cache node restart or connectivity loss.
- Stopping queue consumers.
- Downstream API returning errors or elevated latency.
- Load generator or one load-generating Region experiencing disruption.

Monitor SLOs during and after the fault, detection time, recovery time, queue backlog, and retry counts. Run fault injection only in approved environments with rollback/stop conditions.

AWS Fault Injection Service can help execute controlled experiments on supported resources. Use it to test resilience hypotheses while the load generator supplies realistic traffic pressure.

## 30. Testing in CI/CD and Regression Comparison

Not every commit needs an hour-long load test. You can tier tests:

| Pipeline Stage | Test | Typical Duration |
|---|---|---|
| Pull request | Smoke/performance sanity on core endpoints | A few minutes |
| Pre-release | Representative workload load test | 10–30 minutes |
| Release candidate | Capacity/spike/scale-out test | 30–90 minutes |
| Scheduled | Soak and multi-AZ resilience test | Several hours |
| Before major events | Peak forecast, quota, and recovery game day | Per plan |

Store baselines for p50/p95/p99, RPS, error rate, CPU/memory, and scale-out delay. Compare using the same environment, dataset, and test profile.

A regression is flagged when p95 exceeds allowed thresholds, error rates breach SLOs, or safe throughput drops significantly. Do not declare a regression from a single noisy run; repeat tests and inspect variance/confidence.

## 31. Reading Results and Pinpointing Bottlenecks

When SLOs are missed, trace bottlenecks from outside in:

1. Did the load generator produce the target RPS?
2. Did DNS/TLS/load balancers introduce latency?
3. Did the application hit CPU, memory, thread, or connection pool saturation?
4. Did databases/caches hit locks, IOPS, or connection bottlenecks?
5. Did queue backlogs grow continuously?
6. Did external APIs throttle or add high latency?
7. Did autoscaling trigger on time and quickly enough?
8. Did quotas or subnet IP exhaustion block new capacity creation?

Use distributed tracing to break down request duration across dependencies. A 900 ms p95 API call might spend 80 ms at the gateway, 120 ms in the application, 600 ms in the database, and 100 ms in an external API. Scaling the application tier will not fix a slow database query.

## 32. Troubleshooting Common Autoscaling Issues

| Symptom | Possible Cause | Resolution |
|---|---|---|
| High CPU yet no scaling | Policy attached to wrong scalable target, missing metric/alarm data, or max capacity reached | Check policies, CloudWatch alarms, desired/max capacity, and scaling activities |
| Scale-out starts too late | Long metric interval, overly high threshold, or long warmup/boot time | Use earlier-signaling metrics, cut startup time, add scheduled/predictive scaling |
| New instances marked unhealthy | Grace period too short, slow app boot, or misconfigured health check | Measure startup time, fix health checks and grace period |
| Instances increase yet latency stays high | Database, cache, network, or downstream service is the bottleneck | Use traces and dependency metrics to identify limits |
| Tasks fail placement | Insufficient Fargate/EC2 capacity, subnet IPs, CPU/memory, or quotas | Check ECS events, capacity providers, ENIs, and quotas |
| Repeated scale-out oscillations | Improper warmup, noisy metrics, or conflicting policies | Configure default instance warmup, smoothing, and consistent policies |
| Scale-in causes request errors | Improper connection draining/graceful shutdown | Fix deregistration delay, SIGTERM handling, and task shutdown |
| Fails to scale in under low load | High min capacity, alarm stuck out of OK, scale-in disabled, or another policy demands capacity | Inspect all policies and min/max capacity |
| Lambda throttled | Concurrency/RPS quotas or low reserved concurrency | Inspect Throttles, ConcurrentExecutions, and Service Quotas |
| Queue age rises despite more workers | Slow worker processing, poison messages, or downstream throttling | Check processing duration, DLQs, and downstream capacity |
| ALB p95 rises while CPU stays low | Network, connection, target response, or database slowness | Inspect TargetResponseTime, TargetConnectionErrorCount, and tracing |
| Test RPS lower than target | Generator CPU/network exhausted or closed model self-throttling | Distribute generators, check dropped iterations, and use open models |

## 33. Capacity and Autoscaling Report Template

Every test run should record:

| Field | Values to Record |
|---|---|
| Test ID / commit | Test identifier and application version |
| Environment | Account, Region, AZs, infrastructure configuration |
| Workload | User journeys, request mix, data volume, open/closed model |
| Load profile | Ramp-up, steady, spike, ramp-down, and durations |
| Peak achieved | RPS, concurrency, and successful request count |
| Latency | p50, p90, p95, p99 per journey |
| Errors | HTTP 4xx/5xx, timeouts, application errors, throttles |
| Capacity | Min/desired/max, task/instance counts, and database connections |
| Scaling | Trigger time, scale-out delay, scale-in delay, warmup |
| Bottlenecks | Limiting components and supporting evidence |
| Cost | Compute, database, load generators, logs, and data transfer |
| Decision | Pass/fail, recommended capacity, and follow-up actions |

Archive dashboards, raw test outputs, application logs, trace IDs, and scaling activity history so findings are reproducible.

## 34. End-to-End Example: Verifying ECS Service Autoscaling

A catalog API runs on ECS Fargate behind an Application Load Balancer. Benchmarks show each task safely handles 90 RPS at p95 under 250 ms. Expected peak demand is 900 RPS with 25% headroom, so capacity planning recommends 13 tasks. The service has min 3, max 16 tasks, and 55% CPU target tracking.

### Scenario

1. Run a smoke test at 20 RPS to validate scripts and test data.
2. Ramp load in steps: 100, 300, 600, 900 RPS.
3. Hold 900 RPS for 20 minutes.
4. Inject a spike to 1,200 RPS for 2 minutes.
5. Ramp down to 100 RPS, then to 0.
6. Repeat the cycle to check for scaling oscillation.

### Dashboard

- Load generator: actual RPS, VUs, dropped iterations.
- ALB: RequestCount, TargetResponseTime p95/p99, HealthyHostCount, target 5xx.
- ECS: CPUUtilization, MemoryUtilization, RunningTaskCount, service events.
- Application: request duration, thread/connection pools, errors.
- Database: CPU, connections, read/write latency, and query waits.
- Application Auto Scaling: scaling activities and desired task count.

### Pass Criteria

- 900 RPS for 20 minutes, p95 under 250 ms, p99 under 700 ms.
- Error rate under 0.5%.
- Service scales out to at least 13 tasks before sustained SLO breaches.
- All new tasks become healthy and receive traffic through the ALB.
- The 1,200 RPS spike does not cause total service loss; if SLOs dip briefly, recovery falls within the agreed target.
- After ramp-down, the service scales back to min 3 tasks without 5xx spikes or dropped requests.
- Databases and downstream dependencies remain within safe capacity.

If CPU stays low while latency rises, do not blindly keep adding tasks. Use tracing and database metrics to find the bottleneck. If target tracking reacts too slowly, review the metric, target value, metric interval, task startup time, and scheduled scaling.

~~~mermaid
flowchart TD
    A[Define SLO and workload] --> B[Build production-like environment]
    B --> C[Benchmark each dependency]
    C --> D[Estimate safe capacity]
    D --> E[Configure autoscaling and warmup]
    E --> F[Generate distributed load]
    F --> G[Observe app, ALB, compute and database]
    G --> H{SLO and scaling pass?}
    H -->|No| I[Find bottleneck and tune]
    I --> F
    H -->|Yes| J[Save baseline and capacity report]
~~~

## 35. Pre-Production Capacity Confirmation Checklist

- [ ] SLOs for throughput, latency, error rate, and recovery are agreed upon.
- [ ] Workload mix represents real user journeys.
- [ ] Appropriate open/closed model is chosen and actual arrival rate is recorded.
- [ ] Test environment closely mirrors production.
- [ ] Test data is synthetic or sanitized.
- [ ] Load generator is not a bottleneck.
- [ ] Service quotas, subnet IPs, and dependency limits have been checked.
- [ ] Sustainable capacity of each component has been benchmarked.
- [ ] Headroom and failover capacity exist for losing an AZ/instance.
- [ ] Autoscaling metrics scale appropriately with capacity.
- [ ] Min/max capacity, target values, and scaling policies have been verified.
- [ ] Default instance warmup and health check grace period are based on measurements.
- [ ] Both scale-out and scale-in have been tested.
- [ ] CloudWatch dashboards/alarms cover ALB, compute, databases, queues, and Lambda.
- [ ] Throttling, backlogs, 5xx errors, and tail latency have been inspected.
- [ ] Relevant spike, soak, and failure scenarios have been tested.
- [ ] Stop conditions and an active test observer are in place.
- [ ] Results include raw artifacts, scaling history, and reports.
- [ ] Test cost and peak capacity cost have been estimated.
- [ ] Baselines and regression thresholds exist for future releases.

## 36. Key Takeaways

Load testing verifies the application meets expected workloads; capacity testing determines sustainable throughput and limits; and autoscaling testing proves the system expands and shrinks capacity on time. Reliable results require clear SLOs, realistic user journeys, safe data, and production-like environments.

Capacity must be calculated from benchmarks within the SLO-compliant region, incorporating headroom and reserve for dependency or AZ failures. Autoscaling metrics must reflect scalable target utilization; target tracking usually fits fluctuating workloads, while scheduled/predictive scaling prepares capacity ahead of peaks. Instance warmup, health-check grace period, and cooldown address distinct problems and must be tuned from actual initialization times and observed behavior.

CloudWatch, ALB metrics, ECS/EC2/Lambda metrics, database telemetry, queue age, and load generator output must be analyzed together. When scaling out fails to reduce latency, look for bottlenecks in dependencies or quotas before adding more compute. Retain baselines, capacity reports, and scaling history to make performance verification a repeatable part of your release process.

## References

- [AWS Well-Architected: Load Test Your Workload](https://docs.aws.amazon.com/wellarchitected/2024-06-27/framework/perf_process_culture_load_test.html)
- [AWS Well-Architected: Test Scaling and Performance Requirements](https://docs.aws.amazon.com/wellarchitected/2024-06-27/framework/rel_testing_resiliency_test_non_functional.html)
- [Distributed Load Testing on AWS](https://docs.aws.amazon.com/solutions/latest/distributed-load-testing-on-aws/solution-overview.html)
- [Distributed Load Testing on AWS Features](https://docs.aws.amazon.com/solutions/latest/distributed-load-testing-on-aws/features.html)
- [AWS Prescriptive Guidance: Load Testing Tools](https://docs.aws.amazon.com/prescriptive-guidance/latest/load-testing/tools.html)
- [Target Tracking for Amazon EC2 Auto Scaling](https://docs.aws.amazon.com/autoscaling/ec2/userguide/as-scaling-target-tracking.html)
- [Default Instance Warmup for EC2 Auto Scaling](https://docs.aws.amazon.com/autoscaling/ec2/userguide/ec2-auto-scaling-default-instance-warmup.html)
- [EC2 Auto Scaling Cooldowns](https://docs.aws.amazon.com/autoscaling/ec2/userguide/ec2-auto-scaling-scaling-cooldowns.html)
- [EC2 Auto Scaling Health Check Grace Period](https://docs.aws.amazon.com/autoscaling/ec2/userguide/health-check-grace-period.html)
- [Step and Simple Scaling Policies](https://docs.aws.amazon.com/autoscaling/ec2/userguide/as-scaling-simple-step.html)
- [Application Auto Scaling Target Tracking](https://docs.aws.amazon.com/autoscaling/application/userguide/application-auto-scaling-target-tracking.html)
- [How Target Tracking Scaling Works](https://docs.aws.amazon.com/autoscaling/application/userguide/target-tracking-scaling-policy-overview.html)
- [Create a Target Tracking Policy for ECS](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/target-tracking-create-policy.html)
- [ECS Service Auto Scaling Target Tracking](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service-autoscaling-targettracking.html)
- [ECS Service Utilization Metrics](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service_utilization.html)
- [CloudWatch Metrics for Application Load Balancers](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/load-balancer-cloudwatch-metrics.html)
- [Lambda Scaling Behavior](https://docs.aws.amazon.com/lambda/latest/dg/scaling-behavior.html)
- [Understanding Lambda Concurrency](https://docs.aws.amazon.com/lambda/latest/dg/lambda-concurrency.html)
- [Lambda Quotas](https://docs.aws.amazon.com/lambda/latest/dg/gettingstarted-limits.html)
- [Monitor Application Auto Scaling with CloudWatch](https://docs.aws.amazon.com/autoscaling/application/userguide/monitoring-cloudwatch.html)
