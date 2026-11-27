# UDP outbound channel adapter in Spring Integration

## Learning objectives

After completing this lesson, you will be able to:

- Explain how the **UDP outbound channel adapter** converts a Spring Integration `Message` into a datagram sent to an external system.
- Configure **UnicastSendingMessageHandler**, host, port, and the input **MessageChannel** in Java.
- Standardize payloads into `byte[]`, establish a data contract, observe send status, and test with a standalone UDP listener.
- Distinguish between a message being handed to the outbound handler and the destination actually receiving and successfully processing it.
- Evaluate length-check mechanisms, ACKs, error management, socket operations, and choosing between unicast and multicast.

This lesson belongs to the **Adapter UDP** chapter in the **SPRING_INTEGRATION_ADAPTERS** module. This module covers connecting external systems with Spring Integration using inbound/outbound adapters, gateways, pollers, and **MessageChannel**, alongside flows using files, SFTP, HTTP, JMS, AMQP, Kafka, and databases. In that architecture, the UDP outbound adapter handles the final leg: **converting internal messages into UDP packets sent over the network**.

## 1. The problem: forwarding telemetry events to a device or collector

Suppose a Spring Boot service receives sensor data from a database, Kafka, or HTTP, and must then send the latest reading to a monitoring system exposing a UDP interface at `192.0.2.10:9999`. Each event uses a UTF-8 payload:

~~~text
sensor=node-7;tempC=26.5
~~~

There is no need to write `DatagramSocket` in each business service. The application sends a `Message<byte[]>` to a **MessageChannel**; the outbound endpoint receives the message, builds the datagram, and hands it off to the network layer.

~~~mermaid
flowchart LR
    A["HTTP / Kafka / DB / Service"] --> B["Validate and encode data"]
    B -->|"Message<byte[]>"| C["udpOutboundRequests (MessageChannel)"]
    C --> D["UDP outbound adapter"]
    D -->|"UDP datagram"| E["Collector / external device"]
~~~

**UDP outbound is unidirectional.** The adapter does not create a request/reply protocol on its own and does not guarantee the datagram reaches the destination. A send operation that throws no error only reflects send processing in the application and operating system, not confirmation of business recording on the receiving machine.

## 2. What is a UDP outbound adapter?

Spring Integration provides endpoints dedicated to the Internet Protocol. For UDP, the commonly used components are:

- **`UnicastSendingMessageHandler`**: sends datagrams to a target host and port.
- **`MulticastSendingMessageHandler`**: sends datagrams to a multicast group if the network infrastructure and receivers support multicast.
- **`MessageChannel`**: provides the coupling point between the internal producer and the outbound handler.
- **`Service Activator`**: registers a message handler to process messages from an input channel. When the handler is a UDP sender, its main processing task is dispatching datagrams.

Do not confuse an **outbound adapter** with an **inbound adapter**: an inbound adapter opens a listener to receive packets from the network and emits a `Message` into the flow; an outbound adapter receives a `Message` from the flow and sends it out over the network.

| Criterion | UDP inbound | UDP outbound |
|---|---|---|
| Event source | Datagram from the network | Message from the application |
| Connection point | Output channel | Input channel |
| Unicast component | `UnicastReceivingChannelAdapter` | `UnicastSendingMessageHandler` |
| Core configuration | Listening port/interface | Target host and port |
| Result | Message pushed into the flow | Datagram handed to the network stack |
| Needs a poller? | No, receives on arriving packets | No, handler processes when a message arrives; an upstream producer *may* use a poller |

If the upstream source is a file or database polled periodically, **the poller belongs to the source-reading step**. The outbound UDP handler does not need a separate polling schedule per datagram.

## 3. UDP fundamentals to keep in mind when sending

Each `Message` arriving at a UDP outbound handler is typically mapped to one **UDP datagram**. Unlike TCP, UDP has no connection stream, no ordering guarantee, no retransmission guarantee, and no flow control with the receiver.

| Characteristic | Practical impact |
|---|---|
| Independent datagrams | The producer must define message boundaries, payload format, and size limits. |
| Possible packet loss | You cannot treat the return of `send()` as proof that the destination received it. |
| Out-of-order delivery | Add a `sequence` or business timestamp if ordering matters. |
| Possible duplicate packets | The receiver needs an idempotency mechanism if the producer retries or the device resends. |
| No backpressure to sender | Sending too fast can fill buffers in the network stack or receiver and drop packets. |
| Limited datagram size | Keep messages small; avoid IP fragmentation from oversized packets. |
| Unencrypted and unauthenticated | Do not transmit sensitive data over plain UDP across untrusted networks. |

**Do not infer:** “`MessageChannel.send()` returned `true`, therefore the UDP packet was received at the destination host.” With a **DirectChannel**, `true` only indicates that dispatching the message to the subscriber completed per the channel's contract. Even if the outbound handler writes to the socket successfully, the packet can still be dropped in transit or rejected by the receiver.

If the business requirement is “every single event must be reliably received,” consider a more durable delivery mechanism (for example, HTTP with a business response, or Kafka/JMS/AMQP as appropriate) or design ACKs, retries, deduplication, and send-state persistence at the application layer.

## 4. Designing the message contract

The sender must know **what to send**, **where to send it**, and **how the receiving side interprets the data**. Example contract for a datagram:

~~~text
v=1;sensor=node-7;seq=1042;tempC=26.5
~~~

| Component | Recommended convention | Reason |
|---|---|---|
| Encoding | UTF-8 | Sender and receiver decode consistently. |
| Version | `v=1` | Supports schema evolution over time. |
| Sensor ID | `node-7` | Identifies the business source rather than relying solely on IP. |
| Sequence | `1042`, incrementing per device | Helps detect duplicates, late packets, and estimate packet loss. |
| Temperature | `tempC=26.5` | Provides explicit units and consistent decimal formatting. |
| Maximum size | e.g., 512 bytes | Reduces risk of undersized buffers and fragmentation. |
| Invalid values | Clear rejection rules | Prevents the receiver from guessing payload intent. |

A Spring Integration **Message** contains `payload` and `headers`, whereas a datagram is raw network data. Arbitrary headers in a `Message` (such as `sensorId` or `correlationId`) **are not automatically transmitted to the receiving end as payload fields**. If the receiver needs to read a value, place it inside the payload structure or agree on a separate protocol mapper.

In Java, encode explicitly with `StandardCharsets.UTF_8` and send `byte[]`, avoiding reliance on the host's default charset. With JSON/CBOR/Protobuf, serialize and validate the schema before calling the outbound handler.

## 5. Java configuration: sending unicast UDP

The example uses Spring Boot with the **Spring Integration IP** dependency. When using Spring Boot dependency management, let Boot manage compatible library versions.

~~~xml
<!-- pom.xml: declare inside <dependencies> -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-ip</artifactId>
</dependency>
~~~

### 5.1. Specifying host and port

Externalize environment configuration from Java code:

~~~yaml
# application.yml
app:
  udp:
    target-host: 127.0.0.1
    target-port: 9999
~~~

In the test example, `127.0.0.1` is the **loopback of the environment running the application**. If the application runs inside Docker/a container, this address resolves inside the container's network namespace, usually not the host machine. When sending to an actual collector, specify a reachable DNS name or IP of the receiver and allow **UDP on the target port**.

### 5.2. Declaring the channel and outbound handler

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.ip.udp.outbound.UnicastSendingMessageHandler;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class UdpOutboundConfig {

    @Bean("udpOutboundRequests")
    public MessageChannel udpOutboundRequests() {
        return new DirectChannel();
    }

    @Bean
    @ServiceActivator(inputChannel = "udpOutboundRequests")
    public UnicastSendingMessageHandler udpOutbound(
            @Value("${app.udp.target-host:127.0.0.1}") String targetHost,
            @Value("${app.udp.target-port:9999}") int targetPort) {
        return new UnicastSendingMessageHandler(targetHost, targetPort);
    }
}
~~~

Each part has a clear role:

1. `DirectChannel` receives messages emitted by the business service and dispatches them to the registered handler.
2. `@ServiceActivator(inputChannel = "...")` binds the outbound handler to that channel.
3. `UnicastSendingMessageHandler(host, port)` creates a handler that sends unicast UDP to **one preconfigured destination**; the simple constructor does not enable length checking or require ACKs.
4. The handler bean is managed by Spring, so socket resources and the adapter lifecycle are tied to the application context.

**Version note:** importing `org.springframework.integration.ip.udp.outbound.UnicastSendingMessageHandler` applies to **Spring Integration 7.x**. In **6.x**, this class resides in the `org.springframework.integration.ip.udp.UnicastSendingMessageHandler` package. Use the import matching the library version managed by your project; how `MessageChannel` and `@ServiceActivator` are wired remains essentially the same.

### 5.3. Sending messages from the business layer

Create a service that only knows about `MessageChannel`, without touching sockets directly:

~~~java
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
public class TelemetryUdpPublisher {

    private final MessageChannel udpOutboundRequests;

    public TelemetryUdpPublisher(
            @Qualifier("udpOutboundRequests") MessageChannel channel) {
        this.udpOutboundRequests = channel;
    }

    public void publish(String sensorId, BigDecimal temperatureC) {
        if (sensorId == null ||
                !sensorId.matches("[A-Za-z0-9_-]{1,32}")) {
            throw new IllegalArgumentException("Invalid sensorId");
        }
        if (temperatureC == null) {
            throw new IllegalArgumentException("Missing temperature");
        }

        String body = "sensor=" + sensorId
                + ";tempC=" + temperatureC.toPlainString();

        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        if (bytes.length > 512) {
            throw new IllegalArgumentException("UDP payload too large");
        }

        boolean dispatched = udpOutboundRequests.send(
                MessageBuilder.withPayload(bytes)
                    .setHeader("sensorId", sensorId) // Internal header only
                    .build());

        if (!dispatched) {
            throw new IllegalStateException(
                    "Message was not dispatched to outbound handler");
        }
    }
}
~~~

This is a **sending example**; temperature range rules, version/sequence fields, device authentication, and retries should be added per the real contract. `send()` may throw an exception when synchronous processing fails. With `DirectChannel`, `publish()` normally returns after the handler finishes executing the send call, yet the result is still **not an ACK from the collector**.

To send a demonstration packet after the Spring Boot application starts, add the following bean to the configuration:

~~~java
import java.math.BigDecimal;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;

@Bean
public ApplicationRunner demoUdpSend(TelemetryUdpPublisher publisher) {
    return args -> publisher.publish(
            "node-7", new BigDecimal("26.5"));
}
~~~

Place the `@Bean` method inside the `@Configuration` class; the imports above are additional imports. This bean is for practice only and will send one packet **every time the application starts**. In production, sending should be triggered by business events, a scheduler, or an appropriate integration pipeline.

## 6. Testing with a standalone UDP listener

A quick verification method is to have another process **listen on UDP 9999** on the same machine. If PowerShell and .NET are available, open a terminal and run the following snippet **before starting the Spring Boot application**:

~~~powershell
$listener = [System.Net.Sockets.UdpClient]::new(9999)
try {
    Write-Host "Listening on UDP 9999..."
    $sender = [System.Net.IPEndPoint]::new(
        [System.Net.IPAddress]::Any, 0
    )
    $bytes = $listener.Receive([ref]$sender)
    Write-Host "From: $sender"
    Write-Host ("Payload: " +
        [System.Text.Encoding]::UTF8.GetString($bytes))
}
finally {
    $listener.Dispose()
}
~~~

The `Receive` call above **blocks** until a datagram arrives, so the terminal will not print a payload immediately. Start Spring Boot with `app.udp.target-host=127.0.0.1` and `app.udp.target-port=9999`. When the demo bean sends, the receiver terminal is expected to print:

~~~text
Listening on UDP 9999...
From: 127.0.0.1:<source-port>
Payload: sensor=node-7;tempC=26.5
~~~

`<source-port>` is the ephemeral source port chosen by the operating system; do not hardcode an assumption that the source port is 9999. When the receiver and Spring Boot run on two different machines, use a routable target address, check firewall/NAT rules, and test from the actual deployment network.

### Checks to keep separate

| Check | What it proves | What it does not prove |
|---|---|---|
| `MessageChannel.send()` returns `true` | Message was dispatched to the subscriber per channel semantics | The UDP packet reached the receiver. |
| No exception when the handler sends | No synchronous error detected on the sending path | The network did not drop the packet, or the collector processed it. |
| Listener receives and prints expected payload | One datagram reached the test endpoint and decoded properly | All subsequent datagrams will arrive; the business system persisted it. |
| Receiver returns a contract-compliant ACK | Received an ACK according to the agreed protocol | Data was durably committed, unless the ACK contract explicitly defines that. |
| Collector stores record with ID/sequence | That specific business flow completed at the collector | Other messages were processed as well. |

## 7. Alternative configuration with Java DSL

If the project prefers DSL, you can describe the outbound endpoint using an `IntegrationFlow`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.ip.dsl.Udp;

@Configuration
public class UdpOutboundFlowConfig {

    @Bean
    public IntegrationFlow udpOutboundFlow() {
        return IntegrationFlow.from("udpOutboundRequests")
                .handle(Udp.outboundAdapter("127.0.0.1", 9999))
                .get();
    }
}
~~~

This configuration follows the same idea: take messages from the `udpOutboundRequests` channel and send UDP to the specified host/port. This is an **alternative approach**—do not configure it simultaneously with the `@ServiceActivator` in section 5 for the same test flow, because doing so creates two subscribers and alters dispatch behavior unexpectedly.

Projects using DSL should still move host/port into environment configuration instead of keeping literal values as in the example. Multi-step flows can add transformers or filters before `.handle(Udp.outboundAdapter(...))`, or connect from adapters receiving files, HTTP, JMS, AMQP, Kafka, and DB data. That keeps transformation and validation logic separate from UDP sending responsibilities.

## 8. Advanced options: length check, ACK, and dynamic destinations

### 8.1. Datagram length check

Spring Integration supports a **length check** option on both sending and receiving sides. When enabled on outbound, the library **prepends 4 bytes in network byte order** to declare the length. A compatible receiver can compare this number against actual received bytes to detect packets truncated due to undersized buffers.

~~~java
// Example replacing handler creation in section 5:
UnicastSendingMessageHandler handler =
        new UnicastSendingMessageHandler(targetHost, targetPort);
handler.setLengthCheck(true);
return handler;
~~~

This is no longer raw UTF-8 payload at the datagram level: the receiver must understand that prefix and enable the corresponding check mode (`check-length` on Spring Integration inbound). If using the PowerShell listener in section 6 without stripping the 4-byte prefix, the printed string will contain extra leading bytes.

Length check **only helps detect truncation**; it does not recover lost datagrams and does not guarantee successful delivery.

### 8.2. Application-layer acknowledgment

Spring Integration also provides an **`acknowledge`** option for UDP outbound. When enabled, the sender must configure the ACK listening address/port and timeout, and the receiver must support the ACK headers/protocol added to the datagram by the library. A compatible Spring Integration receiver is the typical scenario; an arbitrary UDP server will not automatically understand these headers.

ACKs are useful when you need to know the receiver responded according to a **protocol convention**. They still do not automatically prove the data was written to a DB or processed exactly once. You must clearly agree on when the ACK is sent and what happens on timeout: retries can create **duplicate packets**.

Do not enable `acknowledge` or `check-length` for a sender targeting a third-party receiver without confirming the binary framing contract with them.

### 8.3. Per-message dynamic host/port

Configuring a fixed host/port is appropriate when the application sends to a single collector. For multiple devices/destinations, Spring Integration also supports a **destination expression** to select the target address dynamically at runtime based on the message. The destination expression must evaluate to a supported address type, such as a `SocketAddress`, URI, or URI string in the syntax required by the endpoint.

When routing by headers, you must **validate against an allowlist of permitted destinations**. Never let untrusted input arbitrarily choose IP/port targets, as the application could be abused to send UDP packets to third-party systems.

**Another advanced case:** using `socket-expression` to send through the same socket as an inbound receiver, which is useful when replying to a UDP client behind NAT using the port the client originally sent to. This option has constraints regarding multicast and acknowledgment; check the documentation for your specific version before implementing. It does not automatically turn the outbound adapter into a request/reply gateway.

## 9. Multicast: sending to a group of receivers

**Unicast** sends to a single target address. **Multicast** sends to an IP group address; receiving devices must join the group and the network infrastructure must allow multicast.

~~~mermaid
flowchart LR
    A["Spring Integration publisher"] --> B["Multicast UDP group"]
    B --> C["Receiver A"]
    B --> D["Receiver B"]
    B --> E["Receiver C"]
~~~

For multicast, Spring Integration provides `MulticastSendingMessageHandler`. Configuration typically requires the multicast address, port, appropriate network interface, and TTL scope; receivers must configure corresponding group joins. A single multicast send does not guarantee every receiver sees the datagram.

Multicast fits certain types of notifications and data distribution inside controlled networks. If you must ensure every subscriber receives every event, consider a pub/sub broker or a delivery design with proper ACKs, tracking, and retries.

## 10. Error handling, backpressure, and lifecycle

A solid outbound design distinguishes errors **before sending**, errors **during sending**, and failures **after the packet leaves the sender**.

| Error category | Examples | How to handle |
|---|---|---|
| Validation/encoding | Invalid sensor ID, malformed JSON, oversized payload | Reject before the adapter, measure invalid rate, and do not retry infinitely. |
| In-app dispatch | Channel has no subscribers, handler throws an exception | Monitor exceptions and endpoint status; apply retries based on error type. |
| Local socket/network | Unresolvable host, send failure, misconfigured network | Log the specific exception, verify DNS/network and retry conditions. |
| Network/receiver | Firewall, packet loss, receiver down, full buffer | Sender usually cannot tell; requires receiver metrics or an ACK protocol. |
| Receiver business processing | Valid parse but DB unavailable | Requires an explicit business response or durable storage prior to confirmation. |

**MessageChannel and load:** if the producer generates thousands of messages/second, `DirectChannel` performs synchronous dispatch and usually executes the send on the caller thread. When upstream needs asynchrony, you can use an executor/queue channel or an intermediate broker, but you need bounded queues, overload policies, and durable persistence if messages cannot be lost.

**Retries:** sender-side retries must follow business policy and error classification. Do not blindly retry every timeout without a `messageId`/`sequence`, as the receiver may already have received the first packet. Nor should failed packets be buffered infinitely in memory. For mandatory delivery, combine a durable outbox/queue, business ACKs, and receiver-side deduplication.

**Lifecycle:** Spring manages starting/stopping the outbound handler, though this does not guarantee the network is always reachable for sending. When deploying, verify target DNS, routes, firewalls, network policies, and interface configuration, especially in containers/Kubernetes. Instrument metrics to know how many sends the system **attempted**, how many **synchronous errors** occurred, and, if applicable, how many the receiver **acknowledged**.

## 11. Security and observability

Plain UDP does not include built-in authentication or data encryption. Therefore:

- Send data only to an allowlisted set of hosts/ports and over networks suited to the sensitivity level.
- Do not use source IP or easily spoofable header info as trusted identity without application-layer authentication.
- If tamper-proofing and replay protection are required, consider signatures/HMAC or a protected transport protocol; validate nonces, timestamps, and sequences per policy.
- Enforce payload size limits, send rate limits, and log levels; never write security keys or sensitive payloads into debug logs.
- Measure prepared messages, dispatched messages, synchronous send errors, and target reception rates. When ACKs exist, separate technical ACKs from business-processing confirmations.

A dashboard showing only `udp_sent_total` on the sender can be misleading. Preferably, also track `udp_received_total`, `udp_invalid_total`, and `udp_business_processed_total` on the receiver, correlated by instance/device or sequence where appropriate.

## 12. Common configuration issues

| Symptom | Common cause | How to verify |
|---|---|---|
| Handler runs but collector gets no data | Wrong host/port, firewall, receiver not listening, or packet loss | Test with a standalone UDP listener; run packet captures at both ends. |
| Works locally, fails inside Docker | `127.0.0.1` inside a container points to the container itself | Use a DNS name or IP reachable from the container network. |
| Receiver sees strange leading characters | Sender enabled `lengthCheck` but receiver does not strip the 4-byte prefix | Align framing on both sides. |
| `acknowledge=true` times out | Receiver does not support ACKs, wrong ACK host/port, or firewall blocks return path | Check ACK protocol and capture return packets. |
| Duplicate events appear | Producer retries when prior outcome is uncertain | Use ID/sequence and receiver deduplication. |
| Packets lost under high load | Exceeding network or receiver processing/buffer capacity | Rate-limit, measure queues/buffers, shrink packet size, consider another transport. |
| Send succeeds but values are wrong | Sender and receiver differ on charset, numeric format, or schema version | Compare payload bytes and data conventions. |
| Two destinations receive unexpected copies | Multiple subscribers on the channel or duplicated endpoint | Inspect flow configuration, handler count, and channel semantics. |

When investigating, follow the chain **producer builds valid message → channel dispatches → outbound handler sends datagram → receiver gets bytes → receiver confirms business processing**. Each step requires separate evidence, because logs at an earlier step do not prove the next step succeeded.

## 13. Practice exercise

Build an event-sending flow from a simulated service to a UDP collector using this contract:

~~~text
v=1;sensor=node-7;seq=1042;tempC=26.5
~~~

Proceed in order:

1. Configure `target-host` and `target-port` in application properties; create a `DirectChannel` and a UDP outbound handler.
2. Write a publisher producing UTF-8 `Message<byte[]>`, enforcing a 512-byte limit and adding an incrementing `seq` per device.
3. Use the PowerShell listener to receive 3 valid packets; verify exact bytes, ordering, and parsed data.
4. Intentionally send to a wrong host/port; note what the sender can know versus what it cannot know without receiver ACKs.
5. Ramp up sending 1,000 packets with consecutive sequence numbers; measure received packets, duplicate packets, and missing sequence numbers.
6. Discuss options when the collector stops for 30 seconds: drop old data, buffer in a durable queue, retry, or switch transports? Explain the trade-offs and duplication consequences.

**Self-assessment questions:**

- What responsibility does `UnicastSendingMessageHandler` handle that `MessageChannel` does not?
- Does a `MessageHeader` added on the sender automatically appear as a field inside the UDP payload?
- Why can `lengthCheck=true` cause a plain UDP receiver to misread the content?
- Why are a technical ACK and a post-database-commit ACK two different contracts?
- When should you choose multicast, and what network conditions must be satisfied?
- If an upstream producer reads files using a poller and then sends UDP, which part of the flow is the poller responsible for?

## 14. References

- [Spring Integration Reference — UDP Adapters](https://docs.spring.io/spring-integration/reference/ip/udp-adapters.html): configuring unicast/multicast, length check, ACK, Java DSL, and destination expressions.
- [Spring Integration Reference — IP Configuration Attributes](https://docs.spring.io/spring-integration/reference/ip/endpoint-reference.html): meanings of UDP inbound/outbound attributes.
- [Spring Integration Reference — TCP and UDP Support](https://docs.spring.io/spring-integration/reference/ip.html): role of UDP among IP endpoints.

## Conclusion

The **UDP outbound channel adapter** establishes a clean boundary between messages inside a Spring Integration application and datagrams sent to external systems. For a basic unicast flow, you only need a **MessageChannel**, `UnicastSendingMessageHandler`, and a consistent payload contract between sender and receiver. Sources such as HTTP, files, SFTP, JMS, AMQP, Kafka, or databases can feed events into this channel after appropriate transformation.

To use UDP safely and operationally, configure the right target, bound payload size and throughput, handle errors and ACKs intentionally, keep schemas consistent, and remember that **a successful send on the sender does not mean the receiver processed it successfully**.
