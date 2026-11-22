# Propagating Correlation IDs Across Messages in Java: Producer, Broker, Consumer, and Retry

## 1. Lesson Objectives

In asynchronous Java application architectures, a request often does not end at the HTTP controller. A service may **publish a message** to a broker; a consumer in a different JVM receives the message seconds or minutes later, or after a system restart. If you only put the Correlation ID into the producer thread's `MDC`, the consumer **does not automatically receive that ID**. MDC lives in the process's runtime context, whereas the message is transmitted through another system.

**Propagating a Correlation ID across messages** means taking a correlation identifier from the producer context and placing it into **message metadata/headers/properties**, preserving it across delivery steps, and then reading and re-attaching it to the logging context when the consumer processes the message.

The goal is that during an investigation, you can answer:

- Which HTTP request created this message?
- Which service published the message, and on which consumer was the message processed?
- Which publish, receive, retry, dead-letter, and downstream publish steps belong to the same workflow?
- Was the error a temporary processing failure or a final outcome?
- Was a redelivered message mistakenly counted as two separate business operations?
- Did context leak between consecutive messages running on the same worker thread?

An example of correlated log lines:

```text
INFO  cid=corr-42 mid=m-001 event=message.published
INFO  cid=corr-42 mid=m-001 event=message.received attempt=1
WARN  cid=corr-42 mid=m-001 event=message.retry_scheduled
INFO  cid=corr-42 mid=m-001 event=message.received attempt=2
INFO  cid=corr-42 mid=m-001 event=message.processed
INFO  cid=corr-42 mid=m-002 event=message.published
```

`corr-42` is the **workflow's Correlation ID**; `m-001` and `m-002` are **two different Message IDs**. When a message is retried, the system can keep a stable business ID while generating a new delivery attempt. Records sharing the same Correlation ID are not necessarily the same message or the same delivery attempt.

**Key takeaway:** context must be propagated **across the message boundary** using the broker/protocol mechanism, and only then placed into the consumer's MDC or ThreadContext. Never treat a `ThreadLocal` variable or `MDC.put` on the producer as a header that is automatically sent over the network.

## 2. How Correlation ID Differs from Message ID, Trace ID, and Event Code

| Attribute | Primary Purpose | Scope | When Does It Typically Change? |
| --- | --- | --- | --- |
| `correlation_id` | Links related operations in the same workflow/journey | Across multiple messages, services, and processing attempts per contract | When a new journey starts |
| `message_id` | Identifies a logical message/event | One business message, depending on the system | When creating a new logical message |
| `delivery_attempt` | Records which delivery/processing attempt this is | Per attempt | On redelivery/retry |
| `trace_id` | Identifies a distributed trace | Across multiple spans per tracing instrumentation | When starting a new trace per tracing rules |
| `span_id` | Identifies a single span of a trace | One unit of work | Per span |
| `request_id` | Identifies a request entering a boundary | HTTP request/gateway or per ID propagation contract | Depends on the API boundary |
| `event_code` | Classifies the **event type**, such as `order.created` | May repeat across millions of transactions | When the event type differs |
| `business_id`, e.g. `order_id` | Identifies a business entity | Across multiple requests and messages | Per entity |

### One Correlation ID Can Span Multiple Messages

Example:

```text
HTTP: POST /orders
  request_id=req-81
  correlation_id=corr-42
        |
        v
order.created
  message_id=m-001
  correlation_id=corr-42
        |
        v
Payment consumer
        |
        +-- publish payment.authorized
              message_id=m-002
              correlation_id=corr-42
                    |
                    v
              Shipping consumer
```

`m-002` **does not reuse** `m-001` if it is a new logical message. However, both can keep `corr-42` to investigate the same business flow together.

### Correlation ID Is Not an Idempotency Key

If a consumer receives the same message again after a timeout or lost ACK, the Correlation ID helps link logs, but **does not prove that a business operation has not already been executed**. A single journey may have dozens of messages sharing a Correlation ID. Preventing duplicate processing requires a **message/event ID or idempotency key** and appropriate state storage/transaction mechanisms.

### Correlation ID Is Not Automatically a W3C Trace ID

`corr-42` is a sample string for business correlation, **not** a valid W3C trace ID. If the application uses OpenTelemetry or distributed tracing, use the SDK/instrumentation to create, receive, and propagate `traceparent`/span context; you can output `trace_id` in logs alongside the Correlation ID.

**Do not manually set `trace_id=corr-42`** and treat it as a compliant distributed trace. The two ID types may be related, but they carry different contracts.

## 3. Why Using MDC Only on the Producer Is Not Enough

Suppose an HTTP handler does:

```java
MDC.put("correlation_id", "corr-42");
try {
    publisher.publishOrderCreated(order);
} finally {
    MDC.remove("correlation_id");
}
```

This is **illustrative application code**, assuming `publisher` and `order` exist. A logger on the producer thread can print `corr-42` if the layout/encoder is configured to read MDC.

However, a JVM on the consumer side does not automatically know this value:

```text
Producer JVM                           Consumer JVM
-------------                          -------------
MDC: correlation_id=corr-42

publish(payload) ---> broker --->      receive(payload)

                                       Consumer's MDC:
                                       does not automatically have corr-42
```

To propagate it, you must do so explicitly:

```text
Producer JVM
  MDC / tracing / application context
       |
       v
  correlation_id
       |
       +--> message header/property: correlation_id=corr-42
               |
               v
             Broker
               |
               v
          Consumer reads metadata
               |
               v
          Validate correlation_id
               |
               v
          MDC.put("correlation_id", id)
               |
               v
          Logger + appender/encoder
               |
               v
          MDC restore/cleanup in finally
```

MDC is used at **both ends**, but message metadata is the actual channel that connects the two processes.

## 4. Propagating in Headers or Payload?

Many brokers have **metadata** or **properties** alongside the payload:

- Kafka: record headers.
- RabbitMQ/AMQP: message properties such as `correlationId` or custom headers.
- JMS: `JMSCorrelationID` and application properties.
- Other brokers/cloud queues: corresponding message attributes/properties.

A message contract might look like:

```text
Topic/queue: orders.created
Key:         O-17
Headers:
  correlation_id: corr-42
  event_id:       evt-1001
  schema_version: 1
Payload:
  {"order_id":"O-17","amount_minor":120000,"currency":"VND"}
```

This is a **contract pattern**, not a universal syntax that can be pasted directly into every broker.

### Advantages of Metadata

1. Avoids modifying business DTOs just to add observability information.
2. Consumers, middleware, and interceptors can read context before deserializing the payload.
3. A child message created from a parent message can **copy context via an allowlist** without touching business fields.
4. Decouples workflow correlation from the payload's JSON/Avro/Protobuf format.

### When Can You Use an Envelope in the Payload?

Some protocols lack convenient headers, or an event contract uses a shared envelope:

```json
{
  "metadata": {
    "correlation_id": "corr-42",
    "event_id": "evt-1001",
    "schema_version": 1
  },
  "data": {
    "order_id": "O-17",
    "amount_minor": 120000,
    "currency": "VND"
  }
}
```

An envelope can work well if agreed upon and versioned. However, **do not simultaneously maintain two conflicting sources of truth**, such as header `corr-A` and payload metadata `corr-B`. If both exist, you must specify which field is authoritative, how to check for mismatches, and how to audit them.

### One ID, One Field Name, One Encoding Rule

Choose one name such as `correlation_id` or `X-Correlation-ID` depending on the protocol, and standardize it across producers and consumers. Define policies for:

- Is the key name case-sensitive?
- Is the value UTF-8 encoded or stored using the broker's string/property type?
- What is the maximum length?
- Are IDs from external clients accepted?
- If missing or malformed, do you generate a new one, reject, or mark it as missing?
- Do retry, redelivery, and DLQ preserve the ID?
- Does a downstream message published by a consumer keep the old ID or start a new correlation scope?

Avoid having the producer send `correlationId` while the consumer reads `correlation_id` and assuming the broker automatically translates names.

## 5. The Correlation ID Contract Should Be Defined at the Entry Boundary

A common strategy:

1. **At the HTTP gateway/entrypoint:** determine whether a Correlation ID already exists from a trusted source. If missing or invalid, generate a new ID using an appropriate tool.
2. **In the producer:** read the validated context and place it into the message header/property according to the contract.
3. **At the consumer:** read metadata, validate the value, and set up the logging context for the scope of message processing.
4. **When publishing child messages:** take the active Correlation ID in the consumer and continue propagating it, unless business requirements define a new scope.
5. **When processing completes:** restore/clear the context so the worker does not carry the ID over to the next message.

The "from a trusted source" condition matters: clients can send their own headers with the same name. A Correlation ID helps locate logs; it is **not proof of caller authentication**, nor does it grant access to resources or log stores.

### Do Not Generate a New ID in Every Method

Incorrect example:

```java
void handle(Message message) {
    String correlationId = UUID.randomUUID().toString();
    // Every retry or every service gets a new ID.
}
```

This is an **illustrative snippet**. If every retry generates a new ID, tracing the same logical message breaks. Typically, you only generate a new ID at a designed **correlation boundary**; when a valid message already carries an ID, you must continue using it.

### Be Careful with Long-Running Work

A message may sit in a queue for days. A Correlation ID can serve as a long-lived link, whereas a **tracing span** has a different lifecycle and semantics. When a consumer receives a delayed message, tracing instrumentation can choose parent/link relationships according to the system. Do not try to keep a span "open" for the entire time a message is queued just because both steps share the same Correlation ID.

## 6. Runnable Java 17 + Maven Example: Propagating via Message Headers and Restoring MDC

This lab uses **SLF4J + Logback** and simulates a broker with an `ExecutorService`. No Kafka/RabbitMQ server is required to run it. The goal is to accurately demonstrate a **header-carrying envelope**, **consumer reading headers**, **MDC scope**, **retry preserving correlation**, and **workers not leaking context**.

Even though the producer and consumer run in the same test program, we treat `Message` as an object that has crossed a transport boundary: the consumer **only gets the Correlation ID from headers**, without relying on the producer thread's MDC.

**Requirements:** JDK 17+, Maven, and access to fetch dependencies if not cached.

Project structure:

```text
message-correlation-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── MessageCorrelationDemo.java
        └── resources/
            └── logback.xml
```

### 6.1. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>message-correlation-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>ch.qos.logback</groupId>
            <artifactId>logback-classic</artifactId>
            <version>1.5.16</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`logback-classic` provides the Logback backend and corresponding SLF4J provider. The versions here are **example versions**, not a claim that they are the latest or meet every production security requirement. When integrating frameworks with a BOM/dependency management, choose supported versions and avoid multiple SLF4J providers on the runtime classpath.

### 6.2. `src/main/resources/logback.xml`

```xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
            <pattern>%level|cid=%X{correlation_id}|mid=%X{message_id}|%msg%n</pattern>
            <charset>UTF-8</charset>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE" />
    </root>
</configuration>
```

- `%X{correlation_id}` reads the Correlation ID from the event's MDC.
- `%X{message_id}` reads the ID of the logical message currently being processed by the consumer.
- `%msg` is the formatted message; `%n` is a newline.
- The pattern omits timestamp/thread so that the **expected output of the lab is deterministic**.
- A production pattern/JSON encoder typically adds timestamp, service, logger, and environment.

### 6.3. `src/main/java/demo/MessageCorrelationDemo.java`

```java
package demo;

import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

public final class MessageCorrelationDemo {
    private static final Logger LOG =
            LoggerFactory.getLogger(MessageCorrelationDemo.class);

    private MessageCorrelationDemo() {
    }

    record Message(
            String messageId,
            String payload,
            Map<String, String> headers,
            int attempt) {

        Message {
            headers = Map.copyOf(headers);
        }

        Message redelivered() {
            return new Message(
                    messageId, payload, headers, attempt + 1);
        }
    }

    private static void restore(Map<String, String> previous) {
        if (previous == null) {
            MDC.clear();
        } else {
            MDC.setContextMap(previous);
        }
    }

    private static Message publish(
            String messageId, String payload) {
        String cid = MDC.get("correlation_id");

        if (cid == null || cid.isBlank()) {
            throw new IllegalStateException(
                    "Missing correlation_id at producer");
        }

        Message message = new Message(
                messageId,
                payload,
                Map.of("correlation_id", cid),
                1);

        LOG.info("event=message.published message_id={}", messageId);
        return message;
    }

    private static boolean consume(Message message) {
        Map<String, String> previous =
                MDC.getCopyOfContextMap();

        try {
            String cid = message.headers().get("correlation_id");

            if (cid == null || cid.isBlank()) {
                throw new IllegalArgumentException(
                        "Invalid correlation_id header");
            }

            MDC.put("correlation_id", cid);
            MDC.put("message_id", message.messageId());

            LOG.info("event=message.received attempt={}",
                    message.attempt());

            if (message.messageId().equals("m-001")
                    && message.attempt() == 1) {
                LOG.warn("event=message.retry_scheduled");
                return false;
            }

            LOG.info("event=message.processed payload={}",
                    message.payload());
            return true;
        } finally {
            restore(previous);
        }
    }

    public static void main(String[] args) throws Exception {
        Map<String, String> before =
                MDC.getCopyOfContextMap();

        ExecutorService worker =
                Executors.newSingleThreadExecutor();

        try {
            MDC.put("correlation_id", "corr-42");

            Message first = publish("m-001", "order.created");
            Message second = publish("m-002", "payment.authorized");

            Future<Boolean> firstAttempt =
                    worker.submit(() -> consume(first));

            if (firstAttempt.get()) {
                throw new AssertionError("Expected a retry");
            }

            Future<Boolean> secondAttempt =
                    worker.submit(() -> consume(first.redelivered()));

            if (!secondAttempt.get()) {
                throw new AssertionError("Retry should succeed");
            }

            Future<Boolean> nextMessage =
                    worker.submit(() -> consume(second));

            if (!nextMessage.get()) {
                throw new AssertionError("Next message should succeed");
            }

            worker.submit(() ->
                    LOG.info("event=worker.idle")).get();
        } finally {
            restore(before);
            worker.shutdown();
        }
    }
}
```

### 6.4. Compile and Run

From the `message-correlation-demo` directory:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.MessageCorrelationDemo
```

**Expected nine application log lines:**

```text
INFO|cid=corr-42|mid=|event=message.published message_id=m-001
INFO|cid=corr-42|mid=|event=message.published message_id=m-002
INFO|cid=corr-42|mid=m-001|event=message.received attempt=1
WARN|cid=corr-42|mid=m-001|event=message.retry_scheduled
INFO|cid=corr-42|mid=m-001|event=message.received attempt=2
INFO|cid=corr-42|mid=m-001|event=message.processed payload=order.created
INFO|cid=corr-42|mid=m-002|event=message.received attempt=1
INFO|cid=corr-42|mid=m-002|event=message.processed payload=payment.authorized
INFO|cid=|mid=|event=worker.idle
```

Maven may print additional runner messages. The output above describes **application logs** when only the example's backend/configuration is loaded; it does not claim every terminal displays stdout and stderr identically.

### 6.5. Explaining the Output and Simulation Limits

1. The producer reads `MDC.get("correlation_id")` to put the ID into `Message.headers`. `message_id` is not placed into the producer's MDC; it is logged in the message via a placeholder, so `mid=` is empty on the first two lines.
2. `Map.copyOf` creates an unmodifiable copy of headers, preventing recipients from accidentally mutating the map after publishing.
3. The consumer on another worker gets the ID **from headers**, not from the producer's MDC.
4. `consume` saves the worker's previous MDC, sets `correlation_id` and `message_id`, processes the message, and **restores in `finally`**.
5. The first attempt of `m-001` is **simulated** as a temporary failure that schedules a retry. There is no real broker, ACK/nack, or queue delay in this example.
6. `redelivered()` preserves `messageId`, `payload`, and headers, only incrementing `attempt`. This is a **simulation convention**, not a claim that every broker preserves the same ID on republish.
7. `m-002` is a new message with its own ID, but shares `corr-42` because it belongs to the same correlated workflow.
8. `Future.get()` forces the main thread to wait for completion, making the line order predictable.
9. The `worker.idle` event runs on the **same worker thread** after the messages, with no leftover context: `cid=|mid=`. This visually verifies that MDC does not leak across worker reuse.

**Important learning point:** the example runs **in a single JVM**, yet the message boundary is still represented via an immutable envelope. In real Kafka/RabbitMQ/JMS, headers/properties are serialized and travel through the broker; producer and consumer do not share heap or MDC. The following sections explain how to wire this into real APIs.

## 7. Kafka: Propagating Correlation ID via Record Headers

In **Apache Kafka**, each `ProducerRecord` has headers; the consumer reads them from `ConsumerRecord`.

### Producer: Adding a Header to a Record

**Illustrative snippet**, assuming `KafkaProducer<String,String> producer`, `key`, `payload`, `correlationId`, and appropriate producer configuration already exist:

```java
import java.nio.charset.StandardCharsets;
import org.apache.kafka.clients.producer.ProducerRecord;

ProducerRecord<String, String> record =
        new ProducerRecord<>(
                "orders.events",
                key,
                payload);

record.headers().add(
        "correlation_id",
        correlationId.getBytes(StandardCharsets.UTF_8));

producer.send(record);
```

This is **not a standalone program**; it requires `kafka-clients`, a broker, serializers, a topic, and producer error/retry configuration. `ProducerRecord` accepts header values as bytes; the code explicitly uses UTF-8.

### Consumer: Reading the Header

```java
import java.nio.charset.StandardCharsets;
import org.apache.kafka.common.header.Header;

Header header =
        record.headers().lastHeader("correlation_id");

String correlationId = header == null
        ? null
        : new String(
                header.value(),
                StandardCharsets.UTF_8);
```

This is a snippet inside a callback/loop that already has `ConsumerRecord<?,?> record`. `lastHeader` retrieves the last value for that key name when a record has multiple headers with the same key. If the system requires **exactly one correlation header**, you should **check for duplicate/ambiguous headers** per policy rather than silently picking the last one in every case.

### Setting MDC During Processing

```java
Map<String, String> previous =
        MDC.getCopyOfContextMap();

try {
    String cid = validatedCorrelationId(record);
    MDC.put("correlation_id", cid);

    log.info("event=kafka.message.received");
    processRecord(record);
} finally {
    if (previous == null) {
        MDC.clear();
    } else {
        MDC.setContextMap(previous);
    }
}
```

This is an **illustrative snippet**; `validatedCorrelationId` and `processRecord` must be defined in the application. The `try/finally` block wraps the processing of **one record**. If processing a batch of multiple records on the same poll thread, you must swap the context properly for each record.

### Kafka Key, Offset, and Message ID Are Not the Same

- `record.key()` usually serves partitioning/ordering or business entity identification; it is not automatically a Correlation ID.
- `topic + partition + offset` identifies a Kafka record at a specific position, but a logical event republished to a retry topic or DLQ will have a new offset.
- An application-managed `event_id`/`message_id` header helps identify the same logical event across republishes.
- `correlation_id` links different events in a journey; do not use it as the sole deduplication key.

### Kafka Retry Topics and DLQ

If handling errors by **republishing** to a retry topic, you must decide on and **copy/allowlist important headers**:

```text
orders.events
  event_id=evt-1001
  correlation_id=corr-42
        |
        v
orders.retry
  event_id=evt-1001
  correlation_id=corr-42
  attempt=2
        |
        v
orders.dlq (if attempts exhausted)
  event_id=evt-1001
  correlation_id=corr-42
  attempt=3
  original_topic=orders.events
  failure_code=...
```

This is **an illustrative policy**, not automatic behavior in every Kafka framework. Some retry/DLT libraries have their own header conventions and may preserve or add information according to their mechanisms. Read your system's specific contract and test against it.

**Offset and ACK/commit** cannot be inferred from a Correlation ID. Committing offsets before processing completes can lose business work; committing after processing can result in redelivery if the consumer crashes. Use idempotency and an appropriate delivery strategy.

## 8. RabbitMQ/AMQP: Using `correlationId` in BasicProperties

With the RabbitMQ Java Client over AMQP 0-9-1, a message has **BasicProperties** including `correlationId` and `messageId`. Distinguish them:

- `correlationId`: used to correlate request/reply or a workflow per contract.
- `messageId`: a message identifier set by the producer/application if present; the broker does not necessarily auto-generate a standard ID for every publish.
- `headers`: holds other attributes per application convention, such as `event_id`, `schema_version`.

### Producer: Setting Properties

Illustrative snippet, assuming `Channel channel`, `byte[] body`, `correlationId`, `messageId`, and the exchange/routing key already exist:

```java
import com.rabbitmq.client.AMQP;

AMQP.BasicProperties props =
        new AMQP.BasicProperties.Builder()
                .correlationId(correlationId)
                .messageId(messageId)
                .contentType("application/json")
                .build();

channel.basicPublish(
        "orders.exchange",
        "order.created",
        props,
        body);
```

**This is not a standalone program**; it requires the RabbitMQ Java Client, connection/channel/exchange/routing configuration, and publisher confirms if you need to verify the broker received the message. Calling `basicPublish` alone does not guarantee end-to-end processing.

### Consumer: Reading Properties, Setting MDC, and ACKing Properly

```java
String cid =
        delivery.getProperties().getCorrelationId();
String mid =
        delivery.getProperties().getMessageId();

Map<String, String> previous =
        MDC.getCopyOfContextMap();

try {
    MDC.put("correlation_id", requireValid(cid));
    if (mid != null) {
        MDC.put("message_id", mid);
    }

    processDelivery(delivery);
    // ACK after successful processing according to the transaction policy.
} finally {
    if (previous == null) {
        MDC.clear();
    } else {
        MDC.setContextMap(previous);
    }
}
```

This is **illustrative code** inside a callback that already has `delivery`, `requireValid`, and `processDelivery`. `basicAck`/`basicNack`, redelivery, and DLX/DLQ must be organized according to the application's reliability contract; never ACK before critical processing completes just to get correlated logs.

### Request/Reply on RabbitMQ

A classic use case:

1. The client publishes a request with `correlationId=corr-42` and `replyTo`.
2. The responder processes the request and sends the reply to the `replyTo` address.
3. The reply carries the Correlation ID so the client can match the reply with the original request.

In request/reply, `correlationId` may directly serve **reply matching**, not just logging. Therefore, its value and lifecycle must follow the protocol contract; do not alter the ID when the responder sends the reply.

If the system also has a business correlation ID spanning multiple events, you may need to **separate the two fields** (RPC reply correlation and workflow correlation) to avoid mixing semantics.

## 9. JMS: `JMSCorrelationID` and Request/Reply Semantics

JMS provides the **`JMSCorrelationID`** header field. Example using the **Jakarta Messaging/JMS API**, a snippet using `JMSContext`:

```java
import jakarta.jms.JMSContext;
import jakarta.jms.Queue;
import jakarta.jms.TextMessage;

// context and queue are already provided by the framework/application.
TextMessage message =
        context.createTextMessage(payload);

message.setJMSCorrelationID(correlationId);
message.setStringProperty("event_code", "order.created");

context.createProducer().send(queue, message);
```

This is **not a complete program**; it requires a JMS provider, connection/session/context, destination, and variables `context`, `queue`, `payload`, `correlationId`. Depending on the system version, you may use the older `javax.jms` namespace or the newer `jakarta.jms`; do not mix both namespaces in the same runnable example.

Consumer reading:

```java
String correlationId =
        message.getJMSCorrelationID();

String eventCode =
        message.getStringProperty("event_code");
```

In request/reply flows, two conventions are common:

- The client generates the Correlation ID and the responder **copies** it to the reply.
- The responder sets the reply's Correlation ID to the **request's `JMSMessageID`**, per the application's request/reply contract.

**Do not assume the two conventions are equivalent.** Decide which approach to use first, then build the client matcher and tests accordingly. Do not replace provider-assigned `JMSMessageID` with a business Correlation ID just for log convenience.

### Message Properties Do Not Automatically Appear in Logs

Having an ID in a JMS header does not mean `MDC.get("correlation_id")` is populated in the consumer. The consumer/framework listener must **read the property and set up the logging context**, then clean it up when message processing finishes.

## 10. How Does Correlation ID Travel Through Retry, Redelivery, and Dead-Letter?

Messaging often operates under **at-least-once delivery** or experiences redelivery. You must separate:

- **Logical event/message:** a unit of work to be processed.
- **Delivery attempt:** one broker delivery of a message to a consumer.
- **Processing attempt:** one application execution of business logic, which may not map 1:1 to delivery.
- **Retry message:** may be a **new record** when the application republishes to another queue/topic.
- **DLQ/DLT:** where messages that fail processing according to policy are routed.

### Values That Should Stay Stable

| Attribute | Retry/Redelivery of Same Logical Event | When Creating a New Child Event |
| --- | --- | --- |
| `correlation_id` | Usually **preserved** | Usually inherited if in the same workflow |
| `event_id` / logical message ID | Preserved if still the same logical event | Generate a new ID for the new event |
| `delivery_attempt` / `attempt` | Changes per attempt, if reliably measurable | Starts according to the new event's policy |
| Broker offset/delivery tag | May change per broker/redelivery | Usually different |
| `event_code` | Kept or changed per retry semantics | Changes per child event type |
| `trace_id` / `span_id` | Per tracing/instrumentation policy | Do not assume the same span is kept |

**Do not assume `attempt=3` just because you see three log lines.** A collector may receive duplicates, a logger may log multiple times, or a message may be reprocessed after a crash. Reliable attempt counts should come from the framework/broker mechanism or application-controlled retry state.

### Direct Retry vs. Retry by Republishing

**Broker redelivery** may preserve the original message and metadata per protocol. **Republishing** may create a new record, so the application must copy headers/attributes via an allowlist. A resend method that only copies `payload` and drops headers will lose the Correlation ID:

```java
// Logic bug illustration: the new message has no correlation_id.
retryPublisher.send(originalPayload);
```

A better design is an **envelope** containing payload + allowlisted metadata and a copy/augment function for retries. Do not blindly copy untrusted headers or sensitive information.

### DLQ Must Retain Enough Information for Investigation

When a message enters a DLQ, it should have:

- Preserved Correlation ID if valid.
- Logical event/message ID to identify the work item.
- Event code/schema version.
- Original source (topic/queue/exchange/routing key) as permitted by data access rules.
- Normalized failure reason and attempt count if reliable.
- Timestamp/metadata needed for investigation, per schema.
- **Do not dump unbounded payloads or stack traces containing secrets.**

A DLQ entry with a Correlation ID but no logical message ID can link the flow, but makes it hard to decide which message already succeeded or needs replay.

### When Replaying from DLQ

A replay is **a new processing attempt of old data**, not necessarily a new business message. Keep the original ID for reconciliation, while optionally adding `replay_id` or `replay_attempt` so operators know it is a replay. Do not automatically replace the Correlation ID on every replay if the goal is to trace the same incident; if a replay starts a new business workflow, define that rule explicitly.

## 11. Asynchronous Producer/Consumer and MDC: Avoiding Leaks Across Messages

Thread pools reuse workers. For example, a consumer receives `m-001` and then `m-002` on the same thread. Without cleaning up MDC after `m-001`, logs for `m-002` may carry the stale `correlation_id` or `message_id`.

How to manage the scope:

```java
Map<String, String> previous =
        MDC.getCopyOfContextMap();

try {
    MDC.put("correlation_id", validatedCorrelationId);
    MDC.put("message_id", messageId);
    handler.process(message);
} finally {
    if (previous == null) {
        MDC.clear();
    } else {
        MDC.setContextMap(previous);
    }
}
```

This is an **illustrative snippet** inside a handler with existing variables. The snapshot/restore technique has several benefits:

1. Leaves no stale context on the worker after processing.
2. Works even when `handler.process` throws an exception.
3. Restores keys set by a parent framework/scope before the consumer scope began.
4. Prevents a child scope from accidentally wiping out the entire parent context with `MDC.clear()`.

However, if other instrumentation intentionally updates the parent context while the handler runs, restoring the snapshot could overwrite that update. Define **ownership and lifecycle** clearly in your actual design.

### A Callback May Switch Threads Again

A consumer callback may submit a follow-up task to `CompletableFuture` or another executor. In that case, the callback thread's MDC does not automatically propagate to the new worker:

```java
CompletableFuture.runAsync(() -> {
    log.info("event=async.task.started");
});
```

This is an illustrative snippet. If correlation needs to be preserved, use the framework's context propagation wrapper or snapshot at the submit boundary; the worker must restore the context upon completion. Do not use `InheritableThreadLocal` as a general solution for reused thread pools.

### Batch Consumers

If a listener receives a batch containing A, B, and C:

- Do not set the **first record's** Correlation ID for the entire batch if records can belong to different flows.
- For each record, set its own context, process, restore, and then move to the next record.
- Batch summary logs should have a `batch_id`; do not borrow an arbitrary record's `correlation_id` to represent the whole batch.
- If batch processing is asynchronous, attach context to each record task or equivalent propagation mechanism.

### Log4j 2 ThreadContext

If using Log4j 2 API/Core, you can use `ThreadContext.put("correlation_id", id)` and `ThreadContext.get`. This API is similar to MDC, though not automatically unified across every SLF4J provider. Choose one consistent logging API per architecture and verify the actual bridge/provider.

## 12. When a Consumer Publishes a New Message

This is where Correlation IDs commonly break:

```text
Producer A -- message m-001, cid=corr-42 --> Consumer B
                                              |
                                              +-- perform business logic
                                              |
                                              +-- publish m-002
                                                  missing cid  ❌
```

Consumer B must not only **read** correlation for logging; if processing generates a new event in the **same business flow**, B's publisher must **propagate it forward**:

```text
Producer A -- m-001, cid=corr-42 --> Consumer B
                                              |
                                              +-- m-002, cid=corr-42
                                                        |
                                                        v
                                                    Consumer C
```

An internal API can be designed as:

```java
record PublishContext(
        String correlationId,
        String causationId) {
}

void publishFollowUp(
        PublishContext context,
        BusinessEvent event) {
    // Map context into message headers according to the contract.
}
```

This is an **API sketch**, without a broker implementation. `causation_id` can point to the immediate parent event (e.g., `evt-1001`), while `correlation_id` links the whole journey. Both fields are useful in long, branching workflows.

### Do Not Rely Solely on Reading MDC in a Shared Publisher

A publisher library may be called from:

- An HTTP handler with MDC.
- A message consumer with MDC.
- A scheduled job without request context.
- A startup hook without correlation.
- An async callback where MDC was not propagated.

If the publisher strictly requires `MDC.get("correlation_id")`, it may lack an ID in the latter cases. A more robust design typically passes an explicit **PublishContext** at the boundary or uses a reliable context propagation abstraction, and then **projects** the ID to MDC only for logging.

MDC is an observability channel, **not a guaranteed source of business state**. For critical workflows, correlation should live in envelope/command metadata that business code can test.

## 13. Tracing Context and Correlation ID in Messages

A modern system may use both:

```text
correlation_id: corr-42
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
```

The `traceparent` above is an **example of W3C Trace Context structure**. OpenTelemetry/instrumentation APIs provide carrier inject/extract mechanisms (Kafka headers, AMQP properties, JMS properties) following semantic conventions and configured propagators.

**Two different propagation streams that can work together:**

- Correlation ID links workflows/logs per business convention.
- Tracing context enables spans/links, producer–consumer relationships, and latency analysis.
- The consumer can start a new span or link to the producer's context depending on instrumentation and processing model.
- A message may sit in a broker for a long time; never keep a span open just to "maintain the same correlation."

### Do Not Manually Parse `traceparent` with Arbitrary String Operations

A valid `traceparent` has format, version, and Trace ID/Span ID validity rules. Use the tracing SDK/propagator instead of slicing substrings, deriving a trace ID from a Correlation ID, or inferring from a single header alone.

### Baggage and Sensitive Information

Tracing baggage can propagate across multiple services and third parties. Do not put passwords, access tokens, payment data, or sensitive information into baggage/headers just for logging convenience. Use allowlists, size limits, and review trust boundaries before propagating.

## 14. Missing, Malformed, or Duplicate Correlation IDs

Not every legacy message has headers. Consumers must have a clear policy instead of throwing an NPE or grouping all headerless messages under a fake ID.

Common options depending on the system:

1. **Strict contract:** reject or route the message to a DLQ with error code `MISSING_CORRELATION_ID` when the field is required. Suitable when producers are expected to uphold the contract.
2. **Compatibility mode:** generate a new Correlation ID for missing messages and log a standardized event reporting the absence; useful during migration, though **it loses the link to the original source**.
3. **Nullable semantics:** allow standalone messages without correlation, logging the missing field without fabricating an ID; appropriate if correlation is truly optional.
4. **Backfill from trusted metadata:** if the envelope has another validated flow ID, map it according to published rules.

**Avoid defaulting to `correlation_id=unknown` for all missing messages**, as they will all be lumped together during log searches.

### Example Allowlist Validation

An internal policy might allow IDs up to 64 characters containing only letters, digits, dots, underscores, and hyphens:

```java
static boolean validCorrelationId(String value) {
    return value != null
            && value.length() >= 1
            && value.length() <= 64
            && value.matches("[A-Za-z0-9._-]+");
}
```

This is a snippet placed inside a Java class. If your project's actual IDs use UUID, ULID, or another format, design a matching validator; the snippet above is **not a validator for W3C Trace IDs**.

### Duplicate Headers

Some APIs allow multiple headers with the same name. If a producer sends two different `correlation_id` values, decide whether to:

- Reject the message due to ambiguity?
- Trust a signed/authenticated header from a trusted hop?
- Pick the first or last header per a specific contract?

**Do not arbitrarily pick the first or last header without a policy.** For example, Kafka's `lastHeader` has last-wins semantics; it is a convenience API, not a trust solution.

### Size Limits and Control Characters

An externally controlled header can contain multi-MB strings, newlines, or Unicode control characters. If written raw into text PatternLayout, log injection can forge lines that look like other events. Therefore:

- Validate and enforce length limits before putting values into MDC.
- Do not log invalid raw headers unescaped as part of a message.
- When diagnostics are needed, log the **failure reason/error category**, not the full raw value.
- For JSON Lines, use an encoder with standard escaping.
- Validate headers across trust boundaries, especially at public APIs/gateways.

A Correlation ID is a **lookup label**, not an authentication token.

## 15. Idempotency, ACK, and Exactly-Once: What Correlation ID Does Not Solve

Suppose a consumer receives `m-001`, calls the DB and succeeds, but crashes **before ACK/offset commit**. The broker may redeliver the same message. Both executions carry `corr-42`; that does not prevent charging a card or sending an email twice.

Different mechanisms:

| Mechanism | What It Solves | What It Does Not Guarantee on Its Own |
| --- | --- | --- |
| Correlation ID | Links logs of a workflow | Does not deduplicate |
| Message/event ID | Identifies a logical event | Does not store processed state |
| Idempotency store | Records processed events/operations | Must handle transactions and race conditions |
| ACK/offset commit | Confirms consumption progress to the broker | Not automatically atomic with external DB side effects |
| Retry policy | Retries transient failures | Does not guarantee no duplicates |
| DLQ | Isolates unprocessable messages | Does not fix data or preserve replayability on its own |
| Distributed tracing | Span relationships and timing | Does not replace delivery semantics |

**Correlation ID is not an exactly-once guarantee.** Even systems with transactional/exactly-once features within a broker scope do not automatically make all external side effects (HTTP, payment gateways, other DBs) exactly-once.

### A Conceptually Simple Idempotent Design

A consumer can record `event_id` in a deduplication table within the same transaction as the business data change. If the event ID has already been processed successfully, skip the side effect, while still logging `event=message.duplicate_skipped` with the Correlation ID.

This is an **architectural idea**, not a complete transaction implementation. Race conditions when two consumers process the same ID and side effects outside the DB must be handled separately.

### When to Generate a New Message ID?

- **Redelivery of the same record:** many brokers preserve the original record/delivery metadata; the logical ID can remain the same.
- **Republishing the same logical event to a retry topic:** usually keep `event_id` as the dedup key, even though the record/offset is new.
- **Emitting a different event due to successful processing:** generate a new `event_id`, keeping `correlation_id` if part of the workflow.
- **Replay of an old event:** distinguish the original `event_id` from `replay_id` if the business has new replay rules.

Do not use `correlation_id` as the sole key to decide whether an entire workflow has completed; one correlation ID typically spans many valid events.

## 16. Structured Logging for Effective Message Tracing

A text pattern:

```text
%level|cid=%X{correlation_id}|mid=%X{message_id}|%msg%n
```

helps developers see relationships clearly. However, for reliable querying and aggregation in a log store, output **separate fields** using an appropriate JSON encoder/layout:

```json
{
  "timestamp": "2026-01-01T00:00:00Z",
  "level": "WARN",
  "service": "billing-worker",
  "event_code": "message.retry_scheduled",
  "correlation_id": "corr-42",
  "message_id": "m-001",
  "attempt": 1,
  "broker": "kafka",
  "topic": "orders.events",
  "error_code": "UPSTREAM_TIMEOUT",
  "message": "Sẽ thử lại sau lỗi tạm thời"
}
```

This is an **illustrative schema**, not the default output of Logback/Log4j 2. Kafka-specific fields do not apply verbatim to RabbitMQ/JMS. Do not name fields `partition` or `offset` for messages that lack those concepts.

One way to emit event fields using the **SLF4J 2.x fluent API**:

```java
log.atWarn()
        .addKeyValue("event_code", "message.retry_scheduled")
        .addKeyValue("message_id", messageId)
        .addKeyValue("attempt", attempt)
        .addKeyValue("error_code", "UPSTREAM_TIMEOUT")
        .log("Sẽ thử lại sau lỗi tạm thời");
```

This is an application snippet. `correlation_id` can come from MDC, while `attempt` is passed as a number. **For key-values to actually become JSON fields**, the backend/encoder must support and enable them. Simply adding `addKeyValue` does not automatically turn a text PatternLayout into JSON.

### Writing Queries

Questions you can query with structured fields:

- Search by `correlation_id="corr-42"` to view the entire workflow.
- Search `message_id="m-001"` to compare attempts of the same message.
- Group `event_code="message.processing_failed"` by `error_code` to see common failures.
- Filter `service="billing-worker"` and `attempt >= 3` when hunting excessive retries.
- Find producer and consumer logs by the same Correlation ID to distinguish publish failures from consume failures.

Do not turn Correlation ID into a **high-cardinality metric label**. For aggregated metrics, typically group by `service`, `event_code`, `result`, or bounded `error_code` categories, reserving dynamic IDs for logs and traces.

## 17. Testing Correlation ID Propagation Across Messages

The most important test is **verifying metadata is transferred accurately from producer to consumer**, not just checking `MDC.get` within the same JVM.

### Test Matrix

| Scenario | What to Assert |
| --- | --- |
| Producer has valid context | Message header/property contains the right Correlation ID |
| Consumer receives valid message | MDC or event context carries the right ID during processing |
| New message published by consumer | ID is inherited if same workflow; new message ID |
| Retry of same logical event | ID unchanged; attempt changes per contract |
| Republish to retry topic | Headers copied properly; no required fields dropped |
| Message routed to DLQ | Correlation and event IDs remain queryable, with error reason |
| Message missing header | Strict reject or fallback per policy; no NPE |
| Malformed/oversized header | Safely rejected/normalized; no log injection |
| Duplicate header names with different values | Handled per duplicate policy; not chosen randomly |
| Worker thread reused | Message B does not carry A's MDC |
| Handler throws exception | `finally` cleanup/restore always runs |
| Async callback/CompletableFuture | Propagates across each boundary as designed |
| Batch with multiple Correlation IDs | Each record has its own context |
| JSON encoder | Correlation ID is a separate field, not just inside message text |
| Broker reconnect/rebalance | Does not lose context of an in-flight delivery |
| Collector or DLQ store | Queryable by ID with appropriate retention/permissions |
| Producer called outside HTTP | Has policy when context is missing; does not pick up stale ID |
| Duplicate delivery | Does not count two business operations just from two receive logs |

### 17.1. Producer Unit Tests

For Kafka/RabbitMQ/JMS, use a producer test double or appropriate test client to **capture the published message object** and inspect its headers/properties. Asserting only that a `getCorrelationId()` helper returns a value is insufficient; verify that **the publishing library receives the right headers/bytes**.

For Kafka, verify UTF-8 decoding of byte values, absence of conflicting duplicate headers, and presence on the actual record. For RabbitMQ, inspect `BasicProperties.getCorrelationId()`. For JMS, inspect `getJMSCorrelationID()`.

### 17.2. Consumer Unit Tests

Create a message with a fixed Correlation ID, pass it to the consumer handler, and capture logging events to verify:

- Correct `correlation_id` on the event.
- Correct `message_id`, `event_code`, and log level.
- When the handler throws an exception, cleanup still runs.
- Events emitted **after the scope** on the same worker do not carry the old ID.

With Logback, you can use `ListAppender<ILoggingEvent>` and inspect `getMDCPropertyMap()`. This tests the **event**, which does not prove console text encoding or collector ingestion.

### 17.3. Broker Integration Tests

In a test environment with a real or dedicated test broker:

1. Start producer and consumer over a real connection.
2. Set `correlation_id=corr-test-1` at a valid entrypoint.
3. Publish a message and verify metadata received at the consumer.
4. Trigger a retryable error; verify the ID across attempts.
5. Trigger conditions to route the message to a DLQ; verify the ID and provenance.
6. Publish message B with a different Correlation ID right after A; verify no context leak.
7. If the consumer publishes event C, verify C's headers keep the right ID.
8. If using tracing, verify `traceparent` via SDK/instrumentation.
9. Test idempotency on duplicate delivery, not just logging.
10. Follow the final message to the collector if that is part of the system contract.

### 17.4. Console/JSON Output Tests

For Logback text, verify the pattern includes `%X{correlation_id}`. For JSON, parse each line into an object and assert the type/value of `correlation_id`, `message_id`, and `attempt`.

Do not compare whole raw lines if they contain variable timestamps, thread names, or stack traces. For JSON, key order is not a contract; compare parsed fields.

### 17.5. Retry Tests Should Not Confuse Semantics

If the application logs:

```text
event=message.received attempt=1
event=message.received attempt=2
event=message.processed attempt=2
```

this may represent **two processing attempts of one logical event**, not three successful business events. Metric systems should use clear event codes and completion conditions for counting.

## 18. Diagnosing Common Issues

| Symptom | Common Cause | How to Check |
| --- | --- | --- |
| Producer logs have ID, consumer does not | Header/property not attached to message | Inspect actual message at producer and consumer. |
| Kafka consumer reads `null` | Wrong key name, missing header, or wrong API usage | Check record headers, encoding, and duplicate policy. |
| RabbitMQ reply does not match request | `correlationId` altered, missing, or client uses different convention | Compare request/reply properties and matcher. |
| JMS reply cannot be matched | Confusing `JMSMessageID` with `JMSCorrelationID` | Clarify the request/reply convention. |
| Retry has a new Correlation ID | Handler generates a new ID per attempt | Preserve original metadata across retries per contract. |
| DLQ is missing ID | Republish/DLX does not preserve metadata across pipeline | Inspect headers/properties at each hop and framework config. |
| Consumer B logs A's ID | MDC not cleaned up on worker thread | `finally` restore; test worker reuse. |
| Async handler loses ID | Context not propagated across executor/reactive boundary | Use wrapper or SDK propagation at the boundary. |
| Non-HTTP producer lacks ID | Relies solely on request MDC | Explicit PublishContext or boundary ID generation policy. |
| ID with newline creates fake log lines | Trusting raw header from external source | Validate, limit length, escape JSON properly. |
| Two headers with same key, different IDs | Multiple middlewares add headers | Clear duplicate/conflict policy. |
| JSON lacks `correlation_id` field | Encoder does not output MDC; wrong collector mapping | Check event map → encoder → collector. |
| Same ID, but not the same message | Correlation links the whole workflow | Use message/event ID to distinguish. |
| Processed twice despite same ID | At-least-once/redelivery; missing idempotency | Deduplicate by logical event ID and transaction policy. |
| Logs have ID, but history search finds nothing | Retention/collector, time filter, or permissions | Check pipeline and central log store. |
| Correlation ID leaked to third party | Header/baggage propagated too broadly | Enforce trust boundaries and allowlists. |
| Metric cardinality spikes | Adding Correlation ID as a metric label | Use event/error codes for metrics; IDs for logs/traces. |
| Span ID stays identical across services | Incorrect tracing context propagation or span reuse | Use instrumentation and inspect parent/span links. |

### Hop-by-Hop Investigation Flow

```text
Does the producer have a valid Correlation ID?
   |
   +-- No -> Entry boundary/context policy.
   |
   +-- Yes -> Attached to message header/property?
                |
                +-- No -> Publisher/serializer/interceptor.
                |
                +-- Yes -> Does consumer read the right header/value?
                             |
                             +-- No -> Key/encoding/transport/retry route.
                             |
                             +-- Yes -> Is MDC/context set in the right scope?
                                          |
                                          +-- No -> Consumer wrapper/lifecycle.
                                          |
                                          +-- Yes -> Does the logging event contain the ID?
                                                       |
                                                       +-- No -> Thread propagation/backend.
                                                       |
                                                       +-- Yes -> Does the encoder output the field?
                                                                    |
                                                                    +-- No -> Pattern/JSON config.
                                                                    |
                                                                    +-- Yes -> Does the collector receive/index it?
                                                                                 |
                                                                                 +-- No -> Pipeline/retention.
                                                                                 |
                                                                                 +-- Yes -> Query logs/traces by ID.
```

Seeing `MDC.get("correlation_id")` correct in one place does not prove metadata remains intact after a retry or downstream service. Checking **the exact hop where the ID is lost** is more effective than adding bulk debug logs.

## 19. Security and Production Operations

### Do Not Pass Sensitive Data for "Easy Correlation"

Correlation headers should only contain low-leakage IDs—never emails, phone numbers, user JWTs, session cookies, Authorization headers, or entire JSON requests. If you truly need to link a business object, use an ID permitted by data and access policies.

### Do Not Blindly Trust External Headers

HTTP clients, third-party publishers, or messages from queues without strict ACLs can send forged IDs. Format validation reduces log injection, **but does not authenticate permissions**. You may need to generate a new ID at the trust boundary and store the incoming ID as controlled diagnostic metadata if needed.

### Log Level and Error Code Policy

A Correlation ID is useful, but it is no reason to log every object at INFO. Maintain clear event codes for:

- `message.published`: publisher created/sent the event; does not necessarily mean the broker has finished handling it.
- `message.received`: consumer received a delivery.
- `message.retry_scheduled`: transient failure; retry scheduled per policy.
- `message.processed`: successful business outcome at the defined boundary.
- `message.processing_failed`: final or unrecoverable failure.
- `message.dead_lettered`: message routed to DLQ/DLT, if that action is confirmed.

**Do not emit `message.processed` before the critical transaction completes**, and do not treat `message.published` as proof of broker acknowledgment. If using publisher confirms/transactions, name events accurately to match the timing.

### Storage, Throughput, and Sampling

If a workflow has thousands of messages all sharing a Correlation ID, overly verbose logging can generate huge data volumes. Choose log levels, payload limits, and controlled sampling carefully. Ensure start, end, and key error/retry events are still captured per investigation requirements. A log event can be dropped by queues/appenders/collectors; Correlation IDs do not increase pipeline durability.

### Correlation Does Not Guarantee Strict Ordering

In multi-partition/multi-consumer systems, events with the same Correlation ID may be processed in parallel or ingested in a different order than execution time. Timestamps, broker offsets, and event sequences add context, but do not impose total ordering across the system. If the business requires ordering, design partition keys, consumer concurrency, and serialization under a separate contract.

## 20. Practice Exercises with Answers

### Exercise 1 — Where Does the Correlation ID Live?

A producer calls `MDC.put("correlation_id","corr-42")` and invokes the Kafka producer with only a JSON payload and no headers. Will the consumer automatically see `corr-42`?

**Answer:** No. MDC is local context; you must inject the Correlation ID into a Kafka record header or envelope per contract, and the consumer must extract and place it into its logging context.

### Exercise 2 — Two Messages, One Workflow

`m-001` and `m-002` share `correlation_id=corr-42`. Are they duplicate messages?

**Answer:** Not necessarily. They can be two distinct logical events in one business flow. Detecting duplicates requires a logical message/event ID and an idempotency policy.

### Exercise 3 — Retry of the Same Logical Event

`m-001` fails on attempt 1 and succeeds on attempt 2. How should `correlation_id` and `message_id` change?

**Answer:** By typical policy, keep the Correlation ID and logical message ID stable; increment the attempt. When republishing to a new topic, the broker record/offset may change even though the logical ID is preserved in metadata.

### Exercise 4 — RabbitMQ Request/Reply

A client publishes a request with `correlationId=corr-42`, and the responder sends a reply with a different Correlation ID. What can happen?

**Answer:** The client matcher may fail to match the reply to the original request if it relies on the client-set `correlationId`. Follow the request/reply convention; do not arbitrarily generate a new ID in the responder.

### Exercise 5 — JMS ID Confusion

A message has `JMSMessageID=ID:abc` and `JMSCorrelationID=corr-42`. Do the two fields mean the same thing?

**Answer:** No. `JMSMessageID` is the provider-assigned message identifier per JMS; `JMSCorrelationID` is for application/protocol correlation. In some request/reply conventions, the reply's Correlation ID may reference the request's message ID.

### Exercise 6 — Batch Containing Multiple IDs

A Kafka consumer polls a batch of two records with different Correlation IDs. Why is setting MDC from the first record for the entire batch wrong?

**Answer:** Logs for record B would be mislabeled with ID A. Set/restore context per record or task, and use a separate batch ID for batch summary logs.

### Exercise 7 — DLQ Without Metadata

A handler republishes a payload to a DLQ without copying headers. What becomes difficult?

**Answer:** You lose the Correlation ID, event ID, and original metadata; tracing the path, distinguishing retries, and reconciling replays becomes hard. You need a header copy/allowlist policy and tests against a real DLQ.

### Exercise 8 — Reading an ID from an Untrusted Source

A publisher sends a `correlation_id` header that is 100,000 characters long and contains newlines. Should it be put into MDC as-is?

**Answer:** No. Enforce format/length limits, check trust boundaries, and reject or replace the ID per policy; do not print raw headers that cause log injection.

### Exercise 9 — Preventing Duplicate Processing

Two deliveries of the same event both carry the same Correlation ID. Can you use a table keyed by Correlation ID to skip the second delivery?

**Answer:** Usually no. A workflow has many valid events sharing a Correlation ID. Deduplication should rely on a logical event/idempotency key defined for the operation, paired with an appropriate transaction mechanism.

### Exercise 10 — End-to-End Testing

Propose a test covering producer → broker → consumer → retry → DLQ.

**Suggested Answer:** Set a deterministic Correlation ID; inspect headers at the producer; verify consumer extraction and logged fields; intentionally trigger a transient failure for retry; verify the ID across retries; intentionally trigger a permanent failure for DLQ; ensure original metadata remains; run message B on the same worker to catch MDC leaks; parse JSON console/collector output to query by ID.

## 21. Design and Implementation Checklist

- [ ] Define which workflows use a Correlation ID and at which boundary it is created.
- [ ] Distinguish Correlation ID from Message ID, event ID, attempt, Trace ID, and Span ID.
- [ ] Choose a consistent header/property name and encoding for producers/consumers.
- [ ] Define policies for missing, empty, oversized, malformed, or duplicate headers.
- [ ] Producers attach Correlation ID **to the actual message**, not only to MDC.
- [ ] Consumers read from transport metadata and validate before placing into logging context.
- [ ] Listeners/callbacks restore/clear context in `finally` when finishing a message.
- [ ] Async tasks, retry callbacks, and worker pools propagate context properly.
- [ ] Child messages in the same workflow inherit Correlation ID; new event IDs follow semantics.
- [ ] Retries preserve required logical ID/context, with attempt counts tracked reliably.
- [ ] DLQ/DLT preserves Correlation ID, logical event ID, origin, and error for investigation.
- [ ] Request/reply follows RabbitMQ/JMS-specific conventions.
- [ ] If using tracing, use a standard tracing propagator to inject/extract `traceparent`.
- [ ] Do not blindly use Correlation ID as an idempotency key for an entire workflow.
- [ ] Plan for duplicate deliveries, ACK/commit, and transactions.
- [ ] Logging pattern or JSON encoder outputs IDs as text/fields per schema.
- [ ] Test producer headers, consumer MDC, subsequent messages, retries, DLQ, and collector.
- [ ] Do not log secrets/PII/raw headers; validate IDs from external sources.
- [ ] Do not add high-cardinality IDs as labels on aggregated metrics.
- [ ] Bound retention/volume and design log retrieval when containers/nodes disappear.
- [ ] Know how to detect and fix an ID dropped at a specific hop in the pipeline.

**Conclusion:** Propagating Correlation IDs across messages is an **end-to-end contract**: create or receive the ID at the boundary → inject into header/property/envelope → broker transports it → consumer extracts and validates → place into MDC/ThreadContext for the processing scope → restore when done → continue propagating when publishing child events, retries, or DLQ entries. Following these steps lets you trace a workflow across services and threads without conflating Correlation ID with Message ID, Trace ID, or deduplication.