# Path Prefix Matching Rules and Case Sensitivity — HttpServer (Java 17+)

**`HttpServer` in Java 17 finds the `HttpContext` whose path is the longest matching literal prefix of the URI path.** The matching is **case-sensitive** and **does not automatically convert to/from percent-encoded form** when selecting a context. Consequence: `"/api"` can also match `"/apiX"`, while `"/api/admin/"` does not match `"/api/Admin/"`. This is the routing rule of the `com.sun.net.httpserver` API, **not** a REST router with path variables, method constraints, or automatic authorization.

Being off by a single character, a `/` slash, or a canonicalization step can cause a request to fall into a different context, which is especially dangerous when a parent context is public while a child context requires authentication. This lesson belongs to the **JDK HTTP Server** group of **Java Advance - networking**, guiding you through the longest-prefix matching mechanism, path boundaries, case sensitivity, raw/decoded URIs, safe guard patterns, and two Java 17+ programs tested over real loopback HTTP.

## 1. Related APIs and Exact Scope

The `jdk.httpserver` module exports the classes `HttpServer`, `HttpsServer`, `HttpContext`, `HttpHandler`, `HttpExchange`, `Filter`, and `Authenticator`. You register a context with:

```java
// Illustrative snippet: server and handler have already been created.
HttpContext ctx = server.createContext("/api/", handler);
```

`HttpServer` receives a request, selects a **context path**, and then calls `HttpHandler.handle(HttpExchange)`. `HttpExchange.getHttpContext()` returns the context actually selected; `getRequestURI()` returns the request URI. A context can have its own filters and authenticator attached. `HttpsServer` adds TLS but does not eliminate the need to design routing and application authorization.

Separate **three concepts**:

1. **Context selection** performed by the JDK: finds the longest literal path prefix.
2. **Route resolution** performed by the application or framework: checks HTTP method, path segments, path parameters, and query/header constraints.
3. **Authorization** performed by the security/business layer: what the principal is allowed to do with a specific resource.

A correct context match only proves that a handler was invoked; it does **not** prove that the user is authorized to read, modify, or delete the resource.

## 2. Longest Matching Prefix: The Primary Selection Rule

Example of registered contexts:

```text
"/"             -> ROOT
"/apps/"        -> APPS
"/apps/foo/"    -> FOO
```

Selection table according to the Java 17 API:

| URI path | Selected context | Why |
| --- | --- | --- |
| `/apps/foo/bar` | `/apps/foo/` | Longest matching prefix |
| `/apps/app1` | `/apps/` | `/apps/foo/` does not match |
| `/apps/Foo/bar` | `/apps/` | Uppercase `F` differs from `f` |
| `/Apps/foo/bar` | `/` | Does not match lowercase `/apps/` |
| `/other` | `/` | Root prefix catch-all |
| `/apps` | `/` | `/apps/` has a trailing slash, does not match `/apps` |

**The order of `createContext()` calls does not create first-match priority.** If two contexts both match, the longer prefix is chosen. Do not use registration order as an override or authorization mechanism. Two contexts with the same path cannot be registered redundantly on the same server.

If there is **no** root context `"/"`, a request that matches no context may receive HTTP 404 from the server; the real example in section 12 confirms this behavior on the JDK.

## 3. Literal Prefix Is Not a Path-Segment Prefix

A string `a` is a prefix of the string `ab` even though the two words have different meanings. For URL paths, this leads to prefix collision:

| Context | Request path | Result on Java 17 |
| --- | --- | --- |
| `/foo` | `/foo` | Match |
| `/foo` | `/foo/bar` | Match |
| `/foo` | `/foobar` | **Match** |
| `/v1` | `/v123` | **Match** |
| `/admin` | `/administrator` | **Match** |
| `/users` | `/users-backup` | **Match** |
| `/users/` | `/users-backup` | No match |
| `/users/` | `/users/42` | Match |

To identify the `/users` root and its true descendants, an application can use:

```java
// Snippet: path has been checked according to the canonical policy.
boolean inside = "/users".equals(path)
        || path.startsWith("/users/");
```

This is better than `path.startsWith("/users")` with respect to **segment boundaries**, but it **still does not automatically solve percent-encoding, non-canonical slashes, dot segments, or authorization**. Context selection is only the initial step; the handler needs additional guards.

## 4. Trailing Slash: One Character Changes the Route

With two contexts:

```java
// Snippet: both handlers exist, server has not started yet.
server.createContext("/api", apiRootHandler);
server.createContext("/api/", apiChildrenHandler);
```

- `/api` goes to `/api`.
- `/api/` goes to `/api/` because the prefix is longer.
- `/api/items` goes to `/api/`.
- `/apiX` still goes to `/api` **if the handler does not reject it**.

Registering **only** `"/api/"` does not automatically catch `"/api"`. You need to decide whether the API accepts both, returns 404 for the bare path, or redirects according to clear semantics. For POST/PUT requests with side effects, redirects must preserve method/body and consider idempotency; do not follow them arbitrarily.

The Java 17 Javadoc advises that context paths in general **should** end with `/`, because `"/foo"` will also match `"/foobar"`. However, adding a slash is **not an authorization mechanism**: `/api/private/../public` still looks like it is under `/api/` in terms of prefix if input has not been processed at another layer.

## 5. Case Sensitivity: `admin` Differs from `Admin`

Example:

```text
Context:
   /api/
   /api/admin/

Request                        Selected context
/api/admin/status              /api/admin/
/api/Admin/status              /api/
/API/admin/status              no match (if / is absent)
```

**Security risk:** if `/api/admin/` has an authentication filter, while `/api/` is a generic handler that might lowercase the path on its own, a request to `/api/Admin/status` can slip into a processing branch that is not properly protected. Never assume "looks like the admin name" means it has passed through the admin context's filter.

To prevent this, use consistent canonical route rules and check authorization **per resource/operation**, rather than relying solely on JDK context selection. For routes with wrong casing, you can return an explicit 404 instead of silently converting to lowercase.

Do not lowercase the entire URI path out of habit. Object keys, file names, URL resources, Unicode identifiers, and storage lookups can be **case-sensitive**, while some proxies have different behaviors. Path normalization must be a **consistent contract of the application**.

## 6. Root Fallback and 404 Are Not the Same

`createContext("/", handler)` becomes a **very broad fallback** because almost all HTTP request paths start with `/`. If you add a root context, requests like `/unknown` or `/API/foo` can enter the root handler instead of being returned 404 by the core server.

```java
// Snippet: root fallback requires a clear policy.
server.createContext("/", fallback);
server.createContext("/api/", api);
server.createContext("/api/admin/", admin);
```

An SPA frontend may want the root fallback to return the HTML index for UI pages, but it **should not return HTTP 200 HTML for every non-existent API path**. Do not let the root handler route to private data using lowercased/decoded strings without proper authorization.

A useful log set should distinguish 404 due to **no matching context**, 404 due to **handler rejecting the path shape**, 404 due to **resource not found**, and 403 due to **insufficient permissions**. They are all HTTP statuses, yet they have different investigation causes.

## 7. URI Path, Query, and HTTP Method Are Separate Layers

Request:

```text
GET /api/item?sort=asc&page=2 HTTP/1.1
       ^^^^^^^^^
       URI path
                ^^^^^^^^^^^^^^^
                   URI query
```

`HttpServer` selects the context from the **URI path**, not from the query string. `/api/item?sort=asc` and `/api/item?sort=desc` match the same prefix. `GET /api/item` and `POST /api/item` can be sent to **the same handler**, because `createContext` is not a method-aware router.

You must manually check `exchange.getRequestMethod()`, `exchange.getRequestURI().getRawQuery()`/`getQuery()` according to contract, along with headers/content-type, and return status 405 when the method is unsupported.

Also do not confuse header names (HTTP header field names are case-insensitive) with URI paths: **paths have case-sensitive semantics in Java 17 `HttpServer`**. `Host` or `X-Forwarded-Host` is not part of the context-prefix selection algorithm; if the app distinguishes tenants via host, you must design separate trusted-proxy/virtual-host validation.

## 8. Context Registration: Order Is Not a Correctness Condition

Both of the following must produce the same longest-prefix result:

```java
// Order A
server.createContext("/api/admin/", admin);
server.createContext("/api/", api);
```

```java
// Order B on another HttpServer
server.createContext("/api/", api);
server.createContext("/api/admin/", admin);
```

The request `/api/admin/users` still enters the `/api/admin/` context. An exact duplicate path cannot be registered twice on the same server as a way to overwrite: the API may throw `IllegalArgumentException`. If you need to swap routes or deployment versions, manage the lifecycle and in-flight exchanges explicitly; `removeContext` does not retroactively cancel exchanges already being processed.

When you need to know which context the server selected, read `exchange.getHttpContext().getPath()` instead of guessing from the request path or registration order. That is an important QA tool in demo 1.

## 9. Raw Path and Decoded Path Can Differ

`HttpExchange.getRequestURI()` returns `java.net.URI`, in which:

- `URI.getRawPath()` preserves the percent-encoded representation.
- `URI.getPath()` returns the path with escape sequences decoded according to the API.

Example:

```text
Request-target: /docs/%61dmin
getRawPath():   /docs/%61dmin
getPath():      /docs/admin
```

The data in the two strings is not identical. A system can use the raw form to check canonical spelling, and then parse the resource ID after a well-defined single decode step. **Do not decode twice**; strings such as `%252e` can change meaning across multiple decode layers, leading to discrepancies with a WAF/proxy.

**The Java 17 `HttpServer` documentation specifies that literal path matching does not automatically convert encoded forms.** However, business routing and authz must still have their own policy for encoded paths, rather than assuming that a request routed to the right context contains no encoded aliases.

## 10. Percent-Encoded Slash, Dot Segments, and Path Traversal

Inputs must have a clear policy:

| Path form | Security question |
| --- | --- |
| `/docs/admin` | Is this the canonical business resource? |
| `/docs/%61dmin` | Are encoded aliases allowed or rejected? |
| `/docs/%2Fprivate` | After decoding `/`, does it create a new segment? |
| `/docs/%2e%2e/secret` | Does encoded `..` lead to traversal in a downstream layer? |
| `/docs/../admin` | Does a proxy or URI normalization alter the path? |
| `/docs//item` | Are repeated slashes collapsed or preserved? |
| `/docs/%252e%252e` | Does double encoding cause double decoding? |
| `/Docs/item` | Does casing differ from the canonical route? |
| `/docs/ITEM` | Is the resource ID case-sensitive? |

**There is no single automatic lowercase/normalize/URL-decode operation that is safe for every application.** If an API only uses ASCII slugs, rejecting percent-encoding/Unicode/multiple segments can be an easy-to-verify policy. However, **you should not globally ban percent-encoding** in APIs that require international user names or valid URLs containing Unicode; in that case, a consistent canonicalization/validation convention from proxy to backend is needed.

When turning a URI path into a real filesystem path, you must also use filesystem containment checks, canonical paths, symlink policies, and per-file authorization. `String.startsWith` on a raw URL path is **not** a sufficient measure to prevent accessing files outside the root directory.

## 11. Segment-Boundary Guard with a Concrete Policy

If the context is `"/docs"`, the handler can receive `/docs-public`. Minimum check:

```java
// Snippet inside handler, uri obtained from getRequestURI().
String rawPath = uri.getRawPath();
boolean isDocs = "/docs".equals(rawPath)
        || rawPath.startsWith("/docs/");
if (!isDocs) {
    // 404/403 per policy, remember to close exchange.
}
```

This condition eliminates prefix collisions but still allows nested paths, encoded aliases, and dot segments. For the requirement "accept only root or exactly **one lowercase ASCII slug**", use:

```java
boolean accepted = "/docs".equals(rawPath)
        || rawPath.matches("/docs/[a-z0-9-]+");
```

This regex **is an illustrative application requirement, not a Java rule**. It intentionally rejects `/docs/a/b` and `/docs/%61dmin`. If the app needs Unicode or nested paths, replace it with a properly designed parser and normalization; **never** skip authorization just because a regex matched.

## 12. Java 17 Runnable Demo 1: Longest Prefix and Case Sensitivity in Practice

The file **`PathPrefixRoutingDemo.java`** contains a standalone program using only the JDK. The HTTP server binds to IPv4 loopback `127.0.0.1` and an ephemeral port. It registers 5 contexts:

```text
/api           -> BASE
/api/          -> SECTION
/api/admin/    -> ADMIN
/Api/          -> CAPITAL
/v1            -> VERSION
```

Each handler writes `LABEL@selected-context-path` using `exchange.getHttpContext().getPath()`. The client sends **10 real HTTP requests**, not just an in-memory `String.startsWith` test.

```java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class PathPrefixRoutingDemo {
    private static void respond(HttpExchange exchange, String label)
            throws IOException {
        try (exchange) {
            String body = label + "@" + exchange.getHttpContext().getPath();
            byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=UTF-8");
            exchange.sendResponseHeaders(200, bytes.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(bytes);
            }
        }
    }

    private static void test(HttpClient client, String base, String path)
            throws Exception {
        HttpRequest request = HttpRequest.newBuilder(
                URI.create(base + path))
                .timeout(Duration.ofSeconds(5)).GET().build();
        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString());
        String result = response.statusCode() == 404
                ? "NO_CONTEXT" : response.body();
        System.out.println(path + " => "
                + response.statusCode() + "/" + result);
    }

    public static void main(String[] args) throws Exception {
        InetAddress local = InetAddress.getByAddress(
                new byte[]{127, 0, 0, 1});
        HttpServer server = HttpServer.create(
                new InetSocketAddress(local, 0), 0);
        ExecutorService workers = Executors.newFixedThreadPool(3);
        server.createContext("/api",
                exchange -> respond(exchange, "BASE"));
        server.createContext("/api/",
                exchange -> respond(exchange, "SECTION"));
        server.createContext("/api/admin/",
                exchange -> respond(exchange, "ADMIN"));
        server.createContext("/Api/",
                exchange -> respond(exchange, "CAPITAL"));
        server.createContext("/v1",
                exchange -> respond(exchange, "VERSION"));
        server.setExecutor(workers);
        server.start();
        try {
            HttpClient client = HttpClient.newHttpClient();
            String base = "http://127.0.0.1:"
                    + server.getAddress().getPort();
            test(client, base, "/api");
            test(client, base, "/apiX");
            test(client, base, "/api/");
            test(client, base, "/api/items");
            test(client, base, "/api/admin/status");
            test(client, base, "/api/Admin/status");
            test(client, base, "/Api/items");
            test(client, base, "/API/items");
            test(client, base, "/v123");
            test(client, base, "/api/item?sort=asc");
        } finally {
            server.stop(0);
            workers.shutdownNow();
        }
    }
}
```

Compile/run with Java 17+:

```sh
javac --release 17 --add-modules jdk.httpserver -encoding UTF-8 PathPrefixRoutingDemo.java
java --add-modules jdk.httpserver PathPrefixRoutingDemo
```

Verified stdout:

```text
/api => 200/BASE@/api
/apiX => 200/BASE@/api
/api/ => 200/SECTION@/api/
/api/items => 200/SECTION@/api/
/api/admin/status => 200/ADMIN@/api/admin/
/api/Admin/status => 200/SECTION@/api/
/Api/items => 200/CAPITAL@/Api/
/API/items => 404/NO_CONTEXT
/v123 => 200/VERSION@/v1
/api/item?sort=asc => 200/SECTION@/api/
```

Explanation of the key lines:

1. `/apiX` enters the `/api` context: **prefix collision** with a path not in the same REST segment.
2. `/api/` and `/api/items` enter the `/api/` context because it is longer than `/api`.
3. `/api/admin/status` enters `/api/admin/` by longest matching prefix.
4. `/api/Admin/status` falls back to `/api/`; a case mismatch in the child context **does not block the parent**.
5. `/Api/items` matches the separate context with an uppercase `A`; `/API/items` matches no context and returns 404 when there is no root fallback.
6. `/v123` enters `/v1` due to literal string prefix.
7. Query `?sort=asc` does not change the selected context.

Applications must validate paths and permissions at the business layer; this test demonstrates **routing** rather than providing authentication or security guarantees. It closes responses/exchanges, cleans up `HttpServer` and the executor, and does not access the Internet.

## 13. Java 17 Runnable Demo 2: Checking Segments, Encoded Aliases, and Method

The file **`StrictPathGuardDemo.java`** registers the broad context `"/docs"`, but only allows `GET /docs` or `GET /docs/<single-lowercase-ascii-slug>`. The paths `/docs-public`, `/docs/%61dmin`, and `/docs/a/b` are rejected by the handler. `/Docs/a1` matches no context and receives 404 from the server. `POST` returns 405 with `Allow: GET`.

```java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public class StrictPathGuardDemo {
    private static void reply(HttpExchange exchange, int status,
                              String body) throws IOException {
        try (exchange) {
            byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=UTF-8");
            exchange.sendResponseHeaders(status, bytes.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(bytes);
            }
        }
    }

    private static HttpResponse<String> request(HttpClient client,
            String base, String path, String method) throws Exception {
        HttpRequest.Builder builder = HttpRequest.newBuilder(
                URI.create(base + path)).timeout(Duration.ofSeconds(5));
        HttpRequest call = "GET".equals(method)
                ? builder.GET().build()
                : builder.POST(HttpRequest.BodyPublishers.noBody()).build();
        return client.send(call, HttpResponse.BodyHandlers.ofString());
    }

    public static void main(String[] args) throws Exception {
        InetAddress local = InetAddress.getByAddress(
                new byte[]{127, 0, 0, 1});
        HttpServer server = HttpServer.create(
                new InetSocketAddress(local, 0), 0);
        ExecutorService workers = Executors.newFixedThreadPool(2);
        AtomicInteger boundaryDenied = new AtomicInteger();
        AtomicReference<String> encodedRaw = new AtomicReference<>();
        AtomicReference<String> encodedDecoded = new AtomicReference<>();

        server.createContext("/docs", exchange -> {
            URI requestURI = exchange.getRequestURI();
            String raw = requestURI.getRawPath();
            if (raw.contains("%")) {
                encodedRaw.set(raw);
                encodedDecoded.set(requestURI.getPath());
            }
            if (!"GET".equals(exchange.getRequestMethod())) {
                exchange.getResponseHeaders().set("Allow", "GET");
                reply(exchange, 405, "METHOD");
                return;
            }
            // One deliberately narrow application route:
            // /docs or /docs/<one lowercase ASCII slug>.
            boolean accepted = "/docs".equals(raw)
                    || raw.matches("/docs/[a-z0-9-]+");
            if (!accepted) {
                boundaryDenied.incrementAndGet();
                reply(exchange, 404, "REJECTED");
                return;
            }
            reply(exchange, 200, "DOC:" + raw);
        });
        server.setExecutor(workers);
        server.start();

        try {
            HttpClient client = HttpClient.newHttpClient();
            String base = "http://127.0.0.1:"
                    + server.getAddress().getPort();

            HttpResponse<String> root = request(
                    client, base, "/docs", "GET");
            HttpResponse<String> item = request(
                    client, base, "/docs/a1", "GET");
            HttpResponse<String> prefix = request(
                    client, base, "/docs-public", "GET");
            HttpResponse<String> encoded = request(
                    client, base, "/docs/%61dmin", "GET");
            HttpResponse<String> nested = request(
                    client, base, "/docs/a/b", "GET");
            HttpResponse<String> uppercase = request(
                    client, base, "/Docs/a1", "GET");
            HttpResponse<String> query = request(
                    client, base, "/docs/a1?view=full", "GET");
            HttpResponse<String> method = request(
                    client, base, "/docs/a1", "POST");

            System.out.println("Exact /docs: " + root.statusCode());
            System.out.println("Single slug: " + item.statusCode());
            System.out.println("Prefix collision rejected: "
                    + prefix.statusCode() + "/" + prefix.body());
            System.out.println("Encoded slug rejected: "
                    + encoded.statusCode() + "/" + encoded.body());
            System.out.println("Nested path rejected: "
                    + nested.statusCode());
            System.out.println("Case mismatch: "
                    + uppercase.statusCode());
            System.out.println("Query does not select context: "
                    + query.statusCode());
            System.out.println("Method rejected: "
                    + method.statusCode());
            System.out.println("Encoded raw path: "
                    + encodedRaw.get());
            System.out.println("Decoded URI path: "
                    + encodedDecoded.get());
            System.out.println("Handler denials: "
                    + boundaryDenied.get());
        } finally {
            server.stop(0);
            workers.shutdownNow();
        }
    }
}
```

Run:

```sh
javac --release 17 --add-modules jdk.httpserver -encoding UTF-8 StrictPathGuardDemo.java
java --add-modules jdk.httpserver StrictPathGuardDemo
```

Verified stdout:

```text
Exact /docs: 200
Single slug: 200
Prefix collision rejected: 404/REJECTED
Encoded slug rejected: 404/REJECTED
Nested path rejected: 404
Case mismatch: 404
Query does not select context: 200
Method rejected: 405
Encoded raw path: /docs/%61dmin
Decoded URI path: /docs/admin
Handler denials: 3
```

Key takeaways:

- `/docs-public` **entered the `/docs` context**, so it received `404/REJECTED` from the handler, unlike `/Docs/a1`, which received a core server 404 due to no matching context.
- `/docs/%61dmin` is not accepted under the demo's **raw spelling** policy; `getPath()` still decodes it to `/docs/admin`.
- `/docs/a/b` does not satisfy the single-slug rule.
- `?view=full` does not change context selection; the handler still needs to validate the query if the API uses it.
- `POST /docs/a1` enters the `/docs` context and is then rejected with 405 by the application method guard.
- `Handler denials: 3` confirms that the three non-conforming paths were **handled by the guard**, rather than disappearing over the network.

**Demo limitations:** only a fictional resource and ASCII slugs; not production authentication/authorization, and does not handle file paths, Unicode identifiers, proxies, or symlink attacks. Do not use this regex to protect any API without analyzing canonical resource identity.

## 14. Placing Authorization Properly with Parent/Child Contexts

You might configure:

```java
// Illustrative snippet: filter has already been implemented.
HttpContext admin = server.createContext(
        "/api/admin/", adminHandler);
admin.getFilters().add(authFilter);
server.createContext("/api/", publicHandler);
```

When a request to `/api/Admin/status` arrives, Java 17 selects **`/api/`**, not `/api/admin/`. The admin context's filter **does not run** because the request does not belong to that context. If `publicHandler` lowercases the path on its own and accesses admin data, that is an **application-induced authorization bypass**.

To avoid this:

1. Guard canonical path and casing at ingress/dispatcher, rejecting invalid aliases.
2. Always check **principal and resource permissions** in the business layer, not only in the context filter.
3. Avoid having a public fallback reinterpret rejected requests differently.
4. Place filters on the right contexts and test parent fallback.
5. Log the context actually selected via `getHttpContext().getPath()`, the canonical route ID, and the authz outcome.

`Filter` and `Authenticator` are building blocks. A multi-tenant system with complex auth/session/roles should consider a proven framework/router rather than assembling fragmented prefix guards by hand.

## 15. Method 405, 404, and Proper Lifecycle

`HttpContext` does not select routes by HTTP method. If a handler only supports GET, it should return 405 and the `Allow: GET` header:

```java
// Snippet inside HttpHandler.handle, not a standalone class.
if (!"GET".equals(exchange.getRequestMethod())) {
    exchange.getResponseHeaders().set("Allow", "GET");
    exchange.sendResponseHeaders(405, -1);
    exchange.close();
    return;
}
```

According to Java 17 `HttpExchange.sendResponseHeaders(status,length)`:

- `length > 0`: must write **the exact number of bytes** of the response.
- `length == 0`: uses chunked transfer encoding, **not** meaning "zero-byte response".
- `length == -1`: response **has no body**.

Do not just `return` without terminating the exchange; close the response stream and request stream or use `try(exchange)` on every code path. Examples 1 and 2 both use `try(exchange)` in their response helper methods.

Status 404 can indicate an invalid path, a non-existent route, or a resource whose existence must not be disclosed; 403 is permission denied, and 401 is missing authn. Choose statuses according to your security/API contract, and do not treat 404 as an authentication mechanism.

## 16. Do Not Use Literal Routes Directly as Filesystem Paths

A file-serving handler often makes this mistake:

```java
// Anti-pattern: illustrates how not to trust the URL path.
Path file = root.resolve(exchange.getRequestURI()
        .getPath().substring("/files/".length()));
// Without containment/symlink checks, traversal is possible.
```

You must determine the canonical route, decode exactly once, reject disallowed dot segments/encoded separators, confirm the resolved/canonical file lies within the authorized storage root **after normalizing and accounting for symlinks**, and then check authz on the file/resource ID. Do not apply `String.startsWith(root.toString())` as a safe filesystem containment check.

If a reverse proxy/WAF performs rewrites/normalization differently from the backend, you must test **the exact chain: proxy → `HttpServer` → app**. A request like `/docs/%2e%2e/admin` can look different at each layer. Never assume every proxy protects the application from encoded aliases.

## 17. Designing Small Routers Without Relying on Prefix Collisions

For very small applications, two safer patterns are:

**A. Register exact root and descendants, with guards:**

```java
server.createContext("/api", apiRoot);
server.createContext("/api/", apiChildren);
```

`apiRoot` must reject `/apiX`. `apiChildren` must parse segments and authorize each operation.

**B. Single context prefix, internal dispatcher with a contract:**

```java
server.createContext("/api", dispatcher);
```

`dispatcher` receives the raw URI, canonicalizes/validates it strictly per policy, checks method + path shape + identity, and then invokes the specific handler. Do not let each business handler decode/lowercase differently.

When you have many templated routes such as `GET /users/{id}`, `POST /orders/{id}/items`, per-route auth, content negotiation, middleware, or dynamic APIs, a framework/router with an explicit route model usually reduces risk compared to building hundreds of `startsWith` checks.

## 18. Do Not Treat `{id}` as a Wildcard in `createContext`

`createContext("/users/{id}", handler)` **does not automatically create a path parameter**. In Java 17 `HttpServer`, this is just a literal context path containing the characters `{` and `}`. A request to `/users/42` will not automatically substitute `{id}`.

To accept `/users/42`, register `"/users/"` and parse the suffix yourself after validating boundaries and canonicalization:

```java
// Illustrative snippet: must handle status, authz, and exceptions.
String raw = exchange.getRequestURI().getRawPath();
if (!raw.startsWith("/users/")) {
    // reject
}
String idText = raw.substring("/users/".length());
if (!idText.matches("[0-9]{1,18}")) {
    // reject
}
```

Parsing `idText` must check for large-number overflow and perform authorization on the resource ID. Do not treat passing a regex as access permission. If routes have deep nesting, it is better to use a router with a parser/path-template model and security tests.

## 19. Case-Sensitive Rules and HTTP Headers Do Not Conflict

HTTP header names such as `Content-Type` and `content-type` are case-insensitive. Meanwhile, URI paths have their own identity, and in Java 17 `HttpServer` **context paths are case-sensitive**. Therefore `/api/Admin` and `/api/admin` are not synonymous unless **the application intentionally designs** them to be aliases.

If you choose case-insensitive routes for a product:

- Define canonical spelling for resources upon creation.
- Create unique constraints/namespaces so `ReportA` and `reporta` cannot collide.
- Canonicalize consistently before authorization, caching, and storage lookups.
- Use Unicode normalization/case folding appropriate for the language requirements when non-ASCII identifiers exist.
- Test the same policy from gateway/proxy to backend.
- Return redirects/404s per contract, avoiding dangerous auto-correction on methods with side effects.

Do not call `toLowerCase()` arbitrarily in individual handlers, and do not confuse supporting Unicode URLs with allowing arbitrary non-canonical encodings.

## 20. Test Plan for Routes with Sensitive Data

At minimum, test these cases:

1. `/admin`, `/admin/`, `/admin/users` — exact identification of root/trailing slash/descendants.
2. `/administrator`, `/admin-old` — prefix collision.
3. `/Admin`, `/ADMIN`, `/api/Admin/users` — case mismatch and fallback.
4. `/admin/%61`, `/admin/%2fsecret`, `/admin/%2e%2e/secret` — encoded aliases.
5. `/admin/%252e%252e` — double encoding.
6. `/admin/./users`, `/admin/../public` — dot segments; test through real clients and proxies.
7. `/admin//users` — repeated slashes.
8. Different queries, header variants, GET/POST/PUT/DELETE/HEAD — method/query independence.
9. With/without root fallback — server 404 vs. handler 404.
10. Authn/authz: regular users must not access admin resources via path aliases or fallbacks.
11. Path params: overly long slugs, malformed Unicode/UTF-8, null bytes, encoded separators.
12. URI → filesystem: canonical path, containment, symlinks, tenant boundaries.
13. Observe `getHttpContext().getPath()` and app route IDs in logs.
14. When upgrading JDK/provider: re-run route-match tests and check for semantic changes.

**Do not test only the happy path** such as `GET /api/admin/status` and conclude the router is safe. Most bugs appear in aliases and fallback paths.

## 21. Resources, Logging, and Operations

Correct routing can still fail under heavy load. `HttpServer` uses handler callbacks that can block on input, DB, and response output. You need `setExecutor` before `start()`, request body size caps, connection/timeouts, bounded queues, and cleanup. `Executors.newFixedThreadPool(n)` **does not automatically create a bounded queue**; it only limits the number of concurrently running workers.

Useful logging includes: redacted raw path, selected context, canonical route name, method, response status, request ID, principal/tenant ID, and authorization outcome. Do not log full query strings if they contain tokens/PII, and do not trust arbitrary `X-Forwarded-*` headers from clients.

Count `path_policy_rejected` and `router_fallback` separately to spot `/api/Admin/*` requests falling into the wrong context early. If the app sits behind an HTTP reverse proxy, tests and logs must verify how the request URI was rewritten/normalized before reaching the Java handler.

If the router needs many path templates, Unicode normalization, method-aware routing, auth middleware, and observability, compare the total cost of building it yourself against a dedicated framework/server rather than comparing lines of code alone.

## 22. Common Mistakes and How to Fix Them

1. **Assuming `"/api"` only matches `/api`.** Wrong: `/apiX` can also match.
2. **Assuming `"/api/"` matches `/api`.** Wrong: the trailing slash is a character in the prefix.
3. **Assuming the first registered context wins.** Wrong: longest matching prefix wins.
4. **Assuming paths are case-insensitive like HTTP headers.** Wrong: Java 17 matches literals case-sensitively.
5. **Assuming a child filter protects all admin aliases.** Wrong: if a request falls back to the parent, the child filter does not run.
6. **Assuming root `"/"` only receives `/` requests.** Wrong: it can act as a catch-all.
7. **Assuming `"/users/{id}"` is a template.** Wrong: it is a literal string in the context path.
8. **Assuming queries change context selection.** Wrong: matching uses the URI path.
9. **Assuming GET and POST are two separate contexts when the path is the same.** Wrong without an application router.
10. **Assuming `getRawPath` always equals `getPath`.** Wrong with percent-encoding.
11. **Decoding a path multiple times to be "sure".** Can cause traversal/authorization mismatches.
12. **Lowercasing every path before authz.** Can accidentally merge distinct resources/tenant keys.
13. **Checking only `startsWith("/docs")`.** Does not distinguish `/docs-public`.
14. **Treating a slug regex as sufficient for authn/authz.** There is no principal/resource permission check.
15. **Opening files from an unchecked raw URI path.** Introduces path traversal/symlink risks.
16. **Letting a public fallback parse secret routes.** Requires 404/canonical guards + authz.
17. **Not closing `HttpExchange` when returning 404/405.** Easily hangs clients or leaks resources.
18. **Interpreting `sendResponseHeaders(404, 0)` as no body.** Java 17: 0 is chunked, -1 is no body.
19. **Testing only direct localhost and skipping proxy rewrites.** Needs end-to-end testing.
20. **Assuming all future JDKs/providers keep identical routing details.** Pin versions and run regression tests.

## 23. Self-Check Questions

**1.** With contexts `"/api"` and `"/api/"`, which one does `/api/items` enter? **`"/api/"`**, the longer prefix.

**2.** With only `"/v1"`, can `/v123` enter that context? **Yes on Java 17** because of literal prefix matching.

**3.** Does `/api/Admin/status` enter the `"/api/admin/"` context? **No**; if `"/api/"` exists, it can fall back to the parent context.

**4.** Are `/API/status` and `/api/status` the same? **No**, case-sensitive.

**5.** Does creating a root context `"/"` make unknown paths automatically return 404? **No**, the root handler is selected and must decide.

**6.** Does `?sort=asc` affect context selection? **No**, queries do not participate in prefix path matching.

**7.** Are `GET` and `POST` to the same URI path automatically dispatched to separate handlers by the core server? **No**; the application checks the method.

**8.** What does `getRawPath()` return for `/docs/%61dmin`? **`/docs/%61dmin`**; `getPath()` gives `/docs/admin`.

**9.** Why did `/docs-public` in the demo return `404/REJECTED`? **It matched the `/docs` context, but the handler had a segment guard that rejected it.**

**10.** Does a filter attached to `/api/admin/` run for `/api/Admin/`? **No** if the request was routed to a different context.

**11.** Should you call `toLowerCase` on all paths to avoid 404s? **No**; a clear canonical route/resource policy is needed.

**12.** In `sendResponseHeaders(status,length)`, what does a length of `-1` mean? **No response body**.

**13.** Is a correct route match safe enough to read a file by path? **No**; you must check the canonical filesystem path, symlinks, and authorization.

**14.** When should you use another HTTP router/framework? **When you need many method/path templates, middleware/security integration, and normalization with clearer contracts than literal-prefix matching.**

## 24. Pre-Deployment Checklist

- [ ] Lock in the exact **longest literal prefix, case-sensitive** behavior of Java 17.
- [ ] Test `/api`, `/api/`, `/apiX`, and descendants.
- [ ] Test uppercase/lowercase casing on both parent and child contexts.
- [ ] Do not treat context prefixes as REST path templates or authorization.
- [ ] Define consistent canonical route and raw/decoded URI policies.
- [ ] Do not decode twice; have policies for encoded slashes, dots, Unicode, and duplicate slashes.
- [ ] Check path segment boundaries, not just string prefixes.
- [ ] Distinguish core 404, handler 404, method 405, and authorization 403.
- [ ] Apply filters/authenticators to the right contexts; fallbacks must not bypass authz.
- [ ] Have validation, size caps, bounded executors, deadlines, and `HttpExchange` cleanup.
- [ ] Test through reverse proxies/WAFs and JDK/provider upgrades.
- [ ] Have redacted structured logs for selected context, canonical route, principal, and outcome.

**Conclusion:** In Java 17 `HttpServer`, **context selection is only longest literal prefix selection**, not a replacement for an application router and certainly not a replacement for authorization. Trailing slashes, casing, percent-encoding, and parent fallbacks must be tested independently. To achieve reliable routing, you need **canonical path policy + segment guards + method handling + authz + negative tests**; if routing requirements are complex, consider a dedicated framework/router rather than writing an increasingly unmanageable chain of `startsWith` checks.

### Official Sources

- [Java SE 17 — HttpServer, Mapping request URIs to HttpContext paths](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html)
- [Java SE 17 — HttpContext, filters and authenticator](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpContext.html)
- [Java SE 17 — HttpExchange, getRequestURI, getHttpContext, response lifetime](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpExchange.html)
- [Java SE 17 — URI, getPath and getRawPath](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URI.html)
- [Java SE 17 — jdk.httpserver package](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/package-summary.html)
- [RFC 3986 — URI Generic Syntax](https://www.rfc-editor.org/rfc/rfc3986)
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html).
