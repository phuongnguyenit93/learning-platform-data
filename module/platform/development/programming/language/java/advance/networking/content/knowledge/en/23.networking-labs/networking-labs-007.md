# Testing Multicast with Explicit Network Interface Selection and Membership Cleanup

## 1. Lab Objectives

In Java Networking, **IP multicast** allows a sender to send **a single UDP datagram to a group address** (multicast group), while receivers that have **joined the group on an appropriate network interface** can receive that data. On a machine with multiple network interfaces — Wi-Fi, Ethernet, VPN, Docker/VM adapters, loopback — you should not leave the sending/receiving interface to the operating system's implicit selection if you need reproducible lab results.

This lesson belongs to the **Networking Labs** series and focuses on two principles:
1. **Explicitly specify the network interface:** the user selects an interface by **name** or a verified policy; the receiver calls `join(group, networkInterface)`, and the sender sets `IP_MULTICAST_IF` to that exact interface. **Do not** grab the first interface the API lists and assume it is the right one.
2. **Clean up membership:** after joining, keep the `MembershipKey` and call `drop()` in `finally`; then close the `DatagramChannel` using `try-with-resources`. With the `MulticastSocket` API, pair `joinGroup(..., netIf)` with `leaveGroup(..., netIf)`; close the socket separately.

You will learn:
- The differences between unicast, broadcast, and multicast; a group IP is not the address of a single host.
- The meaning of the IPv4 group `239.255.42.42`, UDP port, IPv4/IPv6 protocol family, TTL, and multicast loopback.
- How to enumerate `NetworkInterface` instances and evaluate `isUp()`, `supportsMulticast()`, and IPv4 addresses.
- How to use `DatagramChannel.open(StandardProtocolFamily.INET)`, `join(group, nic)`, `IP_MULTICAST_IF`, and `Selector` for receiving with a timeout.
- The exact lifecycle of `MembershipKey.isValid()`, `drop()`, and `channel.close()`.
- A legacy `MulticastSocket` example that still works in Java 17 and the currently appropriate `joinGroup(SocketAddress, NetworkInterface)` API.
- Common errors caused by picking the wrong interface, network policy/firewall/VPN, resource lifecycle, receiver buffer, timeout, and scope.
- Four **Java 17+** test programs, three of which are multicast programs compiled and run on an explicitly specified loopback interface.

**Scope note:** Multicast is primarily based on **UDP**, with no guarantees of delivery, ordering, or deduplication. Joining a multicast group does not make data secure or reliable. Do not send passwords, tokens, or personal information over a test group.

## 2. How Does Multicast Work?

Conceptual model:

```text
                  group: 239.255.42.42
                  UDP destination port: 54321
                           │
Sender ── send packet ─────┘
    │
    ├── outgoing interface: NIC_A
    │
    ▼
OS / network multicast delivery
    ├─ Receiver 1: join(group, NIC_A), bind UDP :54321 ─► may receive
    ├─ Receiver 2: join(group, NIC_B), bind UDP :54321 ─► depends on topology
    └─ Receiver 3: did not join group                  ─► usually does not receive
```

A multicast address represents a **group of receivers**. The sender does not need a list of each receiver's IP. However, **a UDP datagram is sent to both a group IP and a destination port**; a receiver that only joins the group while binding the wrong port will still fail to receive the application payload.

Comparison:

| Type | Destination | Meaning |
| --- | --- | --- |
| Unicast | IP of a single host | Sends to one specific network destination |
| IPv4 Broadcast | Broadcast address of the network | Broadcasts within the applicable broadcast domain; not IP multicast |
| Multicast | IP address in the multicast range | Interested receivers can join the group |
| Anycast | Multiple locations share the same address / routing selects destination | Not synonymous with multicast |

IP multicast does not by itself create a **message broker** or a delivery acknowledgement mechanism. UDP payloads can be lost, duplicated, or arrive out of order; applications need to design their own protocol when reliability is required.

## 3. Group IP, UDP Port, and Network Interface Are Three Independent Parts

A complete lab experiment needs to configure:

```text
Protocol family: IPv4 / INET
Group address:   239.255.42.42
UDP port:        54321 or dynamic port 0 for a single-process test
Interface:       name provided by the runner, e.g. loopback_0 on the test machine
TTL:             0 when only testing on the local host
Loopback:        enabled so a sender on the same host can test receiving
```

**Group address** identifies the group, **port** identifies the UDP endpoint the application is listening on, and **NetworkInterface** identifies the network domain on which the socket joins the group or sends multicast.

A host may have:
- A physical Ethernet card.
- Wi-Fi.
- A VPN adapter.
- A virtual switch for containers/VMs.
- Loopback.
- An IPv6-only interface or an interface without IPv4.

If you use `NetworkInterface.getNetworkInterfaces()` and simply take the first element, the enumeration order can change, and the first element might be a **virtual interface that cannot receive multicast**. This lesson requires the program to accept the **interface name from the command line**, validate its conditions, and report a clear error when the name is invalid.

## 4. Why Does Implicit Network Interface Selection Cause Hard-to-Debug Errors?

When `IP_MULTICAST_IF` is not set, the outgoing interface may be chosen by the OS according to its routing policy. When `MulticastSocket.joinGroup` receives `netIf=null`, the Java 17 documentation states that behavior may be unspecified if no default interface is set, or the call may fail.

Common scenarios:
1. A laptop has both Wi-Fi and Ethernet; the sender transmits over Ethernet while the receiver joins on Wi-Fi.
2. A VPN installs a preferred route, causing multicast to be sent into an unsupported adapter.
3. A Docker/VM adapter appears before the physical card during enumeration.
4. The receiver binds the right UDP port but joins the group on an interface that has no path to receive the packet.
5. The sender and receiver run on the same machine, but the OS does not enable multicast loopback on the selected interface.
6. A laptop switches networks, or interface names/indices or routing change after a restart.
7. A firewall blocks inbound UDP even though `supportsMulticast() == true`.

**Solution:** the user identifies the interface as needed, checks `isUp`, `supportsMulticast`, and the address family, and then uses **that exact `NetworkInterface` object** both when joining and when selecting the sending interface.

## 5. Important NetworkInterface APIs

`java.net.NetworkInterface` represents a network interface on the machine.

| API | Purpose |
| --- | --- |
| `NetworkInterface.getNetworkInterfaces()` | Lists the interfaces visible to Java |
| `NetworkInterface.getByName(String)` | Selects an interface by **system name** |
| `getName()` | Gets a name stable within the current runtime (not guaranteed across all OSes) |
| `getDisplayName()` | Friendly descriptive label; should not be used for identity comparison |
| `isUp()` | Interface is enabled according to the OS |
| `supportsMulticast()` | OS reports that the interface has multicast capability |
| `isLoopback()` | Loopback interface |
| `isPointToPoint()` | Point-to-point interface |
| `getInetAddresses()` | Lists the IP addresses of the interface |
| `getIndex()` | Operating system interface index, which can change |
| `NetworkInterface.getByInetAddress(ip)` | Finds an interface that has a specified address |

`supportsMulticast()` is a **capability check**, not a guarantee that datagrams will arrive. Network ACLs, multicast forwarding, Wi-Fi AP isolation, IGMP snooping, VPNs, and firewalls can still block traffic.

### Example of explicit interface validation (code snippet)

```java
NetworkInterface nic = NetworkInterface.getByName(requestedName);
if (nic == null || !nic.isUp() || !nic.supportsMulticast()) {
    throw new IllegalArgumentException("Interface unavailable for multicast");
}
boolean hasIPv4 = Collections.list(nic.getInetAddresses()).stream()
        .anyMatch(address -> address instanceof Inet4Address);
if (!hasIPv4) {
    throw new IllegalArgumentException("IPv4 interface required");
}
```

This snippet requires imports `java.net.*`, `java.util.Collections`, and the variable `String requestedName`. For IPv6 tests, you must check `Inet6Address` and use `StandardProtocolFamily.INET6`; do not use an IPv4 group on an IPv6-only adapter and assume the failure is a firewall issue.

## 6. Java 17 Program #1: Listing Network Interfaces for Selection

Before running a receiver, you need to know the **actual interface names** on the machine. The following code lists the exact properties needed for the lab **without automatically picking** any interface.

Save file **`InterfaceProbe282.java`**:

```java
import java.net.*;
import java.util.*;

public class InterfaceProbe282 {
    public static void main(String[] args) throws Exception {
        for (NetworkInterface nic :
                Collections.list(NetworkInterface.getNetworkInterfaces())) {
            boolean v4 = Collections.list(nic.getInetAddresses()).stream()
                    .anyMatch(a -> a instanceof Inet4Address);
            System.out.printf(
                    "name=%s up=%s multicast=%s loopback=%s ipv4=%s%n",
                    nic.getName(),
                    nic.isUp(),
                    nic.supportsMulticast(),
                    nic.isLoopback(),
                    v4);
        }
    }
}
```

Compile/run commands:

```bash
javac InterfaceProbe282.java
java InterfaceProbe282
```

**Machine-dependent output** — this is an **excerpt of a few lines** from a test run on Windows/JDK supporting Java 17 APIs, not fixed output for every machine:

```text
name=ethernet_32769 up=true multicast=true loopback=false ipv4=true
name=ethernet_32774 up=true multicast=true loopback=false ipv4=true
name=loopback_0 up=true multicast=true loopback=true ipv4=true
```

Other machines may list `lo`, `eth0`, `en0`, or other names; do not mechanically copy `loopback_0`. Only use the exact **name that the program prints on your machine**.

For **same-process/same-host** tests, prefer an **actual loopback interface that supports IPv4 multicast**. If the OS loopback does not support it, **do not automatically switch** to a physical card and send traffic onto the LAN without understanding the environment; choose an appropriate interface intentionally and read the network notes in section 23.

## 7. Choosing an Appropriate Group Address for Testing

The address `239.255.42.42` belongs to the **239.255.0.0/16 — IPv4 Local Scope** range per RFC 2365. We choose it so it does not collide with multicast groups reserved for specialized control protocols.

However:
- An **administratively scoped group address** does not mean "in-process only" or "localhost only" on every network.
- **TTL = 0** is the key setting for same-machine tests: multicast datagrams **are not transmitted onto the network**, though they may be delivered locally to a local receiver.
- If you want to test between two machines on the same network, TTL usually needs to be greater than 0, and network switches/routers/firewalls must permit multicast; do this in an authorized lab network.
- Avoid using `224.0.0.0/24` arbitrarily because that range contains many link-local control multicast addresses.
- IPv4 multicast is contained within `224.0.0.0/4`. Do not use the unicast address `127.0.0.1` as a multicast group.

Demo groups:
- `239.255.42.42` for the main send/receive experiment.
- `239.255.42.43` for the two independent memberships test.
- `239.255.42.44` for the `MulticastSocket` API.

If these addresses/ports are already used by another application on your machine, choose another test group/port within a range you control.

## 8. Java NIO Multicast: DatagramChannel and MembershipKey

Java NIO supports multicast through `DatagramChannel` because it implements `MulticastChannel`.

A receiver needs to:
1. Open the channel with the right address family, e.g., `DatagramChannel.open(StandardProtocolFamily.INET)` for IPv4.
2. If sharing a port across receivers, set `SO_REUSEADDR` before `bind` (portability depends on the OS).
3. Bind the UDP socket to the **local listening port**; port `0` can be used for OS-assigned ephemeral ports in tests.
4. Call `MembershipKey key = receiver.join(group, nic)`.
5. Read datagrams; you can use blocking receive, or a `Selector` with a nonblocking channel.
6. In `finally`, call `key.drop()` to leave the group.
7. Close the channel after processing finishes.

```java
try (DatagramChannel receiver =
        DatagramChannel.open(StandardProtocolFamily.INET)) {
    receiver.setOption(StandardSocketOptions.SO_REUSEADDR, true);
    receiver.bind(new InetSocketAddress(54321));

    MembershipKey membership = receiver.join(group, nic);
    try {
        // Read UDP datagrams...
    } finally {
        membership.drop(); // leave group even on read error / cancellation
    }
} // receiver.close() is called here
```

This is a **code snippet**; it requires `InetAddress group`, `NetworkInterface nic`, and imports. In production, handle potential bind/join failures, selector/cancellation, and valid port selection. **`MembershipKey` does not implement `AutoCloseable`**, so you cannot use `try (MembershipKey key = ...)` like an input stream; `drop()` must be managed explicitly.

## 9. Receiving Interface vs. Sending Interface

Two operations that are very easy to confuse:

```java
MembershipKey membership = receiver.join(group, nic);

sender.setOption(StandardSocketOptions.IP_MULTICAST_IF, nic);
```

- `receiver.join(group, nic)`: joins the **group on interface `nic` to receive** multicast datagrams.
- `sender.setOption(IP_MULTICAST_IF, nic)`: selects the **outbound interface** for multicast datagrams on the sender.
- `receiver.setOption(IP_MULTICAST_IF, nic)` **does not replace** `receiver.join(group, nic)`. `IP_MULTICAST_IF` primarily determines the multicast **outgoing interface**, not group listening registration.
- Simply calling `sender.send(buffer, groupSocketAddress)` does not make the channel a member of the group; a sender does not need to join if it only sends.

In a same-host test, use the **same `NetworkInterface` object** for both operations to avoid sending on one card while joining on another. When testing between two machines, each machine must select **its own interface**; the interface names/indices do not need to match, but the interfaces must be in the same multicast-reachable domain.

## 10. IP_MULTICAST_IF, TTL, and LOOP

`java.net.StandardSocketOptions` defines these options:

| Option | Type | Meaning |
| --- | --- | --- |
| `IP_MULTICAST_IF` | `NetworkInterface` | Selects the interface for **outbound** multicast |
| `IP_MULTICAST_TTL` | `Integer` 0..255 | TTL/hop-limit of multicast datagrams |
| `IP_MULTICAST_LOOP` | `Boolean` | Allows looping back multicast datagrams within the host, per OS semantics |
| `SO_REUSEADDR` | `Boolean` | Allows address reuse per OS rules, usually set before bind |
| `SO_RCVBUF` | `Integer` | Hint for receive buffer size, does not guarantee the number of datagrams retained |

In the lab:

```java
sender.setOption(StandardSocketOptions.IP_MULTICAST_IF, nic);
sender.setOption(StandardSocketOptions.IP_MULTICAST_TTL, 0);
sender.setOption(StandardSocketOptions.IP_MULTICAST_LOOP, true);
```

**TTL = 0**: for IPv4, datagrams are not transmitted onto the network but **may** be delivered locally. In the test run we executed, the datagram appeared at the loopback receiver. Do not treat TTL 0 as a delivery guarantee across all platforms; `IP_MULTICAST_LOOP` has OS-dependent semantics and may affect the sending or receiving socket depending on the implementation.

**TTL = 1**: usually suitable for a local network when authorized and routers do not forward beyond one hop; it is **not** equivalent to "localhost only". Do not increase TTL to "fix" a loopback failure if you do not intend to send traffic onto the LAN.

## 11. Multicast Receiver Port Binding and SO_REUSEADDR

Receivers that want to receive the **same group:port** usually have to bind that local UDP port:

```java
receiver.setOption(StandardSocketOptions.SO_REUSEADDR, true);
receiver.bind(new InetSocketAddress(54321));
MembershipKey key = receiver.join(group, nic);
```

**Code snippet**. If multiple receiver processes bind the same port:
- `SO_REUSEADDR` and OS-specific rules are usually required.
- Some systems have `SO_REUSEPORT`, but **not every OS/DatagramChannel supports it**.
- Even if reuse succeeds, delivery behavior across multiple sockets can differ by OS, group membership, and firewall.
- Do not assume that "joining the group" automatically opens the right UDP port; `join` does not replace `bind`.

In the complete program, the receiver binds port `0` so the OS picks a free port, and the sender retrieves it:

```java
int port = ((InetSocketAddress) receiver.getLocalAddress()).getPort();
```

That approach is ideal for **a single process containing both sender and receiver**. Two independent processes **must agree in advance on the same group and port**; each process cannot simply bind port 0 and expect to receive the same data stream.

## 12. Java 17 Program #2: Explicit NIC Selection and Loopback Multicast Receive

This is the core example. The program:
- **Requires exactly one argument**: the interface name specified by the runner, never picking a default card automatically.
- Checks that the interface exists, `isUp()`, `supportsMulticast()`, and has IPv4.
- Uses `DatagramChannel.open(StandardProtocolFamily.INET)` for IPv4.
- Receiver binds an ephemeral port, receives group `239.255.42.42` via `join(group, nic)`.
- Sender sets `IP_MULTICAST_IF=nic`, TTL `0`, and loopback `true`.
- Sends `hello-group` (**11 bytes**) over UDP multicast.
- Nonblocking receiver uses `Selector.select(2000)` so it does not wait indefinitely.
- Calls `membership.drop()` in `finally`; both sender/receiver and selector are closed via `try-with-resources`.

Save file **`ExplicitInterfaceMulticastDemo.java`**:

```java
import java.net.Inet4Address;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.NetworkInterface;
import java.net.SocketAddress;
import java.net.StandardProtocolFamily;
import java.net.StandardSocketOptions;
import java.nio.ByteBuffer;
import java.nio.channels.DatagramChannel;
import java.nio.channels.MembershipKey;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.nio.charset.StandardCharsets;
import java.util.Collections;

public class ExplicitInterfaceMulticastDemo {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: java ExplicitInterfaceMulticastDemo <interface-name>");
        }
        NetworkInterface nic = NetworkInterface.getByName(args[0]);
        if (nic == null || !nic.isUp() || !nic.supportsMulticast()) {
            throw new IllegalArgumentException(
                    "Interface absent/down/no multicast support");
        }
        if (Collections.list(nic.getInetAddresses()).stream()
                .noneMatch(a -> a instanceof Inet4Address)) {
            throw new IllegalArgumentException(
                    "Interface has no IPv4 address");
        }

        InetAddress group = InetAddress.getByName("239.255.42.42");
        System.out.println("selected-interface=" + nic.getName());

        try (DatagramChannel receiver =
                     DatagramChannel.open(StandardProtocolFamily.INET);
             DatagramChannel sender =
                     DatagramChannel.open(StandardProtocolFamily.INET)) {

            receiver.setOption(StandardSocketOptions.SO_REUSEADDR, true);
            receiver.bind(new InetSocketAddress(0));
            receiver.setOption(StandardSocketOptions.IP_MULTICAST_LOOP, true);
            receiver.configureBlocking(false);

            sender.setOption(StandardSocketOptions.IP_MULTICAST_IF, nic);
            sender.setOption(StandardSocketOptions.IP_MULTICAST_TTL, 0);
            sender.setOption(StandardSocketOptions.IP_MULTICAST_LOOP, true);

            MembershipKey membership = receiver.join(group, nic);
            try {
                System.out.println(
                        "membership-valid-before=" + membership.isValid());

                int port = ((InetSocketAddress)
                        receiver.getLocalAddress()).getPort();
                byte[] bytes = "hello-group".getBytes(StandardCharsets.UTF_8);
                int sent = sender.send(ByteBuffer.wrap(bytes),
                        new InetSocketAddress(group, port));
                System.out.println("sent-bytes=" + sent);

                try (Selector selector = Selector.open()) {
                    receiver.register(selector, SelectionKey.OP_READ);
                    int ready = selector.select(2000);
                    ByteBuffer buffer = ByteBuffer.allocate(256);
                    SocketAddress from = ready > 0 ?
                            receiver.receive(buffer) : null;

                    if (from == null) {
                        System.out.println("received=false");
                    } else {
                        buffer.flip();
                        String body =
                                StandardCharsets.UTF_8.decode(buffer).toString();
                        System.out.println("received=" + body);
                    }
                }
            } finally {
                membership.drop();
                System.out.println(
                        "membership-valid-after=" + membership.isValid());
            }
        }
    }
}
```

Compile with Java 17:

```bash
javac ExplicitInterfaceMulticastDemo.java
```

Check the interface name using the example in section 6, then **specify the real name**. On the tested environment, the loopback interface is named `loopback_0`:

```bash
java ExplicitInterfaceMulticastDemo loopback_0
```

**Verified stdout when run with interface `loopback_0` on a JDK 17 environment:**

```text
selected-interface=loopback_0
membership-valid-before=true
sent-bytes=11
received=hello-group
membership-valid-after=false
```

Do not assume your Linux/macOS machine has `loopback_0`. For example, `lo` is only valid if the inspector on that machine actually lists `lo` with multicast and IPv4; do not guess an interface name.

**Result caveat:** Packets may not loop back on some OSes, containers, VPNs, or firewall policies even though the code compiles successfully. If nothing is received within 2 seconds, the program prints `received=false` and still calls `drop()`. When that happens, follow the checklist in section 23; do not switch to an interface that transmits onto the LAN without control.

## 13. Step-by-Step Explanation of the Send/Receive Code

Steps in the example:
1. `NetworkInterface.getByName(args[0])` returns the interface **matching the exact name provided by the runner**. If absent, it returns `null` with no fallback.
2. `nic.isUp()` verifies the card is enabled; `supportsMulticast()` checks capability; checking `Inet4Address` prevents using an IPv6-only card for an IPv4 group.
3. `DatagramChannel.open(StandardProtocolFamily.INET)` creates an IPv4 datagram socket, distinct from `INET6` for IPv6.
4. Receiver sets `SO_REUSEADDR` **before `bind`** and binds an ephemeral UDP port. `SO_REUSEADDR` is not required for a single receiver test, but lays the foundation for explaining multiple listeners.
5. Receiver enables loopback and switches to **nonblocking** mode to use `Selector`.
6. Sender explicitly sets `IP_MULTICAST_IF`, rather than leaving outgoing interface selection to routing defaults.
7. Sender sets `TTL=0` to test local delivery on the host only, without sending packets onto the external network.
8. Receiver calls `join(group, nic)` and receives a `MembershipKey` token representing that exact group/interface membership.
9. Sender sends a ByteBuffer of 11 bytes. `DatagramChannel.send` returns the number of bytes sent in the datagram, **not the number of receivers that received it**.
10. Selector waits for readiness for up to about 2000 milliseconds; `receive(buffer)` populates the datagram and returns the source `SocketAddress` or `null` if no packet arrived.
11. `buffer.flip()` switches from write mode to read mode, then decodes UTF-8.
12. `finally` calls `membership.drop()`; afterward, try-with-resources closes the channels.

**Note:** `received=hello-group` verifies the data path **in this lab configuration**, whereas `membership-valid-after=false` verifies the token lifecycle. These two lines are **two separate checks**; do not infer that every packet queued before `drop()` disappeared immediately.

## 14. Datagram Boundaries and ByteBuffer

UDP multicast receives **datagrams**, not a TCP byte stream:
- One `send(ByteBuffer, target)` call sends one datagram if successful.
- The receiver reads at most the number of bytes remaining in the `ByteBuffer`.
- If the buffer is too small, the datagram may be **truncated** according to channel/platform semantics; the remainder **does not become a second datagram**.
- If a ByteBuffer has an incorrect `position`/`limit`, decoding may yield empty, incomplete, or stale bytes.

Correct cycle:

```java
ByteBuffer buffer = ByteBuffer.allocate(2048);
SocketAddress source = receiver.receive(buffer);
if (source != null) {
    buffer.flip();
    byte[] payload = new byte[buffer.remaining()];
    buffer.get(payload);
    processDatagram(source, payload);
}
```

This is a **code snippet**; it requires a configured `receiver` and an application-defined `processDatagram`. If looping to receive multiple packets, you must call `buffer.clear()` before the next packet. Do not reuse a ByteBuffer while forgetting `clear`.

**Application protocols** should enforce datagram size limits, magic/version, session ID, sequence number, and payload schema if required. Do not receive untrusted multicast and arbitrarily `deserialize` Java objects; avoid Java native deserialization on network data.

## 15. Receiving with a Timeout: Selector Instead of Infinite Blocking Receive

A newly opened `DatagramChannel` is in **blocking mode** by default. `receive(buffer)` can block indefinitely when no packet arrives. In labs/CI, tests should not hang.

A controlled approach:
1. `receiver.configureBlocking(false)`.
2. `Selector.open()`.
3. `receiver.register(selector, SelectionKey.OP_READ)`.
4. `selector.select(2000)` waits for readiness for up to about 2 seconds.
5. If no data arrives, finish the experiment and clean up.

```java
receiver.configureBlocking(false);
try (Selector selector = Selector.open()) {
    receiver.register(selector, SelectionKey.OP_READ);
    if (selector.select(2000) > 0) {
        ByteBuffer buffer = ByteBuffer.allocate(2048);
        SocketAddress from = receiver.receive(buffer);
        if (from != null) {
            buffer.flip();
            // process bytes
        }
    }
}
```

This is a code snippet. `select(...)` can return `0` due to timeout or wakeup/spurious reasons. If building a long-running event loop, you need to:
- Loop until a deadline using `System.nanoTime()`.
- Iterate over and remove selected keys after handling.
- Handle `ClosedChannelException` on cancel/close.
- Cap the number of packets per iteration to prevent a group flood from starving other tasks.

**Do not** arbitrarily mix `DatagramSocket.setSoTimeout(...)` with NIO `DatagramChannel.receive` and assume the timeout applies the same way. The NIO example uses `Selector`; the `MulticastSocket` example uses `setSoTimeout` and blocking receive in section 20.

## 16. MembershipKey Lifecycle: What Actually Needs Cleanup

`java.nio.channels.MembershipKey` represents membership in a multicast group on a corresponding interface.

```text
receiver.join(group, nic)
      │
      ▼
MembershipKey valid = true
      │
      ├─ receiver can receive group datagrams on the joined NIC
      │
      ├─ membership.drop()
      │       └─ key.isValid() = false
      │
      └─ receiver.close()
              └─ all membership keys belonging to the channel become invalid
```

Per the Java 17 API:
- A key is **valid upon creation**.
- A key remains valid until **`drop()`** is called or **the channel is closed**.
- `isValid()` returns the membership token's status, not "a packet was received" or "the network definitely works".
- `drop()` leaves the group; if the key is already invalid, calling it again **has no effect** (idempotent when invalid).
- After `drop()`, the channel can **rejoin** the group and obtain a **new key**.
- An invalid key **cannot become valid again**.
- `drop()` **does not close the channel**; the channel can continue operating, receiving unicast or other groups.

### A subtle trap: already-buffered datagrams

Right after `drop()`, you may occasionally still receive a datagram that was already sitting in the socket receive buffer **before leaving the group**. The Java 17 `MembershipKey.drop` documentation explicitly notes this scenario. Therefore, do not write tests asserting that "calling drop guarantees receive immediately returns null".

Better tests:
- `key.isValid() == false` after `drop()`.
- Keep another group still valid when only the first group is dropped.
- Closing the channel invalidates all membership keys of that channel.
- Do not use the packet count received immediately after drop as the sole condition to verify cleanup.

## 17. Proper Cleanup Even When Sender/Receiver Fails

Pattern:

```java
try (DatagramChannel receiver = DatagramChannel.open(
        StandardProtocolFamily.INET)) {
    receiver.bind(new InetSocketAddress(54321));
    MembershipKey key = receiver.join(group, nic);
    try {
        receiveAndProcess(receiver);
    } finally {
        key.drop();
    }
}
```

This is a **code snippet**; `group`, `nic`, and `receiveAndProcess` need to be defined.

Protections:
1. If `receiver.join(...)` throws `IOException` or `UnsupportedOperationException` **before a key is obtained**, try-with-resources still **closes `receiver`**; `drop` is not called on an unassigned variable.
2. If `receiveAndProcess` throws an exception, `finally` **drops the membership**.
3. Afterward, the outer try-with-resources still **closes `receiver`**, ensuring no UDP socket is leaked.
4. If using a `Selector` and sender channel, they should also be inside their own try-with-resources blocks.
5. If the whole program uses a single group and does not need to monitor membership state, closing the channel alone will invalidate the key; **explicit `drop`** is still very useful to clearly express the intent to leave the group **before closing the socket**.

Do not treat `drop()` as a replacement for `DatagramChannel.close()`. Leaving a group does not release all file descriptors/UDP socket buffers held by the channel.

## 18. Testing Two Groups on the Same Channel and Dropping Each Membership Independently

A `DatagramChannel` can join **multiple groups** and receive multiple `MembershipKey` instances. If only group A's key is dropped, group B's key can still remain valid.

Third experiment:
- `group1 = 239.255.42.42`.
- `group2 = 239.255.42.43`.
- Both join the same `NetworkInterface nic` on one receiver.
- Drop `group1`, read `isValid()` for both.
- Exit try-with-resources, the channel closes; group2's key becomes invalid **even without calling `drop` separately**.

**This illustrates the difference between "leaving one group" and "closing all memberships of the channel".** No multicast traffic needs to be sent; it only requires the NIC/OS to support joining.

## 19. Java 17 Program #3: Properly Cleaning Up Each MembershipKey

Save file **`MembershipCleanupDemo.java`**:

```java
import java.net.*;
import java.nio.channels.*;
import java.util.*;

public class MembershipCleanupDemo {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException("Specify interface name");
        }

        NetworkInterface nic = NetworkInterface.getByName(args[0]);
        if (nic == null || !nic.isUp() || !nic.supportsMulticast()
                || Collections.list(nic.getInetAddresses()).stream()
                .noneMatch(ip -> ip instanceof Inet4Address)) {
            throw new IllegalArgumentException(
                    "Unusable multicast interface");
        }

        MembershipKey second;
        try (DatagramChannel receiver =
                DatagramChannel.open(StandardProtocolFamily.INET)) {
            receiver.setOption(StandardSocketOptions.SO_REUSEADDR, true);
            receiver.bind(new InetSocketAddress(0));

            MembershipKey first = receiver.join(
                    InetAddress.getByName("239.255.42.42"), nic);
            second = receiver.join(
                    InetAddress.getByName("239.255.42.43"), nic);

            System.out.println("first-before=" + first.isValid());
            System.out.println("second-before=" + second.isValid());

            first.drop();
            System.out.println("first-after-drop=" + first.isValid());
            System.out.println("second-still-valid=" + second.isValid());
        }

        System.out.println(
                "second-after-channel-close=" + second.isValid());
    }
}
```

Compile and run after finding the exact interface name:

```bash
javac MembershipCleanupDemo.java
java MembershipCleanupDemo loopback_0
```

**Verified stdout on the test machine with interface `loopback_0`:**

```text
first-before=true
second-before=true
first-after-drop=false
second-still-valid=true
second-after-channel-close=false
```

What was verified:
- After both `join` calls, both keys are `true`.
- `first.drop()` turns the first key `false`.
- The second key stays `true` because **dropping group A does not drop group B**.
- When `receiver.close()` is called by try-with-resources, group B's key becomes `false`.

**Test scope note:** the program proves membership lifecycle, **not** delivery on group2, does not test IGMP/router forwarding, and requires no off-host traffic.

### What if joining group2 fails?

In this short code, if `second = receiver.join(...)` throws an exception, `first` remains valid until the outer try-with-resources **closes `receiver`**. By contract, closing the channel invalidates keys, so no membership is leaked. In a system managing multiple dynamic groups, you should still record each successful key in a collection and drop them during cleanup for more explicit lifecycle control.

## 20. Legacy MulticastSocket API: joinGroup/leaveGroup with a Specific Interface

In addition to NIO, Java has `java.net.MulticastSocket`. Java 17 still supports:
- `joinGroup(SocketAddress mcastaddr, NetworkInterface netIf)`.
- `leaveGroup(SocketAddress mcastaddr, NetworkInterface netIf)`.
- `setNetworkInterface(NetworkInterface)` for the outgoing multicast interface.
- `setTimeToLive(int)` for TTL 0..255.
- `setSoTimeout(int)` for blocking `receive` (may throw `SocketTimeoutException`).
- `close()` to close the socket.

In Java 17, the older `joinGroup(InetAddress)` and `leaveGroup(InetAddress)` versions are **deprecated**; use the overloads accepting `SocketAddress` and `NetworkInterface` to avoid implicit selection.

One difference from NIO:
- `DatagramChannel.join(group, nic)` returns a `MembershipKey` that can be `drop()`ed.
- `MulticastSocket.joinGroup(socketAddress, nic)` is a registration call; to leave the group, call **`leaveGroup(socketAddress, nic)`** with the exact group/interface.

**The port in the `SocketAddress` passed to `joinGroup` is ignored in Java 17** for historical API reasons, but the socket **must still bind the right UDP listening port** to receive datagrams. In the example, `new InetSocketAddress(group, 0)` serves as the group identity for join/leave; the sender still sends to the actual `receiver.getLocalPort()`.

## 21. Java 17 Program #4: MulticastSocket and leaveGroup

Save file **`ClassicMulticastSocketDemo.java`**:

```java
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.Collections;

public class ClassicMulticastSocketDemo {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException("Interface name required");
        }
        NetworkInterface nic = NetworkInterface.getByName(args[0]);
        if (nic == null || !nic.isUp() || !nic.supportsMulticast() ||
                Collections.list(nic.getInetAddresses()).stream()
                .noneMatch(a -> a instanceof Inet4Address)) {
            throw new IllegalArgumentException(
                    "Interface unsuitable for IPv4 multicast");
        }

        InetAddress group = InetAddress.getByName("239.255.42.44");
        try (MulticastSocket receiver = new MulticastSocket(null);
             MulticastSocket sender = new MulticastSocket()) {
            receiver.setReuseAddress(true);
            receiver.bind(new InetSocketAddress(0));
            receiver.setSoTimeout(1500);

            SocketAddress membership = new InetSocketAddress(group, 0);
            receiver.joinGroup(membership, nic);
            try {
                sender.setNetworkInterface(nic);
                sender.setTimeToLive(0);

                byte[] bytes = "classic".getBytes(
                        StandardCharsets.UTF_8);
                sender.send(new DatagramPacket(
                        bytes, bytes.length,
                        group, receiver.getLocalPort()));

                byte[] buffer = new byte[100];
                DatagramPacket received = new DatagramPacket(
                        buffer, buffer.length);
                receiver.receive(received);

                System.out.println(
                        "selected-interface=" + nic.getName());
                System.out.println("received=" + new String(
                        received.getData(), received.getOffset(),
                        received.getLength(), StandardCharsets.UTF_8));
            } finally {
                receiver.leaveGroup(membership, nic);
                System.out.println("leave-group-called=true");
            }
        }
    }
}
```

Compile:

```bash
javac ClassicMulticastSocketDemo.java
```

Run with a real interface on the test machine:

```bash
java ClassicMulticastSocketDemo loopback_0
```

**Verified stdout on interface `loopback_0`:**

```text
selected-interface=loopback_0
received=classic
leave-group-called=true
```

- `receiver.joinGroup(membership, nic)` explicitly specifies the interface to **receive** the group.
- `sender.setNetworkInterface(nic)` explicitly specifies the interface to **send**.
- `sender.setTimeToLive(0)` requests local transmission.
- `receiver.setSoTimeout(1500)` prevents infinite blocking receive; if no packet arrives, it throws `SocketTimeoutException`. **`finally` still leaves the group**, and try-with-resources closes the sockets.
- `leave-group-called=true` confirms the `leaveGroup` call **returned successfully** in the test. It does not prove that routers/OS have cleared all forwarding state on the network.

Compared with `DatagramChannel`, the classic API fits traditional code, while NIO fits applications with `Selector`, nonblocking I/O, and the need to manage multiple channels.

## 22. Comparing the Two APIs for Membership Cleanup

| Aspect | `DatagramChannel` | `MulticastSocket` |
| --- | --- | --- |
| Join IPv4 group on NIC | `join(group, nic)` | `joinGroup(new InetSocketAddress(group,0), nic)` |
| Separate membership token | `MembershipKey` | Returns no equivalent token |
| Explicitly leave group | `key.drop()` | `leaveGroup(groupSocketAddress,nic)` |
| Close UDP resource | `channel.close()` | `socket.close()` |
| Select outgoing NIC | `setOption(IP_MULTICAST_IF,nic)` | `setNetworkInterface(nic)` |
| TTL | `setOption(IP_MULTICAST_TTL,0)` | `setTimeToLive(0)` |
| Loopback | `IP_MULTICAST_LOOP` | `setOption(IP_MULTICAST_LOOP,...)`; avoid deprecated `setLoopbackMode` |
| Blocking receive timeout | Use nonblocking + `Selector` if bounded wait is needed | `setSoTimeout` + blocking `receive` |
| Data buffer | `ByteBuffer` | `DatagramPacket` containing `byte[]` |
| Socket lifecycle | Try-with-resources | Try-with-resources |

**Do not mix** `DatagramChannel.join` and `MulticastSocket.leaveGroup` for the same membership. They are two different socket-level membership management APIs. If the source code uses NIO, keep the key and drop it; if it uses `MulticastSocket`, store the group + NIC and call the corresponding `leaveGroup`.

## 23. If Multicast Is Not Received: Diagnostic Checklist

A test that runs and prints `received=false` or throws `SocketTimeoutException` is not necessarily a Java bug. Check in order:

1. **NIC name:** Does `getByName` return the exact interface you intended to use? The name belongs to the running machine, not another machine.
2. **State:** Are `isUp`, `supportsMulticast`, and IPv4 present on the interface? If not, fail with an explanatory error, **do not fall back automatically**.
3. **Group IP:** Is it actually multicast? `group.isMulticastAddress()` should be `true`.
4. **Family:** IPv4 groups use `StandardProtocolFamily.INET`; do not accidentally pick an IPv6-only channel/NIC.
5. **Port:** Which UDP port is the receiver binding? Is the sender sending to that exact port?
6. **Join:** Did `join(group, nic)` actually complete and produce a valid key before the sender sent? If it failed, inspect the exception.
7. **Outgoing NIC:** Did the sender set `IP_MULTICAST_IF=nic`, or did the OS pick a different card?
8. **Loopback:** Is loopback enabled for local tests, and does the OS/NIC support local multicast delivery?
9. **TTL:** `0` is local-only; between two machines, a different scope/hop policy is needed, but only increase it when authorized to test on the LAN.
10. **Firewall:** Is the host firewall blocking inbound UDP/multicast?
11. **Switch/AP:** Are IGMP snooping, Wi-Fi client isolation, or multicast-to-unicast conversion interfering?
12. **VPN/VM:** Are virtual routes/interfaces sending traffic into the wrong domain or blocking multicast?
13. **Container:** Does the network namespace have the interface and multicast capability? Container loopback differs from host loopback.
14. **Socket reuse:** Has another process already bound the port? Was `SO_REUSEADDR` set before bind and supported by the OS as expected?
15. **Buffer:** Does the ByteBuffer have enough `remaining()`, and were `flip`/`clear` called properly?
16. **Timing:** Did the receiver join **before** the sender sent? UDP does not buffer packets for late joiners.
17. **Deadline:** Is a 1500/2000 ms timeout too short on a slow CI runner? Increase it within bounds; do not remove the timeout.
18. **Protocol data:** Does the sent datagram have a valid payload? Log length/sequence ID safely; do not log secrets.
19. **Source address:** Does the sender have a source IP matching the interface? Does the NIC/router have a multicast egress/ingress policy?
20. **Membership cleanup:** If an earlier test held the socket/group, is an old process still running and causing interference? Stop it cleanly per its lifecycle.

**Do not infer from `supportsMulticast()==true` that firewalls, routers, or APs must forward the group to every machine.** The API only reports local interface capability, not the entire network.

## 24. When Should You Run Between Two Machines Instead of Loopback?

Local loopback tests verify:
- Java APIs can open the channel/socket.
- The specified NIC is valid.
- `join`/`leaveGroup`/`drop` have the right lifecycle.
- IP multicast loopback on the host works.
- Codec/ByteBuffer/DatagramPacket handle the payload.

Local tests **do not** verify:
- Whether the network switch has proper IGMP snooping.
- Whether router multicast forwarding is configured.
- Whether the other machine's firewall opens the UDP port.
- TTL/routing scope across VLANs.
- Whether group membership reports reach the router in time.
- Whether the Wi-Fi AP does not isolate clients.

To test two machines on a network you administer:
1. Choose a `239.255.x.x` group and agreed port that do not collide with production traffic.
2. On each machine, list NICs and select **that machine's own** interface name.
3. Receiver binds the same UDP port and joins the group on the NIC connected to the right LAN.
4. Sender sets the outgoing NIC explicitly and uses a TTL permitted by the network (e.g., 1 on the same LAN, depending on topology).
5. Send small test packets with a sequence ID and no secrets.
6. Check firewalls, routes, and metrics on both machines.
7. Clean up memberships/sockets after the test.

The complete examples above **intentionally use TTL=0**, so they only test on the same host. **Do not raise TTL to 1 in the demo to "fix" the output** unless you are intentionally moving to an off-host network experiment.

## 25. Source-Specific Multicast and Filtering: Advanced Scope

`MulticastChannel.join(group, nic)` is **Any-Source Multicast (ASM)** in terms of membership: it can receive packets sent to the group from multiple sources within network limits.

Java NIO also provides an overload:

```java
MembershipKey sourceSpecific =
        receiver.join(group, nic, sourceAddress);
```

This is a **code snippet**; `receiver`, `group`, `nic`, and `sourceAddress` must be prepared. It targets **source-specific membership**, requiring a source address that matches the family, is unicast, and **the OS must support source filtering**. Otherwise, the API may throw `UnsupportedOperationException`.

For non-source-specific keys, `block(source)`/`unblock(source)` can filter sources if the OS supports it. Avoid introducing source filtering into a first test:
- It increases OS/switch/router and source-address-binding dependencies.
- It is easy to confuse dropping the whole group with blocking a single source.
- It does not provide authentication: a source IP address is still not equivalent to a trusted application identity.
- The semantics of packets **already buffered before filtering** need separate handling.

Whether a key is ASM or source-specific, **`drop()` is still the operation to leave the membership**; closing the channel also invalidates keys.

## 26. IPv4 and IPv6 Multicast Differ in Scope and Interface

The main example uses IPv4:
- `StandardProtocolFamily.INET`.
- Group `239.255.42.42`.
- Interface with an `Inet4Address`.
- IPv4 TTL.

If using IPv6:
- Choose `StandardProtocolFamily.INET6`.
- Use an IPv6 multicast group, such as `ff02::...` forms for **link-local scope** when appropriate and properly assigned.
- The interface must have an IPv6 address, and many IPv6 link-local addresses carry a **scope ID/interface**.
- `IP_MULTICAST_TTL` represents the IPv6 **hop limit**; semantics for sending to IPv4-mapped destinations may be implementation-dependent.
- IPv6 multicast membership and network policies can differ from IPv4; do not just swap the group string while keeping every assumption unchanged.

**Do not** write a program that only checks `Inet4Address` and then passes an IPv6 group; do not test IPv6 on an interface without an IPv6 address. For a single-protocol lesson, solve IPv4 completely first, then write a separate IPv6 experiment with verified scope/network capabilities.

## 27. Multiple Receivers, Multiple Senders, Multiple Groups

In practice, one process may want to:
- Have one channel join multiple groups.
- Have multiple channels join the same group on the same NIC.
- Have one sender send to multiple groups using the same NIC.
- Have multiple interfaces join the same group.
- Stop one feature by dropping **one** membership while keeping the channel and other groups active.

Group membership example:

```java
List<MembershipKey> memberships = new ArrayList<>();
try (DatagramChannel channel =
        DatagramChannel.open(StandardProtocolFamily.INET)) {
    channel.bind(new InetSocketAddress(54321));
    try {
        memberships.add(channel.join(groupA, nicA));
        memberships.add(channel.join(groupB, nicB));
        // Process datagrams...
    } finally {
        for (MembershipKey key : memberships) {
            if (key != null && key.isValid()) {
                key.drop();
            }
        }
    }
}
```

This is a **code snippet**, not standalone runnable; it needs proper imports, `groupA`/`groupB`/`nicA`/`nicB`, and error handling. It demonstrates a **collection of membership tokens** cleaned up in `finally`. In production, each group/interface has its own lifecycle, quota, and access policy; add rollback handling if the second join fails.

**Caution:** If source-specific and ASM memberships conflict on the same group/interface, `join` may throw `IllegalStateException`; simply adding keys to a collection does not guarantee every join succeeds.

## 28. Common Resource-Lifecycle Mistakes

1. **Joining and discarding the `MembershipKey`:** Cannot drop a specific group while keeping the channel. Keep the key in a clear ownership structure.
2. **Calling only `key.drop()`, without closing the channel:** Leaves the group, but the UDP channel/socket remains open.
3. **Only closing the channel, without explicitly indicating group leave:** OS cleanup still occurs, but it is harder to observe group lifecycles if the app keeps a socket serving multiple groups.
4. **Joining and returning before `finally`:** Return/exception paths can leak memberships. Put `drop` in `finally`.
5. **Using `try (MembershipKey ...)`:** Invalid; `MembershipKey` is not `AutoCloseable`.
6. **Dropping group A and assuming group B also left:** Each key/group is separate; the test in section 19 shows key B stays valid.
7. **Asserting no packets remain right after `drop`:** Already-queued packets can still be read. Check `isValid()` and lifecycle instead.
8. **Calling `leaveGroup` on the wrong interface:** Must leave the exact group/interface that was joined.
9. **Mixing NIO `drop` with `MulticastSocket` `leave`:** Two different resource management APIs.
10. **Not closing `Selector`:** `Selector` also holds resources; use try-with-resources.
11. **Receiver thread stays blocked on shutdown:** Use nonblocking/Selector deadlines, wakeup/cancel, and cooperative close.
12. **Interpreting a socket timeout as absolute packet loss:** No packet in 2 seconds does not prove the network permanently drops traffic.
13. **Not bounding datagram size/volume:** A multicast flood can exhaust CPU/heap; bound payload sizes and packets processed per loop.

## 29. Logic and Security Mistakes When Testing Multicast

1. **Automatically picking the first interface** in enumeration. No guarantee it is the right card.
2. **Selecting an interface just because it has IPv4.** Also need `isUp`/`supportsMulticast`, policy, and appropriate routing.
3. **Setting `IP_MULTICAST_IF` on the receiver and thinking it joined.** That selects the outgoing NIC; it does not register membership.
4. **Sender not setting `IP_MULTICAST_IF`.** The OS may pick the wrong adapter, especially with VPN/VM adapters.
5. **Joining an IPv4 group on an `INET6`-only channel/NIC.** Wrong family.
6. **Assuming a multicast group is a hostname needing DNS resolution.** In these examples the group is a numeric multicast IP, not DNS host service discovery.
7. **Confusing the group IP with a receiver's address.** The sender sends to the group, not to a unicast receiver IP.
8. **Receiver binds the wrong port.** Right group is not enough; the destination UDP port must also match.
9. **Not enabling loopback when testing on the same host.** May fail to receive self-sent packets.
10. **TTL > 0 when only intending a local test.** Packets can escape onto the network; choose TTL = 0 when the goal is local-only.
11. **Believing TTL = 0 is always looped back.** The OS may still not support it; "may be delivered locally".
12. **Confusing `SO_REUSEADDR` with a portable fan-out mechanism.** Multiple sockets on the same port have OS-dependent behaviors.
13. **Using blocking receive without timeout/cancellation.** CI can hang forever.
14. **Forgetting `ByteBuffer.flip`/`clear`.** Payload is read incorrectly or subsequent datagrams have no room.
15. **Reading a datagram with a small buffer and treating the remainder as the next packet.** UDP datagrams can be truncated.
16. **Sending secrets/API tokens over a test group.** Multicast does not automatically authenticate or encrypt.
17. **Trusting source IP as a security identity.** Can be spoofed or insufficient for authorization; requires protocol/app security.
18. **Assuming multicast guarantees delivery.** UDP has no built-in ACK/retransmit.
19. **Using a shared production group for testing.** Can affect other systems; pick an experimental group/port.
20. **Running LAN traffic without authorization.** Test loopback first; only use real NICs/LANs when authorized.

## 30. Testing and Interpreting Results Scientifically

| Test | Valid Verification | Must Not Infer |
| --- | --- | --- |
| Interface probe prints `up=true/multicast=true/ipv4=true` | Local interface has the reported capabilities | Network/firewall definitely permits delivery |
| Sender has `IP_MULTICAST_IF=nic` | Code selected the outgoing NIC | Every packet actually leaves via this NIC under all OS policies |
| `join(group, nic)` returns a valid key | Channel holds a membership token on the group/interface | A receiver has received a packet |
| Test sends 11 bytes and receives `hello-group` | Local multicast data path works in the test environment | LAN/routers/IPv6 multicast definitely work |
| `key.drop()` then `isValid()==false` | Membership token is now invalid | Receive buffer is immediately empty |
| Drop group1, group2 remains valid | Cleanup is per-membership | Group2 definitely has datagrams |
| Close channel, remaining key becomes invalid | Closing the channel cleans up memberships | All network router state disappears instantaneously |
| `MulticastSocket` `leaveGroup` returns | Application called leave successfully | Network has no remaining queued datagrams |
| `Selector.select(2000)==0` | No readiness observed during that wait | Network is permanently broken |
| `SocketTimeoutException` in classic receive | No packet received within configured interval | Sender didn't send or firewall is the sole cause |

To make tests repeatable:
- Start the receiver **before** the sender.
- Choose group/nic/port transparently.
- Bound the wait time.
- Log **only metadata** — group/port/interface, length, and status — never log secrets.
- Measure packet loss/truncation when testing multiple packets.
- Clean up all keys/sockets/selectors even on timeout/exception.
- If retries are needed, use a protocol with sequence IDs and duplicate handling; do not assume "resending is always safe".

## 31. Step-by-Step Lab Checklist

**Preparation:**
1. Have JDK 17+; check `java -version` and `javac -version`.
2. Run `InterfaceProbe282`, identify the card's **exact name**; do not rely on a name from the article.
3. Confirm the card is up/multicast/IPv4. For local tests, check whether loopback supports it.
4. Choose group `239.255.42.42` and keep TTL = 0.
5. Ensure no port/group from another application is used; in same-process tests use port 0.

**Execution:**
1. Compile `ExplicitInterfaceMulticastDemo` and run it with the explicitly chosen interface name.
2. Verify `membership-valid-before=true`, `sent-bytes=11`, and if the OS permits, `received=hello-group`.
3. Verify `membership-valid-after=false` regardless of whether a packet was received.
4. Compile `MembershipCleanupDemo`, verify dropping group1 does not invalidate group2, and closing the channel invalidates group2.
5. Compile `ClassicMulticastSocketDemo`, verify `leave-group-called=true` on a supported loopback environment.

**Post-test:**
1. No Java receiver processes remain running in the background.
2. No UDP sockets/Selectors remain held by the program.
3. All `MembershipKey` instances are dropped or channels are closed.
4. If tested over LAN, stop the sender and clean up group memberships on receivers.
5. Do not put confidential data into logs or payloads.
6. If no packet was received, use the checklist in section 23; **do not** blindly raise TTL or disable firewalls.

## 32. Self-Check Questions

**Q1.** Why does the lab require passing the interface name via the command line?  
**A:** To prevent the OS/JVM from implicitly picking an unsuitable adapter when Wi-Fi, Ethernet, VPN, or VMs are present; the choice becomes explicit and debuggable.

**Q2.** Does `sender.setOption(IP_MULTICAST_IF, nic)` make the sender join the group?  
**A:** No. It selects the outgoing multicast interface; `receiver.join(group, nic)` is what creates membership for the receiver.

**Q3.** Why choose `StandardProtocolFamily.INET`?  
**A:** The example uses the IPv4 group `239.255.42.42`; `INET` matches IPv4.

**Q4.** What object does `join(group, nic)` return?  
**A:** `MembershipKey`, a token representing group membership on that interface.

**Q5.** How do you leave a membership using the NIO API?  
**A:** Call `key.drop()`, preferably inside `finally`.

**Q6.** Does `drop()` close the channel?  
**A:** No. The channel stays open; you must call `channel.close()` when the socket is no longer needed.

**Q7.** Does closing the channel without calling drop invalidate the key?  
**A:** Yes. The Java 17 contract states that closing the channel invalidates memberships.

**Q8.** After dropping group A, does group B automatically become invalid?  
**A:** No. Group B's key remains valid until dropped separately or the channel is closed.

**Q9.** Why might a packet still be received right after `drop`?  
**A:** A datagram already in the socket receive buffer before `drop` can still be read.

**Q10.** What does TTL 0 guarantee?  
**A:** The IPv4 multicast datagram is not transmitted onto the network; it **may** be delivered locally if the OS supports it.

**Q11.** Does `IP_MULTICAST_LOOP=true` always guarantee a local receiver receives the packet?  
**A:** No. Semantics depend on the OS and other policies/adapters/receive paths.

**Q12.** If a receiver joins the right group but binds a different UDP port than the sender sends to, will it get the packet?  
**A:** You cannot expect it to; the destination UDP port must match the listening port.

**Q13.** In `MulticastSocket`, which API should be used to leave a group on Java 17?  
**A:** `leaveGroup(SocketAddress, NetworkInterface)` with the joined group/interface; avoid the deprecated older overloads.

**Q14.** How do you prevent a Java test from hanging when no multicast arrives?  
**A:** With `DatagramChannel`, use nonblocking mode + `Selector` timeout; with `MulticastSocket`, use `setSoTimeout` and clean up in `finally`.

**Q15.** Is `supportsMulticast()==true` enough to confirm the LAN allows multicast?  
**A:** No. OS firewalls, switches/APs, VPNs, and router multicast topology still affect delivery.

**Q16.** Does multicast guarantee every receiver receives the same datagrams?  
**A:** No. UDP is best-effort; application-level reliability is needed if delivery guarantees are required.

**Q17.** Why should `SO_REUSEADDR` be set before `bind` when there are multiple receivers?  
**A:** It is required/conventional on many OSes for UDP port reuse; actual effect still depends on the platform.

**Q18.** Why does the test use the `239.255.x.x` group?  
**A:** It belongs to IPv4 Local Scope per RFC 2365, suitable for administrative/local tests; TTL 0 is what keeps the demo on the local host.

**Q19.** Is `MembershipKey.isValid` a packet delivery indicator?  
**A:** No. It only checks whether the membership token is still valid.

**Q20.** To test multicast between two machines, what must change?  
**A:** Select a real NIC on each machine, use the same group and UDP port, appropriate TTL/network/firewall policies, and have authorization to run LAN tests. The TTL 0 demo is not for two-machine tests.

## 33. Summary of Practical Principles

When testing multicast in Java 17, keep this lifecycle in mind:

```text
Intentionally select a network interface
     ↓
Verify up + multicast capability + address family
     ↓
Open receiver DatagramChannel, bind UDP port
     ↓
MembershipKey = receiver.join(group, selectedInterface)
     ↓
Open sender and set IP_MULTICAST_IF = selectedInterface
     ↓
Set IP_MULTICAST_TTL = 0 for local-only tests
     ↓
Send UDP datagram, receive with bounded timeout
     ↓
finally: membership.drop()
     ↓
try-with-resources: close selector + sender + receiver
```

This is the reference sequence. In multi-group systems, store multiple `MembershipKey` instances and clean up each key per ownership; closing the channel last invalidates any remaining keys. With `MulticastSocket`, switch to the corresponding `joinGroup/leaveGroup` pair.

**Core takeaway:** **Choosing the right interface** ensures packets go out and are received on the right network; **retaining and dropping membership** lets the application leave groups in a controlled way; **closing the socket/channel** releases resources. Never use one operation to assume the other two were performed according to business intent.

## 34. Official Documentation and Related Standards

- Java SE 17 `DatagramChannel` — opening channels by protocol family, send/receive, socket options: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/DatagramChannel.html
- Java SE 17 `MulticastChannel` — `join(group, interface)`, source-specific multicast: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/MulticastChannel.html
- Java SE 17 `MembershipKey` — `drop()`, `isValid()`, buffered datagrams after drop: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/MembershipKey.html
- Java SE 17 `NetworkInterface` — `getByName`, `isUp`, `supportsMulticast`, IP addresses: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/NetworkInterface.html
- Java SE 17 `StandardSocketOptions` — `IP_MULTICAST_IF`, `IP_MULTICAST_TTL`, `IP_MULTICAST_LOOP`, `SO_REUSEADDR`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/StandardSocketOptions.html
- Java SE 17 `MulticastSocket` — `joinGroup`/`leaveGroup` with interface selection, `setNetworkInterface`, `setTimeToLive`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/MulticastSocket.html
- Java SE 17 `Selector` and `SelectionKey` — nonblocking receive and timeouts: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Selector.html
- Java SE 17 `DatagramPacket` — datagram content buffer/offset/length: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/DatagramPacket.html
- RFC 2365 — Administratively Scoped IPv4 Multicast, `239.255.0.0/16` Local Scope: https://www.rfc-editor.org/rfc/rfc2365
