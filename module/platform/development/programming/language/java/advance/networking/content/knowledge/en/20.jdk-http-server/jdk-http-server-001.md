# The jdk.httpserver Module and Capabilities of HttpServer and HttpsServer (Java 17+)

Java SE 17 includes the **`jdk.httpserver`** module, which provides an embedded, lightweight HTTP server API built right into the JDK. The module exports the `com.sun.net.httpserver` package with two core classes: **`HttpServer`** for receiving HTTP/1.1 over TCP and **`HttpsServer`** for receiving HTTP/1.1 over TLS (HTTPS). Together with `HttpHandler`, `HttpExchange`, and `HttpContext`, you can register endpoints, read requests, build status/headers/body responses, and dispatch worker threads without installing any additional web framework.

Lesson objectives:

1. Understand the `jdk.httpserver` module and distinguish it from **`java.net.http`** (HTTP client).
2. Know how to create/bind/start/stop `HttpServer`, register `HttpContext`, and understand **longest literal prefix matching** instead of automatic REST routing.
3. Grasp the lifecycle of an `HttpExchange`, especially streams and the `sendResponseHeaders(status, length)` rules for **length >0, =0, <0**.
4. Build a server that handles GET/POST, returns 405/404 properly, and avoids unbounded body reads.
5. Know how to use an executor, filters, and custom authorization; understand that backlog is **not** a concurrency limit.
6. Understand that `HttpsServer` requires an `HttpsConfigurator` attached to an `SSLContext` with a server identity key and certificate, and how the client trusts the server.
7. Identify technological limits: this is a **simple** embedded HTTP server, not a default replacement for an HTTP/2/WebSocket server, servlet container, or full-featured framework.
8. Run and analyze **two tested standalone Java 17+ programs**: one HTTP and one loopback HTTPS.

## 1. Where jdk.httpserver Fits in the Java Module System

| Module/package | Provides | Use when |
| --- | --- | --- |
| `jdk.httpserver` | Server API `HttpServer`, `HttpsServer`, `HttpExchange`, `Filter` | Accepting HTTP/HTTPS requests directly on the machine running Java |
| `java.net.http` | `HttpClient`, `HttpRequest`, `HttpResponse`, WebSocket client | Sending HTTP requests to another server |
| `java.base/java.net` | `Socket`, `ServerSocket`, `URI`, `InetSocketAddress` | Low-level networking |
| `java.base/javax.net.ssl` | `SSLContext`, `KeyManagerFactory`, `TrustManagerFactory` | TLS/certificate/trust |
| `java.base/java.security` | `KeyStore`, `SecureRandom` | Storing keys, certificates, and generating secure entropy |

`jdk.httpserver` is a **JDK-specific module** since Java 9; it exports two packages: `com.sun.net.httpserver` and `com.sun.net.httpserver.spi`. Even though the package name starts with `com.sun`, this API is officially documented by the JDK; do not confuse it with internal `sun.*` packages that have no compatibility guarantees. Because it is a JDK-specific module, **custom runtimes created with jlink** might not include it; you must verify before deploying.

~~~bash
java --version
java --describe-module jdk.httpserver
~~~

If the runtime reports that the module is not found, check your Java/JDK configuration and module resolution; do not assume the package has been removed from all Java 17 distributions. A **named module** application uses a `module-info.java` file as follows:

~~~java
// module-info.java fragment for a named module application.
module example.embedded.server {
    requires jdk.httpserver;
    requires java.net.http; // Only needed if the app also uses HttpClient.
}
~~~

The examples in this lesson are **classpath applications**: save them as `JdkHttpServerDemo.java` and `JdkHttpsServerDemo.java`, then run with `javac --release 17` and `java` from a full JDK. If using a module-path or a stripped-down Java runtime, ensure `jdk.httpserver` is resolved.

**Important version limitation:** `SimpleFileServer` and the `jwebserver` command were added in Java 18, not components to assume are available on Java 17. This lesson uses the `HttpServer/HttpsServer` APIs that actually exist in Java 17; it does not require the Java 18+ `java -m jdk.httpserver` command.

## 2. Components of an Embedded HTTP Server

~~~text
HTTP client
  GET /health HTTP/1.1
          |
          v
     TCP listener
     HttpServer.start()
          |
          v
Select HttpContext by longest path prefix
          |
          v
Executor runs HttpHandler.handle(HttpExchange)
          |
          +-- getRequestMethod()
          +-- getRequestURI()
          +-- getRequestHeaders()
          +-- getRequestBody()  -> InputStream
          |
          +-- getResponseHeaders()
          +-- sendResponseHeaders(status, bodyLength)
          +-- getResponseBody() -> OutputStream
          |
          v
Close InputStream/OutputStream, complete exchange
          |
          v
HTTP status + response headers + body
~~~

| Class/interface | Role |
| --- | --- |
| `HttpServer` | Binds IP address and port, listens on TCP, selects handler, dispatches requests |
| `HttpHandler` | Functional interface with `handle(HttpExchange) throws IOException` |
| `HttpContext` | A mapping from a root path to a handler, with its own filters/authenticator |
| `HttpExchange` | A request and its corresponding response, containing method, URI, headers, and body streams |
| `Headers` | Case-insensitive header map for header names |
| `Filter` / `Filter.Chain` | Pre/post-processing middleware for an exchange |
| `Executor` | Executes handler tasks, affecting concurrency capability |
| `HttpsServer` | Subclass of HttpServer, using SSLContext/TLS |
| `HttpsExchange` | Subclass of HttpExchange, adding `getSSLSession()` |
| `HttpsConfigurator` | Provides TLS configuration when accepting HTTPS connections |

An `HttpServer` **does not** automatically serialize/parse JSON, verify tokens, bind endpoints to GET/POST by method name, or provide dependency injection, the servlet API, OpenAPI, or a session system. Those responsibilities belong to application code or a framework built on top of it.

## 3. Creating a Server, Binding an Address, and Choosing an Executor

~~~java
// Java 17+ fragment: server listens only on loopback.
InetAddress loopback = InetAddress.getByAddress(
        new byte[] {127, 0, 0, 1});

HttpServer server = HttpServer.create(
        new InetSocketAddress(loopback, 0), 32);

server.createContext("/health", exchange -> {
    // Read request, send response, and finish exchange.
});

server.start();
~~~

Meaning:

- `127.0.0.1` is the IPv4 loopback address; other machines cannot reach it via this address.
- Port **0** lets the OS assign an available port. Retrieve the actual port after binding with `server.getAddress().getPort()`.
- Backlog **32** is the number of pending TCP connections waiting to be accepted according to configuration and OS limits; it is **not** the number of worker threads or maximum concurrent requests. If backlog ≤0, the JDK uses the system default value.
- You can use `HttpServer.create()` followed by `server.bind(address,backlog)` when you need to separate creation and binding.
- `server.start()` begins accepting connections on a background thread.

Do not expose the server on all interfaces (for example, binding `0.0.0.0`) just for testing. When remote access is needed, design a proper firewall/authentication/TLS/quotas and policy.

### Default Executor

The Java 17 Javadoc states that if no executor is configured, the server uses a default implementation that runs handler tasks on **the thread created by `start()`**. A long-blocking handler can force other requests to wait.

~~~java
// Java 17+ fragment: configure BEFORE calling start().
ExecutorService workers = Executors.newFixedThreadPool(4);
server.setExecutor(workers);
server.start();
~~~

Do not call `setExecutor` after `start()`: the API may throw `IllegalStateException`. Keep in mind that `Executors.newFixedThreadPool(4)` only caps the thread count at 4, while its **default queue is unbounded**, which is not optimal memory protection for a public server. Production requires bounded queues, overload policies, request limits, deadlines, and metrics. Set the executor before starting; when stopping the server, the application must still shut down the executor **that it created**.

## 4. Registering Paths with createContext: Longest Prefix

`HttpServer.createContext(String path,HttpHandler handler)` uses the root path as a **literal prefix** and selects the context with the **longest matching prefix** among matching contexts. Matching is **case-sensitive** and does not automatically encode/decode characters in the manner of a REST router.

~~~java
// Fragment: handler instances have already been provided.
server.createContext("/", rootHandler);
server.createContext("/api/", apiHandler);
server.createContext("/api/users/", usersHandler);
~~~

| Request path | Matching context |
| --- | --- |
| `/api/users/17` | `/api/users/` |
| `/api/orders/7` | `/api/` |
| `/hello` | `/` |
| `/API/users/17` | Does not match `/api/` due to case difference; if `/` exists, falls back to it |
| `/api` | Does not match `/api/` (missing trailing slash); if `/` exists, falls back |

**Warning:** If you create a context `"/foo"` without a trailing slash, **`"/foobar"` also matches**, because this is prefix matching rather than path-segment matching. The Javadoc recommends that context paths typically end with `/`. For a specific endpoint like `"/health"`, the handler should check `exchange.getRequestURI().getPath().equals("/health")` if an exact path is desired.

If no context matches, the built-in server automatically returns **404 Not Found**. However, if a context matches but the GET/POST method is not allowed by the handler, the server **does not automatically** generate a 405: the handler must inspect `exchange.getRequestMethod()` and return **405 Method Not Allowed** with an appropriate `Allow` header.

Do not use a literal `"/users/{id}"` assuming the JDK will automatically parse `id`; extracting path/query variables requires custom code, a custom parser, or a higher-level framework.

## 5. HttpExchange Lifecycle and Stream Ownership

An HTTP request/response is encapsulated in an `HttpExchange`. The Javadoc specifies the typical lifecycle:

1. Read `getRequestMethod()` to decide whether the method is allowed.
2. Use `getRequestHeaders()` if you need to check Content-Type, Authorization, Accept, length, etc.
3. Read `getRequestBody()` as an `InputStream` and close it at the right time; the body may be empty.
4. Set headers via `getResponseHeaders()` **before sending**.
5. Call `sendResponseHeaders(status,responseLength)` before writing the response body.
6. Write bytes to `getResponseBody()` and **close the OutputStream** to complete the exchange.

A simple handler:

~~~java
// Java 17+ fragment, exchange is passed into handle(...).
try (exchange) {
    String method = exchange.getRequestMethod();
    URI uri = exchange.getRequestURI();
    Headers requestHeaders = exchange.getRequestHeaders();

    try (InputStream requestBody = exchange.getRequestBody()) {
        // Read with bounds, validate, and process data.
    }

    byte[] bytes = "OK".getBytes(StandardCharsets.UTF_8);
    exchange.getResponseHeaders().set(
            "Content-Type", "text/plain; charset=UTF-8");
    exchange.sendResponseHeaders(200, bytes.length);
    try (OutputStream responseBody = exchange.getResponseBody()) {
        responseBody.write(bytes);
    }
}
~~~

This is a **fragment**; it requires imports/a class and does not run standalone. `HttpExchange` implements `AutoCloseable`, so `try(exchange)` is valid on Java 17. However, simply calling `close()` without sending headers/body is not how to build a valid response. If a handler throws an exception after response headers have already been sent, it is generally **no longer possible to safely change the status to 500**; you must log the internal error and close/abort the exchange according to policy.

### Request Headers and Response Headers

`getRequestHeaders()` is the map of request headers read from the client. `getResponseHeaders()` is a writable map before sending status/headers; header names are case-insensitive. You can add:

~~~java
exchange.getResponseHeaders().set(
        "Content-Type", "application/json; charset=UTF-8");
exchange.getResponseHeaders().set("Cache-Control", "no-store");
~~~

Set `Content-Type` to match the **returned body**, not the request body. Do not send sensitive information, allow header injection, or return error messages containing stack traces. If the application receives multiple values for the same header, handle them according to that field's semantics rather than assuming every header is single-valued.

### ResponseLength: Cases >0, =0, and -1

`sendResponseHeaders(int status,long responseLength)` is an API that is easy to misuse:

| responseLength | Behavior in JDK 17 | Example |
| --- | --- | --- |
| **> 0** | Fixed-length body of **exact n bytes**; must write the exact number of bytes | `sendResponseHeaders(200, payload.length)` |
| **= 0** | Uses **chunked transfer encoding** (HTTP/1.1), sending data in chunks until OutputStream is closed | Streaming body of unknown length in advance |
| **<= -1** | Sends no response body | 204 No Content, or responses where no body is appropriate |

**Do not confuse `sendResponseHeaders(200,0)` with Content-Length: 0.** Passing 0 in this API selects chunked encoding, not an "empty body". For statuses/methods that disallow a body such as 204/HEAD, follow HTTP semantics and specify a valid length (typically -1 for no body).

When length > 0, **writing fewer bytes can cause an IOException on OutputStream.close()**, writing more can also fail, and the TCP connection is aborted. Every length is in **bytes**, not characters in a Java String:

~~~java
// Fragment: UTF-8 has multi-byte characters, do not use message.length().
String message = "Xin chào";
byte[] payload = message.getBytes(StandardCharsets.UTF_8);
exchange.getResponseHeaders().set(
        "Content-Type", "text/plain; charset=UTF-8");
exchange.sendResponseHeaders(200, payload.length);
try (OutputStream out = exchange.getResponseBody()) {
    out.write(payload);
}
~~~

`OutputStream.close()` completes the exchange and also closes the input stream if it is not already closed. However, draining the request input when reasonable is still recommended because **closing input too early can prevent the TCP connection from being reused**. Do not read malicious bodies unboundedly just to "save reuse": enforcing limits and returning 413/aborting per policy takes priority.

### Bounded Body Reading

An HTTP server exposed to the Internet **should not** use unbounded `input.readAllBytes()`. Byte-counting pattern:

~~~java
// Fragment inside handler, maximum 4 KiB request body.
final int maxBytes = 4096;
ByteArrayOutputStream body = new ByteArrayOutputStream();
try (InputStream input = exchange.getRequestBody()) {
    byte[] buffer = new byte[512];
    int n;
    while ((n = input.read(buffer)) != -1) {
        if (n > maxBytes - body.size()) {
            // Send 413 per policy; stop storing data.
            break;
        }
        body.write(buffer, 0, n);
    }
}
~~~

This fragment does not return 413 by itself; the complete example right below does. Counting bytes avoids the risk of `String.length()` differing from UTF-8 bytes. For public servers, also add read timeouts, concurrent connection limits, and total resource caps; even a small payload sent extremely slowly by a client can tie up a handler thread for a long time.

## 6. Complete HTTP Program Running on Java 17+

The file **`JdkHttpServerDemo.java`** tests:

- GET `/health` → **200 OK**.
- POST `/echo` with a small body → **200 ECHO:hello**.
- GET `/echo` (matching context but wrong method) → **405 Method Not Allowed**.
- GET `/missing` (no matching context) → **404**.
- Server binds only IPv4 loopback and port 0, uses a 4-thread executor, and cleans up resources in try/finally.

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
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
import java.util.concurrent.TimeUnit;

public class JdkHttpServerDemo {
    private static final java.nio.charset.Charset UTF8 =
            StandardCharsets.UTF_8;
    private static final int MAX_BYTES = 4096;

    private static void send(
            HttpExchange ex, int status, String message)
            throws IOException {
        byte[] content = message.getBytes(UTF8);
        ex.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=UTF-8");
        ex.sendResponseHeaders(status, content.length);
        try (OutputStream out = ex.getResponseBody()) {
            out.write(content);
        }
    }

    private static void health(HttpExchange ex)
            throws IOException {
        try (ex) {
            if (!"GET".equals(ex.getRequestMethod())) {
                ex.getResponseHeaders().set("Allow", "GET");
                send(ex, 405, "Method Not Allowed");
                return;
            }
            try (InputStream in = ex.getRequestBody()) {
                in.transferTo(OutputStream.nullOutputStream());
            }
            send(ex, 200, "OK");
        }
    }

    private static void echo(HttpExchange ex)
            throws IOException {
        try (ex) {
            if (!"POST".equals(ex.getRequestMethod())) {
                ex.getResponseHeaders().set("Allow", "POST");
                send(ex, 405, "Method Not Allowed");
                return;
            }
            ByteArrayOutputStream content =
                    new ByteArrayOutputStream();
            try (InputStream in = ex.getRequestBody()) {
                byte[] temp = new byte[512];
                int n;
                while ((n = in.read(temp)) != -1) {
                    if (n > MAX_BYTES - content.size()) {
                        send(ex, 413, "Payload Too Large");
                        return;
                    }
                    content.write(temp, 0, n);
                }
            }
            send(ex, 200, "ECHO:" + content.toString(UTF8));
        }
    }

    private static void check(
            HttpClient client, HttpRequest request)
            throws Exception {
        HttpResponse<String> result = client.send(
                request, HttpResponse.BodyHandlers.ofString(UTF8));
        String display = request.method() + " "
                + request.uri().getPath()
                + " -> " + result.statusCode();
        if (!"/missing".equals(request.uri().getPath())) {
            display += " " + result.body();
        }
        System.out.println(display);
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getByAddress(
                new byte[]{127, 0, 0, 1});
        HttpServer server = HttpServer.create(
                new InetSocketAddress(loopback, 0), 32);
        ExecutorService workers =
                Executors.newFixedThreadPool(4);

        server.createContext("/health", JdkHttpServerDemo::health);
        server.createContext("/echo", JdkHttpServerDemo::echo);
        server.setExecutor(workers);
        server.start();

        try {
            String root = "http://127.0.0.1:"
                    + server.getAddress().getPort();
            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();

            check(client, HttpRequest.newBuilder(
                    URI.create(root + "/health"))
                    .timeout(Duration.ofSeconds(5))
                    .GET().build());

            check(client, HttpRequest.newBuilder(
                    URI.create(root + "/echo"))
                    .timeout(Duration.ofSeconds(5))
                    .header("Content-Type",
                            "text/plain; charset=UTF-8")
                    .POST(HttpRequest.BodyPublishers.ofString(
                            "hello", UTF8))
                    .build());

            check(client, HttpRequest.newBuilder(
                    URI.create(root + "/echo"))
                    .timeout(Duration.ofSeconds(5))
                    .GET().build());

            check(client, HttpRequest.newBuilder(
                    URI.create(root + "/missing"))
                    .timeout(Duration.ofSeconds(5))
                    .GET().build());
        } finally {
            server.stop(1);
            workers.shutdown();
            if (!workers.awaitTermination(
                    5, TimeUnit.SECONDS)) {
                workers.shutdownNow();
            }
        }
    }
}
~~~

**Compile and run:**

~~~bash
javac --release 17 JdkHttpServerDemo.java
java JdkHttpServerDemo
~~~

**Verified stdout on JDK 24 after compiling with `--release 17`:**

~~~text
GET /health -> 200 OK
POST /echo -> 200 ECHO:hello
GET /echo -> 405 Method Not Allowed
GET /missing -> 404
~~~

**Reading the output:** `GET /health` is handled by the GET handler; `POST /echo` reads the body and echoes it back; `GET /echo` still hits the matching context, but the handler actively returns 405, while `/missing` gets 404 from the built-in server. The program only prints the status for 404 because the default HTML body may vary across providers/versions.

This is a **loopback lab**, not a public REST service. It does not yet check Content-Type, exact path, authentication, or request sending rate. `health()` actively drains input into a null stream, which is fine for a bodyless GET test but should not be used unconditionally with untrusted clients because it could end up reading a huge or extremely slow body. `echo()` has a 4096-byte max but no dedicated read deadline; when exceeding the limit and returning 413 before the body finishes, the connection may not be reused. Those are deliberately acknowledged limitations, not a complete production template.

## 7. How Does HttpsServer Extend HttpServer?

`HttpsServer extends HttpServer`. Therefore, most of the **context, handler, filter, executor, bind/start/stop** APIs are identical. The difference lies in **TLS**:

~~~text
HttpServer:
  HTTP bytes (plaintext) -> HttpExchange -> handler -> response

HttpsServer:
  TLS handshake (server identity + crypto)
          |
          v
  HTTP bytes inside encrypted TLS connection
          |
          v
  HttpsExchange -> handler -> response over TLS
~~~

`HttpsServer` requires attaching an `HttpsConfigurator` containing an initialized `SSLContext`. The **server's** `SSLContext` must have **key material** (private key + certificate chain) to authenticate the server. Merely calling `HttpsServer.create()`, `start()`, and hoping for automatic TLS is not enough. Using `SSLContext.getDefault()` also does not guarantee a certificate/private key suitable for the server role.

| HTTPS component | Required? | Why |
| --- | --- | --- |
| `HttpsServer` | Yes | HTTP over TLS listener |
| `HttpsConfigurator` | Yes | Provides SSLContext/TLS settings |
| Server `KeyStore` (PKCS12) | Usually yes | Holds server private key and certificate |
| `KeyManagerFactory` | Yes if using a KeyStore | Loads and supplies server keys for TLS |
| Initialized `SSLContext` | Yes | TLS engine performing handshake and encryption |
| Client `TrustManagerFactory` / truststore | Per how client verifies server | Verifies chain/trust |
| Certificate hostname/SAN | Yes for verification | Prevents host name mismatch/spoofing |
| `HttpsExchange.getSSLSession()` | Optional | Inspects TLS state on the exchange |
| Application authorization | Still must be implemented | TLS does not automatically grant read/write permissions |

### Creating the Server-Side SSLContext

~~~java
// Java 17+ fragment, keys is a loaded PKCS12 KeyStore.
KeyManagerFactory kmf = KeyManagerFactory.getInstance(
        KeyManagerFactory.getDefaultAlgorithm());
kmf.init(keys, password);

SSLContext serverTls = SSLContext.getInstance("TLS");
serverTls.init(
        kmf.getKeyManagers(),
        null, // Demo does not require a client certificate.
        new SecureRandom());
~~~

This is a **fragment**: keys/password/handler are not defined yet; see the complete code in section 9. The `SSLContext` here loads the server key/cert; the client truststore is **separate**. **Successful HTTPS does not automatically provide user authentication**. If you want mTLS, the server needs appropriate trust managers to verify the client certificate and `SSLParameters.setNeedClientAuth(true)` configured; the client must also have its own identity. Even with mTLS, the application still needs authorization per endpoint and resource.

### HttpsConfigurator Can Customize Parameters

~~~java
// Java 17+ fragment, serverTls is an initialized SSLContext.
https.setHttpsConfigurator(new HttpsConfigurator(serverTls) {
    @Override
    public void configure(HttpsParameters params) {
        SSLParameters sslparams =
                getSSLContext().getDefaultSSLParameters();
        // Depending on policy, you can choose protocols/cipher suites/client auth.
        // Do not enable needClientAuth without configuring mTLS.
        params.setSSLParameters(sslparams);
    }
});
~~~

Do not force an arbitrary cipher suite/TLS version just to bypass a handshake error; apply TLS policies according to security requirements, Java provider capabilities, and client support. The `HttpsExchange.getSSLSession()` API provides information about the TLS session on the exchange; it does not replace proof of user authentication or business-level authorization.

## 8. Generating Certificates for Loopback HTTPS with keytool

To test HTTPS properly, you need a server keystore containing the **private key** and a **client-side truststore** containing only the **explicitly trusted public certificate**.

~~~text
server.p12
  - server private key    (SECRET)
  - certificate (SAN localhost and 127.0.0.1)

server.cer
  - public certificate    (no private key)

trust.p12
  - trusted certificate   (used by client to verify server)
~~~

**Do not** give `server.p12` (the private key) to the client. In production, you need a managed CA/chain, rotation, secret access controls, and TLS policies. The 1-day self-signed certificate in this lab is a **test certificate**, not for public services.

Run the following `keytool` commands in a **temporary lab directory**:

~~~bash
# Three illustrative Bash commands; password changeit is ONLY for the lab.
keytool -genkeypair -alias loopback -keyalg RSA -keysize 2048 \
  -validity 1 -storetype PKCS12 -keystore server.p12 \
  -storepass changeit -keypass changeit -dname "CN=localhost" \
  -ext "SAN=DNS:localhost,IP:127.0.0.1" -noprompt

keytool -exportcert -alias loopback -keystore server.p12 \
  -storepass changeit -file server.cer

keytool -importcert -alias loopback -file server.cer \
  -keystore trust.p12 -storetype PKCS12 \
  -storepass changeit -noprompt
~~~

On Windows PowerShell, type each `keytool` command **on a single line** or use PowerShell's line continuation character; the trailing `\` in the Bash example is **not** PowerShell line-continuation syntax.

**Why include a SAN?** The client program will connect to `https://127.0.0.1:port/secure`, so the certificate must have `IP:127.0.0.1` in its Subject Alternative Name. Do not rely on `CN=localhost` to satisfy modern hostname/IP checks.

Set environment variables. Bash example:

~~~bash
export HTTP_LAB_SERVER_P12="$PWD/server.p12"
export HTTP_LAB_TRUST_P12="$PWD/trust.p12"
export HTTP_LAB_P12_PASSWORD="changeit"
~~~

Windows PowerShell example:

~~~powershell
$env:HTTP_LAB_SERVER_P12 = (Resolve-Path .\server.p12).Path
$env:HTTP_LAB_TRUST_P12 = (Resolve-Path .\trust.p12).Path
$env:HTTP_LAB_P12_PASSWORD = "changeit"
~~~

This is an intentionally simple password **for learning only**; never put production passwords in source code, shell history, or repositories. After running the lab, delete the test keystore/cert files from the lab directory and never commit private keys. In real applications, use a secret manager or key management infrastructure instead of hardcoded values or uncontrolled shared environment variables.

### Never Use an Accept-All TrustManager to Fix TLS Errors

If the client reports `SSLHandshakeException`, `PKIX path building failed`, or a SAN mismatch, the fix is to check the truststore, chain, expiry, and URI host/IP—not to attach a TrustManager that trusts every certificate or disable endpoint identification. Only when the client properly verifies the server's identity does HTTPS provide the expected server authentication protection.

## 9. Complete Runnable HTTPS Program on Java 17+

Save the following code as **`JdkHttpsServerDemo.java`**. Run it after creating `server.p12`, `trust.p12`, and the three environment variables from section 8. The program only uses APIs present in Java 17.

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpsConfigurator;
import com.sun.net.httpserver.HttpsExchange;
import com.sun.net.httpserver.HttpsServer;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.SecureRandom;
import java.time.Duration;
import java.util.Arrays;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;

public class JdkHttpsServerDemo {
    private static final java.nio.charset.Charset UTF8 =
            StandardCharsets.UTF_8;

    private static KeyStore load(
            String envName, char[] password) throws Exception {
        KeyStore store = KeyStore.getInstance("PKCS12");
        try (InputStream in = Files.newInputStream(
                Path.of(System.getenv(envName)))) {
            store.load(in, password);
        }
        return store;
    }

    private static SSLContext serverContext(
            KeyStore keys, char[] password) throws Exception {
        KeyManagerFactory kmf = KeyManagerFactory.getInstance(
                KeyManagerFactory.getDefaultAlgorithm());
        kmf.init(keys, password);

        SSLContext ssl = SSLContext.getInstance("TLS");
        ssl.init(
                kmf.getKeyManagers(),
                null, // Do not require client certificate in the lab.
                new SecureRandom());
        return ssl;
    }

    private static SSLContext clientContext(
            KeyStore trusted) throws Exception {
        TrustManagerFactory tmf =
                TrustManagerFactory.getInstance(
                        TrustManagerFactory.getDefaultAlgorithm());
        tmf.init(trusted);

        SSLContext ssl = SSLContext.getInstance("TLS");
        ssl.init(null, tmf.getTrustManagers(), new SecureRandom());
        return ssl;
    }

    private static void handle(
            HttpExchange exchange) throws IOException {
        try (exchange) {
            try (InputStream input = exchange.getRequestBody()) {
                input.transferTo(OutputStream.nullOutputStream());
            }
            boolean secure = exchange instanceof HttpsExchange
                    && ((HttpsExchange) exchange)
                            .getSSLSession() != null;

            byte[] bytes =
                    (secure ? "TLS-OK" : "TLS-MISSING")
                            .getBytes(UTF8);
            exchange.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=UTF-8");
            exchange.sendResponseHeaders(200, bytes.length);

            try (OutputStream output = exchange.getResponseBody()) {
                output.write(bytes);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        char[] password =
                System.getenv("HTTP_LAB_P12_PASSWORD").toCharArray();

        KeyStore serverKeys =
                load("HTTP_LAB_SERVER_P12", password);
        KeyStore clientTrust =
                load("HTTP_LAB_TRUST_P12", password);

        InetAddress loopback = InetAddress.getByAddress(
                new byte[]{127, 0, 0, 1});
        HttpsServer server = HttpsServer.create(
                new InetSocketAddress(loopback, 0), 16);
        ExecutorService workers =
                Executors.newFixedThreadPool(2);

        server.setHttpsConfigurator(
                new HttpsConfigurator(
                        serverContext(serverKeys, password)));
        server.createContext(
                "/secure", JdkHttpsServerDemo::handle);
        server.setExecutor(workers);
        server.start();

        try {
            HttpClient client = HttpClient.newBuilder()
                    .sslContext(clientContext(clientTrust))
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();

            URI uri = URI.create(
                    "https://127.0.0.1:"
                            + server.getAddress().getPort()
                            + "/secure");
            HttpRequest request =
                    HttpRequest.newBuilder(uri)
                    .timeout(Duration.ofSeconds(5))
                    .GET()
                    .build();

            HttpResponse<String> response =
                    client.send(
                            request,
                            HttpResponse.BodyHandlers.ofString(UTF8));
            System.out.println(
                    "httpsStatus=" + response.statusCode());
            System.out.println(
                    "httpsBody=" + response.body());
        } finally {
            server.stop(1);
            workers.shutdown();
            if (!workers.awaitTermination(
                    5, TimeUnit.SECONDS)) {
                workers.shutdownNow();
            }
            Arrays.fill(password, '\0');
        }
    }
}
~~~

Compile/run after generating certificates:

~~~bash
javac --release 17 JdkHttpsServerDemo.java
java JdkHttpsServerDemo
~~~

**Stdout observed when compiling with `--release 17` and running on JDK 24:**

~~~text
httpsStatus=200
httpsBody=TLS-OK
~~~

Meaning:

1. The server uses `KeyManagerFactory` to load the private key/certificate from `server.p12`, creating `SSLContext` and `HttpsConfigurator` **before** starting.
2. The client uses `TrustManagerFactory` to read **`trust.p12` containing the public certificate** as its trust anchor; the certificate has a SAN IP matching the URL. There is no code disabling certificate verification.
3. The handler runs inside `HttpsExchange` and sees `SSLSession`; the `"TLS-OK"` string is generated by the handler itself, not an automatic JDK feature.
4. The server still registers contexts/handlers and manages executor/stop just like `HttpServer`.
5. The demo does not check authorization or persist data: completing HTTPS **does not mean a production API is sufficiently secured**.

If your environment lacks `keytool`, the files have not been created, the password is wrong, the certificate is expired, the TLS provider is unsuitable, or localhost is blocked, you may encounter exceptions; do not treat this as guaranteed stdout on every environment. Do not call the client with `https://localhost` unless the cert/URL match the appropriate SAN. Do not fix it by disabling hostname verification.

## 10. Filter, HttpContext, and Cross-Cutting Handling Around Handlers

`HttpContext` can have `Filter`, `Authenticator`, and attributes for request processing. `Filter` runs **before/after the handler** via `Filter.Chain`, commonly used for correlation IDs, logging, policy checks, or observability.

Java 17 provides a factory:

~~~java
// Fragment, ctx is an already-created HttpContext.
ctx.getFilters().add(
        Filter.beforeHandler(
                "attach demo request ID",
                exchange -> {
                    exchange.setAttribute("requestId", "demo-1");
                    exchange.getResponseHeaders().set(
                            "X-Request-ID", "demo-1");
                }));
~~~

This example only illustrates how to register a filter and does not run standalone; you need to import `com.sun.net.httpserver.Filter` and create `ctx`. In production, the request ID **must be generated uniquely per request** and must not leak secrets. A custom filter can override `doFilter(HttpExchange,Filter.Chain)`, calling `chain.doFilter(exchange)` to continue the chain; if rejecting a request, the filter must send a valid response itself. Never both send a response in the filter and continue so the handler sends a status a second time.

`BasicAuthenticator`/`DigestAuthenticator` support some HTTP authentication mechanisms, but **do not replace authorization**. Basic credentials are Base64-encoded, **not encrypted securely**: if using Basic, you must have proper TLS and check roles/permissions for each resource. Do not assume the framework automatically adds CORS, CSRF protection, or OAuth/JWT verification.

## 11. Threading, Backlog, Load Limits, and Graceful Stop

Distinguish between:

- **Backlog:** TCP connection queue waiting to be accepted, OS-dependent.
- **Executor threads:** execute `HttpHandler.handle()`, which can be held for a long time by slow request bodies or DB calls.
- **Task queue:** in a default fixed thread pool it is typically unbounded, which can grow RAM usage under overload.
- **Open connections/exchanges:** must be bounded separately, not guaranteed by backlog alone.
- **Timeouts:** limits on connection, body reading, downstream processing, and application work; without them, slow clients exhaust workers.

A real service should limit request size, read throughput, concurrent exchanges, response size, queue depth, per-user/IP rate, and set deadlines for dependencies. Measure active handler count, queue length, latency percentiles, HTTP statuses, and TLS handshake failure classes. Do not log raw credentials or sensitive bodies.

### What Does stop(delay) Mean?

The `HttpServer.stop(int delay)` Javadoc states that the server closes the listening socket, stops accepting new exchanges, and waits **until all current handler exchanges have completed or `delay` seconds have elapsed (whichever comes first)**. After that, any remaining open TCP connections are closed, the server's background thread terminates, and **a stopped object cannot be restarted**.

~~~java
// Java 17+ fragment, server and workers are owned by the application.
server.stop(5); // Wait up to about 5 seconds for in-flight exchanges.
workers.shutdown();
if (!workers.awaitTermination(10, TimeUnit.SECONDS)) {
    workers.shutdownNow();
}
~~~

- `stop(0)` stops immediately without waiting for handlers to finish.
- `stop(5)` can wait up to about 5 seconds but **does not guarantee every request succeeds**, because handlers may be cut off when the timeout expires.
- `stop(-1)` is invalid.
- After stopping, **you cannot call start again** on the same instance; you must create a new server.
- `workers.shutdown()` is a separate executor management responsibility; `server.stop()` does not automatically close all business resources.

When shutting down a server with an in-flight POST updating a DB, closing the socket does not mean the transaction is rolled back. You need idempotency keys, transaction policies, error reporting, and separate request state checks.

## 12. Security Notes and Technological Limitations

### Plaintext HTTP vs. HTTPS

`HttpServer` only provides unencrypted HTTP: do not use it to send Bearer tokens, passwords, or private data over untrusted networks. `HttpsServer` adds TLS, but a server certificate does not mean a user is authorized. For public APIs, you still need authn/authz, secret rotation, quotas, origin policies, request parsing, and safe logging.

### This Is Not a Full-Featured HTTP Framework

This JDK 17 module supports a **basic HTTP/1.1 server**, with no guarantee of being an HTTP/2 server, HTTP/3 server, dedicated WebSocket server, or servlet container. An `HttpClient` using HTTP/2 to another system does not make `HttpServer` support HTTP/2. When you need complex request routing, JSON body mapping, middleware, HTTP/2, WebSocket server support, metrics/traces, production certificate rotation/mTLS, or high throughput, consider a framework/servlet container/reverse proxy designed for those requirements.

### Running on Localhost Does Not Replace Access Control

Loopback reduces exposure for labs, but other processes on the same machine can still send requests. Internal admin endpoints must have explicit policies even when bound only to loopback, especially if accessed from a browser/desktop app or handling sensitive data. Do not log request headers/secrets without filtering.

### CORS Is Not Authentication

The JDK server does not automatically apply CORS for browser APIs. If a web app from another origin calls an endpoint, you must configure CORS response headers, `OPTIONS` preflight, and credentials policies accurately. Browser CORS is only a browser-enforced protection; Java HTTP clients are not blocked by browser CORS, and attackers can still call endpoints directly if authentication is missing.

### Input Validation and Parsing

- Check exact paths to avoid unintended prefix routes.
- Decode URI/path/query properly, avoiding traversal when mapping to the filesystem.
- Check method and content type; validate schema/required fields.
- Count **bytes**, not just characters; enforce max-size/deadlines.
- Limit header count/header length appropriately for the runtime/edge proxy.
- Do not let clients directly control the server's outbound HTTP target without SSRF protections.
- Do not return raw exceptions/stack traces in responses.
- Close streams and exchanges on all error paths.

## 13. Common Errors

| Symptom | Primary cause | How to fix |
| --- | --- | --- |
| `com.sun.net.httpserver` not found | Missing module in custom runtime/module resolution | `java --describe-module jdk.httpserver`, requires/add-modules |
| Cannot run `jwebserver` on Java 17 | Confused with Java 18+ feature | Use HttpServer API or upgrade JDK |
| `BindException: Address already in use` | Port is busy | Use port 0 in tests, verify bind |
| Remote cannot connect | Server only bound to loopback | Expected for tests; production needs network/security plan |
| Request gets 404 | No context matches literal prefix | Check path, case sensitivity, trailing slash |
| Request `/foobar` hits context `/foo` | Prefix-matching context | Use path `/foo/` or check exact path |
| GET to POST-only route does not return 405 | Handler did not check method | Compare request method, return 405 + Allow |
| Server is slow when handler blocks | Default executor or insufficient threads/deadlines | Proper executor, bounded queue, and I/O timeouts |
| `setExecutor` throws IllegalStateException | Called after start | Set before `server.start()` |
| Client response hangs | Forgot to send headers/close output | `sendResponseHeaders` before body; always close |
| IOException when closing output | Wrote fewer/more bytes than declared | Use UTF-8 `payload.length`, not `String.length` |
| `sendResponseHeaders(200,0)` produces chunked | 0 means chunked, not no body | Use -1 if truly no body |
| HTTP/1.1 connection not reused | Closed request body before draining | Bounded drain or accept connection close |
| 413 returned but client keeps sending | Client already buffered data/has in-flight bytes | Close/limit connection per policy |
| Server memory grows | Unbounded body/`readAllBytes`/queue | Max bytes, bounded queues, slow-client protection |
| HTTPS handshake failed | Missing HttpsConfigurator or key/cert | SSLContext with key manager, set config before start |
| `PKIX path building failed` | Client does not trust server cert | Correct truststore/CA chain |
| `No subject alternative names present` | SAN does not match URL/IP | Generate proper SAN, do not disable hostname verification |
| HTTPS enabled but no user auth | TLS only protects connection/server identity | Add authentication/authorization |
| App exits main but thread pool stays alive | App-owned executor not shut down | Stop server, shut down executor |
| `stop()` then `start()` does not run | HttpServer cannot be reused after stop | Create a new instance |

### Debugging Checklist

~~~text
1. JDK: java --version; java --describe-module jdk.httpserver
2. Bind: loopback/public address, port, firewall, backlog
3. Context: longest path prefix, case sensitivity, trailing slash
4. Handler: request method, URI, Content-Type, body limit
5. Response: headers before body, exact byte length, close streams
6. Executor: set before start, active/queued tasks, blocking I/O
7. TLS: server keystore, SSLContext, HttpsConfigurator, SAN/trust
8. Shutdown: stop(delay), executor shutdown, pending handlers
~~~

When troubleshooting TLS, first inspect the certificate chain, SAN, expiration date, and trust roots; **never disable SSL certificate verification** to make errors disappear. When troubleshooting routing, log the route template and method rather than sensitive tokens/payloads.

## 14. Self-Check Exercises

**Q1.** Is `jdk.httpserver` the same as `java.net.http`?  
**Answer:** No. The first module is the JDK's embedded HTTP/HTTPS **server** API, while the second provides the HTTP/WebSocket **client**.

**Q2.** What are the core classes for receiving HTTP in JDK 17?  
**Answer:** `HttpServer`, `HttpHandler`, `HttpExchange`, and `HttpContext` from `com.sun.net.httpserver`.

**Q3.** Why can a `"/foo"` context handle `"/foobar"`?  
**Answer:** Because path matching uses **longest literal prefix**, not exact segment routing.

**Q4.** Does setting backlog=32 mean 32 handlers run in parallel?  
**Answer:** No. Backlog is the TCP accept queue; concurrency is determined by the executor, workload, and OS.

**Q5.** If `setExecutor` is not called, where do handlers run?  
**Answer:** The default implementation uses a thread created when `start()` is called, which can become a bottleneck if handlers block.

**Q6.** Can `setExecutor` be called after `start`?  
**Answer:** Not in the valid lifecycle; the API may throw `IllegalStateException`. Call it before `start`.

**Q7.** Who must return 405 when a GET hits a POST-only context?  
**Answer:** The application's own handler/filter, typically with `Allow: POST`. Context matching only looks at the path.

**Q8.** Is sending a UTF-8 string with `sendResponseHeaders(status, message.length())` safe?  
**Answer:** No. Length is in **bytes**, so use `message.getBytes(UTF_8).length`.

**Q9.** Does `sendResponseHeaders(200,0)` mean no body?  
**Answer:** No. Value 0 selects chunked transfer; use -1 for no body when valid.

**Q10.** Why is closing `getResponseBody()` required?  
**Answer:** To complete the exchange and release resources; failing to close it can leave the client/connection hanging.

**Q11.** What does `HttpsServer` need besides create/start?  
**Answer:** An `HttpsConfigurator` containing an `SSLContext` initialized with an appropriate **server identity key/certificate**.

**Q12.** Does the client truststore need the server private key?  
**Answer:** No. It only needs the trusted public CA/certificate; the private key stays on the server.

**Q13.** Why is SAN IP=127.0.0.1 important?  
**Answer:** The demo client calls a URL with IP 127.0.0.1, and the TLS client verifies identity against the certificate SAN.

**Q14.** Does HTTPS automatically perform per-user authorization?  
**Answer:** No. TLS encrypts and authenticates the server; the application still needs authentication and authorization.

**Q15.** Why is `Executors.newFixedThreadPool(4)` not enough to prevent OOM?  
**Answer:** Its default queue can be unbounded; request bodies and response buffers must also be bounded.

**Q16.** Does `server.stop(5)` guarantee that all running POSTs finish committing?  
**Answer:** No. It only waits up to about 5 seconds; the server may cut off connections when the timeout expires.

**Q17.** After stopping, can you restart the same `HttpServer`?  
**Answer:** No. Create a new instance.

**Q18.** Is `jwebserver` a Java 17 API?  
**Answer:** No. This tool, along with `SimpleFileServer`, was added in Java 18.

**Q19.** When should you choose a framework instead of `HttpServer`?  
**Answer:** When you need routing/JSON/security/observability/HTTP/2/WebSocket server features, high load, and complex production lifecycles.

**Q20.** Why should you never use a `TrustManager` that trusts all certificates?  
**Answer:** Because it removes server identity verification, exposing you to MITM attacks; fix the certificate/truststore/SAN properly instead.

## 15. Official Documentation

- Oracle Java SE 17 — `jdk.httpserver` module and exported packages: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/module-summary.html
- Oracle Java SE 17 — `com.sun.net.httpserver` package and HTTP/HTTPS scope: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/package-summary.html
- Oracle Java SE 17 — `HttpServer`: create/bind/start/stop, context prefix, executor: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html
- Oracle Java SE 17 — `HttpHandler`: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpHandler.html
- Oracle Java SE 17 — `HttpContext`: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpContext.html
- Oracle Java SE 17 — `HttpExchange`: request/response lifecycle, length, close: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpExchange.html
- Oracle Java SE 17 — `Filter`: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/Filter.html
- Oracle Java SE 17 — `Headers`: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/Headers.html
- Oracle Java SE 17 — `HttpsServer`: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpsServer.html
- Oracle Java SE 17 — `HttpsConfigurator`: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpsConfigurator.html
- Oracle Java SE 17 — `HttpsExchange`: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpsExchange.html
- Oracle Java SE 17 — `SSLContext` and TLS: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLContext.html
- Oracle Java SE 17 — `HttpClient` used for testing: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html
- Oracle Java SE 18 — `SimpleFileServer/jwebserver` from 18: https://docs.oracle.com/en/java/javase/18/docs/api/jdk.httpserver/module-summary.html
