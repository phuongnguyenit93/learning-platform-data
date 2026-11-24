# WebClient: Reading JSON, Generic Types, Streaming Data, and Multipart

## 1. Goals and Mental Model

**WebClient** is the HTTP client in Spring WebFlux. It builds HTTP requests, sends and receives data through codecs, and returns **Mono<T>** (0–1 value) or **Flux<T>** (0–n values). WebClient works in both Spring MVC and WebFlux applications; calling WebClient does not automatically turn the entire application reactive.

This lesson focuses on the **body** of HTTP requests and responses:
- Reading JSON for a single object and a list of objects.
- Preserving generic type information, including nested structures like an API envelope containing a page.
- Reading continuous streams over NDJSON or Server-Sent Events (SSE).
- Sending multipart forms containing text fields, JSON, and files; when a server returns multipart, reading each part.
- Recognizing the boundary between streaming data, fully buffered data, and resource lifecycles.

Code snippets are based on **Java 17+, Spring Framework 6.x / Spring Boot 3.x, and Project Reactor**. HTTP paths starting with /api in this lesson are **illustrative API contracts**: they only actually work if the target system implements endpoints matching the described Content-Type and body structure.

### Choosing How to Read by Response Contract

| Response Content-Type and body shape | Goal | Common reading approach |
| --- | --- | --- |
| application/json, single object | Get DTO | retrieve().bodyToMono(User.class) |
| application/json, array | Get List<User> | bodyToMono(ParameterizedTypeReference<List<User>>) |
| application/json, generic wrapper object | Get ApiEnvelope<Page<User>> | bodyToMono(ParameterizedTypeReference<...>) |
| application/x-ndjson, one JSON per line | Receive multiple items over time | retrieve().bodyToFlux(User.class) |
| text/event-stream | Receive SSE and event metadata | bodyToFlux(ParameterizedTypeReference<ServerSentEvent<User>>) |
| multipart/form-data, **request** | Send text, JSON, and file | MultipartBodyBuilder + BodyInserters |
| multipart/mixed, **response** | Read name/headers/content of each part | Reader for MultiValueMap<String, Part> |

**Accept** expresses the response format the client wants; **Content-Type** describes the body format being sent. Do not confuse the two headers. WebClient selects codecs based on the **target Java type** and the **actual media type**.

## 2. Preparing Dependencies and WebClient

In a Spring Boot project with managed dependency versions, add the following starter to **pom.xml**:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
~~~

The starter provides WebClient, Reactor, and an appropriate default HTTP client; Spring Boot usually auto-configures Jackson codecs when Jackson is on the classpath. If not using Spring Boot, you must manage Spring WebFlux, Reactor, HTTP connector, and JSON codec dependencies yourself.

Create a client with a base address and an intentional decoding limit:

~~~java
WebClient client = WebClient.builder()
    .baseUrl("http://localhost:8080")
    .codecs(config -> config.defaultCodecs()
        .maxInMemorySize(2 * 1024 * 1024))
    .build();
~~~

**maxInMemorySize** is the buffer limit for certain decoding operations (such as buffering a large JSON value); it is not a cap on the total size of all uploaded files or an entire stream. Before raising this limit, identify why the response is being buffered in RAM.

WebClient is typically registered as a reusable bean:

~~~java
@Configuration
class HttpClientConfig {
    @Bean
    WebClient externalClient(WebClient.Builder builder) {
        return builder.baseUrl("https://api.example.org").build();
    }
}
~~~

The two imports in the bean example are **org.springframework.context.annotation.Bean** and **org.springframework.context.annotation.Configuration**. The example.org URL is illustrative and should be replaced for your real system. Never create a new client per record or per event.

## 3. Reading JSON: Single Object, HTTP Metadata, and Lists

Suppose the server exposes:

~~~http
GET /api/users/7
Accept: application/json

HTTP/1.1 200 OK
Content-Type: application/json

{"id":7,"name":"An"}
~~~

Java 17 DTO:

~~~java
public record User(long id, String name) {}
~~~

Reading JSON into a single object:

~~~java
Mono<User> user = client.get()
    .uri("/api/users/{id}", 7)
    .accept(MediaType.APPLICATION_JSON)
    .retrieve()
    .bodyToMono(User.class);
~~~

**bodyToMono(User.class)** decodes the body according to the DTO structure. **Mono<User>** does not hold a value immediately upon declaration; the HTTP request executes when subscribed to. For responses without a body, the Mono may complete empty; a JSON object and a JSON array cannot arbitrarily share the same target type.

If you need the status code and headers:

~~~java
Mono<ResponseEntity<User>> result = client.get()
    .uri("/api/users/{id}", 7)
    .retrieve()
    .toEntity(User.class);
~~~

Always read the status from **ResponseEntity**, rather than trying to add status as a field on User. For JSON fields named differently from Java fields, use Jackson configuration or **@JsonProperty** annotations as needed. If the response is dynamic JSON, you can decode into **JsonNode** to traverse without a fixed DTO, though DTOs should be preferred when the contract is clear.

### JSON Arrays and Two Ways to Represent Them

Example body:

~~~json
[
  {"id":7,"name":"An"},
  {"id":8,"name":"Bình"}
]
~~~

If you want a complete collection: use the generic type reference in section 4. If you want to process items potentially emitted by the decoder as reading progresses, you can use:

~~~java
Flux<User> userFlux = client.get()
    .uri("/api/users")
    .accept(MediaType.APPLICATION_JSON)
    .retrieve()
    .bodyToFlux(User.class);

Mono<List<User>> allUsers = userFlux.collectList();
~~~

**collectList()** gathers all elements before emitting the result and carries the corresponding memory cost. Having **bodyToFlux** emit a JSON array element-by-element does not by itself prove the server is streaming in real time: networking, JSON framing, and server response flushing all affect arrival timing.

## 4. Reading Generic JSON with Exact Types

In Java, **List.class** only preserves the raw type; it does not represent **List<User>**. Because of type erasure, doing the following easily results in elements decoded as Maps instead of User:

~~~java
// Wrong target type when wanting List<User>: User type information is lost.
Mono<List> raw = client.get()
    .uri("/api/users")
    .retrieve()
    .bodyToMono(List.class);
~~~

Preserve type information using **ParameterizedTypeReference<T>**:

~~~java
ParameterizedTypeReference<List<User>> listType =
    new ParameterizedTypeReference<List<User>>() {};

Mono<List<User>> users = client.get()
    .uri("/api/users")
    .accept(MediaType.APPLICATION_JSON)
    .retrieve()
    .bodyToMono(listType);
~~~

The anonymous subclass captures the generic type information so the Jackson codec knows each element must become a User. Writing **List<User>** on the left-hand side is not enough if the argument passed to bodyToMono is merely **List.class**.

### Nested Generics: API Envelopes and Data Pages

Suppose the API returns:

~~~json
{
  "status": "ok",
  "data": {
    "content": [
      {"id":7,"name":"An"},
      {"id":8,"name":"Bình"}
    ],
    "totalElements": 2
  }
}
~~~

Define the records:

~~~java
public record Page<T>(List<T> content, long totalElements) {}
public record ApiEnvelope<T>(String status, T data) {}
~~~

Decode the full structure:

~~~java
ParameterizedTypeReference<ApiEnvelope<Page<User>>> type =
    new ParameterizedTypeReference<ApiEnvelope<Page<User>>>() {};

Mono<ApiEnvelope<Page<User>>> page = client.get()
    .uri("/api/users/page")
    .retrieve()
    .bodyToMono(type);
~~~

The result of **data().content()** is **List<User>**, not a list of Maps. **ParameterizedTypeReference** also works with **bodyToFlux** if each stream item is itself a generic type (for example, **Event<User>**).

**Distinguish the two cases:** an HTTP response containing a JSON array should be read as List<User> or Flux<User>; a response containing a wrapper object **data.content** must be read with the matching envelope structure. **bodyToFlux(User.class)** does not automatically unwrap the envelope's data.content field.

## 5. Streaming Data: NDJSON and SSE

**Streaming** means processing events/items incrementally as they arrive rather than waiting for the whole response to finish. There are two common formats:

1. **NDJSON** (application/x-ndjson): each line contains an independent JSON value. A newline terminates each record.
2. **SSE** (text/event-stream): each event is framed by **data:** lines, optionally with **id:**, **event:**, and **retry:**. The two formats are not interchangeable.

### 5.1 Reading NDJSON

Illustrative body returned by a server with **Content-Type: application/x-ndjson**:

~~~text
{"id":7,"name":"An"}
{"id":8,"name":"Bình"}
{"id":9,"name":"Chi"}
~~~

Client:

~~~java
Flux<User> liveUsers = client.get()
    .uri("/api/users/live")
    .accept(MediaType.APPLICATION_NDJSON)
    .retrieve()
    .bodyToFlux(User.class);

Mono<Void> firstThree = liveUsers
    .take(3)
    .doOnNext(user -> System.out.println(user.name()))
    .then();
~~~

**take(3)** actively stops after three items and cancels the client-side subscription. This is useful for long-lived streams; if the source completes early, fewer than three items may be received. **then()** only signals completion or error without retaining the list. In this snippet no HTTP call runs until a subscriber subscribes or blocks at a non-reactive boundary.

To inspect records in a terminal once the server implements the endpoint:

~~~bash
curl -N -H "Accept: application/x-ndjson" http://localhost:8080/api/users/live
~~~

Depending on proxies/servers, having the right Content-Type alone is not enough for a real-time experience if the sending layer buffers data without flushing.

### 5.2 Reading SSE with JSON Payloads

Example raw response:

~~~text
id: 101
event: user
data: {"id":7,"name":"An"}

id: 102
event: user
data: {"id":8,"name":"Bình"}

~~~

Reading along with metadata:

~~~java
ParameterizedTypeReference<ServerSentEvent<User>> eventType =
    new ParameterizedTypeReference<ServerSentEvent<User>>() {};

Flux<ServerSentEvent<User>> events = client.get()
    .uri("/api/users/events")
    .accept(MediaType.TEXT_EVENT_STREAM)
    .retrieve()
    .bodyToFlux(eventType);

Flux<User> payloads = events
    .filter(event -> event.data() != null)
    .map(ServerSentEvent::data);
~~~

If you do not need id/event/retry, the application can decode each DTO directly when codecs and SSE payloads match; use **ServerSentEvent<User>** to preserve protocol metadata. Never force an SSE stream into **Mono<List<User>>** if the connection is designed not to terminate.

Direct verification:

~~~bash
curl -N -H "Accept: text/event-stream" http://localhost:8080/api/users/events
~~~

### 5.3 Stream Lifecycle, Backpressure, and Errors

- A **Flux** is a pipeline description; subscription triggers network I/O. In reactive controllers, **return Flux/Mono** for the framework to manage, avoiding arbitrary **subscribe()** calls that lose error management and stream cancellation.
- **Backpressure** regulates element demand in Reactive Streams, though not every API, proxy, or HTTP peer enforces the same emission rate. Avoid unboundedly slow downstreams and unbounded buffering operators.
- **timeout(Duration.ofSeconds(30))** can be used when data truly must appear within that window, but for streams with idle pauses, a timeout can treat a valid pause as an error. Distinguish connection timeout, response timeout, and inter-item timeout.
- **take(n)**, subscription cancellation, and retry policies can disconnect or reconnect streams; define how to avoid duplicate event processing on reconnect, such as using SSE event IDs.
- Do not call **collectList()** on an infinite stream. Do not assume an **application/json** response containing a huge array will naturally flush item by item.

## 6. Multipart Requests: Sending Text + JSON + File

Multipart is not a large JSON object. A **multipart/form-data** body is split into **parts**, each with a name, its own headers (possibly filename/Content-Type), and corresponding data. Typical scenario: uploading a file alongside structured metadata.

Example contract:
- **POST /api/uploads**
- Part **description**: a string.
- Part **metadata**: JSON of **UploadMetadata**.
- Part **file**: binary file.
- Success response: **application/json**, e.g., **{"id":"f-123"}**.

Multipart sending code:

~~~java
public record UploadMetadata(String source, String category) {}
public record UploadReceipt(String id) {}

Path path = Path.of("./avatar.png");

MultipartBodyBuilder parts = new MultipartBodyBuilder();
parts.part("description", "Avatar image");
parts.part("metadata", new UploadMetadata("mobile", "avatar"),
           MediaType.APPLICATION_JSON);
parts.part("file", new FileSystemResource(path), MediaType.IMAGE_PNG);

Mono<UploadReceipt> uploaded = client.post()
    .uri("/api/uploads")
    .contentType(MediaType.MULTIPART_FORM_DATA)
    .body(BodyInserters.fromMultipartData(parts.build()))
    .retrieve()
    .bodyToMono(UploadReceipt.class);
~~~

Explanation:
- **MultipartBodyBuilder** creates a **MultiValueMap<String, HttpEntity<?>>** holding part information and headers. Do not assemble boundaries or multipart strings by hand; the framework assigns the boundary and encodes the body.
- **FileSystemResource** lets the codec read the file and obtain its filename. Passing a **Path**/path string as plain text will only send text, not file bytes.
- Metadata has its own **Content-Type: application/json**; **Content-Type: multipart/form-data** is the header of the overall request.
- The server may return a **JSON response** for a multipart upload; in that case **bodyToMono(UploadReceipt.class)** is right. Do not confuse the request type with the response type.
- The file must exist and the client needs read permissions. If the server expects a different part name, Spring does not automatically rename parts to match.

Ultra-short form when sending only text and one Resource:

~~~java
Mono<String> answer = client.post()
    .uri("/api/uploads/simple")
    .body(BodyInserters.fromMultipartData("description", "Document")
        .with("file", new FileSystemResource(Path.of("./document.pdf"))))
    .retrieve()
    .bodyToMono(String.class);
~~~

For very large files or reactive-sourced parts, **MultipartBodyBuilder.asyncPart(...)** lets you pass a **Publisher** along with its element type into a part. When true sequential multipart streaming is required, Spring also supports **FormPartEvent** and **FilePartEvent**. Only use those advanced mechanisms when you understand **DataBuffer** allocation and release; do not convert an entire large file into a **byte[]** just for convenience.

### Server-Side View to Cross-Check the Contract

Example WebFlux controller receiving those exact parts:

~~~java
@PostMapping(path = "/api/uploads",
             consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public Mono<UploadReceipt> upload(
        @RequestPart("metadata") Mono<UploadMetadata> metadata,
        @RequestPart("file") FilePart file) {
    return metadata.flatMap(info ->
        file.transferTo(Path.of("./uploads", file.filename()))
            .thenReturn(new UploadReceipt("f-123")));
}
~~~

This is only an illustrative example of matching client–server APIs; a real application must **validate the filename and destination path**, create directories, handle duplicate file errors, and never use user-supplied names directly to build storage paths. The **description** field in the request can also be received on the server with **@RequestPart("description") String description** if needed.

## 7. When the *Response* Is Multipart: Reading Each Part

Unlike section 6, some APIs return **Content-Type: multipart/mixed** (or multipart/form-data) for a multi-part response. Reading the body as **List<User>** or **byte[]** will not expose part metadata and boundaries. One approach is decoding into **MultiValueMap<String, Part>** via **MultipartHttpMessageReader**. With WebClient, check whether client codecs already include this reader; you can register it explicitly as follows:

~~~java
WebClient multipartClient = client.mutate()
    .codecs(config -> config.customCodecs()
        .register(new MultipartHttpMessageReader(
            new DefaultPartHttpMessageReader())))
    .build();

ParameterizedTypeReference<MultiValueMap<String, Part>> multipartType =
    new ParameterizedTypeReference<MultiValueMap<String, Part>>() {};

Mono<MultiValueMap<String, Part>> response = multipartClient.get()
    .uri("/api/bundle")
    .accept(MediaType.MULTIPART_MIXED)
    .retrieve()
    .bodyToMono(multipartType);
~~~

Suppose the response contains a file part named **file**:

~~~java
Mono<Void> saved = response.flatMap(map -> {
    Part part = map.getFirst("file");
    if (part instanceof FilePart filePart) {
        return filePart.transferTo(Path.of("./downloaded.bin"));
    }
    return Mono.error(new IllegalStateException(
        "Response does not contain a file part named 'file'"));
});
~~~

**FormFieldPart** provides the text value of a form field; **FilePart** provides **filename()**, **headers()**, and **transferTo(Path)**. When one name has multiple parts, use **get(name)** to obtain the list rather than **getFirst(name)**. **FilePart** holds content with a resource lifecycle; you must read, forward, or write the file properly, never retaining a Part reference and abandoning the stream. Configuring the reader here makes the required codec explicit, because default client codecs can vary across versions/configurations.

For very large multipart responses that must be processed chunk-by-chunk as a stream, you can choose **PartEventHttpMessageReader** / **PartEvent** and handle **DataBuffer** instances carefully; reading all parts into a map is not a good default for all data volumes. Unlike **multipart/form-data**, **application/x-www-form-urlencoded** is simply key–value pairs, not file parts.

## 8. A Complete, Type-Consistent Client Class

The following code combines the main cases into one class. **ReadingWithWebClient.java** belongs to package **demo**. It **compiles with WebFlux dependencies configured as in section 2**; when calling the methods, the server-side HTTP system must implement the matching example endpoints. Because results depend on server data, there is no fixed stdout to assert beforehand.

~~~java
package demo;

import java.nio.file.Path;
import java.util.List;

import org.springframework.core.ParameterizedTypeReference;
import org.springframework.core.io.FileSystemResource;
import org.springframework.http.MediaType;
import org.springframework.http.client.MultipartBodyBuilder;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.http.codec.multipart.DefaultPartHttpMessageReader;
import org.springframework.http.codec.multipart.FilePart;
import org.springframework.http.codec.multipart.MultipartHttpMessageReader;
import org.springframework.http.codec.multipart.Part;
import org.springframework.util.MultiValueMap;
import org.springframework.web.reactive.function.BodyInserters;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public final class ReadingWithWebClient {
    public record User(long id, String name) {}
    public record Page<T>(List<T> content, long totalElements) {}
    public record ApiEnvelope<T>(String status, T data) {}
    public record UploadMetadata(String source, String category) {}
    public record UploadReceipt(String id) {}

    private final WebClient client;

    public ReadingWithWebClient(String baseUrl) {
        this.client = WebClient.builder()
            .baseUrl(baseUrl)
            .build();
    }

    public Mono<User> readUser(long id) {
        return client.get()
            .uri("/api/users/{id}", id)
            .accept(MediaType.APPLICATION_JSON)
            .retrieve()
            .bodyToMono(User.class);
    }

    public Mono<List<User>> readUserList() {
        ParameterizedTypeReference<List<User>> type =
            new ParameterizedTypeReference<List<User>>() {};
        return client.get()
            .uri("/api/users")
            .retrieve()
            .bodyToMono(type);
    }

    public Mono<ApiEnvelope<Page<User>>> readPage() {
        ParameterizedTypeReference<ApiEnvelope<Page<User>>> type =
            new ParameterizedTypeReference<ApiEnvelope<Page<User>>>() {};
        return client.get()
            .uri("/api/users/page")
            .retrieve()
            .bodyToMono(type);
    }

    public Flux<User> readNdjson() {
        return client.get()
            .uri("/api/users/live")
            .accept(MediaType.APPLICATION_NDJSON)
            .retrieve()
            .bodyToFlux(User.class);
    }

    public Flux<ServerSentEvent<User>> readSse() {
        ParameterizedTypeReference<ServerSentEvent<User>> type =
            new ParameterizedTypeReference<ServerSentEvent<User>>() {};
        return client.get()
            .uri("/api/users/events")
            .accept(MediaType.TEXT_EVENT_STREAM)
            .retrieve()
            .bodyToFlux(type);
    }

    public Mono<UploadReceipt> upload(Path sourceFile) {
        MultipartBodyBuilder parts = new MultipartBodyBuilder();
        parts.part("description", "Avatar image");
        parts.part("metadata",
            new UploadMetadata("mobile", "avatar"),
            MediaType.APPLICATION_JSON);
        parts.part("file", new FileSystemResource(sourceFile));

        return client.post()
            .uri("/api/uploads")
            .contentType(MediaType.MULTIPART_FORM_DATA)
            .body(BodyInserters.fromMultipartData(parts.build()))
            .retrieve()
            .bodyToMono(UploadReceipt.class);
    }

    public Mono<Void> downloadMultipartFile(Path destination) {
        WebClient readerClient = client.mutate()
            .codecs(config -> config.customCodecs()
                .register(new MultipartHttpMessageReader(
                    new DefaultPartHttpMessageReader())))
            .build();

        ParameterizedTypeReference<MultiValueMap<String, Part>> type =
            new ParameterizedTypeReference<MultiValueMap<String, Part>>() {};

        return readerClient.get()
            .uri("/api/bundle")
            .accept(MediaType.MULTIPART_MIXED)
            .retrieve()
            .bodyToMono(type)
            .flatMap(parts -> {
                Part part = parts.getFirst("file");
                if (part instanceof FilePart filePart) {
                    return filePart.transferTo(destination);
                }
                return Mono.error(new IllegalStateException(
                    "Missing file part in response"));
            });
    }
}
~~~

**Usage:** create **new ReadingWithWebClient("http://localhost:8080")**, then in a reactive component return **readUser(7)** or **readNdjson()** directly to the caller. In a command-line entrypoint or test not running on an event loop, you can use **readUser(7).block()**, but do not use **block()** inside a WebFlux handler or reactive pipeline. Never call **subscribe()** and immediately return HTTP 200 for an important upload: the caller would not know whether the upload succeeded or failed.

### Tracking HTTP Errors with Context

By default, **retrieve()** turns HTTP 4xx/5xx into **WebClientResponseException**; when business logic needs custom messages, you can place **onStatus** before bodyToMono:

~~~java
Mono<User> user = client.get()
    .uri("/api/users/{id}", 7)
    .retrieve()
    .onStatus(
        status -> status.value() == 404,
        response -> Mono.just(
            new IllegalArgumentException("User 7 not found")))
    .bodyToMono(User.class);
~~~

When using **exchangeToMono/Flux** to choose how to read based on status, process the response body immediately inside the appropriate callback; do not leave the body unread and try to decode it after the callback. Configure timeouts and retries according to business characteristics; retrying a POST upload without an idempotency key can create duplicate records.

## 9. Common Errors and How to Diagnose Them

| Symptom | Common cause | How to resolve |
| --- | --- | --- |
| Receiving LinkedHashMap instead of User in a list | Using List.class, losing generic type | Use ParameterizedTypeReference<List<User>> |
| Decoding reports mismatch or fails to extract fields | JSON root object/array differs from DTO | Inspect actual body and schema; DTO must match JSON |
| NDJSON data does not appear incrementally | Server/proxy does not flush or response is not NDJSON | Check Content-Type, framing, curl -N, and flush behavior |
| SSE fails to decode with standard JSON codec | Confusing text/event-stream with application/json | Use accept(TEXT_EVENT_STREAM) and ServerSentEvent<T> |
| Growing RAM on long-running streams | collectList/cache/unbounded buffering | Process each item, bound/cancel explicitly |
| Multipart only sends the file path | Passing String path instead of a file Resource | Use FileSystemResource or properly encoded file data |
| HTTP 415 / 400 on upload | Wrong Content-Type or part name differs from contract | Compare request headers, boundary, part names, per-part media type |
| Cannot decode multipart response | Client lacks an appropriate multipart reader | Register MultipartHttpMessageReader and inspect Part types |
| DataBufferLimitException | Decoder must buffer a value exceeding the limit | Inspect payload, streaming strategy, and codec limits |
| RuntimeException after block() | 4xx/5xx, timeout, or decoding error | Catch the right error type; read status + body safely if needed |
| Leaked resources/connections when handling parts | Skipping part content or wrong lifecycle cancellation | Consume/transfer/release parts and DataBuffers via proper APIs |

Do not log entire JSON payloads containing personal data or multipart binaries indiscriminately. For downloaded files, use controlled paths and validate size, format, and filename per application requirements.

## 10. Scenario-Based Knowledge Check

1. **GET /users** returns **application/json** with an array of 100 users: want a full List<User> → **bodyToMono(ParameterizedTypeReference<List<User>>)**; if processing item-by-item, consider **bodyToFlux(User.class)**.
2. **GET /users/page** returns object **{"data":{"content":[...]}}**: must have envelope/page DTOs matching the schema; **bodyToFlux(User.class)** does not automatically descend into the content field.
3. **GET /users/live** sends one JSON object per line: use **application/x-ndjson + bodyToFlux(User.class)**, check server flushing, and avoid unbounded collectList.
4. **GET /events** returns **text/event-stream** with event IDs and JSON data: use **ServerSentEvent<User>** to keep metadata.
5. **POST /uploads** requires a **file** part and a JSON **metadata** part: use MultipartBodyBuilder; if the success response is JSON, read **UploadReceipt**, not multipart just because the request was multipart.
6. **GET /bundle** returns **multipart/mixed** with text and file: the client needs a suitable multipart reader; read **Part**, and transfer file content using FilePart APIs or corresponding reactive data streams.

### Self-Implementation Checklist

- Verify the status, Content-Type, and body schema of the **actual response** before picking Java types.
- For generics, pass **ParameterizedTypeReference** all the way into the bodyToMono/bodyToFlux call.
- For streaming, verify NDJSON/SSE format, record boundaries, flushing, cancellation, timeouts, and backpressure.
- For multipart, distinguish **sending a request** from **reading a response**; check part names, filenames, headers, and file/DataBuffer lifecycle.
- Wire Mono/Flux into the final processing chain and manage errors; only block at controlled synchronous boundaries.

## References

- [Spring Framework – WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html)
- [Spring Framework – WebClient retrieve() and response decoding](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html)
- [Spring Framework – WebClient request body and multipart](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-body.html)
- [Spring Framework – Reactive Core, codecs, and multipart](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html)
- [Spring Framework – WebClient exchangeToMono/Flux](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-exchange.html)
