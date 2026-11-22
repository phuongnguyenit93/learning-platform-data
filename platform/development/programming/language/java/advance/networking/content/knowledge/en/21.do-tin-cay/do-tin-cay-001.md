# Classifying DNS, Bind, Connect, Route, Read, TLS, and Protocol Errors in Java Networking

## Objectives

An “unable to call API” error can occur **before a TCP connection exists**, **during TCP setup**, **after TCP has connected**, **during the TLS handshake**, **while waiting for data**, or **after a valid HTTP response has already been received**. All of these sometimes get logged as a vague message like “network error”, leading to the wrong fix: retrying repeatedly even though the machine is binding to a port already in use, changing DNS even though the server is refusing connections, or increasing the read timeout when the TLS certificate is invalid.

This lesson belongs to the **Reliability** context of Java Networking, with one core mission: **classify errors by phase and evidence**, not just by the wording of the exception message. The phases to distinguish are:

1. **DNS / name resolution** — determining the IP address from a hostname.
2. **Bind / claiming a local address** — selecting a local IP/port for a listener or socket.
3. **Connect / establishing a connection** — reaching the remote IP/port and encountering refused/timeout.
4. **Route / network path** — local route, gateway, firewall, reachability.
5. **Read / receiving data** — timeout, EOF, reset, truncated data while the stream is active.
6. **TLS / authentication and secure channel negotiation** — trust chain, hostname, certificate, protocol/cipher.
7. **Protocol / application protocol content** — HTTP framing/status/method/header, WebSocket upgrade, payload contract, and malformed format.

You will learn how to read **`UnknownHostException`, `BindException`, `ConnectException`, `NoRouteToHostException`, `SocketTimeoutException`, `SSLHandshakeException`, `ProtocolException`, `EOFException`, `HttpConnectTimeoutException`, `HttpTimeoutException`** in the proper context. There are four standalone Java 17+ programs: (1) an exception classifier, (2) testing bind/connect/read using loopback, (3) a valid HTTP `503` compared against an API `ProtocolException`, and (4) a TLS connection to a listener that speaks only plaintext HTTP. The hands-on results were compiled with `javac --release 17` and run on loopback.

**Core principle:** an exception class is **evidence**, not the sole explanation. One root cause can produce different exceptions depending on the OS/JDK/proxy and timing, while a single exception like `SocketTimeoutException` can indicate either connect or read. Always combine **callsite + phase + root cause + server logs + network context**.

## 1. Connection Flow Map: Where Can an Error Occur?

For a Java client calling an HTTPS API, a simplified model is:

```text
URI: https://api.example.test/orders
  │
  ▼
[1] Parse URI / validate configuration, proxy, and hostname
  │       syntax/config error → IllegalArgumentException, URISyntaxException...
  ▼
[2] DNS / name lookup (origin or proxy hostname depending on configuration)
  │       UnknownHostException / resolver error / resolver timeout
  ▼
[3] Bind local socket, choose local IP and ephemeral port
  │       BindException / SocketException
  ▼
[4] Route + TCP connect to remote endpoint/proxy
  │       NoRouteToHostException, ConnectException,
  │       SocketTimeoutException / HttpConnectTimeoutException...
  ▼
[5] TLS handshake if HTTPS (or after CONNECT proxy tunnel)
  │       SSLHandshakeException / SSLProtocolException / SSLException;
  │       some connection drops still manifest as SocketException
  ▼
[6] Send HTTP request headers/body
  │       IOException, Broken pipe, Connection reset, timeout...
  ▼
[7] Read HTTP response status/headers/body
  │       SocketTimeoutException, premature EOF, malformed protocol;
  │       or a VALID HTTP response with status 401/404/429/503
  ▼
[8] Validate content and business outcome
          JSON schema error, 422 validation, authorization,
          idempotency, server commit/retry ambiguity...
```

This is a **logical diagram**, not a guarantee that every HTTP client executes these steps as separate functions. For example, an HTTP client with a connection pool **can skip DNS/bind/connect/TLS** on a subsequent request when reusing an eligible connection. Proxy DNS, HTTP/2 connection reuse, and TLS session resumption can also make the observed order more complex.

### Why Not Just Look at the Last Line of the Stack Trace?

`java.net.SocketTimeoutException: Read timed out` sounds like a “general network error”, but it specifically indicates **the read operation timed out**; it is not enough to know whether the server received the request. Meanwhile, `ConnectException: Connection refused` indicates that TCP setup was rejected at an endpoint, **not** that DNS failed. If the stack trace is wrapped by `ExecutionException`/`CompletionException`, the actual class to inspect is the **inner cause**.

**An important point:** Do not classify by searching for substrings like `"refused"`, `"unreachable"`, or `"timed out"` in `getMessage()` before checking the exception type/callsite. Messages depend on the OS, locale, and implementation. Use `instanceof`, preserve the cause chain, and supplement with the instrumented phase.

## 2. Java 17 Quick Classification Table

| Phase | Common exception/symptom | Possible meaning | First things to check |
|---|---|---|---|
| DNS | `UnknownHostException` | Could not resolve IP for hostname through the active resolver | Hostname, DNS resolver, hosts file, proxy lookup |
| Bind | `BindException` | Cannot bind local IP/port, usually due to port already in use or unavailable address | Local IP/port, other listeners, bind permissions |
| Connect | `ConnectException` | TCP connection failed, typically connection refused | Remote host/port and listener, firewall policy |
| Route | `NoRouteToHostException` | Host/network unreachable; route/firewall/ICMP may be involved | Route table, gateway, security groups, VPN |
| Connect-timeout (raw Socket) | `SocketTimeoutException` from `Socket.connect(addr, timeout)` | Timed out waiting to connect | `connect` callsite, SYN/SYN-ACK, and network path |
| Read-timeout (raw Socket) | `SocketTimeoutException` from `InputStream.read()` with `setSoTimeout` | Timed out waiting for data | Server progress, response framing, SO_TIMEOUT |
| TLS handshake | `SSLHandshakeException` | Client/server could not negotiate/verify TLS | Chain/CA, hostname, protocol, SNI, mTLS, clock |
| Other TLS | `SSLProtocolException` or `SSLException` | TLS record/protocol/layer error, not necessarily just a cert issue | TLS version, plaintext vs TLS, peer close, logs |
| HTTP connect-timeout | `HttpConnectTimeoutException` | `java.net.http.HttpClient` could not establish a connection within deadline | `connectTimeout`, endpoint, and route |
| HTTP request-timeout | `HttpTimeoutException` | HTTP request deadline expired before response per contract | `HttpRequest.timeout`, server/proxy latency |
| HTTP API/protocol | `ProtocolException` or `IOException` during parsing | Protocol/config violation or implementation rejection | Request method, response syntax, framing, wire trace |
| Incomplete read/body | `EOFException` or `IOException` | Stream ended early relative to the expected number of bytes | `Content-Length`/chunked, peer close, proxy |
| Valid HTTP status | `404`, `429`, `503` ... | Server/proxy returned an HTTP response; **not necessarily a network error** | `statusCode/getResponseCode`, `Retry-After`, body |
| Business/application | JSON decode, validation, authorization | TCP/TLS/HTTP may all be working fine | Schema, method, auth, contract, error response |

**There is no permanent 1:1 mapping** from an exception type to a broken device. `NoRouteToHostException` can appear due to a firewall or route, but a firewall can also **drop** packets causing a connect timeout or **reject** causing refused/ICMP; sometimes Java only receives a generic `SocketException`. This table is for **locating where to check first**, not for declaring a definitive root cause.

## 3. DNS: `UnknownHostException` and Name Resolution Errors

DNS/name resolution context translates `api.example.test` into one or more IPv4/IPv6 addresses. When Java cannot determine an address, APIs such as `InetAddress.getByName(host)` can throw `UnknownHostException`.

```java
// Illustrative snippet, NOT a standalone program.
try {
    InetAddress address = InetAddress.getByName(host);
    useAddress(address);
} catch (UnknownHostException resolutionFailed) {
    reportDnsOrNameResolutionFailure(host, resolutionFailed);
}
```

Here, `host`, `useAddress`, and `reportDnsOrNameResolutionFailure` must be provided by the application. Do not run examples with arbitrary domain names to “test DNS failure” on public networks.

### Do Not Over-Conclude

`UnknownHostException` means the IP for the hostname **could not be determined**, not proof that “the world's DNS servers are down”. Possible causes include:

- Misspelled hostname, missing domain suffix, IDN/punycode, expired domain.
- Hosts file or search domain differs from the expected environment.
- Internal DNS resolver/VPN unreachable, network policy, or split-horizon DNS.
- A/AAAA records unavailable, differing IPv4/IPv6 policies.
- DNS cache has stored a negative result (NXDOMAIN or no address) for a period of time.
- Client uses a proxy; the name is actually resolved at the **proxy** or **client** depending on the proxy type and call method.

### Cross-Check Tools

On an authorized diagnostic host, compare:

```text
input hostname (exact, without scheme)
→ resolver used by JVM/OS
→ A/AAAA records
→ DNS search domain/split DNS
→ actual IP the client attempts to connect to
```

On Windows you can use `Resolve-DnsName`/`nslookup`, and on Linux `getent hosts`, `dig`, or `resolvectl` depending on the distro. However, **the result of a command-line tool does not necessarily match the JVM's cache/proxy/runtime**. When debugging, log the address actually selected for the real request, not just `ping hostname`.

**Security note:** Editing `/etc/hosts`/DNS on production machines by guesswork is not recommended; changing name resolution can route requests to the wrong server, causing data exposure. Check trust boundaries, certificates, and service discovery.

## 4. Bind: `BindException` Is a Local Address Error

A server typically opens a listener:

```java
// Illustrative snippet, not a complete class.
try (ServerSocket server = new ServerSocket()) {
    server.bind(new InetSocketAddress("127.0.0.1", 8080));
    // accept() in the actual implementation.
}
```

`BindException` occurs when the socket **cannot bind to the local address/port**. Possible causes include:

- Port 8080 is already occupied by another process without a valid sharing mechanism.
- Attempting to bind to a local IP that does not exist on the current interface.
- OS policy/permissions/port reservation or kernel state prevents binding.
- Socket binding options, IPv6/IPv4 dual-stack, and `SO_REUSEADDR` interact differently across OSes.

**It is not equivalent to a remote server refusing a connection.** A bind error occurs on the machine **binding the local socket**; if the server fails to start its listener, another client may see `ConnectException` or a timeout when connecting to that port.

### How Does It Differ from `ConnectException`?

- `BindException`: local code cannot **own the local endpoint**.
- `ConnectException`: the client cannot establish a TCP connection to the chosen endpoint; the remote listener does not accept or the network rejects it.

If a server fails to start due to `BindException`, check listening processes, local IP, and port—do not rush to change the client's DNS. If a client explicitly calls `Socket.bind(localAddress)` before `connect`, it can also encounter `BindException` **on the client machine**.

### Local Bind Test

Create `ServerSocket A` bound to `127.0.0.1:0`; the OS assigns an available port. Keep A open, and create `ServerSocket B` bound to **the exact same address/port**. In the default configuration of the test below, B throws `BindException`. This is a safe way to test on loopback without competing for a running service port.

**Do not use demos to compete with ports serving real traffic.** The test only uses a dynamic port created by the program itself, closed inside `try-with-resources`.

## 5. TCP Connect: `ConnectException` and Connection Refusal

After obtaining an IP, the TCP client calls:

```java
// Illustrative snippet, without main or concrete remote values.
try (Socket socket = new Socket()) {
    socket.connect(new InetSocketAddress(remoteAddress, remotePort), 3000);
    // Connection succeeded; send/read data afterward.
}
```

**`ConnectException`** usually describes a connect failure, most notably **connection refused**. Possibilities to check:

1. Right host but **wrong port**, no process listening.
2. Service has not started/crashed, or is running in a container whose port has not been published.
3. Service only binds to `127.0.0.1`, while a client from another machine tries to reach the public IP.
4. Firewall/security policy **rejects** the connection instead of dropping it.
5. Reverse proxy/load balancer is not yet accepting requests on the corresponding port/scheme.
6. Endpoint closed connection backlog or hit a limit in a way that produces a similar-looking error, depending on the OS.

**Connection refused** is often a positive sign that **a reply from the network stack** arrived, though it does not pinpoint whether it came from the intended service, a firewall, or a proxy. `ConnectException` by itself does not prove the server application is running or completely down.

### Connection Refused vs. Connect Timeout

```text
Client ─ TCP SYN ─► destination
            ├─ fast RST/reject response → usually ConnectException
            ├─ route reported unreachable → possibly NoRouteToHostException
            └─ no response within deadline → connect timeout
```

This model is a common explanation, **not an absolute mapping** from a packet to a single Java exception. SYN retries, network policy, proxies, and the OS determine the outcome.

### When Can You Retry?

If no TCP connection was established, the request **over that connection** was generally not sent. However, at the application layer there may be a proxy, automatic retries, multiple endpoints, or previously processed requests. For workflows with side effects, do not take an isolated `ConnectException` out of context to guarantee “definitely no transaction occurred.” Check attempt IDs, connection IDs, body bytes, and server logs.

## 6. Route: `NoRouteToHostException` Is Not DNS

After obtaining an IP address, the OS must determine the **path to the destination**: interface, gateway, VPN, network namespace, firewall, and route policies. When the endpoint cannot be reached, Java may throw `NoRouteToHostException` (a subtype of `SocketException`).

**Important distinctions:**

- DNS can succeed while **routing fails**: the IP is known, but there is no path or an intermediate hop is unreachable.
- A host with a valid route whose **port is not listening** usually manifests as connection refused.
- A firewall **dropping** packets can lead to a timeout instead of `NoRouteToHostException`.
- Misconfigured NAT/proxy/VPN can manifest as various `IOException` forms.

### The Right Investigation Questions

- Is the destination IPv4 or IPv6? Does the machine have the corresponding route?
- Is access going through a VPN or a container/VM network namespace?
- Is a security group/firewall blocking by **source IP**, **destination port**, or protocol?
- Is the server address returned by DNS reachable from **where the JVM runs**, or only from the developer's laptop?
- If going through an HTTP proxy, is the client connecting to the **proxy endpoint** or the origin? The route error may be on the route to the proxy.
- Is there a difference between the default gateway, subnet route, or pod/container network?
- Is a network device returning ICMP unreachable, or silently dropping packets?

**Do not test by scanning entire networks outside your authorization.** You can use `route print`/`Get-NetRoute` on Windows, or `ip route`/`ip -6 route` on Linux, along with authorized network logs. `ping` is not a test for “TCP port 443 reachable” because ICMP is often restricted.

## 7. Read: `SocketTimeoutException`, EOF, and Reset

Suppose TCP connect succeeds, the client sends a request, but has not read enough of the response. This is the **read phase**, no longer the connect phase. On a `Socket`, you typically see:

```java
// Illustrative snippet, not a full runnable program.
socket.setSoTimeout(1500); // Timeout for read operations.
int next = socket.getInputStream().read();
// May return a byte 0..255, -1 on EOF, or throw an exception.
```

If 1.5 seconds pass **while reading without receiving the needed data**, `read()` can throw `SocketTimeoutException`. This does not prove the server is down: the server may be processing, waiting on a database, writing slowly, or waiting for more request body because the client sent an incomplete `Content-Length`.

### Distinguishing Three Cases

| Symptom | Direct meaning | What to examine |
|---|---|---|
| `SocketTimeoutException` from `InputStream.read` | Failed to read data before SO_TIMEOUT | Deadline, server progress, framing, transport |
| `read() == -1` | EOF: peer closed its send side after all bytes were read | Does the protocol expect EOF? Is the body complete? |
| `EOFException` when code requires exact N bytes | Stream ended before the number of bytes the parser needed | Truncated body, peer close, protocol framing |
| `SocketException: Connection reset` or other I/O error | Transport reported a reset/broken connection | Peer/proxy close, half-open, NAT, race |
| `read` returns a positive count smaller than buffer | Partial bytes available | Does **not** mean the message has ended |

**TCP is a byte stream** and does not carry built-in HTTP message boundaries. A single `read` can receive fewer bytes than requested without being an error. On a persistent HTTP/1.1 connection, calling `readAllBytes()` directly on a **raw Socket InputStream** can wait forever for TCP EOF even though the HTTP response is already complete per `Content-Length`.

### Comparing `setSoTimeout` and HTTP Deadlines

`Socket.setSoTimeout(ms)` applies to read operations on that socket. It differs from `Socket.connect(endpoint, timeout)`, where the same `SocketTimeoutException` subtype can report a **connect timeout**. Same exception class, **different callsite means different phase**.

`HttpURLConnection.setReadTimeout(ms)` also sets a timeout for read operations, whereas `HttpRequest.Builder.timeout(Duration)` in `java.net.http.HttpClient` manages the timeout of the **HTTP request**, which can throw `HttpTimeoutException`. Do not record a generic `timeout=true` metric and lose the phase.

### Closing the Connection After a Partial Response

If the server declared `Content-Length: 100` but the client only received 60 bytes and the peer closed, the HTTP message is **incomplete**. Do not turn those 60 bytes into a successful response. With `Transfer-Encoding: chunked`, you must read up to the zero-sized chunk and trailers; EOF before a valid boundary is also an error.

A `204 No Content` response or a response to `HEAD`, on the other hand, **has no HTTP message body** by rule, so after headers there is nothing to wait for. Accurate read failure classification requires knowing **message framing** first.

## 8. TLS: `SSLHandshakeException`, `SSLProtocolException`, `SSLException`

For `https://`/`wss://`, after TCP connect, client and server must still **negotiate TLS**. Common errors include:

- **Untrusted certificate:** missing CA chain, JVM truststore lacks root/intermediate, unauthorized self-signed certificate.
- **Hostname verification failure:** certificate does not match the endpoint's DNS name/SAN.
- **Certificate expired/not-yet-valid:** client clock is wrong or certificate has expired.
- **Protocol/cipher mismatch:** no matching version/cipher suite, server uses an older TLS version no longer permitted.
- **mTLS:** server requires a client certificate that the client does not send or sends incorrectly.
- **SNI/virtual host:** server selects a certificate/context for the wrong hostname.
- **Wrong scheme/port:** client attempts TLS against a port speaking only plaintext HTTP, or plain HTTP against a TLS-only port.
- **Proxy/TLS inspection:** an intermediate hop swaps the certificate/closes the connection causing trust/handshake errors.

### Exception Classification

| Java exception | Interpretation |
|---|---|
| `SSLHandshakeException` | Client/server **failed to negotiate the desired security level**; the TLS connection is unusable |
| `SSLProtocolException` | Error in the operation of the TLS protocol |
| `SSLException` | General TLS error family; may include the subtypes above |
| `SSLPeerUnverifiedException` | Peer identity has not been verified in the corresponding API context |
| `SocketException`/`EOFException` during handshake | Peer/network closed early; **not necessarily wrapped as SSLHandshakeException** |

**Important:** if Java returns `SSLHandshakeException`, TCP **may have already connected** successfully. Changing DNS or increasing connect timeout usually will not fix a certificate error. Conversely, if TCP is reset before the TLS handshake has enough data, the runtime may only throw `SocketException`, even though the developer sees it at `startHandshake()`.

### Do Not “Fix” by Disabling TLS Checks

Do not install a TrustManager that accepts all certificates, do not disable hostname verification, and do not switch HTTPS to HTTP just to make exceptions disappear. Those workarounds hide the root cause and expose credentials/content. Fix the certificate chain/SAN, truststore, clock, TLS configuration, or endpoint scheme properly.

### Which Layer Is Handling TLS?

`javax.net.ssl.SSLSocket` has `startHandshake()` and `SSLContext`, whereas **Java `HttpClient` or `HttpsURLConnection` usually manages TLS internally**. An HTTPS application may see `SSLHandshakeException` via `IOException` wrapped in `ExecutionException`/`CompletionException`; inspect the cause chain. If the connection goes through an HTTP CONNECT proxy, TLS starts **after the tunnel**, so `407 Proxy Authentication Required` happens at the HTTP proxy layer, not as a cert failure.

## 9. Protocol Errors: Do Not Lump HTTP 4xx/5xx into “Network Failure”

Classifying an HTTP response must separate:

1. **No valid response received**: transport/TLS or HTTP parser/framing failure.
2. **Valid HTTP response received, but status indicates error**: `400`, `401`, `403`, `404`, `409`, `429`, `503` ...
3. **HTTP succeeded at transport/status level, but payload violates contract**: JSON body fails schema, invalid application envelope, missing required fields.
4. **Business outcome undetermined**: timeout/cancel occurred after the server may have already processed side effects.

### HTTP `503` Is Not a DNS/Connect/Read Error

For example, the server returned:

```http
HTTP/1.1 503 Service Unavailable
Content-Type: text/plain
Content-Length: 10

BACK_LATER
```

The client received **a valid HTTP response**. `503` indicates the service is temporarily unable to handle the request per HTTP semantics, while the DNS/TCP/TLS/HTTP framing layers may all be working properly. Do not turn status 503 into `ConnectException` or `UnknownHostException` just because the application considers it a failure.

- With `java.net.http.HttpClient.send(...)`, the API normally returns an `HttpResponse` with `statusCode()==503`.
- With `HttpURLConnection`, `getResponseCode()` returns `503`; `getInputStream()` may throw `IOException` for HTTP error statuses, and `getErrorStream()` lets you read the error body if present.
- HTTP `429` may provide `Retry-After`; retry decisions must follow status, header, method, and idempotency.
- HTTP `401`/`407` are authentication challenges at the origin/proxy; do not treat them as TLS handshake failures by default.
- HTTP `408` or `504` are HTTP statuses from the server/proxy, **not synonymous** with Java `SocketTimeoutException` or `HttpTimeoutException`.

### `ProtocolException` Also Needs Context

`java.net.ProtocolException` is an `IOException` used for protocol-related errors. You can encounter it **right at client API validation**, such as `HttpURLConnection.setRequestMethod("INVALID_METHOD")`, even before the network is called. An HTTP response with broken framing such as conflicting `Content-Length` headers may throw `IOException` or another subtype depending on the implementation; **there is no guarantee that every HTTP syntax error appears as `ProtocolException`**.

Therefore, the `PROTOCOL_API` category in the classifier program below is a **starting point**; you must cross-check the callsite and bytes/protocol state to know the specific cause.

## 10. Timeout Comparison Table by API

| Java 17 API | Timeout layer measured | Typical exception | Impact |
|---|---|---|---|
| `Socket.connect(address, timeoutMillis)` | TCP connect establishment | `SocketTimeoutException` | Connect did not complete within deadline |
| `Socket.setSoTimeout(ms)` + `InputStream.read()` | A single **read** operation | `SocketTimeoutException` | Read waited past limit; socket is not required to close by contract |
| `ServerSocket.setSoTimeout(ms)` + `accept()` | Waiting for inbound connection | `SocketTimeoutException` | No incoming accepted socket within the time limit |
| `HttpURLConnection.setConnectTimeout(ms)` | Connect | `SocketTimeoutException` or related `IOException` | Not a whole-request deadline |
| `HttpURLConnection.setReadTimeout(ms)` | Read | `SocketTimeoutException` | Not a total deadline across redirect chains |
| `HttpClient.Builder.connectTimeout(Duration)` | HTTP client connection establishment | `HttpConnectTimeoutException` | Subclass of `HttpTimeoutException` |
| `HttpRequest.Builder.timeout(Duration)` | HTTP request deadline | `HttpTimeoutException` | Does not by itself prove server rollback |
| `Future.get(timeout, unit)` on `sendAsync` | Time the **thread waits on Future** | `java.util.concurrent.TimeoutException` | Does not automatically cancel the HTTP exchange |
| `CompletableFuture.orTimeout(timeout, unit)` | State of the called Future | `TimeoutException` as exceptional cause | Does not by itself prove the network stopped |

**`instanceof` order matters:** `HttpConnectTimeoutException extends HttpTimeoutException`. If a classifier checks `HttpTimeoutException` first, every `HttpClient` connect timeout will be misclassified into the generic `HTTP_REQUEST_TIMEOUT`.

**Do not classify the two `TimeoutException` types by short name alone.** `java.util.concurrent.TimeoutException` from `Future.get` is neither `java.net.SocketTimeoutException` nor `java.net.http.HttpTimeoutException`.

## 11. Java 17+: Exception Classifier Accounting for Wrappers and Inheritance

The first program builds an **illustrative** classifier: it takes a `Throwable` (including errors wrapped in `CompletionException`/`ExecutionException`) and returns a category based on its class. The exceptions passed in here **are constructed synthetically** to test deterministic mapping; the program does **not** claim to have reproduced real DNS/route/TLS failures over the Internet.

**File `FailureClassifierDemo.java`:**

```java
import java.io.EOFException;
import java.io.IOException;
import java.net.*;
import java.net.http.*;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;
import javax.net.ssl.*;

public class FailureClassifierDemo {
    static Throwable unwrap(Throwable error) {
        Throwable current = error;
        for (int i = 0; i < 8; i++) {
            if ((current instanceof CompletionException
                    || current instanceof ExecutionException)
                    && current.getCause() != null) {
                current = current.getCause();
            } else {
                break;
            }
        }
        return current;
    }

    static String phase(Throwable error) {
        Throwable e = unwrap(error);
        if (e instanceof HttpConnectTimeoutException) return "CONNECT_TIMEOUT";
        if (e instanceof HttpTimeoutException) return "HTTP_REQUEST_TIMEOUT";
        if (e instanceof UnknownHostException) return "DNS_OR_NAME";
        if (e instanceof BindException) return "LOCAL_BIND";
        if (e instanceof NoRouteToHostException) return "ROUTE";
        if (e instanceof ConnectException) return "TCP_CONNECT";
        if (e instanceof SocketTimeoutException) return "SOCKET_TIMEOUT_CHECK_CALLSITE";
        if (e instanceof SSLHandshakeException) return "TLS_HANDSHAKE";
        if (e instanceof SSLException) return "TLS_OTHER";
        if (e instanceof ProtocolException) return "PROTOCOL_API";
        if (e instanceof EOFException) return "PREMATURE_EOF";
        if (e instanceof IOException) return "OTHER_IO";
        return "OTHER";
    }

    public static void main(String[] args) {
        IOException[] errors = {
            new UnknownHostException("test"),
            new BindException("test"),
            new ConnectException("test"),
            new NoRouteToHostException("test"),
            new SocketTimeoutException("test"),
            new SSLHandshakeException("test"),
            new SSLException("test"),
            new ProtocolException("test"),
            new EOFException("test"),
            new HttpConnectTimeoutException("test"),
            new HttpTimeoutException("test")
        };
        for (IOException error : errors) {
            System.out.println(error.getClass().getSimpleName()
                    + " -> " + phase(error));
        }
        Throwable wrapped = new CompletionException(
                new ConnectException("test"));
        System.out.println("CompletionException -> " + phase(wrapped));
    }
}
```

Run with JDK 17+:

```bash
javac --release 17 -encoding UTF-8 FailureClassifierDemo.java
java FailureClassifierDemo
```

**Compiled/run verified stdout:**

```text
UnknownHostException -> DNS_OR_NAME
BindException -> LOCAL_BIND
ConnectException -> TCP_CONNECT
NoRouteToHostException -> ROUTE
SocketTimeoutException -> SOCKET_TIMEOUT_CHECK_CALLSITE
SSLHandshakeException -> TLS_HANDSHAKE
SSLException -> TLS_OTHER
ProtocolException -> PROTOCOL_API
EOFException -> PREMATURE_EOF
HttpConnectTimeoutException -> CONNECT_TIMEOUT
HttpTimeoutException -> HTTP_REQUEST_TIMEOUT
CompletionException -> TCP_CONNECT
```

**Accurate analysis of the classifier's limits:**

- `unwrap` only traverses two specific concurrency wrapper types up to 8 levels deep; it does **not** blindly strip every `getCause()` because sometimes the outer exception layer contains important information (e.g., TLS/HTTP layer) that the application wants to keep.
- `HttpConnectTimeoutException` is checked **before** `HttpTimeoutException` so connect-phase classification is not lost.
- `NoRouteToHostException` is separated **before** any generic `SocketException` branch (this code does not add a generic `SocketException` branch).
- `SSLHandshakeException` is checked **before** `SSLException` because it is a subclass.
- `SocketTimeoutException` returns `SOCKET_TIMEOUT_CHECK_CALLSITE`, **not** forced into READ: both `Socket.connect` and `InputStream.read` can use this class.
- `ProtocolException` returns `PROTOCOL_API` but still requires checking the callsite; malformed HTTP can be a different `IOException`.
- An `EOFException` only means **reading ended before the parser's expected condition**. In a close-delimited protocol, EOF can even be a valid termination; do not mark every EOF as an error.
- In production, return a result structure containing **phase, category, root cause, retryability, and operation ID**, rather than just a `String`. Do not infer safe retry from the category alone.

## 12. Java 17+: Three Real Socket Errors on Loopback

The second program does not simulate with `new BindException(...)`. It executes **three local networking scenarios**:

1. Two `ServerSocket` instances trying to bind to the same IP/port → `BindException`.
2. Connecting to a just-released loopback port with no listener → typically `ConnectException`, confirmed in the test environment.
3. Server accepts TCP but deliberately sends no data; client sets `setSoTimeout(120ms)` and calls `read()` → `SocketTimeoutException` from the **read** phase.

**File `SocketFailureLab.java`:**

```java
import java.io.IOException;
import java.net.*;
import java.util.concurrent.*;

public class SocketFailureLab {
    private static final InetAddress LOOPBACK;
    static {
        try { LOOPBACK = InetAddress.getByName("127.0.0.1"); }
        catch (UnknownHostException impossibleForLiteral) {
            throw new ExceptionInInitializerError(impossibleForLiteral);
        }
    }

    private static String bindConflict() throws Exception {
        try (ServerSocket first = new ServerSocket();
             ServerSocket second = new ServerSocket()) {
            first.bind(new InetSocketAddress(LOOPBACK, 0));
            try {
                second.bind(new InetSocketAddress(
                        LOOPBACK, first.getLocalPort()));
                return "UNEXPECTED_SUCCESS";
            } catch (BindException expected) {
                return expected.getClass().getSimpleName();
            }
        }
    }

    private static String refusedConnect() throws Exception {
        int unusedPort;
        try (ServerSocket reservation = new ServerSocket()) {
            reservation.bind(new InetSocketAddress(LOOPBACK, 0));
            unusedPort = reservation.getLocalPort();
        }
        try (Socket client = new Socket()) {
            try {
                client.connect(new InetSocketAddress(LOOPBACK, unusedPort), 1000);
                return "UNEXPECTED_SUCCESS";
            } catch (ConnectException expected) {
                return expected.getClass().getSimpleName();
            }
        }
    }

    private static String readTimeout() throws Exception {
        CountDownLatch accepted = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        ExecutorService worker = Executors.newSingleThreadExecutor();
        try (ServerSocket listener = new ServerSocket()) {
            listener.bind(new InetSocketAddress(LOOPBACK, 0));
            listener.setSoTimeout(4000);
            Future<?> server = worker.submit(() -> {
                try (Socket peer = listener.accept()) {
                    accepted.countDown();
                    if (!release.await(4, TimeUnit.SECONDS))
                        throw new IllegalStateException("Wait expired");
                } catch (Exception failure) {
                    throw new RuntimeException(failure);
                }
            });
            try (Socket client = new Socket()) {
                client.connect(new InetSocketAddress(
                        LOOPBACK, listener.getLocalPort()), 2000);
                client.setSoTimeout(120);
                if (!accepted.await(2, TimeUnit.SECONDS))
                    throw new IllegalStateException("Server did not accept");
                try {
                    client.getInputStream().read();
                    return "UNEXPECTED_SUCCESS";
                } catch (SocketTimeoutException expected) {
                    return expected.getClass().getSimpleName();
                }
            } finally {
                release.countDown();
                server.get(3, TimeUnit.SECONDS);
            }
        } finally {
            release.countDown();
            worker.shutdownNow();
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println("Bind collision: " + bindConflict());
        System.out.println("Connect to closed port: " + refusedConnect());
        System.out.println("Silent peer read: " + readTimeout());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 SocketFailureLab.java
java SocketFailureLab
```

**Stdout observed on the test environment's loopback:**

```text
Bind collision: BindException
Connect to closed port: ConnectException
Silent peer read: SocketTimeoutException
```

**Scoped explanation:**

- `Bind collision` occurs **on the local machine** before any remote TCP client needs to send a request.
- `Connect to closed port`: the program temporarily holds a port to learn its port number, then closes the listener and attempts to connect. Typically the OS returns refused, though there is a **tiny race** if another process immediately claims the just-released port or if OS/network policy differs. Do not use this result as “proof that every failed connect is refused.”
- `Silent peer read`: the server **accepted successfully** and used a latch to wait without sending a response. Thus the timeout occurs on **read**, not connect; `accepted.await` confirms the phase before testing read.
- `setSoTimeout(120)` does not mean the TCP socket must be closed after the exception. The application must still decide lifecycle/cleanup.
- The test closes resources in `try-with-resources`, releases latches in `finally`, and shuts down the executor. Timeouts and test ports are for loopback only, with no Internet dependency.
- In a real system, if you see `SocketTimeoutException`, inspect the **stack trace/callsite** before classifying it as a connect timeout or read timeout.

## 13. Java 17+: HTTP 503 Is a Valid Response, Not a TCP Error

The third program spins up a loopback HTTP server returning status `503 Service Unavailable` and body `BACK_LATER`. Then:

- Uses `HttpURLConnection` to read `getResponseCode()==503` and the body from `getErrorStream()`.
- Uses `java.net.http.HttpClient` and `BodyHandlers.ofString()`, receiving an `HttpResponse<String>` with status 503.
- Intentionally configures an invalid request method on `HttpURLConnection` to **receive `ProtocolException` at the client API**, rather than from the network.

**File `HttpStatusVsProtocolDemo.java`:**

```java
import com.sun.net.httpserver.HttpServer;
import java.io.*;
import java.net.*;
import java.net.http.*;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public class HttpStatusVsProtocolDemo {
    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress(InetAddress.getByName("127.0.0.1"), 0),
                0);
        server.createContext("/unavailable", exchange -> {
            try (exchange) {
                byte[] bytes = "BACK_LATER".getBytes(StandardCharsets.UTF_8);
                exchange.sendResponseHeaders(503, bytes.length);
                try (OutputStream out = exchange.getResponseBody()) {
                    out.write(bytes);
                }
            }
        });
        try {
            server.start();
            URI uri = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/unavailable");
            HttpURLConnection legacy = (HttpURLConnection)
                    uri.toURL().openConnection();
            legacy.setConnectTimeout(3000);
            legacy.setReadTimeout(3000);
            try {
                System.out.println("URLConnection status: "
                        + legacy.getResponseCode());
                try (InputStream error = legacy.getErrorStream()) {
                    if (error == null)
                        throw new IllegalStateException("Missing error stream");
                    System.out.println("URLConnection error body: "
                            + new String(error.readAllBytes(),
                                    StandardCharsets.UTF_8));
                }
            } finally {
                legacy.disconnect();
            }

            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();
            HttpRequest request = HttpRequest.newBuilder(uri)
                    .timeout(Duration.ofSeconds(3)).GET().build();
            HttpResponse<String> response = client.send(
                    request, HttpResponse.BodyHandlers.ofString());
            System.out.println("HttpClient status: " + response.statusCode());

            HttpURLConnection wrongMethod = (HttpURLConnection)
                    uri.toURL().openConnection();
            try {
                wrongMethod.setRequestMethod("INVALID_METHOD");
                System.out.println("Method validation: UNEXPECTED_SUCCESS");
            } catch (ProtocolException expected) {
                System.out.println("Method validation: "
                        + expected.getClass().getSimpleName());
            } finally {
                wrongMethod.disconnect();
            }
        } finally {
            server.stop(0);
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 HttpStatusVsProtocolDemo.java
java HttpStatusVsProtocolDemo
```

**Verified stdout:**

```text
URLConnection status: 503
URLConnection error body: BACK_LATER
HttpClient status: 503
Method validation: ProtocolException
```

**What the experiment proves:**

1. The server received the request and returned HTTP 503 with a body. This is an **application/proxy response**, not a DNS resolution error, TCP refused, or TLS handshake failure.
2. `HttpURLConnection.getResponseCode()` lets you inspect the status even when `getInputStream()` may throw `IOException` on HTTP errors. In the demo, `getErrorStream()` returns `BACK_LATER`.
3. `HttpClient.send(...)` does not throw a network exception just because the response status is non-2xx; the caller reads `statusCode()==503` and decides how to handle it.
4. `ProtocolException` is thrown **when calling `setRequestMethod` on an unconnected object** because the method is not accepted by the API. It does **not** prove the server sent malformed HTTP; do not misinterpret the result.
5. With `HttpURLConnection`, `getErrorStream()` can return `null` if there is no body/error stream; production code must check for null, bound body bytes, and close the stream.
6. HTTP 503 may include `Retry-After` per semantics; do **not** automatically retry a POST with side effects if the API does not guarantee idempotency.

## 14. Java 17+: TLS Client Meets Plaintext Server

The fourth program simulates **a protocol mismatch on the same endpoint**, a common error when a client uses `https://` or `wss://` against a port where the server only sends plaintext HTTP.

- A loopback `ServerSocket` accepts the TCP connection and writes `HTTP/1.1 200 OK` in **plaintext**.
- A Java `SSLSocket` still expects **TLS records**, so `startHandshake()` cannot complete validly.
- The server holds the socket open with a latch while the client handles the error; this keeps the test focused on **TLS protocol mismatch**, avoiding a case where the peer closes too early and causes Windows to report `SocketException` before JSSE recognizes plaintext HTTP.

**File `TlsVsPlainTcpDemo.java`:**

```java
import java.io.IOException;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.*;
import javax.net.ssl.*;

public class TlsVsPlainTcpDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService worker = Executors.newSingleThreadExecutor();
        CountDownLatch release = new CountDownLatch(1);
        try (ServerSocket listener = new ServerSocket()) {
            listener.bind(new InetSocketAddress("127.0.0.1", 0));
            listener.setSoTimeout(4000);
            Future<?> plainServer = worker.submit(() -> {
                try (Socket peer = listener.accept()) {
                    peer.setSoTimeout(4000);
                    peer.getOutputStream().write(
                            "HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n"
                                    .getBytes(StandardCharsets.US_ASCII));
                    peer.getOutputStream().flush();
                    release.await(4, TimeUnit.SECONDS);
                } catch (Exception error) {
                    throw new RuntimeException(error);
                }
            });
            SSLSocketFactory factory =
                    (SSLSocketFactory) SSLSocketFactory.getDefault();
            try (SSLSocket tls = (SSLSocket) factory.createSocket(
                    "127.0.0.1", listener.getLocalPort())) {
                tls.setSoTimeout(3000);
                try {
                    tls.startHandshake();
                    System.out.println("TLS handshake succeeded: true");
                } catch (IOException expected) {
                    System.out.println("TLS handshake succeeded: false");
                    System.out.println("Exception family: "
                            + (expected instanceof SSLException
                                ? "SSLException" : "other IOException"));
                    System.out.println("Exception subtype: "
                            + expected.getClass().getSimpleName());
                }
            } finally {
                release.countDown();
            }
            plainServer.get(3, TimeUnit.SECONDS);
        } finally {
            release.countDown();
            worker.shutdownNow();
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 TlsVsPlainTcpDemo.java
java TlsVsPlainTcpDemo
```

**Stdout verified in the test environment:**

```text
TLS handshake succeeded: false
Exception family: SSLException
Exception subtype: SSLException
```

**Warning about potential runtime differences:** If the peer closes very early, the network resets, or the OS/JDK detects the error in a different order, the `IOException` may be `SocketException` instead of `SSLException`, or the subtype may be `SSLHandshakeException`/`SSLProtocolException`. What is certain in the demo is that **the client cannot successfully negotiate TLS with a peer that only sends plaintext HTTP**. Do not hard-code one exact subtype as the expected result across all environments.

This program does **not** test certificate chain/hostname mismatch, because the plain server has no certificate at all. To diagnose real certificate errors, use an authorized internal TLS endpoint, inspect SAN/chain/truststore/time/SNI and controlled TLS debug logs; **do not disable trust validation** as a “fix”.

## 15. Reading Stack Traces and Cause Chains by Phase

Consider asynchronous code:

```java
// Illustrative snippet; request/client already configured.
CompletableFuture<HttpResponse<String>> future = client.sendAsync(
        request, HttpResponse.BodyHandlers.ofString());

try {
    HttpResponse<String> response = future.get();
} catch (ExecutionException wrapper) {
    Throwable real = wrapper.getCause();
    // Use exception type, cause chain, and request context to classify.
}
```

`get()` typically wraps exceptional completion in `ExecutionException`; `join()` typically surfaces via `CompletionException`. Do not just log `ExecutionException: ...` and discard `getCause()`. At the same time, do not **unwrap all causes to the very bottom** and lose TLS/HTTP layer information: the outer layer may identify the phase, while the inner layer records the socket error.

### Context-Based Triage Template

```text
1. Operation?   DNS lookup / ServerSocket.bind / Socket.connect /
                 InputStream.read / SSLSocket.startHandshake /
                 HttpClient.send / HTTP parse?
2. Exception?   Exact class + parent cause + suppressed
3. Endpoint?    Origin/proxy hostname, resolved IP, local bind IP,
                 port, scheme http/https, IPv4/IPv6
4. Timeline?    Start/end/connect/read elapsed, timeout values
5. Evidence?    Server access log, TLS logs, authorized packet trace
6. Outcome?     Is there an HTTP response status? Is there a business request ID?
7. Recovery?    Fix config, fail fast, bounded retry, or reconcile
```

For example:

| Observed log | Evidence-based conclusion |
|---|---|
| `Socket.connect(...,2000)` throws `SocketTimeoutException` | **Connect timeout** at that endpoint; does not yet prove firewall as the cause |
| `input.read()` throws `SocketTimeoutException` after successful TCP connect | **Read timeout**, not a DNS error |
| `InetAddress.getByName()` throws `UnknownHostException` | **Name resolution** failed per the active resolver |
| `ServerSocket.bind()` throws `BindException` | **Local bind** failed; check local IP/port |
| `SSLSocket.startHandshake()` throws `SSLHandshakeException` | **TLS handshake** did not complete; inspect cert/negotiation |
| `getResponseCode() == 503` | **Valid HTTP response** 503 received, not a network transport error |
| `HttpURLConnection.setRequestMethod(...)` throws `ProtocolException` | API/protocol method error **before I/O** at this callsite |
| `HttpClient.sendAsync().join()` throws `CompletionException` | Must inspect **cause** to know the phase |
| `readNBytes(100)` only got 40 then EOF | **Incomplete body** if the protocol requires 100 bytes |

### Do Not Assign “Root Cause” with a Single Code

You might have a chain:

```text
CompletionException
    └── SSLHandshakeException
          └── CertificateException / PKIX path building failed
```

In that context, the category should be `TLS_HANDSHAKE`, while the detailed cause description is **certificate trust chain** after inspecting the cause. Someone who only logs `IOException` misses the useful diagnosis.

Conversely:

```text
IOException: unexpected EOF while reading HTTP body
    └── SocketException: Connection reset
```

You may need to record both **phase READ/HTTP_FRAMING** and **transport reset**, rather than forcing one keyword and discarding the entire timeline.

## 16. Retryability: Which Errors Can Be Retried?

**Do not apply a blanket rule “if IOException, then retry”**. Reliability is not just about recovering connections, but also **not duplicating business operations**.

| Error / scenario | Retry recommendation | Important conditions |
|---|---|---|
| Temporary DNS resolution failure | May retry boundedly after checking resolver | Do not retry every few ms, do not change host arbitrarily |
| BindException for fixed server port | **Do not retry immediately with same config** | Fix local port, process conflict, bind permissions |
| ConnectException refused | Bounded retry if service is expected to come up soon | Check deployment/health, backoff/jitter |
| NoRouteToHostException | Usually requires fixing route/VPN/firewall | Retrying will not help if a policy permanently blocks it |
| Connect timeout | May retry with backoff per contract | Do not confuse with a server-side commit on another attempt |
| Read timeout after POST body | **Business outcome unknown** | Idempotency key, status query, avoid duplicate writes |
| Invalid TLS cert/hostname | **Fail fast, fix security** | Do not disable TLS validation or switch HTTPS→HTTP |
| Temporary TLS incompatibility due to version/cipher | Fix config/endpoint, do not retry blindly | Diagnose version/cipher/ALPN/SNI |
| HTTP 401/403 | Usually requires auth/permission, do not retry blindly | Refresh credentials boundedly, right scope |
| HTTP 404 | Check resource/path, do not assume transient | May be eventual consistency per contract |
| HTTP 429 | Bounded retry per `Retry-After` and quota | Preserve method/idempotency and total deadline |
| HTTP 503 | May retry per policy and `Retry-After` | Avoid retry storms; know endpoint/server outcome |
| Malformed HTTP framing | Do not keep reusing an ambiguous connection | Parser/library version, proxy/backend contract |
| EOF before complete body | Request/response incomplete | Server side effect may have already occurred |
| Invalid JSON schema | Fix contract/serialization | Will not be solved by infinite network retries |

### “Connected” Does Not Mean “Executed”

A successful TCP connect only means the transport channel was created. It does not tell you whether the server received the full body or committed. Conversely, a **read timeout or connection reset after sending the body** also does not prove the server did not commit; the response may have been lost after the database write.

When calling a POST to create an order, use **a stable idempotency key for the same logical operation** if the API publishes that contract. The server must perform deduplication properly, with persisted state and a retention limit; **HTTP/TCP does not inherently provide exactly-once semantics** for business logic.

### Conditional Retry Formula

```text
if config/permanent error (bind conflict, invalid cert, bad method):
    fail fast + repair config
else if transient error and request is safe/has idempotency:
    bounded retry + backoff + jitter + total deadline
else if server may have committed:
    mark UNKNOWN + query business status
else:
    surface error with context, do not guess
```

This is a decision diagram, not runnable Java code. Do not generate a new idempotency key when retrying the same intent; doing so can cause the server to treat it as a different transaction.

## 17. Timeout Policies, Connection Pools, and Circuit Breakers

A reliable system should separate:

- **Connect timeout** — do not wait indefinitely for a TCP connection.
- **Read timeout** — do not wait indefinitely on a single read.
- **Whole-request deadline** — do not let a request drag on forever across redirects/retries/body.
- **Business deadline** — the duration the application accepts to complete the operation.
- **Concurrency limit** — do not open unlimited connections/threads/futures.
- **Retry budget** — maximum attempts, total elapsed time, and traffic amplification.
- **Circuit breaker** — temporarily stop calling a persistently failing dependency, with half-open probing.

If you only increase timeouts without finding the root cause, symptoms can worsen: requests hold resources longer, queues grow, threads exhaust, and retry storms occur. A read timeout that is too short also creates false positives for slow but valid responses. Choose thresholds based on **SLOs and actual latency measurements**, not one fixed number for every endpoint.

### Java 17 HttpClient

```java
// Illustrative snippet, requires imports java.net.http.*, java.net.URI,
// java.time.Duration; no real test endpoint here.
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .build();

HttpRequest req = HttpRequest.newBuilder(
        URI.create("https://api.example.test/items"))
        .timeout(Duration.ofSeconds(8))
        .GET()
        .build();

HttpResponse<String> response =
        client.send(req, HttpResponse.BodyHandlers.ofString());
```

`connectTimeout` and `request.timeout` measure different scopes. `HttpConnectTimeoutException` is a subclass of `HttpTimeoutException` and should be classified first. If using `sendAsync`, remember to distinguish `Future.get(timeout)` (which only limits the **caller wait**) from the HTTP request timeout; the wait expiring **does not automatically cancel the HTTP exchange**.

### Circuit Breakers Do Not Fix Certificate Errors

If every request fails because a TLS certificate expired, a circuit breaker can reduce load, but **it will not fix the certificate**. You need observability and proactive alerting on cert expiry, DNS health, port binding, route changes, and dependency SLOs.

## 18. Practical Layer-by-Layer Investigation Toolkit

Only run commands on systems you manage or are authorized to inspect; the examples below are a guide for choosing tools, **not test results for any specific service**.

| Want to know | Windows/PowerShell | Linux |
|---|---|---|
| Name resolution | `Resolve-DnsName api.example.test`, `nslookup` | `getent hosts api.example.test`, `dig` |
| Locally listening ports | `Get-NetTCPConnection -State Listen` | `ss -ltn` |
| Check TCP reachability | `Test-NetConnection host -Port 443` | `nc -vz host 443` if available and permitted |
| Route table | `route print`, `Get-NetRoute` | `ip route`, `ip -6 route` |
| HTTPS headers/status | `curl -v --http1.1 https://...` | `curl -v --http1.1 https://...` |
| TLS certificate/negotiation | Approved TLS tool, e.g. OpenSSL if installed | `openssl s_client -connect host:443 -servername host` |
| Packet diagnostics | Authorized Wireshark/capture | Authorized `tcpdump`/Wireshark |

**Do not equate:**

- `nslookup` returning an IP does not prove TCP port 443 is open.
- `ping` failing does not prove TCP cannot connect.
- `Test-NetConnection` succeeding does not prove the HTTPS certificate is valid or the API returns 200.
- `curl -k`/`--insecure` can mask cert validation errors; **do not use it as a production fix**.
- A listening port does not prove the backend returns a valid HTTP response.
- A TCP packet capture on HTTPS does not reveal the payload because TLS encrypts it.

### Minimal Diagnostic Record

```text
timestamp
logicalRequestId / attemptId
scheme + host + port + path template (redact secrets)
localEndpoint / remoteEndpoint / selected address family
proxyRoute / DNS answer age if available
operationPhase = DNS | BIND | CONNECT | ROUTE | TLS | WRITE | READ | PROTOCOL
timeoutConfig = connect/read/request/overall
elapsedMs by phase
exceptionClass + causeChain (sanitized)
httpStatus + Retry-After if available
bytesSent/bytesReceived (estimated, do not infer peer received all)
serverTraceId / businessOutcome if verified
```

Do not log passwords, Authorization headers, session cookies, private keys, tokens, or full sensitive bodies. If DNS/route contains internal network details, log with appropriate access controls.

## 19. Scenario Exercises and Answers

**Q1.** `InetAddress.getByName("backend.internal")` throws `UnknownHostException`. Is the backend definitely down?  
**Answer:** No. We only know name resolution did not yield an IP in the resolver context. Check hostname, DNS/hosts, search domain, VPN, proxy, A/AAAA.

**Q2.** Server binding port 8080 throws `BindException`. Should you increase the client read timeout?  
**Answer:** No. This is a local bind failure; check conflicting processes/listeners on the port, local IP, and bind permissions.

**Q3.** Client connecting to `127.0.0.1:9999` gets `ConnectException: Connection refused`. Does that mean DNS failed?  
**Answer:** No. A literal IP needs no name lookup; the TCP endpoint did not accept the connection in this attempt.

**Q4.** DNS resolved to `10.0.0.5`, yet `Socket.connect` throws `NoRouteToHostException`. Is that a contradiction?  
**Answer:** No. DNS provides the IP, while routing/reachability is a subsequent phase.

**Q5.** If a firewall drops TCP SYN packets, will you always receive `NoRouteToHostException`?  
**Answer:** No. It may result in a connect timeout; the mapping depends on policy/OS and ICMP/RST responses.

**Q6.** `SocketTimeoutException` occurs during `InputStream.read`. Is this a connect timeout?  
**Answer:** No. The callsite is a read operation after connecting; classify as `READ_TIMEOUT`.

**Q7.** `SocketTimeoutException` occurs during `Socket.connect(addr, timeout)`. Is this a read timeout?  
**Answer:** No. The callsite is connect; classify as `CONNECT_TIMEOUT`.

**Q8.** Is `read() == -1` always a network error?  
**Answer:** No. That is EOF, which can be valid if the protocol expects a close-delimited body, or an incomplete message if bytes are still missing.

**Q9.** Server returns HTTP 503 + body `BACK_LATER`. Did Java `HttpClient` encounter a network exception?  
**Answer:** Not simply because of status 503; this is a valid HTTP response. The caller must read `statusCode()` and decide how to handle it.

**Q10.** `HttpURLConnection.getInputStream()` throws `IOException` for status 404. Can there still be an error body?  
**Answer:** Yes. `getErrorStream()` can return a stream containing the response body, though it may be null and must be closed.

**Q11.** HTTPS certificate hostname does not match; should you change the URL to HTTP?  
**Answer:** No. Fix the certificate/SAN/hostname/trust and TLS configuration; do not downgrade security.

**Q12.** Does `SSLHandshakeException` mean TCP connect did not succeed?  
**Answer:** No. The TLS handshake typically occurs **after** the TCP connection; TCP may already be completely connected.

**Q13.** A TLS client connects to a server speaking only plaintext HTTP. Might you see `SSLException`?  
**Answer:** Yes, though some runtimes/timings may yield `SocketException` if the peer closes/resets first; inspect phase and bytes.

**Q14.** Is `ProtocolException` at `setRequestMethod("INVALID_METHOD")` an error caused by the server sending malformed HTTP?  
**Answer:** No. This is client-side API validation before the network request.

**Q15.** Is `HttpConnectTimeoutException` caught by `catch (HttpTimeoutException e)`?  
**Answer:** Yes, because it is a subclass; however, a classifier that wants to separate connect timeouts must check the subtype **first**.

**Q16.** `Future.get(200, MILLISECONDS)` times out. Does that mean `HttpClient.sendAsync` was cancelled?  
**Answer:** No. Only the calling thread's wait timed out; the future/exchange may still be running.

**Q17.** After sending a POST body, the client hits a read timeout. Can you immediately retry with a new idempotency key?  
**Answer:** Not safe by default. The server may have already committed; check status or retry with the same logical key per the API contract.

**Q18.** Does a `ConnectException` in an application going through a proxy guarantee the socket failed connecting to the origin?  
**Answer:** No. The client may be connecting to the proxy, and where it failed must be verified from the proxy config and actual endpoint.

**Q19.** `ping` works fine, yet HTTPS still fails handshake. Is that abnormal?  
**Answer:** No. ICMP reachability does not validate TLS certificates, ciphers, SNI, or HTTP routes.

**Q20.** When should a protocol error prevent connection reuse?  
**Answer:** When HTTP framing is ambiguous/corrupted, the body is incomplete, or the decoder state is out of sync; discard the connection per the HTTP library/implementation contract.

## 20. End-of-Lesson Checklist and References

### Incident Classification Checklist

- [ ] Identify the **specific phase** via callsite: resolve, bind, connect, route, TLS, write, read, HTTP parse.
- [ ] Distinguish local bind IP/port from remote connect IP/port.
- [ ] Do not treat `UnknownHostException` as proof that the service is down; check resolver/hosts/proxy.
- [ ] Do not treat `ConnectException` as a DNS error; check listener/port and reject policy.
- [ ] Do not treat `NoRouteToHostException` as a DNS error; check route/gateway/VPN/firewall.
- [ ] Do not label every `SocketTimeoutException` as READ; check whether it is `connect` or `read`.
- [ ] Distinguish an incomplete-protocol `EOFException` from a valid terminating EOF.
- [ ] Distinguish `SSLHandshakeException`/`SSLException` from TCP refusal and certificate issues; do not downgrade TLS validation.
- [ ] With `HttpClient`, check `HttpConnectTimeoutException` before `HttpTimeoutException`.
- [ ] Do not turn valid HTTP 4xx/5xx responses into `IOException` in classification logic once a status is present.
- [ ] Inspect `CompletionException/ExecutionException.getCause()` while preserving the full cause chain.
- [ ] Log network/proxy/route and phase elapsed times with appropriate controls, without logging secrets.
- [ ] Use bounded retries and backoff only for appropriate transient failures; **do not blindly retry POSTs with side effects**.
- [ ] Verify the business outcome if the request could have reached the server before timeout/cancel.
- [ ] Close `ServerSocket/Socket/InputStream` with try-with-resources; shut down executors in `finally`.
- [ ] With broken HTTP/1.1 framing, do not reuse an out-of-sync connection.
- [ ] Use deterministic local tests to learn exceptions; do not disrupt DNS/firewalls/certificates on real systems.

**Key takeaway:** DNS, bind, connect, route, read, TLS, and protocol errors belong to **different stages of a network exchange**. An exception class helps point you in the right direction, but only **phase + callsite + root cause + corroborating evidence** is enough to choose the right fix and safe retry strategy.

### Official References (Java 17)

- [`UnknownHostException` — IP address could not be determined](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/UnknownHostException.html)
- [`BindException` — could not bind address/port](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/BindException.html)
- [`ConnectException` — TCP connect error](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ConnectException.html)
- [`NoRouteToHostException` — endpoint/route unreachable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/NoRouteToHostException.html)
- [`SocketTimeoutException` — socket timeout](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/SocketTimeoutException.html)
- [`Socket` — `connect`/`setSoTimeout`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html)
- [`SSLHandshakeException` and `SSLException` — TLS errors](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLHandshakeException.html)
- [`ProtocolException` — protocol error](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ProtocolException.html)
- [`HttpTimeoutException` and `HttpConnectTimeoutException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpConnectTimeoutException.html)
- [`HttpURLConnection` — response/status/error stream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/HttpURLConnection.html)
- [`HttpClient` — HTTP/1.1, HTTP/2, and connection timeouts](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html)
- [RFC 9110 — HTTP Semantics, status, and retry](https://www.rfc-editor.org/rfc/rfc9110.html)
- [RFC 9112 — HTTP/1.1 message framing](https://www.rfc-editor.org/rfc/rfc9112.html)
