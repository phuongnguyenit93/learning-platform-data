# HTTP Proxy, SOCKS Proxy, and Direct Connections: How Do They Differ in Java Networking?

When a Java application calls an external API, the connection can go **directly to the target server**, through an **HTTP forward proxy**, or through a **SOCKS proxy**. All three carry data from the client to a service, but **the endpoint the client first connects to over TCP, the control protocol, HTTP payload visibility, DNS resolution behavior, authentication mechanism, and the Java API to use** are not the same. Choosing the wrong approach can prevent requests from going through the proxy as intended, cause TLS/407 errors, leak DNS queries, bypass network policies, or trick the application into thinking a request was sent successfully when it only connected to the proxy.

This lesson belongs to the **Proxies and HTTP Sessions** topic in the **Java Advance - networking** module. The focus is on explaining the **practical roles and technical differences** between direct, HTTP proxy, and SOCKS connections in Java 17+, accompanied by runnable examples to verify the routing path yourself. Do not treat "proxy" as a JVM-wide switch that automatically affects every library, do not treat SOCKS as HTTP, and do not equate a proxy with a VPN or encryption.

## 1. Three Paths to the Same Resource

Suppose the application wants to access `https://api.example.test/orders`.

### 1.1. Direct Connection (DIRECT)

~~~text
Java client
     │  (1) DNS lookup api.example.test -> IP
     │  (2) TCP connect to IP:443
     │  (3) TLS handshake, verify certificate hostname
     │  (4) HTTP request / response
     ▼
api.example.test:443 (origin)
~~~

Here **the client's TCP peer is the origin**. No application proxy is configured in the logical path. However, there may still be routers, NAT, transparent firewalls, service meshes, or intermediate networks; "DIRECT" does **not** mean the physical transmission path has no intermediate devices.

**How to identify:** the client calls `Socket.connect(originAddress)` or uses an HTTP client configured with **no proxy**; the destination port is the origin's port. TLS, if HTTPS is used, is a client–origin server TLS session.

### 1.2. HTTP Forward Proxy

~~~text
Java HTTP client
      │ TCP to proxy.corp.test:3128
      │
      ▼
HTTP FORWARD PROXY
      │
      │ proxy handles HTTP request / policy / authentication
      │ (for HTTPS, typically uses HTTP CONNECT to tunnel)
      ▼
api.example.test:80 or :443
~~~

An HTTP forward proxy understands **HTTP semantics** on the client→proxy hop. For unencrypted HTTP, the client typically sends the request using an **absolute-form target**:

~~~http
GET http://api.example.test/products?id=1 HTTP/1.1
Host: api.example.test
~~~

This is an **illustrative request** to an HTTP proxy. For a direct HTTP/1.1 origin, the common request-target is **origin-form**:

~~~http
GET /products?id=1 HTTP/1.1
Host: api.example.test
~~~

These two forms **cannot be conflated**. An HTTP proxy can perform access control, logging, caching, or filtering if permitted and implemented. Not every proxy caches, modifies content, or decrypts TLS.

### 1.3. SOCKS Proxy

~~~text
Java TCP Socket
     │  TCP connect to socks.corp.test:1080
     │  SOCKS greeting / select auth / CONNECT hostname:port
     ▼
SOCKS proxy
     │ creates outbound TCP connection as requested
     ▼
api.example.test:443
     │ TLS (if the application initiates TLS itself)
     ▼
application protocol: HTTP, SMTP, custom TCP, ...
~~~

SOCKS is a **connection-forwarding** mechanism at a lower layer than HTTP. SOCKS5 (RFC 1928) has `CONNECT`, `BIND`, and `UDP ASSOCIATE` commands; the Java example below uses **SOCKS5 TCP CONNECT**. SOCKS does not need to understand URI paths, HTTP methods, or HTTP headers just to establish a TCP path. If TLS is used over SOCKS, the application **still must establish and verify TLS itself**.

**SOCKS is not an HTTP forward proxy**; sending an absolute-form HTTP request to a SOCKS port before completing the SOCKS handshake is a protocol error.

## 2. Comparison Table: Core Differences

| Property | DIRECT | HTTP forward proxy | SOCKS5 proxy |
| --- | --- | --- | --- |
| Client's first TCP peer | Origin IP:port | HTTP proxy IP:port | SOCKS server IP:port |
| Path control protocol | TCP/IP + application protocol | HTTP methods/headers, possibly `CONNECT` | SOCKS5 greeting, auth negotiation, command/target address |
| Understands HTTP method/path | Origin understands | HTTP proxy can understand (plain HTTP); CONNECT tunnel only forwards bytes once open | SOCKS does not need to understand HTTP |
| Non-TLS HTTP request | Sends HTTP to origin | Typically sends absolute-form target to proxy | After SOCKS CONNECT, sends HTTP as over normal TCP |
| HTTPS | Direct TLS to origin | Typically HTTP CONNECT, then TLS inside the tunnel to origin | SOCKS CONNECT, then TLS to origin |
| Usability for non-HTTP TCP | Yes, if reachable | Usually requires CONNECT and proxy permission; not automatic | SOCKS CONNECT suits many TCP protocols |
| Origin DNS | Usually resolved by client/OS | Proxy can resolve when receiving URI/CONNECT hostname | SOCKS5 can accept hostname (`ATYP=DOMAINNAME`) and resolve on the proxy side |
| Authentication | Application/origin depending on protocol | Possible HTTP proxy auth, e.g., `407`/`Proxy-Authenticate` | Separate SOCKS5 negotiation/auth, not HTTP 407 |
| Suitable Java 17 API | `HttpClient.Builder.NO_PROXY`, `new Socket(Proxy.NO_PROXY)` | `HttpClient.Builder.proxy(ProxySelector.of(...))` | `new Socket(new Proxy(Proxy.Type.SOCKS,...))` |
| Single configuration for all libraries | Should not be assumed | Each library may have its own proxy config | Should not infer `HttpClient` behavior from `Socket` |
| Data confidentiality | Depends on HTTP/TLS | HTTP may expose plaintext; HTTPS CONNECT is typically a tunnel | SOCKS does not encrypt app payload by itself |

**Short takeaway:** DIRECT sends the connection straight to the origin, an HTTP proxy is an **HTTP-aware** intermediary, and SOCKS is a **transport-establishing/forwarding** intermediary. They can all lead to the same URL, but they are **not equivalent at the protocol layer**.

## 3. Why Does an HTTP Proxy Handle HTTP and HTTPS Differently?

### 3.1. Unencrypted HTTP Through a Forward Proxy

When a client requests `http://service.example.test/a` through an HTTP proxy, the request on the client→proxy hop may look like:

~~~text
TCP: client ─────► proxy:3128

GET http://service.example.test/a HTTP/1.1
Host: service.example.test
~~~

The proxy inspects the URL, checks policy/authorization, and then creates an upstream request or serves from cache if policy/implementation permits. The origin does not necessarily know the client's real IP address: it sees the connection from the proxy (depending on infrastructure) and may receive forwarding headers added by the proxy; **never blindly trust the `X-Forwarded-For` header from any untrusted client**.

An HTTP proxy on an HTTP path **can read the unencrypted method, path, query, headers, and body**. Therefore, do not send secrets over plaintext HTTP just because it "went through an internal proxy."

### 3.2. HTTPS Typically Uses HTTP CONNECT

To access `https://api.example.test:443` through an HTTP/1.1 HTTP proxy, the client typically opens TCP to the proxy and sends:

~~~http
CONNECT api.example.test:443 HTTP/1.1
Host: api.example.test:443
~~~

If the proxy allows it, it returns a 2xx response indicating the tunnel is ready; from then on, **bytes after the response headers belong to the tunnel**, typically the client ↔ origin TLS handshake:

~~~text
Client                 HTTP proxy                     Origin
  │ TCP connect proxy      │                           │
  ├───────────────────────►│                           │
  │ CONNECT origin:443     │                           │
  ├───────────────────────►│──── TCP connect origin ──►│
  │ HTTP/1.1 200 ...       │◄───────────────────────────│
  │◄───────────────────────│                           │
  │  TLS ClientHello (SNI origin hostname)             │
  ├══════════════════════════════════════════════════►│
  │  certificate verification / encrypted HTTPS       │
  │◄═════════════════════════════════════════════════►│
~~~

Key points:
- `CONNECT` is an **HTTP method sent to an HTTP proxy**, not a SOCKS command.
- The target uses **host:port**, not a URL path.
- The proxy can see the target hostname:port, timing, and traffic volume; however, with **end-to-end TLS and no TLS interception**, it does **not** read the plaintext HTTPS payload.
- If an organization deploys **TLS interception** with an internal CA trusted by the client, TLS may actually terminate at the proxy and then establish a new TLS hop to the origin. That is a different model; it requires policy, certificate management, and auditing.
- A successful `CONNECT` does not mean the TLS certificate is valid or the HTTP response succeeded. The client still must verify the TLS peer/origin and send an HTTP request of the appropriate version.
- A proxy may allow tunneling only to controlled destination ports to reduce the risk of relay abuse. <RFC 9110 `9.3.6> describes CONNECT and those protective requirements.

In HTTP/2, CONNECT has its own representation via pseudo-headers; the diagram above illustrates **HTTP/1.1 CONNECT**, not HTTP/2 frames on the wire.

### 3.3. An HTTP Proxy May Require Authentication via HTTP 407

- `401 Unauthorized`: typically the origin requesting authentication, accompanied by `WWW-Authenticate`.
- `407 Proxy Authentication Required`: the HTTP proxy requesting authentication, accompanied by `Proxy-Authenticate`.
- `Authorization` and `Proxy-Authorization` have **different scopes**; never copy origin credentials to the proxy or vice versa.

In Java, `HttpClient.Builder.authenticator(Authenticator)` can supply credentials according to the challenge and scheme supported by the implementation. Do not hardcode passwords in source code, do not put secrets in URLs/queries/logs, and do not assume all proxy auth types are supported equally by JSSE/HTTP clients. For HTTPS CONNECT, some auth schemes (such as Basic) may be disabled by default JDK policy during tunneling; check organization-managed security configuration, and **do not arbitrarily relax policies** just to get past a 407.

## 4. SOCKS5: A Completely Different Handshake from HTTP

SOCKS5 per RFC 1928 has an authentication method negotiation step, after which the client sends a connection request. For the **TCP CONNECT** case:

~~~text
Client                          SOCKS5 proxy
   │ TCP connect proxy:1080           │
   ├─────────────────────────────────►│
   │ VER=05, NMETHODS, METHODS        │
   ├─────────────────────────────────►│
   │ VER=05, METHOD selected          │
   │◄─────────────────────────────────┤
   │ CONNECT request:                 │
   │   VER=05, CMD=01, RSV=00         │
   │   ATYP, DST.ADDR, DST.PORT       │
   ├─────────────────────────────────►│
   │ Reply: VER=05, REP, RSV, BND...  │
   │◄─────────────────────────────────┤
   │ If REP=00: TCP tunnel is ready   │
   │◄════════════════════════════════►│
   │ app bytes: TLS/HTTP/custom TCP   │
~~~

Fields:
- `VER=0x05`: SOCKS version 5.
- `CMD=0x01`: TCP CONNECT (different from HTTP CONNECT on the wire).
- `ATYP=0x01`: IPv4 address; `0x03`: length-prefixed hostname; `0x04`: IPv6.
- `DST.PORT`: two bytes in network byte order.
- `REP=0x00`: success; other values indicate proxy-level errors (refused, network unreachable, unsupported address type...).
- The auth step can use no-auth, username/password, or other mechanisms depending on the SOCKS server; do **not** send HTTP `Proxy-Authorization` to replace SOCKS auth.

SOCKS5 also defines `UDP ASSOCIATE`, but **Java's `new Socket(Proxy.Type.SOCKS...)` in this lesson only performs TCP CONNECT**. Do not treat that as proof that every `DatagramSocket`, `DatagramChannel`, or `HttpClient` can use SOCKS UDP; UDP proxying requires checking the specific API/implementation/protocol.

## 5. Where Is DNS Resolved?

This is an often-overlooked difference.

### 5.1. DIRECT

Typically the application/OS resolves `api.example.test` to an IP and then opens TCP to the destination IP. The actual mechanism may involve DNS resolvers, caches, IPv4/IPv6, and corporate DNS. You cannot infer where the DNS lookup happens merely from Java passing a `URI`.

### 5.2. HTTP Proxy

With an HTTP forward proxy, the client sends a URI containing a hostname or a CONNECT host:port to the proxy. The proxy **can** look up the origin's DNS itself. The client still must resolve the **proxy** address (unless configured by IP or another mechanism) and there may be other DNS activity at the library, redirect, PAC, or security layer.

HTTPS over HTTP CONNECT typically lets the proxy open TCP to the hostname in CONNECT; the client still verifies the TLS identity of the target hostname. Do not conclude that a proxy "completely hides DNS" because in practice the system may still make DNS requests outside the proxy path.

### 5.3. SOCKS5 and `createUnresolved`

With `java.net.Socket`:

~~~java
Proxy socks = new Proxy(
        Proxy.Type.SOCKS,
        new InetSocketAddress("socks.corp.test", 1080));

try (Socket socket = new Socket(socks)) {
    socket.connect(
            InetSocketAddress.createUnresolved(
                    "api.example.test", 443), 5000);
    // After the SOCKS handshake succeeds, communicate with the origin via socket.
}
~~~

This is an **illustrative snippet** inside a method with `throws IOException`, importing `java.net.*`. `InetSocketAddress.createUnresolved` does not perform a DNS lookup when creating the endpoint. With a SOCKS5 implementation that supports hostnames, the socket sends `ATYP=DOMAINNAME` and lets the proxy handle the hostname; the runnable example in section 11 confirms exactly that in the test.

If replaced with `new InetSocketAddress("api.example.test",443)`, the constructor may perform a local DNS lookup. This changes how the name is resolved and can affect security/network routing. However, **remote DNS is not a guarantee across every SOCKS version, provider, or library**; you must test the destination and DNS flows on the target OS/JDK.

**Specifying an unresolved hostname is not a way to bypass access policies.** The proxy must enforce ACLs on the resolved destination address, prevent DNS rebinding/SSRF, filter private IPs/disallowed ports, and protect internal services. When testing, use non-resolving `*.test` hostnames and a safe SOCKS mock on loopback.

## 6. Java 17 Configuration: Three Different APIs

### 6.1. `java.net.http.HttpClient`: DIRECT or HTTP Proxy

~~~java
// Explicit DIRECT, ignoring the default proxy selector.
HttpClient direct = HttpClient.newBuilder()
        .proxy(HttpClient.Builder.NO_PROXY)
        .build();

// HTTP forward proxy for HTTP/HTTPS.
HttpClient viaHttpProxy = HttpClient.newBuilder()
        .proxy(ProxySelector.of(
                new InetSocketAddress("proxy.corp.test", 3128)))
        .build();
~~~

This is a **Java 17 illustrative snippet**, requiring `import java.net.*;` and `import java.net.http.*;`. According to the Javadoc, `ProxySelector.of(InetSocketAddress)` creates a selector that uses an **HTTP proxy for HTTP/HTTPS requests**; it does **not** create a SOCKS proxy just because the server is on port 1080.

If `builder.proxy(...)` is not called, the default `HttpClient` **typically uses `ProxySelector.getDefault()`**, which can be affected by JVM system properties or environment settings. `client.proxy()` returning `Optional.empty()` does not prove the client is DIRECT: this API only exposes an **explicit selector** passed to the builder; the implementation may use an unexposed default selector.

To guarantee DIRECT for a client, use `HttpClient.Builder.NO_PROXY`. When a client needs per-host/per-scheme routing, you can install a custom `ProxySelector` or configure the library per policy; **do not** assume a proxy applies to every request after redirects, every URI scheme, or all frameworks.

**Important limitation of the JDK built-in HttpClient:** even though `java.net.Proxy.Type.SOCKS` exists, do not assume `HttpClient.Builder.proxy(...)` will use SOCKS. In the `java.net.http.HttpClient` implementation provided by OpenJDK/JDK 17, SOCKS proxies are not supported as a standard HTTP client routing path. If you genuinely need HTTP requests over SOCKS, use an HTTP client/library with verified SOCKS support or implement an appropriate transport tunnel; verify using proxy-side logs, not just by inspecting `ProxySelector.select(...)`.

### 6.2. `java.net.Socket`: DIRECT or SOCKS at the TCP Layer

~~~java
// Ignore other JVM proxy configuration for this socket.
try (Socket directSocket = new Socket(Proxy.NO_PROXY)) {
    directSocket.connect(
            new InetSocketAddress("service.example.test", 9000), 5000);
    directSocket.setSoTimeout(5000);
    // Service's app protocol is managed by the caller.
}

// Route TCP through SOCKS.
Proxy socksProxy = new Proxy(
        Proxy.Type.SOCKS,
        new InetSocketAddress("socks.corp.test", 1080));

try (Socket socksSocket = new Socket(socksProxy)) {
    socksSocket.connect(
            InetSocketAddress.createUnresolved(
                    "service.example.test", 9000), 5000);
    socksSocket.setSoTimeout(5000);
    // Data stream after SOCKS connect is treated as a TCP byte stream.
}
~~~

This is an **illustrative snippet** and should not be run against `*.test` hostnames since they are not real servers. `new Socket(Proxy.NO_PROXY)` is **DIRECT** even when the JVM has other SOCKS settings. `new Socket(Proxy.Type.SOCKS, ...)` is not an HTTP proxy and does not perform HTTP framing automatically. If you want to speak HTTP over a TCP socket, the application still must implement proper HTTP protocol framing and TLS/hostname verification for HTTPS.

`SocketChannel.open()` / non-blocking `Selector` does not have the same explicit `SocketChannel(Proxy)` constructor as `Socket(Proxy)`. Do not take a blocking SOCKS `Socket` example and assume every NIO channel automatically routes through SOCKS. If you need NIO over SOCKS, you need a transport adapter/handshake/proxy library that supports asynchronous operation.

### 6.3. `URL.openConnection(Proxy)` Belongs to Another API

With legacy `URLConnection` / `HttpURLConnection`, you can pass a proxy per request:

~~~java
URL url = new URL("http://service.example.test/status");
Proxy proxy = new Proxy(
        Proxy.Type.HTTP,
        new InetSocketAddress("proxy.corp.test", 3128));

URLConnection conn = url.openConnection(proxy);
conn.setConnectTimeout(5000);
conn.setReadTimeout(5000);
// Read input/error streams and close properly when the request executes.
~~~

This is an **illustrative snippet**. `URL.openConnection(Proxy)` can support `Proxy.Type.HTTP` and in some protocol handlers `Proxy.Type.SOCKS`, **but do not infer that every custom URL protocol handler supports it**; the Javadoc notes that an unsupported handler may ignore the proxy and connect directly. `URL.openConnection(Proxy.NO_PROXY)` is the explicit way to request DIRECT for a handler.

Do not mix the APIs into an invalid pattern like `HttpClient.newBuilder().proxy(new Proxy(...))`: **`builder.proxy` takes a `ProxySelector`**, not a `Proxy`. Similarly, `Socket(Proxy)` takes a `Proxy`, not a `ProxySelector`.

### 6.4. API Mapping Table

| Need | Java 17 API | Note |
| --- | --- | --- |
| DIRECT HTTP request | `HttpClient.Builder.proxy(NO_PROXY)` | Ignores default selector |
| HTTP/HTTPS via HTTP proxy | `HttpClient.Builder.proxy(ProxySelector.of(addr))` | `ProxySelector.of` is for HTTP and HTTPS |
| DIRECT TCP socket | `new Socket(Proxy.NO_PROXY)` | Does not rely on SOCKS system properties |
| TCP socket via SOCKS5 | `new Socket(new Proxy(Proxy.Type.SOCKS, addr))` | App still handles TLS/HTTP if needed |
| URLConnection via HTTP proxy | `url.openConnection(new Proxy(HTTP, addr))` | Legacy API, handler behavior may vary |
| Per-URL/host routing rule | Custom `ProxySelector` | Selects DIRECT or proxy per policy |
| HTTP via SOCKS on JDK HttpClient | **Not supported by default** | Use a verified library/transport |

## 7. Configuring Proxies via JVM System Properties

JDK 17 has related networking properties:

~~~bash
java -Dhttp.proxyHost=proxy.corp.test -Dhttp.proxyPort=3128 MyApp
java -Dhttps.proxyHost=proxy.corp.test -Dhttps.proxyPort=3128 MyApp
java -DsocksProxyHost=socks.corp.test -DsocksProxyPort=1080 MyApp
~~~

These are only **Java command syntax examples**; there is no real proxy at `*.test`. According to Oracle Networking Properties:

- `http.proxyHost`, `http.proxyPort` (default 80) for the HTTP protocol handler.
- `https.proxyHost`, `https.proxyPort` (default 443 per documentation) for the HTTPS protocol handler.
- `http.nonProxyHosts` is the list of hosts that bypass the HTTP proxy, with patterns separated by `|` and `*` wildcards; the HTTPS handler uses this same property.
- `socksProxyHost`, `socksProxyPort` (default 1080 if not configured) for TCP SOCKS where supported by the implementation, plus `socksProxyVersion` commonly set to 5.
- `java.net.useSystemProxies=true` allows some environments to use system proxy settings and is read **once at JVM startup**; therefore it should be passed via `-D` at launch.

**System properties are not a contract forcing all libraries through a proxy.** An `HttpClient` with a different explicit selector can ignore the default, `Socket(Proxy.NO_PROXY)` ignores SOCKS settings, and native libraries/Netty/Apache clients have their own configurations. Verify the **actual path** with tests or logs.

Bypass configuration example:

~~~bash
java '-Dhttp.nonProxyHosts=localhost|127.*|*.internal.test' \
     -Dhttp.proxyHost=proxy.corp.test \
     -Dhttp.proxyPort=3128 MyApp
~~~

In real shells, quoting and line-continuation syntax differ among Linux shells, PowerShell, and cmd; when running in Windows PowerShell, put the `-D...` flags on one line or quote appropriately instead of using Unix backslash continuation. Avoid enabling a global system proxy after `HttpClient` instances have already been created: JDK `HttpClient` may capture default settings at build time and not reflect later changes.

**Warning:** if `http.nonProxyHosts` is configured too broadly, requests may go DIRECT unexpectedly, violating egress policy. Do not mutate the global JVM proxy to "fix one request" if the application has multiple tenants or features requiring different policies.

## 8. `ProxySelector`: Chooses a Route, Not Proof the Network Followed It

Per the `ProxySelector` Javadoc, `select(URI)` returns a list of candidate `Proxy` objects in preference order. A custom selector can return `Proxy.NO_PROXY` when direct is needed; `connectFailed` receives notifications when connecting to a proxy fails for availability/failover handling.

Illustrative snippet (inside a method/class with appropriate imports):

~~~java
Proxy httpProxy = new Proxy(Proxy.Type.HTTP,
        InetSocketAddress.createUnresolved("proxy.corp.test", 3128));

ProxySelector selector = new ProxySelector() {
    @Override
    public List<Proxy> select(URI uri) {
        String host = uri.getHost();
        if (host == null) throw new IllegalArgumentException("No host");
        if ("localhost".equalsIgnoreCase(host)
                || host.endsWith(".internal.test")) {
            return List.of(Proxy.NO_PROXY);
        }
        return List.of(httpProxy);
    }

    @Override
    public void connectFailed(
            URI uri, SocketAddress address, IOException error) {
        System.err.println("HTTP proxy connect failed for " + uri.getHost());
    }
};
~~~

This is **pseudocode for learning route policy**, not a standalone class (it requires `List`, `URI`, `IOException`, `Proxy`, `ProxySelector`, `InetSocketAddress`). If attached to `HttpClient.Builder.proxy(selector)`, remember that the **actual HTTP client implementation** may only support certain proxy types. Returning `List.of(Proxy.Type.SOCKS)` from a custom selector does not prove the HTTP client used SOCKS.

In production, build policies carefully:
- Only proxy URI schemes that are actually supported.
- Normalize/validate hostnames per IDNA/IP literal rules to avoid bypasses via mixed case or suffix tricks (e.g., `evilinternal.test` is not `*.internal.test`).
- Prevent redirects from shifting routes unexpectedly to private IPs or loopback; enforce SSRF and network egress controls.
- **Do not add `Proxy.NO_PROXY` as a fallback after a proxy** if policy forbids direct connections. An uncontrolled fail-open default can leak traffic.
- `ProxySelector` is only a **routing decision**, not proof that the TCP connection reached the proxy.
- If the proxy fails, handle according to policy: fail closed, retry another approved proxy, or explicit direct only when permitted.

## 9. Complete Java 17+ Example 1: DIRECT vs. HTTP Forward Proxy

This program **runs entirely on loopback**, with no DNS/Internet or real proxy. It creates:
1. An `HttpServer` acting as the **origin**, returning `FROM_ORIGIN`.
2. A `ServerSocket` acting as an **HTTP proxy mock**, reading the request line/headers and returning `FROM_PROXY`.
3. Two `HttpClient` instances sending to the **same URL**: one explicit DIRECT client, and one client using `ProxySelector.of(...)` pointing to the mock.

**The mock proxy does not actually forward requests to the origin**: this is an experiment to **verify route selection and request-target format**, not an example of building a production proxy. Ports are dynamically assigned by the OS so port numbers are not hardcoded into stdout.

Create the file **`HttpProxyRouteDemo.java`**:

~~~java
import com.sun.net.httpserver.*;
import java.io.*;
import java.net.*;
import java.net.http.*;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.*;

public final class HttpProxyRouteDemo {
    private static void respond(
            HttpExchange ex, String text) throws IOException {
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        ex.sendResponseHeaders(200, bytes.length);
        try (OutputStream out = ex.getResponseBody()) {
            out.write(bytes);
        }
    }

    public static void main(String[] args) throws Exception {
        InetAddress host = InetAddress.getLoopbackAddress();
        HttpServer origin = HttpServer.create(
                new InetSocketAddress(host, 0), 0);
        origin.createContext("/demo",
                ex -> respond(ex, "FROM_ORIGIN"));
        origin.start();

        try (ServerSocket proxy =
                new ServerSocket(0, 1, host)) {
            proxy.setSoTimeout(5000);

            FutureTask<String> captured = new FutureTask<>(() -> {
                try (Socket peer = proxy.accept()) {
                    peer.setSoTimeout(5000);
                    BufferedReader in = new BufferedReader(
                            new InputStreamReader(peer.getInputStream(),
                                    StandardCharsets.ISO_8859_1));
                    String first = in.readLine();
                    String line;
                    while ((line = in.readLine()) != null
                            && !line.isEmpty()) {
                        // Ignore headers in this mock.
                    }

                    byte[] body =
                            "FROM_PROXY".getBytes(StandardCharsets.UTF_8);
                    byte[] head = (
                            "HTTP/1.1 200 OK\r\nContent-Length: "
                            + body.length
                            + "\r\nConnection: close\r\n\r\n")
                            .getBytes(StandardCharsets.ISO_8859_1);

                    OutputStream out = peer.getOutputStream();
                    out.write(head);
                    out.write(body);
                    out.flush();
                    return first;
                }
            });

            Thread worker =
                    new Thread(captured, "one-shot-http-proxy");
            worker.setDaemon(true);
            worker.start();

            URI url = new URI("http", null, host.getHostAddress(),
                    origin.getAddress().getPort(),
                    "/demo", null, null);
            HttpRequest req = HttpRequest.newBuilder(url)
                    .timeout(Duration.ofSeconds(5))
                    .GET().build();

            HttpClient direct = HttpClient.newBuilder()
                    .proxy(HttpClient.Builder.NO_PROXY)
                    .version(HttpClient.Version.HTTP_1_1)
                    .build();
            HttpResponse<String> a = direct.send(req,
                    HttpResponse.BodyHandlers.ofString());
            System.out.println("direct body: " + a.body());

            HttpClient throughProxy = HttpClient.newBuilder()
                    .proxy(ProxySelector.of(new InetSocketAddress(
                            host, proxy.getLocalPort())))
                    .version(HttpClient.Version.HTTP_1_1)
                    .build();
            HttpResponse<String> b = throughProxy.send(req,
                    HttpResponse.BodyHandlers.ofString());
            System.out.println("proxy body: " + b.body());

            String firstLine = captured.get(
                    5, TimeUnit.SECONDS);
            System.out.println("proxy saw absolute-form: " +
                    firstLine.startsWith("GET http://"));
        } finally {
            origin.stop(0);
        }
    }
}
~~~

Compile/run with JDK 17+ (the `jdk.httpserver` module is included in standard JDKs):

~~~bash
javac --release 17 HttpProxyRouteDemo.java
java HttpProxyRouteDemo
~~~

When local loopback and the Java HTTP stack are working, **stdout** is:

~~~text
direct body: FROM_ORIGIN
proxy body: FROM_PROXY
proxy saw absolute-form: true
~~~

Three key takeaways:
- `direct` uses `HttpClient.Builder.NO_PROXY`, so the request goes to the **origin** and receives `FROM_ORIGIN`.
- `throughProxy` selects an explicit HTTP proxy for the **same URL**, so it connects to the **mock proxy** and receives `FROM_PROXY`; that does not mean the origin was called on the second request.
- The mock observes a request-line like `GET http://127.0.0.1:<ephemeralPort>/demo HTTP/1.1` or the equivalent IPv6 URI: **absolute-form**, which is how an HTTP client talks to a forward proxy.
- The code does not expose a proxy to the Internet, does not forward to arbitrary hosts, and has no authentication/caching or TLS interception. It deliberately uses HTTP/1.1 to observe the request line; with HTTP/2/h2 proxies, framing differs.
- `HttpServer` creates a real origin on loopback; an HTTP client with an explicit direct configuration does not depend on the default environment proxy for the test.
- `proxy.setSoTimeout(5000)` and `captured.get(5,TimeUnit.SECONDS)` prevent the test from hanging indefinitely if the request never reaches the mock.
- Use `try-with-resources` for the mock server socket and accepted TCP connection; call `origin.stop(0)` in `finally`.

If a sandbox blocks loopback binding or the Java runtime image lacks `jdk.httpserver`, the test may fail to run even though the API logic is correct. The file/class name must match the above; no external proxy or Internet access is needed to understand the difference.

## 10. HTTPS Through an HTTP Proxy: TLS Must Still Be Verified Even When CONNECT Succeeds

The previous example only used **HTTP** because the mock returned a fake response, so do **not** use it as an example for testing HTTPS and CONNECT. With HTTPS, JDK `HttpClient` can establish a tunnel through an HTTP proxy; then the **TLS handshake to the target hostname** is performed through the tunnel.

A proper client:

~~~java
HttpClient client = HttpClient.newBuilder()
        .proxy(ProxySelector.of(
                new InetSocketAddress("proxy.corp.test", 3128)))
        .connectTimeout(Duration.ofSeconds(5))
        .build();

HttpRequest req = HttpRequest.newBuilder(
        URI.create("https://api.example.test/v1"))
        .timeout(Duration.ofSeconds(10)).GET().build();

HttpResponse<String> resp =
        client.send(req, HttpResponse.BodyHandlers.ofString());
~~~

This is an **illustrative snippet**, not runnable standalone (missing imports and no real proxy/origin at `*.test`). Do not set `SSLParameters.setEndpointIdentificationAlgorithm("")` or install a trust-all manager just because HTTPS through a proxy causes certificate errors. Keep truststore and hostname verification intact. `407` is a proxy error/challenge (possibly right at CONNECT), whereas `SSLHandshakeException` or hostname mismatch can occur **after the tunnel** during TLS.

If the proxy only allows certain hosts/ports, receiving `403`/`502` from the proxy must not be interpreted as coming from the origin. Check access logs at the right hop, but do not log `Proxy-Authorization`, tokens, or sensitive HTTP bodies.

**An HTTP proxy may itself be reached over plaintext HTTP** while the tunnel inside uses HTTPS. This is not the same as an HTTPS-proxy (TLS to the proxy). Each hop has its own security requirements; do not assume the entire path from client to proxy is encrypted just because the origin URL starts with `https://`.

## 11. Complete Java 17+ Example 2: SOCKS5 TCP CONNECT Using an Unresolved Hostname

To see firsthand how the SOCKS protocol differs from HTTP, this program runs a **SOCKS5 mock on loopback**, performing:
1. Receiving the client greeting and returning `VER=5, METHOD=0 (no-auth)`.
2. Receiving `SOCKS5 CONNECT` with an unresolved hostname (`ATYP=3`).
3. Returning a minimal SOCKS success frame.
4. Receiving application text `PING` and returning `PONG` over the same socket.

**The SOCKS mock does NOT connect to a real target host**. The name `target.example.test` is used solely to verify hostname formatting; there is no Internet access or network control bypass.

Create the file **`Socks5SocketDemo.java`**:

~~~java
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.*;

public final class Socks5SocketDemo {
    private static int readByte(InputStream in) throws IOException {
        int value = in.read();
        if (value < 0) {
            throw new EOFException("SOCKS frame truncated");
        }
        return value;
    }

    private static String readHost(
            InputStream in, int type) throws IOException {
        if (type == 3) {
            int length = readByte(in);
            return new String(in.readNBytes(length),
                    StandardCharsets.US_ASCII);
        }
        if (type == 1) {
            return InetAddress.getByAddress(
                    in.readNBytes(4)).getHostAddress();
        }
        if (type == 4) {
            return InetAddress.getByAddress(
                    in.readNBytes(16)).getHostAddress();
        }
        throw new IOException(
                "Unexpected SOCKS address type " + type);
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();
        try (ServerSocket fakeSocks =
                new ServerSocket(0, 1, loopback)) {
            fakeSocks.setSoTimeout(5000);

            FutureTask<String> accepted = new FutureTask<>(() -> {
                try (Socket peer = fakeSocks.accept()) {
                    peer.setSoTimeout(5000);
                    InputStream in = peer.getInputStream();
                    OutputStream out = peer.getOutputStream();

                    int version = readByte(in);
                    int methodsCount = readByte(in);
                    byte[] methods = in.readNBytes(methodsCount);
                    if (version != 5
                            || methods.length != methodsCount) {
                        throw new IOException("Not SOCKS5 greeting");
                    }
                    out.write(new byte[]{5, 0});
                    out.flush();

                    if (readByte(in) != 5
                            || readByte(in) != 1
                            || readByte(in) != 0) {
                        throw new IOException(
                                "Not SOCKS5 CONNECT");
                    }

                    String dst = readHost(in, readByte(in));
                    int port =
                            (readByte(in) << 8) | readByte(in);

                    out.write(new byte[]{
                            5, 0, 0, 1, 127, 0, 0, 1, 0, 0
                    });
                    out.flush();

                    String incoming = new BufferedReader(
                            new InputStreamReader(in,
                                    StandardCharsets.US_ASCII))
                            .readLine();
                    out.write("PONG\n".getBytes(
                            StandardCharsets.US_ASCII));
                    out.flush();
                    if (!"PING".equals(incoming)) {
                        throw new IOException(
                                "Unexpected app payload");
                    }
                    return dst + ":" + port;
                }
            });

            Thread worker = new Thread(
                    accepted, "one-shot-socks5-mock");
            worker.setDaemon(true);
            worker.start();

            Proxy setting = new Proxy(
                    Proxy.Type.SOCKS,
                    new InetSocketAddress(
                            loopback, fakeSocks.getLocalPort()));

            try (Socket client = new Socket(setting)) {
                client.connect(
                        InetSocketAddress.createUnresolved(
                                "target.example.test", 443),
                        5000);
                client.setSoTimeout(5000);
                client.getOutputStream().write(
                        "PING\n".getBytes(
                                StandardCharsets.US_ASCII));

                String answer = new BufferedReader(
                        new InputStreamReader(
                                client.getInputStream(),
                                StandardCharsets.US_ASCII))
                        .readLine();
                System.out.println(
                        "SOCKS tunnel data: " + answer);
            }

            System.out.println(
                    "SOCKS requested: " +
                    accepted.get(5, TimeUnit.SECONDS));
        }
    }
}
~~~

~~~bash
javac --release 17 Socks5SocketDemo.java
java Socks5SocketDemo
~~~

**Verified stdout** on local JDK:

~~~text
SOCKS tunnel data: PONG
SOCKS requested: target.example.test:443
~~~

Explanation:
- `new Proxy(Proxy.Type.SOCKS,...)` configures a SOCKS route for **a `java.net.Socket`**, not `HttpClient`.
- `createUnresolved("target.example.test",443)` does not resolve DNS locally before calling `connect`; the mock receives the hostname in SOCKS `ATYP=DOMAINNAME` and observes the exact name/port.
- The program completes the SOCKS handshake before sending `PING`; this message is **illustrative application data**, not an HTTP GET or TLS handshake.
- The mock sends a SOCKS success reply and then receives `PING`, **without actually relaying to an origin**. Thus the output does not prove `target.example.test` has a TCP:443 server or TLS certificate.
- When writing a real SOCKS5 server, you must strictly parse lengths/address types/methods/credentials, check ACLs, and actually open the tunnel and relay bidirectionally; this mock code is not a production proxy implementation.
- `Socket.connect(...,5000)` is the connect timeout and `setSoTimeout(5000)` is the read timeout; there is no single shared absolute deadline for the entire exchange.
- This model does not use UDP Associate and does not encrypt the payload itself. If the application needs HTTPS over SOCKS, it must establish an `SSLSocket`/TLS client with proper hostname verification after the tunnel is created.
- Only use authorized SOCKS servers with policies protecting DNS, allowed destinations, and authentication; never use arbitrary proxies to bypass egress controls.

## 12. Proxy Authentication: Do Not Mix Proxy Identity with Origin Identity

An HTTP request through a proxy may require authentication **twice**:
1. **Proxy auth:** permission to use the proxy. HTTP typically reports `407` with `Proxy-Authenticate`.
2. **Origin auth:** permission to access the resource. HTTP typically reports `401` with `WWW-Authenticate`.

**The two credential sets have different scopes**. With HTTPS CONNECT, proxy auth can happen **before the TLS handshake to the origin**. If Basic auth is used over an unencrypted client→proxy hop, the credential header can be read by an observer on that hop (Base64 **is not encryption**). Always protect the proxy connection/credentials and use secret storage.

With SOCKS5, authentication is **SOCKS protocol method negotiation**, such as username/password per RFC 1929, not HTTP `407` or `Proxy-Authorization`. SOCKS5 username/password authentication is transmitted over the SOCKS channel per the protocol mechanism and is not encrypted by default; protect the client→proxy hop according to environment requirements.

Do not hardcode usernames/passwords directly in source code:

~~~java
// Do not store credentials in code:
// new PasswordAuthentication("user", "hardcoded-secret".toCharArray());

// In real applications, fetch secrets from a secret manager / secure config
// and apply only to authorized proxy host:port pairs.
~~~

The snippet above is a **policy illustration**, not a standalone `Authenticator` declaration. If you need to use `java.net.Authenticator` with SOCKS or HTTP, check `RequestorType.PROXY`, hostname/port, and permissions; never return a proxy password to an unexpected challenge from the origin. Always use supported APIs/flows, and do not try to shoehorn HTTP proxy authentication into a SOCKS handshake.

## 13. Security: A Proxy Does Not Automatically Provide Privacy or Security

### 13.1. A Proxy Does Not Replace TLS

- **DIRECT HTTPS:** TLS client ↔ origin, verifying certificate/hostname.
- **HTTP proxy + HTTPS CONNECT:** tunnel through proxy, **TLS client ↔ origin** (unless TLS interception is intentionally used).
- **SOCKS + HTTPS:** proxy forwards TCP bytes, **TLS client ↔ origin**.
- **Plaintext HTTP through HTTP proxy or SOCKS:** content remains plaintext on unencrypted hops.

A SOCKS proxy does not provide end-to-end encryption by default. An HTTP proxy is not a VPN. If an enterprise uses TLS interception, the different trust model and policy must be explicitly documented.

### 13.2. DNS Leaks and Internal Destinations

Even when data connections go through a proxy, DNS lookups may go directly due to another component or creating a resolved endpoint. Check all of the following:
- Which side resolves the origin hostname?
- Which side resolves the proxy hostname?
- Do redirects/embedded resources use the same proxy policy?
- Could the URL host point to loopback, link-local, RFC1918/private networks, metadata services, or protected services?
- Does the bypass list have overly broad wildcards, case normalization issues, IPv4/IPv6 variants, or DNS rebinding risks?

A proxy used as an **egress control boundary** must usually fail closed when the proxy is unavailable. Automatically falling back to DIRECT after a proxy error can send traffic outside the approved path; do not use unapproved fail-open behavior.

### 13.3. Hostname Verification for HTTPS

Merely using a proxy does not change TLS rules. The client must still verify the origin certificate for the right hostname; SNI helps select the virtual host but does not authenticate by itself. Do not install a trust-all `X509TrustManager`, disable endpoint identification, or ignore certificate errors just to "get through the proxy." If the certificate is wrong after CONNECT, fix the CA chain/hostname/truststore/proxy interception config in a controlled way.

## 14. How Can a Proxy Affect HTTP Session / Connection Reuse?

Depending on routing, the **first TCP connection** has either the origin or the proxy as its peer. That affects:
- Connection pooling: direct connections are typically reused by origin/policy; proxied connections are reused by proxy/target and implementation.
- HTTP/1.1 vs HTTP/2: `HttpClient.Version.HTTP_2` is a preference; proxy capability/ALPN may cause the actual session to use HTTP/1.1. `HttpResponse.version()` is what confirms the actual version of a response.
- TLS session: with HTTPS CONNECT, TLS is established inside the tunnel to the origin; the HTTP proxy may only see CONNECT and traffic statistics.
- DNS/route: the proxy may resolve on behalf of the client; or an app may still resolve locally depending on settings.
- Failure modes: proxy connection refused, CONNECT refused, proxy 407, upstream DNS fail, origin 5xx, and TLS handshake fail are errors at **different hops**.
- Timeouts: `connectTimeout` to the proxy does not cover the entire time for the proxy to reach the origin, the TLS handshake, and the response body; use appropriate request/deadline policies.

Do not assume "HTTP/2 = a single TCP connection for all requests" when going through a proxy. Proxy configuration, scheme, authority, security policy, and route can cause the client to open another connection or fall back to HTTP/1.1.

## 15. Quick Diagnostics: Where Did the Request Actually Go?

| Symptom | Common Cause | What to Check |
| --- | --- | --- |
| HTTP via proxy returns different content than direct | Proxy/cache/filter/mock differs from origin | Logs, response source, request target, and route |
| `407 Proxy Authentication Required` | Proxy needs credentials / scheme not accepted | `Proxy-Authenticate`, auth policy, do not confuse with 401 |
| `401 Unauthorized` | Origin requires credentials | `WWW-Authenticate`, resource permissions |
| `Connection refused` to proxy | Wrong proxy host:port, service down, or firewall | TCP to proxy, proxy DNS, port, policy |
| `CONNECT` gets `403` | Proxy ACL forbids host/port | Egress rules, allowed ports, target |
| TLS hostname mismatch after CONNECT | Wrong origin/SNI/certificate or interception policy | Certificate chain, SAN, truststore |
| SOCKS reports unsupported method | Proxy does not accept auth methods | SOCKS5 method negotiation |
| SOCKS reports address type unsupported | Proxy does not support hostname/IP family | `ATYP`, DNS side, IPv4/IPv6 |
| Java HttpClient does not go through SOCKS | JDK HttpClient lacks a supported SOCKS path like `Socket` | Use a SOCKS-capable client, inspect actual traffic |
| System properties configured but still DIRECT | Client explicit NO_PROXY, bypass list, or lib ignores settings | Policy of that specific library/client |
| ProxySelector selected proxy but request never arrives | Implementation does not support proxy type, redirect policy, or route error | Authorized proxy-side accept/log/packet trace |
| HTTP works but HTTPS does not | Proxy forbids CONNECT, auth/cert/TLS issue | Distinguish 407/CONNECT/TLS/ALPN |
| Proxy connection succeeds but body times out | Slow origin, proxy buffering, TCP flow/timeout | Separate connect, request, read timeouts and proxy logs |

When debugging, log (without secrets): method, scheme, origin hostname, requested proxy mode, selected proxy host:port, target port, connect/tunnel/TLS/response timings, HTTP status, `response.version`, and exception category. Do not log authentication headers, bearer tokens, or full personal payloads.

## 16. Which Route Should You Choose for Each Scenario?

| Scenario | Typically Appropriate Choice | Reason |
| --- | --- | --- |
| Java service calling an internal API permitted directly | DIRECT | Simpler, fewer hops; still use TLS when needed |
| Enterprise requires auditing outbound HTTP/HTTPS | HTTP forward proxy | HTTP policy, CONNECT, authentication, centralized logging |
| A custom TCP application needs to go through a proxy | SOCKS5 TCP CONNECT or HTTP CONNECT if server permits | No HTTP semantics needed with SOCKS |
| Need a standard Java 17 HTTP client with a corporate proxy | HTTP proxy via `HttpClient.Builder.proxy(ProxySelector.of(...))` | Explicitly supported API |
| Need to route raw Java `Socket` through SOCKS | `Socket(new Proxy(Proxy.Type.SOCKS,...))` | API supports SOCKS5 TCP |
| Java 17 HTTP requests must go through SOCKS | Choose a dedicated HTTP client with SOCKS support, verify behavior | JDK HttpClient does not automatically support it just from Proxy.Type.SOCKS |
| Direct fallback is not allowed | Explicit enforced proxy + fail-closed policy | Protects egress/compliance |
| Only a few domains may go DIRECT | Selector with explicit allowlist/bypass | Reduces risk of broad bypass |
| Need content confidentiality between client and origin | Appropriate end-to-end HTTPS/TLS | A proxy is a route, not an encryption layer |

**Do not choose SOCKS just hoping for "absolute anonymity."** Proxy operators can still log metadata; origins can still receive identifiers in application headers/cookies; DNS/TLS/IP policies differ. The engineering goal is to choose the right transport/routing/authentication for legitimate and secure requirements.

## 17. Self-Check Exercises

**Question 1.** An `HttpClient` application calls the same URL via `NO_PROXY` and via `ProxySelector.of(...)`, and gets different results. Is that a contradiction?  
**Answer:** No. The paths differ: direct to the origin, proxied to the HTTP proxy; the proxy may process/return a different response.

**Question 2.** Does calling `ProxySelector.of(new InetSocketAddress("proxy",1080))` automatically create a SOCKS proxy because it uses port 1080?  
**Answer:** No. `ProxySelector.of` returns an HTTP proxy selector for HTTP/HTTPS. The port does not determine the protocol.

**Question 3.** Does using `new Socket(new Proxy(Proxy.Type.SOCKS,addr))` automatically send an HTTP GET and parse a JSON response?  
**Answer:** No. It creates a TCP connection through SOCKS. The application must speak the appropriate HTTP/TLS protocol.

**Question 4.** For HTTPS through an HTTP proxy, if `CONNECT` finishes and returns 200, does that mean the server certificate is valid?  
**Answer:** No. After the tunnel, TLS to the origin still must handshake and verify.

**Question 5.** Are `HTTP 407` and `HTTP 401` the same kind of auth?  
**Answer:** No. 407 is from the HTTP proxy; 401 is from the origin.

**Question 6.** What does SOCKS5 `ATYP=0x03` mean?  
**Answer:** The destination address is given as a length-prefixed **hostname/domain name**; the proxy can resolve it.

**Question 7.** Does `InetSocketAddress.createUnresolved` trigger DNS immediately when constructed?  
**Answer:** No; it creates an unresolved hostname+port object, useful when passing a target name through SOCKS5.

**Question 8.** Why does `HttpClient.proxy()` returning empty not prove DIRECT?  
**Answer:** It only says no explicit selector was set on the builder; the client may still use the default selector.

**Question 9.** When an HTTP proxy goes down, should you immediately fall back to DIRECT?  
**Answer:** Only if policy permits. In corporate networks with mandatory egress, you must fail closed or retry an approved proxy.

**Question 10.** Does a SOCKS5 proxy automatically encrypt TCP content between client and origin?  
**Answer:** No. HTTPS/TLS is a separate layer.

**Question 11.** With HTTP/2 through a proxy, does `client.version()==HTTP_2` prove the response ran over HTTP/2?  
**Answer:** No. Check `response.version()` on the actual response.

**Question 12.** How should proxy traffic be verified, besides reading configuration?  
**Answer:** Proxy-side request logs/counters or packet captures in an authorized test network, checking origin, target, CONNECT/SOCKS handshake, and status; do not snoop on others' traffic.

## 18. Safe Implementation Checklist

1. **Define the route** for each kind of request: DIRECT, HTTP_PROXY, or SOCKS; do not use a single generic "proxy=true" flag.
2. **Choose the right API**: JDK `HttpClient` for HTTP proxies, `Socket(Proxy.Type.SOCKS)` for SOCKS TCP; do not mix `Proxy` and `ProxySelector`.
3. **Distinguish plaintext HTTP forward proxy from HTTPS CONNECT tunnel**; check port, SNI, and TLS verification.
4. **Specify DNS behavior**: where the origin hostname is resolved; verify with tests rather than inferring from the URI.
5. **Separate authentication scopes**: 401 origin, 407 HTTP proxy, SOCKS method negotiation.
6. **Use explicit NO_PROXY** when direct is required; check default proxy, nonProxyHosts, and system properties when not explicit.
7. **Do not fail-open outside policy** when a proxy errors; prevent internal/SSRF bypasses outside allowlists.
8. **Preserve TLS** between client and origin when confidentiality/integrity is needed; never disable certificate validation.
9. **Bound resources**: connect/read/request timeouts, body size, open sockets, retries, connection pool.
10. **Do not assume a proxy speaks multiple protocols** just because it uses port 8080 or 1080; test the handshake.
11. **Observe the actual route** in integration tests (proxy accept logs, direct origin logs) rather than only checking selector output.
12. **Read the Javadoc for your exact JDK version**, test on the target OS/provider/proxy, and remember different HTTP libraries have different support.
13. **Manage credentials securely** in a secret manager; never log Proxy-Authorization/username/password.
14. **Do not treat a proxy as a VPN** or a guarantee of completely hiding origin/domain/IP; identify the real threat model and data flow.

## Standards and Javadoc References

- [Java SE 17 — `java.net.Proxy`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Proxy.html): `Proxy.Type.HTTP`, `Proxy.Type.SOCKS`, and `Proxy.NO_PROXY`.
- [Java SE 17 — `java.net.ProxySelector`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ProxySelector.html): `select`, `connectFailed`, `of` for HTTP/HTTPS, and default selector.
- [Java SE 17 — `java.net.Socket`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html): `Socket(Proxy)` and SOCKS/direct examples.
- [Java SE 17 — `InetSocketAddress`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/InetSocketAddress.html): `createUnresolved` and DNS behavior.
- [Java SE 17 — `HttpClient.Builder`](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Builder.html): `proxy(ProxySelector)`, `NO_PROXY`, and HTTP proxy example.
- [Java SE 17 — `HttpClient`](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): default selector, `client.proxy()`, HTTP/1.1 vs HTTP/2 support.
- [Java SE 17 — Networking Properties](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/doc-files/net-properties.html): `http.proxyHost`, `https.proxyHost`, `socksProxyHost`, `http.nonProxyHosts`, `java.net.useSystemProxies`.
- [Java SE 17 — `URL.openConnection(Proxy)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URL.html): per-URL proxy and protocol handler limitations.
- [RFC 9110, `9.3.6 — HTTP CONNECT](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.3.6): tunnel semantics, authority-form target, open-port risks.
- [RFC 1928 — SOCKS Protocol Version 5](https://www.rfc-editor.org/rfc/rfc1928.html): greeting, methods, CONNECT, BIND, UDP ASSOCIATE, ATYP, status.
- [OpenJDK issue JDK-8214516 — SOCKS proxy support in java.net.http.HttpClient](https://bugs.openjdk.org/browse/JDK-8214516): limitation to check when wanting to use JDK HttpClient with SOCKS.

**In summary:** **DIRECT** connects straight to the origin, an **HTTP proxy** handles routing at the HTTP layer (and can `CONNECT` to tunnel HTTPS), and a **SOCKS5 proxy** establishes a TCP path based on hostname/IP:port at a layer below HTTP. Java 17 provides **different** APIs for these routes; always verify **the actual connection path, DNS, TLS, and authentication** rather than just seeing a proxy object in configuration.