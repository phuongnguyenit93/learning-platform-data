# Mutable Builders and Built Client and Request Objects

## Lesson Objectives

In Java 17+, the `java.net.http` API uses the **Builder pattern** to create `HttpClient` and `HttpRequest`. A very important distinction is that **the builder remains mutable**, whereas **the built object is designed to be immutable with respect to its configuration**. Without understanding this boundary, a program can easily send the wrong URI, headers, body, or timeout/redirect configuration, especially when multiple threads work together.

After this lesson, you will be able to:

- Distinguish between `HttpClient.Builder`, `HttpClient`, `HttpRequest.Builder`, and `HttpRequest`.
- Explain accurately that each `build()` call creates **a new object based on the builder's state at that moment**, without turning the builder into a locked object.
- Demonstrate that **modifying a builder after `build()`** does not change the configuration of an already created `HttpClient` or the method/URI/headers of an already created `HttpRequest`.
- Know that `HttpClient` should be **reused** to share connection resources; a built `HttpRequest` can be reused according to API semantics, but you must consider its body publisher and resending non-idempotent requests.
- Use `header`, `setHeader`, `uri`, `timeout`, `GET`/`POST`, `HttpRequest.Builder.copy()`, and `HttpRequest.newBuilder(existingRequest, filter)` with their exact intended semantics.
- Distinguish **client-level** properties (connect timeout, HTTP version preference, redirect policy, proxy, TLS) from **request-level** properties (URI, method, headers, body, request timeout).
- Choose a thread-safe coordination approach: **do not share a single builder for concurrent modifications**; share built clients/requests within an appropriate scope.
- Verify behavior with a Java 17 program running an **HTTP server/client on loopback**, with no Internet access required.

**Scope:** Java SE 17 `java.net.http.HttpClient`/`HttpRequest` and their corresponding builders. Differences in Java 21+ are noted separately when they affect resource lifecycle; no APIs that do not exist on Java 17 are used.

## 1. Mental Model: The Builder Is a Draft, the Built Object Is a Finalized Configuration

Overview diagram:

~~~text
HttpClient.newBuilder()
       │
       ▼
HttpClient.Builder  ──── mutable configuration: version, redirect,
       │                  connectTimeout, proxy, TLS, executor...
       │ build()
       ▼
  HttpClient A       ← built configuration; used to send multiple requests
       ▲
       │
       └─── HttpClient.Builder can still be modified further and build() called
                                         │
                                         ▼
                                    HttpClient B

HttpRequest.newBuilder(uri)
       │
       ▼
HttpRequest.Builder ──── mutable configuration: method, URI,
       │                  header, request timeout, body...
       │ build()
       ▼
  HttpRequest X     ← method/URI/header/timeouts already created
       ▲
       │
       └─── builder continues to change, build() called again
                                         │
                                         ▼
                                    HttpRequest Y
~~~

**Key mental model:**

1. `newBuilder()` creates a **builder**, not the final client/request yet.
2. Setters on a builder **mutate the builder instance itself** and typically return `this` for method chaining.
3. `build()` returns **a new client/request** based on the builder's state at the time of the call.
4. **A builder is not automatically disabled after `build()`**: you can keep calling setters and call `build()` again.
5. **Previously built objects are not "upgraded" along with the builder**. To change client configuration or request parameters, create another object.
6. "Immutable" here primarily refers to **the object's configuration**. It does not mean every object referenced through the configuration is deeply immutable, or that the client's network state never changes.

Conceptual example:

~~~java
HttpClient.Builder builder = HttpClient.newBuilder();
HttpClient first = builder.build();

builder.followRedirects(HttpClient.Redirect.ALWAYS);
HttpClient second = builder.build();

// first does not automatically change its policy just because the builder changed.
~~~

This snippet requires importing `java.net.http.HttpClient`. `first` and `second` are two independent objects created from two different configuration snapshots. Do not mistake `first = builder.build()` for a "live link" to the builder.

## 2. The Four Object Types and Their Mutability

| Object | How It Is Created | Can It Be Modified After Creation? | What Should It Be Used For? |
|---|---|---|---|
| `HttpClient.Builder` | `HttpClient.newBuilder()` | **Yes**, via setters | Preparing shared configuration for multiple HTTP requests |
| `HttpClient` | `clientBuilder.build()` or `HttpClient.newHttpClient()` | **Cannot modify client configuration via the old builder** | Sending multiple synchronous/asynchronous requests, sharing resources |
| `HttpRequest.Builder` | `HttpRequest.newBuilder(uri)`, `newBuilder()`, or copied from a request | **Yes**, via setters | Creating one or more request configurations |
| `HttpRequest` | `requestBuilder.build()` | **No setters to modify a built request** | Passing to `HttpClient.send` / `sendAsync` |

`HttpClient.newHttpClient()` is a quick way to create a client with default settings. When you need timeouts, redirects, a TLS context, a proxy, or a version preference, use a builder.

`HttpRequest.newBuilder(URI)` creates a request builder that already has a URI. `HttpRequest.newBuilder()` requires setting `uri(...)` before `build()`; without a URI, `build()` can throw `IllegalStateException`.

**Watch the names:** `HttpClient.Builder` and `HttpRequest.Builder` are two **different** interfaces. Even though both have `build()`, the client builder does not have `uri(...)`/`GET()`, and the request builder does not have `followRedirects(...)`/`connectTimeout(...)`.

## 3. Mutable Builder: Setters Mutate the Current State

Client builder example:

~~~java
HttpClient.Builder cb = HttpClient.newBuilder()
    .connectTimeout(Duration.ofSeconds(2))
    .followRedirects(HttpClient.Redirect.NEVER)
    .version(HttpClient.Version.HTTP_1_1);

HttpClient client1 = cb.build();

cb.connectTimeout(Duration.ofSeconds(5))
  .followRedirects(HttpClient.Redirect.ALWAYS)
  .version(HttpClient.Version.HTTP_2);

HttpClient client2 = cb.build();
~~~

This snippet requires importing `java.net.http.HttpClient` and `java.time.Duration`. Each configuration call mutates `cb`; the sequence above creates two clients with different values.

- `client1.connectTimeout().orElseThrow()` is still 2 seconds.
- `client1.followRedirects()` is still `NEVER`.
- `client1.version()` is still `HTTP_1_1`.
- `client2` receives 5 seconds, `ALWAYS`, and preferred `HTTP_2`.

**Do not say `client2` is guaranteed to communicate over HTTP/2.** `HttpClient.version()` describes the preferred/configured version; the actual protocol may depend on the server, TLS/ALPN, proxies, and negotiation capabilities. Check `HttpResponse.version()` after receiving the response.

### Which Objects Should Change, and Which Should Be Reused?

- To change the timeout/redirect policy of **a built client**: create **another client** from a builder.
- To change the URI/headers of **a built request**: create **another request** from a builder or copy an existing request.
- To send requests to multiple URLs with the same HTTP/TLS policy: **reuse one `HttpClient`** and create multiple `HttpRequest` instances.
- Do not create a `new HttpClient` for **every** request just because you need a different URI; URI configuration belongs to the request, not the client.

The Java 17 documentation explicitly states that a built `HttpClient` is immutable and can be used to send multiple requests; the client also provides **resource sharing** across sends, such as HTTP/network resources that the implementation can reuse. Do not infer that reuse **always** creates exactly one TCP connection, because connection pooling/negotiation and server policy are implementation details.

## 4. `HttpRequest.Builder`: Per-Request State

A request can include a URI, method, headers, body publisher, timeout, and version preference:

~~~java
HttpRequest.Builder rb = HttpRequest.newBuilder(
        URI.create("https://api.example.org/items"))
    .timeout(Duration.ofSeconds(4))
    .header("Accept", "application/json")
    .GET();

HttpRequest request = rb.build();
~~~

This snippet requires importing `java.net.URI`, `java.net.http.HttpRequest`, and `java.time.Duration`. The built `request` does not change automatically when `rb` is modified.

Common operations on a request builder:

| API | Mutates Builder State | Key Points to Remember |
|---|---|---|
| `uri(URI)` | Replaces the target URI | Use a URI with an appropriate `http` or `https` scheme |
| `GET()` | Sets the method to GET | Default is already GET if no other method is set |
| `POST(BodyPublisher)` | Sets POST and body publisher | The body is a data-publishing object, not an automatic String field |
| `PUT(BodyPublisher)` | Sets PUT and body publisher | Choose the right API semantics |
| `DELETE()` | Sets DELETE | Does not automatically turn another built request into DELETE |
| `method("PATCH", publisher)` | Sets a custom method and publisher | Verify the server/API supports the method |
| `header(name, value)` | **Adds** a header value | Can create multiple values for the same header |
| `setHeader(name, value)` | **Replaces** previous values of that header | Use when you want to ensure only the new value is present |
| `headers(name1, value1, ...)` | Adds multiple header pairs | Number of arguments must be even and valid |
| `timeout(Duration)` | Sets the request timeout | Different from the client connect timeout |
| `version(HttpClient.Version)` | Sets the request's own preferred version | The actual response may use a different version |
| `expectContinue(boolean)` | Requests `100 Continue` mechanism when appropriate | Not all servers/proxies handle this identically |
| `build()` | Returns a new `HttpRequest` | The builder remains usable afterward |
| `copy()` | Returns a new builder with the same current state | Available only on **`HttpRequest.Builder`** in Java 17 |

### Difference Between `header` and `setHeader`

Example:

~~~java
HttpRequest.Builder b = HttpRequest.newBuilder(
    URI.create("https://example.org"))
    .header("X-Tag", "one")
    .header("X-Tag", "two");

HttpRequest r1 = b.build();             // X-Tag has 2 values.

b.setHeader("X-Tag", "final");
HttpRequest r2 = b.build();             // X-Tag now has only "final".
~~~

This snippet requires importing `java.net.URI` and `java.net.http.HttpRequest`. `r1.headers().allValues("X-Tag")` has two values; `r2` has one. Although HTTP header names are case-insensitive, you should still use `HttpHeaders.firstValue`/`allValues` rather than comparing names manually or parsing header lines.

Not every header can be set with `HttpRequest.Builder.header`: the JDK HTTP client may reject certain **restricted** names or values (for example, `Content-Length`, which is determined by the body publisher), or control them via dedicated APIs. When encountering `IllegalArgumentException`, do not bypass the check by assembling raw HTTP strings manually.

### `GET()`, `POST()`, and Body Publishers

`HttpRequest.Builder.GET()` is used for standard GET requests and is the default when no method has been chosen. `POST(publisher)` sets the body publisher; some methods have `noBody()` when no body is needed.

~~~java
HttpRequest post = HttpRequest.newBuilder(
    URI.create("https://api.example.org/items"))
    .header("Content-Type", "application/json")
    .POST(HttpRequest.BodyPublishers.ofString(
        "{\"name\":\"Java\"}", StandardCharsets.UTF_8))
    .build();
~~~

The snippet above requires importing `java.net.URI`, `java.net.http.HttpRequest`, and `java.nio.charset.StandardCharsets`. The API accepts a `BodyPublisher` to send bytes; `String.length()` must not be used to manually populate `Content-Length`.

**Merely changing the method on a builder does not guarantee business-level safety.** Resending a `POST` request can create additional resources. Even though `HttpRequest` is immutable and allowed to be sent multiple times, **retrying** depends on idempotency, authentication, API semantics, and whether the body can be replayed.

## 5. Runnable Example: Mutating Two Builders While Old Objects Stay Unchanged

The following Java 17 program uses `com.sun.net.httpserver.HttpServer` on `127.0.0.1` together with `java.net.http.HttpClient`. It makes no Internet calls and requires no credentials. The program creates two clients from **one mutated client builder**, then creates three requests through **one request builder** and a `copy()`. Afterward, it sends the three requests to the local HTTP server to verify the values on the wire.

Save the complete file **`BuilderSnapshotDemo.java`**:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public class BuilderSnapshotDemo {
    private static void handle(HttpExchange ex) throws IOException {
        String stage = ex.getRequestHeaders().getFirst("X-Stage");
        String data = ex.getRequestMethod() + " "
            + ex.getRequestURI().getRawPath()
            + " | stage=" + stage;
        byte[] bytes = data.getBytes(StandardCharsets.UTF_8);
        ex.getResponseHeaders().set("Content-Type",
                                    "text/plain; charset=utf-8");
        ex.sendResponseHeaders(200, bytes.length);
        try (var body = ex.getResponseBody()) {
            body.write(bytes);
        }
    }

    public static void main(String[] args) throws Exception {
        HttpClient.Builder clientBuilder = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(2))
            .followRedirects(HttpClient.Redirect.NEVER)
            .version(HttpClient.Version.HTTP_1_1);

        HttpClient firstClient = clientBuilder.build();

        clientBuilder.connectTimeout(Duration.ofSeconds(5))
            .followRedirects(HttpClient.Redirect.ALWAYS)
            .version(HttpClient.Version.HTTP_2);
        HttpClient secondClient = clientBuilder.build();

        System.out.println("client1: "
            + firstClient.connectTimeout().orElseThrow().toSeconds()
            + "s, " + firstClient.followRedirects()
            + ", " + firstClient.version());
        System.out.println("client2: "
            + secondClient.connectTimeout().orElseThrow().toSeconds()
            + "s, " + secondClient.followRedirects()
            + ", " + secondClient.version());

        HttpServer server = HttpServer.create(
            new InetSocketAddress(InetAddress.getByName("127.0.0.1"), 0), 0);
        server.createContext("/", BuilderSnapshotDemo::handle);
        server.start();
        try {
            URI base = URI.create(
                "http://127.0.0.1:" + server.getAddress().getPort());
            HttpRequest.Builder requestBuilder = HttpRequest.newBuilder(
                    base.resolve("/first"))
                .setHeader("X-Stage", "alpha")
                .header("X-Tag", "one")
                .GET();

            HttpRequest firstRequest = requestBuilder.build();

            requestBuilder.uri(base.resolve("/second"))
                .setHeader("X-Stage", "beta")
                .header("X-Tag", "two");
            HttpRequest secondRequest = requestBuilder.build();

            HttpRequest.Builder fork = requestBuilder.copy();
            HttpRequest copiedRequest = fork
                .uri(base.resolve("/copy"))
                .setHeader("X-Stage", "gamma")
                .build();

            System.out.println("request1: "
                + firstRequest.uri().getRawPath()
                + " | " + firstRequest.headers()
                    .firstValue("X-Stage").orElse("")
                + " | tags=" + firstRequest.headers()
                    .allValues("X-Tag").size());
            System.out.println("request2: "
                + secondRequest.uri().getRawPath()
                + " | " + secondRequest.headers()
                    .firstValue("X-Stage").orElse("")
                + " | tags=" + secondRequest.headers()
                    .allValues("X-Tag").size());
            System.out.println("request3: "
                + copiedRequest.uri().getRawPath()
                + " | " + copiedRequest.headers()
                    .firstValue("X-Stage").orElse("")
                + " | tags=" + copiedRequest.headers()
                    .allValues("X-Tag").size());

            System.out.println("response1: "
                + firstClient.send(firstRequest,
                    HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8)).body());
            System.out.println("response2: "
                + firstClient.send(secondRequest,
                    HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8)).body());
            System.out.println("response3: "
                + firstClient.send(copiedRequest,
                    HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8)).body());
        } finally {
            server.stop(0);
        }
    }
}
~~~

### How to Compile and Run

Requires **JDK 17+** with the standard modules `java.net.http` and `jdk.httpserver`:

~~~bash
javac -encoding UTF-8 BuilderSnapshotDemo.java
java BuilderSnapshotDemo
~~~

Verified stdout:

~~~text
client1: 2s, NEVER, HTTP_1_1
client2: 5s, ALWAYS, HTTP_2
request1: /first | alpha | tags=1
request2: /second | beta | tags=2
request3: /copy | gamma | tags=2
response1: GET /first | stage=alpha
response2: GET /second | stage=beta
response3: GET /copy | stage=gamma
~~~

These lines only show the key values of the demo; the actual port is chosen by the OS via port `0` and **does not appear in stdout**. All three requests are sent using `firstClient` to keep the same client configuration. `secondClient` is created to observe a different snapshot; HTTP/2 is not sent to the demo server, which is HTTP/1.1.

### Step-by-Step Output Explanation

1. `client1` is built when connect timeout = 2s, redirects = `NEVER`, and preferred version = `HTTP_1_1`.
2. Next, **the same client builder** is modified to 5s, `ALWAYS`, and `HTTP_2`, and `client2` is built.
3. `client1` still prints its initial values. If an older client "automatically followed the builder", the output would be wrong — but that does not happen.
4. `firstRequest` is built with `/first`, `X-Stage: alpha`, and one `X-Tag`.
5. **The request builder** is modified to `/second`, replacing `X-Stage` with `beta` and **adding** `X-Tag: two`; `secondRequest` receives two X-Tag values, while `firstRequest` still has only one.
6. `requestBuilder.copy()` creates a new builder from the `/second` state, and the `fork` branch sets `/copy` and `gamma`. `copiedRequest` carries the new branch's state without altering the already built `secondRequest`.
7. The HTTP server receives the exact paths and `X-Stage` values as each built request; there are no silent changes from later builder mutations.
8. Calling `firstClient.send(...)` multiple times on the same client demonstrates **client reuse**. Do not call `clientBuilder.build()` again for every request.

**Note:** `HttpClient.version()` in stdout is the **preferred** version; no HTTP/2 request was sent by `secondClient`, so you cannot use that output to conclude that the server supports HTTP/2.

## 6. How Precise Is the Snapshot and "Immutability" Boundary?

The statement **"HttpClient and HttpRequest are immutable"** is accurate according to the Java 17 documentation at the level of **public configuration after `build()`**. However, you should separate three layers of state:

1. **Builder state**: mutable; each setter modifies the builder's configuration.
2. **Built configuration**: URI, method, headers, request timeout, preferred version, or client connect timeout/redirect policy **cannot be modified by changing the old builder**.
3. **External/runtime state**: sockets, connection pools, cookie stores, authenticators, proxy selectors, custom body publishers, files, or mutable application objects can change over time. `build()` **is not a deep-copy of the entire world**.

An intuitive example:

~~~java
HttpRequest request = HttpRequest.newBuilder(
    URI.create("https://example.org/items"))
    .setHeader("X-Trace", "v1")
    .GET()
    .build();

// There is no request.setHeader("X-Trace", "v2").
// Create another HttpRequest when you want to change headers.
~~~

This snippet requires importing `java.net.URI` and `java.net.http.HttpRequest`. The absence of public setters on `HttpRequest` reflects that its configuration is frozen.

**Yet the client is still active:** an `HttpClient` can open/close TCP connections, maintain HTTP/2 support state, exchange cookies through a configured `CookieHandler`, run asynchronous tasks, and receive multiple responses. That is neither "builder mutation" nor a contradiction of configuration immutability.

**Dependent objects can be stateful:** if you provide a `CookieHandler`, `Authenticator`, `ProxySelector`, `Executor`, or custom `BodyPublisher`, they can carry their own state. Do not infer that every emitted byte or every cookie stays fixed forever after `build()`. Configuration referencing external components and how those components behave at runtime are separate layers of responsibility.

An example of snapshot limits is a request body created from a file or a supplier stream. `HttpRequest` holds a `BodyPublisher`, but the published content may depend on the data source at send time. Modifying the file after `build()` must not be relied upon as a guarantee that "the request will always send the exact same bytes," because it depends on the specific publisher type and when the data is read.

## 7. Two Ways to Create a New Request from an Existing Template

### Approach A: `HttpRequest.Builder.copy()`

The Java 17 documentation states that `copy()` returns a **new** builder with state equivalent to the current builder; afterward, each builder can be modified independently.

~~~java
HttpRequest.Builder template = HttpRequest.newBuilder(
    URI.create("https://api.example.org/v1"))
    .setHeader("Accept", "application/json")
    .timeout(Duration.ofSeconds(3));

HttpRequest.Builder branchA = template.copy()
    .uri(URI.create("https://api.example.org/v1/a"));
HttpRequest.Builder branchB = template.copy()
    .uri(URI.create("https://api.example.org/v1/b"));

HttpRequest a = branchA.build();
HttpRequest b = branchB.build();
~~~

This snippet requires importing `java.net.URI`, `java.time.Duration`, and `java.net.http.HttpRequest`. `copy()` avoids mutating a shared builder across two lines of work, but it **must not be understood as deep-cloning every referenced object**, especially a `BodyPublisher` with external state.

### Approach B: `HttpRequest.newBuilder(request, headerFilter)`

Starting from **a built request**, Java 17 lets you create a builder based on that request and **filter headers** while copying:

~~~java
HttpRequest next = HttpRequest.newBuilder(
        previous,
        (name, value) -> !name.equalsIgnoreCase("Authorization"))
    .uri(URI.create("https://api.example.org/other"))
    .build();
~~~

This snippet assumes `previous` is a built `HttpRequest` and imports `java.net.URI` and `java.net.http.HttpRequest`. The filter receives the name and value of **each header pair**. The example above drops `Authorization` when creating another request, avoiding accidental reuse of a bearer token on the wrong resource.

**Do not assume this filter scrubs all credentials:** cookies may be managed by the client's `CookieHandler`, authentication may come from an `Authenticator`, the URL may contain sensitive information, and other headers may also need review. When redirecting from one host to another, design your client/credential scope and redirect policy rather than relying solely on a header filter.

### Which Approach Should You Use?

| Situation | Reasonable Approach |
|---|---|
| You have an unbuilt template request config and need multiple variants | `template.copy()` per variant |
| You have a built request and need to change URI/headers/timeout | `HttpRequest.newBuilder(existing, filter)` then build a new request |
| Creating a brand-new simple request | `HttpRequest.newBuilder(uri)` directly |
| Multiple threads creating independent requests | Each thread keeps its own builder or an appropriate copy |
| Need to keep shared client configuration | Reuse **one `HttpClient`**, do not rebuild a client per request |

## 8. Thread Safety: A Builder Is Not Like a Client

According to Java SE 17, setters on **`HttpClient.Builder` and `HttpRequest.Builder` are not designed to be thread-safe**. Do not share a single builder instance across multiple threads calling `uri`, `setHeader`, `POST`, and `build` without proper synchronization.

An incorrect example that easily causes "mixed requests":

~~~java
// A shared HttpRequest.Builder is used by both thread A and thread B.
sharedBuilder.uri(uriA).setHeader("X-User", "alice");
sharedBuilder.uri(uriB).setHeader("X-User", "bob");
// Thread A calls build() at an indeterminate time.
HttpRequest requestA = sharedBuilder.build();
~~~

This is code illustrating a race, not a standalone program. `requestA` may end up with B's URI/header or an unintended state. Only use `synchronized` if you genuinely need to share a builder, though a better structure is usually **each request owning its own builder**.

Correct example:

~~~java
HttpClient client = HttpClient.newBuilder()
    .connectTimeout(Duration.ofSeconds(2))
    .build();

// Across different tasks/threads:
HttpRequest req = HttpRequest.newBuilder(targetUri)
    .setHeader("Accept", "application/json")
    .GET()
    .build();

HttpResponse<String> res = client.send(
    req, HttpResponse.BodyHandlers.ofString());
~~~

This snippet requires importing `java.net.http.*` and `java.time.Duration`, and assumes `targetUri` is valid and `res` is handled afterward. Threads can share the built `client` to send requests while each request has its own builder. If the application uses a custom `CookieHandler`/`BodyPublisher`/`Executor`, those components must also have thread-safety appropriate for concurrent use.

**A built `HttpRequest` can also be sent multiple times**, but do not equate "can be sent" with "always makes sense to resend." Read-only `GET` is generally more suitable than a transaction-creating `POST`; input-stream/file/custom publishers may not replay bytes as intended. For requests with side effects, design a dedicated idempotency/retry policy.

## 9. Timeout, Version, Redirect: Configure at the Right Layer

| Policy | Configuration Layer | Meaning |
|---|---|---|
| `connectTimeout(Duration)` | `HttpClient.Builder` | Deadline for establishing **a new connection**, not a timeout for every request and not applied to reused connections |
| `followRedirects(Redirect)` | `HttpClient.Builder` | Whether to follow HTTP redirects automatically, per `NEVER`/`NORMAL`/`ALWAYS` policy |
| `version(Version)` | Client or Request builder | Preferred HTTP version; does not guarantee the server/response will use it |
| `proxy(ProxySelector)` | `HttpClient.Builder` | Client proxy policy |
| `sslContext(SSLContext)` | `HttpClient.Builder` | TLS trust/key context for HTTPS connections |
| `executor(Executor)` | `HttpClient.Builder` | Executor for async/dependent work in the implementation |
| `timeout(Duration)` | `HttpRequest.Builder` | Per-request timeout if the response does not arrive within the deadline |
| `uri(URI)` | `HttpRequest.Builder` | Target endpoint of a single request |
| `header/setHeader` | `HttpRequest.Builder` | Request-specific metadata |
| `POST(BodyPublisher)` | `HttpRequest.Builder` | Request-specific method + body publisher |

**Client connect timeout and request timeout are different.** If the server connects quickly but takes a long time to process the request, `connectTimeout` may not help. Use an appropriate request timeout to bound response waiting, and manage cancellation/state when using `sendAsync`.

Setting a request version different from the client's:

~~~java
HttpRequest req = HttpRequest.newBuilder(target)
    .version(HttpClient.Version.HTTP_1_1)
    .GET()
    .build();

// After send, check response.version(); do not guess from req.
~~~

This snippet requires importing `java.net.http.HttpRequest` and `java.net.http.HttpClient`, and assumes `target` is a valid URI.

**Redirect is a security policy:** `Redirect.ALWAYS` has different semantics from `NORMAL`/`NEVER`. In Java 17, `NORMAL` does not automatically follow redirects from HTTPS to HTTP, whereas `ALWAYS` allows following redirects regardless of protocol. When handling tokens/cookies or user-supplied URLs, carefully evaluate downgrade, host-switching, and SSRF risks; do not pick `ALWAYS` just because you want "every request to succeed."

## 10. BodyPublisher: The Request Is Immutable, but Emitted Data Can Have Its Own Lifecycle

A built `HttpRequest` stores information about its `BodyPublisher`, not necessarily an immutable copy of **every byte** that will be sent.

Some common publishers:
- `HttpRequest.BodyPublishers.noBody()`: no body content.
- `ofString(text, UTF_8)`: prepares to publish string content.
- `ofByteArray(byte[])`: publishes bytes from an array via the publisher API; check the copying/repeatability contract of the specific publisher type.
- `ofFile(path)`: file-backed data is read when published; the file could change or be deleted over time.
- `ofInputStream(supplier)`: produces data from a `Supplier<InputStream>`; the source must be designed to supply a fresh stream if resending is needed.

**Replay note:** a custom `BodyPublisher` reading directly from an already consumed stream may not emit the same bytes if the request is sent twice or retried by the client. The fact that the API allows reusing `HttpRequest` does not mean every publisher, file, or external system is "frozen" and perfectly reproducible.

Example of creating a body appropriately when sending from explicit in-memory data:

~~~java
byte[] payload = "{\"name\":\"Java\"}"
    .getBytes(StandardCharsets.UTF_8);

HttpRequest request = HttpRequest.newBuilder(target)
    .setHeader("Content-Type", "application/json")
    .POST(HttpRequest.BodyPublishers.ofByteArray(payload))
    .build();
~~~

This snippet requires importing `java.net.http.HttpRequest` and `java.nio.charset.StandardCharsets`; `target` must be a URI. When your logic requires **repeatable** bytes, prepare application-immutable content and choose an appropriate publisher. Avoid accidental duplicate `POST` sends when there is a risk of creating duplicate orders or payments.

### Immutable Does Not Mean Deep-Freezing All Dependencies

If you supply a `CookieManager` to the client builder:
- The configuration **attaching the `CookieHandler` to the client** was chosen at build time.
- **The cookie store** can be updated by HTTP responses or by other code, affecting future requests.
- This is not the builder mutating the client; it is state mutation **of the referenced `CookieHandler`**.

Similarly, a stateful `Authenticator` or custom proxy selector can determine runtime behavior; you must manage sharing scope, concurrency, and security.

## 11. Client Lifecycle in Java 17

An `HttpClient` can be used to send multiple requests, and using one long-lived client is generally more sensible than creating a stream of new clients. The goal is to avoid unnecessary overhead and fragmentation of HTTP/network resources caused by building a new client for every operation.

**Pay attention to JDK version:** in **Java 17**, the `HttpClient` API does not yet provide `close()`/`AutoCloseable` like newer JDK versions. Therefore, do not write:

~~~java
// Does not compile with the Java 17 HttpClient API:
try (HttpClient client = HttpClient.newHttpClient()) {
    // ...
}
~~~

This is an **intentional version-error example**, not runnable code in Java 17. When studying Java 21+ documentation that introduces new lifecycle methods, verify the exact target API version instead of copying them into JDK 17 source code.

In a long-running application, manage the **number of `HttpClient` instances**, custom thread pools, connection-level settings, timeouts, and application-wide shutdown. If you supply a custom `Executor` to the client, its lifecycle is controlled by the application. Do not discard client references in a loop as a "close socket" strategy that does not exist in the Java 17 API.

### Client Configuration ≠ Request State ≠ Response State

A client configures timeouts/redirects/version, whereas `send`/`sendAsync` returns a **response** containing:
- `statusCode()` and `headers()` of the response,
- `body()` according to the chosen `BodyHandler`,
- `version()` — the actual protocol version used for the response,
- `uri()` — the final URI corresponding to the response (which may differ from the initial URI after redirects).

These properties are **runtime results**, not "fixed" merely because client configuration is immutable. The body can be a `String`, `byte[]`, `InputStream`, file path, or a subscriber type defined by the handler; each choice has different resource-management implications.

## 12. Common Mistakes

| Mistake | Why It Is Wrong | How to Fix |
|---|---|---|
| "Once `build()` is called, the builder is locked." | The builder remains mutable and can still build more objects | Distinguish the builder from the built object |
| "Modifying the builder automatically updates the old client." | `HttpClient` has immutable configuration after `build()` | Build a new client if you want to change policy |
| "Modifying the builder automatically updates the old request." | `HttpRequest` is immutable | Build a new request or clone via a builder |
| "`HttpClient.Builder` and `HttpRequest.Builder` are the same." | Client setters/policies differ from request URI/body | Configure each setting at the right layer |
| "`header` replaces the previous header." | `header` **adds** a value | Use `setHeader` when you want to replace |
| "`copy()` returns an immutable `HttpRequest`." | `copy()` returns a **new builder** | Call `copy().build()` |
| "`HttpClient.Builder.copy()` exists in Java 17." | This API is not exposed on the JDK 17 client builder | Create a new client builder and apply configuration explicitly |
| "Sharing one request builder across unsynchronized threads." | Builder setters are not thread-safe | Use a separate builder per thread/request |
| "An immutable client means `CookieHandler` never changes." | Runtime dependencies carry their own state | Manage mutable dependencies explicitly |
| "An immutable request means the emitted body is always identical." | Publishers/files/streams have their own lifecycle | Check repeatability; retry only when safe |
| "Creating one `HttpClient` per request is required." | A client can send many requests and share resources | Reuse clients by trust/config scope |
| "`connectTimeout` applies to every `send`." | It only applies to establishing a new connection | Add an appropriate per-request timeout |
| "`version(HTTP_2)` forces the server to use HTTP/2." | It is only a preferred version | Read `HttpResponse.version()` |
| "`Redirect.ALWAYS` is always safe." | Can follow unintended redirects, including downgrades | Choose policy carefully and verify trust boundaries |
| "`HttpClient` in Java 17 is definitely `AutoCloseable`." | Lifecycle API differs from Java 21+ | Check the right JDK docs and manage client count |
| "Resending the same `POST` request object guarantees no duplicate transaction." | Immutability does not create idempotency | Use an idempotency key + server contract |

## 13. Practical Design Checklist

Before introducing `HttpClient` into a Java service, ask:

1. **Client scope:** Do requests share proxy, TLS trust, redirect, cookie policy, and connection timeout? If they match, build and **reuse** one client.
2. **Request scope:** Does each request have its own URI, method, headers, payload, and timeout? Use `HttpRequest.newBuilder` or `copy` each time.
3. **Concurrency:** Can any threads call setters on the same builder simultaneously? If so, redesign so mutable builders are not shared; ensure mutable dependencies are thread-safe.
4. **Timeout:** Are both connect timeout and per-request timeout configured appropriately? When sending asynchronously, is there a cancellation/exception-handling plan?
5. **Body publisher:** Is the data of appropriate size/format, are any streams single-read, and does it need to be replayed on retry/redirect?
6. **HTTP semantics:** Are POST/PUT/PATCH/DELETE idempotent per the contract; is an idempotency key needed to prevent duplicate submissions?
7. **Identity/security:** Does HTTPS have proper truststore/hostname validation? Could the redirect policy accidentally switch hosts, send credentials to the wrong place, or downgrade?
8. **Observability:** Are actual status/latency/version measured; do logs redact `Authorization`, cookies, and queries containing secrets?
9. **Lifecycle:** Are unnecessary clients or executors being created? Which lifecycle APIs exist in your runtime JDK version?
10. **Testing:** Build two clients from one modified builder; build multiple requests from one builder/`copy`; assert old data stays unchanged; test responses on loopback.

## 14. Self-Check Exercises

1. An `HttpClient.Builder` is configured with a 2-second connect timeout and builds `c1`; then it is changed to 5 seconds and builds `c2`. What is `c1.connectTimeout()`? Why?
2. `requestBuilder.header("X-Tag", "a").header("X-Tag", "b")` and then `build()`. How many values does that header have? Which API must be used if you want only `"c"`?
3. After `HttpRequest request = rb.build()`, does `rb.uri(newUri)` change `request.uri()`?
4. Does `requestBuilder.copy()` return an `HttpRequest` or an `HttpRequest.Builder`? If you modify the copy, does the original builder change?
5. Give a scenario for using `HttpRequest.newBuilder(previous, filter)` instead of a brand-new builder.
6. Why should you not share one `HttpRequest.Builder` across multiple threads changing URI/headers and calling `build()` concurrently?
7. `HttpClient` is immutable, yet the application uses a `CookieHandler` that stores session cookies. Does updating cookies contradict client immutability?
8. An `HttpRequest` holds a `BodyPublisher` that reads a file, and the file changes before a later send. Is "request immutability" enough to guarantee the emitted bytes do not change?
9. Why does `HttpClient.version() == HTTP_2` not prove the response used HTTP/2?
10. `connectTimeout` is set to 2 seconds; the server accepts TCP immediately but takes 1 minute to process. Which timeout is more meaningful at the request level?
11. A built `POST` is passed to `send` twice. Does that automatically guarantee the backend creates only one resource?
12. Why should you not unconditionally set `followRedirects(ALWAYS)` on a client that carries credentials or handles user-supplied destinations?
13. On Java 17, is `try (HttpClient c = HttpClient.newHttpClient())` valid for the API version?
14. Write a snippet creating a template request with an `Accept` header and a 3-second timeout, then create two different URI variants without mutating the same builder concurrently.
15. In the runnable example, why does `request1` still have one `X-Tag` even though `X-Tag: two` is later added to the request builder?

**Short answers:** (1) 2 seconds, snapshot at build time; (2) two, use `setHeader("X-Tag","c")`; (3) no; (4) a new builder, can be modified independently; (5) when you want to keep part of a built request and filter/edit headers; (6) data race; (7) no, the cookie store is a stateful dependency; (8) no; (9) only preferred config, check `HttpResponse.version()`; (10) `HttpRequest.Builder.timeout`; (11) no, idempotency is separate; (12) redirect/downgrade risk and credential scope; (13) no on Java 17; (14) use `copy()` or a new builder per branch; (15) a built request does not change with the builder.

## 15. Summary

- **Mutable builders:** setters mutate the builder itself; `build()` creates a new object and **does not lock** the builder against further use.
- **`HttpClient` is immutable in configuration:** build once for a shared policy and **reuse** across many requests; to change timeout/redirect/proxy/TLS, create a new client.
- **`HttpRequest` is immutable in metadata:** built URI/method/headers/timeouts do not change; for variants, use a new builder, `copy()`, or `newBuilder(existing, filter)`.
- **Thread safety:** builders are not thread-safe; separate builders by request/thread instead of mutating together; a built client can be shared to send concurrent requests within the right scope.
- **Do not overstate immutability:** connection pools, `CookieHandler`, custom `BodyPublisher`, and file/stream data have their own lifecycles; retries also depend on HTTP semantics.
- **Check version and timeout at the right layer:** client `connectTimeout` differs from request `timeout`; client/request version is a preference, while response `version()` reflects the actual protocol.
- **Java 17 compatibility:** core `java.net.http` APIs exist since Java 11; do not mechanically copy newer lifecycle APIs into Java 17 source code.

### References

- [Oracle Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html)
- [Oracle Java SE 17 — HttpClient.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Builder.html)
- [Oracle Java SE 17 — HttpRequest](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.html)
- [Oracle Java SE 17 — HttpRequest.Builder, copy, header/setHeader](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html)
- [Oracle Java SE 17 — HttpRequest.BodyPublishers](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublishers.html)
- [Oracle Java SE 17 — HttpResponse](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.html)
- [Oracle Java SE 17 — HttpServer for local tests](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html)
