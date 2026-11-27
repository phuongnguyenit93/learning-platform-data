# Registering Adapters as Standalone Beans

## 1. Problem and Objectives

In Spring Integration, an **adapter** connects an external system to a message flow. An inbound adapter receives external data and emits `Message<?>` into a `MessageChannel`; an outbound adapter receives messages from a channel and sends data outward. You can declare adapters inline inside `IntegrationFlow`, yet it is often cleaner to register the **connector component as a separate Spring bean** and wire that bean into the flow.

This lesson belongs to the **Integration Flow Creation** chapter of the **SPRING_INTEGRATION_ADAPTERS** module, focusing on connecting external systems via inbound/outbound adapters, gateways, pollers, and `MessageChannel`. Scenarios involving files, SFTP, HTTP, JMS, AMQP, Kafka, and databases all raise the same question: **which component reads/writes data, which component triggers it, and which component processes the message?** Designing standalone beans clarifies those three responsibilities, along with error control and connection lifecycles.

After this lesson, learners will be able to:

- Distinguish a **bean holding read/write capability** from an **endpoint registered with a channel and lifecycle**.
- Create a `MessageSource<File>` via `@Bean` and drive it with `@InboundChannelAdapter` or the Java DSL.
- Create an outbound `MessageHandler` via `@Bean` and connect it to a channel via `@ServiceActivator` or `IntegrationFlow.handle(...)`.
- Use dependency injection instead of calling `new` on adapters in multiple places.
- Understand bean naming, sharing source/destination configuration, and avoiding competing duplicate endpoints.
- Analyze risks of duplicate polling, processing failures, timeouts, transactions, and stopping/starting adapters.
- Test both individual beans and actual message paths through the Spring context.

**Most important takeaway:** registering a `MessageSource` or `MessageHandler` as a bean **does not by itself create an active integration endpoint**. A source needs a polling or message-driven endpoint; a handler needs a consumer subscribed to a channel. The standalone bean supplies capabilities and dependencies, whereas the endpoint determines when and how that bean is invoked.

## 2. Separating Three Layers: Bean, Endpoint, and Integration Flow

Consider an application that scans a CSV directory and moves files to a target directory.

~~~mermaid
flowchart LR
    SRC[("Source directory")]
    MS["MessageSource<File> bean<br/>FileReadingMessageSource"]
    EP1["Inbound polling endpoint<br/>+ Poller"]
    IN["files.detected<br/>MessageChannel"]
    FLOW["IntegrationFlow<br/>filter / transform"]
    OUT["files.toArchive<br/>MessageChannel"]
    EP2["Outbound endpoint<br/>Service activator"]
    MH["MessageHandler bean<br/>FileWritingMessageHandler"]
    DST[("Target directory")]
    SRC --> MS
    EP1 -->|"receive()"| MS
    MS -->|"Message<File>"| EP1
    EP1 --> IN --> FLOW --> OUT --> EP2 --> MH --> DST
~~~

| Component | What Is It? | How Is It Registered? |
| --- | --- | --- |
| `FileReadingMessageSource` | A bean that knows how to locate files and return `Message<File>` on `receive()`. | `@Bean` or XML `<bean>`. |
| Inbound polling endpoint | Component calling the source on a schedule and sending messages to a channel. | `@InboundChannelAdapter`, Java DSL `IntegrationFlow.from(source, ...)`, or XML. |
| `MessageChannel` | Message handoff path; can be synchronous or asynchronous. | `@Bean DirectChannel`, DSL channel, or XML. |
| `IntegrationFlow` | Pipeline transforming, filtering, and routing messages between endpoints. | `@Bean` method returning `IntegrationFlow`. |
| `FileWritingMessageHandler` | Bean that knows how to write data to the filesystem. | `@Bean`. |
| Outbound consumer endpoint | Registers the handler to receive messages from the target channel. | `@ServiceActivator`, Java DSL `.handle(handler)`, or XML. |

In Spring, a **bean** is a container-managed object with dependency injection, configuration, and type-driven lifecycle. In Spring Integration, an **endpoint** is an active component at a messaging boundary: it receives or emits messages through channels, sometimes managing its own thread, poller, or listener.

These two concepts are related but not identical:

- Only `@Bean MessageSource<File>`: the source exists, yet **no scheduler automatically calls `receive()`**.
- Only `@Bean MessageHandler`: the handler exists, yet **it does not automatically subscribe to any channel**.
- Source bean **plus** annotation/DSL creating an inbound endpoint: the poller begins reading from the source when the endpoint starts.
- Handler bean **plus** channel-receiving endpoint: messages reach the handler when the consumer is active.

Separating them allows injecting the same beans for config inspection, unit testing their logic, substituting fakes in tests, and choosing a wiring style without coupling connection code to the entire flow.

## 3. Registration Patterns Supported by Spring Integration

There are two common organization styles:

**Approach A: endpoint annotation on the bean factory method.** The `@Bean` method returns the source or handler, while `@InboundChannelAdapter` or `@ServiceActivator` creates the corresponding endpoint. This is concise, and looking at the bean immediately shows the entry or exit channel.

~~~java
@Bean
@InboundChannelAdapter(
        value = "files.detected",
        poller = @Poller(fixedDelay = "5000"))
MessageSource<File> csvFileSource() {
    return createFileSource();
}

@Bean
@ServiceActivator(inputChannel = "files.toArchive")
MessageHandler archiveHandler() {
    return createFileWriter();
}
~~~

`createFileSource()` and `createFileWriter()` are illustrative helper methods; section 4 implements a complete runnable example.

**Approach B: pure beans + Java DSL wiring afterward.** Source and handler beans contain no endpoint metadata. `IntegrationFlow` injects those beans and creates the polling endpoint and consumer.

~~~java
@Bean
MessageSource<File> csvFileSource() {
    return createFileSource();
}

@Bean
MessageHandler archiveHandler() {
    return createFileWriter();
}

@Bean
IntegrationFlow csvFlow(MessageSource<File> csvFileSource,
                        MessageHandler archiveHandler) {
    return IntegrationFlow
            .from(csvFileSource,
                    endpoint -> endpoint.poller(
                            Pollers.fixedDelay(Duration.ofSeconds(5))))
            .handle(archiveHandler)
            .get();
}
~~~

The snippets above are **mutually exclusive alternatives**. If the same source is triggered by `@InboundChannelAdapter` and also passed to `IntegrationFlow.from(source, poller)`, two pollers can race to read data. If the same handler is registered twice, the application may send duplicates or dispatch messages unexpectedly.

Defining standalone beans is a code organization choice; **it never means creating two endpoints for the same adapter**.

## 4. Complete Example: Registering Inbound and Outbound Adapters as Separate Beans

Let's build an application that scans `.csv` files in `./inbox`, skips empty files, and copies the remaining files to `./archive`.

The architecture has three parts:

1. A `FileReadingMessageSource` bean that finds files in a directory.
2. A `FileWritingMessageHandler` bean that writes files to the destination directory.
3. `@InboundChannelAdapter` and `@ServiceActivator` annotations connecting both beans to channels, with an `IntegrationFlow` in between performing validation.

The code below uses Java 17+, Spring Boot, and a compatible Spring Integration version. This example illustrates beans and endpoints; **it does not yet implement durable deduplication or transactional guarantees between source and destination**.

### 4.1. Dependencies

In Maven, rely on Spring Boot's dependency management:

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

`spring-boot-starter-integration` provides Spring Integration core; `spring-integration-file` provides `FileReadingMessageSource` and `FileWritingMessageHandler`. Explicit versions are unnecessary when managed by the BOM.

### 4.2. Application Code

Create `AdapterBeansApplication.java` in package `demo.adapterbeans`:

~~~java
package demo.adapterbeans;

import java.io.File;
import java.nio.file.Files;
import java.time.Duration;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.InboundChannelAdapter;
import org.springframework.integration.annotation.Poller;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.core.MessageSource;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.file.FileReadingMessageSource;
import org.springframework.integration.file.FileWritingMessageHandler;
import org.springframework.integration.file.filters.AcceptOnceFileListFilter;
import org.springframework.integration.file.filters.CompositeFileListFilter;
import org.springframework.integration.file.filters.SimplePatternFileListFilter;
import org.springframework.integration.file.support.FileExistsMode;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHandler;

@SpringBootApplication
@EnableIntegration
public class AdapterBeansApplication {

    public static void main(String[] args) {
        SpringApplication.run(AdapterBeansApplication.class, args);
    }
}

@Configuration
class AdapterBeansConfiguration {

    @Bean(name = "files.detected")
    MessageChannel filesDetected() {
        return new DirectChannel();
    }

    @Bean(name = "files.toArchive")
    MessageChannel filesToArchive() {
        return new DirectChannel();
    }

    // Inbound source as an independent bean.
    @Bean
    @InboundChannelAdapter(
            value = "files.detected",
            poller = @Poller(
                    fixedDelay = "5000",
                    maxMessagesPerPoll = "3"))
    MessageSource<File> csvFileSource(
            @Value("${app.inbox:./inbox}") String inbox) {

        File directory = new File(inbox);
        if (!directory.isDirectory() && !directory.mkdirs()) {
            throw new IllegalStateException(
                    "Failed to create directory: " + directory);
        }

        var source = new FileReadingMessageSource();
        source.setDirectory(directory);

        var filters = new CompositeFileListFilter<File>();
        filters.addFilter(new SimplePatternFileListFilter("*.csv"));
        filters.addFilter(new AcceptOnceFileListFilter<>());
        source.setFilter(filters);

        return source;
    }

    // Transform/filter flow decoupled from file read/write details.
    @Bean
    IntegrationFlow csvValidationFlow() {
        return IntegrationFlow.from("files.detected")
                .filter(File.class,
                        file -> file.isFile() && file.length() > 0)
                .channel("files.toArchive")
                .get();
    }

    // Outbound writer is also an independent bean.
    @Bean
    @ServiceActivator(inputChannel = "files.toArchive")
    MessageHandler archiveWriter(
            @Value("${app.archive:./archive}") String archive) {

        File directory = new File(archive);
        if (!directory.isDirectory() && !directory.mkdirs()) {
            throw new IllegalStateException(
                    "Failed to create directory: " + directory);
        }

        var writer = new FileWritingMessageHandler(directory);
        writer.setFileExistsMode(FileExistsMode.REPLACE);
        writer.setExpectReply(false);
        return writer;
    }
}
~~~

How this configuration works:

- `filesDetected()` and `filesToArchive()` create two explicitly named channel beans. `DirectChannel` typically invokes the subscriber directly on the sender's thread.
- `csvFileSource(...)` returns a `MessageSource<File>` bean. `@InboundChannelAdapter` registers a **polling** endpoint to invoke `receive()` and emit messages to `files.detected`.
- `SimplePatternFileListFilter("*.csv")` selects files by name. `AcceptOnceFileListFilter` helps avoid re-emitting the same file within the filter's in-memory lifetime; it does not provide persistent checkpoints across restarts.
- `csvValidationFlow()` receives `Message<File>`, filters out empty files, and forwards valid messages to `files.toArchive`.
- `archiveWriter(...)` creates a `MessageHandler` bean capable of writing files. `@ServiceActivator` registers it as a consumer on `files.toArchive`.
- `FileExistsMode.REPLACE` is an illustrative option when the target filename already exists. Production systems must decide whether overwriting is allowed or whether to generate unique names or route to review.
- `setExpectReply(false)` marks file writing as a **one-way outbound** operation: the handler does not need to emit a reply message back into the flow.

In the `@Value`-injected factory methods, Spring pulls paths from application properties, defaulting to `./inbox` and `./archive`. Directories are created during bean initialization so the demo starts easily.

To customize paths:

~~~properties
app.inbox=./runtime/inbox
app.archive=./runtime/archive
~~~

This file can be `application.properties` in `src/main/resources` or an equivalent Spring Boot configuration source. In real systems, control filesystem permissions, disk capacity, and storage partitions for these paths.

### 4.3. How Do Messages Travel Across the Beans?

~~~mermaid
sequenceDiagram
    participant P as Poller endpoint
    participant S as csvFileSource bean
    participant C as files.detected
    participant F as csvValidationFlow
    participant O as files.toArchive
    participant H as archiveWriter bean
    P->>S: receive()
    S-->>P: Message<File> or null
    P->>C: send(Message<File>)
    C->>F: filter valid file
    F->>O: send(Message<File>)
    O->>H: handleMessage(message)
    H-->>H: Copy file into archive
~~~

Common misconception: Spring does not re-invoke the Java method `csvFileSource()` every 5 seconds. That method runs once when creating the bean; the endpoint periodically calls `receive()` on the created **`MessageSource` object**.

Likewise, Spring does not instantiate a new `FileWritingMessageHandler` for every file. The handler bean is reused across the container's lifecycle. If a client or handler holds a session or connection pool, creating it once allows centralized resource and configuration management.

## 5. Variant: Registering Adapters with Pure @Bean and Wiring via Java DSL

Many projects prefer placing adapter beans in a dedicated configuration class while keeping all channel and poller wiring inside `IntegrationFlow`. In that style, omit both endpoint annotations from the factory methods so the source and handler remain pure beans.

The following example is an **alternative configuration** for the corresponding beans in section 4—do not register both concurrently on the same source/destination.

~~~java
@Configuration
class SeparateAdapterConfiguration {

    @Bean
    MessageSource<File> independentFileSource() {
        var source = new FileReadingMessageSource();
        source.setDirectory(new File("./inbox"));
        source.setFilter(new SimplePatternFileListFilter("*.csv"));
        return source;
    }

    @Bean
    MessageHandler independentFileWriter() {
        var writer = new FileWritingMessageHandler(
                new File("./archive"));
        writer.setExpectReply(false);
        return writer;
    }

    @Bean
    IntegrationFlow fileCopyFlow(
            MessageSource<File> independentFileSource,
            MessageHandler independentFileWriter) {

        return IntegrationFlow
                .from(independentFileSource,
                        endpoint -> endpoint.poller(
                                Pollers.fixedDelay(
                                        Duration.ofSeconds(5))))
                .filter(File.class,
                        file -> file.isFile() && file.length() > 0)
                .handle(independentFileWriter)
                .get();
    }
}
~~~

Required imports include `@Configuration`, `@Bean`, `MessageSource`, `MessageHandler`, `IntegrationFlow`, `Pollers`, `Duration`, `File`, `FileReadingMessageSource`, `FileWritingMessageHandler`, and `SimplePatternFileListFilter`.

In this variant:

1. `independentFileSource()` creates the source bean.
2. `independentFileWriter()` creates the destination handler bean.
3. `fileCopyFlow(...)` receives **Spring-injected beans** as method parameters rather than calling `@Bean` methods directly to obtain new objects.
4. `IntegrationFlow.from(source, endpoint -> endpoint.poller(...))` builds the inbound polling endpoint using the source bean.
5. `.handle(handler)` builds the consumer endpoint using the handler bean.

**Note for this demo:** using `SimplePatternFileListFilter` alone filters only by name and provides no *accept-once* behavior. To avoid re-emitting files on subsequent polls, add `AcceptOnceFileListFilter` or an appropriate persistent state/filter mechanism. Also ensure source/destination directories exist before running as before.

Both approaches fulfill **the same responsibilities**:

| Purpose | Annotation + Bean | Pure Bean + Java DSL |
| --- | --- | --- |
| Create source | `@Bean MessageSource<File>` | `@Bean MessageSource<File>` |
| Schedule polling | `@InboundChannelAdapter(... @Poller)` | `IntegrationFlow.from(source, poller)` |
| Declare channel | `@Bean MessageChannel` | `@Bean` or DSL `.channel(...)` |
| Create handler | `@Bean MessageHandler` | `@Bean MessageHandler` |
| Bind handler to channel | `@ServiceActivator(inputChannel=...)` | `.handle(handler)` |
| Manage processing logic | Separate bean / `IntegrationFlow` | `IntegrationFlow` using injected beans |

The choice depends on project conventions. When many adapters share client configs, pure beans separate connection objects from topology cleanly. For a single small endpoint, annotations show the adapter's channel right on the bean.

## 6. Standalone Bean Registration Does Not Mean Sharing One Adapter Across All Flows

An adapter often holds **state or resources**: a seen-files filter, SFTP session, connection factory, Kafka producer, or rate limiter. Reusing the same instance across multiple flows can introduce contention or duplicate side effects.

For instance, a `FileReadingMessageSource` maintains filter state and file ordering. Attaching **two pollers** to the same source object looks like:

~~~mermaid
flowchart TD
    S["One FileReadingMessageSource bean"]
    P1["Poller of flow A"]
    P2["Poller of flow B"]
    C1["Channel A"]
    C2["Channel B"]
    P1 --> S
    P2 --> S
    P1 --> C1
    P2 --> C2
~~~

Both pollers can invoke `receive()` at different times and compete for files. Even if the source uses internal locking, you have not explicitly designed which file belongs to which flow. Never treat this as a fan-out mechanism.

When you need **one read with multiple consumers**, use a single inbound endpoint followed by a **`PublishSubscribeChannel`** or deliberate routing to distribute messages. When you need two independent pipelines, give each its own source/filter/state or clear partitioning.

For outbound handlers, if the same `MessageHandler` is wired from multiple channels, verify whether it is thread-safe, avoids per-request mutable state, and whether concurrent calls are supported by the target system. Singleton bean scope manages instance count—it does not automatically guarantee thread safety.

## 7. Bean Naming, Injection, and Avoiding Duplicate Registration

### 7.1. Clear Naming for Observability

Distinguish names for the **source bean**, **handler bean**, **channels**, and **endpoints**:

| Kind | Example | Rationale |
| --- | --- | --- |
| Source bean | `csvFileSource` | Encapsulates file-reading logic. |
| Inbound channel | `files.detected` | Producer sends detected files here. |
| Flow bean | `csvValidationFlow` | Defines validation and routing. |
| Outbound channel | `files.toArchive` | Final handoff point before writing files. |
| Handler bean | `archiveWriter` | Encapsulates file-writing logic. |
| Endpoint | Created by framework from annotation/DSL, with its own lifecycle. | Can be started/stopped and monitored via framework management. |

Do not register another bean named `files.detected` elsewhere once `@Bean(name = "files.detected")` is defined. When component scanning and importing configurations across modules, check for colliding IDs or unintended multiple consumers.

### 7.2. Injecting by Type or @Qualifier

If multiple `MessageSource<File>` beans exist, type-based injection becomes ambiguous. Use `@Qualifier`:

~~~java
@Bean
IntegrationFlow inboundFlow(
        @Qualifier("csvFileSource")
        MessageSource<File> source) {
    return IntegrationFlow.from(
                    source,
                    endpoint -> endpoint.poller(
                            Pollers.fixedDelay(Duration.ofSeconds(10))))
            .channel("files.detected")
            .get();
}
~~~

This snippet applies only to the **pure bean** approach. If `csvFileSource` already carries `@InboundChannelAdapter` as in section 4, do not add this flow, or you will create a second polling endpoint.

Similarly, handlers for HTTP, JMS, Kafka, or files may all implement `MessageHandler`. When wiring them into the DSL, inject by bean name or qualifier to avoid picking the wrong destination.

### 7.3. Never Call @Bean Factory Methods Manually Like Services

Inside `@Configuration` classes, `@Bean` methods may be proxied by Spring to return singleton beans depending on configuration mode. Calling `csvFileSource()` directly from business code or instantiating configuration classes with `new` makes behavior fragile and config-dependent.

With standalone adapters, consistently **let Spring inject the beans** into flows or tests. That preserves lifecycle management and prevents accidentally creating extra instances sharing the same directory, connections, or state.

## 8. Message Contracts at Adapter Boundaries

Whether registered as standalone beans or inline in DSL, adapters must publish clear **payload types and headers** for downstream consumers.

| Element | Example | Control |
| --- | --- | --- |
| Payload | `File`, `byte[]`, business DTO, `String`. | Downstream transformers/handlers must accept the exact type. |
| Correlation ID | `traceId` or `correlationId`. | Preserved across steps to trace requests and failures. |
| Event identifier | `eventId`, `orderId`, or file checksum. | Idempotency when sources redeliver. |
| Protocol headers | Filename, remote directory, topic/partition. | Do not assume all headers cross external boundaries intact. |
| Reply / error | `replyChannel`, `errorChannel`. | Gateway reply path and endpoint error path. |
| Processing outcome | Target ack, business response code. | Distinguishes message receipt from task completion. |

For example, `FileReadingMessageSource` emits `Message<File>`; it has not parsed CSV rows or verified row validity. If the target handler expects `OrderCommand`, insert read/parse/validate/transform steps between the source adapter and destination adapter.

`replyChannel` and `errorChannel` headers may reference internal channel objects. When sending over HTTP, JMS, AMQP, or Kafka, map only safe, useful, protocol-compatible headers. Never dump all `MessageHeaders` onto the wire blindly.

### 8.1. Standalone Beans and Other Protocol Adapters

The same separation applies to other protocols:

- **SFTP:** create a `SessionFactory` bean holding connection/auth config; create sources or message handlers backed by that bean; attach endpoints via DSL or XML.
- **HTTP:** reuse client beans configured with timeouts, converters, auth, and connection pools; outbound message handlers/gateways execute the HTTP calls.
- **JMS/AMQP:** declare `ConnectionFactory`/template/listener infrastructure as beans; endpoints manage acks, transactions, and listener containers.
- **Kafka:** share producer/consumer factory beans, message handlers, or adapters; watch offsets, topics, partitions, serialization, and commits.
- **Database:** use `DataSource`, transaction managers, and JDBC message sources/handlers; queries require checkpoints and multi-instance distribution strategies.

Not every connector is a `MessageSource`. Message-driven inbound endpoints often rely on listener containers or callbacks instead of pollers. Registering them as beans still helps reuse configuration, while activation mechanics depend on the protocol.

## 9. Errors, Retries, and Integrity When Sources and Sinks Are Separate Beans

A flow can have valid beans and endpoints yet still lose data if error handling is underspecified.

~~~mermaid
flowchart TD
    R["Source receives file / event"]
    S["MessageSource / listener"]
    C["Sent to channel"]
    H["Outbound handler"]
    A{"Target system confirms?"}
    OK["Mark success"]
    ERR["Error and recovery policy"]
    R --> S --> C --> H --> A
    A -->|"Yes"| OK
    A -->|"No / uncertain"| ERR
~~~

Distinguish three milestones:

1. **Source emitted message:** data entered Spring Integration.
2. **Handler sent/wrote data:** the outbound action ran at some layer.
3. **Target completed business processing:** the external system confirmed per contract.

For example, a source using `AcceptOnceFileListFilter` may already record a file as seen before the handler fails to write to the archive folder. Without replay or persistent tracking, merely waiting for the next poll cycle will not recover it. Conversely, if a handler succeeded over HTTP but the response was lost, retrying can trigger side effects twice.

Tailor error handling per source and sink:

- **Source errors:** alert, reconnect, backoff, and define poll continuation criteria.
- **Validation errors:** send malformed payloads to quarantine with clear codes and reasons.
- **Outbound delivery errors:** bounded retries, timeouts, and circuit breakers where appropriate.
- **Uncertain outcomes:** reconcile using business IDs or destination idempotency keys.
- **Restarts or multiple instances:** checkpoints, locks/partitions, persistent state, and unique constraints as needed.

**Being a singleton handler bean does not make delivery exactly-once.** Reliability depends on the combined behavior of source, channel, endpoint, transaction, and target system.

### 9.1. Synchronous and Asynchronous Errors

With `DirectChannel`, handlers typically run on the sending thread. Exceptions from `FileWritingMessageHandler` can propagate back to the polling inbound endpoint. The poller/error infrastructure may handle the exception, but do not assume the file will automatically be re-sent.

If `files.toArchive` is replaced with a `QueueChannel` or `ExecutorChannel`, the handler may run on a different thread. That requires an appropriate poller or executor consumer plus error routing such as `errorChannel`, `ErrorMessage`, retry advice, or a dead-letter store. In-memory queues do not survive restarts.

## 10. Bean Lifecycles and Connection Management

Adapters and resource beans live in the Spring context. Components implementing Spring lifecycle interfaces start and stop with the container. Polling endpoints, listener containers, and connection/session pools have their own lifecycles—they are not identical to raw `MessageSource` or `MessageHandler` objects.

Operational scenarios to plan for:

| Event | What to Check? |
| --- | --- |
| Application startup | Are source/handler beans initialized? Do endpoints have consumers? Are directories and credentials valid? |
| Poller start | Poll frequency, `maxMessagesPerPoll`, thread bounds, and processing speed. |
| Slow destination | Client timeouts, backpressure, queue capacity, and retries. |
| SFTP/JMS/DB disconnect | Session reconnects, listener recovery, and unacknowledged message state. |
| Graceful shutdown | Stop accepting new inputs, drain in-flight work, close connections, flush checkpoints. |
| Multiple instances | Could two instances poll the same file/record? Are locks, partitions, or claims in place? |

Standalone beans make it convenient to inject externalized resources such as `DataSource`, client credentials, serializers, retry policies, and metric registries. Keep connection management inside client/session factory beans, while flows focus on **message routing and business rules**.

### 10.1. Avoid Creating Multiple Unintended Schedulers for One Source

If a source is declared with `@Bean + @InboundChannelAdapter`, do not also add an `@Scheduled` task calling `source.receive()` or a second `IntegrationFlow.from(source, poller)` without explicit design. Doing so creates two competing pull loops, causing contention, duplicate reads, or skipped items.

Similarly, when using Spring Integration with JMS or Kafka listeners, avoid creating extra standalone listeners reading the same destination when you only intend one logical consumer.

## 11. Testing Standalone Beans and Endpoint Wiring

Test at two levels:

1. **Bean unit tests:** configure the source or handler and verify how it reads/writes when invoked directly.
2. **Endpoint integration tests:** boot the Spring context, send messages to real channels or place data at the source, and observe outputs after polling.

The second level is essential to catch missing `@InboundChannelAdapter` annotations, mismatched channel names, or handlers never wired to a consumer—issues that direct handler unit tests miss.

### 11.1. Testing Flow and Outbound Handler Through a Channel

In section 4's example, use `files.detected` as the test entry point: the file passes through the validation flow and reaches the file-writing bean, testing the **consumer endpoint** without waiting for the poller.

Place `AdapterBeansApplicationTest.java` in package `demo.adapterbeans`:

~~~java
package demo.adapterbeans;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

@SpringBootTest(properties = {
        "app.inbox=./target/adapter-beans-inbox",
        "app.archive=./target/adapter-beans-archive"
})
class AdapterBeansApplicationTest {

    @Autowired
    @Qualifier("files.detected")
    MessageChannel detectedFiles;

    @Test
    void validFileGoesThroughFlowAndIndependentWriter() throws Exception {
        Path input = Files.createTempFile("adapter-bean-", ".csv");
        Path exported = Path.of("./target/adapter-beans-archive")
                .resolve(input.getFileName());

        byte[] data = "orderId,amount\nORD-1001,250000\n"
                .getBytes(StandardCharsets.UTF_8);
        try {
            Files.write(input, data);

            boolean accepted = detectedFiles.send(
                    MessageBuilder.withPayload(input.toFile()).build());

            assertTrue(accepted);
            assertTrue(Files.isRegularFile(exported));
            assertArrayEquals(data, Files.readAllBytes(exported));
        } finally {
            Files.deleteIfExists(input);
            Files.deleteIfExists(exported);
        }
    }
}
~~~

The project needs `spring-boot-starter-test` in test scope. Here the test writes a temp file outside `app.inbox` to prove the flow and outbound endpoint are wired properly. The source bean from section 4 still initializes when the Spring context boots, though it does not need to emit files during this test. With `DirectChannel`, the handler runs synchronously so assertions can inspect the file right after `send()`.

**Limitation:** this test **does not verify inbound polling**, because it sends directly to the channel. To test the inbound source, drop files into a dedicated test inbox, wait with a bounded timeout condition, and test empty files, non-matching patterns, and restarts.

### 11.2. Testing Standalone Beans to Verify Configuration

You can inject the source bean and invoke `receive()` in a dedicated unit or integration test. If a live poller is concurrently driving that source, do not call `receive()` directly on the same bean in a test or you will compete for items. Either construct an isolated source with a temp directory or stop the endpoint when testing state.

For outbound handlers, test target paths, filenames, file-exists policies, write permissions, and error paths. When moving to SFTP, JMS, HTTP, or Kafka, add tests for timeouts, reconnects, acks/offsets, duplicates, and restarts.

## 12. Comparison with XML Namespaces and Service-Method Annotations

The same design can be expressed in several ways without changing the message contract.

| Style | Where Is the Adapter Bean? | Where Is the Endpoint? |
| --- | --- | --- |
| `@Bean + @InboundChannelAdapter` | `@Bean` method returning `MessageSource`. | Annotation creates the polling endpoint. |
| `@Bean + @ServiceActivator` | `@Bean` method returning `MessageHandler`. | Annotation creates the consumer endpoint. |
| `@Bean` + Java DSL | Source/handler beans created separately. | `IntegrationFlow.from(...)` and `.handle(...)` create endpoints. |
| XML namespace | Source, handler, and clients can be declared with `<bean>`. | `<int:...>` or adapter namespace tags wire endpoints and channels. |
| `@Component` + `@ServiceActivator` method | Bean is a Java service. | Method annotation creates the handler endpoint. |

When migrating from XML to Java DSL, keep payload types, channel names, header contracts, retries, and success semantics consistent. Never import XML and add new DSL definitions for **the same endpoint** before deciding how to cut over, or the application may create duplicate consumers or pollers.

When registering adapters as standalone beans, prefer **constructor injection**, centralized configuration, and clearly bounded tests. Specialized adapters handle protocol details; flows express data pipelines and business policies.

## 13. Common Design Pitfalls

| Symptom | Cause | Fix |
| --- | --- | --- |
| Created `MessageSource` bean, yet no messages arrive. | No polling endpoint uses that bean. | Add `@InboundChannelAdapter` or `IntegrationFlow.from(source, poller)`. |
| Created `MessageHandler`, yet nothing goes outbound. | No consumer endpoint binds the handler to a channel. | Use `@ServiceActivator(inputChannel=...)` or DSL `.handle(handler)`. |
| Same file read twice by two flows. | Multiple pollers on one source or two adapters scanning one folder. | Use one inbound endpoint then route/fan-out, or partition sources cleanly. |
| Messages never reach the handler. | Wrong channel name, stopped endpoint, or no subscriber. | Match channel IDs and lifecycles; verify wiring via integration tests. |
| Two handlers on one `DirectChannel`, yet only one runs. | `DirectChannel` is point-to-point, not multicast. | Use publish–subscribe when broadcasting to multiple consumers. |
| Spring cannot decide which handler to inject. | Multiple beans of type `MessageHandler`. | Use `@Qualifier` or explicit named injection. |
| Multiple client objects connect to the same target. | Created via `new` outside container or duplicated config. | Use Spring-managed beans and dependency injection. |
| Poller keeps running, yet failed messages are not retried. | Source already marked them read; no replay/checkpoint exists. | Design source state tracking and retries at the right layer. |
| App loses messages after restart. | Queue and filter live only in RAM. | Persistent stores, idempotency, and proper acks/transactions. |
| Gateway times out even though outbound completed. | Reply lost or one-way handler returned nothing. | Separate one-way vs. request–reply and fix the reply path. |
| Duplicate writes in external system. | Retries after uncertain outcomes without idempotent keys. | Use idempotency keys/unique constraints and reconciliation. |
| Direct handler test passes, yet flow does not run. | Never tested Spring context wiring and real channels. | Add integration tests through endpoints and channels. |

## 14. Exercise: Separating SFTP and Database Adapters into Standalone Beans

Suppose a system receives CSV files via SFTP, normalizes each row into an `Invoice`, and persists them to a database. Design it as follows:

1. A bean managing the SFTP connection/session factory configured with endpoint, host-key security, timeouts, and reconnects.
2. A bean syncing/reading files from SFTP, attached to **one inbound endpoint** with a poller.
3. Channel `invoices.raw` receiving source files or messages; transformation and validation produce `Invoice` objects.
4. A database writer bean using `DataSource` and a transaction manager; a consumer endpoint receives `Invoice` from `invoices.valid`.
5. Unparseable files move to quarantine rather than being retried endlessly.
6. For database retries, use an idempotency key on the invoice ID so writing twice never creates two rows.
7. Two-instance deployment: propose a lock/partition or record-claiming mechanism so both instances never process the same file.
8. Write tests showing that without an endpoint, the bean exists without running the flow, then verify proper execution once the endpoint is registered.

**Pass criteria:** learners clearly identify which bean holds connections, which reads/writes, which endpoint triggers execution, which channels carry messages, where transactions begin and commit, and where replay starts on failure.

## 15. Self-Check Questions

1. Why doesn't `@Bean MessageSource<File>` scan directories automatically?
2. When are the `@Bean` factory method and `MessageSource.receive()` each invoked?
3. What does `@ServiceActivator` do when placed on a `MessageHandler` bean?
4. Why inject an adapter bean into the Java DSL instead of calling `new`?
5. Can you use both `@InboundChannelAdapter` and `IntegrationFlow.from(source, poller)` on the same source? What is the risk?
6. If a message must reach two handlers, does `DirectChannel` provide multicast?
7. Does a filter storing seen files in memory prevent duplicates after restart?
8. Does singleton bean scope guarantee a handler is thread-safe across concurrent threads?
9. What does a successful `MessageChannel.send()` prove, and what does it not prove?
10. Why is a unit test calling a handler directly insufficient to confirm an integration flow is wired?

**Hints:** a bean is a Spring-managed object, whereas an endpoint creates the message-receiving or sending mechanism. Sources need pollers or listeners; handlers need channel subscribers. Reliability requires durable state, retries, idempotency, and destination acknowledgements.

## 16. Key Takeaways

**Registering adapters as standalone beans** separates data-reading/writing components from message pipeline configuration. In Spring Integration, keep the roles distinct: **`MessageSource` or `MessageHandler` is the functional bean; inbound/outbound endpoints connect them to pollers/channels; `IntegrationFlow` expresses the processing steps**.

This model applies across files, SFTP, HTTP, JMS, AMQP, Kafka, and databases even though each protocol creates clients, listeners, or acks differently. When designing, prefer Spring-managed beans, consistent channel names, one trigger path per responsibility, explicit payload/header contracts, and tests covering both wiring and failure modes. That is the foundation for multi-system integrations that operate and recover reliably.
