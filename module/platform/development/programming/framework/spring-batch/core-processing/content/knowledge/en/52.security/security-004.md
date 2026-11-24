# Output Resource Write Permissions in Spring Batch

A batch job can read and process data properly yet still fail at the final step because it **lacks permission to write the output resource**. For example, `FlatFileItemWriter` cannot create a CSV file, a JDBC writer cannot `INSERT` into the target table, or the batch process lacks `PutObject` permission on an object store. In the **Security** chapter of **Spring Batch Core Processing**, configuring write permissions is not only about making the job succeed: it also governs **who can create, modify, overwrite, delete, and publish results**.

This lesson aims to design access permissions following the **least privilege principle**, isolate outputs per execution period, prevent writes to unintended paths, and preserve **retry/restart** capability when a job fails.

```text
              Scheduler / JobLauncher
                      |
           Controlled JobParameters
                      |
                      v
               Spring Batch Step
                      |
         OutputPathPolicy / target config
                      |
                      v
               ItemWriter / Tasklet
                      |
       +--------------+---------------+
       |              |               |
     File/FS       Database        S3 / SFTP / API
       |              |               |
   OS / ACL       DB privileges    IAM / credentials
       |              |               |
       +--------------+---------------+
                      |
                 Write result
                      |
        Metadata + audit + output verification
```

An essential distinction from the start: **Spring Batch does not grant write permissions to the process itself**. The framework invokes the writer; the operating system, database, object storage, or target system enforces the actual permissions of the identity running the batch job.

## 1. What operations does "write permission" include?

Saying "the job has permission to write to `/srv/batch/output`" is still vague. For many destination types, permissions are broken down further:

| Operation | Example | Permissions to consider |
| --- | --- | --- |
| Create new file | `orders-2026-11-16.csv` | Permission to create entries in the parent directory and traverse the path |
| Write file contents | Write CSV lines | File write permission or permission to create a new file in writable mode |
| Append | Resume a previously created file | Permission to open an existing file for write/append; writer restart rules |
| Overwrite or replace | Re-export end-of-day report | Write/delete/rename permissions per filesystem or target API mechanics |
| Create subdirectory | `2026-11-16/` | Permission to create entries in the parent directory |
| Rename/publish | `report.tmp` to `report.csv` | Permission to modify directory entries in source/target dirs; replace policy |
| Delete temporary files | Cleanup after failure | Entry deletion permission or corresponding DELETE privilege |
| List and verify | Check manifest/output | Metadata read, list, or read permissions if needed |

On POSIX-style operating systems, creating, deleting, or renaming files depends heavily on **permissions of the containing directory** (especially write and execute/search permissions), not just the permission bits of the file itself. Sticky bits, ACLs, and filesystem policies can also apply. On Windows, access is governed by **ACLs/NTFS**; do not directly equate Linux `rwx` bits to Windows permissions.

An account may be allowed to **create** a file without being allowed to **read it back**, or allowed `PutObject` on S3 without `GetObject`. This can be architecturally valid, but must be accounted for during output verification and restart handling.

## 2. Identifying the effective identity writing output

Permissions are checked against the identity seen by the connection or resource, **not the name of the developer who wrote the code**. Common environments:

| Environment | Effective identity | Authorization system |
| --- | --- | --- |
| Batch running directly on Linux | Process user/group, ACLs | Owner/group/mode/ACL, system policies |
| Batch running as Windows Service | Service account and access token | NTFS ACLs, share permissions if networked |
| Docker container | Container UID/GID and volume permission mapping | Host filesystem, volume mount, container security |
| Kubernetes Pod | Container UID/GID, supplemental groups, service account | Volume filesystem, Pod policies, and cloud roles |
| JDBC writer | Database user of the `DataSource` | `GRANT` per schema/table/procedure |
| S3/object storage | IAM role, workload identity, or credentials | Bucket policy, IAM, KMS, object ownership |
| SFTP | SFTP/SSH account | Server-side directory permissions, chroot, ACLs |

For example, a Spring Boot app on a laptop may create files under the developer account, yet when deployed into a Pod with `runAsUser: 10001`, the container fails to write to the volume because the directory belongs to `root:root`. The exact same `FlatFileItemWriter` produces different outcomes without any bug in the Spring Batch API.

### 2.1. Least privilege principle

- Grant permissions only on the **required paths/prefixes/schemas**, never across an entire filesystem or bucket.
- Use dedicated batch service accounts instead of administrative accounts.
- Separate **staging write**, **output publish**, **delete/cleanup**, and **audit read** permissions if business risk requires it.
- Never grant `777`, root access, or IAM wildcards just to quickly silence an `Access denied` error.
- Manage secrets/credentials through secrets engines or workload identity; never hardcode passwords or access keys in `application.yml` or logs.
- Ensure permissions are **sufficient for restarts**: the job must be able to reopen the previous `JobInstance`'s output/temp file when the writer supports state persistence.

## 3. File write permissions on Linux and POSIX

Suppose the output root is `/srv/batch/output`. Prepare the directory during **provisioning/deployment** with a defined owner/group so only the batch group can write.

Example operator commands (not commands to embed inside the job):

```bash
# Provision from an administrative account per deployment procedure.
sudo install -d -o batchuser -g batchgroup -m 0750 /srv/batch/output

# Inspect current identity and permissions.
id batchuser
ls -ld /srv/batch/output
namei -l /srv/batch/output
getfacl /srv/batch/output

# Test using the actual batch identity if system policy permits.
sudo -u batchuser test -w /srv/batch/output
```

Mode `0750` on a directory gives the owner read/write/traverse access, the group read/traverse access, and grants others nothing. If the batch runs as `batchuser`, the owner can create files. If multiple service accounts need to create outputs, use a write-authorized group or specific ACLs rather than opening `0777`.

**Note:** `test -w` or `Files.isWritable(...)` checks conditions only at check time. It does not guarantee subsequent writes will succeed because ACLs, quotas, read-only mounts, SELinux/AppArmor, permission changes, race conditions, or network filesystems can still fail. Always handle exceptions on the actual file open/write operation.

### 3.1. File permissions and `umask`

New files inherit permissions from the creation mode, `umask`, default ACLs, and filesystem behavior. For instance, a process with `umask 027` typically causes newly created files to be unreadable by users outside the group, though final permissions depend on the file-writing API and environment configuration.

Never run `chmod 777` on every output file after writing: this opens unnecessary access, risking exposure of customer data or tampering by other processes before publication. If specific POSIX permissions are needed, configure directory/default ACLs at deployment time and adjust permissions inside the application only when truly necessary.

### 3.2. Parent directory write permission vs. file write permission

For `/srv/batch/output/2026-11-16/orders.csv`, the job needs traversable directories at every level and file creation permission inside `2026-11-16/`. If `orders.csv` already exists from another job, the **existing file's** owner/mode may prevent the writer from opening it in append/truncate mode even when the parent directory is writable.

If the job runs under different service accounts across deployments, maintain a consistent ownership/ACL strategy so **an old file can be restarted**. Changing UID/GID without updating volume permissions can leave a new run able to read inputs yet unable to continue writing outputs.

## 4. Write permissions on Windows and network shares

Windows enforces file access via NTFS ACLs, share permissions (for UNC paths), and the process token. A path like `D:\batch\output\orders.csv` might succeed from an IDE yet fail under a Windows Service because the service account lacks permissions on `D:\batch\output`.

For a network share like `\\fileserver\batch-output`, you usually must verify **both share permissions and NTFS ACLs**; effective access is the intersection of multiple control layers. A batch service running as `LocalSystem` on machine A does not necessarily have permission to access a share on machine B.

Checklist:

1. Does the Windows Service or scheduled task account match the identity granted the ACL?
2. Do **Create files**, **Write data**, **Append data**, **Delete**, or **Modify** permissions match how the writer creates/replaces files?
3. Is the file locked by another process with a sharing violation?
4. Does the path rely on a mapped drive letter that only exists in an interactive user login session? For services, UNC paths are generally more reliable than user-mapped drive letters.

Do not fix file write failures by running the service as Administrator. Grant the proper ACL on the specific folder and consider the sensitivity of the output data.

## 5. Controlling output paths from `JobParameters`

Spring Batch supports passing an output path in `JobParameters` and injecting it with `@StepScope`. This is useful for period-based exports, yet risky if a scheduler or API lets users pass arbitrary paths.

Example **not to use directly with unvalidated input**:

```java
@Bean
@StepScope
FlatFileItemWriter<String> unsafeWriter(
        @Value("#{jobParameters['outputPath']}") String outputPath) {
    return new FlatFileItemWriterBuilder<String>()
        .name("unsafeWriter")
        .resource(new FileSystemResource(outputPath))
        .lineAggregator(item -> item)
        .build();
}
```

If an actor permitted to trigger batch executions passes `/etc/sensitive.conf`, `../other-tenant/report.csv`, or a shared directory path, the writer may attempt to write outside the intended area. Whether it succeeds depends on OS permissions, but the application **must not let external callers dictate the full path**.

### 5.1. Generating paths from validated business keys

A safer model: the application owns `outputRoot` and **constructs filenames itself** from tightly constrained parameters. Spring Boot 3.x / Spring Batch 5.x example:

```java
package com.example.batch.output;

import java.nio.file.Path;
import java.time.LocalDate;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public final class OutputPathPolicy {

    private final Path root;

    public OutputPathPolicy(
            @Value("${batch.output.root}") String configuredRoot) {
        this.root = Path.of(configuredRoot).toAbsolutePath().normalize();
    }

    public Path fileFor(String businessDate, String exportKey) {
        // Parse untrusted date string into a valid LocalDate.
        LocalDate date = LocalDate.parse(businessDate);

        // Allow only safe filename characters; disallow /, \, .., :.
        if (exportKey == null
                || !exportKey.matches("[A-Za-z0-9_-]{1,64}")) {
            throw new IllegalArgumentException("Invalid exportKey");
        }

        Path result = root
            .resolve(date.toString())
            .resolve("orders-" + exportKey + ".csv")
            .normalize();

        if (!result.startsWith(root)) {
            throw new SecurityException("Output escapes configured root");
        }
        return result;
    }
}
```

For example, with `batch.output.root=/srv/batch/output`, `businessDate=2026-11-16`, and `exportKey=settlement-01`, it produces:

```text
/srv/batch/output/2026-11-16/orders-settlement-01.csv
```

**Limitation of lexical checks:** `normalize()` and `startsWith()` block traversal via `..` segments, **but do not protect against symbolic links or junctions** in parent directories. If untrusted users can swap directory entries under the output root, they can make a path appear inside root while actually pointing outside. The primary defense is ensuring **the output root and intermediate directories are owned/managed by the service/deployment, preventing other users from creating or swapping symlinks**. In environments with genuinely untrusted path inputs or contention, use filesystem APIs that do not follow symlinks/secure directory operations or appropriate process isolation rather than relying on a single lexical check.

### 5.2. Wiring the writer to the policy-generated path

```java
package com.example.batch.output;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.file.FlatFileItemWriter;
import org.springframework.batch.item.file.builder.FlatFileItemWriterBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.FileSystemResource;

@Configuration
public class OutputWriterConfiguration {

    @Bean
    @StepScope
    public FlatFileItemWriter<String> ordersWriter(
            OutputPathPolicy pathPolicy,
            @Value("#{jobParameters['businessDate']}") String businessDate,
            @Value("#{jobParameters['exportKey']}") String exportKey)
            throws IOException {

        Path target = pathPolicy.fileFor(businessDate, exportKey);

        // Succeeds only if the service account actually has permission to create directories.
        Files.createDirectories(target.getParent());

        return new FlatFileItemWriterBuilder<String>()
            .name("ordersWriter")
            .resource(new FileSystemResource(target))
            .encoding(StandardCharsets.UTF_8.name())
            .lineAggregator(value -> value)
            .saveState(true)
            .build();
    }
}
```

This is an **illustrative configuration sample** for a step exporting `String` lines. `Files.createDirectories(...)` does not grant permissions: it succeeds only if parent directory permissions already allow it. If your environment requires directories to be pre-provisioned at deploy time or subdirectories follow strict governance, omit dynamic directory creation and let the job fail when provisioning is missing.

`@StepScope` matters because `JobParameters` are bound to **step execution**; the writer is instantiated when the step executes rather than eagerly at Spring context startup. `name("ordersWriter")` and `.saveState(true)` give the writer stable state for recovery via `ItemStream`. Whenever changing bean/writer names, paths, or permissions between runs, assess the impact on restarts.

### 5.3. Output identity across restarts

Suppose `businessDate` and `exportKey` are identifying `JobParameters`:

```java
JobParameters params = new JobParametersBuilder()
    .addString("businessDate", "2026-11-16")
    .addString("exportKey", "settlement-01")
    .toJobParameters();
```

When restarting the **same JobInstance**, the writer must return to the same output resource, be able to open the existing file, and restore its saved state. If every execution generates a new UUID in the filename without preserving a link to the prior instance, the job may create a new file, abandon the partial file, or duplicate results.

For a batch that is already `COMPLETED` and needs re-exporting, that is typically a **rerun/new version** rather than a restart. Use a new `exportKey`/version and an explicit publish policy; do not silently overwrite an official report with an unreconciled run.

## 6. Write permissions and `FlatFileItemWriter` behavior

`FlatFileItemWriter` must open the `Resource` for writing. Several settings affect output handling:

| Setting/characteristic | Meaning | Permission & restart checks |
| --- | --- | --- |
| `resource(...)` | Target file or resource | Does directory/file exist? Can the process open that exact path? |
| `saveState(true)` | Persist writer state in `ExecutionContext` | Repository and existing file must stay consistent across restarts |
| `shouldDeleteIfExists(...)` | Policy for existing file on fresh run, considering restart state | Avoid accidentally deleting another job/instance's output |
| `appendAllowed(true)` | Allow appending to existing file per writer mode | Need duplicate protection and clear ownership of output by instance |
| `shouldDeleteIfEmpty(true)` | Delete empty output per writer condition | Requires delete permission; do not assume a file exists after an empty step |
| `encoding(...)` | Output encoding | Does not affect ACLs directly, but matters when verifying results |

Spring Batch includes restart support for stateful writers; however, do not assume every append/truncate/delete mode is safe across all configurations and filesystems. If permissions prevent reopening the file after a failure, intact reader checkpoints still will not let the write step finish.

### Creating a file does not guarantee full writing succeeds

Permissions can change mid-step; quotas, read-only filesystems, disk-full conditions, or I/O errors can occur after the writer opens the file. If writing fails, the framework typically transitions the step to failed and persists metadata when possible. **The file may already exist and contain partial data**. Never publish that file as complete output simply because `Files.exists(path)` returns `true`.

Verify `JobExecution`/`StepExecution`, result size/contents, or checksums before publishing to consumers. For critical outputs, a **staging → verify → publish** workflow is much easier to control than writing directly to a consumer-readable path.

## 7. Staging, publishing results, and delete permissions

A secure export pipeline can use two distinct permission zones:

```text
/srv/batch/staging/2026-11-16/orders-settlement-01.part
             |
       write and restart here
             |
             v
    Batch COMPLETED + validation
             |
             v
/srv/batch/published/2026-11-16/orders-settlement-01.csv
```

In `staging`, only the batch process has write and cleanup permissions; consumers do not read it directly. `published` is locked down so only a publish step can create or replace approved outputs. Separation can be enforced via OS groups/ACLs or a dedicated publish service.

### 7.1. Publishing via move

On filesystems that support it, the temporary file can be renamed/moved to its official name after closing the writer and verifying the job:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

void publish(Path stagingFile, Path publishedFile) throws Exception {
    // Example: both paths were previously validated by OutputPathPolicy.
    Files.createDirectories(publishedFile.getParent());
    Files.move(stagingFile, publishedFile,
        StandardCopyOption.ATOMIC_MOVE);
}
```

**Conditions and limitations:** `ATOMIC_MOVE` works only when supported by the provider/filesystem. If staging and published reside on different filesystems/volumes, the move can fail; design a copy + verify + final manifest or another publish mechanism. Behavior when the destination already exists depends on the provider; do not rely on the snippet above as an absolute anti-overwrite lock under concurrent publishers. When "create once only" semantics are required, add locking/coordination and explicit replace controls.

Atomic rename prevents consumers from seeing a **half-written file** on supporting filesystems, though it does not mean all bytes are durably flushed across power loss. If strict durability is required, follow platform flush/sync and storage guidelines.

### 7.2. Cleanup permission is not official output write permission

For temporary files from failed jobs, the batch process may need delete permission for cleanup once restart is no longer possible. However, **never clean up temp files before confirming no restart is needed**. A cleanup process using overly broad wildcards can delete outputs of other active executions.

Name files using stable `businessDate`, `jobInstanceId`, or `exportKey` values, and clean up only resources bound to executions/instances confirmed to have ended their lifecycle. Delete privileges can be separated from the writer if security policy requires it.

## 8. Containers and Kubernetes: filesystems may be read-only

In container environments, a common security hardening pattern runs processes **non-root** with a read-only container root filesystem. The job can still write outputs if mounted with a dedicated **writable volume**.

Example Kubernetes Pod template fragment (adjust to your cluster/storage class and application image):

```yaml
spec:
  securityContext:
    runAsNonRoot: true
    runAsUser: 10001
    runAsGroup: 10001
    fsGroup: 10001

  containers:
    - name: batch
      image: example.com/batch/import-orders:1.0.0
      securityContext:
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
      env:
        - name: BATCH_OUTPUT_ROOT
          value: /work/output
      volumeMounts:
        - name: batch-output
          mountPath: /work/output
          readOnly: false

  volumes:
    - name: batch-output
      persistentVolumeClaim:
        claimName: batch-output-pvc
```

In the application:

```yaml
batch:
  output:
    root: ${BATCH_OUTPUT_ROOT:/work/output}
```

`runAsUser`/`runAsGroup` determine the process identity; `fsGroup` can help grant group access on volumes for storage types/CSI drivers that support it. **Not every storage driver changes ownership according to `fsGroup`**, and the PVC still needs proper ACLs/permissions provisioned. If using `emptyDir`, files are lost when the Pod is evicted, breaking restarts for partially written files. For jobs that must recover on a new Pod, choose durable storage and stable paths.

### 8.1. Common container errors

- The image ran as root locally so writes worked; production uses non-root and throws `Permission denied`.
- Volume mount is read-only due to `readOnly: true`, security policy, or node filesystem state.
- A new Pod runs with a different UID/GID than the owner of files created by the old Pod, causing restart failure.
- Output written to container filesystem instead of the volume: files disappear when the Pod is replaced.
- Multiple Pods write to the same output filename on a PVC, causing contention/overwrites.
- Network filesystems or CSI drivers have ownership/ACL semantics different from standard POSIX.

When troubleshooting, verify the effective identity, filesystem permissions of the **exact mount**, Pod security context, CSI driver, and Pod events. Never fix permission errors by running the entire workload as privileged when the actual issue is output directory ownership.

## 9. Object storage: IAM permissions differ from filesystem permissions

When the output is S3 or compatible object storage, the application's writer/adapter typically must use an SDK or service API; a standard `FileSystemResource` **does not automatically turn an `s3://...` path into a writable file**. Permissions are governed by IAM/bucket policies and potentially KMS.

Example IAM policy allowing **only object writes under an export prefix** (replace bucket and prefix for real environments):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:PutObject"],
      "Resource": "arn:aws:s3:::example-batch-output/exports/orders/*"
    }
  ]
}
```

This policy illustrates a single object-level action. If the pipeline needs to check object existence, read back checksums, list prefixes, delete temp files, or perform multipart uploads, it may also need permissions such as `s3:GetObject`, `s3:ListBucket` on the bucket with a prefix condition, tightly scoped `s3:DeleteObject`, or multipart upload actions. If objects are encrypted with customer-managed KMS keys, also configure key policies/IAM for the required KMS operations.

**Never grant `s3:*` on `*` just because an upload was denied.** Failures may stem from bucket policies, wrong keys/prefixes, KMS, explicit denies, permission boundaries, or expired credentials. Always diagnose the exact root cause.

### 9.1. Object keys and versions

Object keys should be generated from validated business keys:

```text
s3://example-batch-output/exports/orders/2026-11-16/settlement-01.csv
```

As with file paths, do not concatenate unvalidated tenant IDs or paths into keys and assume prefix restrictions alone guarantee isolation. In multi-tenant apps, roles/prefixes must be scoped per tenant and API request authorization must match object storage policies.

S3 object uploads do not behave like local file append/truncate. For restarts or upload retries, you may need temporary/versioned objects, ETag/checksum verification per upload semantics, and then manifest publication. If an upload request times out, the object may **already have been created** even though the client received no response; idempotency and object/version checks are therefore crucial.

### 9.2. SFTP and external APIs

With SFTP, the service account needs write permissions in the target server directory and possibly rename/delete permissions when using temporary uploads. Do not grant shell or full filesystem access when SFTP chroot suffices. For HTTP APIs, tokens should hold only the scope needed to create the target resource; if the API supports idempotency keys, reuse the same key for a logical output to avoid duplicate records on timeout/retry.

## 10. Database writers also need right-sized write privileges

`JdbcBatchItemWriter`, `JpaItemWriter`, or custom writers access the database via the `DataSource` user/role. To write into a business table `report_output`, the batch account typically needs `INSERT`, possibly `UPDATE` for upserts, and `SELECT` for verification/idempotency—and does not necessarily need `DROP TABLE`, `ALTER TABLE`, or DBA privileges.

Example minimal PostgreSQL privileges (hypothetical schema/role names):

```sql
GRANT USAGE ON SCHEMA reporting TO batch_writer;
GRANT INSERT, UPDATE, SELECT ON TABLE reporting.report_output
    TO batch_writer;
```

Using sequences or auto-generated IDs may require `USAGE`/`SELECT` on sequences depending on SQL and schema. Using `DELETE`, staging tables, or stored procedures also requires appropriately scoped privileges. Permissions on `JobRepository`'s `BATCH_*` tables are a separate layer: the framework must be able to create/update execution and context metadata as deployed. You can isolate the repository and business tables into separate schemas/datasources with distinct roles, provided transactions and permissions for each source are designed clearly.

**Do not use a full-privilege DDL/migration account as the runtime `DataSource`** just so the application can create tables at startup. Separate schema migration (Flyway/Liquibase or a deployment step) from batch runtime privileges whenever the environment supports it.

### Write permissions and transactions

Having `INSERT` privilege does not guarantee data is committed: a transaction can roll back if a chunk fails. Conversely, a writer calling an external system outside the transaction can create side effects even if Batch metadata fails. For retries/restarts, rely on business keys, unique constraints, intentional upserts, or transactional outbox patterns rather than permissions alone.

## 11. Classifying failures when resources cannot be written

Several failures look externally like "writer failed," yet require different handling:

| Symptom | Possible cause | Appropriate response |
| --- | --- | --- |
| `AccessDeniedException`/`Permission denied` | UID/GID/ACL or parent dir prevents creating/opening file | Verify identity and permissions on exact path; fix provisioning |
| `Read-only file system` | Read-only mount/volume | Fix mount configuration or target path; do not retry forever |
| `No such file or directory` | Missing parent directory, wrong path | Provision directory or fix config; do not create trees outside allowed zones |
| `FileAlreadyExistsException` | Overwrite disallowed, duplicate period run | Check output identity and publish/rerun policy |
| `No space left on device` or quota | Out of disk space/inodes/quota | Remediate infrastructure, clean up within scope, then restart |
| Windows sharing violation | File locked by another process | Close handle, eliminate concurrent writer, or isolate output path |
| `AccessDenied` on object storage | IAM, bucket policy, KMS, explicit deny, or wrong prefix | Inspect permissions by request action/resource |
| SQL permission denied | DB user lacks DML/schema privileges | Grant exact required privileges or fix runtime role |
| Timeout writing to API/SFTP | Slow network/target; outcome uncertain | Check target state, idempotency, and bounded retry |

### 11.1. Do not use skip to hide permission errors

Spring Batch provides `skip(...)` to skip identifiable **item-level data errors**. However, filesystem permission or DB privilege errors generally affect the entire step's output. Never configure `.skip(Exception.class)` or `.skip(IOException.class)` just to let a job end `COMPLETED` when the writer cannot write. That can silently skip an entire valid batch with zero output produced.

For persistent permission denials, retrying continuously will not solve the error either. **Fail the step**, emit an alert with sensitive details masked, fix infrastructure permissions, and then restart. For transient errors (file locks, brief network glitches), bounded retries are appropriate only when repeating the operation is safe and recoverable.

### 11.2. Do not treat `Files.isWritable` as granting permission

In Java NIO:

```java
Path directory = Path.of("/srv/batch/output");

if (!Files.isDirectory(directory) || !Files.isWritable(directory)) {
    throw new IllegalStateException("Batch output directory is not writable");
}
```

This is only a **preflight check for an existing path**, helpful for failing fast. It does not guarantee opening a file will succeed, and can be inaccurate under certain providers/ACLs. The writer must still handle actual `IOException`/write exceptions. Never call `Files.setWritable(..., true)` as a production workaround: the service account is typically not the owner, and attempting to widen permissions itself contradicts least privilege.

## 12. Write permissions and restart: two inseparable requirements

Suppose a batch writes a large file in chunks, saves state in `ExecutionContext`, and fails on the third chunk. When the job restarts:

```text
Run #1
  JobInstance = report-2026-11-16
  output = staging/report-2026-11-16.part
  chunks 1, 2: completed and checkpointed
  chunk 3: failed

Run #2 (restarts same JobInstance)
  must access the exact same output resource
  writer reopens file using existing checkpoint
  processes uncommitted remainder and finishes
```

The following changes can break restarts even while metadata remains intact:

- Changing the batch account from UID 10001 to UID 10002 when old files are writable only by the owner.
- A new Pod fails to mount the same PVC or mounts it at a different path.
- Automated cleanup deletes temp files immediately on `FAILED` even though the instance still needs restarting.
- Naming paths by `jobExecutionId` instead of a stable key tied to `JobInstance` without a state handoff mechanism.
- Generating a random filename in the writer constructor when the context does not store that path.
- Changing writer append/delete settings between executions without testing `ExecutionContext` migration.
- Granting file creation permission without permission to reopen or append to an existing file.

**`JobRepository` does not store or restore OS/IAM permissions.** It persists execution metadata and contexts—it does not repair ACLs, mount volumes, or issue cloud tokens. Therefore, a restart playbook must check both metadata and external resource access conditions.

### 12.1. Safe recovery principles

1. Read persisted `JobInstance` and `JobParameters` to identify the exact business key/output resource.
2. Verify the output/temp file still exists, matches the expected version, and can be opened by the current service account.
3. Verify permissions were fixed **per deployment policy**, avoiding `chmod 777` or unrevoked temporary admin privileges.
4. Restart the same instance via the appropriate Spring Batch API; do not add extra identifying parameters to create a new instance.
5. Reconcile final output after restart: line count, checksum, business keys, or manifest.

If the output cannot be recovered, follow a **controlled rerun from the start** with idempotency; never assume a fresh job can automatically pick up mid-stream.

## 13. Testing output resource write permissions

Unit tests verify path policies, while integration tests verify that the service account/runtime can write to real resources. Do not wait until production to discover the batch job cannot create files.

### 13.1. Unit testing path policy with `@TempDir`

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class OutputPathPolicyTest {

    @TempDir
    Path root;

    @Test
    void createsDeterministicPathInsideConfiguredRoot() {
        OutputPathPolicy policy = new OutputPathPolicy(root.toString());

        Path result = policy.fileFor("2026-11-16", "settlement-01");

        assertThat(result).startsWith(root.toAbsolutePath().normalize());
        assertThat(result.getFileName().toString())
            .isEqualTo("orders-settlement-01.csv");
    }

    @Test
    void rejectsUntrustedExportKey() {
        OutputPathPolicy policy = new OutputPathPolicy(root.toString());

        assertThatThrownBy(() -> policy.fileFor("2026-11-16", "../outside"))
            .isInstanceOf(IllegalArgumentException.class);
    }
}
```

`@TempDir` manages the test directory; these tests verify naming rules and **lexical** traversal. They do not fully verify symlink race resistance, production ACLs, or network volume behavior. For untrusted paths, run security tests in an isolated environment capable of creating symlinks/junctions alongside filesystem permission policies.

### 13.2. Integration testing the writer with temporary output

Example assertions after running a Spring Batch 5.x step with `@SpringBatchTest` and `JobLauncherTestUtils`:

```java
Path root = testDir.resolve("output");
Files.createDirectories(root);

JobParameters params = new JobParametersBuilder()
    .addString("businessDate", "2026-11-16")
    .addString("exportKey", "test-001")
    .toJobParameters();

JobExecution execution = jobLauncherTestUtils.launchStep(
    "exportOrdersStep", params);

assertThat(execution.getStatus()).isEqualTo(BatchStatus.COMPLETED);

Path output = root.resolve("2026-11-16/orders-test-001.csv");
assertThat(Files.readAllLines(output, StandardCharsets.UTF_8))
    .containsExactly("A001,PAID", "A002,NEW");
```

This is a **partial test sample**, assuming the step/beans are configured and `batch.output.root` in the test context points to the test-owned `root`. In real tests, supply the output root via test configuration such as dynamic properties or fixture-specific config—never a production directory. An integration test that checks only file existence without reading contents can miss empty or truncated files.

### 13.3. Negative test: permission denied

A valuable negative test runs the batch under the **same class of identity/volume policy as production** in an isolated environment, but mounts or provisions the resource as **read-only** or non-writable. Expected outcome: step `FAILED`, no output published, and logs/alerts clearly classify the failure.

Avoid simulating permission denied via `chmod` in a cross-platform JUnit test and assuming consistent results everywhere. Windows ACLs, Linux root, container filesystems, and volume drivers behave differently. In Kubernetes, use a non-root test Pod with a read-only mount; on Windows, use a test service account with restricted ACLs. Where real infrastructure cannot be provisioned in CI, use a fake writer/resource throwing `IOException` to test failure and alert policies, while remembering **that does not prove real OS permissions are configured correctly**.

### 13.4. Testing after fixing permissions and restarting

Suggested scenario:

| Phase | Setup | Expected outcome |
| --- | --- | --- |
| 1 | Writer starts on a writable volume; some chunks commit | Temporary output and checkpoint exist |
| 2 | Simulate a write failure on a later chunk or tighten permissions in test env | Execution `FAILED`, partial file not published |
| 3 | Restore permissions per policy | Process can reopen the same output |
| 4 | Restart with the same identifying parameters | New `JobExecution` created under the same `JobInstance` |
| 5 | Reconcile results | Final file has exact line count, no missing/duplicate lines; output published once |

If permission is denied before the writer opens and no chunks have committed, still check status and cleanup; never assume a temp file definitely exists.

## 14. Monitoring, logging, and auditing write permissions

Events should be logged structurally to separate access failures from data failures:

```text
event=batch.output.open_failed
jobName=exportOrdersJob
jobExecutionId=814
stepExecutionId=1260
businessDate=2026-11-16
resourceType=FILE
resourceAlias=orders-report-staging
errorCategory=PERMISSION_DENIED
```

You do not need to log **absolute paths**, presigned URLs, secrets, connection strings, or sensitive object metadata. In multi-tenant environments, a `resourceAlias`, resource type, and error code usually suffice for triage; sensitive details belong in access-controlled logs or internal investigation channels.

Useful metrics:

- Executions failed due to `PERMISSION_DENIED`, `READ_ONLY`, `QUOTA_EXCEEDED`, `RESOURCE_LOCKED`.
- Output open latency and per-chunk write time; upload/object-write failure rate.
- Number of `.tmp/.part` files remaining after instances are no longer restartable.
- Number of business periods `COMPLETED` without a published output manifest.
- Restarts following identity changes or volume migrations.

For auditing, store `jobExecutionId`, `businessDate`, output resource alias, output version/checksum, and principal/service identity **without credentials**. Who had write access and publish events matter for explaining who or what workload generated a result, especially for financial batches or regulated reports.

## 15. Pre-deployment write-permission design checklist

| Question | Recommended action |
| --- | --- |
| Which UID, service account, or IAM role runs the job? | Identify the effective identity and declare it explicitly in deployment config |
| Which exact directories/prefixes/tables need write access? | Scope least privilege to specific resources |
| Does the job need subdir creation, append, rename, or delete? | Grant exact additional privileges, not vague "write" access |
| Does output path come from requests/JobParameters? | Use a fixed output root, validate business keys, protect against symlinks/junctions |
| Can the writer reopen the same output after a crash? | Design deterministic output names per job instance and save writer state |
| Is output on storage durable across restarts/Pod replacements? | Pick a suitable PVC/object store or staging mechanism |
| If publishing is needed, who can move files to the official zone? | Separate staging/published, control replacement and manifests |
| Does the environment enforce quotas, read-only mounts, or custom ACLs? | Test under the runtime identity, not just on a laptop |
| Is duplicate/overwrite protection enforced on concurrent runs? | Business locks, versioned keys, scheduler policies, and idempotency |
| On permission denied, how does the batch behave? | Fail clearly, alert, fix policy, then restart; never bulk-skip |
| Are logs/audits free of sensitive paths/secrets? | Allowlist log fields and restrict log access |
| Have negative cases and restarts been tested? | Test with production-like filesystem/volume/identity setups |

## 16. Typical mistakes

| Mistake | Consequence | Right approach |
| --- | --- | --- |
| `chmod -R 777` on output root | Other users/processes can alter or delete output | Provision owner/group/ACLs only for the required service |
| Running batch as root/Admin just to write files | Larger blast radius when the job fails or is exploited | Use a least-privilege service account and fix resource permissions |
| Using raw `outputPath` from API requests | Risks path traversal or overwriting another tenant/resource | Derive paths from validated business keys under a fixed root |
| Checking only `Files.isWritable` | Can pass preflight yet fail on actual write | Catch and classify writer/API exceptions |
| Writing output to container ephemeral filesystem | Files vanish on Pod replacement, breaking restarts | Use durable volumes or appropriate object storage |
| Changing UID between runs while keeping old file owner | Restarted writer cannot open the file | Stabilize UID/GID or provision volume ACLs |
| Granting only `s3:PutObject` then expecting delete/list | Cleanup/verify operations are denied | Analyze all required operations and grant narrow permissions |
| Granting IAM wildcards or DB DDL privileges to runtime | Excessive privileges increase blast radius | Separate migration/admin from runtime writers |
| Deleting temp files immediately when a job fails | Loses output needed for restart | Clean up based on job instance lifecycle and recovery policy |
| Using `appendAllowed(true)` to "fix" file-exists errors | Can produce duplicate output on a new instance | Distinguish restarts from reruns; use stable naming/versions and state |
| Treating `BatchStatus.COMPLETED` as proof of publish | Final move/upload/verification may not have occurred | Track reconciled manifests or publish statuses |
| Skipping `IOException`/permission errors | Job turns green while missing output data | Fail, alert, and restart after fixing permissions |

## Conclusion

**Output resource write permissions** are part of data integrity and security, not just a tweak to stop `Permission denied` errors from a writer. Spring Batch needs an identity with proper privileges on the **exact** filesystem directory, DB table, object prefix, or endpoint; at the same time, the application must constrain paths, isolate temporary outputs from published outputs, and distinguish write/append/replace/delete privileges.

For restartable batches, resources and their permissions must remain consistent across executions of the same `JobInstance`. A successful design is one where the job **writes when authorized, rejects out-of-bounds targets, fails clearly when permissions are blocked, and recovers without losing or duplicating data**.

## References

- [Spring Batch Reference — Flat Files](https://docs.spring.io/spring-batch/reference/readers-and-writers/flat-files.html): configuring `FlatFileItemWriter`, resources, and output-related options.
- [Spring Batch Reference — ItemStream](https://docs.spring.io/spring-batch/reference/readers-and-writers/item-stream.html): persisting writer/reader state for restart via `ExecutionContext`.
- [Spring Batch Reference — Configuring a Step](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html): transactions, chunks, and error handling during writes.
- [Oracle Java Tutorials — File and Directory Access](https://docs.oracle.com/javase/tutorial/essential/io/fileAttr.html): handling file permissions and attributes in Java NIO.
- [Kubernetes Documentation — Configure a Security Context](https://kubernetes.io/docs/tasks/configure-pod-container/security-context/): `runAsUser`, `fsGroup`, and volume access permissions.
- [AWS IAM User Guide — Policies and Permissions](https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies.html): scoping permissions by action and resource.
- [Spring Batch Reference — Testing](https://docs.spring.io/spring-batch/reference/testing.html): testing steps/jobs, metadata, and scenario-based failures.
