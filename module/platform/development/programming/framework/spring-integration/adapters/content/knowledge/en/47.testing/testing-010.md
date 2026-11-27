# Testing Error Flows and Dead-Letter Handling

**Chapter:** Testing  
**Lesson:** Testing Error Flows and Dead-Letter Handling  
**Module:** Spring Integration Adapters (`SPRING_INTEGRATION_ADAPTERS`)  
**Scope:** Testing how inbound/outbound adapters, gateways, pollers, and `MessageChannel`s handle errors; verifying retries, error channels, recoverers, dead-lettering, acknowledgments, transactions, and replay across File/SFTP, HTTP, JMS, AMQP, Kafka, and databases.

> **Key message:** A test that merely confirms an exception appeared is **not enough**. When an integration flow fails, you must prove the message **was not lost**, **was not processed twice outside contract**, reached the right **error/recovery destination**, maintains consistent **ack/commit** state, and has a **safe reconciliation or replay path**.

## 1. Why Test Error Flows and Dead-Letter Handling?

Happy-path integration flows are easy to test: construct a message, send it through a channel, invoke an adapter, and assert the output. Real failures strike at hard-to-observe moments:

- An HTTP outbound gateway sends a request successfully, yet the response is lost.
- A Kafka consumer processes and writes to the DB, then crashes before committing offsets.
- A JMS/AMQP consumer rolls back and receives the same message again.
- An SFTP poller downloads a file, yet one record fails schema validation.
- A JDBC poller claims a row, calls an external API that times out, leaving transaction commit status unclear.
- A handler exhausts retries; the recoverer emits an `ErrorMessage`, yet the error flow has no subscriber.
- The DLQ publisher fails even though the application assumed the failure was safely stored.
- An operator replays a message that downstream already processed earlier.

These failures can cause **lost tasks**, **duplicated side effects**, **stuck poison messages**, **latency spikes**, or **silent failures**: logs record an error while the flow still reports success.

Running example: the system fetches order files from SFTP, splits them into messages, calls an HTTP API to create shipments, and persists results to a DB or emits Kafka events. If HTTP times out after three attempts, the system needs clear state and evidence:

~~~text
SFTP file/record
    -> parse + validate
    -> MessageChannel
    -> HTTP outbound handler (+ retry)
          -> success: persist result
          -> exhausted: error/recovery flow
                -> durable failure record / DLQ / quarantine
                -> alert + reconciliation/replay
~~~

**The testing question is not just "did an error happen?"**—it is "where is the final order record, who owns resolving it, and how do we know there are no duplicates?"

### 1.1. Learning Objectives

After completing this lesson, you will be able to:

1. Explain `ErrorMessage`, `errorChannel`, the `errorChannel` header, `MessagingException`, and `MessagePublishingErrorHandler`.
2. Distinguish **synchronous** errors, **asynchronous** errors, errors inside **pollers**, and errors **after retry exhaustion**.
3. Design tests across **unit**, **flow component**, **real broker/server integration**, and **failure-injection end-to-end** layers.
4. Use JUnit 5, Spring Test, `@SpringIntegrationTest`, `MockIntegrationContext`, `MockIntegration`, or `QueueChannel` within their proper scope.
5. Verify that recoverers produce `ErrorMessage`s, error flows classify failures, and DLQ/quarantine records **persist durably**.
6. Test ACK/NACK, offset commits, transaction rollbacks, idempotency, and retry budgets across adapters.
7. Test post-error replay, recovery when the error handler itself fails, metrics, and incident closure criteria.

## 2. Key Concepts to Distinguish

| Term | Meaning | What Must Be Proven in Tests |
| --- | --- | --- |
| **Error flow** | Flow receiving failure info and deciding how to handle it | Errors reach the right flow without being dropped |
| **`ErrorMessage`** | Spring Message whose payload is a `Throwable` | Expected exception/cause with sufficient context |
| **`errorChannel`** | Error channel by header or global bean name | Errors route accurately for the endpoint type used |
| **Retry** | Re-invoking an operation on an allowed error class | Attempt counts, backoff, total time limit |
| **Retry exhaustion** | Retry policy permits no more attempts | Recovery executes exactly once as designed |
| **Recoverer / `RecoveryCallback`** | Decision after retries exhaust | Propagate, archive, DLQ, or fallback per contract |
| **Dead-letter queue/topic (DLQ/DLT)** | Destination holding unprocessable messages | Published successfully and readable/replayable |
| **Quarantine store** | Dedicated store holding failed items for investigation/fix | Retention, owner, reference, and audit exist |
| **Acknowledgment** | Confirms source receipt/processing per protocol | Never ACK when operation loss risk remains |
| **Transaction** | Commit/rollback boundary | Failures never leave corrupted state |
| **Idempotency** | Running the same business operation multiple times causes no extra effects | Redelivery/replay never duplicates side effects |
| **Reconciliation** | Determining the true downstream outcome | Never guess FAILED when response was lost |

### 2.1. An Error Channel Is Not Automatically a DLQ

An `ErrorMessage` sent to an in-memory `DirectChannel`, `PublishSubscribeChannel`, or `QueueChannel` **does not mean** it is durably persisted like a broker DLQ. To ensure failures survive restarts, the error flow must publish to a durable destination or persist failure records to safe storage—and **verify that persistence**.

### 2.2. Retry Exhaustion Does Not Mean Processing Never Happened

For operations with side effects, timeouts can occur **after the remote service commits**. Because the response is lost, the caller does not know the outcome. Blindly replaying an order-creation POST can create duplicates. Tests must simulate **unknown outcomes**, forcing the flow to use operation IDs/idempotency keys or partner status lookups before replaying.

### 2.3. DLQ Is Not a Final Business State

Messages landing in a DLQ may represent:

- Schema errors needing data correction.
- Auth/permission config errors needing ops intervention.
- Infrastructure outages that exhausted retries.
- Unknown outcomes needing reconciliation.
- Poison messages that fail consumers every time.

Thus "moved to DLQ" means only **handed off to failure management**, not that business work succeeded or was resolved completely.

## 3. Exception Path Map

~~~mermaid
flowchart TD
    SRC["Inbound adapter / gateway / poller"] --> CH["MessageChannel"]
    CH --> H["MessageHandler / outbound adapter"]
    H --> Q{"Handler throws?"}
    Q -->|No| OK["Normal reply / next channel"]
    Q -->|Yes| MODE{"Sync or async/poller?"}
    MODE -->|Caller thread / DirectChannel| CALL["Exception reaches caller<br/>unless caught/routed separately"]
    MODE -->|Executor/TaskExecutor or poller| PUB["MessagePublishingErrorHandler"]
    PUB --> EC["errorChannel header or global errorChannel"]
    EC --> ROUTE["Error router / service activator"]
    H -.-> RETRY["RequestHandlerRetryAdvice"]
    RETRY --> EXH{"Retry exhausted?"}
    EXH -->|Yes, recovery callback| REC["ErrorMessageSendingRecoverer or custom recoverer"]
    REC --> RCH["Dedicated recovery channel"]
    ROUTE --> STORE["Durable failure store / broker DLQ / quarantine"]
    RCH --> STORE
    CALL --> SOURCE["Caller / source transaction / gateway error contract"]
    STORE --> TEST["Verify evidence + ack + replay policy"]
    SOURCE --> TEST
~~~

This diagram shows **possible paths**; a single exception does not traverse every branch. Advice placement, threading, inbound endpoint type, and handler configuration determine the actual path.

### 3.1. `DirectChannel`: Synchronous Errors

A `DirectChannel` normally invokes its subscriber on the sender's thread. When the handler throws:

~~~text
JUnit thread -> channel.send(message) -> handler -> exception
                                  <- exception propagates
~~~

Therefore tests using `assertThrows(...)` or inspecting the root cause are usually more accurate than waiting for an `ErrorMessage` on the global `errorChannel`. **Do not assume every synchronous exception is automatically published by the framework to `errorChannel`.**

### 3.2. `ExecutorChannel`/Pollers: Asynchronous Errors

When a `TaskExecutor` processes a message, the sender may have returned before the handler throws. Spring Integration supports publishing errors as `ErrorMessage`s via appropriate error handlers. Poller tasks can use `MessagePublishingErrorHandler` to route errors to an error channel.

Tests must therefore **observe async error channels/conditions**, not just assert exceptions on the `send` calling thread.

### 3.3. Error Routing Resolution

When using `MessagePublishingErrorHandler`, lookup order for the error destination is typically:

1. `MessageHeaders.ERROR_CHANNEL` on the message being processed, if present.
2. Global channel named `errorChannel`.

A recoverer wired with an **explicit recovery channel** sends failures there instead of the global `errorChannel`. Tests must specify exactly which route is expected without ambiguity.

## 4. What Does an ErrorMessage Contain?

`ErrorMessage` is a message whose **payload is a `Throwable`**. For errors handled by Spring Integration, the payload may be a `MessagingException` holding the failed message, or an exception wrapped depending on adapter/execution path.

Useful details to assert in tests:

- **Exception class and root cause:** timeout, validation, auth, broker failure, DB conflict...
- **Failed message:** `MessagingException.getFailedMessage()` when available.
- **Original message:** `ErrorMessage.getOriginalMessage()` if provided by `ErrorMessageStrategy`.
- **Headers:** correlation ID, source adapter ID, business operation ID, message ID, tenant ID where policy permits.
- **Flow/endpoint identity:** identifies which handler failed.
- **Attempt history:** how many attempts occurred under the real retry policy.
- **Destination decision:** error flow chose quarantine, DLQ, rethrow, or fallback.

### 4.1. Is `originalMessage` Always Present?

**No.** Depending on the exception and `ErrorMessageStrategy`, `originalMessage` or `getFailedMessage()` may be absent or reflect a different stage in the flow. Especially after transforms/splits, the failing message may differ from the initial raw input.

An extractor feeding a failure record should apply a policy like:

~~~text
if ErrorMessage.originalMessage exists:
    use safely selected fields from originalMessage
else if throwable is MessagingException and failedMessage exists:
    use safely selected fields from failedMessage
else:
    use correlation in logging/trace/input metadata;
    record MISSING_ORIGINAL_CONTEXT, do not fabricate payload
~~~

### 4.2. Never Compare Verbatim Stack Trace Strings

Stack traces shift across runtimes, wrappers, and versions. Stable tests assert:

- Exception type/category or root cause.
- Meaningful business error content if part of the contract.
- Message correlation and metadata.
- Retry/recovery/DLQ behavior.

Avoid asserting stack-trace line counts or full `Throwable.toString()` outputs.

## 5. Default `errorChannel` and Consequences of Having No Subscribers

Spring Integration provides a global `errorChannel` for paths needing message-based error handling. In many releases, the default channel is a **`PublishSubscribeChannel`** with a logging subscriber; requiring subscribers can make dispatch failures explicit instead of silently dropping errors.

Things to test:

1. Global channel exists in the application context.
2. Custom `errorChannel` has the expected channel type and consumers.
3. The `errorChannel` header takes precedence on supported publishing paths.
4. If the channel has no subscribers, failures are not silently ignored—or throw/alert as configured.
5. If the error handler consumer throws, does upstream retry/nack as designed?
6. During app shutdown, do errors in in-flight tasks drop messages?

**Never alter global error channel config inside a test in a way that accidentally changes production semantics.** Use an isolated test context or a dedicated channel for the flow under test.

### 5.1. Why Testing an `ERROR` Log Is Not Enough

A logging subscriber recording an exception is only a **signal**. If the source message was ACKed without durably persisting the failure, no replay is possible; the flow still fails reliability guarantees even with a full stack trace in logs.

## 6. Test Pyramid for Error Flows and Dead-Letter Handling

| Test Level | Primary Checks | Suggested Tools | What Not to Infer |
| --- | --- | --- | --- |
| **Unit** | Error classification, failure envelope building, redaction, retry decisions | JUnit 5, Mockito, AssertJ | Real broker DLQ publish succeeded |
| **Flow/component** | Handler advice, channel routing, `ErrorMessage`, discard/recovery handlers | Spring Integration test, `QueueChannel`, `MockIntegrationContext` | Real broker acks/offsets |
| **Adapter integration** | Protocols, connections, transactions, redelivery, DLQ/DLT | Testcontainers/embedded brokers, fake SFTP/HTTP | Full end-to-end guarantees |
| **End-to-end failure injection** | Crash windows, store outages, replay, idempotency, reconciliation | Container restarts, network faults, observability | Every production failure covered |
| **Operational drill** | Runbooks and backlog ownership | Authorized staging environment | Payload audit or security can be skipped |

### 6.1. Why Multiple Layers Are Needed

Unit tests run fast and isolate your logic, yet miss RabbitMQ acks or Kafka offsets. Integration tests with real brokers prove redelivery, yet run slower. Drills prove failure records survive restarts, yet require careful test resource management.

### 6.2. Rules for Non-Flaky Timing-Independent Tests

- Prefer `QueueChannel.receive(timeout)`, latches, Awaitility, or bounded signals.
- Use reasonable finite timeouts—never arbitrary `Thread.sleep` calls to "wait for the system."
- For retries with backoff, use zero-delay or short test backoff policies.
- Never assert millisecond-exact durations when schedulers/brokers have jitter.
- Reset metadata stores, queues, databases, mocks, and test fixtures after every case.

## 7. Testing Utilities in Spring Integration

Spring Integration provides:

- **`spring-integration-test-support`:** helpers for unit/component tests.
- **`spring-integration-test`:** testing framework offering `@SpringIntegrationTest`, `MockIntegrationContext`, integration mocks, and Spring test context support.
- **Spring Test + JUnit 5:** `@SpringJUnitConfig`, `@SpringBootTest` when appropriate, `@DirtiesContext` when context isolation is truly required.
- **`MockIntegration`:** mocks `MessageSource`, `MessageProducer`, `MessageHandler`, and `MessageChannel` to test target flow segments.
- **`QueueChannel`:** captures messages at a checkpoint for assertions.
- **`OnlyOnceTrigger`:** limits a poller to fire a single event in suitable unit/integration tests.
- **`MockIntegrationContext`:** swaps message sources/handlers, disables endpoint auto-start, and resets after tests.

### 7.1. Controlling Pollers in Tests

If a test loads a real application context where SFTP/JDBC/AMQP inbound adapters auto-start, the test may hit live systems, race, or ingest external data.

~~~java
@SpringJUnitConfig(MyIntegrationConfig.class)
@SpringIntegrationTest(noAutoStartup = {"sftpInbound", "jdbcPoller", "*Source*"})
class ErrorFlowTests {
    @Autowired
    MockIntegrationContext mockIntegrationContext;

    @AfterEach
    void restore() {
        mockIntegrationContext.resetBeans();
    }
}
~~~

Patterns in `noAutoStartup` must match **endpoint bean names**. Do not assume a Java config method name always equals the internal endpoint ID across every DSL style. Tests should verify which endpoints had auto-start suppressed.

### 7.2. Substituting a MessageSource in Tests

~~~java
MessageSource<String> fakeSource =
        () -> new GenericMessage<>("one-test-message");

mockIntegrationContext.substituteMessageSourceFor(
        "myPollingEndpoint", fakeSource);
~~~

This snippet illustrates the API; running it requires proper imports and a `myPollingEndpoint` bean that is a compatible `SourcePollingChannelAdapter`. When a test needs only a single poll, `OnlyOnceTrigger` or a supported replacement trigger prevents repeated emissions.

**Note:** A **mock source** tests error routing in the flow, not SFTP remote file filters, JMS acknowledgments, or Kafka offset commits. Those require protocol-specific integration tests.

## 8. Classifying Errors to Build a Test Matrix

| Error | Default Retry Consideration | What Tests Verify |
| --- | --- | --- |
| HTTP timeout / network reset | Bounded retry if operation is idempotent | Attempts, backoff, recovery, and unknown outcome |
| HTTP 429 / transient 503 | Retry per contract and rate limits | Honors `Retry-After` if supported |
| Invalid JSON/schema | Usually do not retry | Immediate quarantine keeping controlled input/reference |
| HTTP 401/403 | Usually requires auth/permission fix | No retry storm; alerts owner |
| JMS/AMQP deserialization | Likely poison message | Routed to DLQ per policy without blocking queue forever |
| Kafka deserialization | May occur **before** business handler | Container/deserializer error path, DLT, offsets |
| JDBC unique conflict | May be valid duplicate or contract bug | Business decision; no blind retries |
| SFTP transfer interrupted | Retry transfer/finalize per source policy | Partial local file never processed |
| Downstream commits then response lost | Unknown outcome | Reconcile/idempotency before replay |
| Recovery archive/DLQ publish fails | Failure of error flow itself | Never ACK source if it would drop message |

Do not collapse every exception into a generic `RuntimeException` and test one path: **retryable vs. non-retryable classification** and **which layer throws** dictate real behavior.

## 9. Testing Synchronous Flows: Exceptions Reaching Caller

A simple broker-free test proving a synchronous handler throws errors:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.*;

class SynchronousErrorFlowTest {

    @Test
    void handlerFailurePropagatesToSender() {
        DirectChannel input = new DirectChannel();
        input.subscribe((MessageHandler) message -> {
            throw new IllegalStateException("simulated downstream outage");
        });

        Message<String> request = MessageBuilder
                .withPayload("order-971")
                .build();

        RuntimeException failure = assertThrows(
                RuntimeException.class, () -> input.send(request));

        // Framework may wrap exceptions; unwrap to root cause instead of
        // casting the top-level exception.
        Throwable root = failure;
        while (root.getCause() != null) {
            root = root.getCause();
        }
        assertInstanceOf(IllegalStateException.class, root);
        assertEquals("simulated downstream outage", root.getMessage());
    }
}
~~~

**What does this test prove?** `DirectChannel` executes synchronously and exceptions propagate to the caller when no other catch/routing mechanism exists. It **does not** prove an `ErrorMessage` was sent to the global `errorChannel`.

### 9.1. Additional Tests Needed on Gateways

When a flow begins at an inbound HTTP gateway, exceptions may map to HTTP statuses/bodies per gateway/app error handling. Tests must assert:

- Status codes match business/infrastructure error classes.
- Never return `200 OK` when processing failed.
- Correlation ID and error code appear without leaking secrets.
- Caller timeout aligns with total retry duration.

## 10. Unit Testing `ErrorMessage` and Failure Envelopes

You can construct an `ErrorMessage` and invoke an **application error handler** directly to test error classification and failure-record persistence without starting a broker.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.*;

class FailureEnvelopeTest {

    @Test
    void preservesBusinessCorrelationAndRootCause() {
        Message<String> request = MessageBuilder
                .withPayload("sensitive-payload-reference")
                .setHeader("operationId", "order:create:T42:971")
                .setHeader("correlationId", "trace-84021")
                .build();

        Exception cause = new IllegalStateException("partner unavailable");
        MessagingException wrapped =
                new MessagingException(request, "handler failed", cause);

        ErrorMessage error = new ErrorMessage(wrapped, request);

        assertSame(request, error.getOriginalMessage());
        assertSame(request, wrapped.getFailedMessage());
        assertSame(cause, wrapped.getCause());
        assertEquals("trace-84021",
                error.getOriginalMessage().getHeaders()
                        .get("correlationId"));
    }
}
~~~

This is an **object contract unit test**; because we constructed `ErrorMessage` manually, it **does not prove the framework routes errors from an adapter automatically**. Routing tests must send messages through a real flow, observe channels, and assert attempt counts.

### 10.1. Business Failure Envelope

~~~json
{
  "failureId": "fail-20261123-001",
  "sourceAdapter": "sftp-orders",
  "destinationAdapter": "partner-http",
  "businessOperationId": "order:create:T42:971",
  "sourceMessageId": "msg-84021",
  "correlationId": "trace-84021",
  "errorCategory": "PARTNER_TIMEOUT",
  "terminalRetryState": "RETRY_EXHAUSTED",
  "attemptsObserved": 3,
  "outcome": "UNKNOWN_REQUIRES_RECONCILIATION",
  "payloadReference": "encrypted-store:orders/msg-84021",
  "owner": "integration-platform",
  "occurredAt": "2026-11-23T08:05:00Z"
}
~~~

This is an **application-defined schema**, not an `ErrorMessage` structure generated automatically by Spring. **Never log raw payloads, Authorization headers, access tokens, SFTP passwords, or session secrets.**

## 11. Testing Synchronous vs. Asynchronous Error Routing

A trustworthy test distinguishes two mechanisms:

| Condition | Valid Assertion |
| --- | --- |
| `DirectChannel` handler throws | Caller catches exception unless caught/routed elsewhere |
| Async handler via `TaskExecutor`/poller error handler | `ErrorMessage` lands on dedicated/global `errorChannel` per config |
| `errorChannel` header points to test channel | Test channel receives error on supported paths |
| Error publishing fails | Error recorded/propagated per policy; no fake success |
| Error lacks original context | Failure handler reports missing context auditably without fabricating data |

### 11.1. Pseudocode Test with QueueChannel

~~~text
Given:
    dedicatedErrorChannel = QueueChannel
    inbound message carries header errorChannel = dedicatedErrorChannel
    handler runs in async environment configured with ErrorMessage publisher
    handler throws SimulatedBusinessException

When:
    send message to input channel

Then:
    error = dedicatedErrorChannel.receive(timeout)
    assert error is ErrorMessage
    assert rootCause(error.payload) is SimulatedBusinessException
    assert correlationId is preserved or clearly mapped
    assert no business success result exists
~~~

The crux is **crossing a genuine async error-handling boundary**. Sending to a `DirectChannel` and waiting on a queue fails from wrong expectations, not a framework bug.

### 11.2. Pollers and Error Handlers

When testing scheduled polling:

1. Prevent production pollers from auto-starting at context boot.
2. Use fake sources/triggers bounding poll counts.
3. Configure or verify `MessagePublishingErrorHandler`.
4. Have the handler throw an identifiable exception.
5. Assert `ErrorMessage` reaches the designated channel.
6. Verify source state: can the file/JDBC row/broker record still be reprocessed?

Never equate a poller publishing an `ErrorMessage` with the source automatically rolling back or moving to a DLQ.

## 12. Testing Retry Exhaustion and Recoverers

`RequestHandlerRetryAdvice` retries a **message handler**. A `RecoveryCallback` can be configured to decide what happens after retries exhaust; `ErrorMessageSendingRecoverer` is one option for sending an `ErrorMessage` to a channel.

### 12.1. Mandatory Assertions

1. Handler invoked the exact **configured and observed number of attempts**.
2. Handler succeeds before exhausting → **recoverer does not run**.
3. Handler throws retryable error to limit → **recoverer runs** and receives final error.
4. Handler throws non-retryable error → no pointless retries; takes configured branch.
5. Recoverer publishes `ErrorMessage` to the **right channel**.
6. Recoverer failure → never swallowed so upstream falsely ACKs.
7. Never invokes downstream an (N+1)th time inside `RecoveryCallback` uncontrollably.
8. Total attempts account for SDK, handler, container, and broker retries combined.

### 12.2. Warning About Spring Retry Versions

Do not copy a "default retry count" across Spring Integration/Spring Retry releases and assume total attempts from config alone. Newer APIs may expose `RetryPolicy.maxRetries`, whereas Spring Retry 2.x `RetryTemplate`/`SimpleRetryPolicy` examples use `maxAttempts`.

**Durable testing approach:** configure policies **explicitly**, inject an `AtomicInteger` into a fake handler, and observe `invokeCount` and terminal recovery. Document exact library versions and "initial attempt" vs. "retries" semantics in runbooks.

### 12.3. Test Matrix

| Case | Handler Behavior | Expectation |
| --- | --- | --- |
| Immediate success | First call succeeds | 1 call, no recovery |
| Two failures then success | Transient exceptions, then OK | Only needed attempts, no DLQ |
| Always fails | Retryable exception | Exhausted, single terminal recovery per flow |
| Non-retryable | Invalid payload/auth | No repeated retries; quarantined/propagated |
| Recoverer archive succeeds | Error flow persists durably | Terminal failure record, ACK as designed |
| Recoverer archive fails | Recovery DB/broker down | Failure propagates/source retained; no fake success |
| Retries exceed gateway timeout | Caller expires before recovery | Redesign timeout budget |
| Broker redelivery after handler retries | Source rethrows | Total attempts and DLQ stay within limits |

## 13. Testing Error Handler Secondary Failures

This case is often forgotten: **the primary handler fails**, and the error flow fails too.

~~~mermaid
flowchart TD
    IN["Source message"] --> MAIN["Business handler"]
    MAIN -->|Exception| RET["Retry / error publisher"]
    RET --> REC["Recovery handler"]
    REC -->|Persist succeeds| STORE["Durable failure record / DLQ"]
    REC -->|Persist fails| FAIL["Throw / NACK / rollback or pause per policy"]
    STORE --> ACK["Ack/commit only after criteria met"]
    FAIL --> HOLD["Source retains ownership / recovery incident"]
~~~

Cases to test:

- Archive DB loses connection.
- DLQ broker becomes unavailable.
- Failure envelope serialization errors.
- Quarantine store full.
- Error channel has no subscribers.
- Error channel subscriber throws an exception.
- App restarts before failure persistence is confirmed.

**Acceptance criterion:** Never enter a state where "source ACKed, primary business work didn't run, and no failure record exists," unless the contract explicitly permits documented data loss.

## 14. Real Dead-Letter Testing Differs from ErrorMessage Testing

A test observing only an `ErrorMessage` in a `QueueChannel` proves **error routing**, not **dead-letter persistence**.

Real dead-letter tests need:

1. **Real source** or test broker matching production behavior.
2. **Failure triggered** the way the real adapter/container sees it.
3. **Retries/redelivery** occurring per configured policy.
4. **Terminal failure** published to DLQ/DLT/quarantine.
5. **Readable record** retaining payload/reference and headers per contract.
6. **Original data never lost** across the publish/ack window.
7. **Replay** tested with a fixed business key.
8. Poison messages moved to DLQ never auto-replay in an infinite loop.

### 14.1. Fields to Assert in the DLQ

| Field | Purpose |
| --- | --- |
| Source topic/queue/file | Trace origin |
| Message ID / operation ID | Link to delivery and business action |
| Correlation ID | Tie traces, transactions, failures |
| Error classification | Explain why it failed |
| Attempt lineage | Track retries across layers |
| Failure timestamp | Manage SLAs and retention |
| Original payload/reference | Enable replay and investigation |
| Schema/version | Deserialize accurately on replay |
| Target destination | Identify failing adapter |
| Re-drive status/owner | Govern DLQ lifecycle |

Assert only headers/fields **supported by the product and contract**. Never assume every broker stores identical metadata automatically.

### 14.2. Testing Poison Messages

Permanent errors like invalid schemas must not retry infinitely and stall partitions/queues. Tests must verify the message moves to quarantine or DLT per policy while healthy messages behind it continue processing per the source's **ordering and error-handler semantics**.

## 15. JMS: Testing Rollbacks, Redelivery, and DLQs

For JMS inbound adapters, behavior depends on the listener container, `Session`, acknowledgment mode, transactions, and broker dead-letter policy.

### 15.1. Success Case

~~~text
Produce message K
 -> JMS consumer receives
 -> Spring Integration handler commits business result
 -> JMS transaction/ack succeeds

Assert:
  business output accurate
  source queue no longer holds pending record
  DLQ does not contain K
~~~

### 15.2. Handler Failure Case

~~~text
Produce K
 -> handler throws
 -> session rollback / consumer redelivery per configuration
 -> delivery count hits broker limit
 -> broker DLQ receives K
~~~

**Do not assume** `ErrorMessageSendingRecoverer` alone causes the JMS broker DLQ to receive messages. If the recoverer publishes an error and returns normally, the container may treat the delivery as handled and commit per config. When relying on broker-native DLQs, verify matching **exceptions/rollbacks/nacks**.

### 15.3. JMS Test Checklist

- Redelivery count/flag observable on the test broker.
- Rollback genuinely occurs when handler or recovery persistence fails.
- DLQ receives the exact message after terminal failure.
- If failure archiving succeeds and listener ACKs, message is not processed twice.
- Connection restarts between business commit and JMS ACK → idempotency holds.
- Non-retryable errors follow policy without infinite loops.

## 16. AMQP/RabbitMQ: DLX, Ack, and Requeue

RabbitMQ handles acknowledgments, `basic.nack`/reject, requeue, and dead-letter exchanges (DLX) per configuration. Spring AMQP listener containers have specific behavior for exceptions, retry advice, and message conversion.

### 16.1. Designing Broker DLQ Tests

~~~text
orders.queue
   |
   | failed delivery, rejected/nacked without requeue
   v
orders.dead-letter-exchange
   |
   v
orders.dlq
~~~

Tests must provision real exchange/queue/routing-key test fixtures rather than merely asserting a `deadLetterChannel` string in application config.

### 16.2. Test Cases

| Situation | What to Assert |
| --- | --- |
| Transient error then success | Nothing in DLQ; processed once functionally |
| Permanent error | DLQ receives accurate payload/reference per policy |
| Unbounded `requeue=true` | Detects poison-message loop; rejected as terminal strategy |
| Misrouted DLX | Message never vanishes silently; test fails clearly |
| Consumer ACKs before failure persistence | Test catches operation-loss risk |
| Broker restart | Durable queues/messages survive per config |
| Two consumers | Duplicates/out-of-order and idempotency tested |

### 16.3. Never Infer DLQ Delivery from Logs Alone

An `AmqpRejectAndDontRequeueException` or equivalent reject mechanism can route to DLX when the broker queue is configured properly, yet **you must verify the broker route itself**. A log line saying "dead letter" does not prove the DLQ holds a record.

## 17. Kafka: DLT, Offsets, and Container Error Handling

With Kafka, **Spring Integration Kafka adapters** and **Spring for Apache Kafka listener containers/error handlers** have distinct boundaries. Using `DefaultErrorHandler` with `DeadLetterPublishingRecoverer` in a matching setup can publish failed records to a **dead-letter topic (DLT)**.

**Do not conflate:**

- Spring Integration's `ErrorMessageSendingRecoverer`: sends an `ErrorMessage` to a channel.
- Spring Kafka's `DeadLetterPublishingRecoverer`: publishes a failed Kafka record to a configured topic.
- An `errorChannel` inside a flow: routes error messages without directly altering consumer offset commits.

### 17.1. Flow to Test

~~~mermaid
flowchart TD
    T["orders topic"] --> C["Consumer / SI inbound adapter"]
    C --> H["Business handler"]
    H -->|Success| COM["Commit/ack offset per config"]
    H -->|Failure| EH["Listener/container error handler"]
    EH --> RET{"Retries left?"}
    RET -->|Yes| H
    RET -->|No| DLT["DeadLetterPublishingRecoverer -> orders.DLT"]
    DLT --> VERIFY["Verify published DLT record"]
    VERIFY --> OFFSET["Offset/transaction outcome per config"]
~~~

General diagram; exact seek, retry, batch/record listener, transactional recovery, and offset behavior depend on version and config. Never assume a message traverses only one retry layer.

### 17.2. Testing with an Isolated Kafka Broker

1. Create input topic and DLT with partition counts matching policy.
2. Use a dedicated consumer group per test; reset state between cases.
3. Produce a record carrying `businessOperationId`.
4. Have the handler throw a marked permanent or retryable exception.
5. Observe retries and container callbacks accurately.
6. Use a separate consumer to read from the DLT.
7. Assert key, value/reference, and origin topic/partition/offset headers if supplied by the publisher.
8. Assert offset state and confirm subsequent records are not skipped.
9. Test DLT publisher failure: never assume the record recovered.

### 17.3. How Critical Is DLT Publish Failure?

If the DLT producer fails, the pipeline must never mark the record recovered as if saved. Spring Kafka exposes options to inspect publish results and handle recovery failures depending on version. Tests must observe **publisher outcomes and container behavior** rather than just verifying a recoverer method was called.

### 17.4. Deserialization Errors

Key/value deserialization errors can occur **before the business handler is ever invoked**. With `ErrorHandlingDeserializer` or equivalent mechanisms, the container receives error details and can forward raw records to the DLT. Tests must:

- Produce malformed bytes expected to fail deserialization.
- Confirm the business handler did not run.
- Confirm the error path does not stall the partition indefinitely.
- Confirm the DLT contains necessary data/references per security policy.

## 18. File/SFTP: Quarantine and Checkpoints

File/SFTP lacks a broker DLQ/ack model like JMS/AMQP/Kafka. Tests must verify **file lifecycles**, filter metadata, and per-record states.

### 18.1. Failure Points to Simulate

| Failure Point | Evidence to Verify |
| --- | --- |
| SFTP connection/login failure | Adapter retries/logs error; no corrupted local file created |
| Mid-download abort | Staging file never processed as complete |
| Schema-invalid file | Moved to quarantine with reason/reference |
| Split record error | Per-record recovery; file not blindly marked complete |
| Re-uploaded file | Persistent filter and idempotency key work |
| App restart | Local/remote file state, filter metadata, replay accurate |
| SFTP session leak | Sessions/streams closed on both success and failure |
| Quarantine store failure | File never moved to `DONE` without durable backup |

### 18.2. File-Level vs. Record-Level Errors

~~~text
orders.csv
  row 1 -> COMPLETED
  row 2 -> INVALID_SCHEMA -> quarantine
  row 3 -> COMPLETED

File downloaded = true
File fully processed = policy-dependent (all rows handled?)
~~~

If an accept-once filter marks the file downloaded while row 2 lacks a failure record, a restart may skip the failed row. Tests must verify **file filters never substitute for per-record business-outcome evidence**.

### 18.3. SFTP Integration Tests

Use an isolated test SFTP server (Apache MINA SSHD or a compatible container), upload a fixture file, start the inbound adapter with a controlled poller, and inspect local staging and failure stores. Never connect to production SFTP or use real credentials.

## 19. HTTP Inbound/Outbound: Error Mapping and Unknown Outcomes

### 19.1. HTTP Outbound Gateways

Use an HTTP mock server to simulate:

- `503` or timeout twice, then `200` → succeeds with no dead-lettering.
- `400` invalid payload → permanent error, quarantined per policy.
- `401/403` → config/auth alert, no retry storm.
- `429` rate limited → retries per contract.
- Server **committed**, response dropped → unknown outcome; never blindly re-POST as a brand-new operation.

Suggested test tools: `MockRestServiceServer`, WireMock, mock HTTP servers/containers—chosen to match the actual HTTP client used by the outbound adapter.

### 19.2. HTTP Inbound Gateways

For errors in synchronous flows, verify:

- Matching HTTP status/body; never return `200 OK` on business failure.
- Correlation ID, error code, and security redaction accurate.
- Caller retries preserve the same `Idempotency-Key`.
- Duplicates of completed requests return valid cached results/responses.
- On failure after persisting a durable job, API may return `ACCEPTED/PENDING` per contract instead of faking `DELIVERED`.

Never use a one-way `QueueChannel` test to claim a request-reply gateway returned the right HTTP error to clients.

## 20. JDBC: Failure Tables, Row Claiming, and Rollbacks

With JDBC inbound polling, errors typically involve transactions, row claiming, concurrency, and processing states.

### 20.1. Fault Injection

~~~text
T0: poller SELECT row status=NEW
T1: claim row status=PROCESSING
T2: outbound handler fails
T3: retry exhausted
T4: write failure table/quarantine
T5: commit transaction / or rollback per policy
~~~

Checkpoints to verify:

- If T4 persistence fails, the row is never marked `COMPLETED`.
- If the transaction rolls back, the record remains eligible for re-polling.
- If the error flow persists successfully and transitions the row to `RECOVERY_PENDING`, it is no longer polled repeatedly as duplicates every few seconds.
- Two pollers never claim the same row unexpectedly.
- Unique operation keys and idempotency checks protect against upstream inserting two rows for one operation.

### 20.2. Suggested Status Table

~~~sql
CREATE TABLE inbound_jobs (
    job_id           VARCHAR(100) PRIMARY KEY,
    operation_id     VARCHAR(200) NOT NULL,
    status           VARCHAR(40) NOT NULL,
    attempt_count    INT NOT NULL,
    failure_ref      VARCHAR(200),
    updated_at       TIMESTAMP NOT NULL
);
~~~

This schema is illustrative. Tailor transactions/locking and upsert syntax to your database engine; never treat `failure_ref != null` as proof the failure store persisted durably without verifying it.

## 21. Integration Test Example: Retry Exhaustion to Dedicated Recovery Channel

The example below uses **Spring Integration Java DSL**, an always-failing fake handler, `RequestHandlerRetryAdvice`, and `ErrorMessageSendingRecoverer`. The test sends a message to a `DirectChannel` and inspects a recovery `QueueChannel`.

**Version scope:** uses `RetryTemplate`/`SimpleRetryPolicy` APIs in the style of **Spring Integration 6.x and Spring Retry 2.x**. Newer Spring Integration/Spring Retry versions may alter policy APIs; check your project's dependencies before copying verbatim. The test objective remains unchanged: **count actual attempts and confirm the terminal message lands on the recovery channel**.

### 21.1. Test Configuration

~~~java
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.handler.advice.ErrorMessageSendingRecoverer;
import org.springframework.integration.handler.advice.RequestHandlerRetryAdvice;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHandler;
import org.springframework.retry.backoff.NoBackOffPolicy;
import org.springframework.retry.policy.SimpleRetryPolicy;
import org.springframework.retry.support.RetryTemplate;

@Configuration
@EnableIntegration
class RecoveryFlowTestConfig {

    @Bean
    MessageChannel testRequests() {
        return new DirectChannel();
    }

    @Bean
    QueueChannel testRecoveryChannel() {
        return new QueueChannel();
    }

    @Bean
    AtomicInteger handlerAttempts() {
        return new AtomicInteger();
    }

    @Bean
    RequestHandlerRetryAdvice testRetryAdvice(
            QueueChannel testRecoveryChannel) {

        RetryTemplate retryTemplate = new RetryTemplate();
        retryTemplate.setRetryPolicy(new SimpleRetryPolicy(3));
        retryTemplate.setBackOffPolicy(new NoBackOffPolicy());

        RequestHandlerRetryAdvice advice = new RequestHandlerRetryAdvice();
        advice.setRetryTemplate(retryTemplate);
        advice.setRecoveryCallback(
                new ErrorMessageSendingRecoverer(testRecoveryChannel));
        return advice;
    }

    @Bean
    IntegrationFlow testFailureFlow(
            AtomicInteger handlerAttempts,
            RequestHandlerRetryAdvice testRetryAdvice) {

        MessageHandler alwaysFail = message -> {
            handlerAttempts.incrementAndGet();
            throw new IllegalStateException("simulated partner outage");
        };

        return IntegrationFlow.from("testRequests")
                .handle(alwaysFail, endpoint -> endpoint.advice(testRetryAdvice))
                .get();
    }
}
~~~

`NoBackOffPolicy` keeps tests fast and clock-independent. In production, design backoff/rate limiting around downstream SLAs; **never deploy a zero-backoff test config to production**.

### 21.2. JUnit Test

~~~java
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.*;

@SpringJUnitConfig(RecoveryFlowTestConfig.class)
class RecoveryFlowIntegrationTest {

    @Autowired
    MessageChannel testRequests;

    @Autowired
    QueueChannel testRecoveryChannel;

    @Autowired
    AtomicInteger handlerAttempts;

    @Test
    void publishesOneTerminalErrorAfterThreeAttempts() {
        Message<String> input = MessageBuilder
                .withPayload("order-971")
                .setHeader("businessOperationId", "order:create:T42:971")
                .build();

        // Start with a fresh message; counter bean is scoped to the test context.
        assertTrue(testRequests.send(input));

        Message<?> terminal = testRecoveryChannel.receive(1_000);
        assertNotNull(terminal);
        assertInstanceOf(ErrorMessage.class, terminal);
        assertEquals(3, handlerAttempts.get());

        Throwable error = ((ErrorMessage) terminal).getPayload();
        assertNotNull(error);

        Throwable root = error;
        while (root.getCause() != null) {
            root = root.getCause();
        }
        assertInstanceOf(IllegalStateException.class, root);
        assertEquals("simulated partner outage", root.getMessage());

        // No second terminal error message.
        assertNull(testRecoveryChannel.receive(0));
    }
}
~~~

**What the test proves:** The advice invoked the handler three times per the test policy, and the terminal error arrived on the dedicated recovery channel. **What remains unproven:** durable persistence of recovery, safe broker ACKs, or whether remote operations ran.

### 21.3. How to Extend the Test

Add scenarios for:

- Fake handler fails twice then succeeds: recoverer must **not** publish an error.
- Fake handler always throws a non-retryable exception: attempt count matches policy.
- Recovery handler saves to a fake archive preserving the source operation ID.
- Archive throws an exception: test never marks the message safely handled.
- For a reply-expecting gateway, test the caller's contract rather than just `send`.

If tests share `AtomicInteger` and `QueueChannel` in one context, **reset/drain** cleanly in `@BeforeEach` or isolate contexts. Never rely on test execution order.

## 22. Testing Recovery Handlers and Durable Archives

An `ErrorMessageSendingRecoverer` forwards errors, while the **application recovery handler** is responsible for persisting failures durably. Separate tests across two levels:

- **Unit:** Handler transforms `ErrorMessage` into the right failure record without leaking secrets.
- **Integration:** Record survives restarts in DB/DLQ and publish is confirmed.

### 22.1. Application Interface

~~~java
// Application-defined business interface, not a Spring API.
interface FailureArchive {
    void save(FailureRecord record);
}

record FailureRecord(
        String businessOperationId,
        String errorType,
        String state,
        String payloadReference) {}
~~~

A recovery handler converting `ErrorMessage` to a record:

~~~java
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.ErrorMessage;

final class RecoveryArchiveHandler {
    private final FailureArchive archive;

    RecoveryArchiveHandler(FailureArchive archive) {
        this.archive = archive;
    }

    void handle(ErrorMessage error) {
        Throwable failure = error.getPayload();
        Message<?> original = error.getOriginalMessage();

        if (original == null && failure instanceof MessagingException m) {
            original = m.getFailedMessage();
        }
        if (original == null) {
            throw new IllegalStateException(
                    "Cannot archive failure: original context is missing",
                    failure);
        }

        String operationId =
                String.valueOf(original.getHeaders().get("businessOperationId"));
        if ("null".equals(operationId) || operationId.isBlank()) {
            throw new IllegalArgumentException(
                    "Cannot archive failure without businessOperationId");
        }

        // Store only a safe payloadReference, never raw sensitive payloads.
        FailureRecord record = new FailureRecord(
                operationId,
                failure.getClass().getName(),
                "RETRY_EXHAUSTED",
                "encrypted-ref:example"
        );
        archive.save(record);
    }
}
~~~

This is an educational example illustrating **fail-closed** behavior when minimal context is missing. In production, you might recover valid context via **correlation IDs or durable metadata stores** rather than throwing immediately, while never fabricating a `businessOperationId`.

### 22.2. Testing When the Archive Works

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.messaging.support.MessageBuilder;

import static org.mockito.Mockito.*;

class RecoveryArchiveHandlerTest {

    @Test
    void archivesFailedOperation() {
        FailureArchive archive = mock(FailureArchive.class);
        RecoveryArchiveHandler handler = new RecoveryArchiveHandler(archive);

        Message<String> original = MessageBuilder.withPayload("redacted")
                .setHeader("businessOperationId", "create:T42:971")
                .build();
        ErrorMessage error = new ErrorMessage(
                new MessagingException(original, "handler failed"),
                original);

        handler.handle(error);

        verify(archive).save(argThat(record ->
                "create:T42:971".equals(record.businessOperationId())
                && "RETRY_EXHAUSTED".equals(record.state())));
        verifyNoMoreInteractions(archive);
    }
}
~~~

**Limitation:** Mockito `verify(save)` proves only **the method was called**, not that the DB/broker committed. Durability tests must read the record back from real storage.

### 22.3. Testing When the Archive Fails

~~~java
// Illustrates the core assertion, reusing original/error from the test above.
doThrow(new IllegalStateException("failure DB unavailable"))
        .when(archive).save(any(FailureRecord.class));

assertThrows(IllegalStateException.class, () -> handler.handle(error));
~~~

Follow up with an adapter integration test proving that **an archive exception** causes the broker/poller to retry, roll back, or retain the source message as designed. Never stop at unit assertions.

## 23. Checking Acknowledgments, Offsets, and Transactions

These tests are **more critical than counting stack traces**. A recoverer returning normally in app code can signal to the source that the message completed.

### 23.1. State Matrix

| Business Outcome | Failure Archived | Source ACK/Commit | Assessment |
| --- | --- | --- | --- |
| Success with evidence | Not needed | Yes | Usually sound |
| Failed, archived durably with replay owner | Yes | Yes per contract | Acceptable once ownership transferred |
| Failed, archived durably | Yes | No, broker redelivers | May create duplicate failure records; needs idempotent archive |
| Failed, archive also fails | No | Yes | **Message loss risk** |
| Failed, archive also fails | No | No, source retains message | Matches fail-safe design |
| Unknown outcome after remote timeout | Reconciliation metadata stored | Contract-dependent | Requires reconciliation/idempotency before replay |

### 23.2. Crash Windows to Test

~~~text
F1  Before receiving message.
F2  After receiving, before business handler.
F3  After downstream commits, before response.
F4  After business result commits, before source ACK.
F5  After retry exhaustion, before archiving.
F6  After archive persists, before source ACK.
F7  During DLT/DLQ publish.
F8  After DLT published, before source offset commit.
F9  After starting replay, before saving replay outcome.
~~~

For every failure point, know **whether the source redelivers, whether a failure record exists, and whether business effects duplicate**. You don't need to `kill -9` the JVM in every unit test; use targeted integration tests and controlled restart drills.

### 23.3. Testing Redelivery After Commit

Suppose a service commits DB changes for operation `K`, yet the broker ACK fails and the message redelivers. The receiver must see `K` is already `COMPLETED` and **create no second side effect**. This is enforced by **idempotent receivers/unique constraints/inboxes**, not automatically by `ErrorMessage`.

## 24. Testing Multi-Layer Retry Multiplication

An inbound adapter can face:

- HTTP client SDK automatic retries.
- Spring Integration `RequestHandlerRetryAdvice`.
- Spring Kafka or Spring AMQP container retries.
- Broker redelivery after rollback.
- Replay jobs or consumer restarts.

Hypothetical configuration example:

~~~text
HTTP client:           2 attempts / handler invocation
SI handler advice:     3 attempts / broker delivery
Broker redeliveries:   4 delivery attempts

Maximum total downstream HTTP requests in worst case:
    2 x 3 x 4 = 24
~~~

These numbers **illustrate layer multiplication**, not recommended defaults. Place counters/mock servers at the **external request boundary** to measure real call counts, not just message-handler counters.

### 24.1. Timeout Budget

If one HTTP call times out after 2 seconds and the handler allows three attempts with 0.5 s and 1 s backoffs, worst-case duration is roughly **7.5 seconds** (excluding overhead). If an inbound gateway waits only 5 seconds, the caller times out **before retry exhaustion finishes**.

Test:

- Gateway timeouts and end-to-end latency.
- Thread pools do not saturate under retries.
- Upstream and downstream backoff/rate limits.
- Error flows still finish cleanly after client disconnects.
- No further side effects are initiated once requests are cancelled if the contract specifies cancellation.

## 25. Testing Replay from DLQ/Quarantine

Landing in a DLQ is only **the beginning** of the failure lifecycle. Replay may need to:

1. Verify the underlying fault was resolved.
2. Separate permanent vs. transient vs. unknown-outcome messages.
3. Check downstream business state.
4. Preserve the **original operation ID** and payload fingerprint.
5. Record a separate `replayAttempt`/`replayId` for auditing.
6. Bound replay counts, rates, and concurrency.
7. Confirm downstream outcomes.
8. Transition failure records to `REPLAYED`, `RESOLVED`, or `ESCALATED` per contract.

### 25.1. Replay Test Matrix

| Test Case | Expectation |
| --- | --- |
| Transient outage resolved | Replay succeeds and closes failure |
| Invalid payload unfixed | Never replays endlessly; stays quarantined |
| Outcome already committed earlier | No duplicate created; reconciles cleanly |
| DLQ message missing schema/version | Read failure detected and escalated |
| Replay publish fails | Never marked resolved |
| Two operators replay same operation | Atomic claim; no duplicate side effects |
| Replay exceeds rate limit | Backoff/backpressure; never overwhelms downstream |
| Sensitive payload | Raw body never logged; accessed only with authorization |
| Failure purged by retention | Valid lifecycle/retention proven without fabricating data |

### 25.2. Never Change the Idempotency Key During Replay

~~~text
original operation key: order:create:T42:971
first delivery id:      msg-100
DLQ message id:         dlq-308
replay delivery id:     replay-22

Idempotency key sent downstream:
    still order:create:T42:971
~~~

Minting a fresh operation key per replay causes downstream systems to treat it as a brand-new business command and duplicate side effects.

## 26. Correlation, Observability, and Protecting Failure Data

### 26.1. Metrics Worth Observing

| Suggested Metric | Why Needed? |
| --- | --- |
| `integration_error_total` | Total errors by adapter/flow/category |
| `integration_retry_attempt_total` | Attempts by retry layer |
| `integration_retry_exhausted_total` | Terminal retry failures |
| `integration_error_message_published_total` | Count of published `ErrorMessage`s |
| `integration_error_message_delivery_failed_total` | Failures routing to error channels |
| `integration_failure_archive_success_total` | Failure records saved successfully |
| `integration_failure_archive_failed_total` | Failures in the recovery sink itself |
| `integration_dlq_publish_total` | Messages published to DLQ/DLT |
| `integration_dlq_backlog` | Pending unresolved failures |
| `integration_dlq_oldest_age` | Age of oldest unresolved message |
| `integration_replay_total` | Replay attempts, success/failure |
| `integration_outcome_unknown_total` | Transactions needing reconciliation |
| `integration_source_lag` | Backlog at source/file/poller/broker |
| `integration_ack_after_archive_fail_total` | Detects message-loss hazards |

These are **application-designable metric names**, not all default framework-emitted metrics. Avoid high-cardinality labels like business IDs, message IDs, or tenant IDs on metrics.

### 26.2. Safe Failure Logging

~~~json
{
  "event": "integration.dead_letter.recorded",
  "flow": "sftp-orders-to-partner-http",
  "sourceAdapter": "sftp",
  "destination": "partner-http",
  "correlationId": "trace-84021",
  "operationKeyRef": "hash:example",
  "exceptionCategory": "RETRYABLE_TIMEOUT",
  "recoveryAction": "STORE_FOR_RECONCILIATION",
  "failureRecordId": "fail-20261123-001",
  "status": "PERSISTED",
  "occurredAt": "2026-11-23T08:05:00Z"
}
~~~

**Never log raw secrets**, access keys, SFTP passwords, `Authorization` headers, cookies, PII, or customer payloads in logs/metrics. Use encrypted payload references, correlation IDs, and schema versions for investigation.

### 26.3. Testing Logs and Audits

- Exception categories map accurately.
- Correlation links original message → retries → DLQ → replay.
- Attempt counts are observed dynamically, never hardcoded.
- Logs contain zero credentials or sensitive data.
- Failure records carry owners and review SLAs.
- Failure, persistence, and replay timestamps use standard timezones/formats.
- `PERSISTED`, `REPLAY_PENDING`, and `DELIVERED` states are never conflated.

## 27. Safe Test Environment Architecture

A clean test environment isolates boundaries:

~~~mermaid
flowchart LR
    JUNIT["JUnit 5 / Spring Test"] --> CTX["Spring Integration test context"]
    CTX --> SRC["Mock source / Testcontainers broker / SFTP fixture"]
    SRC --> FLOW["Flow under test"]
    FLOW --> HTTP["HTTP stub server"]
    FLOW --> DB["Disposable DB / failure archive"]
    FLOW --> DLT["Test DLQ/DLT"]
    DLT --> ASSERT["DLQ consumer + assertions"]
    DB --> ASSERT
    CTX --> ASSERT
~~~

### 27.1. Ensuring Isolation

- Use separate topics/queues/schemas/test directories; prefer random test identifiers.
- Never use production credentials or endpoints.
- Clean up messages, failure stores, offsets, and metadata after tests.
- Close connections, listener containers, task executors, and SFTP server fixtures.
- Leave no background pollers running after tests finish.
- Use bounded short retry/backoff configs for tests while preserving the **semantics** under verification.
- For parallel tests, avoid shared state or isolate by namespace.
- Never depend on clocks and schedulers in ways that make tests flaky.

### 27.2. What Should Not Be Mocked

To prove a property, **keep the component that actually owns that property**:

| Must Be Proven | Do Not Mock Only |
| --- | --- |
| Kafka offset commit / DLT routing | `MessageChannel` or `KafkaTemplate.send` |
| JMS session rollback | Listener method |
| RabbitMQ DLX / requeue | Error flow handler |
| File accept-once across restarts | Simple `FileMessageSource` |
| SFTP stream cleanup | Parser with `String` payload |
| JDBC transaction atomicity | Repository mock |
| HTTP status/timeouts | `DirectChannel` replacing HTTP gateway |
| Failure persistence | Mocking `FailureArchive.save()` |

Mocks are valuable for **small logic units and wiring**, yet **never replace the system boundary** a test claims to verify.

## 28. Golden Test Plan for an SFTP → HTTP → DB Flow

Suppose each SFTP file record turns into an HTTP request creating a shipment, with results persisted to DB.

### 28.1. Mandatory Test Cases

| ID | Case | Conditions | Acceptance |
| --- | --- | --- | --- |
| T01 | Happy path | Valid file, partner OK | Delivered; no DLQ |
| T02 | Transient recover | Two timeouts then OK | Retried accurately, no terminal error |
| T03 | Retry exhausted | Partner always times out | Durable failure record + correlation |
| T04 | Permanent invalid | Record missing field | Quarantined, zero HTTP retries |
| T05 | Remote outcome unknown | Partner commits then drops response | No duplicate shipment created |
| T06 | Failure archive down | Failure DB store fails | Source never drops processing responsibility |
| T07 | Restart after download | App restarts mid-processing | File/record remains recoverable |
| T08 | Duplicate file | SFTP re-uploads file | No duplicate business effects |
| T09 | Re-drive | Partner recovers | Replayed with same operation key and closed |
| T10 | Poison message | Permanently invalid record | Does not block whole stream per policy |
| T11 | Concurrent consumers | Two instances pick up same record | Idempotency/claiming prevents duplicates |
| T12 | Security | Failing payload contains dummy credentials | Zero leaks in logs/metrics/unprotected DLQs |
| T13 | DLQ full/down | Recovery target cannot persist | Fail-safe and alert triggered |
| T14 | Connection recovery | SFTP/HTTP connection dropped | No leaked sessions/threads |
| T15 | Late response | Response arrives after caller timeout | Outcome reconciled, not misreported failed |

### 28.2. Why Is Test T06 Crucial?

T06 catches a classic design flaw: the recoverer receives `ErrorMessage`, `archive.save` fails, and code catches and merely logs it. The inbound flow returns normally so the source ACKs, yet neither a business outcome nor a failure record exists. A system with 100% green "happy path" tests can still silently lose messages without this test.

### 28.3. Why Is Test T05 Crucial?

An HTTP timeout never tells you whether the server committed or not. A test simulating only pre-processing `500`s misses duplicate risks. Use a mock server capable of:

1. Persisting application side effects.
2. Intentionally withholding or dropping the response.
3. Counting how many times the same `Idempotency-Key` was processed.
4. Allowing status queries by business reference.

Expected outcome: the application reconciles and never creates a second shipment.

## 29. When Tests Fail: Distinguishing Test Bugs from Product Bugs

An async test failing because `receive(1000)` returns `null` can stem from:

- Error channel misrouted.
- Endpoint stopped or `autoStartup` disabled.
- `TaskExecutor` hasn't dispatched yet.
- Error message routed to a different global `errorChannel`.
- Another subscriber consumed the message before the test read it.
- Retry/backoff exceeds the test timeout.
- Handler error swallowed by another callback.
- Broker didn't redeliver because transaction/ack mode differed from expectations.

### 29.1. Systematic Debugging Steps

1. Confirm test input arrived and the endpoint exists.
2. Confirm the handler actually ran via counter or spy.
3. Confirm the exception threw on the expected thread/boundary.
4. Check whether the error channel resolved from headers or globally.
5. Count retries and check if `RecoveryCallback` executed.
6. Inspect which channel subscriber/dispatcher or consumer read the message.
7. Check source transaction/ack/offset settings.
8. Check DLQ publish outcomes and consume via a test consumer.
9. Increase test timeouts **only when** evidence proves the system is right and the environment is merely slow.

**Never "fix" a red test by blindly adding `Thread.sleep(5000)`.** That hides races and makes suites slow and flaky.

## 30. Common Anti-Patterns

| Anti-Pattern | Consequence | Right Way to Test |
| --- | --- | --- |
| Testing only happy paths | Unknown whether data is lost on error | Failure injection + recovery assertions |
| Assuming all exceptions hit global `errorChannel` | Wrong tests for `DirectChannel` | Separate sync/async/poller semantics |
| Checking only `ERROR` logs | Failures may drop without replay | Assert durable failure records |
| Treating `QueueChannel` as broker DLQ | Messages lost on restart | Real broker/file/DB integration tests |
| Counting retries only at handler | Misses SDK/broker retries | Measure downstream boundary requests |
| Recoverer returning `null` treated as success | Upstream may ACK falsely | Assert business outcome and ACK |
| Swallowing exceptions in recovery handler | Silent loss | Test archive failures; propagate/fail-safe |
| Counting DLQ items without checking offsets | Messages lost or duplicated | Broker ack/commit assertions |
| Asserting verbatim stack traces | Flaky across versions | Root cause, category, correlation |
| Mocking `KafkaTemplate` then claiming DLT is safe | Unverified broker publish | Testcontainers/embedded Kafka |
| Auto-starting SFTP pollers in unit tests | Hits external systems or races | `noAutoStartup`, fake sources/triggers |
| Retrying invalid schemas repeatedly | Poison messages stall queues | Non-retryable/quarantine tests |
| Generating new business IDs on replay | Duplicate side effects | Keep stable operation keys |
| Conflating `FAILED` and `OUTCOME_UNKNOWN` | Blind replays after server commit | Test remote commit + lost response |
| Skipping parallel consumer tests | Duplicates when scaling out | Shared store/DB unique constraint tests |
| Writing raw payloads/secrets into DLQs | Data leaks | Redaction, encrypted references, ACLs |
| Tests relying on `Thread.sleep` | Flaky and slow | Bounded waits/latches/Awaitility |
| Skipping shutdown/restart tests | In-flight messages forgotten | Crash/restart drills |

## 31. Self-Check Exercises

### Exercise 1. DirectChannel and errorChannel

**Scenario:** A test sends a message to `DirectChannel`; the handler throws; the test waits on global `errorChannel` and receives nothing.

**Answer:** The test likely assumed wrong semantics. In synchronous flows, errors propagate back to the caller. Assert the thrown exception or configure explicit catch/routing rather than assuming global `errorChannel`.

### Exercise 2. ErrorMessage Appeared

**Scenario:** A test receives an `ErrorMessage` from a dedicated `QueueChannel` and marks DLQ testing complete.

**Answer:** Insufficient. An in-memory `QueueChannel` is not a durable broker DLQ; verify the error flow published/persisted durably and read the failure back.

### Exercise 3. Three Retries

**Scenario:** A team configures `maxRetries=3` and assumes exactly three total calls including the initial one.

**Answer:** Check the exact API/version: `maxRetries` typically counts **retries**, unlike `maxAttempts` which often includes the initial attempt. Configure explicitly and assert actual counters.

### Exercise 4. JMS Acked

**Scenario:** A recovery handler logs and returns normally; the JMS queue empties and the DLQ is empty.

**Answer:** Silent data-loss risk. Persist failures verifiably or throw to trigger rollback/redelivery per container/broker policy.

### Exercise 5. Kafka DLT

**Scenario:** Mockito verifies `DeadLetterPublishingRecoverer.accept()` was called, yet the DLT topic is empty.

**Answer:** Mock tests do not prove publishing. Run against a real test broker and inspect publish outcomes, DLT records, and offsets.

### Exercise 6. HTTP Timeout

**Scenario:** A client calls order creation, times out, and the message enters the recovery store. An operator immediately replays it.

**Answer:** Risk of duplicates if the remote committed before timing out. Reconcile via operation ID/idempotency key or status lookup before replaying.

### Exercise 7. SFTP File Downloaded

**Scenario:** A file has 100 rows; 99 succeed and 1 fails; the persistent file filter marks the file as seen.

**Answer:** File-level accept-once does not prove every row succeeded. Test per-record outcomes, quarantine/replay, and file lifecycles.

### Exercise 8. Recovery Archive Fails

**Scenario:** The DLQ publisher cannot connect; the recovery handler catches the exception and returns normally.

**Answer:** If the source ACKs/commits, operations are lost. Mandate fail-safe tests: never report recovered, keep source responsibility, or verify a durable fallback store.

### Exercise 9. Backoff and Gateway Timeouts

**Scenario:** Retry budgets exceed the caller's wait timeout.

**Answer:** Test gateway timeouts, latency budgets, and error contracts. Consider async accepted workflows or trim attempts/backoff rather than arbitrarily inflating timeouts.

### Exercise 10. Redelivery After Business Commit

**Scenario:** JDBC commits, RabbitMQ ACK drops, and the record redelivers.

**Answer:** Deduplicate via stable operation IDs and inbox/unique constraints; assert zero duplicate side effects while ACKing the broker per policy once recognized.

## 32. Implementation Checklist for Error Flow and Dead-Letter Tests

1. **Error classification:** covers transient, permanent, auth, schema, and unknown outcomes.
2. **Boundary identified:** handler on `DirectChannel`, executor, poller, or broker listener?
3. **Right channel:** `errorChannel` header, global `errorChannel`, or explicit recovery channel.
4. **Rich `ErrorMessage` context:** root cause, failed/original message, correlation when available.
5. **No brittle stack-trace assertions:** assert behavior and contracts.
6. **Explicit retries:** attempts, backoff, non-retryables, timeout budget.
7. **Explicit recovery:** propagate, durable archive, DLQ, quarantine, or valid fallback.
8. **Archive failures:** test faults on the recovery path itself and fail-safe behavior.
9. **Durable DLQ:** read records back from a real broker/store.
10. **Accurate ACK/commit:** never confirm source before a verified business result or durable handoff.
11. **Kafka offsets / JMS / AMQP:** tested against containers/brokers with real semantics.
12. **File/SFTP:** test source filters, staging, per-record failures, and session cleanup.
13. **HTTP:** test statuses/replies, retry timing, idempotency, and lost responses.
14. **JDBC:** test transactions, row claiming, unique constraints, and recovery states.
15. **Poison messages:** never cause infinite redelivery or stall the entire stream.
16. **Replay:** stable operation keys, owners, audits, reconciliation, and rate limits.
17. **Parallelism/restarts:** test concurrency, crashes, and redelivery after commit.
18. **Observability:** errors, DLQ backlog, recovery failures, oldest age, and unknown outcomes.
19. **Security:** zero tokens/PII leaked in error messages, logs, and DLTs.
20. **Test isolation:** appropriate source mocks, `noAutoStartup`, cleanup, and resource disposal.
21. **Version alignment:** verify Spring Integration, Spring Retry, Spring Kafka/AMQP, and broker APIs for your project.
22. **Report only proven claims:** unit routing never substitutes for end-to-end broker DLQ tests.

## 33. Official References

To cross-check APIs and behavior for your project's versions:

1. **Spring Integration — Error Handling:** https://docs.spring.io/spring-integration/reference/error-handling.html
2. **Spring Integration — Testing Support:** https://docs.spring.io/spring-integration/reference/testing.html
3. **Spring Integration — Provided Advice Classes / RequestHandlerRetryAdvice:** https://docs.spring.io/spring-integration/reference/handler-advice/classes.html
4. **Spring Integration — Message Channels:** https://docs.spring.io/spring-integration/reference/channel.html
5. **Spring Kafka — Handling Exceptions / DeadLetterPublishingRecoverer:** https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html
6. **Spring AMQP — Exception Handling:** https://docs.spring.io/spring-amqp/reference/amqp/exception-handling.html
7. **Spring Integration — SFTP Support:** https://docs.spring.io/spring-integration/reference/sftp.html

Examples use **JUnit 5**, Spring Test, Java DSL, and standard APIs. Newer Spring Integration/Spring Retry modules may change retry config methods or API combinations; always cross-check, compile, and run tests under your project's **BOM version** before production deployment. In this authoring stage, code snippets are illustrative examples for learners to adapt; they **have not been verified via a build in a live repository**.

## 34. Summary

**Testing error flows and dead-letter handling** means testing a message's entire failure journey—not merely catching one exception or checking one log line. Spring Integration provides `ErrorMessage`, `errorChannel`, `MessagePublishingErrorHandler`, `RequestHandlerRetryAdvice`, `RecoveryCallback`, and `ErrorMessageSendingRecoverer` to build error paths; JMS/AMQP/Kafka and each inbound adapter add their own **transaction, acknowledgment, offset, redelivery, and dead-letter semantics**.

A trustworthy suite combines **unit tests of error contracts**, **flow tests of routing/retries**, **adapter integration tests against real brokers/servers**, and **failure-injection tests for crashes, archive failures, lost responses, and replays**. Consider a message safely handed off only when **a business outcome is evidenced, or the failure is durably persisted and the source ACKed per verified policy**. Paired with idempotency, reconciliation, observability, and runbooks, this testing approach ensures integration flows not only catch errors, but **never lose or duplicate business operations when failures strike**.
