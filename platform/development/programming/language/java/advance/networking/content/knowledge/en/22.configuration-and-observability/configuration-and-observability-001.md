# Networking properties: process-wide scope and when properties are read

## Learning Objectives

A Java networking program can be affected by configurations such as `java.net.preferIPv4Stack`, `http.proxyHost`, `java.net.useSystemProxies`, `http.keepAlive`, or `networkaddress.cache.ttl`. However, **not all properties have the same scope, way of being set, or time of taking effect**.

There are three questions to answer *before changing configuration*:

1. **Who owns the value?** A **JVM process** via system properties, a **security properties** configuration, a JDK configuration file, an `HttpClient`/`ProxySelector` object, or the operating system itself?
2. **When is the value read?** Once at **JVM startup/initialization**, each time a network operation is performed, when a **class/component is first initialized**, or when **a client object is constructed**?
3. **Who is affected by changing the value?** All threads and libraries **within the same JVM**, only a single HTTP client/connection if configured per instance, or only **JVM processes launched later** when changing `-D`?

A common mistake is seeing `System.getProperty("java.net.preferIPv4Stack")` change from `false` to `true` after the application starts, and then assuming that existing sockets or subsequent sockets will immediately switch their IPv4/IPv6 policy. The JDK 17 documentation specifies that this is a **property read once at JVM startup**; changing **a string in the properties map** is not equivalent to reinitializing the networking stack.

This lesson has four Java 17+ programs that have been compiled/run for verification:

- **`StartupPropertyVisibilityDemo`:** starts **two separate JVMs** with `-Djava.net.preferIPv4Stack=false` and `true`; observes an IPv6 loopback socket and proves that changing `System.setProperty` at runtime does not change the test result.
- **`ProxyPropertyScopeDemo`:** two threads see the same process-wide system property; the default `ProxySelector` looks up `http.proxyHost`/`http.nonProxyHosts` for new requests.
- **`LegacyAgentTimingDemo`:** `http.agent` of the HTTP URL protocol handler keeps the initially read value, even though `System.setProperty` changes after the first request.
- **`SecurityPropertyScopeDemo`:** compares `System.setProperty` with `Security.setProperty` for DNS negative-cache TTL, without needing any real DNS lookup.

All examples only use loopback or construct configuration objects; they do not connect to public services, modify JDK files, or change the machine's network configuration. Each example is **a standalone program**, distinct from the code snippets explicitly marked as illustrative in the theory sections.

## 1. Distinguishing process, thread, object, OS, and JDK installation

A typical Java process has one JVM with multiple threads and multiple libraries:

```text
Operating system / container / VM
  │
  ├── JVM Process A   (java -Dhttp.proxyHost=proxy-a ...)
  │     │
  │     ├── JVM System Properties (one shared store within the process)
  │     │     ├── http.proxyHost
  │     │     ├── java.net.useSystemProxies
  │     │     └── java.net.preferIPv4Stack
  │     │
  │     ├── Java Security Properties (a DIFFERENT store)
  │     │     ├── networkaddress.cache.ttl
  │     │     └── networkaddress.cache.negative.ttl
  │     │
  │     ├── Thread 1: URLConnection / HttpClient / Socket
  │     ├── Thread 2: URLConnection / HttpClient / Socket
  │     └── Shared defaults: ProxySelector, Authenticator, SSL settings...
  │
  └── JVM Process B   (java -Dhttp.proxyHost=proxy-b ...)
        └── Has its own properties store, does not automatically receive setProperty from A
```

**`System.getProperties()` is shared among threads within the same JVM.** It is not the case that “each request keeps an independent set of global properties”. When thread A calls `System.setProperty("http.proxyHost","...")`, thread B can read the new value. This is a source of **coupling, race conditions, and behavioral changes in unrelated libraries**.

Conversely, two Java processes running on the same machine do not automatically share mutations of `System.setProperty`. If process A changes `http.proxyHost`, process B does not automatically change. To apply a new startup configuration to process B, `-D` must be passed when launching B or a configuration mechanism read by process B must be used.

### Scope model

| Source/mechanism | Typical scope | Example | Effect when changed |
|---|---|---|---|
| JVM system property | **Process-wide** | `System.setProperty("http.proxyHost",...)` | Threads/features that re-read the property may see the new value |
| JVM launch flag | Only the newly launched **JVM process** | `java -Djava.net.preferIPv4Stack=true ...` | Takes effect when components read at startup; does not change other JVMs |
| JDK security property | JVM-wide but **separate security store** | `Security.getProperty("networkaddress.cache.ttl")` | May be cached by components; not the `System` map |
| JDK install configuration | File in the JDK installation, applies to processes using that installation depending on mechanism | `conf/net.properties`, `conf/security/java.security` | May only affect new launches; does not directly modify a running JVM |
| Network object property | One object/instance | `HttpURLConnection.setConnectTimeout`, `HttpClient.Builder.proxy(...)` | Does not actively modify global system properties |
| OS network configuration | Machine, namespace, container, or user per OS | DNS resolver, route, system proxy | Java may read/snapshot/cache it; does not update every object immediately by default |
| Environment variable | Process environment provided by the launcher | `System.getenv("HTTPS_PROXY")` | **Not identical** to `System.getProperty("https.proxyHost")` |

A configuration called “global” is usually only global **within one JVM**, not global across all programs on the machine. Do not interpret `System.setProperty` as a command that changes Windows/Linux/macOS proxy settings or modifies values in `$JAVA_HOME/conf/net.properties` on disk.

## 2. When values are read: static, dynamic, initialized, or cached?

The **Java 17 Networking Properties** documentation states the foundational rule:

- Some properties **are checked only once at JVM startup** and should use `-D` of the `java` command.
- Some properties are **dynamic** and can be changed using `System.setProperty(...)`.
- **If a property's description has no specific note about when it is read**, that documentation page states the value is checked on each use. **This rule applies within the scope of that document's list and contract**, not as a promise for every internal `jdk.*` property or every library.

### Three types of behavior to recognize

| Type | When does the component read it? | Effect of `System.setProperty` at runtime | Stable strategy |
|---|---|---|---|
| **Startup-only** | Once during the JVM startup phase | The map string may change, but the network mechanism does not necessarily update | Set `-D` before the process starts, then restart |
| **Dynamic lookup** | Each time the component looks it up, if the contract says so | Subsequent lookups may see the new value | Be careful of process-wide scope; avoid toggling across multiple threads |
| **Component initialization/cached** | When the class/object/subsystem first initializes or snapshots | Changing the map after init may **not** affect existing components | Set early, check Javadoc/component policy, test on the exact JDK |

**A “dynamic” property does not automatically update an in-flight request**: if a proxy for a request has already been selected, changing the property while the socket is active does not make the socket switch to another proxy. Dynamic usually means **the next proxy selection/operation** may observe the new value, depending on the implementation.

### “At startup” is not synonymous with “when main begins”

`main(String[] args)` is the point the programmer sees after the Java launcher has started the runtime. Socket classes, network preferences, or system services may already have been initialized before or during the startup phase. Therefore, **calling `System.setProperty` on the first line of `main` is not strictly equivalent to `-D`** for startup-only properties. If the Java documentation requires startup, place it on the **JVM launch command**, rather than betting on class loading order.

### How to correctly interpret “System.getProperty() has changed”

`System.getProperty("java.net.preferIPv4Stack")` only returns a **String currently in the system properties map** (or `null`). It does **not** query whether the native networking stack is running in IPv4 or IPv6 mode. Changing the map does not prove native state changed; you must test socket behavior separately and check against the contract.

## 3. Important networking properties table according to Java 17

The table below groups properties **strictly according to the Java SE 17 documentation**, without merging them into a single uniform update mechanism.

| Property | Default value per JDK 17 docs | Scope/group | When read? |
|---|---|---|---|
| `java.net.preferIPv4Stack` | `false` | java.net IPv4/IPv6 | **Startup-only** |
| `java.net.preferIPv6Addresses` | `false` | java.net DNS address ordering preference | **Startup-only** |
| `java.net.useSystemProxies` | `false` | Default OS proxy integration | **Startup-only** |
| `http.proxyHost` | Not set | Legacy HTTP/default proxy selection | **Lookup on use** per proxy group |
| `http.proxyPort` | `80` | HTTP proxy | **Lookup on use** per proxy group |
| `http.nonProxyHosts` | `localhost\|127.*\|[::1]` | HTTP/HTTPS proxy exclusions | **Lookup on use** per proxy group |
| `https.proxyHost` | Not set | HTTPS proxy | **Lookup on use** per proxy group |
| `https.proxyPort` | `443` | HTTPS proxy | **Lookup on use** per proxy group |
| `socksProxyHost` | Not set | SOCKS proxy | **Lookup on use** per proxy group |
| `socksProxyPort` | `1080` | SOCKS proxy | **Lookup on use** per proxy group |
| `http.agent` | User-Agent `Java/<version>` | Legacy HTTP URL protocol handler | **Startup-only** |
| `http.keepAlive` | `true` | Legacy URL handler persistent connections | **Startup-only** |
| `http.maxConnections` | `5` | Legacy URL handler: max idle keep-alive connections per destination | **Startup-only** |
| `http.maxRedirects` | `20` | Legacy URL handler redirect limit | **Startup-only** |
| `jdk.http.maxHeaderSize` | `393216` bytes | Header limit the client is prepared to receive | **Startup-only** in the URL handler list |
| `networkaddress.cache.ttl` | Depends on JDK/security config | **Security property**, DNS positive cache | Not a standard `-D` configuration; see `Security.getProperty` |
| `networkaddress.cache.negative.ttl` | `10` seconds in JDK 17 page | **Security property**, DNS negative cache | Not a standard `-D` configuration; may be cached by resolver |
| `jdk.httpclient.connectionPoolSize` | `0` in JDK 17 guide | **JDK-specific java.net.http client** | Check module/version docs; not identical to `http.maxConnections` |

**Note when upgrading JDK:** the list and defaults of JDK-specific properties can change between Java 17, 21, and update releases. In production, check the documentation for the **exact JDK runtime in use**. This table is for Java 17 training purposes and does not grant permission to assume every property exists/remains valid forever.

### Why not conclude `http.maxConnections=5` means an HTTP client has at most five sockets?

`http.maxConnections` is the limit on **idle keep-alive connections per destination** of the **HTTP URL protocol handler** in JDK 17, not “max 5 active connections” across the entire JVM. The modern `java.net.http.HttpClient` has different properties/configuration, such as `jdk.httpclient.connectionPoolSize`. Do not use the same key for two HTTP implementations when no corresponding contract exists.

### Why is `http.keepAlive` not equal to TCP `SO_KEEPALIVE`?

`http.keepAlive` controls the **reuse of HTTP persistent connections** in the legacy HTTP handler. `Socket.setKeepAlive(true)` is a TCP socket option to enable keepalive probes at the OS layer. These are two different behaviors: one relates to sending multiple HTTP requests over a connection, while the other monitors an idle transport.

## 4. IPv4/IPv6: two properties read exactly once

According to Java 17:

- `java.net.preferIPv4Stack=false` is the default. When IPv6 is available, Java typically uses IPv6-capable sockets that can serve IPv4/IPv6 according to OS behavior.
- `java.net.preferIPv4Stack=true` requests an IPv4-only stack, so sockets created by this stack **cannot communicate with IPv6-only hosts**.
- `java.net.preferIPv6Addresses=false` by default prefers IPv4 addresses when a host has both A/AAAA records to preserve historical compatibility. `true` prefers IPv6 when possible; `system` preserves the address order returned by the OS.
- **Both are checked once at JVM startup**. Do not use them as a switch to change addressing between two running requests.

### These two properties do not completely overlap

`preferIPv4Stack` is the **socket/stack type**. `preferIPv6Addresses` is the **preference order** when selecting addresses if resolution returns multiple addresses. For example, setting `preferIPv6Addresses=true` while still using an IPv4-only stack is a configuration with conflicting expectations; it does not automatically ensure you can connect to an IPv6-only host.

A host `localhost` may resolve to `127.0.0.1` and/or `::1` depending on the OS/JDK. **Do not take the order of `InetAddress.getAllByName("localhost")` on this machine as a universal guarantee**. On an environment without IPv6, IPv6 tests may legitimately fail.

### Proper operation

```bash
# Use -D before the class name; launch a new JVM.
java -Djava.net.preferIPv4Stack=true MyNetworkingApp

# Another JVM, at a different launch time, with a different policy:
java -Djava.net.preferIPv6Addresses=system MyNetworkingApp
```

`MyNetworkingApp` is an illustrative name, not an existing class in this lesson. You need to configure the container/systemd/IDE/Java service wrapper launcher so these flags are present **right when the Java process is created**. Do not rely on “calling setProperty(...) after the application has started is enough”.

## 5. Java 17+: comparing two JVMs and mutating properties at runtime

The first example is run **twice in two separate Java processes**. It attempts to bind a server socket on IPv6 loopback `::1`, then changes `java.net.preferIPv4Stack` using `System.setProperty(...,"true")`, retries, and prints the results.

To avoid DNS dependencies, the program uses the **IPv6 literal `::1`**; it does not access the Internet. On an OS without IPv6, both bind attempts may fail; the program intentionally records this as a boolean rather than blaming the network.

**File `StartupPropertyVisibilityDemo.java`:**

```java
import java.net.*;

public class StartupPropertyVisibilityDemo {
    public static void main(String[] args) throws Exception {
        String initial = System.getProperty("java.net.preferIPv4Stack", "false");
        boolean initialSocketIPv6Support;
        try (ServerSocket v6 = new ServerSocket()) {
            v6.bind(new InetSocketAddress(InetAddress.getByName("::1"), 0));
            initialSocketIPv6Support = true;
        } catch (Exception noIpv6) {
            initialSocketIPv6Support = false;
        }
        System.setProperty("java.net.preferIPv4Stack", "true");
        boolean afterSocketIPv6Support;
        try (ServerSocket v6 = new ServerSocket()) {
            v6.bind(new InetSocketAddress(InetAddress.getByName("::1"), 0));
            afterSocketIPv6Support = true;
        } catch (Exception noIpv6) {
            afterSocketIPv6Support = false;
        }
        System.out.println("Initial property: " + initial);
        System.out.println("System property after mutation: " +
                System.getProperty("java.net.preferIPv4Stack"));
        System.out.println("IPv6 loopback socket supported before: "
                + initialSocketIPv6Support);
        System.out.println("IPv6 loopback socket supported after: "
                + afterSocketIPv6Support);
        System.out.println("Socket capability changed: "
                + (initialSocketIPv6Support != afterSocketIPv6Support));
    }
}
```

Compile:

```bash
javac --release 17 -encoding UTF-8 StartupPropertyVisibilityDemo.java
```

Run 1, creating a JVM with `preferIPv4Stack=false`:

```bash
java -Djava.net.preferIPv4Stack=false StartupPropertyVisibilityDemo
```

**Stdout observed on an IPv6-capable Windows machine:**

```text
Initial property: false
System property after mutation: true
IPv6 loopback socket supported before: true
IPv6 loopback socket supported after: true
Socket capability changed: false
```

Run 2, creating a **new JVM**, with `preferIPv4Stack=true`:

```bash
java -Djava.net.preferIPv4Stack=true StartupPropertyVisibilityDemo
```

**Stdout observed on the same machine:**

```text
Initial property: true
System property after mutation: true
IPv6 loopback socket supported before: false
IPv6 loopback socket supported after: false
Socket capability changed: false
```

### Reading the results correctly

1. `System.setProperty(...)` changed the **property map string** to `true` in both processes; this is printed on line 2.
2. The process started with `preferIPv4Stack=false` could bind `::1`; changing the map to true mid-program did not cause the subsequent socket test to lose IPv6 bind capability.
3. The process started with `preferIPv4Stack=true` could not bind an IPv6 socket in the test environment, even though it also had the property string true after mutation.
4. `Socket capability changed: false` demonstrates that **in this test** changing `System.setProperty` at runtime did not change IPv6 bind capability.
5. The data is an **observation on a specific runtime/OS**; a machine lacking IPv6 may print false before and after regardless of `-D`. The startup-only rule is a **JDK 17 documentation contract**, not inferred by looking at a single line of output.
6. The program intentionally catches a broad `Exception` in the socket capability check to avoid OS dependence; production code should not swallow exceptions like that during real diagnostics. In a real system, log the exception class/message and callsite to know why bind failed.
7. It is not recommended to change `java.net.preferIPv4Stack` in a production JVM with many active sockets; changing the string does not “reset” sockets already created.

**Takeaway:** choose the network stack when launching the JVM, and measure behavior rather than looking solely at `System.getProperty`.

## 6. Proxy properties: process-wide scope, per-request lookup

Proxies are a useful example because `http.proxyHost`, `http.proxyPort`, and `http.nonProxyHosts` belong to the group that can be looked up again by the **default proxy selector** when creating new requests.

According to the Java 17 list:

- `http.proxyHost` and `http.proxyPort` configure the HTTP proxy; default port is 80 if not provided.
- `https.proxyHost` and `https.proxyPort` configure the HTTPS proxy; default port is 443. The HTTPS protocol handler uses **`http.nonProxyHosts`** for exclusions.
- `http.nonProxyHosts` uses patterns separated by the pipe character `|`; the wildcard `*` can match domains/hosts as described. Default loopback exclusions are `localhost|127.*|[::1]`.
- `socksProxyHost`/`socksProxyPort` configure the SOCKS proxy when supported, though applications can also use their own proxy or a custom `ProxySelector`.
- `java.net.useSystemProxies=true` allows `java.net` to use system proxy settings on some OSes. **This property itself is read once at startup**; do not toggle it between requests expecting OS proxy integration to change immediately.
- Directly specified proxy properties (such as `http.proxyHost`) **take precedence over OS proxy settings** according to JDK 17 documentation when both are configured.

### Startup pattern

```bash
java -Djava.net.useSystemProxies=false \
     -Dhttp.proxyHost=proxy.example.test \
     -Dhttp.proxyPort=8080 \
     -Dhttp.nonProxyHosts="localhost|127.*|*.internal" \
     MyApp
```

The command above illustrates Unix shell style; `MyApp` and `proxy.example.test` **are not verified endpoints**. If using PowerShell, put flags on **one line** or use the proper PowerShell line continuation character (backtick); POSIX-style trailing backslashes do not continue commands in PowerShell.

### A “dynamic” property does not automatically change an already-connected HttpURLConnection

Once `URL.openConnection()` is called and connected, the proxy route has been chosen at a point in time. Changing `http.proxyHost` afterward does **not** migrate an existing TCP connection to another proxy. The next request using the default selector may see the new value, unless overridden by a custom proxy selector, per-connection proxy, or client snapshot policy.

### Proxy exceptions are a security issue

A configuration of `http.nonProxyHosts="*"` can cause **all hosts to go direct**, bypassing the corporate proxy and breaking egress/audit policy. Conversely, missing internal exclusions can route traffic to an unintended proxy. Do not use overly broad wildcards; verify DNS, internal network zones, and organizational policies.

## 7. Java 17+: two threads see the same proxy property, selector updates

This example **does not open a TCP connection to any proxy**. It uses `ProxySelector.getDefault().select(uri)` to inspect which proxy the default selector intends to use; the proxy IP `192.0.2.10` belongs to the TEST-NET-1 documentation-only block, so there is no risk of accidentally calling a real service from the demo.

We run with `-Djava.net.useSystemProxies=false` so it does not pull proxy policy from the OS UI; inside the process, we set the system properties `http.proxyHost`, `http.proxyPort`, and `http.nonProxyHosts` in turn.

**File `ProxyPropertyScopeDemo.java`:**

```java
import java.net.*;
import java.util.List;
import java.util.concurrent.*;

public class ProxyPropertyScopeDemo {
    private static String decide(String url) {
        List<Proxy> proxies = ProxySelector.getDefault().select(URI.create(url));
        if (proxies.isEmpty()) return "EMPTY";
        Proxy proxy = proxies.get(0);
        if (proxy.type() == Proxy.Type.DIRECT) return "DIRECT";
        InetSocketAddress address = (InetSocketAddress) proxy.address();
        return proxy.type() + ":" + address.getHostString()
                + ":" + address.getPort();
    }
    public static void main(String[] args) throws Exception {
        if (!"false".equals(System.getProperty("java.net.useSystemProxies")))
            throw new IllegalArgumentException("Use -Djava.net.useSystemProxies=false");
        String oldHost = System.getProperty("http.proxyHost");
        String oldPort = System.getProperty("http.proxyPort");
        String oldExceptions = System.getProperty("http.nonProxyHosts");
        ExecutorService worker = Executors.newSingleThreadExecutor();
        try {
            System.setProperty("http.proxyHost", "192.0.2.10");
            System.setProperty("http.proxyPort", "8181");
            System.setProperty("http.nonProxyHosts", "*.internal|localhost|127.*");
            System.out.println("Main thread property: " +
                    System.getProperty("http.proxyHost"));
            System.out.println("Worker thread property: " + worker.submit(
                    () -> System.getProperty("http.proxyHost")).get());
            System.out.println("External URI selection: " +
                    decide("http://public.example.test/resource"));
            System.out.println("Internal URI selection: " +
                    decide("http://database.internal/resource"));
            System.out.println("Loopback URI selection: " +
                    decide("http://127.0.0.1/resource"));
        } finally {
            worker.shutdownNow();
            restore("http.proxyHost", oldHost);
            restore("http.proxyPort", oldPort);
            restore("http.nonProxyHosts", oldExceptions);
        }
    }
    private static void restore(String key, String original) {
        if (original == null) System.clearProperty(key);
        else System.setProperty(key, original);
    }
}
```

Run:

```bash
javac --release 17 -encoding UTF-8 ProxyPropertyScopeDemo.java
java -Djava.net.useSystemProxies=false ProxyPropertyScopeDemo
```

**Verified stdout:**

```text
Main thread property: 192.0.2.10
Worker thread property: 192.0.2.10
External URI selection: HTTP:192.0.2.10:8181
Internal URI selection: DIRECT
Loopback URI selection: DIRECT
```

### Why is this demo notable?

1. The main thread and the `ExecutorService` thread see the same `http.proxyHost`, because it is a **process-wide system property**, not a thread-local property.
2. `ProxySelector.getDefault().select` returns the HTTP proxy for a URI outside the exclusions list, based on the new value set at runtime.
3. `*.internal` and `127.*` cause internal/loopback URIs to be selected as `DIRECT`. An already existing `ProxySelector` object can still look up system properties when selecting a new proxy.
4. This is the **default proxy selector of Java 17**. If the application has called `ProxySelector.setDefault(customSelector)` or `HttpClient.Builder.proxy(custom)`, the result depends on that specific implementation/policy; do not assume all clients see the same global configuration.
5. Selecting a proxy only returns an **intended routing decision**; it does not verify that proxy `192.0.2.10:8181` is running. The demo **performs no HTTP request or TCP connect**.
6. `finally` restores the three old system properties. However, that only makes the demo safer in the test process: when concurrent requests occur while properties are being changed, they **can still observe temporary values**. In multi-threaded production, avoid the save–set–restore pattern of global properties to configure a single request.

### A hard-to-find bug: tests running in parallel

In a JUnit suite running multiple tests concurrently, test A changes `http.proxyHost`; test B sends an HTTP request; both are in the **same JVM**. Test B may unexpectedly use A's mock proxy. Even if A restores the property in `finally`, the race may have already happened. Run tests that mutate global properties in **separate JVMs**, or use explicit per-client/per-request proxy config without mutating globals.

## 8. `java.net.useSystemProxies`: which one needs to be set from startup?

A very common misconception:

```java
// ANTI-PATTERN if you expect to enable system proxies immediately:
System.setProperty("java.net.useSystemProxies", "true");
```

JDK 17 explicitly states `java.net.useSystemProxies` **is read once at startup**. The statement above only changes the property string, not an API that “re-applies” all OS proxy configurations in a running JVM. If you want to use OS proxy defaults, set it at launcher time:

```bash
java -Djava.net.useSystemProxies=true MyApp
```

**Whereas `http.proxyHost` is usually looked up again**, as shown in section 7's demo. Both properties fall under the “proxy” topic but **have different read times**. Therefore, remembering “proxy configuration can be changed at runtime” is not enough; you must look at the **exact key**.

### Behavior when OS proxy changes

Even when `useSystemProxies=true` is enabled at startup, do not assume every OS setting change is reflected immediately for every JVM/connection. OS notifications, native integration, JVM proxy selector, PAC proxies, and caching can all affect this. Test on the exact JDK/OS and create a **new request** after the change; keeping an old connection does not mean the proxy route has changed.

## 9. HTTP URL protocol handler: properties fetched once

In the Java 17 Networking Properties documentation, the `Misc HTTP URL stream protocol handler properties` group includes:

- `http.agent`: provides User-Agent, with `Java/<version>` appended per the contract.
- `http.keepAlive`: default `true`; controls the ability to use persistent HTTP/1.1 connections.
- `http.maxConnections`: default `5`; the number of **idle connections per destination** that can be kept in cache when keep-alive is enabled.
- `http.keepAlive.time.server` and `http.keepAlive.time.proxy`: control the idle timeout fallback when the server/proxy does not provide a timeout; unit is seconds.
- `http.maxRedirects`: default `20`; number of redirects automatically followed for a protocol handler request.
- `http.auth.digest.validateServer`, `http.auth.digest.validateProxy`, `http.auth.digest.cnonceRepeat`: Digest authentication parameters.
- `http.auth.ntlm.domain`: domain configuration for NTLM.
- `jdk.http.maxHeaderSize`: response header section limit; default 393216 bytes in JDK 17.

**The JDK 17 documentation marks this group as checked once at startup**. If you plan to change `http.keepAlive` to debug connection reuse, set it via `-D` before launch and run a new JVM. Do not change it after the HTTP handler has already run and conclude the pool must clear immediately.

### What happens when only the Java String is changed?

For example:

```java
System.setProperty("http.keepAlive", "false");
```

Afterward, `System.getProperty("http.keepAlive")` may return `false`, but **that does not prove the handler has stopped using persistent connections** at runtime. The value for networking behavior is governed by the **startup-only** contract, not just the map. Moreover, a connection already in use cannot “turn back time” because of a mutable string.

### `http.agent` is the easiest example to measure

We can observe the `User-Agent` sent by Java's legacy HTTP URL handler on a **loopback server**. Configure `-Dhttp.agent=START` at launch; after the first request, call `System.setProperty("http.agent","CHANGED")`; the second request still sends **the same User-Agent determined earlier** in the test environment. No reliance on TLS/network firewalls or DNS is needed.

## 10. Java 17+: proving `http.agent` does not change with runtime mutation

The program opens a loopback HTTP server, receives two GET requests, and records the `User-Agent` header. After the first request, the client changes the system property `http.agent` from START to CHANGED, then sends the second request in the **same JVM**.

**File `LegacyAgentTimingDemo.java`:**

```java
import com.sun.net.httpserver.HttpServer;
import java.io.InputStream;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;

public class LegacyAgentTimingDemo {
    private static void get(URL url) throws Exception {
        HttpURLConnection c = (HttpURLConnection) url.openConnection();
        c.setConnectTimeout(2000);
        c.setReadTimeout(2000);
        try (InputStream body = c.getInputStream()) {
            body.readAllBytes();
        } finally {
            c.disconnect();
        }
    }
    public static void main(String[] args) throws Exception {
        if (!"START".equals(System.getProperty("http.agent")))
            throw new IllegalArgumentException("Run with -Dhttp.agent=START");
        HttpServer server = HttpServer.create(
                new InetSocketAddress(InetAddress.getByName("127.0.0.1"), 0), 0);
        List<String> seen = new ArrayList<>();
        server.createContext("/agent", exchange -> {
            try (exchange) {
                synchronized (seen) {
                    seen.add(exchange.getRequestHeaders().getFirst("User-Agent"));
                }
                byte[] bytes = "OK".getBytes(StandardCharsets.US_ASCII);
                exchange.sendResponseHeaders(200, bytes.length);
                try (var out = exchange.getResponseBody()) { out.write(bytes); }
            }
        });
        try {
            server.start();
            URL url = URI.create("http://127.0.0.1:" +
                    server.getAddress().getPort() + "/agent").toURL();
            get(url);
            System.setProperty("http.agent", "CHANGED");
            get(url);
            System.out.println("Property now: " + System.getProperty("http.agent"));
            System.out.println("First agent starts START: "
                    + seen.get(0).startsWith("START "));
            System.out.println("Second agent same as first: "
                    + seen.get(1).equals(seen.get(0)));
            System.out.println("Requests received: " + seen.size());
        } finally {
            server.stop(0);
        }
    }
}
```

Run in the directory containing the file with **JDK 17 or later**:

```bash
javac --release 17 -encoding UTF-8 LegacyAgentTimingDemo.java
java -Dhttp.agent=START LegacyAgentTimingDemo
```

**Verified compiled/run stdout:**

```text
Property now: CHANGED
First agent starts START: true
Second agent same as first: true
Requests received: 2
```

**Explanation:**

1. The `-Dhttp.agent=START` flag makes the property present **right when the JVM starts**.
2. The Java HTTP URL handler builds the User-Agent from the property read at initialization. The JDK may append `Java/<version>`, so the demo checks the START prefix rather than depending on the running version.
3. `System.setProperty` changes the property map to CHANGED, confirmed on the first output line.
4. The second request still carries the same User-Agent as the first request in the test environment. That illustrates **the startup/cached value differs from the string returned by System.getProperty**.
5. The demo uses `HttpURLConnection`, **not** the modern `java.net.http.HttpClient`. Do not treat this test as the User-Agent contract for every HTTP library (OkHttp, Apache HttpClient, Netty) or for the Java HTTP client module.
6. Recording the header on the server does not mean a new TCP connection is created for each request. HTTP keep-alive may reuse the socket, but that does not change the conclusion about User-Agent.
7. The program uses `127.0.0.1` and a dynamic port; it does not connect to the Internet. `seen` only has one entry added by the handler per request, and `main` reads it after receiving both responses.

**Conclusion:** changing a property string at runtime is not proof that a startup-only property has taken effect in a running handler.

## 11. DNS cache TTL is a **security property**, not a regular `-D` networking property

Two important keys:

- `networkaddress.cache.ttl`: duration (seconds) to cache **successful** name resolution results. Java 17 describes 0 = no caching, negative = cache forever, default depends on security manager/JDK implementation.
- `networkaddress.cache.negative.ttl`: duration to cache **failed** name resolution results. Java 17 docs state default 10 seconds; 0 = no caching, negative = cache forever.

**Note:** these are **Java Security properties** of the caching mechanism in `java.net.InetAddress`, **not standard system properties**. JDK 17 documentation explicitly states they **are not configured via `-D` or `System.setProperty`** in the standard way, but via the Java security property mechanism.

### Proper configuration for JDK 17

In a controlled JDK environment, configure security properties via the `$JAVA_HOME/conf/security/java.security` file or through a JDK-supported security mechanism. If an application needs to call `Security.setProperty` at runtime, you must check **when the cache/resolver was initialized** and the implementation documentation; being able to change the security property string does not by itself prove the DNS cache mechanism is using the new TTL.

```java
// Illustrative snippet; use in an early, controlled configuration program.
String current = java.security.Security.getProperty(
        "networkaddress.cache.negative.ttl");

// Unlike System.setProperty:
java.security.Security.setProperty(
        "networkaddress.cache.negative.ttl", "7");
```

**Hot-changing DNS TTL in a Java server actively serving traffic is discouraged.** A change can affect DNS lookups across the entire JVM, and old cached results may still remain, causing divergence between instances/threads. For a stable state, configure **before the resolver is used** and test on the exact JDK, then restart when needed.

### Do not confuse JVM DNS cache with DNS/OS resolver cache

A name can be cached at multiple layers: JVM `InetAddress`, OS resolver, DNS daemon, DNS server, proxy, or sidecar. `networkaddress.cache.ttl=0` in the JVM **does not clear** external caches. Conversely, an updated OS DNS record does not immediately switch already-open Java connections to the new IP.

### Mistake: “I set -Dnetworkaddress.cache.ttl=0 and it still caches”

Wrong configuration mechanism. `System.getProperty("networkaddress.cache.ttl")` may return `0` while `Security.getProperty(...)` still holds a different value. This is the first thing worth checking before blaming DNS.

## 12. Java 17+: distinguishing System property and Security property

The third example does not look up a hostname, so its result is independent of DNS, caches, and the Internet. It reads the initial security property, writes a **system property of the same name** using `System.setProperty(...,"123")`, checks whether `Security.getProperty` was affected, then writes the **security property** using `Security.setProperty(...,"7")` and reads both stores.

**File `SecurityPropertyScopeDemo.java`:**

```java
import java.security.Security;

public class SecurityPropertyScopeDemo {
    public static void main(String[] args) {
        String key = "networkaddress.cache.negative.ttl";
        String initialSystem = System.getProperty(key);
        String initialSecurity = Security.getProperty(key);
        try {
            System.setProperty(key, "123");
            System.out.println("System property: " + System.getProperty(key));
            System.out.println("Security unchanged by System.setProperty: "
                    + java.util.Objects.equals(initialSecurity,
                        Security.getProperty(key)));
            Security.setProperty(key, "7");
            System.out.println("Security property after Security.setProperty: "
                    + Security.getProperty(key));
            System.out.println("System property still: " + System.getProperty(key));
        } finally {
            if (initialSystem == null) System.clearProperty(key);
            else System.setProperty(key, initialSystem);
            if (initialSecurity != null) Security.setProperty(key, initialSecurity);
        }
    }
}
```

Run:

```bash
javac --release 17 -encoding UTF-8 SecurityPropertyScopeDemo.java
java SecurityPropertyScopeDemo
```

**Verified stdout:**

```text
System property: 123
Security unchanged by System.setProperty: true
Security property after Security.setProperty: 7
System property still: 123
```

### Substantive conclusions

- `System.setProperty` only modifies the system map; it does not modify the Security map entry of the same name.
- `Security.setProperty` modifies the security map; it does not automatically modify the System map.
- `Security.getProperty` returning 7 **does not prove** the resolver has updated its active TTL. A component may have already read the TTL earlier or kept cache entries under the old policy.
- The demo attempts to restore initial values in `finally`. **Do not run code that mutates security properties in a shared production JVM**, because other threads may observe the new value during the experiment.
- If `initialSecurity` is `null`, the demo has no `Security.clearProperty` API to delete the newly created entry; thus, full restoration to “unset” is not guaranteed within the demo process itself. This is another reason to **run in a separate JVM**, rather than embedding tests in a production app.
- The demo only proves **the two property stores are independent**; it does not test actual caching duration because DNS caches involve timing and environment-dependent OS resolvers.

## 13. The `conf/net.properties` file: not a file for every system property

In Java SE 17, the JDK provides a default network configuration file, typically located at:

```text
$JAVA_HOME/conf/net.properties
```

According to the Java 17 networking guide, this mechanism supports **proxy-related properties**. Do not assume you can put any `java.net.*` or `jdk.httpclient.*` key in there and expect the JVM to read it from the file. The `conf/net.properties` file is **a source of default values** for supported settings, not a live config service that automatically syncs to all processes.

### Precedence order to remember

- System properties explicitly specified via `-D` or `System.setProperty` per contract can **override default values from `conf/net.properties`** for supported proxy settings.
- `java.net.useSystemProxies=true` can pull settings from the OS on supported platforms; **directly declared proxy properties usually take precedence** over OS defaults.
- A custom `ProxySelector` or explicit `Proxy` per request/client can decide routing with different logic, not necessarily following system properties alone.
- `conf/security/java.security` is the **file for security properties**, not a copy of `conf/net.properties`.

### When editing JDK files

A running Java process typically does not automatically reload `conf/net.properties` after the file is edited. If you manage an installation, changing the file can affect **processes launched afterward**, without automatically changing running JVMs. Consider JDK upgrades, container images, read-only mounts, and configuration drift. For services with multiple instances, it is better to use startup flags/managed configuration per deployment rather than manually editing a shared JDK installation.

**The hands-on exercises do not modify any `conf/net.properties` or `java.security` files.** That avoids affecting other Java applications on the machine.

## 14. The new `java.net.http.HttpClient` and legacy `HttpURLConnection` do not share all configurations

An easy mistake to make is setting:

```bash
java -Dhttp.maxConnections=5 -Dhttp.keepAlive=false MyHttpApp
```

and assuming Java 17's `java.net.http.HttpClient` is strictly limited to **5 active connections** and does not pool. Per JDK 17, these are keys documented under the **HTTP URL stream protocol handler**, tied to legacy `HttpURLConnection`. The `java.net.http` module has its **own group of JDK-specific properties** and client-level configuration.

For example, the JDK 17 Java Networking documentation lists:

- `jdk.httpclient.connectionPoolSize`: limits the number of connections **in the HTTP/1.1 keep-alive cache** of the new client; default `0` means unlimited cache size per this property. It does not mean 0 active connections.
- `jdk.httpclient.keepalive.timeout`: number of seconds to keep an idle HTTP/1.1 connection per JDK 17 docs.
- `jdk.httpclient.HttpClient.log`: can enable logging for the Java HTTP client via the Java Logging API; consider headers/payloads/tokens.
- `jdk.httpclient.disableRetryConnect`, `jdk.httpclient.enableAllMethodRetry`: retry-related switches; use caution with non-idempotent methods.
- `jdk.httpclient.redirects.retrylimit`: attempt limit for redirects/retries per implementation.
- `jdk.httpclient.allowRestrictedHeaders`: for testing only per JDK warning; do not override restricted HTTP headers in production to “fix” protocol errors.

**Do not guess when each `jdk.httpclient.*` is read using the “every proxy property is dynamic” rule.** JDK-specific knobs may be read at class/client/runtime initialization, vary by version, and do not necessarily carry the same contract as the list in `java.base`. For resource-tuning/limit configurations, prefer **setting them at JVM startup** and verifying on the actual JDK release.

### Instance-based configuration is clearer

```java
// Illustrative snippet: not a standalone class.
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .proxy(ProxySelector.of(
                new InetSocketAddress("proxy.internal", 8080)))
        .build();
```

Requires imports `java.net.http.HttpClient`, `java.net.ProxySelector`, `java.net.InetSocketAddress`, and `java.time.Duration`. The endpoint `proxy.internal` is illustrative only. The builder configures a **specific client object**; there is no need for `System.setProperty("http.proxyHost",...)` affecting every library in the JVM.

However, **one HttpClient object can be used by multiple threads**. Per-client configuration is not synonymous with per-thread; if two requests need different proxy/TLS policies, you can create separately managed clients. Do not use global system property mutations to change network config for all modules.

### Choosing a specific proxy for a legacy URLConnection

```java
// Illustrative snippet: 'url' is a verified URL.
HttpURLConnection direct =
        (HttpURLConnection) url.openConnection(Proxy.NO_PROXY);
```

This creates a **DIRECT** connection via the API without changing `http.proxyHost` JVM-wide. However, direct access may violate corporate egress policy; use only with approval. `Proxy.NO_PROXY` is an object-level specification, not a toggle for OS proxies across the whole process.

## 15. System properties, environment variables, and Java security settings

A deployment may contain these types of configuration:

```text
Docker/Kubernetes env:
  HTTP_PROXY=http://proxy.example.test:8080
  HTTPS_PROXY=http://proxy.example.test:8443

JVM launch flags:
  -Dhttp.proxyHost=proxy.example.test
  -Dhttp.proxyPort=8080
  -Djava.net.useSystemProxies=false

Java security configuration:
  networkaddress.cache.negative.ttl=10
```

Do not treat them as **equivalent**. Java code `System.getenv("HTTP_PROXY")` reads the process environment; `System.getProperty("http.proxyHost")` reads the system property map; `Security.getProperty("networkaddress.cache.negative.ttl")` reads the security property map. The JDK does not guarantee that every library automatically translates `HTTP_PROXY` into `http.proxyHost`.

A framework or container entrypoint **may** copy env vars into `-D`, but that is framework/launcher logic, not a universal Java Networking default. When debugging, inspect **what arguments the JVM was actually started with**, not just the Docker Compose file.

### Warning about `JAVA_TOOL_OPTIONS`/`JDK_JAVA_OPTIONS`

Some Java deployment environments use environment options to inject JVM startup flags. If an app receives an unexpected proxy or IPv4-only mode, check both the Java command and how the launcher/IDE/container adds options. **Do not print secrets** contained in launch flags, configuration files, or system properties to public logs.

### Inspecting a running JVM

Java tools like `jcmd <pid> VM.system_properties` or `jcmd <pid> VM.command_line` can show a process's properties and launch arguments when you have permission to inspect it. **Warning:** output may contain secrets/passwords/tokens; use only in authorized environments with restricted log access and redaction. Those values also do not prove the runtime component applied a change if the property is startup-only.

## 16. Does mutation timing create a race?

Yes. A `System.setProperty` call updates a single key, but coordinated keys like `http.proxyHost` + `http.proxyPort` + `http.nonProxyHosts` **are not updated atomically as a single configuration**. In the gap between statements:

```text
Thread A (config updater)                 Thread B (request)
  setProperty(proxyHost="new")                │
        │                                      ├── reads proxyHost=new
        ├── setProperty(proxyPort="8181")      │
        │                                      └── reads proxyPort=OLD
        └── setProperty(nonProxyHosts=...)     │

Result: B may see a configuration mixed between old and new.
```

The `ProxyPropertyScopeDemo` experiment at least demonstrates that **the same property is visible across multiple threads**. In a system with many concurrent requests, changing multiple keys sequentially can make proxy routing inconsistent; do not rely on **each individual `setProperty` being thread-safe** to conclude that an entire group of properties is updated atomically.

### Per-request configuration and immutable config snapshot

A better pattern for applications:

1. At startup, parse env/flags/config files into an **immutable NetworkConfig**.
2. Validate host, port, timeout, TLS options, allowed proxies, and security policy.
3. Create the client object matching the config; register that object for shared use by modules/threads.
4. If hot reload is needed, create a **new client** with the new config snapshot, shift traffic in a controlled manner, and drain/close the old client per its API.
5. Do not mutate `System.setProperty` on every HTTP request to “temporarily pick a proxy” or “switch IPv6 mode for the current thread”.

### Does ThreadLocal help?

You cannot use `ThreadLocal` to automatically turn a system property into a thread-local one: `System.getProperty` still reads the JVM's shared map. To vary configuration per request, pass parameters via arguments/client instance/context, or use a per-client `ProxySelector` that knows how to read an appropriate context. Do not mutate global defaults while other threads are active.

## 17. Debugging scenario: map value changed but traffic stays the same

This is the most important scenario in this lesson:

```text
I called System.setProperty("java.net.preferIPv4Stack","true")
System.getProperty(...) returns "true"
But connections still use IPv6!
```

**Correct interpretation:** Java 17 documentation states that property is **startup-only**, so there is no reason to expect changing the system property string will reinitialize native sockets. Check the launch command, restart the process, and measure actual IPv4/IPv6 behavior.

Other scenarios:

| Symptom | Question to ask first | How to handle |
|---|---|---|
| Changed `java.net.useSystemProxies` at runtime but OS proxy does not apply | Is it a startup-only property? | Set `-D` at launch, restart, and check OS support |
| Changed `http.proxyHost` but new requests still go DIRECT | Does `http.nonProxyHosts` match? Is there a custom selector/client? | Check `ProxySelector` and the actual endpoint |
| Old requests still use the old proxy despite property change | Is the connection already established or client snapshotted? | Track lifecycle; do not switch sockets via map mutation |
| `System.getProperty(networkaddress.cache.ttl)` changed but DNS still caches | Was system used by mistake instead of security property? | Use `Security.getProperty`, configure early, check DNS cache |
| Legacy User-Agent did not change after `setProperty("http.agent",...)` | Is `http.agent` startup-only? | Set before JVM launch |
| Set `http.maxConnections=5` but new HttpClient has more connections | Does the property belong to the legacy handler? | Check `jdk.httpclient.connectionPoolSize` and the actual client module |
| `HTTP_PROXY` is set but Java does not use the proxy | Does the launcher/framework map env to Java properties? | Configure `-D` or an explicit ProxySelector |
| `System.getProperty("http.proxyHost")` changed mid-test | Is another module/test mutating globals? | Run tests isolated or configure per-client |
| `http.nonProxyHosts="*.internal"` does not exclude HTTPS from proxy | Are the exclusion property and evaluated hostname right? | JDK 17 HTTPS handler shares `http.nonProxyHosts`; check proxy policy |
| App running across multiple pods has different proxy behavior | Do all pods have identical JVM flags and JDK images? | Compare startup/config/version/OS/proxy and rollout |
| Edited `conf/net.properties` but old process did not change | Does the process reload the file? | Usually requires JVM restart; do not rely on file edits |
| Enabling HTTP client debug logging leaks headers | Are logger scope and secrets redaction in place? | Enable only in a controlled way, reduce logging detail |

### Step-by-step investigation procedure

1. Identify the **exact key name** and API group: `java.net`, legacy `HttpURLConnection`, `java.net.http`, `javax.net.ssl`, or Security.
2. Find the documentation for the **exact JDK release**, noting **startup-only/dynamic/component-cached**.
3. Record the **actual startup options** of the failing process, not just the current map values.
4. Check `System.getProperty` and where appropriate `Security.getProperty`; do not treat them as the same source.
5. Determine whether the `HttpClient/ProxySelector/Socket` object was created **before or after** the configuration change.
6. For proxies, instrument `ProxySelector.select(URI)` or appropriate HTTP tracing, rather than guessing routes from hostnames.
7. For IPv4/IPv6, observe local/remote socket addresses and OS capabilities, not just `localhost` DNS order.
8. For DNS, check the Java InetAddress cache, OS DNS, DNS TTL, and runtime policy; not just the DNS server record.
9. Try **starting a new JVM with `-D`** and running the corresponding measurement on the same JDK/OS.
10. If it is shared runtime config, eliminate races with per-client configuration or controlled reloads.

## 18. Distinguishing property testing from production system changes

The tests in this lesson are designed to be **safe in a separate test JVM**:

- Do not modify the OS proxy registry, DNS resolver, or routes.
- Do not edit `conf/net.properties`/`java.security` files.
- Do not connect to a “mock” proxy because `ProxySelector.select` only plans routing.
- Do not call `example.test` domains or IP `192.0.2.10` over the network; they are only inputs to describe routing.
- `LegacyAgentTimingDemo`'s HTTP server listens on **127.0.0.1** on a dynamic port.
- The DNS security-property test performs no DNS resolution.

**Do not copy experimental `System.setProperty` snippets into a multi-tenant application server**. These changes are global to threads in the current JVM and can affect unrelated libraries. If a library does not support per-instance config and needs different startup-only properties, the clean solution is to **split into different JVM processes**, not to try simulating thread-local global config.

### Configuration security advice

- Do not put proxy passwords in URLs, system properties, or debug logs if a better credential management API is available.
- `java.net.socks.password` and authentication configs can be secrets; if used, protect process arguments and diagnostic dumps.
- Do not weaken TLS verification just to test routing; proxy tunneling can have its own authentication and certificate constraints.
- `jdk.httpclient.allowRestrictedHeaders` is warned by the JDK as for testing; do not enable it in production to arbitrarily add `Host`, `Content-Length`, or `Connection`.
- When querying `System.getProperties()` for observability, only log an **allowlist of non-sensitive keys**, never dump all properties.
- When hot-reloading proxies, ensure you do not break allowlists, egress controls, or DNS pinning/trust boundaries.

## 19. Self-check questions

**Q1.** Does calling `System.setProperty("java.net.preferIPv4Stack","true")` right after app start guarantee switching socket mode to IPv4-only?  
**Answer:** No. It is startup-only per Java 17. Set `-D` before JVM launch.

**Q2.** Do threads in the same JVM each have an independent copy of `System.getProperties()`?  
**Answer:** No. They access a shared system property map, so mutations can affect other threads.

**Q3.** Process A calls `System.setProperty("http.proxyHost","X")`; does process B automatically use X?  
**Answer:** No. Two JVMs have separate system property maps, unless externally supplied the same configuration at launch.

**Q4.** Do `java.net.preferIPv4Stack` and `java.net.preferIPv6Addresses` serve the same purpose?  
**Answer:** No. One relates to an IPv4-only socket stack, while the other is the preference/order of IPv4/IPv6 addresses from name resolution.

**Q5.** Can `java.net.useSystemProxies` be reliably enabled with `System.setProperty` in the middle of an already-sent HTTP request?  
**Answer:** Do not rely on that. Java 17 marks this property as startup-only.

**Q6.** Can `http.proxyHost` affect new requests when changed at runtime?  
**Answer:** It can, with the default proxy selector/handler re-reading the property, as shown in the demo; it does not migrate open sockets.

**Q7.** Does `http.nonProxyHosts` use a comma or a pipe to separate patterns in JDK 17?  
**Answer:** A pipe `|`; the wildcard `*` is used to match hostnames.

**Q8.** Does an HTTPS request use `https.nonProxyHosts` instead of `http.nonProxyHosts` in the JDK 17 legacy handler?  
**Answer:** Not according to this documentation; the HTTPS URL handler uses `http.nonProxyHosts`.

**Q9.** Why not use `http.maxConnections` to guarantee a limit on all active connections of the new `HttpClient`?  
**Answer:** It describes the per-destination idle cache of the legacy URL handler, not a hard limit on active connections for the new client module.

**Q10.** `http.agent` was read at startup; does changing `System.setProperty` at runtime guarantee the legacy User-Agent changes immediately?  
**Answer:** No. The demo showed the header did not change even though the property map changed.

**Q11.** Does `networkaddress.cache.ttl` belong to `System.getProperties()` or Security properties?  
**Answer:** Per Java 17, it is a **security property**, read with `Security.getProperty`.

**Q12.** Is setting `-Dnetworkaddress.cache.negative.ttl=0` the official way to disable DNS negative caching?  
**Answer:** No. JDK 17 instructs using the security property mechanism, not system `-D`.

**Q13.** `Security.setProperty(key,"7")` and then `Security.getProperty` returns 7; are all DNS caches guaranteed to change TTL immediately?  
**Answer:** No. The mechanism using the property may have already cached/snapshotted it. Check the JDK implementation and lifecycle.

**Q14.** Does editing `$JAVA_HOME/conf/net.properties` automatically change an already running JVM?  
**Answer:** Do not assume so. It is a configuration file and usually requires restarting the JVM to load the new state.

**Q15.** Can you put any `java.net.*` property into `conf/net.properties` and expect Java 17 to use it?  
**Answer:** No. The Java 17 guide limits this file mechanism to supported proxy-related properties.

**Q16.** Are `System.getenv("HTTP_PROXY")` and `System.getProperty("http.proxyHost")` equivalent?  
**Answer:** No. Environment variables and JVM system property maps are different mechanisms; launchers/frameworks may bridge them, but it is not universally automatic.

**Q17.** What risk can the Java HTTP client logging flag `jdk.httpclient.HttpClient.log` pose?  
**Answer:** Logs may contain sensitive metadata/headers; you must control log destination, level, and redaction.

**Q18.** If a service has two tenants needing two proxies, should it change `http.proxyHost` before each request?  
**Answer:** No. System properties are global and have races; use per-client/per-request proxy config or process isolation.

**Q19.** If a test changes host and port with two `setProperty` calls, is another thread guaranteed to read both values from the same version?  
**Answer:** No. The config set has no atomic update, so it may see the new host and old port.

**Q20.** To prove a property is startup-only, should you test in one JVM by changing `System.setProperty` or run two different JVMs with `-D`?  
**Answer:** Run **two separate JVMs** with different startup flags and observe behavior, as in the IPv4/IPv6 demo.

**Q21.** Is `http.keepAlive` the same as TCP `SO_KEEPALIVE`?  
**Answer:** No. One controls HTTP persistent connection reuse in the legacy handler, while the other is TCP keepalive probes.

**Q22.** Does `ProxySelector.getDefault()` always respect `http.proxyHost` if the application has called `setDefault(custom)`?  
**Answer:** No. A custom selector may have different logic and not read that system property.

**Q23.** Why must you check the Java version/update release when comparing `jdk.httpclient.*` settings?  
**Answer:** Because these are JDK-specific properties whose defaults/behavior can change; do not assume legacy `java.net` rules apply.

**Q24.** If a proxy has already been selected for a socket and the host property changes afterward, does the socket automatically connect to the new proxy?  
**Answer:** No. The routing choice for an established connection does not change automatically; a new request/connection must re-select.

## 20. Application checklist and trusted sources

### Pre-configuration checklist

- [ ] Record the **exact property name**, API/module, JDK version, and **documented default**.
- [ ] Identify whether it is a **system property**, **security property**, `conf/net.properties` file, OS proxy, or per-client config.
- [ ] Identify which **JVM process** receives the configuration; do not treat multiple pods/services as one JVM.
- [ ] Determine whether the property is **startup-only** or **dynamic**; for JDK-specific properties, read module/implementation docs.
- [ ] For startup-only properties, add `-D` to the launcher before process start, **restart the JVM**, and verify.
- [ ] For dynamic proxies, only expect new requests/selections to observe the value; running sockets do not reroute automatically.
- [ ] Do not use `System.setProperty` per-request in a multi-threaded JVM.
- [ ] Do not mix `http.maxConnections` of the legacy URL handler with `jdk.httpclient.connectionPoolSize` of the modern client.
- [ ] For DNS TTL, use a **Security property** instead of regular `-D`; do not assume the OS DNS cache resets as well.
- [ ] Do not rely solely on `System.getProperty` to conclude native networking state has changed.
- [ ] Measure actual `ProxySelector.select`, local/remote IPs, TCP connections, and HTTP handler behavior with authorized telemetry.
- [ ] Separate startup config, live config reload, and mutable global state, avoiding races between two property values.
- [ ] Limit logs; never dump all system properties or secrets.
- [ ] Use a **separate test JVM** for any experiments that mutate global security/system properties.
- [ ] When production requires two different network policies, choose instance config or process isolation per contract.

**Conclusion:** in Java Networking, “a property is in `System`” does **not** mean “read on every use”; “`System.setProperty` was changed” does **not** mean “the network stack changed”; and “global” usually means **across one JVM process**, not across all Java processes. Know **which store a property belongs to, when it is read, and which objects it affects** before changing configuration.

### Official documentation (Java SE 17)

- [Networking Properties — java.net IPv4/IPv6, proxies, HTTP handler, DNS cache](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/doc-files/net-properties.html).
- [Java Networking — JDK 17 system/proxy/HTTP Client properties](https://docs.oracle.com/en/java/javase/17/core/java-networking.html).
- [System — `getProperty` / `setProperty` and notes on changing standard system properties](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html).
- [Security — `getProperty` / `setProperty` for security properties](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/Security.html).
- [InetAddress — DNS cache TTL and negative cache](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/InetAddress.html).
- [ProxySelector — `getDefault`/`setDefault`/`select`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ProxySelector.html).
- [HttpClient — `newBuilder`/`proxy` and lifecycle](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html).
- [HttpURLConnection — legacy HTTP URL protocol handler](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/HttpURLConnection.html).
