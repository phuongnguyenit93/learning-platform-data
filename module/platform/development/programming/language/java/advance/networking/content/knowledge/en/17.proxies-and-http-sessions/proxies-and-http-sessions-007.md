# CookieHandler, CookieManager, CookieStore, and Cookie Acceptance Policies in Java HTTP

## 1. The Problem: HTTP Is Stateless, Yet Application Sessions Are Stateful

HTTP does not inherently force every request from the same user to carry a fixed "session". For login-based applications, the server can create a session and send a **cookie** so the client carries an identifier on subsequent requests:

```text
Java HttpClient                                HTTP Server
      |                                              |
      |--- GET /login ------------------------------>|
      |<-- 200 OK, Set-Cookie: sid=abc; Path=/ ------|
      |                                              |
      |   CookieHandler/CookieManager receives response
      |   -> CookiePolicy checks whether to accept cookie
      |   -> CookieStore stores sid                  |
      |                                              |
      |--- GET /profile; Cookie: sid=abc ----------->|
      |<-- 200 OK, profile data ----------------------|
```

There are **two distinct actions** here:

1. The server sends `Set-Cookie` to **propose that the client store a cookie** with attributes such as `Domain`, `Path`, `Secure`, `HttpOnly`, and `Max-Age`.
2. In requests to a matching URI, the client may send a `Cookie` header containing the name/value of cookies that are **permitted to be sent**.

Java provides the API group `java.net.CookieHandler`, `CookieManager`, `CookieStore`, `CookiePolicy`, and `HttpCookie`. When using `java.net.http.HttpClient` (Java 11+, e.g. Java 17), you configure a `CookieHandler` on the **HttpClient builder** so that automatic cookie sending/receiving works for the client's requests.

**Key point:** storing a cookie does not mean user authentication succeeded; a cookie may contain a **session identifier**, and the server must verify the session, access permissions, expiration, and revocation status. Most session cookies are **bearer tokens**: anyone who obtains a valid value can impersonate the session if the server has no additional defenses.

## 2. Exact Roles of the Five APIs

| API | Role | When to use |
| --- | --- | --- |
| `CookieHandler` | Abstract class to read cookies for a request (`get`) and accept cookies from a response (`put`) | Bridge between the HTTP stack and the cookie mechanism |
| `CookieManager` | Implementation of `CookieHandler`, combining a store and an acceptance policy | Default choice when you want the HTTP client to manage cookies |
| `CookieStore` | Storage to save/retrieve/remove `HttpCookie` objects | Inspect received cookies, clear sessions, or swap storage implementations |
| `CookiePolicy` | Decides **whether to accept a new cookie from a response** | `ACCEPT_ORIGINAL_SERVER`, `ACCEPT_NONE`, `ACCEPT_ALL`, or a custom policy |
| `HttpCookie` | Represents cookie name, value, and metadata (domain, path, secure, max-age, HTTP-only, etc.) | Inspecting cookies or manipulating the store explicitly |

Conceptual flow:

```text
                  OUTGOING HTTP REQUEST
                      |
                      v
            CookieHandler.get(uri, headers)
                      |
                CookieManager
                      |
              CookieStore.get(uri)
                      |
       domain/path/secure/expiry filtering
                      |
                      v
         Cookie header attached to request
                      |
                      v
                   HTTP server
                      |
             response Set-Cookie
                      |
                      v
          CookieHandler.put(uri, headers)
                      |
                CookieManager
                      |
            CookiePolicy.shouldAccept
                 /             \
             reject          accept
               |                |
              stop        CookieStore.add
```

The diagram illustrates the API concept. In the actual implementation, cookie scope checks may be performed partly in `CookieStore` and partly in `CookieManager.get`. **Do not reimplement cookie selection yourself by taking every element from `getCookies()` and concatenating them directly into a header**, as this may bypass conditions such as `Secure`, `Path`, and domain.

## 3. Initializing CookieManager for Java 17 HttpClient

Direct configuration, independent of process-wide global state:

```java
import java.net.CookieManager;
import java.net.CookiePolicy;
import java.net.http.HttpClient;

CookieManager manager =
        new CookieManager(null, CookiePolicy.ACCEPT_ORIGINAL_SERVER);

HttpClient client = HttpClient.newBuilder()
        .cookieHandler(manager)
        .build();
```

This snippet is a **code fragment** within a class/method scope with corresponding imports; it is not a standalone file. Meaning:

- The first `null` argument tells `CookieManager` to use the JDK's **default in-memory CookieStore**.
- `CookiePolicy.ACCEPT_ORIGINAL_SERVER` only accepts cookies from the original server deemed authorized to set them under the implementation's domain policy.
- `client.cookieHandler()` returns an `Optional<CookieHandler>`; if not set via the builder, the Optional can be empty.
- `HttpClient` holds a reference to the configured handler and uses it when sending/receiving HTTP, even when there are multiple connections in the connection pool. **Cookies are not a fixed property of a single TCP connection**.
- Java 17 `HttpClient` **is not `AutoCloseable`**; do not use `try (HttpClient client = ...)` with `javac --release 17`.

You can write `CookieManager manager = new CookieManager();` to use the default store and policy. In Java 17, the default accept policy is **`ACCEPT_ORIGINAL_SERVER`**, but writing the policy explicitly helps readers understand the decision.

### `CookieHandler.setDefault(...)` vs. `HttpClient.Builder.cookieHandler(...)`

Legacy APIs may use:

```java
CookieHandler.setDefault(new CookieManager());
```

This is a **system-wide** configuration designed for **HTTP URL stream protocol handlers**, such as flows based on `HttpURLConnection`. It affects other parts of the process and is not a good way to isolate cookie jars for each modern HTTP client.

With `java.net.http.HttpClient`, **configure it directly**:

```java
HttpClient client = HttpClient.newBuilder()
        .cookieHandler(manager)
        .build();
```

Do not assume that setting a global handler will automatically give every `HttpClient` instance the same cookie manager. Nor should you swap the global handler to "switch sessions" for a user in a multi-user application: doing so easily mixes state across requests.

## 4. `CookiePolicy`: Choosing Which Cookies Are **Accepted into the Store**

Java 17 defines three built-in policies:

| Policy | New cookie acceptance behavior | When appropriate |
| --- | --- | --- |
| `ACCEPT_ORIGINAL_SERVER` | Only accepts cookies considered valid for the origin under Java's domain rules | Reasonable default choice for session-managing clients |
| `ACCEPT_ALL` | Accepts all cookies that the parser/store can handle, without applying the original-server condition in the policy | Only for controlled special scenarios; not a production default |
| `ACCEPT_NONE` | Rejects all **new** cookies via `Set-Cookie` processing | Stateless clients / no cookies needed |

API:

```java
CookieManager normal = new CookieManager(
        null, CookiePolicy.ACCEPT_ORIGINAL_SERVER);

CookieManager all = new CookieManager(
        null, CookiePolicy.ACCEPT_ALL);

CookieManager none = new CookieManager(
        null, CookiePolicy.ACCEPT_NONE);
```

**Security note:** the name `ACCEPT_ORIGINAL_SERVER` in `java.net` is a cookie acceptance policy based on domain relationships supported by Java. It **is not equivalent** to modern web browsers with full `SameSite`, public-suffix list, partitioning, tracking prevention, or strict site/origin rules. The Java SE 17 documentation for `CookieManager` references the historical RFC 2965 cookie specification; applications requiring high browser-cookie compatibility must evaluate the implementation, test it, and add any necessary policies.

### Common Misconception: `ACCEPT_NONE` Does Not Automatically Clear Stored Cookies

`CookiePolicy` is used in the processing path for **newly received cookies** via `CookieManager.put(...)`. If you already have a store with valid cookies and call:

```java
manager.setCookiePolicy(CookiePolicy.ACCEPT_NONE);
```

that **blocks accepting new cookies**; it does not guarantee that old cookies disappear or immediately stop being sent. With Java 17, the demo in section 10 proves that old cookies **are still sent** after switching the policy.

If you want to clear stored cookie state:

```java
boolean changed = manager.getCookieStore().removeAll();
```

Note that `removeAll()` empties the **entire CookieStore** associated with the manager, not just cookies for one endpoint. In a multi-account/tenant application, calling this on a shared store can wipe out other users' sessions. Do not use it as a multi-user logout mechanism without state partitioning.

### `ACCEPT_ALL` Does Not Mean "Send That Cookie to Every Host"

A response from `127.0.0.1` might try to set a cookie:

```http
Set-Cookie: foreign=other; Domain=evil.example; Path=/; Max-Age=300
```

In Java 17 tests, `ACCEPT_ORIGINAL_SERVER` rejects it, while `ACCEPT_ALL` **stores** that cookie. However, having the cookie stored in the jar **does not guarantee it will be sent back to `127.0.0.1`**: the outbound path still evaluates domain/path/secure scope.

Conclusion: acceptance policy is only one part of control. Do not set `ACCEPT_ALL` for a client accessing multiple untrusted sources, as it allows the store to save unnecessary state, increasing the risk surface and session complexity.

## 5. Writing a Custom CookiePolicy for Allowed Origins

When an application **only** wants to accept session cookies from a known HTTPS host, you can combine scheme, hostname, and original-server policy restrictions:

```java
import java.net.CookieManager;
import java.net.CookiePolicy;
import java.net.URI;
import java.util.Set;

Set<String> allowedNames = Set.of("SESSION");

CookiePolicy policy = (uri, cookie) ->
        "https".equalsIgnoreCase(uri.getScheme())
        && "api.example.com".equalsIgnoreCase(uri.getHost())
        && allowedNames.contains(cookie.getName())
        && CookiePolicy.ACCEPT_ORIGINAL_SERVER
                .shouldAccept(uri, cookie);

CookieManager manager = new CookieManager(null, policy);
```

*This is a configuration code snippet; there is no runnable HTTP server/client yet.* The names/hosts here are only examples. The policy only accepts cookies named `SESSION` coming from `https://api.example.com` according to original domain matching. In production, also consider requiring cookies to have `Secure`/`HttpOnly` and a lifetime limit if they are session tokens:

```java
CookiePolicy strict = (uri, cookie) ->
        "https".equalsIgnoreCase(uri.getScheme())
        && "api.example.com".equalsIgnoreCase(uri.getHost())
        && "SESSION".equals(cookie.getName())
        && cookie.getSecure()
        && cookie.isHttpOnly()
        && CookiePolicy.ACCEPT_ORIGINAL_SERVER
                .shouldAccept(uri, cookie);
```

**But do not misunderstand:** the policy only runs when **receiving**. It does not automatically block outbound HTTP requests, prevent sending existing cookies to scope-matching URLs, prevent redirects/SSRF, or replace server-side session validation. For HTTP redirects, you must control request/target origins at the application layer; for HTTPS, you need proper trust stores and hostname verification.

If the application allows loading from multiple domains, do not write an arbitrary policy that assumes cookies from a parent domain are valid on every subdomain. An overly broad `Domain` cookie can cause unintended state sharing.

## 6. CookieStore: Where Is Data Stored and How Is It Managed?

When creating `new CookieManager(null, ...)`, the JDK uses the default **in-memory CookieStore**: cookies only exist in process memory and are **not automatically persisted to a file/DB** for use after the JVM exits.

Accessing the store:

```java
CookieStore store = manager.getCookieStore();

List<HttpCookie> allActive = store.getCookies();
List<HttpCookie> byUri =
        store.get(URI.create("https://api.example.com/account"));
List<URI> recordedUris = store.getURIs();

boolean removed = store.remove(uri, cookie);
boolean cleared = store.removeAll();
```

*Code snippet; assumes `manager`, `uri`, `cookie` are already defined along with imports for `CookieStore`, `HttpCookie`, `URI`, and `List`.*

Important methods:

| Method | Meaning |
| --- | --- |
| `add(URI, HttpCookie)` | Adds/updates a cookie in the store |
| `get(URI)` | Retrieves cookies associated with the URI, including domain conditions in the store |
| `getCookies()` | Lists **unexpired** cookies in the store |
| `getURIs()` | Lists URIs associated with cookies |
| `remove(URI, HttpCookie)` | Removes a cookie by its corresponding object/URI |
| `removeAll()` | Removes all cookies, returning a boolean indicating whether the store changed |

Oracle Java 17 states that the lists returned from `get(uri)` and `getCookies()` are **immutable**. To remove cookies, call the `remove`/`removeAll` APIs rather than modifying the list directly.

**Special warning:** `CookieStore.add(...)` is a direct storage operation. If your code manually creates and adds an `HttpCookie` to the store, that path **is not equivalent** to calling `CookieManager.put(...)` and does not automatically apply `CookiePolicy.shouldAccept(...)` to the newly added data. Do not use `store.add` with `Set-Cookie` from untrusted sources assuming `CookiePolicy` has already filtered it.

`CookieStore.get(URI)` is a storage API; when building outbound headers for HTTP, let **`CookieHandler.get(...)`** do the work, and avoid manually sending every cookie in `getCookies()`, as that will leak cookies to the wrong URIs.

### Custom CookieStore and Persistent Cookie Jars

An application can implement its own `CookieStore` to persist cookies long-term, but it must address:

- Encrypting cookie data at rest if they are session tokens, file/DB access permissions, and secret management.
- Managing `Expires`/`Max-Age` and not restoring expired cookies.
- Synchronizing read/write operations across multiple threads; do not assume every custom `CookieStore` is thread-safe.
- Verifying domain/path/secure and cookie policy at the manager layer **after reloading**; do not import cookies from unknown sources.
- Partitioning cookies by user, tenant, environment, and account; do not use a single application-wide jar.
- Handling logout, rotating session IDs, and deleting sessions on the server, not just removing them client-side.

A persistent cookie jar is not a server session database. A browser/Java client stores `sid`, while the server manages whether that cookie still has access or has been revoked.

## 7. Cookie Sending Scope: Domain, Path, Secure, HttpOnly, Max-Age

`Set-Cookie` attributes affect **whether a cookie is accepted and when it is sent**:

| Attribute | Typical meaning | Common mistake |
| --- | --- | --- |
| `Domain` | Host/domain to which the cookie can apply | Making scope too broad or accepting a domain not belonging to the origin |
| `Path` | URL path where the cookie is sent via path matching | Thinking `Path` is a strong security boundary between applications |
| `Secure` | Only send the cookie over protocols considered secure, typically HTTPS | Sending session tokens without `Secure` over HTTP |
| `HttpOnly` | In browsers, prevents JavaScript from reading via `document.cookie` | Thinking Java code cannot read `HttpCookie.getValue()` |
| `Max-Age` | Cookie lifetime in seconds | Forgetting that a cookie can still exist when the server session has expired |
| `Expires` | Expiration timestamp when supported | Not handling session expiry independently on the server |
| `SameSite` | Restricts sending cookies by site context in modern browsers | Assuming Java 17 `CookieManager` automatically has full browser `SameSite` behavior |

Example of a server setting a session cookie for HTTPS:

```http
Set-Cookie: sid=opaque-token; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=1800
```

This is a **header template for security discussion**, not runnable server code. In real products, `opaque-token` must be generated randomly so it is hard to guess; the server needs to protect, bind the lifecycle of, and validate the session. `SameSite` helps reduce some CSRF risks in browsers, but **does not replace CSRF defenses** where needed, and Java 17 `CookieManager` should not be treated as a modern browser with full `SameSite`/Partitioned/public-suffix semantics.

### 7.1. Domain: Host-Only Cookies and the Domain Attribute

When a response **has no `Domain`**, the cookie is normally treated as bound to the sending host (host-only per browser rules). When `Domain=example.com` is present, the cookie may apply to allowed subdomains according to the standard and user-agent policy.

With Java 17, `CookiePolicy.ACCEPT_ORIGINAL_SERVER` controls acceptance using the JDK's original-server/domain logic. Do not assume this policy matches the modern RFC 6265 algorithm identically. From a security standpoint, prefer the **minimal sufficient host**, avoiding letting a less-trusted subdomain set cookies for the entire parent domain.

**Ports are generally not a cookie security boundary in common models.** Two applications on the same host but different ports can share cookie domain/path scope; do not rely on different ports to isolate sessions. `HttpCookie` also has a separate historical `Port` attribute, but it should not be viewed as a substitute for application origin separation.

### 7.2. Path: When Cookies Are Sent

`Set-Cookie: scope=private; Path=/private` restricts sending by path. In the demo:

- `GET /echo` does not include the `scope` cookie.
- `GET /private/echo` includes the `scope` cookie.

`Path` is a **routing hint**, not an absolute access-control boundary; some scripts/servers on the same site can affect other paths. Authorization must live on the backend.

### 7.3. Secure: Stored, but Not Sent Over Plaintext HTTP

In the localhost HTTP demo, the server attempts to send:

```http
Set-Cookie: secureSid=secret; Path=/; Secure; Max-Age=300
```

On the tested JDK 17, the `secureSid` cookie **is stored** in `CookieStore`, but **does not appear on `http://` requests**. This is why you should not use `getCookies()` to directly decide which cookies are sent. Even so, production servers should not set auth cookies over plaintext HTTP: use HTTPS from the start, enable `Secure`, and configure appropriate HSTS for public web origins.

### 7.4. HttpOnly: Different Access Rights in the JVM

`HttpOnly` primarily prevents **JavaScript in browsers** from reading the cookie via `document.cookie`, reducing the chance of client-side scripts stealing session tokens. It **does not** make the cookie disappear from your Java backend code. `HttpCookie.isHttpOnly()` can return `true` and a Java application can still access `HttpCookie.getValue()` if it holds a reference to the cookie. Therefore, do not print tokens to logs, even if the cookie is `HttpOnly`.

### 7.5. Max-Age, Expired Cookies, and Expired Sessions

- `Max-Age=300`: requests a lifetime of about 300 seconds from when the cookie is received, according to the applicable cookie rules.
- `Max-Age=0`: typically has the effect of deleting/expiring a cookie with the same name, Domain, and Path according to user-agent rules.
- Without `Max-Age`/`Expires`: many user agents treat it as a session cookie, though actual lifetime depends on the implementation; Java's default in-memory store does not automatically persist across JVM restarts.
- `HttpCookie.hasExpired()` reports the object's expiration state; `CookieStore.getCookies()` returns unexpired cookies.

**Client-side expiration is not the entire auth system.** The server must enforce its own time limits, invalidate tokens on logout, and rotate session IDs after login/privilege changes. Simply deleting a cookie on the client does not guarantee an active session on the server is invalidated.

## 8. Cookies and HTTP Proxies/Redirects: Who Is the Real Target?

Because this topic is in the context of **Proxies and HTTP Sessions**, we must separate two layers:

```text
Java HttpClient (CookieManager)
      |
      | request URI: https://api.example.com/profile
      | Cookie policy evaluates target application URI/hostname
      v
Corporate forward proxy (possibly via HTTP CONNECT)
      |
      | route to origin per proxy policy
      v
Origin server api.example.com
```

**Cookies sent to an origin** are not the same as **proxy authentication**:

- `Cookie` carries HTTP origin state by domain/path/scheme and jar.
- `Proxy-Authorization` belongs to the proxy authentication mechanism and should not be stored as an origin cookie.
- With HTTPS over CONNECT and end-to-end TLS (no TLS interception), a normal proxy does not see HTTP `Cookie` headers inside TLS. With plaintext HTTP, an intermediate proxy can observe cookie contents.
- If a proxy intercepts/logs/modifies HTTP or performs TLS interception, the environment's trust rules change; dedicated CA management, logging, and security policies are required.

**Redirects also matter:** an initial URL may be valid, but the response leads to a different hostname. `CookieManager` will handle scope based on the requested URI, yet you should not rely on it as the sole defense against SSRF, HTTPS→HTTP downgrades, or sending credentials to another origin. The demo uses `Redirect.NEVER` to reduce variables. Production should allowlist hosts, validate targets per hop, restrict egress, and avoid multi-tenant jars.

Do not arbitrarily copy the `Cookie` header manually from request A to request B on another domain. That **bypasses the cookie jar logic** and can leak session tokens to third parties even when `CookieManager` is configured properly.

## 9. HttpCookie: Inspecting Metadata Without Leaking Secrets

Commonly used Java 17 properties:

```java
HttpCookie c = ...; // Object obtained from CookieStore or parser.

String name = c.getName();
String domain = c.getDomain();
String path = c.getPath();
boolean secure = c.getSecure();
boolean httpOnly = c.isHttpOnly();
long maxAgeSeconds = c.getMaxAge();
boolean expired = c.hasExpired();
```

*Code snippet used in a context with `HttpCookie`; not a standalone file.*

**Do not log `c.getValue()` or `c.toString()` directly**, because the value may be an authentication token and `toString()` may include the value. If metrics are needed, log attribute names and statuses (e.g., count, secure flag) after sensitivity checks. If there are multiple cookies with the same name but different domains/paths, verify the exact tuple to remove/replace; do not assume names are unique across the entire jar.

### Why Might Java's Request Cookie Header Differ from Browser Examples?

On Java 17, `HttpCookie` and `CookieManager` have historical support for RFC 2965. In some cases, the request `Cookie` header may contain components such as:

```http
Cookie: $Version="1"; sid="demo123";$Path="/";$Domain="127.0.0.1"
```

Therefore, **do not write server authentication using `cookieHeader.equals("sid=demo123")`**. A proper HTTP server must parse the cookie header according to the specification/library, verify a random session ID and backend session store, and not trust a simple `contains("sid=")` check. The demo uses `contains` **only to illustrate the presence of the cookie**, not as an example of a parser or secure authorization.

## 10. Complete Java 17 Program: Testing CookieManager and the Three Policies

The following local program creates an HTTP server on loopback and `HttpClient` instances with separate cookie jars. It uses **HTTP without TLS only in this test**, specifically to verify that `Secure` **is not sent over HTTP**.

Main branches:

1. `/login` returns `Set-Cookie: sid=demo123; Path=/; HttpOnly; Max-Age=300`.
2. `/secure` returns `Set-Cookie: secureSid=secret; Path=/; Secure`.
3. `/scope` returns `Set-Cookie: scope=private; Path=/private`.
4. `/foreign` attempts to set a cookie with `Domain=evil.example` even though the response comes from `127.0.0.1`.
5. `/echo` and `/private/echo` check for the **presence** of cookie names in the request; the result prints booleans without logging values.
6. Uses three independent `CookieManager` instances for `ACCEPT_ORIGINAL_SERVER`, `ACCEPT_ALL`, and `ACCEPT_NONE`.
7. Tests switching the policy after cookies have been stored, then clears the entire jar with `CookieStore.removeAll()`.

**File: `CookieManagerDemo.java`**

```java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.CookieManager;
import java.net.CookiePolicy;
import java.net.HttpCookie;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public final class CookieManagerDemo {
    static void respond(HttpExchange exchange, String body)
            throws IOException {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        try (exchange) {
            exchange.getResponseHeaders().set("Content-Type",
                    "text/plain; charset=UTF-8");
            exchange.sendResponseHeaders(200, bytes.length);
            exchange.getResponseBody().write(bytes);
        }
    }

    static void echo(HttpExchange exchange) throws IOException {
        String cookie = exchange.getRequestHeaders().getFirst("Cookie");
        String value = cookie == null ? "" : cookie;
        respond(exchange, "sid=" + value.contains("sid=")
                + ", secureSid=" + value.contains("secureSid=")
                + ", scope=" + value.contains("scope="));
    }

    static HttpClient newClient(CookieManager manager) {
        return HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_1_1)
                .cookieHandler(manager)
                .followRedirects(HttpClient.Redirect.NEVER)
                .connectTimeout(Duration.ofSeconds(3))
                .build();
    }

    static String get(HttpClient client, URI root, String path)
            throws IOException, InterruptedException {
        HttpRequest request = HttpRequest.newBuilder(root.resolve(path))
                .timeout(Duration.ofSeconds(5))
                .GET()
                .build();
        HttpResponse<String> response = client.send(request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));
        if (response.statusCode() != 200) {
            throw new IOException("Unexpected HTTP status");
        }
        return response.body();
    }

    static boolean hasCookie(CookieManager manager, String name) {
        return manager.getCookieStore().getCookies().stream()
                .anyMatch(c -> c.getName().equals(name));
    }

    static boolean isHttpOnly(CookieManager manager, String name) {
        return manager.getCookieStore().getCookies().stream()
                .filter(c -> c.getName().equals(name))
                .findFirst().map(HttpCookie::isHttpOnly).orElse(false);
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/login", exchange -> {
            exchange.getResponseHeaders().add("Set-Cookie",
                    "sid=demo123; Path=/; HttpOnly; Max-Age=300");
            respond(exchange, "OK");
        });
        server.createContext("/secure", exchange -> {
            exchange.getResponseHeaders().add("Set-Cookie",
                    "secureSid=secret; Path=/; Secure; Max-Age=300");
            respond(exchange, "OK");
        });
        server.createContext("/scope", exchange -> {
            exchange.getResponseHeaders().add("Set-Cookie",
                    "scope=private; Path=/private; Max-Age=300");
            respond(exchange, "OK");
        });
        server.createContext("/foreign", exchange -> {
            exchange.getResponseHeaders().add("Set-Cookie",
                    "foreign=other; Domain=evil.example; Path=/; Max-Age=300");
            respond(exchange, "OK");
        });
        server.createContext("/echo", CookieManagerDemo::echo);
        server.createContext("/private/echo", CookieManagerDemo::echo);
        server.start();
        try {
            URI root = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/");
            CookieManager manager = new CookieManager(null,
                    CookiePolicy.ACCEPT_ORIGINAL_SERVER);
            HttpClient client = newClient(manager);

            System.out.println("before: "
                    + get(client, root, "/echo"));
            get(client, root, "/login");
            System.out.println("after login: "
                    + get(client, root, "/echo"));
            System.out.println("stored HttpOnly: "
                    + isHttpOnly(manager, "sid"));
            get(client, root, "/secure");
            get(client, root, "/scope");
            System.out.println("stored Secure: "
                    + hasCookie(manager, "secureSid"));
            System.out.println("public path: "
                    + get(client, root, "/echo"));
            System.out.println("private path: "
                    + get(client, root, "/private/echo"));
            get(client, root, "/foreign");
            System.out.println("original policy foreign: "
                    + hasCookie(manager, "foreign"));

            CookieManager acceptAll = new CookieManager(null,
                    CookiePolicy.ACCEPT_ALL);
            get(newClient(acceptAll), root, "/foreign");
            System.out.println("accept-all foreign stored: "
                    + hasCookie(acceptAll, "foreign"));

            CookieManager none = new CookieManager(null,
                    CookiePolicy.ACCEPT_NONE);
            HttpClient noneClient = newClient(none);
            get(noneClient, root, "/login");
            System.out.println("accept-none count: "
                    + none.getCookieStore().getCookies().size());
            System.out.println("accept-none echo: "
                    + get(noneClient, root, "/echo"));

            manager.setCookiePolicy(CookiePolicy.ACCEPT_NONE);
            System.out.println("switch policy: "
                    + get(client, root, "/echo"));
            System.out.println("removeAll: "
                    + manager.getCookieStore().removeAll());
            System.out.println("after clear: "
                    + get(client, root, "/echo"));
        } finally {
            server.stop(0);
        }
    }
}
```

Compile/run with JDK 17 (the `jdk.httpserver` module provides the local HTTP server):

```bash
javac --release 17 --add-modules jdk.httpserver CookieManagerDemo.java
java --add-modules jdk.httpserver CookieManagerDemo
```

**Actual verified stdout**:

```text
before: sid=false, secureSid=false, scope=false
after login: sid=true, secureSid=false, scope=false
stored HttpOnly: true
stored Secure: true
public path: sid=true, secureSid=false, scope=false
private path: sid=true, secureSid=false, scope=true
original policy foreign: false
accept-all foreign stored: true
accept-none count: 0
accept-none echo: sid=false, secureSid=false, scope=false
switch policy: sid=true, secureSid=false, scope=false
removeAll: true
after clear: sid=false, secureSid=false, scope=false
```

### 10.1. Interpreting the Results

- **Before login:** there is no `sid` yet, so the server sees no session cookie.
- **After login:** `CookieManager` accepts and stores `sid`; subsequent requests automatically include the appropriate `Cookie` header.
- **Stored HttpOnly true:** Java can still observe the `HttpOnly` metadata, even though browser JavaScript has restricted access.
- **Stored Secure true, yet public path secureSid=false:** the `Secure` cookie is stored, but **not sent over plaintext HTTP**.
- **Private path scope=true:** the cookie set with `Path=/private` is sent to `/private/echo`, not to `/echo`.
- **Original policy foreign=false:** `ACCEPT_ORIGINAL_SERVER` rejects the cookie self-declaring `Domain=evil.example` from the localhost response.
- **Accept-all foreign stored=true:** `ACCEPT_ALL` puts that cookie into the store; this **does not prove** it can be sent to another host.
- **Accept-none count=0:** the separate manager using `ACCEPT_NONE` does not store the new `Set-Cookie` from `/login`.
- **Switch policy still sid=true:** changing the policy after cookies are already stored **does not delete or block sending old cookies**. Therefore, do not use `ACCEPT_NONE` as a logout command.
- **RemoveAll true and after clear sid=false:** `CookieStore.removeAll()` clears the manager's jar; subsequent requests do not send old cookies. The server session may still be alive; true logout requires a request/server-side invalidation.

### 10.2. Intentional Limitations of the Demo

This is a **protocol test**, not a production authentication system:

- Uses localhost HTTP to observe `Secure` filtering; **do not use plaintext HTTP to transmit real session tokens**.
- Uses a constant session ID `demo123` and the server only checks the cookie string; **this is not a secure auth mechanism**. Production requires a standard cookie parser, secret session IDs, a session store, expiry, CSRF controls, and authorization.
- Uses `value.contains("sid=")` to show presence in the demo; this string check **does not prove a valid cookie**, does not properly handle duplicate names/escaping, and must not be used to grant permissions.
- `CookieManager` and the in-memory `CookieStore` are for testing only; there is no cookie persistence after JVM shutdown and no automatic user-level partitioning.
- `CookiePolicy.ACCEPT_ALL` is an intentional branch illustrating risk; do not configure this as the default for production clients.
- The server does not use HTTPS/certificates; do not run this demo publicly on the Internet and do not use `Set-Cookie: sid=demo123` for real accounts.
- `Max-Age=300` keeps cookies long enough for testing; if steps are run with very large time gaps, expiry results will depend on timing.

## 11. Logout: Clearing Client Cookies and Invalidating Server Sessions Are Two Different Things

Suppose the server creates a session ID on login:

```text
session "abc":
  userId = 100
  expiresAt = ...
  revoked = false
```

The client stores the token as a cookie. On logout:

1. The server **revokes the session ID** or invalidates the corresponding token.
2. The server can send a `Set-Cookie` to delete the cookie, with the same name/domain/path as the old cookie and `Max-Age=0`.
3. The client can remove the cookie from the jar (via application policy or store API) if needed.
4. Do not treat the client merely deleting the cookie as proof that the server session has lost access; a previously copied token can still be used until the server revokes or expires it.
5. If a `CookieStore` is shared across multiple profiles/tenants, deleting everything can break remaining sessions. **Partition by principal** instead of clearing a global jar.

Cookies also do not replace transport security: HTTPS encryption, XSS protection, CSRF, session fixation, token rotation, auditing, and rate limits remain important.

## 12. Creating a Cookie Manually: Possible, but Mind the Scope

In test scenarios or systems building a custom cookie store:

```java
import java.net.HttpCookie;
import java.net.URI;

HttpCookie theme = new HttpCookie("theme", "dark");
theme.setPath("/");
theme.setMaxAge(3600);
manager.getCookieStore().add(
        URI.create("https://example.com"), theme);
```

*Code snippet; assumes `manager` is already initialized.* You must understand:

- Adding directly via `CookieStore.add` **is not** an HTTP response reception operation and may not go through `CookiePolicy`.
- Java `HttpCookie` creates cookies with the API's conventions/versions and does not guarantee every header matches modern browser behavior.
- Before sending, the `CookieHandler.get` path still processes attributes and URIs; do not manually grab `theme` from every URL and add it to requests.
- Do not manually construct cookies with predictable session ID strings or store plaintext credentials long-term.
- If you want to test cookies with `Secure`/`HttpOnly`, setters `setSecure(true)` and `setHttpOnly(true)` exist, but they do not replace HTTPS or server-side authentication.

## 13. Designing a Cookie Jar for Multi-User or Multi-Environment Applications

A serious architectural mistake is using **a singleton CookieManager** for different users/tenants:

```text
Client A (user Alice) --\
                         -> Shared CookieStore -> sid=Alice or sid=Bob
Client B (user Bob) ----/
```

If both log in to the same host/path, the new cookie can overwrite the old one; Alice's requests risk running with Bob's session or vice versa. Domain/path policies do not solve **tenant isolation**, because each legitimate user shares the same origin.

Strategy:

- Dedicate one `CookieManager`/`CookieStore` per **session context** or use a clear partitioning structure.
- Do not create a new `CookieManager` for **every request** in the same session, as cookies set on previous requests will be lost.
- Reuse `HttpClient` within the same session when appropriate to leverage connection pooling, but consider separating lifecycles/secrets across tenants.
- For service-to-service auth, consider standard application-protocol token/header mechanisms instead of silently sharing a cookie jar.
- Avoid storing cookies containing session tokens in unprotected logs, traces, or crash dumps.
- If persistence is needed, encrypt and set a TTL; when a user logs out or is disabled, clear the store and revoke server-side.
- If the client uses proxies/redirects, revalidate destinations before letting the cookie jar send state to another origin.

Do not let a cookie jar bypass access control: one user must never be able to see another user's cookie data through logs or admin APIs.

## 14. Differences from Browsers: SameSite, CORS, XSS, and CSRF

When carrying cookie knowledge from browsers over to a Java HTTP client, four confusions are common:

**(1) `HttpOnly` does not lock out Java applications:** browser JS is restricted from accessing `document.cookie`, but a Java server-side process can read `HttpCookie.getValue()` if the code holds the cookie.

**(2) `SameSite` is a browser/site policy:** Java SE 17 `CookieManager` should not be assumed by default to implement full `SameSite` algorithms, cookie partitioning, and current browser policy behavior. If a server relies on `SameSite` to mitigate CSRF for browsers, that is a property of browser user agents and **does not happen identically in a custom Java client**.

**(3) CORS is not Java HttpClient's request-sending permission:** CORS is a browser mechanism controlling whether scripts can read cross-origin responses. A Java service can send requests according to its own network policy. Therefore, use `CookiePolicy` and address/redirect allowlists at the backend layer rather than relying on CORS.

**(4) Path/Domain do not replace authorization:** a cookie within scope can be accepted by the server, yet the server must still authenticate the user and check permissions for each resource. A server vulnerable to SSRF or trusting the wrong domain can send or receive unintended cookies.

Applications handling sensitive data should be tested with both real browsers and Java clients if both types of agents are used; they may handle cookie attributes differently.

## 15. Common Mistakes and How to Fix Them

| Mistake | Consequence | Correct approach |
| --- | --- | --- |
| Creating `HttpClient` without configuring a cookie handler while expecting session persistence | `Set-Cookie` responses are not managed through the expected jar | Use `builder.cookieHandler(manager)` |
| Setting `CookieHandler.setDefault` and assuming every `HttpClient` uses it automatically | Global and client-specific management get confused | Configure each `HttpClient` explicitly |
| Confusing `CookiePolicy` with storage | Thinking `ACCEPT_NONE` deletes cookies | `CookiePolicy` filters new incoming cookies; `CookieStore.removeAll` clears old state |
| Using `ACCEPT_ALL` for all sources | Accepting cookies from another host that self-declares a domain | Use original-server or a stricter policy |
| Assuming cookies in `getCookies()` are always sent to every URI | Leaking cookies if headers are attached manually | Let `CookieManager` filter outbound cookies by URI |
| Not restricting domain/path when designing auth cookies | Cookies are shared too broadly | Use the narrowest necessary scope |
| Sending session tokens over HTTP without TLS | Eavesdropping, spoofing | HTTPS + `Secure`; protect certs/hostnames |
| Thinking `HttpOnly` prevents Java from reading cookies | Secret leakage when logging `getValue`/`toString` | Do not log values |
| Seeing `isHttpOnly()==true` and skipping CSRF/XSS/authorization | Missing defense layers | Server-side auth + appropriate web defenses |
| Using `SameSite` as a reason to trust Java `CookieManager` as a browser | Wrong policy assumptions | Test/configure per user-agent type |
| Using one jar across a multi-tenant application | Mixing sessions of multiple users | Partition by session/user |
| Logging out by only calling `removeAll()` | Server session may still remain valid | Revoke the session on the server |
| Relying on ports to isolate cookies | Host/domain/path may share scope | Separate hostnames/jars and access permissions |
| Believing cookie sessions mean keeping the same TCP connection | Depends on connection pool, retries/redirects differ | Cookies live in the client store, not the socket |
| Manually setting raw `Cookie` headers bypassing the jar | Easy to send to the wrong origin/path | Use `CookieManager` |
| Not controlling redirects through proxies | Can send state to the wrong destination or cause SSRF | Allowlist hosts and revalidate redirects |
| Ignoring expiry/`Max-Age`, relying only on cookie existence | Stale sessions or replay | TTL on both client and server; invalidation |
| Manually adding cookies to `CookieStore` from untrusted sources | Bypasses acceptance policy | Receive via `CookieManager.put` and validate |
| Using `HttpCookie.toString()` for logging | Can leak tokens | Only log non-sensitive names/metadata |

## 16. Practical Checklist When Integrating with Proxies and HTTP Sessions

1. Decide whether cookies are needed. If a service is stateless or uses independent bearer tokens, you may not need a cookie manager.
2. If cookies are needed, create `CookieManager(null, CookiePolicy.ACCEPT_ORIGINAL_SERVER)` or a more restrictive policy.
3. Attach via `HttpClient.newBuilder().cookieHandler(manager)`; do not rely on the global default.
4. Define the **session unit**: one manager per user/session context, never shared across tenants.
5. Use HTTPS for real sessions, have the server enable `Secure`/`HttpOnly`, minimize Domain/Path scope, and set an appropriate TTL.
6. Check redirects/`ProxySelector`: which URI is actually being requested, which hops can observe cookies, and whether any TLS downgrade occurs.
7. Observe `Set-Cookie` responses using controlled HTTP debugging without printing session values.
8. When debugging "cookie not sent", check URL scheme, host, path, `Secure` flag, expiry, policy, attached cookie handler, and cookie name/Domain.
9. On logout, revoke the session server-side and clear cookies within the proper scope without wiping other users' jars.
10. If cookies must persist across restarts, design a persistent `CookieStore` with encryption, locking, expiry, partitioning, and testing.
11. Test not only the happy path: wrong domain, different Path, HTTP/HTTPS, expired, `ACCEPT_NONE`, `ACCEPT_ALL`, and shared cookie jars.
12. For modern browser-like cookie requirements, evaluate Java 17 implementation limits and add appropriate policies or HTTP clients.

## 17. Exercises and Answers

**Exercise 1.** Why is `CookieManager` not just a `CookieStore`? Point out the role of `CookiePolicy` in the response-receiving path.

**Exercise 2.** A client already has `sid` stored in `CookieStore`. Later it calls `manager.setCookiePolicy(ACCEPT_NONE)`. Is it guaranteed to stop sending `sid`? What needs to be done to stop using old state?

**Exercise 3.** Server `api.example.com` returns `Set-Cookie: sid=...; Path=/; Secure; HttpOnly`. Should a request to `http://api.example.com` send `sid`? Can Java code read the `HttpOnly` value?

**Exercise 4.** A cookie has `Path=/private`. Why does the server receive the cookie at `/private/profile` but not at `/public`? Can `Path` be used instead of authorization?

**Exercise 5.** Two users both access `https://service.example.com`, but the application lets them share the same `CookieManager`. Why is this a security bug even with `ACCEPT_ORIGINAL_SERVER` enabled?

**Exercise 6.** A client uses a proxy to reach an HTTPS origin. Do `Cookie` and `Proxy-Authorization` mean the same thing? Does the cookie belong to the proxy scope or the origin scope?

**Exercise 7.** `ACCEPT_ALL` stores a cookie declaring `Domain=evil.example` sent from localhost. Does that mean the cookie will be sent back to localhost? How can you verify what is actually sent?

**Exercise 8.** A user logs out and the client calls `getCookieStore().removeAll()`. Is the server guaranteed to have invalidated the session ID? What process is required?

**Exercise 9.** Why should you not manually take `getCookies()` and build a `Cookie` header for every request?

**Exercise 10.** Browsers automatically enforce `SameSite` for a cookie. Can you assume Java 17 `CookieManager` also automatically enforces all the same rules when making cross-origin API calls?

**Suggested answers:**

1. `CookieManager` is a `CookieHandler` coordinating **policy + store**. `CookiePolicy.shouldAccept` decides whether a cookie from a response is stored; `CookieStore` stores/returns/removes cookies.
2. No. The policy filters new cookies; old cookies can still be sent. You must remove them from `CookieStore`/switch jars, and also log out via server-side invalidation.
3. Do not send `Secure` cookies over plaintext HTTP. Java code can read `HttpCookie.getValue()` despite `HttpOnly`; do not log it.
4. Path matching. However, `Path` is not an authorization boundary; the server must still authenticate and authorize.
5. Cookies from user B can overwrite/mix with user A's state because they share the same origin. `CookieManager`/Store must be partitioned by user/session.
6. No. `Proxy-Authorization` authenticates with the proxy; application cookies belong to the origin URI and must obey scope. With HTTPS CONNECT, a normal proxy cannot see cookies inside TLS.
7. No. It only proves acceptance into the store; you must observe the outbound request or `CookieHandler.get(...)` by URI to know what is actually sent.
8. No. You must invalidate the session ID/token on the server and send `Set-Cookie` expiry/clear according to policy.
9. Because it lacks Domain/Path/Secure/expiry filtering and easily sends tokens to the wrong destination. Let `CookieHandler` manage it.
10. No. Java 17 `CookieManager` should not be treated as a modern browser engine with full `SameSite`/partitioning/PSL support.

## Official References

- [Java SE 17 — CookieHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/CookieHandler.html): `get`, `put`, global default handler.
- [Java SE 17 — CookieManager](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/CookieManager.html): combining store and policy, default in-memory store, acceptance mechanism.
- [Java SE 17 — CookiePolicy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/CookiePolicy.html): `ACCEPT_ALL`, `ACCEPT_NONE`, `ACCEPT_ORIGINAL_SERVER`, `shouldAccept`.
- [Java SE 17 — CookieStore](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/CookieStore.html): `add`, `get`, `getCookies`, `remove`, `removeAll`.
- [Java SE 17 — HttpCookie](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/HttpCookie.html): Domain, Path, Secure, HttpOnly, Max-Age, and expiry.
- [Java SE 17 — HttpClient.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Builder.html): `cookieHandler(CookieHandler)`, redirect/proxy.
- [Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): `cookieHandler()` returning Optional, HTTP requests/responses.
- [Java SE 17 — HttpServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): loopback HTTP server in the test.
- [RFC 6265 — HTTP State Management Mechanism](https://www.rfc-editor.org/rfc/rfc6265.html): Set-Cookie/Cookie model, Domain, Path, Secure; distinguish from Java's implementation based on historical specifications.
