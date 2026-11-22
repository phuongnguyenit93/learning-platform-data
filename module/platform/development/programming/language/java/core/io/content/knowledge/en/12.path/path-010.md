# Path does not guarantee the target exists in Java NIO

`java.nio.file.Path` describes **the location/path of an entry on a file system**, rather than an opened and verified existing file or directory. A program can create a `Path` to a location that has no file yet, has been deleted, lacks access permissions, or points to a file that will be created in the future:

~~~java
Path file = Path.of("data", "today.txt");
~~~

This statement only creates a **path object**. It does not create `today.txt`, does not check access permissions, and does not guarantee that the target entry actually exists. This is the core principle to understand before using `Files.exists`, `Files.readString`, `Files.createFile`, `Path.toRealPath`, or similar methods.

## 1. Lesson objectives

After this lesson, you will be able to:

- Distinguish **Path as a name/location** from a **file-system entry** as the actual accessed object.
- Explain how `Path.of`, `resolve`, `getFileName`, `getParent`, `normalize`, and `toAbsolutePath` operate without guaranteeing target existence.
- Use `Files.exists` and `Files.notExists` without mistaking `false` for a definitive conclusion.
- Know when `Path.toRealPath` or `Files.readAttributes` is needed, and the limitations of a single successful check.
- Perform `Files.readString`, `Files.newInputStream`, `Files.createFile`, `Files.createDirectories`, etc. directly and handle `IOException` appropriately.
- Recognize **TOCTOU** (*time of check to time of use*), symbolic links, concurrent modifications, invalid paths, and differences among file system providers.
- Write tests that do not depend on pre-existing paths on the learner's machine.

## 2. `Path` is an abstraction for a path, not a file handle

`Path` is an **interface** in `java.nio.file`, representing a path managed by a specific `FileSystem`. A path can be relative or absolute, have multiple name components, and be combined, normalized, or compared.

Example:

~~~java
import java.nio.file.Path;

Path a = Path.of("reports", "2026.txt");
Path b = a.getParent();           // reports
Path c = b.resolve("draft.txt");  // reports/draft.txt
Path d = a.toAbsolutePath();
Path e = a.normalize();
~~~

This is a **code snippet** (placed inside a Java method or block). Running these calls successfully **in no way proves** that `reports/2026.txt`, the `reports` directory, or `draft.txt` exists.

Look at the two different layers:

~~~text
Path representation layer:
Path.of / resolve / getParent / normalize / toAbsolutePath
              |
              | create and transform paths
              v
       Path object in JVM
              |
              | pass to an actual operation
              v
File system access layer:
Files.readString / Files.newInputStream / Files.createFile /
Files.readAttributes / Path.toRealPath / Files.delete / ...
              |
              v
  Operates on an existing entry or fails with a cause
~~~

This separation allows a program to plan paths before creating files, such as constructing a `Path` for next month's report file, or computing a destination name prior to calling `Files.move`.

A **syntactically valid `Path`** and an **existing file system entry** are two independent concepts. Conversely, even when a real file exists, the `Path` object does not keep that file in existence: another process can delete or replace that entry after you create the `Path`.

## 3. Java 17+ example: creating a Path to a nonexistent file is completely valid

Create the file **`PathExistenceDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class PathExistenceDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("path-existence-");
        Path target = root.resolve("notes.txt");

        try {
            System.out.println("pathCreated=" + (target != null));
            System.out.println("fileName=" + target.getFileName());
            System.out.println("existsBefore=" + Files.exists(target));
            System.out.println("notExistsBefore=" + Files.notExists(target));

            try {
                Files.readString(target, StandardCharsets.UTF_8);
                System.out.println("unexpected read success");
            } catch (NoSuchFileException exception) {
                System.out.println("readBefore=NoSuchFileException");
            }

            Files.writeString(
                    target,
                    "Java NIO",
                    StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE_NEW,
                    StandardOpenOption.WRITE
            );

            System.out.println("existsAfter=" + Files.exists(target));
            System.out.println(
                    "content=" + Files.readString(target, StandardCharsets.UTF_8));
        } finally {
            Files.deleteIfExists(target);
            Files.deleteIfExists(root);
        }
    }
}
~~~

Compile and run with Java 17+:

~~~bash
javac -encoding UTF-8 PathExistenceDemo.java
java PathExistenceDemo
~~~

**Stdout in a typical file system environment, with no external process interfering in the temporary directory:**

~~~text
pathCreated=true
fileName=notes.txt
existsBefore=false
notExistsBefore=true
readBefore=NoSuchFileException
existsAfter=true
content=Java NIO
~~~

### Step-by-step walkthrough

1. `Files.createTempDirectory` actually creates a **temporary directory**; its specific name is chosen by Java and omitted from stdout.
2. `root.resolve("notes.txt")` only creates the `Path` for the child file. That file **has not been created yet**.
3. `target != null` merely confirms the Java variable holds an object reference; it says nothing about the file system.
4. `Files.exists(target)` is initially `false`, and `Files.notExists(target)` is `true` because the path was created inside a fresh temporary directory with no file yet.
5. `Files.readString` must open and read the actual file. Since the file does not exist yet, the default file system typically throws `NoSuchFileException`.
6. `Files.writeString` with `CREATE_NEW` creates a new file; this option avoids silently overwriting an existing file. If a collision occurs, the operation fails instead of writing over the old file.
7. At this point `Files.exists` returns `true` and `Files.readString` reads back the written text.
8. `finally` deletes the temporary resources after the demo. If cleanup encounters an error, `IOException` can still be thrown — this is appropriate behavior when resources cannot be cleaned up.

**Lesson:** `target` is the exact same `Path` variable both **before the file existed** and **after the file was created**. There is no event where "Path becomes more valid" when the file appears; only the file system state changed.

## 4. `Path` transformations do not verify the target

| API | What it primarily does | Guarantees target exists? |
| --- | --- | --- |
| `Path.of("a", "b")` | Parses path name parts per provider | No |
| `path.resolve("child")` | Appends child path or handles a given path | No |
| `path.resolveSibling("other")` | Creates a sibling replacement path relative to the original path | No |
| `path.getFileName()` | Retrieves the last name component (may be `null` for root) | No |
| `path.getParent()` | Retrieves parent from path structure (may be `null`) | No |
| `path.normalize()` | Removes redundant name components per lexical rules | No |
| `path.toAbsolutePath()` | Converts to absolute path form per provider | No |
| `path.toUri()` | URI representation for the path per provider | Should not be treated as an existence check |
| `path.toFile()` | Converts to `java.io.File` when supported by provider | No |
| `Files.exists(path)` | Attempts to check existence at call time | Does not guarantee **future** existence |
| `path.toRealPath()` | Accesses file system for real path, handling links per options | Usually requires entry to exist **at call time**; no guarantee afterward |

### Runnable example: `resolve` and `normalize` still do not "touch" files

Create **`PathLexicalDemo.java`**:

~~~java
import java.nio.file.Path;

public class PathLexicalDemo {
    public static void main(String[] args) {
        Path relative = Path.of("ghost")
                .resolve("draft")
                .resolve("..")
                .resolve("report.txt");

        Path normalized = relative.normalize();

        System.out.println("relative=" + !relative.isAbsolute());
        System.out.println("lastName=" + normalized.getFileName());
        System.out.println("changedByNormalize="
                + !relative.equals(normalized));
        System.out.println("absolute=" + normalized.toAbsolutePath().isAbsolute());
    }
}
~~~

Compile/run:

~~~bash
javac PathLexicalDemo.java
java PathLexicalDemo
~~~

Stdout:

~~~text
relative=true
lastName=report.txt
changedByNormalize=true
absolute=true
~~~

`ghost/draft/../report.txt` is simplified to `ghost/report.txt` by lexical rules. The `ghost` directory and `report.txt` file do not need to exist for the program to run.

**Warning:** `normalize()` is not `toRealPath()`. It does not resolve symbolic links, does not verify files, and does not necessarily preserve path meaning when a removed component is a symbolic link. For instance, `link/../file` can have a different meaning after dropping `link/..` if `link` points to another location. Do not use `normalize()` as a way to confirm a file truly resides inside a trusted directory.

## 5. `Files.exists()` and `Files.notExists()`: different from logical negation

A dangerous misconception is:

~~~java
if (!Files.exists(path)) {
    // Assuming the file DEFINITELY does not exist.
}
~~~

In Java NIO, `Files.exists(path)` can return `false` both when the file truly does not exist **and** when its status cannot be determined. `Files.notExists(path)` can also return `false` if status cannot be determined.

| `Files.exists(path)` | `Files.notExists(path)` | Interpretation in a steady state |
| --- | --- | --- |
| `true` | `false` | Confirmed that the entry exists at check time |
| `false` | `true` | Confirmed that the entry does not exist at check time |
| `false` | `false` | Unable to determine whether the entry exists |

Do not write `Files.notExists(path) == !Files.exists(path)` as an invariant. Moreover, two calls at two different points in time may observe different states if concurrent modifications occur. Existence-checking APIs **do not hold locks or reserve permissions** to guarantee the next operation.

### `isRegularFile` and `isDirectory` also do not guarantee a specific cause for `false`

~~~java
boolean regular = Files.isRegularFile(path);
boolean directory = Files.isDirectory(path);
~~~

A `false` value from `isRegularFile` may occur simply because the target is a directory, does not exist, or attributes cannot be determined. Likewise, `isDirectory == false` does not prove the target is a regular file.

If business logic needs detailed information or requires the cause of an access failure, you can use:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;

public final class FileTypeProbe {
    private FileTypeProbe() {}

    public static BasicFileAttributes inspect(Path path) throws IOException {
        return Files.readAttributes(path, BasicFileAttributes.class);
    }
}
~~~

This is a compilable utility class without `main`. The `readAttributes` method may throw `NoSuchFileException`, `AccessDeniedException`, or another `IOException`, depending on the file system provider. Even so, the attribute result remains merely a **snapshot at a single point in time**, with no guarantee the file is not replaced afterward.

## 6. How does `toRealPath()` differ from `toAbsolutePath()`?

These two methods look similar but have different semantics:

**`path.toAbsolutePath()`**

- Converts a relative `Path` to absolute form per file system/provider.
- **Do not treat the result as certification that the file currently exists**.
- The path may contain `.` and `..` components; `toAbsolutePath()` by itself is not full canonicalization.
- Depending on the environment, obtaining the absolute path may rely on the working directory/provider characteristics; do not infer that it read any metadata of the target.

**`path.toRealPath()`**

- Returns the real path according to the file system.
- Typically normalizes the absolute path, resolves symbolic links, and **checks required existence/accessibility** at call time.
- May throw `IOException`/`NoSuchFileException` when the entry does not exist or encounters an obstacle.
- Can accept `LinkOption.NOFOLLOW_LINKS` to affect how symbolic links are handled. This option does not turn a nonexistent path into an existing one.

### Runnable demo: `toRealPath()` requires a real entry

Create **`RealPathDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;

public class RealPathDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("real-path-");
        Path missing = root.resolve("not-yet.txt");

        try {
            System.out.println("absoluteCanBeBuilt="
                    + missing.toAbsolutePath().isAbsolute());

            try {
                missing.toRealPath();
                System.out.println("unexpected success");
            } catch (NoSuchFileException exception) {
                System.out.println("realBefore=NoSuchFileException");
            }

            Files.createFile(missing);
            Path real = missing.toRealPath();

            System.out.println("realAfterExists=" + Files.exists(real));
        } finally {
            Files.deleteIfExists(missing);
            Files.deleteIfExists(root);
        }
    }
}
~~~

Compile and run:

~~~bash
javac RealPathDemo.java
java RealPathDemo
~~~

Stdout in a typical default file system environment without concurrent modifications:

~~~text
absoluteCanBeBuilt=true
realBefore=NoSuchFileException
realAfterExists=true
~~~

`toAbsolutePath()` succeeds in producing an absolute path before the file appears. `toRealPath()` cannot find the entry on the first call; after `Files.createFile`, the call succeeds.

**Do not misuse `toRealPath()`:** If you are computing the path for a file *about to be created*, calling `toRealPath()` on the **target file** is usually the wrong step because the target does not exist yet. You may need to canonicalize an **already existing parent directory** and apply an explicit file-creation policy, while still handling races/symlinks. Furthermore, `toRealPath()` succeeding today does not supply a file handle holding that entry fixed for subsequent operations.

## 7. Check then act: the TOCTOU problem

Look at this pattern:

~~~java
if (Files.exists(target)) {
    String text = Files.readString(target);
}
~~~

Between `exists` and `readString`, another process/thread can delete the file, change permissions, move the path, or replace a symbolic link. Then `readString` can still throw `IOException`.

Similarly, the following snippet **is not safe for guaranteeing creation of a new file**:

~~~java
if (!Files.exists(target)) {
    Files.writeString(target, "data");
}
~~~

`Files.writeString` by default may create a file or truncate an existing file. In the window between checking and writing, another party can create a file at the target; as a result, their file gets overwritten. In addition, `Files.exists()==false` does not always assert "does not exist".

### Choose conditional operations right at the I/O point

If the goal is to create a **new file without overwriting**, write:

~~~java
Files.writeString(
        target,
        "data",
        java.nio.charset.StandardCharsets.UTF_8,
        java.nio.file.StandardOpenOption.CREATE_NEW,
        java.nio.file.StandardOpenOption.WRITE
);
~~~

`CREATE_NEW` requires checking "file does not exist" and creating the file **under an atomic contract relative to other file system operations**. If the file exists at execution time, the operation fails (typically with `FileAlreadyExistsException`). This is the key difference compared to the `exists → write` sequence.

If the goal is to read a file that must exist, **simply open and read it**:

~~~java
String text = Files.readString(
        target, java.nio.charset.StandardCharsets.UTF_8);
~~~

Catch/propagate `NoSuchFileException`, `AccessDeniedException`, and other `IOException`s from the operation itself, instead of using `Files.exists` as a "guarantee certificate".

If the goal is a directory that **must exist after the operation**, use `Files.createDirectories(dir)` and handle `IOException` if it cannot be created or the target is not a directory. If the goal is deleting a file **if present**, `Files.deleteIfExists(path)` can return `false` when absent while still throwing `IOException` for other deletion errors.

**Rule:** Status checks are useful for user interfaces or diagnostic strategies, but actual I/O operations must always have an error-handling path.

## 8. `Path` does not mean access permission exists

A file may exist yet remain unreadable because:

- File-system permissions, ACLs, sandboxes, or OS policies.
- The entry is in use/locked depending on the system and sharing mode.
- The entry was modified/deleted/moved as the operation began.
- The file system is unavailable, a network drive disconnected, or the provider failed.
- The target is a directory when the API expects a file, or vice versa.
- A symbolic link is dangling or leads to an inaccessible target.

`Files.isReadable(path)` / `Files.isWritable(path)` return booleans reflecting capability checks at that instant; they **do not guarantee** the subsequent open/write call will succeed. A `Path` may also point to a file that currently does not exist but will be created by another task in the future.

When you need to distinguish causes, prefer **exceptions from the operation**:

| API | On success | Some error cases |
| --- | --- | --- |
| `Files.readString(path, UTF_8)` | Reads text from file | `NoSuchFileException`, `AccessDeniedException`, `IOException`, or decoding errors per contract |
| `Files.newInputStream(path)` | Opens byte input stream | `IOException` when opening fails / read error |
| `Files.createFile(path)` | Creates new file | `FileAlreadyExistsException`, `IOException` |
| `Files.createDirectories(path)` | Ensures directory chain is created/exists | `IOException` if creation fails or an entry is not a directory |
| `Files.delete(path)` | Deletes file/entry | `NoSuchFileException`, `DirectoryNotEmptyException` (provider-dependent), `IOException` |
| `Files.readAttributes(path, BasicFileAttributes.class)` | Reads attributes at query time | `IOException` when query fails |
| `path.toRealPath()` | Obtains current real path | `IOException` when unable to locate/resolve |

Specific exceptions of several APIs are documented as *optional specific exceptions* in the Java API; a provider may throw a general `IOException`. Do not rely on English error messages or assume every provider/OS throws the exact specific subclass.

## 9. Symbolic links: path existence and link target existence are two things

Suppose there is a symbolic link `shortcut` pointing to `archive/missing.txt`, yet the target file is gone. Then:

- The **symbolic link** entry itself may still exist on the file system.
- `Files.exists(shortcut)` by default **follows symbolic links** (when supported by API/provider), so it may return `false` because the target does not exist.
- `Files.exists(shortcut, LinkOption.NOFOLLOW_LINKS)` inspects the link itself instead of following to the target, so it may return `true` while the link exists.
- `Path.toRealPath()` by default resolves the link and will fail if the target cannot be resolved; `NOFOLLOW_LINKS` alters link handling per contract.
- `Path.normalize()` completely **ignores where that link points**.

Do not teach `Files.exists()==false` as "there is no file-system entry whatsoever at this location". It may merely indicate that the target *after following the link* does not exist or cannot be determined.

Do not rely on creating symbolic links in unit tests across all OSes: Windows or CI environments may require special privileges/modes. For critical logic, write per-provider integration tests.

## 10. Path traversal, trusted root directories, and limits of `normalize()`

An API receiving an external filename often builds:

~~~java
Path base = Path.of("uploads").toAbsolutePath().normalize();
Path requested = base.resolve(userName).normalize();
~~~

This is a **code snippet** assuming an existing `String` variable `userName`. It computes a working path without opening files. Even if you add:

~~~java
if (!requested.startsWith(base)) {
    throw new IllegalArgumentException("Path escapes base");
}
~~~

this check only defends at the **lexical level** against components like `..` (and you must also check for absolute input paths). It does not guarantee the real file lies under `base`, because symlinks, mount points, hard links, and race conditions can alter the real location.

For untrusted data:

1. Clearly define the allowed set of filenames (e.g., a single filename only, disallowing separators if business logic needs no subdirectories).
2. Disallow user-supplied absolute paths/`..` outside the contract scope.
3. Understand that `normalize` does not query or lock the file system; it does not validate symbolic links.
4. Apply appropriate access-permission boundaries and handle directories/entries being swapped during opening.
5. For strong protection against symlink traversal, explore `SecureDirectoryStream` when supported by the provider and strategies operating relative to a directory handle, rather than only comparing `Path` strings.

**Do not call `toRealPath()` once and treat it as completely eliminating TOCTOU**. Between checking the real path and opening the entry, another actor can still modify the directory tree.

## 11. Relative, absolute, and working with multiple file systems

### Relative `Path`

~~~java
Path path = Path.of("notes.txt");
~~~

It may be interpreted based on the working directory (or provider rules). Running the application from an IDE, terminal, or scheduler can cause **the exact same string `notes.txt`** to point to different absolute locations.

If a path belongs to critical configuration, establish the base directory explicitly:

~~~java
Path base = Path.of("/app/data"); // Illustrates a path specific to Unix-like environments.
Path target = base.resolve("notes.txt");
~~~

On Windows or another provider, `/app/data` has its own semantics. Do not hard-code OS paths into cross-platform libraries; it is better to pass `Path base` from configuration/constructor.

### `Path` from other providers

`Path` is an interface implemented by a file system provider. Beyond local disk, there can be a ZIP file system or additional installed providers. Points to remember:

- Not every provider supports the same attributes, symlinks, atomic moves, permissions, or conversion to `File`.
- `Files.exists`/`Files.readAttributes`/`toRealPath` share general semantics, though certain error reporting/capabilities depend on the provider.
- `Path.toFile()` may throw `UnsupportedOperationException` if the provider is not associated with the default file system.
- `Path.equals` is primarily a representation/provider comparison per contract, **not a check for whether two names point to the same physical inode/file**.
- To ask whether two paths point to the same real file at a point in time, use `Files.isSameFile(pathA, pathB)` when appropriate; note that this API also has optimization rules and must not be used in place of an existence check in all scenarios.

## 12. How does it differ from `java.io.File`?

The two types share an important similarity:

~~~java
File f = new File("missing.txt");
Path p = Path.of("missing.txt");
~~~

Both `new File(...)` and `Path.of(...)` can create objects pointing to a **nonexistent** target. Converting:

~~~java
Path fromFile = f.toPath();
File fromPath = p.toFile(); // If supported by provider.
~~~

also **does not create an entry on disk** or verify that it already exists.

The difference is that NIO enables operations via `Files` with richer capabilities and error reporting:

| Need | Legacy approach | NIO is usually more suitable |
| --- | --- | --- |
| Path representation | `File` | `Path` |
| Existence check | `File.exists()` | `Files.exists(path)` (still has boolean limits) |
| Create new file | `File.createNewFile()` | `Files.createFile(path)` |
| Create multi-level directories | `File.mkdirs()` | `Files.createDirectories(path)` |
| Delete file | `File.delete()` returns boolean | `Files.delete(path)` throws on error |
| Move | `File.renameTo(...)` returns boolean | `Files.move(...)` with options |
| Read attributes | `File` has simple attributes | `Files.readAttributes`/attribute views |

`Path` itself does not open/create/delete files. **`Files` is the utility set operating on Path**. Even so, even when `Files.exists` returns true, the application must still handle errors in the subsequent operation.

## 13. Designing APIs that accept `Path`: do not implicitly require the entry to exist

Functions accepting `Path` can have very different contracts:

~~~java
// Read content: entry must be readable at operation time.
static String load(Path path) throws IOException {
    return Files.readString(path, StandardCharsets.UTF_8);
}

// Create new: entry MUST NOT exist at creation time.
static Path create(Path path) throws IOException {
    return Files.createFile(path);
}

// Compute planned target name only; does not need to exist yet.
static Path plannedOutput(Path folder, String fileName) {
    return folder.resolve(fileName);
}
~~~

The snippets above are **code fragments** to place inside a Java class, importing `Path`, `Files`, `IOException`, and `StandardCharsets`. Do not impose a single precondition "`Path` must always exist" on all three: `create` **requires** the target to be absent, while `plannedOutput` only computes a name.

Document clearly in JavaDoc/API:

- Is the Path permitted to point to a nonexistent target?
- Are relative paths allowed, and where does the base directory come from?
- Are symbolic links followed?
- If the file already exists, overwrite, append, or report an error?
- Does the caller or callee own streams/channels after opening?
- Under what conditions is `IOException` reported, and is distinguishing `NoSuchFileException` needed?

### Example creating a file from a pre-planned Path

Create the file **`PlannedFileDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class PlannedFileDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("planned-file-");
        Path folder = root.resolve("reports");
        Path output = folder.resolve("result.txt");

        try {
            System.out.println("folderExistsBefore=" + Files.exists(folder));
            System.out.println("outputExistsBefore=" + Files.exists(output));

            Files.createDirectories(folder);
            Files.writeString(
                    output,
                    "done",
                    StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE_NEW,
                    StandardOpenOption.WRITE
            );

            System.out.println("folderExistsAfter=" + Files.isDirectory(folder));
            System.out.println("outputExistsAfter=" + Files.isRegularFile(output));
            System.out.println("text=" + Files.readString(
                    output, StandardCharsets.UTF_8));
        } finally {
            Files.deleteIfExists(output);
            Files.deleteIfExists(folder);
            Files.deleteIfExists(root);
        }
    }
}
~~~

Run:

~~~bash
javac PlannedFileDemo.java
java PlannedFileDemo
~~~

Stdout in a normal environment without concurrent activity in the temporary directory:

~~~text
folderExistsBefore=false
outputExistsBefore=false
folderExistsAfter=true
outputExistsAfter=true
text=done
~~~

This example illustrates a practical scenario: the code knows the file and directory paths to create **before they exist**; then it uses two explicit operations to create them. Do not add `toRealPath()` on `output` before creating it just to "validate the path".

## 14. Common misconceptions

**Misconception 1 — Creating a `Path` also creates the file.**  
False. `Path.of` creates a path-representation object; to create files/directories, use `Files.createFile`, `createDirectories`, or open a stream with appropriate open options.

**Misconception 2 — `toAbsolutePath` proves the file actually exists.**  
False. An absolute path can still point to a nonexistent entry.

**Misconception 3 — `normalize` resolves symlinks and confirms the real location.**  
False. `normalize` processes name components lexically; `toRealPath` accesses the file system, and its result only reflects a single point in time.

**Misconception 4 — `Files.exists(path)==false` always means the entry is definitely absent.**  
False. There are cases where status cannot be determined. `Files.notExists` is not simply the negation of `Files.exists`.

**Misconception 5 — `Files.isReadable(path)==true` guarantees `readString` will succeed.**  
False. State, permissions, or the object at the target may change; the operation may also fail for other reasons.

**Misconception 6 — Checking `exists` then calling `writeString` is safe file creation.**  
False. There is a race condition, and default `writeString` can overwrite an existing target; use `CREATE_NEW` if business logic requires creating without overwriting.

**Misconception 7 — `NoSuchFileException` means the `Path` object is invalid.**  
False. The `Path` may be syntactically valid while the file simply does not exist at operation time. `InvalidPathException` is what relates to a path string that cannot be parsed by the provider; that is a different issue.

**Misconception 8 — An absolute path means a fixed path that never changes targets.**  
False. The entry at the same filename can be deleted and replaced. A `Path` does not hold a handle/lock to an immutable object.

**Misconception 9 — Checking `path.normalize().startsWith(base)` makes path traversal impossible.**  
False. It helps with lexical checking, but does not suffice against symbolic links and TOCTOU in a directory tree controlled by others.

**Misconception 10 — `Path.toFile()` always works on every provider.**  
False. Providers outside the default file system may not support conversion to `java.io.File`.

## 15. Checklist when reviewing programs that use Path

- [ ] Are we **creating/describing a path** or actually **accessing the file system**?
- [ ] Does anything assume `Path.of`/`resolve`/`toAbsolutePath` guarantees target existence?
- [ ] If reading a file, does the code perform the read directly and handle `IOException` at that call?
- [ ] If creating a new file, does it use `CREATE_NEW` or `Files.createFile` to prevent overwriting?
- [ ] If a target directory is required, is it created/validated per policy with `createDirectories` or an equivalent API?
- [ ] Does the code distinguish `Files.exists` false from `Files.notExists` true, as well as the unknown case?
- [ ] Does it avoid checking `exists` and then assuming the next operation cannot fail?
- [ ] If using `toRealPath()`, is the target expected to exist and how are symbolic links handled?
- [ ] Is untrusted input validated: absolute paths, `..`, symlinks, permitted directories?
- [ ] Are default/other file-system providers, relative paths, and base directories explicitly documented?
- [ ] Do unit tests use temporary directories so they do not depend on pre-existing files on the learner's machine?
- [ ] Are resources cleaned up properly without deleting paths outside the test area?

## 16. Self-check quiz

**Question 1.** `Path p = Path.of("missing.txt");` runs without exception. Is the file guaranteed to exist?  
**Answer:** No. It only creates a `Path` representing the name `missing.txt`.

**Question 2.** `p.toAbsolutePath()` returns an absolute path. What does this prove about existence?  
**Answer:** It proves nothing; it only converts the representation to an absolute path.

**Question 3.** When can both `Files.exists` and `Files.notExists` return `false`?  
**Answer:** When existence status cannot be determined according to file system query rules.

**Question 4.** Which method typically checks existence and returns the real path at call time?  
**Answer:** `toRealPath()`, which can throw `IOException` and handles symbolic links per options.

**Question 5.** Why shouldn't you write `if (!Files.exists(p)) Files.writeString(p, text);` if you do not want to overwrite?  
**Answer:** Because of race conditions and because default `writeString` can create/truncate an existing file; use `CREATE_NEW`.

**Question 6.** When a method is passed a `Path` for an output file that does not exist yet, should it call `toRealPath()` first?  
**Answer:** Not required and usually inappropriate. Validate/authorize the parent/target per policy, then create the file with an explicit operation.

**Question 7.** Is `p.normalize()` enough to prevent accessing files outside an allowed directory?  
**Answer:** No. Symbolic links, race conditions, and access permissions must still be addressed.

**Question 8.** When `Files.readString(path)` throws `NoSuchFileException`, is the `Path` "broken"?  
**Answer:** No. The requested file did not exist at operation time (or the provider reported a corresponding missing-entry condition), while the `Path` representation itself may be completely valid.

**Remember:** **`Path` is a path, not an existing file.** Creating or transforming a `Path` object does not create files and does not keep the underlying entry alive. To know state, you must query the file system, and even a successful check is only valid at one instant. When you need reliable business outcomes, use `Files` operations directly with appropriate options and handle `IOException`.

## Java SE 17 references

- [Path — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html)
- [Files — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
- [StandardOpenOption — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardOpenOption.html)
- [LinkOption — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/LinkOption.html)