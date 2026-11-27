# Choosing Where to Catch Errors in a Function Chain

## 1. Lesson Objectives

When composing multiple `Function` beans in Spring Cloud Function, an error can arise during normalization, validation, calculation, external resource access, or data persistence. The question is not only **which exception type to catch**, but also **where to catch it so the system neither hides failures nor corrupts business state**.

In the **SPRING_CLOUD_FUNCTION** module, we build logic using `Supplier`, `Function`, and `Consumer`, register them via `FunctionCatalog`, compose them into pipelines, and reuse them across Java, HTTP, event-driven systems, or serverless environments. Consequently, each layer can hold a different error-handling responsibility: the business core knows *why a request is invalid*; the adapter knows *whether to return an HTTP status, ack, retry, or route to a dead-letter queue*.

This lesson belongs to the **Reliability** chapter and focuses on **choosing where to catch errors in a function chain**. After completing it, you will be able to:

- Identify the step where an error originates, the step authorized to recover, and the boundary responsible for responding.
- Distinguish `throw` in imperative Functions from Reactor `onError` signals in reactive execution.
- Decide when to use a local `try/catch`, an outer orchestration layer, or an adapter-level handler.
- Avoid swallowing exceptions inside a Consumer, especially when a database or broker has already produced side effects.
- Choose where to place `onErrorResume`, `onErrorMap`, `doOnError`, and `retryWhen` according to the intended scope.
- Classify data errors, conflict errors, and infrastructure errors to apply retries appropriately.
- Test both **outcomes** and **whether side effects occurred or were prevented**.

> **Principle:** Place error handling at the layer that has enough information to **make the right decision**. Catch near the source to enrich context or perform genuine recovery; let errors propagate to the caller if only that layer knows how to respond, retry, or recover.

## 2. Where an Error Occurs Differs from Where It Is Handled

Consider the pipeline:

~~~text
OrderRequest
     |
     v
validateOrder                  Function<OrderRequest, ValidatedOrder>
     |
     v
calculateQuote                 Function<ValidatedOrder, Quote>
     |
     v
saveQuote                      Consumer<Quote>
     |
     v
End (no business output)
~~~

A request with `quantity=0` fails at validation. A calculation can fail on numeric overflow. A database can time out during a write. All three errors should not be handled the same way.

~~~text
Error origin                            Has enough context to handle
----------------------------------------------------------------------
validateOrder  -- InvalidOrder ----->   adapter/API: reject input
calculateQuote -- DomainFailure ---->   business logic: reject / report error
saveQuote      -- StorageTimeout --->   transaction/adapter: controlled retry
saveQuote      -- Conflict --------->   adapter/API: conflict / investigate
~~~

**Not every step is authorized to choose a fallback.** `calculateQuote` should not return a price of `0` when the database is unavailable just to keep the pipeline "running." Conversely, a REST adapter can encode a data error as a 400 response, while a messaging adapter needs classification to avoid infinite retries.

### 2.1. Four Common Places to Catch Errors

| Location | Example | What Should It Be Responsible For? |
|---|---|---|
| **Inside a Function** | `try/catch` inside `parseOrder` | Translate library errors into contextual domain errors, or apply a genuinely valid fallback |
| **Between steps** | Validation Function or wrapper around a computation step | Preserve type contracts, distinguish pre- vs. post-processing errors |
| **Around the pipeline** | Service calling `catalog.lookup(...).apply(...)` | Overall error classification, transaction management, and deciding whether to return or retry |
| **Adapter layer** | HTTP handler, binder, serverless entrypoint | Translate errors into responses, ack/nack, DLQ, platform retries |

An error can be **enriched with context at a lower layer** while **the response decision happens at a higher layer**; it does not have to be touched in only one place. Still, avoid logging the same stack trace at every layer and producing duplicate telemetry.

## 3. First Rule: Classify the Error Before Choosing Catch

Before writing `catch (Exception e)`, determine which category the error belongs to.

| Category | Example | Where Can Recovery Happen? | Retry Same Input? |
|---|---|---|---|
| **Invalid input** | `quantity=0`, malformed order ID | Entry boundary or adapter, returning a clear error | Usually no |
| **Business rule rejection** | Discontinued item, limit exceeded | Domain/application layer | Usually no unless state/input changes |
| **Conflict** | Same `orderId` with different payload | Write boundary or orchestration | Do not retry blindly |
| **Transient infrastructure** | Database connection timeout | I/O adapter or idempotent orchestrator | Yes, with bounds/backoff |
| **Programming bug** | Unexpected `NullPointerException` | Observe and fix the code | Do not treat a fake fallback as a fix |
| **Conversion error** | Unparseable JSON, wrong content-type | HTTP/broker converter | Usually no with the same payload |
| **Subscription cancellation** | Client disconnects | Reactive/adapter lifecycle | Do not treat automatically as a retriable business error |

These categories are design guidelines, **not built-in Spring Cloud Function error codes**. Define explicit policies per business domain and adapter when implementing.

### 3.1. Two Litmus Tests for Catching Locally vs. Propagating

Ask:

1. **Does this step know a substitute result that is still valid for the business?** If not, do not invent a fallback.
2. **Does this step know the state of side effects/transactions?** If not, do not assume retrying is safe.

For example, an optional catalog lookup might safely fall back to approved cached data; a payment write cannot "return success" without knowing whether the transaction committed.

## 4. Running Example: Data Contracts and Exceptions

This lesson uses Java 17 and Spring Boot / Spring Cloud Function with a simple quoting model. Explicit types make failures observable at the exact step where they occur.

~~~java
package example.functions;

public final class OrderModels {

    private OrderModels() {}

    public record OrderRequest(String orderId, Integer quantity) {}

    public record ValidatedOrder(String orderId, int quantity) {}

    public record Quote(String orderId, int quantity, long totalVnd) {}
}
~~~

`quantity` uses `Integer` so it can also represent missing data (`null`). After validation, `ValidatedOrder` holds `int` because that step guarantees a valid quantity.

Declare meaningful exceptions:

~~~java
package example.functions;

public final class OrderErrors {

    private OrderErrors() {}

    public static class InvalidOrderException extends RuntimeException {
        public InvalidOrderException(String message) {
            super(message);
        }
    }

    public static class QuoteConflictException extends RuntimeException {
        public QuoteConflictException(String message) {
            super(message);
        }
    }

    public static class QuoteStorageException extends RuntimeException {
        public QuoteStorageException(String message, Throwable cause) {
            super(message, cause);
        }
    }
}
~~~

Distinguishing exception classes lets callers choose the right action. Do not throw one generic `IllegalStateException` for everything and try to classify errors by parsing message text.

### 4.1. Storage Port Separated from Calculation

~~~java
package example.functions;

import example.functions.OrderModels.Quote;

public interface QuoteStore {
    void save(Quote quote);
}
~~~

The port does not automatically guarantee transactions or idempotency. It only defines **the side-effect boundary**. Implementations need concrete write rules and error mapping.

## 5. Three Beans: validate, calculate, and save

~~~java
package example.functions;

import java.util.function.Consumer;
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import example.functions.OrderModels.OrderRequest;
import example.functions.OrderModels.ValidatedOrder;
import example.functions.OrderModels.Quote;
import example.functions.OrderErrors.InvalidOrderException;

@Configuration
public class OrderFunctions {

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
                    input.orderId(),
                    input.quantity());
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

    @Bean
    public Consumer<Quote> saveQuote(QuoteStore store) {
        return store::save;
    }
}
~~~

Three contracts:

~~~text
validateOrder:   OrderRequest → ValidatedOrder
calculateQuote:  ValidatedOrder → Quote
saveQuote:       Quote → void
~~~

Here `validateOrder` and `calculateQuote` produce no external side effects. `saveQuote` is the storage touchpoint.

Because `Math.multiplyExact` can throw `ArithmeticException` on overflow in general cases, consider input bounds and currency types carefully. With quantities 1..100 and unit price 125,000 in this example, the value always fits in `long`; never apply arbitrary fallbacks to unexpected arithmetic failures.

### 5.1. In-Memory Implementation with Duplicate Detection

To make `saveQuote` testable, we use an in-memory store:

~~~java
package example.functions;

import java.util.Map;
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
            throw new IllegalArgumentException("Invalid Quote");
        }

        Quote old = entries.putIfAbsent(quote.orderId(), quote);

        if (old != null && !old.equals(quote)) {
            throw new QuoteConflictException(
                    "Same orderId with different quote");
        }
    }

    public Quote find(String orderId) {
        return entries.get(orderId);
    }

    public int size() {
        return entries.size();
    }

    public Map<String, Quote> snapshot() {
        return Map.copyOf(entries);
    }

    public void clear() {
        entries.clear();
    }
}
~~~

`putIfAbsent` is atomic within **one JVM**. It is not a multi-replica persistence solution: production requires unique constraints or atomic upserts, transactions, and conflict handling at the real storage layer.

### 5.2. Repository Exception Boundary

When a JDBC/JPA adapter executes `save`, it may receive database library exceptions. You can translate a specific transient infrastructure failure into `QuoteStorageException` so upper layers do not depend on driver details:

~~~java
@Override
public void save(Quote quote) {
    try {
        jdbcRepository.insertIfAbsent(quote);
    } catch (TransientDatabaseFailure ex) {
        throw new QuoteStorageException(
                "Temporary failure saving Quote", ex);
    }
}
~~~

This is **conceptual code** requiring `jdbcRepository` and `TransientDatabaseFailure` from the concrete adapter. Do not catch every database exception and relabel it transient: unique constraint violations, invalid data, and connection timeouts mean very different things.

## 6. Imperative Composition: How Exceptions Travel Through andThen

In Java, `Function.andThen` chains synchronous calls. If the first step throws an exception, the second step **is not called**:

~~~java
import java.util.function.Function;

import example.functions.OrderModels.OrderRequest;
import example.functions.OrderModels.ValidatedOrder;
import example.functions.OrderModels.Quote;

OrderFunctions definitions = new OrderFunctions();

Function<OrderRequest, ValidatedOrder> validate =
        definitions.validateOrder();
Function<ValidatedOrder, Quote> calculate =
        definitions.calculateQuote();

Function<OrderRequest, Quote> quote =
        validate.andThen(calculate);
~~~

Try an invalid input:

~~~java
try {
    Quote result = quote.apply(new OrderRequest("ORD-42", 0));
} catch (OrderErrors.InvalidOrderException ex) {
    System.out.println("Order rejected: " + ex.getMessage());
}
~~~

`validateOrder` throws before returning a `ValidatedOrder`, so `calculateQuote` is never invoked.

### 6.1. Catching Outside the Pipeline Is a Good Default

When **no single step has a business-valid fallback**, let exceptions propagate out of the Function and catch them at the service or adapter:

~~~text
validateOrder ── error ──┐
                         |
calculateQuote ── error ─┤
                         v
                 Application boundary
                   classify exception
                         |
                         v
               HTTP response / nack / retry
~~~

This keeps Functions small, testable, and independent of HTTP status codes or broker configuration.

### 6.2. Catch Locally When You Know How to Translate the Error

A parsing function can translate `NumberFormatException` into a clear input error:

~~~java
Function<String, Integer> parseQuantity = raw -> {
    try {
        return Integer.parseInt(raw.trim());
    } catch (NumberFormatException ex) {
        throw new OrderErrors.InvalidOrderException(
                "Quantity must be an integer");
    }
};
~~~

The parse step knows exactly which field failed, so translating the error here makes sense. If you need to preserve the cause for tracing, provide a constructor taking `Throwable cause` on the domain exception and pass `ex`; do not log stack traces here and then log again at every layer.

### 6.3. Do Not Catch Exception and Return a Fake Value

Avoid:

~~~java
Function<String, Integer> unsafeParse = raw -> {
    try {
        return Integer.parseInt(raw.trim());
    } catch (Exception ignored) {
        return 0;
    }
};
~~~

If `0` carries business meaning, callers will not know the input was malformed. Even if `0` is rejected later by validation, the error type has been altered and the original context lost. Use a domain exception or a `Result<T>` type if you want to return errors as data.

## 7. Catch at the Orchestration Layer Instead of Inside Every Function

A service typically knows whether a request is a *preview* or a *commit* and which transaction is active. It can decide whether to recover with approved data or propagate the error to the adapter.

Example of an orchestration layer using imperative Functions:

~~~java
import java.util.function.Function;

Function<OrderModels.OrderRequest, OrderModels.Quote> pipeline =
        definitions.validateOrder()
                   .andThen(definitions.calculateQuote());

try {
    OrderModels.Quote quote = pipeline.apply(
            new OrderModels.OrderRequest("ORD-42", 2));

    // The application can return the quote or call storage separately.
} catch (OrderErrors.InvalidOrderException ex) {
    // Forward as input error at the boundary.
    throw ex;
}
~~~

This snippet merely illustrates the placement of `catch`; catching and rethrowing `ex` unchanged is usually **unnecessary** unless adding useful behavior such as metrics or context. Production code should avoid catch blocks that do nothing besides rethrowing.

### 7.1. Rule Against Catching at Every Layer

A `validate → calculate → save` chain does not need every Function to do:

~~~java
try {
    // Perform the step's work.
} catch (Exception ex) {
    log.error("Failed", ex);
    throw ex;
}
~~~

Doing so logs the same exception multiple times, creating noise and risking data leakage. Instead:

- The step that detects an error attaches an appropriate domain code or message.
- The caller or adapter boundary classifies and logs a single structured failure event.
- Telemetry components can measure per-step errors without turning failures into fake successes.

## 8. Catching Errors in FunctionCatalog: lookup, apply, and Downstream

With Spring Cloud Function, pipelines are resolved by bean names:

~~~java
import java.util.function.Function;
import org.springframework.cloud.function.context.FunctionCatalog;

Function<OrderModels.OrderRequest, OrderModels.Quote> quote =
        catalog.lookup("validateOrder|calculateQuote");

if (quote == null) {
    throw new IllegalStateException("Missing quote pipeline");
}

OrderModels.Quote output = quote.apply(
        new OrderModels.OrderRequest("ORD-42", 2));
~~~

Here `catalog` is a Spring-injected `FunctionCatalog`. There are **two distinct error boundaries**:

1. **Lookup/composition:** missing name, missing bean, unsupported composition, incompatible type metadata; errors can appear at `lookup(...)`.
2. **Execution:** invalid data, calculation errors, dependency failures; errors can appear at `apply(...)` or in a reactive signal when using Publishers.

Do not wrap both in one `catch (Exception)` and label everything "invalid input": a `lookup` failure is usually a deployment or configuration bug, not a client data error.

### 8.1. Chains Ending in a Consumer

~~~java
import java.util.function.Consumer;

Consumer<OrderModels.OrderRequest> record = catalog.lookup(
        "validateOrder|calculateQuote|saveQuote");

if (record == null) {
    throw new IllegalStateException("Missing record pipeline");
}

record.accept(new OrderModels.OrderRequest("ORD-42", 2));
~~~

Depending on the Spring Cloud Function version and adapter, composition support across `Supplier`/`Function`/`Consumer` forms must be verified in practice. By **data contract**, `Function<OrderRequest,Quote>` followed by `Consumer<Quote>` yields `Consumer<OrderRequest>`. Because Consumer returns `void`, you cannot chain a Function after it expecting output.

When `saveQuote` throws after the database may already have committed, an outer `catch` **cannot tell on its own whether the write succeeded**. You must design idempotency at the storage boundary.

## 9. Choosing Where to Catch Based on the Handling Goal

Consider three positions along the same chain:

~~~text
A: validateOrder → B: calculateQuote → C: saveQuote
~~~

Errors can be handled **inside A**, **between A and B**, or **around A–C**. Each choice carries different knowledge:

| Position | What It Knows for Sure | What It Does Not Know for Sure |
|---|---|---|
| Inside A | Which field is invalid | Specific HTTP status or broker ack |
| Inside B | Why the calculation failed | Whether the caller wants preview or commit |
| Inside C | What error the storage call reported | Whether the DB committed if the ack was lost |
| After the whole pipeline | Propagated error type and request context | Side-effect state without querying storage |
| Outermost adapter | Protocol, retry/ack, and error formatting | Should not reimplement business rules |

### 9.1. Catch and Transform Errors Where the Cause Is Known

For example, a parser may translate technical errors into input errors:

~~~java
Function<String, Integer> parseQuantity = input -> {
    if (input == null) {
        throw new OrderErrors.InvalidOrderException(
                "Quantity must not be null");
    }

    try {
        return Integer.parseInt(input.trim());
    } catch (NumberFormatException ex) {
        throw new OrderErrors.InvalidOrderException(
                "Quantity must be an integer");
    }
};
~~~

This **adds clarity to the error**, rather than hiding it. In real systems, include a stable error code, and if retaining the cause for debugging, support a constructor taking `cause` on the exception.

### 9.2. Catch at the Layer Authorized to Choose a Fallback

Suppose the system fetches an **optional supplementary description** from an external service. If that service is temporarily unavailable and business rules allow an empty or placeholder description, a fallback can make sense:

~~~java
Function<OrderModels.Quote, String> description = quote -> {
    try {
        return optionalDescriptionService.lookup(
                quote.orderId());
    } catch (OptionalDescriptionUnavailableException ex) {
        return "Description not available";
    }
};
~~~

`optionalDescriptionService` and its exception are conceptual dependencies. A fallback is valid only if **the description is genuinely non-essential** to the quote's correctness; never apply that approach to totals, permissions, financial data, or database write outcomes.

### 9.3. Propagate When You Do Not Know How to Recover

If `saveQuote` throws `QuoteStorageException`, the calculation layer has no authority to claim "saved successfully." The safe choice is to let the error propagate to a layer that understands retries, transactions, or acks rather than swallowing it for a fake success response.

## 10. Why Catching After a Side Effect Is Riskier Than Catching Before

Compare:

~~~text
Case A:
  validate -- error --> never reaches save
  State: Quote not written

Case B:
  validate → calculate → save -- commit --> network timeout
  State: Quote may ALREADY be written, even though caller sees an error
~~~

In Case A, rejecting input is relatively straightforward. In Case B, you must consider:

- Does `saveQuote` use a transaction or unique constraint?
- Is there a stable idempotency key such as `orderId`?
- Given the same key and a different payload, should it report conflict or update by version?
- Will the adapter retry **the entire chain** or only the save operation?
- If an event is emitted after commit, is there a risk of duplicate or lost events?

No catch block can resolve commit ambiguity by itself. **Retry correctness comes from storage and transaction design**, not merely catching exceptions.

### 10.1. Example to Avoid

~~~java
Consumer<OrderModels.Quote> unsafeSave = quote -> {
    try {
        store.save(quote);
    } catch (RuntimeException ex) {
        // Wrong: the adapter may think it succeeded.
    }
};
~~~

If a consumer/binder acknowledges success once `accept` returns, swallowing the exception here can prevent the message from being retried even though saving failed. Propagate the error or durably record the failure state, depending on the adapter contract.

### 10.2. Catching and Immediately Saving Again Is Not Automatically Safe Either

~~~java
try {
    store.save(quote);
} catch (OrderErrors.QuoteStorageException ex) {
    store.save(quote); // Safe only when store has an idempotent contract.
}
~~~

This snippet illustrates the risk: if the database committed yet confirmation was lost, a second call can create duplicates. Do not turn a transient failure into unbounded repeated writes; use bounded retries with backoff and deduplication.

## 11. Reactor: Direct Exceptions Differ from onError

Spring Cloud Function also supports Functions using `Mono` or `Flux`. With imperative code:

~~~java
Function<OrderModels.OrderRequest, OrderModels.Quote> quoteOne =
        definitions.validateOrder()
                   .andThen(definitions.calculateQuote());

quoteOne.apply(new OrderModels.OrderRequest("ORD-42", 0));
// Throws InvalidOrderException immediately.
~~~

In Reactor:

~~~java
import reactor.core.publisher.Mono;

Mono<OrderModels.Quote> quoteMono =
        Mono.just(new OrderModels.OrderRequest("ORD-42", 0))
            .map(quoteOne);
~~~

When `quoteMono` is created, the `map` callback has usually not run yet. Upon subscription, `quoteOne` runs and the mapper's exception typically becomes a terminal `onError` signal.

### 11.1. try/catch Around Assembly Does Not Catch All Reactive Errors

~~~java
try {
    Mono<OrderModels.Quote> result =
            Mono.just(new OrderModels.OrderRequest("ORD-42", 0))
                .map(quoteOne);

    // Only creates the Publisher.
} catch (OrderErrors.InvalidOrderException ex) {
    // Usually does not enter here because the mapper has not run yet.
}
~~~

Use Reactor error operators or let the subscriber/adapter handle `onError`.

### 11.2. Errors Can Still Throw Immediately If Code Runs Before Creating the Publisher

~~~java
// Wrong expectation: Java invokes quoteOne.apply immediately.
Mono<OrderModels.Quote> eager =
        Mono.just(quoteOne.apply(
            new OrderModels.OrderRequest("ORD-42", 0)));
~~~

Here the exception is thrown **before** `Mono.just(...)` receives its argument. To place the invocation inside the Publisher:

~~~java
Mono<OrderModels.Quote> deferred =
        Mono.fromCallable(() ->
            quoteOne.apply(
                new OrderModels.OrderRequest("ORD-42", 0)));
~~~

`fromCallable` defers invoking the Function until subscription and converts regular exceptions into `onError`.

### 11.3. Errors in Both Phases Can Coexist

~~~java
Function<OrderModels.OrderRequest,
         Mono<OrderModels.Quote>> quoteReactive = input -> {
    if (input == null) {
        throw new OrderErrors.InvalidOrderException(
                "Input null");
    }

    return Mono.fromCallable(() -> quoteOne.apply(input));
};
~~~

With `null`, `quoteReactive.apply(null)` throws immediately; with an invalid quantity, `apply` returns a `Mono`, and the mapper emits the error upon subscription. Choose catch boundaries based on **the execution phase**, not merely the word "reactive."

## 12. Reactor: Place onErrorResume Outside or Per Element?

This choice strongly affects pipelines processing multiple messages. Consider:

~~~java
import reactor.core.publisher.Flux;

Flux<Integer> parsed = Flux.just("2", "bad", "5")
        .map(Integer::parseInt);
~~~

### 12.1. onErrorResume Across the Whole Flux

~~~java
Flux<Integer> recovered = Flux.just("2", "bad", "5")
        .map(Integer::parseInt)
        .onErrorResume(
            NumberFormatException.class,
            error -> Flux.just(-1));
~~~

Output:

~~~text
onNext(2)
onNext(-1)
onComplete
~~~

Element `"5"` **is not processed further**. `onErrorResume` at the end of the pipeline replaces the failed stream with another Publisher rather than resuming with the next input.

Thus, this placement fits when **the entire source** should stop or switch to a fallback on the first failure, not when each event must be isolated independently.

### 12.2. Handling Errors Inside Each Element

~~~java
import reactor.core.publisher.Mono;

Flux<Integer> validValues = Flux.just("2", "bad", "5")
        .concatMap(raw ->
            Mono.fromCallable(() -> Integer.parseInt(raw))
                .onErrorResume(
                    NumberFormatException.class,
                    error -> Mono.empty()));
~~~

Output:

~~~text
onNext(2)
onNext(5)
onComplete
~~~

Here, the catch/`onErrorResume` sits **inside the inner Mono** for each input. A bad element does not discard independent subsequent elements. In production, do not silently drop `"bad"` if it is a message requiring a response, audit, quarantine, or dead-letter routing; add an observable invalid-data policy.

### 12.3. Do Not Use onErrorContinue as a Catch-All

`onErrorContinue` has operator-dependent semantics and acts upstream in ways that are hard to predict in complex pipelines. For independent per-event handling, prefer **one inner Publisher per input** with error handling inside the inner Publisher, as in the `concatMap` example.

### 12.4. Scope Selection Table

| Desired Behavior | Where to Handle |
|---|---|
| One event error stops the whole stream | Outer `onErrorResume` or let `onError` reach pipeline boundary |
| One event error does not block other events | `onErrorResume` inside each event's inner Publisher |
| Convert technical failure to domain error | `onErrorMap` near the failing adapter, before classification |
| Log/record metrics while preserving propagation | `doOnError` at the observation boundary |
| Retry one transient step, not the whole pipeline | `retryWhen` wrapping only the Publisher for that step |

## 13. Placement of onErrorMap and doOnError Affects Classification

Operators execute in assembly order; an error already recovered by one operator may **no longer exist as an error to downstream operators**.

### 13.1. doOnError Before or After onErrorResume?

~~~java
Mono<Integer> source =
        Mono.error(new IllegalStateException("temporary"));

Mono<Integer> a = source
        .doOnError(error -> metrics.record(error))
        .onErrorResume(error -> Mono.just(-1));
~~~

`metrics` is an illustrative dependency. Here `doOnError` observes the original error before the fallback applies.

If the order is swapped:

~~~java
Mono<Integer> b = source
        .onErrorResume(error -> Mono.just(-1))
        .doOnError(error -> metrics.record(error));
~~~

The trailing `doOnError` typically **never sees the original error** because `onErrorResume` already replaced it with a value and completed. That is not necessarily a bug: it means placement determines whether you measure **upstream errors** or **unrecovered errors**.

### 13.2. onErrorMap and Retry Filters

If a transient I/O error is transformed by `onErrorMap` into an exception that loses transient identity, a downstream `retryWhen` filtering on the original type may fail to match.

Conceptual flow:

~~~text
source -- TemporaryDatabaseError --> onErrorMap(GeneralError)
                                   |
                                   v
                         retryWhen(filter TemporaryDatabaseError)
                         No longer sees the original error type
~~~

Two options:

- Place `retryWhen` close to the source, **before** remapping the exception; or
- Map to an application exception that preserves classification and retains `cause`, then match that type in the filter.

Do not wrap every exception into one generic class and retry indiscriminately regardless of cause.

### 13.3. doOnError Does Not Recover from Errors

~~~java
Mono<Integer> result = Mono.<Integer>error(
        new IllegalArgumentException("invalid"))
        .doOnError(ex -> System.err.println(ex.getMessage()));
~~~

Downstream still receives `onError`. `doOnError` is only for observational side effects like logging or metrics, never a replacement for `onErrorResume` or an adapter handler.

## 14. Placing retryWhen Before or After Side Effects?

In Reactor, `retry`/`retryWhen` normally resubscribes to **everything upstream of that operator**, so retry placement determines **which work can run again**.

### 14.1. Retrying the Whole Chain Can Duplicate Writes

~~~java
Mono<OrderModels.Quote> risky = Mono.fromCallable(
        () -> quoteOne.apply(request))
    .flatMap(quote ->
        persistThenNotify(quote))
    .retryWhen(retryPolicy);
~~~

In this conceptual snippet, `request`, `quoteOne`, `persistThenNotify`, and `retryPolicy` are supplied by the application. If `persistThenNotify` already saved to the database and then failed while notifying, retrying at the end can **rerun both calculation and persistence**.

Even when calculation is pure, persistence may not be safe to repeat. Do not attach retry at the end of a chain out of syntactic convenience.

### 14.2. Scope Retries Specifically to the I/O Operation

A synchronous `QuoteStore.save` call can be wrapped in a `Mono`:

~~~java
import java.time.Duration;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.util.retry.Retry;

Mono<Void> saveWithRetry(
        QuoteStore store, OrderModels.Quote quote) {

    return Mono.<Void>fromRunnable(() -> store.save(quote))
            .subscribeOn(Schedulers.boundedElastic())
            .retryWhen(
                Retry.backoff(2, Duration.ofMillis(100))
                    .filter(error ->
                        error instanceof OrderErrors.QuoteStorageException));
}
~~~

This example method uses `boundedElastic` because the port assumes possible blocking I/O. `Mono.fromRunnable` defers calling `save` until subscription; `retryWhen` wraps only the persistence Publisher. In a real application, place the method in a class with the required imports.

**Warning:** even retrying a single `save` call can cause duplicate writes if the commit succeeded yet confirmation was lost. Storage needs idempotency keys/unique constraints and accurate transient-error classification. Never treat scoping retries alone as enough for exactly-once behavior.

### 14.3. Separate Data Errors from I/O Errors

`InvalidOrderException` must not be mapped into `QuoteStorageException` and accidentally matched by a retry filter. Validation failures must be detected **before** creating the persistence Publisher, or propagated intact to a boundary authorized to reject them.

## 15. Controlling Errors with Supplier or Consumer

Different combinations yield different error contracts:

~~~text
Supplier<OrderRequest> | Function<OrderRequest, Quote>
    ⇒ Supplier<Quote>        (by composition contract)

Function<OrderRequest, Quote> | Consumer<Quote>
    ⇒ Consumer<OrderRequest>

Supplier<OrderRequest> | Consumer<OrderRequest>
    ⇒ Runnable
~~~

In plain Java, `Supplier` is called via `get()`, `Consumer` via `accept(...)`, and `Runnable` via `run()`. When a step throws directly, the outer caller observes it; inside a reactive Publisher, failures may arrive via `onError`.

### 15.1. A Supplier Source Can Fail Before Business Logic

~~~java
import java.util.function.Supplier;

Supplier<OrderModels.OrderRequest> nextOrder =
        () -> queueClient.pollNextOrder();
~~~

`queueClient` is an illustrative dependency. If the source fails to read a message, validation has not run yet, so the error belongs to the source/transport boundary. Do not catch it inside `calculateQuote` and label it "invalid order."

### 15.2. A Consumer May Have Created Side Effects Before an Error Escapes

~~~java
Consumer<OrderModels.Quote> sendAndAudit = quote -> {
    store.save(quote);
    auditClient.publish(quote);
};
~~~

If `store.save` succeeds while `auditClient.publish` fails, retrying the whole Consumer can write again. Both dependencies are conceptual; many systems need transactions, an outbox, or recovery-aware orchestration rather than just adding a catch block.

### 15.3. Runnable Does Not Trigger Automatically

When `Supplier|Consumer` yields a `Runnable`, it has no return value and does not run on a schedule merely because the composition bean exists. Who calls `run()` or which adapter triggers it must be defined explicitly. `Supplier` and `Consumer` composition/orchestration in Spring Cloud Function must be verified on your actual version and adapter.

## 16. Catching at a Boundary Does Not Mean Swallowing Errors

There are two completely different behaviors:

~~~text
Catch to RESPOND:
  InvalidOrder -> HTTP 400 / message quarantine / business error

Catch to HIDE:
  Storage failure -> log then return success / ack as processed
~~~

Catching errors is good when it converts an exception into a **well-defined outcome** or chooses a **correct recovery action**. Catching an error to make a pipeline look successful when it actually failed is dangerous.

### 16.1. The Application Layer Should Not Return a Generic Boolean

~~~java
boolean process(OrderModels.OrderRequest request) {
    try {
        recordPipeline.accept(request);
        return true;
    } catch (Exception ignored) {
        return false;
    }
}
~~~

`recordPipeline` is a provided `Consumer<OrderRequest>`. This code **discards the error category**: `false` could mean invalid input, conflict, timeout, or a bug. Nor does it indicate whether the write committed.

If the application needs a return value instead of an exception, define a structured outcome type:

~~~java
enum OutcomeCode {
    ACCEPTED,
    INVALID_INPUT,
    CONFLICT,
    TEMPORARILY_UNAVAILABLE
}

record ProcessingOutcome(
        OutcomeCode code,
        String orderId,
        String message) {}
~~~

The orchestration layer can translate **classified exceptions** into `ProcessingOutcome`, while unexpected failures follow the general policy. When commit state is unknown, never return `ACCEPTED` without proof.

## 17. Decision Table for Where to Catch Errors

| Situation | Preferred Location | Action |
|---|---|---|
| `Integer.parseInt` fails | Inside parser or DTO validation | Convert to contextual input error |
| Invalid quantity | `validateOrder` throws; adapter handles | Do not calculate and do not write |
| Valid SKU pattern but out of stock | Domain/application service | Business rejection; watch concurrency |
| Missing optional description | Enrichment step with approved fallback | Return valid default |
| Unexpected monetary overflow | Domain/application | Report error / check rules, no fake value |
| Transient DB error before commit | Write adapter + orchestrator | Bounded retry if idempotent |
| Connection lost after commit | Transaction/storage boundary | Look up / idempotency; do not assume unwritten |
| JSON converter failure | HTTP/message adapter | Reject/quarantine before Function runs |
| Wrong bean name in `lookup` | Startup/config/integration test | Fix deployment, do not blame client |
| Flux mapper fails on one event | Per-item inner Publisher if independent | Quarantine/fallback per message |
| Mapper error stops entire stream | Outer `onError` | Stop stream and report overall failure |
| Broker redelivers message | Storage/consumer boundary | Deduplicate by event/order ID |

Every decision must align with the fact that inputs may arrive from HTTP, messaging, or serverless: **domain rules are shared, while protocol policies can differ**.

## 18. HTTP: Let the Adapter Map Domain Errors to Responses

A REST controller can invoke the pipeline via `FunctionCatalog`. The HTTP layer knows requests and responses, while `validateOrder` does not need to import any Spring Web classes.

~~~java
package example.functions;

import java.util.function.Function;

import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import example.functions.OrderModels.OrderRequest;
import example.functions.OrderModels.Quote;

@RestController
@RequestMapping("/quotes")
public class QuoteController {

    private final FunctionCatalog catalog;

    public QuoteController(FunctionCatalog catalog) {
        this.catalog = catalog;
    }

    @PostMapping
    public Quote preview(@RequestBody OrderRequest request) {
        Function<OrderRequest, Quote> pipeline =
                catalog.lookup("validateOrder|calculateQuote");

        if (pipeline == null) {
            throw new IllegalStateException(
                    "Missing quote pipeline");
        }

        return pipeline.apply(request);
    }
}
~~~

`QuoteController` is a custom adapter for illustration. Spring Cloud Function also has its own web adapter depending on starter and version; do not assume every URL and error handler matches this example controller.

### 18.1. Build a Stable Error Contract

~~~java
package example.functions;

public record ApiError(String code, String message) {}
~~~

Example `@RestControllerAdvice` classifying three domain error types:

~~~java
package example.functions;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import example.functions.OrderErrors.InvalidOrderException;
import example.functions.OrderErrors.QuoteConflictException;
import example.functions.OrderErrors.QuoteStorageException;

@RestControllerAdvice
public class QuoteErrorHandler {

    @ExceptionHandler(InvalidOrderException.class)
    public ResponseEntity<ApiError> invalid(
            InvalidOrderException ex) {
        return ResponseEntity.badRequest()
                .body(new ApiError(
                        "INVALID_ORDER", ex.getMessage()));
    }

    @ExceptionHandler(QuoteConflictException.class)
    public ResponseEntity<ApiError> conflict(
            QuoteConflictException ex) {
        return ResponseEntity
                .status(HttpStatus.CONFLICT)
                .body(new ApiError(
                        "ORDER_CONFLICT",
                        "Order already exists with different data"));
    }

    @ExceptionHandler(QuoteStorageException.class)
    public ResponseEntity<ApiError> unavailable(
            QuoteStorageException ex) {
        return ResponseEntity
                .status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(new ApiError(
                        "TEMPORARILY_UNAVAILABLE",
                        "Storage system is temporarily unavailable"));
    }
}
~~~

Here input errors become HTTP 400, conflicts become 409, and one storage failure becomes 503. This is an **API policy example**, not an automatic Spring Cloud Function mapping. For real APIs, check what details are safe to expose and design consistent error codes.

### 18.2. Errors Before the Function Must Also Be Handled

Malformed JSON or unconvertible types into `OrderRequest` can fail in the converter **before entering the controller/Function**. At that point, `InvalidOrderException` has not been thrown. Add a dedicated deserialization error handler or rely intentionally on Spring Web's mechanism per API requirements.

Do not assume every JSON error goes through `validateOrder` and conclude the Function ran. Likewise, a `FunctionCatalog.lookup(...)` failure due to a wrong name is a server configuration bug, not a client 400 error.

### 18.3. Reactive Controllers and onError

A WebFlux controller can return `Mono<Quote>`:

~~~java
@PostMapping("/reactive")
public Mono<OrderModels.Quote> previewReactive(
        @RequestBody OrderModels.OrderRequest request) {

    return Mono.fromCallable(() -> quoteOne.apply(request));
}
~~~

Here `quoteOne` is an injected `Function<OrderRequest,Quote>`, and the method sits inside a controller with `Mono` and the appropriate Spring Web annotations imported.

If `quoteOne` throws inside the `Callable`, the error signal is emitted at subscription time. A Spring WebFlux exception handler can still map it if it runs within the framework-managed response lifecycle. However, a `try/catch` wrapping only `return Mono.fromCallable(...)` will usually not catch errors thrown inside the `Callable`.

## 19. Messaging: Catch Strategy So the Binder Knows How to Handle Errors

When a function is wired into Spring Cloud Stream, a pipeline can be selected via:

~~~yaml
spring:
  cloud:
    function:
      definition: "validateOrder|calculateQuote|saveQuote"
~~~

The composition takes `OrderRequest` and returns `void`, matching `Consumer<OrderRequest>` in data contract. Beyond this property, the application needs a binder, bindings/destinations, converters, and an error policy appropriate for the messaging system.

### 19.1. Do Not Swallow Exceptions Inside the Consumer

Suppose the broker delivers a structurally valid `OrderRequest` with `quantity=0`. `validateOrder` throws and `saveQuote` never runs.

If the adapter/binder is configured to observe errors and send messages to a dead-letter queue or reject them per policy, letting the error **propagate cleanly to the consumer boundary** lets the adapter decide. If the Consumer catches all exceptions silently, the binder may treat processing as successful.

Still, do not assume "throwing always nacks" or "`onError` always routes to DLQ": exact behavior depends on the binder, delivery mode, Spring Cloud Stream version, and acknowledgement policy.

### 19.2. Poison Messages and Transient Errors Differ

~~~text
Receive message
     |
     v
Deserialize ------ bad schema ------> quarantine / DLQ / observe
     |
     v
validateOrder ---- quantity = 0 ----> reject per policy
     |
     v
calculateQuote
     |
     v
saveQuote -------- DB timeout ------> bounded retry and idempotency
     |
     v
Ack per binder mechanism
~~~

For permanently invalid data, infinite retries on the same payload only create an error loop. When storage times out, retries can make sense, but duplicates must be prevented—especially if confirmation was lost after commit.

### 19.3. Message<T> and Header Handling

If you need `messageId`, `correlationId`, or `schemaVersion`, decide which layer reads and validates headers. `Function<Message<OrderRequest>,...>` and `Function<OrderRequest,...>` are two distinct Java contracts.

An adapter can extract payload and context and construct an informative domain input. Do not blindly trust arbitrary client-supplied headers; fields used for authorization or idempotency must be verified against trusted sources.

### 19.4. Errors Occurring After the Message Was Already Acknowledged

If a Consumer creates an asynchronous subscription on its own and returns from `accept(...)` before work finishes, the binder may not see the failure in time to decide ack/nack. That is why you should not self-subscribe inside a Consumer without honoring the adapter contract; verify that **completion and error signals are observed by the message-orchestration layer**.

## 20. Serverless: Catch in the Handler or Inside the Function?

A Function can run inside a serverless handler through an appropriate adapter. Some runtimes expect synchronous return values; others support asynchronous result types. Either way, the placement rules still hold:

- **Inside domain Functions:** detect and describe business errors.
- **Inside handler/adapter:** map events to input types, handle serialization errors, and build platform responses.
- **Storage layer:** transactions, uniqueness/idempotency, and commit state.
- **Trigger platform:** concrete invocation timeout, retry, or dead-letter policies.

Example of a custom Java handler performing explicit classification:

~~~java
public ProcessingOutcome handle(OrderModels.OrderRequest input) {
    try {
        OrderModels.Quote quote = quotePipeline.apply(input);
        return new ProcessingOutcome(
                OutcomeCode.ACCEPTED, quote.orderId(), "OK");
    } catch (OrderErrors.InvalidOrderException ex) {
        return new ProcessingOutcome(
                OutcomeCode.INVALID_INPUT,
                input == null ? null : input.orderId(),
                "Rejected");
    }
}
~~~

`quotePipeline` is a provided `Function<OrderRequest,Quote>`, while `OutcomeCode` and `ProcessingOutcome` were defined in section 16. This snippet only illustrates returning a **structured business outcome**; real serverless triggers must support the return type and adapter mapping.

When the platform re-invokes after a timeout, do not catch `QuoteStorageException` and return `ACCEPTED` merely to suppress retries. Nor should you return an arbitrary error if business state already committed without checking state first. Storage-level duplicate prevention remains essential.

## 21. Observability: Measure Errors at the Boundary, Avoid Duplicate Logs

Where you catch affects both log volume and quality.

~~~text
validateOrder
     |
     v
calculateQuote
     |
     v
saveQuote
     |
     v
Adapter boundary: final recording / classification / response
~~~

One clean organization:

- Domain steps **throw errors with clear codes or types**.
- I/O adapters **translate library errors to infrastructure types** when they hold enough context.
- The application/adapter boundary **logs one classified error event**.
- Tracing/metrics can count per-step failures without logging repeated stack traces.

### 21.1. Preserve Cause and Context

When translating a technical exception into an application exception, preserve `cause` for root-cause analysis:

~~~java
try {
    externalStore.save(quote);
} catch (SomeTransientException ex) {
    throw new OrderErrors.QuoteStorageException(
            "Quote storage unavailable", ex);
}
~~~

`externalStore` and `SomeTransientException` are illustrative dependencies for a real adapter. Never catch every `Exception` and label it "transient," or the system may retry data errors and programming bugs.

Include trusted correlation IDs and operation names from context, while keeping sensitive payloads, passwords, and access tokens out of logs. In Reactor when schedulers switch threads, traditional `ThreadLocal` may not propagate context automatically; use appropriate Reactor Context / observability propagation.

### 21.2. Measure Before or After Fallback?

~~~java
Mono<OrderModels.Quote> observed = source
        .doOnError(error -> metrics.incrementFailure())
        .onErrorResume(error -> approvedFallback(error));
~~~

`source`, `metrics`, and `approvedFallback` are illustrative dependencies. Placing `doOnError` before fallback counts source errors; placing it after counts only remaining unrecovered errors. Either placement can be valid depending on what you want to measure; make sure metric names accurately reflect their meaning.

### 21.3. Do Not Confuse Cancellation with Error

When a client cancels a subscription or another layer triggers a timeout, the lifecycle may emit **cancel** rather than `onError` at every operator. To observe all termination signals, `doFinally(signalType -> ...)` distinguishes `ON_COMPLETE`, `ON_ERROR`, and `CANCEL` within the relevant Reactor scope.

Do not treat every cancellation as a retriable business error; check what happened to any side effects running at the moment of cancellation.

## 22. When Should You Use Result Instead of Exceptions?

Not every unsuccessful case is **exceptional**. For instance, user input validation may return a list of errors for display rather than immediately throwing an exception.

Illustrative data type:

~~~java
import java.util.List;

record ValidationResult<T>(
        T value,
        List<String> errors) {

    boolean valid() {
        return errors != null && errors.isEmpty();
    }
}
~~~

With this pattern, a Function can return `ValidationResult<ValidatedOrder>`. The next step **cannot assume** it receives a `ValidatedOrder` directly; it must inspect the result and invoke business logic only when valid.

~~~text
OrderRequest
     |
     v
validateOrderAsData
     |
     v
ValidationResult<ValidatedOrder>
     |
     v
routeAcceptedOrRejected
     |
     +-- accepted --> calculateQuote
     |
     +-- rejected --> explicit error result
~~~

This approach works well when one request needs multiple validation errors collected or when "rejected" is an expected business outcome. Yet in linear Spring Cloud Function composition, design intermediate types and branching explicitly; never treat `Result<T>` as `T`.

### 22.1. Should a Function Convert Exceptions Directly into an HTTP Response?

Usually a shared Function used across multiple adapters should not return `ResponseEntity<?>` just to catch errors. Doing so couples the core to HTTP and prevents natural reuse in event or serverless adapters.

Better: let the domain produce **business-meaningful exceptions or results**, let the HTTP layer convert them to status/body, let messaging convert them to nack/DLQ, and let serverless follow the trigger's handler contract.

## 23. Unit Tests: Failures Blocked Before Writing

A good test should verify two things:

1. The error occurs with the **right type and right timing**.
2. The side-effecting step is never called when input is invalid.

### 23.1. Testing an Imperative Pipeline

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

class ImperativeCatchBoundaryTest {

    @Test
    void invalidInputStopsBeforeSave() {
        OrderFunctions definitions = new OrderFunctions();

        Function<OrderRequest, Quote> core =
                definitions.validateOrder()
                           .andThen(definitions.calculateQuote());

        AtomicInteger saveCalls = new AtomicInteger();

        Consumer<Quote> save =
                quote -> saveCalls.incrementAndGet();

        Consumer<OrderRequest> pipeline =
                input -> save.accept(core.apply(input));

        assertThrows(InvalidOrderException.class,
                () -> pipeline.accept(
                    new OrderRequest("ORD-801", 0)));

        assertEquals(0, saveCalls.get());

        pipeline.accept(new OrderRequest("ORD-801", 2));
        assertEquals(1, saveCalls.get());
    }
}
~~~

Here the validation Function rejects invalid data; the `Consumer` runs only after the core returns a `Quote`. By counting invocations, the test verifies **the side-effect boundary**, not just the exception.

### 23.2. Testing That Storage Failures Are Not Swallowed

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
import example.functions.OrderErrors.QuoteStorageException;

class StorageFailureBoundaryTest {

    @Test
    void storageFailurePropagatesToCaller() {
        OrderFunctions definitions = new OrderFunctions();

        Function<OrderRequest, Quote> core =
                definitions.validateOrder()
                           .andThen(definitions.calculateQuote());

        AtomicInteger saveAttempts = new AtomicInteger();

        Consumer<Quote> failingStore = quote -> {
            saveAttempts.incrementAndGet();
            throw new QuoteStorageException(
                    "DB timeout", new IllegalStateException());
        };

        Consumer<OrderRequest> pipeline =
                input -> failingStore.accept(core.apply(input));

        assertThrows(QuoteStorageException.class,
                () -> pipeline.accept(
                    new OrderRequest("ORD-802", 2)));

        assertEquals(1, saveAttempts.get());
    }
}
~~~

This test only confirms **the save call was attempted once and the error reached the caller**. It **does not prove** the database did not commit; real systems need storage/transaction tests and idempotency checks.

### 23.3. When Catching to Remap Exceptions, Test the Cause Too

If an adapter translates a database error to `QuoteStorageException`, verify that the original cause is preserved and not every error is relabeled transient.

~~~java
QuoteStorageException ex = assertThrows(
        QuoteStorageException.class,
        () -> failingAdapter.save(quote));

assertNotNull(ex.getCause());
~~~

Here `failingAdapter` is a `QuoteStore` implementation configured to fail and `quote` is the input quote; the test needs `assertThrows` and `assertNotNull` imported. This is an assertion pattern for an adapter with real exception translation, not the `InMemoryQuoteStore` from section 5.

## 24. StepVerifier: Verifying onErrorResume Scope and Retries

### 24.1. Outer onErrorResume Stops Source Processing

~~~java
package example.functions;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class OuterErrorBoundaryTest {

    @Test
    void fallbackAtEndDoesNotResumeRemainingSource() {
        Flux<Integer> result =
                Flux.just("2", "bad", "5")
                    .map(Integer::parseInt)
                    .onErrorResume(
                        NumberFormatException.class,
                        error -> Flux.just(-1));

        StepVerifier.create(result)
                .expectNext(2, -1)
                .verifyComplete();
    }
}
~~~

As defined: the fallback replaces the failed chain without returning to emit `5`.

### 24.2. Catching Inside Each Inner Publisher Allows Continuation

~~~java
package example.functions;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class PerItemErrorBoundaryTest {

    @Test
    void badElementDoesNotStopIndependentElements() {
        Flux<Integer> result =
                Flux.just("2", "bad", "5")
                    .concatMap(raw ->
                        Mono.fromCallable(
                            () -> Integer.parseInt(raw))
                            .onErrorResume(
                                NumberFormatException.class,
                                error -> Mono.empty()));

        StepVerifier.create(result)
                .expectNext(2, 5)
                .verifyComplete();
    }
}
~~~

This test confirms the `onErrorResume` boundary sits inside **each element**. When applied to a broker, do not skip quarantining/logging/acking bad messages per policy.

### 24.3. Retry Outside Side Effects Can Replay Already-Processed Elements

~~~java
package example.functions;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class RetrySideEffectTest {

    @Test
    void retryResubscribesAndRepeatsEarlierSideEffect() {
        AtomicInteger saves = new AtomicInteger();

        Flux<Integer> result =
                Flux.just("1", "bad", "3")
                    .map(Integer::parseInt)
                    .doOnNext(value -> saves.incrementAndGet())
                    .retry(1);

        StepVerifier.create(result)
                .expectNext(1, 1)
                .expectError(NumberFormatException.class)
                .verify();

        assertEquals(2, saves.get());
    }
}
~~~

`doOnNext` in this test simulates a side effect with a counter. It demonstrates that **retry placement** can re-execute a step that already succeeded on the previous subscription.

### 24.4. Testing Direct Errors vs. Reactive Errors

~~~java
package example.functions;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.function.Function;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class EagerVsDeferredTest {

    @Test
    void fromCallableMovesErrorToSubscriber() {
        Function<String, Mono<Integer>> eager =
                input -> Mono.just(Integer.parseInt(input));

        Function<String, Mono<Integer>> deferred =
                input -> Mono.fromCallable(
                    () -> Integer.parseInt(input));

        assertThrows(NumberFormatException.class,
                () -> eager.apply("bad"));

        Mono<Integer> result = assertDoesNotThrow(
                () -> deferred.apply("bad"));

        StepVerifier.create(result)
                .expectError(NumberFormatException.class)
                .verify();
    }
}
~~~

This test shows that `try/catch` or `assertThrows` around `apply` does not replace `StepVerifier` when work is deferred until subscription.

## 25. Integration Testing FunctionCatalog and Boundaries

The earlier unit tests do not verify whether Spring registered the beans properly. Create a Spring Boot class in package `example.functions`:

~~~java
package example.functions;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrderApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

In an application with `OrderFunctions`, `InMemoryQuoteStore`, Spring Cloud Function context, and compatible Spring Boot Test dependencies, you can test:

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

@SpringBootTest(classes = OrderApplication.class)
class OrderCatalogBoundaryTest {

    @Autowired
    FunctionCatalog catalog;

    @Autowired
    InMemoryQuoteStore store;

    @Test
    void validQuoteIsCalculatedByName() {
        Function<OrderRequest, Quote> pipeline =
                catalog.lookup("validateOrder|calculateQuote");

        assertNotNull(pipeline);

        assertEquals(
                new Quote("ORD-901", 2, 250_000L),
                pipeline.apply(new OrderRequest("ORD-901", 2)));
    }

    @Test
    void invalidInputCannotReachConsumer() {
        Consumer<OrderRequest> pipeline =
                catalog.lookup(
                    "validateOrder|calculateQuote|saveQuote");

        assertNotNull(pipeline);

        assertThrows(InvalidOrderException.class,
                () -> pipeline.accept(
                    new OrderRequest("ORD-902", 0)));

        assertNull(store.find("ORD-902"));
    }

    @Test
    void repeatedValidInputDoesNotCreateTwoEntries() {
        Consumer<OrderRequest> pipeline =
                catalog.lookup(
                    "validateOrder|calculateQuote|saveQuote");

        assertNotNull(pipeline);

        OrderRequest request = new OrderRequest("ORD-903", 2);

        pipeline.accept(request);
        pipeline.accept(request);

        assertEquals(
                new Quote("ORD-903", 2, 250_000L),
                store.find("ORD-903"));
    }
}
~~~

This test verifies name wiring and side effects within the JVM. **It does not prove durable multi-instance storage transactions** and does not exercise a real binding or HTTP adapter. Using distinct keys avoids simple collisions across tests; with parallel tests and shared contexts, you still need proper isolation or resets.

### 25.1. Negative Tests for Lookup Failures

An invalid name expression may be rejected at lookup time or at execution time, depending on the version and wrapper behavior. Do not hard-code an assumption that every invalid expression returns `null`. Tests should follow the contract of the active version and check that **no unintended side effects occur**.

### 25.2. Adapter Testing Remains a Separate Layer

| Test Layer | What It Verifies |
|---|---|
| Unit `Function` | Input/rule failures emitted correctly |
| Unit `QuoteStore` | Conflicts, idempotency, exception translation |
| Unit Reactor | `onErrorResume` scope, retry replay behavior |
| Spring context/catalog | Bean registration, name composition, input/output types |
| HTTP adapter | Body, status, error handler, timeouts |
| Message binder | Converters, ack/nack, retry/DLQ, redelivery |
| Serverless handler | Event mapping, invocation timeouts/retries |
| Fault-injection / real storage | Ambiguous commits, race conditions, uniqueness |

A passing catalog test does not prove an adapter subscribed to a Publisher or mapped errors to the right status or nack.

## 26. Checklist for Choosing Error-Handling Locations

Before finalizing a Spring Cloud Function pipeline, answer:

1. **At which step does the error occur?** Converter, validation, Function, Consumer, or adapter?
2. **When does it occur?** `lookup`, `apply`, assembly, subscription, or post-commit?
3. **Does the catching layer have enough context to recover properly?** Is there an approved fallback?
4. **Which category does the error belong to?** Input, domain rejection, conflict, transient I/O, or programming bug?
5. **If the error is ignored, will the business falsely report success?**
6. **If retried, which operations run again?** The whole chain, an inner Publisher, or only the storage call?
7. **Have any side effects already executed before the error?** Are transactions, idempotency keys, and uniqueness in place?
8. **Must items be handled individually?** Or should a single error stop the entire Flux?
9. **Does the error signal reach the adapter?** Who subscribes to the Publisher?
10. **What will the adapter do?** HTTP status, ack/nack, DLQ, or serverless retry?
11. **Is the error logged/measured usefully once?** Are cause and correlation ID preserved?
12. **Do tests verify both the error and the absence of unintended side effects?**

A helpful practice is to draw the pipeline and mark **data flow**, **error points**, **commit points**, **retry points**, and **response points** before writing catch blocks or Reactor operators.

## 27. Practice Exercises

**Exercise 1 — Catching Parse Errors.** Given `parseQuantity: Function<String,Integer>`, when `Integer.parseInt` throws `NumberFormatException`, where should it be converted into `InvalidOrderException` to preserve field information?

**Exercise 2 — Catching Before Side Effects.** Given `validateOrder → calculateQuote → saveQuote`, with quantity `0`, which step throws? Why must tests assert `saveQuote` was not called?

**Exercise 3 — Write Followed by Timeout.** `saveQuote` committed, yet confirmation was lost. The application layer catches `QuoteStorageException`. Can it immediately return "not saved"? What mechanism is needed?

**Exercise 4 — Flux-Wide onErrorResume.** Given `Flux.just("2","bad","5").map(Integer::parseInt).onErrorResume(ex -> Flux.just(-1))`, what is the output? Why is `5` missing?

**Exercise 5 — Per-Message Errors.** Write a pipeline using `concatMap` and `Mono.fromCallable` so `"bad"` does not block `"5"`. Why must production not silently discard bad messages?

**Exercise 6 — doOnError Before or After Fallback?** To count source errors that were recovered, where do you place `doOnError` relative to `onErrorResume`? What if you want to count unrecovered errors?

**Exercise 7 — Retry Filter.** An adapter maps `TemporaryDatabaseException` to `ApplicationException` before `retryWhen`. What problem does a filter matching the old type face? Propose a fix.

**Exercise 8 — Retry Boundary.** A pipeline computes a Quote, writes to DB, and publishes an event. Which steps can a trailing `retryWhen` re-run? Describe how to protect against already-committed writes.

**Exercise 9 — Adapters.** The same `InvalidOrderException` occurs over HTTP and Kafka. Why should `validateOrder` not build a `ResponseEntity` or call a DLQ directly?

**Exercise 10 — FunctionCatalog.** What is the overall contract of `"validateOrder|calculateQuote|saveQuote"`? If `lookup` fails due to a wrong name, is that a user input error?

**Exercise 11 — Testing.** Write at least one `assertThrows` test for an imperative Function and one `StepVerifier.expectError` test for a reactive mapper. What else must be verified if the pipeline includes a DB-writing Consumer?

**Exercise 12 — Serverless.** A handler times out after storage commits. The platform retries the invocation. Does catching exceptions in the handler prevent duplicate writes? How should idempotency be designed?

### Suggested Answers

- **Exercise 1:** Catch inside the parser to translate into a domain error carrying `quantity` context, then let the adapter decide the protocol response.
- **Exercise 2:** `validateOrder` throws; asserting `saveQuote` call count is 0 catches wrong ordering or hidden side effects.
- **Exercise 3:** No. Commit may already have succeeded; look up by idempotency key or perform safe retries backed by uniqueness/transactions.
- **Exercise 4:** Emits `2` then `-1` then completes; `onErrorResume` replaces the remainder of the stream after the error.
- **Exercise 5:** Put `onErrorResume` inside the inner Mono, paired with quarantine/DLQ/metrics rather than silently dropping errors.
- **Exercise 6:** Measure source errors before `onErrorResume`; measure unrecovered errors after.
- **Exercise 7:** The filter may fail to match; place retry before remapping or keep an identifiable type/cause.
- **Exercise 8:** A trailing retry can resubscribe to the entire process; use storage idempotency and an outbox or equivalent consistency mechanism when publishing events.
- **Exercise 9:** Domain logic must not depend on transport; HTTP returns status/body while the binder applies ack/retry/DLQ separately.
- **Exercise 10:** `Consumer<OrderRequest>`; a wrong-name lookup failure is usually a config/deployment issue, not a client error.
- **Exercise 11:** Direct throw and `onError` happen in different phases; with a Consumer, assert side effects do not occur on validation failure and are idempotent on retry.
- **Exercise 12:** Catching is not enough; use a stable key, atomic/unique storage writes, conflict detection, and an explicit retry policy.

## 28. Key Takeaways

- **Catch errors where enough context exists to decide correctly**, not blindly in every Function.
- Parsers/validators can translate technical failures into domain errors; the business core should not know HTTP statuses or DLQs.
- In imperative Java, exceptions typically propagate directly through `andThen` to `apply`/`accept`; in Reactor, mapper errors usually surface as `onError` upon subscription.
- `onErrorResume` at the end of a Flux replaces the stream on error; per-message processing requires an error boundary inside an inner Publisher.
- `doOnError` only observes, `onErrorMap` transforms error types, and `retryWhen` resubscribes upstream; **operator placement determines scope**.
- Never use fake fallbacks, exception-swallowing `catch (Exception)`, or post-commit retries without idempotency.
- `FunctionCatalog` and `spring.cloud.function.definition` compose/select logic; **they do not automatically supply retries, transactions, HTTP error mapping, or binder acknowledgements**.
- Reliability must be tested across layers: Function, storage/side effects, Reactor, catalog, and HTTP/event/serverless adapters.


