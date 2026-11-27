# Execution Order and Type Compatibility Between Steps

## 1. Learning Objectives

In Spring Cloud Function, each `Supplier`, `Function`, or `Consumer` can act as a unit of business logic independent of the invocation protocol. Thanks to **composition**, small functions can be combined into a processing flow that is reusable across Java, HTTP, events, or serverless when the application is configured with the appropriate adapter.

For function composition to be correct, two questions must be answered simultaneously:

1. **In what order do the steps run?** Which steps does the input pass through before producing a result?
2. **Can the output of the previous step be used as the input of the next step?** Are the Java types, data structures, and business semantics compatible?

This lesson belongs to the **Function Composition** chapter and focuses on those two conditions. By the end of the lesson, you will be able to:

- Predict the execution order of `andThen`, `compose`, and name chains `A|B|C` in `FunctionCatalog`.
- Read `Function<A, B>` contracts and deduce the overall type of a pipeline.
- Distinguish compile-time Java type checking from runtime composition by name and payload conversion.
- Design multi-step business pipelines, handle invalid data, and preserve reusability.
- Write tests proving **correct order, correct data passed between steps, and halting on error**.

## 2. Execution Order of Composition Operations

Suppose there are three functions:

~~~text
f: A → B
g: B → C
h: C → D
~~~

We want to compute:

~~~text
A --f--> B --g--> C --h--> D
~~~

The final result is `h(g(f(x)))`. In Java, there are two ways to write this with equivalent order:

~~~java
Function<A, D> pipeline1 = f.andThen(g).andThen(h);
Function<A, D> pipeline2 = h.compose(g).compose(f);
~~~

Here, `A`, `B`, `C`, and `D` are conceptual type notations; to turn the snippet into runnable Java code, the corresponding types/functions must be declared.

In Spring Cloud Function, if `f`, `g`, and `h` are names of function beans registered in `FunctionCatalog`, a composition-by-name expression is:

~~~java
catalog.lookup("f|g|h");
~~~

The name chain is also read as **f first, then g, then h last**.

| Expression | Processing order | Formula |
|---|---|---|
| `f.andThen(g)` | `f` → `g` | `g(f(x))` |
| `g.compose(f)` | `f` → `g` | `g(f(x))` |
| `f.andThen(g).andThen(h)` | `f` → `g` → `h` | `h(g(f(x)))` |
| `h.compose(g).compose(f)` | `f` → `g` → `h` | `h(g(f(x)))` |
| `"f|g|h"` | `f` → `g` → `h` | `h(g(f(x)))` |

`andThen` and `compose` are methods on `java.util.function.Function`; the `|` symbol is the syntax for composing functions registered through Spring Cloud Function. They express a similar ordering rule but operate at two different layers.

### 2.1. Illustration with Numeric Results

~~~java
import java.util.function.Function;

Function<Integer, Integer> addTwo = n -> n + 2;
Function<Integer, Integer> multiplyThree = n -> n * 3;

int firstThenSecond =
        addTwo.andThen(multiplyThree).apply(4); // (4 + 2) * 3 = 18

int secondThenFirst =
        multiplyThree.andThen(addTwo).apply(4); // (4 * 3) + 2 = 14
~~~

Both functions have the same signature `Integer → Integer`, so both orders are **type-valid**. Yet `18` differs from `14`: **valid types do not guarantee the right business sequence**.

### 2.2. Tracking Order with a Trace

When order is hard to observe, add a list that records called steps in a test example:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Function;

List<String> calls = new ArrayList<>();

Function<String, String> first = text -> {
    calls.add("first");
    return text.trim();
};

Function<String, Integer> second = text -> {
    calls.add("second");
    return text.length();
};

Function<Integer, Integer> third = number -> {
    calls.add("third");
    return number * 2;
};

Function<String, Integer> pipeline =
        first.andThen(second).andThen(third);

int result = pipeline.apply("  abc  ");

System.out.println(result); // 6
System.out.println(calls);  // [first, second, third]
~~~

This is an illustration and testing technique. In production business code, avoid using a mutable `ArrayList` shared across concurrent requests to store pipeline state.

## 3. Type Compatibility: The Condition for Chaining Steps

`Function<T, R>` takes an input of type `T` and returns a result of type `R`:

~~~text
Function<A, B> first
Function<B, C> second
                   |
                   v
first.andThen(second): Function<A, C>
~~~

To chain two steps, **the output type of the previous step must be usable as the input type of the next step**. A basic example:

~~~java
Function<String, Integer> parse = Integer::parseInt;
Function<Integer, Long> calculate = value -> value * 1_000L;

Function<String, Long> pipeline = parse.andThen(calculate);

System.out.println(pipeline.apply("25")); // 25000
~~~

The overall contract of the pipeline is `String → Long`. It is **no longer** `String → Integer` or `Integer → Long`.

### 3.1. Compile-Time Type Errors

~~~java
Function<String, Integer> parse = Integer::parseInt;
Function<String, Boolean> startsWithSku =
        text -> text.startsWith("SKU-");

// Does not compile: parse returns Integer,
// but startsWithSku requires String.
// Function<String, Boolean> invalid = parse.andThen(startsWithSku);
~~~

This is an advantage of composing Java `Function` instances directly: the compiler checks generics and prevents many misconfigurations.

Do not use raw types to bypass the error:

~~~java
// Avoid writing raw types like this:
// Function raw = parse;
// Function unsafe = raw.andThen(startsWithSku);
~~~

Using raw types strips away type information and can push errors to runtime, such as `ClassCastException`.

### 3.2. Compatibility Does Not Require Identical Type Names

Java generics allow passing a subtype instance to a function accepting a supertype, provided the signature permits it. For example:

~~~java
Function<String, Integer> stringLength = String::length;
Function<Number, String> describeNumber =
        number -> "Value: " + number;

Function<String, String> describeLength =
        stringLength.andThen(describeNumber);

System.out.println(describeLength.apply("Java"));
// Value: 4
~~~

`stringLength` returns `Integer`, while `describeNumber` takes `Number`; since `Integer` is a `Number`, Java allows chaining them.

General signature of `andThen`:

~~~java
<V> Function<T, V> andThen(
        Function<? super R, ? extends V> after);
~~~

`? super R` allows the subsequent function to accept an appropriate supertype of `R`. When designing pipelines, still prefer specific, easy-to-understand contracts rather than relying on intricate type variance tricks.

### 3.3. Data Types and Data Semantics Are Two Separate Contracts

Two functions may both take and return `String` while processing completely different kinds of information:

~~~text
fetchCustomerId: String → String     (email → customerId)
validateEmail:   String → Boolean    (email → valid?)
~~~

Even though the expression `fetchCustomerId|validateEmail` has type `String → Boolean`, the second function will validate a **customerId as if it were an email**. The pipeline is still semantically broken.

When needed, use explicit data types:

~~~java
record EmailAddress(String value) {}
record CustomerId(String value) {}
~~~

Then define `Function<EmailAddress, CustomerId>` and `Function<EmailAddress, Boolean>`; the compiler will help catch many nonsensical combinations that plain `String` cannot catch.

## 4. End-to-End Example: Processing an Order Quote

A service receives order data in string form `"SKU-42,2"`, and then sequentially:

1. Parses and validates the input.
2. Calculates the quote.
3. Formats the result for the caller.

Diagram:

~~~text
"SKU-42,2"                (String)
    |
    v
 parseLine                 String → OrderLine
    |
    v
 OrderLine("SKU-42", 2)
    |
    v
 priceOrder                OrderLine → Quote
    |
    v
 Quote("SKU-42", 2, 250000)
    |
    v
 formatQuote               Quote → String
    |
    v
"SKU-42 x 2 = 250000 VND"
~~~

The three steps can be registered as independent `Function` beans. The example uses Java 17 or later and assumes a fixed unit price to demonstrate ordering and type contracts.

~~~java
package example.functions;

import java.util.Locale;
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderFunctions {

    public record OrderLine(String sku, int quantity) {}

    public record Quote(String sku, int quantity, long totalVnd) {}

    @Bean
    public Function<String, OrderLine> parseLine() {
        return raw -> {
            if (raw == null) {
                throw new IllegalArgumentException("Empty order");
            }

            String[] parts = raw.split(",", -1);
            if (parts.length != 2) {
                throw new IllegalArgumentException(
                        "Expected format: SKU,quantity");
            }

            String sku =
                    parts[0].trim().toUpperCase(Locale.ROOT);
            int quantity = Integer.parseInt(parts[1].trim());

            if (!sku.matches("SKU-[0-9]+") || quantity <= 0) {
                throw new IllegalArgumentException(
                        "Invalid SKU or quantity");
            }

            return new OrderLine(sku, quantity);
        };
    }

    @Bean
    public Function<OrderLine, Quote> priceOrder() {
        return order -> {
            long unitPriceVnd = 125_000L;
            long totalVnd =
                    Math.multiplyExact(order.quantity(), unitPriceVnd);
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

The default bean names are `parseLine`, `priceOrder`, and `formatQuote`. Once Spring Cloud Function registers them in `FunctionCatalog`, the pipeline needs the order:

~~~yaml
spring:
  cloud:
    function:
      definition: "parseLine|priceOrder|formatQuote"
~~~

Or retrieve it directly via the catalog in Spring code:

~~~java
import java.util.function.Function;
import org.springframework.cloud.function.context.FunctionCatalog;

// catalog is injected from the Spring context:
Function<String, String> createQuote =
        catalog.lookup("parseLine|priceOrder|formatQuote");

if (createQuote == null) {
    throw new IllegalStateException("Pipeline not found");
}

System.out.println(createQuote.apply("sku-42,2"));
// SKU-42 x 2 = 250000 VND
~~~

This is an example application of Spring Cloud Function, where **business logic is decoupled from the protocol**. With Spring Cloud Function Web, Stream, or a serverless adapter, the application also needs dependencies, endpoint/binding/handler declarations, and environment-appropriate payload conversion.

### 4.1. Why Can't the Order Be Changed Arbitrarily?

The contracts in the example:

| Step | Input | Output |
|---|---|---|
| `parseLine` | `String` | `OrderLine` |
| `priceOrder` | `OrderLine` | `Quote` |
| `formatQuote` | `Quote` | `String` |

The chain `"priceOrder|parseLine|formatQuote"` does not connect matching types: `priceOrder` returns `Quote`, whereas `parseLine` expects `String`. The chain `"parseLine|formatQuote"` is also incompatible because `formatQuote` requires `Quote`, not `OrderLine`.

A configuration yielding an overall type `String → String` is not necessarily right; you must examine **all intermediate types**. This becomes even more important when earlier and later steps all use `String`, because looking only at the start and end types misses broken logic in the middle.

## 5. Type Checking at Compile Time vs. Runtime

Two composition mechanisms should be distinguished:

| Aspect | Direct composition in Java | Composition by name via Spring Cloud Function |
|---|---|---|
| Example | `first.andThen(second)` | `catalog.lookup("first|second")` |
| When the chain is determined | When writing Java code | At lookup/configuration time and application runtime |
| Type checking | Generics provide compile-time checks | Function names and types are resolved at runtime |
| Common errors | Compile error due to generic mismatch | Bean not found, composition failure, type/payload error during execution |
| Data conversion | No arbitrary conversions added automatically | Framework/adapter provides conversion within supported scope |

A declaration like the following **is accepted by the Java compiler** because it only sees the assigned return type:

~~~java
Function<String, String> pipeline =
        catalog.lookup("priceOrder|parseLine");
~~~

That **does not prove** the underlying function beans are compatible. `lookup` is evaluated at runtime; a wrong name or invalid chain can cause lookup or execution to fail. Verify each bean's types and add integration tests with the catalog.

### 5.1. Type Conversion Does Not Replace Business Contracts

Spring Cloud Function supports data conversion mechanisms, including integration with `Message<?>` and payload handling based on type metadata in supported scenarios. However, do not assume the framework will automatically make sense of every pairing:

~~~text
Function<String, Integer> parseQuantity
Function<String, Boolean> validateSku
~~~

A technical conversion from `Integer` to `String` might exist in a conversion ecosystem. Yet converting a **quantity** into a string and validating it as a **SKU code** is still semantically wrong. Add an explicit transformation step with a clear purpose, or redesign the pipeline.

### 5.2. Payload Type Differs from Message Type

A function:

~~~java
Function<String, String> normalize = String::trim;
~~~

does not have the same Java signature as:

~~~java
Function<Message<String>, Message<String>> normalizeMessage;
~~~

because `Message<String>` contains both payload and headers. If a pipeline includes functions handling `Message<T>`, clearly establish the upstream/downstream contracts and conversion behavior of the Spring Cloud Function/adapter version in use.

Do not assume every header is automatically preserved, every JSON payload automatically maps to a POJO, or every `Message<A>` connects seamlessly to `Function<B, C>`. A pipeline that works fine via plain Java `apply` still needs testing with real messages at the adapter boundary.

## 6. Supplier, Function, and Consumer Have Different Positions

Spring Cloud Function supports three basic logic forms:

| Kind | Java contract | Typical role in a flow |
|---|---|---|
| `Supplier<T>` | `() → T` | Produces input data |
| `Function<T, R>` | `T → R` | Transforms data in the middle |
| `Consumer<T>` | `T → void` | Receives results, performs side effects at the end |

Supported compositions depend on each function kind's contract and the framework version. For a one-way data flow, an intuitive model is:

~~~text
Supplier<A> → Function<A, B> → Consumer<B>
  source          transform         sink
~~~

However, `Supplier` and `Consumer` are **not** ordinary `Function<T, R>` objects. `Supplier` has no standard `Function` `andThen`/`compose` methods; `Consumer` has its own `andThen` for chaining two `Consumer` actions, but does not have `compose` like `Function`.

In Spring Cloud Function, the framework supports certain composition forms combining these function kinds. When configuring a chain like `"produce|transform|publish"`, verify the composition capabilities of your framework version and ensure the produce → transform → consume order makes sense. Never assume every ordering of `Supplier`, `Function`, and `Consumer` is valid.

## 7. Ordering When Handling Errors and Special Values

### 7.1. An Exception in an Earlier Step Halts Synchronous Composition

With Java's `Function.andThen`, if an earlier step throws an exception, the next step is not invoked:

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Function;

AtomicInteger calls = new AtomicInteger();

Function<String, Integer> parse = Integer::parseInt;
Function<Integer, Integer> doubleValue = number -> {
    calls.incrementAndGet();
    return number * 2;
};

Function<String, Integer> pipeline = parse.andThen(doubleValue);

try {
    pipeline.apply("not-a-number");
} catch (NumberFormatException expected) {
    System.out.println("Invalid value");
}

System.out.println(calls.get()); // 0
~~~

When calling `apply("not-a-number")`, `parse` throws `NumberFormatException` and `doubleValue` never runs. This is normal behavior for a synchronous Java pipeline.

With Spring Cloud Function, the adapter layer may catch or map exceptions into HTTP responses or message-handling behavior according to configuration. **Function composition does not automatically create retries or error-recovery mechanisms**. Clearly define which layer is responsible for validation, retries, and reporting errors to callers.

### 7.2. Null Can Flow Into the Next Step

~~~java
Function<String, String> sometimesNull =
        value -> value.isBlank() ? null : value;

Function<String, Integer> count = String::length;

Function<String, Integer> pipeline =
        sometimesNull.andThen(count);

// pipeline.apply("") will throw NullPointerException at count.
~~~

`andThen` does not automatically block `null` returned by a function. Design a clear contract for missing data: reject invalid input, return an explicit result type, or use a model such as `Optional` at controlled boundaries. Avoid assuming `null` means an empty result or skipping a step.

### 7.3. Steps with Side Effects Require Attention to Invocation Count

Reading a database, sending messages, or logging inside a step can produce side effects. A pipeline does not automatically guarantee idempotency, transactions, or exactly-once execution. If an adapter performs retries, a step with side effects may execute again according to the adapter's policy.

If you need to emit an event after successful processing, make the order explicit: validate → compute → persist/publish event, and design deduplication mechanisms appropriate for your system.

## 8. Order in Reactive Streams

When processing event streams, Spring Cloud Function can use Reactor, such as `Flux<T>`:

~~~java
import java.util.function.Function;
import reactor.core.publisher.Flux;

Function<Flux<String>, Flux<String>> normalize =
        input -> input.map(String::trim);

Function<Flux<String>, Flux<Integer>> measure =
        input -> input.map(String::length);

Function<Flux<String>, Flux<Integer>> pipeline =
        normalize.andThen(measure);
~~~

Type-wise, the composition looks like:

~~~text
Flux<String> --normalize--> Flux<String>
             --measure---> Flux<Integer>
~~~

However, many Reactor operators like `map` are **lazy**: when calling `pipeline.apply(flux)`, you may only have constructed a reactive pipeline; element processing happens when there is a subscription and corresponding demand.

Therefore, distinguish between:

- **Operator declaration order:** `normalize` before `measure`.
- **When element work actually runs:** depends on subscription, schedulers, and operators.
- **Concurrency/element ordering:** depends on operators such as `map`, `flatMap`, `concatMap`, and scheduler configuration.

Do not assume that `|` automatically runs every step synchronously on one thread, or that the pipeline automatically parallelizes execution. In reactive applications, test both the `Publisher` contract and element ordering if business logic requires preserving order.

A `Function<String, String>` does not automatically become a `Function<Flux<String>, Flux<String>>` under Java generics. How Spring Cloud Function wrappers/adapters bridge imperative and reactive forms must be checked against the specific framework version and integration contract.

## 9. How to Design Verifiable Pipelines

A reliable pipeline should have the following characteristics:

1. **Each step does one clear job.** For example, `parseLine` only parses data, `priceOrder` only calculates quotes, and `formatQuote` only formats output.
2. **Names and types reflect meaning.** Names like `OrderLine` and `Quote` distinguish two concepts that `String` or `Map<String, Object>` easily blur together.
3. **Stable outputs.** Avoid returning different structures per branch from one function if downstream steps have to cast types.
4. **Validate at the right step.** Data is checked before critical calculations or side effects occur.
5. **Consistent error policy.** Decide whether to throw exceptions, return a result type, or translate errors at the adapter; never silently hide exceptions.
6. **Observable flow.** When diagnostics are needed, use tracing/logging with an appropriate correlation ID while avoiding leaking sensitive data.

### Contract Checklist Between Steps

Before adding a function name to `spring.cloud.function.definition`, write a brief table:

| Step | Input type | Output type | Data conditions | Error handling |
|---|---|---|---|---|
| `parseLine` | `String` | `OrderLine` | `SKU-<digits>,quantity > 0` | Throw data error |
| `priceOrder` | `OrderLine` | `Quote` | Valid quantity, no overflow | Throw calculation error |
| `formatQuote` | `Quote` | `String` | Quote available | Return formatted string |

This checklist helps catch mistakes when adding a fourth function, especially when input/output types are all `String` with different meanings.

## 10. Testing Order and Types in Spring Cloud Function

### 10.1. Unit Testing Order in Plain Java

You can verify execution order before bringing functions into Spring:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.ArrayList;
import java.util.List;
import java.util.function.Function;
import org.junit.jupiter.api.Test;

class CompositionOrderTest {

    @Test
    void invokesStepsInDefinedOrder() {
        List<String> trace = new ArrayList<>();

        Function<Integer, Integer> addOne = value -> {
            trace.add("add");
            return value + 1;
        };
        Function<Integer, Integer> doubleValue = value -> {
            trace.add("double");
            return value * 2;
        };

        int actual = addOne.andThen(doubleValue).apply(3);

        assertEquals(8, actual);
        assertEquals(List.of("add", "double"), trace);
    }
}
~~~

With the same input `3`, reversing the order returns `7`. This test catches both **result** and **order** bugs rather than merely confirming the pipeline runs without throwing.

### 10.2. Integration Testing with FunctionCatalog

To test composition by name, you need a Spring context with the `OrderFunctions` beans and Spring Cloud Function registered:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.util.function.Function;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

@SpringBootTest
class OrderCompositionIntegrationTest {

    @Autowired
    private FunctionCatalog catalog;

    @Test
    void catalogBuildsValidOrderPipeline() {
        Function<String, String> createQuote =
                catalog.lookup("parseLine|priceOrder|formatQuote");

        assertNotNull(createQuote);
        assertEquals(
                "SKU-42 x 2 = 250000 VND",
                createQuote.apply("sku-42,2"));
    }
}
~~~

This is an example test inside a Spring Boot application with component scanning and test dependencies properly configured. It helps catch renamed beans, wrong lookup names, or type mismatches at runtime.

### 10.3. Testing the Adapter Boundary

If the same pipeline is exposed over HTTP, events, and serverless, also test:

| Boundary | What to verify |
|---|---|
| HTTP | Input body type, status codes, result/error formatting |
| Events | Binding, serialization, content-type, headers, retry policy |
| Serverless | Event mapping, handler, response structure, error handling |
| Reactive | Publisher types, subscription, element ordering when required |

Catalog tests prove the composition logic inside the Spring context, but do not guarantee every adapter is configured properly.

## 11. Common Errors and How to Identify Them

| Symptom | Possible cause | How to check |
|---|---|---|
| Unexpected result with no error | Steps of the same type are reversed | Log intermediate inputs/outputs and test data that distinguishes the two orders |
| `andThen` code fails to compile | Generics between two steps do not match | Compare output/input signatures pair by pair |
| `lookup` cannot find pipeline | Wrong bean name or function not registered | Check `@Bean`, component scan, and catalog names |
| Composition by name succeeds, invocation fails | Intermediate type, payload, or actual data mismatch | Test `apply` with real inputs; inspect error message and cause |
| Wrong payload type from HTTP/event | Incorrect adapter/serializer/converter | Verify content-type and conversion configuration |
| Downstream function does not run | Upstream threw an error or reactive stream not subscribed | Check logs, upstream errors, and subscriptions |
| Side effects occur repeatedly | Retries or multiple pipeline invocations | Review retry/idempotency policies and adapter behavior |

Do not fix type errors by forcing every step to `Object` or `String`. Doing so obscures data contracts and defers failures to runtime.

## 12. Self-Practice Exercises

**Exercise 1 — Execution Order.** Given:

~~~java
Function<Integer, Integer> increment = n -> n + 1;
Function<Integer, Integer> square = n -> n * n;
~~~

Compute `increment.andThen(square).apply(4)` and `increment.compose(square).apply(4)`. Explain the results using the call order.

**Exercise 2 — Deducing Pipeline Type.** Given `parse: String → Integer`, `toLong: Integer → Long`, and `describe: Number → String`, determine the type of `parse.andThen(toLong).andThen(describe)` and explain why the `Number` parameter type of the final step is compatible.

**Exercise 3 — Finding Contract Mismatches.** Given `readOrder: String → Order`, `validateOrder: Order → ValidationResult`, and `calculateTotal: Order → Receipt`, why does `readOrder|validateOrder|calculateTotal` lack a direct chaining contract? Propose a design when the business logic still needs to calculate the total after validation.

**Exercise 4 — Testing Invalid Data.** Based on the `OrderFunctions` example, describe what happens with inputs `"SKU-42,0"` and `"SKU-42,abc"`. Are `priceOrder` and `formatQuote` called? How would you test this behavior?

**Exercise 5 — Deployment and Integration.** Write `spring.cloud.function.definition` for the three steps `parseLine`, `priceOrder`, and `formatQuote`; then list two additional tests needed when the pipeline is invoked via a message broker instead of direct Java calls.

### Solution Hints

- **Exercise 1:** `increment.andThen(square).apply(4) = 25`; `increment.compose(square).apply(4) = 17`.
- **Exercise 2:** Overall type is `Function<String, String>`; `Long` is a subtype of `Number`.
- **Exercise 3:** `ValidationResult` is not `Order`. You need a conversion step or for the validation result to retain the validated `Order` data so billing can proceed.
- **Exercise 4:** Both inputs fail at `parseLine`; subsequent steps do not run in normal synchronous composition.
- **Exercise 5:** `"parseLine|priceOrder|formatQuote"`. You need to test serialization/content-type and binding/retry behavior in addition to verifying business output.

## 13. Key Takeaways

- Pipeline `A|B|C` executes **A → B → C**; semantically it matches `A.andThen(B).andThen(C)` and `C.compose(B).compose(A)` when type contracts align.
- Two connected steps must have **compatible output/input types** and **matching business semantics**. Checking only the pipeline's initial input and final output types is not enough.
- Java generics help verify `andThen`/`compose` at compile time; composition by name via `FunctionCatalog` must also be verified at runtime.
- Errors in an earlier step can stop later steps from running; message handling, reactive execution, and retries depend on the specific pipeline contract and adapter.
- The goal of Spring Cloud Function is to keep logic reusable across HTTP, events, and serverless. Designing clear step-by-step contracts helps preserve correctness when switching invocation environments.
