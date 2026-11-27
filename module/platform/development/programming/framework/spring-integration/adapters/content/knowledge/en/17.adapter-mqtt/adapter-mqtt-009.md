# Subscription patterns and wildcard topics

## 1. Problem statement and learning objectives

In an IoT system, a Spring Integration application may need to receive data from thousands of devices:

~~~text
tenants/tenant-a/devices/device-17/telemetry
tenants/tenant-a/devices/device-21/telemetry
tenants/tenant-a/devices/device-35/telemetry
...
~~~

Creating a separate MQTT subscription for **each device** causes the number of topic filters and operational configuration to grow rapidly. MQTT solves this with **subscription topic filters**: a subscriber registers a pattern such as `tenants/tenant-a/devices/+/telemetry`, and the broker matches incoming PUBLISH **topic names** automatically.

However, wildcard topics are easily misunderstood. `+` is not an arbitrary regex; `#` can only appear at the final level; and a PUBLISH must never use wildcards like a subscription. More importantly, broad filters are **not an authentication or authorization mechanism**: if a subscription crosses tenant boundaries, the application can receive unauthorized data.

This lesson, **"Subscription patterns and wildcard topics,"** belongs to the **Adapter MQTT** chapter of the **SPRING_INTEGRATION_ADAPTERS** module. The module focuses on integrating external systems via inbound/outbound adapters, gateways, pollers, and `MessageChannel`; practicing with files, SFTP, HTTP, JMS, AMQP, Kafka, and databases while managing message contracts, errors, and connection lifecycles.

After completing this lesson, learners will be able to:

1. Distinguish **MQTT topic names**, **topic filters**, **broker URLs**, **Spring MessageChannels**, and message headers.
2. Apply the exact syntax of `+` (single-level) and `#` (multi-level) wildcards.
3. Explain edge cases such as empty topic levels, topics starting with `$`, case sensitivity, and overlapping filters.
4. Configure `MqttPahoMessageDrivenChannelAdapter` to subscribe to one or more topic filters.
5. Use `MqttHeaders.RECEIVED_TOPIC` to determine the **actual received topic**, without confusing it with the subscribed filter.
6. Combine `IntegrationFlow` with validation of topic, tenant, device ID, schema, error handling, and idempotency.
7. Understand subscription QoS, Client IDs, `cleanSession`, reconnection, and the effects of changing topics at runtime.
8. Test matching with case matrices, brokerless unit tests, and live experiments against an MQTT broker.
9. Choose when to use topic wildcards, Spring routers, shared subscriptions, or multiple inbound endpoints.

**Key takeaway:** a topic filter selects **which publications the broker forwards to the MQTT client**. Once received, the application still must verify the **concrete topic, identity, access permissions, payload schema, and business state** before processing.

## 2. Architecture: broker filters topics first, Spring processes afterward

~~~mermaid
flowchart LR
    D1["Publisher device-17"]
    D2["Publisher device-21"]
    D3["Publisher device-35"]
    B[("MQTT broker<br/>topic matching")]
    SUB["Paho subscriber<br/>filter: tenants/tenant-a/devices/+/telemetry"]
    AD["MqttPahoMessageDrivenChannelAdapter"]
    CH["mqtt.telemetry.in<br/>MessageChannel"]
    FLOW["IntegrationFlow<br/>validate topic + parse JSON"]
    DB[("Database / downstream")]
    D1 -->|"PUBLISH concrete topic"| B
    D2 -->|"PUBLISH concrete topic"| B
    D3 -->|"PUBLISH concrete topic"| B
    B -->|"DELIVER per filter and QoS"| SUB
    SUB --> AD --> CH --> FLOW --> DB
~~~

Each layer has a dedicated role:

| Component | Example | Responsibility |
| --- | --- | --- |
| Broker URI | `tcp://localhost:1883` | Where Paho connects to the MQTT broker. |
| Publish topic name | `tenants/tenant-a/devices/device-17/telemetry` | Protocol address of **one specific PUBLISH**. |
| Subscription topic filter | `tenants/tenant-a/devices/+/telemetry` | Pattern the broker uses to decide whether to deliver a PUBLISH to a subscriber. |
| Spring MessageChannel | `mqtt.telemetry.in` | Internal path for the adapter to hand Spring messages into a flow. |
| Received topic header | `MqttHeaders.RECEIVED_TOPIC` | The **actual** topic of the delivered PUBLISH, e.g., `.../device-17/telemetry`. |
| Business identity | `tenantId`, `deviceId`, `eventId` | Data that must be authenticated/validated and used for deduplication. |

A single Spring channel can accept messages from thousands of MQTT topics without creating one channel per device. Conversely, one MQTT client can subscribe to multiple filters and still feed them into a single Spring channel.

### 2.1. MQTT inbound is message-driven

`MqttPahoMessageDrivenChannelAdapter` registers MQTT subscriptions and receives messages via client callbacks. It does **not** need a `@Poller` to ask the broker periodically whether messages exist. A poller is only required if a **later internal step** pulls messages from a `PollableChannel` like `QueueChannel`.

### 2.2. Topic filters do not determine Java payload types

The broker matches topics; it does not know whether payloads are JSON, protobuf, or plain text. `DefaultPahoMessageConverter` converts byte payloads into `String` or `byte[]` as configured, and Spring Integration handlers/transformers then decode schemas.

Never infer that a `.../telemetry` filter forces every publisher to send valid `TemperatureReading` data. Data-format contracts and device permissions must be enforced by the application.

## 3. Topic names and topic filters: distinguish them from the start

A **Topic name** is the string attached to a PUBLISH. It consists of levels separated by `/`:

~~~text
tenants / tenant-a / devices / device-17 / telemetry
   1        2         3         4          5
~~~

A **Topic filter** is the string a subscriber passes in SUBSCRIBE. It may contain wildcards:

~~~text
tenants/tenant-a/devices/+/telemetry
tenants/tenant-a/devices/#
tenants/tenant-a/#
~~~

| Operation | Valid | Invalid |
| --- | --- | --- |
| PUBLISH | `tenants/tenant-a/devices/device-17/telemetry` | `tenants/tenant-a/devices/+/telemetry` |
| PUBLISH | `devices/device-17/state` | `devices/#` |
| SUBSCRIBE | `tenants/tenant-a/devices/+/telemetry` | `devices/room#` |
| SUBSCRIBE | `devices/#` | `devices/#/state` |

**Rule:** wildcards `+` and `#` are used in **topic filters**; a PUBLISH **topic name** must never contain these wildcards.

### 3.1. Topic filters are not regular expressions

MQTT filters do not recognize `*`, `?`, regex groups, `[0-9]+`, or backslash escapes the way Java regex does.

~~~text
MQTT:
  devices/+/state         ✓ single-level
  devices/#               ✓ multi-level

Not valid MQTT filters with the intended meaning:
  devices/*/state
  devices/(device-17|device-21)/state
  devices/[0-9]+/state
~~~

If you must select a set of devices according to complex database rules, subscribe to a reasonably narrow valid filter and then **filter further inside Spring Integration**; however, broker ACLs must still ensure the client can only receive authorized topics.

### 3.2. Topic names are case-sensitive

~~~text
devices/device-17/state
Devices/device-17/state
devices/Device-17/state
~~~

These three strings are **three distinct MQTT topic names**. If your contract standardizes on lowercase, normalize consistently when issuing identities and constructing topics—never merely lowercase at the subscriber after authorizing against another casing.

## 4. Plus wildcard (+): exactly one topic level

`+` is the **single-level wildcard**. It must occupy an **entire level** of the topic filter on its own, bounded by `/` or string boundaries.

Example:

~~~text
Filter: devices/+/state

✓ devices/device-17/state
✓ devices/device-21/state
✓ devices//state
✗ devices/device-17/metrics/state
✗ devices/state
✗ devices/device-17/state/extra
~~~

`devices//state` has an empty topic level between two `/` separators. MQTT permits empty levels and single-level wildcards match them. However, in business systems, an **empty device ID is usually invalid**; Spring handlers must validate and reject it.

### 4.1. Multiple + wildcards in one filter

~~~text
Filter: tenants/+/devices/+/telemetry

✓ tenants/tenant-a/devices/device-17/telemetry
✓ tenants/tenant-b/devices/device-21/telemetry
✗ tenants/tenant-a/devices/device-17/state
✗ tenants/tenant-a/devices/device-17/extra/telemetry
~~~

This filter can receive **multi-tenant** data, so it must not be used by a service restricted to `tenant-a` unless the broker principal lacks read access to `tenant-b`. Each `+` represents **one level**, never a multi-level path containing `/`.

### 4.2. Misplaced + wildcards

~~~text
devices/device+/state        ← invalid: + does not occupy an entire level
devices/+suffix/state        ← invalid
devices/pre+fix/state        ← invalid
devices/+/state              ← valid
+/devices/+/telemetry        ← syntactically valid; see $ exception in section 6
~~~

To match topics whose device ID starts with `device-`, you cannot write `device-+` as a suffix wildcard. Subscribe to `devices/+/state` and filter IDs with Java regex in the business layer, or design the hierarchy so the prefix is its own level.

## 5. Hash wildcard (#): zero or more levels from the end

`#` is the **multi-level wildcard**. It must be the **final level** and occupy that entire level. `#` alone is valid; `a/#` matches `a`, `a/`, and deeper subtrees.

~~~text
Filter: devices/#

✓ devices
✓ devices/
✓ devices/device-17
✓ devices/device-17/state
✓ devices/device-17/sensors/temperature
✗ other/devices/device-17/state
~~~

Unlike `+`, `#` can match **zero remaining levels**, so `devices/#` matches the topic `devices` even without a trailing slash.

### 5.1. Placement rules for #

| Filter | Valid? | Explanation |
| --- | --- | --- |
| `#` | Yes | Matches ordinary topics at any depth (except topics starting with `$`). |
| `devices/#` | Yes | Matches `devices` and all topics beneath it. |
| `tenants/tenant-a/#` | Yes | Matches the topic tree of `tenant-a`. |
| `devices/#/state` | **No** | `#` is not at the final level. |
| `devices/room#` | **No** | `#` does not stand alone as a level. |
| `devices/#extra` | **No** | Other characters share the level with `#`. |
| `#/#` | **No** | First `#` is not at the final level. |

`devices/#` can match state, telemetry, commands, and other branches all at once. If a service only needs telemetry, use the narrower `devices/+/telemetry` filter or a hierarchy separating tenants and data kinds cleanly.

### 5.2. Combining + and #

~~~text
Filter: tenants/tenant-a/devices/+/sensors/#

✓ tenants/tenant-a/devices/device-17/sensors
✓ tenants/tenant-a/devices/device-17/sensors/
✓ tenants/tenant-a/devices/device-17/sensors/temperature
✓ tenants/tenant-a/devices/device-17/sensors/environment/humidity
✗ tenants/tenant-b/devices/device-17/sensors/temperature
✗ tenants/tenant-a/devices/device-17/commands
~~~

This filters all sensor branches under one tenant while keeping a single device ID level, rather than subscribing with an overly broad root wildcard.

## 6. Topics starting with $: an important exception

In MQTT, topic names starting with `$` are typically reserved for **broker/system topics** or special conventions. MQTT 3.1.1 matching rule: filters beginning with `#` or `+` **do not match** topic names whose first character is `$`.

Examples:

| Subscription filter | Published topic | Matches? |
| --- | --- | --- |
| `#` | `devices/device-17/state` | Yes |
| `#` | `$SYS/broker/uptime` | **No** |
| `+/broker/uptime` | `$SYS/broker/uptime` | **No** |
| `$SYS/#` | `$SYS/broker/uptime` | Syntactically yes; broker ACL may deny. |
| `$SYS/+/uptime` | `$SYS/broker/uptime` | Syntactically yes; broker may use other topics. |

**Do not think `#` means "literally every topic."** To observe `$SYS` on a test broker, explicitly subscribe to a filter starting with `$SYS` with proper permissions; `$SYS` topic names, support, and payloads are not a uniform standard across brokers.

### 6.1. Topics with a leading slash

The topic name `/devices/device-17` is structurally valid in MQTT and has an **empty leading level**. It is different from `devices/device-17`. The filters `/devices/#` and `devices/#` are not equivalent.

To reduce mistakes, business systems should standardize on topics without leading or trailing slashes unless there is a clear reason; however, do not claim the MQTT protocol forbids them.

### 6.2. Empty levels and business IDs

Topics like `devices//state` are valid for matching, yet the device ID is an empty string. Spring handlers must reject them per business policy. Never treat the broker's ability to match a wildcard as proof that IDs were validated.

### 6.3. Unicode characters and length

Topic names/filters are UTF-8 strings within protocol length limits, not ASCII-only. Applications should enforce canonical naming, restrict IDs with allowlists across languages/devices, and verify length **in UTF-8 bytes** where required.

Do not invent ad-hoc URL encoding or replace `/` inside a topic without an agreed contract: it can make publishers and subscribers match differently or cause ID collisions.

## 7. Topic filter matching matrix

The table below follows MQTT matching rules **without** factoring in broker ACLs or broker-specific extensions.

| Filter | Topic name | Matches? | Why? |
| --- | --- | --- | --- |
| `sensors/+/temperature` | `sensors/device-17/temperature` | Yes | `+` matches the single level `device-17`. |
| `sensors/+/temperature` | `sensors/device-17/room/temperature` | No | Extra level `room` present. |
| `sensors/+/temperature` | `sensors//temperature` | Yes | Empty middle level is still one level. |
| `sensors/#` | `sensors` | Yes | `#` matches zero remaining levels. |
| `sensors/#` | `sensors/device-17/temperature` | Yes | `#` matches multiple levels. |
| `sensors/+/+#` | `sensors/device-17/temperature` | **Invalid filter** | `#` must occupy a level by itself. |
| `devices/+/state` | `devices/device-17/state/last` | No | Extra trailing level. |
| `tenants/tenant-a/#` | `tenants/tenant-b/devices/17/state` | No | Different tenant prefix. |
| `#` | `$SYS/broker/uptime` | No | Leading `$` exception. |
| `$SYS/#` | `$SYS/broker/uptime` | Yes | Explicit `$SYS` prefix. |
| `devices/#` | `devices/` | Yes | `#` matches the trailing level. |
| `devices/+` | `devices` | No | Missing `/…` level required by `+`. |

Turn such matrices into **contract tests** against a real broker for specialized/edge cases. A hand-written Java regex simulating MQTT is not final proof the broker behaves identically, especially with shared subscriptions or vendor extensions.

## 8. Overlapping subscription filters: duplicates can arrive

Suppose a single MQTT client subscribes to two filters:

~~~text
sensors/+/temperature
sensors/#
~~~

A publication to `sensors/device-17/temperature` matches **both**. Under MQTT 3.1.1, the server must deliver according to matching subscriptions and granted QoS levels; under permitted conditions it **may deliver extra copies** across overlapping subscriptions. Therefore, **never design business handlers assuming "one PUBLISH always triggers one callback"** when overlapping subscriptions exist.

### 8.1. QoS with overlapping filters

Suppose:

~~~text
SUBSCRIBE sensors/+/temperature, QoS 1
SUBSCRIBE sensors/#,             QoS 0

PUBLISH sensors/device-17/temperature, QoS 1
~~~

One publication matches multiple subscriptions. Delivery QoS follows protocol/broker rules for those subscriptions; typically the highest granted QoS among matching subscriptions applies, yet never assume every broker/extension guarantees a single copy at one fixed QoS.

To handle this safely:

1. Avoid creating redundant overlapping filters when unnecessary.
2. Include `eventId` in payloads for idempotency.
3. Test overlapping filters with mixed QoS against your real broker.
4. Observe duplicate deliveries and ensure side effects do not repeat.
5. When separating business branches, use one narrow subscription plus a **Spring router** instead of organizing business routing via unpredictable overlapping filters.

### 8.2. Multiple distinct MQTT clients

Two clients with different Client IDs subscribing to the same normal filter **each receive** matching publications. This is **per-subscriber fan-out**, not competing consumers like a queue.

To distribute work across workers so only one group member handles each message, use **shared subscriptions** if supported by your broker/MQTT version, or an appropriate queuing infrastructure. Never use **duplicate Client IDs** to simulate competing consumers: the new client will kick the old client off, causing a reconnect loop.

## 9. Subscription QoS and PUBLISH QoS

MQTT has QoS on **two legs**:

~~~mermaid
flowchart LR
    PUB["Publisher QoS=1"]
    B[("MQTT broker")]
    SUB["Subscriber SUBSCRIBE QoS=0"]
    APP["Spring Integration handler"]
    PUB -->|"PUBLISH QoS 1 + PUBACK"| B
    B -->|"Delivery QoS capped by subscription"| SUB --> APP
~~~

A publisher may PUBLISH at QoS 1, yet if the subscriber subscribes at QoS 0, the broker → subscriber leg **never upgrades to QoS 1**. When two subscriptions overlap, consult section 8 rather than a single simplified formula.

| Publisher QoS | Subscriber QoS (single filter) | Typical delivery QoS |
| ---: | ---: | ---: |
| 0 | 0 | 0 |
| 0 | 1 | 0 |
| 1 | 0 | 0 |
| 1 | 1 | 1 |
| 1 | 2 | 1 |
| 2 | 1 | 1 |
| 2 | 2 | 2 |

Spring Integration's inbound adapter can configure:

~~~java
adapter.setQos(1);
~~~

This sets the **subscription QoS** for filters managed by the adapter per its API, not the default QoS for outbound publications. Outbound `MqttPahoMessageHandler` uses `setDefaultQos(1)` or `MqttHeaders.QOS` in the opposite direction.

### 9.1. QoS does not replace database deduplication

- QoS 0: at-most-once at the protocol layer; messages may be lost.
- QoS 1: at-least-once at the protocol layer; redeliveries can occur.
- QoS 2: exactly-once **within MQTT protocol delivery**, not spanning a DB transaction or device actuation.
- Overlapping subscription filters or applications re-publishing a new event with the same `eventId` can also cause business duplicates.

Therefore use stable `eventId`/`commandId` values and idempotent handlers for important data.

## 10. Sessions, re-subscribing, and reconnecting

Topic filters are not just startup strings; they interact with **MQTT Client IDs** and **sessions**.

### 10.1. cleanSession=true

In MQTT 3.1.1, a `cleanSession=true` client requests a clean session. On reconnect, the application/inbound adapter must ensure required subscriptions are re-established. Never assume that because a bean exists in the Spring context, the broker still keeps subscriptions from the prior connection.

### 10.2. cleanSession=false

`cleanSession=false` lets the broker retain sessions/subscriptions and certain QoS 1/2 messages per MQTT rules and storage policies. To benefit from it:

1. The subscriber must actually subscribe to the topic filter successfully.
2. The Client ID must remain **stable** across reconnects/restarts.
3. Two active clients must never share the same Client ID.
4. The broker must support retaining sessions/offline messages within configured bounds.
5. On failover to another broker, the cluster must hold matching session state.

**Persistent sessions are not retained messages:** sessions can hold subscription messages while a subscriber is offline; retained holds the latest per-topic snapshot for future subscribers. The two mechanisms complement rather than replace each other.

### 10.3. Last Will is not a subscription filter

A Last Will is a publication emitted by the broker to a specific Will Topic when an MQTT client disconnects abnormally. A Spring observer can subscribe to `devices/+/availability` to receive Wills from many devices, yet each **device client** must declare its own Will at CONNECT. Spring's filter does not create Wills for devices.

## 11. Spring Boot example: tenant-scoped telemetry subscription pattern

Build an application receiving JSON temperature readings from:

~~~text
tenants/tenant-a/devices/{deviceId}/telemetry
~~~

Instead of subscribing per device, one `MqttPahoMessageDrivenChannelAdapter` uses the topic filter:

~~~text
tenants/tenant-a/devices/+/telemetry
~~~

The Spring flow will:

1. Receive the MQTT message as JSON `String`.
2. Read the **actual topic** from `MqttHeaders.RECEIVED_TOPIC`.
3. Extract `deviceId` from a topic matching the expected shape and belonging to `tenant-a`.
4. Parse the payload via Jackson into `TemperatureReading`.
5. Cross-check the payload `deviceId` against the topic.
6. Record accepted events in a test sink (replaceable with DB/HTTP/JMS/AMQP/Kafka handlers).
7. Reject invalid data; production should route it to an error flow/quarantine.

The example requires Java 17+ and Spring Boot/Spring Integration MQTT using a compatible Eclipse Paho MQTT v3 API.

### 11.1. Maven dependencies

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

Let the Spring Boot BOM manage aligned dependency versions. Do not mix `org.eclipse.paho.client.mqttv3.MqttConnectOptions` with the MQTT v5 API expecting the example to run unchanged.

### 11.2. Source layout

~~~text
src/main/java/demo/mqttfilters/
    MqttFiltersApplication.java
    TemperatureReading.java
    TopicFilterValidator.java
    AcceptedTelemetry.java
    TelemetrySink.java
    TopicFilterFlowConfiguration.java
    MqttFilterTransportConfiguration.java

src/main/resources/
    application.properties

src/test/java/demo/mqttfilters/
    TopicFilterFlowTest.java
~~~

All classes belong to package `demo.mqttfilters`. Java classes with `public` modifier must reside in matching filenames; others may stay package-private for direct testing.

### 11.3. Application and properties

~~~java
package demo.mqttfilters;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MqttFiltersApplication {

    public static void main(String[] args) {
        SpringApplication.run(MqttFiltersApplication.class, args);
    }
}
~~~

`application.properties`:

~~~properties
app.mqtt.broker-url=${MQTT_BROKER_URL:tcp://localhost:1883}
app.mqtt.client-id=${MQTT_CLIENT_ID:tenant-a-telemetry-subscriber-1}
app.mqtt.tenant-id=tenant-a
~~~

The demo assumes a local broker at `localhost:1883` with subscribe permissions on the topic. Spring Boot **does not start an MQTT broker**. Production requires TLS, credentials/secret management, broker topic ACLs, and a unique Client ID per active subscriber.

### 11.4. DTO and business validation

~~~java
package demo.mqttfilters;

record TemperatureReading(
        String eventId,
        String deviceId,
        Double celsius) {

    TemperatureReading {
        if (eventId == null || eventId.isBlank()) {
            throw new IllegalArgumentException("Missing eventId");
        }
        if (deviceId == null
                || !deviceId.matches("[A-Za-z0-9_-]{1,40}")) {
            throw new IllegalArgumentException("Invalid deviceId");
        }
        if (celsius == null
                || !Double.isFinite(celsius)
                || celsius < -80 || celsius > 150) {
            throw new IllegalArgumentException("Invalid temperature value");
        }
    }
}
~~~

The temperature range is illustrative only. A real application needs schema versioning, device-specific limits, and publish/tenant permission checks at both the broker and business layer. An MQTT topic filter only governs delivery, not validation.

### 11.5. Validator using **exact received topic**, not wildcards for parsing

~~~java
package demo.mqttfilters;

import java.util.regex.Matcher;
import java.util.regex.Pattern;

final class TopicFilterValidator {

    private final String tenantId;
    private final Pattern telemetryTopic;

    TopicFilterValidator(String tenantId) {
        if (tenantId == null
                || !tenantId.matches("[A-Za-z0-9_-]{1,40}")) {
            throw new IllegalArgumentException("Invalid tenantId");
        }
        this.tenantId = tenantId;
        this.telemetryTopic = Pattern.compile(
                "^tenants/" + Pattern.quote(tenantId)
                + "/devices/([A-Za-z0-9_-]{1,40})/telemetry$");
    }

    String subscriptionFilter() {
        return "tenants/" + tenantId + "/devices/+/telemetry";
    }

    String requireDeviceId(Object receivedTopic) {
        if (!(receivedTopic instanceof String topic)) {
            throw new IllegalArgumentException("Missing received MQTT topic");
        }

        Matcher matcher = telemetryTopic.matcher(topic);
        if (!matcher.matches()) {
            throw new IllegalArgumentException(
                    "Topic is outside tenant telemetry scope: " + topic);
        }

        return matcher.group(1);
    }
}
~~~

Here **Java regex** runs **after the broker has already matched the MQTT subscription filter**, to validate the **concrete topic name** against the business contract. This regex is **not an MQTT topic filter**.

Security note: `subscriptionFilter()` is built from a validated `tenantId`, never taken raw from an HTTP caller. Because concrete topics must match a pattern pinned to that tenant, topics like `tenants/tenant-b/...` or `.../devices//telemetry` are rejected if they ever enter the flow.

### 11.6. Testable fake sink

~~~java
package demo.mqttfilters;

record AcceptedTelemetry(
        String topic,
        TemperatureReading reading) {
}
~~~

~~~java
package demo.mqttfilters;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

class TelemetrySink {

    private final List<AcceptedTelemetry> accepted =
            new CopyOnWriteArrayList<>();

    void accept(AcceptedTelemetry event) {
        accepted.add(event);
    }

    List<AcceptedTelemetry> snapshot() {
        return List.copyOf(accepted);
    }

    void clear() {
        accepted.clear();
    }
}
~~~

`TelemetrySink` only holds data in memory for this lesson and does not persist across restarts. In real integrations, replace it with a business handler enforcing idempotency, transactions, and retry/error policies for a DB or outbound adapter.

### 11.7. Spring MessageChannel and IntegrationFlow

~~~java
package demo.mqttfilters;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.mqtt.support.MqttHeaders;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
class TopicFilterFlowConfiguration {

    @Bean(name = "mqtt.telemetry.in")
    MessageChannel telemetryInput() {
        return new DirectChannel();
    }

    @Bean
    TopicFilterValidator topicFilterValidator(
            @Value("${app.mqtt.tenant-id}") String tenantId) {
        return new TopicFilterValidator(tenantId);
    }

    @Bean
    ObjectMapper telemetryMapper() {
        return new ObjectMapper();
    }

    @Bean
    TelemetrySink telemetrySink() {
        return new TelemetrySink();
    }

    @Bean
    IntegrationFlow telemetryFlow(
            TopicFilterValidator validator,
            ObjectMapper mapper,
            TelemetrySink sink) {

        return IntegrationFlow.from("mqtt.telemetry.in")
                .handle(String.class, (json, headers) -> {

                    String deviceId = validator.requireDeviceId(
                            headers.get(MqttHeaders.RECEIVED_TOPIC));

                    final TemperatureReading reading;
                    try {
                        reading = mapper.readValue(
                                json, TemperatureReading.class);
                    } catch (JsonProcessingException ex) {
                        throw new IllegalArgumentException(
                                "Failed to parse telemetry JSON", ex);
                    }

                    if (!deviceId.equals(reading.deviceId())) {
                        throw new IllegalArgumentException(
                                "deviceId in payload differs from MQTT topic");
                    }

                    String actualTopic = (String)
                            headers.get(MqttHeaders.RECEIVED_TOPIC);

                    sink.accept(new AcceptedTelemetry(
                            actualTopic, reading));

                    return null; // one-way inbound
                })
                .get();
    }
}
~~~

**The flow uses no `@Poller`** to receive MQTT messages; callbacks from the inbound adapter send `Message<String>` instances onto `mqtt.telemetry.in`. With `DirectChannel`, the handler runs synchronously on the channel's dispatching thread in this lesson. When parsing/DB work is heavy, add a bounded queue/executor to avoid blocking MQTT callbacks uncontrollably.

If using `DefaultPahoMessageConverter.setPayloadAsBytes(true)`, the inbound payload becomes `byte[]` instead of `String`; update the handler/decoder contract accordingly. Never assume the broker parses JSON into DTOs for you.

### 11.8. MQTT client factory and wildcard-subscribing adapter

~~~java
package demo.mqttfilters;

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
class MqttFilterTransportConfiguration {

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
    MqttPahoMessageDrivenChannelAdapter telemetryAdapter(
            MqttPahoClientFactory mqttClientFactory,
            @Qualifier("mqtt.telemetry.in") MessageChannel output,
            TopicFilterValidator topicFilterValidator,
            @Value("${app.mqtt.client-id}") String clientId) {

        var adapter = new MqttPahoMessageDrivenChannelAdapter(
                clientId,
                mqttClientFactory,
                topicFilterValidator.subscriptionFilter());

        adapter.setQos(1);
        adapter.setRecoveryInterval(10000);
        adapter.setConverter(new DefaultPahoMessageConverter());
        adapter.setOutputChannel(output);
        return adapter;
    }
}
~~~

Step-by-step behavior:

1. `mqttClientFactory` supplies Paho connection options; `setCleanSession(false)` illustrates a persistent session for subscribers needing offline delivery.
2. `telemetryAdapter` subscribes to `tenants/tenant-a/devices/+/telemetry`.
3. The broker delivers matching PUBLISHes to the adapter's MQTT client per QoS/session/ACLs.
4. `DefaultPahoMessageConverter` converts MQTT bytes into a Spring text payload in this demo.
5. The inbound adapter sets received-topic metadata and sends the message onto the channel.
6. The Spring flow validates the **actual received topic**, parses JSON, and cross-checks `deviceId` before processing.

**Note:** the `+` filter appears only in **SUBSCRIBE**. External publishers still PUBLISH concrete topics like `tenants/tenant-a/devices/device-17/telemetry`, never publishing to the filter `tenants/tenant-a/devices/+/telemetry` itself.

The Client ID in properties is suitable for a single local instance; running two replicas with the same ID causes the broker to drop the older connection. With `cleanSession=false`, a stable Client ID is required to resume the logical session, yet only one active client may own that ID.

### 11.9. Illustrative inbound MQTT data

PUBLISH from `device-17`:

~~~text
Topic: tenants/tenant-a/devices/device-17/telemetry
QoS:   1
Payload:
{"eventId":"evt-1001","deviceId":"device-17","celsius":26.5}
~~~

`TopicFilterValidator` extracts `device-17` from the actual topic. Jackson parses the payload into `TemperatureReading`. If the JSON `deviceId` is `device-21`, the flow rejects it even though the topic matched the wildcard subscription on the broker.

A publisher trying to send to `tenants/tenant-b/devices/device-17/telemetry` will not match `tenant-a`'s subscription filter. However, **that does not replace broker ACLs**: the subscriber's principal must be authorized only for its own namespace; a narrow filter is defense-in-depth, not authorization.

## 12. Subscribing to multiple filters on one adapter

A client may need to receive both telemetry and availability:

~~~text
tenants/tenant-a/devices/+/telemetry
tenants/tenant-a/devices/+/availability
~~~

`MqttPahoMessageDrivenChannelAdapter` supports configuring multiple topic filters in its constructor in supporting Paho MQTT API versions:

~~~java
var adapter = new MqttPahoMessageDrivenChannelAdapter(
        "tenant-a-mqtt-in",
        mqttClientFactory,
        "tenants/tenant-a/devices/+/telemetry",
        "tenants/tenant-a/devices/+/availability");

adapter.setQos(1);
adapter.setOutputChannel(mqttInboundChannel);
~~~

This snippet is an **alternative** to the section 11 demo adapter; do not add both to the same channel expecting the telemetry business handler to process `ONLINE/OFFLINE` payloads.

### 12.1. Routing in Spring by received topic

When two topic kinds carry different payload schemas, route on `MqttHeaders.RECEIVED_TOPIC` into two separate flows:

~~~mermaid
flowchart TD
    BROKER[("MQTT broker")]
    AD["Inbound adapter<br/>2 subscription filters"]
    CH["mqtt.all.in"]
    R{"Router by received topic"}
    TELE["mqtt.telemetry<br/>JSON decoder → DB"]
    AVAIL["mqtt.availability<br/>ONLINE/OFFLINE handler"]
    ERR["unknown-topic / quarantine"]
    BROKER --> AD --> CH --> R
    R -->|"*/telemetry"| TELE
    R -->|"*/availability"| AVAIL
    R -->|"other"| ERR
~~~

This is an architectural diagram. When implementing Java DSL `.route(...)`, use explicit topic parsing/validation rules or a controlled mapping—never route via fragile `String.contains("state")` checks. Both branches must validate tenant, device ID, and schema.

A Spring channel differs from an MQTT filter: **topic filters** are used by the broker to decide which PUBLISHes reach the client; a **Spring router** chooses internal consumers/processing flows after a message enters the application.

### 12.2. When should you split into two MQTT inbound adapters?

Split adapters if:

- One branch needs a `String` converter and the other needs `byte[]`.
- The two topic groups use different credentials/ACLs or broker URLs.
- They need different Client IDs, sessions, QoS, or recovery policies.
- Congestion in one data stream must not stall the other.
- They need independent start/stop lifecycles or scaling.

Two concurrent adapters need **distinct Client IDs**; they can share an `MqttPahoClientFactory` when connection settings match, though never assume they share a single physical MQTT connection.

## 13. Changing subscriptions at runtime

Some systems add or remove topic filters without restarting the application—for example, when a subscriber switches from one device region to another.

In supporting Spring Integration versions, `MqttPahoMessageDrivenChannelAdapter` exposes runtime subscription APIs such as `addTopic(...)` and `removeTopic(...)`. Verify exact method signatures and running-lifecycle behavior against your project's version.

Conceptual example:

~~~java
// Illustrates API in supporting adapter versions:
adapter.addTopic(
        "tenants/tenant-a/devices/+/availability", 1);

adapter.removeTopic(
        "tenants/tenant-a/devices/+/availability");
~~~

**Do not add this directly to the section 11 complete example.** When changing filters at runtime, govern:

1. **Authorization:** who can add filters and for which tenant?
2. **Idempotency:** avoid adding duplicates or removing a filter still required by another flow.
3. **Session state:** with `cleanSession=false`, broker-stored subscriptions can survive reconnects; define how app and adapter synchronize state.
4. **Concurrency:** altering filters while messages arrive can leave in-flight publications.
5. **Replay:** subscribing to a new filter can cause the broker to emit matching retained snapshots.
6. **Observability:** audit who changed filters and when, active filter counts, and SUBACK/UNSUBACK results where available.
7. **Rollback:** if add/remove fails partway, app and broker state must not silently diverge.

### 13.1. SUBSCRIBE and UNSUBSCRIBE are not business transactions

When a client modifies subscriptions, the broker acts at the protocol level. It does not join a database transaction, delete previously received business events, or compensate already-processed messages when a filter is removed.

If business logic manages per-customer subscriptions, maintain a desired/actual subscription state table, validation, and post-reconnect reconciliation instead of fire-and-forget method calls.

### 13.2. Watch out for retained snapshots when adding filters

When subscribing to a new filter, the broker may immediately deliver matching retained messages. Consumers must not blindly treat them as **brand-new events just emitted by a publisher**. Retained state is a per-topic snapshot, different from event history.

For one-time commands, publishers should generally avoid `retained=true`. A new subscriber could receive an old retained command and accidentally re-trigger a physical action.

## 14. Security: broad wildcards can cross tenant boundaries

MQTT wildcards are **topic selectors**, not authorization controls. For instance, the filter:

~~~text
tenants/+/devices/+/telemetry
~~~

can receive data for multiple tenants if the broker allows it. A service dedicated to `tenant-a` must not subscribe with a tenant-level wildcard relying solely on downstream validators as its only "data protection."

Controls should work together across layers:

| Layer | What it must do |
| --- | --- |
| MQTT broker auth | Authenticate principal/client ID/certificate per infrastructure. |
| Broker subscription ACL | Permit principals to subscribe only to authorized tenant/role filters and topics. |
| Broker publish ACL | Restrict devices to publishing only in their own namespace, never another device's topic. |
| Adapter topic filter | Keep as narrow as the use case allows, e.g., `tenants/tenant-a/devices/+/telemetry`. |
| Received topic validation | Parse the actual received topic; reject empty levels, bad shapes, or tenant mismatches. |
| Payload validation | Cross-check `deviceId`, `tenantId`, `schemaVersion`, and event ID against the topic. |
| Data isolation | Never write `tenant-b` data into `tenant-a`'s DB or leak it to other topics/HTTP targets. |
| Logging/audit | Record actions and safe IDs; never log credentials or sensitive raw payloads. |

### 14.1. Why is subscribing to the entire broker with # dangerous?

`#` is handy for debugging a test broker; in production it can flood the application with unsupported payload types, spike CPU/memory, expose data if ACLs are loose, and risk logging sensitive info. It also misses `$SYS` due to the leading-`$` rule.

**Prefer narrow subscription filters** scoped by domain, tenant, device type, and kind. If you genuinely must consume multiple namespaces, separate roles/client credentials, routes, and validation.

### 14.2. Topic injection through identifiers

If an HTTP client supplies `deviceId = "a/../../tenant-b"` or embeds `+`/`#`, naive string concatenation creates malformed topics or attempts cross-tenant routing. Enforce allowlists on IDs and **independent authorization** rather than "sanitizing" by replacing characters in ways that risk collisions.

### 14.3. Broker ACLs vs. application filters

If the broker lets a user subscribe to all of `tenants/#`, merely configuring `tenants/tenant-a/#` in client config does not stop someone from modifying config to read `tenant-b`. Broker ACLs are the authorization boundary; filters and validators provide defense-in-depth, not a substitute for ACLs.

## 15. Subscription errors and message handling

~~~mermaid
flowchart TD
    APP["Spring Integration app"]
    CONNECT{"Broker connect succeeded?"}
    SUB{"SUBSCRIBE filter accepted?"}
    MATCH["Broker matches PUBLISH"]
    CONVERT["Paho converter → Spring Message"]
    VALID{"Validate topic/payload?"}
    DB["Business DB / outbound"]
    ERR["Error flow / quarantine / alert"]
    APP --> CONNECT
    CONNECT -->|"Yes"| SUB
    CONNECT -->|"No"| ERR
    SUB -->|"Yes"| MATCH --> CONVERT --> VALID
    SUB -->|"No: ACL/filter invalid"| ERR
    VALID -->|"Valid"| DB
    VALID -->|"Invalid"| ERR
    DB -. "Downstream failure" .-> ERR
~~~

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Client connects cleanly yet receives no messages | Topic filter case/shape mismatch, publisher on wrong topic, ACL, subscription rejected. | Check filter, actual MQTT topic, broker logs/SUBACK, and Spring endpoint lifecycle. |
| Broker rejects SUBSCRIBE | ACL or invalid topic filter. | Fix permissions/config; do not infinitely retry permission failures. |
| Receives telemetry from another tenant | Overly broad filter, wrong ACL, or bridge lacks tenant check. | Narrow filter, fix broker ACL, enforce validation and auditing. |
| One publish processed multiple times | Overlapping subscriptions, QoS redelivery, publisher retry, or multiple clients. | `eventId`/unique constraints; inspect topology. |
| Message arrives yet JSON parser fails | Converter/schema mismatch, malicious input, or legacy version. | Quarantine, schema mapping, do not infinitely retry deterministic failures. |
| Inbound gets right topic, yet DB writes wrong device | Missing cross-check between payload `deviceId` and received topic. | Parse/validate concrete topic and identity. |
| Missing prior topics after reconnect | Session purged, Client ID changed, adapter did not re-subscribe, or broker failover. | Test recovery, session/subscription state, and active filters. |
| Subscribing to new filter delivers "old" data | Retained snapshot and/or session backlog. | Handle event time, retained metadata, snapshot vs. event policies. |
| Duplicate Client ID causes continuous reconnects | Two active subscribers share an MQTT Client ID. | Manage Client IDs per instance/consumer ownership. |

**Never infer** that an exception thrown from a Spring handler after inbound will make the broker automatically redeliver the MQTT PUBLISH until the DB commits. MQTT ACKs and DB transactions are separate mechanisms; ack/manual-ack behavior and error channels depend on adapter/version/configuration.

### 15.1. Retries and DLQ/quarantine

- **Never retry infinitely** malformed JSON, cross-tenant topics, or ACL-rejected filters.
- **Apply bounded retries** for network, DB, or downstream unavailability using backoff and metrics.
- **Persist critical messages** in an inbox/queue/outbox or durable store per SLA.
- **Preserve `eventId`** so consumers remain idempotent across redeliveries or replays.
- **Use Spring Integration error channels** on appropriate endpoints/flows without assuming every client callback error lands on one global channel automatically.

### 15.2. Backpressure when wildcards are too broad

A broad filter like `devices/#` can suddenly deliver unexpected message types and multiples of expected traffic. With `DirectChannel`, blocking downstream handlers stretch callback execution; with `ExecutorChannel`/`QueueChannel`, bound queues, thread pools, memory, and overflow policies.

An in-memory `QueueChannel` does not gain persistence just because the subscriber uses `cleanSession=false`. Broker-side persistent sessions and Spring-side durable queues sit at two different layers.

## 16. Testing the flow without an MQTT broker

The section 11 example separates `TopicFilterFlowConfiguration` from `MqttFilterTransportConfiguration`. Tests can therefore load **only the flow, channel, validator, and JSON parser** and send Spring messages with `MqttHeaders.RECEIVED_TOPIC` straight into the channel.

This test touches no network, opens no MQTT client, and needs no running broker.

Create `TopicFilterFlowTest.java` in package `demo.mqttfilters`:

~~~java
package demo.mqttfilters;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.mqtt.support.MqttHeaders;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = TopicFilterFlowConfiguration.class)
@TestPropertySource(properties = "app.mqtt.tenant-id=tenant-a")
class TopicFilterFlowTest {

    @Autowired
    @Qualifier("mqtt.telemetry.in")
    MessageChannel input;

    @Autowired
    TelemetrySink sink;

    @Autowired
    TopicFilterValidator validator;

    @BeforeEach
    void clear() {
        sink.clear();
    }

    @Test
    void createsTenantScopedSubscriptionFilter() {
        assertEquals(
                "tenants/tenant-a/devices/+/telemetry",
                validator.subscriptionFilter());
    }

    @Test
    void acceptsMatchingTopicAndMatchingJsonDevice() {
        String json = "{\"eventId\":\"evt-test-1\","
                + "\"deviceId\":\"device-17\","
                + "\"celsius\":26.5}";

        boolean accepted = input.send(
                MessageBuilder.withPayload(json)
                        .setHeader(MqttHeaders.RECEIVED_TOPIC,
                                "tenants/tenant-a/devices/device-17/telemetry")
                        .build());

        assertTrue(accepted);
        assertEquals(
                List.of(new AcceptedTelemetry(
                        "tenants/tenant-a/devices/device-17/telemetry",
                        new TemperatureReading(
                                "evt-test-1", "device-17", 26.5))),
                sink.snapshot());
    }

    @Test
    void rejectsWrongTenantTopic() {
        String json = "{\"eventId\":\"evt-test-2\","
                + "\"deviceId\":\"device-17\","
                + "\"celsius\":25.0}";

        assertThrows(RuntimeException.class, () ->
                input.send(MessageBuilder.withPayload(json)
                        .setHeader(MqttHeaders.RECEIVED_TOPIC,
                                "tenants/tenant-b/devices/device-17/telemetry")
                        .build()));

        assertTrue(sink.snapshot().isEmpty());
    }

    @Test
    void rejectsEmptyDeviceLevel() {
        String json = "{\"eventId\":\"evt-test-3\","
                + "\"deviceId\":\"device-17\","
                + "\"celsius\":25.0}";

        assertThrows(RuntimeException.class, () ->
                input.send(MessageBuilder.withPayload(json)
                        .setHeader(MqttHeaders.RECEIVED_TOPIC,
                                "tenants/tenant-a/devices//telemetry")
                        .build()));

        assertTrue(sink.snapshot().isEmpty());
    }

    @Test
    void rejectsJsonDeviceDifferentFromTopic() {
        String json = "{\"eventId\":\"evt-test-4\","
                + "\"deviceId\":\"device-21\","
                + "\"celsius\":27.0}";

        assertThrows(RuntimeException.class, () ->
                input.send(MessageBuilder.withPayload(json)
                        .setHeader(MqttHeaders.RECEIVED_TOPIC,
                                "tenants/tenant-a/devices/device-17/telemetry")
                        .build()));

        assertTrue(sink.snapshot().isEmpty());
    }

    @Test
    void rejectsMalformedJson() {
        assertThrows(RuntimeException.class, () ->
                input.send(MessageBuilder.withPayload(
                        "{\"eventId\":")
                        .setHeader(MqttHeaders.RECEIVED_TOPIC,
                                "tenants/tenant-a/devices/device-17/telemetry")
                        .build()));

        assertTrue(sink.snapshot().isEmpty());
    }
}
~~~

What the test proves:

1. The tenant-scoped subscription filter is constructed properly.
2. The flow accepts Spring messages with concrete topics and parses JSON.
3. Cross-tenant topics, empty-device-ID topics, and mismatched payloads are blocked.
4. The sink records only validated messages.
5. No broker connection is opened.

**Limitation:** the test **does not prove** the MQTT broker matches `+`/`#` properly, grants SUBACK, delivers QoS, keeps retained/session state, or reconnects. Those require broker integration tests.

### 16.1. Is testing a custom MQTT filter-matcher function enough?

For practice, you can implement `matches(String filter, String topic)` per MQTT 3.1.1 and test the section 7 matrix. Yet **never use naive regex like `filter.replace("+", ".*")`**: that breaks on topic levels, `#` matching zero levels, `$` prefixes, and empty levels.

A local matcher is only for checking configuration logic or visualization; real broker integration tests remain the final check for live publish/subscribe behavior.

## 17. End-to-end testing with an MQTT broker and CLI

Assumes a test broker at `localhost:1883` with Mosquitto CLI installed. Never run broker-stopping or ACL-changing commands against production. For TLS/auth brokers, configure valid certificates and credentials for both app and CLI.

### 17.1. Subscribing to a filter via CLI

Open Terminal A:

~~~bash
mosquitto_sub -h localhost -p 1883 \
  -i demo-topic-filter-observer-1 \
  -t 'tenants/tenant-a/devices/+/telemetry' \
  -q 1 -v
~~~

The `-t` argument is a **subscription filter**, not a publish topic. `-v` prints both the actual topic and payload for inspection.

### 17.2. Publishing to two matching topics

Terminal B:

~~~bash
mosquitto_pub -h localhost -p 1883 \
  -t 'tenants/tenant-a/devices/device-17/telemetry' \
  -q 1 \
  -m '{"eventId":"evt-cli-17","deviceId":"device-17","celsius":26.5}'
~~~

Then:

~~~bash
mosquitto_pub -h localhost -p 1883 \
  -t 'tenants/tenant-a/devices/device-21/telemetry' \
  -q 1 \
  -m '{"eventId":"evt-cli-21","deviceId":"device-21","celsius":27.0}'
~~~

The CLI subscriber prints two lines, both matched by one MQTT filter:

~~~text
tenants/tenant-a/devices/device-17/telemetry {"eventId":"evt-cli-17","deviceId":"device-17","celsius":26.5}
tenants/tenant-a/devices/device-21/telemetry {"eventId":"evt-cli-21","deviceId":"device-21","celsius":27.0}
~~~

The sample Spring application also receives both messages via its inbound adapter and updates `TelemetrySink` when connected to the same broker with permissions.

### 17.3. Publishing a non-matching topic

~~~bash
mosquitto_pub -h localhost -p 1883 \
  -t 'tenants/tenant-b/devices/device-17/telemetry' \
  -q 1 \
  -m '{"eventId":"evt-other-tenant","deviceId":"device-17","celsius":26.0}'
~~~

`tenant-a`'s filter **does not match** `tenant-b`'s topic. Seeing "no message at the subscriber" can result from non-matching topics, yet also from ACLs, an offline subscriber, or connecting to a different broker; keep connectivity and permissions verified during tests to avoid false conclusions.

### 17.4. Testing single-level and multi-level filters

Open two separate CLI subscribers:

~~~bash
mosquitto_sub -h localhost -p 1883 \
  -i demo-plus-1 -t 'devices/+/state' -v
~~~

~~~bash
mosquitto_sub -h localhost -p 1883 \
  -i demo-hash-1 -t 'devices/#' -v
~~~

Publish sequentially:

~~~bash
mosquitto_pub -h localhost -p 1883 \
  -t 'devices/device-17/state' -m 'ONLINE'
mosquitto_pub -h localhost -p 1883 \
  -t 'devices/device-17/sensors/temp' -m '26.5'
~~~

`devices/+/state` matches only the first publication; `devices/#` matches both. Provided clients hold permissions, this directly demonstrates the difference between `+` and `#`.

### 17.5. Testing the $SYS exception

On a test broker supporting `$SYS`, explicitly subscribe to `$SYS/#`. Do not expect `#` to receive those system topics. Still, not every broker exposes identical topic names or allows test accounts to read `$SYS`; seeing no messages may stem from broker support or ACLs rather than disproving wildcard rules.

### 17.6. Integration test matrix

| Scenario | How to test | What to observe |
| --- | --- | --- |
| Single-level wildcard | `devices/+/state` with a topic having one middle level. | Matches. |
| Extra level | `devices/device-17/sensors/state`. | Does not match the filter above. |
| Multi-level | `devices/#` with deeply nested topics. | Matches. |
| Zero levels for `#` | `devices/#` and topic `devices`. | Matches per MQTT semantics. |
| Empty level for `+` | `devices//state`. | Broker may deliver per filter; business validator must reject empty IDs. |
| `$SYS` topics | `#` and `$SYS/#` on a supporting test broker. | Observe the `$` exception. |
| Overlapping filters | Subscribe to `sensors/#` and `sensors/+/temperature` on one client. | Check QoS/duplicate behavior and deduplication. |
| Unauthorized SUBSCRIBE | Principal restricted to `tenant-a` tries `tenant-b` filter. | Broker denies per ACL. |
| Clean session/restart | Stop subscriber and reconnect with same Client ID. | Subscription/backlog follows broker/session policy. |
| Retained publication | Publish retained state, then subscribe to new filter. | Snapshot may arrive immediately; do not mistake it for a live event. |
| Multiple instances | Two subscribers with distinct Client IDs, then test duplicate IDs. | Normal fan-out vs. connection conflicts. |
| Malformed JSON payload | Topic matches, payload malformed. | Spring validator/quarantine catches it; not a matching bug. |

## 18. Shared subscriptions and consumer load-balancing

A regular filter such as:

~~~text
sensors/+/temperature
~~~

subscribed by multiple MQTT clients gives each client matching publications under its own subscription. This is **not** equivalent to competing consumers on a queue where only one worker handles each message.

Some MQTT brokers support **shared subscriptions**—standardized in MQTT 5 and offered as extensions by many brokers on MQTT 3.x—often written as:

~~~text
$share/telemetry-workers/sensors/+/temperature
~~~

Here `telemetry-workers` is the shared subscription group and `sensors/+/temperature` is the shared filter. **Never assume** every broker, protocol version, and ACL supports `$share` syntax or shares identical load-balancing/retained policies.

Important caveats:

1. Shared subscriptions are a broker/protocol feature, not something created by `DirectChannel` or duplicate Client IDs.
2. They do not guarantee exactly-once DB processing; you still need `eventId`, idempotency, and retries.
3. Per-device ordering may require partitioning/sequence rules; load-balancing can route messages from the same device to different workers.
4. Client IDs of online members must still remain distinct.
5. Test retained behavior, ACLs, QoS, sessions, failover, and compatibility on your exact broker.

For systems needing partitioned stream processing and long-term durable replay, consider Kafka/JMS/AMQP or a suitable queue broker rather than forcing raw MQTT filters to act as a stream processor.

## 19. Operations: topic cardinality, performance, and observability

Narrow versus broad wildcards directly dictate how many messages a subscriber receives:

~~~text
telemetry/device-17             → Only one specific topic
telemetry/+/temperature         → One device class, one data type
telemetry/#                     → All levels beneath telemetry
#                               → Very broad for normal topics
~~~

Across a large fleet, `#` can pull in massive traffic, inflating network bandwidth, converter allocations, JSON parse times, and DB load. This can trigger backpressure even while the MQTT connection stays healthy.

### 19.1. Metrics to observe

| Suggested metric/label | Operational value |
| --- | --- |
| `mqtt_active_filters` | Number of subscription filters managed by the client. |
| `mqtt_received_messages_total{kind}` | Throughput by business kind; avoid per-device labels if cardinality is high. |
| `mqtt_subscription_rejected_total` | Detects misconfigured ACLs/filters. |
| `mqtt_connection_recovery_total` | Tracks reconnects/re-subscriptions. |
| `mqtt_received_topic_validation_errors_total` | Flags malformed topic shapes or tenant violations. |
| `mqtt_payload_schema_errors_total` | Separates JSON/schema errors from topic errors. |
| `mqtt_duplicate_event_total` | Measures idempotency hits and overlapping subscriptions. |
| `mqtt_consumer_backlog` | Tracks queue/outbox lag. |
| `mqtt_business_processing_latency_ms` | Shows post-adapter processing time, not just MQTT connection health. |

Metric names are **design suggestions**, not default metrics automatically emitted with these exact names by Spring Integration/Paho. Never use unbounded raw topics containing device IDs as metric labels; high cardinality can overwhelm monitoring systems.

### 19.2. Process for changing topic filters in production

1. Define the business use case and access permissions.
2. Write a match/non-match matrix including empty levels and `$`.
3. Check broker ACLs and prepare alerts for unexpected payload schemas.
4. Canary deploy on one client with its own Client ID.
5. Monitor rates, queue depth, duplicates, parse errors, and subscription state.
6. Test restart/reconnect/failover.
7. Replace/narrow the old filter on schedule, avoiding unintended overlaps.
8. Audit desired vs. actual subscription filters and maintain a rollback plan.

Never just edit a topic string in config and assume the broker immediately updates filters on active connections. Understand adapter lifecycles and how subscription updates take effect.

## 20. Common configuration mistakes

| Symptom | Possible cause | Investigation / fix |
| --- | --- | --- |
| Subscribing to `devices/*/state` receives nothing. | `*` is not an MQTT wildcard. | Use `devices/+/state`. |
| Subscribing to `devices/#/state` is rejected. | `#` is only valid at the final level. | Use `devices/#` and route/validate, or redesign the hierarchy. |
| `devices/+/state` misses topics with two device levels. | `+` matches exactly one level. | Check topic shape; use `#` only when multiple levels are genuinely needed. |
| `devices/#` also receives topic `devices`. | `#` can match zero levels. | Validate exact received topics in Spring. |
| `devices/+/state` receives `devices//state`. | Empty levels still match `+`. | Reject empty device IDs in the business validator. |
| `#` misses `$SYS`. | Leading-`$` exception. | Use `$SYS/#` when supported and permitted by the broker. |
| Subscription matches, yet handler fails parsing. | Different payload schema/encoding, wrong adapter converter. | Check converter, received topic, and schema routing. |
| One event writes to DB multiple times. | Overlap, QoS redelivery, multiple subscribers, or app retries. | Use `eventId`/idempotency; remove redundant overlapping filters. |
| Two replicas kick each other off. | Duplicate Client ID. | Unique Client ID per active connection. |
| Offline events missing after restart. | Wrong clean session, Client ID, or QoS/broker storage. | Test subscription persistence and broker backlog. |
| `tenant-a` service reads `tenant-b` data. | Overly broad filter/wrong broker ACL. | Fix ACLs and tenant-scope filters; validate identity. |
| CLI subscriber sees no publications. | Different host/port, ACL, QoS/session, wrong filter, or publisher not sending. | Check conditions at each layer. |
| Dynamic add/remove missing in project version. | Different Spring Integration API version. | Check API for your exact version and plan deploy/restart behavior. |
| Queue spikes right after filter change. | Overly broad filter caused a traffic burst. | Narrow the filter; add rate limits and backpressure/persistent queues. |
| Broker sent PUBLISH, yet DB has no writes. | Conversion/validation/business handler failed. | Check error flow/quarantine/transactions, not only subscriptions. |

## 21. Practice exercise: separating telemetry by tenant and device

**Context:** a building management platform hosts thousands of sensors across different tenants. Each device publishes temperature, humidity, `ONLINE`/`OFFLINE` availability, and alerts. One Spring Integration backend handles `tenant-a`, while another worker solely monitors availability.

Requirements:

1. Design a unified topic namespace: `tenants/{tenantId}/devices/{deviceId}/{kind}`.
2. Select subscription filters for temperature, humidity, availability, and all sensors of `tenant-a`.
3. Write a match/non-match table with at least 12 cases covering `+`, `#`, empty levels, and the `$` exception.
4. Explain why publishers must not send to topics containing wildcards.
5. Configure `MqttPahoClientFactory` and `MqttPahoMessageDrivenChannelAdapter` subscribing to `tenants/tenant-a/devices/+/telemetry` at QoS 1.
6. Use `MqttHeaders.RECEIVED_TOPIC` to extract `deviceId` from the concrete topic and cross-check it against the JSON payload.
7. Enforce tenant/device authorization via both broker ACLs and business validation, never relying on filters as the sole security boundary.
8. Build a durable error flow/quarantine for schema mismatches and invalid topics; never retry deterministic errors endlessly.
9. Test two overlapping subscriptions on one client against a test broker and observe duplicates/QoS.
10. Run two subscriber clients with distinct Client IDs on the same topic filter to observe fan-out.
11. Test duplicate Client IDs and explain why this must not be used for load-balancing.
12. Create an availability pipeline with a different schema from telemetry; route by received topic or split adapters/clients when policies differ.
13. Test subscriber offline/reconnect with `cleanSession=false` and a stable Client ID; verify QoS/session/broker persistence.
14. Measure throughput, conversion time, and queue backlog when widening a filter from `.../+/telemetry` to `.../#`.
15. Write brokerless unit tests for topic validation and JSON, then test live subscription matching with Mosquitto CLI.
16. If your broker supports it, test shared subscriptions per version docs and evaluate deduplication/ordering implications.

**Completion criteria:** only authorized data is received and processed, wildcard SUBSCRIBEs are never confused with PUBLISH topics, concrete topics are validated, duplicates are handled, reconnect/sessions are understood, and overly broad filters do not overwhelm Spring Integration flows.

## 22. Self-check questions

1. How do a topic name and a topic filter differ?
2. How does an MQTT broker URL differ from a Spring `MessageChannel`?
3. How many topic levels does `+` match? Does it match an empty level?
4. Where may `#` be placed? Does `a/#` match topic `a`?
5. Why are `devices/#/state` and `devices/device+#` invalid filters?
6. Does filter `devices/+/state` match `devices/device-17/room/state`?
7. Does filter `#` match `$SYS/broker/uptime`? Why or why not?
8. To subscribe to system topics, which filter should you use and what additional permission is required?
9. Are MQTT topic names case-sensitive between `Devices` and `devices`?
10. Why are MQTT wildcard filters not Java regular expressions?
11. Why does a subscription filter matching a topic not guarantee the JSON payload is valid?
12. When should you use `MqttHeaders.RECEIVED_TOPIC` instead of `MqttHeaders.TOPIC`?
13. How can overlapping subscriptions introduce duplicate risk?
14. By what mechanism do two MQTT clients with different Client IDs receive messages when subscribed to the same filter?
15. How do publisher QoS and subscriber filter QoS differ?
16. Why does QoS 2 not replace a database unique constraint?
17. What kind of Client ID does `cleanSession=false` require to resume a session?
18. Does an adapter using `DefaultPahoMessageConverter` automatically parse JSON into a DTO?
19. How do you distinguish topic filters selecting messages from Spring routers selecting business flows?
20. When adding filters at runtime, how must retained snapshots and subscription state be handled?
21. Why are broker ACLs still required even when filters are pinned to a tenant?
22. How do shared subscriptions differ from "two clients sharing one Client ID"?
23. When widening a filter from `devices/+/telemetry` to `devices/#`, what performance risks appear?
24. Does a flow test using fake Spring messages prove broker wildcard matching works?
25. Why does healthy online/reconnect status still not prove data was committed to the DB?

**Hint:** wildcard `+` matches one level, `#` matches remaining levels and must sit at the end; `$` topics have a special rule; inbound adapters pass the **concrete topic** to Spring flows, while ACLs, schemas, and idempotency remain the application's responsibility.

## 23. Conclusion

**Subscription patterns and wildcard topics** enable an MQTT subscriber to consume messages across many topics via a shared pattern without creating one subscription per device:

- `+` matches **exactly one** topic level, including empty levels; `#` matches **zero or more** levels and must appear at the end of the filter.
- A PUBLISH must use a **concrete topic name**, never `+`/`#` like a subscription.
- Topics starting with `$` are excluded from filters beginning with `#`/`+`; to receive system topics, use an explicit prefix with broker authorization.
- Overlapping filters, QoS, and sessions/reconnects affect delivery counts; consumers must be idempotent.
- `MqttPahoMessageDrivenChannelAdapter` subscribes to topic filters on the broker and emits Spring messages to a `MessageChannel`; `MqttHeaders.RECEIVED_TOPIC` reports the **received topic name**, which must be validated before business processing.
- Broker ACLs, tenant/topic validation, schema contracts, error handling, backpressure, and real broker testing are prerequisites for operating wildcard subscriptions safely.

In the **SPRING_INTEGRATION_ADAPTERS** module, MQTT subscription filters form the data-selection boundary from the broker, while Spring Integration channels/routers/handlers manage conversion and integration with files, SFTP, HTTP, JMS, AMQP, Kafka, or databases. Proper design clearly separates **broker matching → inbound conversion → topic/identity validation → business processing**, keeping the system both scalable across devices and reliable and observable.
