# Checking Headers and Payloads in Spring Integration Adapters

## 1. Objectives and Lesson Context

In **Spring Integration**, data does not simply pass from one Java function to another: a **message** carries both a **payload** (business content) and **headers** (metadata for routing, transformation, replies, tracing, and error handling). When using inbound/outbound adapters, gateways, pollers, and MessageChannels to integrate files, SFTP, HTTP, JMS, AMQP, Kafka, or databases, a valid payload paired with wrong headers can still cause severe failures: publishing to the wrong topic, losing correlation, writing the wrong filename, missing a content type, or dropping request identity.

The **"Checking Headers and Payloads"** lesson belongs to the **Testing** chapter of the **Spring Integration Adapters** module. The goal is not merely writing `assertEquals("OK", message.getPayload())`, but designing and verifying an **inbound–outbound message contract**, identifying inspection boundaries for each adapter, and knowing which conclusions are actually supported by test evidence.

After this lesson, you will be able to:

- Distinguish `Message<?>`, payloads, `MessageHeaders`, and headers defined by the framework, adapters, or applications.
- Select the right observation points across `DirectChannel`, `QueueChannel`, gateway replies, error channels, and asynchronous flows.
- Write JUnit 5 unit tests, flow tests, and adapter integration tests checking **payload type, content, headers, count, ordering, correlation, and errors**.
- Test metadata mapping between Spring messages and File/SFTP/HTTP/JMS/AMQP/Kafka/DB without assuming protocols share identical header names.
- Catch dropped headers during transformations, type/encoding mismatches, cross-tenant data leaks, or unintended propagation of sensitive data into messages.
- Design reliable tests with bounded timeouts, isolated fixtures, and target-system assertions whenever the contract requires side effects.

**Code scope:** Examples use modern Java, Spring Integration Java DSL, JUnit 5, and Spring Test illustratively. Exact headers emitted by adapters vary by module, mapper configuration, and version; verify the API for your exact version before applying.

## 2. What Is a Message Contract?

Conceptually, a message in Spring Messaging looks like this:

~~~text
Message<T>
 ├─ payload: T
 │   └─ business content or intermediate representation
 └─ headers: Map<String, Object>
     ├─ Spring-managed metadata
     ├─ transport/adapter metadata
     └─ application-defined business metadata
~~~

Example of an order event entering the system via File/SFTP:

~~~text
Payload:
  OrderEvent(orderId="ORD-42", amountMinor=12500, currency="VND")

Headers:
  correlationId = "corr-2026-42"
  sourceSystem  = "sftp-partner-a"
  tenantId      = "tenant-a"
  eventType     = "order.created"
  schemaVersion = "1"
  sourceFile    = "orders-42.csv"
~~~

The **payload** answers: *"What data needs to be processed?"* **Headers** answer the supporting questions: *"Which source? Which handler? Where should it go? Who gets the reply? Does it belong to the same request? What format is it in?"*

Not every header is trustworthy data. For instance, a `tenantId` arriving from an external HTTP request must be cross-checked against an authenticated identity rather than used directly to select a tenant database or internal resource. Message tests must verify the **origin, presence, data type, and usage rules** of headers.

### 2.1. Payloads and Headers Do Not Replace Each Other

| Information | Where Should It Live? | Why |
|---|---|---|
| `orderId`, amount, items | Payload or schema-defined DTO | Core business data |
| Cross-flow `correlationId` | Controlled business header; optionally copied into event envelope for durability | Traces across adapters, gateways, and logs |
| Event type / schema version | Payload envelope and/or contract header | Tells consumers how to interpret data |
| Filename / path | Adapter header or normalized payload metadata | Supports file routing and auditing |
| Kafka key / routing key | Transport header or record configuration | Controls partitioning/destination |
| Reply / error channel | Internal messaging header if used by flow | Coordinates replies/errors |
| Password, access token, private key | **Never place in business headers for propagation** | Risk of leaking via message bus/logs/traces |
| Tenant / access permissions | Derived from verified security context with explicit mapping | Never trust arbitrary caller claims |

**Design the contract before testing**, then decide which headers are mandatory, which are optional, and which transformations are allowed to strip them.

## 3. Header Layers to Distinguish

### 3.1. Spring Framework-Managed Headers

`org.springframework.messaging.MessageHeaders` defines standard keys such as:

- `MessageHeaders.ID`: identifier of a **message instance**.
- `MessageHeaders.TIMESTAMP`: message creation timestamp per framework mechanics.
- `MessageHeaders.CONTENT_TYPE`: MIME/content type when set.
- `MessageHeaders.REPLY_CHANNEL`: reply channel in certain request–reply flows.
- `MessageHeaders.ERROR_CHANNEL`: error channel when supported by components/flows.

**Do not assume** every message carries all of these headers. `replyChannel` and `errorChannel` usually appear only when flows/gateways need them. Framework-managed IDs and timestamps can be regenerated whenever an endpoint creates a new message, so never use them as durable cross-system business keys.

### 3.2. Spring Integration and Adapter Headers

Spring Integration adds module-specific metadata groups, such as:

- **File:** filename, original filename, relative path; check constants in `FileHeaders` and your version's header mapper.
- **SFTP:** remote directory, remote filename, host/transport metadata when set/configured by the adapter.
- **HTTP:** HTTP request/response headers and status via `HttpHeaders`, header mappers, or message converters.
- **JMS:** correlation ID, destination, message ID, delivery mode, redelivered flag, etc., per JMS mapping.
- **AMQP/RabbitMQ:** exchange, routing key, delivery tag, consumer queue, and metadata per adapter mapping.
- **Kafka:** topic, partition, key, offset, timestamp, and producer/consumer metadata per mapper.
- **JDBC/JPA:** payload is typically a row/DTO while business metadata is constructed by the flow; no universal header set applies to every schema.

**Not all adapters emit the same header names or preserve every header by default.** One transport's conventions do not automatically apply to another. For specific metadata, use module constants where available and test **real messages** at the exact boundary.

### 3.3. Application-Defined Custom Headers

~~~java
Message<String> message = MessageBuilder
        .withPayload("order-42")
        .setHeader("correlationId", "corr-42")
        .setHeader("tenantId", "tenant-a")
        .setHeader("eventType", "order.created")
        .setHeader("schemaVersion", "1")
        .build();
~~~

These headers may pass through several endpoints in a flow, yet **their preservation must never be guessed**. Whenever a transformer builds a new message, a router branches, or an adapter switches transports, tests must verify required headers remain intact as designed.

## 4. Architecture for Testing Headers and Payloads Across Adapters

~~~mermaid
flowchart LR
    EXT["File / SFTP / HTTP / JMS / AMQP / Kafka / DB"] --> IN["Inbound adapter"]
    IN --> IC["inputChannel"]
    IC --> MAP["Transform / filter / route / enrich"]
    MAP --> OC["outputChannel"]
    OC --> OUT["Outbound adapter / gateway"]
    OUT --> TARGET["Target system"]
    IC -. "test observation" .-> T1["Check inbound payload/headers"]
    OC -. "test observation" .-> T2["Check transformed message"]
    TARGET -. "integration test" .-> T3["Check protocol/side effects"]
    MAP -. "error" .-> ERR["Error flow / recovery"]
~~~

Testing layers answer **different questions**:

| Layer | How to Test | What Can Be Concluded |
|---|---|---|
| Unit mapper | Invoke mapper with DTO/`Message<?>` | Data/header conversion logic executed by the mapper |
| Channel/flow test | Send message to channel, receive on terminal channel | Wiring/transforms/routing work in the test context |
| Adapter contract test | Create file/HTTP request/broker record then receive message | How the adapter maps transport ↔ Spring message |
| Outbound adapter test | Send real message through handler using mock server/broker/DB | Mapping to request/record/file and handling responses |
| End-to-end test | Run both inbound and outbound against test infrastructure | Business outcomes observed across the entire chain |

**Never equate** `inputChannel.send(...) == true` with HTTP POST or broker publish completion. When a handler/transport is asynchronous, the message was only accepted for further processing. When verifying side effects, check **at the target**.

## 5. Selecting the Right MessageChannel Observation Point

| Channel | Characteristics | How to Assert |
|---|---|---|
| `DirectChannel` | Dispatches synchronously to one selected subscriber by default | Assert handler/reply after `send()` when flow is genuinely synchronous |
| `QueueChannel` | `PollableChannel` backed by a queue | Call `receive(timeout)` and inspect payload/headers |
| `PublishSubscribeChannel` | Fans out to multiple subscribers; may use an executor | Assert each subscriber/branch; do not confuse with competing consumers |
| `ExecutorChannel` | Handler runs on an executor, typically asynchronous | Wait with latch/await/queue using a timeout |
| `RendezvousChannel` | Synchronous sender/receiver handoff | Test send/receive timeouts |
| `PriorityChannel` | Messages received by priority | Verify priority ordering if part of contract |
| Reactive channel | Subscription/backpressure | Use appropriate reactive testing tools |

**Critical warning:** Attaching an extra test subscriber to a production `DirectChannel` does not create a copy for the test. It can become a **competing consumer**, starving the real handler of messages. To observe without stealing messages, use a properly configured wire tap/monitoring channel or a dedicated terminal output in the test context.

### 5.1. Why Is QueueChannel Commonly Used in Tests?

`QueueChannel` lets tests receive outputs with bounded timeouts without fixed sleeps:

~~~java
Message<?> actual = observedOutput.receive(1000);
assertNotNull(actual, "No message received within test timeout");
~~~

However, if **another consumer** reads `observedOutput`, the test may miss messages. Isolate output channels, drain queues between tests, and use correlation IDs to prevent cross-test mix-ups.

### 5.2. Do Not Over-Infer from an Empty Queue

`observedOutput.receive(0) == null` means only that **at that instant** no message is waiting. With executors/pollers, messages may arrive later. When a contract demands "no output," control completion timing, deadlines, or downstream state.

## 6. Complete Example: JUnit 5 Checking Payloads and Headers Across a Flow

An example flow receives a `String` from a simulated adapter source, normalizes it, and sends the output to a `QueueChannel`. This verifies the **channel message contract** without external infrastructure.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;

@Configuration
@EnableIntegration
class MessageContractConfig {

    @Bean
    MessageChannel adapterInput() {
        return new DirectChannel();
    }

    @Bean
    PollableChannel observedOutput() {
        return new QueueChannel();
    }

    @Bean
    IntegrationFlow normalizeFlow() {
        return IntegrationFlow.from("adapterInput")
                .<String, String>transform(String::trim)
                .channel("observedOutput")
                .get();
    }
}
~~~

Corresponding test:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(MessageContractConfig.class)
class MessageContractTest {

    @Autowired
    @Qualifier("adapterInput")
    MessageChannel adapterInput;

    @Autowired
    @Qualifier("observedOutput")
    PollableChannel observedOutput;

    @Test
    void normalizesPayloadButPreservesBusinessHeaders() {
        Message<String> incoming = MessageBuilder
                .withPayload("  ORD-42  ")
                .setHeader("correlationId", "corr-42")
                .setHeader("tenantId", "tenant-a")
                .setHeader("sourceSystem", "sftp")
                .build();

        assertTrue(adapterInput.send(incoming));

        Message<?> actual = observedOutput.receive(1000);
        assertNotNull(actual);

        assertInstanceOf(String.class, actual.getPayload());
        assertEquals("ORD-42", actual.getPayload());
        assertEquals("corr-42",
                actual.getHeaders().get("correlationId"));
        assertEquals("tenant-a",
                actual.getHeaders().get("tenantId"));
        assertEquals("sftp",
                actual.getHeaders().get("sourceSystem"));

        // Synchronous flow with one output: queue must be empty now.
        assertNull(observedOutput.receive(0));
    }
}
~~~

**What the test proves:** `DirectChannel` dispatched the message, the transformer normalized the `String`, and required business headers survived to the output. This is a **flow test** with a real Spring context.

**What remains unproven:** whether SFTP actually downloaded a file, a broker acknowledged a publish, or HTTP outbound sent body/headers to a server. Those require dedicated adapter and target-system tests.

### 6.1. Avoid Overly Loose Assertions

~~~java
assertNotNull(observedOutput.receive(1000));
~~~

This only proves **a message arrived**. It could carry the wrong payload, lack a tenant, have the wrong correlation, or come from another test. At a minimum, assert **type, business values, and critical headers**.

### 6.2. Avoid Overly Strict Assertions

Do not default to:

~~~java
assertEquals(incoming.getHeaders(), actual.getHeaders());
~~~

The entire headers map can differ because the framework generates new IDs/timestamps or endpoints manage metadata. Compare only the **contract header set**, plus assertions ensuring dangerous headers are absent where needed.

## 7. Unit Testing MessageBuilder and Payload Types

Before sending messages through adapters, verify payload and header construction:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.util.MimeTypeUtils;

class MessageConstructionTest {

    @Test
    void buildsAContractWithStableBusinessIdentifiers() {
        Message<String> message = MessageBuilder
                .withPayload("{\"orderId\":\"42\"}")
                .setHeader("eventId", "order-created-42")
                .setHeader("correlationId", "corr-42")
                .setHeader(MessageHeaders.CONTENT_TYPE,
                           MimeTypeUtils.APPLICATION_JSON)
                .build();

        assertEquals("{\"orderId\":\"42\"}", message.getPayload());
        assertEquals("order-created-42",
                message.getHeaders().get("eventId"));
        assertEquals("corr-42",
                message.getHeaders().get("correlationId"));

        assertNotNull(message.getHeaders().getId());
        assertNotNull(message.getHeaders().getTimestamp());
    }
}
~~~

**Note:** the example builds JSON as a `String`; setting the content-type header **does not automatically convert payloads into `byte[]` or DTOs**. Encoding/decoding is performed by configured converters, transformers, or adapters.

### 7.1. Type Mismatches Must Be Tested Explicitly

If a handler expects `OrderEvent` yet receives a raw `String` or `byte[]`, tests must prove either:

- The right converter runs, or
- The handler rejects the payload with a defined error.

**Never bypass failures by casting data blindly.** A `String` containing valid JSON does not mean the Java object already has type `OrderEvent`.

### 7.2. MessageHeaders and Immutability

`MessageHeaders` is exposed as a metadata structure that should not be mutated in place via the returned map. To add or replace headers, build a new message with `MessageBuilder` or use an appropriate enricher/transformer.

~~~java
Message<String> original = MessageBuilder
        .withPayload("ORD-42")
        .setHeader("eventType", "order.created")
        .build();

Message<String> revised = MessageBuilder.fromMessage(original)
        .setHeader("correlationId", "corr-42")
        .build();

assertEquals("ORD-42", revised.getPayload());
assertEquals("order.created",
        revised.getHeaders().get("eventType"));
assertEquals("corr-42",
        revised.getHeaders().get("correlationId"));
~~~

Do not try mutating header maps with `put`: contracts are verified on the **message returned after transformation**, not in-place metadata mutation.

## 8. Testing Header Propagation Across Transformers, Filters, and Enrichers

Across multiple endpoints, a message may change payloads or gain metadata. Define **what must be kept**, **what must change**, and **what must be removed**.

| Endpoint | Behavior Worth Testing | Example |
|---|---|---|
| Transformer | New payload type/content; required business headers still present | CSV String → `OrderEvent` |
| Header enricher | New headers computed accurately; trusted headers not overwritten outside policy | Add `eventType` |
| Filter | Valid messages proceed; dropped messages cause no side effects | Amount > 0 |
| Router | Routes to right channel/destination; never trusts arbitrary sender headers | `tenantId` → tenant channel |
| Splitter | One input → multiple outputs; matching correlation/sequence | Batch of three orders |
| Aggregator | Groups by correlation; emits only when completion criteria met | Reassemble batch |
| Bridge | Message forwarded to right output channel | No critical headers lost |
| Gateway | Request/reply mapping, reply channel, and timeout | HTTP/gRPC/JMS request–reply |

### 8.1. Testing That Transformers Do Not Accidentally Drop Correlation

When a transformer returns only a new payload, many Spring Integration endpoints propagate headers from request to reply per configuration. However, never **rely on guesswork** when custom transformers construct new `Message<?>` objects or header filters are present.

Example expected behavior:

~~~text
Input:
  payload = "  ORD-42  "
  correlationId = "corr-42"
  tenantId = "tenant-a"

After transformation:
  payload = "ORD-42"
  correlationId = "corr-42"
  tenantId = "tenant-a"
~~~

Tests must assert all three fields. If a built-in transformer is swapped for a custom function, the test catches dropped headers immediately.

### 8.2. When Should Headers Be Removed?

Preserving every header is not always safe. For example, an inbound HTTP adapter may receive an `Authorization` header from a client, while outbound messages sent to Kafka **must not** carry that token. The contract must specify which headers to redact/drop before crossing another boundary.

Illustrative assertion:

~~~java
Message<?> actual = output.receive(1000);
assertNotNull(actual);
assertNull(actual.getHeaders().get("Authorization"));
assertEquals("corr-42",
        actual.getHeaders().get("correlationId"));
~~~

Align header names with your specific system; `Authorization` here is an **illustrative application header**, not a guarantee that every adapter maps that exact name verbatim.

## 9. Mandatory, Optional, and Defaulted Headers

A sound contract classifies headers into three groups:

1. **Mandatory:** rejected or errored if missing. E.g., `eventId` for idempotency, verified `tenantId` before writing multi-tenant data.
2. **Optional:** processed cleanly when absent per an explicit rule. E.g., `sourceFileName` when an event arrives via HTTP.
3. **Safely defaulted:** e.g., `schemaVersion` defaulting only to a defined legacy version for old data; never escalate privileges or alter targets by default.

Test matrix:

| Field | Present | Missing | Wrong Type | Invalid Value |
|---|---|---|---|---|
| `correlationId` | Keep and propagate across flow | Generate per policy or reject | Reject if contract expects String | Too long/duplicate/contains PII → handle |
| `tenantId` | Compare with verified identity | Reject on tenant-scoped resources | Reject | Unauthorized tenant → reject |
| `schemaVersion` | Select matching converter | Default only if contract permits | Reject | Unknown version → reject/DLQ |
| `eventType` | Router selects branch | Error/reject | Reject | Never route to privileged default branch |
| `sourceFileName` | Use for audit/target name after validation | Controlled fallback | Reject | Block traversal / unauthorized paths |

**Never test "missing header" by letting the test wait until an infinite timeout.** Invalid inputs must yield a defined outcome: synchronous exception, reject output, `ErrorMessage`, or dead-letter flow.

## 10. Testing Content Types, Charsets, JSON, and Binary Payloads

A payload can represent the same business data in different forms:

~~~text
Java DTO  -> JSON String -> UTF-8 byte[] -> transport record
   ^                               |
   |                               v
  mapper                      converter/serializer
~~~

Place assertions at the **exact boundary**:

| Boundary | Assertion |
|---|---|
| DTO after parser | Java type, required fields, accurate values |
| JSON String after serializer | Valid JSON, schema, field names, and types |
| `byte[]` before transport | Exact byte encoding/size/content |
| HTTP request | `Content-Type`, charset if applicable, actual sent body |
| JMS/AMQP/Kafka record | Converter/serializer and transport metadata |
| File/SFTP output | Real file contents after write, line endings/encoding per contract |

### 10.1. Byte Arrays Cannot Be Compared with toString()

~~~java
byte[] expected = "Xin chào".getBytes(StandardCharsets.UTF_8);
byte[] actual = (byte[]) result.getPayload();

assertArrayEquals(expected, actual);
~~~

Calling `actual.toString()` on a byte array does not inspect content. For text payloads, decode with the agreed charset; for binary payloads, assert bytes/hashes/lengths per contract.

### 10.2. JSON: Assert Schemas and Fields Regardless of Key Order

~~~java
JsonNode tree = objectMapper.readTree(
        (String) result.getPayload());

assertEquals("ORD-42", tree.path("orderId").asText());
assertEquals("VND", tree.path("currency").asText());
assertEquals(12500, tree.path("amountMinor").asLong());
~~~

`objectMapper` is a Jackson `ObjectMapper` from the test fixture and payload is assumed to be a `String`. If payload is `byte[]`, use the byte-array overload. For monetary values, use **integer minor units** or exact decimals per contract rather than floating-point comparisons when precision matters.

### 10.3. Content Type Must Match Payload

For instance, a header claiming `application/json` when the body is CSV breaks converters/consumers. Complete tests assert `MessageHeaders.CONTENT_TYPE`, actual payload, and target request/record (for transport adapters with dedicated header mappers).

## 11. Testing File Inbound: From File to Business Payload

A File inbound adapter reads files from a directory and emits messages with `java.io.File` payloads. Reading bytes, parsing CSV, or mapping to DTOs typically happens in subsequent endpoints. **Tests must distinguish payloads on the source channel from payloads after transformers.**

Scenario:

~~~text
Input directory:
  orders-42.csv: orderId,total
                 ORD-42,12500
  README.txt: file not processed

File inbound adapter:
  pattern *.csv
  output Message<File>

CSV parser:
  output Message<OrderEvent>
  headers sourceFileName="orders-42.csv", eventType="order.created"
~~~

### 11.1. Testing FileReadingMessageSource Independently

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.integration.file.FileReadingMessageSource;
import org.springframework.integration.file.filters.SimplePatternFileListFilter;
import org.springframework.messaging.Message;

class FilePayloadContractTest {

    @TempDir
    Path inbox;

    @Test
    void fileSourceCreatesFilePayloadFromMatchingPath() throws Exception {
        Files.writeString(
                inbox.resolve("orders-42.csv"),
                "orderId,total\nORD-42,12500\n",
                StandardCharsets.UTF_8);

        Files.writeString(
                inbox.resolve("ignore.tmp"), "ignored",
                StandardCharsets.UTF_8);

        FileReadingMessageSource source = new FileReadingMessageSource();
        source.setDirectory(inbox.toFile());
        source.setFilter(new SimplePatternFileListFilter("*.csv"));
        source.afterPropertiesSet();

        Message<File> found = source.receive();
        assertNotNull(found);
        assertInstanceOf(File.class, found.getPayload());
        assertEquals("orders-42.csv", found.getPayload().getName());
        assertTrue(found.getPayload().isFile());
    }
}
~~~

This test proves only **the file source and filename filtering**, not schedulers/pollers, custom headers, or downstream parsing.

### 11.2. Verifying Authentic File Source Headers

If a transformer sets `sourceFileName` from `File.getName()`, tests should verify:

- The header comes from **actual file metadata**, not an arbitrary user-supplied header.
- The value is safely normalized and sufficient for tracing.
- Paths outside allowed directories are blocked.
- Full directory paths can be operationally sensitive; log only if necessary and permitted.

If the adapter provides module-specific file headers, use constants from `FileHeaders` and assert **directly at the adapter output**. If a custom transformer renames the header, downstream channel tests must check that custom name; **never assume headers propagate unchanged across all endpoints**.

### 11.3. Filters and Duplicates

`SimplePatternFileListFilter("*.csv")` checks filenames; it **does not guarantee accept-once**. If each file must be processed once, configure an appropriate filter/metadata store and test:

1. First poll emits one message.
2. Subsequent polls do not re-emit outside policy.
3. Restarting the endpoint with a persistent metadata store behaves as specified.
4. Modified files or duplicate filenames follow the contract.

Testing only headers/payloads on the first poll cannot prove deduplication or lifecycle behavior.

## 12. Testing SFTP Inbound/Outbound: Remote Metadata and Real Content

SFTP over SSH can stage remote files locally or stream data depending on adapter/streaming mode. A test inspecting only a `File` payload can miss remote directory bugs, partial transfers, or reading files mid-upload.

Key metadata to check:

| Business Field | Source | Assertion |
|---|---|---|
| `sourceSystem` | Trusted adapter/flow configuration | Matches approved SFTP partner |
| Remote filename/path | Adapter or synchronizer | Right directory/filename, no traversal |
| Local temporary filename | Staging/synchronizer | Incomplete files never marked complete |
| File content/size/hash | Remote and local files | Readback matches after sync |
| `correlationId` | Business file ID or event metadata | Links file to downstream operations |
| Timestamp/modified info | Adapter-exposed metadata (if any) | Handles timezones, clock skew, freshness per policy |

**There is no single uniform SFTP header set across all adapter modes.** SFTP synchronizers, inbound streaming adapters, and outbound adapters can attach different metadata. Test directly on the relevant channel using your version's module constants/APIs.

### 12.1. Inbound SFTP

Using an isolated SFTP server/container, create a remote file and verify:

- File downloads with exact bytes (especially UTF-8 and line endings).
- Post-parse message has schema-valid payload and accurate origin headers.
- Temp/partial uploads are never treated as ready files.
- Retries/reconnects do not emit unintended duplicate business events.
- Invalid host keys or credentials are rejected; never disable SSH verification to make tests pass.

### 12.2. Outbound SFTP

Example pre-outbound message:

~~~text
payload: byte[] containing order CSV
headers:
  remoteDirectory = "/partners/a/outgoing"
  targetFileName   = "orders-42.csv"
  eventId          = "order-export-42"
~~~

The names above are **illustrative application contracts**, not guaranteed default SFTP module headers. Tests must verify the **adapter's configured mapping** of these values, and against the test server confirm:

- Real remote file appears in the target directory.
- Exact bytes/charset match.
- Names cannot escape allowed directories.
- Temporary files and renames complete per contract.
- Upload failures, network timeouts, and retries never report false success.

**A pre-outbound collector proves only that the message was prepared**, not that the remote file was written.

## 13. HTTP Inbound: From Request Headers and Body to Message

HTTP inbound gateways accept external requests and construct Spring messages. Example contract:

~~~http
POST /api/orders HTTP/1.1
Content-Type: application/json
X-Correlation-Id: corr-42
X-Tenant-Id: tenant-a

{"orderId":"ORD-42","amountMinor":12500}
~~~

Tests must verify:

1. Request method, URL, and content type route properly.
2. HTTP message converters deserialize body into the expected representation/DTO.
3. Header mapper **forwards only permitted headers**.
4. Correlation keeps the right name and type in the Spring message.
5. Tenant is verified against security context/policy, **never trusting raw self-asserted headers alone**.
6. Gateway returns matching reply/status/body; missing replies or timeouts behave deterministically.
7. Invalid JSON, wrong content types, missing auth, or oversized headers are handled cleanly.

**Do not assume** `X-Correlation-Id` in an HTTP request automatically becomes a custom `correlationId` header on the Spring message. A mapper/enricher/transformer or explicit logic is needed. Base tests on **actual post-mapping header names**.

### 13.1. Testing HTTP Contracts with Mock Clients/Servers

For Spring MVC-backed HTTP inbound endpoints, send requests via `MockMvc` or an HTTP test client instead of calling transformers directly. Assertion idea:

~~~java
mockMvc.perform(post("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .header("X-Correlation-Id", "corr-42")
        .content("{\"orderId\":\"ORD-42\",\"amountMinor\":12500}"))
    .andExpect(status().isAccepted());

// Then collect message on test channel with a timeout.
Message<?> received = observedOrders.receive(1000);
assertNotNull(received);
assertEquals("corr-42", received.getHeaders().get("correlationId"));
~~~

This is an **illustrative snippet**: the test endpoint must configure the HTTP inbound gateway/controller, contract response status, header mapper, `mockMvc`, and `observedOrders`. Not every Spring Integration gateway automatically creates `/api/orders` or returns status 202. Tests must provide real flows matching the example.

### 13.2. Security Headers on HTTP Inbound

A message can accidentally inherit `Authorization` or cookies if an adapter maps all request headers. Test an **allowlist policy**: downstream receives only needed fields, never leaking raw bearer tokens to Kafka or audit logs. Dropping a single case-sensitive header name is insufficient if the HTTP layer handles headers case-insensitively; verify mappers and normalization thoroughly.

## 14. HTTP Outbound: Spring Headers Do Not Automatically Become HTTP Headers

Suppose a flow sends:

~~~text
Message payload: {"orderId":"ORD-42"}
Message headers:
  correlationId = corr-42
  contentType   = application/json
  tenantId      = tenant-a
~~~

An outbound HTTP adapter/gateway must control:

- HTTP method/URI and allowed destination list.
- Body serializer and content type.
- **Header mapper** translating internal headers to expected HTTP header names.
- Authorization sourced from secure credential management rather than copying arbitrary input tokens.
- Response status/body/error handling per one-way or request–reply contract.

### 14.1. Verifying with a Mock HTTP Server

For an outbound handler using `RestTemplate` on a compatible version, `MockRestServiceServer` inspects requests without touching the Internet:

~~~java
MockRestServiceServer server =
        MockRestServiceServer.bindTo(partnerRestTemplate).build();

server.expect(requestTo(
            "https://partner.example/api/orders"))
    .andExpect(method(HttpMethod.POST))
    .andExpect(header("X-Correlation-Id", "corr-42"))
    .andExpect(content().json("{\"orderId\":\"ORD-42\"}"))
    .andRespond(withSuccess(
            "", MediaType.APPLICATION_JSON));

// Trigger outbound IntegrationFlow configured with this exact
// partnerRestTemplate instance and correlation header mapping...
server.verify();
~~~

This is **part of a fixture-configured test**; without a real flow/handler, `server.verify()` cannot pass. Use a socket-based mock HTTP server when testing network timeouts, connection resets, or TLS failures. Newer Spring Integration/Spring Framework versions support `RestClient`; choose HTTP clients and test APIs matching your version.

**Valid conclusion:** the mock server received a request matching expected body/headers. **Invalid conclusion:** the production server committed business changes.

### 14.2. Status and Replies

For outbound **gateways**, also assert output payloads parsed from responses, mapped HTTP status metadata (if mapped), and correlation. For **one-way outbound adapters**, do not expect reply messages by default; focus tests on request side effects and error behavior.

## 15. JMS: Transport Headers, Correlation, and Message Conversion

JMS defines protocol metadata distinct from Spring `MessageHeaders`: message ID, correlation ID, destination, reply-to, priority, delivery mode, redelivery flag, etc. These map through the endpoint's message converter and header mapper.

Separate tests across stages:

| Stage | Assertion |
|---|---|
| Spring message before JMS outbound | Payload and business correlation accurate |
| JMS message on test broker | Properties/correlation/headers mapped; right body type |
| JMS inbound after consume | Spring message carries expected payload and metadata |
| Business handler | No mixed reply/destination; right business key |
| Error/redelivery | Retry/ack/transacted session behaves per policy |

**Never assume** a custom `correlationId` header automatically becomes `JMSCorrelationID`. When the protocol requires correlation, configure explicit converter/header mappings and test **real JMS messages** or mock at the JMS message/producer layer.

### 15.1. Contract Example

~~~text
Internal:
  payload OrderEvent(ORD-42)
  correlationId = corr-42

Expected JMS:
  destination=orders.events
  message body=JSON OrderEvent
  JMSCorrelationID=corr-42 (when mapping is configured)
  businessEventId=order-created-42

After consume:
  payload carries same orderId
  correlation/businessEventId match contract
~~~

JMS queues and topics have distinct semantics; a published message does not prove the consumer finished processing. For acks/transactions/redelivery, run tests against a matching JMS provider.

## 16. AMQP/RabbitMQ: Exchanges, Routing Keys, and Publisher Confirms

RabbitMQ exposes **exchanges**, **routing keys**, **consumer queues**, **delivery tags**, and message properties. Putting `routingKey` in a payload or Spring message header does not guarantee the producer uses it unless the adapter maps it.

Tests should verify:

- Exchange and routing key at the outbound handler/producer.
- Payload bytes and content type/encoding.
- Correlation ID and business event ID in properties/headers as configured.
- Broker routes the message to the expected bound queue.
- Publisher confirms/returns, consumer ack/nack, retries, and DLQs at the broker layer.
- Never use delivery tags or transport IDs as durable business keys.

### 16.1. Difference Between Mock and Broker Tests

~~~text
Unit test:
  verify(RabbitTemplate).convertAndSend(
      "orders.events", "order.created", expectedEvent)

Integration test:
  publish record through real RabbitMQ
  bound queue receives expected message
  body/headers/properties match
  consumer processes or rejects per contract
~~~

The `verify` syntax is **illustrative**; `RabbitTemplate` has many overloads and may use message converters/post-processors, so tests must match the method actually invoked.

**Never treat `MessageChannel.send()` returning `true` as a publisher confirm.** Writing to a channel does not guarantee the broker stored or routed the record.

## 17. Kafka: Payload, Topic, Key, Partition, and Headers

Kafka comprises message value, key, topic, partition, offset, timestamp, and headers; Spring Integration/Spring Kafka map metadata via constants and converters depending on endpoint and version.

| Metadata | Role | How to Test |
|---|---|---|
| Value payload | Serialized event content | Schema, encoding, fields |
| Record key | Drives partition and per-key ordering | Key matches business identity |
| Topic | Event destination | Never leaks to wrong topic/environment |
| Partition | Ordering guarantee per partition (under right conditions) | Never assume topic-wide global ordering |
| Offset | Consumed record position | Never use offset as business event ID |
| Record headers | Version/schema/correlation | Mapped accurately; no leaked secrets |
| Consumer group | Distribution and offset commits | Isolated test namespace/group |
| Delivery outcome | Producer ack, consumer commit | Distinguish from business side effects |

### 17.1. Kafka Contract Example

~~~text
Spring message before outbound:
  payload = {"orderId":"ORD-42"}
  headers:
    eventId=order-created-42
    correlationId=corr-42
    kafkaTopic=orders.events
    kafkaKey=ORD-42

Kafka record:
  topic=orders.events
  key=ORD-42
  value=JSON bytes
  header eventId=order-created-42
  header correlationId=corr-42
~~~

`kafkaTopic`/`kafkaKey` are **illustrative names**, not official Spring header names. When configuring Spring Integration Kafka, use version-appropriate constants/mappings such as those in `KafkaHeaders`. Outbound tests must inspect the **actual `ProducerRecord` or broker record**, not merely the Spring message before the adapter.

### 17.2. Assertion Example with a Kafka Consumer Test

~~~java
ConsumerRecord<String, String> record =
        receiveOneRecordFromTestKafkaTopic();

assertEquals("orders.events", record.topic());
assertEquals("ORD-42", record.key());

JsonNode body = objectMapper.readTree(record.value());
assertEquals("ORD-42", body.path("orderId").asText());

Header eventHeader = record.headers().lastHeader("eventId");
assertNotNull(eventHeader);
assertEquals(
        "order-created-42",
        new String(eventHeader.value(), StandardCharsets.UTF_8));
~~~

This is **just the assertion block**; `receiveOneRecordFromTestKafkaTopic()` is a fixture helper reading from an isolated Kafka test topic/consumer group. `ConsumerRecord`, `Header`, and `objectMapper` require imports, instances, and a test broker. If consumer values are `byte[]` or Avro, decode using the configured serializer/schema rather than hardcoding `String`.

### 17.3. Kafka Test Binder Is Not Real Kafka

If an app uses the **Spring Cloud Stream** test binder with `InputDestination`/`OutputDestination`, seeing a message in memory proves only binding/flow wiring. To prove topics, keys, partitions, serializers, and broker offsets, test against a real Kafka broker. **Never confuse** legacy Spring Cloud Stream `MessageCollector` with built-in Spring Integration core utilities.

## 18. Database Inbound/Outbound: Payloads and Row Mapping

Database adapters create messages from row/JDBC/JPA queries, map `ResultSet`s to `Map<String, Object>`/DTOs, or bind payloads to SQL parameters. There is no single uniform database header set across all queries and mappers.

Source example:

~~~text
Table orders_outbox:
  id=42
  event_id=order-created-42
  payload={"orderId":"ORD-42","amountMinor":12500}
  status=NEW

After inbound polling:
  payload OrderEvent(orderId="ORD-42", amountMinor=12500)
  headers eventId=order-created-42, sourceRecordId=42

After outbound processing:
  table order_status has orderId=ORD-42, state=SENT
~~~

### 18.1. Which Assertions Belong Where?

- Unit test `RowMapper`/converters directly to catch nulls, SQL → Java type mismatches, timezones, and decimals.
- Test the post-inbound channel to verify payload/headers **after mapping**.
- Test against an isolated real database to verify queries, filters, locking, transactions, and row status.
- Test outbound SQL parameter mapping, without treating a mocked JDBC return of `1` as a committed row.
- Test duplicate polling and multiple instances: never mishandle the same business event outside policy.

### 18.2. Source Record IDs and Business IDs Differ

`id=42` may be an outbox row's primary key; `eventId=order-created-42` is the durable business identifier. Never use a primary key scoped only to Database A as a global identifier when ingesting from multiple sources. When multiple sources can emit identical IDs, the contract must specify a clear namespace/source ID.

## 19. Testing replyChannel, errorChannel, and Correlation in Gateways

Gateways can use internal messaging headers to coordinate request–reply:

- `MessageHeaders.REPLY_CHANNEL`: reply destination when used per contract.
- `MessageHeaders.ERROR_CHANNEL`: error destination when supported by flow/endpoint.
- Application header `correlationId`: links requests with business outcomes.
- Transport headers like JMS correlation or HTTP request IDs mapped to/from Spring messages per config.

**Never alter or assume framework-managed `replyChannel` headers survive across external protocols.** A gateway may create an internal temporary reply channel; when an outbound message is serialized to Kafka/HTTP, typically only **business correlation** is transmitted—never a Java `MessageChannel` object.

### 19.1. Two Concurrent Requests

Suppose two orders pass through a gateway:

~~~text
Request A: orderId=ORD-42, correlationId=corr-A
Request B: orderId=ORD-43, correlationId=corr-B

Reply B arrives before reply A:
  replyB must resolve to B, never A
  replyA must resolve to A, never B
~~~

Tests must use **distinct identifiers** and verify each caller receives its matching response. Counting "two replies arrived" without checking correlation misses cross-caller mismatches.

### 19.2. When No Reply Arrives

Verify gateway reply timeouts, error types, and request state when downstream stays silent. Never call `receive()` without a timeout and hang tests indefinitely. For one-way adapters, never write tests demanding replies if the design defines none.

## 20. Inspecting Error Payloads and Failed Messages

In Spring Integration flows, some endpoints use `ErrorMessage` or `MessagingException` to represent failures. Tests must know **whether errors happen synchronously or asynchronously**.

| Topology | Possible Behavior | How to Test |
|---|---|---|
| Synchronous `DirectChannel` | Exception thrown to caller | `assertThrows`, check cause |
| Scheduler-driven poller | Error handled by error handler | Observe error channel/recovery per config |
| `ExecutorChannel` | Error flow runs on another thread | Await `ErrorMessage` or error condition |
| JMS/AMQP/Kafka consumer | Reject/nack/redelivery/DLQ | Test broker/handler config |
| HTTP outbound gateway | Client exception/status code | Assert mapping and reply/error |
| Retry advice | Prior errors retried | Assert attempt counts and final state |

Example **when an endpoint is configured** to send `ErrorMessage` to `PollableChannel errors`:

~~~java
Message<?> message = errors.receive(2000);
assertNotNull(message);

ErrorMessage error = assertInstanceOf(
        ErrorMessage.class, message);

Throwable cause = error.getPayload();
assertNotNull(cause);
~~~

Requires importing `org.springframework.messaging.support.ErrorMessage`; `errors` is declared in the test context. `MessagingException.getFailedMessage()` helps trace the failing input when the exception type provides it, though not every `Throwable` carries one. **Never assume simply declaring an `errorChannel` bean causes all exceptions to land there automatically.**

### 20.1. Safety When Inspecting Errors

Never assert by printing raw payloads containing PII/secrets to CI logs. Instead, check error category, correlation, exception type, diagnostic metadata, and absence of unintended side effects.

~~~text
Input: schema invalid
Expected:
  ErrorMessage or reject branch carries eventId
  no request sent to shipping API
  logs record only safe metadata
  no infinite retries on malformed data
~~~

## 21. Headers and Payloads in Asynchronous Processing

Across `ExecutorChannel`s, pollers, JMS/Kafka listeners, or outbound clients returning `CompletableFuture`, output messages may arrive **after the send call returns**. Checking immediately:

~~~java
input.send(message);
assertNotNull(resultChannel.receive(0));
~~~

can be flaky. Replace with:

~~~java
assertTrue(input.send(message));

Message<?> actual = resultChannel.receive(2000);
assertNotNull(actual, "No output message received within test timeout");
assertEquals("corr-42",
        actual.getHeaders().get("correlationId"));
~~~

The 2-second timeout is illustrative; choose based on scheduler, CI environment, SLAs, and test infrastructure. Never use `Thread.sleep(5000)` as the sole synchronization mechanism—it is both slow and fails to prove completion.

### 21.1. Testing Multiple Asynchronous Messages

When splitters/routers dispatch multiple messages across executors, decide whether ordering is required:

- When **any order** is valid, collect all N outputs and compare **sets of business IDs**.
- When contracts guarantee per-key/partition order, assert order **strictly within the guaranteed scope**, not system-wide.
- For aggregators, verify completion criteria before concluding outputs are missing.
- For pub/sub fan-out, wait for every subscriber to finish rather than just one collector receiving a copy.

### 21.2. Races in Shared Test Contexts

A `QueueChannel` shared across concurrent tests can hold another test's output. Use unique correlations, dedicated output channels/contexts, or clean test partitioning; stop pollers/listeners that could keep emitting once a test finishes.

### 21.3. Headers as JVM Object References

A header can hold a mutable Java object. The messaging API does not automatically make nested values immutable; if two threads read/mutate the same object, test results become unpredictable. Prefer simple/immutable header values and avoid stuffing large mutable maps into headers hoping subscribers won't mutate them.

## 22. Multiple Outputs: Splitters, Routers, and Aggregators

### 22.1. One Input Generating Three Messages

Suppose a batch of three orders is split into three messages:

~~~text
Input:
  batchId=batch-7
  orderIds=[ORD-41, ORD-42, ORD-43]

Expected outputs:
  (ORD-41, batch-7)
  (ORD-42, batch-7)
  (ORD-43, batch-7)
~~~

Test with `PollableChannel output`:

~~~java
Set<String> orderIds = new HashSet<>();

for (int i = 0; i < 3; i++) {
    Message<?> part = output.receive(2000);
    assertNotNull(part);
    assertEquals("batch-7", part.getHeaders().get("batchId"));

    OrderEvent event =
            assertInstanceOf(OrderEvent.class, part.getPayload());
    assertTrue(orderIds.add(event.orderId()),
            "Duplicate orderId in batch output");
}

assertEquals(
        Set.of("ORD-41", "ORD-42", "ORD-43"),
        orderIds);
~~~

`OrderEvent` is a DTO in the test fixture, e.g., a record with an `orderId()` accessor. The snippet omits flow/splitter setup. The count of 3 must align with the contract and test input.

**Note:** correlation/sequence headers created by a **splitter** can differ from business headers. Inspect `IntegrationMessageHeaderAccessor.CORRELATION_ID`/`SEQUENCE_NUMBER` or equivalent constants **when the real flow uses them**; never assume a custom `batchId` matches framework sequence headers.

### 22.2. Router: Right Branch, Zero Cross-Branch Leakage

Suppose:

~~~text
eventType=order.created -> ordersChannel
eventType=order.failed  -> failuresChannel
other eventType         -> rejectedChannel
~~~

Use a dedicated collector per branch. Verify payload, event type, and tenant on the target branch while ensuring **tenant A data never reaches tenant B's consumer**. If the router reads headers from untrusted sources, verify source validation before routing.

### 22.3. Aggregator: Output Only Upon Group Completion

Aggregators can wait for a message count or timeout. Test:

- Sending each part with matching correlation ID.
- Confirming no aggregate emits before completion rules are met.
- Sending the final part and asserting the contract output.
- Sending duplicate/late parts and checking policy.
- Verifying aggregated content, headers, and group release behavior.

Do not merely assert a message appeared; for aggregators, verify **the output dataset matches the exact group with nothing missing or duplicated**.

## 23. Header Validation and Security: External Data Is Untrusted by Default

**Headers can be spoofed** when arriving from HTTP clients, Kafka publishers, partner-supplied file metadata, or unauthenticated integrations. A header like `tenantId=tenant-a` does not prove the sender is authorized to access tenant A's data.

Fields requiring strict validation:

| Header | Risk | Recommended Test |
|---|---|---|
| `tenantId` | Cross-tenant access | Compare against authenticated principal/security context |
| `destinationUri` | SSRF, sending data to rogue hosts | URI allowlist and network policy |
| `targetFileName` | Path traversal, file overwrites | Character/path constraints; block `../` and absolute paths |
| `kafkaTopic` / routing key | Publishing to wrong topic/queue | Topic/exchange allowlist scoped by tenant |
| `Authorization` | Token leaks to other transports/logs | Redact/drop before outbound |
| `correlationId` | Log injection/PII/oversized input | Validate length, charset, and source |
| `contentType` | Parser picks wrong data type | Accept only supported MIME types and verify body |
| `schemaVersion` | Invokes wrong converter or downgrades schema | Reject unsupported versions |

Example flow control:

~~~text
HTTP request:
  X-Tenant-Id: tenant-b
  authenticated principal: tenant-a

Expected:
  reject request or derive mapping from principal per policy
  never send a tenant-b message to tenant-b's outbound topic
  error event retains correlation without logging tokens
~~~

### 23.1. Testing a Header Allowlist

If a flow allows only `correlationId` and `eventType` outbound, verify sensitive headers are stripped:

~~~java
Message<?> message = outboundProbe.receive(1000);
assertNotNull(message);

assertEquals("corr-42",
        message.getHeaders().get("correlationId"));
assertNull(message.getHeaders().get("Authorization"));
assertNull(message.getHeaders().get("rawClientCookie"));
~~~

`outboundProbe` observes **before the adapter**. Add transport-level tests to prove HTTP/JMS/Kafka outputs truly omit sensitive headers; adapters may inject their own headers from client configuration.

### 23.2. Testing Against Path Traversal

Send names such as:

~~~text
orders-42.csv            -> valid
../secrets.txt           -> rejected
/subdir/override.csv     -> rejected if contract permits basenames only
order\nInjected-Header   -> rejected or normalized per rules
~~~

Assert rejection **before the outbound client is invoked**. On Windows and Unix, account for path separator differences, absolute paths, and Unicode normalization if required by the contract.

## 24. Testing Contracts with Parameterized Tests

When testing many invalid payload/header values, JUnit 5 `@ParameterizedTest` makes boundary cases clearer than repetitive methods.

Pure unit test example for an application validator:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.NullAndEmptySource;
import org.junit.jupiter.params.provider.ValueSource;

class CorrelationIdValidationTest {

    private static boolean validCorrelationId(String value) {
        return value != null
                && !value.isBlank()
                && value.length() <= 64
                && value.matches("[A-Za-z0-9_-]+");
    }

    @ParameterizedTest
    @NullAndEmptySource
    @ValueSource(strings = {
        " ", "bad\nvalue", "has/slash", "with space"
    })
    void rejectsInvalidCorrelationId(String value) {
        assertFalse(validCorrelationId(value));
    }
}
~~~

This is an **illustrative validator unit test**. If your app accepts UUIDs with hyphens or tracing IDs in other formats, adjust rules accordingly. **Do not blindly enforce a 64-char limit on every system** without consulting the real contract.

In flow tests, use parameterized inputs to verify:

- `null` payloads **cannot form a normal Spring `Message`** in most builder paths; test validators/null DTO fields at the appropriate layer.
- Empty/whitespace payloads are rejected as expected.
- Unsupported `contentType`.
- Wrong-typed or unauthorized `tenantId`.
- UTF-8 with Vietnamese characters, emojis, and multibyte text.
- Size limits, batch limits, and large header counts.

### 24.1. Assert Business Meaning Rather Than Volatile Values

Some events generate fresh timestamps/IDs on every run. Inject a clock/ID generator or assert invariants:

~~~text
output.eventId is non-blank
output.correlationId == input.correlationId
output.occurredAt falls within controlled test bounds
output.schemaVersion is a supported version
~~~

Avoid coupling tests to volatile framework `MessageHeaders.ID` or timestamps unless required by contract.

## 25. Testing Payload Schema Evolution and Compatibility

Adapters often bridge independently developed systems. Payloads/headers evolve across versions:

~~~json
{
  "eventType": "order.created",
  "schemaVersion": 2,
  "orderId": "ORD-42",
  "amount": {
    "currency": "VND",
    "minorUnits": 12500
  }
}
~~~

Verify:

1. Consumers parse all supported versions.
2. Header `schemaVersion` and payload field do not contradict each other.
3. New optional fields do not break older parsers if backward compatibility is required.
4. Missing required fields fail cleanly.
5. Unknown enums/extra fields follow contract policy.
6. Monetary amounts, timezones, and decimals convert accurately.
7. When changing Avro/Protobuf/JSON schemas, test matching serializers and schema registries/mocks if used.
8. Never silently upgrade/downgrade versions from unverified headers.

### 25.1. Contract Tests Between Producer and Consumer

An outbound adapter can emit syntactically valid JSON that violates the consumer's schema. Verify:

- **Producer side**: DTO → serialized payload matches schema/version.
- **Transport side**: content type/schema headers/keys mapped accurately.
- **Consumer side**: parser/handler accepts and interprets accurately.
- **Compatibility**: published versions continue working or reject cleanly.

**Do not treat raw JSON string equality as the whole contract** when key order or whitespace is irrelevant. Use JSON tree/schema validation and field assertions; verify raw bytes when exact encoding is part of the protocol.

## 26. Retries, Duplicates, and Idempotency Headers

A message can be delivered **multiple times** due to:

- Kafka/JMS/AMQP redelivery after consumer crash.
- HTTP client timeout after server already processed it.
- SFTP poller re-reading a file after restart.
- JDBC polling re-selecting a row after transaction rollback.
- Application retry logic on transient errors.

The `eventId` header or payload field must remain **stable across retries**, while an `attemptId` may change between attempts. Generating a brand-new business ID on every retry prevents consumers from detecting duplicates.

### 26.1. Contract Template

~~~text
First attempt:
  eventId=order-created-42
  correlationId=corr-42
  attempt=1

Second attempt after timeout:
  eventId=order-created-42      (unchanged)
  correlationId=corr-42        (typically unchanged across workflow)
  attempt=2                    (changed)
~~~

Tests must prove:

- Both attempts share the same business event ID.
- Idempotent consumers do not create two orders/shipments.
- Error/retry logs preserve correlation.
- Processors do not use fresh `MessageHeaders.ID` values as dedup keys.
- Response timeouts are never assumed to mean the server did not process the request.

### 26.2. Inspecting Headers Under Retry Advice

When retry advice is configured in a flow, mock the client to fail first and succeed on the next call. Assert arguments retain the same `eventId` and business payload, and verify attempt counts **after retries finish**. Stubbing two outcomes in Mockito **does not trigger retries by itself**; a real retry policy/advice or retry handler must be active.

### 26.3. Target Side Effects

Seeing two `Message<?>` items on a collector does not prove two target records exist. Conversely, seeing one output message does not prove retries didn't duplicate side effects—the server might have written twice before returning. Prove this with stateful tests against a mock server, DB, or test broker.

## 27. Case Study: File/SFTP → OrderEvent → HTTP → Kafka

A system ingests order CSVs from SFTP, parses them into `OrderEvent`, calls a fulfillment HTTP API, and publishes a Kafka event for dashboards. We want to verify payloads/headers **at multiple boundaries**.

~~~mermaid
flowchart LR
    SFTP["SFTP/file inbound"] --> A["Message<File>"]
    A --> PARSER["CSV parser"]
    PARSER --> DTO["Message<OrderEvent>"]
    DTO --> ROUTER["Route tenant + validate"]
    ROUTER --> HTTP["HTTP outbound gateway"]
    HTTP --> RESULT["Message<ShipmentReceipt>"]
    RESULT --> KAFKA["Kafka outbound adapter"]
    PARSER -. "invalid" .-> REJECT["Rejected events / error channel"]
    A -. "probe" .-> P1["File contract"]
    DTO -. "probe" .-> P2["DTO + headers"]
    RESULT -. "probe" .-> P3["Response contract"]
    KAFKA --> EXT["Kafka test broker"]
~~~

### 27.1. Proposed Contract

~~~text
Source:
  file: /incoming/orders-42.csv
  content: orderId,amountMinor,currency
           ORD-42,12500,VND

After parser:
  payload: OrderEvent("ORD-42", 12500, "VND")
  headers:
    eventId=order-created-42
    correlationId=corr-42
    sourceSystem=partner-sftp
    tenantId=tenant-a
    schemaVersion=1

HTTP request:
  POST /shipments
  X-Correlation-Id: corr-42
  body: {"orderId":"ORD-42","amountMinor":12500,"currency":"VND"}

HTTP reply:
  payload: ShipmentReceipt("sh-42","ACCEPTED")
  correlationId=corr-42

Kafka output:
  topic=shipment.events
  key=ORD-42
  eventId=order-created-42
  payload schemaVersion=1
~~~

### 27.2. Tests by Layer

| Layer | Input | Mandatory Assertions |
|---|---|---|
| File/SFTP source | Test file | Name/path/content accurate; file filter behaves properly |
| Parser unit | CSV bytes | DTO has accurate amounts, currency; errors on bad CSV |
| Channel/flow | `Message<File>` or DTO | Payload right class; preserves correlation, tenant |
| Header validation | Missing/invalid `tenantId`, `eventId` | Rejected before calling outbound |
| HTTP gateway | DTO | Mock server observes right method/body/headers; reply mapped |
| Kafka outbound | Event from reply | Broker record has right topic/key/headers/schema |
| Retry/idempotency | Timeout/replay | Event ID stays stable; single side effect per contract |
| Negative/poison | Bad CSV, unknown schema | No bogus HTTP/Kafka traffic; error/recovery triggered |
| Lifecycle | Stop/restart poller | No duplicates outside policy |
| Security | Input with bearer token or malicious filename | Secret never forwarded; no path traversal |

### 27.3. Insufficient Assertions

- `fileChannel.receive(...) != null`: proves only the file message entered the flow, not that HTTP succeeded.
- `httpInput.send(message) == true`: does not prove the mock server received the request.
- `kafkaOutputChannel.receive(...) != null`: does not prove the Kafka broker has the record.
- `eventId` set to `MessageHeaders.ID`: unstable when flows construct new messages.
- `tenantId` exists: does not prove it matches an authorized principal.
- `errors.receive(0) == null`: does not prove an async error won't arrive moments later.

### 27.4. Sample Test Report

~~~text
Scenario: order ORD-42, tenant-a

File stage: PASS
  File payload valid, input filename matched

Parser stage: PASS
  OrderEvent(ORD-42, 12500, VND)

Message contract: PASS
  eventId=order-created-42
  correlationId=corr-42
  tenantId=tenant-a

HTTP stage: PASS
  Mock server received POST /shipments
  body/schema/header matched
  reply shipmentId=sh-42

Kafka stage: PASS
  Test broker record topic=shipment.events, key=ORD-42
  schema/eventId matched

Overall: PASS within test infrastructure scope
Production behavior: not yet proven
~~~

Only mark `PASS` after **running the corresponding tests**. The report above illustrates **acceptance criteria**, not output from an actual execution.

## 28. Testing Matrix and Anti-Patterns

| Anti-Pattern | Consequence | Fix |
|---|---|---|
| Checking only String payloads | Misses lost correlation/tenant/schema headers | Assert all mandatory headers |
| Comparing full `MessageHeaders` | Flaky as IDs/timestamps change | Compare contract headers only |
| Forwarding every header blindly | Leaks secrets and expands trust boundaries | Allowlist/redaction |
| Equating Spring headers with HTTP/JMS/Kafka headers | Broken transport mappings | Test at protocol boundaries |
| Setting `contentType=JSON` and assuming serialized | Payload might still be a DTO or CSV | Verify actual converter/body |
| Comparing `byte[]` with `toString()` | Does not check bytes | `assertArrayEquals`/decode |
| Using emails/message IDs as sole correlation | Unstable or PII risk | Scoped business event ID |
| Attaching second collector to `DirectChannel` | Collector steals messages from handler | Terminal queue/wire tap/pub-sub |
| `receive()` without timeout | Test hangs indefinitely | `receive(timeout)` |
| Asserting no output right after async send | Messages may arrive later | Completion signals/deadlines |
| Checking only one splitter output | Missing/duplicate outputs go unseen | Collect exact count and compare ID sets |
| Router trusting caller `tenantId` | Cross-tenant access leaks | Verify security context + deny |
| Assuming all errors hit global `errorChannel` | Errors route elsewhere | Test actual topology/error handlers |
| Treating file pattern filters as accept-once | Reprocesses on next poll/restart | Filter + metadata store + restart tests |
| Treating Kafka test binder as a real broker | Skips offset/partition/ack behavior | Isolated real broker tests |
| Skipping queue/listener cleanup | Stale messages cause false passes | Context isolation/teardown |
| Reusing one static ID in parallel tests | Cross-talk | Unique business IDs/test namespaces |
| Treating mock client call as target side effect | Unproven server commit | Assert at target system |
| Ignoring schema evolution | Breaks older consumers | Contract/schema version tests |
| Dumping full messages on failure | Leaks PII/tokens/credentials | Safe metadata and redaction |

## 29. Acceptance Checklist and Self-Assessment Questions

### 29.1. Checklist

- [ ] Identified measurement points: pre-adapter, post-transform, post-gateway, or target.
- [ ] Contract specifies **payload type**, schema, encoding, mandatory/optional headers, and trust rules.
- [ ] Test messages use isolated data and correlation IDs.
- [ ] Payload type checked via `assertInstanceOf` or equivalent assertion.
- [ ] Content checked via exact comparison, JSON tree/schema, or byte arrays appropriately.
- [ ] Correlation/business event IDs checked without relying on `MessageHeaders.ID` as a business key.
- [ ] Content type and converters match actual bodies.
- [ ] Avoided comparing entire framework headers unless explicitly part of contract.
- [ ] Sensitive headers stripped/restricted before outbound.
- [ ] Routers/filters/transformers tested for missing, wrong-typed, and unverified headers.
- [ ] Splitter/router/aggregator branches verified for output counts and sets.
- [ ] Async flows use bounded timeouts and completion conditions.
- [ ] HTTP/JMS/AMQP/Kafka tested for transport metadata mappings.
- [ ] File/SFTP tested for source metadata and real file contents/paths.
- [ ] DB tested for row mappers, data types, and transactions/side effects where critical.
- [ ] Error paths retain correlation without logging secrets.
- [ ] Duplicates/retries/idempotency tested if transport can redeliver.
- [ ] Setup/teardown prevents stale messages from prior tests.
- [ ] Clearly distinguished **message received** from **target processing completed**.

### 29.2. Scenario A

**Question:** An output message has the right payload yet lacks `correlationId`. Can the flow test pass because all business fields are present?

**Answer:** No, if correlation is mandatory in the contract. Missing correlation breaks tracing, replies, and retry mapping. Find the endpoint dropping the header and add end-to-end flow assertions.

### 29.3. Scenario B

**Question:** HTTP inbound receives `X-Tenant-Id=tenant-b`, while the JWT authenticates `tenant-a`. A test only verifies this mapped to `tenantId=tenant-b`. Is this safe enough?

**Answer:** No. Bind tenants to the verified principal/authorization policy, rejecting or deriving per policy; **the mere presence of a header does not prove authorization**.

### 29.4. Scenario C

**Question:** A Kafka outbound message carries custom header `kafkaKey=ORD-42`, yet the broker record has a `null` key. Why?

**Answer:** A custom header name does not automatically become a Kafka record key. Configure the proper mapper using your module version's constants and inspect records on the broker.

### 29.5. Scenario D

**Question:** A File inbound test emits `Message<File>`, while the downstream handler casts payload to `String`. How should this be fixed?

**Answer:** Add a transformer that reads/parses file contents or update the handler's contract. Explicitly test payload types **both before and after** the transformer.

### 29.6. Scenario E

**Question:** `assertEquals(input.getHeaders(), output.getHeaders())` fails because message IDs differ. Does that mean the transformer is buggy?

**Answer:** No. The framework can construct new messages with new IDs and timestamps. Tests should assert required business headers, checking framework IDs only when specifically required.

### 29.7. Scenario F

**Question:** `contentType=application/json` with CSV text payload. If a test asserts only the content type, can it conclude the body is valid?

**Answer:** No. Inspect the body, converter, charset, and schema. Declaring a header does not automatically convert content.

### 29.8. Scenario G

**Question:** Two retries have different `MessageHeaders.ID` values yet share the same `eventId`. Are these two separate business events?

**Answer:** Not necessarily. Framework message IDs can change across attempts; business event IDs must remain stable so idempotent consumers recognize redelivered events.

### 29.9. Scenario H

**Question:** An outbound HTTP mock client receives the right request, yet the real service mishandles the data. What did the current test prove?

**Answer:** Only request mapping/invocation at the mock layer. Add contract/integration tests against a compatible server and assert side effects; never claim production works from a mock alone.

### 29.10. Scenario I

**Question:** A splitter creates three messages; a test receives two and times out. Is comparing the payloads of the two received messages enough?

**Answer:** No. Assert the **exact count** of three, ID sets, correlation, and missing-item behavior; the bug could lie in filters, routing, concurrency, or exceptions.

### 29.11. Scenario J

**Question:** A message carries an `Authorization` header, gets sent to Kafka, and is logged verbatim. Where should this be fixed?

**Answer:** Enforce an allowlist/sanitization at the appropriate boundary so raw tokens never enter downstream messaging; add tests verifying transport records and audit logs omit credentials.

## 30. Practice Guide and Testing Scope

### 30.1. Suggested Practice Exercise

Build a small flow:

~~~text
File inbound (order CSV)
  -> fileInput
  -> CSV-to-OrderEvent transformer
  -> validate tenant + schemaVersion
  -> route by eventType
  -> outbound HTTP gateway
  -> resultChannel
  -> Kafka outbound
~~~

Requirements:

1. Create `@TempDir` and CSV fixtures with one valid order, one missing-field order, and one pattern-mismatched file.
2. Use a `QueueChannel` as test output after transformation; assert payload type, order ID, amount, and correlation/tenant.
3. Add a missing/invalid `tenantId` case and prove HTTP outbound is never called.
4. Configure a mock HTTP server and assert actual request body/headers.
5. Test gateway replies and correlation.
6. With a Kafka test broker, verify topic/key/headers/schema.
7. Simulate timeouts and retries while keeping `eventId` stable.
8. Stop pollers and clean files/queues/topics/groups between tests.
9. Run tests in parallel with distinct namespaces/correlations or maintain strict isolation.
10. Report **what was proven** and **what remains unproven** at each layer.

### 30.2. References

To cross-check APIs and header constants for your project's version:

- **Spring Integration Reference — Message:** https://docs.spring.io/spring-integration/reference/message.html
- **Spring Integration Reference — Testing:** https://docs.spring.io/spring-integration/reference/testing.html
- **Spring Integration Reference — File Support:** https://docs.spring.io/spring-integration/reference/file.html
- **Spring Integration Reference — HTTP:** https://docs.spring.io/spring-integration/reference/http.html
- **Spring Framework Reference — Messaging:** https://docs.spring.io/spring-framework/reference/integration.html

Links point to general API documentation; URLs or method names may vary across versions. Examples provide **illustrative fixture-backed snippets** as noted; STEP 4 is the authoring step, not a certification that a real project build or test run was executed.

## Conclusion

**Checking headers and payloads** is central to testing **Spring Integration Adapters** flows because payloads define *business data*, while headers define *context, routing, conversion, correlation, and trust boundaries*. A sound strategy verifies payload types/contents at the right channels, asserts headers **that truly belong to the contract**, checks mappings across File, SFTP, HTTP, JMS, AMQP, Kafka, and databases, and covers error paths, async flows, duplicates, and schema evolution. Avoid confusing **internal headers** with **transport metadata**, or **a message reaching a channel** with **a completed side effect**. When every assertion ties to an observable outcome with clean setup/teardown, the test suite catches data mismatches, lost correlation, broken authorization, and subtle production integration bugs early.
