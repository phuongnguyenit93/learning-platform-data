# Distinguishing Direct Exceptions from Reactor Error Signals

## 1. Lesson Objectives

A Java function processing an order can raise an error immediately when `apply(...)` is called. Yet if the same calculation runs inside `Mono.map(...)` or `Flux.map(...)`, the failure typically surfaces as an `onError` signal **when the Publisher is subscribed to**, not when the pipeline is constructed.

This distinction directly affects system reliability: where you place `try/catch`, how you log, retry, handle invalid data, acknowledge messages, and verify side effects. Especially in Spring Cloud Function, the same business logic can be registered as a `Function`, composed via `FunctionCatalog`, and invoked through HTTP, event-driven systems, or serverless environments. Each adapter can decide when a subscription starts and how errors translate to the transport protocol.

In the **Reliability** chapter, this lesson helps you:

- Distinguish Java exceptions thrown **immediately during invocation** from errors emitted through `Publisher.onError`.
- Understand the **assembly (Publisher creation)**, **subscription**, and **signal-processing** phases.
- Know when `try/catch` works, and when you need `onErrorResume`, `onErrorMap`, and `StepVerifier`.
- Design synchronous and reactive Functions with clear generics, reusing a single business rule across multiple flows.
- Classify validation errors, infrastructure errors, and transient errors so invalid data is not retried.
- Control the ordering of validation and side effects, especially under retries or resubscriptions.
- Test `FunctionCatalog` behavior and HTTP/message/serverless boundaries without mistaking a successful `lookup` for successful data processing.

> In Reactor, non-fatal exceptions thrown **inside an operator callback** (such as `map`) are normally turned into `onError` signals. Errors occurring before the Publisher is created are still thrown directly; never assume "every reactive error is an `onError`."

## 2. Two Fundamental Error Channels

Consider a synchronous function:

~~~java
import java.util.function.Function;

Function<String, Integer> parseQuantity =
        text -> Integer.parseInt(text.trim());
~~~

With `parseQuantity.apply("abc")`, `NumberFormatException` is thrown immediately on the active call stack. To catch it, wrap the call in `try/catch`:

~~~java
try {
    int quantity = parseQuantity.apply("abc");
    System.out.println(quantity);
} catch (NumberFormatException ex) {
    System.out.println("Quantity is not an integer");
}
~~~

Put the same logic inside Reactor:

~~~java
import reactor.core.publisher.Flux;

Flux<Integer> quantities = Flux.just("10", "abc", "30")
        .map(parseQuantity);
~~~

That line usually only constructs the `Flux`. When a subscriber subscribes and requests elements, the sequence can be:

~~~text
onSubscribe
request
onNext(10)
onError(NumberFormatException)
~~~

The element `"30"` is not processed further in the default chain after a terminal `onError`.

| Criterion | Direct Exception | Reactor Error Signal |
|---|---|---|
| Where it occurs | On the current Java call | Inside the Publisher/subscription lifecycle |
| Example | `parse.apply("abc")` | `Flux.just("abc").map(parse)` |
| How it is observed | `try/catch`, `assertThrows` | `onError`, `StepVerifier.expectError` |
| Typical recovery | `catch` then return fallback or remap | `onErrorResume`, `onErrorReturn`, `onErrorMap` |
| Timing | Usually right when code executes the call | Usually when the source emits the failing element |
| Key nuance | Call never returns a result | Some `onNext` signals may already have been emitted before `onError` |

Reactor follows the signal rule **`onNext*` followed by a single terminal signal `onComplete` or `onError`**. Once `onError` is delivered to a subscriber, that chain does not normally emit further `onNext` signals.

## 3. Synchronous Exceptions in Function.apply

Suppose pricing logic accepts a quantity:

~~~java
import java.util.function.Function;

Function<Integer, Long> calculatePrice = quantity -> {
    if (quantity == null || quantity <= 0) {
        throw new IllegalArgumentException(
                "Quantity must be greater than 0");
    }
    return Math.multiplyExact(quantity.longValue(), 125_000L);
};
~~~

Calling:

~~~java
long total = calculatePrice.apply(2); // 250000
~~~

runs synchronously. For input `0`:

~~~java
calculatePrice.apply(0);
~~~

the exception is thrown before `apply` returns normally.

### 3.1. Why try/catch Fits Plain Java

~~~java
try {
    Long amount = calculatePrice.apply(0);
    System.out.println(amount);
} catch (IllegalArgumentException ex) {
    // Respond to data errors immediately at the Java boundary.
    System.out.println("ORDER_REJECTED");
}
~~~

This can be tested with JUnit:

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;
import org.junit.jupiter.api.Test;

@Test
void rejectsNonPositiveQuantity() {
    assertThrows(IllegalArgumentException.class,
            () -> calculatePrice.apply(0));
}
~~~

In this test snippet, `calculatePrice` is the Function declared above and supplied to the test.

### 3.2. Execution Timing Does Not Dictate the Interface Type

A `Function<T,R>` may perform blocking HTTP/JDBC calls or fast in-memory work. The Java signature describes only the input/output contract; **it does not guarantee non-blocking execution or thread safety**.

Conversely, a Function returning `Mono<R>` can throw an exception **immediately before creating the Mono** if code validates input outside the Publisher. See the next section.

## 4. Reactive: Creating a Publisher vs. Executing the Work

Reactor builds a description of a signal stream:

~~~java
import java.util.function.Function;
import reactor.core.publisher.Mono;

Function<Mono<String>, Mono<Integer>> parseMono =
        mono -> mono.map(Integer::parseInt);

Mono<Integer> result =
        parseMono.apply(Mono.just("abc"));
~~~

In this example, `parseMono.apply(...)` returns a Publisher. `Integer.parseInt("abc")` is generally not called yet at that moment, because `map` executes when a subscriber receives the element.

When a subscriber subscribes:

~~~java
result.subscribe(
        value -> System.out.println("Value: " + value),
        error -> System.err.println(
                "Error: " + error.getClass().getSimpleName()));
~~~

The error is typically delivered to the error callback. This `subscribe(...)` snippet only illustrates receiving signals; applications using WebFlux, Spring Cloud Stream, or serverless adapters should follow the framework's subscription and lifecycle management rather than calling `subscribe` ad hoc.

### 4.1. Assembly and Subscription

~~~text
Assembly phase (current Java call)
    Flux.just("10", "abc").map(Integer::parseInt)
                           |
                           v
                 Creates Publisher, does not parse yet

Subscription phase
    Subscriber subscribes / requests
                           |
                           v
                     parse "10"
                           |
                           v
                     onNext(10)
                           |
                           v
                     parse "abc"
                           |
                           v
               onError(NumberFormatException)
~~~

An operator using `map`/`filter` does not execute eagerly simply because the operator factory method ran. Still, **not everything inside a pipeline-building method is lazy**: code placed before `return flux.map(...)` runs immediately.

### 4.2. onError Is a Terminal Signal, Not a Data Value

`Mono<T>` can emit:

- One `onNext(T)` followed by `onComplete`.
- `onComplete` with no element.
- `onError(Throwable)`.

`Flux<T>` can emit zero or more `onNext(T)` signals, followed by `onComplete` or `onError`.

Because `onError` is an error signal, you **cannot treat it as a `T` item inside `Flux<T>`**. To represent business failures as data values, use an explicit result type such as `Result<T>` and design operators accordingly.

## 5. Errors Thrown Immediately While Building a Publisher

A reactive Function **can still throw synchronous exceptions**:

~~~java
import java.util.function.Function;
import reactor.core.publisher.Mono;

Function<String, Mono<Integer>> parseReactive = input -> {
    // This check runs IMMEDIATELY when apply is called.
    if (input == null) {
        throw new IllegalArgumentException(
                "Input must not be null");
    }

    // This parsing is deferred until subscription.
    return Mono.fromCallable(
            () -> Integer.parseInt(input));
};
~~~

When invoked:

~~~java
parseReactive.apply(null); // Throws IllegalArgumentException immediately.
~~~

However:

~~~java
Mono<Integer> result = parseReactive.apply("bad");
// The line above creates the Mono.

result.subscribe(
        System.out::println,
        error -> System.err.println(error.getMessage()));
// NumberFormatException is emitted via onError.
~~~

Inside the same Function, **two errors travel through two different channels** depending on whether code runs before or inside the Publisher.

### 5.1. Errors from Mono.just with an Eager Argument

~~~java
Function<String, Mono<Integer>> eager =
        input -> Mono.just(Integer.parseInt(input));
~~~

`Integer.parseInt(input)` is an argument to `Mono.just`, so Java evaluates it **before calling `Mono.just(...)`**. For `"bad"`, the exception occurs directly inside `apply`.

This is the fundamental difference from:

~~~java
Function<String, Mono<Integer>> deferred =
        input -> Mono.fromCallable(
                () -> Integer.parseInt(input));
~~~

In the `deferred` version, the lambda in `fromCallable` runs on subscription, and Reactor translates its failure into `onError`.

### 5.2. Why try/catch Around apply Is Not Enough

~~~java
try {
    Mono<Integer> result =
            deferred.apply("bad");

    // The apply method returns the Mono successfully.
} catch (NumberFormatException ex) {
    // This does not catch errors raised upon subscription.
}
~~~

`try/catch` remains useful for checking assembly-time logic or synchronous calls, but it **does not replace** handling a Publisher's error signal.

## 6. Mono.defer, Mono.fromCallable, and Mono.error

Common factories carry distinct semantics.

### 6.1. Mono.fromCallable: Deferring a Value-Producing Call

~~~java
Mono<Integer> parsed = Mono.fromCallable(
        () -> Integer.parseInt("bad"));
~~~

The `Callable` executes upon subscription; for normal parsing errors, the subscriber receives `onError(NumberFormatException)`. If the `Callable` returns `null`, `Mono.fromCallable` completes empty rather than emitting `onNext(null)`.

### 6.2. Mono.defer: Deferring Publisher Creation Itself

~~~java
Mono<Integer> parsed = Mono.defer(
        () -> Mono.just(Integer.parseInt("bad")));
~~~

`Mono.just(...)` sits inside the `defer` callback, so `Integer.parseInt` runs at subscription time. If the callback throws a regular exception, Reactor turns it into `onError`.

`Mono.defer` is useful when each subscription must **recreate a Publisher** using context at that moment. Be careful: side effects inside the callback can re-run on retries or resubscriptions.

### 6.3. Mono.error: Creating a Failing Publisher

~~~java
Mono<Integer> rejected =
        Mono.error(new IllegalArgumentException(
                "ORDER_INVALID"));
~~~

Creating `Mono.error(...)` does not `throw` the exception on the spot. The Publisher emits `onError` when subscribed to.

You can pass a `Supplier` variant to instantiate the exception per subscription when needed:

~~~java
Mono<Integer> rejected =
        Mono.error(() -> new IllegalArgumentException(
                "ORDER_INVALID"));
~~~

### 6.4. Quick Comparison Table

| Code Snippet | When Can the Exception Appear? |
|---|---|
| `Integer.parseInt("bad")` | Immediately |
| `Mono.just(Integer.parseInt("bad"))` | Immediately, before creating the Mono |
| `Mono.fromCallable(() -> Integer.parseInt("bad"))` | On subscribe → `onError` |
| `Mono.defer(() -> Mono.just(Integer.parseInt("bad")))` | On subscribe → `onError` |
| `Mono.error(new IllegalArgumentException())` | Publisher emits `onError` on subscribe |
| `Flux.just("bad").map(Integer::parseInt)` | When `map` processes the element → `onError` |

Do not contort contracts just to force every error into one shape. What matters is that error-handling boundaries are **clearly designed and tested**.

## 7. Function Signatures Commonly Confused

These three signatures mean different things:

~~~text
Function<OrderInput, Quote>
Function<OrderInput, Mono<Quote>>
Function<Mono<OrderInput>, Mono<Quote>>
~~~

| Contract | `apply` Parameter | `apply` Return Value |
|---|---|---|
| `Function<OrderInput,Quote>` | One `OrderInput` | One `Quote` |
| `Function<OrderInput,Mono<Quote>>` | One `OrderInput` | Publisher of at most one `Quote` |
| `Function<Mono<OrderInput>,Mono<Quote>>` | A `Mono` of `OrderInput` | A `Mono` of `Quote` |

Example lifting a synchronous calculation into reactive form:

~~~java
import java.util.function.Function;
import reactor.core.publisher.Mono;

Function<String, Integer> parseOne = Integer::parseInt;

Function<Mono<String>, Mono<Integer>> parseMono =
        mono -> mono.map(parseOne);
~~~

Here, `parseOne` stays a plain Java Function. `NumberFormatException` is thrown inside the `map` callback when an element arrives, so it normally surfaces as `onError`.

Do not chain `Function<String,Integer>.andThen(Function<Mono<Integer>,Mono<String>>)` directly in Java: output `Integer` is not `Mono<Integer>`. To compose them, align the intermediate type or add an explicit bridge.

### 7.1. map and flatMap Determine Error and Data Semantics

- `mono.map(Function<T,R>)`: callback returns a value `R`; exceptions inside the mapper usually become `onError`.
- `mono.flatMap(Function<T,Mono<R>>)`: callback returns a Publisher; errors can originate from either the callback or the inner Publisher.
- `flux.flatMap(Function<T,Publisher<R>>)`: can execute multiple inner Publishers concurrently, affecting ordering and error timing.
- `concatMap`: processes inner Publishers sequentially, typically suitable when strict ordering is required.

With `flatMap`, an error in one inner Publisher normally terminates the outer chain by default and can cancel in-flight work; check business requirements when multiple side effects run concurrently.

## 8. Spring Cloud Function Example: Quoting

We build one Function handling a single request and one Function transforming a `Flux`. Both share the same pricing rule.

### 8.1. Models and Business Error

~~~java
package example.functions;

public final class QuoteModels {

    private QuoteModels() {}

    public record OrderInput(String orderId, int quantity) {}

    public record Quote(String orderId, long totalVnd) {}
}
~~~

A dedicated validation exception helps identify errors that should not be retried:

~~~java
package example.functions;

public class InvalidOrderException extends RuntimeException {

    public InvalidOrderException(String message) {
        super(message);
    }
}
~~~

### 8.2. Imperative and Reactive Beans

~~~java
package example.functions;

import java.util.function.Function;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import example.functions.QuoteModels.OrderInput;
import example.functions.QuoteModels.Quote;

@Configuration
public class QuoteFunctions {

    @Bean
    public Function<OrderInput, Quote> quoteOne() {
        return input -> {
            if (input == null
                    || input.orderId() == null
                    || !input.orderId().matches("ORD-[0-9]+")
                    || input.quantity() <= 0) {
                throw new InvalidOrderException(
                        "Invalid order");
            }

            long total = Math.multiplyExact(
                    input.quantity(), 125_000L);

            return new Quote(input.orderId(), total);
        };
    }

    @Bean
    public Function<Flux<OrderInput>, Flux<Quote>> quoteStream(
            @Qualifier("quoteOne")
            Function<OrderInput, Quote> quoteOne) {

        // Mapper runs on subscription, not eagerly at apply.
        return orders -> orders.map(quoteOne);
    }

    @Bean
    public Function<Mono<OrderInput>, Mono<Quote>> quoteMono(
            @Qualifier("quoteOne")
            Function<OrderInput, Quote> quoteOne) {

        return order -> order.map(quoteOne);
    }

    @Bean
    public Function<Flux<Quote>, Flux<String>> formatQuoteStream() {
        return quotes -> quotes.map(
                quote -> quote.orderId()
                        + "=" + quote.totalVnd());
    }
}
~~~

Contract summary:

| Bean | Input | Output |
|---|---|---|
| `quoteOne` | `OrderInput` | `Quote` |
| `quoteStream` | `Flux<OrderInput>` | `Flux<Quote>` |
| `quoteMono` | `Mono<OrderInput>` | `Mono<Quote>` |
| `formatQuoteStream` | `Flux<Quote>` | `Flux<String>` |

In `quoteOne`, validation failure throws directly inside `apply(OrderInput)`. Yet when `quoteOne` runs through `Flux.map(quoteOne)`, that exception normally becomes an `onError` on the Flux.

### 8.3. Same Business Error, Two Expressions

Imperative Java:

~~~java
QuoteFunctions config = new QuoteFunctions();

try {
    config.quoteOne().apply(
            new QuoteModels.OrderInput("ORD-42", 0));
} catch (InvalidOrderException ex) {
    System.out.println("Rejected immediately in apply");
}
~~~

Reactive:

~~~java
import reactor.core.publisher.Flux;

Flux<QuoteModels.Quote> result =
        config.quoteStream(config.quoteOne())
              .apply(Flux.just(
                    new QuoteModels.OrderInput("ORD-42", 0)));

// The error typically appears only when result is subscribed to.
~~~

The same rule does not necessarily mean the same **time when the error is observed**.

## 9. FunctionCatalog and Composing Reactive Pipelines

Once Spring registers the Function beans, they can be looked up by name from `FunctionCatalog`. With the two beans from section 8:

~~~text
quoteStream|formatQuoteStream
~~~

Composition contract:

~~~text
Function<Flux<OrderInput>, Flux<Quote>>
            |
            v
Function<Flux<Quote>, Flux<String>>
            |
            v
Function<Flux<OrderInput>, Flux<String>>
~~~

Illustrative service:

~~~java
package example.functions;

import java.util.function.Function;

import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.stereotype.Service;

import reactor.core.publisher.Flux;
import example.functions.QuoteModels.OrderInput;

@Service
public class QuoteStreamService {

    private final FunctionCatalog catalog;

    public QuoteStreamService(FunctionCatalog catalog) {
        this.catalog = catalog;
    }

    public Flux<String> process(Flux<OrderInput> orders) {
        Function<Flux<OrderInput>, Flux<String>> pipeline =
                catalog.lookup(
                        "quoteStream|formatQuoteStream");

        if (pipeline == null) {
            throw new IllegalStateException(
                    "Quote pipeline not found");
        }

        return pipeline.apply(orders);
    }
}
~~~

With `OrderInput("ORD-42", 2)` and `OrderInput("ORD-43", 3)`, the output stream is expected to emit `"ORD-42=250000"` and `"ORD-43=375000"`. If an element has quantity `0`, `quoteOne` throws `InvalidOrderException` inside the mapper, and the error is typically delivered as `onError` when the subscriber reaches that element.

### 9.1. A Successful Lookup Does Not Prove the Pipeline Works

Wrong names, unregistered beans, uncomposable signatures, or type mismatches can appear right at `catalog.lookup(...)`. Other failures show up only at `apply` or upon subscription.

Therefore, integration tests should verify all four steps:

1. The catalog finds the bean or expression.
2. `apply` accepts the right input type and returns a Publisher matching the contract.
3. The subscriber receives the expected `onNext`, `onComplete`, or `onError`.
4. Side effects execute or are blocked according to business rules.

### 9.2. Configuring definition

~~~yaml
spring:
  cloud:
    function:
      definition: "quoteStream|formatQuoteStream"
~~~

Or:

~~~properties
spring.cloud.function.definition=quoteStream|formatQuoteStream
~~~

`spring.cloud.function.definition` selects the function expression for a compatible adapter. It **does not automatically open an HTTP endpoint**, create a message binding, set up a serverless trigger, subscribe to a Publisher, or define a retry policy.

### 9.3. Do Not Assume Mixed Composition Like Plain Java

`quoteOne` has type `Function<OrderInput,Quote>`, whereas `formatQuoteStream` accepts `Flux<Quote>`. Because `Quote` differs from `Flux<Quote>`, Java's `andThen` cannot directly connect those two signatures.

Spring Cloud Function has adaptation mechanisms depending on version and context, but you must not assume direct mixed composition behaves identically across every adapter. The `quoteStream` bean serves as an explicit bridge, removing ambiguity about types and error timing.

## 10. onError Terminates a Flux; What About Subsequent Elements?

Consider:

~~~java
Flux<Integer> numbers = Flux.just("4", "5", "bad", "6")
        .map(Integer::parseInt);
~~~

When subscribed, the stream typically emits:

~~~text
onNext(4)
onNext(5)
onError(NumberFormatException)
~~~

Element `"6"` is never emitted because `onError` is a terminal signal.

If you attach a fallback:

~~~java
Flux<Integer> recovered = numbers
        .onErrorResume(ex -> Flux.just(-1));
~~~

the result is `4, 5, -1` followed by `onComplete`. `-1` is the fallback item—**it does not mean the original source resumed from `"6"`**.

### 10.1. When You Want to Keep Processing Independent Events

When each element is a separate message, you can design **per-element** error handling:

~~~java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

Flux<Integer> valid = Flux.just("4", "bad", "6")
        .concatMap(raw ->
            Mono.fromCallable(() -> Integer.parseInt(raw))
                .onErrorResume(
                    NumberFormatException.class,
                    error -> Mono.empty()));
~~~

The output is `4` and `6`. `concatMap` processes each inner Publisher sequentially, while `onErrorResume` handles only the failing element.

**Note:** skipping bad messages is not always right. Real applications may need to send failures to a DLQ/quarantine, record message IDs and metrics, and honor the broker's acknowledgement rules.

### 10.2. Be Careful with onErrorContinue

`onErrorContinue` interacts with certain upstream operators in ways that are not always predictable in complex pipelines. When the goal is isolating failures per message, prefer creating an inner Publisher and handling `onErrorResume` **inside the inner Publisher** as above, under an explicit policy.

## 11. Reactor Error-Handling Operators

| Operator | Purpose | Changes the Terminal Signal? |
|---|---|---|
| `doOnError` | Observe errors, log, or record metrics | Does not recover from the error |
| `onErrorMap` | Transform the exception type | Still emits `onError` |
| `onErrorResume` | Switch to a fallback Publisher | Can recover |
| `onErrorReturn` | Return a fallback value | Can recover |
| `retry` / `retryWhen` | Resubscribe upstream | Can reprocess data |

### 11.1. doOnError Does Not Swallow Errors

~~~java
Flux<Integer> observed = Flux.just("bad")
        .map(Integer::parseInt)
        .doOnError(error ->
            System.err.println("Parse failed: "
                    + error.getClass().getSimpleName()));
~~~

`doOnError` only executes an observation callback. Without a recovery step, downstream still receives `onError`.

### 11.2. onErrorMap Changes the Error Type While Preserving the Cause

You can define an application exception:

~~~java
package example.functions;

public class OrderRejectedException extends RuntimeException {
    public OrderRejectedException(
            String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Then convert a parse error into a more easily classified exception:

~~~java
Flux<Integer> mapped = Flux.just("bad")
        .map(Integer::parseInt)
        .onErrorMap(NumberFormatException.class,
            error -> new OrderRejectedException(
                    "Invalid quantity", error));
~~~

This chain still ends in an error, but the exception is now `OrderRejectedException` with the original cause retained. Changing the exception type does not fix invalid input.

### 11.3. Use onErrorResume Only When a Fallback Is Valid

~~~java
Mono<Integer> parsed = Mono.fromCallable(
        () -> Integer.parseInt("bad"));

Mono<Integer> fallback = parsed.onErrorResume(
        NumberFormatException.class,
        error -> Mono.just(-1));
~~~

`-1` here only illustrates the operator. **Never use a dummy number in quotes or inventory** just to suppress an error if that value corrupts business semantics. Instead, convert the failure into a rejection response or quarantine the invalid input.

### 11.4. onErrorReturn Is Not Equivalent to Retry

~~~java
Mono<Integer> result =
        Mono.<Integer>error(new IllegalStateException("Unavailable"))
            .onErrorReturn(-1);
~~~

`onErrorReturn` replaces the error with a value and completes **without re-invoking the source**. By contrast, `retry` can resubscribe, causing the source to execute again—including any side effects inside it.

## 12. Retries Must Classify Error Types and Failure Timing

A validation error such as `quantity=0` will not become valid by repeating the same input. Attaching `retry(10)` usually just throws the same error repeatedly.

Conversely, a database or remote API can suffer transient timeouts. Bounded retries can fit **when the operation is safe to re-invoke**.

### 12.1. Bound and Filter Which Exceptions Are Retried

Define a transient infrastructure exception:

~~~java
package example.functions;

public class TemporaryDependencyException
        extends RuntimeException {

    public TemporaryDependencyException(String message) {
        super(message);
    }
}
~~~

A Publisher from an infrastructure adapter can be retried using `Retry`:

~~~java
import java.time.Duration;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

// remoteCall is a Mono<String> representing an external dependency.
Mono<String> retryable = remoteCall.retryWhen(
        Retry.backoff(2, Duration.ofMillis(100))
             .filter(error ->
                 error instanceof TemporaryDependencyException));
~~~

`Retry.backoff(2, ...)` allows at most **two additional retries** after the initial subscription, with backoff per Reactor configuration. Exceptions not matching the filter are not retried by this operator. Avoid stacking retries across multiple layers, which multiplies call counts unexpectedly.

### 12.2. Retry Means Resubscribe, Not Fixing Only the Failing Item

~~~java
Flux<Integer> retrying = Flux.just("1", "bad", "3")
        .map(Integer::parseInt)
        .retry(1);
~~~

A subscriber can receive:

~~~text
onNext(1)
onNext(1)
onError(NumberFormatException)
~~~

The source is resubscribed from the beginning. If a Consumer already wrote a record for `1`, the second pass can write a duplicate.

### 12.3. Errors Before a Publisher Exists Are Outside retryWhen

If `function.apply(input)` throws an exception **before returning a Mono/Flux**, you have no Publisher to attach `retryWhen` to. You can explicitly defer it:

~~~java
import reactor.core.publisher.Mono;

// quoteOne is a Function<OrderInput, Quote> provided by the application.
Mono<QuoteModels.Quote> deferredQuote =
        Mono.fromCallable(() ->
            quoteOne.apply(
                new QuoteModels.OrderInput("ORD-42", 2)));
~~~

Regular exceptions thrown inside the `Callable` are converted by Reactor into `onError`. Yet that **does not mean every exception should be retried**. Validation failures, authorization errors, and business conflicts require rejection or specialized handling.

## 13. Side Effects: onError Does Not Automatically Undo Data

Consider:

~~~text
Flux<OrderInput>
     |
     v
validate → calculate → saveQuote (DB commit)
                              |
                              v
                         nextStep fails
                              |
                              v
                            onError
~~~

Even though downstream receives `onError`, the database may already have committed. If the whole pipeline is retried, `saveQuote` may run again. **An `onError` signal does not imply transaction rollback.**

Distinguish three points in time:

1. **Error before side effect:** no data written yet.
2. **Error before commit:** check whether the transaction/storage rolls back.
3. **Error after commit but before response/ack:** data may already be saved while the caller does not know; retries risk duplicates.

### 13.1. Validate Before the Consumer

~~~java
import java.util.function.Consumer;
import java.util.function.Function;

Function<QuoteModels.OrderInput, QuoteModels.Quote> quoteOne =
        new QuoteFunctions().quoteOne();

Consumer<QuoteModels.Quote> store =
        quote -> System.out.println("Save: " + quote);

Consumer<QuoteModels.OrderInput> pipeline =
        input -> store.accept(quoteOne.apply(input));
~~~

If `quoteOne.apply(input)` throws `InvalidOrderException`, `store.accept(...)` is not called in the synchronous execution. When using `Flux.map(quoteOne)`, validation failures typically stop the stream before downstream processes that invalid item.

However, **items already written before the error are not automatically rolled back**. This matters for batches and message brokers.

### 13.2. Idempotency Protects Retries and Redeliveries

At the write boundary, you should have:

- A stable business key or idempotency key, such as `orderId`.
- Unique constraints or atomic write operations in storage. An unlocked `SELECT` followed by `INSERT` can race across instances.
- Rules for **same key with a different payload**.
- A recovery mechanism when the DB committed but the response/ack was lost.

If saving to a DB and then publishing an event, consider a transactional outbox or equivalent consistency pattern. Composing a `Function` with a `Consumer` does not automatically span DB and broker in one transaction.

### 13.3. Do Not Subscribe Unmanaged Inside a Consumer

~~~java
import java.util.function.Consumer;
import reactor.core.publisher.Flux;

Consumer<Flux<QuoteModels.Quote>> unsafeSink =
        flux -> flux.subscribe(
                quote -> System.out.println("Save: " + quote));
~~~

This example illustrates **what to avoid in production**. If a Consumer calls `subscribe` and immediately returns, the adapter may consider the invocation finished before all elements are written; errors will not propagate properly to the ack/retry layer.

With Spring Cloud Function/Stream, rely on the adapter's subscription management rather than assuming `Consumer<Flux<T>>` finishes all side effects when `accept` returns.

## 14. HTTP: Status Mapping Does Not Depend on Throw vs. onError

Suppose a controller calls a synchronous service:

~~~java
@PostMapping("/quotes/sync")
public QuoteModels.Quote quoteSync(
        @RequestBody QuoteModels.OrderInput input) {

    return quoteOne.apply(input);
}
~~~

`quoteOne` is the Function injected into the controller. If `apply` throws `InvalidOrderException`, the error happens on the request call stack. Spring MVC/WebFlux can map it via an exception handler as configured.

A reactive handler returning `Mono<Quote>`:

~~~java
@PostMapping("/quotes/reactive")
public Mono<QuoteModels.Quote> quoteReactive(
        @RequestBody QuoteModels.OrderInput input) {

    return Mono.fromCallable(() -> quoteOne.apply(input));
}
~~~

When WebFlux subscribes to the Publisher to produce the HTTP response, an exception from the `Callable` typically becomes `onError`. To compile and run, the controller needs the appropriate Spring Web imports, `Mono`, and an injected `quoteOne` field.

### 14.1. Do Not Wrap return in try/catch Assuming It Catches Async Errors

~~~java
try {
    return Mono.fromCallable(() -> quoteOne.apply(input));
} catch (InvalidOrderException ex) {
    // Cannot catch exceptions from the Callable at subscription time.
}
~~~

The line building the `Mono` does not normally throw exceptions from inside the `Callable`. The framework or reactive operators must observe the error signal after subscription.

### 14.2. Mapping by Error Category

| Error Category | Reference HTTP Behavior |
|---|---|
| Malformed payload / validation failure | 400 or 4xx per API contract |
| Unauthorized | 401/403 per security policy |
| Same idempotency key with different content | 409 if appropriate |
| Infrastructure dependency unavailable | Appropriate 5xx, consider retries |
| Unexpected system failure | 5xx, do not expose sensitive stack traces |

Whether an error is a synchronous exception or a Reactor signal **does not determine the HTTP status on its own**. Your API needs an explicit mapping policy.

### 14.3. Function Web Adapter Differs from a Custom Controller

Spring Cloud Function provides a web adapter depending on the starter and version. Endpoints, converters, and error mapping can differ from a hand-written `@RestController`. Do not assume `spring.cloud.function.definition` turns `InvalidOrderException` into HTTP 400 without configuring and testing it.

## 15. Messaging and Serverless: Avoid Infinite Retries on Poison Messages

A message with invalid JSON syntax may be rejected **before the Function runs** in the converter. A type-valid message with quantity `0` can raise `InvalidOrderException` from business logic. A database timeout is an entirely different infrastructure error.

~~~text
Broker event
    |
    v
Deserialize --- bad schema ---> adapter error policy
    |
    v
Validate  ----- invalid ------> reject / DLQ / quarantine
    |
    v
Business & Persist --- timeout ---> conditional retry
    |
    v
Ack per binder
~~~

A **poison message** continuously fails and cannot be fixed by repeating the exact same retry. Infinite retries can create an error loop or block valid messages.

| Error | Retry Same Payload? | Reference Handling |
|---|---|---|
| Deserialization/schema failure | Usually no | DLQ/quarantine |
| Validation failure | Usually no | Record error, observe |
| Authorization failure | Never use retries to bypass security | Reject |
| Database timeout | Yes if idempotent | Bounded retry/backoff |
| Lost ack after DB commit | Redelivery may occur | Storage-level idempotency |
| Unknown cause | Depends on classification | Investigate, circuit breaker/DLQ |

DLQ capabilities, ack behavior, retries, and bindings depend on the binder, broker, version, and configuration. Reactor's `onError` does not automatically correspond to a specific nack action: verify that the adapter observes the error signal within the proper lifecycle.

### 15.1. Serverless Has Both Error Modes Too

An invocation can throw immediately when the handler validates input, or return a Publisher/async value that fails during execution (if the adapter supports it). Sometimes data has committed before the invocation times out prior to responding.

The platform may retry based on the trigger type. Do not assume every serverless runtime treats `onError` identically or guarantees exactly-once execution; test the real handler and trigger policy.

## 16. Threading and Blocking When Handling Reactive Errors

`Mono.fromCallable(...)` defers the call, yet **does not move work onto another thread by itself**. If the `Callable` performs blocking JDBC I/O, it can block the subscriber or event-loop thread.

One way to isolate a blocking call:

~~~java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

// blockingGateway is an illustrative dependency provided by the application.
Mono<String> result = Mono.fromCallable(
        () -> blockingGateway.load("ORD-42"))
    .subscribeOn(Schedulers.boundedElastic());
~~~

`boundedElastic` is generally intended for a bounded amount of blocking work; it does not turn a blocking client into a non-blocking one, nor replace timeouts, connection pools, and concurrency limits.

If the `Callable` throws a regular exception on that scheduler, Reactor still normally emits `onError`. A `try/catch` around the `Mono`-creating line cannot catch exceptions thrown asynchronously.

Do not rely on thread names to decide error-handling behavior; record the exception cause, correlation ID, and handling ownership at the right boundary.

### 16.1. Do Not Absolutize the onError Rule

Constructors, argument checks, invalid null arguments in Reactor APIs, and code running before `return` can still throw immediately. Certain fatal/JVM errors also follow special rules. Always check **where code executes** instead of assuming every `Throwable` in reactive code becomes `onError`.

## 17. Unit Tests: Right Error Type and Right Timing

To test Reactor streams, add `reactor-test` and use `StepVerifier`—for example with Maven:

~~~xml
<dependency>
    <groupId>io.projectreactor</groupId>
    <artifactId>reactor-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Include compatible JUnit / Spring Boot Test and Reactor versions for your project. `StepVerifier` acts as a subscriber, verifying **actual emitted signals**, not just Publisher construction.

### 17.1. Direct Exception from a Function

~~~java
package example.functions;

import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.function.Function;

import org.junit.jupiter.api.Test;

import example.functions.QuoteModels.OrderInput;
import example.functions.QuoteModels.Quote;

class ImmediateExceptionTest {

    @Test
    void imperativeFunctionThrowsAtApply() {
        Function<OrderInput, Quote> quoteOne =
                new QuoteFunctions().quoteOne();

        assertThrows(InvalidOrderException.class,
                () -> quoteOne.apply(
                    new OrderInput("ORD-42", 0)));
    }
}
~~~

This test needs no Spring context or Publisher; the exception is thrown directly inside `quoteOne.apply(...)`.

### 17.2. Mapper Failures Surface via onError

~~~java
package example.functions;

import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.util.function.Function;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

import example.functions.QuoteModels.OrderInput;
import example.functions.QuoteModels.Quote;

class ReactiveErrorSignalTest {

    @Test
    void mapperFailureIsOnError() {
        QuoteFunctions config = new QuoteFunctions();

        Function<Flux<OrderInput>, Flux<Quote>> stream =
                config.quoteStream(config.quoteOne());

        Flux<Quote> result = stream.apply(Flux.just(
                new OrderInput("ORD-42", 2),
                new OrderInput("ORD-43", 0),
                new OrderInput("ORD-44", 3)));

        assertNotNull(result);

        StepVerifier.create(result)
                .expectNext(new Quote("ORD-42", 250_000L))
                .expectError(InvalidOrderException.class)
                .verify();
    }
}
~~~

`ORD-44` is not processed further by default because `ORD-43` causes a terminal error after `ORD-42`'s result was emitted.

### 17.3. Comparing Mono.just and Mono.fromCallable

~~~java
package example.functions;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.function.Function;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class EagerDeferredTest {

    @Test
    void eagerParsingThrowsBeforeMonoExists() {
        Function<String, Mono<Integer>> eager =
                value -> Mono.just(Integer.parseInt(value));

        assertThrows(NumberFormatException.class,
                () -> eager.apply("bad"));
    }

    @Test
    void deferredParsingSignalsError() {
        Function<String, Mono<Integer>> deferred =
                value -> Mono.fromCallable(
                    () -> Integer.parseInt(value));

        Mono<Integer> result = assertDoesNotThrow(
                () -> deferred.apply("bad"));

        StepVerifier.create(result)
                .expectError(NumberFormatException.class)
                .verify();
    }
}
~~~

Both tests use `Integer.parseInt("bad")`, yet demonstrate **two different error-reporting timings**.

## 18. Testing Retries and Side Effects

### 18.1. Retry Only Transient Errors

~~~java
package example.functions;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.util.retry.Retry;

class RetryErrorTest {

    @Test
    void transientFailureIsRetried() {
        AtomicInteger attempts = new AtomicInteger();

        Mono<Integer> remote = Mono.fromCallable(() -> {
            if (attempts.incrementAndGet() < 3) {
                throw new TemporaryDependencyException(
                    "Temporary failure");
            }
            return 42;
        });

        StepVerifier.create(remote.retryWhen(
                Retry.max(2).filter(error ->
                    error instanceof TemporaryDependencyException)))
                .expectNext(42)
                .verifyComplete();

        assertEquals(3, attempts.get());
    }

    @Test
    void validationFailureIsNotRetried() {
        AtomicInteger attempts = new AtomicInteger();

        Mono<Integer> rejected = Mono.fromCallable(() -> {
            attempts.incrementAndGet();
            throw new InvalidOrderException("Invalid input");
        });

        StepVerifier.create(rejected.retryWhen(
                Retry.max(2).filter(error ->
                    error instanceof TemporaryDependencyException)))
                .expectError(InvalidOrderException.class)
                .verify();

        assertEquals(1, attempts.get());
    }
}
~~~

The exceptions here are `InvalidOrderException` and `TemporaryDependencyException` defined earlier. `Retry.max(2)` permits up to two retries, without always having to exhaust them.

### 18.2. onError Does Not Automatically Roll Back Side Effects

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class SideEffectAfterErrorTest {

    @Test
    void previousWriteIsNotUndone() {
        List<Integer> saved = new CopyOnWriteArrayList<>();

        Flux<Integer> stream =
                Flux.just("1", "bad", "3")
                    .map(Integer::parseInt)
                    .doOnNext(saved::add);

        StepVerifier.create(stream)
                .expectNext(1)
                .expectError(NumberFormatException.class)
                .verify();

        assertEquals(List.of(1), saved);
    }
}
~~~

`doOnNext` serves only as an illustrative side effect. For a production database, you need transactions, idempotency, and dedicated retry handling rather than relying on `onError` for rollback.

## 19. Integration Testing with FunctionCatalog

Unit testing one Function does not verify whether Spring registered the beans and composed their names properly. A minimal Spring Boot application in package `example.functions`:

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

With `QuoteApplication`, `QuoteFunctions`, and Spring Cloud Function dependencies in the context, test the pipeline with `StepVerifier`:

~~~java
package example.functions;

import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.util.function.Function;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

import example.functions.QuoteModels.OrderInput;

@SpringBootTest(classes = QuoteApplication.class)
class QuoteCatalogErrorTest {

    @Autowired
    FunctionCatalog catalog;

    @Test
    void namedCompositionEmitsValuesAndCompletes() {
        Function<Flux<OrderInput>, Flux<String>> pipeline =
                catalog.lookup(
                    "quoteStream|formatQuoteStream");

        assertNotNull(pipeline);

        StepVerifier.create(pipeline.apply(Flux.just(
                new OrderInput("ORD-42", 2),
                new OrderInput("ORD-43", 3))))
                .expectNext("ORD-42=250000", "ORD-43=375000")
                .verifyComplete();
    }

    @Test
    void invalidOrderBecomesReactiveErrorSignal() {
        Function<Flux<OrderInput>, Flux<String>> pipeline =
                catalog.lookup(
                    "quoteStream|formatQuoteStream");

        assertNotNull(pipeline);

        StepVerifier.create(pipeline.apply(Flux.just(
                new OrderInput("ORD-42", 2),
                new OrderInput("ORD-43", 0))))
                .expectNext("ORD-42=250000")
                .expectError(InvalidOrderException.class)
                .verify();
    }
}
~~~

This test suite verifies name registration, type wiring, result transformation, and error emission on subscription inside a Spring context. It **does not replace** tests at HTTP, messaging, or serverless boundaries.

### 19.1. Catalog Tests Pass, Yet the Adapter Still Fails

Possible causes include:

- The adapter provides `Message<OrderInput>` while the pipeline expects `Flux<OrderInput>`.
- The converter fails to deserialize JSON into `OrderInput`.
- The adapter subscribes or manages lifecycle differently than expected.
- Headers or `content-type` do not match.
- The error signal is not translated into the designed response, ack, or retry.
- Imperative/reactive adaptation behavior changed across framework versions.

Therefore, when moving the same Function to another adapter, test real payloads, subscription behavior, error mapping, and acknowledgement semantics.

## 20. Error Diagnosis and Observability

### 20.1. Commonly Confused Scenarios

| Symptom | Possible Cause | How to Verify |
|---|---|---|
| `assertThrows` around `apply` misses error | Mapper runs at subscription time | Use `StepVerifier.expectError` |
| `Mono.just(parse(...))` throws immediately | Java evaluates argument before `just` | Consider `fromCallable` or `defer` |
| `doOnError` logs, yet subscriber still fails | Operator only observes | Explicitly recover or propagate to adapter |
| `onErrorResume` skips items after the error | It replaces the entire remainder with fallback | Design per-element error boundaries |
| `retry` causes duplicate writes | Resubscribes upstream with side effects | Add idempotency / transactions |
| `lookup` succeeds, nothing processes data | Not subscribed or adapter not triggered | Test real signals / adapter |
| No HTTP 400 on invalid input | Missing/incorrect error handler or mapping | Test status and response body |
| Broker loops on poison message | Retries do not distinguish permanent failures | Limit retries, DLQ/quarantine |
| DB committed, yet pipeline reports error | Failure occurred after commit | Check transactions, acks, and data state |
| Threads get blocked | Blocking I/O on unsuitable scheduler | Measure latency, threads/schedulers, and pool usage |

### 20.2. Observability at the Right Boundary

Record correlatable details:

- Trusted correlation ID / message ID and pipeline name.
- Failing processing step and error type.
- Error category: invalid input, conflict, transient dependency, unexpected.
- Retry count, processing duration, and commit/ack state when known.
- Messages routed to dead-letter or quarantine, plus post-retry success rates.

Do not log full sensitive payloads or tokens solely for debugging. When Reactor switches schedulers, traditional `ThreadLocal` values may not propagate context as expected; use context/observability propagation appropriate for your framework version.

### 20.3. Pre-Production Checklist

1. Can `Function.apply` throw before returning a Mono/Flux?
2. Which mappers execute only upon subscription?
3. Who subscribes to the Publisher, and who receives terminal `onError`?
4. Are `onErrorMap`, `onErrorResume`, or adapter error propagation used properly?
5. Are retries bounded and filtered to the right error types?
6. Can resubscription re-trigger data writes?
7. Are idempotency keys, uniqueness constraints, and transactions enforced in storage?
8. Does validation run ahead of side effects?
9. Does a single error in a Flux block subsequent items?
10. Have HTTP statuses, message ack/DLQ, and serverless retries been tested on the real adapter?
11. Is blocking I/O isolated with appropriate concurrency limits?
12. Do tests verify **both direct throws and `onError` signals**?

## 21. Practice Exercises

**Exercise 1 — When Does the Error Happen?** Compare `Mono.just(Integer.parseInt("bad"))` and `Mono.fromCallable(() -> Integer.parseInt("bad"))`. In which phase is the exception observed?

**Exercise 2 — try/catch.** Why might `try/catch` around `parseMono.apply(Mono.just("bad"))` fail to catch the error? Write an appropriate `StepVerifier` assertion.

**Exercise 3 — Flux Terminal Signal.** With `Flux.just("2","bad","9").map(Integer::parseInt)`, which signals are emitted? Is `9` still emitted?

**Exercise 4 — onErrorResume.** Add `onErrorResume(ex -> Flux.just(-1))` to Exercise 3. Describe the output and explain why `9` is missing.

**Exercise 5 — Per-Message.** Design handling for `"2"`, `"bad"`, and `"9"` so both valid items are still emitted. What policy must accompany skipping an invalid message?

**Exercise 6 — Retry.** Why can `Flux.just("1","bad").map(Integer::parseInt).retry(1)` emit `1` twice? If database writes follow `map`, how must you protect them?

**Exercise 7 — Composition.** Given `quoteOne: Function<OrderInput,Quote>` and `formatQuoteStream: Function<Flux<Quote>,Flux<String>>`, why can Java `andThen` not chain them directly? Propose a bridge.

**Exercise 8 — Error Classification.** One message has quantity `0`; another hits a database timeout **after commit**. Should they share the same retry and ack behavior?

**Exercise 9 — Testing.** Propose one `assertThrows` test, one `StepVerifier` test, one filtered retry test, and one catalog integration test; state each test's goal.

**Exercise 10 — Side Effects.** A Flux wrote two quotes and then failed on the third item. Why does downstream receiving `onError` not mean the database rolled back the first two records?

### Suggested Answers

- **Exercise 1:** `Mono.just(parse(...))` evaluates its argument immediately; `fromCallable` turns regular errors into `onError` on subscribe.
- **Exercise 2:** `map` is lazy; use `StepVerifier.create(publisher).expectError(NumberFormatException.class).verify()`.
- **Exercise 3:** `onNext(2)` then `onError(NumberFormatException)`; `9` is not emitted.
- **Exercise 4:** `2`, then `-1`, then complete; the fallback does not resume upstream.
- **Exercise 5:** Use an inner `Mono.fromCallable(...).onErrorResume(...)` inside `concatMap`, and quarantine/record invalid messages.
- **Exercise 6:** Retry resubscribes upstream; use idempotency keys, transactions, and bounded retries.
- **Exercise 7:** `Quote` differs from `Flux<Quote>`; create `quoteStream: Function<Flux<OrderInput>,Flux<Quote>>` via `flux.map(quoteOne)`.
- **Exercise 8:** Validation errors typically do not retry; post-commit timeouts require state checks or idempotent deduplication.
- **Exercise 9:** Direct throw tests the call stack; `StepVerifier` tests error signals; retry test verifies attempt count; catalog test checks name/type wiring and results.
- **Exercise 10:** Reactor does not automatically roll back DB writes; design transactions at the right boundary along with idempotency and delivery handling.

## 22. Key Takeaways

- A synchronous Java function can throw exceptions **immediately when `Function.apply` is called**.
- Inside Reactor `map`, `flatMap`, `fromCallable`, or `defer`, normal callback failures typically surface via **`onError` upon subscription**.
- `Mono.just(calculate())` can throw directly because Java evaluates `calculate()` before constructing the Mono.
- `onError` is a terminal signal, not a `T` element, and does not automatically roll back committed side effects.
- `onErrorResume` switches to a fallback; `doOnError` only observes; `retry`/`retryWhen` resubscribe upstream and can repeat processing.
- `FunctionCatalog` and `spring.cloud.function.definition` compose/select functions; they do not automatically determine HTTP error mapping, binder acks, DLQs, transactions, or serverless retries.
- Test with `assertThrows`, `StepVerifier`, `FunctionCatalog`, and adapters at the **right layer** to verify real failure behavior.






