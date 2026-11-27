# Mapping Messages to External Resources or Protocols

## Learning Objectives

After this lesson, you will be able to:

- Explain how Spring Integration translates data between internal **Message** objects and external resources or protocols via **channel adapters** or gateways.
- Distinguish **payload mapping**, **header mapping**, **message conversion/serialization**, and business **transformers**.
- Design inbound/outbound contracts for files, SFTP, HTTP, JMS, AMQP, Kafka, and databases.
- Build a Java DSL IntegrationFlow demonstrating mapping an inbound File into String content and writing a new file whose name is selected via a header.
- Check critical concerns: data types, encoding, schemas, metadata, mapping errors, retries, idempotency, and connection lifecycles.

## 1. Why Map Between Messages and External Systems?

Each system represents data differently. File systems store **files and paths**; HTTP exchanges **methods, URLs, headers, bodies, and status codes**; JMS/AMQP exchange **messages and broker properties**; Kafka exchanges **records with topic, key, value, partition, and offset**; databases store **rows and columns**. Meanwhile, endpoints inside Spring Integration work with one common model:

~~~text
Message<?>
├── payload: primary message data
└── headers: metadata for routing, correlation, and processing
~~~

**Message mapping** is the process of determining which data and metadata on one side correspond to which component on the other side. This happens in both directions:

- **Inbound:** external protocol resource or representation → Message payload/headers → MessageChannel.
- **Outbound:** Message from MessageChannel → payload/headers translated into a resource or outbound protocol command.

For example, when receiving CSV files from a partner, a file inbound adapter may emit a message with a **File payload**, not yet the parsed CSV content. The next step can read the file into a String and parse it into an Order. Conversely, when sending an Order to Kafka, the application must determine **key, value, topic, and serializer** before the producer can emit the record.

~~~mermaid
flowchart LR
    IN["External system<br/>File / HTTP / Broker / DB"] --> A["Inbound adapter<br/>reads and maps input"]
    A --> M1["Message<br/>payload + headers"]
    M1 --> C1["MessageChannel"]
    C1 --> T["Transformer / Service<br/>domain normalization"]
    T --> C2["MessageChannel"]
    C2 --> M2["Message<br/>payload + headers"]
    M2 --> O["Outbound adapter<br/>maps output"]
    O --> OUT["Target system"]
~~~

Channel adapters handle **connection boundaries**; transformers typically handle **in-flow representation changes**; service activators apply **business logic**. An adapter may integrate a specialized converter or header mapper, but that does not mean every transformation belongs inside the adapter.

## 2. Four Mapping Layers to Separate

When a message crosses a system boundary, there are usually four decisions:

| Layer | What Is Mapped | Examples |
| --- | --- | --- |
| **1. Source/target** | Connections and resources being read/written | SFTP directory, HTTP URL, JMS queue, Kafka topic, DB table |
| **2. Payload** | Data wrapped in the Message or sent outbound | File → String; JSON bytes → DTO; DTO → JSON bytes |
| **3. Headers/metadata** | Information for routing, tracing, and control | Filename, Content-Type, correlation ID, Kafka key, message properties |
| **4. Delivery semantics** | When receipt/send is recorded, errors, and reprocessing | Offset commit, ACK, transaction, retry, idempotency |

The fourth layer is easy to overlook. **Mapping the payload correctly is not enough to guarantee correct system behavior.** If data has already been sent externally when the application loses connectivity before receiving confirmation, retrying may send duplicates. Similarly, a channel accepting a message does not mean the target system finished business processing.

### 2.1. Payload Is a Data Type, Not a Business Concept Name

Two sources both providing "orders" can produce different messages:

~~~text
File inbound adapter       Message<File>
HTTP inbound gateway       Message<String> or Message<DTO>
JMS inbound adapter        Message<String / byte[] / DTO / ...>
Kafka inbound adapter      Message<record value depending on deserializer>
JDBC inbound adapter       Message<row/batch data depending on config>
~~~

Do not assume **all adapters return the same payload type** just because the data shares the same business meaning. Payload type depends on the adapter, converter/deserializer, and endpoint configuration. Before wiring a flow to a handler, verify the exact input type the handler actually receives.

### 2.2. Headers Can Be Internal or Protocol-Specific

Headers like **id**, **timestamp**, **replyChannel**, and **errorChannel** serve messaging infrastructure. Other headers describe source/target attributes such as filename, Content-Type, correlation ID, or routing key. However:

- Not every header in a Message has an equivalent field in the target protocol.
- Not all source metadata is automatically copied into headers by the adapter.
- Header names and mapping rules depend on the specific module, version, and configuration.
- Headers holding internal objects such as MessageChannel are usually **unsuitable for serialization** to a broker or HTTP.

Therefore, maintain an **allowlist** of metadata that actually needs to cross trust boundaries instead of blindly copying all MessageHeaders.

## 3. Inbound Mapping: From External Resources into Messages

An inbound channel adapter is triggered by a poller or listener/consumer mechanism, receives data, and sends a Message into a channel. Consider these questions in order:

1. **Source:** does data arrive from a file path, message broker, HTTP request, or database query?
2. **Initial representation:** File, byte array, String, record, or a client library object?
3. **Required conversion:** charset decoding, JSON deserialization, CSV parsing, date/time normalization?
4. **Metadata to retain:** filename, partner source, event ID, correlation ID, receipt time, key/offset?
5. **Recording point:** when read by the adapter, when accepted by the channel, or after business completion?

### 3.1. File and SFTP

With a file inbound adapter, the payload is usually a **File** pointing to the selected file. Information such as filename or path can be used for tracing or deciding processing steps. However, **a File is not the file's contents**:

~~~mermaid
flowchart LR
    F["orders-1001.csv<br/>on disk"] --> IA["File inbound adapter"]
    IA --> MF["Message<File>"]
    MF --> TR["Read UTF-8 + parse CSV"]
    TR --> MO["Message<Order>"]
    MO --> CH["ordersChannel"]
~~~

For SFTP, synchronizing files from the server to local disk, reading remote file contents, or using a streaming message source creates different payload contracts depending on endpoint type and configuration. Do not assume an SFTP inbound adapter always returns a local File or always returns an InputStream.

Agree on how **completed files are handed off**: a half-written file can be picked up by a poller if only a filename filter is used. Conventions such as writing temporary files then renaming, completion markers, or file-age filters often need to be added.

### 3.2. HTTP

HTTP carries **method, URL, path/query parameters, headers, and body**. An inbound endpoint must decide which parts become the payload, which headers map into MessageHeaders, and how to return the response.

Example of an HTTP POST containing JSON:

~~~http
POST /orders HTTP/1.1
Content-Type: application/json
X-Correlation-Id: req-517

{"orderId":"O-1001","totalVnd":150000}
~~~

If the adapter/gateway is configured to receive the body as a String, the payload can be the JSON string. With an appropriate converter, the payload can be a DTO. **X-Correlation-Id does not automatically become an idempotency key**; these two purposes must be specified separately in the contract.

When an HTTP client **needs a response body/status reflecting the flow's outcome**, choose an **inbound HTTP gateway** and configure request–reply with timeouts. If only ingesting one-way events into the system, an inbound adapter may fit depending on the contract and endpoint type.

### 3.3. JMS, AMQP, and Kafka

Brokers carry both message content and protocol metadata:

| Source | Content That Can Become Payload | Metadata to Consider |
| --- | --- | --- |
| JMS | TextMessage, BytesMessage, or converted object | Destination, message ID, correlation ID, properties, redelivery |
| AMQP | Body bytes or converted object | Exchange, routing key, delivery tag, content type, headers |
| Kafka | Value after deserializer, record, or payload depending on adapter | Topic, partition, offset, key, timestamp, consumer group |

A Kafka consumer usually deserializes record values using client configuration before the adapter passes them into Spring Integration. A **Spring Integration poller** is not the same as the Kafka consumer's internal poll loop.

In particular, **offset**, **acknowledgment**, and **correlation ID** have distinct meanings:

- Kafka offset marks a record's position in a partition, not a business ID.
- JMS/AMQP/Kafka ACKs belong to each technology's delivery mechanism.
- Correlation IDs match request/reply pairs or trace flows; they do not inherently prevent duplicate order creation.

## 4. Outbound Mapping: From Messages to External Operations

When sending outbound, an outbound channel adapter consumes a Message from a channel and converts payload and headers into inputs understood by the target client. Examples include:

| Target | Payload/Representation to Send | Routing Information Required |
| --- | --- | --- |
| Local file | String, byte array, File, or payload supported by handler | Directory path, filename, file-exists handling mode |
| SFTP | Content/file per outbound adapter configuration | Remote directory, filename, session/credentials, temp file policy |
| HTTP | Body bytes, String, or DTO via converter | URL, method, Content-Type, auth, and allowed headers |
| JMS | JMS Message via converter | Destination, correlation, and appropriate JMS properties |
| AMQP | Message body and properties | Exchange, routing key, content type, and serializer |
| Kafka | ProducerRecord matching topic/key/value | Topic, key, serializer, partition if needed |
| JDBC/DB | Values for update/insert statements | Table, keys, transaction, schema, and SQL parameters |

**One-way adapters do not return a business reply message to the flow.** If an HTTP response body, JMS request reply, or query result is needed downstream, consider an appropriate gateway or request–reply endpoint. An adapter can still throw exceptions or receive I/O-level confirmations.

### 4.1. Example: One Domain Event Mapped Differently

Suppose the application internally has an event:

~~~json
{
  "eventId": "evt-1001",
  "type": "ORDER_CREATED",
  "orderId": "O-1001",
  "totalVnd": 150000
}
~~~

The same event can be represented differently per target:

- **File:** filename derived from event ID, UTF-8 JSON content, avoiding accidental overwrites.
- **HTTP:** JSON body, Content-Type application/json, idempotency header as agreed with the API.
- **Kafka:** JSON or Avro/Protobuf value per schema; key may be orderId to preserve per-key ordering within a partition on the configured topic.
- **JMS/AMQP:** body via message converter, correlation ID/properties mapped to standard format.
- **Database:** insert row with eventId as unique key and corresponding columns.

This is **one business event**, yet that does not mean all adapters share the same serializer, headers, or confirmation level.

## 5. Header Mapping: What Metadata to Keep and What to Forward?

Systems frequently make the mistake of trying to copy all Spring Message headers into HTTP or broker headers. This can break serialization, leak internal details, or cause unintended routing.

| Header/Metadata | Purpose | Cross-Boundary Notes |
| --- | --- | --- |
| **id, timestamp** | Tracks Message lifecycle | May change when creating new Messages; does not replace business event ID |
| **correlation ID** | Multi-step tracing or request/reply matching | Align name, type, and scope with partners |
| **replyChannel / errorChannel** | Internal reply and error routing | Usually infrastructure references; do not serialize directly |
| **file name** | Naming output files or tracing source | Check for path traversal, invalid chars, collision rules |
| **Content-Type** | Indicates body media type | Must match actual serializer and charset |
| **Kafka key/topic** | Broker record routing | Use module-specific headers/DSL and config; do not assume identical to JMS |
| **JMS/AMQP properties** | Protocol properties and correlation | Header mapper/converter decides which fields pass through |
| **eventId/schemaVersion** | Business identifier and contract version | Explicitly define in payload/header per mutual agreement |

For example, if a Message has **replyChannel** set to a DirectChannel object, serializing that header directly into JSON or Kafka properties makes no sense to external consumers. Conversely, **eventId** and **schemaVersion** may need to live inside the body so the partner processes them accurately.

### 5.1. Allowlists, Denylists, and Data Security

Define clearly:

1. Which headers are **mandatory**.
2. Which headers are **allowed** to cross system boundaries.
3. Which headers need **renaming, type conversion, or value normalization**.
4. Which headers contain sensitive data and must never be logged or sent to brokers.
5. Whether **signing or authentication** is required at the protocol level.

For HTTP, forward only appropriate headers such as Content-Type, correlation ID, or approved business headers. For JMS/AMQP, use the module's header mapper and converter. Never assume that merely seeing a header name on a Spring Message means the client will automatically send it externally.

### 5.2. Source Metadata Is Not Necessarily Target Metadata

Suppose an input file named **orders-1001.csv** is parsed into an Order object and then emitted as a Kafka event:

- The source filename may be useful for auditing.
- The Kafka key should be chosen based on order ID or an appropriate partitioning key.
- The Kafka topic belongs to event routing configuration.
- The Kafka offset will be assigned by the broker for the written record; you cannot arbitrarily assign the filename as the offset.

Proper metadata mapping must rely on **each system's semantics**, not just copying header strings with similar names.

## 6. Converters, Serializers, and Transformers: Which Layer Does What?

Each conversion should sit at the right layer:

| Mechanism | Typically Handles | Example |
| --- | --- | --- |
| Client **Deserializer** | Protocol bytes → client data type | Kafka byte[] → String/record |
| Adapter **Message converter** | Protocol object ↔ payload or message | JMS TextMessage ↔ String; HTTP JSON ↔ DTO |
| **Header mapper** | Protocol properties ↔ MessageHeaders | HTTP headers, JMS/AMQP properties |
| In-flow **Transformer** | Internal payload/message → shape needed downstream | CSV String → Order; Order → JSON DTO |
| Client **Serializer** | Application data → outbound bytes/record | Kafka String/DTO → bytes |

A conversion could potentially happen in multiple places, so **explicitly designate primary ownership**. For instance, if an HTTP message converter already deserialized JSON into a DTO, a downstream transformer should not parse JSON again. If a Kafka source only yields a JSON String, place an appropriate transformer or converter to produce the DTO before the service activator.

### 6.1. Charset, Content-Type, and Schemas

For Strings/bytes, specify the charset (typically UTF-8) when encoding/decoding. Never treat Content-Type as a guarantee of valid content. For example, an application/json header does not prevent a payload from containing malformed JSON.

For JSON, CSV, Avro, or Protobuf, specify:

- Which schema/version is in use.
- Mandatory fields, optional fields, and default values.
- How new fields or deprecated fields are handled.
- How numeric types, dates/times, timezones, and identifiers are converted.
- How to respond when data is incompatible.

For CSV, splitting by commas is insufficient when fields contain commas, quotes, or newlines. For production data, use a compliant CSV parser/encoder library and validate input size.

## 7. Java DSL Example: Mapping an Inbound File to an Outbound File

This example focuses on two boundaries:

1. **Inbound file adapter** reads **./data/inbox** and creates a Message with a File payload.
2. **Transformer** converts file content to a UTF-8 String.
3. **Header enricher** sets an application header **exportFileName** before the payload type changes.
4. **Outbound file adapter** uses the String payload as file content and **exportFileName** as the target filename.

The sample input is a text file **order-1001.txt**. The expected output is **mapped-order-1001.txt** in **./data/outbox**. This example demonstrates mapping mechanics, not a full order-processing system or CSV parser.

~~~mermaid
flowchart LR
    F["./data/inbox/order-1001.txt"] --> IA["File inbound adapter"]
    IA --> MF["Message<File>"]
    MF --> EH["Header enricher<br/>exportFileName"]
    EH --> TR["Transformer<br/>File → String UTF-8"]
    TR --> MS["Message<String><br/>exportFileName"]
    MS --> OA["File outbound adapter"]
    OA --> OUT["./data/outbox/mapped-order-1001.txt"]
~~~

### 7.1. Spring Integration Configuration

In Spring Boot, use the Spring Integration dependency along with the **spring-integration-file** module matching the Spring Boot-managed version.

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
import org.springframework.integration.file.dsl.Files;
import org.springframework.integration.file.support.FileExistsMode;

@Configuration
@EnableIntegration
public class FileMappingConfiguration {

    @Bean
    public IntegrationFlow fileMappingFlow() {
        return IntegrationFlow
            .from(
                Files.inboundAdapter(new File("./data/inbox"))
                    .autoCreateDirectory(true)
                    .patternFilter("*.txt"),
                endpoint -> endpoint.poller(
                    Pollers.fixedDelay(Duration.ofSeconds(5))
                        .maxMessagesPerPoll(5)))

            // While the payload is still a File, we can read the source filename.
            .enrichHeaders(spec -> spec.headerFunction(
                "exportFileName",
                message -> {
                    File source = (File) message.getPayload();
                    return "mapped-" + source.getName();
                }))

            // Payload: File -> String, keeping exportFileName for the next step.
            .transform(File.class, source -> {
                try {
                    return java.nio.file.Files.readString(
                        source.toPath(), StandardCharsets.UTF_8);
                } catch (IOException ex) {
                    throw new UncheckedIOException(ex);
                }
            })

            // The String payload becomes the target file content.
            .handle(Files.outboundAdapter(new File("./data/outbox"))
                .autoCreateDirectory(true)
                .fileNameGenerator(message ->
                    (String) message.getHeaders().get(
                        "exportFileName"))
                .fileExistsMode(FileExistsMode.FAIL))
            .get();
    }
}
~~~

**What happens at each step:**

| Step | Payload | Notable Header | Responsibility |
| --- | --- | --- | --- |
| Inbound adapter | File | Source metadata if provided | Finds/picks up files from directory |
| Header enricher | File | exportFileName = mapped-order-1001.txt | Determines output name per internal contract |
| Transformer | String | exportFileName carried forward via transformer mechanism | Reads UTF-8 text from file |
| Outbound adapter | String | Reads exportFileName | Writes String content to target file |

The **exportFileName** header is application-defined; it is **not a default protocol header**. The outbound adapter can use this header only because fileNameGenerator was configured to read it. This is an important example of **intentional mapping** between MessageHeaders and external resource attributes.

### 7.2. Verifying the Result

1. Start the application with FileMappingConfiguration.
2. Create **./data/inbox/order-1001.txt** containing **Order O-1001 confirmed**.
3. Once the poller picks up the file, verify **./data/outbox/mapped-order-1001.txt** contains the exact UTF-8 content.
4. Create **notes.csv** in inbox: the **patternFilter("*.txt")** filter ignores this file.
5. Pre-place a target file with the same name: **FileExistsMode.FAIL** should fail the write operation instead of silently overwriting.
6. Test a file containing accented Vietnamese characters to verify UTF-8 encoding; evaluate configuration if partners send a different charset.

**Scope of this example:** File inbound only selects files by name filter; it does not yet guarantee the sender finished writing. The sample naming uses File.getName(), whereas user/partner-controlled names require thorough validation of characters, length, path traversal, and overwrite rules. This version does not handle very large files or streaming, nor does it design restart recovery state. FileExistsMode.FAIL only prevents overwriting the same filename; it is not a complete business idempotency solution.

## 8. Contract Example for an Order Event

Suppose a source emits an OrderCreated event and the system must distribute it over HTTP and Kafka. Define the **internal contract** first:

~~~json
{
  "eventId": "evt-1001",
  "eventType": "ORDER_CREATED",
  "schemaVersion": 1,
  "orderId": "O-1001",
  "totalVnd": 150000
}
~~~

Then separate configuration per target system:

| Target | Mapping Rules |
| --- | --- |
| HTTP outbound | UTF-8 JSON as body; Content-Type application/json; URL/method and auth managed by client/endpoint; eventId sent as idempotency key if API supports it per contract |
| Kafka outbound | JSON/Avro/Protobuf as value per serializer; topic routed; key can be orderId for partitioning; eventId/schemaVersion in body or headers per contract |
| File outbound | JSON or CSV body as required; filename generated from validated eventId; consider temp-write then publish |
| JMS/AMQP outbound | Converter maps payload to message body; correlation/properties mapped per broker config |
| Database | eventId as unique key in events table, remaining fields as columns; transactions and deduplication belong to storage contract |

Never infer that a **Kafka producer acknowledgment** means the consumer has processed the order. Similarly, HTTP 202 Accepted does not mean the work has completed. The contract must clarify what level "successfully sent" signifies.

### 8.1. Normalize Once or Multiple Times?

In a large system, you can standardize on a **canonical DTO/domain event** after inbound ingestion:

~~~text
Source A (CSV) ──┐
                 ├──> Canonical OrderEvent ───> JSON HTTP
Source B (Kafka) ┤                         ├───> Avro Kafka
Source C (HTTP) ─┘                         └───> CSV SFTP
~~~

This reduces cross-coupling between sources and targets, though it does not eliminate per-adapter converters. When changing Kafka's wire format, business logic can remain unchanged; serializers, schema registry, headers, and acknowledgment behavior must still be re-verified.

## 9. What Errors Does Bad Mapping Cause?

### 9.1. Data Errors

- **Wrong payload type:** handler receives a File while downstream expects a String or DTO.
- **Wrong charset:** UTF-8 decoded under another charset, corrupting Vietnamese or non-ASCII text.
- **Schema mismatch:** renamed field, missing required field, or incompatible numeric type.
- **Incompatible converter:** producer and consumer use mismatched serializer/deserializer.
- **Wrong header type:** adapter receives a header value that cannot be mapped to a protocol property.
- **Lost metadata:** correlation ID or event ID needed downstream disappears after a custom transformer.

The solution is usually validating data types, schemas, and headers right at the boundary; route malformed data to a quarantine path or structured error report. **Retries cannot fix malformed data.**

### 9.2. Send/Receive Errors

- Unable to connect to SFTP, HTTP, JMS, AMQP, Kafka, or database.
- Target system rejects permissions, payload size, or invalid format.
- Full queue/buffer, producer timeout, or overloaded server.
- File read while sender has not finished writing.
- Request sent but response lost, leaving success status ambiguous.

With **DirectChannel**, downstream exceptions can propagate back to the sending thread. With **ExecutorChannel** or QueueChannel, errors may occur after the producer was told the message entered the channel; you need **errorChannel**, error handlers/advice, or corresponding callbacks. Do not assume the default errorChannel automatically retries or durably persists failed messages.

~~~mermaid
flowchart TD
    M["Message at boundary"] --> V{"Payload / headers / schema valid?"}
    V -- "No" --> BAD["Contract error: quarantine or fix data"]
    V -- "Yes" --> IO["Adapter calls external resource"]
    IO --> R{"I/O outcome"}
    R -- "Success" --> OK["Record progress"]
    R -- "Transient error" --> RET["Bounded retry with backoff"]
    R -- "Unknown state" --> REC["Reconciliation + idempotency"]
    R -- "Unrecoverable error" --> ERR["Quarantine / alert"]
    RET --> IO
~~~

## 10. Delivery, Idempotency, and Transactions After Mapping

Correct mapping only proves data is **structurally valid**. Reliability still depends on delivery semantics:

1. **Source emitted data:** does not mean the inbound adapter received it.
2. **Inbound adapter sent Message to channel:** does not mean the service activator completed.
3. **Outbound adapter sent request:** does not mean the target acknowledged or finished processing.
4. **Target acknowledged at protocol level:** does not mean the final receiver completed business logic.

For instance, order O-1001 was saved to the database, but the process crashed before publishing the Kafka event. On restart, the event could be replayed or missed if progress state is not persisted. Patterns like **transactional outbox**, **idempotent consumers**, and stable business keys reduce data loss and duplication risks.

Keys like **eventId** or **partnerId + orderId** must stay stable across retries. Do not rely on each message's newly generated MessageHeaders.ID as sole proof that two deliveries represent two distinct business operations. Nor should you claim **end-to-end exactly-once** when the file system, HTTP, broker, and database do not participate in a shared transaction.

### 10.1. Connection Lifecycle Impacts Mapping

Mapping and I/O cannot be completely separated in production operations:

- **SFTP:** session and remote path must exist; reconnect/retry can re-read files.
- **HTTP:** client configuration, content negotiation, auth, timeouts, response status.
- **JMS/AMQP:** connection factory, listener container, converter, ack/requeue.
- **Kafka:** serializer/deserializer, consumer group, offset, producer acknowledgment.
- **Database:** JDBC connection pool, transaction isolation, unique constraints.
- **File:** permissions, path, size, charset, file publication policy.

When a source or target upgrades versions, re-verify the **wire-format contract**, connector configuration, and retry behavior. A change affecting only payload type can break downstream handlers even while connections remain healthy.

## 11. Testing Mapping Systematically

A useful test suite should focus on real boundaries:

| Item | Specific Checks |
| --- | --- |
| Payload type | Inbound produces expected type; transformers and handlers accept declared types |
| Content | Strings/bytes use proper charset; JSON/CSV match schema and escaping |
| Headers | Required headers attached, preserved through transformers, and mapped outbound accurately |
| Filename/address | Filenames cannot escape directory; topics, URLs, destinations are valid |
| Send outcome | Verify actual file/record/request, not only channel send return value |
| Data errors | Bad schema, null values, missing headers, oversized payloads |
| Connection errors | Timeouts, unavailable broker/repository, missing permissions |
| Retries | Do resends retain eventId and avoid duplicate side effects? |
| Restarts | Receive/send state and backlog recover per policy |
| Security | Disallowed headers are not leaked outbound; logs hide sensitive payloads |

A clean testing strategy keeps **unit tests for transformers** and separate integration tests for adapters. Pure data transformers can be tested with input/output objects. Adapters must be tested against real resources or appropriate test doubles, because a valid schema alone does not prove transport works.

## 12. Common Mistakes

**Confusing a Message with raw protocol data.** Message is an internal payload/headers model; converters/adapters are needed to turn it into files, HTTP requests, or broker records.

**Assuming headers copy automatically across every protocol.** Each adapter has its own header mapping and limits; define an allowlist of permitted headers and conversion rules.

**Parsing business data inside every adapter.** Boundary converters can be used, but keep domain normalization separated from transport concerns for testability and swapping sources.

**Treating serializers and transformers as identical.** Serializers convert data to/from wire format; transformers convert in-flow representations for downstream contracts. They can work together, but designate clear ownership for each conversion.

**Using correlation ID in place of idempotency key.** Correlation pairs requests/replies and supports tracing; preventing duplicate business actions requires a stable key and receiver-side checks.

**Treating broker ACK as final business processing.** ACKs are protocol-scoped; the consumer may not have executed business logic yet.

**Ignoring schema versions.** An incompatible new event can break older consumers even when connections and topics remain unchanged.

**Believing filename filters guarantee file integrity.** A file with a matching extension may still be mid-write or contain malformed data.

## 13. Self-Check Questions

1. Why does a File inbound adapter typically create a Message with a File payload, while parsing CSV into Order belongs in a transformer?
2. A Message has a replyChannel header holding an internal object. Should that header be forwarded verbatim into Kafka or JMS properties? Why?
3. If switching from HTTP JSON to Kafka Avro, which mapping layers must be reviewed, and which part of the domain model can remain intact?
4. When a serializer fails due to an incompatible schema, will retrying fix it? How should it be handled?
5. Why should a Kafka offset not replace a business eventId?
6. In the Java DSL example, what tells the outbound file adapter that the filename is mapped-order-1001.txt?
7. If a message was sent to an ExecutorChannel but the output file has not appeared yet, can you conclude the adapter failed solely from the send result?
8. Why can retrying after an HTTP timeout create duplicate transactions, even when payload and headers were mapped accurately?
9. Which tests help catch charset bugs, header mapping mistakes, and duplicate filename handling?

## Summary

**Mapping messages to external resources or protocols** is the translation contract between a **Spring Integration Message's payload/headers** and the data, metadata, and delivery semantics of connected systems. Inbound adapters bring data into a MessageChannel; outbound adapters translate messages into external operations. Converters, serializers, header mappers, and transformers address distinct layers of conversion. When building flows for files, SFTP, HTTP, JMS, AMQP, Kafka, or databases, align payload types, schemas, charsets, metadata, acknowledgment points, retries, idempotency, and connection lifecycles together. Accurate mapping lets systems understand data; sound delivery design ensures data is processed safely.
