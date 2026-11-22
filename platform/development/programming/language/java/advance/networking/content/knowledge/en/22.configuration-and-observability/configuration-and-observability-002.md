# IPv4/IPv6 Preference and Its Impact on Address Selection

## 1. Lesson Objectives

When a Java program connects to a hostname such as **api.example.com**, the machine may know **multiple IP addresses** for that name: one or more **IPv4** addresses from DNS **A** records, along with one or more **IPv6** addresses from **AAAA** records. The program must decide which address to try first, whether the socket type supports that address family, and whether the actual network has a route to it.

Java provides two system properties that are often confused:

- **java.net.preferIPv4Stack**: determines whether to prefer using an **IPv4-only socket stack** instead of sockets that support IPv6/dual-stack.
- **java.net.preferIPv6Addresses**: changes the **priority order of returned addresses** when a hostname has both IPv4 and IPv6; it can be set to **true**, **false**, or **system**.

**The two properties are not synonymous**. The first affects the **capability of the socket stack**; the second primarily affects the **order/preference of name resolution results**. They **do not configure DNS servers**, **do not assign addresses to network interfaces**, **do not fix firewalls**, and **do not guarantee that the preferred address can connect successfully**.

### Three Layers to Distinguish

~~~text
1. NAME RESOLUTION
   api.example.com
      |
      +-- A     192.0.2.20       (IPv4)
      +-- AAAA  2001:db8::20     (IPv6)
      |
      v
   InetAddress.getAllByName(host)
   -> list of addresses according to Java / resolver policy

2. TARGET AND SOCKET TYPE SELECTION
   application/API picks an InetAddress to try
      |
      +-- Inet4Address
      +-- Inet6Address
      |
   java.net.preferIPv4Stack may restrict IPv6 sockets

3. ACTUAL CONNECTION
   Socket.connect / HTTP client / TLS client
      |
      +-- OS route, source address, interface, DNS cache
      +-- TCP/UDP, firewall, proxy, server listener
      +-- retry/fallback or racing if supported by client
      |
   Socket.getInetAddress() / getLocalAddress()
   shows the address of the specific connection
~~~

**A hostname having an AAAA record does not mean the machine can connect over IPv6.** A system having IPv6 sockets also does not guarantee the server is listening on IPv6. Conversely, Java preferring IPv4 first **does not mean IPv6 is disabled**.

This lesson guides you on how to read Java 17 APIs, choose flags for the right goal, observe results in practice, handle dual-stack safely, and run a Java 17 program with both IPv4/IPv6 loopback.

## 2. Fundamentals: IPv4, IPv6, Hostname, and Address

### 2.1. IPv4 and IPv6 Are Two Address Families

| Characteristic | IPv4 | IPv6 |
| --- | --- | --- |
| Address width | 32 bits | 128 bits |
| Documentation example | **192.0.2.20** | **2001:db8::20** |
| Loopback | **127.0.0.1** | **::1** |
| Common wildcard bind | **0.0.0.0** | **::** |
| Java address type | **Inet4Address** | **Inet6Address** |
| Typical DNS record | **A** | **AAAA** |
| Common API | **InetAddress** | **InetAddress** |

The addresses **192.0.2.0/24** and **2001:db8::/32** are used as documentation examples according to standards, not a promise that they are live Internet servers.

Java provides a common abstraction:

~~~java
InetAddress a = InetAddress.getByName("127.0.0.1");
InetAddress b = InetAddress.getByName("::1");

System.out.println(a instanceof Inet4Address); // true
System.out.println(b instanceof Inet6Address); // true
~~~

These two calls check **IP literals**. They do not need to query DNS to determine the address family. In particular, **being able to parse an IPv6 literal does not prove an IPv6 socket can connect**: in the test section, even when the JVM is run with an IPv4-only stack, Java still recognizes the type of the string ::1.

### 2.2. A Hostname Can Carry Multiple Addresses

For example, the hostname **service.example.test** is configured in the name service:

~~~text
service.example.test.  A     192.0.2.20
service.example.test.  AAAA  2001:db8::20
~~~

Resolution result in Java:

~~~java
InetAddress[] candidates =
        InetAddress.getAllByName("service.example.test");
for (InetAddress ip : candidates) {
    System.out.println(ip.getHostAddress() + " " +
            ip.getClass().getSimpleName());
}
~~~

The snippet above requires **service.example.test to exist in an actual test DNS/hosts environment**; this is an illustrative name, not meant to require a fixed Internet result.

**Do not equate the returned list with raw DNS data.** InetAddress may use the OS name service, hosts file, cache, other name services, and transformations such as DNS64/NAT64 in certain environments. Therefore, use **InetAddress.getAllByName()** to observe **what Java sees**, while DNS tools only help inspect the record source.

### 2.3. IPv4-Mapped IPv6 and Dual-Stack

On many operating systems, an IPv6 socket can communicate with an IPv4 destination using **IPv4-mapped IPv6 addresses** or dual-stack support. This is a detail of native socket/OS policy; you should not infer that **every** socket bound to **::** accepts IPv4 on every operating system.

If the operating system sets **IPV6_V6ONLY** on a listening IPv6 socket, it does not accept IPv4 on the same socket. Java and OS behavior can differ across vendors/versions/platforms. Therefore, you need to **test actual connections** from both IPv4 and IPv6 to the server port, rather than just checking that a bind succeeds.

## 3. java.net.preferIPv4Stack: Selecting an IPv4-Only Stack

According to Java SE 17 **Networking Properties**:

- By default, **java.net.preferIPv4Stack=false**.
- If the OS has IPv6, native sockets by default can use IPv6 and on many systems allow the application to communicate with both IPv4 and IPv6.
- When **java.net.preferIPv4Stack=true** is set, the JVM prefers **IPv4-only sockets**; the application cannot communicate with an IPv6-only peer over standard IPv6 sockets.

### Enabling via JVM Startup Option

~~~bash
java "-Djava.net.preferIPv4Stack=true" -cp . IpFamilyPreferenceDemo
~~~

**This is a JVM system property**, not an environment variable named preferIPv4Stack. Use **-D** when starting the process, **before the class name**. Putting quotes around the entire -D argument is also suitable when running in Windows PowerShell.

**Do not set it in main and expect to change the socket stack immediately**:

~~~java
// Unreliable for changing the policy after the JVM has initialized networking.
System.setProperty("java.net.preferIPv4Stack", "true");
~~~

The Java 17 Javadoc states that the two IPv4/IPv6 properties are **read once when the JVM starts**. If you need to compare, launch **separate Java processes** with different flags. Do not run a single process, change System.setProperty, and treat subsequent InetAddress calls as independent tests.

### What Can and Cannot IPv4-Only Do?

| Scenario | Expected Impact |
| --- | --- |
| Application only connects to **IPv4-only server** | May work normally |
| Hostname has both A and AAAA | Java results may only provide IPv4 addresses with the stack forced to IPv4; verify on actual JDK |
| Destination only has AAAA and IPv6 | No IPv6 connection path using standard IPv4-only stack |
| Host OS still supports IPv6 | The property does not disable IPv6 for the entire OS or any other programs |
| Java parses literal **::1** | Can still create an Inet6Address object; **does not guarantee an IPv6 socket can be opened** |
| IPv4 is blocked by firewall, IPv6 works | IPv4-only can make the situation **worse** |

**Do not enable preferIPv4Stack=true by default just because of an undiagnosed IPv6 error**. It may mask a short-term routing issue while breaking connectivity to IPv6-only endpoints, especially on cloud/network infrastructure that has gradually transitioned to IPv6.

## 4. java.net.preferIPv6Addresses: Address Ordering

This property is used by JDK 17 to adjust the order of addresses when a hostname has **both IPv4 and IPv6** and the operating system supports IPv6.

| Value | Meaning | Note |
| --- | --- | --- |
| **false** (default) | Prefer IPv4 before IPv6 when both are present | Java's backward compatibility choice |
| **true** | Prefer IPv6 before IPv4 if capable | **Does not** force IPv6-only; IPv4 can still be used |
| **system** | Preserve the address order returned by the **system-wide resolver/OS** | There is no single fixed order across all OSes |
| Unset | Equivalent to the default policy false when no other configuration exists | Check actual JVM flags when deploying |

Start separate test processes:

~~~bash
# Default: usually prefers IPv4.
java -cp . IpFamilyPreferenceDemo

# Put IPv6 first if both families are available.
java "-Djava.net.preferIPv6Addresses=true" -cp . IpFamilyPreferenceDemo

# Preserve the order provided by the OS resolver.
java "-Djava.net.preferIPv6Addresses=system" -cp . IpFamilyPreferenceDemo
~~~

### Why Does Java 17 Prefer IPv4 by Default?

The Javadoc explains the **backward compatibility** factor. Many legacy applications expect **InetAddress.getHostAddress()** to be an **a.b.c.d** address and only have IPv4 networks. Preferring IPv4 when both are present reduces surprises when running those applications.

However, a modern program **should not assume an InetAddress is an Inet4Address**. Do not write IP parsing functions by splitting on dots or casting:

~~~java
// BAD: the address may be an Inet6Address.
Inet4Address ipv4 = (Inet4Address)
        InetAddress.getByName("some-host");

// BETTER: branch by family.
InetAddress ip = InetAddress.getByName("some-host");
if (ip instanceof Inet4Address) {
    // IPv4 logic when truly needed.
} else if (ip instanceof Inet6Address) {
    // IPv6 logic when truly needed.
}
~~~

When the application does not need IP-specific operations, use the general **InetAddress** and let the networking API handle both families.

### What If Both Flags Are Set?

~~~bash
java "-Djava.net.preferIPv4Stack=true" "-Djava.net.preferIPv6Addresses=true" -cp . IpFamilyPreferenceDemo
~~~

These two flags **do not create a working IPv6 socket**. Setting preferIPv6Addresses=true only requests IPv6 preference at the address ordering layer; preferIPv4Stack=true selects the **IPv4-only socket stack**. When goals conflict, **socket capability is the hard limit**: the program cannot reach an IPv6-only endpoint simply by preferring IPv6 addresses first.

In the Java test environment used in this lesson, this pair of flags caused **localhost** to be returned with IPv4 only. That is an observed test result on a specific runtime; you must re-measure on your actual deployment JDK/vendor/OS rather than extrapolating from a single run.

### What Is System Order?

In **system** mode, Java preserves the result order from the OS resolver. The OS resolver may apply **source/destination selection policies** based on IPv6 availability, prefix policy, scope, and network configuration (reference RFC 6724).

**system does not always mean IPv6 first**. On a dual-stack laptop, the order may be IPv6 first; inside a container, Windows policy, VPN, or an IPv4-only machine, the result may differ. Therefore, sample program output should note the machine/JVM being used.

## 5. How Do InetAddress.getByName and getAllByName Affect Resolution?

### 5.1. Resolving Hostnames via APIs

~~~java
InetAddress first = InetAddress.getByName("localhost");

InetAddress[] all = InetAddress.getAllByName("localhost");
for (InetAddress a : all) {
    System.out.println(a.getHostAddress());
}
~~~

**getByName(...)** returns one InetAddress for the hostname; when multiple addresses are available, the resolver/JVM's ordering policy affects which address is chosen. **getAllByName(...)** returns an array of addresses provided by the resolver for the hostname, already affected by Java/system policy.

Do not use **getByName()** to prove that a remote service is actually reachable. Name resolution is only the first step; the TCP handshake can still fail due to the server not listening, firewall, routing, or network conditions.

### 5.2. Both A and AAAA Exist, but Both Cannot Be Used?

Example:

~~~text
service.example.com
    A    -> 192.0.2.20
    AAAA -> 2001:db8::20

JVM default: IPv4 may be first
JVM preferIPv6Addresses=true: IPv6 may be first
JVM preferIPv6Addresses=system: follows OS-returned order
JVM preferIPv4Stack=true: IPv6 usage capability is restricted
~~~

If the server only **listens on 192.0.2.20:443**, preferring IPv6 to 2001:db8::20 may cause a timeout or connection refused before a client tries IPv4. Conversely, if the IPv4 route is broken but IPv6 works, preferIPv6Addresses=true can improve outcomes **for a client that selects/tries in that order**.

Do not say "if A and AAAA exist, Java always tries both" or "setting true means Java always picks IPv6". **The API/client implementation itself decides how to try multiple candidates**.

### 5.3. DNS Cache Makes Repeated Tests Look Identical

**InetAddress** caches both successful and failed resolution results. Therefore:

- Changes to A/AAAA records are not necessarily seen immediately by a running JVM.
- The TTL of Java's name-service cache can be affected by security properties such as **networkaddress.cache.ttl** and **networkaddress.cache.negative.ttl**, JDK version rules, and providers.
- The DNS TTL on the authoritative server and the cache TTL in the JVM/OS may not be the same.
- Testing with a **fresh JVM** can be useful when changing IPv4/IPv6 flags, which are startup-only.

**networkaddress.cache.ttl is a security property**; you should not assume that passing **-Dnetworkaddress.cache.ttl=0** is always the right way to configure it. Consult the Javadoc and the runtime's **JAVA_HOME/conf/security/java.security** file; manage caching according to system policy. Do not disable caching unconditionally, as it can increase DNS load and introduce new failures.

## 6. Address Order Does Not Equal the Selected Network Path

A connection flow must consider at least four decisions:

~~~text
Hostname
   |
   v
Name service / hosts / DNS A,AAAA
   |
   v
Address ordering (Java property + OS)
   |
   v
Client API picks address to try
   |
   v
OS selects source address + route for destination
   |
   v
Connect success/failure (firewall, listener, NAT, proxy...)
~~~

Distinguish between:

1. **Destination family selection**: whether the client tries the server's IPv4 or IPv6 address.
2. **Source address selection**: the OS chooses the source address of the interface matching the route/destination.
3. **Socket family/capability**: IPv4-only, IPv6-only, dual-stack.
4. **Connection strategy**: try one address, try sequentially, or race multiple addresses over time.

System properties only affect **part** of the pipeline. RFC 6724 describes source/destination selection policies for IPv6 and IPv4-mapped addresses. RFC 8305 describes **Happy Eyeballs v2**: how to sort and interleave address attempts to reduce latency when one family does not work.

**You cannot infer that every Java 17 API implements Happy Eyeballs just from these two system properties**. With a **Socket** you create manually, to have fallback you may need to manage the candidate list and retries yourself; with an HTTP client/framework, retry/racing is a version and implementation detail that must be observed.

### Sequential Fallback When Managing Socket Manually (Snippet)

~~~java
// Illustrative snippet: no network access in the demo lesson
// unless using an authorized test host.
static Socket connectSequential(String host, int port)
        throws IOException {
    IOException last = null;
    for (InetAddress addr : InetAddress.getAllByName(host)) {
        Socket socket = new Socket();
        try {
            socket.connect(
                    new InetSocketAddress(addr, port), 1500);
            return socket;
        } catch (IOException failure) {
            socket.close();
            last = failure;
        }
    }
    throw last != null ? last :
            new UnknownHostException("No usable address");
}
~~~

**Explanation:** the code tries the returned addresses sequentially; there is no parallel racing like Happy Eyeballs. If each address times out at 1.5 seconds and the hostname has many unreachable addresses, the total wait time can be large. In production, you need an **overall deadline**, attempt limits, cancellation, telemetry, a retry policy, and appropriate DNS/service discovery handling.

**With HTTPS/TLS**, choosing the target IP **does not allow skipping hostname verification**. The server certificate must represent the **original DNS hostname of the URL**, even though TCP is connecting to a specific IP. Do not connect directly to an IP and accept all certificates just to "bypass DNS".

### IPv6 Preferred, but Service Actually Uses IPv4

Common reasons:

- DNS only provides an A record or the name service returns IPv4.
- IPv6 is disabled in the container/netns/OS or the JVM has **preferIPv4Stack=true**.
- A proxy handles the hostname and chooses the destination according to the **proxy's** policy, not the getAllByName order in the app.
- IPv6 firewall, route, or listener is not working, and the client falls back to IPv4.
- The HTTP client reuses an existing connection already established over IPv4.
- DNS cache/hosts file holds a different result from a recently updated record.
- The client uses an **IPv4 literal** or a pre-configured specific InetSocketAddress, so there is no step to choose between A/AAAA.

Therefore, debugging must record the **actual socket remote address** or proxy route, not just the System.getProperty value.

## 7. Server Address Binding: Localhost, Wildcard, and Dual-Stack

### 7.1. Binding IPv4 Loopback Differs from IPv6 Loopback

~~~java
ServerSocket ipv4Listener = new ServerSocket(
        8080, 50, InetAddress.getByName("127.0.0.1"));
~~~

The port is only open on the IPv4 loopback **127.0.0.1**; do not expect a client connecting to **[::1]:8080** to automatically switch to IPv4.

Similarly:

~~~java
ServerSocket ipv6Listener = new ServerSocket(
        8080, 50, InetAddress.getByName("::1"));
~~~

This listener binds only to the IPv6 loopback in normal cases, provided the OS and JVM support IPv6 sockets. If the JVM is running with **preferIPv4Stack=true**, do not assume the IPv6 bind call will succeed. These two illustrative snippets should not be run on the same port 8080 in an environment where a service already exists; the complete program uses **port 0** to avoid conflicts.

### 7.2. Wildcard Binds and IPv6-Only Policy

| Bind address | Basic meaning | What still needs checking |
| --- | --- | --- |
| **127.0.0.1** | IPv4 loopback | Only same-machine clients using IPv4 loopback |
| **::1** | IPv6 loopback | Only same-machine clients using IPv6 loopback |
| **0.0.0.0** | All IPv4 interfaces in the namespace | Whether firewall/ACL/port allows connections |
| **::** | All IPv6 interfaces in the namespace | Whether OS IPV6_V6ONLY/dual-stack still accepts IPv4 |
| **A specific IPv4/IPv6 interface** | Only the bound interface/address | Port, route, DNS, and OS permissions |

**Do not use wildcard bind for exercise servers when unnecessary**, because it can accidentally expose the service to the LAN/Internet. The demo uses loopback to ensure traffic stays on the test machine.

### 7.3. IPv6 Link-Local Needs a Scope Zone

IPv6 addresses of the form **fe80::...** are **link-local** and usually require a **scope_id/zone identifier** to specify the interface, such as a **%** after the address and a valid interface name (specifics depend on the OS). Java **Inet6Address** supports scoped addresses; you can inspect NetworkInterface.getName() and Inet6Address.getScopedInterface().

Do not simply turn a link-local literal into a public address for use on the Internet. For **URIs with IPv6 literals**, wrap them in square brackets, for example **http://[::1]:8080/health**. Escaping the percent sign in an IPv6 zone ID within a URL has specific rules; do not concatenate strings manually—use an appropriate URI builder/parser.

## 8. Complete Java 17 Program: Observing Flags, Address Order, and Loopback

**IpFamilyPreferenceDemo.java** does not use Internet DNS or external hosts. It:

1. Prints the two JVM properties at **startup**.
2. Classifies the literal **127.0.0.1** as Inet4Address and **::1** as Inet6Address.
3. Uses **InetAddress.getAllByName("localhost")** to print the **actual address order** that Java sees; prints getByName("localhost") to compare a single selection.
4. Creates a **ServerSocket bound explicitly to 127.0.0.1** on an ephemeral port and calls **Socket.connect** to it; asserts both ends are connected.
5. If not forced to IPv4-only, attempts a similar round on **::1**; may report **UNAVAILABLE** when the OS/container lacks a usable IPv6 loopback.
6. If run with **preferIPv4Stack=true**, reports **NOT_TESTED** for IPv6 TCP because the JVM is configured for IPv4-only; still prints the IPv6 literal type to illustrate **parsing vs. connect capability**.
7. Closes all sockets via try-with-resources, opens no public listener, and sends no data to the Internet.

### File IpFamilyPreferenceDemo.java

~~~java
import java.net.*;
import java.util.*;
import java.io.IOException;

public class IpFamilyPreferenceDemo {
    static String family(InetAddress address) {
        if (address instanceof Inet4Address) return "IPv4";
        if (address instanceof Inet6Address) return "IPv6";
        return "unknown";
    }

    static void require(boolean okay, String detail) {
        if (!okay) throw new AssertionError(detail);
    }

    static void connectToLoopback(InetAddress address)
            throws IOException {
        try (ServerSocket listener =
                    new ServerSocket(0, 1, address);
             Socket client = new Socket()) {
            client.connect(
                    new InetSocketAddress(
                            address, listener.getLocalPort()),
                    2000);
            try (Socket accepted = listener.accept()) {
                require(accepted.isConnected(),
                        "Accepted socket not connected");
                require(client.isConnected(),
                        "Client socket not connected");
                require(family(client.getInetAddress())
                                .equals(family(address)),
                        "Connected to wrong address family");
                require(family(accepted.getLocalAddress())
                                .equals(family(address)),
                        "Listener bound to wrong address family");
            }
        }
    }

    public static void main(String[] args) throws Exception {
        String stack = System.getProperty(
                "java.net.preferIPv4Stack", "(unset)");
        String addresses = System.getProperty(
                "java.net.preferIPv6Addresses", "(unset)");

        System.out.println("preferIPv4Stack=" + stack);
        System.out.println("preferIPv6Addresses=" + addresses);

        InetAddress ipv4 = InetAddress.getByName("127.0.0.1");
        InetAddress ipv6 = InetAddress.getByName("::1");

        require(ipv4 instanceof Inet4Address,
                "IPv4 literal parsed incorrectly");
        require(ipv6 instanceof Inet6Address,
                "IPv6 literal parsed incorrectly");

        System.out.println(
                "IPv4 literal type: " + family(ipv4));
        System.out.println(
                "IPv6 literal type: " + family(ipv6));

        InetAddress[] options =
                InetAddress.getAllByName("localhost");
        require(options.length > 0,
                "localhost not resolved");

        StringJoiner sequence = new StringJoiner(",");
        boolean seenIpv4 = false;
        boolean seenIpv6 = false;

        for (InetAddress address : options) {
            sequence.add(family(address));
            seenIpv4 |= address instanceof Inet4Address;
            seenIpv6 |= address instanceof Inet6Address;
        }

        System.out.println("localhost order: " + sequence);
        System.out.println("localhost has IPv4: " + seenIpv4);
        System.out.println("localhost has IPv6: " + seenIpv6);
        System.out.println("getByName(localhost): " +
                family(InetAddress.getByName("localhost")));

        connectToLoopback(ipv4);
        System.out.println(
                "Explicit IPv4 loopback TCP: PASS");

        if ("true".equalsIgnoreCase(stack)) {
            System.out.println(
                    "Explicit IPv6 loopback TCP: NOT_TESTED " +
                    "(IPv4 stack requested)");
        } else {
            try {
                connectToLoopback(ipv6);
                System.out.println(
                        "Explicit IPv6 loopback TCP: PASS");
            } catch (IOException |
                     UnsupportedOperationException ex) {
                System.out.println(
                        "Explicit IPv6 loopback TCP: UNAVAILABLE");
            }
        }

        System.out.println(
                "Network test used only local loopback");
    }
}
~~~

### Compilation

Use **JDK 17 or later**:

~~~bash
javac --release 17 -encoding UTF-8 IpFamilyPreferenceDemo.java
~~~

### Running Four Separate JVMs

~~~bash
# 1. Default (no property passed).
java -cp . IpFamilyPreferenceDemo

# 2. Request IPv6 preference in resolution results.
java "-Djava.net.preferIPv6Addresses=true" -cp . IpFamilyPreferenceDemo

# 3. Follow the OS resolver order.
java "-Djava.net.preferIPv6Addresses=system" -cp . IpFamilyPreferenceDemo

# 4. Force IPv4-only stack; simultaneously try requesting IPv6 preference.
java "-Djava.net.preferIPv4Stack=true" "-Djava.net.preferIPv6Addresses=true" -cp . IpFamilyPreferenceDemo
~~~

**Why spawn four new processes?** Because the two properties are read once by the JDK at startup; using separate java commands ensures we do not rely on mid-run System.setProperty changes.

### Actual Test Output on the Test Machine

The program was compiled with **javac --release 17** and ran successfully with **OpenJDK 24.0.2 on Windows with IPv4 + IPv6 loopback**. The section below records the exact observed lines; **this is not an invariant stdout template** across all OSes.

**Run 1 — No flags passed:**

~~~text
preferIPv4Stack=(unset)
preferIPv6Addresses=(unset)
IPv4 literal type: IPv4
IPv6 literal type: IPv6
localhost order: IPv4,IPv6
localhost has IPv4: true
localhost has IPv6: true
getByName(localhost): IPv4
Explicit IPv4 loopback TCP: PASS
Explicit IPv6 loopback TCP: PASS
Network test used only local loopback
~~~

**Run 2 — preferIPv6Addresses=true:**

~~~text
preferIPv4Stack=(unset)
preferIPv6Addresses=true
IPv4 literal type: IPv4
IPv6 literal type: IPv6
localhost order: IPv6,IPv4
localhost has IPv4: true
localhost has IPv6: true
getByName(localhost): IPv6
Explicit IPv4 loopback TCP: PASS
Explicit IPv6 loopback TCP: PASS
Network test used only local loopback
~~~

**Run 3 — preferIPv6Addresses=system:**

~~~text
preferIPv4Stack=(unset)
preferIPv6Addresses=system
IPv4 literal type: IPv4
IPv6 literal type: IPv6
localhost order: IPv6,IPv4
localhost has IPv4: true
localhost has IPv6: true
getByName(localhost): IPv6
Explicit IPv4 loopback TCP: PASS
Explicit IPv6 loopback TCP: PASS
Network test used only local loopback
~~~

**Run 4 — preferIPv4Stack=true with preferIPv6Addresses=true:**

~~~text
preferIPv4Stack=true
preferIPv6Addresses=true
IPv4 literal type: IPv4
IPv6 literal type: IPv6
localhost order: IPv4
localhost has IPv4: true
localhost has IPv6: false
getByName(localhost): IPv4
Explicit IPv4 loopback TCP: PASS
Explicit IPv6 loopback TCP: NOT_TESTED (IPv4 stack requested)
Network test used only local loopback
~~~

### How to Correctly Interpret the Four Runs

- In Run 1, the test JVM preferred **IPv4** for localhost when no flags were passed. IPv6 sockets **still worked**, so **IPv4-first does not mean IPv6-disabled**.
- In Run 2, localhost has IPv6 first and getByName picks the IPv6 address; both loopback literals still connect when specified explicitly.
- In Run 3, the OS resolver in the test environment returned **IPv6 first**. Another machine may return IPv4 first or only one family; do not copy this order as a fixed rule for **system**.
- In Run 4, even with preferIPv6Addresses=true, the JVM was configured for an **IPv4-only socket stack**. The test saw localhost only having IPv4 in resolution results, yet **InetAddress.getByName("::1") still created an Inet6Address object**. The program intentionally skipped IPv6 connection when the property requested the IPv4 stack.
- Across all four runs, **explicit IPv4 TCP** succeeded because the test bound an IPv4 loopback listener. That **does not prove** the machine can reach the IPv4 Internet or any external server.

**Environment-dependent output:** in an IPv4-only container, **localhost has IPv6** may be false and **IPv6 loopback TCP** may be UNAVAILABLE; with a different hosts file or resolver, localhost order/availability changes. The goal of the test is to **observe, explain, and assert actual conditions**, not force the environment into a fixed network configuration.

### Why Does the Demo Use Both InetAddress and Socket?

**InetAddress** shows lookup/order and candidate families. **Socket.connect** verifies the ability to establish an actual TCP connection. Both are needed: if you only print InetAddress.getAllByName, you do not know whether the server is listening or where routes go; if you only connect to an IPv4 literal, you do not test hostname preference policies.

## 9. How Does Address Preference Affect HttpClient, TLS, and Proxies?

### 9.1. HTTP Client with a Dual-Family Hostname

A URL like **https://api.example.com/v1** still uses the **hostname api.example.com**. The HTTP client can resolve the name, choose an IPv4/IPv6 destination, open TCP, perform the TLS handshake, and send the HTTP request. However, how the client implements **which address to try, fallback order, connection pooling, and retries** depends on the API/implementation and JDK version.

**Do not claim every HttpClient in Java 17 uses the same Happy Eyeballs strategy**; to know what actually happens, observe connections, timeouts, and logs on the exact runtime.

Whether using **java.net.http.HttpClient**, URLConnection, or Socket, check the current capabilities of each stack. Simply changing system properties is not a complete IPv6 migration plan.

### 9.2. HTTPS Certificates Still Verify the Hostname

If DNS for **api.example.com** points to **192.0.2.20** and **2001:db8::20**, connecting TCP to either IP **does not change the origin name**. With HTTPS, the certificate must be verified to have a matching SAN for **api.example.com** and a valid trust chain.

Do not change the URL from a hostname to an IPv4 literal or IPv6 literal just to avoid DNS issues and then **disable hostname verification**. If the URL truly uses **https://[2001:db8::20]/**, the certificate needs an **iPAddress SAN** matching the target IP, not another dNSName SAN by default. For IPv6 in a URI, remember the **square brackets** around the host literal.

### 9.3. A Proxy Can Change Where DNS Occurs

When going through an **HTTP/SOCKS proxy**, the Java client may establish a TCP connection to the **proxy's** address, while the proxy performs the step of selecting the origin destination. Therefore, the **JVM client's** preference property may primarily affect **the proxy's address**, rather than directly determining IPv4/IPv6 to the origin.

For example, an HTTP CONNECT request may ask the proxy to open a tunnel to **api.example.com:443**; how the proxy resolves the hostname, picks A/AAAA, and routes is the **proxy's policy**. Do not read getAllByName("api.example.com") in the client and claim the proxy is using the first candidate.

**Use your organization's mandatory proxy**, and do not disable the proxy to "fix IPv6". When diagnosing, separate client→proxy from proxy→origin.

### 9.4. Connection Pooling and Stale Results

An HTTP client may **reuse a TCP/TLS connection** created before a DNS record change. In that case, a new request **does not need to re-select an address**. If you change JVM flags, you must **start a new process**; when changing DNS or network routes, check caching/pooling/lifecycle before concluding a change had no effect.

### 9.5. Dual-Stack Does Not Guarantee IPv6 Outperforms IPv4

IPv6 routes can be better or worse depending on the network. Setting preferIPv6Addresses=true may make requests faster on a good IPv6 network, or slower on a network that advertises IPv6 but blackholes packets. **Do not use a single throughput/latency measurement** to conclude that all IPv6 is faster than IPv4 or vice versa.

Measure **lookup duration, first connection attempt, actual remote IP, TLS handshake, fallback delay, and response time** per family, comparing on the same network/host/deadline.

## 10. Troubleshooting Workflow for an IPv4/IPv6 Issue in Java

### Step 1 — Pin Down the JVM and Actual Startup Flags

Record:

- **java -version**, JDK vendor, and runtime.
- Whether **java.net.preferIPv4Stack** is set and its value at startup.
- **java.net.preferIPv6Addresses** false/true/system.
- Container, namespace, OS, VPN/proxy, and network policy.
- The DNS hostname and port the application actually uses.

**Do not look only in source code:** flags can be passed from the JVM launcher, service manager, container JAVA_TOOL_OPTIONS, or deployment configuration. Record the effective values in the actual running process.

### Step 2 — Distinguish DNS Errors from Connection Errors

| Error or observation | Next analysis |
| --- | --- |
| **UnknownHostException** | Name service/hosts/DNS/cache returned no usable address |
| **InetAddress.getAllByName has only IPv4** | Check A/AAAA, IPv4Stack flag, resolver/hosts/OS |
| **getAllByName has IPv6 first** | Indicates candidate order only, not socket connectivity |
| **ConnectException: Connection refused** | Route exists, but endpoint is not listening/is refusing |
| **SocketTimeoutException in connect** | Network path, firewall, blackhole, timeout, wrong address |
| **NoRouteToHostException** | Route or OS policy does not allow reaching the destination |
| **BindException when binding IPv6** | Socket/OS/port/address unavailable or v6only configuration |
| **SSLHandshakeException after TCP connect** | TLS certificate/hostname/protocol, not the same as IP selection failure |
| **HTTP 502/504 via proxy** | Must inspect proxy→origin, not just Java client→proxy |

A successful DNS lookup **does not guarantee a successful TCP connection**; a successful TCP connection also **does not guarantee valid TLS identity verification**. Classify by layer to avoid switching to IPv4-only for every HTTP/HTTPS error.

### Step 3 — See Which Addresses Java Receives

Run **IpFamilyPreferenceDemo** on the actual machine or container. It prints **localhost** for safety/offline operation; when diagnosing a real host, a similar tool can call **InetAddress.getAllByName(target)** with an authorized hostname and log the family/order, while **never logging sensitive data**.

If using nslookup, dig, Resolve-DnsName, or getent, note: those commands may use a **different resolver path than Java**, or display raw records in a different order than the JVM applied. Compare A/AAAA, local hosts, VPN DNS, and Java lookup side by side.

### Step 4 — Check the Listener and Network Route

A service might bind only **0.0.0.0** or **127.0.0.1**, while the client prefers **::1**. Check the actual bound port and family; if dual-stack is desired, test two separate connections to both IPv4 and IPv6.

At the OS layer, check routes, interfaces, firewall, policy tables, NAT64/DNS64, and IPv6 link-local scope. Do not just see an IPv6 address on an interface and declare the application has IPv6 Internet access.

### Step 5 — Measure Client Fallback and Proxy Behavior

- Record the actual remote address/port from Socket or HTTP client telemetry.
- If using a proxy, determine whether Java connects to the proxy over IPv4 or IPv6; check how the proxy selects the origin.
- Measure connect timeout and overall deadline. If the client tries multiple IPs sequentially, delays can accumulate.
- Observe connection reuse and caching, and test with a fresh JVM after changing flags.

### Step 6 — Fix the Root Cause

| Root cause | Fix approach | What to avoid |
| --- | --- | --- |
| Broken IPv6 route | Fix route/firewall/interface, test dual-stack | Permanently disabling IPv6 across the JVM without analysis |
| Hostname AAAA points to wrong server | Fix DNS AAAA/traffic routing and TTL | Just forcing preferIPv4Stack to mask the bug |
| Legacy app only accepts IPv4 literals | Update code to support Inet6Address | Casting to Inet4Address after getByName |
| Client has slow fallback | Set deadlines, try reasonable candidates, use client with clear strategy | Hanging indefinitely on each IP |
| Server only listens on IPv4 | Bind/listen on IPv6 when service needs it, check v6only | Thinking preferIPv6Addresses will fix the server listener |
| Proxy does not support IPv6 | Fix proxy route/policy | Bypassing mandatory proxy |
| Wrong TLS certificate SAN | Fix certificate/trust/hostname | Disabling hostname verification |
| Stale DNS cache | Check resolver/cache TTL, managed restart | Disabling DNS cache for every request |
| IPv6-only cluster | Enable IPv6 sockets and appropriate services | Forcing preferIPv4Stack=true |

## 11. Common Mistakes

### Mistake 1 — Confusing Preference with Requirement

**preferIPv6Addresses=true** means preferring IPv6 **when both are present**; it is not a mandatory check requiring an IPv6 target address or a command disabling IPv4. If you need a specific connection to IPv6, choose an **Inet6Address** or a suitably designed hostname/route, and verify the actual socket.

### Mistake 2 — Confusing IPv4Stack with IPv4-First

**preferIPv4Stack=true** affects socket type/IPv6 capability; **preferIPv6Addresses=false** primarily affects address ordering. An application that is **IPv4-first while IPv6 still works** is completely normal.

### Mistake 3 — Changing Properties Mid-Run

System.setProperty(...) in main is not a reliable way to handle these two **startup-only** flags. Each time you measure a different configuration, launch **a new Java process** with -D placed before the class name.

### Mistake 4 — Printing the First Address and Claiming the Network Used It

**getAllByName** gives candidates, not a log of wire traffic. An HTTP client may pick another address, fall back, reuse a connection, or go through a proxy. Inspect the actual socket's remote/local address or telemetry.

### Mistake 5 — Treating IPv6 Localhost and IPv4 Localhost as One

**127.0.0.1 != ::1**. A listener bound only to 127.0.0.1 is not guaranteed to accept ::1. To test dual-stack, test each family explicitly and do not depend on a single OS's localhost ordering.

### Mistake 6 — Assuming Parsing an IPv6 Literal Means IPv6 Is Enabled

InetAddress.getByName("::1") can create an Inet6Address object even when IPv6 sockets are forbidden or the OS has no IPv6 route. Only an **actual connect** evaluates communication capability.

### Mistake 7 — Fixing HTTPS Issues by Connecting Directly to an IP and Disabling TLS Verification

DNS address family and TLS peer identity are two separate layers. An IP address may be reachable while the certificate is invalid for the origin DNS. You must preserve hostname verification and the truststore.

### Mistake 8 — Trusting Dual-Stack Server Config Without Testing

**:: wildcard bind** can depend on IPV6_V6ONLY. Confirm the listener for both IPv4 and IPv6 with two independent connections; do not infer it solely from a configuration line.

### Mistake 9 — Hardcoding One Family in Library Code

A shared networking module should not always create **Inet4Address**, unless the business contract strictly requires it. Use InetAddress, URI, and family-neutral APIs where possible, and log/troubleshoot family-specific cases when needed.

### Mistake 10 — Using IPv4 Preference as a Security Policy

A service that checks "only block 127.0.0.1" can miss **::1**, IPv4-mapped IPv6, ULA, link-local, and alternative address representations. **Both IPv4 and IPv6 must be evaluated** in allowlists/denylists and SSRF defenses.

## 12. IPv4/IPv6 Security in Network Services

### 12.1. Do Not Use IP Version as Access Control

IPv4/IPv6 are addressing and packet-delivery mechanisms; **they do not authenticate users**. An internal service bound to **0.0.0.0** or **::** can become unexpectedly reachable if the firewall permits it. Preferring IPv4 or IPv6 does not replace ACLs, authentication, or TLS.

### 12.2. SSRF Can Exploit Different IP Representations

A server accepting user-supplied URLs can be vulnerable to SSRF if it only blacklists **127.0.0.1** while allowing **[::1]**, IPv4-mapped addresses, link-local, private ranges, hostname rebinding, or IPv6 ULA. Therefore, URL/destination validation must:

1. Parse the URI and scheme using a standard parser.
2. Resolve **all candidates** that the application could actually use, not just the first address.
3. Define allowed IP ranges for **both IPv4 and IPv6**, including mapped/translation scenarios.
4. Re-apply the policy after **redirects** and, when needed, after fresh DNS resolution.
5. Combine with egress firewall/network policy to reduce impact if app logic is flawed.
6. Never disable hostname verification when using HTTPS over a selected IP.

**Changing system preferences is not an SSRF defense**; an attacker can exploit multiple representations, proxies, or DNS changes if the policy is incomplete.

### 12.3. Observability Must Not Leak Data

When logging addresses from a Socket, avoid recording auth tokens, full URLs containing passwords, cookies, and session IDs. IP addresses can also be sensitive data depending on context; maintain appropriate log retention and access controls.

### 12.4. Source Addresses Can Change

The OS may select different IPv6 source addresses depending on interface, scope, and privacy address policies. A changing source IP does not automatically indicate a different user, nor should source IP be used as the sole authentication method.

## 13. Deployment Checklist and Exercises

### Checklist When Changing IPv4/IPv6 Preference

- Confirm the **JDK vendor/version** and system properties at **startup**.
- Distinguish **preferIPv4Stack** (socket capability) from **preferIPv6Addresses** (address preference).
- Inspect A/AAAA records, hosts file, and **InetAddress.getAllByName** in the actual environment.
- Test IPv4 and IPv6 listeners using literal addresses if permitted.
- Observe actual remote IP, source address, connect duration, and error reason.
- Account for OS routes, firewall, container namespace, VPN, proxy, and NAT64/DNS64.
- Check fallback/Happy Eyeballs behavior for the specific client API and version.
- Check DNS cache, TTL, and connection reuse before drawing conclusions.
- Preserve TLS certificate/hostname verification and security policies.
- Test in IPv4-only, IPv6-only, and dual-stack environments if the application requires it.
- Have timeouts, an overall deadline, and a rollback plan when changing JVM flags.
- Do not treat a successful localhost test as confirmation of Internet routing/availability.

### Exercise A — Changing Localhost Order

Run the demo with no flags, true, and system; record the address arrays. Explain why **system** might not match true on another machine. Do not hardcode an expected order across all systems.

### Exercise B — IPv4Stack and IPv6 Loopback

Run preferIPv4Stack=true combined with preferIPv6Addresses=true. Why is the IPv6 literal still parsed while the IPv6 connection is not attempted? Distinguish **address object** from **native socket capability**.

### Exercise C — Server Bound to One Family

Create a TCP ServerSocket bound only to **127.0.0.1** and try connecting with **::1** using a short timeout. Compare with a listener bound only to **::1**. Do not use a fixed port already in use by another system service.

### Exercise D — Hostname with Multiple IPs

In a test environment with DNS/hosts you manage, configure A and AAAA for the same hostname. Use **getAllByName** to record the order under each JVM startup mode. Verify which destination is actually reachable and whether the client falls back.

### Exercise E — DNS Cache

Modify a record in an isolated environment and measure **InetAddress** in an existing JVM and a fresh JVM. Identify the roles of the OS resolver and Java cache policy. Do not modify DNS outside your administrative authority.

### Exercise F — Proxy Versus Direct

Set up an authorized test HTTP proxy and distinguish the **remote IP of Java→proxy** from the **remote IP of proxy→origin**. Why is getAllByName(origin) in Java not necessarily the list of addresses the proxy used?

### Exercise G — HTTPS with Hostname and Literal

Test an internal HTTPS endpoint with a valid certificate for its hostname. After changing IPv4/IPv6 preferences, hostname verification must still be performed. If accessing by IP literal, the certificate needs a matching SAN; trust-all must not be used.

### Exercise H — Dual-Stack and Connection Source

Record **socket.getInetAddress()** alongside **socket.getLocalAddress()**. Explain how remote family differs from source IP/interface selection. Use loopback before testing real hosts.

## 14. Self-Check Questions

**Question 1.** How do java.net.preferIPv4Stack and java.net.preferIPv6Addresses differ?  
**Answer:** The first selects an IPv4-only socket stack; the second affects the IPv4/IPv6 priority order when resolving a hostname that has both.

**Question 2.** By default, does Java 17 prefer IPv4 or IPv6 addresses?  
**Answer:** According to Java 17 Networking Properties, **preferIPv6Addresses=false**, so IPv4 is preferred when both are present for backward compatibility.

**Question 3.** Does preferIPv6Addresses=true disable IPv4?  
**Answer:** No. It prefers IPv6, but IPv4 can still be selected/used depending on candidates and client behavior.

**Question 4.** Can preferIPv4Stack=true make an IPv6-only host unreachable?  
**Answer:** Yes. An IPv4-only socket stack cannot connect to an IPv6-only peer using standard IPv6 sockets.

**Question 5.** What is the system value used for?  
**Answer:** It preserves the address order from the system-wide resolver/OS, without forcing a specific family first.

**Question 6.** Can you change the flag values with System.setProperty after the JVM is running and re-measure?  
**Answer:** Not reliably; the two flags are checked once at startup. Launch a new JVM with -D.

**Question 7.** Does InetAddress.getAllByName return active TCP connections?  
**Answer:** No; it returns candidates from the name service. Connectability must be tested with Socket or an appropriate client.

**Question 8.** Why might getByName return IPv6 first while HTTP still uses IPv4?  
**Answer:** The client may fall back, use a proxy, reuse an existing connection, or have its own connection strategy.

**Question 9.** Does a machine having an AAAA DNS record mean IPv6 Internet is working?  
**Answer:** No. Corresponding OS interfaces, routes, firewalls, and server listeners are required.

**Question 10.** Are IPv4 loopback and IPv6 loopback the same?  
**Answer:** No. 127.0.0.1 and ::1 are two different addresses/address families.

**Question 11.** Does binding :: on a server guarantee it accepts IPv4?  
**Answer:** Not guaranteed. It depends on the OS and implementation's dual-stack/IPV6_V6ONLY policy.

**Question 12.** Why did ::1 still parse into an Inet6Address when preferIPv4Stack=true was set in the example?  
**Answer:** Parsing an IP literal and native IPv6 socket capability are two separate things.

**Question 13.** How does the DNS cache affect behavior?  
**Answer:** InetAddress caches positive/negative results, so record changes may not be seen immediately by an existing JVM.

**Question 14.** Should -Dnetworkaddress.cache.ttl=0 be used as the standard way to disable caching?  
**Answer:** Not by default; it is a security property and must be configured according to JDK docs/security policy after evaluating the consequences.

**Question 15.** Why can choosing IPv6 first increase latency on a network that blackholes IPv6?  
**Answer:** The client may wait for an IPv6 address to time out before trying IPv4, depending on how it connects; appropriate deadlines/fallback are needed.

**Question 16.** Is Happy Eyeballs automatically guaranteed just by setting preferIPv6Addresses=true?  
**Answer:** No. The flag only changes preference, whereas Happy Eyeballs is a separate connection strategy.

**Question 17.** When using a proxy, who chooses A/AAAA for the origin?  
**Answer:** Potentially the proxy, depending on the proxy/tunnel type; the Java client may only connect directly to the proxy.

**Question 18.** When using HTTPS, can hostname verification be disabled to connect via an IPv6 literal?  
**Answer:** No. The certificate must be verified for the DNS origin or a matching IP SAN according to the actual URL.

**Question 19.** Why is blacklisting only 127.0.0.1 insufficient against SSRF?  
**Answer:** There are also ::1, mapped IPv6, ULA, link-local, private IPv4 ranges, redirects, and DNS rebinding.

**Question 20.** How do you check the selected family after Socket.connect succeeds?  
**Answer:** Inspect Socket.getInetAddress() for remote, getLocalAddress() for local, and verify against actual behavior.

**Question 21.** Does running the demo successfully on localhost prove dual-stack Internet routing?  
**Answer:** No. It only verifies loopback networking/current configuration on the test machine.

**Question 22.** Why should you compare both getAllByName and the socket remote address?  
**Answer:** One gives the candidate list, while the other gives the destination of the actual established connection.

## Conclusion

IPv4/IPv6 preference in Java is a coordination of **name resolution, address ordering, socket stack, OS routing, and client connection strategy**. On Java 17, **java.net.preferIPv4Stack=true** makes the JVM prefer IPv4-only sockets; **java.net.preferIPv6Addresses=false/true/system** changes the IPv4/IPv6 order when both exist, or preserves the OS resolver order.

Do not equate a **preferred address** with an **address guaranteed to connect**. Use **InetAddress.getAllByName** to inspect candidates, **Socket.getInetAddress/getLocalAddress** to inspect the specific connection, and check DNS, caching, proxy, firewall, TLS, and client fallback. When an application needs dual-stack, prioritize designing and observing support for both families rather than forcing a flag to mask infrastructure issues.

### Official References

- [Java SE 17 — Networking Properties](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/doc-files/net-properties.html): java.net.preferIPv4Stack, java.net.preferIPv6Addresses, and startup-only behavior.
- [Java SE 17 — Java Networking](https://docs.oracle.com/en/java/javase/17/core/java-networking.html): IPv4/IPv6 protocol properties, proxy-related properties.
- [Java SE 17 — InetAddress](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/InetAddress.html): getByName, getAllByName, IP literals, and name-service caching.
- [Java SE 17 — Inet4Address](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Inet4Address.html): IPv4 family.
- [Java SE 17 — Inet6Address](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Inet6Address.html): IPv6, scope IDs, and zone identifiers.
- [Java SE 17 — NetworkInterface](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/NetworkInterface.html): interface addresses and metadata.
- [Java SE 17 — Socket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html): connect timeout and remote/local addresses.
- [Java SE 17 — ServerSocket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ServerSocket.html): bind IP/port and listener.
- [Java SE 17 — InetSocketAddress](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/InetSocketAddress.html): endpoint address and resolution behavior.
- [RFC 6724 — Default Address Selection for IPv6](https://www.rfc-editor.org/rfc/rfc6724.html): source/destination address selection.
- [RFC 8305 — Happy Eyeballs Version 2](https://www.rfc-editor.org/rfc/rfc8305.html): sorting and trying candidates to reduce delay.
- [RFC 3986 — URI Syntax](https://www.rfc-editor.org/rfc/rfc3986.html): IPv6 literals in URIs.
