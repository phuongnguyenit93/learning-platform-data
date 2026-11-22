# Creating Temporary Files With Appropriate Permissions and Controlled Cleanup in Java NIO

## 1. Why Are Temporary Files Also a Security Concern?

Java applications frequently create temporary files to process uploaded images, export reports, extract archives, sort large datasets, store intermediate results, or pass data between processing steps. A file existing only briefly **does not mean it is safe**.

Practical risks include:

- **Data exposure:** a file contains tokens, customer data, uploaded content, or secrets that other users on the machine can read.
- **Name prediction and squatting:** using a fixed name like `/tmp/report.txt` and overwriting it can create races or collisions across processes.
- **Symbolic-link attacks:** an attacker makes the temporary path point to a different target file before the application reopens it.
- **TOCTOU:** the application checks `exists()`, `isSymbolicLink()`, or permissions at time A, but the file is replaced before use at time B.
- **Resource leaks:** files/channels remain open, and temporary files/directories are left behind after exceptions, cancellations, or timeouts.
- **Disk exhaustion:** unbounded uploads create huge temporary files, or thousands of requests leave orphaned files that bring down the service.
- **Incomplete erasure:** calling `delete()` does not mean old data has been physically wiped from SSDs, swap, snapshots, backups, or journals.

Goals of this lesson: **create temporary files with appropriate APIs; apply permissions at creation time; isolate working directories; use resources with clear ownership; clean up on both success and failure; and understand remaining limitations.**

## 2. Which API Should You Choose to Create Temporary Files or Directories?

Java NIO.2 (`java.nio.file` package) provides these methods:

~~~java
Path file = Files.createTempFile("prefix-", ".tmp");
Path dir  = Files.createTempDirectory("job-");

// Specify a trusted parent directory:
Path fileInDir = Files.createTempFile(dir, "data-", ".bin");
Path nestedDir = Files.createTempDirectory(dir, "stage-");
~~~

`Files.createTempFile(...)` and `Files.createTempDirectory(...)` **create the object in the filesystem immediately upon invocation**, rather than merely generating a name string for later use.

When supported by the provider, creating the new entry checks existence and creates the file **atomically with respect to the relevant filesystem operation**, avoiding the common bug of "pick a name then check it does not exist." They do not establish a lock or transaction contract for **subsequent operations after creation**.

| API | Result | When to use? |
|---|---|---|
| `Files.createTempFile(prefix,suffix,attrs...)` | Temporary file in provider-determined location | Standalone operation not needing a dedicated tree |
| `Files.createTempFile(dir,prefix,suffix,attrs...)` | Temporary file in chosen directory | Managing permissions/entire lifecycle of a job |
| `Files.createTempDirectory(prefix,attrs...)` | Temporary directory in provider-determined location | Needing isolated space for multiple intermediate files |
| `Files.createTempDirectory(parent,prefix,attrs...)` | Temporary subdirectory inside parent | Service has an administrator-controlled scratch area |
| `Files.createFile(path,attrs...)` | File with a specific name, must not yet exist | Application explicitly manages pathname and requires create-new |
| `File.createTempFile(...)` | Legacy `java.io.File` API | Legacy systems; new code prefers NIO `Files` |

**Do not write:**

~~~java
// Bad pattern: fixed name, check then create.
Path p = Path.of("/tmp/my-app-export.csv");
if (!Files.exists(p)) {
    Files.writeString(p, confidentialData);
}
~~~

There is a race between `exists()` and `writeString()`. Moreover, `Files.writeString` with its default option set can create a new file or truncate an existing file, making it unsuitable when existing external data must not be overwritten.

**Use** `Files.createTempFile(...)` or a create-new command with well-defined semantics. Avoid generating temporary names manually from timestamps, thread IDs, or weak randomness inside a shared directory.

### Are Prefix and Suffix Secret Information?

No. Prefix and suffix aid file-type identification and operations; API-generated names help avoid collisions, but **do not replace access permissions**. Never treat a hard-to-guess name as the sole protection layer. Do not put tokens, passwords, customer emails, or sensitive data into filenames because filenames can appear in logs, directory listings, or crash reports.

## 3. Choosing the Parent Directory: Not Every "Temp" Location Is Trusted

`Files.createTempFile("x-", ".tmp")` and `createTempDirectory("x-")` without a directory argument use the provider's default location. For the default provider, this location is typically tied to the `java.io.tmpdir` system property.

However:

- The actual temp location can vary across OS/containers, runtime configurations, or providers.
- A shared temp directory may allow multiple users to create entries inside it.
- Temp on a network volume has different permission, latency, visibility, and cleanup characteristics than local disk.
- A containerized application may use an ephemeral filesystem, dedicated quotas, or read-only mounts.
- The parent directory may not exist, may run out of space, or may lack permissions.

**Good rule:** for sensitive data or multi-step processing, create **a dedicated temporary directory per job**, restrict access on that directory, and create child files inside it.

~~~text
trusted-temp-parent/
  secure-job-<generated>/
    source-<generated>.bin
    output-<generated>.json
    intermediate-<generated>.dat

Job owns entire subtree:
  create -> use -> close handles -> delete children -> delete directory
~~~

When only one job can write to its private directory, many risks of other users replacing pathnames drop significantly. Still, an actor running under **the same OS account with equivalent privileges**, or a privileged user, can interfere; a `0700` directory does not create a sandbox against the owning principal itself.

### Directory Permissions Matter Just as Much as File Permissions

Even with a `0600` file, an overly permissive parent directory can allow the pathname to be replaced or deleted, causing races when reopening. On POSIX systems, a private scratch directory typically uses mode `0700` (owner read/write/execute, granting nothing to group/others).

**Do not check only file permissions while forgetting the parent chain.** Directories storing confidential data should be owned by a trusted principal, not writable by unauthorized parties, and all symlinks/mounts along the path must fall under a controlled policy.

## 4. POSIX: Grant Permissions **at Creation Time**, Avoid "Create Then Chmod"

On POSIX-compatible filesystems, basic permissions are typically expressed as strings:

- `rw-------`, i.e., mode `0600`: owner only read/write file.
- `rwx------`, i.e., mode `0700`: owner only read/write/traverse directory.
- `r--r--r--`, i.e., mode `0444`: read-only, which is **unsuitable** if the file must be modified during processing.
- Group/others permissions can broaden who can read or alter the data.

Java NIO provides `PosixFilePermissions.asFileAttribute(...)` to pass permissions at creation time:

~~~java
import java.nio.file.attribute.FileAttribute;
import java.nio.file.attribute.PosixFilePermission;
import java.nio.file.attribute.PosixFilePermissions;
import java.util.Set;

Set<PosixFilePermission> dirMode =
        PosixFilePermissions.fromString("rwx------");
Set<PosixFilePermission> fileMode =
        PosixFilePermissions.fromString("rw-------");

FileAttribute<Set<PosixFilePermission>> privateDir =
        PosixFilePermissions.asFileAttribute(dirMode);
FileAttribute<Set<PosixFilePermission>> privateFile =
        PosixFilePermissions.asFileAttribute(fileMode);

// Create with permission attributes directly in the creation operation:
Path jobDir = Files.createTempDirectory("secure-job-", privateDir);
Path artifact = Files.createTempFile(jobDir, "data-", ".bin", privateFile);
~~~

This is an **illustrative snippet**, requiring `java.nio.file.Files` and `Path` imports. It only succeeds on providers supporting POSIX attributes at that location.

Important properties:

1. File attributes are passed into **the creation operation**, avoiding a gap between creating a file with overly broad permissions and restricting them afterward.
2. Providers can reject unsupported attributes with `UnsupportedOperationException`; never ignore this and pretend permissions are protected.
3. Effective permissions can still be restricted further by umask/ACL/platform policy; **re-verify actual permissions** if permissions are a security invariant.
4. Calling `setPosixFilePermissions(path, ...)` on an **existing** file is a separate permission change and does not retroactively undo earlier data exposure.

### Why Is "Create Then Fix Permissions" Dangerous?

~~~java
// Do not use for sensitive data in a shared directory.
Path tmp = Files.createTempFile("secret-", ".bin");
Files.setPosixFilePermissions(
        tmp, PosixFilePermissions.fromString("rw-------"));
~~~

With the default provider, `createTempFile` may create stricter default permissions than an ordinary file creation call, but **do not assume every provider enforces your application's policy**. If specific permissions are mandatory, supply attributes at creation time and verify them on the target platform.

**Note on owner permissions:** mode `0600` does not stop malware running under the same account, root/administrator, or privileged backup mechanisms; use sandboxing or OS account isolation when the threat model demands it.

## 5. Windows and Filesystems Without POSIX Support

Windows typically uses **ACLs (Access Control Lists)** rather than relying purely on POSIX permission bits. `PosixFilePermissions` syntax **is not a portable policy across all providers**.

Check support before use:

~~~java
boolean supportsPosix = FileSystems.getDefault()
        .supportedFileAttributeViews()
        .contains("posix");
~~~

This only checks the capability of the **default filesystem**; the actual path could reside on a different provider or file store. When code handles multiple filesystems, handle errors and verify on the target path itself.

For Windows or ACL-based filesystems:

- Use file owner and `AclFileAttributeView` / `AclEntry` when policy requires setting specific permissions.
- Control **inherited ACLs** from parent directories; do not assume no other account has access just because the program only knows the current username.
- Since file shares/volumes can differ, creating files with ACL attributes at creation time is provider-dependent; check platform documentation and run real security tests.
- If a minimum policy cannot be verified, **fail closed** for sensitive data rather than silently creating files with unknown permissions.
- Do not mechanically translate `chmod 0600` as "equally safe on every Windows filesystem."

Related API:

~~~java
// Illustrative ACL view access, not a complete policy.
AclFileAttributeView view = Files.getFileAttributeView(
        path, AclFileAttributeView.class);
if (view == null) {
    throw new UnsupportedOperationException("ACL view unavailable");
}
// Real ACLs must be designed around owner, service account,
// allowed identities, and parent inherited permissions.
~~~

The imports for this snippet belong to `java.nio.file` and `java.nio.file.attribute`. Do not copy an ACL from another environment and blindly apply it to directories/temp files, as doing so can lock out the application itself or inadvertently grant access.

## 6. Reopening Temporary Files: Avoid Symbolic Links and Redundant Operations

After creation, an application typically writes the file and then reads it back, passes it to the next step, or deletes it. If another party can swap the pathname during this window, reopening can point to a **different object**.

Defensive measures:

1. Create files under a parent directory writable only by a trusted account.
2. Avoid fixed names in publicly shared directories.
3. When reopening, consider `LinkOption.NOFOLLOW_LINKS` in APIs accepting `OpenOption` to reject a symlink at the final component, **if supported by the provider**.
4. Do not treat `Files.isSymbolicLink(path)` followed by `open(path)` as a race-free check: the pathname can change between the two calls.
5. Do not assume `NOFOLLOW_LINKS` checks all parent components or prevents all hardlink, mount, or directory-swap attacks.
6. Where an adversary can modify the directory tree, consider `SecureDirectoryStream` or OS-level APIs supporting operations relative to a secure directory handle when available.

Example reopening a previously created file:

~~~java
import java.nio.channels.SeekableByteChannel;
import java.nio.file.LinkOption;
import java.nio.file.OpenOption;
import java.nio.file.StandardOpenOption;
import java.util.Set;

try (SeekableByteChannel out = Files.newByteChannel(
        artifact,
        Set.<OpenOption>of(
                StandardOpenOption.WRITE,
                StandardOpenOption.TRUNCATE_EXISTING,
                LinkOption.NOFOLLOW_LINKS))) {
    // Write data to channel. Do not open with CREATE if the file already exists.
}
~~~

This snippet uses an already-created `artifact`; it is not standalone runnable. Because `Files.createTempFile(...)` **already created the file**, reopening it for writing **does not need** `CREATE` or `CREATE_NEW`. In particular, `CREATE_NEW` on the path just created will **fail because the file already exists**.

### Why Is `CREATE_NEW` a Different Tool?

`Files.newByteChannel(path, Set.of(CREATE_NEW, WRITE), attrs...)` is used when you want to **create a new file at a chosen pathname** and strictly refuse to overwrite an existing entry. It does not replace `Files.createTempFile` when you already have a temp file. If you need to create and open in a single atomic primitive, you can use `CREATE_NEW` with a chosen path under a trusted parent, while managing name selection, collisions, and permissions yourself.

## 7. Lifecycle Management: Which Resources Must Be Closed Before Deletion?

Temporary files are often opened by:

- `InputStream` / `OutputStream`.
- `BufferedReader` / `BufferedWriter`.
- `FileChannel` / `SeekableByteChannel`.
- Libraries processing images, ZIPs, PDFs, CSVs, XML, or database engines.
- A child process using the path.
- A thread running an asynchronous operation.

**Ownership principle:** the component creating the resource must define who is responsible for closing it and who is authorized to delete the file. If I/O operations are still pending or another process has not finished, deleting immediately can fail or cause OS-dependent behavior.

Typical pattern:

~~~java
Path file = Files.createTempFile("work-", ".tmp");
try {
    try (OutputStream out = Files.newOutputStream(file)) {
        out.write(bytes);
    }

    // Process using a file-reading library after the writer has closed.
    consumeFile(file);
} finally {
    Files.deleteIfExists(file);
}
~~~

This is an illustrative snippet requiring imports and application-defined `bytes`/`consumeFile`. `finally` executes on both normal completion and ordinary exceptions, but **there is no guarantee** it runs on forced process kill, JVM crash, or power loss.

### Why Is `try-with-resources` Better?

`try-with-resources` automatically closes `AutoCloseable` resources on exit, even when a processing step throws an exception. If both the body and `close()` throw errors, Java preserves the primary error and attaches the close error as a **suppressed exception**—better than a cleanup error in `finally` masking the original failure cause.

One way to structure this is creating a temporary workspace manager implementing `AutoCloseable`:

~~~java
try (TempWorkspace workspace = TempWorkspace.create()) {
    // Create and process files inside workspace.
} // close() deletes contents and directory per policy.
~~~

The complete example in the next section implements this structure.

## 8. Complete Java 17+ Program: Private `0700` Directory, `0600` File, and Cleanup

The program below targets **POSIX filesystems** and deliberately **fails closed** if the default filesystem lacks a POSIX attribute view. That means:

- On Linux/macOS or suitable POSIX filesystems: creates the directory with owner-only mode, creates the file owner-only, and verifies no group/others permissions exist.
- On Windows ACL-only: does not attempt to create sensitive files with permissions unprovable via POSIX; prints a notice and exits cleanly.
- Opens the file for writing with `NOFOLLOW_LINKS`; uses `try-with-resources` to close the channel before deleting.
- Deletes the file and subdirectories via `Files.walkFileTree(...)`, without following symbolic links in default traversal.
- Prints deterministic output without leaking random temporary file paths.

Save as **`SecureTempLifecycleDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.SeekableByteChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileSystems;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.OpenOption;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.StandardOpenOption;
import java.nio.file.attribute.BasicFileAttributes;
import java.nio.file.attribute.PosixFilePermission;
import java.nio.file.attribute.PosixFilePermissions;
import java.util.Set;

public class SecureTempLifecycleDemo {

    // Scope owns the entire temporary directory tree.
    private static final class TempWorkspace implements AutoCloseable {
        private final Path root;

        TempWorkspace(Path root) {
            this.root = root;
        }

        @Override
        public void close() throws IOException {
            // walkFileTree does NOT follow symbolic links by default.
            Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
                @Override
                public FileVisitResult visitFile(
                        Path file, BasicFileAttributes attrs)
                        throws IOException {
                    Files.delete(file);
                    return FileVisitResult.CONTINUE;
                }

                @Override
                public FileVisitResult postVisitDirectory(
                        Path dir, IOException failure)
                        throws IOException {
                    if (failure != null) {
                        throw failure;
                    }
                    Files.delete(dir);
                    return FileVisitResult.CONTINUE;
                }
            });
        }
    }

    private static boolean ownerOnly(
            Set<PosixFilePermission> permissions) {
        for (PosixFilePermission permission : permissions) {
            if (permission.name().startsWith("GROUP_")
                    || permission.name().startsWith("OTHERS_")) {
                return false;
            }
        }
        return true;
    }

    public static void main(String[] args) throws Exception {
        if (!FileSystems.getDefault()
                .supportedFileAttributeViews()
                .contains("posix")) {
            System.out.println("POSIX unavailable: refuse sensitive temp");
            return;
        }

        Set<PosixFilePermission> directoryMode =
                PosixFilePermissions.fromString("rwx------");
        Set<PosixFilePermission> fileMode =
                PosixFilePermissions.fromString("rw-------");

        Path root = Files.createTempDirectory(
                "secure-job-",
                PosixFilePermissions.asFileAttribute(directoryMode));

        boolean directoryPrivate;
        boolean filePrivate;
        String content;

        try (TempWorkspace scope = new TempWorkspace(root)) {
            directoryPrivate = ownerOnly(
                    Files.getPosixFilePermissions(
                            root, LinkOption.NOFOLLOW_LINKS));

            if (!directoryPrivate) {
                throw new SecurityException("Directory too permissive");
            }

            Path file = Files.createTempFile(
                    root,
                    "record-",
                    ".txt",
                    PosixFilePermissions.asFileAttribute(fileMode));

            filePrivate = ownerOnly(
                    Files.getPosixFilePermissions(
                            file, LinkOption.NOFOLLOW_LINKS));

            if (!filePrivate) {
                throw new SecurityException("File too permissive");
            }

            ByteBuffer payload = ByteBuffer.wrap(
                    "hello".getBytes(StandardCharsets.UTF_8));

            try (SeekableByteChannel channel = Files.newByteChannel(
                    file,
                    Set.<OpenOption>of(
                            StandardOpenOption.WRITE,
                            StandardOpenOption.TRUNCATE_EXISTING,
                            LinkOption.NOFOLLOW_LINKS))) {
                while (payload.hasRemaining()) {
                    int n = channel.write(payload);
                    if (n <= 0) {
                        throw new IOException("No write progress");
                    }
                }
            }

            // Directory belongs to owner so processes without
            // write permission inside it cannot swap the pathname.
            content = Files.readString(file, StandardCharsets.UTF_8);
        } // Channel closed; TempWorkspace.close() deletes the temp tree.

        System.out.println("private-directory=" + directoryPrivate);
        System.out.println("private-file=" + filePrivate);
        System.out.println("content=" + content);
        System.out.println("cleanup="
                + Files.notExists(root, LinkOption.NOFOLLOW_LINKS));
    }
}
~~~

Compile and run:

~~~bash
javac SecureTempLifecycleDemo.java
java SecureTempLifecycleDemo
~~~

**Stdout on a properly functioning POSIX filesystem with file create/delete permissions:**

~~~text
private-directory=true
private-file=true
content=hello
cleanup=true
~~~

**Stdout when the default filesystem does not support a POSIX view:**

~~~text
POSIX unavailable: refuse sensitive temp
~~~

Explanation:

1. The program checks POSIX capability and does not silently skip the security requirement.
2. `Files.createTempDirectory(..., asFileAttribute(0700))` creates a private workspace.
3. `Files.createTempFile(root,..., asFileAttribute(0600))` creates the file inside the workspace with the required permissions at creation time.
4. `getPosixFilePermissions(...)` verifies no permissions are granted to group/others. This check **does not itself inspect additional ACLs or non-POSIX privilege mechanisms**.
5. `NOFOLLOW_LINKS` rejects a symlink on the final file when reopening if the provider properly implements the option. A private parent reduces the risk of entry replacement by another user, though it does not guarantee safety against an attacker with the same UID.
6. Writes via `SeekableByteChannel` use a loop because you must not assume a single `write` call transfers the entire `ByteBuffer` in all cases.
7. `TempWorkspace.close()` uses `walkFileTree`, calling `Files.delete` on each file first before deleting directories. By default, traversal does not follow symlinks; if a symlink appears in the directory, it is handled as an entry to delete the link without following its target.
8. `try-with-resources` ensures cleanup is attempted on normal exit or exception.
9. `cleanup=true` is printed only after deletion finishes and `Files.notExists(root, NOFOLLOW_LINKS)` confirms no entry remains at that path.

**Limitation:** this is a POSIX example and does not implement a Windows ACL policy. Without POSIX support, it refuses to create a sensitive workspace rather than falling back to unverified default permissions. For cross-platform needs, build an equivalent policy on the ACL provider and test actual permissions.

## 9. Cleaning Up One File vs. Cleaning Up a Directory Tree

### A Single Standalone Temporary File

If there is only one file:

~~~java
Path temp = Files.createTempFile("job-", ".dat");
try {
    process(temp);
} finally {
    Files.deleteIfExists(temp);
}
~~~

`process` is an application function. Close all streams/channels opened by `process` before reaching deletion. Using `deleteIfExists` avoids treating "file was already deleted by another step" as an error, but **does not swallow all deletion errors**: open files, permission denied, or I/O failures can still throw `IOException`.

### Multiple Files and Subdirectories

You cannot delete a directory **that still contains files** with a single `Files.delete(directory)` call. Children must be deleted first, then the parent. `Files.walkFileTree` is suitable when the application **owns the entire tree** and the threat model does not allow external parties to modify the tree during cleanup.

Do not use:

~~~java
// Insufficient if the directory still has entries:
Files.delete(tempDirectory);
~~~

Nor should you write a recursive delete function that accepts an arbitrary path from user input and deletes unchecked. If the pathname is wrong, you could accidentally delete a production directory.

**Safety rules for tree cleanup:**

- Have proof that the application created and owns the workspace root.
- Never accept `directory-to-delete` directly from request bodies or query parameters.
- Do not follow symbolic links (`walkFileTree` does not enable `FOLLOW_LINKS` by default).
- If protection against a same-account attacker swapping pathnames is needed, use stronger mechanisms such as `SecureDirectoryStream` when supported by the filesystem/provider rather than assuming walk-and-delete is always race-free.
- Log cleanup failures in a way that does not expose sensitive data in filenames/paths.
- If deletion fails, alert monitoring and have a follow-up handling policy rather than silently ignoring it.

## 10. Why `deleteOnExit()` Should Not Be the Primary Cleanup Strategy

Java provides:

~~~java
temp.toFile().deleteOnExit();
~~~

It asks the JVM to try deleting the file when the JVM **terminates normally** via a shutdown hook; this is not an adequate guarantee for server environments or sensitive data.

Drawbacks:

- No guarantee of execution on forced JVM kill, power loss, or OS crash.
- Server applications can stay alive for days/weeks; files remain on disk the entire time.
- The list of files registered with `deleteOnExit` stays in JVM memory for the process lifetime; using it across millions of requests increases memory usage.
- Files may still be in use by other processes or fail to delete due to permissions.
- With directories and multiple children, registration deletion order must be considered; do not rely on hooks instead of a clear workspace ownership model.
- In container/Kubernetes environments, lifecycles can be cut short or persistent mounted volumes can retain stale files.

**Recommendation:** use `try-with-resources`/`finally` to delete immediately when the job finishes. `deleteOnExit()` may be considered as a secondary defense for short-lived CLI tools, but never treat it as a cleanup SLA or security mechanism.

## 11. `DELETE_ON_CLOSE`: Useful but Has Limitations

`StandardOpenOption.DELETE_ON_CLOSE` requests deleting the file when the channel is closed, depending on provider support. It can be used in some cases where a temporary file only needs to exist while the channel is open:

~~~java
// Illustrative snippet; temporaryFile was created by the application.
try (SeekableByteChannel channel = Files.newByteChannel(
        temporaryFile,
        Set.<OpenOption>of(
                StandardOpenOption.WRITE,
                StandardOpenOption.DELETE_ON_CLOSE,
                LinkOption.NOFOLLOW_LINKS))) {
    // Process data while the channel remains open.
}
~~~

What you must not assume:

- Not every filesystem/provider supports every option.
- Do not rely on the file remaining visible under its pathname while the channel is open. Some systems may unlink the entry early or have different semantics.
- If another library needs to **reopen the file by name**, `DELETE_ON_CLOSE` can break the workflow.
- It does not guarantee secure physical erasure of all data copies.
- It does not replace cleaning up **other files and containing directories**.

For multi-step pipelines, a private directory + explicit cleanup is usually easier to control.

## 12. Exceptions, Cancellation, and Cleanup Errors: Avoid Masking the Root Cause

Suppose upload processing throws an exception, and deleting the file in `finally` also fails:

~~~java
Path file = Files.createTempFile("upload-", ".tmp");
try {
    importData(file);
} finally {
    Files.deleteIfExists(file);
}
~~~

If `importData` threw an error and `deleteIfExists` throws another, the cleanup error can **mask the original business error** in this `finally` style. When that matters, use an `AutoCloseable` resource cleaner with `try-with-resources` as in Section 8: Java tracks **suppressed exceptions** so the primary cause is preserved.

For example:

~~~java
try {
    runJob();
} catch (Exception e) {
    System.err.println("Cause: " + e);
    for (Throwable suppressed : e.getSuppressed()) {
        System.err.println("Cleanup also failed: " + suppressed);
    }
}
~~~

Illustrative code; `runJob` must close/clean up its resources via `try-with-resources` per policy. In production, error logs must not include sensitive input contents.

### Asynchronous I/O and Child Processes

If a temporary file is used by an `AsynchronousFileChannel`, another process, or a background task, closing a wrapper on the main thread **does not prove** all pending operations have finished and results have been consumed. Coordinate the lifecycle:

~~~text
CREATE TEMP -> SUBMIT WORK -> WAIT / CANCEL / DRAIN
                              |
                              v
                     CLOSE ALL FILE HANDLES
                              |
                              v
                      DELETE TEMP WORKSPACE
~~~

Deletion should only happen once no legitimate party still needs the file. If a job is cancelled, cancel the task first, wait or isolate properly, then clean up with appropriate timeouts and monitoring.

## 13. Cleanup Failures in Production Environments

| Issue | Possible cause | Appropriate response |
|---|---|---|
| `DirectoryNotEmptyException` | Child not deleted yet, another process created a file | Check ownership, traverse in right order, restrict writers |
| `AccessDeniedException` | Permissions/ACL forbid deletion or file is held open | Close handles, check policy, record error |
| `NoSuchFileException` | Another actor already deleted it | `deleteIfExists` when expected |
| `FileSystemException` | Volume error, file busy, provider constraint | Alert ops and bounded retry if safe |
| Disk full | Insufficient space for file/metadata writes | Enforce quotas, fail request, clean up created files |
| Process crash/KILL | `finally`/shutdown hook did not run | Ownership- and TTL-based startup sweeper outside request path |
| Symlink appears in temp tree | Pathname may have been swapped | Avoid following links, consider same-UID adversary, use directory handles when needed |
| Library holds file handle | Windows may forbid deletion while open | Close all readers/writers/processes before cleanup |

**Unbounded deletion retries are discouraged.** Retrying only helps when the error is transient (file temporarily in use) and has an explicit deadline. Permission errors due to misconfigured policies require fixing ownership/ACLs, not increasing retry counts.

## 14. Handling Sensitive Data Written to Temporary Files

A temporary file holding tokens or identifying data needs an explicit policy:

1. **Data minimization:** does it need to touch disk at all? If data is small and processing is brief, keep it in memory.
2. **Permissions/identity:** run with a dedicated service account, private temp root, owner-only file permissions, or verified equivalent ACLs.
3. **Do not leak via names:** never embed sensitive info in prefixes/suffixes, logged paths, or exception messages returned to end users.
4. **Avoid excessive copies:** do not create unnecessary intermediate copies.
5. **Enforce storage limits:** set max bytes per request, per job, per worker, and an overall quota for the scratch volume.
6. **Define retention duration:** keep files as briefly as possible, clean up immediately upon completion/abort, and handle orphaned files by TTL.
7. **Encrypt if necessary:** consider disk or per-file encryption when the threat model includes device loss/theft, snapshots, or backups.
8. **Constrain third-party libraries:** when using image/PDF/ZIP converters, verify where the library creates its own temp files, whether it honors `TMPDIR`, and whether it cleans them up.

### Delete Is Not Secure Erase

`Files.delete(...)` removes a filesystem entry. On SSDs, copy-on-write filesystems, journals, snapshots, backups, or virtualized storage, data can persist in blocks or copies. Never promise "calling delete makes recovery impossible." For confidential data, combine encryption-at-rest, key management, retention policies, and key destruction when needed.

## 15. Uploads and Extraction: Preventing Disk Abuse

An upload-receiving system must do more than generate hard-to-guess filenames:

- Reject oversized HTTP requests before writing to scratch.
- Apply file-count and total-byte quotas per request/user/job.
- For ZIPs, defend against zip bombs: limit total decompressed data, compression ratio, entry count, directory depth, and processing time.
- Prevent path traversal: entry names like `../../secret.txt` must not escape the private temp root.
- Do not rely solely on `Path.normalize().startsWith(root)` when an adversary can control symlinks and subdirectories; enforce real-path/handle checks alongside anti-TOCTOU policies.
- Never copy the uploaded filename verbatim as the on-disk filename. Use a server-generated name and store the display name as sanitized metadata.
- After an import or format-parsing failure, delete the entire job-owned workspace rather than leaving uploaded data files behind.

**Basic** string-path traversal check snippet:

~~~java
// Illustrative: root is a normalized private directory,
// entryName comes from archive, root cannot be modified by outsiders.
Path target = root.resolve(entryName).normalize();
if (!target.startsWith(root)) {
    throw new SecurityException("Archive path escapes workspace");
}
~~~

This is **not enough against symlink races** if untrusted code can place symlinks or swap directories in the subtree. Additional control layers are needed; do not treat this snippet as complete security proof for an extractor handling hostile input.

## 16. Cleaning Up Leftover Temp Files After Crashes: Startup Sweeper

Not every application can guarantee `finally` runs. You can build a process to clean up **orphaned workspaces** based on expiration:

~~~text
scratch-root/  (root managed by the service)
  job-<generated>/        createdAt=...
  job-<generated>/        createdAt=...
  job-<generated>/        createdAt=...

Sweeper (outside the request processing path):
  -> list workspaces belonging to the application
  -> skip jobs with a valid active lease/heartbeat
  -> select directories safely past TTL
  -> verify ownership/root boundaries
  -> delete tree with no-follow rules and limits
  -> log failures for alerting
~~~

**Do not delete every directory sharing a prefix** in a shared folder; files from other jobs or users could share that prefix. A sweeper needs clear ownership (service-controlled parent directory, trusted metadata/leases, dedicated account) and safeguards against accidental deletion.

If multiple application instances share a scratch volume, each instance/job should have its own namespace and fencing/lease mechanism if required; TTL alone could delete files belonging to a very long-running active job.

## 17. Common Misconceptions

| Misconception | Reality |
|---|---|
| "An unpredictable name is enough to secure a temp file" | Requires trusted permissions and parent directory. |
| "`Files.createTempFile` only creates a name" | The method creates the actual file. |
| "After `createTempFile`, use `CREATE_NEW` to reopen" | `CREATE_NEW` will fail saying the file already exists. |
| "`0600` protects the file even if the parent lets attackers swap entries" | A writable parent can cause pathname races. |
| "Create file then chmod is equivalent to setting permissions at creation" | Creates a window of exposure; pass `FileAttribute` at creation. |
| "POSIX permission strings apply to every Windows filesystem" | Windows typically uses ACLs/a different provider. |
| "`NOFOLLOW_LINKS` blocks every filesystem attack path" | Does not block all parent components, hardlinks, or directory swaps. |
| "`Files.isSymbolicLink` then open is race-free" | There is TOCTOU between check and use. |
| "`deleteOnExit` definitely deletes on crash" | Does not run on kill/OS crash and files linger for the entire runtime. |
| "`deleteIfExists` swallows all errors" | Can still throw `IOException`/`AccessDeniedException`. |
| "Closing a channel deletes the file" | No; close and delete are separate operations. |
| "`DELETE_ON_CLOSE` always works on every provider" | May be unsupported and affects reopening by name. |
| "`walkFileTree` is always safe against concurrent attackers" | Pathnames can be swapped; use directory handles when needed. |
| "Deleting a file equals secure erase" | Data can remain in blocks/snapshots/backups. |
| "One request may wipe the whole tmp directory" | Delete only the subtree created and owned by that request. |
| "Each request can use unlimited scratch space" | Quotas, limits, and cleanup mechanisms are required. |

## 18. Implementation Checklist

1. Determine whether data is sensitive and define retention requirements.
2. Choose a service-managed parent scratch root, restricting write/traverse permissions.
3. Create a dedicated private temp directory per job for multi-step processing.
4. Use `Files.createTempFile`/`createTempDirectory` instead of fixed names or check-then-create.
5. Set `FileAttribute` at creation time if supported by the filesystem, and verify actual permissions.
6. On Windows, design/verify ACLs; if security policy cannot be met, fail closed.
7. Do not store confidential info in filenames or logged paths.
8. Avoid symlink TOCTOU; `NOFOLLOW_LINKS` is only one layer of defense.
9. Use `try-with-resources` to close streams/channels and clean up even on exceptions.
10. With async/child processes, delete only after ownership returns or operations are properly isolated.
11. Delete children before parent, do not follow symlinks, and never take `path-to-delete` from requests.
12. Record and handle cleanup failures; do not ignore errors or retry endlessly.
13. Set limits on file count/bytes/time; defend against ZIP bombs and path traversal.
14. Clean up immediately after the job; do not rely on `deleteOnExit` as the primary mechanism.
15. Run a sweeper for orphaned workspaces after crashes while avoiding active jobs.
16. Test on Windows/Linux/containers and production filesystems rather than assuming all providers share the same capabilities.

## 19. Self-Check Questions

1. Does `Files.createTempFile(...)` return just a name or create a file? **It creates the actual file.**
2. If the parent is shared and writable, is a random filename enough to prevent reading/swapping? **No; directory permissions/ownership and controls are needed.**
3. Common POSIX mode for files containing private data? **`rw-------` (`0600`).**
4. Common POSIX mode for scratch directories accessible only by the owner? **`rwx------` (`0700`).**
5. Why pass `asFileAttribute(...)` at creation time? **Avoids an exposure window before setting permissions afterward.**
6. Can POSIX mode strings be applied directly to every Windows ACL filesystem? **No.**
7. Is calling `createTempFile` then reopening with `CREATE_NEW` valid? **No, the file already exists.**
8. Does `NOFOLLOW_LINKS` prevent all types of TOCTOU? **No, it is only one control layer.**
9. Does `Files.deleteIfExists(...)` always succeed if the file is still open? **No.**
10. Does `deleteOnExit()` run when the JVM is forcibly killed? **Not guaranteed.**
11. Does `walkFileTree` follow symbolic links automatically by default? **No.**
12. Why delete children before deleting the directory? **Directories still containing entries usually cannot be deleted.**
13. Why is `try-with-resources` better for cleanup than a plain `finally`? **It manages closing and suppressed exceptions.**
14. Does `Files.delete` prove secure erasure on SSDs/snapshots? **No.**
15. If a job is cancelled during an async write, should the file be deleted immediately while the background task still uses it? **No; coordinate completion/cancel/close and ownership.**
16. What is needed to clean up files after crashes when `finally` does not run? **An ownership-bound sweeper/TTL that avoids accidental deletion.**

## 20. Official References

- [Java SE 17 — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): `createTempFile`, `createTempDirectory`, `newByteChannel`, `delete`, `deleteIfExists`, `walkFileTree`.
- [Java SE 17 — PosixFilePermissions](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/PosixFilePermissions.html): `fromString` and `asFileAttribute`.
- [Java SE 17 — PosixFileAttributeView](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/PosixFileAttributeView.html): permissions, owner, and POSIX attributes.
- [Java SE 17 — AclFileAttributeView](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/AclFileAttributeView.html): ACL policy on corresponding providers.
- [Java SE 17 — SecureDirectoryStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/SecureDirectoryStream.html): safer directory-relative operations against pathname races when supported by the provider.
- [Java SE 17 — StandardOpenOption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardOpenOption.html): `CREATE_NEW`, `TRUNCATE_EXISTING`, `DELETE_ON_CLOSE`.
- [Java SE 17 — LinkOption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/LinkOption.html): `NOFOLLOW_LINKS`.
- [Java SE 17 — File.deleteOnExit](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/File.html#deleteOnExit()): limitations of JVM-exit cleanup.
