# Filter, Authenticator, and Separating Shared Processing in the JDK HTTP Server

**`com.sun.net.httpserver.HttpServer`** in the **`jdk.httpserver`** module is a lightweight HTTP server built into the JDK. Instead of duplicating authentication logic, request tracing, header injection, method checking, and timing across every endpoint, we can separate them into **`HttpContext`**, **`Filter`**, **`Authenticator`**, **`HttpHandler`**, and shared helpers/services.

This Knowledge article belongs to **Java Advance - networking → JDK HTTP server**. The focus is not only on API syntax but also on **separation of responsibilities**, processing order, and safety when multiple HTTP requests run concurrently.

~~~text
                   HttpServer
                       |
            select HttpContext by path
                       |
               user Filter chain
                 /          \
        pre-processing     short-circuit (4xx)
                 |
           authentication
                 |
           HttpHandler
                 |
           response status/body
                 |
          post-processing/logging
~~~

**The diagram illustrates responsibilities, not a guarantee that all user filters run after Authenticator.** In the tested provider, a pre-filter can still run and add a response header even when authentication ultimately rejects the request. Therefore, a pre-processing filter must not assume `HttpExchange.getPrincipal()` already has an authenticated principal.

The two complete Java 17+ programs in this article are run with an HTTP server on `127.0.0.1`, using a port assigned by the operating system. No Internet connection is required, and no real accounts or passwords are used.

## 1. Separation of Responsibilities Among Classes

| Component | Role | Things to Note |
| --- | --- | --- |
| `HttpServer` | Binds port, accepts requests, dispatches to context, manages executor | Simple, not a full framework/gateway |
| `HttpContext` | Maps a root path to a handler and configures filters/authentication | Has its own filter list and shared attributes |
| `HttpHandler` | Processes requests according to business logic, produces responses | Must check permissions for specific resources itself |
| `HttpExchange` | State, headers, and streams of a single request/response | Use `setAttribute/getAttribute` for per-request metadata |
| `Filter` | Pre/post processing or early request blocking | Call `chain.doFilter` exactly once when proceeding |
| `Filter.Chain` | Transfers control to the next filter or handler | Not a loop for calling the handler multiple times |
| `Authenticator` | Verifies credentials, decides Success/Retry/Failure | Authentication differs from authorization |
| `BasicAuthenticator` | Handles HTTP Basic, invokes your `checkCredentials` | Base64 is not encryption; use only over HTTPS outside loopback |
| `HttpPrincipal` | Identity accepted by the authenticator | Handler retrieves via `exchange.getPrincipal()` |
| `Executor` | Runs tasks that process HTTP requests | Set via `setExecutor` **before** `start` |

For example, for the request `GET /secure/report/42`: Filter can attach a trace ID, Authenticator verifies credentials, while the handler must check whether that user has permission to view report 42. Having a valid account **does not mean** being allowed to view all data.

## 2. HttpContext Routes by Prefix, Not Regex

Server configuration (snippet, without full imports/main):

~~~java
HttpServer server = HttpServer.create(
        new InetSocketAddress(
                InetAddress.getByName("127.0.0.1"), 0), 0);

HttpContext api = server.createContext("/api/", exchange -> {
    // Handler checks path/method and responds.
});

server.start();
~~~

`createContext("/api/", handler)` associates a path prefix with a handler. When receiving a request, the server finds the **longest matching prefix**; matching is literal and case-sensitive. There are no `{id}` placeholders or automatic router parameters.

~~~text
Contexts:
    /
    /api/
    /api/admin/

Request /api/users       -> /api/
Request /api/admin/list  -> /api/admin/
Request /other           -> /
Request /API/users       -> /  (different case)
~~~

**Warning:** A context `"/api"` without a trailing slash can match `"/apix"`. For a route group, prefer `"/api/"` and check the specific path inside the handler. If the context is just `"/api/"`, the handler will receive both `/api/foo` and `/api/bar`; you must branch/validate accordingly.

`HttpServer.create(addr, backlog)` takes a TCP backlog. Backlog is the number of connections waiting to be accepted by the OS, **not** a request rate limit, nor a substitute for a body-size limit or bounded executor queue. Port `0` is a convenient way to pick an ephemeral port for tests.

## 3. How Does the Filter Chain Work?

A custom Filter defines:

~~~java
@Override
public String description() {
    return "Measure request time";
}

@Override
public void doFilter(
        HttpExchange exchange, Filter.Chain chain)
        throws IOException {

    long started = System.nanoTime();
    try {
        chain.doFilter(exchange);
    } finally {
        long durationNanos = System.nanoTime() - started;
        // Record into the application's thread-safe histogram/metrics.
    }
}
~~~

This is the **body of a Filter class**, not a standalone program. `Filter.doFilter` can inspect request headers, attach attributes, wrap streams, send a rejection response, or pass control forward with `chain.doFilter(exchange)`.

If Filter A is registered before Filter B:

~~~text
A.before
    B.before
        HttpHandler.handle(exchange)
    B.after
A.after
~~~

**Pre goes forward, post goes backward.** A Filter is allowed to terminate the chain early by **not calling** `chain.doFilter`, in which case it must send an appropriate HTTP response itself and close resources properly.

Do not call the chain twice:

~~~java
chain.doFilter(exchange);
chain.doFilter(exchange); // ANTI-PATTERN: may process/send response twice.
~~~

An `HttpExchange` has one logical response; sending response headers a second time typically results in an I/O error or an invalid exchange state.

## 4. Filter.beforeHandler and Filter.afterHandler Since Java 17

Two convenient factory methods:

~~~java
Filter trace = Filter.beforeHandler(
        "Add trace header",
        exchange -> exchange.getResponseHeaders()
                .set("X-Trace-Id", "study-247"));

Filter statusLog = Filter.afterHandler(
        "Log response code",
        exchange -> System.out.println(
                "HTTP status: " + exchange.getResponseCode()));
~~~

`beforeHandler` runs the Consumer **before** the next filter/handler. `afterHandler` runs the Consumer **after** downstream completes. Both are convenience factories introduced in Java 17.

**Use beforeHandler to add headers before the response is committed.** Do not use `afterHandler` to modify `Content-Type`, CORS, or security headers because the handler may have already sent the response. `afterHandler` is better suited for metrics, logging, and observing status codes.

With two consecutive `afterHandler` filters, the Consumers run in **reverse registration order**, because the chain is nested. If you need to measure cases where downstream throws an `IOException`, a custom Filter with `try/finally` is usually clearer.

**Follow the error-handling contract:** According to the Javadoc, if a filter catches an `IOException` thrown by downstream, it must rethrow it. Do not swallow the IOException and fabricate a fake HTTP 200 to hide the error.

## 5. Registering Filters on the Right Context and at the Right Time

~~~java
HttpContext context =
        server.createContext("/reports/", reportHandler);

context.getFilters().add(
        Filter.beforeHandler("Add marker", exchange ->
                exchange.getResponseHeaders()
                        .set("X-App", "reports")));

context.getFilters().add(new RequestMetricsFilter());
~~~

This is an **architectural snippet**: `reportHandler` and `RequestMetricsFilter` are application-defined. The `context.getFilters()` list is a **live list** actually used during dispatch; modifications affect subsequent requests. For real applications, configure everything completely **before `server.start()`**, avoiding modifying the list while threads are processing requests, as that easily creates hard-to-test ordering/race issues.

**There is no automatic global filter** for all HttpContexts. To apply shared middleware to three contexts, you must attach it to all three, or use a bootstrap/factory function to create contexts with a unified filter list.

You can register the **same Filter instance** across multiple contexts if it is stateless or thread-safe. If the instance holds a counter or mutable state, decide explicitly whether you want to share the counter; do not accidentally mix data across tenants.

## 6. Short-Circuit: Blocking a Request in a Filter

Example guard allowing only GET (snippet inside `doFilter`):

~~~java
if (!"GET".equals(exchange.getRequestMethod())) {
    exchange.getResponseHeaders().set("Allow", "GET");

    byte[] body = "method-not-allowed"
            .getBytes(StandardCharsets.UTF_8);
    exchange.sendResponseHeaders(405, body.length);

    try (OutputStream out = exchange.getResponseBody()) {
        out.write(body);
    }

    return; // Do not call chain.doFilter().
}

chain.doFilter(exchange);
~~~

The Filter sends `405 Method Not Allowed`, the `Allow: GET` header, and then **stops the chain**. The handler and inner filters are not called.

Use short-circuiting for common validation: unsupported methods, missing required headers, request limits, or throttling. However, a filter checking the HTTP method **cannot replace an Authenticator or per-resource authorization**.

If rejecting a request that has a body, the application must also manage the request input stream and connection reuse. Closing the exchange without consuming the body can prevent the underlying connection from being reused; enforce byte limits, avoiding reading an unbounded body just to return an error.

## 7. Authenticator Returns Success, Retry, or Failure

In `com.sun.net.httpserver.Authenticator`, the method:

~~~java
public abstract Authenticator.Result authenticate(
        HttpExchange exchange);
~~~

must return one of:

| Result | Meaning | Main Behavior |
| --- | --- | --- |
| `Authenticator.Success` | Identity/credentials are valid | Proceeds to handler, attaches HttpPrincipal |
| `Authenticator.Retry` | Client needs to re-authenticate via another HTTP exchange | Returns specified status, usually 401 with challenge |
| `Authenticator.Failure` | Authentication permanently failed | Returns appropriate error code, does not run handler |

`Retry` **does not mean the server re-invokes the handler itself**. It only emits an HTTP response so the client can send a new request. With Basic auth, the client typically receives `401` with `WWW-Authenticate: Basic realm="..."` and then resends credentials.

Attaching an Authenticator to a context:

~~~java
context.setAuthenticator(authenticator);
~~~

`setAuthenticator` replaces the previous authenticator; passing `null` can remove the context's authentication requirement, so do not do this casually. Other contexts do not automatically inherit the Authenticator from the current context.

**Authentication and authorization are different:** Authenticator verifies who is sending the request; the handler must check whether the verified identity is allowed to view/modify the specific resource. Without authorization, IDOR/cross-tenant data leakage can occur even when Basic auth works perfectly.

## 8. BasicAuthenticator and HTTP Basic Security

A local example:

~~~java
context.setAuthenticator(
        new BasicAuthenticator(
                "StudyRealm", StandardCharsets.UTF_8) {
            @Override
            public boolean checkCredentials(
                    String user, String password) {
                return "alice".equals(user)
                        && "demo-only".equals(password);
            }
        });
~~~

This is a snippet using **dummy credentials on localhost**, not suitable for production. `BasicAuthenticator` parses the HTTP Basic header and calls `checkCredentials(username,password)`. The constructor taking a charset parameter supports UTF-8 since Java 17; the constructor without a charset parameter behaves according to the default charset in the Javadoc.

**The Basic header only contains Base64 encoding, not encryption.** Over a network transport, you must use HTTPS/TLS, secure credential verification, password hashes/identity provider, brute-force protection policies, rate limiting, secret rotation, and redacted logging. Do not hardcode real user plaintext passwords in source code.

Protecting endpoints:
- If the request lacks credentials, BasicAuthenticator can return a 401 challenge.
- If the user/password is wrong, the request is rejected.
- If valid, the handler retrieves the principal via `exchange.getPrincipal()`.
- A valid principal **does not mean** access is granted to all objects/tenants.

**Do not use `X-User` or the sender's IP as an authenticated principal.** Client-sent headers can be spoofed; a reverse proxy also requires a clear trust boundary.

## 9. Order of Filters and Authentication: A Very Common Pitfall

In the tested provider, the HTTP 401 response still carried the header added by `Filter.beforeHandler`. This shows that a custom pre-filter can run **before authentication finishes**.

Maintain these safety invariants:
1. A pre-processing user filter may observe the method/URI and create a trace, but must not assume `getPrincipal()` is non-null.
2. Do not treat `X-User` or an unverified `Authorization` header as a valid identity.
3. Do not expose sensitive information in a filter that runs even for unauthenticated requests.
4. Do not let a handler process sensitive business logic without passing the context's authentication requirement.
5. In the handler, check **per-object/per-tenant authorization** based on the authenticated principal.
6. When changing HTTP server providers/JDK versions, **test authentication/filter behavior**, rather than relying on internal ordering not guaranteed by the API contract.

`HttpContext.setAuthenticator` ensures authentication is attached to the context, but it does not mean you can skip permission checks in the handler or use a pre-filter as an authorization gate.

## 10. Complete Java 17+ Example: Filter + BasicAuthenticator + 405 Guard

The program **`FilterAuthOrderDemo.java`** creates a loopback HTTP server with context `/secure/`:
- `OrderFilter` records events before/after the chain.
- `Filter.beforeHandler` attaches an attribute and response header `X-Trace-Id`.
- A method guard returns 405 for POST without calling the handler.
- `Filter.afterHandler` records the response status when the downstream handler runs.
- `BasicAuthenticator` accepts only `alice:demo-only`.
- HttpClient sequentially sends four requests: missing auth, wrong password, right password, and right password with POST.

Create file **`FilterAuthOrderDemo.java`**:

~~~java
import com.sun.net.httpserver.BasicAuthenticator;
import com.sun.net.httpserver.Filter;
import com.sun.net.httpserver.HttpContext;
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
import java.util.Base64;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class FilterAuthOrderDemo {
    static final List<String> events = new CopyOnWriteArrayList<>();

    static void send(HttpExchange ex, int status, String message)
            throws IOException {
        byte[] bytes = message.getBytes(StandardCharsets.UTF_8);
        ex.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=utf-8");
        ex.sendResponseHeaders(status, bytes.length);
        try (OutputStream out = ex.getResponseBody()) {
            out.write(bytes);
        }
    }

    static class OrderFilter extends Filter {
        @Override
        public String description() {
            return "Record filter nesting";
        }

        @Override
        public void doFilter(HttpExchange ex, Chain chain)
                throws IOException {
            events.add("outer-in");
            try {
                chain.doFilter(ex);
            } finally {
                events.add("outer-out");
            }
        }
    }

    static HttpRequest request(
            URI uri, String method, String basic) {
        HttpRequest.Builder builder = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(3));

        if (basic != null) {
            String encoded = Base64.getEncoder().encodeToString(
                    basic.getBytes(StandardCharsets.UTF_8));
            builder.header("Authorization", "Basic " + encoded);
        }

        if ("GET".equals(method)) {
            builder.GET();
        } else {
            builder.method(method, HttpRequest.BodyPublishers.noBody());
        }
        return builder.build();
    }

    static String call(HttpClient client, HttpRequest req)
            throws Exception {
        HttpResponse<String> resp = client.send(
                req, HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));

        return resp.statusCode() + "|" + resp.body()
                + "|trace=" + resp.headers()
                .firstValue("X-Trace-Id").orElse("none");
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress(
                        InetAddress.getByName("127.0.0.1"), 0), 0);

        ExecutorService workers = Executors.newFixedThreadPool(3);
        server.setExecutor(workers);

        HttpContext context = server.createContext(
                "/secure/", ex -> {
                    events.add("handler");
                    String user = ex.getPrincipal() == null
                            ? "anonymous"
                            : ex.getPrincipal().getUsername();
                    send(ex, 200, user + "|" + ex.getAttribute("trace"));
                });

        context.getFilters().add(new OrderFilter());

        context.getFilters().add(Filter.beforeHandler(
                "Attach trace", ex -> {
                    events.add("trace-pre");
                    ex.setAttribute("trace", "lesson-247");
                    ex.getResponseHeaders().set(
                            "X-Trace-Id", "lesson-247");
                }));

        context.getFilters().add(new Filter() {
            @Override
            public String description() {
                return "Method guard";
            }

            @Override
            public void doFilter(
                    HttpExchange ex, Chain chain) throws IOException {
                events.add("guard");

                if (!"GET".equals(ex.getRequestMethod())) {
                    ex.getResponseHeaders().set("Allow", "GET");
                    send(ex, 405, "method-not-allowed");
                    return;
                }
                chain.doFilter(ex);
            }
        });

        context.getFilters().add(Filter.afterHandler(
                "Record response status",
                ex -> events.add("after:" + ex.getResponseCode())));

        context.setAuthenticator(new BasicAuthenticator(
                "StudyRealm", StandardCharsets.UTF_8) {
            @Override
            public boolean checkCredentials(
                    String user, String password) {
                return user.equals("alice")
                        && password.equals("demo-only");
            }
        });

        server.start();
        try {
            URI uri = URI.create(
                    "http://127.0.0.1:"
                    + server.getAddress().getPort()
                    + "/secure/hello");

            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .followRedirects(HttpClient.Redirect.NEVER)
                    .build();

            System.out.println("No auth: " + call(
                    client, request(uri, "GET", null)));
            System.out.println("Wrong auth: " + call(
                    client, request(uri, "GET", "alice:incorrect")));

            events.clear();
            System.out.println("Valid auth: " + call(
                    client, request(uri, "GET", "alice:demo-only")));
            System.out.println("Valid events: "
                    + String.join(",", events));

            events.clear();
            System.out.println("Guard: " + call(
                    client, request(uri, "POST", "alice:demo-only")));
            System.out.println("Guard events: "
                    + String.join(",", events));
        } finally {
            server.stop(0);
            workers.shutdownNow();
        }
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 FilterAuthOrderDemo.java
java FilterAuthOrderDemo
~~~

**Tested stdout with the default provider in the executed environment (Java 17-compatible APIs):**

~~~text
No auth: 401||trace=lesson-247
Wrong auth: 401||trace=lesson-247
Valid auth: 200|alice|lesson-247|trace=lesson-247
Valid events: outer-in,trace-pre,guard,handler,after:200,outer-out
Guard: 405|method-not-allowed|trace=lesson-247
Guard events: outer-in,trace-pre,guard,outer-out
~~~

**Reading the output:** Missing auth and wrong password both return 401 without entering the handler. The pre-filter still attaches `X-Trace-Id` in the tested provider, so the output contains the trace even without an authenticated principal. With valid credentials, the handler returns the username and trace. The event sequence shows the outer filter wrapping the entire chain and afterHandler running when the inner handler finishes. POST is blocked with 405 by the method guard, so there are no handler/after:200 events.

**Do not use this credential code on the Internet.** This is only a local fixture to illustrate the API, lacking password hashing, lockout, CSRF controls, TLS, or production policies.

## 11. Separating Shared Processing Across Multiple Endpoints

An architecture can apply the same concerns across multiple contexts:

~~~text
        /alpha/hello --> AlphaHandler
       /alpha/other --> AlphaHandler
         /beta/hello --> BetaHandler
                   |
          +--------+--------+
          | common filters |
          | trace / metrics|
          +--------+--------+
                   |
          shared response helper
                   |
          endpoint-specific logic
~~~

Recommended separation:
- **Shared Filter:** trace/correlation ID, metrics, common method checks, security response headers before commit, request limits.
- **Authenticator:** verifies identity based on the context's credential mechanism.
- **Handler/service:** exact routing, request body parsing, data processing, authorization by principal and resource, returning response.
- **Response support:** UTF-8 encoding, status, headers, responseLength, closing the body stream.
- **Bootstrap:** creating contexts, attaching filters in order, configuring Authenticator/Executor, starting and stopping.

If alpha and beta handlers use the same helper, that does not mean they are allowed to share a `currentUser` state. Mutable fields on a singleton Filter/Handler can be read/written concurrently by multiple HTTP threads.

## 12. Difference Between Per-Request Attributes and Per-Context Attributes

**`HttpExchange.setAttribute/getAttribute`** is suitable for metadata of **a single request**:

~~~java
Filter trace = Filter.beforeHandler(
        "Trace", ex -> ex.setAttribute("trace", "demo-247"));

// Handler receives the same HttpExchange:
Object requestTrace = exchange.getAttribute("trace");
~~~

This is a snippet; in production, the trace ID should be generated/validated per policy, not a fixed string.

**`HttpContext.getAttributes()`** returns a Map **shared across all exchanges** of the context:

~~~java
HttpContext reports = server.createContext(
        "/reports/", reportsHandler);
reports.getAttributes().put("service", "reports");
~~~

This is a snippet, assuming `server/reportsHandler` already exist. Immutable per-context configuration can live here. **Do not** write `currentUser`, bearer tokens, request bodies, or per-HTTP-request information into the shared Map.

If a Filter instance is used on both alpha and beta contexts:
- If stateless: it can be shared.
- If holding a thread-safe counter: the counter can **intentionally count together**.
- If holding context-local config/counter: consider creating a **separate instance per context**.
- If holding a mutable request identity field: **unsafe**, move it to exchange attributes or local variables.

## 13. Complete Java 17+ Example: Same Filter on Two Contexts

The program **`SharedFilterModulesDemo.java`** creates:
- Context `/alpha/` with service config `"alpha"`.
- Context `/beta/` with service config `"beta"`.
- **One** shared `CountingFilter` with `AtomicInteger`.
- **One** `Filter.beforeHandler` attaching `trace` to each exchange, also shared.
- A handler that uses its own service config and returns HTTP 404 if the specific path does not match.
- Three HTTP GET requests sent sequentially so the count output is deterministic.

Create file **`SharedFilterModulesDemo.java`**:

~~~java
import com.sun.net.httpserver.Filter;
import com.sun.net.httpserver.HttpContext;
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
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

public class SharedFilterModulesDemo {
    static final class CountingFilter extends Filter {
        final AtomicInteger seen = new AtomicInteger();

        @Override
        public String description() {
            return "Count across contexts";
        }

        @Override
        public void doFilter(
                HttpExchange ex, Chain chain) throws IOException {
            int count = seen.incrementAndGet();
            ex.getResponseHeaders().set(
                    "X-Count", Integer.toString(count));
            chain.doFilter(ex);
        }
    }

    static void send(
            HttpExchange ex, int status, String body)
            throws IOException {
        byte[] data = body.getBytes(StandardCharsets.UTF_8);
        ex.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=utf-8");
        ex.sendResponseHeaders(status, data.length);
        try (OutputStream out = ex.getResponseBody()) {
            out.write(data);
        }
    }

    static void handle(HttpExchange ex) throws IOException {
        String service = String.valueOf(
                ex.getHttpContext().getAttributes().get("service"));
        String path = ex.getRequestURI().getPath();

        if (!"GET".equals(ex.getRequestMethod())) {
            ex.getResponseHeaders().set("Allow", "GET");
            send(ex, 405, "method-not-allowed");
            return;
        }
        if (!path.equals("/" + service + "/hello")) {
            send(ex, 404, "not-found");
            return;
        }

        send(ex, 200, service + "|" + ex.getAttribute("trace"));
    }

    static HttpResponse<String> request(
            HttpClient client, URI root, String path)
            throws Exception {
        HttpRequest req = HttpRequest.newBuilder(root.resolve(path))
                .timeout(Duration.ofSeconds(3)).GET().build();
        return client.send(
                req, HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress(
                        InetAddress.getByName("127.0.0.1"), 0), 0);

        HttpContext alpha = server.createContext("/alpha/", ex -> {
            try {
                handle(ex);
            } catch (IOException error) {
                ex.close();
            }
        });
        HttpContext beta = server.createContext("/beta/", ex -> {
            try {
                handle(ex);
            } catch (IOException error) {
                ex.close();
            }
        });

        alpha.getAttributes().put("service", "alpha");
        beta.getAttributes().put("service", "beta");

        CountingFilter sharedCounter = new CountingFilter();
        Filter sharedTrace = Filter.beforeHandler(
                "Per-request trace", ex -> {
                    ex.setAttribute("trace", "demo-247");
                    ex.getResponseHeaders().set(
                            "X-Trace", "demo-247");
                });

        alpha.getFilters().addAll(
                List.of(sharedTrace, sharedCounter));
        beta.getFilters().addAll(
                List.of(sharedTrace, sharedCounter));

        server.start();
        try {
            URI root = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort());
            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .build();

            HttpResponse<String> a =
                    request(client, root, "/alpha/hello");
            HttpResponse<String> b =
                    request(client, root, "/beta/hello");
            HttpResponse<String> missing =
                    request(client, root, "/alpha/missing");

            System.out.println("Alpha: " + a.statusCode()
                    + "|" + a.body() + "|count="
                    + a.headers()
                    .firstValue("X-Count").orElse("none"));
            System.out.println("Beta: " + b.statusCode()
                    + "|" + b.body() + "|count="
                    + b.headers()
                    .firstValue("X-Count").orElse("none"));
            System.out.println("Missing: "
                    + missing.statusCode() + "|" + missing.body()
                    + "|trace=" + missing.headers()
                    .firstValue("X-Trace").orElse("none"));
            System.out.println("Shared filter invocations: "
                    + sharedCounter.seen.get());
        } finally {
            server.stop(0);
        }
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 SharedFilterModulesDemo.java
java SharedFilterModulesDemo
~~~

**Stdout verified on localhost with sequential requests:**

~~~text
Alpha: 200|alpha|demo-247|count=1
Beta: 200|beta|demo-247|count=2
Missing: 404|not-found|trace=demo-247
Shared filter invocations: 3
~~~

**Explanation:** The same filter instance only sets the trace for the current exchange. Service configuration resides in two separate contexts. The atomic counter is designed to aggregate requests from **both contexts**, so 404s also increment the value. If requests run concurrently, counts remain safe, though the order of numbers assigned to alpha or beta is not guaranteed. To have two separate counters, create two CountingFilter instances.

## 14. Response Helper and HttpExchange Lifecycle

A helper that can be shared:

~~~java
static void sendText(
        HttpExchange ex, int status, String text)
        throws IOException {
    byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
    ex.getResponseHeaders().set(
            "Content-Type", "text/plain; charset=utf-8");
    ex.sendResponseHeaders(status, bytes.length);
    try (OutputStream out = ex.getResponseBody()) {
        out.write(bytes);
    }
}
~~~

**Call `sendResponseHeaders` before `getResponseBody()`**, and close the OutputStream to finish the exchange. The fixed response length must be the **number of bytes after encoding**, not `String.length()`.

`HttpExchange.sendResponseHeaders(code, length)` Javadoc:

| Length Value | Meaning |
| --- | --- |
| Greater than 0 | Must write the exact declared number of bytes |
| Equal to 0 | Uses **chunked transfer encoding**, can send an arbitrary body size |
| Equal to -1 | **No response body** |

Do not confuse `responseLength=0` with a zero-byte body. For HTTP 204, use the appropriate no-body semantics, e.g. `sendResponseHeaders(204, -1)`, without writing a body.

Closing the response OutputStream also closes the request InputStream if not yet closed, but **you should consume the request body with a limit** to support connection reuse; closing mid-stream may prevent the connection from being reused. The examples only process small requests from a self-controlled client.

## 15. Filter.setStreams and Body Processing

A Filter can wrap request/response streams using:

~~~java
exchange.setStreams(
        wrappedRequestInputStream,
        wrappedResponseOutputStream);
~~~

According to the Javadoc, the new streams must **wrap original streams**; pass `null` for one direction if you do not want to replace it. Use this when you need to limit bytes read, measure response bytes, or perform transformations with a clear contract.

~~~text
original request InputStream
     -> limiting/counting InputStream
     -> handler reads chunk by chunk

handler writes bytes
     -> counting OutputStream
     -> original response OutputStream
~~~

This is a **diagram**, not a runnable implementation. Do not read the entire body upfront in a Filter and expect the Handler to read again from an already-consumed stream. If you only want simple tracing/metrics, use a Filter without wrapping streams to reduce error risk.

**Body limits must be based on bytes actually read.** The `Content-Length` header may be missing or untrustworthy, especially with chunked transfer encoding. A public-facing server needs per-request limits, concurrency limits, timeouts, and admission control.

## 16. Concurrency and Safe State

When attaching an executor with multiple worker threads, the same Filter/Handler object can process multiple requests concurrently.

**Anti-pattern:**

~~~java
class BadFilter extends Filter {
    String lastUser; // Mutable shared field.

    public String description() { return "Unsafe"; }

    public void doFilter(
            HttpExchange ex, Chain chain) throws IOException {
        lastUser = ex.getRequestHeaders().getFirst("X-User");
        chain.doFilter(ex);
    }
}
~~~

This is intentionally flawed illustrative code. It both has a **data race** across HTTP worker threads and trusts a caller-sent header instead of an authenticated principal.

Safer approaches:
- Local variables and `HttpExchange.setAttribute/getAttribute` for request-scoped metadata.
- Immutable configuration placed in final fields or context attributes set before start.
- `AtomicInteger`, `LongAdder`, or a thread-safe metrics registry for counters.
- Do not store a request's `currentUser` or bearer token in a static field, context map, or singleton filter.
- Do not rely on ThreadLocal automatically propagating across executors/callbacks.
- For business logic, obtain the proper principal and check per-object authorization.

**Executor:** `server.setExecutor(executor)` must be called before `start()`. `Executors.newFixedThreadPool(K)` limits the number of worker threads, but the default queue can be unbounded, so production needs bounded queues, timeouts, and request admission control. The localhost examples use a small fixed pool solely to test the mechanism.

## 17. Errors, HTTP Statuses, and Response Sending Limits

A Filter/Handler can return 400, 401, 403, 404, 405, 413, 429, or 500 depending on the error. Distinguish:
- `401`: authentication challenge/invalid credentials.
- `403`: request understood, but access is forbidden by policy.
- `404`: no route/resource found (may be from handler or server).
- `405`: unsupported method; should set `Allow`.
- `500`: server error; do not expose stack traces/secrets to the client.

If an exception occurs **before sending response headers**, an error boundary can safely generate a 500. If headers have already been sent, **do not send a second response**; log and close the exchange according to policy. `exchange.getResponseCode()` may be -1 before a status is set.

If a Filter catches an `IOException` from `chain.doFilter`, the Javadoc requires rethrowing it. For logging/metrics, use `try/finally` so cleanup is not lost. Do not automatically retry an HTTP exchange within the same Filter by calling the chain multiple times.

## 18. Security and Production Deployment

The two examples use loopback HTTP to test the API, **not as a template for Internet deployment**. When exposing a server:
- Use HTTPS via `HttpsServer`/`HttpsConfigurator` with an `SSLContext` and valid certificates, or a controlled TLS reverse proxy.
- Do not use Base64-only Basic credentials over unencrypted transport.
- Passwords must be properly hashed, with rate limiting/brute-force protection, auditing, and credential rotation.
- Do not log `Authorization`, Cookie, session ID, passwords, or sensitive data.
- Authorize by user/resource/tenant in the Handler/Service, not just authenticate.
- Check URI normalization/path matching, avoiding overly broad route prefixes.
- Set request body limits, bounded queues, and timeouts to prevent resource exhaustion.
- Only trust proxy headers from a trusted proxy; a client's `X-Forwarded-For` header is not inherently trustworthy.
- CORS/CSRF and cookie/session policies must be designed specifically if serving browsers.
- Security headers must be set **before** committing the response; do not wait for afterHandler.
- Guard against SSRF if the handler accesses client-supplied URLs/backends.
- Test 401/403/404/405/429 along with both GET/POST and I/O errors.

JDK HttpServer is a small API convenient for learning, but it does not out-of-the-box provide all features of an API gateway framework/production server.

## 19. Checklist for Separating Shared Processing

| Code Review Question | Expected Result |
| --- | --- |
| Are context paths clear and ending with a slash when appropriate? | No accidental match of `/apiX` |
| Are filters attached to the right contexts? | No missed endpoints |
| Has the pre/post filter order been tested? | Has nested tests |
| Does a short-circuit filter send/close the response properly? | No hanging clients |
| Is the Authenticator attached via `setAuthenticator`? | Not confused with `Filter` |
| Does the Filter assume the principal is already authenticated? | No |
| Does the Handler check per-resource authorization? | Yes |
| Where is request metadata placed? | In `HttpExchange`, not a global field |
| Where is context config placed? | `HttpContext.getAttributes()` or immutable dependency |
| Are shared metrics fields thread-safe? | Yes |
| Are response headers set before commit? | Yes |
| Does fixed response length use the correct byte length? | Yes |
| Does error handling avoid double responses? | Yes |
| Are the executor/queue bounded? | Yes for public traffic |
| Are body/credentials protected? | Size limits, TLS, no secret logging |
| Are 401, 405, shared filters, and 404 paths all tested? | Yes |

## 20. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Duplicating trace/metrics in every handler | Repeated code, inconsistency | Extract into a Filter |
| Putting business authorization in an object-unaware Filter | Misses IDOR | Check in service/handler |
| Adding BasicAuthenticator to the filter list | Wrong API | Use `context.setAuthenticator` |
| Assuming a pre-filter always has a principal | Wrong auth assumption | Do not rely on internal auth ordering |
| Forgetting `chain.doFilter` | Handler does not run | Call chain properly on pass-through |
| Calling chain twice | Double response | Process an exchange once |
| Short-circuiting Filter without sending a response | Request hangs | Send 4xx and close stream |
| Modifying headers in afterHandler | Too late after commit | Set in beforeHandler/helper |
| Using `String.length()` as fixed body length | Broken UTF-8 framing | Use `bytes.length` |
| Thinking responseLength 0 = no-body | Mistakenly uses chunked | Use -1 for no-body |
| Not closing response stream | Resource leak/connection not reused | Try-with-resources |
| Shared mutable currentUser on filter | Data race/user leak | Exchange attribute |
| Storing request metadata in context attributes | Requests overwrite each other | Context only holds shared config |
| Using shared Atomic counter thinking it is per-context | Inaccurate metrics | Separate instances or labels |
| Modifying filter list after start | Unpredictable races/order | Configure before start |
| Using HTTP Basic over public HTTP | Credentials can be read | Enforce TLS |
| Trusting `X-User` as authenticated identity | User spoofing | Authenticator principal |
| Using `/api` as route prefix without care | Matches `/apix` too | Use `/api/` and check path |
| Unbounded executor queue/body | DoS/OOM | Bounded resources |
| Trying to send 500 after response is committed | Double write | Log + abort/close |
| Not testing unauthorized method/path | Missing protection | Integration tests with status assertions |

## 21. Self-Check Questions

**1.** How do `HttpContext` and `HttpHandler` differ?  
**Answer:** Context holds the root path and filter/auth configuration, while handler executes the specific request processing.

**2.** Two filters A/B in order; in what order do pre/post run?  
**Answer:** A.pre → B.pre → handler → B.post → A.post.

**3.** Must a Filter always call `chain.doFilter`?  
**Answer:** No; when short-circuiting, it can return a status and not call the chain.

**4.** Should `Filter.afterHandler` add Content-Type?  
**Answer:** It should not, because the response may already be committed.

**5.** Is `BasicAuthenticator` a `Filter`?  
**Answer:** No. It is attached via `HttpContext.setAuthenticator`.

**6.** What does `Authenticator.Success` provide?  
**Answer:** An HttpPrincipal representing the authenticated user.

**7.** Does having an authenticated principal mean permission to view every resource?  
**Answer:** No; the handler/service must still authorize per object/tenant.

**8.** Why is Basic Base64 not secure enough over public HTTP?  
**Answer:** Base64 is only encoding, easily decoded; HTTPS/TLS and a credential policy are required.

**9.** What scope is `HttpExchange.setAttribute` used for?  
**Answer:** For a single exchange/request.

**10.** What scope is `HttpContext.getAttributes` used for?  
**Answer:** Shared across all requests in that context.

**11.** How will the same CountingFilter instance across two contexts count?  
**Answer:** It shares the counter, requiring atomic/thread-safe operations if processed concurrently.

**12.** Can context `/api` match `/apix`?  
**Answer:** Yes, due to prefix matching; use a trailing slash and path checks.

**13.** Does `sendResponseHeaders(status, 0)` mean no body?  
**Answer:** No; 0 is chunked; -1 is no-body.

**14.** Why use `bytes.length` instead of `text.length()`?  
**Answer:** HTTP body length is in bytes, and UTF-8 byte count can differ from the number of UTF-16 characters.

**15.** Is a filter before auth guaranteed to see the authenticated principal?  
**Answer:** No. Do not rely on unguaranteed implementation ordering.

**16.** When a filter rejects a method with 405, does the handler run?  
**Answer:** No, if the filter returns a response and does not call the chain.

**17.** Is `HttpServer.setExecutor` called before or after `start()`?  
**Answer:** Before `start()`.

**18.** When an HTTP handler has already sent headers and encounters an exception, should it send a new 500 response?  
**Answer:** No. You must not commit a second response; log and clean up/abort according to policy.

## 22. Official Documentation

- [Java SE 17 — Module jdk.httpserver](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/module-summary.html): JDK HTTP server classes.
- [Java SE 17 — HttpServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): server creation, executor, start/stop, and prefix routing.
- [Java SE 17 — HttpContext](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpContext.html): filter list, attributes, and authenticator.
- [Java SE 17 — Filter](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/Filter.html): Chain, short-circuiting, beforeHandler/afterHandler.
- [Java SE 17 — Filter.Chain](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/Filter.Chain.html): invoking the next filter.
- [Java SE 17 — Authenticator](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/Authenticator.html): Success/Failure/Retry.
- [Java SE 17 — BasicAuthenticator](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/BasicAuthenticator.html): Basic auth, realm, checkCredentials.
- [Java SE 17 — HttpPrincipal](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpPrincipal.html): authenticated principal.
- [Java SE 17 — HttpExchange](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpExchange.html): request/response lifecycle and attributes/streams.
- [Java SE 17 — HttpsServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpsServer.html): HTTPS server and SSL configuration.
- [Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): client used in the two loopback tests.
