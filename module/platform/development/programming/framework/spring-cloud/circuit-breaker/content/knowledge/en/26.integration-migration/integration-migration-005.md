# Migrating Between Annotations and Factory While Preserving Protection Boundaries

In a Spring Cloud CircuitBreaker application, a dependency call can be protected using the explicit `CircuitBreakerFactory` API. Resilience4j also provides the `@CircuitBreaker` annotation to apply the mechanism via Spring AOP. When migrating from annotations to the factory or vice versa, more changes than just coding style: the protected boundary, ID, fallback, decorator ordering, reactive support, and metrics can all shift.

The goal of migration is to preserve the protection behavior the application relies on: which calls are measured, which errors count, when the breaker opens, what the fallback returns, and what the caller receives. This lesson walks through inventorying current boundaries, mapping annotations to the factory, keeping instance-ID configuration intact, handling AOP and reactive differences, and migrating step by step with verification.

## 1. Two Integration Styles with Different Boundaries

Both annotations and the factory can use the Resilience4j Circuit Breaker, but they apply protection differently:

| Criterion | Resilience4j Annotation | Spring Cloud CircuitBreaker Factory |
|---|---|---|
| Activation mechanism | Spring AOP intercepts the annotated method | Code explicitly calls `factory.create(id)` and wraps the call |
| Where the boundary lives | Method intercepted by the proxy | Supplier or Publisher passed into `run` |
| Configuration | Instance name in the annotation binds to Resilience4j config | ID passed to `create(id)` binds to factory/Resilience4j config |
| Fallback | Fallback method following naming and signature conventions | Function accepting Throwable passed directly to `run` |
| Framework coupling | Depends on Resilience4j Spring AOP integration | Uses the Spring Cloud CircuitBreaker abstraction |
| Implementation portability | Tightly bound to Resilience4j annotations | Can use the Spring Cloud abstraction to swap compatible implementations |
| Scope control | Depends on method boundaries and proxy behavior | Protected call scope is directly visible at the factory call site |

Annotations fit well when a Spring-managed method is a clean protection unit and the team wants resilience declared right on the method. The factory fits well when you want to make the exact protected call explicit, select the ID at the call site, or adopt the Spring Cloud abstraction.

Neither approach is automatically superior in every scenario. Choose based on business boundaries, desired explicitness, synchronous vs. reactive call types, and the application's integration conventions.

## 2. Inventorying Current Behavior Before Migration

Before changing code, document the behavior of every annotation currently in use. Do not record only method names; capture exactly what work happens inside the method and which other decorators apply.

Inventory checklist:

- Which methods carry `@CircuitBreaker`, and which instance name is used?
- Does the method call a single dependency, or does it also contain validation, mapping, and local business logic?
- Is the method invoked internally from another method in the same bean?
- Is there a `fallbackMethod`, and what are its signature and final exception types?
- Are `@Retry`, `@TimeLimiter`, `@Bulkhead`, or `@RateLimiter` present on the same method or on its caller?
- In which profile is the instance configuration defined, and are customizers or property overrides active?
- Does the caller receive an exception, an error response, or fallback data?
- Which breaker names, metrics, and alerts do dashboards rely on?

Example current method:

~~~java
@Service
public class CatalogService {
    private final CatalogClient catalogClient;

    public CatalogService(CatalogClient catalogClient) {
        this.catalogClient = catalogClient;
    }

    @io.github.resilience4j.circuitbreaker.annotation.CircuitBreaker(
        name = "catalog-read",
        fallbackMethod = "findFallback"
    )
    public Product findProduct(String id) {
        return catalogClient.fetchProduct(id);
    }

    private Product findFallback(String id, Throwable cause) {
        return Product.unavailable(id);
    }
}
~~~

In this example, the annotation boundary is the entire `findProduct` method. If the method only calls CatalogClient, the boundary is clean. If the method also runs validation, queries another database, or performs complex mapping, any exception in those parts can be counted as a `catalog-read` failure. When moving to the factory, decide deliberately whether to wrap only the Catalog call or the whole pipeline.

## 3. Preserving IDs and Resilience4j Configuration

The ID is a core part of the boundary. The annotation's `name = "catalog-read"` and the factory's `create("catalog-read")` must use the same ID if your goal is to preserve the corresponding configuration policy.

Example instance configuration:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      catalog-read:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 800ms
        slowCallRateThreshold: 50
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 3
~~~

These parameters govern how the breaker observes calls. During migration, preserve at least:

- Sliding window type and size.
- Minimum number of calls.
- Failure rate and slow-call thresholds.
- Slow-call duration threshold.
- Wait duration in OPEN.
- Permitted number of calls in HALF_OPEN.
- Recorded and ignored exception lists.
- Automatic transition policy if enabled.

Do not change the ID just to make new code run. If the ID changes, instance configs, metrics, dashboards, and alerts may stop matching. At the same time, do not assume the annotation and the factory automatically share the same registry or the same CircuitBreaker object at runtime merely because the ID string matches. Registry wiring and configuration depend on the starter and version. Verify the registry bean, actual runtime instances, and metrics after migrating.

If you need to run both styles side by side for a canary, avoid wrapping the same invocation with both an annotation and the factory. If both use the same ID in a shared registry, state and events may be shared or interact unexpectedly; if they use two distinct IDs, they maintain two independent windows and states. Choose a comparison approach that avoids double wrapping and does not double traffic to the dependency.

## 4. Migrating from Annotation to CircuitBreakerFactory

The factory makes the protection boundary explicit at the call site. Equivalent example to the method in the previous section:

~~~java
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;

@Service
public class CatalogService {
    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final CatalogClient catalogClient;

    public CatalogService(
            CircuitBreakerFactory<?, ?> circuitBreakerFactory,
            CatalogClient catalogClient) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.catalogClient = catalogClient;
    }

    public Product findProduct(String id) {
        return circuitBreakerFactory.create("catalog-read").run(
            () -> catalogClient.fetchProduct(id),
            cause -> findFallback(id, cause)
        );
    }

    private Product findFallback(String id, Throwable cause) {
        return Product.unavailable(id);
    }
}
~~~

Mapping summary:

| Legacy Annotation | New Factory |
|---|---|
| `@CircuitBreaker(name = "catalog-read")` | `circuitBreakerFactory.create("catalog-read")` |
| Method body intercepted by AOP | Supplier passed to `run` |
| `fallbackMethod = "findFallback"` | Function `cause -> findFallback(id, cause)` |
| Instance config `catalog-read` | Keep the ID and `catalog-read` instance config |

Verify that the Supplier contains only the intended protected dependency call. If you want to protect a multi-step sequence, make that an explicit decision. Avoid accidentally placing validation, mapping, or a second dependency inside the same Supplier because they can skew Catalog's failure rate.

## 5. Migrating a Fallback Method to a Fallback Function

With annotations, Resilience4j looks up the fallback method by name and signature. The fallback method usually takes the same parameters as the original method plus an extra trailing exception parameter; its return type must be compatible with the protected method.

With the factory, the fallback is passed directly as a Function accepting a Throwable:

~~~java
return circuitBreakerFactory.create("catalog-read").run(
    () -> catalogClient.fetchProduct(id),
    cause -> {
        if (cause instanceof ProductNotFoundException) {
            throw (ProductNotFoundException) cause;
        }

        return cache.findUsable(id)
            .orElseThrow(() ->
                new CatalogUnavailableException(id, cause));
    }
);
~~~

When migrating, do not blindly copy the fallback body while dropping exception classification. A fallback may handle timeouts, not-found errors, and credential errors differently. Preserve each of those branches.

| Scenario | Behavior to Preserve |
|---|---|
| Timeout or connection error | May use valid cached data or return an availability error |
| Breaker OPEN | Fail fast; fall back per the caller's contract |
| Business 404 | Return not found; do not turn it into unrelated cached data |
| 401/403 from dependency | Report integration/credential error; do not mask with a fallback success |
| Write operation timeout | Return an indeterminate or pending-verification status; do not report fake success |
| Fallback has no data | Throw an appropriate error or return a defined degraded response |

A fallback should never call the same protected dependency again. If the fallback calls a cache or backup service, those sources need their own timeouts and resource bounds.

## 6. Migrating from Factory Back to Annotation

In some cases, an application may want to consolidate calls into a Spring-managed method to reduce boilerplate. You can migrate from the factory back to an annotation:

~~~java
@Service
public class CatalogGateway {
    private final CatalogClient catalogClient;

    public CatalogGateway(CatalogClient catalogClient) {
        this.catalogClient = catalogClient;
    }

    @io.github.resilience4j.circuitbreaker.annotation.CircuitBreaker(
        name = "catalog-read",
        fallbackMethod = "findFallback"
    )
    public Product findProduct(String id) {
        return catalogClient.fetchProduct(id);
    }

    private Product findFallback(String id, Throwable cause) {
        if (cause instanceof ProductNotFoundException) {
            throw (ProductNotFoundException) cause;
        }
        return Product.unavailable(id);
    }
}
~~~

For the annotation to take effect, the matching Spring AOP integration must be active and the bean must be Spring-managed. Only calls passing through the Spring proxy trigger the advice. Self-invocation—where a method inside the same object calls the annotated method directly—bypasses the proxy, so the annotation does not apply as expected.

Example:

~~~java
@Service
public class CatalogService {
    public Product load(String id) {
        // Direct call within the same object: bypasses the AOP proxy.
        return findProtected(id);
    }

    @CircuitBreaker(name = "catalog-read")
    public Product findProtected(String id) {
        return catalogClient.fetchProduct(id);
    }
}
~~~

If `load` calls `findProtected` via `this.findProtected(...)`, the call does not go through the Spring proxy. You can extract the protected method into another bean or continue using the factory at the call site if you need an explicit boundary.

## 7. Avoid Wrapping the Same Call Twice

During migration, a common mistake is leaving the old annotation in place while adding a factory call around the same dependency call:

~~~java
@CircuitBreaker(name = "catalog-read")
public Product findProduct(String id) {
    return circuitBreakerFactory.create("catalog-read").run(
        () -> catalogClient.fetchProduct(id)
    );
}
~~~

This is double wrapping. A single invocation passes through two Circuit Breaker layers. Consequences can include:

- Both breakers record the same failure, or one breaker records the outcome of the other.
- The inner layer runs a fallback whose result is then recorded as a success by the outer layer.
- States and metrics become hard to interpret, especially if the two layers use different IDs or registries.
- One OPEN breaker can block the call before the other breaker ever observes it.
- Thresholds and open durations can behave differently than before migration.

Every dependency boundary should have one clearly owned Circuit Breaker mechanism. During migration, remove the old decorator as soon as the new decorator is verified. Never keep both "for extra protection."

## 8. Preserving Retry, TimeLimiter, and Bulkhead Ordering

A method may be protected by multiple Resilience4j mechanisms. When migrating, inventory all decorators—not just the Circuit Breaker.

Legacy annotation example:

~~~java
@Retry(name = "catalog-read")
@CircuitBreaker(name = "catalog-read")
@TimeLimiter(name = "catalog-read")
public CompletableFuture<Product> findAsync(String id) {
    return catalogClient.fetchAsync(id);
}
~~~

Annotation configuration may depend on Resilience4j's aspect ordering. When moving to the factory, do not assume decorator order is preserved automatically. The factory has its own TimeLimiter configuration and Bulkhead provider; Retry might be applied via Resilience4j APIs or another orchestration layer.

Document the current effective ordering and verify the new ordering with tests. A different order can change:

- Does Retry re-run the entire invocation or only a single inner call?
- Does the Circuit Breaker count each attempt or only the final outcome?
- Does TimeLimiter cancel the task on timeout?
- Is the Bulkhead slot held across all retries or per attempt?
- Does the fallback run before or after the other decorators finish?

Do not add Retry during migration if it was not present before. Retry can multiply requests to the dependency and blow past deadlines. For write operations, idempotency keys or duplicate-processing protection are required.

## 9. Distinguishing Synchronous and Reactive Calls

For synchronous calls, use `CircuitBreakerFactory`:

~~~java
Product product = circuitBreakerFactory.create("catalog-read").run(
    () -> catalogClient.fetchProduct(id),
    cause -> cache.findUsable(id)
        .orElseThrow(() -> new CatalogUnavailableException(id, cause))
);
~~~

For Reactor, use `ReactiveCircuitBreakerFactory` and keep the Publisher inside the boundary:

~~~java
Mono<Product> remoteCall = Mono.defer(() ->
    webClient.get()
        .uri("/products/{id}", id)
        .retrieve()
        .bodyToMono(Product.class)
);

return reactiveCircuitBreakerFactory.create("catalog-read").run(
    remoteCall,
    cause -> cache.findUsableReactive(id)
        .switchIfEmpty(Mono.error(
            new CatalogUnavailableException(id, cause)))
);
~~~

Do not convert a reactive call into `block()` just to use the synchronous factory. Do not call `subscribe()` before passing the Publisher into the reactive breaker. The protected Publisher must contain the actual network call; if an error is already converted into a value via `onErrorResume` before entering the breaker, the breaker may only observe success.

Resilience4j annotations also support certain asynchronous/reactive return types depending on the version and integration module. Before switching between annotations and the factory, confirm that the API supports the exact return type you use, especially for `Mono`, `Flux`, and `CompletionStage`. Do not assume you can swap the return type of a synchronous example without changing cancellation, timeout, or fallback semantics.

## 10. Keeping Boundaries Intact When a Method Has Multiple Steps

Suppose the current method calls Catalog, reads pricing from a local database, and maps a DTO:

~~~java
@CircuitBreaker(name = "catalog-read")
public ProductView getView(String id) {
    Product product = catalogClient.fetchProduct(id);
    Price price = localPriceRepository.findPrice(id);
    return mapper.toView(product, price);
}
~~~

With the annotation, all three steps sit inside the intercepted method. If the local database fails or the mapper throws an exception, the `catalog-read` breaker may record a failure even though the Catalog service is healthy.

When migrating to the factory, you can narrow the boundary strictly around the Catalog call:

~~~java
public ProductView getView(String id) {
    Product product = circuitBreakerFactory.create("catalog-read").run(
        () -> catalogClient.fetchProduct(id),
        cause -> cache.findUsable(id)
            .orElseThrow(() -> new CatalogUnavailableException(id, cause))
    );

    Price price = localPriceRepository.findPrice(id);
    return mapper.toView(product, price);
}
~~~

This is an intentional boundary change, not a mechanical translation. If the old behavior counted database and mapping errors toward the breaker, narrowing the boundary will alter metrics. Document that change explicitly in the migration plan and test it separately.

If you need to preserve the old scope in the first pass, wrap the entire method body inside the Supplier first; then make boundary narrowing a separate, tested, and observed change. Separating the two changes makes it far easier to pinpoint why behavior differs.

## 11. Step-by-Step Migration Plan

You can migrate safely in the following phases:

1. **List all callsites:** record methods, annotations, IDs, fallbacks, retries, timeouts, bulkheads, and return types.
2. **Capture a baseline:** record failure rates, slow-call rates, latencies, fallback counts, and state transitions under normal conditions.
3. **Standardize configuration:** keep IDs and Resilience4j parameters intact; verify active profiles and customizers.
4. **Pick one small callsite:** prefer a call with good tests and minimal side effects.
5. **Swap one mechanism:** remove the old annotation or factory, introduce the new one, and avoid double wrapping.
6. **Test outcomes:** success, exceptions, timeouts, slow calls, OPEN, HALF_OPEN, and fallbacks.
7. **Canary traffic:** compare metrics and responses against the baseline, keeping a rollback path ready.
8. **Expand:** migrate similar callsite groups incrementally and update dashboards and docs.
9. **Clean up legacy config:** remove unused beans, dependencies, or annotation integrations only after verifying zero remaining callsites.

Avoid migrating an entire module at once if it spans multiple dependencies and policies. One callsite can use the factory while another still uses annotations during the transition, as long as each call has exactly one owning Circuit Breaker.

## 12. Pre- and Post-Migration Test Matrix

| Scenario | What Must Remain Unchanged |
|---|---|
| Dependency returns 200 | Result and latency remain unchanged aside from negligible overhead |
| Dependency returns business 404 | Caller receives not found; failure rate follows ignore configuration |
| Dependency returns 503 repeatedly | Breaker records failures and transitions to OPEN past threshold |
| Dependency responds slowly | Slow calls are recorded under the same threshold |
| Breaker OPEN | New calls fail fast without sending HTTP requests to the dependency |
| HALF_OPEN | Probe count and close/reopen decisions follow configuration |
| Fallback succeeds | Same data and same semantics as before |
| Fallback fails | Caller receives the contracted error, with no fake success |
| Retry/TimeLimiter/Bulkhead | Attempt counts, deadlines, concurrency, and cancellation remain unchanged unless intended |
| Reactive cancellation | Canceling a subscription leaves no unexpected background requests or tasks running |

Verify both caller responses and breaker metrics. Identical responses alone do not prove that state, failure rates, and fallbacks work identically.

## 13. Post-Migration Observability

Monitor these signals before and after migration per ID:

- Counts of successful, failed, slow, and not-permitted calls.
- Failure rate, slow-call rate, and state transitions.
- Dependency p50, p95, and p99 latencies.
- Fallback counts and fallback success rate.
- HTTP attempt counts if Retry is present.
- Bulkhead rejection counts and thread/queue utilization.
- End-to-end request success rate and errors observed by callers.

Metric names or tags may differ across integrations and versions. Do not assume legacy dashboards continue tracking the same instance after swapping between factory and annotations. Verify actual IDs, registries, and meters, and update alerts if names or tags change.

During a canary, if the new breaker opens more frequently, inspect the boundary and exception classification first. The new Supplier may include extra local logic, or a fallback may have previously recovered errors before the breaker observed them. Never rush to raise thresholds just to make dashboards look like the baseline before understanding the root cause.

## 14. Common Migration Pitfalls

| Symptom | Likely Cause | Resolution |
|---|---|---|
| Annotation has no effect | Method does not pass through a Spring AOP proxy or is self-invoked | Extract to another bean or use the factory at the call site |
| Factory does not pick up old config | ID in `create` differs from the annotation's instance name | Keep the ID consistent or update configuration intentionally |
| Breaker records more errors | Supplier includes mapping or another dependency | Narrow the boundary or accept the tested change |
| Fallback executes twice | Double wrapping or stacked fallback layers | Keep only one Circuit Breaker per boundary |
| Breaker never opens on HTTP errors | Client returns a response object or errors are swallowed | Normalize exceptions or use `recordResult` |
| Metrics split into two series | Registry/instance or breaker name changed | Inspect registry, IDs, and dashboards |
| Total duration increases | Retry or timeout decorator ordering changed | Compute overall request deadlines and check attempt counts |
| Reactive request blocks | Synchronous factory used or `block()` called | Switch to ReactiveCircuitBreakerFactory and keep the Publisher |

## Conclusion

Migrating between Resilience4j annotations and the Spring Cloud CircuitBreaker factory requires preserving dependency boundaries, IDs, exception classification, fallbacks, and decorator order. Annotations rely on Spring AOP and therefore depend on proxies and avoiding self-invocation; the factory makes the protection scope explicit at the Supplier or Publisher. Inventory existing behavior, migrate one callsite at a time, avoid double wrapping, verify sync/reactive semantics, and compare metrics against your baseline. When every dependency has one clear protection boundary verified by tests and telemetry, the application can switch integration styles while keeping expected resilience behavior intact.
