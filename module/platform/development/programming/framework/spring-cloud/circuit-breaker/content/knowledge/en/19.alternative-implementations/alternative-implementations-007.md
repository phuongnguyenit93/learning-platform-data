# FrameworkRetryCircuitBreakerFactory and Reactive Application Limitations

Spring Cloud CircuitBreaker has multiple implementations behind the same abstraction. One of them is **Framework Retry**, an implementation based on the native retry capabilities introduced in Spring Framework 7. This implementation's factory is named FrameworkRetryCircuitBreakerFactory and uses Spring Framework's RetryTemplate and RetryPolicy to perform retries combined with Circuit Breaker state.

An important point when selecting an implementation is that Framework Retry only supports synchronous calls. It does not provide a reactive Circuit Breaker for Mono or Flux. If your application uses Spring WebFlux, WebClient, and Reactor, choose an implementation with reactive support such as Resilience4j. Wrapping a Mono with the synchronous API does not protect the point where the publisher actually executes and can cause the Circuit Breaker to record inaccurate outcomes.

## 1. What Is Framework Retry?

Spring Framework 7 adds native retry capabilities within its resilience features. Spring Cloud CircuitBreaker provides a Circuit Breaker implementation built on Spring Framework's RetryTemplate and RetryPolicy.

Retry and Circuit Breaker solve two related but distinct problems:

- **Retry** reattempts an operation when a permitted error occurs, according to a policy governing attempt count, duration, or exception types.
- **Circuit Breaker** tracks call state and blocks new calls when a complete execution fails according to the implementation's rules.

FrameworkRetryCircuitBreakerFactory combines these two parts. It creates a Circuit Breaker by ID and applies the retry configuration along with state transition durations. The implementation is modeled after Spring Retry's CircuitBreakerRetryPolicy: the Circuit Breaker opens after a complete logical execution fails—meaning the inner retry attempts have been exhausted.

This differs from how Resilience4j is typically configured with a sliding window and failureRateThreshold. Framework Retry does not wait for an error rate across N calls before opening the circuit. A single logical execution failing after exhausting the retry policy can open the circuit right away.

## 2. Version Requirements and Starter

Framework Retry Circuit Breaker relies on Spring Framework 7's retry API. Therefore, the application must use compatible versions of Spring Boot, Spring Framework, and Spring Cloud. Manage versions via the Spring Cloud BOM instead of picking a standalone starter version manually.

Add the following starter in Maven:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-circuitbreaker-framework-retry</artifactId>
</dependency>
~~~

With Gradle:

~~~groovy
implementation 'org.springframework.cloud:spring-cloud-starter-circuitbreaker-framework-retry'
~~~

The starter provides the CircuitBreakerFactory implementation based on Framework Retry. When the application has the appropriate starter on the classpath, Spring Boot auto-configuration creates the factory so services can inject it.

Do not confuse this starter with the legacy Spring Retry starter:

| Implementation | Retry Foundation | Factory | Reactive Support |
|---|---|---|---|
| Framework Retry | Spring Framework 7 RetryTemplate and RetryPolicy | FrameworkRetryCircuitBreakerFactory | No |
| Spring Retry | Spring Retry and CircuitBreakerRetryPolicy | SpringRetryCircuitBreakerFactory | No corresponding reactive factory |
| Resilience4j | Resilience4j Retry/CircuitBreaker and related modules | Resilience4JCircuitBreakerFactory; reactive uses ReactiveResilience4JCircuitBreakerFactory | Yes, via the Reactor Resilience4j starter |

Check your project's Spring Cloud release train and Spring Boot version before adding the starter. If the project is not yet on Spring Framework 7, you cannot simply add the Framework Retry starter and expect the new retry APIs to appear.

## 3. Creating Default Configuration with FrameworkRetryCircuitBreakerFactory

You can use a Customizer bean to configure common defaults for all Circuit Breakers created from the factory. FrameworkRetryConfigBuilder accepts the ID and lets you set RetryPolicy, openTimeout, and resetTimeout.

Default configuration example:

~~~java
@Bean
public Customizer<FrameworkRetryCircuitBreakerFactory> defaultCustomizer() {
    return factory -> factory.configureDefault(id ->
            new FrameworkRetryConfigBuilder(id)
                    .retryPolicy(RetryPolicy.withMaxRetries(3))
                    .openTimeout(Duration.ofSeconds(20))
                    .resetTimeout(Duration.ofSeconds(5))
                    .build()
    );
}
~~~

Meaning:

- configureDefault applies default configuration to Circuit Breakers that do not have a per-ID configuration.
- RetryPolicy.withMaxRetries(3) allows the retry policy up to three retries according to RetryPolicy's counting rules.
- openTimeout(Duration.ofSeconds(20)) sets how long the circuit stays OPEN before allowing one probe call in HALF_OPEN.
- resetTimeout(Duration.ofSeconds(5)) sets the reset period according to the implementation's behavior; if no new errors occur during this window, the state can automatically return to CLOSED.

These values are examples only. Retry count, open duration, and reset duration should be chosen based on dependency latency, request deadlines, and the business impact of failed calls.

## 4. Per-ID Configuration

The factory lets you configure a specific Circuit Breaker by ID. For example, a slow dependency may need a longer OPEN duration and fewer retries:

~~~java
@Bean
public Customizer<FrameworkRetryCircuitBreakerFactory> slowCustomizer() {
    return factory -> factory.configure(
            builder -> builder
                    .retryPolicy(RetryPolicy.withMaxRetries(1))
                    .openTimeout(Duration.ofSeconds(30))
                    .resetTimeout(Duration.ofSeconds(10))
                    .build(),
            "slow"
    );
}
~~~

When code creates a Circuit Breaker with ID slow, this specific configuration is used. Other IDs continue to receive the default configuration unless configured individually.

You can declare multiple configurations within a single Customizer:

~~~java
@Bean
public Customizer<FrameworkRetryCircuitBreakerFactory> specificCustomizer() {
    return factory -> {
        factory.configure(
                builder -> builder
                        .retryPolicy(RetryPolicy.withMaxRetries(1))
                        .openTimeout(Duration.ofSeconds(30))
                        .resetTimeout(Duration.ofSeconds(10))
                        .build(),
                "slow"
        );

        factory.configure(
                builder -> builder
                        .retryPolicy(RetryPolicy.withMaxRetries(5))
                        .openTimeout(Duration.ofMinutes(2))
                        .resetTimeout(Duration.ofSeconds(15))
                        .build(),
                "critical"
        );
    };
}
~~~

The ID in configure must match the ID passed to factory.create. Name IDs after dependencies or operation groups sharing operational traits, such as inventory, payment, or customer-profile. Do not generate a new ID per request, as that makes Circuit Breaker configuration and state unmanageable.

## 5. Composable RetryPolicy Options

Spring Framework 7 provides retry policies usable within Framework Retry Circuit Breaker:

| RetryPolicy | Meaning |
|---|---|
| withMaxRetries(int) | Caps the number of retries |
| withMaxDuration(Duration) | Retries within a maximum time window |
| withBackoff(Duration, double) | Increases wait time between attempts by a backoff multiplier |
| forExceptions(Class<?>...) | Retries only the specified exception types |
| and(...) | Combines policy conditions with AND |
| or(...) | Combines policy conditions with OR |

For example, retry only IOException and TimeoutException while bounding both retry count and total duration:

~~~java
@Bean
public Customizer<FrameworkRetryCircuitBreakerFactory> retryPolicyCustomizer() {
    return factory -> factory.configureDefault(id ->
            new FrameworkRetryConfigBuilder(id)
                    .retryPolicy(
                            RetryPolicy.withMaxRetries(3)
                                    .and(RetryPolicy.withMaxDuration(
                                            Duration.ofSeconds(5)))
                                    .forExceptions(
                                            IOException.class,
                                            TimeoutException.class)
                    )
                    .openTimeout(Duration.ofSeconds(20))
                    .resetTimeout(Duration.ofSeconds(5))
                    .build()
    );
}
~~~

This example illustrates bounding both retry count and retry duration while filtering exceptions. Verify policy composition against the API of the Spring Framework version you use to ensure conditions are evaluated as intended.

You can use backoff to avoid sending rapid back-to-back requests:

~~~java
RetryPolicy retryPolicy = RetryPolicy.withMaxRetries(3)
        .withBackoff(Duration.ofMillis(100), 2.0);
~~~

Increasing wait intervals reduce pressure on a recovering dependency. In systems with multiple callers, consider jitter if supported by the library or an additional coordination layer so callers do not retry at the exact same instant.

Retry only errors likely to be transient. Do not retry authentication errors, invalid input, or unrecoverable business errors. For operations with side effects such as creating an order or debiting funds, require an idempotency key or duplicate-processing guard.

## 6. How Framework Retry Circuit Breaker Transitions States

Framework Retry Circuit Breaker has three primary states:

| State | Behavior |
|---|---|
| CLOSED | Permits calls through and retries per RetryPolicy. If a logical execution fails after exhausting retries, the Circuit Breaker opens |
| OPEN | Rejects new calls fast and routes to fallback if declared; does not run retries for rejected calls |
| HALF_OPEN | Permits a single probe call to test the dependency. If it succeeds, the circuit closes; if it fails, the circuit opens again |

State flow:

~~~mermaid
stateDiagram-v2
    [*] --> CLOSED
    CLOSED --> OPEN: Execution fails after exhausting retries
    OPEN --> HALF_OPEN: openTimeout elapsed
    HALF_OPEN --> CLOSED: Probe call succeeds
    HALF_OPEN --> OPEN: Probe call fails
~~~

Unlike implementations that allow multiple probe calls in HALF_OPEN, Framework Retry Circuit Breaker allows a single probe call to test recovery. Therefore, do not configure or expect a batch of concurrent requests to probe the dependency simultaneously in this state.

When the circuit is OPEN, calls are rejected immediately without running RetryPolicy. The fallback can be invoked to return an alternative result. Once openTimeout elapses, one call is allowed through to probe. If the probe succeeds, the circuit returns to CLOSED; if it fails, the circuit returns to OPEN.

## 7. Distinguishing openTimeout and resetTimeout

These two properties have similar names but govern different time boundaries:

- **openTimeout** is the duration the Circuit Breaker stays in OPEN before transitioning to HALF_OPEN to test recovery. The default value per the implementation documentation is 20 seconds.
- **resetTimeout** is the wait period after a failure to automatically reset state if no new errors occur during that interval. The default value per the implementation documentation is 5 seconds.

Example:

~~~java
new FrameworkRetryConfigBuilder("inventory")
        .retryPolicy(RetryPolicy.withMaxRetries(2))
        .openTimeout(Duration.ofSeconds(20))
        .resetTimeout(Duration.ofSeconds(5))
        .build();
~~~

Do not use resetTimeout as a substitute for openTimeout. One property controls the wait before probing in HALF_OPEN; the other controls automatic reset when no new errors occur per the implementation's mechanism.

Because timing behavior directly affects recovery traffic, verify state transitions with tests and metrics on the running version. In particular, do not assume resetTimeout is the same as Resilience4j's waitDurationInOpenState.

## 8. Using the Factory in Synchronous Calls

FrameworkRetryCircuitBreakerFactory provides CircuitBreakerFactory, so the API used is the synchronous CircuitBreaker. Example of a service using RestTemplate to call a book service:

~~~java
import org.springframework.cloud.client.circuitbreaker.CircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

@Service
public class BookService {

    private final CircuitBreaker bookCircuitBreaker;
    private final RestTemplate restTemplate;

    public BookService(
            CircuitBreakerFactory<?, ?> circuitBreakerFactory,
            RestTemplate restTemplate) {
        this.bookCircuitBreaker =
                circuitBreakerFactory.create("bookService");
        this.restTemplate = restTemplate;
    }

    public String getBookTitle(Long bookId) {
        return bookCircuitBreaker.run(
                () -> restTemplate.getForObject(
                        "/books/{id}", String.class, bookId),
                error -> "Fallback Book"
        );
    }
}
~~~

In this example:

1. The factory creates a Circuit Breaker with ID bookService.
2. The supplier performs a blocking call via RestTemplate.
3. If an error occurs, RetryPolicy is applied as configured.
4. If the entire execution fails, the Circuit Breaker can open.
5. The fallback receives the Throwable and returns an alternative result.
6. While the Circuit Breaker is OPEN, new calls are rejected fast and the fallback can be used.

Fallbacks should carry business meaning. The string "Fallback Book" is purely illustrative. In a real application, you might return cached data, a temporary status, or a standardized business error. Never return fake data as though it were the latest live data.

## 9. Why Framework Retry Does Not Support Reactive Applications

Reactive applications use Mono, Flux, and subscriptions to describe asynchronous work. A publisher generally has not executed when it is constructed; it begins upon subscription and emits onNext, onError, or onComplete signals later.

FrameworkRetryCircuitBreakerFactory provides the synchronous CircuitBreakerFactory API, not ReactiveCircuitBreakerFactory. Consequently, this implementation cannot protect the reactive lifecycle of Mono or Flux.

A common design mistake is passing a Mono into a synchronous CircuitBreaker's supplier:

~~~java
Mono<Book> result = circuitBreaker.run(
        () -> webClient.get()
                .uri("/books/{id}", bookId)
                .retrieve()
                .bodyToMono(Book.class),
        error -> Mono.just(Book.fallback())
);
~~~

This code does not create a reactive Circuit Breaker. The synchronous supplier may simply return the Mono instance before the HTTP request is ever subscribed to. The Circuit Breaker risks recording publisher creation as a success while network errors or timeouts only occur later inside the reactive pipeline. A synchronous fallback is also not equivalent to a fallback handling Reactor's onError signal.

Do not work around this by calling block() on the WebFlux event loop. block() turns the execution flow into synchronous waiting, forfeiting reactive benefits and risking event-loop starvation or errors when blocking on threads that forbid blocking.

## 10. Choosing Resilience4j for Reactive Applications

If a service uses WebFlux, WebClient, Mono, or Flux, use Resilience4j's reactive starter:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-circuitbreaker-reactor-resilience4j</artifactId>
</dependency>
~~~

ReactiveCircuitBreakerFactory creates a ReactiveCircuitBreaker by ID. The run method takes the primary publisher and a fallback publisher of the same type:

~~~java
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreakerFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

@Service
public class ReactiveBookService {

    private final WebClient webClient;
    private final ReactiveCircuitBreaker bookCircuitBreaker;

    public ReactiveBookService(
            WebClient webClient,
            ReactiveCircuitBreakerFactory<?, ?> factory) {
        this.webClient = webClient;
        this.bookCircuitBreaker = factory.create("bookService");
    }

    public Mono<Book> getBook(Long bookId) {
        Mono<Book> remoteCall = webClient.get()
                .uri("/books/{id}", bookId)
                .retrieve()
                .bodyToMono(Book.class);

        return bookCircuitBreaker.run(
                remoteCall,
                error -> Mono.just(Book.fallback())
        );
    }
}
~~~

With Flux, the fallback must likewise return a Flux of the same element type. ReactiveCircuitBreaker protects publisher execution, so errors raised during subscription are observed within the reactive pipeline.

Resilience4j configuration for the reactive starter can use familiar Circuit Breaker properties such as slidingWindowType, slidingWindowSize, minimumNumberOfCalls, failureRateThreshold, and waitDurationInOpenState. Specific configuration mechanics depend on the implementation and version. Resilience4j also provides Retry, TimeLimiter, and Bulkhead modules to coordinate with Circuit Breaker in reactive applications.

Do not add the Framework Retry starter expecting it to automatically become a reactive implementation. If an application has both blocking and reactive parts, select the proper factory and implementation for each flow. Avoid wrapping publishers with a synchronous factory.

## 11. Comparing Framework Retry with Resilience4j

| Criterion | Framework Retry | Resilience4j |
|---|---|---|
| Foundation | Spring Framework 7 RetryTemplate and RetryPolicy | Resilience4j library |
| Spring Cloud API | CircuitBreakerFactory | CircuitBreakerFactory and ReactiveCircuitBreakerFactory |
| Reactive | Not supported | Supported with Reactor integration |
| How circuit opens | A logical execution failing after retries are exhausted can open the circuit | Can use failure rate, slow-call rate, and sliding window |
| HALF_OPEN | One probe call | Configurable number of permitted probe calls |
| Retry | Spring Framework's RetryPolicy | Resilience4j Retry |
| Bulkhead/Rate Limiter | Not the focus of this implementation | Dedicated modules available |
| Configuration | FrameworkRetryConfigBuilder and Customizer | Customizer, properties, and Resilience4j configuration |
| Best fit | Blocking applications already using Spring Framework 7 Retry | Applications needing rich resilience policies or reactive support |

Framework Retry has the advantage of integrating with Spring Framework 7's native retry API. Resilience4j fits when you need detailed failure statistics configuration, slow-call thresholds, sliding windows, Bulkhead, Rate Limiter, and reactive support.

Do not decide based solely on dependency count. Consider the execution model, how errors need to be measured, and the required policies. A simple blocking application may fit Framework Retry well; a WebFlux application or one needing multiple protection layers typically fits Resilience4j.

## 12. Common Limitations and Implementation Mistakes

- **Using Framework Retry with Spring Framework older than 7**: the required native Retry APIs do not exist in those versions.
- **Confusing Framework Retry with Spring Retry**: the two implementations have similar names but use different APIs and starters.
- **Expecting ReactiveCircuitBreakerFactory**: the Framework Retry implementation does not provide reactive support.
- **Wrapping a Mono with synchronous CircuitBreaker**: the Circuit Breaker may only observe publisher creation, missing errors raised upon subscription.
- **Calling block() on the event loop**: can stall WebFlux and break the reactive model.
- **Assuming every failed attempt opens the circuit**: the implementation opens the circuit when a complete logical execution fails after RetryPolicy is exhausted.
- **Retrying every exception**: business or configuration errors do not resolve on retry.
- **Failing to bound total duration**: multiple retries can exceed the request deadline.
- **Retrying non-idempotent operations**: can cause duplicate side effects when the server processed the first attempt and the response was lost.
- **Confusing openTimeout with resetTimeout**: the two properties control different time milestones.
- **Expecting multiple concurrent HALF_OPEN calls**: Framework Retry permits a single probe call.
- **Inconsistent ID configuration**: the ID in factory.create must correspond to the declared per-ID configuration.

## 13. Selection and Verification Workflow

When implementing FrameworkRetryCircuitBreakerFactory, follow this sequence:

1. Confirm the application uses Spring Framework 7 and a compatible Spring Cloud release train.
2. Determine whether the call to protect is blocking or reactive.
3. If blocking, add spring-cloud-starter-circuitbreaker-framework-retry.
4. Configure RetryPolicy, openTimeout, and resetTimeout via Customizer.
5. Create the Circuit Breaker using a stable ID and wrap the blocking call along with a fallback.
6. Retry only transient exceptions, bounding attempt counts and time budget.
7. Test CLOSED, OPEN, and HALF_OPEN states using success, post-retry failure, and recovery scenarios.
8. Verify that one probe call is executed after openTimeout and its outcome decides whether the circuit closes or reopens.
9. If the application is reactive, use the reactive Resilience4j starter and ReactiveCircuitBreakerFactory instead of Framework Retry.
10. Monitor errors, retry counts, fallbacks, and response times to tune policies.

FrameworkRetryCircuitBreakerFactory is an option for synchronous calls on Spring Framework 7. It combines RetryPolicy with Circuit Breaker state, opens the circuit after a logical execution fails completely, and permits a single probe call in HALF_OPEN. The implementation does not support Mono or Flux; reactive applications require Resilience4j's ReactiveCircuitBreaker so the Circuit Breaker properly observes subscription lifecycles and error signals.

## References

- [Spring Cloud CircuitBreaker — Configuring Framework Retry Circuit Breakers](https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-framework-retry.html)
- [Spring Cloud CircuitBreaker — Overview of Implementations and APIs](https://docs.spring.io/spring-cloud-circuitbreaker/reference/)
