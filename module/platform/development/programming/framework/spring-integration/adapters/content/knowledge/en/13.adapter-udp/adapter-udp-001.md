# UDP inbound channel adapter in Spring Integration

## Learning objectives

After this lesson, you will be able to:

- Explain the role of the **UDP inbound channel adapter** when bringing data from an external system into a Spring Integration processing flow.
- Distinguish between a **UDP datagram**, a Spring Integration **message**, and the **MessageChannel** that receives the data.
- Configure **UnicastReceivingChannelAdapter**, process byte payloads, and validate the message contract.
- Send UDP packets for testing, observe errors, and identify points where data loss can occur.
- Make sound decisions regarding connection lifecycle, performance, and security for a UDP-receiving system.

This lesson belongs to the **Adapter UDP** chapter of the **SPRING_INTEGRATION_ADAPTERS** module. In the ecosystem of adapters, gateways, pollers, and MessageChannels used to connect external systems to an application, the UDP inbound adapter is the **receiving** point for datagrams from the network, converting them into internal messages so downstream components can continue processing.

## 1. The problem: receiving data from devices over UDP

Suppose multiple sensors send temperature readings every few seconds to UDP port 9999 of a Spring Boot service. A packet has UTF-8 content:

~~~text
sensor=node-7;tempC=26.5
~~~

The application needs to receive it, validate the format, convert it into business data, record it, and optionally forward it to a database or another messaging system.

With plain Java, you could open a **DatagramSocket**, continuously call receive, extract the sender's address, and manually wire socket reception to the business layer. The **UDP inbound channel adapter** encapsulates the network receiving logic and emits a **Message** using the Spring Integration mechanism, so downstream processing after the network boundary does not need to know how to read from a socket.

~~~mermaid
flowchart LR
    A["Sensors / external system"] -->|"UDP datagram"| B["UDP socket :9999"]
    B --> C["UnicastReceivingChannelAdapter"]
    C -->|"Message<byte[]>"| D["MessageChannel"]
    D --> E["Validate / Decode / Transform"]
    E --> F["Service Activator"]
    F --> G["Business processing / storage"]
~~~

**Key distinction:** an inbound adapter is the entry point of the flow; it does not store data on its own, guarantee delivery, or reply to the sender. Those responsibilities belong to other components or other protocols.

## 2. How does UDP affect flow design?

UDP is a **datagram** transport protocol and does not establish a connection like TCP. Each transmission is an independent unit of data. The adapter receives one datagram and supplies the payload for one Spring Integration message.

| UDP property | Consequence for the inbound adapter |
|---|---|
| No connection session or TCP handshake | The adapter listens on a UDP address/port; it does not manage one TCP connection per device. |
| No delivery guarantee | No message is created if a datagram is lost before reaching the receiver. |
| No ordering guarantee | Packet 12 may be processed before packet 11; a sequence number is needed if ordering is a business requirement. |
| Possible duplicate packets | The processing flow should have an identifier key or idempotency mechanism if duplicate recording causes harm. |
| Preserves datagram boundaries | No need to manually split a stream into messages like TCP, but the format inside the payload must still be agreed upon. |
| Limited datagram size | Keep messages small; large packets risk IP fragmentation and losing the entire message if a single fragment is lost. |
| No backpressure to the sender | When the receiving host is overloaded or its buffer is full, datagrams may be dropped without the sender knowing. |

The theoretical limit of a UDP payload over IPv4 is around **65,507 bytes** without IP options; this is not a size you should use by default. Over the Internet, a payload around **1,200 bytes or smaller** is usually a conservative choice to reduce fragmentation risk, though the actual limit must be verified based on the network path and the contract between both sides.

**When to use:** periodic telemetry, measurements that can be refreshed in the next cycle, service discovery in an internal network, or systems that tolerate a defined packet loss rate. **When not to rely on UDP alone:** payments, critical control commands, or events that require exactly-once processing. If the business requires acknowledgments, retries, sequence numbering, and deduplication, you must design those mechanisms yourself or choose a more suitable transport.

## 3. Participating components

**UnicastReceivingChannelAdapter** is the component commonly used to receive unicast UDP traffic. It opens a receiver on a port, receives datagrams, and emits Spring Integration Messages through an output channel.

**MessageChannel** transports messages from the adapter to one or more configured processing steps. With **DirectChannel**, dispatching to subscribers essentially occurs on the calling thread; a slow handler can delay the receiving path.

**Service Activator** receives the message and executes application processing. You can place transformers, filters, routers, error handling, and outbound adapters downstream to complete the integration flow.

| Component | Role in the example |
|---|---|
| UDP inbound adapter | Reads datagrams arriving at port 9999 and emits messages. |
| DirectChannel | Delivers messages from the adapter to the handler. |
| Service Activator | Validates data and processes the sensor record. |
| Outbound adapter or other handlers | As required, writes to a DB, sends to Kafka/AMQP, or calls an external service. |
| Poller | **Not required** for receiving UDP because the adapter is event-driven from the socket; a poller typically appears when the source is a channel or resource that needs periodic polling. |

Spring Integration also supports **multicast** receiving components for cases where devices broadcast to a multicast group. This lesson focuses on unicast: one sender transmits datagrams to the IP address and port of the receiving application.

## 4. Message contract at the UDP boundary

UDP transfers **bytes**; it does not natively provide JSON, UTF-8, schemas, or Java objects. With a simple configuration, the payload that the receiver puts into the flow is **byte[]**. Downstream steps must agree on how to decode and validate the data.

A minimal message contract should clearly specify:

| Contract item | Example | What to validate |
|---|---|---|
| Payload type | UTF-8 bytes | Do not assume every datagram is a valid string. |
| Structure | sensor={id};tempC={value} | Required fields, proper delimiters, and valid data types. |
| Size limit | Maximum 512 bytes | Reject empty or oversized datagrams per business rules. |
| Source identification | IP, port, device ID | Network IP/port are auxiliary info only; device ID must be verified according to system policy. |
| Duplicate and order detection | device ID + sequence | Design this if the business requires it, since UDP does not provide it. |
| Data errors | Record metric and discard | One malformed packet must not break the entire receiving path. |
| Compatibility | Version in payload | Recommended when the protocol or schema is expected to evolve. |

In addition to the payload, Spring Integration can attach **headers** describing the sender's address/port and message metadata. Exact header names, types, and the set of headers depend on the library version and configuration; inspect the actual headers received during integration. Do not treat the UDP source IP address as proof of device authentication because the source address can be spoofed in certain network environments.

A specific option on Spring Integration UDP components is **length check**: the sender and receiver can agree on a length prefix added by the library to detect truncated datagrams. Both sides must use the same convention; if the sender transmits raw UTF-8 as in this example, keep the default configuration and avoid enabling length check on only one side. Even though it checks length, this mechanism does **not** turn UDP into reliable delivery.

## 5. Configuring a UDP inbound channel adapter

The example below uses Spring Boot and Spring Integration Java configuration. Add dependencies compatible with the Spring Boot version in use; with Boot dependency management, you typically do not need to declare versions for individual Spring Integration libraries.

~~~xml
<!-- pom.xml: place inside dependencies -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-ip</artifactId>
</dependency>
~~~

Create an internal receiving channel and an adapter listening on the UDP port:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.ip.udp.UnicastReceivingChannelAdapter;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class UdpInboundConfig {

    // Hardcoded for demonstration; in production, load this from configuration.
    public static final int UDP_PORT = 9999;

    @Bean("udpDatagrams")
    public MessageChannel udpDatagrams() {
        return new DirectChannel();
    }

    @Bean
    public UnicastReceivingChannelAdapter udpInbound(
            @Qualifier("udpDatagrams") MessageChannel channel) {
        UnicastReceivingChannelAdapter adapter =
                new UnicastReceivingChannelAdapter(UDP_PORT);
        adapter.setOutputChannel(channel);
        return adapter;
    }
}
~~~

Explanation of the key lines:

1. **UnicastReceivingChannelAdapter(9999)** creates a unicast UDP receiver on port 9999 of the host running the application. This port must be available and permitted to receive traffic from the relevant network.
2. **setOutputChannel(...)** specifies where messages are pushed after a datagram is received. A producer having an output channel is the core wiring pattern in Spring Integration.
3. The adapter bean participates in the Spring application context lifecycle. When the application starts, the receiver is activated via lifecycle management; when stopping, socket resources are closed through the framework lifecycle.
4. **DirectChannel** fits fast, synchronous processing examples. When processing involves calling slow services or writing high volumes, separate receiving and processing using a channel/asynchronous executor with a bounded queue and an overload handling plan.

There is no need to create a **while(receive)** loop or a **@Scheduled poller** in the application. The adapter handles reading from the socket.

## 6. Processing and validating datagrams

Add a service activator that receives **Message<byte[]>**. The example proactively limits the length and checks the format before using the input data:

~~~java
import java.nio.charset.StandardCharsets;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

@Component
public class UdpTelemetryHandler {

    private static final Logger log =
            LoggerFactory.getLogger(UdpTelemetryHandler.class);

    @ServiceActivator(inputChannel = "udpDatagrams")
    public void handle(Message<byte[]> message) {
        byte[] bytes = message.getPayload();

        if (bytes.length == 0 || bytes.length > 512) {
            log.warn("Discard UDP datagram: invalid size={}", bytes.length);
            return;
        }

        String payload = new String(bytes, StandardCharsets.UTF_8);
        String[] fields = payload.split(";", -1);

        boolean valid = fields.length == 2
                && fields[0].matches("sensor=[A-Za-z0-9_-]{1,32}")
                && fields[1].matches("tempC=-?\\d{1,3}(\\.\\d{1,2})?");

        if (!valid) {
            log.warn("Discard UDP datagram: invalid format");
            return;
        }

        // In production: parse into a DTO, validate thresholds, and forward.
        log.info("Accepted UDP telemetry: {}", payload);
    }
}
~~~

This is an example of **syntax validation** for a small format, not yet a complete business parser. A real application needs to parse the temperature as a number, validate value ranges, enforce device ID constraints, follow decimal conventions, deduplicate if needed, and protect log contents. If the contract uses JSON or protobuf, place the corresponding decoder/schema validator after the adapter; do not mix complex decoding into the socket reading layer.

In Java, constructing a string from bytes using standard UTF-8 may replace malformed bytes with a replacement character. If you must reject any invalid UTF-8 payload, use **CharsetDecoder** with **CodingErrorAction.REPORT** and catch decoding errors. In the example above, the replacement character does not match the validation regex, so the datagram will be discarded.

A complete processing flow could look like this:

~~~mermaid
flowchart TD
    A["UDP inbound adapter"] --> B["MessageChannel"]
    B --> C{"Valid size / decoding?"}
    C -->|No| D["Invalid metric + rate-limited log"]
    C -->|Yes| E{"Valid schema / business rules?"}
    E -->|No| D
    E -->|Yes| F["Strongly-typed telemetry record"]
    F --> G["DB / event broker / further processing"]
~~~

In this model, dropping an invalid packet is a **business decision**. Logging does not mean the sender is notified of the error: the UDP inbound adapter does not automatically generate a response message.

## 7. Testing from a sender machine

Start the application containing the two configuration/handler classes above. Run the following PowerShell command on the same machine to send a UTF-8 datagram to **127.0.0.1:9999**:

~~~powershell
$client = New-Object System.Net.Sockets.UdpClient
try {
    $bytes = [System.Text.Encoding]::UTF8.GetBytes(
        "sensor=node-7;tempC=26.5"
    )
    [void]$client.Send($bytes, $bytes.Length, "127.0.0.1", 9999)
}
finally {
    $client.Dispose()
}
~~~

When the flow is working, the application will log something similar to:

~~~text
Accepted UDP telemetry: sensor=node-7;tempC=26.5
~~~

Try changing the payload to **sensor=node-7;tempC=abc** to verify that the handler detects the format error, or send a message larger than 512 bytes to test the application limit.

If sending from **another machine**, replace 127.0.0.1 with the reachable IP of the machine running the application, open the appropriate UDP inbound rule in the firewall, and check Docker/Kubernetes/network policies if applicable. A successful send operation on the sender side only means the data was handed off to the network stack on the sending host; it **does not prove** the receiver received or processed the datagram.

### Testing layers to keep separate

| Testing layer | How to execute | What it verifies |
|---|---|---|
| Handler | Create valid/invalid byte[] messages and invoke the handler in tests | Format rules, limits, error branches. |
| Adapter + channel | Run Spring context, send datagrams to a test UDP port | Socket → adapter → MessageChannel → handler works. |
| Network environment | Send from a real machine/device, inspect logs/metrics and UDP captures | Firewall, IP, NAT, ports, fragmentation, and real traffic. |
| Load and resilience | Generate many datagrams with incrementing sequences, measure received count | Loss/duplication rates, latency, behavior under processing overload. |

Avoid treating the moment **Send** is called as the moment the system successfully processed the data. If you need to prove each event was processed, design explicit identifiers and acknowledgments at the application layer.

## 8. Error handling and resource limits

A UDP listener that works steadily in testing can still drop datagrams when load increases. Consider three independent error categories:

**Errors before message creation:** packets lost in transit, blocked by a firewall, sent to the wrong port, exceeding socket buffer capacity, or truncated. The Spring Integration handler never receives a message to report an error. Monitor sequence numbers, sender packet counts, and network system metrics if packet loss matters.

**Errors during content conversion:** invalid UTF-8, wrong schema version, missing fields, invalid numbers. You should bound size, validate, and classify bad packets; avoid throwing unhandled exceptions onto the receiving path. For messages needing investigation, consider dead-letter/quarantine *after* a safe record can be constructed, though packets that never reached the application cannot be put into a dead-letter queue.

**Downstream processing errors:** slow database, unavailable broker, handler thread exhaustion, or full queue. With **DirectChannel**, a long-running synchronous handler can prolong dispatch time on the receiving path. You can use a channel with a bounded executor/queue and design an overload policy, though adding a queue still does not make UDP reliable. If downstream retries are needed, you must account for duplicates and message retention time.

Operational configurations and behaviors to consider:

- **Port and bind address:** configure the port via environment variables/application properties instead of hardcoding; specify the network interface to listen on; avoid port conflicts across multiple processes.
- **Datagram size and buffers:** agree on a maximum size between sender/receiver; evaluate socket buffers and fragmentation levels on the real network.
- **Throughput:** configure appropriate processing timeouts, thread counts, queues, and rate limits; do not spawn a new thread per packet.
- **Error channel/handler:** record processing errors in Spring Integration according to the application model; do not mistake internal error handling for sending a UDP error notice back to the sender.
- **Lifecycle:** verify the listener starts after configuration, listens on the right port, and shuts down cleanly when the application stops; with containers, verify UDP port mappings and shutdown grace periods.
- **Observability:** count received datagrams, valid datagrams, discarded datagrams, byte counts, processing durations, and forwarding errors; tag these metrics with host/instance.

## 9. Security when opening a UDP port

A UDP port receiving data from the network is an **untrusted** input boundary. You should not rely solely on source IP addresses because they can be spoofed, especially on infrastructure where you do not control the entire transmission path.

Minimize the attack surface by restricting allowed networks/sources, authenticating messages at the application layer when required, enforcing length limits, validating schemas before forwarding, and avoiding logging sensitive payloads directly. If the protocol uses signatures or HMAC, verify the signature and prevent replay attacks using timestamps/nonces/sequences; this is application or exchange-protocol logic, not a built-in guarantee of the UDP inbound adapter.

Plain UDP is **unencrypted**. For data requiring confidentiality in transit, consider a suitable protected protocol (such as DTLS at the system layer, a protected network channel, or switching transports when requirements allow). Do not assume the Spring Integration UDP inbound adapter adds DTLS automatically.

## 10. Common issues

| Symptom | Common cause | How to isolate |
|---|---|---|
| Startup fails because port cannot be bound | Port already in use by another process, insufficient permissions, or wrong bind interface | Check listening processes and port configuration; choose an available port. |
| Sender succeeds but no logs appear | Wrong IP/port, UDP blocked, no subscriber, packet lost | Test via loopback, check firewall, capture datagrams on the receiving host, and confirm the adapter has started. |
| Payload displays garbled characters | Both sides disagree on charset or format | Inspect actual received bytes, UTF-8 convention, and schema. |
| Some large packets fail or are lost | Fragmentation, small buffers, packet limits | Reduce size, measure network path, align limits with the sender. |
| Packets rejected even though they look right | Both sides differ on framing/length check contract or format | Compare payloads at byte level, verify length check settings on both sides. |
| Packets go missing under increased load | Receive buffer full or downstream processing too slow | Measure send/receive rates, handler duration, queue size; limit load and decouple processing appropriately. |
| Business records duplicated or out of order | Inherent UDP behavior or application retry mechanism | Add sequence/identity, idempotency logic, and clear update rules. |

An effective investigation approach is separating three questions: **did the datagram reach the host?**, **did the adapter emit a message?**, **did the handler process it validly?**. Answering each helps determine whether the issue lies in the network, integration configuration, or business logic.

## 11. Comparison with outbound adapter and other mechanisms

- **UDP inbound adapter:** listens for datagrams, turns network input into messages, and sends them to a channel.
- **UDP outbound adapter/message handler:** takes messages within the application and sends datagrams to a destination. If a UDP reply is needed, you must design a separate sending path and a contract for the reply address/port.
- **Gateway:** a request/reply pattern representing call-and-response interactions over suitable transports/forms. A single inbound UDP datagram does not automatically establish a reliable request/reply flow.
- **Poller:** a schedule triggering message retrieval from pollable sources; UDP socket reception is triggered by arriving packets, so no poller is needed to read individual datagrams.
- **MessageChannel:** abstracts the message transport path between endpoints, making it possible to change processing, routing, or forwarding without rewriting socket protocols.

This aligns with the overall goal of the SPRING_INTEGRATION_ADAPTERS module: connecting files, SFTP, HTTP, JMS, AMQP, Kafka, databases, and network sources into a unified messaging architecture. With UDP, the data contract and packet-loss handling decisions play an especially critical role because the transport does not guarantee delivery.

## 12. Consolidation exercise

Build a receiver for telemetry packets with the following contract:

~~~text
v=1;sensor=node-7;seq=1042;tempC=26.5
~~~

Implementation requirements:

1. Receive UDP on a configured port and keep the payload as **byte[]** up to the validation step.
2. Enforce a size limit, validate UTF-8, version, sensor ID, non-negative integer sequence, and temperature within a valid range.
3. Store the last sequence per device in an in-memory store for testing; clearly define how to handle duplicate and late-arriving packets. Discuss what happens when the application restarts or runs multiple instances.
4. Record metrics for total received, valid, and discarded datagrams; generate test packets that are valid, schema-invalid, duplicate-sequence, and out-of-order.
5. Increase sending speed to observe the difference between **DirectChannel** and a bounded asynchronous processing path; specify the policy when the queue is full.

**Self-assessment questions:**

- Why is a successful send from a UDP client not sufficient to conclude that the data was persisted?
- Why does merely adding a **QueueChannel** not guarantee zero datagram loss?
- When should you use an outbound handler, and when do you need to design application-level ACK/sequence mechanisms?
- Why are the payload contract, length control, and listener lifecycle design decisions just as important as choosing the UDP port?

## Conclusion

The **UDP inbound channel adapter** is the bridge between external datagrams and internal messages in Spring Integration. A basic configuration consists of a **UnicastReceivingChannelAdapter**, a **MessageChannel**, and a handler receiving **Message<byte[]>**; from there, you can add validation, transformation, routing, and other system integration steps.

The quality of a UDP receiving flow is determined by a clear message contract, size and load control, error observability, input source security, and how the application tolerates or compensates for UDP's packet loss, duplication, and reordering characteristics.
