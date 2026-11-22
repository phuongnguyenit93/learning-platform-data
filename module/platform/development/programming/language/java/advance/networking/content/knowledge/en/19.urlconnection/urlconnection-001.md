# URL.openConnection, Protocol Handlers, and the Pre/Post-Connect Lifecycle

## 1. Objectives and Overview

In Java networking, **java.net.URL** describes a resource address, while **java.net.URLConnection** represents an object capable of establishing a connection to that resource. When we write:

~~~java
URL url = new URL("https://example.com/data");
URLConnection connection = url.openConnection();
~~~

we **have not automatically fetched HTTP data or performed a TLS handshake**. According to the Java 17 URL contract, **openConnection() creates a new URLConnection via the protocol's URLStreamHandler**, but **does not establish an actual network connection at object creation time**. Before connecting, the application has the opportunity to set request properties, timeouts, cache flags, and other options.

Afterward, the connection can be established **explicitly** via **connection.connect()**, or **implicitly** when the application invokes an operation that requires a connection, such as **getInputStream()**, **getContentLength()**, or certain response-reading methods. Once connected, most request configuration must be considered **locked**, because modifying headers, the method, or configuration options at this point is too late.

This lesson answers five core questions:

1. **What does URL.openConnection() do, and what does it not do?**
2. **How is a URLStreamHandler (protocol handler) selected, and what type of URLConnection does it create?**
3. **How do pre-connect and post-connect differ; which method calls can implicitly trigger connect?**
4. **When using HTTP/HTTPS, how should request headers, responses, timeouts, proxies, errors, and cleanup be handled?**
5. **How can we verify this behavior ourselves with a real, runnable Java 17 program, including a custom protocol handler?**

### Simple Model

~~~text
URL("http://127.0.0.1:PORT/hello")
               |
           openConnection()
               |
   URLStreamHandler for "http"
               |
      HttpURLConnection object
      [request not yet established]
               |
      setRequestProperty(...)
      setConnectTimeout(...)
      setReadTimeout(...)
      setRequestMethod("GET")
               |
     connect() or getInputStream()
               |
       [connected / I/O]
               |
     read status, headers, and body
               |
      close InputStream, disconnect()
~~~

**Key concept to remember:** A URLConnection object represents **one specific configuration/connection attempt**. It is not an **HttpClient connection pool** and is not designed to have its URL or method swapped and be reused like a new request.

## 2. Roles of URL, URLConnection, URLStreamHandler, and Subclasses

| Component | Responsibility | Notes |
| --- | --- | --- |
| **URL** | Holds protocol, host, port, path, query, fragment; provides openConnection | Creating a URL does not mean sending an HTTP request |
| **URLStreamHandler** | Knows how to parse and open a URL for a scheme/protocol | The handler is selected when the URL is created/initialized per API rules |
| **URLStreamHandler.openConnection(URL)** | Creates a URLConnection appropriate for the protocol | Does not require a network connection at the time of return |
| **URLConnection** | Configures and accesses the resource pointed to by the URL | Has two phases: unconnected and connected |
| **HttpURLConnection** | URLConnection specialized for **http** | Has method, status code, redirects, error stream, disconnect |
| **HttpsURLConnection** | HTTP over TLS/HTTPS, a subclass of HttpURLConnection | Adds TLS peer, certificate, and HTTPS verification |
| **JarURLConnection** | Accesses contents inside a JAR URL | Not every URLConnection is HTTP |
| **Proxy** and **ProxySelector** | Routes the connection path when supported by the handler | A proxy does not determine the URL protocol or resource content |

Correct example regarding object types:

~~~java
URLConnection generic =
        new URL("http://127.0.0.1:8080/").openConnection();

if (generic instanceof HttpURLConnection http) {
    http.setRequestMethod("GET");
}
~~~

The example above **only illustrates the class/type**; a real HTTP server will be needed if you want to perform network I/O. Do not blindly cast every URLConnection to HttpURLConnection: a **file:** or **jar:** URL will not be HTTP.

For HTTPS URLs, **HttpsURLConnection** is still an HttpURLConnection with added SSL/TLS logic. Therefore **instanceof HttpURLConnection** can be true for both HTTP and HTTPS, but **HttpsURLConnection** should not be treated like plaintext HTTP.

### URL and URI Are Not Identical

**URI** is a syntactic identifier, whereas **URL** is tied to selecting a protocol handler/access mechanism. In Java 17, you can use:

~~~java
URI uri = URI.create("https://example.com/data");
URL url = uri.toURL();
URLConnection connection = url.openConnection();
~~~

The snippet above requires importing **java.net.URI, URL, URLConnection** and handling exceptions in a real program. Never take an arbitrary user-supplied string and open a URL directly without validating the scheme, host, port, and access permissions (see the security section).

**Version note:** Some URL constructors are deprecated in newer Java versions; in modern JDKs, creating a URI first and converting it to a URL when needed is generally preferred. This lesson still uses the **Java 17** API in accordance with the learning scope.

## 3. Protocol Handlers: Why Does the Same openConnection Produce Different Results?

### 3.1. URL Selects a Handler by Protocol

In a URL:

~~~text
https://api.example.com:443/orders?id=42
  |           |       |         |
protocol     host    port   path + query
~~~

**protocol** is the leading part such as **http, https, file, jar**. When a URL is created, Java locates a matching **URLStreamHandler**. With JDK 17, Java guarantees handlers for four protocols: **http**, **https**, **file**, **jar**; other protocols may also exist depending on the environment/provider.

A URL handler is selected **not solely from the protocol string**, but also based on system configuration and SPI. Typical resolution paths in Java 17:

1. **URLStreamHandlerFactory** installed by the application via **URL.setURLStreamHandlerFactory(factory)**, if present.
2. **java.net.spi.URLStreamHandlerProvider** discovered via the provider/ServiceLoader mechanism when applicable.
3. Packages declared in the **java.protocol.handler.pkgs** system property.
4. Built-in handlers for standard protocols.

This is a focused summary; the URL Javadoc details the handling when a provider returns null, a class is missing, exceptions occur, as well as the implementation-specific nature of caching/ordering.

**Do not create a JVM-wide custom handler just to change the behavior of a test URL.** There is a way to attach a URLStreamHandler **directly to a URL instance**:

~~~java
URL special = new URL(null, "inmemdemo:/resource",
        new URLStreamHandler() {
            @Override
            protected URLConnection openConnection(URL u) {
                // Return a custom URLConnection.
                return new MyConnection(u);
            }
        });
~~~

**MyConnection in this snippet is just an illustrative class** and is not built into the JDK. A complete example with **MemoryConnection** is provided below and actually compiles and runs.

### 3.2. URL.openConnection() Calls handler.openConnection(URL)

The line:

~~~java
URLConnection connection = url.openConnection();
~~~

is conceptually equivalent to the flow:

~~~text
URL object
  |
  +-- associated URLStreamHandler
           |
           +-- openConnection(url)
                     |
                     +-- new URLConnection subclass instance
                             (could be HttpURLConnection,
                              HttpsURLConnection, JarURLConnection
                              or custom URLConnection)
~~~

**Each call to URL.openConnection() creates a new URLConnection instance** via the handler. Two calls can yield two independent objects even when using the same URL. For HTTP, opening a new HttpURLConnection **does not guarantee a new TCP socket**: the implementation may reuse sockets/keep-alive internally after previous requests are handled; you must distinguish between the **request object** and the **underlying transport connection**.

**URL.openStream()** is shorthand for opening a connection and then getting the InputStream. It is convenient when you only need to read a resource, but less flexible if you need to set timeouts, HTTP method, request headers, or inspect the status.

### 3.3. JVM-Wide Factories and Providers Must Be Used Deliberately

**URL.setURLStreamHandlerFactory(...)** is a **JVM-global** configuration API that can succeed at most **once**. Calling it again may throw an **Error**. It affects protocol handler resolution across the entire application and class libraries, so it is unsuitable as a hidden change inside a library.

**URLStreamHandlerProvider** allows declaring custom protocol handlers via the service-provider mechanism; module/service packaging must match the deployment. **java.protocol.handler.pkgs** uses a list of packages separated by **|**, with handler classes following the **package.protocol.Handler** convention.

To demonstrate the lifecycle in a lesson, passing a **handler instance directly to the URL** keeps the scope clear and avoids global side effects.

### 3.4. Not Every Protocol Uses HTTP

| Protocol | Common handler/connection type | Key takeaway |
| --- | --- | --- |
| **http** | HttpURLConnection | Request method, status, response headers/body |
| **https** | HttpsURLConnection | HTTP + TLS, certificate/hostname verification |
| **file** | URLConnection provided by the file handler | Local file access; no HTTP status code |
| **jar** | JarURLConnection | Retrieves resources inside a JAR archive |
| **inmemdemo** in the example | Custom MemoryConnection | No network; connect is a state defined by the custom class |

Do not call getResponseCode() on an arbitrary URLConnection because that is a method on **HttpURLConnection**, not generic URLConnection. When designing a custom handler, the subclass must clearly define the meaning of **connect()**, streams, headers, caching, and state, rather than assuming HTTP semantics.

## 4. Two Main Phases: Before Connect and After Connect

The URLConnection Javadoc describes the standard process:

~~~text
CREATE
  |
  +-- url.openConnection()
  |       connected = false (for a typical lifecycle)
  |
CONFIGURE
  | setConnectTimeout, setReadTimeout
  | setRequestProperty, addRequestProperty
  | setDoInput, setDoOutput, setUseCaches
  | setIfModifiedSince, request method (HTTP)
  |
CONNECT / FIRST OPERATION THAT NEEDS CONNECTION
  | connect()
  | getInputStream() / getOutputStream()
  | getContentLength() / some response metadata getters
  |
CONNECTED
  | request has started according to protocol
  | request headers/method are generally locked
  | response headers/status/body can be read
  |
CLEANUP
  | close opened streams
  | HttpURLConnection.disconnect() when appropriate
~~~

**Calling connect() twice on an already-connected URLConnection** is specified as having the second call ignored per the URLConnection contract. However, that **does not turn the object into a reusable request**. To make another request with a different configuration, call **url.openConnection()** again.

### 4.1. Configurations That Must Be Done Before Connect

HTTP GET example:

~~~java
HttpURLConnection connection =
        (HttpURLConnection) url.openConnection();

connection.setConnectTimeout(3_000); // milliseconds
connection.setReadTimeout(5_000);
connection.setRequestMethod("GET");
connection.setRequestProperty("Accept", "application/json");
connection.setRequestProperty("X-Request-Id", "example-42");
connection.setUseCaches(false);
connection.setDoInput(true);
~~~

**This is a snippet using the url variable**, not a standalone file. These settings must be configured **before performing any operation that could implicitly connect**.

| API | Meaning | Notes |
| --- | --- | --- |
| **setConnectTimeout(ms)** | Timeout limit for opening a communications link | **0** means no timeout limit; choose a positive value |
| **setReadTimeout(ms)** | Timeout limit when reading data | Not a total end-to-end deadline; 0 corresponds to waiting indefinitely |
| **setRequestMethod("GET")** | Selects the HTTP method | Only for HttpURLConnection and before connecting |
| **setRequestProperty(k,v)** | Sets/overwrites a request header | After connected, may throw IllegalStateException |
| **addRequestProperty(k,v)** | Adds a value to a request property | Not every header is valid in HTTP when used this way |
| **setDoInput(true)** | Specifies using the connection for input | Usually needed when reading a response |
| **setDoOutput(true)** | Allows using the output stream | Set before obtaining the output stream/connecting |
| **setUseCaches(false)** | Decides whether to use caching supported by the protocol handler | Does not disable all proxy/server/CDN caches |
| **setIfModifiedSince(timeMillis)** | Hints to fetch the resource only if newer than the specified timestamp | Behavior depends on the protocol/HTTP handler |
| **setInstanceFollowRedirects(...)** | Redirect policy for the **HttpURLConnection instance** | Consider security implications when redirecting to another host |

**Do not treat setReadTimeout(5000) as a 5-second maximum limit for the entire request.** Read timeout applies to a blocking read operation, which may repeat multiple times. If you need an overall deadline, you need an appropriate application-level timeout mechanism.

### 4.2. APIs That Can Trigger an Implicit Connection

~~~java
URLConnection c = url.openConnection();
c.setConnectTimeout(3000);
c.setReadTimeout(3000);

try (InputStream input = c.getInputStream()) {
    byte[] data = input.readAllBytes();
}
~~~

The code does not call **connect()** directly, but **getInputStream() needs the resource**, so it performs the connection steps itself. Certain response metadata getters such as **getContentLength()**, **getContentType()**, and **getHeaderField(...)** can also force URLConnection to connect in order to read the response.

**Warning:** reading response headers **too early** can inadvertently freeze request settings. Do not call getHeaderField, getContentLength, or getInputStream before fully setting the method, timeouts, and headers.

With HttpURLConnection, **getResponseCode()** can also cause the HTTP request to be sent in order to obtain the status. Therefore, **getResponseCode() is not a safe metadata check before configuring the request**.

### 4.3. After Connect: Request Configuration Is Locked

Certain changes after already being connected are **invalid state transitions**:

~~~java
connection.connect();

// IllegalStateException for an already-connected HttpURLConnection.
connection.setRequestProperty("Accept", "text/plain");
~~~

**HttpURLConnection.setRequestMethod(...)** after connected also throws **ProtocolException** because the connection is already established. Depending on the API, setting options after connect may be rejected or have no effect on the current request; the safe rule of thumb is to **set request options before any operation that might connect**.

**Do not try to pass new information via a header after the response has started.** Any header that belongs in the request must be set before the request is sent.

### 4.4. Request Objects and Connections Are Two Distinct Concepts

~~~java
URLConnection first = url.openConnection();
URLConnection second = url.openConnection();
~~~

**first != second** at the new URLConnection object level in standard usage; TCP reuse at the implementation layer does not make the two URLConnection objects the same instance. An HttpURLConnection **should not be reused to send a GET and then modified to a POST on the same object**. Create a new object when you need a new request.

## 5. HTTP: connect() Does Not Always Mean the Response Has Been Received

With HTTP, there are several milestones:

1. **Creating the HttpURLConnection object**: has not sent the request under the standard lifecycle.
2. **connect()**: opens a communications link when needed, potentially initializing socket/proxy/TLS depending on the handler. Do not infer that the response body has been fully downloaded.
3. **getOutputStream()** (if sending a body): may connect implicitly and begin sending the request.
4. **getResponseCode() / getInputStream()**: performs I/O to retrieve the response status, headers, or body.
5. **Closing streams / disconnect**: releases resources held by the request object; the keep-alive layer may have its own policy.

In the Java example in section 8, the program confirms that **openConnection() has not produced a request observed by the server**, whereas **getInputStream()** can do so without an explicit connect() call.

**Do not generalize one run into a claim that connect() always sends the HTTP request immediately.** HttpURLConnection may defer protocol steps until I/O is needed. To verify that an HTTP request actually reached the server, check server-side behavior/status/body, not merely that connect() was called.

### 5.1. Reading the HTTP Response According to Status

~~~java
HttpURLConnection http =
        (HttpURLConnection) url.openConnection();

http.setConnectTimeout(3000);
http.setReadTimeout(5000);
http.setRequestMethod("GET");
try {
    int status = http.getResponseCode();

    InputStream source = status >= 400
            ? http.getErrorStream()
            : http.getInputStream();

    if (source != null) {
        try (InputStream in = source) {
            // Read and process the body according to the appropriate Content-Type/charset.
        }
    }
} finally {
    http.disconnect();
}
~~~

The snippet above is not a standalone program. **getErrorStream() may return null** if there is no error payload; when the response is 4xx/5xx, getInputStream() typically throws IOException, so do not use a single getInputStream() branch and treat every failure as a network error.

**HTTP status 404/500 is a server response**, not automatically a TCP or TLS error. If logging or retrying is needed, distinguish transport errors, HTTP response errors, and business logic.

### 5.2. GET and POST Differ in the Configuration Step

When sending a POST with a request body:

~~~java
HttpURLConnection post =
        (HttpURLConnection) url.openConnection();

post.setConnectTimeout(3000);
post.setReadTimeout(5000);
post.setRequestMethod("POST");
post.setDoOutput(true);
post.setRequestProperty("Content-Type", "application/json; charset=UTF-8");
post.setFixedLengthStreamingMode(bodyBytes.length);

try {
    try (OutputStream out = post.getOutputStream()) {
        out.write(bodyBytes);
    }
    int status = post.getResponseCode();
    // Read response body/error stream if needed.
} finally {
    post.disconnect();
}
~~~

**This is a snippet using bodyBytes/url variables**, not a standalone Java file. You must set the request method, doOutput, Content-Type, and streaming mode **before getOutputStream()**, because getOutputStream() may connect implicitly. If using fixed-length streaming mode, you must write the exact number of bytes declared; failing to do so may cause an IOException.

**Do not assume setDoOutput(true) is the standard way to decide the POST method.** Set the method explicitly so behavior is clear across handler/protocol implementations.

### 5.3. Redirects, Caching, and Response Headers

HttpURLConnection can follow redirects as configured, but **not all HTTP 3xx redirects are always followed**, and redirects that change host/protocol/method have restrictions. If the request carries an Authorization or Cookie header, check the credential-forwarding policy on redirects; do not automatically forward secrets to another host.

**setUseCaches(false)** only applies to the URLConnection/handler caching behavior to the extent supported by the implementation; it does not override every HTTP proxy/CDN cache or server cache-control. **setIfModifiedSince(...)** can produce a conditional request; a **304 Not Modified** response is a valid result of HTTP caching/conditional requests, not a connect error.

**getHeaderFields()** returns response metadata once available; do not use it before finishing request configuration because it can trigger an implicit connection. **getRequestProperties()** is used to inspect request configuration before connecting; after connecting, it may throw IllegalStateException.

## 6. HTTPS: Same Lifecycle, Plus TLS/Identity Verification

For an HTTPS URL:

~~~java
URLConnection generic =
        new URL("https://example.com/api").openConnection();

if (generic instanceof HttpsURLConnection https) {
    https.setConnectTimeout(3000);
    https.setReadTimeout(5000);
    https.setRequestProperty("Accept", "application/json");
    // Getting the response/stream will perform the HTTPS connection when needed.
}
~~~

The HTTPS handler creates an **HttpsURLConnection**, which is a subclass of HttpURLConnection. The HTTP request travels over TLS; depending on the implementation, **connect()** or subsequent I/O operations may lead to TCP/proxy CONNECT, TLS handshake, certificate chain validation, and hostname verification.

**Do not disable certificate or hostname verification** to fix HTTPS connections. Anti-patterns to avoid:

- A TrustManager with an **empty checkServerTrusted(...)**.
- A HostnameVerifier returning **true** for all hostnames.
- An SSLContext accepting all server certificates.
- Falling back to plaintext HTTP just because TLS failed.

If you encounter an SSLHandshakeException, inspect the **chain/truststore, SAN/hostname, system time, TLS algorithm policy, and proxy/TLS termination**. A custom SSLContext or SSLSocketFactory must preserve proper verification.

### HTTPS and When Configuration Can No Longer Be Changed

If **HttpsURLConnection.setSSLSocketFactory(...)** or **setHostnameVerifier(...)** is validly needed (per policy), it must be called before connecting. It is best to use the JVM's **default verification**, or a managed truststore with verified CAs. Once connected, changing those settings does not re-verify the handshake that has already occurred.

**HTTPS does not change the two-phase principle:** openConnection creates the object first; connect/I/O is what requires the link and data. Exactly where an HTTPS handler performs the TLS handshake is an implementation detail and cannot be inferred from a bare new URL(...) statement.

## 7. Proxy, Timeouts, Caching, and Resource Lifecycle

### 7.1. URL.openConnection(Proxy)

An overload supports an explicit proxy:

~~~java
Proxy proxy = new Proxy(
        Proxy.Type.HTTP,
        new InetSocketAddress("proxy.example.test", 3128));

URLConnection connection = url.openConnection(proxy);
~~~

Per the Java 17 Javadoc, **openConnection(proxy)** prioritizes the explicit proxy choice over the system's **default ProxySelector**; a protocol handler may not support proxying and may ignore the proxy parameter or throw UnsupportedOperationException depending on the handler. If you want a direct connection per the API, use **Proxy.NO_PROXY** instead of **null**.

**Never actually try proxy.example.test in this example unless configured in a real environment**; this is only an illustrative snippet and is not used by the loopback test in section 8.

### 7.2. Connect Timeout and Read Timeout

- **setConnectTimeout(ms)**: timeout limit for opening a communications link; does not cover the entire request processing.
- **setReadTimeout(ms)**: timeout limit waiting for data during a blocking read; if no data arrives within the limit, a **SocketTimeoutException** may occur.
- **0** generally means an infinite wait for the respective timeout.
- An application-managed **overall deadline** may be needed if downloading large payloads or if a server trickles small bytes to evade read timeout while dragging out the entire request.

If a timeout occurs, **always close streams/clean up** in finally/try-with-resources. Do not keep the URLConnection object and reuse it for a retry as if it were a new request. When retrying is needed, create a new URLConnection, recalculate remaining time/attempt limits, and only retry operations that are valid under idempotency.

### 7.3. Cleaning Up Streams and disconnect

~~~java
HttpURLConnection http =
        (HttpURLConnection) url.openConnection();
try {
    http.setConnectTimeout(3000);
    http.setReadTimeout(5000);
    try (InputStream input = http.getInputStream()) {
        // Read body, close stream automatically.
    }
} finally {
    http.disconnect();
}
~~~

**Closing the InputStream** is how stream resources are released. **disconnect()** indicates that further requests to the server may not be made in the near future, and **does not make the HttpURLConnection instance reusable**. Underneath, HTTP keep-alive/connection pooling may decide when the physical socket is closed or reused. Do not interpret a disconnect() call as proof that every associated TCP connection is immediately closed in every implementation.

If the response has an error body, use **getErrorStream()** properly when present; that stream must also be closed. Do not read unbounded bodies into RAM when responses are untrusted; enforce byte limits/streaming and treat Content-Length only as a hint.

### 7.4. Do Not Share HttpURLConnection as a Mutable Object Across Threads

URLConnection is configured through many mutable setters and has a specific connected state. Do not design multiple threads to concurrently modify request properties/connect/read on the same instance without clear synchronization/ownership. The simple approach: **use a new URLConnection per request**, with clear resource-closing ownership.

This is a blocking API; if you need many asynchronous requests, HTTP/2, cancellation, streaming, and advanced thread management, **java.net.http.HttpClient** (Java 11+) is usually a better fit. Do not confuse **HttpClient.sendAsync** with **URL.openConnection**: they are different APIs.

## 8. Real Runnable Java 17+ Program: HTTP Loopback and Custom Protocol Handler

The program **URLConnectionLifecycleDemo.java** requires no Internet access. It creates an in-JVM HTTP server on **127.0.0.1** and an ephemeral port, then:

1. Calls **URL.openConnection()** for an HTTP URL, asserts it returns an **HttpURLConnection**, and asserts **the server has not received a request yet**.
2. Sets timeouts, GET, a header, and useCaches before connecting.
3. Calls **connect()**, attempts a late **setRequestProperty(...)**, and asserts it throws **IllegalStateException**.
4. Calls **getInputStream()** to read the **HELLO:explicit** response.
5. Creates a new URLConnection from the **same URL**, **does not call connect()**, and calls **getInputStream()** directly. The server receives the request and returns **HELLO:implicit**.
6. Verifies the server handled exactly **2 HTTP requests**.
7. Creates an **inmemdemo:/resource** URL with a **custom URLStreamHandler** passed directly to the constructor, returning a **MemoryConnection** without using the network.
8. MemoryConnection increments its counter only on the first connect; reading the stream connects implicitly, and calling connect a second time does not increment the counter.
9. Closes streams, disconnects both HttpURLConnections, stops the local server, and shuts down the worker pool.

The code uses **JDK 17** and the standard **jdk.httpserver** module. It does not touch the global URLStreamHandlerFactory, global proxies, or certificate configuration. The **inmemdemo** handler is attached only to the URL instance created in the program; it does not register globally for all URL strings.

### File URLConnectionLifecycleDemo.java

~~~java
import com.sun.net.httpserver.HttpServer;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URL;
import java.net.URLConnection;
import java.net.URLStreamHandler;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class URLConnectionLifecycleDemo {
    static void require(boolean ok, String why) {
        if (!ok) throw new AssertionError(why);
    }

    static String readText(URLConnection connection) throws IOException {
        try (InputStream input = connection.getInputStream()) {
            return new String(
                    input.readAllBytes(), StandardCharsets.UTF_8);
        }
    }

    static final class MemoryConnection extends URLConnection {
        final AtomicInteger connects;

        MemoryConnection(URL url, AtomicInteger connects) {
            super(url);
            this.connects = connects;
        }

        @Override
        public void connect() {
            if (!connected) {
                connected = true;
                connects.incrementAndGet();
            }
        }

        @Override
        public InputStream getInputStream() {
            if (!connected) connect();
            return new ByteArrayInputStream(
                    "MEMORY_OK".getBytes(StandardCharsets.UTF_8));
        }
    }

    public static void main(String[] args) throws Exception {
        AtomicInteger hits = new AtomicInteger();
        HttpServer server = HttpServer.create(
                new InetSocketAddress(
                        InetAddress.getByName("127.0.0.1"), 0), 0);
        ExecutorService serverWorkers =
                Executors.newFixedThreadPool(2);
        server.setExecutor(serverWorkers);

        server.createContext("/hello", exchange -> {
            try {
                hits.incrementAndGet();
                String header = exchange.getRequestHeaders()
                        .getFirst("X-Lifecycle");
                byte[] bytes = ("HELLO:" + header)
                        .getBytes(StandardCharsets.UTF_8);
                exchange.sendResponseHeaders(200, bytes.length);
                try (OutputStream out = exchange.getResponseBody()) {
                    out.write(bytes);
                }
            } finally {
                exchange.close();
            }
        });

        try {
            server.start();
            URL endpoint = new URL("http://127.0.0.1:" +
                    server.getAddress().getPort() + "/hello");
            URLConnection opened = endpoint.openConnection();

            require(opened instanceof HttpURLConnection,
                    "Wrong HTTP handler type");
            require(hits.get() == 0,
                    "openConnection sent a request");
            System.out.println("HTTP handler selected: true");
            System.out.println(
                    "No request at openConnection: true");

            HttpURLConnection explicit =
                    (HttpURLConnection) opened;
            explicit.setConnectTimeout(3000);
            explicit.setReadTimeout(3000);
            explicit.setRequestMethod("GET");
            explicit.setRequestProperty(
                    "X-Lifecycle", "explicit");
            explicit.setUseCaches(false);

            try {
                explicit.connect();

                boolean rejected = false;
                try {
                    explicit.setRequestProperty(
                            "X-Lifecycle", "too-late");
                } catch (IllegalStateException expected) {
                    rejected = true;
                }

                require(rejected,
                        "Mutable setting allowed after connect");
                System.out.println(
                        "Post-connect mutation rejected: true");

                String response = readText(explicit);
                require("HELLO:explicit".equals(response),
                        "Explicit response mismatch");
                System.out.println(
                        "Explicit response: " + response);
            } finally {
                explicit.disconnect();
            }

            HttpURLConnection implicit =
                    (HttpURLConnection) endpoint.openConnection();
            implicit.setConnectTimeout(3000);
            implicit.setReadTimeout(3000);
            implicit.setRequestProperty(
                    "X-Lifecycle", "implicit");

            try {
                String response = readText(implicit);
                require("HELLO:implicit".equals(response),
                        "Implicit response mismatch");
                System.out.println(
                        "Implicit response: " + response);
            } finally {
                implicit.disconnect();
            }

            require(hits.get() == 2,
                    "HTTP server request count mismatch");
            System.out.println(
                    "HTTP requests observed: " + hits.get());

            AtomicInteger connects = new AtomicInteger();
            URL special = new URL(
                    null, "inmemdemo:/resource",
                    new URLStreamHandler() {
                        @Override
                        protected URLConnection openConnection(URL u) {
                            return new MemoryConnection(u, connects);
                        }
                    });

            URLConnection virtual = special.openConnection();
            require(virtual instanceof MemoryConnection,
                    "Custom protocol handler not selected");
            require(connects.get() == 0,
                    "Custom connection too early");

            String text = readText(virtual);
            require("MEMORY_OK".equals(text),
                    "Custom body mismatch");

            virtual.connect();
            require(connects.get() == 1,
                    "connect is not idempotent");

            System.out.println(
                    "Custom protocol: " + special.getProtocol());
            System.out.println("Custom response: " + text);
            System.out.println(
                    "Custom connect calls: " + connects.get());
        } finally {
            server.stop(0);
            serverWorkers.shutdown();
            if (!serverWorkers.awaitTermination(
                    5, TimeUnit.SECONDS)) {
                serverWorkers.shutdownNow();
            }
        }

        require(serverWorkers.isTerminated(),
                "Server workers still running");
        System.out.println(
                "Server executor terminated: true");
    }
}
~~~

### How to Compile and Run

Save the file with the exact name **URLConnectionLifecycleDemo.java**. Use **JDK 17 or later**:

~~~bash
javac --release 17 --add-modules jdk.httpserver -encoding UTF-8 URLConnectionLifecycleDemo.java
java --add-modules jdk.httpserver URLConnectionLifecycleDemo
~~~

**Actual compiled/executed stdout with equivalent Java 17 code on the JVM, verified line by line:**

~~~text
HTTP handler selected: true
No request at openConnection: true
Post-connect mutation rejected: true
Explicit response: HELLO:explicit
Implicit response: HELLO:implicit
HTTP requests observed: 2
Custom protocol: inmemdemo
Custom response: MEMORY_OK
Custom connect calls: 1
Server executor terminated: true
~~~

**Why is the output predictable?** The program uses loopback and **port 0** (the OS picks an available port); it does not print random ports or IDs. The server counter **hits** increments when the handler receives a request, and both responses are compared against expected values. The custom handler uses no sockets, so the connect count is controlled by the program itself. Checking the late post-connect call is done with a **boolean flag** based on the exception, without depending on error message strings that might differ across JDK vendors.

**Intentional limitations:** The program uses HTTP/1.1 loopback rather than HTTPS certificates or a proxy; the TLS/proxy sections are shown only as API illustrations to avoid introducing environment dependencies. The demo does not prove that a public HTTPS endpoint works, but rather clearly verifies the lifecycle of URLConnection and handlers.

### Analyzing the Output Lines

- **HTTP handler selected: true**: The **http** URL protocol creates an HttpURLConnection object.
- **No request at openConnection: true**: The server has not observed a request after merely creating the object.
- **Post-connect mutation rejected: true**: setRequestProperty after connect throws IllegalStateException as expected.
- **Explicit response: HELLO:explicit**: The header configured before connect was read by the server.
- **Implicit response: HELLO:implicit**: getInputStream performed the connection even though the code did not call connect directly.
- **HTTP requests observed: 2**: The second openConnection call created a different request object, and the two reads generated two HTTP requests.
- **Custom protocol: inmemdemo**: The URL instance used the handler provided by the program.
- **Custom response: MEMORY_OK**: MemoryConnection returned the resource from memory without using the network.
- **Custom connect calls: 1**: getInputStream calls connect if needed; the subsequent connect call is ignored in the custom implementation.
- **Server executor terminated: true**: The local server worker pool shut down and kept no threads alive after the program finished.

## 9. When Are Custom Protocol Handlers Useful?

Custom URLStreamHandler and URLConnection implementations can be used for:

1. **Testing/in-memory resources** where you want to avoid network dependencies.
2. **Internal protocols** with their own resource naming.
3. **Adapters for resource storage** that have URL-like semantics.
4. **Resource loaders or integration hooks** with an existing system that genuinely needs protocol management.

However, designing a handler carries responsibilities:

- **The protocol parser** must parse URLs correctly and not accept ambiguous input that introduces risk.
- **openConnection** must create an object with a clear lifecycle, without secretly holding network/background tasks unknown to the caller.
- **connect()** must set the connected flag consistently, manage failures, and avoid creating duplicate resources when called multiple times.
- **getInputStream()/getOutputStream()** must handle I/O, errors, and stream closing according to contract.
- **Request metadata and response metadata** must have documented semantics; do not pretend a custom protocol has HTTP statuses.
- **Thread safety and ownership** must be clearly decided if the application shares URL/handler state.
- **Global registration** via a factory or provider must consider initialization order, security, classloading, and JVM-wide impact.

The MemoryConnection example is intentionally simple: connect only marks the state, and the stream reads from an immutable byte[]. This is a protocol handler for accurately testing the lifecycle, not a promise about the behavior of all handlers in the JDK.

### What If a Protocol Is Unrecognized?

If no matching handler is found for the protocol when creating a URL, Java may throw **MalformedURLException: unknown protocol**. Not every string containing a colon is a URL supported by the JVM.

If you want a custom protocol to work via **new URL("inmemdemo:...")** in multiple places across an application, you need to register the handler through the appropriate mechanism (factory/provider/property) rather than attaching a handler to a single URL instance as in the demo.

## 10. Common Mistakes

| Mistake | Why it is wrong | Correct approach |
| --- | --- | --- |
| **Assuming openConnection() has already sent the request** | It creates the URLConnection object without immediately establishing a network connection | Configure first, connect/read later |
| **Calling getInputStream before setRequestProperty** | getInputStream may connect implicitly | Set method, headers, and timeouts before any response getter |
| **Setting a request header after connect()** | IllegalStateException or too late | Create a new URLConnection if another request is needed |
| **Using the same HttpURLConnection for multiple HTTP requests** | The object is not a reusable request builder | Create a new connection object for each request |
| **Casting file:/jar: to HttpURLConnection** | The handler returns a different URLConnection type | Use instanceof and distinguish by protocol |
| **Assuming connect() always downloads the entire body** | HTTP may defer sending/fetching the response until subsequent I/O | Check getResponseCode, streams, and server-side evidence |
| **Reading all statuses with getInputStream** | For 4xx/5xx it may throw IOException | Check status and use getErrorStream |
| **Not closing InputStream or error stream** | Leaks files/sockets/buffers | Use try-with-resources and cleanup in finally |
| **Assuming disconnect() guarantees the physical socket closes immediately** | Keep-alive/resource management is implementation-dependent | Understand API semantics; measure actual sockets if needed |
| **Not setting timeouts** | The client can wait for a long time or indefinitely | Use setConnectTimeout, setReadTimeout, and an application deadline |
| **Believing setUseCaches(false) disables all CDNs** | It is only a handler option | Distinguish client cache, proxy/CDN, and server cache |
| **Replacing the JVM-wide URLStreamHandlerFactory in a library** | Can only be set once and has global impact | Use a handler instance or a managed provider |
| **Passing null to URL.openConnection(Proxy)** | The API requires a valid Proxy | Use Proxy.NO_PROXY if you want a direct connection |
| **Disabling hostname/certificate verification when HTTPS fails** | Weakens TLS identity | Fix CA/chain/SAN or proxy/TLS configuration |
| **Opening URLs from untrusted input without validation** | Risk of SSRF, accessing metadata/internal networks | Allowlist scheme/host/port; block disallowed redirects and internal addresses |
| **Using HttpURLConnection from multiple threads with concurrent mutations** | The request object is mutable and its lifecycle is hard to control | Own each request clearly in a single flow/thread |
| **Confusing URLConnection with HttpClient.sendAsync** | They are two different APIs | Choose the HTTP client based on concurrency, streaming, and timeout needs |

## 11. Security When URLs Come From Untrusted Data

**SSRF (Server-Side Request Forgery)** can occur if a service lets clients submit arbitrary URLs and the server immediately calls openConnection/getInputStream with the server's internal network privileges.

For example, an attacker might try URLs pointing to:

- **127.0.0.1 or ::1**, services exposed only on localhost.
- **Private networks** or internal hostnames.
- **Cloud metadata endpoints** not intended for users.
- **file:** URLs to attempt reading local files.
- **jar:** or custom protocol handlers with side effects.
- Public **http(s)** URLs that issue a **redirect** to an internal address.

Defenses:

1. **Parse the URI** and accept **only the required schemes**, typically only HTTPS.
2. **Allowlist hostnames and ports** according to business rules; do not rely on raw string blacklists as the primary control.
3. Validate the URL **after every redirect**, not just the initial URL; if possible, disable auto-follow and validate redirects manually.
4. Control **DNS resolution, IP ranges, and rebinding** appropriately for your environment; a simple hostname allowlist is not enough to prevent all DNS-based SSRF.
5. Enforce **timeouts, redirect limits, response size limits, and concurrency limits**.
6. Do not forward Authorization/Cookies/tokens to a new origin unless permitted.
7. Do not allow a custom protocol handler URL to perform unauthorized local file/process access.

**The fact that openConnection() itself has not sent a request does not mean the URL is safe**: it creates a handler-specific object, and subsequent I/O can occur in a code path that looks like it is only reading metadata.

## 12. Self-Check Questions

**Question 1.** Does URL.openConnection() immediately connect over the network?  
**Answer:** Under the Java 17 contract, it creates a new URLConnection object via the protocol handler without establishing a network connection at creation time.

**Question 2.** Does URL.openConnection() create a new instance each time or return the same object?  
**Answer:** It creates a new URLConnection instance via URLStreamHandler.openConnection(URL) each time. That does not guarantee a new physical TCP socket each time.

**Question 3.** Why are HttpURLConnection and HttpsURLConnection both URLConnections?  
**Answer:** They are specialized subclasses implementing HTTP/HTTPS behavior; URL selects the handler based on the protocol.

**Question 4.** Can setRequestProperty be called after connect()?  
**Answer:** No; for an already-connected HttpURLConnection, it throws IllegalStateException.

**Question 5.** If connect() is not called, can getInputStream() cause the request to execute?  
**Answer:** Yes. Operations that require the resource will connect implicitly when needed.

**Question 6.** Are getContentLength() and getResponseCode() always metadata getters that require no I/O?  
**Answer:** No. When they need the response, they can trigger an implicit connection.

**Question 7.** Is setConnectTimeout(3000) in seconds or milliseconds?  
**Answer:** Milliseconds; 3000 ms = 3 seconds.

**Question 8.** Is setReadTimeout an overall deadline for the entire request?  
**Answer:** No. It applies to read operations waiting for data; a separate overall deadline is needed.

**Question 9.** Why shouldn't every URLConnection be cast to HttpURLConnection?  
**Answer:** A handler may return a JarURLConnection, a file URLConnection, or a custom URLConnection that does not support HTTP.

**Question 10.** When a request returns HTTP 404, how should the response be read?  
**Answer:** Check getResponseCode and read getErrorStream if present; do not assume getInputStream will return a normal body.

**Question 11.** Does HttpURLConnection.disconnect() make the object ready to send a new request?  
**Answer:** No. Create another HttpURLConnection from url.openConnection() for a new request.

**Question 12.** How many times can URL.setURLStreamHandlerFactory be used in a JVM?  
**Answer:** It can succeed at most once. It is a global setting and must be used with caution.

**Question 13.** Does a custom URLStreamHandler always require the network?  
**Answer:** No. In the demo, MemoryConnection returns a stream from a byte[] and creates no sockets.

**Question 14.** What is URL.openConnection(Proxy.NO_PROXY) for?  
**Answer:** It chooses a direct path instead of a proxy when the handler supports the overload; unlike passing null, which is invalid.

**Question 15.** Why is SSRF still a risk if openConnection has not connected yet?  
**Answer:** Because getInputStream/getResponseCode and subsequent operations can implicitly connect to the URL specified by untrusted input.

**Question 16.** Does HTTPS allow disabling hostname checks to avoid handshake errors?  
**Answer:** It should not be done. Fix the CA/chain/SAN and trust policy properly to preserve TLS server authentication.

## Conclusion

Remember the sequence **URL → protocol handler → URLConnection object → configure → connect/implicit I/O → read/write → cleanup**.

**openConnection() prepares the object** without sending the resource request itself. **connect()** marks/establishes the link and serves as the configuration boundary; methods that need the response can connect implicitly even if the code does not write connect explicitly. **The protocol handler** determines the specific subclass and semantics: HTTP has HttpURLConnection, HTTPS has HttpsURLConnection, file/jar have their own mechanisms, and a custom handler can produce resources without any network at all.

With HTTP/HTTPS, **configure all request properties and timeouts upfront**, handle status/error streams, close streams/disconnect according to the lifecycle, and never reuse the same HttpURLConnection instance for another request. When a URL comes from input, pay special attention to controlling SSRF, redirects, and TLS identity.

### Official References

- [Java SE 17 — URL](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URL.html): openConnection(), handler resolution, openStream, proxy overload, and factory.
- [Java SE 17 — URLConnection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLConnection.html): two phases, connect(), and setters/getters.
- [Java SE 17 — URLStreamHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLStreamHandler.html): openConnection(URL) and protocol-dependent behavior.
- [Java SE 17 — URLStreamHandlerFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLStreamHandlerFactory.html): creating URLStreamHandlers.
- [Java SE 17 — URLStreamHandlerProvider](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/spi/URLStreamHandlerProvider.html): service provider for custom protocols.
- [Java SE 17 — HttpURLConnection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/HttpURLConnection.html): HTTP method, response status, error stream, redirects, disconnect.
- [Java SE 17 — HttpsURLConnection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/HttpsURLConnection.html): HTTPS and TLS session.
- [Java SE 17 — Proxy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Proxy.html): explicit proxy and Proxy.NO_PROXY.
- [Java SE 17 — HttpServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): loopback test server.
- [RFC 3986 — URI Generic Syntax](https://www.rfc-editor.org/rfc/rfc3986.html): URI/URL handling and security considerations.
