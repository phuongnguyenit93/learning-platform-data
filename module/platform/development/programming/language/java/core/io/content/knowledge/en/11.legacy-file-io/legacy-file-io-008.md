# Error Information Limitations of Boolean-Returning APIs in java.io.File

In legacy Java I/O, many methods of **`java.io.File`** only return a `boolean`: `delete()`, `mkdir()`, `mkdirs()`, `renameTo()`, `setLastModified()`, `setReadable()`, `setWritable()`, `setExecutable()`, and `setReadOnly()`. Several state-checking methods such as `exists()`, `isFile()`, `isDirectory()`, and `canRead()` also return booleans.

This design keeps statements concise, yet **a `false` value is insufficient to know why an operation failed**. For example, `file.delete() == false` could mean the path does not exist, the directory is not empty, access permissions are insufficient, or the file system encountered an obstacle. `false` merely indicates the operation did not succeed per contract; **it contains no `IOException`, error code, cause, or stack trace from the operating system**.

When clear error handling is needed, Java provides **`java.nio.file.Files`** with methods such as `Files.delete`, `Files.createDirectory`, `Files.move`, or `Files.readAttributes`. Many of these methods throw `IOException` or a specific subclass, providing better diagnostic signals.

## 1. Learning Objectives

After this lesson, you will be able to:

- Distinguish **booleans for operation results**, **booleans for state checks**, and **I/O exceptions**.
- Point out why `File.delete()`, `mkdir()`, `mkdirs()`, and `renameTo()` usually do not provide enough causal information when returning `false`.
- Identify the notable exception: `File.createNewFile()` also returns a boolean yet **throws `IOException` when an I/O error occurs**.
- Write equivalent handling using `Files.delete`, `Files.deleteIfExists`, `Files.createDirectory`, `Files.createDirectories`, and `Files.move`.
- Distinguish "does not exist" from "cannot be determined" in `Files.exists`/`Files.notExists` checking APIs.
- Avoid **TOCTOU** (*time-of-check to time-of-use*): checking beforehand does not guarantee the subsequent operation succeeds.
- Log sufficient error details, preserve causes, and decide appropriately between retrying or reporting failure.
- Understand limitations regarding permissions, symbolic links, non-empty directories, and platform dependence of file APIs.

## 2. `java.io.File` Represents a Path, Not an Open File

`File` represents an **abstract pathname**: a path to a potential file or directory. Creating a `File` object does not automatically create a file, does not open a file, and does not prove the entry actually exists:

~~~java
java.io.File file = new java.io.File("reports/output.txt");
~~~

The line above only creates an object describing a path. When calling `file.exists()` or `file.delete()`, the method then queries/requests an operation on the file system.

Legacy boolean methods have **different meanings**; you cannot lump every `false` result into "I/O failed":

| Group | Method | `true` usually means | `false` could mean |
| --- | --- | --- | --- |
| Delete operation | `delete()` | Deleted file/directory | Not found or could not delete for another reason |
| Create single directory | `mkdir()` | Target directory created successfully | Already exists, parent missing, insufficient permissions, or error |
| Create multiple levels | `mkdirs()` | Needed directories created per return contract | Target directory already exists or could not be created; some parent directories may have been created |
| Rename/move | `renameTo(dest)` | Rename per provider/platform succeeded | Failed for various reasons; no detailed `IOException` |
| Modify metadata | `setLastModified(...)`, `setReadOnly()`, `setWritable(...)`... | Update operation succeeded | Missing permissions, unsupported platform, unsuitable path... |
| Check existence | `exists()` | Path existed at check time | Path does not exist or query could not accurately determine state |
| Check type | `isFile()`, `isDirectory()` | Matched respective type at check time | Does not exist, different type, or cannot be determined for sure |
| Check permissions | `canRead()`, `canWrite()`, `canExecute()` | Application is reported as having the respective capability | Does not exist, lacks permission, or cannot be determined for sure |

The **operation** group typically uses booleans to report success/failure. The **check** group uses booleans to describe a property at the moment of the query. You must read each API's contract individually: for instance, `isDirectory()==false` **does not assert** that the file exists and is a regular file.

## 3. Example: `File.delete() == false` Gives No Reason

According to the `File.delete()` contract, `true` means the file/directory was successfully deleted; `false` means it could not be deleted. Some possibilities when false:

1. The path does not exist.
2. The path points to a directory that still contains child entries.
3. Delete permissions on the parent directory or file system policy do not allow it.
4. The file is currently in use in a way that prevents the platform from deleting it.
5. File system/device unavailable, I/O error, or other constraints.

**From `false` alone, you cannot conclude which cause occurred.** Calling `exists()` afterward and seeing `false` also does not prove the file was originally missing: another task might have just deleted it, or query permissions might differ.

### Java 17: Reproducing the Non-Existent Case

Create the file **`BooleanDeleteDemo.java`**:

~~~java
import java.io.File;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;

public class BooleanDeleteDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("boolean-delete-");
        Path missing = root.resolve("never-created.txt");
        File legacy = missing.toFile();

        try {
            System.out.println("File.delete=" + legacy.delete());

            try {
                Files.delete(missing);
                System.out.println("unexpected success");
            } catch (NoSuchFileException exception) {
                System.out.println("Files.delete="
                        + exception.getClass().getSimpleName());
            }

            System.out.println("Files.deleteIfExists="
                    + Files.deleteIfExists(missing));
        } finally {
            Files.deleteIfExists(root);
        }
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 BooleanDeleteDemo.java
java BooleanDeleteDemo
~~~

Result when no external actor interferes with the temporary directory:

~~~text
File.delete=false
Files.delete=NoSuchFileException
Files.deleteIfExists=false
~~~

For the same missing-file situation, the three APIs report results under three **different contracts**:

- `File.delete()` → `false`, with no reason propagated upward.
- `Files.delete(path)` → throws `NoSuchFileException` (a kind of `FileSystemException`/`IOException`).
- `Files.deleteIfExists(path)` → `false` because the file does not exist; although it still returns a boolean, the method **can throw `IOException` for deletion errors**. This is the appropriate choice if business logic considers "file is already gone" an acceptable outcome.

`Files.deleteIfExists` does not guarantee absolute atomicity on every file system; check/delete and other operations can still interact with each other.

## 4. Example: Non-Empty Directory Shows the Benefit of Specific Exceptions

When trying to delete a directory, `File.delete()` can only delete it if the directory is empty. If the directory still contains child files, it usually returns `false` without specifying the exact reason.

Create the file **`NonEmptyDirectoryDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.file.DirectoryNotEmptyException;
import java.nio.file.Files;
import java.nio.file.Path;

public class NonEmptyDirectoryDemo {
    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("nonempty-");
        Path child = Files.createFile(directory.resolve("item.txt"));

        try {
            System.out.println("legacyDelete="
                    + directory.toFile().delete());

            try {
                Files.delete(directory);
                System.out.println("unexpected success");
            } catch (DirectoryNotEmptyException exception) {
                System.out.println("nioDelete="
                        + exception.getClass().getSimpleName());
            }
        } finally {
            Files.deleteIfExists(child);
            Files.deleteIfExists(directory);
        }
    }
}
~~~

Compile and run:

~~~bash
javac NonEmptyDirectoryDemo.java
java NonEmptyDirectoryDemo
~~~

Typical result on a standard file system:

~~~text
legacyDelete=false
nioDelete=DirectoryNotEmptyException
~~~

`DirectoryNotEmptyException` is a **specific exception permitted by the API**, yet not every file system provider is forced to use this exact subclass: the Java specification marks several specific exceptions of `Files.delete` as *optional specific exceptions*. A provider may still report a general `IOException`. Therefore:

- Catch `DirectoryNotEmptyException` to handle that case when the provider supplies it.
- Catch or propagate `IOException` for remaining errors.
- Do not conclude that every non-empty directory deletion error must always have the exact exception type shown in the example.

A real-world application **must not automatically delete all subdirectories** simply because it sees a directory is not empty. Recursive deletion is a separate destructive decision requiring explicit scope confirmation.

## 5. `mkdir()` and `mkdirs()`: False May Mean "Already Exists"

Consider two calls on the same path:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public class DirectoryBooleanDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("mkdir-demo-");
        Path child = root.resolve("cache");

        try {
            System.out.println("first=" + child.toFile().mkdir());
            System.out.println("second=" + child.toFile().mkdir());
            System.out.println("isDirectory=" + Files.isDirectory(child));
        } finally {
            Files.deleteIfExists(child);
            Files.deleteIfExists(root);
        }
    }
}
~~~

Compile/run:

~~~bash
javac DirectoryBooleanDemo.java
java DirectoryBooleanDemo
~~~

Output in a normal environment without concurrent modification:

~~~text
first=true
second=false
isDirectory=true
~~~

The first call creates it successfully; the second returns `false` because the destination **is already a directory**. This is not necessarily a business error: if the goal is "ensure the directory exists," the current state is valid.

### Differences Between `mkdir` and `mkdirs`

- `mkdir()` only attempts to create the **final directory**; parent directories must exist.
- `mkdirs()` also attempts to create any **missing parent directories**.
- Both can return `false` if the directory cannot be created or the target directory already exists.
- `mkdirs()` may successfully create **part of the directory tree** before failing; do not assume false means no changes were made on disk.

NIO comparison:

~~~java
Path dir = Path.of("data", "archive");

Files.createDirectory(dir);   // Creates exactly one level; may throw IOException.
Files.createDirectories(dir); // Creates missing levels; if already a directory, succeeds.
~~~

This is a **code snippet** requiring `import java.nio.file.Files;`, `Path`, and `IOException` handling. You should not call these two statements back-to-back in the same task without a reason; they represent two different strategies.

`Files.createDirectory` can throw `FileAlreadyExistsException` when the destination already exists; `Files.createDirectories` supports the "final directory must exist" requirement, yet if the path exists as a non-directory file or lacks permissions, it will still fail. Multi-level creation does not guarantee the entire directory-creation sequence is an atomic transaction.

## 6. `renameTo()`: When False Is Even Harder to Diagnose

`File.renameTo(File dest)` has a platform-dependent contract: some systems cannot rename when source/destination are on different file systems, or cannot replace an existing destination, or have special rules when the file is open. According to the Java API, many aspects such as whether moving across file systems succeeds, whether the operation is atomic, and how an existing destination is handled are platform-dependent.

~~~java
File source = new File("old.txt");
File destination = new File("new.txt");

if (!source.renameTo(destination)) {
    // Uncertain: source missing, destination conflict,
    // wrong permissions, different file system, or another issue.
}
~~~

This is a **code snippet** requiring `import java.io.File`. Do not program an "unbounded retry" on `false`, because it is unclear whether the condition will disappear or whether the operation had partial effects.

With NIO:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

public final class MoveExample {
    private MoveExample() {}

    public static Path replace(Path source, Path destination)
            throws IOException {
        return Files.move(source, destination,
                StandardCopyOption.REPLACE_EXISTING);
    }
}
~~~

This is a compilable class (without `main`), where **allowing destination replacement** is an intentional business choice. `Files.move` can throw `IOException`; the `REPLACE_EXISTING` operation **does not promise atomicity** or preservation of all attributes across all providers.

If an atomic move is needed, you can request `StandardCopyOption.ATOMIC_MOVE`, but you must handle `AtomicMoveNotSupportedException` if the provider does not support it. Do not silently drop the atomicity requirement without evaluating data consistency. For moves across different file systems, the implementation may have to copy then delete, so errors, partial data, and rollback steps must be considered.

## 7. An Important Exception: `File.createNewFile()` Does Not Only Return Boolean

You should not state "every boolean-returning `File` method swallows I/O errors." `File.createNewFile()` **both returns a boolean and declares `throws IOException`**:

~~~java
boolean created = file.createNewFile();
~~~

Meaning:

- `true`: the new file was created successfully.
- `false`: the destination name already had an existing file/path at the time of the creation operation.
- `IOException`: an I/O error occurred while attempting to create the file.

The documentation also specifies that checking that the name does not exist and creating the new file are **a single atomic operation** relative to related file system activities, within the scope of the API contract.

### Java 17: Distinguishing Already Exists from I/O Failure

Create the file **`CreateNewFileDemo.java`**:

~~~java
import java.io.File;
import java.io.IOException;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.Path;

public class CreateNewFileDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("create-new-");
        Path path = root.resolve("report.txt");
        File file = path.toFile();

        try {
            System.out.println("first=" + file.createNewFile());
            System.out.println("second=" + file.createNewFile());

            try {
                Files.createFile(path);
                System.out.println("unexpected success");
            } catch (FileAlreadyExistsException exception) {
                System.out.println("nio=" +
                        exception.getClass().getSimpleName());
            }
        } finally {
            Files.deleteIfExists(path);
            Files.deleteIfExists(root);
        }
    }
}
~~~

Run:

~~~bash
javac CreateNewFileDemo.java
java CreateNewFileDemo
~~~

Result on a normal file system:

~~~text
first=true
second=false
nio=FileAlreadyExistsException
~~~

Therefore when reviewing code, you must ask **what does this boolean mean and what exceptions does the method still declare?** `File.createNewFile()` still provides `IOException` for I/O errors, unlike `File.mkdir()`/`File.delete()`.

Similarly, `Files.deleteIfExists` also returns a boolean yet **does not hide all errors**: if the file does not exist it returns false, whereas failure to delete can throw `IOException`.

## 8. `false` Values from *Checking* Methods Also Have Limitations

### `exists()`, `isFile()`, and `isDirectory()`

~~~java
File candidate = new File("incoming/data.bin");

if (!candidate.isFile()) {
    // Not enough to say "the file does not exist".
}
~~~

`isFile()==false` could be because the destination is a directory, the path does not exist yet, or it cannot be determined accurately. `isDirectory()==false` likewise does not prove the destination is a regular file.

Some query APIs under `java.nio.file.Files` **still return booleans** and also may not distinguish reasons if state is undetermined:

~~~java
boolean present = Files.exists(path);
boolean absent = Files.notExists(path);
~~~

**`Files.notExists(path)` is not simply `!Files.exists(path)`.** There are three outcome groups to distinguish:

| `Files.exists(path)` | `Files.notExists(path)` | Interpretation |
| --- | --- | --- |
| `true` | `false` | Confirmed that the file existed at query time |
| `false` | `true` | Confirmed that the file did not exist at query time |
| `false` | `false` | Could not determine whether it exists or does not exist |

The two checks are **two separate operations in time**, so when the file system changes concurrently, the pair of values actually read may not reflect a consistent snapshot. The table interprets stable state conditions at query time and cannot substitute for file system locks/transactions.

When a specific error is needed (for example, exists but metadata cannot be read), call an API like `Files.readAttributes(path, BasicFileAttributes.class)`; it can throw `IOException`/`NoSuchFileException` instead of just returning false.

### `canRead()`, `canWrite()`, `canExecute()`

Permission checks describe capability observed at a single point in time, **not a guarantee** that the next file open will succeed:

- File permissions/ACLs can change.
- The file can be deleted or replaced.
- The file system may have different policies depending on operation type.
- The operating system may enforce sharing/locking modes or other restrictions.
- A symbolic link can point to a different entry.

You should **perform the actual operation** (`Files.newInputStream`, `Files.newOutputStream`, `Files.readAttributes`...) and handle `IOException`, instead of using `canRead() == true` as a future guarantee.

## 9. TOCTOU: "Checking Beforehand" Does Not Fix Boolean Drawbacks

Common pattern:

~~~java
if (file.exists()) {
    if (!file.delete()) {
        // ...
    }
}
~~~

There are two independent problems:

1. `delete()==false` still does not tell you the reason.
2. **Race condition**: the file can be deleted, replaced, or have its permissions changed right after `exists()` and before `delete()`.

Similarly:

~~~java
if (!Files.exists(target)) {
    Files.createFile(target); // Can still fail because someone else created it first.
}
~~~

Even when `Files.exists(target)` returns false, that **does not prove** the file does not exist yet; the state might be undetermined. And even if confirmed non-existent, the result can already be stale.

**Better approach:** use a direct operation with the appropriate contract:

- "Must delete the file; if missing, report an error" → `Files.delete(path)`.
- "Ensure after the operation the file is gone; missing file is acceptable" → `Files.deleteIfExists(path)`, handling `IOException` when deletion fails.
- "Create new file and must not overwrite" → `Files.createFile(path)` or `CREATE_NEW`.
- "Ensure directory exists" → `Files.createDirectories(path)`.
- "Move file, need detailed conflict/error handling" → `Files.move(...)` with appropriate options.

Stronger APIs help distinguish errors, yet **do not make all race conditions disappear**. Especially for security requirements involving symlinks, permissions, or directory trees modifiable by others, use APIs/operations and designs providing necessary atomicity rather than chaining fragile check steps.

## 10. `list()` and `listFiles()`: Also Can Return `null`

Not every failing legacy API returns a boolean. `File.list()` and `File.listFiles()` return arrays, yet can return **`null`** if the path does not point to a directory or an I/O error occurs during listing.

~~~java
File directory = new File("reports");
File[] entries = directory.listFiles();

if (entries == null) {
    // Must not assume "empty directory".
    // Might not be a directory or encountered a read error.
} else {
    for (File entry : entries) {
        System.out.println(entry.getName());
    }
}
~~~

`entries.length == 0` is an empty array returned from a successful listing operation; `entries == null` is a different case.

When better diagnostics are needed, use:

~~~java
try (java.nio.file.DirectoryStream<java.nio.file.Path> entries =
             java.nio.file.Files.newDirectoryStream(path)) {
    for (java.nio.file.Path entry : entries) {
        System.out.println(entry.getFileName());
    }
}
~~~

This is a **code snippet**, requiring a `path` variable of type `Path` and `IOException` handling. `DirectoryStream` is a resource that must be closed; iteration errors may surface as `DirectoryIteratorException` (wrapping an `IOException` cause), distinct from errors when opening the stream. Do not assume the returned list has a fixed order.

`Files.list(path)` also creates a `Stream<Path>` that must be closed with `try-with-resources`; errors during lazy iteration can be wrapped in `UncheckedIOException`. That is another nuance: using NIO does not mean every API throws the exact same exception type or requires no resource management.

## 11. Detailed Exception Handling: What Can Be Observed?

Typical NIO operations can report:

- `NoSuchFileException`: the required path/file does not exist.
- `FileAlreadyExistsException`: the destination already exists when the operation forbids it.
- `DirectoryNotEmptyException`: the directory is not empty when deletion is requested.
- `AccessDeniedException`: insufficient permissions / access denied.
- `AtomicMoveNotSupportedException`: the provider does not support the requested atomic move.
- `FileSystemException`: information regarding the file, other file, and reason (when supplied by the provider).
- General `IOException`: another I/O error, or the provider did not report a more specific subclass.

Specific subclasses are not always guaranteed across every provider/OS. Handle the specific exceptions the application genuinely needs to distinguish, then let `IOException` cover remaining cases.

### Informative Error Logging/Representation Pattern

~~~java
import java.io.IOException;
import java.nio.file.AccessDeniedException;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;

public final class DeleteWithReason {
    private DeleteWithReason() {}

    public static void deleteRequired(Path path) throws IOException {
        try {
            Files.delete(path);
        } catch (NoSuchFileException exception) {
            throw new IOException("Required file is missing: " + path,
                    exception);
        } catch (AccessDeniedException exception) {
            throw new IOException("Cannot delete due to access policy: "
                    + path, exception);
        }
    }
}
~~~

This is a compilable class, though **without `main`**. It illustrates preserving the **cause** via the `IOException(message, cause)` constructor, keeping the stack trace and provider-supplied details in logs. The method propagates other `IOException`s without guessing reasons.

In real products, avoid logging sensitive paths, account names, or private data into public logs. Choose log levels/structured logging according to purpose; include properly sanitized paths and actual causes, without fabricating messages like "permission denied" when you only observed `File.delete()==false`.

### Do Not "Fix" Data Based on a Guessed Cause

You should not do:

~~~java
if (!file.delete()) {
    file.setWritable(true);
    file.delete();
}
~~~

This is merely an **illustrative snippet of an unsafe practice**: the failure reason is unknown, it may alter file permissions beyond intended scope, still fails to check the second result, and can introduce security discrepancies. Do not use in real programs.

If an operation needs retrying, identify which errors are transient, limit retry count and duration, verify idempotency, and avoid changing permissions or accidentally deleting a file that was just replaced.

## 12. Platform Characteristics: Permissions, Symbolic Links, and File System Providers

### Access Permissions

The same operation may succeed on one system yet fail on another. In particular, delete permission on Unix-like systems typically depends on the **parent directory**, not simply reading the file's own writable bit. On Windows, a file currently open with an incompatible sharing mode may be refused deletion/movement.

`File.setReadable/setWritable/setExecutable/setReadOnly` are convenience APIs with limited expressiveness; when POSIX permissions or ACLs are needed, consider APIs under `java.nio.file.attribute` such as `PosixFilePermissions`, `PosixFileAttributeView`, or `AclFileAttributeView` if supported by the file system. Check capabilities and handle errors rather than assuming every OS shares the same permission model.

### Symbolic Links

APIs have specific rules when encountering symbolic links:

- Deleting a **symbolic link** normally deletes the link itself, not the target.
- `Files.exists`/`isRegularFile` queries by default usually **follow links**; `LinkOption.NOFOLLOW_LINKS` can be used where supported by the API.
- When resolving paths in externally controlled directories, symlinks can change between operations; if security risks exist, design path traversal restrictions and use appropriate safe file-system mechanisms.

### File System Providers

`Path`/`Files` supports multiple providers, not just the default local disk. A provider may not support atomic moves, certain attribute views, or permission operations; exceptions and error messages may also differ.

Legacy `File` works primarily with the default file system; `Path` extends NIO capabilities and generally has more detailed operational APIs. Converting from `File` to `Path` via `file.toPath()` works when using the default provider; do not assume every `Path` can be converted to `File` (some providers do not support `toFile()`).

## 13. Testing Properly When APIs Report Booleans

Do not write tests assuming "a locked file definitely cannot be deleted" or "changing permissions will cause AccessDenied on every OS." Such outcomes can vary across Windows/Linux, account privileges, mounts, and file system providers.

Prefer **controllable** scenarios:

1. Missing file in a new temporary directory → `File.delete()` returns `false`; `Files.delete` has the opportunity to report `NoSuchFileException`.
2. An existing subdirectory → the next `mkdir()` creation returns `false`, even though the "directory exists" goal is already met.
3. A directory containing child files → `File.delete()` cannot delete directly; `Files.delete` reports an error, `DirectoryNotEmptyException` on many providers.
4. An already existing file → `File.createNewFile()` returns `false`; `Files.createFile` can report `FileAlreadyExistsException`.
5. For permission or device errors, use mock/test file system providers that can deliberately emit errors, or integration tests targeting a defined environment; do not force OS errors on developer/CI machines using brittle behavior.

When testing business logic, do not assert only system API booleans. Verify the **final state** and that the program classifies errors according to the chosen contract; clean up test data using `try/finally` or temporary resources managed by the test framework.

## 14. Comparing Handling Approaches per Business Requirement

| Requirement | Legacy API | Suitable NIO approach | Error signal |
| --- | --- | --- | --- |
| Delete a file that must be present | `file.delete()` | `Files.delete(path)` | `IOException`/subclass |
| Delete if present; missing file is acceptable | `file.delete()` + guesswork | `Files.deleteIfExists(path)` | `false` if absent; delete error may throw |
| Create a new directory; already exists is an error | `file.mkdir()` | `Files.createDirectory(path)` | `FileAlreadyExistsException` (when provider supplies) |
| Ensure directory tree exists | `file.mkdirs()` | `Files.createDirectories(path)` | Throws error, distinguishes other existing entry types |
| Move/rename file | `file.renameTo(dest)` | `Files.move(source, target, options)` | `IOException`/explicit options |
| Determine metadata instead of boolean | `file.isFile()`/`isDirectory()` | `Files.readAttributes(path, ...)` | Can observe query errors |
| List directory | `file.listFiles()` returns array or `null` | `Files.newDirectoryStream`/`Files.list` | Clearer errors, requires closing resource |
| Create new file without overwriting | `file.createNewFile()` | `Files.createFile(path)` | Legacy **also has IOException**; NIO has subclasses |

NIO is not mandatory in every single case: if `false` truly is the only information business logic needs, a boolean API may suffice. For example, a temp-file cleanup "if still there, try deleting" might accept failure with appropriate logging. However, when deleting important documents, executing transactions, updating configuration, or needing error diagnostics for operators, **a boolean is insufficient as the final business result**.

## 15. Common Misconceptions

**"`File.delete() == false` means the file does not exist."**  
False. There are many reasons deletion can fail; use `Files.delete` if you want to know the specific error.

**"`mkdirs() == false` means no directories were created."**  
False. It may fail after creating part of the directory tree; or the destination already existed beforehand.

**"`File.isFile() == false` means it is definitely a directory."**  
False. The path may not exist, may be another type, or may be undeterminable.

**"No boolean method of `File` ever throws `IOException`."**  
False. `createNewFile()` returns a boolean **and** declares `IOException`. In addition, other methods can throw non-I/O exceptions (e.g., `SecurityException` in environments with an active security manager).

**"`Files.exists(path) == false` means `Files.notExists(path) == true`."**  
False. If the state cannot be determined, both can be false.

**"Checking `exists()` beforehand guarantees the next operation won't fail."**  
False. The file system can change state immediately; this is a TOCTOU risk.

**"Using `Files.move` is always an atomic rename."**  
False. Atomicity depends on provider/options; you must request `ATOMIC_MOVE` and handle unsupported cases if that is a hard requirement.

**"Catching `IOException` always gives a complete message from the OS."**  
False. Providers may only supply a generic error; error messages may be absent or vary by environment. Even so, an exception and its cause still provide a much better diagnostic channel than a lone boolean.

**"False means you should retry immediately."**  
False. If the cause is a wrong path, permissions, destination conflict, or non-empty directory, retrying may be futile. You must know which conditions are genuinely transient and what side effects might occur.

## 16. Checklist When Reviewing Code Using `java.io.File`

- [ ] Is the boolean-returning method an **operation** or a **state check**?
- [ ] Is the return value checked, or are failures ignored?
- [ ] If false, is the code guessing a single cause that the API **does not guarantee**?
- [ ] If the exact reason is needed, is there an equivalent `Files` method that throws `IOException`?
- [ ] Is `File.createNewFile` distinguished from APIs that only return booleans?
- [ ] Are existing path, non-existent path, and **undetermined** state cases handled?
- [ ] Does the code avoid relying on `exists/canWrite/isFile` as proof for a future operation?
- [ ] For rename/move, are overwrite, atomicity, and cross-file-system cases clarified?
- [ ] Is the exception cause preserved when propagating errors to the business layer?
- [ ] Does logging avoid exposing sensitive path information?
- [ ] If retrying/cleaning up, are retry counts limited and side effects checked?
- [ ] If files can change externally, have symlinks and TOCTOU been evaluated?
- [ ] Do tests use stable scenarios rather than depending on OS-specific locking/permission behavior?

## 17. Self-Check Questions

**Q1.** `File.delete()` returns false. Can we conclude the file does not exist?  
**Answer:** No. It only indicates deletion did not succeed; determining the cause requires another signal or a more detailed API.

**Q2.** If you need to delete a file and accept that it may already not exist, which API should you choose?  
**Answer:** `Files.deleteIfExists(path)`; when the file is missing it returns `false`, while deletion errors can throw `IOException`.

**Q3.** `mkdirs()` returns false, yet `isDirectory()` returns true. What is a common case?  
**Answer:** The destination may already have been a directory beforehand; concurrency must also be considered. There is not enough data to label false a business failure.

**Q4.** Can `Files.exists(path)` and `Files.notExists(path)` both be false?  
**Answer:** Yes, when the state cannot be determined.

**Q5.** When does `File.createNewFile()` return false, and what exception does it still declare?  
**Answer:** False when the destination path already existed at creation time; I/O errors can throw `IOException`.

**Q6.** `File.renameTo()` returns false. Should you automatically call `setWritable(true)` and retry?  
**Answer:** No. The cause is unknown; changing permissions is a separate action that carries risk and is not guaranteed to fix the error.

**Q7.** Does `File.listFiles() == null` mean an empty directory?  
**Answer:** No. The destination might not be a directory or listing failed. An empty array and `null` have different meanings.

**Q8.** Why does `Files.move(..., ATOMIC_MOVE)` still require error handling?  
**Answer:** The provider may not support atomic moves or the operation may still encounter I/O errors; the atomicity requirement must be checked and handled when unsupported.

**Remember:** `java.io.File` APIs returning `boolean` typically reflect **very little diagnostic information**. Do not infer reasons from `false`, and do not treat a state check as a guarantee for the future. When auditable error handling is required, prefer `java.nio.file.Files` operations with `IOException` and clearly distinguish "already absent" from "could not operate."

## Official API Documentation (Java 17)

- [`java.io.File`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/File.html)
- [`java.nio.file.Files`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
- [`java.nio.file.FileSystemException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileSystemException.html)
- [`java.nio.file.LinkOption`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/LinkOption.html)