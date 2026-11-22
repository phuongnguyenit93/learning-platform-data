# `NoSuchFileException`, `AccessDeniedException`, and NIO Errors in Java

When working with files, directories, or file systems using the `java.nio.file` API, a call such as `Files.readString(path)`, `Files.copy(source, target)`, or `Files.move(source, target)` can fail because **the path does not exist**, **access is denied**, **the target already exists**, **the directory is not empty**, **atomic move is not supported**, or due to many other conditions.

Java NIO.2 (introduced in Java 7 and expanded in later versions) provides specific exception classes to distinguish these situations. The two most notable classes are:

- **`NoSuchFileException`**: the operation attempted to access a file or path that does not exist under the current file system conditions.
- **`AccessDeniedException`**: the operation was denied access to a file or path within the context of the file system.

Both are **checked exceptions**, extending `FileSystemException` → `IOException`. You can catch each type separately to implement an appropriate policy, but **you must not assume that every operating system and every file-system provider will always throw the exact same subclass for the same low-level error**.

**Core principle:** choose handlers based on *exception type and operation semantics*, inspect structured path/reason information, preserve `cause` when translating errors, and always have a fallback for unclassified `IOException`s.

## 1. NIO.2 APIs and Foundational Classes

In Java, commonly used file APIs are located in:

| Type/API | Package | Role |
| --- | --- | --- |
| `Path` | `java.nio.file` | Represents a path in the file system; does not by itself prove the file exists |
| `Files` | `java.nio.file` | Operations for opening/reading/writing/copying/moving/deleting, attributes, and walking directory trees |
| `FileSystem`, `FileSystems` | `java.nio.file` | Abstraction for file-system providers and active file systems |
| `OpenOption`, `StandardOpenOption` | `java.nio.file` | Specifies how a file is opened/created/written |
| `CopyOption`, `StandardCopyOption` | `java.nio.file` | Controls copying or moving |
| `LinkOption` | `java.nio.file` | Specifies whether to follow symbolic links in APIs that support it |
| `BasicFileAttributes` | `java.nio.file.attribute` | File attribute metadata |
| `IOException` | `java.io` | General checked exception class for many I/O failures |
| `FileSystemException` | `java.nio.file` | Checked exception associated with a file, an optional other file, and an error reason |
| `NoSuchFileException`, `AccessDeniedException` | `java.nio.file` | Two specific file-system error classifications |

`Path.of("data", "input.csv")` **only creates an object representing the path**. It does not read from disk to verify that the path actually exists. Therefore, a "file not found" error usually occurs when **performing the I/O operation**, not merely because `Path` was created.

Example:

```java
Path path = Path.of("data", "input.csv");
String content = Files.readString(path);
```

This is an **illustrative snippet** that requires importing `java.nio.file.Path` and `java.nio.file.Files`, and handling the checked `IOException`. The `readString` call can throw an exception due to a missing path, insufficient permissions, a file unsuitable for the operation, or other I/O errors.

## 2. Inheritance Hierarchy of NIO Exceptions

Commonly encountered hierarchy excerpt:

```text
java.lang.Throwable
└── java.lang.Exception
    └── java.io.IOException
        ├── java.io.FileNotFoundException
        └── java.nio.file.FileSystemException
            ├── NoSuchFileException
            ├── AccessDeniedException
            ├── FileAlreadyExistsException
            ├── DirectoryNotEmptyException
            ├── NotDirectoryException
            ├── FileSystemLoopException
            └── AtomicMoveNotSupportedException
```

This is an **abbreviated diagram**; it does not list every subtype, nor does it mean all NIO errors fall under `FileSystemException`.

Each class in the `FileSystemException` branch describes a different situation. Because all of them belong to `IOException`, a `catch (IOException ex)` can catch them, but using only a single generic handler misses the opportunity for intentional recovery.

In addition to checked exceptions, some NIO operations can throw **unchecked exceptions** such as `InvalidPathException`, `ClosedFileSystemException`, `FileSystemNotFoundException`, `ProviderNotFoundException`, `UnsupportedOperationException`, or `SecurityException` under corresponding conditions and environments. You must not treat `catch (IOException)` as "catching all NIO errors".

### Why are `FileNotFoundException` and `NoSuchFileException` different?

`java.io.FileNotFoundException` is a checked subtype of `IOException` commonly encountered from traditional I/O APIs such as `FileInputStream`. `java.nio.file.NoSuchFileException` is a subtype of **`FileSystemException`**, aimed at file-system errors in NIO. **The two classes are not direct parent/child of each other**.

You should not switch from `FileInputStream` to `Files.newInputStream` and assume the exact exception type remains unchanged. Callers need to read the specific API contract and maintain an appropriate `IOException` handler.

## 3. `NoSuchFileException`: File or Path Component Does Not Exist

`NoSuchFileException` represents an operation failing because the requested file/path does not exist in the current situation.

Typical example:

```java
Path path = Path.of("data", "never-created.txt");
String text = Files.readString(path);
```

If the path truly does not exist, the default file-system provider usually throws `NoSuchFileException`. However, do not use this example to assert that **every provider** must always supply the same subtype in all circumstances; the specific I/O error can depend on the provider and system state.

Common causes:

- Typo in the file name, relative path interpreted differently than expected, or wrong letter case on a case-sensitive file system.
- The file previously existed but was deleted or moved between the check and the open operation.
- A parent directory does not exist.
- A symbolic link points to a target that has been deleted, depending on how links are followed.
- The path was constructed from an incorrect configuration, or the process is running in a different working directory than expected.

### Relative Paths and Working Directory

`Path.of("config", "app.properties")` is a relative path. It is resolved in the context of the file system and the process's working directory when the API executes the operation.

You should not assume that it always points to the directory containing the `.java` file or the IDE project directory. For a program packaged and run as a service, the working directory can differ significantly.

You can aid diagnostics with:

```java
Path requested = Path.of("config", "app.properties");
System.out.println(requested.toAbsolutePath().normalize());
```

This is **illustrative code**; `toAbsolutePath()` does not validate that the file exists. It helps display the resolved path, without replacing access permissions or the open operation.

### When a Missing File Is a Normal Outcome

Not every missing file is an incident. For example, an optional configuration file that does not yet exist can be handled with a well-defined default. In that case, you can catch **`NoSuchFileException` specifically** and return a result describing "no optional configuration".

Conversely, for a required data file, you should report the failure clearly and not treat missing as fake empty data indicating success.

## 4. `AccessDeniedException`: Permission or Access Denied

`AccessDeniedException` typically appears when the file-system provider denies an operation attempting to access a file or a path component.

Example:

```java
Path path = Path.of("private", "credentials.txt");
String text = Files.readString(path);
```

This is an **illustrative snippet** and is not guaranteed to throw `AccessDeniedException` on the machine currently running it. Actual permissions depend on the user account, ACLs, parent directory permissions, mounts, security mechanisms, file-system provider, and environment.

Common situations:

- The user/process is not allowed to read the file.
- A parent directory does not allow traversal according to operating system permission rules.
- The process is not allowed to write or delete the file per system ACLs/policies.
- Certain operations are denied by the storage provider or access policy.

### Do Not Confuse with `SecurityException`

`AccessDeniedException` is a **checked `IOException`**, whereas `SecurityException` is an **unchecked `RuntimeException`**. `SecurityException` can be related to Java-level security checks, such as in environments with a supported security manager mechanism; it is not a synonym for all operating system permission errors.

An API might report a permission error using another `IOException` or a specific exception depending on the provider. Therefore:

- `catch (AccessDeniedException ex)` only catches this exact subclass.
- `catch (IOException ex)` also catches other checked I/O errors.
- `catch (IOException ex)` does **not** catch `SecurityException`.

In normal code, you should not `catch (Throwable)` just to force all permission errors and programming bugs into a "file missing" state.

### Why Changing File Permissions in a Demo Does Not Guarantee an Error

A lesson might try `Files.setPosixFilePermissions` on POSIX, but that API may not be supported on Windows or another provider. Even if permissions are changed to read-only, a privileged process, special ACLs, or system policies can still produce a different result than expected.

Therefore, the examples below will **not rely on forcing real permission errors on the learner's machine**. Instead, one program constructs exception objects to teach classification, and another program performs real file operations in a temporary directory to teach the API.

## 5. What Structured Error Information Does `FileSystemException` Hold?

`FileSystemException` provides:

| Method | Return Type | Meaning |
| --- | --- | --- |
| `getFile()` | `String` | Primary file/path involved in the error, may be `null` |
| `getOtherFile()` | `String` | Second file/path in operations like copy/move, may be `null` |
| `getReason()` | `String` | Additional reason, may be `null` |
| `getMessage()` | `String` | Diagnostic string provided by the exception |
| `getCause()` | `Throwable` | Underlying cause if attached, may be `null` |

Usage:

```java
catch (java.nio.file.FileSystemException ex) {
    String file = ex.getFile();
    String other = ex.getOtherFile();
    String reason = ex.getReason();
    // Log safely internally or map to an error code.
}
```

This is an **illustrative handler snippet** and needs to be inside an appropriate `try` structure.

**Subtle point:** `getFile()` and `getOtherFile()` return **`String`**, not `Path`. You should not assume that string is always equivalent to a normalized/canonicalized path or always safe to send to a client.

### Distinguish Data from Message

For an `AccessDeniedException`, an application can record:

- Type: `AccessDeniedException`.
- Primary file: `getFile()`.
- Secondary file: `getOtherFile()` if present.
- Reason: `getReason()` if provided by the provider.

Do not branch solely on `ex.getMessage().contains("Permission denied")`. Wording/locales vary, `reason` may be absent, and the message can expose paths.

In public APIs, you should map **error type → application-defined error code**, and then generate a safe message according to user needs. Full path information should only go into logging systems with appropriate access controls.

## 6. Other NIO Errors to Distinguish

| Exception | Common Scenario | Context-Dependent Handling |
| --- | --- | --- |
| `NoSuchFileException` | Requested file/path component does not exist | Check path; determine if missing is optional or required |
| `AccessDeniedException` | Access denied | Check process permissions/ACL/provider; do not blindly retry |
| `FileAlreadyExistsException` | Creating a new file/dir or copying to an existing target | Choose another name, reject overwrite, or handle overwrite per contract |
| `DirectoryNotEmptyException` | Deleting a directory that still contains entries | Do not auto-delete recursively unless authorized |
| `NotDirectoryException` | A path component expected to be a directory is not one | Check path structure and input data |
| `FileSystemLoopException` | Encountered a cycle while traversing symbolic links | Check link policy and tree-walking logic |
| `AtomicMoveNotSupportedException` | Requested `ATOMIC_MOVE` but provider does not support it | Fail safely or intentionally fall back to non-atomic move |
| Other `IOException` | Device error, data corruption, network, quota, provider... | Do not infer as missing or denied |

**Note:** this classification covers **common scenarios** and does not guarantee a single unique exception for every physical fault. A disk, mount, or provider error may surface under a broader type.

### `FileAlreadyExistsException` Does Not Automatically Mean You Should Overwrite

For example, `Files.createFile(target)` attempts to create a new file, but the file already exists. This can be a **valid contract signal**: do not lose existing data. You should not switch it to `Files.writeString(target, ...)` with default options because a write operation can **truncate** existing data.

If you want to create a new file **only when it does not yet exist**, prefer operations supporting `CREATE_NEW` or `Files.createFile` rather than doing `if (!Files.exists(path))` before creating.

### `DirectoryNotEmptyException` Does Not Permit Auto-Cleaning the Whole Tree

A handler like:

```java
catch (DirectoryNotEmptyException ex) {
    // DO NOT automatically delete all child files if the contract does not allow it.
}
```

should treat this as a signal requiring an explicit policy: reject deletion, require confirmation, move to an archive area, or perform recursive deletion only when designed and authorized.

`Files.delete(path)` does not delete an entire directory tree by default.

## 7. Complete Java 17+ Example: OS-Independent Exception Classification

To verify error types and `FileSystemException` information with **deterministic stdout**, the program below intentionally **constructs exception objects** rather than assuming the operating system will deny permissions in a specific way.

Save the file **`NioExceptionCatalogDemo.java`**:

```java
import java.io.IOException;
import java.nio.file.AccessDeniedException;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.DirectoryNotEmptyException;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.FileSystemException;
import java.nio.file.FileSystemLoopException;
import java.nio.file.NoSuchFileException;
import java.nio.file.NotDirectoryException;

public class NioExceptionCatalogDemo {

    static String classify(IOException error) {
        if (error instanceof NoSuchFileException) {
            return "MISSING";
        }
        if (error instanceof AccessDeniedException) {
            return "DENIED";
        }
        if (error instanceof FileAlreadyExistsException) {
            return "ALREADY_EXISTS";
        }
        if (error instanceof DirectoryNotEmptyException) {
            return "NOT_EMPTY";
        }
        if (error instanceof NotDirectoryException) {
            return "NOT_DIRECTORY";
        }
        if (error instanceof FileSystemLoopException) {
            return "LINK_LOOP";
        }
        if (error instanceof AtomicMoveNotSupportedException) {
            return "NO_ATOMIC_MOVE";
        }
        return "IO_OTHER";
    }

    static String display(String value) {
        return value == null ? "-" : value;
    }

    static void show(IOException error) {
        System.out.println(
                classify(error)
                + " | " + error.getClass().getSimpleName());

        if (error instanceof FileSystemException fs) {
            System.out.println(
                    "file=" + display(fs.getFile())
                    + "; other=" + display(fs.getOtherFile())
                    + "; reason=" + display(fs.getReason()));
        }
    }

    public static void main(String[] args) {
        show(new NoSuchFileException("data/missing.csv"));

        show(new AccessDeniedException(
                "private/report.txt", null, "permission denied"));

        show(new FileAlreadyExistsException("output/result.csv"));

        show(new DirectoryNotEmptyException("archive/old"));

        show(new NotDirectoryException("data/items"));

        show(new FileSystemLoopException("links/current"));

        show(new AtomicMoveNotSupportedException(
                "diskA/input.csv",
                "diskB/input.csv",
                "atomic move unsupported"));

        show(new IOException("general I/O problem"));
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 NioExceptionCatalogDemo.java
java NioExceptionCatalogDemo
```

**Exact stdout:**

```text
MISSING | NoSuchFileException
file=data/missing.csv; other=-; reason=-
DENIED | AccessDeniedException
file=private/report.txt; other=-; reason=permission denied
ALREADY_EXISTS | FileAlreadyExistsException
file=output/result.csv; other=-; reason=-
NOT_EMPTY | DirectoryNotEmptyException
file=archive/old; other=-; reason=-
NOT_DIRECTORY | NotDirectoryException
file=data/items; other=-; reason=-
LINK_LOOP | FileSystemLoopException
file=links/current; other=-; reason=-
NO_ATOMIC_MOVE | AtomicMoveNotSupportedException
file=diskA/input.csv; other=diskB/input.csv; reason=atomic move unsupported
IO_OTHER | IOException
```

### Why Is This a Reliable Classification Demo?

- It does not depend on whether the current account has root/administrator privileges.
- It does not need to create files and change permissions in a Linux/Windows-specific way.
- Each constructor provides concrete file/reason data; unpassed fields may be `null` and are printed as `-`.
- The handler accepts the general `IOException` type but branches using `instanceof` on the exception, **not by parsing message text**.
- The example shows that `FileSystemException` carries secondary path and reason information, **not just a single-line message**.

**Limitation to understand:** the program constructs exceptions to teach classification; it **does not prove** that a real file operation on every provider will throw the exact same-named subclass for each line.

## 8. Catching Exceptions in the Right Order

When handling NIO, subclasses should appear **before** the handler for the superclass:

```java
try {
    String text = Files.readString(path);
    useText(text);

} catch (NoSuchFileException ex) {
    handleMissing(ex);

} catch (AccessDeniedException ex) {
    handleDenied(ex);

} catch (IOException ex) {
    handleOtherIo(ex);
}
```

This is an **illustrative skeleton**, assuming valid imports and `useText`/`handleMissing`/`handleDenied`/`handleOtherIo` methods. This structure allows a distinct policy for each error, followed by fallback handling for any other `IOException`.

### Why Not Catch `IOException` First?

The following snippet is invalid:

```java
// Intentionally DOES NOT COMPILE.
try {
    Files.readString(path);
} catch (IOException ex) {
    handleOtherIo(ex);
} catch (NoSuchFileException ex) {
    handleMissing(ex);
}
```

Because `NoSuchFileException` is a subclass of `IOException`, the subsequent `catch (NoSuchFileException)` branch is **unreachable**: the preceding parent branch already catches all objects belonging to this subclass.

### Can You Use Multi-Catch?

If two errors share the exact same policy:

```java
catch (NoSuchFileException | AccessDeniedException ex) {
    reportUnavailable(ex);
}
```

This is an illustrative handler. `NoSuchFileException` and `AccessDeniedException` are siblings in the type tree, so multi-catch is valid.

However, **do not combine them just because both represent failure**. If a missing file is optional while access denied is an operational error requiring an alert, they **must have two different policies**.

## 9. Complete Java 17+ Example: Real NIO Operations in a Temporary Directory

The next example creates, reads, and copies a file, then simulates existing-target and missing-file cases using real NIO operations. It avoids fixed file names in the project to prevent overwriting the learner's data.

Save the file **`NioFileWorkflowDemo.java`**:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class NioFileWorkflowDemo {

    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("nio-lesson-");
        Path source = directory.resolve("source.txt");
        Path target = directory.resolve("copy.txt");
        Path missing = directory.resolve("missing.txt");

        try {
            Files.writeString(
                    source,
                    "alpha",
                    StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE_NEW);

            System.out.println(
                    "source="
                    + Files.readString(source, StandardCharsets.UTF_8));

            Files.copy(source, target);

            System.out.println(
                    "copy="
                    + Files.readString(target, StandardCharsets.UTF_8));

            try {
                Files.copy(source, target);
                System.out.println("unexpected overwrite");
            } catch (FileAlreadyExistsException ex) {
                System.out.println("copy=ALREADY_EXISTS");
            }

            try {
                Files.readString(missing, StandardCharsets.UTF_8);
                System.out.println("unexpected missing read");
            } catch (NoSuchFileException ex) {
                System.out.println("read=MISSING");
            }

        } finally {
            Files.deleteIfExists(target);
            Files.deleteIfExists(source);
            Files.deleteIfExists(missing);
            Files.deleteIfExists(directory);
        }
    }
}
```

Run with JDK 17+:

```bash
javac -encoding UTF-8 NioFileWorkflowDemo.java
java NioFileWorkflowDemo
```

**Stdout on a typical default file system**, when file creation/deletion is permitted and the provider returns the specific subclasses as shown in the example:

```text
source=alpha
copy=alpha
copy=ALREADY_EXISTS
read=MISSING
```

**Do not assert this stdout is absolute in every environment.** The program uses real file APIs; permissions, providers, antivirus filters, disk conditions, and races with other processes can cause another `IOException`, or classification may differ from a standard file system. In such cases, the program lets the unhandled exception propagate to the caller/JVM (via `main throws IOException`) rather than masking it with a fake success value.

### Why Use `CREATE_NEW` on the Source File?

`Files.writeString` without explicit options typically creates the file if absent and truncates an existing file. Here `StandardOpenOption.CREATE_NEW` is used to **create a new file only**, avoiding accidental overwrites.

With `CREATE_NEW`, the existence check and file creation are performed as an atomic operation with respect to new-file creation per the API contract, rather than `if (!Files.exists(...))` followed by `Files.writeString(...)`, which has a race window.

### Why Not Use `REPLACE_EXISTING` on the Second Copy?

`Files.copy(source, target)` by default does not automatically replace an existing target in normal cases. The second copy is meant to illustrate that **"target already exists" is a meaningful failure type**, not a command that should immediately overwrite.

`StandardCopyOption.REPLACE_EXISTING` can be used when the contract **explicitly allows replacement**, after considering data safety. You should not add this option just to avoid seeing `FileAlreadyExistsException`.

### Why Use `finally` to Clean Up the Temporary Directory?

The example opens/writes multiple files and then intentionally triggers caught exceptions. `finally` attempts to delete the created files and directory even if an error occurs in the body. However, **deletion can also throw `IOException`**, and an exception thrown in `finally` can mask an error from the `try` body. For `AutoCloseable` resources like streams/channels, you should usually use `try-with-resources`; for file deletion in a short example, `finally` demonstrates cleanup intent, not a general rollback recipe.

In production, if cleanup can fail concurrently with the main operation, you need a strategy that preserves both errors—for example, saving the primary exception and attaching the secondary error via `addSuppressed` when appropriate.

## 10. A Missing File Can Be Handled with an Optional Result; a Permission Error Should Not

An **optional** configuration file might have the contract:

- File exists and is readable: return contents.
- File does not exist: return an "absent" result; caller uses default.
- Access denied or other I/O error: **report the error**, do not pretend it is "absent".

Java 17+ example as a method:

```java
static java.util.Optional<String> readOptionalConfig(
        java.nio.file.Path path) throws java.io.IOException {

    try {
        return java.util.Optional.of(
                java.nio.file.Files.readString(path));

    } catch (java.nio.file.NoSuchFileException missing) {
        return java.util.Optional.empty();
    }
}
```

This is a **runnable illustrative method when placed inside a class**. It only translates `NoSuchFileException` to `Optional.empty()`. If `AccessDeniedException` or another `IOException` occurs, the method **still throws it** for the caller to handle.

**Contract note:** `Optional.empty()` here represents a missing file according to this API's own policy; it does not assert that the path remains absent at all subsequent moments. Another thread/process might create the file right after the operation fails.

### When the File Is Required

For a required import file:

```java
static String readRequired(
        java.nio.file.Path path) throws java.io.IOException {

    return java.nio.file.Files.readString(path);
}
```

There is no need to catch `NoSuchFileException` just to rethrow it without adding context. If the service layer must translate a filesystem error into a domain error, wrap it **with the right semantics and preserve the cause**:

```java
try {
    return Files.readString(path);
} catch (NoSuchFileException cause) {
    throw new RequiredInputMissingException(
            "Required import source is missing", cause);
}
```

This snippet is an **illustrative skeleton** with an application-defined custom exception `RequiredInputMissingException` having a constructor that accepts `Throwable cause`. Do not use `new RuntimeException(cause.getMessage())` if you want to preserve the original error's stack/cause.

## 11. Do Not Use `Files.exists` as Sufficient Proof for the Next Operation

A common code pattern:

```java
if (Files.exists(path)) {
    return Files.readString(path);
}
return "";
```

This snippet has two problems:

1. **Time-of-check-to-time-of-use (TOCTOU):** the file can be deleted/replaced or permissions can change between `exists` and `readString`.
2. **`Files.exists` does not prove the file is readable:** the path may exist but have access denied, be a directory, or encounter a file-system provider failure.

Even when `Files.exists(path)` returns `false`, it **does not always prove the file does not exist**; in some cases the existence status cannot be determined. Per the contract of `Files.exists`/`Files.notExists`, both can return `false` if existence cannot be determined with certainty.

Therefore, to read a file according to policy:

- **Perform `Files.readString` or open the file directly**.
- Catch the exception subclasses for which the caller has an explicit policy.
- Let other `IOException`s propagate or be translated with their cause.
- Do not rely on pre-check chains as a substitute for actual error handling.

### `Files.isReadable` Is Not a Permanent Permit Either

`Files.isReadable(path)` can be useful for UI or preliminary checks, but a `true` result does not guarantee that a subsequent open will succeed. Permissions and system state can change; some providers represent permissions differently.

Do not write:

```java
// Anti-pattern: assuming isReadable eliminates all IOExceptions.
if (Files.isReadable(path)) {
    return Files.readString(path);
}
```

without an error-handling contract for the read operation.

## 12. Path Normalization, Symbolic Links, and Security Risks

`Path.normalize()` removes redundant elements such as `.` and `..` using **syntactic rules**; it does not necessarily access the file system or resolve symbolic links.

`Path.toRealPath(...)` may require the actual file to exist in order to resolve the path, involves I/O, and can throw `IOException`. Checking whether a path lies within an allowed directory using only `normalize` and `startsWith` may be insufficient in environments with symbolic links or concurrently modified entries.

Example:

```java
Path root = Path.of("uploads");
Path requested = root.resolve(userSuppliedName).normalize();
```

This is an illustrative skeleton; `userSuppliedName` comes from an untrusted source. Lexical path checking is **one step**, not a complete sandbox solution:

- Sequences of `..` can cause a path to escape the intended directory.
- A symbolic link can point to a location outside `root`.
- Another thread/process can modify an entry between the check step and the open step.
- Operating system or container access permissions remain a separate layer of protection.

For security-sensitive operations, you need to design process permissions, link policies, and race-resistant directory opening/traversal mechanisms, potentially considering `SecureDirectoryStream` on supporting providers. Do not claim that `normalize()` alone blocks all path traversal.

### `NOFOLLOW_LINKS` Changes Certain Checks

Some APIs accept `LinkOption.NOFOLLOW_LINKS` to inspect **the symbolic link itself** rather than following it to its target. For example:

```java
boolean isLink = Files.isSymbolicLink(path);
boolean presentWithoutFollowing =
        Files.exists(path, LinkOption.NOFOLLOW_LINKS);
```

This is an illustrative snippet. A dangling symlink can exist as a link even when its target does not exist; therefore, asking "does the file exist?" must clarify whether you are asking about **the link** or **the link's target**.

Using `NOFOLLOW_LINKS` is not a standalone safety guarantee against races. You need to understand whether each API and provider supports that option for the operation in question.

## 13. `FileSystemLoopException` and Directory Tree Traversal

`Files.walkFileTree` allows traversing a directory tree with callbacks such as `visitFile` and `visitFileFailed`. When requested to follow symbolic links (for example with `FileVisitOption.FOLLOW_LINKS`), a chain of links can form a **cycle**.

When a loop is detected, `FileSystemLoopException` can be passed to `visitFileFailed` so the application can decide whether to report an error or skip it according to policy.

Illustrative skeleton:

```java
Files.walkFileTree(
        root,
        java.util.EnumSet.of(
                java.nio.file.FileVisitOption.FOLLOW_LINKS),
        Integer.MAX_VALUE,
        new java.nio.file.SimpleFileVisitor<Path>() {

            @Override
            public java.nio.file.FileVisitResult visitFileFailed(
                    Path file, IOException ex) throws IOException {

                if (ex instanceof
                        java.nio.file.FileSystemLoopException) {
                    throw ex; // Intentional failure.
                }
                throw ex;
            }
        });
```

This is an **illustrative snippet**, requiring imports for `Path`, `Files`, `IOException`, and a valid `root` variable. The handler could be simplified to `throw ex;` if the policy is fail-fast for all errors; checking `FileSystemLoopException` here is just to highlight the scenario.

You should not automatically ignore every `visitFileFailed` during security scans or backups, because the traversal result will be missing data while potentially being misreported as "successful".

### Does Traversing All Files Guarantee No Race Errors?

No. During traversal, files can be created, deleted, or have their permissions changed by other processes. `visitFileFailed` needs a clear policy. If an application requires a consistent snapshot, `Files.walkFileTree` alone does not create a transaction or snapshot of the entire file system.

## 14. `AtomicMoveNotSupportedException` When Requesting an Atomic Move

`Files.move(source, target, StandardCopyOption.ATOMIC_MOVE)` requests a file/rename operation using the provider's **atomic move** capability:

```java
Files.move(
        source,
        target,
        java.nio.file.StandardCopyOption.ATOMIC_MOVE);
```

This snippet is illustrative code. If the operation cannot be performed atomically, the provider may throw **`AtomicMoveNotSupportedException`**.

### Falling Back from Atomic to Non-Atomic: Not Always Safe

Some applications choose:

```java
try {
    Files.move(source, target, StandardCopyOption.ATOMIC_MOVE);
} catch (AtomicMoveNotSupportedException ex) {
    Files.move(source, target);
}
```

This is an illustrative snippet with appropriate imports and path variables. This policy is only reasonable when **the application permits non-atomic moves** and has considered the consequences if the process crashes midway.

If the application must ensure that the output file is published intact or that data never enters a half-written state, a non-atomic fallback can **break correctness**. In that case, you should propagate the error to the caller and report that the provider does not meet the requirement.

Also note: how **an existing target** is handled under `ATOMIC_MOVE` can have implementation-specific rules. Do not assume all other copy/move options retain the exact same semantics when combined with `ATOMIC_MOVE`.

## 15. Classifying Error Types for APIs/Services Instead of Parsing `getMessage()`

A service may want to translate NIO errors into public codes. For example:

| Original Exception Type | Suggested Application Code | Context Check Before Returning to Client |
| --- | --- | --- |
| `NoSuchFileException` | `RESOURCE_NOT_FOUND` | Is the missing file truly a resource the client is allowed to know about? |
| `AccessDeniedException` | `STORAGE_ACCESS_DENIED` | Do not expose internal paths or permission configurations |
| `FileAlreadyExistsException` | `DESTINATION_EXISTS` | Is it a create-new operation with a contract conflict? |
| `DirectoryNotEmptyException` | `DIRECTORY_NOT_EMPTY` | Is recursive deletion permitted? |
| `AtomicMoveNotSupportedException` | `ATOMIC_MOVE_UNAVAILABLE` | Is atomicity required? |
| Remaining `IOException` | `STORAGE_IO_ERROR` | Needs technical logging and a separate retry policy |

These codes are only **application-defined examples**, not standard NIO constants.

You cannot automatically infer that `NoSuchFileException` must always be HTTP 404 or `AccessDeniedException` must always be HTTP 403. An internal file error can be a **server error**, not a client error. HTTP mapping must be based on the API contract and what information is permitted to be disclosed.

### Do Not Arbitrarily Turn Permission Errors into Missing

In secure systems, an API sometimes intentionally returns a "not found" message rather than confirming that a resource exists but is forbidden, to avoid leaking resource existence. If that choice is made, it must belong to **security policy at the API boundary**, not generic default logic that masks every `AccessDeniedException` as `NoSuchFileException` at the file layer.

Internal logging should still preserve the **original error classification** so operations know an actual permission issue occurred.

## 16. Retries and Races: Which Errors Can Be Retried?

There is no rule that "every `IOException` should be retried" or "every `NoSuchFileException` is transient".

- **NoSuchFileException:** if the file will be created in the future by an asynchronous producer per contract, bounded retries can sometimes be reasonable. If the path is wrong due to configuration, infinite retries are useless.
- **AccessDeniedException:** usually requires fixing permissions/credentials/policies; immediate retries do not help, though dynamic authentication or mount environments may have exceptions.
- **FileAlreadyExistsException:** sometimes a normal race between two tasks creating the same name; requires an idempotency policy or unique naming, not blind overwriting.
- **AtomicMoveNotSupportedException:** you cannot "retry multiple times" to make a provider support atomic move, unless the target environment is intentionally changed.
- **Other IOException:** requires knowing the specific error, operation type, safety of repetition, and prior side-effect state.

Especially with **writes or moves**, when an exception occurs, the caller does not always know for sure that **no side effects occurred**. A retry can create duplicates, overwrite data, or corrupt consistency if there is no idempotency mechanism.

Do not wrap all `Files` operations in a generic retry loop without timeouts, retry limits, and recovery criteria.

## 17. Using `try-with-resources` with File Streams and Channels

Some `Files` APIs return `AutoCloseable` objects such as `InputStream`, `OutputStream`, `BufferedReader`, `Stream<Path>` in the case of `Files.list`, or `Stream<String>` with `Files.lines`. When the current scope owns the resource, it should close it promptly:

```java
static long countLines(Path path) throws IOException {
    try (java.util.stream.Stream<String> lines =
                 Files.lines(path)) {
        return lines.count();
    }
}
```

This is an **illustrative method**, requiring imports for `Path`, `Files`, and `IOException`.

To analyze errors thoroughly:

1. **Opening the source** can throw checked `IOException`, including NIO subclasses.
2. **Reading in the pipeline** can surface `UncheckedIOException` per the `Files.lines` contract if I/O fails during traversal.
3. **Closing the source** still runs when exiting `try-with-resources`; if both the body and close fail, one error can be attached as **suppressed** under the primary exception.
4. `getCause()` and `getSuppressed()` help investigate relationships, not just the outermost `getMessage()`.

**Do not return a live `Stream` out of a closed scope** and expect the caller to continue iterating over it. If an API hands off a stream to the caller, it must document who is responsible for closing it and when errors can arise.

## 18. File Operations Can Throw Multiple Error Types at Different Stages

A `Files.copy` or `Files.move` call can involve:

- The source path.
- The target path.
- Read/write/directory access permissions.
- Whether the target file exists.
- Symbolic link behavior.
- Copy/move options supported by the provider.
- I/O errors after the operation has already started.

You should not just read a method name and guess "if it fails, it's probably `AccessDeniedException`". Each operation has different failure conditions; consult the Javadoc of the API being called when implementing specific policies.

For example, `Files.copy` can throw `FileAlreadyExistsException` if the target already exists and no overwrite policy is selected, but it can also throw `NoSuchFileException` if the source is deleted right before execution, or another `IOException` due to device/network issues.

### Create-New and Overwrite Options

`Files.writeString(path, content)` with default settings can create a file if it does not exist and write/truncate an existing file. If only creating a new file is allowed, add `StandardOpenOption.CREATE_NEW` appropriately.

`Files.copy(source, target, StandardCopyOption.REPLACE_EXISTING)` expresses permission to replace the target if allowed, but it does not guarantee a general atomic transaction. Do not conflate **allowing overwrite** with **recoverability if the copy fails**.

## 19. Analyzing Stack Traces and Messages Properly

Illustrative format example:

```text
java.nio.file.NoSuchFileException: data/missing.csv
    at ... <provider frame>
    at ... <application frame>
```

Or:

```text
java.nio.file.AccessDeniedException: private/report.txt
    at ... <provider frame>
    at ... <application frame>
```

This is **not fixed stdout**; line numbers, internal classes, providers, and messages can vary. On some providers, a reason may be appended to the message. Do not rely on the exact text of a stack trace to make decisions.

Good diagnostic workflow:

1. **Read the actual exception type**.
2. **Identify the `Files` operation running** and the source/target roles.
3. **Read `getFile()`, `getOtherFile()`, and `getReason()`** if it is a `FileSystemException`.
4. **Check relative/absolute paths**, file system, mounts, permissions, and existence at investigation time; do not assume the current state matches the state at the time of failure.
5. **Inspect cause and suppressed exceptions** in wrapper layers when needed.
6. **Distinguish technical errors from business policy**: optional missing differs from required missing; denied may require operational action.
7. **Protect sensitive data** when logging and returning messages.

Do not just do:

```java
System.out.println(ex.getMessage());
```

and treat that as the entire diagnosis. When a logger supports `Throwable` objects, pass the full exception at the appropriate boundary to preserve stack/cause/suppressed, while avoiding logging the same incident repeatedly at every layer.

## 20. Practical Scenarios for Choosing a Handler

### Scenario A: Reading Optional Configuration

**Rule:** use a default if configuration is missing; report an error if access is denied.

Suggestion: catch `NoSuchFileException` and return `Optional.empty()`, letting other `IOException`s propagate. Only use a default when missing is genuinely a valid business condition.

### Scenario B: Uploading a File with a Unique Name

**Rule:** if the name already exists, reject the operation instead of overwriting.

Suggestion: create the file using `CREATE_NEW`; catch `FileAlreadyExistsException` and return a structured conflict error. Do not rely on `Files.exists` before creating due to races.

### Scenario C: Deploying a Configuration File That Must Be Published Atomically

**Rule:** publish only a complete version.

Suggestion: write a temporary file in the appropriate area, verify completion, then consider `Files.move(..., ATOMIC_MOVE)`. If `AtomicMoveNotSupportedException` is thrown, **re-evaluate the requirement** rather than blindly falling back to a non-atomic move.

### Scenario D: Deleting a Directory Containing User Data

**Rule:** delete a directory only when it is empty or when there is explicit confirmation/policy for recursive deletion.

Suggestion: `Files.delete`; if `DirectoryNotEmptyException`, reject or route to an authorized workflow. Do not auto-run recursive delete just to "fix the exception".

### Scenario E: Collecting Statistics on a Directory Tree with Symbolic Links

**Rule:** accurately report that some entries could not be traversed.

Suggestion: `Files.walkFileTree` with an explicit `FOLLOW_LINKS` policy, distinguishing `FileSystemLoopException` in `visitFileFailed` when needed; do not swallow every `IOException` and report a complete scan.

## 21. Common Misconceptions and Mistakes

| Mistake or Misconception | Why It Is Dangerous | How to Fix |
| --- | --- | --- |
| "`NoSuchFileException` and `FileNotFoundException` are the same class" | They are two different subtypes of `IOException` | Check the hierarchy and source API |
| "Every missing file always reports `NoSuchFileException`" | Providers and contexts can differ | Catch useful subtypes and fall back to `IOException` |
| "`AccessDeniedException` is a `SecurityException`" | One is checked, the other is unchecked | Distinguish OS/provider policies from Java security checks |
| "`Files.exists` returning false proves the file definitely does not exist" | Existence state may be indeterminate | Rely on actual operations and exceptions |
| "If `isReadable` is true, `readString` cannot fail" | TOCTOU, permission changes, other I/O errors | Handle errors at the actual operation |
| "`Path.of` automatically checks if the file exists" | It only creates a path object | Check when performing I/O |
| "Catch `IOException` before subclasses for convenience" | Subsequent subclass branches become unreachable | Catch subtypes first |
| "Return `Optional.empty()` on denied errors" | Masks operational/permission failures | Only use empty for valid missing cases |
| "Missing file means create an empty file" | Can violate contract and mask broken config | Distinguish optional vs. required |
| "If target exists, always pass `REPLACE_EXISTING`" | Can lose data or violate idempotency | Require explicit overwrite policy |
| "If atomic move is unsupported, always fall back" | Can break consistency requirements | Only fall back when policy permits |
| "`normalize()` is enough to block all path traversal" | Symbolic links/races still exist | Use proper path and permission controls |
| "`Files.copy` failing means nothing changed" | Copy/move can have partial side effects | Design recovery and inspect state |
| "`getReason()` always has text" | It can be null | Check for null and log structurally |
| "`FileSystemException.getFile()` returns `Path`" | It returns `String` | Do not assume canonical path |
| "`IOException` catches all NIO errors" | `InvalidPathException` and unchecked errors are not caught | Understand each API's contract |
| "Retrying every `IOException` is safe" | File writes may not be idempotent | Classify and bound retries |
| "`Files.lines` auto-closes after `count()`" | Terminal operations do not guarantee `close` | Use `try-with-resources` |
| "Having the message is enough" | Loses error type, secondary path, cause, and suppressed | Log `Throwable` with safe context |

## 22. Self-Check Exercises

**Exercise A — Exception classification**

Are `NoSuchFileException` and `AccessDeniedException` checked exceptions?

**Yes.** Both extend `FileSystemException`, and then `IOException`, so the compiler requires catching or declaring them when a call can let them escape under a checked contract.

**Exercise B — Catch ordering**

Can you place `catch (IOException)` before `catch (NoSuchFileException)`?

**No.** The subsequent subclass handler is unreachable because the parent handler already catches all instances of the subclass.

**Exercise C — Two path properties**

To retrieve the primary file and secondary file from a `FileSystemException`, what do you call?

**`getFile()` and `getOtherFile()`**, returning strings that may be null. `getReason()` provides an additional reason if available.

**Exercise D — Optional config**

Should `NoSuchFileException` when reading an optional configuration file always crash the application?

**Not necessarily.** If the contract allows missing, you can use a default or `Optional.empty()`. However, do not apply the same policy to `AccessDeniedException`.

**Exercise E — Checking access**

If `Files.exists(path)` returns `true`, can you omit `IOException` handling on `Files.readString(path)`?

**No.** The file could be deleted, have its permissions changed, or hit an I/O error between the check and the read.

**Exercise F — Target already exists**

When `Files.createFile(path)` throws `FileAlreadyExistsException`, should you automatically overwrite?

**Not by default.** You need a create-new contract, avoid data loss, and handle races with the appropriate primitive.

**Exercise G — No atomic move**

If `Files.move(..., ATOMIC_MOVE)` throws `AtomicMoveNotSupportedException`, what can falling back to plain `Files.move(...)` change?

**It loses the atomicity guarantee of the original requirement.** Only fall back if the business logic permits non-atomic moves.

**Exercise H — Null `getReason()`**

Can you chain `getReason().toLowerCase()` without checking?

**No.** `getReason()` can be null; furthermore, you should not classify errors by the reason text.

**Exercise I — Missing file via relative path**

Is `Path.of("config/app.txt")` guaranteed to reference the directory containing the source code?

**No.** It is resolved according to the file system/working directory context of the process.

**Exercise J — A read error can occur late**

`Files.lines(path)` opens successfully. Can the terminal `toList()` still encounter an I/O error during iteration?

**Yes.** Some errors during stream traversal can surface as `UncheckedIOException`. Opening successfully does not guarantee reading the entire file will succeed.

**Exercise K — File-system providers differ**

Is a demo that tries to change POSIX permissions and expects `AccessDeniedException` reliable across all Windows/Linux setups?

**No.** Permission systems, providers, and process privileges differ. To teach classification, you can construct structured exceptions; to run integration tests, you need a clearly controlled permission environment.

**Exercise L — Deleting a directory**

Does `DirectoryNotEmptyException` mean `Files.delete` will automatically delete child files?

**No.** It reports that the request to delete a non-empty directory cannot be performed under current conditions; cleaning up the entire tree is a separate decision.

## 23. Checklist for Real-World Code

Before handling an NIO operation that can fail:

1. **Know the operation's contract:** `Files.readString`, `copy`, `move`, `delete`, `walkFileTree`, or another API?
2. **Know whether the file is required or optional:** is missing an error or a valid absent result?
3. **Handle subtypes first:** `NoSuchFileException`, `AccessDeniedException`, `FileAlreadyExistsException`... when policies genuinely differ.
4. **Have a fallback for remaining `IOException`s:** do not assume every failure belongs to the two familiar types.
5. **Do not confuse checked and unchecked:** `InvalidPathException`/`SecurityException` are not caught by `IOException`.
6. **Preserve the root cause:** when wrapping errors at the service layer, pass the `cause` object instead of only copying the message.
7. **Read structured path information:** `getFile()`, `getOtherFile()`, `getReason()`, checking for null.
8. **Do not expose internal paths:** logs and responses must respect access controls; do not print secrets/sensitive paths to clients.
9. **Avoid pre-checking and trusting it absolutely:** `exists`/`isReadable` do not prevent races.
10. **Use explicit create/overwrite options:** `CREATE_NEW` differs from `CREATE` and `REPLACE_EXISTING`.
11. **Control overwrite and delete:** do not automatically delete/overwrite data outside the contract.
12. **Consider symbolic links and traversal:** define `NOFOLLOW_LINKS` policy and path boundaries.
13. **For atomic move, do not fall back arbitrarily:** uphold consistency requirements.
14. **Close resources in the right scope:** use `try-with-resources` for streams/channels/`Files.lines`/`Files.list`.
15. **Check state after copy/move errors:** partial side effects may occur depending on the operation.
16. **Evaluate retries and idempotency:** only retry when justified and bounded.
17. **Test on target providers:** do not extrapolate Linux permission behavior to Windows or zip/cloud providers.
18. **Do not use messages as a protocol:** exception types and stable application codes are the proper basis for branching.

## Conclusion

`NoSuchFileException`, `AccessDeniedException`, and other `FileSystemException` subclasses help Java NIO distinguish **missing paths**, **denied permissions**, and other filesystem failures. Distinguishing them properly enables applications to handle **optional missing files**, **permission failures**, **existing-target conflicts**, **unsupported atomic moves**, or **non-empty directories** under separate policies.

Even so, **the exact error type still depends on the operation and file-system provider**; there is no rule that "every missing/denied error always surfaces as a single subtype" across all environments. Catch subtypes when you have a clear policy, keep a general `IOException` handler, read `getFile()/getOtherFile()/getReason()` with null checks, preserve causes, and handle resources/races/permissions responsibly. A reliable file-handling program must treat **errors as part of the I/O contract**, not as incidents to swallow and continue as if everything succeeded.