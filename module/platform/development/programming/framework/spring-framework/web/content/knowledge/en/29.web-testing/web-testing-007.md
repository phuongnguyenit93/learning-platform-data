# Testing MVC Async, asyncDispatch, and Streaming Responses in Spring MVC

## 1. Problem statement and mental model

A Spring MVC controller method does not have to return data immediately on the Servlet thread that accepted the request. It can return asynchronous work, after which Spring MVC releases the receiving thread, waits for the result, and performs an **ASYNC dispatch** to complete the HTTP response. For continuous or large payloads, a controller can also return a **streaming response** using `ResponseBodyEmitter`, `SseEmitter`, or `StreamingResponseBody`.

A solid test must verify the **entire lifecycle**, rather than merely seeing status 200 on the first MockMvc call. Two common mistakes are inspecting the body before the async result is ready and treating MockMvc as a real HTTP server capable of timing when each chunk reaches the client.

Diagram:

```text
Test using MockMvc                         Spring MVC (Servlet stack)
        |                                            |
        | perform(GET /async)                        |
        |------------------------------------------->|
        |                                  DispatcherServlet invokes controller
        |                                             |
        |                                controller returns Callable /
        |                                DeferredResult / Mono ...
        |                                             |
        |                                  request.startAsync()
        |<-------- request().asyncStarted() ----------|
        |                                             |
        |                  Async source computes result
        |                                             |
        |  request().asyncResult(...) / getAsyncResult |
        |                   waits for result           |
        |                                             |
        | perform(asyncDispatch(mvcResult)) ---------->|
        |                                  DispatcherServlet re-processes
        |                                  result, errors, converters
        |<------------- HTTP status/headers/body -----|
        |                                             |
        v                                             v
 Test checks final response               For streams: multiple writes/flushes
```

Key concepts in this lesson:

- `MockMvc` simulates the Servlet API and `DispatcherServlet` to test Spring MVC without opening an HTTP socket.
- `MvcResult` holds the simulated request/response and async processing state of one `perform` invocation.
- `request().asyncStarted()` verifies the controller initiated async handling.
- `request().asyncResult(...)` checks the completed async value (can wait for the result).
- `asyncDispatch(mvcResult)` creates the follow-up pass with dispatcher type `ASYNC` so Spring MVC completes processing the result.
- `StreamingResponseBody` writes bytes directly to `OutputStream`; `ResponseBodyEmitter` and `SseEmitter` emit multiple parts via message converters and SSE formatting.

**Scope:** Spring MVC on the **Servlet stack**, not WebFlux with `WebTestClient.bindToController`. Java 17+ and Spring Framework 6.x/Spring Boot 3.x form the basis of the examples; core MockMvc APIs are maintained in subsequent Spring releases.

## 2. How does MVC async differ from synchronous requests and WebFlux?

In synchronous handling, the controller returns the result immediately and `DispatcherServlet` finishes the response during the initial dispatch. In async handling:

1. The controller returns an MVC-supported type such as `Callable<T>`, `DeferredResult<T>`, `WebAsyncTask<T>`, or a single-value reactive type (`Mono<T>` when an adapter is present).
2. Spring calls `startAsync()` on the Servlet request. The initial Servlet thread exits to serve other work while the response remains open.
3. An external thread/callback produces the result, or an error/timeout occurs.
4. Spring performs an **ASYNC dispatch** through the Servlet container to process the value as an MVC return value, applying `HttpMessageConverter`, exception resolvers, and finishing the response.

| Controller return type | Who produces the result? | What matters when testing |
| --- | --- | --- |
| `Callable<T>` | Spring MVC's task executor runs the callback on another thread | Verify async started, wait for result, dispatch, and check response |
| `DeferredResult<T>` | Application explicitly calls `setResult` / `setErrorResult` from another callback/thread | Tests can complete it explicitly, avoiding time dependence |
| `WebAsyncTask<T>` | Callable combined with timeout/executor/interceptor config | Test both result and timeout branches in a suitable environment |
| `Mono<T>` | Reactive publisher adapted by MVC into async mechanism | Test result after subscription and final dispatch |
| `ResponseBodyEmitter` | Application calls `send` multiple times, ending with `complete` | Verify finite response, body parts, and completion behavior |
| `SseEmitter` | Application emits SSE events via `send(SseEventBuilder)` | Verify SSE structure and completion with a finite emitter |
| `StreamingResponseBody` | Callback writes bytes directly to `OutputStream` on an executor | Wait for writing task to finish and inspect final bytes/headers |

**Async does not mean non-blocking I/O.** Spring MVC is Servlet-based: when streaming to the response, write operations remain blocking I/O executed on executor-managed threads. WebFlux uses a different I/O model. Therefore configuring `AsyncTaskExecutor`, timeouts, and resource limits in Spring MVC remains essential.

## 3. Standard MockMvc workflow: perform → async result → asyncDispatch

Spring MVC Test documentation uses this pattern:

```java
MvcResult started = mockMvc.perform(get("/async"))
        .andExpect(request().asyncStarted())
        .andExpect(request().asyncResult("done"))
        .andReturn();

mockMvc.perform(asyncDispatch(started))
        .andExpect(status().isOk())
        .andExpect(content().string("done"));
```

This snippet belongs inside a `@Test` method that already has `MockMvc` and static imports for `get`, `asyncDispatch`, `request`, `status`, and `content`. Without a matching controller yet, it illustrates the test flow.

Explanation:

1. `perform(get(...))` simulates the initial HTTP dispatch.
2. `request().asyncStarted()` proves the controller entered Servlet async mode. If the controller returns synchronously, this assertion must fail—that indicates a mismatched test design, not a MockMvc bug.
3. `request().asyncResult(...)` waits for and matches the asynchronous value emitted by the controller. This is the **intermediate computation result**, not necessarily the serialized HTTP body.
4. `asyncDispatch(started)` triggers the second dispatch so MVC converts the result into a body, finalizes status/headers, and runs exception handling.
5. `content().string(...)` and `status()` in the final step verify the HTTP contract.

Never issue a second `mockMvc.perform(get(...))` to “wait for async”: that is a **new HTTP request** and may execute business logic a second time. Always keep the exact `MvcResult` from the first call and pass it to `asyncDispatch`.

### 3.1 Why can checking status immediately be misleading?

In many cases the initial mock response defaults to status 200 even though the async operation has not completed and may fail later. Calling `andExpect(status().isOk())` on the first dispatch only observes the initial state, not proof that 200 is ultimately returned. Assert status and body after async dispatch, especially when converting an exception into 4xx/5xx via `@ExceptionHandler`.

### 3.2 When to use MvcResult.getAsyncResult(timeout)?

`MvcResult.getAsyncResult(long timeToWait)` waits up to a test-chosen number of milliseconds for the async result, preventing tests from hanging indefinitely when a task never completes. Example:

```java
MvcResult started = mockMvc.perform(get("/async"))
        .andExpect(request().asyncStarted())
        .andReturn();

Object asyncValue = started.getAsyncResult(2_000);
assertEquals("done", asyncValue);

mockMvc.perform(asyncDispatch(started))
        .andExpect(status().isOk())
        .andExpect(content().string("done"));
```

`assertEquals` comes from JUnit Jupiter. The 2-second mark here is the **test's maximum wait time**, distinct from the Servlet request timeout configured by the server/MVC. If a test times out, inspect the workflow, executor, and data before simply increasing the timeout.

### 3.3 What does asyncDispatch actually do?

Spring MVC Test has no Servlet container to re-dispatch HTTP over a network. `MockMvcRequestBuilders.asyncDispatch(mvcResult)` simulates the container invoking `DispatcherServlet` again in the ASYNC phase once the async result is available. Return value handlers, converters, and exception resolvers can then build the final response.

For an async handler returning a DTO object, `request().asyncResult(dto)` checks the DTO; the post-dispatch response may be JSON or a specific status. Do not compare `asyncResult` against serialized JSON when the controller's actual value is an object. For `DeferredResult<ResponseEntity<String>>`, the async value is a `ResponseEntity`, while the HTTP status/body comes from the dispatch step.

## 4. Setting up an appropriate test environment

### 4.1 Ways to create MockMvc

- `MockMvcBuilders.standaloneSetup(controller).build()`: fast, good for testing a single controller with minimal MVC config. If specific advice, converters, or interceptors are needed, register them explicitly. Does not load the full application context by default.
- `@WebMvcTest(MyController.class)` with `@Autowired MockMvc`: loads the MVC test slice; supply mocks/beans for needed services. Filters/Security in the slice may affect requests.
- `@SpringBootTest` + `@AutoConfigureMockMvc`: loads a broader application into MockMvc while still using mock Servlets. When real-time I/O streaming needs testing, run a real server with `webEnvironment = RANDOM_PORT`.

Baseline Spring Boot 3.x Gradle setup:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-test` provides JUnit Jupiter, Spring Test, AssertJ/Hamcrest, and common testing dependencies. Use Spring Boot's dependency management to keep versions aligned. If a real controller uses Reactor `Mono` or `Flux`, add the required Reactor libraries (typically via `spring-boot-starter-webflux` or related dependencies), without forcing every MVC async lesson to depend on Reactor.

### 4.2 Scope of guarantees diagram

```text
Direct unit test of Callable/service
     → verifies Java logic, does NOT verify Servlet async MVC

MockMvc (standalone / MVC slice / full application context)
     → checks request mapping, async started/result/dispatch,
       MVC converters, status/headers, final body

Real server + HTTP client
     → checks networking, chunk arrival, flush, open SSE,
       disconnects, proxies, buffering, connector timeouts
```

Do not use MockMvc alone to infer “the client received the chunk after 100 ms” or “the browser auto-reconnects SSE.” MockMvc buffers response bodies in memory and does not fully simulate sockets, proxies, or buffering.

## 5. Complete example: Callable, DeferredResult, and async errors

This section contains two files you can place into a Spring Boot 3.x/Java 17+ project. It creates a controller returning results via three paths: `Callable`, `DeferredResult`, and `setErrorResult`. With `DeferredResult`, the test completes the result itself, controlling timing precisely without `Thread.sleep`.

**File `src/main/java/com/example/demo/AsyncDemoController.java`:**

```java
package com.example.demo;

import java.util.concurrent.Callable;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.request.async.DeferredResult;

@RestController
public class AsyncDemoController {
    private final AtomicReference<DeferredResult<String>> pending =
            new AtomicReference<>();

    @GetMapping("/async/callable")
    public Callable<String> callable() {
        return () -> "callable-ready";
    }

    @GetMapping("/async/deferred")
    public DeferredResult<String> deferred() {
        DeferredResult<String> result = new DeferredResult<>(5_000L);
        pending.set(result);
        return result;
    }

    public DeferredResult<String> pending() {
        return pending.get();
    }

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<String> handle(IllegalArgumentException error) {
        return ResponseEntity.status(HttpStatus.BAD_REQUEST)
                .body("bad-request");
    }
}
```

**Architectural note:** the `pending` field only serves as a control handle in this learning/test example and supports exactly **one waiting request**. Never use a global `AtomicReference` as a production design for concurrent requests. Real applications need ID-keyed promise registries, lifecycle-managing services, limits on pending requests, and cleanup on completion/timeout/cancellation.

**File `src/test/java/com/example/demo/AsyncDemoControllerTest.java`:**

```java
package com.example.demo;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.web.context.request.async.DeferredResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.setup.MockMvcBuilders.standaloneSetup;

class AsyncDemoControllerTest {
    private AsyncDemoController controller;
    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        controller = new AsyncDemoController();
        mockMvc = standaloneSetup(controller).build();
    }

    @Test
    void callableMustBeDispatchedToProduceHttpBody() throws Exception {
        MvcResult started = mockMvc.perform(get("/async/callable"))
                .andExpect(request().asyncStarted())
                .andReturn();

        assertEquals("callable-ready", started.getAsyncResult(2_000));

        mockMvc.perform(asyncDispatch(started))
                .andExpect(status().isOk())
                .andExpect(content().string("callable-ready"));
    }

    @Test
    void deferredResultCompletesOnlyWhenApplicationSetsIt()
            throws Exception {
        MvcResult started = mockMvc.perform(get("/async/deferred"))
                .andExpect(request().asyncStarted())
                .andReturn();

        DeferredResult<String> pending = controller.pending();
        assertNotNull(pending);
        pending.setResult("deferred-ready");

        assertEquals("deferred-ready", started.getAsyncResult(2_000));

        mockMvc.perform(asyncDispatch(started))
                .andExpect(status().isOk())
                .andExpect(content().string("deferred-ready"));
    }

    @Test
    void errorResultUsesMvcExceptionHandlingAfterDispatch()
            throws Exception {
        MvcResult started = mockMvc.perform(get("/async/deferred"))
                .andExpect(request().asyncStarted())
                .andReturn();

        controller.pending().setErrorResult(
                new IllegalArgumentException("invalid"));
        started.getAsyncResult(2_000);

        mockMvc.perform(asyncDispatch(started))
                .andExpect(status().isBadRequest())
                .andExpect(content().string("bad-request"));
    }
}
```

Run in a Gradle project directory containing `gradlew` and the dependencies above:

```bash
./gradlew test --tests '*AsyncDemoControllerTest'
```

Windows PowerShell can use:

```powershell
.\gradlew.bat test --tests '*AsyncDemoControllerTest'
```

All three tests assert on the async lifecycle and response; when passing, JUnit records **3 passing tests** in the test report. No application stdout is guaranteed because the controller/tests do not call `System.out.println` (Spring/Gradle logs depend on configuration).

**Key point:** `DeferredResult.setErrorResult` passes through async MVC result handling; `@ExceptionHandler` produces HTTP 400 in the subsequent dispatch phase. Checking `status().isOk()` on the first dispatch would miss this error-handling path.

### 5.1 Limits of this example under concurrent requests

A real endpoint must not store every `DeferredResult` in one `AtomicReference`. With multiple HTTP requests, request B would overwrite request A's reference and leave A waiting forever. Use a concurrency-safe keyed registry (with cleanup), or an event bus/message listener tied to correlation IDs; test multiple concurrent requests to verify results are never delivered to the wrong session.

## 6. Testing streaming bodies: what differs from a single async result?

**Streaming** has two traits: output can comprise multiple parts written before all work finishes, and some streams (like SSE) are intentionally long-lived with no natural end. For finite streams, MockMvc can inspect the body once the writing task completes. For infinite streams, change your test strategy rather than waiting indefinitely for completion.

### 6.1 StreamingResponseBody writing bytes directly

`StreamingResponseBody` suits file downloads or large exports. Spring executes the `OutputStream`-writing callback under Servlet MVC async mechanics. The callback typically writes buffers and calls `flush()` to push data toward the response layer; sockets/proxies may still buffer in real environments.

**File `src/main/java/com/example/demo/StreamingDemoController.java`:**

```java
package com.example.demo;

import java.io.IOException;
import java.nio.charset.StandardCharsets;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;

@RestController
public class StreamingDemoController {

    @GetMapping("/stream/chunks")
    public ResponseEntity<StreamingResponseBody> chunks() {
        StreamingResponseBody stream = output -> {
            output.write("first\n".getBytes(StandardCharsets.UTF_8));
            output.flush();
            output.write("second\n".getBytes(StandardCharsets.UTF_8));
            output.flush();
        };
        return ResponseEntity.ok()
                .contentType(MediaType.TEXT_PLAIN)
                .body(stream);
    }

    private volatile SseEmitter currentEmitter;

    @GetMapping(path = "/stream/events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter events() {
        SseEmitter emitter = new SseEmitter(5_000L);
        currentEmitter = emitter;
        return emitter;
    }

    public SseEmitter currentEmitter() {
        return currentEmitter;
    }
}
```

In this example, `/stream/chunks` writes two parts and finishes. `/stream/events` returns an `SseEmitter` allowing the test to explicitly send events and complete; the volatile field is strictly a fixture for testing **one connection at a time**. Real apps need a registry/session manager, timeouts, and resource cleanup, never one shared field across multiple streaming clients.

### 6.2 Testing StreamingResponseBody with MockMvc

Why isn't `asyncDispatch` strictly required after the stream finishes writing? With `StreamingResponseBody`, content is written directly to the response output stream inside the callback; the test can wait for the async task to finish and read the written body. Spring's official samples also use `MvcResult::getAsyncResult` to wait for streaming work. For methods returning an object that MVC must serialize after async, `asyncDispatch` remains essential.

**Test snippet** inside a class with `MockMvc` configured for `StreamingDemoController`:

```java
@Test
void finiteByteStreamHasExpectedBody() throws Exception {
    MvcResult result = mockMvc.perform(get("/stream/chunks"))
            .andExpect(request().asyncStarted())
            .andReturn();

    result.getAsyncResult(2_000); // Wait for the byte-writing callback to finish.

    assertEquals("first\nsecond\n",
            result.getResponse().getContentAsString());
    assertEquals(200, result.getResponse().getStatus());
}
```

This snippet needs static imports `get`, `request`, and JUnit `assertEquals`. The assertions check the **final content** and mock HTTP status. Calling `flush()` twice in the controller **cannot be used to conclude** that external network clients see two separate packets/chunks, because MockMvc has no real TCP socket or proxy.

If the application needs to assert raw file bytes, use `getResponse().getContentAsByteArray()` and compare against expected byte arrays, especially for binary data without a reliable string representation.

### 6.3 When does asyncDispatch still matter for streaming?

For some async return-value branches, running `asyncDispatch` lets MVC execute completion handling or resolvers. By contrast, a `StreamingResponseBody` callback usually writes directly to the response; when testing output, waiting for `getAsyncResult(timeout)` and reading the mock response suffices. Neither mechanically demand `asyncDispatch` on every stream nor assume `asyncDispatch` creates extra data chunks.

When testing exception-mapping contracts, know whether the error occurs **before or after the response is committed**. Once bytes have been flushed over the network, the server may no longer be able to replace the status/body with a standard JSON error. For real streaming, test client disconnects, mid-stream IOExceptions, and cleanup against a real server.

## 7. SseEmitter and ResponseBodyEmitter: testing finite event streams

### 7.1 ResponseBodyEmitter and SseEmitter

`ResponseBodyEmitter` can emit multiple objects; each `send(...)` is converted by an appropriate `HttpMessageConverter` and written to the response. `SseEmitter` specializes in **Server-Sent Events**, generating fields such as `id:`, `event:`, and `data:` under the `text/event-stream` protocol.

```text
HTTP response status: 200
Content-Type: text/event-stream

id:evt-1
event:notice
data:ready

id:evt-2
event:notice
data:next

```

Blank lines separate events in SSE. Having the right final text in the body is **not enough** to prove the client actually received each event immediately when the server flushed. For events with multi-line data, check SSE syntax compliance and JSON serialization.

Important callbacks:

- `emitter.send(data)` or `emitter.send(SseEmitter.event().id(...).name(...).data(...))` sends a data chunk.
- `emitter.complete()` signals the server finished the stream cleanly; in production SSE this may only be called on client disconnect or a termination policy.
- `emitter.completeWithError(error)` terminates with an error if handling is still possible. If `send` throws `IOException` due to a peer disconnect, Spring documentation notes the container may initiate async error handling; the application should not blindly call `completeWithError` again in that situation.
- `onCompletion`, `onTimeout`, and `onError` remove the emitter from active connection lists.

### 7.2 Testing finite SSE, controlling send timing and completion

A clean unit-level testing technique lets the controller return the emitter, has the test send an event and call `complete`, and only then inspects the body. That avoids `Thread.sleep` and avoids waiting on an infinite stream:

**File `src/test/java/com/example/demo/StreamingDemoControllerTest.java`:**

```java
package com.example.demo;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import static org.hamcrest.Matchers.containsString;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.setup.MockMvcBuilders.standaloneSetup;

class StreamingDemoControllerTest {
    private StreamingDemoController controller;
    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        controller = new StreamingDemoController();
        mockMvc = standaloneSetup(controller).build();
    }

    @Test
    void bytesAreWrittenInOrder() throws Exception {
        MvcResult result = mockMvc.perform(get("/stream/chunks"))
                .andExpect(request().asyncStarted())
                .andReturn();

        result.getAsyncResult(2_000);

        assertEquals(200, result.getResponse().getStatus());
        assertEquals("first\nsecond\n",
                result.getResponse().getContentAsString());
    }

    @Test
    void completedSseContainsEventFields() throws Exception {
        MvcResult started = mockMvc.perform(get("/stream/events")
                        .accept(MediaType.TEXT_EVENT_STREAM))
                .andExpect(request().asyncStarted())
                .andReturn();

        SseEmitter emitter = controller.currentEmitter();
        assertNotNull(emitter);

        emitter.send(SseEmitter.event()
                .id("evt-1")
                .name("notice")
                .data("ready"));
        emitter.complete();
        started.getAsyncResult(2_000);

        mockMvc.perform(
                    org.springframework.test.web.servlet.request
                            .MockMvcRequestBuilders.asyncDispatch(started))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.TEXT_EVENT_STREAM))
                .andExpect(content().string(
                        containsString("id:evt-1\n")))
                .andExpect(content().string(
                        containsString("event:notice\n")))
                .andExpect(content().string(
                        containsString("data:ready\n\n")));
    }
}
```

Run:

```bash
./gradlew test --tests '*StreamingDemoControllerTest'
```

In finite stream tests, byte output is compared in order; for SSE, the test checks meaningful fields of the event. Never rely on internal scheduling with `Thread.sleep`, because schedulers behave differently between local machines and CI. Both tests create a fresh MockMvc before each case, reducing emitter state leaks across tests.

If responses are gzipped/serialized or use a specific charset, adjust matchers to verify semantics rather than asserting brittle string formats across converters/configurations. For SSE, the body ending events with `\n\n` is part of the format contract.

### 7.3 Testing ResponseBodyEmitter

`ResponseBodyEmitter` is not restricted to SSE formatting. Example controller returning an emitter and calling `send` multiple times before `complete`:

```java
@GetMapping("/stream/messages")
public ResponseBodyEmitter messages() {
    ResponseBodyEmitter emitter = new ResponseBodyEmitter(5_000L);
    // In production, a service/event callback holds the emitter to send data.
    return emitter;
}
```

This is only an illustrative method and will not emit data if run on its own. Tests must drive the emitter via a fixture similar to `SseEmitter` and pick explicit `MediaType`/converters. Never equate “2 send calls” with “2 TCP packets”; verifying chunk delivery timing requires an HTTP client connected to a real server.

## 8. Testing errors, timeouts, and client disconnects

### 8.1 Error branches before the response commits

With `DeferredResult`, calling `setErrorResult(exception)` can be handled by MVC exception resolvers on the dispatch pass. The test in section 5 clearly shows the final HTTP 400 response. With `Callable`, throw an exception inside the callable and handle it with `@ExceptionHandler`/`@ControllerAdvice`; inspect the result after `asyncDispatch`.

Cases to include:

| Scenario | What to check |
| --- | --- |
| Callable completes | `asyncStarted`, right async result, dispatch produces status/body |
| DeferredResult completes on signal | No body returned before `setResult`; right final dispatch |
| DeferredResult emits error | Error mapped via MVC exception handler to right status/body |
| `Mono` publisher completes/errors in MVC | Subscription happens, result/error forwarded by Spring |
| StreamingResponseBody writes successfully | Headers, byte output, and completion state |
| Emitter finishes after n events | Proper order/syntax, emitter cleanup, and completion |
| Async timeout | Timeout callback / response matching app policy |
| Client disconnects mid-stream | Callback/cleanup runs, logs I/O error, and stops source |

### 8.2 Two different kinds of timeout in MockMvc

**Application timeout:** For example, `new DeferredResult<>(5_000L)` sets the time limit for the async request. In a Servlet container, timeouts are handled by the container/MVC async lifecycle, potentially triggering `onTimeout`, interceptors, and exception resolvers.

**Test timeout:** `mvcResult.getAsyncResult(2_000)` is the limit on how long a test waits for a result. It **does not simulate a Servlet async timeout** and does not automatically invoke the application's `onTimeout`.

To test pure timeout callback logic, extract the callback logic into a directly testable service or build timeout-driving infrastructure in an integration test; never do `Thread.sleep(5_001)` expecting `MockMvc` to behave like a production container. Spring MVC supports configuring `AsyncSupportConfigurer`, `DeferredResultProcessingInterceptor`, `CallableProcessingInterceptor`, or timeout callbacks per scenario.

**Illustrative** timeout handling example for a DeferredResult:

```java
@GetMapping("/async/controlled")
public DeferredResult<String> controlled() {
    DeferredResult<String> result = new DeferredResult<>(3_000L);
    result.onTimeout(() -> result.setErrorResult(
            new IllegalStateException("async request timeout")));
    return result;
}
```

This snippet must live inside a controller; register an appropriate handler for `IllegalStateException` if a specific response is desired. It does not spawn work to produce a result and will time out in a real container if left uncompleted. A MockMvc test cannot verify real network timers from this snippet alone.

### 8.3 StreamingResponseBody and exceptions after data is sent

Suppose a stream writes headers and partial body, then hits `IOException`: the response may already be committed, so the status can no longer change to 500 or send a clean JSON error. The system must define how clients detect incomplete data (Content-Length, checksum, record framing, or trailer per contract), close the stream, and log the cause clearly.

An `SseEmitter.send` call can throw `IOException` when the client closes the connection. In a Servlet environment, Spring may receive an `AsyncListener` error and dispatch to handle the exception; do not catch errors and repeatedly call `completeWithError` without understanding the emitter lifecycle. Use `onCompletion`, `onTimeout`, and `onError` to remove the emitter from registries and stop related subscriptions/jobs.

### 8.4 Security context and filters on ASYNC dispatch

If using Spring Security, Servlet filters, or tracing MDC, configure them to support `DispatcherType.ASYNC` per real requirements. If a filter runs only on `REQUEST`, security context/tracing/metrics in later dispatch phases may behave unexpectedly. Understand `OncePerRequestFilter.shouldNotFilterAsyncDispatch()` and filter registration settings; never assert only controller logic and claim full authorization works across async dispatches.

In standalone MockMvc, filters/security do not appear unless added explicitly; in Spring Boot test slices/full contexts, they may participate. Therefore every test should make clear which configuration is loaded.

## 9. When do you need a real server and WebTestClient?

Spring allows using `WebTestClient` with `MockMvcWebTestClient` to test most HTTP responses, including finite async ones. However, when backed by MockMvc, **an infinite stream cannot be actively cancelled by the client on the server** like a real network connection. Therefore:

- Use MockMvc for `DeferredResult`, `Callable`, finite streams, body formatting, and final statuses.
- Use an embedded server + `WebTestClient`/real HTTP client when observing multiple events over time, cancelling subscriptions, closing TCP connections, or handling infinite streams.
- To prove `flush()` pushes data on cadence, test end-to-end over the network. Proxies/gateways/browsers may buffer even after the app flushes.
- For long-lived SSE streams, tests usually do not wait for stream completion; the client subscribes, receives n expected events, and cancels. The server must clean up the corresponding emitter/subscription.

**Illustrative** integration test pattern using a WebTestClient bound to a real HTTP server:

```java
FluxExchangeResult<String> response = webTestClient.get()
        .uri("/stream/events")
        .accept(MediaType.TEXT_EVENT_STREAM)
        .exchange()
        .expectStatus().isOk()
        .returnResult(String.class);

// Test consumes a few events then cancels the subscription.
// Requires StepVerifier / Reactor and a real SSE-emitting server.
StepVerifier.create(response.getResponseBody())
        .expectNextCount(2)
        .thenCancel()
        .verify();
```

This snippet requires a running test server, `WebTestClient` configured with a real URL/port, a server emitting at least two codec-compatible elements, and the `reactor-test` dependency. It is not a standalone Java program. For SSE, `ServerSentEvent<T>` can be used to inspect typed `id`/`event`/`data` rather than forcing everything into `String`. Avoid tests that wait for n events when the server stops emitting; add timeouts in StepVerifier and prepare deterministic test data.

The gap between a **MockMvc mock HTTP response** and a **real HTTP response** is the boundary of evidence: a passing body assertion in MockMvc does not guarantee the client receives a chunk the moment the server calls `flush()`.

## 10. Executor configuration and test stability

Spring MVC uses `AsyncTaskExecutor` for `Callable` and blocking writes of certain streaming types. MVC's default executor in some setups is unsuitable for production under heavy load; configure explicit thread/queue bounds, sensible timeouts, and monitor queue pressure. Example:

```java
package com.example.demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.web.servlet.config.annotation.AsyncSupportConfigurer;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class MvcAsyncConfig implements WebMvcConfigurer {

    @Bean
    ThreadPoolTaskExecutor mvcAsyncExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(16);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("mvc-async-");
        return executor;
    }

    @Override
    public void configureAsyncSupport(AsyncSupportConfigurer configurer) {
        configurer.setDefaultTimeout(10_000L);
        configurer.setTaskExecutor(mvcAsyncExecutor());
    }
}
```

This is a sample configuration for environments with a Spring context; parameters 4/16/100/10 seconds are **illustrative values** to tune based on traffic, blocking behavior, and real resource limits. Spring manages the lifecycle of `ThreadPoolTaskExecutor` beans. If the context has multiple executors or needs to isolate download streams from short tasks, review configuration to avoid thread starvation during many long-lived streams.

In `standaloneSetup` tests, this configuration **does not apply automatically** because standalone only uses the controller and explicitly registered settings. To test the production executor, use WebApplicationContext/full integration tests or configure the matching MVC setup in MockMvc.

Never use `Thread.sleep` to “wait” for results: it is flake-prone when CI machines differ in CPU capacity. Prefer completion conditions: test-controlled `DeferredResult.setResult`, `getAsyncResult(timeout)`, `CountDownLatch`/`CompletableFuture` where needed, or virtual time for pure reactive streams (not to be confused with Servlet async timers).

## 11. Common testing mistakes and fixes

| Mistake | Why is it wrong? | How to fix |
| --- | --- | --- |
| Calling only `mockMvc.perform(get(...)).andExpect(status().isOk())` | Initial status may be default before the final response | Assert `asyncStarted`, wait for result, `asyncDispatch`, then check status/body |
| Re-calling `get(...)` instead of `asyncDispatch(result)` | Creates a new request and may run business logic twice | Keep `MvcResult` from the first dispatch |
| Checking JSON in `request().asyncResult(...)` when controller returns a DTO | Async result is the pre-conversion object | Check DTO in asyncResult, JSON after dispatch |
| Calling `asyncDispatch` before the async result is ready | Test race/timeout | Use `request().asyncResult` or `MvcResult.getAsyncResult(timeout)` |
| Treating `asyncStarted` as proof of business success | Async task can fail or time out afterward | Verify final result and error branches too |
| Using fixed `Thread.sleep` | Flaky on slower CI or varying scheduling | Complete `DeferredResult` explicitly; wait on explicit conditions |
| Using MockMvc to claim streaming flushes to browsers | MockMvc has no sockets/proxies/network | Integration test against a real server |
| Waiting for an infinite SSE stream to complete in MockMvc | No completion point, test may hang | Test a finite emitter or real stream with client cancellation |
| Treating `getAsyncResult(1000)` as a Servlet timeout test | Only limits how long the test waits | Build separate tests for container timeout/callbacks |
| Omitting HTTP message converters in standalone | Body/status differs from real app | Register converters/advice/filters or use WebMvcTest/context |
| Failing to remove emitter on timeout/client disconnect | Leaks connection lists and data sources | `onCompletion`/`onError`/`onTimeout` + idempotent cleanup |
| Using an unbounded executor or blocking event callbacks | High load causes thread exhaustion/latency spikes | Bounded ThreadPoolTaskExecutor, monitor queue/backpressure |
| Testing HTTP 200 after bytes are sent while assuming status can still change | Real response may already be committed | Design stream failure contracts and test over the network |
| Applying Servlet test techniques to WebFlux handlers | Different async/I/O pipeline | Use the test framework matching the stack |

## 12. Exercises and self-assessment questions

1. A controller returns `DeferredResult<String>` and has not called `setResult` yet. What does `MockMvc` return after `perform`? **A result indicating async has started; no final business result yet.**
2. Why is `asyncDispatch` needed? **So Spring MVC completes the dispatch phase once the async result arrives, applying converters and exception handling.**
3. When should `request().asyncResult(dto)` compare against a DTO instead of JSON? **When the async result is an object that MVC only serializes in the subsequent dispatch phase.**
4. With `StreamingResponseBody` writing two buffers, does a matching final body in MockMvc prove two chunks reached the client immediately? **No; MockMvc does not observe network timing.**
5. Why shouldn't an infinite `SseEmitter` be run to completion in a MockMvc test? **The stream never finishes, and MockMvc lacks a real client connection to cancel equivalently.**
6. When `DeferredResult.setErrorResult` is called, where should the response be checked? **After the async dispatch phase and exception handling.**
7. Does `getAsyncResult(2_000)` execute the server's timeout callback? **No; it only bounds how long the test waits for a result.**
8. What should be used to test a user disconnecting mid-stream? **A real test server and a client capable of closing/cancelling the network stream.**

Practice exercise: extend `AsyncDemoController` to return a DTO, add an `@ExceptionHandler` for a business error, and write two tests: verifying the DTO in `asyncResult` and JSON in the `asyncDispatch` phase. Next, write an SSE endpoint emitting two events then completing; verify the format with MockMvc. Finally, build a non-terminating SSE stream and test it with `WebTestClient` against a real server to confirm cancellation and emitter cleanup.

## 13. Official references

- [Spring Framework — MockMvc Async Requests](https://docs.spring.io/spring-framework/reference/testing/mockmvc/hamcrest/async-requests.html): how to use `asyncStarted`, `asyncResult`, and `asyncDispatch`.
- [Spring Framework — Asynchronous Requests, HTTP Streaming](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-async.html): `DeferredResult`, `Callable`, `SseEmitter`, `StreamingResponseBody`, executors, and timeouts.
- [Spring Framework — MockMvc Streaming Responses](https://docs.spring.io/spring-framework/reference/6.2/testing/mockmvc/hamcrest/vs-streaming-response.html): MockMvc limits for infinite streams.
- [Spring Framework — MockMvc Overview](https://docs.spring.io/spring-framework/reference/testing/mockmvc/overview.html): simulated Servlet environment and MockMvc verification scope.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): testing via HTTP client and server response assertions.
- [Spring Framework — MockMvcRequestBuilders.asyncDispatch Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/web/servlet/request/MockMvcRequestBuilders.html): building an ASYNC dispatcher request from `MvcResult`.
