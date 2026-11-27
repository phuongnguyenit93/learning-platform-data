# Testing UDP with test channels in Spring Integration

## Learning objectives

After this lesson, you will be able to:

- Explain the role of a **test channel** when testing adapters, gateways, pollers, and `MessageChannel` in Spring Integration.
- Distinguish between decoder unit tests, socketless channel-only tests, and integration tests using real UDP datagrams.
- Use `DirectChannel` as an entry point, `QueueChannel` as a collection sink, and `receive(timeout)` to assert payloads and headers.
- Test `Message<byte[]>`, strict UTF-8, DTOs, `IpHeaders`, contract violation cases, and no-message cases.
- Start a UDP inbound adapter on **port 0**, wait for `isListening()` or `UdpServerListeningEvent`, and send packets via `DatagramSocket`.
- Test outbound UDP using a standalone mock receiver on loopback without needing an external server.
- Use `@SpringIntegrationTest`, `MockIntegrationContext`, wire taps, timeouts, and cleanup properly.
- Avoid flaky tests and avoid drawing false conclusions about UDP delivery guarantees, ordering, or business processing.

This lesson belongs to the **Adapter UDP** chapter of the **SPRING_INTEGRATION_ADAPTERS** module. The module connects external systems using inbound/outbound adapters, gateways, pollers, and `MessageChannel`; practices integrating files, SFTP, HTTP, JMS, AMQP, Kafka, and databases; and handles message contracts, errors, and lifecycles. With UDP, reliable testing must clearly separate **testing internal messages** from **testing datagrams traversing a socket**.

## 1. The problem: from a datagram to a verifiable message

Suppose a sensor sends telemetry to a UDP receiver:

~~~text
v=1;sensor=node-7;seq=42
~~~

Contract:

- Payload is UTF-8, 1 to 512 bytes long.
- `v=1` is the supported version.
- `sensor` is a valid ID; `seq` is a non-negative integer.
- The inbound adapter turns the datagram into a `Message<byte[]>`.
- A transformer creates a `Telemetry("node-7", 42)` DTO.
- Source headers are preserved when the flow needs diagnostics or to reply to the sender.

When writing tests, there are at least three questions:

1. **Does the decoder accurately convert the byte array into a DTO?**
2. **Does the flow route the DTO into the right channel while preserving the right headers?**
3. **Does the real UDP adapter bind a socket, receive a datagram, and produce the right message?**

A single test rarely tests all three well. Split them into layers so any failure points straight to the responsible layer.

~~~mermaid
flowchart LR
    A["UDP DatagramSocket client"] --> B["UDP inbound adapter"]
    B -->|"Message<byte[]>"| C["MessageChannel"]
    C --> D["Validate + Transformer"]
    D -->|"Message<Telemetry>"| E["QueueChannel - test sink"]
    E --> F["JUnit receive(timeout), assert"]
~~~

In this lesson, a **test channel** is a `MessageChannel` placed in the flow so JUnit can collect and assert results. Spring Integration does not mandate a special class named `TestChannel`. `QueueChannel` is a common choice because tests can actively pull messages via `receive`.

## 2. Three testing levels to keep separate

| Level | Input | Real UDP socket? | What it verifies |
|---|---|---|---|
| **Unit test** | `byte[]` passed straight to decode function | No | Length guard, charset, schema, DTO, parse errors |
| **Channel-only test** | `Message<byte[]>` sent to `DirectChannel` | No | Channel wiring, transformer, header propagation, output type |
| **UDP integration test** | `DatagramSocket.send` to inbound adapter | Yes, usually loopback | Binding, listening, UDP mapper, actual received bytes, IP/port headers |
| **Network/LAN test** | Another host, VLAN, firewall, NAT | Yes, over real infrastructure | Connectivity/routing and operation in a test environment |

**Important limitation:** channel-only tests do **not** prove the UDP port was opened; loopback tests do **not** prove UDP always delivers or will work across NAT and firewalls in production.

## 3. Choosing DirectChannel and QueueChannel

APIs to know:

| Type | How it works | Role in tests |
|---|---|---|
| `MessageChannel` | `send(Message)` and `send(Message, timeout)` | Flow entry point |
| `SubscribableChannel` | Delivers messages to registered subscribers | Basis of push channels |
| `DirectChannel` | Dispatches synchronously to handlers | Starts flows in socketless tests |
| `PollableChannel` | `receive()`, `receive(timeout)` | Lets JUnit await results |
| `QueueChannel` | Queue with optional bounded capacity | Test sink collecting messages |
| `PublishSubscribeChannel` | Broadcasts to subscribers | When multiple intentional observation branches are needed |

Minimal example:

~~~java
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

QueueChannel sink = new QueueChannel(8);
sink.send(MessageBuilder.withPayload("ok").build());

Message<?> result = sink.receive(1000);
if (result == null) {
    throw new AssertionError("No message in 1000 ms");
}
System.out.println(result.getPayload()); // ok
~~~

Meaning of timeouts:

- `receive(0)`: returns immediately if available, otherwise `null`.
- `receive(1000)`: waits for a message up to ~1000 ms; normally returns `null` on expiry.
- `receive()`: can wait indefinitely; **avoid in tests because it can hang builds**.

`QueueChannel(8)` has a capacity of 8 messages; when full, send calls may block waiting. **Do not use unbounded queues** to mask bugs that generate too many messages. In a multi-test suite, drain the queue or use separate contexts/queues so messages from one test do not leak into the next.

**Do not confuse timeouts:** `QueueChannel.receive(1000)` waits for a Spring Message; `DatagramSocket.setSoTimeout(1000)` waits for a UDP datagram; a UDP sender's `ack-timeout` waits for a protocol-specific ACK if enabled. They are not the same contract.

## 4. Dependencies for Spring Boot and JUnit 5

Examples use Java 17+, Spring Boot managing library versions, and Spring Integration IP:

~~~xml
<!-- Place inside <dependencies> of pom.xml -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-ip</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

`spring-integration-test` adds `@SpringIntegrationTest` and `MockIntegrationContext`. Examples using `QueueChannel`/`@SpringJUnitConfig` work with just Spring Test and core Spring Integration, while specialized mocking utilities require the extra test dependency.

## 5. Preparing the decoder for standalone testing

Message DTO:

~~~java
public record Telemetry(String sensorId, long sequence) {
}
~~~

Parser validating length, UTF-8, and structure:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public final class TelemetryDecoder {

    private TelemetryDecoder() {}

    public static Telemetry decode(byte[] bytes) {
        if (bytes == null || bytes.length == 0 || bytes.length > 512) {
            throw new IllegalArgumentException("Expected 1..512 bytes");
        }

        final String text;
        try {
            text = StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(bytes))
                    .toString();
        } catch (CharacterCodingException ex) {
            throw new IllegalArgumentException("Invalid UTF-8", ex);
        }

        String[] fields = text.split(";", -1);
        if (fields.length != 3
                || !fields[0].equals("v=1")
                || !fields[1].startsWith("sensor=")
                || !fields[2].startsWith("seq=")) {
            throw new IllegalArgumentException("Invalid telemetry schema");
        }

        String sensorId = fields[1].substring("sensor=".length());
        String seqText = fields[2].substring("seq=".length());

        if (!sensorId.matches("[A-Za-z0-9_-]{1,32}")
                || !seqText.matches("\\d{1,18}")) {
            throw new IllegalArgumentException("Invalid telemetry value");
        }

        return new Telemetry(sensorId, Long.parseLong(seqText));
    }
}
~~~

This is an **illustrative contract**, not a standard for every UDP device. The parser receives bytes and validates them, but cannot know if packets were lost before the socket or truncated by an undersized receiver buffer.

### 5.1. Decoder unit tests

~~~java
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class TelemetryDecoderTest {

    @Test
    void decodesValidTelemetry() {
        byte[] bytes = "v=1;sensor=node-7;seq=42"
                .getBytes(StandardCharsets.UTF_8);
        Telemetry result = TelemetryDecoder.decode(bytes);

        assertEquals("node-7", result.sensorId());
        assertEquals(42L, result.sequence());
    }

    @Test
    void rejectsInvalidUtf8AndLength() {
        byte[] badUtf8 = {(byte) 0xC3, (byte) 0x28};

        assertThrows(IllegalArgumentException.class,
                () -> TelemetryDecoder.decode(badUtf8));
        assertThrows(IllegalArgumentException.class,
                () -> TelemetryDecoder.decode(new byte[513]));
        assertThrows(IllegalArgumentException.class,
                () -> TelemetryDecoder.decode(new byte[0]));
    }

    @Test
    void rejectsUnsupportedVersion() {
        byte[] invalid = "v=2;sensor=node-7;seq=42"
                .getBytes(StandardCharsets.UTF_8);
        assertThrows(IllegalArgumentException.class,
                () -> TelemetryDecoder.decode(invalid));
    }
}
~~~

These tests need no Spring context, making them fast, repeatable, and failing only when the converter or test case is wrong. They do **not** yet verify channel wiring or the UDP adapter.

## 6. Channel-only test: DirectChannel -> Transformer -> QueueChannel

This is the most important test when learning **test channels**. The test manually constructs a `Message<byte[]>` and sends it into a channel configured inside a Spring context.

~~~mermaid
flowchart LR
    T["JUnit builds Message<byte[]>"] --> A["rawUdpInput: DirectChannel"]
    A --> X["TelemetryDecoder"]
    X --> Q["decodedResults: QueueChannel"]
    Q --> V["JUnit asserts DTO and headers"]
~~~

Spring Test example:

~~~java
import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.ip.IpHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.*;

@SpringJUnitConfig(classes = UdpChannelTest.Config.class)
class UdpChannelTest {

    @Configuration
    @EnableIntegration
    static class Config {

        @Bean("rawUdpInput")
        public MessageChannel rawUdpInput() {
            return new DirectChannel();
        }

        @Bean("decodedResults")
        public QueueChannel decodedResults() {
            return new QueueChannel(8);
        }

        @Bean
        public IntegrationFlow decodeFlow() {
            return IntegrationFlow.from("rawUdpInput")
                    .<byte[], Telemetry>transform(
                            TelemetryDecoder::decode)
                    .channel("decodedResults")
                    .get();
        }
    }

    @Autowired
    @Qualifier("rawUdpInput")
    MessageChannel input;

    @Autowired
    @Qualifier("decodedResults")
    QueueChannel results;

    @Test
    void convertsMessageAndPreservesSourceHeaders() {
        byte[] bytes = "v=1;sensor=node-7;seq=42"
                .getBytes(StandardCharsets.UTF_8);

        Message<byte[]> rawMessage = MessageBuilder.withPayload(bytes)
                .setHeader(IpHeaders.IP_ADDRESS, "192.0.2.31")
                .setHeader(IpHeaders.PORT, 53021)
                .build();

        assertTrue(input.send(rawMessage));

        Message<?> actual = results.receive(1000);
        assertNotNull(actual, "No DTO received by test channel");
        assertInstanceOf(Telemetry.class, actual.getPayload());

        Telemetry telemetry = (Telemetry) actual.getPayload();
        assertEquals("node-7", telemetry.sensorId());
        assertEquals(42L, telemetry.sequence());

        assertEquals("192.0.2.31",
                actual.getHeaders().get(IpHeaders.IP_ADDRESS));
        assertEquals(53021,
                actual.getHeaders().get(IpHeaders.PORT));

        assertNull(results.receive(0), "Unexpected extra result");
    }
}
~~~

This test verifies that **Spring context wires the flow properly**, the transformer is invoked, `Telemetry` enters the test sink, and headers are preserved across payload transformation.

**It does not verify real UDP source IPs**: the `192.0.2.31:53021` headers were fabricated by JUnit. Verifying that the adapter maps headers from a `DatagramPacket` requires an integration test over a real socket as shown in the next section.

### 6.1. Testing the flow's error path

For a **synchronous** flow using `DirectChannel`, when the decoder throws an error, the caller typically receives an exception from the dispatch path. Depending on Spring Integration version, the exception may be wrapped in a `MessagingException`.

~~~java
byte[] invalid = {(byte) 0xC3, (byte) 0x28};

assertThrows(RuntimeException.class,
        () -> input.send(
            MessageBuilder.withPayload(invalid).build()));

assertNull(results.receive(100),
        "Invalid packet must not produce a DTO");
~~~

This is an **additional test snippet** for the class above; when running multiple tests in the same context, purge the queue between tests. When switching to an `ExecutorChannel` or asynchronous error channel, exceptions may not propagate back to the caller. In that case, tests must wait on the configured error channel and assert `ErrorMessage`, rather than using the same assumption as `DirectChannel`.

### 6.2. Do not let multiple consumers compete on one QueueChannel

`QueueChannel` has point-to-point semantics: one message is consumed by only one consumer. If a test lets both JUnit and a service activator consume from `decodedResults`, results become **non-deterministic** because the other consumer may grab the message first.

To run the real handler while also observing messages, use a **wire tap** or an intentional pub/sub branch. Never assume adding a second subscriber to `DirectChannel` duplicates messages to both.

## 7. Integration test: sending a real datagram to the UDP inbound adapter

To verify **socket binding, byte arrays, and real IP headers**, start the UDP inbound adapter on **port 0**. Once it is listening, read the assigned port and send a datagram from a `DatagramSocket` over loopback.

~~~mermaid
flowchart LR
    S["JUnit DatagramSocket<br/>client ephemeral port"] -->|"UDP to 127.0.0.1"| U["UnicastReceivingChannelAdapter<br/>port=0"]
    U --> Q["udpPackets: QueueChannel"]
    Q --> A["JUnit receive(3000)<br/>assert bytes + source headers"]
~~~

The example uses **Spring Integration 7.x** imports. In **6.x**, `UnicastReceivingChannelAdapter` is in package `org.springframework.integration.ip.udp`.

~~~java
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.ip.IpHeaders;
import org.springframework.integration.ip.udp.inbound.UnicastReceivingChannelAdapter;
import org.springframework.messaging.Message;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.*;

@SpringJUnitConfig(classes = UdpSocketTest.Config.class)
class UdpSocketTest {

    @Configuration
    @EnableIntegration
    static class Config {

        @Bean("udpPackets")
        public QueueChannel udpPackets() {
            return new QueueChannel(16);
        }

        @Bean("udpReceiver")
        public UnicastReceivingChannelAdapter receiver(
                @Qualifier("udpPackets") QueueChannel packets) {
            UnicastReceivingChannelAdapter adapter =
                    new UnicastReceivingChannelAdapter(0);
            adapter.setOutputChannel(packets);
            adapter.setReceiveBufferSize(2048);
            adapter.setLengthCheck(false);
            return adapter;
        }
    }

    @Autowired
    @Qualifier("udpPackets")
    QueueChannel captured;

    @Autowired
    @Qualifier("udpReceiver")
    UnicastReceivingChannelAdapter receiver;

    @Test
    void receivesRealUdpDatagram() throws Exception {
        long deadline = System.nanoTime()
                + TimeUnit.SECONDS.toNanos(5);

        while (!receiver.isListening()
                && System.nanoTime() < deadline) {
            Thread.sleep(20);
        }

        assertTrue(receiver.isListening(), "Listener not ready");
        int port = receiver.getPort();
        assertTrue(port > 0);

        byte[] bytes = "v=1;sensor=node-7;seq=42"
                .getBytes(StandardCharsets.UTF_8);

        int sourcePort;
        try (DatagramSocket client = new DatagramSocket(
                0, InetAddress.getByName("127.0.0.1"))) {

            sourcePort = client.getLocalPort();
            DatagramPacket packet = new DatagramPacket(
                    bytes, bytes.length,
                    InetAddress.getByName("127.0.0.1"), port);
            client.send(packet);
        }

        Message<?> message = captured.receive(3000);
        assertNotNull(message, "No Message from UDP adapter");
        assertInstanceOf(byte[].class, message.getPayload());
        assertArrayEquals(bytes, (byte[]) message.getPayload());

        assertEquals("127.0.0.1",
                message.getHeaders().get(IpHeaders.IP_ADDRESS));

        Integer ipPort = message.getHeaders()
                .get(IpHeaders.PORT, Integer.class);
        assertNotNull(ipPort);
        assertEquals(sourcePort, ipPort.intValue());

        assertNotNull(message.getHeaders()
                .get(IpHeaders.PACKET_ADDRESS));
        assertNull(captured.receive(0));
    }
}
~~~

In this test, `ip_port` is **compared against the real client's source port**, not the listener's port. The UDP adapter itself populated the source header metadata. The test also checks that the received datagram's byte array matches what was sent.

### 7.1. Why choose port 0?

If port `12017` is hardcoded, another test or running process may already occupy that port. With unicast inbound UDP, passing `0` when constructing the adapter lets the OS allocate a free ephemeral port.

**Only call `getPort()` after the adapter has `isListening()==true`** or after `UdpServerListeningEvent`. Avoid "finding a free port" by opening a temporary socket, closing it, and rebinding; between those two operations, another process can grab the port.

### 7.2. Waiting for readiness properly

The up-to-5-second wait loop in the test mitigates race conditions between Spring context startup and when the test sends packets. Another option is registering a listener for `UdpServerListeningEvent`, awaiting it with a `CountDownLatch`, and reading the port from `event.getPort()`.

If the context has multiple UDP inbound adapters, verify the event belongs to **the right adapter** before using its port. Never use a fixed `Thread.sleep(3000)` as proof the listener is ready; startup times vary across runners.

### 7.3. Why does this test not prove UDP is always reliable?

Even though loopback tests typically pass consistently, UDP still **does not guarantee** datagrams arrive, arrive in order, or arrive without duplicates. This test only shows that **one specific datagram** traversed the adapter into the test sink under test conditions.

To test packet loss, add sequences, sender/receiver metrics, and a network-loss simulation environment. Never conclude every packet on a LAN/cloud will arrive simply because a loopback test passed.

## 8. Testing outbound UDP with a mock collector on loopback

A small UDP receiver owned by JUnit can verify the reverse direction: `Message<byte[]>` flows through the outbound adapter and is transmitted as a **UDP datagram**.

~~~mermaid
flowchart LR
    J["JUnit Message<byte[]>"] --> D["toUdp: DirectChannel"]
    D --> O["Udp.outboundAdapter"]
    O -->|"UDP datagram"| C["Mock DatagramSocket collector"]
    C --> A["JUnit asserts byte[]"]
~~~

Configure a receiving socket on port 0 and pass that port as the outbound target:

~~~java
import java.net.DatagramSocket;
import java.net.InetAddress;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.ip.dsl.Udp;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class UdpOutboundTestConfig {

    @Bean("toUdp")
    public MessageChannel toUdp() {
        return new DirectChannel();
    }

    @Bean(destroyMethod = "close")
    public DatagramSocket testCollectorSocket() throws Exception {
        return new DatagramSocket(
                0, InetAddress.getByName("127.0.0.1"));
    }

    @Bean
    public IntegrationFlow outboundFlow(DatagramSocket testCollectorSocket) {
        return IntegrationFlow.from("toUdp")
                .handle(Udp.outboundAdapter(
                        "127.0.0.1",
                        testCollectorSocket.getLocalPort()))
                .get();
    }
}
~~~

JUnit test:

~~~java
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.*;

@SpringJUnitConfig(classes = UdpOutboundTestConfig.class)
class UdpOutboundTest {

    @Autowired
    @Qualifier("toUdp")
    MessageChannel toUdp;

    @Autowired
    DatagramSocket testCollectorSocket;

    @Test
    void sendsBytesToUdpCollector() throws Exception {
        byte[] sent = "v=1;sensor=node-7;seq=42"
                .getBytes(StandardCharsets.UTF_8);

        testCollectorSocket.setSoTimeout(3000);

        assertTrue(toUdp.send(
                MessageBuilder.withPayload(sent).build()));

        byte[] buf = new byte[2048];
        DatagramPacket packet = new DatagramPacket(buf, buf.length);
        testCollectorSocket.receive(packet);

        byte[] received = Arrays.copyOf(
                packet.getData(), packet.getLength());
        assertArrayEquals(sent, received);
    }
}
~~~

`setSoTimeout(3000)` here is the **test collector UDP socket timeout**, not a `QueueChannel` timeout. Keep those two timeouts separate when reading test reports.

Pros: needs no external collector host and no hardcoded port. Limitation: it only verifies **the packet reached the test socket**, not that an external receiver performed business processing or persisted to a database.

## 9. Wire tap: capturing messages while still running the business flow

If the goal is observing messages **before or after a transformer** without replacing the final handler, use `wireTap` to create a test-only branch.

Example placing the tap before the transformer:

~~~java
@Bean("rawAudit")
public QueueChannel rawAudit() {
    return new QueueChannel(16);
}

@Bean
public IntegrationFlow businessFlow() {
    return IntegrationFlow.from("rawUdpInput")
            .wireTap("rawAudit")
            .<byte[], Telemetry>transform(TelemetryDecoder::decode)
            .handle(telemetryService, "store")
            .get();
}
~~~

**This is an illustrative snippet**, assuming `telemetryService` is an injected bean with a `store(Telemetry)` method. A test can call `rawAudit.receive(1000)` and assert the raw `byte[]`. To assert the DTO, move the tap **after** the transformer and name the channel accordingly.

Notes:

- A tap observes one point in the flow; it does not confirm a database commit.
- The test queue must have finite capacity and be drained after the test.
- If the main flow ends with a non-replying handler, place the tap **before the handler**.
- Never let two consumers compete on the same `QueueChannel` if JUnit must reliably receive messages.
- Having multiple subscribers on a `DirectChannel` does not broadcast messages to all subscribers; use a wire tap or an explicit pub/sub channel.

## 10. @SpringIntegrationTest and MockIntegrationContext

The `spring-integration-test` module provides context testing utilities:

| Tool | Role |
|---|---|
| `@SpringIntegrationTest` | Enables Spring Integration Test Framework support |
| `noAutoStartup` | Prevents specified endpoints from auto-starting, useful when avoiding network binding |
| `MockIntegrationContext` | Controlled replacement of `MessageSource`/`MessageHandler` beans in context |
| `MockIntegration.mockMessageSource(...)` | Supplies mock messages to a flow |
| `MockIntegration.mockMessageHandler(...)` | Captures and simulates message handling |
| `resetBeans()` | Restores endpoints after mocking to avoid affecting other tests |

Example intentionally preventing the UDP endpoint from starting:

~~~java
import org.springframework.integration.test.context.SpringIntegrationTest;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = UdpSocketTest.Config.class)
@SpringIntegrationTest(noAutoStartup = "udpReceiver")
class UdpWithoutNetworkTest {
    // Inject udpReceiver and verify lifecycle does not auto-start.
    // To test logic after inbound, send Message<byte[]>
    // directly into the next channel instead of opening a socket.
}
~~~

For the **real socket test in section 7**, do not apply `noAutoStartup` to the receiver under test. `MockIntegrationContext.substituteMessageHandlerFor(...)` targets a message-consuming endpoint by bean name; do not misuse it to bypass sockets and still claim you tested the UDP network. When mocking, call `resetBeans()` in `@AfterEach`.

Combine approaches by goal:

- Testing parser: **pure unit test**.
- Testing channels/transformers: **`QueueChannel` test sink**.
- Testing UDP mapping: **real `DatagramSocket`**.
- Testing external services with timeouts or side effects: **mock handlers or dedicated test containers**, avoiding production network dependencies.

## 11. Testing errors and missing messages

Scenarios to cover:

| Input or event | Expectation |
|---|---|
| Valid payload | One DTO with exact fields |
| Invalid UTF-8 bytes `C3 28` | Decoder errors, no DTO produced |
| Version `v=2` | Schema rejected |
| Empty `sensor=` | Invalid ID, rejected |
| Non-numeric sequence | Rejected |
| 513-byte payload | Exceeds 512 limit, rejected |
| Nothing sent to QueueChannel | `receive(timeout)` returns `null` |
| Adapter not listening | Readiness check fails with clear message |
| Raw packet sent when receiver enables length check | Possible framing error; both sides must match |
| Sending many packets | Check by sequence/count while respecting UDP limits |

Specifically:

~~~java
assertNull(results.receive(100));
~~~

This assertion only states that **the queue remained empty for up to 100 ms**. It **does not prove a datagram was lost**. The message may still be in flight, currently parsing, rejected, or routed to a different channel.

When verifying errors, assert at **the exact point of failure**: decoder exception, configured error channel, invalid metrics, or controlled logs. Packets lost before the socket **cannot automatically generate an `ErrorMessage`** in Spring Integration.

### 11.1. Testing sequences, reordering, and duplicates

UDP guarantees neither ordering nor exactly-once delivery. When testing sequence handlers, **inject messages directly into a test channel** in intentionally constructed orders:

~~~text
1, 2, 3       -> normal
1, 3, 2       -> gap observed followed by late message
1, 2, 2       -> possible duplicate
boot-42:100,
boot-43:1     -> new epoch, do not merge two sequence ranges
~~~

If running this test over sockets, loopback may deliver in order on many attempts, yet that **is not a UDP guarantee**. For business reliability, use ID/epoch/sequence, ACKs, retries, and idempotency, or use an appropriate broker/transport.

## 12. Reducing flaky tests in CI

| Risk | Mitigation |
|---|---|
| Fixed port already in use | Use port 0 for inbound tests |
| Sending before socket is ready | Wait for `isListening()` or listening event |
| Test hangs indefinitely | Finite timeouts on queues, sockets, and startup |
| Leftover messages from prior test | Drain queues or isolate contexts/test sinks |
| Competing subscribers | Single consumer per test sink or use a wire tap |
| Variable environment delays | Poll conditions instead of blind sleep |
| IPv4/IPv6 mismatch | Consistently use `127.0.0.1` or verify interfaces |
| Unclosed sockets | Try-with-resources, bean destroy, Spring lifecycle |
| CI inside containers | Loopback stays inside container network namespace; test within same process |
| Unsupported LAN/multicast/broadcast | Separate network tests from unit/channel suites |

**Never retry a flaky test infinitely to hide bugs.** When a test fails, log endpoint name, actual port, listener state, source address, byte count, wait duration, and exception type. Never log sensitive payloads or emit metrics with unbounded dynamic `IP:port` labels.

In CI environments blocking UDP binds, **unit tests and channel-only tests** can still run. Open sockets only on runners that support them. Multicast, broadcast, and NAT/VLAN tests belong in labs with matching topologies rather than every default CI runner.

## 13. Observing and interpreting test results

A diagnostic flowchart:

~~~mermaid
flowchart TD
    A["JUnit creates bytes"] --> B{"Send/dispatch succeeded?"}
    B -->|No| E1["Local/channel error"]
    B -->|Yes| C{"Listener is listening?"}
    C -->|No| E2["Lifecycle/bind error"]
    C -->|Yes| D{"QueueChannel received Message?"}
    D -->|No| E3["Socket/mapper/routing/timeout"]
    D -->|Yes| F{"Payload + headers valid?"}
    F -->|No| E4["Framing/decoder/schema"]
    F -->|Yes| G["Assertion PASS"]
~~~

A passing test on `QueueChannel` does not automatically prove a DB transaction committed, especially if the flow uses an async executor or broker. When the goal is verifying **business effects**, assert against the database, verified side-effect mocks, or contract-compliant business ACKs.

In Spring Integration, `MessageChannel.send()==true` only indicates dispatch completion per channel contract; if followed by UDP outbound, the sender **still does not know whether the receiver received the packet**.

## 14. Comprehensive practice exercise

Design a test suite for the flow:

~~~text
UDP inbound -> Message<byte[]> -> TelemetryDecoder
            -> Message<Telemetry> -> Business service
~~~

Tasks:

1. Build `TelemetryDecoder` and test valid inputs, wrong versions, malformed UTF-8, and oversized payloads.
2. Write channel-only tests with `DirectChannel` input and `QueueChannel` sink, asserting DTOs and simulated headers.
3. Verify an invalid packet produces no DTO; distinguish synchronous exceptions from asynchronous error channels.
4. Create a real UDP inbound test using port 0, wait until listening, then send via `DatagramSocket` over loopback.
5. Assert exact byte array, `ip_address`, `ip_port`, and `ip_packetAddress` from the real datagram.
6. Create an outbound flow sending to a `DatagramSocket` test collector bound to port 0; compare received bytes.
7. Add wire taps before and after the transformer, explaining the payload type at each tap.
8. Run tests in parallel groups to uncover leftover queue messages, port collisions, and lifecycle issues.
9. Separate LAN broadcast/multicast tests from the unit suite; identify packet capture tools when needed.
10. If persisting telemetry to a database, write a separate test verifying commit/idempotency rather than relying solely on a test sink.

**Self-assessment questions:**

- Why is `QueueChannel` better suited as a test sink than `DirectChannel`?
- How does `receive(0)` differ from `receive(3000)`?
- Does a decoder unit test verify that the UDP socket bound?
- Why does port 0 reduce test collision risks?
- Why must you wait for `isListening()` or `UdpServerListeningEvent`?
- How do test-fabricated source headers differ from headers from a real datagram?
- Why do two consumers on the same `QueueChannel` make tests flaky?
- Can a mock handler replace UDP network testing?
- Why does `assertNull(queue.receive(100))` not prove packet loss?
- Does a test channel prove a database transaction committed?

## 15. References

- [Spring Integration Reference — Testing support](https://docs.spring.io/spring-integration/reference/testing.html): `@SpringIntegrationTest`, `MockIntegrationContext`, and mocking.
- [Spring Integration Reference — UDP Adapters](https://docs.spring.io/spring-integration/reference/ip/udp-adapters.html): inbound/outbound config, port 0, `isListening()`, events, and length check.
- [Spring Integration Reference — MessageChannel Interfaces](https://docs.spring.io/spring-integration/reference/channel/interfaces.html): `MessageChannel`, `PollableChannel`, `SubscribableChannel`.
- [Spring Integration Reference — MessageChannel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html): `QueueChannel`, `DirectChannel`, timeouts, and capacity.
- [Spring Integration Reference — Configuring Message Channels](https://docs.spring.io/spring-integration/reference/channel/configuration.html): bounded queue channels and configuration.
- [Oracle Java DatagramSocket API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/DatagramSocket.html): bind, receive, send, and `setSoTimeout`.

## Conclusion

**Testing UDP with test channels** lets JUnit capture a Spring Integration `Message` at a defined point in the flow—commonly via `QueueChannel.receive(timeout)`—and assert payloads, headers, and transformation results. This decouples business logic from sockets, keeping tests fast and failures localized.

However, **test channels do not replace UDP integration tests**. Combine decoder unit tests, channel-only tests, and loopback tests with port 0, readiness checks, finite timeouts, resource cleanup, and separate LAN tests. For critical data, also test business ACKs, durable storage, and idempotency. That layered testing approach applies across the other adapters in **SPRING_INTEGRATION_ADAPTERS**, letting each test prove exactly what it is meant to prove without assuming UDP guarantees delivery.
