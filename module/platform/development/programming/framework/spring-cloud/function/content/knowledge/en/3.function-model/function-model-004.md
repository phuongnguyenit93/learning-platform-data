# BiFunction and BiConsumer with Payload and a Header Map

In **SPRING_CLOUD_FUNCTION**, business data sometimes lives in the **payload**, while processing also needs the message **headers**: a correlation ID for tracing, event type, content format, or routing info. Spring Cloud Function supports **BiFunction** and **BiConsumer** to receive both the **payload** and a **Map containing headers** without forcing business logic to accept a Spring Messaging `Message<T>` object directly.

This lesson belongs to the **Function Model** chapter. We will progress from the Java contract, Spring Cloud Function's special convention, and testable code examples to usage over HTTP, events, and serverless environments. The focus is on **understanding the second argument properly**, preserving metadata when needed, and controlling errors or side effects.

## 1. BiFunction and BiConsumer in Plain Java

Java provides two functional interfaces:

~~~java
@FunctionalInterface
public interface BiFunction<T, U, R> {
    R apply(T first, U second);
}

@FunctionalInterface
public interface BiConsumer<T, U> {
    void accept(T first, U second);
}
~~~

- **BiFunction<T, U, R>** accepts two arguments **T, U** and returns **R**.
- **BiConsumer<T, U>** accepts two arguments **T, U**, performs processing, and returns **void**.
- In **plain Java**, type **U** can be any type, such as Integer, String, or Map.
- In **Spring Cloud Function's BiFunction/BiConsumer integration model**, the framework-supported case expects **the second argument to be a Map containing message headers**. This is a stricter constraint than the general Java signature.

Simple plain Java example:

~~~java
import java.util.Map;
import java.util.function.BiFunction;
import java.util.function.BiConsumer;

BiFunction<String, Map<String, Object>, String> describe =
    (payload, headers) ->
        payload + " [correlationId=" + headers.get("correlationId") + "]";

BiConsumer<String, Map<String, Object>> logEvent =
    (payload, headers) ->
        System.out.println(headers.get("correlationId") + ": " + payload);

Map<String, Object> metadata = Map.of("correlationId", "trace-001");

String result = describe.apply("ORDER_CREATED", metadata);
logEvent.accept("ORDER_CREATED", metadata);
~~~

When invoked directly in Java, **apply(payload, headers)** and **accept(payload, headers)** behave like two ordinary parameters. When registered as beans in Spring Cloud Function, the framework applies a specific rule to extract both arguments from a **Message**.

## 2. Spring Cloud Function Rule: The Second Argument Must Be a Map

At the transport layer, a message typically has two parts:

~~~text
Message<T>
├── payload: T
└── headers: Map<String, Object>
~~~

Spring Cloud Function detects beans of type **BiFunction<T, Map, R>** or **BiConsumer<T, Map>** by convention:

1. The adapter receives data and provides it as a message with **payload** and **headers**.
2. The framework passes **payload** as the first parameter.
3. The framework passes **headers** as the second parameter of type **Map**.
4. The framework invokes **apply(payload, headers)** or **accept(payload, headers)**.
5. For BiFunction, the result is forwarded to the adapter; for BiConsumer, there is no business result.

~~~mermaid
flowchart LR
    A["HTTP / Broker / Serverless"] --> B["Message<T>"]
    B --> C["payload: T"]
    B --> D["headers: Map"]
    C --> E["BiFunction.apply / BiConsumer.accept"]
    D --> E
    E --> F["BiFunction: result R"]
    E --> G["BiConsumer: side effect"]
~~~

**Mandatory constraint:** the second parameter must be a **Map**; it can be declared more specifically as **Map<String, Object>**. **BiFunction<OrderId, Quantity, Price>** is not automatically interpreted by Spring Cloud Function as two separate business payloads. If multiple business values are needed, wrap them in a single **record/DTO** as the payload.

~~~java
// Matches Spring Cloud Function's payload + headers mechanism:
BiFunction<OrderEvent, Map<String, Object>, OrderView>

// Does not express payload + headers under that convention:
BiFunction<OrderEvent, Integer, OrderView>
~~~

**Do not confuse a headers Map with a payload Map.** A payload can certainly be a **Map<String, Object>**; in that case both payload and headers have type Map, yet they serve **different roles** and occupy two separate arguments:

~~~java
BiFunction<Map<String, Object>, Map<String, Object>, String>
~~~

The signature above specifies Map for both arguments, but it does not clearly express business meaning. If the schema is known, prefer a DTO/record for the payload, such as **OrderEvent**, so code is easier to read and test.

## 3. When Should You Use BiFunction, BiConsumer, and Message<T>?

| Model | Data Received by Logic | Result | When Appropriate |
| --- | --- | --- | --- |
| **Function<T, R>** | Payload only | R | Business transformation without headers |
| **Consumer<T>** | Payload only | void | Processing events without caring about metadata |
| **Function<Message<T>, R>** | Message containing payload and headers | R | Need Spring Messaging API inside logic |
| **Consumer<Message<T>>** | Message containing payload and headers | void | Need to work directly with Message |
| **BiFunction<T, Map<String, Object>, R>** | Payload and headers Map separated | R | Read metadata while keeping signature close to Java/POJO |
| **BiConsumer<T, Map<String, Object>>** | Payload and headers Map separated | void | Handle side effects with tracing/metadata |

Example of two equivalent ways to read metadata:

~~~java
import java.util.function.Function;
import java.util.function.BiFunction;
import java.util.Map;
import org.springframework.messaging.Message;

// Receive the full Message object:
Function<Message<String>, String> byMessage =
    message -> message.getPayload() + "-"
        + message.getHeaders().get("correlationId");

// Receive payload and headers Map separately:
BiFunction<String, Map<String, Object>, String> byBiFunction =
    (payload, headers) -> payload + "-"
        + headers.get("correlationId");
~~~

The second approach avoids forcing business transformation code to call **message.getPayload()** and **message.getHeaders()**. Still, the **headers Map** remains metadata from the transport layer; reading a header does not guarantee its authenticity or integrity.

## 4. End-to-End Example: Processing Order Events with correlationId

Suppose a service receives **OrderEvent** and needs to perform two independent tasks:

- **summarizeOrder:** produce an order summary including a correlation ID to record the request origin.
- **auditOrder:** record an audit entry keyed by **eventId** and store the correlation ID for log lookup.

**eventId** resides in the payload and acts as the business key to reduce duplicate writes; **correlationId** resides in the headers and is used for observability. Do not use correlationId as proof that the caller is authorized to act.

### 4.1. Declaring the Application and Two Beans

Example using Java 17+ and Spring Boot with a compatible Spring Cloud Function version:

~~~java
package example.function;

import java.math.BigDecimal;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.function.BiConsumer;
import java.util.function.BiFunction;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class HeaderFunctionApplication {

    public static void main(String[] args) {
        SpringApplication.run(HeaderFunctionApplication.class, args);
    }

    public record OrderEvent(
        String eventId,
        String orderId,
        BigDecimal amount
    ) {}

    public record OrderView(
        String orderId,
        BigDecimal amount,
        String correlationId
    ) {}

    public record AuditEntry(
        String eventId,
        String orderId,
        String correlationId
    ) {}

    public static class AuditStore {
        private final ConcurrentMap<String, AuditEntry> entries =
            new ConcurrentHashMap<>();

        public boolean recordOnce(AuditEntry entry) {
            return entries.putIfAbsent(entry.eventId(), entry) == null;
        }

        public int size() {
            return entries.size();
        }
    }

    @Bean
    AuditStore auditStore() {
        return new AuditStore();
    }

    @Bean
    BiFunction<OrderEvent, Map<String, Object>, OrderView>
            summarizeOrder() {
        return (event, headers) -> {
            validate(event);

            return new OrderView(
                event.orderId(),
                event.amount(),
                correlationId(headers)
            );
        };
    }

    @Bean
    BiConsumer<OrderEvent, Map<String, Object>>
            auditOrder(AuditStore store) {
        return (event, headers) -> {
            validate(event);

            store.recordOnce(new AuditEntry(
                event.eventId(),
                event.orderId(),
                correlationId(headers)
            ));
        };
    }

    static void validate(OrderEvent event) {
        if (event == null
                || event.eventId() == null
                || event.eventId().isBlank()
                || event.orderId() == null
                || event.orderId().isBlank()
                || event.amount() == null
                || event.amount().signum() < 0) {
            throw new IllegalArgumentException("Invalid order event");
        }
    }

    static String correlationId(Map<String, Object> headers) {
        if (headers == null) {
            return "unavailable";
        }

        Object value = headers.get("correlationId");
        if (value instanceof String text && !text.isBlank()) {
            return text;
        }

        return "unavailable";
    }
}
~~~

In the example:

1. **OrderEvent** is a business payload with a clear schema.
2. **summarizeOrder** has signature **BiFunction<OrderEvent, Map<String,Object>, OrderView>** and returns new data.
3. **auditOrder** has signature **BiConsumer<OrderEvent, Map<String,Object>>** and performs a side effect on **AuditStore**.
4. **correlationId(...)** reads metadata by an explicit key, handling missing or non-String headers.
5. **validate(...)** rejects invalid payloads before transforming or writing audit entries.
6. **recordOnce(...)** uses **eventId** to illustrate preventing duplicate writes within a single instance.

**Limitation of AuditStore:** the **ConcurrentHashMap** store is only for examples and unit tests. It does not persist across application restarts and does not coordinate across multiple instances. When taking a Consumer to production, use a database or shared store with a unique constraint/transaction suitable for **eventId**.

### 4.2. Direct Invocation Without Spring Adapters

You can test both beans as plain Java:

~~~java
var app = new HeaderFunctionApplication();

var event = new HeaderFunctionApplication.OrderEvent(
    "evt-001", "ORD-101", new BigDecimal("250000")
);
Map<String, Object> headers =
    Map.of("correlationId", "trace-123");

var summarize = app.summarizeOrder();
var view = summarize.apply(event, headers);
// view.orderId()       -> "ORD-101"
// view.correlationId() -> "trace-123"

var store = new HeaderFunctionApplication.AuditStore();
var audit = app.auditOrder(store);

audit.accept(event, headers);
audit.accept(event, headers);
System.out.println(store.size()); // 1
~~~

Direct invocation verifies the logic of **BiFunction/BiConsumer**. However, direct testing **does not verify** Spring Cloud Function's mechanism for splitting a **Message** into two arguments; that requires separate integration tests.

## 5. FunctionCatalog: From Message to Two Parameters

A common point of confusion: in Spring Cloud Function, **the bean you declare** is a BiFunction/BiConsumer, but the framework may **wrap the function into a Function accepting a Message** to facilitate conversion, composition, and adapters.

~~~mermaid
flowchart TB
    A["Bean: BiFunction<T, Map, R>"] --> B["FunctionCatalog / wrapper"]
    C["Message<T>"] --> B
    B --> D["Split payload and headers"]
    D --> E["BiFunction.apply(payload, headers)"]
    E --> F["R"]
~~~

Therefore, distinguish **calling the bean directly** from **calling via the catalog/adapter**:

- **Plain Java bean:** uses **apply(payload, headers)** or **accept(payload, headers)**.
- **Catalog/adapter:** passes **Message<T>** to the wrapper so the framework splits it into payload and headers Map. Do not assume the wrapper is always a BiFunction object callable directly with two arguments.
- **Conversion:** the adapter can convert bytes/JSON into payload type T based on the function declaration and content type. If types or headers mismatch, check converter configuration.

Example of a Spring class receiving `FunctionCatalog` via constructor injection and invoking the wrapper with a `Message`:

~~~java
package example.function;

import java.math.BigDecimal;
import java.util.function.Function;

import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Component;

@Component
public class CatalogCaller {
    private final FunctionCatalog catalog;

    public CatalogCaller(FunctionCatalog catalog) {
        this.catalog = catalog;
    }

    public Object invokeSummary() {
        HeaderFunctionApplication.OrderEvent event =
            new HeaderFunctionApplication.OrderEvent(
                "evt-001", "ORD-101", new BigDecimal("250000")
            );

        Message<HeaderFunctionApplication.OrderEvent> message =
            MessageBuilder.withPayload(event)
                .setHeader("correlationId", "trace-123")
                .build();

        Function<Message<HeaderFunctionApplication.OrderEvent>, ?>
            invocation = catalog.lookup("summarizeOrder");

        if (invocation == null) {
            throw new IllegalStateException("Function not found");
        }

        return invocation.apply(message);
    }
}
~~~

The example places **CatalogCaller** as a separate class in the same package as **HeaderFunctionApplication**, while the object returned from the wrapper may need type checking depending on the chosen conversion mechanism. The key takeaway is that **Message** is passed to the catalog, while the BiFunction bean receives **payload** and **headers Map**.

You can select a definition when the application contains multiple functions:

~~~yaml
spring:
  cloud:
    function:
      definition: summarizeOrder
~~~

In an application that only receives events for auditing, the corresponding definition is **auditOrder**. These names must match the registered bean names.

## 6. Headers Is a Map: How to Read It Safely?

Header values are not guaranteed to be Strings. Integration components may store content types, timestamps, IDs, or other metadata in various Java types.

~~~java
Object raw = headers.get("correlationId");

if (raw instanceof String correlationId) {
    System.out.println(correlationId);
}
~~~

Do not cast blindly:

~~~java
// May throw ClassCastException if the header is not a String:
String correlationId = (String) headers.get("correlationId");
~~~

Situations to account for:

| Situation | Consequence | Resolution |
| --- | --- | --- |
| **correlationId** header does not exist | **get(...)** returns null | Have a default value or explicit rejection rule |
| Header has a non-String type | Cast fails | Check type with instanceof or define a converter |
| Header name casing changes | Lookup by name fails | Standardize per adapter contract; test HTTP header mapping |
| Payload Map and headers Map coexist | Easy to read the wrong one | Use a DTO for payload and clear parameter names |
| Header contains sensitive metadata | Logs may leak data | Log only required fields, mask sensitive info |

In particular, **the headers Map supplied by the framework is often MessageHeaders**, which is read-only. Do not modify it directly:

~~~java
// Avoid mutating headers received from a Message:
headers.put("processedBy", "order-service");
~~~

If you need to add or alter output headers, construct a **new Message** instead of attempting to mutate the input Map.

## 7. Preserving or Adding Output Headers

**BiFunction<T, Map, R>** returns **R**. Do not assume all input headers are automatically copied to the output. When business logic needs control over output metadata, you can use **Function<Message<T>, Message<R>>**:

~~~java
import java.util.function.Function;

import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

@Bean
Function<Message<OrderEvent>, Message<OrderView>> summarizeMessage() {
    BiFunction<OrderEvent, Map<String, Object>, OrderView> summary =
        summarizeOrder();

    return input -> {
        OrderView view = summary.apply(
            input.getPayload(),
            input.getHeaders()
        );

        return MessageBuilder.withPayload(view)
            .copyHeaders(input.getHeaders())
            .setHeader("processedBy", "summarizeMessage")
            .build();
    };
}
~~~

Place the **summarizeMessage** bean in the same example configuration class where **OrderEvent**, **OrderView**, and **summarizeOrder** are declared. The snippet creates a new **Message<OrderView>** and explicitly decides which headers are kept or added. If only a few headers are needed, use **setHeader(...)** rather than copying everything. Avoid automatically propagating internal or sensitive headers to external systems.

Spring Cloud Function also offers options like **copy-input-headers** for cases where output metadata needs to be preserved:

~~~yaml
spring:
  cloud:
    function:
      configuration:
        summarizeOrder:
          copy-input-headers: true
~~~

This option does not replace designing a header contract. Verify it against the framework version, adapter, and composition order in use, especially when outputs must strip headers not permitted to propagate.

## 8. Over HTTP: Body Is Payload, Headers Are Metadata

With the Spring Cloud Function web adapter:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-function-web</artifactId>
</dependency>
~~~

Select **summarizeOrder** and start the Spring Boot application:

~~~yaml
spring:
  cloud:
    function:
      definition: summarizeOrder
~~~

Try sending a POST request to the corresponding endpoint when the app uses port 8080:

~~~bash
curl -i -X POST http://localhost:8080/summarizeOrder \
  -H "Content-Type: application/json" \
  -H "correlationId: trace-123" \
  -d '{"eventId":"evt-001","orderId":"ORD-101","amount":250000}'
~~~

Meaning of the request:

- **JSON body** is the data source the adapter converts into **OrderEvent**.
- **Content-Type** helps the adapter choose how to interpret the body.
- **correlationId** is the header the application reads via the Map parameter.
- **BiFunction** returns **OrderView**, which the adapter can serialize to JSON.

Example response when the adapter maps the header as configured:

~~~json
{
  "orderId": "ORD-101",
  "amount": 250000,
  "correlationId": "trace-123"
}
~~~

**Note on header names:** HTTP layers, proxies, servlet containers, and message adapters can alter header name representations. Do not treat the **correlationId** name or case preservation as guaranteed across every environment. In real systems, typically pick a consistent header name like **X-Correlation-Id** and write mappings/tests appropriate for the adapter. If not forwarded, the example logic returns **unavailable**.

Remember that **BiConsumer returns no business data**. If exposing **auditOrder** over HTTP, clients should not expect an **OrderView**; check which HTTP status code the adapter returns on success or when the Consumer throws an exception based on the framework version and configuration.

## 9. Over Spring Cloud Stream: Event Headers and Payload

When processing events from Kafka, RabbitMQ, or another broker, the payload is deserialized into **OrderEvent**, while message headers may contain producer, binder, and tracing metadata.

Example configuration for **auditOrder**:

~~~yaml
spring:
  cloud:
    function:
      definition: auditOrder
    stream:
      bindings:
        auditOrder-in-0:
          destination: orders.created
          group: order-audit
~~~

This is an illustrative **input binding** configuration. The application also needs Spring Cloud Stream, an appropriate binder, a broker, and connection details. **BiConsumer** is adapted by the framework to receive **payload and headers**; exact registration/wrapping and binding behavior should be verified with integration tests for the selected version.

~~~mermaid
flowchart LR
    A["Broker / orders.created"] --> B["Stream binder"]
    B --> C["Message<OrderEvent>"]
    C --> D["payload OrderEvent"]
    C --> E["headers Map"]
    D --> F["auditOrder.accept"]
    E --> F
    F --> G["AuditStore"]
~~~

Unlike HTTP, a message broker can **redeliver a message** after timeouts, retries, or restarts. Therefore:

- Choose a **stable business eventId** inside the payload as the idempotency key.
- Do not rely solely on Message ID/offset or **correlationId** as a deduplication key unless the business contract guarantees their stability.
- When the database write succeeds but acknowledgment fails, the binder may redeliver the event; the Consumer must tolerate duplicates.
- Do not infer **exactly-once** semantics merely because code uses BiConsumer or because the broker has its own transactions.

In the example, **ConcurrentHashMap.putIfAbsent** prevents duplicates while the same instance stays alive. Across multiple instances, you must use unique constraints and transactions in durable storage.

### When Metadata Matters More Than Payload

Some integrations emit special events such as a **tombstone record** in Kafka, where the payload may be empty or carry a deletion marker. Receiving the headers Map separately can be useful for accessing metadata when handling null payloads. However, how an adapter represents null/tombstone depends on the binder, serializer type, and version. Never assume an **OrderEvent record** always exists in this case; design a dedicated branch or appropriate handler when the workflow supports tombstones.

## 10. Serverless Uses the Same Function Contract

A serverless runtime can convert an incoming event into a Message and pass it into the Spring Cloud Function adapter:

~~~text
Cloud invocation / event
  -> adapter
  -> Message<OrderEvent>
  -> payload + headers
  -> summarizeOrder or auditOrder
  -> return result / side effect
~~~

The reusable part is **the business signature**. Calculation or audit code does not need to directly read HTTP requests or broker APIs. However, serverless still requires a **handler**, adapter dependencies, packaging, event mapping rules, timeouts, and permissions appropriate for the platform.

A serverless event may not include a header named **correlationId** by default. If correlation metadata is needed, determine how the adapter maps information from the **event envelope** or runtime context into the headers Map, and write integration tests to verify it. Do not assume all provider metadata is already populated in the Map just like HTTP.

## 11. Composition When One Step Needs Metadata

Spring Cloud Function allows chaining functions sequentially with **|** when data types and processing contracts align. For a chain containing a BiFunction that needs headers, consider **whether the headers still exist after the preceding step**.

For example, an input normalization step can take a Message and return a Message to **preserve headers**:

~~~java
import java.util.function.Function;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

@Bean
Function<Message<OrderEvent>, Message<OrderEvent>>
        normalizeOrderMessage() {
    return message -> {
        OrderEvent original = message.getPayload();

        OrderEvent normalized = new OrderEvent(
            original.eventId(),
            original.orderId().trim(),
            original.amount()
        );

        return MessageBuilder.withPayload(normalized)
            .copyHeaders(message.getHeaders())
            .build();
    };
}
~~~

Then configure the intended chain:

~~~yaml
spring:
  cloud:
    function:
      definition: normalizeOrderMessage|summarizeOrder
~~~

Processing flow:

~~~mermaid
flowchart LR
    A["Message<OrderEvent>"] --> B["normalizeOrderMessage"]
    B --> C["Message<OrderEvent> with headers"]
    C --> D["BiFunction summarizeOrder"]
    D --> E["OrderView"]
~~~

Because the first step returns a Message with copied headers, the BiFunction step can read **correlationId** after the payload has been normalized. Test real composition in the target Spring Cloud Function version, especially conversion, wrapper types, and headers added by the adapter.

Do not treat **BiFunction<T, Map, R>** as a pipeline with two independent business inputs. If an earlier step must produce both payload and metadata, construct a new **Message** to represent that boundary.

## 12. BiConsumer and Side Effects: Retries, Security, Consistency

With BiConsumer, headers usually support **tracing** or **technical decisions**, while side-effect data must rely on a validated business contract.

Example scenario:

~~~text
T1: Receive eventId=evt-001, correlationId=trace-123
T2: auditOrder writes successfully to database
T3: Acknowledgment to broker fails
T4: Broker redelivers eventId=evt-001, correlationId may differ
T5: Audit checks eventId already exists and skips duplicate write
~~~

If correlationId were used as the idempotency key, data could be duplicated at step T5. **EventId** or a reliable stable business key should guard side effects.

### Implementation Principles

| Topic | Practice | Why |
| --- | --- | --- |
| **Untrusted headers** | Never use caller-supplied headers to decide access rights or data ownership | Headers can be spoofed |
| **Validation** | Verify DTO, required fields, and metadata types before executing side effects | Prevent writing bad data |
| **Idempotency** | Use business keys, unique constraints/transactions | Tolerate redeliveries and concurrent execution |
| **Retries** | Retry only transient errors, with limits and backoff | Avoid infinite retries on invalid data |
| **Dead-letter / errors** | Configure per broker, binder, and operational policy | Prevent losing or endlessly looping messages |
| **Observability** | Log eventId and normalized correlationId; avoid sensitive data | Trace a request across multiple services |
| **Immutability** | Do not mutate the input headers Map | MessageHeaders may be read-only |
| **Header propagation** | Copy only genuinely needed metadata | Avoid leaking internal headers to other systems |

**Exceptions inside accept(...)** do not by themselves determine how HTTP maps to status codes or how a broker retries. The adapter/binder layer and error-handling configuration govern this. Do not catch all exceptions only to silently ignore them when the transport system needs to know about failures.

When a BiConsumer both updates a database and calls an external API, a state where only one side effect succeeds can occur. If an event must be emitted after a database transaction commits, consider a transactional outbox; for external HTTP APIs, use idempotency keys and appropriate compensating mechanisms.

## 13. Common Pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| BiFunction with String/Integer second argument not recognized as expected | Framework convention expects second argument to be headers Map | Use **Map<String, Object>**, wrap multiple business fields in payload DTO |
| Reading header returns null | Wrong name, missing header, or adapter did not map it | Check actual headers via integration tests |
| **ClassCastException** when reading header | Assuming every header value is a String | Check type with **instanceof** or an explicit converter |
| **UnsupportedOperationException** when calling **put** on headers | Read-only header map | Build a new Message with updated headers |
| Header present in input but lost after Function | No propagation strategy configured | Return Message explicitly or configure copy-input-headers per version |
| Looking up catalog as BiFunction and calling with two args fails | Wrapper may accept Message and be exposed as Function | Distinguish original bean and wrapper; test via catalog |
| Expected output binding not created | Using void-returning BiConsumer in a pipeline that must emit data | Use BiFunction/Function if business output is needed; verify bindings |
| Audit written twice | Retries/redelivery, missing idempotency key | Use stable eventId + unique constraint in storage |
| correlationId header trusted as identity | Confusing metadata with authentication info | Use the environment's authentication/authorization mechanism |
| Bean unit tests pass but HTTP/Stream fails | Tests bypassed conversion or message adapter | Add integration tests for payload, headers, and bindings |

## 14. Testing BiFunction and BiConsumer

### 14.1. Direct Unit Tests: Payload and Headers

JUnit 5 example based on **HeaderFunctionApplication**:

~~~java
package example.function;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;
import java.util.Map;
import org.junit.jupiter.api.Test;

class HeaderFunctionApplicationTest {

    private final HeaderFunctionApplication app =
        new HeaderFunctionApplication();

    private HeaderFunctionApplication.OrderEvent validEvent() {
        return new HeaderFunctionApplication.OrderEvent(
            "evt-001", "ORD-101", new BigDecimal("250000")
        );
    }

    @Test
    void biFunctionReadsCorrelationIdFromMap() {
        var summary = app.summarizeOrder();

        var result = summary.apply(
            validEvent(),
            Map.of("correlationId", "trace-123")
        );

        assertEquals("ORD-101", result.orderId());
        assertEquals("trace-123", result.correlationId());
    }

    @Test
    void biFunctionHandlesMissingHeader() {
        var result = app.summarizeOrder().apply(
            validEvent(),
            Map.of()
        );

        assertEquals("unavailable", result.correlationId());
    }

    @Test
    void biConsumerDoesNotDuplicateEventId() {
        var store = new HeaderFunctionApplication.AuditStore();
        var audit = app.auditOrder(store);

        audit.accept(validEvent(), Map.of("correlationId", "trace-123"));
        audit.accept(validEvent(), Map.of("correlationId", "trace-456"));

        assertEquals(1, store.size());
    }

    @Test
    void invalidEventDoesNotCreateSideEffect() {
        var store = new HeaderFunctionApplication.AuditStore();

        var invalid = new HeaderFunctionApplication.OrderEvent(
            "evt-002", "ORD-102", new BigDecimal("-1")
        );

        assertThrows(IllegalArgumentException.class,
            () -> app.auditOrder(store).accept(invalid, Map.of()));

        assertEquals(0, store.size());
    }
}
~~~

These tests confirm the Java signatures, header handling rules, and side effects of both beans; they **do not verify** how the framework splits a Message into two arguments in HTTP/Stream.

### 14.2. What Should Integration Tests Verify?

An integration test for Spring Cloud Function should spin up a real Spring application context and invoke the catalog or adapter using **MessageBuilder.withPayload(...)** with illustrative headers. Items to verify:

1. The BiFunction/BiConsumer bean appears with the **exact name** in FunctionCatalog.
2. The wrapper accepts a Message, mapping **OrderEvent** to payload and the Map to headers.
3. The **correlationId** header travels from the request/event to the second parameter.
4. The JSON payload deserializes into the right type, including when fields are missing or content type is wrong.
5. BiFunction results serialize properly; BiConsumer is not mistakenly treated as a result-producing source.
6. With Stream, input bindings, retries, idempotency, and acknowledgments match the actual binder.
7. When using composition, headers remain intact across steps according to the desired contract.

Only by passing through the adapter can you verify the accuracy of **payload + headers** mapping from external protocols. This is especially important when upgrading Spring Boot/Spring Cloud Function versions or switching binders.

## 15. Practice Exercises

**Exercise 1 — BiFunction with metadata.** Create a **BiFunction<PaymentEvent, Map<String,Object>, PaymentSummary>** that reads the **correlationId** header and returns the transaction ID, total amount, and correlation ID. Test both when the header is present and when it is missing.

**Exercise 2 — BiConsumer writing audit logs.** Create a **BiConsumer<PaymentEvent, Map<String,Object>>** that writes audit entries to a store. The same **eventId** arriving twice with different correlationIds must be recorded only once. Explain why correlationId must not be used as the idempotency key in this scenario.

**Exercise 3 — Message and propagation.** Convert Exercise 1 into a **Function<Message<PaymentEvent>, Message<PaymentSummary>>**. Preserve only **correlationId**, add a **processedBy** header, and do not copy unnecessary sensitive headers.

**Exercise 4 — Distinguishing two-input patterns.** A requirement needs to compute a total from **quantity** and **unitPrice**. Explain why **BiFunction<Integer, BigDecimal, BigDecimal>** does not fit Spring Cloud Function's payload+headers convention. Propose a **PriceRequest(quantity, unitPrice)** DTO and the proper Function or BiFunction signature.

**Exercise 5 — Switching protocols.** Keep the **auditOrder** bean unchanged. Write a Spring Cloud Stream binding configuration to consume events from a broker; identify the integration tests needed when moving to a serverless trigger, especially for mapping correlationId and handling retries.

### Key Takeaways

- In plain Java, **BiFunction<T, U, R>** accepts two arguments and returns **R**; **BiConsumer<T, U>** accepts two arguments and returns **void**.
- In **Spring Cloud Function**, the supported convention is **BiFunction<T, Map, R>** and **BiConsumer<T, Map>**: **the first parameter receives payload, and the second parameter receives the headers Map**.
- The framework can wrap beans to accept **Message<T>**, splitting payload and headers before invocation. Distinguish the **original bean** from the object looked up from **FunctionCatalog**.
- The headers Map is for reading metadata; do not mutate input headers or treat client-supplied headers as authenticated data.
- **BiFunction** fits cases needing output; **BiConsumer** fits side effects. Header preservation, composition, retries, and idempotency must be designed around the adapter and business rules.

### References

- [Spring Cloud Function — Programming model, BiFunction section](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html): rules for splitting payload and headers Map for BiFunction/BiConsumer.
