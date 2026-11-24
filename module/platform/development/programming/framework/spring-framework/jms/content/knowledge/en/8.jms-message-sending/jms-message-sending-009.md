# Send-Time Exceptions and Limits on Inferring Broker Outcomes in Spring JMS

## 1. Lesson Objectives

When an application calls `JmsTemplate.send(...)` or `convertAndSend(...)`, a message is constructed in the JVM and handed to the JMS provider to send to a Queue or Topic. The call may return normally, throw an exception before the provider sends, or fail when the broker may already have accepted the message while the client never received the response.

For critical events such as order creation, payments, or inventory updates, this boundary must be understood accurately: **an exception does not prove the message never reached the broker**, and **a normal return from `send` does not prove a consumer processed it successfully**.

~~~text
Producer application         JMS client/broker             Consumer
        |                            |                         |
        |---- convertAndSend() ----->|                         |
        |                            |--- route/store -------->|
        |<--- return/exception ------|                         |
        |                            |                         |--- process
        |                            |                         |--- ACK/commit
        |                            |                         |
        v                            v                         v
   Call outcome                Broker state            Business outcome
~~~

After this lesson, you will be able to:

- Recognize Jakarta Messaging's `JMSException` and Spring's `JmsException`.
- Distinguish failures **before the send operation**, failures **during sending**, and failures **during commit**.
- Interpret accurately what a normal return from `convertAndSend` means and what remains unguaranteed.
- Understand the *outcome unknown* window during timeouts, connection resets, broker failovers, or lost send ACKs.
- Design retries with stable event IDs, idempotent consumers, and a transactional outbox when needed.
- Know what to test with mocks and what requires integration tests with a real broker.

## 2. Two Exception Hierarchies: Jakarta Messaging and Spring

### 2.1. Jakarta JMS: Checked JMSException

At the low-level API, `jakarta.jms.MessageProducer.send(...)` declares `throws JMSException`. Common subclasses:

| Jakarta JMS exception | Typical meaning |
| --- | --- |
| `JMSSecurityException` | JMS authentication or authorization failed |
| `InvalidDestinationException` | Destination is invalid for the provider |
| `MessageFormatException` | Incompatible message type or format |
| `ResourceAllocationException` | Broker or provider lacks resources |
| `TransactionRolledBackException` | Transaction was rolled back |
| `JMSException` | General or unclassified provider error |

`JMSException.getErrorCode()` can carry a provider-defined error code, and `getLinkedException()` may hold the low-level cause. Do not build a cross-broker retry policy solely around a single vendor's error code string.

### 2.2. Spring JMS: Runtime JmsException

`JmsTemplate` manages connections/sessions/producers and translates checked `JMSException` into runtime exceptions under `org.springframework.jms.JmsException`. Examples in Spring include `JmsSecurityException`, `InvalidDestinationException`, `ResourceAllocationException`, and `UncategorizedJmsException`. Message conversion or destination resolution errors can also arise in the Spring layer before any send operation occurs.

Usage example:

~~~java
// Snippet inside a method with an existing JmsOperations operations:
try {
    operations.convertAndSend("orders.events", "ORDER_CREATED:O-42");
} catch (org.springframework.jms.JmsException failure) {
    String errorCode = failure.getErrorCode();
    Throwable root = failure.getMostSpecificCause();
    // Log appropriately; retain eventId for retry/reconciliation.
    throw failure;
}
~~~

`JmsOperations` is the interface; `JmsTemplate` is the standard implementation. When calling the Spring API, application code typically catches `JmsException` rather than checked `JMSException`.

**Note:** not every exception thrown during `convertAndSend` is a `JmsException`. Custom validation or callbacks can throw `IllegalArgumentException` or other runtime exceptions. Handling must consider **where the error occurred** and each method's contract—never write `catch (RuntimeException)` and assume the broker definitely did not receive the message.

## 3. Distinct Milestones Within a Single Send

A send lifecycle spans these responsibilities:

~~~text
[1] Application validates eventId and body
       |
[2] Spring/JMS builds message, converts, and adds metadata
       |
[3] Provider executes send over connection/session
       |
[4] Broker receives, routes, stores per policy
       |
[5] Transaction commit (if any)
       |
[6] Consumer receives and runs handler
       |
[7] Business processing commits and JMS ACK/commit
~~~

This is a **responsibility boundary diagram**, not an absolute call sequence for every implementation: a session may be acquired before conversion; in an outer transaction, commit may happen after the send method returns.

| Observation | What can be asserted | What must NOT be inferred |
| --- | --- | --- |
| Validation rejects before JMS call | This attempt never entered the send call | No other attempt existed for the same event |
| Converter proved to fail before producer send | This attempt did not reach the send layer | The broker never had this event |
| Exception because connection could not open | Current connection attempt failed | No event arrived from an earlier attempt |
| Timeout/reset during send/commit | Broker-side outcome may be unknown | "Definitely never sent" |
| `convertAndSend` returns normally | Send method completed per client/provider contract | Consumer received or processed it |
| Queue depth equals 0 | No backlog at the moment metric was sampled | Message never entered the Queue |
| Listener logged "received" | Handler reached that log line | DB and ACK committed |
| Evidence of consumer DB commit | DB side effect committed | Broker will never redeliver |

## 4. Why Can a Send Timeout Leave an Unknown Outcome?

Suppose the broker persisted the message, but the response was lost on the network:

~~~text
Producer                         Broker
  |                                 |
  |----- SEND eventId=evt-42 ------>|
  |                                 |-- may already be stored/accepted
  |<---------- ACK --X--------------|
  |                                 |
  +-- connection reset / timeout
  +-- client cannot be sure whether broker received it
~~~

From the producer's vantage point, two different histories look identical as a timeout:

- **Scenario A:** the request never reached the broker; the message was not accepted.
- **Scenario B:** the broker accepted the message, but the response was lost; the message may already be queued for a consumer.

Retrying with a brand-new message ID in Scenario B can produce **two copies of the same business event**. Not retrying in Scenario A can drop the event. Therefore, retry policies must rely on a **stable event ID** and a consumer capable of preventing duplicate processing.

Per Jakarta Messaging, when an **asynchronous send** with `CompletionListener` fails via call or callback, whether the send succeeded may be **indeterminate**. For synchronous sends, the confirmation level from `send` depends on the API contract and how the provider acknowledges under the configured delivery mode/QoS; there is no single universal guarantee across all network failures.

**Do not confuse Jakarta JMS asynchronous send** with calling `JmsTemplate` on another thread via `@Async`. Another thread does not turn a synchronous `convertAndSend` call into a new kind of broker confirmation.

## 5. What Does a Normal Return from Send Tell Us?

Consider:

~~~java
operations.convertAndSend("orders.events", payload);
System.out.println("SEND_METHOD_RETURNED");
~~~

Once that line prints, you can state that **the `convertAndSend` call returned normally in the JVM**. That does not prove:

1. A consumer is running or has received the message.
2. A consumer validated, wrote to its DB, or finished side effects.
3. An outer session transaction has committed.
4. The message will not expire via TTL or land in a DLQ.
5. An offline non-durable Topic subscriber had backlog buffered for it.
6. The broker can survive every failure without verifying persistence/HA configuration.
7. No duplicate message already exists from an earlier retry.

In operations, name logs accurately by evidence level: `SEND_METHOD_RETURNED`, `BROKER_CONFIRMED` (only when corresponding provider proof exists), `CONSUMER_RECEIVED`, `BUSINESS_COMMITTED`, and `JMS_ACK_COMMITTED`. Never log `ORDER_PROCESSED` immediately after sending.

### 5.1. How QoS and Persistence Affect Conclusions

JMS defines `DeliveryMode.PERSISTENT` and `NON_PERSISTENT`. Persistent requests stronger durability per standard/configuration, yet you must inspect broker journaling, HA, and commit behavior before claiming "fsynced to every node". Non-persistent may trade guarantees for lower latency. Neither **by itself** confirms consumer processing.

To ensure the template actually sends with application-configured QoS, enable `setExplicitQosEnabled(true)`:

~~~java
// Snippet configuring a JmsTemplate before shared use:
template.setExplicitQosEnabled(true);
template.setDeliveryPersistent(true);
template.setPriority(4);
template.setTimeToLive(60_000L);
~~~

A 60-second TTL means the message may expire before a consumer receives it. Do not call `setJMSExpiration` directly assuming it sets TTL before sending; use producer/template options.

### 5.2. Transactions Shift Confirmation Boundaries

When sending inside a JMS transaction, a `send` call can finish before the enclosing transaction commits. If a rollback occurs afterward, the message will not be delivered as a committed transaction.

~~~text
begin transaction
  send E42  -> method returns
  send E43  -> method returns
  commit    -> connection lost right at commit
~~~

When connectivity drops during `commit`, the commit outcome may be unknown. With an externally managed framework/JTA transaction, `publish()` may return **before** the transaction commit point.

A standard database `@Transactional` annotation does not mean JDBC/JPA and JMS automatically share an XA transaction. If DB + messaging consistency is needed, design an outbox or a genuine coordinated transaction manager within your environment's constraints.

## 6. Spring Boot 3.3 / Java 17 Example: Never Label Failure as "Unsent"

The following sample uses **ActiveMQ Artemis** and `JmsOperations` (implemented by `JmsTemplate`). It distinguishes pre-JMS validation errors from JMS errors with uncertain outcomes. Messages carry a stable `eventId` to support deduplication.

### 6.1. Start Local Artemis

With Docker:

~~~bash
docker run --detach --rm --name artemis-send-check -p 127.0.0.1:61616:61616 -p 127.0.0.1:8161:8161 -e ARTEMIS_USER=demo -e ARTEMIS_PASSWORD=demo apache/artemis:latest
~~~

Wait for the broker to be ready and check `docker logs artemis-send-check`. The `demo` account is for testing only; in production, use secrets and least-privilege ACLs. If the broker disallows auto-creating Queues, pre-create `orders.events` and grant send/consume permissions.

### 6.2. Project Structure

~~~text
spring-jms-send-outcome/
  settings.gradle
  build.gradle
  src/main/resources/application.properties
  src/main/java/demo/jms/
    SendOutcomeApplication.java
    OrderEventPublisher.java
    SendUnconfirmedException.java
    OrderEventListener.java
  src/test/java/demo/jms/
    OrderEventPublisherTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'spring-jms-send-outcome'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-artemis'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`src/main/resources/application.properties`:

~~~properties
spring.main.web-application-type=none
spring.artemis.mode=native
spring.artemis.broker-url=${JMS_BROKER_URL:tcp://localhost:61616}
spring.artemis.user=${JMS_BROKER_USER:demo}
spring.artemis.password=${JMS_BROKER_PASSWORD:demo}
spring.jms.pub-sub-domain=false
app.jms.orders-destination=orders.events
~~~

The placeholders above use standard Spring syntax (e.g., `$` + `{JMS_BROKER_URL:tcp://localhost:61616}`). In production, remove default credentials and inject secrets. The project uses Spring Boot 3.3.0 as an illustrative baseline; real products should pick a currently supported maintenance/security release.

### 6.3. Entry Point

`src/main/java/demo/jms/SendOutcomeApplication.java`:

~~~java
package demo.jms;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;

@SpringBootApplication
@EnableJms
public class SendOutcomeApplication {

    public static void main(String[] args) {
        SpringApplication.run(SendOutcomeApplication.class, args);
    }

    @Bean
    CommandLineRunner sendOnce(OrderEventPublisher publisher) {
        return args -> {
            publisher.publish("evt-order-42",
                    "{\"orderId\":\"O-42\",\"status\":\"created\"}");
            System.out.println("SEND_METHOD_RETURNED eventId=evt-order-42");
        };
    }
}
~~~

`CommandLineRunner` merely simulates a single send at startup. Re-running the app republishes an event with the same event ID. In production, events should be emitted when real business transitions occur or from an outbox table.

### 6.4. Publisher and Exception Expressing Observation Limits Accurately

`src/main/java/demo/jms/OrderEventPublisher.java`:

~~~java
package demo.jms;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.jms.JmsException;
import org.springframework.jms.core.JmsOperations;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private final JmsOperations operations;
    private final String destination;

    public OrderEventPublisher(
            JmsOperations operations,
            @Value("${app.jms.orders-destination}") String destination) {
        this.operations = operations;
        this.destination = destination;
    }

    public void publish(String eventId, String jsonBody) {
        if (eventId == null || eventId.isBlank()) {
            throw new IllegalArgumentException("eventId must not be blank");
        }
        if (jsonBody == null || jsonBody.isBlank()) {
            throw new IllegalArgumentException("body must not be blank");
        }

        try {
            operations.convertAndSend(destination, jsonBody, message -> {
                message.setStringProperty("eventId", eventId);
                message.setJMSType("order.created.v1");
                return message;
            });
        } catch (JmsException failure) {
            throw new SendUnconfirmedException(eventId, failure);
        }
    }
}
~~~

- Validation happens before calling JMS. If `eventId` or `body` is blank, **this attempt** never invokes `JmsOperations`.
- `convertAndSend` converts the `String` into a `TextMessage` via Spring's default converter.
- `MessagePostProcessor` sets business `eventId` as a property and `JMSType` as a header before sending.
- `catch (JmsException)` does not assert the broker never received the message. It wraps the failure so callers know the send outcome **could not be confirmed by the application**.
- `JmsTemplate` can be shared after configuration; application services must not mutate broker URLs, transactions, or template setters per event.

`src/main/java/demo/jms/SendUnconfirmedException.java`:

~~~java
package demo.jms;

public final class SendUnconfirmedException extends RuntimeException {

    private final String eventId;

    public SendUnconfirmedException(String eventId, Throwable cause) {
        super("JMS send unconfirmed for eventId=" + eventId, cause);
        this.eventId = eventId;
    }

    public String eventId() {
        return eventId;
    }
}
~~~

Never swallow `SendUnconfirmedException` and report business success. The caller must retain the event for retry, record an `UNKNOWN` state, and/or return an API-contract-appropriate response. Do not change the event ID when retrying.

### 6.5. Listener Demonstrating Receipt Does Not Equal Completion

`src/main/java/demo/jms/OrderEventListener.java`:

~~~java
package demo.jms;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderEventListener {

    @JmsListener(destination = "${app.jms.orders-destination}")
    public void onMessage(String jsonBody) {
        System.out.println("CONSUMER_HANDLER_ENTERED body=" + jsonBody);
    }
}
~~~

The log line only proves the handler method executed up to that statement; this illustrative app does not write to a DB or enforce idempotency. The Spring listener container handles ACK/transactions per configuration, so never name this log `BUSINESS_COMMITTED`.

### 6.6. Run

~~~bash
gradle test
gradle bootRun
~~~

If connection, credentials, Queue, and listener are valid, the console may show:

~~~text
SEND_METHOD_RETURNED eventId=evt-order-42
CONSUMER_HANDLER_ENTERED body={"orderId":"O-42","status":"created"}
~~~

The two lines **may appear in either order** since the listener runs on its own thread; Spring and broker logs will also interleave. If connecting fails, `convertAndSend` may throw an exception, and `SEND_METHOD_RETURNED` will not print.

To stop the local broker:

~~~bash
docker stop artemis-send-check
~~~

## 7. Unit Tests: Proving Interface Calls, Not Broker Outcomes

Mockito only checks interactions inside the JVM. That is an intentional limit of unit tests; proving real send behavior requires a broker in integration tests.

`src/test/java/demo/jms/OrderEventPublisherTest.java`:

~~~java
package demo.jms;

import jakarta.jms.JMSException;
import jakarta.jms.Message;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.jms.UncategorizedJmsException;
import org.springframework.jms.core.JmsOperations;
import org.springframework.jms.core.MessagePostProcessor;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;

class OrderEventPublisherTest {

    @Test
    void sendsCorrectDestinationAndBusinessEventId()
            throws JMSException {
        JmsOperations operations = mock(JmsOperations.class);
        var publisher = new OrderEventPublisher(operations, "orders.events");

        String body = "{\"orderId\":\"O-42\"}";
        publisher.publish("evt-42", body);

        ArgumentCaptor<MessagePostProcessor> post =
                ArgumentCaptor.forClass(MessagePostProcessor.class);

        verify(operations).convertAndSend(
                eq("orders.events"), eq(body), post.capture());

        Message message = mock(Message.class);
        assertSame(message, post.getValue().postProcessMessage(message));
        verify(message).setStringProperty("eventId", "evt-42");
        verify(message).setJMSType("order.created.v1");
    }

    @Test
    void rejectsInvalidInputBeforeJms() {
        JmsOperations operations = mock(JmsOperations.class);
        var publisher = new OrderEventPublisher(operations, "orders.events");

        assertThrows(IllegalArgumentException.class,
                () -> publisher.publish("  ", "{}"));
        verifyNoInteractions(operations);
    }

    @Test
    void reportsJmsFailureAsUnconfirmed() {
        JmsOperations operations = mock(JmsOperations.class);
        var publisher = new OrderEventPublisher(operations, "orders.events");

        doThrow(new UncategorizedJmsException(
                new JMSException("simulated transport error")))
                .when(operations)
                .convertAndSend(
                    eq("orders.events"), eq("{}"),
                    any(MessagePostProcessor.class));

        SendUnconfirmedException error =
                assertThrows(SendUnconfirmedException.class,
                        () -> publisher.publish("evt-42", "{}"));

        assertEquals("evt-42", error.eventId());
        verify(operations).convertAndSend(
                eq("orders.events"), eq("{}"),
                any(MessagePostProcessor.class));
    }
}
~~~

These three tests check payload/destination/properties, pre-JMS validation, and ensuring the application does not mislabel JMS failures as "definitely unsent". They do not simulate transaction commits, broker journals, or lost acknowledgements. Test with a real broker and controlled fault injection to verify those scenarios.

## 8. Retrying Safely Under Unknown Outcomes

### 8.1. Never Change the Business Event ID on Retry

~~~text
Attempt 1: eventId=evt-order-42 -> timeout; may have reached broker
Attempt 2: eventId=evt-order-42 -> send returns normally

If broker received both:
  Consumer sees two JMS messages with the same business eventId.
  Consumer must guard so side effects commit only once.
~~~

`JMSMessageID` is the transport ID of a single JMS message, normally assigned by the provider. A **republish** of the same business event may receive a different `JMSMessageID`, so never substitute it for a stable business event ID.

### 8.2. Which Errors Should Be Retried?

- **Permanent errors:** validation/schema failure, unauthorized destination, wrong username/password. Fix the contract/config; tight retries will not help.
- **Transient errors:** broker restart, connection reset, temporary quota exhaustion, timeouts. Retry with exponential backoff, bounded attempts, alerts, and DLQ/reconciliation.
- **Unknown-outcome errors:** uncertain whether the broker accepted the message. Retry with **the same `eventId`**, accept duplicates, and design idempotent consumers.

A sound retry policy accounts for provider, exception type, failure point, and business SLA. No single `catch (JmsException) { retry(); }` fits every system.

### 8.3. Idempotent Consumer

Logic pattern (pseudocode, not standalone SQL for every DB):

~~~text
BEGIN DB TRANSACTION
  INSERT processed_events(event_id='evt-order-42') if not yet present

  If event_id already exists:
      skip duplicate side effect
  If newly inserted:
      update order / inventory / ledger

COMMIT DB TRANSACTION
JMS ACK or commit per listener policy
~~~

Recording the **processed event marker** and applying the **business update** must share the same DB transaction. If the DB commits while the JMS ACK fails to reach the broker, the message may be redelivered; the consumer sees `eventId` already processed and skips applying the side effect a second time.

If the side effect is an email or external API call, add an idempotency mechanism for that external side effect as well. An in-memory `HashSet` loses all state upon restart.

## 9. Transactional Outbox When DB and JMS Must Agree

If an application executes:

~~~text
COMMIT database order O-42
SEND JMS event evt-order-42
~~~

and crashes in between, the DB holds the order while the broker may lack the event. Conversely, sending JMS before committing the DB risks the broker receiving an event for a rolled-back order.

**Transactional outbox** persists the event inside the **same DB transaction** as the business state:

~~~text
BEGIN DB TRANSACTION
  INSERT/UPDATE orders(...)
  INSERT outbox(event_id, payload, state='PENDING')
COMMIT DB TRANSACTION

Outbox worker:
  read PENDING rows
  send JMS carrying the same event_id
  if send returns, update sent status
  if error/unknown, keep for retry with backoff
~~~

An outbox ensures the event survives process crashes in the DB. However, if the broker accepted the JMS message and the outbox worker crashes **before marking it sent**, the worker will resend it. Thus an outbox provides **at-least-once publication** paired with an idempotent consumer; it does not magically deliver system-wide exactly-once semantics.

A `@Transactional` wrapping only JPA/JDBC does not automatically enlist JMS into an XA transaction. Achieving atomic commit across two resource systems requires a properly designed and configured transaction mechanism; for many services, outbox + idempotency is easier to operate.

## 10. Diagnosing Failures with Proper Traces

For each event ID, log safely:

| Field | Role |
| --- | --- |
| `eventId` | Correlates attempts of the same business event |
| `destination` | Target Queue/Topic |
| `attempt` | Attempt sequence number |
| `startedAt` / latency | Tracks timeouts and latency |
| `status` | `SEND_RETURNED` or `UNCONFIRMED` per evidence level |
| Exception class/root cause | Distinguishes converter/auth/network/transaction errors |
| Provider error code | Aids vendor-specific diagnostics |
| Transaction/correlation ID | Correlates cross-process traces |

Never log passwords, secrets, sensitive payloads, or headers containing tokens. Never log `ORDER_COMPLETED` in the publisher without proof the consumer finished.

On the broker side, monitor connection failures, enqueue/dequeue counts, Queue depth, expired messages, DLQ, redeliveries, transaction outcomes, durable backlog, persistence, and HA. Still, **aggregate metrics** cannot prove the status of a specific `eventId` without proper correlation.

## 11. Experiments Worth Running

1. **Pre-send validation failure:** call publisher with `eventId=" "`; unit test verifies `JmsOperations` is never called.
2. **Broker stopped before send:** run the app while Artemis is down; observe connection cause and wrapper exception. Do not confuse this with losing an ACK after sending.
3. **Wrong credentials:** alter password; distinguish authentication failures from network timeouts. Never retry infinitely with bad secrets.
4. **Stop consumer, keep broker running:** send to a valid Queue; send can return normally while no consumer processes it. Observe the backlog.
5. **Drop connection mid-send:** in a test environment with a fault proxy, sever the network during send; keep the same `eventId` on retry and check for duplicates at broker/consumer.
6. **Crash outbox worker after send:** let the worker send successfully without marking sent; restart and verify the idempotent consumer does not apply business logic twice.
7. **Short TTL:** send a message with a few seconds' TTL while no consumer runs, wait for expiration, then start the consumer; distinguish expiration from send exceptions.

To keep experiments reproducible, record broker/client versions, Queue/Topic mode, QoS/TTL, transaction boundaries, retry counts, failure injection timing, and producer/consumer timestamps. Never run fault injection on production systems.

## 12. Common False Conclusions

| False conclusion | What to remember |
| --- | --- |
| "Send threw no error, so the consumer processed it" | Sender and consumer have separate ACK/commit steps |
| "A JmsException means it definitely wasn't sent" | Send/commit failures can leave outcomes unknown |
| "Use a new event ID per retry to avoid duplicates" | Keep the same business event ID for deduplication |
| "JMSMessageID solves all duplicates automatically" | Republishes can get different JMSMessageIDs |
| "PERSISTENT means exactly-once" | Persistence and idempotency are separate concerns |
| "Queue depth 0 proves nothing was sent" | A consumer may have consumed it immediately or it expired |
| "Listener logged received, so DB committed" | Handler may fail after logging |
| "DB @Transactional automatically covers JMS" | Without coordinated transactions, it is not atomic |
| "Outbox guarantees never sending duplicates" | Crashing after send before outbox update causes retries |
| "Async callback onException proves unsent" | Per JMS, failure states can leave send status indeterminate |

## 13. Self-Assessment Questions

**1.** `convertAndSend` returns normally while the consumer is not running. Is the send considered a failure?

Not necessarily. Sending completed per the producer contract; downstream processing is a separate stage.

**2.** A timeout happens right after the broker may have persisted the message. Can you conclude the message was not sent?

No. This may be an **outcome unknown**; retries must preserve `eventId` and guard against duplicates.

**3.** When can you be sure an attempt never called JMS?

When validation/conversion is proven to have failed prior to the send operation and no other send path ran in that attempt.

**4.** Does a `PERSISTENT` message guarantee the consumer processes it exactly once?

No. Delivery, redelivery, ACK, DB commit, and idempotency all still need handling.

**5.** Why is `JMSMessageID` insufficient for deduplication when a producer resends?

A republish may receive a new message ID even for the same business event. Use a stable business `eventId`.

**6.** Under what scenario can an outbox produce duplicates?

When the broker accepted the message, but the outbox worker crashed before marking the event sent; the worker retries afterward.

**7.** Do Mockito unit tests prove the broker received a message?

No. They only verify the application invokes the right contract; real broker tests are required.

## 14. Official References

- Jakarta Messaging 3.1 Specification (send, transactions, and error handling): https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
- Jakarta Messaging 3.1 `MessageProducer` API (synchronous and asynchronous send): https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/messageproducer
- Spring Framework 6.1 `JmsTemplate` API: https://docs.spring.io/spring-framework/docs/6.1.1/javadoc-api/org/springframework/jms/core/JmsTemplate.html
- Spring Framework `JmsException` API: https://docs.spring.io/spring-framework/docs/6.1.8/javadoc-api/org/springframework/jms/JmsException.html
- Spring Framework — Using Spring JMS: https://docs.spring.io/spring-framework/reference/integration/jms/using.html
- Spring Boot 3.3 — JMS and Artemis: https://docs.spring.io/spring-boot/3.3/reference/messaging/jms.html
- Apache Artemis — Broker persistence: https://artemis.apache.org/components/artemis/documentation/latest/persistence.html

**Remember:** `JmsException` signals that an operation failed **from the client's perspective**. Without strong evidence proving whether the broker accepted or rejected it, treat the state as **unconfirmed**. Resilient systems handle that ambiguity with stable `eventId`s, bounded retries, idempotent consumers, and an outbox when synchronizing with a DB.
