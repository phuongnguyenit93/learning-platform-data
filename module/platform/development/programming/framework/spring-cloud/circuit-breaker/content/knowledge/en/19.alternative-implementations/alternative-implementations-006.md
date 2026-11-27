# Spring Framework Retry: Spring Framework 7 Requirement and Compatible Versions

## Objectives

Spring Framework 7 adds built-in retry directly in the Spring platform: the `@Retryable` annotation, the programmatic `RetryTemplate` API, and `RetryPolicy`. These APIs live in core Framework modules and differ in usage and packages from the legacy Spring Retry library. When implementing Circuit Breaker in Spring Cloud, you need to identify the right Framework version, choose the right retry API set, and understand how retry coordinates with Circuit Breaker.

After this lesson, you will be able to:

- Identify the minimum Spring Framework version required to use built-in Framework retry.
- Distinguish Spring Framework Retry from the `org.springframework.retry:spring-retry` artifact.
- Enable and use `@Retryable` via `@EnableResilientMethods`.
- Use `RetryTemplate` and `RetryPolicy` for code blocks requiring programmatic retry.
- Correctly interpret `maxRetries`, backoff, jitter, and exception conditions.
- Choose the appropriate approach for Spring Boot 3.x, Spring Boot 4.x, and standalone Spring Framework applications.

## Which Version Introduced Spring Framework Retry?

Starting in **Spring Framework 7.0**, Spring brings foundational resilience features into the core platform. The new retry support lives in two packages:

| Component | Package | Role |
|---|---|---|
| `@Retryable`, `@EnableResilientMethods` | `org.springframework.resilience.annotation` | Declares retry on Spring bean methods and enables annotation processing. |
| `RetryTemplate`, `RetryPolicy`, `RetryListener` | `org.springframework.core.retry` | Programmatically retries code blocks and customizes policies. |

This is a Spring Framework feature, not a new release of the `spring-retry` artifact. You do not need the `org.springframework.retry:spring-retry` dependency to use the retry API built into Framework 7; the application needs the corresponding Spring modules, typically already included via Spring Boot dependency management.

`@Retryable` is metadata processed by Spring through a proxy. Simply placing the annotation in code is not enough to activate retries; the application must enable the annotation processor with `@EnableResilientMethods` or register the corresponding `RetryAnnotationBeanPostProcessor`. `RetryTemplate` is a programmatic API and does not require AOP annotation enablement to be called directly.

## Version Compatibility Matrix

The critical requirement is the **Spring Framework** version, not just the Spring Boot version name:

| Platform | Underlying Framework Version | Built-in Spring Framework Retry? |
|---|---|---|
| Spring Framework 7.0.x | 7.0.x | Yes, starting in 7.0. |
| Spring Framework 7.1.x | 7.1.x | Yes; introduced in 7.0. |
| Spring Boot 4.0.x | Spring Framework 7.0.x | Yes. |
| Spring Boot 4.2.x | Spring Framework 7.1.0 or higher | Yes. |
| Spring Boot 3.5.x | Spring Framework 6.2.x | Does not have the new built-in retry API. |
| Spring Framework 6.x | 6.x | Does not include Framework 7's `org.springframework.core.retry` and `org.springframework.resilience.annotation`. |

According to the system requirements documentation at the time of writing, Spring Boot 4.0.10 requires Spring Framework 7.0.11 or higher; Spring Boot 4.2.0 requires Spring Framework 7.1.0 or higher. Spring Boot 3.5.16 requires Spring Framework 6.2.19 or higher. Patch numbers change with releases; check the system requirements and BOM for your exact Spring Boot line before upgrading.

Spring Boot 4.x requires Java 17 or higher. When using Spring Boot, let the BOM manage Spring Framework modules in sync. Avoid manually upgrading `spring-core` or `spring-context` to 7.x inside a Boot 3.x application managed on Framework 6.x; mixing modules across major versions can break binary compatibility and auto-configuration.

If your application uses Spring Framework 6.x or Spring Boot 3.x, you can continue using Resilience4j or a retry library compatible with the current Framework line. You cannot simply change imports to `org.springframework.core.retry` when those classes do not exist in Framework 6.x.

## Distinguishing Spring Framework Retry from Legacy Spring Retry

For many years, Spring Retry was a standalone library under the `org.springframework.retry:spring-retry` artifact. Spring Framework 7 brings a streamlined retry set into core and context. The two API sets share similar class names, yet differ in packages, configuration, and several semantics.

| Item | Legacy Spring Retry | Spring Framework Retry (7.0+) |
|---|---|---|
| Dependency | `org.springframework.retry:spring-retry` | Framework 7's `spring-core` and `spring-context` modules. |
| Annotation | `org.springframework.retry.annotation.Retryable` | `org.springframework.resilience.annotation.Retryable` |
| Enable annotation | `@EnableRetry` | `@EnableResilientMethods` |
| Template | `org.springframework.retry.support.RetryTemplate` | `org.springframework.core.retry.RetryTemplate` |
| Attempt limit | `maxAttempts` typically includes the initial call. | `maxRetries` is the number of retries after the initial call. |
| Recovery after exhaustion | Has a `@Recover` mechanism. | The last original exception is propagated to the caller; no one-to-one `@Recover` mapping. |

Imports matter greatly. If both libraries appear on the classpath, the IDE may suggest two `Retryable` annotations or two `RetryTemplate` classes. Verify the full package in imports and decide explicitly which API set the module uses.

Legacy Spring Retry was moved to the `spring-attic` organization and its repository was archived in July 2026. Its final release was 2.0.13 on June 8, 2026. The legacy project is no longer maintained as an actively developed open-source project, and its README directs users to Spring Framework 7's resilience features. Spring Boot 4 also dropped dependency management for legacy Spring Retry; if an application still retains that artifact, its version must be managed explicitly. For new development on Framework 7, prefer the built-in retry API.

## Enabling `@Retryable` in Spring Framework 7

Declare `@EnableResilientMethods` on a configuration class so Spring registers the annotation processor:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.resilience.annotation.EnableResilientMethods;

@Configuration
@EnableResilientMethods
public class ResilienceConfiguration {
}
```

Then place `@Retryable` on the method to retry:

```java
import org.springframework.messaging.MessageDeliveryException;
import org.springframework.resilience.annotation.Retryable;
import org.springframework.stereotype.Service;

@Service
public class NotificationService {
    private final NotificationClient notificationClient;

    public NotificationService(NotificationClient notificationClient) {
        this.notificationClient = notificationClient;
    }

    @Retryable(
            includes = MessageDeliveryException.class,
            maxRetries = 4,
            delay = 100,
            jitter = 10,
            multiplier = 2,
            maxDelay = 1_000)
    public void sendNotification(Notification notification) {
        notificationClient.send(notification);
    }
}
```

The `Notification` and `NotificationClient` types are application components. The example retries only message delivery errors classified as transient. `maxRetries = 4` means one initial call and up to four retries, for up to five total executions. `delay` is the base wait interval in milliseconds by default; `multiplier` increases the wait between retries, `jitter` adds randomness, and `maxDelay` caps the wait.

`@Retryable` can be placed at the method level or class level. When placed at the class level, the annotation applies to methods invoked through the proxy across the class hierarchy. Prefer placing it on specific methods so readers clearly see which operations are retried and to avoid unintentionally retrying unrelated operations.

## Retry Conditions and Default Behavior

Without configured conditions, `@Retryable` by default can retry any exception thrown by the method. The default is up to three retries after the initial call, with a one-second wait between attempts. Once the policy exhausts retries, the last original exception is propagated to the caller.

In real applications, restrict retries to recoverable exceptions:

```java
@Retryable(
        includes = {
                java.net.ConnectException.class,
                java.net.SocketTimeoutException.class
        },
        excludes = {
                IllegalArgumentException.class,
                SecurityException.class
        },
        maxRetries = 2,
        delay = 150,
        multiplier = 2,
        maxDelay = 600)
public Product loadProduct(String id) {
    return catalogClient.load(id);
}
```

`includes` selects exception types to retry; `excludes` omits exceptions that must not be retried. Matching inspects the thrown exception and its nested causes. If more complex classification logic is needed, supply a `MethodRetryPredicate` via the `predicate` attribute; the predicate receives method metadata and the exception to decide whether to retry.

Do not retry validation errors, access errors, or bad input data, because retrying will not make the cause disappear. For HTTP clients, retry only connection errors, timeouts, or status codes defined as transient by the API contract. For operations with side effects like order creation or payment, require an idempotency key or result lookup mechanism to prevent duplicate execution if the server already processed the request and the response was lost.

## Distinguishing maxRetries and maxAttempts

This difference easily causes bugs when migrating from legacy Spring Retry:

| Configuration | Meaning | Maximum Total Executions |
|---|---|---:|
| Spring Framework `maxRetries = 2` | Two retries after the first call. | 3 |
| Spring Framework `maxRetries = 4` | Four retries after the first call. | 5 |
| Legacy Spring Retry `maxAttempts = 3` | Three executions including the first call. | 3 |

For example, when migrating a method from legacy Spring Retry with `maxAttempts = 3`, the equivalent value in Spring Framework 7 is typically `maxRetries = 2` if you want to preserve the total call count. Do not copy numbers verbatim between the two APIs without checking their meaning.

## Programmatic Retry with RetryTemplate

`RetryTemplate` fits when you need to retry an arbitrary block of code, not necessarily a Spring bean method. The policy is separated into `RetryPolicy`:

```java
import java.time.Duration;

import org.springframework.core.retry.RetryPolicy;
import org.springframework.core.retry.RetryTemplate;
import org.springframework.messaging.MessageDeliveryException;

RetryPolicy policy = RetryPolicy.builder()
        .includes(MessageDeliveryException.class)
        .maxRetries(4)
        .delay(Duration.ofMillis(100))
        .jitter(Duration.ofMillis(10))
        .multiplier(2)
        .maxDelay(Duration.ofSeconds(1))
        .build();

RetryTemplate retryTemplate = new RetryTemplate(policy);

retryTemplate.invoke(() -> notificationClient.send(notification));
```

The builder supports `includes`, `excludes`, `maxRetries`, `delay`, `jitter`, `multiplier`, `maxDelay`, and custom predicates. You can provide a custom `BackOff` via `backOff()` when wait scheduling requires special logic. `RetryTemplate` is lightweight and can be created per specific policy; when reused repeatedly, expose a shared bean with an immutable policy.

`invoke` handles callbacks with or without a return value. When retries are exhausted, the last unchecked exception from the callback is propagated to the caller. If you need detailed state across all attempts, use `execute`; this method throws `RetryException` containing information about the exceptions that occurred, including the last exception.

## Reactive Methods and Reactor

Spring Framework 7 automatically adapts `@Retryable` when a method returns a reactive type such as `Mono` or `Flux`. Spring decorates the pipeline using Reactor's retry support:

```java
import org.springframework.resilience.annotation.Retryable;
import reactor.core.publisher.Mono;

@Retryable(maxRetries = 4, delay = 100)
public Mono<Void> sendNotification(Notification notification) {
    return notificationClient.sendReactive(notification);
}
```

The returned publisher receives retry behavior. Do not manually call `subscribe()` inside the method just to trigger retries; return the publisher to the WebFlux layer or subscriber managing its lifecycle. Verify that the Reactor dependency is present when using reactive return types.

Reactive retry must still obey deadline limits and idempotency. Each retry can create a new subscription or request to the dependency. If a previous request may have already been processed by the server, resending must be safe under the API contract.

## Combining with Transaction, Cache, and Async

Retry is a proxy-based advice, so interceptor ordering affects behavior:

- **With `@Transactional`:** retry advice sits outside transaction advice. Each attempt starts a new transaction; when the method throws an error, that attempt's transaction rolls back before retry decides to try again. This is usually the desired behavior for transient errors such as deadlocks.
- **With `@Cacheable`:** retry sits outside cache advice. Each attempt passes through the cache interceptor; a cache entry populated by another request between attempts can be returned on a subsequent attempt.
- **With `@Async`:** by default, async advice sits outside retry advice. Work is submitted to the executor once; retries run on the async thread and the caller receives the `Future`/`CompletableFuture` once the sequence finishes.

Do not alter advice ordering arbitrarily. In particular, if you invert `@Async` and `@Retryable`, retry may only observe the immediately returned `Future` object and miss exceptions raised during asynchronous execution. Whenever changing order, test execution threads, transactions, and actual attempt counts.

## Coordinating Spring Framework Retry with Circuit Breaker

Spring Framework Retry only performs retries. It does not provide a `CLOSED`, `OPEN`, `HALF_OPEN` state machine, sliding window, failure-rate threshold, or request rejection mechanism when a dependency is unhealthy. In the Spring Cloud Circuit Breaker module, you can use Spring Framework Retry for transient errors and Spring Cloud CircuitBreaker with Resilience4j to monitor dependency health.

The two mechanisms should have clear responsibilities:

| Mechanism | Role |
|---|---|
| Spring Framework `@Retryable` or `RetryTemplate` | Retries an operation when the exception belongs to the retryable set. |
| Resilience4j Circuit Breaker | Tracks outcomes, transitions states, and blocks calls while the dependency is failing. |
| TimeLimiter/HTTP timeout | Bounds the wait time of each attempt or request. |
| Bulkhead | Caps concurrent operations to isolate resources. |

If the Circuit Breaker is `OPEN`, calls can be rejected with `CallNotPermittedException`. Do not retry this rejection exception: the circuit has already decided to temporarily disallow calls to the dependency. Configure `excludes` for the corresponding exception type or write a predicate that only retries network/timeout errors known to be transient. When stacking annotations from multiple libraries on the same method, verify the actual advice order; if exact ordering is required, use explicit programmatic composition and test the number of requests sent upstream.

Fallback is not built into Spring Framework `@Retryable` by default. When retries are exhausted, the last exception propagates to the caller. If you need to return cached or degraded responses, handle it in the application layer or use the Circuit Breaker's fallback according to the API contract.

## Choosing an Approach by Application Version

| Context | Implementation Direction |
|---|---|
| New application on Spring Boot 4.x / Framework 7.x | Prefer `@Retryable` or `RetryTemplate` in Spring Framework. |
| Standalone Spring Framework 7.x application | Use `spring-context` and `spring-core` on the 7.x line; enable `@EnableResilientMethods` if using annotations. |
| Spring Boot 3.x / Framework 6.x application | Use Resilience4j or a retry library compatible with Framework 6; do not import Framework 7 core retry APIs. |
| Existing application using legacy Spring Retry | May need to keep the legacy API during transition; check compatible versions, pin dependency if unmanaged by the BOM, and plan migration to a maintained API. |

When upgrading from Boot 3.x to Boot 4.x, do not change only dependency versions. Check package imports, annotation enablement, attempt counts, fallbacks, listeners, exhaustion handling, and AOP ordering. Spring Framework Retry is designed to be leaner than legacy Spring Retry, so not every legacy feature has a direct drop-in replacement.

## Practical Version and Behavior Verification

Run these checks in a test application with a dependency simulating transient errors:

1. Inspect the dependency tree to confirm `spring-core` and `spring-context` are both on the 7.x line if intending to use built-in retry.
2. Confirm the application has `@EnableResilientMethods`; invoke another bean through the Spring proxy so self-invocation does not bypass advice.
3. Configure `@Retryable` to include only transient exceptions, set `maxRetries = 2`, and observe at most three total calls.
4. Make the dependency succeed on the second attempt; verify the caller receives the result and logs/`MethodRetryEvent` record the initial failure.
5. Make all attempts fail; verify the last exception propagates to the caller and there is no automatic `@Recover` like legacy Spring Retry.
6. Test a method returning `Mono` or `Flux`; verify the pipeline is retried without the service subscribing outside the caller's lifecycle.
7. Disable `@EnableResilientMethods` in a test profile; verify the annotation is not processed, confirming the enablement requirement.
8. If combining with Resilience4j Circuit Breaker, trip the circuit to `OPEN`; verify `CallNotPermittedException` does not trigger additional retries to the dependency.

During verification, record the Framework version, Boot version, attempt counts, exception types, backoff intervals, and actual requests hitting the dependency. Do not rely solely on how many times a controller method is called; interceptors can generate multiple attempts inside one logical call.

## Common Mistakes

- **Using Spring Framework Retry on Framework 6.x:** the `org.springframework.core.retry` and `org.springframework.resilience.annotation` packages do not exist in 6.x.
- **Forgetting `@EnableResilientMethods`:** `@Retryable` is merely metadata without the processor enabled.
- **Importing the wrong `@Retryable`:** legacy Spring Retry and Spring Framework 7 share the same simple name but use different packages.
- **Confusing `maxRetries` with `maxAttempts`:** Framework 7 counts extra retries after the initial call.
- **Keeping `@Recover` during migration:** Framework Retry does not provide a one-to-one `@Recover` equivalent.
- **Retrying every exception:** business, authorization, and validation errors do not fix themselves on retry.
- **Retrying `CallNotPermittedException`:** the Circuit Breaker already rejected the call; retrying immediately does not help the dependency recover.
- **Assuming Retry is a Circuit Breaker:** Retry has no `OPEN` state, sliding window, or failure threshold.
- **Ignoring proxies and self-invocation:** internal calls within the same bean can bypass retry advice.
- **Skipping AOP order checks:** Retry, Transaction, Cache, and Async can change the transaction or thread of each attempt.
- **Skipping BOM checks:** manually mixing Framework 6.x and 7.x modules can cause compatibility failures.

## References

- [Spring Framework 7.0 – Resilience Features](https://docs.spring.io/spring-framework/reference/7.0/core/resilience.html)
- [Spring Framework 7.1 – Resilience Features](https://docs.spring.io/spring-framework/reference/7.1/core/resilience.html)
- [Spring Framework `@Retryable` Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/resilience/annotation/Retryable.html)
- [Spring Boot 4.0 – System Requirements](https://docs.spring.io/spring-boot/4.0/system-requirements.html)
- [Spring Boot 4.2 – System Requirements](https://docs.spring.io/spring-boot/system-requirements.html)
- [Spring Boot 3.5 – System Requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html)
- [Spring Boot 4.0 Migration Guide – Dependency Management for Spring Retry](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide)
- [Spring Retry archived repository](https://github.com/spring-attic/spring-retry)
