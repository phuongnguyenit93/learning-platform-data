# Circuit Breaker and TimeLimiter Configurations Can Come from Different Groups

In Spring Cloud CircuitBreaker with Resilience4j integration, Circuit Breaker and TimeLimiter are two mechanisms with distinct goals. Circuit Breaker evaluates the health of a dependent service through call outcomes, failure rate, and slow call rate. TimeLimiter limits the wait duration of a single execution. Therefore, a service may need a Circuit Breaker policy from one configuration group and a TimeLimiter policy from a different group.

Resilience4j organizes configuration for the two mechanisms in two independent branches: **resilience4j.circuitbreaker** and **resilience4j.timelimiter**. Each branch can declare shared groups under **configs** and map individual instances under **instances**. By setting a separate **baseConfig** for the same instance ID in each branch, the application can pair a health policy with a timeout policy according to the service's needs.

## 1. Why separate configuration groups?

Circuit Breaker and TimeLimiter solve two separate problems:

- **Circuit Breaker** decides whether to continue sending calls to a dependent service. It collects outcomes in a sliding window, calculates the failure rate or slow call rate, and transitions between CLOSED, OPEN, and HALF_OPEN.
- **TimeLimiter** limits the wait time of a protected operation. It prevents calls from holding resources too long and lets the application switch to a fallback when the deadline is exceeded.

A Catalog service may need a short timeout because data must return quickly for the product page, while its Circuit Breaker threshold may need more samples to avoid opening the circuit on a few transient errors. Conversely, a payment service may need a longer timeout due to a complex verification flow, while the Circuit Breaker must open quickly when the failure rate rises.

If you force both mechanisms to share one configuration group, changing the timeout could trigger unwanted changes to the sliding window or failure threshold. Separating groups lets operations teams tune wait times independently of health evaluation policies.

## 2. Understanding configs and instances structure

Each Resilience4j configuration type has two main parts:

| Part | Meaning | Example |
|---|---|---|
| **configs** | Declares reusable policy groups | **resilience4j.circuitbreaker.configs.inventory-health** |
| **instances** | Declares policies bound to an actual identifier in the application | **resilience4j.circuitbreaker.instances.inventory** |
| **baseConfig** | Specifies which configuration group an instance inherits | **baseConfig: inventory-health** |

The same structure applies independently to TimeLimiter. Thus, an instance named **inventory** can inherit the **inventory-health** group in the Circuit Breaker branch and the **short-timeout** group in the TimeLimiter branch.

The instance name must match the ID that code passes to the factory. If code calls **create("inventory")**, the configuration under **instances.inventory** is the one bound to that call. Group names under **configs** can differ from instance IDs, as long as **baseConfig** references an existing group name declared in the same configuration branch.

## 3. YAML example: one instance, two different groups

Suppose an application has two dependent services: Inventory and Catalog. Inventory needs failure evaluation over a 30-second window and a two-second timeout. Catalog uses a count-based call window and a four-second timeout.

**application.yml** can be organized as follows:

~~~yaml
resilience4j:
  circuitbreaker:
    configs:
      inventory-health:
        slidingWindowType: TIME_BASED
        slidingWindowSize: 30
        minimumNumberOfCalls: 15
        failureRateThreshold: 40
        slowCallRateThreshold: 60
        slowCallDurationThreshold: 800ms
        waitDurationInOpenState: 20s
        permittedNumberOfCallsInHalfOpenState: 3

      catalog-health:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallRateThreshold: 70
        slowCallDurationThreshold: 1500ms
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 2

    instances:
      inventory:
        baseConfig: inventory-health

      catalog:
        baseConfig: catalog-health

  timelimiter:
    configs:
      short-timeout:
        timeoutDuration: 2s
        cancelRunningFuture: true

      extended-timeout:
        timeoutDuration: 4s
        cancelRunningFuture: true

    instances:
      inventory:
        baseConfig: short-timeout

      catalog:
        baseConfig: extended-timeout
~~~

The configuration above provides two independent mappings:

| Instance ID | Circuit Breaker group | TimeLimiter group |
|---|---|---|
| **inventory** | **inventory-health** | **short-timeout** |
| **catalog** | **catalog-health** | **extended-timeout** |

Thus, Inventory does not need one combined group containing both timeout and failure thresholds. The **inventory** instance picks its health group from the **circuitbreaker** branch and its wait timeout group from the **timelimiter** branch.

The values only illustrate the organization. For example, **slidingWindowSize: 30** with TIME_BASED means a 30-second window; with COUNT_BASED, the size is a number of outcomes. **minimumNumberOfCalls** bounds the minimum number of samples before evaluating rates. Failure and slow call thresholds should be based on each service's operational characteristics.

## 4. How the factory retrieves configuration by ID

When using Spring Cloud CircuitBreaker, the application creates a Circuit Breaker using the exact ID declared in properties. Blocking example:

~~~java
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;

@Service
class InventoryService {

    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final InventoryClient inventoryClient;

    InventoryService(
            CircuitBreakerFactory<?, ?> circuitBreakerFactory,
            InventoryClient inventoryClient) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.inventoryClient = inventoryClient;
    }

    Stock getStock(String sku) {
        return circuitBreakerFactory.create("inventory").run(
            () -> inventoryClient.getStock(sku),
            error -> Stock.unavailable(sku)
        );
    }
}
~~~

The ID **inventory** is used to look up the corresponding instance configuration. The Resilience4j integration uses the Circuit Breaker configuration bound to that ID and the corresponding TimeLimiter configuration if the operation executes through a TimeLimiter-supported path. In the YAML example, these two configurations inherit from two different groups.

If using **create("catalog")**, the factory looks up the **catalog** instances in both branches. Circuit Breaker and TimeLimiter group names do not need to be identical; what matters is that each **baseConfig** references an existing group in its corresponding branch.

For reactive applications, use the corresponding reactive factory and preserve the publisher:

~~~java
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreakerFactory;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
class ReactiveInventoryService {

    private final ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final ReactiveInventoryClient inventoryClient;

    ReactiveInventoryService(
            ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory,
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

A reactive fallback must return an appropriate publisher. Do not call **block()** to turn a reactive call into a blocking one merely to use a different factory.

## 5. Default configuration group and per-instance configuration

You can declare a **default** group in each branch to serve as the shared policy:

~~~yaml
resilience4j:
  circuitbreaker:
    configs:
      default:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 15s
        permittedNumberOfCallsInHalfOpenState: 3
      inventory-health:
        slidingWindowType: TIME_BASED
        slidingWindowSize: 30
        minimumNumberOfCalls: 10
        failureRateThreshold: 40
        waitDurationInOpenState: 20s
        permittedNumberOfCallsInHalfOpenState: 3
    instances:
      inventory:
        baseConfig: inventory-health
      catalog:
        baseConfig: default

  timelimiter:
    configs:
      default:
        timeoutDuration: 3s
        cancelRunningFuture: true
      short-timeout:
        timeoutDuration: 2s
    instances:
      inventory:
        baseConfig: short-timeout
      catalog:
        baseConfig: default
~~~

The Circuit Breaker branch has the **default** group and the **inventory-health** group. The TimeLimiter branch also has the **default** group and the **short-timeout** group. Inventory's configuration comes from **inventory-health** and **short-timeout**, while Catalog uses the default group in both branches.

In Resilience4j, a configuration group can inherit another configuration via **baseConfig** if supported by the version and configuration type in use. Make sure the parent group exists in the right configuration branch; a Circuit Breaker group cannot be referenced from the TimeLimiter branch or vice versa.

You can place additional properties directly on an instance to adjust a few specific values. When doing so, clearly distinguish which values come from the group and which are overridden on the instance. Avoid creating multiple inheritance layers if they make it difficult for operators to determine the final values.

## 6. Understanding factory's groupName

Spring Cloud CircuitBreaker has an overload that allows creating a Circuit Breaker with **create(id, groupName)**. This is useful when you want to select a configuration group at the factory level. However, the **groupName** parameter is a single group name in the factory call; it does not represent two distinct group names for Circuit Breaker and TimeLimiter.

When the requirement is for a single instance's Circuit Breaker and TimeLimiter to take policies from two different groups, the clearest approach is to declare **instances.<id>.baseConfig** independently under **resilience4j.circuitbreaker** and **resilience4j.timelimiter**, then create the Circuit Breaker by ID. That way, each configuration type can select its own group via Resilience4j's property structure.

Example:

~~~java
CircuitBreaker inventoryBreaker =
    circuitBreakerFactory.create("inventory");
~~~

With the ID **inventory**, Circuit Breaker and TimeLimiter instance configurations are mapped independently per YAML. There is no need to pass a single shared groupName when per-branch mapping is already declared explicitly.

If the application already uses **create(id, groupName)** for other configurations, verify how your Spring Cloud release train applies groupName and properties. Avoid mixing factory groupName with **baseConfig** in multiple places without verifying precedence order, as effective configuration can become hard to predict when multiple sources declare values.

## 7. Configuring via Java Customizer when policies must be built directly

Besides properties, you can configure Circuit Breaker and TimeLimiter in Java. This is useful when policies are constructed from code or need logic to choose parameters. The two configuration objects are still passed separately to the builder:

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
class InventoryCircuitBreakerConfiguration {

    @Bean
    Customizer<Resilience4JCircuitBreakerFactory> inventoryConfig() {
        CircuitBreakerConfig circuitBreakerConfig =
            CircuitBreakerConfig.custom()
                .slidingWindowType(
                    CircuitBreakerConfig.SlidingWindowType.TIME_BASED)
                .slidingWindowSize(30)
                .minimumNumberOfCalls(15)
                .failureRateThreshold(40)
                .waitDurationInOpenState(Duration.ofSeconds(20))
                .permittedNumberOfCallsInHalfOpenState(3)
                .build();

        TimeLimiterConfig timeLimiterConfig =
            TimeLimiterConfig.custom()
                .timeoutDuration(Duration.ofSeconds(2))
                .cancelRunningFuture(true)
                .build();

        return factory -> factory.configure(
            builder -> builder
                .circuitBreakerConfig(circuitBreakerConfig)
                .timeLimiterConfig(timeLimiterConfig),
            "inventory"
        );
    }
}
~~~

In the builder, **circuitBreakerConfig** receives the Circuit Breaker configuration and **timeLimiterConfig** receives the TimeLimiter configuration. They are two separate objects and can be changed independently. Java Customizer is an alternative configuration organization option to YAML; do not declare the same policy in both places without clarifying the precedence rules of the version in use.

## 8. What does TimeLimiter actually limit?

TimeLimiter limits the wait duration of an operation integrated with it. When the deadline expires, the operation is treated as a timeout and the error can be routed to the fallback. The **timeoutDuration** property sets the duration; **cancelRunningFuture** controls attempting to cancel the running Future when a timeout occurs.

Three limits must be distinguished:

| Limit | Where configured | Purpose |
|---|---|---|
| TimeLimiter | **resilience4j.timelimiter** | Limits the wait duration of the wrapped operation |
| HTTP connect/read timeout | HTTP client | Limits time to establish a connection and wait for data from the server |
| Database query/connection timeout | Driver or connection pool | Limits query execution or connection acquisition time |

TimeLimiter does not guarantee that every underlying I/O operation stops immediately when the deadline expires. Whether cancelling the Future succeeds depends on the client and task cancellability. Therefore, timeouts are still needed on the HTTP client or database driver. If TimeLimiter times out while the network request continues running in the background, resources can still be held.

Timeouts can also be recorded as failures by the Circuit Breaker, depending on the integration and exception configuration. When tuning the two groups, consider the relationship between **timeoutDuration**, **slowCallDurationThreshold**, and **slowCallRateThreshold**. If the timeout is always longer than the slow call threshold, slow calls can be recorded by the Circuit Breaker before TimeLimiter terminates the operation. If the timeout is too short relative to normal latency, the application may generate many timeout errors and open the circuit unnecessarily.

## 9. Verifying the effective configuration

When configuring two different groups, common mistakes are an instance referencing the wrong group name or the ID in code not matching the instance name. You can verify in this order:

1. Confirm code creates the Circuit Breaker with the exact ID, e.g., **inventory**.
2. Confirm **resilience4j.circuitbreaker.instances.inventory** exists.
3. Confirm the **baseConfig** of the Circuit Breaker instance points to a key in **resilience4j.circuitbreaker.configs**.
4. Confirm **resilience4j.timelimiter.instances.inventory** exists.
5. Confirm the **baseConfig** of the TimeLimiter instance points to a key in **resilience4j.timelimiter.configs**.
6. Check time units and data types of properties.
7. Start the application and inspect configuration logs or property binding errors if any.
8. Test a slow call to observe timeout behavior, then test a sufficiently long failure sequence to verify whether the Circuit Breaker transitions to OPEN per threshold.

Actuator and Micrometer can be used if the application has configured the appropriate endpoints and registry. Metrics on state, call counts, and timeouts help confirm actual behavior. Do not expose management endpoints publicly without access control mechanisms.

## 10. Common configuration mistakes

- **Using the same group name out of habit:** the two branches do not have to use the same group name. Map each instance using its own baseConfig.
- **Declaring a group in the wrong branch:** TimeLimiter must reference groups in **resilience4j.timelimiter.configs**, whereas Circuit Breaker references groups in **resilience4j.circuitbreaker.configs**.
- **ID in code does not match instance:** code creates **inventory** while YAML only declares **stock-service**, causing the intended configuration not to be applied.
- **Confusing groupName with baseConfig:** groupName in the factory overload is a call-level parameter; baseConfig is a group reference within each properties branch.
- **Configuring only TimeLimiter without client timeouts:** I/O operations may continue holding resources after the calling layer has timed out.
- **Timeout shorter than normal latency:** the application generates continuous timeout errors and the Circuit Breaker may open prematurely.
- **Declaring policy in multiple sources:** YAML and Java Customizer both setting the same parameter can make it hard to determine the effective value.
- **Not checking version differences:** property names, auto-configuration, and property merging behavior can differ across release trains; consult documentation for the exact Spring Cloud and Resilience4j versions.

## 11. Practical scenario

An ordering application calls Inventory to check stock. The operations team wants the Circuit Breaker to evaluate failure rates over a 30-second window, while the timeout must be two seconds because the UI needs a fast response.

The policies are separated as follows:

- The **inventory-health** group in Circuit Breaker sets a 30-second TIME_BASED window, minimum 15 calls, 40% failure rate threshold, 20-second OPEN duration, and three HALF_OPEN probes.
- The **short-timeout** group in TimeLimiter sets a two-second timeout and enables Future cancellation where possible.
- The **inventory** instance references **inventory-health** in the Circuit Breaker branch and **short-timeout** in the TimeLimiter branch.

When the application calls **create("inventory")**, the factory creates the Circuit Breaker bound to that ID. A call slower than two seconds can be terminated by TimeLimiter and routed to the fallback. The timeout outcome can be counted as a failure by the Circuit Breaker depending on integration configuration. Once enough samples accumulate and the failure rate exceeds 40%, the Circuit Breaker transitions to OPEN. While OPEN, new calls are rejected immediately and the fallback can return cached data or a business error.

When analyzing results, separate two questions: did an individual operation exceed two seconds, and does the aggregate of outcomes in the 30-second window meet the condition to open the circuit? The first question belongs to TimeLimiter; the second belongs to Circuit Breaker. Separating configuration groups lets you tune each goal without altering the other policy.

## Conclusion

Circuit Breaker and TimeLimiter can use two different configuration groups because Resilience4j manages them in two independent properties branches. Map **instances.<id>.baseConfig** independently under **resilience4j.circuitbreaker** and **resilience4j.timelimiter**, then create the Circuit Breaker using the matching ID in the application. This organization separates health evaluation policies from wait-time limits, makes per-service tuning easier, and simplifies verification during operations.
