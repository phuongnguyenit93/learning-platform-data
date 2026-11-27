# MQTT outbound channel adapter

## 1. Problem statement and learning objectives

A Spring application may receive orders, device updates, or collect data from a database, and then need to **publish** an event or command to an MQTT broker. Other devices and services subscribe to the corresponding topic to receive the message. In Spring Integration, an **MQTT outbound channel adapter** acts as a consumer of a `MessageChannel`: it receives a Spring `Message<?>`, translates the payload and required headers into an MQTT publication, and sends it through the MQTT client to the broker.

This lesson belongs to the **Adapter MQTT** chapter of the **SPRING_INTEGRATION_ADAPTERS** module. The scope of the module is connecting external systems using inbound/outbound adapters, gateways, pollers, and `MessageChannel`; practicing exchanges over files, SFTP, HTTP, JMS, AMQP, Kafka, and databases, while managing message contracts, errors, and connection lifecycles. MQTT outbound is a clear example of the principle: **the endpoint inside the flow receives internal messages, and the protocol client handles sending to the external system**.

A concrete scenario: a smart-home management system receives control commands in Java, builds JSON, and publishes it to the topic `devices/device-17/commands`. The device subscribes to this topic to receive commands and may publish a status message or business ACK on another topic.

After completing this lesson, learners will be able to:

- Explain the outbound direction **IntegrationFlow → outbound handler → MQTT broker → subscriber**.
- Use `MqttPahoMessageHandler`, `MqttPahoClientFactory`, and `DefaultPahoMessageConverter` to configure MQTT outbound.
- Attach a handler to a channel using Java DSL or `@ServiceActivator` without registering duplicate endpoints.
- Set topic, QoS, and retained defaults or **per-message headers**.
- Distinguish synchronous/asynchronous publishing, completion timeout, broker acknowledgment, and business acknowledgment from the device.
- Analyze connection errors, reconnection, queues/backpressure, retries, idempotency, TLS security, and shutdown.
- Test the flow using a fake handler without a broker, and then perform real outbound testing with a test broker.

**Key takeaway:** a successful publish at MQTT QoS 1 or 2 only represents a guarantee at the **MQTT protocol layer**. It does not prove that the subscriber executed the command and persisted the business state successfully.

## 2. Architecture of the MQTT outbound adapter

~~~mermaid
flowchart LR
    APP["Java service / inbound adapter<br/>file, SFTP, HTTP, JMS, Kafka, DB"]
    CH["mqtt.publish.requests<br/>MessageChannel"]
    FLOW["IntegrationFlow<br/>validate / transform / route"]
    HANDLER["MqttPahoMessageHandler<br/>outbound adapter"]
    CLIENT["Paho MQTT client"]
    BROKER[("MQTT broker")]
    SUB["MQTT subscriber / device"]
    APP --> CH --> FLOW --> HANDLER --> CLIENT
    CLIENT -->|"PUBLISH topic / QoS / retained"| BROKER
    BROKER -->|"DELIVER per subscription"| SUB
~~~

| Component | Responsibility | Limitation to understand |
| --- | --- | --- |
| Internal producer | Creates normalized commands/events as Spring messages. | Does not inherently know the MQTT connection state. |
| `MessageChannel` | Hands off messages to the handling endpoint. | `send() == true` is not a business ACK from the subscriber. |
| `IntegrationFlow` | Validates, transforms, routes, and selects the publish target. | Does not send MQTT messages without an outbound handler. |
| `MqttPahoMessageHandler` | Converts `Message<?>` into an MQTT publication. | It is a **one-way outbound handler**, not an MQTT request–reply gateway. |
| `MqttPahoClientFactory` | Supplies configuration and creates MQTT clients for the handler. | Does not replace ACL, TLS, secrets, or broker version management. |
| MQTT broker | Accepts and distributes publications per QoS and session/topic policy. | Does not automatically guarantee the device processes business logic. |
| Subscriber | Receives messages on subscribed topics. | May be offline, fail processing, or miss messages depending on session/QoS. |

The diagram illustrates a one-way outbound flow. When you need status after a device executes a command, you must have a **separate response flow**—for example, an MQTT inbound message-driven adapter subscribing to `devices/+/ack` and correlating the ACK with the command ID. Do not assume the outbound handler will return a `DeviceAck` to the caller.

### 2.1. An outbound adapter is not an inbound adapter

- An **inbound message-driven adapter** subscribes to MQTT topics and emits messages from the broker into a Spring channel; it is triggered by receive callbacks.
- An **outbound channel adapter** subscribes to a **Spring input channel** and publishes messages out to the MQTT broker; it does not need a `@Poller` when the input channel is a `DirectChannel`.
- A **Poller** is only needed on an internal stage when a consumer pulls messages from a `PollableChannel` such as a `QueueChannel`, not for the outbound handler to actively ask the MQTT broker whether data exists.

### 2.2. An outbound adapter is also not a request–reply gateway

An MQTT publication is not equivalent to an HTTP call that directly receives a response. `MqttPahoMessageHandler` primarily performs the **side effect of sending a message**. If a Java method calls a `@MessagingGateway` expecting a result, do not simply wire a one-way outbound handler and assume the gateway will automatically receive a business ACK.

You can design a `void publishCommand(...)` API, or return a tracking ID once the command has been accepted by the application. For a business ACK, another flow must subscribe to the reply topic, verify the correlation ID, and update state under its own timeout.

## 3. MQTT concepts that affect outbound publishing

### 3.1. Topics and naming structure

A publisher sends to **a specific topic**, for example:

~~~text
devices/device-17/commands
devices/device-17/config
devices/device-21/commands
events/inventory/changed
~~~

A publication topic **must not contain subscription wildcards** such as `+` or `#`. Wildcards are used to define *topic filters* for subscribers, such as `devices/+/commands`. If the application extracts a device ID from a request, validate it before building the topic to avoid publishing to another device or tenant.

### 3.2. QoS is a protocol delivery level

| QoS | Meaning in MQTT | Considerations when publishing |
| --- | --- | --- |
| **0 — at most once** | Performs no QoS 1/2 acknowledgment handshake; messages may be lost. | Suitable for telemetry where losing a sample is acceptable if business rules allow. |
| **1 — at least once** | MQTT uses acknowledgments to improve delivery reliability and may redeliver. | Subscriber must handle duplicates by `commandId`/`eventId`. |
| **2 — exactly once at the MQTT layer** | Protocol uses a handshake to reduce duplication of a single valid delivery. | Does **not** mean DB/device side effects happen once or prevent the publisher from emitting duplicate new commands. |

The maximum effective QoS of a delivery path depends on the publisher QoS, subscription QoS, and broker/client behavior. In the outbound handler, `setDefaultQos(1)` is the default for publications without a QoS header override; it does **not** force subscribers to receive at QoS 1.

### 3.3. Retained messages

A publisher can set **retained = true** so the broker stores the latest retained message for the topic (subject to broker limits/policies). Later subscribers can receive the retained message upon subscribing.

| Use case | Is retained appropriate? | Reason |
| --- | --- | --- |
| Current device state | Usually useful. | New subscribers need the latest snapshot. |
| Desired device configuration | Can be appropriate after considering security and overwrite semantics. | Offline devices can receive the desired state when they reconnect. |
| One-time action command | **Usually not**. | New subscribers or re-subscriptions risk re-executing an old command. |
| Financial/order events | Typically use events with IDs and an appropriate store/broker rather than treating retained as an event log. | Retained does not store the full event history. |

A retained message is not a full offline queue. Do not use retained messages as a replacement for a transaction log or event store.

### 3.4. Client ID, session, and multiple instances

`clientId` identifies the MQTT client connecting to the broker. When multiple Spring instances publish concurrently, **each active client needs its own Client ID** to avoid connection contention. In MQTT 3.1.1, `cleanSession` relates to broker-side state/session; for a publish-only client, session persistence does not automatically turn an API request into a recoverable transaction.

If multiple instances process an outbox to publish MQTT messages, you must have an application-side **claim/outbox/partition** mechanism. Giving each instance its own Client ID only resolves connection conflicts; it does not prevent publishing the same business event multiple times.

## 4. Dependencies and choosing the client

This lesson uses **Spring Integration MQTT + Eclipse Paho MQTT v3 API**, suitable for Java 17+ and compatible Spring Boot/Spring Integration versions. With Maven versions managed via the Spring Boot BOM:

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

The MQTT module provides `MqttPahoMessageHandler` for outbound, `MqttPahoMessageDrivenChannelAdapter` for inbound, and MQTT conversion components. Do not mix the Paho v3 configuration in this lesson with Paho MQTT v5 or other client libraries without adjusting the corresponding APIs and semantics.

Key classes:

~~~java
import org.eclipse.paho.client.mqttv3.MqttConnectOptions;
import org.springframework.integration.mqtt.core.DefaultMqttPahoClientFactory;
import org.springframework.integration.mqtt.core.MqttPahoClientFactory;
import org.springframework.integration.mqtt.outbound.MqttPahoMessageHandler;
import org.springframework.integration.mqtt.support.DefaultPahoMessageConverter;
import org.springframework.integration.mqtt.support.MqttHeaders;
~~~

A test broker may run at `tcp://localhost:1883`. This is only a local environment example. On real networks, TLS, authentication, and proper topic ACLs are required; never put passwords directly in source code or logs.

## 5. Complete example: Spring Integration publishing device control commands

Goal: a Java service sends a JSON command to the Spring `MessageChannel` `mqtt.publish.requests`. The flow receives the message, passes it to `MqttPahoMessageHandler`, and the adapter publishes it to the MQTT broker.

Illustrative layout:

~~~text
src/main/java/demo/mqttout/
    MqttOutboundApplication.java
    MqttPublishFlowConfiguration.java
    MqttPublisherConfiguration.java
    DemoCommandPublisher.java

src/main/resources/
    application.properties
~~~

The classes below belong to package `demo.mqttout`; place each top-level `public` class in a file matching its Java class name.

### 5.1. Bootstrap application

~~~java
package demo.mqttout;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MqttOutboundApplication {

    public static void main(String[] args) {
        SpringApplication.run(MqttOutboundApplication.class, args);
    }
}
~~~

### 5.2. Declaring the channel and integration flow

~~~java
package demo.mqttout;

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
public class MqttPublishFlowConfiguration {

    @Bean(name = "mqtt.publish.requests")
    MessageChannel publishRequests() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow mqttOutboundFlow(
            @Qualifier("mqttPublisher") MessageHandler publisher) {

        return IntegrationFlow.from("mqtt.publish.requests")
                .handle(publisher)
                .get();
    }
}
~~~

This is the minimal **channel → outbound handler** flow. `.handle(publisher)` creates an endpoint that consumes messages from the input channel and calls `MessageHandler.handleMessage(...)`. It does not poll the broker and does not produce a business reply.

### 5.3. MQTT client factory and outbound handler beans

~~~java
package demo.mqttout;

import org.eclipse.paho.client.mqttv3.MqttConnectOptions;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.mqtt.core.DefaultMqttPahoClientFactory;
import org.springframework.integration.mqtt.core.MqttPahoClientFactory;
import org.springframework.integration.mqtt.outbound.MqttPahoMessageHandler;
import org.springframework.integration.mqtt.support.DefaultPahoMessageConverter;

@Configuration
public class MqttPublisherConfiguration {

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
            MqttPahoClientFactory clientFactory,
            @Value("${app.mqtt.publisher-client-id}") String clientId,
            @Value("${app.mqtt.default-topic}") String defaultTopic) {

        var handler = new MqttPahoMessageHandler(
                clientId, clientFactory);

        handler.setDefaultTopic(defaultTopic);
        handler.setDefaultQos(1);
        handler.setDefaultRetained(false);
        handler.setAsync(false);
        handler.setCompletionTimeout(5000);
        handler.setConverter(new DefaultPahoMessageConverter());

        return handler;
    }
}
~~~

Explanation:

1. `MqttConnectOptions` describes the broker, connection timeout, keepalive, and session settings. In production, configure authentication/TLS via a secrets management mechanism.
2. `DefaultMqttPahoClientFactory` creates clients for the handler; exposing the factory as a bean centralizes connection configuration.
3. `MqttPahoMessageHandler` is an **outbound message handler**; it publishes a message when the flow's consumer endpoint invokes the handler.
4. `setDefaultTopic(...)` defines the fallback topic if the message has no topic header.
5. `setDefaultQos(1)` and `setDefaultRetained(false)` set default policies; individual messages can supply corresponding headers.
6. `setAsync(false)` selects synchronous publishing at the handler level. It can wait for Paho/broker completion according to QoS, **not for the device to execute the command**.
7. `setCompletionTimeout(5000)` bounds the adapter/client completion wait time; it does not replace a business timeout or the timeout of a separate flow waiting for an ACK on another topic.
8. `DefaultPahoMessageConverter` converts Spring payloads into MQTT payloads. This example uses JSON `String`; if the input is a custom DTO, serialize/validate it before publishing.

`MqttPahoMessageHandler` is a standalone bean, yet **it only gets a consumer endpoint on `mqtt.publish.requests` when wired via `.handle(publisher)`**. Do not add a `@ServiceActivator` for the same handler/channel unless you actually want a second consumer.

### 5.4. Properties for the local environment

File `application.properties`:

~~~properties
app.mqtt.broker-url=tcp://localhost:1883
app.mqtt.publisher-client-id=spring-commands-publisher-local-1
app.mqtt.default-topic=devices/default/commands
~~~

The example assumes a test broker at `localhost:1883`. To run successfully, the broker must be up and allow the publisher to connect/publish. Do not share this Client ID across multiple instances running concurrently.

### 5.5. Producer sending a command through the channel

~~~java
package demo.mqttout;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.ApplicationRunner;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.integration.mqtt.support.MqttHeaders;
import org.springframework.stereotype.Component;

@Component
class DemoCommandPublisher implements ApplicationRunner {

    private final MessageChannel publishRequests;

    DemoCommandPublisher(
            @Qualifier("mqtt.publish.requests")
            MessageChannel publishRequests) {
        this.publishRequests = publishRequests;
    }

    @Override
    public void run(org.springframework.boot.ApplicationArguments args) {
        String command = "{\"commandId\":\"cmd-1001\","
                + "\"deviceId\":\"device-17\","
                + "\"action\":\"TURN_ON\"}";

        boolean sent = publishRequests.send(
                MessageBuilder.withPayload(command)
                        .setHeader(MqttHeaders.TOPIC,
                                "devices/device-17/commands")
                        .setHeader(MqttHeaders.QOS, 1)
                        .setHeader(MqttHeaders.RETAINED, false)
                        .build());

        System.out.println("Channel handoff: " + sent);
    }
}
~~~

This example intentionally runs **once** when Spring Boot starts. If the broker is unavailable or publishing fails, the handler may throw an exception on the send path; in a production application, decide whether startup should depend on the broker and how unsent commands are recovered.

When the broker receives the publication, a device subscribed to `devices/device-17/commands` can receive the payload:

~~~json
{
  "commandId": "cmd-1001",
  "deviceId": "device-17",
  "action": "TURN_ON"
}
~~~

This still does not prove the device turned on successfully. When confirmation is required, the device should publish a **business ACK** with the same `commandId` to an appropriate response topic, and the application needs a separate inbound adapter to receive, validate the ACK, and update command state.

## 6. Message contract: payload and MQTT outbound headers

`MqttPahoMessageHandler` uses the message payload and MQTT headers to create the publication. For example:

~~~text
Spring Message<String>
  payload:
    {"commandId":"cmd-1001","action":"TURN_ON"}
  headers:
    mqtt_topic: "devices/device-17/commands"
    mqtt_qos: 1
    mqtt_retained: false
    correlationId: "trace-cmd-1001"
~~~

Exact header string names should be accessed via `MqttHeaders` constants to avoid coupling to naming conventions and version differences.

| Java constant | Role | Example value |
| --- | --- | --- |
| `MqttHeaders.TOPIC` | Specifies the publish topic, overriding the default topic. | `"devices/device-17/commands"`. |
| `MqttHeaders.QOS` | Specifies QoS for the publication. | `0`, `1`, or `2`. |
| `MqttHeaders.RETAINED` | Specifies whether the message is retained. | `false` for one-time commands. |
| Application-set `correlationId` | Traces between the request and processing flow. | `"trace-cmd-1001"`. |
| `commandId` in payload | Identifies the business command for deduplication and ACK reconciliation. | `"cmd-1001"`. |

Custom headers such as `correlationId` are **not automatically published verbatim** like MQTT v5 user properties in MQTT v3. An MQTT v3 publication mainly carries topic, QoS, retained flag, and a binary payload. If the subscriber needs a correlation ID, include it in the payload according to an agreed schema. Do not automatically serialize all `MessageHeaders`, especially internal headers like `replyChannel` or `errorChannel`.

### 6.1. Default topic versus per-message topic

If a message does not contain `MqttHeaders.TOPIC`, the handler can use `defaultTopic`:

~~~java
handler.setDefaultTopic("events/default");
~~~

However, if the message carries:

~~~java
.setHeader(MqttHeaders.TOPIC, "events/stock/changed")
~~~

then the outbound converter/handler uses the per-message topic according to its configured behavior. **Do not let messages from untrusted sources choose arbitrary topic names.** Validate tenant/device IDs and map them to allowed topics in a transform/router step before the outbound handler.

### 6.2. Why you should not publish arbitrary DTOs via toString()

An internal producer may hold an `OrderCreatedEvent` or `DeviceCommand` as a Java record. Passing a raw object without a clear converter/schema may produce a payload on the MQTT subscriber that is not the JSON expected by the receiver.

A better approach is to serialize the DTO into JSON `String` or `byte[]` using Jackson or a suitable codec, defining:

- Schema version, charset, timestamps, and data units.
- Required fields (`commandId`, `deviceId`, `eventTime`).
- Payload size limits, format, and encoding.
- Duplicate detection and backward-compatibility rules.

The MQTT broker does not validate whether a payload conforms to a business schema; that responsibility belongs to the producer/consumer.

## 7. Synchronous and asynchronous publishing

`MqttPahoMessageHandler` supports two publishing strategies.

### 7.1. Synchronous: setAsync(false)

~~~java
handler.setAsync(false);
handler.setCompletionTimeout(5000);
~~~

In this mode, the handler can block the thread calling `handleMessage(...)` to wait for the publish operation to complete per Paho's mechanism. If the input channel is a `DirectChannel`, the caller sending the message bears that wait time. On connection errors, missing subscribers, or slow broker responses, distinguish:

- MQTT publication completed at Paho/broker per QoS.
- Spring `MessageChannel.send(...)` handed off the message internally.
- The subscriber received or executed the business command.

These are **three distinct milestones**; a 5-second handler timeout is not a 5-second SLA for a device turning on a light.

### 7.2. Asynchronous: setAsync(true)

~~~java
handler.setAsync(true);
handler.setAsyncEvents(true);
~~~

In asynchronous mode, the handler may return before publish completion is confirmed. In supporting versions, Spring Integration provides application events to track publish sent/delivered/not-delivered states; exact event class names and availability should be checked against your version. **Do not treat an early return from `send()` as a successful publish**.

With async publishing, record `commandId`/`eventId`, track callback/event outcomes where required, handle errors after the caller has returned, and design restart recovery. If you merely fire-and-forget, failures occurring later may never reach the original caller.

### 7.3. When to choose which?

| Criterion | Synchronous | Asynchronous |
| --- | --- | --- |
| Call path | Handler can wait for the publish token to complete. | Handler usually hands off work and returns early. |
| Caller latency | Higher if broker/network is slow. | Lower on the call path, though queue growth still requires control. |
| Error handling | Many errors can be thrown directly on the call stack. | Errors may arrive later via callbacks/events/monitoring. |
| Subscriber processing ACK | Not provided by sync alone. | Not provided by async alone. |
| Durability | Not automatically guaranteed across crashes. | Not automatically guaranteed across crashes; persisting publish state is especially important. |

If you must ensure commands are not lost when the broker is offline or the app restarts, do not simply flip `setAsync(false)` to `true`. Design a **durable outbox**, command state machine, retries, and deduplication.

## 8. Registering the outbound handler with @ServiceActivator

Instead of attaching the handler via Java DSL `.handle(publisher)`, Spring Integration allows placing `@ServiceActivator` on a `@Bean` method that returns a `MessageHandler`:

~~~java
@Bean
@ServiceActivator(inputChannel = "mqtt.publish.requests")
MessageHandler mqttOutboundHandler(
        MqttPahoClientFactory factory) {

    var handler = new MqttPahoMessageHandler(
            "mqtt-publisher-unique", factory);
    handler.setDefaultTopic("events/commands");
    handler.setDefaultQos(1);
    handler.setAsync(false);
    return handler;
}
~~~

This snippet is an **alternative configuration** to `mqttPublishFlow` + handler in section 5, not code to add alongside the full example. If the same `DirectChannel` has two consumers, a message may be dispatched to only one of them rather than sent twice as expected. If you want to broadcast to multiple brokers, use a publish–subscribe/multicast architecture with separate error policies per branch.

Keeping the bean and endpoint decoupled makes tests able to swap `MqttPahoMessageHandler` for a fake `MessageHandler` without needing a broker.

### 8.1. MQTT outbound and QueueChannel

If the application puts commands into a `QueueChannel` to decouple request-receiving threads from publish processing, the endpoint needs a **poller** to pull messages from the queue. Java DSL can declare:

~~~java
@Bean(name = "mqtt.publish.buffered")
QueueChannel bufferedPublishRequests() {
    return new QueueChannel(200);
}

@Bean
IntegrationFlow bufferedMqttOutboundFlow(
        @Qualifier("mqttPublisher") MessageHandler publisher) {

    return IntegrationFlow.from("mqtt.publish.buffered")
            .handle(publisher, endpoint -> endpoint.poller(
                    Pollers.fixedDelay(Duration.ofMillis(500))
                            .maxMessagesPerPoll(20)))
            .get();
}
~~~

This snippet is an **alternative option** for the flow in section 5; it requires importing `QueueChannel`, `Pollers`, `Duration`, `@Bean`, and `@Qualifier`. An in-memory `QueueChannel` does not survive restarts, and a poller does not automatically retry a message once it has been dequeued and fails processing. For critical commands, prefer a persistent queue/outbox and a tested recovery policy.

## 9. Publish failures, retries, and idempotency

An MQTT outbound flow can fail at several points:

~~~mermaid
flowchart TD
    P["Application creates command / event"]
    V{"Validate payload and topic?"}
    CH["MessageChannel"]
    H["MqttPahoMessageHandler"]
    B{"Broker accepts publish?"}
    S["Subscriber processes"]
    OK["Record business outcome"]
    ERR["Error flow / outbox / retry"]
    P --> V
    V -->|"Yes"| CH --> H --> B
    V -->|"No"| ERR
    B -->|"MQTT succeeded"| S --> OK
    B -->|"Error / unknown"| ERR
    H -. "connection / timeout" .-> ERR
~~~

| Failure | Where detected? | Appropriate handling |
| --- | --- | --- |
| Invalid or unauthorized topic | Validation, broker ACL. | Reject/quarantine; fix config or permissions, do not retry endlessly. |
| Broker disconnected | Client/handler and metrics. | Reconnect with backoff, mark message as not reliably published. |
| Completion timeout | Sync handler or publish callback. | Uncertain outcome; broker may have received it, so retries must be idempotent. |
| Payload serialization failure | Transformer/converter. | Fix data/codec; quarantine with context. |
| Internal queue full | Channel/producer. | Load shedding, backpressure, explicit reject/retry policy. |
| Subscriber did not process | Business ACK missing or timed out. | Track command ID, retry/reconcile at the business layer. |
| Lost ACK response | Reply flow or network. | Query device/target state instead of blindly re-issuing commands. |

### 9.1. Example of duplicate publish risk

The application sends command `cmd-1001` at QoS 1. The broker may have received the publication, yet the application disconnects before receiving the acknowledgment. If the application retries with a new publication, the subscriber may receive **two messages with the same command ID**.

Therefore, the payload must carry a stable ID, for example:

~~~json
{
  "commandId": "cmd-1001",
  "deviceId": "device-17",
  "action": "TURN_ON",
  "issuedAt": "2026-11-23T02:00:00Z"
}
~~~

The consumer needs a deduplication mechanism, or commands must be business-idempotent. For high-risk operations such as unlocking, payments, or critical configuration changes, commands should include expiry, authorization, version/state preconditions, and dedicated confirmation; MQTT QoS alone is not sufficient safety control.

### 9.2. Transactional outbox for critical data

When a transaction writes to a database and also needs to publish to MQTT, you cannot assume the database transaction spans the broker. A common architecture:

~~~mermaid
flowchart LR
    API["Business service"]
    DB[("Database<br/>business + outbox")]
    WORKER["Outbox publisher"]
    MQTT["MQTT outbound adapter"]
    BROKER[("Broker")]
    ACK["ACK/state tracking"]
    API -->|"Single DB transaction"| DB
    DB -->|"Read pending events"| WORKER
    WORKER --> MQTT --> BROKER
    BROKER -. "response per contract" .-> ACK
~~~

Write the event into the outbox **in the same DB transaction as the business record**. A worker publishes from the outbox, tracks send results, updates status, and retries with backoff and idempotency. If the worker crashes between publishing and updating the outbox, it may re-send, so the subscriber must still deduplicate by event ID.

**Do not mark an event "processed by subscriber" merely because the MQTT publish token succeeded.** That only proves completion of the send operation at the corresponding level, not the business outcome on the receiver.

## 10. Backpressure, performance, and channel types

MQTT outbound easily becomes a bottleneck when upstream produces messages faster than the broker or network can accept.

| Channel before handler | Behavior | Risks and controls |
| --- | --- | --- |
| `DirectChannel` | Handler publishes immediately on the sender thread. | Slow broker slows the caller; control timeouts and latency. |
| `ExecutorChannel` | Publishing is handed off to a thread pool. | Full executor queue, async errors, shutdown; bound resources. |
| `QueueChannel` | Messages wait for a polling consumer. | Capacity, retries, persistent store, backlog metrics, and poll schedule. |
| `PublishSubscribeChannel` | Delivers the same message to multiple consumers. | Use only when truly sending to multiple destinations; manage branch outcomes independently. |

Do not confuse an **MQTT broker buffer** with a **Spring QueueChannel**. An internal queue does not push data to the broker until a consumer pulls the message and the handler publishes it. On application restart, an in-memory queue loses messages; when the broker is offline, the backlog can exceed capacity and cause upstream errors.

Metrics to track: publications per topic/QoS, publish completion duration, timeouts/reconnects, pending outbox count, queue depth, retry counts, unknown-outcome messages, late ACKs, and duplicates by command ID.

### 10.1. Preserving per-device ordering

If the same device receives `TURN_ON` followed by `TURN_OFF`, publishing concurrently across multiple threads can alter the observed order when network delays or retries occur. For order-sensitive commands, define sequence/version numbers, partitioning, or a controlled per-device producer path. Do not infer that calling `MessageChannel.send(...)` in order guarantees every subscriber processes commands in that order in all scenarios.

## 11. Lifecycle: startup, reconnect, and shutdown

An outbound adapter must be managed as a real connection resource, not just a Java method:

1. **Startup:** create factory/handler beans and open the connection when the endpoint/client needs to publish; decide whether the application is allowed to start when the broker is unavailable.
2. **Broker unavailable:** how unsent commands are recorded, retried, backed off, and alerted; never swallow errors and treat them as published.
3. **Reconnect:** Client ID, session, TLS, and publish permissions remain valid; monitor reconnect counts.
4. **Credential rotation:** passwords/certificates are rotated securely, avoiding extended downtime or secret exposure.
5. **Shutdown:** stop accepting new requests, drain in-flight/pending publishes within a time limit, close resources, and preserve incomplete outbox items.
6. **Multi-instance scaling:** no duplicate Client IDs; outbox items are properly claimed/partitioned; subscribers handle duplicates.

A Spring-managed handler does not automatically guarantee that every message buffered in Paho's memory will be published after a crash. If strict recovery guarantees are required, establish a **durable state contract** in the application or supporting infrastructure.

## 12. Outbound MQTT security

| Risk | Mitigation |
| --- | --- |
| Eavesdropping on commands over the network | Use TLS and verify the broker certificate; configure Paho SSL appropriately for the environment. |
| Exposed passwords | Load secrets from env/secret manager, restrict logging, rotate credentials. |
| Publisher sending to the wrong topic | Enforce broker ACLs and validate topic/tenant/device ID in the application. |
| Duplicate Client ID | Give each active client its own ID; prevent mutual disconnects. |
| Payload triggering unauthorized actions | Business-level signatures/authorization if required; validate command/schema. |
| Replaying expired commands | Business expiry, timestamps, versioning, and device-side deduplication. |
| Dangerous retained commands | Default to `retained=false` for one-time actions to avoid replaying stale commands. |
| Sensitive payloads and metadata in logs | Log `commandId`, validated topic, and error codes; avoid printing secrets/full payloads. |

In MQTT v3, TLS typically uses connections like `ssl://broker-host:8883` and appropriate SSL socket/certificate settings in `MqttConnectOptions`. Merely changing the URL to `ssl://` without configuring the required trust store may not suffice for a secure connection. Also never disable hostname/certificate verification in production.

## 13. Testing the outbound flow without a broker

To test **channel → IntegrationFlow → outbound handler**, you can reuse `MqttPublishFlowConfiguration` from section 5 while **replacing the `mqttPublisher` bean with a fake `MessageHandler`**. This test does not load `MqttPublisherConfiguration`, so it creates no Paho client and performs no network I/O.

Add the dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Create `MqttPublishFlowTest.java` in package `demo.mqttout`:

~~~java
package demo.mqttout;

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
import org.springframework.integration.mqtt.support.MqttHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = {
        MqttPublishFlowConfiguration.class,
        FakePublisherConfiguration.class
})
class MqttPublishFlowTest {

    @Autowired
    @Qualifier("mqtt.publish.requests")
    MessageChannel requests;

    @Autowired
    RecordingPublisher publisher;

    @BeforeEach
    void reset() {
        publisher.clear();
    }

    @Test
    void forwardsPayloadAndOutboundHeadersToHandler() {
        String payload = "{\"commandId\":\"cmd-test-1\","
                + "\"action\":\"TURN_ON\"}";

        boolean accepted = requests.send(
                MessageBuilder.withPayload(payload)
                        .setHeader(MqttHeaders.TOPIC,
                                "devices/test-1/commands")
                        .setHeader(MqttHeaders.QOS, 1)
                        .setHeader(MqttHeaders.RETAINED, false)
                        .build());

        assertTrue(accepted);
        assertEquals(
                List.of(new PublishedCommand(
                        payload, "devices/test-1/commands",
                        1, false)),
                publisher.snapshot());
    }
}

record PublishedCommand(
        String payload, String topic, int qos, boolean retained) {}

class RecordingPublisher implements MessageHandler {

    private final List<PublishedCommand> recorded =
            new CopyOnWriteArrayList<>();

    @Override
    public void handleMessage(Message<?> message) {
        recorded.add(new PublishedCommand(
                (String) message.getPayload(),
                (String) message.getHeaders().get(MqttHeaders.TOPIC),
                (Integer) message.getHeaders().get(MqttHeaders.QOS),
                (Boolean) message.getHeaders().get(MqttHeaders.RETAINED)));
    }

    List<PublishedCommand> snapshot() {
        return List.copyOf(recorded);
    }

    void clear() {
        recorded.clear();
    }
}

@Configuration
class FakePublisherConfiguration {

    @Bean(name = "mqttPublisher")
    RecordingPublisher mqttPublisher() {
        return new RecordingPublisher();
    }
}
~~~

What the test proves:

- The `mqtt.publish.requests` bean has a properly wired consumer endpoint.
- `IntegrationFlow` forwards the message to the `mqttPublisher` bean via `.handle(...)`.
- The `String` payload and three MQTT outbound headers arrive intact at the handler.
- With `DirectChannel`, assertions can run immediately after `send(...)`.

**Limitation:** the test does not verify Paho's real converter, broker topic publishing, QoS ACKs, reconnection, or retained behavior. That is why end-to-end tests with a broker are still needed. Do not conclude MQTT publishing succeeded just because a fake handler received the message.

## 14. End-to-end testing with an MQTT broker

When you have a local broker and the MQTT CLI, you can start a subscriber first:

~~~bash
mosquitto_sub -h localhost -p 1883 \
  -t 'devices/+/commands' -v
~~~

Then run `MqttOutboundApplication`. `DemoCommandPublisher` publishes the command JSON to `devices/device-17/commands`. The subscriber should print the corresponding topic and payload:

~~~text
devices/device-17/commands {"commandId":"cmd-1001","deviceId":"device-17","action":"TURN_ON"}
~~~

Prerequisites: the broker is running, the application uses matching URL/topic settings, and the broker allows both test clients to connect; the `mosquitto_sub` CLI is installed. For brokers requiring authentication or TLS, configure both the application and the CLI with proper credentials; never disable production broker security just for testing.

### 14.1. Scenarios to verify

| Scenario | How to test | What you must conclude accurately |
| --- | --- | --- |
| Default topic | Omit `MqttHeaders.TOPIC`. | Publication uses the configured default topic. |
| Override topic | Set a topic header different from default. | Message reaches the specified topic if ACL permits. |
| QoS 0/1/2 | Vary QoS in the test environment. | Verify protocol delivery/ack, do not infer business execution. |
| Retained | Publish retained to a test topic. | New subscriber receives the retained message upon subscribing. |
| Broker offline | Stop the broker before or during publish. | Errors/timeouts and retry-needed state are recorded; commands are not silently lost. |
| Broker returns | Start the broker, publish/retry per policy. | Messages recover without duplicate side effects. |
| Subscriber offline | Stop subscriber, publish, then restart subscriber. | Outcome depends on QoS/session/broker and retained; do not assume full replay. |
| Unauthorized publish | Topic violates ACL. | Error is reported clearly and the command is not marked successful. |
| Duplicate command ID publish | Resend the same JSON/event. | Subscriber or DB does not perform duplicate business actions. |
| High throughput | Publish more messages faster than the broker. | Queues/pools are bounded, resources are not exhausted, backlog metrics exist. |

If an ACK is required after device execution, implement an inbound subscription on `devices/+/ack` and reconcile `commandId`; tests must verify **device state** rather than just looking at `mosquitto_sub` output.

## 15. Common configuration mistakes

| Symptom | Common cause | How to investigate |
| --- | --- | --- |
| Message sent to channel, but broker does not receive it. | Flow never registered consumer/handler bean, wrong channel, broker offline. | Check `mqtt.publish.requests`, `.handle(publisher)`, and client logs. |
| Handler reports invalid topic. | Empty/invalid topic header, missing default topic, wildcard used on publish. | Check `MqttHeaders.TOPIC` and topic mapping. |
| Cannot connect to broker. | Wrong URL, DNS, port, TLS, or credentials. | Check Paho options, network, certificates, and broker ACLs. |
| Two instances disconnect each other. | Duplicate Client ID. | Generate a unique Client ID per active client. |
| Sent with QoS 1, but device does not respond. | QoS only guarantees MQTT delivery; device did not process/publish ACK. | Design a dedicated business ACK with timeout. |
| New subscriber executes old command. | Command publication was marked retained. | Use `retained=false` for one-time commands. |
| `send()` returns true, yet publish fails later. | `setAsync(true)`, processed on another thread, or delayed failure. | Monitor publish completions/callbacks and outbox state. |
| Command is sent twice after retry. | Broker received it, but client missed ACK; app sent a new publication. | Use `commandId`, deduplication, and reconciliation. |
| Queue holds many messages without publishing. | `QueueChannel` is missing a polling consumer. | Add an appropriate poller and monitor queue depth. |
| Restart loses unsent commands. | Queue or state held only in RAM. | Use an outbox/persistent store and recovery policy. |
| Receiver gets malformed JSON. | Converter did not serialize DTO per agreed schema. | Explicitly serialize `String`/`byte[]` and add contract tests. |
| Java gateway times out even though broker received command. | One-way MQTT outbound does not produce a business reply. | Separate ACK flow, return a tracking ID, and reconcile. |

## 16. Practice exercise: device command dispatch system

**Context:** an air-conditioner management application receives temperature change requests over HTTP and saves the command to a database. It then sends an MQTT command to the device subscribed to `devices/<deviceId>/commands`; the device publishes an ACK to `devices/<deviceId>/ack`.

Requirements:

1. Design the `TemperatureCommand(commandId, deviceId, targetCelsius, issuedAt)` DTO and outbound JSON schema.
2. Configure `MqttPahoClientFactory` from environment settings, including TLS and credentials when required by the broker.
3. Register `MqttPahoMessageHandler` as an independent bean with a default test topic, QoS 1, and `retained=false`.
4. Create `mqtt.publish.requests` and an `IntegrationFlow` using the handler bean to publish.
5. Validate device ID, topic ACL/tenant, and temperature bounds before setting `MqttHeaders.TOPIC`.
6. Write the business command alongside an outbox record in a single DB transaction; a worker reads the outbox and publishes via MQTT.
7. Handle broker disconnects, completion timeouts, restarts, and bounded retries; do not mark a command completed merely after publishing.
8. Create a separate MQTT inbound adapter subscribing to ACKs, correlating `commandId`, and handling late, duplicate, or unmatched ACKs.
9. Write brokerless flow tests for payload/topic/QoS/retained and broker-backed tests for publish, ACLs, retained, and disconnect/reconnect.
10. Explain when to use a sync versus async publisher, and how to apply backpressure by device count/request rate.

**Completion criteria:** no publishing to wrong topics, no retained one-time commands, broker failures do not lose durable commands, retries do not trigger duplicate commands outside contract, and states are clearly separated into **ACCEPTED → PUBLISHED → DEVICE_ACKNOWLEDGED**.

## 17. Self-check questions

1. Where does `MqttPahoMessageHandler` receive messages from, and where does it send them?
2. Does an outbound adapter need a `@Poller` when its input is a `DirectChannel`?
3. What is the difference between `MqttHeaders.TOPIC` and a topic filter containing `+`/`#`?
4. When is `defaultTopic` used?
5. Does `setDefaultQos(1)` guarantee that subscribers execute a command exactly once?
6. Why can `retained=true` be dangerous for one-time commands?
7. How should Client IDs be configured for two publishers running concurrently?
8. How does `async=true` differ from `async=false` in error timing and latency?
9. Why does `MessageChannel.send(...)` returning `true` not prove MQTT publishing succeeded?
10. Why is a successful MQTT publish token not a business ACK?
11. When retrying after a timeout, how do you avoid sending duplicate `commandId` values?
12. Does `QueueChannel` automatically persist messages across restarts?
13. When a handler publishes JSON, why should DTOs be explicitly serialized?
14. What does a test using a fake `MessageHandler` prove, and what does it leave unproven?
15. When switching a broker from TCP to TLS, what additional things must be verified?
16. When the same event must be sent to both MQTT and Kafka, how should state and retries be designed for each destination?

**Hint:** MQTT outbound is a one-way sending endpoint and does not directly return a business reply. Topic/QoS/retained headers control the publication, while execution after broker receipt depends on subscribers, separate ACKs, and idempotency. End-to-end reliability must be tested under network, broker, app, and subscriber failures.

## 18. Conclusion

The **MQTT outbound channel adapter** sends data from Spring Integration to an MQTT broker via `MqttPahoMessageHandler`. A `MessageChannel` accepts internal commands/events, `IntegrationFlow` validates and forwards them to the handler, and `MqttPahoClientFactory` supplies the protocol connection. Topic, QoS, and retained settings can come from defaults or per-message headers.

Within the **SPRING_INTEGRATION_ADAPTERS** module, MQTT outbound is one of the ways to integrate external systems alongside files, SFTP, HTTP, JMS, AMQP, Kafka, and databases. Proper design clearly separates **Spring message handoff**, **broker publish completion**, and **subscriber business completion**, while managing TLS/ACLs, Client IDs, retries/backpressure, idempotency, outboxes, and testing both the flow and real broker connectivity.
