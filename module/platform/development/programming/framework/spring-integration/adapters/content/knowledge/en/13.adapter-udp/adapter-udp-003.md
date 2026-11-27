# Unicast and multicast datagrams in Spring Integration

## Learning objectives

After this lesson, you will be able to:

- Clearly distinguish between **UDP unicast** and **UDP multicast** in terms of target recipients, distribution scope, scalability, and configuration.
- Understand the relationship between a **datagram**, IP address, UDP port, **multicast group**, network interface, TTL, and packet path across the network.
- Configure unicast and multicast UDP inbound/outbound flows using **Spring Integration Java DSL**.
- Explain why a single multicast send does not mean all group members received the packet.
- Test on localhost/LAN and diagnose membership, IGMP, firewall, buffer, and payload format issues.
- Choose the right sending model for business data in an integration system.

This lesson belongs to the **Adapter UDP** chapter of the **SPRING_INTEGRATION_ADAPTERS** module. The module uses adapters, gateways, pollers, and `MessageChannel` to connect external systems with Spring Integration; flows can combine files, SFTP, HTTP, JMS, AMQP, Kafka, and databases. With UDP, what matters is not only adding an adapter, but determining **who receives the datagram**, **whether the network delivers the datagram to them**, and **how the application handles packet loss**.

## 1. UDP datagram: the transport unit for both models

UDP transmits data as **datagrams**. Each time a sender sends a datagram, the operating system builds a UDP packet containing source port, destination port, length, checksum, and payload. The receiver can read one datagram in a single receive call, depending on buffer size.

For example, the application sends a UTF-8 payload:

~~~text
v=1;sensor=node-7;seq=1042;tempC=26.5
~~~

In Spring Integration, a **UDP outbound channel adapter** takes a `Message` from an input `MessageChannel` and sends a datagram; a **UDP inbound channel adapter** receives a datagram and emits a `Message` to an output channel. Payloads are typically handled as `byte[]` before decoding.

Fundamental UDP properties apply to **both unicast and multicast**:

- **No connection session setup** like TCP; datagrams can be sent as soon as the destination address is known.
- **No delivery, ordering, or exactly-once guarantees**; packets may be lost, arrive late, or be processed more than once at the application layer.
- **No end-to-end backpressure**. An overloaded receiver or network may drop packets, usually without the sender knowing.
- **Preserves datagram boundaries**. The receiving side does not have to search for stream delimiters like in TCP, though it must still understand the payload schema.
- **Length limits**. Oversized datagrams are prone to IP fragmentation or truncation when the receiver allocates an insufficient buffer.

From a business perspective, a successful send by the outbound handler **is not** confirmation that the receiver received, decoded, or persisted the data.

## 2. Unicast: a specific network destination

**Unicast** sends a UDP datagram from one endpoint to **one destination IP address and one destination port**.

~~~mermaid
flowchart LR
    A["Application A<br/>UDP sender"] -->|"Datagram to 192.0.2.20:12001"| B["Application B<br/>UDP receiver"]
    C["Application C"]:::muted
    classDef muted fill:#f4f4f4,stroke:#999
~~~

For example: a collector on host `192.0.2.20` listens on UDP port `12001`. The sender configures the exact pair `(192.0.2.20, 12001)` and sends a datagram to that address. If there are 10 different collectors and each needs a copy, the sender or an intermediary component must send separately to each destination.

Unicast is usually suitable for:

- Telemetry from sensors to a fixed collector.
- Commands or events sent to **one** known target device.
- Exchanges over networks with standard IP routing that do not support multicast.
- Models requiring explicit destination management and individual application-level acknowledgments per device.

**Note:** "one destination" describes the IP address and port at the network layer. It does not necessarily mean exactly one process is bound to that port across all OS and network configurations, nor does it guarantee the target process handled the datagram.

## 3. Multicast: one group address, multiple joined receivers

**Multicast** is a model where a sender transmits one datagram to a **multicast group address**. Receivers that want to receive it must **join the group** on the appropriate network interface and listen on the corresponding port. The network infrastructure determines how packets are distributed to interfaces with group members.

Example for IPv4: group `239.10.20.30`, port `12002`.

~~~mermaid
flowchart LR
    S["Spring Integration<br/>multicast sender"] -->|"UDP to 239.10.20.30:12002"| N["Multicast-capable<br/>Switch / Router"]
    N --> A["Receiver A<br/>joined group"]
    N --> B["Receiver B<br/>joined group"]
    C["Receiver C<br/>did not join group"]:::muted
    classDef muted fill:#f4f4f4,stroke:#999
~~~

In a multicast-capable network, the sender **does not necessarily send a separate** datagram to each receiver. Routers/switches can replicate traffic along the appropriate path to deliver it to multiple destinations. Thus, multicast is useful when multiple applications need **the same data stream**.

### 3.1. IPv4 multicast addresses

IPv4 reserves the **224.0.0.0/4** range for multicast (224.0.0.0 to 239.255.255.255). The sample address `239.10.20.30` falls in the **239.0.0.0/8** range reserved for *administratively scoped multicast*, commonly managed for an organization's internal network.

Do not arbitrarily pick addresses in multicast ranges reserved for network protocols or special services. When deploying, coordinate with network administrators to allocate the group, port, and usage scope. This lesson uses **IPv4** for illustration; IPv6 also supports multicast, though addressing representation and scopes differ.

### 3.2. Joining the group is a receiver step

Joining a group expresses interest in receiving packets for a group address, usually paired with a specific **network interface**. In IPv4, mechanisms such as **IGMP** allow hosts to advertise membership to the network; switches with IGMP snooping and multicast routers can forward packets based on membership/routing.

**A group address does not replace the UDP port**: the receiver must join the right group and receive on the port used by the sender. A host with multiple NICs must also pick the right interface, especially when Wi-Fi, Ethernet, VPN, and container networks coexist.

### 3.3. TTL limits dissemination scope

Multicast outbound can set **TTL (Time To Live)**. In IPv4, each forwarding router decrements TTL; a low TTL constrains multicast reach. A TTL of **1** is typically meant for the local network, where routers do not need to forward packets to other networks. Traversing multiple subnets requires multicast routing to be enabled, not just raising TTL.

TTL is a **routing scope limit**, not a security mechanism: receivers within the permitted scope can still observe payloads if they have network reachability and appropriate access.

## 4. Comparison table: unicast vs. multicast

| Criterion | Unicast | Multicast |
|---|---|---|
| Destination address | IP of a specific host | IP of a multicast group |
| Does receiver actively join a group? | No | Yes, on the appropriate interface |
| Sending once to many receivers | Usually must loop over a destination list | The network can distribute copies to members |
| Network infrastructure dependency | Standard IP routing and firewalls | Membership, multicast forwarding, IGMP/snooping, NIC config |
| Usage on Internet/cloud | Typically easier to deploy | Often blocked or unsupported by cloud/VPN/CNI |
| Does sender know who is listening? | Knows configured target address, not processing success | Does not automatically know the list or count of actual receivers |
| Does UDP guarantee delivery? | No | No |
| Best suited for | Sending to one collector/device | Distributing identical telemetry/config/notifications to a group of receivers |
| Business ACK per receiver | Can be designed per destination | Must account for multiple replies, member counts, duplicates/timeouts |

### Multicast is not broadcast

**IPv4 broadcast** sends to a broadcast address range (for example, subnet broadcast), which hosts in that scope may see depending on configuration. **Multicast** uses a group address and a membership mechanism. The two differ in purpose, routing behavior, and switch handling.

Multicast also differs from **publish/subscribe on Kafka or AMQP**: a broker can manage subscribers, persist events, and enforce delivery policies. IP multicast only transmits datagrams over the network and does not provide consumer groups, offsets, durable queues, or replay mechanisms.

## 5. Unicast/multicast in Spring Integration

Spring Integration provides two receiving directions and two sending directions:

| Direction | Unicast | Multicast |
|---|---|---|
| Inbound | `UnicastReceivingChannelAdapter` | `MulticastReceivingChannelAdapter` |
| Outbound | `UnicastSendingMessageHandler` | `MulticastSendingMessageHandler` |
| Java DSL inbound | `Udp.inboundAdapter(port)` | `Udp.inboundMulticastAdapter(port, group)` |
| Java DSL outbound | `Udp.outboundAdapter(host, port)` | `Udp.outboundMulticastAdapter(group, port)` |

These four components are **adapters/message handlers** connecting UDP to Spring Integration's messaging model. Any `MessageChannel` behind inbound or before outbound continues to operate according to its chosen semantics, such as `DirectChannel`, `ExecutorChannel`, or `QueueChannel`.

~~~mermaid
flowchart TB
    O["Application source: HTTP / file / Kafka / DB"] --> C["MessageChannel: toUdp"]
    C --> OUT["UDP outbound adapter"]
    OUT -->|"unicast or multicast datagram"| NET["IP Network"]
    NET --> IN["UDP inbound adapter"]
    IN --> C2["MessageChannel: fromUdp"]
    C2 --> H["Validate / Transform / Service Activator"]
~~~

**A poller is not used to "scan" incoming datagrams**: the inbound UDP adapter receives automatically from socket events. However, an upstream data source may use a poller—for instance, polling files or a database periodically and then sending each record as a UDP datagram.

**Java import version note:** Spring Integration 7.x organizes receiving and sending classes under `org.springframework.integration.ip.udp.inbound` and `org.springframework.integration.ip.udp.outbound`. In 6.x, these classes reside in `org.springframework.integration.ip.udp`. The following examples use **Java DSL** to focus on flow wiring and reduce sensitivity to implementation class package changes.

## 6. Hands-on Spring Integration with Java DSL

### 6.1. Dependencies and data contract

For a Spring Boot project managing dependencies, add:

~~~xml
<!-- Declare inside <dependencies> of pom.xml -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-ip</artifactId>
</dependency>
~~~

Define a simple packet format in UTF-8, up to **512 bytes**:

~~~text
v=1;sensor=node-7;seq=1042;tempC=26.5
~~~

In a real application, parse the schema into a business object, validate length and values, and include version/sequence when tracking loss, duplicates, or reordering. Spring Integration `MessageHeaders` are not automatically copied as datagram payload fields: anything the receiver needs must follow an explicit wire convention.

### 6.2. Configuring inbound and outbound together

The configuration below creates **two receiving paths** and **two sending paths**. Different ports are used to make observation easier while learning:

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
public class UdpDatagramFlows {

    public static final int UNICAST_PORT = 12001;
    public static final int MULTICAST_PORT = 12002;
    public static final String GROUP = "239.10.20.30";

    @Bean("fromUnicast")
    public MessageChannel fromUnicast() {
        return new DirectChannel();
    }

    @Bean("fromMulticast")
    public MessageChannel fromMulticast() {
        return new DirectChannel();
    }

    @Bean("toUnicast")
    public MessageChannel toUnicast() {
        return new DirectChannel();
    }

    @Bean("toMulticast")
    public MessageChannel toMulticast() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow unicastInboundFlow() {
        return IntegrationFlow.from(Udp.inboundAdapter(UNICAST_PORT))
                .channel("fromUnicast")
                .get();
    }

    @Bean
    public IntegrationFlow multicastInboundFlow() {
        return IntegrationFlow.from(
                    Udp.inboundMulticastAdapter(MULTICAST_PORT, GROUP))
                .channel("fromMulticast")
                .get();
    }

    @Bean
    public IntegrationFlow unicastOutboundFlow() {
        return IntegrationFlow.from("toUnicast")
                .handle(Udp.outboundAdapter("127.0.0.1", UNICAST_PORT))
                .get();
    }

    @Bean
    public IntegrationFlow multicastOutboundFlow() {
        return IntegrationFlow.from("toMulticast")
                .handle(Udp.outboundMulticastAdapter(GROUP, MULTICAST_PORT))
                .get();
    }
}
~~~

This configuration is a **single-application demonstration**; when deploying sender and receiver independently, each service only needs the endpoints belonging to its role. The address `127.0.0.1` only points to the host/container **running the sender**, not to other devices on the network.

Key steps:

1. `Udp.inboundAdapter(12001)` opens a unicast listener on UDP port 12001.
2. `Udp.inboundMulticastAdapter(12002, GROUP)` creates a listener that joins the multicast group and receives on port 12002.
3. `Udp.outboundAdapter(...)` sends datagrams to a single IP/port.
4. `Udp.outboundMulticastAdapter(...)` sends datagrams to a group/port.
5. The channels `fromUnicast`, `fromMulticast`, `toUnicast`, and `toMulticast` connect the network boundary to business logic.

When running on a host with multiple network interfaces, you may have to **specify the address/interface** for multicast per environment. The default configuration may select an unintended NIC, especially when VPN or container networks exist.

### 6.3. Service Activator handling received datagrams

~~~java
import java.nio.charset.StandardCharsets;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

@Component
public class UdpDatagramConsumer {

    private static final Logger log =
            LoggerFactory.getLogger(UdpDatagramConsumer.class);

    @ServiceActivator(inputChannel = "fromUnicast")
    public void onUnicast(Message<byte[]> message) {
        show("unicast", message.getPayload());
    }

    @ServiceActivator(inputChannel = "fromMulticast")
    public void onMulticast(Message<byte[]> message) {
        show("multicast", message.getPayload());
    }

    private void show(String type, byte[] payload) {
        if (payload.length == 0 || payload.length > 512) {
            log.warn("Discard {} datagram of size {}", type, payload.length);
            return;
        }

        String value = new String(payload, StandardCharsets.UTF_8);
        log.info("Received {}: {}", type, value);
    }
}
~~~

This snippet only demonstrates turning bytes into log lines. For production, apply **strict UTF-8 decoding**, validate schema, values, and device identity, rate-limit logs, classify errors/metrics, and handle duplicates if duplicate records are disallowed. A receiver must never treat arbitrary network packets as trusted data.

### 6.4. Publisher choosing unicast or multicast

~~~java
import java.nio.charset.StandardCharsets;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
public class UdpDatagramPublisher {

    private final MessageChannel unicast;
    private final MessageChannel multicast;

    public UdpDatagramPublisher(
            @Qualifier("toUnicast") MessageChannel unicast,
            @Qualifier("toMulticast") MessageChannel multicast) {
        this.unicast = unicast;
        this.multicast = multicast;
    }

    public boolean sendUnicast(String telemetry) {
        return send(unicast, telemetry);
    }

    public boolean sendMulticast(String telemetry) {
        return send(multicast, telemetry);
    }

    private boolean send(MessageChannel channel, String telemetry) {
        byte[] bytes = telemetry.getBytes(StandardCharsets.UTF_8);
        if (bytes.length == 0 || bytes.length > 512) {
            throw new IllegalArgumentException("UDP payload length invalid");
        }
        return channel.send(MessageBuilder.withPayload(bytes).build());
    }
}
~~~

From a controller, scheduler, or Kafka consumer, the application calls `sendUnicast(...)` or `sendMulticast(...)` depending on the target audience. A `true` return value from `MessageChannel.send` indicates the message was dispatched per channel semantics; **it does not prove the UDP receiver received it**.

Do not let API clients directly choose multicast groups, hosts/ports, or interfaces without authorization checks and destination allowlisting.

## 7. An equivalent XML configuration

If the project uses the Spring Integration XML namespace, inbound/outbound multicast can be configured as follows:

~~~xml
<int-ip:udp-inbound-channel-adapter
    id="multicastInput"
    channel="multicastReceived"
    port="12002"
    multicast="true"
    multicast-address="239.10.20.30"
    receive-buffer-size="2048"/>

<int-ip:udp-outbound-channel-adapter
    id="multicastOutput"
    channel="multicastToSend"
    host="239.10.20.30"
    port="12002"
    multicast="true"
    time-to-live="1"/>

<int:channel id="multicastReceived"/>
<int:channel id="multicastToSend"/>
~~~

This is a **configuration snippet** to place inside a Spring Integration XML file with the appropriate `int` and `int-ip` namespace versions. A handler downstream of `multicastReceived` still needs to be defined to process messages. Setting `multicast="true"` and `multicast-address` on the inbound adapter causes the listener to join the group; on outbound, `host` is the group address.

For unicast, use `multicast="false"` (or the appropriate default), the target host's `host`, and the listening `port`, without a group address.

## 8. Testing and observing on real machines

### 8.1. Testing unicast on one machine

Run the Spring Boot receiver with `unicastInboundFlow` and open PowerShell on **the same machine**:

~~~powershell
$client = [System.Net.Sockets.UdpClient]::new()
try {
    $text = "v=1;sensor=node-7;seq=1;tempC=26.5"
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($text)
    [void]$client.Send($bytes, $bytes.Length, "127.0.0.1", 12001)
}
finally {
    $client.Dispose()
}
~~~

While the adapter is listening, the expected log is:

~~~text
Received unicast: v=1;sensor=node-7;seq=1;tempC=26.5
~~~

If no log appears, first verify the receiver started, port 12001 is not taken by another app, the `fromUnicast` handler is registered, and the firewall is not blocking packets.

### 8.2. Testing multicast on a LAN

Multicast testing is more reliable with **two machines on the same LAN** (or a virtualized environment confirmed to support multicast):

1. Have receiver A and receiver B both join `239.10.20.30:12002` on the right interface. Each receiver can be a Spring Boot instance running `multicastInboundFlow`.
2. Have the sender emit a datagram via `sendMulticast("v=1;...")`.
3. Compare logs on **both A and B**, along with packet captures on each host if needed.
4. Shut down receiver B or leave the group; send again and verify A continues receiving normally.
5. Have a host C **not join the group**; do not rely on C capturing traffic in promiscuous mode to conclude C is a valid subscriber.
6. Increase the send rate and add `seq` to measure packet-loss rates at each receiver.

Do not conclude multicast is broken solely because sending and receiving within the same process produces no logs: different operating systems, NICs, Docker/VPN setups, or **multicast loopback** policies behave differently. Test across real hosts on the same LAN before changing code.

### 8.3. Observing UDP packets on the network

On a Linux receiving host, you can use a standard capture tool to verify group and port, for example:

~~~bash
sudo tcpdump -ni any 'udp and (port 12001 or port 12002)'
~~~

To inspect multicast specifically, check destination address `239.10.20.30`, the sender source, and the receiving interface. A packet capture may see packets before the application socket receives them; therefore, still check **handler logs, group membership, and buffers**.

Useful metrics include:

| Metric | Meaning |
|---|---|
| `udp_send_attempt_total` | Number of times the application invoked datagram sending |
| `udp_send_error_total` | Synchronous errors during encoding/dispatch/sending |
| `udp_receive_total{mode="unicast|multicast"}` | Number of datagrams pushed into the flow by the inbound adapter |
| `udp_invalid_payload_total` | Number of packets discarded due to schema/size |
| `udp_processed_total` | Number of packets successfully processed by business logic |
| `udp_sequence_gap_total` | Number of missing sequence gaps observed by the receiver |

With multicast, compute metrics **independently per receiver**. A sender sending 1,000 packets while receiver A receives 998 and B receives 995 can happen without any synchronous errors on the sender.

## 9. Network factors that determine multicast success

Multicast is not merely a flag in code.

| Situation | Consequence | How to address |
|---|---|---|
| Receiver joins the wrong group | Does not receive datagrams sent to the expected group | Verify group address and port on both sides |
| Joins the right group on the wrong network interface | Socket lacks the right receive path | Specify the interface/multicast NIC; inspect routing tables |
| TTL = 1 while receiver is on a different subnet | Routers normally do not forward packets to other subnets | Configure multicast routing, TTL, and network policy |
| Switch runs IGMP snooping without matching membership | Packets may not reach the receiver's switch port | Check IGMP joins and querier/switch configuration |
| Firewall or AP isolation | Host sees other traffic but misses desired multicast | Check firewall, Wi-Fi/AP settings, VLAN, and network policy |
| Docker/Kubernetes/VPN lacks multicast support | Code is valid but packets are never forwarded | Use a multicast-enabled LAN or an alternative distribution mechanism |
| Payload exceeds receive buffer | Datagram may be truncated | Reduce payload, size buffers properly, align length check |
| Multiple instances on one host bind the same port | Receiving behavior varies by OS/socket options | Verify `SO_REUSEADDR`, membership, and binding in the target environment |

**Do not automatically assume:** multicast is "free fan-out" regardless of topology. Multicast saves sender-side transmissions under favorable network conditions, but network administration, independent receivers, and observability are typically more complex than unicast.

## 10. Datagram size, length check, and ACK

### 10.1. Datagram size and receive buffer

A UDP datagram over IPv4 has a theoretical payload limit of around **65,507 bytes** (without IP options), but applications should pick a **significantly smaller** size to avoid fragmentation along the path. For telemetry, a few hundred bytes is usually enough; this lesson's example limits payloads to **512 bytes**.

The Spring Integration inbound adapter has a `receive-buffer-size` option for the buffer used to receive each datagram. Distinguish this from the operating system's **socket receive buffer**. Increasing one buffer alone does not solve packet drops caused by the network, a fast sender, or slow business processing.

### 10.2. Length check

Spring Integration UDP lets you enable **length check**: outbound prepends a **4-byte length prefix in network byte order**; a compatible inbound adapter compares that length and detects truncated packets. Sender and receiver must **agree on the mode**. A plain UDP receiver unaware of the prefix will misdecode the message if it treats the entire datagram as UTF-8.

Length check does not recover lost datagrams and does not guarantee ordering.

### 10.3. Acknowledgment

The library supports an **application-layer ACK** mechanism when configuring `acknowledge` and related attributes. The sender can wait for an ACK within a timeout; the receiver must understand Spring Integration's **ACK framing**.

With multicast, you can configure **`min-acks-for-success`** when ACK is enabled, meaning the sender requires at least a certain number of receiver responses. This **does not automatically prove all group members received it**, since the sender has no authoritative membership list like a pub/sub broker. Receiving a packet ACK also does not necessarily prove the transaction on the receiver was committed.

If the system requires every single record to arrive, design additional IDs, sequences, controlled retries, deduplication, durable storage, and business ACKs; consider JMS/AMQP/Kafka or other solutions when guaranteed delivery is required.

## 11. Security and scope limits

Both unicast and multicast UDP carry risks when receiving untrusted data:

- **A multicast group is not an authentication mechanism**. Any host with network access and matching configuration can join to receive or send packets to the group.
- **TTL does not encrypt payloads**; it only bounds routing scope; do not use TTL in place of ACLs/firewalls.
- **Source IP can be spoofed** in some environments; do not authenticate sensors solely by source IP.
- **Enforce size, schema, version, and rate limits** before forwarding into the business pipeline.
- If tamper-proofing/replay protection is needed, design signatures/HMAC or an appropriate protected transport and validate timestamps/sequences; plain UDP does not provide these natively.
- For internal multicast, align allocated group ranges, VLANs, interfaces, firewalls, and operational logs with network administrators.

Do not log every payload in production, especially when telemetry contains sensitive data or send rates are high.

## 12. When to choose unicast vs. multicast?

| Scenario | Recommended choice | Reason |
|---|---|---|
| One sensor sending readings to a fixed collector | **Unicast** | Simple configuration, standard networks, one clear destination |
| One host broadcasting real-time data to many screens on the same LAN | **Multicast** when network supports it | One stream for many subscribers, avoids repeated sends |
| Receivers spread across multiple VPCs/clouds, VPN/CNI lacking multicast | **Unicast or broker** | Easier routing, confirmation, and operations |
| Each receiver needs different data | **Unicast** | Separate targets and customized per-recipient payloads |
| Every subscriber must receive all data with replay capability | **Durable broker** | Multicast UDP has no storage or replay |
| Need visibility into per-receiver confirmation | **Unicast + business ACK**, or broker | Track target list and individual statuses |
| Data may be dropped and superseded in the next cycle | **Unicast/multicast UDP** based on topology | Simple, low latency when packet loss is acceptable |

These choices depend on the **data contract and business requirements**, not merely the receiver count. Even with many recipients, multicast is only worthwhile if the network genuinely implements and operates multicast properly.

## 13. Comprehensive practice exercise

Design a flow following this model:

~~~mermaid
flowchart TD
    A["Producer: sensor data"] --> V["Validate + UTF-8 encode"]
    V --> R{"Target group?"}
    R -->|"1 collector"| U["toUnicast"]
    R -->|"N screens on LAN"| M["toMulticast"]
    U --> OU["Unicast outbound"]
    M --> OM["Multicast outbound"]
    OU --> RU["Collector: UDP 12001"]
    OM --> RA["Screen A: joined group"]
    OM --> RB["Screen B: joined group"]
~~~

Requirements:

1. Configure one **unicast receiver** on port 12001 and two **multicast receivers** both joining group `239.10.20.30` on port 12002.
2. Send 10 datagrams with incrementing `seq` over unicast; verify that only the unicast receiver pushes data into its corresponding channel.
3. Send 10 similar datagrams over multicast; compare how many packets each receiver receives, noting differences across interfaces/environments.
4. Try shutting down one multicast receiver, sending 10 more packets, then starting it back up. Explain why that receiver **does not automatically recover** missed datagrams.
5. Test wrong group address, wrong port, different interface, firewall rules, and low TTL across routers. Document how to distinguish code bugs from network issues.
6. Increase the send rate to observe missing sequence numbers, analyzing receive buffers and handler speed. Propose a strategy when packet loss cannot be tolerated.

**Self-assessment questions:**

- Why does a multicast sender not necessarily need to know the number of receivers?
- Can you merely change the destination IP from unicast to `239.10.20.30` and have receivers automatically see the data? Why or why not?
- Distinguish group address, UDP port, and network interface in a multicast receiver configuration.
- What effect does `TTL=1` have when a receiver is in another subnet?
- Why is enabling ACK still insufficient to prove every subscriber completed business processing?
- If a producer reads a DB using a poller and then sends multicast, which part of the flow does the poller operate in?
- When is multicast UDP unsuitable even if there are hundreds of consumers?

## 14. References

- [Spring Integration Reference — TCP and UDP Support](https://docs.spring.io/spring-integration/reference/ip/intro.html): overview of the four UDP adapter types.
- [Spring Integration Reference — UDP Adapters](https://docs.spring.io/spring-integration/reference/ip/udp-adapters.html): unicast/multicast inbound/outbound, length check, and ACK.
- [Spring Integration Reference — IP Configuration Attributes](https://docs.spring.io/spring-integration/reference/ip/endpoint-reference.html): meanings of `multicast`, `multicast-address`, `time-to-live`, buffers, and `min-acks-for-success`.
- [Spring Integration Java DSL — Udp](https://github.com/spring-projects/spring-integration/blob/main/spring-integration-ip/src/main/java/org/springframework/integration/ip/dsl/Udp.java): factories `inboundAdapter`, `inboundMulticastAdapter`, `outboundAdapter`, and `outboundMulticastAdapter`.

## Conclusion

**Unicast** delivers a UDP datagram to one specific destination address; **multicast** sends to a group address so multiple joined receivers can receive the same data stream. Both use UDP, so both must tolerate or explicitly handle packet loss, duplication, reordering, and size limits.

In **Spring Integration**, choosing unicast or multicast is expressed at the inbound/outbound UDP adapters, while payload validation, error handling, routing, persistence, or integration with HTTP, files, SFTP, JMS, AMQP, Kafka, and databases remain wired via **MessageChannel**. Choose unicast when there is one clear destination or per-receiver state is needed; choose multicast only when broadcasting identical data matches both network infrastructure and operational policies.
