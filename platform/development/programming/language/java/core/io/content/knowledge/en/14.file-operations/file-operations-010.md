# Step-by-Step Error Handling in Multi-File Operations with Java NIO.2

## 1. The Problem: A Multi-File Operation Is Not an Atomic Transaction

A Java feature may need to **copy 50 files**, **bulk-rename**, **export multiple documents**, or **move multiple images** to a destination directory. If the 37th file fails, what happens to the 36 files processed earlier? If an operation completes only partway, how does the program know what state to recover?

Calls such as `Files.copy`, `Files.move`, `Files.delete`, and `Files.write` operate on **one path object per call**. Looping multiple calls **does not turn them into a transaction**: a failure in a later step does not automatically undo earlier steps. An individual copy/move command also has post-error state constraints, especially across different filesystems.

Example:

```text
Source:    a.txt    b.txt    c.txt
             |        |        |
Step:       COPY     COPY     COPY
             OK       OK      ERROR
Target:    a.txt    b.txt   (missing)
```

The program needs to know **what state the target is in** and whether the application requires:

- **Fail-fast:** stop immediately on the first error, typically used when a complete and consistent output set is required.
- **Best-effort:** continue with independent files, recording success/failure individually for each file.
- **Staging + publish:** prepare temporary files, verify beforehand, then publish results; on error, clean up created artifacts when safe.
- **Post-crash recovery:** use a manifest/journal and a recovery workflow if sudden process termination must also be handled.

This lesson belongs to the **File Operations** group of Java Core I/O. The goal is to design **clear steps, ownership boundaries, recoverability, error observability, and cleanup responsibilities** rather than merely wrapping an entire loop in a single `try/catch` block.

## 2. Define Requirements Before Writing Code

First answer these questions:

1. **Must the output be an all-or-nothing complete set, or are missing files acceptable?** For example, a release bundle needs 100% of components; a personal photo-copy job might allow 97/100 to succeed.
2. **Do target files already exist?** Is overwriting allowed, or must old copies strictly be preserved?
3. **Are other processes accessing/updating the directory?** If so, checking existence before writing cannot block races.
4. **Are the files interdependent?** A metadata + payload pair must stay consistent; multiple independent log files can be processed separately.
5. **What are the sizes, counts, and locations of the files?** Dozens of small files on the same filesystem differ from millions of large files spanning multiple volumes or cloud storage.
6. **Which errors can be retried?** Denied access permissions differ from transient network drops; retries must account for target files that may already partially exist.
7. **When an error occurs, what is permitted to be deleted?** Only resources **owned** by the current run may be cleaned up, never pre-existing user data.
8. **When does output become visible to readers?** Writing directly to the final name risks letting others read incomplete versions.

For multi-file tasks, choose a verifiable **success policy**, not merely "the loop finished without throwing an exception."

### 2.1. Strategy Selection Table

| Requirement | Starting strategy | Limitations |
| --- | --- | --- |
| Every file must be prepared successfully | Fail-fast during preparation, then publish | Publishing multiple files is still not atomic |
| Independent files, individual failures tolerated | Best-effort with per-file results | Caller must know which entries failed |
| Must not touch existing targets | `CREATE_NEW` or copy/move without `REPLACE_EXISTING`; appropriate checks | Still must handle races and exceptions |
| Keep old copies if creating new copies fails | Stage in a private directory, verify, then move | Swapping multiple files has no shared transaction |
| Must recover even after mid-run stop/crash | Manifest/journal, idempotency, recovery | Increases complexity and requires data design |
| Single file needs atomic rename if supported | `Files.move` with `ATOMIC_MOVE` | Scoped per move; provider may not support it |
| Copy many large files | Streaming, quotas, concurrency limits | Do not read entire files into heap |
| Multiple writers updating the same directory | Synchronization protocol or proper locking | Checking `exists` before operating is insufficient |

## 3. Breaking the Workflow into Phases

A practical design consists of these phases:

```text
PLAN / VALIDATE
  │ Check sources, targets, name collisions, permissions, expected quotas
  ▼
STAGE
  │ Create temp files in managed area; copy/write; checksum if needed
  ▼
VERIFY
  │ Verify file count, sizes, checksums/formats as required
  ▼
PUBLISH
  │ Move to official names, update manifest/publish point
  ▼
CLEANUP / RECOVERY
    Clean up temps, aggregate errors, recover where feasible
```

Preparation steps reduce risk yet **do not eliminate all races**. For instance, `Files.exists(source)` returning `true` now does not guarantee `Files.copy(source, target)` succeeds immediately afterward; the source may be deleted/renamed or have permissions changed between the two calls. Hence **actual operations must still catch and classify errors**.

### 3.1. Planning Before Touching the Filesystem

A plan record for each file can include:

| Field | Meaning |
| --- | --- |
| Source | Source `Path` |
| Destination | Final target `Path`, name already resolved |
| Stage | Temporary `Path` created by this task |
| Expected length/hash | Size or checksum if a verification contract exists |
| State | `PLANNED`, `STAGED`, `VERIFIED`, `PUBLISHED`, `FAILED`, `CLEANED` |
| Error | Exception type, step where it occurred, message, and cause |
| Owned by task? | Whether deletion is permitted during rollback |

You should **detect duplicate destinations** in the list before running; for example, two different sources both mapped to `output/report.pdf`. Without checking, a later source can overwrite an earlier source's result.

### 3.2. Distinguishing Pre-Checks from Real Guarantees

- `Files.exists`, `Files.isReadable`, `Files.isWritable` are only **snapshots**, which can go stale immediately after returning.
- `Files.createDirectories(parent)` can create missing parent directories, yet does not guarantee permissions, quotas, or filesystem status will stay unchanged.
- For **no-overwrite** cases, avoid checking `if (!Files.exists(target))` and then opening in overwrite mode; there is a race window. Use an operation/file option expressing non-overwrite intent (such as `CREATE_NEW` when creating a new file), and handle `FileAlreadyExistsException`.
- When moving, pick options per the `Files.move` contract; `REPLACE_EXISTING` actively permits replacement, while `ATOMIC_MOVE` has provider-dependent semantics.

## 4. Classifying Errors Properly per Step

`java.nio.file.Files` typically throws `IOException` or its subclasses to describe I/O task failures. Some situations:

| Error type | Common situation | How to handle |
| --- | --- | --- |
| `NoSuchFileException` | Source disappeared, path does not exist | Record missing file; may report invalid input data |
| `FileAlreadyExistsException` | Target already exists when task forbids replacement | Preserve target; decide to rename or reject |
| `AccessDeniedException` | Missing file or directory permissions | Report access error, avoid blind retries |
| `DirectoryNotEmptyException` | Deleting a directory that still has contents | Do not recursively delete outside owned scope |
| `AtomicMoveNotSupportedException` | `ATOMIC_MOVE` unsupported on this filesystem/provider | Per policy: fail or fall back with clear notification |
| `FileSystemException` | Filesystem error carrying source/target/reason info | Preserve context, analyze cause |
| `EOFException` | Can occur in binary reads requiring exact byte counts | Reject truncated files/records |
| General `IOException` | Disk full, connection lost, write failure, filesystem error | Determine completed steps and potentially partial output |

**Not every error is an `IOException`.** `IllegalArgumentException` can occur when arguments/options are invalid; `SecurityException` can occur per environment/permissions; logic errors must also be handled at the appropriate layer. Never catch `Exception`, print "copy failed," and ignore the unknown state.

### 4.1. Recording Enough Information to Act

A useful error record includes: **source file, target file, step name, exception type, message, timestamp/request ID, count of succeeded items, and cleanup status**. Do not log sensitive paths or contents if the environment forbids it.

Illustrative example (not a standalone program):

```java
try {
    Files.copy(source, target);
} catch (NoSuchFileException e) {
    System.err.println("Missing input: " + source);
    throw e;
} catch (FileAlreadyExistsException e) {
    System.err.println("Destination conflict: " + target);
    throw e;
} catch (IOException e) {
    System.err.println("Copy failed: " + source + " -> " + target);
    throw e;
}
```

Here `source` and `target` must be valid `Path` instances. The `catch` order puts **subclasses before the superclass `IOException`**; catching `IOException` first would prevent the two specialized branches below from compiling because they would already be caught by the parent type.

## 5. Fail-Fast, Best-Effort, and Return Results

### 5.1. Fail-Fast

In the fail-fast model, when one file fails, halt subsequent steps and return error details:

```java
// Illustrative: sources is List<Path>, destinationDir is Path,
// and source names must be checked to avoid target collisions.
for (Path source : sources) {
    Path target = destinationDir.resolve(source.getFileName());
    Files.copy(source, target);
}
```

This code **does not roll back automatically**: if 3 files copied successfully and the fourth fails, the first 3 files remain. Fail-fast is a **stopping** policy, not an **undo** policy.

### 5.2. Best-Effort

If each file is independent, you can catch `IOException` **inside the loop** and continue. Results should record both successes and failures instead of only printing to the console; for instance, returning a list of `FileResult(source, destination, status, error)` to the caller.

At minimum, never lump a 95% successful batch into "completely succeeded." Report `total`, `succeeded`, `failed`, and the list of failed files. Retries can be applied to failed items, provided each step guarantees **idempotency**.

### 5.3. Two Cases Suited to Each Strategy

- **Exporting a configuration bundle of metadata + data:** publish only when every component is valid; staging then publishing is usually appropriate.
- **Transferring independent personal photos:** may tolerate a few failed photos, continue with others, and return a detailed report.

Both must still account for partial writes of **an individual file** and policies for pre-existing targets.

## 6. Java 17+ Example: Try Each File, Continue on Error

The following program creates test sources inside a temporary directory. It copies one existing file, attempts to copy a missing file, then copies the remaining file. Each attempt produces its own result; finally it prints total successes/failures. No user files are altered.

Save as **`BestEffortFilesDemo.java`**:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

public class BestEffortFilesDemo {
    static boolean copyOne(Path source, Path target) {
        try {
            Files.copy(source, target);
            System.out.println("OK: " + source.getFileName());
            return true;
        } catch (IOException failure) {
            System.out.println("FAIL: " + source.getFileName()
                    + " (" + failure.getClass().getSimpleName() + ")");
            return false;
        }
    }

    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("best-effort-");
        Path inputs = Files.createDirectory(root.resolve("inputs"));
        Path outputs = Files.createDirectory(root.resolve("outputs"));
        Path first = inputs.resolve("first.txt");
        Path missing = inputs.resolve("missing.txt");
        Path second = inputs.resolve("second.txt");

        try {
            Files.writeString(first, "one", StandardCharsets.UTF_8);
            Files.writeString(second, "two", StandardCharsets.UTF_8);

            int succeeded = 0;
            for (Path source : List.of(first, missing, second)) {
                Path target = outputs.resolve(source.getFileName());
                if (copyOne(source, target)) {
                    succeeded++;
                }
            }

            System.out.println("Succeeded: " + succeeded);
            System.out.println("Failed: " + (3 - succeeded));
        } finally {
            Files.deleteIfExists(outputs.resolve("first.txt"));
            Files.deleteIfExists(outputs.resolve("second.txt"));
            Files.deleteIfExists(first);
            Files.deleteIfExists(second);
            Files.deleteIfExists(outputs);
            Files.deleteIfExists(inputs);
            Files.deleteIfExists(root);
        }
    }
}
```

Commands to run with JDK 17+:

```bash
javac -encoding UTF-8 BestEffortFilesDemo.java
java BestEffortFilesDemo
```

**Stdout on a normal default filesystem when test operations succeed:**

```text
OK: first.txt
FAIL: missing.txt (NoSuchFileException)
OK: second.txt
Succeeded: 2
Failed: 1
```

**Explanation:**

1. `first.txt` exists and is copied to `outputs`.
2. `missing.txt` is **intentionally not created**, so `Files.copy` errors. `NoSuchFileException` is the typical outcome when the source is absent; other providers may surface errors differently, so the code prints **the actual exception class name**.
3. The loop continues and copies `second.txt`.
4. Summary separates succeeded and failed files. `copyOne` does not rethrow because this illustrates a best-effort policy; in real applications, **return/record detailed causes**, not just a boolean.
5. `finally` only attempts to delete files and directories inside the temporary area created by the example. If cleanup throws an error, that `IOException` can mask an earlier exception; production apps need a mechanism to preserve both the primary error and cleanup errors.

**Important limitation:** Standard `Files.copy` **does not replace an existing target file** without `REPLACE_EXISTING`. Under concurrent load, you must handle both target collisions and incomplete copies. The demo runs on a freshly created target directory, so no old data exists.

## 7. Java 17+ Example: Staging and Best-Effort Undo When Publishing Fails

When an entire group of files must belong together in one release, a useful approach is:

1. Copy each source to a **temporary** name inside a dedicated output directory.
2. Only once all preparation steps succeed, rename temporary files to their final names.
3. If publishing fails, attempt to delete files owned by this release run.
4. Never delete pre-existing user files.

The example below **deliberately injects a failure after publishing the first file** to test rollback. It runs in a **new, private, initially empty target directory**; thus the program owns all resulting filenames in that directory.

Save as **`StagedBatchFilesDemo.java`**:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Stream;

public class StagedBatchFilesDemo {
    static void publish(List<Path> sources, Path outputDir,
            boolean injectFailure) throws IOException {

        List<Path> staged = new ArrayList<>();
        List<Path> published = new ArrayList<>();

        try {
            // Phase 1: prepare every file in the private output directory.
            for (Path source : sources) {
                Path temp = Files.createTempFile(
                        outputDir, ".stage-", ".tmp");
                staged.add(temp);
                Files.copy(source, temp,
                        StandardCopyOption.REPLACE_EXISTING);
            }

            // Phase 2: publish under the known final filenames.
            for (int i = 0; i < staged.size(); i++) {
                Path target = outputDir.resolve(
                        "part-" + (i + 1) + ".txt");
                Files.move(staged.get(i), target);
                published.add(target);

                if (injectFailure && i == 0) {
                    throw new IOException(
                            "Simulated failure after first publish");
                }
            }
        } catch (IOException failure) {
            // Only remove files owned by this run.
            for (int i = published.size() - 1; i >= 0; i--) {
                try {
                    Files.deleteIfExists(published.get(i));
                } catch (IOException cleanup) {
                    failure.addSuppressed(cleanup);
                }
            }
            for (int i = staged.size() - 1; i >= 0; i--) {
                try {
                    Files.deleteIfExists(staged.get(i));
                } catch (IOException cleanup) {
                    failure.addSuppressed(cleanup);
                }
            }
            throw failure;
        }
    }

    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("batch-files-");
        Path inputs = Files.createDirectory(root.resolve("inputs"));
        Path outputs = Files.createDirectory(root.resolve("outputs"));
        Path one = inputs.resolve("one.txt");
        Path two = inputs.resolve("two.txt");

        try {
            Files.writeString(one, "alpha", StandardCharsets.UTF_8);
            Files.writeString(two, "beta", StandardCharsets.UTF_8);
            List<Path> sources = List.of(one, two);

            try {
                publish(sources, outputs, true);
            } catch (IOException failure) {
                System.out.println("First attempt: "
                        + failure.getMessage());
            }

            try (Stream<Path> files = Files.list(outputs)) {
                System.out.println("After rollback: " + files.count());
            }

            publish(sources, outputs, false);
            System.out.println("Published: "
                    + Files.readString(outputs.resolve("part-1.txt"))
                    + ","
                    + Files.readString(outputs.resolve("part-2.txt")));
        } finally {
            Files.deleteIfExists(outputs.resolve("part-2.txt"));
            Files.deleteIfExists(outputs.resolve("part-1.txt"));
            Files.deleteIfExists(one);
            Files.deleteIfExists(two);
            Files.deleteIfExists(outputs);
            Files.deleteIfExists(inputs);
            Files.deleteIfExists(root);
        }
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 StagedBatchFilesDemo.java
java StagedBatchFilesDemo
```

**Expected stdout in a normal test environment:**

```text
First attempt: Simulated failure after first publish
After rollback: 0
Published: alpha,beta
```

**Why is the output like this?**

- Both original files are copied into two temporary files in the same `outputs` directory. The source files always remain intact.
- On the first attempt, after moving the first temp file to `part-1.txt`, the program throws a simulated failure. The `catch` block deletes the published file and unmoved temp files, so `outputs` ends up with zero files.
- The second attempt does not inject a failure and publishes both files. `Files.readString` is used to inspect **very small test files**; in large file batches avoid reading whole files into memory just to verify.
- Cleanup calls inside `catch` use `addSuppressed`: if deleting a file also fails, **the original error is preserved** and cleanup info is attached via `Throwable.getSuppressed()`. Real programs should also log suppressed errors.

**Limitations of this pattern that must not be overlooked:**

1. This is only **best-effort compensating rollback**, not an atomic filesystem transaction. During the interval between `Files.move` calls, other readers may observe partial results.
2. When `Files.move` fails non-atomically, source/target file states may be partially indeterminate. The `published` list tracks only steps that **returned successfully**; if a failing move left a partial artifact behind, cleaning only that list may not suffice. Production systems need to scan/verify state against a **manifest** within task-owned space.
3. This pattern is **safe only when the output directory is private, has no pre-existing target files, and has no external writers modifying those filenames**. For pre-existing files, do not overwrite and then delete during rollback; keep prior versions via versioning/backup and a dedicated restore workflow.
4. `Files.createTempFile` creates the temp file first, so `Files.copy(..., REPLACE_EXISTING)` replaces only the content of **the temporary file just created by this task**. Do not apply `REPLACE_EXISTING` indiscriminately to user target names.
5. `Files.move` here **does not request `ATOMIC_MOVE`**. Even when temp and target share a directory, do not claim every provider moves atomically. If an atomic rename is desired, request `ATOMIC_MOVE` with appropriate `AtomicMoveNotSupportedException` handling.
6. If the JVM is killed or the machine loses power mid-way, `catch`/`finally` blocks **are not guaranteed to run**. You need a re-runnable recovery mechanism based on a manifest, actual state, and ownership.
7. There is no checksum or real content validation; if business logic demands integrity, verify after writing stage and before publishing.
8. When cleanup fails, remaining artifacts must be recorded for later handling. Never report "rollback succeeded 100%" merely because the cleanup loop ran.

**Practical meaning:** staging prevents publishing half-prepared data, and state tracking lists know what was done and try to undo actions owned by the run. Yet **publishing multiple filenames still has a window where partial state can be observed**.

## 8. `Files.copy`, `Files.move`, and `Files.delete`: Differences in Post-Error State

### 8.1. Copy

`Files.copy(source, target, options...)` copies content and, depending on options, some attributes. The operation can fail after the target file has already been created or contains partial data. With `REPLACE_EXISTING`, the old file may have already been replaced; this option requires explicit permission.

If output must be whole, avoid copying straight to the final result name while the task is unverified. Use a temporary name in owned space and publish once conditions are met.

### 8.2. Move

`Files.move` can be used as:

```java
// Illustrative snippet; staged and finalPath are appropriate Paths.
Files.move(staged, finalPath);
```

When wanting to request an atomic move:

```java
Files.move(staged, finalPath, StandardCopyOption.ATOMIC_MOVE);
```

**Must know:**

- `ATOMIC_MOVE` may not be supported by the filesystem/provider; in that case `AtomicMoveNotSupportedException` can be thrown.
- When `ATOMIC_MOVE` is used, semantics when the target already exists depend on the provider contract; do not use it as a universal way to guarantee "no overwrite" in all environments.
- **Atomicity of one move is not atomicity of a batch of 20 moves.** Already-moved files can still be visible before the entire batch finishes.
- When a non-atomic move fails, source and target may be in an uncertain state; inspect before retrying or cleaning up.

A stronger publishing model puts **the entire batch into a new versioned directory**, verifies it, and then switches a directory name/manifest pointer as one final publishing step. Even that design must still consider filesystem limits, name replacement semantics, and post-crash recovery.

### 8.3. Delete

`Files.delete(path)` requires deletion and fails if unable to delete; `Files.deleteIfExists(path)` does not treat a missing file as an error. Both can fail due to permissions, locks, non-empty directories, or filesystem errors.

**Use `deleteIfExists` only when policy matches:** during rollback, an already-absent file may be normal; when required to "delete exactly file X," a missing file sometimes needs to be recorded as a distinct state. Never recursively delete a user-supplied directory without proving authorized scope.

## 9. Preserving Primary Exceptions and Cleanup Errors

### 9.1. `try-with-resources`

For resources opened via `Files.newInputStream`, `Files.newOutputStream`, `Files.newBufferedReader`, or `Files.newBufferedWriter`, prefer `try-with-resources`:

```java
// Illustrative snippet: inputPath and outputPath must be valid Paths.
try (InputStream in = Files.newInputStream(inputPath);
     OutputStream out = Files.newOutputStream(outputPath)) {
    in.transferTo(out);
}
```

If the `try` body throws an exception and closing streams also fails, Java preserves the primary exception and attaches resource-closing exceptions to the **suppressed exceptions** list. This is a major advantage when diagnosing multi-step tasks.

Opening output streams requires extra care: `Files.newOutputStream(outputPath)` with default options creates the file if missing and can **truncate** an existing file. When needing to avoid destroying old content, pick the corresponding open policy (e.g., temporary name or `CREATE_NEW`).

### 9.2. `finally` Does Not Guarantee Rollback

`finally` runs when execution leaves a block through normal flow, yet is not guaranteed when a process is killed, power fails, or the system crashes. Furthermore, if `finally` throws a new exception, it can **mask the original error**.

If manual cleanup is unavoidable, preserve the original exception and attach cleanup failures with `addSuppressed`, while logging/manifesting remaining cleanup work. Never silently ignore cleanup exceptions in systems that need accurate file state.

### 9.3. Do Not Catch Errors Too Broadly

A single `catch (Exception ignored)` around the whole batch hides which step failed. Conversely, catching too narrowly around every byte operation is hard to maintain. Layer it cleanly:

- Each I/O step reports errors with `source → target` context and step name.
- The batch coordinator decides whether to stop or continue.
- The outermost layer aggregates/reports status and cleanup.
- Programming bugs and invariant violations are not hidden under a "file missing" label.

## 10. Retries and Idempotency

Retrying operations is necessary for transient failures, yet **blind retries** can cause harm:

- Retrying copy with `REPLACE_EXISTING` may overwrite a file already updated by another process.
- Retrying a log append may create duplicate records.
- Moving a source that already moved successfully while the client thought it failed can hit `NoSuchFileException` on retry.
- Deleting a filename later reused by another writer can accidentally delete new data.

**Idempotent** means repeating the same request does not alter the business outcome after the first success, under explicit assumptions. A design can use unique batch IDs, versioned targets, manifests, and checksums to detect already-completed work.

A retry workflow needs to:

1. Classify the cause (missing permissions, full disk, source temporarily unavailable, target conflict).
2. Inspect actual state of source, stage, and destination.
3. Retry only when conditions guarantee not overwriting unowned data.
4. Cap retry attempts/duration, logging attempts and failure causes.
5. Never retry indefinitely on deterministic errors like wrong permissions or invalid input.

For large batches, a manifest should record **ID, source, target, checksum if needed, and per-step status**. This data supports recovery; a database is not strictly required for every small problem.

## 11. Backups, Overwriting, and Restoring Prior Versions

If target already exists and must be preserved on error, the "delete all new outputs" model **is insufficient**, because an overwrite step may already have destroyed the old version.

Design options:

- **No overwrite:** create unique names with `CREATE_NEW` or versioned directories; publish the version once complete.
- **Separate staging + backup:** create a copy/version of the target before replacing and have a rollback workflow from backup, verifying the backup is actually usable.
- **Pointer/manifest swap:** content files are written to new versions, then a small pointer name/file is updated so readers select the completed version.
- **Application-level transactions:** if synchronizing multiple objects is required, consider a transactional metadata/data store and a purpose-built recovery procedure.

**Do not promise that multiple files can be replaced atomically simply by calling `Files.move` multiple times.** Per-file atomicity differs from whole-set atomicity. Meanwhile, restoring "the old version" requires controlling source files, backup files, and ownership; reverse copying does not automatically solve power loss or concurrent modifications.

### 11.1. Creating Temporary Files in the Right Place

`Files.createTempFile(targetDir, prefix, suffix)` places stage files in the target area, which can facilitate same-filesystem moves. However:

- Temporary names must be unique; keep a list for cleanup.
- Quotas/permissions may apply, and temp file creation itself can fail.
- If secure permissions are required, look into setting file attributes upon creation.
- Never construct temp files using a predictable fixed path vulnerable to hijacking by others, especially in public directories.

## 12. Path Safety and Resource Limits

Batch operations often receive path lists from config files or APIs. Both **target files** and **system resources** must be protected:

- Validate source/target paths, handling `..`, absolute names, symlinks, and directory boundary rules. `Path.normalize()` is purely syntactic; it does not automatically prevent TOCTOU.
- Never use `source.getFileName()` and assume all name collisions disappear: two files in different directories can share the same filename.
- Limit file count, total bytes, concurrent open streams, elapsed time, and staged disk usage.
- For multi-GB files, use streaming/copy APIs; never use `Files.readAllBytes`/`readString` across an entire batch.
- Use a deterministic output filename set; never delete anything outside the batch's scope.
- Multi-file operations on network/cross-volume filesystems have different semantics from a single local drive; test in the real deployment environment.

## 13. Common Design Mistakes

1. **Assuming a `Files.copy` loop is a transaction:** in reality a failure can leave earlier copied files behind.
2. **Catching errors at the outer boundary without knowing which file failed:** loses diagnostic ability and selective retry.
3. **Catching per-file errors and reporting the whole batch succeeded:** hides failure counts and failed items.
4. **Wiping every file in the target directory on rollback:** can delete pre-existing resources belonging to others.
5. **Not tracking created stage files:** can leave stale temporary files indefinitely.
6. **Using `REPLACE_EXISTING` casually:** can cause unrecoverable loss of old data.
7. **Using `Files.exists` and trusting target cannot change:** time-of-check-to-time-of-use still applies.
8. **Ignoring cleanup failures:** information about leftover files gets lost.
9. **Believing every `move` is atomic:** `ATOMIC_MOVE` requires support; moving file-by-file does not make the whole batch atomic.
10. **Believing catch/finally always runs on crashes:** processes can die abruptly; design recovery when required.
11. **Keeping thousands of streams open concurrently:** easily exhausts file descriptors; open/close per file scope.
12. **Counting only file count, not bytes/checksums:** contents may be corrupt or truncated even when the filename exists.
13. **Retrying immediately without checking state:** can duplicate records or overwrite newer data.
14. **Ignoring symlinks:** a path string "inside a directory" can resolve elsewhere through a link.
15. **Logging filenames while omitting the failing step:** cannot distinguish stage, verify, publish, or cleanup errors.
16. **Lacking a manifest when post-crash recovery is needed:** cannot tell which files were published and which still need processing.

## 14. Practice Exercises

1. Given three files `a.txt`, `b.txt`, `c.txt`, simulate a copy failure on `b.txt`. Contrast the remaining state under **fail-fast** vs. **best-effort**.
2. Modify `BestEffortFilesDemo` to return a list of results containing source, target, success/failure, and cause, instead of just a boolean.
3. Add a duplicate destination-name check before running the batch. How should two sources `x/a.txt` and `y/a.txt` be handled?
4. Try pre-creating `outputs/first.txt` before copying. Which exception does `Files.copy` without `REPLACE_EXISTING` throw?
5. Replace the simulated error in `StagedBatchFilesDemo` with a failure during stage creation. Is the cleanup list sufficient to remove files owned by the task?
6. Force `Files.deleteIfExists` during rollback to fail in a test environment. Inspect `getSuppressed()` on the original exception.
7. Describe a case where `Files.move` fails after creating part of the target. Why might relying solely on a list of steps that "returned successfully" be insufficient?
8. Design a manifest for a 10-file batch with states `STAGED`, `VERIFIED`, `PUBLISHED`, `FAILED`; handle resuming after the process is killed.
9. Explain why backing up before overwriting is insufficient if the backup itself can also fail or be overwritten.
10. Compare "10 moves with `ATOMIC_MOVE`" vs. "one operation publishing an entire completed versioned directory." What filesystem conditions do both require?
11. For 1,000 multi-GB files, design policies limiting open streams, total bytes, temporary disk usage, and elapsed time.
12. Explain why `Path.normalize()` does not replace symbolic link and permission checks when letting users upload files into a controlled directory.

## 15. Pre-Deployment Checklist

- [ ] Decided between fail-fast, best-effort, or staging/publish?
- [ ] Checked source → target mappings, name collisions, and overwrite policy?
- [ ] Clearly identified which resources belong to the batch and which must never be deleted?
- [ ] Capped total file count, total bytes, concurrency, and duration?
- [ ] Separated preparation, verification, publishing, and cleanup errors?
- [ ] Preserved primary exceptions along with suppressed exceptions from cleanup?
- [ ] Defined post-error, post-retry, and post-crash states?
- [ ] Verified how results are exposed when only part of a batch succeeds?
- [ ] Verified `Files.copy`/`move`/`delete` semantics on the actual filesystem?
- [ ] Handled permissions, symlinks, concurrent changes, and disk-full conditions?
- [ ] Determined whether checksums/versioning/manifests are needed?
- [ ] Tested failure injection at each critical step?

## 16. Summary

Handling multiple files is a **state and ownership problem**, not just a `Files.copy` loop. A sound design decides clearly whether to **stop or continue**, separates **plan → stage → verify → publish → cleanup**, records per-step success/failure, and strictly avoids deleting resources not owned by the task.

`try-with-resources` and `IOException` help manage I/O errors; `addSuppressed` preserves cleanup info; `ATOMIC_MOVE` (where supported) helps with **a single move step**, yet does not create a transaction for the entire batch. For strong consistency, staged output, manifests/versioning, integrity checks, retry policies, and recovery are required.

**Practical rule:** After every step, you must be able to answer **"which files were modified, which files remain owned by this run, and what will happen if the next step fails?"** Only when you can answer that with concrete data can a system handle multi-file errors verifiably and safely.
