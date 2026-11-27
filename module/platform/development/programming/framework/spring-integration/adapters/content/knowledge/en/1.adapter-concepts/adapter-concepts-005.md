# Adapter vs. Service Activator and Transformer

## Learning Objectives

After this lesson, you will be able to:

- Distinguish **channel adapter**, **service activator**, and **transformer** by responsibility, inputs, outputs, and side effects.
- Explain why these three endpoint types often appear sequentially in the same **IntegrationFlow** yet cannot be treated as direct substitutes for one another.
- Identify the roles of **MessageChannel**, **Message**, payload, headers, and pollers in an inbound or outbound flow.
- Write a Java DSL flow combining a file inbound adapter, transformers to read/normalize CSV, a service activator to process orders, and a file outbound adapter to export receipts.
- Choose the appropriate component when integrating SFTP, HTTP, JMS, AMQP, Kafka, or databases; evaluate errors, retries, idempotency, and connection lifecycles.

## 1. Three Distinct Roles in an Integration Flow

Suppose an application receives partner order files, converts CSV into Java data, validates the order, and writes a receipt to another directory. A typical Spring Integration design looks like this:

~~~mermaid
flowchart LR
    EXT["Partner directory"] --> IN["File inbound adapter"]
    IN --> CH1["MessageChannel"]
    CH1 --> TR["Transformer<br/>File/CSV → Order"]
    TR --> CH2["MessageChannel"]
    CH2 --> SA["Service activator<br/>validate and process Order"]
    SA --> CH3["MessageChannel"]
    CH3 --> TR2["Transformer<br/>Receipt → CSV"]
    TR2 --> OUT["File outbound adapter"]
    OUT --> DEST["Receipts directory"]
~~~

In this diagram:

- **Channel adapter** connects the message flow to a source or target **outside** the application, such as a file, SFTP, HTTP, JMS, AMQP, Kafka, or a database.
- **Transformer** changes the **shape/representation of data** in a message so the next step can consume it, such as from a File to CSV text and then to an Order object.
- **Service activator** triggers **a service method or application action** to process the message, such as validating rules, performing lookups, or persisting business state.

All three participate in one messaging architecture, yet they answer three different questions:

| Question | Answering Component |
| --- | --- |
| Through which protocol does data **enter/leave** the application? | Channel adapter |
| How should the data **be represented** next? | Transformer |
| What **should the application do** with the data? | Service activator |

Separating these responsibilities lets you swap a file source for SFTP or Kafka with minimal impact on order-processing rules. However, when replacing an adapter, you must still verify payload types, metadata, and the send/receive semantics of the new protocol.

## 2. Core Comparison Table

| Criterion | Channel Adapter | Transformer | Service Activator |
| --- | --- | --- | --- |
| Purpose | Connects the messaging flow to an **external system** | Transforms **payload/message** | Executes **business logic or a service** when a message arrives |
| Examples | Reading SFTP, receiving JMS, publishing Kafka, writing files | CSV → DTO, JSON → object, DTO → string | Validating an order, calling OrderService, computing fees |
| Input mechanism | Inbound pulls from external source; outbound receives from channel | Receives message from input channel | Receives message from input channel |
| Output | Inbound emits message to channel; outbound produces external side effect | Typically emits transformed payload/message downstream | May emit a reply or end the flow if void |
| Side effects | External I/O is its primary responsibility | Should favor data mapping and avoid hidden I/O | May call services, query/write DB, or execute business actions |
| Primary concerns | Connections, poller/listener, acks, protocol format | Data types, schemas, conversion errors, preserving headers | Business rules, transactions, performance, exceptions |
| When to use | When ingesting from or sending to the outside world | When the current data shape does not fit the next step | When triggering an application action |

**There is no rule forbidding a service activator from doing I/O.** A service activator can certainly call an HTTP client or repository. However, if Spring Integration already provides a dedicated adapter/gateway for that protocol, using the specialized endpoint usually clarifies connection responsibilities, message contracts, and error configuration. The final decision depends on real requirements.

**A transformer is not limited to changing data types.** It can normalize content, map fields, reshape the payload, or return a new message. Even so, keep transformations predictable and free of side effects to simplify testing, retries, and reuse.

## 3. Channel Adapter: Responsible at the Protocol Boundary

### 3.1. Inbound Adapter

An inbound adapter pulls or receives data from an external system, constructs a **Message<?>**, and pushes it onto a **MessageChannel**. Depending on the source, it works via a **poller** or a **listener/consumer**:

- **Polling:** reads directories, syncs SFTP, or queries a DB on a schedule; a Spring Integration poller triggers the message source.
- **Message-driven:** JMS/AMQP listeners, Kafka consumers, or endpoints triggered by infrastructure events. The internal polling loop inside a Kafka client does not mean users must attach a Spring Integration poller to every Kafka inbound endpoint.

For instance, a file inbound adapter can create a message whose **payload is a File**. It does not yet parse file contents into Order objects; that belongs to downstream transformers/handlers.

### 3.2. Outbound Adapter

An outbound adapter consumes a message from a channel and performs an external side effect: writing a file, sending a message to a broker, uploading to SFTP, or updating a data store. This endpoint usually ends a **one-way** flow without returning a business reply message.

If you need a response for subsequent flow steps, consider an **outbound gateway**. For example, when calling an HTTP API to fetch a credit limit, a gateway fits better than a one-way adapter because the next processing step needs the response body.

### 3.3. Adapters Can Still Have Converters

Many adapters support serializers, converters, or header mappers right at the protocol boundary. That **does not turn the adapter into a business transformer**:

- Converters at the adapter handle how data is represented in the **protocol** or client API.
- Transformers inside the flow handle how data is represented **between processing steps**, especially normalizing source data into a domain model.

For example, a Kafka adapter may deserialize bytes into a String per consumer settings; a subsequent transformer parses that JSON string into an Order object. Both transformations live at different layers of responsibility.

## 4. Transformer: Bridging Source Contracts to Usable Data

A transformer is a **message endpoint**: it receives a message from a channel, transforms the payload or message, and forwards the result to the next step. In Java DSL, you use **transform(...)** with lambdas, beans, or built-in transformers.

~~~mermaid
flowchart LR
    IN["Message<File><br/>headers: file source"] --> TR["Transformer"]
    TR --> OUT["Message<Order><br/>headers: file source + metadata"]
~~~

A transformer can:

1. Decode bytes into a String using a specified charset.
2. Parse CSV or JSON into a DTO.
3. Map partner field names to domain data types.
4. Normalize timezones, status codes, or measurement units.
5. Format an OrderReceipt into a CSV or JSON string for an outbound adapter to send.

Example of a small, I/O-free transformation:

~~~java
record RawOrder(String orderId, String amount) {}
record Order(String orderId, long totalVnd) {}

static Order toOrder(RawOrder raw) {
    return new Order(
        raw.orderId().trim(),
        Long.parseLong(raw.amount().trim())
    );
}
~~~

This function focuses purely on **data conversion**. It does not call a database, publish to Kafka, or validate every business rule for an order. If the input format is invalid, the transformer can throw an exception; the flow must define an error path.

### 4.1. New Payloads and Headers

A Message in Spring Integration has a **payload** and **headers**. When a transformer returns a new payload, the framework builds an output message and preserves appropriate headers according to transformer rules, except for special headers or custom configurations.

Do not assume every header is always preserved across every transformer type or automatically forwarded to the target protocol. Explicitly verify:

- Identification/correlation headers used for tracing and reconciliation.
- Whether file, JMS/AMQP, Kafka, or HTTP metadata remains meaningful downstream.
- Whether headers used for routing, filename generation, topic selection, or reply mapping are altered.
- Whether the normalized DTO needs to retain the source ID and event version.

A newly generated **MessageHeaders.ID** on each message should not replace a **business idempotency key** (such as a stable orderId or eventId).

### 4.2. Why Shouldn't a Transformer Do Everything?

Suppose a transformer parses CSV, calls a REST API to check credit limits, and writes to a database all at once. When a message send is retried, it becomes very hard to tell how far the transformation got and whether side effects were duplicated.

A cleaner design is:

~~~text
File (adapter)
  -> String/Order (transformer)
  -> check credit limit, save info (service activator)
  -> Receipt (format export transformer)
  -> File/Kafka (outbound adapter)
~~~

This does not force every tiny conversion into its own bean. Use lambdas for simple mappings; use dedicated classes for complex, schema-driven mappings or transformations needing independent unit tests.

## 5. Service Activator: Invoking a Service to Process a Message

A service activator is an endpoint that receives a message and invokes a Java method or handler. It is commonly used to:

- Perform business-rule validation.
- Compute fees, classify orders, or determine status.
- Call an application service or repository.
- Record processing status or execute a side effect requiring transaction control.
- Produce a result object so the flow can continue.

A service activator **does not necessarily terminate a flow**. If the method returns a value or appropriate message, Spring Integration can emit a **reply** to the configured output channel or replyChannel.

~~~java
record Order(String orderId, long totalVnd) {}
record Receipt(String orderId, String status, long totalVnd) {}

class OrderService {
    public Receipt accept(Order order) {
        if (order.totalVnd() <= 0) {
            throw new IllegalArgumentException(
                "Total amount must be greater than 0");
        }
        return new Receipt(
            order.orderId(), "ACCEPTED", order.totalVnd());
    }
}
~~~

Here, **accept(...)** is a business processing method. It takes an Order and returns a Receipt. Returning a Receipt does not make the method a transformer in a design sense: its main job is **enforcing order acceptance rules**, and the change in output type is a byproduct of the business operation.

Conversely, if a method merely renames fields and reformats data without applying business behavior, a transformer usually expresses that intent better.

### 5.1. Does a Service Activator Return a Result or Only Perform a Side Effect?

| Method/Handler Style | Meaning |
| --- | --- |
| Returns Receipt | Produces a reply for downstream continuation when the endpoint/flow is wired accordingly |
| Returns Message with new headers | Allows further control over metadata on the result |
| Returns void or null | Produces no business reply from that handler; fits terminal handlers, requires care if upstream expects a response |
| Throws an exception | Synchronous flows may receive the error directly; asynchronous flows need an error-handling path |

With a request–reply gateway, a service activator returning null can leave the waiting gateway with no result until it times out. Never assume a side effect automatically becomes a reply message.

## 6. Complete Java DSL Example: Adapter → Transformer → Service Activator → Adapter

This example builds a small flow:

1. A file inbound adapter picks up new CSV files from **./data/inbox**.
2. A transformer reads the file content as a String.
3. A transformer converts a single-order CSV into an Order.
4. A service activator validates rules and creates a Receipt.
5. A header enricher sets the receipt filename; a transformer formats Receipt into CSV.
6. A file outbound adapter writes the receipt into **./data/receipts**.

~~~mermaid
flowchart LR
    F["./data/inbox/order.csv"] --> I["File inbound adapter<br/>5s poller"]
    I --> T1["Transformer<br/>File → String → Order"]
    T1 --> S["Service activator<br/>OrderService.accept"]
    S --> T2["Header enricher + Transformer<br/>Receipt → CSV"]
    T2 --> O["File outbound adapter"]
    O --> R["./data/receipts/receipt-*.csv"]
~~~

### 6.1. DTOs and Business Service

The example uses Java 17+ for records. In a real application, place these types in appropriate Java files.

~~~java
public record Order(String orderId, long totalVnd) {}

public record Receipt(
        String orderId, String status, long totalVnd) {}
~~~

~~~java
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    public Receipt accept(Order order) {
        // Ensure the filename is generated from a safe ID.
        if (order.orderId() == null
                || !order.orderId().matches("[A-Za-z0-9_-]{1,64}")) {
            throw new IllegalArgumentException(
                "Invalid order ID");
        }
        if (order.totalVnd() <= 0) {
            throw new IllegalArgumentException(
                "Total amount must be greater than 0");
        }
        return new Receipt(
            order.orderId(), "ACCEPTED", order.totalVnd());
    }
}
~~~

In the example, the service only validates and creates a result to highlight its distinction from a transformer. A real service might invoke a repository and require transactions, deduplication locks, order state validation, and fuller business conditions.

### 6.2. IntegrationFlow Configuration

With Spring Boot, you typically use **spring-boot-starter-integration** together with **spring-integration-file**, managed by the Boot version in use.

~~~java
import java.io.File;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.file.FileHeaders;
import org.springframework.integration.file.dsl.Files;
import org.springframework.integration.file.support.FileExistsMode;

@Configuration
@EnableIntegration
public class OrderImportConfiguration {

    @Bean
    public IntegrationFlow orderFileFlow(OrderService orderService) {
        return IntegrationFlow
            // 1. Inbound adapter: fetch files from external system.
            .from(
                Files.inboundAdapter(new File("./data/inbox"))
                    .autoCreateDirectory(true)
                    .patternFilter("*.csv"),
                endpoint -> endpoint.poller(
                    Pollers.fixedDelay(Duration.ofSeconds(5))
                        .maxMessagesPerPoll(5)))

            // 2. Transformer: File -> String.
            .transform(File.class, file -> {
                try {
                    return java.nio.file.Files.readString(
                        file.toPath(), StandardCharsets.UTF_8);
                } catch (IOException ex) {
                    throw new UncheckedIOException(ex);
                }
            })

            // 3. Transformer: CSV -> domain Order.
            .transform(String.class, csv -> {
                String[] rows = csv.strip().split("\\R");
                if (rows.length != 2
                        || !"orderId,totalVnd".equals(rows[0])) {
                    throw new IllegalArgumentException(
                        "CSV requires a header and one data row");
                }
                String[] values = rows[1].split(",", -1);
                if (values.length != 2) {
                    throw new IllegalArgumentException(
                        "CSV must have exactly two columns");
                }
                return new Order(
                    values[0].trim(),
                    Long.parseLong(values[1].trim()));
            })

            // 4. Service activator: process domain Order -> Receipt.
            .handle(orderService, "accept")

            // 5. Header enricher + transformer preparing output.
            .enrichHeaders(spec -> spec.headerFunction(
                FileHeaders.FILENAME,
                message -> "receipt-"
                    + ((Receipt) message.getPayload()).orderId()
                    + ".csv"))
            .transform(Receipt.class, receipt ->
                "orderId,status,totalVnd\n"
                + receipt.orderId() + ","
                + receipt.status() + ","
                + receipt.totalVnd() + "\n")

            // 6. Outbound adapter: write CSV to external system.
            .handle(Files.outboundAdapter(
                    new File("./data/receipts"))
                .autoCreateDirectory(true)
                .fileNameGenerator(message ->
                    (String) message.getHeaders().get(
                        FileHeaders.FILENAME))
                .fileExistsMode(FileExistsMode.FAIL))
            .get();
    }
}
~~~

**Notes on the code:** This is a simplified CSV example with exactly one data row and two columns. Splitting on commas does not fully support CSV rules when fields contain commas, quotes, or newlines; production data needs a CSV parser/encoder library and schema validation. File inbound runs on a polling schedule, so seeing a filename does not prove the sender finished writing it. Production applications need a safe file handoff convention.

### 6.3. Expected Result

Suppose you place **./data/inbox/order-1001.csv** with content:

~~~csv
orderId,totalVnd
O-1001,150000
~~~

If write permissions allow and the target file does not yet exist, the flow creates **./data/receipts/receipt-O-1001.csv**:

~~~csv
orderId,status,totalVnd
O-1001,ACCEPTED,150000
~~~

Explanation:

- The file inbound adapter receives a **File** without understanding Order itself.
- The first transformer converts **File → String**; the second converts **String → Order**.
- The service activator receives the Order, applies validation rules, and produces a Receipt.
- The header enricher adds **FileHeaders.FILENAME** so the outbound adapter knows the receipt filename.
- The final transformer converts Receipt into a **CSV String**; the outbound file adapter writes the content to disk.

Each step has a concrete responsibility, so CSV parsing, OrderService rules, and file-writing configuration can be tested independently.

### 6.4. Header Notes After a Transformer

When a transformer returns a new payload, Spring Integration normally constructs an output message and copies allowed headers per the transformer's mechanism. In the example, **FileHeaders.FILENAME** is attached before the final transformer so the outbound adapter reads it from the incoming message. If you write a custom transformer that builds a Message directly or manipulates headers, verify filename/correlation preservation with integration tests.

Do not rely on the input filename as a unique business key when a partner might resend the same order under a different name. Deduplication keys should come from stable business data, such as partnerId and orderId.

## 7. Choosing Adapter, Transformer, or Service Activator in Practice

| Scenario | Typically Appropriate Component | Why? |
| --- | --- | --- |
| Fetching files from SFTP on a schedule | SFTP inbound adapter + poller | Manages file-transfer protocol and poll schedule |
| Converting File to UTF-8 text | Transformer | Changes payload representation for the next step |
| Parsing JSON into Order | Transformer | Maps the data contract |
| Checking inventory and recording an order | Service activator | Invokes business logic and can participate in transactions |
| Publishing OrderCreated to Kafka | Kafka outbound adapter | Handles producer/broker communication per configuration |
| Converting OrderCreated to JSON | Transformer or boundary converter | Formats payload to match target contract |
| Reading JMS messages into the flow | JMS inbound adapter | Ingests messages from an external source |
| Calling a REST API and using its response | Outbound HTTP gateway | Request–reply contract, distinct from a one-way adapter |
| Writing an update to a database | JDBC outbound adapter or service activator calling a repository | Choose based on abstraction needs, transactions, and business control |
| Invoking a flow from Java and getting a result | Messaging gateway | Bridges a Java method with a messaging flow |

A real flow can chain multiple transformers and service activators after **one** inbound adapter, or one transformer can feed multiple outbound adapters. The number of endpoints depends on architecture and requirements rather than a rigid adapter + transformer + service activator trio.

### 7.1. Is It Wrong for a Service Activator to Call HTTP or Kafka Directly?

Not necessarily. A service activator is a hook for Java code, so it can invoke an HTTP client, repository, or producer. However, consider:

- Is there an appropriate Spring Integration adapter/gateway that makes message dispatch, routing, timeouts, or error flows clearer?
- Does that logic express **business rules**, or is it merely wrapping an external system's I/O API?
- Does it need **request–reply** handling or only one-way dispatch?
- Can business logic be tested without live connections to external systems?

If an endpoint only publishes a message to Kafka, an outbound adapter expresses intent more cleanly than embedding raw producer code inside a service activator. If database persistence is a business step with transactions and complex invariants, a service activator calling an application service/repository may fit very well.

## 8. When Three Components Collaborate, Whose Fault Is an Error?

A flow can fail at different boundaries:

~~~mermaid
flowchart TD
    A["Inbound adapter"] --> B{"Received data OK?"}
    B -- "No" --> E1["Connection / source read error"]
    B -- "Yes" --> C["Transformer"]
    C --> D{"Valid data format?"}
    D -- "No" --> E2["Parse / schema error"]
    D -- "Yes" --> S["Service activator"]
    S --> V{"Business rules valid?"}
    V -- "No" --> E3["Business error"]
    V -- "Yes" --> O["Outbound adapter"]
    O --> Z{"Write/send OK?"}
    Z -- "No" --> E4["I/O / target protocol error"]
    Z -- "Yes" --> DONE["Completed per current contract"]
~~~

| Error Location | Examples | Required Response |
| --- | --- | --- |
| Inbound adapter | SFTP timeout, unreadable file, closed JMS connection | Reconnect, bounded retry, record source state |
| Transformer | Missing CSV column, invalid JSON schema, unparseable amount | Classify data error, quarantine payload, fix contract |
| Service activator | Out of stock, rule violation, database transaction failure | Return business outcome or rollback/mark failed appropriately |
| Outbound adapter | HTTP 5xx, broker rejection, missing file write permission | Retry with backoff, reconcile, persist unsent state |

### 8.1. Exceptions and MessageChannel Types

With **DirectChannel**, downstream steps typically run on the sender thread; exceptions from a transformer, service activator, or outbound adapter can propagate back to the upstream endpoint.

With **ExecutorChannel** or **QueueChannel**, errors can occur after the source has already sent the message to the channel. In that case, configure **errorChannel**, retry advice, callbacks, or appropriate endpoint error handlers. Do not assume the default errorChannel preserves every failed message or guarantees retries.

**QueueChannel** by default is not a disk-persisted durable queue. If messages must survive process restarts, use a proper backing store or patterns like transactional outbox.

### 8.2. Retries Can Re-Run the Entire Chain

In a File → Transformer → Service activator → Outbound adapter flow, if the service already saved to the database while the file outbound adapter fails, retrying the whole flow could re-execute business logic. That is why you must determine:

- Which steps are safe to rerun?
- Which steps already caused side effects before the failure?
- Is there a stable **idempotency** key such as orderId/eventId?
- How does source acknowledgment/commit timing relate to target writes?
- Should per-step state or an outbox be persisted to recover only incomplete work?

**Pure data-mapping transformers** are usually easier to retry than service activators or adapters with side effects. Even so, the source and target themselves may redeliver or duplicate operations under their own mechanisms.

### 8.3. Transactions Do Not Automatically Span Every Adapter

OrderService's database transaction does not automatically form a shared transaction across the file system, HTTP, SFTP, or Kafka. Ensuring consistency between business updates and message dispatch typically requires outbox/inbox patterns, idempotent consumers, compensating events, or infrastructure-supported transactions within their actual scope.

Never claim **end-to-end exactly-once** simply because a flow uses Spring Integration, a particular channel type, or a specific adapter.

## 9. Which Component Owns Pollers, Gateways, and Connection Lifecycles?

**Poller** is a coordination mechanism for actively fetching data from a MessageSource or PollableChannel. A poller is not synonymous with an adapter, transformer, or service activator, even though it triggers the corresponding endpoint:

- A file inbound adapter typically uses a poller to scan files.
- An outbound adapter consuming a **QueueChannel** may need a polling consumer to pull messages from the internal queue.
- A message-driven JMS/AMQP/Kafka adapter is typically triggered by a protocol listener container/client.

**Gateway** serves request–reply contracts. When a service activator produces a result for an outbound HTTP gateway to send externally or for an inbound HTTP gateway to return a response, you must evaluate reply channels, timeouts, error flows, and request/reply correlation.

**Connection lifecycle** belongs primarily to the transport layer: SFTP sessions, JDBC pools, Kafka producers/consumers, JMS/AMQP connection factories, and HTTP clients. A service activator using a repository also has its own operational dependencies; pure data-conversion transformers normally do not manage external connection sessions.

## 10. Testing by Responsibility

In a multi-step flow, isolated tests pinpoint failures faster:

| Component | Useful Tests |
| --- | --- |
| File/CSV → Order transformer | Valid data, missing header, invalid numeric format, wrong charset, multi-row input |
| OrderService service activator | Valid/invalid totals, unsafe IDs, business rules, duplicate orders |
| File inbound adapter | Filename filtering, poller selection, partially written files, restarts |
| File outbound adapter | Filename generation, write permissions, missing directory, existing file, output content |
| Full IntegrationFlow | Headers preserved properly, errors caught at the right place, output matches contract |

### 10.1. Manual Experiment with the Example

1. Start the application containing OrderImportConfiguration and OrderService.
2. Place an **order-1001.csv** file with the two sample lines into **./data/inbox**.
3. Once the poller picks up the file, verify **receipt-O-1001.csv** is created in **./data/receipts**.
4. Change the total amount to a negative number to observe the business exception from the service activator.
5. Change the CSV header name to see the error arise in the CSV transformer.
6. Pre-create a receipt file with the same name to observe the outbound error under FileExistsMode.FAIL.

Do not use the mere creation of a file as proof that the entire business process is idempotent. Specifically in this example, FileExistsMode.FAIL only prevents overwriting the same filename; it does not replace order-level deduplication when the source redelivers input.

### 10.2. Component Selection Checklist

When analyzing a new step in a flow, ask yourself:

1. **Does this step read from or write to an external system?** Look for an adapter or gateway with the right communication contract.
2. **Does this step only change data type or structure?** Prefer a transformer.
3. **Does this step apply rules or invoke a business service?** Prefer a service activator.
4. **Does the next step need the external system's response?** Consider a gateway instead of a one-way adapter.
5. **Does this step have side effects and could it be retried?** Design explicit idempotency, rollback, or state recovery.

## 11. Common Misconceptions

**"Transformers and service activators are both handlers, so they are the same."** Both receive messages via endpoints, yet a transformer expresses **data mapping**, whereas a service activator expresses an **action/service**. Both can produce output; the difference lies in intent and responsibility.

**"An outbound adapter will return a value if the target succeeds."** A one-way adapter can receive technical confirmations or throw exceptions, but it does not produce a business reply message like a request–reply gateway.

**"An inbound adapter must return a domain DTO."** Not required. A file source can emit a File, and a broker can emit a String/byte[]/record; transformers normalize data into the internal contract.

**"A service activator must never access a database."** A service activator invokes application services, can call repositories, and participates in business transactions. Distinguish between business persistence and transport-level I/O already handled by a specialized adapter.

**"A transformer is the best place to parse, call an API, and save to DB."** Bundling multiple side effects makes retries, testing, and error observation harder. Separate data transformation from business actions when needed.

**"Every flow always needs all three components."** No. A flow can simply read from an adapter and write to an adapter, or consist purely of internal transformers and service activators without adapters at that endpoint. The diagram is an organizational pattern, not a mandatory rule.

## 12. Self-Check Questions

1. In a flow receiving SFTP files and parsing JSON into Order, why does JSON parsing typically belong to a transformer while SFTP connectivity belongs to an adapter?
2. When a service activator returns a Receipt, why is it still a service activator rather than automatically considered a transformer?
3. How does an outbound Kafka adapter differ from a service activator calling KafkaProducer directly in terms of responsibility and configurability?
4. If a transformer drops the filename header, what consequence can occur at the file outbound adapter?
5. Why can retrying an entire flow cause a service activator to produce duplicate business effects, even when the transformer is completely pure?
6. When a handler must call a REST API and use the response body to make a business decision, which endpoint type should you choose and why?
7. In the CSV example, at which steps should a missing column error and an invalid total amount error occur?
8. When replacing file inbound with Kafka inbound, which parts of the flow can likely be kept and which parts must be re-evaluated?

## Summary

In Spring Integration, **adapters connect external systems**, **transformers normalize and convert messages**, and **service activators trigger business processing**. Choosing the right role clarifies payload/header contracts, where errors originate, and delivery guarantees. A real-world flow often coordinates multiple endpoints, MessageChannels, pollers, or gateways across files, SFTP, HTTP, JMS, AMQP, Kafka, and databases. In implementation, control side effects, retries, idempotency, transactions, and connection lifecycles at the right boundaries instead of cramming everything into a single handler.
