# Limiting Concurrency to Protect Downstream Systems

Serverless can spin up additional execution environments or instances when request volume increases. Rapid scaling helps applications handle sudden traffic spikes, but it can also push too many simultaneous requests to databases, third-party APIs, payment systems, or internal services. Those downstream systems typically have lower connection limits, throughput caps, and processing capacities than the scaling capability of the serverless layer.

A concurrency limit sets a ceiling on the number of executions or requests processed simultaneously. When chosen properly, the application leverages elastic scaling while keeping load within what dependencies can tolerate. A limit set too high can cause cascading bottlenecks; a limit set too low increases wait times, queue depth, and latency even when downstream capacity remains available.

After this lesson, you will be able to:

- Distinguish concurrency from request rate and instance count.
- Estimate safe concurrency based on processing duration and dependency limits.
- Configure limits at the serverless platform, API gateway, and queue consumer layers.
- Verify throttling, queue depth, database connections, and retry behavior under overload.

## 1. What Is Concurrency?

Concurrency is the number of tasks being processed at the same point in time. For a serverless function handling HTTP requests, an active invocation typically occupies one unit of function concurrency. For serverless container platforms like Cloud Run, a single instance may handle multiple concurrent requests; in that case, service concurrency depends on both the instance count and maximum requests per instance.

Three concepts must be kept distinct:

- **Concurrency:** the number of requests or tasks running at the same time.
- **Request rate/throughput:** the number of requests received or completed per second, typically measured in requests per second (RPS).
- **Instance count:** the number of execution environments or instances currently existing. One instance may handle one or multiple concurrent requests depending on the runtime and configuration.

Concurrency and RPS are related, but not interchangeable. By Little's Law, in steady state:

\[
L = \lambda \times W
\]

Where:

- `L` is the average number of requests inside the system.
- `λ` is the average arrival rate, in requests per second.
- `W` is the average time a request spends in the system, in seconds.

For example, a service receiving an average of 100 requests/second where each request takes 0.5 seconds has an average concurrency of roughly 50. If processing time increases to 2 seconds while RPS stays constant, average concurrency jumps to around 200. When a dependency slows down, requests stay in the system longer and occupy slots longer; this is why a database slowdown can sharply spike concurrency.

Average-based numbers are only a starting point. When designing limits, measure peak load, processing time distributions, bursts, connection pool wait times, and capacity reserved for other applications. Never adopt a simple average as a production limit without load testing.

## 2. Why Do Downstream Systems Need Protection?

Suppose an order-processing function scales up to hundreds of execution environments. Each execution calls a database to read inventory, write an order, and update payment status. The database only has a finite number of connections. If every execution environment opens connections simultaneously, the database can exhaust connections, increase wait times, reject connections, or saturate CPU and I/O.

A typical failure cascade unfolds as follows:

1. Incoming traffic spikes suddenly.
2. The serverless platform scales out executions to handle requests.
3. Many execution environments call the downstream database or API concurrently.
4. The dependency hits its connection or throughput limit, causing response times to climb.
5. Invocations hold resources longer; the number of active in-flight requests continues rising.
6. Timeouts and retries generate extra load, prolonging overload even after the initial traffic spike subsides.

Concurrency limits break this amplification loop by capping how much work is allowed deeper into dependencies. Excess load beyond capacity can be throttled, buffered in queues, or rejected gracefully depending on the architecture.

Dependencies to evaluate include databases and connection pools, caches, search engines, partner APIs, email/SMS providers, payment systems, filesystems, or throughput-limited storage services. Each dependency may need its own limit; a single global concurrency cap for the entire application may not suffice.

## 3. Estimating Safe Limits

Start from the capacity of the weakest dependency along the processing path. For a database, evaluate maximum allowed connections, connections reserved for other workloads, per-instance pool size, and the query rate the database can sustain steadily.

A simple connection-budget calculation:

\[
 C_{\text{app}} \leq \frac{D - R - H}{P}
\]

Where:

- `D`: maximum connections allowed by the database.
- `R`: connections expected to be reserved for other applications or tasks.
- `H`: headroom reserved for administration, migrations, and variance.
- `P`: maximum connections each execution environment or instance may hold.
- `C_app`: maximum execution environments that can exist without exceeding the calculated connection budget.

Example: a database allows up to 120 connections. Reserve 30 connections for other services and admin tasks, and keep 20 connections as headroom. The serverless application has a budget of 70 connections. If each execution environment holds at most one connection, the theoretical ceiling is 70 environments. The team might begin testing at 50 or 60 to retain buffer. If each environment uses a pool of up to two connections, the maximum environments must drop to at most 35 under this calculation.

For platforms handling multiple requests per instance, account for both concurrency and pooling. For instance, a service has up to 10 instances, each accepting up to 5 concurrent requests, allowing 50 concurrent requests across this configuration. If each instance maintains a database pool of up to 4 connections, the pool ceiling is 40 connections. The two limits govern different resources: concurrency limits active work, while the pool limits open connections per instance.

You can use Little's Law to validate target throughput. If the downstream system reliably handles 80 requests/second and average processing time is 0.25 seconds, average concurrency is roughly 20. However, during bursts or higher latency, required concurrency rises. Clearly define your goals: limits to protect dependencies, latency targets, and required throughput. If all three cannot be met simultaneously, increase dependency capacity, reduce per-request work, or adjust SLAs.

Practical workflow:

1. Measure baseline load, peak load, bursts, and processing duration of each dependency.
2. Identify quotas, connection limits, throughput, and rate limits for every dependency.
3. Calculate connection and concurrency budgets, factoring in other applications sharing the dependency.
4. Pick an initial value below the theoretical limit to preserve headroom.
5. Run incremental load tests, monitoring latency, errors, connection pools, and dependency CPU/I/O.
6. Tune limits until target throughput is achieved while the dependency remains stable.

## 4. At Which Layers Should Limits Be Placed?

A system can apply multiple layers of control. Each layer protects a distinct boundary:

| Layer | Mechanism | Purpose |
|---|---|---|
| API gateway/ingress | Rate limit, burst limit, per-client or per-tenant quota | Block excessive traffic before invoking functions |
| Function/service | Reserved concurrency, maximum instances, concurrency per instance | Cap executions or requests entering the workload |
| Application | Semaphores, worker bounds, connection pools | Limit concurrent calls to a specific dependency |
| Queue consumer | Maximum concurrency, consumer count, or batch size | Pace message consumption and smooth bursts |
| Dependency | Connection limits, query limits, quotas, rate limits | Protect resources directly at the receiving system |

Place limits close to where the resource can be measured and controlled. For example, a function calling two dependencies with different capacities may need separate semaphores per dependency. Function-wide concurrency limits remain useful for bounding total invocations, but they do not replace per-pool or partner API limits.

### Distinguishing Concurrency Limits and Rate Limits

A concurrency limit bounds how many requests run simultaneously. A rate limit bounds how many requests are accepted over a time interval. A service allowing 20 concurrent requests where each takes only 0.1 seconds can process roughly 200 RPS in steady state. If each request takes 2 seconds, throughput drops to roughly 10 RPS. Thus, a concurrency cap does not automatically enforce an RPS ceiling.

If a partner only permits 50 requests/second, place a rate limiter or token bucket at the layer calling the partner, even if function concurrency is already capped. Conversely, a per-minute rate limit might still allow a huge burst within a few milliseconds; a concurrency cap bounds how many tasks consume resources at the exact same instant.

## 5. Configuration Examples Across Serverless Platforms

Naming and configuration scopes vary by provider. Check quotas for your account, region, and runtime before deploying.

### AWS Lambda

In Lambda, reserved concurrency sets the maximum concurrency for a function while also reserving that capacity for the function within the account. This is useful for protecting databases: if a function has reserved concurrency set to 40, it will not scale beyond 40 concurrent invocations. When demand exceeds this cap, invocations may be throttled or handled by the event source's retry/queue mechanism.

Example setting reserved concurrency via AWS CLI:

```bash
aws lambda put-function-concurrency \
  --function-name orders-handler \
  --reserved-concurrent-executions 40
```

For Lambda consuming events from Amazon SQS, the event source mapping can set maximum concurrency to limit how much parallelism the poller uses for that queue. If a function has multiple event source mappings, compare the sum of their maximum concurrency settings against the function's reserved concurrency. If the combined limits of event sources exceed reserved concurrency, they can compete and cause function-level throttling.

API Gateway can enforce throttling at the stage or method level to control rate and burst before requests reach Lambda. Provisioned concurrency keeps initialized execution environments warm to reduce cold starts; it is not a database protection mechanism. Distinguish provisioned concurrency from reserved concurrency: one pre-warms environments, while the other caps and reserves concurrency for the function.

### Google Cloud Run

Cloud Run has two parameters to coordinate:

- **Concurrency per instance:** maximum concurrent requests a single instance receives.
- **Maximum instances:** maximum instances the service is allowed to create.

For example, setting concurrency to 5 and maximum instances to 10 caps the theoretical ceiling at roughly 50 concurrent requests across the service. If the application uses a database pool of 4 connections per instance, pools can open up to roughly 40 connections when all instances are active. Check actual pool limits and other clients sharing the database.

Setting concurrency too high can cause CPU or memory contention within an instance, increasing response times. Setting maximum instances too high can overload the database when the service scales out. Tune both based on load testing and pool settings, then check regional quotas and limits.

### Azure Functions

Azure Functions provides scale-out limits depending on hosting plan and host/trigger configuration. For message-processing triggers, extension concurrency settings can cap how many messages are processed in parallel per host; instance count limits control overall scale-out. Setting names and scopes depend on the trigger, extension, and hosting plan.

For example, with the Azure Service Bus trigger, `maxConcurrentCalls` in extension settings controls how many concurrent messages a single instance processes for a function. This limit must be evaluated alongside maximum instance count and downstream database capacity. Never assume a single setting in `host.json` behaves identically across all triggers or plans; consult the documentation for the specific extension in use and validate via metrics during test runs.

## 6. Using Queues to Absorb Bursts

If downstream systems cannot handle all incoming load immediately, queues decouple ingestion rate from processing rate. An API can validate and enqueue a message and return an accepted response; a pool of serverless consumers reads messages under a bounded maximum concurrency.

For example, a sales campaign generates 2,000 order requests in a short window, while the database safely handles only 100 writes per second. The API enqueues the work. Consumers are capped to process near the database's safe capacity. The queue absorbs the temporary excess load; the backlog drains whenever processing rate exceeds incoming message rate.

Queues do not create extra processing capacity. If arrival rate stays permanently higher than processing rate, queue depth and message age climb continuously. Monitor queue depth, oldest message age, and completion times; when thresholds are crossed, shed incoming load, scale downstream capacity if headroom exists, or surface degraded status to clients.

For asynchronous consumers, also design:

- Idempotent processing so redelivered messages do not create duplicate transactions.
- Visibility timeouts or lock durations long enough for expected processing times.
- Bounded retries and dead-letter queues for persistently failing messages.
- Appropriate batch sizes so a single invocation does not spawn excessive parallel operations.
- Message acknowledgment only after successful processing per queue semantics.

## 7. Backpressure, Timeouts, and Retries

When concurrency limits are reached, the system must respond clearly. For synchronous requests, return `429 Too Many Requests` when a client exceeds quota or `503 Service Unavailable` when the service temporarily cannot accept more load. When appropriate, return `Retry-After` to guide clients on when to retry. Avoid accepting requests and letting them queue indefinitely in memory.

For asynchronous work, route jobs to a queue and control consumer pace. This is backpressure: processing speed adapts to real downstream capacity. At the application layer, semaphores or bounded worker pools cap concurrent operations per dependency; in-process bounded queues must have capacity caps to avoid unbounded memory growth.

Retries help recover from transient glitches, yet immediate unbounded retries amplify load. Apply exponential backoff with jitter, max attempts, and overall deadlines. Retry only recoverable errors; honor `Retry-After` on `429` or `503` responses. For writes, use idempotency keys or deduplication. When attempts are exhausted, route messages to a dead-letter queue or record them for manual handling.

Timeouts must also align with concurrency. Overly long timeouts hold slots and connections while a dependency is unresponsive; overly short timeouts trigger retries even when the dependency could still succeed. Keep per-call timeouts shorter than the overall invocation deadline, release connections on timeout, and avoid uncoordinated multi-layer retries without a shared retry budget.

## 8. Limit Design Example for an Order API

Suppose `orders-api` runs on a serverless function platform. Each invocation reads inventory and writes orders to a database. The database permits 120 connections; 30 connections are reserved for other services and 20 for headroom. Thus, the application has a 70-connection budget. The team decides each execution environment holds at most one connection and sets an initial concurrency limit of 50.

The processing flow is designed as follows:

1. API gateway enforces per-client rate limits and burst limits to protect the entry point.
2. The function has a concurrency cap of 50 to bound concurrent invocations.
3. Each execution environment's connection pool is capped at 1 connection with a finite acquisition timeout.
4. Order writes can be offloaded to a queue when async processing fits; consumers have their own maximum concurrency.
5. When the database slows down, the function enforces timeouts, avoids aggressive retries, and returns appropriate status or lets the queue retry per policy.
6. Dashboards monitor concurrency, throttles, duration, errors, active connections, pool wait times, and queue depth.

A limit of 50 is a starting point for testing, not a guarantee the database can always sustain 50 concurrent transactions. A single invocation might run multiple queries, queries might hold connections longer, or other workloads might share the database. The team must ramp load incrementally and adjust based on measured results.

## 9. Verifying Limits in Practice

Before releasing, execute testing in phases:

1. **Baseline:** run low load to measure latency, throughput, connection counts, CPU, memory, and pool wait times when dependencies are healthy.
2. **Ramp-up:** gradually increase clients or request rate; verify concurrency stays within the cap and dependencies stay within budget.
3. **Burst:** send a short burst exceeding processing capacity; verify gateway throttling, queue buffering, or overload responses behave as designed.
4. **Dependency slowdown:** simulate slow downstream databases/APIs or `429`/`503` responses; verify timeouts, backpressure, and bounded retries.
5. **Recovery:** restore the dependency and confirm backlogs drain, errors drop, and the system avoids a retry storm.
6. **Fairness:** if serving multiple tenants or event sources, verify one client cannot monopolize all concurrency and starve others.

Metrics to observe:

| Area | Metrics to Monitor | Warning Signs to Investigate |
|---|---|---|
| Serverless | Concurrent executions/requests, active instances, throttles, duration, errors | Sustained ceiling concurrency, rising throttles, abnormal duration spikes |
| API gateway | Request rate, burst, `429`, `5xx`, latency | Bursts exceeding quota, errors rising before reaching the function |
| Database | Active/max connections, CPU, I/O, lock waits, query latency | Connections nearing limit, slow queries, growing lock waits |
| Connection pool | Active/idle connections, pending acquisitions, wait time, timeouts | Many invocations waiting for connections while database is below limit |
| Queue | Visible messages, oldest message age, receive count, dead-letter count | Backlog or message age rising continuously |
| Retry | Attempt count, retry rate, timeouts, `429`/`503` from dependencies | Attempts climbing faster than completed tasks |

Set alerts for sustained ceiling concurrency, sudden throttle spikes, connections nearing limits, high pool wait times, queue age breaching SLAs, and rising dead-letter counts. Base alert thresholds on workload baselines rather than a single generic number.

## Safe Configuration Checklist

- [ ] Distinguished concurrency, RPS, and instance count in the design.
- [ ] Identified the most constrained dependency and its real quotas.
- [ ] Accounted for connections reserved for other workloads, headroom, and per-instance pool sizes.
- [ ] Configured concurrency caps or maximum instances on the serverless platform.
- [ ] Configured gateway rate/burst limits when dependencies enforce RPS caps.
- [ ] Bounded pools, semaphores, or parallel workers at the application layer.
- [ ] Configured maximum concurrency and backlog policies for queue consumers.
- [ ] Configured timeouts, retries with backoff/jitter, idempotency, and dead-letter handling.
- [ ] Tested ramp-up, bursts, dependency slowdowns, and recovery.
- [ ] Built dashboards and alerts for throttles, connections, pool waits, queue age, and retries.

Limiting concurrency is part of capacity planning and fault tolerance. Set limits based on measured dependency resilience, combine rate limits and backpressure at the right layers, and validate with load testing. Whenever downstream capacity changes, re-measure and adjust limits and related alerts.
