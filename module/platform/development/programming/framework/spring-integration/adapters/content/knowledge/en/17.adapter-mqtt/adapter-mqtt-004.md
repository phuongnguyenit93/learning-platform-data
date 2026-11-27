# Topic expressions and topic headers

## 1. The problem: every message must be published to the right MQTT topic

In an integration application, not every message sent to an MQTT broker belongs to the same topic. Device control commands may go to `devices/device-17/commands`, current state to `devices/device-17/state`, and warehouse events to `inventory/warehouse-02/changed`. Hardcoding a single shared topic makes it difficult for consumers to distinguish data; taking a raw topic string straight from an external request risks publishing to the wrong device or tenant.

**Topic expressions and topic headers** are two ways Spring Integration decides **which topic to publish to for each message**. A topic can be computed from the payload/headers via an expression or determined upstream and placed into `MqttHeaders.TOPIC`. The MQTT outbound handler reads this metadata to construct the MQTT PUBLISH sent to the broker.

This lesson belongs to the **Adapter MQTT** chapter of the **SPRING_INTEGRATION_ADAPTERS** module. The module connects external systems via inbound/outbound adapters, gateways, pollers, and `MessageChannel`, practicing with files, SFTP, HTTP, JMS, AMQP, Kafka, and databases while clarifying message contracts, errors, and connection lifecycles. With MQTT, topic selection is part of the **contract between producer, broker, and subscriber**, not just internal channel naming.

After completing this lesson, learners will be able to:

- Distinguish **broker URL**, **MQTT topic**, **topic filter**, **Spring MessageChannel**, and **message header**.
- Understand how to use `setDefaultTopic(...)`, `MqttHeaders.TOPIC`, and SpEL expressions to determine a publication's topic.
- Distinguish outbound `MqttHeaders.TOPIC` from inbound `MqttHeaders.RECEIVED_TOPIC`.
- Build a Java DSL flow that validates payloads, safely constructs topics, and sets headers before `MqttPahoMessageHandler`.
- Apply `MqttHeaders.QOS` and `MqttHeaders.RETAINED` headers appropriately by event type.
- Explain fixed topics, dynamic topics, topic-based routers, and fallback policies.
- Test topic and header resolution **without an MQTT broker**, then verify real publishing against a broker.
- Design topic/tenant security, deduplication, error handling, and retries.

**Principle:** a Spring `MessageChannel` determines **which internal endpoint** receives a message; an MQTT topic determines **which subscribers on the broker** can receive a publication. These two mechanisms serve two different routing layers.

## 2. Where the topic fits in an MQTT outbound flow

~~~mermaid
flowchart LR
    SRC["Business service / file / SFTP / HTTP / JMS / Kafka"]
    C["device.events<br/>Spring MessageChannel"]
    V["Validate event and identity"]
    T["Determine topic<br/>expression or header"]
    H["MqttPahoMessageHandler"]
    B[("MQTT broker")]
    S1["Subscriber device-17"]
    S2["Subscriber device-21"]
    SRC --> C --> V --> T --> H
    H -->|"PUBLISH devices/device-17/state"| B
    B -->|"matching subscription"| S1
    B -->|"matching subscription"| S2
~~~

An MQTT outbound adapter receives a Spring `Message<?>` containing a **payload** and **headers**, for example:

~~~text
Message<String>
  payload:
    {"eventId":"evt-2001","deviceId":"device-17","temperature":26.5}
  headers:
    mqtt_topic: "devices/device-17/state"
    mqtt_qos: 1
    mqtt_retained: true
    correlationId: "trace-evt-2001"
~~~

These headers express publishing intent. Spring Integration provides the constants `MqttHeaders.TOPIC`, `MqttHeaders.QOS`, and `MqttHeaders.RETAINED`; in Java code, use these constants instead of typing `"mqtt_topic"`, `"mqtt_qos"`, and `"mqtt_retained"` by hand.

When the handler converts the message into an MQTT PUBLISH, MQTT v3 transmits the topic, QoS, retained flag, and payload per the protocol. **Custom Spring headers such as `correlationId` do not automatically become MQTT user properties**; if subscribers must read that ID, include it in the JSON/payload schema or define an explicit mapping protocol.

## 3. Five concepts that are easy to confuse

| Concept | Example | Where is it used? |
| --- | --- | --- |
| **Broker URL** | `tcp://localhost:1883` or `ssl://mqtt.example.net:8883`. | `MqttConnectOptions` and client factory to connect to the broker. |
| **MQTT publish topic** | `devices/device-17/commands`. | A single publication sent to the broker. |
| **MQTT subscription filter** | `devices/+/commands`. | MQTT inbound/subscriber registering to receive matching topics. |
| **Spring MessageChannel** | `mqtt.publish.requests`. | Internal connection path between endpoints inside the Spring context. |
| **Spring message header** | `MqttHeaders.TOPIC` → `devices/device-17/commands`. | Metadata for the outbound handler to construct the MQTT publication. |

For instance, an application can have just **one** Spring input channel `mqtt.publish.requests` yet publish to thousands of different MQTT topics. It does not need a separate Spring channel per device. Conversely, multiple Spring channels can target the same MQTT topic if the business topology calls for it.

### 3.1. A topic is a distribution address, not a URL

~~~text
Broker URL:     ssl://mqtt.example.net:8883
Spring channel: mqtt.publish.requests
Publish topic:  devices/device-17/commands
Subscription:   devices/+/commands
~~~

Do not append a topic to the end of a TCP broker URI like an HTTP path. In raw MQTT over TCP, the topic is an MQTT PUBLISH/SUBSCRIBE protocol field, not a server URL path.

### 3.2. PUBLISH topics must not use wildcard characters

In MQTT, `+` and `#` are wildcards reserved for **subscription filters**. A PUBLISH must use a **concrete topic name**; never publish to `devices/+/state` or `devices/#`.

Topic levels are separated by `/`, and topic names are case-sensitive. `devices/device-17/state` and `Devices/device-17/state` can be two distinct topics. Systems should standardize naming rules and run contract tests between producers and subscribers.

Topics starting with `$` may be reserved by the broker for administrative or special conventions such as `$SYS`. Never allow arbitrary client-supplied values to select topics in an administrative namespace.

## 4. Three strategies for choosing an MQTT outbound topic

### 4.1. Fixed default topic

When every message in a flow carries the same kind of data, you can configure a fixed topic on the outbound handler:

~~~java
var handler = new MqttPahoMessageHandler(
        "events-publisher-1", mqttClientFactory);
handler.setDefaultTopic("events/orders/created");
handler.setDefaultQos(1);
handler.setDefaultRetained(false);
~~~

This works well when every message reaching the handler truly belongs to `events/orders/created`. When no topic override is present and the converter/handler is configured to use the default topic, that value becomes the destination.

**Drawback:** if the application forgets to set a topic on a message meant for a specific device, a default topic can cause the publication to be sent anyway—to the **wrong business destination**. For commands or multi-tenant data, fail explicitly when a topic is missing rather than relying on an overly broad fallback.

### 4.2. Topic via MqttHeaders.TOPIC

An upstream step determines the proper topic and attaches it to the Spring message:

~~~java
Message<String> message = MessageBuilder
        .withPayload("{\"eventId\":\"evt-2001\",\"state\":\"ON\"}")
        .setHeader(MqttHeaders.TOPIC, "devices/device-17/state")
        .setHeader(MqttHeaders.QOS, 1)
        .setHeader(MqttHeaders.RETAINED, true)
        .build();
~~~

This is a clean choice when **multiple producers or flows** share a single outbound MQTT handler. Producers take responsibility for constructing/validating the topic; the adapter handles serialization and MQTT publishing.

`MqttHeaders.TOPIC` expresses the **target topic to publish to**—not an MQTT subscription, not a Spring bean name, and not automatically the same topic an inbound adapter previously received.

### 4.3. Topic expression (SpEL)

When a topic follows a rule derived from message data, you can express that computation using Spring Expression Language:

~~~text
'devices/' + payload.deviceId() + '/state'
~~~

For example, this expression reads `deviceId` from a `DeviceEvent` payload and produces `devices/device-17/state`. Expressions can also read header metadata:

~~~text
'tenants/' + headers['tenantId'] + '/events/' + payload.eventType()
~~~

The expression here is a **Spring evaluation rule**, not an expression evaluated by the MQTT broker. Validate every dynamic value before computing the topic. If your project's adapter/DSL/XML version supports configuring a topic expression directly, you can use that feature; another easier-to-test and less API-coupled approach is computing the expression in an upstream step and placing the result into `MqttHeaders.TOPIC`.

**Note on precedence:** between a topic expression configured directly on the handler, a topic header, and a default topic, final behavior depends on the adapter/converter and version. Avoid configuring multiple competing topic sources at once without an explicit policy; verify behavior with tests on your exact Spring Integration version.

## 5. How do setting a topic header and evaluating a topic expression differ?

| Criterion | Topic header | Topic expression |
| --- | --- | --- |
| Where the decision happens | Upstream producer, transformer, or header enricher. | Expression evaluated at the configured point. |
| Output value | `MqttHeaders.TOPIC` contains an already-decided topic. | Computed result is used for the publication or written to a header. |
| When useful | Multiple sources already know their topics and share one handler. | Topic pattern derived from payload/headers is relatively uniform. |
| Testing | Assert the header at the boundary before the outbound handler. | Test the expression against varied payloads/headers and invalid inputs. |
| Security control | Verify the header value was not chosen arbitrarily by a client. | Validate every input variable; never accept expressions from users. |
| Changeability | Upstream can change targets without changing the handler. | Changing the rule or expression config can affect many messages. |

The two approaches combine cleanly: **expression → topic string → `MqttHeaders.TOPIC` → outbound handler**. That is the pattern used in this lesson's main example.

### 5.1. A topic header is not an authorization mechanism

A header like `mqtt_topic = "tenants/vip/commands"` is just application-carried data. If an inbound HTTP endpoint lets callers supply this header arbitrarily and forwards it straight to MQTT, a caller can intentionally route messages to another tenant's topic. Therefore, **topic headers must be generated or validated at a trusted boundary**, backed by ACL/topic policies in both the application and the broker.

### 5.2. A topic expression is not a Spring channel router

For example, `.route(...)` in Java DSL selects a **Spring MessageChannel** such as `orders.standard` or `orders.express`. An expression producing `"devices/device-17/state"` computes an **MQTT topic**, not a new subscriber inside the Spring context. Distinguish where data is routed for internal processing from where the MQTT broker distributes publications.

## 6. Complete example: setting a dynamic MQTT topic from DeviceEvent

We will build an application that receives `DeviceEvent` instances on Spring channel `device.events`. Based on the event's `kind`, the flow picks the topic:

- `STATE` → `devices/{deviceId}/state`, retained `true` so new subscribers see the state snapshot.
- `COMMAND` → `devices/{deviceId}/commands`, retained `false` to avoid replaying one-time commands.

Each publication uses QoS 1 and carries `eventId` in the JSON payload so subscribers can deduplicate. The demo also puts `eventId` in a Spring header for observability, yet **that ID must remain inside the JSON** if subscribers need to read it over MQTT v3.

### 6.1. Maven dependencies

With Spring Boot managing dependency versions:

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

The example uses Java 17+ and Spring Integration with Eclipse Paho MQTT v3. Typical API classes: `MqttPahoMessageHandler`, `MqttPahoClientFactory`, `DefaultPahoMessageConverter`, and `MqttHeaders`. If your project uses the MQTT v5 adapter, consult the corresponding API/client instead of mixing classes from the two lines.

### 6.2. Code structure

~~~text
src/main/java/demo/mqtttopics/
    MqttTopicApplication.java
    MqttTopicFlowConfiguration.java
    MqttTransportConfiguration.java
    DeviceEvent.java
    TopicMessageMapper.java
    DeviceEventPublisher.java

src/main/resources/
    application.properties
~~~

All snippets belong to package `demo.mqtttopics`. Public classes must reside in Java files matching their class names; package-private classes/records may also be placed in separate files of the same name for readability.

### 6.3. Spring Boot application

~~~java
package demo.mqtttopics;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MqttTopicApplication {

    public static void main(String[] args) {
        SpringApplication.run(MqttTopicApplication.class, args);
    }
}
~~~

### 6.4. Data contract and topic generation policy

~~~java
package demo.mqtttopics;

record DeviceEvent(
        String eventId,
        String deviceId,
        String kind,
        String json) {
}
~~~

A dedicated component validates inputs and builds the Spring message:

~~~java
package demo.mqtttopics;

import org.springframework.integration.mqtt.support.MqttHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

final class TopicMessageMapper {

    private TopicMessageMapper() {
    }

    static Message<String> toMqttMessage(DeviceEvent event) {
        if (event.eventId() == null || event.eventId().isBlank()) {
            throw new IllegalArgumentException("Missing eventId");
        }
        if (event.deviceId() == null
                || !event.deviceId().matches("[A-Za-z0-9_-]{1,40}")) {
            throw new IllegalArgumentException("Invalid deviceId");
        }
        if (event.json() == null || event.json().isBlank()) {
            throw new IllegalArgumentException("Missing JSON payload");
        }

        String suffix;
        boolean retained;

        switch (event.kind()) {
            case "STATE" -> {
                suffix = "state";
                retained = true;
            }
            case "COMMAND" -> {
                suffix = "commands";
                retained = false;
            }
            default -> throw new IllegalArgumentException(
                    "Unsupported event kind: " + event.kind());
        }

        String topic = "devices/" + event.deviceId() + "/" + suffix;

        return MessageBuilder.withPayload(event.json())
                .setHeader(MqttHeaders.TOPIC, topic)
                .setHeader(MqttHeaders.QOS, 1)
                .setHeader(MqttHeaders.RETAINED, retained)
                .setHeader("eventId", event.eventId())
                .build();
    }
}
~~~

In this example:

1. `eventId` is required to provide a business identifier.
2. `deviceId` is restricted by a character and length allowlist, preventing injection of `/`, `+`, or `#` to alter topic structure.
3. Only two `kind` values are supported, preventing arbitrary routing.
4. Topic, QoS, and retained are placed in message headers **before the handler is invoked**.
5. The `json` payload is used as-is. In a real system, serialize from a DTO or validate JSON and ensure the `eventId` inside the payload matches the header.

**Note:** setting `retained=true` for `STATE` is only appropriate when it represents the latest state snapshot allowed to be retained by the broker; do not apply it blindly to every state event. If state events form a historical audit stream where every transition matters, retained does not replace an event log.

### 6.5. Configuring the internal inbound channel and outbound flow

~~~java
package demo.mqtttopics;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHandler;

@Configuration
@EnableIntegration
class MqttTopicFlowConfiguration {

    @Bean(name = "device.events")
    MessageChannel deviceEvents() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow deviceEventOutboundFlow(
            @Qualifier("mqttPublisher") MessageHandler mqttPublisher) {

        return IntegrationFlow.from("device.events")
                .transform(DeviceEvent.class,
                        TopicMessageMapper::toMqttMessage)
                .handle(mqttPublisher)
                .get();
    }
}
~~~

`.transform(...)` accepts a `DeviceEvent` payload, converts it into a Spring `Message<String>` containing topic headers, and `.handle(...)` passes the message to the MQTT outbound handler. The handler is a one-way terminal endpoint and does not return a business reply.

`DirectChannel` keeps the example simple, though when the broker is slow, the sending thread can block under synchronous publishing. Do not add a second `@ServiceActivator(inputChannel="device.events")` unless you intend to introduce multiple consumers, because `DirectChannel` does not broadcast by default.

### 6.6. Configuring the client factory and outbound handler

~~~java
package demo.mqtttopics;

import org.eclipse.paho.client.mqttv3.MqttConnectOptions;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.mqtt.core.DefaultMqttPahoClientFactory;
import org.springframework.integration.mqtt.core.MqttPahoClientFactory;
import org.springframework.integration.mqtt.outbound.MqttPahoMessageHandler;
import org.springframework.integration.mqtt.support.DefaultPahoMessageConverter;

@Configuration
class MqttTransportConfiguration {

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

    @Bean(name = "mqttPublisher")
    MqttPahoMessageHandler mqttPublisher(
            MqttPahoClientFactory factory,
            @Value("${app.mqtt.publisher-client-id}") String clientId) {

        var handler = new MqttPahoMessageHandler(clientId, factory);
        handler.setDefaultTopic("diagnostics/unrouted");
        handler.setDefaultQos(1);
        handler.setDefaultRetained(false);
        handler.setConverter(new DefaultPahoMessageConverter());
        handler.setAsync(false);
        handler.setCompletionTimeout(5000);
        return handler;
    }
}
~~~

File `src/main/resources/application.properties`:

~~~properties
app.mqtt.broker-url=tcp://localhost:1883
app.mqtt.publisher-client-id=topic-publisher-local-1
~~~

Here the handler sets `defaultTopic` to illustrate fallback; however, **every valid message from `TopicMessageMapper` must carry `MqttHeaders.TOPIC`**. In production, treat a missing topic as a validation error when publications target specific devices; do not let a default topic hide a routing bug.

The demo does not configure username, password, or TLS. When connecting to brokers outside a local network, load credentials from secrets, enable TLS with certificate verification, and verify broker ACLs per topic. Creating a factory and handler does not start an MQTT broker automatically.

### 6.7. A service invoking the flow

~~~java
package demo.mqtttopics;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
class DeviceEventPublisher {

    private final MessageChannel input;

    DeviceEventPublisher(
            @Qualifier("device.events") MessageChannel input) {
        this.input = input;
    }

    boolean publish(DeviceEvent event) {
        return input.send(MessageBuilder.withPayload(event).build());
    }
}
~~~

An authenticated caller can invoke:

~~~java
publisher.publish(new DeviceEvent(
        "evt-2001",
        "device-17",
        "STATE",
        "{\"eventId\":\"evt-2001\",\"deviceId\":\"device-17\","
                + "\"state\":\"ON\"}"));
~~~

The message flows from `device.events` → mapper → outbound handler → MQTT broker on topic `devices/device-17/state`, QoS 1, `retained=true`.

**Do not call this confirmation that the device updated:** `MessageChannel.send()` is a Spring message handoff; depending on the channel and sync/async configuration, broker publish outcomes may need separate observation. If the application needs to know the device executed a command, implement an inbound ACK flow correlated by `eventId`/`commandId`.

## 7. Topic expressions with Spring Expression Language (SpEL)

The main example uses plain Java to keep validation and mapping explicit. When topic rules are straightforward, SpEL expresses the same rule concisely.

Suppose the payload is `DeviceEvent`; build a Spring message:

~~~java
Message<DeviceEvent> source = MessageBuilder.withPayload(
        new DeviceEvent(
                "evt-2002",
                "device-21",
                "STATE",
                "{\"eventId\":\"evt-2002\",\"state\":\"OFF\"}"))
        .build();
~~~

Use `SpelExpressionParser` to evaluate the topic:

~~~java
Expression expression = new SpelExpressionParser()
        .parseExpression(
                "'devices/' + payload.deviceId() + '/state'");

String topic = expression.getValue(source, String.class);
// topic = "devices/device-21/state"
~~~

Required imports:

~~~java
import org.springframework.expression.Expression;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
~~~

Here the SpEL root object is `Message<DeviceEvent>`, so `payload` points to the `DeviceEvent` record and `payload.deviceId()` calls its accessor. The resulting value should only be placed into `MqttHeaders.TOPIC` **after** `deviceId` has been validated.

### 7.1. Header-based expressions

A flow can place verified routing information into a `safeDeviceId` header and compute the topic with:

~~~text
'devices/' + headers['safeDeviceId'] + '/commands'
~~~

This works well when the payload is `byte[]` or a JSON `String` and the device ID was parsed/validated in an earlier step. Never take `safeDeviceId` straight from an HTTP request header and trust it merely because the name contains `safe`.

When configuring an expression directly on an adapter or header enricher, verify that the expression is actually evaluated **against the expected message** and returns a `String` containing a valid MQTT topic. Check the XSD/API of your Spring Integration version when translating Java examples to XML or Java DSL endpoint specs.

### 7.2. Never accept SpEL from user input

SpEL is a framework expression language capable of accessing properties, invoking methods, and more. **Never** allow publishers/HTTP callers to supply raw expressions for Spring to evaluate, as that introduces security vulnerabilities and forfeits routing control.

Expressions should be defined by developers or trusted configuration; external inputs may only supply values that have passed validation against allowed characters and event types.

### 7.3. Compute in a transformer or on the outbound adapter?

Both options can be valid:

- **Upstream transformer/header enricher:** produces `MqttHeaders.TOPIC` before the handler. Advantages: you can test topic policies without a broker and log routing decisions before sending.
- **Expression directly on the adapter:** concise when a single handler has one fixed rule, though you must understand precedence with `MqttHeaders.TOPIC`/`defaultTopic` and converter behavior per version.

When multiple sources feed one outbound handler, **normalizing upstream and setting the topic header** is usually easier to audit for authorization and contracts. Do not configure competing topic sources simultaneously without precedence tests.

## 8. Inbound RECEIVED_TOPIC is not the same as outbound TOPIC

In Spring Integration MQTT, an inbound adapter attaches `MqttHeaders.RECEIVED_TOPIC` indicating **the actual topic on which the broker delivered the message**. An outbound handler reads `MqttHeaders.TOPIC` to determine **the publish destination**.

~~~text
Inbound received from:
  mqtt_receivedTopic = "sensors/device-17/temperature"

Outbound needs to publish to:
  mqtt_topic = "telemetry/device-17/normalized"
~~~

The two values often differ because the system performs transformation, security checks, routing, or protocol translation.

### 8.1. Example: bridging data from MQTT inbound to MQTT outbound

Do not blindly copy all headers from an inbound message and assume the outbound target is the source topic. When forwarding normalized telemetry to another topic:

1. Read `MqttHeaders.RECEIVED_TOPIC` to identify the source.
2. Parse/validate the device ID, topic shape, and payload.
3. Determine the new topic according to an allowed mapping, e.g., `telemetry/{deviceId}/normalized`.
4. Set `MqttHeaders.TOPIC` on the outbound message, along with appropriate QoS/retained settings.
5. Route to the outbound handler over a separate channel without creating an infinite publish–subscribe loop.

A publisher can accidentally subscribe to the same topic it publishes to and loop messages forever if two flows form a cycle. Inspect topology and track/prevent loops via `eventId`, origin, and topic rules.

### 8.2. Spring MQTT headers vs. MQTT user properties

In MQTT v3, there is no general user-properties mechanism like MQTT v5. Spring headers used to drive converters **do not automatically appear in the MQTT payload**. If subscribers need a trace ID, tenant, or command ID, include them in the JSON, binary frame, or agreed application-level payload format.

## 9. When to use a topic header vs. when to use a router

An application may need both layers of routing:

~~~mermaid
flowchart LR
    E["Business event"]
    R{"Spring router by eventType"}
    C1["events.telemetry<br/>Spring channel"]
    C2["events.commands<br/>Spring channel"]
    T1["Build topic + headers<br/>telemetry/{id}/state"]
    T2["Build topic + headers<br/>devices/{id}/commands"]
    O1["MQTT outbound handler"]
    O2["MQTT outbound handler"]
    B[("MQTT broker")]
    E --> R
    R -->|"STATE"| C1 --> T1 --> O1 --> B
    R -->|"COMMAND"| C2 --> T2 --> O2 --> B
~~~

If two event types share the same client factory, retry policy, and QoS policy, a **single** outbound handler with dynamic topic headers may suffice. If security/credentials, broker URLs, retained behavior, retries, or client lifecycles differ substantially, consider **two handlers or two factories** to keep boundaries clean.

| Design | Benefits | Risks to manage |
| --- | --- | --- |
| One outbound handler, dynamic topic headers | Centralized config, fewer endpoints. | Every message must safely resolve a topic; shared broker policy. |
| Spring router → multiple outbound handlers | Isolates policies by message type/target. | More endpoints, Client IDs, monitoring, and retry paths. |
| Topic expression in one handler | Concise rule when topic pattern is stable. | Easy to overlook validation or precedence with headers/default topic. |
| Config mapping between business key → topic | Strong allowlist control and target flexibility. | Requires version/config management and tests on mapping changes. |

**Do not use MQTT topic wildcards to simulate a Spring router.** Wildcard filters are for subscribers; publishers must specify concrete topic names.

## 10. Per-tenant/device topics: contract and security design

Generating dynamic topics from multi-tenant data is one of the easiest places to introduce authorization bugs.

Example structure:

~~~text
tenants/{tenantId}/devices/{deviceId}/commands
tenants/{tenantId}/devices/{deviceId}/state
~~~

A secure design requires:

1. **Authentication:** callers must be authenticated.
2. **Authorization:** caller is permitted to control `deviceId` within `tenantId`.
3. **Validation:** IDs contain only allowed characters—no `/`, wildcards, control characters, or excessive lengths.
4. **Canonical mapping:** topics are constructed in code from verified IDs; never accept raw topics from callers.
5. **Broker ACLs:** the MQTT publisher credential is only allowed to publish to permitted topics.
6. **Audit:** log actor, event/command ID, validated topic, and publish/ACK outcome.
7. **Idempotency:** subscribers distinguish new commands from redeliveries.
8. **Retention policy:** never set `retained=true` on one-time commands.

Do not casually use `String.replace("/", "_")` to "sanitize" topic injection, because two distinct IDs can collide onto the same topic. It is better to **reject invalid IDs** per contract or encode them using a bijective scheme agreed upon by all parties.

### 10.1. Topic case sensitivity and naming conventions

For example, `device-17`, `Device-17`, and `DEVICE-17` may be distinct topics. If the system standardizes on lowercase, normalize at ID issuance or before permission lookup—never merely lowercase the topic after authorizing against the original casing.

Every routing decision should be reproducible from **business identity + message type + rule version** to support investigating replays or contract changes.

## 11. QoS and retained can also travel via headers

In Java, topic is not the only header that governs a publication:

~~~java
Message<String> stateMessage = MessageBuilder
        .withPayload("{\"eventId\":\"evt-2003\",\"state\":\"ON\"}")
        .setHeader(MqttHeaders.TOPIC, "devices/device-17/state")
        .setHeader(MqttHeaders.QOS, 1)
        .setHeader(MqttHeaders.RETAINED, true)
        .build();

Message<String> commandMessage = MessageBuilder
        .withPayload("{\"commandId\":\"cmd-3001\",\"action\":\"TURN_OFF\"}")
        .setHeader(MqttHeaders.TOPIC, "devices/device-17/commands")
        .setHeader(MqttHeaders.QOS, 1)
        .setHeader(MqttHeaders.RETAINED, false)
        .build();
~~~

| Data type | Topic | Illustrative QoS | Illustrative retained |
| --- | --- | --- | --- |
| Current device snapshot | `devices/{id}/state` | 1 | `true` when broker should retain latest state. |
| One-time command | `devices/{id}/commands` | 1 | `false` to avoid replaying old commands to new subscribers. |
| Continuous telemetry | `sensors/{id}/temperature` | 0 or 1 per SLA. | Usually `false` if each message is an event sample. |
| Critical business event | `events/orders/created` | 1/2 per protocol. | Usually `false`; use a durable event store beyond retained. |

QoS 1 can deliver duplicates to subscribers. QoS 2 reduces duplicates at the MQTT protocol layer, **without guaranteeing exactly-once business side effects**. Retained only stores the latest snapshot per topic (depending on broker), not a full event store.

### 11.1. Which headers should not cross the broker?

Do not serialize internal Spring headers such as `replyChannel`, `errorChannel`, security objects, internal tokens, or Java connection objects. In MQTT v3, publishers usually place business fields into the payload schema; topic/QoS/retained are the primary MQTT publication parameters in these examples.

If you need request–reply over MQTT, design **two topics or logical request/ACK channels**, with command IDs and timeout/correlation logic. Outbound `MqttPahoMessageHandler` is a one-way sending handler and does not become a gateway returning DTOs when the broker receives a publication.

## 12. Errors when building or passing topics

~~~mermaid
flowchart TD
    IN["Upstream message"]
    VAL{"Validate type, device ID, permissions?"}
    MAP["Expression / mapper builds topic"]
    HDR["Set MqttHeaders.TOPIC"]
    PUB["MqttPahoMessageHandler"]
    BROKER[("MQTT broker")]
    ERR["Error flow / quarantine / retry"]
    IN --> VAL
    VAL -->|"Valid"| MAP --> HDR --> PUB --> BROKER
    VAL -->|"Invalid"| ERR
    MAP -. "expression / mapping error" .-> ERR
    PUB -. "invalid topic / broker error" .-> ERR
~~~

| Error type | Example | Handling |
| --- | --- | --- |
| Missing ID/routing key | Payload lacks `deviceId`. | Reject/quarantine before building topic. |
| Publish topic has wildcards | `devices/+/commands`. | Do not publish; fix topic-generation policy. |
| Wrong tenant topic | Caller attempts to publish to an unauthorized device. | Enforce authorization and broker ACL; audit rejected event. |
| Wrong topic header type | Header is not `String` or holds invalid characters. | Contract validation before the handler. |
| Missing header and default topic | Message falls back to an unintended topic. | Fail fast for critical events; test omission cases. |
| Expression evaluation failure | Missing/wrong-type property, SpEL parse/eval error. | Test rules, validate schema, do not retry bad data indefinitely. |
| Broker rejects publish | ACL, connection, timeout, broker unavailable. | Bounded retry/backoff, outbox, and reconciliation. |
| Target received but ACK missing | Broker/device responded late or dropped. | Uncertain outcome; rely on idempotency and separate business ACK. |

**Distinction:** topic mapping errors are typically **data/configuration errors** and should not be retried infinitely as-is. Broker/network errors may be transient, yet retrying a publication after a timeout risks duplication because the broker may have received the message before the response was lost.

### 12.1. Do not let a default topic hide errors

For commands/transactions, a setting like `handler.setDefaultTopic("devices/default/commands")` can be hazardous: if the mapper omits the header, a command could be delivered to an unintended device or system.

Use contract tests to verify **every command carries an explicit topic** before reaching the handler. If you still want a fallback, pick a diagnostics/quarantine-only topic with restricted permissions and no command-executing subscribers, or simply reject messages missing a topic.

### 12.2. Synchronous and asynchronous errors

With `DirectChannel` and `setAsync(false)`, some outbound errors propagate back to the caller calling `send(...)`. With `ExecutorChannel`, `QueueChannel`, or async handlers, publish errors may surface on another thread/callback and require dedicated monitoring/error handling.

Never assume a successful `MessageChannel.send()` means the MQTT broker ACKed, or that a broker ACK means the subscriber completed the operation. Track states explicitly as **ACCEPTED → PUBLISH_ATTEMPTED → MQTT_PUBLISHED → BUSINESS_ACKNOWLEDGED** when reliable tracking is required.

## 13. Backpressure and high topic cardinality

A single publisher can publish to thousands of topics through one MQTT handler, though throughput and reliability depend on the broker, network, QoS, sessions, and subscribers.

- **Topic cardinality:** number of distinct device IDs/topics; guard against junk input spawning millions of unbounded topics.
- **Payload size:** avoid oversized JSON or embedding secrets in payloads.
- **Publish throughput:** messages/second, completion latency, error and retry rates.
- **Retained state:** `retained=true` across many topics creates broker-stored state consuming resources.
- **Queue backlog:** if using an internal queue, enforce capacity/poller bounds and restart durability where needed.
- **Partitioning:** if multiple instances publish from a shared outbox, use claim/partitioning to curb duplicates.

An in-memory `QueueChannel` stores messages only in RAM by default and does not turn Spring Integration into a durable broker. For critical events, use an outbox or persistent message store with event IDs for safe replay.

### 13.1. Transactional outbox when topics are resolved dynamically

When a DB transaction records an event that must also be published to MQTT, store the **event ID, payload, schema version, and route/topic decision** in the outbox within the same transaction. A worker then reads the outbox and builds a Spring message with a controlled `MqttHeaders.TOPIC`.

If you compute the topic solely from runtime configuration without storing the routing decision or rule version, a retried event after a config change could go to a different topic. Depending on business rules, store the **final resolved topic** or rule version for consistent replay. If MQTT publishing succeeds before the worker crashes prior to updating the outbox, subscribers must still deduplicate by event ID.

## 14. Testing topic mapping without an MQTT broker

To test mapping logic without connecting to a broker, separate the **routing flow** from **MQTT transport beans**. In the section 6 example, `MqttTopicFlowConfiguration` only requires a `MessageHandler` bean named `mqttPublisher`. Tests can provide a fake handler with that name and inspect messages dispatched to it.

Add the test dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Create `MqttTopicFlowTest.java` in package `demo.mqtttopics`:

~~~java
package demo.mqtttopics;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.mqtt.support.MqttHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = {
        MqttTopicFlowConfiguration.class,
        RecordingPublisherConfiguration.class
})
class MqttTopicFlowTest {

    @Autowired
    @Qualifier("device.events")
    MessageChannel input;

    @Autowired
    RecordingPublisher publisher;

    @BeforeEach
    void reset() {
        publisher.clear();
    }

    @Test
    void stateEventUsesDeviceTopicAndRetainedTrue() {
        DeviceEvent event = new DeviceEvent(
                "evt-test-01", "device-17", "STATE",
                "{\"eventId\":\"evt-test-01\",\"state\":\"ON\"}");

        boolean accepted = input.send(
                MessageBuilder.withPayload(event).build());

        assertTrue(accepted);
        assertEquals(
                List.of(new Published(
                        "devices/device-17/state",
                        event.json(), 1, true)),
                publisher.snapshot());
    }

    @Test
    void commandEventUsesCommandTopicAndRetainedFalse() {
        DeviceEvent event = new DeviceEvent(
                "evt-test-02", "device-21", "COMMAND",
                "{\"eventId\":\"evt-test-02\",\"action\":\"TURN_OFF\"}");

        input.send(MessageBuilder.withPayload(event).build());

        assertEquals(
                List.of(new Published(
                        "devices/device-21/commands",
                        event.json(), 1, false)),
                publisher.snapshot());
    }

    @Test
    void invalidDeviceIdIsRejectedBeforePublish() {
        DeviceEvent event = new DeviceEvent(
                "evt-test-03", "other/tenant", "COMMAND",
                "{\"eventId\":\"evt-test-03\"}");

        assertThrows(IllegalArgumentException.class,
                () -> TopicMessageMapper.toMqttMessage(event));

        assertTrue(publisher.snapshot().isEmpty());
    }
}

record Published(String topic, String payload, int qos,
                 boolean retained) {}

class RecordingPublisher implements MessageHandler {

    private final List<Published> messages =
            new CopyOnWriteArrayList<>();

    @Override
    public void handleMessage(Message<?> message) {
        messages.add(new Published(
                (String) message.getHeaders().get(MqttHeaders.TOPIC),
                (String) message.getPayload(),
                (Integer) message.getHeaders().get(MqttHeaders.QOS),
                (Boolean) message.getHeaders().get(MqttHeaders.RETAINED)));
    }

    List<Published> snapshot() {
        return List.copyOf(messages);
    }

    void clear() {
        messages.clear();
    }
}

@Configuration
class RecordingPublisherConfiguration {

    @Bean(name = "mqttPublisher")
    RecordingPublisher mqttPublisher() {
        return new RecordingPublisher();
    }
}
~~~

This test does not load `MqttTransportConfiguration` and creates no Paho client. It verifies:

1. Messages are sent to the right Spring input channel.
2. `IntegrationFlow` invokes the mapper and injected outbound handler bean.
3. `MqttHeaders.TOPIC` varies with `deviceId` and `kind`.
4. QoS/retained are set accurately per publication type.
5. A device ID containing `/` is rejected before building a topic.

**Limitation:** a fake `MessageHandler` does not verify that the MQTT broker receives data, how Paho's converter processes headers, or whether broker ACLs allow the topic. Those require end-to-end testing.

### 14.1. Testing topic expressions directly

In addition to flow tests, write unit tests for expressions across multiple inputs:

~~~java
var expression = new SpelExpressionParser()
        .parseExpression(
                "'devices/' + payload.deviceId() + '/state'");

var source = MessageBuilder.withPayload(
        new DeviceEvent("evt-1", "device-17", "STATE", "{}"))
        .build();

assertEquals("devices/device-17/state",
        expression.getValue(source, String.class));
~~~

This snippet sits in a JUnit context with `assertEquals`. Test missing IDs, invalid characters, cross-tenant keys, empty results, and modified rules. **Never use an expression over unvalidated data** as authorization to publish.

## 15. Live testing with an MQTT broker

With a local broker and Mosquitto CLI available, start a subscriber:

~~~bash
mosquitto_sub -h localhost -p 1883 \
  -t 'devices/+/state' -v
~~~

Then run the application and invoke `DeviceEventPublisher.publish(...)` with `kind="STATE"`. The subscriber receives the message on the matching topic if the broker is up, the subscription matches, and permissions allow it.

To test retained and topic behavior separately, publish directly with the CLI:

~~~bash
mosquitto_pub -h localhost -p 1883 \
  -t 'devices/device-17/state' \
  -q 1 -r \
  -m '{"eventId":"evt-cli-01","state":"ON"}'
~~~

Start a new subscriber on `devices/device-17/state`: the broker delivers the latest retained state. For one-time commands, omit the `-r` flag:

~~~bash
mosquitto_pub -h localhost -p 1883 \
  -t 'devices/device-17/commands' \
  -q 1 \
  -m '{"commandId":"cmd-cli-01","action":"TURN_OFF"}'
~~~

The CLI only works when the broker is running at the test address and Mosquitto clients are installed. For brokers with TLS/username/password, configure proper credentials/certificates and ACLs—do not disable security just to run examples.

### 15.1. Scenarios to confirm

| Scenario | Test action | What to observe |
| --- | --- | --- |
| Topic from header | Send `STATE` for `device-17`. | Publication arrives at `devices/device-17/state`. |
| Default topic | Send a message without a topic header in a controlled test. | Verify whether it uses the default topic or is rejected; production needs a clear policy. |
| Topic per event kind | Send `COMMAND`. | Topic `.../commands`, `retained=false`. |
| Invalid wildcard on publish | Attempt `devices/+/state` as publish topic. | Reject any publish topic containing wildcards. |
| Unauthorized topic header | Use a topic outside broker ACL. | Publish is rejected or error logged; not marked successful. |
| Retained | Publish retained state and re-subscribe. | Broker delivers stored snapshot; do not mistake it for a new event. |
| Broker offline | Stop broker before sending. | Error/timeout and retry state recorded; no silent loss. |
| QoS 1 duplicate | Resend the same event ID. | Subscriber/DB does not produce duplicate side effects. |
| Replay after rule change | Change topic mapping, then retry an old event. | Route decision/version contract is preserved. |
| Multiple publisher instances | Publish concurrently from outbox. | Claim/idempotency prevents uncontrolled duplicate publishing. |

## 16. Common pitfalls

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Every publication goes to one fixed topic. | `MqttHeaders.TOPIC` not set or default topic masks mapping. | Inspect mapper, headers before handler, and default policy. |
| Subscriber receives nothing even though Spring handler shows no error. | Case/topic mismatch, different subscription filter, broker ACL, or offline subscriber. | Inspect actual PUBLISH topic, broker logs, and subscribe filters. |
| Publishing to `devices/+/state` fails. | Subscription wildcard used in publish topic. | Build a concrete topic using a validated device ID. |
| Data leaks to wrong tenant. | Topic taken directly from untrusted request/header. | Validate authorization, generate topics via server-side mapping, enforce broker ACLs. |
| Inbound receives right source topic, yet outbound sends wrong topic. | Confusing `MqttHeaders.RECEIVED_TOPIC` with `MqttHeaders.TOPIC`. | Compute the new outbound topic and set `MqttHeaders.TOPIC`. |
| QoS/retained differs from expectation. | Missing/wrong-type header or different defaults. | Check `MqttHeaders.QOS`/`RETAINED` constants and converter. |
| Expression reports missing property. | Message/payload root differs from schema; wrong accessor. | Unit test SpEL against exact DTO and headers; validate before mapping. |
| Gateway calling publish waits forever for reply. | MQTT outbound is a one-way adapter. | Build a separate ACK inbound flow and correlation ID. |
| Publish succeeded, yet DB/device has duplicates. | Retry after uncertain result, QoS redelivery, or producer emitted twice. | Idempotency by event/command ID, unique constraints, reconciliation. |
| Internal queue grows endlessly. | Slow outbound, missing poller, or unbounded capacity. | Backpressure, load limits, outbox/persistent queue, monitoring. |
| After restart, events go to a different topic. | Mapping/tenant rules changed between attempts. | Store route decision/version when consistent replay is required. |
| Retained command executes again. | One-time command published with `retained=true`. | Set `retained=false` for commands; clear stale retained messages via controlled process. |

## 17. Practice exercise: topic routing for a multi-device system

**Context:** an application receives state events from SFTP CSV files and commands from an HTTP API. After validation, both types are published to an MQTT broker on per-device topics. Devices update state and send separate ACKs for commands.

Requirements:

1. Define `DeviceEvent(eventId, tenantId, deviceId, kind, json)` with `kind = STATE/COMMAND`.
2. Create one Spring input channel `mqtt.publish.requests`. Both SFTP and HTTP inbound flows must normalize messages before sending to that channel.
3. Enforce policies verifying tenant, device ID, and caller permissions—never accept a raw MQTT topic from an HTTP header.
4. Build topics `tenants/{tenantId}/devices/{deviceId}/state` or `.../commands` depending on kind.
5. Set `MqttHeaders.TOPIC`, `MqttHeaders.QOS`, and `MqttHeaders.RETAINED` with the proper data types.
6. Write an equivalent topic expression and unit-test it against the verified DTO contract.
7. Reject wildcard topics, IDs containing `/`, cross-tenant topics, and unsupported event kinds.
8. Configure the Paho outbound handler, broker URL/TLS/ACLs, and distinct Client IDs per active publisher.
9. Design an outbox persisting the routing decision/event ID for safe recovery across broker timeouts or restarts.
10. Broker subscribers must check event IDs and ACK commands on a dedicated topic. Write an integration test sending a duplicate command and prove side effects occur only once.

**Completion criteria:** topics are constructed from authorized inputs; no cross-tenant publications occur; state/command have explicit QoS/retained policies; brokerless tests verify topic headers and broker tests verify live publishing; error reasons are recorded and replays do not alter destinations unexpectedly.

## 18. Self-check questions

1. How do a Broker URL, an MQTT topic, and a Spring `MessageChannel` differ?
2. Can an MQTT publish topic use `+` or `#` wildcards?
3. Which adapter direction uses `MqttHeaders.TOPIC`?
4. When receiving MQTT inbound, why read `MqttHeaders.RECEIVED_TOPIC` instead of guessing the topic?
5. When is `setDefaultTopic(...)` useful, and what risk does it pose for commands?
6. Are topic expressions evaluated by the MQTT broker?
7. Why should an HTTP caller never be allowed to supply a SpEL expression for the server to execute?
8. When using a topic header, which step is responsible for authorizing the device/tenant?
9. What risk arises if you type header string names manually instead of using `MqttHeaders.TOPIC`?
10. Does setting a topic header automatically carry Spring's `correlationId` across MQTT v3?
11. What do `MqttHeaders.QOS` and `MqttHeaders.RETAINED` change on a publication?
12. Why can `retained=true` be dangerous for a one-time command?
13. Does an MQTT QoS 2 message guarantee the DB writes exactly once?
14. When a broker times out even though it may have received the publish, what conditions must a retry satisfy?
15. What does a test using a fake `MessageHandler` verify, and what does it miss?
16. When changing a rule expression, how do you ensure an event being retried does not change topics?
17. Can one outbound handler publish to multiple MQTT topics without creating a Spring channel per topic?
18. When should you use a Spring router to split across multiple MQTT outbound handlers?
19. If an MQTT subscriber receives nothing even though the outbound handler returned without error, what layers must you check?
20. Why does publishing to the right topic still not prove the device executed a command?

**Hint:** an expression or upstream transformer determines the topic; `MqttHeaders.TOPIC` passes that decision to the outbound handler. The MQTT protocol governs publish/delivery; security, ACKs, and idempotency belong to the application contract.

## 19. Conclusion

**Topic expressions and topic headers** enable Spring Integration's MQTT outbound adapter to publish each message to the right topic rather than locking into one fixed target. `MqttHeaders.TOPIC` carries the resolved topic; SpEL expressions can compute topics from payloads/headers, though only over validated inputs. `setDefaultTopic(...)` fits when a safe fallback topic truly exists. The `MqttHeaders.QOS` and `MqttHeaders.RETAINED` headers add per-publication delivery and snapshot policies.

In the **SPRING_INTEGRATION_ADAPTERS** module, routing may originate from files, SFTP, HTTP, JMS, AMQP, Kafka, or databases before reaching the MQTT handler. Reliable systems clearly separate **Spring channel routing** from **MQTT topic routing**, validate permissions by tenant/device, maintain payload/header contracts, track retries/outboxes, and verify both MQTT delivery and downstream business ACKs.
