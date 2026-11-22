# Investigating DNS, Multiple Addresses, and Network Interfaces in a Running Environment with Java 17+

When a Java application connects successfully on a laptop but fails in a container, VPN, dual-stack server, or multi-NIC machine, the cause may lie in **name resolution**, **IPv4/IPv6 address ordering**, **network interface configuration**, **the source address selected by the OS**, or **IPv6 scope**. Simply printing `InetAddress.getLocalHost()` and concluding "this machine has one IP and one network card" is often misleading.

This lab guides you through **observing the running environment** with Java 17+ and cross-checking with OS tools, focusing on four questions:

1. How many **IPs, of which address families, and in what order** does Java currently resolve a hostname to?
2. Which **`NetworkInterface`s** does the machine/JVM see, and what `InterfaceAddress`es, prefixes, MTUs, and flags does each interface have?
3. How does **binding a socket to loopback or a specific IP** differ from merely resolving a name, and how do you verify the socket's actual endpoints?
4. Which results are observed facts at measurement time, and which **must not be inferred** from DNS, flags, routes, or a single ping?

By default, all programs only inspect **`localhost`, existing interfaces, and loopback**; they **do not access the Internet** and do not scan ports on other machines. When passing a hostname from a real environment, only measure against authorized services/infrastructure and consider that logging IP addresses, hostnames, interface names, or MACs may contain sensitive information. This lab does not require administrator privileges or changing network configuration.

## 1. Distinguish Five Concepts Before Running the Experiments

~~~text
Hostname / URI host (e.g., service.example.test)
                   |
                   | Name resolution (hosts, OS resolver, DNS/cache...)
                   v
       [candidate IP #1, candidate IP #2, ...]
                   |
                   | Select destination address and attempt connection
                   v
         Remote IP address + port
                   |
                   | OS routing / address selection / policy
                   v
         Local source IP + local ephemeral port
                   |
                   | Network interface / routing table / network namespace
                   v
               Network path
~~~

**Do not conflate**:

- **Hostname:** the name provided by the application or URL. One name can map to 0, 1, or many IPs; it can change over time.
- **`InetAddress`:** an IP address object (IPv4 or IPv6); it does not contain a TCP/UDP port. An `InetAddress[]` array is a list of candidates, **not** a list of successful TCP connections.
- **`InetSocketAddress`:** an endpoint consisting of IP/hostname + **port**, which may be in an **unresolved** state.
- **`NetworkInterface`:** an interface visible to the JVM on the current system; an interface may have no IP, one IP, or multiple IPs across multiple families.
- **Routing/source-address selection:** decides the interface/source address for a **specific destination**; do not infer this solely from `NetworkInterface.isUp()` being true.

A Wi-Fi card may carry a private IPv4 address, one or more global/link-local IPv6 addresses, and temporary/privacy IPv6 addresses. At the same time, a machine may have Ethernet, loopback, VPN, VPN split tunnel, VLAN, Docker/veth, Hyper-V/VMware adapters, or interfaces visible only inside a container's network namespace.

**DNS A/AAAA records do not mean a local interface is using them.** `A` provides candidate IPv4 addresses; `AAAA` provides candidate IPv6 addresses. Results from the Java resolver may also come from `hosts`, cache, or another name service mechanism, without necessarily issuing a new DNS query.

## 2. Java 17 API Reference Table

| API | What does it return? | Purpose |
| --- | --- | --- |
| `InetAddress.getAllByName(host)` | `InetAddress[]` from the name service | Inspect **multiple candidate addresses** |
| `InetAddress.getByName(host)` | **One** `InetAddress` | Look up a single address; insufficient for dual-stack inspection |
| `InetAddress.getLoopbackAddress()` | IPv4 127.0.0.1 or IPv6 ::1 depending on environment | Safe local-machine experiments |
| `InetAddress.getLocalHost()` | IP after resolving **the local host's name** | Diagnose machine hostname; does **not** list all interfaces |
| `InetAddress.getByAddress(rawBytes)` | IPv4/IPv6 object from valid bytes | Create an IP object **without reverse lookup** |
| `InetAddress.getHostAddress()` | Literal IP address string | Display IP without reverse DNS |
| `InetAddress.getCanonicalHostName()` | Best-effort canonical name | May trigger reverse/name lookup; can be slow |
| `InetSocketAddress.createUnresolved(host,port)` | Hostname + port endpoint, **without DNS** | Store target or let some proxies resolve it themselves |
| `NetworkInterface.getNetworkInterfaces()` | Enumeration of interfaces | Inspect devices visible to the JVM |
| `NetworkInterface.getByName(name)` | Interface by name or null | Select a specific interface after listing |
| `NetworkInterface.getByInetAddress(ip)` | Interface with that **local IP** or null | Find the interface owning a local address |
| `NetworkInterface.getInterfaceAddresses()` | List of `InterfaceAddress` | IP/prefix/broadcast of an interface |
| `NetworkInterface.getInetAddresses()` | Enumeration of `InetAddress` | Interface IPs, **excluding prefix** |
| `NetworkInterface.isUp/isLoopback/isVirtual` | Interface attributes | Diagnose state/type |
| `NetworkInterface.supportsMulticast()` | Reported multicast capability | Does not prove multicast packets will actually arrive |
| `NetworkInterface.getMTU()` | Reported Maximum Transmission Unit | Reference data about the network path |
| `Inet6Address.getScopeId()` | Numeric scope identifier | Important for scoped/link-local IPv6 |
| `Socket.getLocalAddress/getLocalPort` | **Selected source** endpoint after connect/bind | Observe the real socket |
| `Socket.getInetAddress/getPort` | **Connected destination** endpoint | Distinguish actual route from DNS candidates |

These APIs may throw `SocketException`, `UnknownHostException`, or `SecurityException` depending on the environment. The fact that an interface or address does not appear in the JVM **does not prove the OS lacks it**, because containers/network namespaces, access controls, and network state can make the lists differ. A snapshot is also not guaranteed to stay the same when VPN/Wi-Fi changes state.

## 3. Reading DNS Results Correctly: One Name Does Not Mean One IP

### 3.1. Why is `getAllByName` more important than `getByName`?

~~~java
InetAddress[] candidates =
        InetAddress.getAllByName("localhost");

for (InetAddress address : candidates) {
    System.out.println(address.getHostAddress());
}
~~~

This is an **illustrative snippet**, assuming `import java.net.InetAddress` and handling `UnknownHostException`. On one system, `localhost` may map to both `127.0.0.1` and `::1`; on another, it returns only one family. For service hostnames, the resolver may return multiple A/AAAA records, and some IPs change due to DNS round-robin or load balancing.

`InetAddress.getByName(host)` returns **one address**. It does not prove "the host has only that exact IP". If you need to observe all candidates at measurement time, use `getAllByName`. However, **"all" here means all address entries returned by the configured name service in that lookup**, and does not guarantee you have discovered every backend in a service discovery system.

**Specifically:** `InetAddress.getByName(null)` or an empty hostname in Java 17 has semantics that return loopback. Do not use an empty value to check "DNS does not have the host"; validate input first to avoid accidentally connecting to localhost.

### 3.2. Why is A/AAAA ordering unstable or different across machines?

Factors that can affect it:

- OS resolver policy, `hosts`, local DNS proxy, VPN DNS, split-horizon/internal DNS.
- DNS servers returning multiple A/AAAA records with different orders and TTLs.
- Java name-resolution cache: the JVM may serve stale results within TTL; negative lookups are also cached.
- IPv4/IPv6 capability of the OS/network namespace, dual-stack configuration.
- `java.net.preferIPv4Stack` and `java.net.preferIPv6Addresses` read at JVM startup.
- Container images with their own `/etc/hosts`/resolver configuration and their own network namespace.

The same hostname on a laptop and in a container **can legitimately return different lists**, because the two environments use different configurations/namespaces/resolvers. If one `getAllByName` call returns `[IPv4, IPv6]` and another returns `[IPv6, IPv4]`, do not assume that is a DNS bug. Cross-check policy and measurement time.

### 3.3. Suggested Inspection Checklist

When inspecting an authorized name, record:

| Measurement Field | Example of How to Record |
| --- | --- |
| Environment | Physical machine/VM/container, JDK vendor/version |
| Input host | Approved test domain or hostname |
| Time of query | UTC or local timestamp with timezone |
| Candidate count | Length of `getAllByName(host)` |
| Family and position | `[0] IPv4`, `[1] IPv6`, ... |
| Literal IP | `getHostAddress()`, store internally only if sensitive |
| JVM preference flags | `java.net.preferIPv4Stack` and `java.net.preferIPv6Addresses` |
| DNS cache settings | `networkaddress.cache.ttl`, negative TTL, actual implementation defaults |
| DNS resolver evidence | Hosts/resolv.conf/OS DNS settings or DNS tools |
| Connect outcome | Result per IP/port **on an authorized service**, with timeout |
| Local source address | `Socket.getLocalAddress()` of a **successful connection** |

Do not treat the runtime of `getAllByName` as "exact DNS network RTT": it may be a cache hit or `hosts` lookup that sends no packets, and JIT/scheduling/GC also add noise.

## 4. Java 17+ Example #1: Surveying Multiple Addresses with `InetAddress`

This example uses `localhost` by default so it works offline. If you pass another hostname, the JVM will perform name resolution according to the environment's real configuration — **only pass domains authorized for testing**.

Create the file **`DnsLookupSurveyDemo.java`**:

~~~java
import java.net.*;
import java.util.*;

public final class DnsLookupSurveyDemo {
    public static void main(String[] args)
            throws Exception {
        if (args.length > 1) {
            throw new IllegalArgumentException(
                    "Usage: java DnsLookupSurveyDemo [host]");
        }
        String host =
                args.length == 0 ? "localhost" : args[0];
        if (host.isBlank()) {
            throw new IllegalArgumentException(
                    "Host must not be blank");
        }

        long started = System.nanoTime();
        InetAddress[] all =
                InetAddress.getAllByName(host);
        long elapsedNanos = System.nanoTime() - started;

        System.out.println("queried host: " + host);
        System.out.println(
                "addresses returned: " + all.length);

        for (int i = 0; i < all.length; i++) {
            InetAddress address = all[i];
            String family =
                    address instanceof Inet4Address
                    ? "IPv4" : "IPv6";

            System.out.println(
                    "candidate[" + i + "] " + family
                    + " literal=" + address.getHostAddress()
                    + " loopback=" + address.isLoopbackAddress()
                    + " linkLocal=" + address.isLinkLocalAddress());

            if (address instanceof Inet6Address v6) {
                System.out.println(
                        "  v6 scopeId=" + v6.getScopeId()
                        + " scopedInterface=" +
                        (v6.getScopedInterface() == null
                                ? "(none)"
                                : v6.getScopedInterface().getName()));
            }
        }

        System.out.println(
                "lookup nanos nonnegative: " +
                (elapsedNanos >= 0));
        System.out.println(
                "has at least one candidate: " +
                (all.length > 0));

        InetAddress first = InetAddress.getByName(host);
        System.out.println(
                "getByName family: " +
                (first instanceof Inet4Address
                        ? "IPv4" : "IPv6"));

        InetAddress localLoopback =
                InetAddress.getLoopbackAddress();
        System.out.println(
                "system loopback recognized: " +
                localLoopback.isLoopbackAddress());

        InetAddress synthetic4 =
                InetAddress.getByAddress(
                        new byte[]{127, 0, 0, 1});
        byte[] synthetic6bytes = new byte[16];
        synthetic6bytes[15] = 1;
        InetAddress synthetic6 =
                InetAddress.getByAddress(synthetic6bytes);

        System.out.println(
                "synthetic v4 bytes: " +
                synthetic4.getAddress().length);
        System.out.println(
                "synthetic v6 bytes: " +
                synthetic6.getAddress().length);

        InetSocketAddress unresolved =
                InetSocketAddress.createUnresolved(
                        "service.example.invalid", 8443);
        System.out.println(
                "unresolved without DNS: " +
                unresolved.isUnresolved());
        System.out.println(
                "unresolved hostname: " +
                unresolved.getHostString());
    }
}
~~~

Run:

~~~bash
javac --release 17 DnsLookupSurveyDemo.java
java DnsLookupSurveyDemo
java DnsLookupSurveyDemo localhost
~~~

You can add a hostname from your own system:

~~~bash
java DnsLookupSurveyDemo my-authorized-service.internal
~~~

**Note:** the last command is an illustrative internal network name; run it only when that service/hostname exists and you are authorized to inspect it. No public DNS is needed in the default test.

An **example output observed on a local JDK machine**:

~~~text
queried host: localhost
addresses returned: 2
candidate[0] IPv4 literal=127.0.0.1 loopback=true linkLocal=false
candidate[1] IPv6 literal=0:0:0:0:0:0:0:1 loopback=true linkLocal=false
  v6 scopeId=0 scopedInterface=(none)
lookup nanos nonnegative: true
has at least one candidate: true
getByName family: IPv4
system loopback recognized: true
synthetic v4 bytes: 4
synthetic v6 bytes: 16
unresolved without DNS: true
unresolved hostname: service.example.invalid
~~~

**This is not guaranteed stdout on every OS**: the count, order, family, and literal text of `localhost` depend on configuration. The lines `synthetic v4 bytes: 4`, `synthetic v6 bytes: 16`, and `unresolved without DNS: true` are deterministic for the logic in the example. The program does not connect to `service.example.invalid` because `createUnresolved` only creates an endpoint object.

### 4.1. Why not call `getCanonicalHostName()` in the default loop?

`getHostAddress()` gives the literal string. `getHostName()` may return a known name when the object originated from a hostname, whereas `getCanonicalHostName()` may perform a reverse name lookup. A reverse lookup can:
- be slow, time out, or be blocked by DNS/security policy;
- return the IP literal when no name is found;
- return a name that does not match current forward DNS;
- make a test appear to measure a single forward lookup while actually doing extra work.

If you want to inspect **reverse DNS**, run a separate experiment, log latency separately, use authorized names/addresses, and **do not use PTR records as proof of identity verification**. TLS hostname verification or service identity requires separate mechanisms.

### 4.2. Reading the Flags on `InetAddress`

| Method | Correct Interpretation |
| --- | --- |
| `isAnyLocalAddress()` | Wildcard/unspecified address, not a normal connectable remote destination |
| `isLoopbackAddress()` | IPv4 loopback or IPv6 ::1; traffic stays on the local stack |
| `isLinkLocalAddress()` | Address scoped to a link; IPv6 link-local usually needs scope/interface when sending |
| `isSiteLocalAddress()` | API-level classification, **not a complete security classification of private IPs across the Internet** |
| `isMulticastAddress()` | Destination belongs to a multicast range; does not prove a NIC has joined or the network supports it |
| `getAddress().length` | 4 for IPv4, 16 for IPv6 (after API normalization) |
| `getHostAddress()` | Literal text; for scoped IPv6 may include a zone identifier |

These flags help describe an address, **not verify DNS integrity, routing, firewall, or reachability**. For example, `127.0.0.1` is loopback, but port 9000 may not have a listening service; connecting still yields `Connection refused`.

## 5. `InetSocketAddress`: A Hostname May Be Unresolved

Distinguish three objects:

~~~java
InetSocketAddress literal = new InetSocketAddress(
        InetAddress.getLoopbackAddress(), 8080);

InetSocketAddress resolved = new InetSocketAddress(
        "localhost", 8080);

InetSocketAddress unresolved =
        InetSocketAddress.createUnresolved(
                "service.example.invalid", 8080);
~~~

This is an **illustrative snippet inside a Java method** with `import java.net.*`. Meaning:

- `new InetSocketAddress(InetAddress, port)`: the caller already has an IP object; no need to resolve the host string again.
- `new InetSocketAddress(String, port)`: **attempts to resolve the hostname immediately upon object creation**; if it fails, it may still create an object with `isUnresolved()==true`, rather than always throwing `UnknownHostException`.
- `createUnresolved(String, port)`: intentionally **does not resolve** at creation time; `getHostString()` can return the hostname without triggering reverse DNS; `getAddress()` returns `null` when unresolved.

An unresolved endpoint is useful when the transport/proxy **is designed** to resolve the hostname itself (e.g., SOCKS5 supporting hostname forwarding). However, **not every `Socket.connect`/`SocketChannel.connect` accepts an unresolved endpoint for direct connections**; an API may throw `UnknownHostException` or `UnresolvedAddressException`. Do not use `createUnresolved` as a way to "guarantee connection even when DNS fails".

### 5.1. Distinguish DNS Name from Socket Port

DNS A/AAAA only speaks about IP candidates. `service.example.test:443` has:
- host = `service.example.test`;
- port = `443`;
- resolved candidates = IPs returned by the resolver;
- transport = TCP or UDP depending on API/protocol;
- TLS identity = the service's hostname/authority, **not an IP string automatically verified**.

Attempting to connect to a candidate while dropping the URL hostname can break SNI, certificate hostname verification, virtual-host routing, and proxy policy. If you need to pick a specific IP for troubleshooting, preserve the **logical hostname** in HTTP Host/authority and TLS SNI/endpoint identification per library and policy — do not disable TLS verification to force an IP to work.

## 6. JVM IPv4/IPv6 Configuration: Not Just DNS

Oracle Java 17 lists:

| Property | Typical Default | Effect |
| --- | --- | --- |
| `java.net.preferIPv4Stack` | `false` | When true, uses an IPv4-only socket stack and does not communicate with IPv6-only peers |
| `java.net.preferIPv6Addresses` | `false` | For dual-stack hosts, Java defaults to preferring IPv4 for backward compatibility |
| `java.net.preferIPv6Addresses=system` | Explicit selection | Preserves the address order returned by the OS per property semantics |
| `networkaddress.cache.ttl` | Depends on security settings/implementation | Caches **successful** resolution results in seconds |
| `networkaddress.cache.negative.ttl` | Default typically 10 seconds | Caches **failed** resolution results in seconds |

The two `java.net.prefer...` settings are **JVM startup properties**: checked **once when the VM starts** according to Java 17 docs. Run **separate Java processes** to compare:

~~~bash
java DnsLookupSurveyDemo localhost
java -Djava.net.preferIPv6Addresses=true DnsLookupSurveyDemo localhost
java -Djava.net.preferIPv6Addresses=system DnsLookupSurveyDemo localhost
java -Djava.net.preferIPv4Stack=true DnsLookupSurveyDemo localhost
~~~

**Do not expect the output to definitely differ across all four runs.** If the OS or hostname has no IPv6 candidate, a property cannot conjure a new AAAA record. If IPv6 is disabled, `-Djava.net.preferIPv6Addresses=true` will not fix it. If Linux/container has its own resolver/hosts policy, the order may also be the same.

In Windows PowerShell, the Java commands above can run on one line; if the shell specially interprets a `-D...` argument, quote the argument when needed. Do not modify system-wide networking properties of production services to run experiments.

### 6.1. DNS Cache TTL Is a Security Property, Not a Normal System Property

Java 17 documentation distinguishes:

- `networkaddress.cache.ttl`: TTL for successful results.
- `networkaddress.cache.negative.ttl`: TTL for `UnknownHostException`/failed lookups.

These are **security properties**. Setting `-Dnetworkaddress.cache.ttl=0` or `System.setProperty("networkaddress.cache.ttl","0")` **is not the documented, guaranteed way in Java 17**. They can be configured via security configuration (`java.security`) or application startup security policy per JDK; you need to know your JDK version and operational permissions. `Security.getProperty(...)` reads a configured security property; a `null`/blank value does not let you claim caching is "off".

For TTL:
- `-1` (negative) typically means cache forever per policy.
- `0`: do not cache.
- Positive value: number of seconds to keep the cache entry, **not necessarily identical to the authoritative DNS record TTL**.
- Positive/negative caches can differ.
- OS resolver cache, DNS stub, VPN DNS, and server caches still exist **outside the JVM cache**.

Do not measure "DNS TTL" by calling the same hostname 1,000 times in one JVM: results may come solely from cache or `hosts`, with no DNS request sent.

### 6.2. Controlled Cache Experiment

To understand caching without altering real DNS:
1. Use an authorized test DNS zone/server with a small-TTL record and logging.
2. Run separate JVM processes with controlled security-property configuration from startup.
3. Record timestamps, hostnames, `getAllByName` results, and DNS server query logs; do not measure latency alone.
4. Change the record per the test procedure; wait for positive/negative caches to expire.
5. Compare JVM cache vs OS resolver cache; check whether requests actually reach the DNS server.
6. Stop and restore configuration after the test. Do not change all of production DNS just to demonstrate.

In Java 17, the default `networkaddress.cache.ttl` without a SecurityManager is implementation-specific per the Javadoc, **so do not state a single fixed value for all JDK vendors/builds**.

## 7. `NetworkInterface`: A Network Interface Is Not Necessarily a Physical Card

`NetworkInterface` represents an interface with a name/index and assigned IPs. A machine may list:
- Loopback, often named `lo` (Linux/macOS) or another interface on Windows.
- Ethernet/Wi-Fi.
- VPN/TUN/TAP.
- Docker/Kubernetes/WSL/Hyper-V interfaces.
- VLANs/subinterfaces.
- Interfaces that are down or have no IP.

Therefore:
- `getName()` is a platform/JDK-provided name; do not hard-code `eth0`.
- `getDisplayName()` may be user-friendly, but can be null/different from the name.
- `getIndex()` is the index in the current OS; not a persistent identifier across reboots/containers.
- `isUp()==true` only reports that the interface is up/running; **it does not prove Internet connectivity**.
- `isLoopback()==true` describes a loopback interface; it does not mean all traffic over it is safe under business policy.
- `isVirtual()==true` means virtual/subinterface per the API; **it does not guarantee all VPN/VM adapters return true**. A hypervisor virtual adapter can still have `isVirtual()==false` in Java.
- `isPointToPoint()==true` describes the link type, not "TCP connected".
- `supportsMulticast()==true` is a reported capability; it does not prove IGMP/MLD/firewall/routing works.
- `getMTU()` is the interface MTU, **not a guaranteed Path MTU** to a remote destination.
- `getHardwareAddress()` may be null because the interface has no MAC or permissions are restricted; MACs can also change/be randomized. **Do not print raw MACs in default logs**.

### 7.1. `getInetAddresses` vs. `getInterfaceAddresses`

~~~java
for (InterfaceAddress assigned :
        nic.getInterfaceAddresses()) {
    InetAddress ip = assigned.getAddress();
    short prefix = assigned.getNetworkPrefixLength();
    InetAddress broadcast = assigned.getBroadcast();
}
~~~

This is an **illustrative snippet** assuming an existing `NetworkInterface nic`. `getInetAddresses()` only lists IP objects. `getInterfaceAddresses()` adds:
- `getNetworkPrefixLength()`: number of prefix bits, e.g., IPv4 `/24`; Java returns `short`.
- `getBroadcast()`: for IPv4 there may be a broadcast address, though **it can be null** if absent/inapplicable; for IPv6 it returns null because IPv6 **has no broadcast** with the same semantics.

For example, the IPv4 address `192.0.2.15/24` represents an address within the `192.0.2.0/24` prefix in a typical setup. The address here is from the documentation range (not the learner's machine IP). **Do not infer gateway/route from prefix alone**: you need the routing table and neighbor/next-hop information.

An IPv6 interface address might be `2001:db8::1234/64` (documentation address) or `fe80::.../64` (link-local), plus a scope identifier. `getBroadcast()==null` is normal for IPv6.

## 8. Java 17+ Example #2: Surveying Interfaces, IP Assignments, Prefix, and MTU

By default, the program **hides literal IPs and broadcast addresses** to avoid accidentally sharing infrastructure details in screenshots/CI logs. It still displays interface name/index, flags, prefix, IPv4/IPv6, and scope; you can enable `--show-addresses` when **authorized** and running in an internal environment. The program **does not print MAC addresses**.

Create the file **`NetworkInterfaceSurveyDemo.java`**:

~~~java
import java.net.*;
import java.util.*;

public final class NetworkInterfaceSurveyDemo {
    private static String addressFamily(
            InetAddress address) {
        return address instanceof Inet4Address
                ? "IPv4" : "IPv6";
    }

    public static void main(String[] args)
            throws Exception {
        if (args.length > 1 ||
                (args.length == 1 &&
                 !"--show-addresses".equals(args[0]))) {
            throw new IllegalArgumentException(
                    "Usage: java NetworkInterfaceSurveyDemo " +
                    "[--show-addresses]");
        }

        boolean showAddresses = args.length == 1;
        Enumeration<NetworkInterface> enumeration =
                NetworkInterface.getNetworkInterfaces();

        List<NetworkInterface> interfaces =
                enumeration == null
                ? new ArrayList<>()
                : Collections.list(enumeration);

        interfaces.sort(Comparator.comparing(
                NetworkInterface::getName,
                Comparator.nullsLast(String::compareTo)));

        System.out.println(
                "network interfaces found: " +
                interfaces.size());
        System.out.println(
                "address details enabled: " +
                showAddresses);

        int ipv4 = 0;
        int ipv6 = 0;

        for (NetworkInterface nic : interfaces) {
            try {
                System.out.println(
                        "interface name=" + nic.getName()
                        + " index=" + nic.getIndex()
                        + " up=" + nic.isUp()
                        + " loopback=" + nic.isLoopback()
                        + " virtual=" + nic.isVirtual()
                        + " p2p=" + nic.isPointToPoint()
                        + " multicast=" +
                            nic.supportsMulticast()
                        + " mtu=" + nic.getMTU());

                for (InterfaceAddress assignment :
                        nic.getInterfaceAddresses()) {
                    InetAddress address =
                            assignment.getAddress();
                    if (address == null) continue;

                    if (address instanceof Inet4Address) {
                        ipv4++;
                    } else {
                        ipv6++;
                    }

                    String literal = showAddresses
                            ? address.getHostAddress()
                            : "[hidden]";
                    InetAddress broadcast =
                            assignment.getBroadcast();

                    System.out.println(
                            "  " + addressFamily(address)
                            + " address=" + literal
                            + " prefix=" +
                                assignment.getNetworkPrefixLength()
                            + " broadcast=" +
                            (broadcast == null
                                    ? "(none)"
                                    : showAddresses
                                        ? broadcast.getHostAddress()
                                        : "[hidden]"));

                    if (address instanceof Inet6Address v6) {
                        System.out.println(
                                "    scopeId=" + v6.getScopeId()
                                + " scopedInterface=" +
                                (v6.getScopedInterface() == null
                                    ? "(none)"
                                    : v6.getScopedInterface()
                                            .getName()));
                    }
                }
            } catch (SocketException issue) {
                System.out.println(
                        "interface unavailable: " +
                        nic.getName()
                        + " type=" +
                        issue.getClass().getSimpleName());
            }
        }

        System.out.println(
                "IPv4 assignments: " + ipv4);
        System.out.println(
                "IPv6 assignments: " + ipv6);
        System.out.println(
                "MAC bytes intentionally not printed");
    }
}
~~~

~~~bash
javac --release 17 NetworkInterfaceSurveyDemo.java
java NetworkInterfaceSurveyDemo
~~~

Only when authorized to view/log local IPs:

~~~bash
java NetworkInterfaceSurveyDemo --show-addresses
~~~

**The output is live data; there is no fixed stdout for every machine.** A JDK running on a workstation may see a few interfaces, while a machine with VPN/virtual adapters may see dozens, and a container sees only a subset. At the end there will be two lines summarizing IPv4/IPv6 assignment counts and the line `MAC bytes intentionally not printed`. For instance, one test environment showed **74 interface entries**, but **do not treat that number as an expected result**.

### 8.1. How to Read the Output from Each Interface

Suppose you see lines like:

~~~text
interface name=eth0 index=2 up=true loopback=false virtual=false p2p=false multicast=true mtu=1500
  IPv4 address=[hidden] prefix=24 broadcast=[hidden]
  IPv6 address=[hidden] prefix=64 broadcast=(none)
    scopeId=2 scopedInterface=eth0
~~~

This is an **illustrative format output** (not data from the current machine). Interpretation:
- `up=true`: OS reports the interface is up; does not prove there is a route to the Internet.
- `loopback=false`: not a loopback interface.
- `virtual=false`: Java does not classify it as a virtual subinterface; does not confirm physical hardware.
- `p2p=false`: does not report point-to-point type.
- `multicast=true`: reports multicast support; to join a group you still need the right network interface/address family and OS/network verification.
- `mtu=1500`: local MTU; does not say the path MTU to a peer is 1500.
- IPv4 `prefix=24`: number of network prefix bits, not the subnet gateway.
- IPv6 `broadcast=(none)`: expected because IPv6 does not use IPv4-style broadcast.
- `scopeId=2`: IPv6 numeric scope; value depends on OS/interface and is not persistent.

An interface with no `InterfaceAddress` in the output **is not necessarily broken**: it may be down, have link-level state only, have no IP assigned, or the JVM may not be permitted to view addresses.

### 8.2. Checking MAC and Access Permissions

You can call `nic.getHardwareAddress()` when you genuinely need NIC inventory/debugging; the method may return a byte array or null. However, **a MAC is not an immutable secret identifier**—it can be randomized, aliased, changed across VMs/VPNs, and restricted by security policy. If logged in production, mask/hash in a controlled way with a retention policy; do not print it raw to "prove a network card".

## 9. IPv6 Scopes: Why Link-Local Must Be Bound to the Right Interface

IPv4 and IPv6 are both IP, but IPv6 has a prominent **scope** issue:

- `::1` is IPv6 loopback.
- `fe80::/10` belongs to IPv6 link-local, typically used on a single link; to connect to a link-local peer, the OS needs to know the **specific interface/link**.
- `2001:db8::/32` is the documentation prefix, not a real destination for testing the Internet.
- A host can have multiple IPv6 addresses on the same NIC, including temporary/privacy addresses.

Two different interfaces can use the same link-local address form. Therefore an IPv6 endpoint may need a **zone identifier**:

~~~text
fe80::1234%eth0
fe80::1234%7
~~~

The strings above are **illustrative forms**; `eth0` or scope index `7` are just examples, not real interfaces in the current environment. On Windows, zone names/indices may differ. `Inet6Address.getScopeId()` and `getScopedInterface()` provide the object's scope information when present.

### 9.1. Do Not Strip Scope When Storing IPv6 Addresses

If you call `Inet6Address.getHostAddress()` on a scoped link-local address, the output may contain `%scope`. Do not use `split("%")[0]` logic and lose the interface context needed to connect. Do not treat IPv6 link-local as a global address routable across multiple hops. When constructing an `InetSocketAddress`, keep the proper scoped `Inet6Address`/zone identifier when needed.

**IPv6 URL syntax differs from literal socket syntax**: in a URI, a literal IPv6 address must be enclosed in `[ ]`, and an escaped zone identifier follows special URI standard rules. Do not naively concatenate `"http://" + ipv6.getHostAddress() + ":8080"` because `:` in IPv6 causes ambiguity. Prefer a `URI` builder/spec-validated syntax or a logical hostname.

### 9.2. Do Not Infer Private/Global Classification Solely from `isSiteLocalAddress`

Old IPv6 site-local addressing has been deprecated in addressing standards, while ULA `fc00::/7` has its own semantics. `InetAddress.isSiteLocalAddress()` does not replace ACL/route policy or a full IP classifier. For security-sensitive code (SSRF, allowlists), explicitly check IPv4/IPv6, link-local, loopback, unspecified, multicast, ULA/private ranges, mapped addresses, DNS rebinding, and proxy rules.

## 10. Loopback, Wildcard, and Source Address: Verification Experiments with Real Sockets

There are three easily confused cases:

| Local bind | Meaning | Example |
| --- | --- | --- |
| Specific loopback | Binds only to that family's loopback | `127.0.0.1:port` or `[::1]:port` |
| Specific local interface address | Binds to an IP assigned to an interface | E.g., machine's IPv4 or scoped IPv6 |
| Wildcard/any-local | Listens on local addresses per stack/config | `0.0.0.0:port` or `[::]:port` |

**Do not bind a sensitive server to wildcard just to debug**: wildcard can accidentally expose a service to NICs/VPN/container networks, depending on firewall/stack. For demos, use loopback only.

### 10.1. `getLocalHost` Is Not an Interface List

`InetAddress.getLocalHost()` retrieves the machine's hostname and resolves that name. If `hosts` maps the hostname to loopback, you see loopback; if it maps to a LAN IP, you see that IP; if hostname resolution fails, it may throw `UnknownHostException`. **It does not list all NICs/IPs** and does not prove a socket's outbound address.

To know **which local source IP a connected socket used**, read `Socket.getLocalAddress()` and `Socket.getLocalPort()` after connecting. To know the path to a remote host, inspect the routing table/network namespace and actual connection, rather than just picking an address from the NIC list.

### 10.2. Java 17+ Example #3: Server Binding Loopback, Client Connecting and Observing

This example starts a `ServerSocket` on `InetAddress.getLoopbackAddress()` with ephemeral port `0`, uses a server thread to accept, and has the client send `PING` and receive `PONG`. There is no external DNS or remote Internet access. Proxy is explicitly disabled with `new Socket(Proxy.NO_PROXY)` to avoid accidental system proxy settings during the test.

Create the file **`LoopbackBindProbeDemo.java`**:

~~~java
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.*;

public final class LoopbackBindProbeDemo {
    public static void main(String[] args)
            throws Exception {
        InetAddress loopback =
                InetAddress.getLoopbackAddress();
        NetworkInterface localNic =
                NetworkInterface.getByInetAddress(loopback);

        System.out.println(
                "bind address is loopback: " +
                loopback.isLoopbackAddress());
        System.out.println(
                "matching interface found: " +
                (localNic != null));

        try (ServerSocket server =
                new ServerSocket(0, 1, loopback)) {
            server.setSoTimeout(3000);

            FutureTask<String> accepted =
                    new FutureTask<>(() -> {
                try (Socket peer = server.accept()) {
                    peer.setSoTimeout(3000);
                    BufferedReader reader =
                            new BufferedReader(
                                new InputStreamReader(
                                    peer.getInputStream(),
                                    StandardCharsets.US_ASCII));
                    String received = reader.readLine();
                    peer.getOutputStream().write(
                            "PONG\n".getBytes(
                                    StandardCharsets.US_ASCII));
                    return received;
                }
            });

            Thread worker =
                    new Thread(accepted, "loopback-accept");
            worker.setDaemon(true);
            worker.start();

            try (Socket client =
                    new Socket(Proxy.NO_PROXY)) {
                client.connect(new InetSocketAddress(
                        loopback, server.getLocalPort()),
                        3000);
                client.setSoTimeout(3000);
                client.getOutputStream().write(
                        "PING\n".getBytes(
                                StandardCharsets.US_ASCII));

                String reply = new BufferedReader(
                        new InputStreamReader(
                                client.getInputStream(),
                                StandardCharsets.US_ASCII))
                        .readLine();
                System.out.println(
                        "client remote is loopback: " +
                        client.getInetAddress().isLoopbackAddress());
                System.out.println(
                        "client reply: " + reply);
            }

            System.out.println(
                    "server saw: " +
                    accepted.get(3, TimeUnit.SECONDS));
        }
    }
}
~~~

~~~bash
javac --release 17 LoopbackBindProbeDemo.java
java LoopbackBindProbeDemo
~~~

**Stdout observed on a local JDK**:

~~~text
bind address is loopback: true
matching interface found: true
client remote is loopback: true
client reply: PONG
server saw: PING
~~~

On a restricted runtime, `matching interface found` may be false or bind/accept may be forbidden; sandboxed environments that disallow sockets will throw an exception. The example result **does not prove Ethernet/Wi-Fi NICs are working**: both ends are on the machine's loopback.

### 10.3. Why Does the Example Use `new ServerSocket(0,1,loopback)`?

- `0`: lets the OS pick an ephemeral listening port, avoiding hard-coding a port that might already be in use.
- `1`: small backlog hint for the demo; the OS may adjust it per implementation; not a production concurrency limit.
- `loopback`: selects a specific local bind IP, **not listening on all NICs**.
- `setSoTimeout(3000)`: bounded accept/read wait so the test does not hang indefinitely.
- `new Socket(Proxy.NO_PROXY)`: requests a direct socket, bypassing the JVM's default SOCKS routing.
- Client's `getInetAddress()` is the connected remote IP, while `getLocalAddress()` (if logged) is the selected source IP.
- `FutureTask.get(3,TimeUnit.SECONDS)` waits for the test server result; it is not advice to spawn a separate thread per request in a production server.

### 10.4. Extension: Comparing Local Source Address with Remote Destination

After `Socket.connect(...)` succeeds in an authorized experiment:

~~~java
System.out.println("local = " +
        client.getLocalAddress().getHostAddress()
        + ":" + client.getLocalPort());

System.out.println("remote = " +
        client.getInetAddress().getHostAddress()
        + ":" + client.getPort());
~~~

This is an **illustrative snippet inside a block with a connected `Socket client`**. On a machine with VPN/Wi-Fi/Ethernet, the source IP may change depending on the remote IP/route; do not claim that a single loopback connection indicates the source IP used when reaching the Internet.

Do not connect to unfamiliar IPs to "check if the network is alive or dead". If testing remotely, use an approved test endpoint and authorized port, connect once with a timeout, and do not scan subnets/port ranges.

## 11. A Hostname Returns Multiple IPs: Which Address Should You Try Connecting To?

A DNS record returning multiple IPs is usually for redundancy/traffic distribution/dual-stack. However:

- **Multiple IPs do not mean a single connection uses all IPs.** Each TCP connection has one remote `IP:port` endpoint (aside from specialized transport mechanisms outside this scope).
- `InetAddress.getByName(host)` picks one candidate; it does not automatically test all remaining IPs.
- If the first IP has no route or no listening port, a TCP connect may fail immediately or time out. The program may need policy-based fallback.
- Address order is only an **input** to a connection strategy; it is not a measurement of candidate latency or health.
- A high-level HTTP client may implement its own route/proxy/connection-pooling strategy; do not assume it always follows the order printed from `getAllByName`.

### 11.1. TCP Fallback Pattern for Controlled Test Environments

~~~java
// Illustrative code: use only authorized host/port; errors should be logged/aggregated.
// Imports java.net.* and java.io.IOException.
InetAddress[] candidates =
        InetAddress.getAllByName(host);
IOException last = null;
Socket connected = null;

for (InetAddress address : candidates) {
    Socket attempt = new Socket(Proxy.NO_PROXY);
    try {
        attempt.connect(
                new InetSocketAddress(address, port), 1000);
        connected = attempt;
        break;
    } catch (IOException failed) {
        last = failed;
        attempt.close();
    }
}
if (connected == null) {
    throw last != null
            ? last : new IOException("No candidate addresses");
}
// Ownership of connected must be closed by the caller.
~~~

This is a **non-standalone illustrative snippet**: `host` and `port` are validated inputs, and the caller owns and closes `connected` when done. Do **not** naively apply this to POSTs with side effects: reconnecting/falling back and resending a request differs from trying TCP connect before sending payload. If partial application data was already sent, retrying requires idempotency/deduplication.

A good connection strategy may try multiple addresses with time bounds and controlled staggering between IPv4/IPv6 candidates (Happy Eyeballs, RFC 8305) to avoid waiting for a long family timeout. However, **do not open hundreds of parallel sockets**, do not create a port scan, and do not violate network policy. Java 17 `Socket.connect` connects to one endpoint at a time; true Happy Eyeballs requires a strategy/HTTP client that supports it and specific testing—do not assume `getAllByName` does it for you.

### 11.2. Multiple A/AAAA Records Can Have Different States

A dual-stack hostname can have:
- IPv4 connect succeeding while IPv6 fails due to missing IPv6 route.
- IPv6 connect succeeding while IPv4 fails due to firewall.
- Both TCP connects succeeding while HTTPS fails with a different certificate/virtual host.
- DNS resolving successfully while the port is closed on all addresses.
- One IP belonging to an internal network and another to a public network due to split DNS or misconfiguration.

Record **failure per address family and per candidate**, rather than just a generic `ConnectException` and concluding "DNS is broken". An `UnknownHostException` happens **before an IP list is obtained**, whereas `NoRouteToHostException`/`ConnectException`/timeout typically belong to the connection/routing stage (depending on platform).

## 12. When DNS Works but Network Requests Still Fail

Diagnostic layers:

| Stage | Evidence | Possible Errors |
| --- | --- | --- |
| Validate hostname | Nonblank input, IDN policy, URI scheme | Invalid host/URI, wrong name |
| Resolve name | `getAllByName(host)` returns IPs | `UnknownHostException` or stale/negative cache |
| Select IP family | IPv4/IPv6 candidates, JVM properties | Preferring a family with no route |
| Select route/source | OS routing table and actual local endpoint | Wrong VPN split route, source address mismatch |
| TCP connect | `Socket.connect(..., timeout)` or HTTP client connection | Refused, timeout, no route |
| Proxy | ProxySelector/HTTP CONNECT/SOCKS policies | Path differs from direct, 407, proxy auth |
| TLS | SNI, certificate, endpoint verification | SSLHandshakeException/hostname mismatch |
| HTTP | Status, headers, response body | 4xx, 5xx, 429, redirect |
| Application | Protocol response/message semantics | Auth/session/business failure |

**`DNS success != TCP success != TLS success != HTTP 200 != business success`**. Do not replace a hostname with a resolved IP literal to "fix DNS" and then disable certificate hostname verification; that alters the trust boundary.

### 12.1. `InetAddress.isReachable` Is Not a Guaranteed Ping

`InetAddress.isReachable(timeout)`/the overload with `NetworkInterface` may use ICMP echo when OS and permissions allow, or another method such as TCP echo depending on implementation. Many firewalls block probes while still allowing TCP/443. Therefore:

- `isReachable()==false` **does not prove the host/service is down**.
- `isReachable()==true` **does not prove an HTTP endpoint on port 443 is running**.
- Do not use `isReachable` as a health check in place of an authorized **application protocol** check.
- If using the `isReachable(interface, ttl, timeout)` overload, understand that `ttl` is hop limit/network TTL, **not** DNS cache TTL.
- Do not turn the exercise into a ping sweep/port scanner; keep experiments to loopback or authorized endpoints.

## 13. Cross-Checking Java with OS and DNS Tools

When authorized to inspect the environment, cross-check different sources. **Not every command is available on every OS/distro**, so use appropriate tools and do not assume every command returns results identical to the JVM.

| OS | DNS/hostname | Interfaces/addresses | Routes |
| --- | --- | --- | --- |
| Windows | `Resolve-DnsName host` (PowerShell), `nslookup host`, `ipconfig /all` | `Get-NetIPConfiguration`, `Get-NetIPAddress`, `Get-NetAdapter` | `Get-NetRoute`, `route print` |
| Linux | `getent ahosts host`, `resolvectl query host`, `dig A/AAAA` if installed | `ip address show`, `ip link show` | `ip route`, `ip -6 route`, `ip route get <IP>` |
| macOS | `dscacheutil -q host -a name host`, `scutil --dns`, `dig` if available | `ifconfig`, `networksetup -listallhardwareports` | `netstat -rn`, `route -n get <IP>` |

The commands below illustrate **localhost**, without using `ping`/probing the Internet:

~~~powershell
# Windows PowerShell if these cmdlets are available:
Resolve-DnsName localhost
Get-NetIPConfiguration
Get-NetIPAddress
Get-NetRoute
~~~

~~~bash
# Linux (depending on distribution):
getent ahosts localhost
ip address show
ip route
ip -6 route
~~~

~~~bash
# macOS:
dscacheutil -q host -a name localhost
ifconfig
scutil --dns
netstat -rn
~~~

**Do not compare 1:1 without understanding what each command means**:
- `dig` queries DNS in its own way; it can **bypass `/etc/hosts`/NSS policy** that Java and `getent` use.
- `nslookup` may talk directly to a resolver in its own way, not reflecting the full OS/JVM cache.
- `ip address` and `ifconfig` list interfaces visible to the OS **in the current namespace**, not DNS records.
- `route print`/`ip route get` show routing policy based on destination and source, not DNS results.
- On containers, a shell running **inside the container** and a shell running **on the host** may see different NICs/routes; state clearly where each was run.

### 13.1. Checklist for Recording Comparable Evidence

Record four datasets at roughly the same time:
1. Java `InetAddress.getAllByName(host)`: candidate IPs/families.
2. OS resolver (`getent`, `Resolve-DnsName`, or equivalent): output.
3. Java `NetworkInterfaceSurveyDemo`: interfaces/flags/prefix.
4. OS route to **a specific candidate IP**, if authorized.

Then formulate a **testable hypothesis**: "Java is preferring IPv6, but the container has no IPv6 default route", or "the loopback listener only bound `::1`, while the client is trying `127.0.0.1`". Do not assert a root cause solely because two outputs differ.

## 14. DNS Cache and Runtime: How to Avoid Bogus Benchmarks

A naive experiment:

~~~java
for (int i = 0; i < 1000; i++) {
    InetAddress.getAllByName("localhost");
}
~~~

This is an **illustrative snippet**, not a DNS performance benchmark. With JVM/OS caching and loopback mapping, the loop is almost certainly not equivalent to 1,000 DNS network queries.

When analyzing latency:
- Separate **cold lookup** vs. **warm lookup**, and record the experimental conditions.
- Verify real network DNS queries in resolver logs.
- Do not modify the security cache policy of a production JVM serving traffic.
- Use `System.nanoTime()` for elapsed measurement; do not infer exact precision/overhead from a single run.
- Calling `getCanonicalHostName()` adds a reverse lookup; measure it separately.
- A TCP connect measures **DNS + route + handshake** depending on how it is called; to isolate them, resolve first and then connect to each specific IP with a bounded timeout.
- On Windows, there may be a DNS client cache outside the JVM; on Linux, `systemd-resolved`/`nscd`/container resolvers may exist depending on configuration.
- TTL/stale/negative caching behavior varies with JVM security properties and name service.

**Do not set `networkaddress.cache.ttl=0` system-wide just so "every call measures DNS".** Use a dedicated lab environment and understand the request-load impact.

## 15. `NetworkInterface` with Multicast, IPv6, and VPN: Which Signals Are Reliable?

Cases that require a closer look:

**Multicast:** `ni.supportsMulticast()` is a capability flag. A multicast receiver needs to pick the right IPv4/IPv6 group address, the right `NetworkInterface`, and join membership using the corresponding API. Multicast can be blocked by Wi-Fi, VPN, routers, IGMP/MLD, firewalls, or namespaces even when the flag is true. Do not infer "`supportsMulticast=true`" = group traffic will definitely arrive.

**IPv6 link-local:** `scopeId`/zone is critical when a hostname or destination resolves to `fe80::...`. With multiple NICs, the same link-local network does not necessarily route across interfaces; you must choose the right scope and not strip `%zone` from the address.

**VPN:** Windows/macOS/Linux may show tunnel NICs and routes. When VPN is enabled, the route to private hosts may switch to another interface, the DNS server may change, or split DNS may return different A/AAAA records. This does not mean Java is "random"; record routes/resolution before and after enabling VPN in an authorized environment.

**Containers/Kubernetes:** A pod typically sees `lo` and one or a few `eth0`/interfaces **inside its namespace**, not every physical NIC on the host. `InetAddress.getLocalHost()` may return the Pod IP or loopback depending on `/etc/hosts` and hostname policy; do not assume it is the node's public IP. Service DNS, headless services, search domains, and NAT can cause one hostname to yield multiple IPs or a virtual service IP; Java APIs return whatever the configured resolver provides at query time.

**Multiple NICs:** Do not hard-code `NetworkInterface.getByName("eth0")` if the app runs cross-platform. You can choose an interface via explicit configuration, a socket's local address, index, or policy, but indices and addresses can change when an interface restarts. If you must bind to a specific NIC, test both when the NIC disappears/renames and when IPv6 scopes differ.

## 16. Diagnosing Real-World Issues

| Symptom | Common Hypothesis | What to Measure |
| --- | --- | --- |
| `localhost` returns IPv6 first; server only listens on IPv4 | Family/bind mismatch | `getAllByName` order and `ServerSocket.getInetAddress()` |
| `UnknownHostException` in container while host OS resolves | Different DNS search domains/hosts/resolv.conf | Resolver config **inside container**, nameserver logs |
| Java sees one IP; OS sees multiple | Cache, different resolver/API, DNS preference, snapshot timing | TTL, OS lookup tool, Java preferences |
| `getLocalHost()` returns loopback even though machine has LAN IP | Hostname mapped to loopback | Local hosts file and `NetworkInterface` IP list |
| `NetworkInterface.getByName("eth0")==null` | Different interface name or namespace | List actual interface names |
| `isUp()==true` but no Internet access | No route, firewall, proxy, DNS, origin failure | Route to remote IP, TCP connect endpoint |
| IPv6 `fe80::...` connect fails | Missing or wrong scope/interface | `Inet6Address.getScopeId/getScopedInterface` |
| `getInterfaceAddresses()` lacks prefix on a NIC | Interface has no address/permissions/OS reporting | OS interface config, JVM privileges |
| `supportsMulticast()==true` but receives nothing | Network multicast filtering/join group/IGMP | Membership, firewall, NIC, scope |
| `getHardwareAddress()==null` | No MAC or missing privilege | NIC type/OS policy; do not treat null as a mandatory error |
| Socket bound to `0.0.0.0` gets exposed unexpectedly | Wildcard bind + firewall policy | `getLocalSocketAddress`, listening sockets, security rules |
| Server binds `::1` while client uses `127.0.0.1` | Different address family selected | Bind family vs. candidate |
| `isReachable=false` even though HTTPS works | ICMP/TCP echo probe blocked | Test the **authorized protocol/port** |
| Increased DNS TTL but still seeing old IP | JVM/OS/proxy caches or wrong startup config | Security properties, process restart, resolver logs |
| Unexpected source IP observed | Routing/NAT/VPN/split tunnel | `Socket.getLocalAddress()`, OS route, NAT |
| TCP connects but HTTPS fails | SNI/cert/truststore or HTTP authority mismatch | TLS handshake/certificate; do not disable verification |
| A address succeeds; AAAA address times out | Broken IPv6 route/firewall | Per-family connect timeout, route table |
| NIC inventory changes between two runs | VPN, DHCP, hotplug, namespace/permissions | Snapshot timestamp and interface state |

Do not "fix" everything with `java.net.preferIPv4Stack=true`. That may help a specific class of dual-stack issues, but it simultaneously **eliminates the ability to connect to IPv6-only services**. You need root cause, policy, and testing on the real OS/JDK.

## 17. Step-by-Step Analysis Practice on a Running Machine

### Step 1 — Record the Environment

~~~bash
java -version
~~~

Record JDK vendor, major version, and OS/runtime image. If in a container, record namespace/pod/environment per policy; do not dump secrets/env vars into logs.

### Step 2 — Capture Hostname Results

~~~bash
java DnsLookupSurveyDemo localhost
~~~

Fill in an internal log: candidate count, IPv4/IPv6 order, loopback flags. If authorized to test an internal service, switch to the approved hostname. Do not query random names or scan DNS.

### Step 3 — List NICs Without Exposing IPs

~~~bash
java NetworkInterfaceSurveyDemo
~~~

Record interface count, IPv4/IPv6 assignment counts, interfaces that are up, loopback, multicast capability, and MTU. If you genuinely need literal IPs for troubleshooting, run `--show-addresses` in a protected internal terminal/log.

### Step 4 — Verify a Loopback Connection

~~~bash
java LoopbackBindProbeDemo
~~~

Verify the program prints `PONG` and the server sees `PING`. If it fails to run, distinguish sandbox socket restrictions, local OS firewall, family mismatch, and port policy from DNS errors (this test needs no external DNS).

### Step 5 — Compare OS/JVM

Run an appropriate OS resolver command and interface inventory command. Do not assume `dig`, `getent`, and Java always have a single identical output; record differences clearly.

### Step 6 — Change JVM Properties in New Test Processes

~~~bash
java -Djava.net.preferIPv6Addresses=true DnsLookupSurveyDemo localhost
java -Djava.net.preferIPv4Stack=true DnsLookupSurveyDemo localhost
~~~

Do not run these flags as production defaults without proving their impact. Compare candidate count/types/order; explain why the result might not change.

### Step 7 — Draw Evidence-Based Conclusions

Write a short note:
- **Observation:** what appeared in Java/OS.
- **Hypothesis:** DNS preference, route, scope, or binding?
- **Verification test:** one change in the test environment (right IP family, bind address, route check).
- **Result:** did re-measuring improve it?
- **Limitations:** what has not been verified yet (TLS, HTTP, routing, external reachability)?

This is a **reproducible investigation**, not "run a few commands and blame DNS".

## 18. Common Learner Mistakes

| Mistake | Consequence | Correct Understanding |
| --- | --- | --- |
| `getByName(host)` returns one IP → assume host has one IP | Misses A/AAAA candidates | `getAllByName` |
| `getAllByName` returns IPv6 → assume IPv6 connection will succeed | Ignores route/firewall/listener | Authorized connect test with timeout |
| `getLocalHost()` is "current network IP" | May be loopback/hostname mapping | List interfaces and inspect connected socket |
| Calling `getHostName/getCanonicalHostName` in a hot loop | Reverse DNS/blocking overhead | Use `getHostAddress` when only literal is needed |
| Using `createUnresolved` assuming Socket will resolve it | Some direct APIs do not support unresolved | Choose the right resolver/transport |
| Hard-coding interface index/name | Breaks when OS/VPN/container changes | Inspect at runtime, configure explicitly |
| Treating `isUp=true` as Internet alive | False assurance | Route + application-level test |
| Treating `isVirtual=false` as physical card | VPN/VM may report otherwise | Do not infer hardware from a boolean |
| Treating `supportsMulticast=true` as join/traffic succeeds | Network may block it | Check membership/routing/firewall |
| Posting MAC/local IP/internal names in public issues | Leaks infrastructure metadata | Redact by default; log with authorization |
| Binding wildcard to "avoid errors" | May expose server on all interfaces | Bind loopback/allowed IP explicitly |
| Dropping IPv6 `%scope` zone | Link-local connect fails/picks wrong NIC | Preserve the scoped address |
| Treating JVM TTL as authoritative DNS TTL | Misdiagnoses caching | Check security properties + OS resolver cache |
| Using `-Dnetworkaddress.cache.ttl=0` and claiming cache is off | Wrong property type | Use security policy/JDK docs properly |
| Treating `isReachable=false` as host down | ICMP/filtering differs from TCP/HTTPS | Probe the authorized service |
| Connecting directly to IP and disabling TLS hostname verification | Breaks security identity | Keep logical hostname/SNI/verification |
| Comparing host OS with container as one environment | Different namespace/DNS/routes | Run tools in the **same namespace** |
| Trying only the first IP and retrying forever | No bounded timeout/fallback | Candidate addresses + proper retry policy |
| Forgetting to close Socket/ServerSocket | Resource leak | `try-with-resources` |

## 19. Self-Check Questions

**Q1.** `getByName` returns `127.0.0.1`. Does this prove `localhost` has no IPv6?  
**Answer:** No. Use `getAllByName` to observe all candidates per the configured resolver.

**Q2.** A hostname has two A records and one AAAA record. Must Java return all three in the exact DNS packet order?  
**Answer:** No. Java/OS resolvers may cache, sort/filter, or prefer a family per configuration.

**Q3.** Does `InetAddress.getLocalHost()` list every IP on Wi-Fi, Ethernet, and VPN?  
**Answer:** No. It resolves the local host's name to a single `InetAddress`.

**Q4.** Does an interface with `isUp()==true` prove the default route to the Internet works?  
**Answer:** No; you must check routes/firewalls and run an authorized protocol test.

**Q5.** Is `isVirtual()==false` guaranteed to be a physical NIC?  
**Answer:** No. The Java flag refers to virtual subinterfaces; VM/VPN adapters may not be classified the same way.

**Q6.** How do `getInetAddresses()` and `getInterfaceAddresses()` differ?  
**Answer:** The former only returns IPs; the latter adds network prefix/broadcast metadata.

**Q7.** Does `getBroadcast()` return an IPv6 broadcast address?  
**Answer:** No, IPv6 has no IPv4-style broadcast; Java returns null.

**Q8.** What does an `fe80::...` address need when there are multiple NICs?  
**Answer:** It needs the correct IPv6 scope/zone/interface when connecting link-local.

**Q9.** Does `InetSocketAddress.createUnresolved` send a DNS query?  
**Answer:** Not at creation time; the transport/consumer later decides how to handle the hostname.

**Q10.** Does `InetAddress.getByAddress(byte[4])` require a DNS reverse lookup?  
**Answer:** No. It creates an object from raw IP bytes of valid length.

**Q11.** Can `networkaddress.cache.ttl` be set with `-D` as a normal system property and guaranteed to take effect?  
**Answer:** No. Oracle Java 17 documents it as a security property.

**Q12.** Does `java.net.preferIPv6Addresses=true` create an IPv6 route if the OS does not support it?  
**Answer:** No. It affects candidate address selection/preference under appropriate conditions, not OS networking itself.

**Q13.** Does `getAllByName("localhost")` taking 1ms mean the DNS network round-trip is 1ms?  
**Answer:** No. It may be `hosts`/JVM/OS cache plus scheduling overhead.

**Q14.** Does `isReachable` returning `false` prove an HTTP server on port 443 is down?  
**Answer:** No. The probe and the application protocol are different.

**Q15.** A client socket connects to `127.0.0.1`; what does `getLocalAddress()` tell you?  
**Answer:** The local source address of **that connection**, not the source IP when reaching a remote site.

**Q16.** The host has 5 interfaces, but `NetworkInterfaceSurveyDemo` inside a container sees only 2. Is the code definitely wrong?  
**Answer:** No. The container's network namespace/permissions can differ from the host's.

**Q17.** Why not bind a sensitive server to `0.0.0.0` for testing convenience?  
**Answer:** It can expose the listener on multiple NICs, unlike loopback-only, increasing the attack surface.

**Q18.** After `getAllByName` returns IPv4+IPv6, what else is needed to know the service actually works?  
**Answer:** Bounded connect to an authorized endpoint, route/source evidence, and TLS/HTTP/application response depending on protocol.

**Q19.** Does `supportsMulticast()==true` guarantee multicast packets arrive?  
**Answer:** No; membership, OS, route, IGMP/MLD, firewall, and network policy still matter.

**Q20.** Is `getCanonicalHostName` reliable evidence for authenticating a server?  
**Answer:** No. Reverse name resolution is best-effort and does not replace TLS/credential identity verification.

## 20. Post-Lab Implementation Checklist

1. When reporting a DNS issue, record **exact JVM vendor/version, hostname, namespace, and time** before analyzing.
2. Use `InetAddress.getAllByName` for **multi-address inspection**; do not use a single `getByName` to assume a host has one IP.
3. Record **address family order** and startup properties `java.net.preferIPv4Stack`/`java.net.preferIPv6Addresses`.
4. Distinguish **Java positive/negative DNS cache** from OS resolver/authoritative DNS TTL; configure cache as a security property.
5. Inspect `NetworkInterface` and `InterfaceAddress` for NIC flags, IP assignments, prefix, MTU, and scoped IPv6.
6. Do not treat `isUp`, `supportsMulticast`, or `isReachable` as a final health check.
7. For link-local IPv6, preserve the **scope/zone identifier** and select the right NIC.
8. For servers, bind **a specific address per policy**; avoid wildcard when exposure is unnecessary.
9. For clients, use **bounded connect timeouts**, consider all candidate addresses, and use bounded fallback/racing if needed.
10. Keep TLS SNI, origin hostname, and endpoint certificate verification even when testing a specific candidate IP.
11. Cross-check Java and OS tools in the **same machine/container/network namespace**; do not compare different environments and blame Java.
12. Do not put internal hostnames/IPs/MACs in public logs; use redaction/safe retention, and enable `--show-addresses` only when needed.
13. Treat each run as a **snapshot**; do not cache interface indices/addresses indefinitely in services with VPN/DHCP/hotplug.
14. Investigate failures with layered evidence: **DNS → address family → route/source → TCP → TLS → application**.
15. Do not expand the survey into scanning/brute-force; test loopback or authorized endpoints.
16. Clearly note when stdout depends on OS/resolver and **do not fabricate a "standard" NIC/IP list for all learners**.

## Official Sources

- [Java SE 17 — InetAddress](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/InetAddress.html): `getAllByName`, `getByName`, `getLocalHost`, raw address, reverse lookup, caching, reachability methods.
- [Java SE 17 — Inet4Address](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Inet4Address.html): IPv4 address class, special address categories.
- [Java SE 17 — Inet6Address](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Inet6Address.html): IPv6 text format, scope IDs, and scoped interfaces.
- [Java SE 17 — InetSocketAddress](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/InetSocketAddress.html): `createUnresolved`, resolved vs. unresolved socket endpoints.
- [Java SE 17 — NetworkInterface](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/NetworkInterface.html): NIC enumeration, flags, MTU, IP bindings, and subinterfaces.
- [Java SE 17 — InterfaceAddress](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/InterfaceAddress.html): IP assignment, network prefix, and broadcast.
- [Java SE 17 — Socket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html) and [ServerSocket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ServerSocket.html): bind/connect, source/remote IP, timeouts, and socket lifecycle.
- [Oracle Java SE 17 — Networking Properties](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/doc-files/net-properties.html): `java.net.preferIPv4Stack`, `java.net.preferIPv6Addresses`, and DNS security cache policies.
- [RFC 8305 — Happy Eyeballs Version 2](https://www.rfc-editor.org/rfc/rfc8305.html): how dual-stack applications can schedule connection attempts to avoid delays from an unreachable family.
- [RFC 5952 — IPv6 Text Representation](https://www.rfc-editor.org/rfc/rfc5952.html): recommendations for IPv6 text address representation.

**Conclusion:** One name can map to **multiple IPs**, one machine can have **multiple interfaces with multiple addresses**, and a **TCP connection's source IP/route** only has meaning when you observe the actual connection to a specific destination. Inspect Java DNS and network interfaces **layer by layer, snapshot by snapshot**, check IPv4/IPv6, caching, and IPv6 scope, and cross-check OS/network evidence before concluding a network failure.
