# Input Resource Read Permissions in Spring Batch

## 1. Why are input resource read permissions a security concern?

A batch job typically receives data from CSV files, mounted container directories, the classpath, object storage, APIs, or databases. Before an `ItemReader` reads the first item, **the process running the job must have permission to access the right input source**.

For example, `importOrdersJob` receives the parameter:

```text
inputFile=2026-11-16/orders.csv
```

By design, the readable file resides under:

```text
/srv/order-batch/inbound/2026-11-16/orders.csv
```

If the account running Spring Batch lacks permissions on the file or its parent directories, the reader will fail when opening the file. Conversely, if the application accepts an arbitrary path and reads it with an overly privileged account, a caller could try a path such as:

```text
inputFile=../../private/credentials.txt
```

This is not just a configuration bug; it can become a **path traversal** vulnerability, allowing a data-import feature to be abused to read resources outside the permitted boundary.

In the **Spring Batch Core Processing → Security** chapter, input resource read permissions should be understood across three layers:

1. **Execution identity:** under which OS user, service account, workload identity, or cloud role does the process run?
2. **Resource permissions:** which files, directories, buckets, object keys, or APIs is that identity allowed to read?
3. **Input boundary:** among readable sources, **which sources** does the application allow callers to select?

The overarching principle is **least privilege**: the job only needs read access to approved inputs, not read access to the entire server, bucket, or paths belonging to other jobs.

## 2. Spring Resource vs. access permissions

Spring Framework provides `org.springframework.core.io.Resource` as an abstraction for data sources. Readers such as `FlatFileItemReader` accept a `Resource`, but this object only describes **how to access the source**; it does not grant read permissions itself.

| Resource type | Example | Permission source | Suitable use cases |
| --- | --- | --- | --- |
| `ClassPathResource` | `classpath:fixtures/orders.csv` | Artifact/JAR, classloader, and file permissions of the application bundle | Fixtures/tests, static data packaged with the application |
| `FileSystemResource` | `/srv/batch/inbound/orders.csv` | OS user, group, ACL, mounted volume | Files received from upstream, SFTP, shared directories |
| `PathResource` | A `java.nio.file.Path` | File system provider and corresponding OS permissions | Code using Java NIO |
| `UrlResource` | `https://supplier.example/data.csv` | Network, TLS, authentication, and server-side permissions | Approved URL sources |
| S3, GCS, Azure Blob resource/object reader | Object key per bucket/container | IAM, workload identity, object policy, encryption key | Data on cloud object storage |
| `InputStreamResource` | Already opened stream | Source already authenticated and opened by other logic | One-time read streams; consider restart implications |

**Note on classpath:** a newly uploaded file in `/data/inbound` does not automatically appear on the classpath. Resources inside an executable JAR may not be physical files accessible via `getFile()`; use `getInputStream()` when you only need to read the contents.

**Note on S3:** a string like `s3://bucket/key` is not interpreted by Spring Framework core by default as a readable Resource. The project needs an integration or a reader/client supporting the corresponding object storage.

### 2.1. A Resource object does not prove readability

```java
import java.io.InputStream;
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;

Resource resource =
        new FileSystemResource("/srv/batch/inbound/orders.csv");

boolean exists = resource.exists();
boolean readable = resource.isReadable();

try (InputStream in = resource.getInputStream()) {
    // Read contents here.
}
```

`exists()` and `isReadable()` are useful for failing fast, but they are not permanent guarantees. Files, ACLs, mounts, secrets, or network state can change before `getInputStream()` actually opens the stream. Access permissions **are enforced at open time** by the OS, storage service, or target server.

Therefore, both preflight checks and the final read operation must handle exceptions properly. Simply because preflight succeeded does not mean subsequent reads will always succeed.

## 3. Local file read permissions on Linux

Given the path:

```text
/srv/order-batch/inbound/2026-11-16/orders.csv
```

The OS must allow the process to **traverse the parent directories** and **read the target file**.

```text
Process UID + supplementary GIDs
         |
         v
    /srv                          traverse
      /order-batch                traverse
        /inbound                  traverse
          /2026-11-16             traverse
            /orders.csv           read
         |
         v
    ACL / filesystem / mount policy
         |
         v
    InputStream opened successfully?
```

A file with mode `-rw-r-----` (640) is readable by its owner and owning group. A directory with mode `drwxr-x---` (750) gives the owner full permissions, the owning group read/traverse permissions, and grants no permissions to others. However, if the batch user **is not in that group**, access to the file will be denied.

**The `x` permission on directories is crucial:** it allows traversing or looking up entries when the name is known. Having `r` on a file **is not enough** if any parent directory lacks traverse permission.

Example permission layout:

```text
owner = batch-ingest   (producer)
group = batch-read
batch-service is a member of batch-read

inbound directory: 750
orders.csv:         640
```

With appropriate owner/group settings, the service can read without write access. Example commands:

```bash
chmod 750 /srv/order-batch/inbound
chmod 640 /srv/order-batch/inbound/orders.csv
```

These illustrate POSIX modes only and do not replace configuring owner, group, ACLs, or mounts. Do not apply them mechanically to production files without knowing existing permissions.

### Why not use chmod 777 or run as root?

`chmod 777` grants broad write and execute permissions depending on file/directory type; it creates an unnecessary surface for data tampering for a reader that only needs read access. Running the entire Spring Batch process as root to bypass `AccessDeniedException` also grants far more privileges than business requirements call for.

Instead:

- Identify the **actual execution identity** of the job.
- Grant read permissions only on the required directory or group.
- Keep write permission for the producer and read-only permission for the consumer if the workflow permits.
- Verify permissions along the entire parent directory chain.
- Isolate data areas across tenants or jobs that have distinct security boundaries.

On Windows, effective permissions depend on NTFS ACLs and the service/process identity. Modes such as `640`/`750` are not direct measures of NTFS permissions.

## 4. Execution identity varies by environment

| Environment | Identity to check | Common failure points |
| --- | --- | --- |
| IDE/local | User running Java | Relative paths, working directory, local permissions |
| Linux service | systemd `User=`/`Group=` or service account | ACLs, directory traversal, sandbox policy |
| Docker | Container process UID/GID | Bind mount owner/group and file mode |
| Kubernetes Job/CronJob | `runAsUser`, `runAsGroup`, `fsGroup` | PVC/CSI, mounted volumes, Pod policies |
| VM/managed workload | Process user and machine role | File system or cloud IAM |
| S3/GCS/Azure Blob | Workload identity / cloud role / service principal | Object and decrypt permissions, bucket/container policy |

A developer account might read a file on the node while UID 10001 inside a container cannot. Concluding "it works because I can open the file from an admin terminal" can be wrong for the actual job process.

### Inspection commands on Linux

When you have access to the **actual execution environment**:

```bash
id
ls -ld /srv/order-batch/inbound
ls -l /srv/order-batch/inbound/2026-11-16/orders.csv
namei -l /srv/order-batch/inbound/2026-11-16/orders.csv
```

`id` shows the current UID/GID; `ls` displays file/directory permissions; `namei -l` (if available) shows permissions for every path segment. On systems with SELinux, AppArmor, extended ACLs, or network file systems, these commands alone may not explain all effective permissions.

## 5. Do not accept arbitrary inputPath from callers

This configuration easily leads to security vulnerabilities:

```java
// Risky if inputPath comes from an untrusted caller.
Resource input = new FileSystemResource(inputPath);
```

A caller could supply:

```text
../../private/config.yml
/etc/passwd
../other-tenant/orders.csv
```

Even when the OS restricts permissions, the application should still enforce its **business boundary**. Do not rely solely on the service account "happening not to have permission" on files outside the root.

A better design:

```text
Job parameter:
  inputFile = 2026-11-16/orders.csv

Server-side configuration:
  app.batch.input-root = /srv/order-batch/inbound

Resolved:
  /srv/order-batch/inbound/2026-11-16/orders.csv
```

In multi-tenant environments, the application should map the **authenticated tenant** to an authorized source location. Having `tenantId` in job parameters supplied by the caller is not enough on its own to authorize reading that tenant's data.

### 5.1. ApprovedInputResolver example with Java NIO

The class below takes a relative filename, confines it inside a server-configured input root, and then verifies the real path and read permission:

```java
package com.example.batch.security;

import java.io.IOException;
import java.nio.file.AccessDeniedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Objects;

public final class ApprovedInputResolver {

    private final Path root;

    public ApprovedInputResolver(Path configuredRoot) throws IOException {
        Objects.requireNonNull(configuredRoot, "configuredRoot");
        this.root = configuredRoot.toRealPath();

        if (!Files.isDirectory(root)) {
            throw new IllegalArgumentException(
                    "Input root must be a directory");
        }
    }

    public Path resolveReadableFile(String inputFile) throws IOException {
        if (inputFile == null || inputFile.isBlank()) {
            throw new IllegalArgumentException("inputFile is required");
        }

        Path supplied = Path.of(inputFile);
        if (supplied.isAbsolute()) {
            throw new SecurityException("Absolute paths are disabled");
        }

        Path candidate = root.resolve(supplied).normalize();
        if (!candidate.startsWith(root)) {
            throw new SecurityException(
                    "Input path escapes approved root");
        }

        // Resolve symbolic links; fails if the file does not exist.
        Path realFile = candidate.toRealPath();
        if (!realFile.startsWith(root)) {
            throw new SecurityException(
                    "Input symlink escapes approved root");
        }

        if (!Files.isRegularFile(realFile)) {
            throw new IllegalArgumentException(
                    "Input is not a regular file");
        }

        if (!Files.isReadable(realFile)) {
            throw new AccessDeniedException(realFile.toString());
        }
        return realFile;
    }
}
```

| `inputFile` | Expectation with root `/srv/order-batch/inbound` |
| --- | --- |
| `2026-11-16/orders.csv` | Accepted if the real file exists, is inside root, and is readable |
| `./2026-11-16/orders.csv` | Accepted after normalization when permitted by contract |
| `../private/secret.txt` | Rejected because it escapes root |
| `/etc/passwd` | Rejected because it is an absolute path |
| Symlink `inbound/link.csv` pointing outside | Rejected after `toRealPath()` |
| `missing.csv` | Throws exception because the file does not exist |
| `subdir` is a directory | Rejected because it is not a regular file |

**Limitation:** `toRealPath()` and `Files.isReadable()` evaluate the path at **check time**. If an attacker can swap a symlink, file, or mount before the reader opens it, a *time of check to time of use* (TOCTOU) risk remains. For untrusted sources, use a write-restricted staging directory, immutable snapshots, or a secure open mechanism bound to a directory handle (such as `SecureDirectoryStream` when supported by the filesystem provider).

`Files.isReadable` is also not an absolute proof of readability: the actual open call may be denied due to ACLs, mounts, network issues, or file changes. At the application layer, catch read errors and classify them properly when opening `InputStream`.

### 5.2. Controlling via sourceId

When a batch job is triggered via API, it is safer and easier to govern by accepting a `sourceId`:

```text
sourceId=orders:2026-11-16:v3
```

The application looks up the source ID in a catalog owned by the authenticated tenant:

```text
sourceId
  -> tenant owner
  -> approved storage location
  -> object/file version
  -> checksum, schema version
  -> READY/VALIDATED status
```

Only after verifying caller permissions and source status does the job retrieve the internal location. This reduces the need to let callers specify filesystem paths or URLs directly.

## 6. Wiring the verified path into FlatFileItemReader

The Java examples below apply to **Spring Batch 5.x, Spring Boot 3.x, and Java 17+**. Some package/builder APIs changed in Spring Batch 6.x; consult the documentation for your project's version.

### 6.1. Server-side root configuration

```yaml
app:
  batch:
    input-root: /srv/order-batch/inbound
```

Register the bean:

```java
import java.io.IOException;
import java.nio.file.Path;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class InputSecurityConfiguration {

    @Bean
    ApprovedInputResolver approvedInputResolver(
            @Value("${app.batch.input-root}") String configuredRoot)
            throws IOException {
        return new ApprovedInputResolver(Path.of(configuredRoot));
    }
}
```

`input-root` is managed by the server. Do not let callers override this setting via a job launch request.

### 6.2. @StepScope reader using a relative parameter

```java
import java.io.IOException;
import java.math.BigDecimal;
import java.nio.file.Path;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.core.io.FileSystemResource;

public record OrderRow(String orderId, BigDecimal amount) {}

@Bean
@StepScope
FlatFileItemReader<OrderRow> orderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile,
        ApprovedInputResolver resolver) throws IOException {

    Path approvedFile = resolver.resolveReadableFile(inputFile);

    return new FlatFileItemReaderBuilder<OrderRow>()
            .name("orderReader")
            .resource(new FileSystemResource(approvedFile))
            .strict(true)
            .linesToSkip(1)
            .delimited()
            .names("order_id", "amount")
            .fieldSetMapper(fields -> new OrderRow(
                    fields.readString("order_id"),
                    fields.readBigDecimal("amount")
            ))
            .build();
}
```

`@StepScope` allows resolving `inputFile` when **the step executes**. A singleton reader should not hold a dynamic filename from a previous run.

`strict(true)` tells `FlatFileItemReader` that a missing resource is an error rather than silently treating it as an empty source. When actual data import is expected, do not set `strict(false)` just to hide read-permission errors or missing files. A stable reader name helps manage state in `ExecutionContext` across restarts.

The example expects a CSV with header `order_id,amount`; real projects must also validate schema/encoding and record data against the source contract. `JobParameters` alone cannot protect the root if another code path constructs a `Resource` directly from an unvalidated string.

### 6.3. Read and processing step

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        FlatFileItemReader<OrderRow> orderReader,
        ItemProcessor<OrderRow, OrderRow> processor,
        ItemWriter<OrderRow> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderRow, OrderRow>chunk(100, transactionManager)
            .reader(orderReader)
            .processor(processor)
            .writer(writer)
            .build();
}
```

`Step`, `JobRepository`, `StepBuilder`, `ItemProcessor`, `ItemWriter`, and the transaction manager types follow the corresponding Spring Batch/Spring Framework 5.x version. The snippet assumes the processor/writer are already defined and a test database is available when running.

## 7. Preflight step: verifying the source before writing output

In multi-step jobs, input read permissions should be verified **before business steps produce side effects**. A preflight step can verify:

- Source ID is within the authorized scope.
- File/object is READY, exists, and is readable.
- Resource can be opened right at preflight time.
- Schema/header and size are appropriate.
- Hash or object version matches the published snapshot.

### 7.1. Checking that the stream opens

```java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;

public static void verifyOpenable(Path file) throws IOException {
    try (InputStream ignored = Files.newInputStream(file)) {
        // Verify opening for read; write no data.
    }
}
```

This operation is stronger than `Files.isReadable` because the OS actually performs the open. However, it **does not freeze the file state** and does not prove the CSV contents are valid.

### 7.2. Preflight Tasklet example

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.step.tasklet.Tasklet;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;

@Bean
@StepScope
Tasklet inputPreflightTasklet(
        @Value("#{jobParameters['inputFile']}") String inputFile,
        ApprovedInputResolver resolver) {

    return (contribution, context) -> {
        Path input = resolver.resolveReadableFile(inputFile);

        try (InputStream ignored = Files.newInputStream(input)) {
            // Optional: verify header, checksum, and manifest.
        }
        return RepeatStatus.FINISHED;
    };
}
```

Define the step and flow:

```java
@Bean
Step inputPreflightStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        Tasklet inputPreflightTasklet) {

    return new StepBuilder("inputPreflightStep", jobRepository)
            .tasklet(inputPreflightTasklet, transactionManager)
            .build();
}

@Bean
Job importOrdersJob(
        JobRepository jobRepository,
        Step inputPreflightStep,
        Step importOrdersStep) {

    return new JobBuilder("importOrdersJob", jobRepository)
            .start(inputPreflightStep)
            .next(importOrdersStep)
            .build();
}
```

When the Tasklet throws an exception while resolving/opening the file, `inputPreflightStep` fails and the normal sequential flow does not proceed to the importer. The preflight `StepExecution` distinguishes a source read failure from item validation errors in `ItemProcessor`.

**Do not treat preflight as a guarantee of read access for the entire job lifecycle:** if the source can be replaced between preflight and the reader, address it using immutable snapshots/versions and staging write-permission policies.

## 8. Docker and Kubernetes: volume permissions differ from host permissions

A job running in a container might see the path `/app/input/orders.csv`, while the actual file is mounted from a volume or network storage. Read permissions depend on the container's UID/GID, data mode/ACLs, mount options, and the platform's security policy.

### 8.1. Non-root Docker

Example Dockerfile:

```dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY app.jar /app/app.jar
USER 10001:10001
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

If a bind-mounted file is readable only by UID 1000, UID 10001 is not automatically granted access. Adjust the volume's group/ACLs or use a source mount designed for consumer read access rather than switching the entire JVM to root.

### 8.2. Kubernetes Job reading a PVC

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: orders-import
spec:
  template:
    spec:
      restartPolicy: Never
      securityContext:
        runAsUser: 10001
        runAsGroup: 10001
        fsGroup: 2000
      containers:
        - name: batch
          image: example/orders-batch:1.0
          volumeMounts:
            - name: inbound
              mountPath: /srv/order-batch/inbound
              readOnly: true
          env:
            - name: APP_BATCH_INPUT_ROOT
              value: /srv/order-batch/inbound
      volumes:
        - name: inbound
          persistentVolumeClaim:
            claimName: orders-inbound-pvc
```

This is an example assuming the PVC and image already exist.

- `runAsUser`/`runAsGroup` set the process identity.
- `fsGroup` can help grant group access on volumes, though support and ownership changes depend on the volume type/CSI driver and cluster policy.
- `readOnly: true` prevents writes via this mount, **but does not grant read permissions** if ACLs/modes still deny them.
- A Kubernetes ServiceAccount provides Kubernetes API permissions or workload identity as configured; it does not automatically alter ACLs on every PVC file.

### Common root causes when moving from local to a pod

1. The file is not mounted at the path expected by the application.
2. The Pod runs under a different UID/GID than the developer user.
3. File mode is `0600` owned by another user.
4. A parent directory lacks traverse permission.
5. PVC/CSI or network filesystem preserves ACLs/ownership from elsewhere.
6. A changed `working directory` causes relative paths to point to the wrong place.
7. A new Pod runs on a different node while the source resided on the old node's local filesystem.

Inspect permissions inside the actual pod/container and under the actual batch execution identity.

## 9. Object storage: IAM and KMS replace local file ACLs

With S3, GCS, or Azure Blob, read permissions depend on cloud service policies. For instance, on S3 a job needs `GetObject` for the right prefix; if the object is encrypted with SSE-KMS, it may also need `kms:Decrypt` and the corresponding key policy.

Example IAM policy **allowing only object reads** under the `orders/inbound/` prefix:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::company-batch-input/orders/inbound/*"
    }
  ]
}
```

This is a minimal illustrative policy. If the application needs to list a prefix, it may need `s3:ListBucket` on the bucket resource with an appropriate prefix condition. Reading an object with a known key **does not inherently require permission to list the entire bucket**.

Do not store access keys, secret tokens, or presigned URLs in `JobParameters` or logs. Job parameters are typically stored in `JobRepository` metadata for restart and lookup; sensitive values can leak if placed directly there.

Use workload identity, VM/pod roles, or SDK credential provider mechanisms; grant least privilege scoped to the exact bucket/prefix/key.

### Distinguishing object storage access errors

| Error | Common causes | How to handle |
| --- | --- | --- |
| 403/AccessDenied | IAM, bucket policy, key policy, credentials | Check role, policy, and decrypt permission |
| 404/NoSuchKey | Wrong key, object not yet published, wrong version | Check manifest/ready marker |
| 503/timeout | Transient network or backend issue | Retry with backoff and cap |
| Object under same key changed contents | Producer wrote a new version | Pin object version/checksum |
| Opens fine but parse error | Wrong schema, encoding, or format | Data validation; do not blame IAM |

Do not retry indefinitely on 403 errors caused by missing policies. For transient network errors, apply timeouts and bounded backoff according to the client/storage SDK contract.

## 10. URL resources and SSRF risk

If an API allows callers to send `inputUrl` and the application constructs a `UrlResource`, the batch job can be abused to call internal endpoints or unauthorized addresses. This is a form of **server-side request forgery (SSRF)**.

The design should:

- Accept `sourceId` and map it to a registered endpoint.
- Restrict protocols, typically to HTTPS, and maintain an allowlist of approved hosts.
- Enforce policies for redirects, DNS resolution, and internal IP addresses; regex checks on hostnames alone are insufficient.
- Apply timeouts, response size limits, and TLS verification.
- Never put credentials in URL query strings, and never disable certificate verification "just to make it work."
- Combine with infrastructure network egress policies when high security is required.

Not every `"https://..."` URL is a safe input. Authorization policies must verify **the specific authorized source**, not just the protocol.

## 11. Restart and immutability of input resources

Spring Batch can store progress in `ExecutionContext`. When a step fails and restarts, the reader must read **the same source** in a state consistent with the checkpoint. A file with the same name whose contents have changed can cause missing or duplicated records.

```text
09:00 JobExecution #101
      source=orders_2026-11-16.csv
      chunks 1..10 COMMITTED
09:05 file permissions changed -> reader failed -> FAILED

09:30 permissions restored
      JobExecution #102 RESTART same JobInstance
      reader resumes from checkpoint
```

To restart safely:

1. Keep an **immutable source snapshot**: same byte stream, record order, schema, and version.
2. Ensure read permissions remain valid at restart time.
3. Keep identifying `JobParameters` and source identity stable.
4. Configure a stably named reader that supports saving state when needed.
5. Preserve `JobRepository` and `ExecutionContext`; do not delete metadata just to rerun.
6. Design an idempotent writer in case part of the data is replayed.

By default, a `COMPLETED` step may be skipped during a restart. If `inputPreflightStep` already completed in the previous execution, it **does not necessarily run again**. You can choose:

```java
new StepBuilder("inputPreflightStep", jobRepository)
        .tasklet(inputPreflightTasklet, transactionManager)
        .allowStartIfComplete(true)
        .build();
```

to require preflight to run again on restart, though this must be an intentional decision. Do not use revalidation to silently switch to a new file version while the checkpoint still belongs to the old source.

### Why snapshots matter more than isReadable?

```text
10:00:00 preflight file A -> OK
10:00:02 producer overwrites path with file B
10:00:05 FlatFileItemReader.open() reads file B
```

Even though both opens were permitted, the system validated A but processed B. The solution is publishing inputs via **object versions, immutable staging keys, manifests/hashes**, and restricting write permissions after publication. A simple read-permission check alone does not solve this issue.

## 12. Logging and monitoring read permission errors

An "unable to open file" exception must be classified so it is clear which team should respond. Emit structured logs:

```text
jobName
jobExecutionId
stepName
stepExecutionId
sourceId
businessDate
resourceType: FILESYSTEM / CLASSPATH / OBJECT_STORAGE / HTTPS
stage: RESOLVE / AUTHORIZE / OPEN / READ / PARSE
errorCategory: ACCESS_DENIED / NOT_FOUND / NETWORK / INVALID_SOURCE
environment
```

Example:

```json
{
  "event": "batch_input_open_failed",
  "jobName": "importOrdersJob",
  "stepName": "inputPreflightStep",
  "sourceId": "orders:2026-11-16:v1",
  "resourceType": "FILESYSTEM",
  "stage": "OPEN",
  "errorCategory": "ACCESS_DENIED",
  "environment": "production"
}
```

Log real paths or detailed exceptions only in systems with appropriate access controls. Avoid logging raw access tokens, presigned URLs, credentials, or sensitive payloads.

Custom metrics can include:

| Suggested metric | Purpose |
| --- | --- |
| `batch_input_open_total{jobName,result,errorCategory}` | Track successful/failed open attempts |
| `batch_input_access_denied_total{jobName,resourceType}` | Measure read-permission denials |
| `batch_input_validation_duration_seconds{jobName}` | Measure preflight duration |
| `batch_missing_source_total{jobName}` | Detect when upstream misses input SLAs |
| `batch_last_success_timestamp{jobName}` | Detect when a job stops completing |

These are **application-suggested** metric names, not guaranteed default Spring Batch metrics. Do not use file paths, object keys, `sourceId`, or high-cardinality exception messages as metric labels.

## 13. Testing input resource read permissions

Security testing must separate **unit tests for path-selection policy** from **integration tests for actual service account permissions**. A unit test running as a developer/admin may open a file that the production user cannot read.

### 13.1. Unit testing path validation with @TempDir

```java
import static org.junit.jupiter.api.Assertions.*;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class ApprovedInputResolverTest {

    @TempDir
    Path temp;

    @Test
    void acceptsReadableFileWithinRoot() throws Exception {
        Path root = Files.createDirectory(temp.resolve("inbound"));
        Path file = Files.writeString(
                root.resolve("orders.csv"),
                "order_id,amount\nORD-1,100.00\n",
                StandardCharsets.UTF_8);

        var resolver = new ApprovedInputResolver(root);

        assertEquals(file.toRealPath(),
                resolver.resolveReadableFile("orders.csv"));
    }

    @Test
    void rejectsPathTraversal() throws Exception {
        Path root = Files.createDirectory(temp.resolve("inbound"));
        Files.writeString(temp.resolve("private.txt"), "private");

        var resolver = new ApprovedInputResolver(root);

        assertThrows(SecurityException.class,
                () -> resolver.resolveReadableFile("../private.txt"));
    }

    @Test
    void rejectsAbsoluteFilePath() throws Exception {
        Path root = Files.createDirectory(temp.resolve("inbound"));
        var resolver = new ApprovedInputResolver(root);

        assertThrows(SecurityException.class,
                () -> resolver.resolveReadableFile(
                        temp.resolve("private.txt").toString()));
    }

    @Test
    void rejectsDirectoryInsteadOfRegularFile() throws Exception {
        Path root = Files.createDirectory(temp.resolve("inbound"));
        Files.createDirectory(root.resolve("subdir"));
        var resolver = new ApprovedInputResolver(root);

        assertThrows(IllegalArgumentException.class,
                () -> resolver.resolveReadableFile("subdir"));
    }

    @Test
    void rejectsMissingFile() throws Exception {
        Path root = Files.createDirectory(temp.resolve("inbound"));
        var resolver = new ApprovedInputResolver(root);

        assertThrows(java.io.IOException.class,
                () -> resolver.resolveReadableFile("missing.csv"));
    }
}
```

These tests verify path policy, not OS ACLs/IAM. They do not require a full Spring context or job.

### 13.2. Testing symlinks outside root

If the filesystem/CI permits symlink creation:

```java
@Test
void rejectsSymlinkOutsideRoot() throws Exception {
    Path root = Files.createDirectory(temp.resolve("inbound"));
    Path outside = Files.writeString(
            temp.resolve("private.txt"), "private");
    Files.createSymbolicLink(root.resolve("linked.csv"), outside);

    var resolver = new ApprovedInputResolver(root);

    assertThrows(SecurityException.class,
            () -> resolver.resolveReadableFile("linked.csv"));
}
```

Some Windows or CI environments disallow creating symlinks. Run this test only when the feature is supported; if creating the symlink itself fails, that is not evidence that the resolver blocked it.

### 13.3. Testing real permissions with restricted identities

Set up a fixture with distinct identities:

```text
batch-ingest   : write permission on inbound
batch-service  : read-only permission on inbound
unrelated-user : no read permission on inbound
```

Run the job or preflight under **batch-service**, verifying that allowed files open successfully and files with denying ACLs report errors. For object storage, run under the actual role/workload identity. A test running as root may still read a file with mode `000`, so `chmod 000` under a privileged account does not prove real enforcement.

### 13.4. Integration testing in Spring Batch

With **Spring Batch 5.x**, `spring-batch-test` supports `@SpringBatchTest` together with `JobLauncherTestUtils` to run a configured job. A useful test matrix:

| Scenario | Expected outcome |
| --- | --- |
| Valid file, service has permission | Preflight `COMPLETED`, importer runs |
| Missing file | Preflight `FAILED`, importer does not run |
| File exists but ACL denies access | Preflight `FAILED`, log category `ACCESS_DENIED` |
| Path traversal | Resolver rejects, does not open files outside root |
| Symlink outside root | Resolver rejects |
| File opens but wrong header | Permission passes, schema validation fails |
| File changed between preflight/import | Snapshot/version policy detects it or source is immutable |
| Restart after fixing permissions | Same input/checkpoint, writer produces no duplicates |

Example assertion snippet in a test with a valid `launcher` and `parameters`:

```java
JobExecution execution = launcher.launchJob(parameters);

assertEquals(BatchStatus.FAILED, execution.getStatus());

assertTrue(execution.getStepExecutions().stream()
        .anyMatch(step ->
                step.getStepName().equals("inputPreflightStep")
                && step.getStatus() == BatchStatus.FAILED));

assertTrue(execution.getStepExecutions().stream()
        .noneMatch(step ->
                step.getStepName().equals("importOrdersStep")));
```

This is an illustrative excerpt: beans, imports, database, and fixtures must be configured in the real test. With Spring Batch 6.x, use the version-appropriate test APIs, including the matching launch utilities.

## 14. Common errors and troubleshooting

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| `AccessDeniedException` on Linux | UID/GID/ACL/mount or missing parent directory traverse | Inspect process identity and every path segment |
| `FileNotFoundException`/`NoSuchFileException` | Wrong path, volume not mounted, file not READY | Check input root, manifest, staging |
| Readable in IDE but pod reports denied | Different UID, mount, or ACL | Inspect from inside the container as the actual UID |
| File 640 yet job still cannot read | Not in group or missing parent directory permission | Grant appropriate group/ACL |
| Reader reads 0 items and job reports COMPLETED | Empty file, non-strict setting, or wrong input | Preflight and empty-batch policy |
| `ClassPathResource.getFile()` fails inside JAR | Entry resides inside JAR | Use `getInputStream()` |
| S3 returns 403 | IAM/bucket/key policy/KMS | Check role and prefix permissions |
| S3 returns 404 | Wrong key or not yet published | Check manifest, version, and publication time |
| URL calls internal resources | Unbounded URL source | Use source catalog/allowlist and egress restrictions |
| Restart reads a file with different contents | Same path overwritten | Pin version/checksum, immutable snapshot |
| Symlinked file escapes allowed directory | Faulty path resolution or missing real-path check | Check root and symlinks, restrict source write permissions |
| Preflight passes but reader fails to open | Permission/mount/file changed between operations | Handle runtime exceptions, control snapshots/TOCTOU |
| `chmod` test passes yet production still fails | Test did not run under the real service identity | Run integration tests under the exact restricted UID/role |

### Read-permission incident investigation procedure

1. Retrieve `jobExecutionId`, `stepExecutionId`, `sourceId`, and resource type from logs.
2. Determine whether the failure occurred during path resolution, opening the stream, reading contents, or parsing.
3. Verify the job's execution identity, approved root, or IAM role.
4. Inspect the directory chain/ACL/mount or bucket/object/KMS policy.
5. Grant only the minimum required permission for the needed source; do not broaden to other sources.
6. Recover via contract-compliant restart/rerun while keeping the source immutable.
7. Reconcile committed data to avoid duplicates from reprocessing.

## 15. Hands-on exercises

**Exercise 1 — Resource abstraction.** Read a fixture in `src/test/resources` using `ClassPathResource` and a file in `@TempDir` using `FileSystemResource`. Explain the difference between data packaged inside a JAR and newly arrived input.

**Exercise 2 — Least privilege.** On a test Linux environment, configure the producer with write permission and `batch-service` with read-only permission. Verify traverse permissions on parent directories without using `chmod 777`.

**Exercise 3 — Path traversal.** Use `ApprovedInputResolver` to test `orders.csv`, `../secret.txt`, an absolute path, and a symlink escaping root. Write JUnit tests for each case.

**Exercise 4 — Preflight step.** Create a job with `inputPreflightStep` and `importOrdersStep`. When the file is missing or permission-denied, verify the importer does not run and the output database remains unchanged.

**Exercise 5 — Container.** Run the job as a non-root UID over a read-only mounted directory. Observe the difference when file owner/group match vs. mismatch.

**Exercise 6 — Cloud identity.** Design a role allowing only `GetObject` on one prefix. Test missing `kms:Decrypt`, missing objects, and network timeouts, classifying which errors should fail vs. retry.

**Exercise 7 — Restart.** Let several chunks commit, induce a source error, restore read permissions, and restart the exact instance. Preserve the input snapshot and metadata, and verify no duplicate output is created.

**Exercise 8 — Monitoring.** Emit an `ACCESS_DENIED` log with `sourceId`, `jobExecutionId`, and `stepExecutionId`; create a per-job aggregated metric without using filenames or object keys as labels.

## 16. Conclusion

**Input resource read permissions** in Spring Batch are both an operational prerequisite for the job and a security boundary for the data platform. A job must run under a managed identity, be granted read access only to authorized business sources, and never turn `JobParameters` into arbitrary paths or URLs.

For local files, combine OS ACLs, UID/GID, and path validation within an approved root. For containers/Kubernetes, control volumes and security contexts. For object storage, use workload identity/IAM, bucket/prefix scoping, and decrypt permissions. With Spring Batch, use `@StepScope` readers, `FlatFileItemReader.strict(true)`, preflight steps, and stable snapshot/versioned sources to detect issues early and preserve safe restarts.

### References

- [Spring Framework — Resource abstraction](https://docs.spring.io/spring-framework/reference/core/resources.html)
- [Spring Batch — Flat files and FlatFileItemReader](https://docs.spring.io/spring-batch/reference/readers-and-writers/flat-files/file-item-reader.html)
- [Spring Batch — Late binding and StepScope](https://docs.spring.io/spring-batch/reference/step/late-binding.html)
- [Spring Batch — Domain, JobRepository, and restart](https://docs.spring.io/spring-batch/reference/domain.html)
- [Java NIO — Files API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
- [Kubernetes — Security Context](https://kubernetes.io/docs/tasks/configure-pod-container/security-context/)
- [AWS S3 — Policies and permissions](https://docs.aws.amazon.com/AmazonS3/latest/userguide/using-with-s3-policy-actions.html)
- [OWASP — Path Traversal](https://owasp.org/www-community/attacks/Path_Traversal)
