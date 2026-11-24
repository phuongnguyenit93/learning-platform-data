# Distinguishing Producer, Provider, and Application Defaults When Sending JMS

> **Module:** Spring Framework – JMS  
> **Group:** Delivery Quality  
> **Goal:** Know exactly where QoS settings come from, which defaults Jakarta Messaging mandates, which settings Spring actually passes to the producer, and which policies the broker/provider may ultimately apply.

## What Will You Learn?

1. Distinguish the three layers—**producer**, **provider/broker**, and **Spring application**—when determining delivery mode, priority, time-to-live (TTL), and delivery delay.
2. Remember the exact Jakarta Messaging specification defaults without mistaking them for infinite broker retention policies.
3. Understand the difference between `MessageProducer.send(message)` using producer defaults, `send(message, mode, priority, ttl)` specifying QoS for that send, and `JMSProducer.setDeliveryMode(...).setPriority(...).setTimeToLive(...)`.
4. Explain why `JmsTemplate.setPriority(8)` **may not** give messages priority 8 if `setExplicitQosEnabled(true)` has not been enabled.
5. Know an important exception: some providers allow **administrative configurations to override even client-requested QoS values**; outcomes must be verified through headers and provider settings.
6. Properly read `JMSDeliveryMode`, `JMSPriority`, `JMSExpiration`, and `JMSDeliveryTime` after sending or at the consumer; avoid setting provider-managed headers via `Message` setters.
7. Configure stable `JmsTemplate` beans in Spring, write broker-backed tests, anticipate scenarios where TTL is smaller than delivery delay, and build safe application policies.

## 1. Why Does Saying "Default" Often Cause Confusion?

The statement "JMS defaults to persistent, priority 4, no expiration" describes **the producer defaults per Jakarta Messaging**, which is not enough to assert that every production message carries those exact headers.

There are at least three layers:

- **Producer/API:** `MessageProducer` or `JMSProducer` has specification-defined default properties. When developers mutate them or call an explicit-QoS send overload, the client supplies a specific request.
- **Provider/broker:** the Jakarta Messaging implementation, `ConnectionFactory` configuration, destination, address/routing, permissions, quotas, and administrative policies. A provider may configure different defaults in certain setups, and **the specification permits an administrative override mechanism** for some headers; not every provider supports it.
- **Application/framework:** business policies, `JmsTemplate` beans, `MessageCreator`/`MessageConverter`, per-event TTL rules, and retry/idempotency requirements. The framework decides whether to **actively pass** QoS into the send call or let the producer/provider use defaults.

```text
                   APPLICATION / SPRING
          business policy, JmsTemplate config
                       |
             explicitQoS = false/true?
                       |
                       v
                   JMS PRODUCER
    producer defaults or send(mode, priority, ttl)
                       |
                       v
                   JMS PROVIDER
         ConnectionFactory/admin configuration
            optional QoS administrative override
                       |
                       v
            ACTUAL JMS HEADERS + BROKER
         retention/quota/expiry/routing/permissions
                       |
                       v
                     CONSUMER
```

**There is no universal fixed precedence rule across all providers** like "application always beats provider" or "broker always beats client." The specification defines default values, how clients request QoS, and administrative override rights; support for admin overrides and specific policies depend on the provider.

To debug properly, specify which question you are asking:

1. **What are the API specification defaults?**
2. **What values does the actual producer object currently hold?**
3. **Is Spring passing its own values during the send call?**
4. **Is the provider imposing an administrative configuration on the message?**
5. **What are the headers on the message after send / at actual receive?**
6. **Does the destination have retention and failure policies that can still drop/expire the message?**

Answering only question 1 and jumping to conclusions about question 6 is a mistake.

## 2. Standard Table: Producer Defaults per Jakarta Messaging

Per the Jakarta Messaging API, the baseline defaults are:

| Component | JMS Default Value | Exact Meaning |
| --- | --- | --- |
| Delivery mode | `DeliveryMode.PERSISTENT` (int value `2`) | Provider must apply persistent transport protection per the spec |
| Priority | `4` | Normal priority level on a scale from `0` (lowest) to `9` (highest) |
| Time-to-live | `0` milliseconds | No TTL-based expiration deadline; `JMSExpiration=0` if unoverridden |
| Delivery delay | `0` milliseconds | Message is not requested to delay delivery to consumers |
| Message ID generation | Enabled by default | Provider normally assigns `JMSMessageID` at send time |
| Message timestamp generation | Enabled by default | Provider normally assigns `JMSTimestamp` at send time |

Four constants in `jakarta.jms.Message` can be referenced:

```java
Message.DEFAULT_DELIVERY_MODE    // PERSISTENT
Message.DEFAULT_PRIORITY         // 4
Message.DEFAULT_TIME_TO_LIVE     // 0L
Message.DEFAULT_DELIVERY_DELAY   // 0L
```

**JMS defaults are not a promise that the broker always has reliable resources, keeps every message forever, or reaches every subscriber.** Messages remain subject to overridden TTL, quotas, destination policies, failures, transactions, durable subscriptions, and consumer handling.

### 2.1. PERSISTENT Does Not Mean Business Exactly-Once

`DeliveryMode.PERSISTENT` requests the provider to protect the message better during delivery than `NON_PERSISTENT`; it does not mean:

- The consumer is guaranteed to complete business processing successfully.
- The message can never be deleted by storage limits, retention policies, or expiration.
- An offline non-durable topic subscriber will have missed events replayed.
- A task can never run twice upon transaction rollback or redelivery.
- JMS sending and database writing automatically form an atomic transaction.

The specification separates responsibility for **delivering the message to the destination** from **retention policies at the destination until acknowledged**. Brokers can enforce their own quotas, dead-lettering, and retention. Despite JMS delivery rules, business systems still require idempotency when redeliveries, restarts, or client retries occur after an ambiguous send outcome.

### 2.2. Priority 4 and the 0–9 Scale

- Priorities `0..4` are the normal group; `5..9` are the higher-priority group.
- High priority **is not strict FIFO** and does not force the provider to enforce strict priority ordering.
- With multiple queue consumers, selectors, transactions, or redeliveries, never infer system-wide processing order solely from `JMSPriority`.
- If an application assigns priority 9 to every message, tiering loses meaning and lower-priority messages may starve.

Use priority as a **relative urgency hint** backed by broker-tested policies and metrics, not as a processing-time SLA guarantee.

### 2.3. TTL = 0 Does Not Mean Infinite Broker Retention

TTL is how long a message is allowed to live under JMS expiration mechanics. `0` means **does not expire by TTL**, not "keep forever regardless of quotas, policies, destination rules, or broker crashes."

When TTL > 0, the provider computes `JMSExpiration` from send time and TTL. The unit is **milliseconds**. For example, `60_000L` = 60 seconds, not 60 minutes.

Once expired, the provider **must not deliver** that message as though it were still valid. How messages are discarded, logged, or routed to an expired-message address depends on the provider. If a sender claims "the message never expires" simply because it called `setTimeToLive(0)` while an admin override enforces a 20-second TTL, the actual received header will differ.

### 2.4. Delay = 0 Differs from TTL = 0

Delivery delay states **the earliest time delivery is permitted**; TTL states **when it expires**:

```text
send time: t0
  |
  +--- deliveryDelay = 5s ---> earliest delivery at t0 + 5s
  |
  +--- timeToLive   = 3s ---> expires at t0 + 3s
```

In this example, the message **can expire before it even becomes eligible for delivery**. Delay and TTL must be chosen together, especially for delayed jobs, retry schedules, or waiting workflows.

For reliable delayed dispatch, examine TTL, backlog, provider delay support, clock skew, and retention policies; setting delay alone does not guarantee delivery at the exact specified instant.

## 3. Defaults and Overrides in Classic JMS MessageProducer

`jakarta.jms.MessageProducer` provides setters:

```java
producer.setDeliveryMode(DeliveryMode.PERSISTENT);
producer.setPriority(7);
producer.setTimeToLive(45_000L);
producer.setDeliveryDelay(2_000L);
```

These setters update the **producer's** configuration. Calling `producer.send(message)` uses the producer/default QoS applicable to that send, subject to valid override policies. Calling `send(message, mode, priority, ttl)` specifies those three values **for that specific send**, instead of reading the producer's three defaults.

### 3.1. Producer Defaults

```java
// session and destination are valid Jakarta Messaging objects.
MessageProducer producer = session.createProducer(destination);
try {
    producer.setDeliveryMode(DeliveryMode.NON_PERSISTENT);
    producer.setPriority(6);
    producer.setTimeToLive(20_000L);

    TextMessage a = session.createTextMessage("A");
    TextMessage b = session.createTextMessage("B");

    producer.send(a); // Requests producer defaults: NP / 6 / 20s
    producer.send(b); // Same producer defaults
} finally {
    producer.close();
}
```

This is an application snippet that already has a `jakarta.jms.Session` and provider; it **cannot run on plain JDK alone**. The provider may still enforce an admin override. Never call `Message` getters **before send** to infer final send values: several headers are written by the provider at send time.

### 3.2. Overriding All Three QoS Values for a Single Send

```java
MessageProducer producer = session.createProducer(destination);
try {
    producer.setDeliveryMode(DeliveryMode.PERSISTENT);
    producer.setPriority(4);
    producer.setTimeToLive(0L);

    TextMessage urgent = session.createTextMessage("URGENT");
    producer.send(
            urgent,
            DeliveryMode.PERSISTENT,
            9,
            5_000L
    ); // Requests explicit QoS specifically for "URGENT"

    TextMessage normal = session.createTextMessage("NORMAL");
    producer.send(normal); // Reverts to producer defaults: P / 4 / 0
} finally {
    producer.close();
}
```

**Key distinction:** explicit per-send QoS does not permanently overwrite producer defaults. A subsequent `send(message)` reverts to producer state. Delivery delay, if used, is a producer setting (or the equivalent method in the simplified API), not a fourth QoS argument on `send(message, mode, priority, ttl)`.

### 3.3. Identifying Provider-Managed Message Headers

After a successful synchronous send, you can inspect:

```java
System.out.println("mode=" + urgent.getJMSDeliveryMode());
System.out.println("priority=" + urgent.getJMSPriority());
System.out.println("expiration=" + urgent.getJMSExpiration());
System.out.println("deliveryTime=" + urgent.getJMSDeliveryTime());
```

Actual printed values **depend on the provider, admin overrides, and send timestamp**, so no fixed stdout can be stated. In async sends, provider-assigned headers are safe to read only after the completion callback per the specification.

**Do not do this to "configure QoS":**

```java
// WRONG PURPOSE: these header setters are not client APIs
// for deciding send-time QoS.
message.setJMSPriority(9);
message.setJMSDeliveryMode(DeliveryMode.PERSISTENT);
message.setJMSExpiration(System.currentTimeMillis() + 60_000);
```

These setters on `Message` exist for the provider to populate headers; when the message is sent, client-supplied values in provider-managed headers are ignored/overwritten. To configure QoS, use **producer setters**, the `send` overload, or Spring settings that actually pass parameters to the producer.

## 4. Simplified JMS API: JMSProducer Holds Its Own State

Since JMS 2.0/Jakarta Messaging, `JMSContext` and `JMSProducer` reduce boilerplate:

```java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSContext;
import jakarta.jms.JMSProducer;
import jakarta.jms.Queue;

public final class QosJmsProducer {
    private final ConnectionFactory connectionFactory;

    public QosJmsProducer(ConnectionFactory connectionFactory) {
        this.connectionFactory = connectionFactory;
    }

    public void publish() {
        try (JMSContext context =
                     connectionFactory.createContext(JMSContext.AUTO_ACKNOWLEDGE)) {

            Queue queue = context.createQueue("billing.jobs");

            JMSProducer producer = context.createProducer()
                    .setDeliveryMode(DeliveryMode.PERSISTENT)
                    .setPriority(8)
                    .setTimeToLive(30_000L)
                    .setDeliveryDelay(1_000L);

            producer.send(queue, "INV-42");
        }
    }
}
```

This is a **Java class for a project with Jakarta Messaging API/provider/broker**; it cannot be run with plain JDK 17 `javac` alone. Before sending, a valid queue resource or provider auto-creation must exist; `createQueue(String)` creates an object handle, not a portable API for provisioning physical broker queues.

Characteristics:

- `JMSProducer` holds its own delivery mode, priority, TTL, and delay.
- `send(Destination, body)` sends with the producer's configuration at call time, subject to provider-supported administrative policies.
- `JMSProducer` provides getters like `getDeliveryMode()`, `getPriority()`, `getTimeToLive()`, and `getDeliveryDelay()` to inspect **requested producer state**.
- Those getters **do not prove** the broker applied them if an administrative override exists.
- These settings are not properties on the String payload or on the `Queue`.
- `setDisableMessageID(true)` and `setDisableMessageTimestamp(true)` are **optimization hints** that a provider may honor or ignore; by default, message ID and timestamp are enabled.

### 4.1. Do Not Treat "Disable Message ID" as a Guarantee

```java
context.createProducer()
        .setDisableMessageID(true)
        .setDisableMessageTimestamp(true)
        .send(queue, "heartbeat");
```

These calls tell the provider the client does not need an ID/timestamp on that message. The provider **is allowed to ignore the hint**; you cannot treat `getJMSMessageID()==null` or `getJMSTimestamp()==0` as guaranteed. Do not disable IDs if the application needs tracing, message-ID request/reply correlation, or broker debugging.

These hints are completely separate from the core QoS trio `deliveryMode/priority/timeToLive`. Do not lump them into Spring's `explicitQosEnabled` flag, as Spring provides separate `setMessageIdEnabled` and `setMessageTimestampEnabled` settings.

## 5. Provider/Broker: Two Easy-to-Confuse Aspects of "Defaults"

### 5.1. Providers Can Administratively Configure Non-Spec Defaults

Some providers allow configuring default QoS via an administered `ConnectionFactory` or broker environment. When a client creates a producer and calls `send(message)` without explicit QoS, effective values may reflect that administrative config.

Hypothetical example for analysis:

| Layer | Delivery mode | Priority | TTL |
| --- | --- | --- | --- |
| Standard API defaults | PERSISTENT | 4 | 0 ms |
| Provider admin configured for new producers | PERSISTENT | 6 | 120,000 ms |
| Producer does not alter QoS and calls `send(message)` | May use admin set above | May use 6 | May use 120,000 |

This table is a **simulated scenario**, not a claim that every broker uses those numbers. Consult specific provider docs and config; if a provider does not alter defaults, a new producer normally starts with standard defaults.

**Where to be careful:** admin policies are deployment-specific. Some providers offer connection-factory defaults, some offer per-destination policies, and some offer send-time overrides. Do not mistake them all for one standard API.

### 5.2. Providers Can Even Override Client-Specified Values

Jakarta Messaging specification `3.4.12` allows administrators to configure the provider to **override client-specified values** for:

- Delivery mode.
- Priority.
- Time-to-live.
- Delivery delay.

When overridden, the `JMSDeliveryMode`, `JMSPriority`, `JMSExpiration`, and `JMSDeliveryTime` headers must reflect **the applied administrative values**. The specification **does not standardize** how overrides are declared and **does not require** providers to support this feature.

Therefore, saying "`send(message, PERSISTENT, 9, 60_000)` always beats broker configuration" is wrong at the specification level. Developers can **request** explicit QoS; broker deployments may validly enforce overrides, causing received headers to differ.

### 5.3. Effective QoS and Destination Retention Are Two Separate Things

Even when `getJMSDeliveryMode()==PERSISTENT` and `getJMSExpiration()==0`:

- The queue may be subject to quotas, discard policies, max size, or broker-enforced expiry.
- Topic consumers do not automatically exist while offline: non-durable subscriptions have their own semantics; durable ones must be properly created before publishing.
- The broker may route messages to a DLQ after retries.
- Business processing after receive can fail or roll back.
- No QoS setting automatically guarantees atomicity between a JMS send and a separate database transaction.

**Send headers only show the applied delivery policy**, not a guarantee that end-to-end business execution succeeded.

## 6. Spring JmsTemplate: Internal Defaults vs. Producer Defaults

This is the core learning point for Spring.

`JmsTemplate` has properties `deliveryMode`, `priority`, and `timeToLive`, plus the `explicitQosEnabled` flag.

`JmsTemplate`'s internal defaults match JMS:

```text
deliveryMode       = Message.DEFAULT_DELIVERY_MODE  (PERSISTENT)
priority           = Message.DEFAULT_PRIORITY       (4)
timeToLive         = Message.DEFAULT_TIME_TO_LIVE   (0)
explicitQosEnabled = false
deliveryDelay      = -1  (does not call setDeliveryDelay on producer)
messageIdEnabled   = true
messageTimestampEnabled = true
```

Crucial point: **`explicitQosEnabled=false` means Spring does not actively send its internal QoS fields via the explicit overload**. It calls the default-using producer send, allowing the producer/provider to apply configured defaults.

Per Spring JMS `JmsTemplate`:

- `setDeliveryMode(...)`, `setPriority(...)`, and `setTimeToLive(...)` update **configuration values stored in the template**.
- Only when `setExplicitQosEnabled(true)` is set does `JmsTemplate` pass those three values during `send`.
- `setQosSettings(new QosSettings(...))` bundles the settings and **enables explicit QoS**.
- `setDeliveryPersistent(boolean)` adjusts internal delivery mode; it **does not** bypass the need to enable explicit QoS.
- `setDeliveryDelay(...)` is a **separate** mechanism passed via `MessageProducer.setDeliveryDelay` when non-negative; Spring's default is `-1`, meaning do not set delay on the producer. It is **not among the three properties gated by `explicitQosEnabled`**.
- `setMessageIdEnabled(...)` and `setMessageTimestampEnabled(...)` are separate hint settings outside the explicit QoS triplet; providers may decline the optimization.

### 6.1. Spring Configuration Comparison Table

| Spring Config | How Spring Handles Client Side | What Must Not Be Assumed |
| --- | --- | --- |
| `new JmsTemplate(cf)`, QoS untouched | Uses producer defaults on send | Broker always uses 2/4/0 |
| `setPriority(8)`, explicit **not enabled** | Priority 8 sits in template, but send passes no override 8 | Actual message always gets priority 8 |
| `setTimeToLive(15_000)`, explicit still false | 15s TTL is not passed to explicit overload | Message certainly expires after 15s |
| `setDeliveryMode(NON_PERSISTENT)`, explicit still false | Sets internal value only | Message certainly NON_PERSISTENT |
| `setExplicitQosEnabled(true)` | Calls send with template's mode/priority/TTL | Provider admin cannot override |
| `setQosSettings(settings)` | Sets mode/priority/TTL and enables explicit QoS | Eliminates all broker policies |
| `setDeliveryDelay(2_000)` | Spring sets producer delivery delay to 2s on send | DeliveryDelay necessarily belongs to explicit QoS flag |
| `setDeliveryDelay(-1)` | Spring does not set delivery delay | Broker will always use delay 0 |
| `setMessageIdEnabled(false)` | Sends disable-ID hint to producer | ID is guaranteed null |
| `setMessageTimestampEnabled(false)` | Sends disable-timestamp hint to producer | Timestamp is guaranteed 0 |

**Two default-looking layers exist:** Spring holds a `priority=4` field, yet if `explicitQosEnabled=false`, Spring **does not necessarily use that field to override the producer**. Do not debug by calling `getPriority()` on a `JmsTemplate` bean and concluding the consumer receives header 4.

### 6.2. Which Logic Does JmsTemplate's Flow Resemble?

Simplified model based on Spring's implementation:

```java
// PSEUDOCODE for explanation, not a standalone runnable Java file.
if (deliveryDelay >= 0) {
    producer.setDeliveryDelay(deliveryDelay);
}

if (explicitQosEnabled) {
    producer.send(message, deliveryMode, priority, timeToLive);
} else {
    producer.send(message); // uses producer/provider defaults
}
```

The difference lies in **which `send` overload is called**. Taking the right branch matters more than the template fields holding default numbers 4/0/2.

To know what the broker actually accepted, **inspect message headers at send/receive along with provider docs**, rather than guessing from client code alone.

## 7. Spring JMS: Two Templates for Two Send Policies

This example uses Spring Framework 6+ or 7+, Java 17+, `jakarta.jms`, `spring-jms`, and a configured `ConnectionFactory`. The files below **belong to a Spring project with a broker** and cannot compile with plain JDK `javac` alone because they require dependencies, a container, and a real destination.

Assume queue `billing.jobs` exists or the broker allows auto-creation per policy.

### 7.1. First Bean: Letting the Provider Use Defaults

**File `QosSenderConfiguration.java`:**

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
public class QosSenderConfiguration {

    @Bean("providerDefaultsTemplate")
    public JmsTemplate providerDefaultsTemplate(ConnectionFactory cf) {
        JmsTemplate template = new JmsTemplate(cf);
        template.setPubSubDomain(false);
        // explicitQosEnabled defaults to false.
        // Does not pass mode/priority/TTL to producer on send.
        return template;
    }

    @Bean("applicationQosTemplate")
    public JmsTemplate applicationQosTemplate(ConnectionFactory cf) {
        JmsTemplate template = new JmsTemplate(cf);
        template.setPubSubDomain(false);

        template.setDeliveryMode(DeliveryMode.PERSISTENT);
        template.setPriority(7);
        template.setTimeToLive(60_000L);
        template.setExplicitQosEnabled(true);

        // Delivery delay is a separate setting, not part of the QoS triplet.
        template.setDeliveryDelay(2_000L);
        return template;
    }

    @Bean("jmsListenerContainerFactory")
    public DefaultJmsListenerContainerFactory listenerFactory(
            ConnectionFactory cf) {
        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(cf);
        factory.setSessionTransacted(true);
        factory.setPubSubDomain(false);
        return factory;
    }
}
```

**Explanation:**

- Both templates carry **distinct, stable policies**; never call `setPriority(...)` on a single shared bean per request, which causes races across concurrent sending threads.
- `providerDefaultsTemplate` does not actively specify 2/4/0 even though its internal fields hold those defaults. The provider/`ConnectionFactory` governs producer defaults.
- `applicationQosTemplate` **requests** PERSISTENT, priority 7, 60-second TTL per send, and a 2-second delivery delay. Broker admins can still override if supported and configured.
- The listener factory uses a local JMS transaction for consumption; it does not put the two producer templates into a shared DB transaction.
- `@EnableJms` enables `@JmsListener` detection; bean name `jmsListenerContainerFactory` serves as the default factory in this example.

### 7.2. Producer Using Each Policy

**File `BillingSender.java`:**

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;

@Service
public final class BillingSender {

    private final JmsTemplate providerDefaultsTemplate;
    private final JmsTemplate applicationQosTemplate;

    public BillingSender(
            @Qualifier("providerDefaultsTemplate")
            JmsTemplate providerDefaultsTemplate,
            @Qualifier("applicationQosTemplate")
            JmsTemplate applicationQosTemplate) {
        this.providerDefaultsTemplate = providerDefaultsTemplate;
        this.applicationQosTemplate = applicationQosTemplate;
    }

    public void sendNormal(String invoiceId) {
        providerDefaultsTemplate.convertAndSend(
                "billing.jobs", invoiceId);
    }

    public void sendUrgent(String invoiceId) {
        applicationQosTemplate.convertAndSend(
                "billing.jobs",
                invoiceId,
                message -> {
                    message.setStringProperty("kind", "URGENT");
                    return message;
                });
    }
}
```

Here `String` is converted to `TextMessage` by the default `SimpleMessageConverter`. `kind` is an application property and **does not automatically set JMS priority or delivery mode**. In `sendUrgent`, the template passes explicit QoS, not because of `kind="URGENT"`.

A message returning from send **does not mean the listener finished business work**. Monitor acks/commits, retries, and side effects.

### 7.3. Consumer Inspecting **Actual Headers**

**File `BillingQosInspector.java`:**

```java
import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public final class BillingQosInspector {

    @JmsListener(destination = "billing.jobs")
    public void inspect(Message message) throws JMSException {
        String deliveryMode =
                message.getJMSDeliveryMode() == DeliveryMode.PERSISTENT
                        ? "PERSISTENT" : "NON_PERSISTENT";

        System.out.println("messageId=" + message.getJMSMessageID());
        System.out.println("mode=" + deliveryMode);
        System.out.println("priority=" + message.getJMSPriority());
        System.out.println("expiration=" + message.getJMSExpiration());
        System.out.println("deliveryTime=" + message.getJMSDeliveryTime());
        System.out.println("redelivered=" + message.getJMSRedelivered());
    }
}
```

The listener receives raw `jakarta.jms.Message` to read headers. **Do not assume fixed stdout**: message IDs, timestamps, broker overrides, delivery mode/priority, and redelivery depend on runtime.

To draw solid conclusions:

1. Send one message via `sendNormal`.
2. Send one message via `sendUrgent`.
3. Match the **exact message** by ID or business key, comparing mode/priority/expiration/deliveryTime between the two policies.
4. If received priority differs from 7, check admin overrides, provider SDK config, which template bean was injected, and library versions.
5. If TTL/delay misses expectations, examine send timelines, broker timing, clocks, and expiration/delay policies.

### 7.4. A Classic Trap Example

```java
JmsTemplate template = new JmsTemplate(connectionFactory);
template.setPriority(9);
template.setTimeToLive(5_000L);
template.setDeliveryMode(DeliveryMode.NON_PERSISTENT);

// Missing template.setExplicitQosEnabled(true)!
template.convertAndSend("billing.jobs", "invoice-42");
```

The trap: the developer sees the code and thinks QoS is configured; in reality Spring still **sends using producer/provider defaults**. If the `ConnectionFactory` defaults to PERSISTENT, priority 4, TTL 0, the message may still use PERSISTENT/4/0.

**Fix:**

```java
template.setExplicitQosEnabled(true);
```

This fix makes the **client send the requested QoS**. If the provider enforces an explicit admin override, check administrative policies; never claim "setting true guarantees everything."

### 7.5. QosSettings Combines Configuration

`JmsTemplate` also supports `setQosSettings(QosSettings)` to bundle deliveryMode, priority, and TTL:

```java
import jakarta.jms.DeliveryMode;
import org.springframework.jms.support.QosSettings;

template.setQosSettings(
        new QosSettings(DeliveryMode.PERSISTENT, 7, 60_000L));
```

This snippet belongs to a Spring JMS project and assumes `template` already exists. `setQosSettings` enables `explicitQosEnabled` inside its implementation, unlike calling the three setters separately. Verify constructors/APIs in your project's Spring version. Do not assume it sets delivery delay, disables ID/timestamp, or changes provider retention.

## 8. Reading Headers at the Right Time, Computing TTL and Delay

Assume no provider admin override and send time `t0`.

```text
t0 = 1 700 000 000 000 ms (example value)

Producer / send:
  deliveryMode   = PERSISTENT
  priority       = 7
  timeToLive     = 60 000 ms
  deliveryDelay  = 2 000 ms

Provider-managed headers:
  JMSDeliveryMode = PERSISTENT
  JMSPriority     = 7
  JMSExpiration   = t0 + 60 000
  JMSDeliveryTime = t0 + 2 000
  JMSTimestamp    = close to when the provider accepted the send request
```

Real systems may record send timestamps that do not align identically with `System.currentTimeMillis()` in application code. For transacted sends, `JMSDeliveryTime` counts from **client send** time, not waiting for transaction commit before adding delay. `JMSTimestamp` likewise reflects handoff to the provider, not necessarily network wire time or consumer receipt time.

### 8.1. Interpreting the Headers

| Header | Who Decides at Send Time? | Notes |
| --- | --- | --- |
| `JMSDeliveryMode` | Provider based on chosen QoS or admin override | Reports actual mode; does not prove business exactly-once |
| `JMSPriority` | Provider based on chosen/overridden priority | Does not guarantee strict processing order |
| `JMSExpiration` | Provider computed from send time and effective TTL | `0` means no TTL-based expiry |
| `JMSDeliveryTime` | Provider computed from send time + delivery delay | Must not deliver before this time; no promise of exact millisecond |
| `JMSTimestamp` | Provider assigned at send unless disable hint honored | Does not replace business event timestamps |
| `JMSMessageID` | Provider generated at send unless disable hint honored | Does not replace business idempotency keys |
| `JMSDestination` | Provider reflects target destination | Do not use `message.setJMSDestination` to route |
| `JMSRedelivered` | Provider marks upon redelivery | Useful for observation, does not replace dedupe/transactions |

An application-specific property like `message.setIntProperty("desiredPriority", 9)` **does not automatically turn into** `JMSPriority=9`. Use properties for business metadata; use producer/template QoS for JMS priority.

### 8.2. How TTL and Delay Interact on a Message

Illustrative table assuming no admin override:

| TTL | Delay | Possible Outcome |
| --- | --- | --- |
| 0 ms | 0 ms | Eligible for immediate delivery when broker is ready; no TTL expiration |
| 60,000 ms | 0 ms | Delivered promptly, not delivered past expiration |
| 60,000 ms | 2,000 ms | Eligible starting at 2s, expires after 60s |
| 3,000 ms | 5,000 ms | Message may expire **before** becoming eligible for delivery |
| 0 ms | 10,000 ms | No TTL expiry, eligible starting at 10s |
| 1,000 ms | 0 ms | May expire in backlog if consumers are slow |

Never set an ultra-short TTL on mandatory messages facing heavy backlogs. Conversely, `TTL=0` for all transient events can bloat backlogs and storage costs. Base policies on **business SLAs** and consumer capacity, not guesses like "0 is safest."

## 9. Controlling Authority and Responsibilities Across Layers

### 9.1. What Is the Producer API Responsible For?

- Creating messages, choosing destinations, and invoking send.
- Setting default QoS or per-send QoS.
- Supplying application properties such as `businessId` and `eventType`.
- Managing producer-side transactions when configured.
- Handling send errors; on ambiguous outcomes, deciding on idempotent retries.

The producer **cannot** turn the broker into infinite storage, keep subscribers online, or force providers to support configuration overrides.

### 9.2. What Is the Provider/Broker Responsible For?

- Implementing JMS protocol and semantics.
- Supplying `ConnectionFactory`/connections/sessions/producers/destinations.
- Populating message IDs, timestamps, and delivery-related headers per spec.
- Enforcing delay, expiration, and priority per contract and supported policies.
- Applying admin defaults or overrides if supported.
- Managing quotas, retention, DLQs, permissions, topic subscription backlogs, and real persistence.
- Providing consoles/metrics/logs to observe enqueued, expired, redelivered, or rejected messages.

Never generalize **one specific broker's** behavior (such as auto-creating queues, strict priority ordering, or TTL redirection) as a rule of all Jakarta Messaging.

### 9.3. What Is the Application/Spring Responsible For?

- Choosing policies per business need: which events are mandatory, loss tolerance, useful lifetime, and urgency.
- Translating policies into proper `JmsTemplate` or `JMSProducer` configuration.
- Managing `ConnectionFactory`, profiles, secrets, namespaces, destinations, logging, and tracing.
- Maintaining idempotency, retries, and outbox/transactions for dual writes.
- Writing integration tests confirming real QoS at destination/consumer.
- Monitoring send errors, broker quotas/backlogs/expirations/DLQs, and business completion.

An application property like `"priority"=9` or `"ttlSeconds"=10` in a DTO **has no JMS effect** unless code maps it to producer QoS. Conversely, a broker policy like "max TTL 30 seconds" can still constrain an app requesting 60 seconds under supported admin overrides.

## 10. Order of Precedence: Use the Right Mental Model, Avoid Fake Rules

When final values differ from expectations, analyze in order: **request origin → send call → actual headers**, rather than assuming rigid rules:

### Step 1. Find Who Created the Configuration

- Does code call `new JmsTemplate(connectionFactory)` or inject another template?
- Are `setQosSettings` or `setExplicitQosEnabled` called?
- Are QoS setters used on `JMSProducer`/`MessageProducer`?
- Is per-send `send(..., mode, priority, ttl)` used?
- Which method sends? `JmsTemplate.send` or `convertAndSend`?

### Step 2. Determine What QoS the Client **Actually Requested**

- `JmsTemplate` explicit=false → producer send defaults.
- `JmsTemplate` explicit=true → template's mode/priority/TTL.
- Spring `setDeliveryDelay` with non-negative value → producer delay set; default -1 sets nothing.
- Classic API per-send QoS → requests those three values for that single send.
- Direct header setters on `Message` → **not** a valid QoS request.

### Step 3. Check Provider Override Capabilities

- Do `ConnectionFactory` defaults differ from Jakarta Messaging constants?
- Is an admin policy replacing client-specified QoS?
- Are there destination-specific TTL/priority/delivery policies?
- Are there custom quotas, retention, permissions, or scheduling behaviors?

### Step 4. Inspect Headers and Operational Outcomes

- On sender after synchronous send or on consumer: inspect mode, priority, expiration, and deliveryTime.
- Inspect backlog, priority distribution, expiration counts, retention/DLQ, subscriber counts, and transactions.
- Classify discrepancies accurately: **Spring did not pass it**, **producer defaults differ**, **provider admin override**, or **broker retention/failure**.
- Never treat a "send done" log as proof of completed business execution.

### Illustrative Scenario Matrix

The table below assumes a **hypothetical provider policy**: without explicit client QoS, producers start with PERSISTENT / priority 6 / TTL 120s. With **enforced admin override**, the provider enforces PERSISTENT / priority 5 / TTL 30s. This does not imply any specific real broker implements both modes identically.

| Case | Client Requests | Outcome to Verify |
| --- | --- | --- |
| New JMS producer, **no** admin policy | Spec default P / 4 / 0 | Typically P / 4 / 0 |
| New JMS producer, provider has admin defaults | Producer may inherit P / 6 / 120s | Possibly P / 6 / 120s |
| Spring `setPriority(8)`, explicit=false | Producer defaults, **does not request 8** | May remain P / 6 / 120s |
| Spring `setPriority(8)`, TTL 60s, explicit=true | Spring's QoS passed on send | Typically priority 8 / TTL 60s if no admin override |
| JMS explicit `send(priority=9, TTL=5s)` | Values for that specific send | Typically 9 / 5s if no admin override |
| Any case where provider enforces admin override | Client may have requested differently | Headers reflect admin values |
| Spring `setDeliveryDelay(2s)`, explicit=false | Spring still sets producer delay 2s | Possibly 2s; check admin overrides and headers |

Do not use this table to predict an untested broker. Use it only to know **where to look** when debugging.

## 11. Standalone Java 17 Example: Simulating QoS Layers

The snippet below illustrates **how to reason**, not a real JMS implementation. It runs on plain JDK 17, sends no messages, uses no broker, and does not claim to emulate every provider's rules. Admin policies are **simulated data**.

Create **`JmsQosLayersDemo.java`**:

```java
public final class JmsQosLayersDemo {

    record Qos(String mode, int priority, long ttlMs) {
        @Override
        public String toString() {
            return "mode=" + mode
                    + ", priority=" + priority
                    + ", ttlMs=" + ttlMs;
        }
    }

    static Qos chooseClientRequest(
            Qos producerDefaults,
            Qos applicationSettings,
            boolean explicitQosEnabled) {
        return explicitQosEnabled
                ? applicationSettings : producerDefaults;
    }

    static Qos optionalAdminOverride(
            Qos clientRequest, Qos enforcedByAdmin) {
        // Simulates a provider with a policy overriding every field.
        return enforcedByAdmin == null
                ? clientRequest : enforcedByAdmin;
    }

    public static void main(String[] args) {
        Qos jakartaSpec = new Qos("PERSISTENT", 4, 0);
        Qos providerDefaults = new Qos("PERSISTENT", 6, 120_000);
        Qos application = new Qos("NON_PERSISTENT", 8, 15_000);
        Qos adminEnforced = new Qos("PERSISTENT", 5, 30_000);

        Qos implicit = chooseClientRequest(
                providerDefaults, application, false);
        Qos explicit = chooseClientRequest(
                providerDefaults, application, true);

        System.out.println("JMS spec: " + jakartaSpec);
        System.out.println("Spring explicit=false: " + implicit);
        System.out.println("Spring explicit=true: " + explicit);
        System.out.println("After optional admin override: "
                + optionalAdminOverride(explicit, adminEnforced));
    }
}
```

Run:

```bash
javac JmsQosLayersDemo.java
java JmsQosLayersDemo
```

**Exact stdout:**

```text
JMS spec: mode=PERSISTENT, priority=4, ttlMs=0
Spring explicit=false: mode=PERSISTENT, priority=6, ttlMs=120000
Spring explicit=true: mode=NON_PERSISTENT, priority=8, ttlMs=15000
After optional admin override: mode=PERSISTENT, priority=5, ttlMs=30000
```

**Understand the example's limits:** this is an illustrative model **assuming** a provider changed producer defaults and supports admin overrides. It does not detect providers at runtime, prove all providers follow the same algorithm, or replace JMS send/receive testing. The takeaway is: when Spring `explicit=false`, application settings do not automatically override producer defaults; when `explicit=true`, the client sends its QoS request; admin overrides, if supported by the provider, can still alter the final headers.

### Why Is This Demo Helpful?

When investigating a bug like "set priority 8 but consumer sees 6":

- Do not immediately accuse the provider of violating the spec.
- Check whether Spring enabled explicit QoS.
- Check whether producer defaults are administratively configured.
- Check whether an admin override applied after send.
- Check whether the receiver is reading `JMSPriority` on the right message.

That is **evidence-based debugging**, not guessing from a single setter call.

## 12. Relationship with Transactions, Retries, Ordering, and Business QoS

### 12.1. Sending Persistent Does Not Solve Dual Writes

Example `OrderService`:

1. Commit an order to the database.
2. Publish `OrderCreated` to a topic/queue.
3. If a crash happens in between, DB data and message broker state diverge.

Choosing `PERSISTENT` on the producer controls only **the delivery mode of the sent message**; it does not ensure atomicity between DB commit and JMS send. Use a transactional outbox or coordinated transaction architecture; every retry must carry an idempotency key.

### 12.2. Priority Does Not Guarantee Execution Order Across Workers

A priority 9 message can overtake a priority 4 message in the broker, yet final order still depends on enqueue timing, consumer prefetch, selectors, concurrency, transactions, and redelivery. Priority is a **scheduling hint**, not a race-condition or deadline solver.

If SLAs require strong prioritization, consider dedicated queues, dedicated worker pools, rate limiting, backpressure, and provider-supported priority dispatch rather than setting every "urgent" message to 9.

### 12.3. TTL Should Reflect Business Lifetime

- Account activation email expires after 15 minutes: TTL can help, yet business token expiry must still be checked at the consumer.
- Mandatory audit event that must never be dropped: short TTL is risky, while infinite retention bloats backlogs. Use explicit retention policies and failure handling.
- Job scheduled to start after 30 seconds: 30s delivery delay and 5s TTL contradict each other, risking expiration before delivery.
- Job taking 10 minutes to run: TTL sets the **deadline for delivery to start**, not necessarily the business processing timeout once received; keep the two deadlines separate.

### 12.4. Message ID Is Not an Idempotency Key

`JMSMessageID` is assigned by the provider on send and can change when a client retries with a new message. Never rely solely on `JMSMessageID` to recognize two business requests as the same action. Use an application-generated stable `eventId` or `requestId` in properties/body and persist idempotent processing records.

### 12.5. Persistent Delivery Does Not Replace Durable Subscriptions

With topics, an offline non-durable consumer can miss events even when the producer sends `PERSISTENT`. A pre-created durable subscription, stable identity, and broker retention policies are required for offline event delivery. Never confuse "message persistence" with "subscription durability."

## 13. Direct Broker Testing Checklist

### Test A — Measure Producer Defaults

1. Create a fresh `MessageProducer`/`JMSProducer` in the app with no QoS overrides.
2. Read producer getters: mode, priority, TTL, delay.
3. Send a message with a unique `businessId`.
4. On the consumer, inspect mode, priority, expiration, and delivery time.
5. Compare against standard `PERSISTENT/4/0/0` and any `ConnectionFactory`/broker admin config.

If the provider deviates from spec defaults, verify whether an administrative config is active; do not patch every producer with hardcoded constants before understanding the policy.

### Test B — Spring Setters Without Explicit Flag

1. Create a `JmsTemplate` with `setPriority(8)` and `setTimeToLive(10_000)` but **without** `setExplicitQosEnabled(true)`.
2. Send a test message with a business ID.
3. Read `JMSPriority` and `JMSExpiration` on the consumer.
4. Observe they may reflect producer/provider defaults instead of `8`/`10s`.
5. Repeat with `explicit=true` and compare.

This is a critical test because reading source code can mislead you into thinking setters always apply.

### Test C — Administrative Override

1. In a test environment only, check whether your broker/provider supports admin QoS overrides.
2. If supported, configure an example enforced priority of 5.
3. Have the client explicitly send priority 8.
4. Inspect headers after send and at the consumer.
5. Verify headers **reflect the administrative value** if the provider applies spec-compliant overrides.
6. Remove the test policy so other applications' messages are unaffected.

Never attempt this test in production environments where policy changes are unauthorized.

### Test D — TTL and Delivery Delay

1. Send message X with 30s TTL and 2s delay.
2. Send message Y with 1s TTL and 5s delay.
3. Record `JMSTimestamp`/`JMSDeliveryTime`/`JMSExpiration`.
4. Verify X is not delivered before `deliveryTime`; verify Y is not delivered if expired before becoming eligible.
5. Observe broker expired counters and expiry policies; do not guess based on consumer thread sleep durations.

### Test E — Persistent Send with Consumer Failure

1. Send a `PERSISTENT` message to a queue with appropriate retention policy.
2. Have the consumer receive it and deliberately fail before ack/commit.
3. Observe rollback/redelivery, `JMSRedelivered`, and `JMSXDeliveryCount` if provided.
4. Retry once successfully with business idempotency.
5. Demonstrate that persistent mode does not solve duplicate execution at the business layer.

### Test F — A Broker Message Alone Is Not Full Proof

1. Log a unique event ID on the sender.
2. Observe broker accepted/enqueued or delivery counters.
3. Confirm the consumer committed and DB state updated.
4. Measure latency, backlog, expired count, DLQ, and time-to-complete.
5. Distinguish "send ok" from "processed exactly once" when defining SLOs.

## 14. Common Mistakes and Fixes

**Mistake 1: "JMS default is priority 4, so production definitely uses priority 4."**

Incorrect. That is the **producer spec default**; providers can configure administered defaults/overrides. Inspect actual received QoS.

**Mistake 2: "`JmsTemplate.setPriority(9)` is enough."**

No. With `explicitQosEnabled=false`, Spring does not use the template's priority field as an explicit send value. Enable `setExplicitQosEnabled(true)` if that is the desired policy.

**Mistake 3: "Enabling explicit QoS guarantees beating all broker policies."**

Wrong. The spec permits admins to override client-specified mode/priority/TTL/delay. Clients can only request; verify against the broker.

**Mistake 4: "`setTimeToLive(0)` keeps messages forever."**

Wrong. No TTL expiry occurs, yet retention, quotas, failures, topic subscriptions, and consumer handling can still remove or miss messages.

**Mistake 5: "DeliveryDelay 5s and TTL 2s still delivers after 5s."**

No. The message risks expiring before earliest delivery. Evaluate both against the same send anchor.

**Mistake 6: "To get priority 9, just call `message.setJMSPriority(9)`."**

Wrong. `JMSPriority` is a provider-managed header; pass QoS via producer/template. Message header setters are not a portable way to control send priority.

**Mistake 7: "`JMSPriority` is a strictly verifiable FIFO order."**

Wrong. JMS does not enforce strict priority ordering; providers attempt to favor higher levels, yet concurrent consumers can process out of order.

**Mistake 8: "`setDeliveryDelay` always requires `explicitQosEnabled`."**

Incorrect for current `JmsTemplate` implementations. Delay is configured separately; values `>=0` are applied to the producer right before send, whereas the explicit flag controls **mode, priority, and TTL**.

**Mistake 9: "`setMessageIdEnabled(false)` guarantees `JMSMessageID` is null."**

No. It is an optimization hint. Providers may ignore it and still assign an ID.

**Mistake 10: "Persistent topic messages mean all offline subscribers get the event."**

Wrong. Durable subscription is a separate concept; non-durable subscribers miss events published while inactive.

**Mistake 11: "Duplicate `JMSMessageID` means the same business action."**

No. Apps must design business IDs; provider message IDs do not deduplicate client retries of the same business action.

**Mistake 12: "Mutating QoS setters on a singleton `JmsTemplate` per request is safe."**

Avoid this. `JmsTemplate` is thread-safe **once configured**. Never treat bean settings as mutable per-request state under concurrency; use separate per-policy templates or safe designs.

**Mistake 13: "If the broker has a backlog, just raise priority."**

Insufficient. Backlogs can stem from too few consumers, slow processing, DB locks, invalid schemas, retry/DLQ storms, or quotas. Use metrics and root-cause analysis rather than assuming priority fixes throughput.

## 15. Application Send Policy Design Checklist

Before merging any change involving JMS sends, confirm:

- [ ] Identified message types and real SLAs: acceptable loss, deadline, max backlog?
- [ ] Know the **JMS API defaults** for producers: PERSISTENT, priority 4, TTL 0, delay 0?
- [ ] Checked **effective producer defaults** from the provider/`ConnectionFactory` and admin docs?
- [ ] In Spring, intentionally chose `explicitQosEnabled` to match the goal?
- [ ] If explicit=true, configured all three—**mode, priority, and TTL**—rather than changing one and forgetting the other defaults?
- [ ] Handled `setDeliveryDelay` separately and verified compatibility with TTL?
- [ ] Checked whether any admin overrides replace even explicit client QoS?
- [ ] Verified `JMSExpiration`/`JMSDeliveryTime` on real messages?
- [ ] Applied a consistent priority 0–9 policy without overusing 9?
- [ ] Distinguished message expiration from business deadlines/timeouts?
- [ ] Distinguished PERSISTENT from retention, durable subscriptions, and business exactly-once?
- [ ] Set up monitoring for queue depth, expired count, redeliveries, DLQs, send errors, and processing latency?
- [ ] Added idempotency keys/transactions/outbox when messages trigger side effects or require DB/JMS consistency?
- [ ] Avoided depending on disable ID/timestamp hints for mandatory logic?
- [ ] Written integration tests against **real** providers and runtime configurations?

### Useful Team Conventions

Define QoS **by message category** rather than developer habit:

| Business Category (Example) | Policy Direction to Discuss | Additional Checks Required |
| --- | --- | --- |
| Mandatory audit updates | Prioritize zero loss, sufficient retention, durable consumers | DB/JMS consistency, retries, DLQ |
| Expiring reminders | TTL aligned with useful lifetime | Backlog, safe expiry handling |
| Non-critical metrics/heartbeats | `NON_PERSISTENT` acceptable if loss tolerated | Provider failures, throughput |
| Urgent tasks | Conditionally higher relative priority | Queue load, fairness, starvation |
| 30s delayed jobs | 30s delivery delay with compatible TTL | Earliest delivery, clocks, and scheduling |

These are **analysis guidelines**, not rigid numbers for every system. Final TTL, mode, and priority must reflect SLAs, provider support, and testing.

## 16. Knowledge Self-Check

**Q1.** What delivery mode, priority, TTL, and delay does a new `MessageProducer` use by JMS default?

**Answer:** `PERSISTENT`, priority 4, TTL 0 ms (no TTL expiration), delivery delay 0 ms.

**Q2.** Why can we not conclude every production message carries those exact defaults?

**Answer:** Providers/`ConnectionFactory` can configure administered defaults, and the spec permits admin overrides of certain client-specified QoS values. Inspect runtime behavior.

**Q3.** Spring has `template.setPriority(9)` without enabling explicit. Does `convertAndSend` definitely send with priority 9?

**Answer:** No. `JmsTemplate` does not pass its QoS triplet when `explicitQosEnabled=false`.

**Q4.** What does enabling `template.setExplicitQosEnabled(true)` change?

**Answer:** Spring passes the template's delivery mode, priority, and TTL to the explicit producer send overload. It does not invalidate provider admin overrides.

**Q5.** How do `MessageProducer.setPriority(7)` and `producer.send(message, PERSISTENT, 9, 5000)` differ?

**Answer:** The setter updates the producer's default; the explicit send overload specifies priority 9, 5s TTL, and mode for that single send. Subsequent `send(message)` calls still use the producer default unless changed.

**Q6.** Is `message.setJMSPriority(9)` a portable way to send at priority 9?

**Answer:** No. That header is populated by the provider on send. Use producer QoS or a Spring template with `explicit=true`.

**Q7.** Is Spring's `setDeliveryDelay(2_000)` gated by `explicitQosEnabled`?

**Answer:** No, in the described `JmsTemplate` implementation; Spring sets producer delay when non-negative, while the explicit flag controls mode, priority, and TTL.

**Q8.** A message has a 1-second TTL and 5-second delay; is the consumer guaranteed to receive it after 5 seconds?

**Answer:** No. It may expire before becoming eligible for delivery, so never pair conflicting values like that.

**Q9.** What does `JMSExpiration=0` indicate?

**Answer:** No JMS TTL-based expiration timestamp is set. It does not promise the broker keeps the message forever regardless of retention/quotas.

**Q10.** Why does `priority=9` not guarantee exact worker processing order?

**Answer:** Providers are not required to enforce strict priority ordering; concurrency, prefetch, selectors, retries, and multiple consumers affect execution order.

**Q11.** A broker admin enforces priority 5 despite the client requesting explicit priority 9. Should the received message reflect priority 5?

**Answer:** If the provider supports and applies spec-compliant admin overrides, `JMSPriority` must reflect the admin-chosen value.

**Q12.** A producer sends `PERSISTENT` to a topic while a non-durable consumer is off. Will the consumer automatically receive missed events upon restart?

**Answer:** No. Durable subscription is a separate requirement.

**Q13.** Is `JMSMessageID` a durable idempotency key for a retried business operation?

**Answer:** No. Retries can produce a new message with a different `JMSMessageID`; use an application-managed business event/request ID.

**Q14.** Why inspect QoS headers at the consumer instead of only reading bean configuration?

**Answer:** Headers reflect the QoS actually applied by the provider (including admin overrides), whereas bean properties show only Spring-side intent/config.

**Q15.** A JMS job sends successfully, yet the consumer's database update fails. Does choosing `PERSISTENT` automatically fix the business failure?

**Answer:** No. You need proper transactions/acks, retries, and idempotency; for dual writes, use a consistency mechanism like an outbox.

## Core Summary

**There are three distinct "default" concepts:**

- **Producer/JMS API defaults:** `PERSISTENT`, priority 4, TTL 0, delivery delay 0; spec constants describing initial state without other configuration.
- **Provider/broker-admin defaults/policies:** can shape producer defaults or override client-specified QoS if supported by the implementation; also govern retention, quotas, and destination semantics.
- **Application/Spring policies:** business requirements and `JmsTemplate` settings; when `explicitQosEnabled=false`, the template's mode/priority/TTL fields are not sent as explicit parameters; when `true`, they are. Delay uses a separate path.

**Most effective verification workflow:** identify the send call → inspect template/producer state → check broker admin policies → read `JMSDeliveryMode`, `JMSPriority`, `JMSExpiration`, and `JMSDeliveryTime` on real messages → compare against business outcomes. Never confuse what the client **intended to send** with what the broker **actually applied**, and never confuse applied headers with a **completed business transaction**.

### Official References for Lookup

1. [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html), especially `3.4.11–3.4.13` on provider-managed headers, admin overrides, and delivery time; `7` on sending semantics.
2. [Jakarta Messaging 3.1 — MessageProducer API](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/messageproducer): defaults, setters, and explicit send overloads.
3. [Jakarta Messaging 3.1 — JMSProducer API](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/jmsproducer): fluent QoS API, message ID/timestamp hints.
4. [Jakarta Messaging 3.1 — Message API](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/message): default constants and provider-set headers.
5. [Spring Framework — Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html): administered `ConnectionFactory` defaults, `JmsTemplate`, and `explicitQosEnabled`.
6. [Spring Framework — JmsTemplate API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/core/JmsTemplate.html): `setDeliveryMode`, `setPriority`, `setTimeToLive`, `setDeliveryDelay`, `setExplicitQosEnabled`, `setQosSettings`, and message hints.
7. [Spring Framework — Sending a Message](https://docs.spring.io/spring-framework/reference/integration/jms/sending.html): `send`, `convertAndSend`, and template usage.
