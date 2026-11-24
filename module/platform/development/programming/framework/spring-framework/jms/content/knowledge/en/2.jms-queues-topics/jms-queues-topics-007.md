# Durable Subscriptions and Persistent Messages Are Two Different Concepts

> **Module:** Spring Framework – JMS  
> **Topic Group:** Queues and Topics  
> **Focus:** Distinguishing *the lifetime of a topic subscription* from *the delivery mode of each individual message* in JMS/Jakarta Messaging, and configuring both properly in Spring.

## Learning Objectives

After this lesson, you will be able to:

1. Accurately explain `durable subscription`, `non-durable subscription`, `PERSISTENT`, and `NON_PERSISTENT`; showing that they belong to **two independent configuration axes**.
2. Predict what happens when a topic consumer temporarily stops, when the broker restarts, when a subscription has never been created, or when a message expires.
3. Read the table of four durable/non-durable × persistent/non-persistent combinations without confusing "the message was persisted" with "subscribed to receive messages".
4. Configure a durable topic listener and a persistent producer with Spring JMS; understanding the roles of `clientId`, `subscription`, `pubSubDomain`, transactions, and acknowledgment.
5. Design operational tests and handle disconnections, redeliveries, duplicate reception, and subscription identity changes.

## 1. Two Different Questions Commonly Grouped Together as "Durability"

**Question A — Subscription lifecycle:** When the application has no connected consumer, does the broker continue remembering *who* subscribed to the topic and retain messages for that subscriber?

- This is the choice between a **durable subscription** and a **non-durable subscription**.
- It lives on the **subscription/consumer side** of a **topic**.
- A durable subscription has a **stable identity** in the provider, continues to exist when the consumer shuts down, and allows the consumer later to receive matching messages that arrived during its absence, subject to delivery and retention conditions.

**Question B — Message delivery guarantee level:** When a producer sends *a message*, must the broker use a more reliable mechanism so the message survives provider failures?

- This is the **delivery mode**: `PERSISTENT` or `NON_PERSISTENT`.
- It applies **per send/per message**, requested by the producer; the broker enforces it according to the specification and retention policy.
- `PERSISTENT` raises the protection level of transport and message storage against provider failures; it **does not automatically create an absent subscription**.

One short sentence to remember:

> **A durable subscription keeps the "registered receiver" across offline periods; persistent delivery protects the "sent message" against infrastructure failures.**

For the case of **offline topic consumer + broker failure**, achieving high reliability usually requires **both a durable subscription and PERSISTENT delivery**, plus appropriate retention, TTL, transaction, and broker infrastructure policies. The two options do not substitute for each other.

## 2. Topic Recap: Messages Are Recorded per Subscription

Producers send to a `Topic`; receivers do not directly "pull" from a shared topic copy like a queue. The provider manages **subscriptions**: each eligible subscription can receive a copy of messages published after the subscription exists.

```text
                                   TOPIC: orders.events
                                      |
                    +-----------------+-----------------+
                    |                                   |
           Subscription: audit                 Subscription: analytics
                    |                                   |
               Audit Consumer                       Analytics Consumer
```

If `audit` and `analytics` are two independent subscriptions, the Audit consumer acknowledging a message does **not** mean Analytics has acknowledged its copy. In a **shared subscription**, multiple consumers can share the work of the **same subscription**; each message belonging to that subscription is delivered to one consumer, rather than automatically duplicated to every worker in the group.

Normally, a subscription only sees messages published **after it was created**. A durable subscription is not a "replay the entire topic history" mechanism for a newly registered subscriber. If replaying data from before registration time is desired, a separate feature or historical storage stream designed by the system is needed.

### 2.1. Non-durable subscription

A non-durable subscription exists only while active consumers remain according to the JMS-defined lifecycle. When the subscription ceases to exist, newly published messages at that time are **not accumulated** for a returning consumer with the same name to fetch later.

```text
t0       t1            t2             t3
|--------|-------------|--------------|
         consumer OFF  publish M1     consumer ON
         sub gone      no sub         does not receive M1 from offline period
```

Even if the producer sends M1 with `PERSISTENT`, that **does not hold M1 on behalf of a vanished non-durable subscription**. This is a very common misunderstanding.

### 2.2. Durable subscription

A durable subscription is an entity retained by the provider, **not deleted merely because a consumer closes its connection**. When there is no active consumer, the subscription is in an *inactive* state; the provider continues managing matching messages entering the subscription, subject to conditions such as message expiration, delivery mode, and broker policies.

```text
t0                  t1                  t2                 t3
|-------------------|-------------------|------------------|
create durable sub  consumer OFF        publish M1         consumer ON
(clientId + name)   sub still exists    for existing sub   resumes from old sub
```

On a reliable recovery path, M1 should be sent `PERSISTENT` and not yet expired. If sent `NON_PERSISTENT`, **retaining the message across inactive periods or broker failures must not be treated as guaranteed**.

A durable subscription **does not mean every delivery is retained forever**: a message may already have been consumed/acknowledged, expired, failed to match a selector, or been subject to broker resource-limit policies. A subscription may still exist yet have no pending messages.

## 3. What Is a "Persistent Message" Actually?

JMS/Jakarta Messaging has two standard values in `jakarta.jms.DeliveryMode`:

| Delivery mode | Primary Meaning | What Must Not Be Inferred |
| --- | --- | --- |
| `PERSISTENT` | The provider must apply stronger delivery guarantees against provider failures, usually involving durable log/storage writes; the reliability-first choice | Does not automatically create a durable subscription; does not guarantee infinite retention, ignoring expiration, or exactly-once business completion |
| `NON_PERSISTENT` | Allows a lower-overhead delivery path; messages may be lost if the provider fails | Does not mean the broker is forced to drop them immediately; in practice they may still be delivered if the system is running steadily |

In the simplified API, the producer can choose:

```java
JMSProducer producer = context.createProducer();
producer.setDeliveryMode(DeliveryMode.PERSISTENT);
producer.send(topic, "OrderCreated: ORD-42");
```

This is an **illustrative snippet in an application that already has** `JMSContext context`, `Topic topic`, the `jakarta.jms` dependency, and a real provider. It cannot be run standalone with `javac` when those components are missing. With the classic API, the equivalent setting is placed on `MessageProducer` or as a parameter to `send(...)`; do **not** use `message.setJMSDeliveryMode(...)` to request the send mode.

### "Persistent" Does Not Mean "Never Lost"

Delivery mode guarantees per the specification assume the destination has a sufficiently suitable message-retention policy. Factors to consider:

- `timeToLive` and `JMSExpiration`: expired messages may no longer be delivered, even if `PERSISTENT`.
- **Message selector:** a subscription only accumulates messages matching its filter condition; other messages do not belong to that subscription.
- **Retention, quotas, disk, broker policies:** if resources run out, operators must decide the behavior and monitor alerts. Persistent does not turn the broker into an infinite store.
- **Acknowledgment/transactions:** a message that has been properly received, acknowledged, or committed does not remain stored waiting for consumers forever.
- **Provider configuration durability:** durable storage mechanisms, broker clustering, replication, and disaster recovery depend on the provider and deployment; `PERSISTENT` does not replace an operational strategy.

Assuming appropriate destination retention, the specification describes `PERSISTENT`'s guarantee at **provider-side delivery** as stronger than `NON_PERSISTENT`. That is not a promise of "exactly-once business side effects": the database may have committed before the consumer could ack, leading to duplicate business processing when the message redelivers.

## 4. The Four-Combination Table — Core of This Lesson

The following table assumes publishing to a **topic**, the subscription was created before send time, the message matches the selector, and it has not expired.

| Subscription | Message mode | Consumer offline at publish | Broker/provider failure | Conclusion |
| --- | --- | --- | --- | --- |
| **Non-durable** | `NON_PERSISTENT` | No subscription to accumulate messages; missed | Message may also be lost due to weaker mode | Suitable for droppable data |
| **Non-durable** | `PERSISTENT` | **Still missed** if subscription no longer exists | PERSISTENT protects delivery to eligible destinations/subscriptions, does not resurrect a vanished subscriber | **PERSISTENT does not replace durable** |
| **Durable** | `NON_PERSISTENT` | Subscription still exists, but **no guarantee** all non-persistent messages are kept until return | NON_PERSISTENT may be lost on provider failure | **Durable does not replace PERSISTENT** |
| **Durable** | `PERSISTENT` | Basis for accumulating matching messages during consumer absence | Stronger guarantee against provider failure per specification and retention policy | Standard choice for critical events needed after offline periods |

**Read the table along both axes**; do not interpret "durable" or "persistent" as a single switch named "reliable".

### 4.1. Example A: Persistent Yet Non-Durable Still Loses Events

- `Analytics` creates a **non-durable** subscription on `orders.events` while running.
- At 10:00 Analytics stops; the subscription ceases to exist.
- At 10:05 Order Service sends `OrderCreated(42)` with `DeliveryMode.PERSISTENT`.
- At 10:10 Analytics restarts.

Analytics **has no default right to receive** the 10:05 event: at that time no Analytics subscription existed. Sending the message PERSISTENT may protect the message for **other existing eligible subscriptions**, but does not "retroactively create a copy" for Analytics.

### 4.2. Example B: Durable Yet Non-Persistent Can Still Be Lost

- `Audit` created durable subscription `audit-orders`; then the consumer stops.
- The producer sends `OrderCreated(43)` using `NON_PERSISTENT`.
- While Audit is offline, the provider abruptly stops and restarts.
- Audit reconnects using the **same subscription identity**.

Even though the durable subscription remains, **you must not conclude** message 43 is guaranteed to be recovered. The specification permits risk of losing `NON_PERSISTENT` messages; not losing one in a single test run does not elevate it into a general guarantee.

### 4.3. Example C: Durable + Persistent for Critical Events

- `Audit` has registered a durable subscription, preserving a stable identity.
- The consumer stops; the producer sends `OrderCreated(44)` with `PERSISTENT` and an appropriate TTL.
- The broker operates normally or recovers within its guarantee scope, with retention sufficient to keep the message.
- Audit returns to the exact subscription, receives and processes the message, then commits/acks.

This is the standard design to minimize losing events while consumers are offline. **Idempotency** is still required, because messages can be redelivered when ack/commit boundaries are incomplete.

## 5. Durable Subscription Identity: Why "Returning with the Same Name" Matters

A durable subscription is stored under an identity; the consumer must restore **the exact old subscription** to receive backlog instead of registering a new subscription.

### Unshared durable subscription

In Jakarta Messaging, an **unshared durable subscription** is identified by **client identifier (`clientId`) and subscription name**, along with matching attributes such as topic, selector, and `noLocal`.

```text
Topic:           orders.events
Client ID:       audit-service
Subscription:    audit-orders-v1

=> one specific durable subscription on the provider side
```

The consumer starts for the first time and creates the subscription, then stops. On the next startup, use the same `clientId` + `subscriptionName` to reopen it; only **one active consumer** can be attached to an unshared durable subscription at a time.

If `audit-orders-v1` is accidentally changed to `audit-orders-v2`, that is a **different subscription**: old backlog is not automatically transferred to the new name. The old subscription may continue holding resources until deleted via an appropriate procedure.

A common deployment mistake is running two replicas with the **same client ID** for an unshared durable subscription and expecting both to read in parallel. JMS restricts concurrent use of duplicate client IDs and allows only one active consumer for an unshared durable subscription. To increase throughput, choose the right **shared durable** type or separate subscriptions with independent purposes.

### Shared durable subscription

JMS 2.0/Jakarta Messaging supports **shared durable subscriptions**: the same subscription can have multiple consumers consuming concurrently; a message belonging to this subscription is delivered to one consumer in the group. Shared durable is identified by subscription name and client ID **if set**; load-sharing rules depend on the provider.

Difference:

- **Two independent durable subscriptions** (`audit` and `analytics`): each group gets a copy of matching events.
- **Two consumers on the same shared durable subscription** (`audit-worker-1` and `audit-worker-2`): share the work of one group; each message does not automatically go to both workers.

Do not switch between shared and unshared by arbitrarily flipping a flag while a subscription is active. Check provider support, identity, selectors, configuration-change procedures, and pending data before deploying.

### Changing the Selector or Topic Can Also Affect Backlog

For **unshared durable**, the specification stipulates that when a subscription is inactive and a client recreates it with the same client ID + name but a **different topic, message selector, or `noLocal`**, the behavior is equivalent to discarding the old subscription and creating a new one. The old subscription's backlog may be lost. Therefore, do not treat changing a filter or topic name as a "harmless config tweak".

## 6. Another Boundary: Queues Do Not Use the Concept of Topic Durable Subscriptions

A `Queue` has a work-sharing model across consumers. Messages sent to a queue can wait until an eligible consumer receives them; there is no need to create a **durable topic subscription** for each stopped consumer. `PERSISTENT`/`NON_PERSISTENT` modes still apply to messages on a queue.

```text
QUEUE:                                TOPIC:

Producer --> [Queue] --> Worker      Producer --> [Topic]
                                               |
                                      +--------+--------+
                                      |                 |
                                 Durable sub A     Non-durable sub B
                                      |                 |
                                    Worker A          Worker B
```

| Question | Queue | Topic |
| --- | --- | --- |
| When all consumers are offline, do messages wait? | Usually yes, per queue delivery mode/retention | Only an existing (durable) subscription has a basis to keep messages for offline periods |
| Is `clientId + durable subscription name` required? | No for standard queue consumption | Yes for **unshared durable subscriptions** |
| Does `PERSISTENT` still matter? | Yes | Yes |
| How is "one message to multiple independent groups" implemented? | Needs multiple queues or a separate fan-out design | Multiple independent subscriptions on one topic |

In both models, **surviving broker failure** and **retaining until consumer completion** must be verified alongside ack/transactions, TTL, and resource policies.

## 7. How to Configure in Spring JMS (Jakarta Messaging)

Spring Framework 6+ uses `jakarta.jms`. The two axes have different configuration locations:

- **Listener side:** `DefaultJmsListenerContainerFactory.setPubSubDomain(true)`, `setSubscriptionDurable(true)`, `setClientId(...)`; the `@JmsListener` method declares `subscription`.
- **Producer side:** `JmsTemplate.setPubSubDomain(true)` to send to a topic, `setDeliveryPersistent(true)` / `setDeliveryMode(DeliveryMode.PERSISTENT)` to choose mode; **`setExplicitQosEnabled(true)` must be enabled** if you want `JmsTemplate` to apply QoS overrides instead of relying on provider defaults.

### 7.1. Spring Example: Durable Topic Consumer and Persistent Producer

Assume the Spring application already has the `spring-jms` dependency, a compatible JMS provider, a `jakarta.jms.ConnectionFactory` pointing to a real broker, destination `orders.events` configured, and component scanning enabled. The code below uses Java 17+; **this is an example of classes within a Spring project**, not a standalone file runnable with `javac` alone.

**File `DurableTopicJmsConfig.java`**:

```java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.core.JmsTemplate;

@Configuration
@EnableJms
public class DurableTopicJmsConfig {

    @Bean
    public DefaultJmsListenerContainerFactory durableTopicFactory(
            ConnectionFactory connectionFactory) {

        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setPubSubDomain(true);            // Destination is Topic
        factory.setSubscriptionDurable(true);     // Retain subscription while offline
        factory.setClientId("audit-service");     // Stable across restarts
        factory.setConcurrency("1");              // Unshared: one active consumer
        factory.setSessionTransacted(true);       // Commit/rollback JMS receive
        return factory;
    }

    @Bean
    public JmsTemplate persistentTopicTemplate(ConnectionFactory connectionFactory) {
        var template = new JmsTemplate(connectionFactory);
        template.setPubSubDomain(true);           // Send to Topic
        template.setExplicitQosEnabled(true);     // Apply explicit QoS settings
        template.setDeliveryMode(DeliveryMode.PERSISTENT);
        template.setTimeToLive(0);                // 0 = no JMS expiration
        return template;
    }
}
```

**File `OrderEventPublisher.java`**:

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {
    private final JmsTemplate persistentTopicTemplate;

    public OrderEventPublisher(
            @Qualifier("persistentTopicTemplate") JmsTemplate persistentTopicTemplate) {
        this.persistentTopicTemplate = persistentTopicTemplate;
    }

    public void publishOrderCreated(String orderId) {
        persistentTopicTemplate.convertAndSend("orders.events", orderId);
    }
}
```

**File `OrderAuditListener.java`**:

```java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderAuditListener {

    @JmsListener(
            destination = "orders.events",
            subscription = "audit-orders-v1",
            containerFactory = "durableTopicFactory")
    public void onOrderCreated(String orderId) {
        // Real app: check eventId, update business state in a transaction.
        System.out.println("Audit received order: " + orderId);
    }
}
```

If `publishOrderCreated("ORD-42")` is called while the broker, publisher, and listener are running with proper configuration, the listener **may** print:

```text
Audit received order: ORD-42
```

This is only an **illustrative result when the consumer actually receives and processes the message**; it cannot be guaranteed that the log appears strictly once or immediately after the send call. The message may be waiting in the broker, retried, or fail to arrive due to configuration/delivery condition errors.

### 7.2. Role of Each Line Across Both Axes

| Configuration Line | Axis Decided | What Can Omitting or Misconfiguring It Cause? |
| --- | --- | --- |
| Listener `setPubSubDomain(true)` | Choose Topic | May be interpreted as a queue with the same logical name |
| Listener `setSubscriptionDurable(true)` | Subscription lifecycle | When no consumer remains, the subscription no longer retains backlog |
| Listener `setClientId("audit-service")` | Unshared durable identity | Restarting with another ID will not reopen the same subscription; duplicate IDs across replicas cause errors |
| `@JmsListener(subscription="audit-orders-v1")` | Subscription name | Renaming will not automatically inherit old backlog |
| Producer `setPubSubDomain(true)` | Choose Topic | May send to a queue instead of a topic |
| Producer `setExplicitQosEnabled(true)` | Apply QoS overrides | `setDeliveryMode` may not govern the send as assumed |
| Producer `setDeliveryMode(PERSISTENT)` | Message reliability | Choosing NON_PERSISTENT allows message loss on provider failure |
| Listener `setSessionTransacted(true)` | JMS Ack/commit | Configuring durable alone is not enough for reliable error handling |

**Transaction scope:** `setSessionTransacted(true)` places JMS reception in a local JMS transaction. It **does not automatically merge a database transaction** with the broker transaction. If the DB commits and the JVM dies before JMS commits, the message can return; the consumer must handle duplicates safely or use an appropriately scoped coordinated transaction mechanism.

**Multi-instance deployment:** the example uses **unshared durable** and a fixed `clientId`. Do not concurrently run two replicas with the same client ID as two separate consumers. If scaling is needed, consider `setSubscriptionShared(true)` on a provider that supports shared durable and redesign identity, or split consumers by responsibility.

**Do not rely on defaults:** JMS often defaults producers to sending `PERSISTENT`, though QoS can be overridden on the provider or Spring side. When the domain requires specific reliability, configure explicitly and verify actual `JMSDeliveryMode`/metadata on the broker rather than guessing from code.

### 7.3. Why Not Enable Durable for Every Listener?

Durable subscriptions consume resources and can build an ever-growing backlog when a consumer stays inactive for a long time. If every deployment creates a new subscription using a random instance name, the broker will accumulate many "orphan" subscriptions. Use durable when data must be retained for that group, apply managed naming, configure backlog alerts, and have an `unsubscribe` procedure when a subscription is truly no longer used.

## 8. Test Scenarios to Prove Both Axes

A good test must **separate consumer offline** from **broker failure**. Do not simply send a message while everything is online and conclude durability exists.

### Test 1 — Durable While Consumer Is Offline

1. Start the broker; run the durable listener `audit-service/audit-orders-v1` at least once to create the subscription.
2. Stop the listener/application **without deleting the subscription**.
3. Keep the broker running; publish `M1` using `PERSISTENT` to `orders.events`.
4. Verify the broker shows the subscription as inactive with a matching message waiting (how to inspect depends on the provider).
5. Restart the listener using the **same client ID + subscription name**; verify receiving `M1` and then ack/commit.

Expected result under normal conditions: the message published during offline time is retained for the listener to receive later. If not received, check whether the subscription was created before sending, topic, selector, TTL, retention, permissions, and identity.

### Test 2 — PERSISTENT Does Not Save Non-Durable

1. Create a **non-durable** topic consumer, verify receiving `M0` while online.
2. Close the consumer; ensure the non-durable subscription no longer exists.
3. Publish `M2` with `PERSISTENT` while the consumer is offline.
4. Recreate the non-durable consumer.

Do not expect retroactive delivery of `M2`. If a broker-specific feature allows replay, note clearly that it is a proprietary feature, **not a guarantee of JMS non-durable subscriptions**.

### Test 3 — Broker Restart

1. Keep an already created **durable** subscription; stop the consumer.
2. Publish `M3` with `PERSISTENT`; verify the broker accepted it and the message has not expired.
3. Stop/restart the broker per infrastructure test scenarios, with persistence/retention properly configured.
4. Start the consumer with the old identity and verify processing `M3`.

If repeating with `NON_PERSISTENT`, **do not set a mandatory criterion "must be lost"**: that mode permits loss on provider failure, rather than requiring every provider to drop messages on every restart. The proper criterion is **not relying on lucky outcomes to promise reliability**.

### Test 4 — TTL and Acknowledgment

- Send `PERSISTENT` with a very short TTL and leave the consumer offline too long: the message may expire, and this example cannot be used to conclude durable is broken.
- In a transacted listener, intentionally raise an error after receiving: observe rollback/redelivery per provider configuration; then ensure idempotency on retry.
- Recheck a message that was just received without ack when the consumer died: a durable subscription needs to retain/recover unacknowledged messages under JMS conditions.

### Verification Matrix to Record

| Test | Subscription | Send mode | What to Confirm |
| --- | --- | --- | --- |
| Offline + return | Durable | PERSISTENT | Continues receiving matching, unexpired backlog |
| Offline + return | Non-durable | PERSISTENT | No backlog preserved for the vanished subscription |
| Broker restart | Durable | PERSISTENT | Recoverability per JMS guarantees and storage/retention config |
| Broker restart | Durable | NON_PERSISTENT | Recovery is **not guaranteed**; a single test result may vary |
| Listener throws error | Durable | PERSISTENT | Ack/transaction determines redelivery; idempotency is needed |

## 9. Real-World Mistakes and How to Spot Them

### Mistake 1: "The producer enabled PERSISTENT, so an offline topic listener won't lose messages"

**Wrong on the subscription axis.** If the listener only uses a non-durable subscription and closed, nowhere records the right to receive messages during offline time. A previously registered durable subscription matching the business responsibility is required.

### Mistake 2: "Durable is enabled, so delivery mode doesn't matter"

**Wrong on the message axis.** Durable preserves subscription identity and backlog per the model; `NON_PERSISTENT` still carries risk of loss due to provider failure and is not guaranteed while the durable consumer is inactive. For critical events, send `PERSISTENT` and verify retention.

### Mistake 3: "Rename the subscription on deploy just to make logs easier to read"

The subscription name is part of its identity and affects backlog. When renamed, the new consumer may not receive messages waiting on the old subscription. You need a migration procedure, monitoring of pending message counts, and active cleanup of the old subscription.

### Mistake 4: "Running two replicas with the same client ID gives two load-sharing workers"

For unshared durable, that is not a valid scaling model. Choose shared durable when multiple consumers on the same subscription are needed and supported by the provider; or split into separate subscriptions if independent fan-out is needed.

### Mistake 5: "Durable + PERSISTENT alone is enough for system-wide exactly-once"

No. When a listener writes to the DB successfully and then loses connection before JMS commit/ack, the message can be redelivered; if sending an email, adding points, or deducting money lacks an idempotency key, the side effect can double. Durable and PERSISTENT solve different parts of the reliability problem, and do not replace transaction/deduplication design.

### Mistake 6: "If the consumer didn't receive the message, the provider definitely lost it"

Not necessarily. Check in order: right broker and topic, subscription existed before publish, right `clientId`/subscription name, whether listener is actually active, selector/noLocal, TTL, broker destination policy, producer delivery mode, whether send transaction committed, authorization, and broker backlog/dead-letter.

### Mistake 7: "PERSISTENT means the message lives forever"

`PERSISTENT` concerns delivery guarantee levels against provider failure. Messages can still expire or be processed/acked; brokers have administrative policies and resource limits. Long-term event storage for historical querying is a separate data storage requirement and should not be implicitly delegated to a topic.

## 10. Decisions to Finalize During Design

Before putting critical events onto a JMS topic, answer:

1. **Who needs a copy?** Does each interested system have an independent subscription or are workers sharing load within the same shared subscription?
2. **Can offline misses be tolerated?** If yes, non-durable may fit; if no, a durable subscription must be created before publish time.
3. **Can loss on broker failure be tolerated?** If no, consider `PERSISTENT` together with appropriate infrastructure and retention.
4. **What is the fixed identity?** For unshared durable, lock down `clientId` + subscription name; do not vary per run.
5. **How long do messages live?** Choose TTL, backlog rules, quotas, alerts, and handling of long-inactive subscriptions.
6. **Who acks on processing failure?** Choose a local JMS transaction or appropriate mechanism; design retries and idempotency for database/side effects.
7. **How are topic/selector/schema changes handled?** Plan backlog migration, payload compatibility, and rollback.
8. **What is observed?** Active/inactive subscription counts, pending messages per subscription, message age, redelivery count, dead-letter, and processing duration.

## 11. Self-Check

**Question 1.** A consumer uses a non-durable subscription. The producer sends a `PERSISTENT` message while the consumer is off. Can the consumer claim that message back under JMS guarantees?

**Answer:** No. PERSISTENT does not create or hold a non-durable subscription during periods with no consumer.

**Question 2.** Audit created a durable subscription, but the producer sends `NON_PERSISTENT`. When the broker crashes and restarts, is Audit guaranteed to receive everything?

**Answer:** No. The subscription keeps its identity, but the message mode allows loss upon provider failure; succeeding in recovery once does not turn into a guarantee.

**Question 3.** Two teams, Audit and Analytics, both need every event. Can two consumers in the same shared durable subscription be used?

**Answer:** Does not satisfy both groups getting a copy. They would split messages of **one** subscription. Two independent subscriptions are needed, where each group may use multiple workers inside its own shared subscription.

**Question 4.** A durable consumer restarts with a different client ID but the same old subscription name. Does it automatically receive the old backlog?

**Answer:** For **unshared durable**, no: identity consists of client ID and subscription name. You must reopen with the exact same identity.

**Question 5.** Durable + PERSISTENT + 1-minute TTL. The consumer returns after 24 hours and does not receive the message. Is the system definitely violating the specification?

**Answer:** No. The message may have expired according to `JMSExpiration`.

**Question 6.** A Spring listener has `setSubscriptionDurable(true)`; the producer calls `JmsTemplate.setDeliveryMode(PERSISTENT)` without enabling `setExplicitQosEnabled(true)`. Is the send guaranteed to use the specified QoS?

**Answer:** Not yet. `JmsTemplate` may use provider defaults/configured defaults when explicit QoS is not enabled. You must configure it and verify the actual delivery mode.

**Question 7.** A listener commits the DB and crashes before JMS ack. Does the durable + PERSISTENT setup prevent writing to the DB twice?

**Answer:** Not automatically. The message may be redelivered; idempotency (such as a unique processed event ID) or a properly scoped coordinated transaction must be designed.

## Knowledge Conclusion

- **Durable subscription** answers: "Whose subscription continues to exist to receive messages while the consumer is disconnected?"
- **PERSISTENT delivery mode** answers: "With what level of protection against provider failure is this message delivered by the broker?"
- For critical event topics that must be received while consumers are offline, **both axes must be right**: an already existing durable subscription and PERSISTENT messages, along with appropriate retention/TTL/ack/transactions.
- Even then, **do not infer business-level exactly-once**: duplicate handling, backlog monitoring, errors, and subscription lifecycle must be designed.

### Official References

1. [Jakarta Messaging 3.1 Specification — Topic semantics (`4.2.2)](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html) — durable/non-durable, shared/unshared, client ID, and identity.
2. [Jakarta Messaging 3.1 — Reliability (`4.2.11; `7.7; `9.1)](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html) — mode table and guarantee conditions.
3. [Spring Framework — Annotation-driven JMS Listener Endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html) — `@JmsListener` and container factory.
4. [Spring Framework — Receiving a Message](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html) — transactions, acknowledgment, and listeners.
5. [Spring Framework — Sending a Message](https://docs.spring.io/spring-framework/reference/integration/jms/sending.html) — `JmsTemplate`, conversion, and QoS.
6. [Spring Javadoc — `JmsTemplate.setExplicitQosEnabled`](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/core/JmsTemplate.html) — documents the condition for applying `deliveryMode`.