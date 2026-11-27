# Distinguishing Direct Bean Invocation from Catalog Function Lookup

## 1. Why Do Both Invocation Paths Matter in Azure Functions?

**Spring Cloud Function (SCF)** structures business logic using the Java interfaces `Supplier<T>`, `Function<T,R>`, and `Consumer<T>`. Functions can be shared across protocols, chained into multi-step pipelines, and looked up through `FunctionCatalog`. This enables reusable logic that serves HTTP, event streams, or a serverless platform without rewriting core processing.

In **Azure Functions**, a `@FunctionName` Java method is the entrypoint invoked by the Azure Java Worker upon a trigger. With `spring-cloud-function-adapter-azure`, a `@Component`-annotated handler is managed by Spring and can either **inject `Function` beans directly** or **inject `FunctionCatalog` for lookup**.

Both approaches are valid, yet **not completely identical**:

- **Direct bean invocation:** `rawFunction.apply(input)` executes the exact object Spring instantiated from `@Bean`; it does not pass through an SCF wrapper by default.
- **Catalog invocation:** `catalog.lookup("name").apply(input)` executes a *canonical* representation wrapped by Spring Cloud Function, enabling additional features such as composition, signature normalization, and type/message conversion in supported contexts.
- **Catalog composition invocation:** `catalog.lookup("first|second|third")` builds an ordered function pipeline so the handler does not manually wire each step.

The goal of this lesson is to compare **each concrete invocation path inside an Azure handler**, rather than treating the catalog as "always better in every situation."

### Learning Outcomes

After this lesson, you will be able to:

1. Distinguish a raw Spring `Function` bean from a function wrapper in `FunctionCatalog`.
2. Write an Azure handler injecting beans directly and one injecting the catalog, both reusing the same business pipeline.
3. Explain `a|b|c` ordering, type signatures, and conversion limits.
4. Decide when to use direct DI vs. catalog/composition.
5. Recognize that `@FunctionName`, `@HttpTrigger`, `@Bean`, and catalog names live in **different namespaces**.
6. Handle null lookups, parse/conversion errors, message headers, invocation context, concurrency, and security.
7. Test plain Java functions, Spring bean registration, catalog wrappers, and the Azure Host separately.

## 2. Quick Comparison Table

| Aspect | Direct Bean | FunctionCatalog |
| --- | --- | --- |
| How obtained | `@Qualifier("parseOrder") Function<...>` or `applicationContext.getBean(...)`. | Inject `FunctionCatalog` and call `lookup("parseOrder")`. |
| Object received | **Raw bean** instantiated by Spring. | **SCF-wrapped representation** (canonical/instrumented). |
| Business call | `bean.apply(input)`. | `catalogFunction.apply(input)`. |
| Chaining multiple steps | Java `andThen(...)` or sequential calls. | `lookup("parseOrder|classifyOrder|formatOrder")`. |
| Types and conversion | Follows the bean's Java generics; caller prepares the input. | SCF provides wrappers/conversions for supported signatures and media types. |
| Message metadata | Only sees headers if the bean accepts `Message<T>`. | Wrapper supports message-aware signatures; adapter must still pass headers properly. |
| Strengths | Transparent, compile-time type-safe contract, minimal abstraction. | Multi-adapter reuse, composition by name, unified adapter contract. |
| Risks | Forgetting body conversion, duplicating chaining logic in handlers. | Misspelled lookup names, over-relying on conversion, uncontrolled dynamic config. |
| Azure trigger/binding | **Not auto-created**. | **Also not auto-created**. |

**Key takeaway:** For a `Function<String,String>` bean, both paths can return the **exact same data** for a valid `String` input. Differences in **execution path and framework capabilities** do not imply every catalog call alters results or is always faster or slower than a direct call.

## 3. Diagram of Both Paths

~~~mermaid
flowchart LR
    A["HTTP request"] --> B["Azure Functions Host / Java Worker"]
    B --> C["@Component handler with @FunctionName"]
    S["Spring ApplicationContext"] --> D["@Bean parseOrder"]
    S --> E["@Bean classifyOrder"]
    S --> F["@Bean formatOrder"]
    S --> G["FunctionCatalog"]
    D --> G
    E --> G
    F --> G
    C -->|"direct: parse→classify→format"| D
    D -. "raw Java function" .-> E
    E -. "raw Java function" .-> F
    C -->|"catalog.lookup('parseOrder|classifyOrder|formatOrder')"| G
    G --> H["SCF canonical composed function"]
    H --> I["HTTP response"]
    F --> I
~~~

**Ownership rules to remember:**

- `@Bean` registers the function as a **Spring bean**.
- `FunctionCatalog` discovers **functional beans** and exposes them through an SCF wrapper layer.
- `@Component` puts the Azure handler under Spring component scanning/dependency injection.
- `@FunctionName` and `@HttpTrigger` let Azure recognize **a function handler/HTTP route**.
- The Azure Maven/Gradle plugin scans Azure annotations to generate `function.json` binding metadata.

Azure does not automatically turn `catalog.lookup("myFunction")` into an HTTP Trigger. To expose a trigger, declare it on a handler or use a specialized adapter capable of exposing endpoints.

## 4. Project Setup and Dependencies

### 4.1. Required Libraries

For a Java 17+ application configured with a **Spring Boot parent** and a **compatible Spring Cloud BOM**, a Maven `dependencies` snippet can look like:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-function-adapter-azure</artifactId>
    </dependency>

    <dependency>
        <groupId>com.microsoft.azure.functions</groupId>
        <artifactId>azure-functions-java-library</artifactId>
        <version>1.3.1</version>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

`1.3.1` is an **illustrative dependency baseline** for the Azure Functions Java library, not a claim that it is the latest version. Pick the Java library version from the Microsoft template used by your project. The `spring-cloud-function-adapter-azure` version should be aligned with SCF context via the Spring Cloud BOM; modern adapter documentation requires **SCF 4.0.0+**.

`spring-cloud-function-adapter-azure` integrates Spring/SCF with the Azure Java Worker. `spring-cloud-function-context` supplies `FunctionCatalog` and is typically a transitive dependency. The Azure Java library provides the annotations and request/response types.

**Distinction:** `azure-functions-maven-plugin` or the Azure Gradle plugin is a **build/package/run tool**, not a Spring bean or `FunctionCatalog`.

### 4.2. Gradle Equivalent

~~~groovy
dependencies {
    implementation 'org.springframework.cloud:spring-cloud-function-adapter-azure'
    implementation 'com.microsoft.azure.functions:azure-functions-java-library:1.3.1'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Spring Boot/Spring Cloud dependency management is required for Gradle. Use the Azure Gradle plugin `com.microsoft.azure.azurefunctions` when packaging with Gradle; do not mix in Maven workflows without reason.

### 4.3. Choosing the Right Azure Adapter

This lesson uses **`spring-cloud-function-adapter-azure`**, where you declare `@FunctionName` and `@HttpTrigger` yourself. If your application uses Spring MVC controllers/filters in the Spring Web model, there is a dedicated `spring-cloud-function-adapter-azure-web` adapter. That is a **different strategy**; do not add both simultaneously just to invoke a `Function` bean.

## 5. End-to-End Example: One Business Logic, Two Invocation Styles

Problem: an HTTP POST receives an order code and total amount in text format:

~~~text
Input : "  dh-501  |  1500000  "
Output: "DH-501|PRIORITY|1500000"
~~~

We split a single business pipeline into **three function beans**:

| Function Bean | Input | Output | Responsibility |
| --- | --- | --- | --- |
| `parseOrder` | `String` | `OrderInput` | Parse, validate, and normalize order code. |
| `classifyOrder` | `OrderInput` | `OrderDecision` | Classify based on the amount threshold. |
| `formatOrder` | `OrderDecision` | `String` | Build text response. |

Both the direct bean handler and the catalog handler use these exact same three beans. Never write two copies of the classification rules.

~~~mermaid
flowchart LR
    A["String"] --> B["parseOrder"]
    B --> C["OrderInput"]
    C --> D["classifyOrder"]
    D --> E["OrderDecision"]
    E --> F["formatOrder"]
    F --> G["String"]
~~~

### 5.1. Spring Boot Class and Three Function Beans

Create `src/main/java/example/azure/OrderFunctionsApplication.java`:

~~~java
package example.azure;

import java.util.Locale;
import java.util.function.Function;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

record OrderInput(String orderId, long totalVnd) {}

record OrderDecision(String orderId, long totalVnd, String lane) {}

@SpringBootApplication
public class OrderFunctionsApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderFunctionsApplication.class, args);
    }

    @Bean
    public Function<String, OrderInput> parseOrder() {
        return raw -> {
            if (raw == null) {
                throw new IllegalArgumentException("Missing order");
            }

            String[] parts = raw.split("\\|", -1);
            if (parts.length != 2) {
                throw new IllegalArgumentException(
                        "Format must be orderId|totalVnd");
            }

            String id = parts[0].strip()
                    .toUpperCase(Locale.ROOT);
            if (id.isBlank()) {
                throw new IllegalArgumentException("Order code is blank");
            }

            final long total;
            try {
                total = Long.parseLong(parts[1].strip());
            }
            catch (NumberFormatException ex) {
                throw new IllegalArgumentException(
                        "Total amount is not an integer", ex);
            }
            if (total <= 0) {
                throw new IllegalArgumentException(
                        "Total amount must be greater than 0");
            }

            return new OrderInput(id, total);
        };
    }

    @Bean
    public Function<OrderInput, OrderDecision> classifyOrder() {
        return order -> {
            String lane = order.totalVnd() >= 1_000_000
                    ? "PRIORITY" : "STANDARD";
            return new OrderDecision(
                    order.orderId(), order.totalVnd(), lane);
        };
    }

    @Bean
    public Function<OrderDecision, String> formatOrder() {
        return result -> result.orderId() + "|"
                + result.lane() + "|"
                + result.totalVnd();
    }
}
~~~

This is a **Spring Cloud Function application**: there are no Azure SDK imports in the business logic. Both records in the same package are package-private; if moved to other packages, extract them as public records per Java rules.

The three function beans have clear signatures and **hold no mutable state**. Both Java's `Function.andThen(...)` and `FunctionCatalog` can compose them because each step's output type matches the next step's input type.

### 5.2. Calling Beans Directly in Java

Inside a Spring-managed component, you can inject each function individually:

~~~java
private final Function<String, OrderInput> parser;
private final Function<OrderInput, OrderDecision> classifier;
private final Function<OrderDecision, String> formatter;
~~~

Inside a method:

~~~java
String output = formatter.apply(
        classifier.apply(
                parser.apply(rawInput)));
~~~

This is the **raw Java function** path. If `rawInput` is a `byte[]`, the compiler will refuse to pass bytes directly into `Function<String,OrderInput>`. The caller must convert bytes to `String`, deserialize JSON, or read a POJO per contract.

### 5.3. Using FunctionCatalog

If injecting `FunctionCatalog catalog`:

~~~java
Function<String, String> pipeline =
        catalog.lookup("parseOrder|classifyOrder|formatOrder");

String output = pipeline.apply(rawInput);
~~~

This is a **function composition** managed by SCF. The order `parseOrder|classifyOrder|formatOrder` means:

~~~text
formatOrder(classifyOrder(parseOrder(rawInput)))
~~~

Hence, the output for `" dh-501 | 1500000 "` matches the direct call path. This is a case of **same business outcome, different invocation mechanism**.

### 5.4. Should You Use FunctionCatalog for a Single Function?

Yes, if you need the SCF wrapper/canonical behavior:

~~~java
Function<String, OrderInput> fromCatalog =
        catalog.lookup("parseOrder");

OrderInput value = fromCatalog.apply(" dh-501 | 1500000 ");
~~~

However, if you only need a properly typed Java function injected and do not need SCF instrumentation or composition, direct bean injection is simpler and completely appropriate.

## 6. Azure Handler Containing Both Invocation Paths

Create `src/main/java/example/azure/OrderAzureHandlers.java`:

~~~java
package example.azure;

import java.util.Objects;
import java.util.Optional;
import java.util.function.Function;
import java.util.logging.Level;

import com.microsoft.azure.functions.AuthorizationLevel;
import com.microsoft.azure.functions.ExecutionContext;
import com.microsoft.azure.functions.HttpMethod;
import com.microsoft.azure.functions.HttpRequestMessage;
import com.microsoft.azure.functions.HttpResponseMessage;
import com.microsoft.azure.functions.HttpStatus;
import com.microsoft.azure.functions.annotation.FunctionName;
import com.microsoft.azure.functions.annotation.HttpTrigger;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.stereotype.Component;

@Component
public class OrderAzureHandlers {

    private final Function<String, OrderInput> parser;
    private final Function<OrderInput, OrderDecision> classifier;
    private final Function<OrderDecision, String> formatter;
    private final Function<String, String> catalogPipeline;

    public OrderAzureHandlers(
            @Qualifier("parseOrder")
            Function<String, OrderInput> parser,

            @Qualifier("classifyOrder")
            Function<OrderInput, OrderDecision> classifier,

            @Qualifier("formatOrder")
            Function<OrderDecision, String> formatter,

            FunctionCatalog catalog) {

        this.parser = parser;
        this.classifier = classifier;
        this.formatter = formatter;

        this.catalogPipeline = Objects.requireNonNull(
                catalog.lookup(
                        "parseOrder|classifyOrder|formatOrder"),
                "Function composition not found");
    }

    @FunctionName("directBeanOrder")
    public HttpResponseMessage directBeanOrder(
            @HttpTrigger(
                    name = "request",
                    methods = {HttpMethod.POST},
                    authLevel = AuthorizationLevel.FUNCTION,
                    route = "orders/direct")
            HttpRequestMessage<Optional<String>> request,
            ExecutionContext context) {

        Function<String, String> rawPipeline = text ->
                formatter.apply(classifier.apply(parser.apply(text)));

        return handle(request, context, rawPipeline);
    }

    @FunctionName("catalogOrder")
    public HttpResponseMessage catalogOrder(
            @HttpTrigger(
                    name = "request",
                    methods = {HttpMethod.POST},
                    authLevel = AuthorizationLevel.FUNCTION,
                    route = "orders/catalog")
            HttpRequestMessage<Optional<String>> request,
            ExecutionContext context) {

        return handle(request, context, catalogPipeline);
    }

    private HttpResponseMessage handle(
            HttpRequestMessage<Optional<String>> request,
            ExecutionContext context,
            Function<String, String> operation) {

        String body = request.getBody().orElse("");

        try {
            String output = operation.apply(body);
            return request.createResponseBuilder(HttpStatus.OK)
                    .header("Content-Type",
                            "text/plain; charset=utf-8")
                    .body(output)
                    .build();
        }
        catch (IllegalArgumentException invalid) {
            return request
                    .createResponseBuilder(HttpStatus.BAD_REQUEST)
                    .body("Invalid order format")
                    .build();
        }
        catch (RuntimeException failure) {
            // SCF wrapper may wrap the original validation error.
            Throwable root = failure;
            while (root.getCause() != null
                    && root.getCause() != root) {
                root = root.getCause();
            }

            if (root instanceof IllegalArgumentException) {
                return request
                        .createResponseBuilder(HttpStatus.BAD_REQUEST)
                        .body("Invalid order format")
                        .build();
            }

            context.getLogger().log(
                    Level.SEVERE, "Order processing failed", failure);

            return request
                    .createResponseBuilder(
                            HttpStatus.INTERNAL_SERVER_ERROR)
                    .body("Unable to process order")
                    .build();
        }
    }
}
~~~

**The difference lies in the two invocation paths:**

- `directBeanOrder` chains the three raw Java functions via direct calls.
- `catalogOrder` invokes a single `Function<String,String>` returned by SCF for the definition `parseOrder|classifyOrder|formatOrder`.
- `handle(...)` contains the shared HTTP boundary handling for both, making outputs easy to compare.
- Both paths reuse the **same three business function beans**. Do not alter payload content just to prove a difference.
- `@Component` lets Spring instantiate the handler and inject dependencies; `@FunctionName` and `@HttpTrigger` inform the Azure Host of the entrypoint and binding.

### 6.1. Why Constructor Injection and @Qualifier?

All three `Function` beans implement the same raw Java interface with different generic types. Spring can rely on type information, yet `@Qualifier` makes **the exact bean name** explicit, avoiding ambiguity if the project adds functions with matching signatures.

Constructor injection resolves dependencies when Spring initializes the handler; `final` fields prevent accidental mutation. If `catalog.lookup(...)` returns `null`, `Objects.requireNonNull` **fails fast** at startup instead of waiting for the first invocation.

### 6.2. Do Not Cache Request Context in Beans

`OrderAzureHandlers` defaults to a Spring singleton. `ExecutionContext` is supplied by Azure **per invocation**, so it must remain a method parameter rather than a mutable field or an injected singleton bean. Functional beans should be stateless or appropriately thread-safe when concurrent invocations run.

### 6.3. Easily Confused Names

| Name | Which System Owns It? | Purpose |
| --- | --- | --- |
| `directBeanOrder` | Azure Function name | Azure Host discovers and runs the direct handler. |
| `catalogOrder` | Azure Function name | Azure Host discovers and runs the catalog handler. |
| `orders/direct` | Azure HTTP Trigger route | URL path of the direct handler. |
| `orders/catalog` | Azure HTTP Trigger route | URL path of the catalog handler. |
| `parseOrder` | Spring bean / SCF function name | Parses input. |
| `classifyOrder` | Spring bean / SCF function name | Classifies order. |
| `formatOrder` | Spring bean / SCF function name | Formats text response. |
| `parseOrder|classifyOrder|formatOrder` | SCF composition definition | Chains the three function beans. |

An Azure Function name is **not** a Spring bean name. Renaming `@FunctionName` does not change catalog definitions; renaming a `@Bean` can break existing catalog lookups.

## 7. Test Results and the Principle of Business Consistency

Once the Azure Functions Host runs locally with the default `/api` prefix:

~~~text
POST http://localhost:7071/api/orders/direct
POST http://localhost:7071/api/orders/catalog
~~~

Send the same body:

~~~bash
curl -i -X POST "http://localhost:7071/api/orders/direct" \
  -H "Content-Type: text/plain" \
  --data " dh-501 | 1500000 "
~~~

~~~bash
curl -i -X POST "http://localhost:7071/api/orders/catalog" \
  -H "Content-Type: text/plain" \
  --data " dh-501 | 1500000 "
~~~

Both are expected to return:

~~~text
HTTP/1.1 200 OK

DH-501|PRIORITY|1500000
~~~

### 7.1. Input Cases to Test

| Body | Output | HTTP |
| --- | --- | --- |
| `"dh-501|1500000"` | `DH-501|PRIORITY|1500000` | 200 |
| `" dh-502 | 999999 "` | `DH-502|STANDARD|999999` | 200 |
| `"dh-503|1000000"` | `DH-503|PRIORITY|1000000` | 200 |
| `"dh-504|abc"` | Validation error | 400 |
| `"dh-505|0"` | Validation error | 400 |
| `" | 2000000"` | Validation error | 400 |
| `"dh-506"` | Validation error | 400 |
| Blank body | Validation error | 400 |

If the two endpoints produce different results for the same data and version, inspect the **direct pipeline**, **catalog wrapper**, **composition order**, or conversions. Do not jump to concluding "the catalog is broken," since the two may not run identically if an adapter wraps inputs differently.

## 8. FunctionCatalog Is More Than ApplicationContext.getBean

### 8.1. Direct Bean: The Exact Declared Object

In Spring:

~~~java
Function<String, OrderInput> raw =
        applicationContext.getBean("parseOrder", Function.class);
~~~

This looks up the bean by name and raw class type; Java produces an unchecked generic cast warning if assigned directly. In real applications, prefer constructor injection with `@Qualifier` and a properly parameterized `Function<String,OrderInput>` declaration to avoid raw casts.

Calling `raw.apply(...)` runs the bean's implementation along with any Spring decorators/`BeanPostProcessor` proxies. **It does not automatically receive SCF's canonical wrapper** merely because the bean implements `Function`.

### 8.2. FunctionCatalog: Canonical Function Wrapper

SCF documentation states that `FunctionCatalog` converts user-defined functional beans into a unified representation, adding capabilities beyond raw Java invocation.

~~~java
Function<String, OrderInput> wrapped =
        catalog.lookup("parseOrder");
~~~

Capabilities provided by the SCF wrapper/canonical model depending on signature and context:

- **Composition** via `f1|f2` or `f1,f2` definitions in supported contexts.
- **Type conversion** between payload/message representations within the bounds of registered converters, content types, and SCF signatures.
- **Message-aware signatures** that can accept `Message<T>` and process headers.
- **SCF metadata/arity/reactive models**, including specific rules when functions accept `Flux`/`Mono`.
- **Input/output header enrichment** per SCF configuration when the appropriate wrapper and message contract apply.

**Do not overpromise:** the wrapper does not magically understand arbitrary JSON, unregistered schemas, Azure `HttpRequestMessage` objects, or arbitrary event payloads. Appropriate adapters/converters, content types, and boundary contract tests are still required.

### 8.3. Is a Function from the Catalog the Same Instance as the Raw Bean?

Do not assert correctness with:

~~~java
assertSame(rawFunction, catalog.lookup("parseOrder"));
~~~

A function returned by the catalog can be a wrapper or composed representation rather than sharing object identity with the original Spring bean. Test **inputs, outputs, and behavior** rather than reference equality.

### 8.4. Does Execution Cost Always Differ?

There is no universal rule that direct beans are **always meaningfully faster** or that the catalog is **always slower** in real workloads. The catalog introduces a wrapper and may perform conversions, yet Azure I/O, database calls, network latency, or cold starts typically dominate. Resolve fixed compositions **once in the constructor**, then benchmark throughput/latency if performance is critical.

**Choose direct** when types are clear, steps are few, and SCF-specific features are unnecessary. **Choose catalog** when you want composition, uniform invocation across adapters, or supported canonical capabilities.


## 9. Type Conversion: A Difference That Must Be Verified

### 9.1. Direct Beans Enforce Explicit Java Types

A bean with signature:

~~~java
Function<String, OrderInput> parseOrder = ...;
~~~

requires a `String` input. With Azure data:

~~~java
HttpRequestMessage<Optional<String>> request = ...;
String body = request.getBody().orElse("");
OrderInput order = parseOrder.apply(body);
~~~

This is direct and type-safe at the Java level once the request body is deserialized/converted into the expected type. If replacing `String` with `OrderRequest`, the handler needs a converter or Azure POJO binding.

Do not do this:

~~~java
// Type contract violation: Object does not automatically become String.
byte[] bytes = ...;
OrderInput order = parseOrder.apply(bytes);
~~~

This snippet is an **anti-pattern** and will not compile when Java generics are properly typed. Using raw `Function` or unchecked casts turns this into a runtime `ClassCastException`.

### 9.2. Catalog Wrappers Can Convert at Boundaries, Under Conditions

SCF normalizes function signatures and provides conversion/wrapping in supported contexts. For instance, when an adapter provides a `Message<?>` with a valid `contentType`, the wrapper can work with payloads differing from the declared type using registered converters.

However:

- **There is no guarantee** every `byte[]`, `String`, or Azure POJO automatically turns into `OrderInput`.
- **There is no guarantee** an arbitrary JSON body with an unfamiliar schema deserializes properly without configuration.
- Conversion depends on **function signature**, **content type**, **type information**, **message converters**, and which adapter creates/reads the message.
- Azure `HttpRequestMessage<?>` is **not** a Spring `Message<?>`. The handler may need to translate data/metadata at the boundary.
- When the catalog returns a function wrapper, avoid using raw `Function` and casting results arbitrarily.

That is why in the **working example**, both the direct handler and the catalog handler pass a **`String` read from the HTTP body** into the pipeline. We do not rely on conversion as "magic" to obscure the contract.

### 9.3. Message-Aware Functions and Metadata

Suppose a domain service needs `traceId` when writing an audit record. A dedicated function can accept **`Message<OrderInput>`**:

~~~java
@Bean
Function<Message<OrderInput>, Message<OrderDecision>> classifyWithTrace(
        Function<OrderInput, OrderDecision> classifier) {

    return incoming -> MessageBuilder
            .withPayload(classifier.apply(incoming.getPayload()))
            .copyHeaders(incoming.getHeaders())
            .setHeader("processingStage", "CLASSIFIED")
            .build();
}
~~~

This is an **extended example**, requiring imports for `org.springframework.messaging.Message` and `org.springframework.messaging.support.MessageBuilder`, and injecting `classifier` with `@Qualifier("classifyOrder")` if Spring has multiple matching beans. `classifyWithTrace` is not part of the minimal Section 5 example; add it only after agreeing on a metadata contract.

Inside an Azure handler, metadata can be placed into a Spring Message intentionally:

~~~java
Message<String> message = MessageBuilder
        .withPayload(request.getBody().orElse(""))
        .setHeader("correlationId", context.getInvocationId())
        .build();
~~~

This **constructs the envelope at the application layer**; it does not automatically turn `HttpRequestMessage` into a Spring Message. If the function only accepts `String`, it will not see the `correlationId` header. If it accepts `Message<String>`, it can read that header per contract.

SCF Azure also provides `AzureFunctionUtil.enhanceInputIfNecessary(...)` to attach Azure's `ExecutionContext` to a Spring Message when signatures match; there is no need to use it when pure functions do not require Azure context.

### 9.4. Header Propagation Does Not Mean Copying Every Header

When using `MessageBuilder.copyHeaders(...)`, remember:

- `replyChannel`/`errorChannel` and system headers carry special routing semantics.
- Outbound adapters may strip or rewrite headers.
- Never forward raw tokens, cookies, function keys, or acknowledgement handles to external systems.
- For HTTP request headers, map only validated and genuinely needed values.
- Across Service Bus, Queue, or Event Hubs, verify header mapping against the **corresponding binding/adapter**.

**Good design:** business functions take domain objects when metadata is unnecessary; use `Message<T>` or a neutral context DTO when metadata is part of the contract.

## 10. Additional Rules for Composition

### 10.1. Ordering and Type Compatibility

In our example:

~~~text
parseOrder    : String        → OrderInput
classifyOrder : OrderInput    → OrderDecision
formatOrder   : OrderDecision → String
~~~

You can compose:

~~~text
parseOrder|classifyOrder|formatOrder
~~~

But you cannot expect:

~~~text
formatOrder|parseOrder|classifyOrder
~~~

to work, because `formatOrder` expects `OrderDecision`, not `String`, at the start, and the subsequent steps do not align with the intended pipeline.

Direct Java composition must also follow the type contract:

~~~java
Function<String, String> directComposition =
        parseOrder.andThen(classifyOrder).andThen(formatOrder);
~~~

This works when you have the three function instances with generic types declared as in Section 5. Unlike catalog definitions, Java's `andThen` checks generic compatibility at compile time in most cases.

### 10.2. Supplier, Function, and Consumer in Composition

SCF supports a broader composition model than basic Java `Function.andThen`.

| Composition | Conceptual Result | Suitable For |
| --- | --- | --- |
| `Function<A,B> + Function<B,C>` | `Function<A,C>` | HTTP request/reply, message transformation. |
| `Supplier<A> + Function<A,B>` | `Supplier<B>` | Data source/timer producing transformed values. |
| `Function<A,B> + Consumer<B>` | `Consumer<A>` | Event/Queue handler with side effects, no business reply needed. |
| `Supplier<A> + Consumer<A>` | `Runnable` | Produces and consumes values with no external input. |
| `Consumer<A> + Function<...>` | Invalid linear composition | Consumer returns no output for the next step. |

Therefore, if an Azure HTTP handler expects an `OrderDecision` response, never use a definition ending in `Consumer<OrderDecision>` and try to cast it to `Function<String,OrderDecision>`. Pick the pipeline output type intentionally.

### 10.3. Reactive Functions Are Not Standard Direct Event Invocations

Example:

~~~java
@Bean
Function<Flux<OrderInput>, Flux<OrderDecision>> classifyReactive() {
    return stream -> stream.map(order ->
            new OrderDecision(order.orderId(),
                    order.totalVnd(),
                    order.totalVnd() >= 1_000_000
                            ? "PRIORITY" : "STANDARD"));
}
~~~

This is a **standalone example** requiring `reactor.core.publisher.Flux` and the Reactor dependency. Do not add it to the minimal HTTP demo unless you have a reactive pipeline.

For reactive functions, SCF applies specific rules when invoking functions with streams/Publishers. Do not assume you can call `classifyReactive.apply(oneOrder)` like an imperative `Function<OrderInput,OrderDecision>`, or expect an Azure HTTP adapter to automatically wrap every invocation in a `Flux`.

### 10.4. When the Function Catalog Contains Multiple Functions

SCF can auto-resolve a single function when the catalog holds **only one** functional bean; documentation notes that single-function fallback can even match an unmatched lookup name. Once an application has **multiple functions**, **always use exact names**, especially in Azure handlers and tests.

To disable single-function fallback, set:

~~~properties
spring.cloud.function.single-function-fallback-enabled=false
~~~

And if you have a `Function` bean that should not appear in the catalog:

~~~properties
spring.cloud.function.ineligible-definitions=someInfrastructureFunction
~~~

These are **SCF configuration options**, not rules controlling whether the Azure plugin generates triggers.

### 10.5. Does spring.cloud.function.definition Auto-Select an Azure Method?

No. The property:

~~~properties
spring.cloud.function.definition=parseOrder|classifyOrder|formatOrder
~~~

is used by SCF integration frameworks/adapters in certain contexts to specify a default definition. It does not create an Azure `@FunctionName` or the `orders/catalog` route. In our example, the handler calls `catalog.lookup(...)` **explicitly**, so the code itself determines the definition.

## 11. Azure ExecutionContext, Tracing, and Security

### 11.1. Both Direct and Catalog Calls Need an Adapter Boundary

The Azure HTTP method receives:

~~~java
@HttpTrigger(
        name = "request",
        methods = {HttpMethod.POST},
        authLevel = AuthorizationLevel.FUNCTION,
        route = "orders/catalog")
HttpRequestMessage<Optional<String>> request
~~~

Regardless of whether you choose direct beans or the catalog, the handler must still manage:

- Reading request body/query/route data and validating inputs.
- Azure `ExecutionContext`, invocation ID, and logger.
- HTTP response status, content type, and body.
- Trigger authorization and caller authentication when required.
- Transport errors, timeouts, and client retry policies.
- When moving to Queue/Event triggers: message serialization, output bindings, retries, and idempotency.

`FunctionCatalog` does not decide HTTP status **400** or **500**. Error mapping is the responsibility of the handler/adapter or a dedicated exception-mapping layer.

### 11.2. Wrappers May Wrap Exceptions

When a function throws `IllegalArgumentException` on invalid data, a **direct call** normally throws that exception directly. With the catalog/adapter path, exceptions may be wrapped in another `RuntimeException`/`MessagingException` depending on the wrapper and execution path.

Therefore:

- Do not tie tests to **one specific wrapper exception** if the contract only requires a validation failure.
- When mapping HTTP 400, inspect the root cause or use typed domain/validation exceptions.
- Never assume every `RuntimeException` should map to HTTP 400.
- If the root cause is unclear or indicates a system error, return 500/503 per contract and log safely.

**The error-handling branch used in `handle(...)`** in Section 6 catches `RuntimeException failure` and walks to the root cause to recognize validation errors:

~~~java
catch (RuntimeException failure) {
    Throwable root = failure;
    while (root.getCause() != null
            && root.getCause() != root) {
        root = root.getCause();
    }

    if (root instanceof IllegalArgumentException) {
        return request.createResponseBuilder(HttpStatus.BAD_REQUEST)
                .body("Invalid order format")
                .build();
    }

    context.getLogger().log(
            Level.SEVERE, "Order processing failed", failure);

    return request.createResponseBuilder(
            HttpStatus.INTERNAL_SERVER_ERROR)
            .body("Unable to process order")
            .build();
}
~~~

This explains the `catch (RuntimeException)` branch already present in the complete code; **do not paste a duplicate catch block** into the original method. In production, classifying errors via explicit **application exception types** is generally cleaner than inspecting the deepest cause of every exception.

### 11.3. Never Take Arbitrary Function Names from HTTP

Example to avoid using directly:

~~~java
String requestedDefinition =
        request.getQueryParameters().get("function");

Function<?, ?> selected =
        catalog.lookup(requestedDefinition);
~~~

With untrusted callers, this can expose internal non-public functions, alter business workflows, or cause abnormal load. If dynamic routing is truly required, enforce an **allowlist of function definitions**, per-caller authorization, per-function input schemas, and resource limits.

SCF also offers `RoutingFunction` and `spring.cloud.function.routing-expression` in supported contexts. Never let untrusted input directly control execution expressions; use documented evaluation restrictions/authorization and test them in your target environment.

### 11.4. Thread Safety and Cold Starts

`OrderAzureHandlers`, the three function beans, and `catalogPipeline` can be reused across multiple Azure invocations on the same worker. If a function keeps mutable request state in a field, both direct and catalog paths suffer race conditions. The SCF wrapper **does not automatically make a stateful business function thread-safe**.

The catalog must initialize/resolve dependencies when the handler is created; this can contribute to cold start time, while catching typos early. Never create a Spring `ApplicationContext` on every invocation; let the Azure adapter manage the context.

## 12. Testing: Differences Between Raw Beans and Catalog Wrappers

### 12.1. Plain Java Unit Tests for Business Logic

No Azure runtime or Spring context required:

~~~java
OrderFunctionsApplication configuration =
        new OrderFunctionsApplication();

Function<String, OrderInput> parse =
        configuration.parseOrder();

Function<OrderInput, OrderDecision> classify =
        configuration.classifyOrder();

Function<OrderDecision, String> format =
        configuration.formatOrder();

String actual = format.apply(
        classify.apply(parse.apply(" dh-501 | 1500000 ")));

assertEquals("DH-501|PRIORITY|1500000", actual);
~~~

`assertEquals` comes from `org.junit.jupiter.api.Assertions`. This unit tests the **raw function beans**; it does not test the catalog wrapper's message conversion capabilities.

### 12.2. Spring Integration Test: Comparing Both Paths

Create `src/test/java/example/azure/DirectVsCatalogTest.java`:

~~~java
package example.azure;

import java.util.function.Function;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(classes = OrderFunctionsApplication.class)
class DirectVsCatalogTest {

    @Autowired
    @Qualifier("parseOrder")
    Function<String, OrderInput> parser;

    @Autowired
    @Qualifier("classifyOrder")
    Function<OrderInput, OrderDecision> classifier;

    @Autowired
    @Qualifier("formatOrder")
    Function<OrderDecision, String> formatter;

    @Autowired
    FunctionCatalog catalog;

    @Test
    void bothInvocationPathsGiveSameBusinessResult() {
        String input = " dh-501 | 1500000 ";

        String direct = formatter.apply(
                classifier.apply(parser.apply(input)));

        Function<String, String> fromCatalog =
                catalog.lookup(
                        "parseOrder|classifyOrder|formatOrder");

        assertNotNull(fromCatalog);
        String viaCatalog = fromCatalog.apply(input);

        assertEquals("DH-501|PRIORITY|1500000", direct);
        assertEquals(direct, viaCatalog);
    }

    @Test
    void catalogCanLookUpOneFunction() {
        Function<String, OrderInput> fromCatalog =
                catalog.lookup("parseOrder");

        assertNotNull(fromCatalog);

        OrderInput result =
                fromCatalog.apply(" dh-502 | 999999 ");

        assertEquals("DH-502", result.orderId());
        assertEquals(999_999L, result.totalVnd());
    }

    @Test
    void directValidationFailsForInvalidAmount() {
        assertThrows(IllegalArgumentException.class,
                () -> parser.apply("dh-503|abc"));
    }
}
~~~

`@SpringBootTest` confirms Spring instantiates all three beans, the catalog discovers them, and the catalog pipeline produces the expected result on typed payloads. To test cross-type conversion, test with real messages, content types, and converters for your version; do not treat a `String -> String` test as proof that every JSON schema works.

### 12.3. Testing Errors by Root Cause Without Assuming Wrapper Classes

~~~java
@Test
void catalogPathRejectsInvalidInput() {
    Function<String, String> pipeline =
            catalog.lookup(
                    "parseOrder|classifyOrder|formatOrder");

    assertNotNull(pipeline);

    RuntimeException exception = assertThrows(
            RuntimeException.class,
            () -> pipeline.apply("dh-503|abc"));

    Throwable root = exception;
    while (root.getCause() != null
            && root.getCause() != root) {
        root = root.getCause();
    }

    assertInstanceOf(IllegalArgumentException.class, root);
}
~~~

This is an **additional test** you can place into `DirectVsCatalogTest`, requiring a JUnit 5 version supporting `assertInstanceOf`. On older JUnit versions, use `assertTrue(root instanceof IllegalArgumentException)`.

### 12.4. Testing Handler Annotations and Host Integration

A Spring context test does not prove the Azure Host generated `function.json`. After Azure plugin packaging, verify **both** function names and routes:

| Test Layer | What to Verify |
| --- | --- |
| Java unit | Logic of each function, input validation, Java composition. |
| Spring context | Bean injection, catalog lookup, generic types, raw vs. wrapped behavior. |
| Azure package | `directBeanOrder` and `catalogOrder` have metadata/triggers. |
| Azure local Host | Both POST endpoints, HTTP statuses, bodies, error mapping. |
| Azure staging | Function keys/auth, Java runtime, cold starts, logs, scaling. |
| Event/Queue extensions | Retries/poison queues, idempotency, content types, and output bindings. |

### 12.5. Do Not Test Wrappers by Object Identity

Do not assert `assertSame(parser, catalog.lookup("parseOrder"))`. The catalog is designed to return a potentially instrumented representation; **behavior** and contracts matter more than preserving object identity.

## 13. Reusing the Same Functions in Queue or Timer Triggers

Using direct beans or the catalog does not bind a function to HTTP. An Azure handler can be invoked from an Azure Storage Queue and reuse the exact same pipeline:

~~~java
@FunctionName("catalogQueueOrder")
public void catalogQueueOrder(
        @QueueTrigger(
                name = "event",
                queueName = "orders-input",
                connection = "AzureWebJobsStorage")
        String rawOrder,

        @QueueOutput(
                name = "decision",
                queueName = "orders-decisions",
                connection = "AzureWebJobsStorage")
        OutputBinding<String> output,

        ExecutionContext context) {

    output.setValue(catalogPipeline.apply(rawOrder));
}
~~~

This is an **optional extension method** in `OrderAzureHandlers`. Requires imports:

~~~java
import com.microsoft.azure.functions.OutputBinding;
import com.microsoft.azure.functions.annotation.QueueOutput;
import com.microsoft.azure.functions.annotation.QueueTrigger;
~~~

Running it requires the Azure Storage Queue extension, connection settings, and source/target queues—not just Spring function beans. When a message is redelivered, both direct and catalog paths need **idempotency** if business logic causes side effects. `FunctionCatalog` does not configure acknowledgements, broker retries, or exactly-once semantics.

Similarly, an Azure `@TimerTrigger` can call `Supplier.get()` or `Function.apply(...)` at intervals governed by the **Azure schedule**. `@Bean Supplier` does not create a schedule automatically. Triggers/bindings belong to the Azure Host; business functions belong to Spring.

## 14. Azure Packaging and Required Configuration

### 14.1. Configuring the Spring Main Class

With Maven:

~~~xml
<properties>
    <java.version>17</java.version>
    <start-class>example.azure.OrderFunctionsApplication</start-class>
</properties>
~~~

You can set `MAIN_CLASS=example.azure.OrderFunctionsApplication` via Azure application settings/local settings when needed. A Spring Boot `main(...)` configures the application; it is **not** an Azure trigger entrypoint for an HTTP function.

### 14.2. Why Use the Azure Functions Plugin?

The Azure Maven/Gradle plugin processes Java annotations and builds Azure function metadata, package directories, and dependencies. **The default Spring Boot repackaged executable JAR is not the Azure package layout expected by the Java Worker**, so disable/adjust Boot repackaging.

Example Maven fragment:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <configuration>
                <skip>true</skip>
            </configuration>
        </plugin>
        <plugin>
            <groupId>com.microsoft.azure</groupId>
            <artifactId>azure-functions-maven-plugin</artifactId>
            <version>1.22.0</version>
            <configuration>
                <appName>orders-catalog-demo-unique</appName>
                <resourceGroup>orders-demo-rg</resourceGroup>
                <region>eastasia</region>
                <hostJson>src/main/resources/host.json</hostJson>
                <runtime>
                    <os>linux</os>
                    <javaVersion>17</javaVersion>
                </runtime>
                <appSettings>
                    <property>
                        <name>FUNCTIONS_EXTENSION_VERSION</name>
                        <value>~4</value>
                    </property>
                </appSettings>
            </configuration>
            <executions>
                <execution>
                    <id>package-functions</id>
                    <goals>
                        <goal>package</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
~~~

`1.22.0` is the reference plugin baseline in Spring Cloud Function Azure adapter guides, not a claim of being the latest release. Replace the Function App name, resource group, and region, and verify a compatible Azure hosting plan, Java runtime, and Spring Cloud release train. This is only a **`pom.xml` fragment** and requires proper dependency management.

### 14.3. host.json and local.settings.json

Minimal `src/main/resources/host.json`:

~~~json
{
  "version": "2.0"
}
~~~

Example `local.settings.json`:

~~~json
{
  "IsEncrypted": false,
  "Values": {
    "FUNCTIONS_WORKER_RUNTIME": "java",
    "FUNCTIONS_EXTENSION_VERSION": "~4",
    "MAIN_CLASS": "example.azure.OrderFunctionsApplication",
    "AzureWebJobsStorage": "UseDevelopmentStorage=true"
  }
}
~~~

`UseDevelopmentStorage=true` may require **Azurite** or a compatible emulator when the Host/triggers use Azure Storage. Never commit real secrets to the repository. In the cloud, use Azure Function App settings, managed identities/Key Vault, and proper connection policies.

### 14.4. Running Locally

~~~bash
./mvnw clean package
./mvnw azure-functions:run
~~~

Or with Gradle once the Azure Functions plugin is configured:

~~~bash
./gradlew azureFunctionsPackage
./gradlew azureFunctionsRun
~~~

After the host starts, both `directBeanOrder` and `catalogOrder` should appear. If one handler is missing, inspect Azure `@FunctionName`/`@HttpTrigger` and `function.json` rather than immediately blaming the SCF catalog.

This lesson **does not run build/deploy commands or modify Azure resources**. The commands above are instructional steps to try in a compatible project.

## 15. Diagnostic Table: Direct Bean vs. Catalog

| Symptom | Likely Cause | How to Investigate |
| --- | --- | --- |
| Direct bean fails to inject | Wrong `@Qualifier` or bean not registered/scanned. | Spring context logs, bean names, generic types. |
| Catalog lookup returns `null` | Wrong function definition name or bean ineligible for registration. | Check `@Bean` name, `ineligible-definitions`, and catalog tests. |
| Catalog has function but Azure Host misses endpoint | Azure discovery and Spring DI are separate mechanisms. | Check `@FunctionName`, trigger, plugin, and `function.json`. |
| Direct path works, catalog path fails | Composition, wrapper, conversion, or error propagation differs. | Test individual `lookup("name")` calls, composition, and root cause. |
| Catalog path works, direct path has type error | Handler passes raw payload with wrong generic type. | Add conversion/validation at the boundary. |
| HTTP 400 on direct, 500 on catalog | Wrapper may wrap validation exceptions. | Inspect root cause or use typed domain exceptions. |
| Mistyped name still resolves to the single function | Single-function fallback when catalog holds only one functional bean. | Disable fallback and test exact names when needed. |
| `ClassCastException` on JSON request | Wrong POJO/type conversion/content type. | Check payload deserializer and SCF conversion contract. |
| Lost `traceId` | Handler did not copy headers into a Spring Message, or adapter stripped them. | Check ingress mapping and function signature. |
| Multiple functions of same type fail to inject | Spring bean ambiguity. | Use `@Qualifier` or distinct bean names. |
| Both direct/catalog process Queue events twice | Retries/redelivery outside SCF's control. | Design idempotency keys and ACK/poison policies. |
| Spring tests PASS, Azure Worker fails | Runtime/packaging/main class/Java target mismatch. | Azure plugin output, `MAIN_CLASS`, library versions. |
| Slow context cold start | Many beans/starters, expensive lookup/initialization. | Profile startup, trim dependencies, cache fixed definitions. |
| Clients can invoke sensitive functions | Dynamic catalog lookup from external input. | Allowlist, authorization, auditing, and resource limits. |

## 16. Decision Checklist and Exercises

### 16.1. Invocation Style Checklist

- [ ] If there is only one stable function and the input is already typed, is a **direct bean** sufficient?
- [ ] If chaining multiple functions or reusing consistent definitions across adapters, is **`FunctionCatalog`** a better fit?
- [ ] Do the input/output signatures of all composition steps match?
- [ ] Does the Azure handler normalize the body into the expected Java type before invoking the function?
- [ ] Have you tested with real content types and `Message` headers if relying on conversion/wrappers?
- [ ] Does error mapping inspect root causes and separate validation from infrastructure errors?
- [ ] Are Azure Function names, HTTP routes, bean names, and catalog definitions clearly separated?
- [ ] Are fixed `FunctionCatalog` lookups resolved early and tested fail-fast?
- [ ] Have you prevented dynamic lookups controlled by untrusted callers?
- [ ] Are thread safety and idempotency ensured for events/redelivery?
- [ ] Does the Azure package contain metadata for the exact `@FunctionName` methods and compatible Java runtime?

### 16.2. Practice Exercises

1. **Compare outputs:** write tests comparing direct vs. catalog for orders at thresholds 999,999, 1,000,000, and 1,000,001 VND.
2. **Add step 4 function:** `Function<String,String> addPrefix` producing `ORD-...`; update `parseOrder|classifyOrder|formatOrder|addPrefix` and compare with Java `andThen`.
3. **Test wrong name:** change lookup to `parseOrder|missingFunction`, observe fail-fast behavior in the constructor, and fix it.
4. **Test single-function fallback:** build a test context with one function, look up a wrong name, then set `single-function-fallback-enabled=false`.
5. **Message-aware:** create a function accepting `Message<OrderInput>` and recording an audit entry with `correlationId`; test both direct Spring Message calls and catalog calls per contract.
6. **Type mismatch:** try passing `byte[]` to raw `Function<String,OrderInput>`, explain compiler/runtime behavior, and add an explicit converter.
7. **Test validation wrapper:** trigger a non-integer amount error, confirm HTTP 400 on both handlers or adjust the root-cause mapper.
8. **Test Queue Trigger:** invoke the catalog pipeline from a Queue trigger to Queue output, and define an event ID/idempotency key and poison queue policy.
9. **Analyze cold start:** measure context initialization time vs. function invocation time, separating Azure I/O cost from wrapper overhead.
10. **Inspect Azure package:** locate `function.json` metadata for both routes, proving that adding `@Bean Function` alone does not create Azure endpoints.

### 16.3. Self-Assessment

- How does a Spring-created `@Bean Function` differ from the function returned by `FunctionCatalog.lookup(...)`?
- Why does `@Qualifier` help inject a raw function without fixing a misspelled catalog definition?
- Why is `parseOrder|classifyOrder|formatOrder` a valid composition while another permutation causes a type mismatch?
- If both paths return the same `String`, can we conclude the two function objects are the exact same instance?
- Does the catalog wrapper automatically deserialize every JSON payload into any POJO? Why or why not?
- Who decides HTTP 400/500: the Azure Host or a raw Spring `Function`?
- Does a `@Bean` visible in the catalog automatically become an `@HttpTrigger`?
- Why should function names never be taken arbitrarily from query/header inputs?
- Why do both direct and catalog paths need idempotency with a Queue Trigger?
- When is keeping metadata in `Message<T>` better than injecting Azure `ExecutionContext` directly into domain objects?

## 17. Official References

- [Spring Cloud Function — Programming Model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html): raw beans vs. canonical wrappers, `FunctionCatalog`, composition, conversion, single-function fallback, reactive signatures, and routing.
- [Spring Cloud Function — Microsoft Azure Functions](https://docs.spring.io/spring-cloud-function/reference/adapters/azure-intro.html): direct bean invocation vs. `FunctionCatalog` in Azure handlers, `@Component`, Azure adapter, and packaging.
- [Microsoft Learn — Azure Functions Java Developer Guide](https://learn.microsoft.com/en-us/azure/azure-functions/functions-reference-java): `@FunctionName`, trigger/binding annotations, Java worker, and dependency injection.
- [Microsoft Learn — Azure HTTP Trigger](https://learn.microsoft.com/en-us/azure/azure-functions/functions-bindings-http-webhook-trigger): request bodies, routes, responses, authorization, and status handling.
- [Microsoft Learn — Azure Functions Core Tools](https://learn.microsoft.com/en-us/azure/azure-functions/functions-run-local): running the Azure Functions Host locally.
- [Microsoft Learn — Azure Functions Java CLI Quickstart](https://learn.microsoft.com/en-us/azure/azure-functions/create-first-function-cli-java): Azure Maven plugin, packaging, and deployment.
- [Microsoft Learn — Azure Storage Queue Trigger](https://learn.microsoft.com/en-us/azure/azure-functions/functions-bindings-storage-queue-trigger): retries, message redelivery, and poison queues.
- [Spring Cloud Function Samples](https://github.com/spring-cloud/spring-cloud-function/tree/main/spring-cloud-function-samples): sample Azure handlers invoking beans or the catalog.

**Conclusion:** **Direct bean invocation** uses the exact `Function<T,R>` implementation injected by Spring, fitting cases where dependencies and Java types are already clear. **Calling through `FunctionCatalog`** uses an SCF-wrapped representation, fitting **composition**, supported conversions/message-aware behaviors, and reusing function definitions across HTTP, event streams, and serverless runtimes. On Azure Functions, both approaches still pass through a **`@Component` handler**, a **`@FunctionName` method**, and **Azure triggers/bindings**; the catalog does not replace the transport layer. Choose based on your contract, test both paths, and handle errors, headers, security, and idempotency at the right boundaries.
