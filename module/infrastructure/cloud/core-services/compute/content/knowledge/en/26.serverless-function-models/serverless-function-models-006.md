# Concurrency, instance creation rate, and scaling limits

A serverless function can automatically scale up its number of execution environments as request volume grows. This enables applications to handle fluctuating load without managing servers, yet it does not mean scaling is infinite or instantaneous. The platform can limit concurrent executions, the creation rate of new environments, requests per second, maximum instances, event source polling rates, or account and regional quotas.

Without designing for these limits, a traffic spike can cause requests to be throttled, cold starts to lengthen, queue backlogs to pile up, or downstream databases and APIs to become overloaded. Raising concurrency too high can sometimes slow the entire system down because every execution environment opens connections and contends for shared resources.

This lesson belongs to the **Serverless function models** chapter of the **CLOUD_CORE_SERVICES_COMPUTE** module. The module explores cloud compute capacity models—from virtual machines and containers to serverless; how to select CPU, memory, networking, and security settings; and how to deploy applications, scale under load, ensure availability, and optimize operating costs. Within that context, understanding concurrency, instance creation rates, and scaling limits helps design serverless functions that absorb load, protect dependencies, and control cost.

## 1. Understanding concurrency in serverless

### 1.1. Execution environments and invocations

A serverless platform typically creates an execution environment to load the runtime, application code, and required initialization. Each execution of the function is an invocation or execution.

Some platforms can reuse an execution environment across sequential or concurrent invocations depending on the runtime model and configuration. Some models handle multiple concurrent requests within the same environment; others process only one invocation at a time per environment. Therefore, you cannot apply a single per-instance concurrency number across all services.

As load rises, the platform can spin up additional environments. As load drops, environments may stay warm for a period or be reclaimed. This lifecycle is managed by the platform and must not be treated as durable state storage.

### 1.2. Concurrency is the number of jobs running simultaneously

Concurrency is the number of invocations being processed at the same instant. It differs from request rate:

- **Request rate / arrival rate:** number of incoming requests per second.
- **Concurrency:** number of requests or invocations actively running at the same time.
- **Throughput:** number of requests completed per unit of time.
- **Duration:** how long a single invocation runs.
- **Scaling rate:** how fast the platform adds or removes execution environments.
- **Maximum instances:** cap on how many environments can be allocated to a function or workload.

For example, 100 requests per second does not necessarily require 100 execution environments. If each request takes only 100 ms and arrivals are evenly distributed, average concurrent requests sit around 10. If each request takes 2 seconds, average concurrency sits around 200.

### 1.3. Using Little’s Law to estimate concurrency

For a steady-state system, a basic estimate is:

**Average concurrency ≈ Arrival rate × Average duration**

Where:
- Arrival rate is invocations starting per second.
- Average duration is mean processing time in seconds.

Example:

- 120 requests/second.
- Average processing time of 250 ms, or 0.25 seconds.
- Estimated average concurrency: 120 × 0.25 = 30 invocations.

This is an average, not a safe ceiling. Design must account for bursts, high-percentile durations, retries, cold starts, and headroom.

If duration doubles due to a slow database, concurrency can nearly double even though request rate stayed flat. Thus, high concurrency can be a symptom of slow dependencies, not just higher traffic.

### 1.4. System-wide vs. per-instance concurrency

Distinguish two scopes:

- **Function/account concurrency:** total running invocations for one function or a quota scope in an account/region.
- **Per-instance concurrency:** how many invocations a single execution environment handles concurrently.

Illustrative example: if one environment is configured to handle 5 simultaneous requests and a function needs 40 concurrent invocations, the theoretical minimum environment count is 8. If each environment handles only one invocation at a time, roughly 40 environments are required.

Actual counts can be higher due to load distribution, initialization time, scaling limits, and runtime constraints.

## 2. Capacity calculation models

### 2.1. Estimating required environments

In a model where each environment has concurrency cap C, you can estimate:

**Required environments ≈ ceil(Target total concurrency / C)**

Example:
- Target concurrency: 150.
- Each environment processes up to 5 concurrent invocations.
- Theoretical need: ceil(150 / 5) = 30 environments.

Add headroom for bursts and initializing environments. Also verify maximum limits at the function, account, region, and dependency levels.

### 2.2. Calculating capacity by throughput

If each environment handles up to C concurrent invocations and average duration is D seconds, approximate theoretical throughput is:

**Throughput per environment ≈ C / D**

Example:
- C = 4 invocations.
- D = 0.2 seconds.
- Theoretical throughput ≈ 20 invocations/second/environment.

This estimate assumes uniform request distribution and no other bottlenecks. CPU, memory, networking, runtime scheduling, connection pools, and dependencies can reduce actual throughput.

### 2.3. End-to-end sizing example

A serverless API receives 300 requests/second. Average duration is 400 ms.

- Estimated average concurrency: 300 × 0.4 = 120.
- If one environment handles 4 concurrent invocations: roughly 30 environments on average.
- With 50% headroom: target capacity is roughly 180 concurrency, equivalent to 45 environments at concurrency 4.

Next, verify:
- Does the function have enough concurrency quota for 180?
- Can the platform spin up 45 environments fast enough?
- Can the database handle the added connections?
- Do downstream APIs impose rate limits?
- Can networking, subnets, and IP capacity accommodate it?
- Does the cost at this load level stay within budget?

50% headroom is just an example. Choose reserve margins based on bursts, SLOs, duration variance, and budget.

### 2.4. Use percentiles instead of averages alone

Average duration can mask slow requests. If most requests finish in 100 ms while a few take 5 seconds, concurrency and tail latency suffer.

Track:
- p50 duration.
- p90/p95 duration.
- p99 duration.
- Maximum duration.
- Timeout rate.
- Duration broken down by request type or dependency.

You can use p95 for more conservative sizing, but avoid treating any single percentile as a perfect predictor. Request distributions and correlations between duration and load must be measured directly.

## 3. Execution environment creation rate

### 3.1. What is scaling rate?

When concurrency climbs, the platform must provision additional execution environments. This process has a bounded rate, which can be described by:
- Maximum new environments created within a time interval.
- Concurrency ramp-up rate per interval.
- Number of instances provisioned concurrently.
- Initial burst limit and subsequent sustained ramp rate.
- Dedicated quotas per function, account, region, or event source.

Platforms use different algorithms and numbers. Never assume a fixed ramp-up rate across providers or trigger types. Check current quota documentation and measure in the target environment.

### 3.2. Burst traffic vs. gradual traffic

**Gradual traffic:** load climbs slowly, giving the autoscaler time to create environments and distribute invocations.

**Burst traffic:** a massive wave of requests arrives in a very short span, such as after an email campaign, push notification, flash sale, or an upstream system retrying en masse.

During bursts, concurrency demand can outpace environment creation rate. Requests may wait, get throttled, or return errors before fresh capacity becomes ready.

### 3.3. Scale-out speed does not equal maximum capacity

A function may have a very high maximum concurrency quota yet still be unable to jump from 0 to that ceiling instantaneously. Consider all of:
- Maximum concurrency.
- Scaling rate.
- Startup duration.
- Currently available warm capacity.
- Event source polling rate.
- Downstream capacity.

These answer distinct questions: how high the system can go, how fast it can climb, how long one environment takes to become ready, and whether dependencies can survive that load.

### 3.4. Scale-to-zero and cold starts

Some serverless models scale down to zero environments when idle. When the next request arrives, the platform must initialize a new environment. This saves idle cost at the price of a cold start.

A cold start may involve:
- Allocating a compute sandbox or container.
- Preparing network interfaces or runtime isolation.
- Pulling an image or downloading an artifact.
- Initializing the runtime.
- Loading modules and dependencies.
- Running initialization code.
- Fetching secrets or tokens.
- Creating connection pools to dependencies.

Not every cold start executes all of these steps; the sequence depends on the platform and configuration.

### 3.5. Cold starts and request duration

Cold starts increase the latency of the first invocation on a new environment. During sudden traffic spikes, many fresh environments may spin up simultaneously, exposing a large fraction of requests to cold starts.

A function averaging 100 ms when warm can have a much higher p95 under cold starts. Therefore, measure separately:
- Initialization duration.
- Invocation duration.
- End-to-end latency.
- Share of invocations hitting new environments.
- Cold-start rate by runtime version and artifact size.

### 3.6. Reducing cold starts

Possible measures include:
- Shrinking package or container image size.
- Loading only necessary dependencies.
- Avoiding network queries or heavy work during initialization.
- Reusing clients and connection pools when environments are reused.
- Choosing an appropriate runtime and memory tier.
- Using provisioned/warm capacity when latency requires it.
- Keeping initialization idempotent and bounded by timeouts.
- Avoiding loading large models or libraries until needed.

Never optimize by skipping security, TLS, or authentication checks. Measure before and after to see which steps actually consume time.

## 4. Scaling limits across multiple layers

### 4.1. Account and region quotas

Concurrency quotas may apply per account, project, subscription, region, or service. Multiple functions share quotas, so one surging workload can consume capacity needed by another.

Inventory:
- Total quota.
- Reserved or per-function allocated quota.
- Current concurrency in use.
- Daily/weekly peaks.
- Quotas for deployments, VPC networking, or event sources.
- Lead time and approval workflow for quota increases.

Do not wait until production gets throttled to request a quota increase. Quotas must be verified before launch or ahead of anticipated campaign bursts.

### 4.2. Function-level maximum concurrency

Some platforms let you set a maximum concurrency cap per function or per alias/version. This prevents one function from exhausting the shared quota.

Effects:
- If set too low, requests are throttled or queue backlogs grow.
- If set too high, the function can overload databases or downstream services.
- If unset, one function can consume most of the shared quota.

Base limits on dependency capacity, SLOs, and budget. Distinguish reserved concurrency, maximum concurrency, provisioned concurrency, and actual concurrency; names and semantics vary by provider.

### 4.3. Event-source limits

For queues or streams, limits may include:
- Number of pollers or consumers.
- Maximum concurrent batches.
- Batch size.
- Event source mapping maximum concurrency.
- Partition count or shard count.
- Number of in-flight messages.
- Visibility timeout or lease duration.

Raising function concurrency will not speed up queue draining if the event source or partition count is the bottleneck.

### 4.4. Networking and IP capacity

When functions attach to a private network, scaling can depend on:
- Available IP addresses in subnets.
- Network interface or attachment quotas.
- NAT gateway and SNAT capacity.
- DNS resolver capacity.
- Firewall connection tracking.
- Concurrent connections to private endpoints.

A function with a high concurrency quota can still fail to scale out if a subnet runs out of IPs or hits network attachment limits. Include network capacity in serverless capacity planning.

### 4.5. Dependency quotas

Functions can scale faster than the databases, caches, or APIs they call. Common limits:
- Maximum database connections.
- Query throughput or transaction rate.
- API requests per second.
- Queue publish/consume rates.
- Object storage request rates or account quotas.
- Partner system rate limits.
- Proxy connection limits.

Do not simply crank up concurrency to clear a queue backlog. If downstream systems are already saturated, adding invocations only drives up timeouts, retries, and cost.

## 5. Protecting dependencies as concurrency grows

### 5.1. Calculating connection pool limits

Suppose each execution environment opens a pool of P connections to a database. With N environments, potential connections are:

**Total connections ≈ N × P**

Example:
- Database allows at most 500 connections.
- Reserve 100 connections for admin, migrations, and other workloads.
- 400 connections remain for functions.
- Each environment holds a pool of 8 connections.

Maximum environments allowed by the connection limit is 400 / 8 = 50.

If the function can spawn 100 environments, the database can be overwhelmed even when the function quota permits it. Shrink pool sizes, add a connection proxy, cap concurrency, or redesign data access.

### 5.2. Connection reuse and proxies

You can curb connection churn by:
- Reusing clients inside the execution environment.
- Using bounded connection pools.
- Using a database proxy or pooling service when appropriate.
- Setting idle timeouts and max lifetimes.
- Closing connections properly.
- Avoiding opening new connections per request when the runtime supports safe reuse.

Execution environments can be frozen or terminated at any time under platform semantics. Do not assume local connections stay durable; handle reconnects and stale connections.

### 5.3. Backpressure

Backpressure regulates work intake speed when downstream capacity is insufficient.

Examples:
- Capping function concurrency.
- Capping queue pollers or consumers.
- Buffering requests in queues rather than handling them synchronously.
- Reducing batch size or message emission rate.
- Returning 429/503 with `Retry-After` where appropriate.
- Using circuit breakers when dependencies fail.
- Limiting queued/pending requests.

Backpressure keeps the system stable instead of accepting more work than it can process.

### 5.4. Retries and retry storms

When invocations time out, the platform or client may retry. If many requests fail at once, retries pile extra load onto an already weakened system.

You need:
- A cap on retry attempts.
- Exponential backoff and jitter.
- Separation of transient errors from permanent errors.
- Idempotency keys for operations with side effects.
- A dead-letter queue or final error sink.
- No unbounded retries on requests guaranteed to fail.
- Aligned overall and dependency timeouts.

Retry policies depend on the trigger. Synchronous invocations, asynchronous invocations, and event source polling have different retry semantics. Verify the exact behavior of your platform.

### 5.5. Capping concurrency to match downstream capacity

If a database handles 200 concurrent queries, functions should not launch 1,000 concurrent invocations only to let the database reject them.

Set concurrency caps below the downstream ceiling while leaving headroom for other workloads. If multiple functions share one database, budget total concurrency across all functions combined, not each function in isolation.

## 6. Synchronous vs. asynchronous scaling

### 6.1. Synchronous invocation

For HTTP/API or synchronous invocations, the caller waits for the result. When the function lacks capacity:
- Requests may be throttled.
- The gateway or client may time out.
- The caller may retry.
- Latency climbs during cold starts or slow dependencies.

Align timeouts across every layer: client, API gateway, function platform, and dependencies. Total timeout must allow steps to finish without holding requests open indefinitely.

### 6.2. Asynchronous invocation

For asynchronous invocations, events can sit in a platform-managed internal queue before the function processes them.

Advantages:
- Decouples event emission rate from processing rate.
- Absorbs bursts within retention and queue capacity limits.
- Enables independent retries and error handling.

Risks:
- Backlogs can grow rapidly.
- Event age can rise and breach time objectives.
- Retries can generate duplicates.
- Queue retention can expire before processing completes.
- Functions can scale too fast and overload downstream systems.

Monitor event age, queue depth, retries, throttles, and dead-letter counts.

### 6.3. Queue-based load leveling

A queue can act as a buffer between producers and functions:

~~~mermaid
flowchart LR
    P["Producers"] --> Q["Queue / Event buffer"]
    Q --> C["Pollers / Event source"]
    C --> F["Serverless functions"]
    F --> D["Database / Downstream"]
    F --> DLQ["Dead-letter queue"]
~~~

Producers can keep publishing while workers process at capped capacity. However, queues do not provide infinite capacity; configure retention, quotas, message size limits, DLQs, and backlog alerts.

### 6.4. Batch size and concurrency

Event sources can group multiple messages into a batch. Large batches:
- Reduce invocation overhead.
- Can raise throughput.
- Increase processing time and memory demand.
- On failure, can force many messages to retry if partial batch responses are unsupported.

Small batches:
- Shrink retry blast radius.
- Increase invocation counts and overhead.
- May raise cost or scheduler pressure.

Choose batch size based on processing time, message size, memory, timeout, ordering, and queue semantics.

### 6.5. Partial batch failures

Some event sources support responses identifying only the failed messages in a batch so the platform retries just those. If misconfigured, a single bad message can trigger redelivery of the whole batch.

Ensure you:
- Use partial batch responses where supported by platform and trigger.
- Design idempotent processing.
- Track message retry counts.
- Implement poison-message handling and a DLQ.
- Prevent a single failing message from stalling an entire partition or queue indefinitely.

## 7. Quotas, throttling, and limit-exceeded behavior

### 7.1. What is throttling?

Throttling occurs when the platform rejects or delays requests because a concurrency, rate, quota, or capacity limit was exceeded.

Symptoms:
- Throttling or “too many requests” errors.
- HTTP 429 or equivalent error responses.
- Invocations failing to start.
- Growing queue backlogs.
- Rising event age.
- Caller timeouts or retries.
- Concurrent execution metrics hitting the cap.

Distinguish function-platform throttling from rate limits enforced by API gateways, downstream services, or identity providers.

### 7.2. Reserved concurrency vs. provisioned concurrency

Exact names differ across platforms, but two concepts should be distinguished:

- **Reserved concurrency:** reserves or caps a slice of concurrency for a function, isolating capacity or limiting consumption.
- **Provisioned concurrency / pre-warmed capacity:** pre-initializes execution environments to cut cold starts, typically incurring ongoing charges even at low traffic.

Reserving concurrency does not automatically keep environments warm. Conversely, warm capacity does not necessarily raise the account’s overall quota. Read provider semantics carefully before configuring.

### 7.3. Per-function caps

Setting max concurrency protects downstream services, yet creates backlogs or throttling when traffic exceeds the cap.

Example:
- Function receives 500 requests/second.
- Dependency allows only 100 requests/second.
- Cap the function so it stays within dependency capacity.
- Excess work is queued or rejected in a controlled manner.

If a synchronous API has no queue, return a retryable error or appropriate response for the caller to handle. Avoid letting requests wait until multi-layer timeouts fire.

### 7.4. Quota increases

When a quota increase is needed:
1. Measure peak demand and forecast traffic.
2. Identify which specific quota is constraining.
3. Verify downstream dependency and network capacity.
4. Request the quota increase ahead of launch.
5. Confirm the new quota took effect in the right region/account.
6. Run a controlled load test.
7. Watch throttling and downstream behavior afterward.

Raising a quota does not mean consuming all of it. Function and downstream guardrails remain essential.

## 8. Cold starts, warm capacity, and startup optimization

### 8.1. Factors impacting cold starts

Cold starts can be influenced by:
- Runtime and runtime version.
- Package/image size.
- Number of imported dependencies.
- Initialization code.
- Network attachment.
- Secret retrieval and token exchange.
- TLS handshakes and connection setup.
- Runtime compilation or JIT.
- Loading models or configuration data.

Analyze initialization duration separately from request processing duration.

### 8.2. Provisioned or pre-warmed capacity

When consistent latency is critical, you can retain pre-initialized environments. This fits:
- APIs with strict latency SLOs.
- Predictable traffic patterns.
- Campaigns or peak business hours.
- Workloads with heavy cold-start initialization.

Limitations:
- Ongoing cost of maintaining warm capacity.
- May not cover bursts exceeding the provisioned floor.
- Warm environments must be refreshed when deploying new versions.
- Can create excess idle capacity if forecasts miss.

Size warm capacity to baseline concurrency and burst profiles; it does not replace autoscaling or quota planning.

### 8.3. Initialization code must be safe

Initialization can re-run on new environments and can fail. Ensure you:
- Avoid non-idempotent side effects during initialization.
- Avoid automatically running database migrations in every environment.
- Set timeouts for secret reads and connection setup.
- Handle credential refreshes.
- Reuse clients across warm invocations.
- Close or recreate stale connections.
- Never store sole business state in environment memory.

### 8.4. New deployments and cold starts

A new version may require fresh environments. During rollout, some requests can experience cold starts or execute concurrently across two versions.

You should:
- Pre-warm the exact version/alias receiving traffic if supported by the platform.
- Canary traffic before shifting 100%.
- Verify schema and message compatibility.
- Monitor init duration and error rate after deployment.
- Keep a rollback ready if the new version spikes cold starts or timeouts.

## 9. Autoscaling policies and load control

### 9.1. Rely on the right metrics

Do not watch CPU or request count alone. For serverless functions, track:
- Concurrent executions.
- Invocation rate.
- Duration p50/p95/p99.
- Throttle count.
- Error rate.
- Init/cold-start duration.
- Queue depth and oldest event age.
- Event source poller concurrency.
- Downstream connection count and latency.
- Cost per request or cost per successful job.

Tie metrics to service goals. For instance, queue workers care deeply about message age and backlog, whereas synchronous APIs focus on latency and throttle rates.

### 9.2. Scale out fast, scale in cautiously

When load climbs, the system needs capacity promptly. When load drops, shrinking capacity too aggressively can cause repeated cold starts if traffic rebounds shortly after.

Use:
- Stabilization windows.
- Minimum warm capacity.
- Hysteresis between scale-out and scale-in.
- Scheduled capacity for predictable traffic.
- Rate limits on environment churn per cycle.
- Queue buffers to absorb oscillations.

### 9.3. Protect dependencies with concurrency budgets

Establish a concurrency budget for each downstream service.

Example:
- Database allocates 250 connections to the API function.
- Each environment opens at most 5 connections.
- Environment concurrency cap is roughly 50 under the connection limit, before subtracting headroom and other needs.
- If a function handles multiple concurrent requests per environment, calculate pools and concurrency using the true runtime model.

Budgets must include other functions, scheduled jobs, migrations, and operators. Assign an owner responsible for tracking the aggregate budget.

### 9.4. Circuit breakers and load shedding

When downstream services slow down or fail:
- Circuit breakers temporarily halt calls to failing dependencies.
- Load shedding drops lower-priority or excess requests.
- Deferrable work gets queued.
- Critical requests are prioritized.
- Retries and concurrency are capped.
- Actionable errors are returned to callers.

The goal is keeping healthy parts of the system running rather than letting one failing dependency drag down the entire workload.

## 10. Example: a serverless API with burst traffic

An order-processing API has:
- Baseline of 80 requests/second.
- Bursts up to 600 requests/second for 30 seconds.
- Mean warm duration of 200 ms.
- p95 duration of 500 ms.
- Database sustains up to 180 connections dedicated to the API.
- Each environment keeps a pool of at most 3 connections.

Baseline estimates:
- Average concurrency: 80 × 0.2 = 16.
- Using 0.5-second p95 duration for conservative sizing: 80 × 0.5 = 40.

Burst estimates:
- Average concurrency at warm duration: 600 × 0.2 = 120.
- At p95 duration: 600 × 0.5 = 300.

Database constraint:
- 180 connections / 3 connections per environment = 60 environments max by pool limit.
- Spinning up 100 environments could open up to 300 connections, breaching the budget.

Design considerations:
1. Shrink the pool size if the workload does not need 3 connections per environment.
2. Add a database proxy or connection multiplexing if suitable.
3. Cap concurrency to protect the database.
4. Offload work not needing immediate responses to a queue.
5. Check scale-out speed and warm capacity for burst absorption.
6. Load test with p95 durations and slow dependencies.
7. Configure retries with backoff and idempotency for order placement.
8. Monitor throttles, latency, DB connections, and queue age.

Do not treat the 60-environment calculation as the final config limit without accounting for other workloads’ connections, headroom, and actual per-environment concurrency.

## 11. Testing scalability

### 11.1. Test multiple load shapes

Test across diverse patterns:
- Constant load: sustained steady traffic.
- Ramp-up: gradually increasing request rate.
- Burst/spike: sudden short-lived surge.
- Step load: stepping between fixed traffic levels.
- Soak test: prolonged load to surface leaks or cumulative quotas.
- Recovery test: drop load then ramp back up to observe scale-in/scale-out.
- Dependency degradation: intentionally slow down databases or APIs in a controlled way.

### 11.2. Measure end-to-end

Collect:
- Incoming request rate.
- Invocations accepted/started/completed.
- Concurrent executions.
- Environment creation and init duration.
- End-to-end latency.
- Throttle and error rates.
- Queue backlog and oldest event age.
- Downstream connections/throughput/latency.
- Cost per request or per test run.

Measuring function duration alone misses waiting time in API gateways, queues, schedulers, or cold starts.

### 11.3. Test limit-exceeded behavior

Verify how the system behaves when:
- Function concurrency cap is reached.
- Account/region quota is hit.
- Event source polling falls behind.
- Database hits its connection limit.
- Network/IP capacity runs short.
- Provisioned capacity falls below a burst.
- Secret manager or identity provider slows down.
- A dependency times out and retries kick in.

The goal is not merely proving the function scales high, but confirming the system degrades gracefully.

### 11.4. Do not generate load that impacts production

Run load tests in controlled environments or with explicit approval. Use test data, cap spend, define abort thresholds, and notify dependency owners. Never run ad-hoc spike tests against production databases or partner APIs.

## 12. Observability and alerting

| Metric | Meaning | When to alert |
|---|---|---|
| Concurrent executions | Running invocations | Approaching cap or quota |
| Throttles | Invocations rejected due to limits | Sudden spike or SLO breach |
| Invocation duration | Execution time | p95/p99 climbing steadily |
| Init duration | Environment initialization time | Cold starts rise after deploy or burst |
| Invocation errors | Function error rate | Exceeds workload threshold |
| Queue depth | Pending messages | Growing continuously |
| Oldest event age | Age of unprocessed event | Approaching retention or SLO |
| Downstream connections | Connections to DB/APIs | Near connection limit |
| Dependency latency | Downstream service latency | Climbing alongside concurrency |
| Scale-out rate | Environment provisioning speed | Demand grows faster than provisioning |
| Provisioned capacity utilization | Warm capacity usage | Chronically under-provisioned or over-idle |
| Cost per successful invocation | Cost per useful outcome | Abnormal increase |

Base alerts on trends and sustained duration, avoiding noisy paging from brief spikes that do not breach SLOs.

## 13. Cost and performance optimization

### 13.1. High concurrency does not equal high efficiency

Raising concurrency can lift throughput, yet it can also:
- Multiply environments and cost.
- Open excessive database connections.
- Increase contention and retries.
- Worsen p99 latency.
- Increase downstream rejections.

Optimize around cost per successful request and SLOs, not raw maximum invocation count.

### 13.2. Memory and CPU affect duration

On many platforms, memory settings influence allocated CPU or network capacity. Raising memory can sometimes make functions finish faster with lower total billed time, even at a higher per-unit rate.

Benchmark multiple memory tiers with real workloads and measure:
- Duration.
- CPU saturation.
- Peak memory.
- Cold starts.
- Errors/timeouts.
- Cost per successful invocation.

### 13.3. Optimizing batch size and concurrency

For queue workers, larger batches cut invocation overhead while increasing execution duration and retry scope. For synchronous APIs, higher concurrency reduces queuing wait while increasing database pressure.

Tune batch size, concurrency, and memory together. Vary one parameter per benchmark pass to isolate its effect.

### 13.4. Aligning warm capacity with traffic schedules

Provisioned/warm capacity helps during predictable peak windows. You can:
- Scale up before planned campaigns.
- Scale down after peak hours.
- Keep minimum warm capacity for baseline traffic.
- Let autoscaling handle bursts above the floor.

Compare the cost of warm capacity against cold-start impact and latency requirements.

## 14. Common mistakes

**Equating request rate with concurrency.** Concurrency depends on both arrival rate and execution duration. Longer durations drive concurrency up even when request rate stays constant.

**Assuming serverless scales infinitely.** Account quotas, function caps, scaling rates, networking, and downstream services all impose limits.

**Checking only maximum concurrency.** Scaling rates and cold starts can prevent the system from reaching max concurrency fast enough.

**Raising concurrency without counting database connections.** Every environment can maintain its own pool, exhausting database connections.

**Treating provisioned concurrency as a quota increase.** Warm capacity and concurrency caps have distinct semantics; verify provider behavior.

**Setting concurrency caps too low.** Requests get throttled or queue age climbs even while downstream capacity remains idle.

**Retrying immediately.** Retry storms amplify load and prolong outages. Use backoff, jitter, and retry caps.

**Failing to distinguish synchronous and asynchronous scaling.** Each model has different throttling, retry, and buffering behaviors.

**Not measuring cold starts separately.** Average duration hides initialization latency on newly spun-up environments.

**Scaling out functions while forgetting network quotas.** Subnet IPs, NAT, network interfaces, and DNS can become bottlenecks.

**Skipping dependency degradation tests.** Functions may hit concurrency targets only to crush databases or partner APIs.

**Optimizing cost per invocation alone.** Cheap invocations that fail, retry repeatedly, or inflate latency raise overall cost.

## 15. Concurrency and scaling design checklist

### Demand and capacity

- [ ] Measured arrival rate, mean duration, and p95/p99.
- [ ] Estimated concurrency using `arrival rate × duration`.
- [ ] Verified per-instance concurrency for the runtime/platform.
- [ ] Calculated required environments and headroom.
- [ ] Distinguished maximum capacity from scaling rate.
- [ ] Checked account, region, function, and event source quotas.

### Cold starts and scaling

- [ ] Measured init duration and cold-start rate.
- [ ] Audited startup code, packages/images, and dependencies.
- [ ] Decided between scale-to-zero and warm capacity.
- [ ] Configured provisioned/warm capacity if latency requires it.
- [ ] Tested bursts, ramp-ups, and new version deployments.
- [ ] Set appropriate stabilization and scale-in policies.

### Protecting dependencies

- [ ] Calculated total connections across all environments.
- [ ] Capped pools and concurrency to match database capacity.
- [ ] Checked API rate limits, queues, NAT, and subnet IPs.
- [ ] Applied backpressure and circuit breakers.
- [ ] Configured retries with backoff, jitter, and idempotency.
- [ ] Added queues/DLQs for work suitable for async processing.

### Operations and testing

- [ ] Monitored concurrency, throttles, duration, and init duration.
- [ ] Monitored queue depth and oldest event age.
- [ ] Monitored downstream latency and connection usage.
- [ ] Tested quota exhaustion and slow dependencies in controlled environments.
- [ ] Defined load-test abort thresholds and budget caps.
- [ ] Measured cost per successful invocation.
- [ ] Prepared runbooks for throttling, backlogs, or quota exhaustion.

## 16. Key takeaways

- Concurrency is the number of invocations running simultaneously; request rate is incoming invocations per second.
- Baseline estimate: average concurrency equals arrival rate multiplied by average duration.
- Per-instance concurrency and function/account concurrency are distinct limits.
- Maximum capacity does not tell you environment creation speed; check scaling rate and cold starts.
- Burst traffic can outpace instantaneous scale-out even when overall quotas suffice.
- Cold starts involve multiple initialization steps; measure init duration separately from invocation duration.
- Reserved concurrency, maximum concurrency, and provisioned concurrency have platform-specific semantics.
- Cap concurrency according to database, API, and network dependency capacity.
- Queues, backpressure, retries with backoff, and idempotency keep traffic spikes safe.
- Load tests must evaluate throttles, cold starts, quotas, dependencies, and cost together.
- The goal is meeting SLOs with controlled capacity and predictable cost.

## Glossary

| Term | Meaning |
|---|---|
| Invocation | A single execution of a serverless function. |
| Execution environment | The runtime environment provisioned by the platform to run a function. |
| Concurrency | Number of invocations actively executing at the same time. |
| Per-instance concurrency | Number of invocations one execution environment can process simultaneously. |
| Arrival rate | Rate at which requests or events arrive at the system. |
| Throughput | Number of requests or jobs completed per unit of time. |
| Duration | Time taken to process a single invocation. |
| Little's Law | Relationship between average work in system, arrival rate, and time spent in system. |
| Scaling rate | Speed at which the platform can increase or decrease capacity. |
| Cold start | Time spent initializing a new environment before handling an invocation. |
| Warm capacity | Pre-initialized execution environments kept ready to cut startup time. |
| Scale-to-zero | Scaling running environments down to 0 when idle. |
| Throttling | Rejecting or delaying requests when limits are exceeded. |
| Quota | Resource or rate limit enforced by the platform. |
| Reserved concurrency | Concurrency slice dedicated to or capped for a function per platform semantics. |
| Provisioned concurrency | Pre-initialized capacity kept ready to reduce cold starts. |
| Backpressure | Mechanism regulating work intake to match processing capacity. |
| Retry storm | Many clients retrying simultaneously, amplifying load during failures. |
| Exponential backoff | Progressively increasing wait intervals between retry attempts. |
| Jitter | Random delay added to retry intervals to avoid synchronized retries. |
| Idempotency key | Key used to identify and prevent duplicate processing side effects. |
| Event source mapping | Configuration linking an event source to a function for polling and event delivery. |
| Dead-letter queue (DLQ) | Queue storing messages that fail processing after policy-defined retries. |
| Connection pool | Reusable set of connections to a database or other service. |
| Circuit breaker | Mechanism that temporarily halts calls to a failing dependency to protect the system. |
