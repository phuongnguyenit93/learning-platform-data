# Limiting Size, Part Count, and Temporary Resources in Spring WebFlux Multipart

## 1. Why Limit Multipart Uploads?

A multipart request can contain many parts: text fields, JSON metadata, images, documents, or multiple files. Each part has its own headers and body. Without limits, clients can send huge files that fill temporary disk space, thousands of tiny parts that inflate parsing cost, large text fields that swell the heap, oversized part headers, or many concurrent uploads that multiply resource usage.

Spring WebFlux has two primary reading modes. The standard reader creates Part objects and can spill large files to a temporary directory. The PartEvent reader emits data sequentially so the application can process each chunk. The two modes have different limits and resource lifecycles.

The goal is to simultaneously control **memory, disk usage, part count, header size, total request size, and concurrent uploads**. A single limit cannot protect the entire system.

## 2. How Is Multipart Read?

A multipart request has the general form:

~~~http
POST /uploads HTTP/1.1
Content-Type: multipart/form-data; boundary=----demo

------demo
Content-Disposition: form-data; name="description"

profile photo
------demo
Content-Disposition: form-data; name="file"; filename="avatar.png"
Content-Type: image/png

(binary file bytes)
------demo--
~~~

Each boundary separates a part. Each part has headers and content; a file part can contain a large number of bytes.

| Model | Commonly used API | How it works |
| --- | --- | --- |
| Aggregate parts | @RequestPart, MultiValueMap<String, Part>, getMultipartData() | Parses parts and collects metadata/Part objects into a map |
| Streaming parts | @RequestBody Flux<PartEvent> | Receives events sequentially, handling each part and chunk |

### 2.1. Aggregate Parts

MultipartHttpMessageReader delegates parsing to DefaultPartHttpMessageReader, then collects the Parts into a MultiValueMap. File parts larger than the memory threshold are written to temporary files; smaller parts may stay in memory.

~~~java
@PostMapping(path = "/upload", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
Mono<UploadResult> upload(
        @RequestPart("metadata") Mono<UploadMetadata> metadata,
        @RequestPart("file") FilePart file) {
    // Process metadata and file.
}
~~~

Or receive all parts:

~~~java
@PostMapping(path = "/upload-all", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
Mono<Void> uploadAll(
        @RequestBody Mono<MultiValueMap<String, Part>> parts) {
    // Iterate over parts by name.
    return Mono.empty();
}
~~~

ServerWebExchange also provides getMultipartData(). The result is cached so multiple components can access the parsed map. Once multipart data has been read, you cannot go back and read the raw request body as if it were unconsumed; consistently use the chosen multipart API.

### 2.2. Streaming with PartEvent

If files are large or data must be forwarded without collecting the entire multipart body into a map, use Flux<PartEvent>. Form fields typically produce a single FormPartEvent; large files can produce multiple FilePartEvents. The final event of each part has isLast() equal to true.

~~~java
@PostMapping(path = "/stream-upload", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
Mono<Void> streamUpload(@RequestBody Flux<PartEvent> events) {
    return events
            .windowUntil(PartEvent::isLast)
            .concatMap(partEvents -> partEvents.switchOnFirst((signal, content) -> {
                if (!signal.hasValue()) {
                    return content.then();
                }

                PartEvent first = signal.get();

                if (first instanceof FormPartEvent form) {
                    validateField(form.name(), form.value());
                    return content.then();
                }

                if (first instanceof FilePartEvent file) {
                    String clientFilename = file.filename();
                    Flux<DataBuffer> chunks = content.map(PartEvent::content);
                    return storeChunks(chunks, clientFilename);
                }

                return Mono.error(new IllegalStateException("Unsupported part"));
            }))
            .then();
}
~~~

This is an illustrative processing skeleton; validateField and storeChunks represent application logic. For each part event, the DataBuffer content must be completely consumed, relayed, or released. Never skip chunks when exiting a processing branch early.

Streaming reduces the need to hold whole files in memory or the multipart reader's temporary files. In return, the application becomes responsible for handling backpressure, writing chunks, limiting total bytes, and cleaning up on error or cancellation.

## 3. Limits in Spring WebFlux

### 3.1. max-in-memory-size

~~~properties
spring.webflux.multipart.max-in-memory-size=256KB
~~~

Its meaning depends on the part type in DefaultPartHttpMessageReader:

- For **non-file parts** like text fields or JSON metadata, this is the maximum size kept in memory. Exceeding the threshold rejects the part, typically throwing DataBufferLimitException.
- For **file parts**, this is the threshold before content is spilled to a temporary file. Files larger than this threshold are not automatically rejected solely for exceeding it.

The default in Spring Boot 3.5 is 256KB per part. Setting -1 keeps all content in memory; that is unsuitable for large file uploads or high concurrency.

Do not mistake 256KB for a total request limit. A request can have many parts; memory usage also depends on part count and concurrent requests.

### 3.2. max-disk-usage-per-part

~~~properties
spring.webflux.multipart.max-disk-usage-per-part=20MB
~~~

Limits the disk space allowed for **each file part** when the reader writes files to the temp directory. The default is -1, meaning unlimited.

This is not the total disk usage for the whole request. For example, a request with 4 file parts each allowed 20MB can use up to about 80MB of temp space for one request, before overhead. With 50 concurrent requests, the theoretical maximum scales with the request count.

This limit has no effect if max-in-memory-size is set to -1 because the reader never spills file parts to disk. With PartEvent streaming, the application handles events directly, so per-part disk limits and the temporary file directory are not used in the same way.

### 3.3. max-parts

~~~properties
spring.webflux.multipart.max-parts=5
~~~

Limits the number of parts in a multipart request. Parts include both files and form/metadata fields; it does not count files alone. Default is -1, unlimited.

A small limit prevents requests with thousands of tiny fields from driving up CPU, object allocation, and management memory.

### 3.4. max-headers-size

~~~properties
spring.webflux.multipart.max-headers-size=10KB
~~~

Limits the memory allocated for the header section of **each part**. These are the inner multipart headers such as Content-Disposition and Content-Type; it is not the request's overall HTTP header limit.

The Spring Boot 3.5 default is 10KB per part. Avoid setting -1 unless clients genuinely require huge headers.

### 3.5. file-storage-directory

~~~properties
spring.webflux.multipart.file-storage-directory=./var/tmp/demo-multipart-tmp
~~~

Specifies the directory used to store file parts larger than max-in-memory-size. If unconfigured, Spring uses a directory under the system temporary directory.

This directory needs sufficient capacity and quotas, least-privilege permissions, monitoring for free space/inodes/write throughput, and a process to clean orphaned files after crashes. This is intermediate storage managed by the multipart reader, distinct from the final business file storage directory.

### 3.6. headers-charset

~~~properties
spring.webflux.multipart.headers-charset=UTF-8
~~~

Selects the charset used to decode part headers. Default is UTF-8. Keep the default unless a legacy client requires a specific charset and has been tested.

## 4. Spring Boot 3.5 Configuration

Spring Boot provides a dedicated property group for WebFlux:

~~~yaml
spring:
  webflux:
    multipart:
      max-in-memory-size: 64KB
      max-disk-usage-per-part: 20MB
      max-parts: 5
      max-headers-size: 10KB
      headers-charset: UTF-8
      file-storage-directory: ./var/tmp/demo-multipart-tmp
~~~

Explanation of the sample configuration:

- Non-file parts larger than 64KB are rejected.
- File parts larger than 64KB are written to temporary files rather than kept entirely in memory.
- Each file part can use at most 20MB of temporary disk space.
- A request can contain at most 5 parts, including both metadata and files.
- Headers for each part are capped at 10KB.
- Temporary files are stored in demo-multipart-tmp.

The example values are an illustrative starting point, not universal limits for every system. Choose values based on file types, concurrent uploads, volume capacity, and SLAs.

### 4.1. Do Not Confuse WebFlux Settings with Spring MVC

| Spring MVC / Servlet | Spring WebFlux |
| --- | --- |
| spring.servlet.multipart.max-file-size | spring.webflux.multipart.max-disk-usage-per-part |
| spring.servlet.multipart.max-request-size | No equivalent WebFlux property in Boot 3.5 multipart properties |
| MultipartFile | FilePart |
| Servlet multipart temporary storage | DefaultPartHttpMessageReader and Part |

Do not use spring.servlet.multipart.max-request-size to limit uploads in a WebFlux application. That is a Servlet stack property.

### 4.2. No Single Total Request-Size Property in WebFlux Multipart

In Spring Boot 3.5's spring.webflux.multipart group, there are limits for memory, disk per part, part count, header size, and temp directory. There is no spring.webflux.multipart.max-request-size equivalent to spring.servlet.multipart.max-request-size.

If you need a total byte limit across the entire request, configure it at the reverse proxy/API gateway and/or add an application-level byte counter. Do not rely on Content-Length, because requests may omit that header or use chunked transfer encoding.

Nor should you infer total request capacity solely from max-disk-usage-per-part. Per-part limits are not a total quota.

## 5. Resource Estimation Model

Limits must be evaluated alongside concurrency. A simple estimation formula:

~~~text
Temporary memory
≈ concurrent requests
  × non-file parts retained in memory
  × max-in-memory-size
  + headers and overhead

Temporary disk
≈ concurrent requests
  × file parts per request
  × max-disk-usage-per-part
  + filesystem overhead
~~~

Example:

- 40 concurrent upload requests.
- Each request has 3 non-file parts that can stay in memory.
- max-in-memory-size is 64KB.

A rough estimate for non-file data is 40 × 3 × 64KB = 7.5MB. Actual numbers also depend on parsing timing, buffers, objects, and overhead.

If each request has 2 file parts of up to 20MB each, 40 concurrent requests could require up to 40 × 2 × 20MB = 1.6GB of temporary disk space if all hit the limit simultaneously. Thus, per-part limits alone are insufficient; you also need volume quotas and concurrency limits.

Beyond memory/disk, account for file descriptors, multipart parsing CPU, bandwidth, connection hold duration, uploads queued for antivirus/object storage, and volume IOPS.

## 6. Managing Temporary Files and Part Lifecycle

Part represents one piece of a multipart request. Useful APIs:

| API | Meaning |
| --- | --- |
| Part.content() | Flux<DataBuffer> containing the part's content |
| Part.headers() | Part headers |
| Part.name() | Multipart field name |
| Part.delete() | Mono<Void> deleting underlying storage once finished |
| FilePart.filename() | Filename sent by client |
| FilePart.transferTo(Path) | Copies the file part content to a destination path |

Part.delete() returns a Publisher; you must subscribe to that Publisher by composing it into the pipeline. Simply calling part.delete() and ignoring the Mono<Void> will not perform cleanup.

### 6.1. Using usingWhen to Clean Up Across Complete, Error, and Cancel

~~~java
Mono<UploadReceipt> saveFile(FilePart file, Path destination) {
    String id = UUID.randomUUID().toString();
    String originalName = Objects.toString(file.filename(), "");

    return Mono.usingWhen(
            Mono.just(file),
            part -> part.transferTo(destination)
                    .thenReturn(new UploadReceipt(id, originalName)),
            part -> part.delete(),
            (part, error) -> part.delete(),
            part -> part.delete()
    );
}
~~~

Mono.usingWhen attaches asynchronous cleanup to all three termination paths: completion, error, and cancellation. FilePart.transferTo is reactive; never call block() inside a controller.

This snippet assumes the file part has been decoded and the application owns the Part lifecycle within this scope. If another component still needs the Part, coordinate shared ownership and cleanup so storage is not deleted prematurely.

### 6.2. Do Not Store Part or FilePart in Shared Fields

A Part belongs to a single request. Never store a request's FilePart, DataBuffer, or temporary path in a singleton field or global cache. Concurrent requests could cross-contaminate resources, retain files longer than needed, or delete a file while another consumer is still reading it.

If asynchronous processing is required after the request finishes, move the content into application-managed storage and pass an ID or safe internal path to the downstream task.

### 6.3. Do Not Use Client Filenames as Paths

FilePart.filename() is client-supplied data. Do not join this value directly onto the upload directory:

~~~java
// Unsafe:
Path destination = uploadDir.resolve(file.filename());
~~~

Clients can send names with directory separators, ".." segments, or unusual strings. Generate a server-controlled storage name instead:

~~~java
String storageName = UUID.randomUUID() + ".upload";
Path destination = uploadDir.resolve(storageName).normalize();
~~~

Store the original name as metadata if business requirements call for it, but never use it as a filesystem path. Also verify actual content, MIME type, extension, access permissions, and storage policy.

## 7. Streaming with PartEvent and Per-Part Limits

PartEventHttpMessageReader supports streaming multipart parsing. In Spring Framework 6.1 and later, the reader offers these limits:

| API | Meaning | Default |
| --- | --- | --- |
| setMaxInMemorySize(int) | Memory limit for form fields | 256KB |
| setMaxHeadersSize(int) | Header limit per part | 10KB |
| setMaxParts(int) | Limit on part count in a request | -1, unlimited |
| setMaxPartSize(long) | Size limit per part | -1, unlimited |

With PartEvent streaming:

- File content is emitted as events/chunks for the application to process.
- max-in-memory-size applies to form fields.
- max-part-size limits the size of each part, including file parts.
- file-storage-directory and max-disk-usage-per-part are not used in DefaultPartHttpMessageReader's spooling mechanism.

Spring Boot 3.5 provides common properties for multipart readers, but ReactiveMultipartProperties does not include a max-part-size property. If you use PartEvent and need per-file-part limits, configure PartEventHttpMessageReader explicitly.

Example of registering a custom reader:

~~~java
@Configuration
class StreamingMultipartLimits implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(ServerCodecConfigurer configurer) {
        PartEventHttpMessageReader reader = new PartEventHttpMessageReader();
        reader.setMaxInMemorySize(64 * 1024);
        reader.setMaxHeadersSize(10 * 1024);
        reader.setMaxParts(5);
        reader.setMaxPartSize(20L * 1024 * 1024);

        configurer.customCodecs().register(reader);
    }
}
~~~

This configuration is for endpoints using Flux<PartEvent>. When registering a custom reader, verify codec precedence order and test the real endpoint to confirm the bounded reader is actually used. These values must align with gateway limits and your application's upload policy.

### 7.1. Why Does PartEvent Need Backpressure?

A large file can be split across many events. If the application collects all events into a List or byte[] before processing, streaming benefits disappear and heap usage can grow proportionally to file size.

Use sequential operators like concatMap when writing each part or chunk. Never call nested subscribe(); return the Publisher so backpressure, errors, and cancellation flow through the pipeline.

If the application rejects a part midway, it must consume, relay, or release the remaining content per contract. Never abandon DataBuffers remaining in the event window.

## 8. Runnable Java 17+ Example: File Upload with WebFlux Limits

This example uses Spring Boot 3.5.16, Java 17+, and WebFlux. The reader uses multipart settings in application.yml; the controller accepts FilePart, saves the file under a server-generated name, and cleans up the Part after transfer.

### 8.1. Project Structure

~~~text
webflux-upload-limits/
├── pom.xml
└── src/
    ├── main/java/example/upload/
    │   ├── DemoApplication.java
    │   └── UploadController.java
    ├── main/resources/
    │   └── application.yml
    └── test/java/example/upload/
        └── UploadControllerTest.java
~~~

### 8.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>webflux-upload-limits</artifactId>
    <version>1.0.0</version>

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

### 8.3. application.yml

~~~yaml
spring:
  webflux:
    multipart:
      max-in-memory-size: 64KB
      max-disk-usage-per-part: 20MB
      max-parts: 5
      max-headers-size: 10KB
      headers-charset: UTF-8
      file-storage-directory: ./var/tmp/demo-multipart-tmp
~~~

### 8.4. DemoApplication.java

~~~java
package example.upload;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 8.5. UploadController.java

~~~java
package example.upload;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Objects;
import java.util.UUID;

import org.springframework.http.MediaType;
import org.springframework.http.codec.multipart.FilePart;
import org.springframework.http.codec.multipart.Part;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class UploadController {

    private final Path uploadDir;

    public UploadController() {
        this.uploadDir = Path.of("./var/tmp/demo-uploads")
                .toAbsolutePath()
                .normalize();

        try {
            Files.createDirectories(this.uploadDir);
        } catch (IOException error) {
            throw new UncheckedIOException(error);
        }
    }

    @PostMapping(
            path = "/uploads",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<UploadReceipt> upload(@RequestPart("file") FilePart file) {
        String id = UUID.randomUUID().toString();
        String originalFilename = Objects.toString(file.filename(), "");
        Path destination = uploadDir.resolve(id + ".upload").normalize();

        return Mono.usingWhen(
                Mono.just(file),
                part -> part.transferTo(destination)
                        .thenReturn(new UploadReceipt(id, originalFilename)),
                Part::delete,
                (part, error) -> part.delete(),
                Part::delete
        );
    }

    public record UploadReceipt(String id, String originalFilename) {
    }
}
~~~

Key points:

- The controller accepts FilePart instead of MultipartFile.
- FilePart.transferTo returns Mono<Void>; it does not block the request thread.
- The stored filename is a server-generated UUID; the client-sent name is kept only as metadata.
- Mono.usingWhen calls Part.delete on completion, error, or cancellation.
- The final upload directory is separated from the reader's temporary multipart directory.

### 8.6. UploadControllerTest.java

~~~java
package example.upload;

import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.MediaType;
import org.springframework.http.client.MultipartBodyBuilder;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.BodyInserters;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class UploadControllerTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void acceptsSmallFileAndReturnsServerGeneratedId() {
        MultipartBodyBuilder multipart = new MultipartBodyBuilder();

        multipart.part(
                "file",
                new ByteArrayResource("hello".getBytes(StandardCharsets.UTF_8)) {
                    @Override
                    public String getFilename() {
                        return "hello.txt";
                    }
                }
        );

        webTestClient.post()
                .uri("/uploads")
                .contentType(MediaType.MULTIPART_FORM_DATA)
                .body(BodyInserters.fromMultipartData(multipart.build()))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.id").isNotEmpty()
                .jsonPath("$.originalFilename").isEqualTo("hello.txt");
    }
}
~~~

The test constructs a multipart request with a small file, verifying the endpoint accepts the file and returns a server-generated ID. The 64KB, 20MB, 5 parts, and 10KB header limits are configured on the reader; add boundary tests matching your application's policy.

### 8.7. Running and Sending a Request

Run the application:

~~~bash
mvn spring-boot:run
~~~

Create a hello.txt file containing hello, then send:

~~~bash
curl -i -F "file=@hello.txt" http://localhost:8080/uploads
~~~

Illustrative response:

~~~json
{
  "id": "e2c7c6e0-8e39-4c8d-8d3d-5a2d5b5f4d13",
  "originalFilename": "hello.txt"
}
~~~

The ID in the output is randomly generated on each request; it is not fixed across runs.

Run the integration test:

~~~bash
mvn test
~~~

## 9. Handling Limit Errors and HTTP Statuses

When a limit is exceeded, the reader may emit a parse/codec error such as DataBufferLimitException or a corresponding multipart exception. Never assume every error type is automatically mapped to the same HTTP status across all versions and configurations.

An upload API should generally have a clear error contract:

| Case | Typically appropriate status |
| --- | --- |
| Invalid request or multipart format | 400 Bad Request |
| File/part exceeds limit | 413 Payload Too Large |
| Unsupported media type | 415 Unsupported Media Type |
| Missing required part | 400 Bad Request |
| Temporary storage error or volume full | 5xx depending on cause |

In production, map identified limit exceptions to 413 in the application's exception handling layer. Do not turn every IOException or parser error into 413; disk full, permission denied, and system errors need separate observability and handling.

Never return stack traces, temporary file paths, or internal filesystem information to clients.

## 10. Total Request Limits and Concurrency

Per-part limits do not bound the total request. For example, a request with 5 file parts of 20MB each can still use up to 100MB of temporary storage if every part hits the threshold.

An upload system should have layered limits:

1. **Edge proxy/API gateway:** total request bytes, upload duration, transfer rate, and connection limits.
2. **Multipart reader:** memory, disk per part, part count, and header size.
3. **Application:** total business bytes, file types, file count per user/tenant, and storage quotas.
4. **Storage:** volume quotas, free space, retention policies, and cleanup.
5. **Concurrency:** active uploads in flight, especially when antivirus or image processing is needed.

Content-Length can only be used for early rejection. Real limits at the proxy or a stream byte counter are still required because requests may omit length or use chunked transfer.

If the application counts PartEvent bytes itself, count total bytes across all events and stop the stream when the limit is exceeded. When stopping, consume or release remaining buffers per contract to avoid memory leaks.

## 11. Protecting Temporary Resources

### 11.1. Choosing a Dedicated Temporary Directory

Do not use a public/static directory to store temporary parts. The temporary directory should have least-privilege permissions, quotas, monitoring, and a post-crash orphan cleanup policy. If large uploads could impact logs or databases, consider a separate volume.

### 11.2. Lifecycle-Aligned Cleanup

- For parsed Part/FilePart objects, call Part.delete when the application no longer needs the part's storage.
- For PartEvent streaming, the application manages chunks and destination files; close storage resources on complete/error/cancel.
- Never hold FilePart in a singleton or long-lived cache.
- Avoid creating destination files before validating the request when avoidable.
- If writing the destination file fails midway, delete the partial file per application policy.

### 11.3. Concurrency Limits and Monitoring

Even when each upload is capped at 20MB, hundreds of concurrent uploads can consume gigabytes. Apply concurrency limits per user/tenant, endpoint, or worker pool.

Track in-flight multipart requests, part sizes, rejected requests, temporary directory capacity and inodes, parse/transfer/scan durations, remaining temp files, permission/disk-full errors, and cancellations.

Never use filename, user-provided path, or raw form values as metric labels because the data can be sensitive and has very high cardinality.

## 12. File Content Inspection and Path Safety

Size limits do not prove a file is safe. After receiving a file:

- Do not trust client-sent extensions or Content-Type.
- Check magic bytes/signatures and actual format.
- Enforce a business format allowlist.
- Scan for malware if system policy requires it.
- Limit archive extraction and check for zip bombs.
- Never use client filenames as paths.
- Never allow uploaded files to overwrite system files or another user's files.
- Publish the file only after validation and scanning finish.
- When files are retrieved later, use random IDs and authorization checks.

If storing the original name, normalize and limit its length; avoid writing that name to logs unnecessarily.

## 13. Common Configuration Mistakes

| Mistake | Consequence | How to fix |
| --- | --- | --- |
| Setting only max-in-memory-size | Large files can still write huge amounts of data to disk | Set max-disk-usage-per-part |
| Setting max-disk-usage-per-part without max-parts | One request can send many files | Set max-parts |
| Assuming max-disk-usage-per-part is the total request cap | Combined size of multiple files exceeds expectations | Add a total request cap and storage quotas |
| Setting max-in-memory-size=-1 | Large files are retained in memory | Use a finite threshold and disk cap |
| Leaving max-parts=-1 | Unlimited fields/files | Pick a max part count matching the API |
| Leaving max-disk-usage-per-part=-1 | File parts have no reader-level disk cap | Set an appropriate threshold |
| Setting max-headers-size=-1 | Part headers are unbounded by the reader | Set a finite limit |
| Using spring.servlet.multipart in WebFlux | Properties do not apply to reactive readers | Use spring.webflux.multipart |
| Trusting Content-Length | Misses chunked requests or requests omitting the header | Enforce limits at the proxy and count actual bytes |
| Using file.filename() as path | Risks path traversal and overwrites | Generate server-controlled filenames |
| Omitting Part.delete() | Temporary files can linger longer than necessary | Clean up via usingWhen or equivalent lifecycle hooks |
| Switching to PartEvent without handling chunks | Can leak buffers or retain resources | Consume, relay, or release all content |
| Calling block() in upload controller | Blocks the event loop and reduces throughput | Use FilePart.transferTo and reactive storage APIs |
| Not limiting concurrent uploads | Many small requests can still fill disk | Add concurrency limits and quotas |

## 14. Production Upload Readiness Checklist

- [ ] Memory limits are set for non-file parts.
- [ ] File parts have a spill-to-disk threshold and finite disk cap.
- [ ] Part count and per-part header size are limited.
- [ ] Total request limit is enforced at the proxy/gateway or byte-counting layer.
- [ ] Concurrent uploads are limited according to capacity and quotas.
- [ ] Temporary directory sits outside static/public paths and has quotas.
- [ ] Part/FilePart is cleaned up on complete, error, and cancel.
- [ ] Final stored files use server-generated names.
- [ ] Actual format validation and scanning follow policy.
- [ ] Tests cover near-limit files, over-limit files, many parts, large headers, and chunked requests.
- [ ] Disk space, inodes, upload duration, and cleanup errors are monitored.
- [ ] Policies exist to delete partial files and orphaned temporary files.

## 15. Takeaways

- DefaultPartHttpMessageReader keeps small parts in memory and writes large file parts to a temporary directory.
- max-in-memory-size is the limit for non-file parts and the spill-to-disk threshold for file parts.
- max-disk-usage-per-part limits each individual file part, not the total request.
- max-parts counts all parts, including fields and files; max-headers-size limits headers per part.
- Spring Boot 3.5 defaults to 256KB memory, 10KB headers, -1 unlimited disk per part, and -1 unlimited part count.
- file-storage-directory is a temporary staging area; the final business upload directory must be managed separately.
- Part.delete is reactive cleanup; compose it into the pipeline to handle complete/error/cancel.
- FilePart.transferTo is the reactive way to move files; client-sent filenames must never be used as paths.
- PartEvent fits streaming; setMaxPartSize limits each part while the application handles chunks and backpressure.
- There is no spring.webflux.multipart.max-request-size equivalent to the Servlet property; total request limits must be enforced at the gateway or application layer.
- Choose limits based on concurrency, memory, disk, IOPS, and quotas, not just a single file's size.

**Official Documentation:**
- [Spring Boot 3.5 — Common Application Properties: spring.webflux.multipart](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html)
- [Spring Boot 3.5 — ReactiveMultipartProperties](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/web/reactive/ReactiveMultipartProperties.html)
- [Spring Framework 6.2 — Reactive Core: Multipart parsing and limits](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html)
- [Spring Framework — Multipart Content and PartEvent](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/multipart-forms.html)
- [Spring Framework 6.2 Javadoc — DefaultPartHttpMessageReader](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/http/codec/multipart/DefaultPartHttpMessageReader.html)
- [Spring Framework 6.2 Javadoc — PartEventHttpMessageReader](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/http/codec/multipart/PartEventHttpMessageReader.html)
- [Spring Framework 6.2 Javadoc — Part and FilePart](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/http/codec/multipart/Part.html)
- [Spring Framework 6.2 Javadoc — FilePart](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/http/codec/multipart/FilePart.html)
