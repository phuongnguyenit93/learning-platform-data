# Reserved Concurrency and Provisioned Concurrency on Lambda

AWS Lambda automatically scales the number of execution environments based on invocation volume, yet two operational questions frequently arise when moving a function into production: how to ensure a function retains dedicated concurrency to serve critical workloads, and how to reduce initialization latency when requests arrive? Lambda provides two similarly named mechanisms that solve two different problems: **reserved concurrency** and **provisioned concurrency**.

Reserved concurrency dedicates a portion of the account's concurrency to a function while simultaneously setting a maximum concurrency limit for that function. Provisioned concurrency pre-initializes a number of execution environments so the function can serve requests faster. You can use each mechanism independently or combine them, provided you understand how they interact with account quotas, aliases/versions, scaling, and cost.

In the **CLOUD_SERVERLESS** module, learners deploy Java functions triggered via HTTP, messages, or events and need to control cold starts, scaling, access permissions, retries, and cost. This lesson focuses on these two AWS Lambda concurrency settings, how to pick values, and how to monitor them in production.

## 1. What Is Concurrency in AWS Lambda?

Concurrency is the number of invocations being processed simultaneously. Each active invocation requires one unit of Lambda execution capacity. For a synchronous function, if one request takes 200 ms on average and there are 50 requests per second, average concurrent invocations are approximately:

\[
Concurrency = RequestsPerSecond \times AverageDurationSeconds
\]

For example:

\[
50 \times 0.2 = 10
\]

The function needs around 10 concurrency at that load level. This is an estimate based on average traffic and processing time; for production planning, add headroom for bursts, latency variance, retries, and high-percentile load.

Lambda creates or reuses execution environments to handle invocations. Under the standard Lambda model, one environment handles one invocation at a time; when multiple invocations arrive simultaneously, Lambda needs multiple environments. If a function receives load exceeding available concurrency capacity, invocations may be throttled or queued/retried depending on the trigger type and invocation mechanism.

A function's concurrency is governed by multiple limits:

- **Account concurrency quota:** total concurrency available to functions in an AWS account and Region.
- **Function reserved concurrency:** dedicated capacity reserved for the function, which also acts as its concurrency ceiling.
- **Provisioned concurrency:** number of pre-initialized environments for a version or alias; requests beyond this count may use on-demand capacity if available.
- **Trigger and dependency limits:** API Gateway, event source mappings, queues, databases, or downstream services may have their own quotas.

## 2. Reserved Concurrency: Reserving Capacity and Capping Maximum Concurrency

Reserved concurrency is a concurrency allocation set aside for a Lambda function from the account concurrency pool. Setting this value guarantees the function can use its reserved capacity within quota and service limits, while also preventing the function from exceeding that number.

For example, setting reserved concurrency of `orders-api` to 120:

- At most 120 invocations of the function can run concurrently.
- Other functions cannot consume this reserved concurrency.
- Other functions without reserved concurrency share the remaining unreserved pool.
- If `orders-api` receives more than 120 concurrent invocations, the excess is throttled.

Reserved concurrency has two simultaneous effects:

1. **Capacity reservation:** protects a slice of concurrency for critical workloads, preventing other functions in the same account from consuming all capacity.
2. **Concurrency cap:** limits maximum parallelism to protect downstream systems such as databases, payment providers, or partner APIs.

Reserved concurrency does not pre-create execution environments. The function can still experience cold starts when new environments are needed. Nor does it speed up requests or incur an extra fee merely for configuring reserved concurrency; invocations and duration are billed under Lambda's standard model.

### Reserved Concurrency Set to 0

Setting reserved concurrency to 0 restricts the function from accepting new invocations under normal execution, causing Lambda to throttle incoming invocations. This serves as an emergency stop to pause a function when preventing side effects or protecting downstream systems. Keep in mind that producers/triggers may continue sending or retrying events; setting it to 0 does not drain backlogs automatically and may increase message age or retry counts.

### Impact on the Account Concurrency Pool

The sum of reserved concurrency across functions draws capacity from the shared pool. Reserving too much for low-traffic functions can starve other functions even when overall account demand is modest. AWS also requires leaving a portion of concurrency for unreserved functions under current quota rules; check Region and account quotas before allocating.

Reserved concurrency is a function-level capacity allocation tool, not a way to raise the account quota. If total actual demand exceeds the quota, optimize workloads or submit a quota increase request through AWS processes.

## 3. Provisioned Concurrency: Pre-Initializing Execution Environments

Provisioned concurrency pre-configures a set number of execution environments for a Lambda version or alias. Lambda initializes these environments before requests arrive and keeps them ready for as long as the configuration remains active. With Java, initialization can cover runtime startup, class loading, running static initializers, and framework/dependency initialization per the Lambda lifecycle.

If an alias has provisioned concurrency of 50, Lambda prepares 50 initialized environments for the version the alias points to. When up to 50 concurrent invocations hit that exact alias/version, they can be served by pre-warmed capacity, reducing cold starts caused by environment initialization.

Provisioned concurrency is useful when:

- An HTTP API has strict latency targets, especially at p95/p99.
- Workloads have predictable peak windows such as business hours, flash sales, or campaigns.
- A Java function has a relatively long startup due to frameworks or dependencies.
- The first request after idle periods needs a fast response.

Provisioned concurrency does not give a function unlimited capacity and does not eliminate every source of latency. It does not accelerate business logic, database queries, or network calls inside the handler. If concurrent requests exceed the provisioned environment count, Lambda can serve the excess using on-demand concurrency if capacity and quotas allow; those spillover invocations can still incur cold starts.

Provisioned concurrency is designed for synchronous invocation paths. For asynchronous invocations managed via Lambda's internal queue or integrated services pushing events, do not assume this setting keeps environments warm for every trigger type; check the support matrix and invocation semantics of the specific integration. Event source mappings also maintain their own scaling, batching, and concurrency controls.

### Provisioned Concurrency Must Attach to a Version or Alias

Provisioned concurrency cannot be configured directly on `$LATEST`. Publish an immutable version and attach provisioned concurrency to that version or to an alias pointing to it. In production, an alias like `prod` is usually more convenient because deployments can shift the alias to a new version.

Critically, **traffic must invoke the qualified ARN** of the alias or version configured with provisioned concurrency. If API Gateway, a Function URL, an event source, or a client invokes the unqualified function ARN or `$LATEST`, requests may bypass provisioned capacity.

Before shifting traffic to a new alias/version, wait for the provisioned concurrency status to reach `READY`. While the configuration is `IN_PROGRESS`, do not assume full capacity is available. If initialization fails, inspect the status and failure reason before routing traffic.

## 4. Direct Comparison of the Two Mechanisms

| Criterion | Reserved concurrency | Provisioned concurrency |
|---|---|---|
| Goal | Dedicate capacity to a function and cap maximum concurrency | Pre-initialize environments to reduce cold starts |
| Configuration target | Lambda function | Published version or alias |
| Pre-creates environments? | No | Yes |
| Caps maximum concurrency? | Yes, at the reserved value | Does not cap total function concurrency on its own |
| Requests beyond configuration | Exceeding reserved gets throttled | Exceeding provisioned can spill over to on-demand if capacity exists |
| Downstream protection | Can cap maximum parallelism | Does not replace a concurrency cap; use reserved concurrency or other limits to protect downstream |
| Reduces cold starts | No | Yes, within provisioned capacity when traffic hits the right alias/version |
| Separate configuration fee | No separate fee for reservation | Charged for provisioned capacity over time, in addition to standard invocation fees |
| When appropriate | Critical functions needing dedicated capacity or load capping | Latency-sensitive functions with predictable load or requiring always-ready environments |

The two mechanisms complement each other. Reserved concurrency answers "how many concurrent invocations is the function allowed to run, and does it have dedicated capacity?". Provisioned concurrency answers "out of the usable capacity, how many environments are initialized upfront?".

## 5. How the Two Mechanisms Interact

When a function has both reserved concurrency and provisioned concurrency, provisioned concurrency must fit within the allocated reserved concurrency limit. Reserved concurrency is the ceiling; provisioned concurrency is the pre-warmed portion inside that ceiling.

Example:

~~~text
Reserved concurrency = 120
+-------------------------------------------------------+
| 50 provisioned environments | 70 un-warmed capacity   |
+-------------------------------------------------------+
Total maximum function concurrency = 120
~~~

In this example:

- The first 50 invocations can use pre-warmed provisioned environments.
- When concurrency exceeds 50, invocations beyond provisioned can use on-demand capacity.
- Total function concurrency still cannot exceed 120.
- If concurrency exceeds 120, excess invocations are throttled.

The remaining 70 are not 70 constantly warm environments. Lambda creates environments on-demand only when needed, which can incur cold starts. If reserved concurrency is not set, provisioned concurrency still draws capacity from the account pool; include both this capacity and spillover demand in quota planning.

## 6. Example Configuration for a Java HTTP API

Suppose an order-processing API sees peak traffic around 160 requests/second. Average processing duration is 250 ms:

\[
160 \times 0.25 = 40
\]

Estimated average concurrency is roughly 40. To leave buffer for traffic fluctuations and latency variance, the team might test provisioned concurrency of 60 or 70 and measure in practice. Suppose the team sets:

- Reserved concurrency: 100 to cap parallelism and protect the database.
- Provisioned concurrency: 60 to keep 60 environments ready during peak hours.
- Alias: `prod` pointing to a published version configured with provisioned concurrency.

With that setup, the function allows up to 100 concurrent invocations. 60 environments are pre-initialized; up to 40 invocations beyond provisioned can use on-demand capacity within the reserved limit. If the database can only handle 80 concurrent requests, a reserved concurrency of 100 may still be too high; calculate downstream limits and connection pools rather than sizing solely from Lambda capacity.

This example is a starting point for testing. Never take RPS multiplied by average duration as the final provisioned value without measuring bursts, p95/p99 durations, batching behavior, retries, and dependency capacity.

## 7. Estimating Concurrency and Setting Headroom

### Basic Formula

For synchronous HTTP workloads:

\[
RequiredConcurrency \approx PeakRPS \times AverageDurationSeconds
\]

For example, 80 requests/second with 0.4-second average duration requires about 32 concurrency. If duration doubles to 0.8 seconds due to a slow database, the same traffic requires about 64 concurrency. Thus, memory/CPU, GC, and dependency latency also drive concurrency demand.

### Do Not Rely Only on Averages

Averages provide a high-level estimate, but production APIs must examine:

- Peak RPS over short windows, not just daily averages.
- p50, p95, and p99 durations.
- Traffic bursts when many clients retry or start sessions simultaneously.
- Time the function spends waiting on dependencies, since invocations still hold concurrency while waiting.
- Event source mapping batch sizes and concurrency settings for queues/streams.
- Extra invocations generated by retries, duplicate deliveries, or workflow fan-out.

### Choosing Reserved Concurrency

Reserved concurrency should be derived from two bounds: capacity that must be guaranteed to the workload and maximum load dependencies can withstand. If a database has a small connection limit, reserved concurrency may be set below Lambda's theoretical peak capacity. If a function needs priority capacity, reserve enough while still leaving room in the account pool for other functions.

### Choosing Provisioned Concurrency

Provisioned concurrency should be based on peak-hour concurrency or the load tier where the SLA cannot tolerate cold starts. You can start with p95 concurrency in the target window plus headroom, then tune from spillover and utilization metrics. If only a core slice of traffic needs cold-start avoidance, you do not need to provision the entire reserved concurrency.

## 8. Autoscaling Provisioned Concurrency

Provisioned concurrency can be adjusted manually, on a schedule, or automatically using Application Auto Scaling. For clearly scheduled traffic, scheduled scaling can raise capacity ahead of peak hours and scale down afterward. For variable traffic, target tracking can use the `LambdaProvisionedConcurrencyUtilization` metric to adjust provisioned environment counts.

### Scheduled Scaling

For example, a ticketing API routinely sees traffic surge at 08:00. You can schedule provisioned concurrency to increase ahead of time—say at 07:45—so Lambda has time to initialize environments. After the peak ends, scale back down to baseline.

Do not schedule scaling at the exact minute traffic arrives if initialization takes time. Observe how long it takes to reach `READY` and schedule earlier. Schedules should reflect real timezones and holidays/campaigns; AWS schedules usually require explicit timezone settings or clear UTC conversion.

### Target Tracking

Application Auto Scaling can track provisioned concurrency utilization. As utilization rises, the service increases provisioned environments; as it falls, capacity can scale down per policy. Autoscaling has lag, so it cannot instantaneously absorb sudden spikes. When latency requirements are strict, keep a minimum capacity baseline combined with scheduled scaling for known surges.

### Coordinating with Reserved Concurrency

Maximum provisioned capacity must fit within reserved concurrency and account quotas. Under autoscaling, `max capacity` must not exceed what can be allocated. If provisioned concurrency scales up while reserved concurrency or the account pool is insufficient, the configuration may fail to reach the desired state or starve other functions.

## 9. Monitoring Metrics and Detecting Spillover

CloudWatch metrics help evaluate whether your configuration meets workload demands:

| Metric | Meaning | How to interpret |
|---|---|---|
| ConcurrentExecutions | Number of concurrent invocations running | Compare against reserved concurrency and peak traffic |
| UnreservedConcurrentExecutions | Concurrency used from the unreserved pool | Track remaining capacity for shared functions |
| Throttles | Number of throttled invocations | Check reserved cap, account quota, and other limits |
| ProvisionedConcurrentExecutions | Number of provisioned environments currently in use | Compare against provisioned capacity |
| ProvisionedConcurrencyUtilization | Utilization ratio of provisioned concurrency | Use to tune provisioned level or autoscaling target |
| ProvisionedConcurrencySpilloverInvocations | Invocations exceeding provisioned capacity and running on-demand | If rising during cold-start-sensitive SLA windows, consider increasing provisioned capacity |
| ProvisionedConcurrencyInvocations | Invocations served by provisioned concurrency | Assess usage of paid provisioned capacity |
| Duration | Invocation processing time | Increasing duration drives up concurrency demand |

Beyond metrics, inspect initialization logs and `Init Duration` in Lambda REPORT logs when cold starts occur. Throttles are not caused only by reserved concurrency; they can stem from account quotas, scaling rates, or trigger limits. Always correlate Lambda metrics with API Gateway, queues, event source mappings, and downstream systems.

### Quick Interpretation Guide

- **High utilization, rising spillover:** provisioned concurrency may be below demand during that window.
- **Sustained low utilization:** you may be over-provisioned and paying for underused capacity.
- **Rising throttles while provisioned utilization is low:** check reserved concurrency, account quota, alias/ARN, triggers, and configuration errors before raising provisioned concurrency.
- **Rising spillover despite sufficient provisioning:** verify traffic hits the right alias/version, metrics use matching dimensions, and concurrency bursts did not exceed expectations.
- **Rising duration:** locate bottlenecks in the handler or dependencies; adding provisioned concurrency only addresses capacity/cold starts, not slow execution.

## 10. Cost of Reserved and Provisioned Concurrency

Reserved concurrency has no separate charge merely for holding a concurrency reservation. However, reserving capacity carries an opportunity cost: other functions cannot use that slice of capacity. Invocations are still billed for requests and duration under Lambda's standard model.

Provisioned concurrency is billed based on configured concurrency count, allocated memory, and how long the configuration remains active. Invocations running on provisioned capacity also incur request and duration charges at applicable rates. Consequently, keeping many provisioned environments during idle periods still incurs provisioned capacity charges.

When estimating costs, include:

1. Number of provisioned environments per time window.
2. Function memory size.
3. Hours/days or total duration provisioned capacity is maintained.
4. Invocation requests and duration on provisioned capacity.
5. Spillover invocations running on-demand.
6. API Gateway, CloudWatch Logs, data transfer, and dependency costs such as databases.

Unit prices vary by Region, architecture, runtime, and time. Use the AWS Pricing Calculator or current regional pricing tables for exact figures. Do not compare based on Lambda costs alone: cutting cold starts may improve conversion/SLA, while over-provisioning can inflate costs substantially.

### When Is Provisioned Concurrency Worth It?

Provisioned concurrency typically makes sense when cold-start latency noticeably hurts user experience or SLAs, traffic is predictable or has a steady baseline, and the value of lower latency outweighs environment maintenance fees. If a workload has low request volume, is not latency-sensitive, or tolerates cold starts, reserved concurrency or on-demand concurrency may suffice.

## 11. Configuring via the AWS CLI

The commands below illustrate function `orders-api` and alias `prod`. Run them in the right AWS account and Region; the IAM principal needs corresponding Lambda permissions.

### Setting Reserved Concurrency

~~~bash
aws lambda put-function-concurrency \
  --function-name orders-api \
  --reserved-concurrent-executions 100
~~~

Reading configuration:

~~~bash
aws lambda get-function-concurrency \
  --function-name orders-api
~~~

### Publishing a Version and Creating an Alias

~~~bash
aws lambda publish-version \
  --function-name orders-api

aws lambda create-alias \
  --function-name orders-api \
  --name prod \
  --function-version 42
~~~

If the alias already exists, use `update-alias` to shift the alias to the new version once the deployment is ready. Version 42 in the example is illustrative only.

### Setting Provisioned Concurrency for an Alias

~~~bash
aws lambda put-provisioned-concurrency-config \
  --function-name orders-api \
  --qualifier prod \
  --provisioned-concurrent-executions 60
~~~

Checking status:

~~~bash
aws lambda get-provisioned-concurrency-config \
  --function-name orders-api \
  --qualifier prod
~~~

Wait for `Status` to become `READY` before shifting production traffic to the alias. If it returns `IN_PROGRESS`, continue monitoring; if `FAILED`, check `StatusReason` and inspect initialization/configuration.

### Removing Configurations When No Longer Needed

~~~bash
aws lambda delete-provisioned-concurrency-config \
  --function-name orders-api \
  --qualifier prod

aws lambda delete-function-concurrency \
  --function-name orders-api
~~~

The first command removes provisioned concurrency from the alias; the second removes reserved concurrency from the function so it returns to sharing the account pool under default policy. Only run these after evaluating the impact on traffic and downstream systems.

## 12. Safe Version and Alias Deployment

A typical deployment workflow:

1. Build and deploy new code to `$LATEST`.
2. Run tests or smoke tests on the new version.
3. Publish an immutable version.
4. Configure provisioned concurrency on the version or alias that will receive traffic.
5. Wait for provisioned concurrency status to reach `READY`.
6. Shift the production alias to the new version.
7. Monitor error rate, duration, spillover, utilization, and throttles.
8. If an issue occurs, shift the alias back to the previous version following the rollback procedure.

Do not publish a new version and immediately flip the alias if the goal is to avoid cold starts on initial traffic. Prepare capacity on the target version first. Also confirm that API Gateway integrations or clients invoke the alias ARN rather than `$LATEST` or an unqualified ARN.

If using weighted alias routing for canary rollouts, understand how provisioned capacity is configured and distributed across aliases/versions. Test actual traffic paths to ensure requests hit the intended prepared qualifier.

## 13. Combining with Java Functions and Cold Starts

Provisioned concurrency pre-initializes environments, so it can absorb part of Java startup overhead before requests arrive. Tasks like class loading, running static initializers, framework startup, and creating shared clients can happen during the environment initialization phase.

However, you still need to optimize code:

- Keep static initializers short; do not make synchronous database or external API calls.
- Reduce unnecessary dependencies and component scanning.
- Reuse thread-safe HTTP/SDK clients at the environment level.
- Do not store request/user state in static fields.
- Size connection pools for the maximum total concurrency that can occur across multiple environments.
- Measure init duration, handler duration, and downstream latency separately.

For Java, SnapStart is another option on supported Lambda runtimes/versions. SnapStart saves a snapshot of the execution environment after initialization for faster restoration. Combining SnapStart with provisioned concurrency and compatibility limits depends on version/runtime; check current AWS documentation before choosing a design. Regardless of mechanism, handle uniqueness of random values, credentials, and connections properly after restoration.

## 14. Using Reserved Concurrency to Protect Downstream Systems

Suppose the `create-invoice` function calls a database whose connection pool only sustains 40 concurrent queries from that function. If Lambda scales the function up to hundreds of environments, the database can be overwhelmed even though Lambda still has quota.

Setting reserved concurrency appropriately caps concurrent invocations. Remember to sum connections across all functions and other services accessing the same database. If each invocation opens multiple connections or holds connections long, reserved concurrency must be set lower than the raw connection limit implies.

For queue consumers, reserved concurrency indirectly limits consumption rate by capping concurrent function invocations. However, event source mappings also have their own batch size, maximum concurrency, and scaling settings. Coordinate these limits to avoid runaway message backlogs or downstream database overload.

Do not use provisioned concurrency as a circuit breaker. If a downstream dependency fails, provisioned environments will keep calling it. Use timeouts, bounded retries, backoff, circuit breakers, or reduced concurrency to contain incidents.

## 15. Common Misconceptions and Configuration Errors

| Misconception/error | Consequence | Resolution |
|---|---|---|
| Thinking reserved concurrency keeps the function always warm | Still hits cold starts when new environments spin up | Use provisioned concurrency if pre-warmed environments are needed |
| Thinking provisioned concurrency caps concurrency | Function can spill over to on-demand and keep scaling | Use reserved concurrency if a hard maximum cap is needed |
| Configuring provisioned concurrency on `$LATEST` | Desired qualifier is not supported | Publish a version and use a version/alias |
| API invokes unqualified ARN instead of alias | Requests may bypass provisioned capacity | Check integration URI and qualifier |
| Shifting traffic before status is `READY` | Early requests may lack initialized capacity | Wait for configuration to be ready before switching the alias |
| Provisioned concurrency greater than reserved concurrency | Invalid configuration or impossible to allocate | Set reserved concurrency >= provisioned concurrency |
| Setting reserved concurrency too high | Consumes account pool and throttles other functions | Budget at account level and monitor the unreserved pool |
| Setting provisioned concurrency too low | Spillover rises and requests still cold start | Size from peak concurrency and spillover metrics |
| Over-provisioning all day | Paying for idle capacity | Use scheduled/target tracking scaling with sensible min/max |
| Looking only at `Throttles` to raise PC | May miss the true root cause | Check account quota, reserved cap, alias, and triggers |
| Raising PC to fix a slow database | Sends more requests downstream and can worsen errors | Optimize dependencies and cap concurrency |

## 16. Selection and Testing Process

When designing a Lambda function, follow these steps:

1. **Measure baseline:** collect RPS, duration, concurrency, cold starts, p95/p99, and error rate.
2. **Clarify the goal:** protect capacity, throttle downstream load, or cut cold starts?
3. **Choose reserved concurrency:** calculate maximum parallelism dependencies tolerate and capacity the function must guarantee.
4. **Choose provisioned concurrency:** estimate concurrency needed warm during critical windows/SLAs; add justified headroom.
5. **Check account quotas:** total reserved, provisioned, and demand from other functions in the Region.
6. **Configure qualifiers:** publish version, configure alias, and ensure traffic hits the right ARN.
7. **Wait for `READY`:** verify provisioned capacity is initialized before shifting traffic.
8. **Test bursts:** spike RPS to observe spillover, throttles, duration, and dependency saturation.
9. **Test deployments:** update version, shift alias, roll back, and confirm capacity per version.
10. **Monitor costs:** weigh provisioned fees against latency gains and cold-start reductions; tune schedules or autoscaling.

Test cases including: concurrency below PC, equal to PC, above PC but below reserved, above reserved, near-exhausted account pool, initialization failures, alias pointing to the wrong version, delayed scheduled scaling, and downstream throttling. These tests reveal exactly which requests use provisioned capacity, which spill over, and when throttling triggers.

## 17. Conclusion

Reserved concurrency and provisioned concurrency address two distinct needs. Reserved concurrency dedicates capacity to a function and sets a maximum concurrency limit, making it useful for protecting critical workloads and controlling downstream pressure. Provisioned concurrency pre-initializes execution environments for a version or alias, making it useful for reducing cold starts and stabilizing latency.

When combined, provisioned concurrency must stay within the reserved limit if the function configures reserved concurrency. Estimate concurrency from peak request rates and duration, add headroom, verify account quotas, route traffic through the prepared alias/version, wait for `READY`, and track utilization, spillover, and throttles. Pick values backed by real measurements to balance latency, resilience, and cost.
