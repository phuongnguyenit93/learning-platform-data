# QoS, retain, and clean session

## 1. Context and objectives

When connecting Spring Integration to an MQTT broker, three choices strongly influence message sending and receiving behavior: **Quality of Service (QoS)**, **retained messages** (often shortened to *retain*), and **clean session**. They address **three different concerns**:

- **QoS:** the delivery guarantee for an MQTT PUBLISH between protocol participants.
- **Retain:** whether the broker keeps the last message on a topic to send to new subscribers.
- **Clean session:** whether an MQTT 3.1.1 client/broker preserves session/subscription state and related data after the client disconnects.

These three concepts do not substitute for one another. A retained message is not a queue storing all events; clean session does not determine QoS; QoS 2 does not guarantee that a database or device executes a business action only once.

This lesson sits in the **Adapter MQTT** chapter of the **SPRING_INTEGRATION_ADAPTERS** module, where learners integrate external systems via inbound/outbound adapters, gateways, pollers, and `MessageChannel`; practice exchanges over files, SFTP, HTTP, JMS, AMQP, Kafka, and databases; and manage errors, message contracts, and connection lifecycles. With MQTT, Spring Integration connects to the broker using Paho adapters, then passes messages through channels to business flows or publishes them back to the broker.

After completing this lesson, learners will be able to:

1. Accurately distinguish QoS 0, 1, and 2 and the scope of guarantees for each level.
2. Explain the retained flag on publications and how to clear retained messages.
3. Design clean sessions in **MQTT 3.1.1**, Client IDs, subscriptions, and offline/reconnect cases.
4. Choose different settings for **telemetry**, **state snapshots**, **one-time commands**, and **critical events**.
5. Configure QoS/retained via `MqttHeaders` or defaults on `MqttPahoMessageHandler`.
6. Configure inbound QoS and clean session via `MqttPahoMessageDrivenChannelAdapter` and `MqttConnectOptions`.
7. Write Java DSL flows, brokerless unit tests, and broker-backed end-to-end tests.
8. Design retries, idempotency, replay, security, and monitoring at the appropriate layers.

> **Version scope:** examples use Spring Integration MQTT based on Eclipse Paho MQTT v3 and MQTT **3.1.1**. MQTT 5 uses *Clean Start* and *Session Expiry Interval* instead of the single `cleanSession` flag; do not apply the v3 API shown here verbatim to MQTT 5.

## 2. Three concepts on three independent axes

~~~mermaid
flowchart LR
    PUB["Publisher<br/>PUBLISH(payload, topic, QoS, RETAIN)"]
    B[("MQTT broker<br/>session + retained state")]
    SUB["Subscriber<br/>Client ID + cleanSession + subscription QoS"]
    FLOW["Spring Integration<br/>MessageChannel → Handler"]
    PUB -->|"Publish-leg QoS"| B
    B -->|"Delivery QoS per subscription"| SUB
    B -.->|"Retained snapshot on subscribe"| SUB
    SUB -->|"Inbound message-driven adapter"| FLOW
~~~

| Property | Where it is set | Primary effect | What it does **not** guarantee |
| --- | --- | --- | --- |
| **Publish QoS** | Publisher/`MqttPahoMessageHandler` or `MqttHeaders.QOS`. | Delivery mechanism of the publication to the broker per chosen QoS. | Subscriber executing side effects only once. |
| **Subscription QoS** | Subscriber/`MqttPahoMessageDrivenChannelAdapter.setQos(...)`. | Maximum QoS level the broker may use when delivering matching messages to the client. | Changing the original publication's QoS or guaranteeing DB commit. |
| **RETAIN** | Publisher/`MqttHeaders.RETAINED` or handler default. | Asks the broker to keep the latest retained message for the topic. | Storing event history or all messages while subscriber is offline. |
| **Clean session** | Client `MqttConnectOptions.setCleanSession(...)` on CONNECT. | Controls starting fresh versus preserving an MQTT 3.1.1 session. | Automatically creating a durable queue/transaction in Spring Integration. |
| **Client ID** | When creating an MQTT client/adapter. | Broker identifies a specific client session. | Identifying events/commands for business idempotency. |

An important example: a device publishes temperature values to `sensors/device-17/temperature` with QoS 1 and `RETAIN=true`. A new subscriber with `cleanSession=true` can receive the latest retained snapshot immediately on subscribing, yet **does not receive all historical temperatures**. An offline subscriber using a persistent session, a stable Client ID, and subscription QoS 1 can receive QoS 1/2 messages stored by the broker while offline per broker policy, even if those publications were **not retained**.

## 3. QoS 0: at most once

MQTT QoS 0 sends a single `PUBLISH` without the acknowledgment handshake used in QoS 1/2. It prioritizes low overhead, low latency, and minimal protocol traffic.

~~~mermaid
sequenceDiagram
    participant P as Publisher
    participant B as MQTT broker
    participant S as Subscriber
    P->>B: PUBLISH(QoS=0)
    B->>S: PUBLISH if subscriber qualifies
    Note over P,S: No PUBACK/PUBREC/PUBREL/PUBCOMP handshake
~~~

Points to remember:

- Publications can be lost if the connection drops, the broker is down, or a client cannot keep up.
- Do not expect guaranteed redelivery from MQTT QoS 0.
- If a Spring source only holds telemetry in RAM, connection failures can cause unrecoverable record loss.
- Use QoS 0 for data that can be re-sampled—such as frequent temperature readings—**if business rules tolerate losing occasional samples**.

Example:

~~~text
topic   = sensors/device-17/temperature
payload = {"deviceId":"device-17","celsius":26.5}
qos     = 0
retain  = false
~~~

**Common trap:** a successful send in Spring Integration does not mean the subscriber received a QoS 0 message. When the application invokes the outbound handler, the outcome depends on the processing path and sync/async mode, and there is no MQTT QoS 1/2 ACK layer for QoS 0 publications.

## 4. QoS 1: at least once

QoS 1 uses a two-step handshake `PUBLISH → PUBACK`. When a client does not observe acknowledgment under protocol conditions, the message can be redelivered. This improves delivery reliability while allowing **duplicates**.

~~~mermaid
sequenceDiagram
    participant P as Publisher
    participant B as MQTT broker
    P->>B: PUBLISH(QoS=1, packetId=42)
    B-->>P: PUBACK(packetId=42)
    Note over P,B: If PUBACK is lost, PUBLISH may be re-sent
~~~

For publisher → broker, QoS 1 only confirms protocol delivery for **this leg**. Broker → subscriber is a separate leg with its own subscription QoS and session. A PUBACK at the publisher **does not prove**:

1. The subscriber is online.
2. The subscriber actually read the payload.
3. The device executed the command.
4. The Spring service handler committed to the database.

**Business duplicate example:** a publisher creates command `cmd-1001`; the broker receives it and sends PUBACK, but the ACK packet is dropped. The application retries with a new PUBLISH, and the subscriber can receive the command again. Whether one packet is re-sent with the DUP flag or two separate publications carry the same payload, the application still needs a **`commandId`** and an idempotency policy.

| Data type | When QoS 1 fits | Additional conditions |
| --- | --- | --- |
| Inventory update events | Prioritizing not losing events. | Use `eventId`, idempotency, and checkpoints. |
| State-changing commands | Device needs a chance to receive commands over flaky networks. | Prevent duplicate side effects; use a business ACK. |
| Critical telemetry | Needs better delivery reliability than QoS 0. | Deduplicate by device ID + sequence/event ID. |

Do not equate "at least once" at the MQTT layer with "whenever DB processing fails, the broker will definitely redeliver." MQTT acknowledgment timing, manual ack options, and error paths must be verified for your exact adapter/client version.

## 5. QoS 2: exactly once at the MQTT layer

QoS 2 uses a four-step handshake to process one publication within the scope of the MQTT protocol:

~~~mermaid
sequenceDiagram
    participant P as Publisher
    participant B as MQTT broker
    P->>B: PUBLISH(QoS=2, packetId=42)
    B-->>P: PUBREC(packetId=42)
    P->>B: PUBREL(packetId=42)
    B-->>P: PUBCOMP(packetId=42)
~~~

Within a valid MQTT session, the handshake prevents duplicate delivery **of that same publication at the protocol layer**. However:

- The publisher can still create **two distinct publications** representing the same business event.
- Once Spring Integration dispatches the message to a handler, a DB transaction can fail or be retried independently.
- A device can execute a command and crash before sending a business ACK; the caller retries, issuing another command with the same effect.
- Raising QoS adds protocol overhead, in-flight state, and latency compared to lower QoS levels.

**Never call QoS 2 "exactly once end-to-end."** If you must avoid duplicate invoices, use a database unique constraint/idempotency key; if you must ensure a device does not unlock twice, use command IDs, state tracking, and business-layer checks. Choose QoS 2 when the protocol and SLA truly require it, after measuring broker/client cost.

## 6. Effective QoS when publisher and subscriber differ

The publisher chooses QoS on each PUBLISH; the subscriber chooses a QoS level when it SUBSCRIBEs. In MQTT 3.1.1, the broker delivers messages at a maximum QoS not exceeding the granted subscription level, commonly expressed as:

~~~text
QoS_delivery = min(QoS_publish, QoS_subscription)
~~~

| QoS PUBLISH | QoS SUBSCRIBE | QoS broker typically delivers to subscriber |
| ---: | ---: | ---: |
| 0 | 0 | 0 |
| 0 | 1 | 0 |
| 0 | 2 | 0 |
| 1 | 0 | 0 |
| 1 | 1 | 1 |
| 1 | 2 | 1 |
| 2 | 0 | 0 |
| 2 | 1 | 1 |
| 2 | 2 | 2 |

For example, the outbound handler sets `MqttHeaders.QOS = 1`, while the subscriber subscribes to the filter at QoS 0: delivery to the subscriber can be **QoS 0**. Therefore, changing publisher QoS only solves half the equation; inspect both subscriber QoS and broker policies.

If topic filters overlap or multiple overlapping subscriptions exist, brokers have rules for effective delivery; do not simply assume "every subscription gets one copy." Test against a real broker to confirm the behavior your application needs.

## 7. Retained messages: the latest snapshot of a topic

When a publisher sends a `PUBLISH` with **RETAIN=true**, the broker is asked to store the latest retained message for **that topic**. A subscriber creating a matching subscription afterward can receive the retained message according to protocol/broker behavior.

~~~mermaid
sequenceDiagram
    participant P as Temperature publisher
    participant B as MQTT broker
    participant S as New subscriber
    P->>B: PUBLISH(topic=devices/17/state, RETAIN=true, state=ON)
    Note over B: Stores latest retained snapshot for topic
    S->>B: SUBSCRIBE(devices/+/state)
    B-->>S: Retained state=ON
~~~

A topic normally holds only **the latest retained snapshot**, not a history of every publication:

~~~text
PUBLISH retained=true, topic=devices/17/state, payload=OFF
PUBLISH retained=true, topic=devices/17/state, payload=ON

New subscriber subscribes to devices/+/state
  → Receives retained snapshot ON, not both OFF and ON as an event log.
~~~

Retained is especially useful for **current state** data:

- Whether a device is online/offline and its latest status.
- Current desired configuration values.
- Latest temperature snapshot if new subscribers need to see it immediately.

**Do not indiscriminately use retained for one-time commands** such as unlocking, payments, starting a pump, or sending SMS. New or re-subscribing subscribers could receive an old command and repeat the side effect.

### 7.1. RETAIN=false does not delete a prior retained snapshot

If the broker already holds a retained message on a topic and a publisher later sends a new message with `RETAIN=false`, that publication does not automatically replace or clear the stored retained snapshot. To update the retained state, publish a new retained message.

Example:

~~~text
t1: PUBLISH topic=devices/17/state, payload=ON,  RETAIN=true
t2: PUBLISH topic=devices/17/state, payload=OFF, RETAIN=false
t3: new subscriber SUBSCRIBE devices/+/state
    → May receive the retained snapshot ON stored from t1.
~~~

This easily causes a "new subscriber sees stale state" bug even though application logs show a more recent publication. Establish a consistent convention: **always publish state snapshots with `retained=true`** if the broker serves as that state cache.

### 7.2. Deleting a retained message

In MQTT 3.1.1, the way to ask the broker to delete a topic's retained state is to publish to **that exact topic** with `RETAIN=true` and a **zero-byte payload**.

CLI example (test broker):

~~~bash
mosquitto_pub -h localhost -p 1883 \
  -t 'devices/device-17/state' \
  -q 1 -r -n
~~~

Here `-r` sets the retained flag and `-n` sends a null/empty payload. This is a **state-mutating command** on the broker. Never run it on production topics without verifying data ownership, permissions, and subscriber impact.

To represent a business-level null value, **do not** conflate it with clearing retained state. A JSON payload `{"value":null}` has non-zero length and will be retained by the broker if `RETAIN=true`.

### 7.3. The RETAIN flag on received messages

In MQTT 3.1.1, when the broker sends a **retained snapshot due to a new subscription**, the subscriber can observe the retained flag. A live publication forwarded by the broker to an existing subscriber may carry the flag per different protocol rules; never guess whether a message is new merely by inspecting identical payloads.

Spring Integration's MQTT inbound converter can expose this information in received metadata headers. Header constants and mapping behavior should be verified against your exact library version (e.g., `MqttHeaders.RECEIVED_*` constants). When an application must distinguish snapshots from new events, test with a real broker and include timestamps/event IDs in the payload.

## 8. Clean session in MQTT 3.1.1

When an MQTT 3.1.1 client sends CONNECT, the **Clean Session** flag tells the broker/client whether to start a fresh session or preserve an existing session.

### 8.1. cleanSession=true

- The client requests a fresh session, not restoring old session state as a persistent session.
- The broker does not keep that subscription/session state after the client disconnects under clean-session rules.
- When the client reconnects, the application usually **must re-subscribe** to the topics it needs.
- While the subscriber is offline, publications sent during that window **are not accumulated solely via the old subscription** of a clean session.
- After re-subscribing, the broker may deliver the latest retained snapshot if one exists, but not the full offline message history.

Suitable for applications needing only live data, able to tolerate sample loss, and having clear subscribe/reconnect initialization logic.

### 8.2. cleanSession=false

- The client requests a **persistent session** bound to its Client ID.
- The broker can retain subscriptions and queued/in-flight message state per MQTT rules and resource limits.
- If a subscriber already subscribed at QoS 1/2 and goes offline, the broker can store matching messages to deliver when the client **reconnects with the same Client ID**.
- Persistent sessions must be paired with QoS policies, broker storage/quotas, session lifecycle management, and a stable Client ID.
- It does **not** automatically make Spring's `QueueChannel` durable, cover database transactions, or turn QoS 0 telemetry into messages stored durably while offline.

**Important:** merely setting `cleanSession=false` in options without ever having subscribed successfully does not create the needed subscription. Session state depends on actual CONNECT/SUBSCRIBE execution.

### 8.3. Direct comparison

| Criterion | `cleanSession=true` | `cleanSession=false` |
| --- | --- | --- |
| Prior state on CONNECT | Starts a clean session. | Can restore stored session state for the same Client ID. |
| Subscriptions after going offline | Not retained for the client under clean session. | Can be retained by the broker. |
| Offline QoS 1/2 messages | No backlog guarantee from prior session. | Can be stored/delivered per MQTT and broker policy if subscription is valid. |
| Client ID on restart | May change if prior session is not needed. | Typically must stay **stable** to resume the session. |
| Retained snapshot on new subscribe | Can be received. | Can also be received when a new subscription is created; do not assume every reconnect replays retained. |
| Needs idempotency design? | **Yes**, when sources/retries can emit duplicates. | **Yes**, especially with QoS 1/2 and redeliveries. |
| Guarantees exactly-once database? | No. | No. |

### 8.4. Clean session does not mean "clean history"

The clean session flag does not wipe retained messages across the broker. Retained messages are **topic-level broker state**, not merely private client session data. A new subscriber with `cleanSession=true` can still receive a previously stored retained snapshot.

Conversely, `cleanSession=false` is not a "keep every message on every topic" setting. The broker only stores what belongs to configured subscriptions/sessions and policies, within its storage limits.

## 9. Four scenarios combining QoS, retained, and clean session

### Scenario A: live telemetry, sample loss acceptable

~~~text
Publisher: qos=0, retain=false
Subscriber: subscribe qos=0, cleanSession=true
Goal: current readings; losing a few samples is acceptable.
~~~

Simple and lightweight; if the subscriber goes offline, do not expect replay of missed samples.

### Scenario B: latest state snapshot

~~~text
Publisher: qos=1, retain=true
Subscriber: subscribe qos=1, cleanSession=true
Goal: new subscribers receive the latest state snapshot.
~~~

When a subscriber reconnects and creates a fresh subscription, it can receive the retained snapshot immediately. However, if state changed `ON` then `OFF` while offline, the subscriber **does not receive both events**, only the final state snapshot if the publisher maintained retained properly.

### Scenario C: receiving offline events

~~~text
Publisher: qos=1, retain=false
Subscriber: subscribe qos=1, cleanSession=false
Client ID: fixed across restarts
Goal: broker buffers some events while the client is temporarily offline.
~~~

Requires the subscription to have been established before going offline, broker support for session storage, and staying within quotas/retention. On reconnect, the client may receive the stored backlog. Consumers must handle duplicates, lag, and ordering.

### Scenario D: one-time command with business ACK

~~~text
Publisher: qos=1, retain=false
Subscriber: subscribe qos=1, cleanSession=false or per device SLA
Payload: {"commandId":"cmd-1001","action":"TURN_ON"}
Goal: better delivery and confirmation that the device executed it.
~~~

Do not use retained commands unless it is **truly a desired-state command** designed to be idempotent with versioning/expiry. You need a dedicated ACK flow by `commandId`, timeouts, and device-side idempotency; MQTT QoS is only part of the picture.

## 10. Relationship between retained and persistent sessions on reconnect

This is an easy source of confusion worth separating cleanly:

~~~mermaid
flowchart TD
    START["Subscriber reconnects"]
    SESSION{"Existing persistent session?"}
    EXIST["Restore subscriptions / in-flight state<br/>per broker"]
    NEW["Create new subscription"]
    RET{"Broker holds retained snapshot<br/>for topic filter?"}
    BACKLOG["Deliver session offline messages<br/>if still present and valid"]
    SNAP["Deliver retained snapshot per subscribe rules"]
    LIVE["Receive live publications"]
    START --> SESSION
    SESSION -->|"Yes"| EXIST --> BACKLOG --> LIVE
    SESSION -->|"No or clean session"| NEW --> RET
    RET -->|"Yes"| SNAP --> LIVE
    RET -->|"No"| LIVE
~~~

This diagram shows the **main idea**, not a fixed guarantee of callback ordering for every client/broker. When an adapter re-subscribes while a persistent session exists, the broker may treat it as a fresh SUBSCRIBE, and retained behavior depends on protocol/broker rules. Always test against your real broker.

| If you need... | Primary mechanism | What not to do |
| --- | --- | --- |
| Current value only | Latest retained snapshot. | Use retained in place of a historical event log. |
| Missed events while client was offline | Persistent session + QoS 1/2 subscription + broker storage. | Set `RETAIN=true` and assume all events will arrive. |
| Full replay after multi-hour/day DB outage | Event store/outbox/broker suited to retention needs, checkpoints. | Rely solely on clean session or an in-memory queue. |
| Prevent duplicate command execution | Event/command ID, unique constraints, idempotent handler. | Simply bump QoS to 2. |
| Ensure device finished command | Business ACK/correlation and timeout. | Rely solely on MQTT PUBACK. |

## 11. Configuring Spring Integration and Eclipse Paho

With Spring Boot (Java 17+) and Paho v3-based Spring Integration MQTT, the core Maven dependencies are:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-mqtt</artifactId>
</dependency>
~~~

Do not manually override conflicting versions when using Spring Boot's compatible dependency management/BOM. Common classes:

~~~java
import org.eclipse.paho.client.mqttv3.MqttConnectOptions;
import org.springframework.integration.mqtt.core.DefaultMqttPahoClientFactory;
import org.springframework.integration.mqtt.core.MqttPahoClientFactory;
import org.springframework.integration.mqtt.inbound.MqttPahoMessageDrivenChannelAdapter;
import org.springframework.integration.mqtt.outbound.MqttPahoMessageHandler;
import org.springframework.integration.mqtt.support.DefaultPahoMessageConverter;
import org.springframework.integration.mqtt.support.MqttHeaders;
~~~

In real applications, broker URLs, credentials, TLS/ACLs, and Client IDs must come from environment configuration—never hardcode secrets.

### 11.1. Client factory selecting clean session

~~~java
@Bean
MqttPahoClientFactory subscriberFactory() {
    var options = new MqttConnectOptions();
    options.setServerURIs(new String[] {"tcp://localhost:1883"});
    options.setConnectionTimeout(10);
    options.setKeepAliveInterval(30);
    options.setCleanSession(false); // Subscriber needs a persistent session

    var factory = new DefaultMqttPahoClientFactory();
    factory.setConnectionOptions(options);
    return factory;
}
~~~

`setCleanSession(false)` is an **MQTT 3.1.1 connection/session** setting. It is not the same as `setRetained(false)` on outbound messages, and it does not choose subscription QoS. If a separate publisher uses `cleanSession=true`, create a **second factory bean** with its own options instead of sharing a policy that fits only one direction.

### 11.2. Inbound adapter selecting subscription QoS

~~~java
@Bean
MqttPahoMessageDrivenChannelAdapter mqttInboundAdapter(
        @Qualifier("subscriberFactory") MqttPahoClientFactory factory,
        @Qualifier("mqtt.telemetry.in") MessageChannel output,
        @Value("${app.mqtt.subscriber-id}") String clientId) {

    var adapter = new MqttPahoMessageDrivenChannelAdapter(
            clientId, factory, "sensors/+/temperature");
    adapter.setQos(1);
    adapter.setRecoveryInterval(10000);
    adapter.setConverter(new DefaultPahoMessageConverter());
    adapter.setOutputChannel(output);
    return adapter;
}
~~~

This inbound is **message-driven**: the broker delivers MQTT PUBLISH packets via client callbacks, and the adapter converts them into Spring messages sent to `mqtt.telemetry.in`. **There is no `@Poller`** reading the broker. Only if a `QueueChannel` sits downstream does the queue's consumer need a poller at that internal stage.

### 11.3. Outbound handler selecting default QoS and retained

~~~java
@Bean(name = "mqttPublisher")
MqttPahoMessageHandler mqttPublisher(
        @Qualifier("publisherFactory") MqttPahoClientFactory factory,
        @Value("${app.mqtt.publisher-id}") String clientId) {

    var handler = new MqttPahoMessageHandler(clientId, factory);
    handler.setDefaultTopic("devices/default/state");
    handler.setDefaultQos(1);
    handler.setDefaultRetained(false);
    handler.setConverter(new DefaultPahoMessageConverter());
    handler.setAsync(false);
    handler.setCompletionTimeout(5000);
    return handler;
}
~~~

`setDefaultQos(1)` and `setDefaultRetained(false)` are **publication defaults** when a message provides no overrides under the converter contract. Individual publications can specify `MqttHeaders.QOS` and `MqttHeaders.RETAINED`. Do not set default `retained=true` for all messages if the same handler sends both state snapshots and one-time commands.

Both snippets above only illustrate **endpoint configuration**; the complete example with factories, channels, flows, and publisher is in section 12.

## 12. End-to-end Spring Boot example: STATE, COMMAND, TELEMETRY

Goal: build an application with an outbound flow sending three message kinds and an inbound adapter subscribing to telemetry. Configuration:

- **STATE:** QoS 1, `retained=true`.
- **COMMAND:** QoS 1, `retained=false`.
- **TELEMETRY:** QoS 0, `retained=false`.
- **Telemetry subscriber:** subscribes at QoS 1, `cleanSession=false` with a stable Client ID.
- **Publisher:** `cleanSession=true` with a Client ID distinct from the subscriber's.

The application can run against a test broker at `tcp://localhost:1883`; it **does not start a broker**. This is a demo of semantics and does not include a transactional outbox or production persistent store.

### 12.1. Project structure

~~~text
src/main/java/demo/mqttsemantics/
    MqttSemanticsApplication.java
    MqttConnectionConfiguration.java
    MqttEndpointConfiguration.java
    MqttEvent.java
    MqttPublishPolicy.java
    MqttEventPublisher.java

src/main/resources/
    application.properties
~~~

The code uses Java 17+, with classes in package `demo.mqttsemantics`. In the snippets, full imports are shown per file; non-`public` classes can be package-private depending on file organization.

### 12.2. application.properties

~~~properties
app.mqtt.broker-url=${MQTT_BROKER_URL:tcp://localhost:1883}

# Subscriber persistent session requires a stable Client ID across restarts,
# while also remaining unique across online instances.
app.mqtt.subscriber-id=${MQTT_SUBSCRIBER_ID:telemetry-subscriber-local-1}
app.mqtt.publisher-id=${MQTT_PUBLISHER_ID:events-publisher-local-1}
~~~

The local demo omits TLS/credentials. When connecting to a production broker, switch the URL to TLS, configure trust certificates/credentials from secrets, and restrict publish/subscribe rights via broker ACLs. Default Client IDs here are **not safe for running multiple replicas simultaneously**.

### 12.3. Spring Boot application

~~~java
package demo.mqttsemantics;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MqttSemanticsApplication {

    public static void main(String[] args) {
        SpringApplication.run(MqttSemanticsApplication.class, args);
    }
}
~~~

### 12.4. Two factories: separate session policies for subscriber and publisher

~~~java
package demo.mqttsemantics;

import org.eclipse.paho.client.mqttv3.MqttConnectOptions;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.mqtt.core.DefaultMqttPahoClientFactory;
import org.springframework.integration.mqtt.core.MqttPahoClientFactory;

@Configuration
class MqttConnectionConfiguration {

    @Bean(name = "subscriberFactory")
    MqttPahoClientFactory subscriberFactory(
            @Value("${app.mqtt.broker-url}") String brokerUrl) {
        return newFactory(brokerUrl, false);
    }

    @Bean(name = "publisherFactory")
    MqttPahoClientFactory publisherFactory(
            @Value("${app.mqtt.broker-url}") String brokerUrl) {
        return newFactory(brokerUrl, true);
    }

    private MqttPahoClientFactory newFactory(
            String brokerUrl, boolean cleanSession) {
        var options = new MqttConnectOptions();
        options.setServerURIs(new String[] {brokerUrl});
        options.setConnectionTimeout(10);
        options.setKeepAliveInterval(30);
        options.setCleanSession(cleanSession);

        var factory = new DefaultMqttPahoClientFactory();
        factory.setConnectionOptions(options);
        return factory;
    }
}
~~~

The two factories do not create publishers or subscribers until adapters consume them. Because both beans share the type `MqttPahoClientFactory`, use `@Qualifier` when injecting to avoid ambiguity.

### 12.5. DTO and QoS/retained policy at the business boundary

~~~java
package demo.mqttsemantics;

record MqttEvent(
        String eventId,
        String deviceId,
        String kind,
        String json) {
}
~~~

~~~java
package demo.mqttsemantics;

import org.springframework.integration.mqtt.support.MqttHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

final class MqttPublishPolicy {

    private MqttPublishPolicy() {}

    static Message<String> toMessage(MqttEvent event) {
        if (event == null
                || event.eventId() == null
                || event.eventId().isBlank()) {
            throw new IllegalArgumentException("Missing eventId");
        }
        if (event.deviceId() == null
                || !event.deviceId().matches("[A-Za-z0-9_-]{1,40}")) {
            throw new IllegalArgumentException("Invalid deviceId");
        }
        if (event.kind() == null
                || event.json() == null
                || event.json().isBlank()) {
            throw new IllegalArgumentException(
                    "Missing event kind or JSON payload");
        }

        String topic;
        int qos;
        boolean retained;

        switch (event.kind()) {
            case "STATE" -> {
                topic = "devices/" + event.deviceId() + "/state";
                qos = 1;
                retained = true;
            }
            case "COMMAND" -> {
                topic = "devices/" + event.deviceId() + "/commands";
                qos = 1;
                retained = false;
            }
            case "TELEMETRY" -> {
                topic = "sensors/" + event.deviceId() + "/temperature";
                qos = 0;
                retained = false;
            }
            default -> throw new IllegalArgumentException(
                    "Unsupported event kind: " + event.kind());
        }

        return MessageBuilder.withPayload(event.json())
                .setHeader(MqttHeaders.TOPIC, topic)
                .setHeader(MqttHeaders.QOS, qos)
                .setHeader(MqttHeaders.RETAINED, retained)
                .setHeader("eventId", event.eventId())
                .build();
    }
}
~~~

**Contract explanation:**

1. Internal messages contain JSON text; the demo assumes JSON was produced from a trusted DTO. In production, actually serialize/validate JSON, and ensure `eventId` is present **inside the payload** if MQTT subscribers need to read it.
2. `deviceId` uses a restricted character set, disallowing `/`, `+`, or `#` from altering topic structure.
3. The policy chooses QoS/retained **per data kind**, avoiding a single default for all events.
4. `MqttHeaders.TOPIC` is the outbound MQTT topic, not a `MessageChannel` name.
5. `eventId` is only an internal Spring header in this snippet; in MQTT v3, application headers do not automatically become MQTT broker metadata.

Retained state helps new subscribers obtain snapshots, yet also risks stale state if the state-publishing flow is inconsistent. For commands, `retained=false` prevents new subscribers from receiving old one-time commands.

### 12.6. Configuring channels, inbound adapter, and outbound handler

~~~java
package demo.mqttsemantics;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.mqtt.core.MqttPahoClientFactory;
import org.springframework.integration.mqtt.inbound.MqttPahoMessageDrivenChannelAdapter;
import org.springframework.integration.mqtt.outbound.MqttPahoMessageHandler;
import org.springframework.integration.mqtt.support.DefaultPahoMessageConverter;
import org.springframework.integration.mqtt.support.MqttHeaders;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHandler;

@Configuration
@EnableIntegration
class MqttEndpointConfiguration {

    @Bean(name = "mqtt.publish.requests")
    MessageChannel publishRequests() {
        return new DirectChannel();
    }

    @Bean(name = "mqtt.telemetry.in")
    MessageChannel telemetryInput() {
        return new DirectChannel();
    }

    @Bean
    MqttPahoMessageDrivenChannelAdapter telemetryAdapter(
            @Qualifier("subscriberFactory") MqttPahoClientFactory factory,
            @Qualifier("mqtt.telemetry.in") MessageChannel channel,
            @Value("${app.mqtt.subscriber-id}") String clientId) {

        var adapter = new MqttPahoMessageDrivenChannelAdapter(
                clientId, factory, "sensors/+/temperature");
        adapter.setQos(1);
        adapter.setRecoveryInterval(10000);
        adapter.setConverter(new DefaultPahoMessageConverter());
        adapter.setOutputChannel(channel);
        return adapter;
    }

    @Bean(name = "mqttPublisher")
    MqttPahoMessageHandler publisher(
            @Qualifier("publisherFactory") MqttPahoClientFactory factory,
            @Value("${app.mqtt.publisher-id}") String clientId) {

        var handler = new MqttPahoMessageHandler(clientId, factory);
        handler.setDefaultTopic("demo/unrouted");
        handler.setDefaultQos(1);
        handler.setDefaultRetained(false);
        handler.setConverter(new DefaultPahoMessageConverter());
        handler.setAsync(false);
        handler.setCompletionTimeout(5000);
        return handler;
    }

    @Bean
    IntegrationFlow outboundFlow(
            @Qualifier("mqttPublisher") MessageHandler publisher) {
        return IntegrationFlow.from("mqtt.publish.requests")
                .handle(publisher)
                .get();
    }

    @Bean
    IntegrationFlow inboundTelemetryFlow() {
        return IntegrationFlow.from("mqtt.telemetry.in")
                .handle(String.class, (payload, headers) -> {
                    System.out.println(
                            "MQTT topic="
                            + headers.get(MqttHeaders.RECEIVED_TOPIC)
                            + " payload length=" + payload.length());
                    return null;
                })
                .get();
    }
}
~~~

Here:

- `subscriberFactory` uses `cleanSession=false`, while `publisherFactory` uses `cleanSession=true`.
- The inbound adapter subscribes at QoS 1, yet when the publisher sends telemetry at QoS 0, the broker → subscriber leg can still deliver at QoS 0.
- The outbound handler reads QoS/retained **per message** from `MqttHeaders.QOS` and `MqttHeaders.RETAINED`; defaults are only fallbacks.
- `inboundTelemetryFlow` processes via MQTT callbacks, **with no `@Poller`**.
- `outboundFlow` uses `DirectChannel`; with sync publishing, the sending thread can block waiting for completion.
- Default topic `demo/unrouted` is only to demonstrate fallback in the demo; for production commands, missing `MqttHeaders.TOPIC` should be rejected before the handler instead of falling back to a default topic.

### 12.7. Service emitting messages

~~~java
package demo.mqttsemantics;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.stereotype.Service;

@Service
class MqttEventPublisher {

    private final MessageChannel channel;

    MqttEventPublisher(
            @Qualifier("mqtt.publish.requests") MessageChannel channel) {
        this.channel = channel;
    }

    boolean publish(MqttEvent event) {
        return channel.send(MqttPublishPolicy.toMessage(event));
    }
}
~~~

Callers can send a snapshot:

~~~java
publisher.publish(new MqttEvent(
        "evt-state-1001",
        "device-17",
        "STATE",
        "{\"eventId\":\"evt-state-1001\",\"state\":\"ON\"}"));
~~~

or a command:

~~~java
publisher.publish(new MqttEvent(
        "cmd-1001",
        "device-17",
        "COMMAND",
        "{\"commandId\":\"cmd-1001\",\"action\":\"TURN_OFF\"}"));
~~~

The STATE message publishes to `devices/device-17/state` with QoS 1 and `retained=true`; COMMAND publishes to `devices/device-17/commands` with QoS 1 and `retained=false`. This requires a running broker with appropriate publish/subscribe permissions.

**Do not treat the boolean returned by `publish(...)` as a business ACK.** It reflects handing the message off to the Spring channel, not confirmation that the device executed the command.

## 13. Testing QoS/retained policy without an MQTT broker

Decoupling MQTT transport from the flow keeps unit/integration tests fast and reliable. With `MqttPublishPolicy` standalone, topic, QoS, and retained values can be tested directly. To verify Spring wiring, supply a **fake `MessageHandler`** in place of the Paho publisher.

Add the test dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

For a brokerless test, create a Spring context containing only the channel + outbound flow and the fake publisher; **do not load `MqttConnectionConfiguration` or the demo inbound adapter**.

~~~java
package demo.mqttsemantics;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.mqtt.support.MqttHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHandler;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = {
        MqttOutboundTestConfiguration.class,
        RecordingMqttPublisherConfiguration.class
})
class MqttPublishPolicyTest {

    @Autowired
    @Qualifier("mqtt.publish.requests")
    MessageChannel input;

    @Autowired
    RecordingMqttPublisher recorded;

    @BeforeEach
    void reset() {
        recorded.clear();
    }

    @Test
    void stateIsRetainedWithQosOne() {
        MqttEvent event = new MqttEvent(
                "evt-test-state", "device-17", "STATE",
                "{\"eventId\":\"evt-test-state\",\"state\":\"ON\"}");

        assertTrue(input.send(MqttPublishPolicy.toMessage(event)));
        assertEquals(List.of(new SentMqtt(
                "devices/device-17/state", 1, true, event.json())),
                recorded.snapshot());
    }

    @Test
    void commandIsNotRetained() {
        MqttEvent event = new MqttEvent(
                "cmd-test-1", "device-17", "COMMAND",
                "{\"commandId\":\"cmd-test-1\",\"action\":\"TURN_OFF\"}");

        assertTrue(input.send(MqttPublishPolicy.toMessage(event)));
        assertEquals(List.of(new SentMqtt(
                "devices/device-17/commands", 1, false, event.json())),
                recorded.snapshot());
    }

    @Test
    void telemetryUsesQosZeroWithoutRetained() {
        MqttEvent event = new MqttEvent(
                "evt-temp-1", "device-17", "TELEMETRY",
                "{\"eventId\":\"evt-temp-1\",\"celsius\":26.5}");

        assertTrue(input.send(MqttPublishPolicy.toMessage(event)));
        assertEquals(List.of(new SentMqtt(
                "sensors/device-17/temperature", 0, false,
                event.json())),
                recorded.snapshot());
    }
}

record SentMqtt(String topic, int qos, boolean retained,
                String payload) {}

class RecordingMqttPublisher implements MessageHandler {

    private final List<SentMqtt> messages =
            new CopyOnWriteArrayList<>();

    @Override
    public void handleMessage(Message<?> message) {
        messages.add(new SentMqtt(
                (String) message.getHeaders().get(MqttHeaders.TOPIC),
                (Integer) message.getHeaders().get(MqttHeaders.QOS),
                (Boolean) message.getHeaders().get(MqttHeaders.RETAINED),
                (String) message.getPayload()));
    }

    List<SentMqtt> snapshot() {
        return List.copyOf(messages);
    }

    void clear() {
        messages.clear();
    }
}

@Configuration
@EnableIntegration
class MqttOutboundTestConfiguration {

    @Bean(name = "mqtt.publish.requests")
    MessageChannel publishRequests() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow outboundFlow(
            @Qualifier("mqttPublisher") MessageHandler publisher) {
        return IntegrationFlow.from("mqtt.publish.requests")
                .handle(publisher)
                .get();
    }
}

@Configuration
class RecordingMqttPublisherConfiguration {

    @Bean(name = "mqttPublisher")
    RecordingMqttPublisher recordingPublisher() {
        return new RecordingMqttPublisher();
    }
}
~~~

What the test verifies:

1. Topics are built per event kind and device ID.
2. State uses QoS 1, `retained=true`.
3. Command uses QoS 1, `retained=false`.
4. Telemetry uses QoS 0, `retained=false`.
5. Messages actually traverse the Spring channel and flow into the handler bean.

**Limitation:** the fake handler does not use Paho, connect to a broker, or test session/offline delivery, PUBACKs, or retained storage. Those require broker-backed tests.

### 13.1. Additional unit tests worth writing

- Missing `eventId`, `deviceId`, `kind`, or JSON: policy must reject before publishing.
- `deviceId` containing `/`, `+`, or `#`: no topic created.
- A command whose JSON lacks a matching `commandId`: schema validation must reject at the application layer after JSON parsing.
- An inbound callback with `RETAIN=true` where a fake handler treats it as a new event: test snapshot vs. event rules.
- An event retried after a routing policy change: verify fixed `eventId` and route decision per contract.

## 14. Testing QoS, retained, and sessions with a real MQTT broker

To verify protocol behavior, you need a test broker. The following examples use `mosquitto_pub`/`mosquitto_sub` and a local broker on `localhost:1883`. These are standalone test commands, not commands to run on a production broker.

### 14.1. Retained snapshot delivered to a new subscriber

**Terminal A – publish retained state:**

~~~bash
mosquitto_pub -h localhost -p 1883 \
  -t 'devices/device-17/state' \
  -q 1 -r \
  -m '{"eventId":"evt-state-1","state":"ON"}'
~~~

**Terminal B – subscribe after publishing:**

~~~bash
mosquitto_sub -h localhost -p 1883 \
  -t 'devices/+/state' -q 1 -v
~~~

The new subscriber receives the retained state `ON` even though the publication occurred **before** it subscribed.

**Test replacing retained state:**

~~~bash
mosquitto_pub -h localhost -p 1883 \
  -t 'devices/device-17/state' \
  -q 1 -r \
  -m '{"eventId":"evt-state-2","state":"OFF"}'
~~~

When a new subscriber subscribes, the snapshot is `OFF`. This illustrates that retained holds the latest value, not a history of `ON` and `OFF`.

**Delete retained state when authorized:**

~~~bash
mosquitto_pub -h localhost -p 1883 \
  -t 'devices/device-17/state' \
  -q 1 -r -n
~~~

After deletion, new subscribers should no longer receive the old retained snapshot on that topic. Only run this on test brokers/topics you control.

### 14.2. Testing persistent sessions while the subscriber is offline

This test requires a broker configured to permit persistent sessions. **Step 1:** start a subscriber with a fixed Client ID and clean session disabled (per Mosquitto CLI):

~~~bash
mosquitto_sub -h localhost -p 1883 \
  -i durable-temperature-1 -c \
  -q 1 -t 'sensors/+/temperature' -v
~~~

**Step 2:** stop the subscriber with Ctrl+C once the subscription is established.

**Step 3:** while the subscriber is offline, publish a non-retained QoS 1 message:

~~~bash
mosquitto_pub -h localhost -p 1883 \
  -t 'sensors/device-17/temperature' \
  -q 1 \
  -m '{"eventId":"evt-offline-1","celsius":27.5}'
~~~

**Step 4:** run the **same** subscriber command again with Client ID `durable-temperature-1`, `-c`, and the same topic/QoS. If the broker kept the session/subscription and message per its policy, the subscriber receives the offline message.

For comparison, repeat the scenario with a new Client ID or default clean session; the new subscriber has no prior session backlog, except for any retained snapshot created in another test.

**Accurate conclusion:** receiving offline messages depends on the active session, subscription QoS, publish QoS, broker policy/storage, and reconnecting with the same Client ID. Never assume from `-c` alone that every message will be stored indefinitely.

### 14.3. Testing duplicates, QoS downgrade, and restarts

| Scenario | How to perform | Expected conclusion |
| --- | --- | --- |
| Publisher QoS 1, subscriber QoS 0 | Publish `-q 1`, subscribe `-q 0`. | Delivery leg to subscriber can be QoS 0; publisher QoS does not force subscription QoS. |
| QoS 1 network drop | Simulate disconnect/lost ACK, reconnect. | Redelivery can occur; business handler must deduplicate. |
| QoS 2 | Publish/subscribe at QoS 2. | Measure overhead and infer exactly-once only at the MQTT protocol layer. |
| Retained STATE | Publish `-r`, then create a new subscription. | New subscriber receives the stored snapshot. |
| Non-retained COMMAND | Publish command without `-r`, subscribe afterward. | New subscriber does not receive past commands as retained snapshots. |
| Clean session true | Subscriber offline during publish. | No backlog from a previous persistent session. |
| Clean session false | Subscriber restarts with same ID, QoS 1/2. | Subscription/backlog may recover if broker supports it. |
| Duplicate Client ID | Two active subscribers use the same ID. | Risk of kicking each other off; do not use as competing consumers. |
| Broker restart | Restart the broker during the test. | Verify real session/retained persistence; do not assume durability blindly. |

**Environment note:** tests involving restarts/reconnects/ACLs require a broker you control. When a broker requires TLS/authentication, use dedicated test certificates and credentials; never lower production broker security to run demos.

## 15. Error handling, retries, and idempotency

These three MQTT settings are not enough to guarantee an entire Spring Integration pipeline finishes cleanly. A flow can fail at multiple layers:

~~~mermaid
flowchart TD
    SRC["Publisher / Adapter source"]
    MQTT["MQTT transport<br/>QoS, retained, session"]
    B[("MQTT broker")]
    SUB["Spring MQTT inbound adapter"]
    CH["MessageChannel"]
    H["Business handler / DB / HTTP"]
    OK["Record business success"]
    ERR["Retry / error channel / DLQ / quarantine"]
    SRC --> MQTT --> B --> SUB --> CH --> H --> OK
    MQTT -. "disconnect / timeout" .-> ERR
    SUB -. "converter / dispatch" .-> ERR
    H -. "DB/HTTP error" .-> ERR
~~~

| Failure | Do QoS/retained/clean session solve it? | What else is needed? |
| --- | --- | --- |
| TCP disconnect during QoS 0 publish | No QoS 1/2 ACK or redelivery. | Decide whether data loss is acceptable or add an outbox/retry. |
| Delayed/lost MQTT PUBACK | QoS 1/2 have protocol mechanics, yet duplicates/uncertain outcomes remain. | `eventId`/idempotency, backoff, and reconciliation. |
| Subscriber offline | Persistent sessions can buffer QoS 1/2; retained provides the last snapshot. | Broker/session TTL policies, backlog limits, and monitoring. |
| Malformed JSON schema | No. | Parse/validate, reject/quarantine, do not retry bad data infinitely. |
| DB write fails after MQTT delivery | Does not roll back MQTT ACK or broker state. | Dedicated transaction, error flow, source replay, and idempotency. |
| Publisher re-emits the same business command | No; two separate publishes can share one business ID. | `commandId` and subscriber-side deduplication. |
| Old retained command triggers a new device | `RETAIN` creates this risk. | `retained=false`, expiry/nonce/versioning, and business ACK. |
| Spring in-memory queue lost on restart | Clean session does not protect RAM queues. | Persistent message store/broker/outbox. |

### 15.1. Why delivery acknowledgment and business acknowledgment must be separated

~~~mermaid
sequenceDiagram
    participant APP as Publisher app
    participant B as MQTT broker
    participant DEVICE as Device / Subscriber
    participant DB as Business state
    APP->>B: PUBLISH(cmd-1001, QoS=1)
    B-->>APP: PUBACK (MQTT delivery)
    B->>DEVICE: PUBLISH(cmd-1001)
    DEVICE->>DB: Execute / persist state
    DEVICE-->>APP: Dedicated business ACK (ACK topic)
~~~

PUBACK only reflects one protocol leg—it does not prove `DEVICE → DB` succeeded. If the business ACK has not arrived, the caller cannot simply conclude the command did not run; it may have run while the ACK was lost. Store `commandId`, status, timeouts, controlled retries, and the ability to query target state.

### 15.2. Transactional outbox and replay

A pattern worth considering for critical commands/events:

1. Write the business record and outbox record in the same database transaction.
2. The outbox stores `eventId`/`commandId`, payload, topic, QoS, retained, and send status.
3. A worker reads the outbox and publishes via MQTT with retries/backoff.
4. Mark the publication according to the MQTT confirmation level, but **never mark the device as processed** before the business ACK arrives.
5. Subscribers use idempotency keys/unique constraints so duplicates from the broker or app do not repeat side effects.
6. On replay, preserve the original `eventId` and chosen topic/retained policy, or store the rule version if routing can evolve.

If the worker crashes after publishing but before updating the outbox, the event may be re-sent. That is why idempotency remains necessary even with QoS 2.

## 16. Security, lifecycle, and multi-instance scaling

### 16.1. Client IDs and sessions across replicas

With `cleanSession=false`, the Client ID is the key to resuming a session. If every restart generates a random Client ID, the subscriber fails to resume its prior session while also leaving orphaned sessions on the broker until cleaned up. Yet if multiple replicas share one Client ID simultaneously, the broker can disconnect existing connections.

Choose deliberately:

- **One logical pinned consumer:** stable Client ID, only one active instance using that ID at a time.
- **Multiple independent subscribers:** distinct Client IDs, each with its own session and subscriptions.
- **Load-sharing one stream:** use shared subscriptions when supported by the broker/protocol or a queue architecture—never share a Client ID across processes to fake load balancing.
- **HA setup:** verify whether the cluster preserves sessions/retained state across failover; multiple broker URIs do not imply independent brokers share state.

### 16.2. Retained data and access control

A retained snapshot can be delivered to a new subscriber **long after the original publication**. Therefore:

- Never retain secrets/tokens, high-privilege commands, or sensitive data inappropriately.
- Restrict topic ACLs so unauthorized clients cannot subscribe to state topics.
- Validate device/tenant IDs in topics and payloads.
- Define retention/clear-retained procedures when devices are deleted, transferred between tenants, or lose permissions.
- Monitor retained topic cardinality and broker quotas.

### 16.3. TLS, connections, and callback threads

`MqttConnectOptions` should use TLS and proper credentials/ACLs in production. When an inbound adapter sends messages to a `DirectChannel`, blocking downstream work stretches callback execution time; if you decouple using `QueueChannel` or `ExecutorChannel`, design capacity bounds, error paths, persistence, and shutdown carefully.

Never treat `cleanSession=false` as a backpressure solution. Broker backlog and Spring queue backlog live in different layers. Monitor message lag, in-flight counts, reconnects, CPU/thread pools, broker quotas, and database latency.

## 17. Common configuration mistakes

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| New subscriber receives old message right after subscribing. | Broker holds a retained snapshot. | Inspect received retained metadata, event timestamp, and retained policy. |
| Retained state shows ON even though device just sent OFF. | OFF publication used `RETAIN=false`, leaving the snapshot unchanged. | Publish the new state with `retained=true` or clear the snapshot properly. |
| Offline subscriber misses data upon reconnecting. | `cleanSession=true`, QoS 0, Client ID changed, never subscribed, or broker did not retain session. | Check Client ID, clean session, QoS on both legs, broker storage, and subscriptions. |
| Two replicas reconnect continuously. | Shared MQTT Client ID. | Assign unique IDs or run one active logical subscriber. |
| QoS 1 produces duplicate rows in DB. | Redelivery/retry without idempotency. | Unique constraint on event ID and duplicate checking. |
| QoS 2 still creates two orders. | Publisher sent two separate publications with the same business meaning. | Deduplicate by order/command ID, not just QoS. |
| Device re-executes an old command after subscribing. | Command used `RETAIN=true`. | Use `retained=false`, clean up stale retained messages, enforce replay/expiry checks. |
| Inbound `setQos(1)` receives QoS 0. | Publisher published at QoS 0. | Check QoS on both publisher and subscriber. |
| `cleanSession=false` loses events after broker restart. | Broker does not persist sessions/messages per policy or exceeded quota. | Verify broker persistence/quotas/failover tests; add an outbox. |
| Application restart loses queued messages. | Default `QueueChannel` lives in RAM. | Use a persistent store/outbox; clean session does not protect Spring queues. |
| MQTT ACK received, yet business handler never ran. | MQTT delivery and business processing are separate stages. | Implement business ACKs, retries, and downstream observability. |
| Retained topic accidentally wiped. | Zero-length retained message published to a production topic. | Restrict permissions, audit, and control cleanup commands. |

## 18. Practice exercise

**Scenario:** an IoT system receives temperature readings over MQTT and sends turn-on/turn-off commands to air conditioners. Temperature readings may tolerate occasional sample loss, new subscribers need the latest state, and air-conditioner commands must not execute repeatedly.

Tasks:

1. Design topics `sensors/{deviceId}/temperature`, `devices/{deviceId}/state`, `devices/{deviceId}/commands`, and `devices/{deviceId}/ack`.
2. Select QoS and retained settings for each topic and explain why one-time commands are not retained.
3. Create `MqttPahoClientFactory` beans for subscriber (`cleanSession=false`) and publisher (`cleanSession=true`).
4. Choose a stable Client ID for the subscriber without sharing it across replicas.
5. Register an inbound adapter at QoS 1 with output channel `mqtt.telemetry.in`; write a JSON parsing/validation flow.
6. Register an outbound handler consuming from `mqtt.publish.requests`, setting `MqttHeaders.QOS`, `RETAINED`, and `TOPIC` headers by event kind.
7. Write brokerless tests verifying QoS/retained policies for STATE, COMMAND, TELEMETRY, and invalid inputs.
8. Publish a retained state, create a new subscription, confirm the snapshot arrives; publish a non-retained state and explain why the earlier snapshot remains.
9. Clear the retained snapshot on that topic in the test broker and verify new subscribers no longer receive stale state.
10. Test persistent sessions: subscribe with a fixed Client ID and `clean=false`, go offline, publish QoS 1, reconnect, and verify backlog delivery per broker policy.
11. Test publisher QoS 1 / subscriber QoS 0 and explain the effective QoS on the delivery leg.
12. Simulate a command executed by the device whose business ACK is lost; design retries by command ID without causing a second side effect.
13. Add an outbox or dedicated replay store for data that must survive app crashes.

**Completion criteria:** clearly distinguish retained snapshots from offline queued messages, explain Client ID/session behavior, prove QoS does not replace DB transactions, and have tests reflect the three states **MQTT_DELIVERED**, **BUSINESS_PROCESSED**, and **BUSINESS_ACKNOWLEDGED**.

## 19. Self-check questions

1. How do MQTT QoS 0, 1, and 2 differ in handshakes and duplicate risk?
2. Does QoS 2 guarantee that a database transaction commits only once?
3. Publisher uses QoS 1 and subscriber uses QoS 0: which QoS does the broker typically deliver at?
4. Do retained messages store full history or only the latest snapshot for a topic?
5. If a publisher sends `RETAIN=false` to a topic that already has a retained message, is the old snapshot deleted?
6. How do you delete retained state in MQTT 3.1.1?
7. Why can a retained one-time command be dangerous?
8. Does `cleanSession=true` make the broker forget retained messages across all topics?
9. Besides `cleanSession=false`, what conditions are required for a subscriber to receive QoS 1/2 events missed while offline?
10. Why does changing the Client ID on restart break expected persistent session behavior?
11. Are two replicas sharing the same Client ID equivalent to a competing-consumers group?
12. How does inbound `setQos(1)` differ from outbound `setDefaultQos(1)`?
13. When Spring Integration receives an MQTT message and the DB handler fails, does MQTT PUBACK automatically roll back with the DB?
14. How do you distinguish a retained snapshot from a new event and a duplicate delivery?
15. When using `QueueChannel` in Spring, does clean session protect messages sitting in RAM?
16. Why do commands need a business ACK on a separate topic?
17. Can a QoS 1 publication reach the broker even though the publisher hits a timeout?
18. When a broker fails over to an independent node, are persistent sessions guaranteed to remain intact?
19. Why should `eventId` be included in the MQTT v3 payload instead of only in a Spring header?
20. In a multi-tenant system, what authorization and cleanup controls does retained state require?

**Hint:** QoS governs handshakes on MQTT legs, retained provides per-topic snapshots, and clean session governs MQTT 3.1.1 session lifecycle. None of these guarantees replace idempotency, an outbox, or business ACKs.

## 20. Conclusion

**QoS, retain, and clean session are three distinct MQTT mechanisms**:

- **QoS 0/1/2** governs how publications are delivered at the MQTT layer, offering at-most-once, at-least-once, and protocol-level exactly-once semantics.
- **RETAIN** determines whether the broker keeps the latest snapshot on a topic for new subscribers; retained does not store full event history.
- **Clean session** in MQTT 3.1.1 determines whether sessions/subscriptions persist across disconnects for a stable Client ID; it is not a durable persistence option for Spring Integration.

In the **SPRING_INTEGRATION_ADAPTERS** module, using these mechanisms must align with inbound/outbound MQTT adapters, `MessageChannel`, processing flows, and message contracts. Sound configuration requires choosing **QoS on both publisher and subscriber**, **retained per data type**, **Client ID/session per lifecycle**, plus **error handling, backpressure, idempotency, and real broker testing**. Only by combining these pieces and verifying target side effects can an MQTT integration be deemed reliable for business workloads.
