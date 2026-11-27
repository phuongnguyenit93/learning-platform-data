# Checking Default Changes for TimeLimiter, Bulkhead, and Naming Rules

When upgrading Spring Cloud CircuitBreaker or Resilience4j, an application may continue to start up cleanly while its dependency protection behavior has changed. A configuration that omits TimeLimiter or Bulkhead settings may fall back on the provider's defaults. If defaults for wait durations, bulkhead type, or instance name resolution differ from what the development team assumes, requests may time out sooner, execute on a different thread pool, or fail to receive their intended custom configuration.

A safe migration must verify all three layers: actual library versions, effective configuration after Spring binds properties, and runtime behavior under load or failure. Do not merely diff YAML files before and after an upgrade. Confirm the exact IDs passed into the factory in code, the instance names in Resilience4j configuration, and group names if the application uses group-level configuration.

This lesson explains how to inspect TimeLimiter defaults, default Bulkhead selection, ID/group naming rules, precedence between properties and Java Customizers, and a verification workflow before releasing a new version to production.

## 1. Why Check Defaults During Migration?

Spring Cloud CircuitBreaker is an abstraction allowing applications to use a Circuit Breaker provider such as Resilience4j. The provider is responsible for constructing and composing the concrete policies. When upgrading a Spring Cloud release train, Spring Boot, or Resilience4j, configuration layers and defaults may shift.

Changes with clear runtime impact include:

- **TimeLimiter:** maximum wait time for a result, how Futures are canceled, and which execution paths TimeLimiter wraps.
- **Bulkhead:** whether calls use a semaphore on the calling thread or a dedicated thread pool and queue.
- **Instance name:** whether the ID passed to CircuitBreakerFactory matches the configuration keys for Circuit Breaker, TimeLimiter, and Bulkhead.
- **Group configuration:** whether a group name is passed to the factory and has corresponding configuration.
- **Java configuration and properties:** values from application.yml may take precedence over code-based customizers.
- **Instance lifecycle:** whether configuration changes apply at startup or require recreating instances/restarting the application.

An application can compile with zero errors yet suffer issues in production such as requests timing out after one second, thread-pool bulkheads filling up, MDC getting lost across thread switches, or inventory configuration not applying because code uses a different ID.

## 2. Building a Version Matrix Before Making Changes

Before editing configuration, record the actual resolved versions of all relevant components. The version declared in the build file is not always the final runtime version because BOMs, dependency management, or transitive dependencies can override it.

| Component | What to Record | Why |
| --- | --- | --- |
| Java | Build and runtime JDK | Verify bytecode and API compatibility |
| Spring Boot | Version from dependency management | Determines Actuator, Micrometer, and auto-configuration |
| Spring Cloud | Release train/BOM | Determines CircuitBreakerFactory APIs and provider integration |
| Spring Cloud CircuitBreaker | Resilience4j artifact version | Determines default provider, customizers, and property binding |
| Resilience4j | Versions of core, Spring Boot, and Micrometer modules | Determines TimeLimiter, Bulkhead, and state APIs |
| HTTP client | WebClient, RestClient, or other client | Determines connect/response timeouts and cancellation |

Use your build tool's dependency tree or dependency insight to find actual resolved versions. For example, with Maven:

~~~bash
mvn dependency:tree
~~~

You can filter output by relevant artifacts such as spring-cloud-starter-circuitbreaker-resilience4j, resilience4j-circuitbreaker, resilience4j-timelimiter, resilience4j-bulkhead, and resilience4j-spring-boot3.

With Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Do not upgrade a single Resilience4j module independently to a version different from the Spring Cloud BOM without checking the compatibility matrix. Resilience4j modules generally need to stay on the same version line to avoid API errors or inconsistent behavior.

## 3. Checking TimeLimiter Defaults

TimeLimiter bounds how long a task is allowed to run before the caller receives a timeout. In Resilience4j's default configuration, TimeLimiterConfig typically defaults to a one-second timeoutDuration with cancelRunningFuture enabled. Spring Cloud CircuitBreaker Resilience4j can use this default TimeLimiter configuration when the provider builds a Circuit Breaker.

However, you must verify whether TimeLimiter is actually applied on your application's specific execution path. Wrapping a synchronous supplier, a Future/CompletionStage, and a reactive publisher can differ across APIs and provider versions. Never infer that every HTTP request is completely canceled merely because TimeLimiter raised a timeout.

Concepts to keep distinct:

| Mechanism | What Does It Bound? |
| --- | --- |
| TimeLimiter | Wait time for completion of the wrapped task |
| HTTP connect timeout | Time to establish a connection |
| HTTP response/read timeout | Time waiting for a server response |
| Caller deadline | Overall end-to-end business time budget |
| Circuit Breaker slow-call threshold | Threshold for classifying a call as slow in statistics |
| Bulkhead | Concurrent call count or execution capacity allocated to a dependency |

TimeLimiter does not replace HTTP client timeouts. If the client is blocked on a socket or an I/O library that does not respond to interrupts/cancellation, underlying work may keep consuming resources after the caller receives a timeout. Configure timeouts on the HTTP client and verify actual client cancellation behavior.

### 3.1. Declaring TimeLimiter Explicitly

Do not leave production applications relying on default timeouts once a dependency's latency budget is known. Declare shared and per-instance configurations explicitly:

~~~yaml
resilience4j:
  timelimiter:
    configs:
      default:
        timeoutDuration: 2s
        cancelRunningFuture: true

    instances:
      inventory:
        baseConfig: default
        timeoutDuration: 800ms

      payment:
        baseConfig: default
        timeoutDuration: 1500ms
        cancelRunningFuture: true
~~~

In this example, inventory has an 800 ms timeout, payment has a 1,500 ms timeout, and remaining instances can inherit the default configuration. These numbers are illustrative; choose values based on SLOs, p95/p99 latency, and remaining overall request budget.

The TimeLimiter instance name must match the Circuit Breaker ID according to how the provider resolves configuration. When code creates Circuit Breaker ID inventory, verify that TimeLimiter resolves either the inventory instance or the group the factory was instructed to use.

### 3.2. Understanding cancelRunningFuture

cancelRunningFuture determines whether TimeLimiter requests cancellation of the Future upon timeout. Future cancellation generally relies on Future.cancel and may send an interrupt to the running thread.

That does not guarantee all underlying work stops immediately:

- The HTTP client may not abort an active socket or in-flight request when the thread is interrupted.
- The target server may already have received and continued processing the request.
- Work inside native libraries or non-interruptible I/O may continue holding resources.
- If the request mutated data, a caller-side timeout does not prove the server-side operation did not commit.

Therefore, timeouts must work together with HTTP client timeouts, reactive publisher cancellation where applicable, and idempotency for write operations that may be retried.

## 4. Checking the Resilience4j Provider's Default Bulkhead

Bulkhead limits the resources a single dependency can consume. In Spring Cloud CircuitBreaker Resilience4j, the default configuration typically uses FixedThreadPoolBulkhead when bulkhead integration is enabled. FixedThreadPoolBulkhead runs suppliers on a dedicated thread pool with a bounded queue.

You can select SemaphoreBulkhead as the default via property:

~~~yaml
spring:
  cloud:
    circuitbreaker:
      resilience4j:
        enableSemaphoreDefaultBulkhead: true
~~~

When this option is enabled, the provider uses a semaphore bulkhead by default instead of a fixed thread pool bulkhead. Check the exact Spring Cloud CircuitBreaker version in use and confirm the property binds properly, especially when migrating across multiple release trains.

The two strategies behave differently:

| Criterion | FixedThreadPoolBulkhead | SemaphoreBulkhead |
| --- | --- | --- |
| Execution thread | Thread from a dedicated pool | Current calling thread |
| Work queue | Has a bounded queue | No dedicated task queue |
| Limits | Thread count, queue capacity | Permit / concurrent call count |
| Execution model | Typically returns asynchronous result | Preserves caller's synchronous execution |
| ThreadLocal | Requires context propagation to the pool | Typically preserves context on the current thread |
| Rejection when full | Pool and queue reject additional tasks | Fails to acquire a permit within wait duration |
| Overhead | Thread and queue management | Lighter weight, fewer moving parts |

Switching the default from thread pool to semaphore or vice versa can affect latency, thread usage, context propagation, and how fallbacks execute. Do not treat the two bulkhead types as equivalent simply because both limit concurrency.

## 5. Configuring the Right Bulkhead Type

If using SemaphoreBulkhead, configure under resilience4j.bulkhead:

~~~yaml
spring:
  cloud:
    circuitbreaker:
      resilience4j:
        enableSemaphoreDefaultBulkhead: true

resilience4j:
  bulkhead:
    instances:
      inventory:
        maxConcurrentCalls: 10
        maxWaitDuration: 0
~~~

maxConcurrentCalls caps concurrent calls. maxWaitDuration set to 0 means do not wait for a permit when slots are exhausted; excess requests fail fast.

If using the default FixedThreadPoolBulkhead, configure under resilience4j.thread-pool-bulkhead:

~~~yaml
resilience4j:
  thread-pool-bulkhead:
    instances:
      inventory:
        coreThreadPoolSize: 4
        maxThreadPoolSize: 8
        queueCapacity: 16
        keepAliveDuration: 20ms
~~~

In this example, up to eight threads execute concurrently and the queue holds up to 16 waiting tasks. Size the pool and queue based on latency, CPU, connection limits, and the dependency's capacity.

Do not declare semaphore settings and assume they control FixedThreadPoolBulkhead. When the provider uses a thread pool, properties under resilience4j.bulkhead do not replace thread-pool-bulkhead settings. Conversely, when semaphore default is enabled, verify that semaphore instance settings bind correctly.

### 5.1. Verifying the Bulkhead Actually Works

Do not conclude from reading YAML alone. Verify at runtime against a mock dependency with controlled processing time:

1. Set a low concurrency limit, such as 2.
2. Make each call hold the resource long enough to observe overlap.
3. Send more concurrent requests than the limit.
4. Observe execution threads, queued tasks, and rejected requests.
5. Toggle semaphore default and repeat the same load.
6. Compare thread names, latency, rejections, and log context.

With a semaphore, the supplier usually executes on the calling thread. With a fixed thread pool, the supplier executes on a pool thread. This is a useful empirical signal to confirm bulkhead type, though you should combine it with metrics or runtime configuration inspection rather than relying solely on thread names.

## 6. ID and Group Name Rules

Spring Cloud CircuitBreaker uses an ID to identify each Circuit Breaker instance. For example:

~~~java
CircuitBreaker circuitBreaker =
    circuitBreakerFactory.create("inventory");
~~~

The ID inventory is the instance identifier. When using property-based configuration, this name must match the corresponding instance key:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50

  timelimiter:
    instances:
      inventory:
        timeoutDuration: 800ms
~~~

If the provider resolves Bulkhead instances by the same ID, the matching configuration must also use inventory under the active bulkhead section:

~~~yaml
resilience4j:
  thread-pool-bulkhead:
    instances:
      inventory:
        coreThreadPoolSize: 4
        maxThreadPoolSize: 8
        queueCapacity: 16
~~~

The practical rule is to keep IDs stable per dependency or protected operation. Avoid dynamically generating IDs containing user IDs, order IDs, request IDs, or tenant IDs. Dynamic IDs create unbounded numbers of instances, state machines, and meters.

### 6.1. Distinguishing ID from Group Name

Some API versions allow creating a Circuit Breaker with two arguments:

~~~java
CircuitBreaker circuitBreaker =
    circuitBreakerFactory.create("inventory", "critical-services");
~~~

In this call:

- inventory is the Circuit Breaker instance ID.
- critical-services is the group name used to select group configuration supported by the provider.

Do not substitute the group name for the ID. The ID identifies the specific instance; the group name supplies configuration context. How a provider resolves instance config vs. group config can differ across versions, so check the documentation for your release train and verify effective runtime settings.

A common pattern is using IDs for specific dependencies and groups for shared policy tiers:

~~~yaml
resilience4j:
  circuitbreaker:
    configs:
      default:
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
      critical-services:
        slidingWindowSize: 40
        minimumNumberOfCalls: 20
        failureRateThreshold: 40

    instances:
      inventory:
        baseConfig: default

  timelimiter:
    configs:
      default:
        timeoutDuration: 2s
      critical-services:
        timeoutDuration: 1s

    instances:
      inventory:
        baseConfig: default
~~~

When using group names, do not assume every property across Circuit Breaker, TimeLimiter, and Bulkhead resolves from the group using identical rules. Check your specific provider and version, then verify the actual effective values per instance.

## 7. Naming Rules When Using Resilience4j Annotations Directly

Distinguish the Spring Cloud CircuitBreaker API from Resilience4j's AOP annotations.

Annotation example:

~~~java
@CircuitBreaker(name = "inventory")
public InventoryResponse getInventory(String sku) {
    return inventoryClient.getInventory(sku);
}
~~~

Here, name is the instance name in the Resilience4j registry. It normally maps to:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        failureRateThreshold: 40
~~~

Direct annotations do not take a group name the way Spring Cloud factory's create(id, groupName) does. Do not apply factory group-naming rules to the annotation's name attribute.

If the same application uses both integration styles, document which call paths use the factory and which use annotations. Do not wrap the same call through both layers just "to be sure" configuration applies; doing so can create two separate Circuit Breakers with independent state and metrics.

## 8. Properties Configuration vs. Java Customizer

Spring Cloud CircuitBreaker Resilience4j allows configuration through application.yml as well as Java Customizers. When the same property is declared in both places, properties configuration generally takes precedence over Java configuration in Spring Cloud CircuitBreaker's property-based configuration mechanism.

Default customizer example:

~~~java
@Bean
Customizer<Resilience4JCircuitBreakerFactory> defaultCustomizer() {
    return factory -> factory.configureDefault(id ->
        new Resilience4JConfigBuilder(id)
            .timeLimiterConfig(
                TimeLimiterConfig.custom()
                    .timeoutDuration(Duration.ofSeconds(2))
                    .cancelRunningFuture(true)
                    .build()
            )
            .circuitBreakerConfig(
                CircuitBreakerConfig.custom()
                    .slidingWindowSize(20)
                    .failureRateThreshold(50)
                    .build()
            )
            .build()
    );
}
~~~

You can also customize per ID:

~~~java
@Bean
Customizer<Resilience4JCircuitBreakerFactory> inventoryCustomizer() {
    return factory -> factory.configure(
        builder -> builder
            .timeLimiterConfig(
                TimeLimiterConfig.custom()
                    .timeoutDuration(Duration.ofMillis(800))
                    .build()
            ),
        "inventory"
    );
}
~~~

If application.yml also declares a timeout for inventory, verify which value actually takes effect in your version. Avoid letting the same parameter appear in multiple sources without documenting which source holds precedence.

During migration, choose one primary configuration source per parameter group. You can use properties for environment-specific settings and customizers for shared programmatic configuration logic, provided you verify the application order and do not rely on accidental initialization order.

## 9. Coordinating TimeLimiter with Bulkhead

TimeLimiter and Bulkhead guard two different limits. When using FixedThreadPoolBulkhead, a task may wait in the queue before execution starts. Queue wait time, execution time, and how TimeLimiter wraps the task can all affect when the caller sees a timeout.

Questions to answer:

- Does the timeout clock start when the task is submitted or when execution begins?
- Can a queued task be canceled upon timeout?
- When the Future is canceled, does the running thread receive an interrupt?
- Does the HTTP client actually abort the request or release the connection?
- Does a timed-out task keep occupying the thread pool?
- Can the queue fill up even though callers have already timed out?

The answers depend on the integration path and version. Measure in staging using tasks with controllable wait and execution times.

With SemaphoreBulkhead, the supplier normally runs on the calling thread, so there is no bulkhead queue. However, the request can still block the calling thread until the HTTP client returns or times out. A semaphore never replaces a timeout.

Example configuration:

~~~yaml
resilience4j:
  timelimiter:
    instances:
      inventory:
        timeoutDuration: 800ms
        cancelRunningFuture: true

  bulkhead:
    instances:
      inventory:
        maxConcurrentCalls: 10
        maxWaitDuration: 0
~~~

If using thread pool bulkhead, move the instance configuration to resilience4j.thread-pool-bulkhead and verify the provider uses the intended strategy. Do not set timeouts so short that many tasks are constantly canceled while underlying work continues running, as that can silently exhaust the pool behind the caller's back.

## 10. Verifying Effective Configuration After Migration

Configuration in the repository is only the input. Verify the actual configuration after Spring binds properties and the provider creates instances.

A verification table might include:

| Property | Expected Configuration | Runtime Evidence |
| --- | --- | --- |
| Circuit Breaker ID | inventory | State/metrics tagged with instance inventory |
| TimeLimiter | 800 ms | Overdue tasks time out along the chosen execution path |
| cancelRunningFuture | true | Verify Future cancellation and worker impact |
| Bulkhead type | Semaphore or FixedThreadPool | Observe threads, queue, and rejections |
| Bulkhead limit | 10 permits or specific pool/queue | Concurrent load stays within bounds |
| Group name | critical-services | Group configuration applies per provider |
| Failure threshold | 50% or custom value | Inject controlled errors and observe state |
| Slow-call threshold | Per latency budget | Slow calls recorded accurately |
| Fallback | Defined degraded response | Verify it runs only at the intended boundary |

Do not expose sensitive configuration endpoints publicly just for verification. Use startup logs, secured Actuator endpoints, metrics, integration tests, or direct bean inspection in staging.

## 11. Step-by-Step Migration Process

You can follow this sequence when upgrading Spring Cloud CircuitBreaker or Resilience4j:

1. **Capture a baseline:** record the current version's dependency tree, timeouts, bulkhead type, thread usage, rejections, latency, and fallback counts.
2. **Verify the release train:** confirm Spring Boot, Spring Cloud, and Resilience4j compatibility.
3. **Inventory instance IDs:** reconcile every create(id) call, annotation name, and YAML key.
4. **Inventory group names:** check create(id, groupName) calls and corresponding group configurations.
5. **Declare timeouts explicitly:** never leave critical timeouts dependent on defaults.
6. **Choose Bulkhead explicitly:** confirm semaphore vs. fixed thread pool and configure the matching prefix.
7. **Check configuration precedence:** verify whether properties or Java Customizers win.
8. **Test timeouts:** test fast tasks, slow tasks, hung tasks, and canceled tasks.
9. **Test bulkheads:** drive load past the limit and observe queues, permits, threads, and rejections.
10. **Test naming:** verify the expected instance and group are selected.
11. **Test fallbacks and context:** verify MDC, SecurityContext, and trace context if threads switch.
12. **Compare against baseline:** compare latency, throughput, timeout counts, and resource usage.
13. **Roll out gradually:** canary or rolling deployment, monitor metrics, and keep rollback ready.

Change one group of defaults at a time. Changing timeouts, bulkhead type, and ID naming simultaneously makes it hard to tell which factor caused any behavioral shift.

## 12. Minimum Test Scenario Suite

| Scenario | How to Trigger | Outcome to Verify |
| --- | --- | --- |
| Fast call | Dependency responds in 100 ms | Does not trigger TimeLimiter timeout |
| Slow call | Dependency responds past configured timeout | Caller times out within the expected limit |
| Future timeout | Task runs on an observable executor | Check cancellation and whether task keeps running |
| Bulkhead full | Send more requests than concurrency limit | Excess requests are rejected or wait per policy |
| Thread pool queue full | Keep workers busy and fill the queue | Rejections trigger on time; queue does not grow unbounded |
| Semaphore default | Enable enableSemaphoreDefaultBulkhead | Supplier runs on calling thread and permits are enforced |
| Fixed thread pool default | Disable semaphore option or use release default | Supplier runs on dedicated pool with bounded queue |
| Mismatched ID | Code uses inventory while YAML defines inventory-api | Detect that instance configuration is not applied as intended |
| Group config | Call create with ID and group name | Confirm expected instance/group config per version |
| Properties vs. Customizer | Declare the same setting in both places | Determine which source takes higher precedence |
| Multiple replicas | Run multiple application instances | Evaluate per-replica local state, pools, and metrics |

Timeout tests should use controllable clocks and test fixtures when possible. Avoid long sleeps or razor-thin timing margins that cause flaky results. For concurrency tests, count active in-flight calls using thread-safe counters in the test dependency.

## 13. Common Migration Issues

| Symptom | Likely Cause | Fix |
| --- | --- | --- |
| Requests time out after ~1 second | TimeLimiter is using its default value | Declare timeoutDuration explicitly per dependency |
| Caller times out while task still holds thread | Future cancellation cannot stop underlying I/O | Configure HTTP client timeouts and verify cancellation |
| Lost MDC or SecurityContext after upgrade | Bulkhead switched to a thread pool or execution switches threads | Check bulkhead type and configure context propagation |
| Thread pool exhausts despite caller timeouts | Timed-out tasks keep running | Check cancellation, queue, and HTTP-layer timeouts |
| Semaphore config has no effect | Provider is still using FixedThreadPoolBulkhead | Check enableSemaphoreDefaultBulkhead and config prefix |
| Sharp rise in Bulkhead rejections | Concurrency or queue limits lower than real traffic | Measure concurrency and tune within resource budgets |
| YAML configuration is ignored | Code ID differs from instance name or wrong prefix | Align IDs and configuration per provider |
| Group config has no effect | Group name not passed or group mistaken for ID | Verify create(id, groupName) and version resolution rules |
| Customizer does not override YAML | Properties have higher precedence | Pick one authoritative config source and check effective values |
| Metrics show abnormally many instances | IDs generated dynamically per request | Use stable dependency- or operation-level IDs |

## 14. Pre-Release Checklist

Before deploying the new version, confirm:

- Spring Boot, Spring Cloud release train, and Resilience4j are compatible.
- The dependency tree shows the intended runtime versions.
- TimeLimiter timeouts are declared explicitly for critical dependencies.
- The HTTP client has its own connect/response timeouts.
- cancelRunningFuture behavior is understood and cancellation is tested.
- Bulkhead type is explicitly chosen rather than assumed from defaults.
- Configuration prefixes match the active bulkhead type.
- Factory IDs match configured instance names.
- Group names are passed correctly with valid configurations.
- Annotation names are kept distinct from factory IDs/group names.
- Properties and Java Customizers do not override each other unexpectedly.
- Thread pools, queues, semaphores, and rejections are measured under load.
- Fallbacks, context propagation, and metrics are verified.
- A baseline, canary, rollback plan, and monitoring owner are in place.

When migrating Spring Cloud CircuitBreaker, TimeLimiter, Bulkhead, and naming rules must be verified as part of runtime behavior. Explicit timeouts and bulkhead types reduce your reliance on version defaults. Stable IDs, properly understood group names, and verified effective configuration prevent an application from silently running with a policy different from what the team intended. Testing timeouts, cancellation, saturation, and naming before release lowers the risk of unintended changes to dependency protection after an upgrade.

## References

- [Spring Cloud CircuitBreaker reference](https://docs.spring.io/spring-cloud-circuitbreaker/reference/)
- [Spring Cloud CircuitBreaker — Resilience4j](https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-resilience4j.html)
- [Resilience4j TimeLimiter](https://resilience4j.readme.io/docs/timeout)
- [Resilience4j Bulkhead](https://resilience4j.readme.io/docs/bulkhead)
- [Resilience4j CircuitBreaker](https://resilience4j.readme.io/docs/circuitbreaker)
