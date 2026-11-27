# Bridge Between an Adapter and Another Channel

## 1. Context and Objectives

In Spring Integration, an inbound adapter typically emits messages to a `MessageChannel`. Downstream processing may already be wired to a different channel or organized into multiple independent integration flows. When you need to connect **an adapter's output** to **another flow's input channel** without applying business transformations, you use a **Bridge**.

A Bridge is an *Enterprise Integration Pattern*: an endpoint that consumes messages from a source channel and forwards them to a destination channel. Spring Integration provides bridge support via the Java DSL, XML namespaces, and corresponding framework components. A bridge is especially useful when two parts of a system rely on stable channel names yet are configured, deployed, or migrated in stages.

This lesson belongs to the **Integration Flow Creation** chapter of the **SPRING_INTEGRATION_ADAPTERS** module. The module scope covers connecting external systems through inbound/outbound adapters, gateways, pollers, and `MessageChannel`; building flows for files, SFTP, HTTP, JMS, AMQP, Kafka, and databases; and managing message contracts, errors, and connection lifecycles.

After this lesson, learners will be able to:

- Explain why a Bridge is needed and distinguish a bridge from channels, routers, transformers, and gateways.
- Connect a file inbound adapter to another integration flow's channel using Java DSL `.bridge()`.
- Configure `<int:bridge>` in the XML namespace.
- Contrast bridge behavior over `DirectChannel` versus over a `QueueChannel` requiring a poller.
- Understand how bridges preserve payloads/headers and how channels impact threading, transactions, and timeouts.
- Design error handling, retries, backpressure, and deduplication when joining two flows.
- Test the real path through **source channel → bridge → target channel → handler**.

**Scope:** a Bridge is a message-forwarding step. It does not convert schemas, guarantee durable storage, send broker ACKs, or guarantee exactly-once processing in external systems.

## 2. What Does a Bridge Do?

Suppose a file inbound adapter scans `./inbox` and sends each `Message<File>` to `adapter.files`. Meanwhile, an existing CSV processing flow starts at `processing.files`. To connect both parts while keeping their channel names intact, add a bridge:

~~~mermaid
flowchart LR
    DIR[("Inbox directory")]
    SRC["File inbound adapter<br/>+ poller"]
    A["adapter.files<br/>DirectChannel"]
    B["Bridge endpoint"]
    C["processing.files<br/>DirectChannel"]
    VALID["Filter / Validate"]
    HANDLER["CSV processor<br/>or outbound adapter"]
    DIR --> SRC --> A --> B --> C --> VALID --> HANDLER
~~~

A bridge receives a message and **forwards the same business content** to the target channel. No CSV parsing, type conversion, or automatic awareness of HTTP/SFTP/JMS destinations occurs simply because a message passes through a bridge.

| Component | Question It Answers | Example |
| --- | --- | --- |
| Inbound adapter | How is external data brought into the system? | File/SFTP poller, JMS listener. |
| `MessageChannel` | Where do producers and consumers hand off messages? | `adapter.files`, `processing.files`. |
| **Bridge** | How do we link two channels without changing business payload? | `adapter.files → processing.files`. |
| Transformer | What type should the payload be converted from and to? | `File → List<Order>`. |
| Filter | Which messages are allowed to continue? | Drop empty files or reject invalid records. |
| Router | Which branch should a message be sent to? | `VND → payments.vnd`, `USD → payments.usd`. |
| Gateway | Does a request need a reply returned to the caller/flow? | HTTP outbound gateway, messaging gateway. |

### 2.1. A Bridge Is Not a Channel

A channel is a message conduit; a Bridge is an **endpoint** with an input and an output. When configuring:

~~~text
source-channel  ──> Bridge ──> destination-channel
~~~

the framework needs a consumer on `source-channel` and a downstream consumer on `destination-channel` for messages to be processed end-to-end. Declaring two channels in the same context **does not automatically link them**.

If an adapter can be pointed directly at the target channel and no intermediate boundary is required, configure the adapter to send straight there. A bridge earns its place when preserving an existing channel contract, joining two independent flows, or changing handoff semantics at a clean boundary.

### 2.2. Does a Bridge Create a New Message?

Business-wise, a bridge only forwards: the payload and processing/correlation headers continue downstream. Under normal conditions, `BridgeHandler` does not alter business data. However, do not rely on **Java object identity** or assume that after crossing a broker, serializer, or mapper, every internal header remains identical.

What must be verified is the **contract**: payload type, correlation ID, business metadata, and headers required for replies/errors must arrive at the other side according to the active transport mechanism.

## 3. Java DSL: Bridging Two Existing Channels

Minimal example:

~~~java
@Bean
IntegrationFlow filesBridgeFlow() {
    return IntegrationFlow.from("adapter.files")
            .bridge()
            .channel("processing.files")
            .get();
}
~~~

Assume the Spring context already has two channel beans named `adapter.files` and `processing.files`. The flow above registers a Bridge endpoint consuming from `adapter.files` and forwarding to `processing.files`.

- `IntegrationFlow.from("adapter.files")`: declares the flow's input channel.
- `.bridge()`: creates an intermediate handler whose purpose is forwarding messages.
- `.channel("processing.files")`: specifies the channel receiving the bridge's output.
- `.get()`: finalizes the flow definition so Spring registers the endpoint.

This is a **channel-connecting flow**, not an active polling adapter. It has no `MessageSource` or `Poller` unless the source channel itself is pollable or fed by another flow.

The Java DSL can also reference channel beans directly instead of string IDs depending on your configuration style. When using strings, match bean names exactly; for instance, `processing.file` and `processing.files` are distinct names.

### 3.1. Should You Write .bridge() at Every Channel Transition?

**No.** Inside a linear `IntegrationFlow`, you can transition via `.channel(...)` and continue processing steps. The DSL wires endpoints and channels within a flow automatically.

An explicit bridge makes sense when **the target is simply another flow's channel** or you want readers to see a clear boundary linking two channels. For example:

~~~java
@Bean
IntegrationFlow normalizeAndForward() {
    return IntegrationFlow.from("raw.orders")
            .filter(Order.class, order -> order.amount() > 0)
            .transform(Order.class, this::normalizeOrder)
            .channel("normalized.orders")
            .get();
}
~~~

This snippet is *illustrative*: `Order` and `normalizeOrder` are application-provided. The flow applies filter/transform steps and hands off to a channel; there is no need to insert a bare bridge before each step.

Conversely, if you only need to connect `adapter.files` to `processing.files` with no transformation, the `.bridge()` flow at the start of this section expresses that intent directly.

## 4. Complete Example: File Inbound Adapter → Bridge → Processing Flow

Practice scenario: an application reads `*.csv` files from `./inbox` every 5 seconds. The adapter emits `Message<File>` to `adapter.files`. A Bridge forwards it to `processing.files`. The final flow verifies the file is non-empty and records the filename and header in a result receiver bean.

The architecture intentionally separates **three small flows**: file source, bridge, and processing. This lets you swap the file source for SFTP/JMS/Kafka while reusing downstream processing as long as the payload/header contract matches.

### 4.1. Dependencies

With Spring Boot managing dependency versions:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-file</artifactId>
</dependency>
~~~

The example uses Java 17+ and standard Spring Integration 6.x APIs. Place all code below in `BridgeApplication.java`, package `demo.bridge`. Only one class is `public`; the rest are package-private for concise demonstration.

### 4.2. Configuring the Source, Bridge, and Consumer

~~~java
package demo.bridge;

import java.io.File;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.core.MessageSource;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.file.FileReadingMessageSource;
import org.springframework.integration.file.filters.AcceptOnceFileListFilter;
import org.springframework.integration.file.filters.CompositeFileListFilter;
import org.springframework.integration.file.filters.SimplePatternFileListFilter;
import org.springframework.messaging.MessageChannel;
import org.springframework.stereotype.Component;

@SpringBootApplication
public class BridgeApplication {
    public static void main(String[] args) {
        SpringApplication.run(BridgeApplication.class, args);
    }
}

@Configuration
class BridgeConfiguration {

    @Bean(name = "adapter.files")
    MessageChannel adapterFiles() {
        return new DirectChannel();
    }

    @Bean(name = "processing.files")
    MessageChannel processingFiles() {
        return new DirectChannel();
    }

    @Bean
    MessageSource<File> csvFileSource(
            @Value("${app.inbox:./inbox}") String inbox) {

        File directory = new File(inbox);
        if (!directory.exists() && !directory.mkdirs()) {
            throw new IllegalStateException(
                    "Failed to create source directory: " + directory);
        }
        if (!directory.isDirectory()) {
            throw new IllegalStateException(
                    "Source path is not a directory: " + directory);
        }

        var source = new FileReadingMessageSource();
        source.setDirectory(directory);

        var filters = new CompositeFileListFilter<File>();
        filters.addFilter(new SimplePatternFileListFilter("*.csv"));
        filters.addFilter(new AcceptOnceFileListFilter<>());
        source.setFilter(filters);

        return source;
    }

    // Flow 1: inbound adapter emits messages into the source channel.
    @Bean
    IntegrationFlow fileInboundFlow(MessageSource<File> csvFileSource) {
        return IntegrationFlow
                .from(csvFileSource,
                        endpoint -> endpoint.poller(
                                Pollers.fixedDelay(Duration.ofSeconds(5))
                                        .maxMessagesPerPoll(5)))
                .channel("adapter.files")
                .get();
    }

    // Flow 2: bridge connects two channels without modifying the payload.
    @Bean
    IntegrationFlow fileBridgeFlow() {
        return IntegrationFlow.from("adapter.files")
                .bridge()
                .channel("processing.files")
                .get();
    }

    // Flow 3: downstream processing after the bridge.
    @Bean
    IntegrationFlow fileProcessingFlow(FileReceiver receiver) {
        return IntegrationFlow.from("processing.files")
                .filter(File.class,
                        file -> file.isFile() && file.length() > 0)
                .handle(File.class, (file, headers) -> {
                    receiver.record(
                            file.getName(),
                            (String) headers.get("traceId"));
                    return null; // one-way: produces no reply
                })
                .get();
    }
}

record ReceivedFile(String fileName, String traceId) {}

@Component
class FileReceiver {

    private final List<ReceivedFile> results =
            new CopyOnWriteArrayList<>();

    void record(String name, String traceId) {
        results.add(new ReceivedFile(name, traceId));
        System.out.println("CSV accepted: " + name);
    }

    List<ReceivedFile> received() {
        return List.copyOf(results);
    }

    void clear() {
        results.clear();
    }
}
~~~

How are the parts wired together?

1. `csvFileSource` is a `MessageSource<File>` bean. `fileInboundFlow` attaches a poller to the source; when a CSV file is found, it emits `Message<File>`.
2. `fileInboundFlow` sends the message to `adapter.files`. It never calls `FileReceiver` directly.
3. `fileBridgeFlow` subscribes to `adapter.files` and uses `BridgeHandler` to forward the message to `processing.files`.
4. `fileProcessingFlow` subscribes to `processing.files`, checks the file, and records it in `FileReceiver`.
5. `FileReceiver` stores results for demonstration and testing; it does not make HTTP calls or write to a database.

The example uses `DirectChannel` at both boundaries, so once the source sends a message to `adapter.files`, the bridge and downstream handler usually execute on the same thread until processing finishes. The poller still triggers the source; the bridge has no schedule of its own.

### 4.3. Path of a File

~~~mermaid
sequenceDiagram
    participant P as File poller
    participant S as csvFileSource
    participant A as adapter.files
    participant B as Bridge
    participant C as processing.files
    participant H as FileReceiver
    P->>S: receive()
    S-->>P: Message<File> or null
    P->>A: send(Message<File>)
    A->>B: handle(message)
    B->>C: send(message)
    C->>H: filter + record
    H-->>P: synchronous processing completes
~~~

If the poller runs when no files exist, `receive()` returns `null` and no message enters the bridge. If the downstream CSV handler is slow, `DirectChannel` stretches out the poll cycle; `fixedDelay` does not guarantee a specific number of files per second.

**Demo reliability note:** `AcceptOnceFileListFilter` only remembers seen files in process memory. It is insufficient to prevent duplicate reads across restarts, multiple instances, or cases where a file was accepted by the source but the downstream handler failed. Stronger guarantees require completed-file detection, persistent metadata stores, archive/quarantine handling, and business-level idempotency.

## 5. Testing That the Bridge Actually Connects Both Channels

To verify the Bridge, send a message directly to the **adapter channel** and observe the consumer on the **processing channel**. This tests the wiring of both flows without waiting for a polling schedule.

Add the test dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Create `BridgeApplicationTest.java` in package `demo.bridge`:

~~~java
package demo.bridge;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

@SpringBootTest(properties = "app.inbox=./target/bridge-test-inbox")
class BridgeApplicationTest {

    @Autowired
    @Qualifier("adapter.files")
    MessageChannel adapterFiles;

    @Autowired
    FileReceiver receiver;

    @BeforeEach
    void clearResults() {
        receiver.clear();
    }

    @Test
    void forwardsFileAndKeepsTraceHeader() throws Exception {
        Path csv = Files.createTempFile("bridge-", ".csv");
        try {
            Files.writeString(csv, "id,amount\n1,100\n",
                    StandardCharsets.UTF_8);

            boolean sent = adapterFiles.send(
                    MessageBuilder.withPayload(csv.toFile())
                            .setHeader("traceId", "trace-test-01")
                            .build());

            assertTrue(sent);
            assertEquals(
                    List.of(new ReceivedFile(
                            csv.getFileName().toString(), "trace-test-01")),
                    receiver.received());
        } finally {
            Files.deleteIfExists(csv);
        }
    }
}
~~~

This test confirms:

- `adapter.files` exists and has a Bridge consumer.
- The Bridge forwards the message to `processing.files`.
- The downstream consumer receives the `File` payload.
- The `traceId` header is preserved across the bridge.
- Two `DirectChannel` beans allow asserting the outcome right after `send()`.

**Test limitation:** because the test sends directly to the channel, it does **not** verify the poller, directory scanning, or the `*.csv` source filter. To test the real inbound adapter, drop files into a test directory before/after context startup and wait using a bounded timeout condition. Never use arbitrary `Thread.sleep(...)` calls as proof that a poller works reliably.

## 6. Bridging from a QueueChannel: When Is a Poller Required?

In section 4, `adapter.files` is a `DirectChannel`: the sender hands off directly to the bridge subscriber. To decouple file intake speed from downstream processing speed, you can replace that boundary with a `QueueChannel`. At that point, **the Bridge is a consumer of a pollable channel**, so it requires a poller to pull messages from the queue.

~~~mermaid
flowchart LR
    A["Inbound adapter"]
    Q["buffered.files<br/>QueueChannel(capacity=100)"]
    P["Bridge endpoint<br/>with Poller"]
    D["processing.files<br/>DirectChannel"]
    H["Handler"]
    A -->|"offer/message"| Q
    Q -->|"poll()"| P
    P --> D --> H
~~~

### 6.1. Configuration with Java DSL

The example below is a **variant** for a single message boundary; do not register it alongside the `adapter.files` bridge in section 4 without redesigning the topology.

~~~java
@Bean(name = "buffered.files")
QueueChannel bufferedFiles() {
    return new QueueChannel(100);
}

@Bean
IntegrationFlow queueToProcessingBridge() {
    return IntegrationFlow.from("buffered.files")
            .bridge(endpoint -> endpoint.poller(
                    Pollers.fixedDelay(Duration.ofMillis(500))
                            .maxMessagesPerPoll(10)))
            .channel("processing.files")
            .get();
}
~~~

This snippet requires importing `QueueChannel`, `IntegrationFlow`, `Pollers`, `Duration`, and `@Bean`; `processing.files` and its downstream consumer flow must be configured separately.

- `QueueChannel(100)` bounds buffer capacity to prevent unbounded memory growth; define behavior when the queue is full.
- `.bridge(endpoint -> endpoint.poller(...))` creates a scheduled consumer pulling messages from the queue.
- `maxMessagesPerPoll(10)` caps how many messages are processed per poller tick; it does not combine ten messages into a single batch.
- `processing.files` receives each message from the Bridge and dispatches it to handlers according to the destination channel type.

**Note:** `QueueChannel` defaults to an in-memory buffer and does not provide durability across restarts. If the application stops while messages remain in the queue, those messages can be lost unless backed by a persistent message store or another durable delivery mechanism.

### 6.2. How DirectChannel and QueueChannel Differ

| Criterion | `DirectChannel → Bridge → DirectChannel` | `QueueChannel → Bridge poller → DirectChannel` |
| --- | --- | --- |
| When does the Bridge run? | Immediately when the source sends a message. | When the poller pulls a message from the queue. |
| Typical thread | Same thread as the producer. | Poller thread, distinct from the thread enqueuing the message. |
| Buffer between parts? | No queue created by `DirectChannel`. | Yes, a queue with configured capacity. |
| Poller needed on Bridge? | No. | Yes, because the input is a `PollableChannel`. |
| Producer transaction | Can span synchronous steps on the same thread. | Does not automatically span across the queue/thread boundary. |
| Load pressure | Slow handler slows down the producer. | Queue absorbs brief rate mismatches, but risks filling up. |
| Restart recovery | Depends on source/destination. | Requires queue persistence plus ack/retry policies. |

Putting a `QueueChannel` in the middle is an **architectural decision**, not a one-line "enable reliable delivery" switch. You must plan capacity, queue-full policy, transactions, retries, in-flight state, and backlog monitoring.

## 7. Configuring a Bridge with XML Namespaces

Spring Integration also supports Bridges in the core XML namespace. Example with two synchronous channels:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:int="http://www.springframework.org/schema/integration"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           http://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/integration
           http://www.springframework.org/schema/integration/spring-integration.xsd">

    <int:channel id="adapter.files"/>
    <int:channel id="processing.files"/>

    <int:bridge id="filesBridge"
                input-channel="adapter.files"
                output-channel="processing.files"/>

    <!-- Downstream consumer of processing.files is configured separately. -->
</beans>
~~~

`<int:bridge>` creates an endpoint forwarding messages from `input-channel` to `output-channel`. It does not register a file inbound adapter by itself; producers must send to `adapter.files`, and a consumer must subscribe to `processing.files`.

### 7.1. XML When Bridging from a QueueChannel

~~~xml
<int:channel id="buffered.files">
    <int:queue capacity="100"/>
</int:channel>

<int:channel id="processing.files"/>

<int:bridge id="bufferedFilesBridge"
            input-channel="buffered.files"
            output-channel="processing.files">
    <int:poller fixed-delay="500"
                max-messages-per-poll="10"/>
</int:bridge>
~~~

This configuration is a **standalone example**; `<int:queue>` creates the queue and the poller drains it. Channel names must match where the adapter sends messages. If the source is a file inbound adapter, its output can point directly to `buffered.files`.

In a Spring Boot app, you can load this XML via `@ImportResource("classpath:integration/bridge-flow.xml")`. Avoid registering a second Java DSL bridge across the same two channels unless you intentionally want duplicate competing consumers.

## 8. Bridging Protocol Inbound/Outbound Adapters

A Bridge works with messages from many sources whenever channel and payload contracts align. Common scenarios:

| Source or Sink | Where Does the Bridge Connect? | What to Control |
| --- | --- | --- |
| File inbound | File adapter → output channel → Bridge → CSV parsing flow. | Completed files, accept-once, archiving, parse errors. |
| SFTP inbound | SFTP adapter → shared channel → Bridge → file processor. | Remote filters, local sync, sessions, reconnects, duplicates. |
| HTTP inbound gateway | HTTP gateway → channel → Bridge → reply handler. | Preserving `replyChannel`, timeouts, response mapping. |
| JMS/AMQP inbound | Message-driven adapter → Bridge → business flow. | Transactions/acks, redelivery, converters, DLQ. |
| Kafka inbound | Kafka adapter → Bridge → processing flow. | Topics/partitions, offset commits, ordering, idempotency. |
| JDBC polling | JDBC message source → Bridge → validation/handler. | Query checkpoints, locks, transactions, duplicate rows. |
| HTTP/JMS/Kafka outbound | Business flow → Bridge → channel to outbound endpoint. | Producer acknowledgements, uncertain failures, retries. |

**A Bridge does not establish protocol connections.** For instance, SFTP requires its own session factory and adapter; JMS needs a connection factory and listener container; Kafka needs producer/consumer config. A Bridge only sees messages already placed on a Spring Integration channel.

### 8.1. Swapping Adapters Without Changing Downstream Logic

You can define a canonical contract channel, such as `orders.normalized`, and have each adapter run a normalization flow before forwarding into it:

~~~mermaid
flowchart TB
    F["File/SFTP inbound"]
    K["Kafka inbound"]
    H["HTTP inbound"]
    TF["Parse CSV → OrderEvent"]
    TK["Deserialize → OrderEvent"]
    TH["Validate JSON → OrderEvent"]
    C["orders.normalized<br/>MessageChannel"]
    P["Business processor"]
    F --> TF --> C
    K --> TK --> C
    H --> TH --> C
    C --> P
~~~

This illustrates **channel reuse**, not necessarily needing a bridge on every branch. When an adapter already emits the exact `OrderEvent` payload and just needs forwarding to the canonical channel, a bridge fits well. When the payload is still a `File`, byte array, or protocol-specific DTO, **transform and validate first** before bridging. Never pass non-conforming payloads across a bridge hoping downstream consumers will figure them out.

### 8.2. A Bridge Does Not Replace Routers or Publish–Subscribe

To pick **one of several targets** based on currency or event type, use a router. To send **the same message to multiple consumers**, use a `PublishSubscribeChannel` or a multicast flow with an error-handling strategy. A basic Bridge connects **one input channel to one output channel** without automatic fan-out.

If two Bridges subscribe to the same `DirectChannel`, the channel dispatcher typically hands each message to one subscriber according to its dispatching strategy rather than sending to both. Replicating data to two external systems requires explicit broadcast, transaction, and idempotency design per branch.

## 9. Message Contracts: Payloads, Headers, and Replies

A Bridge separates topology without altering business data. Precisely for that reason, both sides must agree on a clear **contract**.

~~~text
Message<OrderEvent>
  payload:
    eventId: "evt-4711"
    orderId: "ORD-1001"
    amount: 250000
  headers:
    correlationId: "trace-ord-1001"
    sourceSystem: "sftp-import"
    idempotencyKey: "order:ORD-1001"
~~~

| Element | What Should the Bridge Do? | What Downstream Must Understand |
| --- | --- | --- |
| Payload type | Forward the existing payload. | DTO/schema/serialization compatible with the consumer. |
| `correlationId` | Keep metadata used for tracing. | Link logs across adapter, bridge, handler, and destination. |
| `sourceSystem` | Preserve the data origin. | Apply source-specific processing rules. |
| `idempotencyKey` | Forward stable key if present. | Prevent duplicate side effects at handler/target. |
| `replyChannel` | Preserve reply path for internal request–reply channels. | Handler must send replies to the right destination. |
| `errorChannel` | Preserve error routing info when present. | Error handlers must be configured appropriately. |

Never pass all `MessageHeaders` blindly over HTTP, JMS, AMQP, or Kafka: internal headers may contain `MessageChannel` objects unsuitable for serialization. Protocol adapter mappers decide which headers cross network boundaries.

### 9.1. Bridges in Request–Reply Flows

Suppose a `@MessagingGateway` calls `orders.requests`, a Bridge forwards to `orders.processor`, and the final service activator returns `OrderResult`. As long as the reply path is preserved and the handler returns a result, the gateway receives the reply from the downstream flow.

~~~mermaid
sequenceDiagram
    participant G as MessagingGateway
    participant A as orders.requests
    participant B as Bridge
    participant P as orders.processor
    participant H as Handler
    G->>A: Request + replyChannel
    A->>B: Message
    B->>P: Message
    P->>H: handle
    H-->>G: Reply to replyChannel
~~~

However, a Bridge **does not generate replies itself**. If the final handler returns `void` or a filter silently drops the message, a gateway expecting a DTO may wait until timeout. With asynchronous channels, replies may arrive late; define timeouts and indeterminate business states explicitly.

## 10. Threads, Transactions, and Backpressure at the Bridge

A Bridge does not itself decide synchronous vs. asynchronous execution; **channel and endpoint types** determine that.

- With `DirectChannel → Bridge → DirectChannel`, execution usually stays on the sender's thread. Exceptions from the target handler can propagate back to the inbound endpoint or caller.
- With `QueueChannel → Bridge poller`, pulling messages from the queue runs on the poller thread, so it does not automatically share a transaction with the thread that enqueued the message.
- With `ExecutorChannel`, downstream steps run on an executor thread; bound the thread pool, internal queue, and handle errors independently.
- With JMS/Kafka/AMQP brokers, the source has its own ack/offset lifecycle; a Spring Integration Bridge does not govern broker commit timing.

A Bridge feeding from a `QueueChannel` can absorb rate bursts, yet if the destination remains slower than the source for a long time, the backlog grows until capacity is reached. Producers may then block, fail to send, or trigger overload policies.

### 10.1. Do Transactions Cross a Bridge?

When every step uses synchronous `DirectChannel` beans, a thread's transaction scope can encompass downstream handlers if configured appropriately. However, a Bridge **never creates a transaction on its own**. When crossing a queue, executor, or broker, never assume the same database transaction still covers the receiving side.

For example, a JDBC source reads a row and a handler sends HTTP across a Bridge: the JDBC transaction cannot automatically roll back an HTTP request already processed by a partner. Consider outbox patterns, delivery state tracking, idempotency, and contractual reconciliation.

### 10.2. When Should You Avoid Adding an Intermediate Channel?

If you only have one adapter, one transformer, and one handler in the same flow, inserting extra channels and bridges just to "split code" can obscure the topology without real benefit. Introduce a channel boundary when you need to:

1. Maintain a stable integration interface between teams or modules.
2. Connect flows configured in separate places or during migrations.
3. Switch handoff semantics (queue, executor, publish–subscribe).
4. Manage, measure, or swap consumers at a specific boundary.

For simple pipelines, point the adapter directly to the target channel or use a single linear `IntegrationFlow`.

## 11. Error Handling When a Bridge Joins Two Flows

There are at least three failure points:

~~~mermaid
flowchart TD
    S["Inbound adapter receives data"]
    B["Bridge forwards message"]
    H["Handler / outbound adapter"]
    OK["Completed per contract"]
    E1["Source / polling error"]
    E2["Dispatch error / no subscriber"]
    E3["Processing / target system error"]
    S --> B --> H --> OK
    S -.-> E1
    B -.-> E2
    H -.-> E3
~~~

| Failure | Example | Handling Strategy |
| --- | --- | --- |
| Source failure | SFTP timeout, file permissions, failed JDBC query. | Source-level retry/backoff, reconnect, and alerting. |
| Dispatch failure | Target channel has no consumer, queue full, stopped endpoint. | Check wiring, queue bounds, and lifecycle state. |
| Validation failure | Message crosses bridge with malformed payload. | Validate at the right boundary; use error flow/quarantine instead of infinite retries. |
| Destination failure | HTTP timeout, JMS broker down, database rollback. | Idempotent retries, DLQ, delivery state, reconciliation. |
| Uncertain outcome | Partner succeeded, but response was lost. | Check via business key; avoid blind duplicate sends. |

**Never treat a Bridge forwarding a message to a channel as "business completion".** Success at this boundary only proves internal handoff; real status must be confirmed at the handler/target per protocol.

### 11.1. Error Channels and Threading

With synchronous channels, exceptions can propagate up the call stack to the poller or gateway. With pollers, executors, listeners, or queues, exceptions may be published as an `ErrorMessage` to a configured `errorChannel`, or handled per endpoint policy.

A Bridge is not where all errors should be handled. Place retries at the layer that understands the cause: connection failures in adapters/clients; schema errors in validators; side-effect errors in outbound handlers with idempotency and recovery workflows.

### 11.2. Behavior When Downstream Stops

If `processing.files` has no subscriber or its consumer is stopped, a `DirectChannel` cannot dispatch the message. If an upstream file source uses an in-memory accept-once filter, the file may already be marked seen in the source before the downstream error occurs. You need explicit recovery mechanisms and tests; merely restarting the Bridge or handler does not guarantee the file will be re-emitted.

To decouple ingestion time from processing time safely, choose a queue or broker with persistent storage and proper monitoring rather than expecting a Bridge to hold messages.

## 12. Common Configuration Errors

| Symptom | Common Cause | Fix |
| --- | --- | --- |
| Adapter sends messages, yet downstream flow never runs. | Wrong channel name, missing Bridge consumer, or endpoint not started. | Verify channel beans and `IntegrationFlow.from(...)` / XML bridge. |
| Bridge is never called despite messages in `QueueChannel`. | Missing poller on Bridge consumer. | Configure `.bridge(endpoint -> endpoint.poller(...))` or XML `<int:poller>`. |
| Two bridges subscribe to one `DirectChannel`, yet only one runs. | `DirectChannel` does not broadcast by default. | Use `PublishSubscribeChannel` if fan-out is required. |
| Payload reaches destination with the wrong type. | Bridge does not transform; source emits `File` while consumer expects `Order`. | Normalize/validate payload before the channel boundary. |
| Request–reply times out. | Reply path lost, handler produces no reply, or filter dropped message. | Check `replyChannel`, business responses, and timeouts. |
| Poller slows down after adding a Bridge. | Downstream runs synchronously on the poller thread. | Measure latency, cap work per poll, and pick suitable channels. |
| Messages vanish on restart after adding `QueueChannel`. | Queue lives only in RAM with no persistence. | Use a persistent message store or broker with proper retries. |
| Files are processed twice. | Two sources/pollers reading together, non-persistent filter, or redelivery. | Use a single clear source, locks/checkpoints, and idempotency. |
| Destination receives duplicates on retry. | Side effect succeeded but response was lost. | Use idempotency keys and reconciliation. |
| Errors appear only in background logs. | Thread switch without error flow or metrics. | Configure `errorChannel`, DLQ, and correlation IDs. |

## 13. Verifying Topology Before Production Deployment

Before introducing a Bridge into a live flow, trace every link with a sample message:

1. Confirm what payload type and headers the inbound adapter actually emits.
2. Confirm the output channel name and channel type (`DirectChannel` vs. `QueueChannel`).
3. Confirm the Bridge subscribes to the exact **input channel** with no unintended duplicate consumers.
4. Confirm the Bridge sends to the exact **output channel**.
5. Confirm downstream has a subscriber/poller and the handler expects that payload type.
6. Use a correlation ID to trace the message end-to-end; measure send/receive latency and errors.
7. Simulate stopping downstream, filling the queue, throwing exceptions, and restarting to verify recovery.

When mixing XML and Java DSL: both register beans in the same application context. Avoid declaring both `<int:bridge input-channel="adapter.files" ...>` and a `.bridge()` flow for the same purpose unless you deliberately want competing consumers—doing so can split traffic unexpectedly.

### 13.1. Useful Metrics

At the Bridge boundary, track messages entering the source channel, messages forwarded, messages processed successfully downstream, channel send errors, queue depth, and latency. When brokers or outbound side effects are involved, also track acks, retries, dead-letter counts, and duplicates by business key.

If your Spring Integration version/config supports Micrometer or observation, enable metrics/tracing on endpoints and channels. Never log entire payloads or sensitive headers just to monitor a bridge; selective IDs and metadata are usually enough for tracing.

## 14. Practice Exercise: Bridging File Inbound with a Payment Flow

**Scenario:** an inbound adapter reads CSV payment files from SFTP and emits `Message<File>`. An existing payment processing service only listens on `payments.files`. You need to connect both parts without modifying the existing processor code.

Requirements:

1. Define source channel `sftp.files` and destination channel `payments.files`.
2. Create a Bridge using the Java DSL, preserving the `File` payload and `sourceSystem` header.
3. Add a poller on the SFTP inbound adapter; explain why with `DirectChannel` the Bridge does not need its own poller.
4. Replace `sftp.files` with `QueueChannel(100)`, move the poller to the Bridge consumer, and explain threading and transaction differences.
5. Write a test sending `Message<File>` with `correlationId` into `sftp.files`; verify the handler receives the exact header and payload.
6. Design a quarantine branch for malformed files before writing to the database.
7. Simulate a database failure after the source has accepted a file; define how to replay safely without duplicate writes.
8. Simulate two instances polling SFTP simultaneously; propose an appropriate lock, partition, or checkpoint strategy.

**Completion criteria:** the diagram includes source, channels, Bridge, and consumer; tests execute through the real Bridge; you explain why the payload needs no conversion when contracts match and why a Bridge does not itself guarantee retries or ACKs.

## 15. Self-Check Questions

1. How does a Bridge differ from a `MessageChannel`?
2. When should you use `IntegrationFlow.from("source").bridge().channel("target")`?
3. Can an adapter point directly to the target channel without a Bridge? When is that appropriate?
4. Does a Bridge automatically parse a `File` into an `Order`?
5. Why does a Bridge consuming from a `QueueChannel` need a poller?
6. Does `maxMessagesPerPoll(10)` count messages or lines inside a file?
7. With `DirectChannel`, how does a slow downstream handler affect the inbound adapter's thread?
8. If two Bridges subscribe to the same `DirectChannel`, do both automatically receive every message?
9. Can a Bridge preserve `replyChannel` for request–reply? What is required for the caller to receive the reply?
10. Why doesn't an in-memory `QueueChannel` guarantee recovery across restarts?
11. When a handler fails after a file was marked accept-once, will the next poll automatically re-emit that file?
12. How do you verify payload/header contracts when replacing a file inbound source with Kafka inbound?

**Hints:** a Bridge is a forwarding endpoint between two channels; pollers belong to pollable sources; threading is determined by channels and endpoints; source adapters and destination handlers own protocol reliability and business state.

## 16. Key Takeaways

A **Bridge between an adapter and another channel** joins two regions of a Spring Integration system without altering business message contents. It keeps channel names stable, decouples source configuration from downstream logic, and helps organize Java DSL or XML flows along clear boundaries.

When connecting files, SFTP, HTTP, JMS, AMQP, Kafka, or databases, a Bridge only forwards messages across channels. **Payload/header contracts, synchronous vs. queue/poller dispatch, error handling, idempotency, and destination acknowledgements** must still be designed explicitly. Testing through both channels and downstream handlers proves the Bridge is registered, wired, and operating properly.
