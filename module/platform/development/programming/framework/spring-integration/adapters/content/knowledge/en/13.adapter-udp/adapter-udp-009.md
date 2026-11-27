# Local network broadcast with Spring Integration UDP

## Learning objectives

After this lesson, you will be able to:

- Distinguish **IPv4 UDP broadcast** from unicast, multicast, and message broker publish/subscribe mechanisms.
- Calculate a **directed broadcast address** from an IP/subnet mask and explain the limited broadcast `255.255.255.255`.
- Configure Spring Integration UDP inbound/outbound adapters, `MessageChannel`, and **`SO_BROADCAST`**.
- Send/receive broadcasts using Java and PowerShell across two machines on the same LAN; observe source addresses, firewalls, and interfaces.
- Design a device discovery protocol (*service discovery*) with request IDs, reply limits, and load control.
- Understand limitations regarding packet loss, NAT/VLANs, Wi-Fi, and security, and choose alternatives when spanning multiple subnets or requiring reliable delivery.

This lesson belongs to the **Adapter UDP** chapter of the **SPRING_INTEGRATION_ADAPTERS** module. The module connects external systems into Spring Integration via inbound/outbound adapters, gateways, pollers, and `MessageChannel`, then handles message contracts, errors, and lifecycles when integrating files, SFTP, HTTP, JMS, AMQP, Kafka, and databases. With broadcast, **a sender attempts to transmit the same datagram to multiple hosts within a local network scope**; broadcasting does not mean every receiver received or processed it.

## 1. The problem: finding devices with unknown IP addresses

Suppose a control application needs to discover sensors on a LAN. The application **does not yet know each sensor's IP**, yet all of them are designed to listen on UDP port `12019`.

The sender emits a datagram to the subnet's broadcast address:

~~~text
v=1;type=DISCOVER;requestId=req-001
~~~

Devices that receive and accept the packet can send a **unicast response** back to the sender's source IP/port:

~~~text
v=1;type=OFFER;requestId=req-001;device=node-7
~~~

~~~mermaid
sequenceDiagram
    participant A as Discovery sender
    participant N as IPv4 broadcast LAN
    participant B as Sensor B
    participant C as Sensor C
    A->>N: DISCOVER requestId=req-001
    N-->>B: Datagram if network allows
    N-->>C: Datagram if network allows
    B-->>A: Unicast OFFER
    C-->>A: Unicast OFFER
    Note over A: Collect replies within deadline
~~~

This is an **application-defined example protocol**, not a built-in Spring Integration service. The application must validate version, length, source, deadlines, and duplicates, and must never assume every device will respond.

Broadcast is usually suitable for **initial discovery within a small broadcast domain**. Once the list of device addresses is obtained, subsequent operations can switch to unicast or a transport with explicit confirmation, authentication, and durable storage.

## 2. IPv4 broadcast concepts

**Broadcast** is a method of sending an IPv4 packet to an address representing multiple hosts within a specific network scope. On a typical Ethernet network, an IP broadcast may be encapsulated in a link-layer broadcast frame. Even so, every OS, switch, AP, firewall, and socket enforces its own policies: **you cannot guarantee every machine sees or delivers the packet to the application**.

| Send type | Example target | Receivers | Join group? |
|---|---|---|---|
| Unicast | `192.168.10.25:12019` | One endpoint at the target IP/port | No |
| IPv4 broadcast | `192.168.10.255:12019` for a /24 network | Hosts within the matching subnet if network/sockets permit | No |
| IPv4 multicast | `239.10.20.30:12019` | Hosts that joined the corresponding group | Yes |

**Broadcast differs from multicast.** Multicast uses group addresses and membership; broadcast does not require receivers to join a group. Broadcast also **differs from a message broker**, which can manage consumers, retries, durable queues, or replays via broker mechanisms.

### 2.1. Limited broadcast

`255.255.255.255` is IPv4's **limited broadcast** address. Routers normally **do not forward** this datagram to other subnets. A sender host with multiple network interfaces may select an outgoing path based on routing tables and OS rules; sending to this address **does not mean sending out on every NIC**.

Therefore, in a lab with a known subnet, calculate the directed broadcast for the target interface and verify with packet captures.

### 2.2. Directed broadcast and subnet masks

Suppose host A has IP `192.168.10.23` and mask `255.255.255.0` (CIDR `/24`):

~~~text
Host address:      192.168.10.23
Subnet mask:       255.255.255.0
Network address:   192.168.10.0
Broadcast address: 192.168.10.255
Host range:        192.168.10.1 .. 192.168.10.254
~~~

Bitwise IPv4 formulas:

~~~text
network   = IP AND netmask
broadcast = network OR (NOT netmask)
~~~

Changing the prefix changes the result:

| Host address | Prefix | Subnet | Broadcast |
|---|---|---|---|
| `192.168.10.23` | `/24` | `192.168.10.0/24` | `192.168.10.255` |
| `192.168.10.23` | `/23` | `192.168.10.0/23` | `192.168.11.255` |
| `192.168.10.23` | `/25` | `192.168.10.0/25` | `192.168.10.127` |

Hence `192.168.10.255` **is not the right broadcast for every host** whose IP starts with `192.168.10`. You must read the actual prefix from the interface and apply the calculation; addresses in this lesson are illustrative only.

### 2.3. Broadcast scope and routers

Broadcasts within one VLAN/broadcast domain do not automatically cross into another VLAN. Routers typically block forwarding **directed broadcasts** across subnets to prevent Smurf-style amplification attacks; some Wi-Fi or cloud networks also actively filter broadcasts.

Do not enable directed broadcast forwarding on routers merely for a lab exercise. If an application must discover devices across multiple subnets/VLANs, deploy **one discovery agent per subnet** and aggregate results over HTTP/Kafka/JMS/AMQP or a service registry.

### 2.4. IPv6 has no broadcast

**IPv6 does not support broadcast like IPv4.** IPv6 uses multicast with specific *scopes*, such as the all-nodes link-local address `ff02::1` in appropriate scenarios. You cannot swap an IPv4 broadcast address for an IPv6 string and keep the same socket behavior; IPv6 multicast requires dedicated design, interface configuration, and firewall rules.

## 3. How does Spring Integration support UDP broadcast?

Spring Integration IP provides unicast and multicast UDP endpoints. To send an **IPv4 broadcast**, you can use a **standard UDP outbound adapter** sending datagrams to the broadcast address, combined with the **`SO_BROADCAST`** socket option.

| Component | Role |
|---|---|
| `Udp.outboundAdapter(broadcastIp, port)` | Creates a UDP outbound handler sending bytes to the IPv4 broadcast address |
| `SO_BROADCAST` | Socket option permitting broadcast sends, supported in Java via `DatagramSocket.setBroadcast(true)` |
| `Udp.inboundAdapter(port)` | Creates a UDP inbound listener receiving datagrams on the corresponding port |
| `MessageChannel` | Transfers messages between producers/handlers and socket adapters |
| `@ServiceActivator` | Validates DISCOVER syntax, processes messages, and records the source |
| `IpHeaders.IP_ADDRESS`, `IpHeaders.PORT` | Source IP/port headers observed by the receiver |
| `MulticastSendingMessageHandler` | Used when sending to a **multicast group**, not required for IPv4 broadcast |

~~~mermaid
flowchart LR
    S["Internal producer"] --> CH["MessageChannel"]
    CH --> O["UDP outbound adapter\nSO_BROADCAST"]
    O --> L["LAN subnet broadcast"]
    L --> A["UDP inbound adapter A"]
    L --> B["UDP inbound adapter B"]
    L --> C["UDP inbound adapter C"]
    A --> H1["Handler A"]
    B --> H2["Handler B"]
    C --> H3["Handler C"]
~~~

UDP inbound receives datagrams via sockets and **does not use a poller** to check incoming packets. A poller only appears if upstream is a file, database, or periodically queried source that then forwards data out over UDP.

## 4. Enabling SO_BROADCAST on Java DatagramSocket

Before integrating with Spring, understand the behavior in plain Java:

~~~java
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.nio.charset.StandardCharsets;

public class SendBroadcastOnce {

    public static void main(String[] args) throws Exception {
        String broadcastIp = "192.168.10.255"; // Lab /24
        int port = 12019;

        byte[] payload =
                "v=1;type=DISCOVER;requestId=req-001"
                        .getBytes(StandardCharsets.UTF_8);

        try (DatagramSocket socket = new DatagramSocket()) {
            socket.setBroadcast(true);
            DatagramPacket packet = new DatagramPacket(
                    payload,
                    payload.length,
                    InetAddress.getByName(broadcastIp),
                    port);
            socket.send(packet);
        }
    }
}
~~~

`DatagramSocket.setBroadcast(true)` enables `SO_BROADCAST`. Java may create new sockets with broadcast enabled by default on some operating systems, yet configuring it explicitly reduces environment dependency. Enabling the option or calling `send()` without error **does not prove the packet reached** any machine.

If the application has multiple NICs, route selection and source address binding can affect which path is used. On Wi-Fi, AP client isolation and device power-saving modes can also make broadcast behave differently from Ethernet. Verify with network tools before blaming the adapter.

## 5. Configuring Spring Boot and Spring Integration Java DSL

In Spring Boot with dependency management, declare:

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

### 5.1. Configuring inbound and outbound flows

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
public class UdpBroadcastConfiguration {

    // Example address: replace with the actual broadcast address of the deployment NIC.
    public static final String BROADCAST_IP = "192.168.10.255";
    public static final int PORT = 12019;

    @Bean("broadcastOut")
    public MessageChannel broadcastOut() {
        return new DirectChannel();
    }

    @Bean("broadcastIn")
    public MessageChannel broadcastIn() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow broadcastOutboundFlow() {
        return IntegrationFlow.from("broadcastOut")
                .handle(
                    Udp.outboundAdapter(BROADCAST_IP, PORT)
                       .configureSocket(socket -> socket.setBroadcast(true)))
                .get();
    }

    @Bean
    public IntegrationFlow broadcastInboundFlow() {
        return IntegrationFlow.from(
                    Udp.inboundAdapter(PORT)
                       .receiveBufferSize(2048)
                       .lengthCheck(false))
                .channel("broadcastIn")
                .get();
    }
}
~~~

In this configuration:

1. `broadcastOut` is the input channel for the UDP outbound handler. It transmits nothing until a producer sends a message to it.
2. `Udp.outboundAdapter(BROADCAST_IP, PORT)` specifies the target IP/port; here it is the subnet-calculated **broadcast address**.
3. `.configureSocket(socket -> socket.setBroadcast(true))` configures the outbound adapter's datagram socket to allow broadcast sends.
4. `Udp.inboundAdapter(PORT)` creates the listener. To receive broadcasts, the socket normally needs to bind to an appropriate **wildcard address** (such as `0.0.0.0`) with firewall rules permitting UDP 12019.
5. `receiveBufferSize(2048)` is the capacity for **one datagram**. Payloads larger than the buffer may be truncated.
6. `lengthCheck(false)` uses raw bytes. If the sender enables Spring Integration `check-length=true`, the receiver must support the 4-byte prefix or it will misdecode.

**Whether a sender receives its own broadcast** when running both flows on one host depends on routing and OS behavior. Always test using **two separate machines on the same LAN** to prove packets actually traverse the network infrastructure.

In production, target hosts/ports and allowed subnets must be controlled configuration values rather than demo constants.

### 5.2. A service publishing DISCOVER on valid requests

~~~java
import java.nio.charset.StandardCharsets;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
public class DiscoveryPublisher {

    private final MessageChannel channel;

    public DiscoveryPublisher(
            @Qualifier("broadcastOut") MessageChannel channel) {
        this.channel = channel;
    }

    public String discoverOnce() {
        String requestId = UUID.randomUUID().toString();
        String text = "v=1;type=DISCOVER;requestId=" + requestId;
        byte[] payload = text.getBytes(StandardCharsets.UTF_8);

        if (payload.length == 0 || payload.length > 512) {
            throw new IllegalArgumentException("Invalid UDP payload size");
        }

        boolean dispatched = channel.send(
                MessageBuilder.withPayload(payload).build());

        if (!dispatched) {
            throw new IllegalStateException("UDP message not dispatched");
        }
        return requestId;
    }
}
~~~

Call `discoverOnce()` from an **internal task or rate-limited administrative operation**. Never let a public HTTP endpoint trigger broadcasts arbitrarily: high request rates can flood the entire LAN.

`requestId` correlates OFFERs with DISCOVERs; **it is not an ACK**. `MessageChannel.send()==true` only indicates internal dispatch succeeded, not that any device received it.

### 5.3. A receiver validating and reading source headers

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.ip.IpHeaders;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

@Component
public class DiscoveryReceiver {

    private static final Logger log =
            LoggerFactory.getLogger(DiscoveryReceiver.class);

    @ServiceActivator(inputChannel = "broadcastIn")
    public void handle(Message<byte[]> message) {
        byte[] bytes = message.getPayload();

        if (bytes.length == 0 || bytes.length > 512) {
            log.warn("Discard discovery packet: invalid bytes={}",
                    bytes.length);
            return;
        }

        final String payload;
        try {
            payload = StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(bytes))
                    .toString();
        } catch (CharacterCodingException e) {
            log.warn("Discard discovery packet: invalid UTF-8");
            return;
        }

        if (!payload.matches(
                "v=1;type=DISCOVER;requestId=[A-Za-z0-9-]{1,64}")) {
            log.warn("Discard discovery packet: invalid schema");
            return;
        }

        String ip = message.getHeaders()
                .get(IpHeaders.IP_ADDRESS, String.class);
        Integer port = message.getHeaders()
                .get(IpHeaders.PORT, Integer.class);

        log.info("DISCOVER received from {}:{}, byteCount={}",
                ip, port, bytes.length);

        // If OFFER is needed: verify permissions, rate-limit, and send
        // unicast to the source endpoint via a separate outbound flow.
    }
}
~~~

`IpHeaders.PORT` is the **UDP source port**, which may be the sender's ephemeral port, not listener port 12019. Source IP is observed network info, **insufficient to authenticate a device**. A custom transformer must preserve necessary headers if downstream steps use `ip_packetAddress` to send replies.

This handler only illustrates receiving and validation; it does not send an OFFER automatically. Adding replies requires protocol design, an allowlist of sources, reply rate limits, and spoofing protection.

## 6. Testing across two machines on the same LAN

### 6.1. Illustrative lab setup

~~~text
Host A (sender):   192.168.10.23/24
Host B (receiver): 192.168.10.45/24
IPv4 broadcast:    192.168.10.255
UDP port:          12019
~~~

If real hosts have different addresses or masks, **you must adjust the broadcast IP**. Broadcasting to `192.168.10.255` from a NIC on `10.0.0.0/24` is not a valid test.

### 6.2. Running a PowerShell UDP listener on host B

Use a standalone listener to isolate network issues from Spring application issues:

~~~powershell
$receiver = [System.Net.Sockets.UdpClient]::new(12019)
$receiver.Client.ReceiveTimeout = 15000

try {
    Write-Host "Listening UDP on port 12019 ..."
    $source = [System.Net.IPEndPoint]::new(
        [System.Net.IPAddress]::Any, 0
    )
    $bytes = $receiver.Receive([ref]$source)

    Write-Host "Source: $source"
    Write-Host ([System.Text.Encoding]::UTF8.GetString($bytes))
}
finally {
    $receiver.Dispose()
}
~~~

The receive call waits up to about 15 seconds; if no packet arrives, `Receive` throws a timeout exception. **Do not run the PowerShell listener and the Spring inbound adapter simultaneously on the same host/port** unless you understand OS socket reuse and configure it intentionally.

### 6.3. Sending a broadcast with PowerShell from host A

~~~powershell
$target = "192.168.10.255" # Replace per actual subnet
$port = 12019

$client = [System.Net.Sockets.UdpClient]::new()
$client.EnableBroadcast = $true

try {
    $text = "v=1;type=DISCOVER;requestId=req-001"
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($text)
    [void]$client.Send($bytes, $bytes.Length, $target, $port)

    Write-Host ("Broadcast attempt to {0}:{1}" -f $target, $port)
}
finally {
    $client.Dispose()
}
~~~

When B is listening and the network allows it, B can observe the payload and A's source endpoint. A successful `Send` call on A **does not mean B received it**, much less that every machine on the subnet received it.

With multiple hosts, each receiver must open the right port, have matching firewall rules, and reside in the permitted broadcast domain. Host C without an app listening on the destination port will not produce a `Message` for a business handler even if its NIC sees the broadcast frame.

### 6.4. Testing unicast to isolate failures

While B is listening on UDP 12019, have A send unicast to B's IP:

~~~powershell
$client = [System.Net.Sockets.UdpClient]::new()
try {
    $bytes = [System.Text.Encoding]::UTF8.GetBytes(
        "v=1;type=DISCOVER;requestId=req-002"
    )
    [void]$client.Send(
        $bytes, $bytes.Length, "192.168.10.45", 12019
    )
}
finally {
    $client.Dispose()
}
~~~

| Unicast A → B | Broadcast A → LAN | What to investigate |
|---|---|---|
| Arrives | Arrives | Socket and network path likely work; inspect Spring flow next |
| Arrives | Missing | Broadcast address, `SO_BROADCAST`, Wi-Fi/AP, VLAN, broadcast firewall rules |
| Missing | Missing | Wrong IP/port, process not listening, firewall, or LAN connectivity |
| Missing | Arrives | Destination/route differences or destination-specific firewall; capture to confirm |

Unicast succeeding only proves the **unicast path** works; networks often enforce stricter policies on broadcasts.

### 6.5. Packet captures at both ends

On a Linux machine with network inspection permissions:

~~~bash
sudo tcpdump -ni any 'udp port 12019'
~~~

Verify in order: **which interface A transmits on**, **whether B sees the packet on its NIC**, and **whether B's socket passes the payload into Spring's MessageChannel**. NIC captures can show datagrams subsequently dropped by a host firewall before reaching the process, so do not treat capturing a packet as proof the business handler processed it.

On Windows, use an authorized capture tool per permissions. Do not tweak Spring code before packets even reach the receiver's interface.

## 7. Replying to DISCOVER via unicast: specific requirements

When a receiver sends an OFFER, it should reply to the **observed UDP source address/port**, not broadcast a large OFFER packet back across the subnet.

~~~mermaid
flowchart TD
    A["Broadcast DISCOVER"] --> B["Receiver validates requestId/schema"]
    B --> C{"Valid source and within quota?"}
    C -->|No| X["Ignore + metric"]
    C -->|Yes| D["Build small OFFER"]
    D --> E["UDP unicast to source IP:port"]
    E --> F["Sender aggregates results by requestId"]
~~~

Spring Integration inbound can expose the source address via `IpHeaders.PACKET_ADDRESS`. An outbound handler with a corresponding `destinationExpression`/Java DSL can route to that address, provided the header is preserved and the destination passes policy checks.

**Safety principles for a discovery protocol:**

1. Bound DISCOVER and OFFER sizes, version, request ID format, and permitted host range.
2. Reply only to authenticated/authorized sources when required by the system; UDP source IPs can be spoofed.
3. Limit to one or a small number of replies per `requestId + deviceId`.
4. Add random delay/jitter in environments with many receivers to avoid hundreds of OFFERs arriving simultaneously.
5. Sender collects OFFERs within a **bounded time window**, discarding replies with mismatched request IDs or arriving late.
6. Deduplicate by `requestId + deviceId`, not solely by ephemeral `IP:port`.
7. To fetch detailed info or sensitive data, switch to authenticated unicast rather than putting everything onto broadcast.

Not seeing an OFFER **does not prove a device is offline**: DISCOVER may be lost, OFFER may be lost, or the receiver may reject or drop it due to a firewall.

## 8. UDP limitations affecting broadcast

| Property | Consequence |
|---|---|
| UDP has no default ACK | Sender does not know which hosts received the broadcast |
| Datagrams can be lost | One host receiving while another misses it is normal |
| No ordering guarantee | Multiple DISCOVERs or OFFERs may arrive out of send order |
| No automatic deduplication | Sender retries may cause receivers to reprocess the same request ID |
| No end-to-end backpressure | Excessive broadcasting can saturate the LAN, socket buffers, or handlers |
| Limited datagram size | Large packets risk fragmentation, loss, or truncation |
| No durable subscriptions | Hosts powered on after the broadcast do not automatically receive missed packets |

**Spring Integration's `check-length`** adds a **4-byte** length prefix when configured on both sides. It helps detect some truncated datagrams, **does not retransmit lost packets**, and does not make third-party UDP servers understand the prefix.

Spring Integration UDP's `acknowledge` option targets endpoints speaking the same ACK protocol. Do not assume it generates confirmations from **every host in a broadcast domain** or guarantees each device's transaction committed.

## 9. Security and performance

Broadcasting forces many hosts to examine packets even when not all of them care about the data. Key risks to watch for:

- **UDP reflection/amplification:** a sender spoofing a victim's source IP can cause many receivers to send replies to that victim. Never return large or unlimited OFFERs to unauthenticated sources.
- **Broadcast storms:** many senders continuously emitting DISCOVER packets increase load on the LAN, APs, and all receivers. Apply rate limiting/backoff and cap attempt counts.
- **Source spoofing:** `ip_address` and `ip_port` are network metadata only, not proof of identity.
- **Sensitive payloads:** plain UDP is unencrypted; never put passwords, tokens, or customer data in broadcasts.
- **Untrusted parsers:** check byte limits, UTF-8, version, structure, and field counts before invoking business logic.
- **Log/metric overload:** avoid logging full raw bytes of every packet or creating labels per dynamic `IP:port`; log counts, error classes, and rate-limited samples.
- **Wrong-subnet routing:** never let untrusted users supply arbitrary broadcast addresses to inject packets into the network.

Suggested metrics: `broadcast_send_attempt_total`, `udp_inbound_total`, `discovery_invalid_total`, `discovery_reply_total`, `discovery_timeout_total`, `discovery_unique_devices`. Clearly separate **send attempts**, **datagrams received**, **valid requests**, and **unique responding devices**.

## 10. Lifecycle and real-world deployment

Spring Integration manages inbound/outbound endpoint lifecycles inside `ApplicationContext`. When the inbound UDP adapter is not started/listening or is stopping/restarting, incoming datagrams can be dropped without clear feedback to the sender.

In production deployments:

- Verify exposed UDP ports, bind addresses, and `UdpServerListeningEvent`/`isListening()` state for your adapter version.
- Sockets need the right interface/bind address; binding to loopback alone may miss LAN broadcasts.
- With Docker/Kubernetes, do not assume bridges/VPCs/CNIs forward broadcasts; many platforms restrict or drop them.
- Check Wi-Fi client isolation, VLANs, broadcast filtering, and per-host firewalls.
- On multi-NIC machines, verify the exact broadcast address, route, and interface actually used.
- When stopping a service, do not expect prior broadcasts to be buffered on the network for replay on startup.
- For cross-subnet discovery, run an agent in each subnet or use a registry/broker instead of opening directed broadcast forwarding across routers.

`SO_TIMEOUT` on a receiving socket only limits how long a single `receive()` call waits; it does not make UDP an ACK/retry protocol. Nor can `MessageChannel` recover a datagram that never reached the socket.

## 11. Common configuration errors

| Symptom | Possible cause | How to resolve |
|---|---|---|
| Sender reports success, receiver logs nothing | Wrong subnet, firewall, AP/VLAN, or not listening | Recalculate broadcast, capture on both hosts |
| PowerShell/Java broadcast send fails | Socket lacks `SO_BROADCAST`, OS policy | Enable `EnableBroadcast`/`setBroadcast(true)`, inspect exception |
| Host A receives its own broadcast but B does not | Local loopback differs from actual LAN path | Test across two hosts and capture packets |
| Unicast works, broadcast fails | Network filters broadcast or wrong broadcast IP | Check IP/mask, switch, WLAN, OS firewall |
| Broadcast reaches B but Spring handler misses it | Adapter not listening, wrong bind interface, channel has no subscriber | Check lifecycle, port, and mapping |
| Some hosts receive, others do not | Different VLAN/subnet, firewall, or Wi-Fi isolation | Compare topology, IP/prefix, and per-host packet captures |
| DISCOVER received, no OFFER seen | Reply not implemented, wrong source port, reply blocked | Check `ip_packetAddress`, capture unicast reply |
| Payload starts with strange bytes | Sender enabled length check while receiver expects raw | Align `check-length` framing |
| Overload when many hosts reply | Response implosion, missing jitter/rate limits | Rate-limit replies and enforce deadlines |
| Broadcast works on LAN, fails in cloud | CNI/VPC does not pass broadcast | Use a service registry, HTTP, broker, or discovery agent |

Debug in order: **sender serializes → outbound handler → socket send → receiver NIC → socket receive → inbound adapter → MessageChannel → handler**. Logs at an earlier step do not prove the next step succeeded.

## 12. Comprehensive practice exercise

Set up at least two machines A/B on a permitted test LAN, with a UDP listener on `12019`. If a third machine C is available, use it to observe fan-out.

**Part A — Network and broadcast**

1. Read NIC A's IP/prefix and compute the directed broadcast. For `192.168.10.23/24`, the result must be `192.168.10.255`.
2. Run the PowerShell listener on B and send a DISCOVER from A with `EnableBroadcast = true`.
3. Compare unicast A → B on the same port; use the isolation table to explain cases where only unicast succeeds.
4. Use packet capture to verify source/destination, interface, and packet type at B.
5. Test stopping B's listener and restarting it. Prior packets **are not replayed automatically**.

**Part B — Spring Integration**

1. Create `broadcastOut` and `broadcastIn`, configuring Java DSL inbound/outbound as in the example.
2. Send a `Message<byte[]>` from `DiscoveryPublisher` into `broadcastOut`.
3. Verify `DiscoveryReceiver` validates size, UTF-8, and schema.
4. Log source IP/port from received headers; explain why the source port is not the listener port.
5. Implement a short unicast OFFER back to the sender in the lab, enforcing rate limits and request ID checks.
6. Test schema-invalid, 513-byte, and malformed UTF-8 payloads, recording error metrics.

**Part C — Design and operations**

1. Simulate 30 receivers sending OFFERs simultaneously; propose jitter, deadlines, and deduplication.
2. Move B to another VLAN: explain why broadcast does not automatically cross routers and design an agent/registry.
3. Design a discovery approach if the network is IPv6-only.
4. Compare broadcast, multicast, unicast, and brokers when zero event loss is required.
5. If input data comes from file/SFTP/DB read by a poller, identify which step the poller occupies before the outbound adapter.

**Self-assessment questions:**

- Why can you not guess the broadcast IP from just the first three octets of a host address?
- How does `255.255.255.255` differ from a subnet-specific directed broadcast address?
- When can `UnicastSendingMessageHandler` send to an IPv4 broadcast address?
- Does `SO_BROADCAST=true` guarantee every receiver got the datagram?
- Why does IPv4 multicast require group membership while broadcast does not?
- Why do UDP broadcasts typically not traverse across VLANs/routers?
- What happens when hundreds of receivers reply with OFFER simultaneously?
- Why are source IP/port insufficient as a device identifier?
- If discovery is needed on an IPv6-only network, what mechanism must change?
- When should you move from broadcast discovery to a service registry or broker?

## 13. References

- [Spring Integration Reference — UDP Adapters](https://docs.spring.io/spring-integration/reference/ip/udp-adapters.html): Java/DSL inbound/outbound, socket customizer, `check-length`, and ACK.
- [Spring Integration Reference — TCP and UDP Support](https://docs.spring.io/spring-integration/reference/ip.html): role of UDP adapters in the endpoint model.
- [Java DatagramSocket API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/DatagramSocket.html): `setBroadcast`, `SO_BROADCAST`, bind, and receive.
- [RFC 919 — Broadcasting Internet Datagrams](https://www.rfc-editor.org/rfc/rfc919): IPv4 broadcast principles.
- [RFC 922 — Broadcasting Internet Datagrams in the Presence of Subnets](https://www.rfc-editor.org/rfc/rfc922): broadcast and subnets.
- [RFC 2644 — Default for Directed Broadcasts in Routers](https://www.rfc-editor.org/rfc/rfc2644): limits on forwarding directed broadcasts.
- [RFC 8085 — UDP Usage Guidelines](https://www.rfc-editor.org/rfc/rfc8085): load, reliability, sizing, and safety when using UDP.

## Conclusion

**IPv4 broadcast** enables a sender to transmit a datagram across a subnet scope so multiple hosts can receive it when network, socket, and firewall policies allow. In Spring Integration, we use a **UDP outbound adapter targeting the broadcast address**, configure **`SO_BROADCAST`**, and use inbound adapters to feed `Message<byte[]>` into `MessageChannel` for validation and processing.

Broadcast fits discovery in small LANs, yet **does not guarantee all devices receive it**, does not automatically traverse VLANs/subnets, and provides no ACK, durable storage, or replay. Calculate broadcast addresses from actual IP/masks, test across two hosts, rate-limit replies, keep payloads small, authenticate sources when needed, and for broader scopes or critical data, choose unicast, multicast, a service registry, or an appropriate broker.
