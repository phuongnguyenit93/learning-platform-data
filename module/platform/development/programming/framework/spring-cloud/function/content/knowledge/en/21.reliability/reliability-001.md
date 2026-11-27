# Designing Pure Functions and Isolating Side Effects

## 1. Lesson Objectives

Spring Cloud Function lets you build business logic using `Supplier`, `Function`, and `Consumer` beans, compose them with `FunctionCatalog`, and reuse the same logic over Java, HTTP, event-driven systems, or serverless platforms when an appropriate adapter is present. However, syntactically valid composition **does not mean** a pipeline is reliable. An operation re-invoked after a timeout or a redelivered message can cause duplicate writes.

In the **Reliability** chapter, this lesson explains how to keep **computation logic pure** and place **side effects at controlled boundaries**. The goal is to clarify which work can be recomputed safely and which work must handle retries, transactions, and idempotency.

After this lesson, you will be able to:

- Identify pure functions, shared state, and hidden side effects.
- Distinguish purity, determinism, idempotency, and transactions.
- Design the **Functional Core, Imperative Shell** pattern in Spring Cloud Function.
- Build pure Functions for parsing, validation, and pricing.
- Place a Consumer or write port at the boundary, after processing succeeds.
- Test the core, duplicate-write protection, and composition via `FunctionCatalog`.
- Turn external data such as time, UUIDs, and price tables into explicit inputs.
- Understand the limitations of retries, reactive subscriptions, and HTTP/message/serverless adapters.

## 2. Pure Functions and Side Effects

A pure function has two characteristics:

1. Given the same input and the same rules, it produces the same output.
2. It does not mutate external state or produce observable side effects across calls.

Example of a pure Java function:

~~~java
import java.util.function.Function;

Function<Integer, Long> calculateTotal =
        quantity -> quantity * 125_000L;

System.out.println(calculateTotal.apply(2)); // 250000
System.out.println(calculateTotal.apply(2)); // 250000
~~~

This function does not depend on the current time, a database, or a shared counter.

Conversely:

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Function;

AtomicInteger sequence = new AtomicInteger();

Function<String, String> generateCode =
        prefix -> prefix + sequence.incrementAndGet();

System.out.println(generateCode.apply("ORD-")); // ORD-1
System.out.println(generateCode.apply("ORD-")); // ORD-2
~~~

With the same `"ORD-"` input, the result changes because the function reads and mutates `sequence`. This is an **impure** Function.

| Operation | Purity | Reason |
|---|---|---|
| `trim`, `toUpperCase(Locale.ROOT)` | Can be pure | Processes based on input, does not mutate external state |
| `Math.multiplyExact` | Pure | Deterministic computation, may throw an error on overflow |
| `Instant.now()` | Impure | Depends on the time of invocation |
| `UUID.randomUUID()` | Impure | Random result outside the input |
| Reading database/API inside the function | Impure | Result depends on external state |
| `repository.save` or sending to a broker | Impure | Mutates an external system |
| Mutating a mutable field on a shared bean | Impure | Other calls can observe the change |
| Writing logs or metrics | Side effect in the strict sense | Produces output outside the return value |

Logging is still needed for production. We do not need to forbid every side effect, but rather clearly define **where they are allowed**.

### 2.1. Pure Functions Can Still Throw Errors

~~~java
Function<String, Integer> parsePositive = text -> {
    int value = Integer.parseInt(text.trim());
    if (value <= 0) {
        throw new IllegalArgumentException("Quantity must be positive");
    }
    return value;
};
~~~

This function does not modify external data. For invalid input, the error is part of a known contract. If you need to represent multiple errors without throwing exceptions, you can use a type like `ValidationResult<T>` or `Either<Error,T>`.

### 2.2. The Function Interface Does Not Guarantee Purity

A `Function<Order,Quote>` can secretly read from a database. A `Supplier<String>` can pull a record from a queue. A `Consumer<Quote>` can publish an event. Java's functional interfaces define **inputs and outputs**, without checking whether there are side effects inside.

In particular, Spring Cloud Function allows reusing beans and does not enforce that beans are stateless or deterministic. The designer must uphold those contracts themselves.

## 3. Pure Is Different from Idempotent

**Pure:** same input yields the same output and does not mutate external state.

**Idempotent:** invoking the same operation again causes no additional effect after the first call, with respect to the state the business cares about.

For example:

~~~java
Function<Integer, Integer> addOne = value -> value + 1;
~~~

`addOne` is a pure function, yet `addOne(addOne(3)) = 5` differs from `addOne(3) = 4`; it is not idempotent in the mathematical sense `f(f(x)) = f(x)`.

Meanwhile, a `Consumer<Quote>` that writes a record keyed by `orderId` can be **impure yet idempotent**: writing the same quote again does not create a second record.

| Property | Question to Answer |
|---|---|
| Pure | Does the function read/mutate state outside its input? |
| Deterministic | Given the same data and rules, is the result the same? |
| Idempotent | Does re-executing the same request change state any further? |
| Atomic | Do the changes succeed or fail together? |
| Delivery | Can messages be lost, delivered twice, or retried? |

You must distinguish these properties when building reliable systems. `FunctionCatalog` and the `|` operator do not automatically provide transactions or exactly-once semantics.

## 4. Functional Core and Imperative Shell

A useful way to organize code is **Functional Core, Imperative Shell**.

~~~text
HTTP request / Message / Serverless event
                    |
                    v
           Imperative Shell
       deserialize, read context, auth
                    |
                    v
             Functional Core
      normalize → parse → validate → calculate
                    |
                    v
                 Quote
                    |
                    v
           Imperative Shell
       persist / publish / ack / response
~~~

The core performs computation based on explicit inputs, while the outer shell handles I/O, obtaining time, generating IDs, managing transactions, and handling retries.

In Spring Cloud Function:

| Java Type | Method | Common Role | Pure by Default? |
|---|---|---|---|
| `Supplier<T>` | `get()` | Fetch/produce source data | No |
| `Function<T,R>` | `apply(T)` | Transform and compute | No |
| `Consumer<T>` | `accept(T)` | Write/save/send result | No |
| `Runnable` | `run()` | Task without input/output | No |

Using `Function` for the pure core and `Consumer` for the final step with side effects is a **good design convention**, not something enforced automatically by Java or the framework.

## 5. Running Example: Calculating and Recording a Quote

We design a feature that accepts this input:

~~~text
" ord-42, sku-7, 2 "
~~~

Processing flow:

~~~text
String
   |
   v
normalizeOrder             Function<String,String>            (pure)
   |
   v
parseOrder                 Function<String,OrderDraft>        (pure)
   |
   v
validateOrder              Function<OrderDraft,ValidatedOrder>(pure)
   |
   v
calculateQuote             Function<ValidatedOrder,Quote>     (pure)
   |
   +-----------------------------+
   |                             |
   v                             v
Return Quote                 recordQuote
                             Consumer<Quote>
                                  |
                                  v
                         QuoteRecorder (I/O)
~~~

There are two needs: **only calculating the quote** and **calculating then saving**. Both share the same core; side effects exist only in the second branch.

### 5.1. Data Model

Using Java 17:

~~~java
package example.functions;

public final class OrderModels {

    private OrderModels() {}

    public record OrderDraft(
            String orderId,
            String sku,
            int quantity) {}

    public record ValidatedOrder(
            String orderId,
            String sku,
            int quantity) {}

    public record Quote(
            String orderId,
            String sku,
            int quantity,
            long totalVnd) {}
}
~~~

`OrderDraft` has been parsed but not yet validated; `ValidatedOrder` has passed the rules; `Quote` is the business result. Using meaningful records helps catch type errors during composition and avoids passing `Map<String,Object>` between every step.

Records are only immutable at the field level; if a record contains a mutable collection, defensive copying is still needed. Furthermore, the name `ValidatedOrder` does not by itself stop arbitrary code from creating an invalid object; when needed, control access via constructors or factories.

## 6. Defining Pure Functions

Spring Boot / Spring Cloud Function example:

~~~java
package example.functions;

import java.util.Locale;
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import example.functions.OrderModels.OrderDraft;
import example.functions.OrderModels.ValidatedOrder;
import example.functions.OrderModels.Quote;

@Configuration
public class QuoteFunctions {

    @Bean
    public Function<String, String> normalizeOrder() {
        return raw -> {
            if (raw == null) {
                throw new IllegalArgumentException(
                        "Order input must not be null");
            }
            return raw.trim().toUpperCase(Locale.ROOT);
        };
    }

    @Bean
    public Function<String, OrderDraft> parseOrder() {
        return raw -> {
            if (raw == null) {
                throw new IllegalArgumentException(
                        "Order input must not be null");
            }

            String[] parts = raw.split(",", -1);
            if (parts.length != 3) {
                throw new IllegalArgumentException(
                        "Expected orderId,sku,quantity");
            }

            String orderId = parts[0].trim();
            String sku = parts[1].trim();

            final int quantity;
            try {
                quantity = Integer.parseInt(parts[2].trim());
            } catch (NumberFormatException ex) {
                throw new IllegalArgumentException(
                        "Quantity must be an integer", ex);
            }

            return new OrderDraft(orderId, sku, quantity);
        };
    }

    @Bean
    public Function<OrderDraft, ValidatedOrder> validateOrder() {
        return draft -> {
            if (draft == null
                    || draft.orderId() == null
                    || !draft.orderId().matches("ORD-[0-9]+")
                    || draft.sku() == null
                    || !draft.sku().matches("SKU-[0-9]+")
                    || draft.quantity() < 1
                    || draft.quantity() > 100) {
                throw new IllegalArgumentException(
                        "Invalid order");
            }

            return new ValidatedOrder(
                    draft.orderId(),
                    draft.sku(),
                    draft.quantity());
        };
    }

    @Bean
    public Function<ValidatedOrder, Quote> calculateQuote() {
        return order -> {
            long unitPriceVnd = 125_000L;
            long totalVnd = Math.multiplyExact(
                    order.quantity(), unitPriceVnd);

            return new Quote(
                    order.orderId(),
                    order.sku(),
                    order.quantity(),
                    totalVnd);
        };
    }
}
~~~

These Functions do not access a database, do not use clocks or randomness, and do not mutate shared state. The fixed unit price serves this lesson; for dynamic pricing, pass a price snapshot as input as shown in a later section.

Result for input `" ord-42, sku-7, 2 "`:

~~~text
Quote[orderId=ORD-42, sku=SKU-7, quantity=2, totalVnd=250000]
~~~

### 6.1. Why Removing Side Effects from Functions Helps

- You can test `calculateQuote` without running a database or broker.
- Retrying the calculation does not create a new record.
- You can reuse the same Function for both preview mode and actual write mode.
- Results are easy to compare across executions given the same input and policy.
- When an error occurs, you can pinpoint which step failed before the I/O boundary.

## 7. Composing the Pure Core in Java

~~~java
import java.util.function.Function;

import example.functions.OrderModels.OrderDraft;
import example.functions.OrderModels.ValidatedOrder;
import example.functions.OrderModels.Quote;

QuoteFunctions config = new QuoteFunctions();

Function<String, String> normalize =
        config.normalizeOrder();
Function<String, OrderDraft> parse =
        config.parseOrder();
Function<OrderDraft, ValidatedOrder> validate =
        config.validateOrder();
Function<ValidatedOrder, Quote> price =
        config.calculateQuote();

Function<String, Quote> pipeline =
        normalize.andThen(parse)
                 .andThen(validate)
                 .andThen(price);

Quote result = pipeline.apply(" ord-42, sku-7, 2 ");
System.out.println(result.totalVnd()); // 250000
~~~

`andThen` executes normalize → parse → validate → price. Java generics check the intermediate types. Calling the `@Bean` methods directly here is only for illustrating plain Java; in a Spring context, inject the beans or use `FunctionCatalog`.

### 7.1. Validation Runs Before Writing

The input `"ORD-42,SKU-7,0"` parses successfully but fails in `validateOrder`. As long as the write step sits only after validation, invalid input does not produce the side effect of saving a quote.

A pipeline ordered in reverse as `recordRaw → validate → calculate` could write bad data before detecting the error. If auditing raw input is a genuine requirement, separate auditing into an action with its own policy rather than mixing it into the pure core.

## 8. Isolating the Write Boundary with a Port

Define an I/O port:

~~~java
package example.functions;

import example.functions.OrderModels.Quote;

public interface QuoteRecorder {
    void record(Quote quote);
}
~~~

A Consumer bean delegates to the port:

~~~java
package example.functions;

import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import example.functions.OrderModels.Quote;

@Configuration
public class QuoteRecorderFunctions {

    @Bean
    public Consumer<Quote> recordQuote(QuoteRecorder recorder) {
        return recorder::record;
    }
}
~~~

As a result, `calculateQuote` does not depend on a repository, HTTP context, or broker. `QuoteRecorder` can be implemented using JPA/JDBC, a message producer, or an in-memory store in tests.

However, using a `Consumer` **does not by itself make the write operation idempotent**. That is the responsibility of the port implementation and storage layer.

## 9. In-Memory Idempotency Example

~~~java
package example.functions;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.stereotype.Component;

import example.functions.OrderModels.Quote;

@Component
public class InMemoryQuoteRecorder implements QuoteRecorder {

    private final ConcurrentHashMap<String, Quote> records =
            new ConcurrentHashMap<>();

    @Override
    public void record(Quote quote) {
        if (quote == null || quote.orderId() == null) {
            throw new IllegalArgumentException(
                    "Quote and orderId must exist");
        }

        Quote previous =
                records.putIfAbsent(quote.orderId(), quote);

        if (previous != null && !previous.equals(quote)) {
            throw new IllegalStateException(
                    "Same orderId with different data");
        }
    }

    public Quote find(String orderId) {
        return records.get(orderId);
    }

    public int size() {
        return records.size();
    }

    public Map<String, Quote> snapshot() {
        return Map.copyOf(records);
    }

    public void clear() {
        records.clear();
    }
}
~~~

Contract within a single JVM:

| Request | Behavior |
|---|---|
| Write `ORD-42` for the first time | Saves one record |
| Write the same Quote for `ORD-42` again | Does not increase record count |
| Write the same ID with different content | Reports conflict |
| Write a new `ORD-43` | Adds a new record |

`putIfAbsent` is atomic within a single `ConcurrentHashMap`, but an in-memory store **is not durable, is not shared across multiple instances, and does not guarantee transactions with a broker**. In production, you need unique constraints, atomic upserts, or transactions backed by real storage.

You also should not use a `SELECT` existence check followed by an `INSERT` without a uniqueness mechanism: two replicas can both observe "not present" and both write.

## 10. Composing the Pure Core with a Consumer via FunctionCatalog

The four registered business Functions can form a pipeline returning `Quote`:

~~~text
normalizeOrder|parseOrder|validateOrder|calculateQuote
    ⇒ Function<String, Quote>
~~~

When `recordQuote` is appended at the end, the overall contract becomes `Consumer<String>`:

~~~text
normalizeOrder|parseOrder|validateOrder|calculateQuote|recordQuote
    ⇒ Consumer<String>
~~~

Spring service:

~~~java
package example.functions;

import java.util.function.Consumer;
import java.util.function.Function;

import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.stereotype.Service;

import example.functions.OrderModels.Quote;

@Service
public class QuoteService {

    private final FunctionCatalog catalog;

    public QuoteService(FunctionCatalog catalog) {
        this.catalog = catalog;
    }

    public Quote preview(String rawOrder) {
        Function<String, Quote> pipeline = catalog.lookup(
                "normalizeOrder|parseOrder|validateOrder|calculateQuote");

        if (pipeline == null) {
            throw new IllegalStateException(
                    "Quote pipeline not found");
        }

        return pipeline.apply(rawOrder);
    }

    public void processAndRecord(String rawOrder) {
        Consumer<String> pipeline = catalog.lookup(
                "normalizeOrder|parseOrder|validateOrder"
                + "|calculateQuote|recordQuote");

        if (pipeline == null) {
            throw new IllegalStateException(
                    "Record pipeline not found");
        }

        pipeline.accept(rawOrder);
    }
}
~~~

`preview(...)` returns a value without writing; `processAndRecord(...)` reuses the core and then performs the side effect in the final Consumer. The pipeline's interface is determined by **the input of the first step and the output of the last step**, not by an arbitrary type chosen by the author in code.

### 10.1. Why Should a Consumer Be Last?

A Consumer accepts a `Quote`, but `accept(...)` returns `void`. It provides no output to pass onward to another Function.

For example, the chain:

~~~text
calculateQuote|recordQuote|formatQuote
~~~

has no normal data-chaining contract because `recordQuote` does not return a `Quote` to `formatQuote`. If the business logic needs both to write and to return formatted text, use explicit orchestration or a Function with a clear return contract and proper error/transaction management.

### 10.2. FunctionCatalog Does Not Prove Purity

`catalog.lookup("A|B|C")` only looks up and composes functions by name and type metadata. Spring Cloud Function does not know whether a `Function` secretly calls a repository, reads a clock, or mutates a static field. Keeping pure logic separate is a design decision that must be maintained through reviews and tests.

Similarly, the Java compiler accepting `andThen` does not prove that the data has the right business meaning—for example, a `String` representing an order ID versus a `String` representing an email.

## 11. Selecting a Pipeline with spring.cloud.function.definition

If the application wants the adapter to use the quote-calculation-only pipeline:

~~~yaml
spring:
  cloud:
    function:
      definition: "normalizeOrder|parseOrder|validateOrder|calculateQuote"
~~~

If the adapter needs the pipeline that receives data and saves it:

~~~yaml
spring:
  cloud:
    function:
      definition: "normalizeOrder|parseOrder|validateOrder|calculateQuote|recordQuote"
~~~

In properties format:

~~~properties
spring.cloud.function.definition=normalizeOrder|parseOrder|validateOrder|calculateQuote|recordQuote
~~~

This property **selects the function chain** for the integration layer; it does not automatically create an HTTP endpoint, Kafka topic, consumer group, serverless trigger, transaction, retry, or schedule.

| Approach | Role | Risks to Consider |
|---|---|---|
| Java calling `FunctionCatalog.lookup` | Looks up a pipeline by name | Bean names, types, and runtime behavior |
| HTTP adapter | Maps request/response | Timeouts, client retries, error mapping |
| Spring Cloud Stream | Connects message/binder | Redelivery, ack, content-type |
| Serverless adapter | Connects cloud trigger | Invocation retries, cold starts |
| Supplier combined with pipeline | Actively produces/fetches data | Polling, duplicates, empty source |
| Reactive Publisher | Value stream via subscription | Resubscription, backpressure, async errors |

The same pure logic can be reused across those adapters, but **end-to-end reliability** also depends on how each adapter triggers execution and acknowledges processing.

## 12. Turning Changing Data Sources into Explicit Inputs

A Function might look like a pure calculation yet depend on time or randomness:

~~~java
import java.time.Instant;
import java.util.UUID;
import java.util.function.Function;

// Receipt is the domain type defined in the next section.
Function<String, Receipt> issue = raw ->
        new Receipt(UUID.randomUUID(), Instant.now(), raw);
~~~

With the same `raw` input, it can generate a different ID and timestamp. Turn those factors into inputs instead:

~~~java
import java.time.Instant;
import java.util.UUID;

record ReceiptInput(
        String payload,
        UUID receiptId,
        Instant issuedAt) {}

record Receipt(
        UUID receiptId,
        Instant issuedAt,
        String payload) {}
~~~

Pure function:

~~~java
Function<ReceiptInput, Receipt> buildReceipt =
        input -> new Receipt(
                input.receiptId(),
                input.issuedAt(),
                input.payload());
~~~

The outer boundary decides the values:

~~~java
UUID receiptId = UUID.randomUUID();
Instant issuedAt = Instant.now();

ReceiptInput input = new ReceiptInput(
        "ORD-42", receiptId, issuedAt);

Receipt result = buildReceipt.apply(input);
~~~

When `buildReceipt` receives the **same `ReceiptInput`** again, the result is deterministic. However, if the outer shell generates a new UUID **on every retry**, the overall workflow still lacks a stable outcome. For proper business retries, the idempotency key or receipt ID must stay stable or be looked up from the original request.

### 12.1. Prices and Pricing Policies Are Input Data

Selling prices can change via a database or API. You should not hide a price lookup inside a Function and claim the result depends only on `order`.

A pattern:

~~~java
record PricingInput(
        OrderModels.ValidatedOrder order,
        long unitPriceVnd,
        String priceVersion) {}

Function<PricingInput, OrderModels.Quote> priceWithContext =
        input -> new OrderModels.Quote(
                input.order().orderId(),
                input.order().sku(),
                input.order().quantity(),
                Math.multiplyExact(
                    input.order().quantity(),
                    input.unitPriceVnd()));
~~~

The shell reads the price snapshot and `priceVersion`, while the function computes solely from the snapshot. If historical auditing or recalculation is needed, store the policy version and unit price used; the `Quote` model in the example should be extended when the business requires that data.

### 12.2. A Pure Function Can Accept Fixed Configuration

Reading an immutable configuration when initializing a bean and capturing it in a closure can produce a Function that is deterministic for **the same instance**. But if the business needs identical results across deployments with different configurations, store the configuration version as well or pass a rule snapshot in the input. Purity does not automatically solve business-rule versioning.

## 13. Three Distinct Failure Points

Consider:

~~~text
normalize → parse → validate → calculate → record → ack/response
                                  |             |
                                  |             +-- acknowledgement may be lost
                                  +-- not yet written
~~~

The cases:

1. **Failure before Consumer:** validation or calculation fails; `recordQuote` has not been called.
2. **Failure inside Consumer before commit:** the transaction or storage determines whether it can be rolled back.
3. **Failure after commit or lost response/ack:** the data may already be saved while the caller does not know; retries may re-run it.

A timeout at the HTTP or broker layer **does not prove** that the transaction failed. This is why you need idempotent writes at the storage layer, not just pure functions before it.

### 13.1. Do Not Swallow Errors and Pretend Success

Example to avoid:

~~~java
Consumer<OrderModels.Quote> unsafe = quote -> {
    try {
        recorder.record(quote);
    } catch (Exception ignored) {
        // Wrong: hides the failure.
    }
};
~~~

Here `recorder` represents a `QuoteRecorder` provided by the application. If the Consumer swallows the error, the adapter may return HTTP success or acknowledge the message even though the data was not saved. Propagate the error to an appropriate handler or explicitly represent the failure state.

### 13.2. Retries Must Match the Error Type

| Error Type | Example | Typically Appropriate Action |
|---|---|---|
| Invalid input | Quantity 0, malformed SKU | Do not retry indefinitely |
| Transient network error | Database connection timeout | Bounded retry with backoff |
| Idempotency key conflict | Same ID with different payload | Return conflict and investigate |
| Uncertain commit outcome | Response lost after commit | Look up / retry via idempotent key |

Infinite retries on a validation error will never make invalid input become valid. Retry, dead-letter, and acknowledgement policies depend on the transport/infrastructure layer.

## 14. Transactions, Retries, and the Transactional Outbox

A flow with two side effects:

~~~text
recordQuote (DB) → publish QuoteCreated (broker)
~~~

If the application crashes after committing to the database but before publishing, the system will have saved the Quote without emitting the event. Conversely, if publishing succeeds and acknowledgement fails, the message may be redelivered.

**Composing Consumers does not automatically create a distributed transaction.** If consistency is required between DB updates and event publishing, a common strategy is the transactional outbox:

~~~text
Within the same database transaction:
  - save Quote
  - save OutboxEvent to publish
COMMIT
    |
    v
Outbox publisher reads unsent records
    |
    v
Broker
    |
    v
Downstream consumer checks for duplicates
~~~

The outbox preserves the intent to publish even if the process stops. A worker can republish after a crash. Still, the publisher or broker can deliver the same event multiple times; the receiving consumer should enforce idempotency by event ID or business key.

### 14.1. Separate the Guarantees by Scope

- The pure core guarantees easily verifiable recomputation without mutating storage.
- The repository/table guarantees uniqueness and atomic updates.
- The transaction/outbox protects consistency across changes within the database.
- The broker/binder governs delivery, retries, and acknowledgements.
- Downstream consumers handle duplicates according to the business contract.

No single `FunctionCatalog.lookup(...)` call replaces all of those layers.

## 15. Reactive Streams and Side Effects Repeating on Resubscription

A pure Function can be lifted into a transformation on a `Flux`:

~~~java
import java.util.function.Function;
import reactor.core.publisher.Flux;

Function<OrderModels.ValidatedOrder,
         OrderModels.Quote> priceOne =
        new QuoteFunctions().calculateQuote();

Function<Flux<OrderModels.ValidatedOrder>,
         Flux<OrderModels.Quote>> priceStream =
        flux -> flux.map(priceOne);
~~~

With a cold Publisher, the mapper usually runs when subscribed. If resubscribed, the computation may run again without writing data on its own.

Conversely:

~~~java
// inputFlux and recorder are illustrative dependencies.
Flux<OrderModels.Quote> withWrite =
        inputFlux.map(priceOne)
                 .doOnNext(recorder::record);
~~~

If there is a resubscription or retry, `record` may run repeatedly. `doOnNext` is mainly suitable for observation or necessary synchronous side effects; it is not a reliable persistence or transaction mechanism by default.

If `record` performs blocking I/O, calling it on an event-loop thread can block the thread. For asynchronous I/O, design an adapter returning `Mono<Void>`/`Mono<Result>` accordingly, using `flatMap`/`concatMap` with clear concurrency, error, subscription, and idempotency management.

### 15.1. What to Check When Using Reactor

- Does `apply(...)` returning a `Flux` only assemble the pipeline; when is the Publisher subscribed to?
- Can `retry` or a new subscription re-trigger side effects?
- Must element order be preserved with `concatMap`, or is concurrent `flatMap` allowed?
- If the Subscriber cancels, what state will an in-flight transaction be left in?
- How does the Spring Cloud Function/Stream adapter handle backpressure, ack, and error signals?

Pure functions make recomputation safe, but **do not automatically make side effects inside reactive operators safe**.

## 16. Do Not Hide Side Effects Behind Ambiguous Function Names

Function names should reveal their responsibilities:

| Recommended | Avoid Ambiguity |
|---|---|
| `normalizeOrder` | `processStep1` |
| `validateOrder` | `checkThenSave` when the goal is only validation |
| `calculateQuote` | `calculateAndPublish` when a pure core is needed |
| `recordQuote` | `handleData` |
| `loadPriceSnapshot` (adapter) | `calculateQuote` reading the database on every call |

During code review, ask: looking only at a bean's name and generic types, can someone tell whether it **mutates external data or not**? If not, the boundary lacks clarity.

## 17. Unit Testing the Pure Core

Because the core does not depend on storage or adapters, it can be tested with JUnit 5 alone without starting Spring.

~~~java
package example.functions;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.function.Function;
import org.junit.jupiter.api.Test;

import example.functions.OrderModels.OrderDraft;
import example.functions.OrderModels.ValidatedOrder;
import example.functions.OrderModels.Quote;

class PureQuoteFunctionsTest {

    private final QuoteFunctions config =
            new QuoteFunctions();

    @Test
    void sameInputProducesSameQuote() {
        Function<String, String> normalize =
                config.normalizeOrder();
        Function<String, OrderDraft> parse =
                config.parseOrder();
        Function<OrderDraft, ValidatedOrder> validate =
                config.validateOrder();
        Function<ValidatedOrder, Quote> price =
                config.calculateQuote();

        Function<String, Quote> pipeline =
                normalize.andThen(parse)
                         .andThen(validate)
                         .andThen(price);

        Quote first = pipeline.apply(" ord-42, sku-7, 2 ");
        Quote second = pipeline.apply(" ord-42, sku-7, 2 ");

        assertEquals(first, second);
        assertEquals(
                new Quote("ORD-42", "SKU-7", 2, 250_000L),
                first);
    }

    @Test
    void invalidQuantityIsRejected() {
        Function<OrderDraft, ValidatedOrder> validate =
                config.validateOrder();

        assertThrows(IllegalArgumentException.class,
                () -> validate.apply(
                    new OrderDraft("ORD-42", "SKU-7", 0)));
    }
}
~~~

The first test verifies determinism on the chosen inputs; it is not a mathematical proof for all inputs, but it catches regressions quickly if a developer later accidentally adds mutable state or an external dependency.

The second test checks validation independently of any database. For critical logic, you can add parameterized tests or property-based tests to cover more datasets.

## 18. Unit Testing an Idempotent Recorder

This test suite targets the side-effect boundary without mixing it with pricing logic:

~~~java
package example.functions;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

import example.functions.OrderModels.Quote;

class QuoteRecorderTest {

    @Test
    void repeatedRequestCreatesOneRecord() {
        InMemoryQuoteRecorder recorder =
                new InMemoryQuoteRecorder();

        Quote quote = new Quote(
                "ORD-42", "SKU-7", 2, 250_000L);

        recorder.record(quote);
        recorder.record(quote);

        assertEquals(1, recorder.size());
        assertEquals(quote, recorder.find("ORD-42"));
    }

    @Test
    void conflictingPayloadIsRejected() {
        InMemoryQuoteRecorder recorder =
                new InMemoryQuoteRecorder();

        recorder.record(new Quote(
                "ORD-42", "SKU-7", 2, 250_000L));

        assertThrows(IllegalStateException.class,
                () -> recorder.record(new Quote(
                    "ORD-42", "SKU-7", 3, 375_000L)));

        assertEquals(1, recorder.size());
    }
}
~~~

This proves behavior for **a single in-memory instance**, not fault tolerance across a multi-replica database. For a real system, test transactions and unique constraints under concurrency, as well as scenarios where the process crashes after commit.

## 19. Integration Testing with FunctionCatalog

Core unit tests cannot verify bean names or composition through the catalog. Create the main Spring Boot class:

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

Place the example classes in package `example.functions` or a subpackage so default component scanning discovers them, and add the appropriate Spring Cloud Function context and Spring Boot Test dependencies.

Test both pipelines:

~~~java
package example.functions;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.function.Consumer;
import java.util.function.Function;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

import example.functions.OrderModels.Quote;

@SpringBootTest(classes = QuoteApplication.class)
class QuoteCatalogIntegrationTest {

    @Autowired
    FunctionCatalog catalog;

    @Autowired
    InMemoryQuoteRecorder recorder;

    @Test
    void purePipelineReturnsQuote() {
        Function<String, Quote> pipeline = catalog.lookup(
                "normalizeOrder|parseOrder|validateOrder|calculateQuote");

        assertNotNull(pipeline);

        assertEquals(
                new Quote("ORD-42", "SKU-7", 2, 250_000L),
                pipeline.apply(" ord-42, sku-7, 2 "));
    }

    @Test
    void repeatedRecordingIsIdempotent() {
        Consumer<String> pipeline = catalog.lookup(
                "normalizeOrder|parseOrder|validateOrder"
                + "|calculateQuote|recordQuote");

        assertNotNull(pipeline);

        pipeline.accept(" ord-77, sku-7, 2 ");
        pipeline.accept(" ord-77, sku-7, 2 ");

        assertEquals(
                new Quote("ORD-77", "SKU-7", 2, 250_000L),
                recorder.find("ORD-77"));
    }

    @Test
    void invalidInputDoesNotReachRecorder() {
        Consumer<String> pipeline = catalog.lookup(
                "normalizeOrder|parseOrder|validateOrder"
                + "|calculateQuote|recordQuote");

        assertNotNull(pipeline);

        assertThrows(IllegalArgumentException.class,
                () -> pipeline.accept("ORD-99,SKU-7,0"));

        assertEquals(null, recorder.find("ORD-99"));
    }
}
~~~

These tests use distinct keys `ORD-42`, `ORD-77`, and `ORD-99` to avoid simple dependencies between tests. With parallel tests or shared contexts, you should still isolate state using fixtures/resets or proper isolation configuration.

### 19.1. What to Test at Each Layer

| Layer | Required Tests | What Remains Unproven |
|---|---|---|
| Core unit test | Same input yields right result, validation works | Bean name registration not verified |
| Port unit test | Same key does not duplicate, conflicts rejected | Multi-instance/transactions not proven |
| Catalog integration test | Correct name composition, order, and overall type | Binder/HTTP behavior not proven |
| Adapter integration test | Payload, headers, routes, bindings, ack/retry | Does not guarantee whole system never fails |
| Resilience/fault test | Network drops, timeouts, crashes, race conditions | Must be paired with operational monitoring |

Catalog tests should verify that **side effects do not occur when a pure step fails**, not just that an exception is thrown.

## 20. Operational Checklist and Common Design Pitfalls

### 20.1. Design Anti-Patterns to Avoid

| Poor Design Pattern | Risk | Improvement |
|---|---|---|
| `calculateQuote` calls `repository.save` | Every recalculation may write again | Separate calculation Function and write Consumer |
| `calculateQuote` calls `Instant.now()` | Result is not reproducible | Pass timestamp via input |
| `generateId` generates a new UUID on every retry | Hard to deduplicate per request | Persist a stable idempotency key |
| `SELECT` then `INSERT` without uniqueness | Race condition across replicas | Enforce uniqueness and atomic writes |
| `Consumer` swallows exceptions | Adapter may ack erroneously | Classify and return/propagate errors |
| Write DB then publish directly | DB may commit while event is lost | Transactional outbox when appropriate |
| Side effect inside `Flux.map` | Retries/resubscriptions cause duplicates | Isolate I/O, idempotency, stream control |
| Treating `definition` as broker config | Missing binding/transport setup | Configure the adapter separately |
| Using mutable fields in a Function bean | Concurrent invocations can corrupt state | Make stateless or synchronize explicitly |

### 20.2. Pre-Production Checklist

1. Do the core Functions depend on hidden state, clocks, randomness, or I/O?
2. Given the same input and same policy version, can the same result be recomputed?
3. Does validation run before critical side effects?
4. Are side effects behind a controlled port/adapter?
5. Is the idempotency key stable across retries?
6. Does storage have appropriate uniqueness constraints or transactions for concurrent requests?
7. Does the same key with a different payload report a conflict rather than silently overwriting?
8. If the DB write succeeds but the response/ack fails, are duplicates handled safely?
9. If events must be published, is there a strategy to avoid losing events after DB commit?
10. Are retries bounded and do they distinguish transient from permanent errors?
11. Has `FunctionCatalog.lookup` been integration tested on the framework version in use?
12. Do HTTP/event/serverless adapters have tests for real serialization, content-type, headers, and retries?
13. For reactive flows, can resubscription repeat side effects?

## 21. Practice Exercises

**Exercise 1 — Identifying Purity.** Consider three Functions: computing `quantity * 125_000L`, generating an ID with `UUID.randomUUID()`, and reading a price from a database. Which function is pure? Why?

**Exercise 2 — Refactoring.** A `Function<Order,Receipt>` both computes an invoice and calls `repository.save`. Separate the pure part and the side-effect part into clearly named Java interfaces.

**Exercise 3 — Pure or Idempotent?** Why is `addOne(x) = x + 1` pure yet not idempotent under `f(f(x))=f(x)`? Why can `saveOnce` be idempotent without being pure?

**Exercise 4 — Time and IDs.** A Function creates `UUID.randomUUID()` and `Instant.now()` internally. Move them into inputs and state what must be stored stably to retry a request.

**Exercise 5 — Composition.** Write the catalog expression for the pipeline returning a `Quote` and the pipeline recording a Quote. Which methods invoke each pipeline?

**Exercise 6 — Client Retry.** The database committed, but the HTTP response was lost. A client resends the same order. If the code only executes `INSERT`, what can happen? Describe how to design an idempotency key.

**Exercise 7 — Concurrent Workers.** Why can two workers both running `SELECT` then `INSERT` still write duplicates? State the solution at the database layer.

**Exercise 8 — Outbox.** Explain why saving a Quote and then publishing to Kafka in two separate commands can lose events. What does an outbox protect, and what risk remains?

**Exercise 9 — Reactive.** If `doOnNext(recorder::record)` runs again due to `retry` or a new subscription, what must you do to avoid creating duplicate side effects?

**Exercise 10 — Test Layers.** Propose one core unit test, one idempotent port test, one catalog test, and one binder test. What kind of bug does each catch?

### Suggested Answers

- **Exercise 1:** Multiplying quantity by a fixed price is pure; UUID generation and DB reads are impure.
- **Exercise 2:** `Function<ValidatedOrder,Receipt> calculate` and `Consumer<Receipt> record`, or an I/O port invoked by the shell.
- **Exercise 3:** `addOne(addOne(x))` differs from `addOne(x)`; `saveOnce` changes storage the first time but adds no further effect on subsequent calls.
- **Exercise 4:** Use a record containing `receiptId` and `issuedAt`; keep the idempotency key/ID stable per request across retries.
- **Exercise 5:** `"normalizeOrder|parseOrder|validateOrder|calculateQuote"` returns `Function<String,Quote>` and is invoked with `apply`; appending `"|recordQuote"` returns `Consumer<String>` and is invoked with `accept`.
- **Exercise 6:** It can insert duplicates; use a fixed key, unique constraint, or atomic idempotent write.
- **Exercise 7:** Both workers observe "not present"; uniqueness must be enforced at the storage layer.
- **Exercise 8:** The process can crash between DB commit and publishing; the outbox records publish intent inside the DB transaction, though downstream consumers still need deduplication.
- **Exercise 9:** Design an idempotent write boundary and manage retries, subscriptions, and concurrency properly for the framework.
- **Exercise 10:** Core tests determinism; port tests duplicate prevention; catalog tests name composition; binder tests delivery, ack, and serialization.

## 22. Key Takeaways

- **Pure functions** depend on their inputs, do not mutate external systems, and produce deterministic results under the same rules.
- `Supplier`, `Function`, and `Consumer` are Java contracts for inputs and outputs; **they do not enforce purity**.
- The **Functional Core, Imperative Shell** pattern separates parsing, validation, and calculation from clocks, randomness, databases, brokers, and transactions.
- Placing side effects in a port/Consumer at the end of a pipeline clarifies test boundaries; idempotency still must be enforced by the implementation and storage.
- Purity and idempotency are distinct. A pure core can be rerun safely, whereas data writes require deduplication mechanisms.
- `FunctionCatalog` and `spring.cloud.function.definition` compose and select logic; they do not provide transactions, exactly-once delivery, or transport configuration.
- With HTTP, events, serverless, or reactive flows, you must verify retries, acks, resubscriptions, error signals, and transactions against the actual adapter.


