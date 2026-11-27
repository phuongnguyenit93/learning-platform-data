# Composing by Name with FunctionCatalog.lookup

## 1. Why Compose Functions by Name?

Spring Cloud Function aims to let you write business logic as **reusable `Supplier`, `Function`, and `Consumer` components**, decoupled from the protocol the system uses to invoke that logic. The same function can participate in an internal processing flow and be connected to an HTTP, event, or serverless adapter when the application is configured appropriately.

In plain Java, you can compose two `Function` instances directly:

~~~java
Function<String, String> normalize = String::trim;
Function<String, Integer> measure = String::length;
Function<String, Integer> pipeline = normalize.andThen(measure);
~~~

However, when a Spring application has many pre-registered functions, you sometimes want to **select and compose them by name** to change the pipeline via configuration or retrieve a combination at runtime. That is the role of `FunctionCatalog`.

This lesson is part of the **Function Composition** chapter and focuses on looking up and composing functions using `FunctionCatalog.lookup(...)`.

After this lesson, you will be able to:

- Describe how Spring Cloud Function discovers, registers, and looks up `Function` beans in `FunctionCatalog`.
- Use `lookup("functionName")` to retrieve a single function and `lookup("funcA|funcB")` to retrieve a function chain.
- Read the execution order accurately, verify output/input type compatibility, and choose suitable bean names.
- Distinguish `lookup` in code from the `spring.cloud.function.definition` property intended for integration environments.
- Handle missing functions, incompatible type contracts, and test pipelines using a Spring context.

## 2. What Is FunctionCatalog?

`FunctionCatalog` is the Spring Cloud Function interface used to look up functions registered by the system. Beans of type `java.util.function.Function`, `Supplier`, and `Consumer` are discovered by Spring Cloud Function and exposed through the catalog according to the framework's registration rules.

Required import:

~~~java
import org.springframework.cloud.function.context.FunctionCatalog;
~~~

Core usage:

~~~java
Function<String, String> one =
        catalog.lookup("normalizeSku");

Function<String, Boolean> composed =
        catalog.lookup("normalizeSku|validateSku");
~~~

In this example, `normalizeSku` and `validateSku` must be function names already registered in the catalog. The `|` symbol indicates execution order **from left to right**:

~~~text
catalog.lookup("normalizeSku|validateSku")

                   Input String
                        |
                        v
                   normalizeSku
                   String → String
                        |
                        v
                    validateSku
                   String → Boolean
                        |
                        v
                  Output Boolean
~~~

In terms of business semantics, the chain above is equivalent to:

~~~java
normalizeSku.andThen(validateSku)
~~~

The main difference is how the function is obtained: `andThen` chains existing `Function` objects in code, whereas `FunctionCatalog.lookup` **resolves registered names** and provides a function or function chain to invoke.

> `FunctionCatalog` belongs to Spring Cloud Function. It is not `ApplicationContext.getBean(...)`: the catalog provides an abstraction layer for lookup, composition, and the framework's type/message adaptation mechanisms. Therefore, an object returned by the catalog may be a wrapper managed by Spring Cloud Function.

## 3. Creating Function Beans with Clear Names

Consider a business case that accepts product codes from multiple sources. Codes may contain whitespace and lowercase letters; the system needs to normalize the code before validating it against the pattern `SKU-<digits>`.

We define two independent functions:

~~~java
package example.functions;

import java.util.Locale;
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class SkuFunctions {

    @Bean
    public Function<String, String> normalizeSku() {
        return value -> value.trim().toUpperCase(Locale.ROOT);
    }

    @Bean
    public Function<String, Boolean> validateSku() {
        return value -> value.matches("SKU-[0-9]+");
    }
}
~~~

Key points to note:

1. `@Bean` adds the functions to the Spring application context. When the project has Spring Cloud Function and appropriate bean scanning configured, the framework registers them in the function catalog.
2. By default, the bean names from the two methods are `normalizeSku` and `validateSku`. These are the names used in `lookup` expressions.
3. `normalizeSku` has the contract `Function<String, String>`; `validateSku` has the contract `Function<String, Boolean>`. Because the output of the first function matches the input of the second, they can be chained.
4. `Locale.ROOT` ensures uppercase normalization is independent of the server's locale. The regular expression in the example only allows codes starting with `SKU-` followed by one or more digits.

If you want a bean name different from the method name, you can specify the name directly:

~~~java
@Bean("skuNormalizer")
public Function<String, String> normalizeSku() {
    return value -> value.trim().toUpperCase(Locale.ROOT);
}
~~~

Then look it up using the registered name `skuNormalizer`:

~~~java
catalog.lookup("skuNormalizer|validateSku");
~~~

Do not assume that a class name, business description, or Java variable name is the name in the catalog. With `@Bean`, always base lookups on the actual bean name registered by Spring.

## 4. Looking Up and Running a Pipeline with lookup

The following example uses `ApplicationRunner` to run a check after the Spring Boot application starts. Assume `SkuFunctions` from section 3 is within the component scan scope and the application has the appropriate Spring Cloud Function dependency.

~~~java
package example.functions;

import java.util.function.Function;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.stereotype.Component;

@Component
public class SkuDemoRunner implements ApplicationRunner {

    private final FunctionCatalog catalog;

    public SkuDemoRunner(FunctionCatalog catalog) {
        this.catalog = catalog;
    }

    @Override
    public void run(ApplicationArguments args) {
        Function<String, Boolean> checkSku =
                catalog.lookup("normalizeSku|validateSku");

        if (checkSku == null) {
            throw new IllegalStateException(
                    "SKU validation pipeline not found");
        }

        System.out.println(checkSku.apply(" sku-42 "));  // true
        System.out.println(checkSku.apply("invalid"));   // false
    }
}
~~~

During the first call:

1. The catalog looks up `normalizeSku` and `validateSku` by name.
2. The catalog creates/retrieves an executable representation of the `normalizeSku|validateSku` chain in accordance with the framework's composition mechanism.
3. When `checkSku.apply(" sku-42 ")` runs, the normalization step returns `"SKU-42"`.
4. The validation step receives `"SKU-42"` and returns `true`.

The `lookup` call **retrieves the function for execution**; actual data processing happens when `apply` is called. Initializing the pipeline may involve checks and wrapper creation depending on how the framework manages the function catalog; do not rely on the assumption that `lookup` always creates a new Java object or always returns the exact original bean instance.

### Looking Up a Single Function

You can retrieve individual functions, which is useful when testing or wanting to run a single step:

~~~java
Function<String, String> normalizer = catalog.lookup("normalizeSku");

if (normalizer == null) {
    throw new IllegalStateException("Missing normalizeSku");
}

System.out.println(normalizer.apply(" sku-07 ")); // SKU-07
~~~

`lookup("normalizeSku")` returns a callable function; `lookup("normalizeSku|validateSku")` returns a transformation chain. **The lookup name is the input describing which function to retrieve**, not the business data input. Actual data is passed via `apply`.

## 5. How to Write Composition-by-Name Expressions

Basic form:

~~~text
"functionName1|functionName2|functionName3"
~~~

Each `|` connects the output of the function on the left to the input of the function on the right. For example, we add a step that extracts the numeric code from a valid SKU string:

~~~java
@Bean
public Function<String, String> trimSku() {
    return String::trim;
}

@Bean
public Function<String, String> uppercaseSku() {
    return value -> value.toUpperCase(Locale.ROOT);
}

@Bean
public Function<String, String> stripPrefix() {
    return value -> value.replaceFirst("^SKU-", "");
}
~~~

Lookup:

~~~java
Function<String, String> getSkuNumber =
        catalog.lookup("trimSku|uppercaseSku|stripPrefix");

System.out.println(getSkuNumber.apply(" sku-123 ")); // 123
~~~

Corresponding processing order:

~~~text
" sku-123 "
   |
   v
trimSku            → "sku-123"
   |
   v
uppercaseSku       → "SKU-123"
   |
   v
stripPrefix        → "123"
~~~

Here, all steps accept and return `String`, so they are easy to compose. However, type compatibility is only a necessary condition: for instance, `stripPrefix` processing a string that does not start with `"SKU-"` still returns a value, which can cause the application to accept invalid codes if a validation step is missing. With real-world data, design validation checks before stripping prefixes or converting to other types.

### Composing Across Different Data Types

Suppose we have:

~~~java
Function<String, Integer> parseAmount = Integer::parseInt;
Function<Integer, Long> calculateTotal = qty -> qty * 125_000L;
~~~

If these functions are registered under their respective names, the chain `"parseAmount|calculateTotal"` has the overall contract `String → Long`.

Conversely, a `Function<String, Integer>` cannot be directly chained to a `Function<Boolean, String>` because `Integer` does not match `Boolean`. In plain Java, `andThen` typically reports a compile-time error when generics are incompatible; name expressions via the catalog are resolved at runtime, so both lookup and function application must be tested.

## 6. How Does lookup Differ from spring.cloud.function.definition?

There are two related but distinct needs:

| Need | Approach | What to remember |
|---|---|---|
| Java code needs a specific function at runtime | `catalog.lookup("normalizeSku")` | Returns a function callable from code |
| Java code needs a composition by name | `catalog.lookup("normalizeSku|validateSku")` | Returns a pipeline, invoked via `apply` |
| Application/adapter needs to select a function to expose or bind | `spring.cloud.function.definition` | Declares the selected function name or chain in configuration |
| Code already holds `Function` objects to compose directly | `first.andThen(second)` | Java API, no bean lookup by name needed |

Example configuration in `application.yml`:

~~~yaml
spring:
  cloud:
    function:
      definition: "normalizeSku|validateSku"
~~~

The `spring.cloud.function.definition` property lets an adapter or Spring Cloud Function integration select the declared function composition. It **does not execute business logic on its own** and does not automatically create HTTP endpoints or event bindings. To receive real requests or messages, the application must have the corresponding adapter and setup, such as integrating Spring Cloud Function Web or Spring Cloud Stream.

If the code **already** calls `catalog.lookup("normalizeSku|validateSku")`, that call requests the pipeline explicitly by name without needing to change the property above. Conversely, changing `spring.cloud.function.definition` does not mean every `lookup("otherName")` call in code will automatically switch to the new name.

When there are multiple function beans, choose specific names to avoid confusion. Do not rely on the assumption that "there is only one function so the framework will automatically pick the right one" when building examples or applications that need to work reliably across environments.

## 7. FunctionCatalog in the Protocol-Independent Model

The catalog itself handles **selecting and connecting logic**, not transport decisions. Adapters handle how inputs are fed in and results are published. You can visualize it as:

~~~text
                     Pipeline name
               "normalizeSku|validateSku"
                            |
                            v
                       FunctionCatalog
                            |
                            v
                       Composed Function
                       String → Boolean
                            ^
                            |
             +--------------+--------------+
             |              |              |
          HTTP Web        Event       Serverless
          adapter        adapter        adapter
             |              |              |
        HTTP payload   Message/payload  Event payload
~~~

This is a conceptual diagram; it does not imply that a single application automatically includes all three adapters. Implementation requires the appropriate dependencies, configuration, and data mapping mechanisms for each adapter.

When using messages (`Message<T>`), metadata such as headers and payload types must also be considered. Spring Cloud Function can adapt and convert messages based on type information and configuration, but do not assume every composition preserves headers or converts JSON arbitrarily. For event-processing pipelines, test with the actual data types provided by the adapter.

### A Maintainable Way to Organize Functions

Organize steps by independent responsibilities:

- `normalizeSku`: normalizes characters and whitespace.
- `validateSku`: validates format.
- `enrichSku`: enriches data when needed and when type contracts match.
- `publishResult`: sends results to another system (if the pipeline design permits steps with side effects).

Function names should be stable, readable, and non-overlapping. Pipelines composed by name work best when each step's inputs, outputs, and errors are explicitly defined.

## 8. Error Handling When Looking Up and Composing Functions

### 8.1. Registered Name Not Found

~~~java
Function<String, Boolean> pipeline =
        catalog.lookup("normalizeSku|unknownStep");

if (pipeline == null) {
    throw new IllegalArgumentException(
            "Pipeline is not registered");
}
~~~

Depending on the version and scenario, composition errors may be detected at `lookup` time or at execution time. Therefore, a `null` check is only the first line of defense; do not treat it as the sole way to catch every misconfiguration. When an error occurs, check the actual bean names, component scan scope, Spring Cloud Function dependencies, and startup logs.

### 8.2. Incompatible Output/Input Types

Suppose `loadOrder` returns `Order`, while `verifyToken` expects `String`. The expression `"loadOrder|verifyToken"` does not have a matching direct chaining contract even though both functions may exist in the catalog.

The solution is to design a semantically meaningful conversion step, such as `extractToken: Order → String`, and then compose `"loadOrder|extractToken|verifyToken"`; or change the function contract if the output truly needs to remain `Order`.

Do not insert arbitrary conversions to `String` just to bypass type errors, as this hides underlying data design issues.

### 8.3. Type-Valid Data with Invalid Content

~~~java
Function<String, Integer> parseQuantity = Integer::parseInt;
~~~

The string `"abc"` is still a `String`, yet `parseQuantity.apply("abc")` throws `NumberFormatException`. The catalog does not automatically interpret this as a business error or build a friendly JSON error response. You must clearly define which layer is responsible for validation, exception mapping, and the application's retry policy.

### 8.4. Missing Data Validation and Side Effects

If a step sends an email, writes to a database, or emits an event, each call to `apply` can produce side effects. Composing functions by name does not automatically provide transactions, idempotency, retries, timeouts, or parallel execution. These mechanisms must be designed separately when using adapters or integrating with external systems.

### 8.5. Pipeline Name Taken Directly from the Caller

Do not allow an external client to send an arbitrary string and pass it directly to `catalog.lookup(userInput)`. Doing so could inadvertently allow invoking functions that the API never intended to expose. If the pipeline needs to vary by context, map valid choices through an **allowlist** at the application layer.

Example:

~~~java
String selected = switch (requestType) {
    case "sku-check" -> "normalizeSku|validateSku";
    case "sku-normalize" -> "normalizeSku";
    default -> throw new IllegalArgumentException("Unsupported request type");
};
~~~

This uses Java 17+ switch syntax to illustrate selecting from a set of approved names. The return type of each pipeline may differ (`Boolean` vs `String`); when sharing a processing flow, design an appropriate result type or branch accordingly rather than forcing both into an incorrect generic type.

## 9. Testing FunctionCatalog.lookup

To test lookup by name, you must start a **Spring application context** containing all the function beans and Spring Cloud Function. Simply instantiating `new SkuFunctions()` does not prove that the catalog registers the names correctly.

JUnit 5 and Spring Boot Test example, placed in the same application that scans `SkuFunctions`:

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.function.Function;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

@SpringBootTest
class SkuCompositionTest {

    @Autowired
    private FunctionCatalog catalog;

    @Test
    void catalogLooksUpNamedComposition() {
        Function<String, Boolean> pipeline =
                catalog.lookup("normalizeSku|validateSku");

        assertNotNull(pipeline);
        assertTrue(pipeline.apply(" sku-42 "));
        assertFalse(pipeline.apply(" invalid "));
    }
}
~~~

The test above requires a valid Spring Boot application class in the test configuration and the appropriate test dependencies. If the returned result has a different type than expected due to an adapter's message conversion, inspect the actual input/output contract before adjusting assertions.

You can add tests across layers:

1. **Unit test each bean:** verify normalization and code validation with valid, empty, whitespace-padded, or malformed inputs.
2. **Catalog integration test:** verify that `lookup` finds the right names and executes in the expected order with the expected output.
3. **Adapter test:** when using HTTP/event/serverless, verify payloads, headers, error formats, and result types at the real boundary.

These tests help catch errors that bypass Java type checking, such as typos in name strings or renaming a bean without updating configuration.

## 10. Distinguishing Easily Confused Concepts

| Concept | Role | Example |
|---|---|---|
| `@Bean` | Registers a function in the Spring context | `normalizeSku()` |
| Bean name | Identifier that the catalog can look up | `"normalizeSku"` |
| `FunctionCatalog` | Lookup portal for registered functions and compositions | `catalog.lookup(...)` |
| Composition string | Describes the order of functions by name | `"normalizeSku|validateSku"` |
| `Function.apply` | Supplies input and executes the pipeline | `pipeline.apply(" sku-42 ")` |
| `spring.cloud.function.definition` | Selects a function/pipeline for integration via configuration | `"normalizeSku|validateSku"` |
| Adapter | Connects logic to HTTP, messaging, or serverless | Spring Cloud Function Web, Stream adapter, or cloud adapter |

Remember the difference between an **identifier string** and a **business value**:

~~~java
// "normalizeSku|validateSku" is how to look up the pipeline.
Function<String, Boolean> pipeline =
        catalog.lookup("normalizeSku|validateSku");

// " sku-42 " is the data that the pipeline processes.
Boolean accepted = pipeline.apply(" sku-42 ");
~~~

## 11. Practice Exercises

### Exercise 1: Quantity Parsing Pipeline

Create three function beans:

- `trimInput: String → String`: trims leading/trailing whitespace.
- `parseQuantity: String → Integer`: converts the string to a number.
- `calculateCost: Integer → Long`: multiplies the quantity by a unit price of `75_000L`.

Write the `lookup` statement to create a `Function<String, Long>` and compute the total cost for the input `" 4 "`. Expected output: `300000L`.

### Exercise 2: Renaming a Bean

Rename the `trimInput` bean to `quantityTrimmer` using `@Bean("quantityTrimmer")` while keeping the Java method name. Then update the composition expression accordingly. Explain why a string containing the old `trimInput` name is no longer reliable.

### Exercise 3: Type-Mismatched Pipeline

Given `parseQuantity: String → Integer` and `isSku: String → Boolean`, determine why `"parseQuantity|isSku"` is invalid. Propose a more suitable next function taking `Integer` to complete a quantity-processing pipeline.

### Exercise 4: Deploying via an Adapter

Configuration `spring.cloud.function.definition` selects `"normalizeSku|validateSku"`. Explain:

1. Does simply adding the property above create an HTTP endpoint?
2. When also using an HTTP adapter, what aspects of the input payload and result type must be tested?
3. Why is it still necessary to test `FunctionCatalog.lookup` directly in an integration test?

**Hint for Exercise 1:**

~~~java
Function<String, Long> totalCost =
        catalog.lookup("trimInput|parseQuantity|calculateCost");

System.out.println(totalCost.apply(" 4 ")); // 300000
~~~

## 12. Key Takeaways

- `FunctionCatalog.lookup("functionName")` retrieves a function registered by Spring Cloud Function by name.
- `FunctionCatalog.lookup("first|second")` composes two functions in the order **first then second**; additional steps continue to be separated by `|`.
- The output of each step must be compatible with the input of the next step, as well as aligned with business semantics.
- `lookup` selects logic callable from Java; `spring.cloud.function.definition` helps adapters/integrations select logic via configuration.
- Composing functions by name is only one part of the system: to run the same logic over HTTP, events, or serverless, you need the corresponding adapter, input/output data handling, and integration tests.
