# NOFOLLOW_LINKS in Attribute Reading and File Checking (Java NIO.2)

## 1. Objective and Context

When a Java program checks a path with `java.nio.file.Files`, that path can point to a **real file**, a **directory**, or a **symbolic link** (abbreviated as symlink). A symlink is an entry in the file system that stores a path referencing another entry. For example:

```text
project/
├── data.txt             (regular file)
├── shortcut.txt -> data.txt
└── missing.txt -> gone.txt   (broken link: target does not exist)
```

When asking "is `shortcut.txt` a regular file?", we need to determine whether we are asking about **the target `data.txt`** or **the symlink entry `shortcut.txt` itself**. The two interpretations yield different results. `LinkOption.NOFOLLOW_LINKS` helps select the second interpretation in **APIs that support this option**.

After this lesson, you should be able to distinguish following a link from reading the link itself, predict the results of `Files.exists` / `Files.isRegularFile` / `Files.readAttributes` when symlinks or broken links are present, and avoid confusing metadata checks with safety guarantees when opening files.

## 2. What Does NOFOLLOW_LINKS Actually Mean?

`java.nio.file.LinkOption` is an enum with the constant `NOFOLLOW_LINKS`. For `Files` methods that accept a `LinkOption... options` parameter:

- **Default (without passing `NOFOLLOW_LINKS`):** usually follows a symlink at the end of the path and operates on the metadata of **the final target**.
- **With `LinkOption.NOFOLLOW_LINKS`:** does not follow a symlink at the end of the path; reads or inspects **the link entry itself**.
- If the path is not a symlink, both approaches usually return the same result when the object does not change and access is valid.

Example with `alias.txt -> original.txt`, where `original.txt` is a regular file:

| Question | Default | With `NOFOLLOW_LINKS` |
|---|---|---|
| `isRegularFile(alias)` | `true`, evaluates the target file | `false`, because the alias entry is a symlink |
| `isDirectory(alias)` | `false`, evaluates the target file | `false`, because the alias is not a directory |
| `exists(alias)` | `true` if the target can be read | `true` if the link itself can be verified |
| `readAttributes(alias, BasicFileAttributes.class).isRegularFile()` | `true` | `false` |
| `readAttributes(alias, BasicFileAttributes.class).isSymbolicLink()` | `false` in this example | `true` |

If the alias points to a **directory**, `Files.isDirectory(alias)` is usually `true`, whereas `Files.isDirectory(alias, NOFOLLOW_LINKS)` is `false`. `NOFOLLOW_LINKS` does not turn a symlink into a regular file and does not change its actual type.

**Limitation to remember:** the option applies to **the specific call**, not as a mode of the JVM or `Path`. It does not implicitly block symlinks in parent directory components of the path. A symlink should not be confused with a *hard link*: a hard link is another name for the same file entry and is not identified by `BasicFileAttributes.isSymbolicLink()`.

## 3. Reading Attributes from Two Perspectives

### 3.1. `Files.readAttributes` with `BasicFileAttributes`

This is a clear way to retrieve multiple pieces of information at once:

```java
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;

// path is a Path already defined in the program.
BasicFileAttributes targetAttributes =
        Files.readAttributes(path, BasicFileAttributes.class);

BasicFileAttributes entryAttributes =
        Files.readAttributes(
                path,
                BasicFileAttributes.class,
                LinkOption.NOFOLLOW_LINKS
        );

System.out.println(targetAttributes.isRegularFile());
System.out.println(entryAttributes.isSymbolicLink());
```

*This is an illustrative code snippet; `path` must be declared and `IOException` handled in the containing program.* For a symlink pointing to an existing regular file, the two printed lines are `true` and `true` respectively. The first line describes **the target**, and the second line describes **the link entry**. When not following the link, `isRegularFile()` and `isDirectory()` on the symlink's metadata are both typically `false`, while `isSymbolicLink()` is `true`.

`BasicFileAttributes` provides entry-type checks (`isRegularFile`, `isDirectory`, `isSymbolicLink`, `isOther`), size (`size`), timestamps (`creationTime`, `lastModifiedTime`, `lastAccessTime`), and `fileKey`. When using `NOFOLLOW_LINKS`, these attributes describe **the link** if the final path element is a symlink. **Do not infer that the `size()` of a symlink is the content size of the target file**; the values and precision of many attributes depend on the file system/provider. Reading multiple attributes in one call is also not guaranteed by every provider to be an atomic snapshot against concurrent changes.

### 3.2. Reading Attributes by Name

The following two overloads also accept `NOFOLLOW_LINKS`:

```java
Object kind = Files.getAttribute(
        path, "basic:isSymbolicLink", LinkOption.NOFOLLOW_LINKS);

var attributes = Files.readAttributes(
        path,
        "basic:size,lastModifiedTime,isSymbolicLink",
        LinkOption.NOFOLLOW_LINKS
);
```

This is an illustrative snippet, assuming `path` exists and `IOException` is handled externally. `getAttribute` returns `Object`; you should cast according to the attribute being read—for example, the value of `"basic:isSymbolicLink"` is `Boolean`. The string-based `readAttributes` returns `Map<String,Object>`, not `BasicFileAttributes`. The name `basic` is the default attribute view; other attribute groups such as `posix:*` work only when supported by the provider.

Several related APIs also accept `LinkOption...`, such as `Files.getLastModifiedTime(path, NOFOLLOW_LINKS)`, `Files.getPosixFilePermissions(path, NOFOLLOW_LINKS)`, `Files.getOwner(path, NOFOLLOW_LINKS)`, and `Files.getFileAttributeView(path, BasicFileAttributeView.class, NOFOLLOW_LINKS)`. Read method signatures carefully: **`Files.size(path)` does not accept `LinkOption`**, so you cannot write `Files.size(path, NOFOLLOW_LINKS)`; to query the metadata size of the symlink itself, use `readAttributes` with the corresponding option.

### 3.3. Getting the Target Recorded in a Symlink

`Files.readSymbolicLink(link)` reads the `Path` **stored inside the link**, rather than reading the target file's content and without guaranteeing that the target exists. If the link was created with a relative target such as `data.txt`, the returned path may also be a relative path. Do not equate this result with `link.toRealPath()`: the latter resolves the real path in the file system and has its own link-following rules.

## 4. Checking Existence and Entry Type

Common checking methods:

| API | Accepts `LinkOption...`? | Key Point to Remember |
|---|---|---|
| `Files.exists(path, options)` | Yes | Checks whether entry exists; follows symlinks by default |
| `Files.notExists(path, options)` | Yes | Only `true` if verified not to exist |
| `Files.isRegularFile(path, options)` | Yes | A symlink to a regular file is a "regular file" by default, but not with `NOFOLLOW_LINKS` |
| `Files.isDirectory(path, options)` | Yes | Similarly when a symlink points to a directory |
| `Files.isSymbolicLink(path)` | No | Checks the symlink entry itself; no need to pass `NOFOLLOW_LINKS` |
| `Files.isReadable(path)`, `isWritable(path)`, `isExecutable(path)` | No | No overload accepting `LinkOption`; do not assume "no follow" |
| `Files.readString(path)`, `readAllBytes(path)` | No | Reads content, not a metadata API with `LinkOption` |

**Common pitfall:** `Files.isSymbolicLink(path)` is useful for identifying a link, but returning `false` can also happen when the state cannot be determined. If the application needs to distinguish an I/O error from "not a link", use `Files.readAttributes(path, BasicFileAttributes.class, NOFOLLOW_LINKS)` and handle exceptions.

### 4.1. Broken Symlink (Dangling Symlink) Case

Suppose `broken.txt -> missing.txt` and `missing.txt` truly does not exist, while the `broken.txt` entry still exists:

| Expression | Result when check succeeds | Reason |
|---|---|---|
| `Files.exists(broken)` | `false` | Follows link to non-existent target |
| `Files.exists(broken, NOFOLLOW_LINKS)` | `true` | Link entry is still present |
| `Files.notExists(broken)` | `true` | Confirms target is absent |
| `Files.notExists(broken, NOFOLLOW_LINKS)` | `false` | Link entry still exists |
| `Files.isSymbolicLink(broken)` | `true` | Checks the link itself |
| `Files.isRegularFile(broken, NOFOLLOW_LINKS)` | `false` | Link is not a regular file |
| `Files.readAttributes(broken, BasicFileAttributes.class)` | May throw `NoSuchFileException` | Cannot read attributes of target |
| `Files.readAttributes(broken, BasicFileAttributes.class, NOFOLLOW_LINKS)` | Reads attributes of link if provider allows | Does not require target to exist |

**Never use `!Files.exists(path)` as definitive proof that no entry exists there.** If permissions or I/O prevent determination, both `exists` and `notExists` can return `false`. Boolean functions such as `isDirectory` and `isRegularFile` also fold the "undetermined" case into `false`. When the application needs to know *why* it failed, read attributes using an API that throws `IOException` and handle it specifically.

## 5. Runnable Java 17+ Example: A Valid Link That Becomes Broken

The following program creates a temporary directory, a target file, and a symlink with a relative target. It compares reading attributes/checking before and after deleting the target file; `finally` cleans up created resources.

**File:** `NoFollowLinksDemo.java`

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;

import static java.nio.file.LinkOption.NOFOLLOW_LINKS;

public class NoFollowLinksDemo {
    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("nofollow-demo-");
        Path target = directory.resolve("data.txt");
        Path link = directory.resolve("shortcut.txt");

        try {
            Files.writeString(target, "Hello Java");

            try {
                // Relative target is interpreted from the directory containing the link.
                Files.createSymbolicLink(link, target.getFileName());
            } catch (IOException | UnsupportedOperationException
                     | SecurityException e) {
                System.out.println("Cannot create symbolic link");
                return;
            }

            BasicFileAttributes followed = Files.readAttributes(
                    link, BasicFileAttributes.class);
            BasicFileAttributes linkItself = Files.readAttributes(
                    link, BasicFileAttributes.class, NOFOLLOW_LINKS);

            System.out.println("target regular: " + followed.isRegularFile());
            System.out.println("entry symbolic: " + linkItself.isSymbolicLink());
            System.out.println("regular nofollow: "
                    + Files.isRegularFile(link, NOFOLLOW_LINKS));
            System.out.println("exists follow: " + Files.exists(link));
            System.out.println("exists nofollow: "
                    + Files.exists(link, NOFOLLOW_LINKS));

            Files.delete(target); // Link remains, but target disappears.
            System.out.println("broken exists follow: " + Files.exists(link));
            System.out.println("broken exists nofollow: "
                    + Files.exists(link, NOFOLLOW_LINKS));
        } finally {
            Files.deleteIfExists(link);
            Files.deleteIfExists(target);
            Files.deleteIfExists(directory);
        }
    }
}
```

Compile and run in the directory containing the source file:

```bash
javac NoFollowLinksDemo.java
java NoFollowLinksDemo
```

When the system supports symlink creation and there are no concurrent external changes, expected stdout is:

```text
target regular: true
entry symbolic: true
regular nofollow: false
exists follow: true
exists nofollow: true
broken exists follow: false
broken exists nofollow: true
```

Some Windows environments require privileges or settings allowing symlink creation; other providers/file systems may also not support it. When link creation fails, the program prints only `Cannot create symbolic link` and runs the `finally` block. The line `Files.delete(target)` deletes the target file **rather than deleting the link**; therefore the two `exists` results at the end differ. The code does not depend on a specific temporary path, and the relative target path avoids tying the example to a single operating system.

## 6. Real-World Application Scenarios

### Scenario A: A Directory Listing Tool That Needs to Distinguish Links

Suppose a file manager wants to label each entry it sees as "File", "Directory", or "Symbolic link". Read metadata with `NOFOLLOW_LINKS` so a symlink pointing to a directory is not treated as the directory itself:

```java
BasicFileAttributes attrs = Files.readAttributes(
        entry, BasicFileAttributes.class, NOFOLLOW_LINKS);

String kind = attrs.isSymbolicLink() ? "Symbolic link"
        : attrs.isDirectory() ? "Directory"
        : attrs.isRegularFile() ? "File"
        : "Other";
```

This illustrative snippet assumes `entry` is a `Path` and `IOException` is handled by the caller. If you also want to display the target type, perform **another read without `NOFOLLOW_LINKS`**, and accept that it may fail for broken links. Avoid presenting symlink entry metadata as though it were target metadata.

### Scenario B: Processing an Upload Directory Containing Symlinks

If business rules only permit **the directly specified object to be a regular file**, `Files.isRegularFile(candidate, NOFOLLOW_LINKS)` is a clear check: it rejects a final entry that is a symlink even when the symlink leads to a regular file. If business rules allow symlinks, you need a separate policy on valid targets and parent paths.

However, **checking and then opening the file are two separate operations**. Between them, another actor or thread can swap the entry or path (race condition/TOCTOU). `NOFOLLOW_LINKS` in a metadata check **does not protect** a subsequent `Files.newInputStream`, `Files.readString`, or open operation. To handle untrusted paths, you need root directory policies, file system permissions, opening files with appropriate options, and when available using `SecureDirectoryStream` for operations relative to an already-opened directory. Do not rely solely on `exists` or `toRealPath` before opening to claim all races have been eliminated.

### Scenario C: Tracking the Timestamp of a Link

A diagnostic tool wanting to know "when was the symlink itself last modified?" can call:

```java
var targetTime = Files.getLastModifiedTime(link);
var linkTime = Files.getLastModifiedTime(link, NOFOLLOW_LINKS);
```

This is an illustrative snippet with `link` declared and `IOException` handled externally. `targetTime` describes the target file (if accessible), while `linkTime` describes the link (if supported by the file system). The two timestamps can differ. Do not assume all file systems store timestamps or precision in the same way.

## 7. Distinction from Related APIs

- **`Path.toRealPath()`:** typically resolves symlinks to obtain the real path; `toRealPath(NOFOLLOW_LINKS)` has rules for not following links while determining the path. It is not an API for reading `BasicFileAttributes`.
- **`Files.readSymbolicLink(link)`:** returns the path contained in the symlink; does not dereference and read content.
- **`Files.walkFileTree` / `Files.walk`:** by default do not descend into symlinks during tree traversal; enabling `FileVisitOption.FOLLOW_LINKS` is a separate mechanism, not passing `LinkOption.NOFOLLOW_LINKS` to all operations.
- **`Files.copy`:** supports `LinkOption.NOFOLLOW_LINKS` via the `CopyOption...` parameter; when copying a link with this option, the link entry is copied instead of following to the target, depending on file system/provider capability. Do not infer from this that every `Files` overload accepts the option.
- **`Files.isSymbolicLink(path)`:** the check itself already asks about the link; do not write `Files.isSymbolicLink(path, NOFOLLOW_LINKS)` because no such signature exists.

## 8. Exceptions, Environment Limitations, and Common Mistakes

1. **Mistakenly calling an API without an option parameter.** `Files.size(path, NOFOLLOW_LINKS)` and `Files.isSymbolicLink(path, NOFOLLOW_LINKS)` do not compile. Choose an overload defined by the Java API.
2. **Confusing `NOFOLLOW_LINKS` with "the path contains no symlinks".** It checks the final entry according to the call's semantics; it does not prove that every parent path component is not a symlink.
3. **Confusing `exists == false` with guaranteed non-existence.** There are cases where lack of permissions or I/O makes the state undetermined; `notExists` also returns `false` when uncertain.
4. **Ignoring broken links.** Following the link cannot retrieve target attributes; not following the link can still read metadata of the link entry itself.
5. **Treating `isRegularFile == false` as a symlink.** That result can also be a directory, a special file type, a non-existent file, or a determination error. To classify, use `BasicFileAttributes` and handle exceptions.
6. **Assuming link attributes represent target content.** `size`, `lastModifiedTime`, and `fileKey` depend on the entry being read and the provider; do not mislabel their meaning when displaying them.
7. **Ignoring OS capabilities.** Symlink creation may be denied; views such as POSIX are not present on every system; some operations on symlink attributes themselves may be unsupported.
8. **Using file checks as security locks.** Checks and uses can be altered between two points in time. When security is required, design safe access operations right at open/use time.

When reading attributes such as `readAttributes` / `getAttribute`, prepare to handle `IOException` (especially `NoSuchFileException` if the target was deleted), `UnsupportedOperationException` for unsupported views, and `SecurityException` when the environment blocks access. Avoid catching all exceptions and silently assuming the object "does not exist".

## 9. Self-Check

1. Symlink `docs -> actual-directory`: what do `Files.isDirectory(docs)` and `Files.isDirectory(docs, NOFOLLOW_LINKS)` return if the target still exists? **Expected:** `true` and `false`.
2. Link `bad -> removed.txt` still remains, while the target has been deleted. What is `Files.exists(bad, NOFOLLOW_LINKS)`? **Expected:** `true` if the link entry itself can be checked.
3. If you want to ask whether a path is a link and distinguish metadata read errors, what do you choose? **Hint:** `Files.readAttributes(path, BasicFileAttributes.class, NOFOLLOW_LINKS).isSymbolicLink()` inside an `IOException`-handling block.
4. Why does `Files.isRegularFile(path, NOFOLLOW_LINKS)` before `Files.readString(path)` not guarantee reading the same object just checked? **Because:** the path/entry can change between the two calls; the content-reading method does not accept the same `LinkOption`.

## 10. Takeaways and Official Documentation

**Core rule:** *To know what the object at the end of a link is, use the default; to know what the link entry itself is, use `NOFOLLOW_LINKS` on APIs that support it.* For existence checks, remember the "undetermined" case; for security, remember the boundary between reading metadata and opening/using a file.

- Java SE 21 — `Files`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html
- Java SE 21 — `LinkOption`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/LinkOption.html
- Java SE 21 — `BasicFileAttributes`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/attribute/BasicFileAttributes.html