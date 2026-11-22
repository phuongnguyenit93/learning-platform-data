# Creating a Server, Binding an Address, and Registering HttpContext

## 1. Lesson Objectives

When writing a small HTTP endpoint in Java, you do not necessarily need to install a web framework. The JDK provides the `jdk.httpserver` module with `com.sun.net.httpserver.HttpServer`, `HttpContext`, `HttpHandler`, and `HttpExchange`. They are sufficient for building a simple HTTP server for practice exercises, internal health checks, test endpoints, or development tools.

After this lesson, you will be able to do three core things:

1. **Create an HTTP server** using `HttpServer.create()` or `HttpServer.create(InetSocketAddress, backlog)`, and know the difference between an **unbound** server and a **bound** server.
2. **Bind to an IP/port and start listening** with `bind(...)` then `start()`; understand the loopback address, port `0`, socket backlog, and the order of configuring an executor.
3. **Register URL paths using `HttpContext`**, associate them with an `HttpHandler`, and understand **longest literal prefix matching** (longest prefix, case-sensitive) as well as how to remove a context.

The two Java 17+ programs in sections 9 and 11 run directly via `javac`/`java`, start a server on `127.0.0.1`, and use the JDK HTTP client to verify responses. You do not need to install Spring, a Servlet container, third-party frameworks, or have an Internet connection.

**Scope:** `com.sun.net.httpserver.HttpServer` is the JDK's lightweight HTTP server. It is **not equivalent** to a full-featured web application server, and does not automatically provide annotation-based routing, validation, business security, reverse proxying, or specialized deployment capabilities. This lesson focuses on **the server lifecycle and context routing mechanism**, rather than turning it into a framework guide.

## 2. Objects and Relationships

| API | Role | Key Points to Remember |
| --- | --- | --- |
| `HttpServer` | Manages the listening socket, contexts, executor, and lifecycle | A server can be created unbound or bound immediately |
| `InetSocketAddress` | IP address/hostname and port to listen on | Port `0` asks the OS to assign a free port |
| `HttpContext` | Maps a **path prefix** to an `HttpHandler` | Resolved by longest matching prefix |
| `HttpHandler` | Handler function for requests routed to the context | `handle(HttpExchange)` method |
| `HttpExchange` | A request and its corresponding response | Contains method, URI, headers, and body streams |
| `Headers` | Request/response headers | Use `getResponseHeaders()` to set headers before sending |
| `Executor` | Dispatches where handlers run | Configure with `setExecutor` before `start` |
| `HttpClient` | JDK client for testing the server | Belongs to the `java.net.http` module, separate from `HttpServer` |
| `HttpsServer` | Server variant supporting HTTPS | Requires `HttpsConfigurator` and a valid TLS configuration |

Typical flow:

~~~text
             Java application
                    |
     HttpServer.create() or create(addr, backlog)
                    |
              bind if needed
                    |
  createContext("/hello", HttpHandler)
  createContext("/api/", HttpHandler)
                    |
            setExecutor(...)
                    |
                 start()
                    |
 TCP accept -> HTTP parse -> select HttpContext -> HttpHandler.handle(exchange)
                                               |
                                read method/URI/headers/body
                                               |
                             set response headers + sendResponseHeaders
                                               |
                              write/close response body + exchange
                    |
               stop(delay)
~~~

`HttpContext` is not an independent socket listener. **One `HttpServer` can have multiple `HttpContext`s, but all of them share that server's bound socket**. Paths like `/hello` or `/api/` do not replace IP/port: they only determine which handler is selected **after the TCP connection and HTTP request reach the server**.

## 3. Exact Lifecycle: create → bind → contexts → executor → start → stop

There are **two common ways to create a server**:

**Approach A — create unbound, bind later:**

~~~java
HttpServer server = HttpServer.create();
server.bind(new InetSocketAddress("127.0.0.1", 8080), 32);
server.createContext("/hello", exchange -> {
    // Handle an HTTP request.
});
server.start();
~~~

*Illustrative snippet; the handler's response body logic is left empty. Use the complete program in section 9 to run.*

`HttpServer.create()` returns a server **not yet bound to any IP/port**. You must call `server.bind(InetSocketAddress,int)` before using the listening socket. Do not call `bind` twice on a server that is already bound.

**Approach B — create and bind in one call:**

~~~java
HttpServer server = HttpServer.create(
        new InetSocketAddress("127.0.0.1", 8080), 32);
server.createContext("/hello", handler);
server.start();
~~~

*Illustrative snippet where `handler` needs to be declared separately.*

`HttpServer.create(addr,backlog)` binds to `addr` immediately upon creation, but **does not start serving requests** until `start()` is called. In this overload, passing `addr == null` creates an unbound server and you must call `bind(...)` later; for clarity, `create()` is usually preferred when you genuinely want to separate the steps.

**State table:**

| Stage | Bound to an address? | Handling requests yet? | Valid actions |
| --- | --- | --- | --- |
| After `create()` | No | No | `bind`, configure contexts/executor |
| After `create(addr,backlog)` | Yes | No | Register contexts, `setExecutor`, `start` |
| After `bind(addr,backlog)` | Yes | No | Read `getAddress`, register contexts, `start` |
| After `start()` | Yes | Yes | Receive/send `HttpExchange`s, manage contexts |
| After `stop(delay)` | No longer serving | No | Release resources; **cannot restart the old server** |

Normally, **register handlers, configure filters/authenticators, and set the executor before `start()`**, so there is no time window where requests arrive at a context that is not ready. `setExecutor(...)` must be called **before** `start()`; calling it after the server has started can throw `IllegalStateException`.

`stop(int delay)` stops listening, rejects new exchanges, and waits for existing exchanges to finish for **at most about `delay` seconds**, then closes the connections. A stopped server cannot be `start()`ed again; create a new server if you need to start it again.

## 4. Binding an Address: loopback, port, backlog

Statement:

~~~java
server.bind(new InetSocketAddress("127.0.0.1", 0), 16);
int actualPort = server.getAddress().getPort();
~~~

There are three meaningful components:

- **IP/hostname**: `127.0.0.1` is the **IPv4 loopback** address, serving only connections on the same machine (in standard network configurations); suitable for tests or local-only services. `0.0.0.0` represents **all IPv4 interfaces**, which may allow other machines to access it depending on firewall/network settings — do not use it inadvertently.
- **Port**: `8080` is a fixed port, and callers need to know this exact number. `0` is an **ephemeral port chosen by the operating system** for that bind; call `getAddress().getPort()` **after binding** to get the actual port.
- **Backlog**: `16` is a hint for **the number of pending TCP connections waiting to be accepted**, not the number of concurrent HTTP requests being processed, not a body size limit, and not a thread pool size. A value `<= 0` causes the implementation to use the system default.

Example of selecting an IP via an object:

~~~java
InetSocketAddress local =
        new InetSocketAddress(InetAddress.getByName("127.0.0.1"), 0);
HttpServer server = HttpServer.create(local, 0);
System.out.println(server.getAddress().getPort() > 0);
~~~

*Illustrative snippet requiring imports and server cleanup; complete programs managing the full lifecycle are in sections 9–11.*

**Two common bind errors:** the port is already in use by another process, or the specified IP is not present/cannot be bound on the host. The JDK may throw `BindException` (a subclass of `IOException`). For fixed services, configure the port and report errors clearly; do not silently pick another port if clients or reverse proxies still point to the old port. For tests, port `0` reduces port conflicts.

For IPv6, the address and URL syntax must match, such as `[::1]`; do not assume the name `localhost` always resolves to the same IP family. The demos explicitly use `127.0.0.1` on **both server and client** to avoid IPv4/IPv6 mismatches.

## 5. Registering HttpContext: Path Prefix to HttpHandler

Shortest form:

~~~java
HttpContext context = server.createContext(
        "/hello", exchange -> {
            // Handle requests for the selected path.
        });
~~~

`createContext(String path, HttpHandler handler)` creates the context and attaches the handler in one call. `path` **must start with `/`**. `handler` must not be `null`, and creating a duplicate context path on the same server can throw `IllegalArgumentException`.

Another approach is used when you need to declare the context first and attach the handler later:

~~~java
HttpContext context = server.createContext("/api/");
context.setHandler(exchange -> {
    // Set the handler for the first time.
});
~~~

*These two snippets are illustrative; the runnable program in section 9 uses the standard overload and stores the `HttpContext` to remove it later.*

`HttpContext.setHandler(...)` is for **setting the handler when the context does not have one yet**; it is not an arbitrary hot-swap handler feature. If a handler is already attached, calling `setHandler` again can throw `IllegalArgumentException`. To change routing at the context level, you need controlled context registration/removal, or let the handler use an internal thread-safe configuration.

A context can be configured further:

- `context.getFilters()`: list of `Filter`s for pre/post-handler processing, such as logging, request control, or input inspection.
- `context.setAuthenticator(...)`: attaches an `Authenticator` when authentication is needed.
- `context.getPath()`: the registered path prefix.
- `context.getHandler()` and `context.getServer()`: access the associated handler/server.
- `context.getAttributes()`: a context-scoped map for sharing configuration with filters/handlers, which requires synchronization if updated concurrently by multiple threads.

Do not leave a context without a handler ready to serve requests. Preparing handlers and filters **before `start()`** is easier to control. Do not treat a context path as an **authorization** mechanism: requests must still be authenticated and authorized by the appropriate handler/filter.

## 6. Routing Rules: Longest Prefix, Literal Matching, and Case Sensitivity

`HttpServer` selects an `HttpContext` based on the **longest matching literal prefix** of the request URI path. There is no regex, no `@GetMapping`, no wildcards like `/users/{id}`, and **no automatic path segmentation like a REST router**.

Registration example:

~~~text
/
 /app/
 /app/admin/
 /legacy
~~~

*Leading spaces are only for visualizing the hierarchy; actual context strings have no leading spaces.*

Incoming requests will be matched as follows:

| Received URI path | Selected context | Why |
| --- | --- | --- |
| `/app/report` | `/app/` | Prefix `/app/` is longer than `/` |
| `/app/admin/users` | `/app/admin/` | This is the longest matching prefix |
| `/app/ADMIN/users` | `/app/` | `admin` differs from `ADMIN`; case-sensitive |
| `/application` | `/` | Does not start with `/app/` |
| `/legacyExtra` | `/legacy` | `/legacy` is a **character prefix**, without automatic segment boundary checking |
| `/foo` | `/` | Context `/` catches all remaining paths |
| `/app/admin/users` after removing `/app/admin/` | `/app/` | The longest remaining matching context wins |

**Important trap:** context `/api` **can also catch `/apiculture`**, because it only checks character prefixes; context `/api/` avoids this collision but **does not catch the exact path `/api`**. If you want to handle both, explicitly register both `/api` and `/api/` or check the exact path in the appropriate handler.

**A trailing `/` matters.** `/admin/` is usually a safer choice than `/admin` if you want to preserve subtree boundaries. Even so, the handler **must still validate the method, path structure, parameters, and permissions**. Selecting a context does not guarantee that the request is allowed.

**No matching context:** if there is no `/` root context and no context matches, JDK `HttpServer` automatically sends **404**. If you have a root context `/`, almost every URI path will match root; in that case, you must explicitly return 404 from the handler when a path is unsupported.

## 7. Percent-Encoding, Method, and Query Do Not Replace Routing

The JDK's path matching API performs **literal, case-sensitive matching without automatic encoding conversion** during the context selection step. Do not confuse:

- `exchange.getRequestURI().getRawPath()`: raw path string, still containing percent-encoded characters.
- `exchange.getRequestURI().getPath()`: path URI-decoded according to `java.net.URI` rules.
- `exchange.getRequestURI().getRawQuery()`: raw query string; **the query is not part of the context path prefix**.
- `exchange.getRequestMethod()`: HTTP method, **not automatically distinguished during context selection**.

For example, `/users?id=42` and `/users?id=99` have the same path for selecting context `/users`. The handler must read the query and validate values itself. Perform controlled path normalization/decoding at the application layer, especially before converting a path into a file name or access check; do not rely on context matching to prevent path traversal.

For a REST API, if you only want GET on exact `/hello`, the handler code should check:

~~~java
if (!"GET".equals(exchange.getRequestMethod())) {
    exchange.getResponseHeaders().set("Allow", "GET");
    respond(exchange, 405, "method not allowed");
} else if (!"/hello".equals(exchange.getRequestURI().getPath())) {
    respond(exchange, 404, "not found");
} else {
    respond(exchange, 200, "hello from JDK");
}
~~~

*This is an excerpt **from the complete program** in section 9; it requires `respond` and the `exchange` variable to be declared.*

The reason for the additional `"/hello".equals(...)` check: context `/hello` can also match `/helloExtra`. `HttpServer` only selects the handler; **only the handler knows what the specific endpoint requires**.

## 8. HttpExchange: Request and Response Lifecycle

`HttpHandler.handle(HttpExchange exchange)` is called when a request matches a context. Inside the handler, the standard procedure consists of:

1. Read `exchange.getRequestMethod()`, `getRequestURI()`, and `getRequestHeaders()`; validate/limit inputs.
2. If the request has a body, consume it properly and **close `exchange.getRequestBody()`**. Avoid unconditional `readAllBytes()` on unbounded bodies.
3. Set `exchange.getResponseHeaders()`, such as `Content-Type` and `Allow`.
4. Call **`exchange.sendResponseHeaders(statusCode, responseLength)` before obtaining the response body output stream**.
5. Write the exact number of bytes matching `responseLength`, close the output stream; **ensure `exchange.close()`** in a `finally` block or try-with-resources to release the exchange.

**`responseLength` is the easiest parameter to get wrong:**

| Value passed to `sendResponseHeaders` | Meaning in the JDK HTTP server |
| --- | --- |
| **`> 0`** | Body has a **fixed byte length**; must write **exactly** that many bytes |
| **`== 0`** | Uses chunked transfer encoding to send a body of unknown length (HTTP/1.1) |
| **`-1`** | **Sends no response body**; appropriate when an empty response is needed |

Therefore, when sending text, **do not use `String.length()` as the Content-Length**. With UTF-8, a Vietnamese string can take more bytes than the number of Java characters. Do it properly:

~~~java
byte[] body = "Xin chào".getBytes(StandardCharsets.UTF_8);
exchange.getResponseHeaders().set(
        "Content-Type", "text/plain; charset=utf-8");
exchange.sendResponseHeaders(200, body.length);
try (OutputStream output = exchange.getResponseBody()) {
    output.write(body);
}
exchange.close();
~~~

*Illustrative snippet; in production, put `close()` in `finally`. If the body is empty and you want to send no body, use `-1` instead of mistaking `0` for a zero-length fixed body.*

With `204 No Content` or `HEAD`, be careful **not to send a disallowed body** per HTTP semantics; use the appropriate response length/handler and close streams properly. Once `getResponseBody()` is opened, it must be closed to complete the exchange. Reading or sending fewer or more bytes than declared can throw `IOException` and cause the connection to be closed.

## 9. Complete Java 17+ Example: create(), bind(), Context Registration, and HTTP Responses

The first example verifies the flow **from an unbound server** to an HTTP-serving server, adds three contexts, uses a dedicated executor, and removes a context at runtime. A client in the same JVM sends real requests over TCP loopback.

Create the file `HttpServerBindDemo.java` with the exact full content:

~~~java
import com.sun.net.httpserver.HttpContext;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class HttpServerBindDemo {
    static void respond(HttpExchange exchange, int status, String body)
            throws IOException {
        try {
            byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=utf-8");
            exchange.sendResponseHeaders(status, bytes.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(bytes);
            }
        } finally {
            exchange.close();
        }
    }

    static HttpResponse<String> get(HttpClient client, String base, String path)
            throws Exception {
        HttpRequest request = HttpRequest.newBuilder(
                URI.create(base + path)).GET().build();
        return client.send(request,
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(); // Not bound yet.
        ExecutorService workers = Executors.newFixedThreadPool(2);
        try {
            server.bind(new InetSocketAddress("127.0.0.1", 0), 16);
            server.createContext("/hello", exchange -> {
                if (!"GET".equals(exchange.getRequestMethod())) {
                    exchange.getResponseHeaders().set("Allow", "GET");
                    respond(exchange, 405, "method not allowed");
                } else if (!"/hello".equals(exchange.getRequestURI().getPath())) {
                    respond(exchange, 404, "not found");
                } else {
                    respond(exchange, 200, "hello from JDK");
                }
            });
            server.createContext("/api/", exchange -> respond(exchange, 200,
                    "api path=" + exchange.getRequestURI().getPath()));
            HttpContext items = server.createContext("/api/items/",
                    exchange -> respond(exchange, 200,
                            "items path=" + exchange.getRequestURI().getPath()));
            server.setExecutor(workers); // Must happen before start().
            server.start();

            String base = "http://127.0.0.1:" + server.getAddress().getPort();
            HttpClient client = HttpClient.newHttpClient();
            for (String path : new String[]{
                    "/hello", "/api/users", "/api/items/7", "/missing"}) {
                HttpResponse<String> response = get(client, base, path);
                System.out.println("GET " + path + ": " + response.statusCode()
                        + (response.statusCode() == 200
                        ? " " + response.body() : ""));
            }

            HttpRequest post = HttpRequest.newBuilder(
                    URI.create(base + "/hello"))
                    .POST(HttpRequest.BodyPublishers.noBody()).build();
            HttpResponse<String> rejected = client.send(
                    post, HttpResponse.BodyHandlers.ofString());
            System.out.println("POST /hello: " + rejected.statusCode()
                    + " Allow=" + rejected.headers().firstValue("Allow")
                    .orElse("(missing)"));

            server.removeContext(items);
            HttpResponse<String> fallback = get(client, base, "/api/items/7");
            System.out.println("GET /api/items/7 after remove: "
                    + fallback.statusCode() + " " + fallback.body());
        } finally {
            server.stop(0);
            workers.shutdownNow();
        }
    }
}
~~~

### Compile and Run

~~~bash
javac HttpServerBindDemo.java
java HttpServerBindDemo
~~~

Expected output when loopback is working:

~~~text
GET /hello: 200 hello from JDK
GET /api/users: 200 api path=/api/users
GET /api/items/7: 200 items path=/api/items/7
GET /missing: 404
POST /hello: 405 Allow=GET
GET /api/items/7 after remove: 200 api path=/api/items/7
~~~

### Why Does the Program Produce These Exact Lines?

- `HttpServer.create()` is initially **unbound**. `server.bind(new InetSocketAddress("127.0.0.1",0),16)` binds the socket to the IPv4 loopback address and an OS-assigned port. `server.getAddress().getPort()` is read **after bind/start** so the client knows the actual address.
- `createContext("/hello", handler)` attaches one handler for the `/hello` prefix. Inside the handler, it **explicitly** checks the GET method and exact path; therefore POST is rejected with status **405** and the `Allow: GET` header.
- `createContext("/api/", handler)` receives `/api/users`. `createContext("/api/items/", handler)` is longer, so it receives `/api/items/7`.
- There is no `/` context, so `/missing` **matches no handler** and the JDK server returns **404**. The client only prints the status for this case without relying on the implementation-generated 404 body.
- `setExecutor(workers)` is called **before `start()`**. The server uses an executor limited to two worker threads for the demo; thread management should not be confused with the backlog of 16.
- `server.removeContext(items)` removes the specific `/api/items/` context. GET `/api/items/7` afterward **matches `/api/`** and returns a body prefixed with `api path=`. This is the **fallback of the longest matching prefix algorithm**, not a cached response.
- `server.stop(0)` stops the server and `workers.shutdownNow()` shuts down the executor in `finally`, preventing the test process from staying alive because of the thread pool.

**Do not infer from the output that all requests were processed sequentially.** The client in the demo sends requests one by one for deterministic output; the server can handle multiple concurrent connections thanks to the executor. To measure concurrency, test with multiple concurrent clients and clear metrics.

## 10. Choosing Between create(), create(addr,backlog), and bind()

| Scenario | Approach | Reason |
| --- | --- | --- |
| Configuring the server across multiple steps before knowing the address | `HttpServer.create()` → `bind(...)` | Separates initialization and binding |
| Address is already known up front | `HttpServer.create(address, backlog)` | Binds immediately, concise code |
| Automated tests on a machine running many tests in parallel | `port = 0` and read `getAddress().getPort()` | Avoids hard-coded port conflicts |
| Internal service allowing same-machine access only | `127.0.0.1` | Reduces network surface compared to all interfaces |
| Service that must listen on an external interface | Bind controlled IP/interface + firewall/auth | Not safe by default |
| Multiple endpoints on the same port | Multiple `createContext(...)` calls on one `HttpServer` | No need for one socket per path |
| TLS required | `HttpsServer` + `HttpsConfigurator` | Plain `HttpServer` does not support HTTPS |

**Do not call `bind(...)` a second time on an already bound server.** If binding fails, inspect the `BindException` message and configuration policy. Do not turn a busy-port failure into switching to a random port in production without updating service discovery/proxies/clients.

An `HttpServer` that has been `stop(...)`ped **cannot be restarted**, even if its executor is still alive. Create a new `HttpServer` for a new lifecycle.

## 11. Complete Java 17+ Example: Longest Prefix, Case Sensitivity, and Context Removal

The second example uses **`HttpServer.create(address,backlog)` to bind immediately**, registers four contexts `/`, `/app/`, `/app/admin/`, and `/legacy`, and prints the **actual selected context** via `exchange.getHttpContext().getPath()`.

Create the file `HttpContextRoutingDemo.java`:

~~~java
import com.sun.net.httpserver.HttpContext;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;

public class HttpContextRoutingDemo {
    static void route(HttpExchange exchange) throws IOException {
        try {
            String chosen = exchange.getHttpContext().getPath();
            String body = "context=" + chosen;
            byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=utf-8");
            exchange.sendResponseHeaders(200, bytes.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(bytes);
            }
        } finally {
            exchange.close();
        }
    }

    static void probe(HttpClient client, String base, String path)
            throws Exception {
        HttpRequest request = HttpRequest.newBuilder(URI.create(base + path))
                .GET().build();
        HttpResponse<String> response = client.send(request,
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
        System.out.println(path + " -> " + response.body());
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        try {
            server.createContext("/", HttpContextRoutingDemo::route);
            server.createContext("/app/", HttpContextRoutingDemo::route);
            HttpContext admin = server.createContext(
                    "/app/admin/", HttpContextRoutingDemo::route);
            server.createContext("/legacy", HttpContextRoutingDemo::route);
            server.start();

            HttpClient client = HttpClient.newHttpClient();
            String base = "http://127.0.0.1:" + server.getAddress().getPort();
            for (String path : new String[]{
                    "/app/report", "/app/admin/users",
                    "/app/ADMIN/users", "/application", "/legacyExtra"}) {
                probe(client, base, path);
            }

            server.removeContext(admin);
            probe(client, base, "/app/admin/users");
        } finally {
            server.stop(0);
        }
    }
}
~~~

Run commands:

~~~bash
javac HttpContextRoutingDemo.java
java HttpContextRoutingDemo
~~~

Stdout:

~~~text
/app/report -> context=/app/
/app/admin/users -> context=/app/admin/
/app/ADMIN/users -> context=/app/
/application -> context=/
/legacyExtra -> context=/legacy
/app/admin/users -> context=/app/
~~~

**Observations:**

- The request `/app/admin/users` initially selects the longest context `/app/admin/`.
- `/app/ADMIN/users` does not match `/app/admin/` because paths are **case-sensitive**, so it falls back to `/app/`.
- `/application` does not have the `/app/` prefix (it differs after `/app`), so it is handled by root `/`.
- `/legacyExtra` **still matches `/legacy`** due to plain character-prefix matching. This is why a context representing a subtree should generally end with `/`, combined with path validation in the handler.
- After `server.removeContext(admin)`, the `/app/admin/users` request no longer has a specialized context, so it falls back to `/app/`.

In this example, because `createContext("/")` is registered, unregistered routes **still match root**. You cannot expect an automatic 404 when a catch-all root handler returns 200 for every request.

## 12. Which HttpContext Is Selected When Contexts Overlap?

Suppose you add the following contexts to the same server:

~~~java
server.createContext("/", rootHandler);
server.createContext("/api/", apiHandler);
server.createContext("/api/orders/", ordersHandler);
~~~

*Illustrative snippet; the `server` and handler variables must exist.*

Algorithm:

1. The HTTP server receives the request URI path.
2. It matches **literal prefixes** against registered `HttpContext.getPath()` values.
3. If multiple prefixes match, it selects the **longest prefix**.
4. It passes the `HttpExchange` to the winning context's `HttpHandler`.
5. If no prefix matches, the HTTP server returns 404. If there is a root `/`, root matches all remaining paths.

Do not confuse the path string `"/api/orders/"` with a template `"/api/orders/{id}"`. The JDK does not automatically extract the `id` parameter. The handler must parse `getRequestURI()`, validate segments, and check authorization itself.

Adding a duplicate context path `"/api/"` a second time does not create an automatic "override"; the API can throw `IllegalArgumentException`. If you want to replace a handler, design an appropriate lifecycle or have one handler delegate based on synchronized internal state.

Note on percent-encoded paths: the raw path and decoded path of a `URI` can differ. The context matching mechanism does not handle normalization or decoding for application security policies. When reading files from a URL path, never concatenate user-supplied paths directly onto the filesystem without normalizing, verifying the path stays within the allowed root, and enforcing access permissions.

## 13. Executor, Thread Pool, and Backlog Are Not the Same Metric

Three things that are easily confused:

- **Socket backlog** is the queue of **pending TCP connections waiting to be accepted** at the OS/server level. It does not directly cap the maximum number of concurrent HTTP requests.
- **`Executor`** provides the way to **run exchange handlers**. `server.setExecutor(Executors.newFixedThreadPool(4))` provides a 4-thread pool, but blocking I/O tasks can still bottleneck; this pool does not automatically protect against all forms of overload.
- **Concurrent request capacity** depends on clients, connection keep-alive, handler processing time, the executor, and machine resources. Do not deduce this number solely from the backlog or the number of contexts.

Example before `start()`:

~~~java
ExecutorService pool = Executors.newFixedThreadPool(4);
server.setExecutor(pool);
server.start();

// During application shutdown:
server.stop(5);
pool.shutdown();
~~~

*Illustrative snippet where `server` is already bound and contexts are attached; real systems must handle executor shutdown deadlines/forced shutdown.*

If `setExecutor` is not called, `HttpServer` uses a default executor provided by the implementation; `getExecutor()` may return `null` when you have not set one yourself. Do not assume the default is suitable for high-load applications.

**Important:** `stop(delay)` stops the server, but if you supplied your own `ExecutorService`, you must **manage that pool's lifecycle**. `stop` does not automatically shut down an external thread pool.

## 14. Security When Binding and Exposing Endpoints

`HttpServer` is very convenient for demos, but binding the wrong address can expose a service to external networks:

1. **Local testing:** bind `127.0.0.1` and use a client on the same machine. Do not use `0.0.0.0` just to "be safe when testing".
2. **Services requiring remote access:** choose an allowed interface, configure firewall/security groups, HTTPS, and proper authentication and authorization.
3. **HTTP does not encrypt by itself:** `HttpServer` with `http://` transmits payloads in plaintext over the network. `HttpsServer` requires TLS configuration via `HttpsConfigurator` and proper certificates/trust. Never disable verification just to get a connection working.
4. **A context path is not an ACL mechanism:** `/admin/` is not automatically protected just because the path contains the word admin. Handlers/filters must enforce authorization.
5. **Input protection:** method, query, headers, path, request body, and content size can all be controlled by the client; enforce size/time limits, validate/normalize, and do not trust these fields.
6. **Limit error details:** do not return stack traces, secrets, private file paths, or sensitive server data in 500 responses.
7. **Do not log tokens/credentials:** log only requestId, route, method, status, latency, and controlled context.
8. **Overload protection:** limit worker pool size, active requests, request body size, timeouts, and quotas at the application/proxy level.

When deploying in containers, `127.0.0.1` is the loopback **inside the container's network namespace**, not necessarily reachable from the host or other containers. Conversely, binding all interfaces combined with port publishing can expose the service unintentionally. Always verify the actual network environment.

## 15. Errors and Exceptions to Recognize

| Condition | Common Symptom | How to Handle |
| --- | --- | --- |
| Port already in use | `BindException`/`IOException` in `create(addr,...)` or `bind` | Check port and process, do not silently overwrite |
| Binding to an IP not present on the machine | `BindException` or I/O failure | Choose the right interface/IP |
| `bind(...)` on an already bound server | `BindException` | Bind only once |
| `start()` when not yet bound | `IllegalStateException` | Bind first, then start |
| `setExecutor(...)` after `start()` | `IllegalStateException` | Configure before start |
| `createContext("api", handler)` missing leading `/` | `IllegalArgumentException` | Use `"/api"` or `"/api/"` |
| Creating a duplicate context path | `IllegalArgumentException` | Register uniquely, manage lifecycle |
| `createContext(path,null)` or `setHandler(null)` | `NullPointerException` | Handler must not be null |
| Calling `setHandler` on a context that already has a handler | `IllegalArgumentException` | Attach handler once or use a delegate |
| URI path matches no context | HTTP 404 | Register appropriate path or return 404 per route |
| Handler only supports GET but receives POST | Must handle 405/Allow yourself | Do not assume HttpServer filters by method |
| Calling `getResponseBody()` before `sendResponseHeaders` | Lifecycle violation, I/O error | Send headers first |
| Declared fixed length differs from actual bytes sent | `IOException`/connection closed | Compute UTF-8 bytes accurately |
| Unbounded body reads | Out of memory or client attack | Apply limits and streaming |
| Forgetting to close exchange/output | Resources leaked, HTTP client hangs | Use try/finally and close streams |
| `stop(...)` then `start()` again | Server cannot be reused | Create a new HttpServer |

In production applications, do not just catch every `IOException` and return "200 OK". Distinguish **bind errors at startup**, **network I/O errors inside a handler**, and **HTTP responses due to invalid method/path**. If a handler has already called `sendResponseHeaders`, you cannot arbitrarily send a second response status on the same exchange; clean up and log instead of trying to write another 500 error.

## 16. Testing Routing and Responses Properly

Both programs use `java.net.http.HttpClient` to send real requests to the bound address. This simultaneously verifies:

- The socket bound properly and has an active port.
- `start()` has started accepting requests.
- Context matching selects the right handler.
- The handler sets response headers, status, and body.
- When no handler matches, the JDK returns 404 (when there is no root context).
- GET/POST methods can be distinguished separately by the handler.
- `removeContext(...)` updates routing accordingly.
- `stop(...)` and cleanup do not leave demo servers running indefinitely.

If you want to test manually when running the server as a long-lived program, you can use:

~~~bash
curl -i http://127.0.0.1:8080/hello
curl -i http://127.0.0.1:8080/api/users
curl -i -X POST http://127.0.0.1:8080/hello
~~~

*The curl commands are illustrative for a server **actually bound to port 8080 and running**. The two programs in this lesson use **port 0** and stop after the test, so you cannot assume those commands will connect to the demos. For the programs in sections 9–11, observe stdout as the deterministic test output.*

For CI, use port `0` and read the actual port from `getAddress()` so parallel tests avoid port collisions; assert HTTP status/body and always clean up in `finally`. Test edge-case paths like `/legacyExtra`, different-case paths, and nonexistent endpoints to catch prefix-matching mistakes.

## 17. Common Misconceptions

| Misconception | Consequence | How to Remember |
| --- | --- | --- |
| "`HttpServer.create()` already opened a port" | Unbound, client cannot connect | Call `bind` |
| "`create(addr,backlog)` starts accepting immediately" | Not started yet | Call `start()` after configuring |
| "Port `0` means an invalid port" | Misunderstands test binding | OS assigns a free port; read `getAddress().getPort()` |
| "Backlog 20 means at most 20 HTTP handlers" | Wrong network layer | Backlog is pending TCP connects |
| "`/foo` only matches exact `/foo`" | Can also match `/foobar` | Use `/foo/` and validate the route |
| "Context paths are case-insensitive" | Wrong routing | Literal, case-sensitive matching |
| "`/api/` also matches `/api`" | Different path prefix | Register/canonicalize explicitly |
| "`/users/{id}` is a JDK routing template" | Does not auto-extract id | Handler parses/validates path itself |
| "`createContext` can only be called once per server" | Misses multi-endpoint support | One server has many contexts |
| "With a root context, unmatched routes still auto-404" | Root catches all paths | Root handler must decide 404 itself |
| "Registering a context secures the endpoint" | Admin endpoint can be accessed without auth | Separate auth/authorization |
| "`setHandler` replaces an existing handler arbitrarily" | `IllegalArgumentException` | Attach once or use a delegate |
| "String.length() equals UTF-8 Content-Length" | Response body truncated/IO failure | Use `byte[].length` |
| "`sendResponseHeaders(200,0)` means no body" | 0 means chunked | Use -1 when there is no body |
| "`server.stop(0)` allows restarting" | Stopped server cannot be reused | Create a new instance |
| "`stop` shuts down external executors automatically" | Thread pool may stay alive | Shut down the pool separately |
| "Binding `0.0.0.0` always serves local only" | Can expose the service to the network | Choose interface and firewall |
| "This HTTP server uses TLS automatically" | `http://` is plaintext | Use `HttpsServer` + TLS |

## 18. Self-Check

**Question 1.** How does `HttpServer.create()` differ from `HttpServer.create(new InetSocketAddress("127.0.0.1",8080),16)`?

*Answer:* `create()` creates an **unbound** instance, so you must call `bind(addr,backlog)` afterward. The overload with an address **binds immediately**, but both still require `start()` to serve requests.

**Question 2.** When binding to port 0, how does a test client know the actual port?

*Answer:* Call `server.getAddress().getPort()` **after binding**, and use that port to build the client's URI. Do not hard-code port 0 into the client URL.

**Question 3.** Given `/`, `/app/`, and `/app/admin/`, which context does `/app/admin/users` select?

*Answer:* `/app/admin/` because it is the **longest matching literal prefix**.

**Question 4.** Why does `/legacyExtra` match the `/legacy` context?

*Answer:* `HttpServer` checks **character prefixes**, without requiring path segment boundaries. When you want a subtree, use `/legacy/` and validate the route.

**Question 5.** If there is a catch-all `/` context, will `/unknown` automatically receive 404?

*Answer:* Not necessarily. It matches root; the status depends on the root handler. Only when no context matches does it automatically return 404.

**Question 6.** When sending the UTF-8 body `Xin chào`, should you use `String.length()` for `responseLength`?

*Answer:* No. `sendResponseHeaders(status, responseLength)` uses **byte count**; encode to UTF-8 `byte[]` and use `bytes.length`.

**Question 7.** Does `stop(5)` allow calling `start()` again on the same instance?

*Answer:* No. `delay=5` is the maximum wait of about 5 seconds for in-flight exchanges before closing; a stopped server cannot be restarted.

**Question 8.** Does an `/admin/` context automatically require login?

*Answer:* No. A context only selects a handler by path; you need an `Authenticator`, filters, or appropriate security checks in the application.

## 19. Practice Exercises

1. Write a server using `HttpServer.create()`, `bind(127.0.0.1:0, 8)`, `createContext("/ping",...)`, `start()`, and call it with `HttpClient` to receive `200 pong`. Close the exchange and stop the server in `finally`.
2. Switch to `HttpServer.create(new InetSocketAddress("127.0.0.1",0),8)`, remove `bind(...)`, and verify the program still runs when the server binds immediately.
3. In `HttpServerBindDemo`, add `/helloExtra` to verify that `"/hello"` can be selected by prefix matching while the handler checks the exact path and returns 404.
4. In `HttpContextRoutingDemo`, change `/legacy` to `/legacy/`; test `/legacyExtra` and `/legacy/item` to observe the difference, keeping in mind that the root context can catch unmatched requests.
5. Add two contexts `/api/` and `/api/orders/`, use `exchange.getHttpContext().getPath()` to verify longest-prefix matching; test URLs with different casing.
6. Register a context with `createContext("/new/")` and then call `setHandler(...)` once. Try attaching another handler to observe the error and explain why this is not a hot-swap API.
7. Try sending a POST request to a handler that only accepts GET, verify status `405` and header `Allow: GET`; distinguish it from 404 when the path does not exist.
8. Replace an ASCII response with accented UTF-8 text, compute `bytes.length`, and verify the received body is not truncated.
9. Write a test where the server returns an empty response using `sendResponseHeaders(...,-1)` semantics, and compare it with chunked mode when passing `0`.
10. Configure a bounded pool before `start()`, send multiple concurrent requests, and measure the time; distinguish the role of the executor from the backlog.
11. Catch `BindException` when trying to run two servers on the same fixed port; do not silently switch to a random port in environments requiring a deterministic port.
12. Design a safe local health-check endpoint: bind loopback, GET method, bounded response, no secrets returned; explain what changes would be needed if it had to serve from another network.
13. Create a context with a `Filter` or `Authenticator` for `/admin/`, test unauthorized responses and logging; do not treat the path name as sufficient protection.
14. Create a startup/shutdown checklist: bind interface, port, contexts, handlers, filters, executor, start, metrics, `stop(delay)`, executor shutdown. Verify that the same instance cannot be restarted.

## Standard References

- [`HttpServer` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): `create`, `bind`, `createContext`, `setExecutor`, `start`, `stop`, longest literal prefix.
- [`HttpContext` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpContext.html): `setHandler`, `getPath`, filters, authenticator, attributes.
- [`HttpHandler` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpHandler.html): `handle(HttpExchange)`.
- [`HttpExchange` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpExchange.html): request/response lifecycle, headers, body streams, and `sendResponseHeaders`.
- [`HttpsServer` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpsServer.html): HTTPS server.
- [`HttpClient` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): HTTP client used for testing the server.
