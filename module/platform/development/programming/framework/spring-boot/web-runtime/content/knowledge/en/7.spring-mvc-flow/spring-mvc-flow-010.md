# When HTTP Responses Commit and Limits on Modifying Status/Headers in Spring MVC

## 1. Lesson Objectives

In Spring Boot using Spring MVC and the Servlet stack, an application can set the HTTP status, response headers, and response body via `ResponseEntity`, annotations, filters, interceptors, `@ExceptionHandler`, or directly on `HttpServletResponse`. However, those changes take effect only if applied **before the HTTP response is committed**.

A common bug is writing or flushing part of the body and then trying to change the status from 200 to 500 or add `Location`, `Set-Cookie`, or `Access-Control-Allow-Origin` headers. Once the status and headers have been sent by the Servlet container, the application cannot rewind to rewrite them.

After this lesson, you should be able to:
- Understand precisely what `committed` means and distinguish it from returning from a controller.
- Recognize operations that commit a response: `flushBuffer()`, flushing the writer/output stream, filling the buffer, `sendError()`, and `sendRedirect()`.
- Distinguish `setStatus`, `setHeader`, `addHeader`, `reset()`, and `resetBuffer()` before and after commit.
- Choose the right moment to set status/headers across `DispatcherServlet`, filters, interceptors, `ResponseEntity`, and exception handlers.
- Design proper error handling and streaming when status codes can no longer change after data is sent.
- Verify behavior with Java 17+ code running in Spring Boot 3.x and real HTTP tools.

The main scope is **Spring MVC on Jakarta Servlet**, typically using embedded Tomcat via `spring-boot-starter-web`. WebFlux/Netty has separate APIs and commit semantics; do not apply `HttpServletResponse` assumptions directly to WebFlux.

## 2. What Is Commit?

An HTTP response consists of:
1. **Status:** e.g., `200 OK`, `201 Created`, `400 Bad Request`, `500 Internal Server Error`.
2. **Headers:** e.g., `Content-Type`, `Location`, `Cache-Control`, `Set-Cookie`.
3. **Body:** JSON, HTML, plain text, file bytes, chunks, or events.

**Commit** in Servlet terminology means the status and response headers have been written out toward the client at the server's response layer. Under the Jakarta Servlet contract, `response.isCommitted()` returns `true` once the response is committed.

This has two consequences:
- **Before commit:** within API limits, you can change status, headers, content type, and buffered body content.
- **After commit:** you cannot change the status or already-sent headers. You can still write further body bytes if the stream remains open, but you cannot turn an already-started response into a different HTTP error response.

Commit **does not equal**:
- The controller simply executing `return`.
- Calling `response.getWriter()`.
- Calling `writer.write(...)` once while data still sits in the buffer.
- The entire body having finished sending or the client definitely having received every byte. Networks and reverse proxies can still buffer data after the container commits.

In HTTP/1.1, we think of the status line and headers being transmitted. In HTTP/2, the equivalent information is carried by the `HEADERS` frame and `:status` pseudo-header; the restriction against changing status/headers after commit remains conceptually identical.

## 3. Response Lifecycle in Spring MVC

Typical processing flow of a synchronous Servlet request:

~~~text
Client
  |
Servlet container (Tomcat / Jetty / Undertow)
  |
Servlet Filter chain
  |  sets certain headers before calling chain
  v
DispatcherServlet
  |
HandlerMapping -> HandlerInterceptor.preHandle
  |
HandlerAdapter -> @Controller / @RestController
  |
Handle return value / exception
  |  ResponseEntity, @ResponseBody, @ResponseStatus
  |  HttpMessageConverter or ViewResolver
  v
Serialize body / render view / write servlet response
  |
Buffer / flush / commit
  |
Container sends bytes over the network
  |
Filters unwind / completion callbacks
~~~

This diagram shows the conceptual progression; some rendering and response writing may occur before later callbacks run.

**The safest place to choose status and headers** is usually when the controller constructs a `ResponseEntity` or before body writing begins. `HttpMessageConverter` normally picks a representation from the return value and media type, then writes the body. Actual commit can occur on flush, when the buffer fills, or when the container finishes the response; therefore **there is no rule that "returning from a controller means the response is committed."**

### 3.1. For Standard JSON Responses

Example handler returning:

~~~java
@GetMapping("/items/{id}")
ResponseEntity<ItemDto> get(@PathVariable long id) {
    ItemDto item = service.find(id);
    return ResponseEntity.ok()
            .header("X-Item-Version", "1")
            .body(item);
}
~~~

This snippet is a controller fragment assuming `ItemDto` and `service`, not a standalone program. Spring MVC reads `ResponseEntity`, applies status/headers, and passes the DTO to `HttpMessageConverter` for serialization. If an error occurs while writing JSON after the buffer has already been flushed, an exception handler cannot guarantee changing the response to 500 with a complete JSON error body.

### 3.2. For JSP, Thymeleaf, or ViewResolver

With a `@Controller` returning a view name, view rendering also writes to the response. It might not be committed right when the handler returns, yet a large view or template can fill the buffer and trigger commit before rendering finishes. Consequently, rendering errors can happen after commit.

## 4. Operations That Commit the Response

| Operation / situation | Causes commit? | Explanation |
|---|---|---|
| `response.setStatus(201)` | Not yet | Only updates the pending status; does not force sending bytes |
| `response.setHeader(...)` / `addHeader(...)` | Not yet | Sets headers on an uncommitted response |
| `response.getWriter()` | Not just from obtaining the writer | May lock in the character encoding choice at this point |
| `writer.write("abc")` | Not necessarily | May stay buffered; if buffer fills, container can auto-flush and commit |
| `response.getOutputStream().write(...)` | Not necessarily | Same buffering and payload size rules |
| `response.flushBuffer()` | **Yes** | Forces buffer flush; status and headers are committed |
| `writer.flush()` / `outputStream.flush()` | **Can trigger commit** | Per writer/stream flush contracts, treat as a commit point |
| Writing past response buffer capacity | **Can auto-commit** | Container can flush once the buffer cannot hold more body |
| `response.sendError(...)` | **Yes** per Servlet contract | Produces an error response; application should not keep writing body |
| `response.sendRedirect(...)` | **Yes** per Servlet contract | Sends redirect, setting status and `Location` per API/version |
| Request finishes and container completes response | Usually yes | If not committed earlier, container finalizes sending the response |
| `ResponseEntity.status(...).body(...)` | Not an immediate commit | Only describes the result; body writing/flushing happens during return-value handling |

**Do not infer commit solely from the byte count passed to `write()`.** Actual buffer sizes, serializers, servlet containers, filter wrappers, and streaming patterns can all shift the commit point.

## 5. Limits on Modifying Status and Headers After Commit

APIs and outcomes to remember:

| API | Before commit | After commit |
|---|---|---|
| `setStatus(int)` | Updates the current response status | Cannot alter already-sent status; late calls have no effect |
| `setHeader(name, value)` | Replaces existing header values with the same name | Cannot modify already-sent headers; late calls have no effect |
| `addHeader(name, value)` | Appends a header value | Cannot append headers to already-committed output |
| `setContentType(...)` | Configures type before writing, subject to writer/encoding rules | Cannot alter an already-sent `Content-Type` header |
| `setCharacterEncoding(...)` | Effective before commit and before obtaining writer | Usually ineffective once writer is obtained, even before commit |
| `addCookie(cookie)` | Adds cookie to emit as `Set-Cookie` | Cannot emit headers that were already committed |
| `sendError(status)` | Can replace with error response and clear buffer per contract | Throws `IllegalStateException` if already committed |
| `sendRedirect(uri)` | Can issue redirect response | Throws `IllegalStateException` if already committed |
| `resetBuffer()` | Clears buffered body while keeping status and headers | Throws `IllegalStateException` |
| `reset()` | Clears buffer, status, headers, and resets writer/stream selection per contract | Throws `IllegalStateException` |

Distinguish **changing pending response state** from **sending bytes over the wire**. Calling `setStatus(404)` before commit only updates the pending status code; it does not make the Servlet container generate an error page. Triggering container error handling via `sendError` or Spring Boot's `/error` behaves differently from merely calling `setStatus`.

### 5.1. `resetBuffer()` vs. `reset()`

Suppose status = 201, header `X-Request-Id` is set, body `"part A"` is still buffered, and the response is not yet committed:

~~~java
response.setStatus(201);
response.setHeader("X-Request-Id", "r-42");
response.getWriter().write("part A");

response.resetBuffer(); // clears unsent body
response.getWriter().write("part B");
// status 201 and X-Request-Id are preserved
~~~

`resetBuffer()` preserves status and headers. By contrast, `reset()` clears body, status, headers, and writer/output-stream selection state. After `reset()`, if a writer was previously obtained, do not keep using the old writer reference indiscriminately; follow the Servlet API contract. Both methods are illegal once `isCommitted()` is `true`.

### 5.2. Adjusting Buffer Size

`response.setBufferSize(n)` asks the container to provide a response buffer of at least the requested size; the container may allocate a larger one. Per the Servlet API, calling it after content has been written (or after commit) can throw `IllegalStateException`.

Enlarging the buffer can delay commit for moderately sized bodies, **but is not a sound error-handling strategy**. For large files or streaming, the container must eventually commit and flush chunks. Validate inputs and determine status before streaming rather than hoping every payload fits in the buffer.

## 6. Choosing the Right Moment Inside Controllers

### 6.1. Set Status/Headers Immediately in ResponseEntity

Use `ResponseEntity` to align status, headers, and body:

~~~java
@PostMapping("/orders")
ResponseEntity<OrderDto> create(@RequestBody CreateOrder input) {
    OrderDto created = service.create(input);
    URI location = URI.create("/orders/" + created.id());

    return ResponseEntity.created(location)
            .header("Cache-Control", "no-store")
            .body(created);
}
~~~

This snippet is illustrative inside a controller with `OrderDto`, `CreateOrder`, and `service`. It returns 201, the `Location` header, and the body upon creating the resource. All of this is given to Spring MVC **before** the converter begins writing the body.

Use `@ResponseStatus` for static statuses and `ResponseEntity` when status/headers depend on business outcomes. If security, cache, CORS, or correlation ID headers are needed, set them in appropriate filters or response handlers before body output begins.

### 6.2. Avoid Setting Headers After Writing the Body

The following snippet is risky:

~~~java
response.getWriter().write(bigPayload);
response.setHeader("X-Trace-Id", traceId);
~~~

If `bigPayload` overflows the buffer or flushes the writer, the header may be silently ignored because the response already committed. Call `setHeader` before calling `write`, `flush`, or handing a body to a converter.

### 6.3. When Writing Directly to HttpServletResponse

If a handler writes directly to `HttpServletResponse` and returns `void`, the application manages status, headers, and body itself. Never write directly with `getWriter()` and simultaneously expect a `ResponseEntity` processed afterward to override an already-committed status. Pick one consistent mechanism per endpoint.

## 7. Timing in Filters, Interceptors, and Advice

This is where bugs frequently arise because not every callback runs before the body is transmitted.

| Location | Timing in normal synchronous flow | Safe to set status/headers? |
|---|---|---|
| `Filter.doFilter` **before** `chain.doFilter` | Before `DispatcherServlet` and controller | Generally the right spot for shared headers |
| `Filter.doFilter` **after** `chain.doFilter` | After downstream finishes; response may be committed | Do not rely on this for mandatory headers |
| `HandlerInterceptor.preHandle` | Before controller | Can set headers before body is written |
| `HandlerInterceptor.postHandle` | After handler; often after `@ResponseBody` processing, before view rendering | Not guaranteed that response is uncommitted |
| `HandlerInterceptor.afterCompletion` | End of request processing, for cleanup/metrics | Usually too late to modify status/headers |
| `ResponseBodyAdvice.beforeBodyWrite` | Before converter writes body on matching path | Suitable for modifying body/headers if uncommitted; does not replace choosing business status upfront |
| `@ExceptionHandler` / `@RestControllerAdvice` | When Spring MVC resolves exceptions inside `DispatcherServlet` | Can build an error response if uncommitted |
| `StreamingResponseBody`, `SseEmitter` | Content continues streaming after handler returns | May commit once streaming starts; do not set late headers |

Example filter intending to add a correlation header:

~~~java
@Component
class CorrelationHeaderFilter extends OncePerRequestFilter {
    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        response.setHeader("X-Correlation-Id", "demo-req");
        chain.doFilter(request, response);
    }
}
~~~

This is a fragment in a Servlet Spring Boot project with imports `jakarta.servlet.*`, `jakarta.servlet.http.*`, `org.springframework.stereotype.Component`, and `org.springframework.web.filter.OncePerRequestFilter`.

Never put mandatory headers inside `finally` after `chain.doFilter`, because the controller or view may have already flushed. With Servlet async dispatches, filters and interceptors may run again under separate rules; `AsyncHandlerInterceptor.afterConcurrentHandlingStarted` participates when switching to async mode. Whether callbacks fire again depends on registration and dispatcher types, so test against your target runtime.

## 8. When an Exception Occurs Before Commit

For instance, if a service throws `OrderNotFoundException` before the response writes any body, an `@ExceptionHandler` can produce a 404/Problem Details response:

~~~java
@RestControllerAdvice
class ApiErrorHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    ResponseEntity<ProblemDetail> notFound(OrderNotFoundException ex) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.NOT_FOUND,
                "Order not found.");
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(problem);
    }
}
~~~

This snippet is illustrative and needs the corresponding exception/imports in your project. Spring MVC uses `HandlerExceptionResolver`s to resolve exceptions. While the response remains uncommitted, the framework can apply a different status/headers and serialize a consistent error body. Certain Servlet errors are also forwarded by the container to Spring Boot's error page mechanism.

However, not every exception thrown from a **filter outside `DispatcherServlet`** is automatically handled by `@RestControllerAdvice`. Those can take separate filter/security/Servlet container error paths. Choose the right layer to own error handling.

## 9. When an Exception Occurs After Commit

Suppose the server has already sent HTTP 200 and the beginning of a file or JSON payload:

~~~text
HTTP/1.1 200 OK
Content-Type: application/json

{"items":[{"id":1},
~~~

Then the serializer or streaming service throws an error. The HTTP status and headers have already been transmitted. At this point:
- You cannot turn `200` into `500` or `400` to signal failure.
- You cannot replace a half-written JSON response with a clean Problem Details body.
- Calling `sendError(500)` or `reset()` can cause the Servlet API to throw `IllegalStateException`.
- `@ExceptionHandler` cannot undo bytes already sent; Spring MVC may log that the response was already committed or terminate the stream/connection.
- Clients may receive a truncated body; if framing remains valid, clients need mechanisms to verify payload completeness.

**Solution:** validate preconditions and determine status before starting to stream; minimize foreseeable errors; handle mid-stream failures using protocol-appropriate mechanisms or close the connection and log. Never try to "send a brand-new error JSON" after partial JSON has left the server.

With Server-Sent Events (SSE), an application can define a business error event while the stream is still open, though **the initial HTTP status remains unchanged**. That is an application/content-level error signal, not changing the status of a committed response.

## 10. Streaming, Async, and File Downloads

Spring MVC offers several ways to send content over time:
- `StreamingResponseBody`: callback writing to `OutputStream`, useful for files or large payloads.
- `ResponseBodyEmitter`: emits multiple objects incrementally.
- `SseEmitter`: supports SSE, pushing events over a long-lived connection.
- `Callable` or `DeferredResult`: lets request work complete asynchronously, then Spring MVC dispatches again to finalize the response.

Across streaming mechanisms, **the exact commit point depends on the first write/flush, buffers, and container**. Do not assume commit happens merely when the controller constructs an `SseEmitter` or `StreamingResponseBody`. Set status, content type, download filename, and cache/security headers **before** emitting the first data.

Illustrative controller return-type example (fragment):

~~~java
@GetMapping(value = "/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
ResponseEntity<SseEmitter> events() {
    SseEmitter emitter = new SseEmitter();
    // Pass emitter to streaming manager to send events later.
    return ResponseEntity.ok()
            .header("Cache-Control", "no-cache")
            .body(emitter);
}
~~~

This snippet does not emit events or implement full emitter management yet; its purpose is to show setting status/headers before streaming. Production code must manage event delivery, timeouts, completion/error callbacks, and resource cleanup.

When sending files via `StreamingResponseBody`, decide 404/403/416, `Content-Disposition`, `Content-Type`, and byte ranges before opening the stream. If the data source fails unexpectedly mid-transfer, mark the transfer as failed and release resources rather than trying to change status after bytes were sent.

## 11. Runnable Example with Spring Boot 3.x, Java 17+

The following example demonstrates three paths:
1. Handler chooses status/headers before Spring MVC writes the body.
2. Handler calls `flushBuffer()` and observes that subsequent status/header changes **do not alter the committed response**.
3. An exception thrown before writing the body can still be mapped to status 400.

### 11.1. Project Setup

Create a Spring Boot 3.x Java 17+ project with `spring-boot-starter-web` (Servlet/Tomcat). With Maven you can use this complete `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>response-commit-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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
~~~

Place the Java file at `src/main/java/example/commit/ResponseCommitDemoApplication.java`:

~~~java
package example.commit;

import java.io.IOException;
import java.io.PrintWriter;
import java.util.Map;

import jakarta.servlet.http.HttpServletResponse;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ResponseCommitDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ResponseCommitDemoApplication.class, args);
    }
}

@RestController
class CommitController {

    @GetMapping(value = "/normal", produces = MediaType.TEXT_PLAIN_VALUE)
    ResponseEntity<String> normal() {
        return ResponseEntity.ok()
                .header("X-Stage", "before-body")
                .body("ok\n");
    }

    @GetMapping(value = "/flushed", produces = MediaType.TEXT_PLAIN_VALUE)
    void flushed(HttpServletResponse response) throws IOException {
        response.setStatus(HttpServletResponse.SC_OK);
        response.setContentType("text/plain;charset=UTF-8");
        response.setHeader("X-Stage", "before-flush");

        PrintWriter writer = response.getWriter();
        writer.write("first chunk\n");

        response.flushBuffer(); // status/headers are committed
        boolean committed = response.isCommitted();

        // FOR ILLUSTRATION ONLY: the next two calls do not modify what was already sent.
        response.setStatus(HttpServletResponse.SC_CONFLICT);
        response.setHeader("X-Stage", "after-flush");

        writer.write("committed=" + committed + "\n");
    }

    @GetMapping("/early-error")
    String earlyError() {
        throw new IllegalArgumentException("bad input");
    }

    @ExceptionHandler(IllegalArgumentException.class)
    ResponseEntity<Map<String, String>> onBadInput(
            IllegalArgumentException exception) {
        return ResponseEntity.badRequest()
                .header("X-Error-Source", "exception-handler")
                .body(Map.of("error", exception.getMessage()));
    }
}
~~~

The two calls changing status/header after `flushBuffer()` in `/flushed` exist solely to prove the Servlet limitation; never copy that pattern into production endpoints.

### 11.2. Run and Observe

Requires JDK 17+, Maven, and port 8080 available. In the project directory:

~~~bash
mvn spring-boot:run
~~~

In another terminal:

~~~bash
curl -i http://localhost:8080/normal
curl -i http://localhost:8080/flushed
curl -i http://localhost:8080/early-error
~~~

Key results (header order, `Date`, `Connection`, `Content-Length`, and chunking depend on the container):

| Endpoint | Actual HTTP status | Notable header | Expected body |
|---|---|---|---|
| `/normal` | 200 | `X-Stage: before-body` | `ok` and newline |
| `/flushed` | 200 | `X-Stage: before-flush` | Two lines: `first chunk` and `committed=true` |
| `/early-error` | 400 | `X-Error-Source: exception-handler` | JSON `{"error":"bad input"}` |

Explanation:
- `/normal` sets the response in `ResponseEntity` before the converter writes the body.
- `/flushed` forces commit via `flushBuffer()`; `isCommitted()` returns `true`. Subsequent calls setting 409 and header `after-flush` do not alter the HTTP headers already transmitted.
- `/early-error` throws an exception before writing a response, so the local `@ExceptionHandler` generates status 400 and error JSON.

There is no need to guess when the buffer fills automatically because the example calls `flushBuffer()` explicitly. Header/body outcomes are verified with a real HTTP client rather than relying on controller logs.

## 12. Testing Response Commit Behavior

### 12.1. Unit Testing with MockMvc

When testing Spring MVC, assert status, headers, and body together:

~~~java
mockMvc.perform(get("/normal"))
        .andExpect(status().isOk())
        .andExpect(header().string("X-Stage", "before-body"))
        .andExpect(content().string("ok\n"));

mockMvc.perform(get("/early-error"))
        .andExpect(status().isBadRequest())
        .andExpect(header().string(
                "X-Error-Source", "exception-handler"))
        .andExpect(jsonPath("$.error").value("bad input"));
~~~

This is a **fragment inside a test class configured with `MockMvc`**, requiring static imports from `MockMvcRequestBuilders` and `MockMvcResultMatchers`. `MockMvc` is great for verifying controller contracts, though it uses a mock servlet response and **does not replace** integration tests against an embedded container when verifying ports, buffers, flushes, and real wire behavior.

### 12.2. Test Scenarios You Should Cover

1. **Success status:** creating a resource returns 201/`Location`, or GET returns 200 with expected cache headers.
2. **Validation failure before writing body:** returns 400/422 per the API's error contract.
3. **Service exception before commit:** `@ExceptionHandler` yields consistent error status and body.
4. **Writer.flush or flushBuffer:** verify `isCommitted()` and confirm late headers have no effect.
5. **Large bodies exceeding buffer:** ensure the app never tries to set status/headers from late callbacks.
6. **Streaming failing after the first chunk:** client may see a partial response; logs, metrics, and cleanup behave accurately.
7. **Filters/interceptors:** mandatory headers appear even when controllers stream directly.
8. **Async dispatch:** verify filter mappings, timeouts, error dispatches, and lifecycle callbacks.
9. **Reverse proxy/CDN:** inspect both app-emitted headers and gateway-modified headers; distinguish where commit occurs.
10. **Client aborts request:** handle `IOException` on network writes as a closed connection and release resources properly.

## 13. Troubleshooting "Status/Header Was Set, But the Client Didn't See It"

Investigation checklist:

1. Capture the actual status/headers received by the client using `curl -i` or an HTTP trace. On HTTP/2, use tools showing headers and `:status`.
2. Search for all calls to `response.flushBuffer()`, `PrintWriter.flush()`, `ServletOutputStream.flush()`, `sendError`, `sendRedirect`, `getWriter`, and large streaming writes.
3. Check actual execution order across filters, interceptors, `ResponseBodyAdvice`, and controllers—especially code setting headers **after** `chain.doFilter`.
4. Check where status is set: `ResponseEntity`, `@ResponseStatus`, exception resolvers, security entry points, or container error handling.
5. Log `response.isCommitted()` right at the branch attempting to modify the response, without treating that check as a fix for already-sent state.
6. If streaming bodies, inspect response size, the first flush, and where output generation throws.
7. Check whether a proxy or load balancer strips or alters response headers downstream. A missing header at a proxy is not necessarily Spring MVC's fault.
8. For SSE or large downloads, design a content-level end-of-stream or error signal so clients can detect mid-stream failures.

For example, suppose a filter sets `response.setHeader("X-Audit", "done")` inside a `finally` block **after** `chain.doFilter`. When a controller serves a large file and flushes, that header disappears. Moving the header assignment before `chain.doFilter` usually solves the issue without touching buffer settings.

**Security note:** never log session cookies, access tokens, or sensitive data while debugging commit timing; correlation/request IDs and commit timestamps are normally enough.

## 14. Common Misconceptions

1. **"Returning from a controller means the response is committed."** Not necessarily; return-value handling, converters, views, and buffering still run.
2. **"Calling `writer.write` once definitely commits the response."** Not necessarily; bytes may still sit inside the buffer.
3. **"Until the whole body is sent, status can still be changed."** False: once status/headers are committed, they cannot be changed.
4. **"`setStatus(500)` after `flushBuffer` returns 500."** False: the client already received the earlier status.
5. **"Having `@ControllerAdvice` guarantees every error becomes clean JSON."** It cannot rewrite committed statuses/bodies; filter errors outside `DispatcherServlet` also take different paths.
6. **"Increasing buffer size indefinitely fixes it."** No: streaming, huge payloads, memory usage, and latency remain problematic.
7. **"`resetBuffer` works after commit."** False: the Servlet API throws `IllegalStateException`.
8. **"`setHeader` in a filter's `finally` always takes effect."** False: downstream code may already have flushed.
9. **"`ResponseBodyAdvice` is guaranteed to modify headers."** Only if the response is still uncommitted when the callback runs.
10. **"Half-written JSON can be switched mid-stream to Problem Details."** Unsafe once initial body bytes have left the server.
11. **"Every Spring MVC async handler commits immediately upon return."** Commit timing depends on body writers, flushes, buffering, and async lifecycle.
12. **"Reading `server.port` from `Environment` checks commit state."** That is a port setting; it says nothing about individual HTTP response states.

## 15. Endpoint and Middleware Design Checklist

- [ ] Success/failure status is decided before writing body data.
- [ ] `Content-Type`, cache, CORS, security, cookie, and correlation ID headers are set early enough.
- [ ] When using `ResponseEntity`, status/headers/body align with business logic without prior manual response writes.
- [ ] Filters set mandatory headers before `chain.doFilter`.
- [ ] `HandlerInterceptor.afterCompletion` is never used to change status/headers.
- [ ] Flush timing and response buffer limits are well understood.
- [ ] `reset()`, `resetBuffer()`, `sendError()`, and `sendRedirect()` are never called on committed responses.
- [ ] Pre-commit errors are mapped via `@ExceptionHandler` or appropriate error handling.
- [ ] Post-commit streaming errors have logging, cleanup, and protocol-level error signaling where supported.
- [ ] Verified with `MockMvc` and real HTTP requests against an embedded container where needed.
- [ ] Sensitive data is never leaked via headers, bodies, or logs during exception handling.

## 16. Key Takeaway

**The decisive boundary is when the Servlet container commits status and headers, not when the controller method returns.** Once committed, transmitted status and headers cannot be rewritten; you can only continue writing the body or handle low-level connection/stream errors. In Spring MVC, set status and headers in controllers/`ResponseEntity` or filters before writing the body, test streaming and error paths carefully, and use `isCommitted()` for diagnostics whenever handling responses manually.

## References

- Jakarta Servlet 6.0 API — `ServletResponse` (`flushBuffer`, `reset`, `resetBuffer`, `isCommitted`): https://jakarta.ee/specifications/servlet/6.0/apidocs/jakarta.servlet/jakarta/servlet/servletresponse
- Jakarta Servlet 6.0 API — `HttpServletResponse` (`sendError`, `sendRedirect`, status, headers): https://jakarta.ee/specifications/servlet/6.0/apidocs/jakarta.servlet/jakarta/servlet/http/httpservletresponse
- Spring Framework — Spring MVC Asynchronous Requests: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html
- Spring Framework — Spring MVC `@ResponseBody` and `HttpMessageConverter`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responsebody.html