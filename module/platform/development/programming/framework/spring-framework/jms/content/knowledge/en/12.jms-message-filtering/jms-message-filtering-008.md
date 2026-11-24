# Impact of Selectors on Load Distribution and Unconsumed Messages in JMS

> **Module:** Spring Framework – JMS  
> **Parent topic:** Message filtering  
> **Focus:** Message selectors alter the set of consumers eligible to receive messages, thereby affecting load distribution, backlogs, and messages with no matching consumer.

## Learning objectives

After this lesson, you can:

1. Accurately describe message selectors in Jakarta Messaging: SQL92-subset conditions evaluated on **JMS headers/properties**, without directly reading the body.
2. Explain on a **Queue**: whichever consumer's selector a message matches can receive it; unmatched messages can be received by another consumer or **remain in the queue**, instead of disappearing.
3. Explain on a **Topic**: selectors restrict which messages are **added to each subscription**, completely different from leaving unmatched messages in a shared queue.
4. Analyze load across multiple consumers when selectors are **mutually exclusive**, **overlapping**, **under-covering**, or when a consumer group stops running.
5. Identify stuck messages caused by missing JMS properties, wrong property type/case, expressions evaluating to `UNKNOWN`, no matching consumer, blocked consumers, or misconfigured durable subscriptions.
6. Use `Session.createConsumer(..., selector)`, `JMSContext.createConsumer(..., selector)`, and `@JmsListener(selector = "...")` in Spring JMS applications.
7. Measure queue depth, pending counts by category, message age, consumer counts, throughput, redeliveries, and expirations to distinguish **mis-filtering** from **under-provisioned workers**.
8. Choose a design among a single queue with selectors, multiple queues separated by group, and topics with appropriate subscriptions, including when fan-out is required.

## 1. What does a message selector actually do?

A **message selector** is a conditional expression registered **when creating a JMS consumer/subscription**. Jakarta Messaging lets the provider inspect a set of JMS headers and message properties on the application's behalf, delivering only messages **matching the condition** to that consumer/subscription.

Example message with properties:

```text
JMSDestination = Queue:dispatch.jobs
JMSPriority    = 4
region         = "NORTH"     (String property)
tier           = 2           (int property)
kind           = "INVOICE"   (String property)
```

Consumer registers:

```sql
region = 'NORTH' AND tier >= 2
```

This message is eligible to be received because both branches are true. A consumer with selector `region = 'SOUTH'` is **not eligible** to receive that message.

A selector is **not**:

- An instruction for the **producer** to send only to one named consumer.
- A Java predicate running after the consumer already received the message and then executing `if`/`else` inside the handler.
- A rule automatically moving unmatched messages to a **DLQ**.
- A mechanism guaranteeing even round-robin distribution.
- A way to search JSON fields inside `TextMessage.getText()`.
- A condition automatically applied to every other consumer on the same destination.

It specifies **the set of messages a consumer wants to receive**. The consequences on Queue and Topic **differ**, which is the core of this lesson.

### 1.1. Inspection boundary: headers/properties, not body

```text
Message
  |-- JMS headers (a set of names allowed in selectors)
  |-- application properties: region, kind, tier, tenantId...
  |-- body: JSON / binary / TextMessage / MapMessage / ...
          X standard selectors do not directly read body fields
```

If the body contains `{"region":"NORTH"}` yet has **no JMS property** named `region`, the selector `region = 'NORTH'` **does not match**. Properties are metadata independent of body content. The producer needs to copy routing fields into **explicitly declared JMS properties**.

Not every JMS header can be used in a selector. Standard header fields allowed to be referenced under Jakarta Messaging are `JMSDeliveryMode`, `JMSPriority`, `JMSMessageID`, `JMSTimestamp`, `JMSCorrelationID`, and `JMSType`. For instance, `JMSPriority >= 7` is valid. Do not assume `JMSDestination`, `JMSReplyTo`, `JMSExpiration`, or body contents are portable filter fields.

### 1.2. How behavior differs by Destination

```text
                 Producer
                    |
         +----------+------------+
         |                       |
         v                       v
      QUEUE                      TOPIC
  dispatch.jobs               orders.events
         |                       |
         |                       +--> Subscription Audit
         |                       |       selector: kind='INVOICE'
         |                       |
         +--> Consumer NORTH     +--> Subscription Analytics
         |      selector:NORTH           selector: amount>=1000
         |
         +--> Consumer SOUTH
                selector:SOUTH

QUEUE: one message is delivered to one matching consumer.
       No match -> message may wait in the queue.

TOPIC: each independent subscription evaluates its own selector.
       Does not match subscription -> no copy added to that subscription.
```

Do not use the visual similarity of "two consumers both having selectors" to infer that two queue consumers both receive every matching message. **Queues are competing consumers; Topics have separate subscriptions**. <u>A selector does not turn a queue into a topic.</u>

## 2. Queue: selectors change who can receive a message

According to the Jakarta Messaging point-to-point specification, a queue can have multiple consumers. A message is delivered to **only one consumer per delivery**, and if the consumer has a selector, the message must match that selector. Messages not chosen by this consumer **remain in the queue or are received by another consumer**.

### 2.1. Two regional workers, mutually exclusive conditions

Suppose on the same queue `dispatch.jobs`:

- `WorkerNorth`: `region = 'NORTH'`
- `WorkerSouth`: `region = 'SOUTH'`

Producer sends:

| Message | JMS property `region` | Eligible consumer |
| --- | --- | --- |
| `M-1` | `NORTH` | North |
| `M-2` | `SOUTH` | South |
| `M-3` | `NORTH` | North |
| `M-4` | `WEST` | **Nobody** |
| `M-5` | **Property missing** | **Nobody** |

```text
                        Queue dispatch.jobs
                    M-1  M-2  M-3  M-4  M-5
                       |    |    |    X    X
                       v    v    v    |    |
                    North South North +----+--> still waiting
```

Assuming the broker accepted the messages, they have not expired, no policy deleted them, and only those two consumers exist, `M-4`/`M-5` have **no eligible consumer**. They do not automatically turn into DLQ messages simply for failing to match a selector; the queue can accumulate them, waiting for a new consumer with a matching selector (or an unfiltered consumer), or another broker policy.

**Key point:** this backlog can grow **even while North and South are healthy and processing very quickly**.

### 2.2. Multiple workers with the same selector still compete for load

Suppose:

- `North A`, `North B` share selector `region = 'NORTH'`.
- `South C` has selector `region = 'SOUTH'`.

A `region=NORTH` message is eligible for both A and B, yet per delivery only **one** of the two receives it. If redelivery occurs after a rollback, the provider may redeliver it, so do not infer "exactly-once business processing."

```text
      NORTH messages
         /     \
        v       v
   North A    North B    (competing within NORTH)
       \        /
     same queue and same type of work

      SOUTH messages
          |
          v
       South C
```

Distribution between A and B is **not mandated by JMS to be 50/50**. The broker may factor in receive readiness, prefetch, active consumers, transactions, priority, message grouping, connection speed, and its own dispatch policies. "Two workers" increases **processing capacity**, not a round-robin guarantee.

### 2.3. Overlapping selectors: not fan-out

Suppose consumer A uses:

```sql
region = 'NORTH'
```

Consumer B uses:

```sql
tier >= 3
```

A message with `region=NORTH, tier=3` **matches both A and B**. On a **Queue**, the provider can deliver that message to **A or B**, without creating two copies just because both selectors evaluate true. As a result:

- A can grab priority messages that B also wants.
- B can process NORTH-region messages, even if B was intended for a different workflow.
- Actual per-listener load can become unpredictable.
- If A and B perform **two independent business operations**, placing them as two consumers on the same queue is an architectural mistake: use a Topic with two subscriptions or explicit fan-out.

**Do not treat selectors as priority rules**: a selector only expresses "eligible to receive" rather than establishing consumer selection order when multiple consumers qualify.

### 2.4. Under-covering selectors: stuck messages

If all consumers filter only `NORTH`/`SOUTH`, while producers still send `WEST` or omit `region`, the backlog fills with messages nobody processes.

Consequences:

1. Queue depth rises, even while consumer status remains "healthy."
2. Pending count can be high even as throughput continues for valid groups.
3. Stuck data can consume broker quotas/disk/memory.
4. Depending on the implementation, scanning/traversing messages and matching can add overhead, latency, or head-of-line-like effects; **do not promise every broker is always blocked by an unmatched message at the head of the queue**.
5. As long as these messages have not expired, they still have no eligible consumer. Adding more North workers does not help process `WEST`.
6. Adding a proper `WestWorker` or a consumer permitted to read all messages can reduce the backlog. However, an unfiltered consumer can **compete for NORTH/SOUTH messages too**, so do not use one as a "catch-only-unmatched fallback" without a dedicated routing policy.

### 2.5. Selectors do not automatically form an "unmatched" group

It sounds reasonable: add a consumer with selector `region <> 'NORTH' AND region <> 'SOUTH'` to catch all erroneous messages.

Yet there is a trap:

- When property `region` **does not exist**, comparing with `NULL` evaluates to `UNKNOWN`, so `region <> 'NORTH'` **does not return TRUE**.
- For messages with wrong property types or invalid contents, some comparisons also fail to return TRUE as a developer expects.
- A fallback expression must handle missing properties explicitly, e.g., `region IS NULL`, and still check data types/broker policies.
- If a consumer cannot filter all error forms, messages still pile up.

Safer approach: **validate routing metadata before publishing**, route invalid messages to a separate queue, and maintain a tested JMS property contract. Do not try to catch every kind of invalid message with one complex selector.

## 3. Topic: selectors filter messages added to each subscription

Topics use the publish/subscribe model. A producer publishes a message; each **independent subscription** receives copies of messages matching that subscription's own selector, starting from when the subscription exists per its lifecycle.

### 3.1. Two independent subscriptions, different selectors

Topic `orders.events` has:

- Subscription `Audit`: `kind = 'INVOICE'`.
- Subscription `Metrics`: `amount >= 1_000` — note that **JMS selectors do not support underscores in Java-style numeric literals**; the actual selector must be written `amount >= 1000`.

Suppose three messages arrive:

| Event | `kind` | `amount` int | Audit | Metrics |
| --- | --- | ---: | --- | --- |
| E1 | INVOICE | 1500 | Gets a copy | Gets a copy |
| E2 | INVOICE | 50 | Gets a copy | No |
| E3 | PAYMENT | 2000 | No | Gets a copy |

`E1` matches **both subscriptions**, so each independent subscription gets a copy added. Ack/commit on Audit does not replace ack/commit on Metrics. `E2` does not match Metrics so **it is not added to the Metrics subscription**; it does not "sit waiting for Metrics to change its selector" like a message on a shared queue.

### 3.2. Non-durable and durable affect retained messages differently

**Non-durable subscription**:

- Receives matching messages while the subscription exists.
- Once no subscriber remains, future messages **are not retained for any new subscriber to receive retroactively** under JMS.
- If the subscription was not created before the producer published, you cannot demand historical events.

**Durable subscription**:

- Has identity (subscription name and appropriate identity/client ID attributes).
- The provider maintains the subscription when the consumer shuts down; messages **matching the selector** are added to the subscription's backlog for later processing, subject to delivery mode, expiration, and broker policies.
- Messages **not matching** the selector **are not added to that subscription's backlog**, so a subscriber changing its mind later does not automatically receive them.
- Multiple **independent subscriptions** can be created for different business purposes, each with its own backlog and acknowledgments.

**Shared subscription**:

- Multiple consumers on the same shared subscription share load: one message copy of the subscription is delivered to **one consumer** in the group.
- A shared subscription is not equivalent to multiple independent subscriptions; if two applications must both see an event, two separate subscriptions are needed.

### 3.3. Changing a durable subscription's selector changes its retention contract

In Jakarta Messaging, a durable subscription has an identity, topic, and selector tied to its state. For an unshared durable subscription, recreating with the same identity yet a **different selector** (when no consumer is active) is equivalent to deleting the old subscription and creating a new one. Old pending messages risk being lost from the subscription under this contract.

**Do not silently edit a durable selector in production** like changing a database SQL query condition expecting the old backlog to remain intact. When event reception requirements change, create a migration plan, rename the subscription intentionally, drain/handle backlog, reconcile duplicate/missing events, and test against the specific broker. For shared subscriptions, rules around recreation and selector changes have their own constraints; do not assume a running consumer's selector can be changed dynamically.

### 3.4. Comparing the same condition on Queue and Topic

| Question | Queue with consumer selector | Topic with subscription selector |
| --- | --- | --- |
| Message matches two consumers/subscriptions? | **One consumer** receives it per delivery | **Each independent subscription** can get a copy |
| Message does not match consumer A? | Can be received by consumer B or **stay in queue** | Not added to **subscription A** |
| A is offline? | Queue message can still wait, per policy | Non-durable guarantees no backlog; durable can accumulate backlog |
| Increasing consumers with same selector? | Can increase throughput for matched group | Shared sub shares load; independent subs create extra copies |
| Changing selector? | New consumer can pick up matching pending queue messages | Does not recreate history of events already excluded from subscription |
| Where is backlog observed? | Queue pending messages; multiple types may mix | Backlog **per subscription**; do not watch only topic publish count |
| When nothing matches? | Pending/expiration/quota per queue/broker | No copy for that subscription |

**Lesson:** selectors affect **load distribution** on a Queue, while on a Topic they also govern **copy scope/retention per subscription**. This is not a single universal "filter after message reaches handler" pattern for all destinations.

## 4. Syntax rules that cause messages to be "wrongly filtered out"

JMS selectors use a **SQL92 subset**, not full database SQL and not JavaScript/SpEL expressions.

### 4.1. Commonly used valid expressions

```sql
region = 'NORTH'
kind IN ('INVOICE', 'PAYMENT')
tier >= 2 AND enabled = TRUE
JMSPriority >= 7
eventType LIKE 'Order%'
region IS NULL
region IS NOT NULL
tier BETWEEN 2 AND 4
(region = 'NORTH' OR region = 'SOUTH') AND tier >= 2
```

These are **selector syntax** examples, not SQL statements sent to an RDBMS. Properties `region`/`tier`/`kind` must actually exist with compatible types on the message.

Important notation:

- String literals use **single quotes** `'NORTH'`, not double quotes like Java strings.
- Property/identifier names are case-sensitive: `region` differs from `Region`.
- String values must also match exact casing per contract: `'NORTH'` differs from `'north'`.
- Boolean literals are `TRUE`/`FALSE`, **not** String `'true'`.
- Common operators: `=`, `<>`, `>`, `>=`, `<`, `<=`, `AND`, `OR`, `NOT`, `IN`, `BETWEEN`, `LIKE`, `IS NULL`.
- Use parentheses to clarify `AND`/`OR` precedence, especially when grouping business clauses.
- Java numeric literals with underscores like `1_000` cannot be used verbatim in selectors; write `1000`.

### 4.2. Property types must be set properly

```java
message.setIntProperty("tier", 3);
message.setBooleanProperty("enabled", true);
message.setStringProperty("region", "NORTH");
```

With these three calls:

```sql
tier >= 2 AND enabled = TRUE AND region = 'NORTH'
```

can evaluate to TRUE.

However, if the producer writes:

```java
message.setStringProperty("tier", "3");
```

then selector `tier >= 2` **does not automatically coerce the String into a number in the Java sense**. Cross-type comparisons may fail to match; JMS selectors are not general String-to-int casts. The proper fix is aligning the **JMS property schema** and setters, not just changing JSON values in the body.

### 4.3. NULL and the three truth values TRUE/FALSE/UNKNOWN

SQL92 selectors use **three-valued logic**:

- Result `TRUE` → message **matches**.
- Result `FALSE` → message **does not match**.
- Result `UNKNOWN` → message **does not match**.

If property `region` is absent:

| Selector | Result | Is message delivered to consumer with this selector? |
| --- | --- | --- |
| `region = 'NORTH'` | UNKNOWN | No |
| `region <> 'NORTH'` | UNKNOWN | No |
| `NOT (region = 'NORTH')` | UNKNOWN | No |
| `region IS NULL` | TRUE | Yes |
| `region IS NOT NULL` | FALSE | No |
| `region = 'NORTH' OR region IS NULL` | TRUE | Yes |
| `region = 'NORTH' AND tier >= 2` | Can be FALSE/UNKNOWN | Only when entire expression is TRUE |

**Important:** `NOT UNKNOWN` remains `UNKNOWN`, and does not become TRUE. This is why "everything except NORTH" selectors often **fail to catch messages missing the property**.

For example, when property `region` does not exist, an explicitly designed fallback selector might be:

```sql
region IS NULL OR region NOT IN ('NORTH', 'SOUTH')
```

It catches missing values and some other String values, **yet it is not a universal fix** for wrong-type data or provider-specific behavior. If routing metadata is untrusted, validate and split invalid-message flows at the producer or through a dedicated classification service with clear policies.

### 4.4. Allowed JMS headers and pitfalls

```sql
JMSPriority >= 7
JMSDeliveryMode = 'PERSISTENT'
JMSType = 'OrderCreated'
```

- `JMSPriority` is a number assigned by the provider per send QoS; not synonymous with a custom `priority` property.
- `JMSDeliveryMode` is represented **as a string** `'PERSISTENT'` or `'NON_PERSISTENT'` when used in selectors.
- `JMSType` is a specification header for message type; **it does not mean a JSON converter sets it automatically**.
- Only a subset of JMS standard headers can be referenced directly; do not generalize all `Message` getters into selector identifiers.
- For `JMSX...` properties, check support and semantics per JMS/provider; do not invent properties in reserved namespaces without reading the contract.

### 4.5. Changing a selector does not process old messages in one uniform way

On a **Queue**, if a new consumer with a matching selector is created, **pending** unexpired messages can become eligible for delivery; that does not mean the broker rewrites messages.

On a **Topic**, a subscription **cannot retroactively pull messages that were never added to it**. Changing a selector does not rewind time to create copies. With durable subscriptions there is also the risk of recreation and losing old state.

## 5. Calculating real load: total consumers alone do not tell capacity

To understand why adding more workers fails to drain queue backlog, examine **rates per message slice** rather than total thread count.

Suppose each hour queue `dispatch.jobs` receives:

- `650` messages with `region=NORTH`.
- `250` messages with `region=SOUTH`.
- `100` messages with `region=WEST`.

Assumed consumer capacity:

- North group can process at most `500` messages/hour.
- South group can process at most `400` messages/hour.
- No consumer matches `WEST`.

Simple assumptions: all messages are accepted by the broker, none expire, no discard policy runs, no redelivery/transactions add work, and no consumers exist outside the listed groups.

| Group | Arrivals/hour | Processing capacity/hour | Backlog growth/hour |
| --- | ---: | ---: | ---: |
| North | 650 | 500 | **150** |
| South | 250 | 400 | **0** (spare capacity remains) |
| West (no matching consumer) | 100 | 0 | **100** |
| Total | 1,000 | Max 900, but only 750 usable | **250** |

Here **South has 150 messages/hour of spare capacity**, yet cannot take North/West messages because its selector forbids it. Total consumers look healthy, while queue depth still grows by **250 messages/hour**. If conditions hold for two hours, backlog grows by roughly **500 messages** over baseline, ignoring the assumed factors.

A metric `consumerCount=10` does not say **which message types those 10 consumers accept**. You need to look at:

- Ingress rate per `region` property.
- Successful completion rate per selector/consumer group.
- Age of the oldest eligible message and oldest unmatched message.
- Pending counts, memory/disk quotas, and dropped/expired/dead-lettered counts per policy.
- Number of instances connected **and** eligible to process the backlogged group.

### 5.1. Simple model

For each segment `g`:

```text
arrivalRate[g]       = number of messages in group g arriving/sec
effectiveCapacity[g] = total actual throughput of consumers eligible for g
backlogGrowth[g]     ≈ max(0, arrivalRate[g] - effectiveCapacity[g])
```

This is an **approximate model**, not a broker guarantee. When selectors overlap, group capacities are **not independent**, so you cannot sum group capacities as if workers were dedicated. With retries, redeliveries, prefetch, TTL, priority, or bursty traffic, actual numbers differ.

### 5.2. Overlap complicates capacity planning

Example:

- Group A: `region = 'NORTH'`, capacity 100/s.
- Group B: `tier >= 3`, capacity 100/s.
- 60% of NORTH messages also have `tier >= 3`.

Both groups share **the same queue**. The broker can deliver overlapping messages to A or B; thus there is no default traffic split like "all NORTH to A, all VIP to B" and no promise both business functions run. If both independent tasks must happen, create **two Topic subscriptions** or an explicit routing step to duplicate work.

### 5.3. Ineligible backlog does not always block every eligible message

Do not treat "an unmatched message at the head of the queue always blocks the entire queue" as a JMS rule. Jakarta Messaging **does not require** all providers to implement identical scan, prefetch, or strict FIFO algorithms. One provider may skip past unmatched messages to deliver eligible ones; another may incur overhead or prioritization effects that increase latency.

Practical takeaway: measure **eligible message latency**, pending counts, and broker implementation behavior, rather than inferring throughput solely from a message's position in the queue.

## 6. How do stuck messages differ from retries, DLQ, and expiration?

A message lingering in a queue can have many causes, not always a selector.

| Symptom | How is a selector involved? | How to distinguish |
| --- | --- | --- |
| No consumer matches | **Direct cause** of pending messages | Property distribution, active selectors, test adding matching consumer |
| Matching consumer exists yet worker is slow | Selector segments capacity; backlog grows due to speed | Arrival vs. completion rate per group |
| Consumer stopped/disconnected | No active eligible consumer | Connection/container health, listener count |
| Selector property missing/wrong type | Condition evaluates FALSE/UNKNOWN | Inspect JMS properties, schema, and selector expression |
| Transaction uncommitted/unacked | Message may be pending/in-flight or redelivered | Transaction logs, delivery count, rollbacks |
| Message expired | TTL may remove message before matching consumer receives it | `JMSExpiration`, expired counters, broker expiry policy |
| Poison message causes rollback | Retry/redelivery and DLQ per policy | `JMSRedelivered`, retry count, DLQ |
| Prefetch holds messages at consumer | Messages may not appear "ready" in monitors | Provider pending/in-flight/prefetch metrics |
| Durable Topic consumer offline | Matched messages can accumulate in **subscription backlog** | Durable subscription pending count, selector identity |
| Topic selector excludes message | Message is not added to that subscription | Publish count vs. per-subscription accepted/matched |

**A selector is not a DLQ router.** An unmatched message on a queue is **not** a message that "failed delivery" because a handler threw. DLQ typically ties to redelivery/expiration/provider-specific routing policies; whether a broker has proprietary "unroutable message handling" is not a universal JMS selector guarantee.

**Expiration does not safely fix invalid business routing:** Expired messages can silently drop critical work. If the requirement is "every order must be processed," do not rely on a short TTL to dispose of an unmatched group.

### 6.1. Having no matching consumer throws no exception on the producer

A producer successfully sending to a queue does not guarantee an eligible consumer currently exists. `JmsTemplate.send`/`convertAndSend` typically only indicates the send satisfied API/provider requirements; it **does not wait for a matching consumer to process it**. Thus `"sent"` logs can keep appearing while the queue steadily accumulates `WEST` or property-less messages.

### 6.2. Why not fix it with an unfiltered consumer?

If you add an unfiltered "fallback" consumer on **the same queue**, that consumer is eligible for **every message**, including NORTH/SOUTH. It can steal work from the rightful groups and corrupt business logic or skew load distribution.

Better options:

- Fix producers so they only emit valid routes.
- Create a dedicated `dispatch.invalid` queue via an intentional validation step.
- Use explicit destination routing: separate queues per region or a router application.
- If inspecting stuck messages is needed, use admin management/`QueueBrowser` for **non-destructive** reads rather than an unfiltered worker accidentally acking messages.

## 7. Plain Jakarta JMS: creating a consumer with a selector

### 7.1. Classic API

Assuming a provider-supplied `jakarta.jms.ConnectionFactory` and an existing broker/queue `dispatch.jobs`:

```java
import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.Message;
import jakarta.jms.MessageConsumer;
import jakarta.jms.Queue;
import jakarta.jms.Session;

public final class SelectorQueueReceiver {

    private final ConnectionFactory connectionFactory;

    public SelectorQueueReceiver(ConnectionFactory connectionFactory) {
        this.connectionFactory = connectionFactory;
    }

    public void receiveNorthOnce() throws Exception {
        try (Connection connection = connectionFactory.createConnection()) {
            try (Session session =
                         connection.createSession(false, Session.AUTO_ACKNOWLEDGE)) {

                Queue queue = session.createQueue("dispatch.jobs");
                try (MessageConsumer consumer =
                             session.createConsumer(
                                     queue, "region = 'NORTH'")) {

                    connection.start();
                    Message message = consumer.receive(3_000L);

                    if (message == null) {
                        System.out.println("No NORTH message within timeout");
                    } else {
                        System.out.println(
                                "Received region=" +
                                message.getStringProperty("region"));
                    }
                }
            }
        }
    }
}
```

This is a **JMS integration class requiring a provider + Jakarta Messaging API**, not compilable with `javac` using only the JDK. `receive(3_000L)` waits up to about 3 seconds and returns null if no eligible message arrives; **it does not prove the queue is completely empty**. The queue could still hold hundreds of `WEST` messages or messages missing `region`.

`Session.createConsumer(queue, selector)` asks the provider to create a consumer with a filter. If the selector has invalid syntax, the provider can throw `InvalidSelectorException` (a checked `JMSException`). Do not mistake an invalid selector for "waiting forever with no messages" while ignoring startup exceptions.

**Session boundary:** Do not share one `Session` concurrently across arbitrary threads; create sessions/consumers per JMS rules or let a Spring listener container manage them.

### 7.2. Simplified JMSContext API

```java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSContext;
import jakarta.jms.JMSConsumer;
import jakarta.jms.Queue;

public final class SelectorContextReceiver {

    private final ConnectionFactory connectionFactory;

    public SelectorContextReceiver(ConnectionFactory connectionFactory) {
        this.connectionFactory = connectionFactory;
    }

    public String pollSouth() {
        try (JMSContext context = connectionFactory.createContext(
                JMSContext.AUTO_ACKNOWLEDGE)) {

            Queue queue = context.createQueue("dispatch.jobs");
            JMSConsumer consumer =
                    context.createConsumer(queue, "region = 'SOUTH'");

            try {
                return consumer.receiveBody(String.class, 2_000L);
            } finally {
                consumer.close();
            }
        }
    }
}
```

`receiveBody` returns `null` on timeout, and can throw a runtime exception if the body cannot be converted to `String` or the provider encounters an error. The simplified `JMSContext` defaults to `autoStart` when creating a consumer unless altered by the application; there is no need to call `context.start()` unnecessarily.

The number of `NORTH` messages in the queue does not cause `pollSouth()` to return `NORTH`; per API, it can only receive messages eligible for `SOUTH`.

### 7.3. Producer must set JMS properties, not just JSON fields

```java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSContext;
import jakarta.jms.Queue;
import jakarta.jms.TextMessage;

public final class SelectorPropertyPublisher {

    private final ConnectionFactory cf;

    public SelectorPropertyPublisher(ConnectionFactory cf) {
        this.cf = cf;
    }

    public void send(String id, String region, int tier)
            throws jakarta.jms.JMSException {
        try (JMSContext context = cf.createContext()) {
            Queue queue = context.createQueue("dispatch.jobs");

            TextMessage message = context.createTextMessage(id);
            message.setStringProperty("region", region);
            message.setIntProperty("tier", tier);

            context.createProducer().send(queue, message);
        }
    }
}
```

Integration example with a broker. To test an "unmatched message," you could send `region="WEST"`, though production should validate `region` against an allowlist before sending or have a valid WEST processing route.

**JMS property metadata** differs from fields inside the body; `TextMessage.getText()` here contains only the ID. When using a Spring/Jackson converter to produce a JSON body, you still must set JMS properties used by selectors via a message post-processor or appropriate header-mapping mechanism.

## 8. Spring JMS: @JmsListener(selector) and impact on worker groups

Spring Framework provides `@JmsListener(selector = "...")`. The annotation supplies a **JMS selector** for the listener endpoint; the container creates consumers with the selector instead of filtering after the listener has already pulled the message.

### 8.1. Two listeners on the same queue filtering by region

Assumes Spring Framework 6+ or 7+, Java 17+, `spring-jms` dependency, a Jakarta Messaging provider, a valid `ConnectionFactory`, and the `dispatch.jobs` queue. The example spans multiple files in a Spring project and does not run with plain JDK alone.

**File `DispatchJmsConfiguration.java`:**

```java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.core.JmsTemplate;

@Configuration
@EnableJms
public class DispatchJmsConfiguration {

    @Bean("dispatchSender")
    public JmsTemplate dispatchSender(ConnectionFactory cf) {
        JmsTemplate template = new JmsTemplate(cf);
        template.setPubSubDomain(false); // String -> Queue
        return template;
    }

    @Bean("dispatchListenerFactory")
    public DefaultJmsListenerContainerFactory dispatchListenerFactory(
            ConnectionFactory cf) {
        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(cf);
        factory.setPubSubDomain(false);
        factory.setSessionTransacted(true);
        factory.setConcurrency("1-4");
        return factory;
    }
}
```

`setSessionTransacted(true)` makes the local JMS listener transaction commit/rollback according to processing outcome; when the handler fails, the provider can redeliver. It **does not turn a selector into an exactly-once business processing mechanism**, nor does it automatically enlist a database transaction with JMS.

**File `DispatchPublisher.java`:**

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;

@Service
public class DispatchPublisher {
    private final JmsTemplate template;

    public DispatchPublisher(
            @Qualifier("dispatchSender") JmsTemplate template) {
        this.template = template;
    }

    public void dispatch(String jobId, String region) {
        template.send("dispatch.jobs", session -> {
            var message = session.createTextMessage(jobId);
            message.setStringProperty("region", region);
            return message;
        });
    }
}
```

Choosing `send(..., MessageCreator)` makes it clear where `setStringProperty("region", ...)` is called. With `convertAndSend`, you can use a `MessagePostProcessor` to attach properties after conversion. Do not expect Spring to turn a `region` field in a DTO into a JMS property for selectors automatically.

**File `NorthDispatchWorker.java`:**

```java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class NorthDispatchWorker {

    @JmsListener(
            destination = "dispatch.jobs",
            selector = "region = 'NORTH'",
            containerFactory = "dispatchListenerFactory",
            concurrency = "2-4")
    public void handle(String jobId) {
        System.out.println("NORTH handled " + jobId);
    }
}
```

**File `SouthDispatchWorker.java`:**

```java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class SouthDispatchWorker {

    @JmsListener(
            destination = "dispatch.jobs",
            selector = "region = 'SOUTH'",
            containerFactory = "dispatchListenerFactory",
            concurrency = "1-2")
    public void handle(String jobId) {
        System.out.println("SOUTH handled " + jobId);
    }
}
```

Both listeners share one **Queue**. `concurrency` adjusts the range of concurrent consumers for the listener container (as supported by provider/container), but **does not change the selector** and **does not create one copy per worker**.

When calling:

```java
publisher.dispatch("JOB-1", "NORTH");
publisher.dispatch("JOB-2", "SOUTH");
publisher.dispatch("JOB-3", "WEST");
```

If only these two listener types exist, the broker is running, the queue is valid, messages have not expired, and consumers are ready, you **may** see:

```text
NORTH handled JOB-1
SOUTH handled JOB-2
```

Log order is not guaranteed. `JOB-3` is **not processed by either handler**, because it does not match; it may sit in the queue, wait for a policy or a future matching consumer. **Do not infer that a successful `dispatch` means `JOB-3` was processed.**

### 8.2. What happens if North concurrency is increased?

Suppose North is scaled up to 8 instances:

- More `region=NORTH` messages can be processed if the bottleneck is on the consumer side.
- Does **not** increase capacity for taking `SOUTH` or `WEST`.
- If the broker is constrained by scanning/prefetch/quotas, adding threads may not raise throughput proportionally.
- For a single NORTH message, all 8 instances do not receive it; each delivery still goes to only one consumer.

If 95% of messages are SOUTH while most concurrency is allocated to NORTH, summing total threads can make dashboards look healthy while the SOUTH backlog continues growing.

### 8.3. Do not filter inside the handler if the goal is for the broker to keep messages for another group

Anti-pattern:

```java
@JmsListener(destination = "dispatch.jobs")
public void handle(String jobId) {
    if (!belongsToNorth(jobId)) {
        return;
    }
    processNorth(jobId);
}
```

This is **business pseudocode**, not an example with all methods to compile; its goal is to illustrate a design flaw. The unfiltered listener **already consumed the message**, and upon returning normally may ACK/commit it. Messages belonging to SOUTH can be removed from the queue without SouthWorker ever seeing them.

**Better:** use a selector on the JMS consumer when competing to handle specific types, or a broker/application router classifying messages into separate queues.

### 8.4. Selectors and destination types do not substitute for one another

`selector` works in both queue and topic domains. Spring must resolve the proper destination type, e.g., `factory.setPubSubDomain(false)` for queues and `true` for topics. If the producer sends to a Queue while the listener is configured for a Topic of the same name, writing a broader selector cannot fix it.

### 8.5. Static selectors and configuration updates

`@JmsListener(selector = "...")` is configured when the endpoint is registered. Changing the selector value in source/config may require the container to **stop and recreate consumers**; there is no guarantee of "hot-swapping" the expression of an existing consumer while keeping all in-flight messages intact.

For durable subscriptions on a Topic, changing a selector can even amount to **recreating the subscription** and affect the backlog. A rollout/migration procedure is needed, not merely deploying a new expression.

## 9. Spring: Topic example with two selectors and separate backlogs

Suppose Topic `orders.events` serves two responsibilities:

- Audit cares only about `kind = 'INVOICE'`.
- Metrics cares only about `amount >= 1000`.

First create a dedicated topic listener factory:

```java
@Bean("topicListenerFactory")
public DefaultJmsListenerContainerFactory topicListenerFactory(
        ConnectionFactory cf) {
    var factory = new DefaultJmsListenerContainerFactory();
    factory.setConnectionFactory(cf);
    factory.setPubSubDomain(true);
    factory.setSessionTransacted(true);
    return factory;
}
```

This is a **`@Bean` method inside a configuration class**, requiring the Spring/JMS imports from the previous config example and a provisioned topic on the broker. Not a standalone Java file.

**Audit Listener:**

```java
@JmsListener(
        destination = "orders.events",
        selector = "kind = 'INVOICE'",
        containerFactory = "topicListenerFactory")
public void auditInvoice(String payload) {
    // Process a matching copy of the Audit subscription.
}
```

**Metrics Listener:**

```java
@JmsListener(
        destination = "orders.events",
        selector = "amount >= 1000",
        containerFactory = "topicListenerFactory")
public void recordLargeOrder(String payload) {
    // Process a matching copy of the Metrics subscription.
}
```

Both methods are fragments inside valid Spring-managed components; they are **not the same listener**. The producer must set `kind` and `amount` properties on the JMS Message, not merely leave the amount in the JSON body. When the same event matches both selectors, the two independent subscriptions can receive **one copy each**. When an event does not match Audit, it **creates no Audit backlog**.

### 9.1. If durable backlog is needed for Audit

Conceptual setup with a durable subscription:

```java
@Bean("durableAuditTopicFactory")
public DefaultJmsListenerContainerFactory durableAuditTopicFactory(
        ConnectionFactory cf) {
    var factory = new DefaultJmsListenerContainerFactory();
    factory.setConnectionFactory(cf);
    factory.setPubSubDomain(true);
    factory.setSubscriptionDurable(true);
    factory.setClientId("audit-service");
    factory.setConcurrency("1");
    factory.setSessionTransacted(true);
    return factory;
}
```

```java
@JmsListener(
        destination = "orders.events",
        selector = "kind = 'INVOICE'",
        subscription = "audit-invoices-v1",
        containerFactory = "durableAuditTopicFactory")
public void durableAudit(String event) {
    // Only matched events can enter the durable backlog.
}
```

These are config snippets in a Spring project; distinguish **unshared durable** from **shared durable** per provider and identity rules. Do not run multiple replicas sharing an unshared client ID like a queue worker group. To scale multiple consumers for **the same durable subscription**, check shared durable support, subscription identity, and corresponding `subscriptionShared` configuration; do not create multiple independent subscriptions expecting to avoid duplication.

**When the audit service is offline:** matched events can enter the durable subscription's backlog (subject to expiration, delivery, and broker policies); unmatched events do not "wait for the service to change its filter."

## 10. Standalone Java 17: clearly observing pending items after filtering

A plain JDK 17 runnable example, **simulating queue semantics** using a list. It shows that when workers take only matching items, other items remain pending. This is **not a JMS/broker implementation**: there are no transactions, acknowledgments, prefetch, priority, expiration, network, or concurrency.

Create file **`SelectorBacklogDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;

public final class SelectorBacklogDemo {
    record Task(String id, String region) {}

    static List<Task> consumeMatching(List<Task> pending, String region) {
        List<Task> received = new ArrayList<>();

        for (Iterator<Task> iterator = pending.iterator();
                iterator.hasNext();) {

            Task task = iterator.next();
            if (region.equals(task.region())) {
                received.add(task);
                iterator.remove();
            }
        }
        return received;
    }

    static String ids(List<Task> tasks) {
        return tasks.stream().map(Task::id).toList().toString();
    }

    public static void main(String[] args) {
        List<Task> queue = new ArrayList<>(List.of(
                new Task("N-1", "NORTH"),
                new Task("W-1", "WEST"),
                new Task("S-1", "SOUTH"),
                new Task("N-2", "NORTH"),
                new Task("M-1", null)
        ));

        List<Task> north = consumeMatching(queue, "NORTH");
        List<Task> south = consumeMatching(queue, "SOUTH");

        System.out.println("NORTH consumed: " + ids(north));
        System.out.println("SOUTH consumed: " + ids(south));
        System.out.println("Queue pending: " + ids(queue));

        List<Task> west = consumeMatching(queue, "WEST");
        System.out.println("WEST consumed: " + ids(west));
        System.out.println("Queue pending after WEST: " + ids(queue));
    }
}
```

Run:

```bash
javac SelectorBacklogDemo.java
java SelectorBacklogDemo
```

**Exact stdout:**

```text
NORTH consumed: [N-1, N-2]
SOUTH consumed: [S-1]
Queue pending: [W-1, M-1]
WEST consumed: [W-1]
Queue pending after WEST: [M-1]
```

Explanation:

- Both North/South groups finish processing their eligible slices.
- `W-1` and `M-1` remain in the simulated queue; no logic automatically moves them to a DLQ.
- After adding a West consumer, `W-1` can be picked up. `M-1` missing `region` remains pending.
- In real JMS, a message missing the `region` property is handled per **SQL NULL semantics**, not Java's `Task.region == null`; the plain Java example only simulates equality selector results.
- List traversal here runs sequentially, so stdout has a fixed order; on a real broker with multiple consumers, do not infer processing order or which worker receives a message from this demo.

### 10.1. Extending the mental model for overlapping selectors

If `South` is replaced by a consumer with condition `tier >= 3` and a NORTH message also has tier 3, the simulation must pick **one** of the two consumers to take that message, rather than copying it into two. If the problem requires both NorthHandler and VipHandler to process it, add an event fan-out/subscription abstraction.

### 10.2. Extending the mental model for Topics

For a Topic, instead of one shared queue list, each subscription gets an **independent pending list containing only events matching its selector**. An event matching two subs is copied into both lists. An event not matching a sub is never added to that list; no item waits for a sub to change its selector.

## 11. When are selectors appropriate, and when should queues be split?

### Keep one queue, multiple selectors when:

- The number of groups is small, relatively stable, and routing metadata is validated.
- Groups share the same logical work stream but split responsibility by partition.
- Broker matching/dispatch performance is adequate for current backlog/traffic.
- Metrics and a runbook exist for unmatched messages.
- If consumer overlap occurs, all consumers are allowed to perform **the same business action**; no multi-business fan-out is needed.

### Create separate queues per group when:

- Groups have clearly different SLOs, capacities, or retry/DLQ requirements.
- There is a risk of a shared queue accumulating many messages with no matching consumer.
- You want to measure pending/oldest age and scale workers **per group** easily.
- Permissions, tenant isolation, quotas, or compliance require separation.
- The broker incurs high scan/prefetch overhead with many complex selectors.
- You want to deploy group A without overly affecting group B's backlog.

Example:

```text
Producer / router
   |
   +-- dispatch.north.jobs --> North workers
   |
   +-- dispatch.south.jobs --> South workers
   |
   +-- dispatch.invalid    --> triage / alert / remediation
```

Splitting queues shifts routing to the producer/router side, **without eliminating the need for validation**. Misrouting can send messages to the wrong queue and still create backlogs. Adding queues also increases administrative overhead; weigh traffic volume, topology, and broker policies.

### Use a Topic with multiple subscriptions when:

- One event needs multiple independent services to all receive and process it.
- Each subscription has its own selector and needs independent backlog control.
- Offline subscribers need to catch up on events → durable subscription fits.
- One group needs to scale workers consuming **the same subscription** → shared subscription, if supported by the provider and configured properly.

**Do not solve a fan-out problem with two consumers having overlapping selectors on a queue.** That is still competing consumers.

## 12. Runbook: queue backlog grows while workers stay "healthy"

To find the root cause, follow this sequence.

### Step 1 — Confirm source and destination

- Destination name, Queue/Topic type, provider namespace/vhost.
- Where the producer sends, and whether queue/topic was misresolved due to `pubSubDomain`.
- When queue depth/ready count/in-flight count began rising.
- Whether the consumer count is actually on the **right destination**.

### Step 2 — Collect active selectors

- Which selector each listener/container has, and which config version.
- Whether any consumers are missing after a rollout or crash.
- Whether an empty default selector (matching everything) is accidentally competing for messages.
- Whether two overlapping selectors are skewing load distribution unexpectedly.
- For Topics, inspect **subscription identity** and the selector on the subscription, not just the topic name.

### Step 3 — Inspect metadata of pending messages

Sample messages via the broker console, admin API, or `QueueBrowser` if appropriate:

- JMS property names: `region` or `Region`?
- JMS property types: int vs. String, boolean vs. String?
- Values: `NORTH`, `SOUTH`, `WEST`, null/missing?
- Have messages expired or do they have a delivery delay?
- JMSPriority, transactions, ack/redelivery, and pending/in-flight state?

**Do not use an unfiltered consumer just to "peek"** if it might ACK valid messages. Use a non-consuming browse/management path. JMS `QueueBrowser` can view messages without removing them, though whether the browser sees a full queue snapshot, pagination, and scan cost depend on the provider and workload; avoid scanning millions of messages unboundedly.

### Step 4 — Identify which group is unmatched

Build a table:

| Message category | Matching consumers | Incoming rate | Completion rate | Oldest age |
| --- | ---: | ---: | ---: | --- |
| NORTH | 4 | ... | ... | ... |
| SOUTH | 2 | ... | ... | ... |
| WEST | 0 | ... | 0 | ... |
| Missing/invalid | 0 | ... | 0 | ... |

In the example, "WEST: zero matching consumers" is a far more important finding than "6 consumers connected." The JMS API **does not standardize an API to count pending messages per selector** across all brokers; you may need broker management, sampling, or application-level observability.

### Step 5 — Classify corrective actions

- **Missing valid worker:** increase capacity for the right selector or create a new worker matching the business contract.
- **Producer sending wrong region:** fix validation/routing, establish a controlled policy for handling already backlogged messages.
- **Selector comparing wrong type:** standardize JMS property setters and test compatibility.
- **Architecturally wrong overlap:** split queues/Topic subscriptions instead of relying on how the broker races messages.
- **Consumer too slow:** profile business I/O, DB locks, transaction latency, prefetch, and concurrency per provider.
- **Consistently malformed payloads:** poison-message retry/DLQ mechanisms, never broadening selectors to swallow schema errors.
- **Broker quota nearly full:** alert/scale storage or process backlog per business rules; never delete messages indiscriminately.
- **Durable Topic with wrong selector:** fix via a subscription migration plan, watching state/backlog and event-loss risks.

### Step 6 — Monitor after fixing

Verify that queue depth and **oldest age** decrease as expected; count completed business IDs, avoiding duplicate side effects; confirm no unfiltered consumer was left behind stealing another group's messages. For Topics, measure **subscription backlog** per sub rather than just publish throughput.

## 13. Required integration tests

### Test A — Queue: unmatched messages remain

1. Provision `dispatch.jobs` in the test environment.
2. Start only North/South listeners with selectors.
3. Send `NORTH`, `SOUTH`, `WEST`, and a message missing `region`.
4. Verify North/South process only messages belonging to their groups.
5. Check that `WEST` and missing remain pending (assuming no other TTL/expiry/cleanup policy).
6. Start a matching West consumer and verify it can process the pending WEST message.

### Test B — Overlapping selectors on Queue

1. Worker A: `region='NORTH'`.
2. Worker B: `tier >= 3`.
3. Send message `region=NORTH,tier=3` with a business ID.
4. Verify it is **not fanned out to both** because it is a queue; one consumer per delivery.
5. Intentionally roll back to observe that redelivery can occur, confirming business idempotency must be separate.

### Test C — NULL/type/case

1. Send a message missing `region`, then property `Region` (capital R), then `region='north'`.
2. Compare against selector `region = 'NORTH'`.
3. Verify only the message with exact name/case/value matches.
4. Test `region IS NULL` and verify messages missing the property are selected.
5. Send `tier` via `setStringProperty("tier", "3")` and `setIntProperty("tier",3)`; verify `tier >= 2` matches only the numeric property per spec.
6. Test an invalid expression; observe startup `InvalidSelectorException`/appropriate runtime exception.

### Test D — Topic subscriptions

1. Create two separate subscriptions with corresponding selectors.
2. Publish E1 matching both, E2 matching only one, E3 matching neither.
3. Verify copies per subscription, without assuming "E2 is still waiting in every subscription."
4. For durable subs, stop the consumer, publish a matched event, restart with the same identity; check backlog per delivery/expiration policy.
5. Change the durable selector on a test subscription and verify provider recreate/migration semantics; **never do this in production while unprocessed events exist**.

### Test E — Backlog and scaling

1. Generate North load > North capacity, South < South capacity, plus an unmatched WEST portion.
2. Monitor per-group backlog, throughput, and oldest message age.
3. Increase North concurrency; verify only the eligible North slice increases throughput.
4. Add a West worker; verify West pending drops.
5. Compare against splitting into `north`/`south`/`invalid` queues for isolation and metrics.

### Test F — Expiration, redelivery, and DLQ

1. Send a `WEST` message with a defined TTL to a queue with no West consumer.
2. Observe the broker handling the expired message per policy (do not infer automatic DLQ from selector).
3. Send NORTH, intentionally throw inside handler, track rollback/redelivery.
4. Verify the distinction between an **ineligible** message and an **eligible message that failed processing** in logs, counters, and DLQ.
5. Use business IDs to verify no duplicate side effects occur on redelivery.

## 14. Common mental-model pitfalls

**Pitfall 1 — "Messages not matching a selector are immediately dropped."**  
False on a Queue under general semantics. They can remain waiting or be taken by another consumer. On a Topic, unmatched messages **are not added to that subscription**.

**Pitfall 2 — "Both selectors match, so both queue workers receive it."**  
False. A Queue uses competing consumers; per delivery only one consumer receives it.

**Pitfall 3 — "Increasing total concurrency will clear the backlog."**  
Not if the backlogged messages belong to a group with no matching consumer or a group whose capacity was not increased.

**Pitfall 4 — "No match makes JMS automatically push to DLQ."**  
No such guarantee exists. DLQ/expiry/unroutable behavior is a separate policy, depending on the provider.

**Pitfall 5 — "region in JSON is enough for a JMS selector."**  
No. Standard selectors do not read the body; an appropriate JMS property/header must be set.

**Pitfall 6 — "region <> 'NORTH' will catch missing region."**  
False. Missing properties evaluate to UNKNOWN; handle `IS NULL` explicitly if needed.

**Pitfall 7 — "setStringProperty('tier','3') is the same as setIntProperty('tier',3)."**  
False. Property types differ; numeric comparisons in selectors do not auto-parse Strings.

**Pitfall 8 — "An unfiltered consumer only receives the leftovers after selector consumers."**  
False. An unfiltered consumer is eligible to receive any message; it can steal work from other groups.

**Pitfall 9 — "Selectors make the broker route like a fixed priority function."**  
False. Selectors only determine eligibility; the broker distributes among eligible consumers per semantics and policy.

**Pitfall 10 — "High queue backlog proves all workers are busy."**  
False. Valid workers may be idle while pending messages belong to another/invalid group. Measure by category.

**Pitfall 11 — "An unmatched topic selector message will wait until the subscriber changes its condition."**  
False. The message is not added to that subscription; there is no standard retroactive replay simply by changing a selector.

**Pitfall 12 — "Changing a durable selector does not affect existing pending messages."**  
Do not assume so. Changing a selector can amount to recreating the subscription and losing pending state; migration is required.

**Pitfall 13 — "Filtering in the listener after receiving is equivalent to a JMS selector."**  
No. The listener may have already consumed/acked the message before returning; that deprives other groups of any chance to receive it.

**Pitfall 14 — "High priority lets a message bypass selector matching."**  
False. QoS priority does not bypass filters: a consumer is only delivered eligible messages.

**Pitfall 15 — "Having active consumers means consumers match all messages."**  
False. Consumer count does not reveal actual selector coverage.

**Pitfall 16 — "No message received in 3 seconds means the queue is empty."**  
False. `receive(timeout)` with a selector can time out even while the queue holds many non-matching messages.

**Pitfall 17 — "Adding more topic subscribers always speeds up the same task."**  
False if each subscriber is an independent subscription: it creates extra copies of work. To share load within one subscription, use a shared subscription where appropriate.

## 15. Pre-deployment selector design checklist

- [ ] **Right semantics chosen:** queue competing work or topic fan-out?
- [ ] **Routing properties defined:** names, types, valid values, default/null handling, and versioning.
- [ ] **Producer verified:** sets actual JMS properties, not only serializing fields into JSON.
- [ ] **Selector checked:** SQL92-subset syntax, case-sensitive identifiers, TRUE/FALSE/UNKNOWN, and precedence.
- [ ] **Group coverage:** does every valid message have at least one capable consumer?
- [ ] **Overlap:** can a message match multiple queue consumers; would that break business effects?
- [ ] **Invalid handling:** do not send to a shared queue without a responsible consumer; have validation/invalid queue/triage.
- [ ] **Per-group capacity calculated:** separate arrival rates, service times, concurrency, and backlog growth.
- [ ] **Broker protection:** quotas, TTL, retention, DLQ, and resources when unmatched messages accumulate.
- [ ] **Message age tracked:** not just total queue depth; track oldest age and consumer idle/busy per group.
- [ ] **Prefetch/priority:** provider-specific interactions tested, not assuming strict FIFO/head-of-line.
- [ ] **Listener factory:** `pubSubDomain`, selector, concurrency, transactions, and redelivery configured properly.
- [ ] **Topic subscription:** durable/non-durable, shared/unshared, identity, and selectors clearly specified.
- [ ] **Rollout:** changing selectors/topic subs has a migration/backlog plan, without silently resetting durable state.
- [ ] **Failure tests:** receive timeout, missing property, wrong type, invalid expression, stopped consumer, dead-letter, expiration.
- [ ] **Idempotency:** business IDs and deduplication when messages are redelivered.
- [ ] **Security:** JMS properties from untrusted producers are never treated as authorization; enforce auth and ACLs at the broker.
- [ ] **End-to-end tests:** measure producer accepted, broker pending, matched deliveries, and completed business actions.

## 16. Knowledge self-check

**Question 1.** Two consumers on the same queue have selectors `region='NORTH'` and `region='SOUTH'`. A message has property `region='WEST'`. Under JMS, what can happen?

**Answer:** Neither consumer is eligible. The message can remain in the queue until an eligible consumer arrives or expiry/management policies take effect; it does not automatically go to DLQ merely for not matching.

**Question 2.** Two Queue consumers have overlapping selectors that both match a message. Does each get a copy?

**Answer:** No. On a Queue, each delivery goes to only one consumer. Redelivery can happen after rollback/ack failure, which is not business fan-out.

**Question 3.** The body contains JSON `{"region":"NORTH"}`, and JMS property `region` does not exist. Does selector `region='NORTH'` match?

**Answer:** No. Selectors do not read JSON bodies; missing properties lead to UNKNOWN/no match.

**Question 4.** Why does adding NORTH workers not reduce the WEST backlog?

**Answer:** All NORTH workers have selectors accepting only NORTH; WEST is not eligible. Adding capacity to the wrong group does not help.

**Question 5.** Does `region <> 'NORTH'` catch a missing `region` property?

**Answer:** No, because comparing against NULL yields UNKNOWN; `region IS NULL` is needed if missing values should be caught.

**Question 6.** `tier` is set as String `"3"`; does selector `tier >= 2` auto-cast it to a number?

**Answer:** You must not rely on automatic String→numeric conversion. Use `setIntProperty("tier",3)` and test the schema properly.

**Question 7.** An unfiltered consumer is added to a queue that already has North/South selectors. Does it receive only WEST?

**Answer:** No. It is eligible for all messages and can steal NORTH/SOUTH messages.

**Question 8.** A Topic has an Audit subscription with selector `kind='INVOICE'` and Metrics with selector `amount>=1000`. How is an event matching both handled?

**Answer:** Each independent subscription can receive a copy. Acknowledgments/commits are independent.

**Question 9.** Does a message not matching a durable subscription's selector wait inside that subscription's backlog?

**Answer:** No. The selector determines which messages are added to the subscription; if it does not match, no copy is created.

**Question 10.** What operation can changing an unshared durable subscription's selector with the same identity and no active consumer be equivalent to?

**Answer:** According to Jakarta Messaging, changing topic/selector/noLocal can be equivalent to deleting the old subscription and creating a new one; backlog protection/migration is required.

**Question 11.** Does `@JmsListener(selector="region='NORTH'")` filter before or after the Spring method receives the message?

**Answer:** The JMS provider/consumer applies the filter before delivering eligible messages to the listener. Unlike an `if` followed by `return` inside the handler.

**Question 12.** Queue depth is high, South consumers are idle, and North is processing at full capacity. Why?

**Answer:** Selectors segment eligibility; South is not permitted to take North messages; North capacity must be scaled or routing architecture changed.

**Question 13.** `receive(3000)` on the North consumer returns null—so the queue is definitely empty?

**Answer:** No. The queue may contain all SOUTH/WEST/missing messages, or messages ineligible due to other conditions.

**Question 14.** Can a selector arbitrarily reference `JMSExpiration` or `JMSDestination` in standard JMS?

**Answer:** No. The list of standard header fields usable in selectors is restricted; use a valid application property if custom metadata is needed.

**Question 15.** On a Topic, do two consumers sharing a **shared durable subscription** each receive every matched event?

**Answer:** No. They share the messages of **one subscription**; each message in the subscription is delivered to one consumer in the group per delivery.

**Question 16.** Does a message with no matching consumer on a queue go to DLQ by default?

**Answer:** There is no universal guarantee; DLQ depends on provider retry/expiry/unroutable policies. Unmatched does not mean failed processing.

**Question 17.** Which metrics help identify backlog caused by having no matching consumer?

**Answer:** Pending/oldest age by category, property sampling, active selectors, matching consumer counts, arrival/completion rates, broker pending/in-flight/expired counters; looking only at total consumer count is insufficient.

**Question 18.** When should you choose multiple queues instead of one queue with multiple selectors?

**Answer:** When separate isolation/capacity/retention/ACL/metrics/SLAs are needed, selector coverage is hard to control, or the broker performs poorly with many unmatched/complex selectors.

## Key takeaways

- **Selectors govern eligibility, not automatic load balancing.** On a Queue, multiple matching consumers compete for **one** message; if none match, the message can remain.
- **Queue backlog can grow even when consumers are healthy** if capacity is skewed across groups, selectors do not cover all messages, properties have wrong types/casing, or no eligible consumer exists.
- **Topic selectors operate per subscription**: only matched messages are added to each subscription; non-matching events do not wait inside the subscription to be read later.
- **Durable subscriptions retain only messages matching their selector** per delivery/expiry rules; modifying a selector can alter or recreate subscription state.
- **JMS selectors do not read the body**; use appropriate JMS properties/headers, the SQL92-subset, and three-valued logic (`TRUE`/`FALSE`/`UNKNOWN`).
- **Spring `@JmsListener(selector)` is server/provider-side eligibility**, unlike filtering after the handler has ACKed the message.
- **Measure by group**, not just total queue depth or consumer count; design fallbacks, invalid routing, observability, and queue separation when needed.

### Official references

1. [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html) — sections `3.8 Message selection`, `4.1.2 Queue semantics`, `4.2.2 Topic semantics`, `8.2`, and `8.3` (durable/shared subscriptions).
2. [Jakarta Messaging 3.1 — Message API](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/message) — property types, SQL92-subset selectors, NULL/UNKNOWN, and allowed standard headers.
3. [Jakarta Messaging 3.1 — Session API](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/session) — `createConsumer(destination, selector)` and durable consumer APIs.
4. [Jakarta Messaging 3.1 — JMSContext API](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/jmscontext) — `createConsumer(destination, selector)` in simplified JMS.
5. [Spring Framework — @JmsListener Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/annotation/JmsListener.html) — `selector`, `destination`, `containerFactory`, `subscription`, and `concurrency`.
6. [Spring Framework — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html) — listener factory, `@EnableJms`, container lifecycle, and method arguments.
7. [Spring Framework — Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html) — destination resolution, queue/topic domain, listener containers, and session transactions.
