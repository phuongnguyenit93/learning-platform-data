# Accessing ExecutionContext via AzureFunctionUtil

## 1. Problem and Objectives

**Spring Cloud Function (SCF)** encourages writing business functions with `Supplier<T>`, `Function<T,R>`, and `Consumer<T>`, looking them up via `FunctionCatalog`, and composing (*composition*) them to reuse the same logic when invoked over HTTP, events, or a serverless platform. In the **SPRING_CLOUD_FUNCTION** module, it is important **not to tightly couple business rules to the invocation protocol**.

When deploying such an application to **Azure Functions**, each invocation provides an Azure Java runtime object: `com.microsoft.azure.functions.ExecutionContext`. This object supplies the **invocation ID**, **function name**, **logger**, and trace information. However, a Spring bean like `Function<String,String>` does not automatically receive an `ExecutionContext` parameter like an Azure `@FunctionName` handler does.

To bridge the two worlds, the Spring Cloud Function Azure adapter provides the utility **`AzureFunctionUtil.enhanceInputIfNecessary(input, context)`**. This utility attaches the invocation's `ExecutionContext` to a **header** on a Spring `Message<T>`, enabling a function with signature `Function<Message<T>,R>` to read the context when needed.

This lesson focuses on the following questions:

1. What is `ExecutionContext`, and how does it differ from an HTTP request, Spring `ApplicationContext`, and `FunctionCatalog`?
2. Why should you never inject `ExecutionContext` as a Spring singleton or store it in a handler field?
3. What does `AzureFunctionUtil.enhanceInputIfNecessary` do? How is the `AzureFunctionUtil.EXECUTION_CONTEXT` header read?
4. When does a function need `Message<T>` vs. taking a plain `T` payload?
5. How do you keep `FunctionCatalog`, conversions, correlation/tracing, logging, and tests at the right boundaries?
6. How do you verify behavior on an Azure HTTP Trigger, Queue Trigger, and a Spring context without the Azure runtime?

The outcome is a Java example featuring a **pure business service**, a **Spring Message-aware function**, an **Azure handler**, and **tests independent of the Azure Host**.

## 2. Distinguishing Four Commonly Confused Objects

| Object | Type / Package | Who Supplies or Manages It? | Purpose |
| --- | --- | --- | --- |
| **Azure ExecutionContext** | `com.microsoft.azure.functions.ExecutionContext` | Azure Java Worker **per invocation** | Logger, invocation ID, function name, trace context. |
| **Spring ApplicationContext** | `org.springframework.context.ApplicationContext` | Spring | Manages beans, dependency injection, configuration/lifecycle. |
| **FunctionCatalog** | `org.springframework.cloud.function.context.FunctionCatalog` | Spring Cloud Function | Looks up/wraps `Supplier`, `Function`, `Consumer`, and compositions. |
| **Spring Message<T>** | `org.springframework.messaging.Message<T>` | Application/adapter/messaging infrastructure | Carries payload and headers to functions or messaging layers. |
| **Azure HttpRequestMessage<T>** | `com.microsoft.azure.functions.HttpRequestMessage<T>` | Azure HTTP binding | Body, method, query, HTTP headers, and response builder. |

An Azure handler can receive both `HttpRequestMessage<Optional<String>>` and `ExecutionContext`:

~~~java
@FunctionName("normalizeAzureOrder")
public HttpResponseMessage execute(
        @HttpTrigger(
                name = "req",
                methods = {HttpMethod.POST},
                authLevel = AuthorizationLevel.FUNCTION,
                route = "orders/normalize")
        HttpRequestMessage<Optional<String>> request,
        ExecutionContext context) {
    // ...
}
~~~

This is an Azure handler signature, not a Spring `Function<T,R>` bean.

**Do not confuse:**

- `@FunctionName("normalizeAzureOrder")` names the **Azure Function**.
- `@Bean Function<Message<String>,String> normalizeOrderWithContext()` names the **Spring functional bean**.
- `catalog.lookup("normalizeOrderWithContext")` looks up the bean in the SCF model.
- `context.getFunctionName()` returns the **currently executing Azure Function name**, not necessarily the bean name.
- `context.getInvocationId()` returns the **invocation ID** issued by Azure, which differs from Spring `MessageHeaders.ID` and business event IDs.

## 3. What Does ExecutionContext Provide?

Per the Azure Java SDK, `ExecutionContext` is an **interface** with these core methods:

| Method | Return Value | Usage |
| --- | --- | --- |
| `getInvocationId()` | `String` | Correlates logs/diagnostics for a single invocation. |
| `getFunctionName()` | `String` | Identifies which Azure handler was invoked. |
| `getLogger()` | `java.util.logging.Logger` | Logs integrated with Azure Functions logging/monitoring. |
| `getTraceContext()` | `TraceContext` in supported API versions | Accesses runtime-provided trace context; check actual values and SDK version. |

Example inside an Azure handler:

~~~java
context.getLogger().info(
        "Started function=" + context.getFunctionName()
        + ", invocation=" + context.getInvocationId());
~~~

**Lifetime:** the context belongs to the **current invocation**. The Azure Functions Host can handle concurrent invocations and scale across multiple processes/instances; never store the context in a mutable field on a Spring singleton for subsequent calls.

### 3.1. Invocation ID, Event ID, and Trace ID Are Different

~~~text
Azure Function name       normalizeAzureOrder
Azure invocation ID       8f...a9  (issued by host per invocation)
Spring Message ID         UUID generated by Spring MessageBuilder
Business event ID         evt-order-601-v1 (set by producer)
Distributed trace ID      trace context from observability infrastructure
~~~

These values may be related, yet they **do not replace one another**:

- When a Queue message is **redelivered**, Azure can assign a new invocation ID.
- If the same business event is retried, the business event ID should **remain stable** to support idempotency.
- `getTraceContext()` does not replace tracing instrumentation or header propagation across HTTP, Queue, and Event Hubs.
- Spring message IDs can change when constructing new messages; do not use them as business deduplication keys.

### 3.2. ExecutionContext Does Not Provide Everything

`ExecutionContext` is **not** a container for all HTTP headers, Queue delivery counts, Blob paths, access tokens, transaction state, or request payloads. Those metadata live on trigger/binding requests, `@BindingName`, other SDKs, or the corresponding adapter.

**Never serialize or return `ExecutionContext` itself in an HTTP response or to a broker.** It is a runtime object holding a logger and execution references; if durable correlation is needed, extract only scalar **values** such as the invocation ID when appropriate for the contract.

## 4. How AzureFunctionUtil Attaches Context to a Spring Message

### 4.1. API and Header Constant

The Spring Cloud Function Azure adapter provides:

~~~java
AzureFunctionUtil.enhanceInputIfNecessary(input, context)
AzureFunctionUtil.EXECUTION_CONTEXT
~~~

Where:

- `input` is the data the handler wants to pass to the functional layer, such as a `String` or a compatible Spring `Message<?>`.
- `context` is the `ExecutionContext` of the **current invocation**.
- The result is the input augmented with context where supported; in the common case of **a plain payload with `ExecutionContext`**, Spring documentation shows the result is a **Spring `Message`** carrying the header.
- `EXECUTION_CONTEXT` is the published constant key; the header name in documentation is **`executionContext`**.

Minimal example matching Spring documentation:

~~~java
Message<?> enriched = (Message<?>)
        AzureFunctionUtil.enhanceInputIfNecessary(
                " dh-601 ", context);

ExecutionContext fromHeader = (ExecutionContext)
        enriched.getHeaders().get(
                AzureFunctionUtil.EXECUTION_CONTEXT);

String payload = (String) enriched.getPayload();
~~~

**Do not scatter literal `"executionContext"` strings across the project when the constant exists.** Using the constant expresses intent and prevents typos when reading/writing headers.

### 4.2. Sequence Diagram

~~~mermaid
sequenceDiagram
    participant Azure as Azure Java Worker
    participant Handler as @Component @FunctionName
    participant Util as AzureFunctionUtil
    participant Catalog as FunctionCatalog
    participant Business as Function<Message<String>,String>
    Azure->>Handler: request + ExecutionContext
    Handler->>Util: enhanceInputIfNecessary(body, context)
    Util-->>Handler: Message(payload, executionContext header)
    Handler->>Catalog: lookup("normalizeOrderWithContext")
    Catalog-->>Handler: function representation
    Handler->>Business: apply(Message<String>)
    Business->>Business: read header / log / normalize payload
    Business-->>Handler: "DH-601"
    Handler-->>Azure: HttpResponseMessage 200
~~~

### 4.3. Why Is the Method Named enhanceInputIfNecessary?

The API name emphasizes that this is **an input enrichment step when necessary**, not a serializer or an Azure trigger mechanism. Rely on the **specific adapter version's** contract and test the resulting types at the boundary; do not assume it turns JSON, POJOs, Azure HTTP requests, or Azure Queue messages into arbitrary domain types.

Another detail: docs show casting to `(Message)` because the initial input might just be a `String`. To avoid unchecked casts, verify the expected payload type at the boundary or maintain strongly typed contracts.

### 4.4. Comparison with Manual MessageBuilder

If you just want an explicit envelope in a unit test or custom adapter, you can build a Spring message manually:

~~~java
Message<String> message = MessageBuilder
        .withPayload(" dh-601 ")
        .setHeader(AzureFunctionUtil.EXECUTION_CONTEXT, context)
        .build();
~~~

This uses `org.springframework.messaging.support.MessageBuilder`. It clearly shows that **data resides in the payload** and **`ExecutionContext` resides in a header**. However, in real Azure handlers, calling `AzureFunctionUtil.enhanceInputIfNecessary(...)` follows Spring Cloud Function's published adapter convention.

If you already have a `Message<String>` and want to preserve other headers:

~~~java
Message<String> enriched = MessageBuilder
        .fromMessage(originalMessage)
        .setHeader(AzureFunctionUtil.EXECUTION_CONTEXT, context)
        .build();
~~~

Note that rebuilding a message can generate a new Spring message ID and timestamp. Tests should assert **application-contract headers** rather than assuming all system metadata are immutable.

## 5. Dependencies and Choosing the Right Adapter Model

### 5.1. Maven Dependency Snippet

Assuming a project with a Spring Boot parent, compatible Spring Cloud BOM, and Java 17+:

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

`spring-cloud-function-adapter-azure` brings Spring/SCF integration into the Azure Java Worker, including `AzureFunctionUtil`. `azure-functions-java-library` supplies `ExecutionContext` and Azure trigger/binding APIs.

`1.3.1` for the Azure Java library is an **illustrative baseline in Microsoft API documentation**, not a claim that it is the latest version. Align with your template, Java runtime, and release train before locking versions. Spring Cloud Function adapters **4.0.0+** support the `@Component`/`@FunctionName` model; use the same BOM-managed line as `spring-cloud-function-context`.

`spring-cloud-function-context` is typically a transitive dependency providing `FunctionCatalog`. With misconfigured dependency management or a missing adapter, importing `AzureFunctionUtil` will fail on the classpath.

### 5.2. Gradle Equivalent

~~~groovy
dependencies {
    implementation 'org.springframework.cloud:spring-cloud-function-adapter-azure'
    implementation 'com.microsoft.azure.functions:azure-functions-java-library:1.3.1'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Appropriate Spring Boot/Spring Cloud dependency management is required. The Azure Gradle plugin `com.microsoft.azure.azurefunctions` or Azure Maven plugin `com.microsoft.azure:azure-functions-maven-plugin` generates binding metadata and packages; they are **separate** from the runtime adapter.

### 5.3. Comparison Across SCF Versions

| Documentation Line | How ExecutionContext Reaches the Function | Notes |
| --- | --- | --- |
| **Modern SCF 4.x/5.x Azure adapter** | `@Component` handler receives `ExecutionContext` from Azure, calls `AzureFunctionUtil.enhanceInputIfNecessary`, function reads header. | Direction this lesson follows based on current official docs. |
| **Some older SCF 3.x guides** | `FunctionInvoker` could attach context to messages or describe registering context with Spring. | **Do not copy verbatim** into new projects; `FunctionInvoker` is deprecated. |
| **Azure Web Adapter** | Spring Web app hosted behind an HTTP trigger hidden by the adapter. | Does not use custom `@FunctionName`/`enhanceInputIfNecessary` handlers by default. |

**Note:** Do not inject `ExecutionContext` via `@Autowired private ExecutionContext context` in a Spring singleton based on an old tutorial. With the modern SCF Azure adapter, the Azure handler method receives the context **per invocation** and attaches it to a Spring `Message` when needed.

## 6. Complete Example: Pure Business Service and Message-Aware Function

Problem: an HTTP POST receives a text order code. The application normalizes the code and logs using the logger tied to the **current Azure invocation**.

~~~text
POST /api/orders/context
Body:  " dh-601 "

Azure handler:
    request.getBody() -> String
    AzureFunctionUtil.enhanceInputIfNecessary(..., ExecutionContext)
    -> Message<String> + executionContext header
    -> FunctionCatalog.lookup("normalizeOrderWithContext")
    -> Function<Message<String>,String>

Response: "DH-601"
Log: function name and invocation ID (do not log secrets/sensitive body)
~~~

### 6.1. Business Service Independent of Azure

Create `src/main/java/example/azure/OrderCodeService.java`:

~~~java
package example.azure;

import java.util.Locale;

import org.springframework.stereotype.Service;

@Service
public class OrderCodeService {

    public String normalize(String raw) {
        if (raw == null || raw.isBlank()) {
            throw new IllegalArgumentException(
                    "Order code must not be blank");
        }

        return raw.strip().toUpperCase(Locale.ROOT);
    }
}
~~~

This component is **pure business logic**: it does not import `ExecutionContext`, `Message`, or any Azure SDK type. Therefore it can be reused whenever an HTTP Trigger, Queue Trigger, Spring Integration flow, or another serverless adapter needs to normalize order codes.

### 6.2. Spring Boot Application and Function Reading Context from Header

Create `src/main/java/example/azure/AzureOrderApplication.java`:

~~~java
package example.azure;

import java.util.function.Function;

import com.microsoft.azure.functions.ExecutionContext;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.function.adapter.azure.AzureFunctionUtil;
import org.springframework.context.annotation.Bean;
import org.springframework.messaging.Message;

@SpringBootApplication
public class AzureOrderApplication {

    public static void main(String[] args) {
        SpringApplication.run(AzureOrderApplication.class, args);
    }

    @Bean
    public Function<Message<String>, String> normalizeOrderWithContext(
            OrderCodeService orderCodes) {

        return message -> {
            ExecutionContext azureContext = (ExecutionContext)
                    message.getHeaders().get(
                            AzureFunctionUtil.EXECUTION_CONTEXT);

            if (azureContext != null) {
                azureContext.getLogger().info(
                        "Normalize order: function="
                        + azureContext.getFunctionName()
                        + ", invocation="
                        + azureContext.getInvocationId());
            }

            // Core business logic has no Azure dependency.
            return orderCodes.normalize(message.getPayload());
        };
    }
}
~~~

**Detailed explanation:**

1. `normalizeOrderWithContext` is a `Function<Message<String>,String>` bean, unlike a `Function<String,String>` that only receives the payload.
2. The function retrieves `ExecutionContext` from `message.getHeaders()` using **`AzureFunctionUtil.EXECUTION_CONTEXT`**, not from a singleton bean.
3. In unit tests, non-Azure environments, or other adapters, the header may be absent. This pattern **accepts `null` and still runs business logic**, keeping the logic reusable.
4. Normalization belongs to `OrderCodeService`. Logging Azure function/invocation IDs is an **adapter-aware concern** and can be moved to the handler if you want the function completely free of Azure dependencies.
5. Never store `azureContext` in a service field, function closure, or static variable after the call finishes.
6. The function returns a `String`, not `ExecutionContext` or the entire `Message`, to the HTTP client.

For stronger decoupling, use a logging interceptor/adapter before invoking `Function<String,String>`. This lesson intentionally uses a **message-aware function** because the goal is understanding how to access `ExecutionContext` **via `AzureFunctionUtil`**.

### 6.3. Why Use FunctionCatalog in the Example?

`FunctionCatalog` places function beans into SCF's canonical model, supporting composition and wrappers/type conversion where supported. The handler looks up `normalizeOrderWithContext` by name:

~~~java
Function<Message<String>, String> normalize =
        catalog.lookup("normalizeOrderWithContext");
~~~

This is the **Spring function name**, not the Azure `@FunctionName`. Injecting a raw `Function<Message<String>,String>` directly would still process the passed `Message`; however, the catalog aligns with the module's goal of reusing function definitions across adapters.

## 7. Azure HTTP Handler Using AzureFunctionUtil

Create `src/main/java/example/azure/OrderAzureHandler.java`:

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

import org.springframework.cloud.function.adapter.azure.AzureFunctionUtil;
import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

@Component
public class OrderAzureHandler {

    private final Function<Message<String>, String> normalize;

    public OrderAzureHandler(FunctionCatalog catalog) {
        this.normalize = Objects.requireNonNull(
                catalog.lookup("normalizeOrderWithContext"),
                "normalizeOrderWithContext not found");
    }

    @FunctionName("normalizeAzureOrder")
    public HttpResponseMessage normalize(
            @HttpTrigger(
                    name = "request",
                    methods = {HttpMethod.POST},
                    authLevel = AuthorizationLevel.FUNCTION,
                    route = "orders/context")
            HttpRequestMessage<Optional<String>> request,
            ExecutionContext context) {

        String raw = request.getBody().orElse("");
        if (raw.isBlank()) {
            return request
                    .createResponseBuilder(HttpStatus.BAD_REQUEST)
                    .body("Order code must not be blank")
                    .build();
        }

        try {
            Object input =
                    AzureFunctionUtil.enhanceInputIfNecessary(
                            raw, context);

            // With a String payload and ExecutionContext,
            // the current API returns a Spring Message.
            if (!(input instanceof Message<?> message)
                    || !(message.getPayload() instanceof String)) {
                throw new IllegalStateException(
                        "Failed to create Message<String>");
            }

            @SuppressWarnings("unchecked")
            Message<String> typed = (Message<String>) message;

            String normalized = normalize.apply(typed);

            return request
                    .createResponseBuilder(HttpStatus.OK)
                    .header("Content-Type",
                            "text/plain; charset=utf-8")
                    .body(normalized)
                    .build();
        }
        catch (RuntimeException error) {
            // Wrapper may wrap IllegalArgumentException.
            Throwable root = error;
            while (root.getCause() != null
                    && root.getCause() != root) {
                root = root.getCause();
            }
            if (root instanceof IllegalArgumentException) {
                return request
                        .createResponseBuilder(HttpStatus.BAD_REQUEST)
                        .body("Invalid order data")
                        .build();
            }

            context.getLogger().log(
                    Level.SEVERE, "Normalize order failed", error);

            return request
                    .createResponseBuilder(
                            HttpStatus.INTERNAL_SERVER_ERROR)
                    .body("Unable to process request")
                    .build();
        }
    }
}
~~~

**Key points of the handler:**

- `@Component` lets Spring manage the handler and inject `FunctionCatalog`.
- `@FunctionName("normalizeAzureOrder")` is the **Azure Function** discovered by the Azure Java Worker.
- `@HttpTrigger` declares POST, route, and authorization policy.
- `ExecutionContext context` is **supplied by Azure per invocation**.
- `AzureFunctionUtil.enhanceInputIfNecessary(raw, context)` is the **boundary passing runtime context into a Spring Message**.
- `normalize.apply(typed)` invokes the function with contract `Message<String> -> String`.
- The handler maps validation errors to HTTP 400 and other errors to 500; the catalog does not decide HTTP status codes.
- Never return the runtime context, stack traces, or sensitive headers directly to callers.

With `AuthorizationLevel.FUNCTION`, the cloud Azure Function App requires a function/host key per host policy. **Function keys do not fully replace authentication/authorization** for sensitive APIs. Local Core Tools may handle keys differently from the cloud, so test security separately in the deployment environment.

### 7.1. When You Do Not Need ExecutionContext

If there is no need to use Azure's logger or trace context inside the functional layer, the simpler approach is:

~~~java
@Bean
Function<String, String> normalizeOrder(
        OrderCodeService orderCodes) {
    return orderCodes::normalize;
}
~~~

The Azure handler can inject the function or `catalog.lookup("normalizeOrder")` and call `apply(raw)` **without calling `AzureFunctionUtil`**. That design is usually better when keeping logic completely environment-independent. Use `Message<T>` only when metadata is genuinely part of the function's contract.

### 7.2. Why Not Inject ExecutionContext via Constructor?

The following is an **anti-pattern** in a Spring singleton component:

~~~java
@Component
class UnsafeHandler {
    @Autowired
    private ExecutionContext currentContext; // Do not do this.
}
~~~

It assumes the Azure runtime context is a long-lived Spring bean, whereas its actual lifecycle is **per invocation**. The right pattern in the modern adapter is accepting `ExecutionContext` on the `@FunctionName` method and passing it into a `Message` if needed.

### 7.3. Checking Headers at the Boundary

During development, you can verify:

~~~java
Message<?> enhanced = (Message<?>)
        AzureFunctionUtil.enhanceInputIfNecessary(
                " dh-601 ", context);

Object attached = enhanced.getHeaders().get(
        AzureFunctionUtil.EXECUTION_CONTEXT);

if (attached != context) {
    throw new IllegalStateException(
            "Missing invocation ExecutionContext");
}
~~~

This is a **diagnostic/test snippet**; do not place identity checks into production business logic. Use tests to verify the input contract when upgrading major SCF versions.


## 8. When Should Context Be Passed via Message?

There are three strategies for the same business logic:

| Strategy | Where Metadata Is Handled | Function Signature | Best When |
| --- | --- | --- | --- |
| **A. Log in the handler** | Azure `@FunctionName` method | `Function<String,String>` | You only need invocation logging at the Azure boundary. |
| **B. Use AzureFunctionUtil** | Message-aware function | `Function<Message<String>,String>` | The function itself genuinely needs the logger/invocation ID. |
| **C. Extract a neutral DTO** | Handler maps Azure context to values | `Function<OrderRequest,R>` | Correlation is needed without coupling the domain to Azure. |

**A — Logger in the handler:**

~~~java
context.getLogger().info(
        "Start invocation " + context.getInvocationId());
String normalized = orderCodes.normalize(raw);
~~~

Choose Strategy A when there is no reason for the business function to accept `Message<T>`.

**B — Context via Spring Message:**

~~~java
Message<?> enriched = (Message<?>)
        AzureFunctionUtil.enhanceInputIfNecessary(raw, context);
Object azure = enriched.getHeaders().get(
        AzureFunctionUtil.EXECUTION_CONTEXT);
~~~

This is the strategy demonstrated throughout this lesson. It does not mean every function in the catalog receives the header automatically if an adapter does not attach it.

**C — Pass only correlation data:**

~~~java
record InvocationInfo(String correlationId, String sourceSystem) {}

record OrderRequest(String code, InvocationInfo invocation) {}
~~~

The handler can construct `new InvocationInfo(context.getInvocationId(), "AZURE")` and pass it into `Function<OrderRequest,R>`. The Azure SDK does not need to appear in the business function. Choose this approach when metadata is genuinely part of the application contract.

**Rule of thumb:** Do not use `AzureFunctionUtil` just because it exists. Only forward the runtime object when a function needs it, and keep a domain layer independent of Azure.

## 9. Header Propagation and Data Safety

### 9.1. The Header Holds a Java Object, Not JSON

After the helper runs, the message conceptually looks like:

~~~text
Message<String>
  payload: " dh-601 "
  headers:
    id: [Spring message ID]
    timestamp: [Spring message timestamp]
    executionContext: [Azure ExecutionContext Java object]
~~~

`executionContext` holds an **in-process** runtime object, not a string suitable for serialization over Kafka, Service Bus, Event Hubs, or HTTP.

When emitting outbound events, create a new message carrying only allowed scalar metadata:

~~~java
Message<String> outbound = MessageBuilder
        .withPayload(normalized)
        .setHeader("businessCorrelationId", businessId)
        .build();
~~~

`normalized` and `businessId` are application-computed/validated values. Never emit `ExecutionContext` itself to a broker or persist this object to a database.

### 9.2. Use a Business Event ID Different from the Invocation ID

A redelivered Queue message can receive a **new Azure invocation ID**. The business event ID should stay stable across retries:

~~~text
Business event ID:  evt-order-601-v1
Invocation A:       inv-123
Invocation B:       inv-987 (retry of the same event)
~~~

Use the business event ID/idempotency key with durable storage supporting unique constraints or atomic operations. `context.getInvocationId()` is suitable for **logging a single execution attempt**, not as a default deduplication key.

### 9.3. Strip the Azure Header Before Leaving the Process

~~~java
Message<String> safe = MessageBuilder
        .fromMessage(internalMessage)
        .removeHeader(AzureFunctionUtil.EXECUTION_CONTEXT)
        .build();
~~~

`internalMessage` is the in-flow message. Removing the Azure header is only the first step: remaining headers still need an outbound mapper/allowlist. Never log function keys, tokens, `Authorization` headers, cookies, connection strings, or private payloads.

### 9.4. When Function Composition Changes Types

If a `Function<Message<String>,String>` returns a `String`, downstream steps no longer see the Azure context automatically. SCF wrappers, Spring Integration transformers, and outbound adapters each have their own metadata propagation rules.

When downstream steps need correlation, design explicit `Message<T>` or DTO contracts and test at the actual boundary. Never assume every header survives every type conversion.

### 9.5. Azure HTTP Headers vs. Spring Message Headers

`request.getHeaders()` belongs to the Azure HTTP binding; `message.getHeaders()` belongs to Spring Messaging. `AzureFunctionUtil.enhanceInputIfNecessary` attaches the context, **not all HTTP headers with validation**. For cross-service trace context, implement dedicated header mapping and instrumentation per transport.

## 10. Errors, Retries, and Lifecycle

**`AzureFunctionUtil` only carries context; it does not handle errors automatically.**

| Context | Behavior on Exception | What Must Be Designed |
| --- | --- | --- |
| HTTP Trigger | Handler/runtime maps HTTP status. | 4xx/5xx schema, timeouts, client retries. |
| Storage Queue Trigger | Host/extension runs retry/poison queue. | Idempotency, max retries, quarantine. |
| Service Bus Trigger | Message settlement, lock/delivery count, and DLQ. | Broker retry policy, duplicate handling. |
| Timer Trigger | Scheduled task fails. | Checkpointing, missed schedules, recovery. |
| SCF FunctionCatalog | Wrapper may wrap business exceptions. | Domain error classification, root cause inspection. |

### 10.1. Missing Context: Optional or Required Policy?

In Section 6's example, the function skips Azure logging when the header is absent; the business service still runs. That fits functions invoked from unit tests or other serverless adapters.

If the application requires auditing every Azure invocation, enforce a **required policy**: validate at the boundary and fail fast. Never silently drop a mandatory audit event.

If headers can originate from external sources, check the type before casting:

~~~java
Object candidate = message.getHeaders().get(
        AzureFunctionUtil.EXECUTION_CONTEXT);

if (candidate instanceof ExecutionContext azureContext) {
    azureContext.getLogger().info("Azure invocation");
}
~~~

This is a safer variant than a direct cast in the demo function, especially when messages arrive from multiple adapters.

### 10.2. Never Store Context in Singletons or Async Jobs

Do not store `ExecutionContext` in mutable fields on Spring `@Component`, `@Service`, or static variables. Azure can execute multiple invocations concurrently and scale across multiple worker instances.

If spawning work that continues after an invocation finishes, **capture String values** like invocation ID/correlation ID into a job DTO rather than retaining the runtime context object:

~~~java
String invocationId = context.getInvocationId();
String functionName = context.getFunctionName();
// Put scalar values into job metadata, do not pass context.
~~~

Do not rely on `ThreadLocal` or an ended invocation's `ExecutionContext` for logging work dispatched to another system.

### 10.3. Context Is Not an Automatic Tracing Solution

`getLogger()` integrates with Azure Functions logging, `getInvocationId()` helps locate logs for a single run, and `getTraceContext()` exposes SDK/runtime trace metadata. However, end-to-end distributed tracing across HTTP, Queue, Service Bus, and Event Hubs requires protocol-level **instrumentation and propagation**. Having an invocation ID in logs does not mean every request has end-to-end tracing.

## 11. Can Queue and Timer Triggers Use AzureFunctionUtil?

### 11.1. Queue Trigger

**Optional extension method** on `OrderAzureHandler` reusing the `normalize` field from Section 7:

~~~java
@FunctionName("normalizeQueuedOrder")
public void normalizeQueuedOrder(
        @QueueTrigger(
                name = "order",
                queueName = "orders-input",
                connection = "AzureWebJobsStorage")
        String orderCode,

        @QueueOutput(
                name = "result",
                queueName = "orders-output",
                connection = "AzureWebJobsStorage")
        OutputBinding<String> output,

        ExecutionContext context) {

    Message<?> enriched = (Message<?>)
            AzureFunctionUtil.enhanceInputIfNecessary(
                    orderCode, context);

    if (!(enriched.getPayload() instanceof String)) {
        throw new IllegalArgumentException("Invalid Queue payload");
    }

    @SuppressWarnings("unchecked")
    Message<String> typed = (Message<String>) enriched;

    output.setValue(normalize.apply(typed));
}
~~~

Requires importing `com.microsoft.azure.functions.OutputBinding`, `com.microsoft.azure.functions.annotation.QueueTrigger`, and `QueueOutput`. Running it requires Azure Storage queues, extensions, and compatible connection settings.

Queue redelivery can generate a new invocation ID. `OutputBinding.setValue(...)` does not guarantee distributed transactions or exactly-once semantics with databases and downstream services. Do not catch all exceptions and return normally if the system relies on Azure retries.

### 11.2. Timer Trigger

~~~java
@FunctionName("scheduledDiagnostics")
public void scheduledDiagnostics(
        @TimerTrigger(
                name = "timer",
                schedule = "0 */5 * * * *")
        String timerInfo,

        ExecutionContext context) {

    context.getLogger().info(
            "Timer invocation=" + context.getInvocationId());
}
~~~

This is a standalone illustrative method requiring `TimerTrigger`. Logging directly in the handler **does not need the helper**. Use `AzureFunctionUtil` only when the Timer handler calls a message-aware function that needs the Azure context. A `Supplier<T>` bean does not create a schedule automatically; the Azure Trigger drives execution via NCRONTAB.

### 11.3. Service Bus and Event Hubs

Similarly, the Azure handler receives the event and `ExecutionContext`, converts the payload to the expected type, calls the helper if the function needs context, and handles outputs appropriately. Ack/checkpoint/retry/DLQ semantics are governed by the binding extension and broker, not by the Spring `executionContext` header.

## 12. Unit Testing AzureFunctionUtil

### 12.1. Test Double for ExecutionContext

Create `src/test/java/example/azure/TestExecutionContexts.java`:

~~~java
package example.azure;

import java.util.logging.Logger;
import com.microsoft.azure.functions.ExecutionContext;

final class TestExecutionContexts {

    static ExecutionContext withInvocationId(String id) {
        return new ExecutionContext() {
            @Override
            public String getInvocationId() {
                return id;
            }

            @Override
            public String getFunctionName() {
                return "normalizeAzureOrder";
            }

            @Override
            public Logger getLogger() {
                return Logger.getLogger("azure-context-test");
            }
        };
    }

    private TestExecutionContexts() {}
}
~~~

`getTraceContext()` is a default method on supported Azure Java library versions, so the test double does not need to override it if unused; verify against your project's SDK.

### 12.2. Testing That Context Is Attached to the Right Header

Create `src/test/java/example/azure/AzureFunctionUtilTest.java`:

~~~java
package example.azure;

import com.microsoft.azure.functions.ExecutionContext;
import org.junit.jupiter.api.Test;
import org.springframework.cloud.function.adapter.azure.AzureFunctionUtil;
import org.springframework.messaging.Message;

import static org.junit.jupiter.api.Assertions.*;

class AzureFunctionUtilTest {

    @Test
    void attachesSameContextToMessage() {
        ExecutionContext context =
                TestExecutionContexts.withInvocationId("inv-test-601");

        Message<?> message = (Message<?>)
                AzureFunctionUtil.enhanceInputIfNecessary(
                        " dh-601 ", context);

        assertEquals(" dh-601 ", message.getPayload());
        assertSame(context,
                message.getHeaders().get(
                        AzureFunctionUtil.EXECUTION_CONTEXT));
    }
}
~~~

`assertSame` is appropriate **in this test**, because we are verifying that the exact context object reference was attached within the same Java process—not checking whether a Spring `FunctionCatalog` wrapper preserves bean identity.

### 12.3. Unit Testing the Service Without Azure

~~~java
OrderCodeService service = new OrderCodeService();

assertEquals("DH-601", service.normalize(" dh-601 "));
assertThrows(IllegalArgumentException.class,
        () -> service.normalize("   "));
~~~

This test proves business logic is independent of the Azure Worker and function context.


## 13. Testing Spring Context and FunctionCatalog

Unit testing `AzureFunctionUtil` proves context attachment onto a `Message`. To verify the function is registered and works when invoked via the catalog, use a Spring Boot test.

Create `src/test/java/example/azure/AzureContextCatalogTest.java`:

~~~java
package example.azure;

import java.util.function.Function;

import com.microsoft.azure.functions.ExecutionContext;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.adapter.azure.AzureFunctionUtil;
import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(classes = AzureOrderApplication.class)
class AzureContextCatalogTest {

    @Autowired
    FunctionCatalog catalog;

    @Autowired
    OrderAzureHandler handler;

    @Test
    void handlerAndFunctionExistInSpringContext() {
        assertNotNull(handler);
        assertNotNull(
                catalog.lookup("normalizeOrderWithContext"));
    }

    @Test
    void catalogFunctionReceivesAzureHeader() {
        ExecutionContext context =
                TestExecutionContexts.withInvocationId("inv-test-602");

        Message<?> enriched = (Message<?>)
                AzureFunctionUtil.enhanceInputIfNecessary(
                        " dh-602 ", context);

        assertSame(context, enriched.getHeaders().get(
                AzureFunctionUtil.EXECUTION_CONTEXT));
        assertInstanceOf(String.class, enriched.getPayload());

        @SuppressWarnings("unchecked")
        Message<String> typed = (Message<String>) enriched;

        Function<Message<String>, String> function =
                catalog.lookup("normalizeOrderWithContext");

        assertNotNull(function);
        assertEquals("DH-602", function.apply(typed));
    }

    @Test
    void functionWorksWithoutAzureHeader() {
        Function<Message<String>, String> function =
                catalog.lookup("normalizeOrderWithContext");

        assertNotNull(function);

        assertEquals("DH-603",
                function.apply(
                        MessageBuilder.withPayload(" dh-603 ")
                                .build()));
    }
}
~~~

**Meaning of each assertion:**

1. The Spring `ApplicationContext` contains the handler bean created by `@Component`.
2. `FunctionCatalog` holds `normalizeOrderWithContext` with the message-aware signature.
3. `enhanceInputIfNecessary` places the exact `ExecutionContext` into the header.
4. The function produces the expected business result even when the context is a test double.
5. The function still handles invocations **without an Azure context**, following the optional policy.

`assertInstanceOf` belongs to modern JUnit 5 versions; for older JUnit compatibility, use `assertTrue(enriched.getPayload() instanceof String)`.

### 13.1. If the Header Has the Wrong Type

In environments where you cannot be certain the header holds an Azure object, use `instanceof` instead of casting directly:

~~~java
Object candidate = message.getHeaders().get(
        AzureFunctionUtil.EXECUTION_CONTEXT);

if (candidate instanceof ExecutionContext azureContext) {
    azureContext.getLogger().info("Processing Azure invocation");
}
~~~

This is a **variant** for the function bean in Section 6, useful when a function is called through multiple adapters or partially untrusted messages.

### 13.2. FunctionCatalog Tests Differ from Azure Host Tests

`@SpringBootTest` does not run the Azure Java Worker, does not generate `function.json` metadata, and does not prove HTTP authorization/routes work. The test layers complement each other:

| Layer | What Is Verified |
| --- | --- |
| Unit service | `OrderCodeService.normalize` processes data correctly. |
| Unit helper | `AzureFunctionUtil` attaches context in the header. |
| Spring Boot test | DI, function registration, catalog lookup, and message-aware calls. |
| Local Azure Functions Host | `@FunctionName` discovery, HTTP route, body/response, and real runtime context. |
| Cloud staging | Authorization, logs, Java runtime, scaling/retries, observability, and performance. |

### 13.3. Do Not Test Object Identity on Function Wrappers

When looking up via `FunctionCatalog`, the function may be wrapped by SCF. **Do not** assert:

~~~java
assertSame(rawBean, catalog.lookup("normalizeOrderWithContext"));
~~~

Instead, test behavior, type contracts, and that headers are read properly per business logic. `assertSame` is only specifically meaningful in the **context header** unit test because the helper must attach the invocation's exact context instance.

## 14. Concurrency, Async, and Observability

### 14.1. One Context per Invocation

Azure can process multiple invocations concurrently:

~~~text
Request A → ExecutionContext A → Message A → Function
Request B → ExecutionContext B → Message B → Function
~~~

If a Spring handler stores `ExecutionContext` in a mutable `currentContext` field, Request B can overwrite Request A's context. With `Message` input, the context travels with the **specific invocation**, independent of singleton fields.

A pattern **never to use**:

~~~java
@Component
class UnsafeContextHolder {

    private ExecutionContext current;

    void setCurrent(ExecutionContext context) {
        this.current = context;
    }

    void log() {
        current.getLogger().info("May log wrong invocation");
    }
}
~~~

The same hazard occurs if a business function uses a `static` variable or mutable closure to hold request/context state.

### 14.2. Async Jobs Must Store Scalar Correlation Values Instead of Runtime Objects

If a job continues after the invocation ends, store durable scalar values:

~~~java
String invocationId = context.getInvocationId();
String azureFunctionName = context.getFunctionName();
// Use scalar values in application JobMetadata.
~~~

Do not retain `ExecutionContext` inside an internal queue/broker or long-running reactive publisher without a clear lifecycle contract. When logging from a background worker, use **that worker environment's** logger/tracing with the correlation ID—do not assume the ended Azure invocation's logger remains valid.

### 14.3. Tracing vs. Logging

- `getLogger()` integrates with Azure Functions logging.
- `getInvocationId()` helps find logs for a single execution.
- `getFunctionName()` identifies the Azure entrypoint.
- `getTraceContext()` can supply trace metadata depending on SDK/runtime.
- End-to-end distributed tracing across HTTP, Queue, Service Bus, or Event Hubs requires appropriate instrumentation and propagation.

**Do not call an invocation ID a distributed trace ID.** When an event is redelivered, you can get a new invocation ID for the exact same business event.

### 14.4. Cold Starts

Initializing the Spring application context and `FunctionCatalog` in the Azure Worker adds cold start latency. `AzureFunctionUtil` is only a metadata-attachment step and does not reduce container startup overhead.

Ways to mitigate risk:

1. Include only dependencies/starters needed for the feature.
2. Never call `SpringApplication.run(...)` per invocation.
3. Avoid constructors/service initialization performing long or unnecessary blocking network I/O.
4. Keep domain functions stateless and thread-safe.
5. Measure startup, memory, and throughput on your actual Azure hosting plan.

## 15. Packaging and Running Locally with Azure Functions Core Tools

### 15.1. Declaring the Spring Main Class

In Maven:

~~~xml
<properties>
    <java.version>17</java.version>
    <start-class>example.azure.AzureOrderApplication</start-class>
</properties>
~~~

`AzureOrderApplication` is the Spring Boot configuration; the Azure entrypoint remains the `@FunctionName("normalizeAzureOrder")` method.

### 15.2. Azure Build Plugin and Spring Boot Repackaging

The Azure Maven/Gradle plugin scans Java annotations and generates `function.json`, `host.json`, and the package layout required by the Azure Java Worker. **A default Spring Boot repackaged executable fat JAR is not directly compatible with Azure Java Functions packaging**, so disable/adjust `spring-boot:repackage` or use a packaging layout supported by the SCF Azure adapter.

Example Maven fragment, to be combined with a POM having an appropriate Boot parent and Spring Cloud BOM:

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
                <appName>azure-context-demo-unique</appName>
                <resourceGroup>azure-context-example-rg</resourceGroup>
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

`1.22.0` is a **reference plugin baseline**, not a claim of being the latest version. The Function App name, resource group, and region are examples; replace them with your approved Azure project values.

### 15.3. host.json and local.settings.json

Minimal `src/main/resources/host.json`:

~~~json
{
  "version": "2.0"
}
~~~

Template `local.settings.json`:

~~~json
{
  "IsEncrypted": false,
  "Values": {
    "FUNCTIONS_WORKER_RUNTIME": "java",
    "FUNCTIONS_EXTENSION_VERSION": "~4",
    "MAIN_CLASS": "example.azure.AzureOrderApplication",
    "AzureWebJobsStorage": "UseDevelopmentStorage=true"
  }
}
~~~

`UseDevelopmentStorage=true` requires **Azurite** when the host/triggers use the Azure Storage emulator. Never commit secrets in `local.settings.json`. On Azure, use Function App settings, managed identities/Key Vault, or proper secrets management.

### 15.4. Starting and Testing

After installing a compatible JDK, Azure Functions Core Tools v4, and Maven:

~~~bash
./mvnw clean package
./mvnw azure-functions:run
~~~

With the default HTTP prefix/port:

~~~bash
curl -i -X POST "http://localhost:7071/api/orders/context" \
  -H "Content-Type: text/plain" \
  --data " dh-601 "
~~~

Expect HTTP 200 with body `DH-601`, while logs record the function name `normalizeAzureOrder` and the current invocation ID. Try an empty or whitespace-only body to receive HTTP 400.

**Note:** Local Core Tools may handle function keys differently from the cloud; `AuthorizationLevel.FUNCTION` must be re-tested in Azure staging. Do not mistake local HTTP testing for verified production authorization.

### 15.5. Deploying to the Cloud Is a Separate Step

The Azure Maven plugin can use:

~~~bash
az login
./mvnw azure-functions:deploy
~~~

Deploying can alter cloud resources and incur costs. These are instructions, **not commands to execute in STEP 4**.

## 16. Troubleshooting and Checklist

### 16.1. Common Errors

| Symptom | Possible Cause | What to Check |
| --- | --- | --- |
| Importing `AzureFunctionUtil` fails | Missing Azure SCF adapter or wrong version. | Dependency tree, Spring Cloud BOM, and import path. |
| `ClassCastException` casting helper result | Input/context or API version mismatch with assumptions. | Test `Message<?>` and payload types at the boundary. |
| `executionContext` header is empty | Helper not called, or message originated elsewhere. | Place assertion at ingress before invoking the function. |
| Header is `String` instead of `ExecutionContext` | External source used the same header name. | Check `instanceof ExecutionContext`. |
| `Function<String,String>` cannot read header | Signature accepts payload, not envelope. | Use `Message<T>` when metadata is needed. |
| Catalog lookup returns null | Wrong bean name/registration or SCF config. | `@Bean` name and catalog tests. |
| Function runs, but logs do not appear in Azure | Different logger level/filter or monitoring config. | Host logs, Application Insights, and observability policy. |
| Azure Host does not see endpoint | Wrong `@FunctionName`/`@HttpTrigger` or package. | `function.json` and Azure plugin output. |
| Spring test PASSES, cloud runtime fails | Different main class/JAR/Java runtime/permissions. | `MAIN_CLASS`, classpath, runtime version, settings. |
| Azure header leaks to a broker | Unfiltered header copying/serialization. | Strip runtime headers, use an outbound allowlist. |
| Concurrent requests log wrong invocation | Context stored in a singleton/static field. | Pass context per `Message`, use stateless handlers. |
| Queue event processed twice | Retry/redelivery, using invocation ID as key. | Business event ID / idempotency store. |
| Tracing disconnects across hops | Missing instrumentation/propagation. | Check trace context on each transport. |

### 16.2. Practical Checklist

- [ ] Azure handler receives `ExecutionContext` as a `@FunctionName` method parameter.
- [ ] Business function accepts `Message<T>` only when context/headers are genuinely needed.
- [ ] Header is accessed via `AzureFunctionUtil.EXECUTION_CONTEXT` instead of scattered literal keys.
- [ ] Handling for missing headers when called outside Azure is explicitly defined.
- [ ] Context is never stored in singleton fields or serialized to a broker.
- [ ] Invocation ID, business event ID, and distributed trace ID are clearly distinguished.
- [ ] Helper unit tests exist with a fake `ExecutionContext`.
- [ ] Spring Boot tests cover `FunctionCatalog` and function signatures.
- [ ] Azure Host tests verify requests, logs, security, and bindings.
- [ ] Error mapping, retries, and idempotency are designed per trigger type.
- [ ] Java runtime, Azure package, Spring Cloud BOM, and adapter versions are aligned.
- [ ] Legacy `FunctionInvoker` is not copied as the default approach for SCF 4.x/5.x.

## 17. Exercises and Official References

### 17.1. Exercises

1. Write a `Function<Message<String>,String>` that prints `getFunctionName()` and `getInvocationId()` to the Azure logger without logging sensitive payloads.
2. Write another Azure HTTP handler using `Function<String,String>` that logs directly in the handler, and compare it with the `AzureFunctionUtil` approach.
3. Test the function when the `EXECUTION_CONTEXT` header is missing and explain the optional policy.
4. Attach a header with the wrong type, update the code to use `instanceof`, and verify no `ClassCastException` occurs.
5. Add a `businessCorrelationId` distinct from the invocation ID and verify it stays unchanged after redelivery.
6. Remove the runtime header before outputting a message to a Queue, and test that serialization never receives an `ExecutionContext` object.
7. Test a Queue Trigger receiving the same business event twice and implement idempotency via event ID.
8. Switch the model to an `OrderRequest` holding a neutral `InvocationInfo` while keeping the domain service free of Azure imports.
9. Inspect `getTraceContext()` in the Java SDK and contrast it with the Azure invocation ID.
10. Upgrade the adapter in a test branch and re-verify the helper, catalog, and Azure package before deploying.

### 17.2. Self-Assessment Questions

- How does `ExecutionContext` differ from Spring `ApplicationContext` and `FunctionCatalog`?
- Why does Azure supply `ExecutionContext` per invocation?
- How does `AzureFunctionUtil.enhanceInputIfNecessary` enable a function to read metadata?
- Does the `AzureFunctionUtil.EXECUTION_CONTEXT` header hold a String ID or a Java runtime object?
- Why can't a `Function<String,String>` read message headers?
- When is logging in the Azure handler better than writing a message-aware function?
- Why is an invocation ID unsuitable as an idempotency key for Queue redelivery?
- Why must runtime context headers be stripped before sending data to a broker?
- Does `catalog.lookup("normalizeOrderWithContext")` create an Azure HTTP route automatically?
- Which tests verify the helper, Spring DI, and the Azure Host at each layer?

### 17.3. References

- [Spring Cloud Function — Microsoft Azure Functions](https://docs.spring.io/spring-cloud-function/reference/adapters/azure-intro.html): `AzureFunctionUtil.enhanceInputIfNecessary`, `AzureFunctionUtil.EXECUTION_CONTEXT`, `FunctionCatalog`, packaging, and Core Tools.
- [Spring Cloud Function — Programming Model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html): `Supplier`, `Function`, `Consumer`, message-aware contracts, composition, and type conversion.
- [Microsoft Learn — Java ExecutionContext API](https://learn.microsoft.com/en-us/java/api/com.microsoft.azure.functions.executioncontext): `getLogger`, `getInvocationId`, `getFunctionName`, and `getTraceContext`.
- [Microsoft Learn — Azure Functions Java Developer Guide](https://learn.microsoft.com/en-us/azure/azure-functions/functions-reference-java): Java handler methods, annotations, execution context, and logging.
- [Microsoft Learn — HTTP Trigger](https://learn.microsoft.com/en-us/azure/azure-functions/functions-bindings-http-webhook-trigger): routes, authorization, requests/responses.
- [Microsoft Learn — Azure Storage Queue Trigger](https://learn.microsoft.com/en-us/azure/azure-functions/functions-bindings-storage-queue-trigger): retries, poison messages, and redelivery.
- [Microsoft Learn — Functions Core Tools Local Run](https://learn.microsoft.com/en-us/azure/azure-functions/functions-run-local): running the local host.
- [Spring Cloud Function Azure Samples](https://github.com/spring-cloud/spring-cloud-function/tree/main/spring-cloud-function-samples): HTTP, Timer, Blob, and Web Adapter examples.

**Conclusion:** `AzureFunctionUtil.enhanceInputIfNecessary(input, context)` attaches the **current Azure invocation's `ExecutionContext`** to the `AzureFunctionUtil.EXECUTION_CONTEXT` header of a Spring `Message<T>`. A function accepting `Message<T>` can read that metadata for logging/tracing when needed, while the business service should remain independent of Azure. Keep clear boundaries across the adapter, function, and transport; never substitute an invocation ID for a business event ID; and never retain or emit the runtime context object outside the process. Test the helper, `FunctionCatalog`, Spring DI, and the Azure Host separately before production operation.
