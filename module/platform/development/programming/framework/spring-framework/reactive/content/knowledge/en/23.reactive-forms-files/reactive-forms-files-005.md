# Streaming Multipart with Flux<PartEvent> in Spring WebFlux

## 1. Why Stream Multipart Data?

A multipart HTTP request contains multiple **parts** within a single body. A part can be a text field, JSON metadata, or a file. Browsers typically send form uploads with \`Content-Type: multipart/form-data\`; each part has its own headers such as \`Content-Disposition\`, \`Content-Type\`, and corresponding content.

For small files, binding multipart data into an object or a map of parts is often convenient. However, if a request contains large files or many files, parsing the entire multipart body into a collection structure before processing can increase memory usage and delay when the application starts consuming the content.

Spring WebFlux provides **\`Flux<PartEvent>\`** to read multipart sequentially as a stream. Each part is represented by one or more events. The application can receive a chunk of data, process or forward it, and then continue receiving the next chunk instead of collecting the entire file into a RAM object.

Key benefits:

- Process large files buffer by buffer.
- Process parts in the order they appear in the request.
- Write data to storage or relay it to another service as data arrives.
- Use Reactive Streams to coordinate demand and cancellation.
- Avoid creating a \`MultiValueMap<String, Part>\` containing the entire multipart body before processing.

**Important point:** \`Flux<PartEvent>\` represents a stream of events from the multipart body. It does not automatically save files, check permissions, enforce business size limits, or automatically release every buffer retained by the application. The handler must properly consume, forward, or release each part's content.

## 2. PartEvent, FormPartEvent, and FilePartEvent

Spring Framework 6 introduced \`PartEvent\` in package:

~~~java
org.springframework.http.codec.multipart
~~~

Main types:

| Type | Meaning | Characteristic data |
| --- | --- | --- |
| \`PartEvent\` | Base event representing a piece of a multipart request | Headers, DataBuffer content, part name, and last-part flag |
| \`FormPartEvent\` | A regular form field | String value via \`value()\` |
| \`FilePartEvent\` | A chunk of uploaded file data | Original filename via \`filename()\`, headers, and content buffer |

Important methods of \`PartEvent\`:

- \`name()\`: multipart field name according to Content-Disposition's \`name\` parameter.
- \`headers()\`: the part's headers.
- \`content()\`: \`DataBuffer\` holding the content of the current event.
- \`isLast()\`: indicates whether this event is the final event of the part.

\`FormPartEvent\` adds \`value()\` to obtain the text value of a form field. \`FilePartEvent\` adds \`filename()\` to obtain the original filename sent by the client.

A regular form field produces a single \`FormPartEvent\`. A file upload can produce **one or more \`FilePartEvent\` instances**. If a large file is split into multiple buffers, the first event may only contain a portion of the file; subsequent events carry the remaining portions.

Never assume a single \`FilePartEvent\` equals the entire file.

## 3. isLast() and Splitting Events by Part

This is the key rule for processing multipart along exact part boundaries:

**The last event of every part has \`isLast() == true\`.** After that event, the stream may continue with events belonging to the next part.

Therefore, Reactor can use:

~~~java
allPartEvents.windowUntil(PartEvent::isLast)
~~~

\`windowUntil\` creates one window per part. Each window contains all events belonging to that part, including the final event where \`isLast() == true\`.

Example of a request containing a description field and a large file:

~~~text
Multipart request
    |
    +-- FormPartEvent(description, isLast=true)
    |
    +-- FilePartEvent(file, buffer 1, isLast=false)
    +-- FilePartEvent(file, buffer 2, isLast=false)
    +-- FilePartEvent(file, buffer 3, isLast=true)
    |
    +-- FormPartEvent(category, isLast=true)
~~~

After \`windowUntil(PartEvent::isLast)\`:

~~~text
Window 1: [FormPartEvent(description)]
Window 2: [FilePartEvent(buffer 1), FilePartEvent(buffer 2),
           FilePartEvent(buffer 3)]
Window 3: [FormPartEvent(category)]
~~~

This lets the application process one complete part before moving to the next part. For multi-buffer files, all buffers of the file remain in the same window.

Do not use \`windowUntil\` with arbitrary predicates like checking event types or filenames. The \`isLast()\` predicate accurately reflects part boundaries per Spring's contract.

## 4. switchOnFirst() to Identify Part Types

Once you have a window, you need to know whether that part is a text field or a file. Reactor provides \`switchOnFirst()\`:

~~~java
partEvents.switchOnFirst((signal, events) -> {
    if (signal.hasValue()) {
        PartEvent first = signal.get();

        if (first instanceof FormPartEvent formEvent) {
            String value = formEvent.value();
            // Process text field
        }
        else if (first instanceof FilePartEvent fileEvent) {
            String filename = fileEvent.filename();
            Flux<DataBuffer> contents =
                events.map(PartEvent::content);
            // Process file content
        }
    }

    return Mono.empty();
});
~~~

\`switchOnFirst\` lets you inspect the first event of the window before deciding how to consume the rest. The \`events\` parameter is the publisher of events in that window, including the first event.

Common processing approach:

1. Get the first event from \`signal\`.
2. Check \`instanceof FormPartEvent\` or \`instanceof FilePartEvent\`.
3. If it is a form field, read \`value()\` and finish consuming the part.
4. If it is a file, obtain \`Flux<DataBuffer>\` from \`events.map(PartEvent::content)\`.
5. Write, relay, or release all buffers.
6. Only move to the next part after the publisher handling the current part completes.

If the first event has no value because the window already completed or errored, propagate the terminal signal from \`events\` instead of synthesizing dummy data.

## 5. concatMap Preserves Order and Coordinates Backpressure

Combining the two operators:

~~~java
allPartEvents
    .windowUntil(PartEvent::isLast)
    .concatMap(part -> part.switchOnFirst((signal, events) -> {
        // Process one part
        return Mono.empty();
    }));
~~~

\`concatMap\` processes each window sequentially and waits for the publisher handling the current part to complete before processing the next part.

This is useful when:

- The file needs to be completely written before processing the next metadata part.
- Parts depend on ordering.
- You want to keep the pipeline simple and limit the number of simultaneously open files.
- You want to avoid unintended concurrent storage writes.

You can use \`flatMap\` if parts are independent and business logic allows concurrent processing. However, you must bound concurrency, manage multiple concurrent files/handles, and handle result ordering. For standard uploads, \`concatMap\` is easier to control.

Backpressure allows downstream to pace event consumption. However, it does not replace file size limits, part counts, upload timeouts, or user quotas.

## 6. Reading Multipart Streaming with @RequestBody Flux<PartEvent>

In an annotated controller, declare:

~~~java
@PostMapping(
    path = "/upload",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
public Mono<UploadResult> upload(
        @RequestBody Flux<PartEvent> allPartEvents) {
    // Process as a stream
}
~~~

Spring selects \`PartEventHttpMessageReader\` to decode the multipart body into a \`PartEvent\` stream.

Notable points:

- \`@RequestBody Flux<PartEvent>\` lets you read parts sequentially.
- No need to collect the whole request into a \`MultiValueMap\`.
- Large files can be represented by multiple events and buffers.
- The request's Content-Type must be \`multipart/form-data\` with a valid boundary.
- The body should only be consumed once; do not read the same request body in multiple independent places.

Example HTTP request:

~~~http
POST /api/upload HTTP/1.1
Content-Type: multipart/form-data; boundary=----demo-boundary

------demo-boundary
Content-Disposition: form-data; name="description"

Quarterly report
------demo-boundary
Content-Disposition: form-data; name="file"; filename="report.pdf"
Content-Type: application/pdf

...file bytes...
------demo-boundary--
~~~

The boundary is generated by the client to separate parts. When using cURL or WebClient, let the multipart tool generate the boundary and matching header automatically. Never set an arbitrary boundary and send a mismatched body.

## 7. When to Use PartEvent Instead of @RequestPart or MultiValueMap?

Spring offers several ways to read multipart data. Choose based on how the application needs to consume data:

| Reading approach | Characteristics | Best suited for |
| --- | --- | --- |
| \`@RequestPart\` | Binds a named part into a parameter like a DTO or \`FilePart\` | Simple form uploads, small/medium files, readable code |
| \`Mono<MultiValueMap<String, Part>>\` | Parses multipart into a map of parts | Accessing multiple parts by name or needing a map structure |
| \`ServerWebExchange.getMultipartData()\` | Gets parsed multipart data cached on the exchange | Multiple components needing map-like access to multipart data |
| \`@RequestBody Flux<PartEvent>\` | Reads events sequentially without collecting the whole multipart body into a map | Large files, sequential processing, relaying, or streaming uploads |

\`@RequestPart\` example:

~~~java
@PostMapping("/simple-upload")
public Mono<String> upload(
        @RequestPart("description") String description,
        @RequestPart("file") FilePart file) {
    return file.transferTo(Path.of("uploads", "fixed-name"))
        .thenReturn("Uploaded: " + description);
}
~~~

This is an illustrative example; the saved filename must be generated safely in a real application. This approach is easy to use, though it is not an example of sequential event processing with \`PartEvent\`.

When using \`MultipartHttpMessageReader\`, the framework parses parts and collects them into a \`MultiValueMap\`. For very large uploads, if you want to process content immediately as it arrives, \`Flux<PartEvent>\` is a better fit.

Once \`ServerWebExchange.getMultipartData()\` has been called to parse and cache map-like multipart data, you cannot subsequently read the raw request body as a fresh independent stream. Choose one body consumption strategy from the start.

## 8. Managing DataBuffer: Preventing Memory Leaks

\`PartEvent.content()\` returns a \`DataBuffer\`. On servers like Reactor Netty, buffers may be pooled and reference-counted. Once a buffer has been consumed, it must be released according to its lifecycle.

Spring's rule:

**The buffer content of every PartEvent must be completely consumed, relayed elsewhere, or released.**

If you skip content or stop processing a part midway without cleaning up buffers, the application can suffer memory leaks or hold onto pooled buffer resources for too long.

### When Writing Files with DataBufferUtils.write

You can stream buffers directly to a file using the overload taking \`Path\`:

~~~java
Flux<DataBuffer> contents =
    partEvents.map(PartEvent::content);

Mono<Void> write =
    DataBufferUtils.write(
        contents,
        destination,
        StandardOpenOption.CREATE_NEW
    );
~~~

The publisher completes when writing finishes or emits an error if the write operation fails. The \`Path\` overload manages writing via an internal channel; compose this publisher into the pipeline rather than subscribing manually.

### When Writing Manually via a Channel or OutputStream

The \`DataBufferUtils.write(..., channel)\` and \`write(..., OutputStream)\` overloads return a stream of buffers and do not automatically release source buffers. If you use these overloads directly, consume the returned publisher with a release consumer while also managing closing the channel/stream:

~~~java
DataBufferUtils.write(contents, outputStream)
    .doOnNext(DataBufferUtils.releaseConsumer())
    .then();
~~~

This is only an illustrative snippet. \`OutputStream\` is a blocking API; do not perform synchronous writes directly on the event loop. For file paths, prefer the appropriate \`DataBufferUtils\` overload or a reactive storage client.

### When Skipping or Discarding Buffers

If the pipeline uses operators that can drop buffers, configure proper discard cleanup:

~~~java
.doOnDiscard(DataBuffer.class, DataBufferUtils::release)
~~~

Add a discard hook only when the pipeline can discard unconsumed buffers; avoid double-releasing buffers that a writer or consumer already owns and releases.

## 9. Streaming File Writes and Protecting Filenames

Do not use client-sent filenames directly to construct paths:

~~~java
Path destination = uploadDirectory.resolve(fileEvent.filename());
~~~

This is dangerous. The filename can contain path segments, \`..\`, special characters, or names intended to overwrite other files. Client filenames must be treated solely as untrusted metadata.

A safer strategy:

1. Generate a storage key from a UUID or server-managed ID.
2. Save files inside a fixed server-configured directory.
3. Do not let the client choose the destination directory.
4. Store the original filename only as metadata if business logic needs to display it.
5. Verify upload permissions and file access permissions.
6. Enforce limits on size, file count, part count, and quotas.
7. Verify content type via actual inspection, not solely from client-sent Content-Type.
8. Scan for malware or handle untrusted content per system policy.

Filename generation example:

~~~java
String storageKey = UUID.randomUUID().toString();
Path destination = uploadDirectory.resolve(storageKey);
~~~

The original name \`report.pdf\` can be stored in the database alongside the storage key. The physical file is saved under the server-generated name.

## 10. Handling Multipart Limits

Streaming avoids collecting the entire file on the heap, but that does not mean requests should be allowed unlimited size. Limits are needed across multiple layers:

- Maximum size per individual file.
- Maximum size per form field.
- Header size per part.
- Total number of parts in a request.
- Total upload volume per user/tenant.
- Maximum time allowed to send a request.
- Number of concurrent upload requests.
- Storage capacity and temporary file cleanup policies.

\`PartEventHttpMessageReader\` provides settings such as:

| Setting | Meaning |
| --- | --- |
| \`setMaxInMemorySize(...)\` | Memory limit for form fields |
| \`setMaxHeadersSize(...)\` | Header size limit per part |
| \`setMaxParts(...)\` | Limit on number of parts in one request |
| \`setMaxPartSize(...)\` | Maximum size limit per part |

Per Spring Framework 6.2 Javadoc, the default memory limit for form fields is 256 KiB and the default header limit is 10 KiB. \`maxParts\` and \`maxPartSize\` are unlimited by default in versions that provide these settings. Configure limits appropriate to your workload instead of relying on defaults.

Reader configuration example:

~~~java
PartEventHttpMessageReader reader =
    new PartEventHttpMessageReader();

reader.setMaxInMemorySize(256 * 1024);
reader.setMaxHeadersSize(10 * 1024);
reader.setMaxParts(10);
reader.setMaxPartSize(50L * 1024 * 1024);
~~~

This is a reader configuration snippet; register the instance into the server's codec registry according to your Spring Framework/Boot setup. Avoid registering a duplicate reader without checking existing reader ordering.

In addition to reader limits, set a request size limit at the reverse proxy/API gateway and business quotas in the service. A limit at one layer does not replace limits at the others.

## 11. Handling Form Fields and Files per Window

A controller can use \`windowUntil\` and \`switchOnFirst\` as follows:

~~~java
@PostMapping(
    path = "/upload",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
public Mono<UploadSummary> upload(
        @RequestBody Flux<PartEvent> allEvents) {

    Map<String, String> fields = new LinkedHashMap<>();
    List<StoredFile> files = new ArrayList<>();

    return allEvents
        .windowUntil(PartEvent::isLast)
        .concatMap(partEvents ->
            processPart(partEvents, fields, files)
        )
        .then(Mono.fromSupplier(() ->
            new UploadSummary(
                Map.copyOf(fields),
                List.copyOf(files)
            )
        ));
}
~~~

Method to process a single part:

~~~java
private Mono<Void> processPart(
        Flux<PartEvent> partEvents,
        Map<String, String> fields,
        List<StoredFile> files) {

    return partEvents.switchOnFirst((signal, events) -> {
        if (!signal.hasValue()) {
            return events.then();
        }

        PartEvent first = signal.get();

        if (first instanceof FormPartEvent form) {
            fields.put(form.name(), form.value());
            return events.then();
        }

        if (first instanceof FilePartEvent file) {
            String originalFilename =
                Objects.requireNonNullElse(file.filename(), "");

            String contentType = Optional
                .ofNullable(file.headers().getContentType())
                .map(MediaType::toString)
                .orElse(MediaType.APPLICATION_OCTET_STREAM_VALUE);

            Path destination =
                uploadDirectory.resolve(UUID.randomUUID().toString());

            Flux<DataBuffer> contents =
                events.map(PartEvent::content);

            return Mono.fromCallable(
                    () -> Files.createDirectories(uploadDirectory)
                )
                .subscribeOn(Schedulers.boundedElastic())
                .then(DataBufferUtils.write(
                    contents,
                    destination,
                    StandardOpenOption.CREATE_NEW
                ))
                .then(Mono.fromRunnable(() ->
                    files.add(new StoredFile(
                        file.name(),
                        originalFilename,
                        destination.getFileName().toString(),
                        contentType
                    ))
                ));
        }

        return events
            .map(PartEvent::content)
            .doOnNext(DataBufferUtils.releaseConsumer())
            .then(Mono.<Void>error(
                new IllegalArgumentException("Unsupported multipart part")
            ));
    });
}
~~~

This example focuses on the processing structure. In production code, verify how form part buffers are consumed/released for the reader in use; clean up partial files when writes error or requests are canceled; and enforce validation, size limits, authorization, and quotas.

Return types can be defined as:

~~~java
public record StoredFile(
    String partName,
    String originalFilename,
    String storageKey,
    String contentType
) {}

public record UploadSummary(
    Map<String, String> fields,
    List<StoredFile> files
) {}
~~~

Here \`fields\` uses a plain map, so if a client sends multiple values with the same name, later values overwrite earlier ones. If the contract permits multiple fields with the same name, use \`MultiValueMap<String, String>\` or a list structure.

## 12. Complete Java 17+ Example with Spring Boot WebFlux

The example below builds an endpoint receiving multipart data with a \`description\` field and a file:

- \`POST /api/uploads\`: reads the body as \`Flux<PartEvent>\`.
- Form fields are read via \`FormPartEvent.value()\`.
- Files are split across events and written sequentially via \`DataBufferUtils.write\`.
- Storage keys are server-generated using UUIDs without using client filenames as paths.
- Response returns upload metadata after all parts are processed.

Structure:

~~~text
part-event-upload/
├── pom.xml
└── src/main/java/com/example/partev/
    ├── PartEventApplication.java
    └── UploadController.java
~~~

File \`pom.xml\` (Spring Boot 3.5.0, Java 17+):

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>part-event-upload</artifactId>
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

File \`src/main/java/com/example/partev/PartEventApplication.java\`:

~~~java
package com.example.partev;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PartEventApplication {
    public static void main(String[] args) {
        SpringApplication.run(PartEventApplication.class, args);
    }
}
~~~

File \`src/main/java/com/example/partev/UploadController.java\`:

~~~java
package com.example.partev;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.UUID;

import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferUtils;
import org.springframework.http.MediaType;
import org.springframework.http.codec.multipart.FilePartEvent;
import org.springframework.http.codec.multipart.FormPartEvent;
import org.springframework.http.codec.multipart.PartEvent;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@RestController
@RequestMapping("/api/uploads")
public class UploadController {

    private final Path uploadDirectory =
        Path.of("uploads").toAbsolutePath().normalize();

    public record StoredFile(
        String partName,
        String originalFilename,
        String storageKey,
        String contentType
    ) {}

    public record UploadSummary(
        Map<String, String> fields,
        List<StoredFile> files
    ) {}

    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public Mono<UploadSummary> upload(
            @RequestBody Flux<PartEvent> allEvents) {

        Map<String, String> fields = new LinkedHashMap<>();
        List<StoredFile> files = new ArrayList<>();

        return allEvents
            .windowUntil(PartEvent::isLast)
            .concatMap(partEvents ->
                processPart(partEvents, fields, files)
            )
            .then(Mono.fromSupplier(() ->
                new UploadSummary(
                    Map.copyOf(fields),
                    List.copyOf(files)
                )
            ));
    }

    private Mono<Void> processPart(
            Flux<PartEvent> partEvents,
            Map<String, String> fields,
            List<StoredFile> files) {

        return partEvents.switchOnFirst((signal, events) -> {
            if (!signal.hasValue()) {
                return events.then();
            }

            PartEvent first = signal.get();

            if (first instanceof FormPartEvent form) {
                fields.put(form.name(), form.value());
                return events.then();
            }

            if (first instanceof FilePartEvent file) {
                String originalFilename =
                    Objects.requireNonNullElse(file.filename(), "");

                String contentType = Optional
                    .ofNullable(file.headers().getContentType())
                    .map(MediaType::toString)
                    .orElse(MediaType.APPLICATION_OCTET_STREAM_VALUE);

                Path destination =
                    uploadDirectory.resolve(UUID.randomUUID().toString());

                Flux<DataBuffer> contents =
                    events.map(PartEvent::content);

                return Mono.fromCallable(
                        () -> Files.createDirectories(uploadDirectory)
                    )
                    .subscribeOn(Schedulers.boundedElastic())
                    .then(DataBufferUtils.write(
                        contents,
                        destination,
                        StandardOpenOption.CREATE_NEW
                    ))
                    .then(Mono.fromRunnable(() ->
                        files.add(new StoredFile(
                            file.name(),
                            originalFilename,
                            destination.getFileName().toString(),
                            contentType
                        ))
                    ));
            }

            return events
                .map(PartEvent::content)
                .doOnNext(DataBufferUtils.releaseConsumer())
                .then(Mono.<Void>error(
                    new IllegalArgumentException(
                        "Unsupported multipart part"
                    )
                ));
        });
    }
}
~~~

Run from the \`part-event-upload\` directory with JDK 17+ and Maven:

~~~bash
mvn spring-boot:run
~~~

### Sending Multipart with cURL

~~~bash
curl -i -X POST http://localhost:8080/api/uploads \
  -F "description=Quarterly report" \
  -F "file=@./report.pdf;type=application/pdf"
~~~

cURL generates the boundary and matching multipart Content-Type automatically. Do not manually set the \`Content-Type: multipart/form-data\` header unless you construct a valid matching boundary yourself.

The JSON response looks like:

~~~json
{
  "fields": {
    "description": "Quarterly report"
  },
  "files": [
    {
      "partName": "file",
      "originalFilename": "report.pdf",
      "storageKey": "<server-generated-uuid>",
      "contentType": "application/pdf"
    }
  ]
}
~~~

The storage key is a server-generated UUID, so the exact value changes on every upload. The file is saved in the \`uploads\` folder of the working directory. This demo does not yet include database persistence, authentication, virus scanning, or partial file cleanup; add those before deploying to production.

## 13. Sending Streaming Multipart with WebClient

Spring WebFlux also supports building multipart bodies from \`PartEvent\` on the client side. You can use:

- \`FormPartEvent.create(name, value)\` for form fields.
- \`FilePartEvent.create(name, Path)\` or \`FilePartEvent.create(name, Resource)\` for files.
- \`Flux.concat(...)\` to concatenate events into a single publisher.

Example:

~~~java
Path file = Path.of("report.pdf");

Flux<PartEvent> multipart = Flux.concat(
    FormPartEvent.create("description", "Quarterly report"),
    FilePartEvent.create("file", file)
);

Mono<UploadController.UploadSummary> result =
    webClient.post()
        .uri("http://localhost:8080/api/uploads")
        .body(multipart, PartEvent.class)
        .retrieve()
        .bodyToMono(UploadController.UploadSummary.class);
~~~

\`webClient\` is a configured \`WebClient\` instance in the application. The multipart writer creates the boundary and serializes the PartEvents into the request body. You do not need to assemble raw multipart bytes manually.

If the server receives multipart and needs to relay it to another service, it can forward the event publisher directly:

~~~java
Mono<Void> relay(Flux<PartEvent> incoming) {
    return webClient.post()
        .uri("http://storage-service/internal/upload")
        .body(incoming, PartEvent.class)
        .retrieve()
        .bodyToMono(Void.class);
}
~~~

This is a direct relay example. When relaying, the incoming publisher can only be consumed once; do not subscribe once to log and subscribe a second time to send. If you need to inspect metadata, use operators inside the same pipeline and ensure buffers are still forwarded or released with proper ownership.

## 14. Multipart Browser Forms and Clients

An HTML form must declare:

~~~html
<form method="post" enctype="multipart/form-data" action="/api/uploads">
  <label>
    Description
    <input type="text" name="description">
  </label>

  <label>
    File
    <input type="file" name="file">
  </label>

  <button type="submit">Upload</button>
</form>
~~~

When the browser submits the form, it generates the multipart boundary and sends each part. If using JavaScript \`fetch\` with \`FormData\`, likewise do not set the Content-Type header manually:

~~~javascript
const form = new FormData();
form.append("description", "Quarterly report");
form.append("file", fileInput.files[0]);

const response = await fetch("/api/uploads", {
  method: "POST",
  body: form
});
~~~

The browser must set the boundary in the header itself. If code manually overrides Content-Type to \`multipart/form-data\` without a boundary, the server cannot split the parts properly.

## 15. Handling Errors, Cancellation, and Partial Files

A multipart upload can fail mid-flight due to:

- Client disconnecting.
- Request timing out.
- File exceeding size limits.
- Storage running out of space or failing to write.
- Filesystem permission denial.
- Malformed multipart data.
- Downstream service going down during a relay.

When a request is canceled or writing fails, the application needs a policy to clean up partially written data. A practical design can:

1. Write to a temporary file using a server-generated storage key.
2. Mark the upload complete only after all parts have been written successfully.
3. On error/cancel, delete the temporary file via a cleanup publisher.
4. On success, atomically move the temporary file to a confirmed location if the filesystem supports it.
5. Write metadata to the database after the file finishes or use upload state to recover if the process stops mid-flight.

Do not treat receiving the first event as a successful upload. A file is complete only once the part's final event has been processed and the writer completes.

If relaying to another service, downstream errors must propagate through the pipeline. Never swallow errors and return a success response when the file has not been fully received.

## 16. Distinguishing Streaming from Temporary Disk Spooling

\`Flux<PartEvent>\` lets the application process content as a stream. That does not mean the entire request always stays in RAM, nor does it mean every part is automatically written to a temporary file under the same policy.

Some other multipart APIs may parse parts and spill large files to temporary storage depending on the reader/configuration. Meanwhile, \`PartEventHttpMessageReader\` delivers an event stream for the application to consume itself.

Comparison:

| Approach | Where data is held | Control |
| --- | --- | --- |
| \`@RequestBody Mono<MultiValueMap<String, Part>>\` | Multipart is parsed into a map; reader may manage part storage | Easy access by name, but requires limit configuration |
| \`@RequestPart FilePart\` | Part abstraction managed by the multipart reader | Convenient API for standard uploads |
| \`@RequestBody Flux<PartEvent>\` | Events and buffers are emitted sequentially | Application decides writing, relaying, releasing, and cleanup |

If the goal is simply uploading moderate files, \`FilePart\` is usually simpler. If you need streaming, relaying, inspecting chunks, or avoiding collecting the whole multipart body into a map, \`Flux<PartEvent>\` gives clearer control.

## 17. Common Mistakes

1. **Treating one FilePartEvent as the whole file:** large files can be split into multiple events. Use \`windowUntil(PartEvent::isLast)\` to group events by part.
2. **Not checking isLast():** you might process a file while content is still incomplete. Wait for the part's window to finish.
3. **Using collectList() on all PartEvents:** collects the entire request into memory and defeats streaming. Process each window with \`concatMap\`.
4. **Using @RequestPart when per-event processing is needed:** \`@RequestPart\` is convenient for named parts, not sequential PartEvent processing. Use \`@RequestBody Flux<PartEvent>\`.
5. **Reading multipart into MultiValueMap then trying to read the raw body:** the body is already parsed/cached; the raw request body cannot be treated as a fresh stream.
6. **Failing to consume or release DataBuffers:** can leak pooled buffers. Every piece of content must be written, relayed, or released.
7. **Calling subscribe() inside the controller:** detaches the upload from the HTTP lifecycle, making cancellation and errors hard to manage. Return the publisher for WebFlux to manage.
8. **Calling block() when writing files or processing parts:** can block the event loop. Use reactive APIs; offload blocking filesystem operations like directory creation to boundedElastic.
9. **Using client-sent filenames as paths:** risks path traversal or overwrites. Generate safe storage keys on the server.
10. **Trusting client-sent Content-Type:** headers can be forged. Inspect actual content and enforce file-type policies.
11. **Not limiting part count:** requests can send huge numbers of fields/files. Configure maxParts and quotas.
12. **Not limiting form fields:** text fields can be abnormally large. Set maxInMemorySize.
13. **Not limiting file size:** streaming does not mean infinite files. Set maxPartSize and gateway request limits.
14. **Using unbounded flatMap for files:** can open too many file writers and put pressure on storage. Use concatMap or flatMap with bounded concurrency.
15. **Not cleaning up when the client cancels:** partial files can occupy storage indefinitely. Tie cleanup to the upload lifecycle.
16. **Writing files before checking permissions:** allows unauthorized users to consume storage. Check authentication/authorization and quotas before or during upload.
17. **Relaying the same publisher multiple times:** the request body is a one-shot stream. Do not subscribe to log and subscribe again to send.
18. **Manually setting multipart Content-Type without a boundary:** the server cannot parse parts. Let cURL, browsers, or WebClient generate the boundary.
19. **Assuming PartEvent saves files automatically:** PartEvent is only an event API. The application must choose where to store data and perform the write/relay.
20. **Not distinguishing form fields from file parts:** use \`switchOnFirst\` and check the subtype before reading content.

## 18. Multipart Streaming Implementation Checklist

Before deploying the upload endpoint to production, check:

- Endpoint accepts \`multipart/form-data\`.
- Handler uses \`Flux<PartEvent>\` when sequential processing is required.
- Uses \`windowUntil(PartEvent::isLast)\` to split parts properly.
- Uses \`switchOnFirst\` to classify FormPartEvent and FilePartEvent.
- Every file processes all events, not just the first event.
- Every DataBuffer is consumed, relayed, or released.
- Never collects entire files into \`byte[]\`, \`String\`, or \`List<DataBuffer>\`.
- Files are stored using server-generated storage keys.
- Limits are set for form fields, headers, part count, and file size.
- Quotas, timeouts, authorization, and content checks are enforced.
- Temporary files are cleaned up on error/cancellation.
- Policies exist for original filenames and metadata.
- Clients do not manually set multipart boundaries.
- No manual subscribe/block calls inside controllers.
- Tests cover multi-buffer files, empty parts, form fields, large uploads, write errors, and cancellation.

## 19. Self-Check Questions

**1.** What is \`PartEvent\`? An event representing a piece of a multipart request, containing headers and DataBuffer content.

**2.** Which event does a form field produce? \`FormPartEvent\`, whose value can be read with \`value()\`.

**3.** Which event does a file upload produce? \`FilePartEvent\`; large files can emit multiple events.

**4.** What does \`isLast()\` indicate? The current event is the final event of that part.

**5.** Why use \`windowUntil(PartEvent::isLast)\`? To group all events belonging to the same part into a single window.

**6.** What does \`switchOnFirst()\` help with? Identifying the part type from the first event before choosing how to process it.

**7.** Why is \`concatMap\` usually appropriate? It processes each part in order and waits for the previous part to finish.

**8.** Should \`collectList()\` be used for large multipart files? No, if the goal is streaming; it collects data into memory.

**9.** Why must DataBuffers be consumed or released? On some servers, buffers are pooled and reference-counted; forgetting them can cause memory leaks.

**10.** Should the original filename be used directly as a path? No. Generate a server-side storage key and keep the original name as metadata.

**11.** Is \`@RequestPart\` the same as \`Flux<PartEvent>\`? No. RequestPart is convenient for named parts; Flux<PartEvent> processes events sequentially.

**12.** Do clients need to generate a boundary manually when using cURL or WebClient? No. Let the client's multipart writer create the boundary and Content-Type.

**13.** What if an upload is canceled mid-file? Stop upstream and clean up temporary/partial files according to the lifecycle.

**14.** Does streaming bypass size limits? No. You still need limits for form fields, headers, part counts, file sizes, quotas, and timeouts.

**15.** When relaying PartEvent with WebClient, can you subscribe to the publisher multiple times? No. The body is a one-shot stream; compose everything into a single pipeline.

**Remember:** \`Flux<PartEvent>\` lets you read multipart data as a stream. Each form field typically produces one \`FormPartEvent\`; large files can produce multiple \`FilePartEvent\` instances. Use \`windowUntil(PartEvent::isLast)\` to split parts, \`switchOnFirst\` to classify them, and \`concatMap\` to process them sequentially. Every DataBuffer must be written, relayed, or released. Generate saved filenames on the server, configure multipart limits, handle cancellation and cleanup, and let cURL/browsers/WebClient generate the boundary.

**Official Documentation:**
- [Spring Framework 6.2 — Multipart Content in WebFlux Controllers](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/multipart-forms.html)
- [Spring Framework 6.2 — Multipart Streaming in Functional Endpoints](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-functional.html)
- [Spring Framework 6.2 — Reactive Core and Multipart Readers](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html)
- [PartEvent Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/http/codec/multipart/PartEvent.html)
- [PartEventHttpMessageReader Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/http/codec/multipart/PartEventHttpMessageReader.html)
- [DataBufferUtils Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/io/buffer/DataBufferUtils.html)
- [WebClient Multipart Request Body](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-webclient/client-body.html).