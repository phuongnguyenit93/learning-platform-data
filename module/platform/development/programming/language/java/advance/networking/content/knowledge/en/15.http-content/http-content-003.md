# Replayable Bodies and Conditions for Resending After Authentication or Redirects

## Lesson Objectives

In HTTP, **sending a request for the first time** and **replaying a request body** are two different tasks. A `POST` request may have already transmitted part or all of its content when the server/proxy returns `401 Unauthorized`, `407 Proxy Authentication Required`, or `307 Temporary Redirect`. If the client needs to send the request again, the body source must produce **the exact same byte sequence from the beginning**. An `InputStream` that has been read to the end does not rewind itself; a real-time event stream does not replay the exact same bytes on its own either.

In Java 17, `java.net.http.HttpRequest.BodyPublisher` is the mechanism that supplies the body for `HttpClient`. The client uses the `Flow.Publisher<ByteBuffer>` model: each time an HTTP request needs to be sent, there is a subscription. **If the request must be replayed, there will be a new subscription and the publisher is expected to provide the same data.** With `BodyPublishers.ofInputStream(Supplier<InputStream>)`, the supplier is used to provide a **new stream** each time it is needed, because Java does not buffer the entire stream source automatically. If the supplier has no data left or returns `null` on a subsequent call, replaying may fail.

After this lesson, you will be able to:

1. Distinguish a **replayable body** from an **idempotent business operation** and from TCP's automatic byte retransmission.
2. Understand the semantics of `BodyPublisher.subscribe(...)`, `contentLength()`, and the factories `ofString`, `ofByteArray`, `ofFile`, `ofInputStream`, `ofByteArrays`, `fromPublisher`.
3. Know when a `401`/`407` authentication challenge or a `301`/`302`/`303`/`307`/`308` redirect leads to a new request **with or without the original body**.
4. Create a supplier that returns **a new InputStream on every invocation**, without reusing a consumed stream or mutable data that has been modified.
5. Decide whether to allow automatic redirect/authentication retries or whether to stop, ask the user, reconcile the business outcome, or use an idempotency key.
6. Run three standalone Java 17+ examples on **loopback**: `307` and `303` redirects; `401` authentication; and intentional failure when the body can only be read once.

## 1. Exact Definition of “Replay”

Consider a client sending:

```http
POST /orders HTTP/1.1
Host: api.example.test
Content-Type: application/json
Content-Length: 21

{"sku":"A1","qty":2}
```

This is a human-readable format; on the HTTP/1.1 wire, each header line ends with CRLF. Body bytes are transmitted according to HTTP framing, not according to `OutputStream.write` call boundaries.

Suppose the request encounters one of two situations:

- The server sends `307 Location: /new-orders`, instructing the client to continue with **the same method and body** at a different URI.
- The server sends `401 WWW-Authenticate`, and the client is authorized to obtain credentials and resend the request with the appropriate `Authorization`.

To continue, the client must ensure the second request has a body that is **identical as required by the protocol and the application** to the first one. That is **replayability**. The need to resend can occur even if the body was already read to EOF on the first attempt, so the body's data source must support **initializing a new read**.

### Three Easily Confused Properties

| Property | Question to Answer | Example |
|---|---|---|
| **Replayable body** | Can it reproduce the same byte sequence when the HTTP client needs to send again? | An immutable `byte[]` or a supplier opening a fresh stream from fixed data |
| **Idempotent operation** | Does executing the same intent multiple times cause a different business effect than executing it once? | “Set status=PAID” can be idempotent if designed properly, whereas “increment balance by 10” is not |
| **Safe HTTP method** | Are the method's semantics read-only, requesting no client-driven state change? | `GET` and `HEAD` by semantics; server-side logging/metrics may still occur |

**Replayable does not mean safe to retry.** A body can be replayed 100 times, yet the server might create 100 orders if there is no idempotency mechanism. Conversely, a business operation that is inherently idempotent may still fail to replay its body if the client emits a one-time live stream.

### TCP Retransmission Is Also Different from Application Replay

TCP has a mechanism to retransmit lost segments within a single connection. It does not require the application to reopen an `InputStream` to “resend a new HTTP request.” By contrast, when `HttpClient` actually sends **another HTTP request** after a challenge/redirect, it may need to invoke the body publisher again. Keep these two layers separate when debugging.

## 2. Why Might Java `HttpClient` Need to Re-subscribe to the Body?

Java 17 defines `HttpRequest.BodyPublisher` as a `Flow.Publisher<ByteBuffer>`. `HttpClient` subscribes to the publisher to receive a stream of `ByteBuffer`s containing the body bytes for **one send attempt**. When it needs to resubmit the request, the client creates a **new subscription** and expects the publisher to produce the same bytes; this is the most important contract of `BodyPublisher`.

```text
HttpRequest (POST, bodyPublisher)
          │
          ├── Attempt 1
          │      BodyPublisher.subscribe(subscriber#1)
          │           -> ByteBuffer A1, A2, ... -> onComplete
          │
          ├── HTTP response: 307/308 or 401/407
          │
          └── Does policy allow continuing?
                 │
                 ├── No -> return response/error to caller
                 │
                 └── Yes, must preserve method + body
                       BodyPublisher.subscribe(subscriber#2)
                            -> A1, A2, ... SAME AS ATTEMPT 1
```

**Not every HTTP response leads to re-subscribing**: `303` typically converts POST to GET, so the POST body does not need to be resent; the `Redirect.NEVER` policy does not follow redirects; authentication may fail or not be configured; or the client may stop due to retry/redirect limits.

Furthermore, on the first attempt the server may return a response **before reading the entire body**. The initial subscription may have finished sending, sent only part of it, or been cancelled. The publisher must still be prepared for the request to be replayed if the contract requires it.

### 2.1. `contentLength()` Does Not Make a Body Replayable

`BodyPublisher.contentLength()`:

- Returns `>0` if the body length is known and positive.
- Returns `0` when there are no body bytes; implementations may skip subscribing to an empty body publisher.
- Returns a negative number (usually `-1`) when the length is not known in advance.
- According to the Javadoc, `contentLength()` may be called multiple times and **must return the same invariant value**.

A publisher that knows its length is 5 bytes can still be **one-shot**: it emits 5 bytes on the first subscription but has no source left for a subsequent subscription. Conversely, a publisher with `contentLength()==-1` can still be fully replayable if every subscription can produce the same bytes from the beginning.

With HTTP/1.1, an unknown body length can be encoded by the client using `Transfer-Encoding: chunked` per the protocol; with HTTP/2, framing works differently. **Do not manually set `Content-Length`** to “force” the client to replay; let `BodyPublisher` declare the accurate size or let the HTTP client choose the framing.

### 2.2. Ownership of `ByteBuffer`

The `BodyPublisher` Javadoc requires the publisher to allocate the emitted `ByteBuffer`s and **not access** a buffer again after passing it to the HTTP client. Custom publishers must not reuse the same mutable `ByteBuffer` across two concurrent subscriptions or modify `position/limit` after `onNext`. Violating this can corrupt the body, cause races, or fail during redirects/authentication.

To support retries from large sources, the publisher should own the mechanism for creating a **new data stream**, with proper cleanup and backpressure; there is no need to hold the entire body on the heap if it can be replayed from a stable file/snapshot.

## 3. `BodyPublishers` in Java 17: Which One to Choose?

| Factory | Data Source | Replayability and Conditions | Risks |
|---|---|---|---|
| `noBody()` | No body | No bytes need to be recreated | Does not represent a lost POST body |
| `ofString(String)` | Encoded string content, UTF-8 by default | Suitable for small, stable bodies | Do not confuse `String.length()` with byte count |
| `ofByteArray(byte[])` | Byte array | Can recreate bytes if the data is not mutated while sending | Externally mutable array; bugs if contents are modified |
| `ofByteArray(buf,offset,length)` | A slice of a byte array | Similar, but restricted to the specified range | Data in that range changes between attempts |
| `ofFile(Path)` | File at a path | Allows reading from a file; must ensure the file still exists and its contents remain unchanged | File modified/deleted, read permissions, data race, TOCTOU |
| `ofInputStream(Supplier<InputStream>)` | Stream provided by a supplier | **Must return a new stream each time** readable from the start with the same bytes | Reusing a read/closed stream, supplier returning null, live source changing |
| `ofByteArrays(Iterable<byte[]>)` | Iterable producing byte arrays | Java calls iterable/iterator on each attempt; must yield equivalent data next time | One-shot iterator, mutation, lost snapshot |
| `fromPublisher(Flow.Publisher)` | Custom-defined publisher | Replayable only if the publisher supports multiple subscriptions recreating the same data | “Hot” publisher, single-subscriber publisher, exhausted state |
| `concat(publishers...)` | Concatenates multiple publishers | The whole chain is replayable only if **every** component can recreate its bytes | One one-shot component makes the whole body unreplayable |

**There is no universal `isReplayable()` flag on Java 17's `BodyPublisher` interface.** Callers must understand the source's contract and be prepared for errors if the client attempts to re-subscribe. With a custom publisher, you must comply with `Flow.Subscription.request(n)`, `cancel()`, `onError/onComplete`, and resource-bounding policies.

### 3.1. Small String/Byte Bodies

```java
// Illustrative snippet, without full URI/client/main.
byte[] canonicalPayload = "{\"count\":2}"
        .getBytes(java.nio.charset.StandardCharsets.UTF_8);

byte[] stableCopy = canonicalPayload.clone();
var publisher = java.net.http.HttpRequest.BodyPublishers
        .ofByteArray(stableCopy);
```

Treat the original bytes as **application-immutable** across all attempts. Use `clone()` before passing to the publisher if other code might mutate the array. `clone()` by itself does not protect you if other code retains a reference to `stableCopy` and mutates it afterward.

### 3.2. Body from a File

```java
// Illustrative snippet: path is an existing java.nio.file.Path.
var publisher = java.net.http.HttpRequest.BodyPublishers.ofFile(path);
```

Merely creating a publisher from a `Path` does not prove the file contents remain immutable across redirects/authentication. For critical file uploads, you can create a **dedicated snapshot file** or record a checksum/size and verify it before each attempt. If the file is modified between two reads, two HTTP requests may carry **two different bodies** despite having the same file path.

### 3.3. Body from a Stream: Wrong and Right

**Wrong — the same InputStream closes/loses its position after the first read:**

```java
// Illustrative anti-pattern only; do not use for production requests.
java.io.InputStream oneShot = new java.io.ByteArrayInputStream(
        "HELLO".getBytes(java.nio.charset.StandardCharsets.UTF_8));

var wrong = java.net.http.HttpRequest.BodyPublishers.ofInputStream(
        () -> oneShot); // All attempts share the same consumed stream.
```

A regular stream **does not rewind itself** when the client re-subscribes. Returning the same already-read stream can cause subsequent attempts to read 0 bytes, send a corrupted body, or throw an exception.

**Right — create a new stream from a stable byte source:**

```java
// Illustrative snippet; "snapshot" must not be modified between attempts.
byte[] snapshot = "HELLO".getBytes(
        java.nio.charset.StandardCharsets.UTF_8);

var replayable = java.net.http.HttpRequest.BodyPublishers.ofInputStream(
        () -> new java.io.ByteArrayInputStream(snapshot));
```

If the body is large, the supplier can open **a new InputStream** to a snapshot file, but it must manage lifecycle and file-open errors. A `Supplier` returning `null` on a subsequent call is a case described in the Javadoc: the request will fail when a new stream cannot be obtained—the HTTP client will not conjure the old bytes out of thin air.

## 4. Why Might `401` and `407` Require Resending the Request?

### 4.1. `401 Unauthorized`: Origin Server Authentication Challenge

A typical round-trip:

```text
Client                           Origin server
  │ POST /upload, body bytes        │
  ├────────────────────────────────►│
  │ 401 Unauthorized                │
  │ WWW-Authenticate: Basic ...     │
  │◄────────────────────────────────┤
  │                                 │
  │ [Client determines valid credentials are available]
  │ POST /upload with Authorization │
  │ + replayed body bytes           │
  ├────────────────────────────────►│
  │ 200 OK or another error         │
  │◄────────────────────────────────┤
```

`401` indicates that the server requires authentication for the resource, usually accompanied by `WWW-Authenticate` describing the challenge. The client is **not forced to retry**: it depends on credentials, policy, scheme, attempt limits, server trustworthiness, and whether the body is replayable. If a retry preserves the method + body, the client must replay the body compatibly.

A request may be read in full by the server/proxy before returning a challenge, or it may be challenged early before the body. There is no general guarantee that every `401` always occurs before any body bytes are transmitted.

### 4.2. `407 Proxy Authentication Required`

`407` is a challenge from a **proxy**, with `Proxy-Authenticate` and the corresponding response header `Proxy-Authorization`. Do not confuse `407` with a `401` issued by the origin server. With a proxy, the challenge may occur at the proxy connection step, the `CONNECT` tunnel step, or the request forwarding step, depending on the proxy/protocol.

- `Authorization` is for the **origin**; `Proxy-Authorization` is for the **proxy**.
- Credentials across hops **must not be mixed up**.
- A proxy auth round-trip may require the client to redo the request, though the actual number of body transmissions depends on challenge timing and the client implementation.
- Do not place proxy credentials directly into origin request headers or leak them into logs. Java `HttpClient` can configure an `Authenticator` per proxy/origin, but you must check the appropriate policy and system context.

### 4.3. Does `Expect: 100-continue` Solve Everything?

`Expect: 100-continue` allows the client to send headers first, wait for an interim `100 Continue` signal in some cases, and then send the body; the server can return an error/auth response early. Java `HttpRequest.Builder.expectContinue(true)` supports this request.

However, **do not treat it as a guarantee that the body has never been sent**:

- The server/proxy may not support it or may handle it differently, and the client has timeouts/implementation policies.
- A response may arrive after part of the body has already started transmitting.
- If another challenge occurs or the request is redirected preserving the method, a replayable body may still be needed.
- `100 Continue` is only an interim response for **continuing transmission**, not proof that the request has been authenticated or that side effects have not occurred.

Therefore, `Expect: 100-continue` is useful to **avoid sending large bodies unnecessarily**, but it does not replace a byte-recreating supplier or an idempotency policy.

## 5. Redirects: Which Statuses Preserve the Body, Which Change the Method?

Redirect status codes are not all the same. According to RFC 9110, especially `15.4`:

| Status | Meaning | For POST When Following Redirect | Must Replay POST Body? |
|---|---|---|---|
| `301 Moved Permanently` | Permanent new URI | User agent is **permitted** to change POST to GET; JDK HttpClient has a rule converting POST→GET | If changed to GET, **no**; if keeping POST under another policy, **yes** |
| `302 Found` | Temporary alternative URI | Similar to 301, may change POST to GET; JDK HttpClient converts POST→GET | Depends on the chosen method |
| `303 See Other` | View result at another URI | Typically sends **GET** (or HEAD as appropriate), dropping the POST body | **Does not** resend POST body |
| `307 Temporary Redirect` | Temporary redirect **without changing method** | Must preserve method, and normally preserves body | **Yes**, if POST has a body |
| `308 Permanent Redirect` | Permanent redirect **without changing method** | Must preserve method, and normally preserves body | **Yes**, if POST has a body |

A valid redirect usually carries `Location`. Looking only at the 3xx code is not enough; you need to know whether `Location` is present, whether the target URI is valid, whether the protocol scheme or host/origin changes, redirect limits, and whether the app is permitted to send the body/credentials to the new destination.

### 5.1. `307` and `308`: Must Preserve Method on Redirect

`307` and `308` were created to avoid the historical ambiguity of 301/302. If a user agent decides to follow automatically, it **must not turn POST into GET** just to avoid replaying the body. If the body is already consumed and the source cannot recreate it, the right choice is **not to follow or to report an error**, rather than silently sending a GET request in place of a POST with side effects.

### 5.2. `303`: Viewing the Result with Another Request

A server may use the POST→303→GET pattern:

```text
POST /orders                -> 303 See Other
                               Location: /orders/123

GET  /orders/123            -> 200 OK (view order status)
```

The GET after the redirect **is not replaying the POST body**. It is a new request with a different method standardized by redirect semantics. Do not interpret `303` as a guarantee that the initial POST has not executed; typically the POST has already created the resource and the server is pointing to the result URI.

### 5.3. Java 17 `HttpClient.Redirect`

`HttpClient.Redirect` has these policies:

- `NEVER`: do not follow automatically; the caller receives the 3xx response and decides.
- `NORMAL`: follow automatically, **except for redirects from HTTPS down to HTTP**.
- `ALWAYS`: allows following per client policy even on downgrades; **should not be used casually** with sensitive tokens/bodies.

**The default policy of Java 17 `HttpClient` is `NEVER`.** To follow automatically, you must configure it:

```java
// Illustrative snippet; requires importing HttpClient.
HttpClient client = HttpClient.newBuilder()
        .followRedirects(HttpClient.Redirect.NORMAL)
        .build();
```

The Java 17 Javadoc explicitly notes that the Java HTTP client **converts POST to GET when following `301` or `302`**. With `307`/`308` it preserves the method; with `303` it normally switches to GET. When not following automatically, the 3xx response and `Location` are handled by the caller, without automatically creating a subsequent request.

**A follow policy does not by itself make a body replayable**: the redirect only dictates *which request to send next*, while the publisher must recreate the bytes if the next request needs to keep the body.

## 6. Cross-Origin Redirects: Check Data and Credentials Before Resending

A `Location` can point to a relative path within the same origin, or an absolute URI to a **different host**. When the origin changes, automatically resending the body can **leak information** even if the client handles `Authorization` properly:

```text
POST https://api.company.example/upload
Body = internal document
   |
   | 307 Location: https://external.example/collect
   v
POST internal body to a different origin?   <-- NEEDS policy approval!
```

This is a warning diagram, not a real recommended address. Necessary principles:

1. **Follow only to trusted origins**, especially when the body contains PII, internal files, secrets, or transactions with side effects.
2. Check the **scheme**: avoid HTTPS→HTTP transitions; `Redirect.NORMAL` rejects this downgrade, but you must still evaluate other redirects.
3. Verify the target domain/port/path, limit redirect counts and loops; do not blindly trust a `Location` returned by a server if that server could be compromised.
4. Handle **Authorization, Cookie, Proxy-Authorization** according to scope and policy; do not copy sensitive headers verbatim to another origin in a custom client.
5. With `307`/`308`, in addition to the method, the original body is preserved, so data-leak risk can be higher than with `303` switching to GET. **Even GET** can still carry secrets in the URI/query, so it is not safe by default.
6. For critical state-changing workflows, consider `Redirect.NEVER` and **manually inspect** `Location`, the target allowlist, and consent before resending.

**Do not rely solely on the publisher being able to produce the body.** A replayable publisher is a technical condition, whereas **where it is allowed to be sent** is an independent security/business condition.

## 7. Java 17+: `307` Replays the Body, `303` Switches to GET

This example runs an `HttpServer` on loopback on a dynamic port; both redirects are **same-origin**. It requires no Internet or accounts. The server reads the first request's body before issuing the redirect, so we can clearly observe that the body source must be reopened.

- `/redirect307` reads the POST body and returns `307 Location: /final307`.
- `/final307` inspects the method and body when the HTTP client follows.
- `/redirect303` returns `303 Location: /final303`.
- `/final303` inspects the method after following.
- `BodyPublishers.ofInputStream` increments a counter each time the supplier opens a new stream.

**File `RedirectReplayDemo.java`:**

```java
import com.sun.net.httpserver.HttpServer;
import java.io.ByteArrayInputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public class RedirectReplayDemo {
    private static void reply(com.sun.net.httpserver.HttpExchange exchange,
                              int code, String text) throws java.io.IOException {
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        exchange.sendResponseHeaders(code, bytes.length);
        try (var out = exchange.getResponseBody()) { out.write(bytes); }
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress(InetAddress.getLoopbackAddress(), 0), 0);
        AtomicInteger opens307 = new AtomicInteger();
        AtomicInteger opens303 = new AtomicInteger();
        AtomicReference<String> target307 = new AtomicReference<>("");
        AtomicReference<String> target303 = new AtomicReference<>("");
        try {
            server.createContext("/redirect307", ex -> {
                try (ex) {
                    ex.getRequestBody().readAllBytes();
                    ex.getResponseHeaders().set("Location", "/final307");
                    ex.sendResponseHeaders(307, -1);
                }
            });
            server.createContext("/final307", ex -> {
                try (ex) {
                    target307.set(ex.getRequestMethod() + ":" + new String(
                            ex.getRequestBody().readAllBytes(), StandardCharsets.UTF_8));
                    reply(ex, 200, "OK307");
                }
            });
            server.createContext("/redirect303", ex -> {
                try (ex) {
                    ex.getRequestBody().readAllBytes();
                    ex.getResponseHeaders().set("Location", "/final303");
                    ex.sendResponseHeaders(303, -1);
                }
            });
            server.createContext("/final303", ex -> {
                try (ex) {
                    target303.set(ex.getRequestMethod() + ":" +
                            ex.getRequestBody().readAllBytes().length);
                    reply(ex, 200, "OK303");
                }
            });
            server.start();

            URI base = URI.create("http://localhost:" + server.getAddress().getPort());
            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .followRedirects(HttpClient.Redirect.NORMAL)
                    .connectTimeout(Duration.ofSeconds(3)).build();

            HttpRequest p307 = HttpRequest.newBuilder(base.resolve("/redirect307"))
                    .timeout(Duration.ofSeconds(5))
                    .POST(HttpRequest.BodyPublishers.ofInputStream(() -> {
                        opens307.incrementAndGet();
                        return new ByteArrayInputStream(
                                "PAYLOAD".getBytes(StandardCharsets.UTF_8));
                    })).build();
            var r307 = client.send(p307, HttpResponse.BodyHandlers.ofString());

            HttpRequest p303 = HttpRequest.newBuilder(base.resolve("/redirect303"))
                    .timeout(Duration.ofSeconds(5))
                    .POST(HttpRequest.BodyPublishers.ofInputStream(() -> {
                        opens303.incrementAndGet();
                        return new ByteArrayInputStream(
                                "PAYLOAD".getBytes(StandardCharsets.UTF_8));
                    })).build();
            var r303 = client.send(p303, HttpResponse.BodyHandlers.ofString());

            System.out.println("307 status: " + r307.statusCode());
            System.out.println("307 destination: " + target307.get());
            System.out.println("307 stream openings: " + opens307.get());
            System.out.println("303 status: " + r303.statusCode());
            System.out.println("303 destination: " + target303.get());
            System.out.println("303 stream openings: " + opens303.get());
        } finally { server.stop(0); }
    }
}
```

Run in the directory containing the file above with **JDK 17 or later**:

```bash
javac --release 17 -encoding UTF-8 RedirectReplayDemo.java
java RedirectReplayDemo
```

**Verified stdout compiled and run on loopback:**

```text
307 status: 200
307 destination: POST:PAYLOAD
307 stream openings: 2
303 status: 200
303 destination: GET:0
303 stream openings: 1
```

**Analysis:**

- `307 status: 200` is the **final status after auto-following**, not the first server returning 200. The first server returned `307`; the response the caller receives after the redirect has status `200`.
- `307 destination: POST:PAYLOAD` confirms the next request kept **POST** and carried the exact original payload.
- `307 stream openings: 2` confirms the supplier created a `ByteArrayInputStream` for each send attempt. This is a concrete example of why you must not return the same consumed `InputStream`.
- For `303`, the client switched to **GET**; `GET:0` shows the new request's body length is 0. The supplier opened only once for the initial POST.
- The server uses a random port on `InetAddress.getLoopbackAddress()` and sends no body out to the Internet. There is no idempotency mechanism in the demo; the two endpoints merely observe requests.
- `HttpClient.Redirect.NORMAL` is enabled explicitly; if `followRedirects` is omitted, the default policy is `NEVER` so the example would not follow automatically.
- Although the demo shows stream opening counts of 2/1, the actual number of subscriptions in a large app can also depend on cancellation, internal retries, connection errors, or policy. **Do not hardcode the number 2** for business logic; the supplier must be able to provide the right data for every valid attempt.

This example illustrates both **method preservation** and **body replay**, not a guarantee that a real POST operation is executed only once.

## 8. Java 17+: `401` Authentication Causes the Body to Be Read Again

The second example creates a loopback `HttpServer` requiring **Basic authentication**. The first request has its body read by the server, but lacks valid credentials, so it returns `401` with `WWW-Authenticate`. Java `HttpClient` has an `Authenticator` that supplies credentials, then creates a new request with authentication and **replays the POST body**.

**Use dummy credentials on loopback only**. Basic authentication sends the password in Base64, **which is not secure encryption**; outside local testing, HTTPS/TLS and a secrets management policy are required. Do not hardcode real passwords in source code.

**File `AuthenticationReplayDemo.java`:**

```java
import com.sun.net.httpserver.HttpServer;
import java.io.ByteArrayInputStream;
import java.net.Authenticator;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.PasswordAuthentication;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Base64;
import java.util.concurrent.atomic.AtomicInteger;

public class AuthenticationReplayDemo {
    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress(InetAddress.getLoopbackAddress(), 0), 0);
        AtomicInteger attempts = new AtomicInteger();
        AtomicInteger streams = new AtomicInteger();
        String expectedHeader = "Basic " + Base64.getEncoder().encodeToString(
                "demo:secret".getBytes(StandardCharsets.ISO_8859_1));
        try {
            server.createContext("/secure", exchange -> {
                try (exchange) {
                    attempts.incrementAndGet();
                    byte[] body = exchange.getRequestBody().readAllBytes();
                    boolean authorized = expectedHeader.equals(
                            exchange.getRequestHeaders().getFirst("Authorization"));
                    if (!authorized) {
                        exchange.getResponseHeaders().add(
                                "WWW-Authenticate", "Basic realm=\"local-demo\"");
                        exchange.sendResponseHeaders(401, -1);
                    } else {
                        String text = new String(body, StandardCharsets.UTF_8);
                        byte[] response = ("accepted:" + text)
                                .getBytes(StandardCharsets.UTF_8);
                        exchange.sendResponseHeaders(200, response.length);
                        try (var out = exchange.getResponseBody()) {
                            out.write(response);
                        }
                    }
                }
            });
            server.start();

            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(3))
                    .authenticator(new Authenticator() {
                        @Override
                        protected PasswordAuthentication getPasswordAuthentication() {
                            return new PasswordAuthentication(
                                    "demo", "secret".toCharArray());
                        }
                    }).build();
            URI url = URI.create(
                    "http://localhost:" + server.getAddress().getPort() + "/secure");
            HttpRequest request = HttpRequest.newBuilder(url)
                    .timeout(Duration.ofSeconds(5))
                    .POST(HttpRequest.BodyPublishers.ofInputStream(() -> {
                        streams.incrementAndGet();
                        return new ByteArrayInputStream(
                                "HELLO".getBytes(StandardCharsets.UTF_8));
                    })).build();
            var response = client.send(request, HttpResponse.BodyHandlers.ofString());
            System.out.println("Final status: " + response.statusCode());
            System.out.println("Final body: " + response.body());
            System.out.println("Server attempts: " + attempts.get());
            System.out.println("Supplier openings: " + streams.get());
        } finally { server.stop(0); }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 AuthenticationReplayDemo.java
java AuthenticationReplayDemo
```

**Verified stdout:**

```text
Final status: 200
Final body: accepted:HELLO
Server attempts: 2
Supplier openings: 2
```

Explanation:

1. The first request to `/secure` lacks a valid `Authorization`. The server **reads the body before returning 401** to emphasize that you cannot rely on “401 will surely happen before the body is consumed.”
2. `WWW-Authenticate: Basic realm="local-demo"` is the challenge sent back by the origin.
3. `HttpClient` queries `Authenticator`; on the next attempt, the client supplies credentials and the request **remains a POST with body HELLO**.
4. `Supplier openings: 2` means the supplier created two distinct `ByteArrayInputStream` instances with identical bytes. Reusing an old stream after it was read to completion would violate the contract.
5. `Server attempts: 2` is the number of times the handler saw an HTTP request in the demo; **do not assume there are always exactly two attempts** across all authentication schemes, proxies, or networks.
6. `Final status: 200` is the final response; the caller does not see the intermediate 401 in the way `client.send` automatically handles the challenge in this experiment.
7. The demo's goal is **replayability**, not a guide to production authentication. In real applications, verify host/origin, TLS scheme, challenge realm, retry limits, and secret handling; do not print credentials/Authorization into logs.

**Proxy `407` follows a similar principle regarding needing the body again**, but the message uses `Proxy-Authenticate`/`Proxy-Authorization` and depends on proxy configuration. The experiment does not simulate a real proxy, so it does not claim to have tested `407`.

## 9. Java 17+: One-Shot Stream Fails When Redirect Requires Resending

The third example intentionally creates a **non-replayable body**. The supplier provides a `ByteArrayInputStream` only on the first call; on the second call it returns `null`. The server returns `307`, requiring the Java HTTP client to recreate the POST body at the new URI. According to the `BodyPublishers.ofInputStream` Javadoc, if the supplier returns `null` on a subsequent attempt, the request will fail.

**File `OneShotReplayFailureDemo.java`:**

```java
import com.sun.net.httpserver.HttpServer;
import java.io.ByteArrayInputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

public class OneShotReplayFailureDemo {
    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress(InetAddress.getLoopbackAddress(), 0), 0);
        AtomicInteger supplierCalls = new AtomicInteger();
        AtomicInteger redirectedHits = new AtomicInteger();
        try {
            server.createContext("/first", ex -> {
                try (ex) {
                    ex.getRequestBody().readAllBytes();
                    ex.getResponseHeaders().add("Location", "/second");
                    ex.sendResponseHeaders(307, -1);
                }
            });
            server.createContext("/second", ex -> {
                try (ex) {
                    redirectedHits.incrementAndGet();
                    ex.getRequestBody().readAllBytes();
                    ex.sendResponseHeaders(200, -1);
                }
            });
            server.start();
            URI uri = URI.create(
                    "http://localhost:" + server.getAddress().getPort() + "/first");
            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .followRedirects(HttpClient.Redirect.NORMAL)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();
            HttpRequest request = HttpRequest.newBuilder(uri)
                    .timeout(Duration.ofSeconds(5))
                    .POST(HttpRequest.BodyPublishers.ofInputStream(() -> {
                        if (supplierCalls.incrementAndGet() != 1) return null;
                        return new ByteArrayInputStream(
                                "ONCE".getBytes(StandardCharsets.UTF_8));
                    })).build();
            boolean failed = false;
            try {
                client.send(request, HttpResponse.BodyHandlers.discarding());
            } catch (java.io.IOException expected) {
                failed = true;
            }
            System.out.println("Resend failed: " + failed);
            System.out.println("Supplier calls: " + supplierCalls.get());
        } finally { server.stop(0); }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 OneShotReplayFailureDemo.java
java OneShotReplayFailureDemo
```

**Verified stdout:**

```text
Resend failed: true
Supplier calls: 2
```

Key takeaways:

- On the first call, the supplier returns `ByteArrayInputStream("ONCE")`; server `/first` reads the body and returns 307.
- Following 307 preserves POST and needs the body, so the client invokes the supplier again.
- The supplier **intentionally returns `null`**: no new stream is available. The Java HTTP client does not save previous content to recreate the body, and the resend fails with an I/O error.
- `Resend failed: true` is a controlled printout for test results, not a recommendation to use a catch-all and swallow `IOException` in real applications. Production code must log/contextualize the error, ensure cleanup, and provide appropriate recovery behavior.
- Important warning: the first server **already received and read the body**. The follow failure **does not prove the first request had no business impact**. For operations like placing an order, the caller must not generate a new request ID to “resend just to be sure” without a deduplication mechanism.
- `redirectedHits` in the demo is an observation counter on the target server, not to be used to decide transaction success. The demo intentionally prints only two stable lines to illustrate supplier calls.

If the actual body is a one-time-read camera stream or socket stream, the solution is usually **not to auto-follow redirects that preserve the body**, or to create a suitable snapshot/seekable source before starting. You cannot “fix” it with `InputStream.mark/reset` when the stream type does not support it or the data has already changed.

## 10. Keeping the Body Stable Across Attempts

Returning a new stream each time is **not enough** if it produces **different content**. For example:

```java
// Illustrative anti-pattern: timestamp changes on each attempt.
var publisher = java.net.http.HttpRequest.BodyPublishers.ofInputStream(
        () -> new java.io.ByteArrayInputStream(
                ("sentAt=" + System.nanoTime())
                        .getBytes(java.nio.charset.StandardCharsets.UTF_8)));
```

Each subscription reads data, but the body differs. If the server uses an HMAC signature, request ID, checksum, or business idempotency key, that difference can cause verification or deduplication to fail. A body can be **technically replayable** yet fail the condition of **same intent/same payload**.

### 10.1. Snapshot Before Sending

Suitable for small bodies:

```java
// Illustrative snippet: serialize once before building HttpRequest.
byte[] snapshot = "{\"amount\":100}"
        .getBytes(java.nio.charset.StandardCharsets.UTF_8);
byte[] stable = snapshot.clone();

var body = java.net.http.HttpRequest.BodyPublishers.ofInputStream(
        () -> new java.io.ByteArrayInputStream(stable));
```

For large bodies, you should not always load them onto the heap; you can use an immutable temporary file, a versioned object storage snapshot, or a stream provider that rereads from offset 0. You must control retention time, cleanup, access permissions, hash/size, and prevent the file from being written to during resends.

### 10.2. Unreplayable Data

Sources that are **not inherently replayable**:

- Live camera/audio streams that have not been recorded.
- File/socket `InputStream`s already read to the end with no way to reopen.
- A “hot” reactive `Flow.Publisher` that only emits current events and does not support replay.
- An iterable tied to a single consumed `Iterator` instead of spawning a new iterator.
- A stream using a one-time token or depending on state that changes after the first read.

For these sources, you usually need to **restart from an authorized source**, save a snapshot before sending, or disable automatic replay. If the server still needs to allow large uploads with auth, you can **pre-authenticate with a small request**, upload in chunks with a checksum/offset/commit protocol, or use a pre-verified URI/credential. Designing a resumable upload is usually better than “retrying an entire unreproducible stream.”

### 10.3. Known Content-Length Does Not Equal a Snapshot

Even when a publisher reports `contentLength()==N`, you must still ensure every attempt sends **exactly N bytes**. A truncated source file or a supplier returning a shorter stream can cause the request to fail. Conversely, a streaming publisher reporting an unknown length can be valid if the protocol and library support it; what matters for replay is **reproducible content**, not just the number N.

## 11. Replay and Business Safety: Two Layers of Protection

A retry cycle can cause the server to receive **two independent HTTP requests**. For example:

```text
POST /charge, requestId=pay-001
    → server commits payment
    → 200 response is lost or not received by client

Client retries due to timeout / auth flow / redirect
    POST /charge, requestId=pay-001
    → if server does not deduplicate, it may charge again
```

Even a 100% stable body can produce duplicate side effects. Non-idempotent business operations require:

1. **A stable business intent key** across all attempts of the same operation, such as `Idempotency-Key` per the API contract. Do not generate a new ID on each retry.
2. **Server stores the result by key + scope + payload fingerprint** and ensures concurrency/crash handling via transactions or an appropriate idempotent mechanism.
3. **Distinguish final responses** from intermediate responses; a timeout state does not prove the request did not commit.
4. **Bound time and attempt counts**, retrying with backoff/jitter when appropriate; do not allow infinite redirect/auth loops.
5. For method-preserving redirects, verify that the **target location is actually authorized to process the same intent**; do not automatically send payment commands to an arbitrary origin.
6. If the outcome cannot be determined, **query the business status** by transaction ID instead of arbitrarily replaying with a new ID.

### Situations Where You Should Not Retry Automatically

| Situation | Why You Must Stop/Check |
|---|---|
| `POST /charge` without an idempotency contract | Risk of duplicate charging |
| Unreplayable live stream when `307` requires the old body | Cannot recreate the same data |
| `Location` redirects to an unauthorized origin | Risk of leaking body/credentials |
| Repeated `401` despite valid credentials | Possibly wrong realm/permission/secret; should not retry infinitely |
| `407` from an untrusted/unconfigured proxy | Avoid sending origin credentials to a proxy |
| Body is a mutable file being written by another process | Attempts may differ in bytes |
| Client times out after server received part/all of the request | Business outcome is unknown |
| Payload has a fresh timestamp signature on every attempt | Hash/signature/dedup no longer represent the same intent |

**Do not confuse `retry` and `redirect`:** a redirect is a server instruction for the next URI, whereas a retry can be triggered by a timeout/error. Both can cause re-subscription; however, permissions and semantics differ. `401/407` is an authentication challenge, not a 3xx redirect.

## 12. HTTP Client Policies and Managing Resend Permissions

### 12.1. `NEVER`: Caller Decides on Redirects

For sensitive bodies or non-idempotent operations, consider:

```java
// Illustrative snippet, without full URI/client/request.
HttpClient client = HttpClient.newBuilder()
        .followRedirects(HttpClient.Redirect.NEVER)
        .build();
```

After `client.send(...)` returns a 3xx response, the application reads `Location`, resolves relative URIs, checks the target allowlist, scheme, method/status, permission to send the body, hop count, and business state before deciding to create the next request. Do not copy `Authorization`/`Cookie` directly to a new origin.

### 12.2. `NORMAL` Is Not a Comprehensive Security Policy

`Redirect.NORMAL` blocks automatic HTTPS→HTTP per the Javadoc, but **does not automatically know** which body is sensitive, which host is approved by the organization, or whether a redirect is permitted to execute a financial command. Do not equate “NORMAL” with “safe for every POST.” `ALWAYS` requires even greater caution because it does not enforce the same anti-downgrade constraint.

### 12.3. Authenticator Must Control Scope

`Authenticator` should supply credentials **for the right origin/proxy and realm** per policy. Java provides APIs for requestor type/host/port/scheme context; the demo above supplies dummy credentials for any challenge on the same localhost test for simplicity, but production must be selective. Do not log secrets or raw Authorization headers.

### 12.4. Asynchronous Sending Does Not Eliminate the Replay Issue

`HttpClient.sendAsync(...)` returns a `CompletableFuture<HttpResponse<T>>`, but the request body is still supplied via `BodyPublisher`. If a redirect/authentication requires the client to resend, the publisher must still satisfy a new subscription. If the future is cancelled or the request times out, do not assume the server has not read the body. Asynchronous I/O completion does not alter business semantics.

## 13. Debugging: What Evidence Identifies a Replay?

Logs should distinguish a **logical request** from a **network attempt**:

```text
timestamp | logicalRequestId | attemptNo | currentUri | method
          | bodyFingerprint | bodyBytes | bodyPublisherSubscriptionId
          | authChallenge=401/407 | redirectStatus=3xx
          | redirectTarget | finalStatus | exceptionClass
          | idempotencyKey | businessRecordId
```

Do not log sensitive payloads, passwords, tokens, or full `Authorization` headers. If a fingerprint is needed, use a hash compliant with security policy, and do not treat the hash as a credential. In the Java demos we count **how many times the supplier is invoked**, which is a very concrete signal that the client needed a new source; however, in production, any retry/cancellation can change the count.

### Common Error Matrix

| Symptom | Possible Cause | What to Check |
|---|---|---|
| `307` then client throws `IOException` | Not replayable, null supplier, source error | Does the supplier create a new stream with identical bytes? |
| Subsequent attempt sends empty body | Reused the same consumed InputStream | Fresh stream on every attempt |
| After `401` re-auth is needed but POST fails to send | One-shot publisher or mismatched credentials policy | Authenticator/challenge, body source, and final status |
| After `303` POST turns into GET | Correct redirect semantics | Do not expect a POST body on GET |
| After `301/302` POST turns into GET on JDK | Java HttpClient behavior per Javadoc | Use 307/308 if the server needs to preserve method and client is allowed to follow |
| `307/308` keeps method but payload differs | Supplier reads mutating data each time | Snapshot/canonicalization/hash |
| File upload retry fails | File deleted, missing permissions, content changed | File lifetime, snapshot, reopen, cleanup |
| Large upload consumes lots of RAM | Buffering entire body onto heap for retries | Streaming from immutable file or resumable protocol |
| HTTPS redirect to HTTP does not run | `Redirect.NORMAL` disallows downgrade | Do not blindly upgrade to ALWAYS; inspect target |
| Body sent to an unexpected host | Auto-following redirects without an allowlist | Restrict origin/URI, control sensitive headers |
| Request executed twice | Replayable body but non-idempotent business effect | Stable requestId, server dedup, transaction/reconciliation |
| `401/407` loops endlessly | Wrong credentials, proxy/realm mismatch | Retry cap, control Authenticator, and report error |
| Supplier not called a second time | Redirect not followed, method switched to GET, source not needed again | Check policy and next response/method |

**Never deduce “if the Java client returned IOException, the server did not process it.”** Bytes may have already arrived and business effects may have already occurred before the client observed the error.

### Investigation Sequence

1. Record the **intermediate response status/headers**: 401 or 407? 303 or 307? Is there a valid Location/challenge?
2. Check client policy: `Redirect.NEVER/NORMAL/ALWAYS`, `Authenticator`, proxy selector, request timeout, and attempt count.
3. Determine the **method of the next request**. If switched to GET, no POST body is needed; if POST is preserved, the publisher must replay the bytes.
4. Instrument the supplier/subscription without leaking data. Check whether the second attempt creates a new stream reading from the beginning.
5. If the body can be recreated, compare checksum and size across two attempts (in an authorized test environment).
6. Check URI, TLS downgrade, realm, Authorization scope, and allowlist before sending the body elsewhere.
7. If the operation has side effects, check the transaction ID/idempotency outcome on the server; do not guess from client-side I/O errors.

## 14. Designing a Replayable Producer for Large Bodies

A practical strategy for large file uploads is **separating the data preparation lifecycle** from the **HTTP attempts lifecycle**:

```text
Prepare:
  serialize exact payload once
  store in immutable snapshot (temp file with restricted permissions)
  compute size, hash, requestId
  mark snapshot READY

Attempt #1:
  open new stream from snapshot, send
  if final response succeeds -> mark DONE

Challenge/Redirect per policy:
  check status, credentials, URI, method, and business safety
  if replay is needed:
     open new stream from the same snapshot
     send the same requestId and body bytes

Finalize:
  after all attempts/futures finish, close remaining streams
  delete snapshot per cleanup policy
```

**Technical conditions:** the snapshot is stable enough for multiple reads; the number of replay sources is bounded; invoking the supplier creates no unwanted side effects; never return a closed stream; never forward sensitive data to an unfamiliar host. If an attempt is cancelled mid-way, clarify the lifecycle before deleting the snapshot.

**Business conditions:** the server accepts the same idempotency key within an appropriate window and does not apply the effect twice. If the server only accepts a single upload/offset-based chunk, the design must know the resume position instead of resending the entire body.

### Why Not Simply Call `mark/reset`?

Many `InputStream`s do not support `mark/reset`, or the read limit is insufficient to reset after a large body has been read. Moreover, subscribers may be used concurrently/cancelled, and the underlying body may have changed. **A fresh stream from a stable snapshot** is much clearer in terms of ownership, exceptions, and replayability.

### What If the Source Can Only Be Read Once?

Do not pretend it is replayable. When the server requires 307/308 or an authentication resend, the right choice may be:

- Return a clear error “request body cannot be replayed” and keep the outcome state unknown.
- Disable automatic redirects and handle them under a different contract.
- Authenticate/obtain a token before starting the stream.
- Use a dedicated resumable/chunked upload protocol with transactions/checkpoints and status verification.
- If permitted, snapshot before the first send and enforce size/lifetime limits.

## 15. Self-Check Questions

**Question 1.** A client POSTs using `BodyPublishers.ofInputStream(() -> existingStream)`, and the server returns 307. Why might the next request fail?  
**Answer:** The new subscription will receive **the same already-read/closed InputStream**, with no bytes from the beginning. You must provide a new stream with the same content or not follow.

**Question 2.** Is `BodyPublisher.contentLength()==1000` enough to prove a body is replayable?  
**Answer:** No. It only describes the expected byte count; it does not prove the source can still produce 1,000 bytes on a subsequent subscription.

**Question 3.** The server returns 303 after an order-creation POST, and the client follows with GET. Is it replaying the POST body?  
**Answer:** No. The method is switched to GET to fetch the result at the target URI; the original POST may have already created the order.

**Question 4.** Do 307 and 308 allow the client to automatically switch POST to GET when following?  
**Answer:** No. These are **method-preserving** redirects; if a body is required, the body must be recreated.

**Question 5.** Java `HttpClient` has no `followRedirects` configured. Will it automatically follow 307?  
**Answer:** No, under Java 17's default `Redirect.NEVER` policy.

**Question 6.** A POST body can be replayed 10 times. Is it guaranteed that POSTing will not create 10 transactions?  
**Answer:** No. Replayability only concerns bytes; side effects require separate idempotency/business transaction protection.

**Question 7.** `ofFile(path)` is created before the file is modified. Is the replay guaranteed to match the first attempt?  
**Answer:** You should not assume so. You need an immutable snapshot, stable permissions, and an integrity policy.

**Question 8.** How do `401` from an origin and `407` from a proxy differ?  
**Answer:** `401/WWW-Authenticate/Authorization` pertains to the origin; `407/Proxy-Authenticate/Proxy-Authorization` pertains to the proxy.

**Question 9.** Does `Expect: 100-continue` make a one-shot body replayable?  
**Answer:** No. It can help avoid sending the body before the server permits continuing, but it does not guarantee the body was never sent in all scenarios.

**Question 10.** For a redirect `Location` from HTTPS to HTTP, what will `Redirect.NORMAL` do?  
**Answer:** Java 17 `HttpClient.Redirect.NORMAL` does not automatically follow HTTPS→HTTP. Do not assume all other redirects are safe just because of that.

**Question 11.** A custom publisher from a hot `Flow.Publisher` emits events only once, and then the HTTP client re-subscribes. Are the same bytes guaranteed?  
**Answer:** No. A custom source must support multiple subscriptions producing the same data, or the caller must disable resending/snapshot beforehand.

**Question 12.** An `ofInputStream` supplier returns `null` on the second attempt, but the first server already read the body. Can you generate a new request ID and resend from scratch to fix it?  
**Answer:** You should not. The first server may have already processed the side effect; you must verify the outcome and keep the ID stable if there is an idempotency contract.

**Question 13.** How does Java `HttpClient` typically handle `301/302` with POST when auto-following?  
**Answer:** The Java 17 Javadoc states that POST is converted to GET. To require preserving POST, the server-side API should use 307/308 and the client should have an appropriate policy.

**Question 14.** Why does a supplier creating a new stream containing `System.nanoTime()` fail proper replayability?  
**Answer:** Each attempt has different bytes. Proper replay requires stable data per logical request.

**Question 15.** Does a final 200 response after an automatic 401/307 flow mean only one HTTP request was sent?  
**Answer:** No. The caller typically only receives the final response; server logs and supplier counters reveal the intermediate attempts.

**Question 16.** A 307 redirects a file upload to an untrusted host, yet the publisher reopens the file cleanly. Should it follow?  
**Answer:** Not just because it is “technically possible.” You must check origin, TLS, permission to send the body, and security policy.

## 16. Key Takeaways and Checklist

- **Replayable body** = a new subscription/attempt can recreate **the same bytes**; it is not idempotency or network retransmission.
- Java `BodyPublisher` is a `Flow.Publisher<ByteBuffer>`; resending creates a new subscription, and the data must be equivalent.
- `ofInputStream` **does not buffer the body for you**; the supplier must create a **new InputStream** each time, and if it returns `null` on a later attempt, the request may fail.
- `ofString`/`ofByteArray` are convenient for small, stable content; `ofFile` and custom publishers must manage mutating data, lifetime, and multiple subscriptions.
- `401`/`407` may require resending the body after a challenge; `Expect: 100-continue` does not completely eliminate the need for replay.
- `307`/`308` preserve method + body, `303` typically converts POST to GET, `301`/`302` allow converting POST→GET and Java HttpClient does so when following.
- `HttpClient.Redirect.NEVER` is the default; `NORMAL` does not follow HTTPS→HTTP; `ALWAYS` requires greater caution regarding downgrades.
- Every automatic resend must evaluate **authorization scope, redirect target, attempt limits, and business idempotency**.
- If replay is not possible, **report an error or change the protocol**—do not silently alter the method/body or replay a new transaction with a new ID.
- Use request/body hashes, logical request IDs, and attempt counters when debugging; do not log secrets.

### References

- [Java 17 `HttpRequest.BodyPublisher` — new subscription when resending is needed](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublisher.html)
- [Java 17 `HttpRequest.BodyPublishers` — `ofInputStream`, `ofFile`, `ofByteArray`, `fromPublisher`](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublishers.html)
- [Java 17 `HttpClient` — builder, default redirects, authenticator](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html)
- [Java 17 `HttpClient.Redirect` — `NEVER`, `NORMAL`, `ALWAYS`](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Redirect.html)
- [Java 17 `HttpRequest.Builder` — `expectContinue`](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html)
- [RFC 9110 — HTTP Semantics: `401`, `407`, `15.4 Redirection](https://www.rfc-editor.org/rfc/rfc9110.html)
- [RFC 9205 — Building Protocols with HTTP: redirect semantics](https://www.rfc-editor.org/rfc/rfc9205.html)
