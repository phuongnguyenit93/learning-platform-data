# Content-Length, Streaming, and When a Response Is Actually Complete

> **Scope:** HTTP in Spring Boot web-runtime applications. This lesson focuses on how the receiver determines response body boundaries, how the server emits data incrementally over time, and when a response is truly complete. Examples use Java 17+ and Spring MVC; WebFlux is covered in its own section.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain `Content-Length` in terms of **bytes transmitted**, distinguishing it from character count, processing time, and uncompressed payload size.
2. Distinguish known-length responses, streaming responses, HTTP/1.1 `Transfer-Encoding: chunked`, and HTTP/2 stream termination.
3. Identify four distinct milestones: handler return, headers committed, individual data flushes, and HTTP response completion.
4. Choose how to send responses in Spring MVC or WebFlux, inspect them with `curl`, and handle common issues such as disconnects, timeouts, or already-committed responses.

## 2. Why Does HTTP Need Message Boundaries?

A typical HTTP/1.1 response has a status line, headers, a blank line, and then the body (when a body is permitted):

```http
HTTP/1.1 200 OK
Content-Type: text/plain; charset=UTF-8
Content-Length: 5

Hello
```

In this example, `Content-Length: 5` means **5 octets (5 bytes)** of body content. The client reads exactly 5 bytes and knows the body has ended; the TCP connection can still be kept open and reused for another request. This value does **not** mean the server finished all business work, that the client application finished reading the data, or that all bytes had to be written in a single `write` call.

Distinguishing the concepts:

| Concept | Practical meaning |
|---|---|
| `Content-Length` | Content length in bytes, used to delimit message content when the corresponding framing rules apply. |
| `Content-Type` | Media type and, if present, charset; does not indicate length. |
| `Content-Encoding: gzip` | Content is encoded/compressed; transmitted length can differ from the original data. |
| `Transfer-Encoding: chunked` | The **HTTP/1.1** framing method that breaks a body into chunks with an end marker; not a JSON format or business structure. |
| Streaming | Strategy of generating/sending data incrementally instead of waiting to assemble the entire payload. Works with either known or unknown length. |
| Response complete | The server has finished generating/sending the response per protocol or completed response handling; not equivalent to every downstream layer having consumed the data. |

### Count Bytes, Not Characters

In Java, `String.length()` counts UTF-16 code units, whereas HTTP `Content-Length` requires the actual number of bytes transmitted. The following standalone example compiles with JDK 17:

```java
// File: ByteLengthDemo.java
import java.nio.charset.StandardCharsets;

public class ByteLengthDemo {
    public static void main(String[] args) {
        String text = "A😊";
        byte[] payload = text.getBytes(StandardCharsets.UTF_8);
        System.out.println(text.length());
        System.out.println(payload.length);
    }
}
```

Compile and run with `javac ByteLengthDemo.java` and `java ByteLengthDemo`; stdout is exactly:

```text
3
5
```

`A` takes 1 UTF-8 byte; the emoji takes 4 UTF-8 bytes yet 2 UTF-16 code units. If the actual payload is the `payload` array, the valid length is `5`, not `3`. For JSON, images, files, or UTF-8 text with accented characters, always measure **bytes after actual serialization and encoding**.

## 3. Three Mechanisms to Determine the End of a Response

### Case A — Known Length Upfront

When a response has a valid body, does not use `Transfer-Encoding`, and the server knows the exact byte count, it can send `Content-Length: N`. The client determines the end once it receives N bytes. Static files or pre-built `byte[]` arrays typically fit this case.

This **does not forbid streaming**: the server can still perform 100 socket writes as long as the total response bytes equal N. Conversely, having N bytes ready does not mean every byte reaches the client immediately; the OS, TLS, proxies, and the client can all buffer.

### Case B — Unknown Length: HTTP/1.1 Chunked

For an HTTP/1.1 response whose body length is unknown ahead of time, servers typically use `Transfer-Encoding: chunked`. Each chunk carries a hexadecimal size, the data, and CRLF; **a final zero-size chunk** marks the end of the body. Line-by-line illustration (actual wire lines end with CRLF):

```http
HTTP/1.1 200 OK
Transfer-Encoding: chunked
Content-Type: text/plain

5
Hello
6
 World
0

```

The concatenated content bytes are `Hello World` (11 bytes); `5`, `6`, `0`, and CRLF are framing, not application content. Servers may split chunks into different sizes depending on buffers and runtime, so **one `write` does not necessarily correspond to one HTTP chunk**. `curl` normally decodes chunked framing before displaying the body.

**Never set both `Content-Length` and `Transfer-Encoding` in the same message.** Under HTTP rules, a sender must not transmit both headers together. Inconsistent framing can cause truncated/extra reads and create vulnerabilities when proxies and servers interpret messages differently.

### Case C — HTTP/2, HTTP/3, and Stream Termination

HTTP/2 carries content in DATA frames, and the `END_STREAM` flag signals that the stream has ended (or HEADERS ends the stream when there is no body). **HTTP/2 does not use `Transfer-Encoding: chunked`**; connection-specific headers like `Transfer-Encoding` are forbidden. HTTP/3 likewise uses its own protocol framing instead of HTTP/1.1 chunked.

`Content-Length` **can still appear in HTTP/2** when the exact length is known. When present, the content byte count must match the actual DATA bytes per protocol rules. Not seeing `Transfer-Encoding: chunked` in HTTP/2 is normal and does not mean the response is not streaming.

In HTTP/1.0 or certain legacy compatibility scenarios, a response without a declared length may rely on **closing the connection** to mark the end. This makes normal completion hard to distinguish from mid-stream connection drops; prefer explicit boundary framing whenever possible.

### Responses Without a Body

Responses to `HEAD`, `1xx` statuses, `204 No Content`, and `304 Not Modified` **carry no response body** by HTTP semantics. `Content-Length` is prohibited in `1xx` or `204` responses; for `HEAD` and conditional `304`, if sent, it must reflect the length that would appear in the corresponding GET response, **not the number of body bytes sent** (which is 0). A `2xx` response to `CONNECT` transitions into a tunnel with different framing rules.

For a **request body** (such as a POST upload), `Content-Length` is likewise the byte count the server expects to read when no transfer coding is used. When the server finishes reading the request body and when the server completes the response are two independent milestones.

## 4. Streaming: "Sending Gradually" vs. "Sending Chunked"

Streaming means the application produces or forwards data piece by piece: large file downloads, progress logs, SSE, NDJSON, or results from an upstream system. The goal is usually to reduce memory needed to buffer the whole payload and reduce time to first byte.

| Scenario | Length known upfront? | Typical approach |
|---|---|---|
| Small pre-built `byte[]` | Yes | Return a normal response; can set `Content-Length` from `byte[].length`. |
| Large file with known, unchanging size during read | Yes | Stream file blocks; can keep an accurate `Content-Length`. |
| Incrementally generated results with unknown count | No | Streaming; HTTP/1.1 typically uses chunked; HTTP/2 uses DATA frames. |
| Progress SSE or continuous events | Usually no | `text/event-stream`, emit/flush events and complete when the source ends; infinite streams have no normal completion. |
| Regular `application/json` data | Depends | Framework may aggregate/buffer; do not assume items arrive immediately just because `Flux` is returned. Choose a streaming media type when continuous delivery is required. |

Three layers to distinguish: **(1)** the application calls `write` or emits an item, **(2)** the runtime flushes/pushes bytes to the protocol layer, and **(3)** the client actually observes and processes the data. Buffering in response wrappers, servlet containers, reverse proxies, HTTP/TLS, the kernel, and client libraries can stagger these layers in time. `flush()` requests pushing buffered data downward; it **does not prove the data reached the screen or was processed by the client**. Proxies such as Nginx may continue buffering even after the application flushes.

**Streaming does not equal chunked.** Chunked is an HTTP/1.1 framing technique, whereas streaming is emitting data over time and works with HTTP/2, HTTP/3, or responses with an exact `Content-Length`.

## 5. Timeline: When Is a Response Truly Complete?

```text
T0  Request arrives at container
    |
T1  Handler decides status, headers, response body, or publisher
    |
T2  Response committed: status/headers have been written to the output stream
    |   (typically on first flush, when buffer fills, or when container commits)
T3  Write + flush part 1 --- Write + flush part 2 --- ... final part
    |
T4  Protocol-level completion:
    |   exact N bytes (Content-Length), chunk 0, or END_STREAM
T5  Client finishes receiving/decoding/reading; may be later than T4
```

- **Handler return (T1):** the controller method has returned `ResponseEntity`, `StreamingResponseBody`, `Mono`, or `Flux`. For asynchronous responses, body generation may just be starting. Controller `return` is **not** a "finished sending" signal.
- **Commit (T2):** status and headers are locked for transmission; in Servlet you can check `HttpServletResponse.isCommitted()`. After commit, you normally cannot change `200` to `500` or reset the response to send a fresh JSON error body.
- **Flush (T3):** pushes written data through flushable buffers; the response remains open and more bytes may follow. Flushing does not end the response automatically.
- **Server-side completion (T4):** the framework/container has closed the response cleanly according to the protocol, or the async processing path has completed. If the stream fails, it may terminate abnormally before a complete message.
- **Client-side completion (T5):** when the client finishes processing and consuming the content is a separate milestone. The server cannot infer it merely from `write`/`flush` returning or a framework completion callback.

When sending a response with `Content-Length: 1000`, the client expects all **1000 bytes**: if the connection closes after 700 bytes, the message is incomplete rather than successfully finished. With HTTP/1.1 chunked, **chunk 0** is the valid terminator; simply closing the socket before chunk 0 leaves an incomplete body. With HTTP/2, the stream must end cleanly; resetting a stream mid-flight is not success.

## 6. Spring MVC Experiment: One Fixed Endpoint, One Streaming Endpoint

Create a Spring Boot application using `spring-boot-starter-web` (Spring MVC, Java 17+). In a Spring Boot project with this dependency, place the **entire file** below at `src/main/java/example/http/FramingApplication.java`:

```java
package example.http;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;

@SpringBootApplication
public class FramingApplication {

    public static void main(String[] args) {
        SpringApplication.run(FramingApplication.class, args);
    }

    @RestController
    static class HttpController {
        private static final MediaType TEXT_UTF8 =
                new MediaType("text", "plain", StandardCharsets.UTF_8);

        @GetMapping("/http/fixed")
        ResponseEntity<byte[]> fixed() {
            byte[] body = "Hello from Spring Boot!\n"
                    .getBytes(StandardCharsets.UTF_8);
            return ResponseEntity.ok()
                    .contentType(TEXT_UTF8)
                    .contentLength(body.length)
                    .body(body);
        }

        @GetMapping("/http/stream")
        ResponseEntity<StreamingResponseBody> stream() {
            StreamingResponseBody writer = output -> {
                for (int i = 1; i <= 3; i++) {
                    byte[] part = ("Part " + i + "\n")
                            .getBytes(StandardCharsets.UTF_8);
                    output.write(part);
                    output.flush();

                    try {
                        Thread.sleep(500);
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        throw new IOException("Write stream interrupted", e);
                    }
                }
            };

            return ResponseEntity.ok()
                    .contentType(TEXT_UTF8)
                    .body(writer);
        }
    }
}
```

**Why does this code fit the goal?**

- `/http/fixed` computes UTF-8 bytes before setting `contentLength(body.length)`. It has a response body of known size.
- `/http/stream` returns `StreamingResponseBody`: the callback writes directly to `OutputStream` inside Spring MVC's async mechanism; the controller call can return before the full body finishes.
- The loop emits three parts and flushes each one. `Thread.sleep(500)` is purely for observation; **do not use sleep for business synchronization in production**. Any `IOException` during writing is propagated to the runtime; do not attempt to return a new error body after the response is committed.
- The streaming endpoint **does not set `Content-Length` manually** because the example illustrates runtime/protocol-managed termination. With embedded Tomcat over HTTP/1.1 and no modifying intermediary, you will usually see `Transfer-Encoding: chunked`. This is an implementation result that can vary with protocol and configuration.

Run the app using the project command (`./gradlew bootRun` on Unix systems or `gradlew.bat bootRun` on Windows). In another terminal:

```bash
curl -i --http1.1 http://localhost:8080/http/fixed
curl -i -N --http1.1 http://localhost:8080/http/stream
```

`-i` shows headers; `-N` disables `curl`'s output buffering so the three parts appear progressively. Expected body of the stream request (each line roughly 0.5 seconds apart in local testing):

```text
Part 1
Part 2
Part 3
```

Use `curl -v -N --http1.1 ...` to observe protocol details. To inspect raw chunked framing bytes that `curl` normally decodes, use `curl --raw -i -N --http1.1 http://localhost:8080/http/stream`; chunk boundaries and sizes **are not guaranteed to match** the three application writes one-to-one. During experiments, temporarily disable compression and hit the embedded server directly so results are easy to compare.

Note for running Spring MVC streaming in production: write I/O in the Servlet stack is generally **blocking**, and `StreamingResponseBody` runs on an async executor. Configure an appropriate `AsyncTaskExecutor`, timeouts, concurrency limits, and test load/slow clients; do not schedule unbounded blocking work on the default executor.

## 7. Spring WebFlux: Data Source Completion

In **a separate Spring Boot WebFlux application** using `spring-boot-starter-webflux` (do not mix this into the MVC project above to avoid changing the expected runtime), the following controller emits three SSE events. Assume the application already has a `@SpringBootApplication` class in the parent package `example.http`.

```java
// File: src/main/java/example/http/EventController.java
package example.http;

import java.time.Duration;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

@RestController
public class EventController {
    @GetMapping(path = "/http/events",
                produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<String>> events() {
        return Flux.interval(Duration.ZERO, Duration.ofSeconds(1))
                .take(3)
                .map(index -> ServerSentEvent.<String>builder(
                                "Part " + (index + 1))
                        .event("progress")
                        .build());
    }
}
```

Run `curl -N -i http://localhost:8080/http/events`. Wire data is formatted as SSE, such as `event:progress` and `data:Part 1`, followed by a blank line, then the next event. Once `.take(3)` emits three items, `Flux` emits **onComplete**; the framework closes out the response once buffered data is processed. If the client disconnects early, the subscription may receive **cancel** rather than a normal completion. A non-terminating `Flux` (such as a long-lived event source) keeps the response open until canceled, errored, or explicitly closed.

In WebFlux, `Mono` typically represents at most one result and `Flux` represents multiple results; codecs and media types govern serialization/flushing. Returning `Flux<T>` with `application/json` **does not guarantee** each item appears immediately; use `text/event-stream` or NDJSON when the API requires item-by-item streaming to clients. Backpressure coordinates emission rates inside the reactive pipeline, yet it does not eliminate proxy/client buffering.

## 8. Commit, Completion, and Errors Across Models

### Servlet/Spring MVC

- In Servlet, `response.flushBuffer()` forces buffer flushing and commits the response; `response.isCommitted()` reports whether headers/status are committed. Calling `flushBuffer()` **does not** mean the Servlet has finished the body.
- For ordinary synchronous responses, return-value handling and body writing are handled by Spring/container. With `StreamingResponseBody`, controller return and callback completion happen at different times.
- `ResponseBodyEmitter` / `SseEmitter` support calling `send(...)` repeatedly followed by `complete()` or `completeWithError(...)`; they provide `onCompletion`, `onTimeout`, and `onError` callbacks for resource management and lifecycle observation. A completion callback marks server-side lifecycle completion, not proof of client rendering.
- At the low-level Servlet async layer, `AsyncContext.complete()` and `AsyncListener.onComplete/onError/onTimeout` exist; applications must not forget to complete, which would leave responses open until timeout. In Spring MVC, prefer framework async APIs over manual `AsyncContext` manipulation unless needed.
- During streaming, client disconnects are usually detected on the **next write** via `IOException`; Servlet does not guarantee immediate notification when a client leaves. For long-lived SSE, consider heartbeats and resource cleanup.

### WebFlux/Reactor

- `onComplete` is normal publisher completion; `onError` is abnormal termination; `cancel` is the signal that consumption was canceled (possibly due to client disconnect). These events belong to the source pipeline; bytes may still be in flight or in lower buffers.
- `ServerHttpResponse` finishing writes and closing the stream per protocol is a server-side metric. It is not proof that the client application finished parsing, rendering, or persisting the content.
- If an error occurs **before commit**, the framework can usually still choose an error status/headers. If **after commit**, do not rely on `@ExceptionHandler` to rewrite the already-emitted response into an error JSON; the connection/stream may terminate abnormally. Design streaming formats capable of expressing a business error event before closing cleanly, if the application protocol allows.

### What Can Each Completion Milestone Prove?

| Observed milestone | What you can conclude | What you cannot conclude |
|---|---|---|
| Controller returned | Handler handed the result/callback/publisher to the framework | Body has finished sending |
| `isCommitted() == true` | Headers/status can no longer be freely changed | Client received the entire body |
| `flush()` succeeded without error | The write/flush call at this layer returned | Every byte passed proxies and was read by the client |
| MVC `complete()`, WebFlux publisher `onComplete` | Application source/processing path finished normally | No lower-layer I/O error occurred or client finished consuming |
| Client received full `Content-Length`, final chunk, or `END_STREAM` | Message body is protocol-complete at the client | Client business logic finished executing |

## 9. Observing, Testing, and Troubleshooting

1. **Verify bytes and headers of fixed payloads:** compare `Content-Length` against actual byte length after serialization and `Content-Encoding`. In Java, use `byte[].length`, not `String.length()`.
2. **Observe progressive delivery:** use `curl -N -v --http1.1`, watching when data arrives rather than only after the command exits. With a proxy, test against the embedded server directly and through the proxy to locate buffering layers.
3. **Test each protocol:** compare HTTP/1.1 vs. HTTP/2 if the server/proxy enables HTTP/2. Do not expect `Transfer-Encoding: chunked` in HTTP/2; look for stream termination and observe data cadence.
4. **Test mid-stream client disconnect:** stop `curl` while streaming and observe `IOException` / cancel / cleanup callbacks, open connections, and retained resources.
5. **Test timeouts and post-flush errors:** observe that committed responses may be cut off mid-stream instead of reverting to HTTP 500 with a full body. For long-lived streams, set proper timeouts and design application-level retry, resume, or error signaling.
6. **Test over a real network:** controller unit tests or `MockMvc` validate content and mappings, but do not replace integration tests over a real HTTP port to verify chunking, flushing, proxies, compression, and disconnects.

Typical symptoms:

| Symptom | Possible cause | Troubleshooting step |
|---|---|---|
| Client waits for the entire response before seeing data | Buffering in converter, proxy, compression, or client; non-streaming media type | Pick streaming API/media type, check flush at each layer, try `curl -N`, and inspect proxy config |
| Client reports incomplete / connection reset | Wrong `Content-Length`, missing terminating chunk, stream reset, or dropped connection | Verify byte count/framing; log I/O errors, timeouts, and disconnects |
| API returns 200 even though streaming later fails | Headers were already committed before the failure occurred | Separate pre-commit and post-commit errors; emit stream-format error events if needed and handle client retries |
| High memory usage when sending large files | Materializing entire `byte[]`/JSON in RAM | Use `Resource`, block streaming, or suitable pipelines; bound concurrent streams |
| Long-lived SSE connections exhaust resources | Uncleaned subscriptions, missing timeout/heartbeat, undetected client disconnects | Handle completion/cancel/error, close upstreams, manage heartbeats and connection limits |
| `Content-Length` mismatch when gzip is enabled | Counting bytes before compression while sending compressed body | Let the runtime manage framing under compression or set length only from exact encoded bytes |

## 10. Design Rules to Remember

- **When exact final byte length is known:** use the exact `Content-Length` if appropriate; in Spring Boot, typically let the framework/container handle it unless manual control is needed.
- **When length is unknown:** never fabricate or "estimate" `Content-Length`. The server chooses valid framing per HTTP version; you can stream without holding the entire payload in memory.
- **When clients need progressive updates:** use a progressive format (SSE, NDJSON, or block-based binary), flush deliberately, check buffering layers, and handle early closes.
- **When you must guarantee the client processed the data:** use **application-layer** acknowledgments (ack, checkpoint, offset, idempotency, etc.), because server-side completion and TCP ACK do not mean the client application finished its work.
- **After commit:** do not expect to change status or replace already-sent body data; design logging, error handling, and streaming protocols upfront.

## 11. Self-Check

**Q1.** If Java `String.length()` is 12, must `Content-Length` be 12?  
**A:** No. Measure the bytes of the content actually transmitted after charset/serialization/encoding.

**Q2.** Does `Transfer-Encoding: chunked` mean data reaches the browser immediately after every `write()`?  
**A:** No. It is HTTP/1.1 framing; runtime, network, proxies, and clients may still buffer. One `write()` does not necessarily equal one chunk.

**Q3.** Once a controller executes `return StreamingResponseBody`, is the response complete?  
**A:** No. The callback still has to write and finish; the framework/container then closes out the response per protocol.

**Q4.** Is an HTTP/2 streaming response wrong if it lacks `Transfer-Encoding: chunked`?  
**A:** No. HTTP/2 uses DATA frames and `END_STREAM`; HTTP/1.1 chunked encoding is not used.

**Q5.** Does `onComplete` on the server guarantee the client wrote the data to its database?  
**A:** No. If that guarantee is needed, the client must acknowledge separately via an application-level protocol.

## Standards and References for Further Reading

- [RFC 9110 §8.6 — Content-Length](https://www.rfc-editor.org/rfc/rfc9110.html#section-8.6): semantics and special cases.
- [RFC 9112 §6–7 — HTTP/1.1 framing and chunked](https://www.rfc-editor.org/rfc/rfc9112.html#section-6): how message body length and terminating chunks are determined.
- [RFC 9113 §8 — HTTP/2 messages](https://www.rfc-editor.org/rfc/rfc9113.html#section-8): DATA, END_STREAM, and forbidden headers in HTTP/2.
- [Spring Framework — Asynchronous Requests (MVC)](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html): `StreamingResponseBody`, `ResponseBodyEmitter`, SSE, executors, and disconnects.
- [Spring Framework — Reactive Core (WebFlux)](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html): non-blocking I/O, codecs, and Reactive Streams.
