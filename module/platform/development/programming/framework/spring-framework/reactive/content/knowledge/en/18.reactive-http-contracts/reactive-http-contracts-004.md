# Limitations of changing the status after the response has been sent in Spring WebFlux

## 1. Why can the HTTP status not be changed arbitrarily?

In Spring WebFlux, the server builds an HTTP response consisting of a status code, headers, and a body. The status and headers are sent at the beginning of the response; the body is sent afterward. Once the server has **committed the response**, the initial metadata has already been applied to the response at the HTTP layer. At this point the client has received, or may have received, the status code and headers, so the server cannot replace the old status with a new one.

For example, the server has already started sending:

```http
HTTP/1.1 200 OK
Content-Type: text/plain

The operation started...
```

Then a subsequent task discovers that the database failed. The server cannot change the already-sent response to:

```http
HTTP/1.1 500 Internal Server Error
```

because the `200` status has already been sent in the headers section. Attempting to call an API to change the status after commit cannot take back the bytes the client has already received.

This is a limitation of the HTTP protocol and the response lifecycle, not a specific shortcoming of Reactor. Spring WebFlux represents this boundary through `ServerHttpResponse.isCommitted()` and the boolean result of `setStatusCode(...)`.

**Practical rule:** decide the status and required headers before you start writing the body. Once the response has committed, only continue sending the rest of the body if the stream is still valid; if the stream errors, handle it according to the policy for a stream that has already started, without trying to change the status.

## 2. What is response commit?

A response can pass through conceptual stages:

```text
NEW
 |
 | Set status, headers, cookies
 v
READY TO COMMIT
 |
 | Start writing/flushing body or complete the response
 v
COMMITTING
 |
 | Apply beforeCommit actions, status, headers, cookies
 v
COMMITTED
 |
 | Continue writing body if it is a streaming response
 v
COMPLETE
```

The state names above are a model to help understand the lifecycle, not a public enum that the application needs to drive itself.

- **Before commit:** the application can choose the status, content type, cache headers, cookies, and other metadata.
- **During commit:** Spring applies the `beforeCommit` callbacks, status, headers, and cookies down to the native response.
- **After commit:** the initial status and headers have already been sent. They cannot be replaced with new values.
- **After the body completes:** the response ends normally. Some streaming responses may have committed long ago while still emitting the body.

Normally a response is committed when writing the body or flushing data begins. For a response with no body, completion (`setComplete`) can also trigger commit. The exact timing depends on how the handler writes the response and the server implementation.

A crucial point: **committed does not mean the body has finished being sent**. With `Flux` or SSE, the server can commit headers and send the first chunk, and then continue emitting data for many seconds or minutes. Throughout that remaining time, the initial status stays fixed.

## 3. APIs to know on `ServerHttpResponse`

`ServerHttpResponse` belongs to the `org.springframework.http.server.reactive` package. Key APIs:

| API | Meaning |
|---|---|
| `setStatusCode(HttpStatusCode status)` | Sets the status; returns `true` if the change is accepted, `false` if the response has already committed |
| `getStatusCode()` | Reads the set status or the status from the underlying server; may be `null` if there is no default value yet |
| `isCommitted()` | Checks whether the response has committed |
| `getHeaders()` | Accesses the response headers |
| `getCookies()` / `addCookie(...)` | Prepares cookies for the response |
| `beforeCommit(Supplier<Mono<Void>> action)` | Registers work to run right before the response commits |
| `writeWith(Publisher<DataBuffer>)` | Writes the body from a Publisher |
| `writeAndFlushWith(Publisher<Publisher<DataBuffer>>)` | Writes groups of buffers and flushes after each group |
| `setComplete()` | Completes the response without a body |

### 3.1. The return value of `setStatusCode`

This is the most important point to remember:

```java
boolean changed = response.setStatusCode(
        HttpStatus.INTERNAL_SERVER_ERROR
);

if (!changed) {
    // The response has already committed; the status was not changed.
}
```

`setStatusCode` **does not necessarily throw an exception** when the response has already committed. It returns `false` to report that the change was not made. Do not ignore the boolean value if your code depends on the status having been set successfully.

Do not confuse it with `setRawStatusCode(Integer)`: the raw status API also has a similar boolean result and has been deprecated in newer Spring versions in favor of `HttpStatusCode`.

### 3.2. `isCommitted()` is only an observation

You can check before making a change:

```java
if (!response.isCommitted()) {
    response.setStatusCode(HttpStatus.BAD_REQUEST);
}
```

This is a useful check for choosing a processing branch. However, in an asynchronous pipeline, another callback may cause the response to commit after the check. Therefore, **do not treat `isCommitted()` as a synchronization lock**. Check the result of `setStatusCode` and make the status decision at a boundary before writing the response.

### 3.3. Headers and cookies are also subject to the commit limit

The status is not the only metadata that is locked. After commit, modifying headers may no longer have any effect or may be rejected depending on the implementation. Calling `addCookie` on `ServerHttpResponse` may throw `IllegalStateException` when the response has already committed.

Prepare values such as:

- `Content-Type`
- `Content-Length` (if known accurately and appropriate)
- `Cache-Control`
- `ETag`
- `Location`
- `Set-Cookie`
- CORS/security headers

before starting to write the body, or register a `beforeCommit` callback for metadata that needs to be added at commit time.

## 4. Setting the status before writing the body

The simplest and clearest way is to decide the status before `writeWith(...)`:

```java
Mono<Void> writeCreated(ServerHttpResponse response) {
    response.setStatusCode(HttpStatus.CREATED);
    response.getHeaders().setContentType(MediaType.TEXT_PLAIN);

    byte[] bytes = "created\n".getBytes(StandardCharsets.UTF_8);
    DataBuffer buffer = response.bufferFactory().wrap(bytes);

    return response.writeWith(Mono.just(buffer));
}
```

Sequence:

1. Choose `201 Created`.
2. Prepare `Content-Type`.
3. Create the `DataBuffer`.
4. Return the Publisher that writes the body.
5. Spring/the server commits the response and sends the status, headers, and body.

At the moment `writeWith` is subscribed to and starts executing, the status has already been chosen. If the data needed to decide the status is not available yet, fetch that data before calling `writeWith`.

### 4.1. Performing business checks before commit

For example, an order-creation endpoint needs to check the product and ownership before returning `201`:

```java
Mono<Void> createOrder(ServerHttpResponse response, CreateOrder command) {
    return orderService.validate(command)
            .then(orderService.create(command))
            .flatMap(order -> {
                response.setStatusCode(HttpStatus.CREATED);
                response.getHeaders().set(
                        HttpHeaders.LOCATION,
                        "/orders/" + order.id()
                );
                return response.writeWith(
                        Mono.just(jsonBuffer(response, order))
                );
            })
            .onErrorResume(ProductNotFoundException.class, error -> {
                response.setStatusCode(HttpStatus.NOT_FOUND);
                return response.writeWith(
                        Mono.just(textBuffer(response, "product not found"))
                );
            });
}
```

This is illustrative code: `orderService`, `CreateOrder`, `jsonBuffer`, and `textBuffer` are application components. The point is that the validate/create part runs before the body is sent; if an error occurs at this stage, the handler can still choose `404` or an appropriate status.

If `orderService.create(...)` wrote data successfully but writing the response failed, you should not automatically retry the order-creation operation without an idempotency key. Transport errors and business errors are two different situations.

## 5. `beforeCommit`: preparing metadata right before sending

`beforeCommit(...)` is useful when a filter or infrastructure layer needs to add headers/cookies after the handler logic has determined the response, but before the server commits.

```java
response.beforeCommit(() -> Mono.fromRunnable(() -> {
    response.getHeaders().set("X-Response-Policy", "validated");
    response.setStatusCode(HttpStatus.ACCEPTED);
}));
```

The callback takes a `Supplier<Mono<Void>>`. **The action must be deferred** so that it runs at the right commit time and in the right order with other actions. Common forms:

```java
response.beforeCommit(() ->
        Mono.fromRunnable(() ->
                response.getHeaders().set("X-Trace-Ready", "true")
        )
);
```

Or:

```java
response.beforeCommit(() ->
        Mono.defer(() -> {
            response.getHeaders().set("X-Trace-Ready", "true");
            return Mono.empty();
        })
);
```

Do not write:

```java
// WRONG: the side effect runs right at registration time, not deferred.
response.beforeCommit(setHeaderImmediately(response));
```

If `setHeaderImmediately(...)` modifies the header as soon as it is called and only returns an already-created Mono, the side effect may happen before the callback is actually executed.

Use `beforeCommit` for short, non-blocking work that can complete within commit time. Do not call a database, wait on an HTTP client, or perform blocking I/O inside this callback. Those tasks must finish before commit begins.

**Limitation:** `beforeCommit` is the last chance to prepare metadata before sending; it is not a hook to fix the status after the body has already been sent. Registering a callback after the response has already committed cannot turn back time to fix the response.

## 6. Why can `onErrorResume` after writing the body not change the status?

A common mistake is putting a fallback after the write operation:

```java
return response.writeWith(body)
        .onErrorResume(error -> {
            response.setStatusCode(HttpStatus.INTERNAL_SERVER_ERROR);
            return response.writeWith(
                    Mono.just(textBuffer(response, "failed"))
            );
        });
```

The snippet above **is unsafe**. When `writeWith(body)` emits an error, the response may have already committed and part of the body may have reached the client. `setStatusCode(500)` may return `false` at that point; calling `writeWith` a second time also cannot turn an already-sent response into a valid new response.

The right approach is to distinguish whether the error occurred **before** or **after** commit:

```java
return operationThatMayFail()
        .flatMap(value -> writeSuccess(response, value))
        .onErrorResume(error -> {
            if (response.isCommitted()) {
                return Mono.error(error);
            }

            boolean changed =
                    response.setStatusCode(HttpStatus.INTERNAL_SERVER_ERROR);

            if (!changed) {
                return Mono.error(error);
            }

            return writeError(response, "request failed");
        });
```

This is illustrative code. `operationThatMayFail`, `writeSuccess`, and `writeError` belong to the application. The before-commit branch can still choose the status and write an error body. The after-commit branch propagates the error further so the runtime/server handles the failed stream, rather than pretending a new HTTP response can be created.

In a real application, place an error boundary around each business operation before writing the body. If an error can only happen during streaming, choose a protocol for representing errors in the stream or accept that the stream terminates abnormally.

## 7. Error handling in `WebExceptionHandler`

`WebExceptionHandler` is often used to map WebFlux errors into a unified response. The handler must check whether the response has already committed:

```java
@Component
class ApiExceptionHandler implements WebExceptionHandler {

    @Override
    public Mono<Void> handle(
            ServerWebExchange exchange,
            Throwable error) {

        ServerHttpResponse response = exchange.getResponse();

        if (response.isCommitted()) {
            // Cannot replace the already-sent status/body.
            return Mono.error(error);
        }

        response.setStatusCode(HttpStatus.INTERNAL_SERVER_ERROR);
        response.getHeaders().setContentType(MediaType.TEXT_PLAIN);

        byte[] bytes = "internal server error\n"
                .getBytes(StandardCharsets.UTF_8);

        DataBuffer buffer = response.bufferFactory().wrap(bytes);
        return response.writeWith(Mono.just(buffer));
    }
}
```

This is an illustrative pattern for errors not yet handled at earlier layers. In a production application:

- Map exceptions only according to type and HTTP policy; do not turn every error into `500` if a specific status applies.
- Do not send stack traces, SQL, tokens, or internal information in the error body.
- If the response has already committed, do not write a second error body. Log/trace with a correlation ID and let the error propagate to the runtime.
- Avoid having multiple `WebExceptionHandler`s handle the same error or subscribing to the Publisher yourself.
- If an error arises when the client has already disconnected, check for cancellation and avoid performing cleanup twice.

## 8. Streaming: the status is fixed right from the start

A streaming response makes the commit limit clearest. For example, the server sends three lines of NDJSON:

```text
{"type":"progress","value":1}
{"type":"progress","value":2}
{"type":"progress","value":3}
```

As soon as the response begins being sent, the status and headers are committed. If the source emits an error before the third line, the client may have already received status `200` and the first two lines. The server cannot change the status to `500` on the third line.

A stream can be created with:

```java
Flux<Progress> progress = job.events();

return progress
        .map(this::toProgressDto)
        .as(events -> ServerResponse.ok()
                .contentType(MediaType.APPLICATION_NDJSON)
                .body(events, ProgressDto.class));
```

This is an illustrative WebFlux.fn example; `job.events`, `toProgressDto`, and the DTOs belong to the application. `ServerResponse.ok()` chooses the status before the body Publisher is written. If the stream errors after the response has committed, the `200` status remains the initial status.

### 8.1. Business errors in a stream should be represented in the data

If the protocol allows it, the stream can emit an error event as a final element:

```java
Flux<StreamMessage> messages = job.events()
        .map(value -> StreamMessage.progress(value))
        .onErrorResume(error ->
                Flux.just(StreamMessage.failed("job interrupted"))
        );
```

`StreamMessage` is an application-defined DTO type. The client needs to clearly understand that the `"failed"` event is the business outcome of the stream; the HTTP status stays the same because the response has already started.

With Server-Sent Events, you can use event names such as `progress`, `completed`, and `error`. With NDJSON, you can emit an object with a `type` field. This is an application protocol; you should not send stack traces or internal details in error events.

If the API does not define an error event in the body, you can terminate the stream with an error and let the client recognize that the connection/stream was interrupted. The client needs controlled retry/reconnect, ideally based on an event ID or cursor to avoid duplicate processing.

### 8.2. Do not buffer the entire stream just to be able to change the status

One way to sidestep the problem is to gather every element into memory before sending the response. This approach allows determining errors before commit, but can cause:

- RAM usage growing with the result size.
- Increased latency before the client receives the first byte.
- Unsuitability for infinite or long-lived streams.
- Loss of backpressure and incremental processing benefits.

Buffer only when the result is bounded, its size is controlled, and the business genuinely needs to know the whole result before returning the status. For large data, design the stream with clear event/error semantics.

## 9. `writeWith`, `writeAndFlushWith`, and the commit point

`writeWith(Publisher<DataBuffer>)` writes the body from one Publisher. `writeAndFlushWith(Publisher<Publisher<DataBuffer>>)` writes each Publisher group and flushes after each group.

Example of a line-by-line flushing stream:

```java
Flux<Publisher<DataBuffer>> chunks = Flux.just(
        "first\n",
        "second\n",
        "third\n"
).map(line -> Mono.just(
        response.bufferFactory().wrap(
                line.getBytes(StandardCharsets.UTF_8)
        )
));

return response.writeAndFlushWith(chunks);
```

This is illustrative code requiring the import `org.reactivestreams.Publisher`; chunks can be flushed individually so the client receives data early. The first write/flush can cause the response to commit. Subsequent flushes send more body; they do not reopen the opportunity to change the status.

With `Flux<DataBuffer>`, `writeWith` can pass many buffers, but the server can decide batching/flushing on its own. If you need per-group streaming, `writeAndFlushWith` expresses the flush requirement more explicitly. Whichever API you use, treat the **first commit** as the boundary where status/headers can no longer change.

## 10. Headers, cookies, and changes after commit

Metadata operations need to be completed before commit:

```java
response.setStatusCode(HttpStatus.CREATED);
response.getHeaders().setContentType(MediaType.APPLICATION_JSON);
response.getHeaders().setCacheControl(CacheControl.noStore());
response.getHeaders().setLocation(URI.create("/orders/123"));
response.addCookie(ResponseCookie.from("notice", "created")
        .httpOnly(true)
        .secure(true)
        .sameSite("Lax")
        .path("/")
        .build());
```

This is an example of preparing response metadata. In production, cookies need attributes matching the domain, HTTPS, SameSite, and the application's security policy.

After commit:

- The status code is fixed.
- Already-sent headers cannot be modified.
- Already-sent `Set-Cookie` cookies cannot be replaced in the current response.
- `Content-Type` cannot be changed to make the client interpret already-received bytes in a different format.
- `Location` or the cache policy cannot be changed after the response has started.

HTTP trailers (if supported by the server/client/protocol) are metadata at the end of a message; they do not replace the initial status and are not a way to fix the status after commit.

## 11. Distinguishing response status from transport errors

Not every error occurring after commit means a different HTTP status.

| Situation | Can the status be changed? | Appropriate behavior |
|---|---|---|
| Validation fails before body write | Yes | Return `400` or an appropriate business status |
| Data not found before commit | Yes | Return `404` |
| Service errors before commit | Yes | Map to `5xx` or a fallback |
| Stream already sent some chunks and then the source emits an error | No | Emit an error event if the protocol supports it, or terminate the stream |
| Client disconnects while the body is being sent | No | Cancel work, release resources, and record cancellation |
| Socket write fails after commit | No | Propagate the error to the runtime, do not write a second response |
| Error occurs after the body completes | No need to change status | Log/metrics for post-processing tasks; the response has completed |

A request may be processed successfully at the business layer yet the client does not receive the full response due to a network error. You cannot know for sure how many bytes the client received just by looking at whether the Publisher emitted complete/error. For write operations with side effects, design idempotency and the ability for clients to query transaction status.

## 12. Runnable Java 17+ example with Spring Boot WebFlux

The example below has three endpoints:

- `/responses/early`: sets status `201` before writing the body.
- `/responses/before-commit`: sets status `202` and a header inside a `beforeCommit` callback.
- `/responses/late`: writes the body first, then tries to change the status to `500`; the API returns `false` because the response has already committed.

### Project structure

```text
response-commit-demo/
├── pom.xml
└── src/main/java/demo/Main.java
```

### File `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>response-commit-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

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
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### File `src/main/java/demo/Main.java`

```java
package demo;

import java.nio.charset.StandardCharsets;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@SpringBootApplication
public class Main {

    public static void main(String[] args) {
        SpringApplication.run(Main.class, args);
    }
}

@RestController
@RequestMapping("/responses")
class ResponseController {

    @GetMapping("/early")
    Mono<Void> early(ServerHttpResponse response) {
        response.setStatusCode(HttpStatus.CREATED);
        response.getHeaders().setContentType(MediaType.TEXT_PLAIN);

        return write(response, "created before commit\n");
    }

    @GetMapping("/before-commit")
    Mono<Void> beforeCommit(ServerHttpResponse response) {
        response.beforeCommit(() -> Mono.fromRunnable(() -> {
            response.setStatusCode(HttpStatus.ACCEPTED);
            response.getHeaders().set("X-Prepared", "true");
        }));

        response.getHeaders().setContentType(MediaType.TEXT_PLAIN);
        return write(response, "status prepared before commit\n");
    }

    @GetMapping("/late")
    Mono<Void> late(ServerHttpResponse response) {
        response.getHeaders().setContentType(MediaType.TEXT_PLAIN);

        return write(response, "body already sent with original status\n")
                .doOnSuccess(ignored -> {
                    boolean accepted = response.setStatusCode(
                            HttpStatus.INTERNAL_SERVER_ERROR
                    );

                    System.out.println(
                            "late status accepted=" + accepted
                                    + ", committed=" + response.isCommitted()
                    );
                });
    }

    private Mono<Void> write(ServerHttpResponse response, String text) {
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        DataBuffer buffer = response.bufferFactory().wrap(bytes);
        return response.writeWith(Mono.just(buffer));
    }
}
```

From the project directory, JDK 17+ and Maven are required:

```bash
mvn spring-boot:run
```

### Checking the status set before commit

```bash
curl -i http://localhost:8080/responses/early
```

Important parts of the response:

```http
HTTP/1.1 201 Created
Content-Type: text/plain

created before commit
```

### Checking `beforeCommit`

```bash
curl -i http://localhost:8080/responses/before-commit
```

Important parts:

```http
HTTP/1.1 202 Accepted
Content-Type: text/plain
X-Prepared: true

status prepared before commit
```

### Trying to change the status after the body has been sent

```bash
curl -i http://localhost:8080/responses/late
```

Important parts of the response:

```http
HTTP/1.1 200 OK
Content-Type: text/plain

body already sent with original status
```

Application console when calling the `/late` endpoint:

```text
late status accepted=false, committed=true
```

Explanation:

1. `/early` sets `201` before calling `writeWith`, so the server sends `201 Created`.
2. `/before-commit` registers a deferred callback; when the response is about to commit, the callback sets `202` and the `X-Prepared` header.
3. `/late` writes the body first. When `writeWith` completes, the response is already committed.
4. The `setStatusCode(500)` call returns `false`, so the response remains `200 OK`.
5. `doOnSuccess` only observes the write result; it does not reopen the response to fix the status.

Secondary headers such as `Date`, `Content-Length`, or `Connection` may vary by server and HTTP client; the status, custom header, and body above are what to verify.

## 13. Testing with `WebTestClient`

You can test the controller without opening a TCP port:

```java
WebTestClient client = WebTestClient
        .bindToController(new ResponseController())
        .build();

client.get()
        .uri("/responses/early")
        .exchange()
        .expectStatus().isCreated()
        .expectBody(String.class)
        .isEqualTo("created before commit\n");

client.get()
        .uri("/responses/before-commit")
        .exchange()
        .expectStatus().isAccepted()
        .expectHeader().valueEquals("X-Prepared", "true");

client.get()
        .uri("/responses/late")
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class)
        .isEqualTo("body already sent with original status\n");
```

This is a test snippet requiring the `spring-test` dependency (usually brought in via `spring-boot-starter-test`) and the `WebTestClient` import. The test verifies the actual status the client receives, rather than only checking internal logs.

You can test commit logic separately with a mock response in a unit test if the project uses `spring-test`. However, an integration test via WebTestClient is more useful when you need to confirm the controller, response writer, and emitted status together.

## 14. Common mistakes

| Error | Consequence | How to fix |
|---|---|---|
| Calling `setStatusCode(500)` after `writeWith` has started | Returns `false`; the old status is kept | Decide the status before the first write |
| Ignoring the boolean returned from `setStatusCode` | Code assumes the status changed, yet the client still receives the old status | Check the return value |
| Only checking `isCommitted()` and assuming the operation will definitely succeed | Can hit an asynchronous commit boundary | Check the result of `setStatusCode` as well |
| Using `onErrorResume` after the stream has sent part of the body | Cannot replace the old response with a new status/body | Recover from errors before commit or emit an error event in the stream |
| Calling `writeWith` a second time to send an error body | Can cause an already-committed response, a broken body, or a write error | Write only one response; after commit, propagate the error/close the stream |
| Registering `beforeCommit` while performing an eager side effect | The action runs too early, out of order | Return `Mono.defer` or `Mono.fromRunnable` from the supplier |
| Calling blocking I/O inside `beforeCommit` | Slows down commit and may block the event loop | Finish I/O before commit; the callback should only do short work |
| Buffering an infinite stream to wait to determine the status | Unbounded RAM growth and high latency | Design the status before the stream or use event/error semantics |
| Thinking `isCommitted=true` means the body is finished | Ignores errors/cancellations that can still happen while the stream continues | Distinguish metadata commit from body completion |
| Trying to change Content-Type or cookies after commit | The client has already received the old metadata | Prepare headers/cookies before writing |
| Swallowing errors after commit and reporting the stream as successful | The client may receive an incomplete body without knowing | Propagate the error or emit an error event per the protocol |
| Retrying the entire operation after a response write failure | Side effects may run repeatedly | Use an idempotency key and separate business retry from transport retry |

## 15. Safe endpoint design checklist

Before returning a response, determine:

1. Which data does the status depend on? Is that data available before the first write?
2. Can the entire request be authenticated, authorized, and validated before commit?
3. Have headers, cookies, `Location`, cache policy, and content type been prepared?
4. Are there any `beforeCommit` callbacks to run? Is the callback deferred and non-blocking?
5. Is the body a finite object or a long stream? If the stream errors midway, how will the client know?
6. Does the error handler distinguish errors before commit from errors after commit?
7. Is any code trying to write the response a second time?
8. If the client disconnects, are subscriptions and resources cleaned up properly?
9. For operations with side effects, can a client retry cause duplicates?
10. Is there an integration test verifying the actual status the client receives?

## 16. Self-check exercises

**Question 1.** What does `ServerHttpResponse.setStatusCode(HttpStatus.INTERNAL_SERVER_ERROR)` return when the response is already committed?

**Answer:** `false`. The new status is not applied.

**Question 2.** Does `isCommitted()` mean the entire body has finished being sent?

**Answer:** No. Headers/status are committed, but the body may continue streaming.

**Question 3.** Can `beforeCommit` be used to change the status?

**Answer:** Yes, if the callback is registered before commit and performs the change inside a deferred action. It runs right before the status/headers are applied.

**Question 4.** A `Flux` has sent two chunks and then emits `onError`. Can the server change the status to 500?

**Answer:** No. The initial status has already been sent. An error event can be emitted if the application protocol supports it, or the stream can be terminated with an error.

**Question 5.** Why should `writeWith` not be called a second time in `onErrorResume` after commit?

**Answer:** The current response has already started sending and cannot become a new response. Writing a body a second time can cause an error or produce protocol-invalid data.

**Question 6.** When should all data be buffered before writing the response?

**Answer:** When the result is clearly bounded, all data must be known before deciding the status, and the memory footprint is acceptable. Do not buffer large/infinite streams just to sidestep the commit boundary.

**Question 7.** Why check the boolean from `setStatusCode` even after checking `isCommitted()`?

**Answer:** Because commit is an asynchronous process; the state can change between the check and the operation. The boolean result tells whether the change was actually accepted.

## 17. Rules to apply

- Set status and headers **before the first body write**.
- Use `isCommitted()` to observe and check the boolean of `setStatusCode(...)` to know whether the change succeeded.
- Use `beforeCommit` for final metadata; the callback must be deferred and non-blocking.
- Handle validation, authorization, and business errors before commit if the status depends on those results.
- After commit, do not attempt to change status, headers, or cookies, or write a second error response.
- For a stream that has already started, represent errors in the event/body per protocol or let the stream end with an error.
- Test with `WebTestClient` and verify the status/body the client actually receives.

**Key takeaway:** The HTTP status is sent along with the headers when the response commits. In Spring WebFlux, `setStatusCode` returns `false` if the response has already committed; `beforeCommit` is the last chance to prepare metadata. Decide the status before writing the body and design a separate way to represent errors for streaming responses.

## 18. Official references

- [Spring Framework 6.1 — `ServerHttpResponse` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/http/server/reactive/ServerHttpResponse.html)
- [Spring Framework 6.1 — `ReactiveHttpOutputMessage` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/http/ReactiveHttpOutputMessage.html)
- [Spring Framework 6.1 — `AbstractServerHttpResponse` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/http/server/reactive/AbstractServerHttpResponse.html)
- [Spring Framework — WebFlux functional endpoints](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html)
- [Spring Framework — WebFlux exception handling](https://docs.spring.io/spring-framework/reference/web/webflux/ann-exceptions.html)
