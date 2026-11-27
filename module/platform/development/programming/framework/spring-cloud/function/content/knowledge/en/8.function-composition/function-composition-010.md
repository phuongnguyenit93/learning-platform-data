# Separating Validation, Transformation, and Business Logic into Reusable Functions

## 1. Learning Objectives

An order-receiving service may have to normalize input data, parse syntax, validate rules, calculate pricing, and produce an output. If you lump all steps into one giant method, changing one rule easily affects the rest, and testing often requires setting up the entire system.

Spring Cloud Function aims to **express business logic as small reusable components**, especially `Supplier<T>`, `Function<T,R>`, and `Consumer<T>`. Each component has an explicit contract, can be registered in `FunctionCatalog`, and can be composed into a pipeline. The logic does not need to know whether it is invoked via HTTP, events, or serverless environments; the adapter layer handles connecting to those protocols.

This lesson belongs to the **Function Composition** chapter: **separating validation, transformation, and business logic into reusable functions**.

After this lesson, you will be able to:

- Identify the kinds of responsibilities that should be separated from a large processing method.
- Design clear data contracts at the boundaries between functions.
- Declare and reuse `Function` beans in Spring.
- Compose by name using `FunctionCatalog.lookup(...)` and select pipelines via `spring.cloud.function.definition`.
- Place side-effecting `Consumer` steps in the right position instead of mixing data writes into every transformation step.
- Write unit tests for individual rules and integration tests for the full pipeline.
- Apply the same functions across multiple HTTP, messaging, or serverless flows when the appropriate adapter is configured.

## 2. When Everything Lives in One Big Function

Consider a function that takes an order string `"sku-42,2"`, normalizes, validates, calculates price, and returns a result string:

~~~java
import java.util.Locale;
import java.util.function.Function;

Function<String, String> handleOrder = raw -> {
    String input = raw.trim().toUpperCase(Locale.ROOT);
    String[] parts = input.split(",", -1);

    if (parts.length != 2) {
        throw new IllegalArgumentException("Invalid format");
    }

    String sku = parts[0].trim();
    int quantity = Integer.parseInt(parts[1].trim());

    if (!sku.matches("SKU-[0-9]+") || quantity <= 0) {
        throw new IllegalArgumentException("Invalid order");
    }

    long total = Math.multiplyExact(quantity, 125_000L);

    return sku + " x " + quantity + " = " + total + " VND";
};
~~~

This function is not wrong merely because it is long, yet it performs many jobs at once:

1. Normalizing the string.
2. Parsing the input syntax.
3. Validating business rules.
4. Calculating the total price.
5. Formatting the result.

If another feature only wants to **calculate the numeric total**, it still has to go through string-formatting logic. If formatting changes, a pricing-related test may break as well. If an event-publishing step is added inside, testing pure logic ends up depending on a broker or database.

The improvement is to split this into small, meaningful functions with explicit data boundaries.

## 3. Three Responsibilities to Distinguish

In practice, "validation," "transformation," and "business logic" may appear together in one service, but they answer different questions.

| Responsibility group | Primary question | Examples | Typical contract |
|---|---|---|---|
| Normalization/transformation | What form and structure does the data have? | Trim, uppercase SKU, parse CSV | `String → OrderDraft` |
| Checking/validation | Does this data satisfy the conditions? | SKU matches pattern, positive quantity | `OrderDraft → ValidatedOrder` |
| Business logic | Given valid data, what must be computed or decided? | Calculate quote, discount, tax | `ValidatedOrder → Quote` |
| Output representation | What format does the interface need? | `Quote → String` or JSON | `Quote → String` |
| Side effects | What must be done with the result? | Save, publish message, audit | `Consumer<Quote>` |

This is a classification for design, not a rule that every tiny operation must have its own bean. Split only when a boundary **has a clear name, reuse value, or independent testability**. Avoid splitting into too many meaningless functions just to increase the bean count.

### 3.1. Validation Does Not Have to Return Boolean

A `Function<OrderDraft, Boolean>` can check validity, yet returning `Boolean` loses the order object at the next connection point:

~~~text
OrderDraft ──validate:Boolean──> Boolean
                                   |
                                   X
                        calculateQuote needs OrderDraft
~~~

When the pipeline needs to continue, you can write:

~~~text
OrderDraft ──validate──> ValidatedOrder ──calculateQuote──> Quote
~~~

With this model, the validation step **returns the verified object** or throws an error if invalid. The `ValidatedOrder` type makes the data-state boundary explicit.

Another design is returning `ValidationResult<OrderDraft>` with error details so a downstream step decides how to handle it. Which design to choose depends on your application's error contract; do not assume every problem must use exceptions.

## 4. Designing the Pipeline Before Writing Code

For text-based orders, we design:

~~~text
Input String: " sku-42, 2 "
              |
              v
normalizeInput                  Function<String,String>
              |
              v
"SKU-42, 2"
              |
              v
parseOrder                      Function<String,OrderDraft>
              |
              v
OrderDraft("SKU-42", 2)
              |
              v
validateOrder                   Function<OrderDraft,ValidatedOrder>
              |
              v
ValidatedOrder("SKU-42", 2)
              |
              v
calculateQuote                  Function<ValidatedOrder,Quote>
              |
              v
Quote("SKU-42", 2, 250000)
              |
              +----------------------------+
              |                            |
              v                            v
formatQuote                    auditQuote
Function<Quote,String>         Consumer<Quote>
              |                            |
              v                            v
"SKU-42 x 2 = 250000 VND"      Record result
~~~

The shared core **normalize → parse → validate → calculate** can form a `Function<String, Quote>`. From there, you choose the **text-returning branch** or the **recording branch** without rewriting the core steps.

### 4.1. Data Contract Table

| Step | Accepts | Returns | Notes |
|---|---|---|---|
| `normalizeInput` | `String` | `String` | Normalizes whitespace, casing |
| `parseOrder` | `String` | `OrderDraft` | Checks basic syntax |
| `validateOrder` | `OrderDraft` | `ValidatedOrder` | Checks business rules |
| `calculateQuote` | `ValidatedOrder` | `Quote` | Calculates total amount |
| `formatQuote` | `Quote` | `String` | Converts result to text |
| `auditQuote` | `Quote` | `void` | Side effect |

Inspect **the output type of each step**, not only the input/output of the whole pipeline. Two functions that both use `String` can still be semantically incompatible, such as one producing a customer ID while the other expects an email.

## 5. Building Meaningful Data Types

Example using Java 17 with `record`:

~~~java
package example.functions;

public final class OrderModels {

    private OrderModels() {}

    public record OrderDraft(String sku, int quantity) {}

    public record ValidatedOrder(String sku, int quantity) {}

    public record Quote(String sku, int quantity, long totalVnd) {}
}
~~~

Why use three records instead of passing the same `Map<String, Object>` everywhere?

- `OrderDraft` represents parsed data that is **not yet guaranteed to be business-valid**.
- `ValidatedOrder` represents data that has passed validation.
- `Quote` is the calculation result, adding the total amount.

Each record establishes a static contract. If you accidentally chain `Function<OrderDraft, Quote>` after a function returning `String`, Java generics catch the error when composing directly in code.

Type names alone do not guarantee safety if callers can arbitrarily construct `ValidatedOrder`. In this lesson, only `validateOrder` is expected to construct that type in the pipeline. In real applications, you can enforce invariants via domain constructors/factories if needed.

## 6. Declaring Reusable Functions in Spring

Each business function is registered as a separate bean. The following example is ready to run when placed in a Spring Boot application with the appropriate Spring Cloud Function dependency.

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
public class OrderFunctions {

    @Bean
    public Function<String, String> normalizeInput() {
        return raw -> {
            if (raw == null) {
                throw new IllegalArgumentException(
                        "Input data must not be null");
            }
            return raw.trim().toUpperCase(Locale.ROOT);
        };
    }

    @Bean
    public Function<String, OrderDraft> parseOrder() {
        return raw -> {
            String[] parts = raw.split(",", -1);

            if (parts.length != 2) {
                throw new IllegalArgumentException(
                        "Expected format: SKU,quantity");
            }

            String sku = parts[0].trim();
            int quantity;
            try {
                quantity = Integer.parseInt(parts[1].trim());
            } catch (NumberFormatException ex) {
                throw new IllegalArgumentException(
                        "Quantity must be an integer", ex);
            }

            return new OrderDraft(sku, quantity);
        };
    }

    @Bean
    public Function<OrderDraft, ValidatedOrder> validateOrder() {
        return draft -> {
            if (draft == null
                    || draft.sku() == null
                    || !draft.sku().matches("SKU-[0-9]+")
                    || draft.quantity() <= 0
                    || draft.quantity() > 100) {
                throw new IllegalArgumentException(
                        "Invalid SKU or quantity");
            }

            return new ValidatedOrder(
                    draft.sku(), draft.quantity());
        };
    }

    @Bean
    public Function<ValidatedOrder, Quote> calculateQuote() {
        return order -> {
            long unitPriceVnd = 125_000L;
            long totalVnd = Math.multiplyExact(
                    order.quantity(), unitPriceVnd);

            return new Quote(
                    order.sku(), order.quantity(), totalVnd);
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

**Rules in the example:** SKU follows `SKU-<digits>`; quantity is between 1 and 100; fixed unit price is 125,000 VND. This is a simplified model for the lesson, not a complete quoting system with taxes, promotions, or inventory.

### 6.1. Each Bean Has a Clear Name and Responsibility

When using `@Bean` without specifying a name, Spring normally names the bean after the method name. The names are:

~~~text
normalizeInput
parseOrder
validateOrder
calculateQuote
formatQuote
~~~

`FunctionCatalog` can look them up by name. If you use `@Bean("myName")`, the registered name is `myName` instead of the default method name.

Separating by name lets you choose different combinations via configuration. However, business code should never arbitrarily look up and invoke any name from untrusted input; if dynamic pipeline selection is needed, control an allowlist of permitted names.

### 6.2. Boundaries of Each Step

**`normalizeInput`** should handle data formatting issues, not calculate prices or save orders.

**`parseOrder`** accepts valid syntax and produces structured data. It can still throw when quantity cannot be parsed, but does not need to know prices, inventory, or promotion rules.

**`validateOrder`** checks business invariants. In this example it does not query a database or mutate external data.

**`calculateQuote`** accepts only validated input and computes `Quote`; it is not responsible for building an HTTP response.

**`formatQuote`** turns the domain result into a string. If a recipient wants JSON or a `Message`, the pricing calculation does not need to change.

## 7. Composing in Plain Java: The Compiler Checks Generics

You do not need `FunctionCatalog` to understand composition principles. In Java, you can use `andThen`:

~~~java
import java.util.function.Function;

import example.functions.OrderModels.OrderDraft;
import example.functions.OrderModels.ValidatedOrder;
import example.functions.OrderModels.Quote;

OrderFunctions config = new OrderFunctions();

Function<String, String> normalize = config.normalizeInput();
Function<String, OrderDraft> parse = config.parseOrder();
Function<OrderDraft, ValidatedOrder> validate =
        config.validateOrder();
Function<ValidatedOrder, Quote> price =
        config.calculateQuote();
Function<Quote, String> format = config.formatQuote();

Function<String, String> fullPipeline =
        normalize
                .andThen(parse)
                .andThen(validate)
                .andThen(price)
                .andThen(format);

System.out.println(fullPipeline.apply(" sku-42, 2 "));
// SKU-42 x 2 = 250000 VND
~~~

The snippet above illustrates plain Java composition by instantiating `OrderFunctions` to obtain the stateless lambdas. In a Spring application, you do not invoke `@Bean` methods directly to look up functions; `FunctionCatalog` or dependency injection uses the Spring-managed beans.

### 7.1. Selecting Reusable Composition Slices

You do not have to run the entire pipeline every time:

~~~java
Function<String, ValidatedOrder> parseValidated =
        normalize.andThen(parse).andThen(validate);

Function<String, Quote> quoteOrder =
        parseValidated.andThen(price);

Function<String, String> quoteAsText =
        quoteOrder.andThen(format);
~~~

These three compositions serve different goals:

| Pipeline | Input | Output | Use case |
|---|---|---|---|
| `parseValidated` | `String` | `ValidatedOrder` | Validate and normalize |
| `quoteOrder` | `String` | `Quote` | Calculate price and return object |
| `quoteAsText` | `String` | `String` | Produce text result |

A single normalization rule is reused across all three without duplicating code.

### 7.2. compose Syntax Changes Reading Order, Not the Contract

`andThen` reads in execution order:

~~~java
normalize.andThen(parse).andThen(validate)
~~~

Whereas `compose` places the earlier-running `Function` in the argument:

~~~java
Function<String, ValidatedOrder> same =
        validate.compose(parse).compose(normalize);
~~~

Both produce the order `normalize → parse → validate`. When designing a multi-step chain, `andThen` or the name composition `A|B|C` is usually easier to read along the data flow.

## 8. Composing by Name with FunctionCatalog.lookup

Spring Cloud Function lets you look up a single function or a composition expression from registered beans.

Service example:

~~~java
package example.functions;

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

    public Quote quote(String rawOrder) {
        Function<String, Quote> pipeline =
                catalog.lookup(
                    "normalizeInput|parseOrder|validateOrder|calculateQuote");

        if (pipeline == null) {
            throw new IllegalStateException(
                    "Quote pipeline not found");
        }

        return pipeline.apply(rawOrder);
    }

    public String quoteAsText(String rawOrder) {
        Function<String, String> pipeline =
                catalog.lookup(
                    "normalizeInput|parseOrder|validateOrder"
                    + "|calculateQuote|formatQuote");

        if (pipeline == null) {
            throw new IllegalStateException(
                    "Text pipeline not found");
        }

        return pipeline.apply(rawOrder);
    }
}
~~~

A Spring context containing `OrderFunctions` and the appropriate Spring Cloud Function context is needed for `FunctionCatalog` to be injected.

The `|` symbol expresses the pipeline **from left to right**:

~~~text
normalizeInput → parseOrder → validateOrder
               → calculateQuote → formatQuote
~~~

The output signature of `lookup` in Java code must match the **overall contract of the name chain**, not just whatever generic type the author wishes. A typo or mismatched pair may only surface as an error at runtime during lookup or execution.

### 8.1. Why Are Catalog Tests Still Necessary?

The Java compiler can verify `normalize.andThen(parse)` because both variables carry concrete generics. With `catalog.lookup("normalizeInput|parseOrder")`, the step names are a string; the compiler cannot inspect bean names or each function's real types inside that string.

Verify:

- Are the beans registered under the exact names?
- Is the composition order right?
- Does each step's output connect to the next step's input?
- Does the actual payload match the data type assumed by Java code?
- If an error occurs at a step, have any side effects already run?

## 9. Selecting the Pipeline via spring.cloud.function.definition

When you want an adapter to use a specific piece of logic, you can set it in `application.yml`:

~~~yaml
spring:
  cloud:
    function:
      definition: "normalizeInput|parseOrder|validateOrder|calculateQuote|formatQuote"
~~~

Or `application.properties`:

~~~properties
spring.cloud.function.definition=normalizeInput|parseOrder|validateOrder|calculateQuote|formatQuote
~~~

The configuration value selects the **function name/combination** that the integration layer will use; it does not define a new algorithm.

| Call / setting | Role |
|---|---|
| `FunctionCatalog.lookup(...)` | Java code looks up a function/pipeline by name |
| `spring.cloud.function.definition` | Selects a pipeline for the integration layer |
| HTTP adapter | Maps requests/responses to the exposed logic |
| Messaging adapter | Maps messages/bindings to the logic |
| Serverless adapter | Maps events/handlers to the logic |

Setting the `definition` property alone **does not automatically configure HTTP endpoints, broker topics, message converters, or serverless triggers**. Adapters have their own conventions/configurations and may have limitations on which function shapes they expose.

### 9.1. Returning an Object Instead of Text

If a recipient needs domain data to serialize as JSON, you can select:

~~~yaml
spring:
  cloud:
    function:
      definition: "normalizeInput|parseOrder|validateOrder|calculateQuote"
~~~

The pipeline then has the contract `Function<String, Quote>`. That is an example of reusing pricing logic without forcing it through `formatQuote`.

Do not assume an adapter automatically preserves every header or serializes every POJO into JSON as expected. Testing serialization, content-type, and type information is a critical part of integration testing.

## 10. Separating Side Effects into a Dedicated Consumer

Pure pricing and recording a quote are two different responsibilities.

If you want to audit a quote, you can declare a `Consumer` accepting `Quote`, placed at the **end** of another pipeline.

~~~java
package example.functions;

import java.util.List;
import java.util.Queue;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import example.functions.OrderModels.Quote;

@Configuration
public class QuoteAuditFunctions {

    public static final class QuoteLedger {
        private final Queue<Quote> entries =
                new ConcurrentLinkedQueue<>();

        public void append(Quote quote) {
            entries.add(quote);
        }

        public List<Quote> snapshot() {
            return List.copyOf(entries);
        }
    }

    @Bean
    public QuoteLedger quoteLedger() {
        return new QuoteLedger();
    }

    @Bean
    public Consumer<Quote> auditQuote(QuoteLedger ledger) {
        return ledger::append;
    }
}
~~~

`QuoteLedger` is only an in-memory temporary store for illustration, not a database with transactions or deduplication. It is a dependency bean of the `Consumer`; `auditQuote` itself is the function used in composition.

### 10.1. Text-Returning Branch vs. Side-Effect Branch

Two pipelines share the pricing core:

~~~text
normalizeInput|parseOrder|validateOrder|calculateQuote|formatQuote
        ⇒ Function<String,String>

normalizeInput|parseOrder|validateOrder|calculateQuote|auditQuote
        ⇒ Consumer<String>
~~~

The second branch ends with a `Consumer`, so it is invoked via `accept(...)`:

~~~java
import java.util.function.Consumer;

Consumer<String> auditPipeline =
        catalog.lookup(
            "normalizeInput|parseOrder|validateOrder"
            + "|calculateQuote|auditQuote");

if (auditPipeline == null) {
    throw new IllegalStateException("Missing audit pipeline");
}

auditPipeline.accept("sku-42,2");
~~~

Do not call `apply(...)` on a `Consumer`: `Consumer.accept` returns `void`.

### 10.2. Why Not Place the Consumer in the Middle and Continue Formatting?

Do not expect the chain:

~~~text
calculateQuote|auditQuote|formatQuote
~~~

to automatically pass `Quote` from `auditQuote` to `formatQuote`: `auditQuote` returns `void`, so there is no output for the next step.

If business logic strictly requires both auditing and returning text, design an explicit orchestration or a `Function` with a clear return contract, while accounting for transactions and error handling. Never assume a `Consumer` emits data for a subsequent `Function`.

## 11. Syntax Validation and Business Validation Are Two Different Boundaries

In the example:

~~~text
String
  |
parseOrder
  |   Error if comma is missing or quantity cannot be parsed
  v
OrderDraft
  |
validateOrder
  |   Error if SKU is wrong or quantity is outside 1..100
  v
ValidatedOrder
~~~

There are two different kinds of errors.

**Structural errors:** `"SKU-42"` is missing the quantity field, or `"SKU-42,abc"` cannot be parsed as a number. The `parseOrder` step is responsible for catching these.

**Rule errors:** `"SKU-42,0"` parses cleanly, yet the quantity is invalid. The `validateOrder` step is responsible for catching these.

Separating the two groups makes error messages and tests more focused. Later, if the "maximum quantity 100" rule changes to 200, only validation needs updating—not parsing or formatting.

### 11.1. Exceptions Are Not Always the Optimal Model

The simple example uses `IllegalArgumentException` to keep the lesson concise. If an application needs to return multiple errors at once to a client, you can use a result type:

~~~java
record ValidationError(String field, String message) {}
record ValidationResult<T>(
        T value,
        List<ValidationError> errors) {}
~~~

This snippet is a design suggestion: in real use, import `java.util.List` and enforce invariants on `ValidationResult`.

When using `ValidationResult<T>`, the next step must know how to handle error states rather than receiving `T` directly. You cannot connect `Function<OrderDraft, ValidationResult<OrderDraft>>` directly to `Function<OrderDraft, Quote>` without an appropriate intermediate step.

## 12. Placing Reusable Functions at Sensible Boundaries

Splitting into small pieces is not just so you can write `A|B|C`. Use clear criteria:

1. **One responsibility expressible by name.** `normalizeInput` is clearer than `processStep1`.
2. **Explicit type contracts.** `ValidatedOrder` separates data before and after validation.
3. **Reusable logic.** `calculateQuote` does not depend on HTTP request text or Kafka headers.
4. **Independent testability.** `validateOrder` can be tested without a database.
5. **Reasonable granularity.** Do not create ten beans just to wrap ten trivial `String.trim` calls that have no domain meaning.
6. **Clear placement of side effects.** Keep computation separate from persistence/message publishing whenever possible.
7. **Clear errors and observability.** Each step can report failure causes without blurring adapter boundaries.

### 12.1. Pure Functions vs. Functions with Side Effects

A function is called *pure* when the same input always yields the same output and causes no observable side effects. `calculateQuote` with a fixed unit price in this lesson is close to a pure function. However, if the function queries mutable prices from a database, it is no longer pure in that sense, even though its Java signature remains `Function<ValidatedOrder, Quote>`.

Thus, **a Function signature does not automatically guarantee purity**. Distinguish the Java interface type from the implementation's actual behavior. When I/O is needed, design dependencies and error handling explicitly.

### 12.2. Keep Transport Details Out of the Core

Avoid letting `calculateQuote` depend directly on `HttpServletRequest`, `MessageHeaders`, topic names, or a specific AWS event. Those details should be mapped at the adapter so the same calculation can be reused across contexts.

For example, a controller can extract an HTTP body into a `String`, while a message consumer can read the payload from a `Message<String>`. Both can invoke a business pipeline accepting `String` once conversion is properly verified.

## 13. Connecting to a Supplier and Data Sources

Sometimes the application does not receive input from a request, and instead **actively fetches an order**. In that case, a `Supplier<String>` can serve as the source for the pipeline:

~~~java
import java.util.function.Function;
import java.util.function.Supplier;

Supplier<String> pendingOrder =
        () -> "sku-42,2";

Function<String, String> quoteAsText =
        normalize
                .andThen(parse)
                .andThen(validate)
                .andThen(price)
                .andThen(format);

Supplier<String> quoteSource =
        () -> quoteAsText.apply(pendingOrder.get());

System.out.println(quoteSource.get());
// SKU-42 x 2 = 250000 VND
~~~

This is a plain Java example composing `Supplier<String>` with `Function<String,String>`. In Spring Cloud Function, when the corresponding beans are registered and composition is supported, the expression by name can be:

~~~text
pendingOrder|normalizeInput|parseOrder|validateOrder|calculateQuote|formatQuote
~~~

The overall contract is then a `Supplier<String>`. Verify this on your framework and adapter version, especially how the source is triggered, polled, or subscribed to.

### 13.1. What If It Ends with a Consumer?

If the `pendingOrder` source is composed further with `auditQuote` (after the `Quote`-producing steps), the entire chain behaves like a **`Runnable`**: taking no input and returning no output.

~~~text
Supplier<String> → Function<String,Quote> → Consumer<Quote>
                                 ⇒ Runnable
~~~

Do not assume every adapter automatically schedules or binds a `Runnable` to a broker. In Java, it requires calling `run()`; in a real system, it requires an appropriate trigger mechanism.

## 14. Reuse Across HTTP, Events, and Serverless

The core in this lesson uses only `String`, `OrderDraft`, `ValidatedOrder`, and `Quote`. Therefore, the same logic can sit behind multiple adapters:

~~~text
HTTP Request ──────┐
                   │
Kafka/Event ───────┼─> Adapter / deserialize
                   │         |
Serverless Event ──┘         v
                        normalizeInput
                              |
                              v
                          parseOrder
                              |
                              v
                         validateOrder
                              |
                              v
                        calculateQuote
                              |
                +-------------+-------------+
                |                           |
                v                           v
           formatQuote                 auditQuote
                |                           |
                v                           v
        HTTP response / text       DB / event / audit
~~~

This diagram is an architectural model. It does not mean that simply setting the same `definition` property makes every adapter work simultaneously without configuration.

| Environment | Reused logic | What the adapter must handle |
|---|---|---|
| HTTP | `Function<String,Quote>` or `Function<String,String>` | Routes, request body, status codes, JSON/text serialization |
| Events | Core Functions and terminal Consumer | Input/output bindings, content-type, headers, retry/ack |
| Serverless | Function matching the event type | Handler, trigger, payload and response mapping |
| Internal Java | `FunctionCatalog` or injected beans | Calling `apply`/`accept` and handling exceptions |

### 14.1. Do Not Let Conversion Mask Contract Bugs

An adapter may support converting `Message<?>`, JSON, or payloads to POJOs. However, never rely on automatic conversion to patch a type-mismatched composition chain.

For instance, `Function<OrderDraft,ValidatedOrder>` cannot be treated as `Function<Quote,ValidatedOrder>` just because both objects happen to have similar fields. When switching transports, proactively test the conversion boundary.

### 14.2. Handling Errors at the Outer Boundary

In Java, `parseOrder` may throw `IllegalArgumentException`. An HTTP adapter may map it to a 4xx status code according to the application's error handling; a messaging adapter may retry or route to a dead-letter destination; a serverless adapter may report an invocation failure.

**Composition does not decide the transport's error-handling policy.** The core should fail clearly with consistent contracts, while adapters translate those failures into the right protocol mechanics.

## 15. Reusing Individual Steps with Reactive Data

If a new pipeline receives `Flux<String>` instead of individual `String` values, you do not need to rewrite all business rules. You can lift a `Function<String,Quote>` to process elements one by one:

~~~java
import java.util.function.Function;
import reactor.core.publisher.Flux;

Function<String, Quote> quoteOne =
        normalize
                .andThen(parse)
                .andThen(validate)
                .andThen(price);

Function<Flux<String>, Flux<Quote>> quoteStream =
        flux -> flux.map(quoteOne);
~~~

Here, `Quote` is `OrderModels.Quote` imported into scope. `quoteOne` is the imperative function for a single order; `quoteStream` simply applies it to each element.

Do not chain `Function<String,Quote>` directly into `Function<Flux<Quote>,Flux<String>>` using Java `andThen`: `Quote` differs from `Flux<Quote>`. A `map` bridge creates an explicit reactive contract.

### 15.1. Reactive Errors and Subscriptions

`Flux.map` normally runs the mapper upon subscription. If `quoteOne` throws an exception for an element, Reactor converts the mapper exception into an `onError` signal, and the stream typically terminates unless proper error handling is added. This differs from `quoteOne.apply(raw)` throwing an exception directly in synchronous Java.

Never call `block()` arbitrarily on an event loop. If a business step contains blocking I/O, putting it inside `map` does not make the I/O non-blocking; use an appropriate scheduler design or a reactive client.

This lesson focuses mainly on separating logic. In real reactive applications, also pay attention to element ordering, backpressure, concurrency, and per-element error policies.

## 16. Testing Each Function Independently

A major benefit of this design is testing business rules without starting Spring or external connections.

### 16.1. Unit Testing Normalization and Parsing

~~~java
package example.functions;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.function.Function;
import org.junit.jupiter.api.Test;

import example.functions.OrderModels.OrderDraft;

class OrderFunctionsUnitTest {

    private final OrderFunctions functions =
            new OrderFunctions();

    @Test
    void normalizeAndParseProduceDraft() {
        Function<String, String> normalize =
                functions.normalizeInput();

        Function<String, OrderDraft> parse =
                functions.parseOrder();

        String value = normalize.apply(" sku-42, 2 ");

        assertEquals("SKU-42, 2", value);
        assertEquals(
                new OrderDraft("SKU-42", 2),
                parse.apply(value));
    }

    @Test
    void parserRejectsMissingOrNonNumericQuantity() {
        Function<String, OrderDraft> parse =
                functions.parseOrder();

        assertThrows(IllegalArgumentException.class,
                () -> parse.apply("SKU-42"));

        assertThrows(IllegalArgumentException.class,
                () -> parse.apply("SKU-42,abc"));
    }
}
~~~

The tests need no Spring context, database, or broker. When parsing rules change, tests stay focused on that exact step.

### 16.2. Unit Testing Validation Independently

~~~java
package example.functions;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.function.Function;
import org.junit.jupiter.api.Test;

import example.functions.OrderModels.OrderDraft;
import example.functions.OrderModels.ValidatedOrder;

class OrderValidationTest {

    private final Function<OrderDraft, ValidatedOrder> validate =
            new OrderFunctions().validateOrder();

    @Test
    void acceptsValidOrder() {
        assertEquals(
                new ValidatedOrder("SKU-42", 2),
                validate.apply(new OrderDraft("SKU-42", 2)));
    }

    @Test
    void rejectsInvalidQuantity() {
        assertThrows(IllegalArgumentException.class,
                () -> validate.apply(new OrderDraft("SKU-42", 0)));

        assertThrows(IllegalArgumentException.class,
                () -> validate.apply(new OrderDraft("SKU-42", 101)));
    }
}
~~~

There is no need to check pricing math just to verify whether validation enforces the 1..100 bounds.

### 16.3. Unit Testing Pricing Independently

~~~java
package example.functions;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.function.Function;
import org.junit.jupiter.api.Test;

import example.functions.OrderModels.ValidatedOrder;
import example.functions.OrderModels.Quote;

class QuoteCalculationTest {

    @Test
    void calculatesTotalFromValidatedOrder() {
        Function<ValidatedOrder, Quote> price =
                new OrderFunctions().calculateQuote();

        Quote actual = price.apply(
                new ValidatedOrder("SKU-42", 2));

        assertEquals(
                new Quote("SKU-42", 2, 250_000L),
                actual);
    }
}
~~~

Thanks to `ValidatedOrder`, the test focuses on calculation with data already guaranteed valid rather than repeating string and syntax checks.

## 17. Testing Composition in Spring Cloud Function

Unit-testing each step does not guarantee that bean names, composition order, and Spring configuration are right. To test `FunctionCatalog`, you need a Spring application context containing the corresponding beans.

### 17.1. Example Application Class

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

Place `OrderApplication` in the same package as `OrderFunctions`, `QuoteAuditFunctions`, and `QuoteService` for default component scanning, while declaring the appropriate Spring Boot/Spring Cloud Function dependencies.

### 17.2. Integration Test for Lookup and Execution

~~~java
package example.functions;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.function.Function;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

import example.functions.OrderModels.Quote;

@SpringBootTest(classes = OrderApplication.class)
class OrderPipelineCatalogTest {

    @Autowired
    FunctionCatalog catalog;

    @Test
    void composesReusableStepsIntoQuote() {
        Function<String, Quote> quoteOrder =
                catalog.lookup(
                    "normalizeInput|parseOrder|validateOrder|calculateQuote");

        assertNotNull(quoteOrder);

        assertEquals(
                new Quote("SKU-42", 2, 250_000L),
                quoteOrder.apply(" sku-42, 2 "));
    }

    @Test
    void rejectsInvalidOrderBeforePricing() {
        Function<String, Quote> quoteOrder =
                catalog.lookup(
                    "normalizeInput|parseOrder|validateOrder|calculateQuote");

        assertNotNull(quoteOrder);

        assertThrows(IllegalArgumentException.class,
                () -> quoteOrder.apply("sku-42,0"));
    }
}
~~~

When switching to `FunctionCatalog.lookup(...)` in Java code, function names are strings resolved at runtime. Integration tests catch renamed `@Bean` methods, missing beans, wrong composition orders, or unexpected data type handling.

### 17.3. Testing the Side-Effecting Consumer Branch

~~~java
package example.functions;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.function.Consumer;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

import example.functions.OrderModels.Quote;

@SpringBootTest(classes = OrderApplication.class)
class QuoteAuditCatalogTest {

    @Autowired
    FunctionCatalog catalog;

    @Autowired
    QuoteAuditFunctions.QuoteLedger ledger;

    @Test
    void auditReceivesCalculatedQuote() {
        Consumer<String> pipeline =
                catalog.lookup(
                    "normalizeInput|parseOrder|validateOrder"
                    + "|calculateQuote|auditQuote");

        assertNotNull(pipeline);
        pipeline.accept(" sku-42,2 ");

        assertTrue(ledger.snapshot().contains(
                new Quote("SKU-42", 2, 250_000L)));
    }
}
~~~

In real applications, when multiple tests share a context or state store, isolate or reset data between tests. This test only proves that the `Consumer` is called and data enters the sample ledger; it does not prove durable database writes or broker publishing.

### 17.4. The Adapter Test Layer Is Still Essential

To deploy over HTTP or event-driven systems, add tests verifying:

- Is the request/message mapped to the expected input type?
- Does the adapter actually use `definition`?
- Are output contents, content-type, and serialization right?
- Are input errors returned via HTTP or message handling as expected?
- Do retries cause duplicate writes when the `Consumer` has side effects?
- Are critical headers/correlation IDs handled properly?

**Catalog tests verify composition logic; they do not replace HTTP/broker/serverless integration tests.**

## 18. Common Design Mistakes

| Issue | Why it is suboptimal | How to improve |
|---|---|---|
| One huge Function doing everything | Hard to test and partially reuse | Separate normalize, parse, validate, calculate |
| `validateOrder` returns only Boolean | Next step no longer has `Order` to price | Return `ValidatedOrder` or a result carrying data |
| Every step uses `String` | Easy to mix data with different meanings | Use clear domain records |
| Pricing Function builds HTTP response | Core tightly coupled to transport | Move response mapping to the adapter |
| Pricing Function writes to database | Hard to test pricing logic independently | Use a dedicated Consumer or orchestration |
| Consumer placed mid-pipeline before Function | Consumer has no output | Move Consumer to the end or write a workflow |
| Function order reversed | Intermediate types may not match | Draw diagram/contract table beforehand |
| Arbitrarily casting raw Function from catalog | Hides generic errors until runtime | Test typed lookup and individual steps |
| Treating `definition` as transport config | Property creates no broker/HTTP routes | Configure the corresponding adapter |
| Function holds shared mutable state | Fails under concurrent invocations | Prefer stateless; synchronize if state is needed |
| Ignoring retries when side effects exist | Can create duplicate records | Use idempotency, transactions, unique keys |

## 19. Checklist Before Putting a Pipeline into Use

Before exposing a Spring Cloud Function pipeline, answer these questions:

1. Does each step have a clear responsibility and domain-meaningful name?
2. Do each step's inputs/outputs use concrete Java types, avoiding unnecessary `Object`?
3. Does the validation step retain the data needed by subsequent business steps?
4. Is calculation logic free of HTTP, broker, and serverless runtime dependencies?
5. Do side effects have a dedicated place and separate error policies?
6. Are all function beans registered in Spring under their actual names?
7. Does `FunctionCatalog.lookup("A|B|C")` resolve and execute properly?
8. Is the overall contract `Function`, `Supplier`, `Consumer`, or `Runnable`?
9. Has the adapter been configured and tested with real payloads/headers?
10. Have errors, retries, concurrency, and duplicate handling been checked where needed?

You do not need to use all four output forms in a single application. Pick the simplest pipeline that satisfies the business requirement.

## 20. Practice Exercises

**Exercise 1 — Splitting a Large Function.** A function `handlePayment` trims input, parses an amount, validates the amount is positive, calculates a fee, and writes to a database. Propose names and signatures for at least four independent functions and identify which function has side effects.

**Exercise 2 — Fixing Validation.** Given `parse: String → OrderDraft`, `check: OrderDraft → Boolean`, and `price: ValidatedOrder → Quote`, why can't all three be chained directly with `|`? Write the new signature for the validation step.

**Exercise 3 — Choosing Multiple Usage Patterns.** With the beans `normalizeInput`, `parseOrder`, `validateOrder`, `calculateQuote`, and `formatQuote`, write a `FunctionCatalog.lookup(...)` chain yielding `Function<String,Quote>` and another yielding `Function<String,String>`.

**Exercise 4 — Consumer Boundary.** Also register `auditQuote: Consumer<Quote>`. Write the composition chain yielding `Consumer<String>` and state the Java method used to invoke that pipeline. Why can't you append `formatQuote` afterward?

**Exercise 5 — Classifying Errors.** For inputs `"SKU-42,abc"`, `"SKU-42,0"`, and `"SKU-42,2"`, determine which step catches the error or produces the result. State the final output for the valid case.

**Exercise 6 — Multi-Protocol Configuration.** The same quote pipeline is used in a REST endpoint and an event-consuming service. Which parts can be reused, and which parts belong to adapter configuration? Why is setting `spring.cloud.function.definition` alone not enough?

**Exercise 7 — Reactive.** A `Flux<String>` stream carries multiple orders. Write a bridge using `map` to reuse `Function<String,Quote>`, then describe when calculation errors can be emitted via `onError`.

**Exercise 8 — Unit Tests and Integration Tests.** Pick two tests that need only plain Java and two tests that need a Spring context/adapter. Explain what kinds of bugs each test layer catches.

### Solution Hints

- **Exercise 1:** For example, `normalize: String→String`, `parse: String→PaymentDraft`, `validate: PaymentDraft→ValidatedPayment`, `calculateFee: ValidatedPayment→PaymentResult`, `persist: Consumer<PaymentResult>`.
- **Exercise 2:** `Boolean` does not carry `ValidatedOrder`. Change it to `Function<OrderDraft,ValidatedOrder>` or a result type with an appropriate data conversion step.
- **Exercise 3:** `"normalizeInput|parseOrder|validateOrder|calculateQuote"` and that chain with `"|formatQuote"` appended.
- **Exercise 4:** `"normalizeInput|parseOrder|validateOrder|calculateQuote|auditQuote"`; retrieve `Consumer<String>` and call `accept(input)`. A `Consumer` does not return a `Quote` for a downstream step.
- **Exercise 5:** `abc` fails in `parseOrder`; quantity `0` fails in `validateOrder`; `2` yields `Quote("SKU-42",2,250000)` and text `"SKU-42 x 2 = 250000 VND"`.
- **Exercise 6:** The core and function beans are shared; HTTP bindings, message bindings, serialization, error mapping, and retries belong to the adapter/integration layer.
- **Exercise 7:** `Function<Flux<String>,Flux<Quote>> all = flux -> flux.map(quoteOne);`. Upon subscription and when the failing element is processed, the stream can emit `onError`.
- **Exercise 8:** Unit-test parse/validate and calculate; integration-test catalog + adapter with real payloads, headers, and responses/acks.

## 21. Key Takeaways

- Separate **normalization**, **parsing**, **validation**, **calculation**, and **side effects** along business-meaningful boundaries, not merely by method length.
- Each `Function<T,R>` should have a clear type contract and responsibility. Use domain types like `OrderDraft`, `ValidatedOrder`, and `Quote` to express data state.
- A pipeline can be composed with Java's `andThen` or by name `A|B|C` via `FunctionCatalog`; check types at every connection point.
- From one set of function beans, you can build multiple pipelines: returning a domain object, formatting text, or ending with a `Consumer` to record results.
- `spring.cloud.function.definition` selects logic for adapters, but does not configure HTTP, events, or serverless automatically.
- Testing individual functions isolates rules; testing `FunctionCatalog` verifies composition names/order; testing adapters verifies protocols, payloads, and error handling.
- Clean separation lets the same business logic be reused across contexts without duplication or tight coupling to transport.
