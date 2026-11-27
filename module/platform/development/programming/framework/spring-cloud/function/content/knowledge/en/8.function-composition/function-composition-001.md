# Function Composition with Function.andThen and Function.compose

## 1. Learning Objectives

In Spring Cloud Function, business logic can be expressed as small functions that are independent of how they are invoked via HTTP, events, or serverless environments. When a request needs to pass through multiple processing steps, you can **compose functions** into a reusable processing flow.

After this lesson, you will be able to:

- Explain how `java.util.function.Function` represents a step that transforms an input into an output.
- Accurately distinguish the execution order of `andThen` and `compose`.
- Check data type compatibility when chaining `Function` instances.
- Create a business pipeline in Java and understand how Spring Cloud Function composes functions registered in `FunctionCatalog`.
- Choose the appropriate function composition approach while recognizing common mistakes regarding order, type conversion, invalid data, and side effects.

## 2. What Is Function Composition?

Suppose you have two functions:

- `f: A → B` processes data from type `A` to type `B`.
- `g: B → C` processes the result from type `B` to type `C`.

You can create a new function `h: A → C` with the rule:

~~~text
Input A ──f──> Result B ──g──> Result C
h(x) = g(f(x))
~~~

The function `h` can be called like a regular `Function<A, C>`. The caller does not need to invoke `f` and `g` individually.

In Java, the `Function<T, R>` interface in the `java.util.function` package has two default methods for function composition:

- `f.andThen(g)`: runs **f first, then g**.
- `g.compose(f)`: runs **f first, then g**, but the expression is written from the perspective of the function receiving the result (`g`).

Therefore, `f.andThen(g)` and `g.compose(f)` express the same processing order if they take the same functions.

> **Distinguishing the two layers:** `Function.andThen`/`Function.compose` is a Java API. Spring Cloud Function adds `FunctionCatalog` and a mechanism to compose function beans by name, such as `normalizeSku|validateSku`. They serve related purposes, but they are not the same API.

## 3. Using Function.andThen: Reading a Pipeline from Left to Right

Abbreviated signature:

~~~java
<V> Function<T, V> andThen(
    Function<? super R, ? extends V> after
);
~~~

With `Function<T, R> first` and `Function<R, V> second`, the expression `first.andThen(second)` creates a `Function<T, V>`. The `first` step completes, and then its output becomes the input to `second`.

~~~java
import java.util.Locale;
import java.util.function.Function;

public class AndThenExample {
    public static void main(String[] args) {
        Function<String, String> normalize =
                text -> text.trim().toLowerCase(Locale.ROOT);

        Function<String, Integer> countCharacters =
                String::length;

        Function<String, Integer> normalizedLength =
                normalize.andThen(countCharacters);

        int length = normalizedLength.apply("  SPRING  ");
        System.out.println(length); // 6
    }
}
~~~

Execution flow:

1. `normalize.apply("  SPRING  ")` returns `"spring"`.
2. `countCharacters.apply("spring")` returns `6`.
3. `normalizedLength.apply(...)` returns `6`.

When there are multiple steps, you can keep chaining:

~~~java
Function<Integer, Boolean> isLong = length -> length >= 8;

Function<String, Boolean> isLongNormalizedText =
        normalize
            .andThen(countCharacters)
            .andThen(isLong);

System.out.println(isLongNormalizedText.apply("  SPRING CLOUD  ")); // true
~~~

Writing with `andThen` fits business flows described in sequence: normalize → analyze → validate → produce result.

## 4. Using Function.compose: Reading by the Step Executed First

Abbreviated signature:

~~~java
<V> Function<V, R> compose(
    Function<? super V, ? extends T> before
);
~~~

With `g: B → C` and `f: A → B`, `g.compose(f)` means **execute f first, then execute g**. Reading it like the mathematical expression `g(f(x))` makes it easier to remember.

~~~java
import java.util.Locale;
import java.util.function.Function;

public class ComposeExample {
    public static void main(String[] args) {
        Function<String, String> normalize =
                text -> text.trim().toLowerCase(Locale.ROOT);

        Function<String, Integer> countCharacters = String::length;

        Function<String, Integer> normalizedLength =
                countCharacters.compose(normalize);

        System.out.println(normalizedLength.apply("  SPRING  ")); // 6
    }
}
~~~

In the example above:

~~~text
normalize.andThen(countCharacters)
                  is equivalent to
countCharacters.compose(normalize)

Both compute: countCharacters(normalize(input))
~~~

A formula to remember:

| Expression | Call order | Result |
|---|---|---|
| `f.andThen(g)` | `f` then `g` | `g(f(x))` |
| `f.compose(g)` | `g` then `f` | `f(g(x))` |
| `g.compose(f)` | `f` then `g` | `g(f(x))` |

### Example Showing That Changing the Order Changes the Result

~~~java
Function<Integer, Integer> addOne = n -> n + 1;
Function<Integer, Integer> doubleIt = n -> n * 2;

System.out.println(addOne.andThen(doubleIt).apply(3)); // (3 + 1) * 2 = 8
System.out.println(addOne.compose(doubleIt).apply(3)); // (3 * 2) + 1 = 7
~~~

The two expressions differ because adding one and doubling are **not commutative**. In business logic, changing the order between "validate before normalizing" and "normalize before validating" can also produce different results.

## 5. Data Types Are the Contract Between Steps

A function chain can only be composed when the output type of the previous step is compatible with the input type of the next step.

~~~text
Function<A, B> first
Function<B, C> second
Function<C, D> third

first.andThen(second).andThen(third) : Function<A, D>
third.compose(second).compose(first) : Function<A, D>
~~~

Valid example:

~~~java
Function<String, Integer> parseQuantity = Integer::parseInt;
Function<Integer, Long> toLong = Integer::longValue;

Function<String, Long> pipeline = parseQuantity.andThen(toLong);
System.out.println(pipeline.apply("12")); // 12
~~~

**Type-invalid** example:

~~~java
Function<String, Integer> parseQuantity = Integer::parseInt;
Function<String, Boolean> hasPrefix = text -> text.startsWith("SKU-");

// Does not compile: parseQuantity produces Integer,
// while hasPrefix requires String input.
// Function<String, Boolean> invalid = parseQuantity.andThen(hasPrefix);
~~~

The compiler will catch many type-mismatch composition errors. However, **type compatibility does not mean semantic compatibility**: a `Function<Integer, Integer>` that converts quantity to price can be composed with a function that takes an `Integer` status code, even though that processing chain may not be valid business logic.

The `? super R` and `? extends V` wildcards in the `andThen` signature allow appropriate supertype/subtype usage according to Java generic rules. When starting out, check simply: **the output of the previous step must be usable as the input of the next step**.

## 6. Business Example: From Order Line to Quote

Suppose the system receives the data `"SKU-01,3"`, then parses it into a purchase request, calculates the total, and formats the result. Three independent steps can be chained into a single `Function<String, String>`.

The following example uses Java 17+ `record` syntax; the fixed unit price is for illustration only and is not a real-world pricing rule.

~~~java
import java.util.Locale;
import java.util.function.Function;

public class OrderPipeline {
    record OrderInput(String sku, int quantity) {}
    record Quote(String sku, int quantity, long totalVnd) {}

    public static void main(String[] args) {
        Function<String, OrderInput> parseOrder = raw -> {
            String[] parts = raw.split(",");
            if (parts.length != 2) {
                throw new IllegalArgumentException("Format: SKU,quantity");
            }

            String sku = parts[0].trim().toUpperCase(Locale.ROOT);
            int quantity = Integer.parseInt(parts[1].trim());
            if (sku.isEmpty() || quantity <= 0) {
                throw new IllegalArgumentException("Invalid SKU/quantity");
            }

            return new OrderInput(sku, quantity);
        };

        Function<OrderInput, Quote> calculateQuote = order -> {
            long unitPriceVnd = 125_000L;
            long totalVnd = Math.multiplyExact(
                    order.quantity(), unitPriceVnd
            );
            return new Quote(order.sku(), order.quantity(), totalVnd);
        };

        Function<Quote, String> formatQuote = quote ->
                quote.sku() + " x " + quote.quantity()
                + " = " + quote.totalVnd() + " VND";

        Function<String, String> createQuote =
                parseOrder
                    .andThen(calculateQuote)
                    .andThen(formatQuote);

        System.out.println(createQuote.apply(" sku-01 , 3"));
        // SKU-01 x 3 = 375000 VND
    }
}
~~~

Processing diagram:

~~~text
" sku-01 , 3"
      │
      ▼
parseOrder: String → OrderInput
      │  OrderInput("SKU-01", 3)
      ▼
calculateQuote: OrderInput → Quote
      │  Quote("SKU-01", 3, 375000)
      ▼
formatQuote: Quote → String
      │
      ▼
"SKU-01 x 3 = 375000 VND"
~~~

Each function has a single responsibility. `parseOrder` can be used in another workflow; `calculateQuote` can be tested with `OrderInput` without mocking HTTP. When the invocation mechanism changes from REST to events, the quoting logic can still be reused.

Equivalent with `compose`:

~~~java
Function<String, String> createQuoteWithCompose =
        formatQuote
            .compose(calculateQuote)
            .compose(parseOrder);
~~~

Here, writing with `compose` starts from the final step (`formatQuote`) and declares the steps that must run earlier in reverse order.

## 7. Composing Function Beans in Spring Cloud Function

Spring Cloud Function provides `FunctionCatalog` to look up functions registered by the application. If you declare functions as `@Bean`, the catalog can create a pipeline from **function names**, using the `|` symbol to describe the execution order.

Example of a Spring Boot application with two function beans:

~~~java
import java.util.Locale;
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ProductFunctions {

    @Bean
    public Function<String, String> normalizeSku() {
        return raw -> raw.trim().toUpperCase(Locale.ROOT);
    }

    @Bean
    public Function<String, Boolean> validateSku() {
        return sku -> sku.matches("SKU-[0-9]+");
    }
}
~~~

At this point:

- `normalizeSku` takes `String` and returns `String`.
- `validateSku` takes `String` and returns `Boolean`.
- `normalizeSku|validateSku` takes `String` and returns `Boolean`.

You can look up the pipeline directly from the catalog (when the application has started and Spring Cloud Function is on the classpath):

~~~java
import java.util.function.Function;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;
import org.springframework.cloud.function.context.FunctionCatalog;

@Component
public class CatalogExample implements ApplicationRunner {
    private final FunctionCatalog catalog;

    public CatalogExample(FunctionCatalog catalog) {
        this.catalog = catalog;
    }

    @Override
    public void run(ApplicationArguments args) {
        Function<String, Boolean> checkSku =
                catalog.lookup("normalizeSku|validateSku");

        if (checkSku == null) {
            throw new IllegalStateException("Function pipeline not found");
        }

        System.out.println(checkSku.apply(" sku-42 ")); // true
        System.out.println(checkSku.apply(" abc "));    // false
    }
}
~~~

The catalog expression `normalizeSku|validateSku` has the same **semantic order** as Java's `normalizeSku.andThen(validateSku)`. However, the catalog is also responsible for looking up and supplying functions to Spring Cloud Function adapters; it is not the `andThen` method on a Java object.

You can select a default pipeline via configuration:

~~~yaml
spring:
  cloud:
    function:
      definition: "normalizeSku|validateSku"
~~~

The `spring.cloud.function.definition` property declares the function chain that the integration environment will select. When using Spring Cloud Function Web, Spring Cloud Stream, or a serverless adapter, how inputs are fed in and outputs are published depends on the installed adapter; **this configuration alone does not create an HTTP endpoint or a message broker connection**.

| Criterion | `Function.andThen` / `Function.compose` | `FunctionCatalog` and `|` |
|---|---|---|
| Where defined | Java `Function` object | Functions registered in Spring |
| How composed | Method call on function object | Composed by name, e.g., `"normalizeSku|validateSku"` |
| Type checking | Primarily at compile time | Involves lookup, function types, and conversion at runtime |
| Usage | In plain Java code or Spring | When integrating with Spring Cloud Function and adapters |
| Reusability | Creates a new `Function`, which can be registered as a bean | Selects a combination from existing function beans |

### When Should You Use Which?

Use `andThen` when you are implementing a pipeline inside Java, want to express processing steps in forward order, and want to leverage compile-time type checking. Use `compose` when you want to read the pipeline like a mathematical function from the outside in, or add a preprocessing step to an existing function.

Use composition by name via `FunctionCatalog` when the functions are already registered in Spring and you want to choose the composition order through configuration or lookup by name. This aligns with the goal of Spring Cloud Function: the same logic can be invoked across many different environments.

## 8. Limitations and Common Pitfalls to Watch Out For

### 8.1. Composing in the Wrong Order

~~~java
Function<String, String> trim = String::trim;
Function<String, Boolean> isExactSku = "SKU-01"::equals;

System.out.println(trim.andThen(isExactSku).apply(" SKU-01 ")); // true
~~~

If you check `isExactSku` before `trim`, input containing whitespace will not be recognized. Write down the order clearly as steps and test at least one input where reversing the order changes the result.

### 8.2. Type-Valid but Invalid Data

`Integer.parseInt("abc")` throws `NumberFormatException` even though the `String → Integer` chain has completely valid types. Similarly, a function may throw an exception when encountering `null`, out-of-range values, or missing required fields.

An exception thrown in an earlier step normally halts the composed chain; subsequent steps are not called. If structured error responses are needed, design a result model such as `Result<T>`/`Either<L, R>` or handle and map exceptions at the application boundary. Avoid silently swallowing errors inside every function.

### 8.3. Confusing Function with Consumer or Supplier

`Function<T, R>` has both `andThen` and `compose`. `Consumer<T>` has its own `andThen` for chaining operations that do not return a value, but **does not have `compose`** like `Function`. `Supplier<T>` has neither of these methods in the standard Java interface.

Spring Cloud Function has mechanisms for composing different function shapes in supported cases, but the `Function<A, B> → Function<B, C>` example is the clearest starting point for learning `andThen`/`compose`.

### 8.4. Side Effects, Performance, and State

Function composition does not automatically create parallel execution or retry mechanisms. By default, `andThen`/`compose` invokes the functions sequentially when `apply` is executed. If a step calls a database, writes logs, or updates shared state, the order and number of invocations can affect the outcome.

Prefer clear data-transformation functions and avoid shared mutable state. For steps involving I/O, design timeouts, retries, and error handling at the appropriate layer; do not assume that function composition will manage them automatically.

### 8.5. Reactive Functions Must Have Matching Type Contracts

If you are using Reactor, a pipeline might consist of `Function<Flux<A>, Flux<B>>` and `Function<Flux<B>, Flux<C>>`; those two Java objects can still be composed with `andThen` if their types are compatible. However, a `Function<A, B>` does not automatically become a `Function<Flux<A>, Flux<B>>` just because both process data `A` and `B`. How Spring Cloud Function processes, recognizes, and converts between imperative and reactive forms must follow the contract of the framework and adapter in use.

### 8.6. Differences Between Plain Java Execution and Invocation via an Adapter

The Java example `checkSku.apply(" sku-42 ")` passes a string directly. When exposing the pipeline over HTTP or an event channel, the adapter must also read the payload, convert types, handle headers/messages, and serialize the result. Matching Java types is not enough to guarantee that the external payload is formatted properly. Additional testing at the adapter boundary is recommended for production deployments.

## 9. Testing Function Composition Chains

Each step should have its own unit tests; in addition, there should be an end-to-end pipeline test to verify the correct order and output.

Spring-independent JUnit 5 example:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.function.Function;
import org.junit.jupiter.api.Test;

class FunctionCompositionTest {

    @Test
    void andThenRunsLeftToRight() {
        Function<Integer, Integer> addOne = n -> n + 1;
        Function<Integer, Integer> doubleIt = n -> n * 2;

        assertEquals(8, addOne.andThen(doubleIt).apply(3));
        assertEquals(7, addOne.compose(doubleIt).apply(3));
    }

    @Test
    void exceptionFromFirstStepStopsPipeline() {
        Function<String, Integer> parse = Integer::parseInt;
        Function<Integer, Integer> doubleIt = n -> n * 2;

        Function<String, Integer> pipeline = parse.andThen(doubleIt);

        assertEquals(24, pipeline.apply("12"));
        assertThrows(NumberFormatException.class,
                () -> pipeline.apply("invalid"));
    }
}
~~~

For `FunctionCatalog`, you should have an integration test that starts the Spring context, retrieves `catalog.lookup("normalizeSku|validateSku")`, and verifies that the pipeline can be looked up and executed properly. When deploying via HTTP or events, also test real input/output data through that adapter.

## 10. Self-Practice

1. Given `trim: String → String`, `toUpper: String → String`, and `length: String → Integer`, write one `andThen` expression and one `compose` expression that both return the length of the string after trimming leading/trailing whitespace and converting to uppercase.
2. Given `addTax: Long → Long` and `formatMoney: Long → String`, explain why `formatMoney.andThen(addTax)` does not compile.
3. Create the beans `trimInput`, `parseNumber`, and `doubleNumber`. Write the appropriate name string for use in `FunctionCatalog`; check the result for the input `" 21 "`.
4. Try reversing the order of SKU normalization and validation in the Spring Cloud Function example. Give an input that causes the result to differ, and explain why.

Hint for question 1: the desired order is `trim → toUpper → length`. Question 3 uses the string `"trimInput|parseNumber|doubleNumber"`, with compatible output/input contracts between each pair.

## 11. Key Takeaways

- `f.andThen(g)` runs `f` then `g` and returns `g(f(x))`.
- `f.compose(g)` runs `g` then `f` and returns `f(g(x))`.
- `f.andThen(g)` is equivalent to `g.compose(f)` in terms of execution order.
- The output of the previous step must be compatible with the input of the next step; type checking is only the first step, and you must also verify business semantics and error data.
- Spring Cloud Function uses `FunctionCatalog` and name strings like `"normalizeSku|validateSku"` to compose registered functions; HTTP, event, and serverless adapters determine how the pipeline is invoked externally.
