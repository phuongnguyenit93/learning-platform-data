# HTTP/2 Negotiation, Protocol Upgrade, and Fallback to HTTP/1.1 in Java HttpClient

## 1. The Problem: Requesting HTTP/2 Does Not Guarantee Using HTTP/2

When using `java.net.http.HttpClient` (Java 17+), we can write:

```java
HttpClient client = HttpClient.newBuilder()
        .version(HttpClient.Version.HTTP_2)
        .build();
```

However, **`HTTP_2` here is a preferred/requested version if possible**, not proof that every request will go over HTTP/2. If the server, proxy, TLS ALPN, or deployment conditions do not support HTTP/2, the client **may use HTTP/1.1**. With Java 17's `HttpClient.Builder`, when `version(...)` is not called, the client **defaults to preferring HTTP/2**.

The question to answer after a request is not "which version did I configure?", but **"which HTTP version did the response actually use?"**. The API to determine this is:

```java
HttpResponse<String> response = client.send(
        request, HttpResponse.BodyHandlers.ofString());
System.out.println(response.version());
```

This is a *code snippet* that requires the `client` and `request` variables along with the `HttpResponse` import. `response.version()` returns `HTTP_2` or `HTTP_1_1` according to the version **actually used for the response**; `client.version()` only returns the **client's preferred version**. Do not confuse the two values.

This lesson distinguishes three important cases:

1. `https://` → HTTP/2 selection via **TLS Application-Layer Protocol Negotiation (ALPN)**, not using HTTP/1.1 `Upgrade`/`101` to enable HTTP/2.
2. `http://` (without TLS) → Java 17 `HttpClient` may attempt **HTTP/1.1 `Upgrade: h2c`** in certain connections; if the server does not upgrade, the response continues on HTTP/1.1. **The h2c Upgrade mechanism is a historical path, deprecated by RFC 9113**, and is not the default recommendation for new systems.
3. The client sets `HTTP_2` but the peer only supports HTTP/1.1 → the client can **fallback** to HTTP/1.1; you need to measure the actual result, not force the server into HTTP/2.

## 2. HTTP/1.1 and HTTP/2 Differ at the Wire Representation Layer

Both versions generally share the same **HTTP semantics**: `GET/POST` methods, URIs, status codes, `Content-Type`, caching, authentication, and many header fields still retain their familiar meanings. The major difference lies in framing and multiplexing.

| Aspect | HTTP/1.1 | HTTP/2 |
| --- | --- | --- |
| Wire representation | Text-based start-line/header section, byte framing per HTTP/1.1 | Binary frames with types such as `HEADERS`, `DATA`, `SETTINGS` |
| Concurrent exchanges | Often requires multiple connections to reduce application head-of-line blocking; pipelining is rarely used | Multiple concurrent **streams** over a single HTTP/2 connection |
| Header compression | No HTTP/2 HPACK | HPACK for header fields |
| Message delimitation | HTTP/1.1 framing, `Content-Length`, or transfer coding per RFC | Stream ID, flags/frames, and end-of-stream; does not use HTTP/1.1 chunk syntax |
| Data flow regulation | Primarily relies on transport and message rules | HTTP/2 has per-stream and per-connection **flow control** |
| Request/response semantics | Method/status/header fields | Mostly preserved, though wire syntax differs |
| Security | Can run over cleartext TCP or TLS | Can be HTTP/2 over TLS (`h2`) or HTTP/2 cleartext with prior knowledge (`h2c`, without TLS) |

**HTTP/2 does not mean all requests are faster.** Multiplexing reduces the need for multiple TCP connections, but performance still depends on network latency, server load, TLS, flow control, stream organization, proxies, and TCP-level head-of-line blocking on packet loss. HTTP/2 also has resource limits such as the number of concurrent streams; it should not be treated as an automatic throughput switch.

With Java `HttpClient`, HTTP/1.1 or HTTP/2 framing is handled by the library. Do not write application code trying to force `Transfer-Encoding: chunked` into HTTP/2; that transfer coding belongs to HTTP/1.1, while HTTP/2 has its own DATA frame representation.

## 3. `https://`: Negotiating HTTP/2 via TLS ALPN, Not 101

For an HTTPS URL, the client establishes a TCP/TLS connection. During the TLS handshake, the client and server negotiate the **application protocol** via ALPN:

```text
Java HttpClient                         HTTPS Server
       |                                     |
       +--------- TCP connect ------------->|
       |                                     |
       | TLS ClientHello                     |
       | ALPN: h2, http/1.1  --------------->|
       |                                     |
       | TLS handshake, certificate           |
       |<--------- ALPN selects "h2" -------|
       |                                     |
       |   HTTP/2 connection preface         |
       |   SETTINGS + HEADERS/DATA frames    |
       +------------------------------------>|
       |<--------- HTTP/2 frames ------------|
       |
       +--> response.version() == HTTP_2
```

If the server only accepts HTTP/1.1 and both sides still agree on a compatible protocol:

```text
TLS ALPN selects "http/1.1"
      |
      v
TLS handshake succeeds
      |
      v
Application exchanges HTTP/1.1 over the TLS connection
      |
      v
response.version() == HTTP_1_1
```

**Important notes:**

- The ALPN identifier string for HTTP/2 over TLS is **`h2`**, and for HTTP/1.1 is **`http/1.1`**.
- **`h2c` is not the ALPN identifier for HTTP/2 over TLS.** RFC 9113 requires HTTP/2 over HTTPS to be negotiated via ALPN.
- If ALPN selects `h2`, both sides use the **HTTP/2 connection preface and frames** after the TLS handshake. **There is no step of sending HTTP/1.1 `Upgrade: h2c` and waiting for `101 Switching Protocols`** on this HTTPS path.
- TLS must still verify the certificate chain and **hostname**, without lowering security when the protocol version is HTTP/1.1. Falling back to HTTP/1.1 **inside HTTPS** does not turn `https://` into `http://`.
- The HTTP version selected by ALPN is distinct from the **TLS version**: HTTP/2 can run over TLS 1.2 or TLS 1.3 per standard constraints, not every `HTTP_2` implies `TLSv1.3`.
- If the server does not provide a valid certificate and the handshake fails, TLS/certificate errors **must not be handled by disabling verification** to force a "fallback" connection.

ALPN and SNI are also different: **SNI** sends the logical hostname so the server can select the virtual host/certificate; **ALPN** negotiates the application protocol; **certificate validation** authenticates the server's identity. Do not use SNI as proof that HTTP/2 was selected or that hostname checking was performed.

## 4. When HTTP/2 Support Over TLS Is Unavailable

You may encounter the following situations:

| Server / HTTPS path | Symptom | Behavior to understand |
| --- | --- | --- |
| ALPN successfully negotiates `h2` | Actual response `HTTP_2` | Client sends/receives HTTP/2 frames |
| ALPN selects `http/1.1` | Response `HTTP_1_1` | This is HTTP/1.1 **still protected by TLS** |
| Server/intermediary does not support `h2` | May use HTTP/1.1 if available | Must confirm via the actual response |
| No common protocol / incompatible TLS | Request may **fail** | There is no guarantee that fallback will always succeed |
| Untrusted certificate / hostname mismatch | TLS handshake fails | Do not retry by trusting all certificates or switching to `http://` |
| HTTP/2 supported only at CDN, origin uses HTTP/1.1 | Client sees the version of the connection **it used** | Do not infer the version on the hop from CDN to origin |

Do not misunderstand "fallback" as every HTTP/2 request automatically retrying over HTTP/1.1 in all situations. It usually describes **selecting the protocol version during connection setup or confirming that the server does not accept an upgrade**, whereas network errors mid-request, timeouts mid-body, business error responses, or proxy failures may not allow a safe retry. HTTP retry mechanisms have their own rules, especially for state-changing requests.

## 5. `http://`: h2c, HTTP/1.1 Upgrade, and Standards History

For cleartext HTTP (without TLS), **ALPN is not exchanged in a TLS handshake** because there is no TLS. There are two historical paths to start HTTP/2 over cleartext TCP:

1. **HTTP/1.1 `Upgrade: h2c`**: the client sends an HTTP/1.1 request proposing to switch to HTTP/2. An agreeing server may return `101 Switching Protocols`; afterward, both sides switch to the HTTP/2 connection preface and frames. This mechanism was described in RFC 7540 (2015).
2. **HTTP/2 prior knowledge**: the client **knows in advance** that the server accepts cleartext HTTP/2 and sends the HTTP/2 connection preface immediately, without starting with an HTTP/1.1 Upgrade request. RFC 9113 (2022) describes this path.

**Very important standards update:** RFC 9113 **deprecated** the HTTP/1.1 `Upgrade: h2c` mechanism and the related `HTTP2-Settings` field, because they were not widely deployed; current specifications describe cleartext HTTP/2 primarily via **prior knowledge**. However, Java 17 `HttpClient` in a specific case can still **emit an h2c Upgrade proposal** when preferring HTTP/2 over `http://`. The test in section 8 will show the empirical behavior of the JDK used, without claiming that all current clients/JDKs/servers behave identically.

### What Does an HTTP/1.1 Upgrade Proposal Look Like?

An illustration of a cleartext request might contain:

```http
GET /version HTTP/1.1
Host: 127.0.0.1:8080
Connection: Upgrade, HTTP2-Settings
Upgrade: h2c
HTTP2-Settings: <valid encoded settings value>

```

This is a **header structure illustration**, not a raw request you can copy and send: `HTTP2-Settings` requires a properly formatted value, and HTTP/1.1 must use CRLF on the wire. **`Connection` specifies hop-by-hop fields**; intermediaries must not forward them with improper semantics.

Under the general HTTP/1.1 Upgrade mechanism, the server can **ignore** the proposal and return a normal HTTP/1.1 response:

```http
HTTP/1.1 200 OK
Content-Type: text/plain
Content-Length: 2

OK
```

In that case, it remains HTTP/1.1; the client must not assume that simply sending `Upgrade: h2c` enabled HTTP/2 on the server. If the server actually accepts the historical Upgrade mechanism, a `101 Switching Protocols` response indicates the transition step, and then the connection speaks the new protocol. However, **do not design new HTTP/2 systems to rely on h2c Upgrade by default**, because this mechanism is deprecated in the current RFC and often does not traverse proxies as expected.

### HTTP/2 Prior Knowledge Is Not "Client Just Sends h2c and It Works"

If a client sends the HTTP/2 preface to a server that only understands HTTP/1.1, the server may treat it as an invalid request and close the connection. Therefore, **prior knowledge requires knowing the capability in advance**, not a blind trial approach that always has a fallback. Depending on the Java API/version, you cannot infer from `client.version(HTTP_2)` that it automatically switches every `http://` request to prior-knowledge mode.

**Security boundary:** h2c uses **unencrypted** HTTP/2. It does not provide TLS certificates, hostname authentication, or transport confidentiality. For sensitive data, prefer `https://` with authenticated TLS.

## 6. HTTP/1.1 `Upgrade` and `101 Switching Protocols` Do Not Mean HTTP/2

`Upgrade` is a general HTTP/1.1 mechanism per RFC 9110 that can be used to propose switching to **another protocol over the same connection**, such as WebSocket in appropriate cases.

```text
HTTP/1.1 request:
  Connection: Upgrade
  Upgrade: <requested-protocol>

Server can:
  - 101 Switching Protocols + Upgrade: ...   -> accept switch
  - normal response (e.g., 200)              -> ignore proposal
  - reject/error per policy
```

Distinguish clearly:

- HTTP/2 **over HTTPS** is not enabled via `101`; it is negotiated via **TLS ALPN**.
- **h2c Upgrade** is a **historical** HTTP/1.1 route into cleartext HTTP/2, now deprecated per RFC 9113.
- **WebSocket Upgrade** in HTTP/1.1 has its own `101` mechanism. `java.net.http.HttpClient.newWebSocketBuilder()` is for WebSocket; it is not an API to force a regular HTTP request onto HTTP/2.
- `101` is not a status code saying "the request completed successfully via HTTP/2"; it announces a protocol change. After the switch, payloads/responses must still be processed according to the new protocol.

If a proxy returns a `101` response for another protocol, do not confuse it with HTTP/2. If an HTTPS request has `response.version()==HTTP_2` without a `101`, **that is normal**.

## 7. Java 17 API: Client Preference, Request Override, and Actual Response

Java `HttpClient` has these places to select the protocol version:

```java
HttpClient client = HttpClient.newBuilder()
        .version(HttpClient.Version.HTTP_2)
        .build();

HttpRequest request = HttpRequest.newBuilder(uri)
        .GET()
        .build();
```

*Code snippet inside a method with `URI uri` and imports.* Here `client.version() == HTTP_2` only describes a **preference**. `request.version()` is an `Optional<HttpClient.Version>`; if not set per-request, it is **empty**, and the request inherits the HttpClient's preference when sent.

If only one request should use HTTP/1.1:

```java
HttpRequest request11 = HttpRequest.newBuilder(uri)
        .version(HttpClient.Version.HTTP_1_1)
        .GET()
        .build();
```

This is a **request-level override** (a preference applied to that request), which does not change the client configuration for other requests. You do not need to create a new client for each request just to switch versions; `HttpClient` is designed for connection pool reuse.

After sending:

```java
HttpResponse<Void> response = client.send(
        request11, HttpResponse.BodyHandlers.discarding());

System.out.println("preferred at client: " + client.version());
System.out.println("actual on response: " + response.version());
```

*Non-standalone code snippet.* Distinguish the three values:

| Value | Meaning |
| --- | --- |
| `client.version()` | The **client's preferred** version, defaulting to `HTTP_2` in Java 17 |
| `request.version()` | `Optional` containing the override when the request sets one; empty if inheriting from the client |
| `response.version()` | The HTTP version **actually used** to receive the response |

**Java 17 note:** `HttpClient` in JDK 17 **does not implement AutoCloseable**, so do not write `try (HttpClient c = HttpClient.newHttpClient())` for code targeting `--release 17`. Use a reusable instance; newer JDKs add client lifecycle APIs, but the examples here maintain Java 17 compatibility.

## 8. Runnable Java 17 Example: Preferring HTTP/2 Against an HTTP/1.1-Only Server

The following loopback example requires no Internet, certificates, or external server. We use `com.sun.net.httpserver.HttpServer` as an **HTTP/1.1-only** HTTP server, then use Java 17 `HttpClient` preferring HTTP/2.

The program also has the server record **the received headers**: on the tested JDK 17, the client sends `Upgrade: h2c` and `HTTP2-Settings`. The server **does not accept the upgrade** and simply returns status `200` over HTTP/1.1. The client reports the actual version as `HTTP_1_1`, without failing just because the request preferred HTTP/2.

**File `Http2NegotiationDemo.java`:**

```java
import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public final class Http2NegotiationDemo {
    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/version", exchange -> {
            try (exchange) {
                String upgrade = exchange.getRequestHeaders()
                        .getFirst("Upgrade");
                boolean hasSettings = exchange.getRequestHeaders()
                        .getFirst("HTTP2-Settings") != null;
                String body = "upgrade=" + (upgrade == null ? "-" : upgrade)
                        + ", settings=" + hasSettings;
                byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
                exchange.getResponseHeaders().set(
                        "Content-Type", "text/plain; charset=UTF-8");
                exchange.sendResponseHeaders(200, bytes.length);
                exchange.getResponseBody().write(bytes);
            }
        });
        server.start();
        try {
            URI uri = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/version");
            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_2)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();

            HttpRequest preferredH2 = HttpRequest.newBuilder(uri)
                    .timeout(Duration.ofSeconds(5))
                    .GET()
                    .build();
            HttpResponse<String> first = client.send(preferredH2,
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));
            System.out.println("client preference: " + client.version());
            System.out.println("actual response: " + first.version());
            System.out.println("server saw: " + first.body());

            HttpRequest forceHttp11 = HttpRequest.newBuilder(uri)
                    .version(HttpClient.Version.HTTP_1_1)
                    .timeout(Duration.ofSeconds(5))
                    .GET()
                    .build();
            HttpResponse<Void> second = client.send(forceHttp11,
                    HttpResponse.BodyHandlers.discarding());
            System.out.println("request override: "
                    + forceHttp11.version().orElseThrow());
            System.out.println("override response: " + second.version());
        } finally {
            server.stop(0);
        }
    }
}
```

Run with JDK 17 having the `jdk.httpserver` module:

```bash
javac --release 17 --add-modules jdk.httpserver Http2NegotiationDemo.java
java --add-modules jdk.httpserver Http2NegotiationDemo
```

**Stdout verified on the Java 17 test environment:**

```text
client preference: HTTP_2
actual response: HTTP_1_1
server saw: upgrade=h2c, settings=true
request override: HTTP_1_1
override response: HTTP_1_1
```

Analysis:

1. **`client preference: HTTP_2`** proves the client prefers HTTP/2 — **with no guarantee that the server supports it**.
2. **`actual response: HTTP_1_1`** is the right fact to know the request received its response over HTTP/1.1.
3. **`server saw: upgrade=h2c, settings=true`** shows that in the Java 17 runtime used, the initial cleartext request included `Upgrade: h2c` and `HTTP2-Settings`. The server did not accept; did not return `101`; the result remained HTTP/1.1. **Do not treat this as a promise that every JDK/HTTP client emits h2c Upgrade**.
4. **`request override: HTTP_1_1`** confirms the second request asked for HTTP/1.1. **`override response: HTTP_1_1`** confirms the actual result.

**Example limitations:** this is local cleartext HTTP containing no sensitive data. It **does not** test TLS ALPN, a real HTTP/2 server, or communication through a proxy/CDN. Its purpose is only to demonstrate **preference vs. negotiated version** and HTTP/1.1 response behavior when the server does not upgrade. `HttpServer` here is a teaching tool, not an example of implementing an HTTP/2 or h2c prior knowledge server.

If run on another JDK version, or behind a proxy, or with a connection already cached/established in a different state, the upgrade proposal headers may differ; look at `response.version()` before drawing conclusions.

## 9. Compilable Java 17 Example to Probe a Real HTTPS Server

For a real valid HTTPS server, verify ALPN by sending a request with HTTP/2 preference and then **reading the response version**. Do not hard-code stdout for this example because it depends on the server, proxy, TLS, and DNS policies.

**File `HttpsVersionProbe.java`:**

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public final class HttpsVersionProbe {
    public static void main(String[] args) throws Exception {
        if (args.length != 1 || !args[0].startsWith("https://")) {
            throw new IllegalArgumentException("Pass an HTTPS URL");
        }
        HttpClient client = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_2)
                .followRedirects(HttpClient.Redirect.NEVER)
                .connectTimeout(Duration.ofSeconds(5))
                .build();
        HttpRequest request = HttpRequest.newBuilder(URI.create(args[0]))
                .timeout(Duration.ofSeconds(10))
                .GET()
                .build();
        HttpResponse<Void> response = client.send(request,
                HttpResponse.BodyHandlers.discarding());
        System.out.println("preferred=" + client.version());
        System.out.println("actual=" + response.version());
        System.out.println("status=" + response.statusCode());
        System.out.println("uri=" + response.uri());
    }
}
```

Compile with Java 17:

```bash
javac --release 17 HttpsVersionProbe.java
java HttpsVersionProbe https://your-valid-https-host.example/path
```

The address on the command line is only a **syntax placeholder**: replace it with an HTTPS URL you actually own or are authorized to test and that has a trusted certificate. Compilation has been verified; **no stdout from a public server is claimed**.

Meaning:

- `preferred=HTTP_2`: the program requested HTTP/2.
- `actual=HTTP_2`: the actual response used HTTP/2; over HTTPS, this is usually the result of ALPN selecting `h2`.
- `actual=HTTP_1_1`: the actual response used HTTP/1.1; this may be because the server/intermediary does not support HTTP/2, ALPN selected HTTP/1.1, or deployment constraints applied.
- `status=...` is the **HTTP status code**, not the version. A `200 OK` response can run over HTTP/1.1 or HTTP/2.
- `uri=...` indicates the response's request URI. The program sets `Redirect.NEVER` to avoid mistaking a redirect to another URL for the original endpoint.

**Do not disable TLS certificate verification or hostname checking just to achieve `HTTP_2`**. Java `HttpClient` uses the platform's TLS/HTTPS policy by default; use a valid trust store/CA when working with internal infrastructure.

## 10. Why Proxies, Reverse Proxies, and Load Balancers Can Cause Fallback

An HTTP path can have multiple **hops**:

```text
Java HttpClient
      |
      | HTTPS, ALPN h2 or HTTP/1.1
      v
Corporate Proxy / CDN / Gateway
      |
      | upstream may be HTTP/1.1 or a different HTTP/2
      v
Backend / Origin Server
```

In such environments:

- The client may negotiate HTTP/2 to the edge while the edge speaks HTTP/1.1 to the origin, or vice versa depending on the system.
- An HTTP proxy may not support HTTP/2 for the requested connection type or may have special policies; the JDK 17 `HttpClient.Builder.version(...)` documentation warns that implementation constraints **may cause HTTP/1.1 to be used when going through a proxy**.
- `Upgrade: h2c` and `Connection` are hop-by-hop in HTTP/1.1; do not expect them to pass through multiple proxies as end-to-end headers. The rarity of h2c Upgrade deployment makes it even less reliable.
- A TLS interception proxy in enterprise environments can change the actual TLS peer and certificate chain. This is a separate security/PKI policy, not Java randomly choosing HTTP/1.1.
- `response.version()` indicates the version **the client used to receive the response** per the implementation; it does not prove that the internal backend uses the same version or reveal the status of each hop.

When checking production performance, measure the protocol version both at the **client edge** and on critical upstream connections if you have observability; do not conclude that the backend supports HTTP/2 solely from `response.version()==HTTP_2` on the client.

## 11. Redirects, Origins, and Connection Reuse: Do Not Infer From One Request

An HTTP/2 connection can be reused for multiple requests/streams to an origin subject to HTTP/2 and client constraints, but that does not mean every request forever uses the same connection/version.

For example:

```text
GET https://api.example.test/data
        |
        v
302 Location: https://login.example.test/
        |
        v
GET https://login.example.test/
```

Two hostnames can lead to different endpoints, different certificates, and different ALPN capabilities. If Java `HttpClient` is configured to follow redirects automatically, `response.version()` on the final response **does not necessarily reflect the version of each intermediate response**. When analysis is needed, inspect the redirect chain via the appropriate API and log the URI, status, and version of each response. In the HTTPS example above, `Redirect.NEVER` keeps the result on the first request for accurate observation.

Similarly, HTTP/2 **coalescing** or connection reuse across origins, if implemented, must obey server authority/certificate policies and implementation rules; do not assume a single HTTP/2 connection for all hostnames or attempt to reuse a connection by bypassing certificate validation.

When debugging, distinguish:

1. The version **requested** at the client/request level.
2. The version **selected on a connection**.
3. The version **returned for a specific response**.
4. The version of the **upstream hop** behind a proxy.
5. The **TLS** version (`TLSv1.2`/`TLSv1.3`) and the HTTP version — two separate quantities.

## 12. Fallback Is Not Automatic Retry for Every Error

Enabling the `HTTP_2` preference allows fallback under valid conditions, but **does not guarantee resending the entire request over HTTP/1.1 when an error occurs**. Distinguish three types of events:

| Type | Example | Interpretation |
| --- | --- | --- |
| **Negotiation / capability** | Server only supports HTTP/1.1, client receives HTTP/1.1 response | Normal protocol fallback |
| **HTTP response** | Server returns 404, 500, 429, or 421 | HTTP-layer response; does not by itself prove ALPN/upgrade failed |
| **Transport / TLS error** | TLS handshake/certificate failure, timeout, connection reset, GOAWAY, stream error | May require dedicated error handling/retry; not safe or successful by default |

With HTTP/2, one connection can carry multiple streams; when the connection closes, unfinished streams are in different states. Do not **blindly retry POST or non-idempotent requests** just because an exception occurred while sending over HTTP/2. The other side may have already processed the operation even though the client could not read the response.

Practical principles:

- Design retries based on **request idempotency and semantics**, combined with idempotency keys for operations that create orders, charge payments, or trigger side effects.
- Configure `HttpRequest.Builder.timeout(...)` and `HttpClient.Builder.connectTimeout(...)` to control specific waiting phases; these are not a system-wide deadline policy for every background job.
- Do not downgrade from `https://` to `http://` when HTTPS ALPN/TLS fails. That is a **security downgrade**, completely different from selecting HTTP/1.1 inside HTTPS.
- If a service **requires HTTP/2**, after the response you can check `response.version()!=HTTP_2` and treat it as an **unmet protocol requirement**, instead of proceeding by default with operations that depend on HTTP/2 features.

Application-layer enforcement example (code snippet inside a method with `response`):

```java
if (response.version() != HttpClient.Version.HTTP_2) {
    throw new IllegalStateException(
            "This operation requires HTTP/2");
}
```

Note: this enforcement happens **after the request has been sent and the response received**, so it does not guarantee that an operation with side effects has not already occurred. If HTTP/2 is mandatory before sending sensitive data or non-retryable operations, API design, routing, and capability discovery must resolve this beforehand; do not only throw after the response.

## 13. When to Keep HTTP/1.1, and When to Prefer HTTP/2?

| Context | Approach |
| --- | --- |
| Modern HTTPS service, server supports HTTP/2 | Usually prefer HTTP/2; verify actual `response.version` |
| Legacy service with HTTP/1.1 only | Allow natural fallback if appropriate, or actively choose `HTTP_1_1` |
| Proxy infrastructure with HTTP/2 limitations | Measure/check proxy capability and actual version, adjust configuration |
| Protocol dependent on WebSocket | Use the WebSocket API; do not equate WebSocket Upgrade with HTTP/2 |
| Service requiring HTTP/2 features like multiplexing or a specific protocol | Verify end-to-end compatibility and enforce a reject policy if version mismatches |
| Testing on `http://localhost` with `HttpServer` | Use to teach fallback and JDK 17 h2c Upgrade, not to measure ALPN |
| System needing to transmit credentials/sensitive payloads | Keep HTTPS + trust/hostname validation; HTTP/2 does not replace TLS |
| Newly designed cleartext h2c | Review RFC 9113 prior knowledge and actual library/server support; do not rely by default on deprecated Upgrade |

HTTP/2 helps with multiplexing and reduces header overhead in many workloads, but throughput/latency still depends on connection count, streams, flow control, and resources. Do not choose HTTP/2 out of a belief that it is "twice as fast": benchmark with realistic workloads and observe the negotiated version in production.

## 14. Test Against a Matrix Instead of Running Only One URL

When building an `HttpClient` library or service used across multiple environments, test at least:

| Case | Expected if system conforms | Verification |
| --- | --- | --- |
| HTTPS server with TLS ALPN `h2` and supporting client | `HTTP_2` | `response.version()` + TLS/proxy logs |
| HTTPS server with HTTP/1.1 only | `HTTP_1_1` if fallback path exists | No 101/h2c for HTTPS |
| Untrusted HTTPS certificate or wrong hostname | Handshake fails | No automatic downgrade to cleartext HTTP |
| Cleartext HTTP server with HTTP/1.1 only | `HTTP_1_1` when server does not upgrade | Check headers and `response.version` |
| HTTP h2c prior-knowledge server | Depends on whether client actually supports that path | Do not infer from `version(HTTP_2)` that prior-knowledge preface is sent |
| With HTTP proxy | Version depends on connection path and implementation | Record proxy configuration + actual version |
| `HTTP_2` client, one request overrides `HTTP_1_1` | Individual request has HTTP/1.1 preference | Does not change global client preference |
| Redirect to another origin | Version may change per endpoint after redirect | Check each URI/response in the chain |
| HTTP/2 connection closed/reset | May raise error/timeout | Do not auto-retry requests with side effects |
| Multiple concurrent requests | HTTP/2 multiplexing if negotiated | Measure concurrency, throughput, and flow-control/backpressure |

If you create a test server with Java `HttpServer` from the `jdk.httpserver` module, do not mistake it for an HTTP/2 server. Also use an HTTPS/HTTP2 server with ALPN support, such as a configured staging environment, to test **the successful `HTTP_2` branch**. Staging results must be actually observed; do not write fabricated stdout for a server that has not been run.

## 15. Logging and Diagnostics Tips for "HTTP_2 Enabled Yet Still HTTP_1_1"

Prioritize collecting verifiable information:

```text
URI scheme:        https or http
Original host:     api.example.com
Client preference: HTTP_2
Request override:  absent / HTTP_1_1 / HTTP_2
Response version:  HTTP_1_1
HTTP status:       200
Redirect:          followed? final URI?
Proxy configured:  yes/no, proxy/transport type
TLS negotiated:    h2 / http/1.1 (if ALPN logs are available)
```

Diagnostic questions in order:

1. Is the URL actually `https://` or `http://`? For HTTPS check **ALPN**; for cleartext HTTP check the HTTP/2 discovery mechanism (h2c/prior knowledge).
2. Did you only check `client.version()` or did you check `response.version()`?
3. Is there an accidental `request.version(HTTP_1_1)` override?
4. Does the server have **ALPN `h2` enabled** on that exact endpoint/port, or does it only advertise HTTP/2 support on another port/CDN?
5. Is there a proxy/VPN/service mesh/load balancer in between?
6. Did the certificate and TLS handshake pass? Do not use insecure HTTP fallback to "solve" TLS errors.
7. Was there a redirect to another host with different capabilities?
8. Are HTTP/2 server errors, connection resets, or concurrent stream limits causing fallback/exceptions?
9. Is the code manually setting hop-by-hop headers `Connection`, `Upgrade`, `HTTP2-Settings`, or trying to force wire frames? Let the library manage the negotiated protocol.
10. Is the HTTP/2 capability **measured at the client edge** the same as what the backend service requires?

To pinpoint failures, you can use TLS/HTTP client logging appropriate to your JDK version and server tools, but do not log authorization tokens, secret cookies, or personal payloads. Very verbose debug logging can increase cost/latency and leak data.

## 16. Common Mistakes and Fixes

| Misconception / wrong code | Why it is wrong | How to handle |
| --- | --- | --- |
| `client.version()==HTTP_2` means all responses are HTTP/2 | That is only a preference | Use `response.version()` |
| `Request.Builder.version(HTTP_2)` guarantees the server has HTTP/2 | Client does not control server/proxy | Observe negotiated version and capability |
| `https://` needs `Upgrade: h2c` and status 101 | HTTPS HTTP/2 uses TLS ALPN | Do not manually add h2c headers |
| `http://` has HTTP/2 so data is encrypted | h2c has no TLS | Choose HTTPS when security is needed |
| Seeing `Upgrade: h2c` means it definitely upgraded to HTTP/2 | Server can ignore it and return 200 | Read `response.version` / actual protocol |
| Treating h2c Upgrade as the currently recommended standard | RFC 9113 deprecated this mechanism | Use TLS ALPN or prior knowledge per actual support |
| HTTP/1.1 fallback inside HTTPS loses TLS | Application version differs from transport security | Keep cert verification, stay on HTTPS |
| Wrong TLS certificate, disabling trust manager to "use HTTP/2" | Loses server authentication | Fix certificate/trust/hostname |
| Using status 200 to prove HTTP/2 | Status and version are independent | Log both status and `response.version` |
| Using the final `response.version` to conclude about the initial redirect chain | Redirects can change endpoint/version | Inspect each response/URI |
| Using `HttpClient` in try-with-resources with `--release 17` | Java 17 HttpClient is not AutoCloseable | Reuse instance; manage lifecycle per JDK version |
| HTTP/2 always reduces latency / has no head-of-line blocking | Flow control/TCP packet loss still affects it | Benchmark and observe performance |
| Unconditionally resending POST after GOAWAY/timeout | Side effects may have already executed | Retry/idempotency policy |
| One origin having HTTP/2 means every proxy/backend hop has HTTP/2 | Version is per hop | Measure each hop when needed |
| Manually forcing `Connection`/`Upgrade` headers in Java HttpClient | The library controls framing and certain headers | Use the version preference API, let the HTTP stack build the request |
| Not handling the case where the server lacks HTTP/2 | Features requiring h2 may fail | Fallback policy or fail-closed when h2 is mandatory |

## 17. Self-Check Exercises

**Question 1.** `HttpClient.newBuilder().version(HTTP_2).build()` sends a request to a server that only supports HTTP/1.1 and receives a normal response. What can `client.version()` and `response.version()` be respectively? Which field proves the version used?

**Question 2.** An application calls `https://api.example.test/data` and wants HTTP/2. Does it need to send HTTP/1.1 `Upgrade: h2c`? Which application protocol is sent in ALPN?

**Question 3.** JDK17 HttpClient sends `Upgrade: h2c` to an HTTP/1.1 loopback server, and the server returns `200 OK` without returning `101`. Has the client switched to HTTP/2? Why?

**Question 4.** A new server wants to support cleartext HTTP/2. Why should it not be designed to rely solely on historical h2c Upgrade? What condition does `prior knowledge` have?

**Question 5.** There is a reverse proxy: the client speaks HTTP/2 with the CDN, but the CDN speaks HTTP/1.1 with the origin. What can `response.version()` on the client be? Does that reveal the upstream version?

**Question 6.** An HTTPS handshake fails certificate validation; a developer proposes changing the URL to `http://` or using trust-all so HTTP/2 can run. What are the risks? How does HTTP version fallback differ from a security downgrade?

**Question 7.** A payment POST was sent on an HTTP/2 stream, and the connection reset before the response. Should it be automatically retried immediately? What mechanism is needed?

**Question 8.** The client defaults to HTTP_2, but one request has `.version(HTTP_1_1)`. Does the request-level setting change the client version for the remaining requests? Where do you check the result?

**Question 9.** When `response.statusCode()==200` and `response.version()==HTTP_1_1`, can we say the API succeeded but did not use HTTP/2? When must the version be treated as a business condition?

**Suggested Answers:**

1. Client preference `HTTP_2`; actual response can be `HTTP_1_1`. You must use `response.version()`.
2. No. HTTPS uses TLS ALPN with `h2` (and possibly `http/1.1`), not via `101/h2c Upgrade`.
3. No. The server ignored the proposal and returned HTTP/1.1; status 200 is a normal response, not an upgrade.
4. RFC 9113 deprecates h2c Upgrade. Prior knowledge is only valid when the client **knows in advance** that the server accepts cleartext HTTP/2 and has a supporting implementation.
5. The client may see `HTTP_2` for client↔CDN, but it does not prove CDN↔origin is also H2.
6. Switching to cleartext HTTP or trust-all loses confidentiality/authentication; selecting HTTP/1.1 **over the same secure HTTPS** differs from dropping HTTPS.
7. Do not retry blindly. Use an idempotency key, check processing state, and apply a safe retry policy.
8. No; the override applies to the individual request. Check `response.version()`, while `client.version` remains the client-level preference.
9. Yes. If the application requires HTTP/2, there must be a verify/reject policy at the protocol/capability level, not just the status code.

## Official Documentation

- [Java SE 17 — HttpClient.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Builder.html): `version(HttpClient.Version)`, HTTP/2 preference, HTTP/1.1 fallback, and proxy constraints.
- [Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): `version()`, `send(...)`, and connection/client configuration.
- [Java SE 17 — HttpRequest.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html): per-request version preference, `timeout`.
- [Java SE 17 — HttpRequest](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.html): `version()` returns Optional; override vs. inherit.
- [Java SE 17 — HttpResponse](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.html): `version()` is the actual response version.
- [RFC 9113 — HTTP/2](https://www.rfc-editor.org/rfc/rfc9113.html): ALPN `h2` for HTTPS, cleartext prior knowledge, and deprecation of h2c HTTP/1.1 Upgrade.
- [RFC 9110 — HTTP Semantics, §7.8 Upgrade](https://www.rfc-editor.org/rfc/rfc9110.html#section-7.8): `Upgrade` and `101 Switching Protocols` in HTTP/1.1 in general.
- [RFC 7540 — HTTP/2 (obsoleted by RFC 9113)](https://www.rfc-editor.org/rfc/rfc7540.html): history of h2c Upgrade/HTTP2-Settings, not recommended for new deployments.
- [Java SE 17 — HttpServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): local HTTP server used for testing HTTP/1.1 fallback.
