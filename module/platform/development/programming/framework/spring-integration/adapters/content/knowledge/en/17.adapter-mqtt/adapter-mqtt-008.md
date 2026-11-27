# Payload conversion for MQTT messages

## 1. The problem: MQTT bytes are not Spring objects

MQTT transmits **payloads as raw bytes**. An MQTT broker does not inherently know whether a byte sequence represents JSON, a JPEG image, protobuf, or a temperature reading. Meanwhile, Spring Integration operates on `Message<?>` with Java payload types such as `String`, `byte[]`, or `TemperatureReading`, alongside `MessageHeaders`. For reliable integration, an application must convert data at the exact boundary between **MQTT transport** and the **business contract**.

For example, a sensor publishes:

~~~text
MQTT topic: sensors/device-17/temperature
MQTT QoS:   1
MQTT bytes: 7B 22 65 76 65 6E 74 49 64 22 3A ... 7D
UTF-8 interpretation:
{"eventId":"evt-1001","deviceId":"device-17","celsius":26.5}
~~~

Those bytes only become a `TemperatureReading` when the application **explicitly chooses an encoding and parses a JSON schema**. If another device uses protobuf on the same topic with binary payloads, forcing everything into a `String` breaks the contract and can corrupt the bytes.

This lesson, **"Payload conversion for MQTT messages,"** belongs to the **Adapter MQTT** chapter of the **SPRING_INTEGRATION_ADAPTERS** module. This module connects external systems using inbound/outbound adapters, gateways, pollers, and `MessageChannel`; practicing with files, SFTP, HTTP, JMS, AMQP, Kafka, and databases while managing message contracts, errors, and connection lifecycles. For MQTT, payload conversion is where the protocol boundary connects to those processing flows.

After completing this lesson, learners will be able to:

1. Distinguish **MQTT payload bytes**, **Spring payloads**, **message headers**, and **business DTOs**.
2. Configure `DefaultPahoMessageConverter` on MQTT inbound/outbound adapters.
3. Choose `String` vs. `byte[]` based on the data contract and understand why charsets must be agreed upon.
4. Parse/serialize JSON via Jackson in a **transformer/handler** instead of expecting the MQTT broker to understand schemas.
5. Distinguish protocol topic/QoS/retained metadata from application data carried inside the payload.
6. Build a Spring Boot flow receiving JSON messages, validating DTOs, and writing to a business sink, as well as publishing DTOs to the broker.
7. Preserve raw bytes for binary payloads, avoiding double conversions that corrupt data.
8. Design brokerless tests and broker-backed end-to-end tests, including encoding/schema failure cases.
9. Plan error flows, quarantine, payload size limits, idempotency, and backward compatibility.

**Core rule:** `DefaultPahoMessageConverter` handles **MQTT message ↔ Spring Message**. Jackson or a business codec handles **JSON or binary schema ↔ Java DTO**. These are two separate layers and should not be collapsed into one "magic" conversion.

## 2. Where conversion sits in both integration directions

~~~mermaid
flowchart LR
    DEVICE["Device / Publisher"]
    BROKER[("MQTT broker")]
    PAHO["Eclipse Paho MQTT client"]
    CONVERTER["DefaultPahoMessageConverter"]
    CH["mqtt.telemetry.in<br/>MessageChannel"]
    FLOW["IntegrationFlow<br/>JSON parser + validation"]
    DTO["TemperatureReading"]
    DB[("Database")]
    DEVICE -->|"PUBLISH bytes/topic/QoS"| BROKER
    BROKER --> PAHO --> CONVERTER
    CONVERTER -->|"Message<String> or Message<byte[]>"| CH
    CH --> FLOW --> DTO --> DB
~~~

Outbound reverses the process at the transport boundary:

~~~mermaid
flowchart LR
    SRC["Java DTO / business event"]
    JSON["Jackson serializer / binary encoder"]
    CH["mqtt.publish.requests<br/>MessageChannel"]
    HANDLER["MqttPahoMessageHandler"]
    CONV["DefaultPahoMessageConverter"]
    BROKER[("MQTT broker")]
    SUB["Subscriber"]
    SRC --> JSON -->|"Message<String> or Message<byte[]>"| CH
    CH --> HANDLER --> CONV
    CONV -->|"MQTT PUBLISH bytes"| BROKER --> SUB
~~~

### 2.1. Which layer is responsible for what?

| Layer | Input | Output | Who is responsible? |
| --- | --- | --- | --- |
| MQTT protocol | Topic, byte payload, QoS, retained flag. | Packets sent through the broker. | MQTT/Paho client and broker. |
| MQTT adapter converter | MQTT message from Paho, or Spring message from flow. | Spring `Message<?>` or Paho MQTT message. | `DefaultPahoMessageConverter` / custom converter. |
| Data format decoder/encoder | JSON `String`, protobuf `byte[]`, Avro, CBOR. | Java DTO or schema-compliant bytes/text. | Jackson / protobuf codec / application-selected transformer. |
| Business validation | Parsed DTO. | Accepted event or error. | Business handler/service/validator. |
| Business effect | Valid event. | DB write, HTTP call, JMS/Kafka send, ACK. | Spring Integration flow and downstream services. |

Successful conversion at one layer **does not imply** validity at the next layer. Syntactically valid JSON with an empty `deviceId` is still invalid business data; an MQTT packet accepted by the broker when the DB write fails is still an incomplete task.

## 3. What fields does an MQTT message have and not have?

An MQTT 3.1.1 PUBLISH carries fields such as **topic name**, QoS, retained flag, packet identifier (depending on QoS), and **payload byte sequence**. MQTT v3 carries no built-in Java schema, no general HTTP-style `Content-Type`, and does not automatically serialize all Spring `MessageHeaders`.

Example:

~~~text
PUBLISH:
  topic  = sensors/device-17/temperature
  qos    = 1
  retain = false
  body   = UTF-8 bytes of JSON

After inbound conversion:
  Spring Message<String>:
    payload = "{\"eventId\":\"evt-1001\",...}"
    headers[RECEIVED_TOPIC] = "sensors/device-17/temperature"
    headers[...]           = MQTT metadata depending on converter/version
~~~

When publishing outbound, headers such as `MqttHeaders.TOPIC`, `MqttHeaders.QOS`, and `MqttHeaders.RETAINED` are used by the converter/handler to populate MQTT publication properties. An application header like `correlationId` is **not automatically transmitted as MQTT v3 metadata**; if subscribers need it, it must reside in the **payload schema** or an explicitly implemented contract.

### 3.1. Internal topics and protocol topics

| Value | Example | Role |
| --- | --- | --- |
| Spring input channel | `mqtt.telemetry.in` | Where the adapter sends Spring messages into the flow. |
| MQTT received topic | `sensors/device-17/temperature` | Concrete topic on which the broker delivered the PUBLISH to the inbound client. |
| MQTT outbound topic | `devices/device-17/commands` | Topic to which the outbound handler publishes. |
| Subscriber topic filter | `sensors/+/temperature` | Rule the broker uses to distribute messages to subscribers. |
| Application-agreed payload content type | `application/json; charset=utf-8` | Schema/encoding of the bytes, **not a built-in MQTT v3 field**. |

In Spring Integration, `MqttHeaders.RECEIVED_TOPIC` reads the source topic of an inbound message, while `MqttHeaders.TOPIC` specifies the outbound publish topic. Do not automatically copy the inbound received topic into the outbound destination when bridging protocols; determine targets according to business policy.

## 4. What does DefaultPahoMessageConverter do?

`DefaultPahoMessageConverter` is the default MQTT converter typically used with Spring Integration's Paho adapters. It bridges data between the MQTT representation and the Spring message representation.

### 4.1. Inbound: byte[] to Spring payload

In a common text configuration, the converter decodes incoming MQTT byte payloads into a `String` using the configured/default charset. This is convenient for JSON text or status messages like `ONLINE`/`OFFLINE`.

~~~java
var adapter = new MqttPahoMessageDrivenChannelAdapter(
        "telemetry-subscriber-1",
        mqttClientFactory,
        "sensors/+/temperature");

adapter.setConverter(new DefaultPahoMessageConverter());
adapter.setOutputChannel(telemetryInputChannel);
~~~

With the default converter in text mode, downstream normally receives `Message<String>`. **This does not parse JSON into a DTO**; the payload is still the raw JSON string.

### 4.2. Inbound: keeping the payload as byte[]

If the source publishes binary payloads, or the application wants full control over decoding/charset, choose byte arrays:

~~~java
var converter = new DefaultPahoMessageConverter();
converter.setPayloadAsBytes(true);

adapter.setConverter(converter);
~~~

Now downstream flows receive `Message<byte[]>` and can inspect signatures/magic bytes, decompress, decode protobuf, or read UTF-8 JSON with an explicitly configured parser.

**Important:** never convert bytes of images, ZIP files, protobuf, or encrypted data into text just for easier logging. An invalid text decode can substitute replacement characters, break hashes/signatures, or prevent a lossless round-trip back to the original bytes.

### 4.3. Outbound: from Spring message to MQTT bytes

Outbound adapters like `MqttPahoMessageHandler` invoke the converter to construct the Paho MQTT message. For a `String` payload, the converter encodes text into bytes; for `byte[]`, it publishes raw binary data without going through JSON/text.

~~~java
var handler = new MqttPahoMessageHandler(
        "events-publisher-1", mqttClientFactory);

handler.setDefaultTopic("events/default");
handler.setDefaultQos(1);
handler.setDefaultRetained(false);
handler.setConverter(new DefaultPahoMessageConverter());
handler.setAsync(false);
~~~

Do not pass a Java DTO like `TemperatureReading` straight into the handler expecting the device to receive JSON automatically. **Serialize the DTO** before placing the message on the outbound channel; if you want a custom converter to accept DTOs directly, explicitly design its API, schema, metadata, and tests.

### 4.4. Can the converter infer content by topic?

`DefaultPahoMessageConverter` is neither a schema registry nor a smart topic-aware JSON parser. It converts transport data—it does not know that `sensors/+/temperature` is a `TemperatureReading` while `sensors/+/humidity` is a `HumidityReading`. That belongs to application-configured transformers, routers, and validators.

## 5. String, byte[], or Java DTO: where to choose each?

| Spring payload type | When appropriate | Considerations |
| --- | --- | --- |
| `String` | UTF-8 text, JSON, `ONLINE`/`OFFLINE` statuses, small CSVs. | Agree on charset, size limits, schema, and content validation. |
| `byte[]` | Protobuf, CBOR, compressed/encrypted data, images, or uncertain encoding. | Preserves bytes; requires dedicated decoder/checksum/signature handling. |
| Java record/DTO | Business layer after parsing/validation; before outbound serialization. | MQTT broker does not understand Java objects; needs a serialization contract. |
| `Message<String>` | Carries both JSON text and MQTT headers. | Internal Spring headers do not automatically cross the broker to subscribers. |
| `Message<byte[]>` | Preserves raw bytes and MQTT metadata for later decoding. | Avoid logging payloads directly or copying byte arrays unnecessarily. |

Avoid default Java serialization (`ObjectOutputStream`) as an inter-device protocol without a strictly controlled contract: it has poor cross-language compatibility, security risks, versioning fragility, and operational complexity. Likewise, do not pick `byte[]` vs. `String` by size alone: data nature, encoding, and byte-preservation requirements are the primary factors.

### 5.1. Two standard pipelines

Text JSON:

~~~text
MQTT byte[] → DefaultPahoMessageConverter → String JSON
            → Jackson ObjectMapper → TemperatureReading
            → validate business fields → DB
~~~

Binary protobuf:

~~~text
MQTT byte[] → converter.payloadAsBytes=true → byte[]
            → Protobuf parser → TemperatureReading
            → validate business fields → DB
~~~

Outbound runs in reverse: DTO → chosen encoder → `String` or `byte[]` → MQTT converter → PUBLISH.

## 6. Charset and encoding: never guess from the topic name

An MQTT payload is fundamentally a byte sequence. When using JSON, publish an explicit encoding rule (typically **UTF-8**) and follow it identically on both producers and consumers.

For example, the same Unicode character has different byte representations across encodings; if a device sends UTF-16 while the consumer assumes UTF-8, JSON parsing fails or produces corrupted values.

A well-defined JSON contract:

~~~text
Topic:          sensors/{deviceId}/temperature
Payload format: application/json
Encoding:       UTF-8
Schema:         temperature-reading/v1
Fields:         eventId, deviceId, celsius
Maximum bytes:  16 KiB per application policy
QoS:            1
Retained:       false
~~~

**Never infer charset from the MQTT Topic Name.** Topic names and payload formats are independent. MQTT 3.1.1 also carries no default HTTP `Content-Type`.

### 6.1. Explicit decoding when keeping byte[]

If the application opts for raw bytes, use `StandardCharsets.UTF_8` in your decoder to avoid relying on the host environment's default charset:

~~~java
String text = new String(rawBytes, StandardCharsets.UTF_8);
~~~

However, the `String` constructor silently replaces malformed UTF-8 byte sequences according to default decoder behavior. When you need to **reject** malformed bytes instead of substituting replacement characters, use a decoder with `CodingErrorAction.REPORT`:

~~~java
CharsetDecoder decoder = StandardCharsets.UTF_8
        .newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

String text = decoder.decode(ByteBuffer.wrap(rawBytes)).toString();
~~~

Required imports:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.CharsetDecoder;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
~~~

`decode(...)` can throw `CharacterCodingException`; handle it via an error/quarantine flow rather than silently dropping messages or retrying schema errors forever.

### 6.2. Check byte size before parsing

Payload size limits should be enforced at the broker, client, and application—for example, rejecting JSON telemetry larger than 16 KiB. `String.length()` counts UTF-16 code units in Java, **not UTF-8 byte count**. To enforce exact byte limits, check `rawBytes.length` while the data is still a `byte[]` before decoding.

If the converter already built a `String` before size validation runs, the broker/client has still allocated memory to read the bytes; enforcing limits at both the broker and decoder provides necessary defense.

## 7. JSON parsing is the transformer/handler's responsibility

A publisher sends JSON:

~~~json
{
  "eventId": "evt-1001",
  "deviceId": "device-17",
  "celsius": 26.5
}
~~~

`DefaultPahoMessageConverter` can turn the bytes into a `String` holding that JSON. Obtaining a Java DTO still requires a data format decoder such as **Jackson**:

~~~java
TemperatureReading reading =
        objectMapper.readValue(json, TemperatureReading.class);
~~~

The parser handles JSON syntax and field mapping to the record; the business validator checks whether values are valid. Keep these responsibilities distinct:

- **Parse error:** invalid JSON, wrong data type, unmappable required field.
- **Validation error:** JSON parsed cleanly, yet `eventId` is blank, `deviceId` fails allowlist, or temperature is out of range.
- **Authorization error:** topic or device ID belongs to an unauthorized tenant.
- **Transport error:** MQTT connection, subscription, byte/text converter, or broker policy failure.

When a downstream handler fails writing to the database, do not treat it as a converter error or blindly re-publish indefinitely without idempotency.

### 7.1. Schemas must be versioned

An older device may send:

~~~json
{"deviceId":"device-17","value":26.5}
~~~

While the newer system expects:

~~~json
{
  "schemaVersion": 2,
  "eventId": "evt-1001",
  "deviceId": "device-17",
  "celsius": 26.5
}
~~~

Do not expect Jackson to guess what `value` means. Use a transformer step driven by `schemaVersion`, topic namespace, or a managed client mapping. Versioning is an **application contract**, not a built-in feature of `DefaultPahoMessageConverter`.

## 8. Complete Spring Boot example: MQTT JSON → DTO → processing

This example uses Java 17+, Spring Boot, Spring Integration MQTT based on Eclipse Paho MQTT v3, and Jackson. We build an application featuring:

- An MQTT inbound message-driven adapter subscribing to `sensors/+/temperature`.
- `DefaultPahoMessageConverter` converting MQTT text to `Message<String>`.
- An `IntegrationFlow` parsing JSON via Jackson into `TemperatureReading`, verifying the topic matches `deviceId`, and writing to a sink.
- An MQTT outbound handler sharing the factory with a **different Client ID**, publishing JSON from a DTO to the broker.
- Unit/integration tests loading only the flows, **without** opening network connections.

The example can run against a test broker at `tcp://localhost:1883` if the broker is already started and allows client connections. Spring Boot does not start an MQTT broker automatically.

### 8.1. Maven dependencies

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

Let the Spring Boot BOM manage compatible versions. This example specifically uses Paho MQTT v3 `MqttConnectOptions` and does not apply directly to MQTT v5 clients. `jackson-databind` is declared explicitly because the code relies on `ObjectMapper`.

### 8.2. File structure

~~~text
src/main/java/demo/mqttconversion/
  MqttConversionApplication.java
  TemperatureReading.java
  AcceptedTelemetry.java
  TelemetrySink.java
  TelemetryInboundFlowConfiguration.java
  MqttTransportConfiguration.java
  MqttOutboundFlowConfiguration.java
  TemperaturePublisher.java

src/main/resources/
  application.properties

src/test/java/demo/mqttconversion/
  TelemetryInboundFlowTest.java
  TemperaturePublisherTest.java
~~~

All classes/records belong to package `demo.mqttconversion`. Classes with the `public` modifier must live in identically named Java files. Everything is placed in the same package for consistent Spring component scanning and package visibility.

### 8.3. Application and environment configuration

~~~java
package demo.mqttconversion;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MqttConversionApplication {

    public static void main(String[] args) {
        SpringApplication.run(MqttConversionApplication.class, args);
    }
}
~~~

`src/main/resources/application.properties`:

~~~properties
app.mqtt.broker-url=${MQTT_BROKER_URL:tcp://localhost:1883}
app.mqtt.subscriber-id=${MQTT_SUBSCRIBER_ID:telemetry-in-local-1}
app.mqtt.publisher-id=${MQTT_PUBLISHER_ID:telemetry-out-local-1}
~~~

The local demo omits TLS/passwords. For production brokers, require TLS, authentication, broker topic ACLs, and externalized secrets. Never share the same Client ID between inbound and outbound clients or across concurrent replicas.

### 8.4. DTO and validation

~~~java
package demo.mqttconversion;

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
                || celsius < -80
                || celsius > 150) {
            throw new IllegalArgumentException(
                    "Invalid temperature value");
        }
    }
}
~~~

Validation lives in the record compact constructor so both the JSON decoder and internal producers must supply valid fields. The `-80..150` range is an **illustrative convention**, not a measurement standard for all sensors. Production should use Bean Validation/schemas and per-device-type limits.

Modern Jackson maps JSON fields onto Java record components. If sources send older schemas or different keys, add a mapping/versioning strategy instead of relying on arbitrary field names without tests.

### 8.5. Illustrative sink

~~~java
package demo.mqttconversion;

record AcceptedTelemetry(
        String topic,
        TemperatureReading reading) {
}
~~~

~~~java
package demo.mqttconversion;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

class TelemetrySink {

    private final List<AcceptedTelemetry> accepted =
            new CopyOnWriteArrayList<>();

    void accept(AcceptedTelemetry item) {
        accepted.add(item);
    }

    List<AcceptedTelemetry> snapshot() {
        return List.copyOf(accepted);
    }

    void clear() {
        accepted.clear();
    }
}
~~~

This sink only stores in RAM for testing; production can replace it with a service activator writing to a DB, an HTTP outbound gateway, a JMS/AMQP/Kafka outbound adapter, or file/SFTP storage. Business completion timing must be clearly defined, especially when the MQTT client has ACKed delivery while downstream has not committed yet.

### 8.6. MessageChannel and inbound IntegrationFlow

~~~java
package demo.mqttconversion;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.mqtt.support.MqttHeaders;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
class TelemetryInboundFlowConfiguration {

    @Bean(name = "mqtt.telemetry.in")
    MessageChannel telemetryInput() {
        return new DirectChannel();
    }

    @Bean
    ObjectMapper telemetryObjectMapper() {
        return new ObjectMapper();
    }

    @Bean
    TelemetrySink telemetrySink() {
        return new TelemetrySink();
    }

    @Bean
    IntegrationFlow telemetryInboundFlow(
            ObjectMapper telemetryObjectMapper,
            TelemetrySink sink) {

        return IntegrationFlow.from("mqtt.telemetry.in")
                .handle(String.class, (json, headers) -> {
                    Object rawTopic =
                            headers.get(MqttHeaders.RECEIVED_TOPIC);

                    if (!(rawTopic instanceof String topic)
                            || !topic.matches(
                                    "sensors/[A-Za-z0-9_-]{1,40}/temperature")) {
                        throw new IllegalArgumentException(
                                "Invalid telemetry topic");
                    }

                    final TemperatureReading reading;
                    try {
                        reading = telemetryObjectMapper.readValue(
                                json, TemperatureReading.class);
                    } catch (JsonProcessingException ex) {
                        throw new IllegalArgumentException(
                                "Failed to parse telemetry JSON", ex);
                    }

                    String expectedTopic = "sensors/"
                            + reading.deviceId()
                            + "/temperature";
                    if (!topic.equals(expectedTopic)) {
                        throw new IllegalArgumentException(
                                "deviceId does not match MQTT topic");
                    }

                    sink.accept(new AcceptedTelemetry(topic, reading));
                    return null; // one-way inbound, no reply
                })
                .get();
    }
}
~~~

**Why the handler uses `String.class`:** this is a JSON text flow where the inbound converter produces a `String` payload. If `setPayloadAsBytes(true)` is enabled on the adapter, the input contract changes to `byte[]` and this handler **no longer matches the type**. Whenever you change the converter, update downstream consumers accordingly.

The flow cross-checks topic and `deviceId` to prevent a publisher from sending device A's payload under device B's topic. This **does not replace broker ACLs and authentication**; it is an additional business-layer check.

**Note on errors:** parse/validation exceptions inside a handler may be wrapped by Spring Integration into messaging exceptions. Real applications need an error flow/quarantine and explicit MQTT acknowledgment policies; never simply throw errors and assume the broker will redeliver the message reliably.

### 8.7. MQTT factory, inbound, and outbound endpoints

~~~java
package demo.mqttconversion;

import org.eclipse.paho.client.mqttv3.MqttConnectOptions;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.mqtt.core.DefaultMqttPahoClientFactory;
import org.springframework.integration.mqtt.core.MqttPahoClientFactory;
import org.springframework.integration.mqtt.inbound.MqttPahoMessageDrivenChannelAdapter;
import org.springframework.integration.mqtt.outbound.MqttPahoMessageHandler;
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
        options.setCleanSession(true);

        var factory = new DefaultMqttPahoClientFactory();
        factory.setConnectionOptions(options);
        return factory;
    }

    @Bean
    MqttPahoMessageDrivenChannelAdapter mqttInboundAdapter(
            MqttPahoClientFactory mqttClientFactory,
            @Qualifier("mqtt.telemetry.in") MessageChannel output,
            @Value("${app.mqtt.subscriber-id}") String clientId) {

        var adapter = new MqttPahoMessageDrivenChannelAdapter(
                clientId, mqttClientFactory, "sensors/+/temperature");

        adapter.setQos(1);
        adapter.setRecoveryInterval(10000);
        adapter.setConverter(new DefaultPahoMessageConverter());
        adapter.setOutputChannel(output);
        return adapter;
    }

    @Bean(name = "mqttPublisher")
    MqttPahoMessageHandler mqttPublisher(
            MqttPahoClientFactory mqttClientFactory,
            @Value("${app.mqtt.publisher-id}") String clientId) {

        var handler = new MqttPahoMessageHandler(
                clientId, mqttClientFactory);
        handler.setDefaultTopic("demo/unrouted");
        handler.setDefaultQos(1);
        handler.setDefaultRetained(false);
        handler.setConverter(new DefaultPahoMessageConverter());
        handler.setAsync(false);
        handler.setCompletionTimeout(5000);
        return handler;
    }
}
~~~

In this example, the inbound adapter is **message-driven** with no poller; the Paho client receives PUBLISH packets and the converter sends Spring messages onto the channel. The outbound handler uses the same factory options with a **different Client ID**, consumes Spring messages, and publishes to MQTT.

Default topic `demo/unrouted` is merely a fallback for the demo. With real data, validate topics on the producer and never let a missing header silently publish events to an unintended topic. `completionTimeout(5000)` is not "how long the DB is allowed to process"; it bounds the publish operation per the handler/Paho contract, and a timeout can yield an **uncertain** publish outcome.

### 8.8. Outbound channel and Java DSL handler

~~~java
package demo.mqttconversion;

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
class MqttOutboundFlowConfiguration {

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

`MessageChannel` connects the internal producer to the outbound endpoint; `.handle(publisher)` registers the consumer. Do not also attach `@ServiceActivator(inputChannel="mqtt.publish.requests")` to **the same handler** unless you intend to create two competing consumers.

### 8.9. Serializing the DTO before publishing

~~~java
package demo.mqttconversion;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.mqtt.support.MqttHeaders;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
class TemperaturePublisher {

    private final MessageChannel output;
    private final ObjectMapper mapper;

    TemperaturePublisher(
            @Qualifier("mqtt.publish.requests") MessageChannel output,
            ObjectMapper mapper) {
        this.output = output;
        this.mapper = mapper;
    }

    boolean publish(TemperatureReading reading)
            throws JsonProcessingException {

        if (reading == null) {
            throw new IllegalArgumentException("Missing telemetry");
        }

        String json = mapper.writeValueAsString(reading);
        String topic = "sensors/"
                + reading.deviceId()
                + "/temperature";

        return output.send(MessageBuilder.withPayload(json)
                .setHeader(MqttHeaders.TOPIC, topic)
                .setHeader(MqttHeaders.QOS, 1)
                .setHeader(MqttHeaders.RETAINED, false)
                .build());
    }
}
~~~

A caller can build a DTO:

~~~java
TemperatureReading reading = new TemperatureReading(
        "evt-1001", "device-17", 26.5);

publisher.publish(reading);
~~~

The outbound pipeline performs:

~~~text
TemperatureReading
  → ObjectMapper.writeValueAsString(...)
  → Spring Message<String> + MQTT headers
  → MqttPahoMessageHandler
  → DefaultPahoMessageConverter
  → MQTT PUBLISH byte payload
~~~

When the same application's subscriber listens on matching topics, the inbound pipeline parses the JSON and writes to `TelemetrySink`. That makes a convenient local round-trip test, though you must not use this loop to claim production has exactly-once delivery.

## 9. Binary payloads: do not force every message into JSON

MQTT is frequently used in IoT environments where payloads are fixed binary frames, CBOR/protobuf, or compressed data. In those cases, `String` is not the right representation.

### 9.1. Configuring inbound byte[]

~~~java
var binaryConverter = new DefaultPahoMessageConverter();
binaryConverter.setPayloadAsBytes(true);

var binaryAdapter = new MqttPahoMessageDrivenChannelAdapter(
        "binary-subscriber-1",
        mqttClientFactory,
        "devices/+/binary");

binaryAdapter.setConverter(binaryConverter);
binaryAdapter.setQos(1);
binaryAdapter.setOutputChannel(binaryInputChannel);
~~~

The channel consumer handles `byte[]`:

~~~java
@Bean
IntegrationFlow binaryFlow() {
    return IntegrationFlow.from("mqtt.binary.in")
            .handle(byte[].class, (bytes, headers) -> {
                if (bytes.length < 4) {
                    throw new IllegalArgumentException(
                            "Binary frame too short");
                }
                // Decode per agreed binary protocol.
                // Can verify checksum, frame version, signature...
                return null;
            })
            .get();
}
~~~

The `binaryFlow` snippet assumes a channel bean named `mqtt.binary.in` exists and `binaryInputChannel` above references that bean. This is an **alternative** to text inbound—do not attach a `String`-accepting consumer to the same channel expecting both handlers to see every message.

### 9.2. Outbound binary

~~~java
byte[] frame = new byte[] {
        0x01, 0x00, 0x7F, (byte) 0xA5
};

Message<byte[]> message = MessageBuilder.withPayload(frame)
        .setHeader(MqttHeaders.TOPIC, "devices/device-17/binary")
        .setHeader(MqttHeaders.QOS, 1)
        .setHeader(MqttHeaders.RETAINED, false)
        .build();

binaryOutboundChannel.send(message);
~~~

This illustrates the producer and requires importing `Message`, `MessageBuilder`, `MqttHeaders`, and a `MessageChannel` named `binaryOutboundChannel` wired to an MQTT handler. Never call `new String(frame)` and re-send it for "convenience": text conversion is not byte-for-byte reversible.

### 9.3. When should adapters be split by payload type?

If two topics carry completely different formats (text JSON vs. raw protobuf), create **two MQTT inbound adapters** with differently configured converters and separate output channels:

~~~text
MQTT JSON topic   → String converter → mqtt.json.in  → Jackson parser
MQTT binary topic → byte converter   → mqtt.bytes.in → Protobuf decoder
~~~

Each MQTT client needs its own Client ID when running concurrently. If a single adapter and channel share `payloadAsBytes=true` across all topics, downstream needs a router/decoder that determines the data format from the received topic and formal schema.

## 10. Topic-based schema mapping and content type

When one client subscribes to multiple filters:

~~~text
sensors/+/temperature
sensors/+/humidity
devices/+/config
~~~

do not apply one JSON DTO to every payload. Map by **topic + schema version**:

| Topic pattern | Agreed payload format | Decoder |
| --- | --- | --- |
| `sensors/+/temperature` | UTF-8 JSON, `temperature/v1`. | Jackson → `TemperatureReading`. |
| `sensors/+/humidity` | UTF-8 JSON, `humidity/v1`. | Jackson → `HumidityReading`. |
| `devices/+/binary` | Protobuf bytes, `device-frame/v2`. | Protobuf parser. |
| `devices/+/availability` | UTF-8 text `ONLINE`/`OFFLINE`. | Enum/state parser. |

MQTT v3 has no standard HTTP-like `Content-Type` header. You can embed `schemaVersion` in the JSON/binary frame, encode it in the topic namespace (`v1/...`), or use an external registry. MQTT v5 supports additional metadata such as Content Type and Payload Format Indicator; when using v5, select the corresponding v5 client/converter rather than assuming those fields appear automatically in Paho v3.

### 10.1. Never use topic as proof of authorization

The broker-provided topic helps select a decoder, yet does not replace authorization. If a publisher has rights to multiple topics, it might try sending a payload containing another tenant's `deviceId`. Therefore decoders must combine validation with identity matching against the topic, while the broker enforces ACLs.

### 10.2. Route before decoding or after decoding?

- **Before decoding:** when the topic dictates the schema, route on `MqttHeaders.RECEIVED_TOPIC` and then apply the corresponding decoder.
- **After decoding:** when all messages share a general envelope/schema, parse the envelope first and route by `eventType`.
- **Hybrid:** decode a small envelope first, then pick a body decoder by `type/version`.

There is no single fixed rule for all systems. What matters is that **schema selection is explicit—never guessed from text inspection**—and unrecognized schemas are tested.

## 11. Header mapping: do not lose metadata during transforms

When passing an MQTT message through a transformer, the payload changes from `String` to a DTO, yet metadata such as received topic, event timestamp, and trace context remains valuable.

Initial message:

~~~text
Message<String>:
  payload = JSON
  headers[MqttHeaders.RECEIVED_TOPIC] = sensors/device-17/temperature
~~~

After transformation:

~~~text
Message<TemperatureReading>:
  payload = TemperatureReading(...)
  headers[MqttHeaders.RECEIVED_TOPIC] = sensors/device-17/temperature
~~~

Constructing new Spring messages must follow an explicit policy to **keep or strip headers intentionally**. Building messages manually with `MessageBuilder.withPayload(dto).build()` without copying headers can accidentally drop `RECEIVED_TOPIC` and correlation metadata. When using Spring Integration transformers, verify header-propagation behavior for your endpoint/version.

On the other hand, **do not blindly forward all headers** when bridging to another system. Internal headers like `replyChannel`, `errorChannel`, or credentials are not public data for MQTT subscribers.

### 11.1. Payload transformation does not change QoS

QoS, retained, and topic belong to MQTT delivery metadata. Once a JSON payload is parsed into a DTO inside Spring, the message is already inside the flow; altering the DTO does not send a new MQTT ACK or alter the received publication's QoS.

If you need to publish a new event after transforming, that is a **separate outbound MQTT publication** with its own topic/QoS/retained decisions. Never blindly copy `MqttHeaders.RECEIVED_TOPIC` into `MqttHeaders.TOPIC` as an unconditional bridge.

### 11.2. Application correlation IDs must live in the right place

In MQTT v3, an event ID that subscribers need to read must live in the payload schema, for example:

~~~json
{
  "schemaVersion": 1,
  "eventId": "evt-1001",
  "deviceId": "device-17",
  "celsius": 26.5
}
~~~

Putting `eventId` **only in an internal Spring header** will not expose that ID to external devices/consumers on the far side of the broker. This distinction is critical for cross-system idempotency and tracing.

## 12. Where should converter and JSON validation errors go?

~~~mermaid
flowchart TD
    BROKER[("MQTT broker")]
    CLIENT["Paho client"]
    CONV{"MQTT converter"}
    CH["Spring MessageChannel"]
    PARSE{"JSON / binary decoder"}
    VAL{"Business validation"}
    DB[("DB / outbound adapter")]
    ERR["Error flow / quarantine / audit"]
    BROKER --> CLIENT --> CONV
    CONV -->|"Spring Message"| CH --> PARSE
    CONV -->|"Text decode / mapping error"| ERR
    PARSE -->|"DTO"| VAL
    PARSE -->|"Malformed payload/schema"| ERR
    VAL -->|"Valid"| DB
    VAL -->|"Business rule violation"| ERR
    DB -. "Timeout/transaction error" .-> ERR
~~~

There are at least four distinct error groups:

| Group | Example | Recommended policy |
| --- | --- | --- |
| Transport converter | Bytes fail text decoding per policy, converter rejects type. | Quarantine raw bytes when possible; check client/converter config. |
| Schema parser | Missing JSON brace, wrong type for `celsius`, unsupported schema version. | Reject/quarantine; do not infinitely retry deterministic data errors. |
| Business validator | `deviceId` mismatches topic, temperature out of allowed range. | Record reason, audit, and verify publisher permissions. |
| Downstream | DB unavailable, HTTP timeout, Kafka producer error. | Bounded retries with idempotency, or durable replay store. |

Spring Integration supports error handling via `ErrorMessage`/`errorChannel` when endpoints/flows are configured accordingly. However, **never assume** every exception inside a Paho callback automatically becomes a message on an arbitrary channel or forces the broker to redeliver until the DB commits.

### 12.1. Why shouldn't JSON errors be retried forever?

If the broker delivers the payload:

~~~text
{"eventId":"evt-1001","celsius":
~~~

re-processing the exact same bytes will never make the JSON valid. Infinite retries cause congestion, log storms, and thread starvation. Mark such errors **non-retryable** and store the bad record (if policy permits) alongside topic, correlation/event ID, byte length, error code, and receipt time.

### 12.2. Downstream failures can happen after MQTT ACK

A QoS 1 PUBLISH may already have been acknowledged by the MQTT client/broker at the protocol layer before the database commits. If the DB fails, the MQTT protocol **does not roll back** DB transactions and does not guarantee broker redelivery. To achieve end-to-end guarantees, implement manual acknowledgment on supporting adapters/versions, or persist into a durable store with idempotent processing—all verified with real crash/restart tests.

## 13. Retaining raw payloads for investigation and replay

When a message fails parsing, storing only a post-conversion string may lose original bytes. For systems requiring forensics or replay, enable inbound `payloadAsBytes=true`, store raw payloads temporarily in durable quarantine, and decode in an independent worker.

A quarantine record might contain:

~~~json
{
  "messageId": "quarantine-001",
  "receivedTopic": "sensors/device-17/temperature",
  "receivedAt": "2026-11-23T03:00:00Z",
  "schemaHint": "temperature/v1",
  "payloadLength": 42,
  "payloadStorageRef": "secure-object-store/path",
  "reasonCode": "INVALID_JSON"
}
~~~

This is an **illustrative schema**, not automatic output from Spring Integration MQTT. For PII/secrets, restrict retention, encrypt at rest, enforce ACLs, and audit access. Avoid dumping large binary payloads or full sensor PII into text logs unnecessarily.

### 13.1. Avoid reprocessing loops

If a failing decoder publishes the same message back onto the source topic, the subscriber will re-ingest it infinitely. Separate an `invalid-events`/quarantine store, track retry counts and reasons, and manage dead-lettering/replay administratively. Replays must preserve `eventId` and idempotent business side effects.

### 13.2. Digitally signed payloads

If payloads are digitally signed by devices, **verify the signature over bytes matching the exact canonical contract** before applying transformations that alter representation. Parsing JSON and re-serializing can change whitespace, key order, or numeric formatting, causing raw-byte signatures to fail verification. Pick verification/decoding order per protocol specification.

## 14. Testing the JSON flow without a broker

Inbound logic in section 8 is decoupled from MQTT transport: `TelemetryInboundFlowConfiguration` creates the channel, `ObjectMapper`, sink, and `IntegrationFlow`, **without creating a Paho client**. You can load just this class via `@SpringJUnitConfig`.

Create `TelemetryInboundFlowTest.java` in package `demo.mqttconversion`:

~~~java
package demo.mqttconversion;

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
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = TelemetryInboundFlowConfiguration.class)
class TelemetryInboundFlowTest {

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
    void validJsonBecomesValidatedDto() {
        String json = "{\"eventId\":\"evt-test-1\","
                + "\"deviceId\":\"device-17\","
                + "\"celsius\":26.5}";

        boolean accepted = input.send(
                MessageBuilder.withPayload(json)
                        .setHeader(MqttHeaders.RECEIVED_TOPIC,
                                "sensors/device-17/temperature")
                        .build());

        assertTrue(accepted);
        assertEquals(
                List.of(new AcceptedTelemetry(
                        "sensors/device-17/temperature",
                        new TemperatureReading(
                                "evt-test-1", "device-17", 26.5))),
                sink.snapshot());
    }

    @Test
    void topicDeviceMismatchIsRejected() {
        String json = "{\"eventId\":\"evt-test-2\","
                + "\"deviceId\":\"device-21\","
                + "\"celsius\":25.0}";

        assertThrows(RuntimeException.class, () ->
                input.send(MessageBuilder.withPayload(json)
                        .setHeader(MqttHeaders.RECEIVED_TOPIC,
                                "sensors/device-17/temperature")
                        .build()));

        assertTrue(sink.snapshot().isEmpty());
    }

    @Test
    void malformedJsonIsRejected() {
        assertThrows(RuntimeException.class, () ->
                input.send(MessageBuilder.withPayload(
                        "{\"eventId\":")
                        .setHeader(MqttHeaders.RECEIVED_TOPIC,
                                "sensors/device-17/temperature")
                        .build()));

        assertTrue(sink.snapshot().isEmpty());
    }

    @Test
    void invalidTemperatureIsRejected() {
        String json = "{\"eventId\":\"evt-test-4\","
                + "\"deviceId\":\"device-17\","
                + "\"celsius\":9999}";

        assertThrows(RuntimeException.class, () ->
                input.send(MessageBuilder.withPayload(json)
                        .setHeader(MqttHeaders.RECEIVED_TOPIC,
                                "sensors/device-17/temperature")
                        .build()));

        assertTrue(sink.snapshot().isEmpty());
    }
}
~~~

What the test proves:

- The Spring channel and flow are registered.
- The parser converts JSON text into the Java record cleanly.
- Validation rejects invalid data.
- Cross-checking `deviceId` against the received topic works.
- With `DirectChannel`, the handler runs synchronously in the demo.

**You cannot** conclude from this test that Paho decoded bytes with the right charset, the broker delivered QoS 1, retained flags are right, or MQTT reconnect works. This is a **business conversion test after a Spring `Message<String>` already exists**.

### 14.1. Testing JSON serialization without a broker

You can test DTO/Jackson round-trips standalone:

~~~java
var mapper = new ObjectMapper();
var original = new TemperatureReading(
        "evt-test-5", "device-17", 26.5);

String json = mapper.writeValueAsString(original);
TemperatureReading decoded = mapper.readValue(
        json, TemperatureReading.class);

assertEquals(original, decoded);
~~~

This snippet belongs in a JUnit test method and requires importing `ObjectMapper` and `assertEquals`. It verifies the Java/Jackson schema, yet **does not prove** the MQTT adapter picked the right topic or the converter emitted the right bytes. For critical contracts, add golden JSON fixtures from real publishers and binary decode tests.

## 15. Testing the outbound flow with a fake MessageHandler

To isolate the network, outbound tests omit `MqttTransportConfiguration`. Create a minimal Spring context holding only `MqttOutboundFlowConfiguration`, `ObjectMapper`, `TemperaturePublisher`, and a fake bean named `mqttPublisher`.

~~~java
package demo.mqttconversion;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHandler;
import org.springframework.integration.mqtt.support.MqttHeaders;

record OutboundObservation(
        String topic, String payload, int qos, boolean retained) {
}

class RecordingPublisher implements MessageHandler {

    private final List<OutboundObservation> observations =
            new CopyOnWriteArrayList<>();

    @Override
    public void handleMessage(Message<?> message) {
        observations.add(new OutboundObservation(
                (String) message.getHeaders().get(MqttHeaders.TOPIC),
                (String) message.getPayload(),
                (Integer) message.getHeaders().get(MqttHeaders.QOS),
                (Boolean) message.getHeaders().get(MqttHeaders.RETAINED)));
    }

    List<OutboundObservation> snapshot() {
        return List.copyOf(observations);
    }
}

@Configuration
class OutboundTestBeans {

    @Bean(name = "mqttPublisher")
    RecordingPublisher mqttPublisher() {
        return new RecordingPublisher();
    }

    @Bean
    TemperaturePublisher temperaturePublisher(
            @Qualifier("mqtt.publish.requests")
            org.springframework.messaging.MessageChannel input,
            com.fasterxml.jackson.databind.ObjectMapper mapper) {
        return new TemperaturePublisher(input, mapper);
    }

    @Bean
    com.fasterxml.jackson.databind.ObjectMapper objectMapper() {
        return new com.fasterxml.jackson.databind.ObjectMapper();
    }
}
~~~

In your test, load `@SpringJUnitConfig(classes = {MqttOutboundFlowConfiguration.class, OutboundTestBeans.class})`, inject `TemperaturePublisher` and `RecordingPublisher`, and assert:

~~~java
TemperatureReading event = new TemperatureReading(
        "evt-out-1", "device-17", 26.5);

boolean sent = publisher.publish(event);
assertTrue(sent);

var actual = recorder.snapshot();
assertEquals(1, actual.size());
assertEquals("sensors/device-17/temperature",
        actual.get(0).topic());
assertEquals(1, actual.get(0).qos());
assertEquals(false, actual.get(0).retained());

TemperatureReading decoded = objectMapper.readValue(
        actual.get(0).payload(),
        TemperatureReading.class);
assertEquals(event, decoded);
~~~

`publisher`, `recorder`, and `objectMapper` are injected beans in the test class; the snippet sits inside a test method and requires the corresponding JUnit imports. What the test verifies:

1. The DTO is serialized to JSON.
2. Topic/QoS/retained headers are set properly.
3. `IntegrationFlow` routes the message to the outbound handler bean.
4. The payload deserializes back into an equivalent DTO.

**Limitation:** the fake handler never calls `DefaultPahoMessageConverter` and sends no MQTT packets to a broker. Byte-level transport and QoS must be verified in integration tests.

## 16. End-to-end testing with a broker and CLI

Use only a test broker you set up. `tcp://localhost:1883` assumes a local MQTT broker permitting test client connections. If your broker requires TLS/credentials, configure both the app and CLI properly; never disable production broker security.

### 16.1. Sending inbound JSON with Mosquitto CLI

With the Spring backend subscribed to `sensors/+/temperature`, publish:

~~~bash
mosquitto_pub -h localhost -p 1883 \
  -t 'sensors/device-17/temperature' \
  -q 1 \
  -m '{"eventId":"evt-cli-1","deviceId":"device-17","celsius":26.5}'
~~~

When the flow works, `TelemetrySink` records an `AcceptedTelemetry` with the expected topic, `eventId`, `deviceId`, and temperature. Verify via test hooks/metrics rather than checking only "broker received."

### 16.2. Sending malformed data to verify quarantine

~~~bash
mosquitto_pub -h localhost -p 1883 \
  -t 'sensors/device-17/temperature' \
  -q 1 \
  -m '{"eventId":"evt-cli-bad","deviceId":"device-17","celsius":'
~~~

The JSON handler flow will throw an error, though this demo does not yet include a production quarantine store. Observe logs/error policies and add quarantine/persistent retry before using in a reliable system. Never claim the broker automatically redelivers forever whenever a handler throws an exception.

### 16.3. Observing outbound publications

Start a subscriber:

~~~bash
mosquitto_sub -h localhost -p 1883 \
  -t 'sensors/+/temperature' -v
~~~

Call `TemperaturePublisher.publish(...)` from a local API or test hook. The subscriber prints the topic and JSON text when the broker permits it and the connection is healthy. If inbound and outbound live in the same app subscribed to the same topic, published messages may **loop back into the inbound flow**; that is expected behavior, so guard against cycles if the flow re-publishes every received message.

### 16.4. Testing binary payloads

For topic `devices/device-17/binary`, use a CLI capable of publishing payloads from a test binary file:

~~~bash
mosquitto_pub -h localhost -p 1883 \
  -t 'devices/device-17/binary' \
  -q 1 \
  -f sample-frame.bin
~~~

`sample-frame.bin` is a file **prepared in advance for the test**, not a pre-existing file. When the adapter sets `setPayloadAsBytes(true)`, downstream must receive the exact byte array; compare length and hash to prove data was not altered by text conversion.

### 16.5. Required test matrix

| Test | Input sent | What to verify |
| --- | --- | --- |
| Valid UTF-8 JSON | v1 schema payload, right topic. | Text converter and Jackson decode fields cleanly. |
| Malformed JSON | Missing brace/value. | Parse error enters error policy; no DB side effects. |
| Wrong field type | `celsius="very hot"`. | Parser/validation rejects with a clear reason. |
| Topic/payload mismatch | Topic `device-17`, JSON `device-21`. | Business validator blocks mismatched identity. |
| Unicode | Text field with Vietnamese characters. | UTF-8 round-trip succeeds without encoding corruption. |
| Binary frame | Bytes containing `0x00` or `0xFF`. | `byte[]` is not corrupted by a text decoder. |
| Oversized payload | Exceeds byte limit. | Broker/client/app rejects cleanly without OOM. |
| Empty bytes | Zero-length MQTT payload. | App distinguishes legitimate empty payloads from retained-delete commands. |
| QoS 1 duplicate | Re-send same `eventId`. | DB/handler is idempotent. |
| Broker disconnect | Drop connection in test env. | Recovery/replay follows policy; do not confuse MQTT errors with schema errors. |
| Retained snapshot | Publish retained, then re-subscribe. | Snapshot may reappear; do not count as a new event if forbidden by contract. |
| New schema version | Payload `schemaVersion=2`. | Consumer rejects or selects the matching decoder version. |

## 17. Empty payloads and retained deletion: handle zero bytes carefully

In MQTT 3.1.1, a PUBLISH with **`RETAIN=true`** and a **zero-length** payload to a specific topic is used to **delete the retained message** on the broker.

This connects directly to payload conversion:

- `byte[0]` is a zero-length payload, not the string `"null"` or JSON `null`.
- An empty `String` encoded as UTF-8 yields zero-length bytes, yet retained-deletion semantics depend on **both the RETAIN flag** and the topic, not just content.
- JSON `{"value":null}` is non-empty bytes and is not equivalent to deleting retained state.
- Applications must never accidentally turn "no body" into a retained publish on a production topic.

**Security:** clearing retained state requires authorization and auditing. A buggy converter that turns missing data into `byte[0]` with `retained=true` could accidentally wipe critical device snapshots.

## 18. Performance, backpressure, and large payloads

Converters do not run in a vacuum: when the broker delivers messages faster than consumers can parse, validate, and write to the DB, the system can stall.

| Risk | Why | Solution |
| --- | --- | --- |
| Oversized JSON | String/AST allocations and GC pressure. | Broker/application byte limits; streaming parsers when needed. |
| Repeated `byte[]` copies | Memory/GC overhead and CPU cost. | Keep binary bytes through minimal steps and measure allocations. |
| Parsing on MQTT callback thread | Blocking handlers delay receives/ACKs. | Isolate with bounded executors/queues and error policies. |
| In-memory queues | Restarts lose queued data. | Persistent store/outbox per SLA. |
| Infinite retries on bad data | Poison messages exhaust pools and flood logs. | Retry budgets, non-retryable schema errors, quarantine. |
| Large per-topic schema mapping | Many rules become hard to maintain/align. | Schema registry/versioned configs and contract tests. |
| Payloads containing secrets/PII | Logs/tracing leak sensitive data. | Redaction, access controls, restricted retention. |

`DirectChannel` is simple and synchronous in the demo, yet production may need `ExecutorChannel` or `QueueChannel` to decouple load. Switching to `QueueChannel` requires a downstream **poller** to pull Spring messages off the queue; that does not turn MQTT inbound into a polling adapter.

### 18.1. Do not treat MQTT as a default file-transfer protocol

Even though MQTT carries binary bytes, it does not provide file chunking, resume, whole-file checksums, multi-chunk transactions, or durable storage like a file/object store. For large payloads, consider publishing **secure metadata/links** to an object store instead of stuffing entire files into PUBLISH packets. Bound URLs/ACLs and expirations, and never treat MQTT payloads as an arbitrary large-file transport.

## 19. Security during payload conversion

MQTT payloads can come from untrusted devices/callers; parsers and converters sit inside your application's threat model:

1. **Connection authentication:** broker TLS/credentials or mTLS per environment.
2. **Topic ACLs:** publishers can only publish to their own device/tenant topics; subscribers only read permitted scopes.
3. **Validation:** enforce required fields/schemas and topic–device ID matching.
4. **Byte limits:** from broker/client through parser, reject oversized payloads.
5. **Reject unsafe deserialization:** never use arbitrary Java object deserialization or uncontrolled polymorphic type resolution on user data.
6. **Explicit encoding:** UTF-8 or binary codec mandated by contract; never guess from payload bytes.
7. **Bounded quarantine:** encryption, TTL, restricted access, and audit logging when storing raw bytes.
8. **Avoid logging full payloads:** especially tokens, personal data, binary payloads, or PII.
9. **Idempotency:** `eventId`/`commandId` inside payloads to guard against redeliveries and replays.
10. **Safe replay:** invalid payloads must never loop endlessly onto source topics or trigger unintended device commands.

### 19.1. Malformed Unicode and JSON injection

When inputs contain special characters, **never build JSON via string interpolation** like:

~~~java
String json = "{\"deviceId\":\"" + userDeviceId + "\"}";
~~~

Quotes or escape sequences can produce invalid JSON or alter meaning. Validate identities and serialize DTOs with Jackson, which escapes per JSON grammar. Even then, serialization does not replace authorization and content validation.

## 20. Common errors and troubleshooting

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| Handler expects `String`, receives `byte[]`. | Converter enabled `payloadAsBytes=true`. | Check converter settings and downstream handler generic types. |
| JSON parser fails even though publisher claims it sent JSON. | Wrong charset, non-JSON bytes, truncated payload, or schema mismatch. | Inspect byte length, decode policy, and raw bytes in a safe test. |
| Emojis/Vietnamese characters corrupted. | Producer/consumer use different charsets or replacement decoding. | Standardize on UTF-8, add multilingual round-trip tests and strict decoders. |
| Java DTO fields are null. | Missing JSON keys, mismatched names, schema version drift. | Log mapping/error codes and add required-field validation. |
| Subscriber does not see `eventId`. | `eventId` was only placed in an internal Spring header. | Put the ID inside the JSON/binary payload schema. |
| Inbound flow updates the wrong device. | Missing check between received topic and payload `deviceId`. | Validate topic shape, device authorization, and ID consistency. |
| Binary payload corrupted. | Converted bytes through `String` and re-encoded. | Enable `setPayloadAsBytes(true)` and verify byte-for-byte. |
| Wrong outbound topic. | Confused `MqttHeaders.RECEIVED_TOPIC` with `MqttHeaders.TOPIC`. | Compute outbound topic after routing/authorization. |
| One event creates multiple DB rows. | QoS redelivery/retry or publisher sent two business-identical messages. | Deduplicate by `eventId` and unique constraints. |
| Parse failure disrupts MQTT connection. | Handler throws uncaught exceptions on callback with no error policy. | Check Paho/Spring logs, `errorChannel`, and quarantine. |
| Old message reappears after restart. | Retained snapshot or persistent session/redelivery. | Inspect metadata, event time, QoS/retained, and idempotency. |
| Zero-byte payload wipes retained state. | `RETAIN=true` with zero-length payload per MQTT. | Restrict publish policy, test empty bytes, enforce ACLs. |
| `channel.send(true)` observed, yet device did not receive. | `send` only reflects internal handoff/handler per topology, not a business ACK. | Check broker, QoS, subscriber/session, and dedicated ACK. |
| Slow parser causes broker reconnects. | Long blocking on inbound callback without backpressure. | Bound parsing latency, use executors/queues, monitor. |
| Legacy protobuf version errors. | Decoder/schema mismatch. | Versioning contracts, migrations, and golden fixtures. |

## 21. Practice exercise: mixed JSON and binary telemetry

**Context:** a system ingests MQTT sensor readings from both legacy and modern devices.

- Legacy devices publish UTF-8 JSON to `sensors/{deviceId}/temperature`.
- Modern devices publish binary frames to `devices/{deviceId}/binary`.
- The backend normalizes both into `TemperatureReading`, writes to a DB, and emits a downstream result event to Kafka.

Requirements:

1. Define topic filters and schemas for each payload type; specify maximum bytes and QoS.
2. Create an `MqttPahoClientFactory` and inbound adapter for JSON using a text converter.
3. Create a second inbound adapter with `setPayloadAsBytes(true)` and a separate Client ID for binary frames.
4. Build two Spring input channels without mixing `String` and `byte[]` without an explicit contract.
5. Write a Jackson JSON decoder and a binary decoder matching a frame spec you define (version, length, checksum).
6. Use transformers to normalize both payload kinds into the shared `TemperatureReading` DTO.
7. Validate `deviceId` matches the MQTT received topic; validate `eventId`, temperature bounds, and `schemaVersion`.
8. Route invalid payloads to a durable error flow/quarantine; never retry schema errors infinitely.
9. Enforce idempotency by `eventId` before DB writes; handle QoS 1 duplicates cleanly.
10. Set proper headers when publishing result events and include needed correlation IDs in the partner payload.
11. Write brokerless tests for JSON, binary, topic mismatches, and byte payloads containing `0x00`/`0xFF`.
12. Test against a real MQTT broker, sending JSON via `mosquitto_pub -m` and binary via `-f`.
13. Bound queues, memory, and max payload sizes; monitor parse times and backlog.
14. Test that retained empty payloads cannot accidentally clear production topic state.
15. Document the data contract including encoding, schema version, backward-compatible evolution, and dead-letter policies.

**Completion criteria:** both JSON and binary messages normalize accurately without byte corruption; converters handle transport while decoders handle schemas; errors are traceable, no wrong-device/tenant writes occur, duplicates are suppressed, and tests cover from raw bytes to target state.

## 22. Self-check questions

1. Why cannot an MQTT broker automatically produce a Java `TemperatureReading` from a payload?
2. How does `DefaultPahoMessageConverter` differ from Jackson `ObjectMapper`?
3. When should inbound use `String`, and when should it use `byte[]`?
4. How does `setPayloadAsBytes(true)` affect the payload type received by a handler?
5. Does MQTT v3 automatically send `Content-Type: application/json` like HTTP?
6. Why is an encoding contract still needed even though JSON text usually uses UTF-8?
7. Is `String.length()` equal to the UTF-8 byte count?
8. When bytes are invalid UTF-8, what should you use to reject them instead of substituting replacement characters?
9. Does topic filter `sensors/+/temperature` prove a publisher is authorized to send any `deviceId`?
10. Why should `MqttHeaders.RECEIVED_TOPIC` be cross-checked against the `deviceId` inside the payload?
11. Why is putting `eventId` only in a Spring header insufficient for MQTT v3 subscribers?
12. When sending a DTO outbound, why serialize with Jackson before the converter?
13. Does converting JSON into a DTO guarantee QoS exactly-once DB persistence?
14. Why can storing raw bytes in quarantine be more important than storing a decoded string?
15. If a payload carries a digital signature, should you verify before or after a parse/serialize step that could alter bytes?
16. What does a zero-length payload with `RETAIN=true` mean?
17. What does a fake-handler test verify, and what does it leave unverified?
18. When switching a flow from JSON to binary, which downstream components must change?
19. If one adapter subscribes to multiple topics with different schemas, where should routing occur?
20. How do you distinguish a parse error, a validation error, and a DB timeout?
21. Why should uncontrolled Java object deserialization never be used on MQTT payloads?
22. Under what condition can an application that both subscribes and publishes on the same topic create an infinite loop?
23. What role does schema versioning play across legacy and new devices?
24. If an inbound message carries an old retained snapshot, should it be counted as a brand-new event?

**Hint:** MQTT is a byte transport. The converter creates Spring messages; parsers/decoders handle formats; validators protect business contracts; broker QoS and business transactions live at separate layers.

## 23. Conclusion

**Payload conversion for MQTT messages** bridges protocol data (**MQTT topic + bytes + QoS/retained**) with **Spring Messages and Java types** intentionally.

- `DefaultPahoMessageConverter` converts at the MQTT/Spring boundary; inbound can select `String` for text or `byte[]` for binary.
- JSON, protobuf, and other formats require **dedicated business decoders/encoders** with explicit schemas and versions.
- `MqttHeaders.RECEIVED_TOPIC` and `MqttHeaders.TOPIC` serve distinct purposes; Spring metadata does not automatically cross MQTT v3.
- Integration quality relies on **encoding, byte limits, validation, topic authorization, error/quarantine handling, idempotency**, and testing against a real broker.
- Completing MQTT delivery does not mean the DB, HTTP, JMS, Kafka, or target device succeeded at business processing.

In the **SPRING_INTEGRATION_ADAPTERS** module, separating **transport converter → data format transformer → business handler** keeps flows testable, makes expanding from JSON to binary straightforward, and lets protocols evolve without breaking message contracts. Preserving data fidelity at every boundary is the foundation of reliable Spring Integration MQTT systems.
