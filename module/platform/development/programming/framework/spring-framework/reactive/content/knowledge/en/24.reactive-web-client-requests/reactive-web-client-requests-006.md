# Sending a Publisher with body and Preserving Element Types in Spring WebClient

## 1. Why Does WebClient Have body(Publisher, elementType)?

Spring WebClient is a reactive HTTP client. When sending a request, the application often does not have the entire body ready as a single complete object. Data may come from a `Mono<T>`, `Flux<T>`, a file source, another service, or an asynchronous processing pipeline.

WebClient lets you pass a publisher directly into the request body:

~~~java
Flux<Person> people = loadPeople();

Mono<Void> result = webClient.post()
    .uri("/people/import")
    .contentType(MediaType.APPLICATION_JSON)
    .body(people, Person.class)
    .retrieve()
    .bodyToMono(Void.class);
~~~

Here:

- `people` is the asynchronous data source.
- Each element emitted by the publisher has type `Person`.
- `Person.class` tells WebClient the type of **each element** to encode.
- The appropriate codec converts each Java value into HTTP request body bytes.
- WebClient manages the subscription and request writing; the application composes the returned publisher instead of calling `subscribe()` itself.

The key point to understand accurately is that `body(publisher, elementType)` does not declare the type of the outer publisher. It declares the type of the **values that the publisher emits**. For `Flux<Person>`, the element type is `Person`; for `Mono<List<Person>>`, the element type is `List<Person>`.

## 2. Commonly Used body() Overloads

`WebClient.RequestBodySpec` provides multiple overloads for passing a publisher or a producer adaptable to a publisher:

| API | Input | Meaning |
| --- | --- | --- |
| `body(Publisher<T>, Class<T>)` | Publisher and element class | Sends publisher, declaring element type with Class |
| `body(Publisher<T>, ParameterizedTypeReference<T>)` | Publisher and generic type reference | Sends publisher when the element type is generic |
| `body(Object producer, Class<?> elementClass)` | Publisher or producer supported by ReactiveAdapterRegistry | Used when the source is not directly a Publisher |
| `body(Object producer, ParameterizedTypeReference<?> elementTypeRef)` | Adaptable producer and generic element type | Preserves generic type for adaptable producers |
| `body(BodyInserter)` | BodyInserter | Controls body writing via an inserter |
| `bodyValue(Object)` | A concrete body value | Sends an already available object/value |

The two most commonly used overloads in Java are:

~~~java
.body(personMono, Person.class)
~~~

and:

~~~java
.body(personFlux, Person.class)
~~~

Both declare the element type as `Person`; the difference is whether the publisher emits at most one element or multiple elements.

### body(Publisher, Class)

~~~java
Mono<Person> onePerson = findPerson();
Flux<Person> manyPeople = findPeople();

webClient.post()
    .uri("/people/one")
    .contentType(MediaType.APPLICATION_JSON)
    .body(onePerson, Person.class)
    .retrieve()
    .bodyToMono(Void.class);

webClient.post()
    .uri("/people/batch")
    .contentType(MediaType.APPLICATION_JSON)
    .body(manyPeople, Person.class)
    .retrieve()
    .bodyToMono(Void.class);
~~~

`Class<T>` is sufficient when the element type is a concrete class such as `Person`, `Order`, `String`, or `byte[]`.

### body(Publisher, ParameterizedTypeReference)

When each element is a generic type, `Class<T>` cannot fully represent type arguments due to Java type erasure. Use `ParameterizedTypeReference<T>`:

~~~java
Flux<ApiEnvelope<Person>> events = loadEvents();

webClient.post()
    .uri("/events")
    .contentType(MediaType.APPLICATION_NDJSON)
    .body(
        events,
        new ParameterizedTypeReference<ApiEnvelope<Person>>() {}
    )
    .retrieve()
    .bodyToMono(Void.class);
~~~

An anonymous subclass of `ParameterizedTypeReference` retains the generic type information at runtime. WebClient can pass the full type to the codec, such as `ApiEnvelope<Person>`, instead of only knowing the raw class `ApiEnvelope`.

## 3. T Is the Type of Each Element, Not the Publisher Type

This is an easy point to misread in the generic signature:

~~~java
<T, P extends Publisher<T>>
RequestHeadersSpec<?> body(
    P publisher,
    Class<T> elementClass
);
~~~

In the signature above:

- `P` is the publisher type, such as `Mono<Person>` or `Flux<Person>`.
- `T` is the emitted element type, such as `Person`.
- `elementClass` describes `T`, not `P`.

Examples:

| Publisher | Element type T | Invocation |
| --- | --- | --- |
| `Mono<Person>` | `Person` | `body(mono, Person.class)` |
| `Flux<Person>` | `Person` | `body(flux, Person.class)` |
| `Mono<List<Person>>` | `List<Person>` | `body(mono, new ParameterizedTypeReference<List<Person>>() {})` |
| `Flux<ApiEnvelope<Person>>` | `ApiEnvelope<Person>` | `body(flux, new ParameterizedTypeReference<ApiEnvelope<Person>>() {})` |
| `Flux<Map<String, Person>>` | `Map<String, Person>` | `body(flux, new ParameterizedTypeReference<Map<String, Person>>() {})` |

Example with `Mono<List<Person>>`:

~~~java
Mono<List<Person>> peopleMono = loadPeopleAsList();

webClient.post()
    .uri("/people/list")
    .contentType(MediaType.APPLICATION_JSON)
    .body(
        peopleMono,
        new ParameterizedTypeReference<List<Person>>() {}
    )
    .retrieve()
    .bodyToMono(Void.class);
~~~

The publisher emits **one value** of type `List<Person>`. The type reference must describe `List<Person>`, not `Mono<List<Person>>`.

Similarly, with `Flux<ApiEnvelope<Person>>`, each `onNext` emits one envelope. The type reference describes `ApiEnvelope<Person>`, not `Flux<ApiEnvelope<Person>>`.

## 4. Preserving Generic Types Despite Java Type Erasure

Java generic types lose most type argument information at runtime. For example, `List<Person>` and `List<Order>` both have the raw class `List.class`.

If you only pass:

~~~java
.body(envelopes, ApiEnvelope.class)
~~~

the codec only receives the raw type `ApiEnvelope`. When you need to serialize/deserialize the exact generic structure, use:

~~~java
.body(
    envelopes,
    new ParameterizedTypeReference<ApiEnvelope<Person>>() {}
)
~~~

Example definitions:

~~~java
public record ApiEnvelope<T>(
    String eventType,
    T data
) {}

public record Person(
    String name,
    int age
) {}
~~~

Publisher:

~~~java
Flux<ApiEnvelope<Person>> events = Flux.just(
    new ApiEnvelope<>("created", new Person("An", 30)),
    new ApiEnvelope<>("updated", new Person("Binh", 28))
);
~~~

Sending the request:

~~~java
Mono<Void> sent = webClient.post()
    .uri("/person-events")
    .contentType(MediaType.APPLICATION_NDJSON)
    .body(
        events,
        new ParameterizedTypeReference<ApiEnvelope<Person>>() {}
    )
    .retrieve()
    .bodyToMono(Void.class);
~~~

The type reference informs the codec that each event has the structure `ApiEnvelope<Person>`. If type arguments are omitted or a raw type is used, the codec may only see a generic map/object or lack sufficient information to handle nested types as intended.

### A Publisher Emitting a List vs. a Publisher Emitting Individual Persons

The following two cases have different body semantics:

~~~java
Flux<Person> people = Flux.just(
    new Person("An", 30),
    new Person("Binh", 28)
);

Flux<List<Person>> batches = Flux.just(
    List.of(new Person("An", 30)),
    List.of(new Person("Binh", 28))
);
~~~

- `Flux<Person>`: each element is a Person.
- `Flux<List<Person>>`: each element is a list of Persons.

If serializing a multi-value publisher into a JSON array, the first case produces an array of Persons; the second case produces an array of arrays. Choose the element type matching the exact data each `onNext` emits.

## 5. Distinguishing body() from bodyValue()

The two APIs serve different purposes.

### body() Accepts a Publisher

Use when the body is produced asynchronously:

~~~java
Flux<Person> people = findPeople();

webClient.post()
    .uri("/people")
    .contentType(MediaType.APPLICATION_JSON)
    .body(people, Person.class)
    .retrieve()
    .bodyToMono(Void.class);
~~~

WebClient subscribes to the publisher while writing the request body. The application does not need to—and should not—subscribe manually to send the request.

### bodyValue() Accepts an Already-Available Value

Use when you already have an object or collection:

~~~java
Person person = new Person("An", 30);

webClient.post()
    .uri("/people")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(person)
    .retrieve()
    .bodyToMono(Void.class);
~~~

For a concrete collection with a generic type, Spring Framework 6.2 provides an overload:

~~~java
List<Person> people = List.of(
    new Person("An", 30),
    new Person("Binh", 28)
);

webClient.post()
    .uri("/people/list")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(
        people,
        new ParameterizedTypeReference<List<Person>>() {}
    )
    .retrieve()
    .bodyToMono(Void.class);
~~~

The type reference in the `bodyValue(value, typeRef)` overload describes the **entire body value**, because there is no publisher element here.

### Do Not Use bodyValue() to Pass a Publisher

The following is incorrect:

~~~java
Flux<Person> people = findPeople();

webClient.post()
    .uri("/people")
    .bodyValue(people);
~~~

`bodyValue` requires a concrete body value. If the object is a `Publisher` or a producer recognized by `ReactiveAdapterRegistry`, Spring throws `IllegalArgumentException` and instructs you to use `body(...)` or the corresponding BodyInserter.

Correct approach:

~~~java
webClient.post()
    .uri("/people")
    .body(people, Person.class);
~~~

Rule of thumb:

- Already have an object/list: `bodyValue(value)`.
- Have a `Mono<T>` or `Flux<T>`: `body(publisher, elementType)`.
- Have a generic type: use `ParameterizedTypeReference`.
- Need to customize how the body is written: use `BodyInserter`.

## 6. body() and BodyInserters

`body(...)` is a convenient shortcut on WebClient. Underneath, it uses a `BodyInserter` to write the body to the request.

You can create an inserter explicitly:

~~~java
Flux<Person> people = findPeople();

Mono<Void> result = webClient.post()
    .uri("/people")
    .contentType(MediaType.APPLICATION_JSON)
    .body(BodyInserters.fromPublisher(people, Person.class))
    .retrieve()
    .bodyToMono(Void.class);
~~~

Common factories:

| Factory | Used for |
| --- | --- |
| `BodyInserters.fromPublisher(publisher, Class)` | Publisher with a concrete element class |
| `BodyInserters.fromPublisher(publisher, ParameterizedTypeReference)` | Publisher with a generic element type |
| `BodyInserters.fromProducer(producer, Class)` | Producer adapted to a Publisher by ReactiveAdapterRegistry |
| `BodyInserters.fromProducer(producer, ParameterizedTypeReference)` | Adaptable producer with a generic element type |
| `BodyInserters.fromValue(value)` | A concrete body value |
| `BodyInserters.fromResource(resource)` | Sending a Resource, such as a file |

Generic inserter example:

~~~java
Flux<ApiEnvelope<Person>> events = loadEvents();

Mono<Void> result = webClient.post()
    .uri("/person-events")
    .contentType(MediaType.APPLICATION_NDJSON)
    .body(BodyInserters.fromPublisher(
        events,
        new ParameterizedTypeReference<ApiEnvelope<Person>>() {}
    ))
    .retrieve()
    .bodyToMono(Void.class);
~~~

In most cases, `body(publisher, elementType)` is more concise. Use BodyInserter when you want to reuse body-writing logic or integrate with APIs that accept a BodyInserter.

Do not use `BodyInserters.fromValue(publisher)` as a substitute for `fromPublisher`; the value inserter is also meant for a concrete value.

## 7. Content-Type Determines How the Publisher Is Encoded

The element type answers **what type each Java value has**. The `Content-Type` header answers **which format the body is sent in**. These two factors work together so Spring selects the appropriate `HttpMessageWriter`/encoder.

For example:

~~~java
.body(people, Person.class)
~~~

does not yet specify whether the body should be a JSON array, NDJSON, or another format. Select the media type according to the endpoint contract:

~~~java
.contentType(MediaType.APPLICATION_JSON)
~~~

or:

~~~java
.contentType(MediaType.APPLICATION_NDJSON)
~~~

The `Accept` header, on the other hand, describes the response format the client wants, not the request body format:

~~~java
.accept(MediaType.APPLICATION_JSON)
~~~

A request can send NDJSON while receiving a JSON response:

~~~java
webClient.post()
    .uri("/people/import")
    .contentType(MediaType.APPLICATION_NDJSON)
    .accept(MediaType.APPLICATION_JSON)
    .body(people, Person.class)
    .retrieve()
    .bodyToMono(ImportSummary.class);
~~~

## 8. Flux<Person> with application/json vs. application/x-ndjson

This is an important distinction when sending a multi-element publisher.

### application/json

With Spring WebFlux's default Jackson encoder, a multi-value publisher with media type `application/json` is collected via `Flux.collectToList()`, then serialized as a JSON array.

Example:

~~~java
Flux<Person> people = Flux.just(
    new Person("An", 30),
    new Person("Binh", 28)
);

webClient.post()
    .uri("/people")
    .contentType(MediaType.APPLICATION_JSON)
    .body(people, Person.class);
~~~

The body takes the form:

~~~json
[
  {"name":"An","age":30},
  {"name":"Binh","age":28}
]
~~~

This is a single array-shaped JSON document. The default encoder waits for the publisher to complete so it has the collection to serialize. It fits finite batches; it is unsuitable for never-ending streams if the client/server expects a complete JSON array.

### application/x-ndjson

With a streaming media type such as `application/x-ndjson`, the Jackson encoder encodes, writes, and flushes each value individually in line-delimited JSON format.

~~~java
webClient.post()
    .uri("/people/stream")
    .contentType(MediaType.APPLICATION_NDJSON)
    .body(people, Person.class);
~~~

The body takes the form:

~~~text
{"name":"An","age":30}
{"name":"Binh","age":28}
~~~

Each line is an independent JSON document. The server can decode each record as data arrives without waiting for the entire publisher to complete.

### Comparison

| Criterion | application/json | application/x-ndjson |
| --- | --- | --- |
| Body structure | Single JSON document, typically an array | Multiple JSON documents, one record per line |
| Default multi-value Flux | Collects into a List then serializes | Encodes, writes, and flushes each element |
| Client parsing | JSON document/array parser | Line-by-line parser |
| Best suited for | Finite batches | Streaming records |
| Infinite publisher | Unsuitable for arrays that need closing | Can continuously emit records |
| Body termination | Ends the JSON document | Ends the HTTP stream |

Note: flushing in the encoder does not guarantee every proxy or client displays data immediately. If end-to-end streaming is required, test server transport, proxies, and clients together.

## 9. Mono, Flux, Empty Publishers, and Data Sources

### Mono<T>: Sending at Most One Element

~~~java
Mono<Person> person = personService.findById("42");

Mono<Void> sent = webClient.put()
    .uri("/people/42")
    .contentType(MediaType.APPLICATION_JSON)
    .body(person, Person.class)
    .retrieve()
    .bodyToMono(Void.class);
~~~

If the publisher completes empty, no object is emitted. That differs from sending a JSON object with empty fields or sending JSON `null`. The endpoint contract should clearly specify whether an absent request body is allowed.

### Flux<T>: Sending Multiple Elements

~~~java
Flux<Person> people = personService.findAll();

Mono<Void> sent = webClient.post()
    .uri("/people/import")
    .contentType(MediaType.APPLICATION_NDJSON)
    .body(people, Person.class)
    .retrieve()
    .bodyToMono(Void.class);
~~~

### Iterable or Collection Sources

If a collection is already available:

~~~java
List<Person> list = loadList();

Mono<Void> sent = webClient.post()
    .uri("/people")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(
        list,
        new ParameterizedTypeReference<List<Person>>() {}
    )
    .retrieve()
    .bodyToMono(Void.class);
~~~

If you want to emit items one by one from a collection:

~~~java
Flux<Person> publisher = Flux.fromIterable(list);

Mono<Void> sent = webClient.post()
    .uri("/people/stream")
    .contentType(MediaType.APPLICATION_NDJSON)
    .body(publisher, Person.class)
    .retrieve()
    .bodyToMono(Void.class);
~~~

Both approaches share the same source data but have different body contracts: one body value is a JSON collection, whereas a multi-item publisher is encoded with a streaming media type.

## 10. Producers That Are Not Directly Publishers

The overload:

~~~java
body(Object producer, Class<?> elementClass)
~~~

accepts a producer that `ReactiveAdapterRegistry` can convert into a Publisher. Reactive types or coroutine types supported by an adapter can be used through this overload.

In Java with Reactor, `Mono` and `Flux` are already Publishers, so use the overload:

~~~java
.body(publisher, Element.class)
~~~

If integrating another reactive library or a producer type like Kotlin `Deferred`, verify whether it has a matching adapter in `ReactiveAdapterRegistry`. Not every object with a `subscribe` or `get` method is automatically recognized by WebClient as a request body publisher.

If the producer has a generic element type, pass the corresponding `ParameterizedTypeReference` so the codec receives the exact element type.

## 11. BodyInserter for Forms and Multipart

WebClient also supports specially structured request body types.

### URL-Encoded Forms

A `MultiValueMap<String, String>` can be sent as form data:

~~~java
MultiValueMap<String, String> form = new LinkedMultiValueMap<>();
form.add("name", "An");
form.add("role", "developer");

Mono<Void> result = webClient.post()
    .uri("/form")
    .bodyValue(form)
    .retrieve()
    .bodyToMono(Void.class);
~~~

Or using:

~~~java
.body(BodyInserters.fromFormData("name", "An")
    .with("role", "developer"))
~~~

### Multipart

For standard multipart, use `MultipartBodyBuilder` to build parts with different data types:

~~~java
MultipartBodyBuilder builder = new MultipartBodyBuilder();
builder.part("description", "Quarterly report");
builder.part("metadata", new Person("An", 30));
builder.part("file", new FileSystemResource("report.pdf"));

Mono<Void> result = webClient.post()
    .uri("/uploads")
    .body(BodyInserters.fromMultipartData(builder.build()))
    .retrieve()
    .bodyToMono(Void.class);
~~~

If you need to stream multipart sequentially with `PartEvent`, you can pass `Flux<PartEvent>` with element type `PartEvent.class`. Choose between a multipart map and PartEvent according to upload requirements; do not collect large files into a collection when sequential streaming is the goal.

## 12. Request Publishers Are Consumed According to Request Lifecycle

WebClient does not send the body immediately at the line calling `body(...)`. It builds a request specification; only when the exchange is subscribed to does WebClient write the request body and subscribe to the source publisher.

A typical sequence:

~~~text
Create source Mono/Flux
       |
       v
webClient.post().body(publisher, elementType)
       |
       v
retrieve() / exchangeToMono()
       |
       v
Caller subscribes or framework composes publisher
       |
       v
WebClient subscribes to body publisher
       |
       v
Codec encodes each value into bytes
       |
       v
HTTP client transport writes request
       |
       v
Receive response
~~~

Do not manually call `subscribe()` on the body publisher:

~~~java
// Avoid:
people.subscribe(person -> log.info("{}", person));

return webClient.post()
    .uri("/people")
    .body(people, Person.class)
    .retrieve()
    .bodyToMono(Void.class);
~~~

The snippet above can subscribe to the same source twice. With a cold publisher, the source may run twice; with a hot or one-shot publisher, the request may lose data or fail to replay.

If logging is needed, observe within the same pipeline:

~~~java
Flux<Person> observed = people
    .doOnNext(person -> log.debug("Sending person name={}", person.name()));
~~~

Do not log sensitive data or full bodies in production without clear justification and appropriate safeguards.

## 13. Cold Publishers, Hot Publishers, and Retries

Many Reactor publishers are cold: each subscription restarts data generation. For example, `Flux.fromIterable(list)` can usually be resubscribed to.

Some sources are hot or one-shot:

- Event streams from a message broker.
- An incoming request body currently being read.
- A file stream or network response that can only be consumed once.
- A publisher created from a non-replayable callback/event source.

This matters when using retries:

~~~java
webClient.post()
    .uri("/people")
    .body(people, Person.class)
    .retrieve()
    .bodyToMono(Receipt.class)
    .retry(2);
~~~

`retry(2)` can resubscribe to the request publisher and re-execute the HTTP exchange. If the body publisher is not replayable, the retry attempt may lack data or fail. If the server already processed the request before the connection failed, retrying can also repeat business operations.

To retry safely:

1. Determine whether the publisher is replayable.
2. Use a cold source capable of regenerating the body when needed.
3. Design an idempotency key for operations with side effects.
4. Do not retry validation errors or unrecoverable 4xx errors.
5. Cap retry attempts and use appropriate backoff and timeouts.
6. For one-shot bodies, consider creating a fresh publisher per attempt or avoiding automatic retries.

## 14. Backpressure, Cancellation, and Errors While Writing Requests

### Backpressure

The body publisher is consumed according to Reactive Streams. Demand from the HTTP writer/transport propagates through the pipeline to regulate data flow.

Backpressure does not mean the entire request is sent in a single batch, nor that each element maps to a single packet. It regulates data production/consumption across layers.

Avoid:

- `collectList()` on large streams that do not require aggregation.
- Unbounded buffering when the source is faster than the network.
- Converting an entire publisher to `byte[]` when streaming is intended.
- Creating unbounded concurrency for pre-encoding work.

### Cancellation

If the caller cancels the subscription or a timeout occurs, WebClient can cancel body writing and the source publisher. File, socket, or listener sources must have proper lifecycle cleanup.

### Error Signal

If the publisher emits `onError` while writing the request, the request body may terminate abnormally and the server receives an incomplete body. This error differs from an HTTP status error returned by the server.

Do not swallow source errors with `onErrorComplete()` if the server needs to know the request was truncated. Propagate the error or map it according to the business contract.

## 15. Distinguishing Request Write Errors from Response Errors

WebClient has two phases:

1. Sending the request: encoding the body and writing bytes.
2. Receiving the response: reading status, headers, and body.

Example:

~~~java
Mono<ImportReceipt> result = webClient.post()
    .uri("/people/import")
    .contentType(MediaType.APPLICATION_NDJSON)
    .body(people, Person.class)
    .retrieve()
    .bodyToMono(ImportReceipt.class);
~~~

- Encoding failures or body publisher errors occur during the sending phase.
- Server returning HTTP 400/500 is a response status.
- Response decoding errors occur when reading the response body.

By default, `retrieve()` turns 4xx/5xx responses into `WebClientResponseException`. This can be customized:

~~~java
Mono<ImportReceipt> result = webClient.post()
    .uri("/people/import")
    .contentType(MediaType.APPLICATION_NDJSON)
    .body(people, Person.class)
    .retrieve()
    .onStatus(
        status -> status.is4xxClientError(),
        response -> response.createException()
    )
    .bodyToMono(ImportReceipt.class);
~~~

If you need to branch per status and actively consume the response, use `exchangeToMono()`. Either way, read/release the response body according to its lifecycle to avoid holding connections or buffers.

## 16. Reading Responses Is the Reverse of Sending Bodies

Do not confuse:

- `body(publisher, elementType)`: sends the request body.
- `bodyToMono(type)`: reads the response body into a single value.
- `bodyToFlux(type)`: reads the response body into multiple values.

Example reading a JSON array response:

~~~java
Flux<Person> responsePeople = webClient.get()
    .uri("/people")
    .retrieve()
    .bodyToFlux(Person.class);
~~~

Example reading a generic object response:

~~~java
Mono<ApiEnvelope<Person>> response = webClient.get()
    .uri("/person/42")
    .retrieve()
    .bodyToMono(
        new ParameterizedTypeReference<ApiEnvelope<Person>>() {}
    );
~~~

Type references are equally important on the response side because Java type erasure still applies. If the response is `ApiEnvelope<Person>`, do not pass only raw `ApiEnvelope.class` when you need to preserve the inner data type.

## 17. Complete Java 17+ Example with Spring Boot WebFlux

The example below illustrates sending a publisher via WebClient while preserving the element type:

- The client receives `Flux<Person>` as NDJSON at `/api/people/forward`.
- WebClient forwards the same publisher to `/api/internal/people`.
- The downstream request uses `body(people, Person.class)`.
- The target server receives `Flux<Person>` and counts the elements.
- The response is a `BatchReceipt` JSON object.

Project structure:

~~~text
webclient-publisher-body/
├── pom.xml
└── src/
    ├── main/java/com/example/webclientbody/
    │   ├── WebClientBodyApplication.java
    │   ├── WebClientConfig.java
    │   └── PeopleController.java
    └── test/java/com/example/webclientbody/
        └── PeopleControllerTest.java
~~~

File `pom.xml` (Spring Boot 3.5.0, Java 17+):

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>webclient-publisher-body</artifactId>
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
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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

File `src/main/java/com/example/webclientbody/WebClientBodyApplication.java`:

~~~java
package com.example.webclientbody;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebClientBodyApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebClientBodyApplication.class, args);
    }
}
~~~

File `src/main/java/com/example/webclientbody/WebClientConfig.java`:

~~~java
package com.example.webclientbody;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
public class WebClientConfig {

    @Bean
    WebClient downstreamClient(WebClient.Builder builder) {
        return builder.baseUrl("http://localhost:8080").build();
    }
}
~~~

File `src/main/java/com/example/webclientbody/PeopleController.java`:

~~~java
package com.example.webclientbody;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class PeopleController {

    public record Person(String name, int age) {}

    public record BatchReceipt(long accepted) {}

    private final WebClient downstreamClient;

    public PeopleController(WebClient downstreamClient) {
        this.downstreamClient = downstreamClient;
    }

    // Downstream endpoint: receives each Person from NDJSON.
    @PostMapping(
        path = "/internal/people",
        consumes = MediaType.APPLICATION_NDJSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<BatchReceipt> receive(
            @RequestBody Flux<Person> people) {

        return people.count()
            .map(BatchReceipt::new);
    }

    // Gateway endpoint: receives publisher and forwards via WebClient.body().
    @PostMapping(
        path = "/people/forward",
        consumes = MediaType.APPLICATION_NDJSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<BatchReceipt> forward(
            @RequestBody Flux<Person> people) {

        return downstreamClient.post()
            .uri("/api/internal/people")
            .contentType(MediaType.APPLICATION_NDJSON)
            .accept(MediaType.APPLICATION_JSON)
            .body(people, Person.class)
            .retrieve()
            .bodyToMono(BatchReceipt.class);
    }
}
~~~

Run in the `webclient-publisher-body` directory with JDK 17+ and Maven:

~~~bash
mvn spring-boot:run
~~~

Create `people.ndjson` with UTF-8 content:

~~~text
{"name":"An","age":30}
{"name":"Binh","age":28}
~~~

Send request with cURL:

~~~bash
curl.exe -i -X POST http://localhost:8080/api/people/forward ^
  -H "Content-Type: application/x-ndjson" ^
  -H "Accept: application/json" ^
  --data-binary "@people.ndjson"
~~~

Expected response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
~~~

Body:

~~~json
{"accepted":2}
~~~

Data flow:

~~~text
people.ndjson
    |
    v
POST /api/people/forward
    |
    v
@RequestBody Flux<Person>
    |
    v
WebClient.body(people, Person.class)
    |
    v
POST /api/internal/people
    |
    v
@RequestBody Flux<Person>
    |
    v
count()
    |
    v
{"accepted":2}
~~~

This is an in-application relay demo illustrating a publisher passed through WebClient. In production, the downstream is usually a separate service; configure the base URL, authentication, timeouts, connection pool, and retry policy appropriately. Do not leave unprotected internal endpoints publicly accessible just because the demo uses the same server.

## 18. Testing Element Types with WebTestClient

The test below sends a typed publisher to an endpoint accepting NDJSON. The `spring-boot-starter-test` dependency is already declared in the pom.

File `src/test/java/com/example/webclientbody/PeopleControllerTest.java`:

~~~java
package com.example.webclientbody;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Flux;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class PeopleControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void sendsTypedPublisherAsNdjson() {
        Flux<PeopleController.Person> people = Flux.just(
            new PeopleController.Person("An", 30),
            new PeopleController.Person("Binh", 28)
        );

        client.post()
            .uri("/api/internal/people")
            .contentType(MediaType.APPLICATION_NDJSON)
            .body(people, PeopleController.Person.class)
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
            .json("{\"accepted\":2}");
    }
}
~~~

Run:

~~~bash
mvn test
~~~

The test verifies that WebTestClient can encode a publisher according to the declared element type and the endpoint decodes both records into `Flux<Person>`. This is an HTTP integration-level request body test; the relay example in the previous section illustrates WebClient performing the same outbound operation.

## 19. Common Mistakes

1. **Using `bodyValue(flux)`:** wrong API. Publishers must use `body(publisher, elementType)`.
2. **Passing `Flux.class` as the element type:** wrong concept. The element type is the type of each emitted element, such as `Person.class`.
3. **Using a raw class for generic elements:** loses type argument information. Use `ParameterizedTypeReference`.
4. **Creating a type reference for the outer publisher:** for `Flux<ApiEnvelope<Person>>`, the type reference is `ApiEnvelope<Person>`, not `Flux<ApiEnvelope<Person>>`.
5. **Confusing the type references of bodyValue and body:** `bodyValue(value, typeRef)` describes the entire value; `body(publisher, typeRef)` describes each publisher element.
6. **Using `bodyValue` for `Mono<List<Person>>`:** this is still a publisher. Use `body(mono, new ParameterizedTypeReference<List<Person>>() {})`.
7. **Using `body(publisher, List.class)` when needing `List<Person>`:** raw List does not preserve generic Person. Use a type reference.
8. **Not setting Content-Type:** codecs may fail to pick the right writer or the server may misinterpret the format. Set Content-Type according to the endpoint contract.
9. **Confusing Accept with Content-Type:** Accept describes the desired response; Content-Type describes the request body.
10. **Assuming Flux + application/json always streams item by item:** the default Jackson encoder collects a multi-value Flux into a List and serializes a JSON array.
11. **Using application/json for an infinite Flux:** the default encoder requires the publisher to complete to form an array. Choose NDJSON or an appropriate streaming protocol.
12. **Using NDJSON while sending a JSON array:** the server expects each line to be an independent JSON document. Both sides must agree on the format.
13. **Manually subscribing to the publisher before sending:** can consume the source twice or lose hot/one-shot data.
14. **Retrying a one-shot publisher:** retries may fail to replay the body and may repeat operations that already succeeded on the server.
15. **Not handling source errors:** a publisher emitting an error mid-request can truncate the body; do not turn that error into success.
16. **Not distinguishing request errors from response errors:** encode/write failures differ from HTTP 4xx/5xx and response decode failures.
17. **Setting Content-Length for an unknown-size stream:** the header can be wrong. Let the transport manage framing when length is unknown.
18. **Unnecessary collectList:** increases memory usage and delays encoding for large sources.
19. **Not handling cancellation:** timeouts or caller cancellation can stop body sending; sources with resources need cleanup.
20. **Not testing generic element types:** code may compile while codecs serialize into raw maps or the wrong structure. Test both request Content-Type and actual JSON.

## 20. Checklist Before Sending a Publisher

- Is the body source a value, `Mono<T>`, `Flux<T>`, or an adaptable producer?
- If it is a publisher, what is the exact element type?
- Do you need `Class<T>` or generic `ParameterizedTypeReference<T>`?
- Have you used `body()` instead of `bodyValue()` when the source is a Publisher?
- If the body is an already-available List, should it be sent via `bodyValue(list, typeRef)`?
- Does Content-Type match the body format?
- Does Accept accurately describe the desired response format?
- Does a JSON array or NDJSON fit the client/server contract?
- Is the publisher cold/replayable if retries are enabled?
- Have manual subscribe/block calls been avoided?
- Are timeouts, cancellation, and encode/write errors handled?
- Are response statuses checked and response bodies decoded to the right type?
- Are nested generic types tested if the endpoint uses generic DTOs?

## 21. Self-Check Questions

**1.** What does `body(Publisher<T>, Class<T>)` use Class to describe? The type of each element emitted by the publisher.

**2.** For `Flux<Person>`, what is the element type? `Person.class`.

**3.** For `Mono<List<Person>>`, what is the element type? `List<Person>`, so use `ParameterizedTypeReference<List<Person>>`.

**4.** Why is `ParameterizedTypeReference` needed? To preserve generic type arguments that Java type erasure cannot represent with a raw Class.

**5.** Does `bodyValue()` accept a Publisher? No; it throws `IllegalArgumentException` for Publishers/producers recognized by ReactiveAdapterRegistry.

**6.** What is the difference between type references in `body` and `bodyValue`? body describes the type of each publisher element; bodyValue describes the type of the concrete body value.

**7.** How is `Flux<Person>` + `application/json` encoded by default? The Jackson encoder collects into a List and serializes a JSON array.

**8.** Which media type should be used to send JSON records line by line? `application/x-ndjson`.

**9.** Do you need to call `subscribe()` on the body publisher? No. WebClient manages the subscription when the request executes.

**10.** Are retries always safe with body publishers? No. The source may be one-shot/hot and the request may have already been processed by the server before a connection error.

**11.** How do Content-Type and Accept differ? Content-Type describes the request body; Accept describes the response media type the client wants.

**12.** Is `bodyToFlux(Person.class)` a request-body sending API? No. It is an API for reading the response body as a Flux.

**Key takeaway:** `body(publisher, elementType)` sends a reactive source and declares **the type of each element**. Use `Class<T>` for concrete classes; use `ParameterizedTypeReference<T>` when elements have generic types. `bodyValue(value)` is for a concrete value and does not accept a Publisher. Choose the right Content-Type: JSON array for finite batches, NDJSON for record streams; let WebClient manage subscription, backpressure, cancellation, and response lifecycle handling.

**Official documentation:**
- [Spring Framework 6.2 — WebClient Request Body](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-webclient/client-body.html)
- [WebClient.RequestBodySpec Javadoc — body and bodyValue](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/reactive/function/client/WebClient.RequestBodySpec.html)
- [BodyInserters Javadoc — fromPublisher and fromValue](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/reactive/function/BodyInserters.html)
- [Spring Framework 6.2 — Reactive Core and Jackson Encoder](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html)
- [ParameterizedTypeReference Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/ParameterizedTypeReference.html)
- [Spring Framework 6.2 — WebClient Response Body](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-webclient/client-retrieve.html).