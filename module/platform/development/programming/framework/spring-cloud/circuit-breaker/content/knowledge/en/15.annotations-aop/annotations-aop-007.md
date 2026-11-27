# Synchronous, Asynchronous, and Reactive Return Types

Resilience4j integrates with Spring AOP through annotations such as `@CircuitBreaker`, `@Retry`, `@RateLimiter`, `@Bulkhead`, and `@TimeLimiter`. How an annotation protects a call depends on the method's return type. A method returning `Stock` executes synchronously; a method returning `CompletableFuture<Stock>` publishes its result asynchronously; and `Mono<Stock>` or `Flux<Stock>` describes a reactive pipeline that executes upon subscription.

With Spring Cloud Circuit Breaker, an application can also choose the explicit API via `CircuitBreakerFactory` for synchronous calls or `ReactiveCircuitBreakerFactory` for `Mono`/`Flux`. Understanding return-type boundaries helps the Circuit Breaker observe the exact timing of success, failure, timeout, and fallback, while avoiding blocking the WebFlux event loop.

## 1. Three Execution Models and When Outcomes Are Recorded

| Return Type | Execution Model | When Is the Outcome Known? | Commonly Used API |
| --- | --- | --- | --- |
| `T` or `void` | Method runs synchronously on the calling thread | When the method body returns or throws an exception | Synchronous AOP annotations; `CircuitBreakerFactory` |
| `CompletableFuture<T>` / `CompletionStage<T>` | Method returns a handle to asynchronous work | When the stage completes normally or exceptionally | AOP annotations for async; CompletionStage decorator API |
| `Mono<T>` / `Flux<T>` | Reactive pipeline, typically lazy and non-blocking | When a subscriber activates it and the publisher emits a terminal or error signal | Annotations with `resilience4j-reactor`; Reactor operators; `ReactiveCircuitBreakerFactory` |

An annotation does not automatically turn a blocking method returning `T` into an asynchronous one. If the method body calls a synchronous HTTP client and waits 5 seconds, the calling thread remains blocked for 5 seconds. Similarly, declaring a `CompletableFuture` return type while calling blocking code before creating the future still blocks the calling thread.

With `Mono`/`Flux`, constructing the publisher does not usually send the request yet. The Circuit Breaker must wrap the pipeline so permissions and outcomes are recorded per subscription. Do not call `subscribe()` manually inside a service/controller and do not call `.block()` on a WebFlux thread.

## 2. Preparing Dependencies for Annotations and Reactive Support

For Spring Boot 3 using Resilience4j directly, the starter needs Actuator and Spring AOP:

```groovy
dependencies {
    implementation 'io.github.resilience4j:resilience4j-spring-boot3'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'org.springframework.boot:spring-boot-starter-aop'
}
```

If the application uses WebFlux and wants to use Resilience4j's annotations or reactive extensions with Reactor, add `resilience4j-reactor` under the version-managing BOM:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'io.github.resilience4j:resilience4j-reactor'
}
```

Spring Cloud CircuitBreaker has dedicated starters. Synchronous calls use `org.springframework.cloud:spring-cloud-starter-circuitbreaker-resilience4j`; reactive calls use `org.springframework.cloud:spring-cloud-starter-circuitbreaker-reactor-resilience4j`. Manage versions using a Spring Cloud BOM compatible with Spring Boot. Pick one integration path as the primary API for each call to avoid wrapping the same dependency in two independent Circuit Breakers.

## 3. Synchronous Return Types: T and void

For methods returning ordinary values, the AOP annotation wraps the method's execution duration. If the method body returns normally, the outcome is recorded as a success; if it throws an exception, the aspect can record a failure and invoke a fallback.

```java
@Service
public class InventoryService {
    private final InventoryClient inventoryClient;

    public InventoryService(InventoryClient inventoryClient) {
        this.inventoryClient = inventoryClient;
    }

    @CircuitBreaker(name = "inventory", fallbackMethod = "stockFallback")
    public Stock getStock(String sku) {
        return inventoryClient.getStock(sku);
    }

    public Stock stockFallback(String sku, CallNotPermittedException error) {
        return Stock.unavailable(sku, "CIRCUIT_OPEN");
    }

    public Stock stockFallback(String sku, Throwable error) {
        return Stock.unavailable(sku, "DEPENDENCY_ERROR");
    }
}
```

In this example, `getStock` returns `Stock` directly. `CallNotPermittedException` occurs when the Circuit Breaker denies permission, such as when the circuit is `OPEN`; the general fallback handles remaining errors. `Stock`, `InventoryClient`, and the constructor merely illustrate application structure.

Synchronous methods fit blocking clients and Spring MVC, though the calling thread must wait. If you need to bound waiting time for a blocking call, configure timeouts directly on the HTTP client/driver and consider `TimeLimiter` via a Future-based API or Spring Cloud CircuitBreaker. `@TimeLimiter` cannot time a method that has already returned a synchronous value after completing.

Do not place `@TimeLimiter` on a method returning `String`, `Stock`, primitives, or `void` expecting it to offload work to another thread automatically. If you need synchronous execution with a deadline, use Resilience4j's `executeFutureSupplier` API or the Spring Cloud factory with a TimeLimiter configuration; consider adding a Bulkhead to cap concurrent blocking tasks.

## 4. Asynchronous Return Types: CompletableFuture and CompletionStage

`CompletableFuture<T>` implements both `Future<T>` and `CompletionStage<T>`. It allows a method to return immediately while work continues on an executor. Resilience4j supports aspects such as `@CircuitBreaker`, `@Retry`, `@RateLimiter`, and `@Bulkhead` with the asynchronous `CompletableFuture` type. `@TimeLimiter` also requires an asynchronous result to attach a deadline.

```java
@Service
public class PricingService {
    private final PricingClient pricingClient;
    private final Executor pricingExecutor;

    public PricingService(PricingClient pricingClient, Executor pricingExecutor) {
        this.pricingClient = pricingClient;
        this.pricingExecutor = pricingExecutor;
    }

    @CircuitBreaker(name = "pricing", fallbackMethod = "priceFallback")
    @TimeLimiter(name = "pricing")
    public CompletableFuture<Price> getPrice(String isbn) {
        return CompletableFuture.supplyAsync(
                () -> pricingClient.fetch(isbn),
                pricingExecutor
        );
    }

    public CompletableFuture<Price> priceFallback(String isbn, Throwable error) {
        return CompletableFuture.completedFuture(Price.unavailable(isbn));
    }
}
```

`pricingExecutor` is an executor whose lifecycle is managed by the application. `supplyAsync` submits the blocking call to that executor; if `pricingClient` already exposes a true async API, use the `CompletionStage` returned by the client directly instead of adding another thread wrapper.

In this example, TimeLimiter does not declare its own fallback so that `TimeoutException` propagates out of its aspect. Under the default aspect order, Circuit Breaker wraps outside TimeLimiter and can record the timeout before `priceFallback` converts the error into a fallback result. If TimeLimiter's fallback handled the error first, an outer Circuit Breaker aspect might only observe a stage completing successfully.

Do not write `CompletableFuture.completedFuture(pricingClient.fetch(isbn))` when `fetch` is blocking. Java invokes `fetch` before constructing the future, so the current thread is still blocked. Likewise, do not default to `ForkJoinPool.commonPool()` for blocking I/O without evaluating application load and thread policies.

`@TimeLimiter` limits the stage wait time according to the `pricing` instance configuration. `cancelRunningFuture` can request Future cancellation upon expiration, but cancellation does not guarantee that all underlying tasks stop immediately. Configure timeouts on the HTTP client/driver and verify whether the client API supports request cancellation.

With AOP, prefer declaring `CompletableFuture` explicitly so the aspect recognizes the return type. Resilience4j's programmatic API can accept a `Future` in `executeFutureSupplier`, but that does not mean every annotation aspect supports raw `Future` identically. Check documentation for the version in use; do not use raw `Future` with `@TimeLimiter` if the aspect requires `CompletionStage`.

## 5. Reactive Return Types: Mono and Flux

`Mono<T>` emits at most one element; `Flux<T>` can emit multiple elements. Both typically begin work only when subscribed to. Resilience4j provides the `resilience4j-reactor` module so aspects and reactive operators can handle publishers. With Spring Cloud CircuitBreaker, you can use `ReactiveCircuitBreakerFactory` to wrap `Mono` or `Flux` and provide a fallback returning a publisher.

Example using an annotation with `Mono`:

```java
@Service
public class ReactiveInventoryService {
    private final WebClient webClient;

    public ReactiveInventoryService(WebClient webClient) {
        this.webClient = webClient;
    }

    @CircuitBreaker(name = "inventory", fallbackMethod = "stockFallback")
    public Mono<Stock> getStock(String sku) {
        return webClient.get()
                .uri("/stock/{sku}", sku)
                .retrieve()
                .bodyToMono(Stock.class);
    }

    public Mono<Stock> stockFallback(String sku, CallNotPermittedException error) {
        return Mono.just(Stock.unavailable(sku, "CIRCUIT_OPEN"));
    }

    public Mono<Stock> stockFallback(String sku, Throwable error) {
        return Mono.just(Stock.unavailable(sku, "DEPENDENCY_ERROR"));
    }
}
```

The fallback has type `Mono<Stock>`, compatible with the original method. `Flux<T>` can be used similarly; the fallback must return `Flux<T>`. If the fallback itself emits an error, that error continues to the subscriber. Only use `Flux.empty()` when the business contract genuinely allows treating a failure as an empty stream.

In reactive flows, Circuit Breaker permission is checked when the pipeline is subscribed to. Each subscription can trigger a separate execution. Therefore, avoid subscribing multiple times to the same publisher unless you intend to send multiple requests. Use `cache()` or `share()` only when sharing outcomes across subscribers fits the application semantics; both operators affect lifecycle and pipeline re-execution.

### Wrapping Reactive Calls with Spring Cloud CircuitBreaker

If the application uses Spring Cloud's abstraction, you can use `ReactiveCircuitBreakerFactory` instead of annotations:

```java
public Mono<Stock> getStock(String sku) {
    Mono<Stock> request = webClient.get()
            .uri("/stock/{sku}", sku)
            .retrieve()
            .bodyToMono(Stock.class);

    return reactiveCircuitBreakerFactory.create("inventory").run(
            request,
            error -> Mono.just(Stock.unavailable(sku, "DEPENDENCY_ERROR"))
    );
}
```

`ReactiveCircuitBreakerFactory.create("inventory")` creates a breaker with ID `inventory`. The `run` method takes a `Mono` or `Flux` and a fallback function accepting `Throwable` and returning a matching publisher. This makes protection boundaries explicit in code and does not depend on method invocation passing through an annotation proxy.

### TimeLimiter with Reactor

Reactor needs a timeout applied to the publisher lifecycle. You can use `TimeLimiterOperator` from `resilience4j-reactor`, or Reactor's `.timeout(...)` operator when a deadline is only needed at the pipeline layer. Example using Resilience4j's operator:

```java
Mono<Stock> protectedRequest = Mono.fromCallable(() -> blockingInventoryClient.getStock(sku))
        .subscribeOn(Schedulers.boundedElastic())
        .transformDeferred(TimeLimiterOperator.of(timeLimiter))
        .transformDeferred(CircuitBreakerOperator.of(circuitBreaker))
        .onErrorResume(error -> Mono.just(
                Stock.unavailable(sku, "DEPENDENCY_ERROR_OR_TIMEOUT")));
```

`subscribeOn(Schedulers.boundedElastic())` shifts the blocking call to a scheduler suited for blocking tasks instead of running it on the event loop. `TimeLimiterOperator` sets a timeout on the publisher; `CircuitBreakerOperator` sits outside so it also observes timeout errors. The `onErrorResume` fallback is placed after both operators so the Circuit Breaker sees errors before they are converted into fallback data.

For `Mono`, the timeout applies to waiting for the completion signal. For `Flux`, Reactor timeouts typically monitor idle gaps between signals; a stream emitting items steadily can continue longer than `timeoutDuration`. If business logic requires bounding the total lifetime of the entire stream, define a separate total deadline and test those exact semantics rather than assuming an inter-signal timeout is a total duration limit.

With `WebClient`, which is already non-blocking, there is no need to wrap calls in `fromCallable` or switch to `boundedElastic`. You can wrap the WebClient publisher directly. When using the `@TimeLimiter` annotation with `Mono`/`Flux`, ensure `resilience4j-reactor` is present and check the starter/aspect version in use; explicit operators are easier to control when you need to specify exactly how timeout applies to the pipeline.

## 6. Practical Compatibility Matrix

| Annotation / API | Synchronous T | CompletableFuture / CompletionStage | Mono / Flux |
| --- | --- | --- | --- |
| `@CircuitBreaker` | Yes | Yes | Yes with Reactor extension |
| `@Retry` | Yes | Yes | Yes with Reactor extension |
| `@RateLimiter` | Yes | Yes | Yes with Reactor extension |
| `@Bulkhead` | Yes; defaults to semaphore | Yes; thread-pool bulkhead selectable | Yes with Reactor extension |
| `@TimeLimiter` | Not for plain value/void | Used with CompletionStage/CompletableFuture | Yes with Reactor extension in supported versions; verify dependency and version |
| Spring Cloud `CircuitBreakerFactory` | Synchronous API | Not a specialized reactive API | No; use the reactive factory |
| Spring Cloud `ReactiveCircuitBreakerFactory` | No | No | Yes; accepts Mono/Flux |

This table summarizes typical usage of the Spring Boot starter and Spring Cloud CircuitBreaker. Details on supported return types, AOP packages, and fallback behavior can vary by major/minor version. Check the dependency tree and documentation for your exact release train before applying to a project.

## 7. AOP Proxies: Why Annotations Sometimes Do Not Run

Resilience4j annotations are executed by Spring AOP aspects. Spring creates a proxy for the bean, and the aspect runs only when calls pass through that proxy. Therefore:

- Place annotations on methods of Spring-managed beans, such as `@Service` or `@Component`.
- Invoke the method from another bean via dependency injection so the call passes through the proxy.
- Internal calls like `this.getStock(...)` within the same bean usually do not go through the proxy, so the aspect can be bypassed.
- Do not invoke constructors directly to manually instantiate an annotated service; that instance will not be proxied by Spring.
- Check the project's proxy mode and method proxyability. With JDK proxies, the method must be on a proxied interface; with class-based proxies, keep class-proxy restrictions such as `final` methods in mind.

Confusing self-invocation example:

```java
@Service
public class OrderService {
    public Order getOrder(String id) {
        return loadProtected(id);
    }

    @CircuitBreaker(name = "orders")
    public Order loadProtected(String id) {
        return orderClient.getOrder(id);
    }
}
```

`getOrder` calls `loadProtected` via `this` inside the same bean, so the call can bypass the proxy and `@CircuitBreaker` is not applied. You can extract the protected part into a separate bean and inject it into `OrderService`, or use an explicit decorator/factory API.

## 8. Fallbacks Must Match the Return Type

An annotation's fallback method usually lives in the same class as the protected method, accepts the same business parameters, and appends one exception parameter at the end. The return type must be compatible with the original return type:

| Protected Method | Fallback Signature |
| --- | --- |
| `Stock getStock(String sku)` | `Stock fallback(String sku, Throwable error)` |
| `CompletableFuture<Price> getPrice(String isbn)` | `CompletableFuture<Price> fallback(String isbn, Throwable error)` |
| `Mono<Stock> getStock(String sku)` | `Mono<Stock> fallback(String sku, Throwable error)` |
| `Flux<Event> events(String id)` | `Flux<Event> fallback(String id, Throwable error)` |

If multiple fallbacks share the same name with different exception types, Resilience4j selects the most specific match. You can have a general fallback accepting `Throwable`, but avoid swallowing every error. Preserve input or programming errors from which the application cannot recover.

A fallback for `CompletableFuture` must return a completed future or a new async future; a fallback for `Mono`/`Flux` must return a publisher. Do not call `.block()` in a reactive fallback and do not return `Stock` directly from a `Mono<Stock>` fallback.

## 9. Aspect Ordering and Its Impact on Outcomes

When placing multiple annotations on the same method, aspect order determines which layer sees errors and how many calls are recorded. Resilience4j describes the default nesting order as:

```text
Retry(
  CircuitBreaker(
    RateLimiter(
      TimeLimiter(
        Bulkhead(method)
      )
    )
  )
)
```

With this order, Retry is on the outside and can re-execute the entire inner chain; Circuit Breaker may observe each execution depending on its position in the chain. If you want Circuit Breaker to record only the outcome after all Retry attempts, design the appropriate ordering and verify with tests. You can configure aspect order via properties `resilience4j.retry.retryAspectOrder`, `resilience4j.circuitbreaker.circuitBreakerAspectOrder`, `resilience4j.ratelimiter.rateLimiterAspectOrder`, `resilience4j.timelimiter.timeLimiterAspectOrder`, and `resilience4j.bulkhead.bulkheadAspectOrder`.

If ordering is complex or you need exact control over how decorators wrap a publisher, use functional chaining instead of stacking many annotations. Document clearly whether a failure counts as one call or multiple attempts; that directly impacts sliding windows and circuit-opening thresholds.

## 10. Verification Scenarios by Return Type

Test with a mock client or mock server to control outcomes and latency:

1. **Synchronous:** call a method returning `T` with dependency success then failure. Confirm the aspect records outcomes and the synchronous fallback has the right return type.
2. **Asynchronous:** return a `CompletableFuture` that completes normally, then one that completes exceptionally. Confirm the Circuit Breaker records outcomes when the stage completes, not when the method returns the future.
3. **Async timeout:** make the future complete slower than `timeoutDuration`. Confirm the caller receives a timeout/fallback; check cancellation and the underlying task state.
4. **Reactive Mono:** confirm the pipeline does not call the dependency before subscription; subscribing once triggers one request; upstream errors reach the fallback.
5. **Reactive Flux:** test a publisher emitting multiple elements, completing normally, and emitting a mid-stream error. Confirm fallback semantics match the API contract.
6. **AOP proxy:** invoke the bean from another bean and compare with self-invocation. Confirm the proxied case runs the aspect and the internal case is unprotected as expected.
7. **Missing Reactor extension:** run configuration checks with and without `resilience4j-reactor` to confirm the application loaded the extension for Mono/Flux properly.
8. **Aspect order:** combine Retry and Circuit Breaker, trigger one failure then recover on the next attempt; check call counts, failures recorded in the sliding window, and fallback behavior.

Do not check only the final returned value. With CompletableFuture and Reactor, verify outcome recording timing, subscription counts, actual requests sent, and exceptions propagated through each protection layer.

## 11. Common Pitfalls

- Placing `@TimeLimiter` on a method returning a plain value and expecting AOP to automatically run it on a worker thread.
- Returning `CompletableFuture` while performing blocking I/O before constructing the future.
- Using raw `Future` with async annotations without verifying the return types supported by your version's aspect.
- Using `Mono`/`Flux` without `resilience4j-reactor`, leaving the reactive extension unregistered.
- Calling `.block()` or `subscribe()` in a WebFlux service, blocking the event loop or creating unexpected subscriptions.
- Calling an annotated method via self-invocation, bypassing the Spring AOP proxy.
- Returning `T` from a fallback when the original method returns `Mono<T>` or `CompletableFuture<T>`.
- Placing a fallback inside Circuit Breaker and turning errors into success data before the breaker records them.
- Unintentionally using both Spring Cloud's factory and Resilience4j annotations on the same call, creating multiple independent breakers.
- Failing to verify aspect ordering when combining Retry, Circuit Breaker, TimeLimiter, and Bulkhead.

## References

- [Resilience4j – Getting Started with Spring Boot 2 and 3](https://resilience4j.readme.io/docs/getting-started-3): starters, AOP annotations, return types, fallback methods, and aspect ordering.
- [Resilience4j – Examples for Reactor](https://resilience4j.readme.io/docs/examples-1): CircuitBreakerOperator, RateLimiterOperator, BulkheadOperator, RetryOperator, and Mono/Flux support.
- [Resilience4j – TimeLimiter](https://resilience4j.readme.io/docs/timeout): TimeLimiter with Future/CompletionStage and schedulers.
- [Spring Cloud Commons – Circuit Breaker](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-circuitbreaker.html): `CircuitBreakerFactory`, `ReactiveCircuitBreakerFactory`, and wrapping Mono/Flux.
- [Spring Cloud CircuitBreaker – Resilience4j](https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-resilience4j.html): synchronous/reactive starters and implementation configuration.
