# CONNECT Tunnels When Accessing HTTPS via a Proxy in Java

## 1. When HTTPS must go through an HTTP proxy, what is different from regular HTTP?

When Java `HttpClient` sends a request to `https://api.example.com/orders` **via an HTTP proxy**, the proxy cannot simply read a GET with a URL and return the HTTPS content as it would when handling cleartext HTTP. The client needs a byte channel to the **origin server** to perform the **TLS handshake** itself and exchange HTTP inside the encrypted channel. The most common mechanism is the HTTP **`CONNECT`** method.

Key points:

- The client opens a **TCP connection to the proxy**, not directly to the origin.
- The client sends HTTP/1.1 `CONNECT api.example.com:443` to the proxy; the target is in **authority-form `host:port`**, without a path or query.
- The proxy decides whether connecting to `api.example.com:443` is allowed and, if permitted, opens a connection from the proxy to the target.
- The proxy returns a **2xx** response, usually `HTTP/1.1 200 Connection Established`.
- **Immediately after the blank line terminating the headers of the 2xx response**, the connection switches to **tunnel mode**. Subsequent bytes are forwarded bidirectionally and are no longer HTTP/1.1 requests sent *to the proxy*.
- The client starts the **TLS handshake over the tunnel** to authenticate the origin by domain name/certificate, negotiate keys, and usually negotiate HTTP/1.1 or HTTP/2 via ALPN.
- The client sends the actual HTTPS request (for example, GET `/orders`) **inside TLS**, then receives the origin server's HTTPS response. With a forward proxy that does not intercept TLS, the proxy mainly relays encrypted bytes and is not permitted to read the URI path, authorization, or HTTP body inside.

~~~text
                      BEFORE TUNNEL
Java HttpClient               HTTP proxy                  HTTPS origin
     |                            |                            |
     |--- TCP connect ----------->|                            |
     |--- CONNECT host:443 ------>|                            |
     |                            |--- TCP connect host:443 -->|
     |<--- HTTP/1.1 200 ----------|<--- TCP established -------|
     |                            |                            |
     |                 BIDIRECTIONAL TUNNEL ESTABLISHED        |
     |                            |                            |
     |--- TLS ClientHello =======>|==== opaque TLS bytes =====>|
     |<== TLS ServerHello ========|<=== opaque TLS bytes ======|
     |--- HTTPS GET /orders =====>|==== TLS ciphertext =======>|
     |<== HTTP 200 encrypted =====|<=== TLS ciphertext ========|
     |                            |                            |
     |             close/cancel/timeout on both sides          |
~~~

**Do not confuse the two "HTTP 200" responses in the diagram.** `200 Connection Established` is the **proxy's response to CONNECT**, indicating that the tunnel was created. `200 OK` after TLS is the **origin's response** to the actual GET/POST. Java's `HttpClient.send(request, ...)` normally returns an `HttpResponse` representing the **origin HTTP response**, not a separate object for the CONNECT 200 response.

This lesson belongs to **Java Advance - networking → Proxies and HTTP Sessions**, focusing on **CONNECT tunnels when accessing HTTPS via a proxy**, the wire protocol model, Java 17+, security, and troubleshooting.

## 2. Learning objectives

After this lesson, you will be able to:

1. Accurately describe the sequence **client → HTTP proxy → CONNECT → tunnel → TLS → HTTPS request/response**.
2. Read the `CONNECT host:port HTTP/1.1` request in **authority-form** and understand why `/path` or `https://.../path` is not sent as the CONNECT target.
3. Distinguish the **2xx response of CONNECT** from the **HTTP response of the target resource**.
4. Understand that a tunnel is a **bidirectional byte stream forwarder**, unlike a proxy that reads, caches, and modifies HTTP messages.
5. Know how TLS certificates, hostname verification, SNI, and ALPN work **after the tunnel is established**.
6. Distinguish an HTTP proxy used to reach an HTTPS origin from an **HTTPS proxy** (where the connection to the proxy itself also uses TLS), a SOCKS proxy, and a reverse proxy.
7. Configure Java 17 `HttpClient.Builder.proxy(ProxySelector.of(...))`, `SSLContext` when needed, and `Authenticator` for proxy authentication.
8. Identify `407 Proxy Authentication Required`, `403`, `502`, TLS handshake failures, `ConnectException`, `UnknownHostException`, and timeouts at each step.
9. Run a raw CONNECT example with a local TCP echo server to observe the proxy switching from HTTP headers to forwarding.
10. Run an example with an **HTTPS server + HTTP CONNECT proxy + real Java HttpClient**, using an explicitly trusted test certificate **without disabling hostname verification**.
11. Recognize risks: arbitrary CONNECT destinations, SSRF, port 25, proxy credential leakage, TLS interception, certificate trust, open proxies, and resource exhaustion.
12. Design proxy policies, retries, observability, tests, and shutdown with proper responsibilities.

## 3. Where does CONNECT sit in the protocol stack?

CONNECT is an **HTTP method primarily intended for proxies**. HTTP RFC 9110 `9.3.6` defines this method for the purpose of requesting an intermediary to open a **tunnel** to the target server and then **forward data bidirectionally** without interpreting the contents inside.

### 3.1. HTTP/1.1 wire request

~~~http
CONNECT api.example.com:443 HTTP/1.1
Host: api.example.com:443

~~~

On the wire, each line ends with `\r\n` and the final blank line is `\r\n\r\n`. This is a message **the client sends to the proxy**, not a GET/POST to the HTTPS origin.

- **`CONNECT`**: special method used to create a tunnel.
- **`api.example.com:443`**: authority-form consisting of host and **required port**; there is no default 443 if omitted.
- **`Host: api.example.com:443`**: HTTP/1.1 host/authority metadata of the request.
- **No CONNECT request body** by semantics.
- **No `GET /orders`** at this step: the URI path is inside the HTTP message **encrypted after TLS**, if the tunnel succeeds.

RFC 9110 requires an explicit port in the CONNECT request-target even when the URL `https://api.example.com/orders` omits the port and implicitly uses 443. Requests like the following are invalid or not valid CONNECT authority-form:

~~~text
CONNECT https://api.example.com/orders HTTP/1.1  # INVALID: full URL
CONNECT /orders HTTP/1.1                   # INVALID: path only
CONNECT api.example.com HTTP/1.1          # INVALID: missing port
CONNECT api.example.com:443 HTTP/1.1      # VALID
~~~

The `#` symbols in the example above are **explanatory comments**, not HTTP request content. For an IPv6 literal, the authority-form target includes the address enclosed in square brackets:

~~~http
CONNECT [2001:db8::10]:443 HTTP/1.1
Host: [2001:db8::10]:443

~~~

The `2001:db8::/32` address is reserved for documentation, **not** a real server. Do not strip the square brackets from an IPv6 authority because `:` also appears inside the address.

### 3.2. 2xx switches modes, it does not return a file

The proxy may respond:

~~~http
HTTP/1.1 200 Connection Established

~~~

From the byte **immediately after the header terminator** of the 2xx response, both sides must understand that the connection no longer carries regular HTTP request–response messages sent to the proxy. Subsequent data belongs to the **tunnel stream**: TLS records, protocol bytes, or other payloads agreed upon by the client and origin.

Key points in the specification:

- **Any successful 2xx response** to CONNECT indicates that the tunnel is established (200 is just the common value).
- An **unsuccessful** CONNECT response (for example, 403, 407, 502) means **no tunnel exists yet**; the client must handle the status as a proxy response.
- The proxy **must not send** `Content-Length` or `Transfer-Encoding` in a 2xx CONNECT response. The client must **ignore** these headers if it happens to receive them in a successful response.
- Do not expect a JSON body with a 200 CONNECT response; the bytes after the blank line are bytes from the tunnel.
- Responses to CONNECT **are not cacheable** by HTTP semantics.
- When one side closes, the proxy should attempt to flush any remaining pending data and then close/release both ends according to the tunnel contract.

This is not `HTTP 101 Switching Protocols`. A successful CONNECT uses **2xx** to switch to a tunnel; HTTP Upgrade/h2c/WebSocket handshakes have their own mechanisms. Do not use 101 as a regular CONNECT indicator.

### 3.3. 2 layers of HTTP status

~~~text
OUTER LAYER: PROXY CONTROL (before tunnel)
Client -> Proxy: CONNECT target:443
Proxy  -> Client: 200 / 403 / 407 / 502 ...

INNER LAYER: HTTPS APPLICATION (after TLS)
Client -> Origin: GET /v1/orders HTTP/1.1 (inside TLS)
Origin -> Client: 200 / 401 / 404 / 500 ... (inside TLS)
~~~

**Example:** If a Java client receives `HttpResponse.statusCode() == 404` for a GET `https://api.example.com/missing` request, that is usually the **origin's response after tunnel/TLS**, **not** the proxy saying CONNECT 404. Conversely, if the proxy returns 407 and authentication fails, the Java client may fail **before an HTTPS response can be produced**; there are no origin body/headers to process.

## 4. Comparing three ways through a proxy

| Path | Client sends to proxy | What HTTP content does the proxy see? | Security |
| --- | --- | --- | --- |
| HTTP `http://...` via HTTP proxy | Usually an HTTP request with an absolute-form target like `GET http://example.com/a HTTP/1.1` | Proxy can read method, path, headers, body if the hop is cleartext | No origin TLS under the plain HTTP scheme |
| HTTPS `https://...` via HTTP proxy | Usually `CONNECT example.com:443`, then TLS inside the tunnel | Sees CONNECT target/metadata and traffic metadata; does not read HTTP payload inside TLS if not intercepting TLS | End-to-end TLS between client and origin in the standard forwarding model |
| HTTPS `https://...` via a proxy with **TLS on the proxy hop** | Client–proxy TLS first, CONNECT inside that TLS, then client–origin TLS over the tunnel | Proxy still knows the target after decrypting client–proxy TLS; origin payload remains encrypted by the inner TLS | Two layers of TLS on different segments, depending on client/proxy support |

**HTTP proxy** does not mean "accesses HTTP websites only." It can create a tunnel for HTTPS using CONNECT. Conversely, the term **HTTPS proxy** usually refers to a proxy endpoint protected by TLS from client to proxy, which is **different** from a regular HTTP proxy used to reach an HTTPS origin.

A SOCKS proxy coordinates connections using the **SOCKS protocol**, not HTTP CONNECT; Java `java.net.http.HttpClient` proxy support in the Java 17 API should be read according to implementation capabilities, without assuming that any arbitrary `ProxySelector` makes Java automatically support every kind of SOCKS handshake.

A reverse proxy in front of an origin is a different component: a Java client can connect via HTTPS to a reverse proxy directly and **does not need CONNECT**. CONNECT is characteristic of **forward proxy/tunnel policies** and certain extended proxy protocol cases.

## 5. The TLS handshake happens **after** CONNECT succeeds

The exact timeline of an HTTPS request going through an HTTP proxy is typically:

~~~text
T0  Java resolves/connects to proxyHost:proxyPort
T1  Client -> Proxy: CONNECT origin.example:443 HTTP/1.1
T2  Proxy checks ACL / authentication / policy
T3  Proxy resolves/connects to origin.example:443
T4  Proxy -> Client: HTTP/1.1 200 Connection Established
T5  Client -> Origin (via tunnel): TLS ClientHello
T6  Origin -> Client (via tunnel): TLS handshake messages
T7  Client validates certificate chain + hostname
T8  TLS handshake completes; ALPN may select h2 or http/1.1
T9  Client -> Origin (encrypted): GET /resource ...
T10 Origin -> Client (encrypted): HTTP response
T11 Keep or close connection/tunnel according to lifecycle
~~~

Notes:

- **CONNECT 200 does not confirm TLS succeeded**; the TLS handshake can fail immediately afterward.
- **A successful TLS handshake does not prove HTTP status 200**; the origin can still return 401/404/500.
- The proxy can see `origin.example:443` in CONNECT and network metadata (timing, traffic volume, addresses). In many configurations without ECH, the SNI name in ClientHello is also observable. **Do not** treat a tunnel as complete anonymity.
- With a pure forwarding proxy, the proxy **does not have the origin's private key** and does not itself decrypt the HTTP requests/bodies inside TLS.
- The client must validate the certificate/hostname against the HTTPS URI; if the proxy routes to a fake endpoint, proper hostname verification will detect it.
- ALPN (typically over TLS) can negotiate `h2` or `http/1.1` **between the Java client and the HTTPS endpoint** inside the tunnel. The proxy's CONNECT itself may be HTTP/1.1 while the **inner HTTPS is HTTP/2**.
- TLS record/handshake traffic **does not look like text GET/POST**; you cannot read the payload after CONNECT by parsing HTTP/1.1 lines from the proxy.
- If an enterprise proxy deploys **TLS interception** with a CA trusted by the client device, the proxy can act as a TLS endpoint and decrypt/inspect requests. That is **no longer** the blind forwarding model to the origin described above; it must follow enterprise policy, security warnings, and the trust model. Do not instruct disabling certificate verification to "make the proxy work."

### 5.1. Who performs DNS for the origin?

The client must know how to find the **proxy** to open the TCP connection first. The origin hostname is sent in `CONNECT hostname:port`; **the proxy usually** performs DNS resolution and opens TCP to the origin. However, specific DNS behavior also depends on the client implementation, routing, proxy chaining, and policy.

Do not state categorically "the client never resolves the origin" or "the proxy always resolves the origin": a client may resolve the hostname to enforce policy/caching/diagnostics, and a proxy may forward CONNECT to a next-hop proxy. Distinguish **who opens the origin TCP hop** from **who performs the DNS query** based on the actual design.

### 5.2. CONNECT does not "upgrade" a regular HTTP request to HTTPS

Suppose Java code uses the URI `http://api.example.com/a` but configures an HTTP proxy. Merely having a proxy does not mean the data is automatically TLS-encrypted; the client may send cleartext HTTP `GET http://api.example.com/a` to the proxy. If you want HTTPS, you must use an **`https://` URI** and validate TLS.

Also do not think of CONNECT 200 as a "certificate of a trusted origin." It only indicates that the proxy claims to have created the tunnel. **TLS authenticates the origin** afterward.

## 6. Using Java 17 HttpClient: no need to write CONNECT manually

At the application layer, configure an HTTP proxy using `ProxySelector`:

~~~java
import java.net.InetSocketAddress;
import java.net.ProxySelector;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

HttpClient client = HttpClient.newBuilder()
        .proxy(ProxySelector.of(
                new InetSocketAddress("proxy.example.net", 3128)))
        .connectTimeout(Duration.ofSeconds(5))
        .version(HttpClient.Version.HTTP_2)
        .build();

HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://api.example.com/v1/items"))
        .timeout(Duration.ofSeconds(10))
        .GET()
        .build();

HttpResponse<String> response = client.send(
        request, HttpResponse.BodyHandlers.ofString());
System.out.println(response.statusCode());
~~~

This is a **code snippet for use inside a `throws Exception` method**; the domain/port are illustrative only, with no verified stdout. Java `HttpClient` **automatically handles proxy selection, CONNECT, the TLS handshake, and HTTP framing**; the application does not need to construct `CONNECT` requests or push TLS records over a `Socket`.

**Important distinctions:**

- `ProxySelector.of(InetSocketAddress)` creates a selector that uses a single specified proxy. With Java 17 `HttpClient.Builder.proxy(...)`, this is the common way to choose a specific HTTP proxy.
- `HttpClient.newBuilder().proxy(...)` records the proxy policy on the **client**. After building, changing the system's default `ProxySelector` usually does not affect the already-created client.
- If `.proxy(...)` is not called, Java `HttpClient` may use the default/system proxy selector depending on runtime/config. `HttpClient.proxy()` may return `Optional.empty()` even when an unexposed default selector is active.
- `ProxySelector` can choose direct or proxy depending on the URI; if you want to bypass, use an appropriate selector/policy. Do not assume every request will always go through the proxy if the application/system configures multiple routes.
- `version(HTTP_2)` is a **preference**; the actual HTTP response may be `HTTP_1_1`. Read `response.version()` instead of assuming that the proxy using HTTP/1.1 means the origin is definitely h1.
- Java 17 `HttpClient` is not yet `AutoCloseable` in the Java 17 API; do not use `try (HttpClient client = ...)` when compiling with `--release 17`.
- `connectTimeout` applies to the connection establishment phase per the API; `HttpRequest.timeout` applies the request deadline. Do not assume these two options automatically set an individual timeout for every proxy/TLS/response step in all implementations. Use an appropriate overall deadline/monitoring.
- **Do not** manually add `Proxy-Authorization` as an application request header to "force proxy CONNECT" if the HTTP stack manages authentication; use `Authenticator`/appropriate policy and check JDK behavior.

### 6.1. When proxy authentication is required

HTTP CONNECT may require proxy login:

~~~http
HTTP/1.1 407 Proxy Authentication Required
Proxy-Authenticate: Basic realm="private-proxy"

~~~

The lines above are an example of a **proxy challenge**, not an authorization error from the origin. The client is permitted to perform authentication according to supported schemes and security policy; a CONNECT retry may carry `Proxy-Authorization` for the proxy:

~~~http
CONNECT api.example.com:443 HTTP/1.1
Host: api.example.com:443
Proxy-Authorization: Basic <credential-value>

~~~

The `<credential-value>` value in the example is a **descriptive placeholder**, not a usable credential. If copied into a real HTTP request, it must be replaced with a standard authentication mechanism and real values; do not log tokens/passwords. Base64-encoding Basic **is not** encryption. When the client–proxy hop is cleartext HTTP, Basic credentials can be observed; prefer a protected proxy connection and an appropriate auth scheme/policy.

Java 17 skeleton example using `Authenticator`:

~~~java
HttpClient client = HttpClient.newBuilder()
    .proxy(ProxySelector.of(
        new InetSocketAddress("proxy.example.net", 3128)))
    .authenticator(new java.net.Authenticator() {
        @Override
        protected java.net.PasswordAuthentication getPasswordAuthentication() {
            // Only return credentials when this is a trusted proxy,
            // do not take them from a hard-coded literal in source code.
            if (getRequestorType() != RequestorType.PROXY) {
                return null;
            }
            return new java.net.PasswordAuthentication(
                    usernameFromSecureStore, passwordCharsFromSecureStore);
        }
    })
    .build();
~~~

**Code snippet**, requiring `usernameFromSecureStore`/`passwordCharsFromSecureStore` variables and imports for `HttpClient`, `ProxySelector`, `InetSocketAddress`; not standalone. In real code, you must also verify the exact proxy host/port/realm before returning credentials to avoid handing them to a different proxy due to changed configuration.

**Java 17 has a security caveat:** the property `jdk.http.auth.tunneling.disabledSchemes` includes **`Basic`** by default for HTTPS tunneling via CONNECT. Therefore, having an `Authenticator` **does not guarantee** Java will send Basic auth for CONNECT. This is one of the causes of repeated 407s. Read the Oracle Networking System Properties documentation and your organization's policy before changing the configuration; **do not** arbitrarily remove `Basic` from the disabled list just to make a test run, especially on untrusted networks. Choose a proxy and authentication scheme that are securely supported by your organization.

### 6.2. Java HttpClient does not represent CONNECT as a business request

The application goal remains:

~~~java
HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://api.example.com/resource")).GET().build();
HttpResponse<String> result = client.send(
        request, HttpResponse.BodyHandlers.ofString());
~~~

The client library can automatically issue CONNECT at the **protocol layer** before sending GET. Do not manually create:

~~~java
HttpRequest.newBuilder(URI.create("https://api.example.com"))
    .method("CONNECT", HttpRequest.BodyPublishers.noBody())
    .build();
~~~

and expect Java to automatically open a tunnel for another HTTPS GET. That asks the **application itself to send the CONNECT method** to the URI, which is different from the internal CONNECT mechanism managed by the HTTP stack for using a proxy. It is not the normal way to use `HttpClient.proxy(...)`; the application normally does not have direct access to inspect/control the raw tunnel socket via `HttpResponse`.

## 7. Java 17+ Program #1: simulating raw CONNECT and byte relay

The first example only illustrates **the HTTP CONNECT step and switching to a tunnel**; it **does not perform a TLS handshake**. After the proxy creates a tunnel to a local TCP echo server, the client sends four bytes `PING` and receives `PONG`. This lets you observe directly that **after CONNECT 2xx, the proxy no longer parses requests as HTTP, but only forwards bytes bidirectionally**.

`PING` and `PONG` should not be mistaken for HTTPS; they are raw bytes to test the tunnel. A real HTTPS example with verified certificates is in section 8.

### 7.1. File `HttpConnectEchoDemo.java`

~~~java
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.IOException;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class HttpConnectEchoDemo {
    private static String readHeaders(InputStream in) throws IOException {
        ByteArrayOutputStream buf = new ByteArrayOutputStream();
        int state = 0;
        while (buf.size() < 4096) {
            int b = in.read();
            if (b == -1) throw new IOException("Headers incomplete");
            buf.write(b);
            state = switch (state) {
                case 0 -> b == '\r' ? 1 : 0;
                case 1 -> b == '\n' ? 2 : b == '\r' ? 1 : 0;
                case 2 -> b == '\r' ? 3 : 0;
                default -> b == '\n' ? 4 : b == '\r' ? 1 : 0;
            };
            if (state == 4) return buf.toString(StandardCharsets.US_ASCII);
        }
        throw new IOException("Header limit exceeded");
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getByName("127.0.0.1");
        ExecutorService workers = Executors.newFixedThreadPool(3);
        try (ServerSocket origin = new ServerSocket(0, 1, loopback);
             ServerSocket proxy = new ServerSocket(0, 1, loopback)) {
            origin.setSoTimeout(5000);
            proxy.setSoTimeout(5000);
            Future<String> originTask = workers.submit(() -> {
                try (Socket upstream = origin.accept()) {
                    upstream.setSoTimeout(5000);
                    String request = new String(
                            upstream.getInputStream().readNBytes(4),
                            StandardCharsets.US_ASCII);
                    upstream.getOutputStream().write(
                            "PONG".getBytes(StandardCharsets.US_ASCII));
                    return request;
                }
            });
            Future<String> proxyTask = workers.submit(() -> {
                try (Socket incoming = proxy.accept()) {
                    incoming.setSoTimeout(5000);
                    String headers = readHeaders(incoming.getInputStream());
                    String requestLine = headers.split("\r\n", 2)[0];
                    String expected = "CONNECT 127.0.0.1:" +
                            origin.getLocalPort() + " HTTP/1.1";
                    if (!requestLine.equals(expected)) {
                        incoming.getOutputStream().write(
                                "HTTP/1.1 403 Forbidden\r\n\r\n".getBytes(
                                        StandardCharsets.US_ASCII));
                        return requestLine;
                    }
                    try (Socket outgoing = new Socket(
                            loopback, origin.getLocalPort())) {
                        outgoing.setSoTimeout(5000);
                        incoming.getOutputStream().write(
                                "HTTP/1.1 200 Connection Established\r\n\r\n"
                                        .getBytes(StandardCharsets.US_ASCII));
                        Future<?> toOrigin = workers.submit(() -> {
                            try {
                                incoming.getInputStream()
                                        .transferTo(outgoing.getOutputStream());
                                outgoing.shutdownOutput();
                            } catch (IOException error) {
                                throw new RuntimeException(error);
                            }
                        });
                        outgoing.getInputStream()
                                .transferTo(incoming.getOutputStream());
                        incoming.shutdownOutput();
                        toOrigin.get(5, TimeUnit.SECONDS);
                    }
                    return requestLine;
                }
            });

            try (Socket client = new Socket(loopback, proxy.getLocalPort())) {
                client.setSoTimeout(5000);
                String target = "127.0.0.1:" + origin.getLocalPort();
                String connect = "CONNECT " + target + " HTTP/1.1\r\n" +
                        "Host: " + target + "\r\n\r\n";
                client.getOutputStream().write(
                        connect.getBytes(StandardCharsets.US_ASCII));
                String status = readHeaders(client.getInputStream())
                        .split("\r\n", 2)[0];
                System.out.println("Proxy reply: " + status);
                client.getOutputStream().write(
                        "PING".getBytes(StandardCharsets.US_ASCII));
                client.shutdownOutput();
                String reply = new String(
                        client.getInputStream().readNBytes(4),
                        StandardCharsets.US_ASCII);
                System.out.println("Tunnel reply: " + reply);
            }
            System.out.println("Origin received: " +
                    originTask.get(5, TimeUnit.SECONDS));
            System.out.println("Valid CONNECT seen: " +
                    proxyTask.get(5, TimeUnit.SECONDS).startsWith(
                            "CONNECT 127.0.0.1:"));
        } finally {
            workers.shutdownNow();
        }
    }
}
~~~

Compile with the Java 17+ API:

~~~bash
javac --release 17 -encoding UTF-8 HttpConnectEchoDemo.java
java HttpConnectEchoDemo
~~~

**Stdout compiled and run on OpenJDK 24 with `--release 17`:**

~~~text
Proxy reply: HTTP/1.1 200 Connection Established
Tunnel reply: PONG
Origin received: PING
Valid CONNECT seen: true
~~~

### 7.2. Code explanation

- `ServerSocket origin` represents the TCP endpoint, listening only on loopback with an OS-chosen port.
- `ServerSocket proxy` represents a minimal HTTP proxy, also listening only on loopback.
- `readHeaders(...)` reads **exactly up to CRLF CRLF**, with a 4096-byte limit to avoid an unbounded header in the demo. Because it reads byte-by-byte, it **does not accidentally read ahead tunnel bytes** into a buffer when switching modes.
- The proxy checks the request line **against the demo's own target whitelist**; if the target is wrong, it returns 403 and does not connect to any other server. Blocking arbitrary CONNECT destinations is a practical security principle.
- Once the origin connection is established, the proxy sends `HTTP/1.1 200 Connection Established` and then runs `transferTo` on streams in **both directions**.
- After reading the 200 headers, the client **does not send another HTTP request to the proxy**. It sends raw `PING`; the origin returns `PONG`.
- `client.shutdownOutput()` is a client-side **TCP half-close** operation, signaling the end of the send direction while still allowing reads on the receive direction.
- The client→origin relay thread calls `outgoing.shutdownOutput()` after EOF, letting the origin know the client has finished sending. The origin→client direction continues to be relayed independently.
- The server/proxy uses try-with-resources and `ExecutorService.shutdownNow()` to clean up demo resources.

**Limitations:** this is a minimal proxy that accepts **only one CONNECT to the port created by the application itself**; it does not implement an RFC-complete HTTP parser, proxy authentication, production logging, TLS, comprehensive request limits, multi-socket forwarding lifecycle, rate limits, DNS policy, or graceful shutdown. **Do not deploy it as a public proxy on the Internet.** It exists to teach switching from HTTP control to byte-tunneling and must only be run on loopback.

## 8. Java 17+ Program #2: real HTTPS through an HTTP CONNECT proxy

The second example uses `java.net.http.HttpClient` itself to access **a local HTTPS origin** through **a local HTTP CONNECT proxy**. Unlike the previous example, the client performs **a real TLS handshake and certificate/hostname validation**.

Components:

- `HttpsServer` from the standard `jdk.httpserver` module acts as the **HTTPS origin**, bound to `127.0.0.1` on an ephemeral port.
- `ServerSocket` acts as a minimal **HTTP CONNECT proxy**, opening a tunnel only to the exact known origin/port.
- `HttpClient` with `ProxySelector.of(...)` pointing to the proxy.
- Client `SSLContext` initialized from a **truststore containing the test certificate** to authenticate the local server. **No trust-all `X509TrustManager`, no disabling hostname verification.**
- A **temporary, self-signed certificate for `localhost`**, with a matching Subject Alternative Name, generated with `keytool` for testing only.
- The 200 response and body `secure-ok` are the **origin response after TLS**, while the proxy observed the CONNECT.

### 8.1. Preparing the test keystore/truststore

**Requirements:** JDK 17+ with the `keytool` command, a shell in a dedicated test directory that you own. Create a new certificate, with a SAN for `localhost`, valid for 2 days, and use it only with loopback:

~~~bash
keytool -genkeypair -alias origin -keyalg RSA -keysize 2048 -storetype PKCS12 -keystore origin.p12 -storepass changeit -keypass changeit -dname "CN=localhost" -ext "SAN=dns:localhost,ip:127.0.0.1" -validity 2 -noprompt
keytool -exportcert -alias origin -keystore origin.p12 -storepass changeit -rfc -file origin.pem
keytool -importcert -alias origin -file origin.pem -storetype PKCS12 -keystore trust.p12 -storepass changeit -noprompt
~~~

**Security:** `changeit` here is a **fixed password for temporary test files, never to be used in production**. Do not commit `origin.p12` (which contains the private key) to Git, do not upload it to the Internet, and do not import the test certificate into the system or global JDK truststore. After the lab, delete `origin.p12`, `origin.pem`, and `trust.p12` from the test directory. A self-signed certificate will not be trusted by the JVM if you **do not** provide the dedicated test truststore — that is the correct security behavior.

### 8.2. File `HttpsThroughConnectProxyDemo.java`

~~~java
import com.sun.net.httpserver.HttpsServer;
import com.sun.net.httpserver.HttpsConfigurator;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ProxySelector;
import java.net.Socket;
import java.net.ServerSocket;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.SecureRandom;
import java.time.Duration;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;

public class HttpsThroughConnectProxyDemo {
    private static String readHeaders(InputStream input) throws IOException {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        int state = 0;
        while (output.size() < 8192) {
            int b = input.read();
            if (b < 0) throw new IOException("Unexpected EOF in proxy headers");
            output.write(b);
            state = switch (state) {
                case 0 -> b == '\r' ? 1 : 0;
                case 1 -> b == '\n' ? 2 : b == '\r' ? 1 : 0;
                case 2 -> b == '\r' ? 3 : 0;
                default -> b == '\n' ? 4 : b == '\r' ? 1 : 0;
            };
            if (state == 4) {
                return output.toString(StandardCharsets.US_ASCII);
            }
        }
        throw new IOException("Proxy header exceeded limit");
    }

    private static SSLContext serverTls(Path store) throws Exception {
        KeyStore ks = KeyStore.getInstance("PKCS12");
        try (InputStream stream = Files.newInputStream(store)) {
            ks.load(stream, "changeit".toCharArray());
        }
        KeyManagerFactory kmf = KeyManagerFactory.getInstance(
                KeyManagerFactory.getDefaultAlgorithm());
        kmf.init(ks, "changeit".toCharArray());
        SSLContext context = SSLContext.getInstance("TLS");
        context.init(kmf.getKeyManagers(), null, new SecureRandom());
        return context;
    }

    private static SSLContext clientTls(Path trust) throws Exception {
        KeyStore ks = KeyStore.getInstance("PKCS12");
        try (InputStream stream = Files.newInputStream(trust)) {
            ks.load(stream, "changeit".toCharArray());
        }
        TrustManagerFactory tmf = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());
        tmf.init(ks);
        SSLContext context = SSLContext.getInstance("TLS");
        context.init(null, tmf.getTrustManagers(), new SecureRandom());
        return context;
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) throw new IllegalArgumentException(
                "Usage: java HttpsThroughConnectProxyDemo origin.p12 trust.p12");

        InetAddress loopback = InetAddress.getByName("127.0.0.1");
        HttpsServer origin = HttpsServer.create(
                new InetSocketAddress(loopback, 0), 0);
        origin.setHttpsConfigurator(new HttpsConfigurator(
                serverTls(Path.of(args[0]))));

        origin.createContext("/secret", exchange -> {
            try (exchange) {
                byte[] content = "secure-ok".getBytes(StandardCharsets.UTF_8);
                exchange.getResponseHeaders().set("Content-Type", "text/plain");
                exchange.getResponseHeaders().set("Connection", "close");
                exchange.sendResponseHeaders(200, content.length);
                exchange.getResponseBody().write(content);
            }
        });

        ExecutorService workers = Executors.newFixedThreadPool(2);
        try (ServerSocket proxy = new ServerSocket(0, 1, loopback)) {
            proxy.setSoTimeout(10000);
            origin.start();
            Future<String> connectLine = workers.submit(() -> {
                try (Socket incoming = proxy.accept()) {
                    incoming.setSoTimeout(10000);
                    String headers = readHeaders(incoming.getInputStream());
                    String line = headers.split("\r\n", 2)[0];
                    String expected = "CONNECT localhost:" +
                            origin.getAddress().getPort() + " HTTP/1.1";

                    if (!line.equals(expected)) {
                        incoming.getOutputStream().write(
                                "HTTP/1.1 403 Forbidden\r\n\r\n".getBytes(
                                        StandardCharsets.US_ASCII));
                        return line;
                    }

                    try (Socket upstream = new Socket(
                            loopback, origin.getAddress().getPort())) {
                        upstream.setSoTimeout(10000);
                        incoming.getOutputStream().write(
                                "HTTP/1.1 200 Connection Established\r\n\r\n"
                                        .getBytes(StandardCharsets.US_ASCII));

                        Future<?> up = workers.submit(() -> {
                            try {
                                incoming.getInputStream()
                                        .transferTo(upstream.getOutputStream());
                            } catch (IOException e) {
                                // Expected when the short demonstration closes.
                            }
                        });

                        upstream.getInputStream().transferTo(
                                incoming.getOutputStream());
                        up.get(10, TimeUnit.SECONDS);
                    }
                    return line;
                }
            });

            HttpClient client = HttpClient.newBuilder()
                    .proxy(ProxySelector.of(new InetSocketAddress(
                            loopback, proxy.getLocalPort())))
                    .sslContext(clientTls(Path.of(args[1])))
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(5))
                    .build();

            URI uri = URI.create("https://localhost:" +
                    origin.getAddress().getPort() + "/secret");
            HttpRequest request = HttpRequest.newBuilder(uri)
                    .timeout(Duration.ofSeconds(8))
                    .GET()
                    .build();

            HttpResponse<String> response = client.send(
                    request, HttpResponse.BodyHandlers.ofString());

            System.out.println("HTTPS status: " + response.statusCode());
            System.out.println("HTTPS body: " + response.body());
            System.out.println("Protocol: " + response.version());

            origin.stop(0);
            System.out.println("CONNECT observed: " + connectLine
                    .get(10, TimeUnit.SECONDS).startsWith(
                            "CONNECT localhost:"));
        } finally {
            origin.stop(0);
            workers.shutdownNow();
        }
    }
}
~~~

### 8.3. Compile, run, verified output

Run in **the same directory** where `origin.p12` and `trust.p12` were just created:

~~~bash
javac --release 17 -encoding UTF-8 --add-modules jdk.httpserver HttpsThroughConnectProxyDemo.java
java --add-modules jdk.httpserver HttpsThroughConnectProxyDemo origin.p12 trust.p12
~~~

**Stdout verified on OpenJDK 24, code compiled with `--release 17` compatibility:**

~~~text
HTTPS status: 200
HTTPS body: secure-ok
Protocol: HTTP_1_1
CONNECT observed: true
~~~

Messages from `keytool` when creating/trusting the certificate depend on the machine's locale and are not Java application stdout. Because the port is chosen by the OS, the program prints a boolean confirming the `CONNECT localhost:...` request instead of printing a fixed port.

### 8.4. Phase-by-phase breakdown

1. `HttpsServer` accepts HTTPS on `127.0.0.1`, on an OS-chosen port. The URL hostname is **`localhost`**, and the certificate has **SAN dns:localhost**; the Java client trusts the certificate from `trust.p12` and performs normal hostname verification.
2. The `ServerSocket` proxy accepts only **one CONNECT** and matches the exact target. This is not an open proxy.
3. `HttpClient.Builder.proxy(ProxySelector.of(...))` requests using the local HTTP proxy. The Java library automatically generates `CONNECT localhost:<port>` because the target URI is `https://localhost:<port>/secret`.
4. The proxy receives CONNECT, **only opens TCP** to the local HTTPS server, and then returns `200 Connection Established`.
5. The Java client initiates the **TLS handshake through the tunnel**. The proxy does not install a server certificate as a CA and does not decrypt the HTTP payload.
6. The Java client performs GET `/secret` over the HTTPS connection. The origin sends the body `secure-ok`.
7. `HttpResponse.statusCode()==200` is the **origin HTTP status**. `HttpResponse.version()==HTTP_1_1` is because the example forces HTTP/1.1 for stable output; it does **not** indicate the proxy CONNECT status.
8. `CONNECT observed: true` confirms the proxy saw the CONNECT line. With a real proxy, the request usually also includes headers and authentication policy; the lab only needs to check the line.
9. `origin.stop(0)` and `workers.shutdownNow()` shut down the local services after the exchange. In a long-running deployment, you must properly manage connection pools/tunnels, graceful drain, futures, exceptions, and timeouts.

**Security boundary:** the demo uses a self-signed certificate but **does not skip certificate verification**; it trusts a **specific test CA/certificate imported into `trust.p12`**, without affecting the system truststore. Do not copy `changeit` or a "trust any certificate" mindset into production.

**Proxy demo limitations:** `readHeaders` is not a complete HTTP parser and does not handle multiple concurrent CONNECTs, authentication retries, sophisticated partial shutdown, DoS mitigations, multi-layer header limits, or HTTP/2 CONNECT mapping. `SocketTimeout` here only keeps the test from hanging indefinitely. **Do not use this code as a production proxy.**

## 9. Common failures in the CONNECT/TLS lifecycle

An HTTPS request through a proxy has **multiple independent failure points**.

~~~text
(1) Resolve/connect to proxy
        |-- Proxy DNS fail / ConnectException / timeout
        v
(2) CONNECT to origin host:port
        |-- 400 malformed target
        |-- 403 policy denied
        |-- 407 proxy auth required
        |-- 502/504 proxy cannot connect upstream
        v
(3) CONNECT 2xx, tunnel ready
        |-- origin TCP reset / proxy relay timeout
        v
(4) TLS handshake inside tunnel
        |-- untrusted certificate / wrong hostname / TLS mismatch
        v
(5) HTTPS request/response at origin
        |-- 401/403/404/429/500/503 at HTTP application layer
        v
(6) Drain/close response/tunnel per lifecycle
~~~

| Symptom | Primarily responsible layer | Diagnostic direction |
| --- | --- | --- |
| Cannot resolve proxy hostname | Proxy DNS | Check proxy name, resolver, VPN, network |
| TCP connect to proxy refused | Client→proxy transport | Host/port/listener/firewall |
| Proxy returns 400 for CONNECT | Proxy control HTTP | Authority-form, host:port, header syntax |
| Proxy returns 403 | Proxy policy | ACL, disallowed target/port, deny list |
| Proxy returns 407 | Proxy authentication | `Proxy-Authenticate`, `Authenticator`, disabled scheme, credentials |
| Proxy returns 502 | Proxy upstream hop | Proxy cannot connect to origin; check DNS/firewall/origin |
| Proxy returns 504 | Proxy upstream timeout | Upstream/connect/relay deadline |
| Proxy returns 200, then `SSLHandshakeException` | Client↔HTTPS origin TLS | Certificate SAN/chain, TLS versions, truststore, inspection |
| TLS succeeds but HTTPS GET returns 404 | HTTP application at origin | URI/route/authorization/caching |
| 200 CONNECT but real request body never arrives | Tunnel/flow control/timeout | Bidirectional relay, half-close, backpressure, socket lifetimes |
| `HttpClient.send` times out even though proxy connected | Multiple possible steps | Distinguish connect/TLS/request/response phases via trace |
| Fails only on corporate network | Proxy/PAC/auth/SSL inspection | Compare routes, certs, ALPN, and policies |
| Proxy sees right target but client receives another domain's certificate | TLS identity / route | Do not bypass verification; fix route/trust legitimately |

**Do not** attribute every error to "HTTP CONNECT failed." For example, an `SSLHandshakeException` after CONNECT 200 is a failure at the **TLS step**, not the proxy rejecting CONNECT. Conversely, a proxy 407 happens **before** the end-to-end origin handshake.

### 9.1. 407 vs. 401

- `407 Proxy Authentication Required` is the **proxy** requesting authentication (usually before the tunnel).
- `401 Unauthorized` from the HTTPS origin is the **origin application** requesting authentication for the resource (after tunnel/TLS).
- `Proxy-Authenticate` and `Proxy-Authorization` belong to the proxy-auth exchange; `WWW-Authenticate` and `Authorization` usually belong to the origin-auth exchange.
- Do not put proxy credentials into the origin's `Authorization` or vice versa.
- Do not log raw `Proxy-Authorization` or tokens, as secrets can leak via logs/telemetry.

### 9.2. TLS truststore and interception

If a system uses intentional TLS interception, the client may see a certificate issued by a corporate CA for the target. This is only valid when the enterprise has appropriate policies and certificate trust. **Do not** patch Java with a trust-all manager or disable hostname verification; that masks security incidents and can allow malicious MITM.

For local testing, use an `SSLContext` with a dedicated test truststore. For production, prefer an organization-approved truststore/PKI; if a proxy CA must be installed, understand **who can decrypt traffic** and what data is sensitive.

### 9.3. Timeouts and retries must be split by phase

- **Proxy TCP connect timeout**: time to reach proxy host:port; do not wait indefinitely.
- **CONNECT response timeout**: the proxy may be resolving or establishing the origin hop; an overall request deadline is needed.
- **TLS handshake timeout**: the proxy tunnel is created, but the origin handshake may be slow or filtered; identify the true cause.
- **Origin response deadline**: the application processing the request may be slow; a 200 CONNECT status is not proof the origin GET is done.
- **Idle/read timeout**: a long-lived tunnel with no bytes; manage according to policy.
- **Cancellation**: close resources/cancel futures and accept that the proxy/origin may still have received part of the data.

**Do not retry a payment POST just because CONNECT/TLS timed out or the socket was reset** without knowing whether the request reached the origin. Depending on the failure point, the request may not have been sent yet or may already have been executed by the origin with the response lost. Use idempotency keys/operation IDs and business policy instead of blind retries.

## 10. What can the proxy see in the tunnel?

| Data | Can a regular forwarding HTTP proxy know it? | Notes |
| --- | --- | --- |
| Proxy client IP and proxy TCP port | Yes | It directly accepts the connection from the client |
| CONNECT target `hostname:port` | Yes | Sent before origin TLS so the proxy knows where to connect |
| Origin IP the proxy connects to | Yes | The proxy opens the upstream TCP connection |
| Timing, byte count, connection close/reset | Yes | Traffic metadata |
| TLS ClientHello metadata / SNI | Observable in many cases | ECH can change exposure; do not assume the TLS handshake is completely hidden |
| URL path `/private/orders` of the HTTPS request | Normally **no** | Inside the TLS HTTP message; exception is intentional TLS interception |
| HTTP `Authorization` header sent to origin | Normally **no** | Sent inside origin TLS |
| HTTPS request body / response JSON | Normally **no** | Readable if the proxy intercepts/terminates TLS |
| Proxy credentials in `Proxy-Authorization` | Yes | Sent to the proxy before the tunnel; risky if the hop is cleartext |
| TLS certificate chain and hostname identity | Client verifies; proxy may observe partial metadata | Certificate/handshake visibility varies by TLS version/configuration |

**Do not call CONNECT a VPN or absolute anonymity.** A tunnel enables transporting bytes through a proxy; it does not hide the origin hostname/port, client identity, or traffic metadata. Content protection depends on **end-to-end TLS and certificate validation**.

## 11. CONNECT to the right port: safe for whom?

A proxy that allows clients to arbitrarily send `CONNECT host:anyPort` can be abused to reach non-web services, scan internal systems, or relay spam. RFC 9110 explicitly warns against CONNECT to **SMTP port 25** because it can be used as a spam relay.

A **production proxy** should:

1. Restrict **destinations and ports** via allowlist/policy (for example, 443 only when appropriate; do not allow all ports by default).
2. Authenticate/authorize who can create tunnels; enforce policy by user/group/tenant.
3. Validate DNS answers/routes after resolution, preventing **DNS rebinding/SSRF** and connections to private/loopback/link-local/metadata IPs unless permitted.
4. Optionally forbid IP literals or require a special allowlist; handle IPv4, IPv6, and IDN/punycode consistently.
5. Prevent users from bypassing policy via host aliases, changing hostnames, alternate numeric IP representations, or redirects/chained proxies.
6. Limit concurrent connections, bytes, tunnel creation rate, idle timeout, and max lifetime.
7. Log at minimum **principal, target policy decision, status/latency**; avoid logging passwords or payloads.
8. Protect the proxy listener (network ACL/firewall); do not run an open proxy on the Internet.
9. Apply client→proxy TLS when sending sensitive credentials or metadata over untrusted networks and when the stack supports it.
10. Clearly define responsibility for **closing both directions** when one end disconnects; avoid leaking sockets/file descriptors.
11. Never treat "tunnel" itself as protocol security: endpoint TLS validation, application policy, and proper auditing are still required.

**SSRF risk:** if an application lets users supply arbitrary URIs/proxy targets, the application can become a bridge to internal services through the proxy. Simply checking `host.endsWith(".trusted.com")` is insufficient without canonicalizing, resolving, checking IPs, and preventing rename loops. Use an approved policy rather than rolling your own security network parser in a lab exercise.

## 12. Is HTTP/2 CONNECT identical to HTTP/1.1 CONNECT?

**CONNECT semantics** belong to HTTP in general, but the wire representation differs by version:

- **HTTP/1.1:** request line `CONNECT host:port HTTP/1.1`, proxy 2xx, and after the header terminator that entire **TCP connection** becomes a byte tunnel.
- **HTTP/2:** CONNECT is represented by a single request stream using pseudo-headers such as `:method = CONNECT` and `:authority = host:port`; after 2xx, **DATA frames of that stream** carry the tunnel bytes. Other HTTP/2 streams can still operate on the same underlying connection.
- **Extended CONNECT** (for example, used for WebSockets over HTTP/2) has additional semantics and should not be equated with a regular TCP tunnel CONNECT.
- **HTTP/3:** has a corresponding CONNECT mapping over QUIC streams/extensions, not a plaintext `CONNECT host:port HTTP/1.1` on a UDP datagram.

Java 17 `HttpClient` supports HTTP/1.1 and HTTP/2 for **application HTTP** per the API; that does **not** automatically mean the proxy control CONNECT hop will always be HTTP/2. The two sides may use HTTP/1.1 for the proxy tunnel and HTTP/2 for the HTTPS origin inside TLS.

For the lab, both examples intentionally use **HTTP/1.1 CONNECT** so plaintext bytes can be observed clearly; the TLS example chooses `HttpClient.Version.HTTP_1_1` for the inner HTTPS response. In production, you must check the capabilities of the proxy, JDK, origin, and how the hops negotiate.

## 13. Configuring and observing proxies in Java

### 13.1. Where does the proxy come from?

There are two common ways:

- **Explicit proxy:** set `HttpClient.Builder.proxy(ProxySelector.of(proxyAddress))` for a specific client.
- **Default proxy selection:** let `HttpClient` use the JDK/OS default selector via system properties and environment configuration. Per Java 17 documentation, these include `http.proxyHost`, `http.proxyPort`, `https.proxyHost`, `https.proxyPort`, `http.nonProxyHosts`, and `java.net.useSystemProxies` (depending on runtime/handler).

**Note:** the name `https.proxyHost` in system properties does **not** automatically mean the proxy endpoint is HTTPS/TLS. It is usually the proxy configuration used to reach **HTTPS URLs**; distinguish this from a separate HTTP proxy endpoint running TLS. `http.nonProxyHosts` also defaults to including localhost patterns in some handlers; the demo uses an **explicit `ProxySelector.of`** so it verified the CONNECT request to the local proxy instead of accidentally bypassing it.

Do not mutate JVM-wide system properties just to apply a proxy to one client when an explicit builder can be configured. If an `HttpClient` has already been created, changing `ProxySelector.getDefault()` may not affect the existing instance.

### 13.2. Basic authentication is disabled by default for tunneling

Oracle Java 17 Networking System Properties documents that `jdk.http.auth.tunneling.disabledSchemes` defaults to **`Basic`**. This is designed to reduce the risk of credential exposure. If a proxy only supports Basic, a Java `HttpClient` with an `Authenticator` can still hit 407 because the scheme is blocked.

**Resolution approach:** ask the proxy administrator about the official scheme/endpoint, use a protected proxy transport if available, configure valid auth according to organizational policy, and test in staging. Do not treat lowering security settings as the first solution.

### 13.3. Reading the origin result without confusing it with the CONNECT result

~~~java
HttpResponse<String> response = client.send(
        request, HttpResponse.BodyHandlers.ofString());

System.out.println(response.statusCode()); // Origin HTTP status
System.out.println(response.version());    // Actual HTTP version of the response
System.out.println(response.uri());        // Final origin URI (may have redirected)
~~~

This is a **code snippet** assuming an existing `client`/`request`. `HttpResponse.version()` represents the actual HTTP version received for the application response, not necessarily the "proxy protocol." If you need to diagnose CONNECT 407/200 or ALPN, use safe logging/debugging on the network/proxy stack you own, without assuming the public `HttpResponse` exposes a separate object for the CONNECT handshake.

### 13.4. Do not put raw proxy passwords in source code

If you must implement proxy credential support:

- Move credentials into a secret manager or environment authentication mechanism; do not commit them to source.
- Do not print `Proxy-Authorization`, password chars, or secret tokens to logs.
- Restrict `Authenticator` to return credentials only for the exact proxy/port/realm; do not hand them out to arbitrary hosts.
- Verify that the scheme is supported by the JDK and not disabled by `disabledSchemes`.
- Use an encrypted proxy hop when appropriate and supported; Basic over cleartext carries risk.
- When encountering 407, distinguish a proxy challenge from an origin 401; do not change the origin's `Authorization` header to "fix the proxy."

## 14. Mistakes to avoid

| Mistake | Consequence | How to understand/fix |
| --- | --- | --- |
| Sending `GET https://origin/path` via a proxy and assuming TLS appears automatically | Wrong semantics if proxy/client does not create a tunnel | HTTPS via an HTTP proxy normally requires CONNECT and TLS after 2xx |
| Using `CONNECT https://origin/path` | Invalid request-target | Use `CONNECT origin:443` authority-form |
| Omitting the port from `CONNECT origin` | Request-target syntax violation | Port is required, even for default ports |
| Thinking `200 Connection Established` is the GET response | Confusing proxy control with origin HTTP | TLS then the origin response is the GET result |
| Sending plaintext `GET /path` right after CONNECT 2xx to a TLS origin | Origin expects TLS handshake, causing protocol error | Client performs TLS first |
| Assuming CONNECT 2xx means TLS is valid | `SSLHandshakeException` may still follow | Check hostname/certificate chain |
| Thinking an HTTP/1.1 proxy hop blocks origin HTTP/2 | The two protocols are at different layers | Origin TLS ALPN can still select h2 |
| Treating a proxy tunnel as an anonymous VPN | Exposes CONNECT target/IP/metadata | TLS protects content, but metadata remains visible |
| Believing a proxy can never see the HTTP body | TLS interception is an important exception | Determine the trust model |
| Sending proxy password with Basic over a plaintext network | Credentials exposed | Proxy transport/auth security |
| Allowing arbitrary `host:port` | Open proxy/SSRF/spam relay | Allowlist, ACL, DNS/IP checks |
| Not cleaning up both ends of the connection when a peer disconnects | File descriptor leak | Half-close/EOF/close on both sides |
| Using `readAllBytes()` on an unbounded tunnel stream | May hang/OOM | Forwarding/backpressure and timeouts |
| Reading CONNECT headers with `BufferedReader` and handing off the stream with prefetched data | Can swallow the first bytes of the TLS handshake | HTTP parser handles boundaries accurately; demo reads byte-by-byte |
| Writing a proxy from the demo and exposing it to the public Internet | Lacks auth, parsing, rate limits, security logging | Use a maintained/supported proxy |
| Seeing `407` and changing `Authorization` for the origin | Confusing identity domains | `Proxy-Authorization`/`Authenticator` |
| Disabling TLS certificate validation when handshake fails | Opens the door to MITM | Fix truststore/SAN/routes per policy |
| Thinking `https.proxyHost` definitely means a TLS proxy | Confusing HTTPS destination with proxy scheme | Check actual proxy capability |
| Resending a POST request after a timeout without checking idempotency | May cause duplicate transactions | Idempotency key / operation status |
| Thinking the proxy receives the full HTTPS URI path | The path is inside end-to-end TLS | A normal proxy sees the CONNECT authority, not the path |
| Treating `ProxySelector.of` as a SOCKS handshake | HTTP client/proxy behavior differs from SOCKS | Use the appropriate API/provider |
| Assuming a CONNECT proxy only returns 200 on success | RFC defines any 2xx | Handle per HTTP CONNECT semantics |
| Sending `Content-Length` in a 2xx CONNECT reply | Violates RFC 9110/9112 | Proxy must not send it |
| Treating `Content-Length` on a CONNECT 2xx as the TLS byte count | Tunnel is not framed as an HTTP body | Ignore this field in 2xx |
| Equating an HTTPS proxy with an HTTPS origin | Two different TLS segments | Distinguish client–proxy TLS and client–origin TLS |

## 15. CONNECT/HTTPS proxy test matrix

| Test | Setup | Expected result to verify |
| --- | --- | --- |
| CONNECT to local allowed target | Proxy has exact origin/port allowlist | 2xx response then byte relay |
| CONNECT to wrong target | Proxy only allows known host:port | 403/no upstream connection |
| CONNECT syntax missing port | Raw client sends invalid target | 400/deny per policy |
| Proxy requires auth | Returns 407 + `Proxy-Authenticate` | Client does not open tunnel without auth |
| Auth scheme disabled | JDK defaults to Basic tunneling disabled | Does not send Basic outside policy; clear error reported |
| Proxy cannot resolve origin | DNS fails upstream | 502/504 or corresponding proxy error |
| Proxy opens TCP to origin but origin TLS is not ready | CONNECT 2xx, TLS fails | Distinguish CONNECT success from handshake failure |
| HTTPS origin with trusted test cert | Custom client `SSLContext` truststore | TLS passes, origin HTTP response |
| HTTPS origin untrusted cert | Use default truststore | Handshake fails, **do not** bypass TLS |
| Certificate SAN wrong hostname | URI `https://localhost` but wrong cert | Hostname validation fails |
| End-to-end proxy tunnel | Log only CONNECT line + timing | Does not parse plaintext origin GET |
| Inner HTTP/1.1 | `client.version(HTTP_1_1)` | `response.version()==HTTP_1_1` |
| Inner HTTP/2 | Origin TLS/ALPN supports h2 | `response.version()==HTTP_2` if actually negotiated |
| Proxy with org-approved TLS interception | Corporate CA is trusted | Audit the exact entity performing decryption |
| CONNECT to port 25 | Port allowlist is 443 only | Denied, preventing SMTP relay abuse |
| IPv6 target | `CONNECT [2001:db8::10]:443` | Bracketed authority/port |
| HTTPS redirect across origins | `followRedirects` policy enabled | CONNECT/tunnel to new origin if needed, preserving security |
| Half-close/EOF | Client `shutdownOutput` in echo demo | Proxy forwards remaining return data then closes |
| Timeout/connection cancellation | Slow/blackholed origin in staging | No leaked sockets, failure phase distinguished |
| Many concurrent tunnels | Production proxy with resource budgets | No starvation/OOM/file-descriptor exhaustion |

**Do not** run intentional failure tests against organizational proxies or external hosts without permission. Set up a local/staging proxy and server that you own, with explicit port restrictions.

## 16. Exercises with solutions

### Exercise 1 — Where is CONNECT sent?

A Java client wants to fetch `https://api.example.com/v1/data` via HTTP proxy `proxy.local:3128`. Who does it open TCP to first, and what request does it send?

**Answer:** The client opens TCP to **`proxy.local:3128`** and sends **`CONNECT api.example.com:443 HTTP/1.1`** to the proxy (with appropriate headers such as Host). It does not send the GET path at this stage.

### Exercise 2 — Why is there no path in CONNECT?

**Answer:** CONNECT authority-form uses **host:port** to request a TCP tunnel. The path/query of the HTTPS resource belongs to the HTTP request **after the TLS handshake** to the origin, not the CONNECT target.

### Exercise 3 — Which 200 belongs to whom?

The proxy returns `HTTP/1.1 200 Connection Established`, and after TLS the origin returns `HTTP/1.1 404 Not Found`. What is `HttpResponse.statusCode()` for the Java GET request typically?

**Answer:** `404`, because that is the **origin's HTTP response** to the GET; CONNECT 200 is only the control response for the tunnel.

### Exercise 4 — How do 407 and 401 differ?

**Answer:** `407` requests **proxy authentication** and occurs before or during tunnel establishment. `401` from the HTTPS origin requests **origin/application authentication** after TLS. The corresponding headers are `Proxy-Authenticate/Proxy-Authorization` and `WWW-Authenticate/Authorization`.

### Exercise 5 — Is CONNECT 200 already secure?

The proxy reports CONNECT 200, but Java throws `SSLHandshakeException` when calling the HTTPS URL. Could the tunnel have been created? Should certificate checks be disabled?

**Answer:** The tunnel **may have been created successfully**, but TLS identity/trust failed. **Do not** disable certificate/hostname verification; check the truststore, SAN, TLS/certificate chain, and appropriate route.

### Exercise 6 — HTTP/2 inside HTTP/1.1 CONNECT

The proxy creates CONNECT using HTTP/1.1. Can the inner HTTPS response be HTTP/2?

**Answer:** **Yes**, if the client/origin negotiate ALPN `h2` over TLS inside the tunnel and support it. The proxy control hop version does not have to match the inner HTTPS version.

### Exercise 7 — Can the proxy read `/private`?

With a blind byte-forwarding proxy and end-to-end TLS to the origin, can the proxy read the `/private` path, headers, and body of the GET?

**Answer:** Normally **no**; they are inside TLS encryption. The proxy still knows the CONNECT host:port, upstream IP, and traffic metadata, and can often observe part of the TLS handshake (such as SNI without ECH). TLS interception with a trusted CA is a different case.

### Exercise 8 — Proxy password and Basic

A Java 17 `Authenticator` is installed, but the proxy only returns `407 Basic` and the client cannot create the tunnel. Explain one possible configuration cause?

**Answer:** `jdk.http.auth.tunneling.disabledSchemes` contains `Basic` by default; Java may not use Basic for HTTPS tunneling even with an `Authenticator`. Work with the proxy/security team to choose a protected auth scheme/hop instead of hastily unblocking Basic.

### Exercise 9 — Port 25 risk

Why do proxies usually reject `CONNECT mail.example:25` even when allowing `CONNECT api.example:443`?

**Answer:** Arbitrary TCP tunnels can be abused as relays to SMTP or internal services. RFC 9110 recommends restricting safe ports/destinations to prevent abuse/open proxies.

### Exercise 10 — Does raw PING/PONG prove HTTPS?

**Answer:** No. It proves **byte forwarding** through the tunnel. HTTPS also requires **TLS handshake, certificate/hostname verification**, and HTTP request/response inside TLS as in the second demo.

### Exercise 11 — Proxy DNS and client DNS

Who usually resolves the origin hostname when Java sends CONNECT?

**Answer:** **The proxy usually** resolves/connects to the origin because it opens the upstream TCP connection. However, specific DNS behavior can vary by route/chain/implementation, so do not make an absolute statement for all clients.

### Exercise 12 — How to send GET after the tunnel?

After CONNECT 200, a client sends literal unencrypted text `GET /secret HTTP/1.1` onto the TCP tunnel leading to an HTTPS server. What is the result?

**Answer:** It will likely hit a TLS error/connection reset because the HTTPS origin expects a **TLS ClientHello first**, not a plaintext HTTP request. The HTTPS client library must establish a TLS session inside the tunnel before sending the encrypted HTTP request.

### Exercise 13 — Retry after timeout

A client sends a POST through a proxy, then loses the connection before reading the origin response. Is it safe to resend immediately?

**Answer:** You cannot conclude the origin has not processed it. You need an idempotency key, operation ID, or outcome check; a blind retry can create duplicate transactions.

### Exercise 14 — TLS interception policy

A corporate proxy replaces the origin certificate with a certificate issued by a trusted corporate CA while reading HTTPS content. Is it still a true "blind tunnel"?

**Answer:** Not at the end-to-end layer: the proxy has become a TLS intermediary that can decrypt, inspect, and re-encrypt. Permissions, compliance, CA trust, and data transparency must be audited. Do not assume every 200 CONNECT proxy is blind to content.

### Exercise 15 — Choosing an API

A Java 17 application wants to call an HTTPS REST API through an HTTP proxy. Should it manually write a `Socket`, send CONNECT, parse TLS, and then send GET?

**Answer:** **No** for normal cases. Use `HttpClient.Builder.proxy(ProxySelector.of(...))` and the Java TLS stack; only use raw sockets in a lab or a professionally maintained protocol implementation.

## 17. Implementation checklist

- [ ] Target URL is `https://...` when HTTPS security is required.
- [ ] Correct HTTP proxy host/port is configured on `HttpClient.Builder.proxy(...)` or a trusted proxy selector.
- [ ] Distinguish proxy TCP connect, CONNECT proxy control, origin TLS, and origin HTTP response.
- [ ] CONNECT uses authority-form `host:port`; port is required.
- [ ] Do not confuse proxy 200 CONNECT with origin GET/POST 200.
- [ ] After CONNECT 2xx, a TLS handshake and hostname/certificate verification must be performed.
- [ ] Do not disable TLS validation to bypass proxy errors.
- [ ] Proxy ACL restricts targets/destination ports; do not create an open proxy/SSRF gateway.
- [ ] Proper proxy authentication is in place; `407` differs from origin `401`.
- [ ] Know that `jdk.http.auth.tunneling.disabledSchemes` may disable Basic by default.
- [ ] Do not expose proxy credentials on a cleartext hop or in logs.
- [ ] Only use credentials from a secret manager/secure configuration.
- [ ] Distinguish `http.proxyHost`/`https.proxyHost` from a TLS proxy endpoint model.
- [ ] Observe actual response version and status instead of inferring from proxy CONNECT.
- [ ] Configure timeouts/deadlines for connect, CONNECT, TLS, request, and idle tunnel per policy.
- [ ] Implement graceful close/half-close/backpressure with no socket leaks.
- [ ] Do not build a public proxy from lab code.
- [ ] Do not retry POSTs with side effects without knowing whether the request was processed.
- [ ] Test certificate SAN/truststore, proxy bypass, direct/proxy routes, and redirects.
- [ ] Do not allow CONNECT to prohibited ports/services (for example, SMTP 25).
- [ ] Ensure monitoring does not log tokens/`Authorization` or sensitive payloads.
- [ ] Tested on the exact JDK/runtime and proxy policy of the deployment environment.

## 18. Official references

- [RFC 9110 `9.3.6 — CONNECT](https://www.rfc-editor.org/rfc/rfc9110#section-9.3.6): authority-form, required port, 2xx becomes tunnel, non-2xx no tunnel created, proxy restrictions, and security.
- [RFC 9112 `3.2.3 — authority-form](https://www.rfc-editor.org/rfc/rfc9112#section-3.2.3): HTTP/1.1 CONNECT request-target representation.
- [RFC 9112 `6.3 — Message body length](https://www.rfc-editor.org/rfc/rfc9112#section-6.3): 2xx CONNECT switches to tunnel immediately after headers, ignoring `Content-Length`/`Transfer-Encoding` in that case.
- [RFC 8441 — Bootstrapping WebSockets with HTTP/2](https://www.rfc-editor.org/rfc/rfc8441): extended CONNECT is a special mechanism distinct from regular TCP tunnel CONNECT.
- [RFC 9113 — HTTP/2](https://www.rfc-editor.org/rfc/rfc9113): HTTP/2 CONNECT on streams/pseudo-headers and multiplexing.
- [RFC 7301 — TLS ALPN](https://www.rfc-editor.org/rfc/rfc7301): application protocol selection during the TLS handshake.
- [Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): proxy, `SSLContext`, `send`, `sendAsync` APIs, and responses.
- [Java SE 17 — HttpClient.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Builder.html): `proxy(ProxySelector)`, `authenticator`, `sslContext`, timeout, and version.
- [Java SE 17 — ProxySelector](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ProxySelector.html): selecting proxy/direct by URI and `ProxySelector.of`.
- [Java SE 17 — Authenticator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Authenticator.html): proxy authentication and `RequestorType.PROXY`.
- [Java SE 17 — Java Networking / System Properties](https://docs.oracle.com/en/java/javase/17/core/java-networking.html): `http.proxyHost`, `https.proxyHost`, `http.nonProxyHosts`, and `jdk.http.auth.tunneling.disabledSchemes` defaulting to Basic.
- [Java SE 17 — HttpsServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpsServer.html): embedded HTTPS origin used in the lab.
- [Java SE 17 — SSLContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLContext.html): configuring TLS, KeyManagers, and TrustManagers.
- [Java SE 17 — KeyStore](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyStore.html): dedicated keystore/truststore for TLS testing.
- [Java SE 17 — HttpResponse](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.html): response status/body/version from the HTTP exchange after the tunnel.

**Conclusion:** When reaching an **HTTPS origin through an HTTP proxy**, `CONNECT origin:443` creates a **bidirectional TCP tunnel**; the proxy's 2xx response **only indicates that the tunnel succeeded**. The client must still complete the **TLS handshake and certificate/hostname validation**, and only then exchange the **actual HTTP request–response inside TLS**. Java 17 applications should use `HttpClient.Builder.proxy(ProxySelector.of(...))` so the library handles CONNECT and TLS automatically, while properly managing **proxy authentication, destination ACLs, timeouts, truststores, observability, and retry semantics**.
