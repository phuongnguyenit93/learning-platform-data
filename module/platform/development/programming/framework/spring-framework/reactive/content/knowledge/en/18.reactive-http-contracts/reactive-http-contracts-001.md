# Status, headers, cookies, and content type in Spring WebFlux

## 1. Goal: build the HTTP response contract correctly

An endpoint does more than return data. It also has to tell the client how the request was handled, which format the data is represented in, whether it can be cached, and which cookies the browser needs to store.

An HTTP response usually has three parts:

1. **Status line:** the HTTP version, status code, and reason phrase (for example, 201 Created).
2. **Headers:** metadata such as Content-Type, Location, Cache-Control, Set-Cookie, and ETag.
3. **Body:** the returned data, which can be JSON, text, a file, an event stream, or no body at all.

In Spring WebFlux, a controller can describe all three parts through **ResponseEntity**, or return data with **@ResponseBody/@RestController** so that Spring picks a message writer and writes the body. With asynchronous flows, the status/headers and the body can be produced at different times, so you need to pick the right return value type.

This lesson focuses on:

- Choosing a status code according to business and HTTP semantics.
- Setting response headers, Location, Cache-Control, ETag, and Content-Disposition.
- Creating, updating, and deleting cookies through Set-Cookie.
- Understanding Content-Type, Accept, consumes, produces, and content negotiation.
- Returning a synchronous body, Mono, Flux, and streaming responses.
- Testing the HTTP contract with WebTestClient without blocking the event loop.

## 2. Response structure and lifecycle

Example response:

```http
HTTP/1.1 201 Created
Content-Type: application/json
Location: /api/items/42
X-Request-Id: req-42
Cache-Control: no-store

{"id":"42","name":"Reactive"}
```

The status says a new resource was created. Location points to where the client can access that resource. Content-Type describes the body format. Cache-Control specifies whether the response may be cached.

WebFlux writes the response through components such as **HttpMessageWriter** and the server response abstraction. With an annotated controller:

- **@RestController** is a combination of @Controller and @ResponseBody.
- The method's return value is converted by the framework into the body if the return type is supported.
- **ResponseEntity** lets the controller control the status, headers, and body.
- Reactor Mono/Flux can represent data that arrives asynchronously.
- The server can commit the response when it starts writing the body. After the commit, the status and headers can no longer be changed as before.

For JSON, Spring usually picks a Jackson encoder/writer when the appropriate dependency is present. For text, byte arrays, resources, or SSE, the matching writer is chosen based on the body type and media type.

**Key principle:** finish choosing the status and headers before the body starts being written. This is especially important for a long Flux or a stream that never ends.

## 3. Choosing a status code based on the meaning of the request

Status codes fall into the groups 1xx, 2xx, 3xx, 4xx, and 5xx. An API should use a consistent set of statuses so that clients can decide whether to retry, display an error, or redirect.

### 3.1. Commonly used success statuses

| Status | Name | When to use | Body |
| --- | --- | --- | --- |
| 200 | OK | The request succeeded and has a result | Usually present |
| 201 | Created | A new resource was created | Usually has a representation; should have Location |
| 202 | Accepted | The work was received for later processing, completion is not yet confirmed | May contain job information |
| 204 | No Content | Processed successfully but no representation needs to be returned | None |
| 206 | Partial Content | Returns part of a representation in response to a Range request | Per the range rules |

Examples:

- GET an existing item: 200.
- POST creating a new item: 201, usually with Location.
- POST putting a task into a queue: 202, possibly with a URL to check its status.
- DELETE succeeds with no data to return: 204.
- The client sends Range and the server supports byte ranges: it may return 206.

Do not use 202 just because the method returns a Mono. 202 expresses that the **business work is not yet complete when the response is sent**, not that "the server processes asynchronously".

### 3.2. Client-side error statuses

| Status | Common situations |
| --- | --- |
| 400 Bad Request | The request has invalid syntax, is missing required input, or cannot be converted |
| 401 Unauthorized | Not authenticated; usually needs WWW-Authenticate depending on the auth mechanism |
| 403 Forbidden | Authenticated but not permitted |
| 404 Not Found | The resource does not exist or is not publicly exposed |
| 405 Method Not Allowed | The URL exists but the HTTP method is not supported; the response should include Allow |
| 406 Not Acceptable | The server cannot produce a representation compatible with Accept |
| 409 Conflict | Conflicts with the current state, for example creating a duplicate record |
| 412 Precondition Failed | A request condition such as If-Match is not met |
| 413 Content Too Large | The request body exceeds the limit |
| 415 Unsupported Media Type | The request Content-Type is not supported by the endpoint |
| 422 Unprocessable Content | The request syntax is valid but the content cannot be processed according to the API contract, if the API chooses to use this status |
| 429 Too Many Requests | The rate limit was exceeded; may include Retry-After |

### 3.3. Server-side statuses and special statuses

- **500 Internal Server Error:** an unexpected error in the application.
- **502 Bad Gateway:** a gateway/proxy received an invalid response from the upstream.
- **503 Service Unavailable:** the service is temporarily unavailable; may include Retry-After.
- **504 Gateway Timeout:** the gateway did not receive a response from the upstream in time.
- **304 Not Modified:** for a conditional GET/HEAD, indicates the representation has not changed; the response has no body.
- **301/302/303/307/308:** redirects; you need to understand the differences in method handling and permanence.

Do not return 200 for every situation and put the error code in the JSON. That loses the meaning of HTTP and causes caches, proxies, client retries, and monitoring to misinterpret the response.

### 3.4. 201 Created and Location

When creating a resource, the response should state the URL of the new resource explicitly:

```java
URI location = URI.create("/api/items/42");

return ResponseEntity.created(location)
        .body(new ItemResponse("42", "Reactive"));
```

The response has status 201, a Location header, and a JSON body. The URI can be a relative reference URI; the application can also build an absolute URI based on a trusted public base URL configuration. Do not build URLs yourself from untrusted forwarded headers.

### 3.5. 202 Accepted is not 201

Suppose an endpoint accepts a request to export a report, and a worker performs it afterward:

```java
return ResponseEntity.accepted()
        .location(URI.create("/api/jobs/job-42"))
        .body(new JobAccepted("job-42", "QUEUED"));
```

202 says that the request was received for processing, with no guarantee that the task will succeed. The client can call the job URL to check the status. When the work completes and the result resource is created, another endpoint can then return 200 or 201 depending on the contract.

### 3.6. 204 No Content has no body

```java
@DeleteMapping("/api/items/{id}")
public Mono<ResponseEntity<Void>> delete(
        @PathVariable String id) {

    return itemService.delete(id)
            .thenReturn(ResponseEntity.noContent().build());
}
```

This is an illustrative snippet, assuming itemService.delete returns Mono<Void>. A 204 response must not include a body. If the client needs to know that the resource was deleted or needs some other result, choose a response with a body instead of trying to write data after a 204.

## 4. ResponseEntity: the direct way to control status, headers, and body

**ResponseEntity<T>** wraps the status code, headers, and body. It is a readable choice when an endpoint needs to customize the response contract.

### 4.1. Synchronous ResponseEntity

```java
@GetMapping("/health")
public ResponseEntity<String> health() {
    return ResponseEntity.ok()
            .contentType(MediaType.TEXT_PLAIN)
            .header("X-Service-Version", "1.0")
            .body("UP");
}
```

In a @RestController, the String is the body written to the response. It is not a view name as in a @Controller that uses view resolution.

### 4.2. Mono<ResponseEntity<T>> when the status depends on an async result

```java
@GetMapping("/api/items/{id}")
public Mono<ResponseEntity<ItemResponse>> find(
        @PathVariable String id) {

    return itemService.findById(id)
            .map(item -> ResponseEntity.ok()
                    .header("X-Request-Id", "req-42")
                    .body(toResponse(item)))
            .defaultIfEmpty(ResponseEntity.notFound().build());
}
```

Here the status depends on the result of the publisher: if there is an item it is 200; if there is no item it is 404. The controller returns the publisher so that WebFlux manages it; there is no need to block or subscribe yourself.

### 4.3. Different reactive shapes

Spring WebFlux supports several ways of combining ResponseEntity and reactive types:

| Return type | When are the status/headers known? | When is the body known? |
| --- | --- | --- |
| ResponseEntity<T> | As soon as the method returns | Immediately |
| Mono<ResponseEntity<T>> | When the Mono emits the ResponseEntity | At the same time as the ResponseEntity |
| ResponseEntity<Mono<T>> | As soon as the method returns | Later, when the Mono emits data |
| ResponseEntity<Flux<T>> | As soon as the method returns | Later, as the Flux emits data |
| Mono<ResponseEntity<Flux<T>>> | When the Mono emits the ResponseEntity | The Flux body continues to emit afterward |

Choose according to your needs:

- Use **Mono<ResponseEntity<T>>** when you need to read data asynchronously and then decide the status/header/body.
- Use **ResponseEntity<Flux<T>>** when the status/headers can be determined immediately but the body is a stream.
- Use **Mono<ResponseEntity<Flux<T>>>** when the response metadata also has to be obtained asynchronously before the stream starts.
- Do not nest Mono/Flux in multiple layers just to be "more reactive"; choose the simplest structure that correctly expresses the lifecycle.

Example of ResponseEntity<Flux<T>>:

```java
@GetMapping(value = "/api/numbers",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public ResponseEntity<Flux<ServerSentEvent<Integer>>> numbers() {
    Flux<ServerSentEvent<Integer>> body = Flux.range(1, 5)
            .map(value -> ServerSentEvent.builder(value)
                    .event("number")
                    .build());

    return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(body);
}
```

Status 200 and Cache-Control are determined immediately; the body is written as the Flux emits events.

### 4.4. When to use @ResponseStatus?

If the status is fixed, you can use the annotation:

```java
@PostMapping("/api/notifications")
@ResponseStatus(HttpStatus.CREATED)
public Mono<NotificationResponse> create(
        @RequestBody NotificationRequest request) {

    return notificationService.create(request);
}
```

@ResponseStatus is suitable for a static status. If the status or headers change depending on the result, use ResponseEntity. Avoid declaring a fixed status in the annotation and then also trying to change the status through several different mechanisms without a clear reason.

## 5. Adding and reading response headers

### 5.1. Headers are the response's metadata

Some common headers:

| Header | Meaning |
| --- | --- |
| Content-Type | The media type of the response body |
| Content-Length | The body size in bytes, if known |
| Location | The URL of the new resource or the redirect target |
| Cache-Control | The caching policy |
| ETag | The validator of the representation |
| Last-Modified | The time the representation was modified |
| Vary | The request headers that affect the choice of representation/cache key |
| Content-Disposition | Whether to display inline or download as an attachment |
| Content-Language | The language of the representation |
| Retry-After | How long the client should wait before retrying |
| WWW-Authenticate | The authentication challenge |
| Allow | The HTTP methods supported for the resource |
| X-Request-Id | A correlation ID by application convention |

Some headers are HTTP standards, while some are internal conventions. For custom headers, use an appropriately namespaced name and document the contract clearly for clients.

### 5.2. Setting headers with ResponseEntity

```java
return ResponseEntity.ok()
        .header("X-Request-Id", requestId)
        .header("X-Api-Version", "v1")
        .contentType(MediaType.APPLICATION_JSON)
        .body(response);
```

You can add multiple values for the same header. You need to understand whether that header allows multiple field values; not every header can be arbitrarily joined with commas.

### 5.3. Use HttpHeaders when you need many operations

```java
HttpHeaders headers = new HttpHeaders();
headers.setContentType(MediaType.APPLICATION_JSON);
headers.set("X-Request-Id", "req-42");
headers.setCacheControl(CacheControl.noStore());

return ResponseEntity
        .status(HttpStatus.OK)
        .headers(headers)
        .body(response);
```

HttpHeaders provides helpers for common headers, reducing typos and value-handling errors. In code that needs multiple Set-Cookie headers, use add instead of set to keep each header separate.

### 5.4. Do not set Content-Length yourself for streams

For a small body, the framework/server can usually determine the size or choose a suitable transfer mechanism. For a Flux, SSE, or a stream whose length is not known in advance, do not set Content-Length yourself unless you calculate the exact number of bytes. A wrong value can make the client read incomplete data or wait forever.

Do not assume every response uses chunked transfer encoding; the transfer method depends on the HTTP version and the server connector. Let the server manage framing unless the application has a special requirement.

### 5.5. Content-Disposition for file downloads

When returning a file, you can ask the browser to download it with a suggested name:

```java
ContentDisposition disposition = ContentDisposition.attachment()
        .filename("report.csv", StandardCharsets.UTF_8)
        .build();

return ResponseEntity.ok()
        .contentType(MediaType.parseMediaType("text/csv"))
        .header(HttpHeaders.CONTENT_DISPOSITION,
                disposition.toString())
        .body(csvBytes);
```

The file name should be generated or validated from trusted data. Do not directly concatenate an arbitrary client-supplied file name into a header; avoid control characters and header injection. For large files, consider returning a Resource or a stream instead of keeping the whole byte array in the heap.

## 6. Setting and managing cookies in the response

### 6.1. Cookies are sent with Set-Cookie

When the server wants the browser to store a cookie, the response uses the **Set-Cookie** header:

```http
HTTP/1.1 200 OK
Set-Cookie: theme=dark; Path=/; Max-Age=86400; SameSite=Lax
Content-Type: text/plain

Preference saved
```

The client sends the cookie back in the request Cookie header on requests that match the browser's domain, path, expiry, and policy. The request Cookie header carries only name/value pairs; attributes such as Secure, HttpOnly, and SameSite are policies the server sets through Set-Cookie, not metadata the browser sends back.

### 6.2. Using ResponseCookie

Spring provides **ResponseCookie** to build a structured Set-Cookie:

```java
ResponseCookie sessionCookie = ResponseCookie
        .from("session", "opaque-session-id")
        .httpOnly(true)
        .secure(true)
        .sameSite("Lax")
        .path("/")
        .maxAge(Duration.ofHours(8))
        .build();

return ResponseEntity.ok()
        .header(HttpHeaders.SET_COOKIE, sessionCookie.toString())
        .contentType(MediaType.TEXT_PLAIN)
        .body("Session cookie issued");
```

ResponseCookie helps express cookie attributes clearly and builds a valid header string. The example uses a fake session value for illustration; a real application must use a random, hard-to-guess session identifier that is managed on the server side, and must not log the value.

### 6.3. Important cookie attributes

| Attribute | Meaning | Notes |
| --- | --- | --- |
| Path | Limits the path for which the browser sends the cookie | Path=/ applies broadly within the host |
| Domain | The host/domain that receives the cookie | Do not widen the domain unless necessary |
| Max-Age | Lifetime in seconds | 0 or a negative value can be used to delete, depending on the API |
| Expires | The expiration time | Max-Age usually takes precedence when both are present |
| Secure | Sent only over a secure connection, per the browser | Production should use HTTPS |
| HttpOnly | Browser-side JavaScript cannot read the cookie through the normal API | The server can still read the cookie |
| SameSite | Controls some cross-site cookie-sending cases | Lax, Strict, or None |
| Partitioned | A partitioned cookie in browsers that support it | Use only when there is a specific compatibility requirement |

If SameSite=None, modern browsers usually require Secure. Check the behavior of your target browsers and the domain/subdomain policy.

### 6.4. Creating multiple cookies in the same response

Each cookie should be sent in its own Set-Cookie header. **Do not join multiple cookies into one comma-separated string**, because Set-Cookie has its own rules and Expires can contain a comma.

```java
ResponseCookie session = ResponseCookie.from(
                "session", "opaque-session-id")
        .httpOnly(true)
        .secure(true)
        .sameSite("Lax")
        .path("/")
        .maxAge(Duration.ofHours(8))
        .build();

ResponseCookie theme = ResponseCookie.from("theme", "dark")
        .secure(true)
        .sameSite("Lax")
        .path("/")
        .maxAge(Duration.ofDays(30))
        .build();

return ResponseEntity.ok()
        .headers(headers -> {
            headers.add(HttpHeaders.SET_COOKIE, session.toString());
            headers.add(HttpHeaders.SET_COOKIE, theme.toString());
        })
        .body("Cookies issued");
```

Use headers.add for each cookie. If you use headers.set several times with the same key, the earlier value may be replaced.

### 6.5. Deleting a cookie

To make the browser delete a cookie, send a Set-Cookie with the same name and the matching Path/Domain scope, setting Max-Age to 0:

```java
ResponseCookie expired = ResponseCookie.from("session", "")
        .httpOnly(true)
        .secure(true)
        .sameSite("Lax")
        .path("/")
        .maxAge(Duration.ZERO)
        .build();

return ResponseEntity.noContent()
        .header(HttpHeaders.SET_COOKIE, expired.toString())
        .build();
```

If the cookie was originally created with a specific Path or Domain, you must send the expired cookie with the matching scope. Sending only the same name with a different Path/Domain may create a different cookie without deleting the old one.

Deleting the cookie in the browser also does not replace revoking the session on the server side. On logout, the server needs to invalidate the session/token according to the security contract, and then send the expired cookie.

### 6.6. Session cookie security

For cookies used for authentication:

- Use Secure on HTTPS.
- Use HttpOnly to reduce the risk of JavaScript reading the session identifier.
- Choose SameSite according to the login flow and cross-site needs.
- Set Path/Domain to the smallest scope necessary.
- Use a Max-Age/Expires that fits the session policy.
- Rotate the session ID on login or when privileges change.
- Protect state-changing operations with an appropriate CSRF defense.
- Do not write the session cookie to logs, telemetry, or error responses.

SameSite is one layer of protection, not the only CSRF solution for every architecture. If authentication relies on cookies that the browser sends automatically, evaluate CSRF, CORS, and cross-site flows separately.

## 7. Content-Type, Accept, and content negotiation

Three concepts are often confused:

- **Request Content-Type:** which format the body the client is sending is in.
- **Request Accept:** which format the client wants to receive the response in.
- **Response Content-Type:** which format the server actually returned the body in.

Example:

```http
POST /api/items HTTP/1.1
Content-Type: application/json
Accept: application/json

{"name":"Reactive"}
```

The client sends JSON and expects to receive JSON. The server can choose a suitable handler/encoder or reject the request if the endpoint does not support that media type.

### 7.1. consumes: checking the request body's media type

```java
@PostMapping(
        path = "/api/items",
        consumes = MediaType.APPLICATION_JSON_VALUE)
public Mono<ItemResponse> create(
        @RequestBody Mono<CreateItemRequest> request) {
    // ...
}
```

The consumes attribute restricts the accepted request Content-Type. If the client sends text/plain while the endpoint only consumes application/json, Spring usually returns 415 Unsupported Media Type.

consumes is appropriate when the endpoint has a clear body contract. Do not declare consumes too broadly if the controller understands only one format.

### 7.2. produces: choosing the response's media type

```java
@GetMapping(
        path = "/api/items/{id}",
        produces = MediaType.APPLICATION_JSON_VALUE)
public Mono<ItemResponse> find(@PathVariable String id) {
    // ...
}
```

produces declares the representations the handler can produce. Spring matches it against the client's Accept header. If the client accepts only text/plain while the endpoint only produces application/json, the mapping does not match and usually returns 406 Not Acceptable.

You can declare several media types if the endpoint genuinely supports several representations:

```java
@GetMapping(
        path = "/api/export",
        produces = {
                MediaType.APPLICATION_JSON_VALUE,
                MediaType.TEXT_PLAIN_VALUE
        })
public Mono<?> export() {
    // ...
}
```

If the same URL has different handlers by media type, Spring can choose the handler that matches Accept. You need to test each variant explicitly to prevent an endpoint from inadvertently returning a format the client did not request.

### 7.3. Accept can contain multiple media types and quality values

A client can send:

```http
Accept: application/json, text/plain;q=0.8, */*;q=0.1
```

q is the quality factor that expresses priority. Content negotiation considers the media types the client accepts and the media types the server can write. A wildcard such as */* allows many types. Do not parse Accept yourself by splitting the string; use Spring's mechanisms and MediaType.

### 7.4. Response Content-Type

When you need to specify it explicitly:

```java
return ResponseEntity.ok()
        .contentType(MediaType.APPLICATION_JSON)
        .body(response);
```

If the controller uses @RestController and the body is an object, the message writer usually chooses a suitable media type based on Accept and the available codecs. ResponseEntity.contentType lets you declare it more explicitly. Avoid assigning a JSON Content-Type to a body that is plain text or non-JSON bytes.

### 7.5. The 406 and 415 errors are different

| Status | Cause | Related header |
| --- | --- | --- |
| 406 Not Acceptable | The server has no response representation matching Accept | Accept |
| 415 Unsupported Media Type | The server does not support the format of the request body that was sent | Content-Type |
| 400 Bad Request | The body has invalid syntax or the input cannot be bound/converted | May relate to the body/query/header |

Examples:

- POST JSON but the endpoint only consumes text/plain: 415.
- GET on an endpoint that produces JSON but the client sends Accept text/plain: 406.
- POST JSON that is missing a bracket or has a wrongly typed field: usually 400.

Do not handle 406/415 by arbitrarily changing the response Content-Type; fix the mapping or the request contract.

## 8. Common media types in WebFlux

| Media type | Use case |
| --- | --- |
| application/json | JSON object/array |
| application/problem+json | HTTP Problem Details |
| text/plain | Simple text |
| text/html | HTML |
| text/csv | CSV |
| application/octet-stream | Generic binary data |
| application/pdf | PDF |
| multipart/form-data | Multi-part upload |
| text/event-stream | Server-Sent Events |
| application/x-www-form-urlencoded | Form URL encoded |

Spring uses codecs/message writers to encode the body. If the media type or object type is not supported by a configured writer, the response may fail when written. For a custom format, you can register a custom encoder/writer through the WebFlux configuration.

**JSON does not automatically mean streaming.** A Flux of objects may be handled as a JSON collection depending on the media type and writer. If you need to send events continuously, declare a streaming media type such as text/event-stream and use a suitable body type.

## 9. Streaming responses and the commit point

### 9.1. Server-Sent Events

Example SSE endpoint:

```java
@GetMapping(
        value = "/api/events",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<ServerSentEvent<String>> events() {
    return Flux.interval(Duration.ofSeconds(1))
            .map(sequence -> ServerSentEvent.<String>builder()
                    .id(Long.toString(sequence))
                    .event("heartbeat")
                    .data("tick-" + sequence)
                    .build());
}
```

The browser/client receives events over time. Each event can contain an id, an event name, and data. With an infinite stream, the server does not wait for the whole Flux to complete before returning the body.

### 9.2. Headers must be set before the stream writes data

Once the response has started being sent:

- The status is already committed.
- The headers are already committed.
- You can no longer change Content-Type or Set-Cookie.
- If the Flux errors midway through the stream, the server cannot replace the already-sent response with a new HTTP error JSON.
- The client may receive an interrupted stream or an error at the protocol layer.

So determine the status, content type, cache policy, CORS, and cookies before emitting the first element. With SSE, if you need to report an application-level error after the stream has started, design a separate event/error protocol and make sure the client understands it.

### 9.3. Do not block to wait for the stream to complete

Do not use collectList().block() in a controller just to build a response. If the API needs a finite JSON array, you can return Flux<T> and let the framework write it according to the media type contract; if you need to compute the whole list to decide the status/header, compose with collectList() in the reactive chain and then return Mono<ResponseEntity<List<T>>>.

Example:

```java
return itemService.findAll()
        .collectList()
        .map(items -> ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(items));
```

collectList keeps the elements in memory, so use it only when the result set is reasonably bounded. For millions of rows or long-running data, streaming may be more appropriate.

## 10. HTTP caching: Cache-Control, ETag, and Last-Modified

### 10.1. Cache-Control

Cache-Control tells browsers/proxies how long and in what scope they may store the response:

```java
return ResponseEntity.ok()
        .cacheControl(CacheControl.maxAge(30, TimeUnit.SECONDS)
                .cachePrivate())
        .body(response);
```

Some common directives:

- public: a shared cache can store the response if other conditions allow.
- private: only the user's/browser's private cache.
- no-cache: may be stored but must be revalidated before reuse.
- no-store: do not store the response.
- max-age: freshness time in seconds.
- must-revalidate: once stale, it must be revalidated before use.

For a response containing personal information or a session, do not enable public caching just to improve performance. Choose a policy according to the sensitivity and shareability of the data.

### 10.2. ETag

ETag is the validator of the representation. When the content has not changed, the client can send If-None-Match and the server returns 304 Not Modified with no body.

```java
@GetMapping("/api/books/{id}")
public ResponseEntity<BookResponse> book(
        @PathVariable String id) {

    BookResponse book = bookService.find(id);
    return ResponseEntity.ok()
            .cacheControl(CacheControl.maxAge(30, TimeUnit.SECONDS)
                    .cachePrivate())
            .eTag(book.version())
            .body(book);
}
```

This is a synchronous example to illustrate ResponseEntity and caching. In a reactive application, if bookService returns Mono<BookResponse>, you can map the result to the corresponding ResponseEntity. Spring supports comparing ETag/Last-Modified against conditional request headers and can return 304 when the representation has not changed.

The ETag must correctly represent the version of the representation. If the content differs by language, user, or content negotiation, the cache key and Vary/headers need to be designed correctly. Do not use the same ETag for two different representations.

### 10.3. Last-Modified and conditional requests

Last-Modified represents the time the resource changed. The client can send If-Modified-Since; if the resource has not changed since that time, the server returns 304.

With GET/HEAD, conditional requests usually help save bandwidth. For operations that modify a resource, If-Match/If-Unmodified-Since can be used to avoid overwriting a newer update; when the precondition is not met, 412 Precondition Failed is the appropriate status.

Do not return 304 yourself without checking the validator. A 304 response has no representation body and usually keeps the necessary cache metadata.

## 11. Writing the response yourself with ServerHttpResponse

In most controllers, ResponseEntity is easier to read and safer. When you need lower-level control, you can accept a ServerHttpResponse:

```java
@GetMapping("/api/raw")
public Mono<Void> raw(ServerHttpResponse response) {
    response.setStatusCode(HttpStatus.ACCEPTED);
    response.getHeaders().setContentType(MediaType.TEXT_PLAIN);
    response.getHeaders().set("X-Mode", "reactive");

    byte[] bytes = "queued".getBytes(StandardCharsets.UTF_8);
    DataBuffer buffer = response.bufferFactory().wrap(bytes);

    return response.writeWith(Mono.just(buffer));
}
```

This is a low-level example that requires importing ServerHttpResponse, DataBuffer, StandardCharsets, and Reactor Mono. The controller sets the status/headers itself and then returns a Mono<Void> representing the completion of writing the body.

When using this API:

- Set the status and headers before calling writeWith.
- Do not call subscribe manually.
- Do not hold on to a DataBuffer after handing it to the framework/server.
- With directly allocated or pooled buffers, follow the DataBuffer ownership/release rules.
- If you only need a regular status/header/body, prefer ResponseEntity.

Do not use both ResponseEntity and direct response writing in the same request if the two mechanisms compete for control of the response. Choose one primary approach.

## 12. Content-Type, headers, and cookies in a complete controller

The example below uses Java 17+ and Spring Boot 3.x with spring-boot-starter-webflux. The controller needs no database to illustrate the HTTP contract; the responses are built in memory.

### 12.1. Project structure

```text
http-contract-demo/
  src/
    main/
      java/demo/
        HttpContractApplication.java
        HttpContractController.java
    test/
      java/demo/
        HttpContractControllerTest.java
  build.gradle
```

Main dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

The project needs the Spring Boot Gradle plugin and a compatible dependency management. Let the BOM manage the versions of Spring Framework, Reactor, Jackson, and test support.

### 12.2. Application class

File src/main/java/demo/HttpContractApplication.java:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HttpContractApplication {

    public static void main(String[] args) {
        SpringApplication.run(HttpContractApplication.class, args);
    }
}
```

### 12.3. DTO

File src/main/java/demo/CreateItemRequest.java:

```java
package demo;

public record CreateItemRequest(String name) {
}
```

File src/main/java/demo/ItemResponse.java:

```java
package demo;

public record ItemResponse(String id, String name) {
}
```

### 12.4. Controller

File src/main/java/demo/HttpContractController.java:

```java
package demo;

import java.net.URI;
import java.time.Duration;

import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseCookie;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
public class HttpContractController {

    @GetMapping(
            value = "/api/items/{id}",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<ResponseEntity<ItemResponse>> find(
            @PathVariable String id) {

        ItemResponse item = new ItemResponse(id, "Reactive item");

        return Mono.just(ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .header("X-Request-Id", "req-42")
                .body(item));
    }

    @PostMapping(
            value = "/api/items",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<ResponseEntity<ItemResponse>> create(
            @RequestBody Mono<CreateItemRequest> request) {

        return request
                .map(body -> new ItemResponse("42", body.name()))
                .map(item -> ResponseEntity
                        .created(URI.create("/api/items/" + item.id()))
                        .contentType(MediaType.APPLICATION_JSON)
                        .body(item));
    }

    @DeleteMapping("/api/items/{id}")
    public Mono<ResponseEntity<Void>> delete(
            @PathVariable String id) {

        return Mono.just(ResponseEntity.noContent().build());
    }

    @GetMapping("/api/session")
    public ResponseEntity<String> issueSessionCookie() {
        ResponseCookie cookie = ResponseCookie
                .from("session", "demo-session-id")
                .httpOnly(true)
                .secure(true)
                .sameSite("Lax")
                .path("/")
                .maxAge(Duration.ofHours(8))
                .build();

        return ResponseEntity.ok()
                .header(HttpHeaders.SET_COOKIE, cookie.toString())
                .contentType(MediaType.TEXT_PLAIN)
                .body("Session cookie issued");
    }

    @GetMapping(
            value = "/api/plain",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public ResponseEntity<String> plain() {
        return ResponseEntity.ok()
                .contentType(MediaType.TEXT_PLAIN)
                .body("Hello WebFlux");
    }

    @GetMapping(
            value = "/api/events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<String>> events() {
        return Flux.interval(Duration.ofSeconds(1))
                .map(sequence -> ServerSentEvent.<String>builder()
                        .id(Long.toString(sequence))
                        .event("heartbeat")
                        .data("tick-" + sequence)
                        .build());
    }

    @GetMapping("/api/cache")
    public ResponseEntity<ItemResponse> cached() {
        ItemResponse item = new ItemResponse("42", "Cached item");

        return ResponseEntity.ok()
                .cacheControl(CacheControl.maxAge(
                        30, java.util.concurrent.TimeUnit.SECONDS)
                        .cachePrivate())
                .eTag("v1")
                .body(item);
    }

    @GetMapping("/api/accepted")
    public ResponseEntity<String> accepted() {
        return ResponseEntity.accepted()
                .location(URI.create("/api/jobs/job-42"))
                .body("Job queued");
    }
}
```

The controller demonstrates:

- GET item: 200, JSON, custom response header.
- POST item: receives a JSON body asynchronously and returns 201 along with Location.
- DELETE: 204 with no body.
- Session endpoint: Set-Cookie with HttpOnly, Secure, SameSite, and Max-Age.
- Plain endpoint: only produces text/plain.
- Events: an SSE stream with text/event-stream.
- Cache endpoint: Cache-Control and ETag.
- Accepted endpoint: 202 along with Location for a job.

The cookie in the example is only a demo value. Production must generate a secure session ID, validate the session on the server side, and enable Secure only on HTTPS.

### 12.5. Running the application

```bash
./gradlew bootRun
```

Call GET JSON:

```bash
curl -i -H "Accept: application/json"   http://localhost:8080/api/items/42
```

Important headers:

```text
HTTP/1.1 200 OK
Content-Type: application/json
X-Request-Id: req-42
```

Call POST to create a resource:

```bash
curl -i -X POST http://localhost:8080/api/items   -H "Content-Type: application/json"   -H "Accept: application/json"   -d '{"name":"Reactive"}'
```

The response has status 201 and Location /api/items/42; the body contains id and name.

Call DELETE:

```bash
curl -i -X DELETE http://localhost:8080/api/items/42
```

The response status is 204, with no body.

Receive the cookie:

```bash
curl -i http://localhost:8080/api/session
```

The response has a Set-Cookie starting with session=demo-session-id and the attributes Secure, HttpOnly, SameSite=Lax, Path, and Max-Age.

Call SSE:

```bash
curl -N http://localhost:8080/api/events
```

The client receives a heartbeat event every second. Stop the client with Ctrl+C; the server-side subscription may be cancelled when the disconnect is detected.

## 13. Testing the HTTP contract with WebTestClient

A test should verify the status, headers, cookies, body, and media type. Do not check only the JSON body.

File src/test/java/demo/HttpContractControllerTest.java:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@WebFluxTest(HttpContractController.class)
class HttpContractControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void getReturnsJsonStatusAndCustomHeader() {
        client.get()
                .uri("/api/items/42")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                    .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
                .expectHeader()
                    .valueEquals("X-Request-Id", "req-42")
                .expectBody()
                .jsonPath("$.id").isEqualTo("42")
                .jsonPath("$.name").isEqualTo("Reactive item");
    }

    @Test
    void createReturns201AndLocation() {
        client.post()
                .uri("/api/items")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .bodyValue(new CreateItemRequest("Reactive"))
                .exchange()
                .expectStatus().isCreated()
                .expectHeader()
                    .valueEquals(HttpHeaders.LOCATION, "/api/items/42")
                .expectHeader()
                    .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
                .expectBody()
                .jsonPath("$.id").isEqualTo("42")
                .jsonPath("$.name").isEqualTo("Reactive");
    }

    @Test
    void deleteReturns204WithoutBody() {
        client.delete()
                .uri("/api/items/42")
                .exchange()
                .expectStatus().isNoContent()
                .expectBody().isEmpty();
    }

    @Test
    void responseCookieHasSecurityAttributes() {
        client.get()
                .uri("/api/session")
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                    .valueMatches(HttpHeaders.SET_COOKIE, ".*HttpOnly.*")
                .expectHeader()
                    .valueMatches(HttpHeaders.SET_COOKIE, ".*Secure.*")
                .expectHeader()
                    .valueMatches(HttpHeaders.SET_COOKIE, ".*SameSite=Lax.*");
    }

    @Test
    void plainEndpointNegotiatesTextOnly() {
        client.get()
                .uri("/api/plain")
                .accept(MediaType.TEXT_PLAIN)
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                    .contentTypeCompatibleWith(MediaType.TEXT_PLAIN)
                .expectBody(String.class)
                .isEqualTo("Hello WebFlux");
    }

    @Test
    void unacceptableMediaTypeReturns406() {
        client.get()
                .uri("/api/plain")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isEqualTo(406);
    }

    @Test
    void unsupportedRequestContentTypeReturns415() {
        client.post()
                .uri("/api/items")
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("name=Reactive")
                .exchange()
                .expectStatus().isEqualTo(415);
    }
}
```

Run the tests:

```bash
./gradlew test
```

The spring-boot-starter-test dependency provides JUnit Jupiter and WebTestClient support. This test uses the WebFlux test slice and does not need to open a real HTTP port. If the project has Spring Security, you need to configure test security appropriately so that 401/403 statuses do not mask the controller's test results.

## 14. Common mistakes when building HTTP responses

| Mistake | Consequence | Correct approach |
| --- | --- | --- |
| Returning 200 for every result | Clients and monitoring cannot distinguish success from error | Choose the status according to HTTP and the business meaning |
| Creating a resource without a Location | The client has trouble finding the new resource | Return 201 along with an appropriate Location |
| Returning a body for 204/304 | Violates the semantics of a no-body status | Use a response without a body |
| Using 202 for every publisher | Confuses async execution with an accepted job | Use 202 only when the business processing is still pending |
| Calling block to learn the result before returning a ResponseEntity | Blocks the event loop | Use Mono<ResponseEntity<T>> |
| Calling subscribe in a controller | Detaches the work from the HTTP lifecycle | Return Mono/Flux so WebFlux manages it |
| Setting a Content-Type that doesn't match the body | The client decodes incorrectly or the writer fails | Choose the MediaType that matches the representation |
| Confusing Accept with Content-Type | Misusing 406/415 | Accept is the format you want to receive; Content-Type is the format of the body being sent |
| Not declaring produces/consumes explicitly | The mapping may accept/return things outside the contract | Declare the media type when the endpoint has restrictions |
| Joining multiple Set-Cookie values with commas | The cookie header may be parsed incorrectly | Add each Set-Cookie header separately |
| Using SameSite=None without Secure | The browser may reject the cookie | Configure Secure when using None |
| Deleting the cookie only in the browser | The server-side session may still be valid | Revoke the server-side session and send an expired cookie |
| Setting headers after the stream has started | The response is already committed and cannot be modified | Prepare the status/headers before the first element |
| Setting Content-Length yourself for a Flux | Wrong size; the client waits or truncates the body | Let the server manage framing for streams |
| Caching private data with public | May expose data between users | Choose private/no-store as appropriate |
| Using the same ETag for different representations | The cache returns the wrong content | The ETag must reflect the actual representation/version |
| Logging the session cookie/Authorization | Leaks credentials | Redact or completely omit sensitive values |
| Parsing Accept/Set-Cookie yourself with a simple split | Mishandles the header grammar | Use MediaType, HttpHeaders, and ResponseCookie |
| Using ServerHttpResponse and ResponseEntity at the same time | The two mechanisms may compete for control of the response | Choose one way of writing the response for each handler |

## 15. Process for designing a response contract

When adding an endpoint, answer in this order:

1. **What does a successful request mean?** Was a resource created, was a job merely accepted, was the update completed, or is there no content to return?
2. **Which status code is correct?** 200, 201, 202, 204, or another status?
3. **Which URL does the client need to know?** If a resource or job is created, consider Location.
4. **What is the representation?** JSON, text, a file, SSE, or binary?
5. **What constraints apply to Accept/Content-Type?** Declare produces/consumes if the endpoint supports only certain media types.
6. **Which headers are needed?** Cache-Control, ETag, Content-Language, Vary, Retry-After, Content-Disposition?
7. **Are there cookies?** Determine Path, Domain, Max-Age, Secure, HttpOnly, SameSite, and logout behavior.
8. **Is the body a single value or a stream?** Choose T, Mono<T>, Flux<T>, and ResponseEntity accordingly.
9. **Can the response commit before the stream ends?** Prepare the status/headers before emitting data.
10. **Is there blocking I/O?** Use a reactive client/driver or isolate the legacy blocking code; do not block the event loop.
11. **Test the whole HTTP contract:** status, headers, cookies, content type, body, 406/415, and no-content behavior.
12. **Check security/caching:** do not cache private data by mistake, do not log secrets, and do not trust untrusted forwarded headers.

## 16. Official references

- [Spring Framework – ResponseEntity in WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/responseentity.html): controlling the status, headers, and body; the ResponseEntity shapes combined with Mono/Flux.
- [Spring Framework – @ResponseBody in WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/responsebody.html): HttpMessageWriter, body serialization, and reactive return types.
- [Spring Framework – Return Types of WebFlux Controllers](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html): the return value types and streaming behavior.
- [Spring Framework – HTTP Caching in WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux/caching.html): Cache-Control, ETag, Last-Modified, and conditional requests.
- [Spring Framework – ResponseCookie Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/ResponseCookie.html): creating response cookies with security attributes and lifetimes.
- [Spring Framework – RequestMapping Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/bind/annotation/RequestMapping.html): consumes/produces and mapping conditions by media type.
- [Spring Framework – WebFlux Configuration](https://docs.spring.io/spring-framework/reference/web/webflux/config.html): configuring HTTP message codecs and writers.
- [RFC 9110 – HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): status codes, representation metadata, content negotiation, and HTTP headers.
- [RFC 6265 – HTTP State Management Mechanism](https://www.rfc-editor.org/rfc/rfc6265): cookie and Set-Cookie semantics.

## 17. Key takeaways

A WebFlux response has three parts that must be designed together: **the status says how the request was handled; the headers describe metadata and policy; the Content-Type says how the body is represented**.

Use ResponseEntity when you need to control the status/header/body, and choose the right reactive return type shape to decide whether the metadata is known before or after asynchronous processing. Use ResponseCookie to build Set-Cookie, add each cookie as a separate header, and protect the session with Secure, HttpOnly, SameSite, Path, and an appropriate lifetime. Use consumes for the request's Content-Type and produces to constrain the representation according to Accept, and test 406/415 explicitly. With SSE or a long Flux, finalize the status/headers before the stream commits; do not block or subscribe yourself in a controller. Test the status, headers, cookies, and media type as part of the API contract, not just the JSON body.
