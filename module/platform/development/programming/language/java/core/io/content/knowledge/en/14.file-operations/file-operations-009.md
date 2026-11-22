# Do Not Check First and Assume the Subsequent Operation Will Succeed in Java I/O

## 1. The Problem: True at Check Time Does Not Guarantee True Later

When working with files, a common pattern is checking a condition beforehand and then **assuming that condition remains true** when performing the action:

~~~java
// UNSAFE if treating the exists() result as a guarantee.
if (Files.exists(path)) {
    String content = Files.readString(path);
    process(content);
}
~~~

At the moment `Files.exists(path)` runs, the file may exist. However, between the check and `Files.readString(path)`, another process, another thread, a sync service, a user, or your own program code can **delete, rename, replace, or change access permissions**. As a result, the read operation can still fail.

~~~text
Time            Application A                  Actor B
----------      ---------------------------    -----------------------
T1              Files.exists(path) == true
T2                                             Files.delete(path)
T3              Files.readString(path)
                -> IOException
~~~

This is a **TOCTOU — Time Of Check To Time Of Use** bug (the gap between check time and use time). TOCTOU does not appear only with files: sockets, database records, locks, transactions, and shared resources all exhibit similar situations.

**Key learning principle:** An I/O operation **must be checked at the moment of execution** through its return value and exceptions; a prior check provides only instantaneous information, **not a guarantee about the future**.

Calling `Files.exists()` is not always wrong. What is wrong is **relying completely on that result to omit error handling on the subsequent operation**, or using check-then-act to simulate an operation that actually needs atomicity.

## 2. Commonly Misunderstood Checks

| Check | Information it provides | What it does NOT guarantee |
| --- | --- | --- |
| `Files.exists(path)` | Path appears to exist at check time | Subsequent open/read/delete/rename will succeed |
| `Files.notExists(path)` | Basis to confirm path does not exist | No one creates the path afterward |
| `Files.isReadable(path)` | Assesses readability at check time | Subsequent read won't hit permission, lock, race, or I/O errors |
| `Files.isWritable(path)` | Assesses writability at check time | Subsequent write will succeed and have enough space |
| `Files.isRegularFile(path)` | Identifies target type at check time | Target isn't swapped for a directory or symlink |
| `Files.isDirectory(path)` | Identifies directory at check time | Subsequent directory open/child traversal will succeed |
| `Files.size(path)` | Observed file size at call time | Size won't change while reading |
| `Files.getLastModifiedTime(path)` | Current modification timestamp metadata | Content won't change; metadata is not a lock |

**Special case of `exists()` and `notExists()`:** Java allows **both to return false** if status cannot be determined due to access permissions or I/O errors. Do not infer that `!Files.exists(path)` equals `Files.notExists(path)` in all situations.

These checks can be useful for **rendering UI** or **providing preliminary diagnostics**, yet cannot replace `try/catch` around the actual operation.

## 3. Java 17+ Example: File Disappears After Check

Create **CheckThenActDemo.java** and save source code in UTF-8:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;

public class CheckThenActDemo {
    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("toctou-demo-");
        Path target = directory.resolve("notes.txt");

        try {
            Files.writeString(
                    target, "hello", StandardCharsets.UTF_8);

            boolean wasThere = Files.exists(target);
            System.out.println("checkedExists=" + wasThere);

            // Simulate another actor modifying the file
            // between the check step and the use step.
            Files.delete(target);

            try {
                String text = Files.readString(
                        target, StandardCharsets.UTF_8);
                System.out.println("text=" + text);
            } catch (NoSuchFileException expected) {
                System.out.println("readAfterChange=missing");
            }
        } finally {
            Files.deleteIfExists(target);
            Files.deleteIfExists(directory);
        }
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac -encoding UTF-8 CheckThenActDemo.java
java CheckThenActDemo
~~~

Stdout:

~~~text
checkedExists=true
readAfterChange=missing
~~~

Here deleting the file **is performed intentionally** between the two statements to reproduce the race in an easily observable way; the example **does not need to spawn threads**. In real applications, the intervening action can come from another thread or process and happen at any moment.

The program proves one point: **`exists() == true` and `readString()` failing can both be true**, because they evaluate two different moments. Handling `NoSuchFileException` at the read operation is the proper error handling.

The `finally` block uses `deleteIfExists()` to clean up the file created by the program; if the file was already deleted, the method can return false without treating it as an error. Directory cleanup runs after file cleanup.

## 4. The Right Way to Read: Execute the Operation and Handle the Outcome

When the goal is **read a file if present**, in many cases you do not need to ask beforehand whether the file exists. Call the read function directly:

~~~java
// Code snippet: path is a Path, corresponding imports exist.
try {
    String text = Files.readString(path, StandardCharsets.UTF_8);
    use(text);
} catch (NoSuchFileException missing) {
    // Object no longer exists at open/read time.
    reportMissing(path);
} catch (java.nio.file.AccessDeniedException denied) {
    // Access not permitted.
    reportDenied(path);
} catch (IOException failure) {
    // Remaining I/O errors: filesystem, device, read failure...
    reportIoFailure(failure);
}
~~~

`use`, `reportMissing`, `reportDenied`, and `reportIoFailure` above are **application-provided** functions; this is an **illustrative code snippet**, not a standalone runnable program.

Advantages:

1. Avoids making a false assumption that an initial check guarantees the operation.
2. Catches errors arising **right at the work step**.
3. Distinguishes missing files, denied permissions, and other I/O errors when the provider supplies specific exceptions.
4. Eliminates a potentially unnecessary filesystem query.

**There is no guarantee every OS and provider will always throw the exact same specific exception class.** `NoSuchFileException` and `AccessDeniedException` are common cases, yet applications should still have a general `IOException` branch.

**For optional files**, "file does not exist" may be a normal business case (e.g., no custom config yet). For required files, that same situation is an error to report to the user. Handling depends on the application contract, not on whether `exists()` was called.

## 5. Check-Then-Create: The Danger When Creating New Files

A race-prone pattern:

~~~java
// WRONG if needing to guarantee not overwriting an existing file.
if (Files.notExists(target)) {
    Files.writeString(target, "new content");
}
~~~

After `notExists()` returns true, another actor can create target immediately. If `Files.writeString` uses default options, that operation can **create a missing file or truncate an existing file**. Thus the program can overwrite someone else's data contrary to the "create only if absent" goal.

The right goal here is a **conditional creation operation** executed by the filesystem as a unit, not two separate check + write operations.

Use **`StandardOpenOption.CREATE_NEW`** when creating a file and writing content:

~~~java
Files.writeString(
        target,
        "new content",
        StandardCharsets.UTF_8,
        StandardOpenOption.CREATE_NEW,
        StandardOpenOption.WRITE);
~~~

By the `Files` contract, with `CREATE_NEW`, **checking existence and creating the new file are performed atomically with respect to other filesystem operations**. If a file already exists (including a symbolic link at the target location), the operation fails; on the default provider this is typically `FileAlreadyExistsException`.

Note: **atomicity at the file creation step** does not mean writing all content immediately afterward is also an atomic transaction. If writing fails mid-way, the newly created file may contain only partial content. Do not confuse "never create over a duplicate" with "content fully committed."

### Java 17+ Example: CREATE_NEW Blocks the Second Creation

Create **CreateNewDemo.java**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class CreateNewDemo {
    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("create-new-demo-");
        Path target = directory.resolve("result.txt");

        try {
            Files.writeString(
                    target,
                    "first",
                    StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE_NEW,
                    StandardOpenOption.WRITE);
            System.out.println("firstCreate=ok");

            try {
                Files.writeString(
                        target,
                        "second",
                        StandardCharsets.UTF_8,
                        StandardOpenOption.CREATE_NEW,
                        StandardOpenOption.WRITE);
                System.out.println("secondCreate=ok");
            } catch (FileAlreadyExistsException expected) {
                System.out.println("secondCreate=already-exists");
            }

            System.out.println("content=" + Files.readString(
                    target, StandardCharsets.UTF_8));
        } finally {
            Files.deleteIfExists(target);
            Files.deleteIfExists(directory);
        }
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 CreateNewDemo.java
java CreateNewDemo
~~~

Stdout:

~~~text
firstCreate=ok
secondCreate=already-exists
content=first
~~~

On the first attempt, the file does not exist yet so creation succeeds. On the second attempt, `CREATE_NEW` detects that the target already exists and rejects the operation. The content **remains first**, not overwritten by the second call. Instead of asking `notExists` beforehand, the code enforces "create new only" at **the write call itself**, where it actually takes effect.

You can also use `Files.createFile(target)` to create a new empty file. By contract, `createFile`'s check-and-create operation is atomic with respect to other filesystem operations. Even so, calling `createFile` and then opening another stream to write is still **two separate steps**: if content safety also matters, consider opening directly with `CREATE_NEW` and holding the appropriate handle.

## 6. Check-Then-Delete and deleteIfExists

The following pattern also lacks guarantees:

~~~java
// Unnecessary and still has a race.
if (Files.exists(path)) {
    Files.delete(path);
}
~~~

Another actor can delete `path` between `exists` and `delete`. Then `Files.delete(path)` can throw `NoSuchFileException`.

If the business requirement is "delete if present; if absent then ignore," use directly:

~~~java
boolean deleted = Files.deleteIfExists(path);
System.out.println("deleted=" + deleted);
~~~

- `true`: the operation deleted an object.
- `false`: the operation did not delete because the object did not exist.
- Additionally, the operation can still throw `IOException` due to access permissions, non-empty directory, I/O errors, or other conditions.

**`deleteIfExists` does not guarantee deletion succeeds**, nor does it make preceding/subsequent business steps a transaction. It simply folds the "if it exists, delete it" logic into one convenient API and eliminates an unnecessary check-then-act window.

If the application **must delete a specific file that was previously inspected**, calling `deleteIfExists(path)` does not satisfy that identity requirement. The path may have been swapped for another object. Solving races against a specific object requires handle/file-identity mechanisms and proper filesystem access controls.

## 7. Check-Then-Write, Copy, and Move

Do not write:

~~~java
// WRONG if the goal is to strictly avoid overwriting another file.
if (!Files.exists(destination)) {
    Files.copy(source, destination);
}
~~~

Between checking and copying, `destination` can appear. Decide **the policy at the operation itself**:

- **Do not overwrite existing destination:** call `Files.copy(source, destination)` without `REPLACE_EXISTING` and handle the target-already-exists case.
- **Accept replacing destination:** consider `StandardCopyOption.REPLACE_EXISTING`, understanding that the result still depends on the filesystem, permissions, and possible errors.
- **Move file:** use `Files.move` with appropriate options; if atomic renaming is needed, consider `StandardCopyOption.ATOMIC_MOVE`, while preparing to handle `AtomicMoveNotSupportedException`.

Examples:

~~~java
// Disallow copy overwrite: application handles IOException if destination exists.
Files.copy(source, destination);
~~~

~~~java
// Accept replacement per the Files.copy contract.
Files.copy(
        source, destination,
        java.nio.file.StandardCopyOption.REPLACE_EXISTING);
~~~

~~~java
// Request atomic move; some providers/filesystems do not support it.
Files.move(
        source, destination,
        java.nio.file.StandardCopyOption.ATOMIC_MOVE);
~~~

These are **code snippets** inside a method that already has `Path` variables and handles `IOException`. Important notes:

1. `copy` and `move` operations can fail due to access permissions, missing source file, appearing target, cross-filesystem issues, or other errors.
2. **`Files.copy` does not guarantee atomicity**; if an I/O error occurs, part of the target file may already have been created or written.
3. `ATOMIC_MOVE` is a support request to the filesystem/provider; it can be rejected with `AtomicMoveNotSupportedException`. Do not assume "move" or "replace existing" is an atomic transaction.
4. With `ATOMIC_MOVE`, semantics when **target already exists** have implementation-dependent details per specification; you must verify the application contract and provider behavior. Do not combine options and assume every platform replaces identically.

**General rule:** avoid checking and then acting as if two steps were one transaction; instead choose an operation with appropriate conditions/options and **always handle the outcome of that operation itself**.

## 8. Check-Then-Mkdir and createDirectories

A common example:

~~~java
if (!Files.exists(directory)) {
    Files.createDirectory(directory);
}
~~~

Another actor can create `directory` right after the check, causing `FileAlreadyExistsException`. If the requirement is "ensure the entire parent directory chain exists when possible," commonly use:

~~~java
Files.createDirectories(directory);
~~~

`createDirectories` can create missing directory components and **does not fail merely because the target directory already exists as a directory**. However, it can still throw `IOException` if a component is a regular file, permissions are lacking, a system error occurs, or the environment changes during creation.

**Do not infer that createDirectories is an atomic transaction.** If creating a chain of components fails, some earlier parent directories may have already been created successfully. The application needs to consider cleanup of resources/side effects it owns if rollback is required.

## 9. Permission and Metadata Checks Do Not Replace Opening

Pattern:

~~~java
if (Files.isReadable(path)) {
    return Files.readString(path);
}
return "";
~~~

has two problems:

1. `isReadable` only describes state **at check time**; permissions can change or the object can be replaced afterward.
2. If `isReadable` returns false, it may be due to inability to check or provider-specific conditions; returning an empty string **hides the failure reason** and tricks the application into thinking the file has empty content.

Better:

~~~java
try {
    return Files.readString(path, StandardCharsets.UTF_8);
} catch (IOException failure) {
    // Business decision: report error, fall back, or perform bounded retry.
    throw failure;
}
~~~

Similarly, `Files.isWritable` does not prove enough storage space remains, no quota is exceeded, the file is unlocked, and writing will succeed. `Files.size` does not guarantee the file keeps that size while reading. To read a consistent snapshot, design appropriate transactions/snapshots/locking suited to the filesystem and writers.

**File locking is also not a universal fix:** enforcement level, scope, interaction with other software, and portability depend on the filesystem and operating system. Never replace exception handling logic with the belief that a single permission check or lock eliminates all races.

## 10. Symbolic Links Make Check-Then-Use More Dangerous

Suppose an application wants to read a file under an allowed directory. It checks:

~~~text
/base/uploads/report.txt
~~~

If an attacker or another process has permission to modify the directory tree, they can replace the file or a parent component with a **symbolic link** pointing elsewhere between verification and opening. A path-based check **does not pin the identity of the object opened afterward**.

Related concepts:

- **`Path.normalize()`** only collapses `.` and `..` components syntactically without querying the filesystem.
- **`Path.toRealPath()`** can resolve an existing path at call time, yet still does not "lock" the result against future changes.
- **`LinkOption.NOFOLLOW_LINKS`** affects certain operations as specified, yet a single check does not guarantee none of the path components are swapped between check and use.
- **`SecureDirectoryStream`** provides certain operations relative to an open directory stream, which can reduce race risks where supported by the provider; not every filesystem provides this API.

For untrusted paths, checking only `resolved.normalize().startsWith(base)` is **insufficient** when symbolic links and races exist. Safer design requires managing directory identity, symlink-following behavior, directory modification permissions, and how files are opened, not merely comparing strings or paths beforehand.

Even if an application does not run in an adversarial threat model, this distinction still matters: even without intentional attacks, file-syncing processes or concurrent user actions can cause races.

## 11. Open-Then-Use Rule: Handles Can Still Fail

There is an important distinction:

- When **opening** a file via `Files.newInputStream` or `Files.newByteChannel`, you obtain a stream/channel object tied to the open accepted at that moment.
- However, **nothing guarantees every subsequent read/write/flush/close will succeed**. Hardware can fail, network or external storage can vanish, the filesystem can run out of space, the stream can be closed, or other resources can change.
- Therefore, **try-with-resources** is needed to close and handle exceptions during opening, reading/writing, and closing.

Streaming read example:

~~~java
// Code snippet: input is a Path, output is a valid OutputStream.
try (var stream = Files.newInputStream(input)) {
    stream.transferTo(output);
}
~~~

`transferTo` can throw `IOException` mid-copy. Try-with-resources still attempts to close the stream. Never assume "opening the stream succeeded" means full reading and closing will always succeed.

**Do not use `Files.exists` as a way to guarantee atomicity for an entire workflow.** A process wanting to write complete output can use the pattern of creating a temp file, writing/flushing/closing, then publishing via move under supported semantics; yet it must handle errors and clean up the temp file. Clear design between steps is still needed; one cannot assume everything rolls back automatically.

## 12. Does Avoiding Pre-Checks Mean Not Validating Data?

No. This lesson **does not advise skipping input validation**. Distinguish:

**Input contract validation** (should do):

- Did the user supply a filename?
- Are the extension/format permitted by business rules?
- What is the maximum payload size accepted?
- Does the path violate security policy?
- Does the read data match the expected schema, checksum, magic bytes, or version?

**Checking dynamic state and assuming it stays unchanged** (should not do):

- `exists` today, so reading is guaranteed to work on the next line.
- `notExists` before writing, so it will never overwrite another file.
- `isWritable` before exporting, so the file will definitely be written completely.
- `size` before allocating, so the file never changes during reading.
- `isRegularFile` before opening, so it cannot be swapped for another object.

An application can **both validate inputs and catch errors from real operations**. At security boundaries, use handle-based operations or race-resistant mechanisms rather than relying solely on a filesystem status check.

## 13. Should You Retry When a File Disappears or Appears?

Not every `IOException` should be retried:

| Situation | How to handle |
| --- | --- |
| Optional file does not exist yet | Can fall back to default configuration, if business rules allow |
| Required file does not exist | Report error clearly or ask for the valid path |
| Creating file with CREATE_NEW hits FileAlreadyExistsException | Choose a different name or report conflict; do not silently overwrite |
| AccessDeniedException permission error | Usually report permission/config error; do not retry indefinitely |
| Transient I/O error per defined protocol | Can do bounded retry with delay/backoff and state check |
| Write may have partially completed | Must know whether the operation is idempotent before retrying |
| Move/copy fails mid-way | Inspect actual output state, handle partial artifact per contract |

An uncontrolled retry can overwrite data, create duplicate files, loop endlessly, or trigger more races. When retrying is needed, pick **idempotent operations** or use unique names/IDs and safe protocols. Especially for writes, account for the possibility of **partial writes** before retrying.

## 14. Right and Wrong Patterns Side by Side

| Goal | Error-prone pattern | Better way to express intent |
| --- | --- | --- |
| Read a possibly absent file | `if (exists) read` then omit error handling | Direct `readString`, catch NoSuchFileException/IOException |
| Create only if absent | `if (notExists) write` | `CREATE_NEW` or `createFile` |
| Delete if present | `if (exists) delete` | `deleteIfExists` and handle IOException |
| Create directory tree | `if (!exists) createDirectory` | `createDirectories` and handle IOException |
| Copy without overwriting | `if (!exists(dest)) copy` | `Files.copy` without REPLACE_EXISTING, handle conflict |
| Move requiring atomicity | Check target first then normal move | Consider `ATOMIC_MOVE` and handle unsupported/race |
| Check readability | `isReadable` then trust read succeeds | Open/read directly, handle real errors |
| Read large file | `size` then trust fixed size | Streamed reading, cap data, handle EOF/errors |
| Restrict file under base | Only `normalize().startsWith(base)` | Control symlinks, permissions, and actual open operation |

**Different `Files` API methods solve different requirements.** Choose APIs by **business invariants**: no-overwrite, controlled replacement, read-only, delete-if-present, directory creation... rather than checking piecemeal and hoping.

## 15. Practical Workflow When Writing File Operations

1. **Define desired behavior:** is the file required or optional? Can it be created? Can it be overwritten? On conflict, report an error or rename?
2. **Choose an operation reflecting the behavior at execution time:** e.g., `CREATE_NEW` for exclusive creation, `deleteIfExists` for optional deletion, `createDirectories` for tree creation.
3. **Never use the result of a status check as a future guarantee.** If you need to show "file exists," you can still call `exists`, yet the operation using the file must handle its own errors.
4. **Manage resource lifecycles** with try-with-resources and handle errors in read/write/flush/close.
5. **Define consistency:** accept a changing file, need a snapshot, need atomic publishing, or need safe locks/handles?
6. **Handle partial outputs** after a failed operation; distinguish resource cleanup from data rollback.
7. **Test error paths and race scenarios:** file disappears after check; file appears before create; permissions change; file swapped for symlink; I/O error mid-copy.

This is the **"try the operation, handle its actual result"** mindset. It does not remove the need for input validation, while eliminating the assumption that an observed state remains valid for the next action.

## 16. Self-Check Questions

**Question 1.** `Files.exists(path)` returns true. Is the next read guaranteed to succeed?  
**Answer:** No. The file may be deleted, renamed, replaced, have permissions changed, or encounter an I/O error before/during reading.

**Question 2.** Why can `if (Files.notExists(path)) Files.writeString(path, data)` overwrite a file just created by another actor?  
**Answer:** Check and write are two separate steps. Another actor can create the file after the check; default `writeString` can truncate an existing file.

**Question 3.** When a new file must be created only if it does not yet exist, what should be chosen?  
**Answer:** `StandardOpenOption.CREATE_NEW` or `Files.createFile`, then handle the target-already-exists case. Do not substitute check-then-create.

**Question 4.** If both `Files.exists` and `Files.notExists` return false, can you conclude whether the file exists or not?  
**Answer:** You cannot tell conclusively from those two values; the system may be unable to determine the file's status.

**Question 5.** Does `Files.deleteIfExists` guarantee deleting any file succeeds?  
**Answer:** No. It ignores the absent-object case, yet can still fail due to permissions, non-empty directories, and I/O errors.

**Question 6.** Is `Files.isReadable(path)` returning true enough to omit catching IOException around `Files.readString`?  
**Answer:** No. State can change and errors can still occur during reading.

**Question 7.** Is `Files.copy` an atomic transaction by default?  
**Answer:** No. Errors during copying can leave a partial target; design cleanup or publishing per requirements.

**Question 8.** Is `normalize().startsWith(base)` enough to prevent access outside base when symbolic links exist?  
**Answer:** Not enough. Normalize is lexical, whereas symlinks and races require filesystem/handle-level controls.

**Question 9.** If `CREATE_NEW` creates the file successfully and the write fails mid-way, does the file automatically vanish?  
**Answer:** There is no such guarantee. CREATE_NEW guarantees the creation condition, not a transaction over the entire content write; the application must handle partial files.

**Question 10.** If a UI check shows "file currently exists," should it be removed?  
**Answer:** Not necessarily. Instantaneous information is useful for UI; just never treat it as replacing result and exception checks on the I/O operation itself.

## 17. Java SE 17 Documentation

- [Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): `exists`, `notExists`, `isReadable`, `createFile`, `createDirectories`, `deleteIfExists`, `copy`, `move`.
- [StandardOpenOption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardOpenOption.html): `CREATE_NEW`, `CREATE`, `TRUNCATE_EXISTING`, `WRITE`.
- [StandardCopyOption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardCopyOption.html): `REPLACE_EXISTING` and `ATOMIC_MOVE`.
- [FileAlreadyExistsException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileAlreadyExistsException.html) and [NoSuchFileException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/NoSuchFileException.html): existence/non-existence errors at operation time.
- [SecureDirectoryStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/SecureDirectoryStream.html): directory operations with mechanisms to help defend against certain path-based races, when supported by the provider.

**Key takeaway:** For files and shared resources, **state observed at check time does not guarantee the subsequent usage operation succeeds**. Instead of check-then-act while assuming everything stays constant, use **APIs that express the condition at the operation itself** (such as `CREATE_NEW`), handle exceptions thoroughly, close resources promptly, and use pre-checks only as supplementary information.
