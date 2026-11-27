# Adding Metadata and Verifying Header Propagation Rules

## 1. Practice Problem

In **Spring Cloud Function** (`SPRING_CLOUD_FUNCTION`), business logic is packaged into `Supplier`, `Function`, or `Consumer` beans and managed by `FunctionCatalog` so it can be reused across HTTP, event-driven systems, or serverless environments. When a function receives data, sometimes the payload alone is not enough for processing or tracing: the application also needs **metadata** such as correlation IDs, source systems, content types, and processing traces.

For example, a system receives order requests:

~~~json
{
  "orderId": "O-501",
  "amountVnd": 750000,
  "source": "PARTNER-A"
}
~~~

The payload describes **the order**. Headers describe **the message context**:

| Header | Meaning | Usage in Lab |
| --- | --- | --- |
| `correlationId` | Links multiple messages/steps belonging to the same business flow | Preserved from input to output |
| `sourceSystem` | Source system that sent the message | Preserved for origin tracing |
| `contentType` | Payload format, e.g., JSON | Reset appropriately for output |
| `receivedBy` | Component that received/enriched the message | Added at the first stage |
| `processedBy` | Component that produced the result | Added at the processing stage |
| `authorization` | Sensitive authentication credentials if present | Not copied to output |

We will build the pipeline:

~~~text
Message<OrderRequest>
  payload + correlationId + sourceSystem
                |
                v
          enrichMetadata
       - keep correlationId
       - keep sourceSystem
       - add receivedBy
       - contentType = application/json
                |
                v
          processOrder
       - read OrderRequest
       - build OrderReceipt
       - keep allowed metadata
       - add processedBy
                |
                v
         formatReceipt
       - turn payload into String
       - keep correlationId
       - contentType = text/plain
                |
                v
Message<String>
~~~

**Goal of this lesson:** learn how to add metadata, control which headers propagate between stages, and test using Spring Messaging and `FunctionCatalog`. We will deliberately choose which headers to keep rather than assuming every header from the producer must be forwarded.

After this lesson, you will be able to:

1. Distinguish payload, message headers, and business metadata.
2. Construct new messages with `MessageBuilder`.
3. Retain an allowlist of permitted headers across each stage.
4. Update `contentType` when the payload type changes.
5. Preserve `correlationId` to trace processing flows.
6. Avoid accidentally forwarding sensitive or internal headers.
7. Verify headers with JUnit and `FunctionCatalog`.
8. Distinguish catalog testing from HTTP/binder header-mapping tests.

> **Scope:** The lab uses Java 17, Spring Boot, and Spring Cloud Function in a single application context. No broker, database, or cloud account is required. The Maven commands are for learners to run in the sample project; the lesson does not require running a build on the content-authoring machine.

## 2. How Do Payload and Metadata Differ?

A Spring `Message<T>` has two parts:

- **Payload:** the core data processed by the function, of type `T`.
- **Headers:** metadata describing the message and transport context.

~~~text
Message<OrderRequest>
  +--------------------------------------+
  | Headers                              |
  |  correlationId = "corr-501"          |
  |  sourceSystem  = "partner-a"         |
  |  contentType   = application/json    |
  +--------------------------------------+
  | Payload                              |
  |  OrderRequest("O-501", 750000, ...)  |
  +--------------------------------------+
~~~

Do not put everything into headers. For example:

| Information | Proper Location | Reason |
| --- | --- | --- |
| Order ID | Payload | Business data that must be validated and stored |
| Amount | Payload | Directly affects business logic |
| Correlation ID | Header | Metadata used to link multiple messages |
| Content type | Header | Describes how to read the payload |
| Processing component | Header | Observability/tracing information |
| Secret token | Security context/secure transport | Should not leak through output messages or logs |
| User permissions | Authenticated security context | Never trust a self-declared header sent by a producer |

**Principle:** headers add context to the payload; they do not replace the business schema. If a field is needed to calculate pricing, approve, or persist an order, place it in the payload and validate it with explicit types and validation rules.

## 3. Header Propagation Rules to Verify

In a multi-function pipeline, distinguish three things:

1. **Does the function receive a Message?** If the signature is `Function<OrderRequest, OrderReceipt>`, the function receives the typed payload; it does not read headers directly as a separate parameter.
2. **Does the function return a Message?** If the signature is `Function<Message<OrderRequest>, Message<OrderReceipt>>`, the function can read headers and produce an output message with metadata.
3. **Does the adapter/binder preserve headers on the wire?** This also depends on the adapter, broker, and header mapping configuration; catalog tests alone do not prove it.

### 3.1. Use Message<T> When Business Logic Needs Metadata

A payload-only signature:

~~~java
Function<OrderRequest, OrderReceipt>
~~~

fits when logic only needs order data.

A message-aware signature:

~~~java
Function<Message<OrderRequest>, Message<OrderReceipt>>
~~~

fits when the function needs to read or write metadata. Not every function should take `Message<?>`: if headers are unused, direct payload types are simpler and easier to reuse.

### 3.2. Headers Are Not a Directly Mutable Map

`MessageHeaders` is an immutable header structure. Do not write:

~~~java
// Do not mutate the input message's MessageHeaders directly.
input.getHeaders().put("processedBy", "order-processor");
~~~

Instead, build a new message using `MessageBuilder`:

~~~java
Message<OrderReceipt> output = MessageBuilder
        .withPayload(receipt)
        .setHeader("correlationId", correlationId)
        .build();
~~~

Creating a new message lets us **explicitly choose the payload and metadata** for the next stage.

### 3.3. Copy All Headers or Only Selected Ones?

Spring Messaging offers APIs like `MessageBuilder.fromMessage(...)` and `copyHeaders(...)` to copy headers. That is convenient when you genuinely want to forward all metadata.

~~~java
Message<?> output = MessageBuilder
        .withPayload(newPayload)
        .copyHeaders(input.getHeaders())
        .build();
~~~

However, in an application with multiple producers and adapters, copying all headers can accidentally propagate:

- Authentication headers or sensitive data.
- Internal binder/framework headers that make no sense on output.
- A stale content type header that no longer matches the new payload.
- Routing headers that should not affect downstream stages.

This lab uses a **header allowlist**: copy only names permitted by the application, then reset the content type for the output. This makes the contract between stages explicit.

## 4. Preparing the Maven Project

The lab uses **JDK 17**, **Maven 3.9+**, **Spring Boot 3.5.0**, and **Spring Cloud 2025.0.0** as a reference baseline for dependencies. This reference setup keeps all snippets on a consistent version set; when starting a new project, choose supported patches and a BOM compatible with your Spring Boot version.

Create the directory `message-metadata-lab`:

~~~text
message-metadata-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/metadata/
    │   │   ├── MetadataLabApplication.java
    │   │   ├── OrderRequest.java
    │   │   ├── OrderReceipt.java
    │   │   ├── OrderPolicy.java
    │   │   ├── HeaderNames.java
    │   │   ├── HeaderPolicy.java
    │   │   └── OrderMessageFunctions.java
    │   └── resources/application.yml
    └── test/java/com/example/metadata/
        ├── OrderPolicyTest.java
        ├── HeaderPolicyTest.java
        └── MessageMetadataCatalogTest.java
~~~

All classes live in package `com.example.metadata` so Spring Boot can scan configurations and functional beans.

### 4.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>message-metadata-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>message-metadata-lab</name>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework.cloud</groupId>
                <artifactId>spring-cloud-dependencies</artifactId>
                <version>2025.0.0</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-function-context</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Dependencies:

| Artifact | Role |
| --- | --- |
| `spring-boot-starter` | Spring ApplicationContext |
| `spring-cloud-function-context` | `FunctionCatalog` and functional beans |
| `spring-boot-starter-test` | JUnit 5, Spring Boot Test, and assertions |

No web adapter or binder is needed for the tests in this lesson. If you later run over HTTP or a broker, add the corresponding adapter and integration tests.

## 5. Creating the Business Payloads

### 5.1. OrderRequest.java

~~~java
package com.example.metadata;

public record OrderRequest(
        String orderId,
        long amountVnd,
        String source) {
}
~~~

### 5.2. OrderReceipt.java

~~~java
package com.example.metadata;

public record OrderReceipt(
        String orderId,
        String status,
        long amountVnd) {
}
~~~

Payloads are strongly typed records. Headers do not need to duplicate `orderId` or `amountVnd` because those fields belong to the business schema.

### 5.3. OrderPolicy.java

~~~java
package com.example.metadata;

import java.util.Locale;

public final class OrderPolicy {

    private OrderPolicy() {
    }

    public static OrderReceipt process(OrderRequest order) {
        if (order == null) {
            throw new IllegalArgumentException("order is required");
        }
        if (order.orderId() == null || order.orderId().isBlank()) {
            throw new IllegalArgumentException("orderId is required");
        }
        if (order.source() == null || order.source().isBlank()) {
            throw new IllegalArgumentException("source is required");
        }
        if (order.amountVnd() <= 0) {
            throw new IllegalArgumentException("amountVnd must be positive");
        }

        return new OrderReceipt(
                order.orderId().trim().toUpperCase(Locale.ROOT),
                "ACCEPTED",
                order.amountVnd());
    }
}
~~~

This is pure Java business logic. It does not accept `Message<?>`, does not read `correlationId`, and has no Spring dependencies. If you later switch from HTTP to Kafka or serverless, the order processing rules remain reusable.

**Locale note:** For identifiers containing letters that need case normalization, prefer `toUpperCase(Locale.ROOT)` rather than relying on the machine's default locale. This lesson keeps the snippet concise; you can enforce an explicit locale in exercises.

## 6. Declaring Header Names and the Allowlist Policy

### 6.1. HeaderNames.java

~~~java
package com.example.metadata;

public final class HeaderNames {

    private HeaderNames() {
    }

    public static final String CORRELATION_ID = "correlationId";
    public static final String SOURCE_SYSTEM = "sourceSystem";
    public static final String RECEIVED_BY = "receivedBy";
    public static final String PROCESSED_BY = "processedBy";
    public static final String AUTHORIZATION = "authorization";
}
~~~

Centralizing header names prevents typos across producers, functions, and tests. `correlationId` is the **flow correlation identifier**, distinct from `MessageHeaders.ID` which identifies an individual message instance.

### 6.2. HeaderPolicy.java

~~~java
package com.example.metadata;

import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public final class HeaderPolicy {

    private HeaderPolicy() {
    }

    @SafeVarargs
    public static <T> MessageBuilder<T> withAllowedHeaders(
            Message<?> input,
            T payload,
            String... allowedNames) {

        MessageBuilder<T> builder = MessageBuilder.withPayload(payload);

        for (String name : allowedNames) {
            Object value = input.getHeaders().get(name);
            if (value != null) {
                builder.setHeader(name, value);
            }
        }

        return builder;
    }
}
~~~

This method:

1. Creates a new message with the new payload.
2. Iterates over the permitted header names.
3. Copies only headers whose values are non-`null`.
4. Does not automatically copy all headers from the input.

Thus, even if a producer includes `authorization`, `spring.cloud.function.definition`, or an unlisted internal header, none of them will leak into the output message.

**Note:** `@SafeVarargs` is valid here because the method is `static` and takes a `String` varargs parameter (a reifiable type). You can omit this annotation if you prefer minimal code; it does not change behavior.

### 6.3. Why Not Copy All Headers?

Suppose the input message contains:

~~~text
correlationId = corr-501
sourceSystem  = partner-a
authorization = Bearer secret-token
debug         = true
spring.cloud.function.definition = internalAdmin
~~~

The output should keep only essential metadata:

~~~text
correlationId = corr-501
sourceSystem  = partner-a
receivedBy    = order-intake-v1
processedBy   = order-processor-v1
contentType   = application/json
~~~

The `authorization` header is not propagated further. The `debug` and routing definition headers are also unnecessary on the result payload. That is why we enforce an allowlist.

## 7. Building Functions That Accept and Return Messages

Create `OrderMessageFunctions.java`:

~~~java
package com.example.metadata;

import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.util.MimeTypeUtils;

@Configuration(proxyBeanMethods = false)
public class OrderMessageFunctions {

    @Bean
    public Function<Message<OrderRequest>, Message<OrderRequest>>
            enrichMetadata() {

        return input -> {
            OrderRequest order = input.getPayload();

            MessageBuilder<OrderRequest> builder =
                    HeaderPolicy.withAllowedHeaders(
                            input,
                            order,
                            HeaderNames.CORRELATION_ID,
                            HeaderNames.SOURCE_SYSTEM);

            builder.setHeader(
                    HeaderNames.RECEIVED_BY,
                    "order-intake-v1");
            builder.setHeader(
                    MessageHeaders.CONTENT_TYPE,
                    MimeTypeUtils.APPLICATION_JSON);

            return builder.build();
        };
    }

    @Bean
    public Function<Message<OrderRequest>, Message<OrderReceipt>>
            processOrder() {

        return input -> {
            OrderReceipt receipt =
                    OrderPolicy.process(input.getPayload());

            MessageBuilder<OrderReceipt> builder =
                    HeaderPolicy.withAllowedHeaders(
                            input,
                            receipt,
                            HeaderNames.CORRELATION_ID,
                            HeaderNames.SOURCE_SYSTEM,
                            HeaderNames.RECEIVED_BY);

            builder.setHeader(
                    HeaderNames.PROCESSED_BY,
                    "order-processor-v1");
            builder.setHeader(
                    MessageHeaders.CONTENT_TYPE,
                    MimeTypeUtils.APPLICATION_JSON);

            return builder.build();
        };
    }

    @Bean
    public Function<Message<OrderReceipt>, Message<String>>
            formatReceipt() {

        return input -> {
            OrderReceipt receipt = input.getPayload();
            String text = "ORDER=" + receipt.orderId()
                    + ";STATUS=" + receipt.status()
                    + ";AMOUNT=" + receipt.amountVnd();

            MessageBuilder<String> builder =
                    HeaderPolicy.withAllowedHeaders(
                            input,
                            text,
                            HeaderNames.CORRELATION_ID,
                            HeaderNames.RECEIVED_BY,
                            HeaderNames.PROCESSED_BY);

            builder.setHeader(
                    MessageHeaders.CONTENT_TYPE,
                    MimeTypeUtils.TEXT_PLAIN);

            return builder.build();
        };
    }
}
~~~

### 7.1. Analyzing the enrichMetadata Stage

Signature:

~~~java
Function<Message<OrderRequest>, Message<OrderRequest>>
~~~

This stage receives the order payload along with headers, then builds a new message. It:

- Retains `correlationId` and `sourceSystem` if present.
- Adds server-controlled `receivedBy`.
- Sets `contentType` to `application/json`.
- Drops `authorization` and any routing headers not in the allowlist.

This stage does not modify order data; it only enriches metadata.

### 7.2. Analyzing the processOrder Stage

Signature:

~~~java
Function<Message<OrderRequest>, Message<OrderReceipt>>
~~~

This stage calls `OrderPolicy.process` on the payload. After producing the receipt, it copies the three allowed headers and adds `processedBy`. This is where the payload type changes from `OrderRequest` to `OrderReceipt`.

### 7.3. Analyzing the formatReceipt Stage

Signature:

~~~java
Function<Message<OrderReceipt>, Message<String>>
~~~

This stage turns the payload into a plain string, so it updates `contentType` to `text/plain`. If it kept `application/json` while emitting plain text, downstream consumers could pick the wrong converter or misinterpret the body.

### 7.4. Why Must Each Stage Explicitly Copy Headers?

Every stage constructs a brand-new output message. By calling `HeaderPolicy.withAllowedHeaders`, we state explicitly:

- Which metadata is carried forward.
- Which metadata is dropped.
- Which headers must change when the payload type changes.

If a later stage fails to copy `correlationId`, that metadata vanishes from the output message produced by that stage. Therefore, header propagation rules are **part of each stage's contract** and must be tested rather than assumed.

## 8. Initializing Spring Boot

Create `MetadataLabApplication.java`:

~~~java
package com.example.metadata;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MetadataLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                MetadataLabApplication.class, args);
    }
}
~~~

Create `src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: message-metadata-lab
  cloud:
    function:
      single-function-fallback-enabled: false
~~~

No `spring.cloud.function.definition` is needed for catalog tests: we want to look up individual functions and composition chains directly through `FunctionCatalog`. When wiring the pipeline into a specific adapter, add the function/binding configuration at deployment time.

## 9. Unit Tests for Business Logic

Create `OrderPolicyTest.java`:

~~~java
package com.example.metadata;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class OrderPolicyTest {

    @Test
    void processesValidOrder() {
        OrderReceipt result = OrderPolicy.process(
                new OrderRequest("O-501", 750_000L, "PARTNER-A"));

        assertEquals(
                new OrderReceipt("O-501", "ACCEPTED", 750_000L),
                result);
    }

    @Test
    void rejectsMissingOrderId() {
        assertThrows(IllegalArgumentException.class,
                () -> OrderPolicy.process(
                        new OrderRequest(" ", 100L, "PARTNER-A")));
    }

    @Test
    void rejectsNonPositiveAmount() {
        assertThrows(IllegalArgumentException.class,
                () -> OrderPolicy.process(
                        new OrderRequest("O-502", 0L, "PARTNER-A")));
    }
}
~~~

This unit test does not require Spring. It proves the business rules are independent of message metadata.

## 10. Unit Tests for HeaderPolicy and MessageHeaders

Create `HeaderPolicyTest.java`:

~~~java
package com.example.metadata;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;

class HeaderPolicyTest {

    @Test
    void copiesOnlyAllowedHeaders() {
        Message<String> input = MessageBuilder
                .withPayload("input")
                .setHeader(HeaderNames.CORRELATION_ID, "corr-501")
                .setHeader(HeaderNames.SOURCE_SYSTEM, "partner-a")
                .setHeader(HeaderNames.AUTHORIZATION, "secret-token")
                .setHeader("debug", true)
                .build();

        Message<String> output = HeaderPolicy
                .withAllowedHeaders(
                        input,
                        "output",
                        HeaderNames.CORRELATION_ID,
                        HeaderNames.SOURCE_SYSTEM)
                .build();

        assertEquals("corr-501",
                output.getHeaders().get(HeaderNames.CORRELATION_ID));
        assertEquals("partner-a",
                output.getHeaders().get(HeaderNames.SOURCE_SYSTEM));
        assertNull(output.getHeaders().get(HeaderNames.AUTHORIZATION));
        assertNull(output.getHeaders().get("debug"));
    }

    @Test
    void messageHeadersAreNotMutable() {
        Message<String> message = MessageBuilder
                .withPayload("payload")
                .build();

        assertThrows(UnsupportedOperationException.class,
                () -> message.getHeaders().put("newHeader", "value"));
    }

    @Test
    void sourceMessageIsNotChangedWhenOutputIsBuilt() {
        Message<String> input = MessageBuilder
                .withPayload("before")
                .setHeader(HeaderNames.CORRELATION_ID, "corr-502")
                .build();

        Message<String> output = HeaderPolicy
                .withAllowedHeaders(
                        input,
                        "after",
                        HeaderNames.CORRELATION_ID)
                .build();

        assertEquals("before", input.getPayload());
        assertEquals("after", output.getPayload());
        assertEquals("corr-502",
                input.getHeaders().get(HeaderNames.CORRELATION_ID));
        assertEquals("corr-502",
                output.getHeaders().get(HeaderNames.CORRELATION_ID));
    }
}
~~~

These three tests verify three rules:

1. Headers are copied only if their names appear in the allowlist.
2. `MessageHeaders` on an existing message cannot be mutated directly.
3. Building an output message does not mutate the payload or headers of the input message.

Do not assert that `MessageHeaders.ID` or `timestamp` stays unchanged. Those are Spring-managed per-message metadata and may be regenerated when a new message is created. `correlationId` is an application business/tracing header that should be preserved according to the application's contract.

## 11. Testing FunctionCatalog and Composition

Create `MessageMetadataCatalogTest.java`:

~~~java
package com.example.metadata;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;

import java.util.function.Function;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.util.MimeTypeUtils;

@SpringBootTest(
        classes = MetadataLabApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class MessageMetadataCatalogTest {

    @Autowired
    private FunctionCatalog catalog;

    private Message<OrderRequest> inputMessage() {
        return MessageBuilder
                .withPayload(new OrderRequest(
                        "O-501", 750_000L, "PARTNER-A"))
                .setHeader(HeaderNames.CORRELATION_ID, "corr-501")
                .setHeader(HeaderNames.SOURCE_SYSTEM, "partner-a")
                .setHeader(
                        MessageHeaders.CONTENT_TYPE,
                        MimeTypeUtils.APPLICATION_JSON)
                .setHeader(HeaderNames.AUTHORIZATION, "secret-token")
                .setHeader(
                        "spring.cloud.function.definition",
                        "internalFunction")
                .build();
    }

    @Test
    void enrichesMetadataWithoutChangingPayload() {
        Function<Message<OrderRequest>, Message<OrderRequest>> function =
                catalog.lookup("enrichMetadata");
        assertNotNull(function);

        Message<OrderRequest> input = inputMessage();
        Message<OrderRequest> output = function.apply(input);

        assertEquals(input.getPayload(), output.getPayload());
        assertEquals("corr-501",
                output.getHeaders().get(HeaderNames.CORRELATION_ID));
        assertEquals("partner-a",
                output.getHeaders().get(HeaderNames.SOURCE_SYSTEM));
        assertEquals("order-intake-v1",
                output.getHeaders().get(HeaderNames.RECEIVED_BY));
        assertEquals(
                MimeTypeUtils.APPLICATION_JSON,
                output.getHeaders().get(MessageHeaders.CONTENT_TYPE));
        assertNull(output.getHeaders().get(HeaderNames.AUTHORIZATION));
        assertNull(output.getHeaders().get(
                "spring.cloud.function.definition"));
    }

    @Test
    void processOrderPreservesAllowedMetadataAndAddsProcessor() {
        Function<Message<OrderRequest>, Message<OrderReceipt>> function =
                catalog.lookup("processOrder");
        assertNotNull(function);

        Message<OrderReceipt> output =
                function.apply(inputMessage());

        assertEquals(
                new OrderReceipt("O-501", "ACCEPTED", 750_000L),
                output.getPayload());
        assertEquals("corr-501",
                output.getHeaders().get(HeaderNames.CORRELATION_ID));
        assertEquals("partner-a",
                output.getHeaders().get(HeaderNames.SOURCE_SYSTEM));
        assertEquals("order-processor-v1",
                output.getHeaders().get(HeaderNames.PROCESSED_BY));
        assertEquals(
                MimeTypeUtils.APPLICATION_JSON,
                output.getHeaders().get(MessageHeaders.CONTENT_TYPE));
        assertNull(output.getHeaders().get(HeaderNames.AUTHORIZATION));
    }

    @Test
    void compositionCarriesCorrelationAcrossStages() {
        Function<Message<OrderRequest>, Message<OrderReceipt>> pipeline =
                catalog.lookup("enrichMetadata|processOrder");
        assertNotNull(pipeline);

        Message<OrderReceipt> output =
                pipeline.apply(inputMessage());

        assertEquals("O-501", output.getPayload().orderId());
        assertEquals("corr-501",
                output.getHeaders().get(HeaderNames.CORRELATION_ID));
        assertEquals("order-intake-v1",
                output.getHeaders().get(HeaderNames.RECEIVED_BY));
        assertEquals("order-processor-v1",
                output.getHeaders().get(HeaderNames.PROCESSED_BY));
    }

    @Test
    void fullCompositionUpdatesContentTypeWhenPayloadChanges() {
        Function<Message<OrderRequest>, Message<String>> pipeline =
                catalog.lookup(
                        "enrichMetadata|processOrder|formatReceipt");
        assertNotNull(pipeline);

        Message<String> output = pipeline.apply(inputMessage());

        assertEquals(
                "ORDER=O-501;STATUS=ACCEPTED;AMOUNT=750000",
                output.getPayload());
        assertEquals("corr-501",
                output.getHeaders().get(HeaderNames.CORRELATION_ID));
        assertEquals(
                MimeTypeUtils.TEXT_PLAIN,
                output.getHeaders().get(MessageHeaders.CONTENT_TYPE));
    }

    @Test
    void missingOptionalCorrelationIdStaysAbsent() {
        Message<OrderRequest> input = MessageBuilder
                .withPayload(new OrderRequest(
                        "O-502", 100_000L, "DIRECT"))
                .build();

        Function<Message<OrderRequest>, Message<OrderReceipt>> function =
                catalog.lookup("processOrder");
        Message<OrderReceipt> output = function.apply(input);

        assertNull(output.getHeaders().get(HeaderNames.CORRELATION_ID));
        assertEquals("O-502", output.getPayload().orderId());
    }
}
~~~

### 11.1. Expected Observations

| Test | Payload | Headers Checked |
| --- | --- | --- |
| `enrichesMetadataWithoutChangingPayload` | Preserves `OrderRequest` | `correlationId`, `sourceSystem`, `receivedBy`, `contentType` |
| `processOrderPreservesAllowedMetadataAndAddsProcessor` | `OrderRequest → OrderReceipt` | Keeps correlation/source; adds `processedBy` |
| `compositionCarriesCorrelationAcrossStages` | `OrderRequest → OrderReceipt` | Metadata flows from first stage to next |
| `fullCompositionUpdatesContentTypeWhenPayloadChanges` | `OrderRequest → String` | `correlationId` remains; `contentType` switches to text/plain |
| `missingOptionalCorrelationIdStaysAbsent` | Produces valid receipt | Does not fabricate a fake correlation ID |

Testing through `FunctionCatalog` matters because it verifies that Spring discovered the beans and composed the function chain. Calling `new OrderMessageFunctions().processOrder()` directly skips bean registration and catalog wrappers.

### 11.2. Why Not Assert Every Input Header Appears in Output?

Because filtering is the exact purpose of the allowlist. The test's input message includes `authorization` and a routing header; the output **must not** keep those two headers. Asserting that all headers match identically would encourage uncontrolled metadata propagation.

### 11.3. Why Must Content Type Change at the Final Stage?

`processOrder` returns `OrderReceipt`, which is structured data serialized as JSON. `formatReceipt` returns a plain-text `String`. If the final stage kept `application/json`, adapters could try to interpret the string as a JSON body and fail or break the contract.

Content type is **metadata describing the current payload**, not an immutable property to copy verbatim from the initial message.

## 12. Understanding Key Header Types

### 12.1. correlationId and Message ID

| Attribute | `MessageHeaders.ID` | `correlationId` |
| --- | --- | --- |
| Meaning | Identifies one specific message | Links multiple messages/processing steps |
| Scope | Usually changes when creating a new message | Can persist across multiple stages |
| Source | Managed by Spring Messaging | Application or upstream system |
| Use as a business key? | No | Does not replace order ID |
| Policy | Do not force preserving ID on output | Keep when present and allowed |

A single request can generate several messages: input, validated event, receipt event. Each message has its own ID, while sharing `correlationId` so logs and traces can link them together.

### 12.2. contentType

Spring Messaging uses the `contentType` header (`MessageHeaders.CONTENT_TYPE`) to describe payload format. Common values include:

| Value | Meaning |
| --- | --- |
| `application/json` | JSON payload |
| `text/plain` | Plain text |
| `application/octet-stream` | Raw byte payload without a specific text schema |
| `application/vnd.example.order+json` | JSON with an application-specific media type |

Whenever the payload type changes, re-evaluate the new content type. Never blindly copy the old header if it no longer describes the output payload.

### 12.3. sourceSystem and receivedBy

`sourceSystem` can indicate which partner sent a message. However, if producers set the header themselves, that value is merely a **producer-declared claim** until verified or authenticated.

`receivedBy` and `processedBy` in this lab are set by the server to mark processing components. They are observability metadata, not security proof or transaction confirmation.

### 12.4. Internal and Sensitive Headers

Do not forward arbitrarily:

- `authorization`, access tokens, cookies, or API keys.
- Routing headers that could influence downstream stages to invoke unintended functions.
- Binder/framework internal headers meaningful only to one adapter.
- Debug headers containing internal details.
- Personal data or oversized payloads stuffed into headers.

The allowlist in `HeaderPolicy` mitigates these risks. Nevertheless, real security requires authentication, authorization, and secret handling at the appropriate layers.

## 13. Header Propagation Rules Across Adapters

Catalog tests verify **in-application message construction logic**. When crossing HTTP or a broker, headers must also be mapped by the adapter to and from the transport.

| Path | What Must Be Verified |
| --- | --- |
| Direct Java function call | Message and headers have expected types in memory |
| FunctionCatalog composition | Each stage preserves headers per allowlist |
| HTTP request → function | Which HTTP headers become message headers; content type/body |
| Function → HTTP response | Which headers appear on the HTTP response and which are filtered |
| Spring Cloud Stream input | Whether the binder propagates custom headers and content type properly |
| Spring Cloud Stream output | Which headers are serialized/transported and which are dropped |
| Serverless event | Whether event attributes/headers are mapped properly by the adapter |

**There is no universal rule that every header passes unchanged through every adapter.** Brokers impose data type and header size limits; HTTP has header naming and hop-by-hop rules; serverless platforms have provider-specific event schemas. Write integration tests against the exact adapter and binder you use.

### 13.1. Headers Over Spring Cloud Stream

When deploying a function taking `Message<OrderRequest>` and returning `Message<OrderReceipt>`, bindings can be configured as follows (an extension example; the lab does not yet include a binder):

~~~yaml
spring:
  cloud:
    function:
      definition: "enrichMetadata|processOrder"
    stream:
      bindings:
        "enrichMetadata|processOrder-in-0":
          destination: orders.in
          group: order-processors
          content-type: application/json
        "enrichMetadata|processOrder-out-0":
          destination: orders.receipts
          content-type: application/json
~~~

In real systems, verify the binder's header mapping. Having a Java header on a message does not guarantee the broker can store and restore that exact Java object type. Prefer simple transport-friendly header values such as Strings, numbers, or types supported by the binder.

When custom headers must survive transport, test sending a message to the input binding and reading the output binding to confirm `correlationId` and `sourceSystem` remain intact, while `authorization` and routing headers do not appear unexpectedly.

### 13.2. Headers Over HTTP

With the web adapter, HTTP request headers can be mapped into message headers, though exact mapping and response propagation vary by adapter and version. Never assume every request header is echoed back in the HTTP response.

An HTTP integration test should send:

~~~http
POST /processOrder
Content-Type: application/json
X-Correlation-Id: corr-501
X-Source-System: partner-a
~~~

The adapter or an application conversion layer must map HTTP header names to internal `correlationId`/`sourceSystem` headers. Tests then verify that the output message/response retains the permitted metadata. Because this lab tests Spring `Message` objects directly, it **does not yet** prove HTTP header mapping.

### 13.3. Headers Over Serverless

Events from AWS Lambda, Azure Functions, or Google Cloud Functions may carry metadata in event attributes, request context, or message attributes. The adapter maps these into message headers or input DTOs. Test the exact event type and adapter you choose; do not assume an arbitrary HTTP header exists on every event trigger.

## 14. Adding New Headers Without Breaking Existing Contracts

When you need to add `schemaVersion` or `processingRegion`, do not switch to copying all headers. Expand the allowlist and add tests:

~~~java
MessageBuilder<OrderReceipt> builder =
        HeaderPolicy.withAllowedHeaders(
                input,
                receipt,
                HeaderNames.CORRELATION_ID,
                HeaderNames.SOURCE_SYSTEM,
                "schemaVersion");

builder.setHeader("processingRegion", "ap-southeast-1");
~~~

Before adding a header, decide:

1. Is this header metadata from the **input**, or generated by the server?
2. Does it need to cross every stage?
3. Should it be sent over the broker or HTTP?
4. Does it contain sensitive information or personal identifiers?
5. Can older consumers safely ignore the new header?

For schema versioning, use content types/versioned schemas or an explicit version header with a clear contract. Never rely on arbitrary headers to dynamically change deserialization classes without allowlist and type-metadata controls.

## 15. Handling Missing or Mistyped Headers

In the example, `correlationId` and `sourceSystem` are optional metadata. If missing, the helper skips copying them and the pipeline still processes the payload. If business rules require a mandatory correlation ID, validate it explicitly and reject the message before processing.

Example validator:

~~~java
public static String requireCorrelationId(Message<?> message) {
    Object value = message.getHeaders().get(
            HeaderNames.CORRELATION_ID);

    if (!(value instanceof String correlationId)
            || correlationId.isBlank()) {
        throw new IllegalArgumentException(
                "correlationId header is required");
    }
    return correlationId;
}
~~~

Do not cast directly:

~~~java
// Can throw ClassCastException if the producer sends a different type.
String id = (String) message.getHeaders().get("correlationId");
~~~

Verify header types before using them. For mandatory metadata, errors should be surfaced clearly and adapters should apply appropriate rejection, retry, or quarantine policies.

## 16. Security and Metadata Integrity

Headers accompany a message, which does not make them trustworthy. A producer could send:

~~~text
sourceSystem = "trusted-bank"
tenantId = "tenant-admin"
authorization = "Bearer fake"
~~~

If the application bases authorization decisions on these values, it creates a vulnerability. Follow these principles:

- **Never treat producer-declared `sourceSystem` as authentication proof.** Verify producer identity at ingress.
- **Never trust a `tenantId` header for authorization.** Use the authenticated identity/tenant context.
- **Never forward `authorization`/tokens** unless output has an explicit security reason to do so.
- **Never dump all headers into logs** because they may hold tokens, cookies, or personal data.
- Limit the count, size, and types of accepted headers.
- Propagate only the metadata needed by the next stage.
- Use `correlationId` for observability and tracing, never as an authorization key.

A header allowlist is a **data-propagation** policy. It does not replace authentication, authorization, encryption, or broker-level access controls.

## 17. Running the Tests

In `message-metadata-lab`:

~~~bash
java -version
mvn -version
mvn test
~~~

Test suites expected to pass:

| Group | Result |
| --- | --- |
| `OrderPolicyTest` | Order processing logic works |
| `HeaderPolicyTest` | Allowlist header copying works; `MessageHeaders` is immutable |
| `MessageMetadataCatalogTest` | Metadata propagates properly across functions and composition |

If catalog tests fail, check package scanning, bean names, and `Message<T>` generic types. If adapter tests fail, inspect transport header mapping, content types, and adapter configuration separately.

## 18. Extension Exercises

### Exercise A — Requiring correlationId

Update `enrichMetadata` to reject messages missing `correlationId` or carrying a non-String value.

**Requirements:**

- Write a test for a missing header.
- Write a test for a blank header.
- Write a test for a numeric header.
- Prove that `processOrder` is not invoked when mandatory metadata is invalid.

### Exercise B — Adding schemaVersion

Producers send a `schemaVersion` header. Define valid versions such as `"1"` and `"2"`, and propagate only that header to output.

**Requirements:** test valid versions, unsupported versions, and a missing header. Never use this header to dynamically load classes or execute code.

### Exercise C — Adding Processing Metadata

Add `processedAt` (ISO-8601 UTC) and `processingRegion`. Inject a `Clock` for deterministic time testing instead of asserting on `Instant.now()`.

**Requirements:** only the server may generate these two headers; spoofed values sent by a producer must be overwritten or stripped according to policy.

### Exercise D — Per-Stage Header Allowlists

Create a table for the three stages:

| Stage | Headers Kept | Headers Added | Headers Dropped |
| --- | --- | --- | --- |
| `enrichMetadata` | correlationId, sourceSystem | receivedBy, contentType | authorization |
| `processOrder` | correlationId, sourceSystem, receivedBy | processedBy, contentType | authorization |
| `formatReceipt` | correlationId, receivedBy, processedBy | contentType=text/plain | sourceSystem if unneeded |

**Requirements:** implement the exact table and test each stage. Explain why a header may be dropped at the final stage.

### Exercise E — Testing Spring Cloud Stream Header Mapping

Add the Spring Cloud Stream Test Binder or an appropriate test broker. Send a message containing `correlationId` and `sourceSystem` to the input binding, then read from the output binding.

**Requirements:** inspect which headers are retained, their post-transport data types, content type, and confirm `authorization` is stripped. Current catalog tests do not replace this exercise.

### Exercise F — Translating Metadata from HTTP Headers

Add the web adapter. Map `X-Correlation-Id` to `correlationId` and `X-Source-System` to `sourceSystem` using an appropriate adapter, controller, or filter.

**Requirements:** send HTTP requests and verify output headers/responses; test missing headers, invalid headers, and sensitive headers. Identify clearly what the web adapter handles automatically versus what the application maps explicitly.

## 19. Common Errors and Troubleshooting

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Headers missing from output | Stage builds a new message without copying headers | Use the allowlist helper and test each stage |
| Old header kept with wrong content type | Copied all headers from previous message | Reset `MessageHeaders.CONTENT_TYPE` for the new payload |
| `MessageHeaders.put` throws exception | Headers are immutable | Create a new message with `MessageBuilder` |
| Sensitive header appears in output | Unbounded `copyHeaders` used | Switch to allowlist and strip tokens/cookies |
| `correlationId` lost in second stage | That stage omitted it from its allowlist | Inspect each stage's header policy |
| `correlationId` changes unexpectedly | Using message ID instead of correlation ID, or adapter generates new metadata | Distinguish message ID from flow correlation ID |
| Mistyped header causes `ClassCastException` | Casting before checking type | Use `instanceof` and validate |
| Catalog test passes but broker drops header | Binder/transport does not map the header as expected | Write an integration test through the binder |
| HTTP request header never reaches function | Adapter does not map custom header or names differ | Map explicitly and test over real HTTP |
| JSON payload has `text/plain` content type | Header carried over from previous stage | Update content type in the stage that changes payload type |
| Using `sourceSystem` for authorization | Trusting producer-supplied header | Use an authenticated identity |
| Flaky tests | Shared mutable state or parallel test execution | Isolate test data; avoid mutable singletons |

### 19.1. Debugging Sequence

1. Check the payload before processing.
2. Print/inspect **only safe headers** at input.
3. Verify the first stage's header allowlist.
4. Check the first stage's output, especially correlation and content type.
5. Repeat for every stage in the composition.
6. Look up and invoke the pipeline through `FunctionCatalog`.
7. If failures happen only over HTTP/broker, inspect the adapter/binder header mapping.
8. Confirm the output contains no tokens or unintended routing headers.

## 20. Completion Criteria

| Criterion | Evidence |
| --- | --- |
| Distinguish payload and headers | `OrderRequest` holds order data; `MessageHeaders` holds metadata |
| Immutable messages | Test attempting to mutate headers directly fails |
| Allowlist enforced | `HeaderPolicy` copies only permitted names |
| Metadata enriched | Server adds `receivedBy` and `processedBy` |
| Correlation preserved | `correlationId` flows through composition |
| Content type updated | Switches from JSON to `text/plain` in the final stage |
| Sensitive headers stripped | `authorization` does not appear in output |
| Catalog composition | `enrichMetadata|processOrder|formatReceipt` runs properly |
| Adapter boundary understood | Distinguishes catalog tests from HTTP/binder integration tests |
| Metadata security | Does not trust headers for authentication or authorization |

**Summary:** The payload describes business data; headers describe message context. When a function needs metadata, accept `Message<T>` and build output messages with `MessageBuilder`. Explicitly specify which headers are kept, which are added, and which must be stripped. Each stage in a composition must verify its own metadata contract; when crossing HTTP, brokers, or serverless platforms, test separately how the adapter maps headers.

## 21. Self-Check Questions

**Question 1.** How do `OrderRequest` and `MessageHeaders` differ in responsibility?

**Answer:** `OrderRequest` holds the business payload such as order ID and amount. `MessageHeaders` holds metadata such as correlation ID, content type, and source system.

**Question 2.** Why should a function that needs to read headers declare `Function<Message<OrderRequest>, ...>`?

**Answer:** So it receives both the payload and metadata. A signature accepting only `OrderRequest` does not expose message headers to the function.

**Question 3.** Should `MessageBuilder.copyHeaders(input.getHeaders())` be used at every stage?

**Answer:** Not by default. It can carry forward tokens, routing headers, or stale content types. Select headers using an allowlist instead.

**Question 4.** Why should `correlationId` be preserved while `MessageHeaders.ID` does not need to stay the same?

**Answer:** Correlation ID links multiple messages within the same flow. Message ID identifies a specific message instance and may be regenerated when building an output message.

**Question 5.** When the payload changes from `OrderReceipt` to `String`, which header should be updated?

**Answer:** `contentType` should be updated appropriately, such as to `text/plain`; do not keep `application/json` if the output is no longer JSON.

**Question 6.** Why should `sourceSystem` or `tenantId` sent by a producer never be used to grant permissions?

**Answer:** Producers can declare or spoof arbitrary headers. Authorization must rely on an identity authenticated at the security layer.

**Question 7.** Catalog tests prove `correlationId` passes through function composition. Does that prove Kafka preserves that header?

**Answer:** No. You must test with a real binder/broker or Test Binder to verify header mapping and transport.

**Question 8.** If the first stage copies a header properly, but the second stage constructs a new message without copying it, what happens?

**Answer:** That header is dropped from the second stage's output. Metadata propagation rules must be implemented and tested at every stage.

## References

- [Spring Cloud Function — Programming Model, FunctionCatalog, and Message](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html)
- [Spring Framework — Message and MessageHeaders](https://docs.spring.io/spring-framework/reference/integration/spring-integration.html)
- [Spring Framework — MessageBuilder API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/messaging/support/MessageBuilder.html)
- [Spring Framework — MessageHeaders API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/messaging/MessageHeaders.html)
- [Spring Cloud Stream — Message Conversion](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/mechanics.html)
- [Spring Cloud Stream — User-defined Message Converters](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-user-defined-message-converters.html)
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [Java 17 — Function interfaces](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/package-summary.html)
