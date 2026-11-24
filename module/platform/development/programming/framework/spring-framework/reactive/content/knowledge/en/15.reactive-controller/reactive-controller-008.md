# ResponseEntity and When Status, Headers, and Body Are Determined in Spring WebFlux

## 1. Role of ResponseEntity

In Spring WebFlux, a controller can return a publisher such as Mono<T> or Flux<T> so the framework writes the response reactively. When it needs active control over the HTTP response, the controller can use ResponseEntity<T>.

ResponseEntity combines the three parts of an HTTP response:

1. **Status code:** for example 200 OK, 201 Created, 204 No Content, 400 Bad Request, 404 Not Found.
2. **Headers:** for example Content-Type, Location, ETag, Cache-Control, or business headers.
3. **Body:** an object or publisher converted into HTTP data by a message writer/codec.

An easily confused point in WebFlux is that **when status/headers are decided and when the body actually emits data can differ**. Simply changing the position of Mono in the return type can change when the status is known:

- **ResponseEntity<T>:** the controller returns status, headers, and body as values immediately.
- **Mono<ResponseEntity<T>>:** an outer publisher emits the complete ResponseEntity after asynchronous processing; status/headers can depend on the business result.
- **ResponseEntity<Mono<T>>:** the controller decides status/headers immediately; the body is a publisher consumed asynchronously afterward.
- **ResponseEntity<Flux<T>>:** status/headers are decided before streaming the body; the body can emit multiple elements over time.

This is the core distinction for properly handling 404, 201, 204, headers, empty bodies, and errors occurring while streaming. ResponseEntity does not turn blocking code into non-blocking code; it is a model representing response metadata and body.

## 2. Three Points in Time to Keep Separate

When a request reaches WebFlux, picture three points in time:

**Time A — controller creates the result:** the controller method is invoked, producing a value or a publisher. If the return type is Mono<ResponseEntity<T>>, this publisher may not have emitted the ResponseEntity yet. If the return type is ResponseEntity<Mono<T>>, the ResponseEntity object already has status/headers as soon as the method returns.

**Time B — framework receives the metadata:** WebFlux processes the return value, chooses status, headers, and message writer, and prepares to write the body. With ResponseEntity, the framework takes status/headers from the object and writes them into the server response.

**Time C — response is committed and body is written:** once the server begins sending the response over the network, status/headers become part of the sent HTTP response. After the response has committed, the application **cannot change the status code or headers already sent**. If the body publisher continues to emit an error after that point, the server can usually only end the stream/connection or handle the error at the transport layer; it cannot change a 200 already sent back to the client into a 500.

Overview diagram:

~~~text
Request
  |
  v
Controller is invoked
  |
  +--> ResponseEntity<T>
      metadata + body value already present
  |
  +--> Mono<ResponseEntity<T>>
      wait for outer Mono to emit ResponseEntity
      only then are status/headers/body known
  |
  +--> ResponseEntity<Mono<T>> / ResponseEntity<Flux<T>>
         metadata already present
         body publisher is subscribed/written later
  |
  v
WebFlux applies status + headers
  |
  v
Response commits (headers are sent)
  |
  v
Body is written / stream continues
~~~

The diagram describes the meaning of the return types; it does not claim that every server implementation commits at the exact same line of code. The actual commit timing depends on response writing, flushing, the body publisher, and the server adapter.

## 3. Comparing Important Return Types

| Return type | When are status/headers known? | Body | Best fit |
| --- | --- | --- | --- |
| ResponseEntity<User> | As soon as the method returns the object | User value already available | Synchronous result, metadata decided immediately |
| Mono<ResponseEntity<User>> | When the outer Mono emits ResponseEntity | User value inside the entity | Look up data reactively then choose 200/404/201 |
| ResponseEntity<Mono<User>> | As soon as the method returns the entity | Mono<User> consumed later | Fixed status/headers, body arrives asynchronously |
| ResponseEntity<Flux<Event>> | As soon as the method returns the entity | Flux<Event> written as a stream | Streaming, SSE, or multiple records |
| Mono<User> | Per endpoint's default status/annotation | One body value or empty | Reactive response body, no need to choose headers/status manually |

### 3.1. ResponseEntity<T> — whole response already available

~~~java
@GetMapping("/version")
ResponseEntity<String> version() {
    return ResponseEntity.ok()
        .header("X-App-Version", "2.0")
        .body("ready");
}
~~~

This is a snippet in a WebFlux controller. The method creates a ResponseEntity with status 200, a header, and a string body right on the call. WebFlux is still responsible for writing the response through the HTTP server and appropriate codec; the controller does not write bytes directly to a socket.

### 3.2. Mono<ResponseEntity<T>> — deciding the response after obtaining the result

~~~java
@GetMapping("/users/{id}")
Mono<ResponseEntity<User>> find(@PathVariable long id) {
    return service.findById(id)
        .map(user -> ResponseEntity.ok(user))
        .defaultIfEmpty(ResponseEntity.notFound().build());
}
~~~

This is a snippet; User and service.findById are defined by the application. The service returns Mono<User>. When a user is present, the outer publisher emits a 200 ResponseEntity. When the source completes empty, defaultIfEmpty emits a 404 ResponseEntity.

This is the right type when **the reactive result itself decides status/headers**. WebFlux waits for the outer Mono to emit the ResponseEntity to know the metadata before writing the body.

### 3.3. ResponseEntity<Mono<T>> — fixed metadata, asynchronous body

~~~java
@GetMapping("/preview/{id}")
ResponseEntity<Mono<User>> preview(@PathVariable long id) {
    Mono<User> body = service.findById(id);

    return ResponseEntity.ok()
        .header("X-Response-Mode", "body-is-reactive")
        .body(body);
}
~~~

Status 200 and the header are chosen right in the controller. The body publisher is only consumed when the framework writes the response. If the user does not exist and the body is Mono.empty(), the response still keeps the chosen status 200 and an empty body. It **does not automatically turn into 404**.

If the user's existence must decide 200 or 404, use Mono<ResponseEntity<User>> or an outer publisher that can construct the ResponseEntity after knowing the result.

### 3.4. ResponseEntity<Flux<T>> — status/headers first, stream body later

~~~java
@GetMapping(value = "/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
ResponseEntity<Flux<ServerSentEvent<Event>>> events() {
    Flux<ServerSentEvent<Event>> body = eventService.events()
        .map(event -> ServerSentEvent.builder(event).event("update").build());

    return ResponseEntity.ok()
        .contentType(MediaType.TEXT_EVENT_STREAM)
        .body(body);
}
~~~

This is a WebFlux/SSE snippet. Status 200 and the content type are determined before streaming the body. Flux can emit events over time; the client receives the events as the server writes them.

If the publisher errors after the response has committed, the status 200 already sent cannot be replaced with 500. Therefore, streaming endpoints need error design in the stream, logging, upstream retry, or a protocol-level error event if the client needs to receive business error details.

## 4. Choosing a Return Type Based on Business Questions

Do not start from generic types. Ask: **Do we need to wait for an asynchronous result to decide status/headers?**

| Scenario | Type to consider | Reason |
| --- | --- | --- |
| GET one resource; 404 if not found | Mono<ResponseEntity<T>> | Wait for lookup then choose 200 or 404 |
| POST create resource; need Location from generated ID | Mono<ResponseEntity<T>> | Wait for create to finish before building 201 + Location |
| Response is always 202; body is async job status | ResponseEntity<Mono<JobStatus>> | Status is known, body arrives later |
| SSE always returns 200 and streams events | ResponseEntity<Flux<ServerSentEvent<T>>> | Fixed metadata, streaming body |
| Value already available synchronously and custom header needed | ResponseEntity<T> | No outer publisher needed |
| Only returning reactive data, default status fits | Mono<T> / Flux<T> | Simpler, framework handles the body |
| Need 204 when command completes | Mono<ResponseEntity<Void>> or Mono<Void> with matching semantics | Explicitly choose status and no body |
| Business error needs its own status | @ExceptionHandler or onErrorResume creating ResponseEntity | Map error to an intentional response |

An endpoint does not need ResponseEntity just because it returns Mono. If the default status is 200 and no custom headers are needed, returning Mono<T> is usually cleaner. Use ResponseEntity when status, headers, or body absence is part of the HTTP contract.

## 5. 404: Empty Body Differs from Not Found

This is one of the most common mistakes when writing reactive controllers.

### 5.1. Wrong expectation: an empty Mono body automatically turns into 404

~~~java
@GetMapping("/users/{id}/body")
ResponseEntity<Mono<User>> body(@PathVariable long id) {
    return ResponseEntity.ok(service.findById(id));
}
~~~

If the service returns Mono.empty(), the controller has already chosen 200. The framework writes a 200 response with no body. Mono.empty() only indicates that the publisher completed without emitting an element; it does not mean HTTP 404.

### 5.2. Choosing status after lookup

~~~java
@GetMapping("/users/{id}")
Mono<ResponseEntity<User>> find(@PathVariable long id) {
    return service.findById(id)
        .map(user -> ResponseEntity.ok(user))
        .defaultIfEmpty(ResponseEntity.<User>notFound().build());
}
~~~

Here the outer Mono emits exactly one ResponseEntity for both the data-present and data-absent cases. If the source is empty, defaultIfEmpty creates a 404 entity. This expresses accurately that "not existing is a valid HTTP outcome".

### 5.3. Fallback with switchIfEmpty

You can build a fallback response with switchIfEmpty:

~~~java
Mono<ResponseEntity<User>> response = service.findById(id)
    .map(user -> ResponseEntity.ok(user))
    .switchIfEmpty(Mono.fromSupplier(
        () -> ResponseEntity.<User>notFound().build()
    ));
~~~

Use fromSupplier to create the fallback response when needed; for a simple builder, Mono.just(ResponseEntity.<User>notFound().build()) is also valid because the builder has no significant side effect.

### 5.4. Distinguishing Three States

| Publisher state | Meaning | HTTP response to choose |
| --- | --- | --- |
| Mono.just(user) | Data found | 200 + body |
| Mono.empty() | No element | Depends on business logic; resource lookup is usually 404 |
| Mono.error(error) | Processing failed | Map error to an appropriate 4xx/5xx |

Do not mechanically turn every empty into 404. A search query with no results can be 200 with an empty list; a specifically identified resource that does not exist is usually 404. Status reflects the endpoint contract, not merely a Reactor operator.

## 6. 201 Created, Location, and Post-Write Responses

When POST creates a resource successfully, status 201 and the Location header should usually be built **after** the service returns the ID or URI:

~~~java
@PostMapping("/users")
Mono<ResponseEntity<User>> create(@RequestBody CreateUserRequest request) {
    return service.create(request)
        .map(user -> ResponseEntity
            .created(URI.create("/users/" + user.id()))
            .body(user));
}
~~~

- created(URI) creates a ResponseEntity builder with status 201 and Location.
- body(user) adds the body; WebFlux serializes it according to the message codec.
- If the create operation fails, the error becomes onError; an exception handler or error mapping decides the error response.
- Do not build Location from a fake ID before the save succeeds.
- For commands only accepted for later processing, 202 Accepted may fit better than 201 Created.

You can return 201 with no body if the contract permits:

~~~java
Mono<ResponseEntity<Void>> create(CreateUserRequest request) {
    return service.create(request)
        .map(user -> ResponseEntity
            .created(URI.create("/users/" + user.id()))
            .<Void>build());
}
~~~

If you need a body containing the newly created resource, use body(user). If no body is needed, use build() with the appropriate generic type.

## 7. 204 No Content and Bodyless Responses

HTTP 204 indicates the request succeeded but the response has no content. Do not attach a body publisher that might emit data to a 204 response.

~~~java
@DeleteMapping("/users/{id}")
Mono<ResponseEntity<Void>> delete(@PathVariable long id) {
    return service.delete(id)
        .thenReturn(ResponseEntity.noContent().build());
}
~~~

This is a snippet: assume service.delete returns Mono<Void> and completes normally when deletion finishes. thenReturn builds a 204 ResponseEntity after the command completes. If delete fails, thenReturn does not run and the error is propagated downstream.

Another option is:

~~~java
@DeleteMapping("/users/{id}")
Mono<Void> delete(@PathVariable long id) {
    return service.delete(id);
}
~~~

If no status/header customization is needed, returning Mono<Void> may suffice; choose the endpoint semantics explicitly and verify the actual response with WebTestClient.

Statuses that should not have a body according to HTTP semantics include 204 No Content and 304 Not Modified. For these responses, do not try to send empty JSON just to have a payload; body absence is part of the contract.

## 8. Headers: Deciding at the Builder and Preserving the Contract

The ResponseEntity builder helps create headers intentionally:

~~~java
ResponseEntity<User> response = ResponseEntity.ok()
    .contentType(MediaType.APPLICATION_JSON)
    .header("X-Correlation-ID", correlationId)
    .cacheControl(CacheControl.noCache())
    .eTag(etag)
    .body(user);
~~~

Commonly encountered headers:

| Header | Purpose | Notes |
| --- | --- | --- |
| Content-Type | Body format | Choose compatible with codec and client |
| Location | URI of the new resource or redirect target | Commonly used with 201 Created |
| ETag | Validator for a representation | Needs to be computed from appropriate content/version |
| Last-Modified | Time validator | Needs accurate time semantics |
| Cache-Control | Caching policy | Consider private data and proxies |
| Vary | States which request headers affect representation | Important for content negotiation/caching |
| Correlation header | Request tracking | Do not put secrets/PII into headers arbitrarily |

Use headers(HttpHeaders) or headers(Consumer<HttpHeaders>) when multiple headers are needed; avoid creating invalid headers or concatenating strings from unvalidated data. Do not set Content-Length manually for streams of unknown size. The server/codec usually manages framing suited to the transport.

### 8.1. Headers Depending on Asynchronous Results

If ETag or Location depends on loaded data, create the ResponseEntity **after the data is available**:

~~~java
Mono<ResponseEntity<User>> response = service.findById(id)
    .map(user -> ResponseEntity.ok()
        .eTag(user.versionTag())
        .header("X-User-Version", user.version())
        .body(user))
    .defaultIfEmpty(ResponseEntity.<User>notFound().build());
~~~

If status/headers are fixed regardless of body, ResponseEntity<Mono<T>> can be appropriate. If status/headers depend on the result, use an outer publisher.

### 8.2. Conditional Requests and 304

ETag can be used to check whether the client already has the current representation. When appropriate, you can use ServerWebExchange/request condition mechanisms to return 304 and omit the body. Do not compare If-None-Match strings naively if full HTTP validator semantics (weak/strong ETag, wildcards, and multiple tags) must be respected. Use Spring's dedicated APIs or an appropriate HTTP library.

## 9. Streaming Bodies: Status/Headers Chosen Up Front, Body Not Yet Complete

A ResponseEntity<Flux<T>> response can stream many elements:

~~~java
@GetMapping(value = "/numbers", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
ResponseEntity<Flux<Integer>> numbers() {
    Flux<Integer> body = Flux.range(1, 3);

    return ResponseEntity.ok()
        .contentType(MediaType.TEXT_EVENT_STREAM)
        .body(body);
}
~~~

In a real application, the source may be infinite or come from a broker. In that case:

- Status and headers are chosen when ResponseEntity is created.
- WebFlux subscribes to the body publisher and writes elements according to demand/transport.
- The body is not necessarily collected into a list before sending.
- The client subscriber can cancel when closing the connection.
- Errors from Flux after the response commits cannot change status/headers already sent.
- Do not hold the whole stream in RAM just to be able to pick a final status; streaming inherently has no "final result" before starting.

If you need status based on whether **the source has at least one element**, you may have to inspect/peek the data before creating the response. However, that can change buffering, latency, cancellation, and source semantics. For infinite streams, waiting for completion to pick a status is not feasible. API design should pick the status based on conditions knowable up front, while post-commit errors are handled according to stream semantics.

## 10. Errors Before and After Response Commit

This is a critical boundary when using ResponseEntity<Mono<T>> or ResponseEntity<Flux<T>>.

### 10.1. Error When the Outer Publisher Has Not Emitted ResponseEntity Yet

~~~java
Mono<ResponseEntity<User>> response = service.findById(id)
    .map(user -> ResponseEntity.ok(user));
~~~

If service.findById emits an error before a ResponseEntity is produced, the outer Mono terminates with onError. Spring WebFlux can pass the error to an exception handler/global error handler to pick an appropriate response, provided the response has not committed.

### 10.2. Error in the Body Publisher Before Writing the Body

~~~java
ResponseEntity<Mono<User>> response =
    ResponseEntity.ok(service.findById(id));
~~~

Status/headers were already chosen in the entity, but commit timing depends on the adapter starting to write the response. If the body publisher errors before the server commits, the framework can still handle the error depending on the pipeline/adapter. Do not build a contract that relies on a body error "certainly" changing the status; if the status needs to reflect lookup errors, wait for the lookup in the outer publisher and build ResponseEntity afterward.

### 10.3. Error After the Body Has Started Writing

Once the response has committed, status and headers have been sent. If the body Flux continues to error:

- A 200 already sent cannot be changed to 500.
- The server can close the connection or report a write error per transport.
- The client may see the body cut off mid-stream.
- The application should log, emit metrics, and design appropriate retries/heartbeats/protocol events.

For SSE, if the business logic needs to report an error in the stream, you can emit an error-type event per the application schema before ending normally, if security policy and protocol permit. Do not confuse an error event in the body with HTTP status 500.

## 11. onErrorResume and Exception Handlers When Creating ResponseEntity

Errors can be mapped into responses directly inside the pipeline:

~~~java
Mono<ResponseEntity<User>> response = service.findById(id)
    .map(user -> ResponseEntity.ok(user))
    .onErrorResume(AccessDeniedException.class, error ->
        Mono.just(ResponseEntity.<User>status(HttpStatus.FORBIDDEN).build())
    );
~~~

This snippet requires importing the relevant types and the application's exceptions. Use onErrorResume when error handling is part of the endpoint's local logic. Do not catch every Throwable and return 200 or 400 arbitrarily; infrastructure errors, programming errors, and business errors need different mappings.

For centralized mapping, use @RestControllerAdvice and @ExceptionHandler:

~~~java
@RestControllerAdvice
class ApiExceptionHandler {
    @ExceptionHandler(UserNotFoundException.class)
    ResponseEntity<ProblemDetail> notFound(UserNotFoundException error) {
        ProblemDetail body = ProblemDetail.forStatusAndDetail(
            HttpStatus.NOT_FOUND,
            error.getMessage()
        );
        body.setTitle("User not found");
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(body);
    }
}
~~~

This is a snippet; you need to import ProblemDetail, HttpStatus, the annotations, and the application's exceptions. ProblemDetail is the structured HTTP error model in Spring 6+. Make sure messages returned to clients do not disclose SQL, stack traces, tokens, or internal information.

Exception handlers are also subject to the commit boundary: if the response has already sent headers/partial body, the handler cannot roll back the sent response to change the status.

## 12. ResponseEntity Does Not Make Blocking Code Reactive

A common mistake is placing a blocking call inside a controller and wrapping it with ResponseEntity:

~~~java
@GetMapping("/legacy/{id}")
ResponseEntity<User> legacy(@PathVariable long id) {
    User user = jdbcRepository.findByIdBlocking(id);
    return ResponseEntity.ok(user);
}
~~~

The return type ResponseEntity<User> does not change the nature of JDBC. The method still blocks the thread calling the controller.

If an older blocking API must be used, defer the call and move it onto a scheduler meant for blocking:

~~~java
@GetMapping("/legacy/{id}")
Mono<ResponseEntity<User>> legacy(@PathVariable long id) {
    return Mono.fromCallable(() -> jdbcRepository.findByIdBlocking(id))
        .subscribeOn(Schedulers.boundedElastic())
        .map(user -> ResponseEntity.ok(user))
        .defaultIfEmpty(ResponseEntity.<User>notFound().build());
}
~~~

This is an illustrative snippet. fromCallable defers the call until subscription; subscribeOn(boundedElastic) isolates the blocking operation from the event loop; map selects the response after a result is obtained. JDBC still blocks a worker while running and does not turn into non-blocking I/O. If possible, prefer a reactive driver such as R2DBC for a genuinely reactive processing path.

Do not use block() in a controller:

~~~java
User user = service.findById(id).block();
return ResponseEntity.ok(user);
~~~

block() blocks the calling thread and may be rejected by Reactor on threads marked non-blocking. Compose publishers with map, flatMap, switchIfEmpty, onErrorResume, and return them to WebFlux.

## 13. Complete Java 17+ Spring Boot WebFlux Demo

This example illustrates three contracts:

1. Mono<ResponseEntity<User>>: look up a user then choose 200/404.
2. ResponseEntity<Mono<User>>: fixed status 200 even though the body may be empty.
3. ResponseEntity<Flux<ServerSentEvent<String>>>: fixed status/headers and a streaming body.

### 13.1. Project Structure

~~~text
response-entity-demo/
  build.gradle
  src/
    main/
      java/demo/
        ResponseEntityDemoApplication.java
        User.java
        CreateUserRequest.java
        UserService.java
        UserController.java
    test/
      java/demo/
        ResponseEntityControllerTest.java
~~~

### 13.2. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.6'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
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
~~~

Spring Boot manages compatible versions of Spring Framework, Reactor, and related libraries through dependency management. Do not add a different Reactor version yourself without a clear compatibility reason.

### 13.3. ResponseEntityDemoApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ResponseEntityDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ResponseEntityDemoApplication.class, args);
    }
}
~~~

### 13.4. User.java

~~~java
package demo;

public record User(long id, String name) {
}
~~~

### 13.5. CreateUserRequest.java

~~~java
package demo;

public record CreateUserRequest(String name) {
}
~~~

### 13.6. UserService.java

~~~java
package demo;

import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class UserService {
    public Mono<User> findById(long id) {
        if (id == 1L) {
            return Mono.just(new User(1L, "Mai"));
        }
        return Mono.empty();
    }

    public Mono<User> create(CreateUserRequest request) {
        return Mono.just(new User(2L, request.name()));
    }

    public Flux<String> events() {
        return Flux.just("created", "updated");
    }
}
~~~

This is an in-memory service for demo purposes. In a real application, the methods can call a reactive repository, WebClient, or another publisher.

### 13.7. UserController.java

~~~java
package demo;

import java.net.URI;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
public class UserController {
    private final UserService service;

    public UserController(UserService service) {
        this.service = service;
    }

    // Outer Mono decides the response after the lookup completes.
    @GetMapping("/users/{id}")
    public Mono<ResponseEntity<User>> find(@PathVariable long id) {
        return service.findById(id)
            .map(user -> ResponseEntity.ok(user))
            .defaultIfEmpty(ResponseEntity.<User>notFound().build());
    }

    // Status/headers are chosen immediately; the body publisher may be empty.
    @GetMapping("/users/{id}/body-only")
    public ResponseEntity<Mono<User>> bodyOnly(@PathVariable long id) {
        return ResponseEntity.ok()
            .contentType(MediaType.APPLICATION_JSON)
            .header("X-Response-Mode", "body-only")
            .body(service.findById(id));
    }

    // Status 201 and Location are created after obtaining the resource ID.
    @PostMapping("/users")
    public Mono<ResponseEntity<User>> create(
            @RequestBody CreateUserRequest request) {
        return service.create(request)
            .map(user -> ResponseEntity
                .created(URI.create("/users/" + user.id()))
                .body(user));
    }

    // Fixed status/headers; the Flux body is written as a stream.
    @GetMapping(value = "/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public ResponseEntity<Flux<ServerSentEvent<String>>> events() {
        Flux<ServerSentEvent<String>> body = service.events()
            .map(value -> ServerSentEvent.builder(value)
                .event("status")
                .build());

        return ResponseEntity.ok()
            .contentType(MediaType.TEXT_EVENT_STREAM)
            .header("X-Stream-Mode", "live")
            .body(body);
    }
}
~~~

### 13.8. Running the Application

In the project directory:

~~~bash
./gradlew bootRun
~~~

If Gradle is installed:

~~~bash
gradle bootRun
~~~

Call the endpoints:

~~~bash
curl -i http://localhost:8080/users/1
curl -i http://localhost:8080/users/99
curl -i http://localhost:8080/users/99/body-only
curl -i -X POST http://localhost:8080/users \
  -H "Content-Type: application/json" \
  -d '{"name":"An"}'
curl -N -i http://localhost:8080/events
~~~

Key results to observe:

| Request | Expected status | Body/headers |
| --- | --- | --- |
| GET /users/1 | 200 | JSON user Mai |
| GET /users/99 | 404 | No user body |
| GET /users/99/body-only | 200 | Empty body, with X-Response-Mode: body-only |
| POST /users | 201 | JSON user An and Location /users/2 |
| GET /events | 200 | text/event-stream, two status events |

The /users/99/body-only endpoint intentionally shows the difference: the controller selects 200 before the body is subscribed; an empty body does not automatically change status to 404.

## 14. Testing with WebTestClient and JUnit 5

Create src/test/java/demo/ResponseEntityControllerTest.java:

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ResponseEntityControllerTest {
    @Autowired
    WebTestClient client;

    @Test
    void foundResourceReturns200AndBody() {
        client.get()
            .uri("/users/1")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody(User.class)
            .isEqualTo(new User(1L, "Mai"));
    }

    @Test
    void missingResourceReturns404() {
        client.get()
            .uri("/users/99")
            .exchange()
            .expectStatus().isNotFound()
            .expectBody()
            .isEmpty();
    }

    @Test
    void emptyReactiveBodyDoesNotChangePreselectedStatus() {
        client.get()
            .uri("/users/99/body-only")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals("X-Response-Mode", "body-only")
            .expectBody()
            .isEmpty();
    }

    @Test
    void createReturns201AndLocation() {
        client.post()
            .uri("/users")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new CreateUserRequest("An"))
            .exchange()
            .expectStatus().isCreated()
            .expectHeader().exists("Location")
            .expectBody(User.class)
            .isEqualTo(new User(2L, "An"));
    }

    @Test
    void eventEndpointDeclaresStreamingContentType() {
        client.get()
            .uri("/events")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().contentTypeCompatibleWith(
                MediaType.TEXT_EVENT_STREAM
            )
            .expectHeader().valueEquals("X-Stream-Mode", "live");
    }
}
~~~

Run:

~~~bash
./gradlew test
~~~

Or:

~~~bash
gradle test
~~~

Five tests verify status, body, headers, and the difference between outer Mono and inner Mono. The SSE test checks metadata; if you need to test individual events and cancellation, you can use returnResult(ServerSentEvent.class) or a suitable streaming client, then verify each event instead of only checking the header.

There is no need for Thread.sleep to test reactive response bodies. WebTestClient waits for the response per the exchange contract and assertions; if testing a publisher with timers, use virtual time at the Reactor unit-test layer or configure an explicit timeout.

## 15. When to Use ResponseEntity vs. ResponseStatusException?

There are two common ways to express errors.

**Returning ResponseEntity directly:**

~~~java
return Mono.just(ResponseEntity.status(HttpStatus.CONFLICT)
    .body(errorBody));
~~~

Suitable when the error is a normal outcome branch of the endpoint and specific headers/body control is needed.

**Throwing an exception and letting an exception handler map it:**

~~~java
return service.findById(id)
    .switchIfEmpty(Mono.error(new UserNotFoundException(id)));
~~~

Then @RestControllerAdvice maps UserNotFoundException to 404. Suitable when you want to centralize error policies and avoid having every controller build responses manually.

ResponseStatusException can also express a specific status:

~~~java
return Mono.error(new ResponseStatusException(
    HttpStatus.NOT_FOUND,
    "User not found"
));
~~~

Do not mix multiple styles arbitrarily. Choose a consistent convention for domain errors, validation, authentication/authorization, and infrastructure errors.

## 16. Common Mistakes

| Mistake | Consequence | How to handle it |
| --- | --- | --- |
| Using ResponseEntity<Mono<User>> and expecting an empty body to automatically become 404 | Status was already chosen as 200 | Use Mono<ResponseEntity<User>> if the lookup decides the status |
| Using Mono<ResponseEntity<User>> but forgetting to handle an empty source | No ResponseEntity emitted; response does not clearly express resource absence | defaultIfEmpty(notFound().build()) or switchIfEmpty |
| Thinking creating ResponseEntity means the response was already sent over the network | Framework still has to process metadata and write the body | Distinguish entity creation from response commit |
| Changing status after body streaming has started | HTTP headers already committed; status cannot change | Pick status before streaming, handle body errors per protocol |
| Using ResponseEntity<Flux<T>> then collectList() on the whole stream | Loses streaming benefits and increases RAM/latency | Return Flux directly if the contract is a stream |
| Setting Content-Type incompatible with the body codec | Client fails to decode properly or server cannot write | Choose a media type matching the body and message writer |
| Returning a body for 204 No Content | Violates HTTP semantics | Use ResponseEntity<Void> and noContent().build() |
| Using ResponseEntity.ok(service.block()) in WebFlux | Blocks the event loop | Compose Mono/Flux and return a reactive type |
| Attaching Location before create completes | Location may be wrong or ID may not exist yet | Create ResponseEntity after the service returns the resource |
| Catching every error and returning 400 | Hides server or programming errors | Map each exception type according to the contract |
| Using ResponseEntity<Mono<T>> for an endpoint that needs to choose status based on body | Cannot change status when body turns out empty later | Use outer Mono<ResponseEntity<T>> |
| Thinking a body publisher error always changes status to 500 | If the response already committed, the old status cannot change | Surface knowable errors before commit; design stream errors |
| Setting Content-Length manually for an infinite stream | Wrong header, client/proxy misbehaves | Let the server manage streaming framing |
| Using Mono.empty() to represent an error | Empty is normal completion, not onError | Return 404/fallback or emit an error per contract |
| Using ResponseEntity on every endpoint | Increases boilerplate when custom metadata is not needed | Return Mono<T>/Flux<T> if the default suffices |

## 17. Response Design Checklist

Before finishing an endpoint, answer these questions:

1. Is the status known as soon as the controller is invoked?
2. If an asynchronous lookup is needed, does the result decide 200/404/409?
3. Do headers depend on an ID/version/data created later?
4. Is the body a single value, a single-value publisher, or a multi-element stream?
5. If the body publisher is empty, what is the expected status?
6. If the body publisher errors before commit, which error handler processes it?
7. If the stream errors after commit, what signal will the client receive?
8. Are 201 + Location, 204 without a body, ETag, or Cache-Control needed?
9. Does the body match the right codec/content type?
10. Are there any blocking calls or block() on the request path?
11. Does the response expose sensitive information in headers/body/error details?
12. Have status, headers, empty body, errors, and cancellation been tested with WebTestClient/StepVerifier?

| Requirement | Suggested return type |
| --- | --- |
| Lookup decides 200 or 404 | Mono<ResponseEntity<T>> |
| Create returns 201 + Location from ID | Mono<ResponseEntity<T>> |
| Fixed metadata, asynchronous body | ResponseEntity<Mono<T>> |
| Fixed metadata, streaming body | ResponseEntity<Flux<T>> |
| Available value, custom header | ResponseEntity<T> |
| Reactive body, default status suffices | Mono<T> or Flux<T> |
| Command completed, 204 | Mono<ResponseEntity<Void>> or Mono<Void> per contract |

## 18. Self-Check Questions with Answers

**Question 1.** ResponseEntity<Mono<User>> contains Mono.empty() and was created with ResponseEntity.ok(). Does the status automatically become 404?

**Answer:** No. The status was already chosen as 200; an empty body only means no body value is emitted.

**Question 2.** Which type fits when the lookup result decides status 200 or 404?

**Answer:** Mono<ResponseEntity<User>>, because the outer Mono can emit ResponseEntity after the lookup reveals whether data exists.

**Question 3.** ResponseEntity<Flux<Event>> returns a stream and the 10th event emits an error after 9 events were sent. Can status 200 be changed to 500?

**Answer:** Not if the response has already committed. The client may observe the stream terminating mid-way; appropriate logging and protocol-level error handling are needed.

**Question 4.** Why is ResponseEntity.created(location).body(user) usually constructed inside map after create completes?

**Answer:** Because the official ID/URI exists only after saving succeeds; only then is the right Location known and 201 can be emitted.

**Question 5.** When is ResponseEntity<Mono<T>> a sensible choice?

**Answer:** When status and headers are known in advance while the body arrives asynchronously, for example an endpoint that always returns 200 with a body publisher.

**Question 6.** How do Mono.empty() and Mono.error(ex) differ?

**Answer:** Empty is normal completion with no element; error is a failure terminal signal. The controller must choose 404/fallback for empty per business logic and map error by exception type.

**Question 7.** Why should you not use block() in a WebFlux controller?

**Answer:** It blocks the calling thread, which may be a non-blocking event loop, reducing request throughput and risking rejection by Reactor.

**Question 8.** Which status usually appears with the Location header when creating a resource?

**Answer:** Usually 201 Created. The URI should point to the newly created resource per the API contract.

**Question 9.** An error occurs in the outer Mono<ResponseEntity<T>> before ResponseEntity is emitted. Can it be mapped to 500 by an exception handler?

**Answer:** Yes, if the response has not committed and a suitable handler exists. When an error occurs after the response has committed, status/headers already sent cannot be changed.

**Question 10.** If an endpoint returns a valid empty list, must it use 404?

**Answer:** No. For collection search, 200 and an empty list is usually a valid outcome; 404 is usually reserved for a specifically identified resource that does not exist.

## 19. Key Takeaways and References

- ResponseEntity represents status, headers, and body; it does not write HTTP bytes the moment it is created.
- Mono<ResponseEntity<T>> lets you **wait for the result to choose metadata**.
- ResponseEntity<Mono<T>> and ResponseEntity<Flux<T>> let you **choose metadata first, write the reactive body later**.
- An empty body does not automatically equate to 404; endpoint semantics must be defined.
- After the response commits, status and headers already sent cannot be changed; streaming errors after commit must be handled according to the stream/transport contract.
- Use ResponseEntity when custom status/header/body semantics are needed; otherwise, Mono<T>/Flux<T> is usually simpler.
- Do not use block() in reactive request handlers; do not let blocking I/O run on the event loop.

Official documentation:

1. [Spring Framework Reference — WebFlux Controller Return Values](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html): semantics of ResponseEntity, Mono<ResponseEntity<T>>, ResponseEntity<Mono<T>>, and ResponseEntity<Flux<T>>.
2. [Spring Framework Javadoc — ResponseEntity](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/ResponseEntity.html): builders, status, headers, and body.
3. [Spring Framework Reference — WebFlux Exceptions](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-exceptions.html): @ExceptionHandler and @ControllerAdvice.
4. [Spring Framework Reference — WebFlux HTTP Message Codecs](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html): writing bodies with reactive codecs.
5. [Spring Framework Reference — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): testing WebFlux endpoints.
6. [Project Reactor Reference — Error Handling](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html): handling onError, fallbacks, and terminal signals.
