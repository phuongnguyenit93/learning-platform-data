# Converting byte arrays to payloads in Spring Integration UDP

## Learning objectives

After this lesson, you will be able to:

- Distinguish between **data in a UDP datagram**, `Message<byte[]>`, text payloads, and business domain objects.
- Decode `byte[]` to UTF-8 **strictly**, validating byte length, version, and message structure.
- Wire `UnicastReceivingChannelAdapter`, `MessageChannel`, `@Transformer`, and `@ServiceActivator` to bring UDP data into the application.
- Convert UTF-8, JSON, or binary payloads into corresponding DTOs; encode DTOs back to `byte[]` when sending out over UDP.
- Preserve source headers, classify conversion errors, and test with a real UDP client.
- Explain how datagram size, framing, buffers, performance, security, and endpoint lifecycles affect the conversion process.

This lesson belongs to the **Adapter UDP** chapter in the **SPRING_INTEGRATION_ADAPTERS** module. The module teaches how to connect external systems into Spring Integration using inbound/outbound adapters, gateways, pollers, and `MessageChannel`, while handling message contracts, errors, and connection lifecycles when integrating files, SFTP, HTTP, JMS, AMQP, Kafka, and databases. At the UDP boundary, **bytes must be interpreted and validated against an explicit contract** before becoming business data.

## 1. Why convert the byte array?

Suppose a sensor sends a datagram containing UTF-8 text:

~~~text
v=1;sensor=node-7;seq=1042;tempC=26.5
~~~

UDP only transports **bytes**; it does not declare whether the data is UTF-8, JSON, or a Java object. When receiving a packet, the Spring Integration UDP inbound adapter typically emits `Message<byte[]>` to its output channel—meaning **the current payload is a raw byte array**.

~~~mermaid
flowchart LR
    A["Sensor / external system"] -->|"UDP datagram"| B["UDP inbound adapter"]
    B -->|"Message<byte[]>"| C["Check size and charset"]
    C -->|"Message<String>"| D["Parse + schema validation"]
    D -->|"Message<TelemetryEvent>"| E["Service Activator"]
    E --> F["DB / Kafka / HTTP / other systems"]
~~~

The phrase *converting byte array to payload* here refers to transforming the **initial `byte[]` payload** into a **typed, meaningful payload** such as `String`, `TelemetryEvent`, `JsonNode`, or a binary structure. The adapter receives packets; the transformer interprets bytes; the business service handles the validated object.

A successfully received datagram **does not guarantee** a valid string; a valid string **does not guarantee** a valid schema; a schema-valid DTO **does not guarantee** persistence succeeded.

## 2. Three layers of the message to distinguish

| Layer | Illustrative data | Source and meaning |
|---|---|---|
| UDP payload on the wire | UTF-8 bytes of `v=1;sensor=...` | Serialized by the sender per contract |
| Spring `Message<byte[]>` | `byte[]` and message headers | Inbound adapter wraps datagram into a message |
| Spring `Message<TelemetryEvent>` | Parsed sensor ID, sequence, and temperature | Transformer builds data for the business layer |

Example of the same datagram across two steps:

~~~text
Inbound message:
  payload = byte[] [118, 61, 49, 59, ...]
  headers = {ip_address="192.0.2.31", ip_port=53021, ...}

After transformer:
  payload = TelemetryEvent("node-7", 1042, 26.5)
  headers = {ip_address="192.0.2.31", ip_port=53021, ...}
~~~

These headers are **internal** Spring Messaging metadata. `ip_address`, `ip_port`, or `id` do not automatically live inside the datagram bytes, nor are they automatically transmitted when sending via a UDP outbound adapter. If the target system needs a field, include that field in the payload according to an agreed protocol.

## 3. Defining the payload contract before decoding

| Item | Convention for example | Reason |
|---|---|---|
| Charset | UTF-8 | Avoids relying on the environment's default charset |
| Version | `v=1` | Allows the parser to identify supported formats |
| Format | `v=...;sensor=...;seq=...;tempC=...` | Aligns delimiters, ordering, and field names |
| Size | 1–512 bytes | Prevents oversized payloads and bounds processing cost |
| Sensor ID | ASCII 1–32 chars | Rejects empty IDs and out-of-contract data |
| Sequence | Non-negative integer | Supports deduplication and ordering checks |
| Temperature | Decimal in °C | Explicit units, parsing rules, and valid range |
| UDP framing | Raw, no length prefix | Aligns with `lengthCheck(false)` in the example |
| Invalid packets | Reject + sampled metric/log | Never create business records from bad data |
| Security | Authenticate device if needed | Source IP is not a substitute for trusted identity |

UDP has no built-in schema, charset, or delivery guarantee. **The payload contract is agreed upon by the two applications.** For JSON, protobuf, or CBOR, write an explicit contract for that format and manage versions.

## 4. Counting bytes before converting to String

The datagram limit is a **byte count** limit, not a character count limit:

~~~java
import java.nio.charset.StandardCharsets;

String text = "nhiệt độ 😀";

int javaUnits = text.length();
int utf8Bytes = text.getBytes(StandardCharsets.UTF_8).length;
~~~

`String.length()` counts UTF-16 code units; `byte[].length` counts bytes. Accented characters or emojis can take multiple UTF-8 bytes, so `javaUnits` and `utf8Bytes` often differ.

On inbound:

~~~java
byte[] bytes = message.getPayload();
if (bytes.length == 0 || bytes.length > 512) {
    throw new IllegalArgumentException("UDP payload outside 1..512 bytes");
}
~~~

On outbound, serialize first and then check `bytes.length`.

## 5. Decoding UTF-8: fast approach vs. strict approach

### 5.1. Standard string conversion

~~~java
String text = new String(bytes, StandardCharsets.UTF_8);
~~~

Specifying `StandardCharsets.UTF_8` keeps code consistent. However, the `String` constructor can replace invalid UTF-8 sequences with a replacement character, allowing malformed bytes to still produce a string.

For instance, bytes `C3 28` are not a valid UTF-8 sequence. If you want to **reject** malformed packets, do not silently substitute bytes.

### 5.2. Decoding in REPORT mode

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public final class StrictUtf8 {
    private StrictUtf8() {}

    public static String decode(byte[] bytes)
            throws CharacterCodingException {
        return StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(bytes))
                .toString();
    }
}
~~~

`CharsetDecoder` with `CodingErrorAction.REPORT` returns a result for valid UTF-8 bytes and throws `CharacterCodingException` on invalid encoding. Creating a decoder per decode call is a simple stateless choice; never share a stateful `CharsetDecoder` across multiple threads without synchronization.

If the payload is protobuf or a binary protocol, **do not decode it into a string**. Instead, choose a byte parser and byte order defined by the protocol.

## 6. Configuring UDP inbound and three MessageChannels

This example uses Spring Boot, Spring Integration IP, and Java 17+ to declare the DTO as a `record`. When Spring Boot manages dependency versions, declare:

~~~xml
<!-- Inside dependencies of pom.xml -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-ip</artifactId>
</dependency>
~~~

Initialize one UDP inbound adapter and three internal channels:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.ip.dsl.Udp;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class UdpDecodeConfig {

    @Bean("udpRawBytes")
    public MessageChannel udpRawBytes() {
        return new DirectChannel();
    }

    @Bean("udpDecodedText")
    public MessageChannel udpDecodedText() {
        return new DirectChannel();
    }

    @Bean("udpTelemetryEvents")
    public MessageChannel udpTelemetryEvents() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow udpInboundFlow() {
        return IntegrationFlow.from(
                    Udp.inboundAdapter(12017)
                        .receiveBufferSize(2048)
                        .lengthCheck(false))
                .channel("udpRawBytes")
                .get();
    }
}
~~~

Explanation:

1. `Udp.inboundAdapter(12017)` listens for unicast UDP datagrams on port 12017.
2. `receiveBufferSize(2048)` reserves buffer space for **one datagram**, distinct from the 512-byte business limit. Packets larger than the buffer may be truncated.
3. `lengthCheck(false)` uses **raw UDP**, matching a PowerShell client sending raw UTF-8. If Spring Integration's length prefix is desired, enable it compatibly on both sender and receiver.
4. `udpRawBytes` carries bytes, `udpDecodedText` carries decoded strings, and `udpTelemetryEvents` carries DTOs.
5. With `DirectChannel`, dispatch is synchronous; slow downstream processing can degrade packet-receiving performance.

UDP inbound is an event-driven socket endpoint, **requiring no poller** to read datagrams. A poller may exist elsewhere, such as reading files or a database before pushing messages to UDP outbound.

## 7. Creating the DTO and transformers for the telemetry contract

### 7.1. Business object

Java 17+:

~~~java
import java.math.BigDecimal;

public record TelemetryEvent(
        String sensorId,
        long sequence,
        BigDecimal temperatureC) {
}
~~~

The DTO separates business data from raw bytes, giving DB storage or Kafka publishing steps explicit types to work with.

### 7.2. Two @Transformer steps

~~~java
import java.math.BigDecimal;
import java.nio.charset.CharacterCodingException;
import org.springframework.integration.annotation.Transformer;
import org.springframework.stereotype.Component;

@Component
public class UdpPayloadTransformers {

    @Transformer(
            inputChannel = "udpRawBytes",
            outputChannel = "udpDecodedText")
    public String decodeUtf8(byte[] bytes) {
        if (bytes.length == 0 || bytes.length > 512) {
            throw new IllegalArgumentException(
                    "UDP payload outside 1..512 bytes");
        }

        try {
            return StrictUtf8.decode(bytes);
        } catch (CharacterCodingException ex) {
            throw new IllegalArgumentException(
                    "Invalid UTF-8 datagram", ex);
        }
    }

    @Transformer(
            inputChannel = "udpDecodedText",
            outputChannel = "udpTelemetryEvents")
    public TelemetryEvent parse(String text) {
        String[] fields = text.split(";", -1);

        if (fields.length != 4
                || !fields[0].equals("v=1")
                || !fields[1].startsWith("sensor=")
                || !fields[2].startsWith("seq=")
                || !fields[3].startsWith("tempC=")) {
            throw new IllegalArgumentException(
                    "Invalid telemetry structure");
        }

        String sensorId =
                fields[1].substring("sensor=".length());
        String sequenceText =
                fields[2].substring("seq=".length());
        String temperatureText =
                fields[3].substring("tempC=".length());

        if (!sensorId.matches("[A-Za-z0-9_-]{1,32}")
                || !sequenceText.matches("\\d{1,18}")
                || !temperatureText.matches(
                    "-?\\d{1,3}(\\.\\d{1,2})?")) {
            throw new IllegalArgumentException(
                    "Invalid telemetry value");
        }

        long sequence = Long.parseLong(sequenceText);
        BigDecimal temperature =
                new BigDecimal(temperatureText);

        if (temperature.compareTo(new BigDecimal("-50")) < 0
                || temperature.compareTo(new BigDecimal("150")) > 0) {
            throw new IllegalArgumentException(
                    "Temperature outside accepted range");
        }

        return new TelemetryEvent(
                sensorId, sequence, temperature);
    }
}
~~~

Step one **checks size + UTF-8**; step two **validates schema + parses**. The parser intentionally requires exact four ordered fields, `v=1`, a valid sensor ID, and temperature in `[-50, 150]` °C. This is an **illustrative contract**, not a universal standard across all devices.

Spring Integration's `@Transformer` accepts the payload and builds a new message with the transformed payload; the transformer mechanism generally **preserves appropriate headers** from the incoming message. If you manually construct a new `Message` or use specialized endpoints, re-verify headers after each step.

### 7.3. Service Activator working with the DTO

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.ip.IpHeaders;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

@Component
public class TelemetryEventHandler {

    private static final Logger log =
            LoggerFactory.getLogger(TelemetryEventHandler.class);

    @ServiceActivator(inputChannel = "udpTelemetryEvents")
    public void handle(Message<TelemetryEvent> message) {
        TelemetryEvent telemetry = message.getPayload();

        String sourceIp = message.getHeaders()
                .get(IpHeaders.IP_ADDRESS, String.class);
        Integer sourcePort = message.getHeaders()
                .get(IpHeaders.PORT, Integer.class);

        log.info("Sensor={}, seq={}, UDP source={}:{}",
                telemetry.sensorId(),
                telemetry.sequence(), sourceIp, sourcePort);

        // Next steps: deduplicate, write to DB, publish to broker...
    }
}
~~~

The handler does not need to know the raw UDP format; it receives an already parsed `TelemetryEvent`. This log is for demonstration only. In production, avoid logging sensitive data or logging every datagram under high load.

## 8. Java DSL approach for the byte[] → String step

If you want to configure the transformer inline within a flow, you can use Java DSL as follows:

~~~java
import java.nio.charset.CharacterCodingException;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.ip.dsl.Udp;

@Configuration
public class UdpInlineDecodeFlow {

    @Bean
    public IntegrationFlow udpInlineFlow() {
        return IntegrationFlow.from(
                    Udp.inboundAdapter(12017)
                        .receiveBufferSize(2048))
                .<byte[], String>transform(bytes -> {
                    if (bytes.length == 0 || bytes.length > 512) {
                        throw new IllegalArgumentException("Invalid size");
                    }
                    try {
                        return StrictUtf8.decode(bytes);
                    } catch (CharacterCodingException ex) {
                        throw new IllegalArgumentException(
                                "Invalid UTF-8", ex);
                    }
                })
                .channel("udpDecodedText")
                .get();
    }
}
~~~

**This is an alternative** to the inbound + first transformer in sections 6–7. Do not register two listeners simultaneously on port `12017`, and do not register two competing transformers on `udpRawBytes` if you want each message processed once. Downstream endpoints/transformers on the `udpDecodedText` channel can be reused.

## 9. Preserving source headers when transforming payloads

The UDP inbound adapter can populate headers such as:

| Java constant | Header name | Meaning |
|---|---|---|
| `IpHeaders.IP_ADDRESS` | `ip_address` | Source IP observed by receiver |
| `IpHeaders.PORT` | `ip_port` | UDP source port, not the listener port |
| `IpHeaders.HOSTNAME` | `ip_hostname` | Hostname or IP per reverse-lookup configuration |
| `IpHeaders.PACKET_ADDRESS` | `ip_packetAddress` | Full source `SocketAddress` |

These values aid diagnostics and reply routing. **Do not use source IP as proof of device identity**, because NAT, DHCP, and IP spoofing can alter or falsify addresses.

If building a new `Message` manually, you can preserve headers explicitly:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public Message<String> copySourceHeaders(
        Message<byte[]> incoming) throws Exception {
    String decoded = StrictUtf8.decode(incoming.getPayload());

    return MessageBuilder.withPayload(decoded)
            .copyHeaders(incoming.getHeaders())
            .build();
}
~~~

Before copying, enforce length and schema checks as shown above. Depending on the pipeline, some headers should not be forwarded to external systems: for example, `ip_packetAddress` is an internal Java object, not a natural field on Kafka/JMS/HTTP events. When a UDP reply is needed, retain the destination metadata through to the outbound handler; when publishing to a broker, map permitted values into explicit business fields.

## 10. JSON: from bytes to a structured DTO

A UDP payload can be JSON:

~~~json
{"v":1,"sensorId":"node-7","sequence":1042,"temperatureC":26.5}
~~~

The processing sequence should be:

~~~mermaid
flowchart LR
    A["Message<byte[]>"] --> B["Size guard"]
    B --> C["Strict UTF-8 decode"]
    C --> D["JSON parser"]
    D --> E["Version + schema validation"]
    E --> F["Message<TelemetryEvent>"]
~~~

With Jackson 2, when the project has compatible dependencies, create a **wire** DTO including the `v` field (Java 17+) to validate version before converting to the business DTO:

~~~java
import java.math.BigDecimal;

public record TelemetryJson(
        int v,
        String sensorId,
        long sequence,
        BigDecimal temperatureC) {
}
~~~

Then parse and validate the data:

~~~java
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;

ObjectMapper mapper = new ObjectMapper()
        .configure(
            DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, true)
        .configure(
            DeserializationFeature.FAIL_ON_MISSING_CREATOR_PROPERTIES,
            true);

String json = StrictUtf8.decode(bytes);
TelemetryJson wire = mapper.readValue(json, TelemetryJson.class);
if (wire.v() != 1
        || wire.sensorId() == null
        || !wire.sensorId().matches("[A-Za-z0-9_-]{1,32}")
        || wire.sequence() < 0
        || wire.temperatureC() == null
        || wire.temperatureC().compareTo(
                new java.math.BigDecimal("-50")) < 0
        || wire.temperatureC().compareTo(
                new java.math.BigDecimal("150")) > 0) {
    throw new IllegalArgumentException("Invalid JSON telemetry");
}
TelemetryEvent event = new TelemetryEvent(
        wire.sensorId(), wire.sequence(), wire.temperatureC());
~~~

This snippet should sit inside a method with exception handling. `readValue` only decodes JSON and binds fields; the application must still check version, value ranges, ID, and sequence. `FAIL_ON_UNKNOWN_PROPERTIES` catches unexpected fields; `FAIL_ON_MISSING_CREATOR_PROPERTIES` catches missing constructor parameters on Jackson 2 versions supporting this setting. Separating the wire DTO `TelemetryJson` from the business DTO `TelemetryEvent` enforces version control without leaking transport fields into services.

Note: the code above uses the **Jackson 2 (`com.fasterxml.jackson.databind`)** API. If your project uses a different major version, choose the corresponding package/dependency. For untrusted JSON, bound size, nesting depth, field count, and string lengths before expensive processing.

## 11. Binary payloads: not all bytes are UTF-8

Suppose a device uses a 9-byte protocol:

~~~text
Byte 0      : version (unsigned 8-bit)
Byte 1..2   : sensor ID (unsigned 16-bit, big-endian)
Byte 3..6   : sequence (unsigned 32-bit, big-endian)
Byte 7..8   : temperature x 10 (signed 16-bit, big-endian)
Total       : 9 bytes
~~~

Binary parser:

~~~java
import java.math.BigDecimal;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;

public final class BinaryTelemetryDecoder {

    public static TelemetryEvent decode(byte[] bytes) {
        if (bytes.length != 9) {
            throw new IllegalArgumentException("Expected 9 bytes");
        }

        ByteBuffer buf = ByteBuffer.wrap(bytes)
                .order(ByteOrder.BIG_ENDIAN);

        int version = Byte.toUnsignedInt(buf.get());
        int sensorId = Short.toUnsignedInt(buf.getShort());
        long sequence = Integer.toUnsignedLong(buf.getInt());
        short scaledTemperature = buf.getShort();

        if (version != 1) {
            throw new IllegalArgumentException(
                    "Unsupported version");
        }

        BigDecimal temperature =
                BigDecimal.valueOf(scaledTemperature, 1);

        return new TelemetryEvent(
                "sensor-" + sensorId, sequence, temperature);
    }
}
~~~

Here `scaledTemperature=265` represents **26.5°C**. `ByteOrder.BIG_ENDIAN` and byte offsets must match the protocol specification; `ByteBuffer` defaults to big-endian, but declaring it explicitly prevents confusion. Check **exact** length before reading, use proper unsigned conversions, and reject unsupported versions.

For protobuf, CBOR, or custom binary formats, use the corresponding parser. `new String(bytes, UTF_8)` will not produce a meaningful intermediate representation for such payloads.

## 12. Reverse conversion DTO → byte[] when sending UDP outbound

When the application holds a `TelemetryEvent` and needs to emit it over UDP, perform the reverse path:

~~~mermaid
flowchart LR
    A["TelemetryEvent"] --> B["Serialize per contract"]
    B --> C["UTF-8 byte[]"]
    C --> D["Check byte length"]
    D --> E["UDP outbound adapter"]
    E --> F["UDP datagram"]
~~~

Encoder:

~~~java
import java.nio.charset.StandardCharsets;

public final class TelemetryEncoder {

    private TelemetryEncoder() {}

    public static byte[] encode(TelemetryEvent event) {
        if (event == null
                || event.sensorId() == null
                || !event.sensorId().matches("[A-Za-z0-9_-]{1,32}")
                || event.sequence() < 0
                || event.temperatureC() == null) {
            throw new IllegalArgumentException("Invalid event");
        }

        String text = "v=1"
                + ";sensor=" + event.sensorId()
                + ";seq=" + event.sequence()
                + ";tempC=" + event.temperatureC().toPlainString();

        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        if (bytes.length == 0 || bytes.length > 512) {
            throw new IllegalArgumentException(
                    "Encoded payload too large");
        }
        return bytes;
    }
}
~~~

Wire into an outbound flow:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.ip.dsl.Udp;

@Configuration
public class UdpOutboundEncodeConfig {

    @Bean
    public IntegrationFlow telemetryOutboundFlow() {
        return IntegrationFlow.from("telemetryToUdp")
                .<TelemetryEvent, byte[]>transform(
                        TelemetryEncoder::encode)
                .handle(Udp.outboundAdapter("127.0.0.1", 12018))
                .get();
    }
}
~~~

Channel `telemetryToUdp` accepts `Message<TelemetryEvent>`; the transformer encodes it to `byte[]`; the outbound handler sends the packet to the receiver at `127.0.0.1:12018`. This is a **separate sending example**, not the listener receiving on port 12017. In Docker, loopback refers only to the current container; when sending across the network, use a reachable host/IP.

Even if `MessageChannel.send()` returns `true` or the outbound handler throws no exception, **there is still no proof the receiver received and committed the business work**. Plain UDP has no automatic ACK.

## 13. Framing, datagram size, and truncated data

Three sizes must be distinguished:

| Size | Example | Risk |
|---|---|---|
| **Application payload** | 512 UTF-8 bytes | Exceeds business contract |
| **UDP payload on the wire** | 512 raw bytes or 516 bytes with 4-byte prefix | Must account for framing overhead |
| **Datagram read buffer** | `receiveBufferSize(2048)` | Larger datagrams may be truncated |

When Spring Integration `lengthCheck(true)` is enabled, the sender prepends a **4-byte length prefix** and a compatible receiver compares the length before forwarding the payload to the channel. With 512 business bytes, the UDP payload on the wire is **516 bytes**; adding the 8-byte UDP header and standard 20-byte IPv4 header yields a **544-byte** example IP packet (excluding IP options/tunnels).

**Both sides must agree on framing**. If the sender sends raw bytes while the receiver expects a length prefix, leading payload bytes will be misinterpreted. If you only check `bytes.length <= 512`, a truncated packet could coincidentally look within limits and slip into the decoder; thus a size guard alone does not prove the full datagram was received.

Length check helps detect some truncation cases; it does **not** recover datagrams lost before the socket, guarantee ordering, or replace checksums/signatures. For larger payloads, consider MTU/Path MTU, IP fragmentation, and alternative transports if full delivery is mandatory.

## 14. Classifying conversion errors

| Error | Example | Appropriate behavior |
|---|---|---|
| Size | 0 or 513 bytes under a 1–512 contract | Reject, increment `udp_invalid_size_total` metric |
| Encoding | Bytes `C3 28` | Rejected by `REPORT` decoder |
| Schema | Missing `seq`, wrong field count, or wrong version | Reject, increment schema error metric |
| Business rule | Temperature `999` | Reject or quarantine per policy |
| Datagram truncation | Receiver buffer too small | Adjust buffer/framing, verify via packet capture |
| Network loss | Datagram never reaches socket | No message produced for transformer to handle |
| Downstream unavailable | Database/broker stopped | Bounded retries and idempotency if needed |

When a transformer throws `IllegalArgumentException`, Spring Integration can wrap it in a messaging exception; whether errors route to an error channel depends on the specific endpoint, channel, and configuration. Explicitly design **error flows, metrics, and logs** for bad packets; do not assume every packet loss or transport issue becomes an `ErrorMessage`.

For schema-invalid data, retrying the same bytes endlessly will not fix the cause. If the business requires storing every record, implement application-layer ACK/retry with durable storage or switch to HTTP, Kafka, JMS, or AMQP as appropriate.

## 15. Testing with a real UDP client

Start the Spring Boot application with the configuration and transformers from sections 6–7. Use PowerShell on the same machine to send a valid datagram:

~~~powershell
$client = [System.Net.Sockets.UdpClient]::new()
try {
    $text = "v=1;sensor=node-7;seq=1042;tempC=26.5"
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($text)
    [void]$client.Send(
        $bytes, $bytes.Length, "127.0.0.1", 12017
    )
}
finally {
    $client.Dispose()
}
~~~

Illustrative log:

~~~text
Sensor=node-7, seq=1042, UDP source=127.0.0.1:<source-port>
~~~

`<source-port>` is chosen by the operating system and may change each time `UdpClient` is created. It is not the listener port 12017.

### 15.1. Sending invalid UTF-8 bytes

~~~powershell
$client = [System.Net.Sockets.UdpClient]::new()
try {
    $invalid = [byte[]](0xC3, 0x28)
    [void]$client.Send(
        $invalid, $invalid.Length, "127.0.0.1", 12017
    )
}
finally {
    $client.Dispose()
}
~~~

`StrictUtf8.decode` must reject that packet. Also test:

~~~text
v=1;sensor=node-7;seq=1042;tempC=26.5   # valid
v=1;sensor=node-7;seq=x;tempC=26.5      # invalid seq
v=1;sensor=node-7;tempC=26.5             # missing field
v=2;sensor=node-7;seq=1042;tempC=26.5   # invalid version
v=1;sensor=node-7;seq=1042;tempC=999    # out of range
~~~

Change `$text` in the send script to each line (omitting comments after `#`). For a 513-byte payload, the transformer must reject before decoding.

### 15.2. Unit testing conversions

~~~java
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class UdpPayloadTransformersTest {

    private final UdpPayloadTransformers converter =
            new UdpPayloadTransformers();

    @Test
    void convertsValidTelemetry() {
        byte[] bytes = ("v=1;sensor=node-7;seq=1042;tempC=26.5")
                .getBytes(StandardCharsets.UTF_8);

        TelemetryEvent event =
                converter.parse(converter.decodeUtf8(bytes));

        assertEquals("node-7", event.sensorId());
        assertEquals(1042L, event.sequence());
        assertEquals(0, event.temperatureC().compareTo(
                new java.math.BigDecimal("26.5")));
    }

    @Test
    void rejectsMalformedUtf8() {
        byte[] bad = {(byte) 0xC3, (byte) 0x28};
        assertThrows(IllegalArgumentException.class,
                () -> converter.decodeUtf8(bad));
    }

    @Test
    void rejectsOversizeMessage() {
        assertThrows(IllegalArgumentException.class,
                () -> converter.decodeUtf8(new byte[513]));
    }
}
~~~

Unit tests verify converter logic on deterministic bytes. Integration tests over a real socket are what verify adapter datagram reception, source header mapping, channel routing, and lifecycle. Only send after the listener is ready; because UDP has no delivery guarantee, a single send in a test is not proof of general reliability.

## 16. Security, performance, and observability

- **Validate early:** enforce byte size limits before decoding or parsing JSON/protobuf; reject unsupported versions and schemas.
- **Avoid unbounded object creation:** JSON parsers can be abused via nesting depth, field counts, and data length; set appropriate limits.
- **Use the right decoder:** strict UTF-8 for text; `ByteBuffer`/protocol parsers for binary; do not guess types from a few bytes unless defined by the contract.
- **Do not trust source addresses:** `ip_address` can change via NAT or be spoofed in some environments; authenticate messages/devices when needed.
- **Do not log raw packets:** avoid data leaks and log spam; log error types, sizes, validated IDs, and metrics with sensible cardinality.
- **Keep transformers fast:** if `DirectChannel` connects directly to slow processing, UDP drop risk rises; offload to a bounded executor/queue, though decoupling channels does not turn UDP into a reliable transport.
- **Monitor lifecycle:** the socket must be listening to produce messages; during adapter stop/restart, datagrams can be lost before conversion.

Recommended metrics include `udp_received_total`, `udp_decoded_total`, `udp_invalid_size_total`, `udp_invalid_encoding_total`, `udp_invalid_schema_total`, and `udp_business_processed_total`. Measure packets received by the receiver separately from business records successfully committed.

## 17. Consolidation exercise

Build a **UDP → `Message<byte[]>` → `TelemetryEvent` → database** pipeline following this contract:

~~~text
v=1;sensor=node-7;seq=1042;tempC=26.5
~~~

Requirements:

1. Use `Udp.inboundAdapter(12017)` with raw UDP and a sufficiently large receive buffer.
2. Write a transformer from `byte[]` to `String` using strict UTF-8, enforcing a 512-byte limit.
3. Write a transformer from `String` to `TelemetryEvent`, validating version, sensor, sequence, and temperature.
4. Preserve `ip_address`/`ip_port` to observe the sender source; do not use source address as a trusted identity.
5. Send valid packets, malformed UTF-8, wrong version, invalid schema, and oversized payloads; classify errors with metrics.
6. Write the reverse encoder from DTO to `byte[]` and send UDP to a test listener, verifying round-trip data.
7. Try a JSON payload and a 9-byte binary payload; pick the right decoder for each format.
8. Simulate database downtime and propose how to handle retry/ACK/idempotency if data cannot be lost.

**Self-assessment questions:**

- Why is `Message<byte[]>` not yet enough to process telemetry as business data?
- What problem does `CharsetDecoder.REPORT` solve?
- Why can using `String.length()` to limit UTF-8 datagrams be wrong?
- When should a transformer return `TelemetryEvent` directly versus using an intermediate `String`?
- Is the `ip_packetAddress` header automatically included inside the UDP payload?
- Why should you not decode protobuf into a `String` before parsing?
- If a datagram was truncated due to a small buffer, can the converter recover the lost bytes?
- When a producer reads files or a DB using a poller and then sends UDP outbound, at which step must the byte limit be enforced?

## 18. References

- [Spring Integration Reference — UDP Adapters](https://docs.spring.io/spring-integration/reference/ip/udp-adapters.html): datagrams, inbound/outbound adapters, and framing.
- [Spring Integration Reference — IP Message Headers](https://docs.spring.io/spring-integration/reference/ip/msg-headers.html): UDP source headers.
- [Spring Integration Reference — Message Transformation](https://docs.spring.io/spring-integration/reference/transformer.html): transformers and message payloads.
- [Oracle CharsetDecoder API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/CharsetDecoder.html): strict UTF-8 and `CodingErrorAction.REPORT`.
- [RFC 8085 — UDP Usage Guidelines](https://www.rfc-editor.org/rfc/rfc8085): risks around datagram size, fragmentation, and delivery.

## Conclusion

In Spring Integration, `byte[]` is the **raw payload** placed into a message by the UDP inbound adapter. To use it safely in the application, **check byte length → decode per charset/protocol → validate version and schema → construct a typed DTO → execute business logic**. Transformers and `MessageChannel` separate datagram reception from data interpretation and downstream system integration.

When forwarding to HTTP, files, SFTP, JMS, AMQP, Kafka, or databases, clearly specify which data is business payload, which metadata should be retained, and the rules for errors, timeouts, and durable storage. **Proper type conversion does not guarantee UDP delivery succeeded or downstream transactions completed.**
