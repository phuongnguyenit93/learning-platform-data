# Reading Multipart Data with @RequestPart, Part, and FilePart in Spring WebFlux

## 1. What is Multipart?

HTTP multipart allows a single request body to contain multiple parts. Each part has its own headers and content. Browsers typically use `multipart/form-data` when a form includes a file upload; APIs can also use `multipart/mixed` or `multipart/related` when a request contains JSON, images, documents, or data of different media types.

Example of a document upload request with JSON metadata and a file:

~~~http
POST /api/uploads HTTP/1.1
Content-Type: multipart/form-data; boundary=----upload-boundary

------upload-boundary
Content-Disposition: form-data; name="metadata"
Content-Type: application/json

{"title":"WebFlux guide","category":"manual"}
------upload-boundary
Content-Disposition: form-data; name="file"; filename="guide.pdf"
Content-Type: application/pdf

<binary file content>
------upload-boundary--
~~~

Key concepts:

- **Boundary**: a string that separates parts. The client generates the boundary and includes it in the overall request's Content-Type.
- **Part name**: the name of the field, such as `metadata` or `file`.
- **Content-Disposition**: describes which field the part represents and whether it has a filename.
- **Part Content-Type**: the data type of that specific part, such as `application/json` or `application/pdf`.
- **Part body**: text data, JSON, or file bytes.

Do not manually set the `Content-Type: multipart/form-data` header when sending from a browser with FormData, because the browser needs to append the boundary to the header itself. If set manually without a boundary, the server cannot parse the request properly.

## 2. How Does WebFlux Parse Multipart?

Spring WebFlux uses the HTTP message reader/codec system to read multipart data. High-level flow:

~~~text
HTTP request body
  Content-Type: multipart/form-data; boundary=...
              |
              v
      MultipartHttpMessageReader
              |
              v
       PartHttpMessageReader
              |
              v
       Part / FilePart objects
              |
       +------+-------------------+
       |                          |
       v                          v
  @RequestPart                MultiValueMap
  by part name                all parts
       |
       v
  HttpMessageReader
  decodes part if target
  is a specific DTO
~~~

In the default configuration, `DefaultPartHttpMessageReader` reads parts as `Part`. `MultipartHttpMessageReader` collects the parts into a `MultiValueMap<String, Part>` so they can be accessed by name.

This explains why there are two approaches:

1. **Access by part name** using `@RequestPart` or `ServerWebExchange.getMultipartData()`. This is convenient when the endpoint expects a well-structured set of parts.
2. **Sequential streaming** using `Flux<PartEvent>`. This is suitable for large files or proxies that need to relay data without collecting all parts into a map.

`@RequestPart` generally requires map-like multipart processing, meaning the parser must parse the multipart body and provide parts by name. If you need to stream each event as soon as it arrives, consider `PartEvent`.

## 3. What is @RequestPart Used For?

`@RequestPart` binds a named part in a multipart request to a controller method parameter.

Example:

~~~java
@PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
Mono<String> upload(
        @RequestPart("metadata") UploadMetadata metadata,
        @RequestPart("file") FilePart file) {
    // ...
}
~~~

Spring locates the parts named `metadata` and `file`, then resolves the corresponding parameters.

`@RequestPart` is similar to `@RequestBody` in that it can use an HTTP message reader to decode the part content into a specific Java type. The difference is that `@RequestBody` reads the entire request body, whereas `@RequestPart` reads a single part within a multipart body.

### 3.1. Decoding a JSON Part into a DTO

If the `metadata` part has Content-Type `application/json`, you can declare a DTO type:

~~~java
public record UploadMetadata(
        String title,
        String category) {
}

@PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
Mono<String> upload(
        @RequestPart("metadata") UploadMetadata metadata) {
    return Mono.just(metadata.title());
}
~~~

Spring uses a JSON codec (typically Jackson when the corresponding dependency is present) to decode the part content into `UploadMetadata`.

Important requirement: **the part's Content-Type must match the target type**. If the client sends JSON but marks the part as `text/plain` or omits an appropriate media type, the codec may not find a matching reader.

With browser FormData, append metadata as a Blob with JSON Content-Type:

~~~javascript
const form = new FormData();

form.append(
  "metadata",
  new Blob(
    [JSON.stringify({
      title: "WebFlux guide",
      category: "manual"
    })],
    { type: "application/json" }
  )
);

form.append("file", fileInput.files[0]);

await fetch("/api/uploads", {
  method: "POST",
  body: form
});
~~~

Do not manually add the `Content-Type` header to fetch in this example. The browser generates the multipart boundary and attaches it to the header automatically.

### 3.2. Validation for a JSON Part

You can combine `@Valid` or `@Validated` with `@RequestPart`:

~~~java
public record UploadMetadata(
        @NotBlank
        @Size(max = 100)
        String title,

        @NotBlank
        @Size(max = 40)
        String category) {
}

@PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
Mono<String> upload(
        @Valid @RequestPart("metadata") UploadMetadata metadata) {
    return Mono.just("accepted: " + metadata.title());
}
~~~

When validation fails, WebFlux throws `WebExchangeBindException` and by default maps it to HTTP 400. If method validation applies because other parameters carry constraint annotations, the error may be `HandlerMethodValidationException`.

For reactive processing, you can declare the argument as `Mono<UploadMetadata>`:

~~~java
@PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
Mono<String> upload(
        @Valid @RequestPart("metadata") Mono<UploadMetadata> metadata) {

    return metadata.map(value -> "accepted: " + value.title());
}
~~~

This approach lets you handle decoding/validation errors in the pipeline with `onErrorMap`, `onErrorResume`, or a global error handler. Do not call `block()` to retrieve metadata.

### 3.3. When to Use @RequestPart with the Part Type?

When you do not want Spring to decode the part into a DTO and instead need to work directly with headers and raw content, declare `Part`:

~~~java
@PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
Mono<String> inspect(
        @RequestPart("metadata") Part metadata) {

    String contentType =
            String.valueOf(metadata.headers().getContentType());

    return Mono.just(
            metadata.name() + ":" + contentType);
}
~~~

`Part` allows you to:

- Get the part name via `name()`.
- Read headers via `headers()`.
- Read the body via `content()` as a `Flux<DataBuffer>`.
- Delete the underlying storage of the part via `delete()`.

`Part` does not assume the part is a file. It can be a text field, JSON, PDF, or other data.

## 4. How Do Part, FormFieldPart, and FilePart Differ?

`Part` is the common interface. Two common specializations:

- `FormFieldPart`: a text field part; provides a `value()` method to get the text value.
- `FilePart`: a part representing an uploaded file; provides `filename()` and `transferTo(Path)`.

| Type | Data | Commonly used API |
| --- | --- | --- |
| `Part` | Any part | `name()`, `headers()`, `content()`, `delete()` |
| `FormFieldPart` | Text field | `value()` |
| `FilePart` | File upload | `filename()`, `transferTo(Path)`, `content()` |

### 4.1. Part

A `Part` provides:

~~~java
String name();
HttpHeaders headers();
Flux<DataBuffer> content();
Mono<Void> delete();
~~~

`content()` returns a stream of DataBuffer. Part content is not always a small byte array on the heap. It can be a stream or data temporarily stored on disk depending on the reader and configuration.

If you consume `content()` directly at the DataBuffer level, you must follow DataBuffer ownership and release rules. If you only need to move the file to a destination, prefer `FilePart.transferTo` instead of writing your own byte read/write loop.

### 4.2. FormFieldPart

`FormFieldPart` extends `Part` for text fields:

~~~java
@PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
Mono<String> submit(
        @RequestPart("comment") FormFieldPart comment) {

    return Mono.just(comment.value());
}
~~~

`value()` is more convenient than reading `content()` and converting bytes into a String manually.

Do not use `FormFieldPart` for file uploads. If the client sends a part with a filename, Spring typically represents it as `FilePart`.

### 4.3. FilePart

`FilePart` is a specialization of `Part`:

~~~java
String filename();
Mono<Void> transferTo(Path destination);
~~~

`filename()` returns the original filename provided by the client. This value is **untrusted**: it may contain paths, `..`, separators, or dangerous characters. Never use filename directly as a storage path.

`transferTo(Path)` writes the file content to the destination and returns `Mono<Void>` upon completion. If the destination file already exists, its content is truncated before writing. Therefore, generate a unique server-side destination name, such as a UUID, rather than using the client-supplied name.

Example:

~~~java
String id = UUID.randomUUID().toString();
Path destination = uploadDirectory.resolve(id + ".bin");

return filePart.transferTo(destination);
~~~

`FilePart` does not have a `size()` API like some Servlet multipart abstractions. If you need size limits, configure the multipart reader/server and consider streaming/counting bytes per the contract; do not infer size from filename or the entire request's Content-Length.

## 5. Reading Individual Parts with @RequestPart

An endpoint can accept multiple parts with different data types:

~~~java
@PostMapping(
        path = "/documents",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
Mono<ResponseEntity<String>> upload(
        @Valid @RequestPart("metadata") Mono<DocumentMetadata> metadata,
        @RequestPart("document") FilePart document,
        @RequestPart("attachment") Part attachment) {

    return metadata.map(value ->
            ResponseEntity.accepted().body(
                    "received " + value.title()
                            + ", file=" + document.filename()
                            + ", attachment=" + attachment.name()));
}
~~~

This is an example of parameter shapes, not a complete file-saving controller. Each name in the annotation must match the exact `name` of the part sent by the client.

You can use `@RequestPart(required = false)` for optional parts when the contract allows it. If a part is required but the client omits it, argument resolution fails before the handler runs normally. Clearly define which parts are required and which are optional.

### 5.1. Part Names with Hyphens

The part name does not have to match the Java variable name:

~~~java
@PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
Mono<String> upload(
        @RequestPart("meta-data") DocumentMetadata metadata,
        @RequestPart("file-data") FilePart file) {
    return Mono.just(metadata.title());
}
~~~

The client must send the exact `meta-data` and `file-data` names. Part names are part of the API contract; renaming them must be treated as a breaking contract change with clients.

### 5.2. A Part Name Can Appear Multiple Times

Multipart requests can contain multiple parts with the same name, such as multiple files under a `files` field. When you need access to the full list or all parts, use `MultiValueMap<String, Part>` via `ServerWebExchange.getMultipartData()` or `@RequestBody Mono<MultiValueMap<String, Part>>`.

Do not assume each key has only one value. If the API only accepts one file, check the corresponding part count and reject extra data according to the contract.

## 6. Accessing All Parts with MultiValueMap

If the controller needs to iterate through parts by name instead of declaring individual parameters, it can accept:

~~~java
@PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
Mono<String> upload(
        @RequestBody Mono<MultiValueMap<String, Part>> partsMono) {

    return partsMono.map(parts -> {
        Part metadata = parts.getFirst("metadata");
        List<Part> files = parts.get("files");
        return "metadata=" + metadata.name()
                + ", files=" + (files == null ? 0 : files.size());
    });
}
~~~

Or use `ServerWebExchange`:

~~~java
@PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
Mono<String> inspect(ServerWebExchange exchange) {
    return exchange.getMultipartData()
            .map(parts -> "part names=" + parts.keySet());
}
~~~

`getMultipartData()` returns `Mono<MultiValueMap<String, Part>>`. When called, Spring parses the multipart request and caches the map so the map can be accessed multiple times. However, **the content of each individual part is not cached and can only be read once**.

Once `getMultipartData()` has been used, you cannot go back and read the raw request body as if it had not been consumed. Be consistent: use multipart map access for reads by name, or use the streaming reader if sequential reading is required.

### 6.1. Cleanup When Accessing Part Directly

`Part.delete()` returns `Mono<Void>` to delete the underlying storage of the part. `ServerWebExchange.cleanupMultipart()` also provides storage cleanup for multipart handling.

When using lower-level APIs like `BodyExtractors.toMultipartData()` or `BodyExtractors.toParts()`, resources used by parts (such as temporary files) are not automatically deleted just because you received the Part objects; you need to compose cleanup using `Part.delete()` or the corresponding cleanup mechanism.

Conceptual example:

~~~java
Mono<Void> cleanup = part.delete();
~~~

The cleanup Publisher must be wired into the pipeline so that it gets subscribed to. Do not call `part.delete()` and ignore the returned Mono. With multiple parts, clean up each part using `concatMap(Part::delete)` or `flatMap` per your policy; ensure cleanup also runs when the pipeline errors or is canceled.

## 7. FilePart.transferTo: The Common File Upload Approach

For a typical file upload, `FilePart.transferTo(Path)` is a convenient API:

~~~java
@PostMapping(
        path = "/upload",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
Mono<ResponseEntity<String>> upload(
        @RequestPart("file") FilePart file) {

    Path destination = uploadDirectory.resolve(
            UUID.randomUUID() + ".bin");

    return file.transferTo(destination)
            .thenReturn(ResponseEntity.created(
                    URI.create("/files/" + destination.getFileName()))
                    .body("uploaded"));
}
~~~

Key points:

- Do not use the client-supplied filename to build the destination path.
- Do not call `block()` on `transferTo`.
- Only return a success response after the transfer Mono completes.
- Use a server-generated filename to prevent overwriting other files or path traversal.
- Place the upload directory outside the web root; uploaded files must not automatically become executable content.
- If the transfer fails, handle any partial destination file according to your application's storage policy.

`transferTo` returns a Mono representing the write operation. Compose it with steps to save metadata, scan the file, or update the database in the proper order. If a file must be scanned before publication, do not mark the resource as ready as soon as the request arrives.

## 8. Multipart Parser, Memory, and Temporary Files

WebFlux uses `DefaultPartHttpMessageReader` by default to read parts. In non-streaming mode:

- Part content smaller than the `maxInMemorySize` threshold is kept in memory.
- File parts larger than the threshold are written to temporary files.
- Non-file parts exceeding the threshold are rejected with `DataBufferLimitException`.
- The temporary storage directory can be configured.
- The number of parts and disk usage per file part can be limited.

According to Spring Framework 7.0.8 JavaDoc:

| Property | Default value | Meaning |
| --- | --- | --- |
| `maxInMemorySize` | 256 KiB | Memory threshold per part; larger files are written to temp storage, non-file parts exceeding the threshold are rejected |
| `maxDiskUsagePerPart` | -1 | Unlimited disk space per file part |
| `maxParts` | -1 | Unlimited number of parts |
| `fileStorageDirectory` | Directory `spring-webflux-multipart` under the system temp directory | Where parts exceeding the memory threshold are stored |
| `maxHeadersSize` | Per reader configuration | Memory limit for each part's headers |

Do not leave disk usage and part count unlimited on public endpoints. A single request could contain many parts, huge files, or overly long metadata. Limits must fit business requirements as well as the reverse proxy/gateway layer.

### 8.1. Configuring Multipart Limits

You can provide a custom-configured `MultipartHttpMessageReader` via `ServerCodecConfigurer`:

~~~java
@Configuration
class MultipartLimitsConfiguration implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {

        DefaultPartHttpMessageReader partReader =
                new DefaultPartHttpMessageReader();

        partReader.setMaxInMemorySize(256 * 1024);
        partReader.setMaxDiskUsagePerPart(25L * 1024 * 1024);
        partReader.setMaxParts(5);
        partReader.setMaxHeadersSize(10 * 1024);

        MultipartHttpMessageReader multipartReader =
                new MultipartHttpMessageReader(partReader);

        configurer.customCodecs().reader(multipartReader);
    }
}
~~~

Meaning of the illustrative configuration:

- Each non-file part can retain at most 256 KiB in memory.
- File parts exceeding the memory threshold are written to temp storage.
- Each file part cannot exceed 25 MiB on disk.
- A request cannot have more than 5 parts.
- Headers of each part are limited to 10 KiB.

This is a reader configuration and does not replace total request body limits at the gateway, load balancer, or server. If the API needs a total maximum size of 50 MiB, ensure that total limit is enforced at the appropriate layer; `maxDiskUsagePerPart` only limits each individual file part, not the sum of all files in the request.

If you replace the default reader, integration test `@RequestPart`, `getMultipartData()`, and streaming endpoints to ensure the reader is registered in the right order and scope.

## 9. Streaming Multipart with Flux<PartEvent>

For large files, parsing multipart into `MultiValueMap<String, Part>` may not be optimal. Spring WebFlux provides `PartEventHttpMessageReader` to read parts sequentially:

~~~java
@PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
Mono<Void> uploadStream(@RequestBody Flux<PartEvent> allPartEvents) {
    // process each part event in received order
}
~~~

Each part produces at least one `PartEvent`:

- A form field produces a `FormPartEvent` containing the field value.
- A file upload produces one or more `FilePartEvent` instances.
- If the file is large enough to span multiple buffers, the first event may be followed by subsequent events.
- The last event of a part has `isLast()` equal to true.

You can use `windowUntil(PartEvent::isLast)` to split the stream into groups of events belonging to a single part:

~~~java
allPartEvents
        .windowUntil(PartEvent::isLast)
        .concatMap(partEvents ->
                partEvents.switchOnFirst((signal, events) -> {
                    if (!signal.hasValue()) {
                        return events.then();
                    }

                    PartEvent first = signal.get();

                    if (first instanceof FormPartEvent form) {
                        String value = form.value();
                        // Process text field.
                        return events.then();
                    }

                    if (first instanceof FilePartEvent file) {
                        String filename = file.filename();

                        Flux<DataBuffer> content =
                                events.map(PartEvent::content);

                        // Forward content to storage or target service.
                        // The storage consumer must consume or release all buffers.
                        return fileStorageService.store(
                                filename, content);
                    }

                    return Mono.error(
                            new IllegalArgumentException(
                                    "Unsupported multipart event"));
                }));
~~~

This is an **illustrative streaming structure snippet**, assuming `fileStorageService.store(...)` returns `Mono<Void>` and actually consumes/relays every DataBuffer. It is not a standalone controller to copy verbatim.

Ownership notes:

- Each `PartEvent` contains a `DataBuffer`.
- File content may span multiple events.
- Body buffers must be fully consumed, forwarded to another service, or released; ignoring buffers can cause memory leaks.
- Do not collect all events into a List just to process them sequentially.
- Use `concatMap` when parts need to be processed in order; only increase concurrency when storage and the contract allow it.

`PartEvent` is well-suited for large files, streaming proxies, or pipelines needing backpressure control. `@RequestPart` is better suited when you need to access a few named parts with moderate-sized data.

## 10. Runnable Java 17+ Spring Boot WebFlux Program

This example creates an endpoint:

~~~text
POST /api/uploads
Content-Type: multipart/form-data
~~~

The endpoint accepts:

- `metadata`: a JSON part decoded into a record and validated.
- `file`: a FilePart transferred into an upload directory under a server-generated filename.

### 10.1. Project Structure

~~~text
webflux-multipart-demo/
  pom.xml
  src/main/java/example/upload/MultipartDemoApplication.java
  src/main/java/example/upload/UploadController.java
  src/test/java/example/upload/UploadControllerTest.java
~~~

Requirements: **JDK 17+**, **Maven 3.6.3+**, **Spring Boot 4.1.2**. In a real project, pick a patch release supported by your organization and let the Boot BOM manage Spring Framework, Reactor, and compatible dependencies.

### 10.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>webflux-multipart-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
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

### 10.3. Startup Class

**src/main/java/example/upload/MultipartDemoApplication.java**

~~~java
package example.upload;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MultipartDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                MultipartDemoApplication.class, args);
    }
}
~~~

### 10.4. Controller Receiving JSON and File

**src/main/java/example/upload/UploadController.java**

~~~java
package example.upload;

import java.io.IOException;
import java.net.URI;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.UUID;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.multipart.FilePart;
import org.springframework.http.codec.multipart.Part;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/uploads")
public class UploadController {

    private final Path uploadDirectory;

    public UploadController() throws IOException {
        this.uploadDirectory = Path.of(
                System.getProperty("java.io.tmpdir"),
                "webflux-multipart-demo");

        Files.createDirectories(uploadDirectory);
    }

    public record UploadMetadata(
            @NotBlank
            @Size(max = 100)
            String title,

            @NotBlank
            @Size(max = 40)
            String category) {
    }

    public record UploadReceipt(
            String id,
            String title,
            String storedAs) {
    }

    @PostMapping(
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public Mono<ResponseEntity<UploadReceipt>> upload(
            @Valid
            @RequestPart("metadata")
            Mono<UploadMetadata> metadata,

            @RequestPart("file")
            FilePart file) {

        return metadata.flatMap(value -> {
            String id = UUID.randomUUID().toString();
            String storedName = id + ".bin";
            Path destination = uploadDirectory.resolve(storedName);

            UploadReceipt receipt = new UploadReceipt(
                    id, value.title(), storedName);

            Mono<UploadReceipt> saveAndCleanup = Mono.usingWhen(
                    Mono.just(file),
                    part -> part.transferTo(destination)
                            .thenReturn(receipt),
                    Part::delete,
                    (part, error) -> part.delete(),
                    Part::delete);

            return saveAndCleanup.map(saved ->
                    ResponseEntity
                            .created(URI.create("/api/uploads/" + id))
                            .body(saved));
        });
    }
}
~~~

Explanation:

- `@RequestPart("metadata") Mono<UploadMetadata>` requests the JSON part named `metadata`. Spring decodes it into a record.
- `@Valid` triggers validation on the metadata fields.
- `@RequestPart("file") FilePart` retrieves the file part named `file`.
- The destination name is generated from a UUID, not taken from `file.filename()`.
- `transferTo(destination)` returns a Mono, so the entire save operation remains inside the reactive pipeline.
- `Mono.usingWhen` calls `Part.delete()` on success, error, or cancellation to clean up the part's underlying storage once the content has been processed.

This is a simple file-saving example. Production applications also need user authentication, size limits, actual file-type verification, malware scanning if appropriate, quota management, and storing metadata in a database.

### 10.5. Running the Application and Sending a File with curl

In the directory containing `pom.xml`:

~~~bash
mvn clean test
mvn spring-boot:run
~~~

Send a request:

~~~bash
curl -i -X POST http://localhost:8080/api/uploads \
  -F 'metadata={"title":"WebFlux guide","category":"manual"};type=application/json' \
  -F 'file=@./guide.pdf;type=application/pdf'
~~~

Curl generates the boundary and multipart Content-Type automatically.

The response looks like:

~~~http
HTTP/1.1 201 Created
Location: /api/uploads/<generated-id>
Content-Type: application/json
~~~

The body looks like:

~~~json
{
  "id": "<generated-id>",
  "title": "WebFlux guide",
  "storedAs": "<generated-id>.bin"
}
~~~

The actual ID is generated randomly. The server stores the file in `java.io.tmpdir/webflux-multipart-demo`; the client's original filename is not used as a path.

### 10.6. Testing with WebTestClient

**src/test/java/example/upload/UploadControllerTest.java**

~~~java
package example.upload;

import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.MediaType;
import org.springframework.http.client.MultipartBodyBuilder;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.BodyInserters;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class UploadControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void acceptsJsonMetadataAndFile() {
        MultipartBodyBuilder multipart =
                new MultipartBodyBuilder();

        multipart.part(
                "metadata",
                new UploadController.UploadMetadata(
                        "Guide", "manual"))
                .contentType(MediaType.APPLICATION_JSON);

        multipart.part(
                "file",
                new ByteArrayResource(
                        "hello".getBytes(StandardCharsets.UTF_8)) {
                    @Override
                    public String getFilename() {
                        return "guide.txt";
                    }
                })
                .contentType(MediaType.TEXT_PLAIN);

        client.post()
                .uri("/api/uploads")
                .contentType(MediaType.MULTIPART_FORM_DATA)
                .body(BodyInserters.fromMultipartData(
                        multipart.build()))
                .exchange()
                .expectStatus().isCreated()
                .expectHeader().exists("Location")
                .expectBody()
                .jsonPath("$.title").isEqualTo("Guide")
                .jsonPath("$.storedAs").exists();
    }
}
~~~

This test exercises the actual HTTP path: the multipart writer builds the parts, the JSON part is decoded, the FilePart is transferred to storage, and the response returns HTTP 201.

## 11. Sending Multipart with WebClient

`WebClient` can send multipart requests using `MultipartBodyBuilder`:

~~~java
MultipartBodyBuilder builder = new MultipartBodyBuilder();

builder.part("metadata", metadata)
        .contentType(MediaType.APPLICATION_JSON);

builder.part("file", resource)
        .filename("guide.pdf")
        .contentType(MediaType.APPLICATION_PDF);

Mono<UploadReceipt> result = webClient.post()
        .uri("/api/uploads")
        .contentType(MediaType.MULTIPART_FORM_DATA)
        .body(BodyInserters.fromMultipartData(builder.build()))
        .retrieve()
        .bodyToMono(UploadReceipt.class);
~~~

In the example:

- `metadata` is serialized via the JSON codec because the part has JSON Content-Type.
- `file` is sent as a Resource.
- `MultipartBodyBuilder` constructs the multipart parts and the writer generates the boundary.
- `retrieve().bodyToMono(...)` decodes the response.

This is a client-side illustrative snippet; `webClient`, `metadata`, `resource`, and `UploadReceipt` must be declared. For large files, choose an appropriate Resource/Publisher and test streaming rather than reading the entire file into `byte[]` before sending.

## 12. Distinguishing @RequestPart, @RequestBody, @RequestParam, and PartEvent

| API | When to use | Data shape |
| --- | --- | --- |
| `@RequestPart("metadata") DTO` | Need to decode a part into an object | A single part with matching Content-Type |
| `@RequestPart("file") FilePart` | Need to save or forward an uploaded file | FilePart |
| `@RequestPart("part") Part` | Need raw headers/content of a part | Part |
| `@RequestBody Mono<MultiValueMap<String, Part>>` | Need all parts by name in one map | MultiValueMap |
| `ServerWebExchange.getMultipartData()` | Need multipart map access at the exchange level | Mono<MultiValueMap> |
| `@RequestBody Flux<PartEvent>` | Need to read multipart sequentially, streaming | Flux<PartEvent> |
| `@ModelAttribute` | Form upload mapped to a command object | DTO with text fields and FilePart |

Choose the API based on usage:

- Small form with metadata and one file: `@RequestPart` is a clear choice.
- Need to iterate over multiple files or multiple parts with the same name: map access can be convenient.
- Large files or relaying multipart to another service: `PartEvent` preserves streaming and backpressure.
- Only need a simple text field: `FormFieldPart.value()` or an appropriate DTO.

## 13. Security When Receiving File Uploads

Multipart upload is an untrusted data ingestion boundary. Values such as filename, Content-Type, metadata, and bytes are all controlled by the client.

### 13.1. Do Not Trust filename

`FilePart.filename()` is the name sent by the client. Do not use it directly in:

~~~java
Path destination = uploadDirectory.resolve(file.filename());
~~~

Doing so can open the door to path traversal, file overwriting, or unpredictable filenames. Generate a random name on the server:

~~~java
Path destination = uploadDirectory.resolve(
        UUID.randomUUID() + ".bin");
~~~

If you need to keep the original name for display, store it as sanitized metadata; do not use it as a path.

### 13.2. Do Not Trust Content-Type

Clients can send `Content-Type: image/png` for content that is not PNG. Checking the MIME header is only the first step.

For critical file types:

- Inspect actual magic bytes or file signatures.
- Validate the file structure with an appropriate parser.
- Restrict file types using an allowlist.
- Do not rely solely on the extension.
- Do not serve uploaded files under the same origin as application content unless necessary.
- Scan for malware or inspect content per business requirements.

### 13.3. Size and Count Limits

Set limits for:

- Total request body at the gateway/server.
- Number of parts.
- Non-file part size in memory.
- File part size on disk.
- Number of files per user or per request.
- Upload duration and minimum rate if the system needs slow-upload protection.
- Storage quota per user/tenant.

`maxInMemorySize` is not the total request size. `maxDiskUsagePerPart` is not the total size of all file parts. Combine multiple layers of limits.

### 13.4. Preventing Path Traversal and Overwrites

- Use server-generated names.
- Store files outside the web root directory.
- Never concatenate client input directly into paths.
- If the client name must be used as metadata, normalize and sanitize it before display.
- Check access permissions per user/tenant.
- Use safe file creation operations to avoid overwrites.
- Clean up partial files if the upload fails or is canceled.

### 13.5. Temporary Storage and Cleanup

The reader may write large file parts to a temporary directory. You must:

- Choose a temp directory with appropriate access permissions.
- Monitor disk usage.
- Configure maxDiskUsagePerPart.
- Clean up part storage after processing if your code manages Part directly.
- Handle error/cancel signals so temp files are not kept indefinitely.
- Never treat the temp directory as long-term storage.

### 13.6. Do Not Block the Event Loop

Do not use `Files.copy`, `InputStream.read`, or `block()` directly on the event loop in a reactive controller. Use `FilePart.transferTo` or reactive streaming APIs. If a blocking library is unavoidable, offload that work to an appropriate scheduler and bound concurrency.

## 14. Common Errors and How to Fix Them

| Error | Cause | How to fix |
| --- | --- | --- |
| HTTP 415 Unsupported Media Type | Request or part has an incompatible Content-Type | Verify Content-Type on the whole request and each part |
| JSON part fails to deserialize | Metadata part lacks `application/json` or codec does not support it | Set Content-Type on the part and check Jackson/codecs |
| Part not found | Name in `@RequestPart` differs from `name` sent by client | Align part names in the API contract |
| FilePart is null or argument resolution fails | Part lacks a filename or is not a file part | Check how the client constructs the multipart file |
| Upload fails with DataBufferLimitException | Non-file part exceeds maxInMemorySize | Limit metadata size or configure the reader appropriately |
| Out of temp storage space | Large file parts, many concurrent uploads, or missing cleanup | Limit disk usage, quotas, temp directory, and lifecycle |
| File overwrites another file | Using client filename as destination | Generate a server-side destination name |
| Path traversal | Filename contains path segments or `..` | Do not use filename as a path |
| Client sends a spoofed MIME file | Trusting Content-Type from the request | Inspect actual signature/content |
| Controller can no longer read raw body | `getMultipartData` was already called or body was parsed | Choose one consistent multipart reading approach |
| Large upload uses too much memory | Collecting the entire multipart into a map or `byte[]` | Use PartEvent streaming and backpressure |
| Temp file is not deleted | Reading Part directly while skipping delete/cleanup | Compose Part.delete or cleanupMultipart |
| Data is read twice | Part content is not cached like MultiValueMap | Consume part content only once |
| Event stream leaks buffers | PartEvent content is not consumed/relayed/released | Handle every DataBuffer and manage cancellation |
| Using @RequestBody DTO for multipart | DTO body is not equivalent to multipart part binding | Use @RequestPart or PartEvent |
| Calling block in controller | Blocks the event loop | Compose Mono/Flux and use transferTo |

## 15. Meaningful Multipart Testing

A test suite should cover:

1. Valid JSON metadata and valid file.
2. Missing required `metadata` part.
3. Missing file part.
4. JSON part with wrong Content-Type.
5. Malformed JSON or validation failure.
6. Empty file.
7. Multiple files with the same part name.
8. Part count exceeding the limit.
9. Non-file metadata exceeding maxInMemorySize.
10. File exceeding maxDiskUsagePerPart.
11. Filename containing `../`, backslashes, or unusual characters.
12. Spoofed Content-Type.
13. Upload canceled mid-flight.
14. Transfer failure due to unwritable destination directory.
15. Temp file cleanup after success/error/cancel.
16. PartEvent streaming with a file split across multiple events.

Use `WebTestClient` to send real multipart requests. For large files or cancellation, include integration tests through a server runtime and proxy similar to production; isolated unit tests do not fully reproduce buffer, disk, and network behavior.

## 16. Production Readiness Checklist for Multipart Upload

- [ ] Endpoint declares the proper `consumes = multipart/form-data` or required media type contract.
- [ ] Part names are clearly defined and consistent with clients.
- [ ] JSON parts have the right Content-Type and are decoded into dedicated DTOs.
- [ ] Metadata uses Bean Validation.
- [ ] File parts are received as `FilePart` when `transferTo` is needed.
- [ ] Destination paths are server-generated, not based on client filenames.
- [ ] File types are verified by actual content when required.
- [ ] Limits are configured for memory, disk, part count, and total request size.
- [ ] Temp directory has proper permissions and capacity.
- [ ] Part storage is cleaned up according to lifecycle.
- [ ] PartEvent buffers are consumed, relayed, or released.
- [ ] Event loop is never blocked.
- [ ] Authentication, authorization, quotas, and rate limits are enforced.
- [ ] Partial files are handled on error/cancel.
- [ ] Tests cover success, validation error, missing part, size limit, and cancellation.
- [ ] File content, tokens, or sensitive metadata are never logged.

## 17. Self-Check

**Question 1.** What does `@RequestPart("metadata") UploadMetadata` do?

Retrieves the part named metadata and decodes its content according to the part's Content-Type into UploadMetadata.

**Question 2.** Why does a JSON part need Content-Type `application/json`?

Because Spring selects the HTTP message reader based on the target type and the part's media type. An incompatible Content-Type can result in no codec being able to read it.

**Question 3.** How do `Part` and `FilePart` differ?

FilePart extends Part, represents an uploaded file, and adds filename along with transferTo(Path).

**Question 4.** Should `file.filename()` be used as the file storage path?

No. Filename is supplied by the client and may contain path traversal or dangerous characters. Generate the storage name on the server.

**Question 5.** What does `FilePart.transferTo(Path)` return?

`Mono<Void>` signaling whether the file write operation completed or errored.

**Question 6.** What type does `Part.content()` return?

`Flux<DataBuffer>`. When reading raw buffers directly, you must manage consumption/release according to ownership rules.

**Question 7.** Does `ServerWebExchange.getMultipartData()` read the body into a map?

Yes. It returns `Mono<MultiValueMap<String, Part>>` and caches the map; the content of individual parts is not cached and can only be read once.

**Question 8.** What should be used to read multipart sequentially without collecting into a MultiValueMap?

`@RequestBody Flux<PartEvent>` with PartEventHttpMessageReader.

**Question 9.** Is `maxInMemorySize` the total request size?

No. It limits the in-memory portion per part according to how DefaultPartHttpMessageReader handles parts; large file parts can be written to temp storage.

**Question 10.** When using Part directly via BodyExtractors, how do you delete temporary files?

Compose `Part.delete()` or the `ServerWebExchange.cleanupMultipart()` mechanism into the cleanup pipeline; do not call a cleanup Mono and ignore it.

**Question 11.** Why shouldn't `@RequestPart` be used for every extremely large file?

Because map-like named-part access requires parsing multipart and providing parts by name. `Flux<PartEvent>` allows sequential processing with backpressure.

**Question 12.** Can a file's PartEvent span multiple events?

Yes. A large file can be split into multiple FilePartEvent instances; the final event of the part has `isLast()` equal to true.

## 18. Official References

- [Spring Framework — Multipart Content in WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/multipart-forms.html): @RequestPart, Part, FilePart, JSON DTO, validation, MultiValueMap, and PartEvent.
- [Spring Framework — Reactive Core: Multipart Data](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html): ServerWebExchange.getMultipartData, default reader, streaming PartEvent, codecs, and multipart limits.
- [DefaultPartHttpMessageReader JavaDoc](https://docs.spring.io/spring-framework/docs/7.0.8/javadoc-api/org/springframework/http/codec/multipart/DefaultPartHttpMessageReader.html): maxInMemorySize, maxDiskUsagePerPart, maxParts, file storage directory, and header limits.
- [Part JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/codec/multipart/Part.html): name, headers, content, and delete.
- [FilePart JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/codec/multipart/FilePart.html): filename and transferTo.
- [PartEvent JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/codec/multipart/PartEvent.html): event, content buffer, and isLast.
- [ServerWebExchange JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/ServerWebExchange.html): getMultipartData and cleanupMultipart.
- [RFC 7578 — Returning Values from Forms: multipart/form-data](https://www.rfc-editor.org/rfc/rfc7578.html): multipart/form-data format, boundary, Content-Disposition, and filename.

**Remember:** `@RequestPart` accesses a part by name and can decode a JSON part into a DTO; `Part` represents any part with headers/content/delete; `FilePart` adds filename and transferTo. Named-part access is convenient for regular form uploads, while `Flux<PartEvent>` suits streaming large files. Always configure memory/disk/part-count limits, never trust client filename or Content-Type, and manage part and DataBuffer cleanup properly throughout the lifecycle.