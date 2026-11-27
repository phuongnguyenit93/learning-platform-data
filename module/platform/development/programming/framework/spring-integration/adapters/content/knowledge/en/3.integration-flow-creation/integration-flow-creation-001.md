# IntegrationFlow with Java DSL

## 1. Objectives and Context

In Spring Integration, an `IntegrationFlow` describes a message processing pipeline: where messages enter, which components they pass through, which target system or component they reach, and how results are returned. The **Java DSL** lets you define that pipeline using typed Java API calls inside Spring configuration, managed as beans.

This lesson belongs to the **Integration Flow Creation** chapter of the **SPRING_INTEGRATION_ADAPTERS** module. The broader goal of the module is to connect external systems using inbound/outbound adapters, gateways, pollers, and `MessageChannel`; practice exchanging data via files, SFTP, HTTP, JMS, AMQP, Kafka, and databases; and control message contracts, errors, and connection lifecycles.

After this lesson, learners will be able to:

- Identify the responsibilities of `IntegrationFlow`, `Message<?>`, `MessageChannel`, and endpoints.
- Create flows using `IntegrationFlow.from(...)`, `filter`, `transform`, `route`, `handle`, `channel`, and `get()`.
- Send requests from Java methods into a flow through a messaging gateway and return results using a request–reply mechanism.
- Connect a polling-based inbound adapter to downstream processing.
- Choose channels, handle errors, preserve headers, and test key branches of a flow.

**Scope:** focuses on how to *create and organize* flows using the Java DSL. Specific adapters such as SFTP, JMS, AMQP, or Kafka require their own dependencies, connection configuration, and business contracts; the Java DSL does not provide those automatically.

## 2. Mental Model: Messages Flowing Through Endpoints

A Spring Integration message consists of a **payload** (business data) and **headers** (metadata such as `id`, `timestamp`, `replyChannel`, `errorChannel`, correlation IDs, or application-added headers). Components in a flow communicate via messages instead of directly calling each service in a tightly coupled dependency chain.

~~~mermaid
flowchart LR
    IN["Message source<br/>Gateway / inbound adapter"]
    CH1["MessageChannel"]
    FILTER["Filter / Transform / Router"]
    CH2["MessageChannel"]
    OUT["Service activator<br/>or outbound adapter"]
    EXT["Target system"]
    IN --> CH1 --> FILTER --> CH2 --> OUT --> EXT
~~~

| Component | Role | Example |
| --- | --- | --- |
| `Message<?>` | Wraps payload and headers to pass through the flow. | `Order` payload, `traceId` header. |
| `MessageChannel` | Connects producers and consumers and determines how messages are delivered. | `DirectChannel`, `QueueChannel`. |
| Inbound adapter | Reads/receives events from an external system and creates messages. | Polling file watcher, Kafka listener. |
| Transformer | Changes the payload representation, typically preserving necessary headers. | JSON to domain object. |
| Filter | Allows only valid messages to proceed; can drop or reroute rejected messages. | Drop records missing a transaction code. |
| Router | Selects a target channel based on payload data or headers. | Route VND/USD to two processing flows. |
| Service activator / handler | Invokes processing logic; can produce a reply or end a one-way flow. | Save an order, call an API. |
| Outbound adapter / gateway | Sends data to a destination; a gateway typically expects a reply, while an adapter typically sends one-way. | Send to JMS or call an HTTP API. |
| Poller | Actively checks a source or consumes a pollable channel on a schedule. | Scan a directory every 5 seconds. |

A **one-way flow** typically ends at a handler that produces no reply or at an outbound adapter. A **request–reply flow** has a return path for the result, such as a method annotated with `@MessagingGateway` invoking a flow and receiving a returned object.

## 3. From Java DSL to an IntegrationFlow Bean

A flow is typically a `@Bean` method inside a `@Configuration` class:

~~~java
@Configuration
class BasicFlowConfiguration {

    @Bean
    IntegrationFlow uppercaseFlow() {
        return IntegrationFlow.from("text.input")
                .filter(String.class, text -> !text.isBlank())
                .transform(String.class, String::toUpperCase)
                .channel("text.output")
                .get();
    }
}
~~~

In the example above:

1. `from("text.input")` declares the input channel that receives messages. The channel name will be resolved by Spring Integration in the application context.
2. `filter(...)` checks the string payload and discards blank strings; by default, rejected messages are not forwarded to the next step.
3. `transform(...)` produces a new uppercase payload. Transforming the payload does not mean losing all headers.
4. `channel("text.output")` forwards the message to the named channel. A consumer must exist for that channel if further processing is expected.
5. `get()` completes the flow definition so Spring can register the corresponding endpoints.

`IntegrationFlow` is **declarative**. When the application initializes the context, Spring Integration creates and manages the appropriate endpoints, subscriptions, and polling tasks. Do not call `uppercaseFlow()` directly to send individual messages; instead, send messages to the input channel or use a gateway.

To use the DSL in a Spring Boot project with dependency management configured, you can start with:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
~~~

The examples in this lesson use Java 17 or later and the common Spring Integration 6.x syntax. Specific adapters such as file, HTTP, JMS, or Kafka require adding their corresponding modules. When reading older documentation, note that some examples use the `IntegrationFlows` factory class; in modern versions, you can use `IntegrationFlow.from(...)` directly.

## 4. Complete Example: Receiving Orders with a Messaging Gateway

Suppose an application needs to receive an `Order`, reject orders without a positive amount, transform it into a `PaymentCommand`, and return an `OrderResult`. This example uses an internal handler to focus on the DSL; it **does not perform real payment capture yet**.

### 4.1. Application Code

~~~java
package demo.integration;

import java.math.BigDecimal;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.annotation.MessagingGateway;
import org.springframework.integration.dsl.IntegrationFlow;

@SpringBootApplication
@IntegrationComponentScan
public class OrderApplication {

    public static void main(String[] args) {
        var context = SpringApplication.run(OrderApplication.class, args);

        var gateway = context.getBean(OrderGateway.class);
        var result = gateway.submit(
                new Order("ORD-1001", new BigDecimal("250000"), "VND"));

        System.out.println(result);
    }

    @Bean
    IntegrationFlow orderFlow() {
        return IntegrationFlow.from("orders.input")
                .filter(Order.class,
                        order -> order.amount().signum() > 0,
                        endpoint -> endpoint.throwExceptionOnRejection(true))
                .transform(Order.class,
                        order -> new PaymentCommand(
                                order.id(), order.amount(), order.currency()))
                .handle(PaymentCommand.class,
                        (command, headers) -> new OrderResult(
                                command.orderId(), "ACCEPTED"))
                .get();
    }
}

@MessagingGateway(defaultRequestChannel = "orders.input")
interface OrderGateway {
    OrderResult submit(Order order);
}

record Order(String id, BigDecimal amount, String currency) {}

record PaymentCommand(String orderId, BigDecimal amount, String currency) {}

record OrderResult(String orderId, String status) {}
~~~

The example is a single file `OrderApplication.java` in package `demo.integration`. The public class name must match the file name. The `record` types and gateway interface have package-private access to keep the example concise; in a real project, they can be split into separate files.

### 4.2. Request and Reply Path

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant G as OrderGateway
    participant F as IntegrationFlow
    participant H as Handler
    C->>G: submit(Order)
    G->>F: Message<Order> to orders.input
    F->>F: filter -> transform
    F->>H: Message<PaymentCommand>
    H-->>G: OrderResult via replyChannel
    G-->>C: OrderResult
~~~

Key points to understand:

- `@IntegrationComponentScan` enables Spring to discover and create proxies for interfaces annotated with `@MessagingGateway` in the scanned package.
- `defaultRequestChannel = "orders.input"` matches the flow's input channel.
- The gateway builds a message and sets up the reply waiting mechanism. The final handler returns an `OrderResult`; when there are no further processing steps, the reply is sent to the corresponding reply channel.
- `filter(..., endpoint -> endpoint.throwExceptionOnRejection(true))` proactively raises an error if the amount is invalid. Without this setting, the filter silently drops rejected messages by default, and a request–reply call may wait until it times out.
- The example above runs along a normal synchronous call path: the caller receives either a result or an exception. When replaced with an asynchronous channel, execution timing, timeouts, and transaction boundaries may change.

**Message contract:** the input is `Order(id, amount, currency)`, where `amount` must be greater than 0; the success output is `OrderResult(orderId, "ACCEPTED")`. The example uses `currency = "VND"`; this field can be used by a router in section 5. Data constraints, payload types, channel names, and rejection behavior must be agreed upon across connected systems. For production code, you should also validate non-empty `id`, non-`null` `amount`, valid currency codes, and duplicate-processing prevention.

## 5. Common DSL Steps and How to Combine Them

### 5.1. `filter`: Separating Valid and Invalid Records

`filter` answers the question *should this message continue?*. There are two common options:

- **Drop or send to a discard channel**: suitable for data allowed to be filtered out; consider metrics and audit trails.
- **Throw an exception**: suitable when the caller needs to know the request is invalid, as in the order example.

If you drop a message in a flow where a gateway is waiting for a reply, you must explicitly decide what response the caller receives. Do not leave callers waiting without a defined timeout standard.

### 5.2. `transform`: Changing Payload While Preserving Context

Example of converting from an external system record to an application DTO:

~~~java
.transform(ExternalOrder.class,
        source -> new Order(
                source.externalId(),
                source.totalAmount()))
~~~

Normalize data types at system boundaries: timezone, currency unit, encoding, field names, date format, and nullability. For headers such as `correlationId` or `traceId`, preserve them across steps if they are still needed for tracing and reply correlation.

### 5.3. `route`: Branching by Content

The snippet below illustrates routing by the `currency` field of `PaymentCommand`. The two channels `payments.vnd` and `payments.usd` must have corresponding consumers in the application.

~~~java
.route(PaymentCommand.class, command -> command.currency(),
        mapping -> mapping
                .channelMapping("VND", "payments.vnd")
                .channelMapping("USD", "payments.usd"))
~~~

A router may need a default channel or a rule for handling missing mappings. Unexpected currencies must be handled explicitly: reject, route to an error flow, or send to a manual review branch.

### 5.4. `handle`: Executing Final Actions or Producing a Reply

A handler can invoke a business service. Complex business logic should be extracted into separate beans so the flow only describes how components connect:

~~~java
.handle(PaymentCommand.class,
        (command, headers) -> paymentService.process(command))
~~~

Here `paymentService` is an application-provided dependency. The handler's return value can become the new payload for the next stage or a reply to the gateway; `null` typically indicates no reply is produced. For one-way designs, avoid placing a synchronous gateway waiting for a non-existent return value.

### 5.5. `split` and `aggregate`: One-to-Many, Many-to-One

`split` breaks a collection or message into child messages. `aggregate` gathers them back together based on correlation information and a group completion condition. Before using them, answer:

- Which header/key identifies messages belonging to the same group?
- When is a group considered complete: expected item count reached, business condition met, or timeout expired?
- If the application restarts mid-way, where is the aggregation state stored?
- Can a duplicate message corrupt the result?

These are concerns about **message contracts and state**, not just DSL syntax.

## 6. Choosing a MessageChannel: Synchronous, Buffered, and Asynchronous

In a flow, channel selection directly affects threads, latency, load pressure, and transaction boundaries.

| Channel Type | Characteristics | When to Consider |
| --- | --- | --- |
| `DirectChannel` | Hands off directly to a subscriber, typically running on the sender's thread; suitable for synchronous calls. | Fast validation → transform → service chains. |
| `QueueChannel` | Buffers messages in a queue and waits for a consumer to poll; requires capacity management. | Decoupling producer and consumer rates when paired with a suitable poller. |
| `ExecutorChannel` | Dispatches processing to a `TaskExecutor`; can alter thread and transaction boundaries. | Processing tasks needing thread isolation with a bounded executor. |
| `PublishSubscribeChannel` | Broadcasts messages to multiple subscribers. | Auditing, metrics, and multiple branches reacting to the same event. |

Steps in the Java DSL can be connected implicitly via anonymous channels or explicitly via `.channel(...)`. Use named channels when reusing them across flows, attaching multiple consumers, or observing/controlling processing boundaries.

**Note:** declaring a queue-backed channel does not create a consumer automatically. The receiving side needs a poller or compatible endpoint; otherwise messages may sit idle. An asynchronous channel does not imply durable delivery: check message store persistence, retry mechanisms, and data loss on restart.

## 7. Inbound Adapter Example: Polling CSV Files into a Flow

An adapter that actively reads files typically needs a poller. With the `spring-integration-file` module (declared via its dependency or appropriate dependency management), you can define:

~~~xml
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-file</artifactId>
</dependency>
~~~

~~~java
package demo.integration;

import java.io.File;
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.file.dsl.Files;

@Configuration
class FileFlowConfiguration {

    @Bean
    IntegrationFlow pollCsvFiles() {
        return IntegrationFlow.from(
                    Files.inboundAdapter(new File("./inbox"))
                            .patternFilter("*.csv"),
                    endpoint -> endpoint.poller(
                            Pollers.fixedDelay(Duration.ofSeconds(5))))
                .transform(File.class, File::getAbsolutePath)
                .channel("files.ready")
                .get();
    }

    @Bean
    IntegrationFlow processFilePaths() {
        return IntegrationFlow.from("files.ready")
                .handle(String.class, (path, headers) -> {
                    System.out.println("CSV file: " + path);
                    return null; // one-way flow
                })
                .get();
    }
}
~~~

Create the `./inbox` directory before running; the path is resolved relative to the application's working directory. On each poll, the inbound adapter checks for CSV files matching the filter; each file is emitted as a `File` payload, then the transformer converts it to a `String` absolute path. The second flow consumes from `files.ready` so messages have a destination.

This example demonstrates **file detection** only—it does not read/parse CSV rows yet, nor does it handle atomic moves, partially written files, retries, or recovery. In production implementations, define:

1. Criteria for completed files (atomic rename into the inbox folder, lock files, or custom conventions).
2. Which files have already been processed and how to avoid duplicate reads after restarts; filters are only part of an idempotency strategy.
3. On parsing or downstream delivery errors, whether to retain, move to quarantine, or retry from a checkpoint.
4. Paths, file permissions, charset, size limits, and poller monitoring.

You can swap the source at the start of the flow with an SFTP inbound adapter, a JMS/AMQP/Kafka message-driven inbound adapter, an HTTP inbound gateway, or a JDBC polling adapter. Downstream DSL processing still relies on `Message`, `MessageChannel`, and endpoint concepts; receiving, connection handling, acknowledgement, and retry mechanisms remain protocol-specific.

## 8. Where Do Adapters, Gateways, and Pollers Fit in IntegrationFlow?

A flow does not have to use only one kind of input or output. A common layout looks like:

~~~mermaid
flowchart TB
    subgraph Sources["Ways to bring messages into a flow"]
        FILE["File/SFTP inbound + Poller"]
        EVENT["JMS/AMQP/Kafka listener"]
        HTTPIN["HTTP inbound gateway"]
        API["Messaging gateway from Java code"]
    end
    PIPE["Validate → Transform → Route → Handle"]
    SINK["Outbound adapter / outbound gateway"]
    DEST["File, HTTP, database,<br/>JMS, AMQP, Kafka..."]
    FILE --> PIPE
    EVENT --> PIPE
    HTTPIN --> PIPE
    API --> PIPE
    PIPE --> SINK --> DEST
~~~

| Scenario | Source / Sink Component | Decisions to Make |
| --- | --- | --- |
| Polling a directory or SFTP periodically | Inbound adapter + poller | Poll frequency, max files per poll, checkpoints, and in-progress files. |
| Receiving HTTP requests and returning HTTP responses | Inbound gateway | Mapping, body conversion, status codes, timeouts, and exception handling. |
| Sending one-way messages to a broker | Outbound adapter | Delivery/ack semantics, serializer, retries, dead-letter storage. |
| Sending a request to a target system and receiving a response | Outbound gateway | Timeout, response format, errors when the target is slow or unreachable. |
| Consuming events from JMS/AMQP/Kafka | Message-driven inbound adapter | Concurrency, ack/offset handling, ordering, redelivery, and idempotency. |
| Reading database changes periodically | JDBC inbound polling | Query selecting only new rows, transactions, and high-water marks. |

An **adapter** typically represents one-way receiving or sending; a **gateway** represents request–reply exchange. A **poller** is a scheduling mechanism for endpoints that actively pull data; not every inbound endpoint uses a poller—message-driven endpoints typically receive events via callbacks/listeners.

Do not treat a connector's API name as proof that processing is duplicate-safe or achieves exactly-once semantics. For any external destination, examine acknowledgement semantics, transaction boundaries, retries, and behavior when a step succeeds but the response is lost.

## 9. Errors, Replies, and Observability

### 9.1. Distinguishing Synchronous and Asynchronous Errors

In a synchronous chain using `DirectChannel`, exceptions from a filter, transformer, or handler usually propagate back to the gateway or sender. With a poller, executor, or listener running on another thread, exceptions are handled at the corresponding endpoint and may be published as an `ErrorMessage` to a configured `errorChannel`.

Therefore, design **error paths** according to the actual execution path of each flow style:

- **Request–reply:** normalize exceptions into error responses with business error codes; configure clear timeouts for requests and replies.
- **One-way inbound:** choose retry/backoff policies, error channels, dead-letter/quarantine handling, or persist events for later reprocessing.
- **Outbound with side effects:** retry only when you understand target behavior; use idempotency keys or deduplication to reduce the risk of double writes/sends.
- **Message-dropping filters:** distinguish *records that do not need processing* from *errors that must be reported*; emit appropriate metrics or audit logs.

### 9.2. Avoiding Lost Critical Headers

Transformers and handlers can construct new messages. When doing so, pay attention to headers used for replies, correlation, and tracing. Ideally, document conventions for payload shapes, header types, correlation IDs, and where idempotency keys are generated at integration boundaries.

For example, a request message has:

~~~text
payload = Order(id="ORD-1001", amount=250000, currency="VND")
headers = {
    correlationId: "order-ORD-1001",
    traceId: "...",
    replyChannel: <temporary channel used to return the result>
}
~~~

`replyChannel` in this example is a channel object rather than necessarily a string; the gateway typically manages this detail. Do not log raw sensitive data in payloads or headers. For HTTP and message brokers, outbound header propagation is constrained by the protocol and specific header mappers.

### 9.3. Connection and Resource Lifecycle

Spring manages flow and endpoint beans, but you still must properly configure starting/stopping adapters, thread pools, connection factories, session caches, pollers, and listener containers. When running multiple instances, decide whether every instance may poll the same source or must coordinate via locks or partitions. Collect minimum metrics including inbound/outbound message counts, error counts, latency, queue depth, and outbound processing duration.

## 10. How to Test an IntegrationFlow

For the `OrderGateway` example in section 4, test through the flow's **actual entry interface** instead of directly calling the bean method that returns `IntegrationFlow`:

~~~java
package demo.integration;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.integration.MessageRejectedException;

@SpringBootTest
class OrderFlowTest {

    @Autowired
    OrderGateway gateway;

    @Test
    void validOrderReturnsAccepted() {
        var result = gateway.submit(
                new Order("ORD-1001", new BigDecimal("250000"), "VND"));

        assertEquals("ORD-1001", result.orderId());
        assertEquals("ACCEPTED", result.status());
    }

    @Test
    void nonPositiveAmountIsRejected() {
        assertThrows(MessageRejectedException.class,
                () -> gateway.submit(
                        new Order("ORD-1002", BigDecimal.ZERO, "VND")));
    }
}
~~~

Test dependency for a Spring Boot project:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

This test verifies the real integration path: Spring registers the gateway, sends the message to the channel, invokes filter → transformer → handler, and returns the result. Depending on gateway configuration, library version, and exception translation layers, the exception type seen by the caller may be wrapped in another exception; in that case, assert the *root cause* rather than relying on the exact outer exception class.

With real adapters, expand tests to the system boundary: create files in a temporary directory, run listener tests against a test broker, simulate HTTP timeouts, verify duplicate/retry handling, and tear down resources after tests. Avoid starting real SFTP/Kafka/DB instances solely to test pure `transform` logic; prefer extracting that logic into independently testable functions or services.

## 11. Common Design Pitfalls and How to Spot Them

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| Gateway hangs and then times out. | Flow produces no reply; filter silently drops message; result sent to wrong channel. | Define the reply path explicitly; make filter throw or return a business error; configure timeouts. |
| Messages enter a channel but are never processed. | No subscriber or no consumer polling the queue. | Verify channel names, running endpoints, and poller configuration. |
| Duplicate processing of files/events. | Redelivery, restart, re-polling, or failed acknowledgement. | Use checkpoints/idempotency keys, proper archive rules, and appropriate acks. |
| Transaction does not cover downstream stages. | Thread switch across an executor, queue, or broker. | Redefine transaction boundaries; use outbox/saga or compensating actions where needed. |
| Latency spikes sharply. | Handler blocks threads for too long, queue fills up, poller falls behind, slow target. | Monitor queue depth, bound concurrency, set timeouts, tune batching and backpressure. |
| Hard to locate where a message failed. | Missing correlation ID, missing error flow, or inconsistent logging. | Standardize metadata, metrics, and centralized error message handling. |
| Data already sent externally, yet client sees an error. | Target succeeded then response was lost; retries may cause duplicates. | Design idempotent retries and distinguish uncertain outcomes from definite failures. |

## 12. Hands-On Practice Exercise

**Requirement:** build a flow `orderRoutingFlow` that receives orders through a gateway, checks that `orderId` is non-empty and `amount > 0`, transforms to `PaymentCommand`, and routes by `currency`:

- `VND` goes to a handler simulating domestic payment.
- `USD` goes to a handler simulating international payment.
- Any other currency must produce an inspectable error notification.
- Both branches return the same `OrderResult` type to the gateway.

**Completion criteria:** include tests for the happy path of each currency, invalid input data, and unsupported currency, and explain which channels the reply travels through. Next, add an inbound file adapter reading CSV files into the same business logic, normalizing each row into an `Order` before sending to the shared channel; try submitting the same `orderId` twice and propose a strategy to prevent double processing.

Design hint: separate validation/normalization before the router; have all processing branches return a unified result type; for one-way file inputs, decide clearly where results and errors are stored since there is no HTTP caller waiting for a reply.

## 13. Key Takeaways

`IntegrationFlow` with the Java DSL is a **declarative way to define message routing and processing** through Spring-managed endpoints. A sound flow clarifies four elements: the entry source and payload/header contract, transformation/routing steps, channels along with synchronous or polling execution, and destinations paired with error-handling paths.

When connecting files, SFTP, HTTP, JMS, AMQP, Kafka, or databases, the Java DSL helps reuse the message model and step composition. End-to-end reliability still depends on protocols, acknowledgements, timeouts, retries, idempotency, and connection lifecycles that are properly designed, configured, and tested.
