# Delivery tokens and publish confirmation

## 1. The problem: what does "sent successfully" really mean?

A service sends a `TURN_ON` command to a device over MQTT and sees `MessageChannel.send(...)` return `true`. Can it immediately update the database to `COMPLETED`? **No.** The system has at least four distinct confirmation levels:

1. Spring accepted and dispatched the message to an internal endpoint.
2. The MQTT client accepted the PUBLISH request and may issue a **delivery token**.
3. The MQTT broker completed receiving the publication per the **QoS** level used.
4. The subscriber/device processed the content, sent a **business ACK**, and the backend verified and persisted the result.

This lesson, **"Delivery tokens and publish confirmation,"** belongs to the **Adapter MQTT** chapter of the **SPRING_INTEGRATION_ADAPTERS** module. The module focuses on connecting external systems via inbound/outbound adapters, gateways, pollers, and `MessageChannel`; practicing with files, SFTP, HTTP, JMS, AMQP, Kafka, and databases while managing message contracts, errors, and connection lifecycles.

After completing this lesson, readers will be able to:

- Distinguish `IMqttDeliveryToken`, `waitForCompletion(...)`, the `deliveryComplete(...)` callback, MQTT `PUBACK`/`PUBCOMP`, and business ACKs.
- Understand how QoS 0/1/2 affect token completion meaning and duplicate risk.
- Configure `MqttPahoMessageHandler` for synchronous or asynchronous publishing and bound `completionTimeout`.
- Observe Spring Integration MQTT Sent/Delivered events in supporting versions without mistaking them for business confirmation.
- Design message IDs/correlation, outboxes, retries on uncertain outcomes, idempotent subscribers, and dedicated ACK topics.
- Build a Java Spring Boot flow sending MQTT commands, receiving ACKs, writing brokerless tests, and testing controlled broker failures.

**Technical scope:** code examples use Spring Integration MQTT with the Eclipse Paho **MQTT v3 API** and MQTT 3.1.1. Event/callback behavior depends on the deployed version. MQTT v5 has different APIs, metadata, and certain protocol semantics; do not mix v3 examples in without adapting them.

## 2. Four milestones in a publish transaction

~~~mermaid
sequenceDiagram
    participant APP as Business service
    participant CH as Spring MessageChannel
    participant H as MQTT outbound handler
    participant P as Eclipse Paho client
    participant B as MQTT broker
    participant D as Device
    APP->>CH: send(commandId=cmd-1001)
    CH->>H: dispatch Spring Message
    H->>P: publish(topic, payload, qos=1)
    Note over APP,P: Internal handoff and Paho token
    P->>B: PUBLISH QoS 1
    B-->>P: PUBACK
    Note over P,B: MQTT publish completion for this leg
    B->>D: PUBLISH command
    D->>D: Validate, execute action
    D->>B: PUBLISH ACK(commandId, result)
    B-->>APP: ACK via separate MQTT inbound flow
~~~

| Milestone | Signal | What you can conclude | What you cannot conclude |
| --- | --- | --- | --- |
| Spring handoff | `MessageChannel.send()` returns `true` | Channel accepted the send per channel/consumer semantics. | That the broker received the publication. |
| Paho accepted | `IMqttDeliveryToken` exists | An MQTT publish operation has a tracking handle. | That publishing has completed. |
| MQTT publish complete | Token/callback/event completes per QoS | The MQTT publisher→broker leg met client/protocol completion conditions. | That the subscriber committed DB or the device acted. |
| Business acknowledged | Valid ACK with `commandId`, DB updated | Business processing was confirmed per contract. | That out-of-contract side effects are consistent unless reconciled. |

**Mistake to avoid:** using `token.isComplete()` or `MqttMessageDeliveredEvent` to update `device_commands.status = APPLIED`. Neither inspects the device's hardware or the subscriber's database.

### 2.1. Broker ACK is not subscriber ACK

MQTT QoS provides handshakes on the **publisher ↔ broker** leg and the **broker ↔ subscriber** leg under their separate subscriptions/QoS levels. A publisher receives no list of subscribers that processed a message; it does not automatically know which devices are online or whether a command will be delivered after an offline period.

### 2.2. MQTT topics vs. Spring MessageChannels

~~~text
Spring channel: mqtt.commands.out
MQTT broker URI: ssl://broker.example.net:8883
MQTT publish topic: devices/device-17/commands
Business ACK topic: devices/device-17/ack
~~~

`MessageChannel` connects internal Spring producers and endpoints; an MQTT topic is a broker distribution target. Never send commands to wildcard topics like `devices/+/commands`: wildcards are for **subscription filters**, not PUBLISH topic names.

## 3. What is IMqttDeliveryToken in Eclipse Paho?

`IMqttDeliveryToken` tracks **a single Paho MQTT publish operation**. When calling the asynchronous publish API, the client returns a token before the broker sends an ACK.

~~~java
import org.eclipse.paho.client.mqttv3.IMqttDeliveryToken;

IMqttDeliveryToken token = client.publish(
        "devices/device-17/commands",
        payloadBytes,
        1,
        false);
~~~

You can observe the token:

~~~java
token.waitForCompletion(5000); // milliseconds
boolean complete = token.isComplete();
int packetId = token.getMessageId();
~~~

Distinct concepts:

| Artifact | Role | Limitation |
| --- | --- | --- |
| `IMqttToken` | Generic token interface for various MQTT async operations. | Not exclusive to PUBLISH. |
| `IMqttDeliveryToken` | Token bound to delivery/PUBLISH. | Runtime-local; not a durable business record. |
| MQTT packet identifier | Protocol-level transaction ID, e.g., `57`. | Can be reused within client/session; not globally unique. |
| `commandId`/`eventId` | Application-assigned and persisted business ID. | Must be present in the payload/contract for external consumers. |
| Spring `Message<?>` | Payload + headers in internal flows. | Does not automatically carry all Spring headers across MQTT v3. |

**Never store `token.getMessageId()` as the primary key of a business commands table.** Packet IDs get reused, and a process restart cannot recover the prior in-memory token object. You need a `commandId` that stays stable across retries, reconnects, and restarts.

### 3.1. A returned token does not mean completion

Once a PUBLISH is accepted for asynchronous processing, the token may start incomplete. Depending on the API, `waitForCompletion(...)` blocks the calling thread up to a timeout and then completes or throws an exception.

Do not read `isComplete()` once immediately after `publish(...)` and declare "message lost" if it is still `false`. The publication may simply be waiting on the broker or the client network worker.

### 3.2. When waitForCompletion times out

If completion is not observed before the timeout, the publisher-side outcome is **uncertain**:

- The PUBLISH may not have left the client.
- The broker may have received it while PUBACK/PUBCOMP was blocked or delayed.
- The broker may have completed while the client/process failed to record it in time.
- The broker may have delivered the message to the subscriber while the application only sees an exception.

**A timeout does not cancel a message already received by the broker.** Therefore, retries after a timeout must keep the same `commandId`/`eventId`, and consumers must be idempotent.

## 4. Standalone example: Paho async client and delivery token

Before examining Spring Integration, look at the raw Paho API. This is a standalone demo client; **do not** instantiate extra raw Paho clients inside handlers managed by Spring.

~~~java
package demo.mqttdelivery;

import java.nio.charset.StandardCharsets;

import org.eclipse.paho.client.mqttv3.IMqttDeliveryToken;
import org.eclipse.paho.client.mqttv3.MqttAsyncClient;
import org.eclipse.paho.client.mqttv3.MqttConnectOptions;

public class RawPahoTokenDemo {

    public static void main(String[] args) throws Exception {
        String broker = "tcp://localhost:1883";
        var client = new MqttAsyncClient(
                broker, "raw-paho-publisher-local-1");

        var options = new MqttConnectOptions();
        options.setConnectionTimeout(10);
        options.setKeepAliveInterval(30);
        options.setCleanSession(true);

        try {
            client.connect(options).waitForCompletion(10000);

            String json = "{\"commandId\":\"cmd-1001\","
                    + "\"action\":\"TURN_ON\"}";

            IMqttDeliveryToken token = client.publish(
                    "devices/device-17/commands",
                    json.getBytes(StandardCharsets.UTF_8),
                    1,
                    false);

            token.waitForCompletion(5000);

            System.out.println(
                    "Publish complete=" + token.isComplete()
                    + ", packetId=" + token.getMessageId());
        } finally {
            if (client.isConnected()) {
                client.disconnect().waitForCompletion(5000);
            }
            client.close();
        }
    }
}
~~~

Steps:

1. Client opens a connection to the test broker.
2. `publish(...)` issues a QoS 1, `retained=false` PUBLISH and returns a token.
3. `waitForCompletion(5000)` waits up to 5 seconds for Paho completion.
4. If no timeout/error occurs, code inspects `isComplete()`/packetId for technical logging.
5. `disconnect()`/`close()` releases the connection on normal exit.

A broker at `localhost:1883` must already be running; the demo does not start a broker. In production, use TLS, certificates/authentication/ACLs, and unique Client IDs across active clients. Never reuse the same Client ID across replicas as in a local demo.

### 4.1. Comparing a token to a business request "future"

A Paho token is a handle for a protocol operation, not a `CompletableFuture<BusinessResult>`. Token completion carries no `APPLIED` status from the device, and no Paho wait call injects a JSON business ACK from another topic into the token result.

### 4.2. Timeouts and retries

~~~text
PUBLISH commandId=cmd-1001 → broker received
PUBACK lost on return path
waitForCompletion(5000) → timeout
Caller re-sends cmd-1001
Device may see cmd-1001 twice
~~~

If the caller re-sends using `cmd-1002`, the system **cannot easily tell** that both attempts represent one business command. Keep `cmd-1001`, enforce idempotency, and reconcile ACKs before issuing unnecessary retries.

## 5. The deliveryComplete callback and asynchrony

Paho MQTT v3 provides `MqttCallback.deliveryComplete(IMqttDeliveryToken)`. On a raw Paho client, the callback signals completion without blocking the caller via `waitForCompletion(...)`.

~~~java
import org.eclipse.paho.client.mqttv3.IMqttDeliveryToken;
import org.eclipse.paho.client.mqttv3.MqttCallback;
import org.eclipse.paho.client.mqttv3.MqttMessage;

client.setCallback(new MqttCallback() {

    @Override
    public void connectionLost(Throwable cause) {
        System.err.println("Connection lost: " + cause);
    }

    @Override
    public void messageArrived(String topic, MqttMessage message) {
        // Unused in non-subscribing publisher demo.
    }

    @Override
    public void deliveryComplete(IMqttDeliveryToken token) {
        System.out.println("Delivery complete: "
                + token.getMessageId());
    }
});
~~~

Register the callback on the raw Paho client **before connecting**. Never overwrite the internal callback of a Spring MQTT adapter, because Spring relies on its own callback for lifecycle, channel dispatch, and error handling.

| Observation mechanism | Characteristics | Key caveat |
| --- | --- | --- |
| `waitForCompletion(...)` | Thread waits for completion or timeout. | Blocks the caller and can leave uncertain outcomes. |
| `deliveryComplete(...)` | Notification emitted via client callback. | May arrive later on another thread; not durable across crashes. |
| Spring async events | Observed from `MqttPahoMessageHandler` where supported. | Not every configuration emits events by default; test on your version. |
| Business ACK topic | Separate MQTT publication from subscriber/device. | Requires schema, identity/correlation, and a dedicated DB commit. |

### 5.1. A callback is not a transactional log

A callback can arrive and the application can crash before persisting state. On restart, the in-memory Paho token object is gone while the broker may already have received the message. Persist callback outcomes into a durable outbox **whenever possible**, paired with reconciliation for uncertain states; a callback alone never forms an atomic commit with the broker.

### 5.2. Do not block inside the callback thread

Inside a callback, record brief metadata or hand off to a bounded queue/handler. Slow HTTP calls, DB locks, or `Thread.sleep(...)` inside a callback stall network I/O and complicate recovery. Business flows need backpressure and retry/error policies in their own layer.

## 6. QoS 0, 1, 2 and what completion means

### 6.1. QoS 0: no broker PUBACK

~~~mermaid
sequenceDiagram
    participant P as Publisher
    participant B as Broker
    P->>B: PUBLISH QoS 0
    Note over P,B: No PUBACK/PUBCOMP for this PUBLISH
~~~

The client's token may complete per Paho semantics, yet **QoS 0 has no broker ACK like QoS 1**. Never treat QoS 0 completion as a guarantee that the broker received or a subscriber read the message.

QoS 0 fits high-frequency telemetry when occasional sample loss is acceptable.

### 6.2. QoS 1: PUBLISH → PUBACK

~~~mermaid
sequenceDiagram
    participant P as Publisher
    participant B as Broker
    P->>B: PUBLISH QoS 1, packetId=57
    B-->>P: PUBACK packetId=57
    Note over P,B: ACK can be lost, causing redelivery
~~~

At QoS 1, completion after PUBACK confirms the publisher→broker leg. QoS 1 allows redelivery when protocol/client retries fire; **two independent publications** can also carry the same `eventId` when higher-level application retries run.

### 6.3. QoS 2: four-step handshake

~~~mermaid
sequenceDiagram
    participant P as Publisher
    participant B as Broker
    P->>B: PUBLISH QoS 2, packetId=57
    B-->>P: PUBREC
    P->>B: PUBREL
    B-->>P: PUBCOMP
~~~

QoS 2 provides protocol-level exactly-once delivery for one publication, yet **does not prove exactly-once side effects in a DB or device**. An application can still issue two separate publish operations representing the same command.

### 6.4. Matrix

| QoS | Confirmation mechanism | What completion can indicate | What it does NOT prove |
| ---: | --- | --- | --- |
| 0 | No PUBACK. | Paho finished its operation per client implementation. | That broker/subscriber received it. |
| 1 | PUBACK. | MQTT publisher→broker leg achieved QoS 1 ACK. | That subscriber processed it. |
| 2 | PUBREC, PUBREL, PUBCOMP. | QoS 2 handshake finished. | That DB committed only once. |

The broker continues delivering to subscribers per their own **subscription QoS and sessions**. A publisher receiving PUBACK is not an ACK from all subscribers matching the topic filter.

## 7. Spring Integration: synchronous MqttPahoMessageHandler

The outbound MQTT endpoint in Spring Integration is typically `MqttPahoMessageHandler`:

~~~java
var handler = new MqttPahoMessageHandler(
        "commands-publisher-1", mqttClientFactory);

handler.setDefaultTopic("diagnostics/unrouted");
handler.setDefaultQos(1);
handler.setDefaultRetained(false);
handler.setConverter(new DefaultPahoMessageConverter());
handler.setAsync(false);
handler.setCompletionTimeout(5000);
~~~

- `setAsync(false)`: publishes in synchronous waiting mode; the caller may block.
- `setCompletionTimeout(5000)`: wait limit in **milliseconds**.
- `setDefaultQos(1)` and `setDefaultRetained(false)`: defaults when messages provide no overrides per the converter/handler contract.
- `setDefaultTopic("diagnostics/unrouted")`: demo fallback only; production commands should fail fast if a concrete topic is missing.
- `setConverter(...)`: translates Spring messages into MQTT bytes/metadata; does not handle business ACKs.

When the handler sits behind a `DirectChannel`, synchronous publish failures can propagate back to `MessageChannel.send(...)`. Still, `DirectChannel` creates no transaction between MQTT and the DB, nor does it force the device to execute the command before returning.

### 7.1. Topic, QoS, and retained headers on a command

~~~java
Message<String> command = MessageBuilder
        .withPayload(
                "{\"commandId\":\"cmd-1001\",\"action\":\"TURN_ON\"}")
        .setHeader(MqttHeaders.TOPIC, "devices/device-17/commands")
        .setHeader(MqttHeaders.QOS, 1)
        .setHeader(MqttHeaders.RETAINED, false)
        .build();
~~~

`MqttHeaders.TOPIC`, `QOS`, and `RETAINED` govern the publication. A custom Spring header `commandId` **does not automatically become an MQTT v3 user property**; if the device needs that ID, place it in the JSON/binary payload.

### 7.2. Sync publish still has uncertain outcomes

~~~text
T0: Paho sends QoS 1 PUBLISH
T1: Broker receives PUBLISH
T2: Network drops PUBACK
T3: Handler waits past completionTimeout
T4: Caller sees exception
~~~

Never turn T4 into the conclusion "the broker definitely never received the command." Your business state model needs `PUBLISH_UNCERTAIN`, an outbox/retry keeping the same `commandId`, and an idempotent subscriber.

## 8. Async publish and Spring Integration MQTT events

The handler can publish asynchronously:

~~~java
handler.setAsync(true);
handler.setAsyncEvents(true);
~~~

With `setAsync(true)`, the caller can return before broker acknowledgment finishes; delayed outcomes require events, callbacks, or separate error handling. In supporting Spring Integration versions, `setAsyncEvents(true)` enables publish notifications such as:

- `MqttMessageSentEvent`: indicates the publish was sent per the adapter's step.
- `MqttMessageDeliveredEvent`: reflects the delivery completion callback when conditions are met.

**Verify against your version:** event emission details, correlation fields, QoS 0 interactions, and sync/async behavior are version-specific API details. Never promise every `send()` yields exactly one Delivered event, especially across disconnects or restarts. "Sent" **does not equal PUBACK**, and "Delivered" **does not equal device execution**.

### 8.1. Observing events with a Spring EventListener

~~~java
package demo.mqttdelivery;

import org.springframework.context.event.EventListener;
import org.springframework.integration.mqtt.event.MqttMessageDeliveredEvent;
import org.springframework.integration.mqtt.event.MqttMessageSentEvent;
import org.springframework.stereotype.Component;

@Component
class MqttPublishEventObserver {

    @EventListener
    public void sent(MqttMessageSentEvent event) {
        System.out.println("MQTT SENT: " + event);
    }

    @EventListener
    public void delivered(MqttMessageDeliveredEvent event) {
        System.out.println("MQTT DELIVERED: " + event);
    }
}
~~~

This is demo logging, not a production implementation. To correlate events to an outbox, use fields guaranteed by your API version; never log full payloads/secrets or rely solely on an MQTT packet ID as a durable key. If your version lacks the expected event support, use documented APIs and verify on your exact dependency.

### 8.2. Sync vs. async comparison

| Aspect | `setAsync(false)` | `setAsync(true)` |
| --- | --- | --- |
| Caller | May wait until completion/timeout. | Usually returns earlier. |
| Error path | Many errors surface on the call stack. | Errors may arrive later via events/callbacks. |
| Completion timeout | Critical for sync publish wait bounds. | Do not treat as a hard deadline for all async outcomes. |
| Throughput | May be constrained by publish latency. | Can be higher, requiring in-flight tracking. |
| Durability | Not automatic. | Not automatic. |
| Business ACK | Not automatic. | Not automatic. |

### 8.3. Never overwrite the callback of a Spring-managed Paho client

The raw Paho API allows `setCallback(...)`, yet Spring's MQTT inbound/outbound adapters rely on their own internal callbacks/lifecycles. Never hijack the callback in application code just to "grab tokens" if doing so breaks endpoint behavior; use framework-supported hooks/events or a tested integration layer.

## 9. Timeouts across different layers

| Parameter | Example | Unit | Purpose |
| --- | --- | --- | --- |
| `setConnectionTimeout(10)` | Paho options | Seconds | Bounds establishing the MQTT connection. |
| `setKeepAliveInterval(30)` | Paho options | Seconds | Maintains/detects connection liveness per protocol. |
| `setCompletionTimeout(5000)` | Spring outbound handler | Milliseconds | Waits for publish operation per handler mode. |
| `setRecoveryInterval(10000)` | Spring inbound adapter | Milliseconds | Throttles inbound endpoint recovery. |
| `businessAckTimeout=30s` | Application policy | Per contract | Waits for command ACK after subscriber executes. |

~~~mermaid
sequenceDiagram
    participant APP as Application
    participant B as Broker
    participant D as Device
    APP->>B: PUBLISH QoS 1 at 00.1s
    B--xAPP: PUBACK blocked
    Note over APP: Completion timeout at 05.0s
    B->>D: PUBLISH command
    D->>D: Executes in 7s
    D->>B: Business ACK at 12.0s
    B->>APP: Business ACK arrives after publish timeout
~~~

In this scenario, if the backend already emitted a brand-new command at 5 seconds, the device could receive two commands. Business state transitions must allow **an ACK arriving after a publish timeout**, and workers must cancel retries once a valid ACK is committed.

## 10. State model: do not collapse outcomes to true/false

~~~mermaid
stateDiagram-v2
    [*] --> CREATED
    CREATED --> READY: Persist outbox
    READY --> PUBLISHING: Worker claim
    PUBLISHING --> MQTT_PUBLISHED: Completion signal observed
    PUBLISHING --> PUBLISH_UNCERTAIN: Timeout / crash / disconnect
    PUBLISH_UNCERTAIN --> PUBLISHING: Retry same eventId
    MQTT_PUBLISHED --> BUSINESS_PENDING: Await ACK
    BUSINESS_PENDING --> BUSINESS_ACKNOWLEDGED: Valid ACK + DB commit
    PUBLISH_UNCERTAIN --> BUSINESS_ACKNOWLEDGED: Late valid ACK
    BUSINESS_PENDING --> REVIEW: Business timeout exceeded
    BUSINESS_ACKNOWLEDGED --> [*]
~~~

These states are an **application-defined model**, not built-in Paho/Spring enums. With callbacks on background threads, retry workers, and ACK consumers running concurrently, transitions require concurrency control and idempotency.

### 10.1. What belongs in an outbox record?

~~~json
{
  "commandId": "cmd-1001",
  "tenantId": "tenant-a",
  "deviceId": "device-17",
  "topic": "devices/device-17/commands",
  "payload": {
    "commandId": "cmd-1001",
    "deviceId": "device-17",
    "action": "TURN_ON"
  },
  "qos": 1,
  "retained": false,
  "publishState": "PUBLISH_UNCERTAIN",
  "attemptCount": 2,
  "businessState": "PENDING"
}
~~~

This schema is **only an example**; Spring Integration/Paho do not create it automatically. Production needs a persisted event ID, pre-resolved topic, byte payload/schema version, retry budget, error code, claim owner, and timestamps.

### 10.2. Distinct identifiers

| ID | Scope | Use as idempotency key? |
| --- | --- | --- |
| Spring Message `id` | One Spring message instance. | Not by default. |
| MQTT packet ID | Protocol, client session, and moment in time. | **No**—not globally unique. |
| MQTT Client ID | Logical client session/connection. | Not a command ID. |
| Business `commandId` | One command across retries/restarts. | **Yes**, scoped by namespace/tenant. |
| Trace ID | Observing operation chains. | Only if explicitly mandated by contract; does not replace business IDs. |

### 10.3. Device-side idempotency

A device receiving `commandId=cmd-1001` twice must recognize it as the **same business command**. If already applied, it can re-emit the recorded ACK instead of repeating side effects.

~~~text
onCommand(command):
    verify identity, authorization, schema, expiry
    if commandId already applied:
        republish recorded ACK
        return
    use idempotent/fenced side-effect policy
    persist result in a recoverable manner
    publish ACK(commandId, status)
~~~

Database unique constraints help, yet cannot automatically undo physical side effects outside a transaction. Commands like "set desired state = ON" are naturally easier to make idempotent than "increment power by 10 units"; design per domain semantics.

## 11. Choosing sync, async, and outbox by business requirements

| Scenario | Typical fit | Notes |
| --- | --- | --- |
| Low-criticality, high-rate telemetry | QoS 0 / async when SLA allows sample loss. | Never use token completion as broker receipt guarantee. |
| Reliable event needing retries | QoS 1 + outbox/persistent event store. | At-least-once; deduplicate on consumer. |
| Critical command | QoS 1/2 per SLA + stable `commandId` + business ACK. | MQTT delivery token does not replace device confirmation. |
| Low HTTP request latency | Persist outbox, return command ID, publish out-of-band. | Provide status endpoint/webhook/event. |
| Simple lab failure analysis | Sync handler + `completionTimeout`. | Still has uncertain outcomes. |
| Many concurrent publishes | Async handler + bounded in-flight/error tracking. | Prevent memory/queue growth; ensure shutdown/recovery. |

**Never hold a DB transaction open while waiting on a broker token.** A database commit is not atomic with an MQTT PUBLISH; use a transactional outbox to persist the business event and publish intent in one DB transaction, then let a worker publish over MQTT. Even if the worker publishes and crashes before updating the outbox, subscribers still need idempotency.

## 12. Spring Boot practice project structure

The example has two directions:

- **Outbound:** Spring channel `mqtt.commands.out` → `MqttPahoMessageHandler` → topic `devices/{deviceId}/commands`.
- **Inbound:** MQTT broker → `MqttPahoMessageDrivenChannelAdapter` subscribing to `devices/+/ack` → `mqtt.acks.in` → JSON parser/validator → `AckSink`.

~~~mermaid
flowchart LR
    API["Command-receiving service"]
    OUT["mqtt.commands.out"]
    H["Paho outbound handler<br/>async + events"]
    B[("MQTT broker")]
    D["Device"]
    I["Inbound ACK adapter"]
    ACKCH["mqtt.acks.in"]
    V["Validate ACK JSON / topic"]
    S["ACK sink / DB"]
    API --> OUT --> H --> B --> D
    D -->|"PUBLISH ACK"| B --> I --> ACKCH --> V --> S
~~~

Illustrative files:

~~~text
src/main/java/demo/mqttdelivery/
    MqttDeliveryApplication.java
    MqttDeliveryConfiguration.java
    Command.java
    CommandPublisher.java
    CommandAck.java
    AckSink.java
    AckFlowConfiguration.java
    MqttPublishEventObserver.java

src/main/resources/application.properties

src/test/java/demo/mqttdelivery/
    AckFlowTest.java
~~~

Uses Java 17+, Spring Boot/Spring Integration MQTT with compatible dependency management. Running the demo requires a **real MQTT broker**; Spring Boot does not start one.

### 12.1. Maven dependencies

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-integration</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.integration</groupId>
        <artifactId>spring-integration-mqtt</artifactId>
    </dependency>
    <dependency>
        <groupId>com.fasterxml.jackson.core</groupId>
        <artifactId>jackson-databind</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Let the Spring Boot BOM align versions; avoid arbitrarily mixing major versions or combining MQTT v3 and v5 APIs.

### 12.2. Application and properties

~~~java
package demo.mqttdelivery;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MqttDeliveryApplication {

    public static void main(String[] args) {
        SpringApplication.run(MqttDeliveryApplication.class, args);
    }
}
~~~

`application.properties`:

~~~properties
app.mqtt.broker-url=${MQTT_BROKER_URL:tcp://localhost:1883}
app.mqtt.publisher-id=${MQTT_PUBLISHER_ID:commands-publisher-local-1}
app.mqtt.ack-subscriber-id=${MQTT_ACK_SUBSCRIBER_ID:acks-in-local-1}
~~~

Use separate Client IDs for inbound and outbound, never shared across active instances. In production, use TLS, secrets-managed credentials, and broker ACLs restricting command publishing and ACK subscribing.

### 12.3. Command and business ACK DTOs

~~~java
package demo.mqttdelivery;

record Command(String commandId, String deviceId, String action) {

    Command {
        if (commandId == null || commandId.isBlank()) {
            throw new IllegalArgumentException("Missing commandId");
        }
        if (deviceId == null
                || !deviceId.matches("[A-Za-z0-9_-]{1,40}")) {
            throw new IllegalArgumentException("Invalid deviceId");
        }
        if (!"TURN_ON".equals(action)
                && !"TURN_OFF".equals(action)) {
            throw new IllegalArgumentException(
                    "Unsupported action: " + action);
        }
    }
}
~~~

~~~java
package demo.mqttdelivery;

record CommandAck(String commandId, String deviceId, String result) {

    CommandAck {
        if (commandId == null || commandId.isBlank()) {
            throw new IllegalArgumentException("Missing ACK commandId");
        }
        if (deviceId == null
                || !deviceId.matches("[A-Za-z0-9_-]{1,40}")) {
            throw new IllegalArgumentException("Invalid ACK deviceId");
        }
        if (!"APPLIED".equals(result)
                && !"REJECTED".equals(result)) {
            throw new IllegalArgumentException(
                    "Invalid ACK result");
        }
    }
}
~~~

These are two package-private records in the same package. `APPLIED` differs from `REJECTED`: both are **received business messages**, yet with opposite command outcomes. If adding `ACCEPTED` or `IN_PROGRESS`, extend the schema/state machine rather than treating every ACK as completion.

### 12.4. Configuring Paho client factory and both MQTT endpoints

~~~java
package demo.mqttdelivery;

import org.eclipse.paho.client.mqttv3.MqttConnectOptions;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.mqtt.core.DefaultMqttPahoClientFactory;
import org.springframework.integration.mqtt.core.MqttPahoClientFactory;
import org.springframework.integration.mqtt.inbound.MqttPahoMessageDrivenChannelAdapter;
import org.springframework.integration.mqtt.outbound.MqttPahoMessageHandler;
import org.springframework.integration.mqtt.support.DefaultPahoMessageConverter;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHandler;

@Configuration
@EnableIntegration
class MqttDeliveryConfiguration {

    @Bean
    MqttPahoClientFactory mqttClientFactory(
            @Value("${app.mqtt.broker-url}") String brokerUrl) {

        var options = new MqttConnectOptions();
        options.setServerURIs(new String[] {brokerUrl});
        options.setConnectionTimeout(10);
        options.setKeepAliveInterval(30);
        options.setCleanSession(true);

        var factory = new DefaultMqttPahoClientFactory();
        factory.setConnectionOptions(options);
        return factory;
    }

    @Bean(name = "mqtt.commands.out")
    MessageChannel commandsOutput() {
        return new DirectChannel();
    }

    @Bean(name = "mqtt.acks.in")
    MessageChannel acksInput() {
        return new DirectChannel();
    }

    @Bean(name = "mqttPublisher")
    MqttPahoMessageHandler mqttPublisher(
            MqttPahoClientFactory factory,
            @Value("${app.mqtt.publisher-id}") String clientId) {

        var publisher = new MqttPahoMessageHandler(
                clientId, factory);
        publisher.setDefaultTopic("diagnostics/unrouted");
        publisher.setDefaultQos(1);
        publisher.setDefaultRetained(false);
        publisher.setConverter(new DefaultPahoMessageConverter());

        // Asynchronous publish; emits events on supporting versions.
        publisher.setAsync(true);
        publisher.setAsyncEvents(true);
        publisher.setCompletionTimeout(5000);
        return publisher;
    }

    @Bean
    IntegrationFlow commandsOutboundFlow(
            @Qualifier("mqttPublisher") MessageHandler publisher) {
        return IntegrationFlow.from("mqtt.commands.out")
                .handle(publisher)
                .get();
    }

    @Bean
    MqttPahoMessageDrivenChannelAdapter ackInboundAdapter(
            MqttPahoClientFactory factory,
            @Qualifier("mqtt.acks.in") MessageChannel ackInput,
            @Value("${app.mqtt.ack-subscriber-id}") String clientId) {

        var adapter = new MqttPahoMessageDrivenChannelAdapter(
                clientId, factory, "devices/+/ack");
        adapter.setQos(1);
        adapter.setRecoveryInterval(10000);
        adapter.setConverter(new DefaultPahoMessageConverter());
        adapter.setOutputChannel(ackInput);
        return adapter;
    }
}
~~~

Design characteristics:

1. `mqttClientFactory` creates Paho MQTT v3 connection options. Both endpoints can share factory options while keeping **distinct Client IDs**.
2. `commandsOutboundFlow` uses a `DirectChannel` to pass Spring `Message<?>` instances to the outbound handler.
3. The publisher enables `setAsync(true)` and `setAsyncEvents(true)`. Callers can return before publish completion; events are reliable only within the scope guaranteed by your version.
4. `ackInboundAdapter` subscribes to `devices/+/ack` at QoS 1 and emits messages to `mqtt.acks.in`. It is a **message-driven** MQTT adapter with no `@Poller` reading the broker.
5. `setRecoveryInterval(10000)` is the endpoint recovery interval in milliseconds; `setCompletionTimeout(5000)` applies to publish completion. Neither is a business ACK timeout.
6. Topic `diagnostics/unrouted` is just a demo fallback. For production commands, reject before the handler when a concrete topic is missing instead of falling back to an unintended target.

For production brokers, require TLS/authentication/ACLs. Creating configuration beans does not prove publisher or inbound subscriber connected cleanly; manage startup, readiness, reconnects, and session state.

### 12.5. Service serializing commands to JSON and publishing

~~~java
package demo.mqttdelivery;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.mqtt.support.MqttHeaders;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
class CommandPublisher {

    private final MessageChannel channel;
    private final ObjectMapper mapper;

    CommandPublisher(
            @Qualifier("mqtt.commands.out") MessageChannel channel,
            ObjectMapper mapper) {
        this.channel = channel;
        this.mapper = mapper;
    }

    boolean requestPublish(Command command)
            throws JsonProcessingException {
        if (command == null) {
            throw new IllegalArgumentException("Missing command");
        }

        String json = mapper.writeValueAsString(command);
        String topic = "devices/" + command.deviceId() + "/commands";

        return channel.send(MessageBuilder.withPayload(json)
                .setHeader(MqttHeaders.TOPIC, topic)
                .setHeader(MqttHeaders.QOS, 1)
                .setHeader(MqttHeaders.RETAINED, false)
                .build());
    }
}
~~~

Caller usage:

~~~java
commandPublisher.requestPublish(
        new Command("cmd-1001", "device-17", "TURN_ON"));
~~~

The name `requestPublish` deliberately communicates **a publish request**, not `executeDeviceCommandAndConfirm`. With an async handler, the returned boolean only reflects Spring channel handoff, not broker receipt or device execution.

A `commandId` must be generated and durably stored by the business layer before publishing. If HTTP clients are allowed to supply IDs, prevent overwriting IDs owned by another tenant or device.

### 12.6. Illustrative ACK sink

~~~java
package demo.mqttdelivery;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

class AckSink {

    private final List<CommandAck> accepted =
            new CopyOnWriteArrayList<>();

    void accept(CommandAck ack) {
        accepted.add(ack);
    }

    List<CommandAck> snapshot() {
        return List.copyOf(accepted);
    }

    void clear() {
        accepted.clear();
    }
}
~~~

This sink is strictly for learning/testing and **does not persist across restarts**. Production needs a database/inbox verifying that `commandId` exists and belongs to the right device/tenant, alongside idempotent transitions, expiry, and auditing. ACK messages can arrive out of order or duplicated.

### 12.7. ACK flow: independent inbound business confirmation

~~~java
package demo.mqttdelivery;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.mqtt.support.MqttHeaders;

@Configuration
class AckFlowConfiguration {

    @Bean
    ObjectMapper mqttObjectMapper() {
        return new ObjectMapper();
    }

    @Bean
    AckSink ackSink() {
        return new AckSink();
    }

    @Bean
    IntegrationFlow ackFlow(
            ObjectMapper mqttObjectMapper,
            AckSink sink) {

        return IntegrationFlow.from("mqtt.acks.in")
                .handle(String.class, (json, headers) -> {
                    Object header =
                            headers.get(MqttHeaders.RECEIVED_TOPIC);

                    if (!(header instanceof String topic)
                            || !topic.matches(
                                    "devices/[A-Za-z0-9_-]{1,40}/ack")) {
                        throw new IllegalArgumentException(
                                "Invalid ACK topic");
                    }

                    final CommandAck ack;
                    try {
                        ack = mqttObjectMapper.readValue(
                                json, CommandAck.class);
                    } catch (JsonProcessingException ex) {
                        throw new IllegalArgumentException(
                                "Invalid ACK JSON", ex);
                    }

                    String expected = "devices/"
                            + ack.deviceId() + "/ack";
                    if (!expected.equals(topic)) {
                        throw new IllegalArgumentException(
                                "ACK deviceId differs from topic");
                    }

                    sink.accept(ack);
                    return null;
                })
                .get();
    }
}
~~~

**These are two independent publications:** commands travel from backend to device; ACKs travel from device back through the broker to the backend. Outbound `MqttPahoMessageHandler` cannot synthesize a Java reply DTO merely because the MQTT broker sent `PUBACK`.

`MqttHeaders.RECEIVED_TOPIC` holds the **actual inbound topic**, unlike outbound `MqttHeaders.TOPIC`. Custom Spring headers like `commandId` do not traverse MQTT v3 automatically; the device must read the ID from JSON and include it in the ACK JSON.

In production, valid ACK JSON **does not prove** the sender is the trusted device. Broker ACLs must bind publishers to topics, and the backend must verify command ownership and update the DB idempotently. Spoofed ACKs can falsely mark commands succeeded.

### 12.8. Observability for the async publisher

`MqttPublishEventObserver` from section 8 can be picked up via Spring component scanning to observe events. It writes technical logs—**never** mark `APPLIED` merely upon seeing `MqttMessageDeliveredEvent`.

In production, use correlation fields actually guaranteed by your API version and record technical MQTT publish states only on valid signals. For business state, rely solely on verified ACKs and DB commits.

### 12.9. When external APIs cannot wait for an ACK

An HTTP API can persist the command/outbox and return:

~~~json
{
  "commandId": "cmd-1001",
  "state": "ACCEPTED",
  "statusUrl": "/commands/cmd-1001"
}
~~~

HTTP `202 Accepted` indicates the backend accepted the work, **not** that the device executed it. `statusUrl` is an illustrative path; Spring Integration MQTT does not generate that REST endpoint. When HTTP timeouts are shorter than MQTT/business processing, returning a command ID and polling/pushing status is far cleaner than holding requests open until a device replies.

## 13. Testing the ACK flow without an MQTT broker

This test proves **Spring channels, JSON parsing, and business topic contracts**. It cannot prove Paho tokens, PUBACKs, or broker delivery. Do not load `MqttDeliveryConfiguration` in this test because it creates network-connecting endpoints; load only `AckFlowConfiguration` and test channels.

~~~java
package demo.mqttdelivery;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.mqtt.support.MqttHeaders;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = {
        AckFlowConfiguration.class,
        AckFlowTestChannels.class
})
class AckFlowTest {

    @Autowired
    @Qualifier("mqtt.acks.in")
    MessageChannel input;

    @Autowired
    AckSink sink;

    @BeforeEach
    void reset() {
        sink.clear();
    }

    @Test
    void acceptsValidAck() {
        String json = "{\"commandId\":\"cmd-test-1\","
                + "\"deviceId\":\"device-17\","
                + "\"result\":\"APPLIED\"}";

        boolean sent = input.send(
                MessageBuilder.withPayload(json)
                        .setHeader(MqttHeaders.RECEIVED_TOPIC,
                                "devices/device-17/ack")
                        .build());

        assertTrue(sent);
        assertEquals(
                List.of(new CommandAck(
                        "cmd-test-1", "device-17", "APPLIED")),
                sink.snapshot());
    }

    @Test
    void rejectsDeviceMismatch() {
        String json = "{\"commandId\":\"cmd-test-2\","
                + "\"deviceId\":\"device-21\","
                + "\"result\":\"APPLIED\"}";

        assertThrows(RuntimeException.class, () ->
                input.send(MessageBuilder.withPayload(json)
                        .setHeader(MqttHeaders.RECEIVED_TOPIC,
                                "devices/device-17/ack")
                        .build()));

        assertTrue(sink.snapshot().isEmpty());
    }

    @Test
    void rejectsMalformedJson() {
        assertThrows(RuntimeException.class, () ->
                input.send(MessageBuilder.withPayload(
                        "{\"commandId\":")
                        .setHeader(MqttHeaders.RECEIVED_TOPIC,
                                "devices/device-17/ack")
                        .build()));

        assertTrue(sink.snapshot().isEmpty());
    }
}

@Configuration
@EnableIntegration
class AckFlowTestChannels {

    @Bean(name = "mqtt.acks.in")
    MessageChannel ackInput() {
        return new DirectChannel();
    }
}
~~~

With `DirectChannel`, the test invokes the handler synchronously so `sink.snapshot()` can be asserted right after `send(...)`. The tests catch generic `RuntimeException` to avoid coupling to framework-version-specific wrapper exceptions; in real applications, inspect cause chains and `errorChannel` handling.

### 13.1. Testing the publisher header contract with a fake handler

A fake `MessageHandler` can record topic, payload, QoS, and retained values:

~~~java
package demo.mqttdelivery;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.springframework.integration.mqtt.support.MqttHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHandler;

record OutboundObservation(
        String topic, String payload, int qos, boolean retained) {}

class RecordingPublisher implements MessageHandler {

    private final List<OutboundObservation> messages =
            new CopyOnWriteArrayList<>();

    @Override
    public void handleMessage(Message<?> message) {
        messages.add(new OutboundObservation(
                (String) message.getHeaders().get(MqttHeaders.TOPIC),
                (String) message.getPayload(),
                (Integer) message.getHeaders().get(MqttHeaders.QOS),
                (Boolean) message.getHeaders().get(MqttHeaders.RETAINED)));
    }

    List<OutboundObservation> snapshot() {
        return List.copyOf(messages);
    }
}
~~~

In a test context, define bean `mqtt.commands.out`, an `IntegrationFlow.from("mqtt.commands.out").handle(recordingPublisher).get()`, `ObjectMapper`, and `CommandPublisher`. Calling `requestPublish(new Command("cmd-test-3","device-17","TURN_ON"))` records:

~~~text
topic:    devices/device-17/commands
payload:  {"commandId":"cmd-test-3","deviceId":"device-17","action":"TURN_ON"}
qos:      1
retained: false
~~~

**Limitation:** the fake handler creates no Paho delivery token, sends no MQTT packets, and does not prove the broker received anything. Sleeping `Thread.sleep(5001)` inside a fake handler only measures test latency, not Paho completion timeouts.

### 13.2. Business state tests you should write

- Reject commands missing IDs, with device IDs containing `/`/`+`, or invalid actions.
- Reject ACKs whose device ID differs from topic, wrong tenant, or unknown `commandId`.
- Idempotency: two identical ACKs do not trigger two business side effects.
- `REJECTED` ACK never transitions to `APPLIED`.
- Late ACK arriving while outbox is `PUBLISH_UNCERTAIN` still reconciles cleanly.
- Application restart recovers pending/uncertain outbox records rather than relying on in-memory tokens.
- Broker ACL forbids device A from publishing ACKs on behalf of device B.

## 14. Testing delivery tokens with a real MQTT broker

Requires a test broker under your control. The commands below assume Mosquitto CLI and a test broker on `localhost:1883`. Never shut down production brokers or weaken production TLS just for testing.

### 14.1. Subscriber observing commands

Terminal A:

~~~bash
mosquitto_sub -h localhost -p 1883 \
  -i demo-command-subscriber-1 \
  -t 'devices/+/commands' -q 1 -v
~~~

Run `RawPahoTokenDemo` or invoke `CommandPublisher.requestPublish(...)` in Spring Boot. The subscriber prints JSON on the matching topic if the broker/client are active and authorized.

**This only verifies delivery to a test subscriber.** A CLI printing payload does not prove an actuator turned on or a downstream service committed to a DB.

### 14.2. Business ACKs must be tested separately

Terminal B:

~~~bash
mosquitto_sub -h localhost -p 1883 \
  -i demo-ack-subscriber-1 \
  -t 'devices/+/ack' -q 1 -v
~~~

Simulate an ACK in the lab:

~~~bash
mosquitto_pub -h localhost -p 1883 \
  -t 'devices/device-17/ack' -q 1 \
  -m '{"commandId":"cmd-1001","deviceId":"device-17","result":"APPLIED"}'
~~~

The Spring inbound flow receives and parses the ACK. Still, this is a **simulated ACK sent from a test terminal**, not proof a real device executed the command. In production, only authenticated, properly authorized devices may publish ACKs.

### 14.3. Comparing QoS 0, 1, 2

Change the QoS parameter in `RawPahoTokenDemo` across 0, 1, and 2 in test runs, observing duration and callbacks:

- QoS 0 has no PUBACK, so token completion is not a broker ACK.
- QoS 1 has PUBACK; a lost ACK can cause retransmission/uncertain outcomes.
- QoS 2 completes protocol handshake after PUBCOMP; still does not prove DB exactly-once.

Verify behavior on your project's exact Paho/Spring/broker versions rather than measuring only an ideal localhost path.

### 14.4. Creating a meaningful publish timeout

Use a network proxy or fault injection to block/delay PUBACK **after the broker has received PUBLISH**:

~~~mermaid
sequenceDiagram
    participant P as Paho client
    participant B as Broker
    participant S as Subscriber
    P->>B: PUBLISH QoS1 cmd-1001
    B->>S: PUBLISH cmd-1001
    B--xP: PUBACK blocked
    Note over P: waitForCompletion times out
    Note over S: May already have processed cmd-1001
~~~

Simply shutting down the whole broker often triggers `connection lost` rather than a publish token timeout. Separate **initial connect failures**, **reconnect failures**, **completion timeouts**, and **business ACK timeouts** when recording test results.

### 14.5. Test matrix

| Scenario | What to verify |
| --- | --- |
| QoS 0 token | Do not interpret completion as PUBACK. |
| QoS 1 token | Completes on PUBACK. |
| QoS 2 token | Completes per QoS 2 handshake. |
| Sync handler | Caller may wait until completion/timeout. |
| Async handler | Outcome may arrive after return; requires event/callback tracking. |
| Lost ACK | Broker/subscriber received while publisher timed out. |
| App crash after PUBACK | Outbox replay can duplicate; subscriber must deduplicate. |
| Subscriber offline | Publisher can still get broker ACK; business ACK has not arrived. |
| Duplicate Client ID | Disconnect/reconnect loop may occur. |
| Late ACK | State reconciliation does not overwrite incorrectly. |
| Retained command | Observe old-command replay hazard in broker lab. |
| Broker offline before startup | Startup recovery differs from losing connection after startup. |
| Broker ACL rejection | Classify as security/config error; never retry infinitely. |

## 15. Publish errors, timeouts, and multi-layer retries

~~~mermaid
flowchart TD
    OUTBOX["Durable outbox READY"]
    PUBLISH["MQTT publish attempt"]
    DECIDE{"Observed outcome?"}
    SENT["MQTT_PUBLISHED"]
    UNKNOWN["PUBLISH_UNCERTAIN"]
    REJECT["FAILED / quarantine"]
    RETRY["Backoff with same eventId"]
    ACK["Valid device ACK"]
    DONE["BUSINESS_ACKNOWLEDGED"]
    OUTBOX --> PUBLISH --> DECIDE
    DECIDE -->|"Completion observed"| SENT
    DECIDE -->|"Timeout/connection lost"| UNKNOWN
    DECIDE -->|"ACL/schema/topic invalid"| REJECT
    UNKNOWN --> RETRY --> PUBLISH
    SENT --> ACK --> DONE
    UNKNOWN --> ACK
~~~

At least two retry layers can stack on top of each other:

1. MQTT/Paho retransmits unacknowledged packets per QoS.
2. The application sees a timeout and issues a **new** PUBLISH from its outbox.

Hence devices can receive the same business command multiple times. **Use `commandId`/`eventId` to deduplicate**, never relying solely on packet IDs or the MQTT DUP flag.

| Error group | Policy |
| --- | --- |
| Transient network/disconnect | Bounded retry, backoff/jitter, preserve business ID. |
| Publish token timeout | Mark uncertain, reconcile ACK, retry idempotently if needed. |
| Invalid topic | Reject/quarantine; never send infinitely. |
| Broker ACL/credential error | Alert and fix config; avoid retry storms. |
| Invalid JSON/schema | Non-retryable data error. |
| Device ACKs `REJECTED` | Record business failure; do not treat as an MQTT publish failure. |
| DB fails updating ACK | Inbox/idempotent transaction/separate retry. |

### 15.1. Spring error channel vs. Paho callbacks

Spring Integration supports `ErrorMessage`, `errorChannel`, and advice on properly configured endpoints/flows. Never assume **every Paho async callback exception** automatically routes onto an arbitrary Spring error channel.

A sync handler on `DirectChannel` can propagate some errors to the caller; async handlers, executors, and pollers may surface errors via different events/callbacks/error flows. Test your exact wiring and version instead of merely wrapping `send()` in a `try/catch (Exception)`.

### 15.2. Never infinitely retry corrupted payloads

If command JSON violates schema or targets another tenant's topic, reconnecting the broker will never fix the data. Reject/audit/quarantine those errors instead of looping them back onto source topics. For transient network errors, bound retries by count/time with load shedding.

## 16. Transactional outbox: more durable than delivery tokens

~~~mermaid
flowchart LR
    API["Business API"]
    DB[("DB + transactional outbox")]
    WORKER["Outbox worker claim/retry"]
    FLOW["Spring MQTT outbound flow"]
    BROKER[("MQTT broker")]
    DEVICE["Device"]
    IN["MQTT ACK inbound"]
    ACKDB[("Business state DB")]
    API -->|"Single transaction"| DB
    DB --> WORKER --> FLOW --> BROKER --> DEVICE
    DEVICE -->|"PUBLISH ACK(commandId)"| BROKER
    BROKER --> IN --> ACKDB
    ACKDB -. "Reconcile retry" .-> WORKER
~~~

A durable outbox record should store:

| Field | Purpose |
| --- | --- |
| `event_id`/`command_id` | Durable business key across restarts/retries. |
| `tenant_id`/`device_id` | Command identity and authorization scope. |
| `mqtt_topic` | Pre-validated target topic. |
| `payload_json`/`payload_bytes` | Payload to publish, with command ID embedded. |
| `qos`/`retained` | MQTT delivery policy. |
| `publish_state` | READY/PUBLISHING/PUBLISHED/UNCERTAIN/FAILED. |
| `business_state` | PENDING/APPLIED/REJECTED/UNKNOWN. |
| `attempt_count`/`next_retry_at` | Backoff and retry budget. |
| `claim_owner`/`claim_until` | Prevents two workers from claiming concurrently under normal conditions. |
| `last_error`/`created_at` | Auditing and monitoring. |

### 16.1. Outbox flow

1. Business API authenticates, validates, and creates `commandId`.
2. Writes the business command + outbox record in the **same DB transaction**.
3. Worker claims records and sends Spring messages with the pre-resolved topic/QoS/retained settings.
4. When MQTT completion is observed, marks `MQTT_PUBLISHED`; on timeout, marks `PUBLISH_UNCERTAIN`.
5. Device processes idempotently and publishes an ACK carrying `commandId`.
6. ACK consumer validates ownership and updates the DB idempotently.
7. After a restart, workers scan unfinished outbox records, reconcile, and retry per policy.

Never keep a DB transaction open while waiting on an MQTT token expecting the DB and broker to commit atomically. Even though an outbox atomically persists the business event and publish intent in the DB, MQTT publishing can still repeat if a crash occurs after PUBACK before the outbox row updates.

### 16.2. Correlation when using async events

If an async handler emits events, the application must map **technical events** back to **outbox records**. Packet IDs can be reused, delayed events can arrive after reconnects, and in-memory maps vanish on crashes. Never store `packetId` alone as a long-lived key.

If your API/version does not provide strong enough correlation, options include publishing synchronously from the worker and handling uncertain outcomes explicitly, or building a dedicated integration layer with a verified callback/recovery contract. Never claim `DeliveredEvent` always carries `commandId` without verifying it.

## 17. ACK security and business state

An ACK payload stating `result=APPLIED` does not prove it came from the legitimate device. The backend needs:

- MQTT authentication, TLS, and per-device/tenant topic ACLs.
- Verification that `commandId` exists, belongs to that device, and is in an eligible state.
- Cross-checking the actual received topic against `deviceId` in JSON.
- Guarding against duplicate/out-of-order ACKs using unique keys and sequence/epoch checks if needed.
- Business state transitions separating `REJECTED`, `APPLIED`, and `PENDING`.
- Validation, auditing, and keeping sensitive data out of logs.
- ACK expiry, reconciliation/retries, and clear handling when a device never confirms.

### 17.1. ACK ACCEPTED vs. APPLIED

If a device sends `ACCEPTED` upon receipt before running the actuator, the backend must not record `APPLIED`. A multi-step contract might be:

~~~text
CREATED → MQTT_PUBLISHED → DEVICE_ACCEPTED → DEVICE_APPLIED
~~~

The `CommandAck` example only accepts `APPLIED`/`REJECTED` for simplicity. Real systems can extend the schema/state machine and must handle out-of-order ACKs.

### 17.2. LWT and ONLINE presence do not replace business ACKs

Keep Alive and Last Will only reflect MQTT connection state at the protocol layer; a device can stay online while its business worker hangs. When an ACK is missing, never blindly issue a risky new command without reconciliation or idempotency.

## 18. How do sessions, retained messages, and reconnects interact?

| Mechanism | What it does | What it does NOT do |
| --- | --- | --- |
| MQTT QoS | Governs protocol-layer handshakes/delivery. | DB exactly-once. |
| `cleanSession=false` | Can keep subscriptions/offline QoS 1/2 messages per broker policy. | Persist Spring outboxes. |
| Retained | Stores the latest snapshot of a topic. | Store full command event history. |
| Automatic reconnect | Attempts to restore the connection. | Perform durable business retries. |
| Delivery token | Tracks a runtime publish operation. | Serve as a durable event record. |
| Last Will | Broker emits on abnormal client disconnect. | Act as a business command ACK. |

A publisher can receive PUBACK from the broker even while the subscriber is offline. Whether the subscriber gets the message upon reconnecting depends on QoS, session, subscription, Client ID, and broker persistence. The publisher's token **never** tells you when the device processed it.

Duplicate Client IDs across two active clients can cause the broker to disconnect them alternately. For persistent sessions, Client IDs must be stable *and* owned by only one active logical subscriber.

### 18.1. Why should commands not be retained?

A retained one-time command can be re-delivered to newly subscribing clients and trigger old actions. The demo sets `MqttHeaders.RETAINED=false`. If a system genuinely uses desired-state retained messages, enforce schema versioning/expiry and explicit idempotent policies.

### 18.2. Process restarts do not restore old Java tokens

When an app crashes, in-memory token objects and callback state disappear, even though the broker may already have received the PUBLISH. Rely on a durable outbox/inbox, stable business IDs, and ACK reconciliation before retrying—never on old tokens.

## 19. Backpressure, threads, and timeout budgets

| Channel/handler setup | Advantage | Limitation |
| --- | --- | --- |
| `DirectChannel` + sync publish | Easy-to-follow synchronous errors. | Blocks producer/HTTP/poller when broker is slow. |
| `DirectChannel` + async publish | Reduces caller wait time. | Must track delayed outcomes/in-flight work; never treat return as ACK. |
| `ExecutorChannel` | Decouples producer thread. | Must bound pool/queue and handle async errors. |
| `QueueChannel` | Buffers messages internally. | Needs a poller; RAM queue loses data on restart. |
| Durable outbox | Recovers pending events across crashes. | Can send duplicates; needs idempotency. |

`setCompletionTimeout(5000)` **is not a circuit breaker**. It does not enforce in-flight quotas, retry budgets, backoff, DLQs, rate limits, or business acknowledgments. When the broker remains unreachable for long stretches while upstream keeps generating tens of thousands of messages, enforce bounded resources, durable buffering, and admission control.

### 19.1. When HTTP times out before MQTT/business processing

HTTP may time out in 2 seconds while publish waits 5 seconds and the device ACKs after 20 seconds. Do not hold the request open indefinitely pretending it is synchronous. Common pattern:

1. Persist command/outbox and return `202 Accepted` with `commandId`.
2. Worker publishes via MQTT and records publish outcome.
3. Client polls status or receives a webhook/event.
4. ACK consumer verifies outcome and commits to DB.

`202 Accepted` does not mean the device executed the command; it only means the server accepted the request per the API contract.

## 20. Observability: measure all three layers

| Suggested metric/field | Purpose |
| --- | --- |
| `mqtt_publish_attempts_total` | Total publish attempts including retries. |
| `mqtt_publish_completed_total{qos}` | Observed publish completions. |
| `mqtt_publish_timeout_total` | Operations exceeding timeout. |
| `mqtt_publish_uncertain_total` | Events where broker receipt is unknown. |
| `mqtt_publish_inflight` | Pressure from incomplete publishes. |
| `mqtt_client_connected{role}` | Connection state of MQTT clients. |
| `outbox_ready_count` | Work backlog. |
| `outbox_oldest_age_seconds` | Age of oldest unprocessed event. |
| `business_ack_received_total{result}` | Business ACKs grouped by result. |
| `business_ack_latency_seconds` | Time from command to ACK. |
| `business_duplicate_ignored_total` | Duplicates filtered by deduplication. |
| `mqtt_error_total{category}` | Classifies network/ACL/schema/downstream errors. |

These metric names are suggestions, not defaults automatically emitted with these exact names by Spring Integration/Paho. Avoid putting individual `deviceId`/`commandId` values into metric labels, which explodes cardinality; use structured logs/traces for per-message correlation.

Normal trace:

~~~text
cmd-1001 CREATED
cmd-1001 OUTBOX_COMMITTED
cmd-1001 PUBLISH_ATTEMPTED
cmd-1001 MQTT_PUBLISHED
cmd-1001 BUSINESS_ACK_RECEIVED
cmd-1001 BUSINESS_ACKNOWLEDGED
~~~

Uncertain trace:

~~~text
cmd-1002 PUBLISH_ATTEMPTED
cmd-1002 PUBLISH_UNCERTAIN (PUBACK lost)
cmd-1002 BUSINESS_ACK_RECEIVED (arrived late)
cmd-1002 BUSINESS_ACKNOWLEDGED
~~~

Logs must separate **observed facts** from guesses. A completion timeout does not prove the device never processed a command, and receiving an ACK does not guarantee the DB commit already succeeded.

## 21. Common pitfalls

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| `channel.send()` returns true, yet subscriber sees nothing. | Spring handoff differs from MQTT delivery. | Check publish result, broker, ACLs, and subscriptions. |
| Token completes, yet device has not run. | Token only tracks the MQTT operation. | Implement a business ACK. |
| QoS 0 token completes, yet broker sees no packet. | QoS 0 has no broker PUBACK. | Choose QoS per SLA; do not promise guaranteed delivery. |
| QoS 1 times out, yet device received command. | PUBACK lost or delayed. | Treat as uncertain outcome; retry idempotently. |
| QoS 2 still triggers duplicate side effects. | Two separate publications or business retries. | Unique command ID / DB idempotency. |
| No `DeliveredEvent` seen in async mode. | Different config/version/callback semantics. | Check `asyncEvents`/API and test against broker. |
| Async send succeeds, yet publish fails later. | No sync exception after return. | Event/error monitoring + outbox. |
| Packet ID mapped to wrong command. | ID reuse, missing client instance/epoch. | Use business IDs and scoped correlation. |
| Restart loses tokens. | Tokens live only in runtime RAM. | Durable outbox, replay/reconciliation. |
| HTTP times out even though device executed. | API deadline shorter than ACK latency. | Return command ID/status instead of arbitrarily issuing a new command. |
| Retained command re-executes on subscribe. | `retained=true` on a one-time command. | Set `retained=false`; clean up improper retained messages. |
| Duplicate ACK updates DB twice. | ACK handler lacks idempotency. | Unique key / atomic state transition. |
| Client reconnects nonstop. | Duplicate Client ID or ACL/network issue. | Check broker logs and Client IDs. |
| Device returns `REJECTED`, yet backend marks `APPLIED`. | Confusing ACK receipt with command result. | Validate result / state machine. |
| Error channel misses async errors. | Different error path/callback than expected. | Test exact framework event/error configuration. |
| Queue fills while broker is offline. | Missing backpressure. | Rate limits, bounded queues, durable outbox. |

## 22. Practice exercise

**Context:** a system controls devices over HTTP and MQTT. Commands must be persisted before sending, the broker may go offline for 30 seconds or drop PUBACKs, and devices must never execute duplicate side effects even when commands are replayed.

Requirements:

1. Define `Command(commandId, deviceId, action)` and a durable outbox record.
2. HTTP API validates permissions, transactionally persists command + outbox, and returns the command ID.
3. Create outbound Spring channel `mqtt.commands.out` and `MqttPahoMessageHandler` with QoS 1, `retained=false`.
4. Test sync `setAsync(false)`, measuring caller latency/exceptions with a healthy broker and a slow broker.
5. Test async `setAsync(true)` + events on a supporting version; explain how return and completion differ.
6. Write a raw Paho demo obtaining `IMqttDeliveryToken`, calling `waitForCompletion(5000)`, and logging packet ID for technical diagnostics.
7. Use a test broker subscribing to `devices/+/commands` and `devices/+/ack`.
8. Simulated device enforces idempotency by `commandId` and replies with `APPLIED` or `REJECTED` ACKs.
9. Create an inbound ACK adapter and flow validating JSON, topic, device identity, and command ownership.
10. Write brokerless JUnit tests for channels, serialization, topic/QoS/retained, and ACK parsing.
11. Test QoS 0/1/2 and explain their handshakes and token completion meanings.
12. Inject a fault that drops PUBACK after the broker receives PUBLISH.
13. Record `PUBLISH_UNCERTAIN`, retry with the same `commandId`, and prove no duplicate side effect occurs.
14. Crash the worker after PUBACK but before DB commit; restart and reconcile the outbox.
15. Test business ACKs arriving after publish timeout, duplicated ACKs, and ACKs from a different device.
16. Manage Client IDs, broker ACLs/TLS, queue capacity, retry budgets, and metrics.
17. Use HTTP status lookup so callers track commands instead of waiting indefinitely for ACKs.
18. Prove `APPLIED` status is only committed from a verified business ACK.

**Completion criteria:** distinguish Spring handoff, Paho publish completion, and verified business ACK; handle uncertain timeouts; preserve messages across restarts; avoid duplicate side effects; combine real broker tests with mocked tests whose boundaries are clearly stated.

## 23. Self-check questions

1. Which operation is `IMqttDeliveryToken` bound to?
2. Is `waitForCompletion(5000)` in seconds or milliseconds?
3. What does `isComplete() == true` at QoS 1 prove?
4. How does `deliveryComplete(...)` differ from calling token wait methods?
5. Can an MQTT packet ID serve as a business primary key?
6. Does QoS 0 have a PUBACK?
7. Which ACK packet does QoS 1 use, and why can duplicates still occur?
8. What steps compose QoS 2, and does it guarantee DB exactly-once?
9. When the broker receives PUBLISH but PUBACK is lost, what does the caller see?
10. Why does a completion timeout not prove the broker never received the message?
11. Does `MessageChannel.send()` returning `true` equal an MQTT ACK?
12. How does `setAsync(true)` change error paths and timing?
13. Does `setAsyncEvents(true)` guarantee one `DeliveredEvent` for every message?
14. Does `MqttMessageDeliveredEvent` confirm the device executed the command?
15. How do connection timeout and completion timeout differ?
16. Why must business IDs appear inside MQTT v3 JSON payloads?
17. Should an ACK flow read the topic via `MqttHeaders.RECEIVED_TOPIC` or `MqttHeaders.TOPIC`?
18. How do you reject an ACK from a device that does not own the command?
19. When a business ACK arrives after a token timeout, what should the worker do?
20. Why is an outbox still required when publishing at QoS 2?
21. Can an app that crashes right after PUBACK re-emit the event?
22. What risk does a retained one-time command carry?
23. What does a fake-handler test prove, and what does it leave unproven?
24. At which layer must you inject faults to test token timeouts?
25. Why should HTTP APIs consider `202` + status lookup?
26. Which metrics separate MQTT publish completion from business ACKs?
27. What problem do duplicate Client IDs across two instances cause?
28. How can the two retry layers (MQTT and outbox) combine to create duplicates?
29. Is a device returning `REJECTED` an MQTT publish error?
30. Does a persistent session let a publisher's token know when an offline device processed a message?

**Hint:** tokens track a single MQTT operation; protocol ACKs never replace business ACKs. Only a valid business ACK and DB commit prove command completion per contract.

## 24. Conclusion

**Delivery tokens and publish confirmation** must be viewed across three independent boundaries:

- **Paho `IMqttDeliveryToken`** tracks an MQTT PUBLISH; `waitForCompletion(...)` and `deliveryComplete(...)` observe operation completion.
- **MQTT QoS 0/1/2** defines distinct handshakes: QoS 0 has no PUBACK, QoS 1 uses PUBACK, and QoS 2 uses PUBREC/PUBREL/PUBCOMP.
- **`MqttPahoMessageHandler`** offers sync/async modes, completion timeouts, and observable events depending on config/version; none of them create a transaction between broker and database.
- **Publish completion is not a business ACK.** Only a dedicated ACK carrying a command ID, authenticated/validated and committed on the backend, confirms device execution per contract.
- **Timeouts can leave unknown outcomes.** The broker may have received the message even when the caller sees no ACK; use a durable outbox, stable command IDs, bounded retries, and idempotent devices.
- **Sessions, retained messages, reconnects, and error channels** support delivery yet do not replace business processing state.

In the **SPRING_INTEGRATION_ADAPTERS** module, separating **Spring handoff → MQTT publish completion → business ACK → database commit** keeps message tracking truthful, handles unstable brokers/networks safely, and prevents reporting completion before business execution is verified.
