# Testing Async, Streaming, and Client Disconnects in Spring Boot Web Runtime

## 1. The Testing Challenge: An Unfinished Response Does Not Mean a Completed Request

In a Spring Boot app, testing a `GET /api/hello` returning HTTP 200 is usually straightforward: send the request, wait for the response, and assert status/body. However, when an endpoint processes asynchronously, streams partial data, or the client drops the connection mid-flight, the questions change:

- Did the controller merely **return a Java value**, or did the HTTP response **complete over the network**?
- Did a `Callable` or `DeferredResult` actually begin Servlet async processing, with proper async dispatch and error handling?
- Was a `Flux` subscribed, did it emit all items, and did it complete/error/cancel?
- Did the server **flush** the first chunk/SSE event before the client disconnected?
- Does canceling a client subscription in a test propagate to the server, upstream `WebClient`, database/stream writers, and temporary resources?
- If the server already committed a side effect before the client disconnected, will a retry produce duplicate side effects?
- Is the test running a real server or only a mock controller where disconnect/socket/buffer bugs can never appear?

This lesson belongs to **Web runtime testing**, focusing on **testing async, streaming, and client disconnects** across both Spring MVC/Servlet and Spring WebFlux/Reactive. Examples run on **Java 17+, Spring Boot 3.3.13, Spring Framework 6.1, and Gradle**. Use this version as a learning API baseline; production should use a Spring Boot branch still receiving security support and check changes when upgrading major versions.

End goal: write tests that **observe the right signals**, enforce finite deadlines, never confuse `MockMvc` with a network test, never “test cancellation” with assertions unrelated to subscription, and never rely on arbitrary `Thread.sleep` as the sole synchronization mechanism.

## 2. Three Distinct Lifecycles Within One HTTP Request

```text
             HTTP client                        Spring Boot server
                  │                                   │
                  ├──── GET /stream ─────────────────►│
                  │                                   ├─ Controller invoked
                  │                                   ├─ Callable/Flux created
                  │                                   ├─ async/Publisher subscribed
                  │                                   ├─ item 1 emitted
                  │◄──────── headers + chunk 1 ───────┤
                  │                                   ├─ item 2 emitted
                  │◄──────── chunk 2 ─────────────────┤
        client closes socket / cancels                 │
                  ╳                                   ├─ error/cancel/close signal
                                                      ├─ resource cleanup
                                                      └─ observation terminated
```

There are at least three layers:

1. **Application computation**: the controller returns `Callable`, `DeferredResult`, `Mono`, `Flux`, or `StreamingResponseBody`; the data source begins processing.
2. **HTTP response pipeline**: the message converter/codec encodes and the server writes bytes to the socket, possibly buffering/flushing. An emitted item is **not yet guaranteed** to have reached the browser.
3. **Transport and client**: the connection/socket may close due to client, proxy, server timeout, network reset, or app shutdown. The app only receives the signal once the I/O layer detects and propagates it.

Thus, testing “the service produced 10 events” **does not replace** testing “the client actually read 10 events.” Likewise, `StepVerifier.thenCancel()` on a plain `Flux` **does not by itself prove** a TCP connection closed, unless the Publisher is actually the body of an HTTP client connected to a real server.

### 2.1. Completion, Error, Cancellation

| Signal | When It Usually Occurs | What Can Be Asserted |
|---|---|---|
| `onComplete` | Publisher finishes emitting or HTTP producer ends normally | Event count/final body, post-complete cleanup |
| `onError` | Logic, codec, I/O, or timeout fails | Exception type and error mapping if response uncommitted |
| `cancel` | Subscriber wants no more items, client disconnects, `take`/`timeout` operator | Subscription receives cancel; resources must clean up |
| Servlet async dispatch | `Callable`/`DeferredResult` produces final value | Final response after `asyncDispatch` |
| Servlet client abort | Socket closes, writer may see `IOException` on next write | Eventual cleanup; never assert exact `IOException` type/timing |
| HTTP partial response | Headers/chunk already sent then source errors | Client may receive prefix then EOF/error; do not demand fresh JSON 500 |

**Do not equate `doFinally(CANCEL)` with a network disconnect in all cases**. A `take(2)` operator also triggers an intentional application-level cancellation. To conclude a client disconnected, tests must **act directly on the network client** and verify socket/response consumption evidence.

## 3. Choosing the Test Layer: One Test Cannot Prove Everything

| Tool | Real Server? | Strong At | Does Not Prove |
|---|---|---|---|
| Pure JUnit + fake clock | No | Business state, timeout policies, cleanup functions | HTTP framing/sockets |
| `StepVerifier` | Not required | Reactive items/errors/cancel/demand | TCP disconnect if only testing local `Flux` |
| `MockMvc` | No | MVC mappings, `Callable`/`DeferredResult`, `asyncDispatch`, advice | Servlet container flushing/real client abort |
| `@WebMvcTest` | No | MVC controller slice | Full bean wiring, network/header parser |
| `WebTestClient.bindToController` | No | Fast WebFlux handler/codec assertions | Netty connections/ingress behavior |
| `@WebFluxTest` | No | WebFlux controller slice, mock `WebTestClient` | Real socket disconnect |
| `@SpringBootTest(RANDOM_PORT)` | **Yes** | Server/port/HTTP client over real network | CDN/Kubernetes/LB unless deployed |
| `WebTestClient.bindToServer` | **Yes** | Streaming/SSE body via `FluxExchangeResult` | Does not replace production ingress |
| JDK `HttpClient` + `BodyHandlers.ofInputStream` | **Yes** | Reading chunk-by-chunk and actively closing client stream | Does not guarantee server detects abort instantly |
| Proxy/ingress staging test | **Includes edge** | HTTP/2, compression, buffering, timeouts, TLS | No real production load unless load-tested |

Per Spring Boot 3.3: `@SpringBootTest` defaults to a mock web environment; `RANDOM_PORT` opens an embedded web server on a random port. `MockMvc` uses mock request/response objects rather than real browsers or network sockets. Similarly, `WebTestClient.bindToController(...)` does not run a Reactor Netty server.

**Sensible strategy:** fast, deterministic unit/reactive tests first; a few real HTTP integration tests for streaming/cancellation; finally proxy/staging tests for infrastructure-only issues.

## 4. Spring MVC Async: Controller Returns While Response Stays Open

Spring MVC uses Servlet async processing when controllers return types such as:
- `Callable<T>`: Spring submits the `Callable` to `AsyncTaskExecutor`; upon completion, it dispatches back into the Servlet pipeline.
- `DeferredResult<T>`: the application decides when to call `setResult` or `setErrorResult`; it does not spawn a business task itself.
- `WebAsyncTask<T>`: wrapper around `Callable` with timeout/executor/interceptors.
- `CompletionStage<T>`/`CompletableFuture<T>`: Spring MVC adapts them into an async HTTP result.
- `ResponseBodyEmitter`/`SseEmitter`: sends multiple chunks/events over time.
- `StreamingResponseBody`: callback writing bytes to `OutputStream`; still blocking writes, run on an executor to avoid blocking the initial Servlet request thread.

Brief example:

```java
@GetMapping("/async")
Callable<String> async() {
    return () -> "done";
}
```

The controller returns the `Callable` almost immediately, yet the **response body does not exist yet**. Spring MVC processes the result during the subsequent `ASYNC` dispatch. When using `MockMvc`, tests must trigger that dispatch manually.

### 4.1. Standard MockMvc Pattern

```java
MvcResult pending = mockMvc.perform(get("/async"))
        .andExpect(request().asyncStarted())
        .andExpect(request().asyncResult("done"))
        .andReturn();

mockMvc.perform(asyncDispatch(pending))
        .andExpect(status().isOk())
        .andExpect(content().string("done"));
```

This is a **test fragment** inside a class with `MockMvc` injected and static imports `MockMvcRequestBuilders.get/asyncDispatch`, `MockMvcResultMatchers.request/status/content`. `request().asyncResult(...)` waits for the async result within MockMvc's timeout; then `asyncDispatch(...)` verifies the final response. Asserting the body on the initial `perform(get(...))` inspects an un-dispatched mock response.

### 4.2. DeferredResult Is Not @Async

`DeferredResult` does not spawn a thread itself. Something must invoke `setResult(...)` or `setErrorResult(...)` while avoiding races among completion, timeout, and client disconnect. Conversely, `@Async` on a service method where the controller immediately returns HTTP 202 becomes a **background job detached from the request lifecycle**; it is not an open Servlet async HTTP response.

When using `DeferredResult` for a long wait:
- Set a finite timeout.
- Register `onTimeout`, `onError`, and `onCompletion`.
- Cancel scheduled tasks or remove listeners/subscriptions upon completion/cancellation.
- Check the boolean returned by `setResult(...)`: `false` means result was already set/timed out/completed; stop writing to the response.
- Use safe request IDs; never retain references to every response in an unbounded static map.

## 5. Streaming in MVC and WebFlux: Formats, Flushing, and Buffering

Common formats:

| Format | Producer | What Clients Should Verify |
|---|---|---|
| `text/event-stream` | MVC `SseEmitter` or WebFlux `Flux<ServerSentEvent<T>>` | Event data, ID, order, heartbeats, reconnect contract |
| `application/x-ndjson` | MVC `StreamingResponseBody` or WebFlux `Flux<T>` | Each line is valid JSON, stream ends/frames properly |
| `application/octet-stream` | MVC `OutputStream` or WebFlux `Flux<DataBuffer>` | Bytes, checksum, file close/cleanup |
| Unformatted streaming body | HTTP/2 chunks or chunked HTTP/1.1 | Correct byte contents; never assume 1 chunk = 1 event |
| WebSocket | Servlet/WebFlux WebSocket APIs | Handshake, messages, close codes, error/cancel |
| `Mono<T>` / small JSON body | Single result | Normal status/body; no StepVerifier streaming needed |

**Do not equate one Java `onNext` with one TCP packet.** Framework encoders may coalesce buffers; proxies/nginx/compression may buffer further; HTTP/2 `DATA` frames do not align 1-to-1 with JSON objects. Application tests should assert **decoded events or records**, not that the network sent “exactly 3 TCP packets.”

**Committed headers:** once the server sends status 200 and a chunk, if an error happens later, it normally **cannot rewind and turn the response into JSON 500**. Tests for mid-stream failures should accept a valid prefix followed by EOF/transport error per contract, and verify cleanup/logs. Demanding status 500 after flushing 200 misunderstands HTTP.

**Flushing:** `StreamingResponseBody` can call `outputStream.flush()`, yet that does not guarantee CDNs/browsers see events immediately if proxy buffering/compression is active. SSE heartbeats must also transmit actual bytes; a timer merely updating a counter will not keep idle proxy connections alive.

## 6. When a Client Disconnects: What Can and Cannot Be Guaranteed?

### 6.1. Different Ways Aborts Happen

- Client **receives headers**, reads one SSE line, then closes the body stream.
- Client cancels `Mono`/`Flux` in `WebClient`/`WebTestClient`.
- Browser closes the tab or invokes `AbortController.abort()` on a streaming fetch.
- Client sends TCP FIN or RST, or a proxy resets an HTTP/2 stream.
- Server timeout, pod shutdown, or load balancer idle timeout.
- A reactive `take(n)` operator cancels upstream while the TCP connection remains reusable.

Not every scenario produces **the exact same Java exception or HTTP status**. A Servlet writer may only detect client loss on the next write, after earlier bytes already landed in kernel buffers. In WebFlux, cancellation generally propagates through the reactive subscription, yet blocking callbacks or already-committed side effects do not auto-rollback.

### 6.2. Testing Two Independent Properties

1. **Publisher/resource level:** upon cancel, do `doFinally(CANCEL)` or `usingWhen(asyncCancel)` run? This is a **deterministic unit test** using `StepVerifier`, needing no network.
2. **Network level:** when a client reading a live stream closes the connection, does the server stop streaming and release resources? Use `@SpringBootTest(RANDOM_PORT)` with a real streaming client, asserting **eventual state within a timeout** rather than expecting a specific `IOException` at an exact millisecond.

If a test just runs `Thread.sleep(100)` and checks an `AtomicBoolean` without knowing whether the connection even opened, that is a **test race condition**. Prefer a latch/barrier confirming the request/subscription actually began, or read the first event before actively aborting.

## 7. Project A: Runnable Spring MVC / Servlet Async and Streaming

The example creates a **Java 17+, Spring Boot 3.3.13, Gradle** project with:
- `GET /mvc/callable`: responds via `Callable<String>`.
- `GET /mvc/deferred`: `DeferredResult<String>` completed by a lifecycle-managed scheduler.
- `GET /mvc/fail`: exception thrown inside `Callable`, handled by `@RestControllerAdvice` after async dispatch.
- `GET /mvc/ndjson`: streams 30 JSON lines, flushing each line and cleaning up in `finally`.
- `StreamProbe`: counts active/finished/write errors; strictly for testing and observing cleanup paths.

### 7.1. Structure

```text
mvc-async-stream-test/
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/mvctest/MvcStreamApplication.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/mvctest/
            ├── MvcAsyncMockTest.java
            └── MvcDisconnectNetworkTest.java
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**`src/main/resources/application.properties`:**

```properties
server.port=8080
spring.application.name=mvc-async-stream-test
spring.mvc.async.request-timeout=5s
```

In production, Servlet async also requires a bounded executor. The code below configures an explicit `ThreadPoolTaskExecutor` and `WebMvcConfigurer` instead of relying on an unbounded default executor.

### 7.2. Application, Executor, Controller, and Cleanup

**`src/main/java/com/example/mvctest/MvcStreamApplication.java`:**

```java
package com.example.mvctest;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.Callable;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.async.DeferredResult;
import org.springframework.web.servlet.config.annotation.AsyncSupportConfigurer;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;

@SpringBootApplication
public class MvcStreamApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcStreamApplication.class, args);
    }
}

@Configuration(proxyBeanMethods = false)
class ExecutorBeans {
    @Bean("mvcAsyncExecutor")
    ThreadPoolTaskExecutor mvcAsyncExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(16);
        executor.setThreadNamePrefix("mvc-async-");
        return executor;
    }

    @Bean(destroyMethod = "shutdownNow")
    ScheduledExecutorService deferredScheduler() {
        return Executors.newScheduledThreadPool(1);
    }
}

@Configuration(proxyBeanMethods = false)
class AsyncMvcSupport implements WebMvcConfigurer {
    private final ThreadPoolTaskExecutor executor;

    AsyncMvcSupport(
            @Qualifier("mvcAsyncExecutor")
            ThreadPoolTaskExecutor executor) {
        this.executor = executor;
    }

    @Override
    public void configureAsyncSupport(AsyncSupportConfigurer configurer) {
        configurer.setTaskExecutor(executor);
        configurer.setDefaultTimeout(5000L);
    }
}

@Component
class StreamProbe {
    final AtomicInteger active = new AtomicInteger();
    final AtomicInteger finished = new AtomicInteger();
    final AtomicInteger writeFailures = new AtomicInteger();
}

@RestController
class MvcStreamController {
    private final ScheduledExecutorService scheduler;
    private final StreamProbe probe;

    MvcStreamController(ScheduledExecutorService scheduler,
            StreamProbe probe) {
        this.scheduler = scheduler;
        this.probe = probe;
    }

    @GetMapping("/mvc/callable")
    Callable<String> callable() {
        return () -> {
            Thread.sleep(80);
            return "callable-ok";
        };
    }

    @GetMapping("/mvc/deferred")
    DeferredResult<String> deferred() {
        DeferredResult<String> result = new DeferredResult<>(3000L);
        var scheduled = scheduler.schedule(
                () -> result.setResult("deferred-ok"),
                80, TimeUnit.MILLISECONDS);
        result.onTimeout(() -> result.setErrorResult(
                ResponseEntity.status(504).body("deadline")));
        result.onCompletion(() -> scheduled.cancel(false));
        return result;
    }

    @GetMapping("/mvc/fail")
    Callable<String> fail() {
        return () -> {
            throw new IllegalStateException("simulated async failure");
        };
    }

    @GetMapping(
            path = "/mvc/ndjson",
            produces = "application/x-ndjson")
    StreamingResponseBody ndjson() {
        return output -> {
            probe.active.incrementAndGet();
            try {
                for (int i = 1; i <= 30; i++) {
                    String line = "{\"n\":" + i + "}\n";
                    output.write(
                            line.getBytes(StandardCharsets.UTF_8));
                    output.flush();
                    try {
                        Thread.sleep(60);
                    } catch (InterruptedException interrupted) {
                        Thread.currentThread().interrupt();
                        throw new IOException(
                                "Stream worker interrupted",
                                interrupted);
                    }
                }
            } catch (IOException writeError) {
                probe.writeFailures.incrementAndGet();
                throw writeError;
            } finally {
                // Covers client abort, exception, or normal completion.
                probe.active.decrementAndGet();
                probe.finished.incrementAndGet();
            }
        };
    }
}

@RestControllerAdvice
class MvcErrorAdvice {
    @ExceptionHandler(IllegalStateException.class)
    ResponseEntity<String> handleAsyncError(
            IllegalStateException error) {
        return ResponseEntity.status(503).body("async-error");
    }
}
```

**Why this example compiles and runs:**
- Only `MvcStreamApplication` is a top-level `public class` matching the filename. Other classes are package-private in the same package and scanned automatically.
- `ExecutorBeans` defines an executor with bounded pool/queue; `AsyncMvcSupport` injects the bean from a separate class to avoid constructor dependency cycles inside the same `@Configuration`.
- MVC `Callable` runs on `mvcAsyncExecutor`, dispatching the response once complete.
- `DeferredResult` returns immediately while the scheduler sets the result later; `onTimeout` maps 504, `onCompletion` cancels the task if pending. `setResult` can return `false` if already completed, so production must not assume setting results always succeeds.
- `StreamingResponseBody` writes chunk bytes; `OutputStream` remains blocking I/O and must never run on a Netty event loop.
- `StreamProbe.finished` increments in `finally` regardless of whether all 30 lines finished or threw `IOException`. Thus it only proves the **streaming callback terminated**, not that the client received all 30 events.
- In the demo, `IOException` from client disconnect may be logged by MVC/container; tests should not depend on exact log text.
- The scheduler bean specifies `destroyMethod="shutdownNow"` so threads do not linger after closing the context. Async tasks with real side effects need separate job durability/lease/retry mechanisms.

**Production note:** `Thread.sleep` only simulates work inside the dedicated Servlet async worker; never use sleep to measure exact flush timing or replace production timeouts.

## 8. MockMvc Testing Callable, DeferredResult, and Post-Async-Dispatch Errors

**`src/test/java/com/example/mvctest/MvcAsyncMockTest.java`:**

```java
package com.example.mvctest;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class MvcAsyncMockTest {
    @Autowired
    MockMvc mvc;

    @Test
    void callableIsAsyncAndHasFinalBody() throws Exception {
        MvcResult pending = mvc.perform(get("/mvc/callable"))
                .andExpect(request().asyncStarted())
                .andExpect(request().asyncResult("callable-ok"))
                .andReturn();

        mvc.perform(asyncDispatch(pending))
                .andExpect(status().isOk())
                .andExpect(content().string("callable-ok"));
    }

    @Test
    void deferredResultIsAsyncAndHasFinalBody() throws Exception {
        MvcResult pending = mvc.perform(get("/mvc/deferred"))
                .andExpect(request().asyncStarted())
                .andExpect(request().asyncResult("deferred-ok"))
                .andReturn();

        mvc.perform(asyncDispatch(pending))
                .andExpect(status().isOk())
                .andExpect(content().string("deferred-ok"));
    }

    @Test
    void exceptionInsideCallableReachesControllerAdvice()
            throws Exception {
        MvcResult pending = mvc.perform(get("/mvc/fail"))
                .andExpect(request().asyncStarted())
                .andReturn();

        mvc.perform(asyncDispatch(pending))
                .andExpect(status().isServiceUnavailable())
                .andExpect(content().string("async-error"));
    }
}
```

**Expected result:** all three tests pass given valid dependencies and environment. Do not claim Gradle was executed merely from static code review.

Takeaways:
- Tests 1 and 2 must not call `andExpect(content())` before `asyncDispatch`.
- Error tests must assert after dispatch, since `@ExceptionHandler` processes exceptions when the request resumes.
- MockMvc can verify error handlers and MVC mappings, yet **cannot verify network broken pipes**.
- `request().asyncResult(...)` waits within a bounded MockMvc timeout; on slow CI, raise the bounded async timeout sensibly instead of sleeping a fixed `Thread.sleep(5000)`.
- For real `DeferredResult` endpoints, add tests for timeouts, result/error races, and subscription cleanup, while avoiding unbounded timers or shared static state across test classes.
- Even with `@SpringBootTest` here, omitting `RANDOM_PORT` means there is no real server socket.

### 8.1. What Does Testing DeferredResult Timeouts Require?

To test timeouts deterministically, extract producers and timers behind controllable interfaces/fake clocks, or use `MockAsyncContext` and MVC test support properly. Never write a test waiting literally 3000ms expecting the callback to fire at the exact same millisecond on every Servlet container/CI machine.

At the unit level, invoke `DeferredResult.getResult()` and trigger your service's timeout abstraction directly if designed. At the integration level, use a real embedded server (`RANDOM_PORT`) with a short timeout plus margin, asserting response status/cleanup instead of millisecond-tight deadlines.

**Do not annotate a method with `@Async` and assume the HTTP request became Servlet async**. If the controller returns `ResponseEntity.accepted()` after submitting a task, the HTTP request is already finished; `asyncStarted` tests will not apply.

## 9. Testing Network Disconnects with MVC StreamingResponseBody

To test a real client reading one line and closing the connection, start a **real embedded server**. Java 17's `HttpClient.BodyHandlers.ofInputStream()` returns the body as an `InputStream`; the test can read one line and close the stream to abandon the remainder.

**`src/test/java/com/example/mvctest/MvcDisconnectNetworkTest.java`:**

```java
package com.example.mvctest;

import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class MvcDisconnectNetworkTest {

    @LocalServerPort
    int port;

    @Autowired
    StreamProbe probe;

    @Test
    void clientClosesMidStreamAndWriterEventuallyCleansUp()
            throws Exception {
        int before = probe.finished.get();

        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(3))
                .build();

        HttpRequest request = HttpRequest.newBuilder(
                URI.create("http://127.0.0.1:" + port
                        + "/mvc/ndjson"))
                .header("Accept", "application/x-ndjson")
                .GET()
                .build();

        HttpResponse<InputStream> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofInputStream());

        assertThat(response.statusCode()).isEqualTo(200);

        try (InputStream body = response.body()) {
            BufferedReader reader = new BufferedReader(
                    new InputStreamReader(
                            body, StandardCharsets.UTF_8));

            // Synchronize by reading a real event, not guessing with sleep.
            assertThat(reader.readLine()).isEqualTo("{\"n\":1}");

            // Exiting try closes InputStream before the server emits
            // all 30 records: client actively aborts the body.
        }

        await().atMost(Duration.ofSeconds(6))
                .untilAsserted(() -> {
                    assertThat(probe.finished.get())
                            .isGreaterThan(before);
                    assertThat(probe.active.get()).isZero();
                });
    }
}
```

**What this test actually proves:** a real HTTP streaming response returned status 200, the client read the first record, then the client **closed the body stream**, and the writer completed **eventual cleanup** within the test deadline. The test **does not assert** `writeFailures==1`, because Java `HttpClient`/OS/kernel/proxy buffering or close timing might let the server finish writing before noticing the disconnect.

**Valid uncertainty:** a stream of only 30 records × 60ms means `finally` could also run via **normal completion**. Therefore asserting `finished` here mainly verifies **no hang/leaked active resource after abort**, rather than proving the client triggered an `IOException`. To verify the server explicitly observed a transport abort, add explicit probe/transport hooks, a longer stream, bounded signals, and connector-level integration tests.

Never open an infinite stream and `await().until(active==0)` if the adapter does not detect client close promptly: the test could hang with a worker stuck in I/O. Always bound client/test timeouts and clean up inside `finally`.

### 9.1. Manual Testing with curl

Run:

```bash
gradle bootRun
```

In another terminal:

```bash
curl --no-buffer --max-time 0.3 \
  http://localhost:8080/mvc/ndjson
```

`--no-buffer` tells curl not to buffer output and `--max-time` caps duration, yet the number of printed lines varies with CPU/network and is not invariant stdout. Initial HTTP status can be 200 before curl times out/aborts, with no HTTP 500 to assert. Observe server `StreamProbe`/logs and bytes sent to interpret the result.

## 10. SseEmitter/ResponseBodyEmitter: Cleanup on Timeout or Lost Client

MVC `SseEmitter` fits SSE. `ResponseBodyEmitter` handles multiple serialized/flushed chunks over time. Common callbacks:

```java
// Code fragment inside an MVC controller/service managing emitters.
SseEmitter emitter = new SseEmitter(30_000L);

emitter.onCompletion(() -> removeFromRegistry(emitter));
emitter.onTimeout(() -> removeFromRegistry(emitter));
emitter.onError(error -> removeFromRegistry(emitter));

return emitter;
```

This fragment **does not run standalone** because `removeFromRegistry` is an application method you define. In production:
- Cleanup must be idempotent because completion, timeout, and error callbacks may arrive along close paths.
- If a publisher/scheduler repeatedly calls `emitter.send(...)`, dispose the subscription/cancel the scheduled future when the client drops.
- Per Spring MVC docs, when `emitter.send(...)` throws `IOException` because the client went away, **you should not and need not call `complete()` or `completeWithError()` again just to “signal failure”**; the container tracks async errors and MVC handles the dispatch. Application resource cleanup must still run idempotently.
- If SSE relies on an event broker, deregister the subscriber so references to closed emitters are not retained.
- Heartbeats can be SSE comments or lightweight events, and must flush past proxies to keep connections alive.
- `SseEmitter` does not make Servlet response writes non-blocking; bound executors and protect against slow clients.

**Never test disconnect by calling `emitter.complete()`**: that is normal server-initiated termination, unlike a browser dropping the connection. Also never call `completeWithError(new IOException(...))` and claim you verified a TCP reset.

## 11. Project B: Spring WebFlux SSE, NDJSON, Timeout, and Cancellation

Standalone project using **Spring Boot 3.3.13 + Java 17+ + `spring-boot-starter-webflux`** and Reactor Netty. Omit `spring-boot-starter-web` in this project so the runtime does not switch to MVC.

Endpoints:
- `GET /flux/sse`: infinite SSE, periodically emitting `tick-N`, counting subscriptions/cancellations.
- `GET /flux/ndjson`: emits three JSON records over time, then completes.
- `GET /flux/timeout`: a slow operation times out and maps to 504 **before committing the response**.
- `StreamService`: `Flux.interval` source decoupled from HTTP for unit testing with `StepVerifier.withVirtualTime`.

### 11.1. Project Structure

```text
webflux-stream-test/
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/fluxtest/ReactiveStreamApplication.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/fluxtest/
            ├── ReactiveStreamingIntegrationTest.java
            └── ReactiveCancellationUnitTest.java
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**`src/main/resources/application.properties`:**

```properties
server.port=8081
spring.application.name=webflux-stream-test

# Illustrative example; production must balance body/buffer/time limits.
spring.codec.max-in-memory-size=256KB
```

### 11.2. WebFlux Controller and Cancellation Probe

**`src/main/java/com/example/fluxtest/ReactiveStreamApplication.java`:**

```java
package com.example.fluxtest;

import java.time.Duration;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.publisher.SignalType;

@SpringBootApplication
public class ReactiveStreamApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveStreamApplication.class, args);
    }
}

@Service
class StreamService {
    Flux<Long> ticks(Duration period) {
        return Flux.interval(period);
    }
}

@Component
class ReactiveProbe {
    final AtomicInteger active = new AtomicInteger();
    final AtomicInteger subscriptions = new AtomicInteger();
    final AtomicInteger cancellations = new AtomicInteger();
}

@RestController
class ReactiveStreamController {

    private final StreamService service;
    private final ReactiveProbe probe;

    ReactiveStreamController(StreamService service,
            ReactiveProbe probe) {
        this.service = service;
        this.probe = probe;
    }

    @GetMapping(
            path = "/flux/sse",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    Flux<ServerSentEvent<String>> sse() {
        return service.ticks(Duration.ofMillis(60))
                .map(i -> ServerSentEvent.<String>builder()
                        .id(Long.toString(i))
                        .data("tick-" + i)
                        .build())
                .doOnSubscribe(s -> {
                    probe.subscriptions.incrementAndGet();
                    probe.active.incrementAndGet();
                })
                .doFinally(signal -> {
                    probe.active.decrementAndGet();
                    if (signal == SignalType.CANCEL) {
                        probe.cancellations.incrementAndGet();
                    }
                });
    }

    @GetMapping(
            path = "/flux/ndjson",
            produces = "application/x-ndjson")
    Flux<Tick> ndjson() {
        return service.ticks(Duration.ofMillis(30))
                .take(3)
                .map(i -> new Tick(i));
    }

    @GetMapping("/flux/timeout")
    Mono<ResponseEntity<String>> timeout() {
        return Mono.delay(Duration.ofSeconds(2))
                .map(ignored -> ResponseEntity.ok("late"))
                .timeout(Duration.ofMillis(100))
                .onErrorResume(TimeoutException.class,
                        error -> Mono.just(
                                ResponseEntity.status(504)
                                        .body("deadline")));
    }
}

record Tick(long index) {}
```

**Explanation:**
- `Flux.interval` generates items over time **upon subscription**; never call `subscribe()` inside the controller. The WebFlux server manages the subscription to write the response.
- SSE is a single HTTP response stream with `text/event-stream` encoding, not a new HTTP request per tick.
- `doOnSubscribe` tracks when upstream is subscribed, not merely when the MVC/WebFlux controller method is invoked.
- `doFinally` runs on upstream complete/error/cancel; `ReactiveProbe.cancellations` only increments on `SignalType.CANCEL` at this operator position.
- `/flux/sse` is intentionally infinite to test canceling after two messages; production needs max session age, heartbeats/idle timeouts, and slow-subscriber handling.
- `/flux/ndjson` produces three records `{"index":0}`, `{"index":1}`, `{"index":2}` via Jackson's record codec.
- `/flux/timeout` applies `timeout` **before emitting a response**, so returning 504 intentionally works cleanly. Once chunks have already been sent, you cannot simply change the status to 504.
- `record Tick(long index)` is a package-private Java record; Jackson in Spring Boot 3.3 supports record serialization/deserialization.
- Probes/counters are lab-only. A “cancellations” counter alone does not prove the cause was a browser closing a tab; tests must isolate who canceled.

## 12. WebTestClient Against a Real Server: Testing Streaming and Cancellation

**`src/test/java/com/example/fluxtest/ReactiveStreamingIntegrationTest.java`:**

```java
package com.example.fluxtest;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.FluxExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ReactiveStreamingIntegrationTest {

    @Autowired
    WebTestClient client;

    @Autowired
    ReactiveProbe probe;

    @Test
    void finiteNdjsonContainsThreeRecordsAndCompletes() {
        FluxExchangeResult<Tick> result = client.get()
                .uri("/flux/ndjson")
                .accept(MediaType.parseMediaType(
                        "application/x-ndjson"))
                .exchange()
                .expectStatus().isOk()
                .returnResult(Tick.class);

        StepVerifier.create(result.getResponseBody())
                .expectNext(new Tick(0),
                        new Tick(1),
                        new Tick(2))
                .expectComplete()
                .verify(Duration.ofSeconds(5));
    }

    @Test
    void clientCancellationReachesRealSseServer() {
        int before = probe.cancellations.get();

        FluxExchangeResult<String> result = client.get()
                .uri("/flux/sse")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .returnResult(String.class);

        StepVerifier.create(result.getResponseBody())
                .expectNext("tick-0", "tick-1")
                .thenCancel()
                .verify(Duration.ofSeconds(5));

        // Network disconnect -> server cancellation may be async.
        await().atMost(Duration.ofSeconds(5))
                .untilAsserted(() -> {
                    assertThat(probe.cancellations.get())
                            .isGreaterThan(before);
                });
    }

    @Test
    void preCommitTimeoutMapsToGatewayTimeout() {
        client.get()
                .uri("/flux/timeout")
                .exchange()
                .expectStatus()
                .isEqualTo(504)
                .expectBody(String.class)
                .isEqualTo("deadline");
    }
}
```

**Expected result:** three tests pass when WebFlux server/client/codecs work and resources suffice. Code has been statically reviewed, **not claiming Gradle was executed**. Key points to note:

1. `RANDOM_PORT` + `@AutoConfigureWebTestClient` creates a **real HTTP network client**. `WebTestClient.bindToController(...)` would not prove Netty disconnects.
2. `returnResult(Tick.class)` returns `FluxExchangeResult<Tick>` for testing **multi-record bodies**. Never call `expectBodyList`/`collectList()` on infinite streams.
3. `StepVerifier.create(...).expectNext(...).expectComplete().verify(Duration)` asserts values, ordering, and finite completion.
4. `thenCancel()` actively stops consuming the body in the test, distinct from server `onComplete`. When reading a real HTTP stream, this closes/cancels the client response subscription; the server receives cancellation when the transport detects it.
5. `ReactiveProbe.cancellations` on the server is asynchronous, so Awaitility waits up to 5 seconds instead of `Thread.sleep(200)` followed by an immediate assertion.
6. Cancellation tests are **end-to-end integration assertions sensitive to HTTP client, server connector, and environment**. Across different proxies/adapters, cancel/error mapping or close timing can differ. Do not tweak assertions to “must always cancel within 1 ms” to look deterministic.
7. `/flux/timeout` maps timeout before response commit, making status 504 valid. Once an SSE event has flushed, a later error may only close/error the stream without altering status.

**If a disconnect integration test flakes:** gather HTTP client/probe state, subscription timestamp, first event timestamp, server termination signal, and connection/proxy logs. Use bounded waits and separate “request started” from “server cleaned up.” Never mask flakiness with an unconditional `Thread.sleep(5000)`.

## 13. Unit Tests with StepVerifier: Virtual Time and Cancellation Without Sockets

Network tests carry latency and nondeterminism. **Pure Reactor** logic—delays, timeouts, retries, sequences, cleanup—should be tested fast with `StepVerifier` and, when suitable, `withVirtualTime(...)`.

**`src/test/java/com/example/fluxtest/ReactiveCancellationUnitTest.java`:**

```java
package com.example.fluxtest;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.publisher.SignalType;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.awaitility.Awaitility.await;

class ReactiveCancellationUnitTest {

    @Test
    void virtualTimeVerifiesTicksAndCancellation() {
        StreamService service = new StreamService();
        AtomicReference<SignalType> last =
                new AtomicReference<>();

        StepVerifier.withVirtualTime(
                        () -> service.ticks(
                                        Duration.ofSeconds(1))
                                .doFinally(last::set))
                .expectSubscription()
                .thenAwait(Duration.ofSeconds(2))
                .expectNext(0L, 1L)
                .thenCancel()
                .verify(Duration.ofSeconds(3));

        assertEquals(SignalType.CANCEL, last.get());
    }

    @Test
    void usingWhenExecutesCancelCleanupExactlyOnce() {
        AtomicInteger cleaned = new AtomicInteger();

        Flux<Long> stream = Flux.usingWhen(
                Mono.just("lease"),
                lease -> Flux.interval(Duration.ofMillis(20)),
                lease -> Mono.fromRunnable(
                        cleaned::incrementAndGet),
                (lease, error) -> Mono.fromRunnable(
                        cleaned::incrementAndGet),
                lease -> Mono.fromRunnable(
                        cleaned::incrementAndGet));

        StepVerifier.create(stream)
                .expectNextCount(2)
                .thenCancel()
                .verify(Duration.ofSeconds(3));

        await().atMost(Duration.ofSeconds(2))
                .until(() -> cleaned.get() == 1);
        assertEquals(1, cleaned.get());
    }
}
```

**Explanation:**
- `withVirtualTime(Supplier<Publisher>)` requires **creating the `Flux` inside the lambda** so `Flux.interval` picks up the virtual scheduler. Creating the `Flux` outside the lambda and returning it prevents virtual time from taking effect.
- `thenAwait(Duration.ofSeconds(2))` advances virtual time, sparing tests a real 2-second wait for interval logic.
- `thenCancel()` asserts Publisher-level cancellation; it **opens no TCP connection**.
- `Flux.usingWhen` provides three cleanup handlers: normal completion, error, and cancellation. Here we intentionally cancel after two elements and await the callback.
- `cleaned==1` catches skipped or duplicated cleanup in the demo. When real resource cleanup uses async I/O, assert eventual state after the cleanup Publisher finishes rather than checking an eager boolean set synchronously.
- Every `verify(...)` uses a **finite deadline**. Unbounded `StepVerifier.verifyComplete()` can hang CI forever on bugs; prefer `expectComplete().verify(Duration)`.
- `Flux.usingWhen`'s `"lease"` string is an in-memory contract illustration. Files/sockets/JDBC connections need cleanup on **all** signal paths plus crash recovery for process kills.

## 14. When Does StepVerifier.thenCancel Truly Prove Client Disconnect?

Three syntactically similar patterns operate at different layers:

```java
// A. Unit-level: NO HTTP socket.
StepVerifier.create(Flux.interval(Duration.ofMillis(10)))
        .expectNextCount(2)
        .thenCancel()
        .verify(Duration.ofSeconds(3));
```

```java
// B. Network-level: body of WebTestClient connected to a real server.
FluxExchangeResult<String> result = realClient.get()
        .uri("/flux/sse")
        .exchange()
        .expectStatus().isOk()
        .returnResult(String.class);

StepVerifier.create(result.getResponseBody())
        .expectNextCount(2)
        .thenCancel()
        .verify(Duration.ofSeconds(5));
```

Pattern A only checks Reactor cancellation inside the test JVM. Pattern B cancels the **HTTP response consumer**, propagating stream close/cancellation over the network stack to the server. For end-to-end proof, pair it with a server probe and bounded Awaitility assertion as in section 12. These fragments are not standalone test files; `realClient` must come from `WebTestClient.bindToServer` or injection in `@SpringBootTest(RANDOM_PORT)`.

**Case C: Browser closing a tab** can differ from both. Browser/proxy/socket I/O, HTTP/2 stream resets, idle timeouts, and retry/reconnect behavior require staging/real browser tests when those are primary risks.

Do not define a `client_disconnects` metric purely from every `doFinally(CANCEL)`: `take(n)`, timeout operators, and server policies cancel too. Combine HTTP connector telemetry and recorded cancellation reasons to classify accurately.

## 15. Testing Backpressure, Slow Clients, and Buffering

`Flux` **backpressure** is a demand mechanism between Subscriber and Publisher. However:
- Java objects emitted do not map 1-to-1 to network chunks.
- TCP window flow control, Reactor prefetching, and HTTP codec buffers can let producers generate items ahead of delivery.
- Servlet `StreamingResponseBody` is a blocking writer; slow clients can hold threads during `write`/`flush`.
- Infinite SSE/NDJSON with slow clients can accumulate queues if unbounded `onBackpressureBuffer()` is used.
- `WebTestClient` buffering the whole body via `expectBodyList` on an infinite stream will hang or exhaust memory.

### 15.1. Testing Demand at the Unit Level

```java
Flux<Integer> source = Flux.range(1, 100)
        .doOnRequest(n -> recordRequest(n));

StepVerifier.create(source, 0)
        .thenRequest(2)
        .expectNext(1, 2)
        .thenCancel()
        .verify(Duration.ofSeconds(3));
```

This is an **illustrative fragment**, where `recordRequest(long)` is an app/test callback. `StepVerifier.create(source,0)` starts with demand 0, and `thenRequest(2)` requests 2 items. On pipelines with `flatMap`/`publishOn`, internal operators prefetch, so upstream demand counts do not necessarily equal the test subscriber's demand.

### 15.2. Testing Slow Network Clients

Do not claim performance based solely on `Flux.delayElements`. To properly test slow readers:
1. Server emits events steadily or from a simulated hot source.
2. Client reads record-by-record with controlled delays using JDK `InputStream` or a demand-bounded Reactor client.
3. Measure queue depth, heap/direct buffers, blocked write duration, and event-loss policy.
4. Enforce **bounded total duration and max events** so the test never hangs.
5. Assert business policy behavior: drop-oldest/latest, disconnect slow subscriber, bounded backpressure, or durable replay.

In production, NGINX buffering/compression can temporarily hide slow clients from the application. To prove the system stays memory-safe behind proxies, test specifically against staging proxies/ingress — not just localhost Reactor Netty.

## 16. DataBuffer: Proper Cleanup on Success/Error/Cancel

In WebFlux, `DataBuffer` sometimes wraps Netty pooled/ref-counted buffers. A common bug is retaining a `DataBuffer` past callback completion or dropping buffers via `filter`/`skip` without releasing them.

Spring Framework DataBuffer docs require:
- If the application is the final consumer, release via `DataBufferUtils.release(buffer)` when done reading.
- If operators discard/cancel held buffers, attach `doOnDiscard(DataBuffer.class, DataBufferUtils::release)` at the proper pipeline stage.
- When passing buffers across async boundaries, follow `retain`/`release` ownership contracts; double-release causes errors too.
- Use `DataBufferUtils.join(source, maxByteCount)` only when aggregation is truly required and bounded; prefer streaming for large streams.
- When passing buffers to `response.writeWith(...)`, the server response writer owns consuming/releasing outgoing `DataBuffer` instances per contract. **Never release an outgoing buffer before the server writes it**.
- For file streams, close file channels on cancel/error. `DataBufferUtils.read(path,...,bufferSize)` manages channel closure on terminal/cancel signals.

**Illustrative file download example, not a standalone class:**

```java
// Inside a WebFlux handler with authorized Path path,
// ServerHttpResponse response, and matching DataBufferFactory.
Flux<DataBuffer> content = DataBufferUtils.read(
        path, response.bufferFactory(), 8192);

return response.writeWith(content);
```

If `path` is an app-owned temp file, use `Mono.usingWhen` or a lifecycle manager to **delete the file on completion, error, and cancellation**, offloading `Files.deleteIfExists` onto `boundedElastic`. Remember: **SIGKILL/crashes skip cleanup callbacks**; add a sweeper/orphan reconciliation job.

Never write:

```java
// UNSAFE:
return DataBufferUtils.join(rawDataBuffers)
        .map(buffer -> expensiveWork(buffer))
        .doOnNext(buffer -> buffer.release());
```

That is **broken pseudocode**: `join` lacks a max byte cap, the `map` result may not even be a buffer, the `DataBuffer` interface has no `release()` method like that, and cleanup fails across error/cancel paths. Use `DataBufferUtils.release` with clear ownership/scope and test cancel/error paths; never copy this snippet.

### 16.1. Testing Racy Cleanup

For example, an upload canceled by the client right as the server prepares to commit:
- Client abort notification may arrive before or after disk write.
- A temp file may be created before being registered with the cleanup manager.
- `usingWhen` cleanup runs when the reactive subscription cancels, yet fails to run if the app detached a separate `subscribe()`.
- Once committed, cancellation does not roll back published database rows/files.
- Improperly released streaming request bodies can grow Netty direct memory in load tests.

Tests should assert **final state** (no staging file left behind, permanent file exists only after atomic commit, no orphans), using bounded polling and idempotency. Never assert exact ordering between socket FIN and CPU scheduler callbacks since those events race legitimately.

## 17. Async, Streaming, and HTTP Status When Mid-Stream Errors Occur

| Failure Moment | Possible HTTP Status/Body | What Tests Should Assert |
|---|---|---|
| Before headers/commit | Can map to 4xx/5xx + `ProblemDetail` | Status/error body + observability |
| After headers, before body writes | Status may already be committed | Do not assume it can flip to 500 |
| After first SSE/NDJSON chunk | Client receives prefix, then stream error/EOF | Valid prefix, termination/cleanup, logs |
| When client already closed | Server sees `IOException`/`CANCEL` or detects late | Eventual cleanup, no hardcoded exception class |
| Downstream HTTP succeeded yet response lost | Client sees timeout/connection reset | Idempotency, reconciliation, no blind retry |
| JSON codec fails mid-stream | May abort response/send partial output | Error path/partial data/cleanup, no fresh JSON 500 demanded |

**Anti-pattern example:** streaming 200 SSE, catching an exception, then trying `ResponseEntity.status(500)` to alter the response. Once committed, headers/status cannot change. Terminate the stream, log safely, or emit an application-level error event **if the protocol still allows writing and policy permits**, then close. Never mask a connection failure with plain text saying “HTTP 500” inside SSE where dashboards expect real status 500.

### 17.1. Fault Injection Beats Arbitrary Sleep

Instead of waiting a random 200ms then cutting the network:
1. Use `CountDownLatch` or `Sinks.One` to confirm the server entered the handler.
2. Have the client read the actual **first event**.
3. Actively close/cancel the response consumer.
4. Perform a bounded wait for the cleanup signal.
5. Inspect final resource state and confirm zero orphaned tasks/queues remain.
6. Repeat under mild concurrency, then escalate in stress/chaos suites.

To inject an error after event #2, the source can use `concatWith(Mono.error(...))`, ensuring status has committed or events actually flushed. In MockMvc, without networking, committed-state status results do not prove real socket behavior.

## 18. Timeouts: Distinguishing Four Deadlines

An async/streaming request often spans multiple deadlines:

| Deadline | Example | Scope |
|---|---|---|
| MVC async request timeout | `spring.mvc.async.request-timeout=5s`, `DeferredResult(3000L)` | Container/MVC request async lifecycle |
| Reactive Publisher timeout | `Mono.timeout(Duration)` | Emits timeout error/cancels upstream in pipeline |
| HTTP client response timeout | Reactor Netty `responseTimeout`, JDK client timeout | Prevents client from waiting forever |
| Test verification timeout | `StepVerifier.verify(Duration)`, Awaitility `atMost` | Prevents test suite from hanging forever |

These **do not substitute for one another**. `StepVerifier.verify(Duration.ofSeconds(2))` does not enforce a server processing timeout. A 1s client timeout does not stop a downstream service that already received the request from writing to its DB. A Servlet MVC async timeout does not automatically abort a blocking JDBC query immediately.

In tests:
- Make verification timeouts **larger** than business timeouts with CI margin.
- Never assert exact 100ms wall-clock durations where schedulers/networks jitter.
- Test cleanup callbacks with bounded eventual assertions rather than `Thread.sleep(100)`.
- With `withVirtualTime`, instantiate publishers inside the supplier after virtual scheduling is configured.
- Never try to run real network tests under virtual time—TCP sockets do not follow Reactor's virtual clock.

## 19. Client Disconnect Is Not a Transaction Rollback

Business logic creating an order may commit to the DB right before the client cancels the response. If the client retries the same request without server idempotency, two orders get created.

```text
Client A                   Server B                   Database
   │ POST /orders             │                           │
   ├─────────────────────────►│                           │
   │                          ├── INSERT order ──────────►│
   │                          │◄── COMMIT ✓ ───────────────┤
   │    client abort          │                           │
   ╳                          ├── response write fails    │
   │                          │                           │
   ├── retry same POST ──────►│                           │
   │                          └── insert duplicate? ─────►│
```

**Cancellation is best effort** for cancelable work; it does not roll back committed side effects and cannot guarantee remote servers/DBs perceive it identically. Separate tests for:
- **Network cancellation test:** server stops streaming/cleans up after client abort.
- **Business idempotency test:** two attempts with the same key create only **one** business object; domain transaction/outbox/inbox/unique constraints.
- **Background-work test:** if HTTP returns 202 before job completion, tasks have durable handoff and SIGKILL recovery/retry.
- **Resource test:** temp files/locks/subscriptions are cleaned up even if clients disconnect.

A 200 status written before a connection reset does not prove the caller received the whole response; a `doFinally(CANCEL)` does not prove the database did not commit. These are two distinct verification layers.

## 20. Observability for Async, Streams, and Disconnects

A server dashboard tracking only completed HTTP responses misses connections aborted before observation finishes, especially on JVM kills. Combine:

- HTTP request duration, status/outcome, 5xx/499 (if proxy reports), aborted connection counts at proxy/server.
- Active MVC async requests, streaming executor pool/queue/blocked writes.
- Active WebFlux subscriptions, `ON_COMPLETE`/`ON_ERROR`/`CANCEL`, stream duration.
- SSE/NDJSON messages emitted **and** delivered/acknowledged if the app protocol tracks acks; never conflate the two metrics.
- Reactor Netty pooled/direct memory, `DataBuffer` leak detection in test/staging.
- Client-side latency/errors/timeouts and downstream spans.
- Resource cleanup durations, leftover temp files, orphaned subscriptions/timers.
- Queue overflow and slow-consumer policy counts: drops, replay requests, rejected connections.
- HTTP/2 stream resets, ingress/nginx buffering/idle timeouts.
- Thread pool saturation and Servlet async timeouts.

**Never use raw request URIs/user IDs/tokens as high-cardinality metric labels**. For streams carrying personal data, never log raw payloads/bodies or `Cookie`/`Authorization` headers. Client disconnects are routine events; avoid logging full stack traces every time someone closes a browser tab.

For metrics distinguishing causes:
- Application-level `CANCEL` from `take(2)`.
- Client response consumer cancellation.
- Transport EOF/RST or proxy timeout.
- Server/app shutdown.
- Enforced deadline/timeout.

These causes can produce the same Reactor signal. Distinguishing them reliably requires combining client/proxy/server instrumentation rather than **guessing from a single tag**.

## 21. Flaky Test Causes and Fixes

| Symptom | Possible Cause | Test Fix |
|---|---|---|
| MockMvc body empty despite controller returning `Callable` | Missing `asyncDispatch` | Assert `asyncStarted`/`asyncResult` then dispatch |
| `asyncStarted()` is false | Controller returned sync value or detached `@Async` job | Check return type and request lifecycle |
| `DeferredResult` test intermittently times out | Scheduler delayed, tight timeout, shared state | Bounded wait, fake clock, or event-controlled producer |
| MockMvc disconnect test always passes | MockMvc has no sockets | Switch to `RANDOM_PORT` and a real client |
| SSE test hangs on `expectBodyList` | Infinite stream, client awaits complete | `returnResult(...).getResponseBody()` + `thenCancel` |
| WebTestClient cancels yet server probe lags | Transport cancellation arrives asynchronously | Use bounded await; verify binding to live server |
| Server still emits a few events after client abort | OS/codec/proxy buffering | Do not assert immediate halt; assert eventual cleanup |
| `IOException` differs across Tomcat/Jetty/Netty | Runtime/OS/socket differences | Do not hardcode abort exception class |
| Status 200 then stream error yet test demands 500 | Headers already committed | Assert prefix + terminal error/close |
| `withVirtualTime` waits in real time or emits nothing | `Flux` created outside supplier, custom `Scheduler` | Instantiate timed operators inside lambda |
| Test uses `verifyComplete()` and hangs CI | No verification timeout, `Flux` never completes | `expectComplete().verify(Duration)` |
| Local `StepVerifier.thenCancel` passes while client holds socket | Test not connected to server | Write separate network integration test |
| `DataBuffer` leak on cancel | `filter`/`flatMap` drops buffers without release | `doOnDiscard`, `usingWhen`, clear ownership policy |
| MVC streaming exhausts thread pool | Blocking writer, unbounded executor | Configure bounded MVC async executor, test slow clients |
| Rate test unstable within milliseconds | CI/network scheduler jitter | Assert ordering/upper bounds with margin |
| Timeout test expects 504 yet receives 200 | Timeout applied after data emitted, wrong fallback | Check placement of `timeout`/`onErrorResume` |
| HTTP/2/proxy staging differs from localhost | Buffering/ingress keepalive/compression | Add E2E tests through proxy |
| Process hangs after tests finish | Scheduler/executor threads never shut down | Bean-managed lifecycle, close clients/resources |
| Retry after disconnect creates duplicates | Missing idempotency/reconciliation | Test key uniqueness + business state |
| Metrics miss aborted requests | Server observation stuck open or proxy rejected early | Correlate client/proxy metrics |
| Concurrent tests leak state | Static maps/sinks never cleaned | Per-test resources, `@AfterEach`, bounded polls |

## 22. Pre-Release Testing Matrix

| Group | Case | What Must Be Proven |
|---|---|---|
| MVC async | `Callable` completes normally | `asyncStarted` → `asyncResult` → `asyncDispatch` → 200/body |
| MVC async error | `Callable` throws exception | Advice/status mapping after dispatch |
| MVC `DeferredResult` | `setResult` before deadline | Response dispatches, no hang |
| MVC timeout | Producer never responds | Timeout/error path, callback cleanup |
| MVC SSE | Sends multiple events | IDs/data/format and ordering |
| MVC NDJSON | Client reads multiple lines | Valid JSON per line, finite flush |
| MVC client abort | Read event 1 then close body | Eventual writer/registry cleanup; no hardcoded `IOException` type |
| WebFlux finite stream | Three NDJSON objects | Exact values/order and `onComplete` |
| WebFlux infinite SSE | Read two events then cancel | Client consumer cancels, server eventually releases subscription |
| Reactor virtual time | 2 ticks after 2 virtual seconds | No real wait, accurate sequence |
| Reactor cleanup | `usingWhen` cancel | Cleanup runs exactly once |
| WebFlux timeout | `Mono` slower than budget | HTTP 504 before response commit |
| Stream partial error | Error after first event | Partial body/EOF/error, no status-change expectation |
| WebFlux `DataBuffer` | Cancel mid-stream | Proper release, no direct memory growth |
| Slow client | Very slow reader | Bounded memory/queue, clear drop/replay policy |
| Upload abort | Close request body mid-upload | Temp stage cleanup, partial file never committed |
| Download abort | Close response early | File channel/subscription cleanup |
| Downstream abort | Caller drops while `WebClient` waits | Best-effort cancel, no assumed upstream rollback |
| Client retry | Lost response after DB commit | Idempotency/unique key prevents duplicates |
| Proxy/ingress | Streaming over NGINX/CDN/HTTP2 | No unintended buffering/timeouts |
| Graceful shutdown | `SIGTERM` mid-SSE/request | Bounded close/reconnect, no deployment hang |
| Observability | Error, complete, cancel, 499/5xx | Right layer, no sensitive payload leaks |

Unit tests should run on every commit. Network abort tests can live in integration suites with **controlled** retries if CI is noisy—never mask real bugs with infinite retries. Proxy/ingress/chaos tests should run in staging or pre-release for critical streaming APIs.

## 23. Practical and Deliverable Checklist

- [ ] Choose the right Servlet MVC or WebFlux runtime; never mix API imports mistakenly.
- [ ] MVC async tests use `asyncStarted` + `asyncResult` + `asyncDispatch`.
- [ ] Do not treat `@Async` jobs after HTTP 202 as open async HTTP requests.
- [ ] Use `@SpringBootTest(RANDOM_PORT)` when verifying sockets, flushing, and client disconnects.
- [ ] SSE/NDJSON tests use `FluxExchangeResult` + `StepVerifier` instead of buffering infinite streams.
- [ ] Assert completion on finite streams, cancellation and cleanup on infinite streams.
- [ ] Set explicit verification/await/test deadlines.
- [ ] Create timed `Flux` instances inside the `withVirtualTime` supplier.
- [ ] When testing client aborts, read the first event before closing/canceling.
- [ ] Distinguish local Publisher `CANCEL` from real transport disconnects.
- [ ] Never assert fixed `IOException` types/timings on Servlet client aborts.
- [ ] Implement idempotent cleanup for `SseEmitter`/`ResponseBodyEmitter`/`DeferredResult`.
- [ ] Use a bounded executor for MVC blocking streaming writes.
- [ ] Define clear `DataBuffer` owners; release on success/error/cancel without double-release.
- [ ] Never try sending 500/`ProblemDetail` after HTTP headers have committed.
- [ ] Treat client, server, Publisher, and test timeouts as distinct boundaries.
- [ ] Test concurrent slow clients, queue/backpressure behavior, and memory/disk limits.
- [ ] Implement idempotency/reconciliation for side effects committed before response loss.
- [ ] Test resource cleanup across JVM crashes via orphan sweepers/recovery.
- [ ] Test staging through gateways/HTTP2/ingress when production includes those layers.
- [ ] Metrics/logs/traces distinguish complete/error/cancel and redact PII/secrets.

## 24. Self-Check Questions

**1. When testing `Callable<String>` with MockMvc, why not assert the body on the first `GET` perform?**  
Because MVC switches to Servlet async; the controller returned the `Callable`, yet the final response has not dispatched yet. Verify `asyncStarted`/`asyncResult`, then run `asyncDispatch`.

**2. Is an `@Async void` service running after the controller returns HTTP 202 an in-flight HTTP request?**  
No. The HTTP response already finished and the job is detached; durability requires DB/queues/leases/retries rather than relying solely on graceful shutdown.

**3. Can `WebTestClient.bindToController(...)` test broken pipes when a browser closes a tab?**  
No. It uses a mock server; open an embedded server on a random port and have a real client close/cancel the response stream.

**4. Why not call `collectList()` on an infinite `Flux.interval` SSE stream?**  
Because the `Flux` never completes; collecting may never return and grows memory. Use `FluxExchangeResult` and `StepVerifier.thenCancel`.

**5. Does `StepVerifier.thenCancel()` on a standalone `Flux` prove the TCP socket closed?**  
No. It only cancels the subscription inside the test JVM. Only when the `Flux` backs an HTTP client connected to a real server with server-side evidence is it an end-to-end test.

**6. Can a server still send a few chunks after the client aborts?**  
Yes. Kernel/proxy buffering and asynchronous disconnect detection cause delays; avoid asserting instantaneous stops.

**7. After flushing 200 SSE, if the source throws an exception, does status change to HTTP 500?**  
Do not expect it. The response is likely already committed; clients see the prefix followed by EOF/error, and tests must reflect that reality.

**8. Why does `StepVerifier.withVirtualTime` need a `Supplier` constructing the `Flux` inside the lambda?**  
So timed operators are constructed after the virtual scheduler is installed. If created beforehand, they may bind to the real scheduler.

**9. What does `Flux.usingWhen` help verify on cancellation?**  
It provides dedicated async cleanup callbacks for normal/error/cancel paths. Tests can cancel the stream and assert resources clean up accurately.

**10. If a client aborts after the server commits to the DB, does cancellation roll back the commit?**  
No. Idempotency, proper transaction boundaries, and reconciliation are required.

**11. In an MVC stream test, does `finished==1` after client close prove the server saw exactly one `IOException`?**  
Not yet. It proves the callback is no longer active within the timeout; a finite stream may complete normally before detecting the abort.

**12. Does a `StepVerifier` test with a 5s deadline make the HTTP server time out after 5s?**  
No. That is purely the test verification deadline. Server/codec/client timeouts are configured separately.

## 25. Official References

1. Spring Framework — **MockMvc Async Requests**, `request().asyncStarted`, `asyncResult`, and `asyncDispatch`: https://docs.spring.io/spring-framework/reference/testing/mockmvc/hamcrest/async-requests.html
2. Spring Framework — **MVC Asynchronous Requests**, `Callable`, `DeferredResult`, `StreamingResponseBody`, `SseEmitter`, and notes on `IOException` after client disconnect: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html
3. Spring Boot 3.3 — **Testing Spring Boot Applications**, `MOCK` vs `RANDOM_PORT` and `WebTestClient`/`MockMvc`: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
4. Spring Framework — **WebTestClient Streaming Responses**, `FluxExchangeResult` + `StepVerifier` + `thenCancel`: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html
5. Spring Framework — **WebFlux @ResponseBody**, reactive streams and codecs: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/responsebody.html
6. Spring Framework — **Data Buffers and Codecs**, pooled memory, ownership, `DataBufferUtils.release`, `doOnDiscard`: https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html
7. Spring Framework — **WebFlux Reactive Core** and testing non-blocking runtimes: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
8. Project Reactor — **Testing with StepVerifier / Virtual Time**: https://projectreactor.io/docs/core/release/reference/testing.html
9. Project Reactor — **Using Resources and the Finally Block**, `doFinally`, `usingWhen`: https://projectreactor.io/docs/core/release/coreFeatures/error-handling.html
10. Spring Boot 3.3 — **Graceful Shutdown** and in-flight requests when closing the context: https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html

**Conclusion:** Testing async, streaming, and client disconnects requires traversing the right **lifecycle** and **observation layer**. For MVC, use `asyncDispatch` to verify HTTP results after `Callable`/`DeferredResult`; for streaming/network behavior, use a `RANDOM_PORT` server and a real client that reads an event before closing/canceling the stream; for WebFlux, use `FluxExchangeResult` and `StepVerifier` to verify events and completion/cancellation alongside server probes confirming transport cancel. Cleanup on complete/error/cancel must be tested explicitly with bounded deadlines and idempotency for already-committed side effects.