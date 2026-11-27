# MQTT inbound message-driven adapter

## 1. Overview: why is MQTT inbound message-driven?

MQTT (Message Queuing Telemetry Transport) is a publish–subscribe protocol commonly used when devices or edge systems send telemetry data, sensor status, or events to an **MQTT broker**. A publisher sends a message to a **topic**; the broker distributes the message to subscribers with matching subscriptions.

In Spring Integration, an **MQTT inbound message-driven adapter** creates an MQTT subscriber, receives messages pushed by the broker via a callback, and converts them into `Message<?>` instances to send to a `MessageChannel`. This is an **event-driven** inbound adapter, not a `MessageSource` with a `@Poller` that polls the broker periodically.

This lesson belongs to the **Adapter MQTT** chapter of the **SPRING_INTEGRATION_ADAPTERS** module. The module focuses on connecting external systems using inbound/outbound adapters, gateways, pollers, and `MessageChannel`; practicing with files, SFTP, HTTP, JMS, AMQP, Kafka, databases, and MQTT, while clarifying message contracts, errors, and connection lifecycles. With MQTT, the key boundary to understand is **publisher → broker → MQTT client → Spring message channel → integration flow**.

After completing this lesson, learners will be able to:

- Distinguish MQTT **message-driven inbound** from polling inbound adapters for files/JDBC/SFTP.
- Explain topics, subscription wildcards, client IDs, QoS, retained messages, sessions, and reconnection.
- Create an `MqttPahoMessageDrivenChannelAdapter` using an `MqttPahoClientFactory` and send messages to a channel.
- Forward payloads/headers to an `IntegrationFlow`, format JSON, or route by topic.
- Design error handling, deduplication, backpressure, security, processing acknowledgment, and lifecycle management.
- Test the flow without a broker, and then perform real integration testing with a test MQTT broker.

**Core point:** The MQTT broker can deliver a message to a client, but that **does not mean** the data has been successfully written to the application's database or target system. You must distinguish MQTT QoS from business processing guarantees.

## 2. Processing flow from broker to Spring Integration

~~~mermaid
flowchart LR
    DEV["Sensor / Publisher"]
    BROKER[("MQTT broker")]
    PAHO["MQTT Paho client<br/>subscribe topic filter"]
    ADAPTER["MqttPahoMessageDrivenChannelAdapter<br/>message-driven callback"]
    CH["mqtt.telemetry.in<br/>MessageChannel"]
    FLOW["IntegrationFlow<br/>validate / transform / route"]
    HANDLER["Service activator<br/>or outbound adapter"]
    DB[("Database / target system")]
    DEV -->|"PUBLISH topic + payload"| BROKER
    BROKER -->|"DELIVER per subscription"| PAHO
    PAHO --> ADAPTER
    ADAPTER -->|"Message<?>"| CH
    CH --> FLOW --> HANDLER --> DB
~~~

The responsibilities are divided as follows:

| Component | Responsibility | What it does not guarantee |
| --- | --- | --- |
| Publisher | Creates messages with topic, payload, QoS, and retained flag. | Does not know when the Spring handler has finished processing. |
| MQTT broker | Distributes messages to subscriptions according to session/QoS. | Does not manage database transactions in the application. |
| Paho MQTT client | Establishes the connection, subscribes, and receives callbacks. | Does not automatically determine business DTOs. |
| `MqttPahoMessageDrivenChannelAdapter` | Converts MQTT deliveries into Spring messages. | Does not automatically parse every JSON schema or handle side effects. |
| `MessageChannel` | Hands off messages to the flow. | Does not inherently persist messages or create consumers. |
| `IntegrationFlow` | Validates, transforms, routes, and invokes handlers. | Does not automatically turn MQTT QoS into business exactly-once processing. |
| Handler/outbound adapter | Writes to DB, sends HTTP/JMS/Kafka, writes files. | Does not automatically avoid duplicates without proper design. |

At startup, the inbound adapter creates or uses a client from the factory, connects to the broker, and subscribes to the topic filters. When the broker delivers a matching message, the client callback is converted by the adapter into a Spring `Message<?>` and sent to the configured channel. **No `@Poller` is needed** for the MQTT message-driven receiving step.

## 3. MQTT concepts you must understand before configuring the adapter

### 3.1. Topic, topic filter, and wildcards

An MQTT publisher sends data to a **specific topic**, for example:

~~~text
sensors/room-17/temperature
sensors/room-17/humidity
sensors/room-21/temperature
~~~

A subscriber can subscribe to a **topic filter** with wildcards:

| Subscription filter | Meaning | Matching example |
| --- | --- | --- |
| `sensors/room-17/temperature` | Receives only the exact topic name. | `sensors/room-17/temperature`. |
| `sensors/+/temperature` | `+` matches exactly **one** topic level. | `sensors/room-21/temperature`. |
| `sensors/#` | `#` matches multiple remaining levels; must be at the end of the filter. | `sensors/room-17/temperature`, `sensors/room-17/humidity`. |
| `devices/+/state` | Receives the state of each device at a single level. | `devices/device-42/state`. |

Wildcards are **subscription** symbols, not a way to name a topic for a publisher to send messages to. For device data, design topic names systematically, limit subscriptions to what is strictly necessary, and avoid overly broad subscriptions that flood the application with irrelevant messages.

### 3.2. MQTT QoS is not the business processing count

| QoS | Delivery between MQTT client and broker | Consequence for Spring Integration |
| --- | --- | --- |
| **0 — at most once** | Delivered at most once at the MQTT layer, without delivery acknowledgments corresponding to QoS 1/2. | Messages may be lost on network drops or if the consumer cannot keep up. |
| **1 — at least once** | Acknowledgment mechanism allows redelivery to improve delivery reliability. | The application must handle duplicates, for example by `eventId`. |
| **2 — exactly once (MQTT protocol)** | Protocol uses a handshake to avoid duplicate processing of an MQTT publication under QoS 2. | Does **not** mean downstream database/HTTP transactions occur only once. |

The effective delivery QoS depends on the published message's QoS, the subscription QoS, and broker/client rules. In the example, `setQos(1)` configures the subscription QoS; it **does not force publishers to publish at QoS 1**.

If a publisher sends the same business event twice as two separate publications, QoS 2 still does not replace idempotency in the processing service.

### 3.3. Client ID, clean session, and retained messages

- **Client ID** identifies an MQTT client session on the broker. Multiple instances using the same Client ID can disconnect each other or cause unstable reconnect behavior; assign a unique ID to each active client.
- In MQTT 3.1.1/Paho v3, `cleanSession=false` allows using a more persistent session on the broker when supported by the broker, typically combined with a stable Client ID and QoS 1/2. It does **not** automatically create a checkpoint for the application's database.
- A **Retained message** is the most recent message stored by the broker on a topic when the publisher sets the retained flag. A new subscriber can receive the retained message immediately upon subscribing, even if it is not newly generated telemetry.
- **Last Will and Testament (LWT)** is a message configured for the broker to publish when a client disconnects abnormally according to protocol conditions; this is an MQTT mechanism, not a Spring exception handler.

**Designing IDs and sessions for your deployment:** if two instances need to receive **all of the same events** as two independent subscribers, each instance needs its own Client ID and appropriate subscription. If the goal is to load-balance a stream, do not treat sharing a Client ID as a safe competing-consumers group; consider shared subscriptions depending on the broker/protocol version or an appropriate queueing architecture.

## 4. Spring Boot configuration and MQTT dependency

With Java 17+, Spring Boot, and Spring Integration under Boot's dependency management, use:

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

`spring-integration-mqtt` provides MQTT endpoints based on Eclipse Paho, including `MqttPahoMessageDrivenChannelAdapter`. The example below uses the **Paho MQTT v3 API** (`org.eclipse.paho.client.mqttv3.MqttConnectOptions`) and MQTT 3.1.1; do not confuse these classes with the MQTT v5 API/adapter from other versions.

Core classes:

~~~java
import org.eclipse.paho.client.mqttv3.MqttConnectOptions;
import org.springframework.integration.mqtt.core.MqttPahoClientFactory;
import org.springframework.integration.mqtt.core.DefaultMqttPahoClientFactory;
import org.springframework.integration.mqtt.inbound.MqttPahoMessageDrivenChannelAdapter;
import org.springframework.integration.mqtt.support.DefaultPahoMessageConverter;
import org.springframework.integration.mqtt.support.MqttHeaders;
~~~

In real deployments, the broker URL, username, password, client ID, and topics must come from environment configuration or secret management—never hardcode credentials in source code.

### 4.1. Example configuration properties

Create `src/main/resources/application.properties`:

~~~properties
app.mqtt.broker-url=tcp://localhost:1883
app.mqtt.client-id=telemetry-inbound-local-1
app.mqtt.topic=sensors/+/temperature
~~~

The configuration above assumes a **test broker** is listening locally on port 1883. It does not start a broker automatically. In real environments, you must configure an existing broker, authentication, and TLS instead of using unencrypted TCP connections when transmitting data over untrusted networks.

## 5. Working example: MQTT inbound adapter → channel → processing flow

This example receives JSON telemetry on the topic `sensors/+/temperature`. To keep the focus on the inbound adapter, the handler **does not parse JSON yet**, and instead records the payload as a `String` along with the received topic. A Jackson transformer and validator can be added in the next step.

Code layout:

~~~text
src/main/java/demo/mqtt/
    MqttInboundApplication.java
    MqttTransportConfiguration.java
    TelemetryFlowConfiguration.java
    TelemetrySink.java

src/main/resources/
    application.properties
~~~

The classes in the snippets below belong to the `demo.mqtt` package.

### 5.1. Application bootstrap

~~~java
package demo.mqtt;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MqttInboundApplication {

    public static void main(String[] args) {
        SpringApplication.run(MqttInboundApplication.class, args);
    }
}
~~~

Spring Boot scans the `@Configuration` classes in the application package. Spring Integration manages the adapter bean and endpoints once the application context is initialized.

### 5.2. MQTT client factory and inbound adapter

~~~java
package demo.mqtt;

import org.eclipse.paho.client.mqttv3.MqttConnectOptions;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.mqtt.core.DefaultMqttPahoClientFactory;
import org.springframework.integration.mqtt.core.MqttPahoClientFactory;
import org.springframework.integration.mqtt.inbound.MqttPahoMessageDrivenChannelAdapter;
import org.springframework.integration.mqtt.support.DefaultPahoMessageConverter;
import org.springframework.messaging.MessageChannel;

@Configuration
class MqttTransportConfiguration {

    @Bean
    MqttPahoClientFactory mqttClientFactory(
            @Value("${app.mqtt.broker-url}") String brokerUrl) {

        var options = new MqttConnectOptions();
        options.setServerURIs(new String[] {brokerUrl});
        options.setConnectionTimeout(10);
        options.setKeepAliveInterval(30);
        options.setCleanSession(false);

        var factory = new DefaultMqttPahoClientFactory();
        factory.setConnectionOptions(options);
        return factory;
    }

    @Bean
    MqttPahoMessageDrivenChannelAdapter mqttInboundAdapter(
            MqttPahoClientFactory mqttClientFactory,
            @Qualifier("mqtt.telemetry.in") MessageChannel inputChannel,
            @Value("${app.mqtt.client-id}") String clientId,
            @Value("${app.mqtt.topic}") String topicFilter) {

        var adapter = new MqttPahoMessageDrivenChannelAdapter(
                clientId, mqttClientFactory, topicFilter);

        adapter.setQos(1);
        adapter.setCompletionTimeout(5000);
        adapter.setRecoveryInterval(10000);
        adapter.setConverter(new DefaultPahoMessageConverter());
        adapter.setOutputChannel(inputChannel);
        return adapter;
    }
}
~~~

Component breakdown:

1. `MqttConnectOptions` defines the broker, connection timeout, keepalive, and session settings. For production, authentication/TLS must be added; do not use `cleanSession=false` as a substitute for durable event storage.
2. `DefaultMqttPahoClientFactory` creates clients with those options for the adapter to use. Separating the factory into a bean allows controlled reuse of connection settings.
3. `MqttPahoMessageDrivenChannelAdapter` is a **message-driven inbound endpoint** that subscribes to topic filters. It does not call `receive()` from a `@Poller`.
4. `setQos(1)` sets the subscription QoS; `setCompletionTimeout(5000)` and `setRecoveryInterval(10000)` tune timeout/recovery limits of the adapter according to the API version in use.
5. `DefaultPahoMessageConverter` converts MQTT messages into Spring `Message<?>` instances. In its default configuration, it typically produces text payloads as `String`; if binary is needed, choose an appropriate converter and update the downstream contract.
6. `setOutputChannel(inputChannel)` specifies where the adapter **emits messages** into Spring Integration. The channel bean name is `mqtt.telemetry.in`; an inbound adapter has no internal input channel in the sense of receiving messages from a flow.

**Security:** the demo omits username/password because a local broker may be configured privately for testing. For brokers requiring authentication, load secrets from the environment and configure `MqttConnectOptions` (username, password/TLS socket factory). Do not put passwords in logs, source control, or shell command examples used in production.

### 5.3. Channel, IntegrationFlow, and handler

~~~java
package demo.mqtt;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.mqtt.support.MqttHeaders;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
class TelemetryFlowConfiguration {

    @Bean(name = "mqtt.telemetry.in")
    MessageChannel mqttTelemetryInput() {
        return new DirectChannel();
    }

    @Bean
    TelemetrySink telemetrySink() {
        return new TelemetrySink();
    }

    @Bean
    IntegrationFlow telemetryFlow(TelemetrySink sink) {
        return IntegrationFlow.from("mqtt.telemetry.in")
                .handle(String.class, (payload, headers) -> {
                    Object topic = headers.get(MqttHeaders.RECEIVED_TOPIC);
                    sink.accept(new ReceivedTelemetry(
                            topic == null ? "unknown" : topic.toString(),
                            payload));
                    return null; // one-way inbound flow
                })
                .get();
    }
}
~~~

Component that records data for the demo:

~~~java
package demo.mqtt;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

record ReceivedTelemetry(String topic, String payload) {}

class TelemetrySink {

    private final List<ReceivedTelemetry> received =
            new CopyOnWriteArrayList<>();

    void accept(ReceivedTelemetry telemetry) {
        received.add(telemetry);
        System.out.println("MQTT received: " + telemetry.topic());
    }

    List<ReceivedTelemetry> snapshot() {
        return List.copyOf(received);
    }

    void clear() {
        received.clear();
    }
}
~~~

Spring Integration receives the MQTT message, converts the payload to `String`, and attaches metadata to headers. The handler reads `MqttHeaders.RECEIVED_TOPIC` to identify the exact topic delivered by the broker, then records the data. Header names/types depend on the library API version; in Java code, use `MqttHeaders` constants rather than guessing header strings.

With `DirectChannel`, the handler runs synchronously on the channel's dispatch thread on the Spring side; because MQTT callbacks also have client thread/ack constraints, do not place unbounded HTTP calls or database queries directly on the callback path.

### 5.4. Sample data flow

Publisher sends:

~~~text
Topic: sensors/room-17/temperature
QoS:   1
Payload:
{"deviceId":"room-17","celsius":26.5,"eventId":"evt-1001"}
~~~

The application receives it as a Spring message with corresponding payload and metadata:

~~~text
Message<String>
  payload = "{\"deviceId\":\"room-17\",\"celsius\":26.5,\"eventId\":\"evt-1001\"}"
  headers:
    mqtt_receivedTopic: "sensors/room-17/temperature"
    ... other MQTT metadata depending on converter/version ...
~~~

In the example, `TelemetrySink` records `ReceivedTelemetry(topic, payload)`. Do not claim the JSON has been validated merely because the text payload reached the handler. To enforce business checks, add a JSON parsing transformer, validate the schema, and route invalid messages to a dedicated quarantine channel.

## 6. How MQTT inbound differs from polling inbound adapters

MQTT inbound is described as **message-driven** because the broker pushes messages to the subscriber over an active connection. In contrast, an inbound adapter reading files or a database typically needs a poller to invoke `MessageSource.receive()`.

| Criterion | MQTT message-driven inbound | File/JDBC polling inbound |
| --- | --- | --- |
| Trigger source | MQTT client receives a callback when the broker delivers a message. | Poller actively calls the source on a schedule. |
| Is `@Poller` required? | **No**. | Normally **yes** for a `MessageSource`. |
| Primary configuration | Broker, Client ID, topic filter, QoS, session, reconnect. | Source, directory/query, filter/checkpoint, poll interval. |
| Message path | Broker → Paho callback → adapter → output channel. | Scheduler → source.receive() → adapter → output channel. |
| Arrival rate | Depends on publisher/broker and connection health. | Depends on poll frequency and per-poll limits. |
| Network outage recovery | MQTT session/QoS and broker policy. | Source checkpoint/metadata and retry. |
| Business processing errors | Requires error flow, replay, idempotency. | Also requires error flow, replay, idempotency. |

If business requirements call for updates every 5 seconds, that does not mean you must use a poller to read MQTT. The device publisher can send on its own schedule while the MQTT inbound adapter still receives messages **via callbacks**.

## 7. MQTT metadata: topic, QoS, retained, and duplicate

When an MQTT message enters Spring Integration, **headers** can carry metadata for routing or replay checks. With Paho inbound, distinguish headers on a **received message** from headers used when the application **publishes** outbound messages.

| Metadata | Meaning | Usage |
| --- | --- | --- |
| Received topic | The specific topic received, even if subscribed via wildcard. | Route by device or telemetry type. |
| Received QoS | The QoS at which the MQTT client received the message. | Observe delivery policy; does not prove DB write. |
| Retained | Broker marked the message as retained. | Avoid mistaking an initial state snapshot for a new event. |
| Duplicate flag | MQTT protocol flag indicating possible redelivery. | Useful for observability, **not sufficient** for business deduplication. |
| Correlation/business ID | Application field carried in payload/header after parsing. | Idempotency, tracing, and reconciliation. |

A topic-based routing rule might dispatch:

~~~text
sensors/+/temperature  -> telemetry.temperature
sensors/+/humidity     -> telemetry.humidity
devices/+/state        -> telemetry.deviceState
~~~

If you want to parse the device name from the topic, validate the number of topic levels and allowed characters before using it as a tenant or database key. Do not trust a publisher-controlled topic string as proof that the publisher is authorized to send data for that tenant; authorization must be enforced via broker ACLs and the business layer.

### 7.1. Retained messages are not new events

Suppose the broker holds the most recent retained temperature payload for `sensors/room-17/temperature`. When the adapter starts and subscribes, the broker may deliver the retained message even when the sensor has not sent a new reading. If downstream logic increments event counters or triggers alerts on every receipt, inspect the retained flag and `eventId`/timestamp.

For **state snapshot** data, retained messages are often useful; for **one-time transaction/event** data, explicitly define whether retained messages are allowed.

### 7.2. The duplicate flag does not replace an idempotency key

A business event can appear multiple times due to publisher retries, dropped network acknowledgments, broker redelivery, or application restarts. You cannot deduplicate solely by checking the MQTT duplicate flag, because two independent publish calls can carry the same content without being flagged as protocol duplicates.

Better yet, include a unique `eventId` generated by the publisher in the telemetry payload; the target system stores processed state by `eventId` combined with device/tenant where appropriate.

## 8. Dynamic topic filters and subscription coordination

One adapter can subscribe to one or more topic filters. With the Paho adapter, the topic list is declared when creating the endpoint, and some versions support modifying subscriptions while the adapter is running.

Static configuration example:

~~~java
new MqttPahoMessageDrivenChannelAdapter(
        "telemetry-consumer-a",
        mqttClientFactory,
        "sensors/+/temperature",
        "sensors/+/humidity");
~~~

Both subscriptions send to the **same output channel** when using the same inbound adapter. Downstream flows can inspect the received topic to route to different pipelines.

If you subscribe to overlapping topic filters or broad wildcards, the broker may deliver more messages than expected. Do not treat topic filters as an authentication mechanism: publish/subscribe permissions must be restricted using ACLs, principals, and broker configuration.

### 8.1. Using a shared channel and router

~~~mermaid
flowchart TD
    B["MQTT broker"]
    A["Paho inbound adapter<br/>topics: sensors/+/temperature, sensors/+/humidity"]
    CH["mqtt.telemetry.in"]
    R{"Router by received topic"}
    T["telemetry.temperature"]
    H["telemetry.humidity"]
    ET["Temperature handler"]
    EH["Humidity handler"]
    B --> A --> CH --> R
    R -->|"*/temperature"| T --> ET
    R -->|"*/humidity"| H --> EH
~~~

If multiple topics carry **different payload schemas**, route **before or right when parsing** based on the topic, then choose the corresponding converter/validator. A default transformer receiving a `String` cannot distinguish `TemperatureReading` from `HumidityReading` without a routing rule.

## 9. Error handling when receiving MQTT messages

Errors can occur at multiple stages:

~~~mermaid
flowchart TD
    PUB["Publisher"]
    BROKER["Broker"]
    CLIENT["Paho / Inbound adapter"]
    FLOW["MessageChannel / IntegrationFlow"]
    DB["Database / outbound"]
    FAIL["Error flow / quarantine / retry"]
    PUB --> BROKER --> CLIENT --> FLOW --> DB
    CLIENT -. "disconnect / conversion error" .-> FAIL
    FLOW -. "schema / dispatch error" .-> FAIL
    DB -. "timeout / transaction failure" .-> FAIL
~~~

| Error category | Examples | Handling policy |
| --- | --- | --- |
| MQTT connection | Broker disconnect, DNS/TLS error, client ID conflict. | Recovery/reconnect, alerting, and downtime threshold checks. |
| Subscription | Unauthorized topic, invalid topic filter, broker rejection. | Fix ACL/config; do not retry infinitely on invalid config. |
| Converter/payload | Invalid bytes, malformed JSON schema, oversized payload. | Quarantine and report error with ID; do not treat as a broker outage. |
| Message channel | No consumer, slow downstream, or full queue. | Review topology, backpressure, and error flow. |
| Business handler | DB unavailable, HTTP timeout, validation failure. | Bounded retry, idempotency, compensation when needed. |
| Uncertain outcome | DB committed, but processing client disconnected before completion. | Reconcile by transaction/ID to prevent duplicates. |

### 9.1. A Spring error channel is not an MQTT dead-letter queue

Spring Integration can emit an `ErrorMessage` to an error channel at supported configured points. MQTT v3 does not provide a **standard dead-letter queue** the way some queue brokers do. If failed messages must be retained for reprocessing, the application must explicitly store them in a database, quarantine file, or publish them to a designated **error topic** with bounded retries and loop prevention.

Never feed failed messages endlessly back into the same source topic; distinguish retry count, recoverable errors, and non-recoverable schema errors.

### 9.2. Error paths and acknowledgements

MQTT protocol delivery acknowledgment is not equivalent to an integration flow successfully writing to a database. Depending on adapter mode, converter, channel, and version, the timing of MQTT acknowledgment may differ from business completion.

If you need to tie acknowledgment to processing, examine **manual acknowledgement** support in the adapter/Paho for your exact version and test actual disconnect/crash scenarios. Do not assume by default that throwing an exception in a handler will cause the broker to redeliver the message until the DB write succeeds.

## 10. Backpressure, threads, and channels

MQTT can deliver messages faster than a database or HTTP client can process them. The `MessageChannel` type connecting the adapter to downstream components strongly affects threading and overload risk.

| Channel | Typical behavior | Key considerations |
| --- | --- | --- |
| `DirectChannel` | Handler executes synchronously on the thread sending from the adapter to the channel. | Blocking handlers slow down callbacks/delivery; exceptions propagate up the call stack. |
| `ExecutorChannel` | Hands off to a thread pool. | Pool/queue bounds, rejection policy, error channel, and shutdown. |
| `QueueChannel` | Enqueues messages for a downstream endpoint to poll. | Capacity, poller, persistence, retry, and backlog. |
| `PublishSubscribeChannel` | Broadcasts to multiple consumers. | Single-branch errors, duplicate side effects, ordering. |

The demo uses `DirectChannel` because the handler only writes a small record into RAM. Do not replace `TelemetrySink` with an unbounded-timeout database/HTTP call while assuming the MQTT callback will be unaffected.

One way to decouple processing with bounds:

~~~mermaid
flowchart LR
    A["MQTT inbound adapter"]
    Q["telemetry.buffered<br/>QueueChannel(capacity=1000)"]
    P["Polling consumer<br/>maxMessagesPerPoll"]
    V["Validate / Transform"]
    H["DB / outbound handler"]
    A --> Q --> P --> V --> H
~~~

This is an **architectural decision**: if you use `QueueChannel`, you must provide a polling consumer and protection when the queue is full. The default in-memory queue is **not durable across restarts**. If you need reliable persistence before ack/destination writes, evaluate a persistent message store, broker pipeline, or outbox and verify it end-to-end.

### 10.1. Message ordering

MQTT provides ordering rules per connection/QoS, but the application can lose observed order when processing concurrently via executors, multiple instances, retries, or multiple topics. If sensor data depends on sequence, include a `sequenceNumber` or `eventTime` in the payload, then define how late-arriving/duplicate records are handled and what degree of ordering is required.

## 11. Lifecycle: start, stop, reconnect, and multi-instance deployment

`MqttPahoMessageDrivenChannelAdapter` is a Spring-managed endpoint. When the context initializes, the adapter can auto-start, open the MQTT connection, and subscribe to topics. When stopping, it must clean up/close resources properly and stop receiving new messages according to the framework/client lifecycle.

Scenarios to verify:

1. **Broker unavailable at startup:** adapter behavior on connection failure and recovery attempts.
2. **Network drop during runtime:** client reconnection, and whether subscriptions/sessions remain valid or must be re-established.
3. **Duplicate Client ID:** two instances logging in with the same ID causing mutual disconnects.
4. **Subscription changes:** impact of topic filter updates on load and whether data can be missed.
5. **Shutdown:** how in-flight messages, internal queues, thread resources, and connections are released.
6. **Client/broker version upgrades:** MQTT protocol compatibility, TLS, retained messages, and session persistence.

### 11.1. Clean session and offline data

With MQTT 3.1.1, if the broker needs to retain subscriptions and certain QoS 1/2 messages while a client is temporarily offline, you usually need a **stable Client ID** and `cleanSession=false` along with broker support/configuration. This does not mean the broker stores messages indefinitely or that data cannot be lost if the broker's disk fills up.

When scaling horizontally with multiple independent instances, each instance must have an appropriate identity and subscription model. Do not use the same Client ID as an automatic load-balancing mechanism. If the broker supports **shared subscriptions**, verify the exact syntax and semantics for your broker/protocol version; this is not the default behavior of regular topic subscriptions.

### 11.2. Monitoring the adapter

Track at least:

- Connection status and reconnect count.
- Messages received per topic/QoS, and latency from `eventTime` to processing time.
- Converter, validation, dispatch, and handler errors grouped by category.
- Queue depth, processing duration, and retry/quarantine counts.
- Duplicate message count by `eventId`; retained messages and late events.
- Silence duration for devices expected to emit a heartbeat.

Do not log raw payloads containing sensitive data or secrets from headers. Use correlation IDs, validated topics, and device IDs for tracing when needed.

## 12. MQTT inbound security

MQTT often carries data from devices in untrusted environments. Adapter design should account for:

| Risk | Mitigation |
| --- | --- |
| Unencrypted MQTT connection | Use TLS (`ssl://...` or appropriate connection settings) and verify the broker certificate. |
| Exposed credentials | Load via secret manager/env; never hardcode or log passwords. |
| Unauthorized subscriptions | Enforce topic ACLs on the broker per principal/client; subscribe to the minimum necessary. |
| Publisher spoofing topic/device ID | Authenticate publishers at the broker, bind topic permissions, and validate device ID in payload. |
| Malicious/oversized payload | Enforce size limits, validate JSON/schema, bound parse times. |
| Duplicate or replayed messages | `eventId`, timestamp, target deduplication, and freshness checks if required by business logic. |
| Consumer overload | Capacity/backpressure, monitoring, concurrency limits, and explicit drop/retain policies. |

Do not rely on `MqttHeaders.RECEIVED_TOPIC` as the sole proof that a publisher is authorized. The topic is protocol metadata; authentication and authorization must be enforced at the broker and application layers according to your trust model.

## 13. Testing the flow without an MQTT broker

Most logic after the adapter should be tested independently of a broker. Because `TelemetryFlowConfiguration` in section 5 only declares the channel and downstream handler, we can start a dedicated **Spring Integration test context** with just that class, without loading `MqttTransportConfiguration`. That way, tests make no network connection attempts.

Add the dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Create `TelemetryFlowTest.java` in package `demo.mqtt`:

~~~java
package demo.mqtt;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.mqtt.support.MqttHeaders;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = TelemetryFlowConfiguration.class)
class TelemetryFlowTest {

    @Autowired
    @Qualifier("mqtt.telemetry.in")
    MessageChannel input;

    @Autowired
    TelemetrySink sink;

    @BeforeEach
    void reset() {
        sink.clear();
    }

    @Test
    void routesReceivedPayloadAndTopicToSink() {
        String json = "{\"deviceId\":\"room-17\",\"celsius\":26.5}";

        boolean sent = input.send(
                MessageBuilder.withPayload(json)
                        .setHeader(MqttHeaders.RECEIVED_TOPIC,
                                "sensors/room-17/temperature")
                        .build());

        assertTrue(sent);
        assertEquals(
                List.of(new ReceivedTelemetry(
                        "sensors/room-17/temperature", json)),
                sink.snapshot());
    }
}
~~~

This test verifies:

- The `mqtt.telemetry.in` bean exists and has a consumer.
- `IntegrationFlow` receives a message containing a `String` payload.
- The topic header is passed into `TelemetrySink`.
- Synchronous processing through `DirectChannel` finishes before the assertions run.

**Limitation:** this test does not verify Paho client connection, subscription, QoS, retained flags, reconnection, or duplicate handling from the broker. To verify those behaviors, you need an **integration test with a real broker** (local container/test environment) and an independent publisher.

## 14. Testing with a test MQTT broker

When a suitable local broker is configured for the test environment, you can use the `mosquitto_pub` CLI to publish a message:

~~~bash
mosquitto_pub -h localhost -p 1883 \
  -t 'sensors/room-17/temperature' \
  -q 1 \
  -m '{"deviceId":"room-17","celsius":26.5,"eventId":"evt-1001"}'
~~~

This command only works if:

- An MQTT broker is running on `localhost:1883` and permits the test client connection.
- The application uses the matching broker URL, Client ID, and topic filter.
- The `mosquitto_pub` CLI is installed.
- If the broker requires username/password/TLS, the command and application configuration are updated accordingly; do not disable production broker security to run a demo.

Observe the log `MQTT received: sensors/room-17/temperature`. Change the topic to `sensors/room-17/humidity`: if the adapter only subscribes to `sensors/+/temperature`, it will not receive the humidity message.

### 14.1. Required tests for end-to-end verification

| Test case | How to perform | Expected observation |
| --- | --- | --- |
| Matching topic | Publish to `sensors/room-17/temperature`. | Inbound receives the expected payload/topic. |
| Non-matching topic | Publish to `sensors/room-17/humidity`. | The temperature subscription does not receive it. |
| QoS 1 / duplicate | Send or simulate redelivery with the same `eventId`. | Target handler produces no duplicate side effects. |
| Retained | Publish retained, restart subscriber/re-subscribe. | Identified as a state snapshot, not miscounted as a new event. |
| Broker disconnect | Drop connection, wait for recovery, reconnect. | Connection/subscription recovers per policy; do not claim zero data loss without proof. |
| App restart | Keep/change Client ID and clean session per scenario. | Verify session/QoS and offline data per broker policy. |
| Downstream error | Have handler throw an exception or make DB unavailable. | Error flow/retry is observed; messages are not silently dropped. |
| High throughput | Publish faster than the handler's throughput. | Backpressure/queue limits and metrics engage; resources are not exhausted. |

Do not merely check a "received" log and declare success: verify the final state in the database or target system whenever the integration flow has real side effects.

## 15. Common pitfalls

| Symptom | Common cause | How to investigate |
| --- | --- | --- |
| Not receiving MQTT messages. | Wrong broker URL, topic filter mismatch, ACL denies subscribe, client not started. | Check connectivity, broker logs, subscriptions, and lifecycle. |
| Two instances repeatedly disconnect. | The same Client ID is being shared. | Assign a unique Client ID to each active client. |
| Re-receiving messages after reconnect. | QoS/redelivery, persistent session, or retained message. | Inspect topic/QoS/retained headers, add idempotency by `eventId`. |
| Messages never reach the handler. | Adapter sends to the wrong channel or channel has no consumer. | Verify `setOutputChannel(...)` and `IntegrationFlow.from(...)`. |
| Invalid JSON still logs `MQTT received`. | Handler currently accepts raw text without JSON parsing/validation. | Add a JSON transformer and validation/quarantine. |
| MQTT errors cleared, but DB has no data. | Protocol delivery acknowledgment differs from business completion. | Check transaction/retry in handler and target system state. |
| Slow MQTT callback causes broker disconnect. | Blocking downstream calls, missing timeouts, overload. | Bound handler latency or decouple with a backpressure-aware queue/executor. |
| Business duplicates still occur with QoS 2. | Publisher emits duplicate events or side-effect retries occur. | Use a stable `eventId`, unique constraint/idempotency. |
| Messages lost after restart. | In-memory queue, non-persistent session, or broker dropped data. | Check clean session, Client ID, QoS, and persistent storage. |
| Old retained payload received. | Broker delivers retained message upon subscribing. | Inspect retained flag/event timestamp and define snapshot handling policy. |
| Spring has an error channel, but no MQTT DLQ. | MQTT v3 does not provide a default application DLQ. | Design an error/quarantine topic or durable store and replay mechanism. |

## 16. Practice exercise

**Scenario:** a system ingests temperature telemetry from multiple MQTT devices. Devices publish to `sensors/<deviceId>/temperature` with JSON payload:

~~~json
{
  "eventId": "evt-1001",
  "deviceId": "room-17",
  "celsius": 26.5,
  "eventTime": "2026-11-23T01:00:00Z"
}
~~~

Requirements:

1. Configure `MqttPahoClientFactory` from environment variables, using a test broker with proper authentication and a stable Client ID.
2. Create an `MqttPahoMessageDrivenChannelAdapter` subscribing to `sensors/+/temperature` at QoS 1 with output channel `mqtt.telemetry.in`.
3. Parse the JSON payload into a `TemperatureReading` DTO and validate `eventId`, `deviceId`, temperature unit, and timestamp.
4. Cross-check the device ID in the payload against the received topic and device permissions according to the design.
5. Forward valid messages to `telemetry.validated` and persist them to the database via a service activator.
6. Design idempotency by `eventId` so retries or duplicates do not write twice.
7. Distinguish retained messages, new messages, and late-arriving messages by `eventTime`.
8. Store schema-invalid messages in quarantine; handle DB connection failures with bounded retries and a reconciliation mechanism.
9. Write a brokerless unit/integration test for the channel/transformer/validator, and an end-to-end test with a broker for subscribe/reconnect/QoS.
10. Explain why `@Poller` is not needed to receive message-driven MQTT messages, yet may appear at a downstream `QueueChannel` stage.

**Completion criteria:** the application subscribes to the right wildcard topic, preserves required metadata, processes valid messages to the DB, records traceable errors, avoids duplicate side effects, and clearly distinguishes MQTT delivery time from business completion time.

## 17. Quick self-check

1. Does an MQTT message-driven adapter receive data via a broker callback or via `MessageSource.receive()` on a poller?
2. What does `MqttPahoMessageDrivenChannelAdapter` need to connect to a broker and subscribe?
3. How does `sensors/+/temperature` differ from `sensors/#`?
4. Does `setQos(1)` force publishers to send at QoS 1?
5. Why does MQTT QoS 2 not guarantee that a database is written only once?
6. If two instances share the same Client ID, what risk can occur?
7. Why does `cleanSession=false` not replace checkpoints/outbox in the application?
8. Is a retained message necessarily a new event?
9. What is the received topic header used for in a flow?
10. Why should you avoid making long blocking HTTP API calls directly on a callback path using `DirectChannel`?
11. When switching to a `QueueChannel`, which component needs a poller?
12. Why does testing `MessageChannel.send(...)` alone not prove real subscribe/reconnect behavior?
13. How can you turn a Spring `errorChannel` into a safe replay mechanism?
14. If a publisher emits duplicate events without a duplicate flag, how should you handle them?

**Hint:** MQTT inbound receives via Paho/broker events; QoS is a protocol delivery mechanism, not a business transaction; Client ID/session govern connectivity and offline messages; payloads/headers must be validated; idempotency, retries, and monitoring are designed at each boundary.

## 18. Conclusion

The **MQTT inbound message-driven adapter** connects Spring Integration to a publish–subscribe system without polling a source. `MqttPahoMessageDrivenChannelAdapter` subscribes to topic filters via `MqttPahoClientFactory`, receives broker-delivered messages, passes them through a converter, and emits them to a `MessageChannel`. From there, an `IntegrationFlow` can validate, transform, route, write to a database, or forward data to HTTP/JMS/Kafka.

When designing MQTT within the **SPRING_INTEGRATION_ADAPTERS** module, clearly distinguish **broker delivery from business completion**, **topic wildcards from access permissions**, **QoS/retained/session from business deduplication**, and **synchronous channels from queues/executors**. An inbound adapter is only truly reliable when backed by secure connection settings, retry/error paths, idempotency, and end-to-end tests matching your broker and target system characteristics.
