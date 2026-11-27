# Functions Composed in Wrong Order or Incompatible Types

## 1. Symptom: Individual Functions Work, Yet Composition Fails

A **Spring Cloud Function** application defines three order-processing steps:

~~~java
@Bean
public Function<RawOrder, NormalizedOrder> normalizeOrder() {
    return order -> new NormalizedOrder(
        order.orderId().trim().toUpperCase(),
        order.items()
    );
}

@Bean
public Function<NormalizedOrder, PriceQuote> calculatePrice() {
    return order -> new PriceQuote(
        order.orderId(),
        calculateTotal(order.items())
    );
}

@Bean
public Function<PriceQuote, OrderReceipt> renderReceipt() {
    return quote -> new OrderReceipt(
        quote.orderId(),
        quote.total().toPlainString()
    );
}
~~~

Each function works properly when invoked individually. Yet after configuring:

~~~properties
spring.cloud.function.definition=calculatePrice|normalizeOrder|renderReceipt
~~~

the application fails to build a valid pipeline or throws errors only when data flows through. The order here is invalid: `calculatePrice` outputs `PriceQuote`, while `normalizeOrder` expects `RawOrder`.

Common symptoms:

- Individual functions work, yet composition fails to resolve or fails on invocation.
- `ClassCastException`, `MessageConversionException`, or type conversion errors mid-pipeline.
- Unexpected output even though every step returns the expected Java type.
- The first function runs, yet the second does not receive the expected data.
- A `Consumer` placed mid-pipeline leaves the next step with no input data.
- `Supplier`/`Consumer` composed in the wrong direction changes the resulting input/output types expected by callers.
- Imperative composition works, yet a reactive pipeline emits nothing due to missing subscription or mismatched element types.
- Configuring `;` instead of `|` causes the application to create multiple independent functions/bindings rather than one sequential chain.

This lesson belongs to the **Diagnostics** chapter of the **SPRING_CLOUD_FUNCTION** module. The module focuses on building reusable business logic with `Supplier`, `Function`, and `Consumer`, decoupled from invocation protocols; covering `FunctionCatalog`, composition, message conversion, and deployment over HTTP, events, or serverless.

**Primary diagnostic question:**

> Is each step's output valid input for the next step, in the right order and with the right execution contract?

### Learning Objectives

After this lesson, you will be able to:

1. Understand sequential composition via `Function.andThen` and left-to-right ordering.
2. Distinguish composition from selecting multiple independent functions in Spring Cloud Stream or the web adapter.
3. Check compatibility between generic inputs and outputs of two functions.
4. Recognize when Spring Cloud Function can use message conversion to bridge differing types.
5. Distinguish `Function`, `Supplier`, `Consumer`, and the resulting composed type.
6. Diagnose errors caused by wrong order, typos, missing beans, converters, message headers, reactive streams, or side effects.
7. Test individual functions, compositions via `FunctionCatalog`, and real adapters.
8. Design pipelines with clear data contracts that are observable and safe to deploy.

## 2. What Does Composition Mean?

Function composition chains multiple steps into **a sequential processing pipeline**. The output of each step becomes the input of the next step.

~~~mermaid
flowchart LR
    INPUT["RawOrder"] --> A["normalizeOrder"]
    A --> B["calculatePrice"]
    B --> C["renderReceipt"]
    C --> OUTPUT["OrderReceipt"]
~~~

Given these functions:

- `normalizeOrder`: `Function<RawOrder, NormalizedOrder>`.
- `calculatePrice`: `Function<NormalizedOrder, PriceQuote>`.
- `renderReceipt`: `Function<PriceQuote, OrderReceipt>`.

We get the pipeline:

~~~text
RawOrder
  → normalizeOrder
  → NormalizedOrder
  → calculatePrice
  → PriceQuote
  → renderReceipt
  → OrderReceipt
~~~

In Java, composing two `Function` instances relies on `andThen`:

~~~java
Function<RawOrder, OrderReceipt> pipeline =
    normalizeOrder
        .andThen(calculatePrice)
        .andThen(renderReceipt);
~~~

`andThen` means **run the current function first, then pass its result to the supplied function**. Therefore:

~~~java
f.andThen(g)
~~~

corresponds to:

~~~text
input → f → output of f → g → final output
~~~

This is neither parallel execution, fan-out, nor invoking multiple independent handlers. If a function must split data into multiple outputs, that is a function arity / multi-output problem with a separate contract.

### 2.1. Ordering Is Part of the Contract

Two functions with the exact same `String → String` type can produce different outputs when reordered.

~~~java
Function<String, String> appendSuffix =
    value -> value + "-sig";

Function<String, String> uppercase =
    String::toUpperCase;
~~~

Composed in one order:

~~~java
String first = appendSuffix
    .andThen(uppercase)
    .apply("order-1");
~~~

Result:

~~~text
ORDER-1-SIG
~~~

Reversed order:

~~~java
String second = uppercase
    .andThen(appendSuffix)
    .apply("order-1");
~~~

Result:

~~~text
ORDER-1-sig
~~~

Both pipelines are type-compatible, yet their **business semantics differ**. You cannot look at generic types alone and assume the order is right.

## 3. DTOs Used Throughout the Example

Using Java 17+ and records to express each step's contract:

~~~java
package demo.composition;

import java.math.BigDecimal;
import java.util.List;

public record RawOrder(
    String orderId,
    List<RawOrderItem> items
) {}

public record RawOrderItem(
    String sku,
    int quantity,
    BigDecimal unitPrice
) {}

public record NormalizedOrder(
    String orderId,
    List<RawOrderItem> items
) {}

public record PriceQuote(
    String orderId,
    BigDecimal total
) {}

public record OrderReceipt(
    String orderId,
    String total
) {}
~~~

In a real project, place each `public record` in its own matching Java file; the block above groups the DTOs so the contract can be read in one place.

Three functions:

~~~java
package demo.composition;

import java.util.function.Function;
import java.math.BigDecimal;
import java.util.Locale;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderFunctions {

    @Bean
    public Function<RawOrder, NormalizedOrder> normalizeOrder() {
        return order -> new NormalizedOrder(
            order.orderId().trim().toUpperCase(Locale.ROOT),
            order.items()
        );
    }

    @Bean
    public Function<NormalizedOrder, PriceQuote> calculatePrice() {
        return order -> {
            var total = order.items().stream()
                .map(item -> item.unitPrice()
                    .multiply(BigDecimal.valueOf(item.quantity())))
                .reduce(BigDecimal.ZERO, BigDecimal::add);

            return new PriceQuote(order.orderId(), total);
        };
    }

    @Bean
    public Function<PriceQuote, OrderReceipt> renderReceipt() {
        return quote -> new OrderReceipt(
            quote.orderId(),
            quote.total().toPlainString()
        );
    }
}
~~~

The example deliberately assigns a distinct type to each stage so ordering bugs stand out clearly. In real applications, each function can inject its own services/repositories; what matters is that input/output signatures reflect the data accurately.

### 3.1. Valid Composition Definition

~~~properties
spring.cloud.function.definition=normalizeOrder|calculatePrice|renderReceipt
~~~

Or using the comma syntax supported by Spring Cloud Function:

~~~properties
spring.cloud.function.definition=normalizeOrder,calculatePrice,renderReceipt
~~~

Both forms describe sequential composition. Using a pipe is usually easier to read because it visually conveys a processing chain.

### 3.2. Wrong Result from Reversed Order

~~~properties
spring.cloud.function.definition=calculatePrice|normalizeOrder|renderReceipt
~~~

After `calculatePrice`, the data type is `PriceQuote`. The next step is `normalizeOrder`, which expects `RawOrder`. This is an incompatibility point.

Unless a converter can turn `PriceQuote` into `RawOrder`, invocation fails at that boundary. Even if a general converter could technically convert them, the pipeline remains semantically broken because a price quote lacks the original line items.

**Do not fix this by arbitrarily mutating DTOs just to make the composition run.** Restore the proper business order or design a meaningful, tested transformation step.

## 4. Type Compatibility Rules Between Two Functions

Given Java functions:

~~~java
Function<A, B> first;
Function<C, D> second;
~~~

Direct composition via `first.andThen(second)` requires that output `B` can be passed to input `C`. The simplest case is:

~~~text
B == C
~~~

or an output type assignable to the input type under Java's type system rules.

Valid example:

~~~java
Function<RawOrder, NormalizedOrder> normalize = ...;
Function<NormalizedOrder, PriceQuote> calculate = ...;

Function<RawOrder, PriceQuote> pipeline =
    normalize.andThen(calculate);
~~~

Java-invalid example:

~~~java
Function<PriceQuote, NormalizedOrder> wrong =
    calculate.andThen(normalize); // Does not compile.
~~~

`calculate` returns `PriceQuote`, while `normalize` expects `RawOrder`. The Java compiler catches the mismatch immediately at compile time.

### 4.1. Spring Cloud Function Can Convert Between Two Types

Composition via `FunctionCatalog` adds type-conversion capability. According to Spring Cloud Function documentation, content-type negotiation can convert data during composition, allowing functions that cannot be chained directly by Java types to connect when an appropriate converter exists.

That does not mean every type pair is convertible.

Examples:

- A `Function<String, OrderEvent>` returning JSON text can be converted to the type needed by the next step if converters and content type support it.
- A `Function<Map<String,Object>, OrderEvent>` can connect if the map payload has a structure compatible with the DTO and conversion is supported.
- A `Function<PriceQuote, RawOrder>` should not be assumed convertible simply because both are Java objects. If no converter exists or required fields do not exist, the pipeline fails.

### 4.2. Distinguish Types of Compatibility

| Type | Question | Example |
| --- | --- | --- |
| Java compatibility | Can output be passed directly to input? | `NormalizedOrder → NormalizedOrder` |
| Converter compatibility | Does the framework have a converter for payload/type/contentType? | JSON String → `OrderEvent` |
| Business compatibility | Does the data have the right semantics for the next step? | `PriceQuote` cannot replace `RawOrder` if line items are missing |

A composition that happens to run through a converter is **not automatically business-valid**. Check both schema and data semantics.

## 5. How Spring Cloud Function Composes via FunctionCatalog

Spring Cloud Function normalizes user-declared functions into a unified representation inside `FunctionCatalog`. When looked up through the catalog, the returned function can be wrapped to support type conversion, composition, and framework features.

~~~java
FunctionCatalog catalog =
    applicationContext.getBean(FunctionCatalog.class);

Object pipeline =
    catalog.lookup("normalizeOrder|calculatePrice|renderReceipt");
~~~

Generic typed lookup example:

~~~java
Function<?, ?> pipeline =
    (Function<?, ?>) catalog.lookup(
        "normalizeOrder|calculatePrice|renderReceipt"
    );
~~~

In real code, cast to the known input/output types or use wrapper/API signatures appropriate to your SCF version. `FunctionCatalog.lookup` does not replace validating the type contract.

### 5.1. Why Retrieving the Raw Bean Differs from Catalog Lookup

~~~java
Function<RawOrder, NormalizedOrder> original =
    applicationContext.getBean("normalizeOrder", Function.class);

Function<?, ?> wrapped =
    catalog.lookup("normalizeOrder");
~~~

The raw bean is the object as declared. The function retrieved from the catalog is instrumented by the framework and can perform conversion and composition. If you grab the raw bean directly and bypass the wrapper, do not expect SCF's conversion capabilities to apply.

### 5.2. Verify Each Name Before Testing the Full Chain

~~~java
Set<String> names = catalog.getNames(null);

assert names.contains("normalizeOrder");
assert names.contains("calculatePrice");
assert names.contains("renderReceipt");
~~~

If one function is absent from the catalog, composition cannot find that link. Yet even if every name exists, you still must check **ordering and type compatibility**.

### 5.3. Do Not Confuse Lookup Success with Invocation Success

A composition may resolve and look up cleanly while failing only when a real payload passes through converters or business functions. Verify all of:

1. Every individual function name exists.
2. The composition definition is recognized.
3. The first function receives the expected input.
4. Each step's output suits the next step.
5. The final result has the expected type/format.
6. Side effects happen strictly once as designed.

## 6. Wrong Order: Signs and Fixes

A pipeline can be misordered in multiple ways:

| Mistake | Example | Consequence |
| --- | --- | --- |
| Validation before normalization | Validating untrimmed raw input | Valid data rejected or rules skipped |
| Persistence before enrichment | Saving order before attaching tenant/audit metadata | Stored record lacks metadata |
| Rendering before pricing | Building receipt without a quote | Missing total |
| Serialization before business logic | Turning DTO into JSON too early | Subsequent steps must parse it again |
| Consumer before function | Side effect ends the pipeline | No output left for next step |
| Misplaced retry/deduplication | Retrying after non-idempotent side effect | Duplicate side effects |

### 6.1. Normalize and Validate Example

~~~java
@Bean
Function<String, String> normalizeCode() {
    return value -> value == null ? "" : value.trim().toUpperCase();
}

@Bean
Function<String, Boolean> validateCode() {
    return value -> value.matches("[A-Z]{3}-[0-9]{4}");
}
~~~

Correct composition:

~~~properties
spring.cloud.function.definition=normalizeCode|validateCode
~~~

Input `" abc-1234 "` is normalized to `"ABC-1234"` and then validated.

If reversed:

~~~properties
spring.cloud.function.definition=validateCode|normalizeCode
~~~

the first function returns `Boolean`, while the second expects `String`. That is a type mismatch, not merely a different value.

### 6.2. Two Same-Typed Steps with Broken Logic

~~~java
@Bean
Function<String, String> appendSignature() {
    return value -> value + "-sig";
}

@Bean
Function<String, String> uppercase() {
    return String::toUpperCase;
}
~~~

These two definitions:

~~~properties
spring.cloud.function.definition=appendSignature|uppercase
~~~

and:

~~~properties
spring.cloud.function.definition=uppercase|appendSignature
~~~

are both valid `String → String` pipelines yet produce different casing for the suffix. When no type error occurs, compare **the expected output of each stage**, not just whether the pipeline ran.

## 7. Delimiters: Composition vs. Independent Function Lists

A common source of confusion is using the wrong delimiter in `spring.cloud.function.definition`.

### 7.1. In Spring Cloud Function, Pipe or Comma Denotes Composition

~~~properties
spring.cloud.function.definition=normalizeOrder|calculatePrice
~~~

or:

~~~properties
spring.cloud.function.definition=normalizeOrder,calculatePrice
~~~

This is a single composed definition: output from `normalizeOrder` flows into `calculatePrice`.

### 7.2. In Spring Cloud Stream, Semicolon Selects Multiple Independent Functions

Suppose an application defines two separate handlers:

~~~java
@Bean
Function<String, String> uppercase() {
    return String::toUpperCase;
}

@Bean
Function<String, String> reverse() {
    return value -> new StringBuilder(value).reverse().toString();
}
~~~

Configuration:

~~~properties
spring.cloud.function.definition=uppercase;reverse
~~~

In Spring Cloud Stream, `;` selects two independent functions to bind separately. It does not feed the output of `uppercase` into `reverse`.

### 7.3. Web Adapter Also Uses Independent Export Lists

With the Spring Cloud Function web adapter, `;` can list multiple functions/compositions to export. Example:

~~~properties
spring.cloud.function.definition=normalizeOrder|calculatePrice;renderReceipt
~~~

This configures the `normalizeOrder|calculatePrice` composition alongside the standalone `renderReceipt` function according to web adapter export rules.

| Syntax | Typical meaning |
| --- | --- |
| `a|b` | Sequential composition `a` then `b` |
| `a,b` | Composition separator supported by SCF |
| `a;b` in Stream | Select multiple independent functions to bind |
| `a;b` in web export | List multiple functions/compositions to export |

**Do not interpret delimiters outside the adapter context.** If two functions run on independent bindings, inspect binding names; if you want an in-JVM pipeline, declare a composition.

## 8. Function, Supplier, and Consumer Have Different Composition Rules

Spring Cloud Function supports several combinations beyond pure `Function` chains.

| Combination | Resulting composed type | Meaning |
| --- | --- | --- |
| `Function<I,M>` + `Function<M,O>` | `Function<I,O>` | Transformation chain |
| `Supplier<T>` + `Function<T,R>` | `Supplier<R>` | Source produces `T`, transformed to `R` |
| `Supplier<T>` + `Consumer<T>` | `Runnable` | Source produces `T`, then consumed |
| `Function<I,T>` + `Consumer<T>` | `Consumer<I>` | Accepts `I`, transforms, then consumes `T` |
| `Consumer<T>` + `Function<T,R>` | Not supported as standard composition | `Consumer` produces no output to forward |
| `Consumer<T>` + `Supplier<R>` | Not supported as standard composition | `Consumer` does not feed input to `Supplier` |

### 8.1. Supplier → Function

~~~java
@Bean
Supplier<String> currentStatus() {
    return () -> "pending";
}

@Bean
Function<String, StatusEvent> toStatusEvent() {
    return value -> new StatusEvent(value, Instant.now());
}
~~~

Composition:

~~~properties
spring.cloud.function.definition=currentStatus|toStatusEvent
~~~

Contractually, the result remains `Supplier<StatusEvent>`: each time the source is invoked, its value is generated and passed through the function.

### 8.2. Supplier → Consumer

~~~java
@Bean
Supplier<String> currentStatus() {
    return () -> "pending";
}

@Bean
Consumer<String> publishStatus() {
    return status -> statusPublisher.publish(status);
}
~~~

Composition:

~~~properties
spring.cloud.function.definition=currentStatus|publishStatus
~~~

This is equivalent to a `Runnable` action: it takes no input from callers and returns no output payload.

### 8.3. Function → Consumer

~~~java
@Bean
Function<OrderEvent, NormalizedOrder> normalizeOrder() {
    return order -> normalize(order);
}

@Bean
Consumer<NormalizedOrder> persistOrder() {
    return repository::save;
}
~~~

Composition:

~~~properties
spring.cloud.function.definition=normalizeOrder|persistOrder
~~~

The result is `Consumer<OrderEvent>`: it accepts an order, normalizes it, and saves it; callers do not receive a `NormalizedOrder` output.

### 8.4. Why Cannot a Consumer Sit Mid-Pipeline?

`Consumer<T>` defines `accept(T)` returning `void`. It is a terminal sink consuming data. There is no output `R` to hand to a subsequent function.

If you need to persist data and continue the pipeline, write a `Function<T,T>` or `Function<T,R>` with an explicit output:

~~~java
@Bean
Function<NormalizedOrder, NormalizedOrder> persistAndReturn() {
    return order -> {
        repository.save(order);
        return order;
    };
}
~~~

This expresses the side effect while preserving data for the next step. Ensure the save operation has appropriate idempotency and transaction semantics.

## 9. Java andThen vs. SCF Declarative Composition

The two approaches are related, though not identical.

### 9.1. Java andThen

~~~java
Function<RawOrder, NormalizedOrder> normalize = ...;
Function<NormalizedOrder, PriceQuote> calculate = ...;
Function<PriceQuote, OrderReceipt> render = ...;

Function<RawOrder, OrderReceipt> pipeline =
    normalize.andThen(calculate).andThen(render);
~~~

The Java compiler checks types across steps. If outputs and inputs mismatch, the code fails to compile.

### 9.2. SCF Declarative Composition

~~~properties
spring.cloud.function.definition=normalizeOrder|calculatePrice|renderReceipt
~~~

SCF looks up functions by name in the catalog and constructs a composition wrapper. Beyond ordering, the framework can also perform conversions at step boundaries when content types and type metadata allow.

### 9.3. Why Can Declarative Composition Work Even When Java andThen Does Not Chain Directly?

Example:

~~~java
Function<String, OrderEvent> parseJson = ...;
Function<OrderEvent, OrderReceipt> acceptOrder = ...;
~~~

Java `andThen` requires the first function's output to be assignable to the second function's input. Here both chain directly because `OrderEvent` matches.

Another case:

~~~java
Function<String, String> parseText = ...;
Function<OrderEvent, OrderReceipt> acceptOrder = ...;
~~~

Java cannot directly chain `String` into `OrderEvent`. However, if the `String` output is JSON, content-type metadata is compatible, and SCF has the matching converter, declarative composition can convert between steps.

**Do not treat conversion as a universal guarantee.** If no converter handles that format/target, or content type misdescribes the payload, composition still fails.

## 10. Content-Type Negotiation in Composition

Spring Cloud Function uses two Spring mechanisms to convert data for functions:

- `MessageConverter` when data is passed as a `Message<?>`.
- `ConversionService` when input data is not a `Message`.

For HTTP or messaging requests, adapters typically build a Spring `Message`. The function signature supplies the target type; the `contentType` header helps pick the converter.

Therefore, when composition fails at the boundary between two functions, determine whether payloads pass as `Message` or plain Java objects. For `Message`, check converters and headers; for non-Message, check `ConversionService` and runtime object types.

### 10.1. JSON Between Two Steps

Suppose:

~~~java
@Bean
Function<OrderEvent, String> serializeOrder() {
    return event -> objectMapper.writeValueAsString(event);
}

@Bean
Function<OrderEvent, OrderReceipt> acceptOrder() {
    return event -> process(event);
}
~~~

If the first function returns a JSON `String`, the next step expects `OrderEvent`. For a converter to bridge them, the pipeline needs matching content-type metadata and a JSON converter. If the string is treated as `text/plain`, do not expect SCF to parse it into `OrderEvent`.

A cleaner design is normally **not serializing between internal functions**:

~~~java
Function<OrderEvent, NormalizedOrder>
    .andThen(Function<NormalizedOrder, PriceQuote>)
~~~

Keep typed objects flowing across the pipeline and serialize only at transport boundaries.

### 10.2. Content Type and Argument Type Must Both Align

| Intermediate data | Next step target | What to check |
| --- | --- | --- |
| `OrderEvent` object | `OrderEvent` | Passes directly |
| JSON `String` | `OrderEvent` | `contentType=application/json` and JSON converter |
| JSON `byte[]` | `OrderEvent` | Content type/encoding and converter |
| `Map<String,Object>` | `OrderEvent` | Converter supporting Map → DTO or explicit mapping |
| `PriceQuote` | `RawOrder` | Do not assume a converter or equivalent semantics exist |

### 10.3. Message Headers Can Change Between Steps

A function can accept `Message<T>` and return `Message<R>`. In a composition, check both the payload and headers the next step actually receives.

Do not assume all input headers automatically propagate to outputs. If a downstream step needs a correlation ID or specific content type, pass headers selectively and test.

## 11. Diagnose Step by Step Instead of Staring Only at the Full Definition

When composition fails, check in order:

1. Does every function name exist in the catalog?
2. Does each individual function run properly with its contract input?
3. Does the ordering in the definition match the business workflow?
4. Does step `i`'s output type match step `i+1`'s input type?
5. If not, are a supporting converter and accurate content type present?
6. Is a `Consumer` terminating the pipeline too early?
7. Is a `Supplier` at the start of a chain where callers expect request input?
8. If reactive, are element generics and subscriptions right?
9. Are routing/headers/other definitions overriding the expected composition?
10. Is the running adapter using the expected definition and bindings?

### 11.1. Quick Symptom Table

| Symptom | Suspected cause | First check |
| --- | --- | --- |
| `NoSuchBeanDefinition` or function not found | Typo or unregistered bean | `catalog.getNames(null)` |
| Composition lookup fails to resolve | Wrong component/definition name | Look up each name individually |
| Failure right when invoking step two | Output/input mismatch or converter | Runtime payload type |
| Wrong output without exception | Broken logical order | Invoke each function and compare outputs |
| Pipeline returns no output | `Consumer` at the end or middle | Composed function type |
| `Supplier` runs without taking request input | `Supplier` is a source with no input | Use `Function`/`Consumer` if input is needed |
| Intermediate JSON turns into String/Map | Content type or target type | Message headers and generic signatures |
| Reactive pipeline emits no data | Missing subscription or silent source | `StepVerifier`, adapter lifecycle |
| Only Stream binding fails | Wrong definition/binding name/binder | Startup binding logs |
| Wrong HTTP route | Web export/definition/path | Mappings and effective properties |

## 12. Composition Diagnostic Flowchart

~~~mermaid
flowchart TD
    START["Composition fails or gives wrong output"] --> NAMES{"Is each function in catalog?"}
    NAMES -->|No| REG["Check bean names, scan,\nregistration, and definition"]
    NAMES -->|Yes| ORDER{"Is business order right?"}
    ORDER -->|No| REORDER["Reorder the pipeline"]
    ORDER -->|Yes| TYPES{"Does step output fit next step input?"}
    TYPES -->|Yes| INVOKE["Invoke each step then full composition"]
    TYPES -->|No| CONVERT{"Is a suitable converter available?"}
    CONVERT -->|No| CONTRACT["Fix signatures or add explicit typed mapping"]
    CONVERT -->|Yes| CONTENT["Check contentType,\nMessage headers, and metadata"]
    INVOKE --> REACTIVE{"Reactive signature?"}
    REACTIVE -->|Yes| SUBSCRIBE["Check subscribe,\nelement type, and terminal signal"]
    REACTIVE -->|No| ADAPTER["Check HTTP / Stream /\nserverless adapter"]
    REG --> VERIFY["Re-test each step and full pipeline"]
    REORDER --> VERIFY
    CONTRACT --> VERIFY
    CONTENT --> VERIFY
    SUBSCRIBE --> VERIFY
    ADAPTER --> VERIFY
~~~

## 13. FunctionCatalog and Name Fallback: Avoid Misdiagnosis

When the catalog contains only one functional bean, single-function fallback can return that sole function even for an invalid lookup name. Hence:

~~~java
catalog.lookup("calculatePrce");
~~~

is not sufficient to prove a function named `calculatePrce` exists if only one candidate is present.

Inspect the inventory:

~~~java
Set<String> names = catalog.getNames(null);

boolean exists =
    names.contains("calculatePrice");
~~~

In environments requiring exact names, disable fallback:

~~~properties
spring.cloud.function.single-function-fallback-enabled=false
~~~

### 13.1. A Missing Function Can Be Masked When Only One Candidate Exists

In multi-step compositions, component names should always be verified link by link. Do not infer from a single non-null lookup that an entire composition is valid. Verify **each name**, then verify the full composition.

### 13.2. Read the Runtime Definition

~~~java
String definition = environment.getProperty(
    "spring.cloud.function.definition",
    "<unset>"
);

log.info("function.definition={}", definition);
~~~

Properties in local files can be overridden by profiles, environment variables, or command-line arguments. Log the effective value without printing the entire environment containing secrets.

## 14. Wrong Function Kind: Supplier, Function, Consumer

Not every functional bean can be chained in any arbitrary order.

| Interface | Input | Output | Role |
| --- | --- | --- | --- |
| `Supplier<T>` | None | `T` | Generates data |
| `Function<I,O>` | `I` | `O` | Transforms data |
| `Consumer<T>` | `T` | None | Consumes/side effects |

### 14.1. Valid Compositions

~~~text
Supplier<OrderEvent>
    → Function<OrderEvent, NormalizedOrder>
    → Consumer<NormalizedOrder>
~~~

The final contract is equivalent to a `Runnable` since there is neither caller input nor output.

~~~text
Function<RawOrder, NormalizedOrder>
    → Consumer<NormalizedOrder>
~~~

The final contract is equivalent to `Consumer<RawOrder>`.

### 14.2. Invalid Compositions

~~~text
Consumer<NormalizedOrder>
    → Function<NormalizedOrder, PriceQuote>
~~~

`Consumer` does not return `NormalizedOrder`; there is no value for the next function to receive.

~~~text
Consumer<NormalizedOrder>
    → Supplier<PriceQuote>
~~~

Nor does `Consumer` feed input to `Supplier`. This is not a standard sequential composition supported by Spring Cloud Function.

### 14.3. Need Both to Consume and Return Data?

Use `Function` instead of `Consumer`:

~~~java
@Bean
Function<NormalizedOrder, NormalizedOrder> persistOrder() {
    return order -> {
        repository.save(order);
        return order;
    };
}
~~~

If you only want to save and finish, `Consumer` is right. If the next step needs the data, declare an output.

## 15. Reactive Composition: Chain Streams by Element Type

Spring Cloud Function supports Project Reactor reactive APIs. A reactive function is invoked to obtain a publisher; element processing occurs once that publisher is subscribed to.

~~~java
@Bean
Function<Flux<RawOrder>, Flux<NormalizedOrder>> normalizeStream() {
    return orders -> orders.map(order ->
        new NormalizedOrder(
            order.orderId().trim().toUpperCase(),
            order.items()
        )
    );
}

@Bean
Function<Flux<NormalizedOrder>, Flux<PriceQuote>> priceStream() {
    return orders -> orders.map(order ->
        new PriceQuote(order.orderId(), calculateTotal(order.items()))
    );
}
~~~

Composition:

~~~properties
spring.cloud.function.definition=normalizeStream|priceStream
~~~

Here the **element type** `NormalizedOrder` must align, not just the outer `Flux` type.

### 15.1. Wrong Element Generics

~~~java
Function<Flux<Object>, Flux<Object>>
~~~

is not equivalent to:

~~~java
Function<Flux<NormalizedOrder>, Flux<PriceQuote>>
~~~

If registration loses nested generics, converters may not know what object type to construct for each element.

### 15.2. Errors Surface Only on Subscribe

~~~java
Flux<PriceQuote> result =
    priceStream.apply(input);
~~~

If `input` is a cold publisher, the function body may not process items until subscription. Type errors or business exceptions can surface late as `onError`.

Test with `StepVerifier`:

~~~java
StepVerifier.create(
        normalizeStream().andThen(priceStream())
            .apply(Flux.just(
                new RawOrder(" ord-1 ", List.of())
            ))
    )
    .expectNextMatches(quote ->
        quote.orderId().equals("ORD-1")
    )
    .verifyComplete();
~~~

This example tests reactive composition using already-typed POJO inputs. It does not prove HTTP/Kafka bytes convert to `RawOrder`/`NormalizedOrder`; add adapter integration tests for that.

### 15.3. Imperative and Reactive Have Different Invocation Units

For imperative functions, adapters typically invoke the function once per event. For reactive functions, adapters pass a publisher to the function; the pipeline handles multiple events inside the stream.

Imperative and reactive functions can be composed when contracts and adapters support it, but verify payload types, lifecycle, and subscriptions. Do not casually mix `T` and `Flux<T>` expecting composition to guess your intent.

## 16. Message Composition: Payload, Headers, and Content Type

A function can use `Message<T>` when metadata is needed:

~~~java
@Bean
Function<Message<OrderEvent>, Message<NormalizedOrder>> enrichOrder() {
    return message -> MessageBuilder.withPayload(
        normalize(message.getPayload())
    )
    .setHeader(
        "correlationId",
        message.getHeaders().get("correlationId")
    )
    .build();
}
~~~

When chaining to the next function, verify:

- Does the output payload match the next step's input type?
- Is the correlation ID header preserved if needed?
- Does `contentType` still accurately describe the new payload?
- Were any routing headers copied unintentionally?
- Does the adapter convert payloads via the expected converter?

### 16.1. Input Headers Are Not Automatically Propagated Everywhere

Spring Cloud Function does not blindly forward every input header to output in all scenarios. When you need to preserve headers, return a `Message` with selective copying or configure `copy-input-headers` appropriately.

Do not copy headers unchecked: old headers may no longer fit the new payload or may carry routing instructions that should not continue downstream.

### 16.2. Conversion During Composition

SCF documentation explains that content-type negotiation can convert data not only on initial request arrival, but also **between composition stages**. Converters require matching target types and content types.

If step A outputs a JSON `String` while step B expects `OrderEvent`, verify `contentType` and converters. Internally, passing typed POJOs along the pipeline and serializing only at transport boundaries is usually cleaner.

## 17. Function Routing Can Override the Expected Composition Chain

Spring Cloud Function registers `functionRouter` in the catalog. Routing instructions can come from application properties or message headers, depending on function type and adapter mechanisms.

Header example:

~~~text
spring.cloud.function.definition=normalizeOrder|calculatePrice
~~~

A request or message can select a function or composition via routing instructions. If the system has a routing callback, header, or property override, the actual function executed may differ from the definition the developer sees in a config file.

### 17.1. Routing Precedence

Per current SCF documentation, when multiple mechanisms supply routing instructions, precedence follows:

1. `MessageRoutingCallback` for imperative functions.
2. Message headers if imperative and no callback is present.
3. Application properties.

For reactive functions, routing applies to **the entire stream** via application properties rather than routing individual messages via headers.

### 17.2. Verify the Actual Target

- Effective `spring.cloud.function.definition` value.
- Actual routing headers arriving at the function.
- Whether a `MessageRoutingCallback` is registered.
- Whether the target function and composition exist in the catalog.
- Whether the target's input type matches the payload.
- Whether untrusted clients can control routing instructions.

Misrouting can look like misordered composition because the executed pipeline is not the one the developer expected.

### 17.3. Never Let Callers Arbitrarily Choose Internal Functions

If HTTP headers or message brokers permit selecting compositions, enforce role/capability allowlists and secure the endpoints/brokers. Do not place untrusted dynamic expressions into routing configuration. Audit the selected target without logging sensitive data.

## 18. Spring Cloud Stream: Composition and Binding Names

Spring Cloud Stream uses Spring Cloud Function as its programming model. When selecting a composition:

~~~properties
spring.cloud.function.definition=normalizeOrder|calculatePrice
~~~

the adapter creates bindings for **the composition** following Stream's binding naming rules, rather than treating the two functions as separate consumers.

If you want to bind two separate functions:

~~~properties
spring.cloud.function.definition=normalizeOrder;calculatePrice
~~~

then each function gets its own input/output bindings. In Stream, `;` denotes a list of independent functions.

### 18.1. Do Not Confuse Binding Names with Function Names

For example, with function `normalizeOrder`:

~~~text
normalizeOrder-in-0
normalizeOrder-out-0
~~~

Those are binding names, whereas `normalizeOrder` is the function name in the catalog. For compositions, binding names derive from the definition/composition and Stream naming conventions.

### 18.2. Inspect Across Three Layers

| Layer | What to verify |
| --- | --- |
| Catalog | Are component function names right? |
| Definition | Does pipe/comma express the right composition order? |
| Binding/broker | Are input/output bindings, destinations, and binders right? |

If functions run fine when invoked directly yet Stream receives no messages, the bug may lie in bindings/destinations rather than composition typing.

### 18.3. Message Conversion and Native Decoding

If Stream receives payloads through a native deserializer, the runtime type may already be a `Map` or bytes before the function wrapper converts it. Check content types, generic signatures, and `useNativeDecoding`. Do not assume composition will fix arbitrary broker types on its own.

## 19. HTTP and Serverless: Same Composition, Different Entry Points

### 19.1. HTTP Adapter

The web adapter can export either a single function or a composition as an endpoint. Example definition:

~~~properties
spring.cloud.function.definition=normalizeOrder|calculatePrice|renderReceipt
~~~

Requests to the exported route pass through the adapter, message conversion, composition wrapper, and business steps. If failures appear only over HTTP:

- Check the actual route and effective definition.
- Check the HTTP `Content-Type`.
- Check the payload type at the first function.
- Verify each step's output.
- Check security and routing headers.

HTTP 404 does not prove composition types are wrong; the route may simply not be exported.

### 19.2. Serverless Adapter

In serverless, the handler receives an event and selects a business function or composition. Distinguish:

- Platform handler / entry point.
- Function or composition name in `FunctionCatalog`.
- Event envelope vs. business payload.
- Runtime property selecting the function.
- Retries/timeouts and per-step side effects.

An event may be an envelope containing `body` instead of `RawOrder` directly. If the first function in the composition expects `RawOrder`, the adapter must supply the proper payload.

### 19.3. Do Not Alter Composition Order to Compensate for a Wrong Event Envelope

If an adapter passes the entire event envelope while the first function expects a business DTO, fix the event mapping/adapter or add an explicit typed unwrapping step. Reordering functions cannot fix an input schema mismatch.

## 20. Common Errors and Reading Stack Traces

| Exception/symptom | Possible cause | Evidence |
| --- | --- | --- |
| Function not found | Wrong component name / unregistered bean | `catalog.getNames(null)` |
| `ClassCastException` | Previous output does not match next input | Runtime payload class |
| `MessageConversionException` | Converter cannot bridge two types | Content type, generic type, converter |
| `IllegalArgumentException` in business code | Right type, invalid field values | Per-step inputs/outputs |
| Null output | A step returned null or terminal semantics | Per-step trace |
| No output after `Consumer` | `Consumer` is terminal | Composition signature |
| Reactive `onError` on subscribe | Error inside stream | `StepVerifier` and operator stack |
| HTTP 404 | Route/definition not exported | Web mappings |
| Stream creates no bindings | Wrong definition/list/binding config | Startup logs |
| Wrong result without error | Wrong business order | Expected vs. actual per step |

### 20.1. Log at Step Boundaries

You can add temporary boundary logging inside functions:

~~~java
@Bean
Function<RawOrder, NormalizedOrder> normalizeOrder() {
    return order -> {
        log.debug("normalize input orderId={}", order.orderId());
        NormalizedOrder result = normalize(order);
        log.debug("normalize output orderId={}", result.orderId());
        return result;
    };
}
~~~

In production, never log entire payloads containing customer PII, payment details, or secrets. Prefer correlation IDs, function names, payload types, durations, and statuses.

### 20.2. Pinpoint the First Failing Step

If logs show:

~~~text
normalizeOrder: completed
calculatePrice: failed
renderReceipt: not invoked
~~~

focus on `normalizeOrder`'s output and `calculatePrice`'s input. Do not touch `renderReceipt` since it was never even called.

## 21. Test Each Function First, Then Test the Composition

Use JUnit 5 and AssertJ. Functions can be extracted into classes/services for independent unit testing; simple example:

~~~java
class OrderPipelineTest {

    private final Function<RawOrder, NormalizedOrder> normalize =
        order -> new NormalizedOrder(
            order.orderId().trim().toUpperCase(),
            order.items()
        );

    private final Function<NormalizedOrder, PriceQuote> calculate =
        order -> new PriceQuote(
            order.orderId(),
            order.items().stream()
                .map(item -> item.unitPrice()
                    .multiply(BigDecimal.valueOf(item.quantity())))
                .reduce(BigDecimal.ZERO, BigDecimal::add)
        );

    private final Function<PriceQuote, OrderReceipt> render =
        quote -> new OrderReceipt(
            quote.orderId(),
            quote.total().toPlainString()
        );

    @Test
    void eachStageHasExpectedContract() {
        RawOrder raw = sampleOrder();

        NormalizedOrder normalized = normalize.apply(raw);
        assertThat(normalized.orderId()).isEqualTo("ORD-101");

        PriceQuote quote = calculate.apply(normalized);
        assertThat(quote.orderId()).isEqualTo("ORD-101");

        OrderReceipt receipt = render.apply(quote);
        assertThat(receipt.total()).isNotBlank();
    }

    @Test
    void compositionRunsInTheExpectedOrder() {
        Function<RawOrder, OrderReceipt> pipeline =
            normalize.andThen(calculate).andThen(render);

        OrderReceipt result = pipeline.apply(sampleOrder());

        assertThat(result.orderId()).isEqualTo("ORD-101");
    }
}
~~~

Helper `sampleOrder()` and imports for DTOs/`BigDecimal`/AssertJ/JUnit go in the real test class. This shows how plain Java unit tests verify type safety before testing SCF's catalog.

### 21.1. Misordered Test Fails to Compile

~~~java
// Does not compile: calculate returns PriceQuote,
// while normalize expects RawOrder.
var invalid = calculate.andThen(normalize);
~~~

This is an advantage of Java generic composition: many ordering bugs fail at compile time. Declarative SCF composition also involves a conversion layer, so runtime tests remain necessary.

## 22. Test Composition via FunctionCatalog

An integration test can use the Spring configuration itself:

~~~java
@SpringBootTest(classes = OrderApplication.class)
class CatalogCompositionTest {

    @Autowired
    FunctionCatalog catalog;

    @Test
    void expectedCompositionWorks() {
        assertThat(catalog.getNames(null))
            .contains(
                "normalizeOrder",
                "calculatePrice",
                "renderReceipt"
            );

        Function<?, ?> pipeline =
            catalog.lookup(
                "normalizeOrder|calculatePrice|renderReceipt"
            );

        assertThat(pipeline).isNotNull();

        Object result = ((Function) pipeline).apply(sampleOrder());

        assertThat(result).isInstanceOf(OrderReceipt.class);
        assertThat(((OrderReceipt) result).orderId())
            .isEqualTo("ORD-101");
    }
}
~~~

This assumes the beans from section 3 are registered in `OrderApplication` and the test has compatible Spring Boot Test, Spring Cloud Function, JUnit 5, and AssertJ dependencies. Unchecked/raw casts may need suppression depending on version when calling `lookup`.

### 22.1. Testing a Missing Function

~~~java
assertThat(catalog.getNames(null))
    .doesNotContain("calculatePrice");
~~~

Then confirm the composition cannot resolve when a link is genuinely missing. Do not rely solely on `lookup != null` if single-function fallback could return a lone remaining function for a bad name.

### 22.2. Testing the Runtime Definition

~~~java
assertThat(environment.getProperty(
    "spring.cloud.function.definition"
)).isEqualTo(
    "normalizeOrder|calculatePrice|renderReceipt"
);
~~~

Configuration tests catch typos, wrong delimiters, or profile overrides.

## 23. Test Reactive Composition with StepVerifier

Given two reactive functions:

~~~java
import java.math.BigDecimal;
import java.util.Locale;
import java.util.function.Function;
import reactor.core.publisher.Flux;

Function<Flux<RawOrder>, Flux<NormalizedOrder>> normalizeStream =
    orders -> orders.map(order ->
        new NormalizedOrder(
            order.orderId().trim().toUpperCase(Locale.ROOT),
            order.items()
        )
    );

Function<Flux<NormalizedOrder>, Flux<PriceQuote>> calculateStream =
    orders -> orders.map(order ->
        new PriceQuote(
            order.orderId(),
            order.items().stream()
                .map(item -> item.unitPrice()
                    .multiply(BigDecimal.valueOf(item.quantity())))
                .reduce(BigDecimal.ZERO, BigDecimal::add)
        )
    );
~~~

Test:

~~~java
@Test
void reactiveCompositionProducesQuotes() {
    Function<Flux<RawOrder>, Flux<PriceQuote>> pipeline =
        normalizeStream.andThen(calculateStream);

    StepVerifier.create(pipeline.apply(
            Flux.just(sampleOrder())
        ))
        .expectNextMatches(quote ->
            quote.orderId().equals("ORD-101")
        )
        .verifyComplete();
}
~~~

The test must subscribe to the publisher; otherwise a cold pipeline never executes.

### 23.1. Checking Error Paths

~~~java
StepVerifier.create(
        pipeline.apply(Flux.just(invalidOrder()))
    )
    .expectError()
    .verify();
~~~

In real tests, assert the specific exception or business error contract rather than accepting any arbitrary error, which can mask unexpected conversion or logic bugs.

## 24. Adapter Tests: Catalog Tests Alone Are Not Enough

| Test | What it proves |
| --- | --- |
| Per-function unit test | Logic of each stage |
| Java `andThen` test | Generic compatibility and ordering |
| `FunctionCatalog` composition test | SCF lookup/wrapper constructs the pipeline |
| HTTP integration test | Routing, request conversion, and composition |
| Stream test binder / broker test | Bindings, content types, and event flow |
| Serverless handler test | Event envelopes, function selection, and output |
| Production smoke test | Profiles, runtime properties, deployment wiring |

A function may run through `FunctionCatalog` yet lack an exported HTTP route; a composition may pass unit tests yet fail on Stream bindings or destinations. Always test the real deployed adapter.

## 25. Spring Cloud Stream: Testing Independent Functions vs. Composition

To bind two independent functions:

~~~properties
spring.cloud.function.definition=uppercase;reverse
~~~

Spring Cloud Stream creates separate bindings for each function. The test binder can send separate messages to each function's input binding and assert its corresponding output.

To run one pipeline inside the same JVM:

~~~properties
spring.cloud.function.definition=uppercase|reverse
~~~

`uppercase`'s output feeds directly into `reverse`. These are two completely different wiring models.

**Do not test a composition by sending messages to two independent input bindings**; that only tests two standalone functions.

## 26. Special Cases Requiring Extra Attention

### 26.1. Function Returning Null

A step might return `null`. The next step may throw an exception or mishandle `null`. Establish an explicit null contract: reject, default, `Optional`, or error route.

~~~java
@Bean
Function<OrderEvent, NormalizedOrder> normalizeOrder() {
    return order -> {
        if (order == null) {
            throw new IllegalArgumentException("Order is required");
        }
        return normalize(order);
    };
}
~~~

Do not let `null` propagate silently across multiple stages only to cause a hard-to-trace failure later.

### 26.2. Side Effects Before a Later Step Fails

If `persistOrder` runs before `publishEvent` and publishing fails, data is saved while the pipeline remains incomplete. Design appropriate transactions, outbox patterns, or idempotency; composition does not automatically create distributed transactions across steps.

### 26.3. Retrying an Entire Composition Can Duplicate Side Effects

If a pipeline retries from the start after step three fails, earlier steps execute again. Use retries only when operations are idempotent or protected by deduplication. Place retry boundaries intentionally instead of treating composition as an atomic transaction.

### 26.4. Consumer at the End Produces No Output

A composition ending in a `Consumer` is a terminal operation. Callers and adapters should not expect a business payload output as they would from a `Function`.

### 26.5. Supplier Accepts No Request Input

If a pipeline starts with a `Supplier`, it produces data independently of caller input. If the workflow must process HTTP or message payloads, start with a `Function` or `Consumer` depending on whether output is needed.

## 27. Checklist Before Fixing a Composition

1. Record the actual effective definition, including any routing overrides.
2. Verify each function name via `catalog.getNames(null)`.
3. Inspect generic input/output signatures of each bean.
4. Trace the output → input chain in exact order.
5. Invoke each function individually with representative data.
6. Check conversion/`contentType` wherever adjacent types do not match directly.
7. Confirm any `Consumer` sits at the end.
8. Confirm any `Supplier` makes sense with zero caller input.
9. If reactive, verify element types, subscription, and terminal signals.
10. If using Stream, distinguish composition from an independent function list.
11. If using HTTP/serverless, verify routes/handlers and event envelopes.
12. Test side effects, retries, and idempotency.
13. Run both catalog composition tests and adapter integration tests.
14. Log actual target/function names without logging sensitive data.

## 28. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| "`a|b` runs `a` and `b` in parallel." | It is sequential composition: `a` first, then `b`. |
| "`a|b` equals two independent functions." | No; Stream uses `;` for multiple independent functions. |
| "Any two functions in the catalog can be composed." | Outputs/inputs must align or have converter support. |
| "Matching generic types guarantee business order is right." | Same-typed functions can yield wrong semantics if reordered. |
| "Spring Cloud Function never converts between steps." | Content-type negotiation can convert across composition boundaries. |
| "Converters can fix any mismatch." | Only when a converter supports it and data semantics hold. |
| "A `Consumer` can sit in the middle and pass data to a `Function`." | `Consumer` returns `void` and produces no output to forward. |
| "A `Supplier` accepts input like a `Function`." | `Supplier` takes no input. |
| "`Function → Consumer` still returns the `Function`'s output." | The resulting composition is a `Consumer`. |
| "`Supplier → Consumer` returns data." | The result behaves like a `Runnable`. |
| "`Function<Flux<T>,Flux<R>>` processes items on `apply`." | It receives a publisher; processing normally happens on subscribe. |
| "Catalog lookup success means invocation will succeed." | Converters or business logic can still fail. |
| "HTTP 404 proves composition types are wrong." | The route may simply not be exported. |
| "Changing the broker destination fixes wrong function order." | Destinations and compositions are separate layers. |
| "Retrying a composition never duplicates side effects." | Earlier steps can re-execute. |

## 29. Self-Assessment Questions

1. Which Java principle underpins composing two `Function` instances?
2. In `f.andThen(g)`, which function runs first?
3. Given `Function<A,B>` and `Function<C,D>`, what is the simplest compatibility requirement?
4. Why can Spring Cloud Function sometimes compose types that would not chain directly via Java `andThen`?
5. Why can converters never guarantee that every mismatch is valid for business logic?
6. What do `|` and `,` mean in a composition definition?
7. How is `;` used when selecting multiple independent functions in Spring Cloud Stream?
8. Why is `normalizeOrder|calculatePrice|renderReceipt` in the right order?
9. What happens if you reorder it to `calculatePrice|normalizeOrder`?
10. How can two `String → String` functions match in types yet fail logically?
11. What is the resulting type when composing `Supplier<T>` with `Function<T,R>`?
12. What is the resulting type when composing `Supplier<T>` with `Consumer<T>`?
13. Why can you not chain a `Consumer` followed by a `Function` in standard composition?
14. When should you use a `Function` instead of a `Consumer` to keep data flowing to the next step?
15. Why does `FunctionCatalog.lookup` differ from fetching a bean directly from `ApplicationContext`?
16. Why does a successful catalog lookup not guarantee payload conversion is valid?
17. How does the `contentType` header affect conversions between steps?
18. What must be verified for reactive compositions regarding element types and subscriptions?
19. Why can a composition fail only when subscribed to?
20. How can routing callbacks and message headers cause the actual target to differ from a config file's definition?
21. Why do reactive functions not route per message via headers like imperative functions?
22. How do you distinguish composition from multiple independent bindings in Stream?
23. When a composition has side effects, what issues can retrying from the start cause?
24. Which tests would you write to confirm both order and types across a real adapter?

## 30. References

- [Spring Cloud Function — Programming Model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html) — `FunctionCatalog`, declarative composition, `Supplier`/`Function`/`Consumer`, routing, conversion, and reactive functions.
- [Spring Cloud Stream — Producing and Consuming Messages](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html) — selecting one or more functions, binding names, and independent message handlers.
- [Spring Cloud Function — Standalone Web Applications](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/standalone-web-applications.html) — exporting functions/compositions and function lists over HTTP.
- [Java Function.andThen API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/function/Function.html#andThen(java.util.function.Function)) — sequential composition semantics and type contracts.
- [Project Reactor — Testing](https://projectreactor.io/docs/test/release/reference/) — `StepVerifier` for testing reactive compositions and subscription errors.
- [Spring Cloud Function — Function Routing](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html#function-routing) — routing callbacks, message headers, application properties, and precedence.

References align with Spring Cloud Function 5.1.0 and current Spring Cloud Stream documentation at the time of writing. Specific binding, web export, and API behavior may vary across BOMs/versions; check your actual dependencies and run integration tests against your deployed adapter.

**Takeaway:** Function composition is a sequential pipeline: **each step's output must suit the next step's input, and the business order must be right**. Use `|` (or `,` per SCF syntax) for composition; in Spring Cloud Stream, `;` selects multiple independent functions. Java `andThen` catches generic mismatches at compile time, while `FunctionCatalog` composition can leverage converters when content types and target types align. Verify `Supplier`, `Function`, `Consumer`, nested reactive types, and routing individually; finally test both individual stages and the full composition on the real adapter to catch type, ordering, and side-effect bugs.
