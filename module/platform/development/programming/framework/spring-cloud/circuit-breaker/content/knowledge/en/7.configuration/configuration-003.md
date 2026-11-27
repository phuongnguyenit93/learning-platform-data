# Mapping factory.create(id, groupName) to Group Configuration

## Lesson objectives

In a Spring Cloud CircuitBreaker application, multiple calls may access the same dependent service. For example, order-service has operations for reading inventory, reserving stock, and releasing stock; all three operations call inventory-service, yet they may need different timeouts and circuit breaker thresholds.

The factory API provides two parameters to describe configuration boundaries:

- id identifies a specific operation or call, such as inventory-read.
- groupName identifies the service group the operation belongs to, such as inventory.

Understanding how these two values map to Resilience4j configuration lets you share policies across a group of operations while still allowing a single operation to have its own configuration. After this lesson, you can:

- Distinguish id and groupName in factory.create(id, groupName).
- Map configuration in priority order: operation, service group, and global default.
- Declare group configuration in resilience4j.circuitbreaker.configs and resilience4j.timelimiter.configs.
- Use per-instance configuration in instances to tune a specific operation.
- Understand that CircuitBreaker and TimeLimiter resolve configuration separately.
- Investigate why a call is using a group configuration or the default configuration.

## 1. Two parameters describing two configuration levels

Spring Cloud CircuitBreaker provides a factory to create circuit breakers by name. With Resilience4j, two common ways to call it are:

    CircuitBreaker breaker = factory.create("inventory-read");
    CircuitBreaker groupedBreaker = factory.create("inventory-read", "inventory");

In the second example:

- inventory-read is the id. It represents the operation or method being protected.
- inventory is the groupName. It represents the service group or operation group sharing a policy.

You can visualize the structure as follows:

    order-service
      |
      +-- inventory-read     --+
      +-- inventory-reserve   --+--> groupName: inventory
      +-- inventory-release  --+

Operations can belong to the same inventory group to share group configuration. However, id still distinguishes each circuit breaker. Each id can have its own CLOSED, OPEN, or HALF_OPEN state and metrics. groupName helps select configuration; it does not merge the states of multiple breakers into a single breaker.

Naming should be stable and reflect responsibility:

| Value | Example | Role |
| --- | --- | --- |
| id | inventory-read | Identifies a specific call for separate configuration and monitoring. |
| groupName | inventory | Groups calls targeting the same dependency or sharing an operational policy. |
| another id | inventory-reserve | A separate breaker that can share the inventory group policy. |
| another groupName | pricing | Configuration group for calls to pricing-service. |

Do not generate an id per request, user, or product code. If names change continuously, the application can create too many breakers and fragment statistical data. Name id after business operations with a stable lifecycle.

## 2. Configuration resolution order

Spring Cloud CircuitBreaker with Resilience4j supports three configuration levels, in descending order of precedence:

1. **Method or operation (id):** dedicated configuration for the specific operation.
2. **Service group (groupName):** shared configuration for a service group or operations of the same kind.
3. **Global default:** default configuration for breakers without a matching specific or group configuration.

This rule is applied independently to CircuitBreaker and TimeLimiter. Thus, an operation can take its circuit breaker configuration from the id level while taking its time limiter configuration from the groupName level if there is no id-specific time limiter configuration.

Examples:

| Factory call | CircuitBreaker configuration | TimeLimiter configuration |
| --- | --- | --- |
| create("backendA") | instances.backendA if present; otherwise uses the appropriate default. | instances.backendA if present; otherwise uses the appropriate default. |
| create("backendA", "groupA") | Prefers backendA config; if absent, checks groupA; finally falls back to default. | Prefers backendA config; if absent, checks groupA; finally falls back to default. |
| create("backendC", "groupC") when only TimeLimiter has group config | Uses default CircuitBreaker configuration. | Uses groupC TimeLimiter configuration. |

The last example shows that groupName is not required to have configuration for both components. If groupC is only declared in resilience4j.timelimiter.configs, TimeLimiter can use that group configuration while CircuitBreaker still uses the global default.

When calling create(id) without passing groupName, the factory uses id as the group name during resolution. If there is no matching configuration for id, it falls back to the global default. When you want to group multiple ids under one shared group, pass groupName explicitly.

## 3. Declaring group configuration in application.yml

Resilience4j separates shared configurations in configs from per-instance configurations in instances. You can declare an inventory group alongside the default group as follows:

    resilience4j:
      circuitbreaker:
        configs:
          default:
            registerHealthIndicator: true
            slidingWindowType: COUNT_BASED
            slidingWindowSize: 50
            minimumNumberOfCalls: 10
            failureRateThreshold: 50
          inventory:
            slidingWindowType: COUNT_BASED
            slidingWindowSize: 100
            minimumNumberOfCalls: 20
            failureRateThreshold: 40
            slowCallDurationThreshold: 800ms
            slowCallRateThreshold: 60
        instances:
          inventory-read:
            baseConfig: inventory
            minimumNumberOfCalls: 8

      timelimiter:
        configs:
          default:
            timeoutDuration: 5s
            cancelRunningFuture: true
          inventory:
            timeoutDuration: 2s
            cancelRunningFuture: true
        instances:
          inventory-read:
            baseConfig: inventory
            timeoutDuration: 700ms

Meaning of the configuration:

- configs.default is the global default policy.
- configs.inventory is the group policy for calls belonging to inventory.
- instances.inventory-read is the dedicated configuration for the inventory-read operation.
- baseConfig: inventory tells instance inventory-read to inherit the inventory group configuration, then apply the specific values declared on the instance.
- CircuitBreaker and TimeLimiter configurations are placed in separate branches; do not mix timeout into circuitbreaker.

With the configuration above, inventory-read inherits a 100-call window, failure rate threshold of 40, and 2-second timeout from the inventory group, then overrides minimumNumberOfCalls to 8 and timeout to 700 milliseconds. Another operation such as inventory-list without its own instance config will directly use the inventory group configuration when created with the matching groupName.

Group configuration is not mandatory for every service. If a group does not exist in configs, the factory continues using the global default for that component. If an instance does not exist in instances, the factory can resolve by groupName.

## 4. Mapping configuration with factory.create(id, groupName)

Suppose order-service needs to read inventory and reserve stock. Both operations belong to the inventory group but have distinct ids:

    import org.springframework.cloud.client.circuitbreaker.CircuitBreaker;
    import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
    import org.springframework.stereotype.Service;
    import org.springframework.web.client.RestClient;

    @Service
    public class InventoryGateway {

        private final RestClient inventoryClient;
        private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;

        public InventoryGateway(
                RestClient inventoryClient,
                CircuitBreakerFactory<?, ?> circuitBreakerFactory) {
            this.inventoryClient = inventoryClient;
            this.circuitBreakerFactory = circuitBreakerFactory;
        }

        public InventoryResponse read(String sku) {
            CircuitBreaker breaker =
                circuitBreakerFactory.create("inventory-read", "inventory");

            return breaker.run(
                () -> inventoryClient.get()
                    .uri("/inventory/{sku}", sku)
                    .retrieve()
                    .body(InventoryResponse.class),
                error -> InventoryResponse.unknown(sku)
            );
        }

        public ReservationResponse reserve(String sku) {
            CircuitBreaker breaker =
                circuitBreakerFactory.create("inventory-reserve", "inventory");

            return breaker.run(
                () -> inventoryClient.post()
                    .uri("/inventory/{sku}/reserve", sku)
                    .retrieve()
                    .body(ReservationResponse.class),
                error -> ReservationResponse.pending(sku)
            );
        }
    }

Both calls use groupName inventory so they can share the group configuration policy. However, the ids inventory-read and inventory-reserve differ, so breaker state and statistics are kept separate. This ensures that failures in a read operation do not necessarily trip the breaker for the reserve operation.

InventoryResponse.unknown and ReservationResponse.pending are application-defined methods. Fallbacks must accurately reflect business semantics. In particular, never return a successful reservation status if confirmation from the dependent service could not be obtained.

## 5. Using groupName with reactive calls

The reactive factory also supports create(id, groupName). With WebClient, a call returning Mono can use the same configuration mapping:

    import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreaker;
    import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreakerFactory;
    import org.springframework.stereotype.Service;
    import org.springframework.web.reactive.function.client.WebClient;
    import reactor.core.publisher.Mono;

    @Service
    public class ReactiveInventoryGateway {

        private final WebClient inventoryClient;
        private final ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory;

        public ReactiveInventoryGateway(
                WebClient inventoryClient,
                ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory) {
            this.inventoryClient = inventoryClient;
            this.circuitBreakerFactory = circuitBreakerFactory;
        }

        public Mono<InventoryResponse> read(String sku) {
            ReactiveCircuitBreaker breaker =
                circuitBreakerFactory.create("inventory-read", "inventory");

            Mono<InventoryResponse> request = inventoryClient.get()
                .uri("/inventory/{sku}", sku)
                .retrieve()
                .bodyToMono(InventoryResponse.class);

            return breaker.run(
                request,
                error -> Mono.just(InventoryResponse.unknown(sku))
            );
        }
    }

The reactive factory follows the same id and groupName resolution rules. The Publisher continues to be processed reactively; there is no need to convert Mono to Future just to select group configuration. When an application needs to protect a Flux, verify the abstraction and implementation in use; the common reactive API focuses on Mono, while Resilience4j Reactor operators can be used to decorate Flux.

GroupName does not change the return type, nor does it decide which fallback runs. The fallback is still supplied by the call or determined by the application's configuration/customizer.

## 6. Distinguishing CircuitBreaker and TimeLimiter configuration

CircuitBreaker and TimeLimiter serve different purposes:

- CircuitBreaker evaluates call outcomes, failure rates, and slow calls to transition between CLOSED, OPEN, and HALF_OPEN.
- TimeLimiter limits the execution time the application waits for supported calls.

Both can receive configuration by id, groupName, and default, but configuration data is declared in separate branches:

| Component | Group configuration | Instance configuration |
| --- | --- | --- |
| CircuitBreaker | resilience4j.circuitbreaker.configs.inventory | resilience4j.circuitbreaker.instances.inventory-read |
| TimeLimiter | resilience4j.timelimiter.configs.inventory | resilience4j.timelimiter.instances.inventory-read |

For example, if you only declare:

    resilience4j:
      circuitbreaker:
        configs:
          default:
            slidingWindowSize: 50
            failureRateThreshold: 50
      timelimiter:
        configs:
          default:
            timeoutDuration: 5s
          inventory:
            timeoutDuration: 2s

When calling factory.create("inventory-read", "inventory"), CircuitBreaker finds neither an inventory-read instance config nor an inventory group config in its registry, so it uses the default configuration. TimeLimiter finds the inventory group config, so it uses a 2-second timeout.

This is why you should not assume that passing groupName always changes both components identically. Check each configuration branch and its corresponding resolution result.

## 7. Combining properties configuration and Java Customizer

Spring Cloud CircuitBreaker allows configuration via application.yml and via Java Customizer. Properties have higher precedence than Customizer configuration. If a value in the configuration file differs from a value created in Java, check whether properties are overriding the result.

Example default configuration in Java:

    @Bean
    Customizer<Resilience4JCircuitBreakerFactory> defaultCustomizer() {
        return factory -> factory.configureDefault(id ->
            new Resilience4JConfigBuilder(id)
                .circuitBreakerConfig(CircuitBreakerConfig.ofDefaults())
                .timeLimiterConfig(
                    TimeLimiterConfig.custom()
                        .timeoutDuration(Duration.ofSeconds(4))
                        .build()
                )
                .build()
        );
    }

A default customizer is useful when you want to define a common policy in Java code. However, for groups with clear policies such as inventory and pricing, properties configuration is usually easier to read, compare across environments, and operate.

Do not declare the same policy in multiple places unnecessarily. When both properties and a Customizer exist, document clearly which is the authoritative source of configuration. Otherwise, maintainers might edit Java code and see no behavior change because properties configuration takes precedence.

## 8. Verifying mapping with concrete cases

Check case by case rather than looking only at configuration names:

| Case | id | groupName | Expected result |
| --- | --- | --- | --- |
| Instance config present | inventory-read | inventory | Uses inventory-read's own config; if the instance has baseConfig, inherits from the specified group/default. |
| No instance config, group present | inventory-list | inventory | Uses inventory group configuration. |
| Neither instance nor group config | pricing-quote | pricing | Uses global default for any component without matching config. |
| Only TimeLimiter has group config | inventory-read | inventory | CircuitBreaker may use global default while TimeLimiter uses the inventory group. |
| Different instance and group configs | inventory-read | inventory | Instance configuration takes precedence; group configuration does not automatically override the instance. |

When the application does not use the expected timeout, check in order:

1. Does the id passed to the factory match the key in instances?
2. Does groupName match the key in configs?
3. Is the configuration placed under the right circuitbreaker or timelimiter branch?
4. Does the instance have baseConfig pointing to another group?
5. Is a Java Customizer or properties from another environment affecting it?
6. Is TimeLimiter disabled at the global, group, or instance level?

You can enable configuration logging at an appropriate level and check breaker metrics after the application starts. Do not include sensitive data in logs merely to verify configuration names.

## 9. Hands-on exercise: creating two operations in the same group

Create two methods in the inventory gateway: reading inventory information and reserving stock. Use groupName inventory for both, but assign a separate id to each operation.

1. Declare configs.default with default sliding window and timeout.
2. Declare configs.inventory with a sliding window and timeout suitable for inventory-service.
3. Create a read method using factory.create("inventory-read", "inventory").
4. Create a reserve method using factory.create("inventory-reserve", "inventory").
5. Observe that both use the group policy when no per-instance configuration is present.
6. Add instances.inventory-read with baseConfig: inventory and change minimumNumberOfCalls.
7. Restart the application and verify read uses its own configuration while reserve continues using the group configuration.
8. Declare only TimeLimiter configuration for another test group to observe the case where CircuitBreaker and TimeLimiter receive different configuration levels.

The desired outcome is that you can explain that id is the name of the protected operation, groupName is the service configuration level, instance configuration takes precedence over group configuration, and the global default is used when no specific configuration is found. You should also verify CircuitBreaker and TimeLimiter configurations separately rather than assuming both components always receive the same configuration level.

## References

- Spring Cloud CircuitBreaker — Circuit Breaker Properties Configuration: https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-resilience4j/circuit-breaker-properties-configuration.html
- Spring Cloud CircuitBreaker — Resilience4J implementation: https://docs.spring.io/spring-cloud-circuitbreaker/docs/current/reference/html/spring-cloud-circuitbreaker-resilience4j.html
