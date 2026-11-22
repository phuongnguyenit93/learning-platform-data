# OpenOption, CopyOption, LinkOption, and FileVisitOption Reference Table in Java NIO.2

## 1. Purpose and Map of the Option Groups

In `java.nio.file` (NIO.2), the same `Path` object can be **opened for reading/writing**, **copied/moved**, **inspected for symbolic links**, or **traversed as a directory tree**. Each operation takes a different option family. Reading the API signature accurately matters more than memorizing an enum name.

| Group | Java type | Primary purpose | Typical APIs |
| --- | --- | --- | --- |
| `OpenOption` | **Interface** | Specifies how to open/create a file or channel | `Files.newOutputStream`, `Files.newByteChannel`, `FileChannel.open`, `Files.writeString` |
| `StandardOpenOption` | **Enum implements OpenOption** | `READ`, `WRITE`, `APPEND`, `CREATE`, ... | Corresponding APIs accepting `OpenOption` |
| `CopyOption` | **Interface** | Specifies how to copy/move | `Files.copy(Path, Path, CopyOption...)`, `Files.move` |
| `StandardCopyOption` | **Enum implements CopyOption** | `REPLACE_EXISTING`, `COPY_ATTRIBUTES`, `ATOMIC_MOVE` | `Files.copy` / `Files.move` depending on the option |
| `LinkOption` | **Enum implements OpenOption, CopyOption** | `NOFOLLOW_LINKS`: do not dereference symbolic links in supported APIs | `Files.exists`, `Files.readAttributes`, `Files.copy`, `Files.newByteChannel` |
| `FileVisitOption` | **Separate enum** | `FOLLOW_LINKS`: traverse through symlinks when walking a tree | `Files.walkFileTree`, `Files.walk` |

**Note:** `OpenOption` and `CopyOption` are *not enums*; neither `OpenOption.READ` nor `CopyOption.REPLACE_EXISTING` exists. The constants live in `StandardOpenOption` and `StandardCopyOption`. Likewise, `FileVisitOption` is not a parameter for `Files.copy`, and `LinkOption.NOFOLLOW_LINKS` is not an option for `Files.walkFileTree`.

Common imports:

```java
import java.nio.file.Path;
import java.nio.file.Files;
import java.nio.file.OpenOption;
import java.nio.file.StandardOpenOption;
import java.nio.file.CopyOption;
import java.nio.file.StandardCopyOption;
import java.nio.file.LinkOption;
import java.nio.file.FileVisitOption;
```

## 2. OpenOption / StandardOpenOption Reference Table

`OpenOption` is the parameter type; `StandardOpenOption` provides 10 standard values. Providers may support additional options, and individual methods may allow different subsets.

| `StandardOpenOption` | Meaning | When to use / notes |
| --- | --- | --- |
| `READ` | Open a file for reading | Default for `Files.newInputStream(path)` and `Files.newByteChannel(path)` when no write option is specified; the file must exist. |
| `WRITE` | Open a file for writing | Does not by itself imply appending or truncating content; commonly combined with `CREATE`, `TRUNCATE_EXISTING`. |
| `APPEND` | Each write goes to the end of the file | Implies write access on standard channels; with `newByteChannel` it cannot be combined with `READ` or `TRUNCATE_EXISTING`. Concurrent appending is not guaranteed to be atomic across all file systems. |
| `TRUNCATE_EXISTING` | Truncate an existing file to length 0 when opening for writing | Takes effect only with write access; **risk of data loss** if used by mistake. |
| `CREATE` | Create the file if it does not exist, or open the existing file if it does | Useful for writes that may create a new file; ignored when used together with `CREATE_NEW`, or when opening read-only. |
| `CREATE_NEW` | Create a new file only, failing if the path already exists | Existence check and file creation are performed atomically with respect to file system operations; useful to prevent unintended overwrites. |
| `DELETE_ON_CLOSE` | Best-effort attempt to delete the file when the handle closes | *Best effort*, not a guaranteed secure delete; avoid using it for data that must be persisted. May disallow opening symlinks depending on the provider. |
| `SPARSE` | Hint to create a sparse file when creating a new file | Only a hint; unsupported providers/file systems may ignore it, not a guarantee of space savings. |
| `SYNC` | Require synchronous updates of content **and metadata** to the storage device | Can incur I/O cost; different from transactional guarantees or atomic writes. |
| `DSYNC` | Require synchronous updates of **content** to the storage device | Narrower guarantee scope than `SYNC`; performance and support depend on the system. |

### 2.1. Defaults by method

| API call | Default when no options are passed | Effect |
| --- | --- | --- |
| `Files.newInputStream(path)` | `READ` | Opens a read stream; fails if unreadable. |
| `Files.newOutputStream(path)` | `CREATE + TRUNCATE_EXISTING + WRITE` | Overwrites the old file's content or creates a new file. |
| `Files.newByteChannel(path)` | `READ` | Read-only channel if no options are passed. |
| `Files.writeString(path, text)` | `CREATE + TRUNCATE_EXISTING + WRITE` | Subsequent calls replace previous content by default. |
| `Files.write(path, bytes)` | `CREATE + TRUNCATE_EXISTING + WRITE` | Same behavior when writing a byte array. |

Check the **API signature** when applying them: `newByteChannel(Path, OpenOption...)` and `FileChannel.open` support combinations of read/write access, whereas `newOutputStream` does not accept `READ`; `Files.newInputStream` is not a tool for creating/writing files. Supported additional options vary across overloads.

### 2.2. Typical combinations

```java
Path path = Path.of("data.txt");

// Create exclusively new, fail if data.txt already exists:
Files.writeString(path, "first\n",
        StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);

// Append to an existing file, do not create automatically:
Files.writeString(path, "next\n", StandardOpenOption.APPEND);

// Open for append, create if missing:
try (var out = Files.newOutputStream(path,
        StandardOpenOption.CREATE, StandardOpenOption.APPEND)) {
    out.write("tail\n".getBytes(java.nio.charset.StandardCharsets.UTF_8));
}

// Intentionally replace all content:
Files.writeString(path, "replaced\n",
        StandardOpenOption.WRITE, StandardOpenOption.TRUNCATE_EXISTING);
```

The code above is an illustrative *snippet*, with `path` in a writable directory. The last statement requires the file to already exist; to also allow creating a new file, add `CREATE`. Use `try-with-resources` when opening a stream/channel directly so the resource is closed even when an exception occurs.

**Comparing `CREATE` and `CREATE_NEW`:** `CREATE` does not prevent opening an existing file; `CREATE_NEW` fails immediately if the path already exists (including a symlink). `CREATE_NEW` is safer than `if (!Files.exists(path)) Files.writeString(...)` because separate check-then-act steps have a race condition (TOCTOU).

**Comparing `APPEND` and `TRUNCATE_EXISTING`:** `APPEND` preserves existing bytes and adds bytes at the end; `TRUNCATE_EXISTING` erases existing bytes immediately upon opening for writing. Do not combine these two options. `APPEND` does not mean file locking or atomic log record writes across multiple processes.

## 3. CopyOption / StandardCopyOption Reference Table

`CopyOption` is an interface. `StandardCopyOption` has only **three** standard constants:

| `StandardCopyOption` | For `Files.copy` | For `Files.move` |
| --- | --- | --- |
| `REPLACE_EXISTING` | Allows replacing an existing target; a non-empty target directory may fail to be replaced. | Allows replacing an existing target within file system/target file constraints. |
| `COPY_ATTRIBUTES` | Attempts to copy the source's attributes (e.g., last-modified time); attribute sets and precision depend on the file system/provider. | **Not** a standard option listed by `Files.move` to configure moving; move has its own attribute-preservation rules. |
| `ATOMIC_MOVE` | **Not used for `Files.copy`**; this is a move option. | Requests moving as an atomic file system operation; if unsupported, throws `AtomicMoveNotSupportedException`. Other options are ignored when `ATOMIC_MOVE` is used. |

Example:

```java
Path source = Path.of("source.txt");
Path target = Path.of("backup.txt");

// Copy, allowing replacement and attempting to preserve metadata:
Files.copy(source, target,
        StandardCopyOption.REPLACE_EXISTING,
        StandardCopyOption.COPY_ATTRIBUTES);

// Rename or move to another location:
Files.move(target, Path.of("archive.txt"),
        StandardCopyOption.REPLACE_EXISTING);

// Request an atomic move only when the file system permits it:
Files.move(Path.of("draft.txt"), Path.of("published.txt"),
        StandardCopyOption.ATOMIC_MOVE);
```

This is a *snippet*, requiring the source paths to exist. When using `ATOMIC_MOVE`, do not assume adding `REPLACE_EXISTING` forces target replacement: JDK documentation specifies that other options are ignored, and if the target already exists, the provider may replace it or throw an error. For applications needing a strict overwrite policy, design exception handling and verify behavior on the target file system.

### 3.1. Three common misconceptions with copy/move

1. **Copying a file is different from recursively copying a directory.** `Files.copy(sourceDir, targetDir)` creates an empty target directory and does not copy its children automatically. To copy a directory tree, combine `walkFileTree` with creating directories and copying each file.
2. **`REPLACE_EXISTING` does not make a copy an atomic transaction.** If I/O fails midway, the target may be left incomplete. Reliability requires a temporary-file write + verification + appropriate move workflow, and relying on `ATOMIC_MOVE` only when the provider actually supports it.
3. **`Files.move` is not always a simple rename.** Within the same file store it may rename directly; across different file stores it may require copy-then-delete and can fail or be non-atomic. Do not infer atomicity just because a single Java call returned.

### 3.2. Symbolic links when copying and moving

By default, `Files.copy(Path, Path, ...)` **follows symlinks at the source** and copies the contents of *the target the link points to*. Add `LinkOption.NOFOLLOW_LINKS` to copy **the symbolic link object itself** (if supported by the system). If the target is already a symlink and `REPLACE_EXISTING` is used, the link at the target itself is replaced; the target link is not followed automatically.

`Files.move` moves **the symbolic link itself** if the source is a link. It does not dereference the link by default to move the file the link points to. Therefore, using `NOFOLLOW_LINKS` for a copy operation has a completely different meaning from `FOLLOW_LINKS` when walking a tree.

## 4. LinkOption: NOFOLLOW_LINKS and Per-API Semantics

`LinkOption` has only **`NOFOLLOW_LINKS`**. It implements *both* `OpenOption` and `CopyOption`, though whether the option is accepted still depends on each API.

| Task | Default | When passing `LinkOption.NOFOLLOW_LINKS` |
| --- | --- | --- |
| `Files.exists(link)` / `notExists(link)` | Follows link to target | Checks the existence of the **link itself**; a dangling symlink can still count as an existing link. |
| `Files.isDirectory(link)` / `isRegularFile(link)` | Inspects the target's type | Inspects the link itself; a symlink is not treated as a directory or regular file based on its target's type. |
| `Files.readAttributes(link, BasicFileAttributes.class)` | Reads target attributes | Reads the attributes of the symlink itself. |
| `Files.getLastModifiedTime(link)` | Target's timestamp | Timestamp of the symlink itself when supported by the provider. |
| `Files.copy(link, target, NOFOLLOW_LINKS)` | By default copies the target the link points to | Copies the symlink itself, if supported. |
| `Files.newByteChannel(link, ..., NOFOLLOW_LINKS)` | May follow symlinks when opening | Opens only if the opened object satisfies the no-follow rule; may fail when the path is a symlink. |

Distinguish a **symlink** from a **hard link**: a symlink is an entry pointing to another path and can dangle; a hard link is another name for the same file within the same file system. `NOFOLLOW_LINKS` targets symbolic links; it does not turn a hard link into a special object to skip.

Example checking the link itself:

```java
Path candidate = Path.of("alias");
boolean entryExists = Files.exists(candidate, LinkOption.NOFOLLOW_LINKS);
boolean isLink = Files.isSymbolicLink(candidate);
System.out.println("entry exists: " + entryExists);
System.out.println("symbolic link: " + isLink);
```

The output of the two lines above **depends on the actual file system**, so no fixed stdout is assumed. Both `Files.exists` and `Files.notExists` can return `false` when the state cannot be determined; they are not exact logical negations of each other. Do not rely on check-then-open for absolute protection against link replacement in sensitive operations; consider APIs operating relative to a directory handle (`SecureDirectoryStream` where supported), permissions, and exception handling.

## 5. FileVisitOption: FOLLOW_LINKS When Walking a Tree

`FileVisitOption` has only **`FOLLOW_LINKS`** in Java 17/21.

| API call | Without `FOLLOW_LINKS` | With `FOLLOW_LINKS` |
| --- | --- | --- |
| `Files.walkFileTree(start, visitor)` | Traverses deeply but **does not enter directories pointed to by symlinks**. | The 4-parameter overload accepts an option set; can traverse into symlink target directories. |
| `Files.walkFileTree(start, options, maxDepth, visitor)` | `EnumSet.noneOf(FileVisitOption.class)`: does not follow symlinks. | `EnumSet.of(FileVisitOption.FOLLOW_LINKS)`: follows symlinks up to the allowed depth. |
| `Files.walk(start, maxDepth, options...)` | Does not follow symlinks, returns `Stream<Path>`. | Follows symlinks; still requires closing the stream after use. |

Standard syntax example:

```java
Files.walkFileTree(
    root,
    java.util.EnumSet.of(FileVisitOption.FOLLOW_LINKS),
    3,
    visitor
);
```

`root` and `visitor` are variables already declared in the calling context; this snippet is not a standalone program. Parameter `3` is the maximum depth: `root` is at depth `0`, direct children at `1`. `Integer.MAX_VALUE` effectively means no active depth limit.

### 5.1. FileVisitor callbacks and control results

This topic pairs naturally with `FileVisitOption`: the option controls traversal behavior, while `FileVisitor` decides how to react to each entry.

| Callback | When it is called | Key points to remember |
| --- | --- | --- |
| `preVisitDirectory(dir, attrs)` | Before visiting the children of a directory | Return `SKIP_SUBTREE` to avoid descending into the subtree. |
| `visitFile(file, attrs)` | When encountering a regular file or an entry treated as a file | Useful for searching or copying individual files. |
| `visitFileFailed(file, exc)` | When attributes cannot be read, a directory cannot be opened, or a symlink cycle is detected | May receive `FileSystemLoopException` when `FOLLOW_LINKS` is enabled. |
| `postVisitDirectory(dir, exc)` | After finishing a directory or when an error occurs while visiting entries | Suitable for deleting a directory after its children are processed; inspect `exc`. |

| `FileVisitResult` | Meaning |
| --- | --- |
| `CONTINUE` | Continue traversal. |
| `SKIP_SUBTREE` | Skip descendants of the current directory (meaningful when returned from `preVisitDirectory`). |
| `SKIP_SIBLINGS` | Skip remaining sibling entries. |
| `TERMINATE` | Terminate traversal immediately. |

Returning `null` from a visitor causes `walkFileTree` to throw `NullPointerException`. The order of sibling entries in a directory is **not guaranteed**; if deterministic ordering is needed for reports, implement sorting yourself.

### 5.2. Why FOLLOW_LINKS requires caution

If the tree contains a symlink pointing back up to an ancestor directory, `FOLLOW_LINKS` can create a cycle. `walkFileTree` detects cycles and invokes `visitFileFailed` with `FileSystemLoopException`; do not assume it will loop infinitely or that every symlink will traverse cleanly. For deletion, backup, or scanning untrusted data, **not following** by default helps avoid escaping the intended tree. Even with a finite `maxDepth`, you must still handle access permission errors and symlinks modified during traversal.

`Files.walk` returns a stream that may hold directory handles; always use `try-with-resources`:

```java
try (var paths = Files.walk(root, 2)) {
    long count = paths.filter(Files::isRegularFile).count();
    System.out.println("regular files: " + count);
}
```

This snippet depends on the `root` directory. With `FOLLOW_LINKS`, an I/O error while consuming the stream may be wrapped in `UncheckedIOException`, unlike the error callback in `walkFileTree`. Note that `Files.isRegularFile` follows symbolic links by default on the inspected entry; if symlinks themselves must not be counted as regular files, pass `LinkOption.NOFOLLOW_LINKS`.

## 6. Standalone Java 17+ Example: Open, Copy, Move

Create the file `OptionDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import static java.nio.file.StandardOpenOption.*;
import static java.nio.file.StandardCopyOption.*;

public class OptionDemo {
    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("nio-option-demo-");
        Path source = dir.resolve("source.txt");
        Path copy = dir.resolve("copy.txt");
        Path moved = dir.resolve("moved.txt");

        try {
            Files.writeString(source, "alpha\n", StandardCharsets.UTF_8,
                    CREATE_NEW, WRITE);
            Files.writeString(source, "beta\n", StandardCharsets.UTF_8, APPEND);

            Files.copy(source, copy, COPY_ATTRIBUTES);
            Files.writeString(copy, "gamma\n", StandardCharsets.UTF_8,
                    WRITE, TRUNCATE_EXISTING);
            Files.move(copy, moved);

            System.out.println(
                    Files.readString(source, StandardCharsets.UTF_8)
                            .replace("\n", "|"));
            System.out.println(
                    Files.readString(moved, StandardCharsets.UTF_8).trim());
            System.out.println(Files.exists(copy));
        } finally {
            Files.deleteIfExists(moved);
            Files.deleteIfExists(copy);
            Files.deleteIfExists(source);
            Files.deleteIfExists(dir);
        }
    }
}
```

Compile and run inside the directory containing `OptionDemo.java`:

```bash
javac -encoding UTF-8 OptionDemo.java
java OptionDemo
```

Exact output:

```text
alpha|beta|
gamma
false
```

Explanation: `CREATE_NEW` creates `source` and guards against accidentally opening an existing file; `APPEND` adds `beta` after `alpha`; `COPY_ATTRIBUTES` requests preserving attributes during copy; `TRUNCATE_EXISTING` replaces the copy's content with `gamma`; `move` renames the copied file to `moved`, so the `copy` path no longer exists. The example cleans up the temporary files and directory upon normal completion; if another process interferes or cleanup fails, an `IOException` may still occur.

## 7. Standalone Java 17+ Example: walkFileTree Without Following Symlinks

Create `WalkDemo.java`:

```java
import java.io.IOException;
import java.nio.file.FileVisitOption;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.EnumSet;
import java.util.concurrent.atomic.AtomicInteger;

public class WalkDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("nio-walk-demo-");
        Path sub = Files.createDirectory(root.resolve("sub"));
        Path one = root.resolve("a.txt");
        Path two = sub.resolve("b.txt");

        try {
            Files.writeString(one, "a");
            Files.writeString(two, "b");

            AtomicInteger directories = new AtomicInteger();
            AtomicInteger files = new AtomicInteger();

            Files.walkFileTree(root, EnumSet.noneOf(FileVisitOption.class),
                    Integer.MAX_VALUE, new SimpleFileVisitor<Path>() {
                        @Override
                        public FileVisitResult preVisitDirectory(
                                Path dir, BasicFileAttributes attrs) {
                            directories.incrementAndGet();
                            return FileVisitResult.CONTINUE;
                        }

                        @Override
                        public FileVisitResult visitFile(
                                Path file, BasicFileAttributes attrs) {
                            files.incrementAndGet();
                            return FileVisitResult.CONTINUE;
                        }
                    });

            System.out.printf("dirs=%d, files=%d%n",
                    directories.get(), files.get());
        } finally {
            Files.deleteIfExists(two);
            Files.deleteIfExists(one);
            Files.deleteIfExists(sub);
            Files.deleteIfExists(root);
        }
    }
}
```

```bash
javac -encoding UTF-8 WalkDemo.java
java WalkDemo
```

Exact output on the structure created by the program:

```text
dirs=2, files=2
```

The root directory and one subdirectory produce `2` `preVisitDirectory` calls; two files produce `2` `visitFile` calls. Changing `EnumSet.noneOf(FileVisitOption.class)` to `EnumSet.of(FileVisitOption.FOLLOW_LINKS)` would enable following symlinks, though the example creates no symlinks so the counts stay unchanged.

## 8. Choosing Options by Scenario

| Practical requirement | Recommended choice | Why |
| --- | --- | --- |
| Read an existing file | `Files.readString(path)` or open with `READ` | Does not create or write the file. |
| Overwrite with completely new content | `Files.writeString(path, text)` or `WRITE + CREATE + TRUNCATE_EXISTING` | Truncates old content before writing. |
| Append to a log, creating if needed | `CREATE + APPEND` | Does not truncate existing data, though it does not guarantee cross-process atomic records. |
| Create only if absent | `CREATE_NEW + WRITE` | Avoids the "check then create" race condition. |
| Back up a file, overwriting the backup | `Files.copy(a, b, REPLACE_EXISTING, COPY_ATTRIBUTES)` | Copies content along with supported attributes. |
| Copy the symbolic link itself | `Files.copy(link, dst, LinkOption.NOFOLLOW_LINKS)` | Does not dereference the link at the source. |
| Check whether an entry is a symlink | `Files.isSymbolicLink(path)` | Checks the path's entry type regardless of whether the target exists. |
| Inspect attributes of **the link itself** | `Files.readAttributes(path, BasicFileAttributes.class, NOFOLLOW_LINKS)` | Avoids accidentally reading the target's metadata. |
| Rename/move requiring atomicity | `Files.move(src, dst, ATOMIC_MOVE)`, catch `AtomicMoveNotSupportedException` | Do not assume the provider supports it. |
| Default directory traversal | `Files.walkFileTree(root, visitor)` | Does not follow symlinks. |
| Traverse directories through symlinks too | `Files.walkFileTree(root, EnumSet.of(FOLLOW_LINKS), maxDepth, visitor)` | May step outside the logical tree and must handle cycles. |

### Easily confused pairs

- `NOFOLLOW_LINKS` and `FOLLOW_LINKS` are **not two symmetric constants in one enum**: the first belongs to `LinkOption` for link/attribute/copy APIs; the second belongs to `FileVisitOption` for tree traversal. Do not pass `FOLLOW_LINKS` to `Files.copy`.
- `REPLACE_EXISTING` operates **on the target path during copy/move**; `TRUNCATE_EXISTING` operates **on the contents of the file being opened for writing**. They are not interchangeable.
- `CREATE`/**`CREATE_NEW`** are used when **opening to write/create a file**; `COPY_ATTRIBUTES` is used when **copying a file**; `ATOMIC_MOVE` is used only when **moving**.
- `FileVisitOption` only changes how the tree is traversed. It does not decide which files to copy/delete, does not replace `FileVisitor`, and does not change how `Files.exists` works.

## 9. Common Errors and How to Handle Them

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| `FileAlreadyExistsException` | `CREATE_NEW` on an existing file or `Files.copy` encountering an existing target | Rename, verify business rules, or use `REPLACE_EXISTING` only when overwriting is truly intended. |
| `NoSuchFileException` | Source does not exist, parent directory is missing, or `APPEND` used when the file does not yet exist | Prepare parent directories; to create if missing, consider `CREATE + APPEND`. |
| `IllegalArgumentException` when opening a channel | Invalid option combination, e.g., `READ + APPEND` or `APPEND + TRUNCATE_EXISTING` | Pick a valid combination matching the API and intended behavior. |
| `UnsupportedOperationException` | Provider does not support the specific option | Choose an approach supported by the provider with proper fallback/handling. |
| `AtomicMoveNotSupportedException` | `ATOMIC_MOVE` is unsupported by the file system/provider | Decide explicitly whether a non-atomic fallback is acceptable or fail with an error. |
| `FileSystemLoopException` during walk | `FOLLOW_LINKS` enabled and a symlink cycle was encountered | Handle in `visitFileFailed`; consider not following links or limiting depth. |
| Old data disappears | Default `writeString`/`newOutputStream` truncates the existing file | Use `APPEND` only when appending; use `TRUNCATE_EXISTING` deliberately. |
| `Files.exists` returns `false` even though the path seems to exist | Dangling symlink, access permissions, or indeterminate state | Use `NOFOLLOW_LINKS` if checking the link itself, and still handle errors during the actual operation. |

When performing real I/O, beyond options you must also account for OS permissions, file system providers, concurrently changing symlinks, durability of writes to storage, closing resources, and error recovery. Avoid using options as a substitute for transactions, locking, or security checks.

## 10. Self-Check

1. Why does `OpenOption.READ` fail to compile? **Because `OpenOption` is an interface; use `StandardOpenOption.READ`.**
2. Want to create a log if missing and append if it already exists? **Use `CREATE + APPEND`.**
3. Does `Files.copy(dirA, dirB)` copy all child files? **No; you must walk the tree and copy each entry.**
4. Want to copy the symbolic link itself? **Use `Files.copy(link, target, LinkOption.NOFOLLOW_LINKS)` if supported by the provider.**
5. Want to walk across a link to a directory? **Use `FileVisitOption.FOLLOW_LINKS` in an overload that accepts options.**
6. Is a call to `Files.move(..., ATOMIC_MOVE, REPLACE_EXISTING)` guaranteed to always overwrite the target? **No; with `ATOMIC_MOVE`, other options are ignored and behavior for an existing target depends on the implementation.**
7. Does `SYNC` mean the same thing as `ATOMIC_MOVE`? **No; `SYNC` concerns flushing file updates to storage, whereas `ATOMIC_MOVE` concerns atomicity when changing a file's location.**

## Reference Documentation (JDK 21)

- [OpenOption](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/OpenOption.html)
- [StandardOpenOption](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/StandardOpenOption.html)
- [CopyOption](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/CopyOption.html)
- [StandardCopyOption](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/StandardCopyOption.html)
- [LinkOption](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/LinkOption.html)
- [FileVisitOption](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/FileVisitOption.html)
- [Files](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html)
