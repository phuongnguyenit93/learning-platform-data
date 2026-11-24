# timeout and Distinguishing Timeouts from Connection Errors in Reactor / Spring WebFlux

## 1. Why Can't Every Network Error Be Called a "Timeout"?

A Spring WebFlux service may call HTTP APIs via WebClient, await a reactive database, or coordinate multiple Monos. When a request fails, at least three distinct situations can occur:

1. **Processing deadline exceeded (deadline/timeout):** the application waited past the allowed interval without receiving the expected signal. For example, a Mono does not return a value within 3 seconds, so the **timeout(Duration)** operator emits an error.
2. **Connection failure:** a connection cannot be established, DNS cannot be resolved, the peer refuses TCP, or the connection is severed. The error can appear **immediately** before any deadline expires.
3. **An HTTP response arrives, but its status indicates an error:** the server or gateway returns **HTTP 408, 429, 500, 502, 503, or 504**. The client **did receive a response**; this is an HTTP status error, not proof that Reactor's timeout operator expired.

These three categories are not synonymous, even though a user interface might describe all of them as "failed to load data". Distinguishing them helps set proper timeouts, log full root causes, control retries, map errors to HTTP responses, and avoid accidentally re-running business operations.

**Scope of this lesson:** the **timeout** mechanism in **Mono/Flux**, how it differs from HTTP/TCP-layer timeouts and connection errors, and how to apply it in **Spring WebFlux/WebClient**.

## 2. Distinguishing Concepts Using a Timeline

Observe an outbound HTTP request:

~~~text
App subscribes to WebClient
    |
    +-- acquire connection from pool
    |      may have to wait on the pool
    |
    +-- DNS lookup (if address not yet resolved)
    |
    +-- TCP connect
    |      may time out or be refused
    |
    +-- TLS handshake (if HTTPS)
    |
    +-- send request
    |
    +-- wait for and read response headers/body
    |      may hit response/read timeout
    |
    +-- decode body, transform, combine results
    |
    +-- Mono onNext + onComplete / empty onComplete
~~~

**The total duration of an operation** can span multiple stages. Each stage can have its own timeout policy; total duration is also affected by queueing, application load, schedulers, retry mechanisms, and business logic.

If you write:

~~~java
Mono<String> result = webClient.get()
        .uri(uri)
        .retrieve()
        .bodyToMono(String.class)
        .timeout(Duration.ofSeconds(3));
~~~

then **timeout(Duration.ofSeconds(3))** applies to the Publisher in front of it: after subscription, if the Mono does not produce the expected result signal before the deadline, the pipeline transitions to a timeout error. It does not tell you exactly whether **DNS, connect, TLS, waiting for response, or body processing** was the slow stage.

Conversely, **connect timeout** is tied specifically to the TCP establishment attempt; **response timeout** is tied to the HTTP response stage per client configuration. A TCP "Connection refused" error can happen after a few milliseconds and is not a timeout.

**Name events accurately:** "Request overall deadline expired" is different from "TCP connect timed out", which is different from "remote server returned HTTP 504".

## 3. What Does Reactor timeout(Duration) Actually Do?

### 3.1. With Mono

**Mono<T>.timeout(Duration)** monitors the wait time before the Mono's value signal. For a source that has not emitted a completion/value signal on time, it emits **java.util.concurrent.TimeoutException** via onError and cancels the upstream subscription.

~~~java
Mono<String> result = Mono.<String>never()
        .timeout(Duration.ofSeconds(2));
~~~

The source **Mono.never()** emits no data, error, or onComplete. Once subscribed, after about 2 seconds, timeout emits onError with **TimeoutException**. The result is neither an empty Mono nor an HTTP 504.

Case where no waiting is needed:

~~~java
Mono<String> immediate = Mono.just("ready")
        .timeout(Duration.ofSeconds(2));
// Emits "ready" and completes normally.
~~~

A Mono that completes successfully or reports a source error before the deadline expires settles the subscription with its own signal. **An early connection error is not turned into TimeoutException by timeout**: the source's onError is forwarded downstream, unless the pipeline has an operator that handles/transforms errors.

**Important:** the timeout starts when the Publisher is **subscribed to**, not when Java creates the Mono variable. If the application creates a CompletableFuture that is already running **before Mono.fromFuture(future)** is built, a timeout operator added later cannot bound the time spent running before subscription.

### 3.2. With Flux

**Flux<T>.timeout(Duration)** monitors the **wait before the first element and the interval between subsequent elements**. It is well suited for detecting a streaming flow that goes silent for too long:

~~~java
Flux<Long> ticks = Flux.interval(Duration.ofSeconds(3))
        .timeout(Duration.ofSeconds(1));
~~~

Because the first element of Flux.interval here arrives after 3 seconds, the 1-second timeout will report an error **before the first element**.

In the opposite direction, if the stream steadily emits elements within the limit, the Flux can run for a very long time without timing out. Because the timer resets after each element, **Flux.timeout(Duration)** is not an overall deadline for the entire stream. To bound the **entire** aggregation process, place the deadline on the final result Mono or use an appropriate overall limiting mechanism.

Example:

~~~java
Mono<List<Long>> allWithinFiveSeconds =
        stream.collectList()
              .timeout(Duration.ofSeconds(5));
~~~

This is an illustrative snippet: **stream** is an application-provided Flux. The outermost operator measures the wait for Mono<List<Long>> to finish collecting, meaning the stream must yield its final result within the deadline. For very large streams, memory must be controlled; timeout does not replace pagination or element limits.

### 3.3. Overload with fallback

~~~java
Mono<String> result = slowSource
        .timeout(Duration.ofSeconds(2), Mono.just("cached"));
~~~

If **slowSource** does not respond within the deadline, Reactor switches to the provided **fallback Mono**. This gives the pipeline a replacement result instead of emitting TimeoutException, **for the timeout branch only**. An early connection error is still an onError from the source and is not automatically turned into the fallback by the fallback timeout overload.

Keep in mind:

- The fallback may contain stale data; the API must clarify freshness and data source.
- The fallback itself can also be slow, fail, or never finish; total time limits must account for the fallback branch if needed.
- Using a fallback does not guarantee upstream work has stopped on the server.
- There are timeout overloads using a **signal-based expiration Publisher** or a **Scheduler as a clock**, suitable for testing/signal-driven limit scenarios.

### 3.4. Difference from block(Duration)

~~~java
String value = someMono.block(Duration.ofSeconds(2));
~~~

**block(Duration)** is a call that **blocks the calling thread waiting for the result** at a synchronous Java boundary; on timeout, it can throw a RuntimeException with TimeoutException as its cause. This is a different API from **someMono.timeout(Duration)**, which creates **an error signal inside the reactive pipeline**.

In Spring WebFlux, do not put **block()** or **get()/join()** to wait for results inside non-blocking request-handling threads. **Return Mono/Flux** for the framework to manage.

## 4. Timeouts and Connection Errors Differ in Exception Types

A classification table is often helpful when analyzing logs:

| Scenario | Common symptom | Nature |
| --- | --- | --- |
| **Reactor timeout(Duration) expires** | **java.util.concurrent.TimeoutException** from the operator | No result signal within the deadline configured in the pipeline |
| **TCP refused** | **java.net.ConnectException: Connection refused** | Endpoint is not accepting connections on that address/port |
| **TCP connect timed out** | Netty **ConnectTimeoutException** or related timeout class, depending on client | Failed to complete connection handshake within connect limit |
| **DNS host not found** | **UnknownHostException** or resolver error | Hostname could not be resolved before any HTTP response |
| **TLS handshake failed** | **SSLHandshakeException** or related SSL error | Connection failed to complete valid TLS |
| **Reading response timed out** | **ReadTimeoutException**, **SocketTimeoutException**, or driver equivalent | Failed to read data in time at client/transport layer |
| **Connection severed mid-flight** | Connection reset, premature close, I/O exception | Established connection was closed/broken |
| **HTTP 408 Request Timeout** | HTTP status 408; WebClient may emit **WebClientResponseException** | Server sent status 408 |
| **HTTP 504 Gateway Timeout** | HTTP status 504; **WebClientResponseException** | Gateway/proxy sent status 504 when the gateway's upstream timed out |
| **HTTP 429 Too Many Requests** | HTTP status 429 | Server reported rate limiting; may include Retry-After |

**Two TimeoutException classes are easily confused:** Reactor operators usually use **java.util.concurrent.TimeoutException**, whereas some I/O libraries use **java.net.SocketTimeoutException**, a subclass of IOException. Both relate to timing out, but they occur at **different layers**, with distinct diagnostic details and retry policies.

**ConnectException is not ConnectTimeoutException.** For example, a closed port can return "Connection refused" almost instantaneously. Conversely, an unresponsive network can cause **connect timeout** to expire. Do not merge the two phenomena into a single error if you need accurate operations, observability, and remediation.

In **WebClient**, errors before receiving an HTTP response are usually presented as **WebClientRequestException** with a **cause** from the network library; HTTP status errors under default **retrieve()** usually become **WebClientResponseException**. Do not inspect only one surface exception class and conclude the exact TCP root cause: inspect the **cause chain** and timing of the error.

## 5. HTTP 408/504 Is Not Always Caused by Client Timeout

**HTTP 408** usually indicates the server did not receive the full request within the server's allowed time. **HTTP 504** indicates the gateway/proxy did not receive an upstream response within the gateway's own deadline. Both are **statuses sent over HTTP**.

For example, a response arrives in 150 ms:

~~~text
Client sends GET /products
Gateway responds in 150 ms:
HTTP/1.1 504 Gateway Timeout
~~~

At the client, that is an **HTTP 504 response**. Do not log "Reactor timeout after 3 s" just because the status contains the word Timeout: the client's 3-second timeout clock never expired.

Conversely:

~~~text
Client subscribes
After 3 seconds with no result signal
Reactor timeout(3 s) emits TimeoutException
No final HTTP response from the server for that request
~~~

Here the error occurred **on the client side**, with no proof the server sent 504.

**A single request can hit multiple limits at once**: proxy timeout, server timeout, HTTP client response timeout, and Reactor deadline. Whichever signal arrives first usually decides the error observed downstream. From a bare "timeout" message alone, you cannot infer which stage failed; you need per-layer logs and metrics.

## 6. Timeout Layers When Using WebClient and Reactor Netty

In Spring WebFlux using **Reactor Netty**, multiple different time limits can be configured. Distinguish them:

| Limit | Scope | Notes |
| --- | --- | --- |
| **Pool acquire timeout** | Waiting for a connection slot from the pool when exhausted | Indicates connection shortage/load pressure; does not mean remote is slow |
| **DNS resolve timeout** | Waiting for domain name resolution | DNS-stage failure |
| **TCP connect timeout** | Time to establish TCP | Configured via ChannelOption.CONNECT_TIMEOUT_MILLIS |
| **TLS handshake timeout** | Time to negotiate TLS | Appropriate SSL configuration |
| **Response/read timeout** | Stage waiting for/reading response in HTTP client | Configured via HttpClient.responseTimeout(...) or appropriate handlers |
| **Reactor Mono.timeout(...)** | Deadline waiting for the Publisher's result signal | Can span multiple steps combined, depending on operator placement |
| **Flux.timeout(...)** | Deadline before first element / between elements | Suited for streaming and detecting stalled updates |
| **Proxy/gateway/server timeout** | Limit enforced by infrastructure/remote | Can produce HTTP 408/504 or close the connection |

### 6.1. Configuring connect timeout and response timeout

In a Spring Boot WebFlux application that already has Spring WebFlux and Reactor Netty dependencies:

~~~java
import java.time.Duration;
import io.netty.channel.ChannelOption;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;

@Configuration
public class RemoteClientConfiguration {
    @Bean
    WebClient remoteWebClient() {
        HttpClient httpClient = HttpClient.create()
                .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 1_000)
                .responseTimeout(Duration.ofSeconds(2));

        return WebClient.builder()
                .clientConnector(new ReactorClientHttpConnector(httpClient))
                .build();
    }
}
~~~

This is a **configuration snippet in a WebFlux application**, not a standalone program. The code sets:

- **1,000 ms** for the TCP connection establishment stage (when a new connection is needed).
- **2 seconds** for the response timeout policy enforced by Reactor Netty.

**responseTimeout is not automatically equivalent to a fixed end-to-end deadline** covering DNS, pool, connect, TLS, reading the whole response, decoding, and all downstream operators. Consult Reactor Netty documentation for the exact semantics of each timeout and the version in use; for streaming responses, gaps between read operations also matter.

You can place a deadline on the entire result **Mono** at the service layer:

~~~java
public Mono<String> fetchText(WebClient client, String uri) {
    return client.get()
            .uri(uri)
            .retrieve()
            .bodyToMono(String.class)
            .timeout(Duration.ofSeconds(3));
}
~~~

This is an illustrative snippet: client and uri are supplied by the application. **Placing timeout after bodyToMono** means the result Mono is tracked until data/completion arrives on time; elapsed time may include pool, DNS, connect, response, and decoding depending on how the source is subscribed.

### 6.2. Choosing a time budget with clear priorities

For example, a user request has a 4-second deadline and calls one downstream API:

- You might allocate roughly **1 second for TCP connect**, **2 seconds for response**, while capping the **entire Mono at 3 seconds**.
- You must budget for queueing, DNS/TLS, decoding, fallback, retry, and remaining processing before the 4-second deadline.
- Do not naively add 1 + 2 = 3 and assume every request finishes at exactly 3 seconds; stages/timers can overlap, run sequentially, or be cut short by another limit.
- If retries are used, the limit for the **entire retry chain** must fit inside the budget; otherwise each attempt could consume its own full deadline.

Numbers here are **illustrative only**; measure P95/P99, throughput, error rates, and actual SLAs before choosing production settings.

### 6.3. Waiting on the pool is not a remote failure

When the connection pool is busy, a request may wait for a slot and hit **pendingAcquireTimeout** before even attempting TCP connect. If you blame everything on "external service is slow", operations will tune the wrong thing. Separate **pool acquire**, **DNS**, **connect**, **TLS**, **response**, and **application timeout** with logs/metrics. Growing the pool unboundedly is not safe either because it can push pressure onto upstream.

## 7. Timeout Placement in the Pipeline Changes Meaning

### 7.1. Timeout on each external call

~~~java
Mono<String> first = clientA.fetch()
        .timeout(Duration.ofSeconds(2));

Mono<String> second = clientB.fetch()
        .timeout(Duration.ofSeconds(2));

Mono<String> combined = Mono.zip(first, second)
        .map(tuple -> tuple.getT1() + ":" + tuple.getT2());
~~~

These illustrative snippets assume clientA/clientB return Mono<String>. Each branch has its **own timeout**. When the two calls are subscribed together, each branch's limit starts from its own subscription. One branch failing can fail the zip and cancel the other branch; **cancellation does not guarantee work already running on the server is rolled back**.

### 7.2. Timeout for the entire combination

~~~java
Mono<String> combined = Mono.zip(
        clientA.fetch(),
        clientB.fetch()
)
.map(tuple -> tuple.getT1() + ":" + tuple.getT2())
.timeout(Duration.ofSeconds(3));
~~~

Here the 3-second deadline applies to the **result Mono of the entire combination**. If one call takes longer, the whole combination can time out. It does not automatically report which branch caused it; to diagnose, measure each branch individually.

### 7.3. Timeout before or after retry

~~~java
// Each subscription/attempt is bounded individually:
Mono<String> perAttempt =
        apiCall()
            .timeout(Duration.ofSeconds(1))
            .retryWhen(retryPolicy);

// Overall deadline covering retries and backoff:
Mono<String> wholeOperation =
        apiCall()
            .retryWhen(retryPolicy)
            .timeout(Duration.ofSeconds(3));
~~~

This is an illustrative snippet: **apiCall()** and **retryPolicy** are defined by the application. The meanings differ:

- **timeout before retryWhen**: when retry re-subscribes to the source, each attempt can get a fresh wait window; total elapsed time can exceed a single attempt's timeout.
- **timeout after retryWhen**: the deadline includes retries and the delays between them within that publisher's scope.
- You may need **both**: each attempt bounded, while the whole operation has an overall deadline. Design the retry policy so it accounts for remaining budget.
- If **apiCall()** already created an eager CompletableFuture before subscription, retry might just re-subscribe to the same old Future. To make a fresh request on the next attempt, use a properly **deferred** source such as Mono.defer(...) or an API creating a new Publisher per subscription.

**An early TimeoutException does not prove a "connection error"**. It only tells you a configured pipeline timer expired; the task may still have been waiting on the pool, DNS, CPU, or response.

## 8. Classifying Errors in WebClient Before Deciding Fallback or Retry

### 8.1. WebClientRequestException and WebClientResponseException

In Spring WebClient:

- **WebClientRequestException** typically represents an error raised while sending/executing the request **before a valid HTTP response arrives**, such as host resolution, connection, TLS, or transport errors. The detailed cause is usually in **getCause()**.
- **WebClientResponseException** typically occurs for HTTP error responses handled by default **retrieve()**, carrying the **status code**, headers, and response body where available.
- **java.util.concurrent.TimeoutException** emitted by Reactor's timeout operator is a pipeline deadline error; it is **not wrapped into WebClientRequestException by default**.
- Other kinds such as body decoding errors, mapper errors, business errors, or cancellation must be distinguished; do not turn every Throwable into "network failure".

Example recording distinct error types in a pipeline:

~~~java
Mono<String> result = webClient.get()
        .uri(uri)
        .retrieve()
        .bodyToMono(String.class)
        .timeout(Duration.ofSeconds(3))
        .doOnError(java.util.concurrent.TimeoutException.class,
                error -> log.warn("Downstream overall deadline exceeded", error))
        .doOnError(
                org.springframework.web.reactive.function.client.WebClientRequestException.class,
                error -> log.warn("HTTP request transport failed", error))
        .doOnError(
                org.springframework.web.reactive.function.client.WebClientResponseException.class,
                error -> log.warn("Remote HTTP status failed: {}",
                        error.getStatusCode().value(), error));
~~~

This is an **illustrative snippet in a service that already has webClient, uri, and log**. Not a standalone program. The **doOnError** callbacks only observe errors, **they do not swallow errors**. In practice, standardize metric labels and avoid logging sensitive URLs/tokens/bodies.

### 8.2. Inspecting the cause chain in a controlled way

If the error is **WebClientRequestException**, inspect the cause:

~~~text
WebClientRequestException
  └── cause: java.net.ConnectException       → TCP refused
  └── cause: io.netty.channel.ConnectTimeoutException → TCP connect timeout
  └── cause: java.net.UnknownHostException    → DNS
  └── cause: SSLHandshakeException            → TLS
  └── cause: ReadTimeoutException             → response/read timeout
~~~

These lines are **independent possibilities**, not a cause chain that must appear all at once. Wrapper types depend on library version and request stage. Sometimes the cause is deeper than one level or a different type; do not write classifiers based solely on Exception.getMessage() strings because they are brittle across languages, versions, or transports.

### 8.3. HTTP status errors must be handled by status and business logic

For example, you may want to separate **404 no data**, **429 rate limited**, **503 upstream unavailable**, and **504 gateway timeout**. Use **getStatusCode()** and response details rather than treating them as "connection refused" errors.

HTTP 400/401/403/404 should usually **not be retried as-is** in most workflows because invalid requests or missing permissions will keep failing. HTTP 429/502/503/504 can be retry candidates **per service contract**, rate limits, and operation safety. HTTP 408 also requires checking idempotency and specific context.

**Do not assume 504 is safe to retry for every POST.** The server behind the gateway may have already executed side effects even though the gateway did not receive the response in time.

## 9. RetryWhen and Deadlines: Only Retry with Reason

A retry policy typically considers:

1. **Error type:** overall timeout, connect timeout, connection reset, 429, 503, 504, or business error? Not all share the same policy.
2. **Safety:** idempotent GETs are usually easier to manage than payment or order-creation commands. For side effects, consider idempotency keys, transactions, and deduplication.
3. **Attempt limit:** set max retries; infinite retries can crush upstream and hold requests indefinitely.
4. **Backoff and jitter:** avoid having all clients retry simultaneously at the exact same interval.
5. **Overall deadline:** do not let retries exceed the user response budget; a timeout outside the retry policy is a safeguard.
6. **Observability:** count attempts, causes, per-attempt latency, and final outcome; do not generate huge logs on every retry.
7. **Source configuration:** ensure retries create a fresh I/O attempt when needed; a retained eager source will not re-call the API.

Example bounded retry, only for application-accepted connection errors:

~~~java
Mono<String> resilient = Mono.defer(() -> client.fetchAsync())
        .retryWhen(
                reactor.util.retry.Retry.backoff(
                        2,
                        Duration.ofMillis(200)
                )
                .maxBackoff(Duration.ofSeconds(2))
                .jitter(0.5)
                .filter(error -> error instanceof java.net.ConnectException)
        )
        .timeout(Duration.ofSeconds(4));
~~~

This is an **illustrative snippet**, assuming client.fetchAsync() returns a fresh Mono<String> per subscription. Retries at most **2 extra times after the initial attempt**, with increasing wait and jitter; the overall operation has a 4-second timeout. **In real WebClient usage**, connect errors are usually wrapped inside WebClientRequestException, so the example predicate **catching ConnectException directly** would need adjustment to match your actual classifier/cause chain. Do not copy that exact filter into an app and think it handles all TCP errors.

If retries are exhausted, Reactor may emit a **retry-exhausted exception** wrapping the final error per policy. When logging/mapping errors, inspect the root cause as well; do not identify errors solely by the outer wrapper message.

### Errors that should not be retried automatically

- **Invalid input errors**: 400 validation, bad parameters.
- **Unauthorized**: 401/403, unless there is a proper token-refresh workflow.
- **Mapping/decoding/bug errors**: network retries cannot fix broken Java logic.
- **Non-idempotent commands**: can execute twice if the first response is lost.
- **Severely overloaded systems**: unbounded retries can worsen an outage.

If a request timed out, that does not mean the server did not process it. Especially for write APIs, have a status-check or idempotency mechanism before re-sending.

## 10. Runnable Java 17+ Example: Timeout vs. Connection Error

The example below uses **pure Reactor Core** without opening real network connections. It simulates each signal deterministically:

- **fast:** Mono emits immediately, does not time out.
- **deadline:** Mono.never emits nothing; timeout creates TimeoutException and is handled into the string "TIMEOUT".
- **connection:** Mono emits ConnectException immediately; timeout does not turn it into TimeoutException.
- **retry:** deferred source gets ConnectException the first time, succeeds the second time; **Retry.max(2)** allows up to two retries.

By using Mono.never and deliberately constructed exceptions, the example **does not depend on the internet or a hard-to-reproduce failing server**.

Structure:

~~~text
reactor-timeout-demo/
├── pom.xml
└── src/main/java/TimeoutVsConnectionDemo.java
~~~

File **pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>reactor-timeout-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.6.12</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>TimeoutVsConnectionDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

File **src/main/java/TimeoutVsConnectionDemo.java**:

~~~java
import java.net.ConnectException;
import java.time.Duration;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

public class TimeoutVsConnectionDemo {
    public static void main(String[] args) {
        String fast = Mono.just("OK")
                .timeout(Duration.ofSeconds(1))
                .block();
        System.out.println("fast = " + fast);

        String deadline = Mono.<String>never()
                .timeout(Duration.ofMillis(50))
                .onErrorResume(
                        TimeoutException.class,
                        error -> Mono.just("TIMEOUT"))
                .block();
        System.out.println("deadline = " + deadline);

        String connection = Mono.<String>error(
                        new ConnectException("simulated refusal"))
                .timeout(Duration.ofSeconds(1))
                .onErrorResume(
                        TimeoutException.class,
                        error -> Mono.just("TIMEOUT"))
                .onErrorResume(
                        ConnectException.class,
                        error -> Mono.just("CONNECTION"))
                .block();
        System.out.println("connection = " + connection);

        AtomicInteger attempts = new AtomicInteger();

        Mono<String> request = Mono.defer(() -> {
            int attempt = attempts.incrementAndGet();
            if (attempt == 1) {
                return Mono.error(
                        new ConnectException("temporary refusal"));
            }
            return Mono.just("RECOVERED");
        });

        String retried = request
                .retryWhen(
                        Retry.max(2)
                                .filter(ConnectException.class::isInstance))
                .block();

        System.out.println("retry = " + retried
                + ", attempts = " + attempts.get());
    }
}
~~~

With **JDK 17+**, Maven, and downloaded dependencies, run from the project directory:

~~~bash
mvn -q compile exec:java
~~~

**Lines printed by the program:**

~~~text
fast = OK
deadline = TIMEOUT
connection = CONNECTION
retry = RECOVERED, attempts = 2
~~~

### Explanation of each case

1. **Mono.just("OK")** emits immediately on a synchronous source; the 1-second timeout does not expire.
2. **Mono.never()** emits no signal. Roughly 50 ms after subscription, **timeout** emits **TimeoutException**, and the **onErrorResume(TimeoutException.class, ...)** branch returns "TIMEOUT". Output is deterministic even if actual scheduler delay is not exactly 50 ms.
3. **Mono.error(new ConnectException(...))** emits **ConnectException** immediately. The timeout is disarmed once the source reports an error; the TimeoutException branch **does not** catch it. The ConnectException branch returns "CONNECTION".
4. **Mono.defer(...)** invokes the Supplier on each subscription. The first attempt reports ConnectException, Retry re-subscribes a second time; the second attempt emits "RECOVERED". **Retry.max(2)** allows up to two retries, though only one is needed here.
5. **block()** in the console example is the synchronous boundary for printing output. **Never use block() in a WebFlux request handler**. Monos in controllers/services should be returned to the framework.

### Limitations of the example

This is a simulation of **reactive signals**; it does not test real TCP connectivity and does not demonstrate WebClient's specific exception wrappers. In real applications, DNS/connect/response events come from Reactor Netty/HTTP client and may be wrapped by WebClientRequestException. Use integration tests to verify exact classification for your Spring and driver versions.

## 11. Testing Timeouts Without Real Time Using StepVerifier

A test using **Thread.sleep()** to wait out a timer can be slow and flaky. With **reactor-test**, StepVerifier supports virtual time for compatible operators:

~~~java
import java.time.Duration;
import java.util.concurrent.TimeoutException;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class TimeoutChecks {
    static void verify() {
        StepVerifier.withVirtualTime(
                () -> Mono.<String>never()
                        .timeout(Duration.ofSeconds(5)))
                .expectSubscription()
                .thenAwait(Duration.ofSeconds(5))
                .expectError(TimeoutException.class)
                .verify();

        StepVerifier.create(
                Mono.<String>error(new java.net.ConnectException("refused"))
                        .timeout(Duration.ofSeconds(5)))
                .expectError(java.net.ConnectException.class)
                .verify();
    }
}
~~~

This is an **illustrative test snippet** in a project that already has **reactor-test**; not the standalone Maven program from earlier. With virtual time, sources and timers must be created per StepVerifier rules (inside the Supplier passed to withVirtualTime). The second test verifies that a simulated connection error is not turned into TimeoutException.

In WebClient integration tests, use a controllable test server for cases like:

- Closed port returning **connection refused** immediately.
- Missing DNS or invalid DNS configuration.
- Server accepting the connection but **delaying the response** past response timeout.
- Server sending a **real HTTP 504**, to verify HTTP status classification.
- Response stream starting fast but **stalling between chunks** for long periods, to test read timeout/Flux.timeout.
- Pool exhaustion causing **pendingAcquireTimeout**.
- Cancellation/retry when a request has side effects, to verify whether cancellation reaches the server.

Do not use an external public website outside your control to draw conclusions about exact exception types, since DNS, proxies, TLS, and network conditions can vary.

## 12. Timeout, Cancellation, and the Risk of "Request Still Running on Server"

When a timeout operator expires, it typically **cancels the upstream subscription** and emits an error. In a non-blocking HTTP client, cancellation may close/abort the request on the client side depending on timing; however, you cannot assert that an operation in a backend system was cancelled or rolled back.

Dangerous example:

~~~text
App POST /payments
   |
   +-- Server receives request and executes payment
   |
   +-- Response lost / client times out after 3 seconds
   |
   +-- App retries identical POST
   |
   +-- Risk of charging a second time
~~~

Therefore, for critical write commands:

- Use an **idempotency key** when supported by the API and verify transaction outcomes.
- Provide a **status-query** mechanism after a timeout when it is unknown whether the request was executed.
- Do not retry infinitely or treat every timeout as a guaranteed server-side failure.
- Record **request ID/correlation ID** to correlate logs across client, proxy, and downstream.
- Distinguish **response received**, **request sent**, and **business committed**; those three milestones are not the same.

Timeouts, connect failures, and HTTP 504 can all leave **uncertain outcome state** for write operations: design the application protocol rather than guessing from error labels.

## 13. Observability and Logging to Distinguish Causes

A system with reliable timeouts needs to show operators **which stage was slow and which failure type occurred**:

| Log/metric attribute | Example / meaning |
| --- | --- |
| operation | catalog.fetch, order.details, payment.status |
| correlationId/traceId | Correlate requests across gateway/services |
| remoteService | Service name; avoid logging tokens or URLs containing secrets |
| outcome | success, reactor_deadline, tcp_refused, connect_timeout, dns_failure, read_timeout, http_504 |
| elapsedMs | Observed duration of the whole operation |
| connectElapsedMs / responseElapsedMs | If measurable by the library, split stages |
| attempt | Call attempt 1, 2, 3; retries used |
| exceptionType / rootCauseType | Actual exception class, not just message |
| httpStatus | Present only when an HTTP response arrived |
| fallbackUsed | Whether fallback data was used |
| poolPending / poolAcquireTimeout | Whether connection pool contention occurred |

Metrics to watch over time: **timeout rate**, **connect failed rate**, **HTTP 5xx**, **P50/P95/P99 latency**, pending pool, retry counts, timeout frequency per endpoint, event-loop/CPU utilization, and upstream responsiveness.

When timeouts spike alongside saturated CPU and event loops, the culprit may be **blocking work inside the app** or an overloaded scheduler, not necessarily the network. If "Connection refused" spikes right after a deploy, check listening ports, service discovery, and readiness health checks. If HTTP 504 increases before the client reaches its deadline, inspect the gateway and its upstream.

Name metrics meaningfully instead of one generic **network_error** counter. Never log request bodies or sensitive credentials just to classify timeouts.

## 14. Common Errors and Fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| "TimeoutException means TCP could not connect." | Misdiagnosis; a Mono delayed by queueing/CPU can also time out. | Separate **operator deadline** from TCP exceptions and other timeout layers. |
| "Connection refused is a connection timeout." | Misses immediate port/service-down errors. | Distinguish **ConnectException** from **ConnectTimeoutException**. |
| "HTTP 504 is Reactor's TimeoutException." | Ignores actual response status. | Classify **WebClientResponseException** and status codes. |
| "Putting timeout(2 s) after an eager operation limits from Future creation." | Work running before subscribe is not counted. | Defer source creation with **Mono.defer** or a Supplier when needed. |
| "Flux.timeout(2 s) is a 2-second cap on the whole stream." | A steadily emitting stream can run much longer. | Distinguish **interval between onNext** from **overall deadline**. |
| "responseTimeout(2 s) is the entire request SLA." | May exclude pool, DNS, TLS, and downstream processing. | Add an operation-level deadline and per-phase metrics. |
| "Retrying any error is good." | Causes retry storms, repeated side effects, or crushes upstream. | Filter by error/business type, use backoff/jitter, max attempts, and idempotency. |
| "If it timed out, the server didn't do anything." | May write data twice upon retry. | Use idempotency keys and status-query APIs. |
| "block(Duration) is the same as timeout(Duration)." | Blocks threads and changes exception-handling boundaries. | In WebFlux, keep Mono/Flux and use the timeout operator. |
| "Catch Throwable and return a success fallback for all errors." | Masks bugs, validation, and authorization errors. | Select eligible error types; fail clearly when unrecoverable. |
| "Testing with sleep 100 ms will always be stable." | Flaky under load/CI. | Use StepVerifier virtual time and a controllable test server. |
| "Logging getMessage() alone is enough to classify." | Loses wrapper/cause/status/stage details. | Log exception type, root cause, status, elapsed time, and attempt. |

## 15. Checklist for Designing Timeout and Retry on a WebClient Call

1. **Define the user deadline:** how long is the total request allowed to wait?
2. **Identify the stages:** pool acquire, DNS, TCP connect, TLS, response, decode, and business logic.
3. **Choose layer-specific timeouts:** connect/response/pool for network resources; Reactor timeout to bound the overall Mono when needed.
4. **Place operators properly:** timeout before vs. after retry gives different behavior; you may need both per-attempt and overall limits.
5. **Classify signals:** Reactor TimeoutException, WebClientRequestException with cause, WebClientResponseException with HTTP status.
6. **Choose conditional retries:** transient vs. permanent, idempotent or not, Retry-After present, sufficient budget remaining?
7. **Handle uncertain state:** when the server may have executed a write before timeout, use idempotency and status queries.
8. **Pick valid fallbacks:** is cache/stale data acceptable? Does the fallback need its own deadline?
9. **Verify with tests:** simulate DNS failure, connection refused, TCP connect timeout, response delay, HTTP 504, and cancellation.
10. **Measure in real environments:** P95/P99, error classes, pool saturation, attempts, and upstream metrics; tune limits with data rather than guesswork.

## 16. Remember

**timeout(Duration)** in Reactor sets a wait limit on a **Publisher** signal after subscription and can emit **java.util.concurrent.TimeoutException**; for **Flux**, it primarily measures the first-element wait and gaps between elements. **Connection errors** such as ConnectException, connect timeout, UnknownHostException, and TLS/read timeout originate at the **transport layer**, often wrapped by WebClient in WebClientRequestException. **HTTP 408/504**, on the other hand, are **HTTP response statuses** sent by the server/gateway.

Use both **purpose-specific network-layer timeouts** and **an overall operation deadline**, classify exceptions by layer, configure bounded retries, and control total duration. When a client times out, never assume the server stopped or the transaction rolled back.

**Official documentation:**
- [Project Reactor — Mono.timeout and overloads](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html)
- [Project Reactor — Flux.timeout](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html)
- [Spring Framework — WebClient Configuration / Timeouts](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html)
- [Reactor Netty — HTTP Client Timeout Configuration](https://projectreactor.io/docs/netty/release/reference/http-client.html)
- [Project Reactor — RetryBackoffSpec and error handling](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html)
