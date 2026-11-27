# Datagram packet size and payload limits in Spring Integration UDP

## Learning objectives

After this lesson, you will be able to:

- Distinguish between **application payload size**, **UDP datagram**, **IP packet**, **MTU/Path MTU**, **per-datagram receive buffer**, and **socket receive buffer**.
- Calculate UDP payload limits for IPv4/IPv6 and explain why the ~65 KB theoretical limit is not an appropriate default sending size.
- Understand **IP fragmentation**, fragment loss, datagram truncation at the receiver, and the impact of NAT, VPN, or containers.
- Configure Spring Integration UDP inbound/outbound adapters to receive properly sized messages, validate the data contract, and use **`check-length`** when both sides support it.
- Practice sending small, threshold, and oversized payloads; observe differences between business validation errors, truncation errors, and packet loss.
- Design policies for byte limits, throughput, retry/ACK, and metrics before integrating UDP flows with files, SFTP, HTTP, JMS, AMQP, Kafka, or databases.

This lesson belongs to the **Adapter UDP** chapter of the **SPRING_INTEGRATION_ADAPTERS** module. The module connects external systems into Spring Integration via inbound/outbound adapters, gateways, pollers, and `MessageChannel`; therefore, a **message contract** must be established at the transport boundary. With UDP, *datagram size* is a critical part of that contract: it directly affects full payload delivery, network errors, and processing cost on both sides.

## 1. The problem: small telemetry packets and oversized JSON payloads

A collector receives events from devices over UDP:

~~~text
v=1;sensor=node-7;seq=1042;tempC=26.5
~~~

This message is only a few dozen bytes. However, when a device attaches measurement history, error logs, or deeply nested JSON, the payload can grow to 5 KB, 20 KB, or even larger. The sender can still construct a `DatagramPacket` and call `send()`, which raises several questions:

1. Will the datagram be fragmented along the network path?
2. Has the receiver allocated enough bytes to read the datagram?
3. If the receiver has a small buffer, will it know the payload was truncated?
4. If the payload arrives intact but exceeds the business limit, how will the system handle it?
5. If every event must be persisted, can UDP satisfy that requirement?

~~~mermaid
flowchart LR
    P["Sender application<br/>byte[] payload"] --> O["UDP outbound adapter"]
    O --> N["UDP + IP<br/>network path / MTU"]
    N --> R["UDP inbound adapter<br/>DatagramPacket buffer"]
    R --> V{"Enough bytes<br/>and valid?"}
    V -->|Yes| C["MessageChannel<br/>business processing"]
    V -->|No| E["Record error metric<br/>discard / handle appropriately"]
~~~

**Two independent questions to answer:** *Did the UDP packet arrive intact?* and *Did an intact payload exceed business limits?* Avoid conflating these two scenarios into a single error.

## 2. Distinguishing different sizes

| Metric | What bytes does it count? | Who controls it? |
|---|---|---|
| **Application payload** | Business data after encoding, e.g., UTF-8 JSON or protobuf | Sender and contract between both systems |
| **Spring Integration UDP length prefix** | **4 bytes prepended before payload**, only when `check-length` is enabled on sender | Spring Integration config on both sender and receiver |
| **UDP payload** | Data following the 8-byte UDP header; includes length prefix if enabled | Application and adapter framing |
| **UDP datagram** | 8-byte UDP header + UDP payload | UDP/IP stack |
| **IP packet** | IP header + UDP datagram | IP stack, depending on IPv4/IPv6 and optional headers |
| **Link MTU** | IP packet limit a single network hop transmits without fragmentation (depending on config context) | Interface/network device |
| **Path MTU (PMTU)** | Smallest MTU across hops on the path to the destination | Network topology; may change |
| **Adapter receive buffer** | Bytes the receiver allocates to read **a single datagram** | `receive-buffer-size` / `receiveBufferSize(...)` |
| **Socket receive buffer** | Kernel buffer for traffic waiting to be read by the socket | `so-receive-buffer-size` / `soReceiveBufferSize(...)` |

**Note:** `byte[].length` is the byte count, whereas `String.length()` is the number of **UTF-16 code units**. For Vietnamese text, emoji, and Unicode data, these two numbers can differ. UDP limits must be enforced **after encoding**, based on `byte[].length`, not character count.

### Byte-counting example

Suppose a UTF-8 payload is exactly **512 bytes**, with a standard 20-byte IPv4 header (no IP options):

~~~text
Without length check:
  Application payload        512 bytes
  UDP header                   8 bytes
  IPv4 header                 20 bytes
  ------------------------------------
  Total IP packet            540 bytes

With length check:
  Application payload        512 bytes
  Spring length prefix         4 bytes
  UDP header                   8 bytes
  IPv4 header                 20 bytes
  ------------------------------------
  Total IP packet            544 bytes
~~~

With a standard 40-byte IPv6 header and no extension headers, the two totals are **560** and **564 bytes** respectively. These calculations exclude Ethernet framing, VLAN tags, VPN/tunnel overhead, or optional IP headers.

## 3. UDP's theoretical limit is not an operational limit

UDP has a 16-bit `Length` field covering the 8-byte UDP header and the payload. For standard IP packets:

| Case | Standard IP header | UDP header | Theoretical max UDP payload |
|---|---:|---:|---:|
| IPv4, no IP options | 20 bytes | 8 bytes | **65,507 bytes** |
| IPv6, no extension headers or jumbograms | 40 bytes | 8 bytes | **65,527 bytes** |

These are **theoretical limits** based on standard IP packet size, not guarantees of real networks or receive buffers. IPv6 has a special *jumbogram* mechanism, which is not typical for UDP adapters; do not design telemetry around that exception.

When payloads reach tens of KBs, IP packets often exceed the MTU of many hops. The operating system may fragment them if protocols and policies permit, or return a send error/drop the packet. The sending API returning without an exception **does not prove** the receiver obtained the complete datagram.

**Recommendation:** set payload limits based on schema, business needs, network path, and real tests; never use 65,507 or 65,527 bytes as a default `MAX_PAYLOAD`.

## 4. MTU, Path MTU, and avoiding fragmentation

### 4.1. Calculation formula

When **PMTU** is known and there is no extra encapsulation:

~~~text
Max unfragmented UDP payload
    = Path MTU - IP header - UDP header
~~~

For example, with a **1500-byte** Ethernet MTU on a direct path without tunnels or optional headers:

| IP version | Example PMTU | IP header | UDP header | Calculated max UDP payload |
|---|---:|---:|---:|---:|
| IPv4 | 1500 | 20 | 8 | **1472 bytes** |
| IPv6 | 1500 | 40 | 8 | **1452 bytes** |
| IPv6, assuming PMTU 1280 | 1280 | 40 | 8 | **1232 bytes** |
| IPv4, assuming PMTU 576 | 576 | 20 | 8 | **548 bytes** |

The table above assumes basic IP headers with no extension/option headers and no tunnel overhead. With Spring Integration `check-length=true`, you must **subtract 4 more bytes** from the budget available for the **application payload**.

For instance, on an IPv6 PMTU of 1280, the calculated max UDP payload is 1232 bytes. With a 4-byte prefix, the calculated max application payload is **1228 bytes**.

### 4.2. Why do many systems choose small messages?

Some applications choose **around 1200 bytes or less** as a UDP payload budget for networks with unknown PMTU, aiming to avoid fragmentation in many common IPv6 scenarios. This is only a **conditional design convention**, not a guarantee across all networks: IPv4 paths can have lower path MTUs; VPN, GRE, IPsec, or overlay networks further reduce the payload budget. RFC 8085 recommends that applications avoid sending datagrams that cause IP packets to exceed PMTU and use PMTU information or PMTU discovery where appropriate.

For a simple telemetry system, choosing **512 bytes of business payload** is usually plenty for small records and easy to control. The value 512 in this lesson is an **illustrative contract**, not a UDP limit or a Spring Integration default.

### 4.3. Why does fragmentation hurt reliability?

Suppose an application produces a UDP packet that IP must split into multiple fragments:

~~~mermaid
flowchart TD
    U["Large UDP datagram"] --> F["IP fragmentation"]
    F --> A["Fragment 1"]
    F --> B["Fragment 2"]
    F --> C["Fragment 3"]
    A --> R["IP reassembly at destination host"]
    B --> R
    C --> R
    R --> D["Complete UDP datagram<br/>delivered to socket"]
    X["One fragment lost"] -.-> C
~~~

The IP receiver needs every fragment to reassemble the complete datagram. If a single fragment is lost or blocked by a firewall/NAT, **the entire datagram** may never reach the UDP socket. **IPv4** supports fragmentation at the source and certain routers depending on circumstances; with **IPv6**, routers do not fragment packets on the fly—the source must respect PMTU limits or use supported fragmentation mechanisms.

This explains why **increasing buffers in Spring Integration cannot rescue a datagram lost before reaching the socket**.

## 5. Two buffer layers on the UDP inbound adapter

Spring Integration has two easily confused attributes:

| XML attribute | Java DSL | Applied layer | When too small |
|---|---|---|---|
| `receive-buffer-size` | `receiveBufferSize(n)` | Data capacity of **one `DatagramPacket`** when the adapter calls receive | Incoming datagrams may be **truncated**, and the remainder cannot be read on the next receive |
| `so-receive-buffer-size` | `soReceiveBufferSize(n)` | Socket/kernel receive buffer | Under rapid packet bursts, the kernel queue can fill up and **drop datagrams** |

Example:

~~~yaml
application-contract:
  max-payload-bytes: 512
transport:
  datagram-receive-buffer-bytes: 2048
  requested-socket-receive-buffer-bytes: 262144
~~~

This is a **policy illustration**; these YAML keys do not automatically configure Spring Integration. Implementers must wire them into the adapter or Java DSL.

If the application caps payloads at 512 bytes, why might you still use a **2048-byte** receive buffer? Because the receiver gets the chance to **receive intact and deliberately reject** packets between 513 and 2048 bytes, instead of truncating at 512 and losing visibility into how many bytes the sender transmitted.

For datagrams larger than the buffer, without length-detection framing, the receiver does not necessarily know truncation occurred: a 4096-byte packet may simply hand 2048 bytes to the adapter. **The application cannot "read the remainder" of the same datagram in the next receive call.**

### 5.1. Socket receive buffer does not replace packet buffer

Suppose the kernel holds many packets in the socket receive buffer, yet the adapter allocates only 256 bytes per `DatagramPacket`. An 800-byte packet **can still be truncated** when the socket hands data to the adapter. Increasing `so-receive-buffer-size` while keeping `receive-buffer-size=256` will not fix this cause.

Conversely, setting `receive-buffer-size=4096` while a handler takes 500 ms per packet and the sender emits 5,000 packets/sec means the kernel still may not retain all datagrams.

### 5.2. Do not assume socket buffer size is applied verbatim

`so-receive-buffer-size` is a **requested value** passed to the operating system; the OS may adjust it according to system limits and socket implementation. Never use the configured number to claim the kernel actually allocates that exact byte count.

Similarly, `so-send-buffer-size` on outbound relates to the sending socket, not business datagram size; increasing the send buffer does not turn UDP into a transport with retries, ACKs, or delivery guarantees.

## 6. Java DSL configuration: receiver with explicit limits

Example using Spring Boot and Spring Integration IP. If Spring Boot manages dependency versions, you typically do not specify versions manually:

~~~xml
<!-- Inside <dependencies> of pom.xml -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-ip</artifactId>
</dependency>
~~~

Create an inbound adapter listening on `12015` with a 2048-byte datagram receive buffer and a requested 256 KiB socket receive buffer:

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
public class UdpPacketSizeConfig {

    public static final int PORT = 12015;

    @Bean("udpRawPayloads")
    public MessageChannel udpRawPayloads() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow udpReceiverFlow() {
        return IntegrationFlow.from(
                    Udp.inboundAdapter(PORT)
                        .receiveBufferSize(2048)
                        .soReceiveBufferSize(262_144)
                        .lengthCheck(false))
                .channel("udpRawPayloads")
                .get();
    }
}
~~~

**Meaning of the options:**

1. `receiveBufferSize(2048)` reserves space to receive a datagram up to 2048 bytes per adapter configuration; larger data still risks truncation.
2. `soReceiveBufferSize(262_144)` requests increased kernel capacity to absorb packet bursts, subject to OS capability.
3. `lengthCheck(false)` uses **raw datagrams**. PowerShell, Python, or device senders unaware of Spring Integration framing can send UTF-8 directly.
4. `MessageChannel` is the boundary between UDP reception and business processing. With `DirectChannel`, downstream handlers should execute fast operations or hand off to an appropriate processing layer to avoid bottlenecks.

**Do not use a poller to receive individual datagrams:** the inbound UDP adapter actively listens on the socket. A poller before or after the flow only appears if another component requires polling, such as files, a database, or a `QueueChannel`.

## 7. Checking byte[] at the business layer

The adapter does not inherently know the telemetry schema or the 512-byte business limit. Create a service activator that enforces limits before decoding:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

@Component
public class UdpPayloadGuard {

    private static final Logger log =
            LoggerFactory.getLogger(UdpPayloadGuard.class);
    private static final int MAX_PAYLOAD_BYTES = 512;

    @ServiceActivator(inputChannel = "udpRawPayloads")
    public void accept(Message<byte[]> message) {
        byte[] bytes = message.getPayload();

        if (bytes.length == 0 || bytes.length > MAX_PAYLOAD_BYTES) {
            log.warn("UDP payload rejected, observedBytes={}", bytes.length);
            return;
        }

        final String text;
        try {
            text = StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(bytes))
                    .toString();
        } catch (CharacterCodingException ex) {
            log.warn("UDP payload rejected: invalid UTF-8");
            return;
        }

        // Example: full business schema not yet parsed.
        log.info("UDP payload accepted: bytes={}", bytes.length);
        processTelemetry(text);
    }

    private void processTelemetry(String payload) {
        // Real application: validate schema, version, sensor ID, seq...
    }
}
~~~

This is a **size and UTF-8 guard**, not a full validator. Downstream steps still need to verify `v`, `sensor`, `seq`, temperature bounds, device identity, and deduplication policy. Avoid logging entire payloads in production when data is sensitive or packet rates are high.

**An important limitation:** if a 4096-byte datagram is truncated down to 2048 bytes at the receiving layer, the guard sees 2048 bytes and rejects it for exceeding 512. However, for a contract that allows 4096 bytes with a smaller receive buffer, the guard could accidentally accept a **truncated payload** if the leading bytes happen to look valid. Detecting truncation reliably requires compatible length-checking/framing or a data contract containing checksums, length, signatures, and sequences as needed.

## 8. Enforcing size limits before sending UDP outbound

Checking on the **sender** avoids wasting bandwidth on payloads guaranteed to be rejected by the receiver.

Example of a publisher sending UTF-8 `byte[]` to a `MessageChannel`:

~~~java
import java.nio.charset.StandardCharsets;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
public class UdpTelemetryPublisher {

    private static final int MAX_PAYLOAD_BYTES = 512;
    private final MessageChannel outbound;

    public UdpTelemetryPublisher(
            @Qualifier("udpToCollector") MessageChannel outbound) {
        this.outbound = outbound;
    }

    public void publish(String telemetry) {
        if (telemetry == null) {
            throw new IllegalArgumentException("Missing telemetry");
        }

        byte[] encoded = telemetry.getBytes(StandardCharsets.UTF_8);
        if (encoded.length == 0 || encoded.length > MAX_PAYLOAD_BYTES) {
            throw new IllegalArgumentException(
                    "UDP encoded payload outside 1..512 bytes");
        }

        boolean dispatched =
                outbound.send(MessageBuilder.withPayload(encoded).build());
        if (!dispatched) {
            throw new IllegalStateException(
                    "UDP outbound message was not dispatched");
        }
    }
}
~~~

To wire the publisher into the configuration from section 6, add these two beans **inside the `UdpPacketSizeConfig` class**:

~~~java
@Bean("udpToCollector")
public MessageChannel udpToCollector() {
    return new DirectChannel();
}

@Bean
public IntegrationFlow udpOutboundFlow() {
    return IntegrationFlow.from("udpToCollector")
            .handle(Udp.outboundAdapter("127.0.0.1", PORT))
            .get();
}
~~~

`127.0.0.1` is suitable when testing sender and receiver on the same host. If the application runs inside a container, this loopback resolves **inside the container**, not to the host machine. In real deployments, put the target IP/DNS and port into configuration. A payload successfully dispatched to the outbound handler **does not mean the collector received it**.

### Why enforce limits with byte[] instead of String?

~~~java
String message = "nhiệt-độ";
int javaUnits = message.length();
int utf8Bytes =
        message.getBytes(StandardCharsets.UTF_8).length;
~~~

`javaUnits` and `utf8Bytes` can differ because Unicode characters have a different number of UTF-8 bytes than UTF-16 code units. Use `encoded.length` when checking the UDP byte budget.

## 9. Length check: detecting truncated datagrams

Spring Integration UDP supports the **`check-length`** option. When enabled on **outbound**, the adapter prepends a **4-byte prefix in network byte order** ahead of the data. A correspondingly configured **inbound** adapter uses this length prefix to check against the received datagram, helping detect cases where an undersized buffer clipped the tail of the packet.

~~~mermaid
flowchart LR
    A["Application payload N bytes"] --> B["Prepend 4-byte length prefix"]
    B --> C["UDP datagram carries 4 + N data bytes"]
    C --> D["Receiver checks length"]
    D --> E{"Length matches?"}
    E -->|Yes| F["Forward payload to MessageChannel"]
    E -->|No| G["Handle error per adapter"]
~~~

If the sender sends a **512-byte payload**, the datagram's UDP data section must accommodate **516 bytes** when length check is enabled. Subtract those 4 bytes when calculating your PMTU budget.

### 9.1. Configuring both sides

Java DSL example **replacing** the inbound/outbound configuration from earlier sections:

~~~java
@Bean
public IntegrationFlow lengthCheckedInbound() {
    return IntegrationFlow.from(
            Udp.inboundAdapter(12016)
               .receiveBufferSize(2048)
               .lengthCheck(true))
            .channel("udpRawPayloads")
            .get();
}

@Bean
public IntegrationFlow lengthCheckedOutbound() {
    return IntegrationFlow.from("udpToCollector")
            .handle(Udp.outboundAdapter("127.0.0.1", 12016)
                       .lengthCheck(true))
            .get();
}
~~~

To test this configuration on its own, enable only **one** outbound subscriber and the matching inbound port; do not keep the old outbound subscribed to the same channel unless you intend to alter dispatch behavior.

**Compatibility:** a standard PowerShell receiver simply reads raw bytes and will see the 4-byte prefix if the Spring sender enables `lengthCheck(true)`. Conversely, a Spring receiver with `lengthCheck(true)` receiving raw UTF-8 from a sender will misinterpret the frame. **Both sides must agree on the protocol** before enabling it.

### 9.2. What does length check help with, and what does it not?

| Scenario | Does length check help? | Explanation |
|---|---|---|
| Packet reaches socket but is clipped by a small receive buffer | **Yes** | Actual received length mismatches the declared length |
| Packet completely lost on the network | **No** | There is no packet to inspect |
| IP fragment lost | **No** | The socket usually never receives a complete datagram |
| Packet arrives out of order | **No** | Length prefix contains no sequence number |
| Sender sends invalid schema with matching length | **No** | Does not validate JSON/telemetry |
| Payload tampered with while preserving length | **Insufficient** | Requires proper checksum/signature; length is not authentication |
| Third-party UDP receiver unaware of framing | **Risk of failure** | First four bytes become garbled data |

**Do not confuse `check-length` with ACK.** Spring Integration also provides an `acknowledge` option for application-level confirmation; both sides must support the right protocol. Even a technical ACK does not necessarily mean a receiver transaction has committed.

## 10. Testing with PowerShell: 511, 512, 513, and 2049 bytes

For the **`lengthCheck(false)`** configuration on port `12015`, start the Spring Boot application and use PowerShell to send raw packets. Each payload consists of ASCII `'A'` characters, so **one character equals one UTF-8 byte**:

~~~powershell
$client = [System.Net.Sockets.UdpClient]::new()
try {
    foreach ($size in @(511, 512, 513, 2049)) {
        $data = [byte[]]::new($size)
        for ($i = 0; $i -lt $size; $i++) {
            $data[$i] = 65  # ASCII 'A'
        }

        [void]$client.Send($data, $data.Length, "127.0.0.1", 12015)
        Write-Host "Sent UDP payload bytes: $size"
    }
}
finally {
    $client.Dispose()
}
~~~

**Expected receiver behavior on a single host without packet loss:**

| Sender payload | Adapter receive buffer | 512-byte business guard | Expected result |
|---|---:|---:|---|
| 511 bytes | 2048 bytes | Size valid | Forwarded; still requires schema validation |
| 512 bytes | 2048 bytes | Size valid | Forwarded; still requires schema validation |
| 513 bytes | 2048 bytes | Over limit | Guard rejects and increments invalid metric |
| 2049 bytes | 2048 bytes | Over limit | May be truncated at receive; guard still rejects if observed > 512 |

The test above uses payload `AAAA...`, which **fails the telemetry schema** if the application implements a full validator. The table results describe only the **size-check step**, not the full business pipeline.

**Observation limitation:** with length check disabled, if a 2049-byte datagram is truncated to 2048 bytes, the handler might simply log `observedBytes=2048`; it cannot safely claim the sender sent exactly 2048 bytes. To prove truncation, re-test using a sender/receiver pair with a compatible length prefix and observe the checker's output.

In a performance test, include `seq` in the payload, send many packets, and compare received sequence numbers. A successful PowerShell `Send` call only indicates the sender OS accepted the send call, not that the receiver processed it.

## 11. Distinguishing three commonly conflated failures

~~~mermaid
flowchart TD
    A["Sender has a datagram"] --> B{"Did datagram reach socket?"}
    B -->|No| C["Packet loss / fragmentation / firewall"]
    B -->|Yes| D{"Did adapter read full datagram?"}
    D -->|No| E["Receive buffer too small / truncation"]
    D -->|Yes| F{"Payload within business contract?"}
    F -->|No| G["Reject per schema/byte limit"]
    F -->|Yes| H["Business processing"]
~~~

| Failure category | Symptoms | How to verify |
|---|---|---|
| **Packet loss before socket** | Sender called send, receiver got no message | Packet captures at both ends, firewall, MTU/fragments, missing sequence numbers |
| **Truncated on receive** | Handler sees fewer bytes than sent; length may coincidentally match buffer size | Check `receive-buffer-size`, enable compatible length check, compare capture vs. payload |
| **Exceeds business limit** | Message arrives intact but `byte[].length > MAX_PAYLOAD` | Receiver guard and invalid-size metric |
| **Kernel/handler overload** | Missing messages at high send rates | Throughput metrics, kernel UDP drop counters, processing duration, queues |
| **Invalid charset/schema** | Byte count is valid but decode or parse fails | Use strict UTF-8 decoder, version/field validators |
| **Spring Integration framing mismatch** | Length check enabled on one side only, 4 strange bytes or length check failure | Compare sender/receiver `check-length` settings |

Do not treat raising buffers as a universal fix for every failure. Whether the root cause is in-transit packet loss, receive-layer truncation, or contract rejection leads to very different remedies.

## 12. Throughput and resource limits

Bytes per packet is only one part of the problem. With UDP, **packets per second**, concurrent handler count, bytes per packet, and processing duration all affect the risk of data loss.

For example, if a receiver averages **5 ms** per message on a single-threaded synchronous path, that equals an ideal ceiling of roughly **200 messages/second** assuming no other latency. If a sender emits 2,000 datagrams/second, kernel buffers can only absorb bursts briefly and cannot compensate for sustained congestion.

**Practical design should include:**

- Enforcing byte limits on the **sender** before dispatch, even when the receiver also validates.
- `receive-buffer-size` large enough to accept contract-compliant datagrams (including the 4-byte prefix if used), with reasonable headroom to classify oversized packets.
- `so-receive-buffer-size` tuned via load testing, checking how the OS honors it.
- Fast receiving handlers that avoid heavy work blocking the receive path; hand off to a **bounded** executor/queue with a full-queue policy.
- Producer rate limiting, application-layer batching, or using a broker when durable storage/replay is needed.
- Metrics at **sender, receiver, network, and business layers**, especially missing sequence ratios.
- Distinguishing **UDP acknowledgment** (if any) from **business ACK** and durable persistence.

Switching from `DirectChannel` to asynchronous processing can free the socket reader sooner, yet adding a queue introduces memory bounds, latency, and backpressure concerns downstream. No channel configuration can synthesize delivery guarantees out of a UDP network.

## 13. What if a business message exceeds the chosen limit?

There are four main approaches:

| Approach | When suitable | Trade-offs |
|---|---|---|
| **Shrink payload**: drop unneeded fields, compact schema, use binary encoding | Telemetry only needs a few fields | Requires version/schema management and hurts human readability |
| **Compress content** | Highly repetitive payloads large enough to offset overhead | Higher CPU cost, decompression limits, risk of incompressible payloads |
| **Application-level chunking** | Mandatory reason to stay on UDP and chunked transfers | Requires message ID, chunk index, total, timeouts, deduplication, reassembly limits |
| **Switch transport**: HTTP, TCP, JMS/AMQP/Kafka, or file/SFTP as appropriate | Large data, requires confirmation/persistence/replay | Higher connection/broker/integration complexity |

### 13.1. Application-level chunking differs from IP fragmentation

If a large message must be split across multiple small datagrams, each chunk needs a **message ID**, **chunk index**, **total chunk count**, and an integrity check. The receiver needs an assembly timeout, per-sender memory caps, missing-chunk policies, and deduplication.

~~~text
msgId=ab12;part=1/3;data=...
msgId=ab12;part=2/3;data=...
msgId=ab12;part=3/3;data=...
~~~

The lines above merely illustrate a chunking protocol, **not a format built automatically by Spring Integration**. Splitting at the application layer allows selective chunk retransmission and bounds each UDP packet's size; however, you take responsibility for correctness, security, and resource limits during reassembly.

Never buffer unbounded numbers of chunks in memory waiting for the final packet. An untrusted sender can exploit a reassembly protocol to exhaust RAM.

## 14. Specific scenario: connecting file, HTTP, Kafka, or DB sources to UDP

Suppose an application fetches a large JSON payload from HTTP or Kafka and passes it straight to a UDP outbound adapter. Without checking size **after encoding**, a message that was completely valid in HTTP/Kafka can exceed the UDP budget and cause data loss.

~~~mermaid
flowchart LR
    SRC["File / SFTP / HTTP / JMS / AMQP / Kafka / DB"] --> T["Transform + validate schema"]
    T --> B["Serialize to byte[]"]
    B --> L{"bytes <= MAX?"}
    L -->|Yes| U["UDP outbound adapter"]
    L -->|No| A["Report error / persist / switch transport / chunk"]
    U --> NET["UDP network"]
~~~

When the source is files or a database read on a schedule, the **poller** handles fetching messages from the source; the **UDP outbound adapter** handles sending datagrams and does not replace the poller. For inbound UDP, the adapter emits `Message<byte[]>` to a `MessageChannel` so business logic can validate and forward to other systems.

**Practical rule:** enforce `MAX_PAYLOAD_BYTES` at the UDP boundary, measured in actual serialized bytes. Never expect a MessageChannel, Kafka broker, or HTTP client to resize messages to fit UDP MTU.

## 15. Security and observability

Beyond datagram loss, payload sizing carries resource and security risks:

- **Enforce size, datagrams/second, and sender limits** per policy; never allocate memory blindly from a client-declared length.
- **Do not trust a length prefix alone**: it is external input, not an authentication signature. If a sender declares an absurd length, reject it and avoid allocating buffers of that size.
- **Validate schema and source** before deep processing; UDP source IP/port can be spoofed or altered by NAT.
- **Do not log entire large payloads**. Prefer logging observed byte sizes, error codes, validated request/device IDs, and adapter state.
- **Bound decompression and reassembly** if the system accepts compressed/chunked messages; enforce max decompressed size and timeouts.
- **Protect data** with appropriate authentication/encryption when crossing untrusted networks; plain UDP is unencrypted.
- **Classify metrics**: `udp_send_attempt_total`, `udp_receive_total`, `udp_size_rejected_total`, `udp_decode_error_total`, `udp_business_processed_total`, `udp_sequence_gap_total`.

When building dashboards, track bytes **the sender intended to send**, bytes **the receiver actually observed**, and business completion rates. Avoid high-cardinality labels (such as every dynamic IP:port) in metrics if time-series counts could explode.

## 16. Consolidation exercise

Set up a receiver on UDP `12015` with `receiveBufferSize=2048`, `soReceiveBufferSize=262144`, and a `1..512 byte` payload contract. Record at least three metrics: received packets, size rejections, and successful processing.

### Part A — Size and configuration

1. Send ASCII payloads of 511, 512, 513, and 2049 bytes using PowerShell; record `observedBytes` and how the handler classifies each.
2. Send UTF-8 payloads with diacritics/emoji: verify why `String.length()` is not the actual transmitted byte count.
3. Reduce `receiveBufferSize` from 2048 to 256, send a 500-byte packet, and observe the truncation risk.
4. Increase `soReceiveBufferSize` alone while keeping `receiveBufferSize=256`; explain why truncation can still occur.
5. Enable `lengthCheck` on **both sender and receiver**, induce an intentional truncation test, and verify error detection. Then enable it on only one side to observe the incompatibility error.

### Part B — Calculation and operations

1. With an MTU of 1500, calculate the maximum unfragmented UDP payload for IPv4 and IPv6 without optional headers.
2. Recalculate the application budget when Spring Integration adds a 4-byte length prefix.
3. Suppose a sender emits 1,000 datagrams/second, each with a 512-byte payload: estimate the payload data rate at **512,000 bytes/second**, excluding IP/UDP headers, link overhead, or packet loss.
4. Send packets with `seq` from 1 to 1,000, recording received and missing counts; increase the rate to find the threshold where the system begins dropping packets.
5. Choose a solution for a 20 KB JSON payload requiring reliable delivery: shrink schema, compress, chunk over UDP, or switch transports? State confirmation and recovery requirements if the receiver stops.

**Self-assessment questions:**

- Why might a 1,500-byte payload require fragmentation on a path with a 1,500 MTU?
- What is the difference between `receive-buffer-size` and `so-receive-buffer-size`?
- Why does length check only detect **some truncation cases** and cannot fix packet loss?
- Why must UTF-8 payloads be checked via `byte[].length`?
- What happens if a receiver sets `check-length=true` while the sender sends raw UTF-8?
- When should you reject large payloads, and when should you use a broker or another transport?
- Why is a technical ACK insufficient to prove data was durably committed in a database?

## 17. References

- [Spring Integration Reference — UDP Adapters](https://docs.spring.io/spring-integration/reference/ip/udp-adapters.html): length check, framing, and inbound/outbound examples.
- [Spring Integration Reference — IP Configuration Attributes](https://docs.spring.io/spring-integration/reference/ip/endpoint-reference.html): `receive-buffer-size`, `so-receive-buffer-size`, and socket attributes.
- [RFC 8085 — UDP Usage Guidelines](https://www.rfc-editor.org/rfc/rfc8085): guidance on message sizes, PMTU, fragmentation, and UDP constraints.
- [RFC 8900 — IP Fragmentation Considered Fragile](https://www.rfc-editor.org/rfc/rfc8900): why relying on IP fragmentation is risky and ways to avoid fragmentation.

## Conclusion

**Datagram packet size and payload limits** must be designed across multiple layers: business data **after encoding**, UDP/IP overhead, **Path MTU**, `DatagramPacket` buffers, socket receive buffers, and downstream processing speed. UDP's theoretical limit cannot replace setting explicit byte budgets for each contract.

In Spring Integration, **enforce limits at the sender**, size the **receive buffer appropriately**, **validate `Message<byte[]>` at the receiver**, and only enable `check-length` when both sides agree on framing. Those measures help detect and reduce size-related errors, yet do not turn UDP into a reliable transport. When events are too large or full delivery is mandatory, evolve the delivery architecture with retry/ACK management, a broker, or an appropriate transport while keeping `MessageChannel` as the integration boundary between systems.
