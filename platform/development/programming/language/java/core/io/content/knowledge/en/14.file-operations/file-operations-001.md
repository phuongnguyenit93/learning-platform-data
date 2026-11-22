# Files.createFile, createDirectory, and createDirectories in Java

In Java NIO.2, the `java.nio.file.Files` class provides three common operations to **create new resources** on the file system:

- `Files.createFile(path)`: creates **an empty file**.
- `Files.createDirectory(path)`: creates **a single directory**; parent directories must already exist.
- `Files.createDirectories(path)`: creates **the specified directory and any missing parent directories**; does not treat an existing valid target directory as an error.

The names of these three methods are very similar, yet they differ significantly in resource type, parent directory requirements, whether an existing target is allowed, and atomicity. Choosing the wrong one easily leads to `FileAlreadyExistsException`, `NoSuchFileException`, or a partially created directory tree.

This lesson uses `Path`/`Files` on Java 17+ and creates resources inside temporary directories in the examples so as not to touch user data.

## 1. Quick Comparison Table

| API | Resource created | Creates missing parent directories? | If the target already exists? | Initial data |
|---|---|---|---|---|
| `Files.createFile(path)` | Regular file | **No** | Fails; usually `FileAlreadyExistsException` | Empty file, size 0 bytes |
| `Files.createDirectory(path)` | A single directory | **No** | Fails; usually `FileAlreadyExistsException` | New empty directory |
| `Files.createDirectories(path)` | One or more missing directories | **Yes** | Succeeds if the target is already a suitable directory; fails if the target is a non-directory file | New empty directories |

All three methods return a `Path` object corresponding to the passed path, making it convenient to continue using in the program. All of these methods can throw `IOException` or its subclasses depending on actual conditions.

**Important:** `createFile` does not create text content, does not write headers, and does not open an `OutputStream` for the caller. If you want to write data immediately upon creation, you can use `Files.writeString`/`Files.newOutputStream` with appropriate `StandardOpenOption` values.

## 2. Path Only Describes Location; Files Interacts with Disk

`Path` is an object representing a path. Merely creating a `Path` does not create a real file or directory:

~~~java
// Illustrative snippet; requires importing java.nio.file.Path.
Path file = Path.of("data", "report.txt");
// No file creation operation happens here yet.
~~~

Only when calling `Files.createFile(file)` does Java ask the file system to create the corresponding resource. A path can be:

- **Relative:** `Path.of("data", "report.txt")`, interpreted relative to the working directory or provider context.
- **Absolute:** for example `Path.of("data").toAbsolutePath().resolve("report.txt")`.
- **A path from another provider:** ZIP file system, virtual file system, or custom file system. They may enforce different rules regarding permissions, roots, names, attribute support, and error messages.

Do not manually concatenate `"/"` or `"\\"` to build cross-platform paths. `Path.of("a", "b", "c")` and `resolve(...)` represent path components according to the corresponding provider.

## 3. Files.createFile: Creates Only a Single Empty File

Common signature:

~~~java
public static Path createFile(
        Path path, FileAttribute<?>... attrs) throws IOException
~~~

`attrs` is an optional parameter to set attributes at creation time, such as access permissions on systems supporting POSIX. If you do not need to configure attributes yet, just call `Files.createFile(path)`.

Example:

~~~java
// Illustrative snippet; the logs directory must exist beforehand.
Path file = Path.of("logs", "app.log");
Files.createFile(file);
~~~

### Behaviors to Remember

1. Creates **a new, empty file** at the exact `path`; does not create the parent `logs` directory if it does not exist.
2. Checking that the name does not exist and creating the file are performed **atomically against all other file system operations that affect the same directory** according to the `Files.createFile` contract. This helps avoid the "check `exists` first, then create" race pattern.
3. If the target name is already used by a file or directory, the operation fails. `FileAlreadyExistsException` is the common error type and is the specific exception a provider may use.
4. If the parent directory does not exist or is not a valid directory, the operation fails; `NoSuchFileException` or another I/O exception is commonly thrown depending on the file system.
5. Does not automatically create parent directories, does not write bytes to the file, and does not return an open write stream to the caller.
6. The file exists on disk after the method returns successfully; deleting it requires a separate operation (`Files.delete` or `Files.deleteIfExists`).

Distinguish **creating a file** from **opening a file for writing**:

~~~java
// Illustrative snippet: file is a defined Path.
Files.createFile(file);        // Creates an empty file; errors if it already exists.
Files.writeString(file, "Hi"); // Writes data using default open options.
~~~

Two separate operations can be interfered with by another actor between calls. If the requirement is **create new and write immediately without overwriting**, consider opening the file directly with `StandardOpenOption.CREATE_NEW` instead of creating it first and opening it afterward.

## 4. Files.createDirectory: Creates One Level, Parent Must Exist

Similar signature:

~~~java
public static Path createDirectory(
        Path dir, FileAttribute<?>... attrs) throws IOException
~~~

Example:

~~~java
// Illustrative snippet; the work directory must exist.
Files.createDirectory(Path.of("work", "reports"));
~~~

If `work` exists and permits child creation, the method creates the `reports` directory. If `work` does not exist yet, `createDirectory` does not silently generate `work`: the operation will fail.

Example with multiple levels:

~~~text
workspace/
    (no 'images' directory yet)
~~~

Calling:

~~~java
Files.createDirectory(Path.of("workspace", "images", "icons"));
~~~

will fail when `workspace/images` does not yet exist. `createDirectory` creates only the final level; it has no mechanism to generate the entire chain of parent directories.

If the target already exists, even if it is itself a valid directory, `createDirectory` still does not treat this as a request to "ensure the directory is present." It must create a **new** directory and typically throws `FileAlreadyExistsException` when it cannot create it due to a name collision.

## 5. Files.createDirectories: Creates Missing Parent Directories Too

`Files.createDirectories(dir)` is the choice when you need to ensure the existence of a directory tree along a path, such as `data/2026/reports`:

~~~java
// Illustrative snippet:
Path reports = Path.of("data", "2026", "reports");
Files.createDirectories(reports);
~~~

If `data` and `data/2026` are missing, the method creates the necessary directories in sequence; if one or more levels already exist as directories, they can be reused.

### Key Differences from createDirectory

- If the target directory **already exists and is a valid directory**, `createDirectories` usually completes normally without forcing an error.
- If a component needed as a directory **is actually a regular file**, a child directory cannot be created through it; the method fails.
- If permissions are insufficient, the path is invalid, the storage device fails, or a provider does not support the operation, an exception can still be thrown.
- **Not atomic across the entire tree**: if creating multiple levels and failing at a later level, **some parent directories may have already been created**. There is no automatic rollback to delete the levels that succeeded.

Therefore, `createDirectories` is suitable for preparing typical directory structures, but it is not a "transaction" guaranteeing all-or-nothing. If cleanup after an error is needed, you must clearly identify which directories were created by the current run and whether other tasks are still using them.

## 6. Runnable Example: All Three Methods

Create the file **`CreatePathsDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.Path;

public class CreatePathsDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("create-demo-");
        Path reports = root.resolve("reports");
        Path nested = root.resolve("data").resolve("2026").resolve("exports");
        Path report = reports.resolve("summary.txt");

        try {
            Files.createDirectory(reports);
            System.out.println("reportsDir=" + Files.isDirectory(reports));

            Files.createDirectories(nested);
            System.out.println("nestedDir=" + Files.isDirectory(nested));

            Files.createFile(report);
            System.out.println("fileExists=" + Files.isRegularFile(report));
            System.out.println("fileSize=" + Files.size(report));

            // Target is already a directory: not an error with createDirectories.
            Files.createDirectories(nested);
            System.out.println("nestedAgain=" + Files.isDirectory(nested));

            try {
                Files.createFile(report);
            } catch (FileAlreadyExistsException ex) {
                System.out.println("duplicateFile=FileAlreadyExistsException");
            }
        } finally {
            Files.deleteIfExists(report);
            Files.deleteIfExists(nested);
            Files.deleteIfExists(nested.getParent());
            Files.deleteIfExists(nested.getParent().getParent());
            Files.deleteIfExists(reports);
            Files.deleteIfExists(root);
        }
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac -encoding UTF-8 CreatePathsDemo.java
java CreatePathsDemo
~~~

Stdout on a standard default file system:

~~~text
reportsDir=true
nestedDir=true
fileExists=true
fileSize=0
nestedAgain=true
duplicateFile=FileAlreadyExistsException
~~~

Explanation:

1. `Files.createTempDirectory(...)` creates a temporary directory with a unique name; the program does not guess a fixed path that might already exist.
2. `createDirectory(reports)` creates a single level `reports` because its parent `root` already exists.
3. `createDirectories(nested)` creates the three levels `data/2026/exports` as needed.
4. `createFile(report)` creates `summary.txt` with an initial size of 0 bytes.
5. Calling `createDirectories(nested)` a second time still succeeds because `nested` is already a directory.
6. Calling `createFile(report)` a second time fails because the filename already exists; on the default file system, the specific error is `FileAlreadyExistsException`.
7. `finally` deletes the file first, then deletes the directories from deepest to shallowest. `Files.deleteIfExists` **does not recursively delete** a non-empty directory; the steps are intentionally written in the proper order.

If another actor concurrently modifies the temporary area or system permissions are lacking, any file operation example can fail for I/O reasons; the stdout shown here is for an environment running with a normal file system.

## 7. Comparison Example: Missing Parent Directory and Existing Target Name

Suppose `root` is an existing directory. `createFile(root/missing/a.txt)` cannot automatically create `missing`, and `createDirectory(root/missing/leaf)` also cannot automatically create `missing`.

Create the file **`CreateFailuresDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.NoSuchFileException;
import java.nio.file.Files;
import java.nio.file.Path;

public class CreateFailuresDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("create-errors-");
        Path missing = root.resolve("missing");
        Path file = root.resolve("marker.txt");

        try {
            try {
                Files.createFile(missing.resolve("a.txt"));
            } catch (NoSuchFileException ex) {
                System.out.println("createFile: missing parent");
            }

            try {
                Files.createDirectory(missing.resolve("leaf"));
            } catch (NoSuchFileException ex) {
                System.out.println("createDirectory: missing parent");
            }

            Files.createDirectories(missing.resolve("leaf"));
            System.out.println("createDirectories: nested exists="
                    + Files.isDirectory(missing.resolve("leaf")));

            Files.createFile(file);
            try {
                Files.createDirectory(file);
            } catch (FileAlreadyExistsException ex) {
                System.out.println("createDirectory: target exists");
            }
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(missing.resolve("leaf"));
            Files.deleteIfExists(missing);
            Files.deleteIfExists(root);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 CreateFailuresDemo.java
java CreateFailuresDemo
~~~

Stdout with the default Unix/Windows file system:

~~~text
createFile: missing parent
createDirectory: missing parent
createDirectories: nested exists=true
createDirectory: target exists
~~~

This illustrates common specialized exceptions; **the contract for some specific exceptions is documented in Javadoc as implementation-optional**. In applications supporting multiple providers, you still need to handle `IOException` when the exact expected subclass is not received.

Do not write logic relying solely on exception messages because their content can vary by OS/locale/implementation; prioritize exception types, application state, and the requested operation.

## 8. Atomicity and Race Conditions: "Check Then Create" Is Unsafe

Problematic code pattern:

~~~java
// Illustrative snippet; unsafe under concurrent competition.
if (Files.notExists(file)) {
    Files.createFile(file);
}
~~~

Between `Files.notExists(file)` and `Files.createFile(file)`, another thread or process may create that exact file. `Files.notExists` only reflects an observation at the time of checking; moreover, `exists/notExists` are not exact logical negations of each other when existence cannot be verified.

If the goal is "create a new file, never overwrite existing data," call `Files.createFile(file)` directly and handle the appropriate exception. By contract, `createFile`'s check-and-create action is atomic with respect to other file system operations affecting the directory.

Similarly, `Files.createDirectory(dir)` requests creating **a new directory**; do not use an "if it does not exist then create" pattern to assume it is guaranteed to succeed. If "the directory already exists" is acceptable as a valid state, `Files.createDirectories(dir)` usually better expresses your intent.

However, atomicity of **creating a single object** is not atomicity of **a sequence of multiple objects**. `createDirectories(a/b/c)` may leave `a` or `a/b` behind after failing at a deeper level. During cleanup, never indiscriminately delete directories that another thread or process already created or is using.

## 9. Want to Both Create a File and Write Content: Use CREATE_NEW

If you need to write bytes or text to a file **only if the file does not yet exist**, you can instruct the open/write API to use `StandardOpenOption.CREATE_NEW`. It combines the create-new policy with the open operation in one step, avoiding the race window between two separate `createFile` and `writeString` calls.

Create the file **`CreateAndWriteDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class CreateAndWriteDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("fresh-write-");
        Path file = root.resolve("result.txt");

        try {
            Files.writeString(
                    file,
                    "Hello\n",
                    StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE_NEW,
                    StandardOpenOption.WRITE);

            System.out.println("content="
                    + Files.readString(file, StandardCharsets.UTF_8).strip());

            try {
                Files.writeString(
                        file,
                        "Overwrite?",
                        StandardCharsets.UTF_8,
                        StandardOpenOption.CREATE_NEW,
                        StandardOpenOption.WRITE);
            } catch (FileAlreadyExistsException ex) {
                System.out.println("secondWrite=refused");
            }
            System.out.println("unchanged="
                    + Files.readString(file, StandardCharsets.UTF_8)
                            .equals("Hello\n"));
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(root);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 CreateAndWriteDemo.java
java CreateAndWriteDemo
~~~

Stdout:

~~~text
content=Hello
secondWrite=refused
unchanged=true
~~~

What the result illustrates:

- The first write creates the file with UTF-8 content. `CREATE_NEW` requires creating a new file and forbids using an existing file as the target.
- The second write is refused, so the `Hello\n` data remains intact.
- `WRITE` expresses the write intent. When writing text with `Files.writeString`, explicitly choose the charset according to the required storage format (here UTF-8).
- If you only use `Files.writeString(file, text)` without specifying options, the default API behavior can create a nonexistent file but **truncate** an existing one. It does **not** mean "create new only."
- The parent directory must already exist. If the parent does not exist yet, create the directory structure using `createDirectories(parent)` under the right policy before writing.

Another option is `Files.newOutputStream(path, StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE)` and writing bytes in chunks when the data is large, ensuring the stream is closed with `try-with-resources`.

## 10. Initial Attributes and Access Permissions

All three file/directory creation methods take the varargs parameter `FileAttribute<?>... attrs`. The goal is to set supported attributes **immediately upon creation**, avoiding a time window where the resource exists with unintended default permissions.

Example on a file system supporting POSIX:

~~~java
// Illustrative snippet; use only when the file system supports POSIX.
import java.nio.file.attribute.PosixFilePermissions;
import java.nio.file.attribute.FileAttribute;

FileAttribute<?> privateDir =
        PosixFilePermissions.asFileAttribute(
                PosixFilePermissions.fromString("rwx------"));
Files.createDirectory(path, privateDir);
~~~

The snippet above **is not a complete Java program**: `import` statements must be placed at the top of the file, and the `path` variable must be declared. Its purpose is to show creating a directory with POSIX permissions `rwx------` (only the owner can read/write/access in the POSIX sense). On Windows or a default provider that does not support the POSIX view, this approach may be unsuitable or throw `UnsupportedOperationException`; do not assume every provider uses POSIX permissions.

With `createDirectories(path, attrs)`, the attributes are passed into each directory creation step per the API contract, yet the supported attribute set and effective permissions are also affected by the provider, ACLs, umask, and operating system rules. **Verify actual permissions if the application handles sensitive data.**

On the other hand, if the resource **already exists**, `createDirectories` is not an API for updating permissions on the existing directory. To change permissions, use another attribute API with appropriate permission controls.

## 11. Existing Paths and Symbolic Links

When checking state, distinguish:

- **Regular file** at the target: `createFile`/`createDirectory` cannot create a new object with the same name; `createDirectories` cannot treat a file as a directory.
- **Existing directory**: `createDirectories` can succeed without recreating it; `createDirectory` requires a new one so it fails.
- **Symbolic link**: the path may be a link pointing to another file or directory. Checks like `Files.isDirectory(path)` by default may **follow links**; link-following policy must be determined by business requirements and the API.
- **Broken symbolic link**: the link path exists at the name level, though the link's target may not exist. Do not equate it with a safe empty slot for creating a new file.

If the program processes paths supplied by untrusted users, do not run a sequence of `exists`/`normalize`/`createDirectories` and implicitly conclude it is safe. There are risks of **TOCTOU** (check-then-use), symbolic links changing between operations, or parent directories pointing outside the allowed region.

For example, an application allowed to write only inside `workspace` needs clear policies on absolute paths, `..`, symlinks, permissions, existing objects, and file open timing. A lexical check `candidate.normalize().startsWith(base)` is useful but **insufficient on its own** to protect the file system against a concurrent actor altering symlinks.

## 12. Exception Handling and Retry Policy

Common exceptions:

| Exception / situation | Common cause | How to handle |
|---|---|---|
| `FileAlreadyExistsException` | `createFile`/`createDirectory` name collision | Reject or pick another name; do not silently overwrite |
| `NoSuchFileException` | Missing parent directory or path component | Verify parent; use `createDirectories` if business logic permits |
| `AccessDeniedException` | Insufficient read/write/create permissions at the location | Adjust permissions or report error; do not retry indefinitely |
| `SecurityException` | SecurityManager or deployment security policy may deny it | Handle according to application security policy |
| `UnsupportedOperationException` | Provider does not support requested attributes on creation | Choose compatible attribute set or handle per platform |
| Other `IOException` | Out of disk space, target is not a directory, I/O failure, race, resource modified | Log with proper context; do not assume a single cause |

Specific subclasses are sometimes **optional specific exceptions** in Javadoc, so when supporting arbitrary providers, there must be a general `IOException` handling branch. Do not handle errors by catching everything and ignoring them, or creating a directory tree regardless of the original intent.

Especially with `createDirectories`: when an error occurs mid-way, some levels may already exist. On retry, the method can usually continue if those levels are suitable directories. However, if a non-directory file exists at some level or the file system state changes, retrying can still fail. Therefore, **retries must have a sound reason, bounds, and an appropriate cleanup/rollback strategy**.

## 13. Common Pitfalls

1. **Confusing `Path.of(...)` with file creation:** `Path.of` only represents a path and does not touch the file system.
2. **Using `createFile` and expecting it to auto-generate parent directories:** it does not; create the parent separately if allowed.
3. **Using `createDirectory` to create `a/b/c` when `a/b` does not exist:** use `createDirectories` or create each level individually.
4. **Assuming `createDirectories` only creates when the target is absent and always errors on a second call:** if the target is still a directory, repeated calls can succeed.
5. **Assuming `createDirectories` is a transaction:** there is no full rollback when creating one level fails.
6. **Checking `Files.notExists` first and believing there is no longer a race:** state can change between the two calls.
7. **Using `createFile` to open an existing file for writing:** creation operations are not for overwriting or appending. Choose a write API with the right `OpenOption` policy.
8. **Using `Files.writeString(path, text)` thinking it refuses to overwrite:** by default it can truncate; use `CREATE_NEW` when overwriting must be prevented.
9. **Catching `FileAlreadyExistsException` and assuming the target is definitely a directory:** the target could be a file, symlink, or another object type; verify according to policy.
10. **Choosing POSIX permissions for every operating system:** the provider may not support them; check capabilities and permission/ACL mechanisms.
11. **Using `deleteIfExists(dir)` on a directory that still has children:** this is not recursive tree deletion.
12. **Assuming lexical path checks prevent all symbolic link issues:** real file system protection requires safe checking and opening designs suited to the context.

## 14. Quick Selection Guide by Requirement

**Create a new file without writing content:** choose `Files.createFile(path)`. If a file already exists, return a clear error; do not silently delete it.

**Create exactly one new directory inside an existing parent:** choose `Files.createDirectory(dir)`. If the target already exists and the business logic considers that an error, preserve the exception.

**Prepare a multi-level directory path or ensure an existing directory:** choose `Files.createDirectories(dir)`. Keep in mind that a file sitting at any level is an error, and creating multiple levels can partially succeed.

**Create a new file and write immediately with an overwrite-prevention policy:** choose `Files.writeString(..., CREATE_NEW, WRITE)` or `newOutputStream(..., CREATE_NEW, WRITE)`. This is usually clearer in intent and reduces the race window compared to separate create + open-for-write operations.

**Create temporary data:** choose `Files.createTempFile(...)` for files or `Files.createTempDirectory(...)` for directories. Temp APIs choose names automatically to reduce collision risk, though the application must still close resources and clean up when appropriate.

**Applications with multiple processes or sensitive data:** define permissions, ownership, symlinks, lifecycle, and TOCTOU handling; these three creation methods do not replace a full transactional or file authorization mechanism.

## 15. Key Takeaways

- `createFile` **creates exactly one empty file** and **does not create parents**.
- `createDirectory` **creates exactly one new directory**, requiring the parent to already exist.
- `createDirectories` **creates missing directories along the chain**, accepts an existing target directory, yet **is not atomic for the entire chain**.
- When a filename may already exist, do not check manually then overwrite; use an appropriate create-new / overwrite-prevention mechanism such as `CREATE_NEW`.
- File systems can reject calls due to missing permissions, resource type conflicts, symlinks, and I/O issues; handle specific errors where possible while always understanding the source of exceptions.
- For examples or tests, create a temporary directory, operate inside it, and clean up bottom-up; with real data, never delete outside owned scope.

### References

- [Java 17 — Files.createFile/createDirectory/createDirectories](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
- [Java 17 — StandardOpenOption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardOpenOption.html)
- [Java 17 — Path](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html)
- [Java 17 — FileAttribute](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/FileAttribute.html)
