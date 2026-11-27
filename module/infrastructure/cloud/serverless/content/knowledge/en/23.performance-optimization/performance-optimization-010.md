# Evaluating Provisioned Capacity and Snapshots by Workload

A serverless function can execute its business logic quickly yet still respond slowly on the first invocations of a new execution environment. With Java, starting the JVM, loading classes, initializing frameworks, creating clients, and establishing connections can add substantial latency at the tail of the distribution. If an API has a tight SLO, even a handful of slow initializations can degrade user experience despite most requests being fast.

AWS Lambda provides two mechanisms commonly considered for this problem: **Provisioned Concurrency (PC)** and **Lambda SnapStart**. PC pre-allocates a number of initialized execution environments ready to serve invocations. SnapStart runs the initialization phase when publishing a version, saves a snapshot of memory and disk state, and restores execution environments from that snapshot when scaling.

These two mechanisms solve different problems. PC suits workloads needing ultra-low latency with predictable or manageable ready concurrency. SnapStart cuts initialization cost during scale-out without holding a fixed number of pre-allocated instances. On AWS Lambda, SnapStart and Provisioned Concurrency cannot be enabled simultaneously on the same function. Therefore, the choice must be grounded in traffic shape, SLOs, Java application compatibility, and actual cost.

## 1. Why Evaluate Capacity and Snapshots?

A cold start occurs when Lambda must create a new execution environment before running the handler. This process can include downloading code, starting the runtime, initializing the JVM, loading dependencies, running static initializers, and setting up shared resources. With Java frameworks like Spring Boot, Quarkus, or Micronaut, initialization can be substantial compared to request processing time.

A request typically flows through these stages:

~~~mermaid
flowchart LR
    A["Request arrives at Lambda"] --> B{"Environment ready?"}
    B -->|"Yes"| C["Invoke handler"]
    B -->|"No"| D["Create new environment"]
    D --> E["Start runtime and Init"]
    E --> C
    C --> F["Return response"]
~~~

If a request must wait for the Init step, latency can spike sharply. This issue is particularly visible with:

- User-facing synchronous APIs with p95 or p99 SLOs.
- Payment, login, or transaction-confirmation endpoints.
- Workloads with sudden traffic bursts after idle periods.
- Java functions using large frameworks or many dependencies.
- Batch-processing systems with deadlines and steady throughput requirements.

Not every cold start needs capacity or snapshots. If a function runs only periodically, processes asynchronous messages, or callers already have retries/backoff, initialization delay may not affect the business. Measure latency first and identify how much comes from Init, Restore, handler, network, or dependencies.

## 2. Three Concepts to Distinguish

In AWS Lambda, the terms below serve distinct purposes:

| Mechanism | Function | Pre-initializes Environments? | Additional Cost |
|---|---|---:|---|
| On-demand concurrency | Lambda creates environments on demand | No | Requests and duration per usage |
| Reserved Concurrency | Sets a concurrency limit and reserves capacity for the function | No | No separate charge for the reserved setting |
| Provisioned Concurrency | Pre-allocates initialized environments | Yes | Billed by configured PC amount and retention duration |
| SnapStart | Captures snapshot after Init, restores environments from snapshot | Creates snapshot on version publish | For supported managed Java runtimes, no separate SnapStart cache/restore fee |

Reserved Concurrency is not a pool of always-warm instances. It gives the function dedicated concurrency headroom and sets a maximum cap to protect dependencies. The function can still hit cold starts whenever new environments are created.

Provisioned Concurrency is a count of pre-initialized environments. It fits when requests must be served with minimal startup latency. SnapStart saves post-initialization state so environments created during scaling can recover faster.

Never use these terms interchangeably in designs or dashboards. Clearly state whether you are measuring reserved concurrency, provisioned concurrency, on-demand concurrency, or environments restored from snapshots.

## 3. How Does Provisioned Concurrency Work?

When Provisioned Concurrency is configured, Lambda pre-initializes a specified number of execution environments for a published version or alias. These environments stay ready for requests, avoiding most Init time on the invocation path.

For example, if the `live` alias is configured with 40 PC, Lambda maintains 40 initialized environments for that alias. While concurrent requests stay within ready capacity, Lambda serves them using those environments.

~~~mermaid
flowchart TD
    A["Published version / live alias"] --> B["Provisioned Concurrency = 40"]
    B --> C["40 initialized environments"]
    C --> D["Request concurrency <= 40"]
    D --> E["Invoke on ready environment"]
    C --> F["Request concurrency > 40"]
    F --> G["Spillover to standard concurrency if capacity available"]
    G --> H["Cold start may occur"]
~~~

PC reduces cold starts for the provisioned concurrency slice. If traffic exceeds that level, Lambda can use standard concurrency to handle the excess, subject to reserved concurrency and account capacity. That spillover slice may experience cold starts.

PC is configured on a specific published version or alias—never on the unpublished `$LATEST` version. If API Gateway, an event source, or a caller still invokes `$LATEST` instead of the alias with PC, requests will not use the provisioned environments.

When allocating PC, Lambda needs time to initialize the environments. New configurations may remain in `IN_PROGRESS`; route latency-sensitive traffic to that alias only after allocation completes. Never treat issuing the configuration command as proof that capacity is ready.

## 4. Reserved Concurrency vs. Provisioned Concurrency

Both concurrency settings can be configured together, yet they serve different goals.

| Criterion | Reserved Concurrency | Provisioned Concurrency |
|---|---|---|
| Goal | Reserve capacity and cap concurrent executions | Keep initialized environments ready |
| Prevent function from consuming too much concurrency | Yes | Not the primary goal |
| Reduce cold starts | No | Yes, within the provisioned capacity |
| Configuration scope | Function-level, including `$LATEST` | Published version or alias |
| Separate configuration charge | No | Yes |
| Relationship between the two | Can act as an upper limit | PC cannot exceed reserved concurrency when both are set |

Reserved Concurrency is useful when a function calls a database with a low connection limit. For example, if the database supports only 80 connections from this workload, the team can set reserved concurrency to cap function scaling. PC can then be set lower than or equal to that cap if the endpoint requires warm environments.

Do not set reserved concurrency too low just to save money if it causes requests to throttle. Conversely, do not raise concurrency without checking connection pools, downstream rate limits, and account quotas.

## 5. How Does SnapStart Work?

SnapStart shifts when Init runs. Instead of waiting for the first invocation of a new environment, Lambda initializes the code when publishing a function version, captures a snapshot of memory and disk state after initialization, encrypts the snapshot, and caches it.

When the function version is invoked and scales up, Lambda creates environments by restoring from the snapshot. This can substantially cut latency from JVM startup, class loading, and framework initialization.

~~~mermaid
flowchart TD
    A["Deploy code and configure SnapStart"] --> B["Publish function version"]
    B --> C["Lambda runs Init"]
    C --> D["Capture memory and disk snapshot"]
    D --> E["Encrypt and cache snapshot"]
    E --> F["Invoke published version"]
    F --> G["Restore execution environment"]
    G --> H["After-restore hook if present"]
    H --> I["Invoke handler"]
~~~

SnapStart is a snapshot-based startup optimization, not a fixed pool of always-ready environments. Whenever more environments are needed, Lambda restores from the snapshot instead of initializing from scratch.

SnapStart can cut startup latency to sub-second levels under suitable conditions, though this is not a fixed latency guarantee for every request. It does not replace measuring p95/p99, checking restore times, and optimizing handler code.

## 6. Comparing PC, SnapStart, and On-Demand by Workload

| Workload | On-Demand | SnapStart | Provisioned Concurrency |
|---|---|---|---|
| Low-traffic API, relaxed SLO | Usually sufficient | Can trim Init outliers | Usually wasteful |
| Java API with heavy framework, variable traffic | Can suffer long cold starts | Strong option to cut Init | Use if ultra-low startup is mandatory |
| API with clear hourly peaks | Can scale slowly at peak | Cuts Init during scaling | Can schedule PC ahead of peaks |
| API with sudden bursts and ultra-tight SLO | Cannot guarantee low latency | Reduces but does not eliminate all cold starts | Better fit if capacity suffices |
| Asynchronous queue consumer | Usually sufficient | Helpful if Init is a bottleneck | Use only when throughput/latency requires it |
| Scheduled batch job | Usually sufficient | Can speed up Java startup | Provision around run window if deadline is tight |
| Rarely invoked function | Low cost | May see limited benefit | Usually unsuitable |

SnapStart is often the first choice to test for Java functions needing lower cold starts during scale-out, provided the function is compatible. PC fits when latency SLOs demand pre-initialized environments ahead of requests and the organization accepts ongoing capacity costs.

Do not adopt PC simply because a single cold start appeared in the logs. Quantify the cold-start rate, user impact, and latency percentiles across all requests.

## 7. Characterizing Workloads by Traffic Shape

Required capacity depends on concurrent requests, not merely total daily requests.

Common traffic shapes:

- **Steady:** consistent requests throughout the day; PC can hold a small baseline.
- **Predictable peak:** traffic climbs at business open, start of day, or month-end; scheduled scaling can prepare capacity beforehand.
- **Bursty:** sudden spikes from campaigns or events; fixed PC may run short, requiring auto scaling and fallbacks.
- **Sporadic:** irregular arrivals; on-demand or SnapStart usually makes more sense.
- **Batch window:** many messages processed in a short burst; size concurrency to throughput and duration while considering queue batching.
- **Seasonal:** traffic varies by week, month, or season; track history and schedule scaling appropriately.

For every workload, collect at least:

1. Requests per second across time intervals.
2. Mean duration and p50/p95/p99 distributions.
3. Concurrent executions, especially peaks.
4. Percentage of requests arriving when no environment is ready.
5. Init Duration or Restore Duration.
6. Spillover rate if PC is already enabled.
7. Downstream capacity and connection limits.
8. Caller SLOs/latency budgets.
9. Hours of the day when low latency is truly required.

A function receiving 100,000 requests/day spread evenly may need less concurrency than a function receiving just 10,000 requests inside a 30-second burst.

## 8. Estimating Required Concurrency

Approximate formula:

\[
Concurrency = RequestsPerSecond \times AverageDurationSeconds
\]

For example, an API receiving an average of 30 requests/second with an average duration of 0.4 seconds:

\[
30 \times 0.4 = 12
\]

Estimated average concurrency is 12. This is not yet production capacity because traffic has peaks, duration has outliers, and concurrency climbs whenever downstream slows down.

A more practical approach:

1. Use the `ConcurrentExecutions` metric to observe peaks.
2. Analyze at 1-minute windows or finer from application telemetry.
3. Use p95/p99 concurrency if granular data is available.
4. Determine the share of requests needing PC to meet the SLO.
5. Add a buffer for traffic variance and scaling time.
6. Check account quotas and reserved concurrency.
7. Load test at the selected capacity.

AWS documents estimating concurrency as requests/second multiplied by average duration and suggests adding roughly a 10% buffer over typical concurrency. For production, buffers must reflect actual variance and SLOs; 10% does not guarantee enough headroom for bursts.

For example, a workload typically peaks at 200 concurrent executions. A starting point might test 220 PC, then load test and adjust based on spillover, latency, and cost. If p99 peaks significantly above 200, evaluate using that peak figure instead.

## 9. Measuring Latency Correctly

Do not measure only handler `Duration`. End-to-end requests can include DNS, TLS, API Gateway, Lambda initialization/restore, handler execution, network calls to databases, and response serialization.

Measure:

- p50: typical experience.
- p90/p95: majority of slower-than-normal requests.
- p99/p99.9: outliers that can violate SLOs.
- Init Duration: initialization time during environment creation.
- Restore Duration: snapshot restoration time with SnapStart.
- Handler Duration: time code spends handling invocations.
- Integration latency: time the gateway waits on the backend.
- Error/throttle rate: failures from overload or misconfiguration.

If p50 is healthy yet p99 is poor, PC or SnapStart can improve tail latency. However, if the handler spends most of its time waiting on a database or partner API, cutting Init only trims a small slice of total latency.

Log correlation IDs and release versions to compare measurements across releases. Never mix canary, staging, and production traffic into one distribution without separating sources.

## 10. Choosing SnapStart for Java Functions

SnapStart supports Java 11 and later on supported managed runtimes. You can use ZIP deployments or container images built on compatible Lambda base images. Check the supported runtime and Region list before enabling.

SnapStart is a good fit when:

- JVM and framework initialization account for a significant share of cold starts.
- The function scales out to many execution environments.
- Init-driven latency outliers impact SLOs.
- The application can handle snapshot/restore semantics properly.
- Provisioned Concurrency is not needed on the same function.
- The function does not depend on features restricted by SnapStart.

SnapStart works only with published function versions and aliases pointing to versions. Never use `$LATEST` to evaluate results. After publishing, wait until version State is `Active` and OptimizationStatus is `On` before shifting traffic.

## 11. SnapStart Compatibility Limits

Before selecting SnapStart, review current constraints:

- SnapStart and Provisioned Concurrency cannot be enabled on the same function simultaneously.
- Applies only to published versions and aliases pointing to versions, not `$LATEST`.
- Does not support Amazon EFS or Amazon S3 Files.
- Does not support ephemeral storage larger than 512 MB.
- Supported only on specific managed runtimes; Java 11 and later are the relevant group for this lesson.
- Container images must use compatible base images and adhere to hooks/uniqueness guidelines.
- Snapshots do not preserve all network connections or transient data in a form safe to use directly after restore.

SnapStart can run inside a VPC if network and service conditions are met. Still, test DNS, connections, and dependencies after restore.

Support lists evolve over time. Before production, verify AWS documentation for your Region, runtime, deployment format, and actual integrated services.

## 12. Snapshots and State Uniqueness

Lambda uses one initialized snapshot as the starting state for many execution environments. Consequently, data generated once during initialization can be cloned across multiple environments upon restore.

Values that must not be generated and baked into the snapshot if they need to be unique per environment or invocation:

- UUIDs or execution environment IDs.
- Seeds or internal state of pseudo-random generators.
- Short-lived secrets or expiring tokens.
- Timestamps computed at initialization time.
- Nonces, challenges, or anti-replay tokens.
- In-memory counters assumed to be globally unique.

Generate unique values inside the handler or an after-restore hook. For cryptographic randomness, use a CSPRNG such as `java.security.SecureRandom` and verify cryptography library versions per SnapStart guidance. Never use a fixed seed or pre-snapshot random value to generate secrets across multiple environments.

Example generating an ID per invocation:

~~~java
import java.util.UUID;

public class OrderHandler {
    public String handleRequest(OrderEvent event, Context context) {
        String invocationId = UUID.randomUUID().toString();

        return process(event, invocationId);
    }

    private String process(OrderEvent event, String invocationId) {
        // Attach ID to invocation logs or traces.
        return "accepted";
    }
}
~~~

If a per-execution-environment ID is needed, generate it after restore and store it in environment state. Never use hostname as a unique ID because multiple environments restored from the same snapshot may observe the same hostname.

## 13. Network Connections and Transient Data After Restore

Network connections opened during initialization are not guaranteed to remain valid after restoring a snapshot. Sockets may have expired, peers may have closed connections, or connection state may be out of sync.

For Java functions:

- Validate connection pools before use.
- Re-establish connections inside the handler or after-restore hooks.
- Use finite timeouts and bounded retries.
- Never bind connections to fixed source ports.
- Do not cache DNS inside the JVM in ways that cause stale addresses post-restore.
- Refresh credentials and transient data before use.
- Load-test database pools, HTTP clients, and TLS sessions.

The AWS SDK typically includes connection/credential recovery mechanisms, yet you should still test with your exact SDK version and dependencies. Do not assume every HTTP or JDBC library automatically recovers connections after a snapshot restore.

If using Java DNS caching with SnapStart, check AWS guidance for your runtime version. Certain JVM DNS cache settings can trigger connection timeouts after restore. Only modify TTLs after understanding both the JVM cache and Lambda's managed DNS cache.

## 14. Using CRaC Runtime Hooks in Java

AWS Lambda supports runtime hooks modeled on Coordinated Restore at Checkpoint (CRaC). Two key callbacks:

- `beforeCheckpoint()`: runs before Lambda captures the snapshot.
- `afterRestore()`: runs after Lambda restores an execution environment from the snapshot.

Use `beforeCheckpoint` to close resources that should not be snapshotted or prepare stable state. Use `afterRestore` to recreate connections, refresh transient data, or regenerate values needing uniqueness.

Illustrative example:

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class RestoreLifecycle implements Resource {
    private static final RestoreLifecycle INSTANCE =
            new RestoreLifecycle();

    private volatile String environmentId;

    private RestoreLifecycle() {
        Core.getGlobalContext().register(this);
    }

    public static void initialize() {
        // Call during static initialization to register the resource.
        // INSTANCE holds a strong reference so the hook is not garbage collected.
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        // Close or clean up resources unsafe for snapshotting.
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        environmentId = java.util.UUID.randomUUID().toString();
        // Re-initialize required resources after restore.
    }

    public String environmentId() {
        return environmentId;
    }
}
~~~

This is a structural example; add a compatible `org.crac` dependency and invoke `initialize` inside a class loaded by the runtime. CRaC `Context` holds a `WeakReference` to `Resource`, so the application must retain a strong reference to ensure callbacks fire. `afterRestore` callbacks have a completion time limit; never run lengthy tasks or wait indefinitely on dependencies inside hooks.

If hooks are unnecessary, lazy refresh inside the handler can be simpler. Choose where recovery happens based on latency budgets and resource lifecycles.

## 15. Optimizing Java Initialization Before Snapshotting

SnapStart delivers the most benefit when heavy setup runs during initialization so the snapshot captures pre-warmed state.

Candidates to consider:

- Loading commonly used classes and dependencies.
- Initializing the framework container.
- Creating SDK clients that can recover safely.
- Parsing immutable configuration.
- Preparing serializers/deserializers.
- Preloading small, stable metadata or models.
- Safely warming up hot code paths so JIT compiles before the snapshot.

Never execute business side effects during initialization. For instance, never create orders, send emails, charge payments, write audit events, or publish messages inside static initializers. Lambda can run initialization when publishing versions and building snapshots; those side effects do not represent normal business invocations.

If using dummy invocations to warm up, ensure synthetic requests never trigger transactions, data writes, or notifications. Use mocked dependencies or read-only paths if possible.

Do not preload every dependency just because you can. Loading excessive data bloats the snapshot, slows down publish/restore times, and increases memory footprint. Preload only components that genuinely reduce latency on the critical path.

## 16. Optimizing Java with Provisioned Concurrency

With PC, initialization code runs while Lambda allocates capacity ahead of requests. Thus, you can move framework, client, and dependency setup outside the handler so live invocations skip repeating it.

Example:

~~~java
public final class PaymentHandler
        implements RequestHandler<PaymentRequest, PaymentResponse> {

    private static final PaymentService PAYMENT_SERVICE =
            PaymentService.createFromEnvironment();

    @Override
    public PaymentResponse handleRequest(
            PaymentRequest request,
            Context context) {

        return PAYMENT_SERVICE.process(request);
    }
}
~~~

This snippet illustrates initializing a service once per environment lifecycle. The service must be thread-safe if the runtime or framework allows concurrent processing within the same environment; never store mutable request state in static fields.

PC does not automatically speed up the handler if slowness lies in the database, network, or algorithms. It primarily removes Init from invocations served by PC. Optimize handler code, connection pools, queries, serialization, and dependencies as usual.

If the function exhausts PC and spills over to on-demand, excess invocations can still experience cold starts. Therefore, PC must be sized and scaled to the workload rather than left at one static number.

## 17. Configuring SnapStart with AWS CLI

Enable SnapStart for published versions:

~~~bash
aws lambda update-function-configuration \
  --function-name orders-api \
  --snap-start ApplyOn=PublishedVersions
~~~

Publish a new version:

~~~bash
aws lambda publish-version \
  --function-name orders-api
~~~

Check version status:

~~~bash
aws lambda get-function-configuration \
  --function-name orders-api:12
~~~

Confirm SnapStart `OptimizationStatus` is `On` and `State` is `Active` before pointing the production alias to the new version.

Create or update an alias so callers invoke the exact version:

~~~bash
aws lambda update-alias \
  --function-name orders-api \
  --name live \
  --function-version 12
~~~

API Gateway or event sources must point to the `live` alias to use the SnapStart-enabled version. Verify integration ARNs after deployment to avoid accidentally calling `$LATEST`.

## 18. Configuring Provisioned Concurrency with AWS CLI

Provisioned Concurrency requires a published version or alias. Example allocating 40 environments for the `live` alias:

~~~bash
aws lambda put-provisioned-concurrency-config \
  --function-name orders-api \
  --qualifier live \
  --provisioned-concurrent-executions 40
~~~

Check allocation status:

~~~bash
aws lambda get-provisioned-concurrency-config \
  --function-name orders-api \
  --qualifier live
~~~

Shift traffic only after status is `READY` and allocated concurrency reaches the requested target. While `IN_PROGRESS`, capacity is not fully ready.

When traffic varies by hour, Application Auto Scaling can adjust PC via schedules or target tracking. Configure an initial provisioned concurrency value and register a scalable target before relying on auto scaling.

## 19. Auto Scaling Provisioned Concurrency

Two common approaches:

- **Scheduled scaling:** raise PC ahead of peak hours and lower it after traffic subsides.
- **Target tracking:** keep utilization near a target threshold by automatically scaling capacity up/down.

Example registering the `live` alias as a scalable target:

~~~bash
aws application-autoscaling register-scalable-target \
  --service-namespace lambda \
  --resource-id function:orders-api:live \
  --scalable-dimension lambda:function:ProvisionedConcurrency \
  --min-capacity 5 \
  --max-capacity 120
~~~

Example target tracking maintaining utilization near 70%:

~~~bash
aws application-autoscaling put-scaling-policy \
  --service-namespace lambda \
  --resource-id function:orders-api:live \
  --scalable-dimension lambda:function:ProvisionedConcurrency \
  --policy-name orders-api-pc-utilization \
  --policy-type TargetTrackingScaling \
  --target-tracking-scaling-policy-configuration '{
    "TargetValue": 0.7,
    "PredefinedMetricSpecification": {
      "PredefinedMetricType": "LambdaProvisionedConcurrencyUtilization"
    }
  }'
~~~

Min/max values are examples only. Set them based on account quotas, downstream capacity, and SLOs. Target tracking needs reaction time; for predictable traffic ramps, scheduled scaling prepares capacity earlier.

Do not scale PC up after a peak has already started and expect every request to benefit from the new capacity. Allocation takes time; schedule ahead of traffic ramps and monitor `READY` status.

## 20. Routing Callers to the Right Version or Alias

One of the most common reasons cold starts persist after enabling PC is callers failing to invoke the provisioned alias.

Verify:

- API Gateway integration URI.
- Lambda Function URL or resource policy.
- Event source mappings.
- EventBridge target ARNs.
- Step Functions task resources.
- SDK invoke targets.
- Alias routing configurations.

For example, callers must invoke the alias ARN:

~~~text
arn:aws:lambda:ap-southeast-1:123456789012:function:orders-api:live
~~~

If callers invoke an unqualified function ARN or `$LATEST`, requests can run on on-demand environments. In CloudWatch, compare alias/version metrics against overall function metrics.

With SnapStart as well, invoke the published version or an alias pointing to it. Snapshots do not apply to unpublished versions.

## 21. Cost of Provisioned Concurrency

PC introduces an additional billing dimension: configured concurrency multiplied by retention duration and function memory. When the function is invoked, requests and duration are still billed according to the pricing model. Initialization code executed while allocating or recycling environments is also billed, even if an environment has not served any request yet.

A 24/7 PC baseline costs money even with zero requests. If an API needs low latency only during business hours, scheduled scaling or lowering PC off-peak can save substantially.

When estimating costs, include:

- Minimum baseline PC maintained.
- Hours per day holding PC.
- Peak PC during traffic surges.
- Memory allocation.
- Request count and duration.
- Initialization during allocation/recycling.
- Downstream costs such as database connections or caches.
- Operational overhead and spillover risks.

Do not compare PC against on-demand Lambda solely by request count. PC purchases environment readiness, so capacity charges accrue even while environments sit idle.

## 22. Cost of SnapStart for Java

Under current AWS pricing, SnapStart carries no separate caching and restore fee for supported managed Java runtimes. Standard Lambda request and execution duration charges still apply; initialization and runtime hook execution times must be factored into duration/billing evaluations per service rules.

For other SnapStart runtimes, pricing may include snapshot caching by memory and active version duration, plus per-restore charges for each environment restoration. Therefore, do not apply Java managed runtime pricing assumptions to Python, .NET, or custom containers without checking current pricing tables.

Even for Java, clean up unused published versions. SnapStart creates snapshots per version, and stale versions inflate inventory to manage. Java snapshots can transition to `Inactive` after 14 days without invocations; the next invocation may receive `SnapStartNotReadyException` while Lambda recreates the snapshot.

Actual costs also depend on memory, retained version count, deploy frequency, and invocations. Check AWS Pricing Calculator and Cost Explorer for your Region before production decisions.

## 23. Evaluating Cost by Traffic Shape

Qualitative comparison example:

| Workload | PC 24/7 | Scheduled PC | Java SnapStart | On-Demand |
|---|---|---|---|---|
| Steady API all day | May make sense if SLO is ultra-tight | Little benefit | Can cut Init | May suffice if SLO is relaxed |
| API busy only 8 hours/day | Wastes capacity charges while idle | Often more economical | Can fit well | Cheap but has outliers |
| Unpredictable bursty API | May fall short if sized low | Misses unexpected bursts | Helpful during scale-out | Can suffer cold starts |
| Nightly batch job | Usually unjustified | Provision only around run window if needed | Can speed up startup | Usually sufficient |
| Rarely executed function | Unjustified | Unjustified | Minimal gain if rarely scaling | Usually appropriate |

Calculate total cost over the same traffic window and weigh against latency goals. If PC cuts p99 yet capacity costs outweigh business value, SnapStart or code optimization may be better choices.

Never size from monthly averages. Separate peak hours, peak days, and anomalous events to understand where ready capacity is actually needed.

## 24. Metrics to Monitor for Provisioned Concurrency

Key CloudWatch metrics:

| Metric | Meaning | How to Use |
|---|---|---|
| `ConcurrentExecutions` | Invocations running concurrently | Identify peak concurrency |
| `ProvisionedConcurrentExecutions` | PC environments actively processing invocations | Observe actual usage |
| `ProvisionedConcurrencyInvocations` | Invocations served by PC | Share of requests served by PC |
| `ProvisionedConcurrencySpilloverInvocations` | Invocations exceeding PC and using standard concurrency | Detect insufficient PC or bursts |
| `ProvisionedConcurrencyUtilization` | Ratio of PC actively utilized | Spot over- or under-allocation |
| `Throttles` | Invocations rejected due to concurrency exhaustion | Check reserved/account limits |
| `Duration` | Handler execution time | Isolate processing bottlenecks |
| `Errors` | Failed invocations | Track release quality |

`ProvisionedConcurrentExecutions` reflects busy PC environments at a point in time, not total allocated PC. `ProvisionedConcurrencyInvocations` counts invocations within a period. `ProvisionedConcurrencySpilloverInvocations` reveals requests forced onto standard concurrency because PC was fully occupied.

If spillover rises and latency degrades, you may need higher PC or scaling adjustments. If utilization stays persistently low, you may be over-provisioned. Read these metrics alongside `Duration`, `Throttles`, and traffic patterns.

## 25. Metrics to Monitor for SnapStart

With SnapStart, distinguish Init from Restore:

- `Restore Duration` shows how long Lambda spent restoring the snapshot and running after-restore hooks.
- `platform.restoreStart` marks when restoration begins.
- `platform.restoreRuntimeDone` indicates restore success, failure, or timeout.
- `platform.restoreReport` contains restore timing and billed restore time per runtime rules.
- The X-Ray `Restore` subsegment helps break down restore latency.
- Function `Duration`, `Errors`, and `Throttles` must still be monitored as usual.

SnapStart does not emit a traditional cold-start `Initialization` subsegment; traces show a `Restore` subsegment instead. Dashboards must distinguish both phases so teams do not mistakenly conclude startup latency vanished altogether.

Correlate end-to-end p99 against `Restore Duration`. If restore is fast yet handlers are slow, optimize database queries or business logic. If restore is slow due to hooks or huge snapshots, trim initialization and snapshotted data.

## 26. Controlled Benchmark and Testing Process

Do not choose PC or SnapStart solely from someone else's benchmark numbers. Test on your own function, framework, memory, Region, dependencies, and traffic shape.

Test plan:

1. Select a representative function and pin a code version.
2. Measure the on-demand baseline with identical memory and configuration.
3. Enable SnapStart, publish a new version, and wait until the snapshot is `Active`.
4. Measure startup latency, p95/p99, and throughput during scale-out.
5. Disable SnapStart on a separate test version if needed for a clean comparison.
6. Enable PC on another version/alias and allocate capacity to match expected peaks.
7. Measure in-PC latency, spillover, and capacity cost.
8. Generate bursts at both typical and peak levels.
9. Test traffic after idle periods.
10. Test deploying new versions, shifting aliases, and rolling back.
11. Repeat enough times to smooth out noise.
12. Compare costs across the same request volume and SLO target.

Hold payloads, dependencies, memory, architecture, and concurrent requests constant across options. Never compare a warm-cached build against a freshly deployed build to crown a winner.

## 27. Required Test Scenarios

| Scenario | What to Verify |
|---|---|
| First invocation after publish | SnapStart version is Active and restore succeeds |
| Scale from 1 to peak | Restore/PC allocation keeps up with traffic |
| Burst exceeding PC | Spillover behavior, latency, and throttles |
| Extended low traffic | Idle PC cost and snapshot state |
| Heavy Java framework init | Whether SnapStart actually lowers p99 |
| Slow dependency | Whether startup optimization masks another bottleneck |
| Connections post-restore | Whether JDBC/HTTP clients reconnect safely |
| Randomness/unique IDs | No state duplicated from the snapshot |
| Credential rotation | Stale tokens/credentials are never reused after restore |
| Deploying a new version | Alias routes to the right version with PC or SnapStart |
| Rollback | Previous version retains valid config and snapshot/capacity |
| Downstream saturation | Reserved concurrency and connection pools protect dependencies |

For functions processing payments or creating orders, use sandbox/test accounts and idempotent test data. Never run load tests that trigger side effects on production data.

## 28. Safe Version and Alias Deployment

PC and SnapStart attach to versions/aliases. Whenever publishing a new version, verify startup optimization settings for that version.

A typical release flow:

~~~mermaid
flowchart TD
    A["Build and test artifact"] --> B["Update $LATEST"]
    B --> C["Enable SnapStart or configure PC"]
    C --> D["Publish new version"]
    D --> E["Wait until Active / PC READY"]
    E --> F["Smoke test version"]
    F --> G["Shift live alias"]
    G --> H["Monitor p95/p99, errors, spillover"]
    H --> I{"Release stable?"}
    I -->|"Yes"| J["Keep version"]
    I -->|"No"| K["Revert alias to previous version"]
~~~

With PC, allocate capacity on the new version or alias before shifting traffic if you want to avoid cold starts during release. With SnapStart, wait until the snapshot finishes and reaches `Active` before the alias receives traffic.

Keep older versions long enough to support rollbacks, while maintaining a cleanup process for obsolete versions. If a Java SnapStart version receives no invocations for 14 days, its snapshot may be deleted and the version turns `Inactive`; reverting to it requires handling snapshot regeneration.

## 29. Common Errors and Troubleshooting

| Symptom | Likely Cause | How to Check |
|---|---|---|
| Cold starts continue with PC enabled | Caller invokes `$LATEST` or wrong alias | Inspect integration ARN and qualifier |
| PC stuck in `IN_PROGRESS` | Allocation unfinished or quota/capacity constraints | Check `GetProvisionedConcurrencyConfig` and account quotas |
| Rising spillover | Peak concurrency exceeds PC | Compare utilization and `ConcurrentExecutions` |
| Rising throttles | Reserved/account concurrency or downstream limits | Check concurrency caps and dependencies |
| SnapStart not taking effect | Version unpublished or not `Active` | Check `OptimizationStatus` and `State` |
| SnapStart restore failure | Hook timeout or incompatible state | Inspect `restoreReport` and application logs |
| Duplicate IDs after restore | Unique values generated before snapshot | Regenerate in handler/`afterRestore` |
| Connection timeouts post-restore | Stale sockets or incompatible DNS caching | Reconnect and verify client/DNS behavior |
| Latency fails to improve | Handler/dependencies dominate duration | Trace end-to-end and analyze breakdown |
| High PC cost despite low traffic | Continuous provisioned capacity | Schedule scaling or lower min capacity |
| Java snapshot unavailable after idle | Version uninvoked for 14 days | Wait for version to become `Active` after Lambda recreates snapshot |

Once PC is exhausted, Lambda can serve excess load with standard concurrency; therefore, not every spillover causes throttling. However, spillover requests can hit cold starts. Distinguish latency degradation from throttling errors.

## 30. Java Frameworks and Runtime Optimization Choices

Java frameworks exhibit different startup profiles. Spring Boot typically involves substantial auto-configuration and class loading; Quarkus and Micronaut focus on reducing startup/memory via compile-time processing, though actual results depend on the application.

Optimization practices:

- Package only required dependencies.
- Strip unused auto-configurations.
- Use reusable clients and serializers.
- Reduce unnecessary reflection and classpath scanning.
- Re-measure memory and CPU after changing memory size.
- Size connection pools to concurrency.
- Avoid instantiating heavy objects on every handler invocation.
- Apply SnapStart or PC only after understanding the initialization profile.
- Measure JIT warm-up and frequently executed code paths.

With Java 25 and newer runtimes, AWS may apply different JVM defaults when using SnapStart or PC. Check runtime-specific documentation before overriding `JAVA_TOOL_OPTIONS`. Never copy legacy JVM flags to a new runtime without benchmarking.

## 31. Decision Tree for Choosing an Option

~~~mermaid
flowchart TD
    A["Cold start problem affecting SLO?"] -->|"No"| B["Use on-demand; optimize code as needed"]
    A -->|"Yes"| C["Managed Java runtime supports SnapStart?"]
    C -->|"No"| D["Optimize init or evaluate PC"]
    C -->|"Yes"| E["Does SnapStart meet p95/p99?"]
    E -->|"Yes"| F["Use SnapStart"]
    E -->|"No"| G["Need ultra-low startup and strict latency?"]
    G -->|"Yes"| H["Use Provisioned Concurrency"]
    G -->|"No"| I["Optimize init, dependencies, and handler"]
    H --> J["Size to peak concurrency and autoscaling"]
~~~

Practical rules of thumb:

- Choose on-demand if cold starts do not breach SLOs.
- Try SnapStart when Java initialization is a major latency source and workloads scale across many environments.
- Choose PC when pre-initialized environments with ultra-low startup latency are required.
- Use reserved concurrency to protect dependencies or cap scaling, not as a warm-start solution.
- If PC is expensive, test scheduled scaling or provision only the most critical APIs/routes.
- If neither SnapStart nor PC meets targets, revisit architecture, runtime, framework, downstream services, and SLOs.

## 32. Pre-Production Evaluation Checklist

**Workloads and SLOs**

1. Have end-to-end p50, p95, p99, and p99.9 been measured?
2. Are Init, Restore, handler, and downstream latencies separated?
3. Are steady, peak, burst, and idle traffic profiles documented?
4. Has concurrency been calculated from request rates and durations?
5. Has the subset of requests needing ultra-low latency been identified?

**Provisioned Concurrency**

6. Is PC attached to a published version or alias?
7. Do callers invoke the exact alias/version?
8. Was capacity `READY` before shifting traffic?
9. Is PC sized to actual peaks and buffers?
10. Are reserved concurrency and account quotas sufficient?
11. Can downstream databases/HTTP dependencies handle the concurrency?
12. Are spillover, utilization, and throttle metrics tracked?
13. Are scheduled scaling or target tracking configured where needed?
14. Have idle-period capacity costs been calculated?

**SnapStart and Java**

15. Is the Java runtime on the supported list?
16. Is SnapStart enabled for published versions?
17. Is the version `Active` with `OptimizationStatus` `On`?
18. Are unique IDs, secrets, or RNG states initialized during startup?
19. Are network connections re-established after restore?
20. Are temporary credentials and caches refreshed?
21. Do CRaC hooks hold strong references and finish within limits?
22. Has snapshot/restore been tested against real dependencies?
23. Are unused published versions cleaned up?
24. Is the `Inactive` state after 14 days without invocations handled?

**Release and Cost**

25. Have on-demand, SnapStart, and PC been benchmarked under identical conditions?
26. Have bursts, scale-out, and idle periods been tested?
27. Is there a step waiting for snapshot `Active` or PC `READY`?
28. Can the alias roll back to the previous version?
29. Are dashboards tracking latency, errors, restore/init, and concurrency?
30. Have costs been reviewed by traffic shape and Region?

## References

- [AWS Lambda: Configuring Provisioned Concurrency](https://docs.aws.amazon.com/lambda/latest/dg/provisioned-concurrency.html)
- [AWS Lambda: Understanding concurrency and scaling](https://docs.aws.amazon.com/lambda/latest/dg/lambda-concurrency.html)
- [AWS Lambda: Monitoring concurrency](https://docs.aws.amazon.com/lambda/latest/dg/monitoring-concurrency.html)
- [AWS Lambda: Improving startup performance with SnapStart](https://docs.aws.amazon.com/lambda/latest/dg/snapstart.html)
- [AWS Lambda: Activating and managing SnapStart](https://docs.aws.amazon.com/lambda/latest/dg/snapstart-activate.html)
- [AWS Lambda: Handling uniqueness with SnapStart](https://docs.aws.amazon.com/lambda/latest/dg/snapstart-uniqueness.html)
- [AWS Lambda: Runtime hooks for Java](https://docs.aws.amazon.com/lambda/latest/dg/snapstart-runtime-hooks-java.html)
- [AWS Lambda: Maximize SnapStart performance](https://docs.aws.amazon.com/lambda/latest/dg/snapstart-best-practices.html)
- [AWS Lambda Pricing](https://aws.amazon.com/lambda/pricing/)

## Conclusion

Both Provisioned Concurrency and SnapStart reduce AWS Lambda initialization latency, yet they serve different workloads. PC keeps a pool of initialized execution environments ready, fitting APIs with strict SLOs and concurrency needs that can be sized or autoscaled. SnapStart snapshots state after Init when publishing a version, enabling faster scale-out without maintaining a fixed pool of environments.

For Java, start by measuring latency percentiles, Init/Restore durations, and concurrency across traffic shapes. Try SnapStart when initialization is the bottleneck, verifying uniqueness, random state, connections, credentials, and CRaC hooks. Choose PC when ultra-low startup is essential and capacity costs are justified; configure it on aliases/versions, wait for `READY`, and monitor spillover. Reserved Concurrency remains useful for protecting dependencies, though it does not pre-warm environments. Base the final decision on benchmarks, SLOs, compatibility, and total workload cost.
