# MQTT client factory and broker URL

## 1. Learning objectives

In Spring Integration, connecting to an MQTT broker does not start with a `MessageChannel`, but with an **MQTT client**. The client must know where the broker is located, which transport protocol to use, whether authentication or TLS is required, how long to wait before timing out, how to manage sessions, and which ID identifies the client. Spring Integration encapsulates this shared configuration in **`MqttPahoClientFactory`**, enabling both inbound and outbound MQTT adapters to use consistently managed connections.

This lesson, **MQTT client factory and broker URL**, belongs to the **Adapter MQTT** chapter of the **SPRING_INTEGRATION_ADAPTERS** module. The module aims to connect external systems using inbound/outbound adapters, gateways, pollers, and `MessageChannel`, practicing with files, SFTP, HTTP, JMS, AMQP, Kafka, and databases, while handling message contracts, errors, and connection lifecycles. Because MQTT is a publish–subscribe protocol, managing brokers, clients, and subscriptions differs from polling sources like file/SFTP/JDBC.

After completing this lesson, learners will be able to:

- Understand the relationship between **`DefaultMqttPahoClientFactory`**, **`MqttConnectOptions`**, MQTT clients, and MQTT adapters.
- Choose a broker URL with the right protocol (`tcp://`, `ssl://`), distinguishing the connection URL from an MQTT topic.
- Configure multiple broker URIs for **fallback connectivity**, without mistaking it for message load balancing.
- Create a Spring factory bean and use it for both `MqttPahoMessageDrivenChannelAdapter` and `MqttPahoMessageHandler`.
- Manage Client IDs, sessions, keepalive, connection timeouts, recovery/reconnection, and multi-instance deployments.
- Apply TLS, credentials/ACLs, environment variables, and the rule of keeping secrets out of source code.
- Test the factory configuration **without a broker**, then verify real connectivity in end-to-end tests.
- Analyze the boundaries of the factory: being connected does not mean MQTT messages were processed successfully downstream.

**Key takeaway:** The factory is responsible for **creating and configuring the protocol client**. The inbound adapter handles subscribing and emitting Spring messages to a channel; the outbound adapter receives Spring messages from a channel and publishes them. Capabilities like business retries, transactions, idempotency, or device ACKs **do not appear automatically just because the factory connects to the broker**.

## 2. Where does the factory sit in the architecture?

~~~mermaid
flowchart LR
    CFG["Spring Configuration<br/>broker URL, TLS, credentials, session"]
    OPT["MqttConnectOptions"]
    FACTORY["DefaultMqttPahoClientFactory"]
    INBOUND["MqttPahoMessageDrivenChannelAdapter<br/>subscriber client ID"]
    OUTBOUND["MqttPahoMessageHandler<br/>publisher client ID"]
    BROKER[("MQTT Broker")]
    INCH["mqtt.inbound<br/>MessageChannel"]
    OUTCH["mqtt.outbound<br/>MessageChannel"]
    FLOW["IntegrationFlow"]
    CFG --> OPT --> FACTORY
    FACTORY --> INBOUND
    FACTORY --> OUTBOUND
    BROKER -->|"deliver"| INBOUND --> INCH --> FLOW
    FLOW --> OUTCH --> OUTBOUND -->|"publish"| BROKER
~~~

The components carry distinct responsibilities:

| Component | Role | Distinction to keep in mind |
| --- | --- | --- |
| `MqttConnectOptions` | Describes broker URIs, timeout, keepalive, credentials, and TLS/session settings in the Eclipse Paho v3 API. | This is **connection configuration**, not an MQTT message. |
| `MqttPahoClientFactory` | Factory interface used by MQTT adapters to obtain preconfigured MQTT clients. | Not an MQTT broker. |
| `DefaultMqttPahoClientFactory` | Common implementation that accepts `MqttConnectOptions`. | Not a channel and does not create an integration flow on its own. |
| `MqttPahoMessageDrivenChannelAdapter` | Subscriber client receiving messages via callbacks and emitting to a Spring channel. | Does not require a poller to read the MQTT broker. |
| `MqttPahoMessageHandler` | Outbound handler publishing payload/topic from a Spring message to the broker. | Not a synchronous gateway waiting for a business result from a subscriber. |
| `MessageChannel` | Hands off messages between Spring Integration endpoints. | Does not contain broker URL information. |
| MQTT broker | Server receiving publications and distributing them by topic/subscription. | Does not manage downstream application transactions. |

Typically, the factory is registered as a **singleton Spring bean** holding connection settings. Two adapters can inject the same factory bean, but **you should not conclude** that inbound and outbound share the same physical connection or Client ID. Each adapter specifies its own client identity and manages its subscribe/publish operations accordingly.

### 2.1. Sharing a factory versus sharing a client

Suppose an application both subscribes to `sensors/+/temperature` and publishes to `devices/+/commands`. Both adapters can share one `MqttPahoClientFactory` to reuse URIs, TLS trust settings, and credentials. However:

1. The inbound adapter needs an appropriate **subscriber Client ID** to manage its session/subscriptions.
2. The outbound handler needs a separate **publisher Client ID** to avoid connection contention.
3. If the two directions have different session or credential policies, create **two factory beans** or separate configurations rather than forcing every adapter to share identical options.
4. A factory is not a message bus that automatically shares subscriptions or business ACKs across adapters.

**Never use the same Client ID for two concurrent MQTT clients.** Brokers generally treat Client ID as the unique identity of an active session; a new client connecting with the same ID can disconnect the existing one.

## 3. What is a Broker URL?

A **Broker URL** (connection URI) is the address Eclipse Paho uses to **open an MQTT connection to the server**. It is neither a topic nor a Spring `MessageChannel` address.

Common examples with Paho MQTT v3:

| Broker URI | Transport | Usage context |
| --- | --- | --- |
| `tcp://localhost:1883` | Unencrypted MQTT over TCP. | Local test broker on the same machine. |
| `tcp://mqtt-broker.internal:1883` | MQTT over TCP within an internal network. | Only when network and security policies permit it. |
| `ssl://mqtt.example.com:8883` | MQTT over TLS using the Paho v3 URI scheme. | Connections requiring encryption and server verification. |

**Do not equate a broker URL with a web URL** like `https://...`, or blindly replace `tcp://` with `mqtt://` without checking whether the MQTT client library supports that URI scheme. Paho also supports WebSocket connections in specific versions/configurations; this lesson limits scope to `tcp://` and `ssl://` to illustrate the Paho v3 API.

A URI consists of: **scheme → host → port**. When changing the port, ensure the broker is actually listening on that port and firewalls/security groups allow it. Ports 1883/8883 are common conventions, not a guarantee that every broker uses them by default.

~~~text
tcp://mqtt-broker.internal:1883
│     │                    │
│     │                    └─ MQTT broker port
│     └────────────────────── Broker hostname / IP
└──────────────────────────── Transport scheme
~~~

### 3.1. How does a Broker URI differ from an MQTT topic?

~~~text
Broker URI: tcp://localhost:1883
Client ID:  telemetry-subscriber-1
Subscribe:  sensors/+/temperature

Publish topic: devices/device-17/commands
Payload:       {"commandId":"cmd-1001","action":"TURN_ON"}
~~~

- The Broker URI is used when **establishing the connection**.
- The Client ID identifies the MQTT client session with the broker.
- A subscribe filter like `sensors/+/temperature` is registered by the inbound adapter **after connecting**.
- A publish topic like `devices/device-17/commands` specifies where to **send the message** in the broker's topic namespace.

Do not embed a topic into the broker URI string like `tcp://localhost:1883/devices/...`. In raw MQTT over TCP, the topic is an MQTT protocol field, not an HTTP path. To carry multiple event types, keep the broker URI stable and configure topics/subscriptions on adapters and messages.

### 3.2. Broker URIs and environment-specific configuration

| Environment | Example | Recommendation |
| --- | --- | --- |
| Local development | `tcp://localhost:1883` | Dedicated test broker; never use real data. |
| Integration test | URI of test/container broker. | Wait for broker readiness; isolate test Client IDs/topics. |
| Staging | `ssl://mqtt-staging.example.internal:8883` | Use TLS and topic permissions close to production. |
| Production | `ssl://mqtt-prod.example.internal:8883` or infrastructure-provided DNS/VIP. | Configure secrets, TLS trust, monitoring, and a failover plan. |

When an application runs inside a container, `localhost` refers to **that container itself**, not the MQTT broker on the host machine or another container. Use a DNS/service name reachable from the application's network namespace.

## 4. Dependencies and choosing the MQTT client version

With Spring Boot managing dependency versions, the minimal Maven configuration is:

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

`spring-integration-mqtt` provides MQTT adapters and factory components based on Eclipse Paho. Examples in this lesson use **Paho MQTT v3**, specifically `org.eclipse.paho.client.mqttv3.MqttConnectOptions`, suitable for MQTT 3.1.1 clients.

Do not mix the v3 API in these examples with the MQTT v5 API simply because a broker supports both. MQTT v5 introduces concepts such as session expiry and user properties; how they are expressed in client/options differs from MQTT v3's `cleanSession`.

Core imports:

~~~java
import org.eclipse.paho.client.mqttv3.MqttConnectOptions;
import org.springframework.integration.mqtt.core.DefaultMqttPahoClientFactory;
import org.springframework.integration.mqtt.core.MqttPahoClientFactory;
import org.springframework.integration.mqtt.inbound.MqttPahoMessageDrivenChannelAdapter;
import org.springframework.integration.mqtt.outbound.MqttPahoMessageHandler;
~~~

Prefer letting the **Spring Boot BOM manage versions** of Spring Integration/Paho and check the API for the exact version in use. Adding `mqtt:...` entries to a YAML file or having an MQTT URL does not substitute for having a compatible MQTT module on the classpath.

## 5. Creating MqttPahoClientFactory with a Spring @Bean

For a test broker, the shortest Java configuration is:

~~~java
@Configuration
class SimpleMqttFactoryConfiguration {

    @Bean
    MqttPahoClientFactory mqttClientFactory() {
        MqttConnectOptions options = new MqttConnectOptions();
        options.setServerURIs(new String[] {
                "tcp://localhost:1883"
        });
        options.setConnectionTimeout(10);
        options.setKeepAliveInterval(30);
        options.setCleanSession(true);

        DefaultMqttPahoClientFactory factory =
                new DefaultMqttPahoClientFactory();
        factory.setConnectionOptions(options);
        return factory;
    }
}
~~~

This snippet requires importing `@Configuration`, `@Bean`, and the Paho/Spring Integration classes listed above. Only use hardcoded URLs in a local example; deployed applications must read broker URLs and credentials from environment-based configuration.

Meaning of each setting:

- `setServerURIs(String[])` provides **one or more broker endpoints** for Paho to attempt connections against.
- `setConnectionTimeout(10)` sets the connection timeout in **seconds**.
- `setKeepAliveInterval(30)` sets the keepalive interval in **seconds**, helping the broker/client detect dropped connections at the protocol level.
- `setCleanSession(true)` starts a fresh session on connect per MQTT 3.1.1. If a subscriber needs a persistent session across offline periods, redesign Client ID, QoS, and session policy accordingly.
- `setConnectionOptions(options)` attaches the options to the factory so adapters build clients with shared settings.

**Important:** creating the factory bean does not mean an MQTT connection is open yet. Connections are established during the adapter/client lifecycle when the adapter starts or publishes/subscribes according to endpoint behavior.

## 6. Complete example: configuring the broker URL via application.properties

We will build a small application with two flows: inbound telemetry subscription and outbound command publishing. Both use **one factory bean** while keeping **separate Client IDs**. The goal is to clarify where connection settings live, how adapters connect, and which channels messages traverse.

File structure:

~~~text
src/main/java/demo/mqttfactory/
    MqttFactoryApplication.java
    MqttConnectionConfiguration.java
    MqttAdapterConfiguration.java

src/main/resources/
    application.properties
~~~

Requires Java 17+ and Spring Boot/Spring Integration with a compatible MQTT module. A running MQTT broker is required to test publish/subscribe end-to-end; running Spring Boot does not start a broker.

### 6.1. Property placeholders and environment variables

~~~properties
# Broker URI: one or more URIs, separated by commas.
app.mqtt.broker-urls=${MQTT_BROKER_URLS:tcp://localhost:1883}

# Two client IDs must be different at the same time.
app.mqtt.inbound-client-id=${MQTT_INBOUND_CLIENT_ID:demo-telemetry-in-1}
app.mqtt.outbound-client-id=${MQTT_OUTBOUND_CLIENT_ID:demo-command-out-1}

app.mqtt.subscribe-topic=sensors/+/temperature
app.mqtt.publish-topic=devices/demo-1/commands

# Paho MQTT v3 parameters.
app.mqtt.connection-timeout-seconds=10
app.mqtt.keep-alive-seconds=30
app.mqtt.clean-session=true

# Read secrets from environment variables, do not commit real values.
app.mqtt.username=${MQTT_USERNAME:}
app.mqtt.password=${MQTT_PASSWORD:}
~~~

In production, configure broker URLs, IDs, username/password, and certificates via deployment secrets or a configuration management system. Never commit real passwords to `application.properties` in a repository, and never print raw secrets into logs during bean configuration.

### 6.2. Bootstrapping Spring Boot

~~~java
package demo.mqttfactory;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MqttFactoryApplication {

    public static void main(String[] args) {
        SpringApplication.run(MqttFactoryApplication.class, args);
    }
}
~~~

`@SpringBootApplication` scans `@Configuration` classes in the same package or subpackages. The Spring Boot integration starter provides the infrastructure for Spring Integration to register endpoints from bean definitions.

### 6.3. Configuring options and factory independently

~~~java
package demo.mqttfactory;

import java.util.Arrays;

import org.eclipse.paho.client.mqttv3.MqttConnectOptions;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.mqtt.core.DefaultMqttPahoClientFactory;
import org.springframework.integration.mqtt.core.MqttPahoClientFactory;

@Configuration
class MqttConnectionConfiguration {

    @Bean
    MqttConnectOptions mqttConnectOptions(
            @Value("${app.mqtt.broker-urls}") String brokerUrls,
            @Value("${app.mqtt.connection-timeout-seconds:10}")
            int connectionTimeoutSeconds,
            @Value("${app.mqtt.keep-alive-seconds:30}")
            int keepAliveSeconds,
            @Value("${app.mqtt.clean-session:true}") boolean cleanSession,
            @Value("${app.mqtt.username:}") String username,
            @Value("${app.mqtt.password:}") String password) {

        String[] uris = Arrays.stream(brokerUrls.split(","))
                .map(String::trim)
                .filter(uri -> !uri.isBlank())
                .toArray(String[]::new);

        if (uris.length == 0) {
            throw new IllegalArgumentException(
                    "app.mqtt.broker-urls must contain at least one URI");
        }

        for (String uri : uris) {
            if (!uri.startsWith("tcp://")
                    && !uri.startsWith("ssl://")) {
                throw new IllegalArgumentException(
                        "Only tcp:// or ssl:// are allowed in this demo: " + uri);
            }
        }

        var options = new MqttConnectOptions();
        options.setServerURIs(uris);
        options.setConnectionTimeout(connectionTimeoutSeconds);
        options.setKeepAliveInterval(keepAliveSeconds);
        options.setCleanSession(cleanSession);

        if (!username.isBlank()) {
            options.setUserName(username);
        }
        if (!password.isBlank()) {
            options.setPassword(password.toCharArray());
        }

        return options;
    }

    @Bean
    MqttPahoClientFactory mqttClientFactory(
            MqttConnectOptions mqttConnectOptions) {

        var factory = new DefaultMqttPahoClientFactory();
        factory.setConnectionOptions(mqttConnectOptions);
        return factory;
    }
}
~~~

The design uses **two separate beans**:

1. `mqttConnectOptions` holds all connection parameters, making it easy to unit test and inspect via safe properties without logging secrets.
2. `mqttClientFactory` holds the options and supplies them to adapters when Spring starts the flows.

The example only permits `tcp://` or `ssl://` URIs. It does **not** verify DNS, whether the broker is listening, or whether TLS certificates are valid—those are only verified during actual connection attempts. If a broker uses WebSockets, add the scheme and configure the client appropriately **after verifying Paho version support**.

When username/password are omitted, the client attempts to connect according to broker policy; not every broker allows anonymous connections. When production requires authentication, validate required fields fail-fast and avoid starting up with missing secrets.

### 6.4. Inbound and outbound adapters sharing a factory

~~~java
package demo.mqttfactory;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.mqtt.core.MqttPahoClientFactory;
import org.springframework.integration.mqtt.inbound.MqttPahoMessageDrivenChannelAdapter;
import org.springframework.integration.mqtt.outbound.MqttPahoMessageHandler;
import org.springframework.integration.mqtt.support.DefaultPahoMessageConverter;
import org.springframework.integration.mqtt.support.MqttHeaders;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHandler;

@Configuration
class MqttAdapterConfiguration {

    @Bean(name = "mqtt.inbound")
    MessageChannel mqttInboundChannel() {
        return new DirectChannel();
    }

    @Bean(name = "mqtt.outbound")
    MessageChannel mqttOutboundChannel() {
        return new DirectChannel();
    }

    @Bean
    MqttPahoMessageDrivenChannelAdapter mqttInboundAdapter(
            MqttPahoClientFactory factory,
            @Qualifier("mqtt.inbound") MessageChannel input,
            @Value("${app.mqtt.inbound-client-id}") String clientId,
            @Value("${app.mqtt.subscribe-topic}") String topicFilter) {

        var adapter = new MqttPahoMessageDrivenChannelAdapter(
                clientId, factory, topicFilter);
        adapter.setQos(1);
        adapter.setRecoveryInterval(10000);
        adapter.setConverter(new DefaultPahoMessageConverter());
        adapter.setOutputChannel(input);
        return adapter;
    }

    @Bean(name = "mqttPublisher")
    MqttPahoMessageHandler mqttPublisher(
            MqttPahoClientFactory factory,
            @Value("${app.mqtt.outbound-client-id}") String clientId,
            @Value("${app.mqtt.publish-topic}") String topic) {

        var handler = new MqttPahoMessageHandler(
                clientId, factory);
        handler.setDefaultTopic(topic);
        handler.setDefaultQos(1);
        handler.setDefaultRetained(false);
        handler.setAsync(false);
        handler.setCompletionTimeout(5000);
        handler.setConverter(new DefaultPahoMessageConverter());
        return handler;
    }

    @Bean
    IntegrationFlow telemetryFlow() {
        return IntegrationFlow.from("mqtt.inbound")
                .handle(String.class, (payload, headers) -> {
                    System.out.println(
                            "MQTT received topic="
                            + headers.get(MqttHeaders.RECEIVED_TOPIC)
                            + ", bytes=" + payload.length());
                    return null; // one-way inbound
                })
                .get();
    }

    @Bean
    IntegrationFlow outboundFlow(
            @Qualifier("mqttPublisher") MessageHandler publisher) {

        return IntegrationFlow.from("mqtt.outbound")
                .handle(publisher)
                .get();
    }
}
~~~

Both adapters use the **same factory bean** but are configured with two distinct Client IDs. `mqttInboundAdapter` receives messages from the broker and uses `setOutputChannel(...)` to emit Spring messages onto `mqtt.inbound`; `outboundFlow` listens on `mqtt.outbound` and uses `mqttPublisher` to publish messages.

When the application starts, the inbound adapter starts its subscription and connects to the broker per lifecycle rules. The outbound handler creates/uses a client connection when publishing. **Do not also annotate the same handler with `@ServiceActivator(inputChannel="mqtt.outbound")` if the DSL already registers a consumer**; avoid creating unintended competing endpoints.

Example service sending a command to the outbound channel:

~~~java
@Service
class DeviceCommandPublisher {

    private final MessageChannel output;

    DeviceCommandPublisher(
            @Qualifier("mqtt.outbound") MessageChannel output) {
        this.output = output;
    }

    void publish(String commandJson, String deviceId) {
        // Must validate deviceId, tenant, and permissions before building the topic.
        String topic = "devices/" + deviceId + "/commands";
        output.send(MessageBuilder.withPayload(commandJson)
                .setHeader(MqttHeaders.TOPIC, topic)
                .setHeader(MqttHeaders.QOS, 1)
                .setHeader(MqttHeaders.RETAINED, false)
                .build());
    }
}
~~~

This snippet requires importing `@Service`, `@Qualifier`, `MessageChannel`, `MessageBuilder`, and `MqttHeaders`. It assumes the caller has already validated `deviceId` and JSON per contract; **never use an untrusted device ID directly** to route publications. For multi-tenant data access, enforce both client/broker ACLs and business-layer permissions.

### 6.5. Expected result and limitations

~~~mermaid
sequenceDiagram
    participant APP as Java / Spring Integration
    participant OUT as MQTT outbound handler
    participant F as MqttPahoClientFactory
    participant BROKER as MQTT broker
    participant IN as MQTT inbound adapter
    participant FLOW as mqtt.inbound flow
    APP->>OUT: Message<String> + mqtt_topic
    OUT->>F: Uses Paho client configuration
    OUT->>BROKER: PUBLISH topic + QoS
    BROKER-->>OUT: MQTT protocol acknowledgement per QoS
    BROKER->>IN: DELIVER when topic filter matches
    IN->>FLOW: Spring Message<String>
~~~

A successful publish call does not mean the subscriber updated the device state. If a business ACK is required, design an ACK topic, message correlation, timeouts, idempotency, and a dedicated inbound consumer. The factory only manages connections; **it does not turn MQTT into a request–reply transaction**.

## 7. Multiple broker URLs: fallback is not load balancing

`MqttConnectOptions#setServerURIs(...)` can accept multiple URIs:

~~~java
options.setServerURIs(new String[] {
        "ssl://mqtt-a.example.internal:8883",
        "ssl://mqtt-b.example.internal:8883"
});
~~~

The goal is usually to provide **a list of broker endpoints that Paho can try connecting to**. However, distinguish these architectures:

| Infrastructure type | Meaning of multiple URIs | Risks |
| --- | --- | --- |
| Nodes belonging to one MQTT cluster with shared state/sessions | Client can try another endpoint when one node is unavailable per client/broker behavior. | Session/subscription/retained behavior still depends on the real broker cluster. |
| Two independent brokers without shared data | Client can connect to the other broker. | Topics/history/sessions between the two brokers do not sync automatically. |
| DNS/VIP/load balancer in front of a cluster | Client may only need a single DNS/VIP. | Requires proper health checks, sticky sessions, or broker cluster behavior. |

**Multiple URIs do not mean a publish is sent to every broker.** Paho connects to one endpoint in the list at a time according to client behavior—it is not a message replicator or multicast mechanism. If you need to send the same event to two independent MQTT systems, use two outbound endpoints/factories or an explicit replication mechanism with per-target retry/deduplication policies.

### 7.1. Session warning during failover

In MQTT v3, a subscriber using `cleanSession=false` and a stable Client ID can have session state and offline deliveries stored by the broker per its configuration. If a client switches between **two independent brokers that do not share sessions**, you cannot assume offline messages will still be delivered completely.

When designing HA, verify whether the broker cluster synchronizes sessions, subscriptions, retained messages, and in-flight state as required, and test scenarios: broker loss, network partition, reconnect, publishes awaiting ACK, and subscriptions after failover.

### 7.2. Should a TCP URI and a TLS URI be placed together?

For example:

~~~text
tcp://mqtt-a:1883,ssl://mqtt-b:8883
~~~

Paho could encounter endpoints with different security requirements. Such a list **must not serve as an automatic downgrade from TLS to plaintext**. In production, backup endpoints must meet the same security policy; when TLS is required, configure only valid TLS broker URIs and corresponding trust settings.

## 8. Client ID: connection identity is not correlation ID

Several names look similar but serve completely different purposes:

| Identifier | Scope | Example |
| --- | --- | --- |
| **MQTT Client ID** | Identifies the client session connecting to the broker. | `telemetry-inbound-prod-1`. |
| **MQTT topic** | Broker's publish/subscribe namespace. | `sensors/room-17/temperature`. |
| **Message ID / business `eventId`** | Identifies an event or command for deduplication and reconciliation. | `evt-2026-1001`. |
| **Correlation ID** | Links requests, publishes, ACKs, and logs. | `trace-ord-1001`. |
| **Spring bean name** | Identifies a component in the application context. | `mqttClientFactory`, `mqttPublisher`. |

Using the same Client ID on two active MQTT clients can cause **new connections to kick off existing ones**, resulting in continuous reconnect loops and unstable messaging. If the same process has both inbound and outbound adapters, assign separate IDs to each client.

In multi-replica environments, `MQTT_INBOUND_CLIENT_ID` and `MQTT_OUTBOUND_CLIENT_ID` can be derived from deployment identity or instance ordinal. However, a Client ID that **changes on every restart** affects the continuity of an MQTT persistent session. Choose a consistent strategy:

- To **preserve offline subscriptions/sessions for one logical client**: use a stable Client ID across restarts and avoid running two clients with the same ID.
- To **let multiple independent subscribers receive the same messages**: use distinct IDs and understand that each subscription/session has its own policy.
- To **distribute load across a consumer group**: use the broker's shared subscriptions feature when supported by your broker/protocol version, or another queue architecture; do not share a Client ID to simulate competing consumers.

Do not confuse unique Client IDs with **event uniqueness**. If two instances read the same outbox and publish the same `eventId`, subscribers can still receive two separate publications even though each publisher has a unique Client ID.

## 9. Session, QoS, and cleanSession on the factory

In MQTT 3.1.1/Paho v3, `MqttConnectOptions.setCleanSession(...)` controls how the client and broker initialize or retain a session.

| Option | Typical meaning | Best suited for |
| --- | --- | --- |
| `cleanSession=true` | Starts a fresh session on connect; previous subscriptions/session state are not restored as a durable session. | Consumers that do not need offline message retention, or demo publishers. |
| `cleanSession=false` | Enables a more durable session with supporting brokers; requires a stable Client ID. | Subscribers needing a chance to receive certain QoS 1/2 messages upon reconnect per broker policy. |
| QoS 0 | At-most-once delivery at the MQTT layer. | Telemetry where sample loss is acceptable. |
| QoS 1 | At-least-once delivery at the MQTT layer; duplicates possible. | Events needing higher reliability where consumers are idempotent. |
| QoS 2 | Exactly-once handshake at the **MQTT protocol layer**. | Does not replace business transactions on the receiver. |

The factory sets `cleanSession` for clients created with those options. In the sample application, **both inbound and outbound** share the same `cleanSession` option. If inbound requires `cleanSession=false` while outbound prefers `true`, create **two factory beans** with separate options and inject them via `@Qualifier` to make the policy explicit.

`cleanSession=false` **does not guarantee unlimited offline messages**: brokers enforce capacity limits, TTLs, and session policies, and delivery still depends on QoS, existing subscriptions, and broker storage capabilities.

### 9.1. Where is QoS configured?

`MqttConnectOptions` focuses on **connection/session** settings, not selecting business QoS per publication or subscription. QoS is normally configured on the **adapters**:

~~~java
// Inbound subscription QoS
inboundAdapter.setQos(1);

// Default outbound publish QoS
outboundHandler.setDefaultQos(1);
~~~

For outbound, individual messages can override this via `MqttHeaders.QOS`. For inbound, publisher QoS and subscription QoS together determine effective delivery QoS. Do not use `setCleanSession(false)` as a substitute for choosing QoS and implementing idempotency.

## 10. TLS, authentication, and secure broker URLs

In real environments, the connection between application and broker usually requires encryption and server verification.

### 10.1. Switching from TCP to TLS

Configure the address:

~~~properties
app.mqtt.broker-urls=ssl://mqtt.example.internal:8883
~~~

In Paho v3, `ssl://` denotes MQTT over TLS. Trusted certificates, hostname verification, client certificates if the broker uses mTLS, and TLS policies depend on the JVM, Paho, broker, and infrastructure.

For example, providing the JVM with an operations-managed trust store:

~~~text
-Djavax.net.ssl.trustStore=/path/to/truststore.p12
-Djavax.net.ssl.trustStoreType=PKCS12
~~~

The trust store password (if any) must be supplied via secret management or an equivalent security mechanism—**never** committed to a repo or shell history. The path above is illustrative, not a pre-existing file.

**Verify in practice:** a TLS connection can succeed while still requiring verification of certificate chains, hostnames, rotation, and publish/subscribe permissions. Never disable certificate checking or install permissive trust-all managers as a "quick fix" for TLS errors.

### 10.2. Username/password do not replace TLS

~~~java
options.setUserName(username);
options.setPassword(password.toCharArray());
~~~

These are MQTT CONNECT credentials as supported by Paho v3. When using `tcp://` over an untrusted network, credentials and payloads can be exposed. When a broker requires authentication, use **TLS** alongside credentials/ACLs.

Do not log `MqttConnectOptions` in any way that could expose secrets. For systems needing live password or certificate rotation, design lifecycle-controlled restarts/reconnects/bean refreshes rather than assuming updating an environment variable automatically updates an existing open connection.

### 10.3. Topic ACLs and least privilege

Example:

| Client | Permissions it should have | Permissions it should not have |
| --- | --- | --- |
| Inbound telemetry | Subscribe to `sensors/+/temperature`. | Subscribe to unrelated administrative topics. |
| Outbound command | Publish to `devices/+/commands` within authorized device scope. | Publish arbitrarily to another tenant's topics. |
| Audit subscriber | Subscribe to authorized audit topics. | Publish control commands without authorization. |

Broker ACLs determine which topics a principal/client may publish or subscribe to. The application must also validate the tenant/device ID from incoming requests before constructing an MQTT topic. Having a valid URL and credentials is **not enough** to prove a command is authorized for a specific device.

## 11. Timeout, keepalive, and reconnect: three different goals

Several properties sound similar but operate at different stages:

| Property | Typical unit | Effect |
| --- | --- | --- |
| `MqttConnectOptions.setConnectionTimeout(10)` | **Seconds** | Time limit for a single connection attempt in Paho. |
| `MqttConnectOptions.setKeepAliveInterval(30)` | **Seconds** | Controls MQTT keepalive to detect dead connections at the protocol level. |
| `MqttPahoMessageHandler.setCompletionTimeout(5000)` | **Milliseconds** | Wait limit for a publish operation to complete in the handler/client. |
| `MqttPahoMessageDrivenChannelAdapter.setRecoveryInterval(10000)` | **Milliseconds** | Connection recovery/retry interval in the inbound adapter per its API. |
| Business ACK timeout | Defined by the application | Waits for a device/subscriber to confirm command execution, if applicable. |

**Do not equate connection timeout with completion timeout.** For instance, a connection may succeed in 2 seconds while a QoS 1 publish is still delayed by the broker or network. A 5-second completion timeout also does not prove the device executed the command within 5 seconds.

### 11.1. Who manages reconnect?

Paho has automatic reconnect capabilities, and Spring Integration's inbound adapter also includes recovery/lifecycle logic depending on the version. When configuring, establish **one clear connection/recovery strategy**; do not blindly enable every reconnect mechanism simultaneously without testing how they interact.

Scenarios to test:

1. Broker is not running yet at application startup.
2. Broker disconnects while the subscriber is processing messages.
3. Brief network interruption without losing DNS.
4. Credentials are revoked so reconnect never succeeds until config is fixed.
5. Duplicate Client ID caused by deploying two instances simultaneously.
6. Broker failover between two URIs, with or without synchronized sessions.

Policies should include backoff, metrics, alerts, and reconnect rate limits. If an application has thousands of clients, simultaneous reconnects can trigger a "thundering herd"; coordinate rollouts and backoff.

### 11.2. Keepalive is not a business heartbeat

MQTT keepalive indicates that the protocol connection is alive; it does not prove **a sensor is sending valid data** or that a device received the latest command. To detect offline devices, design explicit heartbeats/state events/Last Will messages and timestamps, along with evaluation rules based on real telemetry.

## 12. Using multiple factory beans when policies differ

In multi-purpose systems, sharing a single factory can create unwanted configuration coupling:

~~~mermaid
flowchart TB
    OPT1["Inbound options<br/>cleanSession=false<br/>Stable Client ID"]
    OPT2["Outbound options<br/>cleanSession=true<br/>Separate Client ID"]
    F1["telemetryClientFactory"]
    F2["commandsClientFactory"]
    IN["MQTT inbound adapter"]
    OUT["MQTT outbound handler"]
    OPT1 --> F1 --> IN
    OPT2 --> F2 --> OUT
~~~

Illustrative concept snippet:

~~~java
@Bean("telemetryClientFactory")
MqttPahoClientFactory telemetryClientFactory() {
    var options = new MqttConnectOptions();
    options.setServerURIs(new String[] {
            "ssl://mqtt.example.internal:8883"
    });
    options.setCleanSession(false);
    var factory = new DefaultMqttPahoClientFactory();
    factory.setConnectionOptions(options);
    return factory;
}

@Bean("commandsClientFactory")
MqttPahoClientFactory commandsClientFactory() {
    var options = new MqttConnectOptions();
    options.setServerURIs(new String[] {
            "ssl://mqtt.example.internal:8883"
    });
    options.setCleanSession(true);
    var factory = new DefaultMqttPahoClientFactory();
    factory.setConnectionOptions(options);
    return factory;
}
~~~

This is an **illustrative snippet**, not a replacement for complete TLS/credentials configuration, and must not share bean names with the section 6 example without reorganizing the context.

When two beans of type `MqttPahoClientFactory` exist, Spring injection becomes ambiguous. Use `@Qualifier("telemetryClientFactory")` or `@Qualifier("commandsClientFactory")` on the adapter bean methods. Also prevent duplicate Client IDs across adapters even when they use different factories.

Reuse a safe helper to build `MqttConnectOptions` so secret/TLS settings are not copied inconsistently across classes, while preserving adapter-specific session/reconnect policies as needed.

## 13. Handling connection errors and message state

A misconfigured client factory can prevent adapters from connecting, yet even when the broker is healthy, message delivery failures still happen.

~~~mermaid
flowchart TD
    CFG["Broker URI / auth / TLS"]
    CLIENT{"Paho connect succeeded?"}
    ADAPTER["Inbound subscribe / outbound publish"]
    CH["MessageChannel"]
    BUSINESS["Validate / DB / HTTP / Kafka"]
    ERROR["Error flow / retry / quarantine / outbox"]
    CFG --> CLIENT
    CLIENT -->|"Yes"| ADAPTER --> CH --> BUSINESS
    CLIENT -->|"No"| ERROR
    ADAPTER -. "publish/subscription error" .-> ERROR
    BUSINESS -. "business error" .-> ERROR
~~~

| Error type | Where it arises | Appropriate measure |
| --- | --- | --- |
| Invalid URI | Parsing options or at connect time. | Validate URI/scheme and test config before deployment. |
| Wrong DNS/firewall/port | TCP/TLS connection. | Check network routing, DNS, and broker health. |
| Invalid TLS trust/hostname | TLS handshake. | Fix certificate/trust configuration; never disable verification. |
| Wrong username/password or ACL | CONNECT/SUBSCRIBE/PUBLISH. | Fix secrets/permissions and fail explicitly; avoid endless retries on bad config. |
| Duplicate Client ID | During connection establishment. | Generate distinct IDs or ensure only one active client per session. |
| Publish completion timeout | Outbound handler/client. | Treat outcome as uncertain; retry using idempotency and outbox. |
| Inbound receives invalid schema payload | Downstream converter/validator. | Quarantine and report data error; do not blame the broker URL. |
| Downstream DB/HTTP unavailable | After `MessageChannel`. | Retry/transact at the business layer, not merely by reconnecting MQTT. |

**Message errors cannot be solved merely by changing the broker URL.** When the application has already received a message from the broker and the DB write fails, MQTT reconnection is completely irrelevant. Design error channels, retries, DLQ/quarantine, idempotency, and acknowledgment policies at the appropriate endpoints.

### 13.1. MQTT QoS is not a business transaction

- With MQTT QoS 1, the broker/client may redeliver messages causing **duplicate delivery**.
- With QoS 2, exactly-once is defined at the **MQTT protocol delivery** layer, excluding database transactions or device actuation.
- With retained messages, new subscribers may receive an **old state snapshot**, not necessarily a fresh event.
- If an outbound publish finishes but the application crashes before updating its outbox, the next run may republish the same event ID.

Therefore, payloads should carry a stable `eventId`/`commandId`; downstream uses unique constraints/idempotency and tracks processed state. When the broker does not return an ACK in time, never blindly re-issue critical commands without checking prior results.

## 14. Lifecycle of the factory and adapters in Spring

`MqttPahoClientFactory` is a bean holding rules for creating MQTT clients; the factory itself **has no active subscriptions** until an inbound adapter uses it. Nor does an outbound adapter publish merely because the factory exists.

In operation, understand these stages:

1. **Bean creation:** Spring initializes options, factory, and adapters. Missing or invalid configuration can be caught early here if validated.
2. **Endpoint startup:** the inbound adapter can connect and subscribe via `SmartLifecycle`/framework management. The outbound client may connect when the handler starts operating.
3. **Message processing:** broker delivery → adapter → channel → flow, or flow → handler → broker; errors can occur at any stage.
4. **Connection recovery:** applies recovery/reconnect policies, potentially re-establishing subscriptions depending on session state.
5. **Shutdown:** stops accepting new requests, gives in-flight work a chance to finish, and releases client resources.

If a broker URI or credential changes in deployment config, **already-created beans do not automatically update** just because a property file changed. A controlled refresh/restart or explicit reconfiguration mechanism is usually required, verifying sessions/reconnection and avoiding data loss.

### 14.1. Required monitoring

Key operational signals:

- Connected/disconnected state, reconnect count, downtime duration.
- Active broker URI—but **never log passwords, tokens, or private keys**.
- Publish attempts, publish successes/timeouts, subscribe failures, and ACL rejections.
- Inbound/outbound message counts, processing latency, and queued message counts.
- Duplicate/retry counts by `eventId`, outbox/quarantine state.
- Alerts on duplicate Client IDs or frequent broker switching.

Connection observability is helpful, but it is not the final measure of business processing. For example, a dashboard showing `MQTT connected = true` does not guarantee that the DB event consumer is working.

## 15. Testing factory beans without a broker

Because `MqttConnectOptions` and `MqttPahoClientFactory` are standalone Spring beans, configuration can be tested **without opening an MQTT connection**. Avoid booting the entire `MqttFactoryApplication` in unit tests if doing so causes the inbound adapter to auto-connect to a broker.

Add the test dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Create `MqttConnectionConfigurationTest.java` in package `demo.mqttfactory`:

~~~java
package demo.mqttfactory;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.eclipse.paho.client.mqttv3.MqttConnectOptions;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.integration.mqtt.core.MqttPahoClientFactory;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = MqttConnectionConfiguration.class)
@TestPropertySource(properties = {
        "app.mqtt.broker-urls=tcp://mqtt-a:1883,tcp://mqtt-b:1883",
        "app.mqtt.connection-timeout-seconds=8",
        "app.mqtt.keep-alive-seconds=45",
        "app.mqtt.clean-session=false",
        "app.mqtt.username=test-client",
        "app.mqtt.password=test-secret"
})
class MqttConnectionConfigurationTest {

    @Autowired
    MqttConnectOptions options;

    @Autowired
    MqttPahoClientFactory factory;

    @Test
    void createsOptionsAndClientFactoryWithoutNetwork() {
        assertNotNull(factory);
        assertArrayEquals(
                new String[] {
                        "tcp://mqtt-a:1883",
                        "tcp://mqtt-b:1883"
                },
                options.getServerURIs());
        assertEquals(8, options.getConnectionTimeout());
        assertEquals(45, options.getKeepAliveInterval());
        assertEquals("test-client", options.getUserName());
        assertTrue(!options.isCleanSession());
    }
}
~~~

What this test proves:

- Spring binds `app.mqtt.*` values into the options factory method.
- Both broker URIs are parsed/trimmed and passed into Paho.
- Timeout/keepalive/clean session are applied to options in the right units.
- The factory bean is created without requiring a running broker.

**This test does not prove an MQTT connection succeeds.** It does not verify DNS, TLS, production secrets, ACLs, subscriptions, failover, publishing, or reconnection. Those require integration tests with a real broker.

### 15.1. Testing invalid configurations

Add fail-fast tests for:

1. Empty `app.mqtt.broker-urls` or containing only commas/whitespace.
2. URIs with unsupported schemes in this demo such as `http://...`.
3. Negative connection timeout or invalid keepalive—validate against policy before constructing options.
4. Production profile missing secrets or missing TLS.
5. Duplicate inbound and outbound Client IDs; detect via a validation bean or startup integration test.
6. Configuration with two factories of the same type missing `@Qualifier` on adapters.

Never put production passwords into source or test logs. The password in the example test is only a dummy string illustrating property binding.

## 16. End-to-end connectivity testing with a broker

Once a test broker is running and the MQTT CLI is installed, a simple manual test is:

**Terminal A — subscribe to topic:**

~~~bash
mosquitto_sub -h localhost -p 1883 \
  -i demo-cli-subscriber-1 \
  -t 'devices/+/commands' -v
~~~

**Terminal B — publish a command:**

~~~bash
mosquitto_pub -h localhost -p 1883 \
  -i demo-cli-publisher-1 \
  -t 'devices/demo-1/commands' \
  -q 1 \
  -m '{"commandId":"cmd-1001","action":"TURN_ON"}'
~~~

Run the Spring Boot application against the same environment's broker URI. You can publish from `DeviceCommandPublisher` to test **Spring outbound handler → broker**. To test the **Spring inbound adapter**, publish a message to the `sensors/+/temperature` topic filter.

For example:

~~~bash
mosquitto_pub -h localhost -p 1883 \
  -i demo-cli-telemetry-1 \
  -t 'sensors/room-17/temperature' \
  -q 1 \
  -m '{"eventId":"evt-1001","celsius":26.5}'
~~~

The CLI only works if the broker permits these example connections and Mosquitto tools are installed. If the broker requires TLS/credentials, pass the appropriate flags and certificates rather than disabling security.

### 16.1. Essential test matrix

| Test | How to run | Expected observation |
| --- | --- | --- |
| Single valid broker URI | Connect to a running test broker. | Adapter starts and processes subscriptions/publications properly. |
| Unreachable URI | Point to wrong host/port. | Connection failure is recorded; do not treat messages as handled successfully. |
| Two fallback broker URIs | Use a test cluster supporting failover. | Client tries appropriate endpoint and subscriptions/side effects are re-verified. |
| Invalid TLS certificate | Use an untrusted broker cert. | Handshake fails properly; never "bypass TLS". |
| Wrong publish/subscribe ACL | Use a principal lacking topic rights. | Error is surfaced; messages are not silently dropped. |
| Duplicate Client ID | Have two clients use the same ID. | Observe connection contention; apply proper identity strategy. |
| `cleanSession=false` | Disconnect/reconnect subscriber with a stable ID. | Verify offline delivery per broker QoS/session policy without guessing. |
| Broker restart | Restart broker while transferring messages. | Recovery, reconnect, redelivery/duplicates behave per contract. |
| Downstream failure | Handler receives MQTT, then DB fails. | Verify error flow/retry or quarantine, not just broker health. |
| High message burst | Publish faster than handler throughput. | Queue/backpressure are measured; memory/threads are not exhausted. |

To confirm full system correctness, reconcile message counts at the broker, Spring channels, and final state in the database/target device. Checking only that the MQTT client says "connected" is insufficient.

## 17. Common errors and troubleshooting

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Cannot connect even though broker is running. | Wrong host/port, `localhost` pointing to another container, firewall. | Check DNS, network namespace, and broker listener. |
| Broker URI reported invalid. | Confusing `https://`/`mqtt://` with Paho TCP/TLS URIs. | Use a client-supported scheme; distinguish URI from topic. |
| TLS handshake failure. | Missing CA/truststore, wrong hostname or certificate chain. | Fix trust configuration; never disable certificate verification. |
| Unauthorized on connect. | Wrong username/password or changed broker policy. | Update secrets/permissions securely and restart/reconnect safely. |
| Connects but does not subscribe. | Wrong topic ACL, wrong filter, inbound adapter not started. | Check subscriptions, broker logs, and adapter lifecycle. |
| Publish does not reach device. | Wrong topic, publisher ACL, subscriber offline, QoS/session policy. | Verify actual topic, broker delivery, and dedicated business ACK. |
| Two instances disconnect repeatedly. | Duplicate Client ID. | Assign unique identifiers or manage stable active sessions. |
| Offline messages missing after failover. | Two brokers do not share MQTT sessions. | Review cluster/session topology and test with a real broker. |
| Multiple URLs set, yet messages are not replicated. | `setServerURIs` is not a fan-out publisher. | Use replication or two separate outbound flows for multiple targets. |
| Publish times out, yet broker may have received it. | MQTT ACK lost or delayed. | Avoid blind retries; use outbox and idempotency by event ID. |
| Environment variable changed, yet connection unchanged. | Beans/options were already created earlier. | Perform a controlled restart/reload and verify state. |
| MQTT connected fine, yet no data in DB. | Validation/downstream error, unhandled error channel. | Inspect the full `IntegrationFlow`, transactions, and retries. |

## 18. Practice exercise: designing an MQTT connection factory for two environments

**Scenario:** a system receives MQTT telemetry from devices and publishes control commands. Development uses a local broker; production uses a TLS broker cluster with two endpoints.

Requirements:

1. Create an `MqttConnectOptions` bean from `app.mqtt.broker-urls`, timeout, keepalive, clean session, and credentials.
2. Declare `DefaultMqttPahoClientFactory` using those options, injected into one inbound adapter and one outbound handler.
3. Define distinct Client IDs for inbound/outbound, detecting duplicate IDs at startup if both adapters ever share an ID.
4. Development uses `tcp://localhost:1883`; production uses only `ssl://mqtt-a:8883,ssl://mqtt-b:8883` with a proper truststore.
5. Supply TLS/username/password via secrets; never commit passwords to `application.properties`.
6. Inbound subscribes to `sensors/+/temperature` at QoS 1, sends to `mqtt.inbound`, and validates JSON.
7. Outbound publishes to `devices/<deviceId>/commands` at QoS 1, `retained=false`, with payload carrying `commandId`.
8. Simulate the first broker URI being unreachable, observe fallback, and verify session/subscription behavior against a broker cluster.
9. Test two replicas with the same Client ID, then fix the identity strategy and explain the impact on persistent sessions.
10. Run tests for duplicate handling, late broker ACKs, DB failures, and restarts to prove application recovery behavior.

**Completion criteria:** connection settings are decoupled from flows, URIs and schemes are valid, Client IDs/sessions are clear, TLS/ACLs are correct, reconnects are observable, and tests prove broker delivery is not mistaken for business completion.

## 19. Self-check questions

1. How does `MqttPahoClientFactory` differ from `MqttConnectOptions`?
2. Does merely creating the factory bean cause an MQTT client to subscribe or publish?
3. How does a Broker URI differ from an MQTT topic?
4. Why can `tcp://localhost:1883` be wrong inside Docker/Kubernetes?
5. What does `ssl://` specify, and what else must be checked for a secure connection?
6. Does `setServerURIs` automatically publish the same message to all brokers?
7. When failing over to a backup broker that does not share sessions, what data risks arise?
8. Why do inbound and outbound sharing a factory still need two Client IDs?
9. What problem occurs with `cleanSession=false` if the Client ID changes on every restart?
10. How do connection timeout and completion timeout differ?
11. Does keepalive prove that a sensor is functioning properly?
12. When credentials change, does a running factory bean automatically reload options?
13. Does an MQTT QoS 2 publication guarantee the database writes exactly once?
14. Should `retained=true` be used for a one-time device turn-on command?
15. What does a brokerless factory unit test verify, and what does it not verify?
16. If the application receives an MQTT message and then the DB fails, will reconnecting the broker solve it?
17. When should two separate factories be used instead of one shared factory?
18. How do you restrict a publisher from generating arbitrary topics from an untrusted header?

**Hint:** The factory builds clients from connection options; the broker URI is for connecting, while topics are for publishing/subscribing; Client IDs/sessions govern broker-side state; downstream errors and duplicate side effects must be handled outside the connection layer.

## 20. Conclusion

**MQTT client factory and broker URL** form the connectivity foundation for MQTT in Spring Integration. `MqttConnectOptions` defines broker URIs, timeouts, keepalive, sessions, and credentials; `DefaultMqttPahoClientFactory` supplies those settings to `MqttPahoMessageDrivenChannelAdapter` or `MqttPahoMessageHandler`. Adapters then handle subscribing/publishing and integrating with `MessageChannel`/`IntegrationFlow`.

When implementing **SPRING_INTEGRATION_ADAPTERS** with MQTT, cleanly separate **connection configuration**, **client/session identity**, **topic/payload/header contracts**, and **business success**. Multiple broker URLs provide endpoint selection for connection failover, not multicast or transactions; TLS/ACLs must be verified; and retries, outboxes, idempotency, and end-to-end testing determine whether the system recovers safely when the broker, application, or downstream dependencies fail.
