# Aspect Ordering When Combining Retry, Bulkhead, and TimeLimiter

In Spring Boot, Resilience4j can apply `@Retry`, `@Bulkhead`, and `@TimeLimiter` via Spring AOP. When multiple annotations protect the same method, aspects wrap the call in a specific order. That order determines whether each retry attempt must re-acquire a bulkhead permit, whether the TimeLimiter timeout applies per attempt or to the entire sequence, and whether permits are held during backoff or released after each attempt.

Do not infer execution order from the order in which annotations are written in source code. Spring AOP orders advice by aspect order. Choose the order based on protection goals, configure it explicitly, and verify it with integration tests on the exact Resilience4j version in use.

## 1. Aspects Form Wrapping Layers Around the Call

Consider a method calling an inventory service:

```java
@Retry(name = "inventory")
@Bulkhead(name = "inventory")
@TimeLimiter(name = "inventory")
public CompletableFuture<InventoryResult> fetch(String sku) {
    return CompletableFuture.supplyAsync(
        () -> inventoryClient.fetch(sku),
        inventoryExecutor
    );
}
```

When the three aspects are ordered as `Retry` → `Bulkhead` → `TimeLimiter`, the call structure is equivalent to:

```text
Retry(
  Bulkhead(
    TimeLimiter(
      fetchFromDependency()
    )
  )
)
```

The outermost aspect receives the call first and invokes the next inner aspect. When the task finishes or throws an error, the outcome flows back outward. Thus, an outer aspect observes outcomes already processed by inner aspects.

Spring follows the `Ordered` rule: a lower order value has higher precedence. With around advice, a higher-precedence aspect typically sits on the outside; it runs before entering the call and finishes after inner layers return results. Resilience4j's order properties allow tuning the precedence of each aspect. Annotation declaration order on the method does not substitute for this configuration.

## 2. Choose the Goal Before Setting the Order

The three mechanisms have distinct responsibilities:

| Mechanism | Responsibility | Question to Answer |
| --- | --- | --- |
| `Retry` | Retries when the outcome falls into retryable error categories | How many total attempts and what wait intervals are allowed per request? |
| `Bulkhead` | Limits concurrent tasks or threads/queues allocated to a dependency | How much processing capacity may a dependency consume? |
| `TimeLimiter` | Limits waiting time of a `Future` or `CompletionStage` | How long may each attempt or the entire retry sequence last? |

Aspect ordering is not merely an implementation detail. It defines the scope each mechanism protects. For example, a Bulkhead outside Retry holds one permit across the entire retry sequence; a Bulkhead inside Retry acquires and releases a permit per attempt. A TimeLimiter inside Retry applies a separate timeout to each attempt; a TimeLimiter outside Retry can bound the entire sequence if the method returns a stage representing the whole retry process.

## 3. Common Order: Retry → Bulkhead → TimeLimiter

For a dependency that can be retried safely, a frequently useful composition is:

```text
Retry
  └── Bulkhead
        └── TimeLimiter
              └── Dependency call
```

Execution flow:

1. Retry starts an attempt.
2. Bulkhead requests a permit; if capacity is exhausted and waiting is disabled, the call is rejected.
3. TimeLimiter sets a time limit for that attempt's task.
4. The dependency call completes or times out.
5. Bulkhead releases the permit when the attempt finishes.
6. Retry decides whether to stop or wait for backoff before starting the next attempt.

The advantage is that backoff duration does not hold a bulkhead permit. Each attempt must re-acquire a permit, giving other requests a chance to use capacity while the previous request rests between retries. TimeLimiter bounds each attempt individually.

In return, total duration can exceed a single attempt's timeout. For example, three attempts of up to 800 ms each, plus 100 ms and 200 ms backoffs, can take around 2.7 seconds excluding queueing and extra processing time. If an API only has a two-second deadline, add an overall request-level deadline or place an outer bound around the entire sequence.

## 4. Explicit Order Configuration

The example below places Retry outermost, Bulkhead in the middle, and TimeLimiter innermost. The order properties are declared at their respective configuration levels:

```yaml
resilience4j:
  retry:
    retryAspectOrder: 1
    instances:
      inventory:
        maxAttempts: 3
        waitDuration: 100ms
        enableExponentialBackoff: true
        exponentialBackoffMultiplier: 2
        retryExceptions:
          - java.util.concurrent.TimeoutException
        ignoreExceptions:
          - io.github.resilience4j.bulkhead.BulkheadFullException
  bulkhead:
    bulkheadAspectOrder: 2
    instances:
      inventory:
        maxConcurrentCalls: 20
        maxWaitDuration: 0ms
  timelimiter:
    timeLimiterAspectOrder: 3
    instances:
      inventory:
        timeoutDuration: 800ms
        cancelRunningFuture: true
```

Under Spring's order rules, `1` has higher precedence than `2`, and `2` has higher precedence than `3`; therefore Retry is the outermost aspect in this example. Check which order properties are supported by your project's Resilience4j starter version and avoid using identical order values for aspects that need a deterministic order.

`maxAttempts: 3` includes the initial call plus up to two retries. Backoff increases by a factor of 2: expected wait intervals are 100 ms then 200 ms. `retryExceptions` permits retrying only the specified timeout. `BulkheadFullException` is ignored to avoid immediately retrying a rejection caused by exhausted capacity; immediate retries in that situation typically increase contention and load.

`maxConcurrentCalls: 20` caps concurrent calls via a semaphore bulkhead. `maxWaitDuration: 0ms` specifies not waiting for a permit when slots are full. `timeoutDuration: 800ms` caps the wait time for each asynchronous task wrapped by TimeLimiter. Tune this configuration to match dependency capacity and business deadlines.

## 5. Applying Annotations to Asynchronous Methods

Resilience4j's `@TimeLimiter` is designed for `Future`/`CompletionStage` and asynchronous types supported by the integration. The method below returns a `CompletableFuture`, uses a managed executor, and places all three annotations on the same Spring bean method:

```java
import io.github.resilience4j.bulkhead.annotation.Bulkhead;
import io.github.resilience4j.bulkhead.annotation.Bulkhead.Type;
import io.github.resilience4j.retry.annotation.Retry;
import io.github.resilience4j.timelimiter.annotation.TimeLimiter;
import org.springframework.stereotype.Service;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;

@Service
public class InventoryGateway {

    private final InventoryClient inventoryClient;
    private final Executor inventoryExecutor;

    public InventoryGateway(
            InventoryClient inventoryClient,
            Executor inventoryExecutor) {
        this.inventoryClient = inventoryClient;
        this.inventoryExecutor = inventoryExecutor;
    }

    @Retry(name = "inventory")
    @Bulkhead(name = "inventory", type = Type.SEMAPHORE)
    @TimeLimiter(name = "inventory")
    public CompletableFuture<InventoryResult> fetch(String sku) {
        return CompletableFuture.supplyAsync(
            () -> inventoryClient.fetch(sku),
            inventoryExecutor
        );
    }
}
```

The example assumes the Resilience4j version in use supports combining these aspects with `CompletableFuture` and a semaphore bulkhead. Use the appropriate Resilience4j Spring Boot starter, enable Spring AOP as required by the version, and configure a bounded executor. Do not call `CompletableFuture.supplyAsync(...)` omitting an executor in loaded applications because the common pool is not a dependency bulkhead limit.

If choosing `Bulkhead.Type.THREADPOOL`, configure a thread-pool bulkhead and a dedicated queue. Do not treat `THREADPOOL` and semaphore as the same mechanism: a semaphore limits the number of calls holding a permit; a thread-pool bulkhead isolates execution using a bounded pool and queue. Choose the type matching the dependency's execution model.

### For Synchronous Blocking Methods

If a method directly returns `InventoryResult` and calls a blocking HTTP client, `@Retry` and `@Bulkhead` can protect the synchronous call. However, do not assume `@TimeLimiter` will automatically offload an arbitrary blocking method onto an executor or interrupt a waiting thread. Set connect/response/read timeouts directly on the HTTP client. If TimeLimiter is needed, offload the task to a `Future`/`CompletionStage` using a bounded executor or use an asynchronous client API.

## 6. When Bulkhead Is Outside Retry

Another option is:

```text
Bulkhead
  └── Retry
        └── TimeLimiter
              └── Dependency call
```

In this setup, one permit is held across the entire retry sequence, including backoff wait time. This bounds the number of workflows currently handling the dependency, even while resting between attempts. It can be suitable when you want to cap total logical transactions or prevent too many workflows from retrying simultaneously.

The drawback is that permits stay occupied while no actual request is executing. If many workflows are waiting in backoff at once, the bulkhead can run out of permits and reject new requests even though the dependency is idle. This reduces throughput and increases `BulkheadFullException` errors.

| Criterion | Retry Outside Bulkhead | Bulkhead Outside Retry |
| --- | --- | --- |
| Permit scope | One permit per attempt | One permit for the entire retry sequence |
| Permit during backoff | Released before waiting | Still held |
| Impact on new requests | Permits can be reused between attempts | Fewer slots available while many workflows are in backoff |
| Suitable when | You want to limit concurrency of each dependency call | You want to limit concurrency of the whole workflow |

There is no single right order for every system. Identify which resource the Bulkhead is protecting: individual requests to the dependency or the overall business workflow.

## 7. When TimeLimiter Is Outside Retry

If TimeLimiter is the outermost aspect, the structure is:

```text
TimeLimiter
  └── Retry
        └── Bulkhead
              └── Dependency call
```

With an asynchronous method, an outermost TimeLimiter can bound completion time for the entire retry sequence. When the deadline expires, the caller receives a timeout even if Retry still has remaining attempts or backoff has not finished. This fits when business requirements impose a strict overall time budget.

In this structure, the outer TimeLimiter does not automatically enforce a per-attempt timeout on each dependency call. If one attempt can hang for a long time, you need an HTTP client timeout or a per-attempt limit inside the sequence. Do not rely solely on an overall deadline if underlying tasks do not respond to cancellation.

Comparing the two choices:

| Structure | Timeout Meaning | Consequence |
| --- | --- | --- |
| `Retry(Bulkhead(TimeLimiter(call)))` | Separate timeout per attempt | Total duration can exceed one timeout; an outer overall deadline is needed if an SLA applies |
| `TimeLimiter(Retry(Bulkhead(call)))` | Timeout for the entire retry sequence | Caps total caller wait time; a client or per-attempt timeout is needed if individual requests can hang |

Do not stack two TimeLimiters merely to "be safer" without defining which deadline each manages. If both per-attempt timeout and an overall deadline are required, configure one client timeout per network request and one overall deadline at the workflow layer; document both limits clearly.

## 8. Ordering Affects Which Errors Retry Observes

Retry should only repeat errors that are likely transient and safe to retry. When Bulkhead sits inside Retry, `BulkheadFullException` bubbles out of Bulkhead to Retry. If this error is not ignored, Retry can keep retrying while the system still lacks permits, adding load and delaying requests.

Similarly, if a circuit breaker is added to the chain, do not retry `CallNotPermittedException` when the breaker is `OPEN`. Retrying immediately does not make the dependency healthier and can create a rejection loop. Only retry selected timeouts or network errors, with a small attempt count and jittered backoff.

For commands with side effects, a timeout can occur after the dependency already executed the operation and the response was lost. Retrying commands is only safe when an idempotency key is durably enforced by the receiver. Never retry permanent business errors such as invalid data, permission denied, or disallowed state.

Fallbacks should be placed at a layer with clear responsibility, typically after retries are exhausted. Avoid declaring multiple fallbacks across aspects on the same method without understanding execution order; an inner fallback can convert an error into a success and prevent an outer Retry from seeing the error to retry.

## 9. AOP Only Applies When Calls Go Through a Spring Proxy

Resilience4j annotations are applied through Spring AOP. Therefore, the object must be Spring-managed and calls must go through the proxy. An internal call within the same instance like `this.fetch(sku)` normally does not go through the proxy, so aspects may not run.

Example structure prone to bypassing AOP:

```java
@Service
public class InventoryService {

    public InventoryResult load(String sku) {
        // Self-invocation: direct call within the same object.
        return fetchProtected(sku).join();
    }

    @Retry(name = "inventory")
    @Bulkhead(name = "inventory")
    @TimeLimiter(name = "inventory")
    public CompletableFuture<InventoryResult> fetchProtected(String sku) {
        // ...
    }
}
```

In this example, `load(...)` directly calls a method on the same object. Move the protected method to another Spring bean and inject that bean, or design call boundaries so requests pass through the proxy. Do not rely on `this` calls to trigger aspects.

## 10. Verifying Order with Integration Tests

Do not only test that the method returns the expected result. Test the behavioral consequences produced by aspect ordering:

1. **Attempt count:** configure `maxAttempts: 3`, make the dependency time out, and verify call count does not exceed three.
2. **Per-attempt permits:** hold the first request with a latch, verify the bulkhead hits its limit; after the request finishes and before the next attempt, check that the permit is released according to the chosen structure.
3. **Timeout:** make the dependency fail to complete and verify the caller receives a timeout according to the per-attempt limit or overall deadline.
4. **Backoff:** record timestamps between attempts to verify wait intervals and jitter within expected bounds.
5. **Ignored errors:** exhaust Bulkhead permits and verify Retry does not repeat `BulkheadFullException` if policy requires ignoring it.
6. **AOP proxy:** invoke through the injected Spring bean; avoid testing by instantiating the object with `new` when the goal is verifying aspects.

You can record milestone traces to inspect actual execution order:

```text
retry.attempt-1
bulkhead.acquire
timelimiter.start
dependency.start
timelimiter.timeout
bulkhead.release
retry.backoff
retry.attempt-2
bulkhead.acquire
timelimiter.start
dependency.start
dependency.complete
bulkhead.release
retry.complete
```

The trace above illustrates `Retry(Bulkhead(TimeLimiter(call)))`. If Bulkhead is outside Retry, there is only one `bulkhead.acquire` before the first attempt and `bulkhead.release` after all retries finish. If TimeLimiter is outside Retry, there is only one deadline start milestone for the whole sequence. Use counters, event listeners, or mocks at the dependency boundary to verify; do not deduce order solely from the line order of annotations.

## 11. Selection Guidelines

- Use `Retry → Bulkhead → TimeLimiter` when you want to cap each attempt, release permits during backoff, and apply a per-attempt timeout.
- Use `Bulkhead → Retry → TimeLimiter` when you want to cap the number of retrying workflows and accept holding permits during backoff.
- Use `TimeLimiter → Retry → Bulkhead` when you need an overall deadline for an async sequence; add client or per-attempt timeouts if individual network requests must also be bounded.
- Retry only transient errors, cap `maxAttempts`, use backoff/jitter, and ignore capacity rejections such as `BulkheadFullException` when retrying does not help.
- Use `@TimeLimiter` only with asynchronous return types supported by your integration; for blocking clients, configure timeouts on the client.
- Ensure calls pass through a Spring proxy and aspects use distinct, explicit order values.
- Test call counts, concurrency, wait durations, permits, and fallbacks to confirm the actual runtime structure.

Aspect ordering is part of your fault-tolerance policy. Choosing the right scope for each layer ensures Retry does not generate unnecessary repeated load, Bulkhead bounds the right resource, and TimeLimiter enforces deadlines in the right place. Explicit order configuration paired with integration tests keeps that behavior predictable and maintainable across Spring Boot or Resilience4j upgrades.
