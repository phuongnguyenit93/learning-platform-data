# Resilience4JCircuitBreakerFactory and Coordinated Components

Spring Cloud CircuitBreaker provides a unified API layer for applications to protect calls to dependent services. When Resilience4j is chosen as the implementation, the application typically receives a factory named **Resilience4JCircuitBreakerFactory** for blocking flows. The factory creates named Circuit Breakers, combining Resilience4j configuration with related mechanisms such as TimeLimiter, Bulkhead, executors, and event publishers.

Understanding the role of the factory and its coordinated components helps organize configuration per dependent service. Each service can have its own failure threshold, sliding window, wait duration, timeout, and concurrency limit. The factory is responsible for creating the protection object according to the configuration; the Circuit Breaker makes the runtime decision to permit or reject calls.

## 1. What is the factory and what components does it create?

**Resilience4JCircuitBreakerFactory** is the Circuit Breaker creation point in the Spring Cloud CircuitBreaker integration with Resilience4j for blocking calls. Spring Boot auto-configuration provides the factory when the corresponding starter is on the classpath and the application is configured appropriately.

Applications typically inject the factory into a service or gateway and call **create(id)** to obtain a named Circuit Breaker:

~~~java
import org.springframework.cloud.client.circuitbreaker.CircuitBreaker;
import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4JCircuitBreakerFactory;
import org.springframework.stereotype.Service;

@Service
class InventoryGateway {

    private final Resilience4JCircuitBreakerFactory circuitBreakerFactory;
    private final InventoryClient inventoryClient;

    InventoryGateway(
            Resilience4JCircuitBreakerFactory circuitBreakerFactory,
            InventoryClient inventoryClient) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.inventoryClient = inventoryClient;
    }

    Stock getStock(String sku) {
        CircuitBreaker breaker = circuitBreakerFactory.create("inventory");
        return breaker.run(
            () -> inventoryClient.getStock(sku),
            error -> Stock.unavailable(sku)
        );
    }
}
~~~

In the example, the name **inventory** is the configuration identifier for calls to the inventory service. When **create("inventory")** is called, the factory creates or retrieves the Circuit Breaker corresponding to that identifier. The Supplier contains the operation calling the dependent service; the fallback function handles errors propagated from the protected call, including cases where the Circuit Breaker rejects calls while OPEN.

You should not use the same name for dependent services that have different behaviors and protection policies. If Catalog and Inventory have different latencies, traffic levels, or criticality, assign separate identifiers such as **catalog** and **inventory**. This allows configuration, state, metrics, and logs to be tracked independently.

The factory is the component that creates the Circuit Breaker; it does not decide whether fallback data is valid from a business perspective. The application must still define the behavior when the dependent service is unavailable, such as reading from a cache, returning a retryable message, or throwing a business exception.

## 2. Core components in the integration

A protected call can coordinate multiple components. Each component addresses a specific aspect:

| Component | Role | Example configuration or API |
|---|---|---|
| Resilience4JCircuitBreakerFactory | Creates Circuit Breakers by identifier and application configuration | **create("inventory")** |
| CircuitBreaker | Tracks call outcomes and decides CLOSED, OPEN, or HALF_OPEN | **CircuitBreakerConfig** |
| CircuitBreakerRegistry | Manages Resilience4j Circuit Breakers and their corresponding configurations | Registry by instance name |
| TimeLimiter | Limits the wait time of an asynchronous operation or an operation integrated via an executor | **TimeLimiterConfig** |
| Bulkhead | Limits the number of concurrent calls or resources allocated to a service | **BulkheadConfig** or **ThreadPoolBulkheadConfig** |
| Executor or scheduler | Executes tasks and supports timeout mechanisms according to the integration model | Executor configured for the factory |
| Customizer | Adjusts default configuration, per-ID configuration, or attaches additional behavior | **Customizer<Resilience4JCircuitBreakerFactory>** |
| Event publisher and metrics | Emits state transition events, records call counts, and supports monitoring | State transition, Micrometer |

**CircuitBreaker** is the core of the circuit-breaking mechanism. It records outcomes over a sliding window, calculates the failure rate or slow call rate, and transitions states when configured conditions are met. When OPEN, it rejects new calls; when HALF_OPEN, it permits only the configured number of probes.

**TimeLimiter** addresses time limits. A call may be permitted by the Circuit Breaker yet still wait too long. TimeLimiter helps cap the wait time so the application does not hold resources indefinitely. Timeouts can be counted as failures or slow calls depending on how the Circuit Breaker is configured.

**Bulkhead** limits the level of concurrency a dependent service can consume. The Circuit Breaker reacts to recorded failure rates or latencies; the Bulkhead limits resources currently in use simultaneously. When a Bulkhead reaches capacity, calls can be rejected with a dedicated exception such as **BulkheadFullException**.

These components can be combined, but they do not replace one another. A system may need timeouts, a Circuit Breaker, and a Bulkhead together: timeouts limit wait duration, the Circuit Breaker prevents continued calls when a service shows signs of being unhealthy, and the Bulkhead prevents one service from exhausting resources meant for other parts of the system.

## 3. Default configuration using Customizer

Spring Cloud allows configuring the factory with a Spring bean of type **Customizer**. This approach is suitable when you want to apply a default policy to Circuit Breakers created within the application.

The following example configures the sliding window, minimum number of calls, failure threshold, and TimeLimiter timeout:

~~~java
import java.time.Duration;

import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import io.github.resilience4j.timelimiter.TimeLimiterConfig;
import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4JConfigBuilder;
import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4JCircuitBreakerFactory;
import org.springframework.cloud.client.circuitbreaker.Customizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class CircuitBreakerConfiguration {

    @Bean
    Customizer<Resilience4JCircuitBreakerFactory> defaultCircuitBreakerConfig() {
        CircuitBreakerConfig circuitBreakerConfig =
            CircuitBreakerConfig.custom()
                .slidingWindowType(
                    CircuitBreakerConfig.SlidingWindowType.COUNT_BASED)
                .slidingWindowSize(20)
                .minimumNumberOfCalls(10)
                .failureRateThreshold(50)
                .waitDurationInOpenState(Duration.ofSeconds(15))
                .permittedNumberOfCallsInHalfOpenState(3)
                .build();

        TimeLimiterConfig timeLimiterConfig =
            TimeLimiterConfig.custom()
                .timeoutDuration(Duration.ofSeconds(2))
                .build();

        return factory -> factory.configureDefault(id ->
            new Resilience4JConfigBuilder(id)
                .circuitBreakerConfig(circuitBreakerConfig)
                .timeLimiterConfig(timeLimiterConfig)
                .build()
        );
    }
}
~~~

**configureDefault** accepts a function that builds configuration from a Circuit Breaker identifier. This default configuration is used for IDs that do not have a matching custom configuration. The **id** argument enables creating configuration by name, and if needed, it can be used to select different policies.

In the example:

- The **COUNT_BASED** window has a size of 20 samples.
- Failure rate evaluation only begins once at least 10 calls have occurred.
- A 50% failure rate threshold is the condition for the Circuit Breaker to open.
- The duration spent in the OPEN state is 15 seconds.
- HALF_OPEN permits at most three probe calls.
- TimeLimiter caps the wait duration at two seconds.

These are illustrative values. They must be tuned according to the normal latency, traffic volume, criticality, and recovery characteristics of each dependent service. You should not apply a single timeout or failure threshold across all services if their characteristics differ.

## 4. Dedicated configuration per identifier

When dependent services have different characteristics, use **configure** to apply dedicated configuration to one or more IDs. Per-ID configuration allows Catalog to have a short timeout while Inventory may need a longer timeout due to different business operations.

~~~java
import java.time.Duration;

import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import io.github.resilience4j.timelimiter.TimeLimiterConfig;
import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4JConfigBuilder;
import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4JCircuitBreakerFactory;
import org.springframework.cloud.client.circuitbreaker.Customizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class NamedCircuitBreakerConfiguration {

    @Bean
    Customizer<Resilience4JCircuitBreakerFactory> inventoryConfiguration() {
        CircuitBreakerConfig inventoryConfig =
            CircuitBreakerConfig.custom()
                .slidingWindowType(
                    CircuitBreakerConfig.SlidingWindowType.TIME_BASED)
                .slidingWindowSize(30)
                .minimumNumberOfCalls(15)
                .failureRateThreshold(40)
                .waitDurationInOpenState(Duration.ofSeconds(20))
                .permittedNumberOfCallsInHalfOpenState(2)
                .build();

        TimeLimiterConfig inventoryTimeLimiter =
            TimeLimiterConfig.custom()
                .timeoutDuration(Duration.ofSeconds(3))
                .build();

        return factory -> factory.configure(
            builder -> builder
                .circuitBreakerConfig(inventoryConfig)
                .timeLimiterConfig(inventoryTimeLimiter),
            "inventory"
        );
    }
}
~~~

Here, **inventory** uses a 30-second time-based window, a minimum of 15 calls, a 40% failure threshold, a 20-second OPEN duration, two probes in HALF_OPEN, and a three-second timeout. When **create("inventory")** is called, the factory uses the configuration bound to that ID.

You can declare configuration for multiple IDs in a single **configure** call, but you should only group IDs when they genuinely require the same policy. If individual services have different SLAs, traffic volumes, or failure characteristics, keep their configurations separate so adjustments do not cause unintended side effects.

## 5. Configuration via application.yml

Resilience4j also supports per-instance configuration in **application.yml**. This approach decouples policy from Java code and makes it convenient to adjust per deployment environment.

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: TIME_BASED
        slidingWindowSize: 30
        minimumNumberOfCalls: 15
        failureRateThreshold: 40
        waitDurationInOpenState: 20s
        permittedNumberOfCallsInHalfOpenState: 2
      catalog:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 3

  timelimiter:
    instances:
      inventory:
        timeoutDuration: 3s
      catalog:
        timeoutDuration: 2s
~~~

The name under **instances** must match the ID the application passes to the factory, such as **create("inventory")**. If configuration is declared for the ID **inventory** while the code calls **create("stock-service")**, that per-instance configuration will not apply as expected.

When using both YAML properties and Java Customizers, you need to understand the precedence rules of the Spring Cloud and Resilience4j versions in use. Spring Cloud CircuitBreaker supports configuration via properties, and the documentation for your version specifies the precedence order between properties and Java Customizers. Avoid declaring the same parameter for the same ID in multiple places without a clear reason; when combining them is necessary, clearly establish which configuration layer is the final source of truth and verify the effective configuration at application startup.

## 6. Attaching additional behavior after Circuit Breaker creation

The factory provides **addCircuitBreakerCustomizer** to register custom operations on an already-created Circuit Breaker object. A common use case is registering a listener to observe state transitions.

~~~java
import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4JCircuitBreakerFactory;
import org.springframework.cloud.client.circuitbreaker.Customizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class CircuitBreakerEventConfiguration {

    @Bean
    Customizer<Resilience4JCircuitBreakerFactory> inventoryEventListener() {
        return factory -> factory.addCircuitBreakerCustomizer(
            circuitBreaker -> circuitBreaker.getEventPublisher()
                .onStateTransition(event ->
                    log.info(
                        "Circuit Breaker inventory state transition: {}",
                        event.getStateTransition()
                    )
                ),
            "inventory"
        );
    }
}
~~~

This customizer only attaches the listener to the Circuit Breaker with ID **inventory**. When the state transitions from CLOSED to OPEN, OPEN to HALF_OPEN, or HALF_OPEN back to CLOSED/OPEN, the application can record the event to assist operations.

You can register listeners for other events such as successful calls, failed calls, or rejected calls. However, you should not log excessively at the ERROR level for every rejected call, because during the OPEN period there may be a very large number of requests. Aggregated metrics are usually better suited for observing traffic and failure rates; logs should focus on state transitions or situations requiring investigation.

## 7. TimeLimiter and executor coordination with the factory

TimeLimiter sets a time limit on protected operations. In the Spring Cloud CircuitBreaker integration with Resilience4j, TimeLimiter configuration is passed into **Resilience4JConfigBuilder** alongside the Circuit Breaker configuration. When an application uses the blocking API and timeouts need to execute tasks on an executor, the factory can be configured with an appropriate executor via **configureExecutorService**.

Example of creating a dedicated executor for managed tasks:

~~~java
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;

import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4JCircuitBreakerFactory;
import org.springframework.cloud.client.circuitbreaker.Customizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class CircuitBreakerExecutorConfiguration {

    @Bean(destroyMethod = "shutdown")
    ScheduledExecutorService circuitBreakerExecutor() {
        return Executors.newScheduledThreadPool(8);
    }

    @Bean
    Customizer<Resilience4JCircuitBreakerFactory> configureCircuitBreakerExecutor(
            ScheduledExecutorService circuitBreakerExecutor) {
        return factory ->
            factory.configureExecutorService(circuitBreakerExecutor);
    }
}
~~~

The executor size must be chosen based on expected load and processing time. If an executor is shared across multiple tasks, a group of hanging or long-running calls can impact other tasks. You must monitor the queue, active thread count, and wait times.

A timeout does not guarantee that every underlying I/O operation stops immediately. The ability to cancel a task depends on the client, the executor, and how the operation is implemented. With blocking clients, configure timeouts at the corresponding HTTP/database layer so network operations truly have bounds. With reactive clients, prefer timeout and subscription cancellation mechanisms suited to the pipeline; do not block the event loop with synchronous calls.

## 8. How is Bulkhead coordinated?

Bulkhead creates resource limits per dependent service. In the Spring Cloud CircuitBreaker integration with Resilience4j, Bulkhead support can be enabled when the Resilience4j Bulkhead dependency is present on the classpath. The integration supports two common types:

- **SemaphoreBulkhead:** limits the number of concurrent calls using a semaphore; calls exceeding the limit are rejected.
- **FixedThreadPoolBulkhead:** isolates calls within a bounded thread pool and queue.

The Bulkhead type and how it is configured depend on the version and integration properties in use. Spring Cloud CircuitBreaker Resilience4j has the property **spring.cloud.circuitbreaker.resilience4j.enableSemaphoreDefaultBulkhead** to select SemaphoreBulkhead as the default type in the corresponding configuration. Before enabling it, consult the documentation for the release train in use and check its impact on blocking or reactive flows.

A Bulkhead is not a second Circuit Breaker. For example, the **inventory** Circuit Breaker might still be CLOSED while the Bulkhead has run out of concurrent slots. In that case, calls are rejected by the Bulkhead; it does not mean the service's failure rate has caused the Circuit Breaker to transition to OPEN. Exceptions and metrics for the two mechanisms should be recorded separately to accurately identify the root cause.

Concurrency limits should be chosen based on the dependent service's load capacity and the caller's resources. A limit that is too high may fail to protect the system; a limit that is too low may reject valid traffic even when the dependent service is healthy.

## 9. Blocking factory and reactive factory

**Resilience4JCircuitBreakerFactory** serves the blocking API. For reactive applications, Spring Cloud CircuitBreaker provides the corresponding factory **ReactiveResilience4JCircuitBreakerFactory**. Both integrate Resilience4j, but return Circuit Breaker types suited to their execution model.

| Aspect | Blocking | Reactive |
|---|---|---|
| Factory | **Resilience4JCircuitBreakerFactory** | **ReactiveResilience4JCircuitBreakerFactory** |
| Spring Cloud API | **CircuitBreakerFactory** | **ReactiveCircuitBreakerFactory** |
| Call result | Synchronous value or synchronous return type | **Mono** or **Flux** |
| Fallback | Function returning the corresponding value | Function returning the corresponding publisher |
| Note | Timeouts and executors must suit blocking operations | Do not call **block()** on a reactive pipeline |

Reactive example using the reactive factory and publisher:

~~~java
import org.springframework.cloud.circuitbreaker.resilience4j.ReactiveResilience4JCircuitBreakerFactory;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
class ReactiveInventoryGateway {

    private final ReactiveResilience4JCircuitBreakerFactory circuitBreakerFactory;
    private final ReactiveInventoryClient inventoryClient;

    ReactiveInventoryGateway(
            ReactiveResilience4JCircuitBreakerFactory circuitBreakerFactory,
            ReactiveInventoryClient inventoryClient) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.inventoryClient = inventoryClient;
    }

    Mono<Stock> getStock(String sku) {
        return circuitBreakerFactory.create("inventory").run(
            inventoryClient.getStock(sku),
            error -> Mono.just(Stock.unavailable(sku))
        );
    }
}
~~~

Do not inject the blocking factory and force a publisher into a synchronous value using **block()** inside WebFlux. Doing so can block reactive processing threads, reduce scalability, and cause bottlenecks under increasing load.

## 10. Monitoring state and protection effectiveness

Resilience4j provides events and metrics to observe Circuit Breaker operation. When integrated with Micrometer, the application can export metrics for successful calls, failed calls, rejected calls, current state, and state transitions. Exact metric names and tags depend on the version, registry, and integration configuration.

When monitoring, distinguish between the following signal groups:

| Signal | Interpretation |
|---|---|
| Successful and failed call counts | Outcomes of calls that were permitted to execute |
| Not-permitted call count | Calls rejected by the Circuit Breaker while OPEN or not granted permission in the corresponding state |
| Failure rate and slow call rate | Basis for determining why the Circuit Breaker opened |
| State transition count | Indicates whether the Circuit Breaker is stable or flapping between open and closed |
| Timeout | Indicates calls exceeded the configured wait duration |
| Bulkhead rejected | Indicates the concurrency limit or queue reached capacity |
| Fallback used | Indicates the application is serving requests using fallback behavior |

Circuit Breaker names should be kept consistent across code, properties, logs, and dashboards. For example, if a service calls **create("inventory")**, metrics and configuration should use the same identifier **inventory**. Do not use dynamic names per request or per user, as the number of instances and tags can grow uncontrollably.

State should be viewed alongside signals from the dependent service. Being OPEN for a short period can be proper protective behavior. If a Circuit Breaker repeatedly transitions CLOSED → OPEN → HALF_OPEN → OPEN, review the service health, thresholds, sliding window, timeout, probe count, and wait duration. If Bulkhead rejections increase while the Circuit Breaker remains CLOSED, inspect the concurrency limit and processing capacity.

## 11. Common mistakes when coordinating components

1. **Using a single ID for multiple services with different characteristics.** Configuration and metrics get mixed together, making it hard to tune policies per service.
2. **Configuring only the Circuit Breaker while ignoring timeouts.** Permitted calls can still wait too long and hold resources if the client layer lacks proper bounds.
3. **Treating BulkheadFullException as a Circuit Breaker open error.** The two mechanisms reject calls for different reasons; they must be categorized separately.
4. **Using an undersized or uncontrolled shared executor.** Timed-out tasks or slow calls can occupy threads and slow down other calls.
5. **Registering duplicate Customizers for the same ID.** Configuration becomes scattered across multiple beans, making the effective policy hard to determine.
6. **Defining the same parameter in both YAML and Java without understanding precedence order.** The actual runtime configuration may differ from the values a developer sees in a single file.
7. **Attaching listeners that generate excessive logs.** When the Circuit Breaker is OPEN, a high volume of rejections can cause logs to spike.
8. **Using the blocking factory in a reactive pipeline.** Blocking threads negates non-blocking benefits and can stall the event loop.

## 12. Practical scenario

An order application calls two dependent services: Inventory to check stock quantities and Catalog to fetch product information. Because the two services have different characteristics, the application creates two Circuit Breakers with separate identifiers.

- **inventory:** 30-second time-based window, minimum 15 calls, 40% failure threshold, 20-second OPEN duration, two HALF_OPEN probes, and a three-second timeout.
- **catalog:** 20-call count-based window, minimum 10 samples, 50% failure threshold, 10-second OPEN duration, three HALF_OPEN probes, and a two-second timeout.

The factory creates two instances by ID. The Circuit Breaker records outcomes and decides state. TimeLimiter bounds the operation's wait duration. Bulkhead limits the number of concurrent calls so Inventory or Catalog cannot exhaust the application's resources. A Customizer registers a state-transition listener; metrics are tagged by name so dashboards distinguish the two services.

When Inventory responds slowly and timeouts increase, the Circuit Breaker can transition to OPEN once enough samples are collected and the threshold is reached. New requests are rejected early and routed to fallback according to business policy. If the Bulkhead fills up before the Circuit Breaker opens, calls are rejected due to the concurrency limit; dashboards must reflect this as a distinct event. After the OPEN duration, a limited number of probes are sent to Inventory. If the service recovers, the Circuit Breaker returns to CLOSED; if results remain poor, it transitions back to OPEN.

Through this scenario, you should be able to identify:

- Which factory creates the instance for each service and which ID is used.
- Which configuration applies by default and which is dedicated per ID.
- Which component enforces timeouts, which limits concurrency, and which decides to open the circuit.
- Which events or metrics prove a call was rejected by the Circuit Breaker, timed out, or rejected by the Bulkhead.
- Which fallback is executed and whether the fallback data satisfies business requirements.

## Conclusion

**Resilience4JCircuitBreakerFactory** is the creation point for named Circuit Breakers in the Spring Cloud CircuitBreaker integration with Resilience4j for blocking flows. The factory coordinates Circuit Breaker, TimeLimiter, Bulkhead, and executor configuration; Customizers enable applying default policies, per-ID configurations, and event listeners. Reactive applications use the corresponding reactive factory. Consistent naming, clear separation of responsibilities across components, and dedicated metrics tracking will help protect each dependent service while preserving operability and policy tunability.
