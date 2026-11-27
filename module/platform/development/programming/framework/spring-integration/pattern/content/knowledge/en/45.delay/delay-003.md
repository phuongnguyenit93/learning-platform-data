# Delay groups and message identity in Spring Integration

## 1. The problem: how are multiple pending messages managed?

Suppose an e-commerce system receives these events:

- `reminder-101`: wait 30 seconds, then remind the customer to pay for order `order-101`.
- `reminder-102`: wait 30 seconds, then remind the customer to pay for order `order-102`.
- `fraud-101`: wait 5 seconds, then forward the risk alert for `order-101` to the risk control department.

The two payment reminder events pass through the same **Delayer** and are held in the same **delay group** for that endpoint. The risk alert passes through a different Delayer, with its own group. Each message still has its own identity for tracking and deduplication. Events belonging to the same order also need a business correlation key to trace across branches.

This is a key part of the **SPRING_INTEGRATION_PATTERN** module: implementing Enterprise Integration Patterns (EIP) with Spring Integration to connect Routers, Filters, Transformers, Splitters, Aggregators, Gateways, and retry/error channel branches in a loosely coupled, observable, and extensible way.

The goal of this lesson is to clearly distinguish:

1. **Delay group**: the set of pending messages managed by a Delayer in a `MessageGroupStore`.
2. **Message identity**: the identifier of a `Message` object, represented by the `MessageHeaders.ID` header.
3. **Correlation identity**: a key linking multiple messages belonging to the same transaction or process.
4. **Business identity/idempotency key**: the stable identifier of a business event across transformations, retries, and redeliveries.

~~~mermaid
flowchart TB
    P[Producer: events] --> R{Route by type}
    R -->|Payment reminder| D1["Delayer A<br/>messageGroupId=payment.reminders.v1"]
    R -->|Fraud alert| D2["Delayer B<br/>messageGroupId=fraud.alerts.v1"]
    D1 --> S[(MessageGroupStore)]
    D2 --> S
    S -. "Two independent groups" .-> X[Pending message store]
    D1 --> C1[Payment reminder consumer]
    D2 --> C2[Risk control consumer]
~~~

> **Common misconception:** a delay group does *not* correspond to a single customer or order, unless you intentionally design dedicated Delayers that way. In typical Java DSL configuration, `messageGroupId` is **a fixed string per Delayer**, used as the key to manage that endpoint's message group in the store.

## 2. Four types of IDs to distinguish

| Concept | Example | Who creates / manages it? | What is it used for? |
| --- | --- | --- | --- |
| Delayer's `messageGroupId` | `payment.reminders.delay.v1` | Endpoint configuration | Locate the Delayer's pending message group in `MessageGroupStore`, especially on restart |
| `MessageHeaders.ID` | Spring-generated UUID | Framework when creating a message | Identify a Spring **message instance** |
| `correlationId` | `order-101` | Integration flow or framework depending on EIP | Relate messages of the same business flow across Splitter/Aggregator, Router, and logging |
| `eventId` / `idempotencyKey` | `reminder-101` | Producer/business system | Identify the logical event, detect duplicate processing across retries, restarts, or redeliveries |

For example, two different events for the same order:

| Attribute | Message A | Message B |
| --- | --- | --- |
| `eventId` | `reminder-101-first` | `reminder-101-final` |
| `correlationId` | `order-101` | `order-101` |
| `MessageHeaders.ID` | UUID A | UUID B |
| Receiving Delayer | Payment Reminder Delayer | Payment Reminder Delayer |
| `messageGroupId` | `payment.reminders.delay.v1` | `payment.reminders.delay.v1` |

Thus, **two messages with different IDs can still belong to the same delay group**; and **two messages with the same correlationId do not necessarily sit in the same group** if they are routed through two different Delayers.

### Is `MessageHeaders.ID` stable throughout the flow?

Do not treat the `id` header as a permanent business key. Spring generates `MessageHeaders.ID` (usually a UUID) when constructing a message. When a step builds a **new message** after transforming the payload or headers, the ID may change. That change is expected because it is the identifier of the message object, not the immutable identifier of the real-world event.

`MessageHeaders.ID` and `MessageHeaders.TIMESTAMP` are read-only headers; do not use `MessageBuilder.setHeader("id", ...)` to force them into a business key. If you need a stable key, set a dedicated header such as `eventId` generated and managed by your system.

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<String> first = MessageBuilder.withPayload("raw-order")
        .setHeader("eventId", "evt-101")
        .setHeader("correlationId", "order-101")
        .build();

Message<String> transformed = MessageBuilder.fromMessage(first)
        .setPayload("normalized-order")
        .build();

// When building a new message, the system ID may change.
System.out.println(first.getHeaders().getId());
System.out.println(transformed.getHeaders().getId());

// eventId and correlationId are copied unless filtered or overwritten.
System.out.println(transformed.getHeaders().get("eventId")); // evt-101
~~~

`MessageBuilder.fromMessage(...)` illustrates copying headers when building a new message. In real flows, a Transformer returning a full message can decide its own output headers; verify the propagation of `eventId` and `correlationId` rather than assuming every endpoint preserves all metadata.

## 3. How does a delay group form and live?

When Delayer receives a message with a positive delay:

1. `DelayHandler` determines the release deadline using `defaultDelay`, a delay expression, or a delay function.
2. The message is stored in the **group keyed by `messageGroupId`** inside `MessageGroupStore`.
3. `TaskScheduler` is asked to schedule a task to release the message to the output when due.
4. When due, Delayer looks up and removes the message from the stored group right before forwarding it to the next endpoint.

This is a group of **pending messages**. It does not have the Aggregator semantics of "collect N parts then release", nor does it automatically establish per-order correlation. Delayer schedules **each message individually**; messages can have different deadlines while residing in the same delay group.

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant D as DelayHandler
    participant M as MessageGroupStore
    participant T as TaskScheduler
    participant C as Consumer
    P->>D: Message(eventId=evt-101, delay=3s)
    D->>M: Store in group payment.reminders.delay.v1
    D->>T: Schedule by deadline
    D-->>P: Return control
    Note over D,T: Message is held waiting for release
    T->>D: Due
    D->>M: Retrieve and remove message from group
    D->>C: Send message to next step
~~~

With a delay of `0` or negative, Delayer forwards immediately on the caller's thread; the message does not go through the scheduled waiting mechanism as with positive delays.

### Groups in Delayer vs. groups in Aggregator

| Property | Delayer | Aggregator |
| --- | --- | --- |
| Purpose | Wait until each message's release time | Combine related messages into a joint result |
| Group key | `messageGroupId` configured on the endpoint | Correlation key determined by the correlation strategy |
| Release timing | Each message's individual deadline | Release strategy, timeout, completion conditions |
| Needs `correlationId` to compute group? | No, for a standard Delayer | Usually yes, or requires an equivalent correlation mechanism |
| Result | Message forwarded after waiting | An aggregated result or released stream per configuration |

If the flow is `Splitter → Delayer → Aggregator`, keep the **two types of groups** semantically separate. The delay group stores Delayer's pending messages; the Aggregator group is computed by the correlation key of each batch/entity.

## 4. Rules for naming `messageGroupId`

A good `messageGroupId` should be:

- **Fixed and explicit** in configuration: e.g., `billing.payment-reminders.delay.v1`.
- **Distinct across independent Delayers** if they share a `MessageGroupStore`.
- **Stable across restarts and deployments** if pending messages should be recovered.
- **Follow a management naming convention**: business context, flow name, Delayer role, and version for planned migrations.

Example:

~~~java
.delay(d -> d
        .messageGroupId("billing.payment-reminders.delay.v1")
        .defaultDelay(30_000L)
        .messageStore(delayedMessageStore))
~~~

Since Spring Integration 6.2, Java DSL requires `DelayerEndpointSpec.messageGroupId(String)` for Delayer. Do not rely on framework-generated bean names: after a restart, an auto-generated name may change, preventing the new Delayer from reading the pending messages in the store.

**Important warning when sharing a store:** if two *different logical Delayers* point to the same `messageGroupId`, they can steal each other's messages (*work stealing*) or release them into the wrong branch. Conversely, multiple instances deployed as **the same logical Delayer** may share a group by design, but you must evaluate locking, transactions, scheduling, and processing contention in a distributed system. Sharing a group ID does not automatically give you exactly-once delivery.

Do not set the group ID to each message's individual `orderId` in standard Delayer configuration; that belongs in correlation/business headers. If a design truly requires partitioning processing by order, use a Router, a partitioned queue, or an appropriate orchestration mechanism.

## 5. Complete example: two Delayers, one MessageGroupStore

This Spring Integration Java DSL example uses **two independent Delayers** sharing an in-memory store to observe group separation. Producers only need to send messages to named channels; consumers can process asynchronously after the wait period ends.

Main dependency when using Spring Boot: `spring-boot-starter-integration`. To run the JUnit examples in the next section, add `spring-boot-starter-test`.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.store.MessageGroupStore;
import org.springframework.integration.store.SimpleMessageStore;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;

@Configuration
@EnableIntegration
public class DelayIdentityFlowConfig {

    public static final String PAYMENT_GROUP =
            "billing.payment-reminders.delay.v1";
    public static final String FRAUD_GROUP =
            "risk.fraud-alerts.delay.v1";

    @Bean
    public MessageGroupStore delayedMessageStore() {
        // For demo only: pending data is lost when the process stops.
        return new SimpleMessageStore();
    }

    @Bean("payment.in")
    public MessageChannel paymentIn() {
        return new DirectChannel();
    }

    @Bean("payment.out")
    public PollableChannel paymentOut() {
        return new QueueChannel();
    }

    @Bean("fraud.in")
    public MessageChannel fraudIn() {
        return new DirectChannel();
    }

    @Bean("fraud.out")
    public PollableChannel fraudOut() {
        return new QueueChannel();
    }

    @Bean
    public IntegrationFlow paymentReminderFlow(MessageGroupStore delayedMessageStore) {
        return IntegrationFlow.from("payment.in")
                .delay(d -> d
                        .messageGroupId(PAYMENT_GROUP)
                        .messageStore(delayedMessageStore)
                        .defaultDelay(3_000L))
                .channel("payment.out")
                .get();
    }

    @Bean
    public IntegrationFlow fraudAlertFlow(MessageGroupStore delayedMessageStore) {
        return IntegrationFlow.from("fraud.in")
                .delay(d -> d
                        .messageGroupId(FRAUD_GROUP)
                        .messageStore(delayedMessageStore)
                        .defaultDelay(3_000L))
                .channel("fraud.out")
                .get();
    }
}
~~~

All messages from `paymentReminderFlow` are held in `PAYMENT_GROUP`, even when they belong to different orders. Messages from `fraudAlertFlow` are stored in `FRAUD_GROUP`, even though one may share `correlationId = order-101` with a reminder.

`SimpleMessageStore` makes the mechanism easy to see, but it is **not the choice for preserving messages across restarts**. Section 8 explains the requirements when switching to a persistent store.

### Producer attaches identity at the right layer

~~~java
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

public class PaymentEventPublisher {
    private final MessageChannel paymentInput;
    private final MessageChannel fraudInput;

    public PaymentEventPublisher(MessageChannel paymentInput,
                                 MessageChannel fraudInput) {
        this.paymentInput = paymentInput;
        this.fraudInput = fraudInput;
    }

    public void publish() {
        paymentInput.send(MessageBuilder.withPayload("PAYMENT-REMINDER")
                .setHeader("eventId", "reminder-101")
                .setHeader(IntegrationMessageHeaderAccessor.CORRELATION_ID, "order-101")
                .build());

        paymentInput.send(MessageBuilder.withPayload("PAYMENT-REMINDER")
                .setHeader("eventId", "reminder-102")
                .setHeader(IntegrationMessageHeaderAccessor.CORRELATION_ID, "order-102")
                .build());

        fraudInput.send(MessageBuilder.withPayload("RISK-ALERT")
                .setHeader("eventId", "fraud-101")
                .setHeader(IntegrationMessageHeaderAccessor.CORRELATION_ID, "order-101")
                .build());
    }
}
~~~

The snippet above only illustrates the producer: when using dependency injection, specify the exact `payment.in` and `fraud.in` channels using `@Qualifier`. Each call creates a distinct `Message` with its own `id` header; `eventId` distinguishes the event, while `correlationId` indicates which order they belong to. Those headers **do not change Delayer's `messageGroupId`**.

## 6. Testing: separating groups and identity

The test below verifies the essentials: two messages with different IDs can wait in the same group, a third message belongs to a different group, and the consumer receives `eventId` for tracing. A 3-second wait is used to allow time to inspect the store before the deadline.

~~~java
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.integration.store.MessageGroupStore;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.*;

@SpringJUnitConfig(DelayIdentityFlowConfig.class)
class DelayIdentityFlowTest {

    @Autowired
    @Qualifier("payment.in")
    MessageChannel paymentIn;

    @Autowired
    @Qualifier("payment.out")
    PollableChannel paymentOut;

    @Autowired
    @Qualifier("fraud.in")
    MessageChannel fraudIn;

    @Autowired
    @Qualifier("fraud.out")
    PollableChannel fraudOut;

    @Autowired
    MessageGroupStore delayedMessageStore;

    @Test
    void separatesDelayerGroupsWithoutConfusingMessageIdentity() {
        Message<String> reminder1 = event("reminder-101", "order-101");
        Message<String> reminder2 = event("reminder-102", "order-102");
        Message<String> risk = event("fraud-101", "order-101");

        UUID firstMessageId = reminder1.getHeaders().getId();
        UUID secondMessageId = reminder2.getHeaders().getId();
        assertNotEquals(firstMessageId, secondMessageId);

        assertTrue(paymentIn.send(reminder1));
        assertTrue(paymentIn.send(reminder2));
        assertTrue(fraudIn.send(risk));

        // Read immediately while all three messages are still waiting.
        assertEquals(2, delayedMessageStore.getMessageGroup(
                DelayIdentityFlowConfig.PAYMENT_GROUP).size());
        assertEquals(1, delayedMessageStore.getMessageGroup(
                DelayIdentityFlowConfig.FRAUD_GROUP).size());

        Message<?> ready1 = paymentOut.receive(6_000);
        Message<?> ready2 = paymentOut.receive(6_000);
        Message<?> readyRisk = fraudOut.receive(6_000);

        assertNotNull(ready1);
        assertNotNull(ready2);
        assertNotNull(readyRisk);
        assertEquals("fraud-101", readyRisk.getHeaders().get("eventId"));

        // Do not enforce release order when messages have close deadlines.
        assertEquals(
                java.util.Set.of("reminder-101", "reminder-102"),
                java.util.Set.of(
                        ready1.getHeaders().get("eventId"),
                        ready2.getHeaders().get("eventId")));
    }

    private Message<String> event(String eventId, String orderId) {
        return MessageBuilder.withPayload("EVENT")
                .setHeader("eventId", eventId)
                .setHeader(IntegrationMessageHeaderAccessor.CORRELATION_ID, orderId)
                .build();
    }
}
~~~

The test demonstrates the behavior of a single context and `SimpleMessageStore`. The group size checks need to run **before the deadline**; in an overloaded CI pipeline, allow a longer wait duration or control the scheduler to avoid a race if the test runs too slowly before reading the store.

To also test release timing, you can add assertions that no output message arrives in the first 100 ms, then receive them with a sufficiently large timeout. Do not require the first-sent message to be released first when deadlines are close together.

## 7. Message identity across Transformer, Splitter, Router, and Aggregator

An event can pass through multiple EIPs:

~~~mermaid
flowchart LR
    I[Inbound Adapter] --> F[Filter]
    F --> T[Transformer]
    T --> S[Splitter]
    S --> D[Delayer]
    D --> R{Router}
    R --> C1[Consumer A]
    R --> C2[Consumer B]
    C1 --> A[Aggregator if business requires]
    C2 --> A
~~~

Each step must preserve the right type of identity:

| Component | Identity to care about | Notes |
| --- | --- | --- |
| Filter | `eventId` and discard reason | Log discarded messages without exposing sensitive data |
| Transformer | `eventId`, `correlationId` | A new message may get a new UUID; preserve business headers when needed |
| Splitter | `correlationId`, `sequenceNumber`, `sequenceSize` | Each part has its own message; identify both the root event and each part |
| Delayer | Configured `messageGroupId`, `eventId` | The delay group is for waiting to release, not for the Aggregator group |
| Router | `eventId`, target branch | Log the chosen processing branch for tracing |
| Aggregator | Correlation key and release strategy | Aggregate by business logic, do not use the delay group as a correlation key |
| Retry/error channel | `eventId`, attempt, error cause | Distinguish a release error from a new logical event |

For example, an order with three items after a Splitter shares `correlationId = order-101`, while each item message has its own `id`. Passing through Delayer, all three can wait in group `billing.payment-reminders.delay.v1`. Afterward, the Aggregator must aggregate by `correlationId` (or an explicit correlation strategy), **not by** `billing.payment-reminders.delay.v1`, because Delayer's group can hold messages from many orders.

If a business process has multiple child events, define `eventId`/`partId` stably at the producer or Transformer. A single shared `eventId` for the whole batch may not be enough as a deduplication key for **each individual item** after a Splitter.

## 8. Persistent store, restarts, and preserving groups

With the default `SimpleMessageStore`, pending messages typically live in process memory. When the application stops, messages not yet due risk being lost. For reminders that wait minutes or hours, configure a persistent `MessageGroupStore` such as `JdbcMessageStore`, together with a stable `messageGroupId`.

Replacement snippet in the flow when a `JdbcMessageStore` bean has **already been declared and configured**:

~~~java
@Bean
public IntegrationFlow durablePaymentReminderFlow(
        org.springframework.integration.jdbc.store.JdbcMessageStore jdbcMessageStore) {

    return IntegrationFlow.from("durable.payment.in")
            .delay(d -> d
                    .messageGroupId("billing.payment-reminders.delay.v1")
                    .messageStore(jdbcMessageStore)
                    .defaultDelay(60_000L))
            .channel("durable.payment.out")
            .get();
}
~~~

This snippet only illustrates attaching the store, **not a standalone runnable application**: it requires a `DataSource`, the JDBC Message Store schema, both channel beans, and an appropriate transaction strategy. Do not merge it into `DelayIdentityFlowConfig` above without declaring those dependencies.

After restart, `DelayHandler` finds messages in its group and reschedules them based on the original receipt timestamp for numeric delays, or by `Date` if the expression returned an absolute timestamp. Overdue messages can be released immediately after the application starts.

~~~mermaid
sequenceDiagram
    participant A as Application before restart
    participant J as JDBC MessageGroupStore
    participant B as Application after restart
    participant C as Consumer
    A->>J: Store evt-101 under stable group
    Note over A: Process stops while still waiting
    B->>J: Read group billing.payment-reminders.delay.v1
    J-->>B: Pending message
    B->>B: Recalculate deadline and schedule
    B->>C: Release when due
~~~

**Renaming a group ID is a data change** when using a persistent store. If a new version changes `billing.payment-reminders.delay.v1` to `...v2` without a data migration plan, the new application will not automatically pick up messages from the old group. When a change is needed, plan to drain, migrate, or explicitly manage both groups in parallel.

Beyond the group ID, pay attention to payload and header serializability. Some JDBC stores only support `Serializable` data by default and may drop non-serializable headers. In particular, watch out for reply/error channel headers pointing to in-memory objects, since after a restart the old object no longer exists. For long-running asynchronous flows, use suitable channel names or design dedicated callbacks with stable identifiers.

## 9. Redelivery, duplicates, and idempotency

A persistent store helps recover pending messages, but **does not turn the system into exactly-once**. For example:

1. Message `reminder-101` becomes due and is sent to the consumer.
2. The consumer successfully calls the email-sending service.
3. The process crashes before the full state is committed.
4. After retry or recovery, the same business event may be processed again.

If you only check `MessageHeaders.ID`, a message recreated from the same event may carry a different UUID and slip past duplicate detection. Use a stable business key such as `eventId = reminder-101`, combined with uniqueness constraints or a `MetadataStore` for Idempotent Receiver.

Minimal model:

~~~java
public void processReminder(String eventId, String orderId) {
    // Pseudocode: this operation needs to be atomic and persisted.
    if (alreadyProcessed(eventId)) {
        return;
    }

    sendReminder(orderId);
    markProcessed(eventId);
}
~~~

The snippet above is **pseudocode to illustrate the idea**: checking and marking separately has a race condition, and a database transaction cannot automatically roll back a sent email. In a real application, use a unique constraint/atomic claim and consider outbox, inbox, idempotency keys on the receiving service, or coordination mechanisms suited to external side effects.

Never use `messageGroupId` as an idempotency key: all reminders in the same Delayer can share one group ID, so doing so would accidentally treat distinct events as duplicates. Also do not treat `correlationId` as a deduplication key by default; one order can have multiple valid events sharing the same correlation ID.

## 10. Multi-instance coordination and store sharing

In a multi-instance deployment, two cases must be distinguished:

1. **Two different logical Delayers** sharing a store: each Delayer needs its own `messageGroupId`. If IDs collide, messages may be picked up by the wrong Delayer or released into an unintended flow.
2. **Multiple instances of the same logical Delayer** looking at one store: they can share a group, but then you must verify concurrency handling, store locking, transactions, rescheduling, and idempotency. Do not assume "only one instance will release a message" just because they share the same ID configuration.

Some `MessageGroupStore` implementations support locking mechanisms to protect group operations, but group locking does not solve the entire distributed scheduling and downstream effect problem. Monitoring concurrency, reprocessing counts, and release lag is mandatory when running distributed applications.

Prefer managing the group ID as a **stable deployment identifier**, and managing `eventId` as a **stable business identifier**. Both outlive a single in-memory Java instance.

## 11. Observability and troubleshooting

When logging or tracing each message, a useful metadata set is:

~~~text
flow=paymentReminderFlow
delayGroup=billing.payment-reminders.delay.v1
eventId=reminder-101
correlationId=order-101
messageId=<UUID of Message at the observed step>
scheduledAt=...
dueAt=...
releasedAt=...
attempt=...
outcome=SUCCESS|FAILED|RETRIED
~~~

Record `messageGroupId` in the endpoint's configuration/metrics; it does not automatically become a business header on every message. You can obtain `eventId` and `correlationId` from headers prepared by the producer/Transformer. Use the same trace ID to link logs across steps without logging sensitive payloads.

For a Delayer with persistence, `DelayHandler` provides management operations such as `getDelayedMessageCount()` and `reschedulePersistedMessages()`; invoking reschedule should be controlled to avoid interfering with messages currently in flight. Looking at the store only tells you which messages are **still waiting**; messages that have left the store but failed downstream must be tracked via the error channel, retries, and target systems.

| Symptom | Causes to check | Resolution |
| --- | --- | --- |
| After restart, pending reminders are missing | Group ID changed; in-memory store; wrong store/schema | Restore stable group ID, verify persistence and initialization |
| Fraud branch receives reminder messages | Two logically different Delayers share the same `messageGroupId` in one store | Separate group IDs and handle legacy data |
| One order has multiple pending messages | Multiple valid events share the same `correlationId` | Check `eventId` and business rules; do not dedupe by correlation alone |
| UUID at consumer differs from producer UUID | An intermediate step constructed a new message | Track stable `eventId`/trace ID |
| Consumer sends email twice | Retry/redelivery, upstream resend, or crash before acknowledgment | Idempotent consumer, inbox/outbox, atomic marking |
| Group exists but messages are not released | Scheduler stopped, startup error, delay configuration, store contention | Check scheduler, metrics, logs, and reschedule mechanism |
| Message is no longer in the group but business action failed | Message was already pulled for release, downstream error | Inspect retry/error channel, audit logs, and consumer results |

## 12. Practice exercises and self-check questions

1. Change `PAYMENT_GROUP` to another value and restart an application using a persistent store. What happens to pending messages in the old group? What migration plan is needed?
2. Send two events `reminder-101-first` and `reminder-101-final` with the same `correlationId = order-101` into one Delayer. Why are both valid and why shouldn't they be deduped solely by correlation ID?
3. Place a Transformer returning a new payload between the producer and Delayer. Observe `MessageHeaders.ID`, `eventId`, and `correlationId` before and after the Transformer.
4. Design a `Splitter → Delayer → Aggregator` flow for three line items of the same order. Clearly state the group used for waiting and the group used for aggregating results.
5. Configure two logically different Delayers but intentionally give them the same `messageGroupId` on the same test store. Describe the risk, then fix the configuration.
6. Test a restart with `JdbcMessageStore` and verify pending messages are rescheduled. Measure `dueAt` and `releasedAt` to identify late releases.
7. Simulate a consumer error followed by retry. Design an idempotency key that recognizes the **same business event** even when the producer builds a new `Message` with a different UUID.

## References

- [Spring Integration Reference — Delayer](https://docs.spring.io/spring-integration/reference/delayer.html): `messageGroupId`, `MessageGroupStore`, release scheduling, and restart recovery.
- [Spring Integration Reference — Message](https://docs.spring.io/spring-integration/reference/message.html): `MessageHeaders.ID`, `TIMESTAMP`, correlation headers, and message construction.
- [Spring Integration Reference — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html): `MessageGroupStore`, in-memory storage, persistence, and serialization.
- [Spring Integration API — DelayHandler](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/handler/DelayHandler.html): semantics and constraints of `messageGroupId`.
- [Spring Integration Reference — Idempotent Receiver](https://docs.spring.io/spring-integration/reference/handler-advice/idempotent-receiver.html): strategies for limiting duplicate processing at the consumer.
