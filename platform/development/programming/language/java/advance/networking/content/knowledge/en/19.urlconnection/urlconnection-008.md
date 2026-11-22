# ResponseCache, CookieHandler, and Process-Wide Shared Configurations in URLConnection (Java 17+)

In Java Networking, `java.net.URLConnection` and its subclass `HttpURLConnection` provide legacy APIs that still appear in many systems for opening URLs, sending HTTP requests, and reading responses. A notable characteristic of this API group is that, in addition to properties **belonging to each individual URLConnection object**, the JDK also has several **JVM process-wide default handlers**. For example, `ResponseCache.setDefault(...)` registers a shared cache hook, and `CookieHandler.setDefault(...)` registers a shared cookie handler. These default settings can affect **multiple libraries and multiple parts of the same application**, including places that do not directly call the configuration methods.

This lesson focuses on:

1. **`ResponseCache`**: callbacks for checking cache hit/miss and writing responses; the roles of `CacheResponse`, `CacheRequest`, and `URLConnection.setUseCaches(...)`.
2. **`CookieHandler` / `CookieManager`**: policies for storing/sending HTTP cookies, `CookieStore`, and session scope; differences from `HttpClient.Builder.cookieHandler(...)`.
3. **JVM-wide defaults**: `ProxySelector`, `Authenticator`, `URLConnection`/`HttpURLConnection` flags, redirect behavior, and one-time factory APIs; when defaults are captured and how to configure per connection.
4. **Limits and safety**: not sharing cookies/sessions across multiple users, not mistakenly storing private responses in a shared cache, and not mutating static defaults while requests are in flight.
5. **Java 17+ hands-on**: three standalone classes, two using a loopback HTTP server to verify caching/cookies and one creating only URLConnection objects, **without making network connections**.

**Key takeaway:** `setDefault(...)` is a **shared setting**, not a property of the current request. `setUseCaches(...)` is a **per-URLConnection control**, whereas the modern `HttpClient` has a different builder and behavior; do not lump all Java HTTP APIs into one unified configuration system when the Javadoc makes no such promise.

## 1. What states does URLConnection have?

A typical lifecycle:

~~~text
URL url = ...
      |
      v
URLConnection conn = url.openConnection()
      |               -> creates object, copies some defaults into the object
      |
      +--> conn.setUseCaches(...)
      +--> conn.setConnectTimeout(...)
      +--> conn.setReadTimeout(...)
      +--> conn.setRequestProperty(...)
      |
      v
conn.connect() or getInputStream()/getHeaderFields()
      |
      +--> protocol handler may query ResponseCache.get(...)
      +--> HTTP handler may query CookieHandler.get(...)
      |
      v
HTTP response
      |
      +--> CookieHandler.put(...) with response headers
      +--> ResponseCache.put(...) + CacheRequest.getBody()
      |    (if caching is allowed and the implementation supports it)
      |
      v
Read body until EOF, close stream, disconnect when needed
~~~

**Note:** the diagram illustrates callbacks at a conceptual level, not a mandatory internal order across all protocol handlers. A custom handler or a different HTTP API may not use these callbacks. Calling `openConnection()` **only creates a URLConnection object** and does not necessarily open a TCP connection; the first I/O operation triggers the actual connection.

### 1.1. Per-connection vs. process-wide

| API | Scope | Remember |
| --- | --- | --- |
| `conn.setUseCaches(false)` | Single `URLConnection` | Set before the connection is connected |
| `conn.setConnectTimeout(3000)` | Single `URLConnection` | Connect timeout, in milliseconds |
| `conn.setReadTimeout(3000)` | Single `URLConnection` | Read wait timeout, not a total deadline |
| `conn.setRequestProperty("Accept", ...)` | Single connection/request | Do not modify after already connected |
| `http.setInstanceFollowRedirects(false)` | Single `HttpURLConnection` | Overrides the global redirect default |
| `ResponseCache.setDefault(cache)` | JVM-wide (default ResponseCache) | Eligible URL protocol handlers may share the same cache |
| `CookieHandler.setDefault(handler)` | JVM-wide (default CookieHandler) | Eligible HTTP URL handlers may share the same cookie store |
| `ProxySelector.setDefault(selector)` | JVM-wide (default proxy selector) | Shared route configuration, overridable via supporting APIs |
| `Authenticator.setDefault(authenticator)` | JVM-wide (default authenticator) | Risk of using credentials out of scope if poorly designed |
| `URLConnection.setDefaultUseCaches("http",false)` | Static default for the HTTP protocol | Affects connections created afterward |
| `HttpURLConnection.setFollowRedirects(false)` | Static redirect default | New connections inherit the default; can be overridden per instance |

A single **JVM** may run multiple tenants, plugins, modules, concurrent threads, and multiple HTTP clients. If module A calls `CookieHandler.setDefault(tenantACookies)`, module B running URLConnection may unintentionally use A's cookie policy. That is **shared mutable global state**, not safe dependency injection.

## 2. ResponseCache: designing caching through the protocol handler

### 2.1. Role and lifecycle

According to the [Java 17 ResponseCache Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ResponseCache.html), `ResponseCache` is the abstract class for cache implementations of `URLConnection`. When registered:

~~~java
ResponseCache previous = ResponseCache.getDefault();
ResponseCache.setDefault(myCache);
try {
    // Eligible HTTP URLConnections are allowed to use the cache.
} finally {
    ResponseCache.setDefault(previous);
}
~~~

This is a **non-standalone illustrative snippet** because `myCache` has not been declared. `getDefault()` returns the shared cache or `null`, and `setDefault(null)` unregisters the global cache. **Non-standard URL protocol handlers may ignore ResponseCache**, and registering the hook does not automatically turn `java.net.http.HttpClient` into a caching client.

Two main callbacks:

~~~java
abstract CacheResponse get(
        URI uri,
        String requestMethod,
        Map<String, List<String>> requestHeaders)
        throws IOException;

abstract CacheRequest put(
        URI uri, URLConnection connection)
        throws IOException;
~~~

- `get(...)`: asks whether the request can be served from the cache. **Returns `CacheResponse`** if a matching entry exists, or **`null`** so the protocol handler takes the normal network path. `get` is called with the URI, method, and request headers; a safe cache **cannot look only at the URL** if the response depends on request headers, credentials, language, Accept-Encoding, or cookies.
- `put(...)`: after the handler fetches the response from the origin, asks whether the cache wants to store it. **Returns `CacheRequest`** to receive the response bytes or `null` if not storing. A cache implementation must decide eligibility based on method, status, Cache-Control, authorization, cookies, Vary, expiry, and policy.
- `CacheResponse.getHeaders()` and `CacheResponse.getBody()`: provide the metadata and input stream of a cache hit.
- `CacheRequest.getBody()`: output stream for the protocol handler to write response bytes for the cache entry.
- `CacheRequest.abort()`: signals that writing failed; **the incomplete entry must be discarded**, and a partial response must never be served as complete.

### 2.2. `useCaches` is permission to use the cache, not the cache object

For each URLConnection:

~~~java
HttpURLConnection conn =
        (HttpURLConnection) url.openConnection();

conn.setUseCaches(false);  // call before connecting
conn.setConnectTimeout(3000);
conn.setReadTimeout(3000);

try (InputStream body = conn.getInputStream()) {
    // read body
} finally {
    conn.disconnect();
}
~~~

This is an **illustrative snippet** assuming `url` already exists, with `java.net.*` and `java.io.*` imported. If `conn.getUseCaches()==true`, the protocol handler **is allowed** to query the cache; this **does not guarantee** the response will come from the cache. It may miss, be expired, be `no-store`, be uncacheable, or have no cache registered. If `setUseCaches(false)` is called, the handler must bypass the cache per the flag's contract. Changing `setUseCaches` after already connected may throw `IllegalStateException`.

Two misconceptions:

- **`ResponseCache.setDefault(cache)` does not automatically create a fully configured cache.** Java only provides the hook/abstract classes; you or a library implement the cache policy.
- **`conn.setUseCaches(true)` does not enable a magical cache.** An actual handler/cache must exist and the request/response must be eligible.

### 2.3. Cache key, freshness, and HTTP semantics

A production HTTP cache must consider at a minimum:

| Factor | Consequence if ignored |
| --- | --- |
| HTTP method | May return a GET response for a POST request, violating semantics |
| URI including scheme, host, port, path, query | May mix content from two origins/resources |
| `Cache-Control: no-store` | Accidentally stores data forbidden from caching |
| `Cache-Control: private` | Stores personal data in a shared cache |
| `Authorization` or `Cookie` | Leaks session/user data across requests |
| `Vary`, e.g. `Accept-Language`/`Accept-Encoding` | Returns wrong body/encoding to another client |
| `max-age`/`Expires`/`Age`/date | Returns stale data after freshness has expired |
| `ETag`/`Last-Modified` and conditional GET | Fails to revalidate properly or mishandles 304 |
| Redirects and response `Cache-Control` | Mistakenly caches 3xx/4xx/5xx responses |
| Interrupted/partial body | Serves a truncated response |
| Capacity/eviction | Unbounded memory/disk growth |
| Invalidations after write methods | Caches stale data after PUT/DELETE |
| Concurrent readers/writers | Races, half-written entries, use-after-close |

Modern HTTP caching rules are defined in **RFC 9111**. Merely checking `Cache-Control: public, max-age=60` and storing a byte array by URI is not a production cache: you also need clock/freshness, revalidation, Vary, header updates, validation, eviction, response metadata, and security.

### 2.4. Thread-safety considerations

`ResponseCache.getDefault()` returns the same object that many HTTP calls/threads may use. Therefore, the implementation must manage concurrent maps, byte buffer ownership, atomic commits, eviction, file lifecycles, I/O failures, and memory quotas. When `get` returns a `CacheResponse`, each caller needs its **own InputStream** or immutable data so multiple readers do not contend over `position`. While `put` is writing, **do not publish an entry whose stream has not been closed/completed**; `abort` must delete partial data. Also do not use the `URLConnection` object inside the `put` callback to accidentally reopen the same URL and cause recursion.

## 3. CookieHandler: managing session state for HTTP URL handlers

### 3.1. CookieHandler does not bring its own cookie jar

`CookieHandler` is an abstract class with callbacks:

~~~java
abstract Map<String, List<String>> get(
        URI uri,
        Map<String, List<String>> requestHeaders)
        throws IOException;

abstract void put(
        URI uri,
        Map<String, List<String>> responseHeaders)
        throws IOException;
~~~

- `get(...)` is used by the HTTP protocol handler to retrieve cookie headers matching the URI before sending a request.
- `put(...)` feeds response headers (such as `Set-Cookie`) into the policy/store.
- `CookieHandler.getDefault()` returns the JVM-wide default handler or `null`.
- `CookieHandler.setDefault(handler)` changes the JVM-wide default; `setDefault(null)` removes the handler.
- Non-standard handlers/libraries may **ignore** the global handler.

**`CookieManager`** is a built-in implementation combining **`CookieStore`** and **`CookiePolicy`**. For example:

~~~java
CookieManager jar = new CookieManager(
        null, CookiePolicy.ACCEPT_ORIGINAL_SERVER);
CookieHandler previous = CookieHandler.getDefault();
CookieHandler.setDefault(jar);
try {
    // HttpURLConnection in the HTTP URL handler can share the jar.
} finally {
    CookieHandler.setDefault(previous);
}
~~~

This is an **illustrative snippet**, not a way to configure multiple tenants running concurrently. Passing `null` for the `store` parameter causes the JDK to create a default **in-memory** store; the cookie manager does not automatically persist to disk and does not promise browser-like persistent sessions. `CookiePolicy.ACCEPT_ORIGINAL_SERVER` is the default policy of `CookieManager` if no policy is specified; there are also `ACCEPT_ALL` and `ACCEPT_NONE`. Using `ACCEPT_ALL` for all external origins can grant overly broad permissions. Cookie policy, cookie attributes, and origin validation still require a threat model and testing.

### 3.2. Cookies are received and sent by URI, not dumped blindly from the whole jar

Server responds:

~~~http
HTTP/1.1 200 OK
Set-Cookie: sid=abc123; Path=/; HttpOnly; Secure
~~~

With a `Secure` cookie, browser/JDK cookie handling must consider secure transport; such values must not be sent over plaintext HTTP merely because of the same hostname. `Path`, `Domain`, `Max-Age`/`Expires`, and host/path matching affect which cookies are attached to which request. JDK cookie handling is not completely equivalent to modern browsers for every newer attribute (such as SameSite rules), and **should not be relied on as an untested browser security engine**.

`CookieHandler.get(URI,requestHeaders)` receives a URI containing the specific scheme/host; `CookieManager` decides which cookies apply. `HttpCookie` represents a cookie; `CookieStore` allows inspecting/deleting via `getCookies()`/`remove`/`removeAll`. Cookie values can be **session tokens**—do not log raw values, and do not put them into plaintext cache keys or metrics labels.

### 3.3. Scope and lifecycle of a cookie jar

A shared `CookieManager` can be useful for **a single logical HTTP session** that needs:
1. A login GET or POST receiving `Set-Cookie`.
2. Subsequent HTTP requests sending `Cookie` for the same origin/path.
3. The server receiving the session cookie and processing according to the logged-in state.
4. Logout/cookie deletion or expiry/policy ending the session.

However, if a single JVM runs multiple customer sessions, sharing one cookie jar poses a **risk of cross-tenant/cross-user leakage**. `CookieStore` must be isolated per logical tenant/session. Just because two APIs share the `CookieHandler` type does not mean sharing a jar across users is right. For requests carrying credentials, use a separate cookie manager, proper cookie policy, age limits, and clear the store on session logout.

### 3.4. Global cookie default must be configured stably

Do not do this:

~~~java
// ANTI-PATTERN: mutating global state per request
CookieHandler.setDefault(cookieJarUserA);
doRequestA();
CookieHandler.setDefault(cookieJarUserB);
doRequestB();
~~~

This is **wrong pseudocode**: `doRequestA`/`doRequestB` are not isolated, and in a concurrent application, request A may be sending headers at the exact moment thread B swaps the default. There is no dynamic-scoping guarantee that “while inside the try block only this thread uses the handler.”

Set the global `CookieHandler` once during bootstrap for a service that truly has **one unified cookie policy** if the legacy API is genuinely needed. If multiple policies are needed, prefer client-specific dependency injection or a library supporting per-client jars.

## 4. What is not automatically shared with java.net.http.HttpClient

Java 11+ has the modern `java.net.http.HttpClient` API, which **is not a subclass of `URLConnection`**. The differences regarding global hooks are critical:

| Feature | URLConnection / HttpURLConnection | java.net.http.HttpClient (Java 17) |
| --- | --- | --- |
| Default cookie | HTTP URL handler may use `CookieHandler.getDefault()` | **Does not automatically use the global CookieHandler** unless the builder sets `cookieHandler(...)` |
| Per-client cookie | Global URL handler, so hard to isolate per instance | `HttpClient.newBuilder().cookieHandler(manager)` |
| ResponseCache | HTTP URL handler uses `ResponseCache.getDefault()` when appropriate | **No guarantee of using global ResponseCache**, no ResponseCache builder |
| Proxy | Protocol handler may use JVM default `ProxySelector` and system properties | Builder `proxy(...)` can override; if omitted, typically uses the default selector |
| Authenticator | Has legacy global `Authenticator.setDefault(...)` | Builder `authenticator(...)` for the specific HTTP client |
| Redirects | `HttpURLConnection.setFollowRedirects(boolean)` static default and `setInstanceFollowRedirects` | Builder `followRedirects(HttpClient.Redirect)` per client |
| Protocol version | Legacy HTTP/1.1 handler | `Version.HTTP_1_1`/`HTTP_2` preference, separate actual response version |
| Timeouts | `URLConnection.setConnectTimeout`/`setReadTimeout` | `HttpClient.Builder.connectTimeout` and `HttpRequest.Builder.timeout` |
| Body/resource lifecycle | `getInputStream`, error stream, `disconnect` | `BodyHandlers`, futures, streams/subscribers per the API |

**`HttpClient.Builder.cookieHandler(...)` is an explicit opt-in.** If that method is not called, a Java 17 client **does not use a cookie handler**. Merely calling `CookieHandler.setDefault(jar)` and then `HttpClient.newHttpClient()` should not be assumed to enable cookies. Example 2 will prove this using a loopback server.

How to isolate cookies per logical session:

~~~java
CookieManager alice = new CookieManager(
        null, CookiePolicy.ACCEPT_ORIGINAL_SERVER);
CookieManager bob = new CookieManager(
        null, CookiePolicy.ACCEPT_ORIGINAL_SERVER);

HttpClient aliceClient = HttpClient.newBuilder()
        .cookieHandler(alice)
        .build();
HttpClient bobClient = HttpClient.newBuilder()
        .cookieHandler(bob)
        .build();
~~~

This is an **illustrative snippet** with `java.net.*` and `java.net.http.*` imported. The two clients have separate `CookieStore` instances, yet you still need to control same-origin checks, session expiry, credential handling, and avoid accidentally sharing another singleton. Do not reuse the same CookieManager object for two users when strict separation is required.

**ResponseCache is not HttpClient's HTTP caching API.** If you need caching for the modern HttpClient, use a dedicated HTTP caching layer/library or write your own architecture compliant with RFC 9111; do not expect `ResponseCache.setDefault(...)` to make `HttpClient.send(...)` return cache hits.

## 5. Java 17+ Example 1: Real ResponseCache, cache-hit, and bypass

This example is a **very small cache demo** that intentionally caches only one URL path `/public` from a **programmatically created loopback HTTP server**. The server returns an incrementing payload `origin-1`, `origin-2`... and the header `Cache-Control: public, max-age=60`. `SmallPublicCache`:

- `get(...)` looks up the entry for GET `/public`; returns `CacheResponse` when present.
- `put(...)` stores only HTTP 200 with the exact test Cache-Control; returns `CacheRequest` and commits when the output stream closes.
- Caps each entry at **16,384 bytes** so the demo does not buffer unbounded bodies.
- `ResponseCache.setDefault(cache)` is active only within the demo block; `finally` restores the previous default.
- `fetch(url,true)` allows caching; `fetch(url,false)` bypasses the cache.

**Security limitations:** this sample cache implementation does **NOT** support expiration, Vary, conditional requests, Authorization/cookies, revalidation, status variants, eviction, or robust concurrency/cancellation. It is **only for public resources controlled by the test server**—never use it as a production HTTP cache or with real user responses.

Create the file **`UrlResponseCacheDemo.java`**:

~~~java
import com.sun.net.httpserver.*;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public final class UrlResponseCacheDemo {
    static final class SmallPublicCache extends ResponseCache {
        record Entry(byte[] data,
                     Map<String, List<String>> headers) {}

        private final ConcurrentMap<URI, Entry> entries =
                new ConcurrentHashMap<>();
        final AtomicInteger lookups = new AtomicInteger();
        final AtomicInteger hits = new AtomicInteger();
        final AtomicInteger stores = new AtomicInteger();

        @Override
        public CacheResponse get(
                URI uri, String method,
                Map<String, List<String>> requestHeaders) {
            lookups.incrementAndGet();
            if (!"GET".equals(method)
                    || !"/public".equals(uri.getPath())) {
                return null;
            }
            Entry entry = entries.get(uri);
            if (entry == null) return null;
            hits.incrementAndGet();
            return new CacheResponse() {
                @Override
                public Map<String, List<String>> getHeaders() {
                    return entry.headers();
                }

                @Override
                public InputStream getBody() {
                    return new ByteArrayInputStream(entry.data());
                }
            };
        }

        @Override
        public CacheRequest put(
                URI uri, URLConnection connection)
                throws IOException {
            if (!(connection instanceof HttpURLConnection http)
                    || !"/public".equals(uri.getPath())
                    || http.getResponseCode() != 200
                    || !"public, max-age=60".equalsIgnoreCase(
                        http.getHeaderField("Cache-Control"))) {
                return null;
            }

            Map<String, List<String>> headers =
                    new LinkedHashMap<>();
            http.getHeaderFields().forEach((key, values) ->
                    headers.put(key, List.copyOf(values)));

            return new CacheRequest() {
                private final ByteArrayOutputStream buffer =
                        new ByteArrayOutputStream();
                private boolean aborted;

                @Override
                public OutputStream getBody() {
                    return new OutputStream() {
                        @Override
                        public void write(int b) throws IOException {
                            if (buffer.size() >= 16384) {
                                throw new IOException("Too large");
                            }
                            buffer.write(b);
                        }

                        @Override
                        public void write(
                                byte[] b, int off, int len)
                                throws IOException {
                            if (len > 16384 - buffer.size()) {
                                throw new IOException("Too large");
                            }
                            buffer.write(b, off, len);
                        }

                        @Override
                        public void close() throws IOException {
                            if (!aborted) {
                                entries.put(uri, new Entry(
                                        buffer.toByteArray(), headers));
                                stores.incrementAndGet();
                            }
                        }
                    };
                }

                @Override
                public void abort() {
                    aborted = true;
                }
            };
        }
    }

    private static String fetch(
            URL url, boolean useCaches) throws Exception {
        HttpURLConnection connection =
                (HttpURLConnection) url.openConnection(
                        Proxy.NO_PROXY);
        connection.setConnectTimeout(3000);
        connection.setReadTimeout(3000);
        connection.setUseCaches(useCaches);

        try (InputStream in = connection.getInputStream()) {
            return new String(
                    in.readAllBytes(), StandardCharsets.UTF_8);
        } finally {
            connection.disconnect();
        }
    }

    public static void main(String[] args)
            throws Exception {
        ResponseCache original = ResponseCache.getDefault();
        InetAddress loopback =
                InetAddress.getLoopbackAddress();
        AtomicInteger originCalls = new AtomicInteger();

        HttpServer server = HttpServer.create(
                new InetSocketAddress(loopback, 0), 0);
        server.createContext("/public", ex -> {
            byte[] body = (
                    "origin-" + originCalls.incrementAndGet())
                    .getBytes(StandardCharsets.UTF_8);
            ex.getResponseHeaders().set(
                    "Cache-Control", "public, max-age=60");
            ex.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=UTF-8");
            ex.sendResponseHeaders(200, body.length);
            try (OutputStream out = ex.getResponseBody()) {
                out.write(body);
            }
        });
        server.start();

        try {
            SmallPublicCache cache = new SmallPublicCache();
            ResponseCache.setDefault(cache);
            URL url = new URI(
                    "http", null, loopback.getHostAddress(),
                    server.getAddress().getPort(),
                    "/public", null, null).toURL();

            System.out.println(
                    "first: " + fetch(url, true));
            System.out.println(
                    "second: " + fetch(url, true));
            System.out.println(
                    "bypass: " + fetch(url, false));
            System.out.println(
                    "origin calls: " + originCalls.get());
            System.out.println(
                    "cache hits: " + cache.hits.get());
            System.out.println(
                    "cache stores: " + cache.stores.get());
        } finally {
            ResponseCache.setDefault(original);
            server.stop(0);
        }
    }
}
~~~

Compile/run on JDK 17+ (with the `jdk.httpserver` module):

~~~bash
javac --release 17 UrlResponseCacheDemo.java
java UrlResponseCacheDemo
~~~

Stdout **verified on a local JDK**:

~~~text
first: origin-1
second: origin-1
bypass: origin-2
origin calls: 2
cache hits: 1
cache stores: 1
~~~

Exact explanation:

1. First request `setUseCaches(true)`: `cache.get` has no entry so the protocol handler goes to the loopback origin and receives `origin-1`; `cache.put` receives the bytes and stores them upon completion.
2. Second request to the **same URI**, with caching enabled: `get` returns `CacheResponse` with body `origin-1`, and **the origin is not called a second time**.
3. Third request `setUseCaches(false)`: bypasses the global cache hook, goes to the origin, and fetches `origin-2`.
4. `origin calls: 2` is the number of times the actual origin handler was invoked in the test, not the number of URLConnections created (three).
5. `cache hits: 1` and `cache stores: 1` demonstrate successful cache lookup/put; the `lookups` field is kept for debugging but not printed so it is not confused with hits.
6. `CacheResponse.getBody()` creates **a new ByteArrayInputStream each time**, preventing multiple readers from contending over the read position of a single mutable stream.
7. `CacheRequest.getBody().close()` is what commits the data. `abort()` does not insert the failed entry into the map.
8. In the demo, `get` ignores `requestHeaders` and does not check expiry, so **do not use this code for any response that is personal, varies by headers, or comes from the real Internet**.

Note: `CacheRequest.getBody()` only needs to provide a buffer/stream because the protocol handler will write the bytes. **`ResponseCache.put` must NOT call `conn.getInputStream()` itself to download the response a second time**. Reading again inside `put` can cause re-entry/redundant I/O or deadlock.

## 6. Java 17+ Example 2: Global CookieHandler and explicit HttpClient

The next test shows that the same `CookieManager` is used as the **global CookieHandler** by `HttpURLConnection`, whereas **java.net.http.HttpClient does not automatically use it when the builder lacks `cookieHandler(...)`**.

The loopback server has:
- `/login`: sends header `Set-Cookie: sid=demo123; Path=/; HttpOnly`.
- `/whoami`: checks whether that request cookie is present and returns only the string `true` or `false`, **without echoing the secret**.

Create the file **`UrlCookieHandlerDemo.java`**:

~~~java
import com.sun.net.httpserver.*;
import java.io.*;
import java.net.*;
import java.net.http.*;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public final class UrlCookieHandlerDemo {
    private static String fetchOld(URL url)
            throws Exception {
        HttpURLConnection c =
                (HttpURLConnection) url.openConnection(
                        Proxy.NO_PROXY);
        c.setConnectTimeout(3000);
        c.setReadTimeout(3000);
        c.setUseCaches(false);
        try (InputStream body = c.getInputStream()) {
            return new String(
                    body.readAllBytes(),
                    StandardCharsets.UTF_8);
        } finally {
            c.disconnect();
        }
    }

    private static String fetchNew(
            HttpClient client, URI uri) throws Exception {
        HttpRequest req = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(5))
                .GET().build();
        return client.send(
                req, HttpResponse.BodyHandlers.ofString())
                .body();
    }

    public static void main(String[] args)
            throws Exception {
        CookieHandler previous =
                CookieHandler.getDefault();
        InetAddress loopback =
                InetAddress.getLoopbackAddress();

        HttpServer server = HttpServer.create(
                new InetSocketAddress(loopback, 0), 0);

        server.createContext("/login", exchange -> {
            exchange.getResponseHeaders().add(
                    "Set-Cookie",
                    "sid=demo123; Path=/; HttpOnly");
            byte[] bytes = "set".getBytes(
                    StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(
                    200, bytes.length);
            try (OutputStream out =
                    exchange.getResponseBody()) {
                out.write(bytes);
            }
        });

        server.createContext("/whoami", exchange -> {
            String incoming =
                    exchange.getRequestHeaders()
                            .getFirst("Cookie");
            byte[] bytes = String.valueOf(
                    incoming != null &&
                            incoming.contains("sid=demo123"))
                    .getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(
                    200, bytes.length);
            try (OutputStream out =
                    exchange.getResponseBody()) {
                out.write(bytes);
            }
        });

        server.start();
        try {
            CookieManager jar = new CookieManager(
                    null,
                    CookiePolicy.ACCEPT_ORIGINAL_SERVER);
            CookieHandler.setDefault(jar);

            URI base = new URI(
                    "http", null, loopback.getHostAddress(),
                    server.getAddress().getPort(),
                    "/", null, null);

            fetchOld(base.resolve("login").toURL());
            System.out.println(
                    "legacy sends cookie: " +
                    fetchOld(base.resolve("whoami").toURL()));
            System.out.println(
                    "stored cookies: " +
                    jar.getCookieStore().getCookies().size());

            HttpClient without = HttpClient.newBuilder()
                    .proxy(HttpClient.Builder.NO_PROXY)
                    .build();
            System.out.println(
                    "new client default cookie: " +
                    fetchNew(without,
                            base.resolve("whoami")));

            HttpClient withJar = HttpClient.newBuilder()
                    .proxy(HttpClient.Builder.NO_PROXY)
                    .cookieHandler(jar)
                    .build();
            System.out.println(
                    "new client explicit cookie: " +
                    fetchNew(withJar,
                            base.resolve("whoami")));
        } finally {
            CookieHandler.setDefault(previous);
            server.stop(0);
        }
    }
}
~~~

~~~bash
javac --release 17 UrlCookieHandlerDemo.java
java UrlCookieHandlerDemo
~~~

Stdout **verified on a local JDK**:

~~~text
legacy sends cookie: true
stored cookies: 1
new client default cookie: false
new client explicit cookie: true
~~~

Reading the output step by step:

1. `CookieHandler.setDefault(jar)` causes the HTTP URL handler to call `CookieManager.put` when `/login` returns `Set-Cookie`, so the jar contains one cookie.
2. The second `HttpURLConnection` calls `CookieManager.get` and sends the matching cookie to `/whoami`: the server reports `true`.
3. `HttpClient.newBuilder()` **without calling `cookieHandler(...)`** does not automatically use the global jar: the server reports `false`, even though `CookieHandler.getDefault()==jar` during the test.
4. `HttpClient.newBuilder().cookieHandler(jar)` uses that exact jar as an **explicit per-client dependency**: the server reports `true`.
5. `CookieHandler.setDefault(previous)` in `finally` ensures the test does not leave the demo's global cookie manager behind after normal completion or throwing an exception; **this mechanism does not turn global mutation into thread-local safety** if other HTTP requests are running concurrently.
6. `CookiePolicy.ACCEPT_ORIGINAL_SERVER` is suitable for demonstrating first-party `Set-Cookie`; JDK cookie policy still needs checking against host, domain/path, and attributes required by the product.
7. `HttpClient.Builder.NO_PROXY` specifies direct connections for the demo, preventing an environment default proxy from altering the route; it is not part of `CookieManager`.

Do not use the cookie `sid=demo123` as a real credential. In production, do not print cookie values or send session tokens to another host. For secure/session cookies, you need HTTPS, a CSRF strategy, SameSite/server validation, and other security policies.

## 7. Default useCaches and redirects can affect new connections

### 7.1. URLConnection.setDefaultUseCaches(String,boolean)

In Java 17, there is a static API:

~~~java
URLConnection.setDefaultUseCaches(
        "http", false);
boolean value =
        URLConnection.getDefaultUseCaches("http");
~~~

It sets the default `useCaches` for **future URLConnection objects of the HTTP protocol**. `"http"` is case-insensitive per the Javadoc. Do not confuse it with the instance method `conn.setDefaultUseCaches(boolean)` (a legacy method that changes the default per Javadoc behavior) or `conn.setUseCaches(boolean)` (only that connection).

Use the **right overload**: `setDefaultUseCaches(String,boolean)` is **static** (since Java 9), whereas `setDefaultUseCaches(boolean)` is an **instance method** on `URLConnection` with default-mutating semantics. Similarly, `getDefaultUseCaches(String)` is static; `getDefaultUseCaches()` is an instance method. Do not call the instance method thinking you are changing the flag of a single connection.

Each connection captures the default value at creation time, and can override it afterward:

~~~java
URLConnection.setDefaultUseCaches("http", false);
URLConnection first = someHttpUrl.openConnection();
// first.getUseCaches() is typically false.

URLConnection.setDefaultUseCaches("http", true);
URLConnection second = someHttpUrl.openConnection();
// second.getUseCaches() is typically true.
// first still keeps the initialized value.

first.setUseCaches(true);  // override only first, before connect.
~~~

This is **illustrative code**; `someHttpUrl` must already exist. Changing the default does not update any `URLConnection` objects that have already been created.

### 7.2. Static and instance HttpURLConnection.setFollowRedirects

~~~java
HttpURLConnection.setFollowRedirects(false);
boolean global = HttpURLConnection.getFollowRedirects();

HttpURLConnection conn = (HttpURLConnection)
        someHttpUrl.openConnection();
boolean perInstance = conn.getInstanceFollowRedirects();
conn.setInstanceFollowRedirects(true);
~~~

The static call `setFollowRedirects` changes the **global default** for `HttpURLConnection` instances created afterward; `setInstanceFollowRedirects` adjusts the **instance**. This is the redirect policy of the legacy HTTP stack, **not** `HttpClient.Builder.followRedirects(...)`. Both security and performance are affected if a redirect unexpectedly goes to another origin, another port, an internal endpoint, or a URI containing a token.

### 7.3. Java 17+ Example 3: checking default snapshots without opening the network

Create the file **`UrlGlobalDefaultsDemo.java`**. The example only creates a URL targeting loopback port 1 (without calling `connect`/`getInputStream`), so no real network request occurs.

~~~java
import java.net.*;

public final class UrlGlobalDefaultsDemo {
    public static void main(String[] args)
            throws Exception {
        boolean previousCache =
                URLConnection.getDefaultUseCaches("http");
        boolean previousRedirect =
                HttpURLConnection.getFollowRedirects();

        try {
            URL url = new URI(
                    "http://127.0.0.1:1/not-connected")
                    .toURL();

            URLConnection.setDefaultUseCaches(
                    "http", false);
            HttpURLConnection a =
                    (HttpURLConnection) url.openConnection(
                            Proxy.NO_PROXY);
            System.out.println(
                    "a default cache: " + a.getUseCaches());

            URLConnection.setDefaultUseCaches(
                    "http", true);
            HttpURLConnection b =
                    (HttpURLConnection) url.openConnection(
                            Proxy.NO_PROXY);
            System.out.println(
                    "a existing cache: " + a.getUseCaches());
            System.out.println(
                    "b new cache: " + b.getUseCaches());

            a.setUseCaches(true);
            System.out.println(
                    "a instance cache override: " +
                    a.getUseCaches());

            HttpURLConnection.setFollowRedirects(false);
            HttpURLConnection c =
                    (HttpURLConnection) url.openConnection(
                            Proxy.NO_PROXY);
            System.out.println(
                    "c default redirects: " +
                    c.getInstanceFollowRedirects());

            c.setInstanceFollowRedirects(true);
            System.out.println(
                    "c instance redirects override: " +
                    c.getInstanceFollowRedirects());
            System.out.println(
                    "global redirect default: " +
                    HttpURLConnection.getFollowRedirects());
        } finally {
            URLConnection.setDefaultUseCaches(
                    "http", previousCache);
            HttpURLConnection.setFollowRedirects(
                    previousRedirect);
        }
    }
}
~~~

~~~bash
javac --release 17 UrlGlobalDefaultsDemo.java
java UrlGlobalDefaultsDemo
~~~

Stdout **deterministic, run on a local JDK**:

~~~text
a default cache: false
a existing cache: false
b new cache: true
a instance cache override: true
c default redirects: false
c instance redirects override: true
global redirect default: false
~~~

Notable observations:

- `a` was created when the default HTTP cache flag was `false`, so after the static default changes to `true`, `a.getUseCaches()` **remains false**.
- `b` was created after changing the default to true, so it gets `useCaches=true`.
- `a.setUseCaches(true)` only changes instance `a`, without affecting `b` or the static default.
- `HttpURLConnection.setFollowRedirects(false)` gives the new connection `c` a false redirect flag, but `c.setInstanceFollowRedirects(true)` overrides the instance and **global remains false**.
- `finally` restores the pre-test values; **do not leave the demo's global defaults active for other code**.
- These flags are not proof that an HTTP request was sent; all connections in the example are **not connected**.

## 8. Other default settings that easily “leak” across modules

In addition to ResponseCache/CookieHandler, Java Networking has other JVM-wide hooks:

| Global API | Meaning | Risk when a module changes it arbitrarily |
| --- | --- | --- |
| `ProxySelector.setDefault(...)` | Default route selector for APIs that use it | Traffic goes through the wrong proxy, bypasses egress, or breaks routes |
| `Authenticator.setDefault(...)` | Default auth callback | Sends credentials to an unintended origin/proxy |
| `CookieHandler.setDefault(...)` | Default cookie handler | Cookie/session leakage between users/modules |
| `ResponseCache.setDefault(...)` | Default cache hook | Serves stale/private responses to another caller |
| `URLConnection.setDefaultUseCaches("http", ...)` | Default cache flag for the protocol | One place disables cache while another expects caching |
| `URLConnection.setDefaultAllowUserInteraction(...)` | Default interaction permission | Changes behavior of new URLConnection objects |
| `HttpURLConnection.setFollowRedirects(...)` | Redirect default | Client does not follow as expected or redirects outside policy |
| `URLConnection.setFileNameMap(...)` | File extension → MIME mapping | MIME/conversion mapping changes across modules |
| `URLConnection.setContentHandlerFactory(...)` | Installs content handler factory | One-time setup; a second plugin may fail to install |
| `URL.setURLStreamHandlerFactory(...)` | Installs factory for URL protocols | One-time setup per VM; late changes may fail |
| System properties `http.proxyHost`, `https.proxyHost` | Used by some URL handlers/default selectors | Changes process-wide egress, does not cover every library |
| `java.net.useSystemProxies` | Uses OS proxy settings when supported | Typically read at JVM startup; runtime changes may have no effect |

Not every hook affects **all libraries** or all protocols. `ProxySelector` applies to clients that actively use the selector, `ResponseCache` is primarily a URLConnection cache hook, and `CookieHandler` relates to HTTP URL handlers and clients explicitly configured with it. **“JVM-wide default” = shared state if an API uses that default**, not that every library automatically consults the same object.

### 8.1. Authenticator: credential scope must be tight

A custom `Authenticator` can receive challenges from an origin or an HTTP proxy. If `Authenticator.setDefault(...)` is used, it can potentially be called for **many destinations** in the JVM. You must distinguish:
- `RequestorType.SERVER` vs. `RequestorType.PROXY`.
- Requested host/port/protocol and realm/auth scheme.
- The credential store for the right tenant/service.
- Never log raw passwords or hardcode them in source code literals.
- Never return private-origin secrets to a proxy challenge or vice versa.

An `HttpClient` created with `HttpClient.newBuilder().authenticator(myAuthenticator)` has an explicit per-client dependency, which is easier to audit than a global singleton. However, the same authenticator object can still hold shared state; the per-client builder does not automatically create isolation if the application intentionally shares a secrets object.

### 8.2. ProxySelector: JVM-wide, yet request routes must still be tested

`ProxySelector.setDefault(...)` changes the default selector. In multi-tenant code, changing the default per request is very dangerous. If using `HttpClient.Builder.proxy(selector)`, each client can choose its own selector; to force direct connections, use `HttpClient.Builder.NO_PROXY` (Java 17). With legacy URLConnection, `url.openConnection(Proxy.NO_PROXY)` specifies direct for that connection without depending on the default proxy selector. Avoid failing open to DIRECT after a proxy error if egress policy forbids it.

JVM system properties like `http.proxyHost`/`http.nonProxyHosts` or `socksProxyHost` do not automatically affect every HTTP library/custom client. Check proxy-side logs or permitted network tracing to verify the actual route. Defaults are not an authorization boundary; the proxy must still enforce allowed destinations.

### 8.3. “Set only once” is not the same as “swap defaults at will”

`URL.setURLStreamHandlerFactory(...)` and `URLConnection.setContentHandlerFactory(...)` are extension mechanisms for URL schemes/content types with restrictions on factory installation. Per the Javadoc, a `URL` factory can only be set **once per VM**, and subsequent calls may throw `Error`; `URLConnection.setContentHandlerFactory(...)` can also only be set once, and subsequent calls may throw `Error`. Do not recommend “restoring the old factory in finally” like cache/cookie defaults. A library that arbitrarily calls these setters can hijack the application server's configuration and conflict with plugin containers.

`URLConnection.setDefaultRequestProperty(key,value)` is **deprecated**; the Javadoc recommends using `conn.setRequestProperty(...)` on each instance. Do not use default request properties to broadcast `Authorization` or session headers JVM-wide.

## 9. What changes immediately vs. what is captured at creation time

There are two groups of effects to distinguish:

### 9.1. Static defaults captured when creating the object

`URLConnection.setDefaultUseCaches("http", false)` changes the value that **future HTTP URLConnections** will use as their default. A connection created earlier has its own `useCaches` and **does not automatically change** when the static default changes. Similarly, `HttpURLConnection.setFollowRedirects(false)` sets the static default for **new HttpURLConnection instances**. Example 3 verifies this.

### 9.2. Global handlers referenced at I/O time per implementation

`ResponseCache.setDefault(cache)` and `CookieHandler.setDefault(handler)` register singleton handlers that the HTTP URL protocol implementation may reference during request/response processing. **Do not treat a `URL.openConnection()` call as an immutable “snapshot” of all global handlers**. Changing `CookieHandler.setDefault(...)` or `ResponseCache.setDefault(...)` while multiple requests are active can cause behavior to differ across phases depending on the implementation, callback timing, and protocol handler. Therefore, do not use global swaps as dynamic request scoping.

Tests use `try/finally` only to **restore state when running standalone**, not as a thread-safe pattern in a server with concurrent requests. To avoid races:
1. Set globals once at bootstrap if the entire application is truly uniform.
2. Better yet, pass separate dependencies via constructors/builders per client/session.
3. Design integration tests to run in a separate process/isolated JVM when static defaults must be modified.
4. Do not mutate global defaults of a JVM serving live traffic.

## 10. When are ResponseCache and CookieHandler needed together?

A Java HTTP workflow may:
1. `CookieManager` receives `Set-Cookie: sid=...` upon login.
2. Subsequent requests attach `Cookie: sid=...` based on URI/path/secure policy.
3. `ResponseCache` checks whether the resource can be served from the local cache instead of the network.
4. The server may return private content depending on the session cookie.

This is also the **most dangerous point**: if the cache key consists only of the URI, user A's `/account/profile` response can be served back to user B. You cannot simply “enable ResponseCache + CookieHandler” and assume cross-user data leaks are automatically prevented. The application cache must:
- By default **not cache authenticated/private responses** in a shared cache.
- If caching user-specific data, partition safely by tenant/session, respect `Cache-Control`/`Vary`, and avoid writing secrets into keys/logs.
- Consider `no-store` for `Set-Cookie` responses, tokens, and sensitive endpoints per policy.
- Never pass tenant A's cookie store into tenant B's `HttpClient`.
- Never use cache lookup to bypass authorization; permissions must be enforced even on a cache hit.
- Ensure logout/revocation/session expiry have compatible cache invalidation.

Example 1 **caches only `/public`** with a body containing no session data, and Example 2 **disables caching** on legacy URLConnections carrying cookies. This is an intentional separation of the two concepts in the lesson, not a complete HTTP caching policy.

## 11. How do caching, cookies, and redirects interact?

Suppose URL `https://service.example.test/start` returns HTTP 302 to `/login` and then `Set-Cookie` is received in a later step. A client might:
- Follow redirects according to `HttpURLConnection.setInstanceFollowRedirects` / the global static default.
- Use CookieHandler to receive cookies from the endpoint returning `Set-Cookie`.
- Allow caching certain responses if the cache policy deems them valid.

However, there is no guarantee that “a 302 redirect is always cached” or “CookieManager will definitely send cookies to every redirected host.” A redirect can change hostname/path/scheme; each step must evaluate cookie `Domain`, `Path`, `Secure`, and security. A cache hit may return a response without contacting the network; if the handler does not accurately model response metadata/session policy, the application may miss headers or side effects that would occur when fetching from the origin.

Do not conflate:
- `HttpURLConnection.setFollowRedirects(...)`: static default redirect policy of the legacy stack.
- `HttpURLConnection.setInstanceFollowRedirects(...)`: per-connection.
- `HttpClient.Builder.followRedirects(HttpClient.Redirect.NORMAL/ALWAYS/NEVER)`: per modern client.

For requests with an `Authorization` header, redirects to another origin can cross a new security boundary. Do not automatically supply credentials without checking host/trust, and do not blindly follow HTTP→HTTPS or HTTPS→HTTP. For cookies, avoid plaintext HTTP if the cookie is `Secure` or the session is sensitive.

## 12. URLConnection and HTTP response-body resource lifecycle

An `HttpURLConnection` instance typically corresponds to **one HTTP request**, though the underlying persistent TCP connection may be shared across multiple instances per the Javadoc. To read the body:

~~~java
HttpURLConnection connection =
        (HttpURLConnection) url.openConnection();

connection.setConnectTimeout(5000);
connection.setReadTimeout(5000);
connection.setUseCaches(false);

try {
    int status = connection.getResponseCode();
    InputStream source = status >= 400
            ? connection.getErrorStream()
            : connection.getInputStream();

    if (source != null) {
        try (InputStream body = source) {
            consumeBodyWithLimit(body);
        }
    }
} finally {
    connection.disconnect();
}
~~~

This is **non-standalone illustrative code**: `url` and `consumeBodyWithLimit` must be provided by the application, along with `java.io.*` and `java.net.*` imports. On HTTP errors, `getErrorStream()` may return `null`; a status code does not guarantee an error body exists. `disconnect()` may close the underlying socket if the persistent connection is idle, but it should not be assumed to tear down every shared connection.

**Before integrating caching**, plan streaming carefully: a `CacheRequest` may be `abort()`ed if reading the response fails or is incomplete. Never replay an incomplete cache entry. With modern `HttpClient` streaming bodies, ownership is described by `BodyHandler`/`BodySubscriber`, unrelated to the global `ResponseCache`.

## 13. The truth about “hidden caches” in Java applications

A Java application may have **multiple cache layers**:

~~~text
business cache (per tenant / feature)
        │
HTTP library cache (if configured)
        │
URLConnection ResponseCache hook (legacy URL handler)
        │
HTTP proxy / CDN cache (out-of-process)
        │
server/application cache
        │
database cache
~~~

`URLConnection.setUseCaches(false)` controls **cache usage at the URLConnection protocol handler**; it does not magically disable CDN caches, proxy caches, DNS caches, application caches, or caches in another HTTP library. The `Cache-Control: no-cache` header **does not mean “must not be stored”**; per HTTP caching semantics it primarily requires validation before reuse. `no-store` is the directive that forbids storage under RFC 9111.

Furthermore, `CookieHandler` neither guarantees cookie persistence on disk nor handles session rotation/revocation or CSRF on its own. Do not use the notion of a “stateful HTTP session” to infer that a TCP connection and a cookie session are the same thing. Cookies live across multiple HTTP requests, potentially over multiple TCP connections; `ResponseCache` caches resources according to its own semantics.

## 14. Testing strategy: isolating global state and testing miss/hit/deny branches

If you write a cache or cookie integration, design tests for:

**ResponseCache**
- Public cacheable GET → miss then put, next GET → hit.
- `setUseCaches(false)` → bypass.
- `no-store` → no put.
- `private` / `Authorization` / `Cookie` → do not cache shared response.
- Different `Vary` request headers → do not reuse the wrong representation.
- Expired entry → revalidation or network.
- Mid-stream body write error → `CacheRequest.abort()`, do not serve partial.
- Two concurrent misses on the same URI → handle race/duplicate downloads per policy.
- Cache size cap/eviction, crash recovery, updates after write methods.
- Vary status/headers/content-type preserved on hit.

**CookieHandler**
- `ACCEPT_NONE`: `Set-Cookie` is not stored.
- `ACCEPT_ORIGINAL_SERVER`: first-party cookie matching host/path.
- `Secure`: not sent over plain HTTP.
- Domain/path matching, expiry, cookie deletion.
- No session sharing across users/tenants.
- `HttpURLConnection` uses the installed global jar; `HttpClient` only uses an explicit jar.
- Case-insensitive header fields per HTTP semantics; do not log cookie values.

**Global defaults**
- Create connection A before static default change, B after; observe `getUseCaches` / `getInstanceFollowRedirects`.
- Instance setter override succeeds before connected.
- Calling setter after connected is rejected per the respective API.
- Test in a separate process if one-time global factories must be changed.
- When integration tests run in parallel, avoid sharing JVM static setters or use a sandbox/isolated subprocess.
- Read/write defaults at startup; document system properties and target JDK build.

**Do not call unauthorized external URLs** when testing. The three examples in this lesson use loopback/no network for deterministic results and to avoid impacting external servers.

## 15. Troubleshooting: finding the root cause at the right layer

| Symptom | Possible cause | Check |
| --- | --- | --- |
| Second GET request still calls origin | Cache miss, no handler, useCaches=false, uncacheable response | `ResponseCache.getDefault()`, `conn.getUseCaches()`, cache counters, response headers |
| Getting stale data when fresh is wanted | Cache not invalidated, wrong TTL/revalidation, proxy/CDN cache | Response headers, `Age`, authorized network trace, cache policy |
| Cache returns another user's data | Cache key lacks tenant/session, ignores `private`/`Vary` | Disable affected cache, security incident review, partition/cache invalidation |
| Cookie not sent in URLConnection | Default CookieHandler null, policy rejected, wrong domain/path/secure scope | `CookieHandler.getDefault()`, CookieStore, request URI, Set-Cookie |
| Cookie is in CookieStore but modern HttpClient does not send it | Builder lacks `cookieHandler(...)` | `client.cookieHandler()`, builder wiring |
| Login succeeds but next request loses session | Cookie expiry/path/domain/scheme, different jars, or redirects | Cookie flags, URI, handler instance, tenant isolation |
| Single unit test PASSES, parallel suite FAILS | Another test mutates global defaults | Isolate process/serial test, restore state, avoid global mutation |
| `setUseCaches` throws IllegalStateException | Setter called after connection was established | Set before `connect/getInputStream/getHeaderFields` |
| `HttpClient` still fetches from origin despite ResponseCache entry | Modern HttpClient does not rely on global ResponseCache | Use a dedicated cache layer for the client |
| Redirect behavior differs across modules | Global `setFollowRedirects` changed at runtime | `getInstanceFollowRedirects()` and connection creation time |
| CookieManager grows memory long-term | In-memory store retains cookies, session lifecycle lacks cleanup | Expiry, removeAll/logout, monitoring |
| Cache put never commits | Body not read to EOF/stream not closed, CacheRequest aborted | I/O lifecycle, getBody close/abort, counters |
| Unexpected proxy route | Default/global ProxySelector or environment | `ProxySelector.getDefault()`, per-client overrides |
| SecurityException on setDefault | Security manager/permission policy blocks it per target JDK | Permission contract; do not bypass policy |
| Custom URL handler ignores cookie/cache globals | Handler does not support them | Check handler documentation; do not assume all URL schemes behave like HTTP |

## 16. Self-check questions

**Q1.** Does calling `ResponseCache.setDefault(cache)` automatically enable caching for all `HttpClient.newHttpClient()` requests?  
**Answer:** No. `ResponseCache` is a URLConnection/protocol-handler hook; modern `HttpClient` does not automatically use that global cache.

**Q2.** Does `conn.setUseCaches(true)` guarantee a cache hit?  
**Answer:** No. It only allows the handler to use a cache when a policy-compliant implementation/entry exists.

**Q3.** Is a cache key consisting only of the URI safe for responses that vary by Cookie/User?  
**Answer:** No. A shared cache can leak session/private data; you must respect `Cache-Control`/`Vary`, partition, or not cache authenticated responses.

**Q4.** What does `ResponseCache.get(...)` returning `null` mean?  
**Answer:** Cache miss/entry not usable; the protocol handler proceeds to fetch the resource from the origin per contract.

**Q5.** May `CacheRequest.abort()` retain a partially written body?  
**Answer:** No. Incomplete entries must be discarded and never served as complete.

**Q6.** Does `CookieHandler.setDefault(jar)` make modern `HttpClient.newHttpClient()` automatically send cookies from the jar?  
**Answer:** No. An explicit `HttpClient.Builder.cookieHandler(jar)` is required.

**Q7.** Does `CookieManager(null, ACCEPT_ORIGINAL_SERVER)` automatically persist cookies to disk?  
**Answer:** No. The default store is in-memory.

**Q8.** What problem can occur if two users share the same `CookieManager`?  
**Answer:** Cookie/session leakage across contexts, violating isolation; separate jars are needed per tenant/session.

**Q9.** After `URLConnection.setDefaultUseCaches("http",false)`, does a previously created connection automatically change its `getUseCaches()`?  
**Answer:** No. Setting the default affects future connections; an existing instance has its own flag.

**Q10.** Do `HttpURLConnection.setFollowRedirects(false)` and `setInstanceFollowRedirects(false)` have the same scope?  
**Answer:** No. One is a static default for new connections; the other is for a single instance.

**Q11.** Is `URLConnection.setDefaultUseCaches(boolean)` a static method that should be called on the class?  
**Answer:** No. The single-boolean overload is an instance method; the `(String,boolean)` overload is static in Java 9+.

**Q12.** Should each thread call `CookieHandler.setDefault(ownJar)` before a request and restore it immediately afterward?  
**Answer:** No. There is no per-thread isolation; concurrent requests can observe another thread's handler.

**Q13.** Why are `Cache-Control: no-cache` and `no-store` not the same?  
**Answer:** `no-cache` primarily requires revalidation before reuse, whereas `no-store` forbids storing the response under RFC 9111.

**Q14.** Are cookies part of a TCP connection?  
**Answer:** No. Cookies are HTTP state across multiple requests/connections; scope is determined by URI/cookie attributes.

**Q15.** Can you change `URL.setURLStreamHandlerFactory(...)` several times and restore the old factory in `finally`?  
**Answer:** No. It is a one-time-per-VM factory API per the Javadoc; subsequent calls may fail.

**Q16.** Why does Demo 1 output `first=origin-1`, `second=origin-1`, `bypass=origin-2`?  
**Answer:** The first is a miss+store, the second is a cache hit, and the third has per-connection `useCaches=false` so it fetches fresh from the origin.

**Q17.** Does `HttpClient.Builder.cookieHandler(jar)` make legacy URLConnections use that jar?  
**Answer:** Not automatically; only that built client uses the jar, while legacy URL handlers still depend on the default `CookieHandler`.

**Q18.** In a multi-tenant server, what is the best way to handle cookie/cache/redirect options?  
**Answer:** Scope dependencies separately per client/session, prefer explicit builder/instance settings, and avoid mutating global JVM state while serving traffic.

## 17. Pre-production checklist

1. Distinguish **per-instance URLConnection setters** from **system-wide/default setters**.
2. `ResponseCache` is only a **cache hook**; have a valid implementation and RFC 9111 policy before using it with real data.
3. `CookieHandler` is only a **session policy hook**; define `CookieManager`/`CookieStore`/`CookiePolicy` explicitly.
4. Do not store `private`/`no-store` responses or authenticated content in a shared cache; handle `Vary`/TTL/revalidation/partial writes.
5. Do not share cookie jars across tenants; clear cookies on logout and protect values from logs.
6. Use `URLConnection.setUseCaches(false)` before network I/O when you need to bypass the URL handler cache.
7. Treat global handlers/static flags as **shared mutable state**, not as a way to route policy per thread/request.
8. With `java.net.http.HttpClient`, configure `cookieHandler(...)` explicitly; do not expect global `CookieHandler` or `ResponseCache` to be used automatically.
9. Distinguish static `HttpURLConnection.setFollowRedirects(...)` from per-connection `setInstanceFollowRedirects(...)`.
10. Set connect/read timeouts, clean up body/error streams, and call `disconnect` per the HTTP handler lifecycle.
11. Test cache hit/miss/no-store, cookie domains/paths/secure, redirects, concurrency, and default isolation.
12. Isolate global integration tests into separate processes; restoring state in `finally` is only post-test cleanup and does **not** solve concurrency races.
13. Do not reinstall `URLStreamHandlerFactory` / `ContentHandlerFactory` because they only support one-time installation.
14. Control proxy/authentication/redirect alongside security policy; do not relax policy to fix errors.
15. Monitor metrics: cache hit/miss/size, cookie counts, session-jar ownership, URLConnection errors, redirections, and timeouts.
16. When backward compatibility is not required, consider a modern HTTP client with appropriate explicit builder/lifecycle rather than global legacy hooks.

## Official Documentation

- [Java SE 17 — ResponseCache](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ResponseCache.html): global default, get/put callbacks, URLConnection cache flag.
- [Java SE 17 — CacheRequest](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/CacheRequest.html): getBody/abort, handling partial cache writes.
- [Java SE 17 — CacheResponse](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/CacheResponse.html): cached headers and body input stream.
- [Java SE 17 — CookieHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/CookieHandler.html): global default and cookie get/put.
- [Java SE 17 — CookieManager](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/CookieManager.html): CookieStore, CookiePolicy, cookie acceptance.
- [Java SE 17 — CookieStore](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/CookieStore.html): add/get/removeAll and scope.
- [Java SE 17 — URLConnection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLConnection.html): per-instance options, static protocol defaults, content handler factory.
- [Java SE 17 — HttpURLConnection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/HttpURLConnection.html): global/instance redirect flags, input/error streams, disconnect/persistent connections.
- [Java SE 17 — HttpClient.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Builder.html): explicit `cookieHandler`, `authenticator`, `proxy`, and `followRedirects`.
- [Java SE 17 — ProxySelector](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ProxySelector.html) and [Authenticator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Authenticator.html): system-wide routing and credentials callbacks.
- [RFC 9111 — HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111.html): freshness, validation, Vary, and private/shared caching rules.
- [RFC 6265 — HTTP State Management Mechanism](https://www.rfc-editor.org/rfc/rfc6265.html): Cookie/Set-Cookie, Domain/Path/Secure/HttpOnly, and lifetime.

**Core mindset:** `ResponseCache` and `CookieHandler` in `URLConnection` provide powerful hooks, but they are **JVM-wide when registered via `setDefault`**. Share them only when policy, users, and lifecycle truly permit; for multi-tenant/session workloads or the modern HTTP client, prefer **per-client dependencies and per-connection configuration**, and verify behavior with tests rather than relying on method names.
