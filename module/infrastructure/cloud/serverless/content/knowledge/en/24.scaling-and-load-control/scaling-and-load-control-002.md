# Understanding autoscaling, burst traffic, and instance provisioning speed

Autoscaling enables a serverless platform to increase or decrease the number of execution environments/instances based on demand. When traffic rises, the platform spins up additional capacity to process requests or messages in parallel; when traffic drops, excess capacity is reclaimed. This mechanism reduces the burden of managing servers manually, but it does not mean capacity grows instantaneously or infinitely.

Three factors must be distinguished: **the required concurrency level**, **the speed at which the platform provisions additional instances**, and **the time it takes for a new instance to become ready to handle requests**. A system may have a large enough concurrency limit yet still experience throttling or high latency during a sudden burst because capacity takes time to initialize. Java functions can also incur cold starts due to JVM startup, class loading, dependency injection, and SDK initialization.

In the **CLOUD_SERVERLESS** module, learners build Java functions triggered by HTTP, messages, or events while handling state, access control, retries, idempotency, cold starts, scaling, and cost. This lesson explains autoscaling, burst traffic, instance provisioning speed, load-control limits, and how to test capacity before production.

## 1. How does autoscaling work?

Autoscaling is the process of adjusting capacity according to observed load. With FaaS, the provider typically manages execution environments and the number of invocations running in parallel. With serverless container platforms, an autoscaler may adjust the number of instances/containers based on request concurrency, CPU, memory, or other signals.

A generalized autoscaling loop:

~~~mermaid
flowchart TD
    A[Incoming requests / messages] --> B[Measure demand]
    B --> C{Capacity available?}
    C -->|Yes| D[Route to ready instances]
    C -->|No| E[Request more capacity]
    E --> F[Provision and initialize]
    F --> G[Ready instances]
    G --> D
    D --> H[Process work]
    H --> I[Observe load and latency]
    I --> B
    I --> J{Demand stays low?}
    J -->|Yes| K[Scale in after policy delay]
    J -->|No| B
~~~

An autoscaler usually does not look at a single individual request alone. It uses signals such as pending requests, concurrency, CPU, queue backlog, unprocessed message count, or instance utilization. Policies then decide when to scale out, how much capacity to add, and when to scale in.

The steps of measuring load, making a decision, and provisioning instances all introduce latency. Therefore, the design must account for the interval before new capacity becomes ready, especially when traffic grows faster than scale-out capability.

## 2. Distinguishing request rate, concurrency, throughput, and instance count

These concepts are related but not interchangeable:

| Concept | Meaning | Common units |
|---|---|---|
| Request rate | Number of requests arriving per unit of time | requests/second (RPS) |
| Concurrency | Number of requests or invocations running at the same time | concurrent requests/invocations |
| Throughput | Number of work items completed per unit of time | requests/second, messages/second |
| Instance count | Number of active execution environments or container instances | instances |
| Provisioning rate | Speed at which new instances are created and brought to ready state | instances/second |
| Startup latency | Time from initialization start until the instance is ready | milliseconds/seconds |

For example, 100 RPS does not necessarily require 100 instances. If each request completes in 100 ms and an instance handles one request at a time, average concurrency is roughly 10. If a container can handle 10 concurrent requests, the required number of containers may be even lower, depending on CPU, memory, and application performance.

With AWS Lambda, a typical execution environment processes one invocation at a time; scaling concurrency generally means needing additional execution environments. With serverless containers like Cloud Run, a single instance can receive multiple concurrent requests depending on its concurrency setting and the application's thread safety. Do not apply a single instance-to-concurrency conversion rule across all platforms.

## 3. Estimating concurrency with Little’s Law

A useful initial estimate is:

\[
C \approx \lambda \times W
\]

Where:

- \(C\): average number of requests currently being processed (concurrency).
- \(\lambda\): incoming request rate, measured in requests/second.
- \(W\): average processing time, measured in seconds.

For example, an API receives 400 RPS and has an average processing time of 250 ms:

\[
C \approx 400 \times 0.25 = 100
\]

The system needs roughly 100 concurrently running requests under steady conditions. If you want headroom for fluctuations, you can test at 120–150 concurrency and re-measure; the reserve factor must be based on SLAs, latency distribution, and downstream limits, not a fixed constant for every system.

### Why not use only the average?

The average can hide tail latency. If most requests take 100 ms but a few take 3 seconds, p95/p99 can be much higher. Those slow requests occupy concurrency slots longer, causing active requests to climb even when RPS stays constant.

Measure at a minimum:

- RPS over time and per route.
- p50, p95, and p99 duration.
- Concurrent requests/invocations.
- Timeout, 429, 5xx, and throttling rates.
- CPU, memory, connection pools, and dependency latency.
- Queue backlog/oldest message age for async workloads.

For systems with diverse request types, calculate capacity per route group or workload class. An endpoint making slow database calls may require far more concurrency than an endpoint that only returns cached responses.

## 4. Concurrency does not equal throughput

Concurrency measures how many items are running simultaneously; throughput measures how many items complete per unit of time. If request duration increases, the same concurrency yields lower throughput.

Example:

| Concurrency | Average duration | Approximate theoretical throughput |
|---:|---:|---:|
| 50 | 100 ms | 500 RPS |
| 50 | 250 ms | 200 RPS |
| 50 | 1 s | 50 RPS |

This is an estimate for a stable workload, not a benchmark. CPU saturation, lock contention, downstream limits, and batching can reduce actual throughput.

A system that scales out when latency rises may not improve throughput if every instance is waiting on the same overloaded database. In that case, adding more functions only increases connection counts and resource contention. Autoscaling must be coordinated with downstream limits.

## 5. Scale-out and scale-in

**Scale-out** increases the number of execution environments/instances when load exceeds current capacity. **Scale-in** reduces capacity when demand stays low for a period of time.

Fast scale-out helps absorb bursts, but spinning up too many instances at once can cause:

- Increased cold starts.
- Many simultaneous connections to databases.
- Pressure on secret managers, caches, or external APIs.
- Quota-induced throttling.
- Sudden cost spikes.

Scaling in too aggressively can cause oscillation: capacity gets reclaimed, traffic picks up again, and everything must initialize from scratch. For long-running workloads or queue consumers, scale-in also needs to ensure in-flight requests/messages finish or can be safely retried.

Autoscalers typically use thresholds, measurement windows, cooldowns, or stabilization policies to avoid constant capacity churn. Parameter names and semantics depend on the provider.

## 6. Instance provisioning speed differs from concurrency limits

A system may allow up to 1,000 concurrent invocations yet be unable to provision 1,000 execution environments at the exact same instant. The concurrency limit defines the maximum allowed; the provisioning rate defines how fast capacity is added over time.

Generalized model:

- \(C_{target}\): target concurrency to reach.
- \(K\): number of concurrent requests one instance can handle effectively.
- \(N_{target}\): number of instances required.
- \(R_p\): provisioning rate of new instances.
- \(T_i\): initialization time for a new instance.

Instance count estimate:

\[
N_{target} \approx \left\lceil \frac{C_{target}}{K} \right\rceil
\]

If scaling from \(N_{current}\) to \(N_{target}\), the additional instances needed are:

\[
\Delta N = \max(0, N_{target} - N_{current})
\]

In a very simple linear model, the time to provision additional capacity can be approximated as:

\[
T_{scale} \approx \frac{\Delta N}{R_p} + T_i
\]

This is only a mental model. Providers may use multiple pools, burst allowances, regional quotas, nonlinear scaling algorithms, and multi-step initialization. Do not assume a fixed provisioning rate unless the provider publishes it or you have measured it in the exact account/Region.

### Example

A container effectively handles 8 concurrent requests. The application needs to scale from 5 to 45 instances, adding 40 instances. If measurements in a test environment show the system typically provisions 10 instances/second and startup takes 0.8 seconds on average, the approximate theoretical time is:

\[
T_{scale} \approx \frac{40}{10} + 0.8 = 4.8 \text{ seconds}
\]

In practice, it may take longer due to quotas, scheduling, image pulls, JVM initialization, network setup, and downstream readiness. Therefore, bursts must be tested rather than merely calculated on paper.

## 7. Burst traffic, ramp traffic, and sustained traffic

Not all traffic surges look the same:

| Load pattern | Description | Primary risk |
|---|---|---|
| Burst/spike | Jumps very rapidly within seconds | Capacity cannot provision in time |
| Ramp-up | Increases steadily over time | Scale-out lags behind load growth rate |
| Sustained peak | Holds high load for a long period | Quotas, downstream capacity, and cost |
| Periodic peak | Rises by hour/day or scheduled events | Insufficient baseline capacity before peak hours |
| Flash crowd | Many clients hit simultaneously due to an event | Thundering herd and retry storms |
| Sudden drop | Load falls rapidly after a peak | Delayed scale-in, idle excess capacity, and cost |

A system capable of handling 500 steady RPS may not survive a jump from 20 to 500 RPS in 100 ms. In the first case, the autoscaler has time to observe and expand. In the second case, requests arrive before new capacity is ready.

### Illustrative load curves

~~~mermaid
xychart-beta
    title "Three traffic growth patterns"
    x-axis ["t0", "t1", "t2", "t3", "t4", "t5"]
    y-axis "Relative load" 0 --> 100
    line [10, 12, 20, 35, 55, 70]
    line [10, 10, 95, 95, 20, 10]
    line [10, 25, 45, 65, 85, 100]
~~~

This chart only illustrates load shapes. When designing, use real traffic profiles from access logs, campaign calendars, or load tests to determine spike magnitude, ramp rate, and peak duration.

## 8. Why do bursts cause throttling even when quota remains?

Suppose a function has 20 ready execution environments. Traffic spikes suddenly so required concurrency jumps to 500. If the platform only adds capacity at a bounded rate and each environment takes time to initialize, a portion of requests will arrive before new capacity is ready.

These requests may:

- Wait in an internal gateway queue if the service supports queuing.
- Receive throttling or 429/503 responses.
- Time out at the client before the function starts.
- Be retried by the client or event source.
- Create duplicate load when many clients retry at once.

Retries can worsen a burst. If all 500 failed requests are retried immediately by clients, the system can get hit with another wave of similar size while already short on capacity. Use exponential backoff, jitter, retry budgets, and idempotency to curb this effect.

Do not treat throttling solely as an error requiring higher concurrency. Identify whether requests are being blocked at the API gateway, account quota, function concurrency, event source mapping, or downstream dependencies.

## 9. Cold starts and readiness speed of Java functions

A cold start is the time required to create a new execution environment and bring the application into a state ready to accept requests. For Java, initialization tasks may include:

- Runtime/JVM startup.
- Class loading and dependency resolution.
- Dependency injection container initialization.
- Creating clients for databases, queues, object storage, and secret managers.
- Reading configuration, certificates, or schemas.
- JIT compilation and warm-up of certain code paths.
- Establishing network connections.

Cold start duration depends on the runtime, artifact size, framework, allocated memory/CPU, initialization strategy, and platform. You cannot conclude that Java is always slower than every other language; measure under the same workload and deployment configuration.

### Reducing initialization time

- Keep dependencies minimal; avoid pulling in a massive framework for a small handler.
- Initialize shared clients outside the handler when the runtime allows environment reuse.
- Avoid synchronous calls to multiple services in static initializers unless strictly necessary.
- Use appropriately sized connection pools and manage timeouts.
- Shrink artifact size and remove unused dependencies.
- Choose suitable memory/CPU settings and benchmark them.
- Use Java runtime optimizations or snapshot features if the provider supports them and the workload fits.
- Measure init duration separately from business execution duration.

Initializing clients outside the handler can reduce overhead for subsequent invocations, but environments can be reclaimed at any time. Do not store unique business state in static fields or temporary filesystems.

## 10. Warm capacity, minimum instances, and provisioned concurrency

There are several ways to maintain ready capacity:

- **Minimum instances/min replicas:** keep a minimum number of container instances running.
- **Provisioned concurrency:** the provider pre-initializes a number of execution environments for a function/alias/version.
- **Scheduled scaling:** increase baseline capacity on a schedule before peak hours.
- **Pre-warming:** send preparatory traffic or tasks before a peak arrives, if platform and policies allow.

Provisioned/warm capacity reduces the probability that requests wait on cold starts, but it does not guarantee zero latency for every request. When load exceeds warm capacity, overflow requests still undergo normal scale-out. Networks, dependencies, and application processing can still be slow.

### Terraform example for AWS Lambda

~~~hcl
resource "aws_lambda_function" "orders" {
  function_name = "orders-api"
  role          = aws_iam_role.lambda_exec.arn
  runtime       = "java21"
  handler       = "com.example.OrderHandler"
  filename      = "build/orders.zip"
  publish       = true

  # Maximum concurrency limit reserved for the function.
  reserved_concurrent_executions = 120
}

resource "aws_lambda_alias" "live" {
  name             = "live"
  function_name    = aws_lambda_function.orders.function_name
  function_version = aws_lambda_function.orders.version
}

resource "aws_lambda_provisioned_concurrency_config" "live" {
  function_name                     = aws_lambda_function.orders.function_name
  qualifier                         = aws_lambda_alias.live.name
  provisioned_concurrent_executions = 30
}
~~~

This is an illustrative example. The alias must point to a valid published version; Terraform resources/function versions should be structured according to the project's release workflow. Reserved concurrency caps the function's total concurrency, while provisioned concurrency pre-warms a subset of initialized environments. Both limits must be planned together and aligned with account/Region quotas.

### Warm-up pings are not a guarantee

Sending periodic requests to "keep warm" a function does not guarantee production requests will land on those exact environments. The platform may spin up different environments, reclaim old ones, or route traffic differently. Warm-up pings also consume invocations and can incur costs. Use official capacity features when predictable latency is needed.

## 11. Concurrency limits and admission control

Autoscaling needs guardrails to protect the system. Common mechanisms include:

- **Account/Region concurrency quota:** total concurrent invocations allowed within an account/Region.
- **Reserved concurrency:** dedicating or capping a function's concurrency on supported platforms.
- **Maximum instances:** capping the instance count of a service/container.
- **Maximum concurrency per instance:** capping concurrent requests per container.
- **Event source maximum concurrency:** capping consumer concurrency from a queue/stream if supported by the source.
- **API rate limits:** throttling request rates per client, route, or tenant.
- **Admission control:** rejecting or delaying requests before the system becomes overloaded.

A low cap protects databases but can raise backlogs or throttling. A high cap enables rapid scaling but can crash downstream services. Choose limits based on the real capacity of the entire dependency chain.

### Instance limit example for serverless containers

On serverless container platforms, you can configure minimum and maximum instance counts along with concurrency per instance. Setting names vary across providers. The principle is to compute:

\[
C_{max} \approx N_{max} \times K_{instance}
\]

Where \(K_{instance}\) is the benchmarked effective concurrency, not necessarily the configured max concurrency. If a Java application has a global lock or a small database pool, effective concurrency may be far lower.

## 12. Rate limiting and token buckets

Rate limiting regulates request arrival rates before they overload functions or dependencies. Token bucket is a common model:

- A bucket holds at most \(B\) tokens.
- Tokens are replenished at a rate of \(r\) tokens/second.
- Each request consumes one or more tokens.
- When the bucket runs out of tokens, requests are delayed or rejected according to policy.

The bucket allows a short burst up to capacity \(B\) while keeping the average rate near \(r\).

For example, a tenant may be allowed an average of 100 requests/second with a burst capacity of 200. An instantaneous burst of 150 requests can be accepted if the bucket is full; requests beyond capacity will be throttled or queued.

Rate limiting should have multiple layers:

1. Edge/API gateway to block invalid traffic early.
2. Per-tenant or per-client quotas to prevent one customer from monopolizing capacity.
3. Function concurrency caps to protect the execution budget.
4. Dependency-specific limits to avoid exceeding database or provider quotas.

When rejecting HTTP requests, return appropriate status codes and retry guidance, typically 429 for client rate limits. For temporary system overload, 503 may be appropriate. Never return a fake 200 and silently drop the request.

## 13. Queue buffering to absorb bursts

For work that does not require an immediate synchronous response, queues decouple request ingestion speed from processing speed. Producers write messages quickly, and consumers process them at controlled capacity.

~~~mermaid
flowchart LR
    A[Traffic burst] --> B[API / Producer]
    B --> C[Durable queue]
    C --> D[Consumer scaling policy]
    D --> E[Java functions]
    E --> F[Database / downstream]
    C --> G[Backlog and age metrics]
    G --> D
~~~

Queues do not eliminate load; they convert load into backlog. If producers send faster than consumers process over an extended period, the backlog will grow continuously.

If the arrival rate is \(\lambda\) messages/second and total processing rate is \(\mu\) messages/second:

- When \(\mu > \lambda\), consumers can work down the accumulated backlog.
- When \(\mu = \lambda\), the backlog does not shrink significantly.
- When \(\mu < \lambda\), the backlog continues to grow.

If the backlog contains \(B_q\) messages and processing capacity exceeds the incoming rate by \(\mu-\lambda\), approximate drain time is:

\[
T_{drain} \approx \frac{B_q}{\mu-\lambda}
\]

This formula assumes steady rates, no errors/retries, and no other limits. Monitor oldest message age, queue depth, receive count, DLQ, and throughput instead of looking only at current message count.

### Queues are not suitable for every request

If a client requires an immediate result, putting the request into a queue changes the contract from synchronous to asynchronous. You can return 202 Accepted with an operation ID and provide a status-polling endpoint. Never return a final success response when the message has only just been enqueued.

## 14. Controlling concurrency for queue consumers

Queue consumers can scale with backlog size. However, scaling out too fast can cause hundreds of functions to open database connections or call external APIs simultaneously.

Cap consumer concurrency based on:

- Maximum database capacity.
- Connection pools and proxies.
- External provider rate limits.
- Batch size and processing time per message.
- Visibility timeout or lock duration.
- Retry and DLQ policies.
- Ordering/partition constraints.

For example, a database supports at most 300 application connections, but other services already use 180. If each function environment opens a pool of 5 connections, the theoretical limit for workers is only 24 environments, before even accounting for admin/monitoring connections and headroom. Smaller pools or a proxy may allow more functions, but this must be measured.

For AWS Lambda + SQS, you can use reserved concurrency to cap the function and maximum concurrency on the event source mapping when supported by the queue/provider. Configure both values consistently: the event source should not demand higher concurrency than the function's cap if the goal is to avoid throttling.

## 15. Protecting databases and dependencies during scale-out

A serverless system can spin up far more instances than a traditional server model. That does not mean databases automatically scale to match.

For example, 200 Lambda environments each opening a pool of 10 connections can create up to roughly 2,000 connections if all pools are active at once. The database may run out of connections before the function even reaches its desired concurrency.

Measures:

- Use small, explicitly bounded pools.
- Close/release connections properly.
- Consider a connection proxy/pooling service.
- Use caching for repeatedly read data where appropriate.
- Batch writes/reads when business logic permits.
- Cap concurrency at the function or event source layer.
- Use reasonably short timeouts and circuit breakers.
- Offload heavy workloads to queues.
- Monitor database connection count, wait time, locks, CPU, and IOPS.

Do not raise max instances just because function CPU is low. The function may be blocked waiting on a database or external API. Scaling out when the bottleneck sits at a dependency increases pressure without increasing throughput.

## 16. Which signals should drive autoscaling?

Autoscalers can use several types of signals:

| Signal | Best suited for | Limitations |
|---|---|---|
| Concurrent requests | HTTP services and FaaS | Does not fully reflect the weight of individual requests |
| Requests per instance | HTTP containers | Requires benchmarking effective concurrency |
| CPU utilization | CPU-bound workloads | Can react slowly to I/O-bound traffic |
| Memory utilization | Memory-bound workloads | Does not directly indicate request queueing |
| Queue depth | Async consumers | Queue depth does not show backlog age if messages arrive continuously |
| Oldest message age | Queues with time SLAs | Requires measuring the right source metric |
| Custom business metric | Specialized workloads | Avoid high metric cardinality and hard-to-understand feedback loops |

For HTTP functions, the API gateway may need separate rate limits and throttling before requests reach the function. For queue consumers, queue depth and oldest age are usually more useful than CPU alone. For workflows, active executions, time per step, and retry counts help uncover bottlenecks.

## 17. Scale-in and graceful shutdown

When load drops, the platform can reclaim execution environments. Applications should not assume instances will live long or always receive shutdown notices early enough to finish all work.

Safe design practices:

- Do not keep unique business state solely in memory.
- Commit progress before acknowledging a message or returning success.
- Close connections/resources if the runtime provides lifecycle hooks.
- Use timeouts and cancellation propagation.
- Ensure unfinished messages can be retried.
- Do not spawn unbounded background threads after an invocation finishes.
- Use durable workflows/queues for work exceeding the invocation budget.

Container platforms may offer a termination grace period or shutdown signal. FaaS providers have different lifecycles; read your platform's semantics and do not assume SIGTERM/cleanup hooks behave like standard containers.

## 18. Multi-Region and quotas

Autoscaling is generally subject to quotas by account, project, subscription, Region, or service. A function may run smoothly in Region A yet get throttled in Region B due to differing quotas, capacity pools, or dependencies.

When designing for multi-Region:

- Check concurrency quotas and scaling limits in each Region.
- Verify database/replication and network capacity.
- Avoid shifting 100% of traffic to a standby Region if that Region has not been tested at corresponding load.
- Prepare a phased failover plan and rate limits.
- Measure cold starts, provisioning rates, and dependency latency separately per Region.
- Ensure queues, event routing, and idempotency tolerate cross-Region replays.

Active-active increases availability but also raises total load and duplicate-processing risks. Active-passive requires sufficient standby capacity or accepting ramp-up delay after failover. Test failover under realistic load.

## 19. Observing scaling and bursts

Autoscaling should be evaluated with metrics across the platform, function, and dependency layers.

| Metric | What you need to know |
|---|---|
| Concurrent executions/requests | Is actual demand hitting limits? |
| Throttles / 429 / 503 | Which requests are rejected and at which layer? |
| Instance count | How many instances are ready? |
| Instance startup/init duration | How long does new capacity take to become ready? |
| Cold start rate | How many requests incur initialization? |
| p95/p99 latency | How do bursts affect tail latency? |
| Queue depth/oldest age | Is the backlog growing or shrinking? |
| Provisioned capacity utilization | Is baseline warm capacity set too high or too low? |
| Database connections | Are downstreams under scale pressure? |
| Retry/DLQ rate | Is throttling causing retry storms or poison backlogs? |
| Cost per request/job | Does peak capacity push costs over budget? |

A dashboard should plot traffic and concurrency on the same timeline alongside instance count, init duration, throttles, queue age, and downstream metrics. Seeing instance counts rise alone does not prove autoscaling is working well; the goal is meeting SLAs without overloading dependencies.

## 20. Load testing for autoscaling and bursts

Load tests must simulate traffic shapes, not just send a constant RPS for a few minutes.

Scenarios:

1. **Baseline:** normal load to establish baseline latency and cost.
2. **Step load:** jump quickly from low load to peak.
3. **Ramp load:** increase steadily over time to observe scale-out.
4. **Spike:** very brief burst followed by a rapid drop.
5. **Sustained peak:** hold peak long enough to observe steady state.
6. **Soak:** prolonged moderate load to uncover leaks, pool exhaustion, and cost behavior.
7. **Overload:** intentionally exceed capacity in a safe environment to verify backpressure.
8. **Recovery:** reduce load and measure how quickly backlog/latency return to normal.
9. **Failover:** lose a dependency or Region and observe scale/queue behavior.

### Example traffic profile

~~~text
Phase             Duration      Load
Warm baseline     5 min         50 RPS
Ramp-up           2 min         50 -> 500 RPS
Burst             10 sec        1,500 RPS
Sustained peak     10 min        500 RPS
Cool-down          5 min         500 -> 50 RPS
Recovery           5 min         50 RPS
~~~

This is an illustrative profile. Adjust it to match real traffic and SLAs. Do not run tests that impose load on production dependencies or third-party services without approved scope.

### What to record

- When the load generator starts sending requests.
- When the platform begins scaling.
- When the first new instance becomes ready.
- When capacity reaches target.
- Throttling and timeout rates.
- p50/p95/p99 latency.
- Queue backlog and drain time.
- Database connections and external API rates.
- Total cost or cost proxy per invocation/instance.

The load generator itself can become a bottleneck. Use multiple generators or partition load if needed, and verify they have enough network/CPU to generate the intended traffic profile.

## 21. Example burst-control architecture for a Java order service

Suppose an API receives orders. Clients may send a burst when a campaign starts. Each request must validate, record the order, and call inventory/payment. If the function synchronously calls all dependencies, a burst can create excessive concurrent connections and requests.

One possible design:

1. The API gateway authenticates, enforces per-client rate limits, and validates request size.
2. A Java ingress function writes a durable operation record and enqueues an event.
3. The API returns 202 with an operation ID if the contract is asynchronous.
4. The queue buffers the backlog when incoming traffic exceeds consumer capacity.
5. Java workers scale with the backlog while bounded by a concurrency cap.
6. Workers use idempotency keys to handle message redelivery.
7. A database proxy/pool and external API rate limits protect dependencies.
8. A DLQ stores messages that cannot be processed after the retry policy.
9. A workflow updates status and emits a completion event.
10. Dashboards track queue age, consumer concurrency, dependency latency, and order completion time.

~~~mermaid
flowchart TD
    A[Clients / burst] --> B[API Gateway]
    B --> C[Auth + rate limit]
    C --> D[Java ingress function]
    D --> E[(Operation store)]
    D --> F[Durable queue]
    F --> G[Consumer autoscaling]
    G --> H[Java worker functions]
    H --> I[Idempotency check]
    I --> J[(Database / proxy)]
    I --> K[External API]
    H --> L[DLQ]
    H --> M[Workflow state]
    F --> N[Backlog / age metrics]
    G --> N
    H --> O[Logs / metrics / traces]
~~~

This architecture decouples intake speed from processing speed, but it must clearly define when an order is considered accepted, processing, or completed. Successfully enqueuing a message does not mean payment or inventory reservation has succeeded.

## 22. Common mistakes when designing autoscaling

| Mistake | Consequence | Fix |
|---|---|---|
| Assuming autoscaling is instantaneous | Bursts trigger throttling before capacity is ready | Measure provisioning lag and design buffers |
| Confusing max concurrency with provisioning rate | Target capacity is sufficient, yet ramp-up still lags | Track concurrency and startup rate separately |
| Using only average latency | Tail requests hold concurrency longer than expected | Measure p95/p99 and workload mix |
| Letting concurrency scale unbounded | Downstream databases/APIs get overloaded | Set caps based on dependency capacity |
| Scaling queue consumers by depth without limits | Retry storms and connection exhaustion | Max concurrency, backoff, and DLQs |
| Keeping warm via continuous pings | Higher cost without guaranteed environment reuse | Use official provisioned/min capacity |
| Scaling in too aggressively | Instances are reclaimed before work completes | Graceful shutdown and durable state |
| Using queues but returning final success | Clients mistakenly assume the operation completed | Use 202 and operation status |
| Not testing bursts | Cold starts/throttles discovered only in production | Step, spike, ramp, and failover tests |
| Only raising function capacity when DB is slow | Increases pressure on the bottleneck | Measure dependencies and throttle concurrency |
| Ignoring per-Region quotas | Failover Region gets throttled | Check and load test each Region |
| Retrying immediately when throttled | Creates larger load and prolongs outages | Exponential backoff, jitter, retry budget |

## 23. Capacity and scaling policy design workflow

When preparing a Java function or serverless service:

1. **Classify workload:** synchronous HTTP, async queue, stream, or workflow.
2. **Measure traffic profile:** baseline, peak, burst magnitude, ramp rate, and peak duration.
3. **Measure service time:** p50/p95/p99 by route and dependency.
4. **Estimate concurrency:** use Little’s Law as a starting point, then benchmark.
5. **Determine instance capacity:** effective concurrency per environment/container.
6. **Check provisioning:** measure startup latency, scale-out lag, and provider quotas.
7. **Set baseline:** minimum/provisioned capacity if SLAs require it.
8. **Set limits:** reserved/max concurrency, max instances, and API rate limits.
9. **Protect dependencies:** database pools, proxies, external API quotas, and circuit breakers.
10. **Choose buffers:** queues, batching, and backlog age SLAs for async work.
11. **Design retries:** backoff, jitter, idempotency, DLQs, and retry budgets.
12. **Load test:** step, ramp, spike, sustained peak, overload, and recovery.
13. **Observe:** concurrency, init duration, throttles, p99, queue age, dependency load, and cost.
14. **Tune:** adjust policies incrementally and verify they do not cause scale oscillation.

## 24. Production checklist

- **Traffic model:** baseline, peak, spike, ramp rate, and peak duration are known.
- **Concurrency:** estimated from RPS and duration, then verified via load tests.
- **Instance capacity:** effective concurrency per environment/container is known.
- **Provisioning rate:** scale-out time measured in the exact Region/account/project.
- **Cold starts:** init duration tracked separately; Java bootstrap and dependency initialization optimized.
- **Warm capacity:** minimum/provisioned instances set according to SLA and budget.
- **Limits:** account quotas, reserved concurrency, max instances, and event source limits checked.
- **Admission control:** gateway/per-tenant rate limits and overload responses configured.
- **Queues:** backlog, oldest message age, consumer max concurrency, and DLQs have alarms.
- **Downstreams:** database connections, API quotas, and connection pools have appropriate limits.
- **Retries:** backoff, jitter, retry budgets, and idempotency protect side effects.
- **Scale-in:** durable state, timeouts, and cleanup do not rely on long-lived instances.
- **Multi-Region:** each Region has quotas, dependencies, and failover capacity tested.
- **Observability:** dashboards include instance count, concurrency, throttles, p95/p99, queue age, and startup duration.
- **Load tests:** step, ramp, spike, sustained peak, overload, and recovery executed in suitable environments.
- **Cost:** warm capacity, peak concurrency, backlog, retry, and telemetry costs accounted for.

## 25. Conclusion

Autoscaling enables serverless platforms to adjust capacity to demand, but burst resilience simultaneously depends on concurrency quotas, provisioning rates, startup latency, and dependency resilience. Concurrency shows how many invocations/requests are active; throughput shows completion rate; instance count shows environment count; provisioning rate shows how quickly new capacity comes online.

For Java functions, JVM and dependency initialization can increase cold starts. Provisioned concurrency or minimum instances help maintain a ready baseline, though traffic above baseline still requires scale-out. Queue buffering, rate limiting, and concurrency caps help absorb or regulate bursts; they must be paired with idempotency, retry policies, and backlog monitoring.

Use Little’s Law to estimate concurrency, load tests to measure scale-out lag and p95/p99, and check database/API capacity before raising limits. The goal is to meet SLAs as load changes, keep downstreams stable, and control costs during both normal hours and major bursts.
