# Automatic reconnect and completion timeout

## 1. Context: MQTT connections are not always stable

A Spring Integration application may send device control commands via MQTT, receive telemetry from a broker, and forward data to databases, HTTP, JMS, Kafka, or other systems. When a broker restarts, the network drops, a certificate expires, or downstream overloads, two questions immediately arise:

1. **How does the MQTT client recover its connection without restarting the entire application?**
2. **How long is a connect, subscribe, or publish operation allowed to wait before returning an error/timeout?**

That is the scope of **automatic reconnect** and **completion timeout**. They are related, yet they are not two names for the same mechanism:

- **Automatic reconnect** allows the client to attempt re-establishing a connection when an MQTT connection is lost.
- **Completion timeout** bounds how long to wait for an operation performed by the endpoint/client to finish; a publish operation timing out does not mean the broker definitely never received the message.

This lesson sits in the **Adapter MQTT** chapter of the **SPRING_INTEGRATION_ADAPTERS** module. The module focuses on integrating external systems via inbound/outbound adapters, gateways, pollers, and `MessageChannel`, with examples for files, SFTP, HTTP, JMS, AMQP, Kafka, and databases; it also requires managing message contracts, errors, and connection lifecycles. With MQTT, Spring Integration uses an MQTT client to connect to the broker, then transfers payloads/headers into or out of an `IntegrationFlow`.

After this lesson, learners will be able to:

- Distinguish Eclipse Paho's `MqttConnectOptions.setAutomaticReconnect(true)` from the inbound adapter's `setRecoveryInterval(...)`.
- Distinguish **connection timeout**, **keepalive interval**, **completion timeout**, **recovery interval**, and **business ACK timeout**.
- Configure inbound/outbound MQTT adapters with suitable factories and Client IDs.
- Explain failures including **initial connection loss**, **network drop mid-publish**, **client reconnected yet session gone**, and **publish completion timeout**.
- Design replay, idempotency, backpressure, and uncertain-publish states.
- Test configuration and flows without a broker; test live against a broker that is disconnected, slow, rejecting authentication, or restarting.
- Monitor connectivity, publish latency, reconnect errors, queue backlog, and application state.

**Limitation:** examples use Spring Integration MQTT with the Eclipse Paho **MQTT v3 API**, `MqttConnectOptions`, and MQTT 3.1.1. Callback, event, and recovery behavior when enabling multiple mechanisms simultaneously can vary across Spring Integration/Paho versions; test on your project's versions rather than generalizing a single example into a guarantee for all systems.

## 2. Where reconnect and timeout sit in the architecture

~~~mermaid
flowchart LR
    SRC["Business service / inbound adapters"]
    OUT["mqtt.commands.out<br/>MessageChannel"]
    HANDLER["MqttPahoMessageHandler<br/>outbound"]
    CLIENT["Paho MQTT client<br/>connect / publish / reconnect"]
    BROKER[("MQTT broker")]
    SUB["Subscriber / device"]
    IN["MqttPahoMessageDrivenChannelAdapter<br/>inbound"]
    CH["mqtt.telemetry.in<br/>MessageChannel"]
    FLOW["Validation / database flow"]
    SRC --> OUT --> HANDLER --> CLIENT
    CLIENT -->|"PUBLISH QoS + topic"| BROKER --> SUB
    BROKER -->|"DELIVER"| IN --> CH --> FLOW
    CLIENT -. "connection lost" .-> CLIENT
    IN -. "endpoint recovery" .-> IN
~~~

A message from a business system crosses multiple boundaries, and a timeout at each boundary has a distinct meaning:

| Boundary | Controlling component | Question to answer |
| --- | --- | --- |
| Opening TCP/TLS/MQTT connection | Paho `MqttConnectOptions` | Did the client establish a connection within the allotted time? |
| Maintaining connection | MQTT keepalive, client network, and broker | Without application traffic, can both sides still detect a dead connection? |
| Disconnect and recovery | Paho automatic reconnect and/or adapter recovery | Who initiates reconnection? When is the next attempt? |
| Subscribe or publish | Paho token, adapter completion timeout | Did the operation finish within the wait limit? |
| Handoff to Spring channel | `DirectChannel`/`QueueChannel`/`ExecutorChannel` | Was the message received by a consumer, queued, or rejected? |
| Target side effect | Database transaction, HTTP/JMS/Kafka handler | Did business processing finish or merely start? |
| Device response | ACK topic and business correlation | Which command did the device execute, with what outcome, and when? |

**Never call `completionTimeout=5000` "the maximum 5 seconds the broker is allowed to be offline."** It bounds waiting on one specific operation; it does not force the broker to recover within that window.

## 3. Distinguishing five common time parameters

| Parameter | API/config example | Unit | Primary meaning |
| --- | --- | --- | --- |
| **Connection timeout** | `MqttConnectOptions.setConnectionTimeout(10)` | Seconds | Maximum time allowed to establish a connection in Paho. |
| **Keepalive interval** | `MqttConnectOptions.setKeepAliveInterval(30)` | Seconds | MQTT activity interval used to detect an unresponsive connection at the protocol layer. |
| **Recovery interval** | `MqttPahoMessageDrivenChannelAdapter.setRecoveryInterval(10000)` | Milliseconds | Inbound endpoint recovery/retry interval per Spring Integration API. |
| **Completion timeout** | `MqttPahoMessageHandler.setCompletionTimeout(5000)` | Milliseconds | Wait limit for synchronous publish completion in the outbound handler. |
| **Business ACK timeout** | Application-defined, e.g., 30 seconds | Per contract | Time to wait for a subscriber to confirm business command execution. |

The two lines most often confused:

~~~java
options.setConnectionTimeout(10);   // 10 SECONDS
handler.setCompletionTimeout(5000);  // 5000 MILLISECONDS = 5 seconds
~~~

When configuring, also keep in mind:

- `connectionTimeout` is not a timeout for an HTTP request or for Spring's `MessageChannel.send(...)`.
- `keepAliveInterval` is a **connection** signal, not a business sensor heartbeat.
- `recoveryInterval` controls how the endpoint schedules recovery attempts; it does not say where messages are located.
- `completionTimeout` does not provide exactly-once semantics and does not guarantee receiver processing.
- Business ACK timeouts can be much longer and independent of MQTT publish timeouts.

## 4. Eclipse Paho automatic reconnect

Eclipse Paho MQTT v3 provides the option:

~~~java
MqttConnectOptions options = new MqttConnectOptions();
options.setServerURIs(new String[] {
        "tcp://localhost:1883"
});
options.setConnectionTimeout(10);
options.setKeepAliveInterval(30);
options.setAutomaticReconnect(true);
~~~

When a client **was already connected and unexpectedly loses the connection**, Paho can automatically try reconnecting using the library's internal backoff/monitoring logic. The application does not need to write its own `connect()` loop for a client whose automatic reconnect is managed by Paho.

### 4.1. What does automatic reconnect help with?

- Recovering from transient network interruptions or broker restarts under library-supported conditions.
- Reducing the need to write manual reconnect loops in business code.
- Combining with multiple broker URIs to try suitable endpoints per client capabilities and broker topology.
- Allowing adapters to resume work once the client recovers and required subscriptions/sessions remain valid.

### 4.2. What does automatic reconnect NOT guarantee?

1. **Does not automatically handle all initial connection failures.** If the client has never connected successfully, the application still must consider endpoint startup/retry policies. Automatic reconnect mainly targets *connection lost* after an established connection.
2. **Cannot fix wrong credentials or denied ACLs.** Repeating CONNECT with an invalid password is not a self-healing strategy.
3. **Does not automatically buffer all outbound messages while the broker is offline.** Buffering/offline queuing requires dedicated configuration and bounds, plus restart durability planning.
4. **Does not guarantee a subscriber still has its previous subscriptions** if the session was purged, Client ID changed, or brokers do not share sessions on failover.
5. **Does not roll back downstream side effects** if a DB already committed, HTTP succeeded, or a device already executed a command.
6. **Does not turn MQTT QoS 1 into business exactly-once.** Messages can be redelivered or publishers can emit a new event with the same meaning.

### 4.3. Reconnect is a state machine, not a one-shot call

~~~mermaid
stateDiagram-v2
    [*] --> Configured
    Configured --> Connecting: Initialize client
    Connecting --> Connected: MQTT CONNECT succeeded
    Connecting --> ConnectFailed: Timeout / ACL / DNS / TLS
    Connected --> ConnectionLost: Network or broker drop
    ConnectionLost --> Reconnecting: Recovery policy enabled
    Reconnecting --> Connected: Reconnect succeeded
    Reconnecting --> Reconnecting: Failed / retry backoff
    Reconnecting --> Stopped: Endpoint stopped
    Connected --> Stopped: Intentional shutdown
    ConnectFailed --> Stopped: Policy stops startup
~~~

This diagram shows **logical states**. Spring Integration and Paho do not necessarily emit events with these exact names. In implementation, logs and metrics must show: connecting, disconnected, retrying, recovered, or intentionally stopped.

### 4.4. Disconnections can disrupt both inbound and outbound

In an application using two MQTT clients, publisher and subscriber usually have **different Client IDs**. They can reconnect at different times even when sharing a broker. A successful outbound PUBLISH on client A does not prove inbound client B has finished re-subscribing or is online.

If the application switches broker URIs after failover, verify whether the cluster synchronizes subscriptions, sessions, retained state, and in-flight messages. **`setServerURIs(...)` is not replication or publishing to all brokers.**

## 5. Recovery interval on the Spring Integration inbound adapter

Spring Integration provides `MqttPahoMessageDrivenChannelAdapter` to subscribe to topics and emit MQTT messages onto a channel. Supported versions provide the recovery interval API:

~~~java
var adapter = new MqttPahoMessageDrivenChannelAdapter(
        "telemetry-subscriber-1",
        mqttClientFactory,
        "sensors/+/temperature");

adapter.setQos(1);
adapter.setRecoveryInterval(10000);
adapter.setOutputChannel(mqttTelemetryInput);
~~~

`setRecoveryInterval(10000)` expresses an endpoint-level recovery interval in **milliseconds**. It is not a poller reading the broker periodically. The MQTT inbound adapter remains **message-driven**: when the client receives a PUBLISH via callback, the adapter emits a Spring message.

### 5.1. Adapter recovery vs. Paho automatic reconnect

| Mechanism | Where configured | Goal | What to verify |
| --- | --- | --- | --- |
| Paho `setAutomaticReconnect(true)` | `MqttConnectOptions`. | MQTT client automatically attempts to reconnect when connection is lost. | Callback behavior, subscriptions/sessions after reconnect, initial startup phase. |
| Spring `setRecoveryInterval(...)` | `MqttPahoMessageDrivenChannelAdapter`. | Throttles when the endpoint handles/recovers from connection errors per version mechanics. | Whether it is invoked in specific scenarios when Paho auto-reconnect is also enabled. |
| Business handler retry | Advice/error flow/outbox. | Retries failed business processing or publishing. | Idempotency, source state, non-retryable data errors. |

These sit at **different layers**, yet both can touch the connection lifecycle if enabled together. Do not assume "turning both on makes reconnect twice as fast." With real Spring Integration/Paho, pick a clear policy and test interactions on your deployed framework version.

### 5.2. Example separating the two policies for clarity

An easily observable setup in a demo environment:

- **Subscriber:** set `automaticReconnect=false` on Paho options and let the inbound adapter manage recovery via `recoveryInterval`.
- **Publisher:** use a second factory with `automaticReconnect=true` so Paho attempts to recover an active connection after a drop.
- **Each client** has its own Client ID and session settings.

This is a **way to illustrate responsibility boundaries**, not a rule that every Spring Integration version must use this exact setup. Across versions, the framework may manage reconnection/subscriptions differently; test disconnections and read your exact API's behavior before choosing a production policy.

## 6. Completion timeout on the MQTT outbound handler

In Spring Integration, the outbound MQTT adapter is typically implemented with `MqttPahoMessageHandler`:

~~~java
MqttPahoMessageHandler handler =
        new MqttPahoMessageHandler(
                "commands-publisher-1", clientFactory);

handler.setDefaultTopic("devices/default/commands");
handler.setDefaultQos(1);
handler.setDefaultRetained(false);
handler.setAsync(false);
handler.setCompletionTimeout(5000);
~~~

For **synchronous publishing** (`setAsync(false)`), the handler can wait up to a limit for the Paho publish token to complete. `setCompletionTimeout(5000)` bounds that wait in milliseconds.

### 6.1. What does completion timeout actually state?

When a publish exceeds the wait limit:

- The caller/endpoint may receive a timeout/exception depending on the API and wrapping layers.
- The publication state may be **uncertain**: the broker might not have received it, might be processing it, or **might have received it while the ACK arrived late or was lost**.
- Immediately re-sending with a brand-new message/command risks the subscriber executing it twice.
- A timeout **does not automatically cancel a publication already received by the broker**.

Example:

~~~mermaid
sequenceDiagram
    participant APP as Spring handler
    participant CLIENT as Paho client
    participant BROKER as MQTT broker
    APP->>CLIENT: publish(cmd-1001, QoS=1)
    CLIENT->>BROKER: PUBLISH(cmd-1001)
    BROKER--xCLIENT: PUBACK lost or severely delayed
    CLIENT-->>APP: Completion timeout
    Note over APP,BROKER: Broker may have already received cmd-1001
    APP->>APP: Mark outcome uncertain
~~~

In this situation, a timeout error is not safe grounds to create another command with a new ID. Keep `commandId`/`eventId` stable and implement idempotency, an outbox, reconciliation, or a dedicated business ACK.

### 6.2. Completion timeout vs. connection timeout

~~~java
MqttConnectOptions options = new MqttConnectOptions();
options.setConnectionTimeout(10); // Seconds: opening connection

MqttPahoMessageHandler handler =
        new MqttPahoMessageHandler("publisher-1", clientFactory);
handler.setCompletionTimeout(5000); // Milliseconds: waiting for publish
~~~

If DNS or the TLS handshake does not finish, you are investigating **connection establishment**. If a connection already exists and a QoS 1 PUBLISH waits too long for PUBACK, you are investigating **publish completion**. The same network outage can produce both symptoms, yet their metrics and recovery steps differ.

### 6.3. QoS 0/1/2 give completion different meanings

| QoS | Primary handshake | Expectation while waiting on publish token | What still cannot be inferred |
| --- | --- | --- | --- |
| 0 | No QoS 1/2 PUBACK. | Completes at client/protocol level without a separate QoS 1 broker ACK. | That the subscriber received the payload. |
| 1 | `PUBLISH → PUBACK`. | Operation can wait for QoS 1 acknowledgment. | That the subscriber processed/committed DB. |
| 2 | `PUBLISH → PUBREC → PUBREL → PUBCOMP`. | Operation tracks the QoS 2 handshake. | Exactly-once application side effects. |

**Note:** how Paho tokens signal completion per QoS and how the handler waits depend on API/version; when designing SLAs, verify with broker tests rather than inferring subscriber ACK timing from general descriptions.

## 7. Async publish: completion timeout does not mean the same thing as sync

The outbound handler can be switched to asynchronous mode:

~~~java
handler.setAsync(true);
handler.setAsyncEvents(true);
~~~

In async mode, the handler can return **before the broker completes acknowledgment**, and delayed failures must be tracked via callbacks/application events or version-supported APIs. `setCompletionTimeout(...)` should not be viewed as "a synchronous call timeout waiting on the broker" across operations once async is enabled.

| Criterion | `setAsync(false)` | `setAsync(true)` |
| --- | --- | --- |
| Caller after `DirectChannel.send(...)` | May wait for publish token completion. | Typically returns earlier. |
| Delayed errors | Many errors surface on the same call stack. | May arrive on callbacks/events/separate error handling. |
| Completion timeout | Critical for synchronous publish wait bounds. | Must understand exact async handler and completion-event behavior. |
| Persistence guarantee | Not automatic. | Not automatic. |
| Device processed MQTT publish | Cannot be inferred. | Cannot be inferred. |

**Wrong pattern:** call `channel.send(message)`, receive `true`, and immediately mark the database `DEVICE_COMPLETED`. With async publishing, that result may only mean send handoff; even if the MQTT publish succeeded, the device may not have executed the command yet.

To know **when a publication completed**, track publish outcomes by `eventId` using version-appropriate APIs/application events. Simulate network failures after `send()` returns and verify outbox state updates accurately.

## 8. Why you should not blindly retry on timeout or reconnect

Suppose the application handles command `cmd-1001` as follows:

~~~text
T0: Spring creates event cmd-1001
T1: MQTT publisher sends PUBLISH QoS 1
T2: Broker receives cmd-1001
T3: Network drops before PUBACK
T4: Handler reports completion timeout
T5: Application retries with a new PUBLISH
T6: Device receives cmd-1001 again
~~~

In some situations, the client/protocol already retries unacknowledged publications while **the application** also retries. Without coordination, two retry layers produce duplicates.

### 8.1. Three outcome states to distinguish

| State | Meaning | Action to take |
| --- | --- | --- |
| `PUBLISH_NOT_ATTEMPTED` | Publishing never started per application evidence. | Can attempt per outbox policy. |
| `PUBLISH_CONFIRMED` | Completed per observed MQTT publish signal. | Mark sent at MQTT layer; await business ACK if needed. |
| `PUBLISH_UNCERTAIN` | Timeout, disconnect, unclear callback, or crash before state update. | Do not assume broker missed it; retry with the **same event ID**, enforce dedup/reconciliation. |

These names are **illustrative business states**, not built-in Spring Integration enums. Use them to separate durable records from technical callbacks.

### 8.2. Separating retries at the right layer

1. **MQTT client reconnect:** restores the connection between client and broker.
2. **MQTT QoS retransmission:** recovers unacknowledged packets within protocol bounds.
3. **Outbox publish retry:** handles application events not yet confirmed published or in uncertain state.
4. **Subscriber processing retry:** handles downstream DB/HTTP failures after receiving MQTT.
5. **Business command retry:** re-issues a business request when the device ACK does not arrive.

Never mix all these layers into an unbounded `while(true)` loop. Each layer has its own stop conditions, backoff, idempotency, metrics, and error classes.

## 9. Connections and sessions after reconnect

A successful reconnect does not automatically prove message flow has fully recovered. Evaluate **Client ID**, **clean session**, **subscription QoS**, and broker state.

### 9.1. MQTT 3.1.1 clean session

- `cleanSession=true`: on reconnect, the old session is not kept as a persistent session; the subscriber usually must re-subscribe.
- `cleanSession=false`: the broker can restore the session/subscriptions and QoS 1/2 messages queued while offline if the Client ID is stable and the broker supports it.
- Retained snapshots are topic-level broker data, **not** the full history of a persistent session.
- A Client ID changing on restart prevents the old session/subscriptions from resuming under the new ID.

### 9.2. Never share a Client ID to scale horizontally

If two application instances both use `telemetry-subscriber-1`, the broker can disconnect the older client whenever the newer client sends CONNECT. The two clients will continuously kick each other off. This looks like a "reconnect loop," yet the root cause is **duplicate Client ID configuration**, not a timeout needing a larger number.

Proper patterns to consider:

| Goal | Approach | Notes |
| --- | --- | --- |
| Single logical consumer with persistent session | Stable Client ID; only one active client with that ID. | Failover must manage active ownership. |
| Multiple independent subscribers receiving the same events | Distinct Client ID per instance. | Each instance has its own independent session/subscriptions. |
| Load-sharing among subscribers | Shared subscriptions if broker/protocol supports it, or an appropriate broker queue. | Never simulate competing consumers via duplicate Client IDs. |
| Publishing from multiple instances | Distinct publisher Client IDs, outbox claim/partitioning. | Prevent multiple instances from publishing the same business event twice. |

### 9.3. Topic subscriptions can be lost after failover

Two broker URIs do not imply two brokers share sessions or retained messages. A client reconnecting to another independent broker may need to re-subscribe and may miss messages stored by the first broker while offline. For HA, test the actual broker cluster: session replication, subscription state, in-flight messages, retained state, and quotas.

## 10. Working example: inbound recovery and outbound completion timeout

The following Spring Boot example illustrates **two factories** to separate subscriber and publisher policies:

- Inbound subscriber uses `automaticReconnect=false` and adapter `recoveryInterval=10000 ms` to observe endpoint-level recovery.
- Outbound publisher uses `automaticReconnect=true` and handler `completionTimeout=5000 ms`, `async=false`.
- The two MQTT clients use **separate Client IDs**.
- Two integration flows separate inbound telemetry from outbound commands.

This configuration is **deliberately chosen for learning**, not a fixed rule for every version. Before production, test both initial connection failures and mid-run disconnects, and verify adapter/Paho interactions.

### 10.1. Dependencies

Use Java 17+ and compatible Spring Boot/Spring Integration versions:

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

Let the Spring Boot BOM manage Spring Integration/Paho versions. Examples use the Eclipse Paho MQTT v3 API (`org.eclipse.paho.client.mqttv3.MqttConnectOptions`); MQTT v5 clients/options differ and require adapting the examples.

### 10.2. Example structure

~~~text
src/main/java/demo/mqttrecovery/
    MqttRecoveryApplication.java
    MqttClientConfiguration.java
    MqttEndpointConfiguration.java
    CommandPublisher.java

src/main/resources/
    application.properties

src/test/java/demo/mqttrecovery/
    MqttClientConfigurationTest.java
    CommandFlowTest.java
~~~

Place each Java class with a `public` modifier into a file matching its name. The code below primarily uses package-private classes to focus on configuration.

### 10.3. application.properties

~~~properties
app.mqtt.broker-url=${MQTT_BROKER_URL:tcp://localhost:1883}
app.mqtt.subscriber-id=${MQTT_SUBSCRIBER_ID:telemetry-in-local-1}
app.mqtt.publisher-id=${MQTT_PUBLISHER_ID:commands-out-local-1}
~~~

These values are only for local testing. The application **does not start a broker**. In production, the URL should be an appropriate TLS URI; username/password, truststore/certificates, ACLs, and Client IDs are managed via deployment/secrets. The two Client IDs must be **distinct and unique across active instances**.

### 10.4. Spring Boot application

~~~java
package demo.mqttrecovery;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MqttRecoveryApplication {
    public static void main(String[] args) {
        SpringApplication.run(MqttRecoveryApplication.class, args);
    }
}
~~~

### 10.5. Two separate sets of connection options

~~~java
package demo.mqttrecovery;

import org.eclipse.paho.client.mqttv3.MqttConnectOptions;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.mqtt.core.DefaultMqttPahoClientFactory;
import org.springframework.integration.mqtt.core.MqttPahoClientFactory;

@Configuration
class MqttClientConfiguration {

    @Bean(name = "subscriberOptions")
    MqttConnectOptions subscriberOptions(
            @Value("${app.mqtt.broker-url}") String brokerUrl) {

        var options = connectionOptions(brokerUrl);
        options.setAutomaticReconnect(false);
        options.setCleanSession(false); // retain session per broker policy
        return options;
    }

    @Bean(name = "publisherOptions")
    MqttConnectOptions publisherOptions(
            @Value("${app.mqtt.broker-url}") String brokerUrl) {

        var options = connectionOptions(brokerUrl);
        options.setAutomaticReconnect(true);
        options.setCleanSession(true);
        return options;
    }

    private static MqttConnectOptions connectionOptions(String brokerUrl) {
        var options = new MqttConnectOptions();
        options.setServerURIs(new String[] {brokerUrl});
        options.setConnectionTimeout(10); // seconds
        options.setKeepAliveInterval(30); // seconds
        return options;
    }

    @Bean(name = "subscriberFactory")
    MqttPahoClientFactory subscriberFactory(
            @Qualifier("subscriberOptions") MqttConnectOptions options) {
        return newFactory(options);
    }

    @Bean(name = "publisherFactory")
    MqttPahoClientFactory publisherFactory(
            @Qualifier("publisherOptions") MqttConnectOptions options) {
        return newFactory(options);
    }

    private static MqttPahoClientFactory newFactory(
            MqttConnectOptions options) {

        var factory = new DefaultMqttPahoClientFactory();
        factory.setConnectionOptions(options);
        return factory;
    }
}
~~~

**Design intent:** `subscriberOptions` and `publisherOptions` are two `MqttConnectOptions` beans with different policies. Each factory is built from the right options via `@Qualifier`; never let injection pick arbitrarily when two beans of the same type exist in the context.

Note that `options.setAutomaticReconnect(true)` does not directly define how long the application waits when the broker is offline. Paho has its own retry policy; Spring endpoint startup, threads, and initial connect failures still need testing.

### 10.6. Inbound adapter and outbound handler

~~~java
package demo.mqttrecovery;

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

    @Bean(name = "mqtt.telemetry.in")
    MessageChannel telemetryInput() {
        return new DirectChannel();
    }

    @Bean(name = "mqtt.commands.out")
    MessageChannel commandOutput() {
        return new DirectChannel();
    }

    @Bean
    MqttPahoMessageDrivenChannelAdapter telemetryAdapter(
            @Qualifier("subscriberFactory") MqttPahoClientFactory factory,
            @Qualifier("mqtt.telemetry.in") MessageChannel output,
            @Value("${app.mqtt.subscriber-id}") String clientId) {

        var adapter = new MqttPahoMessageDrivenChannelAdapter(
                clientId, factory, "sensors/+/temperature");

        adapter.setQos(1);
        adapter.setRecoveryInterval(10000); // milliseconds
        adapter.setConverter(new DefaultPahoMessageConverter());
        adapter.setOutputChannel(output);
        return adapter;
    }

    @Bean(name = "mqttPublisher")
    MqttPahoMessageHandler mqttPublisher(
            @Qualifier("publisherFactory") MqttPahoClientFactory factory,
            @Value("${app.mqtt.publisher-id}") String clientId) {

        var handler = new MqttPahoMessageHandler(clientId, factory);
        handler.setDefaultTopic("demo/unrouted");
        handler.setDefaultQos(1);
        handler.setDefaultRetained(false);
        handler.setAsync(false);
        handler.setCompletionTimeout(5000); // milliseconds
        handler.setConverter(new DefaultPahoMessageConverter());
        return handler;
    }

    @Bean
    IntegrationFlow telemetryFlow() {
        return IntegrationFlow.from("mqtt.telemetry.in")
                .handle(String.class, (payload, headers) -> {
                    System.out.println(
                            "Telemetry from "
                            + headers.get(MqttHeaders.RECEIVED_TOPIC)
                            + ", size=" + payload.length());
                    return null;
                })
                .get();
    }

    @Bean
    IntegrationFlow commandFlow(
            @Qualifier("mqttPublisher") MessageHandler publisher) {

        return IntegrationFlow.from("mqtt.commands.out")
                .handle(publisher)
                .get();
    }
}
~~~

Behavior:

- The inbound adapter subscribes to `sensors/+/temperature` at QoS 1, receives broker deliveries, and sends them to `mqtt.telemetry.in`. It needs no `@Poller`.
- The outbound handler publishes `Message<String>` messages from `mqtt.commands.out` to the broker; `setAsync(false)` and completion timeout bound the publish wait time.
- `DirectChannel` keeps the flow easy to observe, though sending threads may block waiting on network/broker during publishes. When switching to `QueueChannel`/`ExecutorChannel`, design pollers, capacity, and error flows.
- `defaultTopic("demo/unrouted")` is only to illustrate fallback; **never allow production commands missing a topic** to fall back to a default topic without validation.

### 10.7. Service creating messages with a stable ID

~~~java
package demo.mqttrecovery;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.mqtt.support.MqttHeaders;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
class CommandPublisher {

    private final MessageChannel output;

    CommandPublisher(
            @Qualifier("mqtt.commands.out") MessageChannel output) {
        this.output = output;
    }

    boolean publish(
            String commandId, String deviceId, String jsonPayload) {

        if (commandId == null || commandId.isBlank()) {
            throw new IllegalArgumentException("Missing commandId");
        }
        if (deviceId == null
                || !deviceId.matches("[A-Za-z0-9_-]{1,40}")) {
            throw new IllegalArgumentException("Invalid deviceId");
        }
        if (jsonPayload == null || jsonPayload.isBlank()) {
            throw new IllegalArgumentException("Missing payload");
        }

        String topic = "devices/" + deviceId + "/commands";

        return output.send(MessageBuilder.withPayload(jsonPayload)
                .setHeader(MqttHeaders.TOPIC, topic)
                .setHeader(MqttHeaders.QOS, 1)
                .setHeader(MqttHeaders.RETAINED, false)
                .setHeader("commandId", commandId)
                .build());
    }
}
~~~

An authorized caller can invoke:

~~~java
publisher.publish(
        "cmd-1001",
        "device-17",
        "{\"commandId\":\"cmd-1001\",\"action\":\"TURN_ON\"}");
~~~

**Contract:** `commandId` must appear inside the **MQTT payload** if the subscriber needs to read it. The Spring header `commandId` does not automatically travel as an MQTT v3 user property. In a real application, serialize a validated DTO to JSON rather than letting callers supply a raw JSON string that might mismatch the checked `commandId`.

`MqttHeaders.QOS=1` enables redeliveries; `MqttHeaders.RETAINED=false` avoids storing one-time commands for new subscribers. Neither property replaces a business ACK.

## 11. Testing Paho configuration without a broker

You can test `MqttConnectOptions` and factory beans in isolation **without loading MQTT adapters**. This catches wrong timeout units, clean session flags, automatic reconnect toggles, and injection ambiguity right in CI.

Add the dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Create `MqttClientConfigurationTest.java`:

~~~java
package demo.mqttrecovery;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.eclipse.paho.client.mqttv3.MqttConnectOptions;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.mqtt.core.MqttPahoClientFactory;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = MqttClientConfiguration.class)
@TestPropertySource(properties = {
        "app.mqtt.broker-url=tcp://localhost:1883"
})
class MqttClientConfigurationTest {

    @Autowired
    @Qualifier("subscriberOptions")
    MqttConnectOptions subscriberOptions;

    @Autowired
    @Qualifier("publisherOptions")
    MqttConnectOptions publisherOptions;

    @Autowired
    @Qualifier("subscriberFactory")
    MqttPahoClientFactory subscriberFactory;

    @Autowired
    @Qualifier("publisherFactory")
    MqttPahoClientFactory publisherFactory;

    @Test
    void connectionPoliciesRemainDistinct() {
        assertNotNull(subscriberFactory);
        assertNotNull(publisherFactory);
        assertFalse(subscriberOptions.isAutomaticReconnect());
        assertTrue(publisherOptions.isAutomaticReconnect());
        assertFalse(subscriberOptions.isCleanSession());
        assertTrue(publisherOptions.isCleanSession());
        assertEquals(10, publisherOptions.getConnectionTimeout());
        assertEquals(30, publisherOptions.getKeepAliveInterval());
    }
}
~~~

This test only verifies **beans and options**; it does not prove Paho reconnect works when the broker drops, that the adapter re-subscribes cleanly, or that outbound publishes receive ACKs.

### 11.1. Measuring timeouts with meaningful values

To test completion timeouts, you need an environment that can control the broker/network to force a **publish token to wait past the timeout**. Never put `Thread.sleep(5001)` inside a fake handler and claim you tested Paho's completion timeout: that only tests your application code sleeping, not the MQTT publish path.

Nor should you conclude from a fast localhost broker test that a 5-second completion timeout suffices for production WAN/TLS links. Test under realistic latency, packet loss, broker overload, and retries.

## 12. Testing the Spring outbound flow with a fake handler

To verify the **channel → endpoint** path without a broker, supply a fake `MessageHandler` that records messages or simulates errors. There is no need to load `MqttEndpointConfiguration`, whose inbound adapter automatically attempts network connections.

~~~java
package demo.mqttrecovery;

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
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.mqtt.support.MqttHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageDeliveryException;
import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = {
        CommandFlowTestConfiguration.class,
        RecordingPublisherConfiguration.class
})
class CommandFlowTest {

    @Autowired
    @Qualifier("mqtt.commands.out")
    MessageChannel output;

    @Autowired
    RecordingPublisher recorder;

    @BeforeEach
    void reset() {
        recorder.clear();
        recorder.setFail(false);
    }

    @Test
    void deliversTopicAndPayloadToOutboundEndpoint() {
        String json = "{\"commandId\":\"cmd-test-1\"}";

        boolean sent = output.send(
                MessageBuilder.withPayload(json)
                        .setHeader(MqttHeaders.TOPIC,
                                "devices/device-17/commands")
                        .setHeader(MqttHeaders.QOS, 1)
                        .setHeader(MqttHeaders.RETAINED, false)
                        .build());

        assertTrue(sent);
        assertEquals(
                List.of(new SentMessage(
                        json, "devices/device-17/commands")),
                recorder.snapshot());
    }

    @Test
    void directChannelReportsSynchronousFailure() {
        recorder.setFail(true);

        assertThrows(MessageDeliveryException.class,
                () -> output.send(
                        MessageBuilder.withPayload(
                                "{\"commandId\":\"cmd-test-2\"}")
                                .setHeader(MqttHeaders.TOPIC,
                                        "devices/device-17/commands")
                                .build()));
    }
}

record SentMessage(String payload, String topic) {}

class RecordingPublisher implements MessageHandler {

    private final List<SentMessage> records =
            new CopyOnWriteArrayList<>();
    private boolean fail;

    @Override
    public void handleMessage(Message<?> message) {
        if (fail) {
            throw new MessageDeliveryException(
                    message, "Simulated outbound failure");
        }
        records.add(new SentMessage(
                (String) message.getPayload(),
                (String) message.getHeaders().get(MqttHeaders.TOPIC)));
    }

    void setFail(boolean value) {
        fail = value;
    }

    List<SentMessage> snapshot() {
        return List.copyOf(records);
    }

    void clear() {
        records.clear();
    }
}

@Configuration
@EnableIntegration
class CommandFlowTestConfiguration {

    @Bean(name = "mqtt.commands.out")
    MessageChannel commandChannel() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow outboundFlow(
            @Qualifier("mqttPublisher") MessageHandler publisher) {
        return IntegrationFlow.from("mqtt.commands.out")
                .handle(publisher)
                .get();
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

What this test proves:

1. The channel exists and the flow and handler are registered.
2. Payload and topic headers reach the handler.
3. With `DirectChannel` and a handler throwing `MessageDeliveryException` synchronously, the caller observes the corresponding error.

It **does not prove** that Paho automatic reconnect works, completion timeouts fire properly, messages reached the broker, or subscribers processed them. Testing those requires a real test broker and network.

## 13. Experimenting with broker disconnect, reconnect, and completion timeout

End-to-end testing requires a dedicated MQTT broker under your control. Never intentionally disrupt the network or restart a production broker to test resilience.

You can use Mosquitto or an equivalent test/container broker alongside the `mosquitto_pub`/`mosquitto_sub` CLIs.

### 13.1. Verify the system works before injecting faults

Open Terminal A to receive commands:

~~~bash
mosquitto_sub -h localhost -p 1883 \
  -i test-command-subscriber-1 \
  -q 1 -t 'devices/+/commands' -v
~~~

Open Terminal B to send telemetry to the Spring inbound adapter:

~~~bash
mosquitto_pub -h localhost -p 1883 \
  -i test-telemetry-publisher-1 \
  -q 1 -t 'sensors/device-17/temperature' \
  -m '{"eventId":"evt-1001","celsius":26.5}'
~~~

When the broker is up, the inbound flow logs the topic and payload size. Call `CommandPublisher.publish(...)` in the app to test the outbound flow; if successful, the test subscriber receives the message.

### 13.2. Testing a disconnect after a successful connection

1. Verify both the inbound adapter and outbound handler have connected successfully.
2. Stop the test broker, or use a network fault-injection tool in the test environment.
3. Observe connected/disconnected states, publish exceptions, caller wait times, and recovery attempts.
4. Restore the test broker.
5. Verify the inbound adapter **re-subscribes to the right topics**, without Client ID conflicts, and processes fresh telemetry.
6. Verify the publisher can send new publications, distinguishing messages **sent after reconnect** from messages **potentially lost while offline**.
7. Reconcile counts in the outbox/quarantine against actual publications, including duplicates.

Do not merely read a "reconnected" log and assume the backlog was delivered completely. Under clean session/persistent session/QoS, session recovery and offline message retention still depend on the broker.

### 13.3. Testing a broker unavailable at startup

This is a **different test** from disconnecting after startup. When the broker has never accepted CONNECT, Paho automatic reconnect may not replace adapter startup retries. Check how the application behaves:

- Does it start cleanly with the endpoint in a retry state?
- Does it fail fast and shut down the application context?
- Does it report **not ready** for services depending on the broker?
- Does it hold pending commands in an outbox instead of losing them?
- Does it reconnect once the broker comes up without requiring a redeploy?

The exact outcome must be observed on your project's Spring Integration/Paho version. Never promise that every Spring Boot app with `setAutomaticReconnect(true)` starts and delivers messages smoothly when the broker is offline.

### 13.4. Simulating publish timeouts properly

To make a Paho publish token stay incomplete beyond 5 seconds, use a test broker or network proxy capable of **blocking/delaying packets/ACKs** after the client has connected. Test:

~~~text
Paho connectionTimeout = 10 seconds
Spring completionTimeout = 5000 milliseconds
MQTT publish QoS        = 1
Network fault            = block/delay PUBACK after PUBLISH
Expected                 = application observes timeout or publish error
                           and marks PUBLISH_UNCERTAIN
~~~

However, exact results depend on the client/broker, fault-injection method, and version. Blocking the entire network may be detected as **connection lost** before the completion timeout fires; distinguish the two causes accurately. Do not "fake a timeout" by sleeping inside a business handler.

### 13.5. Test matrix

| Case | Fault introduced | What to verify |
| --- | --- | --- |
| Broker drops after connecting | Restart test broker. | Auto reconnect/endpoint recovery and proper subscription restoration. |
| Broker down at startup | Start app before broker. | Startup policy, errors/logs, and recovery once broker appears. |
| Duplicate Client ID | Two active clients use the same ID. | Reconnect loop/kicks and proper ID assignment. |
| Wrong credentials or ACL | Broker rejects CONNECT/SUBSCRIBE/PUBLISH. | Do not infinitely retry a config error without alerting. |
| TLS error | Invalid certificate/hostname. | Fails properly; never bypass TLS verification. |
| Completion timeout | Delay/block publish ACK. | Timeout, uncertain state, idempotent retry. |
| QoS 1 publisher sends duplicate | Simulate lost ACK or app retry. | Subscriber deduplicates by `commandId`/`eventId`. |
| `cleanSession=false` subscriber offline | Publish QoS 1 while offline. | Session/subscription/backlog per broker policy. |
| Broker failover to another URI | Switch client to backup endpoint. | Session/retained/in-flight state and missing/duplicate data. |
| App shutdown with in-flight publish | Intentional stop. | Outbox recovery, pending state, no silent data loss. |

## 14. Threads, queues, and backpressure when the broker is slow

A synchronous outbound handler on a `DirectChannel` can stall callers when the broker is slow. If an HTTP inbound endpoint calls `DirectChannel.send(...)` and MQTT publishing waits 5 seconds, HTTP request latency spikes right along with it.

| Channel before MQTT handler | Advantage | Consequence during reconnect/timeout |
| --- | --- | --- |
| `DirectChannel` | Simple, synchronous error path. | Caller/poller blocks while handler waits to publish. |
| `ExecutorChannel` | Decouples processing thread from producer. | Must bound thread pool/queue, track async errors and shutdown. |
| `QueueChannel` | Buffers messages internally. | Needs poller, capacity, and durability; RAM queue loses data on restart. |
| Durable broker/outbox | Persists unpublished work. | Adds complexity; still needs idempotency and checkpoints. |

An architecture with an outbox:

~~~mermaid
flowchart LR
    API["Business service"]
    DB[("Business DB + transactional outbox")]
    WORKER["Outbox worker<br/>backoff / claim / retry"]
    FLOW["Spring MQTT outbound flow"]
    BROKER[("MQTT broker")]
    DEVICE["Subscriber/device"]
    ACK["ACK flow"]
    API -->|"Single DB transaction"| DB
    DB --> WORKER --> FLOW --> BROKER --> DEVICE
    DEVICE -. "Business ACK" .-> ACK
~~~

If the broker stays offline for several minutes while upstream produces 10,000 messages/second, a 100-item RAM queue cannot save you. Apply rate limiting, durable persistence, accept work only within system capacity, and return appropriate retry/throttling signals upstream.

### 14.1. Completion timeout is not a circuit breaker

Completion timeout only limits how long a single operation waits; it does not automatically:

- Pause new sends during a cooldown window.
- Cap concurrent requests.
- Prevent retry storms.
- Reroute to another broker/target.
- Move messages to a DLQ or durable outbox.

If you need those behaviors, apply circuit breakers/rate limiters/retry advice/outboxes at the appropriate layer and test how they interact with client auto-reconnect.

## 15. Error handling and endpoint state

### 15.1. Error channels in Spring Integration

In synchronous flows, exceptions from handlers can propagate up the call stack to the producer or gateway. In asynchronous or polling flows, errors may be routed as `ErrorMessage` instances to `errorChannel` or an error flow depending on endpoint/advice configuration. MQTT connection errors can also surface via events, logging, or client callbacks.

**Never assume** every Paho failure is automatically published as a message to an arbitrary Spring error channel. Design an error policy covering:

- Connect/auth/TLS errors.
- Subscribe/topic ACL errors.
- Converter/schema errors.
- Channel dispatch errors.
- MQTT publish completion/timeout errors.
- Downstream DB/HTTP errors after inbound.
- Missing business ACKs.

Each category warrants a distinct strategy: fix configuration, retry with backoff, quarantine, persist to outbox, DLQ, or reconcile.

### 15.2. Bounded retries and non-recoverable errors

Do not infinitely retry a malformed JSON payload or a topic rejected by ACLs. Those errors will not vanish just because the broker reconnects. Conversely, a brief network timeout may be worth retrying, provided retries are bounded in count/duration and keep the same `eventId`.

Policy sketch:

~~~text
network disconnected:
    mark PUBLISH_UNCERTAIN
    retry with backoff and same eventId
    stop after retry budget / escalate

invalid topic or forbidden publish:
    reject/quarantine
    alert on configuration/security issue
    no blind retry loop

downstream business validation failed:
    do not treat as MQTT reconnect issue
    create data-quality error with correlationId
~~~

The policy above is a business specification, not built-in Spring Integration configuration. Implement it using appropriate handlers, advice, outboxes, and monitoring.

## 16. Lifecycle and observability

### 16.1. Metrics and states to measure

| Useful metric/log | Why |
| --- | --- |
| `mqtt_connected{clientId,role}` | Detects offline publishers/subscribers; avoid labels containing secrets. |
| `mqtt_disconnect_total` | Distinguishes isolated disconnects from reconnect loops. |
| `mqtt_reconnect_attempt_total` | Detects broker outages and thundering herds. |
| `mqtt_connection_duration_ms` | Measures connection establishment and TLS handshakes. |
| `mqtt_publish_completion_ms` | Tunes completion timeout from real measurements rather than guesses. |
| `mqtt_publish_timeout_total` | Flags slow brokers/networks or QoS ACK issues. |
| `mqtt_pending_outbox` | Count of commands/events awaiting safe publication. |
| `mqtt_subscription_recovered_total` | Confirms inbound subscribers resume after reconnects. |
| `business_ack_lag_ms` | Measures gap between MQTT publish and business confirmation. |
| `message_duplicate_total` | Tracks downstream deduplication effectiveness. |

These names are **design suggestions**, not exact default metrics emitted by Spring Integration/Paho.

### 16.2. Tracing an event across the pipeline

With payload:

~~~json
{
  "commandId": "cmd-1001",
  "deviceId": "device-17",
  "action": "TURN_ON"
}
~~~

Log/trace states across steps:

~~~text
cmd-1001 CREATED
cmd-1001 PUBLISH_ATTEMPTED
cmd-1001 PUBLISH_UNCERTAIN (completion timeout)
cmd-1001 PUBLISH_CONFIRMED (per outcome observed after retry)
cmd-1001 BUSINESS_ACKNOWLEDGED (device confirmed)
~~~

Every state transition should carry timestamps and correlation IDs, while **never logging secrets, credentials, or sensitive full payloads**. State must never jump straight from `CREATED` to `BUSINESS_ACKNOWLEDGED` simply because `MessageChannel.send()` succeeded.

### 16.3. Startup readiness and graceful shutdown

When the broker is mandatory for core functionality, readiness checks may need to report degraded/not ready until both publisher and subscriber operate within SLA. However, do not necessarily crash the whole application if the broker serves a non-critical feature and an outbox still accepts work.

On shutdown:

1. Stop accepting new commands or enqueue them into the outbox.
2. Wait for in-flight publishes within a bounded grace period.
3. Preserve unreconciled `PUBLISH_UNCERTAIN` records.
4. Stop adapters/clients to release connections and threads.
5. Ensure restarts do not reuse a Client ID colliding with an older still-active replica.

Automatic reconnect is not a mechanism for "keep the app running and you'll never lose data"; shutdown and crash recovery require explicit durable persistence planning.

## 17. Security and environment configuration

Automatic reconnect can retry repeatedly against expired credentials, wrong TLS certificates, or updated ACLs. Those are **configuration/security failures**—never mask them by raising timeouts.

| Risk | Mitigation |
| --- | --- |
| Plaintext TCP on untrusted network | Use TLS and verify certificate chains/hostnames. |
| Reconnecting with revoked credentials | Alert early; rotate secrets via a safe process. |
| Duplicate Client IDs | Assign stable/valid identities per instance or consumer ownership. |
| Publishing to the wrong topic | Validate device/tenant, enforce broker topic ACLs and default topic policies. |
| Retry storm after broker recovery | Backoff with jitter, concurrency caps, and bounded outbox workers. |
| Uncontrolled replay of sensitive payloads | Encryption/retention/ACLs, audit replays, limit copies. |
| Dangerous commands executed twice | Stable `commandId`, idempotency, expiration, and state checks. |
| Stale MQTT retained commands | `retained=false` for one-time commands; clean up improper retained messages via admin workflow. |

In Paho v3, TLS URIs typically look like `ssl://broker-host:8883`. Changing the URL string alone is not enough: supply proper trust configuration/certificates and verify live connectivity. Never disable hostname verification in production.

## 18. Common configuration mistakes

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| `automaticReconnect=true`, yet app fails immediately at startup. | Never completed initial CONNECT; endpoint startup policy differs from mid-run disconnect recovery. | Test initial connection failure separately; design appropriate readiness/startup retries. |
| App reconnects nonstop even though broker is healthy. | Duplicate Client ID, ACL, network proxy, or broker kicking connection. | Inspect broker logs, Client IDs, and policies rather than just raising timeouts. |
| Inbound adapter receives nothing after reconnect. | Session/subscriptions not restored or wrong topic filter/ACL. | Check clean session, re-subscription, Client ID, and version behavior. |
| Very short completion timeout fails over WAN. | Insufficient latency budget for QoS/SSL or loaded broker. | Measure publish latency; tune timeout and backpressure appropriately. |
| Retrying after timeout creates duplicate commands. | Broker may have received it before ACK dropped. | Keep same `commandId`, enforce idempotency and reconciliation. |
| `MessageChannel.send()` returns true, yet publish fails later. | Async handler or thread handoff. | Monitor publish callbacks/events/outbox; do not treat send as MQTT ACK. |
| Raising `connectionTimeout` leaves publishing slow. | That only governs opening connections, not publish completion. | Check `setCompletionTimeout(...)` and broker QoS/latency. |
| Changing keepalive fails to prevent devices from appearing offline. | Keepalive only monitors the MQTT connection, not device business health. | Implement business device heartbeats/Last Will messages. |
| Queue fills up while broker is offline. | Inbound rate exceeds publish rate; no backpressure. | Rate limiting, persistent outbox, capacity caps, alerts. |
| QoS 2 still produces duplicate business events. | Two independent publishes or retried business side effects. | Use `eventId`/unique constraints, not QoS 2 alone. |
| Broker failover loses old subscriptions. | Two independent brokers do not share persistent sessions. | Verify cluster/session replication and re-subscription. |
| Auto reconnect causes CPU/log spam. | Misconfigured retries without proper backoff/jitter/alerts. | Fix root cause, throttle logging, and measure actual retry rates. |
| Listener stays connected, yet DB has no writes. | Converter/handler/channel/downstream failure. | Inspect the entire pipeline and error channel, not only the MQTT client. |

## 19. Verified practice exercise

**Context:** a smart-home system uses MQTT to ingest temperature from sensors and publish air-conditioner commands. The broker may drop for 30–60 seconds during peak hours; on/off commands must not execute repeatedly, and states must be reconcilable.

Tasks:

1. Configure a Spring Integration MQTT inbound adapter subscribing to `sensors/+/temperature`, and an outbound handler publishing to `devices/{id}/commands`.
2. Assign two distinct Client IDs; explain why publisher and subscriber must not share the same ID.
3. Create two `MqttPahoClientFactory` beans with separate options: one demonstrating adapter recovery, the other demonstrating Paho automatic reconnect.
4. Set `connectionTimeout=10s`, `keepalive=30s`, `recoveryInterval=10000ms`, and `completionTimeout=5000ms`. Note the units explicitly.
5. Write brokerless integration tests verifying connection options policies, channels, message headers, and synchronous exception handling.
6. With a test broker, send telemetry and commands successfully before injecting faults.
7. Stop the broker after a successful connection; observe reconnect attempts, reconnect duration, and subscription recovery.
8. Start the application while the broker is offline; compare with losing the connection after startup.
9. Use fault injection to trigger a QoS 1 publish with an ACK slower than `completionTimeout`; mark the state `PUBLISH_UNCERTAIN`.
10. Retry the same `commandId` via an outbox; have the device/subscriber enforce idempotency to prevent a second side effect.
11. Test `cleanSession=true/false` and a stable Client ID across offline windows; observe message backlog and missing/duplicate deliveries.
12. Place the handler behind a bounded `QueueChannel`; measure backlog while the broker is offline and behavior when the queue is full.
13. Add readiness/alerts and track failed publishes, uncertain messages, duplicates, and business ACK timeouts.
14. Explain how authentication/TLS failures differ from transient network outages and why configuration errors must not be retried infinitely.

**Completion criteria:** clear state diagram, separated timeouts, tests distinguishing initial connect from reconnect, logs/states never confusing MQTT publish with business ACK, and a strategy that neither loses commands nor repeats side effects across broker/app restarts.

## 20. Self-check questions

1. What problem does `MqttConnectOptions.setAutomaticReconnect(true)` solve?
2. Does it automatically retry forever if the very first connection never succeeds?
3. Is `MqttPahoMessageDrivenChannelAdapter.setRecoveryInterval(10000)` in milliseconds or seconds?
4. Why shouldn't you enable both reconnect mechanisms without testing their interaction on your version?
5. How does `setConnectionTimeout(10)` differ from `setCompletionTimeout(5000)`?
6. Is keepalive the ACK timeout for a command?
7. When a QoS 1 publish times out, can you be sure the broker never received the message?
8. Why can retrying with a new PUBLISH create duplicates despite QoS?
9. Does QoS 2 guarantee a database transaction commits only once?
10. Why can `setAsync(true)` make `MessageChannel.send()` return before the broker ACK?
11. After the publisher finishes auto-reconnecting, why might the subscriber still miss messages?
12. How do clean session and Client ID affect offline delivery?
13. Are two replicas sharing the same Client ID a valid way to load-balance a subscriber?
14. Do multiple broker URIs guarantee synchronized sessions/state across failover?
15. Is `completionTimeout` a circuit breaker?
16. Why does a test with a fake `MessageHandler` fail to prove Paho recovery?
17. How do you verify a timeout came from the publish token rather than opening TCP/TLS?
18. In an outbox-backed system, how should you handle messages whose broker receipt is uncertain?
19. Which metrics help detect reconnect loops and rising publish latency?
20. Why must a device emit a dedicated business ACK when business rules require execution confirmation?

**Hint:** automatic reconnect is a connection recovery strategy; completion timeout bounds waiting on one operation; MQTT success does not equal business completion. Explicitly model message states, Client IDs, QoS, replay, and idempotency.

## 21. Conclusion

**Automatic reconnect and completion timeout** are two foundational tools when operating MQTT adapters in Spring Integration:

- `MqttConnectOptions.setAutomaticReconnect(true)` helps Paho attempt to restore an established connection after a drop, yet it does not replace startup policies, authentication handling, or durable storage.
- `MqttPahoMessageDrivenChannelAdapter.setRecoveryInterval(...)` governs endpoint connection recovery; verify interactions with Paho reconnect on your exact version.
- `MqttPahoMessageHandler.setCompletionTimeout(...)` bounds publish wait time under the applicable processing mode; **a timeout can produce an uncertain outcome**, not proof that the broker missed the message.
- `connectionTimeout`, `keepAliveInterval`, `recoveryInterval`, `completionTimeout`, and business ACK timeout are distinct quantities with different units and goals.

In the **SPRING_INTEGRATION_ADAPTERS** module, a reliable architecture is more than "the client reconnects by itself." You must align **Client ID/session, subscriptions, QoS/retained, MessageChannel, and threading**, alongside error handling, backpressure, transactional outboxes, idempotency, monitoring, and broker-failure testing. Knowing which stage a message is in and who owns recovery allows the system to operate safely even when the network or broker is unstable.
