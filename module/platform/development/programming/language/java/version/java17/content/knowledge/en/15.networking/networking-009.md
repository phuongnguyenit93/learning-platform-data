# Network Limits, DNS, and Testing with Local Services in Java 17

When a Java application calls an HTTP service, failures can occur at multiple stages: domain name resolution, TCP connection establishment, HTTP exchange, waiting for a response, or reading the payload. Setting only one timeout without understanding which stage it bounds can still leave the application hanging for a long time or reporting hard-to-distinguish errors.

In Java 17, `java.net.http.HttpClient` provides timeout settings for connection establishment and per request. `java.net.InetAddress` supports resolving hostnames to IP addresses. To test without depending on the Internet, you can run an HTTP service listening only on loopback using a dynamic port.

This lesson focuses on APIs still usable in Java 17: timeouts, DNS, loopback addresses, testing local HTTP services, and identifying network errors.

## 1. What Phases Does a Network Request Go Through?

When an application calls a URL like `https://api.example.test/orders`, the flow can be pictured as:

~~~text
Java Application
    |
    v
Parse URI / hostname
    |
    v
DNS: hostname -> one or more IP addresses
    |
    v
Establish TCP connection (and TLS if using HTTPS)
    |
    v
Send HTTP request
    |
    v
Wait for HTTP response
    |
    v
Read and process response body
~~~

Each phase has distinct error types and bounding mechanisms:

| Phase | Example issue | Related concept / API |
|---|---|---|
| Name resolution | DNS cannot find hostname or resolver is slow | `InetAddress`, `UnknownHostException` |
| Connection | Target refuses connection, firewall blocks, or network unresponsive | TCP, `connectTimeout` |
| TLS | Invalid certificate or handshake failure | TLS, `SSLHandshakeException` |
| HTTP | Server returns 404, 429, or 500 | `HttpResponse.statusCode()` |
| Waiting for response | Server takes too long to process | `HttpRequest.timeout` |
| Reading content | Large body or slow transfer | `BodyHandler`, application limits |

**Timeouts do not mean all network errors are handled identically.** For example, HTTP 404 is a valid HTTP response, not a connection error; conversely, `ConnectException` occurs before the application receives any HTTP response.

## 2. Bounding Connection Establishment Time with connectTimeout

`HttpClient.Builder.connectTimeout(Duration)` sets a time limit for establishing a connection when the client needs to open a new connection.

~~~java
import java.net.http.HttpClient;
import java.time.Duration;

HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .build();
~~~

In this example, the client is configured with a 3-second connect timeout. If a connection cannot be established within the specified time, the operation may fail with `HttpConnectTimeoutException`.

Points to remember:

- The timeout is configured on `HttpClient`, not on each `HttpRequest`.
- It applies when a new connection needs to be established.
- If the client reuses an existing pooled connection, there is no new connection attempt to apply connect timeout to.
- Duration must be positive; invalid values can cause the builder to throw `IllegalArgumentException`.
- Do not set the timeout arbitrarily too small; slow networks or TLS handshakes may need more time.

Once built, `HttpClient` is immutable and can be used for multiple requests. In practice, reuse the client rather than creating a new client for every call to benefit from connection management and reduce initialization overhead.

### 2.1. connectTimeout is not the overall request timeout

Example:

~~~java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(2))
        .build();
~~~

This snippet only bounds connection establishment time. Once the connection is established, the server can still take a long time to process the request or return data.

To bound response wait time for a specific request, configure `HttpRequest.timeout` in the next section.

### 2.2. Do not rely on an arbitrary "unresponsive" IP address as a timeout test

An unreachable address may fail very quickly, be rejected immediately by a firewall, or behave differently across operating systems. Therefore, a test connecting to an arbitrary IP address cannot always reproduce a timeout reliably.

When you need to test real connect timeouts, use a test network environment where you can control firewalls, routes, or proxies. For typical exercises, testing request timeout against a slow local server is usually much more stable and repeatable.

## 3. Bounding Per-Request Duration with HttpRequest.timeout

`HttpRequest.Builder.timeout(Duration)` sets the wait limit for a single request:

~~~java
import java.net.URI;
import java.net.http.HttpRequest;
import java.time.Duration;

HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://example.com"))
        .timeout(Duration.ofSeconds(5))
        .GET()
        .build();
~~~

The request has a 5-second timeout. If the response is not received within that window, sending the request can terminate with `HttpTimeoutException`.

### 3.1. Combining client and request timeouts

~~~java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(2))
        .build();

HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://example.com"))
        .timeout(Duration.ofSeconds(5))
        .GET()
        .build();

HttpResponse<String> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofString()
);
~~~

The two timeouts have different scopes:

| Setting | Scope | Example |
|---|---|---|
| `HttpClient.Builder.connectTimeout` | Establishing a new connection | Up to 2 seconds |
| `HttpRequest.Builder.timeout` | Waiting for the request's response | Up to 5 seconds |

Do not add the two numbers together and treat the sum as a strict bound for every scenario. Connections can be reused, DNS may be cached, and exact behavior depends on which stage the request is in.

### 3.2. Requests without an explicit timeout

If `timeout` is not called on the request, the API does not apply an application-specified finite request limit. When calling external services, choose timeouts based on SLAs, operation type, and the calling thread's time budget.

Do not pick a single number for every endpoint. A health-check endpoint may need a short timeout; a heavy reporting operation may need a larger budget.

### 3.3. Synchronous and asynchronous sending

Synchronous sending:

~~~java
HttpResponse<String> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofString()
);
~~~

The calling thread waits for the result or an exception.

Asynchronous sending:

~~~java
CompletableFuture<HttpResponse<String>> future = client.sendAsync(
        request,
        HttpResponse.BodyHandlers.ofString()
);

future.thenAccept(response ->
        System.out.println(response.statusCode())
);
~~~

`sendAsync` returns a `CompletableFuture`. Request timeout is still configured on `HttpRequest`. If the application calls `future.get(timeout, unit)`, the timeout on `get` is the caller's wait limit for retrieving the result; it is not the same as the request's timeout configuration and does not automatically replace it.

When cancelling a future or request, handle cancellation state and related resources properly. Do not assume that because the caller stopped waiting, the server stopped processing.

## 4. DNS and InetAddress

DNS (Domain Name System) maps hostnames like `example.com` to IP addresses. In Java, `InetAddress` represents an IP address and provides name resolution APIs.

~~~java
import java.net.InetAddress;

InetAddress address = InetAddress.getByName("localhost");

System.out.println(address.getHostName());
System.out.println(address.getHostAddress());
~~~

`getByName` can return an IPv4 or IPv6 address depending on machine configuration and resolution results. Do not assume `localhost` always maps solely to `127.0.0.1`.

### 4.1. Retrieving all resolved addresses

~~~java
InetAddress[] addresses = InetAddress.getAllByName("localhost");

for (InetAddress address : addresses) {
    System.out.println(address.getHostAddress());
}
~~~

A hostname can have multiple addresses. Applications and the operating system may choose an appropriate address when connecting; returned order should not be treated as a fixed contract across all environments.

### 4.2. Getting the loopback address without hardcoding IPv4

~~~java
InetAddress loopback = InetAddress.getLoopbackAddress();
System.out.println(loopback.getHostAddress());
~~~

Loopback is the address pointing back to the machine running the program. It is commonly used for local services, integration tests, and inter-process communication on the same host.

If you want to test IPv4 specifically, you can specify `127.0.0.1`. If you want to test IPv6, use the IPv6 loopback address `::1` and verify the environment supports it. Do not mix IPv4/IPv6 assumptions in tests without explicitly verifying both the bind address and the client's target address.

### 4.3. Distinguishing hostname, IP address, and URI

| Value | Meaning |
|---|---|
| `localhost` | Hostname typically resolved to loopback |
| `127.0.0.1` | IPv4 loopback address |
| `::1` | IPv6 loopback address |
| `http://localhost:8080/health` | URI containing scheme, hostname, port, and path |
| `InetAddress` | Object representing a resolved IP address |

DNS only applies to hostnames. If a URI uses an IP literal, no DNS lookup is needed for that hostname. However, TCP connection and HTTP/TLS steps can still fail.

## 5. DNS Caching and Control Limits in Java 17

Name resolution results can be cached to avoid repeated DNS queries. Java defines caching policies for both successful lookups and failed lookups.

Two common security properties:

- `networkaddress.cache.ttl`: cache duration for successful resolutions.
- `networkaddress.cache.negative.ttl`: cache duration for failed resolutions.

These are **security properties** managed under Java's security configuration. Do not confuse them with ordinary system properties that can always be changed via `System.setProperty`.

Specific TTL values and policies should be configured per operational, platform, and security requirements. Do not alter JVM-wide DNS caching just to speed up a single test.

### 5.1. Why can DNS make tests hard to reproduce?

Suppose a test resolves a hostname the first time and DNS succeeds. A subsequent call may receive a cached result instead of querying the resolver. Conversely, a hostname that previously failed to resolve can continue failing for the duration of the negative cache.

Consequently, test outcomes may depend on:

- The machine running the tests.
- The hosts file and DNS resolver configured on that machine.
- Previously cached DNS entries.
- The active network and environment DNS policies.

To test HTTP logic without relying on public DNS, prefer loopback or local IP addresses. If the goal of the test is DNS itself, use a controlled resolver or test environment.

### 5.2. InetAddress does not offer a per-call DNS timeout

`InetAddress.getByName` and `getAllByName` are synchronous resolution APIs. Java 17 does not provide a `Duration` parameter per call to set a separate DNS timeout.

`HttpClient.connectTimeout` is a connection establishment timeout; do not treat it as an independent DNS timeout setting. DNS lookup details are handled by the runtime and OS name-resolution mechanisms.

If an application has specialized requirements for DNS timeouts, custom resolvers, failover, or cache control, design that at the resolver/network layer suited to the environment. Do not rely on internal classes like `sun.net.*`; they are not stable public APIs for applications to depend on.

### 5.3. Handling unresolvable hostnames

`InetAddress.getByName` can throw `UnknownHostException`:

~~~java
try {
    InetAddress address = InetAddress.getByName("host-that-does-not-exist.invalid");
    System.out.println(address.getHostAddress());
} catch (UnknownHostException e) {
    System.err.println("Could not resolve hostname: " + e.getMessage());
}
~~~

The `.invalid` suffix is reserved for testing and documentation purposes, yet actual DNS queries may still depend on the resolver and environment timeouts. Do not use this example as a fixed-duration timeout test.

In unit tests, mock the resolution layer or pass a known address into the component under test. In DNS integration tests, run inside an environment with a managed resolver.

## 6. Distinguishing Timeout Types and Network Errors

Common exceptions:

| Exception | Typical meaning |
|---|---|
| `UnknownHostException` | Hostname could not be resolved |
| `HttpConnectTimeoutException` | Connection could not be established within connect timeout |
| `HttpTimeoutException` | Request did not receive a response within request timeout |
| `ConnectException` | Connection refused or could not be established |
| `SocketException` | Socket-layer or networking subsystem error |
| `SSLHandshakeException` | TLS handshake failed |
| `IOException` | General I/O error group |

Several exceptions are subclasses of `IOException`; when handling them, catch the more specific types first before catching the general `IOException`.

Example:

~~~java
try {
    HttpResponse<String> response = client.send(
            request,
            HttpResponse.BodyHandlers.ofString()
    );

    System.out.println("HTTP status: " + response.statusCode());
} catch (HttpConnectTimeoutException e) {
    System.err.println("Timed out establishing connection");
} catch (HttpTimeoutException e) {
    System.err.println("Request timed out waiting for response");
} catch (UnknownHostException e) {
    System.err.println("Could not resolve hostname");
} catch (IOException e) {
    System.err.println("Network I/O error: " + e.getMessage());
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    System.err.println("Thread was interrupted");
}
~~~

Note: in some cases, a hostname resolution failure occurring while HttpClient connects may surface as the root cause inside an I/O exception. For detailed classification, inspect the cause chain rather than only reading the outer message.

### 6.1. HTTP status is not a connection exception

If the server returns status 404 or 500, the request still received an HTTP response:

~~~java
int status = response.statusCode();

if (status >= 200 && status < 300) {
    System.out.println("Success");
} else {
    System.out.println("Service returned HTTP " + status);
}
~~~

`HttpClient.send` does not throw an exception solely because the status is 404 or 500. The application must determine which statuses count as success.

## 7. Testing with Local Services: Principles

A reliable network test should minimize dependencies on:

- The public Internet.
- External DNS.
- Third-party services.
- Fixed ports that another process might already occupy.
- Data or state that changes over time.

For HTTP tests, you can run a local service bound only to loopback:

1. Bind the server to `127.0.0.1`.
2. Choose port `0` so the OS assigns an available ephemeral port.
3. Register a simple endpoint like `/health`.
4. Start the server inside the test.
5. Read the actual port from `server.getAddress().getPort()`.
6. Send requests via `HttpClient` to loopback and that port.
7. Stop the server in a `finally` block.

Port `0` asks the operating system to select a free port at bind time. Do not hardcode `8080` in tests because another process may already hold that port.

## 8. Spinning Up a Local HTTP Service with HttpServer

JDK 17 provides `com.sun.net.httpserver.HttpServer` in the `jdk.httpserver` module. This is a lightweight HTTP server useful for tests and development tools. It is not a default choice for building large production web servers; production applications typically use servers/frameworks designed for their operational needs.

Create **`LocalHttpTest.java`**:

~~~java
import com.sun.net.httpserver.HttpServer;

import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public class LocalHttpTest {
    public static void main(String[] args) throws Exception {
        // Listen only on IPv4 loopback; port 0 lets the OS assign a free port.
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0),
                0
        );

        server.createContext("/health", exchange -> {
            byte[] body = "OK".getBytes(StandardCharsets.UTF_8);

            exchange.getResponseHeaders().set(
                    "Content-Type",
                    "text/plain; charset=UTF-8"
            );
            exchange.sendResponseHeaders(200, body.length);

            try (OutputStream output = exchange.getResponseBody()) {
                output.write(body);
            }
        });

        server.start();

        try {
            int port = server.getAddress().getPort();
            URI uri = URI.create(
                    "http://127.0.0.1:" + port + "/health"
            );

            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(2))
                    .build();

            HttpRequest request = HttpRequest.newBuilder()
                    .uri(uri)
                    .timeout(Duration.ofSeconds(3))
                    .GET()
                    .build();

            HttpResponse<String> response = client.send(
                    request,
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8
                    )
            );

            System.out.println("Status: " + response.statusCode());
            System.out.println("Body: " + response.body());
        } finally {
            server.stop(0);
        }
    }
}
~~~

Compile and run with JDK 17:

~~~bash
javac --release 17 --add-modules jdk.httpserver LocalHttpTest.java
java --add-modules jdk.httpserver LocalHttpTest
~~~

Output:

~~~text
Status: 200
Body: OK
~~~

### 8.1. Why is this example more stable for testing?

- The server binds only to loopback, exposing no endpoint on external network interfaces.
- Dynamic port selection avoids conflicts with fixed ports.
- Tests require no public DNS queries or third-party services.
- The client has explicit connect and request timeouts.
- The server is stopped in `finally` even if the request fails.

The example uses IPv4 loopback `127.0.0.1` for both binding and requesting to avoid differences in IPv4/IPv6 resolution order for `localhost` across machines.

### 8.2. The jdk.httpserver module

`HttpServer` resides in the `jdk.httpserver` module. For simple classpath programs, the compile/run commands above add the module using `--add-modules jdk.httpserver`.

If the project uses named modules, declare the dependency:

~~~java
module local.http.test {
    requires java.net.http;
    requires jdk.httpserver;
}
~~~

`java.net.http` is the module containing `HttpClient`; `jdk.httpserver` provides `HttpServer`. For single-file Java exercises on the classpath, no `module-info.java` is needed.

## 9. Testing Request Timeouts with a Slow Endpoint

You can add a `/slow` endpoint to simulate a slow server:

~~~java
server.createContext("/slow", exchange -> {
    try {
        Thread.sleep(1_000);
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        return;
    }

    byte[] body = "finished".getBytes(StandardCharsets.UTF_8);
    exchange.sendResponseHeaders(200, body.length);

    try (OutputStream output = exchange.getResponseBody()) {
        output.write(body);
    }
});
~~~

Build a request with a timeout shorter than the server's delay:

~~~java
HttpRequest slowRequest = HttpRequest.newBuilder()
        .uri(URI.create("http://127.0.0.1:" + port + "/slow"))
        .timeout(Duration.ofMillis(200))
        .GET()
        .build();

try {
    client.send(
            slowRequest,
            HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8)
    );
} catch (HttpTimeoutException e) {
    System.out.println("Request timed out as expected");
}
~~~

In the example, the handler sleeps for about one second while the request sets a 200 ms timeout. The client finishes waiting with `HttpTimeoutException`.

Notes:

- A client-side timeout does not guarantee the server handler immediately stops executing.
- The server may still finish its work after the client stops waiting.
- In real tests, stop the server and clean up executors/resources properly.
- Do not use fixed sleeps to benchmark exact performance; this is solely a timeout illustration.

## 10. Testing DNS and Local Hostnames

You can inspect loopback hostname resolution using:

~~~java
import java.net.InetAddress;

for (InetAddress address : InetAddress.getAllByName("localhost")) {
    System.out.println(address.getHostAddress());
}
~~~

Results depend on machine configuration; you may see IPv4, IPv6, or both. Do not write assertions requiring that only a single fixed address be returned.

If the goal is testing an HTTP server, using explicit loopback IPs like the earlier example keeps tests independent of hostname resolution. If the goal is testing DNS, isolate that into its own test and explicitly specify the resolver, hostname, cache policy, and environment expectations.

### 10.1. Do not depend on public DNS in unit tests

A unit test calling an external hostname can fail because:

- CI runners lack Internet access.
- DNS resolvers fail transiently.
- Rate limits or corporate network policies interfere.
- DNS caches serve stale records.
- Target services change addresses or go down.

Unit tests should test processing logic with mocked dependencies. DNS/HTTP integration tests should run separately in controlled environments with finite timeouts.

### 10.2. Hostname and the Host header

When calling a service by hostname, the hostname can also be used in HTTP authority/`Host` and TLS server name indication. Replacing a hostname with an IP literal is not always equivalent, especially with HTTPS and TLS certificates.

Therefore:

- Use loopback IPs for simple local plain-HTTP tests.
- When testing virtual hosts or TLS, use a test hostname and configure the corresponding resolver and certificates.
- Never disable TLS certificate validation in tests just to make requests pass; generate proper test certificates and configure a dedicated test trust store.

## 11. Timeouts, Retries, and Resource Limits

Timeouts are part of resilience, but they do not replace retry policies or resource bounds.

### 11.1. Retry only appropriate operations

A read-only GET request can often be retried on transient failures if time budget remains. For a POST creating an order or payment, blind retries can cause duplicate side effects if the server processed the request but the response was lost.

Before retrying, verify:

- Is the request idempotent?
- Is there an idempotency key or duplicate-prevention mechanism?
- Is the failure likely transient?
- How much time remains in the overall deadline?
- What are the max attempts and backoff?

Never retry indefinitely. Any retry loop must be bounded and observable via logs and metrics.

### 11.2. Distinguishing per-request timeout from overall deadline

If a workflow calls three services sequentially, setting a 5-second timeout on each request can push total elapsed time well beyond 5 seconds. The application needs an overall deadline for the entire workflow and should compute the remaining budget before each call.

Conceptual example:

~~~text
Overall deadline: 8 seconds
    |
    +-- Service A: up to 2 seconds
    |
    +-- Service B: uses remaining time budget
    |
    +-- Service C: called only if deadline has not expired
~~~

An overall deadline is an application-level policy. `HttpRequest.timeout` does not coordinate budgets across multiple independent requests.

### 11.3. Limiting body size and concurrency

A request with a timeout can still receive a huge body. For untrusted responses, consider:

- Using `BodyHandlers.ofInputStream()` and limiting bytes read yourself.
- Bounding concurrent in-flight requests at the application layer.
- Closing the body stream when finished reading or stopping early.
- Avoiding spawning excessive threads just to block on I/O.
- Monitoring connection counts, latency, and error rates.

`BodyHandlers.ofString()` is convenient for small responses; it reads the body into an in-memory string. For large or unknown-size bodies, consider streaming and size limits.

## 12. Complete Example: Testing Local Timeouts

Create **`LocalTimeoutTest.java`**:

~~~java
import com.sun.net.httpserver.HttpServer;

import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.HttpTimeoutException;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public class LocalTimeoutTest {
    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0),
                0
        );

        server.createContext("/slow", exchange -> {
            try {
                Thread.sleep(1_000);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }

            byte[] body = "done".getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(200, body.length);

            try (OutputStream output = exchange.getResponseBody()) {
                output.write(body);
            }
        });

        server.start();

        try {
            int port = server.getAddress().getPort();

            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(2))
                    .build();

            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(
                            "http://127.0.0.1:" + port + "/slow"
                    ))
                    .timeout(Duration.ofMillis(200))
                    .GET()
                    .build();

            try {
                HttpResponse<String> response = client.send(
                        request,
                        HttpResponse.BodyHandlers.ofString(
                                StandardCharsets.UTF_8
                        )
                );

                System.out.println("HTTP " + response.statusCode());
                System.out.println(response.body());
            } catch (HttpTimeoutException e) {
                System.out.println("Caught expected request timeout");
            }
        } finally {
            server.stop(0);
        }
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 --add-modules jdk.httpserver LocalTimeoutTest.java
java --add-modules jdk.httpserver LocalTimeoutTest
~~~

Expected output in a normal runtime environment:

~~~text
Caught expected request timeout
~~~

This is a request timeout test. It is not a connect timeout or DNS timeout test: the server bound successfully on loopback, the client connects directly by IP address, and the timeout is set on the request.

## 13. Common Pitfalls

| Symptom | Possible cause | Resolution |
|---|---|---|
| Request hangs very long | No request timeout set | Configure an appropriate `HttpRequest.timeout` |
| New connection hangs long | No connect timeout configured | Configure `HttpClient.Builder.connectTimeout` |
| Confusing DNS timeout with connect timeout | Java 17 lacks per-call DNS timeout on `InetAddress` | Control resolver/DNS environment at the appropriate layer |
| `UnknownHostException` | Hostname failed to resolve | Check hostname, DNS resolver, and hosts file |
| `ConnectException` | No service listening or connection refused | Check host, port, bind address, and firewall |
| `HttpTimeoutException` | Request received no response within timeout | Check server latency, network, and timeout |
| HTTP 500 without IOException | Server returned a valid HTTP response | Inspect `statusCode()` |
| Local test cannot connect | Server bound IPv4 while client used IPv6 or vice versa | Use the exact same loopback address explicitly |
| Test reports port already in use | Hardcoded port occupied by another process | Bind port `0` and read the actual assigned port |
| Test depends on Internet | Calling external hostnames or public services | Use loopback or dedicated mock/test services |
| Client times out yet server continues processing | Client timeout does not immediately cancel server logic | Design cancellation and work limits on the server |

## 14. Practice Exercises

### Exercise 1: Setting both timeout types

Create an `HttpClient` with a 2-second connect timeout and an `HttpRequest` with a 4-second request timeout.

**Suggested solution:**

~~~java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(2))
        .build();

HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://example.com"))
        .timeout(Duration.ofSeconds(4))
        .GET()
        .build();
~~~

### Exercise 2: Resolving loopback

Write a program that prints all addresses returned by `InetAddress.getAllByName("localhost")`.

**Solution:**

~~~java
for (InetAddress address : InetAddress.getAllByName("localhost")) {
    System.out.println(address.getHostAddress());
}
~~~

Do not assert that only a single address is returned.

### Exercise 3: Why avoid port 8080 in tests?

**Solution:** Port 8080 may already be in use by another application. Bind the server to port 0 so the OS allocates a free port, then retrieve the actual port from `server.getAddress().getPort()`.

### Exercise 4: Classifying errors

Match each error with its stage:

- `UnknownHostException`.
- `HttpConnectTimeoutException`.
- `HttpTimeoutException`.
- HTTP status 503.

**Solution:**

- `UnknownHostException`: hostname resolution failed.
- `HttpConnectTimeoutException`: connection could not be established within the allowed time.
- `HttpTimeoutException`: request did not receive a response within the timeout.
- HTTP 503: server returned an HTTP response; the application must handle the status.

### Exercise 5: Testing local request timeout

Start an `HttpServer` on loopback, register an endpoint that sleeps 1 second before replying, send a request with a 200 ms timeout, and catch `HttpTimeoutException`.

**Hint:** Use `InetSocketAddress("127.0.0.1", 0)`, read the dynamic port, and call `server.stop(0)` inside `finally`.

### Exercise 6: Can you set a DNS timeout via connectTimeout?

**Solution:** Do not treat it as a dedicated DNS timeout. `connectTimeout` bounds establishing a new connection; `InetAddress` provides no per-lookup timeout parameter in Java 17. When strict DNS control is needed, design an appropriate resolver or network environment.

## 15. Key Takeaways

When handling network connections in Java 17:

1. Use `HttpClient` and reuse the client across multiple requests.
2. Set `connectTimeout` to bound establishing new connections.
3. Set `HttpRequest.timeout` to bound waiting for a response per request.
4. Use `InetAddress` to resolve hostnames and work with loopback addresses.
5. Remember DNS is cached and Java 17 provides no per-call DNS timeout on `InetAddress`.
6. Distinguish DNS errors, connection errors, request timeouts, and HTTP statuses.
7. Test HTTP using a local server on loopback and a dynamic port.
8. Stop servers and close resources on every execution path.
9. Bound retries, total duration, and response size per application requirements.

A good network test has controllable inputs and environments. Local services allow verifying HTTP, status codes, bodies, and request timeouts without relying on the Internet; DNS and connect timeouts should have dedicated tests in appropriately controlled environments.

## 16. References

- [Oracle Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): client configuration, connect timeout, synchronous and asynchronous sending.
- [Oracle Java SE 17 — HttpRequest](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.html): request timeout and builder.
- [Oracle Java SE 17 — HttpTimeoutException](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpTimeoutException.html): timeout waiting for HTTP response.
- [Oracle Java SE 17 — HttpConnectTimeoutException](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpConnectTimeoutException.html): connection establishment timeout.
- [Oracle Java SE 17 — InetAddress](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/InetAddress.html): hostname resolution, IP addresses, and DNS cache policy.
- [Oracle Java SE 17 — HttpServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): lightweight HTTP server in the `jdk.httpserver` module.
- [Oracle Java SE 17 — StandardSocketOptions](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/StandardSocketOptions.html): connection-level socket options.
- [OpenJDK JEP 321 — HTTP Client](https://openjdk.org/jeps/321): HTTP Client API standardized in Java 11.
