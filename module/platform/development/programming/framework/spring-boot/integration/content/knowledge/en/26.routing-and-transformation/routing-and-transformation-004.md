# Splitter and Dividing One Message into Multiple Processing Units

## Goals and Context

In the **SPRING_BOOT_INTEGRATION** module, Spring Boot connects HTTP clients, databases, caches, message brokers, and Spring Integration adapters to build production-ready integration flows. An order containing 100 line items, a CSV file with 10,000 records, or a batch of events read from a database often enters the application as **a single message**. Yet each line/record may need independent validation, transformation, routing, state persistence, or downstream delivery.

**Splitter** implements the **Message Splitter** pattern in Enterprise Integration Patterns (EIP): it takes an input message, breaks its payload into parts, and emits **multiple output messages**, each representing one unit of work.

This lesson belongs to the **Routing and Transformation** chapter and focuses on **Splitter and dividing one message into multiple processing units** in Spring Integration. It connects Java DSL, annotations, and custom splitters with real-world concerns: data contracts, message headers, transactions, concurrency, errors, retries/idempotency, aggregation, testing, and observability.

After this lesson, you will be able to:

1. Distinguish Splitter from Transformer, Filter, Router, Publish-Subscribe, and Aggregator.
2. Use `IntegrationFlow.split()` or `@Splitter` to split collections into child messages.
3. Understand `payload`, headers, `correlationId`, `sequenceNumber`, and `sequenceSize`.
4. Choose sequential, asynchronous, or parallel output processing without losing load control.
5. Know when to use Aggregator/Resequencer and why filtering or partial errors can stall a group indefinitely.
6. Build flows that split batches and process SQL/HTTP/broker targets with stable idempotency keys.
7. Design tests, dead-letter handling, checkpoints, and metrics at both batch and item levels.

> **Principle:** A Splitter changes the **unit of message transport and processing**; it does not automatically wrap all child messages in one transaction, guarantee ordering under concurrency, or turn each item into exactly-once execution.

## 1. One Input Message Becomes Multiple Output Messages

Suppose the system receives an inventory update batch:

~~~json
{
  "batchId": "B-2026-001",
  "lines": [
    {"lineId": "L-1", "sku": "P-100", "quantity": 4},
    {"lineId": "L-2", "sku": "P-200", "quantity": 2},
    {"lineId": "L-3", "sku": "P-300", "quantity": 6}
  ]
}
~~~

A Splitter can turn a `Message<List<InventoryLine>>` into three messages:

~~~text
Message<List<InventoryLine>>
    |
    +--> Message<InventoryLine(L-1)> --> Validate --> Apply
    |
    +--> Message<InventoryLine(L-2)> --> Validate --> Apply
    |
    +--> Message<InventoryLine(L-3)> --> Validate --> Apply
~~~

If the batch has 3 items, the output count is typically 3; if the list is empty, the splitter may emit zero messages. Exact behavior depends on the implementation and configuration. Never assume an empty batch automatically emits a special "completed" marker message; if the domain needs that signal, design it explicitly.

### 1.1. EIP Model

~~~mermaid
flowchart LR
    A["Message<Batch>"] --> B["Splitter"]
    B --> C["Message<Item 1>"]
    B --> D["Message<Item 2>"]
    B --> E["Message<Item N>"]
    C --> F["Handler / Transformer"]
    D --> F
    E --> F
    F --> G["SQL, HTTP, cache, broker"]
~~~

A Splitter **does not inherently run in parallel**. With `DirectChannel`, handlers execute on the sender's thread; outputs may be processed sequentially as the splitter emits each message. To truly run asynchronously, configure appropriate channels/executors or a queueing system.

### 1.2. How Splitter Differs from Similar EIPs

| Component | Input → Output | Use when |
| --- | --- | --- |
| **Splitter** | One message containing a collection → many child messages | Processing each line of a batch |
| **Transformer** | One message → one message with transformed payload | JSON → DTO, DTO → another format |
| **Filter** | One message → pass or drop | Dropping ineligible records |
| **Router** | One message → choose destination by condition | Picking queue by region/status |
| **Publish-Subscribe Channel** | Same message → multiple subscribers | Fan-out to independent functions |
| **Recipient List Router** | One message → copies to selected endpoints by rule | Sending the same event to multiple departments |
| **Aggregator** | Multiple correlated messages → one grouped result | Combining item results back into a batch |
| **Resequencer** | Multiple sequenced messages → reordered sequence | Ensuring ordered processing/output when needed |

For example, passing `List<Item>` through **publish-subscribe** keeps the entire list inside each copy sent to subscribers. Passing it through a **splitter** gives each output message a payload of **one Item** (or another split unit). These two fan-out mechanisms are not equivalent.

## 2. Related Spring Integration Concepts

Spring Integration builds on Spring Messaging:

- `Message<T>`: carries a `payload` of type `T` and `headers`.
- `MessageChannel`: transports messages.
- `MessageHandler`: consumer processing messages.
- `MessageProducer` and inbound adapters: bring messages from HTTP, files, brokers, databases...
- **Splitter endpoint**: receives one message and produces one or more output messages.
- `IntegrationFlow`: defines processing chains via Java DSL.
- `@Splitter`: annotation marking a payload-splitting method.

Key implementations:

| API/Class | Role |
| --- | --- |
| `IntegrationFlow.split()` | Java DSL splitting payloads using default rules |
| `DefaultMessageSplitter` | Standard splitter for supported collection-like payloads |
| `AbstractMessageSplitter` | Base class for custom splitters |
| `@Splitter` | Annotation-based splitter method registration |
| `@ServiceActivator` | Handler processing each child message |
| `MessageGroupStore` | Stores message groups for Aggregator/Resequencer when needed |
| `IntegrationMessageHeaderAccessor` | Constants for correlation/sequence headers |
| `MessageBuilder` | Constructs messages and sets headers from gateways or adapters |

### 2.1. Do Not Confuse Business Payload with the Message Envelope

A `Message<List<InventoryLine>>` has:

~~~text
payload = [L-1, L-2, L-3]

headers:
  id = UUID of current message
  timestamp = message creation time
  batchId = "B-2026-001"             (custom business context)
  source = "inventory-import"          (custom business context)
  ...
~~~

After splitting, each output message should carry:

- **Child payload**: `InventoryLine`.
- **Relevant headers**: e.g., `batchId`, `source`.
- **Sequence/correlation metadata** when sequencing is enabled to support aggregation.

Technical headers like `id` and `timestamp` follow Spring Messaging generation rules; do not assume all headers are copied verbatim. If a custom splitter builds its own `Message<?>` instances, carefully verify how headers are preserved or overwritten.

## 3. Setting Up Spring Integration in Spring Boot

In Gradle Groovy DSL, minimal example:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-integration'

    // When Micrometer/Actuator observability is needed:
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    // For tests:
    testImplementation 'org.springframework.integration:spring-integration-test'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Spring Boot auto-configures core Spring Integration when the appropriate dependency is present. Specific adapters require dedicated modules such as JDBC, HTTP, AMQP, or Kafka; **the integration starter does not automatically include every transport**.

To keep the lesson focused on Splitter, the examples below use a `DirectChannel` input and a service bean receiving each line. The exact same flow can be triggered by an HTTP controller, broker listener, JDBC poller, or Spring Integration adapter.

### 3.1. Batch Models

~~~java
// InventoryLine.java
public record InventoryLine(
        String lineId,
        String sku,
        int quantity) {
}
~~~

~~~java
// InventoryBatch.java
import java.util.List;

public record InventoryBatch(
        String batchId,
        List<InventoryLine> lines) {
}
~~~

These are Java 17+ models describing the data contract. In production, validate `batchId`, `lineId`, SKU, quantity, maximum item count, and null lists. A Splitter does not automatically enforce business validation.

## 4. Using Java DSL with Default split()

When the **input payload is already a collection**, the simplest approach is `split()`.

~~~java
// InventorySplitFlowConfiguration.java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration(proxyBeanMethods = false)
public class InventorySplitFlowConfiguration {

    @Bean
    MessageChannel inventoryBatchInput() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow inventoryLineFlow(
            MessageChannel inventoryBatchInput,
            InventoryLineProcessor processor) {

        return IntegrationFlow.from(inventoryBatchInput)
                .split()
                .handle(InventoryLine.class,
                        (line, headers) -> {
                            processor.process(line);
                            return null;
                        })
                .get();
    }
}
~~~

`InventoryLineProcessor` is a port processing a single line, e.g.:

~~~java
// InventoryLineProcessor.java
public interface InventoryLineProcessor {
    void process(InventoryLine line);
}
~~~

Each message carrying an `InventoryLine` is passed to the handler. Returning `null` from the handler here indicates a **one-way endpoint producing no reply payload**; that fits when no downstream aggregation is needed. To combine results with an Aggregator, the handler must emit a result instead of returning null.

### 4.1. Sending a Batch into the Input Channel

~~~java
import java.util.List;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

public class InventoryBatchPublisher {

    private final MessageChannel input;

    public InventoryBatchPublisher(
            MessageChannel inventoryBatchInput) {
        this.input = inventoryBatchInput;
    }

    public void publish(InventoryBatch batch) {
        boolean accepted = input.send(
                MessageBuilder.withPayload(batch.lines())
                        .setHeader("batchId", batch.batchId())
                        .build());

        if (!accepted) {
            throw new IllegalStateException(
                    "Failed to dispatch batch into IntegrationFlow");
        }
    }
}
~~~

`MessageBuilder.withPayload(...)` **rejects a null payload**; validate `batch.lines()` before sending. With a `DirectChannel`, `send(...)` normally invokes downstream **synchronously on the same thread**; if a handler fails, the exception may be thrown before `send` finishes.

This snippet builds a Spring message with a `List<InventoryLine>` payload and business header `batchId`—a payload type supported by default `split()`.

**Design note:** if you receive an `InventoryBatch` instead of `List<InventoryLine>`, do not expect `split()` to automatically look up a `lines` property on arbitrary domain records. Either **transform** the batch into a list before splitting, or use a custom splitter method as shown next.

### 4.2. Controlling Element Counts

A 2-item batch produces 2 messages, whereas a 100,000-item batch can generate massive load. Therefore:

- Enforce `maxItemsPerBatch` at ingress.
- Use paging/chunking when reading large databases or files.
- Do not materialize an enormous list if the source can be streamed.
- If using downstream queues/executors, choose bounded capacities and overload policies.
- Track both input item counts and items actually completed.

Do not assume splitting 100,000 items in Java DSL automatically provides **end-to-end backpressure** across all channel and transport types.

## 5. Using @Splitter When the Payload Is a Batch Object

If the input payload is `InventoryBatch`, declare a splitter method:

~~~java
// InventoryBatchSplitter.java
import java.util.List;
import org.springframework.integration.annotation.Splitter;
import org.springframework.stereotype.Component;

@Component
public class InventoryBatchSplitter {

    @Splitter(
            inputChannel = "inventoryBatchRequests",
            outputChannel = "inventoryLines")
    public List<InventoryLine> split(
            InventoryBatch batch) {

        if (batch.lines() == null) {
            throw new IllegalArgumentException(
                    "InventoryBatch.lines must not be null");
        }

        return List.copyOf(batch.lines());
    }
}
~~~

Once a publisher sends `InventoryBatch` into `inventoryBatchRequests` and downstream subscribes to `inventoryLines` per the flow definition, Spring Integration invokes the method and treats the returned `List<InventoryLine>` elements as splitter outputs.

**Clarification:** `@Splitter` is specific to Spring Integration. It is not `@GetMapping` or `@Async`; annotating a method does not create an HTTP endpoint or a new thread pool.

In a real application, keep source channel names consistent and do not accidentally register another DSL splitter on the same input causing batches to be processed twice.

### 5.1. Splitting by Business Rules

Suppose a batch contains 200 lines, but downstream accepts at most 50 lines per call. The splitter does not have to return individual lines; it can split into **chunks**:

~~~java
import java.util.ArrayList;
import java.util.List;

public List<List<InventoryLine>> splitChunks(
        InventoryBatch batch, int chunkSize) {

    if (chunkSize <= 0) {
        throw new IllegalArgumentException(
                "chunkSize must be > 0");
    }

    List<InventoryLine> lines = batch.lines();
    if (lines == null) {
        throw new IllegalArgumentException(
                "lines must not be null");
    }

    List<List<InventoryLine>> chunks =
            new ArrayList<>();

    for (int start = 0; start < lines.size();
            start += chunkSize) {

        int end = Math.min(
                start + chunkSize, lines.size());

        chunks.add(List.copyOf(
                lines.subList(start, end)));
    }

    return chunks;
}
~~~

When wired as a splitter, each output payload is a **`List<InventoryLine>` chunk**, not a single `InventoryLine`. This changes the downstream handler contract: you may need batch SQL inserts or an HTTP bulk API instead of a single-item endpoint.

Chunking is a decision about **unit-of-work granularity**, balancing timeouts, HTTP body limits, throughput, and transaction scope.

## 6. DefaultMessageSplitter and Custom Splitters

### 6.1. What Payloads Does the Default Splitter Handle?

`DefaultMessageSplitter` splits several supported collection-like payload types:

| Payload type | Typical output | Notes |
| --- | --- | --- |
| `List<Item>` / `Collection<Item>` | One message per item | Size known upfront |
| Java array | One message per element | Watch element type |
| `Map<K,V>` | Elements of type `Map.Entry` | Not automatically unwrapped to V |
| Iterator/Iterable/Stream when version supports | Iterated element by element | Size may be unknown upfront |
| Domain object `InventoryBatch` | **Does not automatically know `lines` property** | Use custom method |

Do not treat a provider returning a `Stream`/`Iterator` as equivalent to a sized collection. Streams are single-use, lazy, and tied to open resources. If an iterator wraps a JDBC `ResultSet` whose transaction closes before the splitter finishes consuming it, the flow may fail mid-way.

### 6.2. When to Subclass AbstractMessageSplitter?

A custom splitter is useful when you must:

- Parse a complex batch file format.
- Split payloads by business segmentation or nested JSON paths.
- Emit distinct `Message<?>` outputs carrying different business headers.
- Partition blocks by window, page, or maximum byte size.
- Validate payloads before starting fan-out.

Spring Integration provides `AbstractMessageSplitter` as a base class. For simpler cases, `@Splitter` methods or Java DSL are usually clearer and easier to test than a custom class.

If a custom splitter builds `Message<?>` instances per element, do not blindly copy `id`/`timestamp` or arbitrarily overwrite sequencing headers. Child message identity and correlation behavior must be tested against downstream endpoints.

### 6.3. A Splitter Is Not a JSON Parser

For HTTP inbound JSON:

~~~text
HTTP JSON → DTO/record → List<InventoryLine> → Splitter
~~~

Use HTTP message conversion/Jackson or an appropriate transformer to convert JSON into Java objects. A splitter does not replace JSON schema validation or type mapping. If a broker consumer receives `byte[]` JSON, do not pass `byte[]` into a splitter and accidentally emit one message per byte; decode and validate the payload first.

## 7. Correlation Headers and Sequence Metadata

When one input message splits into multiple child messages, an Aggregator needs to know **which messages belong to the same batch** and **when all have arrived**. Spring Integration uses common headers:

| Header | Meaning | Example |
| --- | --- | --- |
| `correlationId` | Identifies child group from the same source | Original request/split group ID |
| `sequenceNumber` | 1-based position of the child message | 1, 2, 3 |
| `sequenceSize` | Expected total elements in the sequence | 3 |
| `id` | Unique Spring message ID | UUID per output message |
| `timestamp` | Message creation time | Message timestamp |
| `batchId` (custom) | Stable business batch ID | B-2026-001 |
| `lineId` (custom) | Stable business line ID | L-1 |

Example output:

~~~text
Message<InventoryLine L-2>
  correlationId = 7b...          (split correlation)
  sequenceNumber = 2
  sequenceSize = 3
  batchId = B-2026-001
  id = different UUID from L-1 message
~~~

**Key distinctions:**

- Splitter's `correlationId` is technical metadata for grouping messages within a single split execution.
- `batchId` / `lineId` are business keys for tracing, reconciliation, and deduplication.
- If the same business batch is **re-split on retry/replay**, the technical correlation ID may change.
- `sequenceNumber` only indicates position within that split output, not a durable long-term idempotency key.
- `sequenceSize` helps when element count is known; for streaming/iterator sources of unknown size, never assume an exact total is always present.

### 7.1. Are Sequence Headers Applied Automatically?

`AbstractMessageSplitter` provides an **apply sequence** feature to attach correlation/sequence headers to outputs. Default policies and configuration details can vary across Spring Integration versions, endpoints, and split variants; when downstream depends on an Aggregator/Resequencer, **verify against your running version and configure explicitly**.

Conceptual splitter configuration:

~~~java
import org.springframework.integration.splitter.DefaultMessageSplitter;

DefaultMessageSplitter splitter =
        new DefaultMessageSplitter();

splitter.setApplySequence(true);
~~~

This snippet constructs a splitter; to use it in a pipeline, register it as an endpoint/bean via Java DSL or equivalent XML config. Enabling `applySequence` does not solve **groups waiting forever when elements fail or are filtered out**.

### 7.2. Do Not Break Headers During Transformation

A downstream transformer after a splitter may produce new outputs. When a transformer returns a new payload through a standard Spring Integration endpoint, the framework manages/copies headers appropriately. If code manually builds a new `Message<?>` setting only the payload, `correlationId` and sequence metadata may be lost.

When chaining `split → transform → aggregate`, test that transformer outputs **retain the headers needed by the aggregator**. Also avoid preserving stale headers across nested splits, which can merge two separate groups.

## 8. Combining Splitter → Handler/Transformer → Aggregator

A common pattern is splitting a batch, processing each item, and gathering results:

~~~mermaid
flowchart LR
    A["Message<List<OrderLine>>"] --> B["Splitter"]
    B --> C1["OrderLine 1"]
    B --> C2["OrderLine 2"]
    B --> C3["OrderLine 3"]
    C1 --> D["Pricing transformer"]
    C2 --> D
    C3 --> D
    D --> E["Aggregator"]
    E --> F["Message<List<PricedLine>>"]
~~~

Domain example:

~~~java
public record OrderLine(
        String lineId, String sku, int quantity) {
}

public record PricedLine(
        String lineId, long totalMinor) {
}

public interface PricingService {
    PricedLine price(OrderLine line);
}
~~~

Illustrative Java DSL:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration(proxyBeanMethods = false)
public class PricingFlowConfiguration {

    @Bean
    IntegrationFlow pricingFlow(PricingService pricingService) {
        return IntegrationFlow.from("pricingInput")
                .split()
                .handle(OrderLine.class,
                        (line, headers) ->
                                pricingService.price(line))
                .aggregate()
                .channel("pricingResults")
                .get();
    }
}
~~~

Here:

1. Input is `List<OrderLine>`.
2. Splitter emits one message per `OrderLine`.
3. Handler returns **`PricedLine`** instead of null.
4. Aggregator collects messages sharing correlation and waits for the release condition.
5. Output is a grouped message, typically a collection of `PricedLine`.

This example shows the **happy path** with complete sequence information and every item returning a result. `pricingResults` needs a suitable channel/consumer for the environment; if a gateway expects a reply, reply routing must also be configured. Do not treat this snippet as proof that aggregation always finishes under errors, filters, timeouts, or unknown stream sizes.

### 8.1. Why Can a Filter After a Splitter Stall an Aggregator Forever?

Suppose a splitter emits 3 items with `sequenceSize=3`. A `Filter` drops the second item **without sending a replacement/completion message**. The Aggregator receives only 2 items, keeps waiting for count 3, and may never release.

Solutions depend on business rules:

- **Filter before splitting**, so sequence size reflects the actual items to process.
- **Return a result for every input**, e.g., `Processed` / `Skipped` / `Failed`, so the Aggregator receives all parts.
- Customize the release strategy based on a business completion count.
- Configure a group timeout and an explicit incomplete-group policy.
- If gathering is unnecessary, do not add an Aggregator just because you used a Splitter.

Do not manually set `sequenceSize=2` on some messages when 3 outputs came from the Splitter without managing group-wide correlation.

### 8.2. Aggregators Hold Group State

An Aggregator retains a **message group** until release conditions are met. For long-running flows, high concurrency, or mid-flight restarts, decide:

- Should the message group store be in-memory or persistent?
- How long is the group timeout?
- On expiry: discard the group, emit partial results, or mark failed?
- Who cleans up completed/expired groups?
- If an item is redelivered, how does the Aggregator detect duplicates?
- If sequence metadata is missing or invalid, how is the group released?

Spring Integration offers `MessageGroupStore` implementations capable of durable persistence when configured, though **a persistent group store does not automatically provide exactly-once semantics**. Downstream side effects still require idempotency.

### 8.3. Resequencer vs. Aggregator

A **Resequencer** orders messages by sequence and normally emits **individual messages**. An **Aggregator** combines multiple messages into **one result**.

If the goal is simply saving lines in business order, you may need ordering at the DB or a serialized channel; gathering with an Aggregator and sorting by `lineId` is sometimes easier to manage. Under concurrency, never infer original order from completion timestamps.

## 9. Synchronous and Asynchronous Processing After Splitting

Splitting itself does not spawn threads. **The channel** defines the execution boundary.

| Channel | Typical Behavior | What to Watch |
| --- | --- | --- |
| `DirectChannel` | Synchronous dispatch on caller's thread | Errors propagate to sender; one slow item stalls the entire flow |
| `ExecutorChannel` | Dispatches via `TaskExecutor` | Runs concurrently; changes thread and transaction context |
| `QueueChannel` | Buffers messages in memory for poller/consumer | Must bound capacity and manage startup/shutdown |
| `PublishSubscribeChannel` | Delivers same message to multiple subscribers | Not a splitter, though composable |
| Broker channel/adapter | Durable queue depending on broker and config | Ack/redelivery/idempotency required |

### 9.1. Synchronous: All Items Processed on Caller Thread

~~~text
Inbound handler
  └─ DirectChannel → Splitter
      ├─ Item 1 → service call (done)
      ├─ Item 2 → service call (done)
      └─ Item 3 → service call (done)
  → send() completes
~~~

Pros: simple, straightforward exception propagation, can share a local transaction if boundaries are configured accordingly. Cons: a single slow item holds the HTTP request thread or broker listener, causing timeouts, backlogs, and reduced throughput.

### 9.2. Asynchronous: ExecutorChannel

Illustrative bounded thread pool configuration:

~~~java
import java.util.concurrent.ThreadPoolExecutor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.ExecutorChannel;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
public class InventoryAsyncChannelConfiguration {

    @Bean
    ThreadPoolTaskExecutor inventoryExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("inventory-item-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        executor.initialize();

        return executor;
    }

    @Bean
    ExecutorChannel inventoryWorkChannel(
            ThreadPoolTaskExecutor inventoryExecutor) {
        return new ExecutorChannel(inventoryExecutor);
    }
}
~~~

To execute post-split work asynchronously, wire the splitter output to the `inventoryWorkChannel` bean and place the handler after it. Conceptual DSL snippet:

~~~java
return IntegrationFlow.from(inventoryBatchInput)
        .split()
        .channel(inventoryWorkChannel)
        .handle(InventoryLine.class,
                (line, headers) -> {
                    processor.process(line);
                    return null;
                })
        .get();
~~~

This snippet is a **bean method body** with `inventoryBatchInput`, `inventoryWorkChannel`, and `processor` injected; not a complete class. When both the thread pool and queue are full, `AbortPolicy` signals rejected execution. Turn this rejection into proper retry/DLQ/backpressure rather than silently dropping messages.

**Transaction context does not cross onto the new thread.** If the broker acks or HTTP returns before async tasks finish, subsequent item failures will not roll back or throw to the caller. Design a **durable handoff**, completion tracking, and error handling.

### 9.3. QueueChannel and Backpressure

`QueueChannel` buffers messages in RAM between a splitter and a poller/consumer. Example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.integration.channel.QueueChannel;

@Bean
QueueChannel inventoryPendingQueue() {
    return new QueueChannel(500);
}
~~~

This is a **bounded in-memory** queue, not equivalent to a durable broker. On process crash, messages sitting only in RAM are lost. If work cannot be lost, use a durable broker or persist work items to a SQL outbox/work table before acknowledging the inbound batch.

Bounded queues require an overflow policy when full: block with timeout, reject, retry with backoff, or spill to durable storage. Never use unbounded queues to hide a slow downstream, as this risks out-of-memory crashes.

## 10. Splitter and Transaction Boundaries

Suppose a batch containing L1, L2, and L3 must update a database. There are two distinct strategies.

### 10.1. One Transaction Covering the Entire Batch

If the whole flow is **synchronous, on the same thread, sharing a transaction manager**, a transaction can wrap the service calling the flow. When L2 fails, SQL changes for L1/L2/L3 can roll back together if transactional preconditions hold.

However:

- L1 may already have called HTTP, published to a broker, or sent email; those effects **do not roll back** with SQL.
- A transaction spanning many lines holds DB connections and locks for a long time.
- Switching to `ExecutorChannel` means the original thread-local transaction **no longer covers** worker threads.
- If a handler catches and swallows exceptions, the transaction may commit even when an item failed.

### 10.2. Separate Transaction Per Item

A common choice is processing each `InventoryLine` in a short transaction:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class JdbcInventoryLineProcessor
        implements InventoryLineProcessor {

    private final InventoryRepository repository;

    public JdbcInventoryLineProcessor(
            InventoryRepository repository) {
        this.repository = repository;
    }

    @Override
    @Transactional
    public void process(InventoryLine line) {
        repository.applyInventoryChange(
                line.lineId(), line.sku(), line.quantity());
    }
}
~~~

`InventoryRepository` is an illustrative port; the implementation must use a suitable **claim/idempotent update** mechanism. Simply adding stock on every invocation without checking whether `lineId` was already applied will corrupt inventory on broker redelivery or retry.

Choose per-item transactions when lines must be retried independently, while tracking **batch status** and defining a partial-failure policy. Without a shared transaction across items, L1 can commit even if L2 fails.

### 10.3. Durable Handoff Before Splitting

For critical batches received over HTTP/brokers, consider:

~~~mermaid
flowchart LR
    A["Inbound batch"] --> B["Validate whole batch"]
    B --> C["SQL transaction: batch + work items"]
    C --> D["Commit + acknowledge inbound"]
    D --> E["Worker claims items"]
    E --> F["Process item"]
    F --> G["Persist outcome"]
    G --> H["Batch completion / aggregate status"]
~~~

The crux: **durably persist the items or processing intent** before acknowledging the source. If a splitter merely dispatches into RAM and the inbound broker message is immediately acked, a process crash loses unprocessed items.

No single Splitter configuration guarantees durable handoff on its own; you must align the message source, channel, transaction manager, broker ack, and work table.

## 11. Idempotency for Each Item and the Whole Batch

`correlationId` and `sequenceNumber` headers support flow routing. Duplicate prevention must rely on **business identity** that remains stable across retries.

Common keys:

- `batchId`: business batch identifier.
- `lineId` or `(batchId, lineId)`: item identifier.
- `sourceVersion`: upstream change version.
- `operationType`: distinguishes create/update/delete when multiple valid actions target the same lineId.

Example PostgreSQL table:

~~~sql
CREATE TABLE processed_inventory_lines (
    batch_id VARCHAR(100) NOT NULL,
    line_id VARCHAR(100) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (batch_id, line_id)
);
~~~

Illustrative SQL claim:

~~~sql
INSERT INTO processed_inventory_lines(
    batch_id, line_id, processed_at)
VALUES (?, ?, CURRENT_TIMESTAMP)
ON CONFLICT (batch_id, line_id) DO NOTHING;
~~~

If the insert affects **0 rows**, that line was already claimed/processed per contract and inventory must not be adjusted again. **Crucially:** the claim and the business update must be in the **same transaction**; if the claim commits separately and the update fails, retries would wrongly skip the unfinished line.

When inventory receives multiple versions for the same SKU, the business unique key may need `sourceEventId` or an explicit version. Choose deduplication keys from event semantics rather than list position.

### 11.1. Why sequenceNumber Is Not Enough

If the first batch had `[L1, L2, L3]`, L2 had `sequenceNumber=2`. If upstream retries with a filtered batch `[L2, L3]`, L2 becomes sequence 1. Relying on sequence numbers for idempotency breaks immediately.

When a batch is replayed, `Message.id` and Splitter correlation metadata can be completely new. **Business keys must be independent of fan-out mechanics**.

## 12. Handling Partial Errors and Retry Decisions

Suppose L1 succeeds, L2 hits HTTP 503, and L3 has not run yet. Behavior depends on channels and transactions:

| Flow type | Potential consequence | Decisions needed |
| --- | --- | --- |
| Synchronous `DirectChannel`, exception propagates | Sender sees error; earlier items may already have side effects | Rollback/replay/idempotency |
| Async `ExecutorChannel`, one item fails | Failure surfaces on worker/error channel | Item retry, DLQ, batch completion |
| In-memory `QueueChannel`, process crashes | Unconsumed messages lost | Durable queue/store needed |
| Durable per-item broker | Broker may redeliver before ack | Per-item inbox/unique constraint |
| Split → transform → aggregate | Missing output for failed item | Timeout/partial result/failure marker |
| Split + filter | Output dropped per policy | Adjust sequence/release strategy |

### 12.1. Message Errors and errorChannel

Spring Integration provides `errorChannel` and `ErrorMessage` for suitable contexts, especially across async boundaries. Handler exceptions can be wrapped in `MessageHandlingException` or other messaging errors containing the failed message for diagnostics.

**Do not assume all errors arrive on `errorChannel`.** In fully synchronous `DirectChannel` flows, exceptions normally throw directly to the caller. With async tasks or broker listeners, error publishing depends on configured pollers, adapters, channels, and error handlers.

Design considerations:

- Classify validation errors (permanent), network/429/503 (transient), and timeouts with unknown outcomes.
- Apply bounded retry policies with backoff/jitter.
- Persist failed records with `batchId`/`lineId` in an audit/work table.
- Send dead-letter/parking-lot messages when automatic recovery fails.
- Never put raw payloads or sensitive data in logs or error descriptions.
- If using an Aggregator, emit a `FailedLine` result or define explicit partial-group release.

### 12.2. Per-Line Result Model

An output model can capture full status:

~~~java
public record LineResult(
        String batchId,
        String lineId,
        LineStatus status,
        String errorCode) {

    public enum LineStatus {
        APPLIED,
        DUPLICATE,
        SKIPPED,
        FAILED
    }
}
~~~

With this model, if the business requires an **end-of-batch report**, the handler can emit a `LineResult` for **every input line**, including classified failures, instead of swallowing errors and emitting nothing. Infrastructure errors with uncertain outcomes may need `PENDING_RETRY` rather than concluding permanent `FAILED`.

Even when the Aggregator receives all messages, **business status** still matters: it may need to emit `PARTIALLY_SUCCEEDED` instead of treating a full sequence count as success.

## 13. Processing Order and Output Order

An ordered input list `[L1, L2, L3]` does not guarantee the same **completion order** under async execution:

~~~text
Split order:
  L1 → L2 → L3

Completion with parallel workers:
  L3 (120ms) → L1 (500ms) → L2 (800ms)
~~~

When ordering must be preserved per aggregate/SKU/account:

- Route items sharing the same business key to a **partition/serialized consumer**.
- Use a single worker for keys requiring sequential processing.
- Record `sourceVersion` and enforce optimistic locking/version checks on updates.
- Use a Resequencer when output messages must be reordered by sequence.
- Or gather results and **sort by business order** before consuming.

Never use a Resequencer to "fix" an out-of-order side effect already committed to a database. If correctness requires "never apply event version 5 before version 4," enforce update/locking guards directly in the repository/consumer.

### 13.1. Nested Splits and Correlation

You can split a file into chunks, then split each chunk into lines:

~~~text
FileBatch
  ├─ Chunk 1
  |   ├─ Line 1
  |   └─ Line 2
  └─ Chunk 2
      ├─ Line 3
      └─ Line 4
~~~

Each level may need distinct correlation: file ID, chunk ID, line ID. Do not let an inner level's correlation header overwrite the outer one and cause an outer Aggregator to misgroup messages. For nested split/gather flows, design hierarchical metadata or distinct business keys and test real grouping behavior.

## 14. Large Payloads: Files, CSVs, and Database Batches

### 14.1. FileSplitter and Line-Oriented Processing

Spring Integration provides file/text adapters and splitters in the relevant module, such as `FileSplitter`, to stream file contents line-by-line or with markers depending on configuration. You do not need to load an entire huge file into a `List<String>` just to use `DefaultMessageSplitter`.

Practical flow:

~~~text
File inbound adapter
   ↓
Validate file metadata + size
   ↓
FileSplitter / line reader
   ↓
Parse CSV row → DTO
   ↓
Validate record
   ↓
Batch insert / HTTP adapter
   ↓
Checkpoint + result
~~~

Watch out for:

- Charset/BOM, CSV quoting, and escaping.
- Header/trailer rows and malformed records.
- Line length/row count limits to prevent OOM from huge payloads.
- Duplicate rows, checkpoints, and file state after errors.
- Moving/archiving files only after processing meets the contract.
- Whether a single bad line fails the entire file or is quarantined individually.

### 14.2. Database Paging Instead of Loading Everything

When a reconciliation job reads 2 million SQL rows, running `SELECT *` and splitting everything into RAM is usually wrong. Instead:

1. Query with stable-key pagination/keyset.
2. Create work chunks with IDs/versions.
3. Save a checkpoint after each chunk commits.
4. Split each chunk into items within safe processing bounds.
5. Resume from the checkpoint on crash instead of blindly reprocessing.

**Warning about JDBC/JPA streams:** a cursor/stream is typically tied to a connection/transaction. If the splitter processes asynchronously after the transaction scope ends, the cursor may close. For durable jobs, materialize small work items or persist them before crossing thread/process boundaries.

### 14.3. Transport Configuration Differences

A REST request may have a 2-second timeout; a 5,000-item batch should not run synchronously in the request thread or return 200 merely upon receipt. Return 202 Accepted with a batch ID if the contract allows, persist work durably, process in the background, and expose a status endpoint.

Similarly, a broker consumer should not ack a batch before items are durably handed off downstream if the contract forbids job loss.

## 15. Designing Batch-Level and Item-Level Observability

Because a Splitter fans out work, **counting batches is insufficient to understand item load**.

| Metric/Observation | Meaning |
| --- | --- |
| `integration.batch.received` | Batches received |
| `integration.batch.size` | Distribution of items per batch |
| `integration.item.started` | Items started processing |
| `integration.item.completed` | Item outcomes: success/duplicate/skipped/failure |
| `integration.item.duration` | Per-item latency |
| `integration.item.retry` | Attempt/retry counts |
| `integration.batch.completed` | Batches completed per contract |
| `integration.queue.depth` | Post-splitter backlog/buffer |
| `integration.batch.oldest.age` | Oldest pending batch |
| `integration.deadletter.count` | Items needing manual intervention |

**Do not equate "split into N messages" with "successfully processed N records."** If downstream errors, times out, or rolls back, the output count only proves the splitter emitted messages.

### 15.1. An Observation for Item Processing

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
public class ObservedInventoryLineProcessor
        implements InventoryLineProcessor {

    private final InventoryRepository repository;
    private final ObservationRegistry registry;

    public ObservedInventoryLineProcessor(
            InventoryRepository repository,
            ObservationRegistry registry) {
        this.repository = repository;
        this.registry = registry;
    }

    @Override
    public void process(InventoryLine line) {
        Observation.createNotStarted(
                        "integration.inventory.item.process",
                        registry)
                .lowCardinalityKeyValue(
                        "operation", "apply_inventory")
                .observe(() ->
                        repository.applyInventoryChange(
                                line.lineId(),
                                line.sku(),
                                line.quantity()));
    }
}
~~~

`InventoryRepository` is an illustrative business port. This code measures a **synchronous method**; when the underlying operation is reactive/asynchronous, wrapping only `Mono`/`CompletableFuture` creation does not measure total execution duration. Capture completion lifecycle and propagate context properly.

Appropriate tags: `flow=inventory-import`, `operation=apply_inventory`, `outcome=success/error` with small value sets. Never use `batchId`, `lineId`, individual SKUs, or `correlationId` as metric labels due to high cardinality.

### 15.2. Distributed Tracing Across Async Boundaries

With synchronous `DirectChannel`, trace context stays on the current thread when instrumentation is enabled. With `ExecutorChannel`, brokers, or external systems, trace context may not automatically cross every boundary unless executors/transports are instrumented.

A batch trace can link many item spans, but remember to:

- Configure sampling, because fanning out thousands of items generates many spans.
- Propagate context across boundaries using Micrometer/Spring-supported mechanisms.
- Never turn trace/span IDs into idempotency keys.
- Include business correlation IDs in secured audit logs to reconcile retries.
- Measure batch completion and final business state, not just the batch-receiving HTTP request.

## 16. Testing the Splitter and Output Headers

Testing should cover **three levels**: pure splitting logic, messaging flow wiring, and end-to-end transactions/retries.

### 16.1. Unit Testing the Chunking Function

~~~java
import java.util.List;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class ChunkSplitTest {

    @Test
    void dividesFiveLinesIntoThreeChunks() {
        var batch = new InventoryBatch(
                "B-1",
                List.of(
                        new InventoryLine("L-1", "P1", 1),
                        new InventoryLine("L-2", "P2", 1),
                        new InventoryLine("L-3", "P3", 1),
                        new InventoryLine("L-4", "P4", 1),
                        new InventoryLine("L-5", "P5", 1)));

        var chunks = splitChunks(batch, 2);

        assertEquals(3, chunks.size());
        assertEquals(2, chunks.get(0).size());
        assertEquals(2, chunks.get(1).size());
        assertEquals(1, chunks.get(2).size());
    }

    // splitChunks(...) is the illustrative method from section 5.1,
    // which can be placed into an injected service.
}
~~~

This is a unit-test sketch; to compile, place `splitChunks` in an appropriate fixture/service class and call the corresponding instance/static method. Add tests for empty lists, `chunkSize=0`, `chunkSize=1`, and very large batch boundaries.

### 16.2. Spring Integration Test with QueueChannel

A flow test can use a `QueueChannel` with capacity 10 to **collect splitter output messages**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration(proxyBeanMethods = false)
public class SplitterTestConfiguration {

    @Bean
    MessageChannel batchInput() {
        return new DirectChannel();
    }

    @Bean
    QueueChannel lineOutput() {
        return new QueueChannel(10);
    }

    @Bean
    IntegrationFlow testSplitFlow(
            MessageChannel batchInput,
            QueueChannel lineOutput) {
        return IntegrationFlow.from(batchInput)
                .split()
                .channel(lineOutput)
                .get();
    }
}
~~~

Test:

~~~java
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(classes = SplitterTestConfiguration.class)
class SplitterFlowTest {

    @Autowired
    @Qualifier("batchInput")
    MessageChannel batchInput;

    @Autowired
    @Qualifier("lineOutput")
    QueueChannel lineOutput;

    @Test
    void emitsOneMessagePerLine() {
        var lines = List.of(
                new InventoryLine("L-1", "P1", 1),
                new InventoryLine("L-2", "P2", 2));

        assertTrue(batchInput.send(
                MessageBuilder.withPayload(lines)
                        .setHeader("batchId", "B-1")
                        .build()));

        var first = lineOutput.receive(1000);
        var second = lineOutput.receive(1000);

        assertNotNull(first);
        assertNotNull(second);
        assertEquals("L-1",
                ((InventoryLine) first.getPayload()).lineId());
        assertEquals("L-2",
                ((InventoryLine) second.getPayload()).lineId());

        assertEquals("B-1",
                first.getHeaders().get("batchId"));
        assertEquals("B-1",
                second.getHeaders().get("batchId"));

        assertNull(lineOutput.receive(10));
    }
}
~~~

This test verifies output count, payloads, and business headers, not sequence metadata. When the flow depends on an Aggregator, test **`correlationId`, `sequenceNumber`, and `sequenceSize` per configuration/version**. A test `QueueChannel` does not represent production durability.

### 16.3. Testing Critical Failure Cases

| Scenario | What to assert |
| --- | --- |
| Empty input collection | No unexpected messages emitted; batch completes per rule |
| Null input | Fails validation before splitting |
| Huge batch | Bounded or chunked, no OOM |
| Message with business headers | Required headers are not lost |
| Apply sequence | Valid correlation and sequence for the group |
| Transformer returns result | Aggregator receives enough outputs to release |
| Filter drops an item | Group does not wait forever if policy requires completion |
| Handler throws exception on item 2 | Side effects and retries match transaction boundaries |
| Executor queue full | Rejection does not silently drop items |
| Crash after inbound ack | Durable handoff protects unprocessed items |
| Duplicate broker delivery | Same business key is not applied twice |
| Parallel out-of-order completion | Business state stays correct per version |
| Nested split/aggregate | Outer/inner correlations do not mix |

### 16.4. Do Not Mistake Splitter Unit Tests for Transactional Integration Tests

Java DSL tests only prove Spring messaging routing/wiring. For real processing, write integration tests with PostgreSQL/Testcontainers, HTTP stubs, and/or broker test fixtures to verify:

1. Inbox/outbox/checkpoints are written **in the same transaction** as business updates when required.
2. Message ACK happens only when durable responsibility has been taken.
3. Crashes/replays do not emit duplicate business effects.
4. One item failing does not lose unprocessed items.
5. Batch completion reaches success only when permitted by the business contract.

## 17. Common Design Mistakes

| Symptom | Cause | Solution |
| --- | --- | --- |
| Splitter emits one single message containing the whole batch | Input not a collection type or method not wired as splitter | Check payload/annotations/flow |
| `@Splitter` does not run | Input channel not wired, missing integration config | Check bean scanning/channel names |
| 100 input items but only 99 processed | Filter/drop/error on one item or queue loss | Per-item audit, error flow, durability |
| Assumed split runs in parallel, still slow | Synchronous `DirectChannel` | Bounded ExecutorChannel/broker |
| Switched to async and lost transactions | Thread-local transaction context | Per-item transactions and durable handoff |
| Aggregator never releases | Lost sequence, filtered item, error, or unknown size | Release strategy, failure markers, timeouts |
| Aggregator merges two batches | Wrong/duplicate correlation header or nested split | Design correlation and test |
| Duplicate processing after retry | Used sequence/message ID as idempotency key | Stable business key + unique constraint |
| Pool/DB overloaded after split | Unbounded fan-out with no backpressure | Chunking, queue capacity, concurrency budget |
| Messages lost after restart | In-memory QueueChannel only, early upstream ack | Durable broker/SQL work table/outbox |
| Out-of-order data | Executor running concurrently | Version guards/partitioning/resequencer |
| XML/JSON `byte[]` split into wrong pieces | Split before decode/validation | Deserialize/transform first |
| JDBC stream fails mid-way | Cursor/transaction closed before split finished | Materialize chunks or manage stream scope |
| Metrics count split success as business success | Measured fan-out instead of completion | Item outcomes + batch completion |
| Async item error never reaches caller | ExecutorChannel/ErrorMessage boundary | Error channel, retry/DLQ/audit |

## 18. Pre-Production Splitter Checklist

- [ ] Clearly defined whether one input message contains a **collection, chunk, or domain batch object**.
- [ ] Selected default `split()` or `@Splitter`/custom splitter matching the contract.
- [ ] Handled empty lists, nulls, size limits, and invalid elements.
- [ ] Business headers (`batchId`, `lineId`, version) preserved through the flow.
- [ ] If using an Aggregator, correlation/sequence metadata configured and tested.
- [ ] Post-split filters/errors cannot leave the Aggregator waiting indefinitely.
- [ ] Never assumed Splitter runs concurrently by itself; channel/thread model explicitly designed.
- [ ] Thread pools and queues have capacity/concurrency limits and overflow/rejection policies.
- [ ] Transaction boundaries defined per batch or per item, including across thread switches.
- [ ] Upstream ACK occurs only after downstream/work items are durably accepted per contract.
- [ ] Idempotency uses **stable business keys**, never technical sequence/message IDs.
- [ ] Retries are bounded, errors are classified, and DLQ/reconciliation paths exist.
- [ ] Ordering/version policies defined for items targeting the same business aggregate.
- [ ] Tests cover Splitter outputs, headers, Aggregator, concurrency, crash/replay, and duplicates.
- [ ] Metrics/traces distinguish fan-out counts, item completion, retries, and backlogs.

**Key takeaway:** A Splitter divides one message into **multiple processing units**, but it does not decide how large a unit should be, whether it runs in parallel, where transactions live, or whether retries are safe. When combining `split → handle/transform → aggregate`, preserve correlation/sequence and design for missing elements. When integrating with HTTP/SQL/cache/brokers in Spring Boot, reliability depends on **data contracts, durable handoff, idempotency, transactions, error handling, testing, and observability**.

## References

- [Spring Integration — Splitter](https://docs.spring.io/spring-integration/reference/splitter.html): Message Splitter, annotations, Java DSL, and sequence metadata.
- [Spring Integration — Aggregator](https://docs.spring.io/spring-integration/reference/aggregator.html): correlation, release strategies, and message groups.
- [Spring Integration — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html): DirectChannel, ExecutorChannel, QueueChannel, and processing boundaries.
- [Spring Integration — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): synchronous/asynchronous error handling and error channels.
- [Spring Integration — Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html): IntegrationFlow, endpoints, and Java configuration.
- [Spring Boot — Spring Integration](https://docs.spring.io/spring-boot/reference/messaging/spring-integration.html): Spring Integration auto-configuration in Boot.
- [Enterprise Integration Patterns — Splitter](https://www.enterpriseintegrationpatterns.com/patterns/messaging/Sequencer.html): pattern for splitting a message into parts.
