# Verifying Multicast in a Local Area Network and Distinguishing Application Errors from Infrastructure Errors

## Objectives

Multicast allows **one sender** to send a datagram to a **group address**, and machines that have joined the group can receive copies within the permitted network scope. When a Java application does not receive a multicast message, you cannot immediately conclude that “the Java code is wrong” or “the switch is blocking it”: a good verification must separate **application → OS/socket → NIC/firewall → switch/Wi-Fi/VLAN → routing device**.

After this lesson, you will be able to:

1. Describe the path of an IPv4 UDP multicast packet in a LAN; distinguish **group address**, **UDP port**, **network interface**, **IGMP membership**, **TTL**, and intermediate devices.
2. Use Java 17+ to check whether an interface is up and reports multicast support; join/leave the right group using `MulticastSocket.joinGroup(SocketAddress, NetworkInterface)`.
3. Run a send–receive test with **fixed group/port/interface/TTL**, attaching `runId` and `sequence` to the payload to compare logs on both sides.
4. Inspect layer by layer using logs, timeouts, a unicast control test, packet captures, and data from switches/routers when permitted.
5. Classify failure symptoms: **cannot send**, **packet not seen at sender NIC**, **packet not seen at receiver NIC**, **packet reaches NIC but Java does not receive it**, **Java receives it but the parser rejects it**.
6. Understand the limits of each piece of evidence and avoid claiming “the network is fine” just because `joinGroup()` or `send()` returns successfully.

> The focus is on **diagnosing multicast in a local area network**, not building a multicast routing system across multiple networks. The examples use **IPv4**, the UDP protocol, and JDK 17 or later.

## 1. Problem Map: Where Does Multicast Travel?

Consider two machines on the same LAN/VLAN: machine A runs the sender and machine B runs the receiver.

```text
Machine A — sender                           Machine B — receiver
 ┌─────────────────┐                          ┌──────────────────────┐
 │ Java UDP send() │                          │ Java UDP receive()   │
 │ group:port      │                          │ joinGroup(group, NI) │
 └────────┬────────┘                          └──────────▲───────────┘
          │                                             │
     UDP/IP stack                                    UDP/IP stack
          │                                             ▲
          ▼                                             │
    NIC/interface ───► switch / Wi-Fi AP ─────────────► NIC/interface
                         │
                         ├─ VLAN / firewall / ACL?
                         ├─ IGMP snooping?
                         ├─ IGMP querier?
                         └─ AP client isolation?

Sender sends to 239.255.42.99:50017 (IPv4 multicast, UDP).
Receiver joins group 239.255.42.99 on the right interface and binds UDP port 50017.
```

A multicast **destination address** such as `239.255.42.99` does not represent a single machine. Multiple receivers can join the same group, while the receiving socket must listen on the **UDP port** that the sender uses. The group address and port are **two independent components**: joining the right group while binding the wrong port can still result in receiving nothing.

### 1.1. Components That Must Match

| Component | Example used in this lesson | Role | What goes wrong if mismatched |
|---|---|---|---|
| IP family | IPv4 | IP addressing protocol used for the group | Joining IPv4 while the sender sends IPv6 or vice versa |
| Multicast group | `239.255.42.99` | Group destination address | Sender and receiver are in different groups |
| UDP destination port | `50017` | Receiving port of the socket | Packets do not reach the right application socket |
| Interface/NIC | `eth0`, `en0`, or another real name | Outgoing port/adapter and group-joining interface | Picking a VPN, virtual adapter, different Wi-Fi, or wrong NIC |
| Local bind | UDP port `50017` on the receiver | Socket receives datagrams on the right port | Fails to bind, or binds the wrong address/port |
| IGMP membership | Join group on the receiving interface | OS announces the need to receive IPv4 multicast | Switch/router may not forward traffic to the receiver's port |
| Sender TTL | `1` | Hop limit at the IP layer | Does not cross routers; this is intentional for LAN testing |
| Firewall / ACL | Inbound/outbound UDP rules | Decides whether packets are allowed through | Packets may be blocked even when Java code is correct |
| Wi-Fi/switch policy | Isolation, IGMP snooping, querier | Controls how multicast is forwarded on the LAN | Packets fail to reach the receiver over L2 |

Addresses in `239.0.0.0/8` are commonly used for **administratively scoped IPv4 multicast** within a managed domain. Choosing `239.255.42.99` for an experiment **does not mean this address is globally reserved** for this lesson; you should check to avoid conflicts with groups already in use on a real network. Do not arbitrarily pick `224.0.0.x`, because many addresses in `224.0.0.0/24` are reserved for link-local control protocols.

### 1.2. What Does IGMP Do, and What Does It Not Do?

For IPv4 multicast, **IGMP (Internet Group Management Protocol)** helps receivers announce group membership to the local network/multicast routing devices. A switch with **IGMP snooping** can observe membership to decide to forward multicast datagrams only to the needed ports, instead of flooding every port.

Things to distinguish:

- `joinGroup` interacts with the **host networking stack** and membership; the OS may generate an appropriate IGMP report. It **does not create a reliable channel like TCP**.
- IGMP membership **does not** confirm that a sender is transmitting to the right address/port.
- Seeing an IGMP report somewhere does not guarantee that the UDP payload will be delivered to each receiver; delivery still depends on switch/AP policies, firewalls, topology, and timing.
- IGMP snooping/querier configuration on a switch can affect membership maintenance. A missing querier in certain topologies can cause multicast to work initially and then stop after a period of time.
- If there is a router between the two machines, **multicast routing** must be designed/enabled; simply increasing TTL does not automatically make network devices forward multicast.

**Diagnose IGMP and the data path separately.** Seeing an IGMP report only proves that the host/network stack performed membership signaling at that capture point; it does not prove that the UDP group payload reaches the application.

## 2. Three Principles Against False Conclusions

### 2.1. A Successful `joinGroup()` Does Not Guarantee a Sender Exists

`MulticastSocket.joinGroup(new InetSocketAddress(group, port), ni)` registers group membership on interface `ni`. The Java 17 Javadoc states that the port parameter in the group address object **does not determine membership at the group level**; the **actual receiving port** is determined by the **bound socket**.

Therefore, a program can join the group successfully while:

- The sender has not started or is sending to a different port.
- The sender uses an interface/route that does not reach the receiver's VLAN.
- The switch does not forward packets to the corresponding port.
- The local firewall blocks inbound UDP, or the Wi-Fi AP has client isolation enabled.
- The receiving application has exited, timed out, read into the wrong buffer, or rejected the payload.

**Do not use `joinGroup()` as an end-to-end health check.**

### 2.2. `send()` Returning Does Not Prove the Receiver Got It

`MulticastSocket.send(DatagramPacket)` passes the datagram to the network stack. It does not require a response from receivers and does not guarantee delivery, because UDP provides no application-level acknowledgment or retransmission like TCP. With multicast, this matters even more: one receiver may receive the packet while another does not.

If you need to know who processed a message, **design an application-layer ACK or separate verification** with an ID/nonce, deadline, and authentication as required. ACKs can still be lost; you must distinguish “no ACK seen” from “no one processed it”.

### 2.3. A Timeout Does Not Pinpoint the Exact Failing Layer

`MulticastSocket.receive(packet)` blocks waiting if no matching datagram arrives. `setSoTimeout(6000)` causes it to throw `SocketTimeoutException` after the wait interval when no datagram is received. **That is only an observation at the socket**, and does not by itself identify the root cause. Combine it with NIC packet captures and sender logs to isolate the layer.

## 3. Designing a Repeatable LAN Test

Instead of sending the string “hello” and only checking whether it appears, record a clear *test vector*:

| Property | Value |
|---|---|
| IP family | IPv4 |
| Group | `239.255.42.99` |
| UDP port | `50017` |
| Sender TTL | `1` (LAN test, no router traversal) |
| Sender interface | Interface name taken directly from `NetworkInterface` on **machine A** |
| Receiver interface | Interface name taken directly from `NetworkInterface` on **machine B** |
| Payload | `MC1|<runId>|<seq>` |
| Expected datagrams sent | `5` |
| Interval between sends | `200 ms` |
| Receiver timeout | `6000 ms` per wait |
| Observed evidence | Sender log, receiver log, sender/receiver captures, group/port/interface/TTL |

`runId` distinguishes different test runs; `seq` helps count received packets, detect duplicates, and observe ordering. Do not assume UDP will always deliver all 5 or deliver them in order 1 through 5. In a healthy LAN test, seeing all 5 is a **positive observation**, not a protocol guarantee.

An example result:

```text
Sender: SENT run=ab12cd34 seq=1
Sender: SENT run=ab12cd34 seq=2
Sender: SENT run=ab12cd34 seq=3
Sender: SENT run=ab12cd34 seq=4
Sender: SENT run=ab12cd34 seq=5

Receiver: RECV run=ab12cd34 seq=1 ...
Receiver: RECV run=ab12cd34 seq=2 ...
Receiver: RECV run=ab12cd34 seq=3 ...
Receiver: RECV run=ab12cd34 seq=4 ...
Receiver: RECV run=ab12cd34 seq=5 ...
```

The lines above are only a **sample**; the actual ID, source IP, packet count, and ordering may differ. If a packet is lost—for example, the receiver sees 1,2,4,5—record explicitly that **seq=3 was not observed by the application**, and do not immediately claim “the switch dropped it” before obtaining a packet capture.

## 4. Java 17+: Identifying the Right Network Interface

A machine can have many adapters: Ethernet, Wi-Fi, VPN, Docker bridge, WSL, virtual interfaces, and loopback. `InetAddress.getLocalHost()` only resolves the host name to a single address and **does not choose the right multicast interface for you**.

The following program lists interfaces where `isUp()` is true along with the `supportsMulticast()` flag and the addresses bound to each interface, so you can select the exact **interface name** for the next two programs.

**File `MulticastInterfaceAudit.java`:**

```java
import java.net.InetAddress;
import java.net.NetworkInterface;
import java.util.Enumeration;

public class MulticastInterfaceAudit {
    public static void main(String[] args) throws Exception {
        Enumeration<NetworkInterface> all =
                NetworkInterface.getNetworkInterfaces();

        if (all == null) {
            System.out.println("No network interfaces visible");
            return;
        }

        while (all.hasMoreElements()) {
            NetworkInterface ni = all.nextElement();
            System.out.println("name=" + ni.getName()
                    + " up=" + ni.isUp()
                    + " multicast=" + ni.supportsMulticast()
                    + " loopback=" + ni.isLoopback());

            Enumeration<InetAddress> addresses = ni.getInetAddresses();
            while (addresses.hasMoreElements()) {
                System.out.println("  ip="
                        + addresses.nextElement().getHostAddress());
            }
        }
    }
}
```

**Commands:**

```bash
javac -encoding UTF-8 MulticastInterfaceAudit.java
java MulticastInterfaceAudit
```

**Output depends on the machine and operating system**, for example:

```text
name=eth0 up=true multicast=true loopback=false
  ip=192.168.1.20
name=lo up=true multicast=false loopback=true
  ip=127.0.0.1
```

Do not treat the example stdout as a fixed list. Interface names on Windows/macOS/Linux, address ordering, IPv6 addresses, and loopback attributes vary by platform.

**Which interface should you choose?** Pick the interface whose address belongs to the LAN under test, is **up**, and reports **supportsMulticast=true**. This flag is a capability **reported by the OS**; it **does not prove** that the switch/AP allows multicast or that the host has joined the right group. Machines A and B may use different interface names.

## 5. Java 17+: Receiver Joining a Group on an Explicit Interface

The `LanMulticastReceiver` example listens on UDP port `50017` on the local wildcard address and uses `joinGroup(group, networkInterface)` to register for reception on the selected interface. It prints `runId`, `seq`, and source IP/port, while flagging duplicate `seq` values per run. This is a standalone program for **Java 17+**.

**File `LanMulticastReceiver.java`:**

```java
import java.net.DatagramPacket;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.MulticastSocket;
import java.net.NetworkInterface;
import java.net.SocketTimeoutException;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

public class LanMulticastReceiver {
    private static final int PORT = 50017;

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.out.println("Usage: java LanMulticastReceiver <interface-name>");
            return;
        }

        NetworkInterface ni = NetworkInterface.getByName(args[0]);
        if (ni == null || !ni.isUp() || !ni.supportsMulticast()) {
            System.out.println("Interface missing, down or no multicast support");
            return;
        }

        InetAddress group = InetAddress.getByName("239.255.42.99");
        InetSocketAddress membership = new InetSocketAddress(group, PORT);

        try (MulticastSocket socket = new MulticastSocket(null)) {
            // Set the reuse option before binding; not a guarantee that
            // every OS allows multiple processes to receive on the same port.
            socket.setReuseAddress(true);
            socket.bind(new InetSocketAddress(PORT));
            socket.setSoTimeout(6000);
            socket.joinGroup(membership, ni);

            Map<String, Set<Integer>> seen = new HashMap<>();
            System.out.println("READY group=239.255.42.99:50017"
                    + " interface=" + ni.getName());

            try {
                for (int i = 0; i < 5; i++) {
                    byte[] buffer = new byte[2048];
                    DatagramPacket packet =
                            new DatagramPacket(buffer, buffer.length);

                    try {
                        socket.receive(packet);
                    } catch (SocketTimeoutException timeout) {
                        System.out.println("TIMEOUT waiting for datagram");
                        break;
                    }

                    String payload = new String(packet.getData(),
                            packet.getOffset(), packet.getLength(),
                            StandardCharsets.UTF_8);
                    String[] parts = payload.split("\\|", -1);

                    if (parts.length != 3
                            || !"MC1".equals(parts[0])
                            || parts[1].isBlank()) {
                        System.out.println("APP_REJECT invalid format");
                        continue;
                    }

                    try {
                        int seq = Integer.parseInt(parts[2]);
                        if (seq < 1) {
                            System.out.println("APP_REJECT invalid sequence");
                            continue;
                        }
                        boolean duplicate = !seen
                                .computeIfAbsent(parts[1], k -> new HashSet<>())
                                .add(seq);

                        System.out.println("RECV run=" + parts[1]
                                + " seq=" + seq
                                + " from=" + packet.getAddress().getHostAddress()
                                + ":" + packet.getPort()
                                + " duplicate=" + duplicate);
                    } catch (NumberFormatException e) {
                        System.out.println("APP_REJECT invalid sequence");
                    }
                }
            } finally {
                socket.leaveGroup(membership, ni);
            }
        }
    }
}
```

**Compile:**

```bash
javac -encoding UTF-8 LanMulticastReceiver.java
```

**Run on the receiving machine**, replacing the interface name with the real name from the audit program:

```bash
java LanMulticastReceiver eth0
```

If the interface name contains spaces, enclose it in double quotes on the command line. `eth0` is only a Linux example, **not the default interface name on every operating system**.

When the join succeeds, the program **prints the READY line before waiting for UDP**:

```text
READY group=239.255.42.99:50017 interface=eth0
```

If no matching datagram arrives within 6 seconds, it may print:

```text
TIMEOUT waiting for datagram
```

**READY is not proof that packets will arrive**, and **TIMEOUT does not identify the failing layer**. If a properly formatted packet is received, it also prints `RECV run=... seq=... from=... duplicate=...`. These dynamic values have no fixed stdout.

### Key Technical Points

1. `new MulticastSocket(null)` creates an unbound socket so `SO_REUSEADDR` can be configured **before** binding. `bind(new InetSocketAddress(PORT))` makes the socket listen on UDP port `50017` on the local wildcard address.
2. `joinGroup(membership, ni)` uses the **group IP** and **interface ni** to join. According to the Javadoc, the port component in `membership` is ignored for the join operation; the **port of the bound socket** determines which UDP traffic is received.
3. `setSoTimeout(6000)` only bounds the wait time for each `receive` call. It does not perform a network-wide liveness check.
4. Each `DatagramPacket` receives **one datagram**; `getLength()` is the number of bytes received. Decoding the entire 2,048-byte buffer would include trailing garbage; the code decodes only `offset..offset+length`.
5. `APP_REJECT` means **the application received a datagram**, but its content failed the illustrative parsing rules; this is completely different evidence from `TIMEOUT`.
6. `duplicate=true` here only detects `runId+seq` already seen **within this process**. It does not guarantee durable deduplication or anti-spoofing; memory limits and time windows are the responsibility of a real system.
7. `leaveGroup` is called when the read loop finishes; `try-with-resources` closes the socket afterward. If joining fails, the program throws an exception; the error message typically points toward checking permissions, the interface, or stack support, rather than concluding the switch is at fault.

**Caution when testing multiple receivers on the same machine:** `setReuseAddress(true)` does not guarantee on every OS that two processes bound to the same port will both receive all datagrams. Test one receiver per host first to eliminate OS port-sharing behavior dependencies.

## 6. Java 17+: Sender Sending Five Probes with TTL = 1

The sender program selects the same group and port, specifies the **outgoing** interface with `setNetworkInterface(ni)`, sets `setTimeToLive(1)`, and sends five datagrams with the same `runId` and increasing `seq`. It **does not join the group**, because a multicast-only sender does not need to be a group member to send.

**File `LanMulticastSender.java`:**

```java
import java.net.DatagramPacket;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.MulticastSocket;
import java.net.NetworkInterface;
import java.nio.charset.StandardCharsets;
import java.util.UUID;

public class LanMulticastSender {
    private static final int PORT = 50017;

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.out.println("Usage: java LanMulticastSender <interface-name>");
            return;
        }

        NetworkInterface ni = NetworkInterface.getByName(args[0]);
        if (ni == null || !ni.isUp() || !ni.supportsMulticast()) {
            System.out.println("Interface missing, down or no multicast support");
            return;
        }

        InetAddress group = InetAddress.getByName("239.255.42.99");
        InetSocketAddress destination = new InetSocketAddress(group, PORT);
        String runId = UUID.randomUUID().toString().substring(0, 8);

        try (MulticastSocket socket = new MulticastSocket()) {
            socket.setNetworkInterface(ni);
            socket.setTimeToLive(1);

            for (int seq = 1; seq <= 5; seq++) {
                String message = "MC1|" + runId + "|" + seq;
                byte[] bytes = message.getBytes(StandardCharsets.UTF_8);

                socket.send(new DatagramPacket(
                        bytes, bytes.length, destination));

                System.out.println("SENT run=" + runId
                        + " seq=" + seq + " bytes=" + bytes.length);
                Thread.sleep(200);
            }
        }
    }
}
```

**Compile and run on machine A:**

```bash
javac -encoding UTF-8 LanMulticastSender.java
java LanMulticastSender eth0
```

In a normal run, the sender prints five lines. `runId` differs on each run; for example:

```text
SENT run=ab12cd34 seq=1 bytes=14
SENT run=ab12cd34 seq=2 bytes=14
SENT run=ab12cd34 seq=3 bytes=14
SENT run=ab12cd34 seq=4 bytes=14
SENT run=ab12cd34 seq=5 bytes=14
```

With the structure `MC1|` (4 bytes) + `runId` (8 bytes) + `|` (1 byte) + a 1-digit sequence number, the payload size is **14 bytes**. The `runId` in the stdout above is only an example value; the `SENT` lines indicate that the code completed the `send()` call, **not** that the receiver received the datagrams.

**TTL note:** `setTimeToLive(1)` restricts multicast to the appropriate hop scope and prevents crossing routers under normal conditions. For the goal of verifying **the same LAN/VLAN**, this is an intentional limit to avoid sending packets farther. If the two machines are on **different subnets/VLANs** separated by a router, a TTL=1 test may fail **as configured**. Do not arbitrarily raise TTL to “fix” a system that is not permitted to route multicast; routing groups across VLANs requires network design and approval from network administrators.

### Running the Test in the Right Order

1. Audit interfaces on both machines and identify the interfaces connected to the same LAN/VLAN.
2. Verify that both machines can communicate on the subnet using an appropriate mechanism; if only `ping` works, do not assume UDP multicast will be forwarded.
3. On **machine B**, run `LanMulticastReceiver` and confirm the `READY` line appears. Avoid starting the sender **before** the receiver: UDP datagrams already sent are not buffered for applications that join the group later.
4. Within the receiver's wait window, run `LanMulticastSender` on **machine A**. Pick the exact interface on each machine; do not hardcode `eth0` if the OS differs.
5. Compare the matching `runId`, sent/received `seq` values, and source IP:port. Count only packets with the right group/port, matching run, and valid format.
6. If no `RECV` appears, move to layer-by-layer inspection rather than changing multiple parameters at once.

An **illustrative** output when the receiver gets one valid datagram might be:

```text
RECV run=ab12cd34 seq=1 from=192.168.1.20:53741 duplicate=false
```

The IP and source port are chosen by the OS and are not fixed. The demo program only receives up to five datagrams per 6-second wait window and is not meant as a production service. If multiple senders transmit at the same time, the first five received datagrams may come from different runs.

## 7. Important Baseline: Testing UDP Unicast Loopback to Isolate the Issue

When multicast fails, a **UDP unicast loopback** test can independently verify that the JVM can create datagrams, write/read UTF-8 buffers, and receive packets via sockets on the same machine. This **does not verify multicast**, nor does it verify the physical NIC, IGMP, LAN firewall, or switch.

**File `UdpLoopbackControl.java`:**

```java
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;

public class UdpLoopbackControl {
    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();

        try (DatagramSocket receiver = new DatagramSocket(
                     new InetSocketAddress(loopback, 0));
             DatagramSocket sender = new DatagramSocket(
                     new InetSocketAddress(loopback, 0))) {
            receiver.setSoTimeout(2000);

            byte[] payload = "MC1|selftest|1"
                    .getBytes(StandardCharsets.UTF_8);
            sender.send(new DatagramPacket(
                    payload, payload.length, receiver.getLocalSocketAddress()));

            DatagramPacket incoming = new DatagramPacket(new byte[128], 128);
            receiver.receive(incoming);
            String text = new String(incoming.getData(),
                    incoming.getOffset(), incoming.getLength(),
                    StandardCharsets.UTF_8);

            System.out.println("UDP_LOOPBACK_OK " + text);
        }
    }
}
```

**Commands:**

```bash
javac -encoding UTF-8 UdpLoopbackControl.java
java UdpLoopbackControl
```

**Stdout when local UDP works normally:**

```text
UDP_LOOPBACK_OK MC1|selftest|1
```

If the program succeeds, you can rule out some hypotheses that Java cannot run basic UDP on that machine. However, **unicast loopback OK is not enough to conclude multicast loopback or LAN multicast is OK**. If it fails, do not jump straight to IGMP on the switch: check the Java runtime, socket permissions, firewall/local policy, and loopback behavior first.

## 8. Evidence Matrix: Application or Infrastructure Error?

A program can “fail to receive” at several layers. The following matrix does not turn a symptom into a definitive conclusion, but points to the **next observation step**.

| Symptom | Priority cause group | Next evidence to gather |
|---|---|---|
| Java cannot find interface / interface down | Wrong interface, VPN/virtual adapter, host config | Run audit, inspect real addresses and NIC state |
| `supportsMulticast()==false` | Driver/interface does not report support | Pick another NIC, check OS/driver |
| `bind` throws `BindException` | Port in use, wrong sharing/permission/bind address | Check bound UDP sockets, avoid two receivers competing for the port |
| `joinGroup` throws an exception | Interface, group address, OS/socket policy | Record exception type, verify IPv4 group/NI, permissions, and platform |
| Receiver prints `READY`, sender not running | No sending source | Start sender within the wait window, compare `runId` |
| Sender prints `SENT`, no packet in sender NIC capture | Possible wrong interface, route/capture, host policy | Capture on the right NIC and check interface/OS |
| Sender NIC capture shows UDP, receiver NIC capture does not | Possible loss on L2/AP/VLAN/firewall/route, or wrong capture | Check same VLAN, switch ports, Wi-Fi isolation, IGMP snooping/querier |
| Receiver NIC capture shows UDP, Java does not `RECV` | Host filter/firewall, bind/join/NI, parser/log, namespace | Check socket bind, join, UDP port, local firewall, namespace |
| Java prints `APP_REJECT` | Data **reached the application**, but parser rejected it | Compare payload, encoding, version, length, `runId`/`seq` |
| Java prints `RECV` but business logic does not run | Post-receive processing bug, validation, thread/queue | Log and test parser/handler separately |
| Some `seq` lost, other `seq` still arrive | Datagram loss, buffer/drop, overload, infrastructure, or sender | Compare captures and counters, rate, receive buffer, thread |
| Multicast works on same machine, fails on another | Depends on real LAN path or different NIC policy | Capture on both physical NICs, check firewall and network equipment |
| Same VLAN OK, different VLAN fails | TTL=1 or missing multicast routing/ACL | Verify topology/TTL with network administrators |

**Warning:** seeing a packet in a sender-side capture **does not conclusively prove the packet was transmitted onto the wire** (it can be affected by capture placement and offloading). Seeing a packet in a receiver NIC capture while Java receives nothing can be caused by a **host firewall/stack** before the socket, not necessarily a Java bug. Root-cause classification must rely on **combined evidence**.

### Layer-by-Layer Questions

**Application layer:** Is the message version right? Are `MC1`, `runId`, `seq`, UTF-8, and length valid? Are exceptions being swallowed or packets dropped by the parser? Log events **before and after `receive()`** to know whether traffic entered the app.

**Socket/OS layer:** Is the receiver bound to the right port `50017`? Did it join the group via the **right interface**? Is the socket still open? Does the local firewall block inbound UDP? Is the program running inside a container/VM/WSL with a different network namespace from the host? Is another process bound to the same port with inconsistent sharing behavior?

**NIC/LAN layer:** Are machines A and B on the same VLAN/SSID? Does the Wi-Fi AP have client isolation or a guest network enabled? How are switch ports configured for multicast? Is IGMP snooping learning group membership? Is there a querier maintaining membership if the topology requires one? Is an ACL dropping the traffic?

**Routing layer:** If the machines are on different subnets/VLANs, does the router support and have **multicast forwarding** configured? Is TTL sufficient for the permitted hops? Do not assume normal unicast connectivity implies multicast across routers.

**Operational layer:** Is the packet rate too high, receiver CPU/buffer unable to keep up, receiver started after sender, or NIC offloading/filtering or firewall policy changing over time? An “intermittently received” scenario can differ from “never received”.

## 9. Packet Capture: Viewing Packets at the Right Place and Layer

If permitted to use Wireshark or tcpdump, capture **simultaneously** on the physical NICs of machines A and B, or on a properly placed switch port mirror. Do not capture only loopback on a laptop and conclude the LAN is receiving multicast.

### 9.1. Wireshark Filters

Display filter for UDP to the exact group and port:

```text
ip.dst == 239.255.42.99 && udp.dstport == 50017
```

Filter to view IGMP membership signaling:

```text
igmp
```

If you need to observe both **payload** and **membership**, use the two filters in turn or an appropriate combined expression. Verify that the packet actually has `ip.dst=239.255.42.99`, `udp.dstport=50017`, the expected source IP/port, length, and `MC1|runId|seq` value. Do not look only at the total “UDP packets” count.

### 9.2. tcpdump Examples (Linux/macOS, Requires Capture Privileges)

```bash
sudo tcpdump -ni eth0 'udp and dst host 239.255.42.99 and dst port 50017'
sudo tcpdump -ni eth0 'igmp'
```

`eth0` is only an illustrative name: replace it with the real interface; on macOS it usually has a different name. On Windows, use an equivalent capture tool permitted by your organization. **There is no need to change firewall/switch configurations** just to collect evidence, unless you have authorization.

### 9.3. Parallel Correlation Procedure

1. Before sending, start the capture on the **receiver** side and observe/record when the receiver joins the group (an IGMP report might not be visible due to capture placement, caching, or OS behavior; not seeing a report alone is not enough to conclude the join failed).
2. Start the capture on the **sender** side and verify the right **outgoing interface**.
3. Run one sender batch; record `runId`, timestamps, and the logged `seq` values.
4. Compare each `seq` across **sender log → capture A → capture B → receiver log**.
5. If packets appear in capture B but there is no receive log, check the host firewall, local bind/join, and path to the application; if `APP_REJECT` is logged, focus on the app parser rather than suspecting the entire LAN.
6. If packets are missing in capture B while present in A, check VLAN, AP isolation, switch snooping, IGMP querier, and ACLs; avoid jumping straight to a single hypothesis.

**Capture limitations:** capture software sees packets at its observation point, not across the entire path. Some offload/virtualization environments change how packets appear. Concluding that a specific switch dropped packets requires additional counters or captures on both sides of that device.

## 10. Common Local Network Issues

### 10.1. Wrong NIC on a Multi-Homed Machine

A laptop has Wi-Fi, Ethernet, and VPN; a container has veth/bridge; the interface Java picks automatically may **differ from the NIC connected to the LAN**. Therefore, **pass the interface name explicitly** to the program, check its IP in the audit, and capture on that same NIC.

Using `InetAddress.getLocalHost()` alone is not enough to identify the right multicast NIC. The `supportsMulticast()` flag is an OS-reported capability, **not a guarantee** that the physical network allows it.

### 10.2. IGMP Snooping / Missing Querier

Some switches learn which ports have receivers via IGMP reports so they can forward group traffic to the right places. When **IGMP snooping is enabled** but the topology lacks an active, properly functioning IGMP querier, membership may not be maintained reliably over time. Symptoms can include receiving right after joining and then losing traffic, or receiving only on certain switch ports.

Do not disable IGMP snooping system-wide on your own to test without authorization. Instead, provide the **group, VLAN, switch port, timestamps, and captures** to the network administrator; inspect IGMP groups, querier, and forwarding tables using tools appropriate for the switch model.

### 10.3. Wi-Fi Guest / AP Client Isolation

Two devices on the same SSID are not guaranteed to communicate peer-to-peer. A guest network or AP client isolation can block direct traffic between clients; many WLANs also throttle, buffer, or convert multicast to save airtime. For comparison, test **two machines plugged into Ethernet on the same VLAN** if available and permitted; if Ethernet works while Wi-Fi does not, prioritize checking AP/SSID policies and wireless multicast settings.

Do not infer a “Java on Windows” bug solely from a failed test over Wi-Fi.

### 10.4. Firewall/Endpoint Security

A host firewall may allow UDP loopback/unicast while blocking inbound multicast by network profile, application, or UDP port. A capture on the receiving NIC may show packets while the Java process cannot read them. When comparing, record the **network profile, inbound/outbound rules, executable process, and port `50017`**.

Do not broadly disable firewalls or antivirus to fix the issue. If you need to verify a rule, follow the machine administrator's process and make only narrow, time-bounded, authorized changes.

### 10.5. Different VLAN/Subnet, TTL, and Multicast Routing

Testing with TTL=1 **is designed for LAN scope**, not for verifying across routers. If two hosts are on different VLANs, successful unicast ping does not prove multicast will pass. Forwarding multicast across a router requires appropriate routing/policy and a TTL/hop limit sufficient for the permitted path. Raising TTL cannot by itself create routes, group state, or bypass ACLs.

### 10.6. Containers, VMs, and WSL

`joinGroup` may succeed inside a container's network namespace while no packets cross the bridge/NAT to the host NIC as expected; multicast across Docker/VM/WSL also depends on the driver and network mode. Results from inside a container should record the **interface inside the namespace** and how the bridge/vSwitch attaches to the LAN. Run an equivalent Java program **directly on the host** (if permitted) to test the virtualization boundary.

### 10.7. Receive Buffers, Large Packets, and High Load

UDP preserves datagram boundaries, but a `DatagramPacket` with too small a buffer can receive a **truncated payload**. In the example, a 2,048-byte buffer is plenty for a 14-byte probe; for larger payloads, design clear limits and avoid IP fragmentation where possible. If the sender transmits in rapid bursts, the OS socket receive buffer or the application may drop datagrams; check counters and try lowering the rate before concluding the switch is at fault.

**Do not treat `SO_RCVBUF` as a promise that “UDP never drops packets”**. The actual buffer size is subject to the OS, and UDP remains best-effort.

## 11. Self-Check by Scenario

**Scenario A — `READY` but no `RECV`:** The receiver joined the right group and printed READY. The sender has not been started. Is infrastructure at fault?  
**Answer:** No. READY only confirms local setup, not that a sending source exists. Start the sender on the right interface within the receive window.

**Scenario B — All five `SENT` lines:** Sender logs seq 1..5. Receiver logs 1,2,4,5. Can you conclude the switch dropped seq 3?  
**Answer:** Not yet. Sender logs do not guarantee packets hit the wire; there are also the host stack, NIC, AP/switch, firewall, receiver buffer, and code. Compare captures by matching `runId`/`seq` to isolate the layer.

**Scenario C — Packet reaches NIC B, Java prints `APP_REJECT`:** Where is the error?  
**Answer:** There is evidence that **the application received the datagram** and the parser rejected the format. Check version, encoding, payload string, length, and schema; at the same time, do not assume all other packets arrived intact.

**Scenario D — Sender and receiver use the same group, but receiver binds port `50018` instead of `50017`:** Is joining the group with the right IP enough?  
**Answer:** No. The socket must bind the matching UDP port. The port component in the `joinGroup` argument does not replace local binding.

**Scenario E — Unicast loopback OK, but multicast over Wi-Fi receives nothing:** Can you rule out firewall/AP/switch?  
**Answer:** No. Unicast loopback only verifies part of local functionality; check the NIC, group join, Wi-Fi isolation, IGMP snooping/querier, firewall, and captures.

**Scenario F — Machines A and B on two VLANs, TTL=1:** Why does unicast ping across the router work while multicast fails?  
**Answer:** TTL=1 and missing multicast routing/ACL/group state can block multicast across a router. Unicast connectivity does not guarantee multicast forwarding.

**Scenario G — IGMP report appears in the capture:** Is that enough to prove the UDP payload will reach Java?  
**Answer:** No. IGMP membership signaling is separate from the UDP data path; there are still the sender, port, group, device forwarding, firewall, socket bind, and parser.

**Scenario H — Two machines on the same SSID see no packets:** Does that mean they are not on the same LAN?  
**Answer:** Not necessarily. The AP may have client isolation enabled, split VLANs, or handle multicast specially. Check the SSID/VLAN configuration and compare with a permitted Ethernet connection.

**Scenario I — Receiver logs `duplicate=true` for the same `runId+seq`:** Is the network definitely duplicating packets?  
**Answer:** No. The sender may have retransmitted, multiple paths/multicast mechanisms may create copies, or the app may receive duplicates. Correlate sender logs and captures rather than looking at a single log.

**Scenario J — `joinGroup` throws `SocketException`:** Should you fix the Java parser first?  
**Answer:** No. It has not reached payload reception. Prioritize verifying the interface, IPv4 group address, socket permissions, bind, and OS/driver support; record the exact exception type and context.

## 12. Summary of the Diagnostic Workflow

A multicast verification is valuable when it answers *at which boundary packets are lost*, rather than merely *whether it works or not*:

```text
Java sender logs SENT?
  │ no  -> check sending code, group/port/NI, exceptions
  │ yes
  ▼
Capture at sender NIC sees UDP multicast?
  │ no  -> check source host / interface / route / capture location
  │ yes
  ▼
Capture at receiver NIC sees matching group:port + runId?
  │ no  -> check LAN/VLAN/AP/IGMP/switch/firewall/TTL/topology
  │ yes
  ▼
Java receiver gets datagram?
  │ no  -> check host firewall, bind/port, join/NI, namespace, socket
  │ yes
  ▼
Parser accepts payload?
  │ no  -> check schema, length, UTF-8, version, ID
  │ yes
  ▼
Application processes it correctly?
  │ no  -> check business handler, queue/thread, state/ack
  │ yes -> this test path is verified at the time of measurement
```

The arrows represent **investigation priority**, not absolute causal proof. Each capture/log only reflects where and when it was observed.

Quick takeaways:

- **Group + UDP port + right interface + local bind + membership** are the foundation of the receiver.
- **Sender interface + TTL + right group:port** are the foundation of sending.
- `joinGroup` and `send` do not create a delivery guarantee; UDP multicast can be lost, duplicated, or reordered.
- **IGMP snooping, querier, AP isolation, VLAN, firewall, virtualization, and routing** are commonly overlooked infrastructure variables.
- **Observing by `runId/seq` across sender, capture A, capture B, and receiver** separates pre-socket, network, and application errors.
- When critical business requirements apply, design additional **ACK, timeout/retry, dedup, and security** mechanisms; do not rely on multicast itself to provide reliability.

### Reference Documentation

- [Java 17 `MulticastSocket` — `joinGroup`, `leaveGroup`, `setNetworkInterface`, `setTimeToLive`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/MulticastSocket.html)
- [Java 17 `NetworkInterface` — `getNetworkInterfaces`, `isUp`, `supportsMulticast`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/NetworkInterface.html)
- [Java 17 `DatagramPacket` and `DatagramSocket`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/DatagramPacket.html)
- [Cisco — Troubleshoot Multicast Networks with CLI Tools](https://www.cisco.com/c/en/us/support/docs/ip/ip-multicast/13726-57.html)
