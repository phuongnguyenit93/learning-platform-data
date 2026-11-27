# Composing Supplier with Function

## 1. Learning Objectives

Spring Cloud Function helps you develop reusable business logic using `Supplier`, `Function`, and `Consumer`, independent of the invocation protocol. The same logic can run in internal Java code or be connected to HTTP, events, or serverless via the appropriate adapter. In the **Function Composition** chapter, an important case is connecting a **data source** with a **data transformation step**.

This lesson focuses on the composition:

~~~text
Supplier<A> --get()--> A --Function<A, B>.apply(...)--> B

Behavioral result: Supplier<B>
~~~

After this lesson, you will be able to:

- Distinguish `Supplier.get()` from `Function.apply(...)`.
- Explain why composing `Supplier<A>` and `Function<A, B>` produces `Supplier<B>`.
- Write the composition in plain Java and look up compositions by name using `FunctionCatalog.lookup(...)`.
- Specify pipelines with `spring.cloud.function.definition` and understand the role of adapters.
- Identify errors related to ordering, data types, execution counts, exceptions, and reactive streams.
- Test the invocation order as well as the output of a multi-step pipeline.

## 2. Supplier Produces Data, Function Transforms Data

`Supplier<T>` is a Java interface with the method `T get()`. It takes no input parameters.

~~~java
import java.util.function.Supplier;

Supplier<String> greetingSource = () -> "Welcome!";
String greeting = greetingSource.get();

System.out.println(greeting); // Welcome!
~~~

`Function<T, R>` takes `T` and returns `R` via the method `R apply(T input)`.

~~~java
import java.util.function.Function;

Function<String, Integer> countChars = String::length;
System.out.println(countChars.apply("Welcome!")); // 8
~~~

With a `Supplier<String>` source and a `Function<String, Integer>` step, you can connect them:

~~~text
                        get()                 apply(...)
Supplier<String> ----------------> String ----------------> Integer
                                   Function<String,Integer>
~~~

The final caller only needs to trigger the composed source. Because the caller **passes no input**, the result conforms to the `Supplier<Integer>` interface.

### 2.1. General Formula

Given:

~~~text
source: Supplier<A>
transform: Function<A, B>
~~~

The composition can be described as:

~~~text
combined: Supplier<B>

combined.get() = transform.apply(source.get())
~~~

The following table summarizes the contracts:

| Component | Input passed by caller | Output | How to invoke |
|---|---|---|---|
| `Supplier<A>` | None | `A` | `get()` |
| `Function<A, B>` | `A` | `B` | `apply(A)` |
| Composed components | None | `B` | `get()` |

**Key point:** a standard Java `Supplier` **does not have** `andThen` or `compose` methods. Those methods belong to `Function`; Spring Cloud Function adds the mechanism to compose function beans by name.

## 3. Composing Manually in Plain Java

Example: a source returning a quantity to be billed, and a function calculating the cost from the quantity.

~~~java
import java.util.function.Function;
import java.util.function.Supplier;

public class SupplierFunctionExample {

    public static void main(String[] args) {
        Supplier<Integer> quantitySource = () -> 4;
        Function<Integer, Long> calculateCost =
                quantity -> quantity * 75_000L;

        Supplier<Long> totalCostSource = () ->
                calculateCost.apply(quantitySource.get());

        System.out.println(totalCostSource.get()); // 300000
    }
}
~~~

A call to `totalCostSource.get()` executes in this order:

1. `quantitySource.get()` produces `4`.
2. `calculateCost.apply(4)` returns `300000L`.
3. `totalCostSource.get()` returns that `Long` result to the caller.

The declaration of `totalCostSource` only creates a lambda; **it has not executed the source or the transformation function yet**. The steps run when `get()` is called.

### 3.1. Writing a Generic Composition Helper

If used in multiple places, you can define a plain Java utility method:

~~~java
import java.util.function.Function;
import java.util.function.Supplier;

public final class SupplierComposition {

    private SupplierComposition() {}

    public static <A, B> Supplier<B> combine(
            Supplier<? extends A> source,
            Function<? super A, ? extends B> transform) {

        return () -> transform.apply(source.get());
    }
}
~~~

Using two chained `Function` steps after a `Supplier`:

~~~java
Supplier<String> textSource = () -> "  spring  ";

Function<String, String> trim = String::trim;
Function<String, Integer> length = String::length;

Supplier<Integer> result =
        SupplierComposition.combine(
                textSource,
                trim.andThen(length));

System.out.println(result.get()); // 6
~~~

`trim.andThen(length)` combines **Function with Function**. The `combine` helper combines **Supplier with the composed Function**. The overall type remains `Supplier<Integer>`.

### 3.2. Why Not Use source.andThen(transform)?

This **does not compile**:

~~~java
Supplier<String> source = () -> "abc";
Function<String, Integer> length = String::length;

// Supplier<Integer> invalid = source.andThen(length);
~~~

Standard Java `Supplier` does not have `andThen`. The valid approach in plain Java is:

~~~java
Supplier<Integer> valid = () -> length.apply(source.get());
~~~

In a Spring Cloud Function application, `FunctionCatalog` allows chaining by name without manually writing a lambda for every combination.

## 4. Business Example: Order Source and Quote

Suppose a service needs to fetch a pending order, price it, and prepare the quote text. To illustrate the composition cleanly, we have the `Supplier` return a fixed order; connecting to a database or broker belongs to a later integration layer.

Expected data flow:

~~~text
pendingOrder: Supplier<OrderDraft>
            |
            | get()
            v
OrderDraft("SKU-17", 2)
            |
            v
priceOrder: Function<OrderDraft, Quote>
            |
            | apply(order)
            v
Quote("SKU-17", 2, 250000)
            |
            v
formatQuote: Function<Quote, String>
            |
            | apply(quote)
            v
"SKU-17 x 2 = 250000 VND"
~~~

### 4.1. Defining Function Beans in Spring

Using Java 17 or later with `record`:

~~~java
package example.functions;

import java.util.function.Function;
import java.util.function.Supplier;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class QuoteFunctions {

    public record OrderDraft(String sku, int quantity) {}

    public record Quote(
            String sku,
            int quantity,
            long totalVnd) {}

    @Bean
    public Supplier<OrderDraft> pendingOrder() {
        return () -> new OrderDraft("SKU-17", 2);
    }

    @Bean
    public Function<OrderDraft, Quote> priceOrder() {
        return order -> {
            if (order == null
                    || order.sku() == null
                    || !order.sku().matches("SKU-[0-9]+")
                    || order.quantity() <= 0) {
                throw new IllegalArgumentException(
                        "Invalid order");
            }

            long unitPrice = 125_000L;
            long totalVnd = Math.multiplyExact(
                    order.quantity(), unitPrice);

            return new Quote(
                    order.sku(),
                    order.quantity(),
                    totalVnd);
        };
    }

    @Bean
    public Function<Quote, String> formatQuote() {
        return quote ->
                quote.sku() + " x " + quote.quantity()
                + " = " + quote.totalVnd() + " VND";
    }
}
~~~

The default bean names are `pendingOrder`, `priceOrder`, and `formatQuote`. Once Spring Cloud Function is configured and the beans are discovered by the application, they can be registered in `FunctionCatalog`.

| Bean | Contract | Role |
|---|---|---|
| `pendingOrder` | `Supplier<OrderDraft>` | Produces order data |
| `priceOrder` | `Function<OrderDraft, Quote>` | Calculates quote |
| `formatQuote` | `Function<Quote, String>` | Formats text |

The price `125_000L` and order `SKU-17` are sample data. A real source must define how to read new records, handle unready records, and avoid duplicate emissions.

### 4.2. Retrieving the Composed Supplier with FunctionCatalog.lookup

`FunctionCatalog` supports composing functions by name with `|`. Steps on the left run before steps on the right according to the data contract.

~~~java
package example.functions;

import java.util.function.Supplier;

import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.stereotype.Service;

@Service
public class QuoteService {

    private final FunctionCatalog catalog;

    public QuoteService(FunctionCatalog catalog) {
        this.catalog = catalog;
    }

    public String generateQuote() {
        Supplier<String> pipeline =
                catalog.lookup(
                        "pendingOrder|priceOrder|formatQuote");

        if (pipeline == null) {
            throw new IllegalStateException(
                    "Quote pipeline not found");
        }

        return pipeline.get();
    }
}
~~~

The composition `pendingOrder|priceOrder|formatQuote` has the overall contract:

~~~text
Supplier<OrderDraft>
    |
    v
Function<OrderDraft, Quote>
    |
    v
Function<Quote, String>
    |
    v
Supplier<String>
~~~

Calling `pipeline.get()` triggers the `Supplier`, then passes data through each `Function`. The result from the example is:

~~~text
SKU-17 x 2 = 250000 VND
~~~

You do not call `pipeline.apply(...)` because the pipeline starts with a `Supplier`, so it **requires no input from the caller**.

### 4.3. Example Spring Boot Application Class

Place the application class in the `example.functions` package so the classes above are scanned:

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

Spring Boot, Spring Cloud Function, and appropriate dependency configuration are required. Internal Java lookups do not require creating an HTTP controller. If integrating with HTTP, a broker, or serverless, the corresponding adapter is required.

## 5. Selecting the Pipeline with spring.cloud.function.definition

You can declare the function chain name for adapters/framework in `application.yml`:

~~~yaml
spring:
  cloud:
    function:
      definition: "pendingOrder|priceOrder|formatQuote"
~~~

Or in `application.properties`:

~~~properties
spring.cloud.function.definition=pendingOrder|priceOrder|formatQuote
~~~

The meaning of these configurations is: select a **pipeline sourced by** `pendingOrder`, then pass sequentially through `priceOrder` and `formatQuote`.

Two usage patterns must be distinguished:

| Need | Approach |
|---|---|
| Java code retrieves the pipeline itself to invoke | `catalog.lookup("pendingOrder|priceOrder|formatQuote")` |
| Adapter selects the configured pipeline | `spring.cloud.function.definition` |
| Invoking the retrieved pipeline in Java | `pipeline.get()` |
| Connecting to publish via a broker | Install binder/adapter and configure appropriate output |

`spring.cloud.function.definition` **does not automatically create an HTTP endpoint, trigger polling, or connect to a broker**. It selects the function name/composition; how it is triggered and how results are sent are still determined by the integration environment.

### 5.1. Composing a Supplier with Only One Function

If you need a `Quote` object instead of a `String`:

~~~java
import java.util.function.Supplier;

Supplier<QuoteFunctions.Quote> quotes =
        catalog.lookup("pendingOrder|priceOrder");

if (quotes == null) {
    throw new IllegalStateException("Missing quote supplier");
}

QuoteFunctions.Quote quote = quotes.get();
~~~

The composition `pendingOrder|priceOrder` is a `Supplier<Quote>`, while the composition with `formatQuote` added is a `Supplier<String>`. Simply adding or removing a `Function` at the end changes the pipeline's output contract.

## 6. What Happens When Calling get() Multiple Times?

Each call to `get()` triggers the composed `Supplier` logic in typical synchronous execution. To see this clearly, consider an example generating sequential order codes:

~~~java
import java.util.concurrent.atomic.AtomicLong;
import java.util.function.Function;
import java.util.function.Supplier;

AtomicLong sequence = new AtomicLong();

Supplier<Long> nextId = sequence::incrementAndGet;
Function<Long, String> label = id -> "ORDER-" + id;

Supplier<String> nextOrderCode =
        () -> label.apply(nextId.get());

System.out.println(nextOrderCode.get()); // ORDER-1
System.out.println(nextOrderCode.get()); // ORDER-2
System.out.println(nextOrderCode.get()); // ORDER-3
~~~

One call to `nextOrderCode.get()` consists of two steps: incrementing the sequence number and then formatting it. The function does not automatically cache the result to return on subsequent calls.

Conversely, `pendingOrder` in the earlier example returns the same `SKU-17` data every time it is called. That is convenient for a lesson example, but it can cause **duplicate order emissions** if attached to an event adapter triggered multiple times.

### 6.1. Who Decides When to Call the Supplier?

This depends on the environment:

- Internal Java: the pipeline runs as many times as code calls `get()`.
- Spring Cloud Stream with an imperative `Supplier`: the binder's poller/trigger mechanism typically determines when data is fetched; configuration varies by version.
- Reactive `Supplier`: may be subscribed to and emit multiple elements according to the `Publisher` model, unlike polling a standard `Supplier`.
- Serverless or HTTP: trigger behavior depends on the adapter and configured handler type.

The `|` symbol only specifies **data chaining order**. It does not configure schedules, retries, transactions, or deduplication mechanisms.

## 7. Data Types Between Steps Must Be Compatible

Rule:

~~~text
Supplier<A> | Function<A, B> | Function<B, C>
                                  ↓
                            Supplier<C>
~~~

The condition for chaining two steps is that the output value of the previous step must be usable as the input of the next step. Valid example:

~~~java
Supplier<String> raw = () -> "  42  ";

Function<String, Integer> parse =
        text -> Integer.parseInt(text.trim());

Function<Integer, Long> price =
        amount -> amount * 1_000L;

Supplier<Long> total =
        () -> price.apply(parse.apply(raw.get()));

System.out.println(total.get()); // 42000
~~~

However, the following **does not compile in plain Java**:

~~~java
Supplier<String> raw = () -> "SKU-17";
Function<Integer, Long> price =
        amount -> amount * 1_000L;

// Invalid: String is not Integer.
// Supplier<Long> invalid = () -> price.apply(raw.get());
~~~

When composing by name with `catalog.lookup("raw|price")`, the compiler cannot check steps based on a name string. Errors from missing beans or incompatible types can surface at lookup or execution time at runtime. Therefore, know each bean's actual signature and write integration tests.

### 7.1. Different Type Names Are Not Necessarily Incompatible

Java allows passing a subtype value to a function accepting a supertype:

~~~java
Supplier<Integer> numberSource = () -> 5;

Function<Number, String> describe =
        number -> "Value: " + number;

Supplier<String> description =
        () -> describe.apply(numberSource.get());

System.out.println(description.get()); // Value: 5
~~~

`Integer` is a subtype of `Number`, so the steps connect. Keep generics explicit, and do not use raw types to hide errors.

### 7.2. Right Type, Wrong Business Meaning

A source might return a `String` representing a customer ID, while a downstream `Function` takes a `String` assuming it is an email address. The pipeline can still run, yet it processes the wrong kind of data.

You can use records as explicit domain types:

~~~java
record CustomerId(String value) {}
record EmailAddress(String value) {}
~~~

Then `Supplier<CustomerId>` cannot be passed directly to `Function<EmailAddress, Boolean>` under Java generics, helping catch design errors earlier.

## 8. Handling Missing Data, null, and Exceptions

### 8.1. Do Not Arbitrarily Use null to Represent Missing Data

~~~java
Supplier<String> maybeEmpty = () -> null;
Function<String, Integer> length = String::length;

// Calling get() here will throw NullPointerException.
Supplier<Integer> invalid =
        () -> length.apply(maybeEmpty.get());
~~~

Composition does not automatically interpret `null` as "skip this step." If a source occasionally has no record, design an explicit contract.

In plain Java, `Optional` can help represent absent values:

~~~java
import java.util.Optional;
import java.util.function.Function;
import java.util.function.Supplier;

Supplier<Optional<String>> source = Optional::empty;

Function<Optional<String>, Optional<Integer>> measure =
        value -> value.map(String::length);

Supplier<Optional<Integer>> result =
        () -> measure.apply(source.get());

System.out.println(result.get()); // Optional.empty
~~~

This is `Supplier<Optional<Integer>>`, not `Supplier<Integer>`. When using a messaging adapter, `Optional.empty()` **is not necessarily** interpreted automatically as "do not emit a message"; check the adapter's contract.

### 8.2. An Exception from Supplier Stops the Next Step in Synchronous Java

~~~java
Supplier<String> brokenSource = () -> {
    throw new IllegalStateException("Source not ready");
};

Function<String, Integer> measure = String::length;

Supplier<Integer> pipeline =
        () -> measure.apply(brokenSource.get());

// pipeline.get() throws IllegalStateException;
// measure.apply(...) has not run.
~~~

If `Supplier.get()` fails, data never reaches the `Function`. If the `Function` throws an exception, the composed `Supplier` likewise fails to produce a normal final result.

In HTTP, event, or serverless deployments, how errors are logged, returned, and retried depends on the adapter. **Function composition by itself does not provide retries, exactly-once delivery, or idempotency.** With real data, clarify when the source acknowledges that a record was fetched, when a record is allowed to be retried, and how to prevent duplicate sends.

### 8.3. Design Questions for Sources with Side Effects

If a `Supplier` reads from a database or external API, determine:

1. How much data can a single `get()` call fetch?
2. Can the source return the same record on two consecutive calls?
3. If a downstream `Function` fails, has the data already been marked as "processed"?
4. Can multiple `get()` calls run concurrently?
5. Where should timeouts, rate limits, retries, and idempotency be placed?

The fixed source example in this lesson is for learning composition; for production, separately design the data lifecycle and error handling.

## 9. The Reactive Supplier Case

In Spring Cloud Function, Reactor can be used to process data streams. In that case, the overall signature must express the **Publisher**, not just individual elements.

Java example:

~~~java
import java.util.function.Function;
import java.util.function.Supplier;

import reactor.core.publisher.Flux;

Supplier<Flux<String>> source = () ->
        Flux.just("  a  ", "  bb ");

Function<Flux<String>, Flux<Integer>> measure =
        input -> input
                .map(String::trim)
                .map(String::length);

Supplier<Flux<Integer>> transformed =
        () -> measure.apply(source.get());
~~~

Data type diagram:

~~~text
Supplier<Flux<String>>
          |
          v
Function<Flux<String>, Flux<Integer>>
          |
          v
Supplier<Flux<Integer>>
~~~

When calling `transformed.get()`, you receive a `Flux<Integer>`. Elements may only be processed once there is a subscriber:

~~~java
import java.util.List;

List<Integer> lengths =
        transformed.get().collectList().block();

System.out.println(lengths); // [1, 2]
~~~

`block()` is only for demonstration in synchronous programs/tests; do not call it arbitrarily inside an active reactive pipeline.

### 9.1. Avoid Confusing Element Types with Publisher Types

Two declarations:

~~~text
Supplier<Flux<Order>>
Function<Order, Quote>
~~~

do not connect automatically via Java generics like:

~~~text
Supplier<Flux<Order>>
Function<Flux<Order>, Flux<Quote>>
~~~

Spring Cloud Function and adapters may provide adaptation in some cases, but do not assume every reactive/imperative combination converts automatically. Check the contract of your version, clarify where each element is processed, and test with a real `Publisher`.

### 9.2. Invocation Count of a Reactive Supplier May Differ from a Regular Supplier

In Spring Cloud Stream, an imperative `Supplier` is typically polled according to configuration. A reactive `Supplier` may have its `Publisher` obtained and subscribed to differently depending on the binder/version. Do not assume each `Flux` element corresponds to a new `get()` call.

Verify subscriptions, backpressure, stream completion timing, and error handling before introducing a reactive source into an event-driven system.

## 10. Deploying the Pipeline via HTTP, Events, or Serverless

Spring Cloud Function's goal is to **decouple business logic from the invocation transport**. The beans `pendingOrder`, `priceOrder`, and `formatQuote` do not need to know whether they will be used over HTTP, a message broker, or a serverless handler.

| Environment | Who triggers the Supplier? | What to verify |
|---|---|---|
| Internal Java | Code calling `get()` | Bean names, data types, results, and call count |
| HTTP | Web adapter according to supported Supplier exposure | Method/path, response, and errors |
| Events | Binder/poller or subscription | Output binding, trigger schedule, serializer, retries |
| Serverless | Corresponding trigger and handler | Supplier support, event/result mapping |

A `Supplier` has no input like `Function<Order, Receipt>`. If the requirement is to **receive** an order from an HTTP request body or inbound message, you should generally define a `Function` or `Consumer` that accepts that data. A `Supplier` fits better when the business logic **actively produces or fetches** data.

### 10.1. Event Producer Illustration

~~~text
Data source
     |
     v
pendingOrder: Supplier<OrderDraft>
     |
     v
priceOrder: Function<OrderDraft, Quote>
     |
     v
formatQuote: Function<Quote, String>
     |
     v
Composed Supplier<String>
     |
     v
Adapter/binder with output binding
     |
     v
Broker or event destination
~~~

To work in practice, the application must have a compatible binder, destination/output binding, polling or reactive subscription mechanism, and error-handling policy. Configuring `spring.cloud.function.definition` alone is not enough.

## 11. Testing the Composition

### 11.1. Unit Tests Checking Order and Invocation Count

JUnit 5 example:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.ArrayList;
import java.util.List;
import java.util.function.Function;
import java.util.function.Supplier;
import org.junit.jupiter.api.Test;

class SupplierFunctionOrderTest {

    @Test
    void callsSupplierBeforeFunctionOnEachGet() {
        List<String> calls = new ArrayList<>();

        Supplier<Integer> source = () -> {
            calls.add("supplier");
            return 3;
        };

        Function<Integer, Integer> doubleIt = value -> {
            calls.add("function");
            return value * 2;
        };

        Supplier<Integer> composed =
                () -> doubleIt.apply(source.get());

        assertEquals(List.of(), calls); // Not run at declaration time
        assertEquals(6, composed.get());
        assertEquals(
                List.of("supplier", "function"),
                calls);

        assertEquals(6, composed.get());
        assertEquals(
                List.of(
                    "supplier", "function",
                    "supplier", "function"),
                calls);
    }
}
~~~

This test proves two properties of synchronous composition: the source runs before the `Function`, and each `get()` call re-executes the chain.

### 11.2. Integration Tests Using FunctionCatalog

To test function bean names and Spring Cloud Function's composition mechanism, you need a Spring context containing `QuoteFunctions` and `QuoteApplication` from section 4.

~~~java
package example.functions;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.util.function.Supplier;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

@SpringBootTest(classes = QuoteApplication.class)
class SupplierCompositionIntegrationTest {

    @Autowired
    private FunctionCatalog catalog;

    @Test
    void catalogComposesSupplierWithFunctions() {
        Supplier<String> quoteSource =
                catalog.lookup(
                        "pendingOrder|priceOrder|formatQuote");

        assertNotNull(quoteSource);
        assertEquals(
                "SKU-17 x 2 = 250000 VND",
                quoteSource.get());
    }
}
~~~

The test above requires Spring Boot Test, a Spring Cloud Function context, and appropriate component scanning. It verifies that the pipeline can be looked up by name, the output contract is `Supplier<String>`, and the result is correct.

To test an event adapter, add tests verifying output via the appropriate binder or broker, especially emission counts and how the source behaves during retries.

### 11.3. Additional Cases Worth Testing

- `Supplier` throws an exception: is the downstream `Function` called?
- `Supplier` returns `null` or invalid data: how does the pipeline react?
- `Function` throws an error: how does the adapter handle it, and does it re-invoke the `Supplier`?
- `Supplier` is triggered multiple times: can data be duplicated?
- Does the final payload have the right structure, charset/content-type for the adapter to send?

Isolated unit tests for each bean do not guarantee the entire name chain and adapter are configured correctly.

## 12. Common Mistakes

| Symptom | Cause | How to address |
|---|---|---|
| `source.andThen(transform)` fails to compile | Java `Supplier` has no `andThen` | Use lambda `() -> transform.apply(source.get())` or Spring composition |
| Calling `pipeline.apply(...)` on a chain starting with `Supplier` | Overall contract is `Supplier` | Look up with the right type and call `get()` |
| Writing `transform|source` | `Supplier` cannot receive data from a preceding function | Place `Supplier` at the start of the pipeline |
| `lookup` cannot find function | Wrong bean name, missing registration, or component scan | Check `@Bean`, dependencies, catalog |
| Name composition succeeds, runtime fails | Intermediate type or actual data is invalid | Inspect each step's signature and test `get()` |
| Duplicate messages emitted | Source returns the same data on repeated calls | Design source tracking, acknowledgment, idempotency |
| No output event observed | Missing binder, binding, or trigger | Configure adapter and run real integration tests |
| `Flux` emits nothing | No subscription or stream completed/errored | Check publisher, operators, and logs |

Do not force every step to `Object` or `String` just to make chaining work. That hides business contracts and makes errors harder to detect.

## 13. Self-Practice Exercises

**Exercise 1.** Given `Supplier<String> source = () -> " 15 "` and `Function<String, Integer> parse = s -> Integer.parseInt(s.trim())`, write the composed `Supplier<Integer>`, invoke it, and state the result.

**Exercise 2.** Given `Supplier<Integer> quantity`, `Function<Integer, Long> price`, and `Function<Long, String> format`, determine the type of the entire pipeline and write a lambda chaining all three steps.

**Exercise 3.** Based on `QuoteFunctions`, write a `spring.cloud.function.definition` value to obtain `Supplier<Quote>`, and another value to obtain `Supplier<String>`.

**Exercise 4.** Why can't `Supplier<OrderDraft>` be connected directly to `Function<Quote, String>` under Java generics? Propose an intermediate function.

**Exercise 5.** If `pendingOrder.get()` throws an exception, do `priceOrder` and `formatQuote` continue running in a synchronous flow? If an adapter retries, what could happen?

**Exercise 6.** A `Supplier` always returns the same order code and is polled periodically to emit events. Identify the risk along with two mitigation measures.

### Solution Hints

- **Exercise 1:** `Supplier<Integer> result = () -> parse.apply(source.get());`; `result.get()` returns `15`.
- **Exercise 2:** `Supplier<String>`; `() -> format.apply(price.apply(quantity.get()))`.
- **Exercise 3:** `"pendingOrder|priceOrder"` yields `Supplier<Quote>`; `"pendingOrder|priceOrder|formatQuote"` yields `Supplier<String>`.
- **Exercise 4:** Needs `Function<OrderDraft, Quote>` such as `priceOrder`.
- **Exercise 5:** Downstream steps are not called if the source throws an exception; retries may invoke the source again.
- **Exercise 6:** May emit duplicates. Design selection of new records/progress tracking and idempotent processing keyed by identifier.

## 14. Key Takeaways

- `Supplier<A>` produces data via `get()`; `Function<A, B>` transforms data via `apply(A)`.
- Composing `Supplier<A>` with `Function<A, B>` yields `Supplier<B>` behaviorally: `() -> transform.apply(source.get())`.
- In plain Java, `Supplier` does not have `andThen`; Spring Cloud Function supports composition by name such as `catalog.lookup("pendingOrder|priceOrder")`.
- For pipelines starting with `Supplier`, retrieve the result type `Supplier<R>` and call `get()`; verify types between every pair of steps.
- `spring.cloud.function.definition` selects logic for adapters; triggers, emission schedules, and error handling depend on the HTTP, messaging, or serverless adapter used.
- When a `Supplier` fetches real data, explicitly design for missing data, source errors, invocation counts, and potential duplicate emissions.
