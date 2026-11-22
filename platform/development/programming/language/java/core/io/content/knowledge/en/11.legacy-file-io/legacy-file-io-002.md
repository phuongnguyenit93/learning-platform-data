# Creating a `File` Object Does Not Create a Physical File in Java

When you write `new File("report.txt")`, Java **only creates an object describing a path**; it does not yet create `report.txt` on disk. This is a crucial point in **Legacy File I/O** (`java.io.File`): a `File` object can point to an existing file, a directory, a non-existent path, or an inaccessible path. The existence of the Java object and the existence of the resource on the file system are **two different things**.

Minimal example:

```java
File report = new File("report.txt"); // Only creates an object representing the name/path
boolean exists = report.exists();     // Asks the file system if the corresponding resource exists
```

The snippet requires `import java.io.File;`. `new File(...)` does not perform a physical file creation operation. `exists()` checks the path state at the time of the call; it may be `false` if the file does not exist yet. If the file already existed beforehand, `exists()` may return `true` immediately after the constructor, but the constructor itself **was not what created the file**.

This lesson explains the nature of `File`, the methods that actually create files/directories, error handling, a runnable JDK 17+ example, and things to know when migrating to `java.nio.file.Path` / `Files`.

## 1. A File Object Is Only a Path Representation

The Java documentation defines `File` as an **abstract representation of file and directory pathnames**. It is not the file content, not an open byte stream, and not a mandatory handle bound to an existing file.

Visualize it like this:

```text
In the JVM                             On disk
----------------------------------   -------------------------------
File f = new File("data/a.txt");      data/a.txt may not exist yet
        |
        +-- stores path information
        +-- has getPath(), getName()
        +-- can call exists(), isFile()
        |
        +-- DOES NOT automatically open, write, or create a physical file
                                        |
f.createNewFile() ---------------------> creates an empty file if not present
Files.writeString(...) ---------------> may create/write the file
new FileOutputStream(f) -------------> may create/open the file for writing
```

All three cases are valid:

1. `File f = new File("a.txt")` when `a.txt` **does not exist yet**: the object `f` is still created.
2. `File f = new File("a.txt")` when `a.txt` **already exists**: the object `f` is still created, without recreating or overwriting.
3. `File f = new File("reports")` when `reports` is a **directory**: the object `f` is still created; check `isDirectory()` to determine the resource type.

The constructor can report programming errors such as a `null` path, but it does **not** verify that the file exists or automatically create parent directories. Do not treat constructor success as proof that data has been written.

### Distinguishing Path Names and Real Resources

| Concept | Example | Meaning |
| --- | --- | --- |
| `File` object | `new File("data.txt")` | Path representation in JVM memory |
| Relative path | `"data.txt"` | Resolved against the process's working directory |
| Absolute path | `"C:\\data\\data.txt"`, `"/tmp/data.txt"` | Specifies a location independent of the current directory (per OS rules) |
| Resource on the file system | Regular file, directory, symbolic link, etc. | Exists only when the file system contains the corresponding entry |
| Open stream | `FileInputStream` / `FileOutputStream` | Actual interaction with source/destination bytes, with a close lifecycle |

`File` does not guarantee that the named path is a regular file; it could point to a **directory**. Moreover, the resource can be created, deleted, or renamed by another process **after** the `File` object has been created.

## 2. Every Constructor Only Creates a Path Object

Common ways to instantiate:

```java
File a = new File("notes.txt");
File b = new File("data", "notes.txt");
File parent = new File("data");
File c = new File(parent, "notes.txt");
```

The snippet requires `java.io.File`.

None of the four lines **creates a file or directory**. `b` and `c` are constructed from parent/child parts; the parent part not existing on disk does not prevent creating these objects. Constructing a path object does not automatically create intermediate parent directories.

In particular, the two lines below are not equivalent:

```java
new File("logs");  // Only creates a File object describing "logs"
new File("logs").mkdir(); // Attempts to create the "logs" directory on the file system
```

Only the second line requests an I/O operation, which can succeed or fail and whose result must be checked.

Even `getAbsolutePath()` **only returns path information**:

```java
File f = new File("missing.txt");
System.out.println(f.getAbsolutePath());
```

This statement prints an absolute path string based on the working directory. It does **not** create `missing.txt`, and the result is not proof that the file is present. `getCanonicalPath()`/`getCanonicalFile()` can normalize the path according to file system rules and may throw `IOException`, but they are not equivalent to creating a physical file.

## 3. Checking Existence and Resource Type

`File` provides several status-probing methods:

| Method | Meaning |
| --- | --- |
| `exists()` | Checks whether the corresponding path currently has an accessible resource according to the API |
| `isFile()` | Checks whether it is a **regular file** |
| `isDirectory()` | Checks whether it is a **directory** |
| `length()` | Gets file size in bytes; if it is not a regular file or an error occurs, the result is insufficient to conclude content |
| `lastModified()` | Last modified time reported by the file system, with limited value when non-existent/error |
| `canRead()` / `canWrite()` | Checks reported read/write capability at the time of the call |
| `getName()` / `getParent()` / `getPath()` | Extracts path information; does not require the resource to exist |

Example:

```java
File candidate = new File("config/app.properties");
if (candidate.isFile()) {
    System.out.println("Đang trỏ tới một file thường");
} else if (candidate.isDirectory()) {
    System.out.println("Đang trỏ tới thư mục");
} else {
    System.out.println("Không có file thường/thư mục truy cập được tại đường dẫn");
}
```

This is a code snippet with `import java.io.File;`.

**Do not infer too much from boolean results:**

- `exists() == false` may mean the path does not exist yet, but it can also involve access permissions/system errors. A boolean alone cannot diagnose all causes.
- `isFile() == false` does **not** guarantee the path is definitely empty: it could point to a directory or another type of file system entry.
- `length() == 0` does **not** prove the file is empty: it could be a non-existent path or an error.
- `canWrite() == true` does not guarantee the upcoming write operation will succeed; permissions and state can change.
- After checking `exists()`, another process can still create/delete the file right before the next operation. This is the **TOCTOU** (*time-of-check to time-of-use*) problem.

When an action needs to ensure "create new if absent, fail if already present," prefer an atomic create-new operation rather than checking separately with `exists()` and then opening for writing.

## 4. Which Operations Actually Create a Physical File?

### 4.1. `File.createNewFile()`

```java
File output = new File("result.txt");
boolean created = output.createNewFile();
```

This is a snippet requiring `java.io.File`, and `IOException` must be handled.

Meaning:

- Creates an **empty file** at `output`'s path when **no entry with the same name exists**, performing existence check and creation as an atomic operation per the API contract.
- Returns `true` if **newly created successfully**.
- Returns `false` if an entry with the same name **already exists**; does not overwrite automatically.
- May throw `IOException` if the file cannot be created due to I/O errors, missing parent directory, access permissions, or other system conditions.
- Does not automatically create missing parent directories.
- The newly created file has a length of 0 bytes; it does not yet contain text or application content.

Therefore:

```java
File f = new File("result.txt");
System.out.println(f.createNewFile()); // true when newly created
System.out.println(f.createNewFile()); // false if the file still exists
```

The two `println` lines illustrate the result **under the condition that no other agent modifies the path** and the first creation succeeds. It cannot be guaranteed that every system allows writing at the example path.

### 4.2. `Files.createFile(path)`

Modern NIO API:

```java
Path path = Path.of("result.txt");
Files.createFile(path);
```

This is a snippet requiring `java.nio.file.*` and `IOException` handling.

`Files.createFile(...)` also requests creating a **new empty file** with an atomic existence check and creation. The easily observable difference is: **if the path already exists, it usually throws `FileAlreadyExistsException`**, instead of returning `false` like `File.createNewFile()`. Other errors are also typically provided as more informative `IOException` subtypes.

Use `Files.createFile(...)` in new designs with `Path`; use `createNewFile()` when working with the legacy `java.io.File` API.

### 4.3. Opening a Write Stream Can Also Create a File

`new FileOutputStream(file)` or `new FileWriter(file)` is an operation that opens an **actual write target**, and can:

- Create a new file if the path does not exist yet and the parent directory is valid.
- Overwrite/truncate existing file content if using the default non-append constructor.
- Fail if lacking permissions, the path is invalid, the parent directory does not exist yet, or it points to an unwritable resource.

Example:

```java
File f = new File("message.txt"); // File not created yet
try (FileOutputStream out = new FileOutputStream(f)) {
    out.write(new byte[] { 65, 66, 67 }); // Writes "ABC" as bytes
}
```

This is a snippet; it requires `java.io.File`, `java.io.FileOutputStream`, and `IOException` handling. **Opening `FileOutputStream`** can create the file; `new File` does not. For an existing file, `FileOutputStream(f)` clears old content by default before writing. To append, use a constructor with the appropriate append flag and understand the system's append rules.

For text data, you can also use:

```java
Files.writeString(Path.of("message.txt"), "Xin chào",
        StandardCharsets.UTF_8);
```

In Java 17, when no `OpenOption` is passed, `Files.writeString` defaults to `CREATE`, `TRUNCATE_EXISTING`, and `WRITE`: it can **create the file if absent or overwrite its content if present**. You need to import `java.nio.file.*`, `java.nio.charset.StandardCharsets`, and handle `IOException`. Do not use that default for important user files if you do not want to overwrite them.

## 5. Creating Directories Differs from Creating Regular Files

`File` has two important methods:

```java
File single = new File("logs");
boolean one = single.mkdir();

File nested = new File("reports/2026/october");
boolean many = nested.mkdirs();
```

The snippet requires `java.io.File`. Here:

- `mkdir()` attempts to create **a single directory**. If a parent directory is missing, the operation normally fails.
- `mkdirs()` attempts to create the target directory **and any missing parent directories**. When it fails, some parent directories **may already have been created**, so the operation is not a full rollback transaction.
- Both return `true` when the target directory **was created by that call**, and `false` if it could not be created; `false` can also occur because the directory already exists.
- `mkdirs()` does not mean creating a text file `october`; it attempts to create a **directory** with that name.

Pattern for a file inside a non-existent directory:

```java
File file = new File("reports/2026/result.txt");
File parent = file.getParentFile();

if (parent != null && !parent.isDirectory()) {
    if (!parent.mkdirs() && !parent.isDirectory()) {
        throw new IOException("Cannot create parent directory");
    }
}
boolean created = file.createNewFile();
```

This is a snippet; it requires `java.io.*`. Checking a second time with `isDirectory()` helps handle the case where another actor just created the directory before `mkdirs()` returned. However, the filesystem can continue changing between statements; the snippet does not eliminate all races.

NIO is usually clearer when creating multi-level directories:

```java
Path folder = Path.of("reports", "2026");
Files.createDirectories(folder);
Path file = folder.resolve("result.txt");
Files.createFile(file);
```

The snippet requires `java.nio.file.*` and `IOException` handling. `Files.createDirectories` is not `Files.createFile`: the former creates **directories**, the latter creates a **regular file**.

## 6. Standalone, Verifiable Java 17+ Runnable Example

The example uses a **separate temporary directory** so it does not depend on an existing file in the project directory. It shows what happens at each step, then deletes the created resources.

Save as `FileObjectVsDiskDemo.java`:

```java
import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class FileObjectVsDiskDemo {
    public static void main(String[] args) throws IOException {
        // This method actually creates a temporary directory on disk.
        Path root = Files.createTempDirectory("file-path-demo-");

        // resolve(...) and toFile() only prepare the paths/objects.
        Path parent = root.resolve("reports").resolve("2026");
        Path name = parent.resolve("lesson.txt");
        Path generated = parent.resolve("generated.txt");

        try {
            File f = name.toFile();

            System.out.println("after new File: " + f.exists());
            System.out.println("parent exists: " + Files.exists(parent));

            System.out.println("mkdirs: " + parent.toFile().mkdirs());

            System.out.println("first createNewFile: " + f.createNewFile());
            System.out.println("second createNewFile: " + f.createNewFile());

            System.out.println("isFile: " + f.isFile());
            System.out.println("isDirectory: " + f.isDirectory());

            Files.writeString(generated, "Hello", StandardCharsets.UTF_8);
            System.out.println("writeString created: "
                    + Files.isRegularFile(generated));
            System.out.println("read: "
                    + Files.readString(generated, StandardCharsets.UTF_8));
        } finally {
            // Clean up from child to parent; deleteIfExists does not recursively delete directory trees.
            Files.deleteIfExists(generated);
            Files.deleteIfExists(name);
            Files.deleteIfExists(parent);
            Files.deleteIfExists(root.resolve("reports"));
            Files.deleteIfExists(root);
        }
    }
}
```

Compile/run:

```bash
javac FileObjectVsDiskDemo.java
java FileObjectVsDiskDemo
```

Stdout in an environment where temporary files are writable and no agent modifies the paths between operations:

```text
after new File: false
parent exists: false
mkdirs: true
first createNewFile: true
second createNewFile: false
isFile: true
isDirectory: false
writeString created: true
read: Hello
```

Explanation:

1. `Files.createTempDirectory(...)` **actually creates a temporary directory** to host the example. This differs from `new File(...)`.
2. `root.resolve(...)` creates a `Path` pointing to a non-existent name; `name.toFile()` creates a `File` object. `exists()` is still `false` because no physical file exists yet.
3. `parent.toFile().mkdirs()` creates `reports` and `reports/2026`, so the result is `true`.
4. The first `f.createNewFile()` creates the empty file `lesson.txt` and returns `true`; the second returns `false` because the entry already exists.
5. `f.isFile()` confirms a regular file; `f.isDirectory()` is `false`.
6. `Files.writeString(generated, ...)` creates `generated.txt` and writes the bytes of `"Hello"` in UTF-8; `readString` reads it back.
7. `finally` deletes files first, then child directories. If a cleanup operation encounters an I/O error, Java will throw an exception; the example should not be considered a robust cleanup mechanism for every OS/race condition.

The example is designed with a new temporary path, yet output still depends on file/directory creation permissions and the file system not being modified concurrently. Hardcoding absolute paths in stdout is avoided to keep tests reproducible across Windows, Linux, and macOS.

## 7. Different File Creation Approaches Have Different Behaviors

| Call | Automatically creates physical file/directory? | If path already exists |
| --- | --- | --- |
| `new File(path)` | **No** | Only creates a path object |
| `Path.of(path)` | **No** | Only creates a `Path` object |
| `file.getAbsolutePath()` | **No** | Only returns a path string |
| `file.exists()` | **No** | Only probes state |
| `file.createNewFile()` | **Yes: empty file** if absent | Returns `false` |
| `Files.createFile(path)` | **Yes: empty file** if absent | Usually throws `FileAlreadyExistsException` |
| `file.mkdir()` | **Yes: one directory** if creatable | Returns `false` |
| `file.mkdirs()` | **Yes: chain of needed directories** if creatable | May return `false` |
| `Files.createDirectories(path)` | **Yes: needed directories** | Succeeds if the path is already a suitable directory |
| `new FileOutputStream(file)` | May create/open file for writing | Truncates existing file by default |
| `new FileOutputStream(file, true)` | May create file if absent | Opens for appending |
| `Files.writeString(path, text, UTF_8)` | May create and write file | Truncates old content by default |
| `File.createTempFile(...)` | **Yes: creates an actual empty temp file** | API chooses a suitable name per temp-creation mechanism |
| `Files.createTempFile(...)` | **Yes: creates an actual empty temp file** | API chooses a suitable name per temp-creation mechanism |
| `Files.createTempDirectory(...)` | **Yes: creates an actual temp directory** | API chooses a suitable name per temp-creation mechanism |

The contrast between `new File(...)` and `File.createTempFile(...)` is worth remembering: both API names mention `File`, but **the constructor only creates an object**, whereas **the `createTempFile` factory has side effects on the file system**.

## 8. A File Can Exist Without Being a Regular File

Suppose a directory named `data` already exists:

```java
File candidate = new File("data");
System.out.println(candidate.exists());
System.out.println(candidate.isFile());
System.out.println(candidate.isDirectory());
```

This snippet is illustrative only. Provided `data` is an accessible directory, the results are `true`, `false`, and `true` respectively.

This means:

- `exists()` checks whether a resource is at the path, **not** whether it is the expected type.
- If the program needs to read a regular file, check `isFile()` or use a read API with proper error handling.
- If the program needs to create a file `data` when a directory with the same name already exists, `createNewFile()` cannot turn that directory into a regular file.
- If the program needs to create a directory `data` when a regular file with the same name already exists, `mkdirs()` cannot turn that file into a directory.

In many cases, you do not need to call `exists()` or `isFile()` beforehand; performing the required read/write operation and handling `IOException` avoids a race window between checking and using.

## 9. Relative Paths, Working Directory, and Real Location

`new File("output.txt")` creates an object with a **relative path**. The location the program looks at depends on the JVM's effective working directory. It must not be equated with the directory containing `.java` files, the location displayed by an IDE, or the directory containing `.class` files.

Example:

```java
File f = new File("output.txt");
System.out.println(f.getPath());
System.out.println(f.getAbsolutePath());
System.out.println(f.getCanonicalPath());
```

The snippet requires `java.io.File` and handling `IOException` from `getCanonicalPath()`. The three results can differ in containing a relative, absolute, and canonical path. **None of the methods above creates a file.**

A few notes:

- Depending on the operating system, the path separator may be `/` or `\`. Do not manually concatenate paths with an inappropriate character when you can use `new File(parent, child)` or `Path.resolve(...)`.
- `getAbsolutePath()` does not guarantee that all `.`/`..` components are normalized like a real path. `getCanonicalPath()` returns the canonical form per system rules and may require interacting with the filesystem.
- `Path.toAbsolutePath()` and `Path.normalize()` also **do not create files**. `normalize()` mainly performs syntactic normalization and does not replace validating the real resource.
- `Path.toRealPath()` is different: it queries the filesystem and usually requires the path to actually exist. It also **does not create the resource**.
- If the path string is supplied by a user, you must validate the allowed access scope in the application; creating a `File` does not guarantee the path is safe or resides in the intended directory.

## 10. Missing Parent Directory: A Common Error

Here is a very typical mistake:

```java
File file = new File("reports/2026/summary.txt");
file.createNewFile();
```

If `reports/2026` does not exist yet, `createNewFile()` is not responsible for creating those directories; the operation can throw `IOException`. When a task requires creating a file inside a new directory structure, you need to:

1. Determine the parent path properly.
2. Create/verify the parent directories using `mkdirs()` or `Files.createDirectories(...)`.
3. Create the actual file with `createNewFile()`/`Files.createFile(...)` or open a stream with the desired options.
4. Write content and close resources, then check the result or handle exceptions.

NIO example:

```java
Path target = Path.of("reports", "2026", "summary.txt");
Files.createDirectories(target.getParent());
Files.writeString(target, "Báo cáo",
        StandardCharsets.UTF_8, StandardOpenOption.CREATE_NEW);
```

This is a **snippet**; it requires `java.nio.file.*`, `java.nio.charset.StandardCharsets`, and `IOException` handling. `StandardOpenOption.CREATE_NEW` requires creating a new file and fails if the path already exists; this approach helps prevent overwriting existing data. It differs from the default behavior of `Files.writeString` when no options are supplied.

If you only want to "create an empty file and ensure no overwrite," use `Files.createFile(target)` after preparing the parent directory. If you want to "open a file for writing and allow overwriting," explicitly select `CREATE`/`TRUNCATE_EXISTING` according to business requirements.

## 11. Checking Existence Before Creating Is Not a Transaction

This code is problematic if two processes run concurrently:

```java
if (!file.exists()) {
    // Between the two lines, another process could create a file with the same name.
    Files.writeString(file.toPath(), "content",
            StandardCharsets.UTF_8);
}
```

Another party can create the file **after** `exists()` but **before** `writeString(...)`. Then, because the default write mode can truncate an existing file, the program risks overwriting content that does not belong to it.

If the requirement is to create only when it does not exist, use a create-new operation:

```java
try {
    Files.writeString(file.toPath(), "content",
            StandardCharsets.UTF_8, StandardOpenOption.CREATE_NEW);
} catch (FileAlreadyExistsException e) {
    // Handle the state where the file name is already taken.
}
```

This snippet requires importing `java.nio.file.*`, `java.nio.charset.StandardCharsets`; other `IOException`s must still be handled.

`File.createNewFile()` also combines checking and creating an empty file under an atomic contract. However, after creating an empty file, if the program closes and reopens it to write, another process can still modify the filesystem in between. To be safer, choose to open with `CREATE_NEW` so the create-and-write requirement happens right within the same open operation as supported by the provider.

Do not use file existence/non-existence to build a homemade inter-process locking mechanism. Java has `FileLock` and more appropriate coordination mechanisms; even an atomic create-new operation cannot replace all synchronization/access-control requirements.

## 12. Deleting a File Reference Does Not Delete the Physical File

The opposite misconception is also very common:

```java
File f = new File("report.txt");
f = null;
```

Dropping the reference to `File` or letting the object be collected by the garbage collector **does not delete the file on disk**, does not close an independent open stream, and does not affect the real path. File resources are modified by concrete I/O operations such as `delete()`, `Files.delete(...)`, or corresponding writes/moves.

Example:

```java
File f = new File("report.txt");
boolean deleted = f.delete();
```

Only `delete()` requests deleting the corresponding entry and returns `boolean`. It can fail, and it does not recursively delete non-empty directories. With NIO, `Files.delete(path)` or `Files.deleteIfExists(path)` provides appropriate deletion operations and can report more detailed errors.

You also should not call `deleteOnExit()` and assume the resource is deleted immediately. This is only a **request to delete upon normal JVM termination**, not a substitute for resource lifecycle management and error checking of an actual delete operation.

## 13. Resources and Ownership When Opening Streams

A `File` object typically does not need `close()`, because it only represents a path and has no `close()` method itself. However, streams/readers/channels used to manipulate actual data usually must be closed:

```java
File f = new File("input.txt");
try (FileInputStream in = new FileInputStream(f)) {
    int firstByte = in.read();
    // Process firstByte; -1 means EOF.
}
```

This snippet requires `java.io.*` and `IOException` handling. The `FileInputStream` constructor opens a resource for **reading** and can throw `FileNotFoundException` when the file does not exist or cannot be read; **it does not automatically create a missing file**.

Conversely, the `FileOutputStream` constructor for **writing** can create a new file. Thus two similarly named classes have different file-creation behaviors. From `new File(...)`, you cannot infer that a file is opened for reading or writing.

Wrap streams/readers in try-with-resources to release handles even when exceptions occur. You do not need to arbitrarily close shared system resources owned by another component.

## 14. Choosing `File` or `Path`/`Files`?

`java.io.File` remains common when interacting with older APIs, libraries requiring `File`, or when learning I/O fundamentals. However, Java NIO provides `java.nio.file.Path` and the `Files` utility class offering clearer file operations:

| Task | Legacy `java.io.File` | Java NIO |
| --- | --- | --- |
| Represent path without creating resource | `new File("data.txt")` | `Path.of("data.txt")` |
| Check existence | `file.exists()` | `Files.exists(path)` |
| Check regular file | `file.isFile()` | `Files.isRegularFile(path)` |
| Create new empty file | `file.createNewFile()` | `Files.createFile(path)` |
| Create a single directory | `file.mkdir()` | `Files.createDirectory(path)` |
| Create entire parent directory tree | `file.mkdirs()` | `Files.createDirectories(path)` |
| Write UTF-8 text | `FileWriter` with appropriate charset | `Files.writeString(path, text, UTF_8)` |
| Delete path | `file.delete()` | `Files.delete(path)` |
| Convert between the two types | `file.toPath()` | `path.toFile()` on the default filesystem |

`Files.exists(...)` and NIO probing operations also have limitations regarding races/permissions. When an operation needs to distinguish failure causes, NIO methods that throw specific `IOException`s are often more useful than `File`'s booleans.

Another reason to choose NIO is access to filesystem/metadata, paths representing symbolic links, and advanced operations with dedicated APIs. Regardless of which type is used, **a path object is always distinct from creating a resource on disk**.

## 15. Common Mistakes and How to Fix Them

| Mistake | Consequence | How to handle |
| --- | --- | --- |
| Calling `new File("a.txt")` and assuming `a.txt` exists | Read/write fails when the file is missing | Perform an appropriate create or open-for-write operation |
| Relying on `getAbsolutePath()` as proof the file exists | Confuses a name string with filesystem state | Use `exists()`/`isFile()` when immediate info is needed |
| Calling `createNewFile()` on a path missing parent directories | May throw `IOException` | Call `mkdirs()` / `Files.createDirectories(...)` first |
| Using `mkdirs()` to create a text file | Creates a directory instead of a file | Create parent directories first, then create a regular file |
| Ignoring the boolean from `createNewFile()` | Unknown whether the file existed or was newly created | Check `true`/`false` or use `Files.createFile` |
| Using `exists() == true` instead of `isFile()` | Might treat a directory as a file | Check the type or let the read/write API validate |
| Using `exists() == false` then default write | Prone to races and may overwrite another process's file | Use `CREATE_NEW` or atomic creation |
| Using `Files.writeString` without knowing defaults | May truncate old data | Choose `CREATE_NEW`/`APPEND`/`TRUNCATE_EXISTING` as required |
| Assuming `FileInputStream` creates a missing file | Throws an error when opening the file to read | Create the resource first if business logic demands it |
| Assuming `new FileOutputStream` only creates an in-memory object | Can create/truncate the real file upon opening | Manage path and write options explicitly |
| Forgetting to close streams after opening files | Handle and resource leaks | Use try-with-resources |
| Clearing a `File` reference and assuming the file is deleted | The real file still exists | Call `delete()`/`Files.delete(...)` if deletion is needed |
| Using a relative path assuming it is next to source code | Reads/writes the wrong location | Check the working directory, use `Path`/absolute paths when needed |
| Using an existence boolean as a final safety check | Result may be stale due to a race | Perform open/create directly with error handling |
| Not checking exceptions/filesystem permissions | False assumption of write success | Handle `IOException`, verify the operation completed |

## 16. Self-Check Questions

1. **Does `new File("hello.txt")` create an empty file on disk?** No. It creates a path object.
2. **Can `File` point to a directory?** Yes. Use `isDirectory()` to probe the resource type.
3. **If the file does not exist yet, can `getAbsolutePath()` return a path?** Yes. It builds an absolute path form without creating the file.
4. **What does `createNewFile()` return if the file already exists?** Returns `false`, without overwriting content.
5. **How does `Files.createFile(path)` differ when the file already exists?** Usually throws `FileAlreadyExistsException`.
6. **How do `mkdir()` and `mkdirs()` differ?** `mkdir()` creates one directory level; `mkdirs()` attempts to create all necessary parent directories as well.
7. **Why can `new File("a/b/c.txt").createNewFile()` fail?** Because the parent directory `a/b` does not exist yet or is inaccessible.
8. **Can `new FileOutputStream(file)` create a new file?** Yes, when opening a write target with a valid path/permissions; if it already exists, it may truncate it.
9. **Does `new FileInputStream(file)` automatically create a missing file?** No. This is a read operation and may throw `FileNotFoundException`.
10. **Should you check `!exists()` then call `Files.writeString` to ensure no overwrite?** No. There is a race. Use `CREATE_NEW` when create-only is required.
11. **Does garbage collection of `File` delete the real file?** No.
12. **Does creating a temp file with `File.createTempFile(...)` create a physical file?** Yes. This is a factory that performs a creation operation, unlike the `new File(...)` constructor.

## Java 17 API References

- [`java.io.File`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/File.html): constructors, `createNewFile`, `mkdir`, `mkdirs`, `exists`, `delete`.
- [`java.nio.file.Path`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html): path representation and manipulation.
- [`java.nio.file.Files`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): creating/writing/reading/deleting files and directories.
- [`java.nio.file.StandardOpenOption`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardOpenOption.html): `CREATE_NEW`, `CREATE`, `APPEND`, and `TRUNCATE_EXISTING`.
- [`java.io.FileOutputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/FileOutputStream.html): opens and writes a byte stream, may create a file.
- [`java.io.FileInputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/FileInputStream.html): opens and reads a byte stream.
- [`java.io.IOException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/IOException.html): error handling for filesystem operations.

**Remember:** `new File(path)` only tells the JVM **which path is being referred to**. `createNewFile()`, `mkdir()/mkdirs()`, `Files.createFile(...)`, `Files.writeString(...)`, and open-for-write operations are the actions that can **create or modify real resources on the file system**. Choose the right operation depending on whether you need to create a file, create a directory, read only, write new, or overwrite, and always handle I/O errors.