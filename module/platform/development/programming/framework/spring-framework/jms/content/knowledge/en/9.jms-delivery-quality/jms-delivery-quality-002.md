# Guarantee Limits When Only Durable Storage Is Enabled

> **Topic:** Delivery quality in Spring Framework – JMS. Configuring `DeliveryMode.PERSISTENT` (persistent delivery) is an important part of reliability, **but it is not enough to guarantee "never lose a message under any circumstance", "never process a duplicate", or "update the database exactly once"**. This lesson clearly separates Jakarta Messaging guarantees, broker conditions, and application responsibilities, then walks through a Java 17/Spring Boot/ActiveMQ Artemis experiment so you can observe it firsthand.

## 1. Exact Definition: What Does "Enabling Durable Storage" Actually Turn On?

In Jakarta Messaging (JMS), a producer has two delivery modes:

| Mode | Standard Value | Meaning in JMS | Common Use Cases |
| --- | --- | --- | --- |
| `DeliveryMode.PERSISTENT` | `2` | Requests the JMS provider to use a sufficiently durable transmission/delivery method so the message is not lost merely due to **provider failure**, subject to destination, retention, and resource conditions | Critical commands, business events that must be processed |
| `DeliveryMode.NON_PERSISTENT` | `1` | Not required to be stored on stable storage; provider failure may cause message loss | Telemetry/signals that can be missed or regenerated |

`PERSISTENT` is **the default for a JMS producer**. It usually entails the broker writing the message to a journal or appropriate storage, but **it does not mean** the Java application has enabled durable persistence for its database, does not automatically configure replication, and does not prevent an administrator from deleting a queue.

The Jakarta Messaging 3.1 specification uses two concepts: `NON_PERSISTENT` provides **at-most-once delivery** within the JMS provider's scope, whereas `PERSISTENT` provides **once-and-only-once delivery** within the provider's scope, provided retention policies and resources meet the conditions. The specification also notes important limits: **messages may expire, be discarded under administrative policy, or be affected by resource limits**; redelivering a message due to session recovery **is not considered a duplicate message** under the specification's definition.

Therefore, saying "PERSISTENT guarantees exactly-once" is **too broad and misleading**. You must always state clearly: *exactly-once for which component, at which boundary, and for which outcome?*

## 2. Breaking It Down into Four Guarantee Boundaries

An order-sending flow typically has these steps:

~~~text
[1] Order Service Database
     INSERT order, COMMIT
            |
            v
[2] JMS Producer
     JmsTemplate.convertAndSend(...)
            |
            v
[3] JMS Broker / Queue
     receive, route, store message, deliver to consumer
            |
            v
[4] Consumer / Worker
     receive -> update database / call external API -> ACK or JMS COMMIT
~~~

At each boundary, `PERSISTENT` solves only **part** of the problem:

| Boundary | Risk | How Does PERSISTENT Help? | What Is Still Missing? |
| --- | --- | --- | --- |
| (1) Database → producer | DB commits, then app crashes before sending the event | Does not help: the message has not even been created/sent yet | Transactional outbox or a DB + message coordination mechanism |
| (2) Producer → broker | Network drops right during send; client does not know if the broker persisted it | Broker honors the persistent contract if it actually accepted/durably wrote it | Handling ambiguous outcomes, retries with a stable ID, preventing duplicate events |
| (3) Broker storage → consumer | Broker restarts while messages remain in the queue | Can recover durably stored messages, if destination, journal, and resources are right | Durable queue/subscription, persistence config, storage/HA, quota, TTL |
| (4) Consumer → database | DB commits successfully, client crashes before JMS ACK | Broker can redeliver un-acked/uncommitted messages | Idempotency or appropriate coordinated transactions |
| (4) Consumer ACK → side effect | Early ACK, worker crashes before finishing | Does not help; broker already considers the message handled | ACK/commit only after required processing, with transactions/retries |

**The right way to read it:** `PERSISTENT` is a **request regarding message quality of service within the JMS provider**, not a transaction spanning from the producer's database to the consumer's database.

## 3. What Does the JMS Guarantee Actually Say?

### 3.1. Scope of "Once-and-Only-Once"

Jakarta Messaging 3.1, sections *Message delivery mode* and *Reliability*, specifies that persistent messages must be protected by the provider against provider failures, subject to retention/resource caveats. A persistent message properly managed by the provider will not be arbitrarily lost or duplicated by the provider itself due to a broker failure.

However, there are at least **three distinct kinds of "duplicates"**:

1. **Provider-created duplicates due to failure**, the kind of duplication the JMS persistent contract aims to avoid within the stated scope.
2. **Redelivery after rollback/recover**, meaning the same logical message is delivered again when the prior processing attempt was not completed/acked per JMS; this is necessary behavior so the application gets a chance to reprocess, and JMS does not define it as an invalid duplicate.
3. **Producer emitting two equivalent business messages** because a `send`/`commit` call had an ambiguous outcome and was retried. To the JMS provider, these can be **two separate sends**, each honoring the delivery contract while the application receives two `order-paid` events with the same `orderId`.

Thus, even when the provider honors persistent delivery, the business system can still **observe repeated events or execute side effects multiple times** if idempotency is missing.

### 3.2. Destination Conditions

Sending a persistent message to a **durable queue** is the common scenario. For a **topic**, a subscriber that wants to receive messages published while it is offline must use a **durable subscription** with an appropriate subscription/client identifier; a **non-durable subscription** can miss messages when inactive, even if the publisher uses `PERSISTENT`.

With temporary destinations, do not treat persistent mode as a retention contract after the connection/destination is destroyed. A durable message **does not automatically turn** every queue or subscription into a durable object.

### 3.3. Limits Explicitly Stated by the Specification

- **Expiration/TTL:** a message whose `JMSExpiration` has elapsed may be discarded and not newly delivered. `PERSISTENT` does not override TTL.
- **Administrative deletion:** queue purges, deleting subscriptions/addresses, or administrative policies can remove messages.
- **Resource restrictions:** running out of disk space, queue quotas, capacity/flow control, or insufficient processing resources can break the assumption that "every message is kept".
- **Unresponsive clients:** when consumers cannot keep up, message backlog and latency grow; storing a message does not guarantee it is processed on time.
- **Provider implementation/configuration:** storage, sync, HA, paging, routing, and send acknowledgements must all be verified against the actual broker.

## 4. What Does a Successful Send Mean — and What Does It Not Mean?

Consider:

~~~java
// Snippet: jmsTemplate is a configured Spring bean.
jmsTemplate.convertAndSend("orders.queue", "order-created");
System.out.println("send returned");
~~~

If the call returns normally, the code has completed the send operation according to the current configuration of `JmsTemplate`, provider, and session. However:

- It **does not** guarantee a consumer has received the message.
- It **does not** guarantee a consumer has committed its database.
- It **does not** guarantee the destination/subscription has suitable retention.
- It **does not** by itself prove storage was fsynced or replicated to another site.
- If a transaction is open, the message may **not yet be visible** to consumers until the JMS transaction commits.
- If asynchronous sending or client settings that do not wait for full acknowledgement are used, when the method returns may differ from when the broker durably committed. You must understand the provider's acknowledgement policy.

Conversely, if `send` throws an exception due to a dropped connection, **you also cannot assume** the message never reached the broker. Jakarta Messaging explicitly describes the failure case occurring **after the broker receives/commits but before the client receives the response**. This is the *ambiguous outcome* problem.

### 4.1. Illustrating Disconnection at the Worst Moment

~~~text
Producer                              Broker
   |                                     |
   |---- SEND eventId=evt-001 ---------->|
   |                                     |-- Persist event
   |                [network breaks]     |
   X<--- ACK/response never arrives -----|
   |
   +-- Producer reports timeout/exception
   +-- Does not know whether the event already exists
   +-- Retries eventId=evt-001
                 |
                 +--> Broker may receive another send
~~~

If the producer generates a new `eventId` on every retry, the consumer has almost no way to tell two equivalent events apart. Using a **stable business ID** is a prerequisite for deduplication. Some providers, such as Artemis, have their own duplicate detection mechanism, but that is a feature **that must be properly configured/applied**, not something that appears automatically just by setting `PERSISTENT`.

### 4.2. Ambiguous Commit Outcomes

Similarly, when calling `Session.commit()`:
- If a successful commit notification arrives, there is ground to treat the JMS transaction as completed per the contract and configuration.
- If the client loses connectivity **between sending commit and receiving the response**, it is impossible to know for sure whether the broker committed or rolled back based solely on the exception.
- Retrying the entire business action without an event ID/idempotency can create business duplicates.

Suitable techniques depend on requirements: checking state by ID, transactional outbox for DB→message, consumer deduplication, and broker duplicate detection if supported.

## 5. Consumer: Persistent Does Not Replace ACK or Transactions

### 5.1. Why Receiving a Message Does Not Mean Processing Is Done

A consumer usually performs multiple steps:

~~~text
Broker -> Consumer.receive()
           |
           +--> Validate payload
           +--> Write data to DB
           +--> Call external service
           +--> Acknowledge or commit JMS
~~~

If the order of ACK and side effects is not managed carefully:

| Scenario | What Happens | Consequence |
| --- | --- | --- |
| Early ACK | Consumer acknowledges first, DB write second, then process crashes | Broker may not redeliver; DB work is lost |
| DB commit first, ACK later | DB write succeeds, process crashes before ACK | Broker may redeliver; DB side effect risks repeating |
| JMS transaction rollback | Listener fails before `commit()`, session rolls back | Message is incomplete and may be redelivered |
| Continuous redelivery | Poison payload or DB always failing, listener keeps rolling back | Backlog/retry storm; need DLQ and retry limits |
| AUTO_ACKNOWLEDGE in listener container | ACK semantics depend on container/provider and callback timing | Does not automatically guarantee "DB finished then ACK strictly after" |

Jakarta Messaging provides session transactions and acknowledge modes. Spring JMS provides listener containers with transaction configuration; **do not merely change the producer's delivery mode and consider consumer reliability solved**.

### 5.2. Local JMS Transaction and Its Scope

A consumer using plain Jakarta JMS can process inside a transacted session:

~~~java
// Snippet inside code that already has Connection, Queue, and consume permissions.
try (Session session = connection.createSession(Session.SESSION_TRANSACTED);
     MessageConsumer consumer = session.createConsumer(queue)) {

    connection.start();
    Message message = consumer.receive(5_000L);

    if (message != null) {
        try {
            // Perform processing that may throw an error.
            processMessage(message);
            session.commit();  // Commit the JMS local transaction.
        } catch (Exception ex) {
            session.rollback(); // Allow JMS recovery/redelivery.
            throw ex;
        }
    }
}
~~~

This snippet is **not standalone**: variables `connection`, `queue`, and method `processMessage` must exist in the application, along with `jakarta.jms.*` imports. Its purpose is to illustrate where `commit/rollback` are called. **A local JMS transaction does not automatically manage a database transaction**: if `processMessage` already committed the DB and then JMS `commit` fails, the message may be received again.

With Spring's `DefaultMessageListenerContainer`, set `sessionTransacted=true` to roll back JMS when the listener throws an exception. In environments with an external Spring transaction manager, you must examine interactions with the transaction manager, caching, session ownership, and how the listener container is configured.

### 5.3. Redelivery Is a Signal, Not a Deduplication ID

When the provider redelivers an incompletely processed message, the `JMSRedelivered` header is marked and the `JMSXDeliveryCount` property increases as required by the specification. These are useful for logging, tuning retries, and operations.

However, **do not** use `JMSRedelivered=false` to conclude "the side effect has never executed"; DB/JMS commit failures can occur outside what this flag captures. And `JMSMessageID` typically identifies **each JMS send**, not necessarily **one business operation across producer retries**. Use a separate stable `eventId` or `commandId`.

## 6. Practical Limits of Broker Storage and HA

A queue containing persistent messages can recover after a broker restart **only when the required configuration, data, and resources actually exist**. Do not equate a single delivery mode bit with the overall storage design.

### 6.1. With Apache ActiveMQ Artemis

Artemis supports a **file journal** or **JDBC store** for persistence; the default journal is append-only. Items to verify in real configurations:

| Config/Topic | Why It Matters |
| --- | --- |
| `persistence-enabled` | Whether the broker has durable persistence enabled |
| Durable queue / durable subscription | Whether messages are persisted and retained for the right destination/subscriber |
| `journal-sync-non-transactional` | For non-transactional sends/acks, whether the journal is synced before acknowledging per policy |
| `journal-sync-transactional` | For transactions, whether commit/rollback data is synced before responding |
| `journal-datasync` and journal type | Durability across process crashes vs. power failures; depends on filesystem/OS |
| Storage volume/replication/HA | Whether data remains accessible after container/host/disk failure |
| Address full policy, disk/memory limits, paging | How the broker behaves when resources run out or backlog grows large |
| Message expiry, dead-letter, purge policy | Reasons a message can be removed other than a broker crash |

Artemis's *Guarantees of Sends and Commits* documentation states: for a durable message on **at least one durable queue**, non-transactional send, and `journal-sync-non-transactional=true`, the broker acknowledges after persisting via the corresponding mechanism. The Core client's `blockOnDurableSend` setting determines whether to wait for a response on durable sends. Defaults and compatibility must be verified against the **version and client protocol** in use.

**This does not guarantee against every hardware failure:** if the volume is deleted, snapshots lack data, a controller/disk reports a write succeeded when it actually failed, replication is misconfigured, or HA failover is misconfigured, you cannot infer zero data loss from `PERSISTENT` alone.

### 6.2. Containers and Ephemeral Storage

A containerized broker **without a persistent volume attached** can lose its journal when the container is removed and recreated. That is different from restarting **the same broker instance on the same storage volume**. To test post-restart durability meaningfully:

1. Pick a test broker; verify persistence is enabled and the durable queue has been created.
2. Identify the **actual data path** and durable volume.
3. Send a persistent message, **do not receive/ACK it yet**.
4. Restart the broker per operational procedures; **do not delete the journal/volume**.
5. Reconnect and receive the message with the matching event ID.
6. Record the broker version, storage settings, results, and logs.

Do not run `docker rm`/delete volumes and expect messages to recover. Do not run destructive procedures against production queues.

### 6.3. Availability Is Not Durability

- **Durability:** committed data can be recovered according to the contract.
- **Availability:** the service can send/receive at the moment needed.
- **RPO:** the amount of data loss acceptable in a disaster/failover scenario.
- **RTO:** the time required to restore the service.
- **Correctness:** business processing without missing, duplicated, or corrupted data.

A single-node broker with durable disks can still be **unavailable for minutes or hours** after an outage. Conversely, a cluster coming back up quickly does not automatically prove RPO=0 if replication/ack policies are insufficient. Design HA, backups, recovery, and testing according to real risk.

## 7. Runnable Example: Persistent Send/Receive on Spring Boot

Uses **Java 17**, **Spring Boot 3.3.5**, **ActiveMQ Artemis client**, and `JmsTemplate`. The example splits execution into two modes, **send** and **receive**, so you can restart the broker between runs. It tests the JMS layer and **does not pretend to prove database exactly-once**.

**Prerequisites:** an Artemis broker at `tcp://localhost:61616`, credentials `demo/demo`, a **durable anycast** queue named `demo.durable` provisioned with send/consume permissions, broker persistence enabled, and data stored on a durable volume. If the broker allows auto-creating queues, still verify the created queue is **durable**. The `demo/demo` credentials are local examples only; do not use them in production. The demo does not provide destructive Docker commands because volume paths vary by image/installation.

### 7.1. Project Structure

~~~text
persistent-jms-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/demo/PersistentProbeApplication.java
    └── resources/application.yml
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'persistent-jms-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

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
}
~~~

`src/main/resources/application.yml`:

~~~yaml
spring:
  main:
    web-application-type: none
  artemis:
    mode: native
    broker-url: tcp://localhost:61616
    user: demo
    password: demo
~~~

In real environments, use `SPRING_ARTEMIS_USER`, `SPRING_ARTEMIS_PASSWORD`, and `SPRING_ARTEMIS_BROKER_URL` or secret management to replace demo values; never commit real passwords.

### 7.2. Standalone Java Program in the Project

`src/main/java/demo/PersistentProbeApplication.java`:

~~~java
package demo;

import java.util.List;
import java.util.UUID;

import jakarta.jms.DeliveryMode;
import jakarta.jms.Message;
import jakarta.jms.TextMessage;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
public class PersistentProbeApplication {

    private static final String QUEUE = "demo.durable";

    public static void main(String[] args) {
        SpringApplication.run(PersistentProbeApplication.class, args);
    }

    @Bean
    ApplicationRunner probe(JmsTemplate template) {
        return args -> {
            String mode = option(args, "probe.mode", "send");
            String eventId = option(
                    args, "probe.id", UUID.randomUUID().toString());

            // Safe ID for JMS selector and easy log correlation.
            if (!eventId.matches("[A-Za-z0-9._-]{1,80}")) {
                throw new IllegalArgumentException("Invalid probe.id");
            }

            if ("send".equals(mode)) {
                // Configure once for this single-threaded demo program.
                template.setExplicitQosEnabled(true);
                template.setDeliveryMode(DeliveryMode.PERSISTENT);
                template.setTimeToLive(0L); // Does not expire by TTL.

                template.convertAndSend(
                        QUEUE,
                        "event:" + eventId,
                        message -> {
                            message.setStringProperty("eventId", eventId);
                            return message;
                        });

                // Print after the send call returns normally.
                System.out.println("SEND_RETURNED eventId=" + eventId);
                return;
            }

            if ("receive".equals(mode)) {
                template.setReceiveTimeout(5_000L);
                String selector = "eventId = '" + eventId + "'";
                Message message = template.receiveSelected(QUEUE, selector);

                if (message == null) {
                    System.out.println(
                            "NO_MESSAGE_WITHIN_5000MS eventId=" + eventId);
                    return;
                }

                if (!(message instanceof TextMessage text)) {
                    throw new IllegalStateException(
                            "Expected TextMessage");
                }

                String expectedBody = "event:" + eventId;
                if (!expectedBody.equals(text.getText())) {
                    throw new IllegalStateException(
                            "Unexpected message body");
                }
                if (message.getJMSDeliveryMode()
                        != DeliveryMode.PERSISTENT) {
                    throw new IllegalStateException(
                            "Unexpected delivery mode");
                }

                System.out.println(
                        "RECEIVE_OK eventId=" + eventId
                        + " body=" + text.getText()
                        + " mode=PERSISTENT");
                return;
            }

            throw new IllegalArgumentException(
                    "probe.mode must be send or receive");
        };
    }

    private static String option(
            ApplicationArguments args,
            String name,
            String fallback) {
        List<String> values = args.getOptionValues(name);
        if (values == null || values.isEmpty()
                || values.get(0) == null
                || values.get(0).isBlank()) {
            return fallback;
        }
        return values.get(0);
    }
}
~~~

**Why is this a suitable example?**

1. `JmsTemplate` is auto-configured by Spring Boot from the Artemis `ConnectionFactory`, requiring no manual Session/Connection management.
2. `setExplicitQosEnabled(true)` forces the template to pass the configured QoS to the producer send; otherwise, `setDeliveryMode` on the template is not actively applied as intended.
3. `DeliveryMode.PERSISTENT` asks the provider to use persistent delivery; `timeToLive=0` means no expiration **by JMS TTL**, rather than disabling retention/quotas.
4. `eventId` is written as a message property and used in a consumer selector to receive the exact test message, avoiding picking up old messages by mistake.
5. `send` and `receive` are **two separate runs**, allowing you to restart the broker after sending without accidentally ACKing/consuming the message.
6. After `SEND_RETURNED`, the broker still might not have delivered the message to a consumer; the program intentionally does not claim "ORDER_PROCESSED".
7. `receiveSelected` is a synchronous receive approach for the demo; in real applications, use a listener with clearly designed transactions/acknowledgements.

In a single-threaded demo program, setters on `JmsTemplate` are set once and used. **Do not mutate delivery mode/priority/TTL on a singleton JmsTemplate per HTTP request** in concurrent applications; requests can interfere with each other's settings.

### 7.3. Running: Send First, Receive Later

From the project directory with JDK 17+, Gradle, and the broker ready:

~~~bash
gradle bootRun --args="--probe.mode=send --probe.id=evt-1001"
~~~

With a valid broker and send permission, the application prints:

~~~text
SEND_RETURNED eventId=evt-1001
~~~

Do not run the consumer yet if you want to test a restart. On the test broker, verify the `demo.durable` queue exists/is durable and the message is pending; then restart **the same instance, preserving the journal and volume** using your operational tools. Once the broker is ready:

~~~bash
gradle bootRun --args="--probe.mode=receive --probe.id=evt-1001"
~~~

If the message is still in the queue and the user has consume permission:

~~~text
RECEIVE_OK eventId=evt-1001 body=event:evt-1001 mode=PERSISTENT
~~~

Spring Boot/Artemis may print additional logs. If you only see `NO_MESSAGE_WITHIN_5000MS`, do not jump to concluding persistent "does not work": check queue durability, broker instance, journal volume, expiration, selector, credentials, competing consumers, whether the message was ACKed by another run, and administrative policies. If you run receive a second time with the same ID, the message may have been acknowledged/consumed on the first run, so timing out on the second run is normal behavior.

**Limits of this test:** it can show that a message survives a controlled restart. It **does not** simulate disk loss, crashes between journal write and response, network partitions, DB transactions, consumer rollbacks, or end-to-end exactly-once.

### 7.4. Control Tests: Where Is the Real Evidence?

| Experiment | How to Conduct | Maximum Conclusion |
| --- | --- | --- |
| Persistent, unreceived, restart keeping volume | Send `evt-1001`, restart broker, receive matching ID | Under test conditions, the broker recovers unconsumed messages |
| Send `NON_PERSISTENT` then restart | Change mode in a **separate test run** | Message may be lost; not guaranteed to be lost in every run |
| Send persistent then purge queue | Administrator purges the **test** queue | Persistent does not protect against administrative deletion |
| Send persistent with very short TTL | Set TTL before send, wait past expiry | Message may be removed due to expiration |
| Send to topic with no active durable subscriber | Publish first then register subscriber later | Persistent does not save missed messages for non-durable subscriptions |
| Crash consumer after DB commit, before JMS ACK | Separate integration test with DB/test queue | Redelivery can cause duplicate side effects if not idempotent |
| Crash producer after DB commit, before send | Separate integration test DB + outbox | Persistent cannot protect an event not yet published |
| Lose response after broker receives send | Inject failure in test environment | Producer must handle ambiguous outcomes; cannot infer from exception that the broker lacks the message |

Never test purges, volume deletion, or killing brokers in production. With non-persistent mode, a message **still remaining** after a restart **is not a bug**; the contract allows providers to store better than the minimum.

## 8. The DB → JMS Gap: Transactional Outbox

A typical scenario:

~~~text
BEGIN DB TRANSACTION
  UPDATE orders SET status='PAID'
COMMIT DB
      |
      X Process dies before jmsTemplate.convertAndSend(...)
      |
      +--> DB: PAID
      +--> Broker: NO event
~~~

`PERSISTENT` only applies **once the message is sent**; it cannot bridge the gap between DB commit and producer send.

### 8.1. Outbox Structure

A common solution is writing **business data and an outbox record in the same DB transaction**:

~~~sql
-- PostgreSQL example, illustrating a minimal schema.
CREATE TABLE outbox_event (
    event_id       VARCHAR(80) PRIMARY KEY,
    event_type     VARCHAR(100) NOT NULL,
    payload_json   TEXT NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at   TIMESTAMPTZ NULL
);
~~~

Write flow:

~~~text
Order Service / DB transaction
  |
  +-- UPDATE orders ...
  +-- INSERT outbox_event(event_id, event_type, payload_json)
  +-- COMMIT --> both order and outbox coexist
                    |
                    v
       Outbox relay (polling/CDC)
          |
          +-- Publish persistent JMS message, fixed eventId
          +-- Mark published_at after receiving a sufficiently reliable result
          +-- Retry on error or ambiguous state
                    |
                    v
             JMS broker / Queue
~~~

The relay may resend if the broker received the message but the relay died before marking it published. **Outbox does not by itself achieve exactly-once delivery**. It protects events from "DB committed but no record to send," in exchange requiring **at-least-once publishing + idempotent consumer** or an equivalent deduplication mechanism.

### 8.2. Details That Must Not Be Overlooked

- `event_id` is generated once per **logical business event**, not regenerated on every relay retry.
- Use appropriate locking, leases, or claim mechanisms so multiple relays do not unintentionally emit the same outbox event simultaneously.
- Do not mark outbox `published` **before** JMS send/commit succeeds at the chosen confirmation level.
- Configure retry/backoff limits, outbox retention, backlog alerts, and crash recovery when the relay dies.
- If payloads mutate after DB commit, the relay must read **the snapshot stored in the outbox** rather than inconsistently reconstructing it from the DB.
- When multiple brokers/destinations are needed, design per-target publish state or a reconciliation strategy.

Spring `@Transactional` on the DB does not automatically merge a JDBC transaction with JMS. Distributed transactions require XA/JTA infrastructure and proper configuration; many systems prefer outbox for operational simplicity, though the choice must weigh consistency requirements and platform constraints.

## 9. The JMS → DB Gap: Idempotent Consumer

Another failure window:

~~~text
Broker delivers eventId=evt-1001
  |
Consumer BEGIN DB
  |-- INSERT payment_transaction ...
  |-- COMMIT DB (succeeds)
  |
  X Consumer crashes / loses network before JMS ACK/COMMIT
  |
Broker sees incomplete message
  |-- Redelivers evt-1001
  |
Consumer runs again
  |-- Without deduplication: may produce side effects a second time
~~~

Common solution: store processed `eventId` values in **the same DB transaction as the side effect**. Illustrative PostgreSQL model:

~~~sql
CREATE TABLE processed_message (
    consumer_name VARCHAR(100) NOT NULL,
    event_id      VARCHAR(80) NOT NULL,
    processed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Standard pseudo-flow to implement in the service:

~~~text
When JMS listener receives an event:
    BEGIN DB TRANSACTION
        INSERT INTO processed_message(consumer_name, event_id)
        ON CONFLICT DO NOTHING

        If a new row was inserted:
            Execute business UPDATE/INSERT
        If eventId already exists:
            Skip side effects (treat as already processed)
    COMMIT DB
    Then complete JMS ACK / JMS COMMIT

If DB fails:
    ROLLBACK DB
    ROLLBACK or do not ACK JMS to allow redelivery
~~~

**Note:** the dedupe INSERT and the business update must be in **the same DB transaction**; if you only write a "processed" flag while the side effect runs outside the transaction, a crash can cause the message to be skipped even though the work never completed. For external API calls, consider receiver-side idempotency keys or a saga/state machine to prevent repeated side effects.

### 9.1. In a Spring JMS Listener

Spring supports listener containers with **local JMS transactions**, such as `sessionTransacted=true` on `DefaultJmsListenerContainerFactory`/container. If the listener method throws an exception, the JMS transaction can roll back and the message is redelivered per policy; however, **a Spring Data/JDBC DB transaction does not automatically sit inside that same JMS transaction**.

In applications using both JMS and a DB, define commit order, exception propagation, transaction managers, and handling of "DB committed, JMS commit unfinished." An idempotent consumer reduces the risk of duplicate side effects upon redelivery.

### 9.2. Do Not Treat Redelivery Flags as a Deduplication Mechanism

`JMSRedelivered` and `JMSXDeliveryCount` identify redelivery attempts of the same message, but are insufficient:
- A producer retry can create a **new message** carrying the exact same business event where both have `JMSRedelivered=false`.
- A message that already caused a side effect may be replayed after a timeout or rollback.
- Broker-specific properties and delivery counts do not replace a business `eventId` key.

The dedupe ID should belong to the **domain/event contract** and stay unchanged across producer retries.

## 10. Retry, DLQ, and Retention Need Their Own Strategy

Persistent messages **do not** solve poison messages (payloads that always fail the consumer). If a listener keeps rolling back, the broker may redeliver repeatedly:

~~~text
Queue
  |
  +--> Consumer receives -> error -> rollback
  |                       |
  +<----------------------+
  |
  +--> After N attempts per broker policy -> Dead Letter Queue
~~~

Configure at the broker level:
- Maximum redelivery attempts and delay/backoff to avoid tight loops.
- Appropriate dead-letter address/queue, access permissions, and alerts.
- Classification between transient errors (DB timeout) and permanent data errors (bad schema/payload).
- Safe reprocessing operations using a stable idempotency key.
- Clear limits on message age, queue size, disk capacity, and expiry policies.

**A DLQ is not infinite storage.** It also has TTL/quotas/cleanup; for long-term auditing, store business/reconciliation data in an appropriate system. A message in a DLQ does not mean it was processed successfully.

## 11. Why Might "PERSISTENT + TTL=0" Still Result in Not Seeing the Message?

Choosing `PERSISTENT`, TTL `0`, and seeing `send` succeed can still leave a consumer without the expected message due to:

| Cause | How to Verify |
| --- | --- |
| Sent to wrong destination or routing type | Check exact address/queue, anycast/multicast, and actual broker |
| Topic only has an offline non-durable subscriber | Check durable subscription and client/subscription identity |
| Broker policy deleted/purged or moved the message | Check audit logs, expiry address, DLQ, and retention policy |
| Another consumer already received/ACKed the message | Check consumer count, queue browse/metrics, and application logs |
| Selector does not match property/type | Check selector and properties written at send time |
| Producer send was inside an uncommitted transaction | Check transaction boundaries; commit succeeded before concluding |
| Broker storage was wiped/non-durable | Check volumes, journal, backups, logs, and restart procedure |
| Disk full/quota or flow-control | Check address full policy, paging, quota, and broker alerts |
| Receive timeout too short | Measure backlog/latency, check listener started status and consume permissions |
| Provider/broker failed after app reported OK under async config | Check send acknowledgement policy and journal sync |

A `receive(timeout)` returning `null` **is not** enough to conclude "JMS persistent failed." Only by knowing the exact message ID, broker/destination, journal state, consumer state, and send time can you analyze it properly.

## 12. End-to-End Reliability Design Checklist

Before claiming "events are never lost and never processed twice," make sure you can answer these questions:

### Producer
- [ ] Is the event generated before or after DB commit? Is there an **outbox** or another consistency mechanism?
- [ ] Does every event carry a stable `eventId` across retries?
- [ ] Has the producer chosen `PERSISTENT` and verified the actual mode?
- [ ] If using `JmsTemplate.setDeliveryMode(...)`, is `setExplicitQosEnabled(true)` enabled?
- [ ] Is the send synchronously acknowledged at the right level? On timeout, how are **ambiguous outcomes** handled?
- [ ] Are retry/backoff, rate limits, alerts, tracing, and post-restart recovery policies in place?

### Broker
- [ ] Is the destination a durable queue or an appropriate durable topic subscription?
- [ ] Is persistence truly enabled; have journal/JDBC store and fsync/sync configs been verified?
- [ ] Does storage use durable volumes/disks; are backups, recovery, and permissions operated safely?
- [ ] Are RPO/RTO and HA/failover measured in failure injection tests?
- [ ] Are disk quotas, address full policy, paging, TTL, retention, purge, and DLQ managed?
- [ ] Are queue depth, oldest message age, expired/removed count, and journal/disk health metrics collected?

### Consumer
- [ ] Are ACK/transactions used at the required reliability level instead of relying on persistent mode?
- [ ] Are the DB side effect and dedupe table committed atomically in the DB?
- [ ] Do consumer errors roll back/skip ACK appropriately; are exceptions propagated?
- [ ] Are duplicate business events identified by a stable `eventId`?
- [ ] Do retry/DLQ avoid infinite loops, include alerts, and support safe replay?
- [ ] Has crashing after DB commit but before JMS ACK/commit been tested?

### Operations
- [ ] Have broker restart test results **keeping the journal** been documented?
- [ ] Have both unreceived messages and in-flight messages during a consumer crash been tested?
- [ ] Are process crashes, power failures, disk loss, and site failures distinguished?
- [ ] Is there an end-to-end dashboard: outbox lag, send failure, queue age, redelivery, duplicate count, consumer lag, and DLQ?
- [ ] Does the operations team know when to reconcile or republish messages by event ID?

## 13. Self-Check Questions

1. Why does `DeliveryMode.PERSISTENT` not help when the database commit succeeds but the process dies before `convertAndSend` is called?
2. According to Jakarta Messaging, does once-and-only-once for persistent messages apply to **provider delivery** or to application database side effects?
3. Can two producer sends with the same `orderId` after a timeout create two valid messages? How does the consumer detect business duplicates?
4. Why can a persistent message still be discarded when TTL expires or an admin purges the queue?
5. Why can a non-durable topic subscription miss messages published in persistent mode while the subscriber is offline?
6. Why does a local JMS transaction not automatically protect a PostgreSQL transaction?
7. In the sequence "DB commit → crash → no JMS ACK yet," why can the broker redeliver and how do you prevent a second DB update?
8. How do `journal-sync-non-transactional`, `blockOnDurableSend`, and a persistent queue relate to certainty when `send` returns?
9. Is restarting a broker by deleting the container and volume a valid test for message recovery?
10. If a system must promise never to drop commands and never to execute an action twice, what components besides persistent mode must be designed?

**Takeaway:** `PERSISTENT` protects messages **within the JMS provider's delivery contract** under explicit conditions. It does not create a transaction spanning DB and broker, does not replace ACK/commit, does not resolve ambiguous send outcomes, and does not eliminate duplicate side effects. To achieve end-to-end reliability, combine **durable destinations + broker persistence/HA + send acknowledgements + transactions/ACK + stable event IDs + idempotency + outbox + retry/DLQ + observability** according to real risk.

## References

1. Jakarta Messaging 3.1 Specification — `7.7 Message delivery mode`, `9.1 Reliability`, and `6.2.9 Sessions/Commit`: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
2. Apache ActiveMQ Artemis — *Persistence* (journal, JDBC store, sync): https://artemis.apache.org/components/artemis/documentation/latest/persistence
3. Apache ActiveMQ Artemis — *Guarantees of Sends and Commits*: https://artemis.apache.org/components/artemis/documentation/latest/send-guarantees.html
4. Spring Framework — *Using Spring JMS* (JmsTemplate, transaction management): https://docs.spring.io/spring-framework/reference/integration/jms/using.html
5. Spring Framework — *Receiving a Message* (transacted listener containers): https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html
6. Spring Boot 3.3 — *JMS and ActiveMQ Artemis*: https://docs.spring.io/spring-boot/3.3/reference/messaging/jms.html
