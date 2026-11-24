# Distinguishing Network-Layer Timeouts from Chain-Wide Timeout Operators in WebClient

## 1. Why Distinguish the Two Types of Timeouts?

When using `WebClient`, a request can take time across many stages: waiting for the connection pool, resolving DNS, opening a TCP connection, TLS handshake, sending the request, waiting for the response, and reading the body. Two timeout layers are frequently confused:

- **Transport/network-layer timeouts** managed by the HTTP connector. With Reactor Netty, a key example is `responseTimeout`: it limits the silent interval between two network-level read operations while receiving a response.
- **Reactor sequence timeouts** such as `Mono.timeout(Duration)` or `Flux.timeout(Duration)`: they limit how long to wait for Publisher signals according to the semantics of each sequence type.

These two layers protect different things. A response stream can last several minutes and still be valid if it continuously sends data before the network read timeout expires. Conversely, a `Mono` can time out even while the server sends chunks steadily, because `bodyToMono` only emits a result after the entire body has been read and decoded.

**Key point to remember:** `responseTimeout` controls the gap between network reads; `Mono.timeout` controls how long to wait for the `Mono` to emit its result.

## 2. Lifecycle of a Request and Timeout Positions

~~~text
Subscribe WebClient Publisher
          |
          v
  Wait for connection pool
          |
          v
  DNS resolve
          |
          v
  TCP connect
          |
          v
  TLS handshake (HTTPS)
          |
          v
  Send HTTP request
          |
          v
  Wait / read response bytes  <--- responseTimeout
          |
          v
  Decode body into DTO        <--- still inside bodyToMono
          |
          v
  Mono emits result           <--- Mono.timeout
          |
          v
  Complete
~~~

Some timeouts are configured on the connector for specific stages. Reactor operators are placed on the Publisher and monitor signals of the chain they wrap.

Example:

~~~java
Mono<Product> product = webClient.get()
        .uri("/v1/products/{id}", id)
        .retrieve()
        .bodyToMono(Product.class)
        .timeout(Duration.ofSeconds(4));
~~~

With the request above, `Mono.timeout` starts when the Publisher is subscribed. `bodyToMono(Product.class)` emits a `Product` after the body has been read and decoded; therefore, the deadline covers waiting for the request/response and decoding before the `Product` appears.

Placing `timeout` at the end of code does not automatically bound every piece of work in the application. It only monitors the Publisher upstream of that operator itself. If a blocking task or a side effect runs outside the Publisher, this timeout does not manage that task.

## 3. What Is Reactor Netty's responseTimeout?

`HttpClient.responseTimeout(Duration)` configures the maximum duration between network-level data reads while reading a response.

According to Reactor Netty's JavaDoc, this mechanism:

1. Adds a `ReadTimeoutHandler` to the channel pipeline after the request is sent.
2. Monitors the duration between network-level read operations while receiving the response.
3. Removes the handler once the response has been completely received.
4. Can be overridden by request-level timeout configuration.

It is a **read-inactivity timeout**. It does not impose a total time limit from when the request begins until the response ends.

For example, the server sends a chunk every 500 ms and the client sets `responseTimeout(Duration.ofSeconds(2))`. As long as network reads continue occurring within intervals under 2 seconds, the response can keep running for many minutes without being stopped by this timeout.

### 3.1. Configuring responseTimeout for Every Request

~~~java
HttpClient httpClient = HttpClient.create()
        .responseTimeout(Duration.ofSeconds(2));

WebClient webClient = WebClient.builder()
        .clientConnector(
                new ReactorClientHttpConnector(httpClient))
        .build();
~~~

This configuration applies to every request going through the provided Reactor Netty connector.

### 3.2. Configuring responseTimeout for a Single Request

When only one endpoint needs a dedicated policy:

~~~java
Mono<String> response = webClient.get()
        .uri("/reports/export")
        .httpRequest(request -> {
            HttpClientRequest nativeRequest =
                    request.getNativeRequest();

            nativeRequest.responseTimeout(
                    Duration.ofSeconds(10));
        })
        .retrieve()
        .bodyToMono(String.class);
~~~

Requires importing `reactor.netty.http.client.HttpClientRequest`. This example uses Reactor Netty's native API; if WebClient uses JDK HttpClient, Jetty, or another connector, it does not have the same native request API.

### 3.3. responseTimeout Is Not Connect Timeout

`responseTimeout` only handles silent intervals while reading the response. It does not replace:

- Connection pool acquire timeout.
- TCP connection establishment timeout.
- DNS timeout.
- TLS handshake timeout.
- Overall business deadline.

If the server has not accepted the connection yet, response read timeout is not the right layer for diagnosing connect failures.

## 4. Mono.timeout(Duration) Limits Wait Time for a Mono Result

A `Mono` emits at most one value. `Mono.timeout(Duration)` emits `TimeoutException` if no `onNext` arrives before the configured duration expires.

~~~java
Mono<Product> product = webClient.get()
        .uri("/v1/products/{id}", id)
        .retrieve()
        .bodyToMono(Product.class)
        .timeout(Duration.ofSeconds(4));
~~~

With `bodyToMono`, the decoder normally emits the DTO only after the body has finished reading. Thus, if the response body takes 7 seconds to finish, a 4-second deadline can expire even if the server sends chunks steadily every 200 ms.

A few details:

- The timer starts on subscribe, not when assembling the Publisher.
- When it expires before `onNext`, Reactor emits `TimeoutException` or subscribes to a fallback if configured.
- If the `Mono` completes empty before the deadline, that is still a normal empty result; no timeout occurs.
- When the timeout wins, Reactor cancels the upstream subscription. The WebClient request is therefore canceled on the client side.
- A timeout does not prove the server did not process the request. The server may have already received and processed a POST before the client stopped waiting for the response.

You can provide a fallback:

~~~java
Mono<Product> product = webClient.get()
        .uri("/v1/products/{id}", id)
        .retrieve()
        .bodyToMono(Product.class)
        .timeout(
                Duration.ofSeconds(4),
                Mono.error(new PartnerDeadlineExceeded()));
~~~

`PartnerDeadlineExceeded` is an application-defined exception. The fallback must have a type compatible with the resulting `Mono`.

## 5. Flux.timeout(Duration) Is Not an Overall Stream Deadline

A `Flux` can emit multiple elements. With `Flux.timeout(Duration)`, the timeout is measured:

- From subscription until the first element.
- Then reset after each element.
- If no new element arrives within the allowed duration, the sequence times out.

Example:

~~~java
Flux<ServerEvent> events = webClient.get()
        .uri("/events")
        .retrieve()
        .bodyToFlux(ServerEvent.class)
        .timeout(Duration.ofSeconds(15));
~~~

If the server emits an event every 5 seconds, the `Flux` can continue running for hours. Each wait interval is shorter than 15 seconds, so no timeout occurs.

| Publisher | Meaning of `timeout(Duration)` |
| --- | --- |
| `Mono<T>` | Waits for a single first value within the specified duration |
| `Flux<T>` | Waits for the first element, then bounds the silent gap between elements |
| `bodyToMono(String.class)` | Usually emits a single String after the body is completely read and decoded |
| `bodyToFlux(DataBuffer.class)` | Can emit multiple buffers while the body is streaming |

If you need to limit the total duration of a finite `Flux` and the data size allows aggregation, you can use:

~~~java
Mono<List<ServerEvent>> allEvents = webClient.get()
        .uri("/events/batch")
        .retrieve()
        .bodyToFlux(ServerEvent.class)
        .collectList()
        .timeout(Duration.ofSeconds(10));
~~~

This approach accumulates all events in memory. Do not use `collectList()` for infinite streams or large bodies.

For large streams requiring an absolute deadline, you must design an independent timer/deadline and cancel the subscription when time runs out. Do not confuse `Flux.timeout(Duration)` with a total stream lifetime limit.

## 6. Comparison Table: Network-Layer Timeouts and Reactor Timeouts

| Criterion | Reactor Netty responseTimeout | Mono.timeout | Flux.timeout |
| --- | --- | --- | --- |
| Operating layer | HTTP connector / Netty channel | Reactor sequence | Reactor sequence |
| Monitors | Interval between network read operations | Wait time for `Mono`'s `onNext` | Interval between `onNext` signals |
| Starts | After the request is sent and the response is being read | On Publisher subscribe | On subscribe; resets after each item |
| Scope | Reading response bytes | Waiting for the Mono value | Waiting for the next item |
| Long stream with steady data | Can run long if read gaps stay below threshold | `bodyToMono` can time out before the body finishes | Does not time out if gaps between items are short enough |
| Typical exception | Netty `ReadTimeoutException` wrapped by connector | `TimeoutException` | `TimeoutException` |
| Used for | Detecting when server/network stops sending data | Deadline for a request returning a single result | Limiting silent time between events |

No single timeout number replaces all these layers. Choose the layer according to the failure mode you need to control.

## 7. Other Timeouts in Reactor Netty

Besides response read timeout, Reactor Netty has dedicated settings for each stage.

| Stage | API | Meaning |
| --- | --- | --- |
| Connection pool | `pendingAcquireTimeout` | Maximum time waiting to borrow a connection from the pool |
| TCP connect | `CONNECT_TIMEOUT_MILLIS` | Maximum time to establish a connection to the remote peer |
| TLS | `handshakeTimeout` | Maximum time to complete the TLS handshake |
| DNS | `queryTimeout` | Maximum time for a DNS query |
| Response read | `responseTimeout` | Maximum interval between network-level response reads |
| Reactive operation | `Mono.timeout` / `Flux.timeout` | Deadline or signal wait interval per Publisher semantics |

Current Reactor Netty release documentation lists reference defaults:

- Pool pending acquire: 45 seconds.
- TCP connect: 30 seconds.
- TLS handshake: 10 seconds.
- DNS query: 5 seconds.
- `responseTimeout`: not set by default.

These values belong to Reactor Netty and may vary by version, configuration, or connector. WebClient also supports JDK HttpClient, Jetty, and Apache HttpComponents; those connectors have their own APIs and defaults. Check your application's actual dependencies before relying on any default value.

### 7.1. Configuring Multiple Timeouts Together

~~~java
ConnectionProvider pool =
        ConnectionProvider.builder("partner-api")
                .maxConnections(40)
                .pendingAcquireTimeout(Duration.ofMillis(400))
                .build();

HttpClient transport = HttpClient.create(pool)
        .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 1_000)
        .responseTimeout(Duration.ofSeconds(2))
        .secure(ssl -> ssl.handshakeTimeout(
                Duration.ofSeconds(3)))
        .resolver(spec -> spec.queryTimeout(
                Duration.ofSeconds(1)));

WebClient partnerClient = WebClient.builder()
        .baseUrl("https://partner.example.test")
        .clientConnector(
                new ReactorClientHttpConnector(transport))
        .build();
~~~

The example requires the corresponding Reactor Netty, Netty, and Spring WebFlux imports. `secure(...)` configures TLS for HTTPS; it is unnecessary for plain HTTP endpoints.

The configuration above controls:

- Pool wait at most 400 ms.
- TCP connect at most 1 second.
- Silent gap while reading response at most 2 seconds.
- TLS handshake at most 3 seconds.
- Each DNS query at most 1 second.

This is still not an overall deadline. A response stream can last longer than 2 seconds if network reads keep arriving continuously. If the business logic needs to limit total request duration, add a timeout on the appropriate Publisher.

## 8. Combining Timeouts Using a Time Budget

Suppose a partner API has a 4-second SLA. An illustrative budget can be divided as follows:

| Component | Example Threshold |
| --- | ---: |
| Connection pool wait | 300 ms |
| TCP connect | 800 ms |
| TLS handshake | 1,000 ms |
| Response read gap | 1,200 ms |
| Total time for Mono request | 4,000 ms |

Phase thresholds do not simply add up to the total deadline. They limit individual stages or wait intervals; the overall timeout is the final guardrail to uphold the SLA.

Example setting a deadline on the result:

~~~java
Mono<PartnerResponse> response = partnerClient.get()
        .uri("/v1/data")
        .retrieve()
        .bodyToMono(PartnerResponse.class)
        .timeout(Duration.ofSeconds(4));
~~~

Set the overall timeout reasonably larger than individual phase timeouts to leave room for sequential stages. If the overall timeout is smaller than a phase timeout, the overall deadline can expire first and mask the phase error you wanted to observe.

Do not choose timeouts based solely on the lowest possible value. Base them on latency percentiles, SLAs, server processing time, body sizes, and caller tolerance.

## 9. Placement of the timeout Operator with Retries

Where `timeout` is placed relative to `retryWhen` changes the scope of the deadline.

### 9.1. Timeout Covering All Retries

~~~java
Mono<Product> result = Mono.defer(this::callOnce)
        .retryWhen(Retry.backoff(
                2, Duration.ofMillis(150)))
        .timeout(Duration.ofSeconds(4));
~~~

`timeout` sits after `retryWhen`, so it covers all retry attempts and backoff durations. The total duration of the retry chain cannot exceed this Publisher deadline without emitting a timeout.

### 9.2. Separate Timeout per Attempt

~~~java
Mono<Product> result = Mono.defer(this::callOnce)
        .timeout(Duration.ofSeconds(2))
        .retryWhen(Retry.backoff(
                2, Duration.ofMillis(150)));
~~~

Here each resubscription has a 2-second timeout. Total duration across multiple attempts and backoff can exceed 2 seconds.

The two approaches are not equivalent. If there is an SLA for the entire operation, place an outer deadline around the whole retry chain. You can still keep a shorter inner timeout per attempt if needed.

### 9.3. Do Not Blindly Retry After a Timeout

When the client times out, the server may have already received and processed the request while the response has not yet arrived. Retrying a POST that creates an order or payment can produce duplicate side effects.

Only retry operations that can be repeated safely or use an idempotency key and corresponding contract. Use a small retry count, backoff, jitter, and a clear overall deadline.

## 10. Timeouts and Cancellation

When `Mono.timeout` or `Flux.timeout` emits a timeout, Reactor cancels the upstream subscription. With WebClient, cancellation can cause the client to stop reading the body and close or discard the connection depending on protocol and connector state.

Cancellation is not a command guaranteeing that the server stops processing. For example:

1. The client sends a POST to generate a report.
2. The server receives the request and starts writing data.
3. The client hits its deadline before receiving the response.
4. The client cancels the subscription.
5. The server may still finish the operation and write the data.

Therefore:

- Do not infer that the server did not process the request solely from a client-side timeout.
- For write operations, use an idempotency key or a status-check mechanism.
- Do not auto-retry without knowing the operation's semantics.
- Track request IDs to look up outcomes after a timeout.
- Ensure client-side resources are cleaned up on cancellation.

## 11. Diagnosing Timeouts via Exceptions and Metrics

Exception names help identify the originating layer, though the connector may wrap exceptions inside a Spring layer.

| Symptom | Investigation Direction |
| --- | --- |
| `PoolAcquireTimeoutException` | Pool full, long pending queue, connections not released in time |
| Connect timeout | DNS resolved an address, but TCP connect did not complete in time |
| `ReadTimeoutException` | No network read occurred within `responseTimeout` |
| `TimeoutException` from Reactor | Publisher did not emit signals within the deadline |
| TLS handshake timeout | Certificate, handshake, network, or slow TLS server |
| DNS query timeout | Slow DNS resolver or nameserver |

You can walk the cause chain:

~~~java
static boolean hasCauseNamed(
        Throwable error, String simpleName) {

    for (Throwable current = error;
         current != null;
         current = current.getCause()) {

        if (current.getClass().getSimpleName()
                .equals(simpleName)) {
            return true;
        }
    }

    return false;
}
~~~

This is an illustrative diagnostic helper. In production code, classify by specific connector exception types and preserve the root cause when translating into a domain exception.

Useful Reactor Netty metrics include:

- DNS resolve time.
- Connect time.
- TLS handshake time.
- Response time.
- Connection pool active, idle, and pending counts.
- Error request count.
- Bytes sent/received.

Split metrics by service and route template. Do not attach raw URLs containing IDs or sensitive query parameters as metric tags, as this can create massive cardinality.

## 12. Runnable Java 17+ Program: Comparing Read-Gap Timeout and Mono Deadline

This program creates a local HTTP server using the JDK's `ServerSocket` and calls the server with WebClient/Reactor Netty.

The server has two endpoints:

- `/pause`: waits 450 ms before sending the response. The client sets a 150 ms response read timeout, so a network read gap timeout occurs.
- `/stream`: sends 6 chunks, spaced 60 ms apart. The total body takes about 360 ms, but each gap between sends is under 150 ms.

The same client has a 150 ms `responseTimeout`. The stream request still succeeds with a 2-second Mono deadline, yet times out when given a 250 ms `Mono.timeout`.

### 12.1. Project Structure

~~~text
webclient-timeout-layers/
  pom.xml
  src/main/java/example/timeout/TimeoutLayersDemo.java
~~~

Requirements: **JDK 17+**, **Maven 3.6.3+**, **Spring Boot 4.1.2**. The Boot BOM manages compatible Spring Framework, Reactor, and Reactor Netty versions.

### 12.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>webclient-timeout-layers</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 12.3. TimeoutLayersDemo.java

~~~java
package example.timeout;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;
import reactor.netty.http.client.HttpClient;

public final class TimeoutLayersDemo {

    private static void writeAscii(
            OutputStream output, String value) throws IOException {

        output.write(value.getBytes(StandardCharsets.US_ASCII));
    }

    private static void writeFixedResponse(
            OutputStream output) throws IOException {

        byte[] body = "late".getBytes(StandardCharsets.UTF_8);

        writeAscii(output,
                "HTTP/1.1 200 OK\r\n"
                + "Content-Type: text/plain; charset=utf-8\r\n"
                + "Content-Length: " + body.length + "\r\n"
                + "Connection: close\r\n\r\n");

        output.write(body);
        output.flush();
    }

    private static void writeChunkedResponse(
            OutputStream output)
            throws IOException, InterruptedException {

        writeAscii(output,
                "HTTP/1.1 200 OK\r\n"
                + "Content-Type: text/plain; charset=utf-8\r\n"
                + "Transfer-Encoding: chunked\r\n"
                + "Connection: close\r\n\r\n");

        output.flush();

        byte[] body = "ABCDEF".getBytes(StandardCharsets.UTF_8);

        for (byte value : body) {
            writeAscii(output, "1\r\n");
            output.write(value);
            writeAscii(output, "\r\n");
            output.flush();
            Thread.sleep(60);
        }

        writeAscii(output, "0\r\n\r\n");
        output.flush();
    }

    private static void handle(Socket socket) {
        try (Socket client = socket) {
            client.setSoTimeout(3_000);

            BufferedReader reader = new BufferedReader(
                    new InputStreamReader(
                            client.getInputStream(),
                            StandardCharsets.US_ASCII));

            String requestLine = reader.readLine();
            if (requestLine == null) {
                return;
            }

            String[] requestParts = requestLine.split(" ");
            String path = requestParts.length > 1
                    ? requestParts[1]
                    : "/";

            String header;
            while ((header = reader.readLine()) != null
                    && !header.isEmpty()) {
                // Read all request headers before sending response.
            }

            OutputStream output = client.getOutputStream();

            if ("/pause".equals(path)) {
                Thread.sleep(450);
                writeFixedResponse(output);
            }
            else if ("/stream".equals(path)) {
                writeChunkedResponse(output);
            }
            else {
                writeAscii(output,
                        "HTTP/1.1 404 Not Found\r\n"
                        + "Content-Length: 0\r\n"
                        + "Connection: close\r\n\r\n");
                output.flush();
            }
        }
        catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
        }
        catch (IOException ignored) {
            // Client may have canceled the request due to timeout.
        }
    }

    private static boolean hasCauseNamed(
            Throwable error, String simpleName) {

        for (Throwable current = error;
             current != null;
             current = current.getCause()) {

            if (current.getClass().getSimpleName()
                    .equals(simpleName)) {
                return true;
            }
        }

        return false;
    }

    private static void expectTimeout(
            String label,
            Mono<?> publisher,
            String expectedCause) {

        try {
            publisher.block(Duration.ofSeconds(3));
            throw new AssertionError(
                    label + " should have timed out");
        }
        catch (RuntimeException error) {
            if (!hasCauseNamed(error, expectedCause)) {
                throw new AssertionError(
                        label + " did not contain " + expectedCause,
                        error);
            }

            System.out.println(label + "=TIMEOUT");
        }
    }

    public static void main(String[] args) throws Exception {
        ServerSocket serverSocket = new ServerSocket(
                0, 50, InetAddress.getByName("127.0.0.1"));

        ExecutorService workers = Executors.newCachedThreadPool(
                task -> {
                    Thread thread = new Thread(task);
                    thread.setDaemon(true);
                    return thread;
                });

        Thread acceptor = new Thread(() -> {
            while (!serverSocket.isClosed()) {
                try {
                    Socket socket = serverSocket.accept();
                    workers.execute(() -> handle(socket));
                }
                catch (IOException error) {
                    if (!serverSocket.isClosed()) {
                        throw new IllegalStateException(error);
                    }
                }
            }
        }, "timeout-demo-acceptor");

        acceptor.setDaemon(true);
        acceptor.start();

        try {
            String baseUrl = "http://127.0.0.1:"
                    + serverSocket.getLocalPort();

            HttpClient transport = HttpClient.create()
                    .responseTimeout(Duration.ofMillis(150));

            WebClient client = WebClient.builder()
                    .baseUrl(baseUrl)
                    .clientConnector(
                            new ReactorClientHttpConnector(transport))
                    .build();

            expectTimeout(
                    "network-read-gap",
                    client.get()
                            .uri("/pause")
                            .retrieve()
                            .bodyToMono(String.class),
                    "ReadTimeoutException");

            Mono<String> streamWithShortDeadline = client.get()
                    .uri("/stream")
                    .retrieve()
                    .bodyToMono(String.class)
                    .timeout(Duration.ofMillis(250));

            expectTimeout(
                    "mono-total-deadline",
                    streamWithShortDeadline,
                    "TimeoutException");

            String stream = client.get()
                    .uri("/stream")
                    .retrieve()
                    .bodyToMono(String.class)
                    .timeout(Duration.ofSeconds(2))
                    .block(Duration.ofSeconds(3));

            if (!"ABCDEF".equals(stream)) {
                throw new AssertionError(
                        "Unexpected body: " + stream);
            }

            System.out.println(
                    "stream-over-read-gap=OK:" + stream);
        }
        finally {
            serverSocket.close();
            workers.shutdownNow();
            acceptor.join(1_000);
        }
    }
}
~~~

### 12.4. Running the Program

In the directory containing `pom.xml`:

~~~bash
mvn -q clean compile exec:java -Dexec.mainClass=example.timeout.TimeoutLayersDemo
~~~

**Expected stdout:**

~~~text
network-read-gap=TIMEOUT
mono-total-deadline=TIMEOUT
stream-over-read-gap=OK:ABCDEF
~~~

Interpretation:

- `/pause` sends no bytes for 450 ms. The 150 ms `responseTimeout` triggers a network read timeout before the server returns headers/body.
- `/stream` sends a chunk every 60 ms. Each silent interval is shorter than 150 ms, so the response read timeout never triggers.
- The total stream duration is about 360 ms. `Mono.timeout(250 ms)` expires because `bodyToMono(String.class)` only emits the String after the body finishes.
- That same stream succeeds with a 2-second Mono deadline even though the total duration exceeds the 150 ms response read timeout.

The program uses local sockets and does not call the Internet. Actual timing can fluctuate slightly depending on the scheduler and OS; thresholds are spaced far enough apart to demonstrate the difference.

## 13. Testing Timeouts with StepVerifier

For pure Reactor logic, you can use virtual time to test without waiting on real wall-clock time:

~~~java
StepVerifier.withVirtualTime(() ->
        Mono.<String>never()
                .timeout(Duration.ofSeconds(2)))
        .thenAwait(Duration.ofSeconds(2))
        .expectError(TimeoutException.class)
        .verify();
~~~

Requires the `reactor-test` dependency in `test` scope. Virtual time is suitable for Reactor operators; it does not simulate DNS, TCP connect, TLS, or network read timeouts of real sockets.

For network-layer timeouts, write integration tests using the actual connector and a server capable of:

- Delaying the first byte.
- Sending chunks steadily.
- Stopping mid-transfer.
- Closing the connection abruptly.
- Sending a body longer than the Mono deadline.

## 14. Common Mistakes

| Mistake | Consequence | How to Handle |
| --- | --- | --- |
| Treating responseTimeout as total response duration | Continuous streams can still run very long | Add a Publisher deadline if an overall limit is needed |
| Treating Mono.timeout as a read inactivity timeout | Cannot distinguish network phases from overall request time | Use `responseTimeout` for read gaps and `Mono.timeout` for the result |
| Using Flux.timeout to limit stream lifetime | Streams emitting events steadily can run indefinitely | Use a separate absolute deadline |
| Setting only connect timeout | Server can accept connections yet stop sending responses | Configure `responseTimeout` |
| Setting only responseTimeout | Pool, DNS, connect, or TLS can still wait on their own timeouts | Set timeouts for each stage |
| Configuring timeouts without checking the connector | Reactor Netty APIs do not apply to other connectors | Identify the actual `ClientHttpConnector` |
| Total timeout smaller than every phase timeout | Overall deadline finishes first and masks phase timeouts | Design an ordered time budget |
| Placing timeout before retry and assuming it covers all retries | Each attempt may get its own timer; total duration runs longer than expected | Place the deadline after the retry chain if an overall limit is needed |
| Retrying every timeout | Can amplify load and duplicate side effects | Retry conditionally with idempotency |
| Assuming cancel means the server stops processing | The server may have already completed the operation | Use idempotency keys and query by request ID |
| Using one timeout for every API | Streaming endpoints and RPC endpoints have different characteristics | Configure per service and operation type |
| Not monitoring pool metrics | Pool saturation gets mistaken for a slow server | Monitor pending acquire and active connections |
| Setting timeouts too short | Increases false timeouts during jitter or GC pauses | Choose thresholds based on latency percentiles and SLAs |

## 15. Production Timeout Design Checklist

- [ ] Identify the connector in use: Reactor Netty, JDK HttpClient, Jetty, or Apache.
- [ ] Have a connection pool wait timeout aligned with concurrency.
- [ ] Have a connect timeout.
- [ ] Have DNS/TLS timeouts when control over those phases is needed.
- [ ] Configure `responseTimeout` for network read inactivity.
- [ ] Set a `Mono` deadline for single-result requests when the business has an overall SLA.
- [ ] For `Flux` streaming, distinguish inter-item timeouts from overall deadlines.
- [ ] Place a timeout around the retry chain if the SLA applies to all attempts and backoff.
- [ ] Preserve root causes to classify timeouts by phase.
- [ ] Monitor pool pending counts, connect time, response time, and request errors.
- [ ] Do not retry write operations without an idempotency strategy.
- [ ] Test slow first bytes, steady streams, interrupted streams, and total body deadline overruns.
- [ ] Do not log URLs/headers containing tokens or sensitive data.

## 16. Self-Check

**Question 1.** What does Reactor Netty's `responseTimeout` measure?

The maximum duration between network-level read operations while reading a response.

**Question 2.** Can a response stream run longer than `responseTimeout`?

Yes. If data continues to be read and every silent interval stays below the timeout, the stream can last longer than the timeout value in total.

**Question 3.** When does `Mono.timeout(Duration)` emit a timeout?

When the `Mono` does not emit `onNext` within the configured duration, measured from subscription.

**Question 4.** Why can `bodyToMono(String.class).timeout(2s)` bound the entire response body?

The String `Mono` only emits after the body has been completely read and decoded; the timer continues waiting for the result throughout that process.

**Question 5.** Is `Flux.timeout(Duration)` an overall deadline?

No. It limits the wait interval between items, starting from subscription for the first item.

**Question 6.** Why can an SSE `Flux` run for hours even with a 15-second timeout?

Because each event arrives before the 15-second silent interval expires, resetting the timer.

**Question 7.** How does `CONNECT_TIMEOUT_MILLIS` differ from `responseTimeout`?

Connect timeout limits establishing a TCP connection; `responseTimeout` limits silent intervals while reading the response.

**Question 8.** Which stage does `pendingAcquireTimeout` control?

The time spent waiting to borrow a connection from the pool when no connection is ready.

**Question 9.** Should `timeout` be placed before or after `retryWhen` when an overall deadline is needed?

Place `timeout` outside after `retryWhen` so it covers all retry attempts and backoff.

**Question 10.** Does a client timeout prove the server has not executed a POST?

No. The server may have already received and processed the request before the client stopped waiting for the response.

**Question 11.** Can `responseTimeout` be used with every WebClient connector?

No. It is a Reactor Netty API; JDK, Jetty, or Apache connectors have their own configurations.

**Question 12.** How should timeouts be tested?

Use virtual time for Reactor operators and integration tests with a real connector/server for DNS, connect, network read gaps, and streaming.

## 17. Official References

- [Spring Framework — WebClient Configuration](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html): configuring `ClientHttpConnector`, Reactor Netty, connect timeout, and response timeout.
- [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): WebClient reactive API and supported connectors.
- [Reactor Netty — HTTP Client Timeout Configuration](https://projectreactor.io/docs/netty/release/reference/http-client.html#timeout-configuration): pool acquire, response, connect, TLS, and DNS timeouts.
- [Reactor Netty — HttpClientRequest JavaDoc](https://projectreactor.io/docs/netty/release/api/reactor/netty/http/client/HttpClientRequest.html): exact semantics of `responseTimeout(Duration)` and bounds between network-level read operations.
- [Reactor Netty — HttpClient JavaDoc](https://projectreactor.io/docs/netty/release/api/reactor/netty/http/client/HttpClient.html): configuring response timeout for `HttpClient`.
- [Reactor Core — Mono JavaDoc](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html): `Mono.timeout` and `onNext` wait semantics.
- [Reactor Core — Flux JavaDoc](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html): `Flux.timeout` and inter-element interval semantics.

**Key Takeaways:** Reactor Netty's network-layer timeout detects silent intervals while reading responses; `Mono.timeout` limits how long to wait for a `Mono` result; `Flux.timeout` limits the silent gap between events. Combine per-phase timeouts with business deadlines, place deadlines outside the retry chain when an overall SLA is required, and remember that client cancellation does not guarantee the server has stopped processing.