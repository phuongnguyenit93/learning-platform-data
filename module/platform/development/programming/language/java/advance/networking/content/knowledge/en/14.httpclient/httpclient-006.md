# Preferred HTTP Version Differs from Actual Response Version in Java HttpClient

## 1. The core question: requesting HTTP/2 but the server returns HTTP/1.1 — is it an error?

In Java `java.net.http.HttpClient`, when you write:

~~~java
HttpClient client = HttpClient.newBuilder()
        .version(HttpClient.Version.HTTP_2)
        .build();
~~~

you are setting the **preferred/requested HTTP version if possible**, **not** signing a contract guaranteeing that every request will be exchanged over HTTP/2.

If the connection or server cannot use HTTP/2 in that situation, Java HttpClient **may use HTTP/1.1** and return an `HttpResponse` normally. For example:

~~~text
Client preference: HTTP_2
Response version: HTTP_1_1
HTTP status: 200
Body: local-ok

=> This can be a valid fallback, NOT automatically synonymous with an error.
~~~

Most importantly, distinguish **three values**:

1. `HttpClient.version()`: **the preference configured on the client**, defaulting to `HTTP_2` in Java 17.
2. `HttpRequest.version()`: an `Optional<HttpClient.Version>` containing **the preference set specifically on the request**, or empty when the request inherits the client's setting.
3. `HttpResponse.version()`: **the actual HTTP version used for that response**, such as `HTTP_1_1` or `HTTP_2`.

In the context of the **Java Advance - networking → HttpClient** lesson, the title **“Preferred HTTP Version Differs from Actual Response Version”** reminds you not to treat the preferred configuration as proof that protocol negotiation succeeded. **Only observing `response.version()` tells you the actual version of the received response.**

This lesson uses **Java 17+ APIs at a Java 17-compatible level**. In Java 17, the `HttpClient.Version` enum has `HTTP_1_1` and `HTTP_2`; newer JDKs may add versions/protocols, so always read the documentation for your **target JDK**, and do not infer that an enum in Java 17 is a permanent list.

## 2. Learning objectives

After this lesson, you will be able to:

- Explain the exact meaning of **preferred/requested HTTP version**, **actual response version**, **fallback**, and **protocol negotiation**.
- Understand the precedence of `HttpClient.Builder.version(...)` and `HttpRequest.Builder.version(...)`, including when a request does not set a version.
- Read `client.version()`, `request.version()`, and `response.version()`; avoid incorrectly comparing an `Optional` with an enum.
- Explain why HTTPS typically uses **TLS ALPN** to negotiate HTTP/2, whereas plain HTTP may attempt **HTTP/1.1 Upgrade (h2c)**, with results depending on the server/proxy.
- Distinguish HTTP/1.1 fallback from **TCP, DNS, TLS, and HTTP 4xx/5xx status** errors, and from downgrading HTTPS to insecure HTTP.
- Know why **servers, proxies, HTTPS endpoints, connection reuse, and redirects** can affect the actual version.
- Inspect each `HttpResponse.version()` instead of relying on `HttpClient.version()` to emit metrics or enforce policies.
- Run **two Java 17 examples** on loopback: HTTP/2 preference → HTTP/1.1 actual; request-level override and `sendAsync`.
- Design an appropriate “HTTP/2 **required**” policy, understanding that checking the version **after the response** does not prevent the request from having been sent.
- Read logs/troubleshoot when expected and actual versions differ, without blindly retrying requests that have side effects.

## 3. What versions does a request have?

### 3.1. Distinguishing configuration-level and exchange-level

~~~text
HttpClient.Builder
    .version(HTTP_2)             (A) client's default preference
        |
        v
HttpClient client
    .version() -> HTTP_2
        |
        +--------+-------------------------------------------+
        |                                                    |
        v                                                    v
HttpRequest req1                                     HttpRequest req2
  does not call .version(...)                        .version(HTTP_1_1)
  req1.version() -> Optional.empty                   req2.version() -> Optional[HTTP_1_1]
  => inherits preferred HTTP_2                       => per-request preference HTTP_1_1
        |                                                    |
        v                                                    v
  client.send(req1, ...)                               client.send(req2, ...)
        |                                                    |
        +----------------------+-----------------------------+
                               |
                  negotiation / routing / proxy
                               |
                               v
                    HttpResponse<?> resp
                    resp.version() -> ACTUAL VERSION
                      HTTP_1_1 or HTTP_2
~~~

There is **no** general inference `client.version() == response.version()`. They may match or they may differ; the API clearly states that the client/request **proposes a version if feasible**, while the response carries the version **actually used**.

### 3.2. Table for choosing the right API

| Java 17 API | Return type / parameter | What does that value indicate? |
| --- | --- | --- |
| `HttpClient.newBuilder().version(HTTP_2)` | Builder setting | Client-level preference |
| `HttpClient.newHttpClient()` | HttpClient | Defaults to preferring HTTP/2 in Java 17 |
| `client.version()` | `HttpClient.Version` | The client's preferred version, **not the most recent communication version** |
| `HttpRequest.newBuilder(uri).version(HTTP_1_1)` | Builder setting | Request-specific preferred version |
| `request.version()` | `Optional<HttpClient.Version>` | Optional **recorded on the request**; empty means use the client preference |
| `client.send(request, handler)` | `HttpResponse<T>` | Returns a response after I/O-level communication succeeds; status may be 4xx/5xx |
| `client.sendAsync(request, handler)` | `CompletableFuture<HttpResponse<T>>` | Asynchronous response, with the same HTTP version selection rules |
| `response.version()` | `HttpClient.Version` | **The actual version used for this response** |
| `response.statusCode()` | `int` | HTTP status code, **different from version** |
| `response.uri()` | `URI` | Actual URI of the response, which may differ from the initial URI due to redirects |
| `response.previousResponse()` | `Optional<HttpResponse<T>>` | Intermediate response from redirect/authentication; may have a different version |
| `response.request()` | `HttpRequest` | Request corresponding to this response; after redirects it may not be the first request |

All three `version()` methods on client/request/response **are not the same method** in terms of semantics:

~~~java
HttpClient.Version wantByClient = client.version();
Optional<HttpClient.Version> wantByRequest = request.version();
HttpClient.Version actual = response.version();
~~~

This is a **code snippet** requiring `client`, `request`, and `response` variables created from a real request and imports `java.net.http.*`, `java.util.Optional`. If no response was received due to a DNS/TLS/connect error, there is **no** `response.version()` to read — do not fabricate a fake “actual” version.

### 3.3. Precedence when a request has an override

- If `request.version().isEmpty()`, the request uses the preferred version of the **`HttpClient`** sending it.
- If `request.version()` is present, **that value is the request's preferred version**, overriding the client preference for this send.
- Both are only **preferences**, not mandatory outcomes of negotiation.
- `HttpResponse.version()` indicates the actual choice for that exchange/response; if this version is not as preferred, **the API can still return a response normally**.

Example:

~~~text
Client preferred | Request override | Effective preferred | Actual response
-----------------|------------------|---------------------|----------------
HTTP_2           | empty            | HTTP_2              | HTTP_2 (if supported)
HTTP_2           | empty            | HTTP_2              | HTTP_1_1 (fallback)
HTTP_2           | HTTP_1_1         | HTTP_1_1            | HTTP_1_1 (common)
HTTP_1_1         | HTTP_2           | HTTP_2              | HTTP_2 (if supported)
HTTP_1_1         | HTTP_2           | HTTP_2              | HTTP_1_1 (fallback)
~~~

These rows are **possible scenarios**, not guaranteed outcomes independent of server/OS/proxy/JDK. Do not assume that calling `.version(HTTP_2)` forces an HTTP/1.1 server to use HTTP/2 or produce an error.

## 4. Why does preferred HTTP/2 result in actual HTTP/1.1?

### 4.1. The server only supports HTTP/1.1

The most straightforward case: the client proposes HTTP/2, but the origin server only implements HTTP/1.1.

~~~text
Java HttpClient
  preferred = HTTP_2
       |
       | HTTP/2 capable request / attempted negotiation
       v
HTTP/1.1-only server
       |
       | HTTP/1.1 200 OK
       v
Java HttpResponse
  version() = HTTP_1_1
  statusCode() = 200
~~~

**No application error has to occur.** HTTP semantics such as GET/POST, URI, status, headers, and body can still be carried out over HTTP/1.1. The differences are mainly in framing and version-specific features such as HTTP/2 stream multiplexing.

In the hands-on section, we use the JDK's `com.sun.net.httpserver.HttpServer` with HTTP/1.1 to **create a reproducible setup** on loopback without depending on public websites, certificates, or corporate proxies.

### 4.2. HTTPS and TLS ALPN

With **HTTPS over TCP/TLS**, HTTP/2 is typically negotiated during the **TLS handshake** via ALPN (*Application-Layer Protocol Negotiation*). The client can advertise protocols such as `h2` and `http/1.1`, and the server selects a protocol supported by both sides according to its deployment rules.

~~~text
Client wants HTTP/2
    |
    v
TCP connect -> TLS handshake + ALPN
    |
    +--> h2 selected            -> HTTP/2 frames -> response.version()=HTTP_2
    |
    +--> http/1.1 selected      -> HTTP/1.1      -> response.version()=HTTP_1_1
    |
    +--> handshake/TLS error    -> IOException/TLS exception, NO response
~~~

**HTTP/1.1 fallback over HTTPS does not automatically mean TLS is lost.** The connection can still use valid TLS; **HTTP version** and **TLS version** are two different dimensions. For example, `HTTP_1_1` over TLS 1.3 can still be fully protected HTTPS, depending on certificate verification and security configuration.

Conversely, `HTTP_2` does not by itself prove that the certificate is valid or that the client verified authorization. TLS security must be evaluated separately; an HTTP/2 preference does not replace authorization or TLS policy.

### 4.3. Unencrypted HTTP (h2c upgrade)

With `http://` URIs, HTTP/2 over cleartext is also called **h2c**. When preferring HTTP/2, Java HttpClient may **attempt an upgrade** from HTTP/1.1 to HTTP/2 according to its implementation capabilities, such as using the `Upgrade` mechanism. If the server does not accept the upgrade, the request/response **can continue over HTTP/1.1**.

~~~text
Java client -> HTTP/1.1 request with upgrade proposal mechanism
                  |
                  v
          Server supports HTTP/2 upgrade?
                  |
        +---------+-----------+
        |                     |
       yes                   no
        |                     |
        v                     v
      HTTP/2               HTTP/1.1
  response.version()    response.version()
     = HTTP_2              = HTTP_1_1
~~~

This is a conceptual model. Actual wire-level behavior has many conditions regarding upgrade, connection reuse, server/proxy, and request properties. You should not manually craft `Upgrade` or `HTTP2-Settings` headers in `HttpRequest.Builder` and assume you have properly implemented HTTP/2; let the HTTP stack handle it.

**Warning:** `h2c` has no TLS, so it is **not** suitable for transmitting sensitive content over untrusted networks just because its name contains “HTTP/2”. When you want HTTPS, the URI must be `https://` and certificates must be properly verified.

### 4.4. Proxy or gateway restricts the version

A request may pass through a forward proxy or reverse proxy. Java HttpClient may not support a particular style of HTTP/2 through a proxy, or the proxy may only speak HTTP/1.1 on a given hop.

~~~text
HttpClient (prefer h2) --proxy/route--> origin
             |
     proxy capability / route
             v
      HTTP/1.1 response is still valid
~~~

**Do not infer** that the versions for client-to-proxy, client-to-origin, and proxy-to-backend are always the same. `HttpResponse.version()` describes the version used for **the response received by the Java client**, not what version a backend behind a reverse proxy used.

A corporate proxy, VPN, gateway, or service mesh configuration can produce different results compared to a direct call. Investigation must record **the actual path of the request**, not just look at a single server-side setting.

### 4.5. Connection reuse and not every request is identical

`HttpClient` can keep and reuse connections. Negotiation is a property of **the connection/path**, not “every `send` call performs a new HTTP/2 handshake”.

Requests using the same client but hitting different origins, proxies, redirects, server instances, or occurring at different times may yield **different response versions**. That is not necessarily caused by using GET vs. POST. You should log per response, including the URI/authority and relevant routing information.

If response B has the same version as response A, that alone does not prove B reused the same TCP connection. `response.version()` is **not** a connection ID.

## 5. Where do HTTP/1.1 and HTTP/2 differ, and what stays the same?

| Property | HTTP/1.1 | HTTP/2 |
| --- | --- | --- |
| HTTP semantics | Method, target URI, status, headers, representation | Preserves those common semantics |
| Wire framing | Start-line, text-based headers, length/chunked rules | Binary frames and logical streams |
| Header compression | Does not use HPACK | Uses HPACK |
| Multiplexing multiple exchanges on one connection | No HTTP/2-equivalent stream multiplexing | Multiple concurrent streams on one TCP connection |
| TCP transport | Common, may have TLS | Common over TLS/TCP, with h2c on cleartext in some implementations |
| Connection reuse | Yes (persistent connections) | Yes, with multiplexing |
| Head-of-line blocking | Limited by exchanges on an h1 connection | Still has TCP-level head-of-line blocking |
| HTTP status `200`/`404` | Yes | Yes |
| Java 17 HttpClient.Version | `HTTP_1_1` | `HTTP_2` |

A GET request returning 200 over HTTP/1.1 is **not inherently less correct** than a GET returning 200 over HTTP/2. However, if a product requires **HTTP/2-specific features** (for example, multiple concurrent streams on one connection, or certain gRPC deployments), fallback can violate assumptions of **the infrastructure/application protocol**. In that case, an explicit policy is needed rather than trusting configuration alone.

**HTTP/3 in newer Java:** Java 17 does not have `HttpClient.Version.HTTP_3` in its enum, and this lab uses Java 17. Future or more modern JDKs may add HTTP/3 support; check `HttpClient.Version` for the target deployment JDK rather than using Java 17 documentation to conclude that every JDK only supports 1.1/2.

## 6. Practice 1: preferred HTTP/2, actual HTTP/1.1 — Java 17+ program

### 6.1. Demo goal

The program below:

1. Creates an HTTP/1.1-only server using the standard `jdk.httpserver` module, binding to `127.0.0.1` with port `0` so the OS picks a free port.
2. Creates an `HttpClient` with `version(HTTP_2)`.
3. Sends a GET request **with no override** to observe `request.version().isPresent() == false`.
4. Reads `HttpResponse.version()` and `statusCode()`. The server returns `200` with body `local-ok`.
5. Sends a second request **explicitly specifying HTTP_1_1**; the actual response is HTTP/1.1.
6. Sends a third request **explicitly specifying HTTP_2**; the server is still HTTP/1.1, so actual remains HTTP/1.1.
7. Stops the server in `finally` and requires no Internet access.

**File: `PreferredVsActualHttpVersion.java`**

~~~java
import com.sun.net.httpserver.HttpServer;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public class PreferredVsActualHttpVersion {
    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress(InetAddress.getByName("127.0.0.1"), 0), 0);
        server.createContext("/version", exchange -> {
            try (exchange) {
                byte[] payload = "local-ok".getBytes(StandardCharsets.UTF_8);
                exchange.getResponseHeaders().set("Content-Type", "text/plain");
                exchange.sendResponseHeaders(200, payload.length);
                exchange.getResponseBody().write(payload);
            }
        });
        server.start();
        try {
            URI uri = URI.create("http://127.0.0.1:" +
                    server.getAddress().getPort() + "/version");
            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_2)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();

            HttpRequest inherited = HttpRequest.newBuilder(uri)
                    .timeout(Duration.ofSeconds(5))
                    .GET().build();
            HttpResponse<String> first = client.send(
                    inherited, HttpResponse.BodyHandlers.ofString());

            System.out.println("Client preferred: " + client.version());
            System.out.println("Request override present: " +
                    inherited.version().isPresent());
            System.out.println("Response actual: " + first.version());
            System.out.println("HTTP status: " + first.statusCode());
            System.out.println("Body: " + first.body());

            HttpRequest explicitH1 = HttpRequest.newBuilder(uri)
                    .version(HttpClient.Version.HTTP_1_1)
                    .timeout(Duration.ofSeconds(5))
                    .GET().build();
            HttpResponse<Void> second = client.send(
                    explicitH1, HttpResponse.BodyHandlers.discarding());
            System.out.println("Request preferred: " +
                    explicitH1.version().orElseThrow());
            System.out.println("Second response actual: " + second.version());

            HttpRequest explicitH2 = HttpRequest.newBuilder(uri)
                    .version(HttpClient.Version.HTTP_2)
                    .timeout(Duration.ofSeconds(5))
                    .GET().build();
            HttpResponse<Void> third = client.send(
                    explicitH2, HttpResponse.BodyHandlers.discarding());
            System.out.println("H2 requested, response actual: " +
                    third.version());
        } finally {
            server.stop(0);
        }
    }
}
~~~

Compile with the Java 17 API and run:

~~~bash
javac --release 17 -encoding UTF-8 --add-modules jdk.httpserver PreferredVsActualHttpVersion.java
java --add-modules jdk.httpserver PreferredVsActualHttpVersion
~~~

**Verified stdout when run with OpenJDK 24 and compiled with `--release 17`:**

~~~text
Client preferred: HTTP_2
Request override present: false
Response actual: HTTP_1_1
HTTP status: 200
Body: local-ok
Request preferred: HTTP_1_1
Second response actual: HTTP_1_1
H2 requested, response actual: HTTP_1_1
~~~

### 6.2. Deep analysis of the output

- `Client preferred: HTTP_2` is read from `client.version()`, **not** negotiation success.
- `Request override present: false` proves the first request **has no per-request `.version(...)`**; therefore it takes the preference from the client.
- `Response actual: HTTP_1_1` is the real fact: in the first exchange, the client used HTTP/1.1 for the response, even though the configuration preferred HTTP/2.
- `HTTP status: 200` and `Body: local-ok` show that the request still succeeded. **A version mismatch does not automatically equate to a failure.**
- The second request explicitly chose `HTTP_1_1`; the response was HTTP/1.1 as expected.
- The third request explicitly chose `HTTP_2`, but the server only supports HTTP/1.1; the response was still HTTP/1.1. This is proof that **a request-level preference is also not a hard requirement**.

**Why is the result reproducible?** The `jdk.httpserver` module provides an embedded HTTP server using HTTP/1.1; the client connects to the local server. No external proxy, TLS, public DNS, or infrastructure setup is required.

### 6.3. Limitations of the example

- This is an **unencrypted HTTP lab on loopback** to verify negotiation/version, not a model for sending credentials over the Internet.
- If the OS or sandbox blocks opening a listening TCP socket, the example may fail due to network permissions; a normal Java 17 environment with loopback can run it.
- Do not conclude that every server falls back, or that every JDK produces HTTP/1.1 on every HTTP/2 request. **The essence of the lesson is reading `response.version()`.**
- `HttpServer` is a minimal embedded server suitable for demos/testing, and does not provide all the features of a production server.
- `HttpClient` in **Java 17** does not have `close()`/`AutoCloseable` in the Java 17 API; do not use `try (HttpClient client = ...)` when targeting `--release 17` compatibility.
- `send(..., BodyHandlers.discarding())` still waits for/returns a response; it only **discards the body**, and does not mean a missing HTTP response or an error status.
- `server.stop(0)` shuts down the demo server in `finally` so no listener is left behind.

## 7. Practice 2: request override, sendAsync, and a policy requiring HTTP/2

### 7.1. Goal

The second example illustrates two practical misconceptions:

- The client prefers HTTP/1.1, while **an individual request** prefers HTTP/2. The request preference overrides the client preference for that send.
- `sendAsync()` **does not** cause the HTTP version to default to HTTP/2. It only changes how the application awaits the **HTTP response**, not the negotiation capability.

When the actual response is HTTP/1.1, the code computes the `strict HTTP/2 satisfied` flag as false. This is a **post-response check**, and cannot turn back time to prevent the server from having already received the GET.

**File: `PerRequestVersionPolicyDemo.java`**

~~~java
import com.sun.net.httpserver.HttpServer;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.concurrent.TimeUnit;

public class PerRequestVersionPolicyDemo {
    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress(InetAddress.getByName("127.0.0.1"), 0), 0);
        server.createContext("/check", exchange -> {
            try (exchange) {
                exchange.sendResponseHeaders(204, -1);
            }
        });
        server.start();
        try {
            URI uri = URI.create("http://127.0.0.1:" +
                    server.getAddress().getPort() + "/check");
            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();
            HttpRequest request = HttpRequest.newBuilder(uri)
                    .version(HttpClient.Version.HTTP_2)
                    .timeout(Duration.ofSeconds(5))
                    .GET().build();

            HttpResponse<Void> response = client.sendAsync(
                    request, HttpResponse.BodyHandlers.discarding())
                    .get(6, TimeUnit.SECONDS);

            System.out.println("Client preferred: " + client.version());
            System.out.println("Request preferred: " +
                    request.version().orElseThrow());
            System.out.println("Response actual: " + response.version());
            System.out.println("Status: " + response.statusCode());
            System.out.println("Strict HTTP/2 satisfied: " +
                    (response.version() == HttpClient.Version.HTTP_2));
        } finally {
            server.stop(0);
        }
    }
}
~~~

Commands:

~~~bash
javac --release 17 -encoding UTF-8 --add-modules jdk.httpserver PerRequestVersionPolicyDemo.java
java --add-modules jdk.httpserver PerRequestVersionPolicyDemo
~~~

**Verified stdout:**

~~~text
Client preferred: HTTP_1_1
Request preferred: HTTP_2
Response actual: HTTP_1_1
Status: 204
Strict HTTP/2 satisfied: false
~~~

### 7.2. Lessons from the post-send check

- `request.version().orElseThrow()` returns `HTTP_2` because the builder set it; `request.version()` is **not empty**.
- `response.version()` = `HTTP_1_1` because the local server is HTTP/1.1; for this server, preferring HTTP/2 does not lead to a successful 101 upgrade.
- `sendAsync(...)` returns `CompletableFuture<HttpResponse<Void>>`; calling `get(...)` in `main` is just to wait for the result in the demo, and **does not** turn the async API into a different protocol choice.
- `204 No Content` is a valid HTTP status with no response body; `BodyHandlers.discarding()` is simply a body-handling choice.
- `strict HTTP/2 satisfied: false` is **an application policy result**, not `HttpClient` automatically throwing an error on protocol fallback.

**Business warning:** if that were a payment POST, the server might have already executed the operation before you ever saw `response.version()`. Therefore, you should not “see a lower version and retry the POST” without idempotency/deduplication design. If the HTTP version is a mandatory requirement before allowing sensitive operations, you need **upfront server/proxy capability checks and enforcement on the receiving system**, not just an assertion on the response after the request has already run.

## 8. HTTP status and HTTP version are not interchangeable

Suppose:

~~~text
Preferred HTTP_2 | Actual HTTP_1_1 | Status 200
Preferred HTTP_2 | Actual HTTP_2   | Status 404
Preferred HTTP_2 | Actual HTTP_1_1 | Status 503
~~~

The three scenarios above need to be handled **differently**:

- **Row 1:** the request succeeded in terms of HTTP status, but used a different version than preferred. If HTTP/2 is only a performance optimization, you can accept it and record a metric.
- **Row 2:** the version matched the preference, but the server returned 404; the application must handle the resource/URI/authorization issue, **not** conclude it succeeded because HTTP/2 was used.
- **Row 3:** actual HTTP/1.1 and 503; you need to analyze server availability/rate limiting/gateway issues, **not** automatically conclude that 503 was caused by a protocol downgrade.

**I/O error codes are different as well:**

| Symptom | Is there an `HttpResponse.version()`? | Diagnosis |
| --- | --- | --- |
| `HttpClient` receives HTTP `200` | Yes | Check status/body and actual version |
| Receives HTTP `404`/`500` | Yes | This is still an HTTP response |
| Cannot resolve DNS | No | DNS error/`UnknownHostException`, no HTTP response yet |
| TCP connect refused/timeout | No | Transport/connect error, no HTTP exchange negotiated yet |
| TLS certificate/handshake error | No | TLS/SSL error; do not call it HTTP/1.1 fallback if there is no response |
| Request timeout before receiving response | Possibly no | Check cancellation/deadline; do not fabricate an actual version |
| Proxy returns HTTP `502`/`504` | Yes if a response was received | The version returned to the client may differ from the upstream protocol |
| Redirect followed automatically | Yes | `version()` is on the final response; inspect intermediate ones if needed |

Do **not** use `response.version()==HTTP_2` as a measure of request success: the client must still check `statusCode()`, valid content, and the business response schema.

## 9. When do you truly need to enforce an HTTP version?

### 9.1. When it is only for performance optimization

Many REST APIs work well over both HTTP/1.1 and HTTP/2. If this is your situation:

- Set `HTTP_2` as the preference.
- Allow HTTP/1.1 fallback if the server/gateway does not support h2.
- Record actual version metrics to measure HTTP/2 adoption and factors such as proxy/server versions.
- Evaluate latency/throughput under real load: HTTP/2 has multiplexing, but a single TCP connection still suffers from head-of-line blocking on packet/segment loss.
- Do **not** immediately retry a request just because the actual version is HTTP/1.1.

This is the appropriate approach when HTTP/2 features are an **optimization**, not a business contract.

### 9.2. When the application protocol requires HTTP/2

Some protocols/deployments require HTTP/2 characteristics (for example, certain gRPC deployments). In that case:

1. **Identify version requirements at every hop**: client-to-edge, edge-to-backend, proxy-to-upstream. The Java client's `response.version()` only observes **the hop/protocol the client used** for the response.
2. **Deploy servers/proxies with proper HTTP/2 and TLS ALPN**; verify the result in a production-like staging environment.
3. **If fail-closed behavior is needed**, use a policy at the gateway/server or a reliable capability/health preflight mechanism. Do not assume `HttpClient.Builder.version(HTTP_2)` rejects fallback on its own.
4. Check `response.version()` to detect mismatches and log/alert. Detecting after sending is only a **postcondition**, not a replacement for a precondition.
5. Do not re-execute operations with side effects just because of a postcondition mismatch; design idempotency keys/transaction boundaries.
6. Consider using a protocol-appropriate library (such as an official gRPC implementation) instead of forcing Java `HttpClient` and handling HTTP/2 frames manually.

**Distinguish the levels:** if you want *“prefer h2”*, `.version(HTTP_2)` is appropriate. If you want *“h2 or reject before the business operation”*, you must have additional enforcement at the infrastructure/protocol layer, not just the `version` parameter alone.

### 9.3. When to intentionally prefer HTTP/1.1?

You might choose `HTTP_1_1` to:

- Test compatibility with a legacy server or gateway.
- Isolate bugs related to HTTP/2 proxies/settings/stream multiplexing.
- Reproduce a production issue that only occurs over HTTP/1.1.
- Reduce variables when teaching the text structure of HTTP/1.1 requests/responses.

Example:

~~~java
HttpClient client = HttpClient.newBuilder()
        .version(HttpClient.Version.HTTP_1_1)
        .build();
~~~

This is a **code snippet**, requiring `import java.net.http.HttpClient;`. Do not treat choosing HTTP/1.1 as a security guarantee or as “HTTP/1.1 does not need TLS”. HTTP version and HTTPS are two separate concepts.

## 10. Common sources of confusion when debugging

### 10.1. Misunderstanding due to the shared `version()` method name

The following lines are **not equivalent**:

~~~java
client.version();     // Preferred on the client
request.version();    // Optional per-request preference
response.version();   // Actual on the response
~~~

For a request that has not called `.version(...)`, `request.version()` returns `Optional.empty()` — which does not mean the request uses no HTTP protocol, nor does it mean it defaults to HTTP/1.1. It **inherits the client's preference**, and **the real version is still determined by the response**.

A common mistake:

~~~java
// INCORRECT MEANING: this condition only compares configuration and actual.
boolean h2Guaranteed =
        client.version() == HttpClient.Version.HTTP_2;

// CORRECT FOR RESPONSE OBSERVABILITY:
boolean thisResponseUsedH2 =
        response.version() == HttpClient.Version.HTTP_2;
~~~

The snippet above requires existing `client` and `response` variables; the two booleans have different scopes. `thisResponseUsedH2` does **not** prove that an internal upstream server uses HTTP/2 or that all requests on the same client use h2.

### 10.2. Looking at `request.version()` instead of `response.version()`

The request builder only has the authority to **propose**; the response tells you the **actual** result. If code evaluates:

~~~java
request.version().orElse(client.version())
~~~

the result is the **effective preference**. It is useful for logging configuration, but **cannot** be used as the actual protocol label. To record metrics:

~~~java
HttpClient.Version wanted =
        request.version().orElse(client.version());
HttpClient.Version actual = response.version();
boolean matched = wanted == actual;
~~~

This is a **code snippet** placed after a successful send, requiring `client`/`request`/`response`. Log `"wanted"`, `"actual"`, and `"matched"` clearly, rather than lumping them into a misleading field named `http_version`.

### 10.3. Not setting a version yet still seeing a difference

`HttpClient.newHttpClient()` in **Java 17** has a default preference of `HTTP_2`. Therefore, if a request does not call `.version(HTTP_2)` and the response is still `HTTP_1_1`, it does not necessarily mean the client hasn't “enabled” HTTP/2. The client may already prefer HTTP/2 by default, while the server/hops did not fulfill it.

Verification snippet:

~~~java
HttpClient client = HttpClient.newHttpClient();
System.out.println(client.version()); // Java 17: HTTP_2
~~~

The print statement above reflects the Java 17 spec; it does not prove that any request has been executed or that HTTP/2 has been negotiated.

### 10.4. Trying HTTP/2 over plain HTTP when the server does not upgrade

With a URL like `http://localhost:port`, selecting HTTP/2 may require an **h2c upgrade**. If the server only speaks HTTP/1.1, an actual version of HTTP/1.1 can be completely normal.

You should not directly compare h2c results on localhost against a production HTTPS website and conclude that “Java HttpClient is inconsistent”. The two negotiation paths differ: **Upgrade vs TLS ALPN**.

### 10.5. Results change when a proxy is enabled

A client with a proxy may use h1 for a proxy path that does not support HTTP/2 even if the target server itself supports HTTP/2. Therefore, minimal logs should include:

- Target scheme/authority/URI as appropriate, with sensitive data redacted.
- Effective preferred version (client or request).
- Actual `response.version()`.
- Status code.
- Proxy/network route mode (direct/proxy), if permitted to log.
- Final redirect URI and intermediate responses when needed.
- JDK runtime version (not just compiler `--release 17`).
- TLS/ALPN diagnostics in a controlled environment, without logging raw tokens/cookies.

You should **not** enable overly verbose network/TLS debugging in production where credentials are present; logs can expose metadata and sensitive content.

### 10.6. Redirects cause you to look at the wrong response

Suppose an initial request to `https://a.example/path` receives a redirect to `https://b.example/final`. The client may connect to a **different origin**, negotiate differently, and the final response may have a different version from the redirect response.

According to the Java API:

- `response.uri()` is the URI of the current response (which may differ from the initial request URI).
- `response.request()` is the request corresponding to this response (which may differ from the initial request).
- `response.previousResponse()` provides the previous/intermediate response (redirect/authentication) if any.

Diagnostic example (snippet, where `response` is the received response):

~~~java
System.out.println("Final URI: " + response.uri());
System.out.println("Final HTTP version: " + response.version());

var earlier = response.previousResponse();
while (earlier.isPresent()) {
    var intermediate = earlier.get();
    System.out.println("Earlier URI: " + intermediate.uri());
    System.out.println("Earlier version: " + intermediate.version());
    earlier = intermediate.previousResponse();
}
~~~

This **code snippet** requires an existing `HttpResponse<?>` `response`; it is not a standalone program. With Java 17, `var` can be used for local variables. These intermediate responses may not contain a body like the final response. Do not assume all redirects are followed automatically: `HttpClient.Redirect.NEVER` is the default redirect policy in Java 17, unless the builder is configured otherwise.

If the goal is to log all negotiations across multiple origins, you must observe each actual hop and potentially add tracing at the proxy/server; the final `HttpResponse.version()` does not describe every downstream connection on its own.

## 11. Does a version mismatch compromise HTTP security?

**HTTP version** and **transport security** are not a “higher means more secure” pair:

| Case | Has TLS? | Actual HTTP version | Conclusion |
| --- | --- | --- | --- |
| `https://` using TLS 1.3, ALPN selects `http/1.1` | Yes | HTTP/1.1 | Can be valid, secured HTTPS |
| `https://` using TLS, ALPN selects `h2` | Yes | HTTP/2 | HTTP/2 over TLS |
| `http://` cleartext server does not accept h2c | No | HTTP/1.1 | Unencrypted due to scheme, **not** because the version fell back |
| `http://` cleartext h2c upgrade succeeds | No | HTTP/2 | HTTP/2 can still be cleartext |
| `https://` TLS handshake error | Did not complete | No HTTP response yet | Should not assign an actual HTTP version |

Do not react to `HTTP_1_1` by disabling TLS certificate verification or changing `https` to `http`. That is **downgrading transport security**, and is completely unnecessary for resolving a protocol version mismatch.

If you need to verify the TLS version/cipher/certificate, check them using **TLS/SSL APIs and endpoint validation policies** directly; `response.version()` is only the **HTTP protocol version**, not the TLS version.

## 12. Logging, metrics, and observing the protocol version properly

A conceptual logging pattern:

~~~java
HttpClient.Version preferred =
        request.version().orElse(client.version());
HttpClient.Version actual = response.version();
int status = response.statusCode();

System.out.printf(
    "preferred=%s actual=%s matched=%s status=%d%n",
    preferred, actual, preferred == actual, status);
~~~

This is a **code snippet** used inside a method after receiving a response, with `client`, `request`, and `response` already available. To evaluate an HTTP/2 rollout:

- Percentage of **actual HTTP_2**, broken down by scheme/hostname/proxy and request group (without logging tokens/user IDs).
- Count of responses where **preferred HTTP_2 but actual HTTP_1_1**.
- Distribution by JDK runtime and network environment.
- Associated HTTP status/latency, **without lumping mismatches into network errors**.
- Count of requests that actually failed before receiving a response (DNS/connect/TLS), separate from version mismatches.
- p50/p95/p99 latency under comparable workloads, avoiding conclusions based solely on the version label.
- Consistency with server/proxy information (ALPN, negotiated version, upstream protocol) when accessible.

`HttpResponse.version()` measures **the version of the response**, and does not prove actual throughput, TCP connection reuse, or header compression. Do not use it in place of performance measurement.

### 12.1. Investigation plan when HTTP/2 does not appear

1. **Verify expectation**: is `client.version()` equal to `HTTP_2`? Is there a per-request `request.version()`?
2. **Read actual**: `response.version()` right after `send()` or when `sendAsync()` completes.
3. **Separate errors**: did the request return a normal response status/body, or did it throw an exception? Without a response, do not call it a successful fallback.
4. **Check URL**: `http://` and `https://` negotiate differently (h2c vs TLS ALPN).
5. **Check server h2 support**: evidence from config/logs/server capabilities, not just seeing that a web page "works".
6. **Check proxy/gateway**: are there any intermediaries on the client's actual path? Is HTTP/2 supported on the relevant hop?
7. **Check redirects**: did `response.uri()` change? Does `previousResponse()` contain earlier response versions?
8. **Check JDK/runtime**: do the Java 17 enum and behavior match the running runtime? Is another HTTP client/library being used?
9. **Check connection reuse**: requests to the same origin may reuse an already-negotiated connection; do not assume every request performs a new handshake.
10. **Measure & decide policy**: if h2 is required for mandatory features, enforce it in infrastructure and the application; if it is only for performance, record metrics and accept valid h1 fallback.

You should not start by **forcing a `Connection: Upgrade` header into `HttpRequest`**. Java HttpClient manages special headers and protocol negotiation; doing it manually can produce an invalid request or be blocked by the JDK.

## 13. When must the issue be solved at the server/proxy rather than in Java code?

| Symptom | Appropriate change | What not to do |
| --- | --- | --- |
| HTTP/1.1-only server | Configure/deploy HTTP/2 on the server or edge if needed | Just set `version(HTTP_2)` and assume h2 is guaranteed |
| HTTPS does not negotiate `h2` | Check TLS ALPN and support on both sides | Disable certificate verification to look for h2 |
| Proxy only uses h1 | Check proxy support and route | Assume client config forces the proxy to upgrade |
| Redirect to an h1 origin | Observe final URI and intermediate responses | Assign one version to the entire chain |
| Only some requests get h2 | Inspect origin/connection/server pool/timing | Conclude “HttpClient is random” without evidence |
| Need h2-specific gRPC | Use a stack and infrastructure supporting HTTP/2 end-to-end | Only check the response after an important POST |
| Mismatch but HTTP status 200 and API is stable | Monitor metrics and evaluate whether adjustment is needed | Unnecessarily retry the entire request |
| `SSLHandshakeException` occurs | Fix certificate/TLS protocol trust and endpoint policy | Call a TLS error an HTTP/1.1 downgrade |
| `HTTP_1_1` with high latency | Analyze concurrency, connection pooling, proxy, response size | Treat the version label alone as the sole cause |

**The right mindset:** protocol policy spans **the entire path**, not a single Java enum alone.

## 14. Testing to avoid misinterpretation

Write tests with clear conditions:

| Test | Setup | Expectation |
| --- | --- | --- |
| Java 17 default | `HttpClient.newHttpClient()` | `client.version() == HTTP_2` (preferred) |
| Request with no override | `newBuilder(uri).GET().build()` | `request.version().isEmpty()` |
| Request override HTTP/1.1 | `.version(HTTP_1_1)` | `request.version().get()==HTTP_1_1` |
| h1-only server, client prefers h2 | Send GET to `jdk.httpserver` | `response.version()==HTTP_1_1`; status can still be 200 |
| h1-only server, request prefers h2 | Request override HTTP_2 | Actual is still HTTP_1_1 |
| Client prefers h1, request prefers h2 | Request override HTTP_2 | Effective preference h2, actual depends on server |
| `sendAsync` | `client.sendAsync(...).get()` | Async completion does not force h2 |
| Server truly supports h2 TLS | HTTPS + ALPN selects `h2` | Actual `HTTP_2` when negotiation succeeds |
| ALPN does not select h2 | Server/proxy does not select `h2` but supports h1 | Actual `HTTP_1_1` if fallback is valid |
| TLS handshake failure | Invalid certificate/TLS | Exception, no HTTP response version |
| Cross-origin redirect | `followRedirects(...)` configured | Observe final & intermediate versions separately |
| HTTP status 404 | Valid HTTP response | `response.version()` is still readable |
| Policy requiring h2 | `if (resp.version()!=HTTP_2)` | Mismatch is detected **after the request** |
| Client uses proxy | Configure proxy in staging test | Version confirmed from actual on that path |
| Multiple responses from same client | Send sequentially to h1/h2 servers | Do not assume all responses have the same version |

When testing with HTTPS, create a server with a **trusted test** certificate and control ALPN; do not disable validation in main code. When testing locally over `http://127.0.0.1`, you only measure **the version negotiation of that environment**, do not generalize to production.

### 14.1. Tests should not depend on external environments

The two programs in sections 6–7 use loopback and an in-JDK server, so:

- They do not depend on public Internet websites changing their policies.
- They do not depend on public certificates/proxies/VPNs.
- They do not need to time an h2 handshake to confirm the objective.
- They produce deterministic output because the server only supports h1.
- They prove **h2 preference != h2 actual**, without concluding that any entire JDK/OS always uses only h1.

Important explanation: **the difference is behavior permitted by the API contract**, not an exception thrown when the client does not receive HTTP/2.

## 15. Common misconceptions

| Misconception | Why it is wrong | Correct understanding |
| --- | --- | --- |
| “`client.version()==HTTP_2` means the request just used h2” | `client.version()` is only preferred | Use `response.version()` |
| “`request.version()` empty means h1” | Empty = no override set | Inherits client preference |
| “A request specifying HTTP/2 will fail if the server is h1” | `version` is preferred where possible | The client may fall back and return an h1 response |
| “`response.version()` tells you TLS 1.3 or 1.2” | It is the HTTP version | Use separate TLS diagnostics |
| “An HTTP/1.1 response over HTTPS is definitely unencrypted” | HTTP version does not determine scheme/TLS | Check HTTPS/SSL |
| “h1 fallback automatically causes a 500 status error” | Status is independent of protocol version | Observe `statusCode()` |
| “HTTP 404 happens because the server does not support h2” | 404 is about resource/request semantics | Check URL/auth/router |
| “All requests on the same HttpClient have the same actual version” | Origin/proxy/redirect/reuse can differ | Log per response |
| “`sendAsync` will prefer h2 more than `send`” | The two APIs differ in how they await results, not server support | Expect same preference/actual |
| “If an HTTPS client supports h2, the server must automatically support h2” | Requires ALPN and compatible server/edge setup | Check h2 at each hop |
| “Cleartext HTTP uses ALPN just like HTTPS” | h2c upgrade is a different mechanism | Distinguish `http` and `https` |
| “If a proxy uses h1, the backend is definitely h1” | A proxy can switch protocols between hops | Observe on each hop |
| “If `response.version()==HTTP_1_1`, just retry the POST” | The request may have already caused side effects | Do not blindly retry; use idempotency |
| “Calling .version(HTTP_2) is strict mode” | There is no hard-fail promise in the builder | Add policy/enforcement separately |
| “An HTTP/1.1 server returning 200 means the client never tried to upgrade” | The result only shows actual, not the full negotiation sequence | Check logs/traces at the proper scope |
| “Running Java 24 with Java 17 code means the enum supports HTTP_3” | `--release 17` restricts the compile-time API; runtime may differ | Read API docs for compile/runtime JDK |
| “Java 17 `HttpClient` supports try-with-resources” | Java 17 `HttpClient` is not `AutoCloseable` | Do not use that try-with-resources syntax under `--release 17` |
| “An h1 result is a TCP error” | HTTP/1.1 is a valid protocol | Distinguish transport errors |
| “Manually adding a header will force an HTTP/2 handshake” | Negotiation is managed by the HTTP stack/proxy/server | Use API/infrastructure config |
| “The final response.version describes every redirect” | Each response may belong to a different origin/version | Use `previousResponse()` when needed |
| “A higher version automatically gives better latency for every request” | Performance depends on network, concurrency, server, head-of-line, cache | Benchmark and collect telemetry |
| “An actual h2 response proves the backend uses h2” | A proxy/gateway may change the version | Verify the backend hop if needed |

## 16. Exercises with solutions

### Exercise 1 — Client prefers h2 but h1 returns 200

~~~text
client.version()   = HTTP_2
response.version() = HTTP_1_1
response.statusCode() = 200
~~~

Must an exception be thrown?

**Answer:** No. This can be a valid fallback. If HTTP/2 is only a performance preference, accept the response and record the actual version; if HTTP/2 is mandatory, you need **a separate policy**, rather than expecting the client to throw automatically based on the preferred configuration.

### Exercise 2 — What is Optional.empty?

~~~java
HttpRequest request = HttpRequest.newBuilder(uri)
        .GET().build();
System.out.println(request.version());
~~~

If the output is `Optional.empty`, will the request use HTTP/1.1 by default?

**Answer:** False. `Optional.empty` only states that **the request did not set an override**. The client sending the request determines the default preference; Java 17 defaults the client to preferring `HTTP_2`, while actual must be read from `HttpResponse.version()`. The snippet above is a **code snippet** requiring a defined `uri` and an `HttpRequest` import.

### Exercise 3 — Client and request conflict

The client is configured with `HTTP_1_1`; the request is configured with `HTTP_2`. What is the effective preferred version? Is actual guaranteed to be HTTP_2?

**Answer:** Because the request has an override, the **effective preferred** version is `HTTP_2`; **actual** still depends on server capability, TLS/proxy/network, and may be `HTTP_1_1`.

### Exercise 4 — HTTPS TLS 1.3 returns h1

A response comes from `https://` over TLS 1.3, with `response.version()==HTTP_1_1`. Was the connection downgraded from HTTPS to HTTP?

**Answer:** No. HTTP/1.1 can still run over TLS 1.3. TLS version/security is independent of HTTP version; if HTTPS is properly authenticated, h1 fallback does not automatically lose encryption.

### Exercise 5 — Server has no h2, request succeeds

An internal server only supports HTTP/1.1. The client prefers HTTP/2 and sends a GET. Why can `HttpClient.send()` return HTTP 200 without throwing an exception?

**Answer:** Because version selection allows HTTP/1.1 fallback. HTTP status 200 indicates a successful response in HTTP semantics; `response.version()` = HTTP_1_1 indicates the actual version.

### Exercise 6 — Async and version

Does `client.sendAsync(request, handler)` guarantee HTTP_2 more than `client.send(request, handler)`?

**Answer:** No. `sendAsync` refers to the **async Java API**, not the HTTP protocol version. Both follow client/request preferences and server/proxy negotiation.

### Exercise 7 — Redirect between two origins

A client sends a request to origin A and is redirected to B. The final response version is HTTP/1.1, while A supports HTTP/2. Can you conclude that A only uses HTTP/1.1?

**Answer:** No. The final response belongs to origin B and may have a different version from A. Inspect `response.uri()`, `response.request()`, and `response.previousResponse()`, or the logs for each hop.

### Exercise 8 — Requiring HTTP/2 before payment

An application creates an order with POST and only discovers after the response that actual is HTTP_1_1, not h2. Should it POST again to “get h2”?

**Answer:** No. The server may have already created the order. Resending can easily cause duplicates; if the business requires h2, enforce capability/policy on the server/gateway side and use idempotency keys to guard against network failures, **not** version mismatch as a reason for blind retries.

### Exercise 9 — Proxy and upstream

A Java client receives an HTTP/2 response from a reverse proxy, while the proxy sends HTTP/1.1 to the backend. Is `response.version()==HTTP_2` contradictory?

**Answer:** No. The Java response version is **the version the client used for the response on the client-facing hop**; the proxy can use a different protocol with the upstream backend.

### Exercise 10 — Identifying the error

A client calls `send()` and receives `SSLHandshakeException`. Can you record the metric `actualVersion=HTTP_1_1` for that request?

**Answer:** No. The TLS handshake did not complete, so there is no `HttpResponse`; **the actual HTTP version was never observed**. Record the TLS error separately, and do not fill in h1.

### Exercise 11 — HTTP/3 and Java 17

Does the following code compile with `javac --release 17`?

~~~java
HttpClient.Version desired = HttpClient.Version.HTTP_3;
~~~

**Answer:** No. Java 17 only defines `HTTP_1_1` and `HTTP_2`. If the application uses a newer JDK, you must read the docs for the exact version; do not infer HTTP/3 support from the Java 17 API.

### Exercise 12 — Getting preferred and actual for logging

Write an expression to determine the effective preferred version whether or not the request has an override; then get the actual version.

**Answer:**

~~~java
HttpClient.Version preferred =
        request.version().orElse(client.version());
HttpClient.Version actual = response.version();
boolean mismatch = preferred != actual;
~~~

This is a **code snippet** after receiving a response. The result is used for observability or policy; it does not prove that other requests from the same client will also mismatch.

## 17. Checklist for applying to Java HTTP clients

- [ ] I distinguish `client.version()` = preferred, `request.version()` = Optional override, `response.version()` = actual.
- [ ] If `request.version().isEmpty()`, I use the client preference rather than assuming HTTP/1.1.
- [ ] I know Java 17 prefers `HTTP_2` by default, which does not mean every response is h2.
- [ ] I do not treat `version(HTTP_2)` as a hard requirement.
- [ ] I log the actual version **from each request's response**, along with status and a sanitized URI.
- [ ] I separate DNS/TCP/TLS errors from HTTP status and HTTP version mismatches.
- [ ] I distinguish h2c upgrade over cleartext HTTP from ALPN over HTTPS/TLS.
- [ ] I inspect proxy/redirect/backend hops when the version differs from expectations.
- [ ] If h2 is required for business logic, I have server/proxy enforcement and dedicated protocol tests; not just post-response assertions.
- [ ] I do not retry POST/payment requests due to actual version differing from preferred without an idempotency policy.
- [ ] I verify that h1 fallback still preserves HTTPS/TLS when the URI/connection is appropriate.
- [ ] I do not mix up HTTP_1_1 / HTTP_2 with TLS_1_2 / TLS_1_3.
- [ ] I do not use the Java 17 API to claim that all future JDKs only have two enum constants.
- [ ] I test behavior with `javac --release 17` when Java 17 compatibility is required.
- [ ] I do not use `try (HttpClient ...)` when compiling with target Java 17.
- [ ] I test on loopback with a controllable server to distinguish “h2 not supported” from network failure.

## 18. Official references

- [Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): `client.version()` is preferred, defaults to HTTP/2, note proxy constraints.
- [Java SE 17 — HttpClient.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Builder.html): `version(HTTP_2)` prefers when possible, HTTP/2 upgrade behavior and HTTP/1.1 fallback.
- [Java SE 17 — HttpClient.Version](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Version.html): the enum constants `HTTP_1_1` and `HTTP_2` in Java 17.
- [Java SE 17 — HttpRequest](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.html): `request.version()` returns Optional; when empty, the client determines the preferred version.
- [Java SE 17 — HttpRequest.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html): request-level `version(...)` preference.
- [Java SE 17 — HttpResponse](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.html): actual `version()`, `request()`, `uri()`, `previousResponse()`.
- [Java SE 17 — HttpServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): embedded server in `jdk.httpserver` for local HTTP/1.1 demos.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): common methods/statuses/resources across HTTP versions.
- [RFC 9112 — HTTP/1.1](https://www.rfc-editor.org/rfc/rfc9112): HTTP/1.1 message/framing.
- [RFC 9113 — HTTP/2](https://www.rfc-editor.org/rfc/rfc9113): HTTP/2 framing/connection, h2c and TLS contexts.
- [RFC 7301 — TLS ALPN](https://www.rfc-editor.org/rfc/rfc7301): application-layer protocol negotiation over TLS.
- [Java SE 26 — HttpClient.Version](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpClient.Version.html): example of a newer JDK that may have the HTTP_3 enum; always check docs for the deployment version.

**Key takeaway:** `HttpClient.Builder.version(...)` and `HttpRequest.Builder.version(...)` express **the version you want to use**, whereas `HttpResponse.version()` expresses **the version actually used**. Preferred HTTP/2 with actual HTTP/1.1 can be normal fallback due to the server, TLS ALPN, h2c, proxy, or routing; it is **not synonymous with an HTTP error, a TLS error, or losing HTTPS security**. When HTTP/2 is truly required, verify the response and design enforcement at the right hop and at the right time — do not rely on the builder alone.
