# HTTP/3 from JDK 26: Versions, HttpOption, and Discovery Mechanisms

**Topic:** Java Advance - networking  
**Group:** HttpClient

Starting from **JDK 26**, the standard library **java.net.http.HttpClient** supports **HTTP/3** via **JEP 517**. This is an addition at the protocol layer, not a replacement for how HttpClient is written: applications still create an **HttpClient**, an **HttpRequest**, call **send()** or **sendAsync()**, and then read the **HttpResponse**. The key point to understand deeply is: **HTTP_3 is a preferred version**, while **HttpOption.H3_DISCOVERY** specifies the strategy for discovering/establishing the HTTP/3 path. The final outcome must be checked via **response.version()**; you must not infer from a preference setting that every request definitely runs over QUIC.

Core rules:

1. **HttpClient.Version.HTTP_3** is only available starting from **Java 26**.
2. **HttpOption<T>**, **HttpOption.H3_DISCOVERY**, **HttpOption.Http3DiscoveryMode**, and **HttpRequest.Builder.setOption(...)** are new APIs starting from Java 26.
3. **HttpClient still defaults to preferring HTTP/2**, even on JDK 26. Existing requests are not automatically switched to H3 when upgrading the JDK.
4. Setting **H3_DISCOVERY** alone **without selecting HTTP_3 on the client or request** causes the option to **have no effect**.
5. **ANY** is flexible and allows fallback; **ALT_SVC** learns H3 via HTTP Alternative Services; **HTTP_3_URI_ONLY** only attempts QUIC/H3 directly to the request URI's authority, with no fallback to H2/H1.
6. The built-in JDK 26 HttpClient only uses HTTP/3 for the **https** URI scheme and currently does not support **HTTP/3 through a proxy**.
7. HTTP 2xx/4xx/5xx codes are still application-layer responses; DNS, UDP path, TLS/QUIC, or timeout failures are transport/client errors and may not produce an HttpResponse.

This article includes **Java 26 code** illustrating the new APIs and **Java 17 code** compiled/run on JDK 24 to verify the difference between the preferred version and the actual version. Examples requiring JDK 26 are clearly marked with their environment requirements and do not claim to have been executed without JDK 26.

## 1. What Is HTTP/3 Actually?

Common HTTP/1.1 and HTTP/2 run over **TCP**. HTTPS uses TLS over TCP. HTTP/3, on the other hand, transports HTTP over **QUIC**, and QUIC runs over **UDP**. QUIC integrates **TLS 1.3** protection and provides stream multiplexing, flow control, congestion control, and packet loss recovery.

~~~text
HTTP/2                           HTTP/3
+-------------------+           +-------------------+
| HTTP semantics    |           | HTTP semantics    |
| request/response  |           | request/response  |
+-------------------+           +-------------------+
| H2 frames + HPACK |           | H3 frames + QPACK |
+-------------------+           +-------------------+
| TLS over TCP      |           | QUIC with TLS 1.3 |
+-------------------+           +-------------------+
| TCP               |           | UDP               |
+-------------------+           +-------------------+
| IP                |           | IP                |
+-------------------+           +-------------------+
~~~

| Aspect | HTTP/2 | HTTP/3 |
| --- | --- | --- |
| Transport | TCP byte stream | QUIC over UDP |
| Multiplexing | Multiple HTTP streams over one TCP connection | Multiple HTTP streams over one QUIC connection |
| Header compression | HPACK | QPACK |
| Packet loss | TCP head-of-line blocking can delay all H2 streams on the same connection | QUIC limits transport-level HOL **between** streams; still subject to loss/congestion |
| HTTPS encryption | TLS over TCP | TLS 1.3 within QUIC |
| Required infrastructure | TCP/TLS listener | QUIC listener, UDP path, appropriate TLS/ALPN |
| Benefits | Broad deployment ecosystem | Can reduce some latency and avoid TCP HOL cases |

**Do not assume HTTP/3 is guaranteed to be faster than HTTP/2.** On networks that block UDP, through an enterprise proxy, or against a service that has not enabled QUIC, trying HTTP/3 may spend time before falling back. On stable networks with good connection reuse, the performance difference may be small. You need to measure **latency, negotiated version, errors, and retries** under real workloads.

**HTTP semantics do not disappear:** URIs, GET/POST methods, 200/404/503 statuses, headers, caching, body, and business protocols still need to be handled properly. HTTP/3 does not replace authentication, idempotency keys, timeouts, or API design.

## 2. What New APIs Does JDK 26 Have?

| API | Role | Milestone |
| --- | --- | --- |
| **HttpClient.Version.HTTP_3** | Enum value to select HTTP/3 as the preferred version | Java 26 |
| **HttpOption<T>** | Sealed interface for request configuration hints | Java 26 |
| **HttpOption.H3_DISCOVERY** | Option configuring how to discover/establish H3 | Java 26 |
| **HttpOption.Http3DiscoveryMode.ANY** | Selects an implementation-specific strategy, may use direct QUIC and fallback | Java 26 |
| **HttpOption.Http3DiscoveryMode.ALT_SVC** | Uses only Alt-Svc to discover H3 | Java 26 |
| **HttpOption.Http3DiscoveryMode.HTTP_3_URI_ONLY** | Only tries H3 at the host/port from the URI, no Alt-Svc or fallback | Java 26 |
| **HttpRequest.Builder.setOption(option, value)** | Configures a hint for an individual request | Java 26 |
| **HttpRequest.getOption(option)** | Reads the hint stored on an HttpRequest | Java 26 |

Existing APIs **HttpClient.Builder.version(...)**, **HttpRequest.Builder.version(...)**, **HttpClient.send(...)**, **sendAsync(...)**, **HttpResponse.statusCode()**, and **HttpResponse.version()** retain their familiar model.

**There is no separate Http3Client class** in the standard JEP 517 API. In JDK 26, **HttpOption** is a sealed interface and only provides the **H3_DISCOVERY** option; you cannot create an arbitrary custom option and assume the built-in HttpClient understands it. **setOption** is a hint for the implementation to decide how to handle: with a non-built-in implementation, an unrecognized option may be ignored or cause an error per its contract.

### Four layers to distinguish

~~~text
HttpClient configuration
  preferred version: HTTP_2 (default) or HTTP_3
             │
             ▼
HttpRequest configuration
  optional preferred version: overrides client level
  optional H3_DISCOVERY: ANY / ALT_SVC / HTTP_3_URI_ONLY
             │
             ▼
Implementation + network
  cached connections, Alt-Svc, QUIC/UDP, TCP/TLS, proxy, timeout
             │
             ▼
HttpResponse.version()
  HTTP_3, HTTP_2, or HTTP_1_1 if the response succeeds
~~~

**Preferred version** is a preference, **discovery mode** is how the connection path is chosen, and **actual version** is the result. Do not conflate these three concepts into one.

## 3. Selecting HTTP_3 at the Client Level or Request Level

### Client level

~~~java
// Java 26+ snippet, import java.net.http.HttpClient.
HttpClient client = HttpClient.newBuilder()
        .version(HttpClient.Version.HTTP_3)
        .build();
~~~

Every request that does not set its own version inherits **HTTP_3 preferred** from the client. An HttpClient instance is typically reused to benefit from connection pools, known Alt-Svc information, and reduced connection setup overhead.

### Request level

~~~java
// Java 26+ snippet, import URI, HttpClient, and HttpRequest.
HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://service.example/health"))
        .version(HttpClient.Version.HTTP_3)
        .GET()
        .build();
~~~

This request prefers HTTP_3 even when the client is created with the default HTTP_2. Conversely, a request with **version(HTTP_2)** will override a client's **version(HTTP_3)** for that specific request.

| Client preference | Request preference | Effective preference for the request |
| --- | --- | --- |
| Not set (default HTTP_2) | Not set | HTTP_2 |
| HTTP_3 | Not set | HTTP_3 |
| HTTP_2 | HTTP_3 | HTTP_3 |
| HTTP_3 | HTTP_2 | HTTP_2 |
| HTTP_3 | HTTP_1_1 | HTTP_1_1 |

**Do not call HTTP_3 a hard requirement** when only setting version. The Javadoc clearly states that the actual version chosen depends on many conditions. With the built-in implementation, **H3_DISCOVERY=ANY** is the default strategy when HTTP_3 is selected; the outcome can be H3, H2, or H1.

### Checking the version

~~~java
// Snippet: client, request, and response already exist.
System.out.println(client.version());   // Preferred at client.
System.out.println(request.version());  // Optional preferred at request.
System.out.println(response.version()); // Actual version of the response.
~~~

**HttpRequest.version()** is an Optional and may be empty if the request did not set its own version. When empty, the client preference is used. **HttpResponse.version()** after a successful send is the actual evidence of which protocol the request/response ran on. Do not use **statusCode() == 200** as proof of HTTP/3, because HTTP/1.1, HTTP/2, and HTTP/3 can all return 200.

## 4. How Does HttpOption.H3_DISCOVERY Work?

**HttpOption.H3_DISCOVERY** has type **HttpOption<HttpOption.Http3DiscoveryMode>**. Set it on **HttpRequest.Builder** using the generic API:

~~~java
// Java 26+ snippet.
import java.net.http.HttpOption;
import java.net.http.HttpOption.Http3DiscoveryMode;

HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://service.example/api"))
        .version(HttpClient.Version.HTTP_3)
        .setOption(HttpOption.H3_DISCOVERY, Http3DiscoveryMode.ALT_SVC)
        .GET()
        .build();
~~~

**Crucial note:** If **neither** HttpClient nor HttpRequest selects **HTTP_3** as the preferred version, the **H3_DISCOVERY option is ignored**. The form below does **not** enable H3 with a default client:

~~~java
// Syntactically valid, but H3_DISCOVERY has no effect if
// the client also defaults to HTTP_2.
HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://service.example/"))
        .setOption(HttpOption.H3_DISCOVERY, Http3DiscoveryMode.ALT_SVC)
        .GET()
        .build();
~~~

**How to fix:** add **version(HttpClient.Version.HTTP_3)** on the request or client. Do not copy a snippet that only has **setOption** and conclude that the JDK does not support H3.

**An option is not an HTTP request header.** Do not do **header("H3_DISCOVERY", "ALT_SVC")** as a substitute; HTTP/3 discovery is a hint for the Java implementation, not content sent over HTTP. **getOption(HttpOption.H3_DISCOVERY)** returns an Optional of the configured hint; it does not prove a QUIC connection was opened.

With built-in Java 26, if HTTP_3 is selected and no H3_DISCOVERY hint is given, the default strategy is **ANY**. In the case of a redirect, the Javadoc states that the H3_DISCOVERY hint (if present) is carried over to the new request, though the path and actual version may still change depending on the URI/proxy.

## 5. Discovery Mode ANY: Flexible and Allows Fallback

**Http3DiscoveryMode.ANY** allows the implementation to discover or establish an appropriate HTTP path on its own. The built-in JDK **may**:

- Attempt an **HTTP/3 connection over QUIC/UDP** at the authority in the request URI.
- Simultaneously or on its own schedule attempt **HTTP/2 over TLS/TCP**, then choose the appropriate path.
- When the request explicitly sets **HTTP_3**, prioritize trying H3 before the TCP path.
- Leverage **Alt-Svc** already learned from the origin; when no Alt-Svc is known yet, may attempt direct QUIC at the host/port of the request URI.
- When H3 is unavailable and fallback is permitted, handle the request over HTTP_2 or HTTP_1_1.

~~~java
// JDK 26+: explicit ANY.
HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://service.example/"))
        .version(HttpClient.Version.HTTP_3)
        .setOption(HttpOption.H3_DISCOVERY, Http3DiscoveryMode.ANY)
        .GET()
        .build();
~~~

**ANY is an implementation-specific algorithm**, not a promise that it will always open QUIC first, always race two connections, or send two duplicate business HTTP requests. Each environment may reuse a connection pool or an already established path. **The actual version is only known after the response.**

**When to use:** when you want to try H3 where supported while still serving clients on networks that disallow UDP. This is an option for monitored migration and rollout. Do **not** use ANY to write tests asserting that a request must be HTTP_3.

## 6. Discovery Mode ALT_SVC: Learning from Origin Advertisements

**Http3DiscoveryMode.ALT_SVC** requires relying solely on **HTTP Alternative Services** to discover/establish an HTTP/3 path. Initially, if the client does not yet know a suitable h3 alternative service, the request may use **HTTP/2 or HTTP/1.1**. The server advertises via an HTTP response header:

~~~http
HTTP/1.1 200 OK
Alt-Svc: h3=":443"; ma=3600
Content-Type: text/plain

hello
~~~

**Alt-Svc** is not an HTTP redirect. Meaning:

- **h3** is the protocol identifier for HTTP/3.
- **":443"** specifies an alternative service on the same hostname at port 443 per Alt-Svc syntax.
- **ma=3600** advertises max-age in **seconds**; storing/applying the advertisement depends on policy and implementation.
- The **resource URI** in the application still represents the **same origin**, not a switch to a new resource path.
- The server may advertise H3 when returning 200 over HTTP/2; the next request may use H3 if the advertisement is accepted and the QUIC path works.

~~~text
Turn 1: Client prefers HTTP_3, ALT_SVC mode, Alt-Svc not yet known
         |
         +--> TCP/TLS => HTTP/2 or HTTP/1.1
                      |
                      +-- Server returns Alt-Svc: h3=":443"; ma=3600
                            |
                            v
Turn 2: Same client, same origin => may try QUIC/H3
         |
         +--> Success: response.version() = HTTP_3
         +--> H3 not yet/not used: H2 or H1 per valid selection
~~~

~~~java
// JDK 26+: selecting HTTP_3 at the client is required for the hint to take effect.
HttpClient client = HttpClient.newBuilder()
        .version(HttpClient.Version.HTTP_3)
        .build();

HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://service.example/"))
        .setOption(HttpOption.H3_DISCOVERY, Http3DiscoveryMode.ALT_SVC)
        .GET()
        .build();
~~~

**Do not assume the first request uses H3** just because the origin actually supports H3. In ALT_SVC, the client must know a suitable advertisement first, typically through a previous HTTP response. There is **no** guarantee that the 2nd request will definitely use H3; the advertisement may not have been applied, may have expired, may not qualify, a cached connection may be reused, or the UDP/TLS network path may fail.

### Alt-Svc vs. HTTP 302

| Alt-Svc | HTTP Redirect |
| --- | --- |
| Advertises an **alternative protocol service** endpoint for the same origin | Points to a different URI for the resource/request |
| Usually appears in a 200 response or other appropriate response | Usually status 301/302/303/307/308 with Location |
| Does not change the resource URI in the HTTP sense | May generate a request to a new URI |
| Useful for switching H2 ↔ H3 | Useful for URI/resource navigation |
| Requires validating that the alternative service is authoritative for the origin | Requires applying redirect policy, credentials, and scheme restrictions |

**Security:** Alt-Svc does not grant permission to skip certificate validation. QUIC/TLS must authenticate the peer appropriately for the **origin**. Never take an untrusted Alt-Svc header and disable hostname verification.

## 7. Discovery Mode HTTP_3_URI_ONLY: Strict H3, Direct URI Authority

**Http3DiscoveryMode.HTTP_3_URI_ONLY** requires attempting **HTTP/3 directly at the request URI's authority**: the host and port specified by the URI. It does **not** use Alt-Svc to find another host/port, and does **not** fall back to HTTP/2 or HTTP/1.1 if a QUIC/H3 connection cannot be established.

~~~java
// JDK 26+: strict mode takes effect because HTTP_3 is selected as preferred.
HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://service.example:443/ping"))
        .version(HttpClient.Version.HTTP_3)
        .setOption(HttpOption.H3_DISCOVERY,
                Http3DiscoveryMode.HTTP_3_URI_ONLY)
        .GET()
        .build();
~~~

**Requirements:** a valid HTTPS URI, the server must listen for QUIC/H3 at this **host:port**, the UDP path must be reachable, TLS/ALPN/certificate must match, and it must not hit proxy restrictions rejected by the JDK. Otherwise, the request may throw an exception.

**HTTP_3_URI_ONLY does not mean selecting HTTP_3 is automatically strict.** Only when **the strict option is set** together with the HTTP_3 preference does this policy apply. Using **version(HTTP_3)** alone without setting the option is equivalent to **ANY** with the built-in implementation.

### What if Alt-Svc points to a different port?

Suppose origin **https://service.example/** advertises:

~~~http
Alt-Svc: h3=":8443"; ma=3600
~~~

- **ALT_SVC** can use that advertisement to reach H3 port 8443 once known/accepted.
- **ANY** can use that advertisement or direct QUIC according to its algorithm.
- **HTTP_3_URI_ONLY** **ignores Alt-Svc**, only trying the URI's authority directly—meaning the default HTTPS port 443. If the server only opens QUIC on 8443, strict URI_ONLY may fail.

**When to use:** testing an endpoint known to have QUIC at that host/port, or an H3-mandatory policy. Do **not** enable on all production requests if client networks may block UDP and the application still needs fallback.

## 8. Behavior Matrix to Remember

| Client/request config | Discovery mode | What the client can actually do |
| --- | --- | --- |
| Neither sets HTTP_3 | H3_DISCOVERY absent | Default HTTP_2, may fall back to HTTP_1_1 |
| Neither sets HTTP_3 | ALT_SVC or URI_ONLY | **Option has no effect** |
| Either selects HTTP_3 | Option not set | Built-in treats as **ANY** |
| Either selects HTTP_3 | ANY | May be H3, H2, or H1 |
| Either selects HTTP_3 | ALT_SVC | Before knowing h3 Alt-Svc, usually H2/H1; afterward may be H3 |
| Either selects HTTP_3 | HTTP_3_URI_ONLY | Direct H3 at URI only; no fallback |
| Client selects HTTP_3, request selects HTTP_2 | Any H3_DISCOVERY | Request prefers HTTP_2; H3 hint has no effect |
| H3 preferred but **http://** URI | ANY/ALT_SVC/URI_ONLY | **Not** sent over HTTP/3 |
| H3 preferred, HTTP proxy selected | ANY/ALT_SVC | JDK 26 built-in downgrades to H2/H1, ignores hint |
| H3 preferred, HTTP proxy selected | URI_ONLY | Built-in request fails |

**Note on proxies:** this limitation is a **JDK 26 built-in implementation note**; it does not assert that no vendor/provider or future version can implement HTTP/3 over a proxy. JDK 26 by default **does not** have HTTP/3 over a proxy. Environments that require a corporate proxy may see H3-preferred requests fall back to HTTP/2/H1.

### FAQ: does ANY send two POSTs in parallel?

**Do not conclude that.** The Javadoc describes establishing/racing **transport connection paths**, not a promise that the application automatically sends two duplicate business POSTs. For a POST with side effects, retrying after a timeout must still follow **idempotency keys, request IDs, and the business contract**. Do not infer application outcomes from the connection discovery algorithm.

## 9. Offline JDK 26 Program: Inspecting Configuration

This demo uses **HTTP_3**, **HttpOption**, and **getOption** from **JDK 26+**, but **does not execute a request**. Use it to verify the API version and option safely without depending on an external H3 server on the Internet.

Create file **Http3Options26.java**:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpOption;
import java.net.http.HttpOption.Http3DiscoveryMode;
import java.net.http.HttpRequest;

public class Http3Options26 {
    public static void main(String[] args) {
        try (HttpClient client = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_3)
                .build()) {

            HttpRequest req = HttpRequest.newBuilder(
                    URI.create("https://example.com/"))
                    .version(HttpClient.Version.HTTP_3)
                    .setOption(HttpOption.H3_DISCOVERY,
                            Http3DiscoveryMode.ALT_SVC)
                    .GET()
                    .build();

            System.out.println("clientPreferred=" + client.version());
            System.out.println("requestPreferred=" +
                    req.version().orElseThrow());
            System.out.println("discovery=" +
                    req.getOption(HttpOption.H3_DISCOVERY).orElseThrow());
            System.out.println("scheme=" + req.uri().getScheme());
        }
    }
}
~~~

Compile **with JDK 26 or later**, targeting release **26**:

~~~bash
javac --release 26 -encoding UTF-8 Http3Options26.java
java Http3Options26
~~~

**Expected output per the public JDK 26 contract** (not executed on JDK 26 in the article's verification environment):

~~~text
clientPreferred=HTTP_3
requestPreferred=HTTP_3
discovery=ALT_SVC
scheme=https
~~~

**Explanation:** the getters read the client/request configuration. There is no HTTP response yet, so you cannot claim that example.com supports H3 or has QUIC open. **getOption(H3_DISCOVERY)** shows the request contains the **ALT_SVC** hint, which does not mean that protocol has been selected.

**Why JDK 26 is required:** **HttpClient.Version.HTTP_3**, **HttpOption**, **Builder.setOption**, and **HttpRequest.getOption** do not exist in JDK 24/Java 17. If you compile with javac 24 or **--release 17**, you will hit a compile error because the API does not exist; that is the proper API version protection mechanism, not a bug in the example.

## 10. JDK 26 Program Observing Live Actual HTTP Version

When **JDK 26+** and a valid HTTPS endpoint are available, the following program lets you choose a discovery mode, send **two consecutive GETs through the same HttpClient**, and observe **response.version()**. This is useful with ALT_SVC because the advertisement is typically learned from the previous response.

Create file **Http3LiveProbe26.java**:

~~~java
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpOption;
import java.net.http.HttpOption.Http3DiscoveryMode;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public class Http3LiveProbe26 {
    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: java Http3LiveProbe26 <https-url> <ANY|ALT_SVC|HTTP_3_URI_ONLY>");
        }
        URI uri = URI.create(args[0]);
        if (!"https".equalsIgnoreCase(uri.getScheme())) {
            throw new IllegalArgumentException("HTTPS URI required for HTTP/3");
        }
        Http3DiscoveryMode mode = Http3DiscoveryMode.valueOf(args[1]);

        try (HttpClient client = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_3)
                .connectTimeout(Duration.ofSeconds(5))
                .followRedirects(HttpClient.Redirect.NEVER)
                .build()) {

            HttpRequest req = HttpRequest.newBuilder(uri)
                    .version(HttpClient.Version.HTTP_3)
                    .setOption(HttpOption.H3_DISCOVERY, mode)
                    .timeout(Duration.ofSeconds(15))
                    .GET().build();

            System.out.println("clientPreferred=" + client.version());
            System.out.println("requestPreferred=" +
                    req.version().orElseThrow());
            System.out.println("mode=" +
                    req.getOption(HttpOption.H3_DISCOVERY).orElseThrow());

            for (int i = 1; i <= 2; i++) {
                try {
                    HttpResponse<Void> response = client.send(
                            req, HttpResponse.BodyHandlers.discarding());

                    System.out.println("attempt=" + i
                            + " actual=" + response.version()
                            + " status=" + response.statusCode());
                    System.out.println("altSvc=" +
                            response.headers().firstValue("Alt-Svc")
                                    .orElse("absent"));
                } catch (IOException e) {
                    System.out.println("attempt=" + i +
                            " transportFailure=" +
                            e.getClass().getSimpleName());
                    break;
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    throw e;
                }
            }
        }
    }
}
~~~

Compile and run with **JDK 26**:

~~~bash
javac --release 26 -encoding UTF-8 Http3LiveProbe26.java
java Http3LiveProbe26 https://www.example.org/ ANY
java Http3LiveProbe26 https://www.example.org/ ALT_SVC
java Http3LiveProbe26 https://www.example.org/ HTTP_3_URI_ONLY
~~~

**There is no fixed stdout** for HTTP/3 over the network: an endpoint may not support H3, may use a CDN/proxy, may advertise Alt-Svc differently, UDP may be blocked, or TLS/QUIC may be incompatible. **Conditional illustrative output**, not an actual run against example.org:

~~~text
clientPreferred=HTTP_3
requestPreferred=HTTP_3
mode=ALT_SVC
attempt=1 actual=HTTP_2 status=200
altSvc=h3=":443"; ma=3600
attempt=2 actual=HTTP_3 status=200
altSvc=absent
~~~

If a request uses **HTTP_3_URI_ONLY** to a server not listening for QUIC at the URI authority, the application may print **transportFailure=...**. Do not replace that with **status=505**, because when there is no HTTP response there is **no HTTP status**. Conversely, status 404 on an HTTP_3 response simply means the resource was not found; the HTTP/3/QUIC layer still worked well enough to receive a response.

**QA limitation:** the Java 26 examples use APIs verified against **JDK 26 Javadoc**. The actual execution environment had **JDK 24**, which lacks **HTTP_3** to compile/run the two JDK 26 programs. The program in section 11 was actually compiled and run with **--release 17**.

### Notes when using the live probe

- **HttpClient** is reused for two requests; a new client per request might not preserve discovery information/connection reuse.
- Only send **GET** to endpoints you are authorized to test; do not substitute a POST with side effects without idempotency.
- **Redirect.NEVER** helps observe the supplied origin; if redirects are followed, the actual response may belong to a different host.
- **IOException** is a transport/client failure; the specific cause still needs to be read from the cause/logs to distinguish UDP path, TLS, timeout, or proxy.
- The H3_DISCOVERY option in the request **is not a response field**; **getOption()** shows the configuration, while **response.version()** shows the actual protocol.
- Two requests are not enough to prove all future requests will use H3: cache lifetime, network conditions, and load balancing can change.

## 11. Tested Java 17 Program: Preferred Is Not Actual

To demonstrate the principle **preferred version ≠ actual version** in a way that runs on a machine without JDK 26, the demo uses a local **HTTP/1.1** HTTP server and an HttpClient that defaults to preferring HTTP_2. The actual result from the response is HTTP_1_1. The code also checks at runtime whether the Version enum has **HTTP_3** by comparing names, without referencing Java 26 APIs at compile time.

Create file **HttpVersionBaseline.java**:

~~~java
import com.sun.net.httpserver.HttpServer;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public class HttpVersionBaseline {
    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress(InetAddress.getByName("127.0.0.1"), 0), 0);
        server.createContext("/hello", exchange -> {
            try (exchange) {
                byte[] data = "OK".getBytes(StandardCharsets.UTF_8);
                exchange.sendResponseHeaders(200, data.length);
                try (OutputStream stream = exchange.getResponseBody()) {
                    stream.write(data);
                }
            }
        });
        server.start();
        try {
            HttpClient client = HttpClient.newHttpClient();
            URI uri = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/hello");
            HttpRequest request = HttpRequest.newBuilder(uri).GET().build();
            HttpResponse<String> response = client.send(
                    request, HttpResponse.BodyHandlers.ofString());

            System.out.println("preferred=" + client.version());
            System.out.println("requestVersionSet=" +
                    request.version().isPresent());
            System.out.println("http3EnumPresent=" + Arrays.stream(
                    HttpClient.Version.values())
                    .anyMatch(v -> v.name().equals("HTTP_3")));
            System.out.println("actual=" + response.version());
            System.out.println("status=" + response.statusCode());
            System.out.println("body=" + response.body());
        } finally {
            server.stop(0);
        }
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 -encoding UTF-8 HttpVersionBaseline.java
java HttpVersionBaseline
~~~

**Exact stdout verified on JDK 24.0.2 when compiled targeting Java 17:**

~~~text
preferred=HTTP_2
requestVersionSet=false
http3EnumPresent=false
actual=HTTP_1_1
status=200
body=OK
~~~

Why?

- **preferred=HTTP_2** because HttpClient defaults to preferring HTTP/2.
- **requestVersionSet=false** because the request did not override; it uses the client's preference.
- **actual=HTTP_1_1** because the demo server only speaks HTTP/1.1 on loopback and has no H2/H3.
- **http3EnumPresent=false** because the test runtime is JDK 24; on JDK 26 this value is expected to be **true**.
- **status=200** and **body=OK** prove the HTTP response arrived, even though it did not use the preferred version.

**com.sun.net.httpserver.HttpServer** in module **jdk.httpserver** is only used as an HTTP/1.1 test fixture; **it is not an HTTP/3 server**. This demo does not test QUIC. With the **--release 17** flag, HttpClient is not yet **AutoCloseable** in the Java 17 API, so the code does not wrap HttpClient in try-with-resources; that ensures genuine Java 17 target compilation. The two Java 26 demos can use try-with-resources for HttpClient per the new Javadoc.

## 12. Practical Conditions for Using HTTP/3

### 12.1. The URI must be HTTPS in the built-in JDK 26 HttpClient

Requests with a URI scheme other than **https** will **not** be sent over HTTP/3. Simply calling **version(HTTP_3)** on an **http://** URI does not automatically create an HTTPS upgrade. HTTP redirect, HSTS, TLS, and HTTP/3 preference are separate mechanisms.

### 12.2. HTTP/3 requires a UDP path and a QUIC listener

Working TCP/443 does not guarantee working UDP/443. Firewalls, NATs, VPNs, load balancers, container ingress, cloud egress, or corporate proxies may block UDP. Against a server with only a TCP-based HTTPS listener:

- **ANY** may use H2/H1.
- **ALT_SVC** may only use H2/H1 if there is no H3 advertisement or QUIC does not work.
- **HTTP_3_URI_ONLY** will not silently fall back to H2/H1.

### 12.3. TLS, certificates, ALPN, and policy

QUIC integrates TLS 1.3 and requires appropriate certificate/hostname verification. **Alt-Svc does not permit bypassing trust manager/hostname checks**, because the alternative service must be authoritative for the origin. **ALPN** with identifier **h3** is involved in protocol negotiation; it is completely different from **HttpOption.H3_DISCOVERY** (a selection hint on the Java application side).

An incompatible custom **SSLContext** or **SSLParameters** can render HTTP/3 unusable; the Javadoc mentions **UnsupportedProtocolVersionException** in certain cases, especially with strict HTTP_3_URI_ONLY or when building the client. Do not relax TLS just to "force" an H3 benchmark.

### 12.4. Proxies in built-in JDK 26

In the documented implementation, **HTTP/3 through a proxy is not yet supported**. If a proxy is selected for the URI:

- With **ANY** or **ALT_SVC**, the protocol downgrades to **HTTP/2 or HTTP/1.1**, and the H3_DISCOVERY hint is ignored.
- With **HTTP_3_URI_ONLY**, the request **fails**.

Do not say that falling back over a proxy proves the HTTP/3 server is down; it may be a transport path limitation of the Java client.

### 12.5. Alt-Svc and lifetime

An Alt-Svc response header can advertise an alternative protocol/port with a max-age. The client may use the learned information in subsequent requests. This state is neither a redirect cache nor DNS; not every h3 advertisement will be used forever. Origin, certificate, cache lifetime, connection pooling, and policy all play a role. **Do not manually add an Alt-Svc header to a request to force the server to return H3**.

### 12.6. Redirects and versions

In built-in JDK 26, **H3_DISCOVERY** is propagated to the redirect request if configured. However, the subsequent request may have a **different URI**, a different proxy, and different H3 support conditions. The **response.version()** of the final response indicates the actual version for the observed exchange. Pay attention to method preservation, credentials, and redirect policy for APIs with sensitive data.

## 13. Distinguishing HTTP Errors from H3 Setup Failures

An **HttpResponse** returning 200, 404, 429, or 503 is still an HTTP response, regardless of whether the actual version is H3, H2, or H1. An exception during QUIC setup, TLS handshake, or connect does not mean the server "returned 503".

| Symptom | Is there an HttpResponse? | Interpretation |
| --- | --- | --- |
| HTTP_3 response 200 | Yes | Request succeeded per HTTP semantics |
| HTTP_2 response 200 in ANY mode | Yes | Valid fallback/TCP path; not an error in itself |
| HTTP_3 response 404 | Yes | HTTP resource not found; H3 still worked |
| HTTP_2 response 503 | Yes | Server/gateway returned Service Unavailable |
| URI_ONLY fails due to blocked UDP | Usually no | Transport failure, possibly timeout/IOException |
| Invalid QUIC/TLS hostname certificate | No complete HTTP response from request | TLS/client failure |
| DNS resolution error | No | DNS/connection error |
| Client timeout during path selection | No complete response from send | Unknown whether the request had side effects |
| Redirect to a new host fails DNS | send may throw an exception | Do not fabricate a 502/504 status |

**Do not assign status code = 0, 500, or 505 to fake a server response.** If a framework needs an internal code, put it in a separate **transportError** field and keep **status** absent. Especially for POST requests, a timeout/connection failure does not prove the server did not process it: an idempotency key and business state check are needed before resending.

## 14. Rollout and Observability Guidelines

1. **Check toolchain:** JDK 26+ is used for both building and running the new APIs. Do not compile HttpOption with javac 24 or **--release 17**.
2. **Check server:** the HTTPS endpoint has a real QUIC/H3 listener, UDP path, and proper TLS/ALPN/certificate. A JDK **HttpServer** that only speaks HTTP/1.1 cannot prove H3.
3. **Gradually enable HTTP_3:** at the client or for selected requests; start with ANY/ALT_SVC depending on migration goals.
4. **Measure actual version:** track **response.version()** across HTTP_3, HTTP_2, HTTP_1_1. Preferred is not the negotiated metric.
5. **Measure errors:** Quic/TLS errors, timeouts, DNS/connect, proxy use, response statuses, and retries. Do not lump transport failures into 5xx.
6. **Use long-lived clients:** reuse pools and discovery information. Do not create a new HttpClient for every request without a reason.
7. **Test strict:** only use HTTP_3_URI_ONLY on endpoints known to support direct H3, and clearly define behavior when UDP is blocked.
8. **Limit retries:** use bounded exponential backoff+jitter, support idempotency, and protect against retry storms.
9. **Maintain security:** proper certificates/truststore, do not disable TLS hostname verification, control logs and secrets.
10. **Have a rollback:** be able to lower the request/client preference back to HTTP_2 if the H3 rollout causes errors or increased latency.

### Information to log when debugging

~~~text
preferred_client_version=HTTP_3
request_preferred_version=HTTP_3
discovery_mode=ANY
actual_response_version=HTTP_2
http_status=200
transport_failure=none
proxy_selected=true_or_false
latency_ms=...
~~~

Transport error case:

~~~text
preferred_client_version=HTTP_3
discovery_mode=HTTP_3_URI_ONLY
actual_response_version=absent
http_status=absent
transport_failure=IOException_or_subtype
endpoint=https://service.example
~~~

Keep URI logs at a safe level (do not log sensitive tokens/queries). JDK 26 has logging for java.net.http, including the **http3** and **quic** categories, which can be enabled in a controlled manner via property:

~~~bash
java -Djdk.httpclient.HttpClient.log=errors,requests,http3,quic Http3LiveProbe26 https://service.example/ ANY
~~~

This is an illustrative command when you have JDK 26 and a real endpoint. Logs can contain sensitive metadata; do not leave verbose debug logging enabled continuously in production.

## 15. Common Misconceptions

| Misconception | Consequence | Fix |
| --- | --- | --- |
| JDK 26 automatically enables H3 for all HttpClients | Deployment does not change protocol | Default is still **HTTP_2** |
| Setting H3_DISCOVERY alone is enough | Option is ignored | Select **HTTP_3** at client/request |
| version(HTTP_3) guarantees H3 | Still receives HTTP_2/HTTP_1_1 | Distinguish preferred vs actual |
| ANY always opens QUIC first | Wrong latency predictions | ANY is implementation-specific |
| ALT_SVC means HTTP 302 redirect | Wrong URI path and security | Alt-Svc advertises an alternative service, does not move the resource |
| Having Alt-Svc means the next request is definitely H3 | Wrong metrics | May not use the alt service |
| HTTP_3_URI_ONLY will look up the port from Alt-Svc | Strict mode fails unexpectedly | URI_ONLY only uses the URI authority |
| Having TCP/443 means H3 works | UDP/QUIC fails to connect | Check UDP listener/egress |
| HTTP/3 runs over TCP | Wrong network architecture | HTTP/3 uses QUIC/UDP |
| Proxies usually support H3 automatically in JDK 26 | Strict fail or H2 fallback | Check JDK implementation note |
| TLS certificates do not matter because of QUIC | MITM risk | TLS 1.3/identity verification is still required |
| Response 200 means HTTP_3 was used | Wrong monitoring | Check **response.version()** |
| Strict H3 fail means server returned 505 | Fabricating HTTP codes | Distinguish exceptions from HttpResponse |
| Using local HttpServer to test H3 | Test only has H1 | Need an H3-capable server |
| Compiling Java 26 API with --release 17 | Compile failure | Use JDK 26 and release 26 |
| Retrying POST after timeout is always safe | Can create duplicate side effects | Idempotency key and business state |

## 16. Practice Exercises

1. On JDK 26, create a default client and a **version(HTTP_3)** client. Compare **client.version()**; why can you not conclude the network path yet?
2. Create a **version(HTTP_3)** request from a default HTTP_2 client; inspect **request.version()** and **response.version()**.
3. Select **H3_DISCOVERY=ALT_SVC** but forget to select HTTP_3. Why does the option have no effect? Fix it both ways: client-level and request-level.
4. Have a server emit **Alt-Svc: h3=":443"; ma=3600**. With the same HttpClient and ALT_SVC, log the version of two consecutive requests; why might the first one be HTTP_2?
5. A server has QUIC only on a port different from the URI authority. Explain why ALT_SVC can use that port while HTTP_3_URI_ONLY may fail.
6. Configure **HTTP_3_URI_ONLY** to a server without UDP/QUIC open. Inspect the exception; why must it not be converted into status 505?
7. Enable an HTTP proxy in a test environment. Compare ANY, ALT_SVC, and URI_ONLY per the JDK 26 implementation notes.
8. Use an HTTPS URI and an HTTP URI with HTTP_3 preferred. Which request can run HTTP/3 per the built-in JDK?
9. Run **HttpVersionBaseline.java** on JDK 24 and JDK 26; compare the **http3EnumPresent** value, while explaining why actual remains HTTP_1_1 on the demo server.
10. Build a dashboard breaking down **actual HTTP_3/HTTP_2/HTTP_1_1**, percent of fallback, UDP failures, p95 latency, timeouts, and status codes; propose a rollback rule.
11. Why does **ANY** not automatically permit retrying a POST with side effects when the client encounters an IOException? Propose an idempotency key per the API contract.
12. Read RFC 9114, RFC 9000, and RFC 7838. Summarize the differences between HTTP/3, QUIC, and Alt-Svc.

## 17. Short Pre-Use Checklist

- [ ] JDK 26+ in runtime/toolchain, not using new APIs under --release 17?
- [ ] Selected HTTP_3 at client or request, not just setting H3_DISCOVERY?
- [ ] Chose the right ANY/ALT_SVC/HTTP_3_URI_ONLY per policy?
- [ ] Know that ANY can fallback, ALT_SVC needs an advertisement, and URI_ONLY is strict?
- [ ] Valid HTTPS URI and origin hostname/certificate?
- [ ] Appropriate UDP/QUIC listener and network path?
- [ ] Not assuming HTTP/3 works through the built-in JDK 26 proxy?
- [ ] Using **response.version()** to verify actual?
- [ ] Have timeouts, retry limits, idempotency, and metrics?
- [ ] Tested with a real HTTP/3 server and a blocked-UDP case?

**Conclusion:** HTTP/3 on JDK 26 is an extension of **HttpClient** with **HTTP_3** and **HttpOption.H3_DISCOVERY**. **ANY** optimizes for flexibility; **ALT_SVC** relies on advertised alternative services; **HTTP_3_URI_ONLY** enforces direct H3 with no fallback. Correctness must be evaluated on **HttpResponse.version()**, not just configuration getters. HttpClient still defaults to preferring HTTP/2; only **HTTPS + QUIC/UDP + suitable server/TLS/proxy/network** enable H3 per the JDK 26 implementation.

### Official Documentation

- [JEP 517 — HTTP/3 for the HTTP Client API](https://openjdk.org/jeps/517)
- [Java SE 26: HttpClient](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpClient.html)
- [Java SE 26: HttpClient.Version](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpClient.Version.html)
- [Java SE 26: HttpOption](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpOption.html)
- [Java SE 26: HttpOption.Http3DiscoveryMode](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpOption.Http3DiscoveryMode.html)
- [Java SE 26: HttpRequest.Builder](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html)
- [Java SE 26: java.net.http module](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/module-summary.html)
- [Oracle JDK 26 Release Notes](https://www.oracle.com/java/technologies/javase/26all-relnotes.html)
- [Inside Java: HTTP/3 Support in JDK 26](https://inside.java/2025/10/22/http3-support/)
- [RFC 9114 — HTTP/3](https://www.rfc-editor.org/rfc/rfc9114)
- [RFC 9000 — QUIC Transport](https://www.rfc-editor.org/rfc/rfc9000)
- [RFC 9001 — QUIC TLS](https://www.rfc-editor.org/rfc/rfc9001)
- [RFC 7838 — HTTP Alternative Services](https://www.rfc-editor.org/rfc/rfc7838)
- [RFC 9204 — QPACK](https://www.rfc-editor.org/rfc/rfc9204)
