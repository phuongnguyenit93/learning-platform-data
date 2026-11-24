# Reading Bodies with bodyToMono/bodyToFlux and Data Validation in Functional WebFlux

## 1. Problem: the HTTP body is a byte stream, not a trusted Java object

When a client sends a request to an API:

```http
POST /api/books HTTP/1.1
Host: localhost:8080
Content-Type: application/json

{
  "title": "WebFlux in practice",
  "contact": {"email": "reader@example.org"}
}
```

First, the server only receives **bytes**. To execute business logic, the application must decode JSON, construct a DTO, validate the data, and only then call a service or save to a database. Spring WebFlux functional endpoints (commonly called **WebFlux.fn**) provide two key methods on `ServerRequest`:

- **`bodyToMono(Class<T>)`:** reads/decodes the request body into a `Mono<T>`, suitable when the contract expects **a single object** or single value.
- **`bodyToFlux(Class<T>)`:** creates a `Flux<T>` of **multiple values** decoded from the body, suitable for representations with multi-element framing such as NDJSON.

Both rely on WebFlux's `HttpMessageReader`/`Decoder` system; they **do not** automatically verify that data satisfies Bean Validation or domain rules.

Specifically, in a **functional handler** you usually must invoke the validator **explicitly**, unlike the `@Valid @RequestBody` mechanism that Spring infrastructure applies to annotated controller parameters. Skipping this step allows JSON with blank fields to be deserialized into a DTO and reach the data store.

This lesson belongs to **Functional WebFlux**, targeting **Java 17+, Spring Framework 6.2.x, Spring Boot 3.5.x, and Reactor 3.7.x**, running WebFlux on Reactor Netty. The examples do not use Servlet MVC and do not mix `org.springframework.web.servlet.function` with `org.springframework.web.reactive.function.server`.

### After this lesson, you will be able to

1. Choose `bodyToMono` vs. `bodyToFlux` according to the HTTP content representation.
2. Recognize `ServerRequest.body(BodyExtractors.toMono/toFlux)` as the underlying equivalent of the convenience methods.
3. Use `jakarta.validation.Validator` or Spring `Validator` to validate before any side effects.
4. Distinguish **empty body**, **malformed JSON**, **valid JSON violating constraints**, **wrong `Content-Type`**, **oversized request**, and **business rule violations**.
5. Handle reactive errors selectively with `onErrorResume` by type, without turning every error into 400.
6. Understand per-record NDJSON streaming, backpressure, and mid-stream error handling.
7. Set up tests for valid and invalid requests with `WebTestClient`.
8. Control memory/cancellation, avoiding `collectList()` or `block()` on long streams.

## 2. Request body architecture in WebFlux.fn

```text
HTTP request
  |
  v
Reactor Netty -> ServerHttpRequest
  |
  v
Flux<DataBuffer>       (bytes / buffers)
  |
  v
ServerRequest
  |
  | bodyToMono(CreateBook.class)
  | bodyToFlux(ImportLine.class)
  | body(BodyExtractors.toMono(...))
  |
  v
HttpMessageReader + Decoder (selected by type and Content-Type)
  |
  +--> onError(DecodingException / WebFlux input errors)
  |
  v
Mono<DTO> or Flux<DTO>
  |
  v
Validator / business rules (must be called at the right place)
  |
  +--> onError(input validation)
  |
  v
Reactive service / repository
  |
  v
Mono<ServerResponse>
  |
  v
HttpMessageWriter -> HTTP status + headers + body
```

Components:

| Component | Responsibility |
| --- | --- |
| `RouterFunction<ServerResponse>` | Selects the route by method, path, and predicates |
| `HandlerFunction<ServerResponse>` | Receives `ServerRequest` and returns `Mono<ServerResponse>` |
| `ServerRequest` | Accesses headers, URI, query, path variables, and body |
| `HttpMessageReader` | Reads the HTTP body into one or more Java values |
| `Decoder<T>` | Decodes `DataBuffer`/bytes into type `T` |
| `Mono<T>` | Publisher with 0 or 1 value |
| `Flux<T>` | Publisher with 0 to many values |
| `jakarta.validation.Validator` | Evaluates Bean Validation constraints on an object |
| `ServerResponse` | Declares status, headers, and body, written when the response `Mono` is subscribed |

Unlike Spring MVC.fn, a WebFlux.fn handler **returns `Mono<ServerResponse>`**:

```java
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;
import reactor.core.publisher.Mono;

Mono<ServerResponse> handle(ServerRequest request) {
    return ServerResponse.ok().bodyValue("Hello");
}
```

The snippet above is a **method fragment** for a handler; `ServerResponse.ok().bodyValue(...)` produces a **`Mono` of `ServerResponse`**, not a synchronous `ServerResponse` as in MVC Servlet functional handlers.

## 3. `bodyToMono(Class<T>)`: a single object in the request

Basic syntax:

```java
Mono<CreateBook> body =
        request.bodyToMono(CreateBook.class);
```

Suitable for:

- A JSON object for a create/update command.
- A JSON scalar or string depending on media type/decoder.
- A metadata object requiring validation before writing data.
- A body sent once by the client, not an unbounded stream of records.

Example:

```java
Mono<ServerResponse> create(ServerRequest request) {
    return request.bodyToMono(CreateBook.class)
            .flatMap(command ->
                    ServerResponse.ok().bodyValue(command));
}
```

**This is only a deserialization fragment**, without validation, authorization, or persistence.

### 3.1. `Mono` is a publisher, not a ready-made DTO

Right after calling `request.bodyToMono(CreateBook.class)`, you hold an asynchronous computation description. The decoder and body bytes are consumed only when the WebFlux infrastructure subscribes to the pipeline. **Never** do:

```java
// Wrong in WebFlux request handling:
CreateBook command =
        request.bodyToMono(CreateBook.class).block();
```

Calling `block()` on the Reactor Netty event loop can stall processing, leading to poor throughput or unsupported blocking operation exceptions.

Also never subscribe manually and return a success response before work completes:

```java
// Wrong: side effect escapes the HTTP response lifecycle:
request.bodyToMono(CreateBook.class)
        .subscribe(this::save);

return ServerResponse.accepted().build();
```

If `save` fails, the HTTP response no longer reflects the outcome; errors and cancellation may be mishandled. **Compose the publisher and return the `Mono` directly to WebFlux.**

### 3.2. Empty body vs. JSON containing null

With `bodyToMono(T.class)`, **no value** can result in `Mono.empty()`. A truly empty body and the JSON literal `null` can yield decoder-dependent behavior; never assume every case produces a non-null object.

An API requiring a body should state it explicitly:

```java
Mono<CreateBook> required = request
        .bodyToMono(CreateBook.class)
        .switchIfEmpty(Mono.error(
                new IllegalArgumentException(
                        "Request body required")));
```

This fragment illustrates `switchIfEmpty`; production code should map the exception to **400 with a stable error code** rather than returning raw messages. Use `defaultIfEmpty(...)` only when the domain genuinely has a valid default; **never** synthesize a dummy DTO to bypass required input.

### 3.3. What if the body is a JSON array?

```http
Content-Type: application/json

[
  {"sku":"A-1","quantity":2},
  {"sku":"B-2","quantity":3}
]
```

There are at least two options:

- If you want **one aggregate object**: `bodyToMono(new ParameterizedTypeReference<List<ImportLine>>() {})`. Accumulates the list; bound memory for the total array.
- If you want multi-item processing: use `bodyToFlux(ImportLine.class)` when the reader supports decoding/streaming the representation; for a JSON array, how incremental decoding and buffering work depends on the codec.

**Prefer NDJSON** when the contract transmits an arbitrary number of separate records, one JSON object per line. Do not assume `Flux<T>` turns every body into optimal streaming automatically.

## 4. `bodyToFlux(Class<T>)`: multiple sequential elements

```java
Flux<ImportLine> items =
        request.bodyToFlux(ImportLine.class);
```

Suitable for **a stream of records** in a content representation with clear framing, for example:

```http
POST /api/books/import HTTP/1.1
Content-Type: application/x-ndjson

{"sku":"B-101","quantity":3}
{"sku":"B-102","quantity":5}
{"sku":"B-103","quantity":2}
```

`application/x-ndjson` (Newline Delimited JSON) means **each line is an independent JSON value**, unlike a single JSON array.

A handler can do:

```java
Mono<ServerResponse> importLines(ServerRequest request) {
    return request.bodyToFlux(ImportLine.class)
            .map(this::validateAndNormalize)
            .reduce(
                new ImportSummary(0, 0),
                (summary, line) ->
                    new ImportSummary(
                        summary.rows() + 1,
                        summary.quantity() + line.quantity()))
            .flatMap(total ->
                ServerResponse.ok().bodyValue(total));
}
```

This is a **fragment**, requiring the records, validator, and `validateAndNormalize` method. Using `reduce` keeps only two counters in memory rather than `collectList()` holding every record in RAM.

### 4.1. Flux supports backpressure, but that does not bound total memory automatically

- `Flux<T>` uses `request(n)` to coordinate **element demand** between publisher and subscriber.
- The decoder may still have to buffer until a JSON record is complete.
- `flatMap` has its own concurrency, prefetch, and internal queues.
- `collectList()` accumulates **every item** before emitting a response.
- A single huge item can still exceed `maxInMemorySize`.
- A multi-GB NDJSON stream of small records under the codec limit can still exceed the **total upload quota**.

Therefore, public import APIs must enforce **total byte limits, record counts, durations, rate limits, concurrency limits, and quotas**, not just per-record memory checks.

### 4.2. Ordering when validating and writing data

If lines must be processed in order:

```java
return request.bodyToFlux(ImportLine.class)
        .concatMap(line ->
                validate(line)
                    .then(repository.save(line)))
        .then(ServerResponse.noContent().build());
```

This is a **fragment**; `validate` is assumed to return `Mono<Void>` and `repository.save` is reactive. `concatMap` preserves source element order. **It does not promise all-or-nothing transactions**: if line 100 fails after 99 lines were saved, side effects 1–99 may already be committed. For atomic batch semantics, use staging, proper transaction logic, idempotency, or an independent import job.

`flatMap` processes concurrently and completion order can vary; choose based on business semantics, not speed alone.

## 5. `body(...)` and `BodyExtractors`: the general form

`bodyToMono` and `bodyToFlux` are shortcuts:

```java
Mono<CreateBook> a = request.bodyToMono(CreateBook.class);

Mono<CreateBook> b = request.body(
        BodyExtractors.toMono(CreateBook.class));

Flux<ImportLine> c = request.bodyToFlux(ImportLine.class);

Flux<ImportLine> d = request.body(
        BodyExtractors.toFlux(ImportLine.class));
```

This is a fragment requiring:

```java
import org.springframework.web.reactive.function.BodyExtractors;
```

`BodyExtractors` provides ways to read **raw `DataBuffer`, `Resource`, parts, and form/multipart** depending on media type. Use the specialized API when representations are complex rather than misusing `bodyToFlux(MyPojo.class)` for large files.

### 5.1. Generic types

`bodyToMono(Class<T>)` is convenient when `T` has no generic parameters. For `List<Book>` or `Map<String,List<Book>>`:

```java
Mono<List<ImportLine>> lines =
        request.bodyToMono(
            new ParameterizedTypeReference<
                List<ImportLine>>() {});
```

This is a fragment requiring `org.springframework.core.ParameterizedTypeReference` and `java.util.List`. The `ParameterizedTypeReference<T>` overload preserves the generic element type for Jackson/codecs; `List.class` erases the generic type in most cases.

**Do not use `bodyToMono(List.class)` and cast elements** to DTOs; without generic metadata, items are usually decoded as maps instead of your target record.

## 6. Bean Validation does not run automatically in functional endpoints

Suppose we have these DTOs:

```java
record Contact(
        @NotBlank @Email String email) {}

record CreateBook(
        @NotBlank @Size(min = 3, max = 80) String title,
        @NotNull @Valid Contact contact) {}
```

If the handler only writes:

```java
return request.bodyToMono(CreateBook.class)
        .flatMap(book -> repository.save(book));
```

**Validation does not run automatically** just because `@NotBlank` is on the record. WebFlux.fn has no `@Valid @RequestBody`-annotated method parameters like annotated controllers do. You must invoke Spring `Validator` or Jakarta Bean Validation **after decoding and before saving**.

### 6.1. Option A: Spring `Validator` + `BeanPropertyBindingResult`

This is the pattern shown in the official Spring WebFlux.fn documentation:

```java
import org.springframework.validation.BeanPropertyBindingResult;
import org.springframework.validation.Errors;
import org.springframework.validation.Validator;
import org.springframework.web.server.ServerWebInputException;

private final Validator springValidator;

private void validate(CreateBook book) {
    Errors errors =
            new BeanPropertyBindingResult(book, "createBook");
    springValidator.validate(book, errors);

    if (errors.hasErrors()) {
        // In practice, use a safe error code and message.
        throw new ServerWebInputException(
                "Book input validation failed");
    }
}
```

**This is a class fragment** requiring an initialized/injected `springValidator` field. A global `LocalValidatorFactoryBean` integrates Jakarta constraints; custom Spring `Validator`s also work.

- `BeanPropertyBindingResult` holds both field errors and object errors.
- Nested `@Valid` cascades work when the provider and Spring adapter are configured properly.
- Use `errors.getFieldErrors()` for field names, but **never return raw rejected values** to clients or logs.
- `ServerWebInputException` generally yields HTTP 400 semantics in WebFlux, though the exact JSON body depends on the app's error handler.

### 6.2. Option B: Jakarta `Validator` directly

In a project with `spring-boot-starter-validation`, inject `jakarta.validation.Validator`:

```java
import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validator;

private final Validator beanValidator;

private <T> T requireValid(T input) {
    Set<ConstraintViolation<T>> violations =
            beanValidator.validate(input);

    if (!violations.isEmpty()) {
        throw new InputProblem("INPUT_VALIDATION");
    }

    return input;
}
```

This is a fragment requiring `java.util.Set` and a custom `InputProblem` exception. It uses the standard Bean Validation API directly, fitting DTOs annotated with `jakarta.validation.constraints.*`. The runnable demo uses **Jakarta Validator** and builds error field paths safely.

**Key point:** both approaches must be **invoked explicitly**:

```java
Mono<CreateBook> validated =
        request.bodyToMono(CreateBook.class)
                .map(this::requireValid);
```

`map` does not run for `Mono.empty()` or when the decoder has already errored; therefore you need `switchIfEmpty` for required bodies and a separate path for decoder exceptions.

### 6.3. Cascaded validation and null

| Annotation | Meaning | Notes |
| --- | --- | --- |
| `@NotNull` | Must not be null | Allows whitespace strings |
| `@NotBlank` | Text containing non-whitespace | Fits titles/emails |
| `@Size(min,max)` | Bounds string/collection length | Does not forbid null on its own |
| `@Email` | Email format | Does not prove email ownership |
| `@Positive` | Number must be > 0 | Does not forbid null on its own |
| `@Valid` | Cascades into nested object | Does not fail if nested object is null |
| `@Validated(...)` | Selects validation groups in Spring | Use intentionally; not auto-applied to functional bodies |

For instance, `@NotNull @Valid Contact contact` performs **two duties**: requiring `contact` to be present and validating constraints inside it. With only `@Valid Contact contact`, `contact=null` normally produces no violation.

### 6.4. Applying validation across a `Flux`

```java
Flux<ImportLine> validLines =
        request.bodyToFlux(ImportLine.class)
                .index()
                .map(tuple -> {
                    long line = tuple.getT1() + 1;
                    return checkLine(
                            tuple.getT2(),
                            "lines[" + line + "].");
                });
```

`Flux#index()` emits **0-based** indices, so add 1 when reporting user-facing line numbers. `checkLine` in the full example returns the validated object; on failure it throws an exception, emitting `onError` and halting further processing. With NDJSON, blank lines, delimiters, and parser behavior must be tested rather than assuming the index always equals physical file line numbers including blank lines.

## 7. Distinguishing five types of input errors

A serious REST API must not collapse every exception into "invalid body":

| Scenario | Cause | Typical appropriate response |
| --- | --- | --- |
| Required body is empty | `Mono.empty()` / `Flux.empty()` | 400, `BODY_REQUIRED` |
| Body JSON syntax/type invalid | Decoder/Jackson error | 400, `MALFORMED_BODY` |
| Valid JSON violating `@NotBlank`, `@Positive` | Bean Validation | 400, `INPUT_VALIDATION` |
| `Content-Type` mismatches route/reader | Route predicate or unsupported media type | 415 or 404/other per routing/config; do not guess |
| Business conflict after validation | Domain service / DB unique constraint | 409 or 422 per contract |

Other errors must be handled by their proper mechanisms:

- **Body/record too large:** `DataBufferLimitException` can come from codecs; the API should have a 413 policy, though not every version defaults to 413 automatically.
- **Unacceptable response media type:** 406 when no suitable writer matches.
- **Too many requests:** 429 is quota/rate limiting, not Bean Validation.
- **Auth missing/forbidden:** 401/403 in the Spring Security layer.
- **DB/network outage:** 5xx or retry policy, **never** return 400.
- **Client disconnect:** cancellation/transport handling; do not assume a JSON error can always be sent.

### 7.1. Decoder errors and validation errors happen at different stages

Invalid JSON example:

```json
{"title":
```

There is no valid `CreateBook` to validate. The error may be `DecodingException` or wrapped by WebFlux in `ServerWebInputException`; inspect the exception chain for your Spring Framework/codec version.

Valid JSON with blank title example:

```json
{
  "title": " ",
  "contact": {"email":"reader@example.org"}
}
```

The decoder builds the DTO, and then **the validator you call** emits violations. Catching both in `onErrorResume(Throwable.class, ...)` to return 400 would hide DB errors, programming bugs, or OOMs.

### 7.2. Scoping `onErrorResume`

```java
return request.bodyToMono(CreateBook.class)
        .map(this::requireValid)
        .flatMap(this::save)
        .onErrorResume(InputProblem.class, this::badInput);
```

This handles only **`InputProblem`** exceptions. If the database fails, the error propagates to WebFlux's global error infrastructure instead of being disguised as an invalid request. This is the principle of classifying errors by **exception type and layer**.

If you add `onErrorResume(DecodingException.class, ...)`, map only decode errors to `MALFORMED_BODY`. If `ServerWebInputException` arrives from a reader, map input problems according to HTTP status/policy while keeping exception text private.

## 8. Boundaries of Content-Type, Accept, and route predicates

With a router:

```java
RouterFunctions.route()
        .POST(
            "/api/books",
            RequestPredicates.contentType(
                    MediaType.APPLICATION_JSON),
            handler::create)
        .build();
```

The request predicate matches only if `Content-Type` is compatible. A client sending XML may **fail to match the route**, yielding 404 or 415 depending on other handler mappings and error policies; do not assume Bean Validation catches it.

- `Content-Type` describes the **request representation**, e.g., JSON, NDJSON, or form.
- `Accept` describes **which representations the client accepts** in the response.
- `contentType(APPLICATION_JSON)` **does not** prove the body is actually valid JSON.
- `accept(APPLICATION_JSON)` does not turn output into JSON if the writer/DTO is incompatible.
- HTTP headers are client-supplied; validate both payload and business rules.
- If you must return a strict 415 instead of "no matching route", design fallback/error handling at the application or gateway and write tests.

**In WebFlux.fn, route predicates are evaluated in declaration order.** A broad route declared earlier can shadow a more specific one. Place `/api/books/import` before `/api/books/{id}` if both share the same HTTP method and could overlap.

## 9. Never read the body twice without intentional caching

An HTTP request body is **a stream**, not an arbitrary cached Java object.

Anti-pattern:

```java
// Do not do this:
request.bodyToMono(String.class)
        .doOnNext(System.out::println)
        .subscribe();

return request.bodyToMono(CreateBook.class)
        .flatMap(this::save);
```

You just subscribed manually (leaving the HTTP lifecycle) and then tried to consume the body a second time. The body may already be consumed and pooled buffers released, causing errors.

To inspect and validate, use **a single pipeline**:

```java
return request.bodyToMono(CreateBook.class)
        .doOnNext(dto ->
                metrics.markReceived())
        .map(this::requireValid)
        .flatMap(this::save);
```

Never log raw DTOs containing passwords, tokens, or emails/PII. For genuine request-body logging, use a properly designed buffer decorator with byte caps, retain/release lifecycle safety, redaction, and security review; do not re-read the request to log it.

### 9.1. BodyExtractors and buffer ownership

- Standard `bodyToMono`/`bodyToFlux` let HTTP codecs manage `DataBuffer` lifecycles.
- When reading `Flux<DataBuffer>` directly, understand pooled buffer retention, `DataBufferUtils.release`/`retain`, cancellation, and discard hooks.
- Never `collectList()` raw `DataBuffer`s without bounds.
- `DataBufferUtils.join(...)` aggregates bytes and offers a `maxByteCount` overload, yet is unsuitable for infinite/unbounded bodies.
- Never store raw `DataBuffer`s in downstream caches after the framework releases them; if handoff is required, define an explicit ownership contract.
- Spring WebFlux codecs honor Reactive Streams demand within implementation limits, while networks and proxies still have their own queues and buffers.

## 10. Validation must happen before side effects

Correct flow:

```text
decode body
  |
  v
validate DTO / field paths
  |
  +--- invalid ---> 400 JSON error, DO NOT save
  |
  v
validate business rules / authorization
  |
  v
repository.save / publish event
  |
  v
201 / 200 response
```

If you hit the database first and call `validate` afterward, a request with a blank title will already have created an invalid record. For multi-record streams, distinguish:

- **Per-record validation:** each record is validated before its individual processing.
- **Whole-batch validation:** checks cross-record duplicates, limits, and batch-wide invariants; may require staging, transactions, or snapshots.
- **Atomicity:** on large streams, you cannot promise rollback of all side effects with `onErrorResume` alone. Design DB transactions or job-based processing.
- **Ordering:** `concatMap` preserves source order when sequential side effects matter; `flatMap` runs concurrently and may reorder.
- **Database uniqueness:** Bean Validation does not replace DB unique constraints under concurrent requests.
- **Authorization:** field constraints do not replace user/tenant access checks.

### 10.1. Obtaining trusted user identity

Never put `ownerId` or `role` in an input DTO and trust it blindly. Extract the authenticated identity from the WebFlux security context and enforce permissions using reactive services. Validation checks format; authorization checks **who is allowed to do what**.

## 11. Returning errors: safe codes and field lists

Suggested error JSON:

```json
{
  "code": "INPUT_VALIDATION",
  "fields": ["title", "contact.email"]
}
```

For the second line of NDJSON:

```json
{
  "code": "INPUT_VALIDATION",
  "fields": ["lines[2].quantity"]
}
```

Field names and error codes are usually enough for frontend display or i18n. Never return:

```json
{
  "field": "password",
  "rejectedValue": "MySecret",
  "stackTrace": "java.lang.IllegalArgumentException..."
}
```

Exception messages and custom constraints can accidentally embed user input. Limit echoing; if human-readable messages are needed, select them from a safe lookup table rather than returning `violation.getInvalidValue()` directly.

### 11.1. `ProblemDetail` as an option

Spring 6.2 supports `ProblemDetail`/RFC 9457 for HTTP errors. With functional endpoints, you can build a `ServerResponse` with `application/problem+json` or use global exception infrastructure for error responses. Just **avoid mixing multiple uncoordinated error schemas**; choose one consistent error format per API version.

## 12. Runnable example: Spring Boot 3.5 + Java 17 WebFlux.fn

The demo covers both body styles completely:

1. **`POST /api/books`**: reads a single JSON object via `bodyToMono(CreateBook.class)`, validates nested `contact`, stores in-memory, returns **201 Created** + `Location`.
2. **`POST /api/books/import`**: reads multiple NDJSON records via `bodyToFlux(ImportLine.class)`; validates **each item** with its line index, reduces into count/quantity totals, returns 200.
3. **`GET /api/books/{id}`**: reads the saved resource to verify `Location`.
4. Safe error format for `BODY_REQUIRED`, `INPUT_VALIDATION`, `MALFORMED_BODY`, and `INVALID_ID`.
5. No `subscribe()`/`block()` inside handlers, and no blocking JDBC on the Netty event loop.

This is an **in-memory demo, not a production application**: data is lost on restart, and multiple nodes do not share the map. Batch import only sums totals without saving rows; there is no database, auth, global byte cap, or cross-record reconciliation.

### 12.1. Gradle dependencies

Use Spring Initializr to generate a **Spring Boot 3.5.x, Java 17, Spring Reactive Web, Validation** project. With Boot plugin, repositories, and Java toolchain already in `build.gradle`, dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-validation'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

This is a **`build.gradle` fragment**, not a complete Gradle file. Do not add `spring-boot-starter-web` just to use `RouterFunction`; Boot 3.x typically picks Servlet MVC when both MVC and WebFlux starters are present.

### 12.2. Complete Java source

Create **`src/main/java/demo/fnbody/FnBodyApplication.java`**:

```java
package demo.fnbody;

import java.net.URI;
import java.util.List;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Valid;
import jakarta.validation.Validator;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.codec.DecodingException;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;
import org.springframework.web.server.ServerWebInputException;

import reactor.core.publisher.Mono;

import static org.springframework.web.reactive.function.server.RequestPredicates.contentType;

@SpringBootApplication
public class FnBodyApplication {
    public static void main(String[] args) {
        SpringApplication.run(FnBodyApplication.class, args);
    }
}

record Contact(@NotBlank @Email String email) {}

record CreateBook(
        @NotBlank @Size(min = 3, max = 80) String title,
        @NotNull @Valid Contact contact) {}

record Book(long id, String title, String contactEmail) {}

record ImportLine(
        @NotBlank String sku,
        @Positive @Max(1000) int quantity) {}

record ImportSummary(long rows, long units) {}

record ApiError(String code, List<String> fields) {}

final class InputProblem extends RuntimeException {
    private final String code;
    private final List<String> fields;

    InputProblem(String code, List<String> fields) {
        super(code);
        this.code = code;
        this.fields = List.copyOf(fields);
    }

    String code() { return code; }
    List<String> fields() { return fields; }
}

@Component
class BookHandler {
    private final Validator validator;
    private final AtomicLong ids = new AtomicLong(2000);
    private final ConcurrentMap<Long, Book> books =
            new ConcurrentHashMap<>();

    BookHandler(Validator validator) {
        this.validator = validator;
    }

    private <T> T checked(T value, String prefix) {
        Set<ConstraintViolation<T>> violations =
                validator.validate(value);

        if (!violations.isEmpty()) {
            List<String> fields = violations.stream()
                    .map(v -> prefix + v.getPropertyPath())
                    .distinct()
                    .sorted()
                    .toList();

            throw new InputProblem(
                    "INPUT_VALIDATION", fields);
        }

        return value;
    }

    private Mono<ServerResponse> error(
            String code, List<String> fields) {
        return ServerResponse.badRequest()
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new ApiError(code, fields));
    }

    // Do not catch Throwable or database errors as 400.
    private Mono<ServerResponse> handleInputErrors(
            Mono<ServerResponse> publisher) {
        return publisher
                .onErrorResume(InputProblem.class,
                    problem -> error(
                        problem.code(), problem.fields()))
                .onErrorResume(DecodingException.class,
                    problem -> error(
                        "MALFORMED_BODY", List.of("body")))
                .onErrorResume(ServerWebInputException.class,
                    problem -> error(
                        "MALFORMED_BODY", List.of("body")));
    }

    Mono<ServerResponse> create(ServerRequest request) {
        Mono<ServerResponse> result =
                request.bodyToMono(CreateBook.class)
                    .switchIfEmpty(Mono.error(
                        new InputProblem(
                            "BODY_REQUIRED", List.of("body"))))
                    .map(value -> checked(value, ""))
                    .flatMap(value -> {
                        long id = ids.incrementAndGet();
                        Book created = new Book(
                            id, value.title().trim(),
                            value.contact().email());
                        books.put(id, created);

                        // Relative Location: demo runs at context root.
                        URI uri = URI.create("/api/books/" + id);

                        return ServerResponse.created(uri)
                                .contentType(
                                    MediaType.APPLICATION_JSON)
                                .bodyValue(created);
                    });

        return handleInputErrors(result);
    }

    Mono<ServerResponse> importLines(ServerRequest request) {
        Mono<ImportSummary> count =
                request.bodyToFlux(ImportLine.class)
                    .index()
                    .map(tuple -> {
                        long lineNumber = tuple.getT1() + 1;
                        return checked(
                                tuple.getT2(),
                                "lines[" + lineNumber + "].");
                    })
                    .reduce(
                        new ImportSummary(0L, 0L),
                        (acc, line) ->
                            new ImportSummary(
                                acc.rows() + 1,
                                acc.units() + line.quantity()));

        Mono<ServerResponse> result =
                count.flatMap(summary -> {
                    if (summary.rows() == 0) {
                        return error(
                            "BODY_REQUIRED", List.of("body"));
                    }
                    return ServerResponse.ok()
                            .contentType(MediaType.APPLICATION_JSON)
                            .bodyValue(summary);
                });

        return handleInputErrors(result);
    }

    Mono<ServerResponse> get(ServerRequest request) {
        long id;
        try {
            id = Long.parseLong(
                    request.pathVariable("id"));
        } catch (NumberFormatException badId) {
            return error(
                "INVALID_ID", List.of("id"));
        }

        return Mono.justOrEmpty(books.get(id))
                .flatMap(book ->
                    ServerResponse.ok()
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(book))
                .switchIfEmpty(
                    ServerResponse.notFound().build());
    }
}

@Configuration
class BookRoutes {
    @Bean
    RouterFunction<ServerResponse> bookRouter(
            BookHandler handler) {
        return RouterFunctions.route()
                .POST(
                    "/api/books/import",
                    contentType(MediaType.APPLICATION_NDJSON),
                    handler::importLines)
                .POST(
                    "/api/books",
                    contentType(MediaType.APPLICATION_JSON),
                    handler::create)
                .GET("/api/books/{id}", handler::get)
                .build();
    }
}
```

**Structural check:**

- One `public class FnBodyApplication`; records, `BookHandler`, and `BookRoutes` are package-private in the same package.
- `@Component BookHandler` is component-scanned by Spring Boot and injected with `jakarta.validation.Validator` configured by the validation starter.
- `@Configuration BookRoutes` registers a WebFlux.fn `RouterFunction<ServerResponse>` bean.
- `BookHandler` takes `ServerRequest` and returns `Mono<ServerResponse>` per WebFlux.fn.
- `checked` inspects typed `ConstraintViolation`s yet emits only **field paths**, never echoing inputs or constraint messages that might contain sensitive values.
- `create` generates the ID and stores in the map only **after** decoding and Bean Validation succeed.
- `importLines` validates each line before aggregating totals; it never materializes the full batch.
- `handleInputErrors` catches only specific input/domain validation exceptions and decoder-related exceptions; it never converts arbitrary bugs into 400.
- `GET /api/books/{id}` returns 404 when missing, `INVALID_ID` when the ID is non-numeric.
- `@Positive @Max(1000)` bounds quantity per line, but **does not** bound total line count or total quantity across the stream; production needs quotas and overflow handling.

### 12.3. Running and testing with curl

```bash
./gradlew bootRun
```

**Create a valid book:**

```bash
curl -i -X POST 'http://localhost:8080/api/books' \
  -H 'Content-Type: application/json' \
  -d '{"title":"Reactive Guide","contact":{"email":"reader@example.org"}}'
```

If this is the first create request, expected output:

```http
HTTP/1.1 201 Created
Location: /api/books/2001
Content-Type: application/json

{"id":2001,"title":"Reactive Guide","contactEmail":"reader@example.org"}
```

`Location` is a relative path fitting the demo's root context. In production behind a gateway or context prefix, generate links matching your public base path and `Host`/`Forwarded` trust policy.

**Missing body:**

```bash
curl -i -X POST 'http://localhost:8080/api/books' \
  -H 'Content-Type: application/json' \
  --data-binary ''
```

Expected 400:

```json
{"code":"BODY_REQUIRED","fields":["body"]}
```

**Valid JSON violating constraints:**

```bash
curl -i -X POST 'http://localhost:8080/api/books' \
  -H 'Content-Type: application/json' \
  -d '{"title":" ","contact":{"email":"not-an-email"}}'
```

Expected 400; fields are `title` and `contact.email` (via `@Valid` cascade):

```json
{"code":"INPUT_VALIDATION","fields":["contact.email","title"]}
```

Field names are sorted alphabetically in code, so ordering is deterministic in the demo (even though raw violation order from the provider before sorting is not guaranteed).

**Malformed JSON:**

```bash
curl -i -X POST 'http://localhost:8080/api/books' \
  -H 'Content-Type: application/json' \
  --data-binary '{"title":'
```

Expect the decoder error to map to `MALFORMED_BODY` when handled as `DecodingException` or `ServerWebInputException`:

```json
{"code":"MALFORMED_BODY","fields":["body"]}
```

If the infrastructure surfaces another exception class/adapter, verify via integration tests and add selective handlers; never map `Throwable` to 400.

**Valid NDJSON import:**

```bash
printf '%s\n' \
  '{"sku":"B-101","quantity":3}' \
  '{"sku":"B-102","quantity":5}' \
  '{"sku":"B-103","quantity":2}' \
  | curl -i -X POST 'http://localhost:8080/api/books/import' \
      -H 'Content-Type: application/x-ndjson' \
      --data-binary @-
```

Expected body:

```json
{"rows":3,"units":10}
```

**Invalid second line:**

```bash
printf '%s\n' \
  '{"sku":"B-101","quantity":3}' \
  '{"sku":"B-102","quantity":0}' \
  | curl -i -X POST 'http://localhost:8080/api/books/import' \
      -H 'Content-Type: application/x-ndjson' \
      --data-binary @-
```

Expected 400:

```json
{"code":"INPUT_VALIDATION","fields":["lines[2].quantity"]}
```

Because the import only aggregates totals without saving data, an invalid stream leaves no partial writes. **Do not treat this example as a transactional bulk import** when moving to a DB.

## 13. WebTestClient HTTP tests on RANDOM_PORT

Tests use `@SpringBootTest(webEnvironment=RANDOM_PORT)` to exercise WebFlux with real HTTP codecs and Netty rather than invoking handler methods directly.

Create **`src/test/java/demo/fnbody/FnBodyApplicationTests.java`**:

```java
package demo.fnbody;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.core.publisher.Flux;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class FnBodyApplicationTests {
    @Autowired
    WebTestClient client;

    @Test
    void createsBookFromOneJsonObject() {
        client.post()
                .uri("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("""
                    {
                      "title":"Reactive Guide",
                      "contact":{"email":"reader@example.org"}
                    }
                    """)
                .exchange()
                .expectStatus().isCreated()
                .expectHeader().exists("Location")
                .expectBody()
                .jsonPath("$.title")
                    .isEqualTo("Reactive Guide")
                .jsonPath("$.contactEmail")
                    .isEqualTo("reader@example.org");
    }

    @Test
    void emptyBodyIsRejectedBeforePersistence() {
        client.post()
                .uri("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code")
                    .isEqualTo("BODY_REQUIRED");
    }

    @Test
    void invalidFieldsProduceValidationError() {
        client.post()
                .uri("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("""
                    {
                      "title":" ",
                      "contact":{"email":"invalid-email"}
                    }
                    """)
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code")
                    .isEqualTo("INPUT_VALIDATION")
                .jsonPath("$.fields[0]")
                    .isEqualTo("contact.email")
                .jsonPath("$.fields[1]")
                    .isEqualTo("title");
    }

    @Test
    void missingNestedContactIsInvalid() {
        client.post()
                .uri("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("""
                    {"title":"Valid title"}
                    """)
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code")
                    .isEqualTo("INPUT_VALIDATION")
                .jsonPath("$.fields[0]")
                    .isEqualTo("contact");
    }

    @Test
    void malformedJsonIsNotBeanValidationError() {
        client.post()
                .uri("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("{\"title\":")
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code")
                    .isEqualTo("MALFORMED_BODY");
    }

    @Test
    void multiLineNdjsonIsReducedWithoutCollectList() {
        client.post()
                .uri("/api/books/import")
                .contentType(MediaType.APPLICATION_NDJSON)
                .body(Flux.just(
                    new ImportLine("B-101", 3),
                    new ImportLine("B-102", 5),
                    new ImportLine("B-103", 2)),
                    ImportLine.class)
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.rows").isEqualTo(3)
                .jsonPath("$.units").isEqualTo(10);
    }

    @Test
    void invalidNdjsonItemIdentifiesIndex() {
        client.post()
                .uri("/api/books/import")
                .contentType(MediaType.APPLICATION_NDJSON)
                .body(Flux.just(
                    new ImportLine("B-101", 3),
                    new ImportLine("B-102", 0)),
                    ImportLine.class)
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code")
                    .isEqualTo("INPUT_VALIDATION")
                .jsonPath("$.fields[0]")
                    .isEqualTo("lines[2].quantity");
    }

    @Test
    void emptyNdjsonIsRejected() {
        client.post()
                .uri("/api/books/import")
                .contentType(MediaType.APPLICATION_NDJSON)
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code")
                    .isEqualTo("BODY_REQUIRED");
    }

    @Test
    void malformedIdIsBadInput() {
        client.get()
                .uri("/api/books/not-a-number")
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code")
                    .isEqualTo("INVALID_ID");
    }

    @Test
    void missingBookReturns404() {
        client.get()
                .uri("/api/books/999999999")
                .exchange()
                .expectStatus().isNotFound();
    }
}
```

Run:

```bash
./gradlew test
```

**These ten tests are designed to pass** on Boot 3.5, Reactor Netty, and the Java 17 code above. This is **an expectation from source and API review, not proof that Gradle was executed**. In a real project, execute the tests and adjust wherever actual codec/config version behavior differs from assumptions.

Notable points:

- Tests `bodyToMono` with valid JSON, empty body, invalid/nested constraints, and malformed syntax.
- Tests `bodyToFlux` using an **NDJSON publisher** from `WebTestClient` and verifies totals and invalid line index.
- Tests that an empty body is not silently accepted as a successful 0-item batch.
- Tests path variables parsed manually by the functional handler, distinguishing bad IDs from missing resources.
- Tests creating new books use the ID sequence without asserting fixed IDs to avoid execution-order coupling.
- `@SpringBootTest(RANDOM_PORT)` exercises actual HTTP encoding/decoding, while unit tests for Java validators should be added separately if domain constraints are complex.

### 13.1. Seriously testing "never persist invalid input"

The demo does not expose the count of stored books. To prove invalid payloads never write to a production DB, use reactive repository spies/mocks or DB integration tests:

1. Send an invalid DTO.
2. Assert status 400.
3. Assert repository `save` **was never invoked**.
4. If wrapped in a transaction, assert rollback / unchanged DB rows.
5. Test concurrency/races, auth, and idempotency.

Do not merely assert status 400 and assume no side effects occurred; verify at the repository layer.

## 14. Empty body, malformed, validation, and domain errors: designing exception flow

Recommended order:

```text
bodyToMono / bodyToFlux
  |
  +--- Flux/Mono empty --> explicit BODY_REQUIRED
  |
  +--- decode error --> MALFORMED_BODY
  |
  v
validate each DTO
  |
  +--- violations --> INPUT_VALIDATION (400)
  |
  v
business & security checks
  |
  +--- permission --> 403
  +--- conflict --> 409
  |
  v
repository
  |
  +--- infrastructure failure --> 5xx
  |
  v
ServerResponse success
```

**Never map `DataBufferLimitException` to `MALFORMED_BODY` by default** if it arrives wrapped inside `ServerWebInputException`; certain input size-limit failures require 413 per product contract. The demo keeps the error handler concise for learning; production should inspect the cause chain, enforce payload caps at ingress/codecs, and test 413.

### 14.1. Why avoid raw exceptions in response bodies?

`DecodingException#getMessage()` can expose class names, parse positions, or payload fragments. `ConstraintViolation#getInvalidValue()` can contain secrets. Substitute safe **field names and error codes**, and log internal error details with controlled redaction at the app, gateway, or APM layer.

### 14.2. Once the response has committed

With a `bodyToFlux` request input, you might stream responses concurrently or per item. Once 200 and initial bytes are sent before an invalid line arrives, the HTTP status **cannot reliably switch to 400**. Either adopt explicit stream-error frames or complete validation before emitting success when batches are small and business logic demands an atomic reply.

In the demo, `reduce` awaits the entire input before producing the response, so an invalid line still yields 400 before the response commits. This is a **latency/aggregation trade-off**: low memory via `reduce`, at the cost of emitting the response only after the stream ends.

## 15. NDJSON, JSON arrays, and other choices

| Input representation | Typical appropriate reader | Trade-off |
| --- | --- | --- |
| `application/json`, single object | `bodyToMono(MyDto.class)` | Easy single-command validation; decoder may aggregate object |
| `application/json`, single array | `bodyToMono(ParameterizedTypeReference<List<Dto>>)` | Holds list in RAM; easy cross-item validation |
| `application/x-ndjson`, multi-line | `bodyToFlux(Dto.class)` | Per-record processing, clear framing |
| `text/plain`, single string | `bodyToMono(String.class)` | Watch charset and max bytes |
| `application/octet-stream`, large file | `body(BodyExtractors.toDataBuffers())` / `FilePart` | Raw byte ownership, quotas, and storage complexity |
| `application/x-www-form-urlencoded` | `ServerRequest.formData()` | Binds form map; invoke validation manually |
| `multipart/form-data` | `ServerRequest.multipartData()` | Files/parts plus separate disk/RAM/part limits |

`bodyToFlux<T>` is unsuitable for arbitrary file uploads; decoding bytes into DTOs requires an appropriate representation. `multipartData()` returns parsed part data and may spool files to disk; for very large files or part streaming, look at WebFlux 6.2 `PartEvent` APIs and manage buffers carefully.

### 15.1. Form data

```java
Mono<MultiValueMap<String, String>> form =
        request.formData();
```

This is a fragment; each client-supplied value must be parsed and validated—for instance, `Integer.parseInt` can throw `NumberFormatException`. Do not assume form maps trigger `@NotBlank` automatically in functional handlers.

### 15.2. Multipart

```java
Mono<MultiValueMap<String, Part>> parts =
        request.multipartData();
```

This is a fragment requiring `org.springframework.http.codec.multipart.Part`. For files, never trust `FilePart.filename()` as a filesystem path. When storing files, generate **server-controlled** paths and enforce authorization, size limits, storage isolation, MIME validation, and lifecycle cleanup; metadata Bean Validation does not scan for malware or inspect file contents.

## 16. Memory and byte-size limits matter more than DTO count

Independent limits:

| Limit | Layer affected | What it does not guarantee |
| --- | --- | --- |
| Codec `maxInMemorySize` | Bytes of one decoded/aggregated unit | Not a total request quota |
| Body max bytes | Gateway/server/app | Not business field validation |
| NDJSON max record length | Decoder/endpoint contract | Does not bound total batch size |
| `@Size(max=80)` | DTO field length (Java semantics) | Does not bound total JSON bytes |
| `take(maxRecords)` | Reactive items received downstream | Can cancel early; does not always block bytes already sent on transport |
| Database unique constraint | Duplicate persisted keys | Does not replace client validation |
| Rate/concurrency limit | Request volume and resource usage | Does not replace codec limits |
| Timeout | Request/stream duration | Does not cap byte volume |

For **Spring Boot 3.5**, the HTTP codec configuration property is:

```properties
spring.http.codecs.max-in-memory-size=256KB
```

The value above is an **illustrative setting**: the `spring.http.codecs` namespace applies to Boot 3.5; verify for your version if switching Boot majors. Many codecs default around 256 KiB per aggregated unit; this property is not a cap on total uploads. For manually configured `WebClient` instances, client codec limits may differ from server limits.

Do not copy `spring.codec.max-in-memory-size` from older Boot tutorials expecting it to still apply in Boot 3.5.

### 16.1. Slow bodies and cancellation

Clients can upload data very slowly (slowloris/slow upload) or disconnect mid-NDJSON stream. Reactor offers `timeout`, `doFinally`, and `doOnCancel`, yet network cancellation propagation is not always instantaneous and upstream sources may keep running briefly. In production:

- Enforce upload duration and idle timeouts at the gateway/Netty.
- Enforce per-tenant request concurrency and rate quotas.
- Clean up any external subscriptions or storage streams in `doFinally`/`usingWhen`.
- Avoid unbounded replay or logging queues for raw inputs.
- Guard against recursive or deeply nested JSON, numeric overflows, and CPU-heavy regexes.
- Bound **line counts** and **byte counts** explicitly by contract, not only decoded item counts.

## 17. When to use annotated controllers instead of WebFlux.fn?

| Scenario | Functional WebFlux | Annotated WebFlux |
| --- | --- | --- |
| Route organization via functions/predicates | `RouterFunctions.route()` | `@RequestMapping` |
| Reading a single body | `request.bodyToMono(Dto.class)` | `@RequestBody Mono<Dto>` |
| Reading a streaming body | `request.bodyToFlux(Dto.class)` | `@RequestBody Flux<Dto>` |
| Validating DTOs from JSON | Invoke `Validator` in handler | `@Valid`/`@Validated` supported by framework |
| Direct method constraints `@Min` | Explicit parsing/validation or domain/service | Built-in handler method validation |
| Body field errors | Custom `InputProblem` + error response | `WebExchangeBindException` typically |
| Local middleware | `HandlerFilterFunction` | `WebFilter`, advice, or stack interceptors |
| Error schema | `ServerResponse` or `WebExceptionHandler` | `@RestControllerAdvice`/`ErrorResponse` |
| JSON codecs | Shared WebFlux `HttpMessageReader`/`Writer` | Shared codecs |
| Backpressure | `Mono`/`Flux` | `Mono`/`Flux` |

**Important:** when using `bodyToMono` in a functional handler, do not expect the framework to throw `WebExchangeBindException` merely because the DTO has `@NotBlank`. You must call the validator explicitly. Conversely, in an annotated controller with `@Valid`, WebFlux infrastructure handles validation and its exception path automatically for controller signatures.

Spring MVC.fn is a separate product (`org.springframework.web.servlet.function.ServerRequest`), where `body(...)` typically returns a synchronous object; never copy that pattern into a reactive handler.

## 18. Custom validation and asynchronous business logic

### 18.1. Cross-field constraints

For example, a DTO with `startDate` and `endDate` ensuring `start` is not after `end` needs a class-level Bean Validation constraint or domain code:

```java
Mono<EventCommand> checkRange(EventCommand input) {
    if (input.start().isAfter(input.end())) {
        return Mono.error(
                new InputProblem(
                    "INVALID_TIME_RANGE",
                    List.of("start", "end")));
    }
    return Mono.just(input);
}
```

This is a fragment; the DTO and exception must exist. Avoid collapsing all errors into `IllegalArgumentException` and generic 400s when typed business exceptions are clearer.

### 18.2. Uniqueness checks via reactive repositories

```java
Mono<Book> checkThenSave(CreateBook input) {
    return repository.existsByTitle(input.title())
            .flatMap(exists -> {
                if (exists) {
                    return Mono.error(
                        new DuplicateBookException());
                }
                return repository.save(toEntity(input));
            });
}
```

This is a fragment. There is a **race condition** between `exists` and `save`, so if duplicates are forbidden, back it with a DB unique index/constraint and map conflicts to 409. Never place blocking DB calls inside a `ConstraintValidator` running on the Netty event loop.

### 18.3. Bean Validation groups

You can pass `validator.validate(dto, CreateGroup.class)` to select a group when calling Jakarta Validator directly. If create and update rules differ:

```java
Set<ConstraintViolation<CreateBook>> errors =
        validator.validate(input, OnCreate.class);
```

This fragment assumes an `OnCreate` marker interface exists and constraints declare that group. When specifying a custom group, constraints in the `Default` group are not triggered unless explicitly included; test `null`, empty, whitespace, and nested cascades.

## 19. Additional tests: missing body, IDs, serialization, and memory

A thorough test suite beyond the ten tests above should include:

1. Valid JSON body with wrong `Content-Type`: verify the actual status from your router/predicate policy.
2. Missing `Content-Type`: verify route behavior without assuming a validation error.
3. Generic JSON array: verify `ParameterizedTypeReference<List<...>>` decodes the exact element type.
4. Single NDJSON record exceeding `maxInMemorySize`: verify codec limit and dedicated error policy.
5. Many small records totaling a large request: verify upload quotas at proxy or application level.
6. Stream failing at line N: verify prior side effects and transaction semantics.
7. Stream client cancellation: verify publisher and external resource cleanup.
8. Nested Bean Validation errors with deterministic sorted field order.
9. Handlers never call `subscribe()` or `block()` (via static analysis/code review).
10. Staging proxy tests with chunked/HTTP2 requests, slow uploads, and gateway timeouts.

### 19.1. Why WebTestClient?

`WebTestClient` supports WebFlux HTTP testing. It can bind directly to router functions or run against a real server. The demo uses **`RANDOM_PORT`** to test codecs and network request/response flow, not just handler logic.

When testing external networks, timing, connection pools, and backpressure introduce factors that make tight wall-clock assertions flaky. To test raw reactive demand, use `StepVerifier` in unit tests; to verify HTTP body framing, use `WebTestClient` or an appropriate streaming client.

## 20. Common mistakes

| Mistake | Consequence | Right approach |
| --- | --- | --- |
| `bodyToMono` followed by `block()` | Blocks the event loop | Compose `flatMap`/`map` and return `Mono` |
| Manual `subscribe()` in handler | Breaks HTTP error/cancellation lifecycle | Let WebFlux subscribe |
| Assuming `@NotBlank` auto-validates in fn | Invalid input reaches services | Inject `Validator` and invoke explicitly |
| Validating only the first record | Later records remain unchecked | Validate every item in the `Flux` |
| `collectList()` on infinite NDJSON | Unbounded heap growth | Stream or use bounded `reduce` |
| Ignoring `Mono.empty` | Missing-body request accepted or hangs depending on code | `switchIfEmpty` or explicit policy |
| Catching every `Exception` as 400 | Masks DB failures and bugs | Typed errors per layer |
| Logging `violation.getInvalidValue()` | Leaks credentials or PII | Field paths + safe error codes |
| Returning `INPUT_VALIDATION` for broken JSON | Misclassified error | Handle decoder errors separately |
| Treating wrong `Content-Type` as `@Valid` failure | Actually a route/predicate miss | Test HTTP routing and statuses |
| Reading binary files via `bodyToFlux(Dto.class)` | Wrong codec | `FilePart`/`DataBuffer` extractors |
| Reading body twice to log | Single-use stream; buffers released | Single pipeline; bounded decorator if needed |
| `flatMap(save)` for sequential workflows | Reorders items, concurrency races | `concatMap` or transactions |
| Stream fails at line 100 after 99 commits | Partial batch | Staging/transaction/job design |
| Bounding only per-record size | Total upload can still be huge | Gateway/request body quotas |
| Assuming `take(1000)` rejects oversized uploads | Cancels after 1000 without reporting limit exceeded | Explicit reject/count policy |
| Nested `@Valid` without `@NotNull` | Null nested object slips through | `@NotNull @Valid` |
| Treating `@Email` as address ownership proof | Identity spoofing | Separate email verification and authorization |
| Error after HTTP 200 bytes written | Cannot switch status to 400 | Streaming error protocol or retry |
| Unit-testing input directly without HTTP tests | Misses codecs and media types | `WebTestClient` on `RANDOM_PORT` |

## 21. Pre-production checklist

- [ ] Use `bodyToMono` for single-value representations and `bodyToFlux` for appropriate multi-record streams.
- [ ] Document and test `Content-Type`, `Accept`, and body framing.
- [ ] Never confuse WebFlux.fn with Spring MVC.fn.
- [ ] Configure validation provider and explicitly invoke Bean Validator in handlers.
- [ ] Add `@NotNull` alongside `@Valid` on required nested DTO fields.
- [ ] Handle `Mono.empty`/`Flux.empty` explicitly.
- [ ] Catch decoder errors and Bean Validation errors separately—no catch-all 400.
- [ ] Run side effects only after validating each item/command.
- [ ] Never call `subscribe()` or `block()` inside handlers.
- [ ] Never read the request body twice without a safe caching decorator.
- [ ] Enforce per-record and batch-level limits/quotas and clear transaction semantics on import streams.
- [ ] Choose `flatMap` concurrency vs. `concatMap` ordering intentionally.
- [ ] Ensure error responses never expose rejected values, secrets, or parser stack traces.
- [ ] Handle authn/authz, tenant boundaries, and mass-assignment protections independently.
- [ ] Define clear codec max memory, total bytes, max records, timeouts, and per-user rate limits.
- [ ] Handle multipart files via `Part`/`FilePart`/`PartEvent` with private storage policies.
- [ ] Check accumulators for overflow before persisting if totals can grow large.
- [ ] `WebTestClient` tests cover success, invalid, empty, malformed, nested, and streaming cases.
- [ ] Monitor cancellations, errors, latency, and queue bytes without logging DTOs containing PII.
- [ ] Cross-check Javadocs and properties when upgrading Spring Boot/Framework versions.

## 22. Self-practice exercises

1. Compare `bodyToMono(CreateBook.class)` and `bodyToFlux(ImportLine.class)`: how do the publishers differ?
2. If the JSON body is `null` or the request has no body, how does `Mono.empty` affect `map(this::validate)`?
3. Why are Bean Validation annotations on a DTO insufficient in WebFlux.fn without calling `Validator`?
4. Replace `jakarta.validation.Validator` with Spring `Validator` + `BeanPropertyBindingResult`.
5. Create a nested DTO with `@NotNull @Valid`; remove `@NotNull` and test a `contact=null` payload.
6. Add `@Size(max=20)` to `sku` and verify which NDJSON line fails.
7. Change `.index().map(...)` to `.map(...)`; without the index, how would UI errors pinpoint the failing line?
8. Switch import to `concatMap(repository::save)` and simulate failure on the third record. How many rows may have committed?
9. If import must be atomic, design a staging/transaction/job workflow instead of saving line-by-line.
10. Why is `onErrorResume(Throwable.class, ...)` dangerous during a DB outage?
11. Compare malformed JSON against valid JSON with a blank title; which codes are returned and where is each error emitted?
12. When a request sends `Content-Type: text/plain` to a JSON-only route, which statuses can appear and what should you test?
13. Body is `List<CreateBook>`: write the `ParameterizedTypeReference` overload to preserve the generic type.
14. Why does `request.bodyToFlux(...)` followed by `collectList()` defeat streaming benefits?
15. Test a 1 MiB NDJSON line; which codec limit applies? If 10,000 small lines are sent, where is the total body quota enforced?
16. Why doesn't `@Size(max=80)` stop a 100 MB JSON payload?
17. A client disconnects after sending two lines. Which Reactor APIs clean up repository streams or subscriptions?
18. Using `doOnCancel` and `doFinally`, compare complete, error, and cancel when the client closes the connection.
19. Add a `page` query parameter in a functional request via `request.queryParam("page")`; how do you parse and validate it?
20. When a product supports binary/multipart uploads, why use `FilePart` instead of `bodyToFlux(MyDto.class)`?
21. Design a `ProblemDetail` response for `INPUT_VALIDATION` that never leaks passwords or tokens.
22. If a WebFlux app scales to 3 nodes with an in-memory map, why can `GET` on `Location` fail?
23. Once `Mono<ServerResponse>` is created but not yet subscribed, have repository side effects necessarily run? Distinguish side effects outside vs. inside operators.
24. Write `WebTestClient` tests for empty body, malformed JSON, nested validation, and invalid NDJSON line.
25. Compare `@Valid @RequestBody Mono<DTO>` in an annotated WebFlux controller with manual validation in WebFlux.fn.
26. Outline a plan to take the demo to production: auth/tenant checks, DB uniqueness/atomic imports, total quotas, codec limits, error codes, and observability.

## 23. Official documentation

- [Spring Framework 6.2 — Functional Endpoints WebFlux.fn](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-functional.html): `ServerRequest`, `bodyToMono`/`bodyToFlux`, `BodyExtractors`, functional Bean Validation, routing, and filters.
- [Spring Framework 6.2 — ServerRequest Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/reactive/function/server/ServerRequest.html): `bodyToMono(Class)`, `bodyToMono(ParameterizedTypeReference)`, `bodyToFlux`, `formData`, `multipartData` overloads.
- [Spring Framework 6.2 — ServerResponse Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/reactive/function/server/ServerResponse.html): `Mono` response, `created`, `ok`, `bodyValue`, and error responses.
- [Spring Framework 6.2 — BodyExtractors Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/reactive/function/BodyExtractors.html): `toMono`, `toFlux`, raw `DataBuffer`, form/multipart.
- [Spring Framework 6.2 — WebFlux HTTP Codecs](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html): `Reader`/`Decoder`, byte buffers, aggregation limits, backpressure.
- [Spring Framework 6.2 — Annotated Controller Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-validation.html): differences in automatic validation when using `@Valid` on annotated method arguments.
- [Spring Framework 6.2 — WebFlux Multipart](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/multipart-forms.html): `FilePart`, `PartEvent`, and upload safety.
- [Spring Boot 3.5 — Servlet/Reactive Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html): reactive web stack and WebFlux setup.
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html): `spring.http.codecs.max-in-memory-size`.
- [Spring Boot 3.5 — Validation](https://docs.spring.io/spring-boot/3.5/reference/io/validation.html): Jakarta Validation provider and auto-configuration.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): WebFlux HTTP integration testing.
- [Jakarta Bean Validation Specification](https://jakarta.ee/specifications/bean-validation/): constraints, nested cascades, and groups.
- [Reactive Streams Specification](https://www.reactive-streams.org/): demand, cancellation, and publisher/subscriber contracts.
