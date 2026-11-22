# Logging Message Producers in Java: Accurately Observing Every Stage of Sending a Message

## 1. What Is a Message Producer and Why Does It Need Dedicated Logging?

In a message-driven system, a **message producer** is the component that creates and sends events or commands to a broker, topic, exchange, or queue for one or more consumers to process later. In Java, a producer may use Apache Kafka, RabbitMQ, Jakarta Messaging (JMS), another client library, or an internal interface wrapping those systems.

Producer-side logging helps answer: **what message is the application attempting to send (at a safe metadata level), where is it being sent, to what extent is the send result confirmed, what errors occurred, whether a retry happened, and how does it link back to the originating business request?** It is not merely for printing payloads to "see what the producer is doing."

Three events that are easily conflated must be distinguished:

- **The producer called `send()`:** the code has initiated the operation; this is not yet sufficient evidence that the broker received it.
- **The client/broker reported a successful send:** an outcome according to the protocol and ACK configuration; it does not necessarily mean a consumer has processed it.
- **The consumer completed business processing:** this happens on the receiving side, possibly much later, and may fail or be retried; the producer has no automatic way of knowing this without a business feedback mechanism.

The most important principle: **do not log "published successfully" immediately after calling an asynchronous send API before receiving the corresponding result from a callback/Future/confirm**. The call may have only placed the record into the client's in-memory buffer.

Producer logging needs to combine **structured events, callbacks, correlation IDs, metrics, retry policies, and data protection**. For messages with audit or transactional significance, an additional durable persistence mechanism independent of diagnostic logs is required.

## 2. Milestones in a Publish Lifecycle

A producer typically goes through the following stages:

~~~text
Business operation / HTTP request / scheduled task
        │
        ▼
Generate eventId, correlationId; validate data and schema
        │
        ▼
[1] SEND_ATTEMPT (send requested, no result yet)
        │
        ▼
Serialize / select topic, partition, routing key
        │
        ├─ immediate error at call site → [2a] CLIENT_REJECTED
        ▼
Enqueue into client buffer / send over network
        │
        ├─ timeout, broker reject, serialization error...
        ▼
Broker processes according to ACK/confirm configuration
        │
        ├─ callback/error → [2b] SEND_FAILED / OUTCOME_UNKNOWN
        └─ callback/confirm → [3] BROKER_ACKED
                                    │
                                    ▼
                           Consumer receives message
                                    │
                                    ▼
                           Consumer processes and commits/ACKs separately
~~~

From `SEND_ATTEMPT` to `BROKER_ACKED` can take a few milliseconds or longer depending on load and the broker. The callback may run **on a different thread**. If MDC is only attached on the sending thread without context propagation, callback logs may lack `traceId` or mix up contexts.

Do not equate `BROKER_ACKED` with "delivered to all subscribers," "consumer has run," "consumer database has committed," or "data can never be lost." The meaning of an ACK depends on the broker, durability, configuration, and failure timing.

Some clients return a `Future` or `CompletionStage`; that is a handle to the operation, **not a success result** at the moment the object is returned.

## 3. Events to Log and Reference Levels

| Event code | When emitted | Suggested level | Exact meaning |
| --- | --- | --- | --- |
| `PRODUCE_ATTEMPT` | Before each time the application actively calls send | DEBUG/FINE or metric | An application attempt has started |
| `PRODUCE_ENQUEUED` | Client confirms acceptance into local buffer (if a reliable signal exists) | DEBUG/FINE | No broker ACK yet |
| `PRODUCE_ACKED` | Callback/confirm succeeds per broker contract | INFO or DEBUG as needed | Broker/client confirmed the send outcome |
| `PRODUCE_REJECTED` | Validation/serialization or client API rejects immediately | WARN | The call was not accepted under the contract |
| `PRODUCE_FAILED` | Future/callback reports an error | WARN/ERROR | Send reported a failure; inspect type and certainty |
| `PRODUCE_OUTCOME_UNKNOWN` | Timeout/network disconnect when it is uncertain whether the broker received it | WARN | Cannot conclude the message was lost |
| `PRODUCE_RETRY_SCHEDULED` | Application decides to retry | DEBUG/INFO or metric | A new attempt is coming, with risk of duplicates |
| `PRODUCE_EXHAUSTED` | Retry budget exhausted and failure handled per policy | ERROR/WARN | No more normal application retries |
| `OUTBOX_COMMITTED` | Event committed in a durable outbox | INFO/audit per policy | Local durable intent saved, not yet a broker ACK |
| `CONSUMER_PROCESSED` | Emitted by the **consumer** after business outcome | Separate channel | The producer must not emit this event itself |

These levels are **recommendations**, not a fixed standard for every organization. At very high throughput, logging `PRODUCE_ACKED` for every single message can be too expensive; prefer aggregated metrics, sampling, or channels by event class. However, if an event is mandatory for auditing, policy must not allow evidence to be lost simply because the log level was lowered.

In particular, **do not log the same success both before the call and inside the callback**. If there are "start" and "ack" logs, they must have different event names and share the same `eventId` so they are not counted as two successful publishes.

## 4. Designing a Traceable Producer Log Schema

A useful producer event should have **fixed fields**, clear data types, clear semantics, and clear protection policies:

| Field | Purpose | Notes |
| --- | --- | --- |
| `eventCode` | Status classification, e.g., `PRODUCE_ACKED` | Stable code, not dependent on free-form messages |
| `messageId` or `eventId` | Application-assigned message identifier | Keep stable across retries; do not derive from secret payloads |
| `messageType` / `schemaVersion` | Event type and content version | Use an allowlist; aids schema error investigation |
| `correlationId` / `requestId` | Links to HTTP request and business operation | Not an identity proof on its own |
| `traceId` / `spanId` | Distributed tracing linkage | Must propagate properly via headers |
| `destination` / `topic` / `exchange` | Target destination | Verify values contain no credentials |
| `partition` / `offset` or `publishSeqNo` | Broker-returned metadata | Log only if available and meaningful for the broker |
| `attempt` | Send attempt managed by the **application** | Do not confuse with internal client retries |
| `outcome` | `ACKED`, `FAILED`, `UNKNOWN` per contract | Do not emit `CONSUMED` from the producer |
| `reasonCode` / `exceptionClass` | Error classification | Do not include raw exception messages containing secrets |
| `elapsedMs` | Latency from a defined start point to outcome | Use a monotonic clock for durations |
| `producerInstance` | Identifies instance/region during investigation | Do not log host tokens or config secrets |
| `timestamp` | Time the event was recorded | UTC with synchronized clocks |

**Illustrative** JSON example (not the default output of JUL or Kafka):

~~~json
{
  "eventCode": "PRODUCE_ACKED",
  "messageId": "evt-001",
  "messageType": "ORDER_CREATED",
  "schemaVersion": 2,
  "correlationId": "req-8fd",
  "destination": "orders.events",
  "partition": 0,
  "offset": 501,
  "attempt": 1,
  "outcome": "ACKED",
  "elapsedMs": 18
}
~~~

Do not assume every broker has `partition` and `offset`. Kafka provides these fields in `RecordMetadata`; RabbitMQ uses per-channel sequence/confirm numbers; JMS has provider-specific message IDs and metadata.

**Distinguishing IDs:**

- `messageId` is an ID assigned by the application before publishing to link attempts together.
- `correlationId` links a message to a request or workflow; one request can produce multiple messages.
- `traceId` links diagnostic spans; it may be sampled, whereas business IDs must still be present.
- `Kafka key` is a partitioning/data-semantics key, not inherently an immutable ID.
- `Kafka offset` is a record's position within a topic-partition, not a globally unique ID across the system.

## 5. Two Error Paths: Immediate Throw and Callback Failure

A messaging client can report errors at **two different points in time**.

**Synchronous errors (before/during `send` on the caller thread):** topic validation, missing serializer, serialization failure, configuration errors, closed producer state, missing metadata, or buffer allocation failure. Depending on the API, `send()` may throw an exception instead of returning a Future.

**Asynchronous errors:** the callback/Future/CompletionListener receives an error after the network or broker has been attempted. This is where late-occurring ACK, broker, timeout, or authorization errors are observed.

**Conceptual** Java pattern:

~~~java
try {
    // Some clients accept a callback to return the asynchronous result.
    // Log the ACK according to the backend contract only when the callback succeeds.
    client.send(message, (result, error) -> {
        if (error != null) {
            logSendFailed(messageId, classify(error));
        } else {
            logBrokerAcked(messageId, result);
        }
    });
} catch (RuntimeException error) {
    logClientRejected(messageId, classify(error));
}
~~~

This is **not** a generic API that compiles against every client; `client`, `message`, and the handler methods are hypothetical to illustrate the two places errors appear. For each broker, use its exact API as shown in the following sections.

Do not automatically log in both `catch` and the callback for the same failure if a client might invoke the callback and throw under an unusual contract. **Read the client's Javadoc** to know whether an exception at the call site prevents the callback from being invoked.

For timeouts after a request has left the client, the state may be **UNKNOWN**: the broker may have written it, but the response was lost. Retries must rely on idempotency/deduplication rather than assuming "the message definitely never reached the broker."

## 6. Standalone Java 17 Example: Logging Asynchronous Send Outcomes

The program below **simulates** a message broker using `CompletableFuture` and a sender thread. It runs on JDK 17, **requires no Kafka/RabbitMQ/JMS**, and connects to no real broker. The program intentionally produces one successful event and one simulated timeout on the first attempt, followed by a successful retry.

Verification goals:

1. Log `send attempt` at `FINE` before sending, toggleable.
2. Log `publish acknowledged` at `INFO` after the Future completes successfully.
3. Log `publish failed` at `WARNING` when the Future completes exceptionally.
4. Keep the same `messageId` on retry while incrementing `attempt`.
5. Never log `payload` content, raw exception messages, or PII.
6. The callback runs on an executor, yet logs still carry IDs via captured variables without relying on thread-local MDC.
7. Wait for completion with `join()` in the **demo** for deterministic output ordering; production code should use a bounded async pipeline rather than waiting per message.

Create the file **ProducerLoggingDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeoutException;
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class ProducerLoggingDemo {
    private static final Logger LOG = Logger.getLogger("demo.producer");

    record Outbound(String messageId, String topic, String payload) {}
    record Receipt(int partition, long offset) {}

    static final class FakeBroker implements AutoCloseable {
        private final ExecutorService executor =
                Executors.newSingleThreadExecutor();

        CompletableFuture<Receipt> send(Outbound message, int attempt) {
            return CompletableFuture.supplyAsync(() -> {
                if ("evt-002".equals(message.messageId()) && attempt == 1) {
                    throw new CompletionException(
                            new TimeoutException("simulated timeout"));
                }
                return new Receipt(0, "evt-001".equals(
                        message.messageId()) ? 501L : 502L);
            }, executor);
        }

        @Override
        public void close() {
            executor.shutdown();
        }
    }

    private static String reason(Throwable error) {
        Throwable root = error;
        for (int depth = 0; depth < 8 && root.getCause() != null; depth++) {
            root = root.getCause();
        }
        return root instanceof TimeoutException
                ? "BROKER_TIMEOUT" : "SEND_ERROR";
    }

    private static boolean sendAndObserve(
            FakeBroker broker, Outbound message, int attempt) {
        LOG.log(Level.FINE,
                "send attempt messageId={0} topic={1} attempt={2}",
                new Object[]{message.messageId(), message.topic(), attempt});

        // Callback reflects completion, not just local send invocation.
        return broker.send(message, attempt).handle((receipt, error) -> {
            if (error != null) {
                LOG.log(Level.WARNING,
                        "publish failed messageId={0} topic={1} reasonCode={2} attempt={3}",
                        new Object[]{message.messageId(), message.topic(),
                                reason(error), attempt});
                return false;
            }
            LOG.log(Level.INFO,
                    "publish acknowledged messageId={0} topic={1} partition={2} offset={3} attempt={4}",
                    new Object[]{message.messageId(), message.topic(),
                            receipt.partition(), receipt.offset(), attempt});
            return true;
        }).join(); // Demo waits for deterministic output.
    }

    public static void main(String[] args) {
        if (args.length > 1 ||
                (args.length == 1 && !"--debug".equals(args[0]))) {
            System.err.println("Usage: java ProducerLoggingDemo [--debug]");
            System.exit(2);
            return;
        }
        ConsoleHandler handler = new ConsoleHandler();
        handler.setLevel(Level.ALL);
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + " "
                        + formatMessage(record) + System.lineSeparator();
            }
        });
        LOG.setUseParentHandlers(false);
        LOG.setLevel(args.length == 1 ? Level.FINE : Level.INFO);
        LOG.addHandler(handler);
        try (FakeBroker broker = new FakeBroker()) {
            sendAndObserve(broker,
                    new Outbound("evt-001", "orders.events",
                            "PRIVATE_SAMPLE_DO_NOT_LOG"), 1);
            Outbound second = new Outbound(
                    "evt-002", "orders.events", "SENSITIVE_BODY");
            if (!sendAndObserve(broker, second, 1)) {
                sendAndObserve(broker, second, 2);
            }
        } finally {
            LOG.removeHandler(handler);
            handler.flush();
            handler.close();
        }
    }
}
~~~

Using JDK 17 or later:

~~~bash
javac --release 17 ProducerLoggingDemo.java
java ProducerLoggingDemo
~~~

**Exact standard error (stderr) in default mode:**

~~~text
INFO publish acknowledged messageId=evt-001 topic=orders.events partition=0 offset=501 attempt=1
WARNING publish failed messageId=evt-002 topic=orders.events reasonCode=BROKER_TIMEOUT attempt=1
INFO publish acknowledged messageId=evt-002 topic=orders.events partition=0 offset=502 attempt=2
~~~

**Standard output (stdout):** empty. Exit code: `0`. JUL's `ConsoleHandler` writes to stderr.

Run with debug enabled:

~~~bash
java ProducerLoggingDemo --debug
~~~

**Standard error (stderr) when `FINE` is enabled:**

~~~text
FINE send attempt messageId=evt-001 topic=orders.events attempt=1
INFO publish acknowledged messageId=evt-001 topic=orders.events partition=0 offset=501 attempt=1
FINE send attempt messageId=evt-002 topic=orders.events attempt=1
WARNING publish failed messageId=evt-002 topic=orders.events reasonCode=BROKER_TIMEOUT attempt=1
FINE send attempt messageId=evt-002 topic=orders.events attempt=2
INFO publish acknowledged messageId=evt-002 topic=orders.events partition=0 offset=502 attempt=2
~~~

Standard output remains empty; exit code `0`. The offset numbers **501/502 are simulated values from FakeBroker**, not offsets from a real Kafka cluster.

**Limitation note:** `FakeBroker` always succeeds on the second attempt for `evt-002`. With a real broker, a timeout does not guarantee the message was not written; retrying may create a duplicate. This demo does not test durability, real broker ACKs, transactions, distributed tracing, or an outbox. `reason(...)` returns a **safe error code** instead of logging raw exception messages that could contain uncontrolled data.

## 7. Analyzing the Example: Why Not Log "Success" Right After `send()`?

In the demo code, `sendAndObserve` calls `broker.send(...)` and receives a `CompletableFuture<Receipt>`. That Future may **not be completed yet**. `publish acknowledged` is only logged when the `handle((receipt, error) -> ...)` handler is invoked with `error == null`.

There are two separate lifecycles:

~~~text
Sending thread               Callback / simulated broker thread
-----------                  ----------------------------------
log FINE attempt
send(...) ------------------> async work
receive Future                (sending/attempting send...)
                              ├── success: log INFO acknowledged
                              └── error: log WARNING failed
join() waits for result <---- handler result
~~~

If an application simply writes:

~~~java
var future = producer.send(record);
log.info("published successfully");
~~~

then this is **semantically wrong observability code** when `send` is asynchronous; the log line can execute before the broker responds, or even when the request later fails. In the snippet above, `record`, `producer`, and `log` are application variables with appropriate APIs, not a standalone Java program.

The fix is to **log inside the callback or when handling Future completion**; or await the Future when synchronous behavior is genuinely needed and the latency cost is acceptable. Do not turn every publish into `future.get()/join()` on a request thread just to make logging easier.

## 8. Apache Kafka: Logging in the `KafkaProducer.send` Callback

The Kafka Java Producer supports:

- `KafkaProducer.send(ProducerRecord<K,V>, Callback)`: sends asynchronously and invokes the callback when the broker ACKs or an error occurs.
- `RecordMetadata` in a successful callback: information such as `topic()`, `partition()`, `offset()`, and timestamp depending on the scenario.
- `send(...)` also returns `Future<RecordMetadata>`; obtaining the Future **does not** prove completion.
- Some errors may be thrown on the thread calling `send` before the callback, such as serialization, configuration, buffer, or metadata errors. Exact conditions and exception types depend on the version.
- Kafka callbacks typically run on the producer's I/O thread. **Do not block the callback** with network calls, DB queries, or formatting huge log payloads.

Illustrative snippet in an application with `producer` of type `KafkaProducer<String,byte[]>`, `record` of type `ProducerRecord<String,byte[]>`, and a safely generated `messageId`:

~~~java
// Kafka API illustration: requires a compatible kafka-clients version.
try {
    producer.send(record, (metadata, error) -> {
        if (error != null) {
            LOG.warn("producer outcome=FAILED messageId={} topic={} errorClass={}",
                    messageId, record.topic(),
                    error.getClass().getSimpleName());
            return;
        }
        LOG.info("producer outcome=ACKED messageId={} topic={} partition={} offset={}",
                messageId, metadata.topic(), metadata.partition(),
                metadata.offset());
    });
} catch (RuntimeException error) {
    LOG.warn("producer outcome=CLIENT_REJECTED messageId={} topic={} errorClass={}",
            messageId, record.topic(), error.getClass().getSimpleName());
}
~~~

This is **not** a standalone Java example: `LOG` is a configured SLF4J logger and the Kafka variables are already initialized. Follow the library and exception policy for your project's `kafka-clients` version.

**Key points about Kafka ACKs:**

1. With `acks=0`, the producer does not wait for broker acknowledgement in the way `acks=all` does; do not label a successful callback under this setting as "broker confirmed durable write." The provided offset may be `-1`.
2. With `acks=1` or `acks=all`, the guarantee depends on the leader, replicas in the ISR, `min.insync.replicas`, and related settings.
3. A Kafka callback ACK for a record **does not** mean a consumer has polled the record or completed business processing.
4. `partition` and `offset` are meaningful within a topic/partition; consumer lag is a separate measurement.
5. If a timeout error occurs after the request has been sent, the outcome may be indeterminate. Do not log "message LOST" solely from a `TimeoutException`.

Based on the `KafkaProducer.send` documentation, the send callback is the right milestone to log the send outcome, while synchronous exceptions must also be checked at the call site.

## 9. Kafka Retries, Idempotence, and Transactions: How to Label Logs

The Kafka producer can perform **internal retries**; therefore, you must distinguish:

- `attempt`: the **application** calling `send` again after an error outcome.
- `retry`: the Kafka client retrying internally within a single send call.
- `redelivery`: at the consumer due to consumer failure or replay.
- `duplicate business event`: two transactions or outbox entries publishing the same business intent.

Do not log `attempt=3` by guessing how many times Kafka resent over the network if the application does not have exact data. A callback does not necessarily run on every internal network retry performed by the client.

**Idempotent producer:** enable/maintain Kafka configuration appropriate for idempotence to reduce the risk of duplicate records from internal retries within supported bounds. This **does not** prevent the application itself from emitting two business events with two message IDs or a consumer from processing twice.

**Transactions:** a Kafka transactional producer uses `beginTransaction()`, `commitTransaction()`, and `abortTransaction()` per the appropriate API. A record send callback may complete before the transaction is committed; when "visible/committed" status is required, you must also log an outcome at the **transaction commit milestone** rather than calling each record ACK "transaction complete."

**Timeouts:** when a definitive result is not received, a status code like `OUTCOME_UNKNOWN` is usually clearer than `LOST`. When retrying at the application layer, use the same business event ID, exponential backoff with jitter, a retry budget, and an appropriate idempotency mechanism.

Properties such as `acks`, `enable.idempotence`, `delivery.timeout.ms`, `request.timeout.ms`, and `max.block.ms` must be chosen based on version, delivery requirements, and workload. Do not change them arbitrarily just to "reduce WARN logs."

## 10. RabbitMQ: Publisher Confirms, Routing, and Correlation

With the RabbitMQ Java AMQP 0-9-1 client, a producer typically calls `channel.basicPublish(...)`. That method returning does not mean the broker has sent a publisher confirm. When you need to know the broker handled the publish at the corresponding protocol level, use **publisher confirms**.

The RabbitMQ documentation describes three options:

1. Publish one message and call `waitForConfirmsOrDie(timeout)` — simple to understand, but reduces throughput.
2. Publish a batch and wait for confirms — faster, but harder to attribute a failure to a single message.
3. Call `channel.confirmSelect()` and register `addConfirmListener(...)` — async callbacks receiving ACK/NACK, requiring a correlation map.

Illustrative snippet for enabling confirms, assuming `channel` is a connected RabbitMQ `com.rabbitmq.client.Channel`:

~~~java
channel.confirmSelect();
channel.addConfirmListener(
        (deliveryTag, multiple) -> {
            // ACK: match deliveryTag against the messageId stored before publishing.
        },
        (deliveryTag, multiple) -> {
            // NACK: log a safe error code and offload the retry to a separate worker.
        });
~~~

This is a callback configuration snippet inside an application using the RabbitMQ client, not a standalone class; full correlation logic requires a map with proper lifecycle management and synchronization.

**Characteristics to log accurately:**

- `deliveryTag` / publisher sequence number is scoped to a **channel**; it does not replace the business `messageId`.
- The `multiple=true` parameter can confirm a range of sequence numbers, not just a single message. The correlation map must handle that range properly.
- A publisher confirm ACK means the broker processed the message under confirm rules; it **does not** mean a consumer received and ACKed it.
- **Publisher confirms are not consumer acknowledgments**. A consumer ACK is a separate event on the receiving side.
- When using `mandatory`, you must handle **`basic.return`** for unroutable messages according to policy. A publisher confirm ACK **is not enough** to conclude the message reached an intended queue if routing failed. Returned messages must also be observed.
- RabbitMQ confirm callbacks may run on the client's I/O thread; avoid calling publish again or performing heavy I/O or blocking operations directly inside the callback. Offload retries to an appropriate executor or queue.
- Sequences and callbacks may arrive out of the order the application expects; the event ID should exist independently in headers/metadata per policy.

A WARN log for "publish NACK" should include `messageId`, exchange, safe routing key, delivery tag, attempt, and reason code; **do not** print the raw body to locate the message.

## 11. Jakarta Messaging / JMS: Synchronous Send and `CompletionListener`

Jakarta Messaging defines `MessageProducer` and `JMSProducer`, which can send synchronously or asynchronously depending on the API and supported environment.

For asynchronous sends on `MessageProducer`, `CompletionListener.onCompletion(Message)` signals that the send operation completed **with the same reliability guarantees as a corresponding synchronous send**. `onException(Message, Exception)` reports an error that occurred during the async send. Do not assume the callback always proves data has been durably fsynced, as that depends on the provider, delivery mode, and transactions.

**API illustration** (not a standalone class) with existing producer, message, and `messageId`:

~~~java
producer.send(message, new jakarta.jms.CompletionListener() {
    @Override
    public void onCompletion(jakarta.jms.Message completed) {
        LOG.info("JMS send completed messageId={}", messageId);
    }

    @Override
    public void onException(jakarta.jms.Message failed, Exception error) {
        LOG.warn("JMS send failed messageId={} errorClass={}",
                messageId, error.getClass().getSimpleName());
    }
});
~~~

In this snippet, `LOG` is an SLF4J logger. **Do not log the entire `Message`** because headers and body may contain confidential data.

Notes per Jakarta Messaging 3.1:

- Errors can be thrown immediately on the thread calling `send`; the callback does not replace synchronous error handling.
- The provider decides which work is done on the calling thread versus a background thread.
- Sessions and Messages have concurrency restrictions; do not arbitrarily read or modify a `Message` asynchronously before the callback fires.
- These asynchronous send methods are **restricted/disallowed by the specification in Jakarta EE web/EJB containers**; check the API and environment rather than copying examples into any application server.
- With a transacted session, send completion does not automatically mean the transaction is committed; commit/rollback milestones must be observed separately.
- JMS message ID, correlation ID, and TTL have their own semantics; do not assume they are equivalent to a Kafka offset.

## 12. Correlation IDs, Trace Context, and Header Propagation

If an HTTP request produces a message that is later processed by a consumer in another process, logs on the producer and consumer must be linkable **without printing the payload**.

Example flow:

~~~text
HTTP request:
  requestId=req-8fd
  traceId=tr-281

Producer:
  messageId=evt-001
  topic=orders.events
  correlationId=req-8fd
  traceparent=<trace-context-value>
  outcome=ACKED

Consumer (in another application):
  messageId=evt-001
  correlationId=req-8fd
  outcome=PROCESSED or RETRY
~~~

The above is a diagram, not runtime output. `traceparent` is the distributed context header per W3C Trace Context / OpenTelemetry when using the corresponding instrumentation; do not fabricate arbitrary `traceparent` text and treat it as valid.

**Practical rules:**

1. Generate `messageId` **before the first send** and keep it stable across application retries for the same logical event.
2. Attach `correlationId` and tracing headers to the envelope/headers if the broker and policy allow; do not parse payload text to find IDs.
3. In async callbacks, capture immutable IDs in a closure or an explicit context snapshot. The caller thread's `MDC` is not guaranteed to propagate automatically to the callback thread.
4. On the consumer, extract headers in a standard format and create a new span/context; clean up ThreadLocal/MDC after processing to avoid cross-message contamination.
5. Avoid confusing business actor IDs with correlation IDs: actor IDs may link to personal data and require appropriate retention and access controls.

**A message may be retried or duplicated** while still carrying the same logical ID. Each attempt's log record should add `attempt` or `deliveryAttempt` depending on context to distinguish actual executions.

## 13. Producer Logging and Privacy: Never Log Raw Payloads

Message bodies may contain names, addresses, emails, tokens, payment details, files, or privacy-sensitive data. Logging patterns like the following are dangerous:

~~~java
// Avoid: the entire payload/domain object may be printed.
LOG.debug("publishing message={}", message);
LOG.info("sending payload={}", new String(bytes, java.nio.charset.StandardCharsets.UTF_8));
LOG.error("publish failed body={} exception={}", body, error.getMessage());
~~~

These lines illustrate an SLF4J-style logger API; they are not standalone JDK code. A DTO/record's `toString()` and `Exception.getMessage()` can contain unauthorized data.

Log only allowlisted fields:

~~~text
eventCode=PRODUCE_ACKED
messageId=evt-001
messageType=ORDER_CREATED
topic=orders.events
partition=0
offset=501
attempt=1
payloadBytes=482
~~~

`payloadBytes` is the size, not the content; even so, attributes such as message type, topic, size, or IDs can still be sensitive in some systems and should be evaluated.

When a specific payload must be investigated, use a **separate access-controlled data/trace store** following an approved process, rather than enabling DEBUG to dump every message's content in production.

For Kafka keys, RabbitMQ routing keys, JMS properties, and headers: check them for sensitive data as well. Avoid printing `Authorization`, cookies, secrets, or broker connection credentials.

## 14. Logging Exceptions Properly Without Leaking Data

A callback receives a `Throwable` or `Exception`. Two goals must be balanced:

- **Fast incident classification:** serialization error, auth failure, network timeout, broker rejection, missing topic/queue, record too large, or overload.
- **No secret leakage in messages/stack traces:** exceptions from HTTP, JDBC, or serializers can contain URLs, input data, headers, or bodies.

Operational channel logs should use `errorClass` and an allowlisted `reasonCode`; when policy permits, stack traces can go to a restricted-access channel after data sanitization. Do not log `error.toString()` unconditionally.

Classification examples:

| Error type | Suggested code | Action |
| --- | --- | --- |
| Unable to serialize payload | `SERIALIZATION_FAILED` | Check schema/codec; usually do not retry with the same raw data |
| Missing topic/exchange permission | `AUTHORIZATION_DENIED` | Alert on config/permissions; do not retry blindly |
| Invalid metadata/destination | `INVALID_DESTINATION` | Fix destination name and configuration |
| Transient connection loss | `NETWORK_UNAVAILABLE` | May retry/backoff within limits |
| Timeout uncertain whether broker wrote | `OUTCOME_UNKNOWN` | Requires idempotency and reconciliation |
| Broker NACK | `BROKER_NACK` | Analyze confirm/routing and retry policy |
| Client buffer full | `PRODUCER_BACKPRESSURE` | Slow down, bound pending work, tune pipeline |
| Producer closed | `CLIENT_CLOSED` | Fix lifecycle and shutdown ordering |

Error codes are an application-chosen taxonomy; **there is no single unified enum** across Kafka, RabbitMQ, and JMS. When upgrading a client version, verify exception mappings.

**Do not confuse logging a WARN with ensuring the application handled the error.** Logging only records the symptom. Retries, DLQs, outboxes, readiness signals, and business return decisions must be explicitly implemented.

## 15. Retries, Duplicates, and the `attempt` Field

Retries are a vital part of producers, and also an easy source of log misinterpretation.

One logical message `evt-002` might have multiple attempts:

~~~text
evt-002 attempt=1 SEND_ATTEMPT
evt-002 attempt=1 OUTCOME_UNKNOWN
evt-002 attempt=2 SEND_ATTEMPT
evt-002 attempt=2 BROKER_ACKED
~~~

If the first attempt timed out after the broker already received it, the second attempt can create a **duplicate**. A log saying "attempt 1 failed" does not prove the first copy does not exist. Therefore:

- Use the same logical `eventId` when retrying, adding an attempt number for application-level retries.
- Design idempotent consumers or apply a deduplication key appropriate for the system.
- Use backoff with jitter, bound the retry count/deadline, and distinguish transient errors from non-retryable ones.
- Do not automatically retry indefinitely inside a client callback or directly on an I/O thread.
- Use metrics such as `publish_attempt_total`, `publish_acked_total`, `publish_error_total`, and `retry_scheduled_total` to monitor volume; metric names here are suggestions only.
- Do not count each retry as **a new business event**. Business ID and transport attempt must remain separate concepts.

**Idempotency does not automatically provide end-to-end exactly-once processing.** Consumers can still process duplicates due to redelivery, the application emitting two logical messages, or side-effect writes lacking transactions/deduplication.

## 16. Messaging and Business Transactions: Avoiding Dual-Write

A major problem that debug logs cannot solve:

~~~text
Business DB COMMIT succeeds
       │
       ▼
producer.send(...) network error or JVM crash
       │
       ▼
DB changed, but uncertain whether the message reached the broker
~~~

Conversely, if the message is sent first and the DB transaction rolls back, a consumer may process an event describing state that was never committed.

For systems that must preserve **event-publishing intent after a business state change**, a **transactional outbox** can be used:

~~~text
BEGIN DB transaction
  UPDATE order
  INSERT outbox(eventId, destination, safeEventPayload, state)
COMMIT
    │
    ▼
Outbox worker reads committed record
    │
    ▼
Send message to broker, observe callback/ACK
    │
    ├── ACK: mark DELIVERED per contract
    └── error/UNKNOWN: retry with idempotency
~~~

Producer logs may include `OUTBOX_COMMITTED`, `PRODUCE_ATTEMPT`, `BROKER_ACKED`, and `OUTBOX_DELIVERED`; these are distinct milestones and must be clearly defined. **Do not** call `PRODUCE_ACKED` a DB transaction success.

What an outbox **does not automatically guarantee**:

- That the broker receives the message the instant the database commits.
- Zero duplicates if the worker crashes after publishing but before marking delivered.
- Exactly-once consumer processing when other side effects need transactions.
- That the outbox and broker are in the same physical transaction.

An outbox typically leads to **at-least-once delivery** at the application level; it requires stable IDs, deduplication, and backlog monitoring. Payloads stored in the outbox also require encryption, access control, and retention policies.

## 17. "Success" Semantics Must Be Stated Precisely

Do not use a single word `SUCCESS` for every situation:

| Observed milestone | Accurate phrasing | What is not yet proven |
| --- | --- | --- |
| `send` call started | "Publishing attempted" | Client acceptance |
| Future returned or local enqueue | "Submission buffered/initiated" | Broker ACK |
| Kafka callback succeeds with appropriate `acks` | "Broker acknowledged according to producer config" | Consumer processing, side effects completed |
| RabbitMQ publisher confirm ACK | "Broker confirmed publish" | Message reached intended queue if routing/return wasn't checked; consumer ACK |
| JMS CompletionListener succeeds | "Async send completed under provider's contract" | Session transaction committed if that milestone hasn't occurred |
| Outbox commit | "Publish intent stored durably in business DB" | Reached the broker |
| Consumer ACK/commit | "Consumer delivery/process state reported" | Entire downstream workflow completed |
| Business completion event | "Business operation completed per application contract" | External systems that haven't responded if no evidence exists |

**Good logging cannot fix a poorly designed delivery protocol.** It only expresses state accurately so operators are not misled.

If a producer needs to know that a consumer has processed a message, there must be a proper **reply message, status store, business callback, or correlation flow**; the producer cannot infer it from a Kafka offset or RabbitMQ publisher confirm.

## 18. Correlation Across Logging, Metrics, and Tracing

These three tools serve different levels of observability:

**Logs:** describe the event and reason for a specific message (event ID, destination, outcome, errorCode), especially on errors.

**Metrics:** aggregate events/sec, failure counts, retry rates, latency percentiles, pending/inflight counts, queue fullness, and destination health. This is the right approach when throughput exceeds what should be logged per ACK.

**Distributed traces:** connect HTTP request → business service → producer → broker → consumer, with standardized span boundaries and trace context. Traces may be sampled; therefore, **do not** treat a missing span as proof that an event did not occur.

Example producer dashboard:

- `messages_attempted_total`, `messages_acked_total`, `messages_failed_total`.
- `messages_outcome_unknown_total` and `retries_scheduled_total`.
- `publish_ack_latency_seconds` histogram with p95/p99.
- `producer_inflight_messages`, buffered records, and backpressure.
- `outbox_oldest_pending_age_seconds` if an outbox is used.
- `broker_connectivity_status` and auth failure rate.

These metric names are **naming suggestions only**; Kafka and RabbitMQ clients have their own metric systems. When exporting to Prometheus, avoid putting `messageId`, email, or `traceId` into metric labels due to unbounded cardinality and data exposure risks. Use low-cardinality labels such as normalized destination and errorCode.

## 19. Performance: Logging Every Message Is Not Always Right

In a system sending tens of thousands of messages per second, one INFO line per attempt and one per ACK will generate massive log volume, increasing I/O, GC pressure, and storage costs.

**Common strategy:**

1. Log detailed `PRODUCE_ATTEMPT` at DEBUG/FINE during investigations, not enabled indefinitely.
2. Record structured warnings/errors for failures, timeouts, and unknown outcomes, while rate-limiting if the same incident bursts.
3. Use **metrics** for successful ACK volume; critical audit events use a dedicated pipeline and are not arbitrarily sampled.
4. If sampling success logs is needed, document the sampling rate and do not use sampled logs to reconcile absolute message counts.
5. Use parameterized logging instead of string concatenation or payload serialization before checking the log level.
6. Do not block Kafka/RabbitMQ/JMS callbacks with disk syncs, network API calls, or DB queries.
7. Bound retry/pending queues and monitor backpressure; producer logs themselves may use an async appender and risk being dropped on a JVM crash.

The demo code uses `LOG.log(Level.FINE, "send attempt ...", args)` to demonstrate `--debug`, but real applications must benchmark total overhead and decide which data has long-term value.

## 20. Shutdown: Waiting for Sends to Actually Finish and Recording Outcomes

An application stopping for a deployment should not simply think "all `send()` calls were made, exit the JVM now." Especially if the producer has a buffer, incomplete sends can be lost.

A reference **graceful shutdown** sequence:

~~~text
Stop accepting new work/messages
     │
     ▼
Wait for active producer tasks to finish within a deadline
     │
     ▼
Call version-appropriate broker client close/flush APIs
     │
     ▼
Await callbacks/Futures/confirms within contract and timeout
     │
     ▼
Update outbox/pending state based on confirmed outcomes
     │
     ▼
Stop async logging appenders and release resources
     │
     ▼
Exit JVM
~~~

**Do not conflate:**

- Kafka `producer.flush()` waits for previously sent records to complete per the producer's contract, but it does not turn failures into ACKs.
- Kafka `close(Duration)` has specific timeout/shutdown behavior that must be checked for your version; do not call close from inside the I/O callback itself.
- RabbitMQ requires managing pending confirmations and connection/channel lifecycles; some callbacks must not perform publish I/O on the same callback thread.
- JMS async close/commit has callback waiting requirements and threading constraints; follow provider/container rules.
- Flushing a logging appender only flushes **log data**; it does not wait for the broker to process messages.

SIGKILL, fatal JVM crashes, or power loss can bypass graceful shutdown. Critical events require recovery via a durable outbox or queue, not just `finally` blocks or shutdown hooks.

## 21. Testing Producer Logging Before Production

A good test suite should use a **fake producer/test broker** and real log records captured from an appender/collector, not just mocking `LOG.info(...)`.

| Case | Test behavior | Expectation |
| --- | --- | --- |
| Send success | Client callback succeeds | `BROKER_ACKED` present with valid ID and metadata |
| Send API throws | Serializer/config rejects immediately | `CLIENT_REJECTED` present; no ACK reported |
| Async failure | Future/callback reports error | `PRODUCE_FAILED` present with correct error code |
| Indeterminate timeout | No ACK received within deadline | `OUTCOME_UNKNOWN` present; does not log "LOST" |
| Retry succeeds | Attempt 1 fails, attempt 2 ACKs | Same logical ID, two attempts, one confirmed success |
| Retry causes duplicate | Broker received before timeout | Consumer/producer dedup/idempotency behaves per policy |
| Kafka `acks=0` | No broker ACK per protocol | Logs do not claim durable ACK |
| Rabbit publisher confirm ACK + return | Broker confirms but fails to route | Distinguishes confirmed vs routed |
| JMS async | `onCompletion/onException` | Logged accordingly, respects threading/session rules |
| Different callback thread | Caller MDC not auto-propagated | Correlation ID/trace context captured accurately |
| Shutdown with pending | Close/flush with incomplete callbacks | Does not claim delivered before signal arrives |
| Producer crash | Sudden JVM termination | Recovers from outbox if required by policy |
| Payload with fake secret | Event body contains `TEST_SECRET_DO_NOT_LOG` | Secret never appears in logs, metrics, traces, or error messages |
| Large/unusual messages | JSON, binary, unicode | Safe schema logging, no body dump |
| High load burst | Queue near full, slow broker | Metrics/alerts on inflight, backpressure, drops |
| Debug toggled off/on | Log level changes | Important ACK/FAIL outcomes remain observable per policy |

In unit tests, remember that callbacks may run **immediately, later, or on another thread**. Avoid relying on `Thread.sleep(100)` to assert a callback finished; use `CompletableFuture`, `CountDownLatch`, a test executor, or mock confirms with explicit deadlines.

When using a real test broker, verify both broker and consumer sides, including topic/queue durability, publisher confirms, retries, headers, record metadata, and alerts on network loss.

## 22. Investigation Scenario: Reported Sent, but Consumer Sees Nothing

**Symptom:** the HTTP service returns 202 and the producer logs "message sent," but downstream systems have no data.

Ask questions in order:

1. Did the producer log an **attempt** or an actual **broker ACK**? Was there a callback? Was there a synchronous error?
2. Does the Kafka record have a valid `topic/partition/offset` according to `acks` and broker settings? For RabbitMQ, did the confirm ACK come with proper routing/no return?
3. Is the consumer subscribed to the right topic/queue, and is there group lag, permission issues, pausing, or rebalancing?
4. Did a schema/serializer mismatch cause the consumer to reject the message and route it to a DLQ?
5. Does the message have TTL, retention, compaction, dead-lettering, or expiry?
6. Did the consumer process it, fail at the database, and retry/rollback?
7. Did the correlation ID travel across hops and get logged safely at the consumer?
8. Could a producer retry have caused the consumer to see two copies and deduplicate them into one outcome?

If you only find `logger.info("sent")` right after `send()`, that evidence is unreliable. You must observe the actual milestones and systems involved. The "ACKed properly, but consumer didn't process" case usually requires investigating the consumer, routing, or schema rather than just adding producer retries.

## 23. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Logging `SUCCESS` right after `producer.send(...)` | Marks success before ACK | Log completion inside callback/Future/confirm |
| Not catching errors at call site | Loses pre-callback serialization/config errors | Handle both synchronous and asynchronous failures |
| Treating every timeout as "broker didn't receive" | Retries may create duplicates | Use `OUTCOME_UNKNOWN`, idempotency, and reconciliation |
| Treating publisher confirm as consumer ACK | Falsely reports business completion | Distinguish each confirmation boundary |
| Logging raw payload/key/headers | Leaks PII/credentials, increases I/O | Log only allowlisted metadata |
| Logging `exception.getMessage()` freely | Message may contain secrets | Safe error code/class; restricted stack traces |
| Relying only on caller MDC | Callback lacks or mixes correlation | Snapshot IDs, propagate context explicitly, clean up |
| Retrying directly inside I/O callback | Blocks event loop, deadlocks, or spikes latency | Offload retries to dedicated worker/queue |
| Logging INFO per message at high load | Log storm, GC/I/O overhead | Metrics, policy-based success sampling |
| Using `attempt` for internal client retries | Miscounts active application sends | Separate application and transport retries |
| Treating Kafka offset as a system-wide ID | Not unique across partitions/topics | Use application `eventId` |
| Ignoring RabbitMQ mandatory returns | ACKed even though message wasn't routed as expected | Monitor returns and confirms separately |
| Treating JMS callback as transaction commit | Reports completion before commit | Observe commit/rollback milestones separately |
| Assuming outbox = exactly-once | Crashes cause duplicates/replays | Deduplication and idempotent consumers |
| Closing producer too late, or closing logs first | Pending messages lost, callbacks don't run | Ordered shutdown with explicit timeouts |
| Calling `logger.flush()` to wait for broker | Flushing logs is a different layer | Use broker-specific producer/confirm APIs |
| Not monitoring pending/unknown states | Errors persist silently despite WARN logs | Metrics, alerts, DLQ/outbox backlog monitoring |
| Putting message ID or trace ID in metric labels | High cardinality, higher cost, privacy risk | Use low-cardinality classification labels |

## 24. Pre-Deployment Review Checklist

1. Is the **producer success milestone** clearly defined and separated from consumer processing?
2. Do logs include `messageId`, destination, `eventCode`, `outcome`, `attempt`, and error code when needed?
3. Does every async `send()` observe the proper callback/Future/confirm API?
4. Are exceptions thrown **at the call site** and errors returned **later** both handled?
5. Do you avoid logging `SUCCESS` when a message is only buffered/enqueued?
6. On timeout, is an `UNKNOWN` state represented instead of assuming definite loss?
7. Do retries use backoff, jitter, a retry limit, and an idempotency/dedup mechanism?
8. Are internal client retries distinguished from application-level attempts?
9. Are correlation IDs / trace context placed in envelopes/headers and captured properly on callback threads?
10. Are payloads, keys, headers, exception messages, MDC, and log schemas protected against PII/secrets?
11. Do ACK/error/retry/inflight/backpressure/outbox metrics have appropriate alerts?
12. Are callbacks fast, non-blocking on I/O threads, and avoiding direct re-publish where prohibited?
13. Have success, callback failure, synchronous exceptions, timeouts, broker down, and retry duplicates been tested?
14. Have shutdown/crash scenarios, pending sends, and callback completion within deadlines been tested?
15. If business durability is required, are outbox/transactions/recovery in place and verifiable by ID independently of logs?
16. Is documentation aligned with the running backend (exact Kafka/RabbitMQ/JMS version) and verified at the final sink?

## 25. Self-Check Questions

1. Why does a Future returned by `KafkaProducer.send` not allow logging "sent successfully" yet?
2. Does a successful Kafka callback with `acks=0` prove the broker durably ACKed the record?
3. How do Kafka `RecordMetadata.partition()/offset()` differ from an application `messageId`?
4. When `send()` throws an exception before a Future is created, where should it be logged?
5. Why should a timeout be represented as `OUTCOME_UNKNOWN` in many situations?
6. In RabbitMQ, how do publisher ACK/NACK and consumer ACK differ?
7. Why might a publisher confirm ACK not be enough to conclude a message was routed to the target queue?
8. What does `multiple=true` mean in a RabbitMQ publisher confirm?
9. Does Jakarta Messaging `CompletionListener.onCompletion` always mean a transaction has committed?
10. Why should raw payloads or `record.toString()` not be passed into DEBUG logs?
11. Why can a callback lose the sending thread's MDC, and what should be done?
12. Are three retries of the same message ID three different business events?
13. How does an outbox help avoid the dual-write problem, and why is idempotency still needed?
14. At high throughput, why can an ACK rate metric be better than an INFO log per message?
15. Can consumer processing be inferred from a broker ACK at the producer?
16. Why does closing a logging appender not automatically drain a producer's pending network sends?

**Answer key:** (1) `send` is async and the Future may still be pending; (2) no, `acks=0` does not wait for a broker ACK; (3) broker storage position vs. application logical ID; (4) in the `catch` block at the caller; (5) the response may have been lost while the broker already received it; (6) sending to the broker vs. consumer processing delivery; (7) routing/returns are a separate mechanism; (8) it confirms a range of sequence numbers; (9) no, commit is separate; (10) leaks PII/secrets and incurs I/O cost; (11) MDC is thread-local, so capture/propagate explicitly and clear afterwards; (12) same logical event with multiple attempts; (13) writes intent in the same DB transaction, though delivery can still repeat; (14) reduces log storms and cardinality issues; (15) no; (16) they are two separate subsystems with different queues and contracts.

## 26. Official References

- [Apache Kafka — KafkaProducer Javadoc](https://kafka.apache.org/44/javadoc/org/apache/kafka/clients/producer/KafkaProducer.html): `send(ProducerRecord, Callback)`, `Future<RecordMetadata>`, synchronous/asynchronous errors, and callback threads.
- [Apache Kafka — Callback Javadoc](https://kafka.apache.org/44/javadoc/org/apache/kafka/clients/producer/Callback.html): receiving metadata and exceptions from send operations.
- [Apache Kafka — ProducerRecord](https://kafka.apache.org/44/javadoc/org/apache/kafka/clients/producer/ProducerRecord.html): key/value, topic, partition, and timestamp.
- [RabbitMQ — Publisher Confirms Java Tutorial](https://www.rabbitmq.com/tutorials/tutorial-seven-java): `confirmSelect`, `addConfirmListener`, sequence numbers, `multiple`, and callbacks/threading.
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms): meaning of ACK/NACK, durability, routing, and confirmation conditions.
- [Jakarta Messaging 3.1 — MessageProducer](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/messageproducer): `send`, `CompletionListener`, threading, close, and transactions.
- [Jakarta Messaging 3.1 — Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html): asynchronous send rules and restrictions in Jakarta EE web/EJB containers.
- [Java SE 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): `handle`, `join`, and completion coordination.
- [Java SE 17 — java.util.logging.Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html): levels, logging parameters, and handlers.
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): structured logging, sensitive data, sanitization, and log management.
