# Testing I/O Errors, Access Permissions, Stream Closure, and Resource Cleanup

A document upload feature in Spring Boot may work fine with small files and writable directories, yet fail when a volume fills up, a file is locked, the OS user lacks permissions, an input stream breaks mid-transfer, or renaming a temporary file fails. If tests only assert `HTTP 201` on the happy path, the application can leave behind `.tmp` files with partial data, leak file descriptors, expose internal paths to clients, or report success before data is actually saved.

This Knowledge lesson belongs to **Additional integration** in the **Spring Boot – testing** module, focusing on four intertwined failure areas: **I/O errors**, **access permissions**, **stream lifecycles**, and **resource cleanup**. We design a file store with an explicit I/O boundary, simulate `AccessDeniedException` and read/write/close stream errors, test cleanup when `move` fails, and verify the multipart API with `MockMvc`. The goal is not building a complete production storage service, but cultivating the habit of **testing failure paths and resource postconditions**.

Examples use **Java 17+, Spring Boot 3.5.16, JUnit Jupiter 5, Mockito, Spring MVC, MockMvc, `@TempDir`, and NIO.2 (`java.nio.file`)**. Sample files are synthetic and confined to test directories. Permission errors are simulated **deterministically** rather than relying on `chmod` or whether CI runs as root/administrator. The pattern guarantees stream closure and staging deletion across simulated failures; it does not replace dedicated testing for disk crashes, durability, antivirus/file locks, symlink races, or specialized filesystems.

## 1. Learning objectives

After this lesson, you will be able to:

- Recognize `IOException`, `NoSuchFileException`, `AccessDeniedException`, `FileAlreadyExistsException`, `FileSystemException`, `EOFException`, and `UncheckedIOException` along with their usage contexts.
- Distinguish **HTTP 401/403 authentication/authorization errors** from **OS/process filesystem ACL errors**; never blindly map every `AccessDeniedException` to HTTP 403.
- Define clearly **who owns `InputStream`/`OutputStream`** and who is responsible for calling `close()`.
- Use `try-with-resources` to close streams on success, read failures, write failures, and `close` failures.
- Understand resource closing order and `Throwable.getSuppressed()`.
- Explain why `Files.copy(InputStream, Path)` does **not** automatically close the `InputStream`.
- Write to a staging file before publishing to the final destination so incomplete copies are never exposed.
- Clean up temporary files when copy/move fails without deleting already-published files.
- Assert postconditions: zero leftover `.part` files, no corrupt final files, and input streams closed.
- Use `@TempDir` to isolate real files and a Mockito spy / fake I/O adapter to inject exceptions deterministically.
- Avoid relying on POSIX permission bits when tests run on Windows or privileged CI runners.
- Test `MockMvc.multipart(...)`, JSON error contracts, and verify internal paths are never leaked.
- Distinguish mock MVC multipart tests from real socket/parser tests on `RANDOM_PORT`.
- Guard against path traversal, symlink abuse, oversized payloads, duplicate IDs, and directory permission pitfalls.
- Apply the same resource-ownership cleanup principles to databases, Redis, object storage, transactions, and file handles.

## 2. Four failure layers to distinguish

```text
HTTP caller
   |
   | multipart/form-data
   v
Spring MVC / MultipartResolver
   |  - oversized request / malformed multipart
   |  - servlet temp files
   v
DocumentController
   |  - is the user authorized to upload?
   |  - validation and public error contract
   v
LocalDocumentStore
   |  - takes ownership of InputStream
   |  - creates .part in app-controlled directory
   |  - streams bytes into staging file
   |  - closes OutputStream and InputStream
   |  - moves staging -> generated final name
   v
NIO / filesystem / OS
   |  - read failure, write failure, disk full
   |  - AccessDeniedException, lock, quota
   |  - rename/move failure, cleanup failure
   v
HTTP response:
  201 when stored
  400 invalid ID
  404 file not found
  413 file exceeds store limit
  500 IO/server storage error (without leaking absolute path)
```

**No single layer replaces all others.** `@WebMvcTest` with a mocked store proves the controller maps errors properly; store unit tests with real NIO prove cleanup/read/write logic; fake I/O permission tests make fault injection deterministic; real HTTP integration tests verify multipart parsers, containers, and proxies.

### 2.1. Error and source matrix

| Symptom | Possible source | What to assert |
|---|---|---|
| `NoSuchFileException` | Deleted file, unknown ID, race | 404 when client fetches; no path leak |
| `AccessDeniedException` | Process lacks file/directory permission | Does not report success; stream closed; safe public error |
| `FileAlreadyExistsException` | Destination collision or existing path | Never overwrites unrelated data |
| `FileSystemException` | Filesystem-specific (disk full, file lock, etc.) | Classification/retry policy; cleanup itself can fail |
| `EOFException` | Fewer bytes read than contract expects | Never treat partial file as complete |
| `IOException` during `read` | Broken source or remote stream | Zero leftover staging files |
| `IOException` during `write/close` | Partial output, failed flush/close | Never publish partial output |
| `IOException` during `move` | Promotion failed or uncertain | Never return 201; clean up staging per policy |
| `IOException` during `delete` | Cleanup failed | Preserve primary error via suppressed exceptions |
| `UncheckedIOException` | Adapter/lambda wrapping checked I/O error | Preserve root cause and lifecycle |
| Socket timeout | HTTP client / remote object store | Dedicated timeout/retry/idempotency rules |
| HTTP 403 | Security filter / business ACL **or** public policy | Do not equate automatically with OS `AccessDeniedException` |

## 3. Checked `IOException` and NIO.2 taxonomy

`IOException` is Java's checked I/O exception, with several subclasses offering concrete semantics:

```java
import java.io.IOException;
import java.io.EOFException;
import java.nio.file.AccessDeniedException;
import java.nio.file.NoSuchFileException;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.FileSystemException;
```

`AccessDeniedException`, `NoSuchFileException`, and `FileAlreadyExistsException` all extend `FileSystemException`; they report filesystem conditions and OS/provider reasons, carrying no inherent HTTP status. On `FileSystemException`, `getFile()`, `getOtherFile()`, and `getReason()` can expose internal paths—**never serialize the raw exception to an HTTP response**.

Tests should check **the exception type** when part of the contract and **postconditions**. Asserting `assertThrows(IOException.class, ...)` alone misses leaked streams or leftover partial files.

### 3.1. Do not map every `IOException` to "client error"

A read failure caused by a client disconnecting belongs to connection handling. In contrast, write failures due to a read-only volume, full disk, or missing service-account permissions are server infrastructure failures. Returning HTTP 403 for a process `AccessDeniedException` misleads clients into thinking **the user needs higher application privileges**, when in truth the server volume or service account is misconfigured.

The sample maps generic filesystem I/O errors to **HTTP 500 + a neutral error code**. That is an illustrative policy; production apps may pick 503 or 507 per contract, always hiding absolute paths, stack traces, and permission layouts. **HTTP 403 should express application-level authorization denial**, not automatically translate every OS permission error.

## 4. Which resources must close, and who owns them?

| Resource | Who opens? | Who closes? | On mid-operation failure |
|---|---|---|---|
| Upload `InputStream` from `MultipartFile.getInputStream()` | Controller obtains stream | **`FileStore`** per demo contract | Closes even if temp file creation fails |
| Staging `OutputStream` | `FileStore` calls I/O adapter | `FileStore` | `try-with-resources` closes before publish |
| Download `InputStream` | `FileStore` reads file | `FileStore` (since it returns `byte[]`) | Closes even when read fails |
| `Files.list(...)` `Stream<Path>` | Test/util creates | Test/util | `try-with-resources` closes directory stream |
| `Files.walk(...)` `Stream<Path>` | Cleanup code creates | Cleanup code | Close stream to avoid open handles |
| `ZipFile`, `ZipInputStream` | Archive processor | Stream owner | Close even on invalid archives |
| `BufferedReader` / `BufferedWriter` | Code creating wrapper | Wrapper/resource owner | Flush/close via `try-with-resources` |
| JDBC `Connection` / `ResultSet` | Driver / pool | Per transaction / pool contract | Do not manually close pooled physical connections |
| HTTP response body stream | Client adapter | Response consumer | Close/consume per HTTP client API |
| Servlet multipart temp file | Servlet/container resolver | Framework/container | Do not confuse with app staging files |

**Define ownership before writing code:** the demo's `store.save(InputStream input)` **takes ownership** and closes `input` on both success and failure. If another API only "borrows" a stream that the caller will keep using, it must not close it and should document that contract explicitly. There is no universal rule that "every method taking an `InputStream` must close it."

### 4.1. `Files.copy` does not close the `InputStream`

A common anti-pattern:

```java
// ANTI-PATTERN: caller does not close input after Files.copy.
Files.copy(input, target, StandardCopyOption.REPLACE_EXISTING);
```

The JDK documents that `Files.copy(InputStream, Path, ...)` copies bytes and can leave a partial target on failure; **it does not manage ownership or close the `InputStream` for you**. Write:

```java
try (InputStream input = source.openStream()) {
    Files.copy(input, target);
}
```

This snippet assumes `source` and `target`. Even when `InputStream` closes, the destination file may still hold partial bytes if copy fails; for atomic-style publication, use **staging + move** with cleanup as shown in the main sample.

## 5. `try-with-resources`: closing even when exceptions occur

```java
try (InputStream in = openInput();
     OutputStream out = openOutput()) {
    in.transferTo(out);
}
```

In this snippet, `openInput` and `openOutput` are illustrative factory methods; full runnable code appears later. Java closes resources in **reverse declaration order**: `out.close()` first, then `in.close()`. If reading or writing throws, Java still attempts to close every resource that opened successfully.

**Important:** `transferTo` can copy unbounded amounts of data; for untrusted uploads, enforce size limits at both the HTTP parser and application storage layers instead of letting arbitrary bytes exhaust RAM or disk. The demo `FileStore` uses a bounded copy loop.

### 5.1. Checked exceptions during `close()`

`close()` **can also throw `IOException`**. Storage devices or buffered streams may fail while flushing on close. To avoid reporting success before output flushes cleanly, the sample:

1. Opens input and staging output.
2. Copies bytes.
3. **Closes output**.
4. **Closes input**.
5. **Only afterward** moves staging to the final filename.
6. If any of steps 1–4 fail, deletes staging without publishing.

This ordering prevents moving a file and then throwing on `InputStream.close()`, which would make the caller see an error even though the file was published. Still, local move/copy alone does not guarantee durability on power loss; see section 29.

## 6. Suppressed exceptions: preserving both primary and cleanup failures

Java's `try-with-resources` preserves the primary exception from the block body and attaches `close()` failures to `Throwable.getSuppressed()`.

Standalone Java 17 example:

```java
public class SuppressedDemo {
    static final class BrokenResource implements AutoCloseable {
        @Override
        public void close() throws Exception {
            throw new Exception("close failed");
        }
    }

    public static void main(String[] args) {
        try (BrokenResource ignored = new BrokenResource()) {
            throw new IllegalStateException("work failed");
        } catch (Exception e) {
            System.out.println(e.getMessage());
            System.out.println(e.getSuppressed()[0].getMessage());
        }
    }
}
```

Run:

```bash
javac SuppressedDemo.java
java SuppressedDemo
```

**Exact stdout:**

```text
work failed
close failed
```

If manual cleanup inside `finally` throws during delete, that error can **mask the original copy error**. `LocalDocumentStore` tracks `primary` and calls `primary.addSuppressed(cleanup)` so the root cause is never lost. A dedicated test verifies both primary and suppressed exceptions when `move` and cleanup both fail.

**Never silently swallow cleanup failures.** If there is no primary exception, the cleanup failure should propagate; if there is a primary exception, retain it and attach the cleanup failure. Logs should distinguish primary vs. cleanup errors without leaking secret paths.

## 7. Why use a staging file?

Anti-pattern:

```java
try (InputStream in = upload.getInputStream()) {
    Files.copy(in, finalPath);
}
```

If copying fails partway, `finalPath` already exists with truncated bytes. Concurrent GET requests can read it as a complete file, or background jobs can process corrupt data.

Safer workflow:

```text
1. Validate request/ID, check quota
2. createDirectories(root) as appropriate
3. createTempFile(root, ".part-*") on the same filesystem
4. open output for staging
5. copy with size limit
6. close output, close input
7. move staging -> generated final filename
8. return object ID / size
9. on error: deleteIfExists(staging), do not publish ID
```

Creating the staging file in the **same directory/filesystem** as the destination enables atomic renames on supporting providers and avoids cross-device moves. Even so, **default `Files.move` does not promise atomicity or fsync durability**. The demo uses portable `move` across OSes; production apps may require `StandardCopyOption.ATOMIC_MOVE` and **fail** on `AtomicMoveNotSupportedException` rather than falling back unsafely.

### 7.1. Staging files are not a crash recovery journal

If a process receives `kill -9` or the host loses power, Java `finally` blocks never run, leaving `.part` files behind. Production systems need a **janitor cleanup job** targeting stale stages in an isolated namespace with clear retention windows and metrics—never deleting active in-flight uploads. `try-with-resources` handles **control flow within a live JVM** only.

## 8. "Permissions" span multiple layers

| Layer | Example | What tests should verify |
|---|---|---|
| Application authorization | User A may not read User B's file | Spring Security 403/404, zero I/O calls |
| Filesystem permissions / ACLs | Process cannot write to volume | I/O adapter throws `AccessDeniedException` |
| Container UID/GID | Non-root Kubernetes pod vs. volume owner | Integration test with real container/volume |
| SELinux / AppArmor | OS security policy blocks file op | Environment-specific integration |
| Object storage IAM | S3 role lacks `PutObject`/`DeleteObject` | Mocked boundary + IAM integration |
| Windows ACLs / file sharing | Locked file / missing rights | Windows / real filesystem test |
| NFS/SMB remote permissions | Stale handle, share denial, network split | Integration test on real server |

**OS `AccessDeniedException` does not test Spring Security authentication/authorization.** The sample tests OS errors at the storage layer; real security tests must verify `Principal` and object ownership whenever users upload or download.

### 8.1. Why are `chmod 000` tests flaky?

On Linux/macOS, `Files.setPosixFilePermissions(...)` can block reads/writes for ordinary users. However:

- Windows filesystem providers may not support `PosixFileAttributeView`.
- CI runners executing as root/administrator can still access files despite cleared mode bits.
- ACLs, mount flags, and NFS semantics differ.
- Altering permissions on a shared directory can break other tests.
- Already-open file descriptors may continue reading/writing after permission changes.

Therefore, **unit-test `AccessDeniedException` handling with a fake/spy I/O adapter**, and gate a few OS-specific integration tests behind assumptions/labels on matching runners. Never assume a passing local `chmod` test behaves identically on CI or cloud nodes.

## 9. Test pyramid for I/O and resource cleanup

| Tier | Tooling | Catches | Misses |
|---|---|---|---|
| Pure unit | Fake `InputStream`/`OutputStream` | Read/write/close failures, primary/suppressed | Real ACLs / filesystem behavior |
| Temp filesystem | JUnit `@TempDir` + `Files` | Staging/final files, readbacks, cleanup | Volume-specific permissions |
| I/O adapter fault injection | Mockito spy / adapter | Exact `AccessDenied`, move/delete failures | Full OS-specific exception nuances |
| MVC slice | `@WebMvcTest` + `MockMultipartFile` | HTTP statuses, JSON codes, no path leaks | Real multipart parser / TCP sockets |
| Full app MockMvc | `@SpringBootTest` + `@AutoConfigureMockMvc` | Real wiring / controller / store | Real TCP / multipart parsing |
| Real HTTP | `RANDOM_PORT` + real multipart client | Container limits / parsing / temp cleanup | Cloud IAM / volumes if env differs |
| Container/volume integration | Testcontainers + mounted volumes / IAM emulator | Provider-specific UID/GID/quotas/locks | Full production cloud behavior |

**Strong tests do not always require real sockets**, yet they must accurately state the boundary they verify. `MockMvc.multipart(...)` builds an in-memory `MockMultipartHttpServletRequest`; it does not exercise reverse proxy or servlet container request-size limits.

## 10. Runnable project design

We build a demo-grade safe binary file storage service:

- Clients upload multipart files via `POST /api/documents`.
- The server generates `UUID.bin`; **it never uses `MultipartFile.getOriginalFilename()` as a path**.
- Bytes stream into `.upload-*.part` inside an app-owned directory.
- Only after copying and closing both input and output streams succeed does the staging file `move` to its final name.
- A 1 MiB quota is enforced **inside `FileStore`** (distinct from the multipart parser).
- Clients download via `GET /api/documents/{id}`; `FileStore` reads up to 1 MiB, closes the `InputStream`, and returns `byte[]`.
- A `StorageOps` interface isolates NIO calls so `AccessDenied` and read/write/move/delete failures can be injected deterministically.
- Error advice returns public JSON codes without serializing `IOException.getMessage()` paths.
- Tests use `@TempDir` and fault injection to prove cleanup and stream closure.

**Structure:**

```text
io-resource-testing/
  settings.gradle
  build.gradle
  src/main/java/com/example/ioresource/
    IoResourceApplication.java
    StorageOps.java
    NioStorageOps.java
    StoredDocument.java
    FileTooLargeException.java
    InvalidDocumentIdException.java
    LocalDocumentStore.java
    StoreConfiguration.java
    DocumentController.java
    StorageErrorAdvice.java
  src/test/java/com/example/ioresource/
    LocalDocumentStoreTest.java
    DocumentControllerTest.java
    DocumentIntegrationTest.java
```

This is a **single-module** example using Java 17, Spring Boot 3.5.16, and JUnit Jupiter/Mockito. It needs no Docker, database, or external network services. The demo lacks authentication, auditing, malware scanning, encryption at rest, retention policies, durable catalogs, and idempotency; do not use it as-is for sensitive production data.

## 11. Gradle files

**`settings.gradle`**

```groovy
rootProject.name = 'io-resource-testing'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
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

`spring-boot-starter-web` provides Spring MVC and JSON serialization; `spring-boot-starter-test` provides JUnit Jupiter, Mockito, MockMvc, JUnit's `@TempDir`, and assertion utilities. No extra virtual filesystem or permission library is required: JDK NIO.2 paired with a mockable adapter cleanly exercises every failure branch.

**Never run tests against production accounts or real upload paths.** The demo's default storage property targets `./build/io-store` inside the project when not overridden, never sensitive host paths.

## 12. Spring Boot bootstrap

**`src/main/java/com/example/ioresource/IoResourceApplication.java`**

```java
package com.example.ioresource;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class IoResourceApplication {
    public static void main(String[] args) {
        SpringApplication.run(IoResourceApplication.class, args);
    }
}
```

The application automatically scans `@Component NioStorageOps`, `@Configuration StoreConfiguration`, the controller, and the advice in the same package. Storage unit tests instantiate objects directly without starting a Spring context.

## 13. I/O adapter: isolating failable NIO calls

**`src/main/java/com/example/ioresource/StorageOps.java`**

```java
package com.example.ioresource;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Path;

public interface StorageOps {

    void createDirectories(Path directory) throws IOException;

    Path createTempFile(Path directory) throws IOException;

    OutputStream openOutput(Path path) throws IOException;

    InputStream openInput(Path path) throws IOException;

    void move(Path source, Path destination) throws IOException;

    void deleteIfExists(Path path) throws IOException;
}
```

**`src/main/java/com/example/ioresource/NioStorageOps.java`**

```java
package com.example.ioresource;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import org.springframework.stereotype.Component;

@Component
public class NioStorageOps implements StorageOps {

    @Override
    public void createDirectories(Path directory)
            throws IOException {
        Files.createDirectories(directory);
    }

    @Override
    public Path createTempFile(Path directory)
            throws IOException {
        return Files.createTempFile(
                directory, ".upload-", ".part");
    }

    @Override
    public OutputStream openOutput(Path path)
            throws IOException {
        return Files.newOutputStream(
                path,
                StandardOpenOption.WRITE,
                StandardOpenOption.TRUNCATE_EXISTING);
    }

    @Override
    public InputStream openInput(Path path)
            throws IOException {
        return Files.newInputStream(
                path, StandardOpenOption.READ);
    }

    @Override
    public void move(Path source, Path destination)
            throws IOException {
        Files.move(source, destination);
    }

    @Override
    public void deleteIfExists(Path path)
            throws IOException {
        Files.deleteIfExists(path);
    }
}
```

**Why introduce this interface?** Instead of mutating real OS ACLs in tests, Mockito can make `createDirectories`, `createTempFile`, `openOutput`, `move`, or `deleteIfExists` throw deterministically. When unstubbed, `NioStorageOps` delegates straight to JDK `Files`, so `@TempDir` tests verify real disk state.

**Important for production security:** `Files.newInputStream`/`newOutputStream` here do not use `SecureDirectoryStream`, `NOFOLLOW_LINKS`, or defend against every symlink race. They assume **the directory is private and untrusted actors cannot modify entries**. When external untrusted processes can write to the storage directory, enforce symlink-safe/`openat`/ACL protections or use object storage with strict identity policies.

## 14. Value objects and domain input exceptions

**`src/main/java/com/example/ioresource/StoredDocument.java`**

```java
package com.example.ioresource;

public record StoredDocument(String id, long bytes) {
}
```

**`src/main/java/com/example/ioresource/FileTooLargeException.java`**

```java
package com.example.ioresource;

import java.io.IOException;

public class FileTooLargeException extends IOException {
    public FileTooLargeException(String message) {
        super(message);
    }
}
```

**`src/main/java/com/example/ioresource/InvalidDocumentIdException.java`**

```java
package com.example.ioresource;

public class InvalidDocumentIdException
        extends IllegalArgumentException {

    public InvalidDocumentIdException() {
        super("Invalid document identifier");
    }
}
```

Intentionally using a **dedicated exception type** for invalid IDs avoids catching every `IllegalArgumentException` across the app; an internal programming bug should never surface as a client 400. `FileTooLargeException` is a specialized `IOException` mapped to 413 on uploads, while NIO `AccessDeniedException` maps as a storage infrastructure error without printing file paths in responses.

## 15. `LocalDocumentStore`: closing streams before publishing

**`src/main/java/com/example/ioresource/LocalDocumentStore.java`**

```java
package com.example.ioresource;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Path;
import java.time.Duration;
import java.util.Objects;
import java.util.UUID;
import java.util.regex.Pattern;

public final class LocalDocumentStore {

    private static final Pattern DOCUMENT_ID = Pattern.compile(
            "^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
            + "[0-9a-f]{4}-[0-9a-f]{12}\\.bin$");

    private final Path root;
    private final StorageOps ops;
    private final long maxBytes;

    public LocalDocumentStore(
            Path root, StorageOps ops, long maxBytes) {
        this.root = Objects.requireNonNull(
                root, "root").toAbsolutePath().normalize();
        this.ops = Objects.requireNonNull(ops, "ops");
        if (maxBytes <= 0) {
            throw new IllegalArgumentException(
                    "maxBytes must be positive");
        }
        this.maxBytes = maxBytes;
    }

    public StoredDocument save(InputStream input)
            throws IOException {

        Objects.requireNonNull(input, "input");

        Path staged = null;
        boolean promoted = false;
        Throwable primary = null;
        long byteCount = 0L;
        String id = UUID.randomUUID() + ".bin";

        try {
            // Store owns input. It closes even if mkdir/create fails.
            try (InputStream source = input) {
                ops.createDirectories(root);
                staged = ops.createTempFile(root);

                try (OutputStream target =
                             ops.openOutput(staged)) {
                    byteCount = copyBounded(source, target);
                }
            }

            // Only publish after BOTH streams closed successfully.
            ops.move(staged, root.resolve(id));
            promoted = true;
            return new StoredDocument(id, byteCount);

        } catch (IOException | RuntimeException error) {
            primary = error;
            throw error;

        } finally {
            if (staged != null && !promoted) {
                try {
                    ops.deleteIfExists(staged);
                } catch (IOException cleanupError) {
                    if (primary != null) {
                        primary.addSuppressed(cleanupError);
                    } else {
                        throw cleanupError;
                    }
                }
            }
        }
    }

    public byte[] readBytes(String id) throws IOException {
        if (id == null
                || !DOCUMENT_ID.matcher(id).matches()) {
            throw new InvalidDocumentIdException();
        }

        Path path = root.resolve(id);

        try (InputStream source = ops.openInput(path);
             ByteArrayOutputStream result =
                     new ByteArrayOutputStream()) {
            try {
                copyBounded(source, result);
            } catch (FileTooLargeException tooLarge) {
                throw new IOException(
                        "Stored data exceeds read safety limit",
                        tooLarge);
            }
            return result.toByteArray();
        }
    }

    private long copyBounded(
            InputStream source, OutputStream target)
            throws IOException {

        byte[] buffer = new byte[8192];
        long count = 0L;
        int amount;

        while ((amount = source.read(buffer)) != -1) {
            if (amount == 0) {
                throw new IOException(
                        "Unexpected zero-length read");
            }

            if (amount > maxBytes - count) {
                throw new FileTooLargeException(
                        "File exceeds configured size limit");
            }

            target.write(buffer, 0, amount);
            count += amount;
        }

        return count;
    }
}
```

**Important:** This is a complete Java file. The `java.time.Duration` import above is unused; Java allows unused imports (triggering only an IDE/linter warning) without affecting compilation. Production projects should remove it per Checkstyle/Spotless rules. Logic is intentionally minimal so **ownership, resource closure, and cleanup** remain crystal clear.

### 15.1. Success sequence

1. `save` takes ownership of the `InputStream`.
2. `createDirectories` prepares the directory.
3. `createTempFile` returns a `Path` inside `root`.
4. `openOutput` opens the staging file.
5. `copyBounded` copies up to `maxBytes`.
6. `target.close()` runs via `try-with-resources`; on error, jumps to the failure path.
7. `source.close()` runs via `try-with-resources`; on error, also enters the failure path.
8. `ops.move(staged, root.resolve(id))` publishes the file.
9. `promoted=true`, returning the generated ID and byte count.
10. `finally` **leaves the published file untouched**.

### 15.2. Failure sequence

If mkdir/create/read/write/close/move fails:

- The input stream is closed if execution entered `try (InputStream source = input)`.
- The output stream is closed if opened.
- If `staged` exists → `deleteIfExists` runs.
- If delete also fails, the cleanup error is added to `error.getSuppressed()`.
- Neither `StoredDocument` nor HTTP 201 is returned.
- The generated destination filename is never published unless promotion succeeds.

**Explicit limitation:** OS/filesystem crashes, ambiguous move failures, `fsync` durability, and process kills cannot be "proven" by `finally` alone. Critical data requires storage transactions/outbox/idempotency, atomic moves where supported, and a dedicated recovery janitor.

### 15.3. Reading files: who owns the input stream?

`readBytes` opens the `InputStream`, **reads it into RAM within `maxBytes`**, and closes the stream before returning `byte[]`. This suits the demo's ≤1 MiB cap. For multi-GB files, never buffer everything in RAM: stream responses with explicit closing responsibility and test client disconnects, backpressure, and servlet lifecycles.

### 15.4. Why validate IDs instead of using `originalFilename`?

Final files use a server-generated UUID, and `readBytes` accepts only exact `UUID.bin` strings. `../../secrets`, slashes, backslashes, and client-supplied filenames cannot escape `root`. Still, **name validation does not stop symlink races** if another actor can create symlinks inside `root`: production requires strict directory permissions and safe open primitives.

## 16. Spring bean configuration and upload limits

**`src/main/java/com/example/ioresource/StoreConfiguration.java`**

```java
package com.example.ioresource;

import java.nio.file.Path;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class StoreConfiguration {

    @Bean
    LocalDocumentStore localDocumentStore(
            StorageOps ops,
            @Value("${demo.storage.root:./build/io-store}")
                    String root,
            @Value("${demo.storage.max-bytes:1048576}")
                    long maxBytes) {

        return new LocalDocumentStore(
                Path.of(root), ops, maxBytes);
    }
}
```

`demo.storage.root` must point to an **application-owned, isolated directory**. The `./build/io-store` default works for the demo, not production. `demo.storage.max-bytes=1048576` enforces **1 MiB at the storage layer**, alongside multipart parser and proxy limits:

```properties
# Example multipart parser limits; does not replace the store's maxBytes.
spring.servlet.multipart.max-file-size=5MB
spring.servlet.multipart.max-request-size=6MB
demo.storage.max-bytes=1048576
```

Note: `MockMvc.multipart(...)` does not run a real servlet container parser, so do not use a MockMvc test to claim `spring.servlet.multipart.max-file-size` rejects bytes on TCP. Test storage limits directly; test servlet parser limits via a real server integration test.

## 17. HTTP controller and response contract

**`src/main/java/com/example/ioresource/DocumentController.java`**

```java
package com.example.ioresource;

import java.io.IOException;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequestMapping("/api/documents")
public class DocumentController {

    private final LocalDocumentStore store;

    public DocumentController(LocalDocumentStore store) {
        this.store = store;
    }

    @PostMapping(
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<StoredDocument> upload(
            @RequestPart("file") MultipartFile file)
            throws IOException {

        return ResponseEntity.status(HttpStatus.CREATED)
                .body(store.save(file.getInputStream()));
    }

    @GetMapping(
            path = "/{id}",
            produces = MediaType.APPLICATION_OCTET_STREAM_VALUE)
    public ResponseEntity<byte[]> download(
            @PathVariable String id) throws IOException {

        return ResponseEntity.ok()
                .contentType(
                        MediaType.APPLICATION_OCTET_STREAM)
                .body(store.readBytes(id));
    }
}
```

**The controller does not call `close` a second time** because `store.save` already took ownership of the stream. Having both controller and storage close a non-idempotent resource can cause confusing errors or states. If switching to `MultipartFile.transferTo(Path)` instead of `InputStream`, ownership and cleanup differ: inspect the API Javadoc; servlet multipart temp files are still managed by the multipart resolver/container.

On upload failure, the controller never returns 201. On invalid download IDs, the store throws `InvalidDocumentIdException`; on missing files, NIO throws `NoSuchFileException`; on OS denials or I/O failures, advice maps appropriate error responses.

## 18. Error advice: never leak OS paths in responses

**`src/main/java/com/example/ioresource/StorageErrorAdvice.java`**

```java
package com.example.ioresource;

import java.io.IOException;
import java.nio.file.NoSuchFileException;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class StorageErrorAdvice {

    public record ErrorPayload(String code) {
    }

    @ExceptionHandler(InvalidDocumentIdException.class)
    ResponseEntity<ErrorPayload> invalidId() {
        return ResponseEntity.badRequest()
                .body(new ErrorPayload("INVALID_ID"));
    }

    @ExceptionHandler(NoSuchFileException.class)
    ResponseEntity<ErrorPayload> missingFile() {
        return ResponseEntity.status(404)
                .body(new ErrorPayload("NOT_FOUND"));
    }

    @ExceptionHandler(FileTooLargeException.class)
    ResponseEntity<ErrorPayload> tooLarge() {
        return ResponseEntity.status(413)
                .body(new ErrorPayload("TOO_LARGE"));
    }

    @ExceptionHandler(IOException.class)
    ResponseEntity<ErrorPayload> ioError() {
        return ResponseEntity.status(500)
                .body(new ErrorPayload("STORAGE_FAILURE"));
    }
}
```

Spring MVC matches specific exception handlers before generic `IOException`. NIO's `AccessDeniedException` is an `IOException`, so it maps to 500 in the demo rather than being confused with a Spring Security 403 authorization denial.

**Postcondition to test:** paths like `/srv/private/invoices` inside exception messages must never appear in JSON responses. Server logs may record stack traces under logging policy without leaking keys or tokens; test responses return only `code`.

**Do not assume a generic `IOException` handler covers every HTTP failure:** if a client disconnects mid-response after headers are committed, advice cannot reliably rewrite the response to JSON 500. Large-file download streaming needs separate tests.

## 19. JUnit `@TempDir`: testing real files without touching the workspace

JUnit Jupiter provides:

```java
@TempDir
Path tempDirectory;
```

The extension allocates a dedicated directory per test lifecycle scope with JUnit-managed cleanup. It beats hardcoding `/tmp/test.txt` because:

- No collisions across parallel tests.
- Never alters user or production files.
- Independent of working directory and drive letters.
- Lets tests inspect exact staging and final files.
- Still attempts cleanup on test failure depending on lifecycle mode.
- Keeps tests portable across Windows, macOS, and Linux.

**Do not use `@TempDir` to test permission denial with `chmod` by default.** Test permission branches via a spy or OS-gated tests with assumptions. And **never blindly run `Files.walk(root).forEach(delete)`** on paths from external inputs: confine deletion strictly to test-owned directories.

### 19.1. `Files.list` must be closed too

In tests:

```java
try (Stream<Path> entries = Files.list(root)) {
    assertEquals(0L, entries.count());
}
```

`Files.list` returns a `Stream<Path>` backed by an OS directory handle that must be closed. Likewise, `Files.walk` and `Files.lines` must be closed to prevent handle leaks or Windows failing to delete the directory afterward.

## 20. Store tests: happy paths and failures with Mockito spy

**`src/test/java/com/example/ioresource/LocalDocumentStoreTest.java`**

```java
package com.example.ioresource;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.AccessDeniedException;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.util.stream.Stream;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doReturn;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.spy;

class LocalDocumentStoreTest {

    @TempDir
    Path root;

    private NioStorageOps ops;
    private LocalDocumentStore store;

    @BeforeEach
    void setUp() {
        ops = spy(new NioStorageOps());
        store = new LocalDocumentStore(root, ops, 8);
    }

    @Test
    void savesAndReadsBytesWithoutLeftoverStage()
            throws Exception {

        byte[] bytes = "abc".getBytes(StandardCharsets.UTF_8);
        TrackedInput input = new TrackedInput(bytes);

        StoredDocument saved = store.save(input);

        assertTrue(input.closed);
        assertEquals(3L, saved.bytes());
        assertTrue(Files.exists(root.resolve(saved.id())));
        assertArrayEquals(bytes, store.readBytes(saved.id()));
        assertEquals(1L, fileCount());
    }

    @Test
    void overLimitFailsAndDeletesStaging()
            throws Exception {

        TrackedInput input = new TrackedInput(
                "123456789".getBytes(StandardCharsets.UTF_8));

        assertThrows(FileTooLargeException.class,
                () -> store.save(input));

        assertTrue(input.closed);
        assertEquals(0L, fileCount());
    }

    @Test
    void readErrorStillClosesInputAndDeletesStage()
            throws Exception {

        FailingReadInput input = new FailingReadInput();

        IOException error = assertThrows(
                IOException.class,
                () -> store.save(input));

        assertEquals("read failed", error.getMessage());
        assertTrue(input.closed);
        assertEquals(0L, fileCount());
    }

    @Test
    void writeErrorClosesInputAndDeletesStage()
            throws Exception {

        OutputStream brokenOutput = new OutputStream() {
            @Override
            public void write(int value) throws IOException {
                throw new IOException("disk write failed");
            }
        };

        doReturn(brokenOutput).when(ops)
                .openOutput(any(Path.class));

        TrackedInput input = new TrackedInput(
                "abc".getBytes(StandardCharsets.UTF_8));

        IOException error = assertThrows(
                IOException.class,
                () -> store.save(input));

        assertEquals("disk write failed", error.getMessage());
        assertTrue(input.closed);
        assertEquals(0L, fileCount());
    }

    @Test
    void directoryPermissionErrorStillClosesInput()
            throws Exception {

        doThrow(new AccessDeniedException("blocked-root"))
                .when(ops).createDirectories(root);

        TrackedInput input = new TrackedInput(
                "abc".getBytes(StandardCharsets.UTF_8));

        assertThrows(AccessDeniedException.class,
                () -> store.save(input));

        assertTrue(input.closed);
        assertEquals(0L, fileCount());
    }

    @Test
    void cannotOpenStageOutputLeavesNoStage()
            throws Exception {

        doThrow(new AccessDeniedException("blocked-file"))
                .when(ops).openOutput(any(Path.class));

        TrackedInput input = new TrackedInput(
                "abc".getBytes(StandardCharsets.UTF_8));

        assertThrows(AccessDeniedException.class,
                () -> store.save(input));

        assertTrue(input.closed);
        assertEquals(0L, fileCount());
    }

    @Test
    void moveAccessDeniedDeletesUnpromotedStage()
            throws Exception {

        doThrow(new AccessDeniedException("rename blocked"))
                .when(ops).move(
                        any(Path.class), any(Path.class));

        TrackedInput input = new TrackedInput(
                "abc".getBytes(StandardCharsets.UTF_8));

        assertThrows(AccessDeniedException.class,
                () -> store.save(input));

        assertTrue(input.closed);
        assertEquals(0L, fileCount());
    }

    @Test
    void cleanupFailureIsSuppressedOnOriginalMoveError()
            throws Exception {

        doThrow(new IOException("move failed"))
                .when(ops).move(
                        any(Path.class), any(Path.class));
        doThrow(new IOException("delete failed"))
                .when(ops).deleteIfExists(any(Path.class));

        IOException error = assertThrows(
                IOException.class,
                () -> store.save(new ByteArrayInputStream(
                        "abc".getBytes(StandardCharsets.UTF_8))));

        assertEquals("move failed", error.getMessage());
        assertEquals(1, error.getSuppressed().length);
        assertEquals(
                "delete failed",
                error.getSuppressed()[0].getMessage());
        // The intentional failed cleanup leaves a .part file.
        // @TempDir extension owns this isolated test directory.
    }

    @Test
    void sourceCloseFailureHappensBeforePublish()
            throws Exception {

        InputStream closeFails =
                new ByteArrayInputStream(
                        "abc".getBytes(StandardCharsets.UTF_8)) {
                    @Override
                    public void close() throws IOException {
                        super.close();
                        throw new IOException("input close failed");
                    }
                };

        IOException error = assertThrows(
                IOException.class,
                () -> store.save(closeFails));

        assertEquals("input close failed", error.getMessage());
        assertEquals(0L, fileCount());
    }

    @Test
    void invalidIdCannotEscapeStoreRoot()
            throws Exception {

        assertThrows(InvalidDocumentIdException.class,
                () -> store.readBytes("../secrets.txt"));
        assertEquals(0L, fileCount());
    }

    @Test
    void absentDocumentReturnsNoSuchFile()
            throws Exception {

        String validButUnknown =
                "00000000-0000-0000-0000-000000000000.bin";

        assertThrows(NoSuchFileException.class,
                () -> store.readBytes(validButUnknown));
    }

    @Test
    void failingDownloadReadClosesOpenedStream()
            throws Exception {

        StoredDocument saved = store.save(
                new ByteArrayInputStream(
                        "abc".getBytes(StandardCharsets.UTF_8)));
        FailingReadInput faulty = new FailingReadInput();

        doReturn(faulty).when(ops).openInput(
                root.resolve(saved.id()));

        assertThrows(IOException.class,
                () -> store.readBytes(saved.id()));

        assertTrue(faulty.closed);
        assertTrue(Files.exists(root.resolve(saved.id())));
    }

    private long fileCount() throws IOException {
        try (Stream<Path> files = Files.list(root)) {
            return files.count();
        }
    }

    private static final class TrackedInput
            extends ByteArrayInputStream {

        boolean closed;

        TrackedInput(byte[] bytes) {
            super(bytes);
        }

        @Override
        public void close() throws IOException {
            closed = true;
            super.close();
        }
    }

    private static final class FailingReadInput
            extends InputStream {

        private boolean first = true;
        boolean closed;

        @Override
        public int read() throws IOException {
            if (first) {
                first = false;
                return 'A';
            }
            throw new IOException("read failed");
        }

        @Override
        public void close() {
            closed = true;
        }
    }
}
```

**There are 12 test methods** in this class. They exercise real filesystem operations inside `@TempDir`, injecting exceptions via a Mockito spy on `NioStorageOps`. None modify POSIX permissions or assume specific CI runner privileges.

### 20.1. Why test write failures without actually filling a disk?

Generating multi-GB files to trigger `ENOSPC` can break CI, take forever, or disrupt other jobs. In `writeErrorClosesInputAndDeletesStage`, the spy returns an `OutputStream` that throws `IOException("disk write failed")`. The real staging file is still created on disk, proving filesystem cleanup without requiring an actual full disk. Dedicated volume-quota tests verify OS/volume limits separately.

### 20.2. Why do permission tests use `doThrow`?

`doThrow(new AccessDeniedException(...))` ensures the error branch executes regardless of Windows ACLs, POSIX mode bits, Docker users, or running as root. Unit tests guard the **application's reaction** to errors. Proving an application deployment has real permissions on a PVC/NFS/S3 bucket requires an integration test in that environment.

### 20.3. What does the cleanup-failure test prove?

When `move` throws `IOException` and deleting the staging file also throws `IOException`, the code preserves **`move failed`** as the primary exception and attaches **`delete failed`** as suppressed. Catching and ignoring delete errors would silently accumulate orphan temp files. A production janitor needs alerting, quotas, and retention policies, plus safe retries without deleting arbitrary files.

### 20.4. How is stream ownership verified?

`TrackedInput.closed` flips to `true` inside `close()`. Tests assert `true` across mkdir, write, and move failures. Checking only `fileCount == 0` without checking `closed` misses file descriptor leaks on Windows; checking only `closed` without checking staging misses partial files left behind.

## 21. MVC slice: checking HTTP statuses and redaction of paths

**`src/test/java/com/example/ioresource/DocumentControllerTest.java`**

```java
package com.example.ioresource;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.AccessDeniedException;
import java.nio.file.NoSuchFileException;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.not;
import static org.hamcrest.Matchers.containsString;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(DocumentController.class)
@Import(StorageErrorAdvice.class)
class DocumentControllerTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    LocalDocumentStore store;

    @Test
    void validMultipartMapsToCreatedResponse()
            throws Exception {

        MockMultipartFile file = new MockMultipartFile(
                "file", "../../untrusted-name.txt",
                "text/plain",
                "abc".getBytes(StandardCharsets.UTF_8));

        when(store.save(any(InputStream.class)))
                .thenReturn(new StoredDocument(
                        "11111111-1111-4111-8111-111111111111.bin",
                        3));

        mvc.perform(multipart("/api/documents").file(file))
                .andExpectAll(
                        status().isCreated(),
                        jsonPath("$.bytes").value(3),
                        jsonPath("$.id").value(
                                "11111111-1111-4111-8111-111111111111.bin"));

        verify(store).save(any(InputStream.class));
        // Controller does not use original filename as storage path.
    }

    @Test
    void noSuchDocumentMapsTo404WithoutRawPath()
            throws Exception {

        String id =
                "00000000-0000-0000-0000-000000000000.bin";

        when(store.readBytes(id))
                .thenThrow(new NoSuchFileException(
                        "/srv/private/missing.bin"));

        mvc.perform(get("/api/documents/{id}", id))
                .andExpectAll(
                        status().isNotFound(),
                        jsonPath("$.code").value("NOT_FOUND"),
                        content().string(
                                not(containsString("/srv/private"))));
    }

    @Test
    void storagePermissionDeniedIsServerErrorNotAuth403()
            throws Exception {

        MockMultipartFile file = new MockMultipartFile(
                "file", "data.bin",
                "application/octet-stream",
                new byte[] {1, 2});

        when(store.save(any(InputStream.class)))
                .thenThrow(new AccessDeniedException(
                        "/srv/private/upload-root"));

        mvc.perform(multipart("/api/documents").file(file))
                .andExpectAll(
                        status().isInternalServerError(),
                        jsonPath("$.code").value("STORAGE_FAILURE"),
                        content().string(
                                not(containsString("/srv/private"))));
    }

    @Test
    void oversizedPayloadIs413WithNeutralCode()
            throws Exception {

        MockMultipartFile file = new MockMultipartFile(
                "file", "huge.bin",
                "application/octet-stream",
                new byte[] {1, 2});

        when(store.save(any(InputStream.class)))
                .thenThrow(new FileTooLargeException(
                        "secret storage limit path"));

        mvc.perform(multipart("/api/documents").file(file))
                .andExpectAll(
                        status().is(413),
                        jsonPath("$.code").value("TOO_LARGE"),
                        content().string(
                                not(containsString("secret storage"))));
    }
}
```

**There are 4 test methods.** `@WebMvcTest` runs the real controller against a mocked `LocalDocumentStore`, verifying multipart request mapping and exception handlers at the MVC layer. It does not test NIO cleanup—`LocalDocumentStoreTest` handles that. Also, **`MockMultipartFile`** lives in memory rather than running a real TCP multipart parser.

Spring Security 403 responses (if added later) require their own tests; here, filesystem `AccessDeniedException` maps to 500 so users do not mistake server I/O errors for HTTP authorization denials.

## 22. Full Spring context with real NIO and MockMvc

**`src/test/java/com/example/ioresource/DocumentIntegrationTest.java`**

```java
package com.example.ioresource;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
        "demo.storage.max-bytes=1048576",
        "spring.servlet.multipart.max-file-size=5MB",
        "spring.servlet.multipart.max-request-size=6MB"
})
@AutoConfigureMockMvc
class DocumentIntegrationTest {

    @TempDir
    static Path root;

    @DynamicPropertySource
    static void storageDirectory(DynamicPropertyRegistry registry) {
        registry.add(
                "demo.storage.root", () -> root.toString());
    }

    @Autowired
    MockMvc mvc;

    @Autowired
    ObjectMapper objectMapper;

    @Test
    void realNioStoreRoundTripsUploadedDocument()
            throws Exception {

        byte[] bytes = "hello".getBytes(StandardCharsets.UTF_8);
        MockMultipartFile file = new MockMultipartFile(
                "file", "../../not-a-path.txt",
                "text/plain", bytes);

        MvcResult created = mvc.perform(
                multipart("/api/documents").file(file))
                .andExpectAll(
                        status().isCreated(),
                        jsonPath("$.bytes").value(5))
                .andReturn();

        String id = objectMapper.readTree(
                created.getResponse().getContentAsString())
                .get("id").asText();

        assertTrue(Files.exists(root.resolve(id)));

        mvc.perform(get("/api/documents/{id}", id))
                .andExpectAll(
                        status().isOk(),
                        content().bytes(bytes));

        try (Stream<Path> paths = Files.list(root)) {
            assertEquals(
                    0L,
                    paths.filter(p -> p.getFileName()
                            .toString().endsWith(".part")).count());
        }
    }

    @Test
    void storeRejectsPayloadOverOneMib()
            throws Exception {

        byte[] bytes = new byte[1048577];
        MockMultipartFile file = new MockMultipartFile(
                "file", "large.bin",
                "application/octet-stream", bytes);

        mvc.perform(multipart("/api/documents").file(file))
                .andExpectAll(
                        status().is(413),
                        jsonPath("$.code").value("TOO_LARGE"));
    }

    @Test
    void malformedIdIs400RatherThanRawFilesystemLookup()
            throws Exception {

        mvc.perform(get("/api/documents/{id}", "bad_id"))
                .andExpectAll(
                        status().isBadRequest(),
                        jsonPath("$.code").value("INVALID_ID"));
    }
}
```

**There are 3 test methods.** The full-context test uses the real NIO adapter, real bean configuration, and real files inside `@TempDir`, though `MockMvc` still opens no TCP socket. It proves controller/store wiring, staging cleanup on the happy path, and the 1 MiB **storage-layer** limit—not reverse proxy or servlet multipart parser limits in production.

**JUnit / context caching note:** `@TempDir static Path root` follows the test class lifecycle, while `@DynamicPropertySource` supplies the directory when the Spring context constructs beans. If multiple test classes share a cached context while each declares its own static `@TempDir`, the file store or DataSource can point to a temp directory already deleted by JUnit. The demo uses **only one class** with this configuration; real projects should use unique dynamic configs, isolated contexts, or a test-owned directory aligned with the cached context's lifetime.

## 23. Test count summary and running the suite

| Test class | `@Test` count | Focus |
|---|---:|---|
| `LocalDocumentStoreTest` | 12 | Read/write/move/permissions/close/cleanup and suppressed exceptions |
| `DocumentControllerTest` | 4 | HTTP statuses, 413/404/500, and error redaction |
| `DocumentIntegrationTest` | 3 | Real Spring + NIO wiring, mock multipart, and readback |
| **Total** | **19** | I/O failure paths + stream ownership + resource cleanup |

Run:

```bash
./gradlew test
```

Windows PowerShell:

```powershell
.\gradlew.bat test
```

**Expected** outcome given compatible build/dependencies/Java 17: `BUILD SUCCESSFUL`. JUnit reports appear at `build/reports/tests/test/index.html`. **Gradle/JUnit was not executed against an actual repository here**, so this is an expected result from reviewing source and APIs rather than an execution report.

There is no fixed business stdout. Generated UUIDs, temp filenames, filesystem paths, and test execution order vary and are not asserted. Failure branches are injected deterministically via Mockito, making error codes and staging assertions far more stable than forcing real disk-full or permission denials on CI.

## 24. Test matrix: every failure must verify postconditions

| Failure | Input closed? | Output closed? | Stage removed? | Final visible? | API result |
|---|---|---|---|---|---|
| Success | Yes | Yes | Stage moved away from temp name | Yes | 201 |
| Directory create denied | Yes | Not opened | No stage created | No | 500 |
| Temp file create denied | Yes | Not opened | No stage created | No | 500 |
| Output open denied | Yes | Failed to open | Cleanup attempted | No | 500 |
| Read `IOException` | Yes | Close attempted | Cleanup attempted | No | 500 |
| Write `IOException` | Yes | Close attempted | Cleanup attempted | No | 500 |
| Input close `IOException` | Close attempted | Already closed | Cleanup attempted | No | 500 |
| Output close `IOException` | Close attempted | Close attempted | Cleanup attempted | No | 500 |
| Move `AccessDeniedException` | Yes | Yes | Cleanup attempted | Publish not confirmed | 500 |
| Cleanup `IOException` | Yes | Per primary error | **Attempted, yet file may remain** | Publish not confirmed | 500 + suppressed |
| Payload over limit | Yes | Close attempted | Cleanup attempted | No | 413 |
| Download file absent | Failed to open | N/A | N/A | No | 404 |
| Download read `IOException` | Close attempted | `ByteArrayOutputStream` closed | N/A | Existing file remains | 500 |
| Invalid document ID | Not opened | N/A | No | No | 400 |

**Distinguish "attempted close" from "closed cleanly."** When `close()` itself throws, tests cannot guarantee the underlying OS handle was released; track metrics/diagnostics or provider-specific checks. Likewise, when `delete` fails, never claim "stage removed"—tests must assert the suppressed exception and production needs a cleanup/recovery policy.

## 25. A critical bug: close failure after publishing

Anti-pattern:

```java
try (InputStream input = requestInput) {
    Files.copy(input, tempPath);
    Files.move(tempPath, finalPath);
    return success();
}
// InputStream.close() runs only AFTER the final file has moved.
```

If `InputStream.close()` throws `IOException`, the method reports failure even though the file is already published. Client retries create duplicate documents. The demo closes **both source and output before `ops.move`**:

```text
try (InputStream) {
    try (OutputStream) { copy(); }
}
move(staging, final);
return success;
```

That small difference in brace placement changes **externally observable state**. `sourceCloseFailureHappensBeforePublish` proves a close failure deletes staging without creating a final file.

**Note:** reordering `close()` does not turn a filesystem into a perfect ACID transaction. `move` can still fail ambiguously, and the app can be killed at any line. If callers retry, use idempotency keys, object registries, compensation policies, and durable checkpoints.

## 26. When should you use `Files.move(..., ATOMIC_MOVE)`?

`StandardCopyOption.ATOMIC_MOVE` instructs the filesystem to execute the move as an atomic operation, though **not every provider supports it**, especially across filesystems. The API throws `AtomicMoveNotSupportedException` when unsupported. When requirements demand "readers never observe a half-published file," production code should:

- Create staging on the exact same filesystem as the final target.
- Move with `ATOMIC_MOVE`.
- If unsupported, **fail per policy** instead of falling back silently.
- Omit `REPLACE_EXISTING` when overwrites are forbidden.
- Guard against duplicate destination IDs/collisions.
- Check provider docs for behavior when the destination already exists.
- Consider `FileChannel.force(true)` and directory `fsync` if crash/power-loss durability is required (OS/provider-dependent).
- For object storage, never assume atomic rename; rely on multipart completion and metadata publish contracts.

**`ATOMIC_MOVE` does not guarantee crash durability** or exactly-once request semantics. MockOps tests verify the options passed; real filesystem tests must run on the target provider. The demo uses portable `Files.move` to focus on error handling and cleanup without claiming production durability.

## 27. Reading streams in Spring MVC and ownership

When the controller returns `byte[]`, Spring MVC already holds the bytes in RAM and `LocalDocumentStore.readBytes` closed the input before response serialization. For large files, apps commonly return `Resource` or `StreamingResponseBody`:

```java
// Snippet: not a standalone runnable file.
// StreamingResponseBody requires lifecycle/error management per framework.
StreamingResponseBody body = out -> {
    try (InputStream in = storage.openOwnedStream(id)) {
        in.transferTo(out);
    }
};
```

Here `out` belongs to the servlet response and **should not be closed manually** when managed by the framework. The `InputStream` from the storage adapter must close after copying. If a client disconnects mid-stream, `IOException` can occur after HTTP headers are committed, making it impossible to switch cleanly to a JSON 500 body. Test response write failures, early disconnects, and boundary cleanup explicitly.

### 27.1. `InputStreamResource` is single-use

`InputStreamResource` wraps an **already-open stream**, not a resource repeatable at will. If framework/test code calls `contentLength()` or reads twice on certain paths, the stream can be consumed prematurely. For files on disk, `PathResource` or a `Resource` capable of opening fresh streams is preferable. Never grant callers arbitrary filesystem read access; validate IDs, enforce authorization, and bind lifecycles carefully.

## 28. Path traversal, symlinks, and filesystem trust boundaries

A request such as:

```http
POST /api/documents
filename="../../application.yml"
```

must never write outside the root. The demo ignores `originalFilename` in paths, generating `UUID.bin`, and GET accepts only strict regex-validated IDs. Still, production faces extra risks:

- `resolve(userInput)` followed by `normalize()` alone does not stop symlink traversal.
- A symlink inside the root can point outside the root even with a valid filename.
- Time-of-check/time-of-use (TOCTOU): checking `exists`/`isReadable` and opening afterward allows swaps in between.
- Windows path canonicalization (drive letters, UNC paths, reserved device names) differs from POSIX.
- Case-insensitive filesystems and Unicode normalization can cause collisions.
- Shared world-writable temp directories risk races when filenames are predictable.
- Zip Slip when extracting archive entry names is also path traversal.
- Root ACLs must prevent untrusted users/processes from altering contents.
- Reading files per tenant requires application-level ownership authorization before NIO opens.

**Never treat a UUID regex as a security substitute for OS ACLs.** Production requires private roots, strict permissions/ownership, no-follow strategies when untrusted actors exist, storage/network egress controls, and auditing.

## 29. Disk full, quotas, partial writes, and durability

Disk-full failures can appear when:

- `Files.createTempFile` fails to allocate an entry.
- `OutputStream.write` throws `IOException` after writing partial bytes.
- `flush()`/`close()` reports a delayed write error.
- `Files.move` fails due to filesystem or provider limits.
- Another process consumes remaining quota right after a free-space check.

**Never rely on `Files.getFileStore(...).getUsableSpace()` as a guarantee of enough space**; it is a point-in-time snapshot subject to races and quotas. Enforce application upload limits before/during copying, monitor disk usage, and handle real `IOException` failures. Fault injection for disk-full is safer than generating massive files in CI; run real volume-quota tests in isolated dedicated environments.

**Durability:** closing a stream does not mean bytes were `fsync`ed to physical media. Systems needing power-loss guarantees require explicit durability contracts with the filesystem/object store and matching integration tests. A `@TempDir` test writing and reading right back only proves visibility in the live runtime, not crash survival.

## 30. Concurrency, duplicate names, and retries

A client may time out after the server published the file yet before receiving `201`. Retrying the upload creates **two UUID files**, even though each `save` succeeded cleanly. When duplicates violate the contract:

- Accept a caller/operation-scoped idempotency key.
- Record a registry mapping `key → object status/result` transactionally.
- Define explicit states: `UPLOADING`, `COMMITTED`, `FAILED`.
- Clean up orphaned stages by TTL without deleting in-flight uploads.
- Prevent two concurrent requests with the same key from publishing two objects.
- When pairing DB records with files, use outbox/saga/compensation; filesystem moves do not share transactions with JDBC.
- Never rely on single-JVM `synchronized` across multiple replicas.

**UUID filenames are not an idempotency mechanism.** They only prevent filename collisions. Even without overwriting another object's name, retries still create business-level duplicates.

## 31. Resource cleanup after an application crash

`try-with-resources` runs when Java control flow exits a block, not when a process is killed or the host loses power. Artifacts can remain:

```text
root/
  .upload-442211.part        <- orphaned incomplete stage
  1960c74d-... .bin         <- already published
  .upload-667788.part        <- actively used by a live request
```

A janitor **must never delete every `.part` file immediately**, because it could delete a live upload's staging file. Require ownership/age thresholds, upload leases, or process coordination, and scan only app-owned directories. With multiple pods sharing a PVC, use distributed locks/leases or metadata so janitors do not step on each other.

In object storage, incomplete multipart uploads incur storage charges; configure lifecycle policies to abort incomplete multipart uploads and audit them. For servlet temp uploads, containers run their own cleanup, yet you should not rely on them to clean application staging files.

## 32. File locks and Windows-specific failures

Windows is far stricter about unclosed file handles: a file cannot be renamed or deleted while a stream stays open or antivirus scans it. Linux/POSIX allows unlinking open files, so a passing "file deleted" test on Linux does not prove handles were closed.

How to catch handle leaks:

- Use `TrackedInput.closed` / instrumented `OutputStream` in unit tests.
- Use `@TempDir` to scope test files cleanly.
- Run real lock tests on a Windows runner when Windows is a supported target.
- Retry transient lock errors with bounded backoff and idempotency—never retry every `AccessDeniedException` infinitely.
- Never ignore cleanup failures just because Linux allows unlinking.
- Close `Files.list`/`Files.walk` streams so JUnit `@TempDir` cleanup is never blocked.

**Cross-platform tests must avoid asserting exact OS error messages.** `AccessDeniedException.getMessage()` differs by provider, locale, and path. Assert exception types and contracts rather than exact wording unless your own test explicitly threw that message.

## 33. NIO permissions and cross-platform simulation

When a product must test real POSIX permissions:

```java
// Snippet runs on a POSIX runner supporting the attribute view.
// Does not run by default on Windows or as CI root.
Assumptions.assumeTrue(Files.getFileStore(dir)
        .supportsFileAttributeView("posix"));
Files.setPosixFilePermissions(
        dir, PosixFilePermissions.fromString("r--------"));
```

This is a **snippet**, not part of the demo tests; it also needs `Assumptions`, `Files`, and `PosixFilePermissions` imports plus restoring permissions in `finally` before `@TempDir` cleanup. Even on POSIX, privileged processes can bypass mode bits, so robust tests add effective-UID assumptions or run inside non-root containers.

For Windows ACLs, use `AclFileAttributeView` on a dedicated Windows runner. Never force the same `chmod` test across every OS.

## 34. Interacting with cloud object storage and remote I/O

Stream-closure and cleanup principles apply equally to S3, GCS, and Azure Blob, though the real APIs have different semantics:

- Object-store multipart uploads use `complete` or `abort` rather than `Files.move`.
- Cloud IAM denials are usually wrapped by SDKs as service exceptions with HTTP 403 from the cloud API; that is a **backend IAM error**, not automatically an HTTP 403 to return to your end user.
- S3 read streams must be closed to return connections to the SDK HTTP pool.
- Socket timeouts and partial responses have different retry/chunking semantics than local filesystems.
- Object deletion and multipart aborts can be eventual and require idempotency.
- Object versioning can make "delete" write a delete marker while retaining versioned data.
- Testcontainers/MinIO emulators are helpful yet do not cover all cloud IAM/policy nuances.
- Production error logs must never print access keys, presigned URLs, or private object names.

To test cloud adapters, extract a `StorageOps`-style boundary, mock SDK error types in unit tests, and run integration tests in isolated sandboxes/containers. Assert cleanup on **test-owned object IDs / upload IDs** rather than calling "delete entire bucket" on shared storage.

## 35. Filesystem tests and HTTP tests do not prove the same thing

These two assertions:

```java
assertThrows(AccessDeniedException.class,
        () -> store.save(input));
```

and

```java
mvc.perform(multipart("/api/documents").file(file))
   .andExpect(status().isInternalServerError());
```

sit at two different boundaries. The first uses fake I/O to prove **the store's reaction** to `AccessDeniedException`; the second uses a mocked store to prove **MVC exception mapping**. Only a full integration test with real NIO and proper fault injection across wired beans tests the full chain together. Never report "production Windows/Linux storage permissions verified" solely because these two tests pass.

Similarly, `@SpringBootTest + @AutoConfigureMockMvc` wires real beans yet **opens no TCP socket**. To test servlet container multipart size limits, chunked/truncated uploads, real client disconnects, or proxy timeouts, run with `RANDOM_PORT` or a production-like environment.

## 36. Common anti-patterns

| Anti-pattern | Why it is wrong | Replacement |
|---|---|---|
| `Files.copy(input, finalPath)` ignoring input | Stream may stay open; final file may be partial | `try-with-resources` + staging |
| Catching `IOException` and returning 201 | False success with corrupt/partial data | Propagate/map error and clean up |
| Using `MultipartFile.getOriginalFilename()` as `Path` | Path traversal / collisions | Server-generated ID |
| `new File("/tmp/shared.txt")` in tests | Cross-test collisions | JUnit `@TempDir` |
| Testing only the happy path | Misses leaks and partial data | Failure matrix |
| Using `chmod` to force `AccessDenied` on all CI | Non-portable / root bypasses it | Fault-injecting I/O adapter |
| Mapping every `AccessDeniedException` to HTTP 403 | Confuses OS errors with app authZ | Explicit error sources/contracts |
| `catch(IOException ignored)` when deleting temp | Hides orphan accumulation | Suppressed exceptions + metrics/janitor |
| Moving to final before closing input/output | Close failures occur after publication | Close before promoting |
| Ignoring `OutputStream.close()` failures | Bytes may fail to flush/commit | Propagate failure |
| Reading GB files with `readAllBytes()` | RAM exhaustion | Bounded streaming |
| Leaving `Files.list/walk` unclosed | Directory handle leaks | `try-with-resources` |
| Assuming `resolve(userPath).normalize()` is enough | Symlinks and TOCTOU still exist | Secure directory/ACL strategy |
| `@WebMvcTest` passes → TCP parser tested | Mock multipart bypasses network parsing | Real HTTP test |
| Deleting entire storage root after every test | Breaks concurrent tests | `@TempDir` / test-owned prefix |
| Immediately deleting every `.part` file | Deletes live uploads in flight | Lease/age/ownership janitor |
| Retrying uploads without idempotency | Creates duplicate documents | Idempotency keys / registry |
| Asserting exact OS error messages | Provider/platform-specific | Assert exception type + contract |
| Using production credentials/paths in tests | Risks real data | Test-only temp/IAM accounts |

## 37. Symptom-based troubleshooting

| Symptom | What to investigate |
|---|---|
| `.part` files left behind after copy failure | Cleanup skipped, delete threw, stage path untracked |
| HTTP 201 returned yet file unreadable | Returned before close/promote; move/provider failed |
| Tests fail intermittently on Windows | Unclosed input or `Files.list` stream; antivirus lock |
| Oversized uploads still accepted | Configured only multipart parser limit without store bound (or vice versa) |
| API returns 403 when volume is unwritable | `AccessDeniedException` mapped at wrong layer |
| Error response leaks `/srv/private` | Exception message or raw stack trace serialized |
| `"abc"` becomes `"ab"` after error | Partial copy was published directly |
| Mockito permission test green, prod fails | Unit reaction ≠ real OS ACLs or IAM config |
| Every retry adds another UUID file | Missing idempotency key |
| 5 MB upload passes MockMvc, prod fails 413 | `MockMultipartFile` skips real parser/proxy |
| File vanishes after cleanup race | Janitor deleted an active stage |
| `NoSuchFileException` instead of `AccessDeniedException` | Provider/FS permission semantics differ |
| JUnit `@TempDir` fails to delete | Open handles, unclosed `Files.walk`, external process lock |
| Close exception hides copy exception | Cleanup/`finally` failed to preserve suppressed errors |
| `Files.move` succeeds then file lost on crash | Missing `fsync`/durability contract |
| Symlink under root reads outside root | Untrusted directory, missing `NOFOLLOW`/secure directory checks |
| Account A reads Account B's document | Missing Spring Security object-level authorization |
| Reused Spring context points to deleted temp dir | `@TempDir` lifecycle mismatches cached context |

### 37.1. Debugging workflow

1. **Start at the symptom:** wrong HTTP status, partial file, leaked stream, or OS permission error?
2. Identify **which layer failed:** multipart parser, MVC, storage logic, filesystem, or cloud SDK.
3. Identify who owns `InputStream`/`OutputStream` and when `close()` runs.
4. Capture primary and suppressed exceptions without logging secrets.
5. Inspect staging and final files via `@TempDir` or test-owned prefixes.
6. Use a fake I/O adapter to inject the exact exception deterministically.
7. If the bug only appears on Windows or containers, run matching provider-specific tests.
8. Check whether cleanup could delete another worker's resources.
9. Check retries, idempotency, and locks when requests succeed right before a client timeout.
10. Re-verify public error contracts, logs, and janitor operations.

## 38. Practice exercises

### A. Stream read fails on the second byte

An `InputStream` yields one byte and then throws `IOException`. If the service skips staging and copies directly to `finalPath`, what happens? Write a unit test with a fake stream asserting the input closed and no staging file remains.

**Answer:** It can leave a corrupt 1-byte file if cleanup is missing. Use staging + `try-with-resources` + `finally` cleanup, and never promote on failure.

### B. Directory permissions

A server inside a Docker container lacks write permission on a mounted volume, so NIO throws `AccessDeniedException` creating the temp file. Should an authenticated user receive HTTP 403 or 500/503 per storage contract?

**Answer:** This is a server infrastructure/OS error, not a user lacking app permissions. The sample returns 500 with a neutral error code while logging safe diagnostics for operators.

### C. Move fails

Copying all bytes and closing both streams succeed, yet `move` from staging to final throws `IOException`. What should be tested?

**Answer:** No 201 response, no published final ID, staging deletion attempted, and original error preserved; inject the move failure with Mockito.

### D. Cleanup also fails

An upload fails while writing and deleting the temp file fails too. With `finally { Files.delete(temp); }`, what gets masked?

**Answer:** The delete `IOException` masks the write error. Save `primary` and call `addSuppressed(cleanup)`, or structure `AutoCloseable` resources cleanly.

### E. Input close fails

The server moved to final first, and then `InputStream.close()` threw `IOException`. The client retries, creating duplicates. How do you fix the ordering?

**Answer:** Close source and output before promoting; for distributed retries, pair with idempotency keys too.

### F. Output close fails

Copying finishes, yet `OutputStream.close()` throws `IOException` on flush/storage error. Should 201 be returned?

**Answer:** Not under the demo contract; treat close failures as failures, clean up staging, and surface the error.

### G. Permission tests on Windows

A test calls `Files.setPosixFilePermissions`. On Windows it throws `UnsupportedOperationException`. What should you do?

**Answer:** Unit-test `AccessDenied` via a mocked I/O adapter; guard OS-specific POSIX or Windows ACL tests behind assumptions on appropriate runners.

### H. Handle leak from `Files.list`

A test calls `Files.list(root).count()` without closing the stream. Why can that break test teardown on Windows?

**Answer:** The directory stream holds an open OS handle until closed; wrap `Stream<Path>` in `try-with-resources`.

### I. Dangerous filenames

A client sends `../../application.yml` as the multipart filename. If the server used the raw filename, what are the risks and how do you test against them?

**Answer:** Path traversal and overwrites; generate server-side UUIDs, validate IDs and app-owned roots, add negative traversal tests, and verify zero files exist outside the root.

### J. Where did 413 come from?

MockMvc uploads 2 MB while `spring.servlet.multipart.max-file-size` is 1 MB, yet the request still enters the controller. Why?

**Answer:** Mock multipart requests do not execute the real network parser. Verify store bounds in unit/full-context MockMvc tests, and verify parser limits with real HTTP server tests.

### K. Returning a 2 GB `byte[]`

A service calls `Files.readAllBytes` on a 2 GB file and returns `ResponseEntity<byte[]>`. What is the risk?

**Answer:** Heap exhaustion / OOM. Use bounded streaming and test client disconnects and resource closure; the sample supports ≤1 MiB only.

### L. S3 permissions

The app lacks `s3:PutObject`; the SDK throws a cloud 403. Should that automatically become a Spring Security 403 for the end user?

**Answer:** Not by default. That is a service/role IAM failure; public error contracts and operational remediation differ from user authorization.

### M. Crash mid-copy

The process is killed before `finally`, leaving `.part` files behind. Who cleans them up without deleting active uploads?

**Answer:** A janitor using ownership, leases, age thresholds, and monitoring rather than blindly deleting all staging files.

### N. "Atomic" filesystem moves

You call `Files.move(stage, final)` assuming readers never see partial state on any filesystem. Is that guaranteed?

**Answer:** No. Atomic renames require `ATOMIC_MOVE` where supported by the provider, alongside separate durability, idempotency, and recovery contracts.

### O. Asserting zero side effects on denied HTTP requests

Alice is unauthorized to read Bob's document, yet the controller calls `storage.readBytes` before checking permissions and then returns 403. Is asserting 403 enough?

**Answer:** No. Assert zero storage calls and zero leaked bytes; authorization must precede I/O.

### P. `InputStream` ownership

A library method accepts an `InputStream` whose docs state the caller retains ownership. May the method close it anyway?

**Answer:** No. Closing belongs to the ownership contract; the demo closes only because it explicitly claims ownership. Test that callers can continue using borrowed streams.

## 39. End-of-lesson checklist

- [ ] I can distinguish `IOException`, `AccessDeniedException`, `NoSuchFileException`, and `FileSystemException`.
- [ ] I never confuse OS permission denials with HTTP authentication/authorization denials.
- [ ] Method contracts explicitly state who owns `InputStream` and who closes it.
- [ ] `OutputStream` and `InputStream` close on success and every failure path.
- [ ] Closing output/input happens **before publishing** the final object.
- [ ] `try-with-resources` wraps streams, readers/writers, and `Files.list`/`walk`.
- [ ] I understand suppressed exceptions and never let cleanup errors mask primary errors.
- [ ] Byte limits are enforced when reading/writing untrusted inputs.
- [ ] Staging files are used instead of writing straight to final filenames.
- [ ] Copy/write/close/move failures never return success.
- [ ] Cleanup removes staging strictly within resource ownership.
- [ ] Cleanup failures emit logs/metrics and are preserved in the thrown error.
- [ ] Never deletes staging or final files belonging to other requests or tests.
- [ ] Generated final names never come from `originalFilename`.
- [ ] IDs/paths are validated; roots are app-owned directories.
- [ ] Symlinks/TOCTOU/ACLs are evaluated whenever other actors could modify the root.
- [ ] Tests use `@TempDir` rather than machine-wide hardcoded paths.
- [ ] Permission failures are mocked/fault-injected for cross-platform CI.
- [ ] OS-specific permission tests use assumptions rather than running blindly.
- [ ] Tests assert both stream closure and absence of leftover staging files.
- [ ] Tests do not assert exact OS-localized exception messages.
- [ ] MockMvc errors return safe status codes and payloads without leaking internal paths.
- [ ] `MockMultipartFile` is never mistaken for a real multipart parser.
- [ ] Full-context integration tests exercise real NIO inside a temp directory.
- [ ] HTTP 401/403 and file ownership are tested separately in multi-user apps.
- [ ] Large files are never buffered unboundedly into RAM.
- [ ] Download streaming defines policies for client disconnects and committed responses.
- [ ] Move atomicity and `fsync` durability are never assumed from ordinary `Files.move`.
- [ ] Retries/idempotency are handled when clients time out after publishing.
- [ ] Crash cleanup, janitors, and staging retention have explicit designs.
- [ ] Logs never leak credentials, private paths, or sensitive data.
- [ ] Resource pools and remote streams close per SDK contracts.
- [ ] QA summaries clearly distinguish code reviews, simulated I/O failures, and real OS/HTTP runs.

**Conclusion:** Integration testing for files and streams does not end at "read/write succeeded." A reliable design verifies **failure causes, post-failure resource state, and client contracts**. Combine `try-with-resources`, staging files, close-before-publish, bounded copying, and cleanup preserving suppressed exceptions; use `@TempDir` for real local filesystems and a fake I/O adapter to inject permission/read/write/move failures portably across OSes. `@WebMvcTest` protects error mapping, while full-context and real HTTP/volume tests cover deeper boundaries. Never equate a simulated `AccessDeniedException` test with verified real-deployment permissions, and never rely on Java `finally` to clean up after crashes.

### Official references

- Java SE 17 — `Files`, copy/move/createTempFile/newInputStream/newOutputStream: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html
- Java SE 17 — `AccessDeniedException` / `FileSystemException`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/AccessDeniedException.html
- Java SE 17 — `Throwable` suppressed exceptions: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html
- Java Tutorials — `try-with-resources` and suppressed exceptions: https://docs.oracle.com/javase/tutorial/essential/exceptions/tryResourceClose.html
- Spring Framework 6.2 — `MockMvc` request builders, multipart simulation: https://docs.spring.io/spring-framework/reference/6.2/testing/spring-mvc-test-framework.html
- Spring Boot 3.5 — Testing Spring Boot applications, `@WebMvcTest`, and `MockMvc`: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Getting Started — Uploading Files, `MultipartFile`, and `MockMvc` tests: https://spring.io/guides/gs/uploading-files/
- Spring Framework 6.2 — `MultipartFile` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/multipart/MultipartFile.html
- JUnit Jupiter — `@TempDir` temporary directories: https://junit.org/junit5/docs/current/user-guide/#writing-tests-built-in-extensions-TempDirectory
- OWASP — File Upload Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html