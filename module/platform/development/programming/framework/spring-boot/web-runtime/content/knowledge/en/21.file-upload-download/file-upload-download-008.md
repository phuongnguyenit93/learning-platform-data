# Cleaning Up Temporary Files and Releasing Resources on Request Errors or Cancellations

## 1. The Problem: File Uploads and Downloads Involve Multiple Resource Types

In a **Spring Boot web-runtime** application, uploading or downloading is more than just transferring bytes. The framework may store parts of a multipart request in RAM or temp files; the app may create `.part` files to receive data and hold an `InputStream`, file channel, or `DataBuffer`; meanwhile, the client can close the connection before processing finishes.

A failed request can leave behind:
- A partially written file (partial upload) exposed to others as if it were complete.
- Temporary files consuming disk even after a request errored, expired, or the client disconnected.
- Unclosed `InputStream`, `OutputStream`, file channels, file descriptors, connections, or pooled buffers.
- A background task continuing to write after the HTTP subscriber cancelled.
- A final file already published while the client missed the response, making success vs. failure ambiguous.

Therefore, **two lifecycle layers** must be handled:

1. **Resources owned by the framework/container:** such as multipart parsing and spool files created by the Servlet container or WebFlux multipart reader. They have their own lifecycles; use patched versions and follow API contracts.
2. **Resources created by the application:** such as `Files.createTempFile`, file streams, scan files, extracted archives, and pre-commit staging files. The app is responsible for cleaning these up on every exit path, including exceptions and cancellations.

**Principle:** never assume that the end of an HTTP request proves *all* application files were cleaned up. Make **who creates, who owns, when to publish, and who cleans up** explicit.

## 2. Distinguishing Complete, Error, Cancel, and Crash

| Outcome | MVC / Servlet | WebFlux / Reactor | What Must Be Guaranteed |
|---|---|---|---|
| Successful completion | Method finishes, response written | Publisher completes (`onComplete`) | Close streams/channels; staging moved or deleted |
| Read/write error | `IOException`, validation/security/storage exception | Publisher emits `onError` | Never publish incomplete file; delete staging; preserve root error |
| Client drops mid-way | May hit socket read/write error; sync handler may already or still be running | Framework/transport may cancel subscription on disconnect | Clean up request-owned resources; do not assume external work stops automatically |
| Timeout | Container/Servlet async timeout or custom business timeout | `Mono.timeout`, network timeout, reactive timeout | Stop work cleanly, clean up; never assume side effects rolled back |
| Process killed / power loss | `finally` does not run | `usingWhen` does not run if JVM dies | Must have stale temp-file sweeping, quotas, and reconciliation |

**Cancel is not the same as error.** In Reactor, a subscriber calls `Subscription.cancel()`; upstream may be signaled to stop emitting, yet blocking writes or SDK calls are not guaranteed to abort instantaneously. `doOnError` does not run for cancellations; `doFinally` can observe `CANCEL` as a hook signal. In synchronous MVC, there is no Reactor cancel signal for standard handlers; try-with-resources and catching `IOException` form the baseline cleanup mechanism.

Network errors occurring **after a file is committed** do not automatically roll back file changes. If a client retries after missing the reply, business logic needs an idempotency key, object ID, processing state, or reconciliation workflow.

## 3. Safe File-Saving Pipeline with Staging and Commit

A straightforward design is **exposing the final filename only after writing succeeds**:

```text
HTTP multipart upload
        │
        ├── Parse multipart (framework may spool to temp)
        ▼
Validate metadata + size/type limits
        │
        ▼
Create isolated staging file under app-managed directory
  .incoming-<random>.part
        │
        ▼
Write data to staging
        │
        ├── Error / cancel / timeout ──► stop writing if possible
        │                                  └── close streams/channels
        │                                       └── delete .part
        │
        ▼
Verify size, checksum, content per requirements
        │
        ▼
Move/rename staging to final file on the same filesystem
        │
        ▼
Record file ID and return response
        │
        ▼
Clean up leftover staging path (if any)
```

**Key design decisions:**

- Generate a **server-side UUID/token** for the filename; `MultipartFile.getOriginalFilename()` and `FilePart.filename()` are client-supplied and can hold `../` or untrusted text. Never append client filenames directly into write paths.
- Keep staging and the final file on the **same filesystem** if you plan to use `Files.move(..., ATOMIC_MOVE)`. Atomic moves may not be supported everywhere; when falling back to a regular move, recognize atomicity is no longer strictly guaranteed.
- If an upload involves multiple files or writes both to a database and disk, `Files.move` only guarantees an operation on **one path** per filesystem semantics; it does not create a distributed transaction.
- Treat a file as complete only after copying/transferring and all required checks succeed. In-progress files must never appear in downloadable listings.
- For large files, never call `MultipartFile.getBytes()` or unbounded `DataBufferUtils.join(...)` to hold the entire file in RAM.
- Cap concurrent uploads, per-file size, total request size, disk quotas, and staging retention; if disk is full, return an appropriate error and clean up.

The examples below use **Spring Boot 3.3.x + Java 17+** to demonstrate the APIs. The MVC and WebFlux projects are **independent**; each creates its own `data/uploads` folder in its working directory.

## 4. Spring MVC: Container-Managed Multipart vs. App-Managed Staging

With `spring-boot-starter-web`, Boot automatically configures Servlet multipart. Controllers can accept `@RequestParam("file") MultipartFile`. A part's content may live in memory or the Servlet container's temp storage; `MultipartFile` is only a request-scoped access handle and **must not be retained to read after the request ends**.

Relevant properties:

```properties
spring.servlet.multipart.max-file-size=8MB
spring.servlet.multipart.max-request-size=10MB
spring.servlet.multipart.file-size-threshold=1MB
# Specify *Servlet container multipart staging* location if needed:
# spring.servlet.multipart.location=/var/app/multipart-inbox
```

The `spring.servlet.multipart.location` path must exist with proper permissions in deployment if set. It is **distinct** from the `data/uploads` directory and `.part` files created by the examples. The container/framework cleans up multipart resources per the normal request lifecycle, though async paths, bugs, or older framework versions can affect it; do not indiscriminately delete files in the container's temp folder yourself.

When calling `MultipartFile.transferTo(File)`, the provider may move a temp file, copy it, or flush in-memory bytes; the API does not promise every call is an atomic move. In the example, we use `InputStream` and an app-owned staging file so write and delete behavior is explicit and testable.

## 5. Example A — Spring Boot MVC: try-with-resources Cleans Up Staging on Any Error

### 5.1. Structure and Configuration

```text
mvc-file-cleanup/
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/mvcfiles/MvcFilesApplication.java
    │   └── resources/application.properties
    └── test/java/com/example/mvcfiles/FileStoreTest.java
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`src/main/resources/application.properties`:

```properties
server.port=8080
spring.servlet.multipart.max-file-size=8MB
spring.servlet.multipart.max-request-size=10MB
spring.servlet.multipart.file-size-threshold=1MB
```

### 5.2. Controller, Storage, and Lifecycle

`src/main/java/com/example/mvcfiles/MvcFilesApplication.java`:

```java
package com.example.mvcfiles;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.Map;
import java.util.UUID;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;

@SpringBootApplication
public class MvcFilesApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcFilesApplication.class, args);
    }
}

@RestController
@RequestMapping("/files")
class FilesController {
    private final FileStore store;

    FilesController(FileStore store) {
        this.store = store;
    }

    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    ResponseEntity<Map<String, String>> upload(
            @RequestParam("file") MultipartFile file) throws IOException {
        if (file.isEmpty()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,
                    "Empty file is not accepted");
        }

        // FileStore owns the stream from here and closes it via try-with-resources.
        String id = store.save(file.getInputStream());
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(Map.of("id", id));
    }

    @GetMapping("/{id}")
    ResponseEntity<StreamingResponseBody> download(
            @PathVariable("id") String id) throws IOException {

        Path path = store.find(id);
        StreamingResponseBody responseBody = output -> {
            // Close input even if the client disconnects while writing the response.
            try (InputStream input = Files.newInputStream(path)) {
                input.transferTo(output);
            }
            // Do not close output yourself: the Servlet container owns HTTP output.
        };

        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_OCTET_STREAM)
                .header(HttpHeaders.CONTENT_DISPOSITION,
                        "attachment; filename=\"download.bin\"")
                .body(responseBody);
    }
}

@Service
class FileStore {
    private final Path root;

    FileStore() {
        this(Path.of("data", "uploads"));
    }

    // Constructor used for testing with an isolated directory.
    FileStore(Path root) {
        this.root = root.toAbsolutePath().normalize();
    }

    String save(InputStream supplied) throws IOException {
        Files.createDirectories(root);

        // If any step fails, try-with-resources
        // still closes input and deletes staging.
        try (InputStream input = supplied;
             TempLease stage = new TempLease(
                     Files.createTempFile(root, ".incoming-", ".part"))) {

            Files.copy(input, stage.path(), StandardCopyOption.REPLACE_EXISTING);

            String id = UUID.randomUUID() + ".bin";
            Path published = root.resolve(id);

            try {
                Files.move(stage.path(), published,
                        StandardCopyOption.ATOMIC_MOVE);
            } catch (AtomicMoveNotSupportedException unsupported) {
                // This fallback does not guarantee atomicity across all filesystems.
                Files.move(stage.path(), published);
            }
            return id;
        }
    }

    Path find(String id) {
        // Never use client filenames as arbitrary lookup paths.
        if (!id.matches("[0-9a-fA-F-]{36}\\.bin")) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,
                    "Invalid file id");
        }
        Path path = root.resolve(id).normalize();
        if (!Files.isRegularFile(path)) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND,
                    "File not found");
        }
        return path;
    }

    private record TempLease(Path path) implements AutoCloseable {
        @Override
        public void close() throws IOException {
            Files.deleteIfExists(path);
        }
    }
}
```

**Why does this code clean up temp files reliably?**

- `Files.createTempFile(root, ".incoming-", ".part")` creates an app-controlled random path unrelated to the user's filename.
- `try (InputStream input = supplied; TempLease stage = ...)` closes the stream and invokes `stage.close()` on normal completion **or** exception. Java's try-with-resources also preserves cleanup errors as *suppressed exceptions* if a primary exception was already thrown.
- On success, staging is moved to `UUID.bin`; at the end of the block, `Files.deleteIfExists(stage.path())` sees the staging file is already gone and returns safely.
- If `Files.copy` or `Files.move` fails before commit, `TempLease.close` deletes the incomplete `.part` file. Deletion errors also surface rather than being swallowed silently.
- The download endpoint uses `StreamingResponseBody` to avoid buffering the entire file in memory; `InputStream` is closed even when `output.write`/`transferTo` throws `IOException` because the client dropped mid-stream.
- On the download path, the file may exist during lookup yet be deleted before the stream opens; in that case the async write can fail. Manage that race via retention policy if concurrent deletes are possible.

Example limitation: synchronous uploads can keep running until a read error is detected; if the client disconnects after all bytes were already saved, the committed file may still exist. This is valid for many APIs; use an idempotency key to prevent retries from creating duplicates.

### 5.3. Running and Testing over HTTP

With JDK 17+ and Gradle compatible with Spring Boot 3.3:

```bash
gradle bootRun
```

If the project includes a Gradle Wrapper, use `./gradlew bootRun` (Linux/macOS) or `.\gradlew.bat bootRun` (Windows PowerShell).

Create a sample `sample.txt` containing a line `"hello"` and upload it:

```bash
curl -i -F "file=@sample.txt" http://localhost:8080/files
```

Expected result: HTTP **201 Created**, JSON shaped like:

```json
{"id":"<new-UUID>.bin"}
```

This is an **illustrative format**; `<new-UUID>` is not a fixed output or literal JSON to copy verbatim. The ID is generated randomly on commit.

Use the actual returned `id` value to download the file:

```bash
curl -OJ "http://localhost:8080/files/<actual-ID>"
```

In this example, the response has `Content-Type: application/octet-stream` and `Content-Disposition: attachment; filename="download.bin"`. The `-OJ` flags tell curl to save using the server-suggested filename; replace the placeholder with the actual file ID.

**Never verify success solely via HTTP 201.** Verify downloaded bytes match, no `.incoming-*.part` files remain after processing finishes, and only one `UUID.bin` file exists.

## 6. Testing Mid-Stream Errors to Prove MVC Cleanup

A worthwhile test simulates a source stream reading a few bytes and then throwing `IOException`, asserting that neither a temp file nor a final file remains in the directory.

`src/test/java/com/example/mvcfiles/FileStoreTest.java`:

```java
package com.example.mvcfiles;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class FileStoreTest {
    @TempDir
    Path temp;

    @Test
    void brokenInputDoesNotLeavePartialFile() throws IOException {
        Path root = temp.resolve("uploads");
        FileStore store = new FileStore(root);

        InputStream broken = new InputStream() {
            int reads;

            @Override
            public int read() throws IOException {
                if (++reads > 4) {
                    throw new IOException("simulated input failure");
                }
                return 'a';
            }
        };

        assertThrows(IOException.class, () -> store.save(broken));

        try (Stream<Path> items = Files.list(root)) {
            assertEquals(0L, items.count());
        }
    }
}
```

Run `gradle test`. The test needs no running server or network and **genuinely** exercises the read-failure branch: staging is deleted before the method returns. Class/method/path names align with Example A. In production, also test permission denied/disk full, commit errors, exceptions during delete, and errors while writing post-commit responses.

## 7. When an MVC Request Uses Async Processing

`try-with-resources` fits when the entire resource lifetime lies inside the executing method/callback scope. With `StreamingResponseBody`, the resource must be opened and closed **inside the streaming lambda**, because the controller method returns before streaming runs.

With Servlet async/`DeferredResult`/`Callable` or app-spawned tasks, the controller can return early while work continues. Never create `Path temp` in the method and delete it in the method's `finally` block while an async task is still writing: that can delete the file under the writer.

Hooks to consider depending on the mechanism:
- Servlet async `AsyncListener.onTimeout` / `onError` / `onComplete` to observe async request lifecycle.
- `DeferredResult.onTimeout`, `DeferredResult.onError`, and `onCompletion` to manage MVC-level async responses.
- `Future.cancel` / custom cancellation tokens when application tasks support cancellation.
- Resource leases with explicit owners and state, closed exactly once after the task actually stops.

**An HTTP completion callback does not mean a custom background writer has stopped.** If a background writer exists, coordinate stopping the writer before deleting staging; if the task cannot abort immediately, mark staging for a sweeper job to clean later. Avoid deleting concurrently with an active writer thread on Windows/Linux, as behavior depends on the filesystem.

## 8. Spring WebFlux: FilePart, Cancellation, and Async Resources

With `spring-boot-starter-webflux`, controllers typically accept:

```java
@PostMapping(path = "/files", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public Mono<ResponseEntity<Receipt>> upload(
        @RequestPart("file") FilePart file) {
    return storage.save(file)
            .map(id -> ResponseEntity.status(HttpStatus.CREATED)
                    .body(new Receipt(id)));
}
```

This is an illustrative method requiring the `storage` bean, `Receipt`, and imports; the full example appears in section 9. `org.springframework.http.codec.multipart.FilePart` has `transferTo(Path)` returning `Mono<Void>`: **the transfer runs only when the Mono is subscribed**.

Lifecycle flow:

```text
Multipart parser → FilePart
                       │
                       ▼
       Mono.usingWhen(acquire staging Path)
                       │
                       ▼
             file.transferTo(staging)
                       │
          ┌────────────┼────────────┐
          │            │            │
       complete      onError      cancel
          │            │            │
      commit file      │            │
          │            │            │
          └────────────┴────────────┘
                       │
          async cleanup staging path
                       │
                       ▼
              HTTP response / error
```

**Distinguish two temp types:** the WebFlux multipart reader may spool the body into its own temp file *before* the controller receives `FilePart`, whereas `Files.createTempFile` in the example creates app-managed staging. Cleanup of the latter is handled by the app's `usingWhen`. Never assume older framework/library versions clean up spool files flawlessly on every failure path; track security updates and disk metrics.

If the client closes the connection after the framework finished receiving the multipart body but before the response is written, the backend may already have committed. Decide the policy upfront: either return the same file ID on retry with the same idempotency key, or expose a `"processing"` state for reconciliation.

## 9. Example B — WebFlux: Mono.usingWhen Cleans Up Staging on Complete/Error/Cancel

### 9.1. Standalone Project

```text
webflux-file-cleanup/
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/reactivefiles/ReactiveFilesApplication.java
    │   └── resources/application.properties
    └── test/java/com/example/reactivefiles/LeaseCleanupTest.java
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

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
```

`src/main/resources/application.properties`:

```properties
server.port=8081
# In WebFlux, multipart readers/codecs have separate settings from Servlet.
# Do not use spring.servlet.multipart.* to control reactive uploads.
```

### 9.2. Runnable Code

`src/main/java/com/example/reactivefiles/ReactiveFilesApplication.java`:

```java
package com.example.reactivefiles;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.UUID;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.multipart.FilePart;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@SpringBootApplication
public class ReactiveFilesApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveFilesApplication.class, args);
    }
}

@RestController
@RequestMapping("/files")
class ReactiveFilesController {
    private final ReactiveFileStore store;

    ReactiveFilesController(ReactiveFileStore store) {
        this.store = store;
    }

    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    Mono<ResponseEntity<UploadReceipt>> upload(
            @RequestPart("file") FilePart file) {

        return store.save(file)
                .map(id -> ResponseEntity.status(HttpStatus.CREATED)
                        .body(new UploadReceipt(id)));
    }
}

record UploadReceipt(String id) {}

@Service
class ReactiveFileStore {
    private final Path root = Path.of("data", "uploads")
            .toAbsolutePath().normalize();

    Mono<String> save(FilePart file) {
        return Mono.usingWhen(
                Mono.fromCallable(() -> {
                    Files.createDirectories(root);
                    return Files.createTempFile(
                            root, ".incoming-", ".part");
                }).subscribeOn(Schedulers.boundedElastic()),

                staging -> file.transferTo(staging)
                        .then(Mono.fromCallable(() -> publish(staging))
                                .subscribeOn(Schedulers.boundedElastic())),

                this::deleteStaging,
                (staging, error) -> deleteStaging(staging),
                this::deleteStaging
        );
    }

    private String publish(Path staging) throws IOException {
        String id = UUID.randomUUID() + ".bin";
        Path finalPath = root.resolve(id);
        try {
            Files.move(staging, finalPath,
                    StandardCopyOption.ATOMIC_MOVE);
        } catch (AtomicMoveNotSupportedException unsupported) {
            Files.move(staging, finalPath);
        }
        return id;
    }

    private Mono<Void> deleteStaging(Path staging) {
        // java.nio.file.Files is blocking I/O: offload off the event loop.
        return Mono.fromRunnable(() -> {
            try {
                Files.deleteIfExists(staging);
            } catch (IOException ex) {
                throw new UncheckedIOException(ex);
            }
        }).subscribeOn(Schedulers.boundedElastic()).then();
    }
}
```

**How it works:**

1. `Mono.fromCallable` creates the staging path **only upon subscription**, on `boundedElastic` since `Files.createDirectories/createTempFile` are blocking filesystem calls.
2. `usingWhen` owns one staging `Path` per subscription. `file.transferTo(staging)` processes the body via WebFlux's API; the demo never calls `subscribe()` manually.
3. Only after `transferTo` completes does `publish` move staging to `UUID.bin`; `publish` performs blocking filesystem operations, so it runs on `boundedElastic`.
4. `asyncComplete`, `asyncError`, and `asyncCancel` all invoke `deleteStaging`. On the success path, staging was already moved so delete is a no-op; on error/cancel paths, cleanup deletes the incomplete file.
5. `Mono.usingWhen` waits for cleanup publishers before emitting completion or value downstream on normal termination. **Errors inside cleanup can turn the final signal into an error**, so log/meter cleanup failures and handle them deliberately.
6. If cancel arrives right as a blocking filesystem call runs, `Files.move`/writes are not guaranteed to interrupt instantaneously. At the commit boundary, a race can occur; design idempotency and orphan-staging cleanup jobs, especially with third-party writers.

**Caution:** This demo frees staging files via reactive resource scoping and moves blocking filesystem calls off the event loop. It does not create a transaction between file storage and network responses, nor does it guarantee timely deletion across every OS-level crash/cancellation. Production should pick upload mechanisms with cancellation contracts suited to the driver/filesystem and monitor aged files.

### 9.3. Running and Observing

```bash
gradle bootRun
```

In the project folder, use JDK 17+ and Gradle compatible with Boot 3.3; if using Gradle Wrapper: `./gradlew bootRun` on Linux/macOS or `.\gradlew.bat bootRun` on Windows PowerShell.

```bash
curl -i -F "file=@sample.txt" http://localhost:8081/files
```

Expected result is **HTTP 201** with JSON containing a random `id`, formatted like:

```json
{"id":"<new-UUID>.bin"}
```

This illustrates the format, not an actual ID. After the upload completes, check `data/uploads`: there should be a `UUID.bin` file and no `.incoming-*.part` file from that request.

To try cancelling mid-upload on a large file, you can throttle curl and kill the process, though **there is no guarantee** the controller method has already started. The multipart parser might not have constructed `FilePart` or handed off to the app yet; in that case there is no app staging to delete, and you must observe the framework's own multipart temp area separately. Testing cancellation reliably requires controllable timing as shown next.

## 10. Testing Cancellation of a Reactive Resource Scope

Use `StepVerifier` to cancel a never-completing publisher and await the cleanup callback. This test verifies the **`usingWhen` contract**, without pretending to test full filesystem or HTTP client disconnects.

`src/test/java/com/example/reactivefiles/LeaseCleanupTest.java`:

```java
package com.example.reactivefiles;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertTrue;

class LeaseCleanupTest {

    @Test
    void cancellationTriggersAsyncCleanup() throws InterruptedException {
        CountDownLatch cleaned = new CountDownLatch(1);

        Mono<String> pipeline = Mono.usingWhen(
                Mono.just("lease"),
                lease -> Mono.<String>never(),
                lease -> Mono.empty(),
                (lease, failure) -> Mono.empty(),
                lease -> Mono.fromRunnable(cleaned::countDown)
        );

        StepVerifier.create(pipeline)
                .expectSubscription()
                .thenCancel()
                .verify();

        assertTrue(cleaned.await(2, TimeUnit.SECONDS));
    }
}
```

Run `gradle test`. The test passes when the `asyncCancel` callback executes, decrementing the latch to 0 within two seconds. **This test does not create real files**; for thorough upload verification, add integration tests with large files, a controllable `FilePart` simulating transfer errors/cancellations, assertions that no staging files remain, and real container/OS tests.

With real files, test normal reads, disk full, permission denied, failed cleanups, and cancel/commit races. For async cleanup tests, do not assert HTTP status alone; assert leftover file counts, open file descriptors, pool usage, and error logs.

## 11. Buffers and Low-Level Multipart Streams: Avoiding Memory Leaks

In WebFlux, `FilePart.transferTo(Path)` is the convenient high-level API. When working directly with `Part.content()` or `Flux<PartEvent>`, data arrives as `DataBuffer` instances, some of which are pooled and **reference-counted**.

Ownership principles:

- If the app **directly consumes** `DataBuffer`, follow the release contract after reading or on discard/cancel.
- `DataBufferUtils.release(buffer)` frees a buffer if pooled, yet must not be called when the framework/codec already holds ownership and will release it.
- `doOnDiscard(DataBuffer.class, DataBufferUtils::release)` applies when upstream operators support discard for retained/prefetched buffers; place it carefully and avoid double-release.
- `DataBufferUtils.write(source, OutputStream/Channel)` returning `Flux<DataBuffer>` **does not automatically close the stream/channel or release all buffers for the caller**; handle source lifecycles and buffers per the API contract. Do not confuse it with the `Path`-writing overload returning `Mono<Void>`, which has a different contract.
- With `Flux<PartEvent>` streaming multipart, every data chunk must be **consumed, forwarded, or released**. Dropping events/buffers without cleanup can leak pooled memory.

If you only need to save a received `FilePart` without inspecting individual chunks, prefer `transferTo` to avoid low-level `DataBuffer` management.

WebFlux's `Part` interface also provides `delete(): Mono<Void>` to request deletion of the part's underlying storage per implementation. This is a **part-resource API**, separate from app-created staging files. Never call `delete` concurrently with an active `transferTo` or delete the parser's internal paths directly; compose it cleanly within the Publisher chain per contract. The framework has built-in cleanup, yet buggy versions or unusual request paths still require patches.

## 12. Downloading Files and Closing Resources When Clients Disconnect

In **MVC**, `StreamingResponseBody` opens `InputStream` inside its callback with try-with-resources as in Example A. When `OutputStream.write` throws `IOException` on client disconnect, execution exits the callback and closes the input stream. Never close the container-owned servlet response stream yourself.

In **WebFlux**, an endpoint can return `Resource` or `Mono<Resource>` for files; the framework's response writers manage reading/writing the body and resource lifecycles. Conceptual example:

```java
@GetMapping(path = "/download", produces = MediaType.APPLICATION_OCTET_STREAM_VALUE)
Mono<ResponseEntity<Resource>> download() {
    return Mono.fromCallable(() -> {
        Path file = findExistingFile(); // Illustrative application API.
        return ResponseEntity.ok().body(new FileSystemResource(file));
    }).subscribeOn(Schedulers.boundedElastic());
}
```

This snippet is **not a standalone class**; it requires importing `Resource`, `FileSystemResource`, `ResponseEntity`, `Mono`, `Schedulers`, and implementing `findExistingFile()`. If you build a custom `Flux<DataBuffer>` from `DataBufferUtils.read(...)`, ensure the reader publisher is wired to the response writer without calling `subscribe()` manually, and follow the codec/framework buffer release callbacks.

For temporary files generated **specifically for one download** (e.g., dynamic ZIP/exports), never delete the file right when the controller returns a `Resource`: the HTTP encoder may not have read it yet. Hold the resource lease until the writer finishes or cancels, then clean up. In Reactor, you can use `Flux.usingWhen`/`Mono.usingWhen` keeping response writing **inside the resource closure**; returning a plain `ResponseEntity<Resource>` separates when Spring reads the resource from when the callback ends. In MVC async, clean up inside `StreamingResponseBody` or the true completion callback. For production temp downloads, pick streaming/file-provider APIs with explicit lifecycles.

## 13. Error Handling, Cleanup Failures, and Idempotency

Not every upload failure maps to the same status:

| Scenario | Handling | Typical HTTP |
|---|---|---|
| Oversized file / multipart request | Reject early; enforce size limits and framework cleanup | 413 Payload Too Large if mapped/configured |
| Missing part or invalid metadata | Validate request; avoid opening staging needlessly | 400 |
| Disk full / permission denied | Abort write, delete partial file if any, log storage error | 5xx, typically 500 or 507 per policy |
| Virus scan or content validation fails | Do not publish, clean up staging | 400/422 per contract |
| Client disconnects during upload | Stop work if possible, clean up | Client may receive no response at all |
| Deleting staging fails | Record cleanup failure for reconciliation job | Possibly 5xx; if already cancelled, no client remains |
| Committed yet response lost | Never assume the file does not exist | Retries must be idempotent or return status by ID |

**Cleanup errors must be observable:** emit a `temp_cleanup_failures` metric, log only ID/request correlation, and avoid logging personal data or raw payload bytes. In Java `try-with-resources`, exceptions in `close` attach as suppressed to the primary exception; in Reactor `usingWhen`, cleanup errors can alter downstream signals. Never slap `onErrorResume(e -> Mono.empty())` blindly onto cleanup just to “ignore it,” as that hides resource leaks.

**Side effects do not auto-rollback:** a file moved successfully before the client drops can remain on disk. Any app needing exactly-once semantics requires server-generated IDs, idempotency keys, duplicate checks, or deliberate metadata state tracking. Atomic move only prevents publishing half-written files within a filesystem; it is not an HTTP, DB, or object-storage transaction.

## 14. Sweeping Orphan Files After Process Crashes

No `finally`, `doFinally`, or `usingWhen` is guaranteed to run on `kill -9`, power failure, or sudden container eviction. To prevent disk exhaustion, production needs a **reaper/sweeper**:

1. Scan only **app-owned staging directories**; never blindly sweep `java.io.tmpdir` or container/framework-managed folders.
2. Match only specific patterns like `.incoming-*.part` under a verified root (never follow symlinks to arbitrary targets).
3. Choose an age threshold exceeding the maximum valid upload duration; check timestamps plus upload session/lease state if stored.
4. Distinguish **actively written** files from orphans: multiple instances may share storage; use owner/heartbeat/lease or storage isolation to avoid deleting active uploads.
5. Use bounded retries with backoff for transient errors; export metrics for orphan count, bytes, staging age, and delete failures.
6. Set staging disk usage quotas/alerts and isolated cleanup; prevent malicious uploads from exhausting the main filesystem.

**Illustrative** code for a single-instance program prior to building a real reaper:

```java
try (Stream<Path> paths = Files.list(stagingDirectory)) {
    paths.filter(path -> {
        String name = path.getFileName().toString();
        return name.startsWith(".incoming-") && name.endsWith(".part");
    }).filter(path -> Files.isRegularFile(path))
      .filter(path -> isExpired(path)) // Must implement via lease/age.
      .forEach(path -> safeDelete(path)); // Must log/retry per policy.
}
```

This snippet **does not run standalone**; `stagingDirectory`, `isExpired`, and `safeDelete` must be defined. Without a reliable way to confirm a file is no longer active, never run a destructive sweep over shared staging.

## 15. Real-World Failure Monitoring and Security Bounds

Useful metrics:
- `upload_staging_files` and `upload_staging_bytes`: count and bytes currently in staging.
- `upload_cleanup_errors_total`, `upload_cancel_total`: failed cleanups and cancellations (distinguishing timeout vs. disconnect if observable).
- `upload_commit_success_total`, `upload_commit_failures_total`.
- Orphan files older than TTL; free disk/inodes; open file descriptors and pooled direct memory; multipart-related 4xx/5xx counts.

Upload protections: size and part-count limits, treating content-type merely as a hint (never trusted blindly), actual format verification when needed, protection against path traversal and symlink traversal, malware scanning where threat model warrants, and never serving user files from paths that can execute scripts. For ZIP/extraction, guard against Zip Slip and zip bombs, cap total extracted file counts and bytes; extracted artifacts must also follow staging and cleanup rules.

**Version & patch note:** Spring disclosed **CVE-2026-22740** (2026-04-17) regarding WebFlux multipart temp files potentially lingering in certain cases. The advisory lists affected Spring Framework branches with specific fixed versions (e.g., 6.2.18 and 7.0.7 on their respective branches; 6.1.27 via commercial support). Therefore **never assume WebFlux alone eliminates leaks automatically**; verify your deployment's actual framework version, support/patch status, and multipart temp behavior. The Spring Boot 3.3.x examples above teach the 6.1 API, not a promise that older dependencies still receive security fixes.

## 16. Common Issues

| Symptom | Possible Cause | How to Check |
|---|---|---|
| `.part` files left after failed upload | Cleanup ran only on success; writer may still be active | Use try-with-resources / usingWhen, test error/cancel, track leases |
| File deleted before download finishes | Cleanup ran when controller returned view/ResponseEntity without waiting for writer | Tie cleanup to stream/writer lifecycle callbacks |
| `onErrorResume` misses cancellations | Cancel is not `onError` | Use cleanup scopes and `doFinally` to observe `CANCEL` |
| Parser temp grows even after app deletes staging | Framework maintains separate multipart spool | Check version, multipart config, advisories, and spool directory |
| Netty direct memory grows | Pooled `DataBuffer` not released/discarded | Audit ownership, `DataBufferUtils.release`, `doOnDiscard`, leak detection |
| Disk full with zero active requests | Process crash; orphan staging not swept | Reaper job + TTL + quotas + alerts |
| Client cancels yet server keeps writing | Blocking I/O/external driver non-cancellable; late cancel | Audit threads and transfer lifecycle; clean up after writer stops |
| Same file created twice | Client retried after losing response despite completed commit | Idempotency keys/metadata for reconciliation |
| File named `../../...` | Trusted client filename | Use server-generated IDs, check root/normalization |
| IOException when deleting staging | Permissions/locks, race, or filesystem issue | Log cleanup errors, safe retries, reconciliation job |

## 17. Knowledge Self-Check

**Q1:** Why isn't calling `Files.deleteIfExists` inside `catch(IOException)` sufficient?  
**Answer:** Cleanup must also run on completion, other exception types, cancellations, and stream closure; use try-with-resources (MVC) or `usingWhen` (WebFlux). Crashes require a separate reaper.

**Q2:** Do Servlet/WebFlux parser temp files and app-created `.incoming-...part` files share the same owner?  
**Answer:** No. The parser/framework manages its own spool storage; the app must clean up its own staging. Never sweep shared temp directories indiscriminately.

**Q3:** Why not guarantee returning HTTP 504 as a fixed response after a client disconnects?  
**Answer:** The client already closed the connection and may receive nothing; if headers/body were committed, status cannot be changed arbitrarily either.

**Q4:** Why isn't `FilePart.transferTo(Path)` alone enough to guarantee a file is committed and free of orphans?  
**Answer:** It only signals completion of transferring the part per contract; the app must still validate/commit, clean up staging on error/cancel, and handle races and crashes.

**Q5:** When is `DataBufferUtils.release` needed and when is it not?  
**Answer:** When application code owns a pooled buffer, it must release it per contract. If WebFlux encoders/decoders or helpers took ownership and release it themselves, calling release again can cause a double-release bug.

**Q6:** If an upload already moved staging to the final file and then the response was lost, should the file be deleted?  
**Answer:** Depends on the business contract and idempotency; never equate a lost response with the commit not happening.

## 18. Official Documentation

- Spring Framework — Multipart Resolver in MVC: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/multipart.html
- Spring Boot 3.3 — Common Application Properties, `spring.servlet.multipart.*` properties: https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
- Spring Framework 6.1 — `MultipartFile`, temp storage, and `transferTo`: https://docs.spring.io/spring-framework/docs/6.1.3/javadoc-api/org/springframework/web/multipart/MultipartFile.html
- Spring Framework — WebFlux Multipart Content, `FilePart` / `PartEvent`: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/multipart-forms.html
- Spring Framework 6.1 — `FilePart` and `Part.delete` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/http/codec/multipart/FilePart.html
- Spring Framework — Data Buffers and Codecs: https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html
- Spring Framework 6.1 — `DataBufferUtils` overloads: https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/core/io/buffer/DataBufferUtils.html
- Reactor — `Mono.usingWhen` complete/error/cancel cleanup: https://projectreactor.io/docs/core/3.6.17/api/reactor/core/publisher/Mono.html
- Spring Security Advisory CVE-2026-22740, temp files in WebFlux multipart: https://spring.io/security/cve-2026-22740

**Remember:** safe file handling requires explicit **ownership**, writing via **staging**, **committing only upon completion**, and cleaning up on **success/error/cancel**. `finally`/`usingWhen` handle in-process lifecycles; **orphan sweeper jobs** and patched dependencies cover crashes and multipart parser bugs.
