# Creating Temporary Files with Proper Permissions and Controlled Cleanup in Java NIO

## 1. Why Are Temporary Files Also a Security Issue?

Java applications often create temporary files to process uploaded images, export reports, extract archives, sort large datasets, store intermediate results, or transfer data between processing steps. Just because a file exists only briefly **does not mean it is safe**.

Real-world risks include:

- **Data exposure:** a file containing tokens, customer data, uploaded content, or secrets can be read by other users on the machine.
- **Name prediction and squatting:** using a fixed name like `/tmp/report.txt` and overwriting it can cause races or collisions between processes.
- **Symbolic-link attacks:** an attacker makes the temporary path point to another target file before the application reopens it.
- **TOCTOU:** the application checks `exists()`, `isSymbolicLink()`, or permissions at time A, yet the file is replaced before use at time B.
- **Resource leaks:** open files/channels, leftover temporary files and directories after exceptions, cancellations, or timeouts.
- **Disk exhaustion:** unbounded uploads create huge temporary files, or thousands of requests leave files behind until the service stops working.
- **Incomplete deletion:** calling `delete()` does not mean old data has been physically erased from SSDs, swap, snapshots, backups, or journals.

Goals of this lesson: **create temporary files with the right API; apply permissions at creation time; isolate the working directory; use resources with clear ownership; clean up on success or failure; understand the remaining limitations.**

## 2. Which API Should You Choose to Create a Temporary File or Directory?

Java NIO.2 (package `java.nio.file`) provides these methods:

~~~java
Path file = Files.createTempFile("prefix-", ".tmp");
Path dir  = Files.createTempDirectory("job-");

// Specify a trusted parent directory:
Path fileInDir = Files.createTempFile(dir, "data-", ".bin");
Path nestedDir = Files.createTempDirectory(dir, "stage-");
~~~

`Files.createTempFile(...)` and `Files.createTempDirectory(...)` **create the object in the filesystem right at the call**, rather than merely generating a filename string for later use.

When supported by the provider, creating the new entry checks existence and creates the file **atomically with respect to the relevant filesystem operation**, avoiding the common bug of “pick a name then check it does not exist”. They do not establish a lock or transaction contract for operations **using the file after creation**.

| API | Result | When to Use? |
|---|---|---|
| `Files.createTempFile(prefix,suffix,attrs...)` | Temporary file in provider-determined location | Standalone operation needing no dedicated tree |
| `Files.createTempFile(dir,prefix,suffix,attrs...)` | Temporary file inside chosen directory | Wanting to manage permissions/full lifecycle of a job |
| `Files.createTempDirectory(prefix,attrs...)` | Temporary directory in provider-determined location | Needing an isolated place for multiple intermediate files |
| `Files.createTempDirectory(parent,prefix,attrs...)` | Temporary subdirectory inside parent | Service with an administrator-controlled scratch area |
| `Files.createFile(path,attrs...)` | File with a specific name, must not exist yet | When the application explicitly manages the pathname and requires create-new |
| `File.createTempFile(...)` | Legacy `java.io.File` API | Legacy systems; new code should prefer NIO `Files` |

**Do not write:**

~~~java
// Wrong pattern: fixed name, check then create.
Path p = Path.of("/tmp/my-app-export.csv");
if (!Files.exists(p)) {
    Files.writeString(p, confidentialData);
}
~~~

There is a race between `exists()` and `writeString()`. In addition, `Files.writeString` with its default options can create a new file or truncate an existing file, making it unsuitable when foreign data must not be overwritten.

**Instead use** `Files.createTempFile(...)` or a create-new call with well-defined semantics. Avoid generating temporary names yourself using timestamps, thread IDs, or weak random values and placing them in a shared directory.

### Are Prefix/Suffix Secret Information?

No. Prefixes/suffixes help identify file types and assist operations; API-generated names help avoid collisions, **not replace access permissions**. Do not treat an unpredictable name as the sole layer of defense. Never put tokens, passwords, customer emails, or sensitive data into filenames because names can appear in logs, directory listings, or crash reports.

## 3. Choosing the Parent Directory: Not Every “Temp” Location Is Trustworthy

`Files.createTempFile("x-", ".tmp")` and `createTempDirectory("x-")` without a directory argument use the provider's default location. For the default provider, this location is typically tied to the `java.io.tmpdir` system property.

However:

- The actual temp location can differ across OSes/containers, runtime configurations, or providers.
- A shared temp directory may allow multiple users to create entries inside it.
- Temp on a network volume has different permissions, latency, visibility, and cleanup behavior than local disk.
- An application running inside a container may have an ephemeral filesystem, dedicated quotas, or read-only mounts.
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

When only one job has write access to its dedicated directory, many risks of other users swapping pathnames drop significantly. However, an actor running under **the same OS account with equivalent privileges**, or a privileged user, can still interfere; a `0700` directory does not create a sandbox against the owning principal itself.

### Directory Permissions Matter Just as Much as File Permissions

Even with a file in mode `0600`, an overly permissive parent directory can allow the pathname to be renamed/deleted, causing a race on reopen. On POSIX systems, a private scratch directory typically uses mode `0700` (owner read/write/execute, nothing granted to group/others).

**Do not check only file permissions while forgetting the parent chain.** Directories holding confidential data should be owned by a trusted principal, non-writable by unauthorized actors, and any symlinks/mounts in the path must obey control policies.

## 4. POSIX: Grant Permissions **at Creation Time**, Avoid “Create Then `chmod`”

On POSIX-compatible filesystems, basic permissions are often represented by strings:

- `rw-------`, i.e., mode `0600`: only the owner can read/write the file.
- `rwx------`, i.e., mode `0700`: only the owner can read/write/traverse the directory.
- `r--r--r--`, i.e., mode `0444`: read-only, **unsuitable** if the file must be modified during processing.
- Group/others permissions can expand who may read or alter the data.

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

// Create with permission attributes right inside the creation operation:
Path jobDir = Files.createTempDirectory("secure-job-", privateDir);
Path artifact = Files.createTempFile(jobDir, "data-", ".bin", privateFile);
~~~

This is an **illustrative snippet** requiring `java.nio.file.Files` and `Path` imports. It only works properly on providers supporting POSIX attributes at that location.

Important properties:

1. File attributes are passed into the **creation operation**, avoiding a window between creating a file with overly broad permissions and tightening them afterward.
2. A provider may reject unsupported attributes with `UnsupportedOperationException`; never ignore it and pretend permissions were protected.
3. Effective permissions may be further restricted by platform umask/ACL/policies; **re-verify actual permissions** if permissions are a security invariant.
4. Calling `setPosixFilePermissions(path, ...)` on an **already-existing** file is a separate permission change and does not retroactively undo earlier data exposure.

### Why Is “Create Then Fix Permissions” Dangerous?

~~~java
// Should not be used for sensitive data in a shared directory.
Path tmp = Files.createTempFile("secret-", ".bin");
Files.setPosixFilePermissions(
        tmp, PosixFilePermissions.fromString("rw-------"));
~~~

With the default provider, `createTempFile` may apply tighter default permissions than a regular file creation call, yet **do not assume every provider enforces your application's policy**. If specific permissions are mandatory, supply attributes at creation time and verify them on the target platform.

**Note on owner privileges:** mode `0600` does not stop malware running under the same account, root/administrator, or privileged backup mechanisms; use sandboxing/OS account isolation when the threat model demands it.

## 5. Windows and Non-POSIX Filesystems

Windows typically uses **ACLs (Access Control Lists)** rather than relying purely on POSIX permission bits. `PosixFilePermissions` syntax **is not a portable policy across all providers**.

Check support before using:

~~~java
boolean supportsPosix = FileSystems.getDefault()
        .supportedFileAttributeViews()
        .contains("posix");
~~~

This only checks the capability of the **default filesystem**; the actual path could still lie on a different provider/file store. When code handles multiple filesystems, handle errors and verify on the target path itself.

For Windows or ACL-based filesystems:

- Use the file owner and `AclFileAttributeView` / `AclEntry` when policy requires setting specific permissions.
- Control **inherited ACLs** from parent directories; do not assume other accounts lack access just because the program only knows the current user's name.
- Since file shares/volumes can differ, creating a file with ACL attributes at creation time depends on the provider; check platform documentation and run real security tests.
- If the minimum policy cannot be verified, **fail closed** for sensitive data instead of silently creating files under unknown permissions.
- Do not mechanically translate `chmod 0600` into “equivalent safety on every Windows filesystem”.

Related API:

~~~java
// Illustrates accessing the ACL view, not a complete policy.
AclFileAttributeView view = Files.getFileAttributeView(
        path, AclFileAttributeView.class);
if (view == null) {
    throw new UnsupportedOperationException("ACL view unavailable");
}
// An actual ACL must be designed around the owner, service account,
// authorized identities, and inherited parent permissions.
~~~

The snippet's imports belong to `java.nio.file` and `java.nio.file.attribute`. Never copy an ACL from another environment and blindly apply it to a temp directory/file, as doing so can lock out the application itself or open unintended access.

## 6. Reopening Temporary Files: Avoid Symbolic Links and Redundant Operations

After creation, an application typically writes the file, reads it back, passes it to the next step, or deletes it. If another party can replace the pathname during this window, the reopen can point to **a different object**.

Defense points:

1. Create files under a parent directory writable only by a trusted account.
2. Avoid keeping fixed names in publicly shared directories.
3. When reopening, consider `LinkOption.NOFOLLOW_LINKS` in APIs accepting `OpenOption` to reject symlinks at the final component, **if supported by the provider**.
4. Do not treat `Files.isSymbolicLink(path)` followed by `open(path)` as a race-free check: the pathname can change between the two calls.
5. Do not assume `NOFOLLOW_LINKS` checks every parent component or stops all hardlink/mount/directory-swap attacks.
6. Where an adversary can modify the directory tree, consider `SecureDirectoryStream` or OS-level APIs capable of operating relative to a safe directory handle when supported.

Example of reopening a created file:

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

The snippet above uses a previously created `artifact`; it is not standalone runnable. Because `Files.createTempFile(...)` **already created the file**, reopening it to write **does not need** `CREATE` or `CREATE_NEW`. In particular, `CREATE_NEW` on the freshly created path will **fail because the file already exists**.

### Why Is `CREATE_NEW` a Different Tool?

`Files.newByteChannel(path, Set.of(CREATE_NEW, WRITE), attrs...)` is used when you want to **create a new file at a chosen pathname** and strictly never overwrite an existing entry. It does not replace `Files.createTempFile` when you already have a temporary file. If you need to create and open with the same atomic primitive, you can use `CREATE_NEW` with a chosen path under a trusted parent, while managing name selection, collisions, and permissions yourself.

## 7. Lifecycle Management: Which Resources Must Close Before Deletion?

Temporary files are often held open by:

- `InputStream` / `OutputStream`.
- `BufferedReader` / `BufferedWriter`.
- `FileChannel` / `SeekableByteChannel`.
- Libraries processing images, ZIP, PDF, CSV, XML, or database engines.
- A child process using the path.
- A thread running an asynchronous operation.

**Ownership principle:** the component creating a resource must define who is responsible for closing it and who is authorized to delete the file. If an I/O operation is still pending or another process has not finished, immediate deletion can fail or exhibit OS-dependent behavior.

Typical pattern:

~~~java
Path file = Files.createTempFile("work-", ".tmp");
try {
    try (OutputStream out = Files.newOutputStream(file)) {
        out.write(bytes);
    }

    // Process with a file-reading library after the writer is closed.
    consumeFile(file);
} finally {
    Files.deleteIfExists(file);
}
~~~

This is illustrative code requiring imports and application-defined `bytes`/`consumeFile`. The `finally` block runs on normal completion as well as normal exceptions, yet **there is no guarantee** it executes on forced process kill, JVM crash, or power loss.

### Why Is `try-with-resources` Better?

`try-with-resources` automatically closes `AutoCloseable` objects on exit, even when a processing step throws an exception. If both the body and `close()` throw errors, Java preserves the primary error and attaches the close error as a **suppressed exception** — much better than having a cleanup error in `finally` mask the original failure cause.

One way to structure this is creating a temporary workspace manager implementing `AutoCloseable`:

~~~java
try (TempWorkspace workspace = TempWorkspace.create()) {
    // Create and process files inside the workspace.
} // close() deletes contents and directory per rules.
~~~

The complete example program in the next section implements this pattern.

## 8. Complete Java 17+ Program: Private `0700` Directory, `0600` File, and Cleanup

The program below targets **POSIX filesystems** and intentionally **fails closed** if the default filesystem lacks the POSIX attribute view. This means:

- On Linux/macOS or a compatible POSIX filesystem: creates an owner-only directory, creates an owner-only file, and verifies there are no group/others permissions.
- On ACL-only Windows: does not attempt to create sensitive files with permissions unprovable via POSIX; prints a notice and exits cleanly.
- Opens the file for writing with `NOFOLLOW_LINKS`; uses `try-with-resources` to close the channel before deletion.
- Deletes files and subdirectories using `Files.walkFileTree(...)`, without following symbolic links in default traversal.
- Prints stable output without leaking random temporary file paths.

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

    // Scope owning the entire temporary directory tree.
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

**Stdout when the default filesystem does not support the POSIX view:**

~~~text
POSIX unavailable: refuse sensitive temp
~~~

Explanation:

1. The program verifies POSIX availability instead of silently skipping the security requirement.
2. `Files.createTempDirectory(..., asFileAttribute(0700))` creates an isolated workspace.
3. `Files.createTempFile(root,..., asFileAttribute(0600))` creates the file inside the workspace with the required permissions right at creation time.
4. `getPosixFilePermissions(...)` verifies no permissions are granted to group/others. This check **does not inspect additional ACLs or privileged mechanisms outside POSIX**.
5. `NOFOLLOW_LINKS` rejects symlinks at the final file upon reopen if the provider implements the option properly. A private parent reduces the risk of entry replacement by other users, though it does not guarantee safety against an attacker with the same UID.
6. Writing via `SeekableByteChannel` uses a loop because you must not assume a single `write` call transfers the entire `ByteBuffer` in every case.
7. `TempWorkspace.close()` uses `walkFileTree`, calling `Files.delete` on each file first before deleting the directory. By default traversal does not follow symlinks; if a symlink appears in the directory, it is handled as an entry to delete the link without following the target.
8. `try-with-resources` ensures cleanup runs on normal exit or exception.
9. `cleanup=true` is printed only after deletion completes and `Files.notExists(root, NOFOLLOW_LINKS)` confirms no entry remains at that path.

**Limitation:** this is a POSIX example and does not implement a Windows ACL policy. Without POSIX support, it refuses to create a sensitive workspace rather than falling back to unverified default permissions. For cross-platform needs, build an equivalent policy on the ACL provider and test actual permissions.

## 9. Cleaning Up a Single File vs. Cleaning Up a Directory Tree

### A Standalone Temporary File

If there is only one file:

~~~java
Path temp = Files.createTempFile("job-", ".dat");
try {
    process(temp);
} finally {
    Files.deleteIfExists(temp);
}
~~~

`process` is an application method. Every stream/channel opened by `process` must be closed before reaching deletion. Using `deleteIfExists` avoids treating “another step already deleted the file” as an error, yet **does not swallow all deletion errors**: an open file, permission denied, or I/O failure can still throw `IOException`.

### Multiple Files and Subdirectories

You cannot delete a directory **that still contains files** with a single `Files.delete(directory)`. Children must be deleted first and parents afterward. `Files.walkFileTree` is suitable when the application **owns the entire tree** and the threat model prevents outsiders from mutating the tree during cleanup.

Do not use:

~~~java
// Insufficient if the directory still contains entries:
Files.delete(tempDirectory);
~~~

Nor should you write a recursive delete method that accepts an arbitrary path from user input and deletes unchecked. If a wrong pathname is passed, you could accidentally delete a production directory.

**Safety rules for tree cleanup:**

- Have proof that the application created and owns the root workspace.
- Never accept the directory-to-delete directly from a request body or query parameter.
- Never follow symbolic links (`walkFileTree` does not enable `FOLLOW_LINKS` by default).
- If defense against a same-account attacker modifying pathnames is needed, use a stronger mechanism like `SecureDirectoryStream` where supported by the filesystem/provider, rather than assuming walk-and-delete is always race-free.
- Log cleanup failures without leaking sensitive information inside filenames/paths.
- If deletion fails, alert monitoring and have a follow-up policy; never silently ignore it.

## 10. Why `deleteOnExit()` Should Not Be the Primary Cleanup Mechanism

Java has:

~~~java
temp.toFile().deleteOnExit();
~~~

It asks the JVM to try deleting the file when the JVM **terminates normally** via a shutdown hook; this is not a sufficient guarantee for server environments or sensitive data.

Drawbacks:

- No guarantee of running when the JVM is forcibly killed, loses power, or suffers an OS crash.
- Server applications can run for days or weeks; the file remains present the entire time.
- The list of files registered with `deleteOnExit` stays in JVM memory for the process lifetime; using it across millions of requests increases memory consumption.
- The file may still be in use by another process or fail to delete due to permissions.
- When a directory and many children exist, registration order must be considered; do not rely on a hook instead of clear workspace ownership.
- In container/Kubernetes environments, lifecycles can be cut short or persistent volume mounts can still retain leftover files.

**Recommendation:** use `try-with-resources`/`finally` to delete immediately when the job finishes. You may consider `deleteOnExit()` as a secondary safety net for short-lived CLI tools, but never treat it as a cleanup SLA or security mechanism.

## 11. `DELETE_ON_CLOSE`: Useful but Limited

`StandardOpenOption.DELETE_ON_CLOSE` requests deleting the file when the channel closes, depending on provider support. It can be used in cases where a temporary file only needs to exist while the channel is open:

~~~java
// Illustrative code, temporaryFile was already created by the application.
try (SeekableByteChannel channel = Files.newByteChannel(
        temporaryFile,
        Set.<OpenOption>of(
                StandardOpenOption.WRITE,
                StandardOpenOption.DELETE_ON_CLOSE,
                LinkOption.NOFOLLOW_LINKS))) {
    // Process data while the channel remains open.
}
~~~

What you should not assume:

- Not every filesystem/provider supports every option.
- Do not rely on the file remaining visible under its pathname while the channel is open. Some systems may unlink the entry early or have different semantics.
- If another library needs to **reopen the file by name**, `DELETE_ON_CLOSE` can break the workflow.
- It does not guarantee secure physical erasure of all data copies.
- It does not replace cleaning up **other files and containing directories**.

For multi-step pipelines, a private directory plus explicit cleanup is usually easier to control.

## 12. Exceptions, Cancellation, and Cleanup Errors: Avoid Losing the Root Cause

Suppose upload processing throws an exception, and then deleting the file in `finally` also fails:

~~~java
Path file = Files.createTempFile("upload-", ".tmp");
try {
    importData(file);
} finally {
    Files.deleteIfExists(file);
}
~~~

If `importData` threw an error and `deleteIfExists` throws another, the cleanup error can **mask the original business error** in this `finally` style. When that matters, use an `AutoCloseable` resource wrapper cleaned up via `try-with-resources` as in Section 8: Java tracks **suppressed exceptions** to preserve the root cause.

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

Illustrative code; `runJob` must close/clean up its own resources via `try-with-resources` per policy. In production, error logs should not include sensitive input contents.

### Asynchronous I/O and Child Processes

If a temporary file is used by an `AsynchronousFileChannel`, another process, or a background task, closing a wrapper on the main thread **does not prove** all pending operations have finished and results have been consumed. Lifecycle coordination is required:

~~~text
CREATE TEMP -> SUBMIT WORK -> WAIT / CANCEL / DRAIN
                              |
                              v
                     CLOSE ALL FILE HANDLES
                              |
                              v
                      DELETE TEMP WORKSPACE
~~~

Deletion time should only arrive once no legitimate consumer still needs the file. If a job is cancelled, cancel the task first, wait or isolate properly, then clean up with appropriate timeouts/monitoring.

## 13. Cleanup Failures in Production Environments

| Issue | Possible Cause | Appropriate Response |
|---|---|---|
| `DirectoryNotEmptyException` | Child not yet deleted, another process just created a file | Check ownership, traverse in right order, restrict writers |
| `AccessDeniedException` | Permissions/ACL forbid deletion or file is held open | Close handles, verify policy, record error |
| `NoSuchFileException` | Another actor already deleted it | `deleteIfExists` when expected/valid |
| `FileSystemException` | Faulty volume, file busy, provider constraint | Emit operational alert and bounded retry if safe |
| Disk full | Insufficient space for file/metadata writes | Enforce quotas, fail request, clean up created files |
| Process crash/KILL | `finally`/shutdown hook did not run | Ownership- and TTL-based startup sweeper outside request path |
| Symlink appears in temp tree | Pathname may have been swapped | Avoid following links, consider same-UID adversary, use directory handles when needed |
| Library holds file handle | Windows may forbid deleting an open file | Close all readers/writers/processes before cleanup |

**Unbounded deletion retries are discouraged.** Retrying only helps when the error is transient (file temporarily still in use) and has a clear deadline. Permission errors due to misconfigured policies require fixing ownership/ACLs, not increasing retry counts.

## 14. Handling Sensitive Data When Writing to Temporary Files

A temporary file containing tokens or personally identifiable information should have a clear policy:

1. **Data minimization:** does it need to hit disk at all? If data is small and processing is brief, it may be handled in memory.
2. **Permissions/identity:** run with a dedicated service account, private temp root, owner-only file permissions, or verified equivalent ACLs.
3. **No name leakage:** never put sensitive info into prefixes/suffixes, logged paths, or exception messages shown to end users.
4. **Do not duplicate excessively:** avoid creating unnecessary intermediate copies.
5. **Enforce capacity limits:** set max bytes per request, per job, per worker, and a quota on the whole scratch volume.
6. **Define retention duration:** keep files as briefly as possible, delete immediately on completion/abort, and handle orphaned files by TTL.
7. **Encrypt if needed:** consider disk-level or per-file encryption when the threat model includes device loss/theft, snapshots, or backups.
8. **Constrain third-party libraries:** when using image/PDF/ZIP conversion tools, determine where the library creates its own temp files, whether it respects `TMPDIR`, and whether it cleans up.

### Delete Is Not Secure Erase

`Files.delete(...)` removes a filesystem entry. On SSDs, copy-on-write filesystems, journals, snapshots, backups, or virtualized storage, data can persist in blocks or copies. Never promise “calling delete makes recovery impossible”. For confidential data, combine encryption-at-rest, key management, retention policies, and key destruction when needed.

## 15. Uploads and Extraction: Preventing Disk Abuse

An upload-receiving system must do more than generate unpredictable filenames:

- Reject oversized HTTP requests before writing to scratch space.
- Enforce file-count and total-byte quotas per request/user/job.
- For ZIPs, defend against zip bombs: limit total decompressed data, compression ratio, entry count, directory depth, and processing time.
- Prevent path traversal: entry names like `../../secret.txt` must not escape the private temp root.
- Do not rely solely on `Path.normalize().startsWith(root)` when an adversary can control symlinks and subdirectories; validate real paths/handles alongside anti-TOCTOU policies.
- Never copy the uploaded filename verbatim onto disk. Use server-generated names and store the sanitized display name as metadata.
- After import or format-parsing errors, clean up the entire job-owned workspace instead of leaving uploaded data files behind.

A **basic** string-path traversal check:

~~~java
// Illustrative: root is a normalized private directory,
// entryName comes from archive, root cannot be modified by outsiders.
Path target = root.resolve(entryName).normalize();
if (!target.startsWith(root)) {
    throw new SecurityException("Archive path escapes workspace");
}
~~~

This **is not sufficient against symlink races** if untrusted code can place symlinks or modify directories in the subtree. Additional controls are needed; do not treat this snippet as complete security proof for an extractor accepting hostile content.

## 16. Cleaning Up Leftover Temporary Files After a Crash: Startup Sweeper

Not every application can guarantee `finally` runs. You can build a sweeper for **orphaned workspaces** based on expiration:

~~~text
scratch-root/  (service-managed root)
  job-<generated>/        createdAt=...
  job-<generated>/        createdAt=...
  job-<generated>/        createdAt=...

Sweeper (outside the request handling path):
  -> list application-owned workspaces
  -> skip jobs with an active valid lease/heartbeat
  -> select directories past a safe TTL
  -> verify ownership/root boundaries
  -> delete tree with no-follow and bounded limits
  -> log failures for alerting
~~~

**Do not delete every directory sharing a prefix** inside a shared folder; files belonging to other jobs or users could share the prefix. A sweeper needs clear ownership (application-controlled parent directory, trusted metadata/leases, dedicated account) and safeguards against accidental deletion.

If multiple application instances share a scratch volume, each instance/job should have its own namespace and fencing/lease mechanism if required; TTL alone could delete files of a very long-running active job.

## 17. Common Misconceptions

| Misconception | Reality |
|---|---|
| “An unpredictable name is enough to secure a temp file” | Trusted permissions and parent directory are also required. |
| “`Files.createTempFile` only generates a name” | The method actually creates the file. |
| “After `createTempFile`, reopen with `CREATE_NEW`” | `CREATE_NEW` will fail because the file already exists. |
| “`0600` protects the file even if the parent lets attackers swap entries” | A writable parent can allow pathname races. |
| “Create file then `chmod` equals setting permissions at creation” | There can be an exposure window; pass `FileAttribute` at creation. |
| “POSIX permission strings apply to every Windows filesystem” | Windows typically uses ACLs/other providers. |
| “`NOFOLLOW_LINKS` blocks every filesystem attack vector” | It does not block all parent components, hardlinks, or directory swaps. |
| “`Files.isSymbolicLink` then open is race-free” | TOCTOU exists between check and use. |
| “`deleteOnExit` definitely deletes on crash” | Does not run on kill/OS crash, and files linger throughout runtime. |
| “`deleteIfExists` swallows all errors” | It can still throw `IOException`/`AccessDeniedException`. |
| “Closing the channel deletes the file” | No; close and delete are separate operations. |
| “`DELETE_ON_CLOSE` always works on every provider” | May be unsupported and affects reopening the file. |
| “`walkFileTree` is always safe against concurrent attackers” | Pathnames can be swapped; use directory handles when needed. |
| “Deleting a file means secure erase” | Data may persist in blocks/snapshots/backups. |
| “One request can wipe the entire `tmp` directory” | Delete only the subtree created and owned by that request. |
| “Each request can use unlimited scratch space” | Quotas, limits, and cleanup mechanisms are mandatory. |

## 18. Implementation Checklist

1. Determine whether the data is sensitive and define retention requirements.
2. Choose a service-managed scratch parent root and restrict write/traverse permissions.
3. Create a dedicated private temp directory per job for multi-step processing.
4. Use `Files.createTempFile/createTempDirectory` instead of fixed names or check-then-create.
5. Supply `FileAttribute` at creation time if supported by the filesystem, and verify effective permissions.
6. On Windows, design/verify ACLs; if the security policy cannot be satisfied, fail closed.
7. Never store secrets in filenames or logged paths.
8. Avoid symlink TOCTOU; `NOFOLLOW_LINKS` is only one defense layer.
9. Use `try-with-resources` to close streams/channels and clean up even on exceptions.
10. With async I/O or child processes, delete only after ownership returns or operations are properly isolated.
11. Delete children before parents, do not follow symlinks, and never take path-to-delete from requests.
12. Record and handle cleanup failures; do not ignore errors or retry infinitely.
13. Enforce file-count/byte/time limits; defend against ZIP bombs and path traversal.
14. Clean up immediately after the job finishes; do not rely on `deleteOnExit` as the primary plan.
15. Run a sweeper for orphaned workspaces after crashes without deleting active jobs.
16. Test on Windows/Linux/containers and production filesystems; never assume all providers have identical capabilities.

## 19. Self-Check Questions

1. Does `Files.createTempFile(...)` only return a name or create a file? **It actually creates the file.**
2. If the parent is shared and writable, is a random filename enough to prevent reading or swapping? **No; permissions/ownership and directory control are needed.**
3. Which POSIX mode is usually appropriate for a file holding private data? **`rw-------` (0600)**.
4. Which POSIX mode is usually appropriate for a scratch directory accessible only by its owner? **`rwx------` (0700)**.
5. Why pass `asFileAttribute(...)` at creation time? **To avoid an exposure window before setting permissions afterward.**
6. Can POSIX mode strings be applied directly to every Windows ACL filesystem? **No.**
7. Is reopening a `createTempFile` result with `CREATE_NEW` valid? **No, the file already exists.**
8. Does `NOFOLLOW_LINKS` block every kind of TOCTOU? **No, it is only one control layer.**
9. Does `Files.deleteIfExists(...)` always succeed if the file is still open? **No.**
10. Does `deleteOnExit()` run when the JVM is forcibly killed? **Not guaranteed.**
11. Does `walkFileTree` follow symbolic links by default? **No.**
12. Why delete children before deleting the directory? **A directory that still contains entries generally cannot be deleted.**
13. Why is `try-with-resources` better for cleanup than a simple `finally`? **It manages closing and suppressed exceptions.**
14. Does `Files.delete` guarantee secure erase on SSDs/snapshots? **No.**
15. If a job is cancelled mid-async write, should you delete the file immediately while the background task still uses it? **No; completion/cancellation/closing and ownership must be coordinated.**
16. What is needed to clean up files after a crash when `finally` never ran? **An ownership-bound sweeper/TTL that avoids deleting active jobs.**

## 20. Official References

- [Java SE 17 — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): `createTempFile`, `createTempDirectory`, `newByteChannel`, `delete`, `deleteIfExists`, `walkFileTree`.
- [Java SE 17 — PosixFilePermissions](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/PosixFilePermissions.html): `fromString` and `asFileAttribute`.
- [Java SE 17 — PosixFileAttributeView](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/PosixFileAttributeView.html): permissions, owner, and POSIX attributes.
- [Java SE 17 — AclFileAttributeView](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/AclFileAttributeView.html): ACL policy on supporting providers.
- [Java SE 17 — SecureDirectoryStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/SecureDirectoryStream.html): safer directory-relative operations against pathname races when supported by the provider.
- [Java SE 17 — StandardOpenOption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardOpenOption.html): `CREATE_NEW`, `TRUNCATE_EXISTING`, `DELETE_ON_CLOSE`.
- [Java SE 17 — LinkOption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/LinkOption.html): `NOFOLLOW_LINKS`.
- [Java SE 17 — File.deleteOnExit](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/File.html#deleteOnExit()): limitations of cleanup on JVM termination.