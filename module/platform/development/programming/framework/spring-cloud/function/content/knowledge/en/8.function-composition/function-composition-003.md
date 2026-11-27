# spring.cloud.function.definition with | or Comma

## 1. Learning Objectives

In Spring Cloud Function, you can build business processing steps using `Supplier`, `Function`, and `Consumer`, and then connect them to HTTP, event-driven systems, or serverless environments using the appropriate adapter. The same function can be reused without tightly coupling business logic to the invocation protocol.

When an application has multiple function beans, the `spring.cloud.function.definition` property specifies **which function or function composition is selected for integration**. Two symbols that are often confused are:

- `|` (pipe): represents **sequential composition**, passing the output of the previous function into the next function.
- `,` (comma): in contexts that support declaring multiple definitions, represents **a list of selected independent functions**, without creating a data flow between them.

This topic is part of the **Function Composition** chapter. After this lesson, you will know how to write the configuration, trace data flow, verify type contracts, distinguish the role of `FunctionCatalog`, and detect errors when deploying through adapters.

> **Scope:** Examples use Java 17, Spring Boot, and Spring Cloud Function. How an adapter actually exposes functions—especially when selecting **multiple** functions—depends on the Spring Cloud Function / Spring Cloud Stream version and starter in use. In Spring Cloud Stream, `;` is commonly used in version documentation to declare multiple definitions; always check your project's version-specific documentation when using `,`.

## 2. What Does spring.cloud.function.definition Do?

Spring Cloud Function detects and registers function beans with `FunctionCatalog`. For example, an application has three beans named `trimText`, `upperText`, and `countChars`. You can select one or more definitions for the adapter/framework via `spring.cloud.function.definition`:

~~~yaml
spring:
  cloud:
    function:
      definition: "trimText"
~~~

This value is a **function definition name**, not the text data that the function will process. It tells the integration layer which function to use. To receive HTTP requests, read events from a broker, or run serverless, the application still needs the appropriate adapter and configuration.

There are three separate questions:

1. **Which functions are registered?** `Function`, `Supplier`, or `Consumer` beans are registered and named in `FunctionCatalog`.
2. **Which function is selected?** The `spring.cloud.function.definition` property indicates the function name, pipeline, or set of definitions to integrate.
3. **How is the function invoked?** The HTTP, messaging, or serverless adapter handles input/output routing, payload conversion, and the trigger mechanism.

Do not assume that simply adding this property causes the application to automatically create an HTTP endpoint or connect to a message broker.

## 3. Preparing Three Function Beans to Observe

The following example declares three transformation steps with clear contracts:

~~~java
package example.functions;

import java.util.Locale;
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class TextFunctions {

    @Bean
    public Function<String, String> trimText() {
        return String::trim;
    }

    @Bean
    public Function<String, String> upperText() {
        return text -> text.toUpperCase(Locale.ROOT);
    }

    @Bean
    public Function<String, Integer> countChars() {
        return String::length;
    }
}
~~~

| Function bean name | Input type | Output type | Meaning |
|---|---|---|---|
| `trimText` | `String` | `String` | Trims leading/trailing whitespace |
| `upperText` | `String` | `String` | Converts to uppercase |
| `countChars` | `String` | `Integer` | Counts UTF-16 characters in the string |

The three functions are independent of HTTP, message brokers, and cloud platforms. They only process Java data. Methods annotated with `@Bean` produce default bean names matching their method names; therefore, the configurations below use `trimText`, `upperText`, and `countChars`.

In a real application, ensure that the configuration class falls within Spring's component scan scope and that the project includes the appropriate Spring Cloud Function dependency.

## 4. The | Symbol: Sequential Composition into a Pipeline

When using `|`, functions are executed **from left to right**. The output of each step becomes the input to the adjacent step.

~~~yaml
spring:
  cloud:
    function:
      definition: "trimText|upperText"
~~~

Diagram:

~~~text
Input "  spring cloud  "
              |
              v
          trimText
              |  "spring cloud"
              v
          upperText
              |  "SPRING CLOUD"
              v
         Output "SPRING CLOUD"
~~~

Equivalent in processing order to Java:

~~~java
Function<String, String> pipeline =
        trimText.andThen(upperText);
~~~

In this Java line, `trimText` and `upperText` are `Function` objects held in variables. In Spring Cloud Function configuration, the two character strings are **registered bean names**. Both approaches express the flow where the output of the previous step enters the next step.

You can compose multiple steps:

~~~yaml
spring:
  cloud:
    function:
      definition: "trimText|upperText|countChars"
~~~

The pipeline above has the overall type `String → Integer`:

~~~text
"  spring cloud  "
         |
         v
      trimText      String → String
         |  "spring cloud"
         v
      upperText     String → String
         |  "SPRING CLOUD"
         v
      countChars    String → Integer
         |  12
         v
        12
~~~

Each function can be used individually in other contexts, while the composed pipeline creates a new business transformation. **Name composition** via `|` is typically handled by adapters as **a single combined definition**.

### 4.1. Output and Input Types Must Connect

Suppose:

~~~java
Function<String, Integer> parseQuantity = Integer::parseInt;
Function<Integer, Long> calculateCost = quantity -> quantity * 75_000L;
~~~

If the two functions are registered with those exact names, a valid expression is:

~~~yaml
spring:
  cloud:
    function:
      definition: "parseQuantity|calculateCost"
~~~

The resulting type is `String → Long`. With input `"4"`, the numeric result is `300000L`.

Conversely, `"countChars|trimText"` does not have a natural contract because `countChars` returns `Integer` whereas `trimText` takes `String`. Do not rely on implicit type coercion as part of your business logic, even if some adapters support payload conversion. Redesign the order or add a meaningful transformation step.

### 4.2. Order Cannot Be Swapped Arbitrarily

~~~yaml
# Trim whitespace first, then count.
spring:
  cloud:
    function:
      definition: "trimText|countChars"
~~~

Input `"  abc  "` yields `3`. If changed to `"countChars|trimText"`, the data types no longer match. For two functions that both accept and return `String`, the chain can still be composed, but **the business result may change** when the order is reversed.

## 5. Comma: Selecting Multiple Independent Definitions

When the integration environment and Spring Cloud Function version support comma-separated lists, you can specify **two separate functions**:

~~~yaml
spring:
  cloud:
    function:
      definition: "trimText,upperText"
~~~

Meaning of the list:

~~~text
                        +--> trimText  --> Separate result of trimText
Select two definitions
                        +--> upperText --> Separate result of upperText
~~~

There is no data-flow edge `trimText → upperText` merely because the two names appear in the same comma-separated string. Each function keeps its own type contract.

Example with the string `"  spring cloud  "`:

| Function invoked individually | Result |
|---|---|
| `trimText.apply("  spring cloud  ")` | `"spring cloud"` |
| `upperText.apply("  spring cloud  ")` | `"  SPRING CLOUD  "` |
| Pipeline `trimText|upperText` with the same input | `"SPRING CLOUD"` |

The comma **does not mean running trimText first and then upperText**. Nor does it mean any single request will automatically be duplicated to run both functions; how inputs and outputs are routed is determined by the adapter.

### 5.1. Version and Adapter Notes

Support for declaring multiple definitions and separators can vary across Spring Cloud components. In particular, Spring Cloud Stream documentation often shows multiple function definitions in the form:

~~~properties
spring.cloud.function.definition=trimText;upperText
~~~

In `application.yml`:

~~~yaml
spring:
  cloud:
    function:
      definition: "trimText;upperText"
~~~

Conceptually, `;` also represents **multiple independent definitions** in supported versions/integrations. The key is to verify the syntax supported by the adapter you are using. If a project uses commas and the adapter fails to create the expected functions/bindings, consult the documentation for your exact version instead of arbitrarily changing separators in business code.

For example, Spring Cloud Stream requires configuring the binder, input/output destinations, and possibly binding names for each function. The `spring.cloud.function.definition` property alone does not decide which topic each function listens to.

### 5.2. A Practical Example of Selecting Multiple Functions

An order-processing service might register:

- `validateOrder: Function<Order, ValidationResult>` to receive and validate orders.
- `enrichOrder: Function<Order, EnrichedOrder>` to add information to orders.

If these are **two independent processing paths** receiving data from different sources, selecting both definitions makes sense when the adapter supports configuring multiple functions/bindings. If the goal is for the output of `validateOrder` to flow directly into `enrichOrder`, the current contracts cannot be composed directly: `ValidationResult` is not `Order`. In that case, you need to design a new pipeline with compatible types rather than just changing the separator.

## 6. Comparing | and Comma

| Criterion | `"trimText|upperText"` | `"trimText,upperText"` |
|---|---|---|
| Meaning | One sequentially composed pipeline | List of two separate definitions, if supported |
| Data flow | Output of `trimText` feeds into `upperText` | Does not automatically pass output between the two functions |
| Order | Processing order matters | Listing order does not represent a pipeline |
| Type requirement | Output of previous step must match input of next step | Each function has an independent contract |
| Number of selected logic units | One combined logic unit | Two separate logic units |
| Common use cases | Normalize → validate → transform | Expose/route multiple functions for an adapter |
| Adapter dependency | Invocation method and input/output payloads | How each function is exposed and separator support |

Remember the formula:

~~~text
A|B  = A then B, creating pipeline A → B

A,B  = list A and B as two separate definitions
       (in environments supporting comma syntax)
~~~

If you need the pipeline `A → B`, use `|`. If you need two functions to be independently selected by an adapter, check the list syntax supported by that adapter.

## 7. Combining definition Selection with FunctionCatalog.lookup

`FunctionCatalog` provides a mechanism to look up registered functions. You can access a single function or compose functions by name directly in Java:

~~~java
import java.util.function.Function;

import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.stereotype.Component;

@Component
public class TextPipelineService {

    private final FunctionCatalog catalog;

    public TextPipelineService(FunctionCatalog catalog) {
        this.catalog = catalog;
    }

    public int normalizedLength(String raw) {
        Function<String, Integer> pipeline =
                catalog.lookup("trimText|upperText|countChars");

        if (pipeline == null) {
            throw new IllegalStateException("Text pipeline not found");
        }

        return pipeline.apply(raw);
    }
}
~~~

`catalog.lookup("trimText|upperText|countChars")` requests **one composed function** to invoke with `apply`. Meanwhile, the `spring.cloud.function.definition` property indicates which definitions are selected for the integration system. They are related, but they do not replace each other's role.

For example, if the configuration states:

~~~yaml
spring:
  cloud:
    function:
      definition: "trimText,upperText"
~~~

then the following Java call can still directly look up a pipeline by name from the registered functions:

~~~java
Function<String, String> pipeline =
        catalog.lookup("trimText|upperText");
~~~

Do not assume that `catalog.lookup("trimText,upperText")` will return a `Function<String, String>` behaving like `trimText.andThen(upperText)`. A comma in the **definition property** does not have the same meaning as `|` in a catalog composition expression.

### Matching Needs to Approaches

| Need | Solution |
|---|---|
| Run a single function in code | `catalog.lookup("trimText")` |
| Run multiple sequential steps in code | `catalog.lookup("trimText|upperText")` |
| Select one pipeline for an adapter | `spring.cloud.function.definition: "trimText|upperText"` |
| Expose multiple independent definitions | Configure a definition list using syntax supported by the adapter/version |
| Process input arriving from HTTP/events/serverless | Configure the corresponding adapter, convert payloads, and run integration tests |

## 8. Configuration Syntax in Practice

### 8.1. application.yml

Wrap the value in quotation marks to clearly indicate it is a string:

~~~yaml
spring:
  cloud:
    function:
      definition: "trimText|upperText"
~~~

Or with a comma-separated list in supported environments:

~~~yaml
spring:
  cloud:
    function:
      definition: "trimText,upperText"
~~~

Do not confuse `|` **inside a string value** with the `|` symbol placed **after a colon** in YAML. In YAML, `definition: |` starts a **multiline block scalar**; it does not mean composing two functions via Spring Cloud Function.

The following example **does not properly express** composing two functions:

~~~yaml
spring:
  cloud:
    function:
      definition: |
        trimText
        upperText
~~~

The YAML value in that case is a string containing newline characters, not `"trimText|upperText"`.

### 8.2. application.properties

~~~properties
spring.cloud.function.definition=trimText|upperText
~~~

For a list of definitions, if the version supports comma syntax:

~~~properties
spring.cloud.function.definition=trimText,upperText
~~~

### 8.3. Arguments When Running the Application

You can pass the property as a Spring Boot command-line option. When writing commands in a shell, **quote the entire argument containing `|`** so the shell does not interpret it as a pipe operator:

~~~powershell
java -jar app.jar '--spring.cloud.function.definition=trimText|upperText'
~~~

The filename `app.jar` is only an example; the actual path depends on your project. In container, cloud, or manifest deployments, follow the quoting and escaping rules of the target environment.

## 9. Choosing Function, Supplier, and Consumer

This lesson uses `Function<T, R>` to clearly show input/output data flow, but Spring Cloud Function also supports `Supplier<T>` and `Consumer<T>`.

- **`Supplier<T>`** produces data; it takes no arguments in its `get` call.
- **`Function<T, R>`** transforms an input into an output.
- **`Consumer<T>`** receives data and performs an action; it has no return value like `Function`.

When composing a pipeline with `|`, the position and contract of each step must make sense. For instance, where supported by the framework, a `Supplier<String>` can produce data for a downstream `Function<String, Integer>`; a `Consumer` typically acts as the terminal processing endpoint. Do not assume every arrangement of `Supplier`/`Consumer` can be chained like ordinary `Function` beans. Check the composition contract of the Spring Cloud Function version you are running.

A multi-definition list using commas or `;` does not solve this type-compatibility issue because it does not create a data connection between components.

## 10. Common Mistakes

### 10.1. Using a Comma When Sequential Composition Is Intended

~~~yaml
spring:
  cloud:
    function:
      definition: "trimText,upperText"
~~~

If the business requirement is "trim whitespace and then convert to uppercase," write:

~~~yaml
spring:
  cloud:
    function:
      definition: "trimText|upperText"
~~~

The first configuration selects independent definitions in supported environments; only the second describes a pipeline.

### 10.2. Using | When Two Separate Processing Channels Are Needed

Conversely, suppose `validateOrder` and `calculateShipping` need to receive data from two separate event streams. Composing `"validateOrder|calculateShipping"` chains the steps into one sequence (if the type contracts allow it), rather than selecting two definitions for the adapter to bind separately. Declare the list in the format supported by your adapter, then configure independent bindings.

### 10.3. Using the Wrong Function Name

~~~java
@Bean("normalizePayload")
public Function<String, String> normalize() {
    return String::trim;
}
~~~

The registered bean name is `normalizePayload`; do not assume `definition: "normalize"` will find that bean. Verify `@Bean`, component scanning, and the actual registered name before looking for bugs in the `|` or comma expression.

### 10.4. Incompatible Type Contracts

`"countChars|trimText"` turns `String` into `Integer` and then attempts to pass it to a step expecting `String`. Such a composition may be rejected by the framework or fail at runtime, depending on the runtime and data conversion capabilities. Fix the business contract instead of relying on accidental type conversion.

### 10.5. Confusing Function Selection with Automatic Adapter Configuration

`spring.cloud.function.definition` does not automatically provision URLs, register serverless triggers, configure topics, serializers, or listeners. Those belong to the adapter and deployment environment. A pipeline that works in Java does not guarantee that HTTP payloads, event headers, or JSON schemas also match.

### 10.6. Forgetting to Restart or Verify the Effective Configuration

When changing `spring.cloud.function.definition`, confirm which configuration source actually takes effect: profiles, environment variables, and command-line arguments can override `application.yml`. Check startup logs, exposed function lists, and actual integration tests.

### 10.7. Letting Clients Decide the Definition Chain

Do not pass arbitrary pipeline names directly from a request into `FunctionCatalog.lookup(...)` and execute them, as clients could invoke beans never meant to be exposed. When switching between multiple pipelines is needed, map requests to an allowlist of approved names at the application layer.

## 11. Testing Behavior in Code

### 11.1. Unit Tests for Sequential Composition Correctness

For plain Java `Function` objects, you can verify order directly:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.Locale;
import java.util.function.Function;
import org.junit.jupiter.api.Test;

class TextFunctionTest {

    @Test
    void chainedFunctionsRunInOrder() {
        Function<String, String> trim = String::trim;
        Function<String, String> upper =
                s -> s.toUpperCase(Locale.ROOT);
        Function<String, Integer> length = String::length;

        Function<String, Integer> pipeline =
                trim.andThen(upper).andThen(length);

        assertEquals(12, pipeline.apply("  spring cloud  "));
    }

    @Test
    void independentFunctionsKeepOwnResults() {
        Function<String, String> trim = String::trim;
        Function<String, String> upper =
                s -> s.toUpperCase(Locale.ROOT);

        assertEquals("spring cloud", trim.apply("  spring cloud  "));
        assertEquals("  SPRING CLOUD  ", upper.apply("  spring cloud  "));
    }
}
~~~

This test verifies transformation behavior, but does not verify how Spring Cloud Function resolves function names or how an adapter reads `definition`.

### 11.2. Integration Tests with FunctionCatalog

When you have a Spring Boot application configured to scan `TextFunctions` and the Spring Cloud Function context, you can test the pipeline by name:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.util.function.Function;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

@SpringBootTest
class TextCompositionIntegrationTest {

    @Autowired
    FunctionCatalog catalog;

    @Test
    void lookupComposesByPipe() {
        Function<String, Integer> pipeline =
                catalog.lookup("trimText|upperText|countChars");

        assertNotNull(pipeline);
        assertEquals(12, pipeline.apply("  spring cloud  "));
    }

    @Test
    void namesAreLookedUpIndependently() {
        Function<String, String> trim = catalog.lookup("trimText");
        Function<String, String> upper = catalog.lookup("upperText");

        assertNotNull(trim);
        assertNotNull(upper);
        assertEquals("spring cloud", trim.apply("  spring cloud  "));
        assertEquals("  SPRING CLOUD  ",
                upper.apply("  spring cloud  "));
    }
}
~~~

The test above requires the `spring-boot-starter-test` dependency and a properly configured Spring Cloud Function environment. For commas or `;`, you also need **adapter integration tests** to confirm that multiple definitions are actually selected, exposed, and wired to the right channels.

### 11.3. Testing Adapters by Deployment Target

| Invocation environment | What to verify |
|---|---|
| HTTP | Actual endpoint/path, body type, response type, input errors |
| Events/messaging | Which function binds to which binding, destination, serializer, headers, and errors |
| Serverless | Event trigger, input payload, return result, handler configuration |
| Internal Java | `lookup` name, data types, execution order, exceptions |

Do not conclude that a multi-definition configuration works just because unit tests for individual beans pass.

## 12. Real-World Scenario: One Flow or Two Flows?

An application has the following steps:

- `parseOrder: Function<String, Order>` parses a raw order.
- `validateOrder: Function<Order, ValidatedOrder>` checks business rules.
- `calculateTotal: Function<ValidatedOrder, Receipt>` calculates the total amount.
- `updateCatalog: Function<CatalogEvent, CatalogResult>` updates the catalog.

If the goal is to process an order end-to-end, select the pipeline:

~~~yaml
spring:
  cloud:
    function:
      definition: "parseOrder|validateOrder|calculateTotal"
~~~

If the same application also receives an **independent** catalog-update event type, you may also need to select `updateCatalog` for an adapter that supports multiple definitions. Conceptually, there are two branches:

~~~text
Order branch:
  parseOrder → validateOrder → calculateTotal

Catalog event branch:
  updateCatalog
~~~

Example when the adapter and version support comma-separated lists:

~~~yaml
spring:
  cloud:
    function:
      definition: "parseOrder|validateOrder|calculateTotal,updateCatalog"
~~~

The snippet above illustrates the meaning of **one pipeline and one separate function**; whether mixing `|` and `,` is parsed properly must be confirmed in the actual framework/adapter version. With Spring Cloud Stream, you may need to use the multi-definition separator specified by that version, typically `;`, along with declaring bindings for each branch.

Do not compose `"...|updateCatalog"` directly because `Receipt` is not `CatalogEvent` and that is not the business requirement.

## 13. Self-Practice Exercises

1. Given `trimText: String → String`, `upperText: String → String`, and `countChars: String → Integer`, write the `spring.cloud.function.definition` value to compute the length of a string after trimming and uppercasing. Determine the output for `"  java  "`.
2. You need to expose `findCustomer` and `findInvoice` as **two independent functions** in an adapter that supports multiple definitions. Write the comma-separated list and explain why `findCustomer|findInvoice` does not express the requirement.
3. Given `parse: String → Integer` and `format: Long → String`, why does `"parse|format"` lack a directly compatible type contract? Propose a semantically meaningful conversion step.
4. An application sets `definition: "trimText,upperText"`, yet all events are routed to one binding where you expected the pipeline to run. Describe how to distinguish between a **composition syntax error** and an **adapter configuration error**.
5. Write an integration test that calls `catalog.lookup("trimText|upperText")` and verifies that the input `" abc "` returns `"ABC"`. Explain why this test is not sufficient to prove that two independent functions are exposed via a broker.

**Hint for Exercise 1:** `definition: "trimText|upperText|countChars"`; the string `"JAVA"` has length `4`.

## 14. Key Takeaways

- `spring.cloud.function.definition` selects the function name or function expression that Spring Cloud Function/the adapter will use.
- The `|` symbol creates **one sequential pipeline**: `A|B` runs A first and passes its result into B.
- The comma `,` in environments supporting definition lists is used to **select multiple independent functions**; it does not automatically pass data from A to B. Spring Cloud Stream often uses `;` for this purpose depending on the version.
- `FunctionCatalog.lookup("A|B")` looks up a composed function in Java, whereas `spring.cloud.function.definition` selects logic for the integration layer.
- To deploy over HTTP, events, or serverless, in addition to selecting the definition, you need the appropriate adapter, data contracts, and integration tests.
