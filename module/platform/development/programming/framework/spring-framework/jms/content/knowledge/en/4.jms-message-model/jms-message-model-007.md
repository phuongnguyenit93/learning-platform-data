# JMSMessageID, JMSTimestamp, and Provider-Generated Information

> **Goal:** understand **who creates each metadata field of a JMS message, when that field becomes meaningful, how to read it, and the limits of its semantics**. Focuses on `JMSMessageID` and `JMSTimestamp`, then expands to other headers/properties set by the JMS provider on send or prior to consumer delivery. Examples follow **Jakarta Messaging 3.1**, package `jakarta.jms` (Java 17+ / Spring Framework 6+ when using Spring). Legacy JMS systems may use `javax.jms`, though the core principles are similar.

## 1. Why Distinguish "Provider-Generated" from "Application-Generated"?

A message passes through three very different moments in time:

~~~text
Application creates TextMessage
  ├─ body: "OrderCreated"
  ├─ app property: eventId="evt-42"
  └─ JMSCorrelationID="req-21"          (set by application)
                 │
                 ▼
MessageProducer.send(message)
  ├─ provider assigns JMSMessageID
  ├─ provider assigns JMSTimestamp
  ├─ provider determines JMSDestination, JMSDeliveryMode, JMSPriority,
  │   JMSExpiration, and JMSDeliveryTime
  └─ broker receives/handles send per QoS and transaction
                 │
                 ▼
Consumer receives the same message
  ├─ reads headers assigned by provider on send
  ├─ provider marks JMSRedelivered if this is a redelivery
  └─ provider assigns JMSXDeliveryCount on receive
                 │
                 ▼
Application processes, writes data, ACK / commit
~~~

**Fundamental mistake:** seeing a `JMSMessageID` or `JMSTimestamp` and concluding that a business event occurred only once, that the message has already reached the consumer's database, or that the consumer has finished processing. Those fields help **identify, route, and observe a message**; they do not replace transactions, acknowledgments, or business state.

A JMS message consists of three parts:

| Part | Examples | Characteristics |
| --- | --- | --- |
| **Standard header** | `JMSMessageID`, `JMSTimestamp`, `JMSDestination`, `JMSCorrelationID` | Standard fields of the `Message` interface; each field has an authorized setter party |
| **Properties** | `eventId`, `schemaVersion`, `JMSXDeliveryCount` | Numeric, boolean, or String properties; some managed by application, some by provider |
| **Body** | `TextMessage` containing JSON | Business data; schema and interpretation are agreed upon by the applications |

`getPropertyNames()` lists **properties**, not standard JMS headers. `JMSMessageID` is read via `getJMSMessageID()`, not `getStringProperty("JMSMessageID")`.

## 2. Standard Header Ownership Table

The following table classifies fields per **Jakarta Messaging 3.1, `Message` headers**. Crucially, **a setter existing in the API does not mean the application is permitted to use that setter to dictate the value**.

| Field | Who sets it per spec? | When it is meaningful | Read with |
| --- | --- | --- | --- |
| `JMSMessageID` | Provider during send operation | After synchronous send completes; after async callback | `getJMSMessageID()` |
| `JMSTimestamp` | Provider during send operation | After send completes; after async callback | `getJMSTimestamp()` |
| `JMSDestination` | Provider during send operation | Target used for the send | `getJMSDestination()` |
| `JMSDeliveryMode` | Provider during send operation | Actual `PERSISTENT` or `NON_PERSISTENT` | `getJMSDeliveryMode()` |
| `JMSPriority` | Provider during send operation | Actual priority 0–9 | `getJMSPriority()` |
| `JMSExpiration` | Provider computed from TTL on send | Message expiration timestamp; 0 if no TTL set | `getJMSExpiration()` |
| `JMSDeliveryTime` | Provider computed from delivery delay on send | Earliest time delivery is permitted | `getJMSDeliveryTime()` |
| `JMSRedelivered` | Provider before delivering to consumer | Hint that the message is being redelivered | `getJMSRedelivered()` |
| `JMSCorrelationID` | Application | Pairing request/reply or correlation trace | `getJMSCorrelationID()` |
| `JMSReplyTo` | Application | Expected destination for replies | `getJMSReplyTo()` |
| `JMSType` | Application | Message type per convention/provider | `getJMSType()` |

Setters like `setJMSMessageID`, `setJMSTimestamp`, `setJMSPriority`, and `setJMSExpiration` are **public so providers can interoperate with other message implementations**, not as client message-configuration APIs. If an application calls them **before send**, those values are **ignored and overwritten with provider-determined values**. To change delivery mode, priority, TTL, or delivery delay, configure `MessageProducer` / `JMSProducer` or use the corresponding `send` overload.

**Valid exceptions:** `setJMSCorrelationID`, `setJMSReplyTo`, and `setJMSType` are setters applications may call before send. Do not manually populate timestamp or message ID hoping to "preserve the ID"; the provider controls those fields.

## 3. JMSMessageID: Provider-Assigned Identifier for a Single Send

### 3.1. Exact Meaning

`JMSMessageID` is a `String` issued by the provider to identify a **sent message**. Important specification rules:

1. When a message is newly created, there is no reason to assume an ID already exists.
2. During `send`, **any prior value in this field is ignored**; when synchronous `send` **returns successfully**, the field holds the provider-issued ID if ID generation is enabled.
3. Every standard message ID must start with the prefix **`ID:`**. **Everything after the prefix is provider-defined**: it may be digits, a UUID, or another opaque value; do not parse it assuming a fixed format.
4. The exact uniqueness scope is **defined by the provider**, at minimum across an installation of interconnected provider routers. **There is no global uniqueness guarantee across different vendors or two independent installations.**
5. The ID is an **opaque identifier**: do not infer creation time, broker address, publication order, or partition key solely from the string's contents.

Illustrative ID example only, **not a predictable runtime value**:

~~~text
ID:4bb10a9d-6e10-4ac4-a150-bef5cabcd123
~~~

When a system bridges across two providers, republishes messages, or clones events to send to multiple destinations, do not assume the JMS ID remains intact across every boundary. To link publications representing the same business meaning, add an application-controlled **`eventId` / `businessMessageId`**.

### 3.2. Message ID Differs from Business ID

| Identifier type | Who issues it | When it stays stable | Used for |
| --- | --- | --- | --- |
| `JMSMessageID` | JMS provider on send | Per sent message within provider scope; may change if application re-sends as a new message | Broker/client tracing; matching replies via request message ID within same JMS domain |
| `eventId` / `commandId` | Event/command publishing application | **Constant across retries of the same business event** | Idempotency, deduplication, business auditing |
| `orderId` | System of record | Per order record | Linking multiple events to the same entity |
| `JMSCorrelationID` | Application | Per request/reply or workflow correlation convention | Pairing exchanges, tracing multiple messages |

Confusing scenario:

~~~text
Send attempt A: eventId = evt-42 ; JMSMessageID = ID:aaa
        send succeeded, yet producer lost connection before confirmation
Retry attempt B: eventId = evt-42 ; JMSMessageID = ID:bbb
        consumer may receive both A and B
~~~

These are **two messages sent by the producer** yet only **one business event**. The consumer needs to key on `eventId` with transactions/idempotency so the same mutation is not applied twice. Conversely, when the **broker redelivers the same message** after rollback or failure, the JMS ID typically continues identifying the same message, yet the ID alone still does not prove business side effects never occurred.

### 3.3. When Is JMSMessageID Absent?

`MessageProducer.setDisableMessageID(true)` and `JMSProducer.setDisableMessageID(true)` are optimization **hints**; message IDs are **enabled by default**.

- If the provider **honors** the hint, `getJMSMessageID()` will be **`null`**.
- If the provider **ignores** the hint, it still generates an ID normally.
- This is neither a flag the provider is forced to obey nor a way to force a client-chosen ID.

Do not enable it if tracing, request/reply, tests, or operational tools rely on IDs. Even when IDs are always present, do not use them instead of `eventId` to guarantee exactly-once business effects.

## 4. JMSTimestamp: Time Message Was Handed to Provider for Sending

`JMSTimestamp` has type **`long`**, measured in **milliseconds since 1970-01-01T00:00:00Z (Unix epoch)**. It represents **when the message was handed over to the provider to be sent**. Specifically, for synchronous `send`, the value is set between **the send call and when send returns** (unless timestamping is disabled via hint).

A timeline:

~~~text
10:00:00.000  producer creates TextMessage in RAM
10:00:00.200  producer calls send
10:00:00.210  JMSTimestamp is assigned (illustrative)
10:00:00.450  synchronous send returns
10:00:03.000  JMS transaction finally commits (if any)
10:00:05.500  consumer receives message
10:00:05.800  consumer starts processing
10:00:06.100  business DB commit
~~~

**`JMSTimestamp` is not** when the application created the object, when the broker flushed to disk, when the JMS transaction committed, when the consumer received it, or when business processing finished. Its value can precede commit by many seconds; asynchronous sends or client/provider buffering make the gap even clearer.

### 4.1. Converting Epoch Milliseconds to Human-Readable Time

Java 17+ can convert with an explicit time zone:

~~~java
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZonedDateTime;

public class ReadJmsTimestamp {
    public static void main(String[] args) {
        long millis = 1_700_000_000_000L;
        Instant instant = Instant.ofEpochMilli(millis);
        ZonedDateTime vietnam = instant.atZone(
                ZoneId.of("Asia/Ho_Chi_Minh"));

        System.out.println(instant);
        System.out.println(vietnam);
    }
}
~~~

Save in `ReadJmsTimestamp.java` and run:

~~~bash
javac ReadJmsTimestamp.java
java ReadJmsTimestamp
~~~

Exact result for the fixed timestamp above:

~~~text
2023-11-14T22:13:20Z
2023-11-15T05:13:20+07:00[Asia/Ho_Chi_Minh]
~~~

**Do not accidentally divide by 1,000 twice.** `Instant.ofEpochMilli` takes milliseconds; JMS timestamp data does not carry a separate time zone. Time zones appear **only when formatting for display**. If `getJMSTimestamp() == 0` because the provider honored the disable-timestamp hint, do **not** display that as "1970, when the message was created", because 0 in that case means **timestamp unavailable**.

### 4.2. JMSTimestamp and Measuring Latency

You can compute an approximate measurement:

~~~java
long sentMillis = message.getJMSTimestamp();
long observedMillis = System.currentTimeMillis();
if (sentMillis > 0) {
    long approximateAgeMillis = observedMillis - sentMillis;
    System.out.println("Approximate message age ms = "
            + approximateAgeMillis);
}
~~~

This is a **code snippet inside a consumer method** where `message` is `jakarta.jms.Message`; imports and `JMSException` handling belong in the enclosing method. The value can be negative or skewed when producer/consumer/provider clocks drift, system clocks are adjusted, messages traverse a bridge, or receivers run in environments with different latencies. **Do not** call this an exact "broker processing time" metric. When reliable tracing is required, record client event creation time, send time, enqueue, delivery, consumer start, and DB commit using standardized telemetry; use a monotonic clock to measure **durations within the same process**.

### 4.3. Disabling Timestamp Is a Hint, Not an SLA

~~~java
producer.setDisableMessageTimestamp(true);
producer.send(message);

long timestamp = message.getJMSTimestamp();
~~~

After synchronous `send` succeeds:

- Provider **honors** the hint → `timestamp == 0`.
- Provider **ignores** the hint → timestamp remains normal epoch milliseconds.

Timestamping is **enabled** by default. Do not disable it when the system needs timestamps for message-age diagnostics, auditing, or correlation. In particular, **never rely on disabling timestamps to control TTL**: TTL and `JMSExpiration` have their own provider calculation mechanism.

## 5. Other Headers Computed by Provider on Send

### 5.1. JMSDestination — Where Was the Message Sent?

`getJMSDestination()` returns the destination object of the send (queue/topic). With a bound `MessageProducer`, it reflects the producer's destination; with an unidentified producer, it reflects the destination passed to `send(destination, message)`. The provider sets it on send; any pre-send value is ignored.

Do not assume `Destination.toString()` is a portable queue name across providers. To retrieve the name via API, check its type:

~~~java
Destination destination = message.getJMSDestination();
if (destination instanceof Queue queue) {
    System.out.println("Queue: " + queue.getQueueName());
} else if (destination instanceof Topic topic) {
    System.out.println("Topic: " + topic.getTopicName());
}
~~~

This is a snippet with `message` of type `jakarta.jms.Message`, importing `jakarta.jms.Destination`, `Queue`, `Topic`; `getQueueName/getTopicName` can throw `JMSException`. Be careful with bridges or aliases: physical/binding names on the broker may differ from the identifier the application expects.

### 5.2. JMSDeliveryMode — Actual Mode

`getJMSDeliveryMode()` reflects the `DeliveryMode.PERSISTENT` or `DeliveryMode.NON_PERSISTENT` used on send, whether via producer settings, `send` overload, or administrative override (if supported by the broker). `PERSISTENT` is the producer default in the JMS API.

~~~java
int mode = message.getJMSDeliveryMode();
String label = mode == DeliveryMode.PERSISTENT
        ? "PERSISTENT"
        : "NON_PERSISTENT";
~~~

The snippet above uses `jakarta.jms.DeliveryMode`. **PERSISTENT does not prove the consumer processed the message.** It requests durability guarantees within spec/provider limits; operations still depend on transactions, storage, HA, TTL, quotas, and downstream systems.

### 5.3. JMSPriority — Delivery Priority, Not Strict Ordering

`getJMSPriority()` ranges from **0–9**, default **4**, set by the provider per actual QoS on send. You can use `producer.setPriority(8)` or `send(message, DeliveryMode.PERSISTENT, 8, ttl)` to request a priority. JMS **does not require providers to enforce strict priority ordering** and does not guarantee "higher priority finishes processing sooner"; concurrency, backlogs, redeliveries, selectors, and consumer performance also affect execution.

### 5.4. JMSExpiration — Expiration Timestamp from Time-to-Live

The application configures `timeToLive` on the producer or via a `send` overload (in **milliseconds**). The provider computes:

~~~text
TTL > 0:
JMSExpiration ≈ send time + TTL

TTL = 0:
JMSExpiration = 0   (no TTL expiration set)
~~~

In a **transacted session**, expiration is calculated from **when the application sends**, not from **when the transaction commits**. If a producer sends and waits 40 seconds before committing while TTL is only 10 seconds, the message may already be expired when the transaction completes.

Per the specification, providers **should** discard undelivered messages upon expiration, yet **expiry precision is not strictly defined**; consumers must not rely on the assumption "it is impossible to receive an expired message under any circumstance". For business-critical deadlines, check expiration **in the consumer**, separate from broker expiry policies.

### 5.5. JMSDeliveryTime — Earliest Time Delivery Can Occur

`JMSDeliveryTime` is a Unix millisecond timestamp computed by the provider from **send time + delivery delay**, also measured from send before commit when inside a transaction. A producer may call:

~~~java
producer.setDeliveryDelay(5_000L);  // request not to deliver before 5 seconds
producer.setTimeToLive(30_000L);    // message has 30-second TTL
producer.send(message);             // uses both settings above
~~~

**After send**, `message.getJMSDeliveryTime()` gives the earliest eligible delivery timestamp; this is **not** actual delivery time or processing latency. If TTL is shorter than delay, the message can expire before ever becoming eligible for delivery.

QoS values configured administratively on the provider can **override** application mode, priority, TTL, or delay if the provider supports overrides. When an override occurs, header fields must reflect the administratively applied values; thus comparing client config against post-send/consumer headers is a useful diagnostic check.

## 6. Metadata Set by Provider on Consumer Receive: JMSRedelivered and JMSXDeliveryCount

### 6.1. JMSRedelivered Is Not Part of Send

`JMSRedelivered` is set by the provider **before delivering to a consumer**; it is meaningless on a just-sent message. When `getJMSRedelivered() == true`, it signals that the message **may have been delivered previously without being ACKed/committed**. Consumers should guard against duplicate side effects.

However, `false` **does not prove** duplicate business effects never occurred from a new producer send, bridge, or edge case. What matters is idempotency checks keyed on a **business event ID**, not relying solely on this flag.

### 6.2. JMSXDeliveryCount Is a Standard Property, Not a Header

`JMSXDeliveryCount` is a **mandatory provider-assigned property on receive** per Jakarta Messaging 3.1:

| Value | Interpretation |
| --- | --- |
| `1` | First delivery according to provider information |
| `2` or higher | Message has been redelivered at least once |
| When `JMSRedelivered=true` | `JMSXDeliveryCount` must be **2 or higher** |

Read with:

~~~java
int attempts = message.getIntProperty("JMSXDeliveryCount");
boolean redelivered = message.getJMSRedelivered();
~~~

**Do not treat the count as exact across every failure**: the specification does not require providers to persist the count durably across all server crashes. Do not use `JMSXDeliveryCount` as a unique key, do not use it to prove how many times business logic committed, and do not rely on selectors over properties **assigned by the provider at receive time** because selector behavior on them is undefined by the spec.

### 6.3. Additional JMSX Properties That May Appear

JMS defines the `JMSX...` property group:

| Property | Set by | Support level | Notes |
| --- | --- | --- | --- |
| `JMSXDeliveryCount` | Provider on receive | **Mandatory** | Delivery attempt count, with accuracy limits on crashes |
| `JMSXUserID` | Provider on send | Optional | Sender identity per provider |
| `JMSXAppID` | Provider on send | Optional | Application identity per provider |
| `JMSXProducerTXID` | Provider on send | Optional | Producer transaction ID |
| `JMSXConsumerTXID` | Provider on receive | Optional | Consumer transaction ID |
| `JMSXRcvTimestamp` | Provider on receive | Optional | Time provider delivered to consumer |
| `JMSXGroupID`, `JMSXGroupSeq` | Application | Spec-supported when using grouping | Message ordering/grouping per provider mechanism |

Some providers also define vendor-specific properties prefixed with `JMS_<vendor_name>`. Do not assume they exist on other brokers or treat vendor-specific fields as portable metadata. You can inspect `ConnectionMetaData.getJMSXPropertyNames()` to see which JMSX names a connection supports, while still checking each message.

## 7. Distinguishing Provider Metadata from Client Metadata

`JMSCorrelationID` is **not auto-generated by the provider on every send** like `JMSMessageID`. The application sets it before sending to link requests with responses or connect workflow steps.

Request–reply example:

~~~text
Producer sends Request A
  ├─ JMSMessageID     = ID:req-A-123   (assigned by provider on send)
  └─ JMSReplyTo       = reply.queue    (set by application before send)

Consumer receives Request A
  └─ sends Response B with:
       JMSMessageID   = ID:res-B-456   (newly assigned by provider)
       JMSCorrelationID = ID:req-A-123 (copied by application from request)
~~~

These are merely **illustrative strings**, not real provider-generated IDs. When `JMSCorrelationID` carries a provider message ID, the `ID:` prefix is valid. If the application uses its own correlation string, **do not manually prepend `ID:`** to self-generated strings: the specification reserves that prefix for provider-issued IDs. Byte-array correlation IDs are a special case and are not portable across all JMS providers.

Applications can also set their own metadata:

~~~java
message.setJMSCorrelationID("checkout-request-42");
message.setJMSType("OrderCreated");
message.setStringProperty("eventId", "evt-42");
message.setLongProperty("eventOccurredAtMillis", 1_700_000_000_000L);
~~~

`eventOccurredAtMillis` is the business occurrence timestamp attested by the application; it does not have to equal `JMSTimestamp`. Business property names should be clear, versioned, and documented in a contract. For exactly-once business effects, consumers need transactions paired with a unique constraint on (`consumerName`, `eventId`) or an equivalent idempotency mechanism; `JMSMessageID` cannot substitute for that.

## 8. When Is It Safe to Read: Before Send, After Send, Async, Transactions

| Stage | `JMSMessageID` / `JMSTimestamp` | Other provider-on-send headers | `JMSRedelivered` / `JMSXDeliveryCount` |
| --- | --- | --- | --- |
| Message just created | Not yet issued for the current send | Does not yet reflect any send | Not yet meaningful |
| Building message before send | Do **not** set manually | Do not set directly on `Message` | Do not set manually |
| Synchronous `send` **returns successfully** | Safe to read provider-assigned values; ID may be null / timestamp 0 if hint honored | Safe to read | Do not infer consumer state |
| Asynchronous `send` **just returned** | **Do not read yet** | **Do not read yet** | Not yet meaningful |
| `CompletionListener` invoked | Safe to read after completion callback; check success vs. failure branch | Safe to read after callback; on failure, do not assume full metadata | Not yet delivery semantics |
| Send ran, JMS transaction not yet committed | Send headers already computed | Headers may hold values | **Does not prove message is visible to consumers** |
| Consumer receives message | Reads metadata of received message | Reads send-set metadata | Provider adds delivery/attempt info |

**Dangerous bug with async send:** immediately after `producer.send(message, completionListener)` returns, the application must not read or mutate the message while the provider is still processing it. Access provider-on-send fields only after `CompletionListener` has been invoked; on success, `onCompletion` is the right place to log. On async failure, do not assume the message definitely never reached the broker; the connection may have dropped while the acknowledgment was on its way back.

`JMSMessageID`/`JMSTimestamp` are metadata of the send operation; **JMS transaction commit** and **consumer acknowledgment/DB commit** are separate boundaries. With local JMS transactions, never treat header values visible **before commit** as proof that a message was successfully published.

## 9. End-to-End Example in Spring Boot 3.x: Reading Before and After Send

The example uses **Java 17+**, **Spring Boot 3.x**, **Spring JMS/Jakarta Messaging**, and a **configured JMS provider and broker**. You can use the `org.springframework.boot:spring-boot-starter-artemis` dependency with a compatible Artemis broker, connection settings, and destination `jms.header.demo` ready per broker policy.

File `src/main/java/com/example/jmsheaders/JmsHeadersApplication.java`:

~~~java
package com.example.jmsheaders;

import java.time.Instant;
import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.MessageProducer;
import jakarta.jms.Queue;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@SpringBootApplication
@EnableJms
public class JmsHeadersApplication {
    public static void main(String[] args) {
        SpringApplication.run(JmsHeadersApplication.class, args);
    }

    @Bean
    ApplicationRunner publishSample(ConnectionFactory connectionFactory) {
        return args -> {
            try (Connection connection = connectionFactory.createConnection();
                 Session session = connection.createSession(
                         false, Session.AUTO_ACKNOWLEDGE)) {

                Queue queue = session.createQueue("jms.header.demo");
                try (MessageProducer producer = session.createProducer(queue)) {
                    producer.setTimeToLive(120_000L);
                    producer.setDeliveryDelay(1_000L);
                    producer.setDisableMessageID(false);
                    producer.setDisableMessageTimestamp(false);

                    TextMessage message = session.createTextMessage(
                            "Hello from producer");
                    message.setStringProperty("eventId", "evt-demo-001");
                    message.setJMSCorrelationID("request-demo-001");

                    // Do not rely on provider headers before send.
                    producer.send(message);

                    System.out.println("Producer eventId="
                            + message.getStringProperty("eventId"));
                    System.out.println("Producer JMSMessageID="
                            + message.getJMSMessageID());
                    System.out.println("Producer JMSTimestamp="
                            + describeTime(message.getJMSTimestamp()));
                    System.out.println("Producer JMSExpiration="
                            + message.getJMSExpiration());
                    System.out.println("Producer JMSDeliveryTime="
                            + message.getJMSDeliveryTime());
                }
            }
        };
    }

    static String describeTime(long millis) {
        return millis == 0L ? "unavailable"
                : Instant.ofEpochMilli(millis).toString();
    }
}

@Component
class HeaderConsumer {
    @JmsListener(destination = "jms.header.demo")
    public void handle(Message message) throws JMSException {
        System.out.println("Consumer JMSMessageID="
                + message.getJMSMessageID());
        System.out.println("Consumer JMSTimestamp="
                + JmsHeadersApplication.describeTime(
                        message.getJMSTimestamp()));
        System.out.println("Consumer JMSCorrelationID="
                + message.getJMSCorrelationID());
        System.out.println("Consumer eventId="
                + message.getStringProperty("eventId"));
        System.out.println("Consumer JMSRedelivered="
                + message.getJMSRedelivered());
        System.out.println("Consumer JMSXDeliveryCount="
                + message.getIntProperty("JMSXDeliveryCount"));
    }
}
~~~

**How to run:** start a compatible broker, configure `ConnectionFactory` for Spring Boot, create/allow auto-create for the queue per broker policy, and run the application. You can observe both producer and consumer log groups; because the listener runs asynchronously, **line ordering across the two groups has no global guarantee**.

**There is no fixed stdout:** `JMSMessageID` is provider-assigned; timestamps depend on run time; `JMSExpiration` and `JMSDeliveryTime` are live timestamps. `JMSXDeliveryCount` for a first-time message is typically 1, though listener receive order and errors/retries vary at runtime. If the broker is unreachable, the application can fail immediately on send with no success logs to observe.

**Why this example is valid:**

1. `ConnectionFactory` is configured and injected by Spring Boot/provider; using direct JMS API gives access to read the `TextMessage` object **after send**. `connection.start()` is **not required for a pure send operation**.
2. `Session.AUTO_ACKNOWLEDGE` on the **sending** session does not prove consumer ACK. It is a receive-related property, not an end-to-end synchronous signal.
3. `setDisableMessageID(false)` and `setDisableMessageTimestamp(false)` keep both observational fields **requested enabled**; provider-assigned values are read after `send` returns.
4. `setTimeToLive(120_000L)` and `setDeliveryDelay(1_000L)` produce comparable timestamps. Delivery time is the **earliest eligible delivery time**, not a guarantee the consumer receives it at exactly 1 second.
5. `@JmsListener` receives `jakarta.jms.Message`, allowing headers and properties to be read without converting the message to `String` early.
6. The listener can be extended to parse the body, though this lesson inspects metadata only. To test redelivery, configure a **transacted listener session** and trigger a controlled processing error; do not assume exceptions trigger retries on every container mode.

### Why Not Read the ID Inside Spring MessageCreator / MessagePostProcessor?

Spring example:

~~~java
jmsTemplate.send("jms.header.demo", session -> {
    TextMessage m = session.createTextMessage("Hello");
    // Here the message is still being CREATED, not yet sent.
    // m.getJMSMessageID() is not yet the ID of the upcoming send.
    return m;
});
~~~

Similarly, `JmsTemplate.convertAndSend(...)`'s `MessagePostProcessor` runs during message preparation before sending. **Do not place audit logic for the provider-assigned `JMSMessageID` at this step**. `JmsTemplate.send(...)` returns `void`; if you need post-send metadata, use classic JMS API inside an appropriately managed session context or capture it at the consumer/broker/tracing layer. Do not open connections outside Spring's transaction context without understanding the difference.

## 10. Asynchronous Send Example: The Callback Is the Information Boundary

The following snippet sits **inside a method that already has `MessageProducer producer` and `Message message`**, with `jakarta.jms.CompletionListener`:

~~~java
producer.send(message, new CompletionListener() {
    @Override
    public void onCompletion(Message completed) {
        try {
            System.out.println(
                    "Async JMSMessageID=" + completed.getJMSMessageID());
            System.out.println(
                    "Async JMSTimestamp=" + completed.getJMSTimestamp());
        } catch (JMSException ex) {
            System.err.println("Cannot read send metadata: "
                    + ex.getMessage());
        }
    }

    @Override
    public void onException(Message failed, Exception cause) {
        System.err.println("Async send failed: " + cause.getMessage());
    }
});
~~~

Only after the callback is invoked may you inspect provider-on-send headers or reuse the message object. This snippet is not standalone (it requires imports, connection/session/provider, and lifecycle management). **Do not close producer/session/connection inside the callback** and do not call `commit/rollback` on the session owning the callback. If the application exits or ignores exception callbacks, publish failure information can be lost. When using async senders, explicitly design lifecycle, backpressure, metrics, and retry/outbox handling.

## 11. Three Scenarios Where Metadata Must Be Cross-Checked Against Business Truth

### Scenario A — Producer Retries Because No Response Was Seen

~~~text
Producer send(eventId=evt-42)
    broker received it (JMSMessageID=ID:first)
    but producer timed out
Producer retry(eventId=evt-42)
    broker receives new copy (JMSMessageID=ID:second)
Consumer processes both copies
~~~

Two different `JMSMessageID`s do not mean two different business events. A stable `eventId`, unique constraint, and business transaction are the appropriate deduplication controls.

### Scenario B — Broker Redelivers Because Consumer Rolled Back

~~~text
Message ID: ID:first ; eventId=evt-42
  1st receive: JMSXDeliveryCount=1, JMSRedelivered=false (typical)
  processing error / JMS rollback
  2nd receive: JMSXDeliveryCount>=2, JMSRedelivered=true
~~~

`JMSMessageID` may remain the same ID for a redelivered message. However, the consumer might have committed its **DB** before the JMS rollback; thus "redelivered" does not automatically mean the DB remained untouched. Moreover, delivery count is not strictly guaranteed across server failures.

### Scenario C — Timestamp, TTL, and Transactions

~~~text
t = 0s: send with TTL = 5s, JMSTimestamp approximately t = 0s
t = 3s: JMS transaction has still not committed
t = 7s: commit
           → JMSExpiration was already calculated from t = 0s
           → message may have expired before consumer receives it
~~~

`JMSTimestamp` does not wait for commit, and `JMSExpiration` is not recalculated from commit either. If an application fails to receive a message, check **expiry, transaction, delay, broker policy, consumer selector, and DLQ** before concluding it is a provider bug.

## 12. Logging, Tracing, and Controlled Testing

Useful publish and consume logs should record the **same field names** for easy correlation:

| Log field | Source | Practical value |
| --- | --- | --- |
| `eventId` / `commandId` | Client property/body | Links retries, deduplication, and business outcome |
| `jmsMessageId` | `getJMSMessageID()` | Look up message in broker, when available |
| `jmsTimestampEpochMs` | `getJMSTimestamp()` | Provider send time, when non-zero |
| `jmsDestination` | `getJMSDestination()` | Send/receive target, normalized per provider |
| `jmsCorrelationId` | `getJMSCorrelationID()` | Trace workflows / request–reply |
| `jmsExpiration` / `jmsDeliveryTime` | JMS headers | Understand expiration and delivery delay |
| `jmsRedelivered` / `jmsxDeliveryCount` | Provider on receive | Observe redelivery attempts |
| `consumerResult` | Application | Success, error, DB transaction/side effect |

To keep logs safe, never log credentials, tokens, sensitive payloads, or uncontrolled PII. Protect log access, standardize time zones (typically UTC), and measure clock skew. Do not assume global uniqueness of `JMSMessageID` as the foundation of an audit system spanning multiple providers.

### Hands-On Lab Checklist

1. **Before/after send reads:** create a message, read ID/timestamp before sending to see why pre-send state cannot serve as proof; perform synchronous send, log ID/timestamp/destination/delivery mode/priority/expiration after send and in the consumer.
2. **Disable hints:** test `setDisableMessageID(true)` and `setDisableMessageTimestamp(true)` in a test environment. Note the exact provider/version and observe whether it honors or ignores the hints; never claim all brokers behave identically.
3. **Producer retry:** re-send the same `eventId` as a new JMS send; verify `JMSMessageID` changes while the consumer deduplicates via `eventId`.
4. **Consumer redelivery:** configure a transacted JMS listener to throw an error before commit. Observe `JMSRedelivered` and `JMSXDeliveryCount`, then verify DB side effects do not duplicate.
5. **TTL/delay/commit:** send with a short TTL, long delay, or hold a transaction before commit; inspect `JMSExpiration` and `JMSDeliveryTime`, and observe provider expiry behavior.
6. **Time zones:** convert `JMSTimestamp` to UTC and `Asia/Ho_Chi_Minh` using `Instant`; simulate clock skew to show why subtracting two wall-clock timestamps yields only approximate latency.
7. **Request–reply:** send a request with `JMSReplyTo`, have the consumer create a new response and set `JMSCorrelationID` to the request's `JMSMessageID`; verify the response gets **its own `JMSMessageID`**.

**Minimum evidence after each test:** provider configuration and mode, business ID, JMS ID, timestamp/TTL, consumer delivery count, DB transaction outcome, and observed trace/logs. Avoid interpreting "message has an ID" as proof the entire workflow succeeded.

## 13. Misconceptions to Eliminate

1. **"Creating a TextMessage already populates standard ID/timestamp."** Send headers are assigned by the provider during send; reading before send proves nothing about the message to be published.
2. **"Because `setJMSMessageID` exists, the client can pick its own ID."** The setter is for provider interoperability; client-set values before send are ignored.
3. **"`JMSMessageID` is a global UUID."** The spec only requires the `ID:` prefix and uniqueness at minimum within an installation; the rest of the format is provider-specific.
4. **"Retrying an event always keeps the same JMSMessageID."** If the application performs a new send, the provider can assign a new ID; a separate event ID is required.
5. **"`JMSTimestamp` is when the listener received the message."** It is when the message was handed to the provider to send; async sends, transactions, TTL, delays, and backlogs separate those times.
6. **"Timestamp 0 proves the message is from 1970."** It can indicate the provider honored the disable-timestamp hint.
7. **"`JMSExpiration` starts from when the consumer receives."** It is computed from send time and TTL; in transacted sends it does not wait for transaction commit.
8. **"DeliveryTime is the actual delivery time."** It is the **earliest** time the provider is allowed to deliver the message.
9. **"`JMSRedelivered=false` proves business logic never ran before."** Duplicate producer sends and side effects outside JMS can still exist.
10. **"`JMSXDeliveryCount` is always exact after every crash."** It is mandatory metadata on receive, yet not guaranteed to survive every failure accurately.
11. **"Every JMSX property is always present."** Many JMSX fields are optional; vendor-specific metadata is not portable.
12. **"`JmsTemplate` MessageCreator knows JMSMessageID."** The creator callback executes before sending, not when the provider completes the send.
13. **"Disabling timestamp disables TTL."** No; they are two separate mechanisms.
14. **"Having a JMSMessageID means the consumer ACKed."** The ID only describes send metadata; ACK, transactions, and business outcomes must be verified separately.

## 14. Self-Check Questions

- Who assigns `JMSMessageID`, what prefix must it start with, and what is the guaranteed scope of uniqueness?
- Why does `eventId` stay constant across retries while `JMSMessageID` can change? Which field must you deduplicate on?
- What moment does `JMSTimestamp` measure? Is it enqueue, commit, receive, or business event time?
- When is it safe to read provider-on-send metadata with synchronous vs. asynchronous sends?
- Which headers does the provider compute for `JMSExpiration`, `JMSDeliveryTime`, `JMSPriority`, and `JMSDestination`? How does the client configure them?
- Are `JMSRedelivered` and `JMSXDeliveryCount` set on send or on receive? Why do those two fields not guarantee exactly-once processing?
- What happens if the provider honors `setDisableMessageID(true)` or `setDisableMessageTimestamp(true)`?
- What additional logs and verification are needed to conclude a business event was processed safely?

**Learning outcome:** You can trace a message from creation through post-send, inside the broker, and at the consumer, accurately distinguish provider-generated metadata from application-managed metadata, and use them to diagnose systems without over-assuming reliability guarantees.

## Authoritative References

1. [Jakarta Messaging 3.1 Specification – `3.4 Message header fields`](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html): authoritative source on header ownership, `JMSMessageID`, `JMSTimestamp`, expiration, delivery time, and compatibility limits.
2. [Jakarta Messaging 3.1 – Message API](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/message): getter/setter signatures, headers/properties, and exceptions.
3. [Jakarta Messaging 3.1 – MessageProducer API](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/messageproducer): QoS, `setDisableMessageID`, `setDisableMessageTimestamp`, synchronous/async send.
4. [Spring Framework – Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html): `JmsTemplate`, `MessageCreator`, and how Spring uses the JMS API.
5. [Spring Framework – Annotation-driven JMS Listener Endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html): receiving `jakarta.jms.Message` via `@JmsListener` and managing listener containers.