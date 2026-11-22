# Reading Networking API Contracts by JDK Version and Distinguishing Platform-Dependent Behavior

When working with Java Networking, having the same method name on two machines **does not mean every result will be identical**. The API contract defines what you can rely on; the JDK implementation, operating system, network configuration, and runtime environment determine many observable details. This lesson guides you on reading documentation for the exact JDK version, identifying binding wording, and turning unguaranteed behaviors into defensive code and appropriate tests.

## 1. Three Layers to Separate When Reading a Network Behavior

| Layer | Where to look | What can be concluded? |
| --- | --- | --- |
| **API contract / specification** | Javadoc of the exact Java SE/JDK version: class, method, parameter, return value, exception, and note descriptions | What the API guarantees, input constraints, error conditions, and post-call state |
| **JDK implementation** | Implementation Note/Requirements, release notes, JEPs, JDK vendor documentation, and runtime options | Implementation mechanisms, optimizations, and changes across JDK/vendor/build; only treat as guaranteed when the contract explicitly states so |
| **Platform + environment** | Operating system, TCP/IP stack, DNS/hosts, firewall, container, IPv4/IPv6, process permissions, proxy, and network devices | Actual addresses, interfaces, ports, timings, permissions, protocol selection, and errors on the running machine |

For example, `new ServerSocket(0)` has a contract requiring the system to select a local port. The **specific port number** varies between runs; it cannot be inferred from the Javadoc. Similarly, `InetAddress.getLoopbackAddress()` returns a loopback address, but tests should not be hardcoded to expect the exact string `127.0.0.1`: the system may choose an IPv6 form.

Three levels of wording should also be distinguished:

- **“Returns”, “throws”, “must”, and explicitly stated conditions**: the basis for assertions about the contract.
- **“May”, “typically”, “best effort”, “implementation-specific”, “platform-dependent”**: indicate what can vary; do not turn common examples into absolute guarantees.
- **“API Note”**: usage guidance; **“Implementation Requirements”**: requirements for the implementation; **“Implementation Note”**: details about how it is implemented. When there are differences, read each section according to its exact role.

Do not extrapolate a single run into a specification. One result is *evidence of that environment*, not automatically a promise for every environment.

## 2. Choose the Right Documentation Version Before Concluding

First, identify the **JDK used to compile**, the **JDK actually running the program**, and the **minimum Java version supported by the product**. These three values can differ, especially in IDEs, CI, Docker, and production.

~~~bash
java -version
javac -version
java -XshowSettings:properties -version
~~~

On systems with multiple JDKs, verify the actual executable path and the IDE/container runtime configuration. In Java, `Runtime.version().feature()` reports the runtime feature version; `System.getProperty("java.vendor")` and `System.getProperty("os.name")` help record the environment. They do not replace identifying the specific security update/build.

Examples of **versioned** documentation:

| API/document | JDK 17 | JDK 21 |
| --- | --- | --- |
| `java.net.InetAddress` | [Javadoc 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/InetAddress.html) | [Javadoc 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/InetAddress.html) |
| `java.net.ServerSocket` | [Javadoc 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ServerSocket.html) | [Javadoc 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/ServerSocket.html) |
| `java.net.Socket` | [Javadoc 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html) | [Javadoc 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/Socket.html) |
| `java.nio.channels.SocketChannel` | [Javadoc 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html) | [Javadoc 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/SocketChannel.html) |

Process for reading a method: (1) check the class name, module, signature, and `Since`; (2) read the description in *Method Detail*, not just *Method Summary*; (3) note `Parameters`, `Returns`, and `Throws`; (4) carefully read *API Note*, *Implementation Requirements/Note*, deprecated status, and related links; (5) compare those exact sections between the **two target JDKs**, then check the release notes if differences appear. `Since: 16` only states that the API was introduced in Java 16; it does **not** guarantee that every operating system and every configuration supports that feature.

When compiling on a newer JDK to run on Java 17, use `javac --release 17` to verify Java 17 API compatibility and generate corresponding bytecode. This flag **does not simulate** DNS, TCP stack, permissions, TLS algorithms, or OS differences at runtime; you still need to run tests on the target JDK and platform.

## 3. Typical Examples: What Is the Contract, and What Is a Variable?

### 3.1. Domain Name Resolution: `InetAddress`

`InetAddress.getAllByName(host)` relies on the name resolution mechanism provided by the runtime and the system. The count, order, and type of IPv4/IPv6 addresses can change depending on DNS, hosts file, VPN, address policies, and JDK configuration. A hostname can have multiple addresses; do not pick the first element assuming it is always IPv4 or the “primary” server. If resolution fails, handle `UnknownHostException` according to context, without turning a transient failure into a permanent conclusion.

`InetAddress.isReachable(timeout)` is a **best effort** check. The documentation states that ICMP may be blocked by permissions or firewalls and the implementation may try another mechanism, such as TCP Echo port 7. Therefore, `false` **does not prove** that the host's HTTPS service or application port is down; `true` also does not prove that the application API is healthy. To evaluate a service, perform a health check on the right protocol/endpoint with its own timeout.

DNS caching is a separate layer. `networkaddress.cache.ttl` and `networkaddress.cache.negative.ttl` are **Java security properties**, not ordinary system properties that can be assumed configurable via `-Dnetworkaddress.cache.ttl=...`. Default policies and re-resolution behavior must be checked against the documentation of the running JDK; changing the configuration also does not mean clearing already cached results. See [Networking Properties, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/doc-files/net-properties.html).

### 3.2. Port Binding, Backlog, and Timeout: `ServerSocket` / `Socket`

`new ServerSocket(0, backlog, bindAddress)` requests binding to the specified address and asks the system to allocate an ephemeral port; read the assigned port using `getLocalPort()`. The number `0` is **not** the actual TCP port for clients to connect to. With `bindAddress = null`, the server can accept connections on suitable local addresses of the system; when doing local-only experiments, bind to `InetAddress.getLoopbackAddress()`.

`backlog` is the **requested queue length**, not a guarantee to “accept exactly N concurrent connections”. The Javadoc allows the operating system/implementation to cap or ignore the parameter; backlog also does not equate to the number of requests the application can process. Do not turn `backlog = 8` into an assertion that the ninth connection will definitely be rejected.

`Socket.setSoTimeout(2000)` sets the timeout for **blocking read** operations on the input stream once the option takes effect; it does **not** automatically bound `connect` time and is not a deadline for the entire request. `Socket.connect(endpoint, timeout)` has a separate timeout for the connection step; a timeout of `0` is interpreted as infinite wait per the respective API. If a read times out, `SocketTimeoutException` is thrown and the socket remains valid per the contract, though the application must still decide whether to reuse that connection according to its own protocol. Wall-clock observed time can exceed the nominal threshold due to scheduling and system overhead; do not treat absolute millisecond measurements as an API guarantee.

### 3.3. Socket Options: Feature Support vs. Effective Value

`StandardSocketOptions` lists standard options, but the existence of a constant does **not** mean every socket type and every platform accepts that option. With `SocketChannel` / `NetworkChannel`, query `supportedOptions()` before calling `setOption(...)`; the contract may throw `UnsupportedOperationException` if unsupported, `IllegalArgumentException` if the value is invalid, or `IOException` due to a system error. Some options such as buffer sizes are subject to kernel limits/adjustments; check back via `getOption(...)` when you need to observe the effective value.

Do not use one machine's defaults to infer universal defaults: `SO_REUSEADDR`, `SO_RCVBUF`, `SO_SNDBUF`, `TCP_NODELAY`, multicast/broadcast behavior, and extended options have different scopes of applicability across TCP, UDP, Unix-domain sockets, operating systems, and JDK versions. Always read the **Socket options** section for the exact channel type and exact version.

### 3.4. Network Interfaces, Addresses, and Configuration Changes

`NetworkInterface.getNetworkInterfaces()` / `networkInterfaces()` reflects the machine's network configuration at the time of retrieval. Names such as `eth0`, `en0`, interface indices, NIC counts, and addresses bound to NICs are all environment data; container networks, VPNs, or hot-plugging can change them during runtime. Recent JDK documentation also notes that interface objects may be a **snapshot**, requiring re-retrieval for a fresh view. Do not treat interface indices or ordering as durable IDs.

`InetAddress.getLoopbackAddress().isLoopbackAddress()` is a reasonable invariant to assert; `getLoopbackAddress().getHostAddress().equals("127.0.0.1")` hardcodes the address representation, making it less portable.

### 3.5. HTTP Client, Proxy, and TLS

`HttpClient.version()` in `java.net.http` returns the **preferred HTTP version** in the client configuration, without guaranteeing that every response will use HTTP/2. Proxies, servers, and negotiation conditions can cause the actual request to use HTTP/1.1; if you need to know the outcome, inspect `HttpResponse.version()` on the response. Similarly, proxy configuration, trust stores, certificates, and supported TLS protocols can vary between runtimes and environments; distinguish *desired* configuration from *negotiated* state.

Note: `java.net.http.HttpClient` is a standardized API since Java 11; however, you must not infer from “API presence” that all providers, proxies, or protocol versions will produce the same connection outcome.

## 4. Reading Changes Across JDK Versions Using Concrete Scenarios

| Reference milestone | Feature/reading point | Correct conclusion |
| --- | --- | --- |
| **JDK 11** | Standard `java.net.http.HttpClient` in module `java.net.http` | Requires both the appropriate module/API and actual HTTP negotiation capability |
| **JDK 16** | `UnixDomainSocketAddress` and Unix-domain socket channels | API available since 16; runtime still depends on OS, OS version, filesystem type, and permissions |
| **JDK 18** | SPI `java.net.spi.InetAddressResolverProvider` (JEP 418) | Allows plugging in a resolver instead of the default path; code directly referencing this SPI is not Java 17 API-compatible |
| **JDK 21** | Virtual threads and interrupt descriptions for default `Socket` | When a virtual thread is interrupted during Javadoc-specified socket operations, the operation may close the socket and throw an exception; do not apply that rule to all versions or all custom implementations |

With Unix-domain sockets, `StandardProtocolFamily.UNIX`/`UnixDomainSocketAddress` uses a filesystem path instead of an IP:port pair. Do not assume absolute portability just because the code compiles: the OS or the location where the socket file is created may not support it; paths, permissions, and socket file cleanup also need consideration. [Javadoc UnixDomainSocketAddress 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/UnixDomainSocketAddress.html) states `Since: 16`; the JDK 16 release notes also document support limitations on certain Windows versions.

With the DNS provider SPI added in JDK 18, the difference is not just a new class name: the resolution path can be customized by the application/runtime. When comparing JDK 17 and JDK 21, do not assume every `InetAddress` call goes through the same resolver mechanism. See [JDK 18 release notes — JEP 418](https://www.oracle.com/java/technologies/javase/18-relnote-issues.html).

With virtual threads (JDK 21), read the **exact overloads** of `Socket.connect`, `getInputStream`, and the interrupt notes in Javadoc 21. Changes in interrupt semantics cannot be guessed merely from method signatures that already existed in JDK 17.

## 5. Two Java 17+ Programs to Verify Contract and Environment

### Example A — Assert Only What the API Truly Guarantees

File `NetContractProbe.java`:

~~~java
import java.io.IOException;
import java.net.InetAddress;
import java.net.ServerSocket;

public class NetContractProbe {
    public static void main(String[] args) throws IOException {
        InetAddress loopback = InetAddress.getLoopbackAddress();
        System.out.println("Loopback: " + loopback.isLoopbackAddress());

        try (ServerSocket server = new ServerSocket(0, 8, loopback)) {
            System.out.println("Bound: " + server.isBound());
            System.out.println("Loopback bind: "
                    + server.getInetAddress().isLoopbackAddress());
            System.out.println("Ephemeral port assigned: "
                    + (server.getLocalPort() > 0));
        }
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 NetContractProbe.java
java NetContractProbe
~~~

When the environment allows opening a local server socket, the exact stdout is:

~~~text
Loopback: true
Bound: true
Loopback bind: true
Ephemeral port assigned: true
~~~

The assertions use **properties**, not the assigned port or a specific IP string. The backlog parameter `8` is only a request passed to the implementation; the example does not falsely check that the OS will queue exactly 8 connections. If the machine/sandbox forbids binding sockets or resources are exhausted, the program may throw `IOException`; that indicates an unmet environment precondition, not a violation of the contract when binding succeeds. The `try-with-resources` block releases the socket even if an error occurs inside.

### Example B — Print Environment Facts Without Enforcing Fixed Stdout

File `NetEnvironmentProbe.java`:

~~~java
import java.net.InetAddress;
import java.net.StandardSocketOptions;
import java.nio.channels.SocketChannel;

public class NetEnvironmentProbe {
    public static void main(String[] args) throws Exception {
        String host = args.length == 0 ? "localhost" : args[0];

        System.out.println("JDK feature: " + Runtime.version().feature());
        System.out.println("Vendor: " + System.getProperty("java.vendor"));
        System.out.println("OS: " + System.getProperty("os.name"));

        for (InetAddress address : InetAddress.getAllByName(host)) {
            System.out.println(address.getClass().getSimpleName()
                    + ": " + address.getHostAddress());
        }

        try (SocketChannel channel = SocketChannel.open()) {
            boolean supported = channel.supportedOptions()
                    .contains(StandardSocketOptions.TCP_NODELAY);
            System.out.println("TCP_NODELAY supported: " + supported);

            if (supported) {
                channel.setOption(StandardSocketOptions.TCP_NODELAY, true);
                System.out.println("TCP_NODELAY configured: "
                        + channel.getOption(StandardSocketOptions.TCP_NODELAY));
            }
        }
    }
}
~~~

~~~bash
javac --release 17 NetEnvironmentProbe.java
java NetEnvironmentProbe localhost
java -Djava.net.preferIPv4Stack=true NetEnvironmentProbe localhost
java -Djava.net.preferIPv6Addresses=system NetEnvironmentProbe localhost
~~~

There is no single “standard stdout” for Example B: major version, vendor, OS, returned addresses, and supported options depend on the machine. `localhost` also depends on name resolution configuration; if it fails, the program may throw `UnknownHostException`. The `-D` commands demonstrate how to **experiment** with a different configuration, without promising that the address count or address order will definitely change. `java.net.preferIPv4Stack` and `java.net.preferIPv6Addresses` are checked at JVM startup, so start a new process when changing them; see [Networking Properties, Java 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/doc-files/net-properties.html).

For real-world errors, also log the exception type, target address/port (without logging credentials), timestamp, JDK build, proxy, and IPv4/IPv6 context so it can be reproduced. Do not catch every `Exception` and print “network unavailable”: `UnknownHostException`, `ConnectException`, `SocketTimeoutException`, and `UnsupportedOperationException` represent different situations.

## 6. Turning Contracts into Meaningful Tests

| What to verify | Good assertion | Fragile assertion |
| --- | --- | --- |
| Loopback | `isLoopbackAddress() == true` | IP string is always `127.0.0.1` |
| Ephemeral port bind succeeds | `isBound()` and `getLocalPort() > 0` | Assigned port is always a fixed number |
| DNS | Each result is a valid address; application tolerates multiple results/resolution errors | `getAllByName("localhost")[0]` is always IPv4 |
| Backlog | Server can bind and accept connections under defined test conditions | Queue always holds exactly N connections |
| Reachability | Check the actual application endpoint to know if the service is working | `isReachable(false)` implies the entire service is dead |
| Socket option | Check `supportedOptions()` and handle exceptions/effective values | Every OS supports every `StandardSocketOptions` |
| HTTP version | Check `HttpResponse.version()` after the request | `HttpClient.version() == HTTP_2` guarantees the response uses HTTP/2 |

Separate **unit tests of result-handling logic** from **integration tests over a real network**. Unit tests avoid OS assumptions; integration tests record the environment, keep finite timeouts, use test-controlled endpoints, and accept variations permitted by the API. When a feature is optional per OS/JDK, use a capability probe and choose a fallback path or mark the test case as not applicable; do not treat the absence of that feature as a business bug if the product does not promise to support it.

A minimal test matrix might include JDK 17 and 21 on the OSes the product actually supports, environments with and without IPv6, containers and bare-metal/regular machines, and different proxy/DNS configurations. Only include combinations in the matrix that fit the application's support scope; JDK patch levels and CI network policies should be recorded in the evidence.

## 7. Diagnostic Workflow When Two Machines Behave Differently

1. **Reproduce with a narrow question:** which method, which input, what was expected, what was observed? Record the exception class rather than just copying the message.
2. **Pin down versions:** save `java -version`, `javac -version`, vendor/build, OS, target `--release`, and the exact API documentation URL.
3. **Read the full contract:** cross-check `Parameters`, `Returns`, `Throws`, `Since`, and API/Implementation Notes; underline words like “may”, “best effort”, and “implementation-specific”.
4. **Classify claims:** what is guaranteed, what is merely an environment-dependent default, and what is implementation-specific; do not try to fix an allowed difference by hardcoding values.
5. **Measure at runtime:** IP family, resolver, network interfaces, proxy, supported socket options, timeouts, and negotiated protocol; do not assume implicit ordering or values.
6. **Design the handling:** set timeouts on the right operations, catch errors meaningfully, try alternative addresses when the connection strategy calls for it, manage resources, and retry only in a controlled manner.
7. **Re-verify:** test the API invariants on the target JDK/OS while logging platform variables to distinguish product bugs from environment characteristics.

Typical warning signs that you should stop and open the right Javadoc: “Java ping returned false so HTTP must fail”, “backlog is the concurrent client limit”, “enabling `SO_REUSEADDR` guarantees the port can be reused”, “preferring HTTP/2 means the response will be HTTP/2”, “the API has `Since` so every machine must support it”, or “compiling with `--release 17` makes Java 17 runtime behavior identical on Linux and Windows”. Every one of those conclusions goes beyond the API contract.

## 8. Self-Check Questions

**Scenario 1:** Java 17 on a laptop returns `127.0.0.1`, while Java 21 in a container returns `::1` for loopback. Is it necessarily a bug? **No.** Check loopback validity and IPv4/IPv6 policy; only force IPv4 when the product has a specific compatibility requirement.

**Scenario 2:** `isReachable(1000)` returns `false`, but a GET `/health` to the server succeeds. Is there a contract contradiction? **No.** A best-effort network probe differs from the service's protocol/port.

**Scenario 3:** On a newer JDK, `javac --release 17` reports that `InetAddressResolverProvider` cannot be found. Why? **Because the SPI was introduced in JDK 18**; the Java 17 target API does not have that class.

**Scenario 4:** Configuring `backlog = 8` results in the OS handling pending connections differently than expected. Is the contract violated? **You cannot conclude that**: the documentation allows the implementation to cap or ignore the requested backlog.

**Scenario 5:** `HttpClient.version()` returns `HTTP_2`, but `HttpResponse.version()` is `HTTP_1_1`. Is that necessarily wrong? **No.** The client property only indicates the preferred version; the result depends on the server, proxy, and negotiation.

## Primary Sources to Consult

- [Java SE 17 — InetAddress](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/InetAddress.html), [Networking Properties](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/doc-files/net-properties.html): name resolution, `isReachable`, and DNS caching.
- [Java SE 17 — ServerSocket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ServerSocket.html), [Java SE 21 — Socket](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/Socket.html): binding, backlog, timeouts, exceptions, and interrupts.
- [Java SE 21 — NetworkChannel](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/NetworkChannel.html), [SocketChannel](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/SocketChannel.html): socket options, channel lifecycle, and support limits.
- [Java SE 21 — HttpClient](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpClient.html), [UnixDomainSocketAddress](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/UnixDomainSocketAddress.html): preferred protocol configuration and Unix socket capabilities.
- [JDK 18 release notes — JEP 418](https://www.oracle.com/java/technologies/javase/18-relnote-issues.html), [Java SE 25 — Networking Properties](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/doc-files/net-properties.html): API evolution and version-dependent configuration.

**Usage principle:** choose **the exact documentation for the runtime/target**, assert only what the contract truly guarantees, and verify OS/JDK/network-determined details directly in the deployment environment.
