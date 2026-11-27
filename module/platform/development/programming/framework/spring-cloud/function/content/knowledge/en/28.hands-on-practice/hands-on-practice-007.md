# Exposing the Same Function over HTTP and Spring Cloud Stream

## 1. Practice Problem

**Spring Cloud Function** (**SPRING_CLOUD_FUNCTION**) lets you develop reusable business logic using **Supplier**, **Function**, and **Consumer** beans, independent of the invocation protocol. **FunctionCatalog** manages these functions and supports composition and message conversion, while adapters expose the same function over HTTP, event-driven systems, or serverless environments.

In this lesson, we build an order-processing capability:

- Receive an **OrderRequest**.
- Validate order ID, customer ID, quantity, and unit price.
- Calculate the total amount.
- Return an **OrderReceipt**.

We want two client groups to invoke **the same business bean**:

1. A web application or partner sends HTTP **POST /processOrder**.
2. Another system publishes a message to RabbitMQ destination **orders.in**; Spring Cloud Stream forwards the payload to the same function and sends the result to **orders.receipts**.

~~~text
                   HTTP POST /processOrder
                           |
                           v
                    Spring Cloud Function
                      Web adapter
                           |
                           v
                  +-------------------+
                  | FunctionCatalog   |
                  |   processOrder    |
                  +---------+---------+
                            |
                            v
              Function<OrderRequest, OrderReceipt>
                            ^
                            |
                  +---------+---------+
                  | FunctionCatalog   |
                  |   processOrder    |
                  +---------+---------+
                            ^
                            |
                      Stream adapter
                            ^
                            |
                     RabbitMQ binder
                            ^
                            |
                    orders.in destination

Stream output:
processOrder-out-0 -> orders.receipts
~~~

**Core point to prove:** both the HTTP adapter and the Stream binder invoke the same functional bean **processOrder**. Each has its own way of receiving data, converting payloads, handling errors, and acknowledging delivery, while the business logic remains shared.

After this lesson, you will be able to:

- Create a strongly typed **Function<OrderRequest, OrderReceipt>**.
- Export the function via the Spring Cloud Function Web adapter.
- Bind the same function to input/output destinations via Spring Cloud Stream.
- Use the Test Binder to test message flows without an external broker.
- Send HTTP requests and inspect JSON responses.
- Understand **processOrder-in-0**, **processOrder-out-0**, **content-type**, and **function.definition**.
- Distinguish HTTP responses from broker acknowledgments, retries, and DLQs.

## 2. Architecture: One Function, Two Adapters

In Spring Cloud Function, the business bean does not need to know whether it was invoked from HTTP or RabbitMQ. For example:

~~~java
Function<OrderRequest, OrderReceipt> processOrder
~~~

The Web adapter receives an HTTP request, converts the body to **OrderRequest**, looks up the function, and returns the result in the HTTP response. The Stream binder receives a message from a destination, converts the payload to **OrderRequest**, invokes the function, and turns **OrderReceipt** into an output message.

| Component | HTTP | Spring Cloud Stream |
| --- | --- | --- |
| Entry point | POST /processOrder | processOrder-in-0 |
| Transport | HTTP request | RabbitMQ message |
| Input conversion | JSON body → OrderRequest | Message payload + content type → OrderRequest |
| Logic | processOrder | processOrder |
| Output conversion | OrderReceipt → JSON response | OrderReceipt → output message |
| Exit point | HTTP response | processOrder-out-0 |
| Errors | HTTP error mapping | Binder error handling/retry/DLQ |

Two adapters do not make the semantics of the underlying protocols identical. An HTTP request produces a direct synchronous response; a message broker typically involves acknowledgments, delivery retries, and dead-letter policies.

## 3. Environment Setup

The lab uses:

- **JDK 17**.
- **Maven 3.9+**.
- **Spring Boot 3.5.0**.
- **Spring Cloud 2025.0.0**, the release train compatible with Spring Boot 3.5.x.
- Docker (only needed if you want to run a real RabbitMQ broker in the extension section).

Spring Cloud versions are managed through the BOM. For new projects, pick supported patches within the same compatible release train; do not specify individual versions on Spring Cloud artifacts.

Create the directory **dual-adapter-order-lab**:

~~~text
dual-adapter-order-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/dualadapter/
    │   │   ├── OrderLabApplication.java
    │   │   ├── OrderRequest.java
    │   │   ├── OrderReceipt.java
    │   │   ├── OrderProcessor.java
    │   │   └── OrderFunctions.java
    │   └── resources/
    │       └── application.yml
    └── test/
        └── java/com/example/dualadapter/
            ├── OrderProcessorTest.java
            ├── OrderFunctionCatalogTest.java
            ├── OrderHttpTest.java
            └── OrderStreamTest.java
~~~

All Java classes use package **com.example.dualadapter**.

## 4. Declaring Maven Dependencies

Create **pom.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>dual-adapter-order-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>dual-adapter-order-lab</name>

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
        <!-- HTTP runtime -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-function-web</artifactId>
        </dependency>

        <!-- Event-driven runtime: RabbitMQ binder -->
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-starter-stream-rabbit</artifactId>
        </dependency>

        <!-- Tests -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
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

Dependency roles:

| Artifact | Role |
| --- | --- |
| spring-boot-starter-web | Spring MVC and embedded server for HTTP |
| spring-cloud-function-web | Exports functional beans over HTTP |
| spring-cloud-starter-stream-rabbit | Spring Cloud Stream RabbitMQ binder |
| spring-boot-starter-test | JUnit 5, Spring Test, and MockMvc |
| spring-cloud-stream-test-binder | Tests input/output bindings in the test environment |

In this project, the Rabbit binder is the production runtime adapter; Test Binder is used in test scope. If the project needs Kafka instead, replace the Rabbit starter with the matching Kafka binder while letting the BOM manage versions.

## 5. Creating the Payload and Business Result

### 5.1. OrderRequest.java

~~~java
package com.example.dualadapter;

public record OrderRequest(
        String orderId,
        String customerId,
        int quantity,
        long unitPriceVnd) {
}
~~~

### 5.2. OrderReceipt.java

~~~java
package com.example.dualadapter;

public record OrderReceipt(
        String orderId,
        String customerId,
        String status,
        long totalVnd) {
}
~~~

Explicitly typed payloads allow both the HTTP adapter and the Stream binder to convert into the same Java contract. Avoid **Map<String,Object>** when the order schema is well defined; strong types let the compiler and tests catch errors early.

## 6. Writing Adapter-Independent Business Logic

Create **OrderProcessor.java**:

~~~java
package com.example.dualadapter;

import java.util.Locale;

public final class OrderProcessor {

    private OrderProcessor() {
    }

    public static OrderReceipt process(OrderRequest request) {
        if (request == null) {
            throw new IllegalArgumentException("request is required");
        }
        if (request.orderId() == null || request.orderId().isBlank()) {
            throw new IllegalArgumentException("orderId is required");
        }
        if (request.customerId() == null
                || request.customerId().isBlank()) {
            throw new IllegalArgumentException("customerId is required");
        }
        if (request.quantity() <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        if (request.unitPriceVnd() <= 0) {
            throw new IllegalArgumentException(
                    "unitPriceVnd must be positive");
        }

        long total = Math.multiplyExact(
                request.unitPriceVnd(),
                request.quantity());

        return new OrderReceipt(
                request.orderId().trim().toUpperCase(Locale.ROOT),
                request.customerId().trim().toUpperCase(Locale.ROOT),
                "ACCEPTED",
                total);
    }
}
~~~

Logic:

- Rejects null requests.
- Requires `orderId` and `customerId`.
- Quantity and unit price must be positive.
- Uses `Math.multiplyExact` to detect overflow.
- Normalizes identifiers using `Locale.ROOT`.
- Returns `OrderReceipt` with status `ACCEPTED`.

`ACCEPTED` in this lab means the order passed validation and was priced. It does **not** mean a payment gateway charged a card, a database committed, or inventory was reserved.

## 7. Registering a Single Functional Bean

Create **OrderFunctions.java**:

~~~java
package com.example.dualadapter;

import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class OrderFunctions {

    @Bean
    public Function<OrderRequest, OrderReceipt> processOrder() {
        return OrderProcessor::process;
    }
}
~~~

This is the sole business bean shared by both adapters:

~~~text
Bean name: processOrder
Input:     OrderRequest
Output:    OrderReceipt
Type:      Function<OrderRequest, OrderReceipt>
~~~

Do not write one controller that calculates pricing and a separate Stream consumer that recalculates pricing. Controllers and adapters handle only the transport protocol and delegate to the function.

### 7.1. Application Startup

Create **OrderLabApplication.java**:

~~~java
package com.example.dualadapter;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrderLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderLabApplication.class, args);
    }
}
~~~

## 8. Configuring the Function and Stream Bindings

Create **src/main/resources/application.yml**:

~~~yaml
spring:
  application:
    name: dual-adapter-order-lab
  cloud:
    function:
      definition: processOrder
      single-function-fallback-enabled: false
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.in
          group: order-processors
          content-type: application/json
        processOrder-out-0:
          destination: orders.receipts
          content-type: application/json

server:
  port: 8080
~~~

### 8.1. Reading the Configuration

| Property | Meaning |
| --- | --- |
| spring.cloud.function.definition | Selects `processOrder` for Spring Cloud Stream to bind |
| processOrder-in-0 | Input binding of the function |
| destination: orders.in | Destination receiving incoming orders |
| group: order-processors | Consumer group of the Stream binding |
| content-type: application/json | Input payload is converted from JSON |
| processOrder-out-0 | Output binding of the function |
| destination: orders.receipts | Destination emitting receipts |

For an imperative `Function<I,O>`, the function has one input and one output, so the binding names are `processOrder-in-0` and `processOrder-out-0`. Indexing starts at 0.

### 8.2. Why Is definition Set to processOrder?

`spring.cloud.function.definition` tells Spring Cloud Stream which function to bind. It does not create a new bean. The `processOrder` bean is still declared only once in `OrderFunctions`.

If you later add `normalizeOrder` or `auditOrder`, only functions listed in `definition` will be bound by the Stream adapter under this configuration. The HTTP adapter follows its own export rules; test specific endpoints directly rather than inferring behavior from binding names.

### 8.3. Do Not Put URLs in Stream Bindings

`orders.in` and `orders.receipts` are binder destinations (exchanges/queues or topics depending on the broker), not HTTP URLs. HTTP endpoints are mapped by the web adapter from function names.

## 9. Pure Java Business Logic Tests

Create **OrderProcessorTest.java**:

~~~java
package com.example.dualadapter;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class OrderProcessorTest {

    @Test
    void calculatesOrderTotal() {
        OrderReceipt result = OrderProcessor.process(
                new OrderRequest(" o-501 ", " c-10 ", 3, 250_000L));

        assertEquals(
                new OrderReceipt(
                        "O-501", "C-10", "ACCEPTED", 750_000L),
                result);
    }

    @Test
    void rejectsInvalidQuantity() {
        assertThrows(IllegalArgumentException.class,
                () -> OrderProcessor.process(
                        new OrderRequest("O-502", "C-10", 0, 100L)));
    }

    @Test
    void detectsLongOverflow() {
        assertThrows(ArithmeticException.class,
                () -> OrderProcessor.process(
                        new OrderRequest(
                                "O-503", "C-10", 2, Long.MAX_VALUE)));
    }
}
~~~

This unit test confirms the business logic has no dependency on HTTP or a broker. If this test fails, fix the logic before investigating adapters.

## 10. Testing FunctionCatalog

Create **OrderFunctionCatalogTest.java**:

~~~java
package com.example.dualadapter;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.util.function.Function;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.cloud.stream.binder.test.TestChannelBinderConfiguration;
import org.springframework.context.annotation.Import;

@SpringBootTest(
        classes = OrderLabApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
@Import(TestChannelBinderConfiguration.class)
class OrderFunctionCatalogTest {

    @Autowired
    private FunctionCatalog catalog;

    @Test
    void looksUpAndInvokesTheSharedFunction() {
        Function<OrderRequest, OrderReceipt> function =
                catalog.lookup("processOrder");

        assertNotNull(function);

        OrderReceipt result = function.apply(
                new OrderRequest("O-501", "C-10", 3, 250_000L));

        assertEquals(
                new OrderReceipt(
                        "O-501", "C-10", "ACCEPTED", 750_000L),
                result);
    }
}
~~~

The catalog test verifies that Spring registered the bean and `FunctionCatalog` can look it up by name. It does not yet verify the HTTP route or Stream bindings.

## 11. Testing the HTTP Adapter with MockMvc

Create **OrderHttpTest.java**:

~~~java
package com.example.dualadapter;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.stream.binder.test.TestChannelBinderConfiguration;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest(classes = OrderLabApplication.class)
@AutoConfigureMockMvc
@Import(TestChannelBinderConfiguration.class)
class OrderHttpTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void exposesTheFunctionAsAnHttpEndpoint() throws Exception {
        mvc.perform(post("/processOrder")
                        .contentType(MediaType.APPLICATION_JSON)
                        .accept(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "orderId": "o-501",
                                  "customerId": "c-10",
                                  "quantity": 3,
                                  "unitPriceVnd": 250000
                                }
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.orderId").value("O-501"))
                .andExpect(jsonPath("$.customerId").value("C-10"))
                .andExpect(jsonPath("$.status").value("ACCEPTED"))
                .andExpect(jsonPath("$.totalVnd").value(750000));
    }
}
~~~

### 11.1. Sending HTTP Requests with curl

After starting the application:

~~~bash
curl -i -X POST "http://localhost:8080/processOrder" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  --data-binary '{
    "orderId": "o-501",
    "customerId": "c-10",
    "quantity": 3,
    "unitPriceVnd": 250000
  }'
~~~

Expected response body:

~~~json
{
  "orderId": "O-501",
  "customerId": "C-10",
  "status": "ACCEPTED",
  "totalVnd": 750000
}
~~~

The web adapter receives the request, uses the content type to deserialize JSON into `OrderRequest`, invokes the function, and serializes `OrderReceipt` into the JSON response.

**HTTP status:** a successful function invocation normally returns `200 OK`. Validation errors do not automatically yield a structured error schema; if this is a public API, add error mapping and test status/body against the chosen contract.

## 12. Testing the Stream Adapter with Test Binder

Spring Cloud Stream Test Binder creates in-memory input/output destinations to test message flows without running a real RabbitMQ broker.

Create **OrderStreamTest.java**:

~~~java
package com.example.dualadapter;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.stream.binder.test.InputDestination;
import org.springframework.cloud.stream.binder.test.OutputDestination;
import org.springframework.cloud.stream.binder.test.TestChannelBinderConfiguration;
import org.springframework.context.annotation.Import;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.util.MimeTypeUtils;

@SpringBootTest(
        classes = OrderLabApplication.class,
        properties = {
                "spring.cloud.function.definition=processOrder"
        })
@Import(TestChannelBinderConfiguration.class)
class OrderStreamTest {

    @Autowired
    private InputDestination input;

    @Autowired
    private OutputDestination output;

    @Autowired
    private ObjectMapper objectMapper;

    @Test
    void receivesOrderMessageAndPublishesReceipt() throws Exception {
        byte[] payload = objectMapper.writeValueAsBytes(
                new OrderRequest("O-601", "C-20", 2, 125_000L));

        Message<byte[]> message = MessageBuilder
                .withPayload(payload)
                .setHeader(
                        MessageHeaders.CONTENT_TYPE,
                        MimeTypeUtils.APPLICATION_JSON)
                .build();

        input.send(message, "processOrder-in-0");

        Message<byte[]> result =
                output.receive(1_000, "processOrder-out-0");
        assertNotNull(result);

        OrderReceipt receipt = objectMapper.readValue(
                result.getPayload(), OrderReceipt.class);

        assertEquals(
                new OrderReceipt(
                        "O-601", "C-20", "ACCEPTED", 250_000L),
                receipt);
    }
}
~~~

### 12.1. What Does the Test Binder Prove?

The test sends a message to `processOrder-in-0`, then reads the result from `processOrder-out-0`. It verifies:

- The Stream adapter created bindings based on the function name.
- The input message was converted into `OrderRequest`.
- The shared `processOrder` bean executed.
- The `OrderReceipt` result was published to the output binding.

This is an in-memory binder integration test. It does **not** prove that RabbitMQ created exchanges/queues, that the broker durably stores messages, or that retries/DLQs are functioning.

### 12.2. Why Use byte[] and Content Type?

The test simulates a JSON message on the wire. `Content-Type` tells the message converter that the payload is JSON so it converts it into the function's target type. Sending a raw Java object directly could bypass parts of the serialization path used by real producers.

In real applications, also verify:

- The `contentType` header sent by the producer.
- The binding's `content-type` configuration.
- The payload type after conversion.
- JSON schema/versioning.

## 13. Running the Application with Real RabbitMQ

Once unit, catalog, HTTP, and Test Binder tests pass, you can run RabbitMQ to observe real transport.

### 13.1. Starting RabbitMQ

If Docker is installed:

~~~bash
docker run -d --name scf-rabbit \
  -p 5672:5672 \
  -p 15672:15672 \
  rabbitmq:3-management
~~~

The Management UI is accessible by default at `http://localhost:15672` using the image's default `guest/guest` credentials from localhost. Never use these default credentials in production.

The Rabbit binder connects to localhost using Spring Cloud Stream Rabbit binder defaults. If the broker runs on another host or uses custom credentials, configure the binder accordingly in `application.yml`.

### 13.2. Running the Application

~~~bash
mvn spring-boot:run
~~~

The application starts both the HTTP server and the Stream bindings:

~~~text
HTTP:
POST /processOrder

RabbitMQ:
orders.in -> processOrder-in-0
processOrder-out-0 -> orders.receipts
~~~

Both entry points can invoke the same `processOrder` bean. Never submit the same order over both HTTP and RabbitMQ if the business logic has real side effects without an idempotency key; in this lab, the function only computes a result and creates no external transactions.

### 13.3. Sending a Message via RabbitMQ

You can use the RabbitMQ Management UI to publish a message to the exchange/queue created by the binder, or use a separate Spring Cloud Stream producer. Example payload:

~~~json
{
  "orderId": "O-701",
  "customerId": "C-31",
  "quantity": 4,
  "unitPriceVnd": 50000
}
~~~

Set the content type to `application/json`. Expected result at destination `orders.receipts`:

~~~json
{
  "orderId": "O-701",
  "customerId": "C-31",
  "status": "ACCEPTED",
  "totalVnd": 200000
}
~~~

In a real system, use a producer with explicit schema/versioning and correlation IDs; avoid relying on manual message entry via the management UI.

## 14. Adapter Configuration and Deployment Profiles

HTTP and Stream can run simultaneously as configured in this lab. In real systems, you sometimes deploy two separate instances:

- An HTTP instance containing only the web adapter.
- An event-processor instance containing the Stream binder.

The same artifact and the same function bean can run across two different profiles or deployments. This allows independent scaling for HTTP traffic versus event load and reduces operational coupling.

### 14.1. Example HTTP-Only Profile

For an HTTP-only deployment, build an application variant without the Rabbit binder dependency (keeping the web adapter and the module holding the functions). You do not need to recreate or copy `OrderProcessor`/`OrderFunctions`. Separating dependencies by artifact or profile keeps the HTTP deployment from attempting to open broker connections.

### 14.2. Example Stream-Only Profile

**application-stream.yml**:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.in
          group: order-processors
          content-type: application/json
        processOrder-out-0:
          destination: orders.receipts
          content-type: application/json
~~~

If you do not want to expose HTTP, omit the web dependency from the standalone Stream artifact or enforce appropriate gateway/network policies. Simply setting `server.port=-1` is no substitute for properly designing public surface area and dependencies.

When sharing a single artifact with both adapters active, verify via integration tests that function-named HTTP endpoints still work when Stream bindings are enabled. Under web mapping rules, catalog functions map to URLs by name; the `definition` property can also affect root-path mapping or filter exported functions.

## 15. Error Handling Differences Between HTTP and Message Brokers

The function can throw `IllegalArgumentException` on invalid requests. However, the two adapters must express errors according to their respective contracts.

| Concern | HTTP | Spring Cloud Stream |
| --- | --- | --- |
| Malformed input schema | Usually a conversion error before calling the function | Message conversion error in the consumer |
| Business validation | Must map to a 4xx status and error body | May trigger error handling/retries depending on configuration |
| Transient failure | Client may retry the request | Binder applies retry policy |
| Unrecoverable error | Returns an error response | May route to DLQ/quarantine |
| Success | HTTP response | Output message and binder acknowledgment |

Never assume:

- HTTP 200 equals a message broker ACK.
- HTTP 500 automatically sends to a DLQ.
- Throwing an exception from a function guarantees the broker redelivers.
- Publishing an output message guarantees a database transaction committed.

Configure and test each adapter independently.

### 15.1. Idempotency When the Same Function Is Called over Two Protocols

A client might send an HTTP request that times out, and another producer might subsequently publish the same order over the broker. If the function performs side effects like database writes or payment API calls, the same business operation could run twice.

In production:

1. Use a unique `orderId` or `idempotencyKey` with clear semantics.
2. Check and record processing state atomically at the persistence layer.
3. Do not rely on correlation ID as an idempotency key when one flow performs multiple distinct operations.
4. Use an outbox pattern when events must be published after a transaction commits.
5. Test duplicate delivery across both HTTP and Stream.

This lab only computes pricing and returns a receipt without database persistence, so idempotency storage is not implemented here.

## 16. Observability and Operations

Both adapters need correlatable logs and metrics:

- `orderId`: business identifier.
- `correlationId`: links processing steps within a flow.
- `source`: declared data source in the payload (must be verified if used for policy).
- Adapter: HTTP or Stream.
- Processing latency and outcome.

Avoid logging tokens, sensitive payment details, or full payloads unnecessarily. Use Micrometer/observation and tracing appropriate for your deployment stack; do not treat raw log messages as the sole audit system.

When scaling:

- HTTP scales with request concurrency and latency.
- Stream consumers scale with partition/queue concurrency and downstream capacity.
- Sharing one function does not mean both adapters share the same resource limits, timeouts, or retry policies.

## 17. Extension Exercises

### Exercise A — Adding a Currency Field

Extend `OrderRequest` with `currency`. Accept only `VND` in this lab.

**Requirements:**

- Update unit tests.
- Send HTTP JSON with `currency`.
- Send a Test Binder message with `currency`.
- Both adapters invoke the same logic and produce identical results.

### Exercise B — Adding a Correlation ID

Producers send `correlationId` via an HTTP header and a message header. Design how metadata maps into the function or logging context.

**Requirements:** verify the ID is recorded in both adapters; never leak authentication headers into outputs.

### Exercise C — Adding an Audit Consumer

Create `Consumer<OrderReceipt> auditOrder` to record receipts after processing. Determine how composing `processOrder|auditOrder` affects output:

- The pipeline becomes a consumer and no longer returns `OrderReceipt` like the original function.
- If a receipt output is still needed, perform auditing in the adapter or create a function that returns the receipt after an intentional side effect.

### Exercise D — Switching from RabbitMQ to Kafka

Replace the Rabbit binder with the BOM-managed Kafka binder. Keep `OrderProcessor` and `processOrder` unchanged.

**Requirements:** configure the broker, destinations, consumer group, serialization, retry/DLQ, and test with real messages.

### Exercise E — Running Two Independent Deployments

Create two profiles/containers:

- HTTP deployment receiving requests from an API gateway.
- Stream deployment consuming events from RabbitMQ.

**Requirements:** share the same function code, scale independently, expose only required ports, and explain how to manage schema versions during rolling deployments.

### Exercise F — Testing Errors in Both Adapters

Send a negative quantity or `unitPriceVnd` equal to `0`:

- HTTP: verify error status and body.
- Stream: verify retries, DLQ, and acknowledgments.

**Requirements:** write two separate integration tests; never infer one adapter's behavior from the other's results.

## 18. Common Errors and Troubleshooting

| Symptom | Possible Cause | What to Check |
| --- | --- | --- |
| `POST /processOrder` returns 404 | Web adapter missing or wrong endpoint name | Check `spring-cloud-function-web`, mappings, and logs |
| HTTP receives JSON but function is not called | Incompatible content type or schema | Check `Content-Type` and record fields |
| Stream fails to create input binding | Wrong `spring.cloud.function.definition` | Verify the name `processOrder` |
| Message enters but no output is emitted | Conversion/function failure or wrong output binding | Check logs, `processOrder-out-0`, and destination |
| `FunctionCatalog.lookup` returns null | Bean not scanned or wrong name | Check `@Bean` and package structure |
| Test Binder cannot find destination | Wrong binding name | Use `processOrder-in-0`/`processOrder-out-0` |
| Test Binder fails to convert JSON | Missing content type or incompatible payload | Set `application/json`; inspect `byte[]`/DTO |
| Rabbit binder fails to connect | Broker not running or wrong credentials | Check port 5672 and binder properties |
| HTTP passes but Stream fails | Binder/serialization/retry differs from web adapter | Write dedicated Stream integration tests |
| Message processed twice | Delivery retry or duplicate producer publish | Implement idempotency |
| Same function yields different results | Two adapters supply different payloads/schemas | Compare JSON, content types, and conversion |
| Unexpected error status | HTTP error mapping not configured | Define API error contract |
| Broker does not route to DLQ | Binder DLQ/retry policy not enabled | Check binder-specific configuration |
| Unintended function exposed | Adapter exports more beans than expected | Check web routing and gateway/network policy |

### 18.1. Debugging Sequence

1. Run `java -version` and `mvn -version`.
2. Run `mvn test` to verify pure Java business logic.
3. Test `FunctionCatalog.lookup("processOrder")`.
4. Test HTTP with MockMvc.
5. Test Stream with Test Binder.
6. Only then run real RabbitMQ.
7. Verify output destinations, error policies, and duplicate delivery separately.

## 19. Completion Criteria

| Criterion | Evidence |
| --- | --- |
| Single business bean | `Function<OrderRequest,OrderReceipt> processOrder` declared once |
| HTTP adapter | `POST /processOrder` returns JSON receipt |
| Stream adapter | `processOrder-in-0` consumes JSON and `processOrder-out-0` emits receipt |
| Catalog | `FunctionCatalog.lookup("processOrder")` succeeds |
| HTTP test | MockMvc verifies status and response fields |
| Stream test | Test Binder verifies input/output messages |
| Shared logic | HTTP and Stream produce identical business results |
| Content type understood | JSON converts into the DTO in both adapters |
| Error semantics understood | HTTP responses are not confused with broker ACK/retry/DLQ |
| Operations | Understands deployment profiles, idempotency, and observability |

**Summary:** A single functional bean can serve multiple adapters. The Spring Cloud Function Web adapter turns the function into an HTTP endpoint; a Spring Cloud Stream binder connects the same function to event destinations. Payloads and business logic are reused, while content negotiation, bindings, error handling, retries, acknowledgments, and security must still be configured and tested per protocol.

## 20. Self-Check Questions

**Question 1.** Which bean is shared by both adapters in this lesson?

**Answer:** `processOrder`, of type `Function<OrderRequest, OrderReceipt>`.

**Question 2.** What is the function's HTTP endpoint path?

**Answer:** `POST /processOrder` under the web adapter.

**Question 3.** What are the default input and output binding names?

**Answer:** `processOrder-in-0` and `processOrder-out-0`.

**Question 4.** Does `spring.cloud.function.definition` create an additional function bean?

**Answer:** No. It selects the function definition for adapters; the business bean is still declared only once.

**Question 5.** Does Test Binder require a running RabbitMQ instance?

**Answer:** No. Test Binder creates in-memory bindings; only the real Rabbit binder requires a running broker.

**Question 6.** Does HTTP returning 200 mean RabbitMQ has ACKed a message?

**Answer:** No. The two adapters have distinct success and delivery acknowledgment semantics.

**Question 7.** Why must `content-type: application/json` be configured for the Stream input?

**Answer:** So the message converter knows the payload is JSON and converts it into `OrderRequest`.

**Question 8.** If the function has side effects, what issue can arise when the same request arrives via both HTTP and Stream?

**Answer:** Duplicate processing. You need idempotency and appropriate transaction/outbox design.

**Question 9.** Can you run only `FunctionCatalog` tests and conclude that both HTTP and RabbitMQ work?

**Answer:** No. You must separately test the web adapter, Stream binder, and real broker within your deployment scope.

## References

- [Spring Cloud Function — Programming Model and FunctionCatalog](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html)
- [Spring Cloud Function — Standalone Web Applications](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/standalone-web-applications.html)
- [Spring Cloud Stream — Functional Binding Names](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/functional-binding-names.html)
- [Spring Cloud Stream — Rabbit Binder](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview.html)
- [Spring Cloud Stream — Testing](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/spring_integration_test_binder.html)
- [Spring Cloud Function — HTTP function mapping and filtering rules](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/standalone-web-applications.html)
- [Spring Cloud — Release train compatibility](https://spring.io/projects/spring-cloud/)
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [Java 17 — Function API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/Function.html)
