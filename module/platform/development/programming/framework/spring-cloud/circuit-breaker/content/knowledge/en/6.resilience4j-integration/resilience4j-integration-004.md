# Dedicated Per-ID Configuration with configure

In Spring Cloud CircuitBreaker, the factory creates a Circuit Breaker by ID. This ID represents a specific dependency or call flow, such as `catalog-read`, `payment-authorize`, or `recommendation-read`. When dependencies have different criticality, latency, and error-handling requirements, you can use the `configure` method to attach dedicated configurations per ID.

This approach allows an application to use the same Circuit Breaker API while applying tailored policies to each call. For instance, a catalog service may use a short timeout and cache fallback; a payment gateway must return a clear error if it cannot authorize a transaction; a recommendation service may accept omitting supplemental data. This lesson focuses on declaring per-ID configurations, binding IDs to calls, and verifying that the configuration has been applied.

## 1. Which configuration does an ID identify?

When calling `factory.create("catalog-read")`, the string `catalog-read` is the Circuit Breaker's ID. The factory uses the ID to look up the registered configuration and create or retrieve the corresponding Circuit Breaker. Therefore, the ID passed to `create(...)` must match the ID passed to `configure(...)` exactly.

An application can organize IDs by dependency and call purpose:

| ID | Dependency and call flow | Illustrative policy |
|---|---|---|
| `catalog-read` | Reading product catalog details | Short timeout, open breaker on errors or slowness, try cache when safe |
| `payment-authorize` | Requesting payment gateway to authorize a transaction | Time limit, fail fast when dependency degrades, never fabricate success |
| `recommendation-read` | Fetching recommended content | Can omit recommendations if the dependency is temporarily unavailable |

IDs should be stable and finite in number. Do not generate IDs per request, user ID, or product ID. If every request gets a new ID, the application can create a huge number of breakers with sparse statistical windows that are hard to observe and manage.

If two calls share the same ID, they share the same policy and breaker state. This only makes sense when they truly target the same dependency, have the same characteristics, and share the same failure handling. If one dependency has two call flows with different time budgets or business requirements, consider using two separate IDs.

## 2. Distinguishing configure and configureDefault

Spring Cloud CircuitBreaker with Resilience4j provides two primary configuration methods:

- `configure(..., "id")` registers configuration for one or more specific IDs.
- `configureDefault(...)` defines the default configuration used when an ID has no dedicated configuration.

For example, an application can set a default three-second timeout for calls, then configure `catalog-read` individually with a two-second timeout and its own observation window. Other IDs continue to use the default configuration.

```java
@Bean
Customizer<Resilience4JCircuitBreakerFactory> circuitBreakerCustomizer() {
    return factory -> {
        // Baseline configuration for IDs not specified individually.
        factory.configureDefault(id -> new Resilience4JConfigBuilder(id)
            .circuitBreakerConfig(CircuitBreakerConfig.ofDefaults())
            .timeLimiterConfig(TimeLimiterConfig.custom()
                .timeoutDuration(Duration.ofSeconds(3))
                .build())
            .build());

        // Dedicated configuration for the catalog-read call.
        factory.configure(builder -> builder
            .circuitBreakerConfig(CircuitBreakerConfig.custom()
                .slidingWindowType(SlidingWindowType.COUNT_BASED)
                .slidingWindowSize(20)
                .minimumNumberOfCalls(10)
                .failureRateThreshold(50)
                .build())
            .timeLimiterConfig(TimeLimiterConfig.custom()
                .timeoutDuration(Duration.ofSeconds(2))
                .build()),
            "catalog-read");
    };
}
```

In the example, `configureDefault` supplies the baseline policy. Calls with ID `catalog-read` receive their individually registered configuration. Other IDs without a dedicated configuration use the default. If multiple IDs are passed as the trailing arguments of `configure`, all of those IDs share the configuration declared in the lambda.

To keep code maintainable, group related configurations into a single `Customizer` bean or split them into beans by dependency group. Avoid declaring multiple beans that configure the same ID with conflicting policies, as it becomes difficult for readers to determine the final effective configuration.

## 3. Creating a Customizer for the Resilience4J factory

For synchronous calls, Spring Cloud CircuitBreaker provides `Resilience4JCircuitBreakerFactory`. You declare a `Customizer<Resilience4JCircuitBreakerFactory>` bean; Spring applies the customizer to the factory created by auto-configuration.

The example below creates dedicated configurations for two dependencies. Catalog data can be served from cache; payment is a mandatory operation and must fail fast if the payment gateway is unresponsive.

```java
import java.time.Duration;

import org.springframework.cloud.client.circuitbreaker.Customizer;
import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4JCircuitBreakerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig.SlidingWindowType;
import io.github.resilience4j.timelimiter.TimeLimiterConfig;

@Configuration
public class CircuitBreakerConfiguration {

    @Bean
    Customizer<Resilience4JCircuitBreakerFactory> perIdCircuitBreakerConfig() {
        return factory -> {
            factory.configure(builder -> builder
                .circuitBreakerConfig(CircuitBreakerConfig.custom()
                    .slidingWindowType(SlidingWindowType.COUNT_BASED)
                    .slidingWindowSize(20)
                    .minimumNumberOfCalls(10)
                    .failureRateThreshold(50)
                    .slowCallDurationThreshold(Duration.ofSeconds(2))
                    .slowCallRateThreshold(50)
                    .waitDurationInOpenState(Duration.ofSeconds(15))
                    .permittedNumberOfCallsInHalfOpenState(3)
                    .build())
                .timeLimiterConfig(TimeLimiterConfig.custom()
                    .timeoutDuration(Duration.ofSeconds(2))
                    .build()),
                "catalog-read");

            factory.configure(builder -> builder
                .circuitBreakerConfig(CircuitBreakerConfig.custom()
                    .slidingWindowType(SlidingWindowType.COUNT_BASED)
                    .slidingWindowSize(10)
                    .minimumNumberOfCalls(5)
                    .failureRateThreshold(40)
                    .waitDurationInOpenState(Duration.ofSeconds(30))
                    .permittedNumberOfCallsInHalfOpenState(2)
                    .build())
                .timeLimiterConfig(TimeLimiterConfig.custom()
                    .timeoutDuration(Duration.ofSeconds(5))
                    .build()),
                "payment-authorize");
        };
    }
}
```

The thresholds in the example are purely to illustrate per-ID configuration. For `catalog-read`, the window holds 20 calls and requires at least 10 samples before evaluating the failure rate; calls taking two seconds or more are considered slow. For `payment-authorize`, the configuration uses a different window and thresholds to demonstrate an independent policy. Actual values should be based on normal latency, traffic volume, SLOs, and the end-to-end request time budget.

Circuit Breaker and TimeLimiter configurations have distinct responsibilities:

- `CircuitBreakerConfig` controls the observation window, failure threshold, slow call threshold, and CLOSED/OPEN/HALF_OPEN state transitions.
- `TimeLimiterConfig` limits the wait time for calls integrated via the TimeLimiter mechanism.
- Timeouts do not replace Circuit Breakers: a timeout produces a failure outcome or ends waiting; the Circuit Breaker uses observed outcomes to decide whether to keep permitting calls.

For synchronous calls that can block, verify how the client handles interrupts or task cancellation. Timing out does not guarantee that all underlying I/O stops immediately. Timeout configuration must be paired with HTTP client timeouts and appropriate resource limits.

## 4. Using the right ID when calling a dependency

After registering the configuration, pass the matching ID to the factory where the call is made. For example:

```java
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;

@Service
public class ProductQueryService {

    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final ProductClient productClient;
    private final ProductCache productCache;

    public ProductQueryService(
            CircuitBreakerFactory<?, ?> circuitBreakerFactory,
            ProductClient productClient,
            ProductCache productCache) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.productClient = productClient;
        this.productCache = productCache;
    }

    public ProductDetails findDetails(String productId) {
        return circuitBreakerFactory.create("catalog-read").run(
            () -> productClient.fetchDetails(productId),
            cause -> productCache.findUsable(productId)
                .orElseThrow(() ->
                    new CatalogUnavailableException(productId, cause))
        );
    }
}
```

Here, `create("catalog-read")` matches the ID in `configure`. When the dependency fails or the Circuit Breaker rejects the call because it is OPEN, the fallback function attempts to fetch cached data. If the cache has no valid data, the fallback throws `CatalogUnavailableException` so the caller knows the service is unavailable.

You should not treat fallbacks as a way to turn every error into a success. If the client returns a business error such as product not found, classify that error separately and ensure it is not converted into stale or incorrect cached data. For payment operations, a fallback must never return a "paid" result without confirmation from the payment gateway.

An example of a mandatory call using its own ID:

```java
public PaymentResult authorize(PaymentCommand command) {
    return circuitBreakerFactory.create("payment-authorize").run(
        () -> paymentClient.authorize(command),
        cause -> {
            throw new PaymentUnavailableException(
                "Unable to authorize payment at this time", cause);
        }
    );
}
```

When the `payment-authorize` breaker is OPEN, new calls fail fast. The application returns an error matching the API contract, and the transaction state must be handled explicitly. If a transaction outcome is uncertain due to a timeout, the system should reconcile using a transaction ID or idempotency key before retrying; never assume a timeout means either failure or success.

## 5. Per-ID exception classification

One reason to configure per ID is that each dependency has a different set of errors that should count toward the failure rate. By default, Resilience4j treats exceptions thrown within a protected call as failures. This can be adjusted using `ignoreExceptions` or `recordExceptions` in `CircuitBreakerConfig`.

For example, a product-not-found error is a valid business outcome and should not cause the catalog breaker to open. You can add a policy to ignore that exception:

```java
CircuitBreakerConfig catalogConfig = CircuitBreakerConfig.custom()
    .slidingWindowSize(20)
    .minimumNumberOfCalls(10)
    .failureRateThreshold(50)
    .ignoreExceptions(ProductNotFoundException.class)
    .build();
```

When using `recordExceptions`, remember that exceptions not in the record list may be treated as successes unless they are also ignored or classified by another predicate. Therefore, only use a record list once you have thoroughly identified all error types that should count. If you want all exceptions to count as failures by default and only exclude specific business outcomes, `ignoreExceptions` is usually clearer.

Some classification guidelines:

| Error type | Typically appropriate statistical handling |
|---|---|
| Timeout, connection error, HTTP 5xx from dependency | Count as dependency failure |
| Slow call exceeding threshold | Count toward slow call rate |
| Business data not found | Ignore if it is a normal API outcome |
| Invalid request or unauthorized | Handle at validation/security layer; do not miscount as dependency incident |
| Programming bugs such as NullPointerException | Investigate as application bugs; do not mask with a generic fallback |

Do not ignore every exception just to keep the breaker from opening. If timeouts and connection errors are ignored, the breaker will fail to reflect the actual health of the dependency.

## 6. Configuring multiple IDs and organizing code

Multiple IDs can be passed into a single `configure` call when they genuinely share the same policy:

```java
factory.configure(builder -> builder
    .circuitBreakerConfig(CircuitBreakerConfig.custom()
        .slidingWindowSize(30)
        .minimumNumberOfCalls(10)
        .failureRateThreshold(50)
        .build()),
    "customer-read",
    "address-read");
```

In this example, `customer-read` and `address-read` share the same window, failure threshold, and default policy. If one dependency later requires a different timeout or threshold, split it into its own `configure` call. Do not group IDs simply because they are called from the same service; what matters is the dependency's characteristics and protection goals.

An easy-to-follow organization strategy:

- Use a constant or enum for IDs to avoid typos between configuration and call sites.
- Name IDs after the dependency and operation type, not after a controller or user.
- Give each ID one clear place where its policy is defined.
- Only share configurations across IDs when parameters are genuinely identical.
- Document the rationale for chosen timeouts, windows, and thresholds so the team can tune them based on metrics.

Example constant declarations:

```java
public final class CircuitBreakerIds {
    private CircuitBreakerIds() {}

    public static final String CATALOG_READ = "catalog-read";
    public static final String PAYMENT_AUTHORIZE = "payment-authorize";
    public static final String RECOMMENDATION_READ = "recommendation-read";
}
```

Then use `CircuitBreakerIds.CATALOG_READ` in both `configure` and `create`. This reduces the risk of a single-character mismatch preventing the dedicated configuration from being applied.

## 7. Per-ID configuration for reactive calls

If the application uses WebFlux and Reactor, use `ReactiveResilience4JCircuitBreakerFactory` to configure IDs for reactive flows. The `configure` structure is similar, but the factory and invocation API are reactive:

```java
@Bean
Customizer<ReactiveResilience4JCircuitBreakerFactory> reactiveCircuitBreakerCustomizer() {
    return factory -> factory.configure(builder -> builder
        .circuitBreakerConfig(CircuitBreakerConfig.custom()
            .slidingWindowSize(20)
            .minimumNumberOfCalls(10)
            .failureRateThreshold(50)
            .build())
        .timeLimiterConfig(TimeLimiterConfig.custom()
            .timeoutDuration(Duration.ofSeconds(2))
            .build()),
        "recommendation-read");
}
```

When using it:

```java
public Mono<Recommendation> findRecommendation(String customerId) {
    Mono<Recommendation> request = webClient.get()
        .uri("/recommendations/{customerId}", customerId)
        .retrieve()
        .bodyToMono(Recommendation.class);

    return reactiveCircuitBreakerFactory
        .create("recommendation-read")
        .run(request, cause -> recommendationCache.find(customerId));
}
```

The `recommendation-read` ID in `create` must match the ID configured on the reactive factory. The fallback also returns a `Mono`; do not call `block()` inside the pipeline as it can stall the event loop. Configurations for the reactive factory and the synchronous factory should be kept distinct to avoid mixing up APIs or assuming one customizer automatically applies to both.

## 8. Precedence between Java configure and application.yml

Spring Cloud CircuitBreaker supports configuring Resilience4j via Java Customizers or via properties in `application.yml`. Properties configuration takes precedence over Java Customizers. If an ID is declared in both places, values in properties can override the corresponding Java configuration.

Example per-instance configuration in YAML:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      catalog-read:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 15s
  timelimiter:
    instances:
      catalog-read:
        timeoutDuration: 2s
```

Use Java `configure` when you want to declare policies in code, need shared logic, or want to organize configuration via beans. Use properties when you want to adjust thresholds without modifying code and want to separate configuration by environment. Choose one clear management source per ID. If you intentionally use both, document which values are overridden and verify against the effective runtime configuration.

Do not assume Java configuration isn't working just because metrics differ from expectations. Check whether the same ID is declared in YAML or another profile, and inspect the loaded environment configuration.

## 9. Verifying per-ID configuration

After declaring customizers and using IDs, verify step by step:

1. Verify that the `Customizer` bean is instantiated by Spring; the application starts without factory creation errors.
2. Cross-check the ID string in `configure` against the ID string passed to `create`.
3. Verify no properties configuration with the same ID accidentally overrides Java.
4. Call the dependency successfully and confirm requests pass through the right client.
5. Simulate errors or timeouts in a test environment to confirm breaker metrics and states change according to thresholds.
6. Call again while the breaker is OPEN to confirm new calls fail fast and fallbacks or errors are returned as designed.
7. Wait for `waitDurationInOpenState` to elapse, verify HALF_OPEN allows the configured number of probe calls, and confirm the breaker recovers or re-opens based on outcomes.

A configuration test should not merely confirm the application starts up. Observe each ID individually. If `catalog-read` is OPEN, do not assume `payment-authorize` is also OPEN; each ID exists to isolate the state and metrics of its corresponding call flow.

## 10. Common errors when using configure

| Symptom | Possible cause | Resolution |
|---|---|---|
| Dedicated configuration has no effect | ID in `configure` differs from ID in `create` | Use shared constants and check spelling |
| Two dependencies open the breaker together | Accidentally sharing the same ID | Separate IDs if they need independent states |
| Breaker does not open despite repeated dependency errors | Exception is ignored or record config omits the needed error | Check exception classification and metrics |
| Breaker opens too quickly | Window is too small or threshold is too low for actual traffic | Re-evaluate `minimumNumberOfCalls`, window size, and threshold |
| Timeout occurs but background task keeps running | Client or task does not support cancellation on timeout | Configure HTTP client timeouts, limit resources, and verify cancellation support |
| Runtime values differ from Java Customizer | Properties or a profile is overriding the same ID | Inspect `application.yml`, `application-*.yml`, and loaded configuration |
| Reactive pipeline stalls | Blocking operation like `block()` inside fallback | Keep fallback non-blocking and return `Mono`/`Flux` |

## Conclusion

Use `configure` when a dependency or call flow needs a dedicated Circuit Breaker policy. Pick a stable ID, register the configuration on the right factory, and pass that exact ID to `create`. Use `configureDefault` as the baseline policy for IDs without dedicated configurations. Separate IDs according to dependency characteristics, classify exceptions properly, and check whether properties configuration overrides Java. That way, each call in a Spring Cloud application can have an observation window, failure threshold, timeout, and fallback behavior tailored to its requirements.
