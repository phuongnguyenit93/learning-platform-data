# Writing Files with transferTo and Managing Destination Paths in Spring WebFlux

## 1. Goal

In Spring WebFlux, file uploads commonly arrive as `multipart/form-data` requests. The server must read the part, validate the data, and write it to a storage location controlled by the application. Spring provides `FilePart` to represent a file in a multipart request. Its `transferTo(Path)` method copies the file content to a destination on the filesystem and returns `Mono<Void>` signaling when the operation finishes.

**The destination path must be decided by the server.** The original filename, Content-Type, and multipart metadata are all sent by the client. Using the filename directly to construct a path can lead to path traversal, overwriting other files, or writing data to unintended locations.

This lesson focuses on:

- Reading files using `@RequestPart FilePart`.
- Writing with `FilePart.transferTo(Path)` and composing completion inside a reactive pipeline.
- Building safe destination paths decoupled from client filenames.
- Managing the storage root, staging files, move/commit, and cleanup on error or cancellation.
- Distinguishing the in-RAM buffering threshold from actual upload size limits.
- Checking file format, access permissions, quotas, and malicious content.
- Handling large uploads with `Flux<PartEvent>` when streaming is needed.
- Testing with `WebTestClient` or service tests.

Examples use Java 17+, Spring Boot 3.x/Spring Framework 6.2+, and Reactor. The `FilePart.transferTo(Path)` API has been available since Spring Framework 5.1.

## 2. Multipart Requests and FilePart

A multipart request can contain multiple parts. Each part has its own name, headers, and content:

```http
POST /api/uploads HTTP/1.1
Host: localhost:8080
Content-Type: multipart/form-data; boundary=----upload-boundary

------upload-boundary
Content-Disposition: form-data; name="description"

Quarterly report
------upload-boundary
Content-Disposition: form-data; name="file"; filename="report.pdf"
Content-Type: application/pdf

%PDF-1.7
... file bytes ...
------upload-boundary--
```

Common types in WebFlux:

| Type | Meaning |
| --- | --- |
| `Part` | A general part in a multipart request |
| `FilePart` | A part representing an uploaded file |
| `FormFieldPart` | A part representing a text form field |
| `PartEvent` | An event for a part in a streaming multipart flow |
| `DataBuffer` | A byte buffer used in Spring's I/O pipeline |

A controller can accept a specific file:

```java
@PostMapping(
        value = "/api/uploads",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public Mono<String> upload(
        @RequestPart("file") FilePart file) {

    return file.transferTo(Path.of("/srv/app/uploads/report.pdf"))
            .thenReturn("uploaded");
}
```

This is only an **API illustration snippet**. A fixed path is unsuitable for concurrent requests because they can overwrite each other's files. Later sections replace it with a unique server-generated path per upload.

You can also accept both metadata and a file:

```java
@PostMapping(
        value = "/api/documents",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public Mono<DocumentResponse> upload(
        @RequestPart("metadata") Mono<DocumentMetadata> metadata,
        @RequestPart("file") FilePart file) {

    return metadata.flatMap(data ->
            documentService.store(data, file));
}
```

Spring reads the metadata part and deserializes it into a Java type; the file is represented as a FilePart. If metadata requires Bean Validation, you can use `@Valid @RequestPart("metadata") Mono<DocumentMetadata>` and handle validation errors in the reactive pipeline or an appropriate advice.

## 3. How Does FilePart.transferTo(Path) Work?

Main signature:

```java
Mono<Void> transferTo(Path destination)
```

This method copies the part's file content to the destination file and returns a Mono that completes when the transfer finishes. It does not return a byte array or file content; the result is a completion signal.

Key points to remember:

1. The destination is a **file path**, not merely a directory. The server determines the stored filename.
2. If the destination file already exists, its content is truncated before writing. Never pass a path that could point to an important file or another request's file.
3. The parent directory must exist and the application must have write permission.
4. The Mono represents the operation; compose it using `then`, `map`, or `flatMap` so subsequent steps only run after the transfer completes.
5. Do not call `block()` in controllers/services to wait for the file to be written.
6. Do not call `subscribe()` inside a controller to run the upload detached from the HTTP request.

Composition example:

```java
return file.transferTo(destination)
        .then(Mono.just("stored"));
```

Mono.just("stored") is emitted only after the transfer completes. If the transfer errors, the error signal propagates downstream and the then stage does not run.

Do not write:

```java
file.transferTo(destination).subscribe();
return Mono.just("stored");
```

This creates a separate subscription. The controller may return a response before the file finishes writing; write errors are no longer tied to the response, client cancellation is not properly linked to the task, and cleanup becomes difficult to manage.

### 3.1. transferTo Does Not Make Client Filenames Safe

`FilePart.filename()` returns the original filename from the client's filesystem. Spring's documentation warns that this value is client-supplied and may contain directory segments, `..`, or exploitable characters. Never use it directly as a path.

Examples of possible filenames:

- `report.pdf`
- `../../application.yml`
- `../private/secret.txt`
- An absolute path according to the client's operating system.
- A name containing control characters, path separators, or excessive length.

Do not assume browsers always send a clean basename. The client could be a script or HTTP tool crafting custom multipart headers.

**Recommendation:** generate a new storage name using a UUID or server-managed ID. If business logic needs to keep the original name for display, store it as sanitized metadata; never use that metadata to decide where the file is written.

## 4. Designing the Storage Directory

Before writing code, decide where files will be stored:

- Place it outside the webroot/static resource directory so the web server does not automatically expose or execute files.
- Use a directory writable only by the application's service account; restrict read permissions as needed as well.
- For persistent storage, choose a persistent volume/disk; do not use the OS temporary directory as the final storage location.
- Separate staging and accepted directories if there is an inspection or antivirus scanning step.
- Monitor disk usage, file counts, temporary file age, and per-user/tenant quotas.
- Maintain backup, retention, and deletion policies when business data is deleted.

Example configuration:

```properties
app.upload.storage-root=/var/lib/myapp/uploads
```

In a local environment you can use a project-specific directory. Production should use an environment-configured path with clear filesystem permissions located outside public directories.

Do not store uploaded files in `src/main/resources/static`, directories holding configuration/secrets, executable directories, or client-supplied paths. If the application runs multiple instances, one instance's local filesystem may not be shared with others. In that case, use a shared volume or object storage; the database stores metadata and the storage key.

## 5. Safely Managing Destination Paths

### 5.1. Do Not Concatenate Filenames

Dangerous pattern:

```java
Path destination = uploadRoot.resolve(file.filename());
return file.transferTo(destination);
```

If filename contains traversal sequences or an absolute path, the destination can escape uploadRoot. Two requests with the same name can also overwrite each other's files.

Do not rely solely on stripping `../` with replace or regex. Path traversal has many representations depending on OS, URL decoding, separators, and filesystem.

### 5.2. Generating Server-Side Names

Simple approach:

```java
String id = UUID.randomUUID().toString();
Path destination = uploadRoot.resolve(id + ".bin");
```

The client does not control the ID. You can store the mapping from ID → sanitized original name in the database if display or download requires it.

If only one file type is allowed, you can use a fixed server-chosen extension after verifying content, such as `.pdf`. Do not take the extension straight from the client name and trust that the file is truly a PDF.

### 5.3. Normalizing and Validating Paths

When resolving a relative path is necessary, you can use:

```java
Path root = uploadRoot.toAbsolutePath().normalize();
Path candidate = root.resolve(relativeName).normalize();

if (!candidate.startsWith(root)) {
    throw new IllegalArgumentException("Invalid destination path");
}
```

`Path.startsWith(Path)` compares by path components, which is better than string comparison with `String.startsWith`. `normalize()` removes `.` and `..` segments lexically.

However, normalize alone does not solve every symlink issue. A subdirectory could be a symbolic link pointing outside root. `toRealPath()` resolves the actual path of existing components, but if another user has permission to modify directories between check and write, a race condition risk remains.

The easiest approach to control for uploads is **not accepting relative paths or filenames from the client**. Use a dedicated root, strict filesystem permissions, and server-generated paths. If directories are organized by tenant, derive the tenant ID from the authenticated principal, never arbitrarily from a form field.

### 5.4. Giving Each Upload Its Own Staging Directory

A solid pattern is creating a unique temporary directory under the storage root:

```java
Path uploadDirectory = Files.createTempDirectory(realRoot, "upload-");
Path staging = uploadDirectory.resolve("payload.part");
Path destination = uploadDirectory.resolve("payload.pdf");
```

Each invocation creates a new directory. FilePart writes only to `payload.part`. After transfer and validation succeed, the server moves the file to `payload.pdf` in the same directory.

Benefits:

- Concurrent requests do not share a staging path.
- Does not rely on client filenames.
- The entire directory can be cleaned up if the upload fails.
- The file can be promoted only after validation.
- Destination is on the same filesystem as staging, enabling atomic move where the filesystem supports it.

The storage root must be a dedicated directory where only the application or trusted processes have permission to create/delete contents. Creating paths in public directories or locations writable by untrusted users undermines these checks.

## 6. transferTo Overwrites the Destination File: How to Handle It?

Per FilePart's Javadoc, if the destination already exists, transferTo truncates that file before writing. This behavior must be actively accounted for.

| Strategy | Approach | When appropriate |
| --- | --- | --- |
| Unique name | Generate a new ID per upload | Recommended default |
| Controlled overwrite | Check permissions and policy then replace a specific resource | APIs for updating an existing file |
| Stage then promote | Write temp file, validate, then move to final name | Files requiring validation or hiding incomplete files |

Never use a client-sent filename as the mechanism to select a file to overwrite. If an API replaces a file, use a server-managed resource ID, verify the user has permission to modify that resource, and check version/concurrency if needed.

### 6.1. Writing to Staging First

Processing flow:

1. Create a dedicated upload directory.
2. Create a server-named staging file.
3. Call `file.transferTo(stagingPath)`.
4. After transfer finishes, validate size and format.
5. If valid, move staging to the final destination.
6. If invalid or an error occurs, delete staging and the temporary directory.
7. Only publish the metadata/file ID after the file has been promoted.

Do not return a file ID in a "saved" state before transfer completes. If a multi-step workflow is needed, persist statuses like `UPLOADING`, `SCANNING`, `AVAILABLE`, or `REJECTED` in the database.

### 6.2. Atomic Move

When staging and destination reside on the same filesystem, you can attempt:

```java
Files.move(
        stagingPath,
        destinationPath,
        StandardCopyOption.ATOMIC_MOVE);
```

If the filesystem does not support atomic move, Java may throw `AtomicMoveNotSupportedException`. The application can fall back to `Files.move(staging, destination)` if policy permits.

An atomic move prevents readers from seeing a partially written file at the final path. However, semantics when the destination already exists can be provider-dependent when using ATOMIC_MOVE. Create the destination inside a fresh dedicated directory, ensuring it does not already exist and no untrusted process writes to that directory.

Do not use `REPLACE_EXISTING` unless replacing the file is explicitly allowed. If falling back to a non-atomic move, do not advertise it as an atomic commit.

## 7. Complete Example: Uploading PDF with a Server-Side Name

This example accepts a PDF file, writes it into a unique staging directory, checks size and a minimal PDF signature, then promotes it to a fixed server-chosen name.

**Limitation of the PDF check:** checking the `%PDF-` prefix is only a preliminary check. It does not prove a PDF document is safe or completely valid. Production requires a proper parser/validator, antivirus, or sandbox/CDR if security demands it.

### 7.1. Configuration

File `src/main/resources/application.properties`:

```properties
app.upload.storage-root=/var/lib/myapp/uploads
```

This directory must sit outside the webroot, persist across restarts, and grant write permissions only to the application account as needed.

### 7.2. Multipart Limits

The multipart parser has its own limits. You can configure the reader:

```java
package demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.http.codec.ServerCodecConfigurer;
import org.springframework.http.codec.multipart.DefaultPartHttpMessageReader;
import org.springframework.http.codec.multipart.MultipartHttpMessageReader;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration(proxyBeanMethods = false)
public class MultipartUploadConfiguration implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {

        DefaultPartHttpMessageReader partReader =
                new DefaultPartHttpMessageReader();

        partReader.setMaxInMemorySize(256 * 1024);
        partReader.setMaxDiskUsagePerPart(12L * 1024 * 1024);
        partReader.setMaxParts(5);
        partReader.setMaxHeadersSize(10 * 1024);

        configurer.defaultCodecs().multipartReader(
                new MultipartHttpMessageReader(partReader));
    }
}
```

Explanation:

- `maxInMemorySize(256 KiB)` is the threshold for keeping a part in RAM. File parts exceeding the threshold are written to the temp directory; this is **not** the maximum upload limit.
- `maxDiskUsagePerPart(12 MiB)` limits disk space per file part in the reader.
- `maxParts(5)` limits the total number of parts in a multipart request.
- `maxHeadersSize(10 KiB)` limits the headers of each part.

By default, DefaultPartHttpMessageReader's `maxInMemorySize` is 256 KiB; `maxDiskUsagePerPart` and `maxParts` are unlimited by default. When increasing memory/disk limits, account for concurrent request counts and temp disk capacity.

In this example, the service only accepts PDFs up to 10 MiB. The reader allows up to 12 MiB per part so the service can return a clear business error at the 10 MiB threshold; requests larger than 12 MiB are blocked at the multipart parser layer. The gateway/reverse proxy still needs a total request body limit, because multipart requests can contain multiple parts and overhead.

When using Spring Boot, `WebFluxConfigurer` normally does not need `@EnableWebFlux`; omit that annotation to preserve Boot's auto-configuration customizations.

### 7.3. UploadService

File `src/main/java/demo/UploadService.java`:

```java
package demo;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.Arrays;
import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.core.env.Environment;
import org.springframework.http.HttpStatus;
import org.springframework.http.codec.multipart.FilePart;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@Service
public class UploadService {

    private static final long MAX_PDF_BYTES = 10L * 1024 * 1024;

    private static final byte[] PDF_MAGIC =
            "%PDF-".getBytes(StandardCharsets.US_ASCII);

    private final Path storageRoot;

    public UploadService(Environment environment) {
        this(Path.of(environment.getRequiredProperty(
                "app.upload.storage-root")));
    }

    UploadService(Path storageRoot) {
        this.storageRoot = storageRoot.toAbsolutePath().normalize();
    }

    public Mono<StoredUpload> store(FilePart file) {
        return Mono.usingWhen(
                Mono.fromCallable(this::createPaths)
                        .subscribeOn(Schedulers.boundedElastic()),

                paths -> file.transferTo(paths.staging())
                        .then(Mono.fromCallable(
                                () -> validateAndPromote(paths))
                                .subscribeOn(Schedulers.boundedElastic())),

                paths -> Mono.empty(),

                (paths, error) -> cleanup(paths),

                this::cleanup
        );
    }

    private UploadPaths createPaths() throws IOException {
        Files.createDirectories(storageRoot);
        Path realRoot = storageRoot.toRealPath();

        Path directory = Files.createTempDirectory(
                realRoot, "upload-");

        Path staging = directory.resolve("payload.part");
        Path destination = directory.resolve("payload.pdf");

        try {
            Files.createFile(staging);
        } catch (IOException error) {
            Files.deleteIfExists(directory);
            throw error;
        }

        return new UploadPaths(
                directory,
                staging,
                destination,
                new AtomicBoolean(false));
    }

    private StoredUpload validateAndPromote(
            UploadPaths paths) throws IOException {

        long size = Files.size(paths.staging());

        if (size == 0 || size > MAX_PDF_BYTES) {
            throw new ResponseStatusException(
                    HttpStatus.PAYLOAD_TOO_LARGE,
                    "PDF must be between 1 byte and 10 MiB");
        }

        try (InputStream input =
                     Files.newInputStream(paths.staging())) {

            byte[] prefix = input.readNBytes(PDF_MAGIC.length);

            if (!Arrays.equals(prefix, PDF_MAGIC)) {
                throw new ResponseStatusException(
                        HttpStatus.UNSUPPORTED_MEDIA_TYPE,
                        "Only PDF content is accepted");
            }
        }

        try {
            Files.move(
                    paths.staging(),
                    paths.destination(),
                    StandardCopyOption.ATOMIC_MOVE);
        } catch (AtomicMoveNotSupportedException error) {
            Files.move(paths.staging(), paths.destination());
        }

        paths.committed().set(true);

        String id = paths.directory().getFileName().toString();
        return new StoredUpload(id, size);
    }

    private Mono<Void> cleanup(UploadPaths paths) {
        return Mono.fromCallable(() -> {
                    if (!paths.committed().get()) {
                        Files.deleteIfExists(paths.staging());
                        Files.deleteIfExists(paths.destination());
                        Files.deleteIfExists(paths.directory());
                    }
                    return Boolean.TRUE;
                })
                .subscribeOn(Schedulers.boundedElastic())
                .then();
    }

    private record UploadPaths(
            Path directory,
            Path staging,
            Path destination,
            AtomicBoolean committed) {
    }

    public record StoredUpload(String id, long size) {
    }
}
```

Key points:

- The constructor receives the storage root from configuration, never a path from the request.
- `createPaths()` creates the root, resolves the real root via `toRealPath()`, and creates a dedicated directory via `createTempDirectory()`.
- FilePart writes only to the server-created `payload.part`.
- After transfer, the service reads size and signature in an operation scheduled on boundedElastic.
- When valid, staging is moved to `payload.pdf`.
- `AtomicBoolean committed` distinguishes promoted files from temporary files that need deletion.
- `Mono.usingWhen` invokes cleanup when the pipeline errors or is canceled.
- Synchronous filesystem operations like creating directories, reading signatures, moving, and deleting are isolated on `Schedulers.boundedElastic()`.

FilePart.transferTo returns a Mono and should be composed directly. Never wrap it in `Mono.fromCallable(() -> file.transferTo(...).block())`; that blocks and breaks the reactive lifecycle.

**About cleanup:** if the application is killed abruptly or the machine loses power, reactive callbacks cannot run. Production should have a periodic job cleaning uncommitted `upload-*` directories past their TTL, while keeping upload state in a database if recovery is needed.

### 7.4. Controller

File `src/main/java/demo/UploadController.java`:

```java
package demo;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.multipart.FilePart;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/uploads")
public class UploadController {

    private final UploadService uploadService;

    public UploadController(UploadService uploadService) {
        this.uploadService = uploadService;
    }

    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public Mono<ResponseEntity<UploadResponse>> upload(
            @RequestPart("file") FilePart file) {

        return uploadService.store(file)
                .map(saved -> ResponseEntity
                        .status(HttpStatus.CREATED)
                        .body(new UploadResponse(
                                saved.id(), saved.size())));
    }

    public record UploadResponse(String id, long size) {
    }
}
```

The controller does not build paths from filename, does not read the file into a byte array, and does not block. It delegates FilePart to the service, then constructs the response once the service emits StoredUpload.

The response body contains a server-generated ID and the file size. Do not echo the raw client filename back directly. If the original name is needed, store it as sanitized metadata and apply encoding when displaying it.

### 7.5. Calling the Endpoint with curl

Create a test PDF `sample.pdf` and run:

```bash
curl -i -X POST http://localhost:8080/api/uploads   -F "file=@sample.pdf;type=application/pdf"
```

A successful response has status 201 and JSON similar to:

```json
{
  "id": "upload-<generated-id>",
  "size": 842
}
```

The ID and size values depend on the actual upload. The server stores the file inside an application-managed directory under the internal name `payload.pdf`. The client does not decide the final path or filename.

Sending a non-PDF file returns 415 Unsupported Media Type according to the example. Files exceeding the 10 MiB threshold are rejected by the service; files exceeding the 12 MiB multipart parser limit are rejected before the service completes. The gateway/server also needs a total request limit.

## 8. Testing the Service and Destination Paths

Tests should verify:

- Valid files are written to a server-generated directory.
- Two uploads produce different IDs/directories.
- Files with invalid signatures are rejected and staging is deleted.
- Oversized files are rejected.
- Transfer errors leave no staging files behind.
- Cancellation during upload performs proper cleanup.
- No client filename/path is used as the destination.
- Storage root is not inside the webroot and cannot be accessed directly.

Unit test example for the service, using Mockito to stub FilePart.transferTo:

File `src/test/java/demo/UploadServiceTest.java`:

```java
package demo;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.concurrent.atomic.AtomicReference;
import java.util.stream.Stream;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.http.codec.multipart.FilePart;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class UploadServiceTest {

    @TempDir
    Path tempDir;

    @Test
    void storesPdfInGeneratedDirectory() throws Exception {
        Path source = Files.writeString(
                tempDir.resolve("source.pdf"),
                "%PDF-1.7
sample content");

        Path storageRoot = tempDir.resolve("uploads");
        FilePart filePart = mock(FilePart.class);

        when(filePart.transferTo(any(Path.class)))
                .thenAnswer(invocation -> {
                    Path destination = invocation.getArgument(0);

                    return Mono.fromCallable(() ->
                                    Files.copy(
                                            source,
                                            destination,
                                            StandardCopyOption.REPLACE_EXISTING))
                            .subscribeOn(Schedulers.boundedElastic())
                            .then();
                });

        UploadService service = new UploadService(storageRoot);
        AtomicReference<UploadService.StoredUpload> saved =
                new AtomicReference<>();

        StepVerifier.create(service.store(filePart))
                .assertNext(saved::set)
                .verifyComplete();

        assertTrue(saved.get().size() > 0);

        Path storedFile = storageRoot
                .resolve(saved.get().id())
                .resolve("payload.pdf");

        assertEquals(
                "%PDF-1.7
sample content",
                Files.readString(storedFile));
    }

    @Test
    void rejectsInvalidSignatureAndCleansStaging() throws Exception {
        Path source = Files.writeString(
                tempDir.resolve("invalid.pdf"),
                "not a PDF");

        Path storageRoot = tempDir.resolve("uploads");
        FilePart filePart = mock(FilePart.class);

        when(filePart.transferTo(any(Path.class)))
                .thenAnswer(invocation -> {
                    Path destination = invocation.getArgument(0);

                    return Mono.fromCallable(() ->
                                    Files.copy(
                                            source,
                                            destination,
                                            StandardCopyOption.REPLACE_EXISTING))
                            .subscribeOn(Schedulers.boundedElastic())
                            .then();
                });

        UploadService service = new UploadService(storageRoot);

        StepVerifier.create(service.store(filePart))
                .expectError(ResponseStatusException.class)
                .verify();

        try (Stream<Path> entries = Files.list(storageRoot)) {
            assertEquals(0, entries.count());
        }
    }
}
```

The tests focus on the service and path management. Mockito stubs transferTo by copying a local file into the staging path passed by the service. These tests do not replace multipart parser integration tests; the real endpoint should also have WebTestClient tests covering `@RequestPart("file")` resolution, status responses, and request limits.

The tests require JUnit Jupiter, Mockito, reactor-test, and Spring WebFlux on the test classpath. `spring-boot-starter-test` in a Spring Boot project usually supplies the required test libraries; `reactor-test` may need to be declared explicitly if the project does not already include it.

## 9. Multipart Parser: RAM Threshold Is Not the Upload Limit

A common misconception is thinking `maxInMemorySize=256 KiB` means files larger than 256 KiB are rejected. With DefaultPartHttpMessageReader:

- Non-file parts exceeding the memory threshold may be rejected with DataBufferLimitException.
- File parts exceeding the threshold are written to a temporary directory on disk.
- `maxDiskUsagePerPart` sets the disk capacity limit per file part.
- `maxParts` limits the number of parts in a request.
- `fileStorageDirectory` changes the temporary directory used to store large parts.
- `setBlockingOperationScheduler(...)` can change the scheduler used for file/directory operations; boundedElastic is used by default.

Distinguishing the limits:

| Configuration/measure | Limit |
| --- | --- |
| maxInMemorySize | Number of bytes a part stays in RAM before a file part spills to disk |
| maxDiskUsagePerPart | Maximum disk usage per file part in the reader |
| maxParts | Total number of parts in one multipart request |
| Service MAX_FILE_SIZE | File size accepted by business logic after transfer |
| Reverse proxy/request limit | Total HTTP request size before the application processes it |
| User quota | Total storage or number of files a user/tenant may store |
| Concurrency/rate limit | Concurrent uploads and upload frequency |

Checking size after transfer determines whether the file is promoted, but **does not prevent disk from already being consumed while receiving the upload**. Limits at the parser, gateway, and quota levels are required to prevent resource exhaustion.

To change the multipart temp directory, configure `DefaultPartHttpMessageReader.setFileStorageDirectory(Path)`. The temp directory should reside on a monitored volume with restricted permissions and a cleanup policy.

## 10. Large File Uploads: When to Use PartEvent?

`FilePart` is convenient when you need a parser-identified file written to a path. For very large uploads or sequential per-part processing, WebFlux supports multipart streaming via:

```java
@RequestBody Flux<PartEvent>
```

Each part emits one or more PartEvents. Form fields typically emit a single FormPartEvent; large files may be split across multiple FilePartEvents and multiple DataBuffers. The final event of a part has `isLast() = true`.

Common processing structure:

```java
@PostMapping(
        value = "/api/stream-upload",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public Mono<Void> uploadStream(
        @RequestBody Flux<PartEvent> allPartEvents) {

    return allPartEvents
            .windowUntil(PartEvent::isLast)
            .concatMap(partEvents ->
                    partEvents.switchOnFirst((signal, samePart) -> {
                        if (!signal.hasValue()) {
                            return samePart.then();
                        }

                        PartEvent first = signal.get();

                        if (first instanceof FormPartEvent form) {
                            return saveField(form.name(), form.value())
                                    .then(samePart.then());
                        }

                        if (first instanceof FilePartEvent file) {
                            Flux<DataBuffer> content =
                                    samePart.map(PartEvent::content);

                            return streamToStorage(
                                    file.filename(), content);
                        }

                        return Mono.error(
                                new IllegalArgumentException(
                                        "Unsupported multipart part"));
                    }))
            .then();
}
```

This is **skeleton code**: `saveField(...)` and `streamToStorage(...)` are defined by the application. The stream-writing method must consume, relay, or release all received DataBuffers. Never ignore buffers of rejected parts; otherwise memory leaks can occur, especially on Netty with pooled DataBuffers.

| FilePart.transferTo | Flux<PartEvent> |
| --- | --- |
| Easy to use for a resolved file part | Processes each part/event as a stream |
| Parser manages multipart parts and can spool file parts to temp | Application controls consumption of each buffer |
| Calls transferTo to write the file to a path | Composes a sink writing DataBuffers or relaying to another service |
| Fits most standard form uploads | Fits large streaming, many parts, or relaying |
| Less buffer management code | Requires more careful buffer, backpressure, and cleanup handling |

If per-event multipart processing is not needed, prefer FilePart. Do not use PartEvent just because the endpoint uses WebFlux; the streaming API demands stricter buffer handling code.

## 11. DataBuffer Ownership and Cleanup

When using FilePart.transferTo, Spring manages reading/writing part content through the FilePart and DataBuffer implementations. Applications generally do not need to release individual buffers manually.

If you access `file.content()` or process PartEvents directly, you must understand ownership:

- A DataBuffer can wrap pooled memory and reference-counted buffers.
- Consumed buffers must be released at the right time.
- Buffers dropped by filters, errors, or cancellations also need cleanup.
- Do not release a buffer after transferring ownership to another writer/sink.
- Do not read a buffer after it has been released.
- When relaying a stream, ensure downstream consumes all buffers or cleans up on error/cancellation.

`Part.delete()` returns a Mono to remove the part's backing storage. This API is useful when the application actively manages a Part's lifecycle; call it only after the part's content is no longer needed. Never delete a part before transfer or before the consumer finishes.

With custom streaming code, test success, error, and cancellation paths. Testing only the happy path can miss leaks that happen when a client disconnects mid-upload.

## 12. Inspecting Files Before Publishing

Do not trust the following metadata:

- `FilePart.filename()`: name sent by the client.
- `file.headers().getContentType()`: MIME type declared by the client.
- Filename extension: can be spoofed or contain double extensions.
- Client-declared size in part headers: does not replace counting actual bytes.

Multi-layered validation process:

1. **Authentication/authorization:** does the user have permission to upload to this resource/tenant?
2. **Filename policy:** generate a new storage key; limit and sanitize the display name if stored.
3. **Size policy:** enforce limits at proxy, multipart reader, service, and quota.
4. **Extension allowlist:** accept only file types required by business logic.
5. **Content-Type quick check:** useful for client error reporting, but not proof.
6. **Magic bytes/signature:** check actual content against format; never rely on it alone.
7. **Parser validation:** open/parse with an appropriate library with bounded CPU/memory.
8. **Antivirus/sandbox/CDR:** apply according to risk level and file type.
9. **Storage policy:** outside webroot, non-executable uploads, least privilege.
10. **Download policy:** serve through an authorized endpoint using server-managed IDs.

The service example checking `%PDF-` is only illustrative. A signature check does not prove a file lacks malicious payloads; a PDF can still contain JavaScript, embedded files, or parser-exploiting structures. Data published to other users should be scanned/inspected before transitioning to AVAILABLE status.

If files are processed with ZIP, XML, image, or document parsers, bound resources for decompression/parsing separately. A small file can expand into a huge payload (zip bomb) or exhaust parser CPU/memory.

## 13. Preventing Path Traversal and Overwrites

### 13.1. Attack Example

Suppose the server uses:

```java
Path destination = storageRoot.resolve(file.filename());
file.transferTo(destination);
```

A client can send a filename containing `../` to attempt writing outside the upload directory. An absolute path can also cause resolve to ignore the root. On Windows, separators and drive letters behave differently from Linux.

Even when taking the basename, risks remain:

- The filename may collide with an existing file.
- The name may contain control characters or special characters.
- Unicode normalization can create visually identical names.
- Case-insensitive filesystems may treat names differing only in case as the same file.
- Symbolic links in subdirectories may point outside root.
- A user could upload a file with a name that has special meaning to the web server.

### 13.2. Defenses

- Generate IDs/filenames using UUIDs or random storage keys.
- Never allow clients to pass destination paths.
- Keep the storage root in server configuration, never from requests.
- Use a dedicated directory where untrusted users cannot write.
- Use path component checks if paths must be resolved.
- Disallow file execution in the upload directory.
- Store original metadata in a database separate from the physical path.
- For duplicate files or resource updates, use business IDs and clear policies.
- Never expose files by concatenating filenames into filesystem URLs.

### 13.3. Path Checks Do Not Replace Filesystem Permissions

`normalize()` and `startsWith(root)` help prevent lexical path traversal. However, if a directory contains a symlink controlled by another user or a race occurs between check and write, escaping root is still possible.

Ensure root and subdirectories are managed only by trusted processes. In environments where multiple processes/users write, design proper permissions and atomic creation; do not rely on a single string check.

## 14. Handling Upload Errors and Statuses

| Case | Typical status | Action |
| --- | --- | --- |
| Missing file part | 400 Bad Request | Report missing file field |
| Request Content-Type is not multipart | 415 Unsupported Media Type | Client fixes request |
| File part exceeds parser disk limit | Request rejected at multipart layer | Record oversized upload error |
| File exceeds business max size | 413 Payload Too Large | Delete staging |
| File has disallowed format | 415 or 422 per API contract | Delete staging |
| User lacks upload permission | 403 Forbidden | Do not write file |
| Storage disk full or permission denied | 5xx | Log internally, do not return filesystem path |
| Virus scan fails | 422 or contract status | Keep quarantine/reject state |
| Client disconnects/cancels | No complete response | Clean staging and track orphan files |

Do not return absolute filesystem paths or stack traces to clients. Logs should record upload ID, authorized user/tenant ID, size, error code, and status; do not log session cookies, tokens, or entire file contents.

If uploads require asynchronous scanning, the API can return 202 Accepted and a job ID, then let clients poll status. Return 201/AVAILABLE only once the file is written and passes all required contract steps.

## 15. Reading and Serving Uploaded Files

Do not expose the storage directory as static resources. When users need to download files, provide an endpoint by ID:

```http
GET /api/uploads/{uploadId}
```

The server should:

1. Authenticate the user.
2. Verify access permission for the upload ID.
3. Retrieve the storage key from the database or trusted metadata.
4. Resolve the path inside the storage root.
5. Check file existence and download policy.
6. Return an appropriate Content-Type, safe Content-Disposition, and proper cache policy.

Do not accept arbitrary filenames from query strings and read files directly off disk. Nor does an opaque ID replace authorization; hard-to-guess UUIDs are only a layer reducing enumeration risk.

To serve large files, use Resource or an appropriate streaming response rather than reading everything into a byte array. Enforce download limits and support ranges if business logic requires resuming.

## 16. Common Mistakes

| Mistake | Consequence | How to fix |
| --- | --- | --- |
| Using client filename as destination | Path traversal or file overwrites | Generate a server-side UUID/storage key |
| Using a single fixed destination | Concurrent requests overwrite each other | Create a separate staging directory per upload |
| Assuming transferTo does not overwrite | Existing destination files get truncated | Generate a unique destination and control overwrites |
| Calling transferTo().subscribe() then returning response | Response may complete before file finishes writing | Compose Mono and return from controller |
| Calling block() to wait for file write | Blocks reactive threads | Use then/flatMap and let WebFlux subscribe |
| Not creating parent directories | Transfer fails due to invalid path | Create root/staging directory before transfer |
| Using normalize as the sole defense | Cannot handle all symlinks/races | Use dedicated root, server-generated paths, and filesystem permissions |
| Trusting client Content-Type | Spoofed MIME files pass through | Check signature/parser and allowlist |
| Checking only file extension | Vulnerable to double extensions or spoofed files | Verify actual content and scan |
| Thinking 256 KiB is the upload limit | Large files can still spool to disk | Configure maxDiskUsagePerPart and request limits |
| Checking size in service only after write | Disk is already consumed before rejection | Block at proxy/parser and quotas |
| Skipping cleanup on error/cancel | Leftover staging files or full temp disk | usingWhen cleanup and a crash-recovery janitor |
| Writing files into webroot | Files may become public or executable | Store outside webroot and download via authorized handler |
| Reading entire file into `byte[]` | Increases heap usage and risks OOM | Use transferTo or streaming PartEvent |
| Reading DataBuffer manually without releasing | Leaks direct/pooled memory | Manage ownership and cleanup across all paths |
| Not limiting part count | Multipart request can create many files/fields | maxParts and gateway limits |
| Letting users choose tenant directory | Could write into another user's directory | Derive tenant from authenticated principal |
| Testing only success | Misses cleanup/error/cancel bugs | Test transfer failure, invalid content, size, and cancellation |

## 17. Secure Upload Implementation Checklist

1. Endpoint consumes `multipart/form-data` and binds the right part via `@RequestPart("file") FilePart`.
2. Destination is built from a server-configured storage root.
3. Client filenames/paths are never used as destinations.
4. A dedicated directory or unique staging key is created per upload.
5. Parent directories are created before calling transferTo.
6. Publishers are composed with then/flatMap; no blocking or manual subscribing.
7. transferTo can never write to important files or files selectable by another request.
8. Size, file type, and content are validated before promoting.
9. Limits are set on memory threshold, disk per part, max parts, total request size, and quota.
10. Files are stored outside the webroot with least-privilege filesystem permissions.
11. Staging is cleaned up on error/cancel with a post-crash orphan cleanup job.
12. If streaming is needed, use PartEvent and consume/relay/release all DataBuffers.
13. Original metadata is stored separately from the storage key; filesystem paths are never returned to clients.
14. Authorization is checked on both upload and download.
15. Tests cover concurrent uploads, duplicate filenames, path traversal, spoofed MIME files, oversized files, and storage errors.

## 18. References

- [Spring Framework – Multipart Content in WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/multipart-forms.html): FilePart, @RequestPart, multipart maps, and PartEvent streaming.
- [FilePart Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/codec/multipart/FilePart.html): filename(), transferTo(File/Path), destination truncation, and client-supplied filename warnings.
- [Part Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/codec/multipart/Part.html): content(), headers(), name(), and delete().
- [DefaultPartHttpMessageReader Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/codec/multipart/DefaultPartHttpMessageReader.html): maxInMemorySize, maxDiskUsagePerPart, maxParts, temp directory, and scheduler.
- [MultipartHttpMessageReader Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/codec/multipart/MultipartHttpMessageReader.html): reading multipart into a MultiValueMap.
- [Spring Framework – Reactive Core / Multipart Limits](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html): memory threshold, disk limits, and multipart parts.
- [OWASP File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html): filename, extension/content validation, storage location, upload limits, and file scanning.
- [OWASP Input Validation Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html): handling untrusted data and multi-layered validation.

## 19. Takeaways

`FilePart.transferTo(Path)` is a convenient way to write multipart file content in WebFlux. It returns `Mono<Void>`, so compose completion inside the reactive pipeline and let WebFlux manage the subscription. If the destination file already exists, transferTo truncates it; therefore, destination paths must be server-generated and unique per upload.

Place the storage root outside the webroot, create a dedicated staging directory, validate the file, and promote it to an internal name. Never use client-sent filenames or paths as storage paths. Distinguish the 256 KiB in-RAM part threshold from actual disk/request limits; configure the multipart parser, gateway, and quotas consistently. When handling DataBuffer/PartEvent directly, consume or release all buffers across success, error, and cancellation. These practices prevent uploads from accidentally overwriting data, leaking paths, or leaving orphaned temporary files behind when requests fail.
