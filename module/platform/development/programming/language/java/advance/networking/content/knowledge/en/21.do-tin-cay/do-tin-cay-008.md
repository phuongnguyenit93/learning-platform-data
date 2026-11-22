# TCP keep-alive, HTTP reuse, and application heartbeats serve different purposes

**Topic:** Java Advance - networking  
**Group:** Reliability  
**Goal:** understand three mechanisms often called “keep-alive” that differ in network layer, goal, failure-detection capability, and implementation in Java 17+.

A TCP connection can still respond with ACKs while the Java service is deadlocked. A connection in an HTTP client's pool may have already been closed by a proxy due to an idle timeout. A **GET /ready** heartbeat may return **503** while the HTTP request still makes a complete round trip. Therefore:

- **TCP keep-alive** probes connectivity at the TCP layer when a socket is idle, managed by the OS; it **does not generate HTTP requests**.
- **HTTP keep-alive/persistent connection** allows **connection reuse** for multiple requests/responses to save TCP/TLS handshakes and resources.
- **Application heartbeat** is a message with **health/readiness semantics** and a **deadline**, managed by the application or SDK, to evaluate a specific operational condition.

**SO_KEEPALIVE=true ≠ HTTP connection reused ≠ service ready.** The three mechanisms can coexist, but they do not replace one another. This article includes comparison tables, diagrams, Java APIs, a standalone runnable Java 17 program, a scheduler pattern, real-world failure modes, operational observability, and a checklist.

## 1. Where each mechanism sits

~~~text
Application layer
    GET /ready -> 204/503
    App heartbeat message -> ACK / timeout
    Goal: check app/service against contract
              |
              v
HTTP layer
    HttpClient, connection pool, persistent HTTP/1.1
    HTTP/2 multiplexed streams, HTTP/3 QUIC connection reuse
    Goal: save connections/handshakes
              |
              v
Transport layer (if using TCP)
    Socket SO_KEEPALIVE, kernel idle probes
    Goal: detect some peer/path failures
~~~

| Question | TCP keep-alive | HTTP connection reuse | Application heartbeat |
| --- | --- | --- | --- |
| Which layer? | TCP/OS | HTTP client + server/pool | Business/application protocol |
| Who triggers it? | Kernel when socket is idle and option is enabled | HTTP implementation when sending requests | Scheduler/SDK/app calling health/ping |
| What is sent? | TCP probe, waiting for TCP ACK | Actual HTTP request on an existing connection | /ready request or heartbeat+ACK |
| Purpose | Check partial TCP reachability | Reduce connection opening cost | Check responsiveness/readiness |
| Checks DB, queue, worker? | **No** | **No** | **Only if the endpoint checks them** |
| Detects failures within a few-second SLA? | Not guaranteed, depends on OS timers | Only when send/read encounters an error | Per interval, deadline, threshold |
| Guarantees using the same socket? | Only configures one specific socket | No | No |
| Used for HTTP/3? | No: HTTP/3 runs over QUIC/UDP | Has QUIC reuse, but not TCP | Can have health requests over H3 |

An HTTP heartbeat can be sent over a persistent HTTP connection, and the underlying TCP connection can have SO_KEEPALIVE enabled. There is no conflict when all three operate, but each layer needs its own metrics and error handling.

## 2. TCP SO_KEEPALIVE: a kernel mechanism

**TCP keep-alive** is an optional feature of the TCP stack. When enabled on a TCP socket, after an idle period and under conditions permitted by the operating system, the kernel may send probes to check whether the TCP peer/path is still responding. **RFC 9293 section 3.8.4** explains its optional nature, default-disabled state, and that the default probe interval can be very long; a single unanswered probe must not be treated as sufficient proof that the peer is dead.

In Java 17:

~~~java
// Snippet: the port variable is already defined.
try (Socket socket = new Socket()) {
    socket.setKeepAlive(true);
    socket.connect(new InetSocketAddress("127.0.0.1", port), 2000);
    System.out.println(socket.getKeepAlive()); // true
}
~~~

**Socket.getKeepAlive()==true only confirms that the option is enabled**; it does not prove that a probe was sent, cannot read an HTTP status, and does not invoke a Java server handler. A connection may have just been created and not yet been idle long enough for the kernel to send any keep-alive probe.

Equivalent with SocketChannel:

~~~java
// Java 17 snippet.
try (SocketChannel ch = SocketChannel.open()) {
    ch.setOption(StandardSocketOptions.SO_KEEPALIVE, true);
    ch.connect(new InetSocketAddress("127.0.0.1", port));
}
~~~

**StandardSocketOptions.SO_KEEPALIVE** is a Boolean and probe behavior is **system-dependent**. On platforms that support them, **jdk.net.ExtendedSocketOptions.TCP_KEEPIDLE/TCP_KEEPINTERVAL/TCP_KEEPCOUNT** can change the idle time, interval between probes, and maximum probe count. They are not portable APIs across all sockets/OSes; you must check supportedOptions() and handle unsupported behavior.

**Do not confuse with Socket.setSoTimeout()**: SO_TIMEOUT relates to read() waiting for data; SO_KEEPALIVE is probing an idle TCP connection. Enabling SO_KEEPALIVE **does not replace a request timeout** and does not make the app handler respond faster.

### Why can a TCP peer be alive while the app is dead?

~~~text
Client TCP                  Server kernel             Server app
    | --- keepalive probe ---> |                         |
    | <--------- ACK --------- |                         |
    |                          |     Worker deadlock     |
    | --- GET /ready --------> | -----> not processed --> X
    |     waiting until deadline...
~~~

A TCP ACK can be handled by the kernel without any application worker running. The server can still lose its DB, experience a stop-the-world pause, run out of threads, suffer a queue failure, or lack permission to handle requests. Therefore, **TCP keep-alive is only a TCP-level signal**, not service readiness.

**Sockets you create are different from HttpClient's sockets.** Java 17 **HttpClient.Builder** has no general public setter named tcpKeepAlive(true) to set SO_KEEPALIVE on all sockets owned by the built-in HttpClient. Do not call **Socket.setKeepAlive(true)** on a separate socket and assume the HTTP client also uses that configuration.

## 3. HTTP keep-alive: persistent connection/connection reuse

According to **RFC 9112 section 9.3**, **HTTP/1.1 allows persistent connections by default** if there is no **Connection: close** and other framing conditions allow it. One TCP/TLS connection can serve multiple HTTP requests, avoiding TCP handshake/TLS handshake overhead for each request.

~~~text
Without reuse:
  TCP connect -> TLS -> GET /a -> response A -> close
  TCP connect -> TLS -> GET /b -> response B -> close

With reuse:
  TCP connect -> TLS -> GET /a -> response A
                     -> GET /b -> response B
                     -> GET /c -> response C -> close later
~~~

**HTTP keep-alive does not require Socket.setKeepAlive(true).** They are two independent mechanisms. HTTP/1.1 persistent connections **do not require** the **Connection: keep-alive** header; this is a source of confusion from HTTP/1.0 compatibility. **Connection: close** signals that the connection will not remain persistent after the exchange according to protocol rules.

A persistent connection needs to know message body boundaries; according to the RFC, a server that wants to reuse must receive the entire request body or close, and a client that wants to reuse must read the entire response body. If an HTTP response stream remains open and unconsumed, the client may not reuse the connection.

~~~java
// Java 17: complete body.
HttpResponse<String> res = client.send(
        request, HttpResponse.BodyHandlers.ofString());

// For streaming, the caller is responsible for read-to-EOF or closing.
HttpResponse<InputStream> streamed = client.send(
        request, HttpResponse.BodyHandlers.ofInputStream());

try (InputStream body = streamed.body()) {
    byte[] buffer = new byte[8192];
    int count;
    while ((count = body.read(buffer)) != -1) {
        // Process chunk with size/deadline limits.
    }
}
~~~

These are snippets that require imports and previously created client/request variables. Do not call readAllBytes() on a multi-GB response or an infinite stream just to preserve keep-alive; **closing early** may lose reuse, but is still correct if the consumer does not need the data.

### HTTP/1.1, HTTP/2, and HTTP/3

| Protocol | Connection and reuse | TCP keep-alive |
| --- | --- | --- |
| HTTP/1.1 | One persistent TCP connection for multiple HTTP exchanges | Can be enabled on the TCP socket if the implementation allows |
| HTTP/2 | Multiplexes multiple HTTP streams over one TCP/TLS connection | TCP still exists; however, HTTP/2 PING is a different mechanism |
| HTTP/3 | Multiplexes streams over a QUIC connection running on UDP | **Does not** use TCP; SO_KEEPALIVE does not apply |

**HTTP/2 PING** and **QUIC PING** are control/protocol-level signals; they do not prove **business readiness**. **WebSocket Ping/Pong** also does not automatically confirm that a worker has committed an application message.

## 4. Java HttpClient and the connection pool

**HttpClient** in Java 17 can be built once and reused across many requests. The HTTP client holds configuration, connection resources, auth/proxy/redirect policies, and can reuse connections depending on the implementation.

~~~java
// Java 17 snippet:
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(2))
        .version(HttpClient.Version.HTTP_1_1)
        .followRedirects(HttpClient.Redirect.NEVER)
        .build();

HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://service.example/data"))
        .timeout(Duration.ofSeconds(3))
        .GET().build();

HttpResponse<String> a = client.send(
        request, HttpResponse.BodyHandlers.ofString());
HttpResponse<String> b = client.send(
        request, HttpResponse.BodyHandlers.ofString());
~~~

Using the same instance **creates the opportunity for reuse**, not a guarantee that a and b use **the same socket**. The client/server/proxy may open multiple connections, handle concurrent requests, perform idle eviction, or hit TLS issues or server closes.

**In Java 17, HttpClient is not yet AutoCloseable.** Direct close/shutdown APIs were added in Java 21; do not write try-with-resources for HttpClient when compiling with **--release 17**. Streaming response resources must be closed separately by the consumer.

### Pool idle timeout is not a TCP probe interval

Some OpenJDK builds have the **jdk.httpclient.keepalive.timeout** property specifying how long to keep an **idle HTTP connection in the pool**. This is a **cache eviction policy**, not the interval at which the kernel sends TCP probes. Its default/semantics are implementation- and version-specific. Do not tune this property expecting TCP keep-alive or readiness to be enabled.

**The HTTP Connection/Keep-Alive headers** are also not knobs to enable Socket.SO_KEEPALIVE. In java.net.http, some headers related to connection management are restricted. If HTTP/2/HTTP/3 is used, semantics also differ from HTTP/1.1 hop-by-hop headers.

## 5. Application heartbeat and health contract

An application heartbeat actively asks a remote service about a specific condition. Examples:

- **GET /live** asks whether the process/handler still responds according to the liveness definition.
- **GET /ready** checks whether the service is eligible to receive traffic: workers, DB/queue/dependencies per contract.
- **WebSocket app heartbeat** includes an ID/nonce and ACK, not just a WebSocket control Pong.
- **gRPC health service** returns service status per the protocol.
- A lightweight message or request in the business protocol with its own deadline.

Example /ready:

~~~text
Client GET /ready   ---> Server ready=true
Client <--- 204 No Content

Server switches ready=false

Client GET /ready   ---> Server (TCP/HTTP still working)
Client <--- 503 Service Unavailable
~~~

**HTTP 503 here is a valid response sent by the server**. It indicates the application is reporting not ready, **not that the TCP connection is dead**. Similarly, the TCP peer/kernel may still ACK while /ready times out because the app is deadlocked.

### Liveness differs from readiness

| Check | What can it tell? | What does it not prove? |
| --- | --- | --- |
| TCP keepalive ACK | TCP peer/path responded at probe time | Worker/DB is ready |
| HTTP GET /live → 200 | Live endpoint responded within deadline | All dependencies are ready |
| HTTP GET /ready → 204 | Endpoint says ready per its contract | All future requests will succeed |
| WebSocket Pong | WebSocket protocol peer returned control frame | Business event was processed |
| App heartbeat ACK+nonce | Application received and responded to message correctly | Another job has committed |
| Business receipt/ID | Operation has an outcome per contract | System will not fail next |

**A health endpoint is only as good as its implementation logic.** If /ready always returns 200 without checking the required queue/DB, it does not accurately represent readiness. If every check runs a heavy DB query and 10,000 clients ping simultaneously, the endpoint can cause overload itself.

### Components of a heartbeat

- **Interval**: frequency appropriate for the SLA and traffic.
- **Per-attempt deadline**: connect/request/response timeout.
- **Success predicate**: which status/body/ACK/nonce is valid.
- **Failure threshold**: how many consecutive failures transition to degraded/unhealthy.
- **Recovery threshold**: how many successes to recover, avoiding flapping.
- **Non-overlap**: do not run multiple checks against the same target while the previous round has not finished.
- **Jitter/backoff**: avoid synchronized clients and retry storms.
- **Cancellation/shutdown**: stop tasks, close resources/streams.
- **Observability**: latency, last success, error class, status code.
- **Security**: limit exposure of health details and tokens.

A heartbeat returning 204 proves **the endpoint returned 204 at that moment**; it does not promise that a subsequent POST will succeed.

## 6. Failure scenario: connection reused while service is not ready

A server can still accept HTTP requests while key workers/dependencies are unavailable:

~~~text
T0: GET /resource -> 200, full body, connection can be reused
T1: Application ready=true -> GET /health = 204
T2: DB queue backlog or app switches ready=false
T3: GET /health = 503 (same HTTP protocol working)
T4: Load balancer/routing logic can stop sending business traffic
~~~

**There is no contradiction:** connection reuse is an HTTP-layer capability, while readiness is the result from the health handler. If you only monitor socket status or HTTP 200 counts, you may miss a degraded service.

## 7. Failure scenario: cached connection becomes stale due to LB/NAT

~~~text
Java HttpClient --- TCP A ---> proxy/LB --- TCP B ---> backend
      |                       |                      |
      | -- GET /data -------->|--------------------->|
      |<--- 200 --------------|<---------------------|
      |                       |                      |
      |       idle            |  middlebox closes    |
      |                       |                      |
      | -- next request ----->|   reconnect or fail  |
~~~

**SO_KEEPALIVE** on client TCP A does not prove the state of TCP B. Some middleboxes have independent idle policies and may not reset timers on TCP keepalive probes. An HTTP heartbeat, if it actually traverses the proxy and reaches the backend handler, can reflect a more end-to-end path, but does not **guarantee** keeping the exact idle socket alive or covering every dependency.

**Do not infer from a single stale connection failure that the server process is dead**. The client can reconnect. Also do not force high-frequency heartbeats solely to avoid new handshakes if the cost outweighs the benefit.

## 8. Standalone Java 17 example: demonstrating all three layers

The file **KeepAliveLayersDemo.java** creates an HTTP server on loopback **127.0.0.1** with an OS-assigned port. It runs three checks:

1. A **separate raw Socket** enables **SO_KEEPALIVE** and verifies the flag with **getKeepAlive()**. It does not send HTTP and does not apply the configuration to HttpClient.
2. An **HTTP/1.1 HttpClient** sends two GET **/resource** requests; the server returns a debug header **X-Observed-Peer-Port** recording the client source port to observe potential reuse during **the test run**.
3. Two GET **/health** requests; the first with **ready=true** returns **204**, and after switching **ready=false** it returns **503**; the server increments **healthRequests**.

All requests go to the fixture launched by the program itself, requiring no Internet access. The debug header is for illustration only, **not a standard HTTP connection ID**. Matching client source ports are consistent with reuse on loopback, but are not a mandatory test assertion because pools/proxies/NAT can change them.

### Source code: KeepAliveLayersDemo.java

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public class KeepAliveLayersDemo {
    static final AtomicBoolean ready = new AtomicBoolean(true);
    static final AtomicInteger healthRequests = new AtomicInteger();

    static void resource(HttpExchange exchange) throws IOException {
        try (exchange) {
            byte[] body = "DATA".getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set(
                    "X-Observed-Peer-Port",
                    Integer.toString(exchange.getRemoteAddress().getPort()));
            exchange.sendResponseHeaders(200, body.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(body);
            }
        }
    }

    static void health(HttpExchange exchange) throws IOException {
        try (exchange) {
            healthRequests.incrementAndGet();
            if (ready.get()) {
                exchange.sendResponseHeaders(204, -1);
            } else {
                byte[] body = "NOT_READY".getBytes(StandardCharsets.UTF_8);
                exchange.sendResponseHeaders(503, body.length);
                try (OutputStream out = exchange.getResponseBody()) {
                    out.write(body);
                }
            }
        }
    }

    static HttpRequest get(URI uri) {
        return HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(3))
                .GET().build();
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(new InetSocketAddress(
                InetAddress.getByName("127.0.0.1"), 0), 0);
        server.createContext("/resource", KeepAliveLayersDemo::resource);
        server.createContext("/health", KeepAliveLayersDemo::health);
        server.start();
        try {
            InetSocketAddress address = new InetSocketAddress(
                    "127.0.0.1", server.getAddress().getPort());
            try (Socket raw = new Socket()) {
                raw.setKeepAlive(true);
                raw.connect(address, 2000);
                System.out.println("tcpSO_KEEPALIVE=" + raw.getKeepAlive());
            }

            URI base = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/");
            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(2))
                    .version(HttpClient.Version.HTTP_1_1)
                    .followRedirects(HttpClient.Redirect.NEVER)
                    .build();

            HttpResponse<String> a = client.send(
                    get(base.resolve("resource")),
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));
            HttpResponse<String> b = client.send(
                    get(base.resolve("resource")),
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));
            String firstPeerPort = a.headers()
                    .firstValue("X-Observed-Peer-Port").orElseThrow();
            String secondPeerPort = b.headers()
                    .firstValue("X-Observed-Peer-Port").orElseThrow();
            System.out.println("httpStatuses="
                    + a.statusCode() + "," + b.statusCode());
            System.out.println("httpBodies=" + a.body() + "," + b.body());
            System.out.println("observedSameConnection="
                    + firstPeerPort.equals(secondPeerPort));

            HttpResponse<Void> ok = client.send(
                    get(base.resolve("health")),
                    HttpResponse.BodyHandlers.discarding());
            ready.set(false);
            HttpResponse<Void> notReady = client.send(
                    get(base.resolve("health")),
                    HttpResponse.BodyHandlers.discarding());
            System.out.println("healthStatuses="
                    + ok.statusCode() + "," + notReady.statusCode());
            System.out.println("healthRequests=" + healthRequests.get());
            System.out.println("businessReadyAfterChange=" + ready.get());
        } finally {
            server.stop(0);
        }
    }
}
~~~

### Run and verify

Requires JDK 17+ with the **jdk.httpserver** module. Create the file with the exact name:

~~~bash
javac --release 17 -encoding UTF-8 KeepAliveLayersDemo.java
java KeepAliveLayersDemo
~~~

**Stdout compiled with --release 17 and actually run on JDK 24.0.2:**

~~~text
tcpSO_KEEPALIVE=true
httpStatuses=200,200
httpBodies=DATA,DATA
observedSameConnection=true
healthStatuses=204,503
healthRequests=2
businessReadyAfterChange=false
~~~

**Line-by-line analysis:**

- **tcpSO_KEEPALIVE=true** only confirms enabling the option on the **separate raw Socket**. It does not claim the kernel sent a probe because the idle time in the demo is very short.
- **httpStatuses=200,200** and **httpBodies=DATA,DATA** show that two HTTP requests were sent and received complete response bodies with the same HttpClient.
- **observedSameConnection=true** is an observation from the JDK 24 loopback test: the server saw the same client source port on both GETs. This line **can be false in other environments without violating the API**.
- **healthStatuses=204,503** demonstrates that the HTTP service can still respond while business readiness changes from true to false.
- **healthRequests=2** is the count of HTTP endpoint invocations, unrelated to TCP probes.
- **businessReadyAfterChange=false** is state defined by the test fixture, not representing a production dependency.

The demo does not actually test TCP probes on the wire, TLS, HTTP/2 multiplexing, QUIC, proxies, or load balancers. To observe SO_KEEPALIVE probes, appropriate idle time/timers and packet capture or OS counters are needed. **Do not** modify the test to print “TCP alive” just because getKeepAlive()==true.

## 9. Java 17 application heartbeat scheduler

In practice, health checks are usually run periodically. The following snippet is **not a standalone program**: it assumes **client**, **healthUri**, **scheduler**, **consecutiveFailures**, and application-defined metrics functions already exist.

~~~java
HttpRequest healthRequest = HttpRequest.newBuilder(healthUri)
        .timeout(Duration.ofSeconds(3))
        .GET().build();

ScheduledFuture<?> task = scheduler.scheduleWithFixedDelay(() -> {
    try {
        HttpResponse<Void> response = client.send(
                healthRequest, HttpResponse.BodyHandlers.discarding());
        if (response.statusCode() == 204) {
            consecutiveFailures.set(0);
            recordReady();
        } else {
            int fails = consecutiveFailures.incrementAndGet();
            recordNotReady(response.statusCode(), fails);
        }
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        // The application must handle shutdown/cancel accordingly.
    } catch (IOException e) {
        int fails = consecutiveFailures.incrementAndGet();
        recordTransportFailure(e, fails);
    }
}, 0, 10, TimeUnit.SECONDS);
~~~

**ScheduledExecutorService.scheduleWithFixedDelay** is used so tasks do not overlap when a previous run is still executing; the next run executes after the previous one finishes plus an additional delay. **Do not** let the task block indefinitely: requests must have deadlines and cleanup.

**Lifecycle:** the application must call **task.cancel(...)** and **scheduler.shutdown()** on stop; do not let scheduler threads keep the JVM/resources alive indefinitely. A **consecutive failures** threshold (for example, three runs) can be added before marking unhealthy, along with a separate recovery threshold to avoid flapping.

**The business health contract** here accepts only 204; that is this example's convention. For another service, 200 + a JSON healthy flag or an ACK+nonce message may be right. Do not lump HTTP status 503/401/429 into IOException: they have responses and different root causes/remediations.

### Scheduling table

| Factor | Decision needed |
| --- | --- |
| Interval | How often status is needed before real requests |
| Deadline | HTTP request timeout + app reply deadline |
| Threshold | How many failures mark degraded/unhealthy |
| Recovery | How many successes mark healthy again |
| Jitter | Reduce synchronized health traffic |
| Concurrency | Do not send overlapping checks to the same target |
| Safety | Health requests should be safe/idempotent |
| Cleanup | Cancel/shutdown scheduler, release bodies |
| Metrics | Last success, latency, failure reason |
| Security | Do not leak tokens, cookies, dependency internals |

**Load example:** 20,000 clients sending a heartbeat every 5 seconds generate **4,000 checks/second on average**; if synchronized, spikes within a single second can be much higher. Do not assume more frequent heartbeats are always better. Use jitter, aggregation, or central health checks depending on topology.

## 10. Timeouts and failure detection

| Configuration | What it limits/observes | What it is not |
| --- | --- | --- |
| SO_KEEPALIVE idle timer | When the OS may probe an idle TCP socket | Request timeout |
| TCP probe interval/count | How the OS determines a TCP path is unresponsive | App health deadline |
| HTTP pool idle timeout | How long to keep a connection in the pool | Peer/application liveness |
| HttpClient.connectTimeout | Time to establish a new connection | Total lifetime of all requests |
| HttpRequest.timeout | Request limit per Java contract | Body idle timeout of an already-handed-over stream |
| Heartbeat interval | Frequency of asking readiness | Per-request timeout |
| Heartbeat request deadline | Waiting for a response per contract | Guarantee of future health |
| Business transaction timeout | Limit on a business operation | Guarantee of server rollback |

An **ofInputStream()** request can return an HttpResponse while the body is still open, so streaming applications need additional body idle deadlines/close/cancel handling. **TCP keep-alive does not replace** these deadlines. An **HTTP 503** is a received response; a **connect timeout** may have no HttpResponse at all.

If a POST with side effects has already been committed by the server but the response is lost, unconditional retries can duplicate transactions. **SO_KEEPALIVE, HTTP reuse, and heartbeats do not determine business outcomes by themselves**. You need idempotency keys, server deduplication, or status inquiries per the API contract.

## 11. Middleboxes and multiple hops

~~~text
Java client --- TCP A ---> proxy/LB --- TCP B ---> backend
      |                     |                    |
      |---- HTTP request -->|---- HTTP request -->|
      |<--- HTTP response --|<--- HTTP response --|
      |                     |                    |
      | idle / probe        | closes TCP B       |
      |                     |                    |
      |---- next request -->| reconnect/fail     |
~~~

**SO_KEEPALIVE** on TCP A only probes the **client↔proxy** connection. It proves nothing about TCP B to the backend, let alone whether the backend DB is healthy. An HTTP heartbeat, if forwarded through the proxy and handled by the backend handler, can check end-to-end per contract. The proxy's HTTP client pool also has a different idle policy, so a reused client-side connection does not guarantee a reused backend-side connection.

**NAT/LB may have its own idle timeout** and may not count TCP probes as traffic that resets the timer. Sending /health can make a connection less idle if it actually travels over that connection, but there is no guarantee it keeps every network flow alive. Do not disable timeouts or send continuous heartbeats just because idle connections can be closed normally.

## 12. Classifying failures by the right layer

| Symptom | Accurate signal |
| --- | --- |
| Socket.getKeepAlive()==true | TCP option is enabled |
| TCP probe is ACKed | TCP peer/path responded in that situation |
| Two HTTP GETs have the same peer port in fixture | Observed possible connection reuse |
| HTTP GET /health → 204 | Service reports ready per contract |
| HTTP GET /health → 503 | Service reports not ready, but HTTP still responds |
| GET /health → 401/403 | Auth/permission failure; do not assume server is dead |
| GET /health → 429 | Rate limit/overload; reduce checks/backoff |
| TLS certificate error | Identity/trust failure; no corresponding HTTP status |
| DNS/connect failure | Transport/network error |
| Timeout | No response before deadline; unknown what server processed |
| WebSocket Pong | Control-plane peer responded, not a business ACK |
| HTTP/2 PING ACK | HTTP/2 protocol peer responded, not readiness |
| QUIC PING response | QUIC path is responding, not TCP keepalive |

**Do not map a transport IOException to a fake HTTP 503/500**. Log **httpStatus**, **transportError**, **serviceReady**, and **actualHttpVersion** separately. Do not treat a single failure as the system being permanently dead: consider bounded retries, consecutive failures, and recovery policies.

## 13. Monitoring and observability

A good dashboard separates three groups:

**Transport metrics:** TCP connect attempts/failures, resets, retransmissions, OS socket configuration where measurable, proxy/LB closes, TLS failures.

**HTTP connection metrics:** connection setup latency, new/reused connections where instrumentation allows, idle pool size/lifetime, response protocol version via **HttpResponse.version()**, open/cancelled streaming bodies, request throughput.

**App heartbeat metrics:** health attempts/success/failure, response status and semantic result, response latency, last successful check, consecutive failures, time in DEGRADED/UNHEALTHY, and dependency checker scope.

Example:

~~~text
transport.tcp_keepalive_option=true
http.connection_reused_observed=true
http.version=HTTP_1_1
heartbeat.endpoint=/health
heartbeat.http_status=503
heartbeat.ready=false
heartbeat.latency_ms=(actual measured value)
~~~

These fields **do not conflict**. A connection can be reused while service readiness is false. Do not log raw bodies/secret headers from health requests; avoid creating high-cardinality metrics from URLs containing personal data.

## 14. Common mistakes

| Misconception | Consequence | Fix |
| --- | --- | --- |
| SO_KEEPALIVE=true means the app is alive | Deadlocks go undetected | Separate app heartbeat/ready check |
| TCP keepalive and HTTP keep-alive are the same | Misconfigured layer | Kernel probes differ from connection pools |
| Enabling TCP keepalive automatically sends GET /health | No application traffic | Scheduler or SDK must send it |
| HTTP/1.1 always needs Connection: keep-alive | Redundant/restricted header | HTTP/1.1 is persistent by default |
| Same HttpClient always uses the same socket | Brittle assertions | No reuse guarantee |
| Pooled connections are guaranteed to still be open | Stale sockets via LB | Handle reconnect/failure |
| HTTP 503 means TCP is dead | Misdiagnosis | 503 is an HTTP response |
| /ready returning 200 means DB is healthy | False positive | Health contract must check real dependencies |
| WebSocket Pong means event committed | Broken business state | App-level ack |
| HTTP/3 uses TCP keepalive | Wrong transport | QUIC/UDP is separate |
| Enabling SO_KEEPALIVE suffices for few-second detection | Broken SLA | OS timers are usually long |
| More frequent heartbeats are always better | Health traffic storm | Interval, jitter, caps |
| Heartbeats automatically protect sockets from all LB timeouts | Stale paths still occur | Measure topology and idle policies |
| Forgetting to close InputStream response | Leaks and reduced reuse | Drain or close streaming body |
| Timeout on POST means retry immediately | Duplicate side effects | Idempotency key |
| Treating TCP ACK as business transaction success | Wrong layer | Business receipt/status inquiry |

## 15. Engineering testing

| Scenario | How to simulate | What to evaluate |
| --- | --- | --- |
| SO_KEEPALIVE enabled | Socket.setKeepAlive(true), getKeepAlive | Flag is true, do not claim probes |
| HTTP reuse | Two GETs with same client, server records peer port | Reuse can be observed |
| Server closes idle connection | HTTP test server closes between requests | Reconnect or failure depending on client |
| App not ready while HTTP works | /health 204 then 503 | Distinguish HTTP vs readiness |
| App worker hung | Block handler, keep TCP kernel active | TCP keepalive does not replace deadline |
| Proxy splits TCP A/B | Create middlebox/ingress test | Do not infer one hop proves another |
| Streaming body left open | BodyHandlers.ofInputStream unconsumed | Check cleanup/timeout |
| HTTP 401/403 heartbeat | Invalid token | Authentication error is not app dead |
| HTTP 429 heartbeat | Rate limiter | Backoff, no retry storm |
| Network timeout | Unresponsive server | Reasonable error type/threshold |
| TCP keepalive probes | OS timers + packet capture | Distinguish option true vs real probes |
| HTTP/3 service | QUIC endpoint | TCP options do not affect QUIC |
| POST commit + lost reply | Fixture side-effect then drop response | Idempotency/no duplicates |

**Do not turn observedSameConnection=true in the demo into a hard test across all machines.** Same client source port is only a simple observation without a proxy; the OS/HTTP client may legitimately manage different connections.

## 16. Exercises

1. Distinguish TCP keepalive, HTTP connection reuse, and application heartbeats by layer, message, trigger, and goal.
2. Explain why the kernel ACKs TCP probes when Java workers are deadlocked.
3. Why does default HTTP/1.1 persistence not need Connection: keep-alive?
4. Create an HttpClient used for two GETs. Can you prove both used the same socket using client identity alone?
5. If a proxy has closed an idle connection, what outcomes can the next request encounter?
6. Why must the caller drain/close an ofInputStream body to release resources?
7. Does Socket.setKeepAlive(true) on a raw Socket configure HttpClient's sockets?
8. Compare HTTP/2 PING, WebSocket Pong, and application ACK.
9. Why does TCP SO_KEEPALIVE not apply to HTTP/3/QUIC?
10. A /ready endpoint returns 503 while GET /resource still returns 200. Which state do you mark as unhealthy?
11. Design a heartbeat interval, timeout, threshold, and jitter to detect failures without creating a health traffic storm.
12. Run KeepAliveLayersDemo on Java 17+ and explain each line; which observation is not guaranteed by the Java API?
13. Change the health predicate from HTTP 204 to HTTP 200 + JSON ready flag; how should the body be validated?
14. If 20,000 clients ping every 5 seconds, what is the average number of heartbeat requests per second? How do you handle spikes?
15. Propose a reasonable health check when a service needs a DB/queue but you want to avoid heavy queries.
16. A POST has committed but the response was lost: can TCP keepalive or a heartbeat determine the business outcome? Design idempotency.
17. For an open SSE connection with no events, at which layer do you monitor liveness?
18. Design metrics separating transportError, httpStatus, actualVersion, heartbeatReady, and lastSuccess.

## 17. Pre-deployment checklist

- [ ] Do you know whether you need TCP peer probing, HTTP reuse, or readiness?
- [ ] Are you avoiding using SO_KEEPALIVE to replace request/heartbeat timeouts?
- [ ] Is SO_KEEPALIVE enabled on the right Socket when genuinely needed, with platform timers understood?
- [ ] Are you avoiding assuming HttpClient automatically uses SO_KEEPALIVE from another Socket?
- [ ] Do you understand HTTP/1.1 default persistence, Connection: close, and body framing?
- [ ] Are you reusing HttpClient without assuming it always uses a single TCP socket?
- [ ] Are streaming response bodies read/closed per contract?
- [ ] Do you distinguish HTTP/2 and HTTP/3 reuse from TCP keepalive?
- [ ] Does the health endpoint have a success predicate and check the right dependencies?
- [ ] Do you have interval, deadline, fail/recovery thresholds, jitter, and non-overlap?
- [ ] Is there task/scheduler cleanup on shutdown?
- [ ] Are you aware that proxies/LBs/NATs have different idle policies and TCP hops?
- [ ] Are HTTP 503/401/429 classified separately from DNS/TCP/TLS IOExceptions?
- [ ] Is there an idempotency/retry policy for requests with side effects?
- [ ] Are TCP, HTTP pooling, and application readiness measured separately?
- [ ] Have you tested app not ready while TCP/HTTP are still working?

**Conclusion:** **TCP keep-alive** probes an idle TCP path in the kernel. **HTTP keep-alive** is **connection reuse capability** to send multiple requests efficiently. **Application heartbeat** actively queries a **readiness/liveness** condition over a protocol with **timeouts and policies**. The three mechanisms can be used together, but they are not equivalent: **good TCP ACKs** do not guarantee **HTTP handlers are running**, **good HTTP reuse** does not guarantee **the business service is ready**, and **a ready heartbeat right now** does not promise every future request will succeed.

### Official documentation

- [Java SE 17: Socket.setKeepAlive](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html)
- [Java SE 17: StandardSocketOptions.SO_KEEPALIVE](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/StandardSocketOptions.html)
- [Java SE 17: ExtendedSocketOptions TCP_KEEPIDLE/TCP_KEEPINTERVAL/TCP_KEEPCOUNT](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.net/jdk/net/ExtendedSocketOptions.html)
- [Java SE 17: HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html)
- [Java SE 17: HttpResponse.BodyHandlers](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html)
- [Java SE 17: HttpServer (test fixture)](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html)
- [RFC 9293 — TCP Keep-Alives, section 3.8.4](https://www.rfc-editor.org/rfc/rfc9293)
- [RFC 9112 — HTTP/1.1 Persistence, section 9.3](https://www.rfc-editor.org/rfc/rfc9112)
- [RFC 9113 — HTTP/2](https://www.rfc-editor.org/rfc/rfc9113)
- [RFC 9114 — HTTP/3](https://www.rfc-editor.org/rfc/rfc9114)
- [RFC 6455 — WebSocket](https://www.rfc-editor.org/rfc/rfc6455)
