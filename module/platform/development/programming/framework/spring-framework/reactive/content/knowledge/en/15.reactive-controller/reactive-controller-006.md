# Reading `@RequestBody` as an Object or a Publisher in Spring WebFlux

## 1. Role of @RequestBody in WebFlux

In Spring WebFlux, the `@RequestBody` annotation tells the framework to read the HTTP request body and convert its content into the Java type declared by the controller. The conversion is performed by **`HttpMessageReader`**s (usually invoked through codecs such as the Jackson JSON decoder). The reader chooses how to decode based on the target type, `Content-Type`, codec configuration, and the received data.

An important difference between WebFlux and Spring MVC is that WebFlux allows a `@RequestBody` parameter to be a **reactive type** such as `Mono<T>` or `Flux<T>`. This lets the body be read in the Reactive Streams model, without blocking to wait for the entire content before composing with the reactive pipeline; WebFlux also supports client-to-server streaming.

There are three common ways to declare it:

~~~java
// An object bound directly:
@PostMapping("/accounts")
public Account handle(@RequestBody Account account) {
    return account;
}

// A body containing at most one object:
@PostMapping("/accounts/mono")
public Mono<Account> handle(@RequestBody Mono<Account> account) {
    return account;
}

// A body containing multiple objects:
@PostMapping("/accounts/stream")
public Mono<Long> handle(@RequestBody Flux<Account> accounts) {
    return accounts.count();
}
~~~

These are illustrative signatures; a real controller needs the appropriate annotations, imports, and `Account` type. Choose the type based on **the amount of data and how it is processed**, not just on whether the application uses WebFlux.

## 2. Reading the Body Directly into a Java Object

If an endpoint receives a small JSON object, you can declare the parameter directly:

~~~java
@PostMapping(path = "/accounts", consumes = MediaType.APPLICATION_JSON_VALUE)
public AccountView create(@Valid @RequestBody CreateAccountRequest request) {
    return new AccountView(request.name(), request.email());
}
~~~

With the request:

~~~http
POST /accounts
Content-Type: application/json

{"name":"An","email":"an@example.com"}
~~~

Spring WebFlux uses the message reader to decode the JSON into `CreateAccountRequest`, then passes the object into the controller method. The controller method does not need to accept `Mono` just because the application runs on WebFlux.

Characteristics:

- Simple, readable declaration when the business logic needs a single DTO.
- The body is resolved into an object before the controller method is invoked.
- Suitable for requests of finite, reasonably bounded size.
- You can use `@Valid` or `@Validated` to trigger Bean Validation.
- If you need direct access to validation errors via `Errors` or `BindingResult`, declare that parameter immediately after the validated body parameter.

**Do not infer that a direct Java parameter makes WebFlux switch to Servlet blocking I/O.** WebFlux still uses the reactive infrastructure to read the body; the controller signature simply receives the already-decoded result as an object instead of receiving a publisher to compose further.

## 3. Using Mono<T> When the Body Contains at Most One Value

When you want to keep reading the body inside the reactive pipeline, use `Mono<T>`:

~~~java
@PostMapping(path = "/accounts/mono", consumes = MediaType.APPLICATION_JSON_VALUE)
public Mono<AccountView> create(@Valid @RequestBody Mono<CreateAccountRequest> body) {
    return body.map(request ->
        new AccountView(request.name(), request.email())
    );
}
~~~

`Mono<CreateAccountRequest>` expresses a contract of **0 or 1 element** per subscription. This is the natural choice for a single JSON object when the service needs to combine additional publishers:

~~~java
// The service methods below are hypothetical examples.
public Mono<AccountView> create(Mono<CreateAccountRequest> body) {
    return body.flatMap(request ->
        accountService.save(request)
            .map(saved -> new AccountView(saved.id(), saved.name()))
    );
}
~~~

Benefits:

- You can use `map`, `flatMap`, `switchIfEmpty`, `onErrorResume`, and other operators.
- You can compose with reactive repositories, `WebClient`, or asynchronous operations.
- No need to call `subscribe()` manually in the controller; return the publisher so WebFlux manages the subscription.
- Decoding and processing the body stay in one chain that can propagate cancellation and errors downstream/upstream.

A request with an empty body, an invalid body, or one that fails to decode to the required type does not always mean the same thing. Define clearly whether the endpoint allows an absent body, whether the data type can be empty, and the corresponding HTTP policy. Do not use `null` as a reactive element; absence is represented by an empty publisher.

## 4. Using Flux<T> When the Body Contains Multiple Objects

If the client sends a sequence of multiple records, declare `Flux<T>`:

~~~java
@PostMapping("/accounts/import")
public Mono<Long> importAccounts(@RequestBody Flux<CreateAccountRequest> requests) {
    return requests
        .map(request -> new Account(request.name(), request.email()))
        .count();
}
~~~

`Flux<CreateAccountRequest>` represents **0 to many objects**. As the data is decoded, elements can flow through the pipeline one by one. The controller can process each element, apply a concurrency limit, or pass each record to a reactive service.

Example of processing each record:

~~~java
// accountService.save(...) returns Mono<Account> in a real application.
@PostMapping("/accounts/import")
public Mono<Long> importAccounts(@RequestBody Flux<CreateAccountRequest> requests) {
    return requests
        .concatMap(accountService::save)
        .count();
}
~~~

`concatMap` processes sequentially and preserves source order. If the business logic allows concurrent processing, you can use `flatMap(accountService::save, concurrency)` with a bounded concurrency level; the order of results is then not guaranteed to match the request order. Do not set concurrency too high if the database or downstream service has connection limits.

**Do not collect the entire Flux into a List if the goal is streaming large data.** `collectList()` keeps every element in memory before emitting a single `Mono<List<T>>`. Use it only when the batch has a bounded size and the business logic genuinely needs the entire list before processing.

## 5. JSON Object, JSON Array, and NDJSON

The Java type only states the cardinality of the publisher; the actual HTTP format also depends on `Content-Type` and the message reader.

### A JSON Object

Body:

~~~json
{"name":"An","email":"an@example.com"}
~~~

Usually `Content-Type: application/json` is used with `@RequestBody CreateAccountRequest` or `Mono<CreateAccountRequest>`.

### A JSON Array

Body:

~~~json
[
  {"name":"An","email":"an@example.com"},
  {"name":"Binh","email":"binh@example.com"}
]
~~~

With the Jackson decoder in WebFlux, multiple objects can be read from a JSON array into `Flux<CreateAccountRequest>` when the codec and media type are supported. The reader decodes each JSON object as soon as enough data for that object arrives. If the endpoint needs a finite collection and processes the whole thing as a single unit, you can also use `Mono<List<CreateAccountRequest>>` or a DTO containing a list.

### NDJSON (Newline Delimited JSON)

NDJSON puts each JSON object on its own line:

~~~text
{"name":"An","email":"an@example.com"}
{"name":"Binh","email":"binh@example.com"}
{"name":"Chi","email":"chi@example.com"}
~~~

The client sends with:

~~~http
Content-Type: application/x-ndjson
~~~

This is a convenient format for streaming multiple records: the decoder can emit each object as soon as it receives a full JSON line, instead of waiting for the entire batch to finish. In Spring Framework, the Jackson decoder supports line-delimited JSON formats such as NDJSON; check the specific codec if replacing Jackson with another library.

Quick selection table:

| HTTP content | Common parameter type | Notes |
| --- | --- | --- |
| A single JSON object | `Account` or `Mono<Account>` | Direct DTO is simple; Mono is convenient for reactive composition |
| Finite JSON array | `Flux<Account>` or `Mono<List<Account>>` | Flux processes element by element; List holds everything in RAM |
| Multi-line NDJSON | `Flux<Account>` | Suitable for client-to-server streaming |
| Form URL encoded | Use form data / `@ModelAttribute` mechanism or corresponding API | Not a JSON DTO |
| Multipart upload | `@RequestPart`, `Flux<Part>`, or multipart API | Requires handling the lifecycle of files/parts |

Do not confuse `application/json` with NDJSON. Both are JSON, but a JSON array is a single document with an array structure, whereas NDJSON is a sequence of independent JSON documents separated by newlines. Choosing the right media type helps client and server agree on how data is framed.

## 6. Complete Java 17+ Example with Spring Boot WebFlux

The example below has three endpoints:

- `POST /api/accounts/plain`: reads one DTO directly.
- `POST /api/accounts/mono`: reads one DTO via `Mono<T>` and uses Bean Validation.
- `POST /api/accounts/stream`: reads multiple DTOs via `Flux<T>` from NDJSON and processes them as a stream.

Create the structure:

~~~text
request-body-demo/
├── pom.xml
└── src/main/java/com/example/requestbody/
    ├── RequestBodyApplication.java
    └── AccountController.java
~~~

File `pom.xml` (Spring Boot 3.5.0, Java 17+):

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>request-body-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
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
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
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

File `src/main/java/com/example/requestbody/RequestBodyApplication.java`:

~~~java
package com.example.requestbody;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RequestBodyApplication {
    public static void main(String[] args) {
        SpringApplication.run(RequestBodyApplication.class, args);
    }
}
~~~

File `src/main/java/com/example/requestbody/AccountController.java`:

~~~java
package com.example.requestbody;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.*;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/accounts")
public class AccountController {

    public record CreateAccountRequest(
        @NotBlank String name,
        @NotBlank @Email String email
    ) {}

    public record AccountView(String name, String email) {}

    private AccountView toView(CreateAccountRequest request) {
        return new AccountView(request.name(), request.email());
    }

    // 1. One DTO bound directly.
    @PostMapping(
        path = "/plain",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public AccountView plain(@Valid @RequestBody CreateAccountRequest request) {
        return toView(request);
    }

    // 2. One DTO in a 0..1 publisher.
    @PostMapping(
        path = "/mono",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<AccountView> mono(
            @Valid @RequestBody Mono<CreateAccountRequest> body) {
        return body.map(this::toView);
    }

    // 3. Multiple DTOs in an NDJSON stream.
    @PostMapping(
        path = "/stream",
        consumes = "application/x-ndjson",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public Mono<String> stream(
            @RequestBody Flux<CreateAccountRequest> body) {
        return body
            .map(this::toView)
            .count()
            .map(count -> "accepted=" + count);
    }
}
~~~

Run from the `request-body-demo` directory with JDK 17+ and Maven:

~~~bash
mvn spring-boot:run
~~~

### Try the Endpoint Receiving a Direct Object

~~~bash
curl -i -X POST http://localhost:8080/api/accounts/plain ^
  -H "Content-Type: application/json" ^
  -d "{"name":"An","email":"an@example.com"}"
~~~

Expected JSON body:

~~~json
{"name":"An","email":"an@example.com"}
~~~

### Try the Endpoint Receiving a Mono

~~~bash
curl -i -X POST http://localhost:8080/api/accounts/mono ^
  -H "Content-Type: application/json" ^
  -d "{"name":"Binh","email":"binh@example.com"}"
~~~

Expected JSON body:

~~~json
{"name":"Binh","email":"binh@example.com"}
~~~

### Try the Endpoint Receiving a Flux from NDJSON

Create the file `accounts.ndjson` with the following content, each JSON object on one line:

~~~text
{"name":"An","email":"an@example.com"}
{"name":"Binh","email":"binh@example.com"}
{"name":"Chi","email":"chi@example.com"}
~~~

Send the file:

~~~bash
curl -i -X POST http://localhost:8080/api/accounts/stream ^
  -H "Content-Type: application/x-ndjson" ^
  --data-binary "@accounts.ndjson"
~~~

Response body:

~~~text
accepted=3
~~~

The commands above use Windows CMD line continuation (`^`). If running Bash or another shell, you can write the command on one line or replace the line-continuation character accordingly.

**What the example demonstrates:**

1. The same DTO can be received as a direct object or as `Mono<CreateAccountRequest>`.
2. `Mono` lets you use `map` to transform the decoded result without subscribing manually.
3. `Flux` receives multiple records; the stream endpoint only counts the records after the source completes, without needing to collect everything into a List.
4. For the stream endpoint, `Content-Type` must match a media type supported by the mapping and codec.
5. The example does not save to a database; in a real application, replace `toView` with a reactive service and choose `concatMap` or `flatMap` according to ordering/concurrency requirements.

## 7. Validation When Using @RequestBody

Spring WebFlux supports `@Valid` and `@Validated` on `@RequestBody`. With a direct DTO:

~~~java
@PostMapping("/accounts")
public AccountView create(@Valid @RequestBody CreateAccountRequest request) {
    return toView(request);
}
~~~

If `name` is empty or `email` has an invalid format, Bean Validation reports an error. By default, request body bind/validation errors are represented by `WebExchangeBindException` and mapped to HTTP **400 Bad Request**.

With a reactive wrapper, you can declare:

~~~java
@PostMapping("/accounts")
public Mono<AccountView> create(
        @Valid @RequestBody Mono<CreateAccountRequest> body) {
    return body.map(this::toView)
        .onErrorResume(WebExchangeBindException.class, error -> {
            // Can convert into a domain-specific response or let
            // the global exception handler process it.
            return Mono.error(error);
        });
}
~~~

This snippet illustrates where validation errors can pass through the reactive chain. If no custom handling is needed, there is no need to add `onErrorResume`; letting the default exception handler or `@ControllerAdvice` manage the error is enough.

If you declare `Errors` or `BindingResult` to read errors directly in the method, that parameter must come immediately after the validated DTO. Under WebFlux's contract, when using this approach the body **must not be declared as `Mono`** and is resolved before the method is invoked.

With a multi-record `Flux<T>`, you need to define a clear per-record validation policy. You can inject `jakarta.validation.Validator` and call `validator.validate(record)` inside the pipeline, then convert violations into domain errors. If you want to skip an invalid record, express that policy explicitly; do not automatically swallow every error because that can cause data loss.

## 8. Content-Type, Codecs, and HTTP Errors

`@RequestBody` does not parse every format by itself. The framework selects an `HttpMessageReader` compatible with the target type and media type. Common errors:

| Symptom | Common cause | How to check |
| --- | --- | --- |
| HTTP 415 Unsupported Media Type | Client sends a `Content-Type` with no matching reader or not matching the `consumes` mapping | Check the header, `consumes`, and registered codecs |
| HTTP 400 Bad Request | Invalid JSON syntax, unconvertible data type, or validation failure | Check the body, DTO, enum/date format, and BindingResult |
| Empty body / no result | Client sends no body, publisher completes empty, or the endpoint allows absence | Define whether the body contract is required or optional |
| `Flux<T>` does not decode as expected | Wrong framing/media type or decoder does not support the data type | Try JSON array/NDJSON and check the specific codec |
| Memory error with large bodies | Collecting data into a collection or unsuitable codec limits | Process as a stream, set size and concurrency limits |
| Data read twice | Multiple components consume the one-shot request body | Designate one owner for the body or use a bounded cache by design |

`Content-Type` describes the body format the client **is sending**; `Accept` describes the response format the client **wants to receive**. Do not use `Accept` as a substitute for `Content-Type` when sending JSON or NDJSON.

WebFlux's default codecs support many types such as JSON, text, byte arrays, forms, and multipart depending on dependencies. You can configure them via `ServerCodecConfigurer`, for example to limit memory for decoding JSON or register a custom reader. When increasing `maxInMemorySize`, consider request sizes and concurrent requests, because a large limit can increase RAM pressure.

## 9. Request Body Is a One-Shot Stream: Do Not Subscribe or Block Manually

The reactive body is provided to the controller by the framework according to the request lifecycle. Avoid these patterns:

~~~java
// Wrong: subscribing manually, detaching the work from the HTTP request lifecycle.
@PostMapping("/bad")
public Mono<Void> bad(@RequestBody Flux<CreateAccountRequest> body) {
    body.subscribe(this::save);
    return Mono.empty();
}

// Wrong: blocking to obtain a value synchronously on the WebFlux processing path.
@PostMapping("/also-bad")
public AccountView alsoBad(@RequestBody Mono<CreateAccountRequest> body) {
    CreateAccountRequest request = body.block();
    return toView(request);
}
~~~

The examples above intentionally illustrate anti-patterns. `subscribe()` creates a separate subscription and can cause the controller to return a response before the work finishes; request cancellation/errors no longer properly manage the self-created pipeline. `block()` waits synchronously, can block the event loop, and reduces the ability to serve other requests.

The right way is to **compose and return a publisher**:

~~~java
@PostMapping("/good")
public Mono<Void> good(@RequestBody Flux<CreateAccountRequest> body) {
    return body.concatMap(accountService::save).then();
}
~~~

If you need to inspect the request body in filters, logging middleware, or multiple components, each place should not read the raw body independently. Design a single owner for the body, use a request decorator/bounded cache when genuinely needed, and preserve backpressure/cancellation semantics. With form data, use the `ServerWebExchange.getFormData()` API consistently; after parsing/caching the form, do not switch to reading the raw body again as an independent source.

## 10. Backpressure and Processing Large Bodies

When using `Flux<T>`, downstream can request data on demand through Reactive Streams. This lets the pipeline throttle reading and processing the body, but it does not mean every codec, proxy, or client does not buffer. Design the entire path:

- Limit request size at the server/gateway and codec memory limits.
- Avoid `collectList()` with unbounded batches.
- Choose bounded concurrency if saving/calling downstream for each record.
- Handle cancellation when the client disconnects.
- Have timeouts, rate limits, and clear error responses.
- Monitor memory, connection pools, latency, records received, and records saved successfully.

If you need ordered processing:

~~~java
return body.concatMap(accountService::save).then();
~~~

If bounded concurrent processing is allowed:

~~~java
return body.flatMap(accountService::save, 8).then();
~~~

The number `8` is only a concurrency example; choose based on the connection pool and downstream capacity, do not treat it as an optimal default. `flatMap` may complete inner publishers in a different order than the order in which the body was received.

### When Do You Need to Handle DataBuffer Directly?

Normally, let the codec decode JSON into DTOs. You do not need to retain or release `DataBuffer` yourself in a controller using `@RequestBody Mono<DTO>` or `Flux<DTO>`.

Only when handling raw `Flux<DataBuffer>`, writing a custom codec, or retaining buffers yourself do you need to pay attention to the lifecycle. On some servers such as Reactor Netty, buffers may be pooled and reference-counted. If the application consumes/retains buffers itself, it must release them on time with `DataBufferUtils.release(...)`; when using operators that can discard buffers, handle discards properly, for example `doOnDiscard(DataBuffer.class, DataBufferUtils::release)` in an appropriate pipeline. When using standard codecs, buffer management is usually handled by the framework.

## 11. Comparing @RequestBody with @RequestPart and WebClient

Do not use `@RequestBody` for every kind of request:

- **JSON/XML body**: usually use `@RequestBody` and a DTO or reactive wrapper.
- **Multipart form**: use `@RequestPart` for each part, or `ServerWebExchange`'s multipart API; file parts have their own lifecycle.
- **Query/form parameters**: use `@RequestParam`, `@ModelAttribute`, or `getFormData()` as appropriate.
- **Raw byte stream**: you can use `Flux<DataBuffer>` when you genuinely need to handle bytes yourself, but you must manage releases.
- **Client sending requests**: `WebClient.bodyValue(object)` for an already-available value; `WebClient.body(publisher, Type.class)` for a `Mono`/`Flux` that emits data.

Client-side example:

~~~java
// Send an available DTO.
webClient.post()
    .uri("/api/accounts/plain")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(account)
    .retrieve()
    .bodyToMono(AccountView.class);

// Send a publisher of multiple DTOs.
webClient.post()
    .uri("/api/accounts/stream")
    .contentType(MediaType.APPLICATION_NDJSON)
    .body(accountFlux, CreateAccountRequest.class)
    .retrieve()
    .bodyToMono(String.class);
~~~

This is an illustrative snippet in a service where `WebClient`, `account`, and `accountFlux` are defined. `bodyValue` is for an already-available object; `body` accepts a publisher. The client's media type must match the server's `consumes`.

## 12. Common Mistakes and How to Avoid Them

1. **Using `Mono<T>` for a multi-record body:** cardinality contract mismatch. Use `Flux<T>` or `Mono<List<T>>` if the full list is genuinely needed.
2. **Using `Flux<T>` then `collectList()` for an unbounded stream:** nullifies the benefit of element-by-element processing and can grow RAM without bound. Process as a stream or split into bounded batches.
3. **Assuming a direct DTO in WebFlux is blocking:** the body is still read through the reactive infrastructure; choose a direct DTO when the method needs one object, choose Mono when you want to compose.
4. **Sending NDJSON while setting `Content-Type: application/json`:** client and server may interpret framing differently. Use the media type corresponding to the chosen format.
5. **Sending a JSON object to an endpoint expecting `Flux<T>` of multiple elements:** the payload does not match the endpoint's schema/framing. Align on object, array, or NDJSON.
6. **Forgetting `consumes`:** the endpoint may accept the wrong type or reject unexpected media types. Declare `consumes` and send the right header.
7. **Calling `subscribe()` yourself in the controller:** detaches the pipeline from the request lifecycle, making cancellation and errors harder to manage. Return the publisher.
8. **Calling `block()` on the event loop:** blocks the shared thread. Use `map`/`flatMap` and return `Mono`/`Flux`.
9. **Reading the body from multiple places:** the request body is a one-shot stream. Design one consumer or a bounded cache.
10. **Assuming `@Valid` automatically handles every per-item validation of Flux the same way as a single DTO:** clearly define how each record is validated and how errors propagate in the pipeline.
11. **Swallowing decode/validation errors:** can return success even when the request is invalid. Keep the error signal or convert it into a domain-specific response.
12. **Not handling client cancellation on large streams:** upstream work may continue if the external source does not support cancellation. Attach cleanup to resources and use cancellable reactive APIs.
13. **Retaining DataBuffer yourself and forgetting to release:** can cause memory leaks, especially with pooled buffers. Prefer DTO codecs; if managing buffers yourself, follow the lifecycle.
14. **Increasing maxInMemorySize unconditionally:** can increase RAM when many large requests run concurrently. Set limits according to workload and gateway/server policy.
15. **Using flatMap while assuming order:** inner publishers can complete out of input order. Use concatMap if the business logic requires sequential order.

## 13. Checklist for Designing Body-Receiving Endpoints

Before writing the controller, answer these questions:

- Does the body contain **one object**, a **finite collection**, or a **stream of many records**?
- Does the client send `application/json`, a JSON array, or `application/x-ndjson`?
- Does the controller need a direct DTO, `Mono<T>`, `Flux<T>`, or `Mono<List<T>>`?
- Is Bean Validation needed? Should validation errors return 400 by default or need custom mapping?
- If the body is empty, does the endpoint treat that as an error, absence, or an empty list?
- Does processing order need to be preserved? If so, use `concatMap`; if processing concurrently, bound concurrency.
- Are there limits on payload, codec memory, batch size, and sending rate?
- When the client cancels the request, do upstream and resources stop/clean up?
- Is the body being read multiple times or manually subscribed/blocked?
- Is raw `DataBuffer` really needed, or can a codec decode directly into a DTO?

## 14. Self-Check Questions

**1.** Can `@RequestBody Account account` be used in WebFlux? **Yes.** WebFlux can decode the body directly into an object via `HttpMessageReader`.

**2.** When should you choose `Mono<Account>`? When the body contains at most one Account and you want to keep reading/transforming inside the reactive pipeline.

**3.** When should you choose `Flux<Account>`? When the body has multiple Accounts and needs to be processed as a stream, such as NDJSON or a JSON array with a supported codec.

**4.** How does `Mono<List<Account>>` differ from `Flux<Account>`? Mono emits one List after collecting; Flux emits each Account. List requires holding all elements in memory.

**5.** Which component does `@RequestBody` use for decoding? `HttpMessageReader`s and codecs matching the target type and Content-Type.

**6.** How does WebFlux handle validation errors on `@Valid @RequestBody`? Usually emits `WebExchangeBindException`, mapped to HTTP 400 Bad Request.

**7.** Why should you not manually subscribe to a `Flux` body in a controller? Because it detaches the work from the subscription managed by WebFlux and breaks the cancellation/error lifecycle.

**8.** When sending NDJSON, what should Content-Type be? `application/x-ndjson`, per the NDJSON media type supported by Spring.

**9.** When must you release DataBuffer yourself? When handling/retaining raw buffers yourself or building a custom codec; for DTOs decoded by standard codecs, the framework usually manages it.

**10.** Which operator should you use to process a stream sequentially? `concatMap`; `flatMap` is appropriate when inner publishers are allowed to run concurrently with controlled concurrency.

**Key takeaway:** `@RequestBody` in WebFlux can receive a **direct object**, **`Mono<T>` for a single value**, or **`Flux<T>` for multiple values**. Message readers/codecs decode the body according to the target type and `Content-Type`. Use Mono/Flux when you want non-blocking composition and streaming; align JSON/NDJSON with the contract, keep the body in a single pipeline managed by WebFlux, and control validation, backpressure, request size, and cancellation.

**Official documentation:** [Spring Framework 6.2 — @RequestBody in WebFlux](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/requestbody.html); [Spring Framework 6.2 — Reactive Core, Jackson codecs](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html); [Spring Framework 6.2 — Data Buffers and Codecs](https://docs.spring.io/spring-framework/reference/6.2/core/databuffer-codec.html).