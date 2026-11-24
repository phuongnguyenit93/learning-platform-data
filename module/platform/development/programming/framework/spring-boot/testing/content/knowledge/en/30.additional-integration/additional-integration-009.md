# Object Storage or External Filesystems Substituted at the Right Boundary

In the **Additional integration** group of the **Spring Boot - testing** module, an upload/download feature may store contents in Amazon S3, an S3-compatible object storage API, Azure Blob Storage, Google Cloud Storage, or a directory on a local disk or NFS/SMB mount. If unit tests have to log into the cloud, find a pre-created bucket, or write to a shared production-like directory, **the test boundary is in the wrong place**. Conversely, if every test merely mocks `S3Client.putObject(...)` without ever exercising bucket/key configuration, region, credentials, streaming, or status codes, **the real integration has not been verified**.

This lesson presents an easily swappable architecture and a multi-layer testing strategy:

- **Business layer:** depends on a `BlobStore` interface (port) rather than the AWS SDK or `java.nio.file.Files`. Unit tests use Mockito or an in-memory fake; **no network or disk needed**.
- **HTTP layer:** uses `MockMvc` to verify upload/download, status codes, headers, and bodies, mocking `AssetService` when testing the controller slice alone.
- **Application flow:** runs the real controller + service inside Spring Boot while swapping **only the external boundary `BlobStore`** for an in-memory test bean. This verifies internal wiring, **without pretending to test S3**.
- **Filesystem adapter:** uses JUnit `@TempDir` and real filesystem I/O without touching production directories or volumes.
- **Object storage adapter:** uses `LocalStackContainer` with a real `S3Client` to verify `PutObject/GetObject`, endpoint overrides, bucket/key handling, and binary round-trips. This is an integration/contract test against an S3 emulator—**not equivalent to production IAM, latency, quotas, or every AWS S3 behavior**.
- **Target environment testing:** when NFS/SMB permissions, network timeouts, IAM, encryption, versioning, or pre-signed URLs matter, run tests in a properly permissioned staging/ephemeral environment with explicit contracts.

The examples use **Java 17+, Spring Boot 3.5.x, JUnit Jupiter, MockMvc, Mockito, AWS SDK for Java v2, and Testcontainers 1.x**. A small Java SE program includes `javac`/`java` commands with deterministic stdout. Sample classes enforce minimal conventions: random object keys, a 1 MiB payload cap, and `application/octet-stream` downloads. These limits keep the boundary clear and are **not a complete design for large-file storage products**.

## 1. What does "substituting at the right boundary" mean?

An application typically has this flow:

```text
HTTP POST /assets                  HTTP GET /assets/{key}
          |                                    |
          v                                    v
     AssetController                    AssetController
          |                                    |
          v                                    v
       AssetService  <--- business rules ---> AssetService
          |                                    |
          +------------ BlobStore -------------+
                             |
                    Implementation adapter
                  /                     \
                 v                       v
       DiskBlobStore                S3BlobStore
      java.nio.file.*                AWS S3Client
                 |                       |
                 v                       v
         Local/NFS/SMB                  S3 API
            filesystem               (AWS/LocalStack)
```

The **port (interface)** expresses the application's need in business terms: store bytes under a key and read them back. Adapters translate that need into `Files` or S3 SDK calls. Dependencies point from the application service toward the **port**, never from the service directly to AWS packages.

With this architecture:

1. Service unit tests verify validation, key generation, and delegation using a mock `BlobStore`.
2. Disk adapter tests verify `Files.move`, file contents, missing files, and traversal protection inside a temporary directory.
3. S3 adapter tests verify real AWS SDK interactions against an S3-compatible container service.
4. HTTP tests verify status codes, bodies, and headers without buckets or credentials.
5. Application wiring tests run through HTTP to the real service while substituting a fake at the port; this verifies where the **seam** sits in the Spring context.

**Do not** let `AssetService` call `S3Client` directly, compute `Path.resolve(...)`, or read `AWS_ACCESS_KEY_ID`. Doing so mixes business policy with infrastructure, making faults hard to isolate and risking accidental calls to real environments.

## 2. Comparing test layers

| Test layer | Substitutes | What it verifies | What it does not verify |
| --- | --- | --- | --- |
| Service unit | Mock `BlobStore` | Rules, keys, bytes, exception propagation | Disk/S3 protocols |
| Controller slice | Mock `AssetService` | Routes, multipart binding, HTTP responses/advice | Service rules and adapters |
| Spring flow | Fake `BlobStore` | Real controller + service + DI/wiring | Filesystem or S3 I/O |
| Filesystem integration | **Real** `@TempDir` directory | Filenames/keys, bytes, atomic replacement fallback, missing files | Production NFS/SMB/permissions |
| S3 integration | S3 API in LocalStack | SDK, bucket/key, PUT/GET, networking, test auth | Real AWS IAM, bucket policies/KMS, cloud latency |
| Environment contract | Staging/ephemeral storage | Permissions, region, TLS, encryption/presigned URLs/quotas | Scenarios omitted from the test |

**Two common mismatches:**

- Mocking `AssetService` itself in a **service unit test** means you are not testing business logic; use the real service + mocked port.
- Using `@TempDir` to claim "S3 works" is false: it only tests the filesystem adapter. Protecting S3 integration requires tests exercising the real S3 API or an S3-compatible test server.

Which layers to run depends on the contract. Not every PR needs live AWS staging tests; most logic is checked quickly by unit/adapter tests, while CI integration jobs cover protocols and wiring.

## 3. Object storage is not a filesystem with real directories

S3-style object stores organize objects by **bucket + key**, lacking directory trees, renames, and locking semantics like `java.nio.file.Path`:

| Concept | Filesystem | S3-style object store |
| --- | --- | --- |
| Addressing | Root directory + file path | Bucket + object key |
| Writing | File write/rename, filesystem semantics | HTTP PUT object/API |
| Reading | File read/open stream | GET Object or signed URL |
| Directory names | Real directory entries | Key prefixes; "folders" are usually conventions |
| Rename | Move/rename operation; atomicity varies by FS | Typically copy + delete, not atomic rename |
| Overwrite | Depends on move/write flags and OS | PUT with same key replaces object (or adds version if versioned) |
| Listing | Directory traversal | LIST objects with pagination/permissions |
| Permissions | OS accounts/ACLs/volumes | IAM/bucket policies/credentials/KMS |
| Deletion | Delete file | Delete Object, or delete markers under versioning |
| Shared DB transactions | None built in | None built in |

**Do not assume "S3 is eventually consistent so tests must sleep."** Amazon S3 provides strong read-after-write consistency for PUT/DELETE and LIST under documented conditions; however, other S3-compatible stores, NFS gateways, or providers may differ. Always test the **actual provider and contract** rather than assuming universal behavior across all object stores.

In this lesson, the port exposes only `put(key, bytes)` and `get(key)`. It does not pretend to emulate a full `java.nio.file.FileSystem`. Features like pre-signed URLs, multipart uploads, large streaming, object tagging, ETags, retention, and versioning need **explicit port contracts**, never tacked onto a fake ad hoc just to pass tests.

## 4. Defining a clear `BlobStore` contract

A sound port states clearly:

- Keys are **application-generated**; never use client filenames as paths or keys directly.
- Inputs and outputs are byte arrays; payloads may contain UTF-8 Unicode or arbitrary binary data.
- `get(key)` returns `Optional.empty()` **only when the object genuinely does not exist**.
- Permission denied, timeouts, disk-full, DNS failures, or missing buckets must surface as **failures**, never turned into `Optional.empty()`.
- Storage does not enforce business policies on size, MIME type, or tenant; the service enforces business rules, while the adapter enforces path/protocol safety.
- `put` with an existing key overwrites contents in both sample adapters; this is an **overwrite contract**. Systems requiring immutable objects must update the port to reject overwrites or use conditional writes.
- Do not promise atomic transactions shared with a database or cross-client thread-safe consistency without designing and testing them explicitly.
- Bounded memory buffers: the demo caps at 1 MiB; larger data requires streaming, backpressure, or multipart uploads.

### File: `BlobStore.java`

Create `src/main/java/example/storage/BlobStore.java`:

```java
package example.storage;

import java.io.IOException;
import java.util.Optional;

public interface BlobStore {
    void put(String key, byte[] bytes) throws IOException;

    Optional<byte[]> get(String key) throws IOException;
}
```

**Why does the interface declare `IOException`?** Disk I/O throws checked exceptions. The S3 adapter **wraps SDK runtime failures into `IOException`** so the application handles unavailable storage uniformly. This is an illustrative choice; production systems may define an unchecked `StorageUnavailableException` distinguishing retryable, not-found, conflict, auth, and provider errors.

Never expose `S3Exception`, `Path`, or `ResponseInputStream` in the service API if adapters must remain swappable. When contracts need metadata or streaming, model typed inputs/outputs right on the port instead of buffering unbounded byte arrays.

## 5. Key validation sits at the I/O gate

Keys are randomly generated by the service, yet adapters might still be called from elsewhere; therefore **both the service and adapters validate keys**.

Create `src/main/java/example/storage/ObjectKeys.java`:

```java
package example.storage;

public final class ObjectKeys {
    private ObjectKeys() {
    }

    public static void requireValid(String key) {
        if (key == null
                || !key.matches("[a-z0-9-]{1,80}")) {
            throw new IllegalArgumentException(
                    "invalid object key");
        }
    }
}
```

The demo convention **intentionally forbids dots, forward slashes, and backslashes**. Lowercase/hyphenated UUID keys pass; `../etc/passwd`, `a/b`, and `C:\\secret` are rejected. Without path separators, the filesystem adapter never needs to resolve nested directories or handle traversal through user filenames.

**This is only partial protection:** if the filesystem root is a shared directory where an attacker can plant symlinks/hardlinks or swap mounts between check and read, a key regex cannot stop race/symlink attacks. An app's storage root must be a **private, permission-controlled directory** where untrusted users cannot create or alter entries. Where untrusted actors share write access, use sandboxes, secure directory descriptors, and a stronger threat model.

Never use `MultipartFile.getOriginalFilename()` or any path from an HTTP client as an object key. Original filenames are **untrusted metadata** only.

## 6. `AssetService`: business logic unaware of AWS SDK or `Files`

Create `src/main/java/example/storage/AssetService.java`:

```java
package example.storage;

import java.io.IOException;
import java.util.Optional;
import java.util.UUID;

import org.springframework.stereotype.Service;

@Service
public class AssetService {
    public static final int MAX_BYTES = 1024 * 1024;

    private final BlobStore store;

    public AssetService(BlobStore store) {
        this.store = store;
    }

    public String save(byte[] content) throws IOException {
        if (content == null
                || content.length == 0
                || content.length > MAX_BYTES) {
            throw new IllegalArgumentException(
                    "invalid asset size");
        }

        String key = UUID.randomUUID().toString();
        store.put(key, content.clone());
        return key;
    }

    public Optional<byte[]> read(String key)
            throws IOException {
        ObjectKeys.requireValid(key);
        return store.get(key).map(data -> data.clone());
    }
}
```

Inspect this file to see the **clean boundary**:

- The service enforces size limits, generates keys, and calls the port.
- The service **has zero imports** from `software.amazon.awssdk.*` or `Files.*`, and reads neither credentials nor absolute filesystem paths.
- `UUID.randomUUID()` prevents key collisions across test methods; never treat this identifier as an authorization token or capability grant.
- `content.clone()` on put and `data.clone()` on read make defensive copies so fakes/adapters cannot share mutable byte arrays and produce false test passes.
- Key validation before invoking the adapter stops invalid keys/paths from reaching infrastructure.
- The example omits database metadata, owner/tenant checks, MIME sniffing, malware scanning, and transactions. Real apps with metadata DBs must test consistency and orphan compensation when an upload succeeds yet the DB commit fails.

**Business rule ≠ provider policy.** The 1 MiB limit in the service is a domain rule in this lesson; Spring MVC multipart limits, reverse proxy limits, and provider quotas are separate layers. Never rely solely on a service-layer check when oversized requests may already be buffered upstream.

## 7. `FileBlobStore`: real filesystem adapter with a controlled root

Create `src/main/java/example/storage/FileBlobStore.java`:

```java
package example.storage;

import java.io.IOException;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.Optional;

public final class FileBlobStore implements BlobStore {
    private final Path root;

    public FileBlobStore(Path root) throws IOException {
        this.root = root.toAbsolutePath().normalize();
        Files.createDirectories(this.root);
    }

    private Path resolve(String key) {
        ObjectKeys.requireValid(key);
        Path target = root.resolve(key).normalize();

        if (!target.getParent().equals(root)) {
            throw new IllegalArgumentException(
                    "object outside storage root");
        }

        return target;
    }

    @Override
    public void put(String key, byte[] bytes)
            throws IOException {
        Path target = resolve(key);
        Path temp = Files.createTempFile(
                root, ".asset-", ".tmp");

        try {
            Files.write(temp, bytes);

            try {
                Files.move(
                        temp, target,
                        StandardCopyOption.ATOMIC_MOVE,
                        StandardCopyOption.REPLACE_EXISTING);
            } catch (AtomicMoveNotSupportedException error) {
                Files.move(
                        temp, target,
                        StandardCopyOption.REPLACE_EXISTING);
            }
        } finally {
            Files.deleteIfExists(temp);
        }
    }

    @Override
    public Optional<byte[]> get(String key)
            throws IOException {
        Path target = resolve(key);

        if (Files.isSymbolicLink(target)) {
            throw new IOException(
                    "symbolic links not allowed");
        }

        try {
            return Optional.of(
                    Files.readAllBytes(target));
        } catch (NoSuchFileException missing) {
            return Optional.empty();
        }
    }
}
```

**What this adapter guarantees within the demo scope:**

- The root is normalized and created on construction; keys are validated before resolving.
- Writes go to a temporary file **in the same target directory**, then move to the final key. Where the filesystem supports `ATOMIC_MOVE`, readers never observe a half-written target file; where unsupported, the `REPLACE_EXISTING` fallback **does not guarantee atomic renames**. This limitation is explicit—do not label both paths atomic.
- `finally` cleans up the temp file if writing or moving fails.
- Missing files return `Optional.empty()`; other `IOException` failures are not masked as missing.
- Symbolic link targets are explicitly rejected on read, though **this does not claim full TOCTOU protection** if an attacker can mutate the root.
- This adapter buffers entire byte arrays in memory, matching the demo's 1 MiB cap. Multi-GiB files require streaming, limits, and backpressure instead of `readAllBytes`.

**Regarding NFS/SMB:** `Files.move(ATOMIC_MOVE)` may be unsupported or have different consistency/locking semantics. Local `@TempDir` tests **do not prove** real network share behavior, remote permissions, mount outages, oplocks, latency, or cross-host locking. Add dedicated integration jobs against a configured mount when that is part of the contract.

## 8. `S3BlobStore`: adapter using the real AWS SDK

Create `src/main/java/example/storage/S3BlobStore.java`:

```java
package example.storage;

import java.io.IOException;
import java.util.Optional;

import software.amazon.awssdk.core.exception.SdkException;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.NoSuchKeyException;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;

public final class S3BlobStore implements BlobStore {
    private final S3Client client;
    private final String bucket;

    public S3BlobStore(S3Client client, String bucket) {
        this.client = client;
        this.bucket = bucket;
    }

    @Override
    public void put(String key, byte[] bytes)
            throws IOException {
        ObjectKeys.requireValid(key);

        try {
            client.putObject(
                    PutObjectRequest.builder()
                            .bucket(bucket)
                            .key(key)
                            .build(),
                    RequestBody.fromBytes(bytes));
        } catch (SdkException error) {
            throw new IOException(
                    "object storage write failed", error);
        }
    }

    @Override
    public Optional<byte[]> get(String key)
            throws IOException {
        ObjectKeys.requireValid(key);

        try {
            byte[] bytes = client.getObjectAsBytes(
                    GetObjectRequest.builder()
                            .bucket(bucket)
                            .key(key)
                            .build())
                    .asByteArray();

            return Optional.of(bytes);
        } catch (NoSuchKeyException missing) {
            return Optional.empty();
        } catch (SdkException error) {
            throw new IOException(
                    "object storage read failed", error);
        }
    }
}
```

This is a **real AWS SDK v2 adapter**, not a mock:

- `putObject` uses `bucket`, `key`, and body bytes without local paths.
- `getObjectAsBytes` calls the S3 API; `NoSuchKeyException` maps to empty per contract. Other SDK errors (such as `AccessDenied` or network errors) are wrapped in `IOException`.
- The adapter **never** creates buckets, deletes buckets, or falls back to the local filesystem when credentials fail; bucket provisioning belongs to infrastructure.
- Production setups must configure the SDK HTTP client, timeouts/retry policies, connection pools, region, credentials, and `S3Client` shutdown lifecycle, plus streaming/multipart uploads for large objects.
- This illustrative port omits content-type, checksums, encryption, object tags, and metadata; when required, model typed request/response objects and **test metadata explicitly**.
- Client IAM permissions should allow only required actions and bucket/key prefixes; avoid over-privileged cloud accounts in apps.

**Never use `S3BlobStore` inside service unit tests.** Unit tests swap out the port; S3 integration tests run the real adapter against LocalStack.

## 9. Spring configuration picks the right adapter without silent fallbacks

Create `src/main/java/example/storage/BlobStorageConfiguration.java`:

```java
package example.storage;

import java.io.IOException;
import java.nio.file.Path;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import software.amazon.awssdk.services.s3.S3Client;

@Configuration(proxyBeanMethods = false)
public class BlobStorageConfiguration {

    @Bean
    @ConditionalOnProperty(
            name = "app.storage.provider",
            havingValue = "disk",
            matchIfMissing = true)
    BlobStore diskBlobStore(
            @Value("${app.storage.root:build/blob-data}")
                    String root) throws IOException {
        return new FileBlobStore(Path.of(root));
    }

    @Bean(destroyMethod = "close")
    @ConditionalOnProperty(
            name = "app.storage.provider",
            havingValue = "s3")
    S3Client s3Client() {
        return S3Client.create();
    }

    @Bean
    @ConditionalOnProperty(
            name = "app.storage.provider",
            havingValue = "s3")
    BlobStore s3BlobStore(
            S3Client client,
            @Value("${app.storage.bucket}")
                    String bucket) {
        return new S3BlobStore(client, bucket);
    }
}
```

Values of `app.storage.provider`:

| Value | Application beans created | Environment requirement |
| --- | --- | --- |
| Property omitted | `diskBlobStore` | Default root `build/blob-data` |
| `disk` | `diskBlobStore` | Write permissions / configured directory |
| `s3` | `s3Client` + `s3BlobStore` | AWS region, credential chain, bucket |
| `memory` | **Creates no production adapter** | Boots only when tests import a fake bean |

**Why doesn't `memory` fall back to disk?** Flow tests set `app.storage.provider=memory` and provide a test-only `BlobStore`. If the fake bean is missing, Spring fails to satisfy `AssetService`'s dependency and **fails startup loudly** instead of silently writing to the default disk directory—a safe design that catches missing test seams right away.

When production selects `s3`, `S3Client.create()` uses the default credential/region provider chain; configure region and identity via deployment settings (e.g., workload identity), never hardcoded access keys. `@Bean(destroyMethod="close")` closes the SDK client when the Spring context shuts down.

**Warning about default disk storage:** `build/blob-data` is a local project demo path, **not a recommended persistent location for production containers**. In Kubernetes, container filesystems are often ephemeral. Production needs explicit volume mounts/storage roots with proper backups, permissions, and quotas.

## 10. Spring Boot app and REST API with clean boundaries

### `AssetApplication.java`

Create `src/main/java/example/storage/AssetApplication.java`:

```java
package example.storage;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AssetApplication {
    public static void main(String[] args) {
        SpringApplication.run(AssetApplication.class, args);
    }
}
```

### `AssetController.java`

Create `src/main/java/example/storage/AssetController.java`:

```java
package example.storage;

import java.io.IOException;
import java.net.URI;
import java.util.Map;
import java.util.Optional;

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
@RequestMapping("/assets")
public class AssetController {
    private final AssetService service;

    public AssetController(AssetService service) {
        this.service = service;
    }

    @PostMapping(
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<Map<String, String>> upload(
            @RequestPart("file") MultipartFile file)
            throws IOException {
        String key = service.save(file.getBytes());

        return ResponseEntity.created(
                URI.create("/assets/" + key))
                .body(Map.of("key", key));
    }

    @GetMapping("/{key}")
    public ResponseEntity<byte[]> download(
            @PathVariable String key)
            throws IOException {
        Optional<byte[]> result = service.read(key);

        if (result.isEmpty()) {
            return ResponseEntity.notFound().build();
        }

        return ResponseEntity.ok()
                .contentType(
                        MediaType.APPLICATION_OCTET_STREAM)
                .body(result.get());
    }
}
```

**Actual request flow:**

1. Servlet multipart handling reads the uploaded file; the controller passes bytes to the service.
2. The service validates size, generates a fresh key, and calls the port.
3. POST returns `201 Created`, `Location: /assets/{key}`, and a JSON key payload.
4. GET fetches bytes from the service/port and returns `application/octet-stream`; missing keys return 404.
5. Neither the controller nor the service imports the AWS SDK or `Files.*`.

**Never treat a UUID key as access control.** This demo API lacks authentication, tenant authorization, encryption, and ownership checks—production APIs must enforce authorization **before calling storage**. Never use `originalFilename` to determine object keys or paths either.

**Payload sizing:** because `MultipartFile.getBytes()` loads bytes into memory, configure multipart limits at both the reverse proxy and Servlet container (`spring.servlet.multipart.max-file-size` and `max-request-size`). The demo service rejects payloads larger than 1 MiB, yet that check runs **after** MVC buffers the upload. Larger files require streaming with explicit memory budgets.

### `BlobErrorAdvice.java`

Create `src/main/java/example/storage/BlobErrorAdvice.java`:

```java
package example.storage;

import java.io.IOException;
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class BlobErrorAdvice {

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<Map<String, String>> badInput() {
        return ResponseEntity.badRequest()
                .body(Map.of("error", "invalid input"));
    }

    @ExceptionHandler(IOException.class)
    public ResponseEntity<Map<String, String>> unavailable() {
        return ResponseEntity.status(
                        HttpStatus.SERVICE_UNAVAILABLE)
                .body(Map.of(
                        "error", "storage unavailable"));
    }
}
```

The advice never echoes raw paths, secrets, bucket names, or SDK exception messages in responses. Mapping `IOException → 503` is an **illustrative policy**; production apps should distinguish auth misconfiguration (normally non-retryable), throttling/transient storage outages (retryable), oversized uploads (413), unsupported media types (415), and unknown internal failures.

## 11. Java 17-compatible Gradle project

Layout:

```text
src/
├── main/java/example/storage/
│   ├── AssetApplication.java
│   ├── BlobStore.java
│   ├── ObjectKeys.java
│   ├── AssetService.java
│   ├── FileBlobStore.java
│   ├── S3BlobStore.java
│   ├── BlobStorageConfiguration.java
│   ├── AssetController.java
│   ├── BlobErrorAdvice.java
│   └── ObjectKeysDemo.java
└── test/java/example/storage/
    ├── AssetServiceTest.java
    ├── FileBlobStoreTest.java
    ├── AssetControllerTest.java
    ├── AssetFlowWithFakeStoreTest.java
    └── S3BlobStoreLocalStackTest.java
```

Create `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.0'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'

    implementation platform(
            'software.amazon.awssdk:bom:2.30.36')
    implementation 'software.amazon.awssdk:s3'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:localstack'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**Target versions:** Spring Boot 3.5.0, Java 17+, AWS SDK v2 BOM `2.30.36`, Testcontainers 1.x managed by the Spring Boot BOM. Teams using other versions must align dependencies and imports; Testcontainers 2.x may change artifact/module coordinates. Running Gradle commands requires a compatible Gradle Wrapper or installed Gradle; this build file does not generate `gradlew` automatically.

**Which tests require Docker?** Only `S3BlobStoreLocalStackTest` requires Docker/Testcontainers. Service unit tests, filesystem tests, MVC slice tests, and the Spring fake-flow test require neither AWS credentials nor Docker. Pulling the LocalStack image requires network access or an image cache in CI.

**Real AWS access keys are never needed for LocalStack tests.** LocalStack tests use container-supplied dummy credentials (worthless in production AWS), endpoint overrides, and path-style access. Never set `AWS_ACCESS_KEY_ID` pointing to a real account for these tests.

## 12. Service unit test: mocking the `BlobStore` port

Create `src/test/java/example/storage/AssetServiceTest.java`:

```java
package example.storage;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Optional;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

class AssetServiceTest {
    private final BlobStore store = mock(BlobStore.class);
    private final AssetService service =
            new AssetService(store);

    @Test
    void savesOpaqueKeyAndExactBytes() throws Exception {
        byte[] data = "Hello 😀".getBytes(
                StandardCharsets.UTF_8);

        String key = service.save(data);

        ObjectKeys.requireValid(key);

        ArgumentCaptor<byte[]> captured =
                ArgumentCaptor.forClass(byte[].class);

        verify(store).put(eq(key), captured.capture());

        assertArrayEquals(data, captured.getValue());
        assertNotSame(data, captured.getValue());
    }

    @Test
    void rejectsNullEmptyAndOversizedContent()
            throws Exception {
        assertThrows(
                IllegalArgumentException.class,
                () -> service.save(null));

        assertThrows(
                IllegalArgumentException.class,
                () -> service.save(new byte[0]));

        assertThrows(
                IllegalArgumentException.class,
                () -> service.save(
                        new byte[AssetService.MAX_BYTES + 1]));

        verifyNoInteractions(store);
    }

    @Test
    void returnsMissingWhenBackendReportsMissing()
            throws Exception {
        when(store.get("absent"))
                .thenReturn(Optional.empty());

        assertFalse(service.read("absent").isPresent());
        verify(store).get("absent");
    }

    @Test
    void returnsDefensiveCopyOfStoredBytes()
            throws Exception {
        byte[] actual = {0, 1, 2, -1};
        when(store.get("valid-key"))
                .thenReturn(Optional.of(actual));

        byte[] returned = service.read(
                "valid-key").orElseThrow();

        assertArrayEquals(actual, returned);
        assertNotSame(actual, returned);
    }

    @Test
    void rejectsPathLikeKeyBeforeCallingStore()
            throws Exception {
        assertThrows(
                IllegalArgumentException.class,
                () -> service.read("../other"));

        verifyNoInteractions(store);
    }

    @Test
    void propagatesStorageOutageInsteadOfReturning404()
            throws Exception {
        doThrow(new IOException("disk offline"))
                .when(store)
                .put(anyString(), any(byte[].class));

        assertThrows(
                IOException.class,
                () -> service.save(new byte[]{1, 2}));

        verify(store).put(
                anyString(), any(byte[].class));
    }
}
```

**Six JUnit test methods** verify business rules and port interactions without touching disk or S3:

- Generated keys are valid and random, never trusting client filenames.
- UTF-8 Unicode payloads pass through intact; the service clones arrays to prevent external mutation.
- Null, empty, and oversized payloads are rejected before touching storage.
- Not-found returns `Optional.empty()`, distinct from storage failures.
- Key `../other` is blocked before reaching the backend.
- `IOException` propagates to the application boundary instead of turning into a misleading 404.

**Why not mock `S3Client` in this class?** The service should know nothing about `S3Client`. Writing `verify(s3Client).putObject(...)` in a service test couples tests tightly to AWS and makes swapping backends painful. A separate adapter test covers AWS SDK mapping.

**When is a fake better than a mock?** When running multi-step workflows (upload then download) and asserting state semantics, an in-memory `MapBlobStore` fake behaves like real storage with far less manual stubbing; section 15 demonstrates this.

## 13. Filesystem integration: `@TempDir` tests real I/O

Create `src/test/java/example/storage/FileBlobStoreTest.java`:

```java
package example.storage;

import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.Optional;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class FileBlobStoreTest {
    @TempDir
    Path directory;

    @Test
    void roundTripsUnicodeBytesOnRealFilesystem()
            throws Exception {
        BlobStore store = new FileBlobStore(
                directory.resolve("objects"));

        byte[] original = "File 😀".getBytes(
                StandardCharsets.UTF_8);

        store.put("unicode-key", original);

        assertArrayEquals(
                original,
                store.get("unicode-key").orElseThrow());
    }

    @Test
    void missingFileReturnsEmptyOptional()
            throws Exception {
        BlobStore store = new FileBlobStore(
                directory.resolve("objects"));

        assertFalse(
                store.get("not-present").isPresent());
    }

    @Test
    void rejectsTraversalAndSlashSeparatedKeys()
            throws Exception {
        BlobStore store = new FileBlobStore(
                directory.resolve("objects"));

        assertThrows(
                IllegalArgumentException.class,
                () -> store.put("../escape", new byte[]{1}));

        assertThrows(
                IllegalArgumentException.class,
                () -> store.get("tenant/other"));
    }

    @Test
    void overwriteReplacesPreviousContents()
            throws Exception {
        BlobStore store = new FileBlobStore(
                directory.resolve("objects"));

        store.put("same-key", new byte[]{1, 2, 3});
        store.put("same-key", new byte[]{9});

        assertArrayEquals(
                new byte[]{9},
                store.get("same-key").orElseThrow());
    }

    @Test
    void independentRootsDoNotShareObjects()
            throws Exception {
        BlobStore first = new FileBlobStore(
                directory.resolve("first"));
        BlobStore second = new FileBlobStore(
                directory.resolve("second"));

        first.put("only-first", new byte[]{1});

        assertTrue(
                first.get("only-first").isPresent());
        assertFalse(
                second.get("only-first").isPresent());
    }
}
```

**Five integration methods** never mock `Files.*`; they execute real filesystem operations inside JUnit's `@TempDir`.

**Scope of evidence:**

- Directory creation, real byte PUT/GET, Unicode round-trip, and empty `Optional` on missing keys.
- Key validation blocking traversal and slashes.
- Overwrites and isolation between two storage roots.
- Never writes to global `/tmp`, home directories, or a developer's shared NFS mount.
- No `@SpringBootTest` needed because the adapter has no Spring dependency; plain JUnit runs fast with clear failure diagnostics.

**Limitation:** this is a local filesystem test. It does **not** verify NFS mount outages, SMB ACLs, cross-host locks, remote permissions, real network-share rename atomicity, or disk-full quotas. When production relies on those semantics, add tests on the target resource; `@TempDir` alone cannot prove a remote filesystem behaves like local disk.

## 14. MVC slice: mock the service because this tests the HTTP boundary

Create `src/test/java/example/storage/AssetControllerTest.java`:

```java
package example.storage;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Optional;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@WebMvcTest(AssetController.class)
class AssetControllerTest {
    @Autowired
    MockMvc mvc;

    @MockitoBean
    AssetService service;

    @Test
    void multipartUploadReturnsCreatedLocationAndKey()
            throws Exception {
        byte[] bytes = "data".getBytes(
                StandardCharsets.UTF_8);

        MockMultipartFile file = new MockMultipartFile(
                "file", "ignored-name.txt",
                "text/plain", bytes);

        when(service.save(any(byte[].class)))
                .thenReturn("stored-key");

        mvc.perform(
                multipart("/assets").file(file))
                .andExpect(status().isCreated())
                .andExpect(
                        header().string(
                                "Location", "/assets/stored-key"))
                .andExpect(
                        jsonPath("$.key").value("stored-key"));

        ArgumentCaptor<byte[]> captured =
                ArgumentCaptor.forClass(byte[].class);

        verify(service).save(captured.capture());
        assertArrayEquals(bytes, captured.getValue());
    }

    @Test
    void downloadReturnsBytesAsOctetStream()
            throws Exception {
        byte[] bytes = {0, 1, 2, -1};

        when(service.read("stored-key"))
                .thenReturn(Optional.of(bytes));

        mvc.perform(get("/assets/stored-key"))
                .andExpect(status().isOk())
                .andExpect(
                        content().contentType(
                                MediaType.APPLICATION_OCTET_STREAM))
                .andExpect(content().bytes(bytes));
    }

    @Test
    void missingObjectBecomes404() throws Exception {
        when(service.read("missing"))
                .thenReturn(Optional.empty());

        mvc.perform(get("/assets/missing"))
                .andExpect(status().isNotFound());
    }

    @Test
    void invalidContentBecomes400() throws Exception {
        when(service.save(any(byte[].class)))
                .thenThrow(new IllegalArgumentException(
                        "invalid size"));

        MockMultipartFile file = new MockMultipartFile(
                "file", "empty.txt",
                "text/plain", new byte[0]);

        mvc.perform(
                multipart("/assets").file(file))
                .andExpect(status().isBadRequest())
                .andExpect(
                        jsonPath("$.error").value(
                                "invalid input"));
    }

    @Test
    void storageIOExceptionBecomes503() throws Exception {
        when(service.read("stored-key"))
                .thenThrow(new IOException(
                        "backend unavailable"));

        mvc.perform(get("/assets/stored-key"))
                .andExpect(status().isServiceUnavailable())
                .andExpect(
                        jsonPath("$.error").value(
                                "storage unavailable"));
    }
}
```

**Five JUnit MVC methods** verify request binding, status codes, the `Location` header, `Content-Type`, binary responses, and API error mapping. They create neither disk files nor S3 objects.

**Mocking the right boundary:** in `@WebMvcTest(AssetController.class)`, the controller is real and `AssetService` is mocked. That fits because the goal is **only the HTTP contract**. When testing business rules, never mock the service—use service unit tests or the flow test below.

**Why `@MockitoBean`?** Spring Framework 6.2 / Spring Boot 3.5 provides this annotation for overriding beans in Spring test contexts. `@MockBean` is deprecated in newer Boot releases; use imports matching the project's version line. Never pull AWS S3 SDK classes into controller slices unnecessarily.

## 15. Full Spring flow with a fake placed at the external boundary

This is the centerpiece for **"substituting at the right boundary"**: both the controller and business service are **real**, and only `BlobStore` is replaced by an in-memory implementation **scoped to the test class**.

Create `src/test/java/example/storage/AssetFlowWithFakeStoreTest.java`:

```java
package example.storage;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(
        webEnvironment =
                SpringBootTest.WebEnvironment.MOCK,
        properties = "app.storage.provider=memory")
@AutoConfigureMockMvc
class AssetFlowWithFakeStoreTest {
    @Autowired
    MockMvc mvc;

    @Autowired
    ObjectMapper mapper;

    @Test
    void uploadThenDownloadThroughRealControllerAndService()
            throws Exception {
        byte[] bytes = "Real flow 😀".getBytes(
                StandardCharsets.UTF_8);

        MockMultipartFile file = new MockMultipartFile(
                "file", "user/../ignored.txt",
                "text/plain", bytes);

        MvcResult response = mvc.perform(
                multipart("/assets").file(file))
                .andExpect(status().isCreated())
                .andReturn();

        String key = mapper.readTree(
                        response.getResponse()
                                .getContentAsString())
                .get("key").asText();

        ObjectKeys.requireValid(key);

        mvc.perform(get("/assets/" + key))
                .andExpect(status().isOk())
                .andExpect(content().contentType(
                        MediaType.APPLICATION_OCTET_STREAM))
                .andExpect(content().bytes(bytes));
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class FakeStorageConfiguration {
        @Bean
        BlobStore memoryBlobStore() {
            return new MemoryBlobStore();
        }
    }

    static class MemoryBlobStore implements BlobStore {
        private final ConcurrentMap<String, byte[]> data =
                new ConcurrentHashMap<>();

        @Override
        public void put(String key, byte[] bytes)
                throws IOException {
            ObjectKeys.requireValid(key);
            data.put(key, bytes.clone());
        }

        @Override
        public Optional<byte[]> get(String key)
                throws IOException {
            ObjectKeys.requireValid(key);
            byte[] found = data.get(key);

            return found == null
                    ? Optional.empty()
                    : Optional.of(found.clone());
        }
    }
}
```

**One Spring integration method** exercises the full flow: `HTTP → controller → service → port fake → controller`. It proves:

- Spring component scanning and constructor injection wire the real beans together.
- The multipart controller invokes the real service, which generates a valid key.
- Unicode bytes are stored and retrieved through the fake honoring the port contract.
- A client filename intentionally containing `../` is **never used as an object key or path**.
- Setting `app.storage.provider=memory` disables both production disk and S3 beans, leaving the test-only `@Bean BlobStore` as the sole backend. If the fake bean is omitted, Spring startup fails due to a missing `BlobStore` instead of falling back to disk.
- The test requires no file permissions, AWS credentials, LocalStack endpoint, or network.

**What it does not prove:** real files were written, atomic rename is supported, or S3 requests succeed. Those belong to adapter tests. This is an **integration test with zero external I/O**, not an S3 integration test.

### Why is a fake different from a mock?

A Mockito mock returns canned values per stubbed call; the `MemoryBlobStore` fake maintains real state across `put` and `get`. Fakes fit multi-step **application workflows**, provided they obey the contract: missing returns `Optional.empty()`, arrays are cloned, invalid keys are rejected, and overwriting updates contents. An overly permissive fake (e.g., returning bytes for any key) lets broken flows pass falsely.

**Never place the fake as a `@Component` in `src/main`.** Keep it inside `src/test` (or test utilities) so it can never be deployed accidentally as a production storage option.

## 16. S3 integration with LocalStack Testcontainers and AWS SDK v2

Create `src/test/java/example/storage/S3BlobStoreLocalStackTest.java`:

```java
package example.storage;

import java.util.Optional;
import java.util.UUID;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.localstack.LocalStackContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.S3Configuration;
import software.amazon.awssdk.services.s3.model.CreateBucketRequest;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;

@Testcontainers
class S3BlobStoreLocalStackTest {
    private static final String BUCKET =
            "lesson-storage";

    @Container
    static LocalStackContainer localstack =
            new LocalStackContainer(
                    DockerImageName.parse(
                            "localstack/localstack:3.8.1"))
                    .withServices(
                            LocalStackContainer.Service.S3);

    private static S3Client client;
    private static BlobStore store;

    @BeforeAll
    static void createBucket() {
        client = S3Client.builder()
                .endpointOverride(
                        localstack.getEndpointOverride(
                                LocalStackContainer.Service.S3))
                .credentialsProvider(
                        StaticCredentialsProvider.create(
                                AwsBasicCredentials.create(
                                        localstack.getAccessKey(),
                                        localstack.getSecretKey())))
                .region(Region.of(
                        localstack.getRegion()))
                .serviceConfiguration(
                        S3Configuration.builder()
                                .pathStyleAccessEnabled(true)
                                .build())
                .build();

        client.createBucket(
                CreateBucketRequest.builder()
                        .bucket(BUCKET)
                        .build());

        store = new S3BlobStore(client, BUCKET);
    }

    @AfterAll
    static void closeClient() {
        if (client != null) {
            client.close();
        }
    }

    @Test
    void putAndGetRoundTripWithRealS3Api()
            throws Exception {
        String key = UUID.randomUUID().toString();
        byte[] bytes = {0, 1, 2, -1};

        store.put(key, bytes);

        assertArrayEquals(
                bytes, store.get(key).orElseThrow());
    }

    @Test
    void nonexistentKeyReturnsEmpty()
            throws Exception {
        String key = UUID.randomUUID().toString();

        assertFalse(store.get(key).isPresent());
    }

    @Test
    void invalidKeyIsRejectedBeforeS3Request()
            throws Exception {
        assertThrows(
                IllegalArgumentException.class,
                () -> store.put(
                        "../bad", new byte[]{1}));
    }
}
```

**Three integration methods** run a LocalStack container managed by JUnit Jupiter's extension per **test class**. Once started, the test builds an `S3Client` using LocalStack's **endpoint override**, region, and credentials, creates the test bucket, executes **real S3 API calls** through the SDK, and reads back bytes or confirms missing keys.

**How this differs from unit tests:**

- Real AWS SDK request serialization and HTTP client execution run.
- Bucket and object key rules are enforced by an S3-compatible server.
- Neither `putObject` nor `getObjectAsBytes` is mocked; real adapter code runs.
- `S3Client` is closed in `@AfterAll`; the static container stops automatically after the class finishes.
- Never hardcode `localhost:4566`, because mapped ports/hosts vary on CI and remote Docker daemons.
- Needs no production AWS credentials and never talks to public AWS endpoints.

**LocalStack limitations:** S3 emulation does not replace testing real IAM roles, bucket policies, KMS grants, endpoint TLS, network firewalls, object locks, cross-region replication, S3 Event Notifications, or cloud latency. When those contracts matter, run targeted tests in a controlled staging account/bucket with proper cleanup. Never create or delete test objects inside production buckets.

**Version note:** this test uses the Testcontainers 1.x artifact `org.testcontainers:localstack` and imports `org.testcontainers.containers.localstack.LocalStackContainer`. Testcontainers 2.x reorganizes modules and packages; align imports with your active BOM and docs without mixing versions.

## 17. Why mocking AWS `S3Client` alone is not enough

An adapter unit test might write:

```java
S3Client s3 = mock(S3Client.class);
S3BlobStore store = new S3BlobStore(
        s3, "lesson-storage");
store.put("abc", new byte[]{1});
verify(s3).putObject(
        any(PutObjectRequest.class),
        any(RequestBody.class));
```

This is an **illustrative snippet** needing Mockito imports. Its value is limited: it proves the adapter invokes the SDK method, yet **does not verify** the bucket/key in the request, body transmission, region/path-style config, permissions, or 404 handling. Verifying call counts without inspecting arguments passes even with `.bucket("wrong-bucket")`.

If you want an adapter unit test verifying request construction, use `ArgumentCaptor<PutObjectRequest>` to assert `bucket`, `key`, and metadata—yet still pair it with LocalStack or real S3 integration tests to exercise the protocol.

**Never mock static `Files.readAllBytes` in service unit tests**: that drags filesystem APIs into the service instead of placing them behind a port, making tests brittle and encouraging I/O-coupled designs.

## 18. Standalone Java SE program for key validation

Create `src/main/java/example/storage/ObjectKeysDemo.java`:

```java
package example.storage;

public class ObjectKeysDemo {
    public static void main(String[] args) {
        String safe = "abc-123";
        ObjectKeys.requireValid(safe);
        System.out.println("valid=" + safe);

        try {
            ObjectKeys.requireValid("../etc/passwd");
        } catch (IllegalArgumentException error) {
            System.out.println(
                    "rejected=" + error.getMessage());
        }
    }
}
```

With JDK 17+ from the project root:

```bash
javac -d out src/main/java/example/storage/ObjectKeys.java src/main/java/example/storage/ObjectKeysDemo.java
java -cp out example.storage.ObjectKeysDemo
```

**Exact** stdout:

```text
valid=abc-123
rejected=invalid object key
```

**Limitation:** this is a plain Java SE demo verifying the key allowlist; it starts no Spring context, reads no filesystem, and connects to no S3 endpoint. Use it to verify why raw filenames/paths must never enter the adapter directly—not as proof that uploads work.

## 19. Distinguishing mocks, fakes, local emulators, and production contracts

| Test double / environment | Lesson example | Strengths | Blind spots |
| --- | --- | --- | --- |
| Mockito mock | `mock(BlobStore.class)` | Verifies calls, arguments, thrown exceptions | Holds no real state |
| In-memory fake | `MemoryBlobStore` | Tests real `upload → download` flow | Lacks filesystem/S3 semantics |
| Local filesystem | `FileBlobStore(@TempDir)` | Real NIO I/O, easy cleanup | Not real NFS/SMB |
| LocalStack | `S3BlobStore + S3Client` | API integration without an AWS account | Omits full AWS IAM/KMS/quotas |
| AWS staging bucket | Deployment-controlled test | Production-like auth/region/behavior | Cost, security, cleanup, flaky remote calls |

### "Right boundary" depends on what you assert

- Testing controller routes: mock `AssetService`; no port needed.
- Testing service rules: mock/fake `BlobStore`; **real service**.
- Testing application orchestration: real controller + real service, fake at `BlobStore`.
- Testing disk adapter: real `FileBlobStore` + real `@TempDir`.
- Testing S3 adapter: real `S3BlobStore` + real `S3Client` + LocalStack.
- Testing production IAM/permissions: real staging provider with scoped identity; LocalStack is insufficient.

**Anti-pattern:** misconfiguring a test so it silently uses the default disk bean in the project directory when you intended to test the fake, simply because the provider property wasn't set. The flow test sets `app.storage.provider=memory` alongside a test bean so neither production disk nor S3 adapters match. To guard against accidental fallbacks, tests can assert there is exactly one `BlobStore` bean and check its class (`FileBlobStore`/`S3BlobStore`).

## 20. Test matrix for success, failures, and isolation

| Scenario | Service unit | MVC | Filesystem `@TempDir` | LocalStack S3 | Full flow fake |
| --- | --- | --- | --- | --- | --- |
| Valid upload | Yes | 201 status | Put bytes | PUT/GET | HTTP→service→fake |
| Existing download | Mocked result | 200 bytes | Read bytes | GET bytes | Yes |
| Missing key | `Optional.empty` | 404 | Yes | Yes | Can be added |
| Null/empty/oversized input | Yes | 400 from service | Does not enforce business rule | Does not enforce business rule | Can be added |
| Key traversal | Before port | Route/input contract | Validates | Validates | Service validates |
| I/O failure | Mock `IOException` | 503 | Separate fault-injection test | Separate SDK exception test | Fake can throw |
| Overwrite same key | Port contract | Not primary | Yes | Yes | Can be added |
| Unicode/binary | Yes | Binary | Unicode bytes | Binary | Unicode bytes |
| Credentials/permission denied | No | 5xx policy | Env-dependent OS permissions | Limited in LocalStack | No |
| Real NFS outage | No | 5xx policy | No | No | No |
| S3 IAM/KMS/presigned URL | No | No | No | Only with dedicated emulation tests | No |

**Do not force one test to cover the whole matrix.** Each layer has a clear job, keeping failures easy to pinpoint. A balanced CI setup runs unit/MVC/`@TempDir`/fake-flow tests on every commit, LocalStack in an integration job, and staging provider contracts per release/nightly/permission policy.

### Not-found vs. unavailable behavior differ

Wrong:

```java
try {
    return store.get(key);
} catch (Exception error) {
    return Optional.empty();
}
```

This is an **anti-pattern**, not the lesson's implementation. It turns access denied, DNS failures, timeouts, disk I/O errors, and wrong regions into **404**. Clients assume the object was deleted, risking data loss or bad retry logic.

In the example:

- Missing disk file → `NoSuchFileException` → `Optional.empty()`.
- Missing S3 key → `NoSuchKeyException` → `Optional.empty()`.
- Other errors → `IOException` → API returns 503 per sample advice.

Verify this contract with fault-injection tests, not happy paths alone.

## 21. Large files, streaming, and memory budgets

The demo enforces `MAX_BYTES=1_048_576`, indirectly bounding `MultipartFile.getBytes()` and `S3Client.getObjectAsBytes()` during uploads. **However**, a GET for an object written outside the service is **not automatically bounded** by upload rules: an S3 object created by another client could exceed 1 MiB. Production code must bound downloads or stream rather than calling `getObjectAsBytes` on large objects.

For large files:

- HTTP uploads should use `InputStream`/streaming/multipart APIs with explicit size budgets, content-length checks, and read limits.
- The port can define `put(ObjectKey key, InputStream body, long length, Metadata metadata)` or an upload session abstraction, documenting stream ownership and closing rules.
- AWS SDK v2 sync `RequestBody.fromInputStream(inputStream, length)` requires an exact length; when unknown, never buffer unbounded data in memory just to compute `byte[]`.
- Object storage multipart uploads must abort incomplete uploads to avoid accumulating storage charges.
- GET endpoints should return streams/resources with clear closing semantics, supporting range requests, `ETag`/`If-None-Match`, and cache headers where appropriate.
- In Spring MVC, `StreamingResponseBody` or resource streaming must align with thread pools and cancellation; tests must verify streams close and error paths behave properly.
- In reactive WebFlux, use reactive streams with backpressure and never call blocking S3/File APIs on event-loop threads.

**Never build an in-memory fake that silently accepts unbounded streams.** Fakes must enforce important port constraints (length, cancellation, checksums, metadata) whenever those are part of the business contract.

## 22. File/object metadata and download security

Production systems often add:

- `contentType`, `Content-Disposition`, **sanitized** original filename, size, checksum (SHA-256), `ETag`, `createdAt`.
- Tenant/user ownership, object retention, soft deletes, and audit logs.
- Virus/malware scanning, MIME sniffing, allowlisted types; never trust `MultipartFile.getContentType()` alone.
- Encryption at rest (SSE-S3/SSE-KMS), TLS in transit, least-privilege IAM roles, short-lived signed URLs.
- Scoped presigned URL expiries/permissions per bucket/key/method; **never** treat UUIDs as authorization tokens.
- Defenses against zip bombs, polyglot files, path traversal, header injection, and malicious SVG/HTML.
- Download headers: `Content-Type`, `Content-Disposition`, `Cache-Control`, `X-Content-Type-Options`, and CSP where risk warrants it.
- Checksums and tamper detection for critical payloads.

**This lesson deliberately serves `application/octet-stream`** to avoid serving untrusted content inline as HTML/JS. That alone does not replace full content security controls. Controller tests verify headers and bodies without implementing authentication/authorization; do not treat the demo's security as production-complete.

### When metadata lives in a database

A typical upload workflow is:

```text
PUT object to S3
    |
    v
INSERT asset_metadata into PostgreSQL
    |
    +-- DB transaction fails?
          |
          +-- orphan object remains in S3
```

No local `@Transactional` spans both PostgreSQL and S3. Designs often need **compensation**, outbox/recovery jobs, `pending`/`ready` states, idempotency keys, and garbage collection. A service unit test mocking `BlobStore` cannot prove distributed fail-recovery; test failure windows and orphan cleanup in integration/E2E jobs.

**Avoid assuming:** "if the file was PUT to S3, the database commit definitely succeeded," or vice versa. Both resources have separate transactions and lifecycles.

## 23. `@TempDir` does not emulate NFS/SMB or strict atomic renames

When storing files over network mounts, bugs surface only on real environments:

- File permissions, UID/GID, SMB ACLs, share modes, and identity mapping.
- Dropped mounts, network partitions, and stale file handles.
- Atomic rename and fsync/durability semantics varying by filesystem/provider.
- Concurrent writers across multiple hosts and advisory vs. mandatory locking.
- Case sensitivity, max path lengths, Unicode normalization, and Windows vs. POSIX separators.
- Quotas, disk-full, inode exhaustion, latency, and recovery.
- Symlink/hardlink races if untrusted actors share write access to the root.
- File watchers/`inotify` behaving differently across remote filesystems.

**`FileBlobStoreTest` with local `@TempDir` proves basic NIO operations**, not the items above. When NFS/SMB is a core dependency, run an integration job against an isolated network share with proper fault injection and key-prefixed cleanup.

**Never use `Files.exists` to distinguish missing files from permission denied.** `Files.exists` returns `false` whenever existence cannot be determined; to tell missing apart from unavailable, open/read directly and catch the specific exception. The sample file adapter catches **`NoSuchFileException` exclusively** for missing objects.

## 24. Testcontainers lifecycle and Spring context caching

In the LocalStack test above, `@Testcontainers` + static `@Container` is **Jupiter-owned** without a Spring context, so no cached Spring client can outlive the container. However, when a `@SpringBootTest` declares a static `@Container` with `@ServiceConnection`:

- The JUnit extension stops the container after **that test class**.
- Spring TestContext may cache the `ApplicationContext` across classes with identical configs.
- If a reused Spring context holds an endpoint pointing to the stopped container, subsequent tests fail with "connection refused."

Options include managing the container as a Spring test `@Bean` (where supported by your framework version) so its lifecycle matches the context, or defining explicit suite-level ownership. Here, S3 integration tests run directly under JUnit without mixing lifecycles with a cached Spring context.

**Never fall back to real AWS credentials** if Testcontainers fails to start. In integration tests, configure the client exclusively from `localstack.getEndpointOverride(...)`, never the public credential chain.

## 25. Race conditions, overwrites, and concurrent upload contracts

Random keys reduce collision risk, yet do not prove concurrency safety:

- Two writers on the same key overwrite each other; the sample port **permits overwrites** with no compare-and-set or `ETag` precondition.
- The file adapter uses move replacement; on filesystems lacking `ATOMIC_MOVE`, the fallback leaves an observation window.
- S3 supports conditional requests/`ETag`/versioning for **no-overwrite** or optimistic concurrency; model those preconditions on the port when required.
- Two successful PUTs do not guarantee downloads always observe one specific version when completion order is unspecified.
- Multipart uploads carry intermediate states and dedicated cleanup.
- Object listing/prefix consistency and pagination are outside the `get(key)` contract; add dedicated tests if listing/filtering is supported.
- In distributed apps, service caches can return stale metadata even when provider GETs are strongly consistent.
- When tests share a bucket, isolate keys under a unique prefix and clean up even on failure; never wipe the entire bucket.

**Define the overwrite contract clearly before writing assertions.** If products demand immutable event blobs, derive content-addressed keys or pass `If-None-Match: *` and reject conflicts; do not invent semantics in a fake without matching provider support.

## 26. Testing resilience and provider errors

Key error paths to test independently:

| Failure | Unit / fake | Adapter integration | Production policy |
| --- | --- | --- | --- |
| Invalid key/size validation | Mockito verifies zero calls | Adapter rejects unsafe keys | 400 / 413 |
| Object missing | Fake / `Optional.empty` | File / S3 missing | 404 |
| Storage access denied | Fake throws `IOException` | Provider staging permission test | 5xx / error classification |
| Bucket does not exist | Mock SDK / LocalStack case | S3 error path | Never return 404 object |
| Network timeout | Fault injection | Proxy/container fault injection | Retry budget, idempotency |
| Disk full / quota | Fault injection / FS sandbox | Mount / quota test | Cleanup, alerting |
| Partial write | Fault injection | Atomic move / stream test | No corrupt final object |
| Checksum mismatch | Controlled corrupt payload | Real metadata/checksum test | Reject / repair |
| Concurrent duplicate key | Interleaved reproducer | `ETag` / conditional write test | Conflict / versioning policy |
| Oversized payload | Service size rule | Stream / range integration | Memory / cost budget |

**Never treat exact exception message strings as API contracts**, because AWS SDKs and cloud providers change wording. Map exception **types, statuses, and codes** deterministically while logging redacted root causes.

**Retries require idempotency:** retrying a PUT for the same key/bytes can be safe, whereas generating a new key or DB metadata row on every retry creates orphan/duplicate objects. When uploads trigger external side effects, use idempotency keys or pending-state compensation.

## 27. Running the full test suite

Using the Gradle Wrapper in the project:

```bash
./gradlew test --tests example.storage.AssetServiceTest
./gradlew test --tests example.storage.FileBlobStoreTest
./gradlew test --tests example.storage.AssetControllerTest
./gradlew test --tests example.storage.AssetFlowWithFakeStoreTest
./gradlew test --tests example.storage.S3BlobStoreLocalStackTest
```

On Windows PowerShell:

```powershell
.\gradlew.bat test --tests "example.storage.AssetServiceTest"
.\gradlew.bat test --tests "example.storage.FileBlobStoreTest"
.\gradlew.bat test --tests "example.storage.AssetControllerTest"
.\gradlew.bat test --tests "example.storage.AssetFlowWithFakeStoreTest"
.\gradlew.bat test --tests "example.storage.S3BlobStoreLocalStackTest"
```

Suite summary:

| Test class | Methods | Real resource |
| --- | ---: | --- |
| `AssetServiceTest` | 6 | None; mocked port |
| `FileBlobStoreTest` | 5 | `@TempDir` filesystem |
| `AssetControllerTest` | 5 | MockMvc + mocked service |
| `AssetFlowWithFakeStoreTest` | 1 | Spring context; in-memory fake |
| `S3BlobStoreLocalStackTest` | 3 | Docker + LocalStack S3 |
| **Total** | **20** | |

**Non-LocalStack tests run without Docker.** `@WebMvcTest` and `@SpringBootTest` boot their respective Spring contexts without connecting to S3. If Docker/image/daemon is unavailable, only the S3 integration test should fail on that dependency—never swap in live S3 credentials as a workaround.

This code is provided for learners to **run and verify in an appropriate project**; no claim is made that Docker or AWS ran in the reader's environment. Gradle/JUnit output varies across runners, so no fixed suite stdout is printed. Only the Java SE demo in section 18 has exact deterministic stdout.

### Tiered CI pipelines

- **Fast tests job**: service unit tests, MVC slice, `@TempDir` filesystem tests, and fake flow.
- **Storage integration job**: LocalStack Testcontainers with pinned image versions, readiness checks, and diagnostics.
- **Staging contract job** where needed for IAM, NFS/SMB, encryption, pre-signed URLs, signed credentials, or async notifications.
- Report executed and skipped counts accurately; when storage integration is mandatory, **never silently skip** if Docker is unavailable.
- Use least-privilege test buckets, path prefixes, and credentials with teardown cleanup and failure TTL/GC.
- Never let static caches or test fakes leak across classes or unrelated projects.

## 28. Common anti-patterns

**1. Service calls `S3Client` directly.** Service unit tests become tied to the SDK and hard to swap; introduce a port.

**2. Unit tests hit a real AWS bucket.** Slow, costly, exposed to network/IAM failures, and risks colliding data; mock/fake at the right boundary.

**3. Mocking `AssetService` when trying to test business rules.** You only test controller delegation, skipping validation and key logic.

**4. Mocking `Files.*` inside the service.** Signals that business logic holds paths/I/O directly instead of delegating through an adapter.

**5. Running `@TempDir` and calling it "S3 integration."** Exercises local filesystems only, not the AWS SDK protocol.

**6. Mocking `S3Client.putObject` and concluding bucket policies/routing/permissions work.** SDK mocks open no network connections.

**7. Building overly permissive fakes.** E.g., `get` returns bytes even when `put` was never called, giving false flow passes.

**8. Skipping key validation and using `originalFilename` as a path.** Opens path traversal, overwrites across users, and cross-tenant leaks.

**9. Catching all errors into `Optional.empty()`.** Masks `AccessDenied` and network outages as 404s, making incidents hard to diagnose.

**10. Logging raw payloads, credentials, presigned URLs, or real paths in exceptions.** Leaks sensitive data; redact logs.

**11. Treating UUIDs as authorization tokens.** Random IDs do not replace owner/tenant ACLs.

**12. Omitting multipart/request body limits.** Allows huge payloads into RAM before the service checks sizes.

**13. Calling `getObjectAsBytes` for arbitrarily large files.** Risks OOM and lacks streaming/range support.

**14. Falling back silently from S3 to disk on IAM/endpoint errors.** Writes to the wrong backend while tests stay green; fail loudly instead.

**15. Using `@SpringBootTest` for every test.** Slows down suites and blurs boundaries; unit and adapter tests often need plain JUnit only.

**16. Asserting status 200 without verifying bytes.** Could return empty, corrupted, or wrong-key bodies; use `assertArrayEquals` / `content().bytes`.

**17. Treating LocalStack as 100% identical to AWS.** Does not cover IAM/KMS, quotas, cross-region behavior, durability, or production networking.

**18. Using a publicly writable root and trusting key regexes against symlink races.** Real OS isolation and permissions are mandatory.

**19. Assuming `ATOMIC_MOVE` always works.** Network filesystems may reject it; the sample fallback loses atomicity guarantees.

**20. Assuming NFS/SMB behaves like local `@TempDir`.** Test remote mount permissions, locking, and outages directly.

**21. Failing to close `S3Client` or streams on test errors.** Leaks connections; use `@AfterAll`, `try-with-resources`, or lifecycle beans.

**22. Using production credentials or buckets in CI tests.** Risks real data and bills; use isolated credentials and bucket prefixes.

**23. Passing fake tests and declaring real S3 works.** Add dedicated adapter contract integration tests.

**24. Writing DB metadata and object storage inside `@Transactional` assuming atomicity.** No single transaction covers JDBC + S3; design recovery and compensation.

**25. Failing to test missing vs. unavailable separately.** 404 and 503 are distinct application contracts.

**26. Depending on test ordering/timing or a shared bucket.** Causes state leakage; use unique keys and explicit cleanup.

**27. Leaving overwrite/versioning policies undefined.** Fakes may overwrite silently while production cloud policies require conditional requests.

**28. Wiping an entire bucket/directory for test cleanup.** Catastrophic if pointed at the wrong environment; clean up by namespace or test-owned keys only.

## 29. Final QA checklist

**Boundary design:**

- Does the service depend solely on the `BlobStore` port without importing AWS SDK or `Files`?
- Does the port define `put`/`get`, missing vs. error semantics, and overwrite rules clearly?
- Are keys server-generated so client filenames never become paths/keys?
- Do adapters protect keys/paths and avoid silent fallbacks?
- Are business validation, authorization, metadata, and provider transport separated into clean layers?

**Unit + HTTP tests:**

- Do service unit tests pair the real service with a mocked port, verifying bytes, keys, and errors?
- Do MockMvc controller tests cover 201/200/400/404/503, `Location`, content-type, and bodies?
- Do negative size/key tests verify zero backend calls?
- Does the in-memory fake clone arrays, handle missing keys accurately, and isolate data?
- Does the full Spring flow test run the real controller + service with only `BlobStore` faked?
- Does `app.storage.provider=memory` prevent creating real disk/S3 adapters?

**Adapter integration:**

- Do disk tests use `@TempDir` to read/write real bytes and cover missing, overwrite, and traversal cases?
- Are filesystem roots properly permissioned so attackers cannot plant symlinks?
- Do LocalStack tests use a real `S3Client`, endpoint override, dedicated bucket, and path-style/region/credential config?
- Are binary round-trips, missing keys, and invalid keys covered?
- Is SDK 404 `NoSuchKey` kept distinct from permission and network errors?
- Are `S3Client` and resources closed cleanly in lifecycle hooks?
- Are staging S3 tests added when IAM/KMS/presigned URLs matter?
- If using NFS/SMB, are mount contract tests run against the real resource?

**Resilience + security:**

- Are multipart/body memory and size budgets set, with streaming for large files?
- Are MIME policies, virus scanning, filename sanitization, `ETag`/checksums, and metadata handled?
- Is owner/tenant authorization enforced before GET/PUT rather than treating UUIDs as secrets?
- Are timeouts, retries, metrics, safe logging, and 404/5xx classifications in place?
- Are idempotency and compensation handled across uploads and DB metadata?
- Does cleanup target only test-owned keys/prefixes instead of wiping whole buckets?
- Are CI pipelines prevented from using production credentials or writing out of scope?
- Is the full suite free from state leakage, Spring context cache mismatches, and parallel races?

**Conclusion:** Substituting storage at the right boundary means **business services depend on a port**, unit tests mock/fake only that port, and adapter tests exercise **real filesystems or real S3 APIs** against isolated resources. `@TempDir` protects filesystem tests; LocalStack protects SDK, bucket, and key integration; staging contracts cover behaviors emulators cannot represent. Never treat green unit or fake tests as proof of IAM, networking, atomicity, or durability in external storage systems.

## 30. References

- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@SpringBootTest`, test slices, and MockMvc.
- [Spring Framework — `MockitoBean`](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-mockitobean.html): bean overrides in Spring test contexts.
- [JUnit 5 — `@TempDir`](https://junit.org/junit5/docs/current/user-guide/#writing-tests-built-in-extensions-TempDirectory): temporary directory lifecycle and cleanup.
- [Java SE 17 — `Files`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): `Files.move`, `ATOMIC_MOVE`, file reads, and I/O exceptions.
- [AWS SDK for Java v2 — S3 Client](https://docs.amazon.com/sdk-for-java/latest/developer-guide/java_s3_code_examples.html): `PutObject`/`GetObject` and client configuration.
- [Testcontainers Java — LocalStack](https://java.testcontainers.org/modules/localstack/): S3-compatible container, endpointOverride/credentials/region, and Testcontainers module.
- [AWS S3 — Consistency Model](https://docs.aws.amazon.com/AmazonS3/latest/userguide/Welcome.html#ConsistencyModel): consistency guarantees rather than guessing with sleeps.
- [OWASP — File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html): validation, filenames, malware, and access controls.