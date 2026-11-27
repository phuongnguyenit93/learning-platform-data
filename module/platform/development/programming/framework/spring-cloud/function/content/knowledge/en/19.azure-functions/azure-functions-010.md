# The Legacy FunctionInvoker Model and Version-Based Migration Guide

## 1. Why Understand the History of FunctionInvoker?

Spring Cloud Function (SCF) helps build reusable business logic through Java's functional interfaces `Supplier<T>`, `Function<T,R>`, and `Consumer<T>`. `FunctionCatalog` registers, normalizes, and looks up functions; adapters connect that same logic to HTTP, messaging, or serverless runtimes.

Azure Functions has its own programming model: Java handlers annotated with `@FunctionName` and trigger/binding annotations, invoked by the Azure Java Worker. Spring Cloud Function previously provided several base classes to connect Azure invocations to function beans. Over time, this model evolved:

- Early handler classes such as `AzureSpringBootRequestHandler` were replaced by `FunctionInvoker`.
- `FunctionInvoker` was later marked legacy/deprecated in current Azure adapter documentation.
- The currently recommended model uses Spring dependency injection with `@Component`/`@Service` handlers, and `FunctionCatalog` when executing functions under SCF conventions.
- `AzureFunctionUtil` helps attach Azure's `ExecutionContext` to `Message<T>` when a function needs invocation metadata.

This is a critical topic when maintaining Spring Cloud Function Azure projects: **simply swapping the superclass name does not complete a migration**. You must accurately identify the adapter generation, function definitions, message/header passing, output handling, and package/runtime configuration.

### After This Lesson, You Will Be Able To

1. Distinguish early Azure handlers, `FunctionInvoker`, and the current dependency injection model.
2. Understand `handleRequest`, `handleOutput`, and how the legacy invoker selects functions.
3. Understand what the SCF 3.1, 3.2, 4.x, and 5.x version milestones mean.
4. Migrate a handler extending `FunctionInvoker` into a Spring bean with constructor injection.
5. Use `FunctionCatalog.lookup(...)` with explicit function names or compositions.
6. Pass `ExecutionContext` and HTTP headers into `Message<T>` properly.
7. Preserve HTTP/Queue/Timer trigger contracts during migration.
8. Plan dependency alignment, packaging, testing, and safe rollouts.

## 2. Three Azure Integration Generations to Distinguish

### 2.1. First Generation: AzureSpringBootRequestHandler

In SCF 3.1.x documentation, the common pattern was extending an adapter base handler. Two familiar class names:

- `org.springframework.cloud.function.adapter.azure.AzureSpringBootRequestHandler`.
- `org.springframework.cloud.function.adapter.azure.AzureSpringBootHttpRequestHandler`.

These classes relied on SCF's initializer/context infrastructure to bootstrap Spring and route Azure requests to functions. For HTTP, `AzureSpringBootHttpRequestHandler<I>` specifically handled `HttpRequestMessage<I>` and `HttpResponseMessage`.

SCF 3.1.5 Javadoc marked `AzureSpringBootRequestHandler` and `AzureSpringBootHttpRequestHandler` deprecated as of **3.2**, replaced by `FunctionInvoker`. Code extending those classes indicates first-generation integration.

### 2.2. Middle Generation: FunctionInvoker

Starting in SCF 3.2, `FunctionInvoker<I,O>` became the documented base class replacing earlier handlers. Azure handlers extended it, built a `Message` if needed, and called `handleRequest(...)`:

~~~java
public class UppercaseHandler
        extends FunctionInvoker<Message<String>, String> {

    @FunctionName("uppercase")
    public String execute(
            @HttpTrigger(
                    name = "req",
                    methods = {HttpMethod.GET, HttpMethod.POST},
                    authLevel = AuthorizationLevel.ANONYMOUS)
            HttpRequestMessage<Optional<String>> request,
            ExecutionContext context) {

        Message<String> message =
                MessageBuilder.withPayload(
                        request.getBody().orElse(""))
                    .copyHeaders(request.getHeaders())
                    .build();

        return handleRequest(message, context);
    }
}
~~~

The business function was declared in the Spring context:

~~~java
@Bean
public Function<String, String> uppercase() {
    return value -> value.toUpperCase(Locale.ROOT);
}
~~~

Or a function directly accepting a message:

~~~java
@Bean
public Function<Message<String>, String> uppercase() {
    return message ->
            message.getPayload().toUpperCase(Locale.ROOT);
}
~~~

`FunctionInvoker` provided two common methods:

- `handleRequest(input, context)`: dispatches the invocation to the corresponding SCF function.
- `handleOutput(output)`: formats output per the legacy adapter's conventions.

Legacy documentation explained that the function definition name was derived from `ExecutionContext.getFunctionName()`. Thus, the Azure function name and the SCF function definition were implicitly coupled. While convenient in older apps, that coupling must be handled explicitly during migration.

### 2.3. Current Generation: Dependency Injection + FunctionCatalog

Current Azure adapter documentation instructs:

- Add the `spring-cloud-function-adapter-azure` dependency.
- Annotate classes holding Azure handler methods with `@Component` or `@Service`.
- Let the Azure Java Worker invoke methods annotated with `@FunctionName`.
- Let Spring inject services, beans, or `FunctionCatalog` into the handler.
- Use `FunctionCatalog` to obtain canonical SCF functions and compositions.
- Use `AzureFunctionUtil.enhanceInputIfNecessary(...)` if Azure `ExecutionContext` is needed in message headers.

Example structure:

~~~text
Azure Functions Host
        |
        v
Java Worker
        |
        v
@Component OrderAzureHandler
        |
        +---- FunctionCatalog.lookup("normalizeOrder")
        |                  |
        |                  v
        |             SCF function bean
        |
        +---- AzureFunctionUtil (when ExecutionContext is needed)
~~~

The handler no longer extends `FunctionInvoker`. It is an ordinary Spring bean, while Azure annotations describe triggers/bindings so the Azure plugin generates metadata.

If the application is genuinely a Spring MVC/WebFlux web app needing only an HTTP trigger, evaluate `spring-cloud-function-adapter-azure-web` separately. It is a specialized web adapter, not a new name for `FunctionInvoker`; for HTTP/Queue/Blob/Timer handlers needing Azure annotations and bindings directly, use the generic Azure adapter.

## 3. Version Map and Support Status

The following table summarizes milestones recorded in official documentation and Javadoc:

| SCF Line | Common Azure Model | Status / Direction |
| --- | --- | --- |
| 3.1.x | `AzureSpringBootRequestHandler` / `AzureSpringBootHttpRequestHandler` | First-generation model; these classes were deprecated in 3.2. |
| 3.2.x | `FunctionInvoker` / `HttpFunctionInvoker` | Documented replacement for the older base handlers; Javadoc marks first-gen handlers deprecated since 3.2. |
| 4.0.x | Azure adapter with dependency injection; `FunctionInvoker` still present in legacy docs | Adapter requires 4.0.0+ to enable Azure Java Worker integration; docs steer users toward `@Component` and `FunctionCatalog`. |
| 4.1–4.3.x | Dependency injection + Azure handler annotations | New model is primary guidance; `FunctionInvoker` is marked deprecated. |
| 5.0.x | Dependency injection + Azure handler annotations | Current docs still mark legacy `FunctionInvoker` deprecated and recommend the new integration. |

At the time of writing, current Spring Cloud Function documentation reflects the stable 5.0.x line. Choose adapter versions via your project's Spring Cloud BOM/release train; never mix a 5.x adapter with older context modules.

**What to understand about 4.0.0+:** documentation requires `spring-cloud-function-adapter-azure` 4.0.0 or later to enable Azure Java Worker integration. That does not mean `FunctionInvoker` was immediately deleted in 4.0.0. Both 4.x and 5.x docs retain legacy/deprecated sections. Spring does not announce a specific removal version for this class in the guide; treat deprecation as a signal to plan replacement rather than guessing a removal date.

### 3.1. Never Infer Versions from Class Names Alone

Some projects keep legacy code while upgrading the Spring Cloud BOM, or pull in multiple adapter dependencies transitively. Before changing code, verify:

- The actual resolved version of `spring-cloud-function-adapter-azure`.
- The version of `spring-cloud-function-context` and related SCF modules.
- The Spring Boot version and Spring Cloud release train.
- The Java target/runtime.
- The Azure Functions runtime and Azure Java library.
- The Maven/Gradle plugin building the package.

Inspect the dependency tree instead of only reading direct declarations:

~~~bash
./mvnw dependency:tree -Dincludes=org.springframework.cloud
~~~

With Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

These commands reveal whether the adapter and context modules resolved to mismatched versions.

## 4. How the Legacy FunctionInvoker Worked

### 4.1. Azure Handler as a Bridge

In the legacy model, the handler class extended `FunctionInvoker<Message<String>, String>`. The Azure Host called the `@FunctionName` method, which:

1. Received the Azure request and `ExecutionContext`.
2. Read the payload.
3. Constructed a `Message<String>`.
4. Optionally copied HTTP headers onto the message.
5. Called `handleRequest(message, context)`.
6. Returned output to the Azure runtime.

`FunctionInvoker` handled part of bridging the Spring function context to the Azure invocation.

### 4.2. Function Name Selected Implicitly

The legacy model used `ExecutionContext.getFunctionName()` to locate the function definition. Example:

~~~java
@FunctionName("uppercase")
public String execute(...) {
    return handleRequest(message, context);
}
~~~

If an SCF bean was registered under the name `uppercase`, function selection happened automatically based on the Azure function name.

This created an implicit convention:

~~~text
@FunctionName("uppercase")
        |
        v
ExecutionContext.getFunctionName()
        |
        v
FunctionInvoker selects definition "uppercase"
        |
        v
FunctionCatalog / SCF function
~~~

Renaming the Azure function without renaming the bean—or renaming the bean without updating the Azure function name—caused the application to look up the wrong function. During migration to the new model, make both names explicit.

### 4.3. handleRequest and handleOutput Are Not Business Logic

`handleRequest` and `handleOutput` are APIs of the legacy adapter base class. They are neither `Function<T,R>` methods nor Azure Java Worker APIs.

When migrating to dependency-injected handlers:

- The handler is responsible for calling the appropriate function or service.
- The handler converts the result into the output type required by the Azure binding.
- For HTTP, the handler can build `HttpResponseMessage`.
- For Queue/Blob/Service Bus outputs, use the corresponding output binding annotations/types.
- Never keep calls to `handleRequest` or `handleOutput` in a class that no longer extends `FunctionInvoker`.

## 5. FunctionCatalog in the New Model

### 5.1. Spring Beans and SCF Functions Are Distinct Concepts

Spring can inject a `Function<String,String>` bean directly into a handler. That invokes the raw Java bean directly, whereas if you need SCF's normalized features such as type conversion, composition, and canonical function wrappers, look it up via `FunctionCatalog`.

Example:

~~~java
@Bean
Function<String, String> normalizeOrder() {
    return value -> value.strip().toUpperCase(Locale.ROOT);
}

@Bean
Function<String, String> addPrefix() {
    return value -> "REF-" + value;
}
~~~

Inside the Azure handler:

~~~java
Function<Object, Object> pipeline =
        functionCatalog.lookup("normalizeOrder|addPrefix");
Object result = pipeline.apply(input);
~~~

`FunctionCatalog.lookup(...)` returns an SCF-instrumented/wrapped function. Use SCF function bean names and composition syntax—never substitute Azure route names unless they happen to match by coincidence.

### 5.2. Function Name vs. Azure Function Name

| Name | Belongs To | Example |
| --- | --- | --- |
| `normalizeOrder` | Spring bean / SCF function | `@Bean normalizeOrder()` method |
| `addPrefix` | Spring bean / SCF function | `@Bean addPrefix()` method |
| `normalizeOrder|addPrefix` | SCF composition definition | Two functions executed sequentially |
| `normalizeAzureOrder` | Azure Function name | `@FunctionName("normalizeAzureOrder")` |
| `orders/normalize` | HTTP route | `route = "orders/normalize"` |

The new model makes this relationship explicit: Azure invokes the handler by its Azure function name/trigger; inside the handler, the application explicitly looks up the desired function definition.

### 5.3. Why Explicit Lookup?

Explicit lookup offers clear advantages:

- No requirement for the Azure function name to match the bean name.
- Easy to reuse one function across multiple Azure handlers.
- Easy to invoke compositions without creating extra wrapper beans.
- Easy to test function definitions independently of Azure triggers.
- Renaming a route/handler leaves the business function intact.

If a catalog lookup returns null, fail fast when constructing the handler or during startup tests rather than waiting for the first production request to uncover a typo.

## 6. Complete Migration Example: HTTP Uppercase

### 6.1. Reusable Business Functions

Define two function beans in a Spring configuration:

~~~java
package example.azure;

import java.util.Locale;
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class TextFunctions {

    @Bean
    public Function<String, String> normalizeText() {
        return value -> {
            if (value == null || value.isBlank()) {
                throw new IllegalArgumentException("Input is empty");
            }
            return value.strip().toUpperCase(Locale.ROOT);
        };
    }

    @Bean
    public Function<String, String> addReferencePrefix() {
        return value -> "REF-" + value;
    }
}
~~~

These beans have no Azure SDK imports. They can be called from an Azure handler, another HTTP adapter, or unit tests.

### 6.2. New Dependency-Injected Handler

~~~java
package example.azure;

import java.util.Optional;
import java.util.Objects;
import java.util.function.Function;

import com.microsoft.azure.functions.ExecutionContext;
import com.microsoft.azure.functions.HttpRequestMessage;
import com.microsoft.azure.functions.HttpResponseMessage;
import com.microsoft.azure.functions.HttpStatus;
import com.microsoft.azure.functions.annotation.AuthorizationLevel;
import com.microsoft.azure.functions.annotation.FunctionName;
import com.microsoft.azure.functions.annotation.HttpTrigger;
import com.microsoft.azure.functions.HttpMethod;

import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.stereotype.Component;

@Component
public class OrderAzureHandler {

    private final Function<Object, Object> pipeline;

    public OrderAzureHandler(FunctionCatalog functionCatalog) {
        this.pipeline = Objects.requireNonNull(
                functionCatalog.lookup("normalizeText|addReferencePrefix"));
    }

    @FunctionName("normalizeAzureOrder")
    public HttpResponseMessage normalize(
            @HttpTrigger(
                    name = "request",
                    methods = {HttpMethod.POST},
                    authLevel = AuthorizationLevel.FUNCTION,
                    route = "orders/normalize")
            HttpRequestMessage<Optional<String>> request,
            ExecutionContext context) {

        String input = request.getBody().orElse("");

        if (input.isBlank()) {
            return request
                    .createResponseBuilder(HttpStatus.BAD_REQUEST)
                    .body("Order code must not be blank")
                    .build();
        }

        try {
            Object result = pipeline.apply(input);

            context.getLogger().info(
                    "Order normalized: " + context.getInvocationId());

            return request
                    .createResponseBuilder(HttpStatus.OK)
                    .header("Content-Type", "text/plain; charset=utf-8")
                    .body(result)
                    .build();
        }
        catch (IllegalArgumentException invalidInput) {
            return request
                    .createResponseBuilder(HttpStatus.BAD_REQUEST)
                    .body(invalidInput.getMessage())
                    .build();
        }
    }
}
~~~

For input `" dh-901 "`, the output is `REF-DH-901`. The Azure function name is `normalizeAzureOrder`, while the SCF composition is `normalizeText|addReferencePrefix`. Both names are clearly separated.

This illustrative handler focuses on the migration flow. In real applications, add domain error mapping, sensitive-data-safe logging, timeouts, and API output contracts.

### 6.3. Key Differences from FunctionInvoker

| Legacy | New Model |
| --- | --- |
| `extends FunctionInvoker<Message<String>, String>` | `@Component` / `@Service` |
| Calls `handleRequest(message, context)` | Calls `functionCatalog.lookup("...").apply(input)` |
| Function definition derived from Azure function name | Function definition specified explicitly |
| Base class manages most dispatching | Handler owns request/output mapping |
| Legacy header convention | `AzureFunctionUtil.EXECUTION_CONTEXT` when Azure context is needed in `Message` |

## 7. Migrating ExecutionContext and Message Headers

### 7.1. Legacy FunctionInvoker Attached Context Automatically

The legacy model attached Azure `ExecutionContext` to a Message header under key `executionContext`. A function taking `Message<T>` could read that header:

~~~java
import java.util.Locale;
import java.util.function.Function;

import com.microsoft.azure.functions.ExecutionContext;
import org.springframework.messaging.Message;

@Bean
public Function<Message<String>, String> uppercase() {
    return message -> {
        String payload = message.getPayload();

        ExecutionContext context =
                (ExecutionContext) message.getHeaders()
                        .get("executionContext");

        if (context != null) {
            context.getLogger().info("Processing message");
        }

        return payload.toUpperCase(Locale.ROOT);
    };
}
~~~

This snippet reflects how legacy samples accessed the header. During migration, avoid scattering literal `"executionContext"` strings across business code.

### 7.2. New Model Uses AzureFunctionUtil

The current Azure adapter provides:

~~~java
AzureFunctionUtil.enhanceInputIfNecessary(input, context)
~~~

This helper attaches the `ExecutionContext` instance to a Spring `Message` header under key:

~~~java
AzureFunctionUtil.EXECUTION_CONTEXT
~~~

Example:

~~~java
import java.util.function.Function;

import com.microsoft.azure.functions.ExecutionContext;
import org.springframework.cloud.function.adapter.azure.AzureFunctionUtil;
import org.springframework.messaging.Message;

String payload = request.getBody().orElse("");

Message<?> message = (Message<?>)
        AzureFunctionUtil.enhanceInputIfNecessary(
                payload, context);

Function<Object, Object> uppercaseWithContext =
        functionCatalog.lookup("uppercaseWithContext");
Object result = uppercaseWithContext.apply(message);
~~~

The function bean can read metadata:

~~~java
import java.util.Locale;
import java.util.function.Function;

import com.microsoft.azure.functions.ExecutionContext;
import org.springframework.cloud.function.adapter.azure.AzureFunctionUtil;
import org.springframework.messaging.Message;

@Bean
public Function<Message<String>, String> uppercaseWithContext() {
    return message -> {
        String payload = message.getPayload();

        Object value = message.getHeaders().get(
                AzureFunctionUtil.EXECUTION_CONTEXT);

        if (value instanceof ExecutionContext context) {
            context.getLogger().info("Uppercase function invoked");
        }

        return payload.toUpperCase(Locale.ROOT);
    };
}
~~~

If the function only needs the payload, keep the `Function<String,String>` signature and log in the Azure handler. Use `Message<T>` only when metadata or headers are required; do not force every business function to depend on the Azure runtime.

### 7.3. HTTP Headers Do Not Automatically Equal Azure Context

Legacy samples often copied HTTP headers into the `Message`:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<String> message =
        MessageBuilder.withPayload(payload)
                .copyHeaders(request.getHeaders())
                .build();
~~~

`AzureFunctionUtil.enhanceInputIfNecessary` handles attaching `ExecutionContext`. When migrating, do not assume this helper copies all HTTP headers under the old policy. If business logic needs correlation IDs or tenant metadata, selectively map them explicitly:

~~~java
import org.springframework.cloud.function.adapter.azure.AzureFunctionUtil;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<String> input = MessageBuilder.withPayload(payload)
        .setHeader("correlationId",
                request.getHeaders().get("x-correlation-id"))
        .build();

Message<?> enriched = (Message<?>)
        AzureFunctionUtil.enhanceInputIfNecessary(input, context);
~~~

Never copy all headers blindly: HTTP headers can contain authorization tokens, cookies, function keys, or sensitive data. Forward only allowlisted and validated headers.

### 7.4. Never Store ExecutionContext in Singleton State

Azure handler beans are typically Spring singletons. Never keep invocation context in a mutable field:

~~~java
// Avoid this
private ExecutionContext currentContext;
~~~

Concurrent invocations can overwrite one another's context. Pass context via method parameters or the invocation's own message; never store it in static fields, shared caches, or message brokers.

## 8. Converting HTTP Input/Output

### 8.1. Legacy Handlers Could Return Payloads Directly

The legacy `FunctionInvoker` let handlers call `handleRequest` and return business values directly. When moving to DI, the handler takes clearer responsibility for Azure output types.

Example:

~~~java
@FunctionName("normalizeAzureOrder")
public HttpResponseMessage normalize(
        @HttpTrigger(
                name = "request",
                methods = {HttpMethod.POST},
                authLevel = AuthorizationLevel.FUNCTION,
                route = "orders/normalize")
        HttpRequestMessage<Optional<String>> request,
        ExecutionContext context) {
    Function<Object, Object> normalizeText =
            functionCatalog.lookup("normalizeText");
    String result = (String) normalizeText.apply(
            request.getBody().orElse(""));
    return request.createResponseBuilder(HttpStatus.OK)
            .body(result)
            .build();
}
~~~

With an HTTP Trigger, returning `HttpResponseMessage` gives full control over status, headers, and body. Other output types also work where bindings and contracts permit; preserve legacy response semantics during migration.

### 8.2. Error Mapping Must Be Preserved

Build a comparison table before editing code:

| Scenario | Legacy Contract | Verify in New Handler |
| --- | --- | --- |
| Empty body | Exception or 400 depending on code | Consistent 400 status and message |
| Invalid input | Error mapped by function/adapter | Do not turn validation errors into accidental 500s |
| Business exception | Legacy handler behavior | Domain-appropriate HTTP 4xx/5xx |
| Downstream timeout | Adapter/host behavior | Timeout status and retry policy |
| Null output | Possibly serialized differently by legacy adapter | Azure response/output binding matches contract |
| Content-Type header | Possibly handled by legacy converter | Preserve content type and JSON shape |

Never assume `handleOutput` can simply be removed without testing. Compare JSON output, encoding, status codes, and headers between old and new implementations.

### 8.3. Non-HTTP Triggers

For Queue, Blob, Timer, Event Hubs, or Service Bus triggers, Azure annotations stay on the handler. Migration changes how SCF functions are invoked, not the trigger contract:

- `@QueueTrigger` continues defining queue name and connection.
- `@BlobTrigger` continues defining container/path.
- `@TimerTrigger` continues defining the schedule.
- Output bindings continue using the matching Azure types/annotations.

The new handler calls `FunctionCatalog` and maps results to output bindings. Never convert every trigger to HTTP just to reuse sample code.

## 9. Common Migration Pitfalls

| Symptom | Common Cause | Remediation |
| --- | --- | --- |
| Azure Host does not see function | Handler no longer discovered or missing `@FunctionName` | Keep `public` methods, annotations, and package metadata. |
| Spring fails to inject handler | New class missing `@Component`/`@Service` or outside component scan | Check root package and Spring main class. |
| Catalog lookup returns null | Used Azure function name instead of bean name; typo or unregistered bean | Check `@Bean` method names and lookup definitions. |
| Composition failure | Wrong order or mismatched output/input types | Check each function and the `a|b` composition. |
| Output changed | Removed `handleOutput` without re-mapping HTTP/binding responses | Compare status, body, headers, and serialization. |
| Function does not see headers | Signature accepts payload instead of `Message<T>` | Use `Message<T>` when metadata is genuinely needed. |
| Missing Azure logger | Reading legacy literal header or forgot to call new helper | Use `AzureFunctionUtil.enhanceInputIfNecessary` and constant. |
| Request headers disappeared | Did not copy allowlisted headers after removing legacy `MessageBuilder` | Map correlation/tenant headers explicitly. |
| App invokes wrong function | Legacy relied on `getFunctionName()`; new code looks up wrong name | Separate Azure function name from SCF function definition. |
| Context starts repeatedly | Manually calling `SpringApplication.run` on every invocation | Let the adapter bootstrap the context and inject beans. |
| `ClassNotFoundException` after upgrade | BOM / adapter / context dependency mismatch | Check dependency tree and release train. |
| Azure package fails discovery | Wrong JAR layout/Boot repackage or plugin staging | Check `function.json`, `host.json`, manifest, and package layout. |
| Spring tests pass, Host fails | Unit/context tests do not run the Azure Java Worker | Run Core Tools integration tests and verify discovery. |

### 9.1. Do Not Look for a Helper/Initializer Class Replacing FunctionInvoker

The name `FunctionInvoker` appears in many legacy guides, but do not assume a stable public class named `FunctionInvokerHelper` or `FunctionInvokerInitializer` exists across all Azure adapter versions. Check the exact package/API for your version in Javadoc and actual dependencies. The current model relies on Spring components, Azure handler annotations, `FunctionCatalog`, and specifically `AzureFunctionUtil`.

## 10. Step-by-Step Migration Plan

### Step 1: Inventory Existing Handlers

Search the source tree:

~~~bash
rg -n "FunctionInvoker|AzureSpringBootRequestHandler|AzureSpringBootHttpRequestHandler|handleRequest|handleOutput" src
~~~

For each handler, record:

- Azure function name.
- Triggers and bindings.
- Function definition selected by the legacy invoker.
- Input/output types.
- Copied headers.
- Error, status, and serialization behavior.
- Whether `ExecutionContext` is read.

### Step 2: Verify Dependencies and Versions

- Choose a Spring Cloud release train compatible with your Spring Boot version.
- Use a BOM to manage all SCF modules in sync.
- Upgrade `spring-cloud-function-adapter-azure` to the 4.0.0+ line when adopting the current Azure Java Worker model.
- Verify the Azure Java Functions library and Maven/Gradle plugin.
- Never upgrade only the adapter while pinning SCF context modules to older versions via explicit overrides.

### Step 3: Separate Business Logic from Azure Handlers

Keep function beans or services in plain Java. Never move business rules into `@FunctionName` methods if the goal is reuse across adapters.

If a business function accepts `Message<T>` solely for Azure context, consider splitting it into:
- A domain function taking the payload/domain object.
- An adapter handler handling `ExecutionContext`, logging, and correlation.
- A message-aware wrapper only where metadata is genuinely needed.

### Step 4: Convert Handlers to Spring Components

- Remove `extends FunctionInvoker<...>`.
- Add `@Component` or `@Service`.
- Use constructor injection for services and the catalog.
- Keep `@FunctionName` and trigger/binding annotations.
- Keep the `public` method signature required for Azure plugin scanning.

### Step 5: Replace Implicit Dispatch with Explicit Lookup

Replace:

~~~java
return handleRequest(message, context);
~~~

with:

~~~java
import java.util.function.Function;

Function<Object, Object> pipeline =
        functionCatalog.lookup("normalizeText|addReferencePrefix");
Object result = pipeline.apply(input);
~~~

Use the exact bean names/SCF definition. If only calling a plain Java service, you can inject the service directly; if needing type conversion, composition, or canonical SCF wrappers, use `FunctionCatalog`.

### Step 6: Migrate Header Propagation

- Identify which headers the function actually uses.
- For Azure context, call `AzureFunctionUtil.enhanceInputIfNecessary(input, context)`.
- Read the header with `AzureFunctionUtil.EXECUTION_CONTEXT`.
- Map correlation ID/tenant metadata using an allowlist.
- Drop legacy headers that are no longer used.

### Step 7: Re-Map Outputs and Errors

Recreate the corresponding HTTP response or output binding. Test status codes, bodies, content types, null outputs, error mapping, and retry behavior.

### Step 8: Build/Package and Inspect Metadata

- Verify main class and `MAIN_CLASS`.
- Verify the Maven/Gradle Azure plugin.
- Confirm `function.json` points to the right handler.
- Inspect JAR layout, dependencies, and `host.json`.
- Avoid the default Spring Boot fat JAR if incompatible with Azure packaging.

### Step 9: Run Parallel Testing and Release

Run unit tests, Spring context tests, and the local Azure Host. Deploy to staging, send identical test vectors to old/new versions when feasible, and compare outputs. Promote only after triggers, auth, logs, and downstream integrations are verified.

## 11. Post-Migration Testing

### 11.1. Unit Testing Business Functions

~~~java
@Test
void normalizesAndAddsPrefix() {
    String normalized = " dh-901 ".strip().toUpperCase(Locale.ROOT);
    String output = "REF-" + normalized;
    assertEquals("REF-DH-901", output);
}
~~~

In real projects, test the service/function bean directly rather than duplicating production logic inside tests as in this minimal example.

### 11.2. Spring Context and FunctionCatalog

~~~java
import java.util.function.Function;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
class AzureFunctionMigrationTest {

    @Autowired
    FunctionCatalog catalog;

    @Test
    void migratedCompositionIsRegistered() {
        Function<Object, Object> pipeline =
                catalog.lookup("normalizeText|addReferencePrefix");
        assertNotNull(pipeline);

        Object result = pipeline.apply(" dh-901 ");

        assertEquals("REF-DH-901", result);
    }
}
~~~

This test verifies the Spring context and SCF catalog. It does not start the Azure Functions Host.

### 11.3. Azure Host Integration Testing

Use local Azure Functions Core Tools to confirm:

- The Host discovers the exact function names.
- HTTP methods, routes, and auth levels are accurate.
- The Java worker and Spring context initialize cleanly.
- Invocations return expected statuses, bodies, and headers.
- Queue/Blob/Timer triggers run per their binding contracts.
- Logs and `ExecutionContext` attach to the right invocations.
- No duplicate function names collide during side-by-side migration.

### 11.4. Regression Test Matrix

| Category | Test Cases |
| --- | --- |
| Payload | Blank strings, Unicode, JSON objects, large payloads |
| Message | `Content-Type`, correlation IDs, allowlisted headers |
| Context | `ExecutionContext` header present/absent, invocation IDs |
| Function selection | Bean names, compositions, Azure function name distinct from bean name |
| HTTP | GET/POST, 200/400/401/403/500, response headers |
| Output | Strings, JSON, null, `OutputBinding` |
| Trigger | Queue redelivery, Blob events, Timer schedules |
| Failure | Validation errors, downstream timeouts, dependency outages |
| Concurrency | Concurrent invocations without context cross-talk |
| Packaging | `function.json`, main class, classpath, Java runtime |

## 12. Release and Rollback Strategy

You do not need to migrate every handler in one big-bang release if an app has many triggers.

You can migrate in batches:

1. Pick one simple HTTP function as a pilot.
2. Convert the handler to dependency injection and `FunctionCatalog`.
3. Run regression tests against the same test vectors.
4. Deploy to a staging Function App or slot supported by your hosting plan.
5. Compare telemetry, latency, error rates, and trigger discovery.
6. Migrate remaining triggers/handlers incrementally.
7. Delete legacy code once all callers and deployment packages are verified.

Never keep two handlers with the same `@FunctionName` inside one Function App. To compare old and new side by side, use a separate staging Function App or distinct Azure function names, and avoid consuming the same production queue/topic.

Rollbacks must revert both the artifact and matching dependency configs. Never revert Java source alone if the pipeline also changed the BOM, Java runtime, function metadata, or settings.

## 13. Migration Checklist

- [ ] Identified the legacy generation accurately: `AzureSpringBootRequestHandler` or `FunctionInvoker`.
- [ ] Documented which function definitions the legacy invoker selected implicitly.
- [ ] Mapped Spring bean names and Azure function names clearly.
- [ ] Aligned Spring Boot, Spring Cloud BOM, and SCF adapter versions.
- [ ] New handler is annotated with `@Component`/`@Service`.
- [ ] Constructor injection replaces the legacy base class.
- [ ] `FunctionCatalog` lookups use explicit names/compositions.
- [ ] `ExecutionContext` is passed via `AzureFunctionUtil` when needed.
- [ ] HTTP headers are allowlisted instead of blindly copied.
- [ ] Output and error mapping preserve existing contracts.
- [ ] `function.json` and the package layout are regenerated.
- [ ] Unit, Spring context, and Azure Host tests all pass.
- [ ] Staging smoke tests and rollback artifacts are ready.
- [ ] No duplicate-named or unmigrated legacy handlers remain.

## 14. Self-Assessment Questions

- Why was `AzureSpringBootRequestHandler` replaced starting in SCF 3.2?
- How does `FunctionInvoker` differ from `AzureSpringBootRequestHandler`?
- Why does `FunctionInvoker` still appear in 4.x documentation while marked legacy/deprecated?
- What is the significance of SCF adapter 4.0.0+ for Azure Java Worker integration?
- Which class do `handleRequest` and `handleOutput` belong to?
- How did legacy `FunctionInvoker` use `ExecutionContext.getFunctionName()` to select functions?
- In the new model, must an Azure function name match an SCF bean name?
- When should you inject a bean directly vs. using `FunctionCatalog`?
- What problem does `AzureFunctionUtil.EXECUTION_CONTEXT` solve?
- Why should you avoid copying all HTTP headers into a `Message`?
- What responsibilities does a new handler have regarding HTTP statuses and output bindings?
- Why isn't a Spring context test enough to confirm Azure Host integration?
- How should you roll back when both the dependency BOM and function metadata changed?

## 15. Official References

- [Spring Cloud Function — Microsoft Azure Functions, current reference](https://docs.spring.io/spring-cloud-function/reference/adapters/azure-intro.html): current dependency injection model, `FunctionCatalog`, `AzureFunctionUtil`, and `FunctionInvoker` deprecation notice.
- [Spring Cloud Function 4.3 — Azure adapter reference](https://docs.spring.io/spring-cloud-function/reference/4.3/adapters/azure-intro.html): Azure adapter guide and deprecated `FunctionInvoker` section.
- [Spring Cloud Function 4.0.4 — Reference guide](https://docs.spring.io/spring-cloud-function/docs/4.0.4/reference/html/spring-cloud-function.html): `FunctionInvoker` history and SCF programming model.
- [Spring Cloud Function 3.2.5 — Azure reference](https://docs.spring.io/spring-cloud-function/docs/3.2.5/reference/html/azure.html): 3.2-era `FunctionInvoker` model.
- [Javadoc 3.2.7 — Deprecated API](https://javadoc.io/static/org.springframework.cloud/spring-cloud-function-adapter-azure/3.2.7/deprecated-list.html): `AzureSpringBootRequestHandler` and `AzureSpringBootHttpRequestHandler` deprecated since 3.2.
- [Javadoc 4.0.2 — HttpFunctionInvoker](https://javadoc.io/static/org.springframework.cloud/spring-cloud-function-adapter-azure/4.0.2/org/springframework/cloud/function/adapter/azure/HttpFunctionInvoker.html): HTTP invoker class from the `FunctionInvoker` generation.
- [Spring Cloud Function Azure sample — Legacy FunctionInvoker and current samples](https://github.com/spring-cloud/spring-cloud-function/tree/main/spring-cloud-function-samples/function-sample-azure): legacy example and links to dependency-injection adapter samples.
- [Spring Cloud Function — Programming Model and FunctionCatalog](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html): function registration, lookup, canonical wrappers, and composition.
- [Spring Cloud Function for Azure Function — Spring Blog](https://spring.io/blog/2023/02/24/spring-cloud-function-for-azure-function/): introduction to the Azure adapter and background on using SCF with Azure.

**Conclusion:** Spring Cloud Function's Azure integration evolved through three generations: early `AzureSpringBootRequestHandler` classes, `FunctionInvoker` starting in SCF 3.2, and the current dependency injection model. Current Spring documentation marks `FunctionInvoker` legacy/deprecated and steers developers toward `@Component`/`@Service` handlers, `FunctionCatalog`, and `AzureFunctionUtil` when message metadata is needed. During migration, align dependencies to your release train, separate Azure function names from SCF function definitions, preserve HTTP/trigger output contracts, audit headers/context handling, and verify packages against the Azure Host before releasing.
