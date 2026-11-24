# Creating Responses with bodyValue, body, and build

**Context:** Spring Framework Reactive → **Functional Endpoints (WebFlux.fn)**.

In WebFlux.fn, a handler takes a `ServerRequest` and returns a `Mono<ServerResponse>`. `ServerResponse` describes the HTTP response: status, headers, and body. When creating a response, the three common methods are:

- `bodyValue(value)` — writes **a concrete Java value** as the body.
- `body(publisher, elementType)` — writes the body from a **Publisher** such as `Mono<T>` or `Flux<T>`; the framework subscribes and converts the elements into HTTP content.
- `build()` or `build(voidPublisher)` — creates a response **without a body**; the second overload waits for a publisher to complete before the response is committed.

The easiest point of confusion is that `build()` has two different meanings depending on the builder: `RouterFunctions.route().build()` creates a router, whereas `ServerResponse.ok().build()` creates an HTTP response without a body. In this lesson, `build` mainly refers to `ServerResponse`.

## 1. How Does WebFlux.fn Create Responses?

WebFlux.fn is Spring WebFlux's functional programming model. Instead of declaring routes with annotations on a controller, the application combines `RouterFunction` for routing with `HandlerFunction` for handling requests.

A `HandlerFunction<ServerResponse>` receives a `ServerRequest` and returns a `Mono<ServerResponse>`:

```java
HandlerFunction<ServerResponse> hello =
        request -> ServerResponse.ok().bodyValue("Hello World");
```

`Mono<ServerResponse>` is the asynchronous result of the handler. It allows reading the body, querying data, or writing data to finish before the response is created. `ServerResponse` itself is a response description; WebFlux's server adapter and response result handler are responsible for writing it to the HTTP connection.

A minimal router:

```java
@Bean
RouterFunction<ServerResponse> routes(PeopleHandler handler) {
    return RouterFunctions.route()
            .GET("/people/{id}", handler::getOne)
            .GET("/people", handler::list)
            .POST("/people", handler::create)
            .DELETE("/people/{id}", handler::delete)
            .build();
}
```

This is a snippet that requires the `PeopleHandler` class and Spring WebFlux configuration. `RouterFunctions.route().build()` finishes declaring routes and returns a `RouterFunction<ServerResponse>`. The referenced handler methods will return `Mono<ServerResponse>`.

When a request matches a route, the `HandlerFunction` is called. `ServerResponseResultHandler` processes the result and calls `writeTo` to write the response. Therefore, a handler should **return a publisher**, not call `subscribe()` or `block()` itself to force the response to run.

## 2. ServerResponse and BodyBuilder

`ServerResponse` is the abstraction representing the HTTP response on the server side. Commonly used factory methods:

| Factory | Status | Purpose |
|---|---:|---|
| `ServerResponse.ok()` | 200 | Return data successfully |
| `ServerResponse.created(uri)` | 201 | Create a new resource, with a `Location` header |
| `ServerResponse.accepted()` | 202 | Accepted for processing, commonly used for async workflows |
| `ServerResponse.noContent()` | 204 | Success without a body |
| `ServerResponse.badRequest()` | 400 | Invalid request |
| `ServerResponse.notFound()` | 404 | Resource not found |
| `ServerResponse.status(code)` | Custom | Custom status |

The factories return the appropriate builder. For example:

```java
Mono<ServerResponse> response =
        ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(person);
```

Methods such as `contentType`, `header`, `headers`, `contentLength`, and `hint` configure metadata/serialization. Then `bodyValue`, `body`, or `build` creates the `Mono<ServerResponse>`.

Example of adding a header:

```java
return ServerResponse.ok()
        .header("X-Request-Source", "catalog")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(person);
```

`ServerResponse` has an immutable contract once created; the builder is where the response is configured before building. You should not keep a shared mutable builder across multiple requests. Create a new response builder for each request handling.

## 3. bodyValue(value): Returning a Concrete Value

`bodyValue` is used when the application already has **a concrete Java object** and wants to use that object as the response body.

```java
Person person = new Person(7, "An");

return ServerResponse.ok()
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(person);
```

The framework selects an `HttpMessageWriter` and codec matching the data type along with `Content-Type`. If a JSON codec is configured, the `Person` object is serialized into JSON.

Example body the client might receive:

```json
{
  "id": 7,
  "name": "An"
}
```

This is an illustrative JSON representation; the actual content depends on fields, Jackson configuration, serializers, and DTO annotations.

### 3.1. When is bodyValue suitable?

- A DTO that has already been retrieved from cache or is already available in memory.
- A synchronous computation result.
- A domain object that has already been converted to a response DTO.
- A finite, small, and clearly bounded collection when you want to return it as a JSON array.

Example of returning an existing list:

```java
List<PersonDto> people = List.of(
        new PersonDto(1, "An"),
        new PersonDto(2, "Binh")
);

return ServerResponse.ok()
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(people);
```

Here `List<PersonDto>` is an already created value. `bodyValue` does not turn the list into a reactive stream. If the list is large, collecting all the data before returning the response can consume significant memory.

### 3.2. bodyValue is not the way to put a Mono or Flux into a response

This is a common mistake:

```java
Mono<Person> person = repository.findById(id);

// Wrong: bodyValue takes an object, not a Publisher to stream.
return ServerResponse.ok()
        .bodyValue(person);
```

In Spring WebFlux, `bodyValue` rejects a `Publisher` or a producer recognized by `ReactiveAdapterRegistry`; in that case it can throw `IllegalArgumentException`.

Use `body` when the actual value is a publisher:

```java
Mono<Person> person = repository.findById(id);

return ServerResponse.ok()
        .contentType(MediaType.APPLICATION_JSON)
        .body(person, Person.class);
```

If the repository returns empty, `body` does not automatically turn the response into 404. The handler must explicitly decide the not-found case with `switchIfEmpty`.

## 4. body(publisher, elementType): Returning Reactive Data

`body` is used when the body comes from an asynchronous source, such as:

- `Mono<Person>`: at most one object.
- `Flux<Person>`: multiple objects emitted over time.
- Another `Publisher<T>` compatible with Reactive Streams.
- Another producer that can be converted into a Publisher by Spring's `ReactiveAdapterRegistry` via the appropriate overload.

Example of a `Mono`:

```java
Mono<Person> person = repository.findById(id);

return ServerResponse.ok()
        .contentType(MediaType.APPLICATION_JSON)
        .body(person, Person.class);
```

Example of a `Flux`:

```java
Flux<Person> people = repository.findAll();

return ServerResponse.ok()
        .contentType(MediaType.APPLICATION_JSON)
        .body(people, Person.class);
```

Important difference: `body` does not require the handler to collect the whole stream into a list first. The writer consumes the publisher and serializes elements according to the capabilities of the codec/transport. This is the natural choice for responses with reactive data.

### 4.1. Meaning of elementType

Common overload:

```java
.body(publisher, Person.class)
```

The second parameter is **the type of each element emitted by the publisher**, not the type of the whole publisher. For `Flux<Person>`, the element type is `Person.class`.

If each item is a generic type, you can use `ParameterizedTypeReference` to preserve generic information:

```java
Flux<Map<String, Object>> rows = repository.findRows();

return ServerResponse.ok()
        .contentType(MediaType.APPLICATION_JSON)
        .body(rows,
                new ParameterizedTypeReference<Map<String, Object>>() {});
```

This is a snippet that requires importing `ParameterizedTypeReference` and the corresponding types. The type reference describes **one Map element**, because the publisher emits multiple Maps. Do not pass `ParameterizedTypeReference<List<Map<...>>>` unless each element is actually a list.

### 4.2. body can take a Mono or Flux

Both are Publishers:

```java
Mono<Person> one = repository.findById(7);

Mono<ServerResponse> oneResponse =
        ServerResponse.ok().body(one, Person.class);

Flux<Person> many = repository.findAll();

Mono<ServerResponse> manyResponse =
        ServerResponse.ok().body(many, Person.class);
```

In the first example, the publisher emits at most one person. In the second example, the publisher can emit multiple people. The same `body` API supports both; the source type and endpoint contract determine the semantics.

If `Mono<Person>` is empty, the response body has no person. If the API requirement is to return 404 when there is no resource, handle empty before creating the response:

```java
return repository.findById(id)
        .flatMap(person ->
                ServerResponse.ok()
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(person))
        .switchIfEmpty(ServerResponse.notFound().build());
```

### 4.3. body does not automatically choose status based on data

`body` only configures the response body. It does not infer on its own that:

- Empty means 404.
- Having data means 200.
- A repository error means 404.
- A publisher emitting multiple items means 206 Partial Content.

The status is a decision of the handler and the API contract. Set the status explicitly with `ok()`, `created()`, `notFound()`, or `status(...)`.

## 5. body(BodyInserter): Controlling How the Body Is Written

`BodyInserter` is the abstraction that describes how content is inserted into the response. The overload:

```java
.body(BodyInserter<?, ? super ServerHttpResponse> inserter)
```

allows using a built-in inserter or a custom inserter. For ordinary cases, `bodyValue` and `body(publisher, type)` are more concise APIs.

Example using `BodyInserters.fromValue`:

```java
return ServerResponse.ok()
        .contentType(MediaType.APPLICATION_JSON)
        .body(BodyInserters.fromValue(person));
```

This is semantically equivalent to `bodyValue(person)`. It is useful when you need to integrate with the `BodyInserters` API or when another method has already created a BodyInserter.

With a publisher:

```java
return ServerResponse.ok()
        .contentType(MediaType.APPLICATION_JSON)
        .body(BodyInserters.fromPublisher(people, Person.class));
```

This is the way to create an inserter from a publisher, which is semantically equivalent to `body(people, Person.class)` in this case.

### 5.1. When is a custom BodyInserter needed?

It may be needed when:

- A shared abstraction already provides a `BodyInserter`.
- You need to combine a specialized body-writing approach with the response builder.
- You need to integrate an existing content-writing strategy.
- You want to reuse a body inserter factory function across multiple handlers.

You should not create a custom inserter just to replace a simple `bodyValue` call. A custom writer must respect lifecycle, cancellation, backpressure, and buffer ownership.

### 5.2. Hints for codecs

`BodyBuilder.hint(key, value)` and `hints(...)` pass hints to codecs that support them. Example with Jackson JSON View:

```java
return ServerResponse.ok()
        .contentType(MediaType.APPLICATION_JSON)
        .hint(Jackson2CodecSupport.JSON_VIEW_HINT, PublicView.class)
        .bodyValue(person);
```

This is a snippet that requires a Jackson codec and an appropriate view class. A hint only takes effect if the codec in use understands that key; it is not a general security filter. Do not rely on JSON View to replace authorization or response DTO design.

## 6. build(): Creating a Response Without a Body

`build()` creates a `ServerResponse` without writing a response body.

Example:

```java
return ServerResponse.noContent().build();
```

The result is a 204 No Content response, with no body.

A 201 Created response with a Location header:

```java
URI location = URI.create("/people/7");

return ServerResponse.created(location).build();
```

`created(location)` sets status 201 and the `Location` header. `build()` finishes the response without a body.

Other examples:

```java
return ServerResponse.notFound().build();

return ServerResponse.badRequest().build();

return ServerResponse.accepted().build();
```

Do not attach a JSON body to status 204. According to HTTP semantics, 204 indicates no content in the response; if the client needs a result object, use an appropriate status such as 200 or 201 with a body.

### 6.1. build() does not wait for another business task

Suppose:

```java
Mono<Void> save = repository.save(person);

return ServerResponse.ok().build();
```

This snippet **does not use the save publisher**. If the handler does not compose `save` into the response pipeline elsewhere, the save is not executed by the code above. `build()` only creates a bodyless response.

Do not understand `build()` as "wait for every previous operation in local variables". A reactive publisher only runs when subscribed to and connected to the execution chain.

## 7. build(Publisher<Void>): A Bodyless Response That Waits for Work to Complete

The `build(Publisher<Void>)` overload also creates a bodyless response, but the response is committed when the passed-in publisher **completes**.

Here is the core difference:

```java
Mono<Void> save = repository.save(person);

return ServerResponse.ok().build(save);
```

If `save` completes successfully, `build(save)` creates the response. If `save` emits an error, the error follows the resulting publisher and the normal response is not committed by this success path.

Spring describes this overload as building a response without a body and only committing the response when the supplied publisher completes. It is suitable for tasks with type `Mono<Void>` such as save/delete/audit where the client does not need to receive a response object.

### 7.1. Signal flow

```text
Handler creates Mono<Void> save
          │
          ▼
ServerResponse.ok().build(save)
          │
          ▼
Framework subscribes to Mono<ServerResponse>
          │
          ▼
Publisher save executes
     ┌────┴──────────┐
     │               │
 onComplete        onError
     │               │
     ▼               ▼
Create/commit    Propagate error to
bodyless         WebFlux error
response         handling
```

If the publisher is `Mono.empty()`, it completes immediately when subscribed to; therefore the response can be created right after that completion. If the publisher is `Mono.never()`, the response will wait indefinitely if there is no timeout or cancellation. If the publisher errors, the handler returns a reactive error instead of treating the operation as successful.

### 7.2. Using build(Publisher<Void>) for create/delete

Example of a delete operation:

```java
Mono<Void> deletion = repository.deleteById(id);

return ServerResponse.noContent().build(deletion);
```

The 204 response is only created after the delete publisher completes. However, if the repository treats "ID not found" as normal completion, this snippet still returns 204. If the API needs 404 when the resource does not exist, the repository must provide a result with enough information to distinguish and the handler must map it explicitly.

Example of recording an audit before returning a response:

```java
Mono<Void> audit = auditService.recordAccess(userId);

return ServerResponse.ok().build(audit);
```

The bodyless response is created after the audit publisher completes. If audit is required for the request, an audit error will cause the workflow to fail. If audit is only best-effort, define a separate policy instead of accidentally dropping errors.

### 7.3. build(Publisher<Void>) does not send that publisher as the body

This is an API distinction error:

```java
// Not the way to stream a list of Person:
return ServerResponse.ok().build(repository.findAll());
```

`build(Publisher<Void>)` requires a publisher representing **completion**, not response items. `Flux<Person>` is not an appropriate `Publisher<Void>`.

To write a list of Person, use:

```java
return ServerResponse.ok()
        .contentType(MediaType.APPLICATION_JSON)
        .body(repository.findAll(), Person.class);
```

`body` uses the elements to create response content; `build` only uses the completion publisher to decide when to commit the empty response.

## 8. Comparing the Three Ways to Create a Response

| Approach | Input | Has body? | Waits for publisher? | Example |
|---|---|---:|---:|---|
| `bodyValue(value)` | Concrete object | Yes | No body publisher to wait for | `Person` |
| `body(publisher, type)` | Publisher emitting data | Yes, per emitted item | Yes, writer consumes publisher | `Flux<Person>` |
| `build()` | No publisher needed | No | Does not wait for other tasks | `204 No Content` |
| `build(voidPublisher)` | Publisher representing completion only | No | Yes, waits for completion | `Mono<Void>` |

Example with the same data:

```java
Person person = new Person(7, "An");

// Already existing object:
Mono<ServerResponse> a =
        ServerResponse.ok().bodyValue(person);

// Publisher with only one item:
Mono<Person> personMono = Mono.just(person);
Mono<ServerResponse> b =
        ServerResponse.ok().body(personMono, Person.class);

// No body, do not wait for task:
Mono<ServerResponse> c =
        ServerResponse.noContent().build();

// No body, wait for save operation:
Mono<Void> save = repository.save(person);
Mono<ServerResponse> d =
        ServerResponse.noContent().build(save);
```

The right choice is based on **the input type and response semantics**, not on whether the method name is short or long.

## 9. Practical Example: Handler for the Person Resource

A handler class can group read, list, create, and delete operations:

```java
import java.net.URI;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import static org.springframework.web.reactive.function.server.ServerResponse.*;

public class PeopleHandler {

    private final PeopleRepository repository;

    public PeopleHandler(PeopleRepository repository) {
        this.repository = repository;
    }

    public Mono<ServerResponse> getOne(ServerRequest request) {
        int id = Integer.parseInt(request.pathVariable("id"));

        return repository.findById(id)
                .flatMap(person -> ok()
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(person))
                .switchIfEmpty(notFound().build());
    }

    public Mono<ServerResponse> list(ServerRequest request) {
        Flux<Person> people = repository.findAll();

        return ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(people, Person.class);
    }

    public Mono<ServerResponse> create(ServerRequest request) {
        Mono<Person> saved = request.bodyToMono(Person.class)
                .flatMap(repository::save);

        return saved.flatMap(person -> created(
                        URI.create("/people/" + person.id()))
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(person));
    }

    public Mono<ServerResponse> delete(ServerRequest request) {
        int id = Integer.parseInt(request.pathVariable("id"));

        return noContent().build(repository.deleteById(id));
    }
}
```

This is a structurally complete handler, though it depends on `Person`, `PeopleRepository`, and the application's repository implementation. Assumptions:

- `findById` returns `Mono<Person>`, empty if not found.
- `findAll` returns `Flux<Person>`.
- `save` returns the saved `Mono<Person>` with an ID.
- `deleteById` returns `Mono<Void>` that completes when the delete operation completes.

Analyzing each method:

**getOne:** `bodyValue` is used when `findById` has emitted a concrete Person. If empty, `switchIfEmpty` chooses a 404 response without a body. A repository error still goes through the error signal; it does not automatically turn into 404.

**list:** `body` takes `Flux<Person>`. The handler does not need `collectList()`; the response writer consumes the publisher and serializes each element according to the codec. The client may receive a JSON array; how writing and flushing work depends on the media type, writer, and transport.

**create:** the request body is decoded into a `Person`, the repository saves and emits the saved person. Then the handler creates a 201 response with Location and a JSON body. `bodyValue` is called when the saved object is available.

**delete:** `build(Publisher<Void>)` ensures a bodyless response is created after the completion of the delete operation. If the repository emits an error, the response follows the error path.

### Another create approach: returning only status and Location

If the API does not need to return the created object, you can use `build()` after having the save result:

```java
public Mono<ServerResponse> createWithoutBody(ServerRequest request) {
    return request.bodyToMono(Person.class)
            .flatMap(repository::save)
            .flatMap(saved -> created(
                    URI.create("/people/" + saved.id()))
                    .build());
}
```

Here `build()` is **inside flatMap after save has emitted saved**. Therefore the handler still waits for save; the waiting comes from the `flatMap` chain. This differs from `build()` called standalone before chaining the save publisher.

## 10. bodyValue, body, and build in RouterFunction

A router can combine multiple response types:

```java
@Bean
RouterFunction<ServerResponse> peopleRoutes(PeopleHandler handler) {
    return RouterFunctions.route()
            .GET("/people/{id}", handler::getOne)
            .GET("/people", handler::list)
            .POST("/people", handler::create)
            .DELETE("/people/{id}", handler::delete)
            .build();
}
```

Distinguish the two `build` calls:

- `RouterFunctions.route().build()` — creates a `RouterFunction` from route definitions.
- `ServerResponse.noContent().build()` — creates a `Mono<ServerResponse>` without a body.
- `ServerResponse.ok().build(publisher)` — creates an empty response after publisher completion.

Three calls with the same name but different builders, return types, and purposes. When reading code, always look at the object before the dot to determine whether you are building a router or an HTTP response.

## 11. Status, Headers, and Body Must Be Consistent

Body methods do not decide the status on their own. The handler should choose the status according to the API contract.

| Scenario | Commonly used response | Body |
|---|---|---|
| Successfully reading one resource | 200 OK + `bodyValue` | Resource |
| Reading a list from a repository | 200 OK + `body` | `Flux<T>` |
| Creating new and returning the resource | 201 Created + Location + `bodyValue` | New resource |
| Creating new without needing content | 201 Created + Location + `build()` | None |
| Deleting successfully | 204 No Content + `build(voidPublisher)` | None |
| Accepting a background job | 202 Accepted + `bodyValue` or `build()` | Possibly a job ID |
| Not found | 404 Not Found + `build()` | None |
| Invalid request | 400 Bad Request or 422 per contract | Possibly an error DTO |

Example of creating a response with a cache header:

```java
return ServerResponse.ok()
        .cacheControl(CacheControl.maxAge(Duration.ofMinutes(5)))
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(person);
```

Examples such as adding an ETag or Location need to be computed accurately per resource. Do not set Content-Length manually for a stream if the exact number of bytes to be written is not yet known; the encoder may generate data over time.

### 11.1. 202 Accepted does not mean the work is finished

An API that accepts background jobs typically returns 202 when the job has been accepted for processing, not necessarily waiting until processing finishes.

If the application enqueues a durable job and has a job ID:

```java
return ServerResponse.accepted()
        .location(URI.create("/jobs/" + job.id()))
        .bodyValue(new JobAccepted(job.id()));
```

If you use `build(jobProcessingPublisher)`, the handler instead waits for that publisher to complete before the response is committed. This can have different semantics from "accepted, process later". Distinguish between **enqueuing succeeded** and **the entire job finished processing**.

## 12. Handling Empty and Error Properly

A body publisher can:

- Emit one or more items.
- Complete without emitting an item.
- Emit an error before any item.
- Emit partial data and then error.

### 12.1. Empty does not automatically mean Not Found

`Mono.empty()` is successful completion with no items. Only when the endpoint contract defines "no item" as meaning the resource does not exist should you turn it into a 404.

```java
return repository.findById(id)
        .flatMap(person -> ServerResponse.ok().bodyValue(person))
        .switchIfEmpty(ServerResponse.notFound().build());
```

### 12.2. Errors must not be turned into empty arbitrarily

`onErrorResume(error -> Mono.empty())` can mask a database outage as if the resource did not exist. Distinguish business errors, codec errors, persistence errors, and the empty state.

If you need to turn domain errors into specific statuses, use exception mapping or a centralized error handler. `bodyValue`, `body`, and `build` do not replace error-handling mechanisms.

### 12.3. Body publisher errors after the response has started writing

With streaming responses, the writer may have already sent the status and headers before the body publisher errors. The server usually cannot go back to change a committed status or replace a partial stream with a complete error JSON.

If a streaming endpoint needs to express mid-stream errors, design protocol-level error events, sequence IDs, or a resume mechanism. Do not assume `body(Flux<T>, T.class)` turns every late error into a complete 500 response.

## 13. Streaming, Backpressure, and Memory

`body(Flux<T>, Class<T>)` is the natural choice when the response is produced gradually. However, using `Flux` does not automatically guarantee every layer is streaming seamlessly.

Points to note:

- Do not `collectList()` an unbounded or very large source just to call `bodyValue`.
- Use `Flux<T>` if each element can be encoded and sent with a suitable media type.
- Clearly define JSON array, NDJSON, or SSE according to the client contract.
- Limit upstream concurrency; do not create unbounded inner calls.
- Measure buffers, direct memory, response latency, and slow clients.
- When the client disconnects, cancellation can propagate to the publisher; external side effects do not roll back automatically.
- If the stream must replay, use an event store/broker and sequence instead of expecting `body` to store history itself.

NDJSON example:

```java
return ServerResponse.ok()
        .contentType(MediaType.APPLICATION_NDJSON)
        .body(repository.streamEvents(), EventDto.class);
```

SSE example:

```java
return ServerResponse.ok()
        .contentType(MediaType.TEXT_EVENT_STREAM)
        .body(eventService.stream(), ServerSentEvent.class);
```

These are snippets; the SSE type can be `ServerSentEvent<EventDto>` and needs the corresponding element type. The media type must match how the client reads it. `body` only connects the publisher to the response writer; it does not create SSE framing on its own if the source data is not represented in the right type.

## 14. Do Not Subscribe or Block Yourself to Create a Response

Do not do the following:

```java
public Mono<ServerResponse> wrong(ServerRequest request) {
    repository.save(request.bodyToMono(Person.class))
            .subscribe();

    return ServerResponse.ok().build();
}
```

This snippet creates a separate subscription and the response can complete before the save. Save errors do not automatically go into the handler response; client disconnect does not necessarily cancel the child work.

Chain the publisher instead:

```java
public Mono<ServerResponse> correct(ServerRequest request) {
    return request.bodyToMono(Person.class)
            .flatMap(repository::save)
            .flatMap(saved -> ServerResponse.created(
                    URI.create("/people/" + saved.id()))
                    .bodyValue(saved));
}
```

Similarly, do not use `block()` in a WebFlux handler to obtain an object synchronously and then build the response. That blocks the reactive thread and breaks the non-blocking model. Use `flatMap`, `map`, `then`, and return `Mono<ServerResponse>`.

## 15. Standalone Java 17+ Program: Distinguishing bodyValue, body, and build

The following example uses Maven and Spring WebFlux. The program creates `ServerResponse` objects to illustrate how the builder chooses a body and how `build(Publisher<Void>)` waits for completion. It **does not start an HTTP server and does not serialize the body to a socket**; the actual HTTP writing is handled by the WebFlux server adapter and response writer.

Structure:

```text
server-response-builder-demo/
├── pom.xml
└── src/main/java/demo/ServerResponseBuilderDemo.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>server-response-builder-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-webflux</artifactId>
            <version>6.2.16</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.4.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/demo/ServerResponseBuilderDemo.java`:

```java
package demo;

import java.net.URI;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.server.ServerResponse;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class ServerResponseBuilderDemo {

    record Person(int id, String name) { }

    public static void main(String[] args) {
        Person person = new Person(7, "An");

        ServerResponse valueResponse = ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(person)
                .block();

        System.out.println("bodyValue status="
                + valueResponse.statusCode().value());

        ServerResponse publisherResponse = ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(Flux.just(
                        person,
                        new Person(8, "Binh")),
                        Person.class)
                .block();

        System.out.println("body publisher status="
                + publisherResponse.statusCode().value());

        ServerResponse emptyResponse = ServerResponse.noContent()
                .build()
                .block();

        System.out.println("build status="
                + emptyResponse.statusCode().value());

        AtomicInteger completedWork = new AtomicInteger();

        Mono<Void> save = Mono.fromRunnable(() -> {
            completedWork.incrementAndGet();
            System.out.println("save publisher completed");
        });

        ServerResponse afterSave = ServerResponse
                .created(URI.create("/people/7"))
                .build(save)
                .block();

        System.out.println("build(publisher) status="
                + afterSave.statusCode().value()
                + ", completedWork=" + completedWork.get());
    }
}
```

Run from the directory containing `pom.xml` with JDK 17+ and Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.ServerResponseBuilderDemo
```

**Expected standard output** (excluding Maven messages):

```text
bodyValue status=200
body publisher status=200
build status=204
save publisher completed
build(publisher) status=201, completedWork=1
```

Explanation:

1. `bodyValue(person)` creates a 200 response whose body value is one Person.
2. `body(Flux.just(...), Person.class)` creates a 200 response whose body comes from a publisher emitting two People.
3. `noContent().build()` creates a 204 response without a body.
4. `created(uri).build(save)` subscribes to the completion publisher. The callback increments the counter and prints the save complete line before `block()` receives the 201 response.
5. `block()` only appears in `main` of the illustrative program to wait for the result. Do not put `block()` in a WebFlux handler or on an event loop.

The example demonstrates the builder API and when the completion publisher runs. It does not check JSON bytes over the network, build real HTTP headers, or replace an integration test with WebTestClient.

## 16. Testing Handlers and Responses

You should check both response metadata and publisher lifecycle.

### 16.1. StepVerifier for handlers

For a handler returning `Mono<ServerResponse>`:

```java
StepVerifier.create(handler.getOne(request))
        .assertNext(response ->
                assertEquals(200, response.statusCode().value()))
        .verifyComplete();
```

This is a snippet that requires JUnit, Reactor Test, a request fixture, and imports. Checking status is not enough to prove the body is serialized properly; an HTTP boundary test is needed for the writer/codec.

### 16.2. WebTestClient testing real HTTP

`WebTestClient` can bind to a router function or a real server to check status, headers, and body:

```java
webTestClient.get()
        .uri("/people/7")
        .exchange()
        .expectStatus().isOk()
        .expectHeader()
        .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
        .expectBody()
        .jsonPath("$.id").isEqualTo(7)
        .jsonPath("$.name").isEqualTo("An");
```

This is a snippet that needs a `WebTestClient` bound to the application/RouterFunction and corresponding test data.

### 16.3. Testing that build(Publisher<Void>) waits for completion

You can use a controllable publisher to prove the response has not appeared before completion. Unit-level examples with `MonoProcessor`/`Sinks.One` need to manage subscriptions and test synchronization; do not use `Thread.sleep` to guess timing. In an integration test, verify that when the write operation has not completed yet, the response has not been committed.

Additionally, test cases such as:

- Repository emits empty.
- Repository emits an error before creating the response.
- Body publisher emits partially and then errors.
- Client cancels while the body is streaming.
- Response uses the right status, Content-Type, and Location.
- Body has the right JSON schema or NDJSON/SSE framing.
- No task has a detached subscription.

## 17. Common Mistakes

1. **Using `bodyValue(mono)`.** `bodyValue` takes a concrete object; use `body(mono, Type.class)` for a publisher.
2. **Using `build()` expecting to wait for a save.** `build()` does not accept a publisher; chain operations via `flatMap` or use `build(Mono<Void>)`.
3. **Using `build(fluxOfPeople)` to return a list.** This overload indicates completion with no body; use `body(flux, Person.class)`.
4. **Using `bodyValue` for an infinite stream.** It is not a streaming API; use `body(Flux, type)`.
5. **Forgetting Content-Type.** The writer may not choose the representation the client wants; set content type per the API contract when needed.
6. **Assuming an empty body automatically returns 404.** Empty is a completion signal with no items; the handler must use `switchIfEmpty` if empty means not found.
7. **Assuming a body publisher error always produces a complete HTTP 500.** If the response is already committed, the status cannot be reversed; a stream error can cause the response to terminate abnormally.
8. **Calling subscribe inside a handler.** Creates a separate subscription and detaches errors/cancellation from the response.
9. **Calling block in a handler.** Blocks the reactive thread; compose publishers instead.
10. **Using build(Publisher<Void>) with a publisher that emits values.** Convert it to `Mono<Void>` if only completion is needed, or use `body` if you want to send items.
11. **Returning 202 after waiting for the entire job to complete.** Check semantics; 202 usually indicates accepted rather than necessarily finished processing.
12. **Returning 204 with a JSON body.** 204 has no content; choose another status if a body is needed.
13. **Using bodyValue(large List) for unbounded data.** An aggregated collection can consume lots of memory; consider Flux and a streaming format.
14. **Not declaring the element type properly.** `body(publisher, Person.class)` describes each element, not the type of the whole publisher.
15. **Confusing RouterFunctions.Builder.build with ServerResponse.build.** Identify the builder receiver and return type before concluding.
16. **Treating BodyInserter as the place to perform business logic.** The inserter is responsible for writing the representation; business logic should sit in the service/publisher before the response is created.
17. **Using JSON View as an authorization mechanism.** Codec hints only adjust serialization; you still need to check permissions and DTOs.
18. **Forgetting to handle save errors when using build(save).** Errors must go into error handling; do not swallow or log and then return success.
19. **Setting a wrong or missing Location after create.** Location must point to the resource per contract; do not build URIs from unvalidated input.
20. **Assuming a built response object means the body is already sent.** The server still has to write the response through the writer/adapter; I/O errors can happen during that stage.

## 18. API Selection Checklist

Before writing a handler, answer:

- Is the body already a concrete object? If yes, `bodyValue` is usually suitable.
- Is the body a `Mono<T>` or `Flux<T>`? Use `body(publisher, elementType)`.
- Is each element a generic type? Use `ParameterizedTypeReference`.
- Is custom body insertion needed? Consider `BodyInserter`.
- Is the response bodyless and not waiting on another task? Use `build()`.
- Is the response bodyless but must wait for an operation to complete? Use `build(Publisher<Void>)`.
- Do you need to return 404 when the repository is empty? Handle `switchIfEmpty` before creating the response.
- Do the status and headers match the HTTP contract? Explicitly choose 200/201/202/204 and Location.
- Is the body streaming? Choose a suitable media type and publisher, avoiding unbounded aggregation.
- Are there errors or cancellations? Keep every task in the same publisher chain and manage resource lifecycles properly.
- Is body serialization tested? Use WebTestClient, not just asserting `ServerResponse.statusCode`.
- Are you confusing the router builder with the response builder? Verify the object type before `build()`.

**Key takeaway:** `bodyValue` is for an existing object; `body` is for a publisher emitting content; `build()` creates a bodyless response; `build(Publisher<Void>)` creates a bodyless response after the completion publisher finishes. All four options return a publisher for WebFlux to manage. Choose properly based on **the input data, whether a body needs to be sent, and when the response is allowed to commit**.

## References

- Spring Framework — [Functional Endpoints (WebFlux.fn): HandlerFunction and ServerResponse](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html).
- Spring Framework — [ServerResponse.BodyBuilder Javadoc: bodyValue, body, hints](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/web/reactive/function/server/ServerResponse.BodyBuilder.html).
- Spring Framework — [ServerResponse.HeadersBuilder Javadoc: build(), build(Publisher<Void>)](https://docs.spring.io/spring-framework/docs/5.3.20/javadoc-api/org/springframework/web/reactive/function/server/ServerResponse.HeadersBuilder.html).
- Spring Framework — [BodyInserters API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/BodyInserters.html).
- Spring Framework — [WebFlux.fn running a server and response handling](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html).
- Project Reactor — [Mono and Flux reference](https://projectreactor.io/docs/core/release/reference/).
- Project Reactor — [Testing with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html).
