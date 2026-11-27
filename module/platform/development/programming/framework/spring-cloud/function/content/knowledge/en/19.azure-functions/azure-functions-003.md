# HTTP Trigger, Other Trigger Types, and Input/Output Bindings

## 1. Objectives and Context

**Spring Cloud Function (SCF)** encourages writing business logic as `Supplier<T>`, `Function<T,R>`, and `Consumer<T>`. These functions can be registered in `FunctionCatalog`, chained via *composition*, and reused whether the application is invoked over HTTP, events, or serverless platforms. A function like `Function<String,String>` normalizing an order code does not need to know whether the data arrives from an HTTP request, an Azure Storage Queue, or Event Hubs.

**Azure Functions** handles triggering and transport: receiving HTTP requests, reading events from external services, running on a schedule, and writing results to output bindings. To connect the Azure Java Worker with the Spring application context, Spring Cloud Function provides **`spring-cloud-function-adapter-azure`**. A class annotated with `@Component` can inject `FunctionCatalog`; methods annotated with `@FunctionName` and trigger/binding annotations become entrypoints discovered by the Azure Host.

This lesson focuses on **three easily confused concepts**:

1. **Trigger:** determines what **starts an invocation**; each Azure Function has **only one trigger**.
2. **Input binding:** reads **additional data** into an already-triggered invocation.
3. **Output binding:** sends results to a target system, which does not have to be the same system as the trigger source.

After this lesson, you will be able to:

- Write an HTTP trigger that accepts `HttpRequestMessage<Optional<String>>` and returns `HttpResponseMessage`.
- Use `@QueueOutput` combined with `OutputBinding<String>` to emit messages to an Azure Storage Queue.
- Use `@QueueTrigger` to process messages and forward results to another queue.
- Understand `@TimerTrigger`, `@BlobTrigger`, `@BlobInput`, and when to consider Event Hubs, Service Bus, or Event Grid.
- Keep business functions trigger-agnostic, use `FunctionCatalog.lookup(...)` or composition, test each boundary, and manage errors/redelivery/idempotency.

## 2. How Triggers Differ from Input Bindings and Output Bindings

An Azure Function can have **one trigger**, **zero or more input bindings**, and **zero or more output bindings**, within the binding types and Java signatures supported by the extension.

~~~mermaid
flowchart LR
    T["Trigger<br/>HTTP or Queue or Timer"] --> H["Azure Host / Java Worker"]
    I["Optional input binding<br/>Blob or other data"] --> H
    H --> M["@FunctionName Java method"]
    S["Spring @Component<br/>+ FunctionCatalog"] --> M
    M --> O["Output binding<br/>Queue / Blob / Event Hub / ..."]
    M --> R["HTTP response<br/>if HTTP trigger"]
~~~

| Concept | Question Answered | Java Example | What It Does Not Mean |
| --- | --- | --- | --- |
| **Trigger** | *When* and *why* does the function run? | `@HttpTrigger`, `@QueueTrigger`, `@TimerTrigger` | Does not implicitly write data elsewhere. |
| **Input binding** | What *extra data* does the running invocation need to read? | `@BlobInput` | Does not start a new invocation on its own. |
| **Output binding** | *Where* should the result go? | `@QueueOutput` + `OutputBinding<String>` | Not a new trigger or a distributed transaction. |
| **Return value** | How does the method return data to a binding/HTTP? | `HttpResponseMessage`, `String` | Not always an HTTP response; depends on the output binding. |
| **Spring function** | *What business logic* executes? | `Function<T,R>` from the catalog | Does not create an Azure trigger/binding automatically. |

Further distinctions:

- `@FunctionName("name")` is the **Azure Function name** recognized by the host.
- `@Bean Function<T,R> methodName()` is the **bean name** that SCF can register.
- `catalog.lookup("f1|f2")` is a **composition** in Spring Cloud Function, not a Queue name, topic, or `function.json`.
- A Spring Cloud Function **`Supplier`** can be called from a Timer Trigger, but declaring `@Bean Supplier` alone does not create a Timer Trigger.

### 2.1. One Function Cannot Have Two Triggers

Model error:

~~~java
// Do not do this: two triggers on a single function.
@FunctionName("twoSources")
public void wrong(
        @HttpTrigger(name = "req", authLevel = AuthorizationLevel.FUNCTION)
        String httpBody,
        @QueueTrigger(name = "event", queueName = "order-work",
                      connection = "AzureWebJobsStorage")
        String queueBody) {
    // An Azure Function may only have one trigger.
}
~~~

This is an **anti-pattern snippet**; do not copy it into a real application. If both HTTP and Queue need to normalize order codes, create **two separate `@FunctionName` methods** that both inject the same business function.

### 2.2. Trigger Events Are Not Webhook Requests

An Azure Storage Queue Trigger can re-read an item due to retries/redelivery; an HTTP request typically has a caller waiting for a response; a Timer Trigger runs on a schedule with no business payload. Therefore, **error/ack/retry paths differ**, even when all three invoke the same `Function<String,String>`.

## 3. Overview of Common Triggers and Bindings

| Source / Service | Trigger | Input Binding | Output Binding | When to Use |
| --- | --- | --- | --- | --- |
| **HTTP** | `@HttpTrigger` | Request payload from trigger | `HttpResponseMessage` or HTTP output binding | Request/reply, APIs/webhooks. |
| **Timer** | `@TimerTrigger` | No separate Timer input binding | Can combine with Queue/Blob/... outputs | Scheduled tasks. |
| **Azure Storage Queue** | `@QueueTrigger` | Payload from trigger | `@QueueOutput` | Simple asynchronous work processing. |
| **Azure Blob Storage** | `@BlobTrigger` | `@BlobInput` | `@BlobOutput` | Processing created/updated files or reading/writing blobs. |
| **Azure Service Bus** | `@ServiceBusQueueTrigger` / `@ServiceBusTopicTrigger` | Payload from trigger | Queue/topic output bindings | Enterprise queues/topics with sessions, dead-lettering, and optional duplicate detection. |
| **Azure Event Hubs** | `@EventHubTrigger` | Event stream payload from trigger | `@EventHubOutput` | High-throughput event streams, partitions/consumer groups. |
| **Event Grid** | `@EventGridTrigger` | Event payload from trigger | Event Grid output binding | Resource/service change notifications. |
| **Azure Cosmos DB** | `@CosmosDBTrigger` | Cosmos DB input binding | Cosmos DB output binding | Change feed or reading/writing documents, per extension. |

Not every service has all three binding kinds. For example, **Timer only has a trigger**, while HTTP typically uses a trigger + response. Always check the **binding extension**, Java annotation API, hosting plan, and connection permissions for the specific service. Support can vary by extension and runtime version.

**Azure Storage Queue is not Azure Service Bus Queue.** They differ in namespaces, connections, retries, messages, and operational features; do not swap `@QueueTrigger` for `@ServiceBusQueueTrigger` without changing the underlying infrastructure.

## 4. Dependencies and How Azure Discovers Bindings

### 4.1. Maven Dependencies

Example for a Maven project with a Spring Boot parent and a **compatible Spring Cloud BOM**:

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

`1.3.1` is an **illustrative version** of the Azure Java Functions library, not a claim that it is always the latest release. Align it with your active Azure Java project template. `spring-cloud-function-adapter-azure` requires **SCF 4.0.0+** for the modern `@Component`/`@FunctionName` model; the adapter version and `spring-cloud-function-context` must belong to the same BOM-managed release line.

### 4.2. Azure Plugin and Binding Extensions

Beyond runtime libraries, Java Azure Functions need the **Azure Maven/Gradle plugin** to scan annotations and generate `function.json`, `host.json`, and a valid Azure package.

Example of metadata generated by the plugin from a single method:

~~~json
{
  "bindings": [
    {
      "type": "httpTrigger",
      "direction": "in",
      "name": "request",
      "route": "orders",
      "methods": ["post"],
      "authLevel": "function"
    },
    {
      "type": "queue",
      "direction": "out",
      "name": "work",
      "queueName": "order-work",
      "connection": "AzureWebJobsStorage"
    },
    {
      "type": "http",
      "direction": "out",
      "name": "$return"
    }
  ]
}
~~~

This is an **illustration of binding metadata**, not a complete `function.json` for every version. The plugin also generates `scriptFile` and `entryPoint` matching the Java application artifact and handler. Do not hand-edit staging output to patch an incorrectly declared Java annotation.

HTTP and Timer are built-in host bindings; Blob/Queue, Event Hubs, Service Bus, Event Grid, and other services may require compatible **extension bundles/extension registrations**. A Java class compiling cleanly does not guarantee the host can load the extension to run the trigger. Check host startup logs and documentation for the chosen binding.

### 4.3. Gradle Equivalent

~~~groovy
dependencies {
    implementation 'org.springframework.cloud:spring-cloud-function-adapter-azure'
    implementation 'com.microsoft.azure.functions:azure-functions-java-library:1.3.1'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Use the Gradle plugin `com.microsoft.azure.azurefunctions` to package/run/deploy, or the Maven plugin `com.microsoft.azure:azure-functions-maven-plugin` if using Maven. Pick only one build workflow to avoid uncontrolled artifact changes.

## 5. Complete Example: HTTP -> Queue -> Queue Trigger -> Queue

### 5.1. Business Requirements

An application receives a text order code via HTTP:

~~~text
POST /api/orders
Body: "  dh-301  "

→ HTTP 202 Accepted
→ Azure Storage Queue "order-work" receives "DH-301"
→ Queue Trigger processes the message
→ Azure Storage Queue "order-results" receives "DH-301"
~~~

The same **order code normalization** rule can be reused from both entrypoints via SCF composition:

~~~text
trimCode   : Function<String,String>
upperCode  : Function<String,String>

FunctionCatalog.lookup("trimCode|upperCode")
  → Function<String,String>
~~~

~~~mermaid
flowchart LR
    A["HTTP client"] --> B["@HttpTrigger<br/>submitOrder"]
    B --> C["FunctionCatalog<br/>trimCode|upperCode"]
    C --> D["@QueueOutput<br/>order-work"]
    D --> E["Azure Storage Queue"]
    E --> F["@QueueTrigger<br/>processOrder"]
    F --> G["Same FunctionCatalog"]
    G --> H["@QueueOutput<br/>order-results"]
~~~

**Exercise policy:** if the body is blank, HTTP returns 400 and no message is placed on the queue. The Queue Trigger throws an exception on an empty message or processing failure so the Azure Host applies its retry/poison-message policy. In production, avoid logging raw sensitive payloads and implement idempotency using a dedicated event/transaction ID.

### 5.2. Spring Boot Class Declaring Business Functions

Create `src/main/java/example/azure/OrderFunctionsApplication.java`:

~~~java
package example.azure;

import java.util.Locale;
import java.util.function.Function;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class OrderFunctionsApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderFunctionsApplication.class, args);
    }

    @Bean
    public Function<String, String> trimCode() {
        return String::strip;
    }

    @Bean
    public Function<String, String> upperCode() {
        return value -> value.toUpperCase(Locale.ROOT);
    }
}
~~~

Both functions neither import the Azure SDK nor know about queue names or HTTP routes. They can be called directly in Java, via another HTTP adapter, or from another serverless runtime as long as the adapter converts data to the expected type.

### 5.3. Azure Handler with Two Entrypoints and Output Bindings

Create `src/main/java/example/azure/OrderAzureHandlers.java`:

~~~java
package example.azure;

import java.util.Objects;
import java.util.Optional;
import java.util.function.Function;

import com.microsoft.azure.functions.AuthorizationLevel;
import com.microsoft.azure.functions.ExecutionContext;
import com.microsoft.azure.functions.HttpMethod;
import com.microsoft.azure.functions.HttpRequestMessage;
import com.microsoft.azure.functions.HttpResponseMessage;
import com.microsoft.azure.functions.HttpStatus;
import com.microsoft.azure.functions.OutputBinding;
import com.microsoft.azure.functions.annotation.FunctionName;
import com.microsoft.azure.functions.annotation.HttpTrigger;
import com.microsoft.azure.functions.annotation.QueueOutput;
import com.microsoft.azure.functions.annotation.QueueTrigger;

import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.stereotype.Component;

@Component
public class OrderAzureHandlers {

    private final Function<String, String> normalize;

    public OrderAzureHandlers(FunctionCatalog catalog) {
        this.normalize = Objects.requireNonNull(
                catalog.lookup("trimCode|upperCode"),
                "Function trimCode|upperCode not found");
    }

    @FunctionName("submitOrder")
    public HttpResponseMessage submitOrder(
            @HttpTrigger(
                    name = "request",
                    methods = {HttpMethod.POST},
                    authLevel = AuthorizationLevel.FUNCTION,
                    route = "orders")
            HttpRequestMessage<Optional<String>> request,

            @QueueOutput(
                    name = "work",
                    queueName = "order-work",
                    connection = "AzureWebJobsStorage")
            OutputBinding<String> work,

            ExecutionContext context) {

        String body = request.getBody().orElse("");
        if (body.isBlank()) {
            return request.createResponseBuilder(HttpStatus.BAD_REQUEST)
                    .body("Order code must not be blank")
                    .build();
        }

        String normalized = normalize.apply(body);
        work.setValue(normalized);

        context.getLogger().info("Order submitted");
        return request.createResponseBuilder(HttpStatus.ACCEPTED)
                .body("Accepted: " + normalized)
                .build();
    }

    @FunctionName("processOrder")
    public void processOrder(
            @QueueTrigger(
                    name = "order",
                    queueName = "order-work",
                    connection = "AzureWebJobsStorage")
            String orderCode,

            @QueueOutput(
                    name = "result",
                    queueName = "order-results",
                    connection = "AzureWebJobsStorage")
            OutputBinding<String> result,

            ExecutionContext context) {

        if (orderCode == null || orderCode.isBlank()) {
            throw new IllegalArgumentException(
                    "Message contains an invalid order code");
        }

        String normalized = normalize.apply(orderCode);
        result.setValue(normalized);
        context.getLogger().info("Order processed");
    }
}
~~~

**Boundary analysis:**

1. `submitOrder` has **one** HTTP trigger and **one** Queue output binding. The method returns `HttpResponseMessage` to the HTTP client, while `work.setValue(...)` assigns a message that the runtime will write to the Queue output.
2. `processOrder` has **one** Queue trigger and **one** Queue output binding; it is **not** an HTTP endpoint. A `void` return type is appropriate because the output is set via `result.setValue(...)`.
3. `@Component` ensures Spring manages the handler and injects `FunctionCatalog`; `@FunctionName` ensures Azure recognizes each Azure Function.
4. The names `submitOrder`/`processOrder` belong to the **Azure Host**; `trimCode`/`upperCode` belong to the **SCF catalog**.
5. `OutputBinding<String>` is a holder for the output binding value; calling `setValue` **does not mean** downstream processing has finished or that a distributed transaction committed alongside the HTTP response.
6. The Azure Host orchestrates writing bindings when the function finishes executing. If writing to the queue fails, the entire invocation can fail; thus HTTP 202 in this design is not confirmation that business processing succeeded at the destination queue.
7. `ExecutionContext` is the per-invocation context, suitable for logging, and must not be stored in the singleton handler.

### 5.4. Why Choose HTTP 202 Instead of 200?

HTTP 202 `Accepted` expresses that the request has been accepted into an **asynchronous pipeline**, without claiming the Queue Trigger step has completed. This is the **example's API policy**; in production, if clients need to check status, return a request/correlation ID and provide a status endpoint or post-processing notification event.

Note that when the output binding is actually committed depends on the runtime and extension. Do not build logic treating `work.setValue(...)` as durable end-to-end confirmation without testing/designing consistency guarantees.

### 5.5. Main Class and Azure Functions Host

`OrderFunctionsApplication` is in the same `example.azure` package as `OrderAzureHandlers`, so component scanning detects the handler. Set `MAIN_CLASS=example.azure.OrderFunctionsApplication` if the adapter needs the main class explicitly specified in local/Azure settings.

The Function App uses **Azure Functions runtime 4.x** with a compatible Java runtime, and the Azure Maven/Gradle plugin generates `function.json` and a valid package. **Do not call `SpringApplication.run(...)` on every invocation**; the adapter manages Spring context creation across the worker lifecycle.

## 6. HTTP Trigger and Response Details

### 6.1. @HttpTrigger

~~~java
@FunctionName("submitOrder")
public HttpResponseMessage submitOrder(
        @HttpTrigger(
                name = "request",
                methods = {HttpMethod.POST},
                authLevel = AuthorizationLevel.FUNCTION,
                route = "orders")
        HttpRequestMessage<Optional<String>> request,
        @QueueOutput(name = "work",
                     queueName = "order-work",
                     connection = "AzureWebJobsStorage")
        OutputBinding<String> work,
        ExecutionContext context) {
    // Logic from Section 5.
}
~~~

| Attribute | Meaning |
| --- | --- |
| `name` | Binding parameter name in metadata (e.g., `request`). |
| `methods` | Allowed HTTP methods that trigger the function. |
| `authLevel` | Authorization key policy: `ANONYMOUS`, `FUNCTION`, `ADMIN` depending on the scenario. |
| `route` | Relative URL path; default prefix is `/api`. |
| `HttpRequestMessage<T>` | Reads body, query parameters, headers, URI, and method. |
| `HttpResponseMessage` | Returns status, headers, and body to the HTTP caller. |

`@HttpTrigger` is placed on the **parameter**, `@FunctionName` is placed on the **method**. Azure Java entrypoints must be `public`. The Azure Maven/Gradle plugin uses annotations to generate metadata; simply adding `@Component` does not create an HTTP route.

### 6.2. Query, Path Parameters, and Headers

You can read query strings and headers with:

~~~java
String orderId = request.getQueryParameters().get("orderId");
String correlation = request.getHeaders().get("x-correlation-id");
~~~

If the route declares `route = "orders/{id}"`, you can add a parameter:

~~~java
@BindingName("id") String id
~~~

by importing `com.microsoft.azure.functions.annotation.BindingName`. The demo takes a text body to avoid complex parsing; when accepting JSON, deserialize and validate the domain object at the boundary before calling `Function<OrderRequest,OrderDecision>`.

Never implicitly trust client-supplied headers, routes, or query parameters: validate, authorize, and enforce size limits on them; never use external input to arbitrarily choose `catalog.lookup(...)` by function name.

### 6.3. Auth and HTTP Errors

- `AuthorizationLevel.FUNCTION` requires a function/host key per Azure host policy; keys do not fully replace user authentication/authorization for sensitive APIs.
- Local Core Tools may handle authorization differently from production; verify cloud staging before exposing public endpoints.
- Blank or schema-invalid inputs should return 4xx per the API contract.
- Infrastructure failures may require 5xx/timeouts and a request ID for troubleshooting.
- An HTTP response status must not be treated as the sole source of truth that downstream processing of a Queue message succeeded.

## 7. Queue Trigger and Queue Output Binding

### 7.1. Queue Trigger

~~~java
@FunctionName("processOrder")
public void processOrder(
        @QueueTrigger(name = "order",
                      queueName = "order-work",
                      connection = "AzureWebJobsStorage")
        String orderCode,
        ExecutionContext context) {
    // Invoke the business function.
}
~~~

`queueName` is the Azure Storage Queue name, and `connection` is the **app setting/connection configuration name**, not a connection string written directly in the annotation. The Queue trigger relies on host polling to wake up the function when a message is ready.

**A Queue is not an SCF Supplier:** the Azure Host/extension actively triggers on queue messages. A `@Bean Supplier<T>` does not automatically poll a queue; if you want to use a supplier, the handler/adapter must invoke it explicitly.

### 7.2. Queue Output Binding

~~~java
@QueueOutput(
        name = "result",
        queueName = "order-results",
        connection = "AzureWebJobsStorage")
OutputBinding<String> result
~~~

Inside the handler body:

~~~java
result.setValue(normalized);
~~~

`OutputBinding<T>` is an Azure Java library abstraction for setting outputs, not a `java.util.function.Consumer<T>` or a Spring Integration channel. The Azure host/binding extension handles writing the value to the Queue.

Aside from the `OutputBinding<T>` parameter style, Azure Java also supports declaring an output binding on the return value using corresponding APIs/annotations. When returning **both an HTTP response and a Queue output at the same time**, the `OutputBinding<String>` parameter makes it clear that the HTTP return and the Queue message are **two independent outputs**.

### 7.3. Retries, Poison Queues, and Duplicate Data

A Queue Trigger can retry a message when an invocation fails; after repeated failures, the message can move to a **poison queue** according to the Azure Queue Storage extension mechanism/configuration. Retry timing, dequeue counts, encoding, and processing limits depend on the host/extension version.

Therefore:

- Do not swallow exceptions if the system relies on triggering retries.
- Do not retry infinitely on validation-invalid data; use a quarantine/poison-message policy.
- Do not assume exactly-once delivery; the same message can arrive again.
- Use a stable `eventId` or business key and persist state using storage with atomicity guarantees.
- Distinguish an **Azure Storage Queue poison queue** from a **Service Bus DLQ**, as they belong to two different services.
- When enqueuing text Queue messages from external SDKs, verify the **message encoding** expected by the Queue extension to avoid base64/plain-text mismatches across versions.

### 7.4. Do Not Assume an Output Binding Is Transactional

If a business function writes to a database and an output binding emits a Queue message, those two operations are not automatically enclosed in a distributed transaction. If you must guarantee event emission after commit, consider a **transactional outbox** and idempotency. An HTTP 202 response does not substitute for message broker acknowledgement.


## 8. Timer Trigger: Scheduled Execution vs. Supplier.get()

### 8.1. NCRONTAB Expressions

Azure Timer Trigger executes a `@FunctionName` method on a schedule managed by the Azure Host:

~~~java
@FunctionName("scheduledHeartbeat")
public void scheduledHeartbeat(
        @TimerTrigger(
                name = "timer",
                schedule = "0 */5 * * * *")
        String timerInfo,
        ExecutionContext context) {
    context.getLogger().info("Timer triggered");
}
~~~

Requires importing `com.microsoft.azure.functions.annotation.TimerTrigger`. The schedule `0 */5 * * * *` means at second 0, **every five minutes**, using the **six-field NCRONTAB** format:

~~~text
{second} {minute} {hour} {day} {month} {day-of-week}
~~~

Azure Functions uses **UTC** by default; configuring timezones via `WEBSITE_TIME_ZONE` has restrictions depending on hosting plan/OS, especially Linux Consumption/Flex Consumption plans. Do not configure custom timezones arbitrarily without checking deployment docs.

Other examples:

| NCRONTAB | Meaning |
| --- | --- |
| `0 */5 * * * *` | Every 5 minutes. |
| `0 0 * * * *` | At the top of every hour. |
| `0 30 9 * * *` | Daily at 09:30 in the host timezone. |
| `0 0 */2 * * *` | Every 2 hours, at minute/second 0. |

**Timer is not an extra input binding:** it is a trigger. If a Timer Function needs to read a DB, Blob, or service, it can call an SDK/service bean or use a supported input binding within Azure extension limits.

### 8.2. Timer Trigger Calling an SCF Supplier and Writing Queue Output

To emit a new heartbeat/event on a schedule, a `Supplier<String>` bean supplies the payload:

~~~java
@Bean
Supplier<String> createHeartbeat() {
    return () -> "heartbeat-" + UUID.randomUUID();
}
~~~

Requires importing `java.util.function.Supplier` and `java.util.UUID` in the Spring configuration. An Azure handler can inject the catalog and use the supplier:

~~~java
@Component
class HeartbeatHandler {

    private final Supplier<String> heartbeat;

    HeartbeatHandler(FunctionCatalog catalog) {
        this.heartbeat = Objects.requireNonNull(
                catalog.lookup("createHeartbeat"),
                "createHeartbeat not found");
    }

    @FunctionName("sendHeartbeat")
    public void sendHeartbeat(
            @TimerTrigger(
                    name = "timer",
                    schedule = "0 */5 * * * *")
            String timerInfo,

            @QueueOutput(
                    name = "out",
                    queueName = "order-ops",
                    connection = "AzureWebJobsStorage")
            OutputBinding<String> out,

            ExecutionContext context) {

        out.setValue(heartbeat.get());
        context.getLogger().info("Heartbeat generated");
    }
}
~~~

This is an **independent additional configuration**; it requires the corresponding Azure/Spring imports and the `createHeartbeat` bean to be registered. It is not a mandatory part of the two handlers in the main example.

Key takeaways:

- `@TimerTrigger` determines **when** to invoke.
- `Supplier.get()` determines **what value** to emit.
- `@QueueOutput` specifies the **destination** of the event.
- If the supplier always returns the same value, each scheduled run will emit identical messages.
- Timer Trigger has its own error handling and missed-schedule behavior; it does not automatically apply poison-queue retries like Queue Trigger. If retries are needed, use mechanisms supported by Azure Functions for your chosen trigger/runtime, or design a stateful job with checkpointing.

## 9. Blob Trigger and Blob Input Binding

### 9.1. Blob Trigger: File as Trigger Source

When a blob is created or updated in a monitored container, `@BlobTrigger` can invoke a Java handler:

~~~java
@FunctionName("inspectIncomingBlob")
public void inspectIncomingBlob(
        @BlobTrigger(
                name = "blob",
                path = "incoming/{name}",
                connection = "AzureWebJobsStorage",
                dataType = "binary")
        byte[] content,

        @BindingName("name") String filename,
        ExecutionContext context) {

    context.getLogger().info(
            "Blob received, size=" + content.length);
}
~~~

Requires importing `com.microsoft.azure.functions.annotation.BlobTrigger` and `BindingName`. This is a **standalone method**, assuming an Azure Storage container `incoming` and a compatible Blob extension. `{name}` is a binding expression for the blob name. `dataType = "binary"` fits when the Java parameter accepts `byte[]`.

**Watch the size:** reading an entire blob into `byte[]` can consume significant RAM. For large files, check stream/SDK binding types supported by the Java extension or use the Azure Blob SDK to stream downloads. Do not default to loading whole files into memory for large datasets.

Blob Trigger detection and retries vary depending on the extension/`source` (e.g., container polling vs. Event Grid-based triggers). Check latency, concurrency, and create/update semantics in the actual extension docs.

### 9.2. Blob Input: Reading an Additional File for a Queue Trigger

A Queue item contains a **file name**; the Queue Trigger starts the invocation, while Blob Input merely reads the contents of the referenced file:

~~~java
@FunctionName("inspectQueuedDocument")
public void inspectQueuedDocument(
        @QueueTrigger(
                name = "filename",
                queueName = "document-work",
                connection = "AzureWebJobsStorage")
        String filename,

        @BlobInput(
                name = "document",
                path = "documents/{queueTrigger}",
                dataType = "binary")
        byte[] document,

        ExecutionContext context) {

    context.getLogger().info(
            "Document size=" + document.length);
}
~~~

Requires importing `com.microsoft.azure.functions.annotation.BlobInput`. In this example, `BlobInput` uses the default `AzureWebJobsStorage`; to target another storage account, specify `connection`/`@StorageAccount` per the corresponding API/extension.

**This is an important illustration:** the Queue event is the **trigger**, the Blob is read via an **input binding**, and the handler processes both inputs. There is no second Blob Trigger on this method.

Queue data provided externally should not be blindly trusted as a blob path. Validate file names, namespaces, access control, sizes, and behavior when the blob does not exist. For large files, streaming via the SDK or delegating to a dedicated service is safer.

### 9.3. Blob Output

Azure Java also offers `@BlobOutput` to write results to Blob Storage via an output binding. A pipeline can look like:

~~~text
Queue Trigger (file name)
    +
Blob Input (file data)
    ↓
Business Function
    ↓
Blob Output (processed file)
~~~

Select `path`, `connection`, content type, and write permissions for your actual data. If the output path matches a container/pattern watched by a Blob Trigger, you can accidentally create an infinite event loop; separate input/output locations or enforce anti-reprocessing policies.

## 10. Event Hubs, Service Bus, Event Grid, and Cosmos DB

### 10.1. Event Hubs Trigger

Event Hubs suits high-throughput telemetry/event streams with **partitions**, **consumer groups**, and checkpoints. Example Java method:

~~~java
@FunctionName("receiveOrderEvents")
public void receiveOrderEvents(
        @EventHubTrigger(
                name = "event",
                eventHubName = "order-events",
                consumerGroup = "$Default",
                connection = "EventHubConnection")
        String payload,
        ExecutionContext context) {

    String normalized = normalize.apply(payload);
    context.getLogger().info("Event Hub event handled");
}
~~~

Requires importing `com.microsoft.azure.functions.annotation.EventHubTrigger`; this is a **fragment of a separate handler**, assuming the `normalize` field is injected as in Section 5 and an Event Hubs extension/connection is configured. When receiving JSON events instead of plain text order codes, deserialize/validate before invoking the function.

`EventHubTrigger` supports configuring `cardinality` (single event or batch) per the Java API and extension version. When choosing batch mode, parameter signatures and error/checkpoint handling differ from single events. Do not copy a method taking `String` and merely flip `cardinality` to `MANY` without checking the supported binding parameter types.

### 10.2. Service Bus Queue and Topic Triggers

Service Bus provides message broker capabilities such as sessions, dead-lettering, and configurable duplicate detection. Queue Trigger example:

~~~java
@FunctionName("receiveServiceBusOrder")
public void receiveServiceBusOrder(
        @ServiceBusQueueTrigger(
                name = "message",
                queueName = "orders",
                connection = "ServiceBusConnection")
        String payload,
        ExecutionContext context) {

    String normalized = normalize.apply(payload);
    context.getLogger().info("Service Bus message handled");
}
~~~

Requires importing `com.microsoft.azure.functions.annotation.ServiceBusQueueTrigger`. For topic subscriptions, use `@ServiceBusTopicTrigger` with `topicName` and `subscriptionName`. On the output side, use `@ServiceBusQueueOutput` or `@ServiceBusTopicOutput`, **not Azure Storage Queue's `@QueueOutput`**.

Note for modern Java projects: if using the Service Bus SDK directly, choose a Microsoft-supported library such as `com.azure:azure-messaging-servicebus`; older legacy Service Bus SDKs reach end-of-support in 2026. Using Functions bindings does not mean pulling legacy SDKs onto the classpath.

### 10.3. Event Grid and Cosmos DB

- **Event Grid Trigger** typically receives notifications of resource or business events. Event Grid event schema and CloudEvents schema can differ; verify the payload contract before calling the function.
- **Cosmos DB Trigger** monitors the change feed via its extension; specify batch reading, lease container, idempotency, and how repeated document updates are handled.
- **Azure Storage Queue** generally fits simple asynchronous work; **Service Bus** fits broker-grade semantics; **Event Hubs** fits high-volume event streams; **Event Grid** fits event distribution notifications. Do not swap them merely by changing annotations without changing the underlying infrastructure.

### 10.4. Choosing the Right Source by Requirement

| Need | Suitable Starting Point | Risks to Control |
| --- | --- | --- |
| HTTP request/reply | `@HttpTrigger` | Auth, validation, timeouts, synchronous workload. |
| Simple work queue consumption | `@QueueTrigger` | Redelivery, poison queue, encoding, storage permissions. |
| Message broker with topics/sessions | Service Bus Trigger | Lock/settlement, dead-lettering, duplicate detection. |
| High-throughput telemetry/event stream | Event Hubs Trigger | Partition ordering, checkpointing, batching, consumer groups. |
| React to new files | Blob Trigger | File size, trigger source, infinite loops on write-back. |
| Read a file pointed to by another message | Queue Trigger + Blob Input | Blob path, permissions, missing or not-yet-ready files. |
| Scheduled tasks | Timer Trigger | Timezone, missed schedules, idempotent jobs, cold start. |

## 11. Binding Data, Metadata, and Conversion

### 11.1. Trigger Data Does Not Automatically Become a Domain Object

Example JSON HTTP body:

~~~json
{
  "eventId": "evt-301",
  "orderId": " dh-301 ",
  "totalVnd": 1500000
}
~~~

You can define:

~~~java
record OrderRequest(
        String eventId,
        String orderId,
        long totalVnd) {}
~~~

and a business function:

~~~java
@Bean
Function<OrderRequest, String> normalizeOrderRequest() {
    return order -> order.orderId()
            .strip()
            .toUpperCase(Locale.ROOT);
}
~~~

However, **HTTP `HttpRequestMessage<Optional<String>>` in Section 5 returns a String body**, not an `OrderRequest` automatically. The handler needs a JSON deserialization and validation step, or Azure Java Worker POJO binding with a supported type. SCF `FunctionCatalog` provides wrappers/converters, but that does not mean every HTTP/Queue/Blob format automatically decodes into every Java record.

Furthermore, the `OrderRequest` structure above only illustrates a contract; in production, check nulls, schema versions, enums, numeric ranges, content types, and input sizes.

### 11.2. Trigger Metadata Is Invocation Data

Triggers can carry:

| Trigger | Common Important Metadata |
| --- | --- |
| HTTP | Method, route/query, request headers, correlation/trace context. |
| Storage Queue | Message ID, dequeue count, enqueue timestamp, and retry info. |
| Blob | Container/path/name, ETag, blob properties. |
| Event Hubs | Partition/sequence/offset, enqueued time, consumer group. |
| Service Bus | Message ID, correlation ID, delivery count, session, lock. |
| Timer | Scheduled timestamp, past-due info per model. |

Azure Java provides `@BindingName` to extract supported trigger/binding metadata. Do not assume all metadata exists under identical names or types across all extensions.

### 11.3. Spring Message<T> and Azure Binding Metadata

A simple business function `Function<String,String>` only needs the payload. If tracing/correlation is needed, the handler can:

- Read metadata from `HttpRequestMessage` or the binding context.
- Map that metadata into the domain input when it carries business meaning.
- Or construct a Spring `Message<T>` and call a function with signature `Function<Message<T>,R>` in verified SCF adapter/wrapper setups.

SCF provides `AzureFunctionUtil.enhanceInputIfNecessary(...)` to attach `ExecutionContext` as a Spring message header when needed. Still, avoid passing full Azure runtime objects into business functions when the goal is reuse across HTTP, brokers, or other serverless runtimes.

### 11.4. CloudEvents Does Not Replace a Trigger

CloudEvents is an **event envelope specification** (id, source, type, specversion, data), not a default Azure trigger type for all infrastructure. Event Grid, Event Hubs, or HTTP can carry CloudEvents under their own contracts. You still need the corresponding trigger/binding, parser/converter, validation, and metadata propagation.

## 12. Local Settings, Extensions, and Packaging

### 12.1. local.settings.json

Local example **for the Storage emulator only**:

~~~json
{
  "IsEncrypted": false,
  "Values": {
    "FUNCTIONS_WORKER_RUNTIME": "java",
    "FUNCTIONS_EXTENSION_VERSION": "~4",
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "MAIN_CLASS": "example.azure.OrderFunctionsApplication"
  }
}
~~~

When using `UseDevelopmentStorage=true`, you must run **Azurite** or a compatible storage emulator. The example omits Service Bus/Event Hubs credentials; if you also run those triggers, configure their corresponding app settings and identities/connections. **Never commit secrets in `local.settings.json`** to the repository.

In Azure, configure Function App settings, managed identities, and Key Vault per operational policy. The `connection` attribute in annotations normally names an app setting or connection prefix; never embed connection strings directly in source code.

### 12.2. host.json and Extension Bundles

Minimal template:

~~~json
{
  "version": "2.0"
}
~~~

Some hosts/bindings require an extension bundle or explicit extension registration matching the runtime. When using Queue/Blob/Event Hubs/Service Bus, check the **binding extension version** and how it is supplied via package or extension bundle; do not assume a Java annotation alone makes the extension available.

### 12.3. Maven / Gradle Packaging

With Maven:

~~~bash
./mvnw clean package
./mvnw azure-functions:run
~~~

With Gradle, if the project already configures the Azure Functions plugin:

~~~bash
./gradlew azureFunctionsPackage
./gradlew azureFunctionsRun
~~~

The Azure plugin produces a package with metadata/binding files generated from annotations. **A standard Spring Boot repackaged executable fat JAR does not match the layout expected by the Azure Worker**; disable/adjust Boot repackaging or use the official packaging configuration suitable for the adapter.

Do not run both Maven and Gradle for the same project just because the lesson presents both options.

## 13. Testing at Each Boundary

### 13.1. Unit Testing Business Functions

No Azure Functions Host required:

~~~java
OrderFunctionsApplication application =
        new OrderFunctionsApplication();

String normalized =
        application.upperCode().apply(
                application.trimCode().apply(" dh-301 "));

assertEquals("DH-301", normalized);
~~~

Requires JUnit 5 `assertEquals`. Unit tests only verify the business function; they do not verify Queue Output bindings, retries, or host discovery.

### 13.2. Spring Context / FunctionCatalog Test

~~~java
@SpringBootTest(classes = OrderFunctionsApplication.class)
class CatalogTest {

    @Autowired
    FunctionCatalog catalog;

    @Test
    void compositionShouldNormalize() {
        Function<String, String> normalize =
                catalog.lookup("trimCode|upperCode");

        assertNotNull(normalize);
        assertEquals("DH-301",
                normalize.apply(" dh-301 "));
    }
}
~~~

Add imports for Spring Boot Test, `@Autowired`, `FunctionCatalog`, `Function`, and JUnit Assertions. This test catches component scanning issues, dependency injection errors, and composition name/type mismatches.

### 13.3. Azure Functions Host Integration Test

Run Core Tools locally with Azurite. Send:

~~~bash
curl -i -X POST "http://localhost:7071/api/orders" \
  -H "Content-Type: text/plain" \
  --data " dh-301 "
~~~

Expected per the demo contract: HTTP 202, Queue `order-work` receives `DH-301`, then `processOrder` is triggered by the host and Queue `order-results` receives `DH-301`.

If the host starts without `@QueueTrigger` because the extension is not ready, the test may stop at the HTTP step or fail immediately at startup. Do not claim the pipeline works solely by observing the HTTP response.

### 13.4. Minimum Error Test Matrix

| Test | Expected |
| --- | --- |
| Valid HTTP body | 202, message enqueued, downstream processes properly. |
| Blank HTTP body | 400 and **no** output queue message emitted. |
| Wrong HTTP method | Not invoked as a valid POST. |
| Missing function key on Azure | Rejected according to authorization policy. |
| Blank queue message | Queue Trigger throws an error; verify retry/poison behavior per extension. |
| Queue output lacks write permissions | Invocation fails or output fails to commit; logged/monitored. |
| Multiple messages with same order/event ID | Idempotent consumer, no duplicate side effects. |
| Host restarts mid-pipeline | Data is resumed/reprocessed by design; do not assume exactly-once. |
| Missing Blob file | Blob Input fails with clear categorization and error handling. |
| Timer fires late | Past-due policy / scheduled reconciliation handles it. |
| Event Hubs batch error | Clear per-item or batch/checkpoint handling policy. |

### 13.5. Do Not Confuse Unit Tests with Integration Tests

A `Function<String,String>` transforming data correctly **does not prove**:

- The Azure plugin generated valid `function.json`.
- The Host loaded the Queue/Blob extension properly.
- `AzureWebJobsStorage` has read/write permissions.
- JSON/content types are mapped properly.
- Retries/dead-lettering/idempotency work.
- The Azure Function App Java runtime matches the JDK build bytecode.

Test each layer and run end-to-end tests in a production-like staging environment for critical triggers.

## 14. Errors, Retries, ACKs, and Idempotency

| Trigger | Typical Behavior on Error | What Must Be Designed |
| --- | --- | --- |
| HTTP | Returns error to caller or times out per host/adapter. | HTTP status/schema, request timeout, client retries. |
| Storage Queue | Dequeue retry and poison queue per extension. | Max retries, message encoding, deduplication, and poison-queue monitoring. |
| Service Bus | Message lock/settlement, delivery count, DLQ per broker/extension. | Sessions/ordering, lock duration, duplicate detection/idempotency. |
| Event Hubs | Batch/partition processing and checkpointing per extension. | Replay, partition ordering, errors/retries/throughput. |
| Blob | Event detection/retry per trigger source and extension. | State tracking, file size limits, preventing trigger loops. |
| Timer | Scheduled task without Queue poison-message semantics. | Missed runs, appropriate retries, idempotent scheduled jobs. |

**There is no exactly-once guarantee simply from using Azure Functions or Spring Cloud Function.** Trigger redelivery can cause repeated processing. If a consumer writes to a database, sends emails, or calls payment APIs, use a stable idempotency key such as `eventId` or `orderId + eventVersion` backed by atomic storage/unique constraints.

Do not catch all exceptions, merely log them, and return success in Queue/Service Bus triggers if you expect Azure to retry. Conversely, validation errors cannot be fixed by infinite retries; consider dead-lettering/quarantine with clear reasons.

### 14.1. Where Should Retries Live?

- **In the business handler:** bounded retries/backoff for transient infrastructure calls.
- **In the Azure binding extension:** trigger-specific redelivery/poison policies.
- **In the HTTP client:** callers may retry requests.
- **In downstream brokers:** events may be re-queued by design.

Avoid stacking multiple independent retry layers that multiply attempts far beyond expectations. Set timeouts/deadlines and clarify which layer owns primary retries.

### 14.2. End-to-End Observability

For HTTP -> Queue, generate an `eventId` or `requestId` at ingress and include it in the payload/message contract for tracing. When logging, prefer invocation ID, correlation ID, Azure Function name, status, and error category; avoid logging function keys, connection strings, or private payloads.

Azure `ExecutionContext` belongs to each invocation and should not be retained in a singleton Spring handler. If metadata is needed inside business functions, pass minimal fields via a domain contract or a controlled `Message<T>`.

## 15. Troubleshooting and Design Decisions

| Symptom | Check First |
| --- | --- |
| Azure Host does not see `submitOrder` | `@FunctionName`, `@HttpTrigger`, `public` Java method, Azure plugin, and `function.json`. |
| HTTP 404/405 | Route, `/api` URL prefix, HTTP method, and host configuration. |
| HTTP 401/403 in the cloud | Function key/authorization level, identity/network settings. |
| `FunctionCatalog` fails to inject | `spring-cloud-function-adapter-azure`, Spring main class, auto-configuration/BOM. |
| `catalog.lookup(...)` returns nothing | Bean name, composition, generic types, and component scan. |
| HTTP 202 but queue is empty | Output binding, Storage connection, extension, logs, permissions; do not inspect only the response. |
| Queue Trigger does not run | Wrong queue name/connection, missing extension, encoding, stopped host. |
| Message keeps retrying | Handler throws exception, uncategorized validation error, poison queue policy. |
| `@BlobInput` errors | Path expression, missing file, storage permissions, or `dataType`. |
| Timer does not run on schedule | NCRONTAB, UTC/timezone, host state, plan, and schedule monitoring. |
| Event Hubs processes only some events | Consumer group/partition, batch/cardinality, checkpointing, handler errors. |
| Data processed twice | Retry/redelivery, duplicate messages, missing idempotency. |
| Works locally, cloud fails Java version | JDK target and Azure Functions Java runtime mismatch. |
| Azure Worker fails to load JAR | Boot executable fat JAR layout mismatch, missing Azure plugin output/dependencies. |

### Quick Architecture Selection

- Want the client to **receive the result immediately**: HTTP Trigger returning `HttpResponseMessage` with the result of `Function<T,R>`, clear timeouts, and validation.
- Want to **accept a request and process in the background**: HTTP Trigger + Queue Output + Queue Trigger; return 202 and expose status via an API/event if needed.
- Want to **emit events on a schedule**: Timer Trigger calling `Supplier.get()` + output binding.
- Want to **trigger on files**: Blob Trigger. Want to **read a file for another event**: Queue Trigger + Blob Input.
- Need **message broker features**: Service Bus. Need **high-volume event streams**: Event Hubs.
- Need **multiple EIPs** between steps: you can combine Spring Integration/Stream, but avoid adding unnecessary frameworks to Azure Functions that inflate cold starts.

## 16. Exercises and Self-Assessment Questions

### Exercises

1. Replace `trimCode|upperCode` with two business functions accepting/returning Java records; add JSON validation in the HTTP handler.
2. Add an `eventId` to the message before writing to `order-work`; write an idempotent consumer using a unique key in storage.
3. Migrate `processOrder` to a Service Bus Trigger and compare connections, DLQs, and settlement semantics.
4. Write a Timer Trigger calling `Supplier<String>` to generate a heartbeat and use Queue Output. Verify duplicate emissions when identical data is emitted repeatedly.
5. Create a Queue Trigger receiving a file name and `@BlobInput` reading its contents. Explain why Blob Input does not trigger invocations on its own.
6. Intentionally misconfigure `AzureWebJobsStorage` and observe the difference between host startup errors, output binding errors, and `FunctionCatalog` errors.
7. Add tests for blank bodies, duplicate queue events, retries, and permission failures.
8. Inspect the Azure plugin staging metadata and record the number of triggers and input/output bindings on each Azure Function.

### Self-Assessment

- How many triggers can a single Azure Function have? How many input/output bindings?
- Why is `@QueueOutput` not a `@QueueTrigger`?
- When an HTTP handler returns 202, does that confirm the Queue Trigger has finished processing?
- Why doesn't `Supplier<T>` automatically become a Timer Trigger?
- When should you use `@BlobTrigger` vs. `@BlobInput`?
- How does Azure Storage Queue differ operationally from Service Bus Queue?
- What generates `function.json`, and why is a Spring `@Bean` alone not enough for Azure to discover a function?
- Why is idempotency required when Queue/Service Bus/Event Hubs can redeliver events?
- When should you move from `Function<String,String>` to `Function<OrderRequest,OrderDecision>`?
- Which tests beyond unit tests must be run to confirm a multi-trigger pipeline works end-to-end?

## 17. Official References

- [Spring Cloud Function — Microsoft Azure Functions](https://docs.spring.io/spring-cloud-function/reference/adapters/azure-intro.html): Azure adapter, `@Component`, handler annotations, `FunctionCatalog`, packaging, and local execution.
- [Spring Cloud Function — Programming Model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html): `Supplier`, `Function`, `Consumer`, composition, and conversion.
- [Microsoft Learn — Triggers and Bindings](https://learn.microsoft.com/en-us/azure/azure-functions/functions-triggers-bindings): matrix of supported trigger/input/output bindings.
- [Microsoft Learn — Java Developer Guide](https://learn.microsoft.com/en-us/azure/azure-functions/functions-reference-java): `@FunctionName`, `ExecutionContext`, metadata, and Java annotations.
- [Microsoft Learn — HTTP Trigger](https://learn.microsoft.com/en-us/azure/azure-functions/functions-bindings-http-webhook-trigger): route, request/response, and authorization.
- [Microsoft Learn — Azure Storage Queue Trigger](https://learn.microsoft.com/en-us/azure/azure-functions/functions-bindings-storage-queue-trigger) and [Queue Output](https://learn.microsoft.com/en-us/azure/azure-functions/functions-bindings-storage-queue-output): Queue Trigger, `OutputBinding<T>`, retries, and encoding.
- [Microsoft Learn — Timer Trigger](https://learn.microsoft.com/en-us/azure/azure-functions/functions-bindings-timer): NCRONTAB, timezone, schedule monitoring, and errors.
- [Microsoft Learn — Blob Trigger](https://learn.microsoft.com/en-us/azure/azure-functions/functions-bindings-storage-blob-trigger) and [Blob Input](https://learn.microsoft.com/en-us/azure/azure-functions/functions-bindings-storage-blob-input): file detection and reading supplemental data.
- [Microsoft Learn — Event Hubs Trigger](https://learn.microsoft.com/en-us/azure/azure-functions/functions-bindings-event-hubs-trigger): partitions, consumer groups, and cardinality.
- [Microsoft Learn — Service Bus Trigger](https://learn.microsoft.com/en-us/azure/azure-functions/functions-bindings-service-bus-trigger) and [Service Bus Output](https://learn.microsoft.com/en-us/azure/azure-functions/functions-bindings-service-bus-output): queues/topics, retries, settlement, and dead-lettering.
- [Microsoft Learn — Error Handling and Retries](https://learn.microsoft.com/en-us/azure/azure-functions/functions-bindings-error-pages): retry policies and annotations supported by the runtime.
- [Microsoft Learn — Java Output Binding to Azure Storage](https://learn.microsoft.com/en-us/azure/azure-functions/functions-add-output-binding-storage-queue-java): Java `@QueueOutput` + `OutputBinding<String>` example.

**Conclusion:** **Triggers** decide **when** an Azure Function runs, **input bindings** supply additional data, and **output bindings** deliver results to external systems. With **`spring-cloud-function-adapter-azure`**, Spring component handlers use `FunctionCatalog` to invoke protocol-agnostic `Supplier`, `Function`, or `Consumer` beans; the same function can serve HTTP, Storage Queue, Event Hubs, Service Bus, Timer, or Blob triggers. Clearly separating boundaries, defining connection rules, serialization, retries, idempotency, and testing against the actual host are essential for running serverless systems safely.
