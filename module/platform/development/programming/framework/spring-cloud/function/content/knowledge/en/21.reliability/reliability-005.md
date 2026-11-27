# Bounded Retries Using Adapter or Application Mechanisms

## 1. Lesson Objectives

In Spring Cloud Function, business logic can be built using `Supplier`, `Function`, and `Consumer`, registered in `FunctionCatalog`, composed into pipelines, and invoked via Java, HTTP, event-driven systems, or serverless platforms. In operation, database calls can time out, HTTP clients can resend requests, and brokers can redeliver messages. Without bounded retries—or when retrying at the wrong boundary—a system can amplify load, write duplicates, and obscure processing state.

In the **Reliability** chapter, **Bounded Retries Using Adapter or Application Mechanisms** explains how to design intentional retries without conflating each adapter's mechanisms.

After this lesson, you will be able to:

- Distinguish initial execution, retries, redeliveries, reinvocations, and Reactor resubscriptions.
- Identify which layer owns retries: application, HTTP client, Spring Cloud Stream binder, or serverless platform.
- Retry only potentially transient errors and know what to do when attempts are exhausted.
- Configure attempt counts, backoff, jitter, timeouts, deadlines, and retry budgets.
- Use Reactor's `retryWhen` on the right Publisher and the right error types.
- Avoid retrying an entire pipeline in ways that repeat already-committed side effects.
- Design idempotency keys, uniqueness constraints, and transactions in storage.
- Test attempt counts, final errors, side effects, and real adapter behavior.

> **Note:** Spring Cloud Function provides function contracts and composition; **it does not define a unified retry policy** across HTTP, messaging, or serverless. Concrete retry behavior depends on the application, adapter, binder, version, and deployment configuration.

## 2. What Is a Bounded Retry?

A **retry** re-invokes a failed operation in the expectation that the underlying cause may recover on its own. A reliable retry policy must answer:

1. **When to retry?** Filter by exception type or infrastructure signal.
2. **How many times?** Distinguish total `attempts` from `retries`.
3. **How long to wait?** Fixed delay, exponential backoff, jitter.
4. **What gets retried?** Only the DB call, or the whole `validate|price|save` chain?
5. **Is there enough time?** Deadlines, timeouts, and retry budgets.
6. **What when exhausted?** Propagate failure, return a response, route to DLQ/quarantine, or recover.
7. **Is re-execution safe?** Idempotency and commit state.

Example:

~~~text
Attempt 1 (initial)  → timeout
Wait 100 ms
Attempt 2 (retry #1) → timeout
Wait 200 ms
Attempt 3 (retry #2) → succeeds

Total: 3 attempts = 1 initial + 2 retries.
~~~

Configuration names can carry different semantics. For instance, `maxAttempts=3` in one system typically means *total attempts*, whereas Reactor's `Retry.max(2)` permits *two additional retries*. Never swap the two numbers without checking their meaning.

### 2.1. Retries, Redeliveries, and Resubscriptions Differ

| Concept | What Happens? | Who Controls It? |
|---|---|---|
| Local retry | Re-invokes a specific operation | Application/library |
| Reactor retry | Resubscribes to an upstream Publisher | `retry`/`retryWhen` |
| Broker redelivery | Message is delivered again after failure or missing ack | Broker/binder |
| Serverless reinvocation | Platform invokes the handler again | Trigger/cloud platform |
| HTTP resend | Client sends a new request after timeout | Client/SDK/user |

A consumer may attempt processing a message three times **within one delivery**, and the broker may still redeliver that message on the next round. An internal retry limit does not guarantee the message is seen at most three times system-wide.

## 3. Classify Errors Before Retrying

Retrying the same invalid input cannot fix a validation failure. Classify errors explicitly.

| Error Type | Example | Retry Same Input? | Reason |
|---|---|---|---|
| Invalid input | Quantity 0, malformed JSON | Usually no | Data does not change |
| Authorization | Missing permission | Usually no | Does not alter access rules |
| Conflict | Same key with different payload | Never blindly | Requires business resolution |
| Programming bug | Unexpected `NullPointerException` | Usually no | Repeating a bug still fails |
| Transient infrastructure | DB timeout, HTTP 503 | Conditionally | Service may recover |
| Rate limit | HTTP 429 | Conditionally | Respect `Retry-After` and bounds |
| Post-commit timeout | Lost DB write response | Only if idempotent | Write may already have succeeded |
| Client cancellation | Disconnected client | Not by default | Result may no longer be wanted |

These are guidelines, not immutable laws. An HTTP 404 might be transient in an eventually consistent system, yet should be retried only with solid business justification.

### 3.1. Do Not Treat Every Exception as Transient

~~~java
try {
    store.save(quote);
} catch (Exception ex) {
    // Wrong: retries regardless of cause and without bounds.
}
~~~

An exception can indicate invalid data, a unique-key conflict, a network timeout, or a bug. A storage adapter should classify **genuinely recoverable** infrastructure failures and preserve the cause. Never relabel every exception as "temporary" just to satisfy a retry filter.

## 4. Choose the Layer That Owns Retries

A request can cross multiple layers:

~~~text
HTTP client / SDK       (may retry)
         |
         v
HTTP adapter / gateway  (may time out)
         |
         v
Spring Cloud Function
validate → calculate → save
                          |
                          v
                  DB client (may retry)

Or another path:

Broker → Stream binder → Function → Store
Cloud trigger → Serverless adapter → Function → Store
~~~

Not every layer in the diagram exists in every request. Identify the actual execution path in use.

### 4.1. Application-Level Retry

The application can:

- Attach Reactor `retryWhen(...)` to a `Mono`/`Flux`.
- Use a wrapper retrying a specific I/O port.
- Configure an HTTP client/SDK to retry outbound requests.
- Use Spring Retry when the project has the right dependencies and setup.

The advantage is rich error semantics and scoping retries to a single operation. The risk is **nested retries** if the adapter retries too.

### 4.2. Adapter-Level Retry

The adapter or platform may manage retries/redeliveries:

- Spring Cloud Stream consumer bindings have per-binding retry policies.
- An HTTP client or gateway may resend requests.
- A serverless trigger may reinvoke the handler.
- A broker may redeliver unacknowledged messages.

The adapter understands delivery lifecycle, but may not know whether a DB write committed or that validation failures shouldn't be retried. Hence, propagate accurate error types, enforce idempotency, and test the transport layer.

### 4.3. Coordinating Multiple Layers

**Designate one primary retry owner per failure scope.** If two layers both retry, check the combined upper bound.

~~~text
HTTP client: max 3 attempts
DB wrapper: max 3 attempts per request

=> One logical request can cause up to 9 DB calls.
~~~

If broker redelivery or an outer retry sits on top, total executions multiply further. Real incidents may stop earlier, but design must account for the worst case.

## 5. Backoff, Jitter, Timeouts, and Deadlines

Aggressive retries can hammer an already overloaded dependency right when it is weakest.

| Strategy | Behavior | Trade-Off |
|---|---|---|
| Immediate retry | No wait | Easily causes load spikes |
| Fixed delay | Equal wait between tries | Simple, but can synchronize retries |
| Exponential backoff | Progressively longer waits | Reduces pressure during sustained outages |
| Backoff + jitter | Randomized variation around delay | Prevents synchronized retry herds |
| Server-directed | Honors `Retry-After` when suitable | Must still cap and validate delay |

Example exponential schedule:

~~~text
Retry #1: 100 ms
Retry #2: 200 ms
Retry #3: 400 ms
Retry #4: 800 ms
Cap growth at a ceiling, e.g. 2 seconds.
~~~

Jitter spreads actual wait times around the base schedule. Total processing duration also includes **each attempt's execution time**, not just backoff waits.

### 5.1. Bound by an Overall Deadline

If an invocation has 500 ms remaining before timeout while backoff reaches 2 seconds, retries cannot finish in time.

~~~text
Total duration ≈ attempt durations
               + total backoff waits
               + overhead/cleanup/response
~~~

Stop retries early enough before the deadline to send a response or ack and persist required state. An outer pipeline timeout may cancel the subscription, yet may not cancel an already-committed blocking side effect.

### 5.2. Retry Storms and Retry Budgets

Thousands of requests each retrying three times still multiply traffic severalfold. Backoff and jitter are only part of the solution. When needed, combine rate limits, concurrency limits, circuit breakers, retry budgets, and alerts on retry-to-originating-request ratios.

**Retry budgets must be evaluated system-wide**, not just inside one Java method.

## 6. Running Example: Quoting and the Persistence Boundary

We build a pipeline that receives an order request, validates it, computes a quote, and saves it. Data is split into pre- and post-validation types.

~~~java
package example.functions;

public final class OrderModels {

    private OrderModels() {}

    public record OrderRequest(
            String orderId,
            Integer quantity) {}

    public record ValidatedOrder(
            String orderId,
            int quantity) {}

    public record Quote(
            String orderId,
            int quantity,
            long totalVnd) {}
}
~~~

Example rules:

- `orderId` has the form `ORD-<digits>`, e.g., `ORD-42`.
- `quantity` is an integer in 1..100.
- Fixed unit price is 125,000 VND.
- Writing the same `orderId` with the same result **does not create a second record**.
- Same `orderId` with different content is a conflict.
- Validation failures are never retried; transient storage failures allow bounded retries.

~~~text
OrderRequest
     |
     v
validateOrder          (pure, input errors not retried)
     |
     v
calculateQuote         (pure, no DB writes)
     |
     v
saveQuote              (side effect, may be transient)
     |
     v
Complete or report error to adapter
~~~

### 6.1. Three Application Exception Types

~~~java
package example.functions;

public final class OrderErrors {

    private OrderErrors() {}

    public static class InvalidOrderException
            extends RuntimeException {
        public InvalidOrderException(String message) {
            super(message);
        }
    }

    public static class QuoteConflictException
            extends RuntimeException {
        public QuoteConflictException(String message) {
            super(message);
        }
    }

    public static class TransientStoreException
            extends RuntimeException {
        public TransientStoreException(
                String message, Throwable cause) {
            super(message, cause);
        }
    }
}
~~~

These types express intent rather than wrapping every failure indiscriminately. A JDBC/JPA adapter must translate only failures **classified as transient** into `TransientStoreException`, keeping data conflicts as their own type.

## 7. Pure Functions and the Write Port

Register the two computation Functions:

~~~java
package example.functions;

import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import example.functions.OrderModels.OrderRequest;
import example.functions.OrderModels.ValidatedOrder;
import example.functions.OrderModels.Quote;
import example.functions.OrderErrors.InvalidOrderException;

@Configuration
public class QuoteFunctions {

    @Bean
    public Function<OrderRequest, ValidatedOrder> validateOrder() {
        return input -> {
            if (input == null
                    || input.orderId() == null
                    || !input.orderId().matches("ORD-[0-9]+")
                    || input.quantity() == null
                    || input.quantity() < 1
                    || input.quantity() > 100) {
                throw new InvalidOrderException(
                        "Invalid OrderRequest");
            }

            return new ValidatedOrder(
                    input.orderId(), input.quantity());
        };
    }

    @Bean
    public Function<ValidatedOrder, Quote> calculateQuote() {
        return order -> new Quote(
                order.orderId(),
                order.quantity(),
                Math.multiplyExact(
                    (long) order.quantity(), 125_000L));
    }
}
~~~

These Functions have no dependency on a database, broker, HTTP, or scheduler. Given identical input, they return identical results or reject by the same rules.

Write port:

~~~java
package example.functions;

import example.functions.OrderModels.Quote;

public interface QuoteStore {
    void save(Quote quote);
}
~~~

Register a trailing Consumer when using composition:

~~~java
package example.functions;

import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import example.functions.OrderModels.Quote;

@Configuration
public class QuoteSinkFunctions {

    @Bean
    public Consumer<Quote> saveQuote(QuoteStore store) {
        return store::save;
    }
}
~~~

### 7.1. In-Memory Deduplicating Store for Study/Testing

~~~java
package example.functions;

import java.util.concurrent.ConcurrentHashMap;

import org.springframework.stereotype.Component;

import example.functions.OrderModels.Quote;
import example.functions.OrderErrors.QuoteConflictException;

@Component
public class InMemoryQuoteStore implements QuoteStore {

    private final ConcurrentHashMap<String, Quote> entries =
            new ConcurrentHashMap<>();

    @Override
    public void save(Quote quote) {
        if (quote == null || quote.orderId() == null) {
            throw new IllegalArgumentException(
                    "Invalid Quote");
        }

        Quote old = entries.putIfAbsent(
                quote.orderId(), quote);

        if (old != null && !old.equals(quote)) {
            throw new QuoteConflictException(
                    "Same orderId with different quotes");
        }
    }

    public Quote find(String orderId) {
        return entries.get(orderId);
    }

    public int size() {
        return entries.size();
    }

    public void clear() {
        entries.clear();
    }
}
~~~

`putIfAbsent` is atomic within **one JVM**, but is not durable and does not span multiple replicas. Production requires unique constraints, atomic upserts, or transactions backed by real storage. The example does not claim "exactly-once" semantics.

### 7.2. Rewriting the Same Quote vs. Reusing an Existing ID

| Request | In-Memory Result |
|---|---|
| `ORD-42`, quantity 2 (first time) | Saves one Quote |
| Repeat `ORD-42`, quantity 2 | Does not create a second record |
| `ORD-42`, quantity 3 | Conflict, never silently overwrites |
| `ORD-43`, quantity 2 | Creates another Quote |

This is an illustrative idempotency rule. If a real application permits order updates, define a **distinct version or update operation** instead of treating modifications as replays.

## 8. Composing Logic with FunctionCatalog

Look up the computation portion through Spring Cloud Function:

~~~java
package example.functions;

import java.util.function.Function;

import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.stereotype.Service;

import example.functions.OrderModels.OrderRequest;
import example.functions.OrderModels.Quote;

@Service
public class QuotePreviewService {

    private final FunctionCatalog catalog;

    public QuotePreviewService(FunctionCatalog catalog) {
        this.catalog = catalog;
    }

    public Quote preview(OrderRequest request) {
        Function<OrderRequest, Quote> pipeline = catalog.lookup(
                "validateOrder|calculateQuote");

        if (pipeline == null) {
            throw new IllegalStateException(
                    "Missing quote pipeline");
        }

        return pipeline.apply(request);
    }
}
~~~

The expression `validateOrder|calculateQuote` has contract `Function<OrderRequest,Quote>`. It is the reusable business core across HTTP, messaging, or serverless.

To append `saveQuote`:

~~~java
import java.util.function.Consumer;

Consumer<OrderModels.OrderRequest> record =
        catalog.lookup("validateOrder|calculateQuote|saveQuote");

if (record == null) {
    throw new IllegalStateException("Missing record pipeline");
}

record.accept(new OrderModels.OrderRequest("ORD-42", 2));
~~~

The snippet shows looking it up inside a method with an injected `FunctionCatalog catalog`. Since the trailing Consumer returns nothing, the overall contract is `Consumer<OrderRequest>`.

**No retries exist simply because `validateOrder|calculateQuote|saveQuote` was composed.** `FunctionCatalog` does not configure attempt counts, backoff, or DLQs.

### 8.1. Pipeline Selection Config Is Not Retry Config

~~~yaml
spring:
  cloud:
    function:
      definition: "validateOrder|calculateQuote|saveQuote"
~~~

`spring.cloud.function.definition` selects which function or composition an adapter exposes. It does not create HTTP endpoints, broker destinations, polling schedules, or retry policies. Each adapter has its own mechanisms and must be tested on the real version in use.

## 9. Application-Level Retry with Reactor

If `QuoteStore.save` may perform blocking I/O, use `Mono.fromRunnable` to defer execution and `Schedulers.boundedElastic()` to avoid blocking an event loop.

~~~java
package example.functions;

import java.time.Duration;

import org.springframework.stereotype.Service;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.util.retry.Retry;

import example.functions.OrderModels.Quote;
import example.functions.OrderErrors.TransientStoreException;

@Service
public class QuoteWriter {

    private final QuoteStore store;

    public QuoteWriter(QuoteStore store) {
        this.store = store;
    }

    public Mono<Void> saveWithRetry(Quote quote) {
        return Mono.<Void>fromRunnable(() -> store.save(quote))
                .subscribeOn(Schedulers.boundedElastic())
                .retryWhen(
                    Retry.backoff(2, Duration.ofMillis(100))
                        .maxBackoff(Duration.ofSeconds(1))
                        .jitter(0.5)
                        .filter(error ->
                            error instanceof TransientStoreException));
    }
}
~~~

Breakdown:

- `Mono.fromRunnable` defers calling `store.save` until subscription.
- `subscribeOn(boundedElastic)` isolates blocking I/O; **it does not turn a blocking client into a non-blocking one**.
- `Retry.backoff(2, ...)` allows at most **two additional retries**, meaning up to three attempts per subscription if all fail.
- `maxBackoff` caps the wait interval; `jitter(0.5)` adds randomness to avoid synchronized retries.
- `filter` retries only `TransientStoreException`. `InvalidOrderException` and `QuoteConflictException` are not retried by this policy.
- Once attempts are exhausted, Reactor emits a terminal error; the final exception type may be a retry-exhausted wrapper depending on policy/version. If a specific error contract is required, configure unwrapping/conversion explicitly and test it.

`Mono<Void>` emits `onComplete` when saving succeeds, or `onError` on failure; it emits no Quote value. Adapters consuming the Publisher must await completion or observe errors per contract—never treat creating the Mono as having saved the data.

### 9.1. Retry Only the Save Call, Not Validation

Compose the core first, then invoke `QuoteWriter`:

~~~java
package example.functions;

import java.util.function.Function;

import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.stereotype.Service;

import reactor.core.publisher.Mono;

import example.functions.OrderModels.OrderRequest;
import example.functions.OrderModels.Quote;

@Service
public class QuoteWorkflow {

    private final FunctionCatalog catalog;
    private final QuoteWriter writer;

    public QuoteWorkflow(
            FunctionCatalog catalog,
            QuoteWriter writer) {
        this.catalog = catalog;
        this.writer = writer;
    }

    public Mono<Quote> process(OrderRequest request) {
        Function<OrderRequest, Quote> core = catalog.lookup(
                "validateOrder|calculateQuote");

        if (core == null) {
            throw new IllegalStateException(
                    "Missing quote pipeline");
        }

        // Synchronous validation/calculation runs before creating the write Mono.
        Quote quote = core.apply(request);

        return writer.saveWithRetry(quote)
                .thenReturn(quote);
    }
}
~~~

With this code, `process(invalidInput)` throws `InvalidOrderException` immediately, before invoking the writer. For valid input, it returns `Mono<Quote>`; saving and scoped retries on `save` begin only when subscribed.

Having a `Mono`-returning service throw validation synchronously can be a valid choice if documented. If you want **all failures to flow through `onError`**, defer the core step explicitly; see the next section.

### 9.2. Unifying Reactive Errors with defer When Needed

~~~java
public Mono<Quote> processDeferred(OrderRequest request) {
    return Mono.defer(() -> {
        Function<OrderRequest, Quote> core = catalog.lookup(
                "validateOrder|calculateQuote");

        if (core == null) {
            return Mono.error(
                    new IllegalStateException(
                        "Missing quote pipeline"));
        }

        Quote quote = core.apply(request);
        return writer.saveWithRetry(quote).thenReturn(quote);
    });
}
~~~

Place this method inside `QuoteWorkflow` where `catalog` and `writer` are declared. Inside `defer`, if `core.apply` throws a regular exception, Reactor emits it as `onError` upon subscription.

**Watch retry scope:** `writer.saveWithRetry(quote)` retries only the write, but if a caller attaches `.retryWhen(...)` **outside `processDeferred`**, everything inside `defer` can run again—including lookup, validation, and calculation. If the core has hidden side effects, outcomes become even harder to predict.

## 10. Errors in the apply Phase vs. the subscribe Phase

In imperative Java:

~~~java
Function<OrderModels.OrderRequest, OrderModels.Quote> core =
        new QuoteFunctions().validateOrder()
            .andThen(new QuoteFunctions().calculateQuote());

core.apply(new OrderModels.OrderRequest("ORD-42", 0));
// Throws InvalidOrderException immediately.
~~~

In Reactor:

~~~java
Mono<OrderModels.Quote> deferred = Mono.fromCallable(
        () -> core.apply(
            new OrderModels.OrderRequest("ORD-42", 0)));
~~~

Errors inside the `Callable` typically surface as `onError` at subscription time. Contrast that with:

~~~java
Mono<OrderModels.Quote> eager = Mono.just(
        core.apply(new OrderModels.OrderRequest("ORD-42", 0)));
~~~

In the `eager` version, Java evaluates `core.apply(...)` before calling `Mono.just`, so the exception can occur **immediately at assembly**.

To place retries accurately, you must know whether failures happen inside the Publisher or **before the Publisher is created**. You cannot attach `retryWhen` to a Publisher that was never returned because the call threw directly.

## 11. When Retries Are Exhausted

Never swallow the error after the final attempt:

~~~java
try {
    // Perform the save call
} catch (Exception ignored) {
    // Wrong: caller thinks it succeeded even though saving did not finish.
}
~~~

In Reactor, once `retryWhen` stops permitting retries, the Publisher must emit a terminal error (or convert to an outcome **permitted by business rules**). Never assume `onErrorReturn(quote)` implies the Quote was saved successfully.

### 11.1. Classifying the Final Error

| Final Error | Appropriate Application Action |
|---|---|
| Validation | Reject input; do not retry |
| Conflict | Report conflict; do not overwrite |
| Storage transient exhausted | Report temporary unavailability, or hand off to durable work |
| Unknown commit | Look up by idempotency key; do not assume unwritten |
| Programming bug | Record and fix code; do not mask with fake fallback |

If you need to propagate the original error after Reactor exhausts retries, configure `onRetryExhaustedThrow(...)` on `RetrySpec` when supported by your version, preserving `cause` and testing the error contract. Never rely solely on parsing exception message text to distinguish a timeout from validation.

## 12. Per-Item Retry or Whole-Flux Retry?

In a reactive pipeline processing multiple events, `retryWhen` placement determines **which elements get reprocessed**.

### 12.1. An Outer Retry Can Re-Emit Prior Elements

~~~java
import reactor.core.publisher.Flux;

Flux<Integer> parsed = Flux.just("1", "bad", "3")
        .map(Integer::parseInt)
        .retry(1);
~~~

A subscriber may observe:

~~~text
onNext(1)
onNext(1)
onError(NumberFormatException)
~~~

Because `retry(1)` resubscribes to the entire upstream, `1` is emitted twice. Default retry has no memory of "already processed the first element."

If `doOnNext(store::save)` sits after `map`, side effects for items before the failing element can repeat too. Business data requires idempotency and clear scope boundaries.

### 12.2. Retry Only Each Element's Async Operation

Suppose each message invokes an independent remote service:

~~~java
import java.time.Duration;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

Flux<String> responses = Flux.just("ORD-1", "ORD-2")
        .concatMap(orderId ->
            remoteService.fetch(orderId)
                .retryWhen(
                    Retry.backoff(2, Duration.ofMillis(100))
                        .filter(error ->
                            error instanceof TransientRemoteException)));
~~~

`remoteService.fetch` is an assumed port returning `Mono<String>`; `TransientRemoteException` is an exception classified as transient by the adapter. A real application provides those dependencies.

With this structure, retrying `ORD-2` happens **inside the inner Mono** for `ORD-2`, rather than automatically re-emitting `ORD-1`'s result. Still, if an inner Mono fails after exhausting retries without per-item error handling, the outer Flux normally terminates with `onError`. To keep independent messages moving, add per-inner error handling.

### 12.3. Isolating One Message's Failure Does Not Mean Silently Dropping It

~~~java
Flux<String> responses = Flux.just("ORD-1", "ORD-2")
        .concatMap(orderId ->
            remoteService.fetch(orderId)
                .retryWhen(
                    Retry.max(2).filter(error ->
                        error instanceof TransientRemoteException))
                .onErrorResume(error -> {
                    // Illustrative only; production must record/observe the failure.
                    return Mono.empty();
                }));
~~~

Here, post-retry failure becomes an empty inner Mono so the Flux can continue to subsequent items. That is valid only when the system permits **emitting no output** for a failed message and already handles quarantine, metrics, or DLQ routing. Never assume returning `Mono.empty()` tells a broker to send the message to a dead-letter queue.

### 12.4. flatMap, concatMap, and Concurrency

- `concatMap` processes inner Publishers sequentially, making sequential side effects easier to reason about.
- `flatMap` runs inner Publishers concurrently; cap concurrency and mind output ordering.
- `flatMapSequential` runs concurrently while emitting in source order, at the cost of buffering.
- With retries inside each inner Publisher, total dependency requests scale with concurrency.

Pick operators based on ordering requirements, load, and business semantics—not just to "catch errors."

## 13. Spring Cloud Stream: Retries at the Consumer Binding

When using Spring Cloud Function with Spring Cloud Stream, a `Consumer<OrderRequest>` can bind to a message source. Depending on the binder and version, Spring Cloud Stream provides **consumer retries** at the binding layer for imperative paths.

To illustrate **binder-owned retries**, use a synchronous Consumer that calls the core and write port without wrapping its own retries:

~~~java
package example.functions;

import java.util.function.Consumer;
import java.util.function.Function;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import example.functions.OrderModels.OrderRequest;
import example.functions.OrderModels.ValidatedOrder;
import example.functions.OrderModels.Quote;

@Configuration
public class StreamOrderHandler {

    @Bean
    public Consumer<OrderRequest> processOrder(
            @Qualifier("validateOrder")
            Function<OrderRequest, ValidatedOrder> validate,
            @Qualifier("calculateQuote")
            Function<ValidatedOrder, Quote> calculate,
            QuoteStore store) {

        return request -> {
            ValidatedOrder valid = validate.apply(request);
            Quote quote = calculate.apply(valid);
            store.save(quote);
        };
    }
}
~~~

A synchronous Consumer returns only after those calls complete or throw. That gives the binder a chance to observe the invocation outcome under the imperative consumer contract.

### 13.1. Configuring max-attempts per Binding

Illustrative YAML following Spring Cloud Stream 4.x conventions:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders
          group: quote-service
          consumer:
            max-attempts: 3
            back-off-initial-interval: 1000
            back-off-max-interval: 5000
            back-off-multiplier: 2.0
~~~

Explanation:

- `processOrder-in-0` is the functional input binding name for bean `processOrder`.
- `max-attempts: 3` specifies at most three processing attempts within the applied consumer retry mechanism, including the initial attempt and retries.
- `back-off-*` properties configure delay intervals and multiplier for that mechanism.
- `group` matters for the binder's subscriber/consumer-group semantics, though it is not a database deduplication mechanism.

**Verify on your actual binder and version:** Certain binders, reactive Function types, custom retry/error-handler setups, or error behaviors may use different mechanisms, ignore specific shared properties, or require binder-specific settings. This YAML snippet is not a guarantee that every broker executes the exact same schedule.

### 13.2. Do Not Enable Both Binder and Consumer Retries Unplanned

If the binder executes up to 3 attempts and `processOrder` calls `store.save` with 3 internal attempts, one message can trigger up to 9 storage calls before the binder gives up.

In many designs, **choosing one primary layer** makes sense:

- Binder-level retries across the whole consumer when the operation is short, idempotent, and errors are classified properly.
- Application-level retries **around a single dependency** when rich error filtering is needed and repeating the entire Function is undesirable.
- Combining both layers only when total attempt budgets, ambiguous commits, and separated metrics are explicitly accounted for.

### 13.3. Binder Retry Is Not Broker Redelivery

After the binder exhausts attempts, what happens next depends on error handling and the broker:

- Failures may route to an error channel or handler.
- Some binders support dead-letter topics/queues when explicitly configured.
- Messages may be requeued/redelivered or handled by another policy.
- Ack/nack behavior depends on the binder and consumer style.

Never read `max-attempts: 3` as "guaranteed at most three executions over the message's entire lifetime" or "guaranteed DLQ after three tries."

## 14. Dead-Letter Queues and Poison Messages After Exhaustion

A **poison message** consistently fails with the same data, such as a bad schema or `quantity=0`. If an adapter retries indefinitely, it wastes resources and can stall other messages.

~~~text
Broker
  |
  v
Deserialize
  |
  +-- invalid schema ------------> reject / quarantine / DLQ
  |
  v
Validate
  |
  +-- invalid business input ----> reject / quarantine / DLQ
  |
  v
Persist
  |
  +-- transient failure
          |
          v
      limited attempts
          |
          +-- succeeds ----------> ack per binder
          |
          +-- exhausted ---------> error policy / DLQ / alert
~~~

Decide explicitly:

1. May invalid messages be discarded?
2. Must failures go to a DLQ/quarantine for manual replay?
3. When transient storage failures exhaust attempts, should the message be requeued or sent to an error queue?
4. Are message IDs, correlation IDs, and diagnostic context preserved?
5. When replaying from the DLQ, how do you prevent duplicates for messages that already committed?

Spring Cloud Function does not define DLQs directly. DLQ settings, retry error handlers, and acks depend on **the specific binder**; never invent a generic property and assume it works everywhere.

### 14.1. Bad Payloads Can Fail Before the Function Runs

If JSON fails to deserialize into `OrderRequest`, the error can occur **in the converter** before `validateOrder` is invoked. Exception filters inside `QuoteWriter` cannot handle that error. The adapter layer needs a dedicated strategy for conversion errors.

### 14.2. Reactive Functions and Consumer Retries

With `Function<Flux<T>,Flux<R>>` or `Consumer<Flux<T>>`, subscriptions and error signals may be managed differently than in a synchronous Consumer. Do not assume imperative binding retry settings automatically cover every post-subscription error.

When using reactive Functions, verify:

- Who subscribes to the source?
- Does `onError` reach the binder?
- Do retries apply per element, to the whole Flux, or to the entire message delivery?
- What backpressure, buffering, and redelivery behaviors arise?
- When do acks/errors happen relative to side effects?

If a Consumer calls `subscribe()` itself and immediately returns from `accept(...)`, the binder may miss the final async outcome. Never treat this pattern as retry/ack-safe without verifying the adapter contract.

## 15. HTTP: Client Retries vs. Server Retries

In HTTP systems, both sides carry different responsibilities:

- **HTTP server/adapter** receives requests, calls the Function, handles results/errors, and sends responses.
- **HTTP client/SDK** may automatically resend requests on timeouts, connection drops, or retryable status codes.
- **Server-side application** may retry outbound calls to dependencies, yet should not blindly rerun entire business requests without idempotency.

### 15.1. A Timeout Does Not Prove the Server Did Nothing

~~~text
Client --- POST /quotes ---> Server
                              |
                              v
                          save DB (commit)
                              |
                   Response lost on network
                              |
Client sees timeout and retries POST /quotes
~~~

If the second request inserts a second record, the system is broken even though the first request succeeded.

For side-effecting APIs, use a **stable idempotency key** across resends—such as `orderId` or an API-defined header. The server must check key and payload inside storage capable of enforcing uniqueness.

### 15.2. When Should an HTTP Client Retry?

| Situation | Handling Guidance |
|---|---|
| Cannot connect to server | Bounded retry may be appropriate |
| HTTP 503/502/504 | Retry per policy and deadline |
| HTTP 429 | Honor `Retry-After` if valid and within budget |
| HTTP 400 from validation | Do not retry the same payload |
| HTTP 401/403 | Never use retries to bypass security |
| HTTP 409 conflict | Never retry blindly |
| POST wrote data but response lost | Safe to resend only with idempotency |

HTTP method alone does not replace domain understanding. `GET` is normally designed to be safe and idempotent, whereas side-effecting `POST` calls demand extra care. A client may retry even if the server configures no retry policy at all.

### 15.3. Spring Cloud Function Web Adapter Is Not an HTTP Client

`spring.cloud.function.definition` selects the exposed Function; it does not configure HTTP client retries or guarantee specific response statuses. When using `WebClient`, `RestClient`, or another SDK for outbound calls, configure retries **on that client** per its version and request semantics—do not confuse it with `FunctionCatalog`.

## 16. Serverless: Trigger Retries and Invocation Limits

A serverless platform may reinvoke a function when an invocation fails or times out, yet **policies vary across trigger types**.

~~~text
Cloud event / queue / HTTP
          |
          v
Serverless adapter
          |
          v
validate → calculate → save
          |
          +-- error → trigger-specific retry / DLQ / failure policy
~~~

Scenarios to account for:

- Invocations may replay with the same event ID.
- Code may run on a fresh instance, making in-memory caches/deduplication unreliable.
- A DB write may already have committed before an invocation timed out.
- Each invocation has platform-enforced deadlines and concurrency limits.
- A handler may be triggered via synchronous HTTP or an asynchronous queue, with different retry policies.

Never configure a `Retry.backoff` longer than the remaining invocation time. If 300 ms remain and one backoff waits 1 second, local retries merely waste time or trigger a timeout.

### 16.1. Application Config Does Not Replace Trigger Config

Spring Cloud Function adapters map events/payloads to beans. Cloud retry counts, timeouts, dead-letter destinations, and failure reporting belong to trigger/platform configuration.

Test **the exact trigger type in use** rather than assuming "serverless always retries three times" or "serverless never retries."

### 16.2. Platform Reinvocations Can Exceed Java Retries

If the application attempts up to 3 DB writes and the platform reinvokes the same event twice more, one logical request can trigger many write attempts. Exact counts depend on error handling and trigger settings; deduplication must tolerate events replaying after timeouts.

## 17. Supplier, Function, and Consumer: Retry Placement Differs

Spring Cloud Function supports composing multiple shapes:

~~~text
Supplier<T> → Function<T,R> ⇒ Supplier<R>
Function<T,R> → Consumer<R> ⇒ Consumer<T>
Supplier<T> → Consumer<T> ⇒ Runnable
~~~

These contracts describe composition structure. Actual adaptation and triggering across adapters must be verified per version.

### 17.1. Do Not Retry a Supplier Blindly If Each get Fetches a New Event

~~~java
import java.util.function.Supplier;

Supplier<OrderModels.OrderRequest> next =
        () -> queueClient.poll();
~~~

`queueClient` is an illustrative dependency. If every `get()` pulls **a different message**, retrying the whole `Supplier|get|process` flow can pull a new message instead of retrying the failed one.

When processing an item fails, retain a stable ID and payload alongside the source's ack/requeue mechanism. Never assume `Supplier.get()` always returns the same item.

### 17.2. A Consumer Returning void Does Not Mean All Side Effects Finished

~~~java
import java.util.function.Consumer;

Consumer<OrderModels.Quote> save =
        quote -> quoteStore.save(quote);
~~~

If `quoteStore.save` is synchronous, `accept` returns after the call completes or throws. If the Consumer launches async work and returns immediately, the adapter may never observe eventual failures.

Choose Function signatures and subscription/ack lifecycles properly. Never assume a self-subscribing `Consumer<Flux<T>>` gives safe retry semantics.

### 17.3. Composition Does Not Create Retries Automatically

`FunctionCatalog.lookup("validateOrder|calculateQuote|saveQuote")` defines **execution order**, not attempt counts. If the adapter manages retries for the chain, ensure exceptions/error signals reach the adapter cleanly; if the application retries `saveQuote`, prevent the adapter from repeating the whole operation beyond budget.

## 18. Idempotency Is a Prerequisite for Safe Retries

A pure computation can rerun without altering storage. A write or event publish is different: repeating the same request creates extra side effects unless guarded.

### 18.1. Defining Idempotency for Business Operations

In request/event processing, **idempotency** usually means: resending **the same request** with **the same identifier** produces no further business effect beyond the first successful execution.

Example:

~~~text
Request: orderId=ORD-42, quantity=2

Attempt 1: saves Quote(ORD-42,2,250000)
Attempt 2: recognizes same orderId and same payload
        → returns/completes as already processed, no second record

Different request: orderId=ORD-42, quantity=3
        → conflict, never silently treated as a replay of the first
~~~

Purity and idempotency are not identical. `calculateQuote` is pure even though `f(f(x))` is meaningless; `saveQuote` is impure yet can be idempotent when storage enforces uniqueness and compares payloads.

### 18.2. Keys Must Stay Stable Across Attempts

An HTTP `POST` may use `Idempotency-Key` or a business-managed `orderId`. An event may use `eventId` plus processing version. Essential requirements:

- The same request **keeps the same key** across client retries, broker redeliveries, and serverless reinvocations.
- Keys must never be regenerated randomly on each retry.
- Keys must be scoped adequately to avoid collisions across tenants or operations when needed.
- Storage must distinguish **same key, same content** from **same key, different content**.
- Keys do not replace authorization or input-origin verification.

If a system supports multiple operation types, `orderId` alone may be insufficient; combine operation type/version or use an appropriately scoped request ID.

### 18.3. Unique Constraints Beat SELECT-Then-INSERT

Suppose two concurrent workers run:

~~~text
Worker A: SELECT ... WHERE order_id='ORD-42' → not found
Worker B: SELECT ... WHERE order_id='ORD-42' → not found
Worker A: INSERT → succeeds
Worker B: INSERT → can write a duplicate if storage does not constrain it
~~~

Checking before writing does not prevent race conditions. Databases should enforce uniqueness with indexes/constraints and atomic writes inside proper transactions.

Conceptual SQL example (exact syntax depends on the database):

~~~sql
CREATE TABLE quote (
    order_id VARCHAR(64) PRIMARY KEY,
    quantity INTEGER NOT NULL,
    total_vnd BIGINT NOT NULL
);
~~~

Having a primary key blocks duplicate rows for the same `order_id`, yet implementations must still handle existing rows:

- If payloads match identically, treat as a successful replay.
- If payloads differ, report a conflict.
- If a write reports a timeout, **query by key** when state confirmation is needed.

### 18.4. Idempotency Does Not Make Every Side Effect Exactly-Once

A Consumer may write idempotently to a DB while also sending an email, charging a card, or publishing an event. Each side effect has its own "once" semantics.

Example:

~~~text
DB Quote write: idempotent
Notification email: may still send twice on retry
Published message: may be emitted again
~~~

When an entire multi-step workflow must be reliable, manage email/event boundaries separately with deduplication, an outbox, or appropriate orchestration.

## 19. Transactional Outbox When Writing DB and Publishing Events

Consider the workflow:

~~~text
validate → calculate → save Quote (COMMIT) → publish QuoteCreated
~~~

If the process crashes after commit yet before publishing, the database holds the record while downstream never hears about it. Retrying the whole pipeline may keep the DB write safe via idempotency, while event publishing still risks missing or duplicating events.

A common pattern:

~~~text
Inside the same DB transaction:
    - UPSERT/INSERT Quote by key
    - INSERT OutboxEvent(quoteId,eventId,payload)
COMMIT
           |
           v
Outbox publisher reads unsent events
           |
           v
Broker
           |
           v
Downstream consumer deduplicates by eventId
~~~

The outbox ties publishing intent to the business commit. A publishing worker can retry on timeouts. Since brokers/downstream can still deliver duplicates, **receiving consumers** need idempotency where appropriate.

### 19.1. Outbox Retries Differ from Business Pipeline Retries

If publishing from the outbox fails, do not re-invoke `validateOrder|calculateQuote|saveQuote` by default. Retry only outbox publishing per policy, since business data already committed.

This illustrates why splitting pipelines into clear responsibility boundaries beats stuffing every side effect into one Function with a trailing retry.

## 20. Retries with Timeouts, Circuit Breakers, and Concurrency Limits

Retries cannot replace timeouts. A single hanging attempt keeps a "retry up to three times" policy from ever reaching attempt two.

### 20.1. Each Attempt Needs Its Own Timeout Where Appropriate

~~~text
Attempt #1: wait at most 500 ms
Backoff: 100 ms
Attempt #2: wait at most 500 ms
Backoff: 200 ms
Attempt #3: wait at most 500 ms

Leave enough budget for response/ack.
~~~

Maximum total duration depends on implementations, schedulers, cancellation, and overhead. A timeout on a Publisher may not immediately abort an in-flight blocking JDBC call; verify driver/client timeout support and connection lifecycle.

### 20.2. Ordering of Reactor timeout and retry

These two operator orderings have different meanings:

~~~java
Mono<String> a = remoteCall
        .timeout(Duration.ofMillis(500))
        .retryWhen(retryPolicy);

Mono<String> b = remoteCall
        .retryWhen(retryPolicy)
        .timeout(Duration.ofMillis(500));
~~~

Here `remoteCall` is a dependency `Mono<String>` and `retryPolicy` is a configured `Retry`. In `a`, `timeout` sits upstream of `retryWhen` and typically applies **per attempt**. In `b`, `timeout` wraps the entire sequence including retries and backoff delays.

Define the intended semantics clearly. A design may combine a **per-attempt timeout** with an **outer overall deadline**, while carefully controlling ordering and final error types.

### 20.3. Circuit Breakers and Rate Limits

When a dependency fails broadly, retries can worsen overload. A circuit breaker fails fast while a dependency is unhealthy; rate and concurrency limits cap simultaneous requests within capacity.

When a circuit breaker is open, do not immediately retry multiple times against the same fast-fail rejection. Policies should consider circuit-open exceptions, total deadlines, and system budgets. These mechanisms typically live in HTTP clients or I/O adapters, not inside every pure Function.

## 21. Configuring Retries in Imperative Java Applications

Not every project uses Reactor. When persistence is synchronous and the project intentionally uses Spring Retry, you can configure a `RetryTemplate` around a specific call.

> The example below requires compatible Spring Retry dependencies (for example `org.springframework.retry:spring-retry`, plus AOP dependencies if using annotations). Builder APIs can vary by version; verify against your project.

~~~java
package example.functions;

import org.springframework.retry.support.RetryTemplate;
import org.springframework.stereotype.Service;

import example.functions.OrderModels.Quote;
import example.functions.OrderErrors.TransientStoreException;

@Service
public class BlockingQuoteWriter {

    private final QuoteStore store;
    private final RetryTemplate retry;

    public BlockingQuoteWriter(QuoteStore store) {
        this.store = store;

        this.retry = RetryTemplate.builder()
                .maxAttempts(3)
                .exponentialBackoff(100, 2.0, 1000)
                .retryOn(TransientStoreException.class)
                .build();
    }

    public void save(Quote quote) {
        retry.execute(context -> {
            store.save(quote);
            return null;
        });
    }
}
~~~

Here `maxAttempts(3)` denotes total attempts including the initial call. `retryOn` permits retries only for the selected exception class. All other errors propagate normally.

**Never call this blocking wrapper on an event loop** if it waits on backoff and executes blocking JDBC. In reactive applications, use proper I/O/scheduler boundaries or genuinely reactive clients.

### 21.1. Avoid Retrying in Both a Proxy and Inside the Method

If `@Retryable` also wraps the same operation via a Spring Retry AOP proxy, one call can receive double retries. Conversely, internal `this.someMethod()` calls may bypass proxies depending on AOP setup, causing retries not to run as expected.

Keep **one observable policy**, test attempt counts, and never assume annotations work without verifying dependencies and configuration.

### 21.2. Do Not Use Thread.sleep in Reactive Functions

A manual loop calling `Thread.sleep` between attempts can block request/message worker threads. It is also hard to cancel after a client times out and easily violates overall deadlines.

In imperative services, a controlled retry library paired with client/driver timeouts is safer; in Reactor, use `retryWhen` with proper scheduling.

## 22. Retry Mechanism Selection Table

| Scenario | Preferred Mechanism to Consider | Mandatory Caveats |
|---|---|---|
| Direct DB call from sync service | `RetryTemplate` or bounded storage wrapper | Transient only, idempotent |
| Async API call in Reactor | `retryWhen` on inner Publisher | Timeouts, jitter, concurrency |
| HTTP client calling another service | Client/SDK retry | Retryable status/network only; deadline |
| Spring Cloud Stream imperative Consumer | Per-binding binder retry | Error classification, binder-specific DLQ/ack |
| Reactive Function receiving Flux via binder | Adapter policy + per-item operator | Test subscription and error propagation |
| Serverless handler | Trigger retry or short app retry | Deadlines, event IDs, idempotency |
| Polling Supplier | Source/adapter policy | Do not pull a new event when retrying an old one |
| Validation error | Never retry same input | Clear rejection / quarantine |
| Lost response after commit | Idempotent retry or state lookup | Unique keys, transactions |
| Publishing event after DB commit | Outbox + publisher retry | Downstream deduplication |

**No single choice fits every case.** A low attempt count with overly broad scope can be riskier than more attempts tightly scoped to an idempotent call. Design around side-effect boundaries and each adapter's responsibilities.

### 22.1. Two Alternative Configurations—Do Not Stack Blindly

Option A:

~~~text
processOrder synchronous Consumer
  → binder retry maxAttempts=3
  → QuoteStore.save has no separate retry
~~~

Option B:

~~~text
processOrder Consumer or reactive Function
  → binder/application defines clear error policy
  → QuoteWriter.retryWhen retries only DB I/O
  → adapter does not infinitely replay the whole pipeline
~~~

If combining A and B, document why, total attempts, deadlines, idempotency, and exhaustion behavior.

## 23. Observing Retries in Production

Do not measure only "function succeeded or failed." Track how many times the system tried, why, and total duration.

Recommended metrics and logs:

- `requestId`/`eventId` or idempotency key (scrubbed so no sensitive data leaks).
- Operation name and retried step, e.g., `quoteStore.save`.
- Classified error category: invalid, conflict, transient, unknown.
- `attemptIndex`, total attempts, backoff wait, and execution duration.
- Post-retry success rate, exhaustion rate, and DLQ volume.
- Redelivery/reinvocation counts if exposed by the adapter.
- End-to-end latency from receipt to ack or response.
- Conflict and storage-deduplicated duplicate counts.

### 23.1. Do Not Log the Same Exception at Every Layer

A failure can pass from the database through a retry wrapper, `FunctionCatalog`, and an adapter. Logging full stack traces everywhere produces dozens of log lines per request.

Instead:

1. In the retry wrapper, record attempt count and error category.
2. At the outer boundary, log one failure event with correlation ID and final outcome.
3. At the adapter layer, record response code, ack, or DLQ routing per policy.
4. Log payloads only when allowed, preferring IDs and redacted fields.

### 23.2. Alert on Ratios, Not Just Total Errors

If request success rate stays high while retries surge, a dependency may already be degrading before an obvious outage. Track p95/p99 latency, average attempts, retry exhaustion, and queue lag alongside HTTP 500 counts.

### 23.3. When Should Retries Stop Early?

A system can stop retrying early when:

- The overall deadline has elapsed.
- The error is non-retryable.
- A circuit breaker is open or the retry budget is exhausted.
- The client cancelled and no longer needs processing (per business rules).
- The operation already committed and state lookup should replace re-writing.
- The event was already processed according to its idempotency key.

This keeps retries a **conditional recovery mechanism**, not a mandatory loop until max attempts run out.

## 24. Unit Tests: Verifying Attempt Counts and Retryable Error Types

Retry tests must verify **how many times the dependency was actually invoked**, not just final success. Use JUnit 5 and `reactor-test` for the examples below.

### 24.1. Succeeding After Two Transient Failures

~~~java
package example.functions;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

import reactor.test.StepVerifier;

import example.functions.OrderModels.Quote;
import example.functions.OrderErrors.TransientStoreException;

class QuoteWriterRetryTest {

    @Test
    void retriesTwiceThenSucceeds() {
        AtomicInteger attempts = new AtomicInteger();

        QuoteStore flaky = quote -> {
            int attempt = attempts.incrementAndGet();

            if (attempt < 3) {
                throw new TransientStoreException(
                        "Temporary DB timeout",
                        new IllegalStateException("timeout"));
            }
        };

        QuoteWriter writer = new QuoteWriter(flaky);
        Quote quote = new Quote("ORD-501", 2, 250_000L);

        StepVerifier.create(writer.saveWithRetry(quote))
                .verifyComplete();

        assertEquals(3, attempts.get());
    }
}
~~~

This test confirms `QuoteWriter` called the port three times: initial attempt, retry 1, retry 2. Because `QuoteWriter` uses real backoff/jitter and a scheduler, the test incurs a brief delay. For longer schedules, use virtual time as in section 25.

### 24.2. Conflict Errors Are Not Retried

~~~java
package example.functions;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import reactor.test.StepVerifier;

import example.functions.OrderModels.Quote;
import example.functions.OrderErrors.QuoteConflictException;

class ConflictNotRetriedTest {

    @Test
    void conflictFailsAfterOneAttempt() {
        AtomicInteger attempts = new AtomicInteger();

        QuoteStore conflicting = quote -> {
            attempts.incrementAndGet();
            throw new QuoteConflictException(
                    "Same key, different payload");
        };

        QuoteWriter writer = new QuoteWriter(conflicting);

        StepVerifier.create(writer.saveWithRetry(
                new Quote("ORD-502", 2, 250_000L)))
                .expectError(QuoteConflictException.class)
                .verify();

        assertEquals(1, attempts.get());
    }
}
~~~

Key check: the `filter` in `retryWhen` must exclude `QuoteConflictException`. If all exceptions were retried, this test would catch the unexpected extra attempts.

### 24.3. Exhausting Retries Still Emits an Error

~~~java
package example.functions;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import reactor.test.StepVerifier;

import example.functions.OrderModels.Quote;
import example.functions.OrderErrors.TransientStoreException;

class RetryExhaustionTest {

    @Test
    void stopsAfterRetryBudget() {
        AtomicInteger attempts = new AtomicInteger();

        QuoteStore unavailable = quote -> {
            attempts.incrementAndGet();
            throw new TransientStoreException(
                    "Still unavailable",
                    new IllegalStateException("timeout"));
        };

        QuoteWriter writer = new QuoteWriter(unavailable);

        StepVerifier.create(writer.saveWithRetry(
                new Quote("ORD-503", 2, 250_000L)))
                .expectError()
                .verify();

        assertEquals(3, attempts.get());
    }
}
~~~

The test intentionally avoids asserting the exact final exception class because Reactor may wrap retry exhaustion depending on policy and version. If your application contract requires the original exception, configure `onRetryExhaustedThrow` and test the **exact** exception type and cause.

### 24.4. Validation Failures Never Reach the Store

~~~java
package example.functions;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Consumer;
import java.util.function.Function;

import org.junit.jupiter.api.Test;

import example.functions.OrderModels.OrderRequest;
import example.functions.OrderModels.Quote;
import example.functions.OrderErrors.InvalidOrderException;

class ValidationBoundaryTest {

    @Test
    void invalidOrderIsNotPersisted() {
        QuoteFunctions functions = new QuoteFunctions();

        Function<OrderRequest, Quote> core =
                functions.validateOrder()
                         .andThen(functions.calculateQuote());

        AtomicInteger saves = new AtomicInteger();

        Consumer<Quote> store =
                quote -> saves.incrementAndGet();

        Consumer<OrderRequest> pipeline =
                request -> store.accept(core.apply(request));

        assertThrows(InvalidOrderException.class,
                () -> pipeline.accept(
                    new OrderRequest("ORD-504", 0)));

        assertEquals(0, saves.get());
    }
}
~~~

Invalid inputs must be rejected **before side effects**, not merely excluded from retries. Asserting `saves.get() == 0` is an essential guarantee.

### 24.5. Testing Idempotency When the Same Request Replays

~~~java
package example.functions;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

import example.functions.OrderModels.Quote;
import example.functions.OrderErrors.QuoteConflictException;

class QuoteStoreIdempotencyTest {

    @Test
    void repeatedSameRequestCreatesOneEntry() {
        InMemoryQuoteStore store = new InMemoryQuoteStore();

        Quote quote = new Quote("ORD-505", 2, 250_000L);

        store.save(quote);
        store.save(quote);

        assertEquals(1, store.size());
        assertEquals(quote, store.find("ORD-505"));
    }

    @Test
    void sameKeyWithDifferentPayloadIsConflict() {
        InMemoryQuoteStore store = new InMemoryQuoteStore();

        store.save(new Quote("ORD-505", 2, 250_000L));

        assertThrows(QuoteConflictException.class,
                () -> store.save(
                    new Quote("ORD-505", 3, 375_000L)));

        assertEquals(1, store.size());
    }
}
~~~

This suite only verifies behavior inside **one JVM**. It does not prove transactions, uniqueness, or crash-recovery commit behavior in a production database.

## 25. Testing Retry Timing with StepVerifier Virtual Time

With long exponential backoffs, real-time tests can be slow and flaky. Reactor's `StepVerifier.withVirtualTime` lets you verify delayed retries without waiting in real seconds.

~~~java
package example.functions;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.util.retry.Retry;

class RetryVirtualTimeTest {

    @Test
    void succeedsAfterTwoVirtualDelays() {
        AtomicInteger attempts = new AtomicInteger();

        StepVerifier.withVirtualTime(() ->
                Mono.fromCallable(() -> {
                    int n = attempts.incrementAndGet();
                    if (n < 3) {
                        throw new IllegalStateException(
                                "Temporary failure");
                    }
                    return "saved";
                }).retryWhen(
                    Retry.fixedDelay(2, Duration.ofSeconds(1))))
                .expectSubscription()
                .thenAwait(Duration.ofSeconds(2))
                .expectNext("saved")
                .verifyComplete();

        assertEquals(3, attempts.get());
    }
}
~~~

Notice the supplier passed to `withVirtualTime` **constructs the Publisher inside the callback** so time-operator schedulers use virtual time. The example uses `Retry.fixedDelay` without jitter for predictable timing.

### 25.1. Virtual Time Does Not Replace I/O Integration Tests

Virtual time verifies Reactor's retry schedule, yet **cannot simulate**:

- Database commits followed by lost confirmations.
- Broker redeliveries, acks, and DLQs.
- Real cloud invocation timeouts.
- Blocking JDBC threads that fail to cancel promptly.
- External service rate limits or circuit breakers.

Test those failure modes at the proper integration boundaries.

### 25.2. Test retryWhen Across Error Categories

Do not stop at `transient → success`. Also test:

- `invalid → fails immediately`.
- `conflict → fails immediately`.
- `persistent transient failure → stops once attempts exhausted`.
- `transient recovers on retry → succeeds`.
- `unknown error → not treated as transient automatically`.
- `post-commit timeout → idempotent retry or state lookup`.

That is the minimum matrix to keep an accidental refactor from turning retries into a `catch-all`.

## 26. Integration Testing FunctionCatalog and Test Boundaries

A Spring Boot application in the same package:

~~~java
package example.functions;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class QuoteApplication {

    public static void main(String[] args) {
        SpringApplication.run(QuoteApplication.class, args);
    }
}
~~~

Once `QuoteFunctions`, `QuoteSinkFunctions`, `InMemoryQuoteStore`, `QuoteWorkflow`, and Spring Cloud Function / Boot Test dependencies are registered, test composition:

~~~java
package example.functions;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.function.Consumer;
import java.util.function.Function;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

import example.functions.OrderModels.OrderRequest;
import example.functions.OrderModels.Quote;
import example.functions.OrderErrors.InvalidOrderException;

@SpringBootTest(classes = QuoteApplication.class)
class QuoteCatalogTest {

    @Autowired
    FunctionCatalog catalog;

    @Autowired
    InMemoryQuoteStore store;

    @Test
    void calculatesQuoteByComposedName() {
        Function<OrderRequest, Quote> pipeline = catalog.lookup(
                "validateOrder|calculateQuote");

        assertNotNull(pipeline);

        assertEquals(
                new Quote("ORD-601", 2, 250_000L),
                pipeline.apply(new OrderRequest("ORD-601", 2)));
    }

    @Test
    void invalidOrderDoesNotReachConsumer() {
        Consumer<OrderRequest> pipeline = catalog.lookup(
                "validateOrder|calculateQuote|saveQuote");

        assertNotNull(pipeline);

        assertThrows(InvalidOrderException.class,
                () -> pipeline.accept(
                    new OrderRequest("ORD-602", 0)));

        assertNull(store.find("ORD-602"));
    }

    @Test
    void repeatedConsumerInvocationIsIdempotent() {
        Consumer<OrderRequest> pipeline = catalog.lookup(
                "validateOrder|calculateQuote|saveQuote");

        assertNotNull(pipeline);

        OrderRequest request = new OrderRequest("ORD-603", 2);

        pipeline.accept(request);
        pipeline.accept(request);

        assertEquals(
                new Quote("ORD-603", 2, 250_000L),
                store.find("ORD-603"));
    }
}
~~~

Note that in a Spring context containing multiple Function beans, you must select the right `definition` for real adapters. Because this test queries the catalog directly, it does not verify which `processOrder` or expression a binder uses in production config.

### 26.1. What This Test Proves and Does Not Prove

| Test | Verified | Not Verified |
|---|---|---|
| Unit `QuoteFunctions` | Independent validation/calculation | Runtime catalog, binder |
| Unit `QuoteWriter` | Application attempt count | Real DB commit, binder retry |
| Unit `InMemoryQuoteStore` | Single-JVM deduplication | Multiple replicas and durability |
| Catalog integration | Composition names/types/order | HTTP status, broker ack |
| HTTP integration | Request body, status, client retry | Broker DLQ or serverless trigger |
| Broker integration | Binder attempts, ack, redelivery, DLQ | Cloud invocation policy |
| Serverless integration | Event mapping, timeout, reinvocation | Database transactions |
| Fault-injection DB | Atomic writes, conflicts, unclear commits | Every possible real-world outage |

When production uses a real database and multiple instances, test concurrent requests and unique constraints rather than relying on `ConcurrentHashMap`.

### 26.2. Testing the Actual processOrder-in-0 Binding

If running through Spring Cloud Stream with `definition: processOrder`, adapter tests should send real messages or use a version-compatible test binder/harness, inject transient failures, and verify:

1. How many times was the Function called within **one delivery**?
2. After exhaustion, where did the message go—error handler, DLQ, or requeue?
3. Does redelivery occur on the next receive cycle?
4. Does ack happen before or after side effects finish?
5. When the same message replays, does storage keep a single result?
6. On validation errors, does the policy avoid infinite retries?

**You cannot conclude a binder feature works simply because a unit test called `Consumer.accept(...)` three times.** Tests must exercise the actual adapter deployed by the application.

## 27. Common Retry Design Mistakes

| Symptom | Cause | Fix |
|---|---|---|
| Validation errors retried multiple times | Retry lacks exception filtering | Exclude input errors from retries |
| `maxAttempts=3` yet more than three calls seen | Binder retry + app retry + broker redelivery | Separate layers and bound total attempts |
| HTTP POST creates two records | Client resends after timeout | Idempotency key and unique constraint |
| `retryWhen` re-emits older elements | Resubscribes the whole Flux | Place retry inside per-item inner Mono |
| Retries trigger concurrent bursts | No backoff, jitter, or concurrency cap | Backoff, jitter, rate limits |
| No retries happen despite `retryWhen` | Unsubscribed Publisher or eager throw before Publisher | Test subscription; use `defer`/`fromCallable` when needed |
| DB errors not filtered accurately | Exceptions wrapped/retyped indiscriminately | Preserve `cause` and classify in the adapter |
| Retries exhausted yet API returns success | `onErrorReturn`/catch swallows failure | Return proper failure status |
| Consumer self-subscribes and returns | Binder misses terminal signal | Honor the subscription contract |
| Backoff exceeds deadline | Missing time budget | Enforce per-attempt timeouts and total deadline |
| Retries worsen outage when service is down | Retry storm | Circuit breaker, concurrency limits, retry budgets |
| Poison message loops endlessly | Missing DLQ or requeue policy | Separate permanent errors, quarantine/DLQ |
| In-memory dedupe used in serverless | Instances scale/recycle and lose state | Persist idempotency in durable storage |
| Write DB then publish event loses messages | Two side effects outside one transaction | Outbox or equivalent consistency pattern |
| `@Retryable` does not trigger as expected | Proxy/AOP or self-invocation | Verify dependencies, proxy boundaries, integration tests |

### 27.1. Mistake: Retrying to "Boost Reliability" Regardless of Business Semantics

Not every retry is beneficial. For instance, a money transfer or email send may have succeeded right before timing out; if the caller repeats it without idempotency, the damage can exceed the original failure.

Reliability improves when **transient failures recover while keeping state accurate**, not simply by cranking up retry counts.

### 27.2. Mistake: Counting Backoff Time Without Counting I/O Time

A policy with two backoffs of 100 ms and 200 ms does not add only 300 ms to total latency. If each attempt waits for a 5-second timeout, three attempts can take over 15 seconds. Sum it up:

~~~text
attempt 1 timeout + wait + attempt 2 timeout + wait
+ attempt 3 timeout + overhead + response/ack
~~~

Under tighter deadlines, stop early instead of letting requests be aborted mid-write.

### 27.3. Mistake: Converting Every Exception into a Transient Store Error

In code:

~~~java
catch (Exception ex) {
    throw new OrderErrors.TransientStoreException(
            "Temporary", ex);
}
~~~

This can mark `IllegalArgumentException`, `QuoteConflictException`, or bugs as retryable. A storage adapter must classify **based on the real database/client error**, never labeling everything "temporary" by default.

### 27.4. Mistake: Using One Attempt Count Across All Transports

HTTP clients, Spring Cloud Stream binders, and serverless platforms have different lifecycles. A binder's `max-attempts` setting does not constrain a cloud platform's reinvocation limit.

Maintain a per-boundary policy table alongside operational docs or deployment configs so operators know where and why messages were retried.

## 28. Pre-Production Design Checklist

### 28.1. Error Contract

- [ ] Distinguished invalid input, conflicts, transient dependencies, and unknown errors.
- [ ] Non-recoverable failures are not retried indefinitely.
- [ ] Dependency exceptions are remapped cleanly, preserving `cause` when needed.
- [ ] On retry exhaustion, errors propagate or map to accurate business failure outcomes.

### 28.2. Bounds and Scope

- [ ] Defined both total attempts and retry counts for every mechanism.
- [ ] Configured appropriate backoff/jitter with a maximum wait cap.
- [ ] Defined total deadline, per-attempt timeout, and response/ack budget.
- [ ] Identified **the primary retry owner** on every invocation path.
- [ ] Calculated worst-case total calls across stacked retry/redelivery layers.
- [ ] Scoped `retryWhen` strictly to the right Publisher without repeating unrelated side effects.

### 28.3. Data Safety

- [ ] Idempotency key stays stable across client resends, broker redeliveries, and reinvocations.
- [ ] Storage enforces unique constraints or atomic writes.
- [ ] Same key with a different payload reports a clear conflict.
- [ ] Uncertain commit states are verified via key/state lookup rather than assuming unwritten.
- [ ] Combined DB writes and event publishing use an outbox or consistency pattern when needed.
- [ ] Downstream consumers deduplicate when duplicate deliveries can occur.

### 28.4. Adapters and Testing

- [ ] Verified actual binding names, binders, and retry policies.
- [ ] Tested converters, acks, requeues, and DLQs on the real broker.
- [ ] Tested HTTP client retries after timeout with the same idempotency key.
- [ ] Tested serverless trigger timeouts/reinvocations if applicable.
- [ ] For Reactor, tested subscriptions, error signals, and per-item vs. outer retries.
- [ ] Tested retry recovery, non-retry of permanent errors, and exhaustion.
- [ ] Metrics/traces for attempts, backoffs, and failures are sufficient for troubleshooting.

A system with only pure-Function unit tests has not proven production retry safety. Test the real failure boundaries and adapter recovery paths.

## 29. Practice Exercises

**Exercise 1 — Counting Attempts Correctly.** An app uses `Retry.max(2)` and its binder uses `max-attempts: 3`. If both actually retry on the same call with no extra redeliveries, at most how many dependency calls can one message trigger? Why?

**Exercise 2 — Error Classification.** Given four errors: `InvalidOrderException`, `QuoteConflictException`, `TransientStoreException`, and an unexpected `NullPointerException`, which one should the write step's retry filter accept?

**Exercise 3 — Protecting POST.** A client submits a Quote creation request, the server commits to the DB, and the response is lost. The client resends. Design an idempotency key and the rule when the same key arrives with a different payload.

**Exercise 4 — Per-Item Retry.** Given `Flux.just("1", "bad", "3").map(Integer::parseInt).retry(1)`, predict the emitted signals. Why can `1` be emitted twice?

**Exercise 5 — Backoff.** Three retries use exponential backoff with a 100 ms base and factor 2. State the wait schedule before jitter, and explain why an overall deadline is also required.

**Exercise 6 — Binder-Level Retry.** Write a `max-attempts: 3` configuration for input binding `processOrder-in-0`. Which Function type in the example does it apply to, and why does it not guarantee a DLQ on its own?

**Exercise 7 — Serverless.** A handler disconnects after a DB commit and the platform reinvokes the event on another instance. Why is in-memory deduplication insufficient?

**Exercise 8 — Timeout Scope.** Compare `source.timeout(500ms).retryWhen(policy)` with `source.retryWhen(policy).timeout(500ms)`. Which limits a single attempt, and which typically bounds the entire sequence?

**Exercise 9 — Application vs. Adapter.** A synchronous Consumer receives messages from Kafka. Propose one setup using binder retries and another retrying only the DB write inside the app. If combining both, what must you calculate?

**Exercise 10 — Outbox.** A pipeline writes to DB and then emits an event. The process dies after commit before publishing. Does retrying the whole pipeline reliably solve it? How does an outbox help?

**Exercise 11 — Unit Tests.** Write one `StepVerifier` test for two transient failures succeeding on the third try, and one test confirming conflicts are not retried. What assertion is needed beyond the terminal signal?

**Exercise 12 — Retry Exhaustion.** Why should you not use `onErrorReturn(savedQuote)` when saving exhausts retries? Which states must be distinguished?

**Exercise 13 — Supplier.** A `Supplier<OrderRequest>` calls `queue.poll()` on every `get()`. When processing fails, what problem arises if you retry the whole Supplier?

**Exercise 14 — Reactive Consumer.** A `Consumer<Flux<T>>` calls `subscribe()` itself and returns immediately. How can it break the binder's ack/retry behavior?

**Exercise 15 — Observability.** Propose five log/metric fields that help distinguish an HTTP client resend from a binder redelivery and an application retry.

### Suggested Answers

- **Exercise 1:** Up to 3 × 3 = **9 calls** if the binder makes three attempts, each running one initial attempt plus two app retries, before counting any later broker redeliveries.
- **Exercise 2:** Only `TransientStoreException` when genuinely classified as transient; do not blindly retry the others.
- **Exercise 3:** Use `orderId` or a durable idempotency key with a unique constraint: same key + same data returns the prior result; same key + different payload reports conflict.
- **Exercise 4:** `onNext(1)`, `onNext(1)`, then `onError(NumberFormatException)`; `retry(1)` resubscribes to the entire source.
- **Exercise 5:** 100, 200, 400 ms before jitter; you must add per-attempt execution times and reserve budget for response/ack.
- **Exercise 6:** Configured under `spring.cloud.stream.bindings.processOrder-in-0.consumer.max-attempts`; applies when the binder/version supports imperative Consumer retries, whereas DLQ is a separate binder policy.
- **Exercise 7:** New instances do not share memory and crashes lose in-memory state; durable storage idempotency with a stable key is required.
- **Exercise 8:** Timeout before `retryWhen` is usually per-attempt; timeout after retry usually covers the whole process including delays.
- **Exercise 9:** Pick binder retry or app-level I/O retry; if combining them, calculate total attempts, deadlines, error policy, and idempotency.
- **Exercise 10:** Not reliably because commit already occurred; an outbox persists publish intent in the DB transaction so a worker can republish.
- **Exercise 11:** Assert both `verifyComplete`/`expectError` and `assertEquals(n, attempts.get())`.
- **Exercise 12:** Data might not be saved, might be committed with lost ack, or storage may still be down; never fake success.
- **Exercise 13:** It may pull a new event instead of retrying the failed one; keep payload/ID stable and rely on the source's ack/requeue mechanism.
- **Exercise 14:** The binder may treat `accept` as finished before the async Publisher completes, missing failures at ack time.
- **Exercise 15:** For example `requestId`, `eventId`, `attemptIndex`, `retryOwner`, `operationName`, `errorCategory`, `deliveryCount`, or `finalOutcome`.

## 30. Key Takeaways

- **Bounded retries** must explicitly define error types, attempt counts, backoff/jitter, scope, deadlines, and exhaustion handling.
- `Retry.max(2)` typically grants **two additional retries**; a consumer binding's `max-attempts: 3` typically represents **three total processing attempts** in the active binder mechanism.
- Spring Cloud Function builds and composes `Supplier`/`Function`/`Consumer`; retries belong to **the application, adapter, binder, SDK, or platform** along each path.
- Place `retryWhen` on the right Publisher. Retrying a whole Flux can replay prior items; per-item retries need per-message inner boundaries.
- Validation failures, conflicts, and bugs should not be retried blindly. Timeouts/503s may be retried when budgeted and safe.
- **Storage-level idempotency**, unique constraints, and transactions are essential to survive resends and redeliveries after uncertain commits.
- When writing to a DB and publishing events, a transactional outbox reduces lost events; downstream must still handle duplicates.
- Spring Cloud Stream binding retries, HTTP resends, and serverless reinvocations each have distinct semantics; **never stack them without control**.
- Tests must verify actual attempt counts, error signals, side-effect states, and ack/DLQ lifecycles on the deployed adapter—not just pure Functions.








