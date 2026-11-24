# Streaming or SSE and When Real-Server HTTP Is Needed

## 1. Why Streaming Tests Must Pay Attention to the HTTP Boundary

In Spring MVC, many endpoints return a complete response: the controller constructs a DTO, Spring serializes it to JSON, writes the response body, and finishes the request. Streaming works differently. The server can write data incrementally while the request remains open.

Two common response types are:

- **StreamingResponseBody:** the application writes bytes directly to the response's output stream. Suitable for large files, exports, incrementally generated content, or data that does not need to be wrapped as discrete events.
- **SseEmitter:** the application sends a sequence of Server-Sent Events (SSE) to the client over a long-lived HTTP connection. Suitable for unidirectional notifications from the server to a browser or client.

Both can be tested with `MockMvc` at the Spring MVC level. However, `MockMvc` uses mock servlet requests/responses and runs inside the same test process. It does not open a real HTTP socket. Therefore, `MockMvc` can verify controller logic, the async lifecycle, and the final content, but it cannot prove that data was transmitted in multiple client-observable writes over the network.

Choose the right test level based on what you need to verify:

- If you need to verify status, headers, content type, final content, and how the controller initiates async, `MockMvc` is usually sufficient.
- If you need to verify that clients receive events while the stream is still open, flush timing, client disconnects, buffering, timeouts, or servlet container behavior, you must send HTTP requests to a real server.

## 2. Distinguishing Streaming Body and Server-Sent Events

### StreamingResponseBody

The controller returns a callback that writes data to an `OutputStream`:

~~~java
import java.nio.charset.StandardCharsets;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;

@RestController
public class ReportController {

    @GetMapping(
            value = "/reports/export",
            produces = MediaType.TEXT_PLAIN_VALUE
    )
    public StreamingResponseBody export() {
        return outputStream -> {
            outputStream.write("report header\n"
                    .getBytes(StandardCharsets.UTF_8));
            outputStream.flush();

            outputStream.write("row 1\n"
                    .getBytes(StandardCharsets.UTF_8));
            outputStream.flush();

            outputStream.write("row 2\n"
                    .getBytes(StandardCharsets.UTF_8));
        };
    }
}
~~~

Spring MVC runs the stream writing asynchronously. The controller returns before the callback finishes; the callback writes data during the async processing phase. You can call **flush()** to request pushing written data down to the response stream. Exactly when the client receives each chunk also depends on the servlet container, network, and any proxies or gateways.

**StreamingResponseBody** works well when the application wants control over how bytes are written. If content can be large, write incrementally and avoid assembling the entire payload in a **byte[]** or **String** before returning.

### SseEmitter

SSE is a text-based event format running over HTTP. Responses typically use the **text/event-stream** media type. Each event consists of optional lines such as **id**, **event**, **retry**, one or more **data** lines, and a blank line terminating the event.

Example event on the wire:

~~~text
id:42
event:notification
data:An order has been paid

~~~

Browsers can consume events via the **EventSource** API. The connection typically stays open so the server can continue sending new events.

A controller can return an **SseEmitter**:

~~~java
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

@RestController
public class NotificationController {

    private final NotificationService notificationService;

    public NotificationController(NotificationService notificationService) {
        this.notificationService = notificationService;
    }

    @GetMapping(
            value = "/notifications",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE
    )
    public SseEmitter notifications() {
        return notificationService.subscribe();
    }
}
~~~

An event producer can send data like this:

~~~java
emitter.send(SseEmitter.event()
        .id("42")
        .name("notification")
        .data("An order has been paid"));
~~~

When no more events remain and you want to close the stream, call **complete()**. If an error occurs, you can call **completeWithError(exception)**. **SseEmitter** also supports **onCompletion**, **onTimeout**, and **onError** callbacks; applications typically use them to cancel subscriptions, release resources, or log connection lifecycle events.

Do not confuse SSE with WebSocket. SSE is a unidirectional stream from server to client over HTTP; clients send data back via separate HTTP requests. WebSocket provides a bidirectional connection with its own protocol after an HTTP upgrade.

## 3. What Can MockMvc Verify?

`MockMvc` invokes Spring MVC through components such as handler mappings, controllers, argument resolvers, return value handlers, message converters, and exception resolvers. It supports async requests, so it can verify:

- Whether the request started async processing.
- Whether the async result completed.
- Whether the post-async-dispatch result has the right status and headers.
- Whether the final body has the expected data and format.
- How exceptions are handled while MVC can still produce an error response.
- For SSE completed within a test, whether the final event lines match expected content.

The limitation is that `MockMvc` creates no real TCP connection, does not simulate a client reading bytes incrementally while the server keeps writing, and cannot verify whether the servlet container or a proxy flushes data out immediately after every flush call.

### MockMvc Async Testing Flow

For an async endpoint, the first request may return before the final result is ready. Tests must verify async started, capture **MvcResult**, and then call **asyncDispatch** to assert the response after async processing finishes.

~~~text
mockMvc.perform(request)
        |
        v
request().asyncStarted()
        |
        v
MvcResult (pending request)
        |
        | callback / async task completes
        v
mockMvc.perform(asyncDispatch(result))
        |
        v
Assert final status, headers, and body
~~~

If **asyncDispatch** is skipped, the test may only see the initial state of the request and fail to inspect the response after async completion.

## 4. Testing StreamingResponseBody with MockMvc

Example test verifying the final content of a streaming response:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ReportController.class)
class ReportControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void shouldReturnTheCompletedStreamingBody() throws Exception {
        MvcResult pending = mockMvc.perform(get("/reports/export"))
                .andExpect(request().asyncStarted())
                .andReturn();

        mockMvc.perform(asyncDispatch(pending))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.TEXT_PLAIN))
                .andExpect(content().string(containsString("report header")))
                .andExpect(content().string(containsString("row 1")))
                .andExpect(content().string(containsString("row 2")));
    }
}
~~~

This test verifies that the controller started async processing and the final response contains the expected data parts. It does not prove the client received **report header** before **row 1**, nor does it prove each **flush()** call produced a separate network transmission.

If the async task depends on a service, you can mock the service or use deterministic data so test outcomes are repeatable. If the task can run slowly, configure an appropriate async request timeout in the test so failures give clear feedback instead of hanging indefinitely.

Do not infer streaming behavior from a single assertion over the full response body. A mock response can buffer every written byte before letting the test read it. Having the right final body does not mean bytes were delivered with the right timing.

## 5. Testing SSE with MockMvc

A `MockMvc` test can verify that a controller returns an async response, the SSE content type, and events sent before the emitter completes.

Example service returning an emitter:

~~~java
public interface NotificationService {
    SseEmitter subscribe();
}
~~~

The test creates a controllable emitter, stubs the controller to return it, then sends events and closes the stream:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import static org.hamcrest.Matchers.containsString;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(NotificationController.class)
class NotificationControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private NotificationService notificationService;

    @Test
    void shouldSerializeAnSseEvent() throws Exception {
        SseEmitter emitter = new SseEmitter(10_000L);
        when(notificationService.subscribe()).thenReturn(emitter);

        MvcResult pending = mockMvc.perform(get("/notifications")
                        .accept(MediaType.TEXT_EVENT_STREAM))
                .andExpect(request().asyncStarted())
                .andReturn();

        emitter.send(SseEmitter.event()
                .id("42")
                .name("notification")
                .data("ready"));

        emitter.complete();

        mockMvc.perform(asyncDispatch(pending))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.TEXT_EVENT_STREAM))
                .andExpect(content().string(containsString("id:42")))
                .andExpect(content().string(containsString("event:notification")))
                .andExpect(content().string(containsString("data:ready")));
    }
}
~~~

The sequence of operations matters:

1. `MockMvc` executes the request and Spring registers the emitter with the async request.
2. The test sends an event after the request has started.
3. The test calls **complete()** to close the stream.
4. The test uses **asyncDispatch** to verify the completed response.

If the emitter is never completed or timed out, async dispatch may have to wait until timeout. For a long-lived SSE connection in production, keeping the connection open is the intended behavior; in a `MockMvc` test asserting the final body, explicitly control when events are sent and when the emitter completes.

The test above verifies the event formatting written to the mock response. It does not verify that a browser receives events while the connection remains open, nor that events arrive at the expected cadence.

## 6. When Is MockMvc Enough?

Use `MockMvc` when the goal focuses on Spring MVC logic and final response content:

| Goal | Is MockMvc appropriate? |
|---|---|
| Testing an endpoint returning **StreamingResponseBody** | Yes |
| Verifying the request starts async | Yes |
| Asserting content after async completes | Yes |
| Verifying SSE has the right **id**, **event**, **data** after completion | Yes |
| Asserting status, headers, and content type | Yes |
| Testing exceptions raised before the response is committed | Yes |
| Proving the first event reaches the client before the stream ends | No |
| Measuring latency between events or heartbeats | No |
| Proving **flush()** becomes immediately readable bytes over a socket | No |
| Testing client disconnects and server-side disconnect detection | No |
| Testing buffering by servlet containers, reverse proxies, or gateways | No |
| Testing real behavior under load and many concurrent connections | No |

`MockMvc` remains a solid choice for most controller and MVC testing. When a requirement depends on timing, connections, or transport, add an integration test over real HTTP.

## 7. Testing Over HTTP Against a Real Server

With Spring Boot, **@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)** starts the application context with an embedded servlet container. The test sends requests to an actual randomly assigned port.

For SSE, you can use Java's **HttpClient** to read the response body line by line. The example below assumes the endpoint emits a **ready** event right after a client connects; a test fixture or publisher must ensure that event is emitted.

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.stream.Stream;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class NotificationHttpIntegrationTest {

    @LocalServerPort
    private int port;

    @Test
    void shouldDeliverAnSseEventOverRealHttp() throws Exception {
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("http://localhost:" + port + "/notifications"))
                .header("Accept", "text/event-stream")
                .GET()
                .build();

        HttpResponse<Stream<String>> response = HttpClient.newHttpClient()
                .send(request, HttpResponse.BodyHandlers.ofLines());

        assertEquals(200, response.statusCode());

        String contentType = response.headers()
                .firstValue("Content-Type")
                .orElse("");

        assertTrue(contentType.startsWith("text/event-stream"));

        try (Stream<String> lines = response.body()) {
            String dataLine = lines
                    .filter(line -> line.startsWith("data:"))
                    .findFirst()
                    .orElseThrow();

            assertEquals("data:ready", dataLine);
        }
    }
}
~~~

**BodyHandlers.ofLines()** lets the test read lines from the response body as they arrive. **findFirst()** blocks until a matching line arrives or the stream ends. Consequently, the endpoint must emit an event within the test's allowed window. Closing the stream body closes the client's response reader and can terminate the connection.

To verify that data arrives before the server closes the stream, design a controlled test: the server emits the first event and keeps the connection open; the client reads that event and then signals the server to emit the next event or complete. A **CountDownLatch**, test publisher, or test-only control endpoint can synchronize both sides. Do not use **Thread.sleep()** to guess when an event will arrive, as that makes CI builds flaky.

For **StreamingResponseBody**, you can similarly use **HttpClient** with **BodyHandlers.ofInputStream()** or **BodyHandlers.ofLines()** to read early chunks while the server is still writing later ones. This tests behavior `MockMvc` cannot verify: that clients actually observe data over a live HTTP connection.

## 8. Behaviors That Can Only Be Reliably Verified via a Real Server

### Flush Timing and Buffering

Calling **flush()** requests pushing written data down the output stream. However, bytes can still be held in the servlet container, TLS layer, proxy, load balancer, or client buffers. A `MockMvc` test only reads the final mock response and cannot verify which layer buffers data.

If a product requires near-real-time dashboard updates or periodic SSE heartbeats, test over a real HTTP path. If production traffic goes through a reverse proxy, also test through the proxy path, because hitting the embedded server directly cannot catch proxy response buffering.

### Client Disconnects and Cleanup

In production, browsers can close tabs, lose network connectivity, or actively cancel requests. With **SseEmitter**, applications should handle **onCompletion**, **onTimeout**, and **onError** to cancel subscriptions or release resources.

`MockMvc` can exercise callback branches or unit-test cleanup logic if the test controls the emitter. However, it does not accurately simulate a socket closing mid-write. To verify that the server detects a disconnect and halts background work, use a real HTTP client to open and close the response stream while observing cleanup state on the server.

Disconnect detection may happen on the next write or flush attempt. Do not assume the server always learns immediately when a client closes a connection.

### Timeouts and Long-Lived Connections

An SSE connection can stay open for minutes. You must verify emitter timeouts, async request timeouts, proxy idle timeouts, and heartbeat mechanisms. `MockMvc` is helpful for testing application-driven timeout branches, but does not represent the timeout policy of the entire infrastructure.

### Multiple Clients and Resource Usage

Each streaming connection can hold application resources. You must test concurrent connection counts, thread/task executors, event queues, memory limits, and how the application handles slow-reading clients. Load tests or multi-client tests over real HTTP are far more suitable than `MockMvc`.

### Protocol and Deployment Infrastructure

If you need to verify TLS, cookies, authentication filters, compression, HTTP/1.1, HTTP/2, or reverse proxies, test against a server and network path matching the configuration under test. An embedded server on localhost does not automatically validate every deployment environment difference.

Never assert exact HTTP chunk sizes as if they were SSE event boundaries. Chunked transfer encoding is HTTP/1.1 framing; HTTP/2 uses different framing. One event may arrive split across multiple client reads, or multiple events may appear in a single read. Verify event boundaries according to SSE format rather than transport chunk boundaries.

## 9. Error Handling in Streaming Responses

MVC errors occurring before the response is committed can usually pass through **HandlerExceptionResolver** or **@ControllerAdvice**. In that case, `MockMvc` can verify status and error bodies just like ordinary endpoints.

Streaming introduces a critical boundary: once the server has sent headers or part of the body, the response may already be committed. At that point, the server generally cannot change the status to 500 and replace the entire body with a JSON error response like a request that has not written data yet.

With **StreamingResponseBody**, if the callback fails after writing partial content, the client may receive an incomplete body or an abruptly closed connection. `MockMvc` tests can verify certain exception cases during async processing, but cannot prove how many bytes a client received before the connection closed.

With SSE, a business error after the connection opens can be represented as an event named **error** if your application protocol defines one. **completeWithError** terminates the emitter with an error; it does not guarantee converting an already-started stream into a fresh JSON error response. Clients need clear rules for handling error events and reconnecting.

Test these scenarios separately:

- Errors before the response starts: assert status and error representation.
- Errors while producing the stream: assert error callbacks, cleanup, and how clients detect an interrupted stream.
- Client disconnects: assert background tasks or subscriptions are cancelled.
- Timeouts: assert connections are closed and resources are released.

`MockMvc` fits logic branches controllable within tests. Scenarios depending on committed connections and live clients require HTTP integration tests.

## 10. Organizing the Test Suite

A streaming/SSE test suite typically spans multiple levels:

| Test level | Tools | Goal |
|---|---|---|
| Unit test | JUnit and Mockito | Verify chunk/event creation logic, error handling, and cleanup |
| MVC test | `MockMvc` | Verify mappings, async start, status, headers, and final body |
| HTTP integration test | **@SpringBootTest(RANDOM_PORT)** + **HttpClient** | Verify bytes/events delivered through a real embedded server |
| Deployment test | HTTP client via proxy or staging environment | Verify TLS, proxy buffering, timeouts, and deployment settings |
| Load test | Multi-client HTTP driver tools | Verify concurrency, throughput, and resource consumption |

There is no need to turn every controller test into an HTTP integration test. Keep most logic and response-contract assertions in `MockMvc` so tests run fast and failures are easy to diagnose. Add real-server tests where requirements specifically depend on connections, timing, or container behavior.

When testing SSE, make the contract explicit: event names, event IDs, data schema, heartbeats, reconnect policy, and disconnect behavior. When testing streaming bodies, define content, encoding, ordering, when data must become available, and how errors are signaled if the stream aborts.

A `MockMvc` test verifies that the final response is right. A real HTTP test verifies that clients can actually receive data over an open connection as the system requires.

