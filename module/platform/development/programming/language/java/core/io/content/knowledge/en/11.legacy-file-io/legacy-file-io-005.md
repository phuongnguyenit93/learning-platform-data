# Checking Existence, File Type, Size, and Permissions with `java.io.File`

`java.io.File` is Java's legacy API for **representing a pathname** of a file or directory and querying certain file-system-related attributes. It does not mean an open file, nor does it prove an object actually exists just because you called `new File(...)`.

Common questions are:

- Does this path exist?
- Is it a **regular file** or a **directory**?
- How many **bytes** is the file?
- Can the current Java process **read**, **write**, or **execute** the path?
- Once checked, what guarantees the next I/O operation will succeed?

This lesson focuses on `File.exists()`, `isFile()`, `isDirectory()`, `length()`, `canRead()`, `canWrite()`, `canExecute()`, and their important limitations; it also points out when to switch to `java.nio.file.Path`/`Files` for more accurate metadata retrieval and error handling.

## 1. `File` Is a Path Representation, Not a File Handle

```java
File file = new File("data/report.txt");
```

This is an **illustrative snippet** (requiring `import java.io.File;`). The constructor takes a path string and creates a `File` object. It **does not automatically create** `data/report.txt`, does not open a read/write stream, and does not guarantee the path is valid or currently exists.

Distinguish:

| Object/API | Main role | Opens I/O resource immediately upon creation? |
| --- | --- | --- |
| `new File("report.txt")` | Represents a pathname, queries attributes/paths | No |
| `Path.of("report.txt")` | Path representation per NIO.2 API | No |
| `new FileInputStream(file)` | Opens file to read bytes | Yes, may throw `FileNotFoundException` |
| `new FileOutputStream(file)` | Opens file to write bytes; may create/overwrite by default | Yes, may throw errors |
| `Files.newInputStream(path)` | Opens a byte stream with corresponding options | Yes, may throw `IOException` |
| `Files.readAttributes(...)` | Queries attributes per NIO.2 API | Performs a filesystem query operation, may throw `IOException` |

Relative paths like `"data/report.txt"` are resolved against the Java process's **working directory**, not automatically against the directory containing `.java` or `.class` files. `/` and `\` are separators with platform-dependent details; using `Path.of("data", "report.txt")` or `new File(parent, child)` makes path representation clearer.

`getName()`, `getParent()`, `getPath()` mainly process path information; they do **not** confirm the file exists. `getAbsolutePath()` produces an absolute path without automatically resolving symbolic links or checking the file. `getCanonicalPath()` may need to access the file system and throw `IOException`; it should not be equated with `getAbsolutePath()`.

## 2. Core Checks of `java.io.File`

| Method | Value and meaning | Important limitation |
| --- | --- | --- |
| `exists()` | `true` if the object the path points to exists according to the query | `false` gives no clear reason; could be missing file or undetermined |
| `isFile()` | `true` when it is a **regular file** as recognized by the file system | `false` if directory, non-existent, or another type |
| `isDirectory()` | `true` when it is a directory | `false` does not necessarily mean a regular file |
| `length()` | File length in **bytes**, type `long` | For non-existent paths may return `0`; for directories the value is **unspecified** |
| `canRead()` | Checks read permission per the mechanism Java/OS provides | An advisory signal; does not guarantee a subsequent read succeeds |
| `canWrite()` | Checks write permission | Does not replace an actual write and exception handling |
| `canExecute()` | Checks execute permission | Depends on platform, policy/permissions; does not guarantee execution succeeds |
| `isHidden()` | Checks hidden file attribute per platform convention | Should not rely solely on dot prefixes across all operating systems |

**Important:** `isFile()` and `isDirectory()` are not negations of each other. `!file.isFile()` **does not mean** `file.isDirectory()`: the file could be absent, a broken symbolic link, a device, a special socket, or unqueryable. Similarly, `exists() == true` does not necessarily mean a **regular** file.

### Example 1 — File, Directory, and Non-Existent Path

The following Java 17+ program creates a temporary directory and a file with known ASCII data, independent of paths or files prepared by the learner.

```java
// FileTypeDemo.java
import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class FileTypeDemo {
    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("file-type-");
        Path text = root.resolve("notes.txt");
        Path folder = root.resolve("folder");
        Path missing = root.resolve("missing.txt");

        try {
            Files.writeString(text, "ABC", StandardCharsets.UTF_8);
            Files.createDirectory(folder);

            File file = text.toFile();
            File directory = folder.toFile();
            File absent = missing.toFile();

            System.out.println("file.exists=" + file.exists());
            System.out.println("file.isFile=" + file.isFile());
            System.out.println("file.isDirectory=" + file.isDirectory());
            System.out.println("file.length=" + file.length());

            System.out.println("dir.exists=" + directory.exists());
            System.out.println("dir.isFile=" + directory.isFile());
            System.out.println("dir.isDirectory=" + directory.isDirectory());

            System.out.println("missing.exists=" + absent.exists());
            System.out.println("missing.isFile=" + absent.isFile());
            System.out.println("missing.isDirectory=" + absent.isDirectory());
            System.out.println("missing.length=" + absent.length());
        } finally {
            Files.deleteIfExists(text);
            Files.deleteIfExists(folder);
            Files.deleteIfExists(root);
        }
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 FileTypeDemo.java
java FileTypeDemo
```

Output when file/directory creation operations succeed:

```text
file.exists=true
file.isFile=true
file.isDirectory=false
file.length=3
dir.exists=true
dir.isFile=false
dir.isDirectory=true
missing.exists=false
missing.isFile=false
missing.isDirectory=false
missing.length=0
```

`missing.length=0` is why you cannot use `length()==0` to assert "this is an empty file": a non-existent path can also yield `0`. A **truly empty** file also has `length()==0`. Checking `exists()` and `isFile()` can help express your intent, but in code requiring accurate error handling you should still perform the I/O operation and catch exceptions.

`length()` on a **directory** should not be used to ask "how much data does the directory hold" or "how many child files are there." The return value for a directory is unspecified. To list child files, use directory listing APIs; to measure the size of an entire directory tree, you must traverse the entries inside under an explicit policy.

## 3. `length()` Measures Bytes, Not Characters

A text file containing Unicode characters can have a byte count different from the number of `char`s and Unicode code points. For example, in UTF-8:

- The letter `A` takes 1 byte.
- The emoji `😀` takes 4 UTF-8 bytes.
- The string `"A😀"` has 5 bytes, while `String.length()` returns 3 UTF-16 code units and the code point count is 2.

### Example 2 — Comparing File Size and String Length

```java
// FileByteLengthDemo.java
import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class FileByteLengthDemo {
    public static void main(String[] args) throws Exception {
        Path path = Files.createTempFile("byte-size-", ".txt");
        String text = "A😀";

        try {
            Files.writeString(path, text, StandardCharsets.UTF_8);

            File file = path.toFile();
            System.out.println("fileBytes=" + file.length());
            System.out.println("stringChars=" + text.length());
            System.out.println("codePoints=" +
                    text.codePointCount(0, text.length()));
            System.out.println("nioBytes=" + Files.size(path));
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 FileByteLengthDemo.java
java FileByteLengthDemo
```

Output:

```text
fileBytes=5
stringChars=3
codePoints=2
nioBytes=5
```

The actual byte count depends on the **charset** used when writing. If the file was written with a different encoding, `length()` still returns the stored byte count (when retrievable), without decoding to count characters.

`File.length()` returns `long`; do not cast to `int` when a file may exceed the `int` limit. Some file attributes can change after querying, especially when another process writes or deletes the file. Do not treat `length()` as a guarantee that data will not change during reading.

### Large Files and Unflushed Data

If writing through `BufferedOutputStream` or `BufferedWriter`, data may still sit in the application-layer buffer not yet transferred to the file. When you need to observe recently written content, `flush()` or close the appropriate writer before checking; however, `flush()` **does not itself guarantee data is durably persisted to hardware**. Even after flushing, another process can still modify the file.

## 4. Read, Write, Execute Permissions: Three Different Questions

```java
File file = new File("data/report.txt");
boolean readable = file.canRead();
boolean writable = file.canWrite();
boolean executable = file.canExecute();
```

This is an **illustrative snippet**, not a standalone program.

The methods above check the status reported by the platform for the running process. Practical meaning depends on the operating system, file system, user privileges, ACLs, remote-mounted volumes, sandbox policies, parent directory permissions, and entry state.

| Check | Intended question | What **must not be inferred** |
| --- | --- | --- |
| `canRead()` | Is the path currently readable per information provided by the platform? | That a subsequent open/read will definitely succeed |
| `canWrite()` | Is the path currently writable per information provided by the platform? | That writing will definitely succeed; sufficient disk space; file can be overwritten |
| `canExecute()` | Is execute permission granted per platform model? | That the file is a valid program or `ProcessBuilder` will run it |
| `exists()` | Does the queried object exist? | That the caller has permission to read content or open the file |

A file can exist yet `canRead()==false`; a directory can exist yet not be listable; a file can be writable at check time and have permissions changed right afterward. On some platforms or when running under a privileged account, permission check results may differ from expectations based on POSIX bits. Do not write a rigid test asserting that any arbitrary temporary file necessarily has `canExecute()==false` across all operating systems.

For directories, "execute" permission on POSIX typically relates to the ability to **traverse/search** the directory, not "run the directory like an application." The ability to create a new file also depends on the containing directory's permissions, not only `canWrite()` on a non-existent file.

**Do not use these checks as a security authorization mechanism for multi-user systems.** A server needs independent authentication/authorization mechanisms and must still handle actual access errors during operations.

### Example 3 — Observing Permissions Without Assuming a Single Platform Result

```java
// FilePermissionsDemo.java
import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class FilePermissionsDemo {
    public static void main(String[] args) throws Exception {
        Path path = Files.createTempFile("permissions-", ".txt");

        try {
            Files.writeString(path, "data", StandardCharsets.UTF_8);
            File file = path.toFile();

            System.out.println("exists=" + file.exists());
            System.out.println("regularFile=" + file.isFile());

            System.out.println("canRead=" + file.canRead());
            System.out.println("canWrite=" + file.canWrite());
            System.out.println("canExecute=" + file.canExecute());

            System.out.println("nioReadable=" + Files.isReadable(path));
            System.out.println("nioWritable=" + Files.isWritable(path));
            System.out.println("nioExecutable=" + Files.isExecutable(path));
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
```

Run:

```bash
javac FilePermissionsDemo.java
java FilePermissionsDemo
```

The first two lines are normally:

```text
exists=true
regularFile=true
```

The next six lines print `true` or `false` **depending on the runtime environment**, so there is no single standard stdout for the entire program. You may observe `File` and `Files` methods giving similar results on local files, but that is not a universal guarantee across every provider or runtime state.

Setting permissions with `setReadable()`, `setWritable()`, `setExecutable()`, or `setReadOnly()` has many platform-dependent conditions; the return value only indicates whether the request succeeded per the API contract, and does not turn permission checks into a complete security mechanism. For POSIX permissions, consider `Files.getPosixFilePermissions()`/`setPosixFilePermissions()` on supporting providers; Windows and other systems have different permission models. Calls unsupported by a provider may throw `UnsupportedOperationException`.

## 5. Four Commonly Confused States

Do not treat `if (file.exists())` as synonymous with any of the following four claims:

1. **A file system entry exists:** `exists()` can return `true` for a file, a directory, or another type of entry.
2. **It is a regular file:** `isFile()` is what checks this type; a path pointing to a directory must return `false`.
3. **It has data:** a regular file can be **empty**, `length()==0`, and still exist completely validly.
4. **The desired operation can be performed:** reading/writing/deleting/renaming also depends on permissions, current state, parent directory permissions, file locks, provider, and other constraints.

Examples of states:

| Case | `exists()` | `isFile()` | `isDirectory()` | `length()` | Notes |
| --- | --- | --- | --- | --- | --- |
| Regular file, with content | Usually `true` | `true` | `false` | Byte count if determinable | Read/write can still fail |
| Regular file, empty | `true` | `true` | `false` | `0` | Valid empty file |
| Directory | `true` | `false` | `true` | **Unspecified by contract** | Do not use `length()` to count child files |
| Non-existent path | `false` | `false` | `false` | `0` per `File.length()` behavior when file does not exist | Cannot distinguish from an empty file using `length()` alone |
| Unqueryable path | May be `false` | May be `false` | May be `false` | Unreliable for inferring type | Requires actual operation or exception-throwing API |
| Symbolic link pointing to regular file | Usually evaluates **link target** | May be `true` | Usually `false` | Usually per target | NIO.2 allows choosing not to follow links |

The cases in the table describe **typical** situations, without guaranteeing results will not change between calls or that every provider supports the same entry types.

## 6. Symbolic Links: A "Path" Can Point to Another Object

A symbolic link is a file system entry containing a reference to another path. Therefore you must ask clearly: do you want to check the **link** or the **target of the link**?

Conceptual example:

```text
notes-link.txt  -->  documents/notes.txt
       ^                    ^
       |                    |
     link                target
```

- If the target exists and is a regular file, common `File` queries usually report based on the target.
- If the target is deleted, the link becomes a **broken/dangling symbolic link**; `File.exists()` may return `false` even though **the link itself still exists**.
- If you need to manage the link itself (checking for broken links, deleting the link, inspecting type without following the link), use `Path` and `Files` with `LinkOption.NOFOLLOW_LINKS` on supporting APIs.

```java
Path path = Path.of("notes-link.txt");

// Illustrative code: requires importing java.nio.file.Files,
// java.nio.file.Path, and java.nio.file.LinkOption.
boolean targetExists = Files.exists(path);
boolean linkItselfExists =
        Files.exists(path, LinkOption.NOFOLLOW_LINKS);
boolean isLink = Files.isSymbolicLink(path);
```

`Files.exists(path)` follows links by default per API choice; `Files.exists(path, NOFOLLOW_LINKS)` asks about the **link entry** (if determinable); `Files.isSymbolicLink(path)` identifies the entry type. For broken symbolic links, this distinguishes a missing target from a still-existing link. On some platforms, creating symbolic links requires special privileges or is unsupported by the provider; do not force a symbolic link test to pass on every machine.

If enforcing security policies related to a root directory, be careful with symbolic links, canonicalization, and **paths modified during checking**. A `startsWith` check on an unnormalized path string is not a reliable confinement mechanism against malicious input. Use directory-handle-based APIs, no-follow-link options, or OS access controls when the task demands it.

## 7. Comparing `java.io.File` with `java.nio.file.Files`

`File` has a convenient API and is still seen in legacy libraries. However, `java.nio.file.Path` + `Files` is usually better suited when you need status queries, error handling, symbolic links, and detailed attributes.

| Need | Legacy `File` | NIO.2 (`Path`/`Files`) |
| --- | --- | --- |
| Existence | `file.exists()` | `Files.exists(path)` |
| Non-existence | `!file.exists()` often used with wrong semantics | `Files.notExists(path)` (may both be `false` with `exists()` if state is undetermined) |
| Regular file | `file.isFile()` | `Files.isRegularFile(path)` |
| Directory | `file.isDirectory()` | `Files.isDirectory(path)` |
| Byte length | `file.length()` | `Files.size(path)` may throw `IOException` |
| Readable/writable/executable? | `canRead/canWrite/canExecute` | `Files.isReadable/isWritable/isExecutable` |
| View basic attributes | `lastModified()`, some utilities | `Files.readAttributes(path, BasicFileAttributes.class)` |
| Symbolic links | Hard to control link-following behavior | `LinkOption.NOFOLLOW_LINKS`, `isSymbolicLink`, `readSymbolicLink` |
| Special file types | Limited info | `BasicFileAttributes.isOther()` and file attribute views |
| On query error | Many methods return `false`/`0` | Many metadata-reading operations throw `IOException` with useful info |

Do not interpret `Files.exists(path)==false` as `Files.notExists(path)==true`. Java NIO.2 has **three possible states** when querying the file system: known to exist, known not to exist, or **cannot be determined**. In the third state, **both `exists()` and `notExists()` can return `false`**. When you need to clearly distinguish permission errors, filesystem issues, or I/O failures, perform a query/operation that can report `IOException`, instead of relying solely on booleans.

### Example 4 — Retrieving Metadata with Error Control Using `Files`

```java
// NioFileAttributesDemo.java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;

public class NioFileAttributesDemo {
    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("nio-meta-", ".txt");

        try {
            Files.writeString(file, "Hello", StandardCharsets.UTF_8);

            BasicFileAttributes attributes =
                    Files.readAttributes(file, BasicFileAttributes.class);

            System.out.println("regular=" + attributes.isRegularFile());
            System.out.println("directory=" + attributes.isDirectory());
            System.out.println("size=" + attributes.size());
            System.out.println("filesSize=" + Files.size(file));
            System.out.println("exists=" + Files.exists(file));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Run:

```bash
javac NioFileAttributesDemo.java
java NioFileAttributesDemo
```

Output when operations succeed:

```text
regular=true
directory=false
size=5
filesSize=5
exists=true
```

`BasicFileAttributes` also has `creationTime()`, `lastModifiedTime()`, `lastAccessTime()`, `fileKey()`, `isSymbolicLink()`, `isOther()`; meaning and support level depend on the file-system provider. Do not assume all timestamps have the same precision or that `fileKey()` is always non-`null`.

`Files.readAttributes(...)` allows requesting multiple basic attributes in a single call and reports errors via `IOException`. However, do not assume this is an **atomic snapshot** of all attributes across all providers: the file can still change between fetching attributes and using them in the application.

## 8. The I/O Operation Itself Is the Real Check: TOCTOU

A common design bug is **check-then-act**:

```java
if (file.exists() && file.canRead()) {
    // Another process could delete or change permissions
    // right after the check.
    readTheFile(file);
}
```

This is **illustrative code**, not standalone runnable. Between the **time of check** and the **time of use** there is a gap. During this gap, the file can be deleted, replaced by a directory, modified in content, have permissions changed, or be redirected by a link. Thus preflight results are not a guarantee for the next operation.

What an application should do when the goal is **reading content**:

```java
try (InputStream input = Files.newInputStream(path)) {
    // Read using stream; still handle IOException as needed.
} catch (NoSuchFileException ex) {
    // File no longer exists at open time.
} catch (AccessDeniedException ex) {
    // Provider reported an access error.
} catch (IOException ex) {
    // Other I/O error.
}
```

This is **illustrative code**; it requires importing `InputStream`, `Files`, `Path`, `IOException`, `NoSuchFileException`, `AccessDeniedException`; `path` must be declared. Specific exception types depend on the provider and operation; not every permission error is classified as `AccessDeniedException`.

### Example 5 — Existence Check Succeeds, Yet the Subsequent Operation Fails

The following program **deterministically simulates** a state change by deleting the file itself between two steps. It does not create a real race, but logically shows why an `exists()` statement cannot guarantee the outcome of the next call.

```java
// CheckThenActDemo.java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;

public class CheckThenActDemo {
    public static void main(String[] args) throws Exception {
        Path path = Files.createTempFile("check-act-", ".txt");

        try {
            Files.writeString(path, "data", StandardCharsets.UTF_8);

            System.out.println("before=" + Files.exists(path));

            // A change can happen after the check step.
            Files.delete(path);

            try {
                Files.readString(path, StandardCharsets.UTF_8);
                System.out.println("read succeeded");
            } catch (NoSuchFileException ex) {
                System.out.println("read failed: file was removed");
            }
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
```

Run:

```bash
javac CheckThenActDemo.java
java CheckThenActDemo
```

Stdout when file system operations run normally:

```text
before=true
read failed: file was removed
```

The conclusion is **not** "check `exists()` again before reading." Extra checks still have a race window. Instead:

- For read operations, **open** the file and handle the result of the open/read itself; perform additional metadata checks if business logic requires.
- For writing/creating new files, use operational open options such as `StandardOpenOption.CREATE_NEW` to request creation **only if it does not already exist**, instead of doing `if (!exists) createFile()` and hoping no competitor intervenes.
- For multi-step file processing or security requirements, use handle management techniques, atomic renames, application transactions, or dedicated APIs depending on the file system and required guarantees.

## 9. Listing Directories and Checking Entry Types

To list directory members using the legacy API, `File.list()` or `File.listFiles()` can be used. However, `listFiles()` **can return `null`** if the path is not a directory or an I/O error occurs, instead of always returning an empty array:

```java
// Illustrative code with directory as a declared File.
File[] children = directory.listFiles();

if (children == null) {
    // Cannot treat this as a successfully listed directory.
} else {
    for (File child : children) {
        System.out.println(child.getName());
    }
}
```

`children.length == 0` means listing **succeeded and had zero elements**; `children == null` means **the list could not be obtained**. Do not write `for (File child : directory.listFiles())` without checking for `null` if the input might be invalid or inaccessible.

With NIO.2, `Files.newDirectoryStream(path)` or `Files.list(path)` provides listing mechanisms and can report errors via exceptions; you must **close** the directory stream/stream in `try-with-resources`. Listed entries may change if another process edits the directory; do not assume a fixed listing order, and do not treat the listing result as a consistent snapshot for subsequent operations.

## 10. Choosing the API Based on the Question Actually Being Answered

| Program goal | Approach |
| --- | --- |
| Display advisory info in a UI | Can use `File.exists()/isFile()/length()/canRead()`, keeping in mind state may change |
| Check for a regular file before suggesting file selection | `isFile()` or `Files.isRegularFile()` is useful, yet still catch errors on open |
| Need exact error reason when metadata cannot be read | `Files.readAttributes`, `Files.size` with `IOException` |
| Check broken symbolic link | `Files.exists(path, NOFOLLOW_LINKS)` and `Files.isSymbolicLink(path)` |
| Read a file for business logic | Open a stream or use `Files.readString` appropriately, catch and handle real errors |
| Create a new file without overwriting an existing file | Use `CREATE_NEW` instead of check-then-create |
| Count files in a directory | List with directory stream/`listFiles` and handle errors; do not use `File.length()` |
| Verify user access rights to data | Application/OS authorization mechanisms, not just `canRead/canWrite` |
| Retrieve attributes of various file types | NIO.2 APIs and corresponding attribute views/providers |

The `exists`, `canRead`, and `canWrite` checks are very useful for supporting UI conditions, early warnings, and status displays. Yet **final business decisions** usually depend on the result of the actual operation and the system's contract.

## 11. Common Mistakes When Using `File`

1. **Confusing `new File(path)` with creating a file:** the constructor does not create a file. Use an appropriate file-creation method and handle exceptions.
2. **Using `!isFile()` to conclude it is a directory:** there are multiple types/states; check `isDirectory()` separately.
3. **Using `length()==0` to identify an empty file:** non-existent files also yield `0`. Remember to check file type and error conditions.
4. **Confusing bytes with characters:** `length()` is byte count; UTF-8 and UTF-16 have different unit counts.
5. **Trusting `canRead()`/`canWrite()` absolutely:** permissions, files, and systems can change; a check does not replace the operation and `IOException`.
6. **Ignoring symbolic links:** broken links can make `exists()` return `false`; if you want to ask about the link, use `NOFOLLOW_LINKS`.
7. **Not distinguishing non-existent from undetermined:** `Files.exists()==false` and `Files.notExists()==false` can both be true if the provider cannot determine state.
8. **Using `File.length()` on directories:** directory length does not mean file count or total tree size.
9. **Calling `listFiles()` and iterating immediately:** the array can be `null`, causing `NullPointerException`.
10. **Assuming having an absolute path means the file exists:** `getAbsolutePath()` manipulates paths, not file validation.
11. **Checking `exists()` first then creating the file:** susceptible to races; prefer `CREATE_NEW` for non-overwriting creation.
12. **Ignoring exceptions when opening/reading/writing:** real error handling is mandatory, even after permission checks.
13. **Not closing streams/directory streams:** risks leaking file descriptors or resources; use `try-with-resources`.
14. **Using permission-check results as security controls:** file checks do not replace user- and business-level authorization.

## 12. Self-Check Knowledge Questions

**Q1.** After `File f = new File("missing.txt");`, has the file been created yet?

**Answer:** Not yet. The `File` object only represents a pathname; no file open or creation operation has occurred.

**Q2.** `f.exists()` returns `true`. Can we conclude `f.isFile()` is also `true`?

**Answer:** No. It could be a directory or another entry type.

**Q3.** Does `f.length() == 0` mean the file is currently empty?

**Answer:** Not necessarily. A non-existent file can also return `0`; a directory has an unspecified length.

**Q4.** Writing `"A😀"` in UTF-8, what are `File.length()` and `String.length()`?

**Answer:** 5 **bytes** and 3 UTF-16 `char` units respectively; the string contains 2 Unicode code points.

**Q5.** If `canRead()==true`, is the next `new FileInputStream(f)` guaranteed to succeed?

**Answer:** No. The file/permissions may change, or the operation may be constrained by other conditions.

**Q6.** Does `Files.exists(path)==false` always mean `Files.notExists(path)==true`?

**Answer:** No. If the state cannot be determined, both can return `false`.

**Q7.** A symbolic link exists, yet its target was deleted. What do you use to check the link itself?

**Answer:** `Files.exists(path, LinkOption.NOFOLLOW_LINKS)` and, when appropriate, `Files.isSymbolicLink(path)`.

**Q8.** Why is `if (!Files.exists(path)) { Files.createFile(path); }` not a safe way to ensure new creation under concurrency?

**Answer:** The two separate operations have a TOCTOU gap. For non-overwriting requirements, use an atomic check-and-create API such as `Files.createFile(path)` or open with `StandardOpenOption.CREATE_NEW` and handle `FileAlreadyExistsException`.

**Q9.** Do `listFiles()` returning `null` and an empty array mean the same thing?

**Answer:** No. `null` can indicate it is not a directory or an I/O error; an empty array means listing succeeded with zero entries.

**Q10.** If the goal is reading content for business processing, should you stop after `exists()` and `canRead()` both return true?

**Answer:** No. You must open/read the file, check the result, and handle `IOException`; those checks are only advisory at the moment of the call.

**Rule of thumb:** `File` represents a **path**; `exists()/isFile()/isDirectory()` answer different questions; `length()` measures **bytes** and cannot distinguish all states via `0`; `canRead()/canWrite()/canExecute()` reflect permissions in the current environment yet **do not guarantee the next operation succeeds**. When you need clear errors, symbolic link control, or safer operations, prefer `Path` and `Files`, and always handle exceptions from the real operation.