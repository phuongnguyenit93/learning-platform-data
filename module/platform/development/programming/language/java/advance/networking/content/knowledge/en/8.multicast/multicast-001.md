# How Multicast Differs from Unicast and Broadcast in Recipient Selection

## 1. All Send Network Data, but "Send to Whom?" Are Three Different Problems

Suppose a Java application has **one sender** that wants to deliver a message to multiple machines. There are at least three ways to specify the recipients at the network addressing layer:

- **Unicast:** sends to **one unicast destination address**. For example, a client sending a request to a server. To send the same content to multiple destinations, the application typically has to send multiple times, or use an intermediary service for distribution.
- **Broadcast:** sends to a **broadcast domain** determined by the address/link. In IPv4, a broadcast message can be received by devices belonging to that domain **without registering for a specific application group**. Broadcast does not mean "every machine on the Internet."
- **Multicast:** sends to a **group address**. Machines that want to participate register to receive the group's traffic on the appropriate network interface; the network can distribute and replicate packets where needed to reach members.

The core difference is not merely **one-to-one**, **one-to-many**, or **one-to-all** as shorthand, but **what type of address the sender uses to select destinations, how receiving machines are identified, and how far the traffic propagates**.

For example, an application broadcasts status to four machines A, B, C, and D:

- To send specifically to B: use **unicast** to B's IP address.
- To send to the local network domain of A, B, and C: you can use **IPv4 broadcast** according to the appropriate scope and network configuration; D on another network does not automatically receive it.
- To send to machines **that have joined group G**: use **multicast** to group address G. If A and C join G while B does not, then A/C are the group destinations; B is not automatically selected just because it is on the same network.

This lesson focuses on the **recipient selection mechanism**, while relating it to sending over UDP/IP and Java 17+ APIs to avoid equating the destination address with what the application actually receives.

## 2. Comparing Unicast, Broadcast, and Multicast

| Criterion | Unicast | Broadcast | Multicast |
|---|---|---|---|
| Destination address meaning | A specific unicast address | A broadcast address/scope | A **multicast group address** |
| Logically selected recipients | One network destination per packet | Hosts within the corresponding broadcast domain/scope | Hosts/interfaces that are **group members** within the routed scope |
| Does the receiver need to join a multicast group? | No | No | **Yes**, typically via joining a group at the host/network layer |
| One sender to multiple recipients | Sends separately to each destination (or uses a distribution service) | One broadcast datagram within its scope | One datagram sent to the group; the network can replicate as needed |
| IPv4 | Yes | **Yes**, limited/directed broadcast depending on configuration | Yes, range **224.0.0.0/4** |
| IPv6 | Yes | **No IP broadcast mechanism** | Yes, multicast addresses **ff00::/8** |
| Crossing routers | Follows unicast routing | Broadcast is typically restricted and/or blocked | Only when the network has appropriate multicast routing configured/supported |
| Common scenarios | HTTP/TCP request to a service | Some local discovery mechanisms relying on IPv4 broadcast | Streaming, group notifications, internal discovery/protocols depending on the network |
| What is not guaranteed | That the target application will accept or process it | That every application/machine will receive it | That every member will receive and fully process it |

**Common misconception:** a unicast packet sometimes uses an address backed by multiple service instances behind anycast or a load balancer; this does not turn the packet into multicast. At the IP level, the packet's destination is still a unicast address. Conversely, multicast is not "a server opening multiple TCP connections and sending the same data."

### Visualizing Recipient Scope

```text
One sender S; machines A, B, C on LAN-1; machine D on LAN-2.

                  +------- LAN-1 -------+
S ---- unicast -->| B                   |  Selects only destination B
                  | A    B    C         |
                  +---------------------+
                                  +--- LAN-2 ---+
                                  | D           |
                                  +-------------+

S --- IPv4 broadcast LAN-1 ---> A, B, C (hosts in the broadcast domain)
                                 D: does not automatically receive (different domain)

Group G:
  A: joins G        B: does not join G
  C: joins G        D: joins G but is on LAN-2

S --- multicast G, hop limit/TTL 1 ---> A, C
D can only receive if scope and multicast routing allow reaching LAN-2.
```

The diagram **illustrates the selection of candidate destinations**, not a delivery guarantee. Firewalls, NICs, kernels, membership, UDP ports, binding, routing, and applications can further filter packets. A machine being in a broadcast LAN does not mean every process on that machine sees the datagram.

## 3. Unicast: Selecting One Destination Address for One Packet

**Unicast** uses a unicast destination IP address, for example `192.0.2.20` or `2001:db8::20` (two ranges reserved for documentation). With a UDP socket, a datagram is typically sent to an **IP address + port** pair; with TCP, a client connects to a unicast endpoint by IP/port and exchanges data over the corresponding connection.

For example, one machine S sending to three machines A, B, and C:

```text
S -- datagram #1 --> A
S -- datagram #2 --> B
S -- datagram #3 --> C
```

The sending application is responsible for transmitting to all three destinations, unless an intermediary system such as a broker or CDN handles distribution. A unicast packet does not automatically become a group transmission just because the payload is identical.

**Advantages:** specifies a concrete destination, easy to set up request–response, and allows applying TLS/TCP, access control, and per-peer sessions. **Trade-offs:** to distribute large content to N separate destinations, the sender or distribution service may have to retransmit the data multiple times. Even so, multicast is not automatically the optimal choice: network constraints, security, and client support can make unicast more suitable.

It is necessary to distinguish between an **IP address** and an **application**: a packet arriving at an IP does not guarantee that a specific process receives the data. With UDP, the destination port must be opened/bound by the application; with TCP, the server must have a listener and a valid protocol.

## 4. Broadcast: Selecting a Network Domain, Not a Registered Group

### 4.1. Broadcast at the Link Layer and IPv4

In Ethernet, a **broadcast** frame uses the destination MAC address `ff:ff:ff:ff:ff:ff`; switches typically flood the frame within the corresponding broadcast domain/VLAN. This is **Layer 2**. In **IPv4**, two forms of broadcast are commonly mentioned:

- **Limited broadcast:** `255.255.255.255`, which has only local scope; routers do not forward it like a normal Internet broadcast packet.
- **Directed broadcast:** the broadcast address of an IPv4 subnet, for example `192.0.2.255` for the hypothetical subnet `192.0.2.0/24`. Routers and network policies typically **do not forward directed broadcasts** due to security/abuse concerns.

The subnet `192.0.2.0/24` is only a documentation example; the actual broadcast address must be calculated from the **network prefix/mask**. Not every network is a /24; do not conclude "the last address is always .255" without knowing the subnet.

**There is no IPv6 broadcast** equivalent to IPv4 broadcast. IPv6 uses **multicast** addresses defined for functions such as all-nodes on the link; this is still multicast, not IP broadcast in the IPv4 sense.

### 4.2. Who Does "All" Mean Here?

Broadcast delivers a packet to a wide network scope, but it does not mean every application program on every host receives or processes it:

1. Switches/routers determine the scope the packet can reach.
2. NICs, host firewalls, and the IP/UDP stack can block or filter it.
3. A UDP application must bind to the corresponding port and be configured to allow receiving it.
4. Environmental policies (Wi-Fi AP isolation, VLANs, VPNs, cloud networks) can block broadcast.

A host on another LAN normally **does not** receive LAN-1's broadcast. Many cloud/VPC systems also do not support the broadcast model like a traditional Ethernet LAN.

**Use cases:** certain local machine or device discovery protocols. You should not default to sending large/continuous business data via broadcast: it can cause unnecessary traffic to uninterested devices.

## 5. Multicast: Selecting Recipients by Group Address and Membership

With multicast, the sender **does not select each client's individual IP**. It selects a **multicast address G**. Parties that want to receive the traffic join group G on the relevant network interface.

- **IPv4 multicast:** `224.0.0.0/4`, meaning addresses `224.0.0.0` through `239.255.255.255`. Within this range are blocks reserved for special purposes or scopes; **do not arbitrarily pick** a reserved group.
- **IPv6 multicast:** `ff00::/8`, which has a scope field in the address. For example, `ff02::1` is the **link-local** all-nodes multicast; it is not an "IPv6 broadcast address."
- **Example application group for an administratively managed network:** `239.10.10.10` (in the administratively scoped multicast range `239.0.0.0/8`). An actual group must follow the organization's addressing policy and avoid colliding with other systems.

A multicast IP is a **group identifier**, not a server's unicast address. **A sender does not need to join a group just to send**; joining is primarily for the **receiving** side. A host can join multiple groups and can leave a group at any time.

### 5.1. Membership and the Role of Switches/Routers

The conceptual process:

1. The application opens a UDP socket on the receiving port and asks the operating system to **join group G** on the appropriate network interface.
2. The IP stack records the membership; in IPv4 networks, the **IGMP** mechanism exchanges membership information, while IPv6 uses **MLD**.
3. Switches with **IGMP/MLD snooping** can learn which ports actually have receivers to reduce multicast flooding in the LAN.
4. If traffic needs to cross routers, the infrastructure must support multicast routing according to the corresponding scope/policy. **Multicast routing does not exist by default on the Internet or in every VPN/cloud network.**
5. When the application leaves the group or membership expires under the network mechanism, group traffic may no longer be delivered to that interface.

**Distinction:** IGMP/MLD are **membership management** mechanisms between a host and the adjacent network; they are **not** protocols that carry application payloads. Multicast routing is a separate problem; do not assume that merely calling Java's `joinGroup` will make routers forward packets across all subnets.

### 5.2. Filtering Layers Through Which Recipients Are Selected

For a **Java application** to actually receive a multicast datagram, all of the following are typically needed simultaneously:

- The destination address is a **group** that the interface has joined, in the appropriate network scope.
- The network path delivers the packet to the host/interface (switching, routing, firewall, TTL/hop limit).
- The UDP **destination port** matches the bound socket, for example `5001`.
- The socket/OS and receiving API support membership/interface as configured.
- The application calls `receive`, successfully parses the payload, and processes it.

Therefore, the statement "multicast only sends to registered machines" is a **destination selection model**, not an absolute promise that the network will not send the frame to any other port, or that every member will read the message. A switch without snooping may flood multicast within a VLAN; a host that has not joined the group may still see the frame at a lower layer without delivering it to a normal application socket.

### 5.3. Group, Port, TTL, and Scope

For example, sending UDP to `239.10.10.10:5001`:

- `239.10.10.10` is the **group IP**.
- `5001` is the **application protocol's UDP port**.
- Two applications that both join group G, where only one binds the right port, will not necessarily both receive the same datagram.
- **TTL/hop limit** determines the maximum number of hops across routers; a value of `1` is commonly used to restrict multicast packets to the local link, which does not automatically mean every packet is delivered.
- Multicast address scope and router policies also limit where packets can go.

With multicast, the network can **replicate packets at distribution branches** instead of the sender having to send N copies to N separate IPs. However, reducing sender traffic does not guarantee reduced load on every link or always achieving better performance than unicast.

## 6. A Comparison with Concrete Addresses and Clear Results

Suppose there are machines:

| Machine | Illustrative Address | Network | Joined Group G = `239.10.10.10`? |
|---|---|---|---|
| A | `192.0.2.10` | LAN-1 | Yes |
| B | `192.0.2.11` | LAN-1 | No |
| C | `192.0.2.12` | LAN-1 | Yes |
| D | `198.51.100.10` | LAN-2 | Yes |

Sender S is on LAN-1:

1. **Unicast to B:** the sender directly identifies the address `192.0.2.11` → B is the candidate destination.
2. **IPv4 broadcast in LAN-1:** selects the LAN-1 scope → A, B, C are the hosts in the domain; D on LAN-2 is not selected.
3. **Multicast G, limited to TTL=1:** selects group G and LAN-1 scope → A, C are the matching members. B is not in the group; D is in the group but is on LAN-2, so it is outside this scope.
4. **Multicast G across multiple LANs (if infrastructure supports it):** when valid multicast routing exists and TTL/scope permit, D may additionally receive it. This cannot be asserted solely from the fact that D has joined.

From the example, we see that multicast **is not broadcast**: B is on the same LAN but does not want to receive G, so it is not part of the application's target group. Multicast is also **not repeated unicast**: the sender represents the destination by G rather than an explicit list of A, C, D.

## 7. Java 17+: Accurately Simulating Recipient Selection

To learn **recipient selection rules** without depending on whether a router, Wi-Fi, or OS has multicast enabled, the program below **simulates** a host/subnet/membership table. It does not send real datagrams. The addresses in the table are illustrative only.

Create the file **`RecipientSelectionDemo.java`**:

```java
import java.util.List;
import java.util.Set;
import java.util.function.Predicate;

public class RecipientSelectionDemo {
    record Host(
            String name,
            String ip,
            String network,
            Set<String> groups) {
    }

    static List<String> choose(
            List<Host> hosts, Predicate<Host> rule) {
        return hosts.stream()
                .filter(rule)
                .map(Host::name)
                .toList();
    }

    public static void main(String[] args) {
        String group = "239.10.10.10";
        String localNetwork = "LAN-1";

        List<Host> hosts = List.of(
                new Host("A", "192.0.2.10", "LAN-1",
                        Set.of(group)),
                new Host("B", "192.0.2.11", "LAN-1",
                        Set.of()),
                new Host("C", "192.0.2.12", "LAN-1",
                        Set.of(group)),
                new Host("D", "198.51.100.10", "LAN-2",
                        Set.of(group))
        );

        List<String> unicast = choose(
                hosts, h -> h.ip().equals("192.0.2.11"));

        List<String> broadcast = choose(
                hosts, h -> h.network().equals(localNetwork));

        List<String> multicastLocal = choose(
                hosts, h -> h.network().equals(localNetwork)
                        && h.groups().contains(group));

        List<String> remoteMembers = choose(
                hosts, h -> !h.network().equals(localNetwork)
                        && h.groups().contains(group));

        System.out.println("Unicast to B: " + unicast);
        System.out.println("Broadcast LAN-1: " + broadcast);
        System.out.println("Multicast G, TTL=1: " + multicastLocal);
        System.out.println("Members on other LANs: " + remoteMembers);
    }
}
```

Compile and run with **JDK 17 or later**:

```bash
javac -encoding UTF-8 RecipientSelectionDemo.java
java RecipientSelectionDemo
```

**Exact output:**

```text
Unicast to B: [B]
Broadcast LAN-1: [A, B, C]
Multicast G, TTL=1: [A, C]
Members on other LANs: [D]
```

**Explanation:**

- `unicast` checks **the exact destination address** `192.0.2.11`: only B matches.
- `broadcast` checks only the same **LAN-1 domain** in the model: A/B/C are candidates, independent of `groups()`.
- `multicastLocal` simultaneously checks **group G** membership and being on the same **LAN-1** as the sender when the simulated scope/TTL is restricted: only A/C.
- `remoteMembers` shows that D has joined G, but **it cannot be inferred** that D receives the datagram when the sender transmits in LAN-1 with TTL=1.

This is a **logical** model for comparing address semantics; a Java `Predicate` does not replace real-network routing, IGMP/MLD, firewalls, or UDP ports. A network packet can be dropped, duplicated, or handled differently from the model even when a host is a candidate recipient.

## 8. Real-World Java: `DatagramSocket` and `MulticastSocket`

In Java, the API type to choose reflects the sending method:

| Task | Typical API | Destination Address |
|---|---|---|
| UDP unicast | `DatagramSocket.send(DatagramPacket)` | Unicast IP + UDP port |
| IPv4 UDP broadcast | `DatagramSocket`, sometimes requires `setBroadcast(true)` depending on configuration | Limited/directed IPv4 broadcast + UDP port |
| UDP multicast | `MulticastSocket` or multicast-capable `DatagramChannel` | **Multicast group IP** + UDP port |
| Join/leave group | `MulticastSocket.joinGroup(...)` / `leaveGroup(...)`; or `DatagramChannel.join(...)` | Group and **network interface** |

### 8.1. UDP Unicast

**Illustrative code** example, placed in a method that may throw `IOException`:

```java
byte[] payload = "STATUS".getBytes(StandardCharsets.UTF_8);
InetAddress destination = InetAddress.getByName("192.0.2.11");
DatagramPacket packet = new DatagramPacket(
        payload, payload.length, destination, 5001);

try (DatagramSocket socket = new DatagramSocket()) {
    socket.send(packet);
}
```

The packet is sent toward **one destination** IP:port. Because `192.0.2.11` is a documentation address, this snippet only illustrates API structure, **with no real server receiving**. The `send` call not throwing an exception also **does not prove the receiver processed the payload**.

### 8.2. IPv4 UDP Broadcast

**Illustrative code** example using limited IPv4 broadcast in a permitted environment:

```java
byte[] payload = "DISCOVER".getBytes(StandardCharsets.UTF_8);
InetAddress destination = InetAddress.getByName("255.255.255.255");
DatagramPacket packet = new DatagramPacket(
        payload, payload.length, destination, 5001);

try (DatagramSocket socket = new DatagramSocket()) {
    socket.setBroadcast(true);
    socket.send(packet);
}
```

Depending on the OS, interface, firewall, and network, broadcast may be restricted/blocked. It does not send to the entire Internet; do not use broadcast indiscriminately or assume every machine will reply. `setBroadcast(true)` enables broadcast sending mode on the socket when supported by the system, but **does not create routing across routers**.

### 8.3. UDP Multicast: Sending and Joining a Group

To actually receive multicast, the application must select the **appropriate network interface**, bind the right port, and then join the group. The helper example below is **illustrative code for integration**, not a standalone class: it assumes the caller passes a validly selected `NetworkInterface nic` and that network policy permits IPv4 multicast.

```java
// Code snippet placed inside a class with imports java.net.*,
// java.nio.charset.StandardCharsets, and java.io.IOException.
static void receiveOneMulticast(NetworkInterface nic)
        throws IOException {
    InetAddress group = InetAddress.getByName("239.10.10.10");
    int port = 5001;
    InetSocketAddress membership = new InetSocketAddress(group, port);

    try (MulticastSocket receiver = new MulticastSocket(port)) {
        receiver.setNetworkInterface(nic);
        receiver.setSoTimeout(2_000); // avoid waiting indefinitely on receive()
        receiver.joinGroup(membership, nic);
        try {
            byte[] buffer = new byte[2048];
            DatagramPacket packet =
                    new DatagramPacket(buffer, buffer.length);
            receiver.receive(packet);

            String message = new String(
                    packet.getData(), packet.getOffset(),
                    packet.getLength(), StandardCharsets.UTF_8);
            System.out.println(message);
        } finally {
            receiver.leaveGroup(membership, nic);
        }
    }
}

static void sendOneMulticast(NetworkInterface nic)
        throws IOException {
    InetAddress group = InetAddress.getByName("239.10.10.10");
    byte[] payload = "HELLO GROUP".getBytes(StandardCharsets.UTF_8);
    DatagramPacket packet =
            new DatagramPacket(payload, payload.length, group, 5001);

    try (MulticastSocket sender = new MulticastSocket()) {
        sender.setNetworkInterface(nic);
        sender.setTimeToLive(1);
        sender.send(packet);
    }
}
```

**API explanation—do not confuse with delivery conditions:**

1. `group` is a **multicast group** address, not a destination host address.
2. `receiver.joinGroup(new InetSocketAddress(group, port), nic)` registers to receive the group on interface `nic`. The `port` variable matches the receiver's bound UDP port; passing `InetSocketAddress` in this overload **does not create a TCP connection**.
3. `receiver.receive(packet)` returns only if a matching datagram arrives at the socket; `setSoTimeout` limits the read wait time. **There is no guarantee** a datagram will arrive within 2 seconds if the infrastructure does not support multicast.
4. `leaveGroup` leaves the membership; `close` closes the socket. Cleanup code in `finally` attempts to leave the group even if reading throws an exception.
5. **The sender does not have to `joinGroup` just to send.** It selects the group IP:port, interface, and `setTimeToLive(1)` to limit the scope.
6. On machines with multiple NICs, choosing the wrong interface is a very common reason an app "joins successfully but receives no packets." The interface needs to be up and support multicast (`NetworkInterface.supportsMulticast()` if the API/system provides this information).
7. `MulticastSocket.joinGroup(InetAddress)` is the older API style; with modern JDKs, prefer the overload taking **`SocketAddress` and `NetworkInterface`**, or the `DatagramChannel` API to make the interface explicit.

**Do not predict stdout** for this real-network example: success depends on routing, group, interface, firewall, port, and sender/receiver processes; the complete demo class in Section 7 is the deterministic, offline-runnable test example.

### 8.4. DatagramChannel and IPv6

The NIO API can use `DatagramChannel`, for example opened with `StandardProtocolFamily.INET` or `INET6`, configured with `StandardSocketOptions.IP_MULTICAST_IF`, and then calling `join(group, networkInterface)`. This is a more flexible choice when a project already uses NIO and selectors; it still depends on scope, a multicast group of the right family, and network capability.

With IPv6, do not try to simulate broadcast with `255.255.255.255`: that is an **IPv4** address. IPv6 applications must use multicast appropriate to the scope and interface.

## 9. UDP Multicast Does Not Provide TCP-Style Guarantees

Multicast is commonly used over **UDP datagrams/IP multicast**, not a TCP connection "with multiple recipients." Compare:

- **TCP** has a sequenced byte stream, retransmission, flow control, and a dedicated connection between two endpoints at the transport layer. TCP is the common choice for unicast requiring ordering.
- **UDP** preserves individual datagram boundaries but does not promise delivery, does not automatically retransmit, does not enforce ordering, and does not prevent duplicates at the application level.
- **IP multicast** selects the group receiving the datagram; it **does not automatically make UDP reliable**. Members can join after a packet is sent, lose packets due to congestion, or fail to receive due to routers/firewalls.
- A multicast sender does not know for certain whether each member has read/processed the payload. If the application requires this, it must have an ACK protocol, sequence numbers, replay, FEC, or suitable mechanisms; receiving many ACKs simultaneously can also cause **ACK implosion**.

Multicast can be efficient when one source distributes the same content to many recipients in a supporting network, but it is not suitable for every request–response API, transactions requiring individual confirmation, or services deployed in environments without multicast routing support.

## 10. Practical Mechanism Selection

| Problem | Commonly Considered Choice | Why |
|---|---|---|
| Client calling a service's payment API | **Unicast** over TCP/TLS/HTTP | Single logical endpoint, clear authentication/response requirements |
| Sending a private message to machine B | **Unicast** | Selects B's exact destination address |
| Service discovery on a legacy IPv4 LAN | **Broadcast** or another discovery protocol | May want to announce to hosts in a local scope without application-level membership |
| Multiple devices on the same network subscribing to an event stream | **Multicast** if the network supports it | Only group members are logical targets; sender transmits one stream to the group |
| Application on the Internet/cloud/mobile distributing events | Usually **unicast via broker/CDN/pub-sub service** | IP multicast is typically not routed across the Internet and cloud networks |
| Discovery functionality on an IPv6 network | **IPv6 multicast** mechanism or appropriate discovery protocol | IPv6 has no IP broadcast |

**Do not equate multicast with application-layer pub/sub.** A message broker (Kafka, RabbitMQ, Redis Pub/Sub…) may select subscribers by topic, yet still distribute over **unicast** connections. A "topic" and a "multicast IP group" both involve the concept of a recipient group, but they belong to **different layers** and have completely different guarantees.

## 11. Common Misconceptions and Pitfalls

| Misconception | Reality |
|---|---|
| "Broadcast sends to every machine on the Internet." | IPv4 broadcast is typically limited to a network scope; routers may block directed broadcast. |
| "IPv6 has broadcast just like IPv4." | IPv6 **has no IP broadcast**; it uses scoped multicast. |
| "Multicast = sending unicast N times." | Multicast uses one **group address**; the network can replicate traffic at branches where needed. |
| "All machines on the same LAN receive multicast." | No. The target group at the application level is based on membership; hosts that have not joined normally do not have datagrams delivered to application sockets. |
| "Just calling joinGroup receives datagrams from any subnet." | No. Scope, TTL, interface, routers, switches, and firewalls can all restrict it. |
| "The sender must join the group before sending multicast." | Usually no. The **receiver** joins the group to receive; the sender can transmit to the group. |
| "Joining a group = opening a TCP connection to members." | No. Group membership is an IP/UDP multicast operation; it does not create a multi-party TCP connection. |
| "Multicast guarantees everyone receives exactly once." | No. UDP/IP multicast has no delivery/exactly-once guarantee. |
| "Same group means the same application receives it, regardless of port." | UDP destination port and socket binding still matter. |
| "If multicast isn't meant for host B, B can't see the frame at any layer." | A host may see traffic at a lower layer due to flooding/snooping policies, but an unjoined application is not automatically handed the packet. |
| "`255.255.255.255` is a multicast group." | This is the **limited IPv4 broadcast** address, not multicast. |
| "`setBroadcast(true)` lets IPv4 broadcast cross any router." | It only enables the socket feature if the OS allows it; it does not change network routing. |
| "Multicast is always better than unicast for many viewers." | Benefits depend on infrastructure support, bandwidth, error control, and security; unicast via CDN/broker may be more suitable. |

## 12. Self-Check Exercises

**Q1.** A/B/C are on the same LAN; only A and C join group `239.10.10.10`. A sender transmits UDP to this group with TTL=1; who are the **candidate group members** on the LAN?

**Answer:** A and C. B did not join the group and is not selected by membership. This is not a guarantee that A/C will receive the datagram, as it still depends on the network/socket.

**Q2.** With the same three machines A/B/C, the sender uses the LAN's IPv4 broadcast. Do A/B/C need to join a multicast group first?

**Answer:** No. Broadcast targets the broadcast domain and does not use group membership; however, OS, firewall, and UDP port can still filter it.

**Q3.** D on another LAN has joined the same group G. Will D definitely receive it when the sender transmits with TTL=1?

**Answer:** No. TTL=1 limits the multicast scope and does not by default cross routers. Crossing subnets requires appropriate routing/scope and infrastructure.

**Q4.** Can IPv6 use `255.255.255.255`?

**Answer:** No. That is an IPv4 limited broadcast address. IPv6 has no IP broadcast and instead uses multicast with addresses in `ff00::/8` and the corresponding scope.

**Q5.** When sending UDP multicast to `239.10.10.10:5001`, a host has joined `239.10.10.10` but only has a process bound to port `5002`. Will the process definitely receive the payload?

**Answer:** No. The datagram has UDP destination port `5001`, so a process on `5002` will not automatically receive it. Group membership is a necessary condition for multicast addressing, not sufficient for the application socket.

**Q6.** If you want each machine to confirm it has processed a business command, is plain UDP multicast enough?

**Answer:** No. Multicast selects the receiving group; UDP does not guarantee delivery/processing. You need an acknowledgment protocol, message identification, retry/idempotency, and an ACK implosion mitigation strategy if truly needed.

**Q7.** Is a broker sending a message via TCP unicast to 100 subscribers considered IP multicast?

**Answer:** No. That is **application-layer** fan-out/pub-sub using multiple unicast streams. IP multicast requires a multicast address and corresponding network mechanisms.

**Q8.** Within the same LAN, is multicast always transmitted only to Ethernet ports that have group members?

**Answer:** Not necessarily. A switch may flood multicast when it does not know membership or when snooping is disabled. Whether the host/app receives the datagram also depends on stack and socket checks.

## 13. Key Takeaways

- **Unicast selects a specific destination address.**
- **IPv4 broadcast selects a broadcast domain**, not a group of registered recipients; it typically works only within local scope, and **IPv6 has no IP broadcast**.
- **Multicast selects a group address**; receivers join the group on the appropriate interface. Being on the same LAN without joining means not belonging to the group's logical recipient set.
- **Groups on other networks do not receive automatically**: scope, TTL, multicast routing, IGMP/MLD, switches/firewalls, and UDP ports determine the path and actual delivery.
- **Selecting the right recipients does not mean guaranteeing delivery.** UDP/IP multicast does not replace acknowledgment, idempotency, or business-level processing confirmation.
- In Java, `DatagramSocket` serves UDP; `MulticastSocket.joinGroup`/`leaveGroup` and `NetworkInterface` help control membership, but supporting infrastructure is still required. For typical TCP client–server communication, unicast is the foundational connection model.

References: Java SE 17 API `java.net.DatagramSocket`, `java.net.DatagramPacket`, `java.net.MulticastSocket`, `java.net.NetworkInterface`; IP multicast/IGMP/MLD and IPv6 addressing standards (RFC 1112, RFC 4291, RFC 3810).
