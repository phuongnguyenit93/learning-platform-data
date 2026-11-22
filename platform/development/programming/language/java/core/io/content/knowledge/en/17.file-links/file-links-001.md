# Symbolic Links and Hard Links in Java NIO.2

## 1. Objective

In a file system, **the name/path of a file** and **the data object referenced by that name** are two concepts that need to be distinguished. Symbolic links and hard links allow multiple paths to refer to a file, but they do so through two different mechanisms:

- **Hard link**: adds a new name for **the same file object**. Both names share the data and metadata of that object.
- **Symbolic link (symlink)**: a link object that stores **the path of the target**. When accessed by following the link, the operating system/filesystem resolves this path to find the target.

Java supports these operations via `java.nio.file.Path`, `Files`, and `LinkOption`. The API has been available since Java 7; the examples use Java 17+. Actual link creation capability also depends on the operating system, file system, and permissions.

```text
Hard link:
  data.txt -----------+
                      +---- [same file object, same data]
  alias-hard.txt -----+

Symbolic link:
  alias-symbolic.txt --(contains path "data.txt")--> data.txt --> [file object]
```

A symlink is not the same as a Windows `.lnk` shortcut file: it is a path-resolution mechanism of the filesystem.

## 2. Comparison

| Criterion | Hard link | Symbolic link |
|---|---|---|
| Nature | Another name for the same file object | A link object containing the target path |
| Must target exist when created? | Yes | Not necessarily; a broken link can be created |
| When deleting the original target name | Other hard links can still access the content | Symlink may become broken because the target name disappears |
| When writing/modifying file content in place | All hard links see the same new content | Symlink sees the new content if it still resolves to that file |
| When replacing the **file object** at the target name | Old hard link still points to the old object | Symlink usually follows the name to the new object |
| Across different filesystems/volumes | Usually no | Possible if supported by the platform |
| Linking directories | Usually hard links to directories are not allowed | Usually supported, depending on permissions/system |
| Java creation | `Files.createLink` | `Files.createSymbolicLink` |
| Java inspection | `Files.isSameFile` checks if two paths refer to the same file | `Files.isSymbolicLink` checks the link entry |

On Unix, the model is often described using **inodes**: two hard links reference the same inode. This is a useful mental model, though Java NIO.2 does not require every filesystem to use inodes. Once a hard link is created, the "original name" and the "new name" are **two equal names**.

## 3. Hard Link: Different Name, Same File Object

Suppose `a.txt` exists and `b.txt` is created as a hard link to `a.txt`:

1. The filesystem creates a name entry `b.txt` pointing to **the same object** that `a.txt` references; it does not copy all the data.
2. Reading `a.txt` or `b.txt` yields the same content. If new content is written **to the same object** through one name, the content read through the other name also changes.
3. Deleting `a.txt` only removes that name. `b.txt` still references the file object and can still read the data.
4. On POSIX-style filesystems, the object is typically reclaimed when no hard link names remain and no open handles hold it; details depend on the system.

**Distinguishing content modification from file replacement:** a program may create a temporary file and then use `Files.move(temp, a, REPLACE_EXISTING)` to replace **the object pointed to by the name `a.txt`**. In that case, `b.txt` may still reference the old object. Therefore, hard links are **not** an independent backup method or a way to synchronize every type of file update.

### API to create a hard link

```java
Path existing = Path.of("data.txt");
Path alias = Path.of("data-hard.txt");

Files.createLink(alias, existing);
boolean sameObject = Files.isSameFile(existing, alias);
```

This is an **illustrative snippet**, not a standalone program. It assumes `data.txt` already exists, `data-hard.txt` does not yet exist, both names reside on the same filesystem, and the filesystem permits hard links. When creation succeeds, `sameObject` is `true`. The `Files.isSameFile` method checks whether two paths resolve to the same file, **not specifically to detect hard links**: a symlink followed to the same file can also return `true`.

## 4. Symbolic Link: One Path Referencing Another Path

A symlink contains a target path. This path can be **absolute** or **relative**.

```java
Path link = Path.of("logs", "current.log");
Path target = Path.of("2026-10.log");

Files.createSymbolicLink(link, target);
Path storedTarget = Files.readSymbolicLink(link);
```

The snippet above assumes the `logs` directory exists and the system allows symlink creation. With a relative target, `2026-10.log` is resolved **from the directory containing the symlink**, which here is `logs`, not from the working directory when the program accesses it. `readSymbolicLink` returns the exact path stored in the link (in this example, `2026-10.log`), without automatically converting it into an absolute/canonical path.

Symlinks can usually point to a **file** or a **directory**. Content-reading operations such as `Files.readString(link)` follow the symlink to the target. If the target path can no longer be resolved (deleted, renamed, or moved with broken directory relationships), the symlink becomes a **dangling/broken symlink**: the link remains a filesystem entry, but the target cannot be read.

Relative paths are convenient when you need to move an entire directory tree while preserving the relationship between link and target. Absolute paths are easy to understand at a fixed location, but can break when moving the project to another directory/machine.

### Distinguishing whether the symlink exists vs. whether the target exists

```java
Files.isSymbolicLink(link);                    // Checks the link itself
Files.exists(link);                            // Follows the link to the target by default
Files.exists(link, LinkOption.NOFOLLOW_LINKS); // Does not follow the link
Files.readSymbolicLink(link);                  // Gets the stored target path
```

For a broken symlink, `Files.exists(link)` usually returns `false` while `Files.exists(link, NOFOLLOW_LINKS)` returns `true`. However, `Files.exists` can also return `false` when existence cannot be determined due to access issues; it is not a check that guarantees subsequent I/O operations will succeed.

## 5. Runnable Java 17+ Program

The following program creates a temporary directory, writes a file, creates a hard link, attempts to create a symlink, and then deletes one file name. It illustrates the difference between **data still referenced by a hard link** and **a symlink whose target has disappeared**.

Save with the exact filename `FileLinksDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;

public class FileLinksDemo {
    public static void main(String[] args) throws IOException {
        Path folder = Files.createTempDirectory("file-links-");
        Path original = folder.resolve("original.txt");
        Path hard = folder.resolve("alias-hard.txt");
        Path symbolic = folder.resolve("alias-symbolic.txt");

        try {
            Files.writeString(original, "v1", StandardCharsets.UTF_8);
            Files.createLink(hard, original);
            System.out.println("Cùng tệp: "
                    + Files.isSameFile(original, hard));

            Files.writeString(hard, "v2", StandardCharsets.UTF_8);
            System.out.println("Đọc tên gốc: "
                    + Files.readString(original, StandardCharsets.UTF_8));

            boolean symbolicCreated = false;
            try {
                // Relative target: resolved from the directory containing the symlink.
                Files.createSymbolicLink(symbolic, Path.of("original.txt"));
                symbolicCreated = true;
                System.out.println("Là symlink: "
                        + Files.isSymbolicLink(symbolic));
                System.out.println("Path lưu trong symlink: "
                        + Files.readSymbolicLink(symbolic));
            } catch (IOException | UnsupportedOperationException | SecurityException ex) {
                System.out.println("Không tạo được symbolic link trên hệ thống này.");
            }

            // Delete the name original.txt, not the object held by the hard link.
            Files.delete(original);
            System.out.println("Đọc qua hard link: "
                    + Files.readString(hard, StandardCharsets.UTF_8));

            if (symbolicCreated) {
                System.out.println("Mục nhập symlink còn: "
                        + Files.exists(symbolic, LinkOption.NOFOLLOW_LINKS));
                System.out.println("Mục tiêu symlink còn: "
                        + Files.exists(symbolic));
            }
        } finally {
            Files.deleteIfExists(symbolic);
            Files.deleteIfExists(hard);
            Files.deleteIfExists(original);
            Files.deleteIfExists(folder);
        }
    }
}
```

Compile and run in the directory containing the file:

```bash
javac FileLinksDemo.java
java FileLinksDemo
```

If the filesystem allows creating hard links and symbolic links, stdout is:

```text
Cùng tệp: true
Đọc tên gốc: v2
Là symlink: true
Path lưu trong symlink: original.txt
Đọc qua hard link: v2
Mục nhập symlink còn: true
Mục tiêu symlink còn: false
```

Step-by-step explanation:

- `Files.createLink` does not duplicate data; `isSameFile` confirms both names resolve to the same file.
- Writing `"v2"` via `alias-hard.txt` changes the content seen via `original.txt`.
- The symlink stores the relative path `original.txt`; `readSymbolicLink` returns that exact path.
- Deleting `original.txt` only deletes that name, so `alias-hard.txt` can still read `v2`.
- The symlink still exists as an entry, but the target `original.txt` is gone, so checking by following the link fails.

If creating a symbolic link is not permitted, the program prints the line `Không tạo được symbolic link trên hệ thống này.` instead of the three informational lines upon symlink creation and the two symlink check lines at the end. If `Files.createLink` is unsupported or lacks permissions, the program throws an exception before the symlink section; this shows that environmental conditions must be handled in real applications. The example uses a single shared temporary directory to avoid cross-filesystem hard link errors.

## 6. Important API Table

| API | Purpose | Key points to remember |
|---|---|---|
| `Files.createLink(link, existing)` | Creates a hard link | `existing` must exist; new link must not exist yet; usually same filesystem |
| `Files.createSymbolicLink(link, target)` | Creates a symlink storing `target` | `target` does not have to exist yet, but the system must support it |
| `Files.readSymbolicLink(link)` | Reads the path inside a symlink | Returns the stored path, does not automatically resolve to an absolute path |
| `Files.isSymbolicLink(path)` | Checks whether the entry is a symlink | Does not require the target to still exist |
| `Files.isSameFile(a, b)` | Checks whether two paths point to the same file | Follows symlinks when resolving; may throw `IOException` |
| `Files.exists(path, NOFOLLOW_LINKS)` | Checks the entry without following symlinks | Useful for dangling symlinks |
| `Files.readAttributes(path, BasicFileAttributes.class, NOFOLLOW_LINKS)` | Reads attributes of the symlink itself | Can check `isSymbolicLink()` |
| `path.toRealPath()` | Real path, follows symlinks by default | Requires the path to be resolvable, may fail with I/O error |
| `path.toRealPath(NOFOLLOW_LINKS)` | Real path without following symlinks | Differs from `toAbsolutePath()`, which mainly performs syntactic transformation |

`NOFOLLOW_LINKS` here is `LinkOption.NOFOLLOW_LINKS`. To use `BasicFileAttributes`, import `java.nio.file.attribute.BasicFileAttributes`.

### Reading metadata of the link itself

```java
Path link = Path.of("alias-symbolic.txt");

// Follows symlink by default: attributes of the target.
var targetInfo = Files.readAttributes(
        link, java.nio.file.attribute.BasicFileAttributes.class);

// Does not follow symlink: attributes of the symlink entry itself.
var linkInfo = Files.readAttributes(
        link, java.nio.file.attribute.BasicFileAttributes.class,
        LinkOption.NOFOLLOW_LINKS);
```

This is an illustrative snippet and requires the link to exist in the runtime environment. If the target has disappeared, the call reading `targetInfo` may throw `NoSuchFileException`, while the call reading `linkInfo` can still succeed. Specific metadata varies by filesystem/provider.

## 7. Copy, Move, Delete, and Directory Tree Traversal

**Delete:** `Files.delete(symbolic)` deletes **the symlink entry**, not the target it points to; `deleteIfExists` follows the same rule. When deleting a hard link, only that name disappears; the object remains if other names/handles hold it.

**Move:** `Files.move(symbolic, dest)` moves the symlink itself. If the stored target is relative, the symlink's new directory may change the meaning of the path, causing the link to break.

**Copy:** `Files.copy(symbolic, dest)` follows the symlink to copy the target by default; add `LinkOption.NOFOLLOW_LINKS` if you want to copy the symlink object itself (if supported by the provider). Normal copying **does not** mean recursively copying an entire directory tree. `Files.copy(hard, dest)` usually creates a new independent file with the same data, without creating another hard link.

Example of copying the symlink itself (illustrative; source and filesystem conditions must be valid):

```java
Files.copy(
        Path.of("alias-symbolic.txt"),
        Path.of("alias-symbolic-copy.txt"),
        LinkOption.NOFOLLOW_LINKS
);
```

**Directory traversal:** `Files.walk(root)` and `Files.walkFileTree(root, visitor)` do not descend into symbolic links to directories by default. With `FileVisitOption.FOLLOW_LINKS`, traversal may encounter symlink loops; you need to handle `FileSystemLoopException` or corresponding I/O errors. The stream returned by `Files.walk` must be closed (usually via try-with-resources).

## 8. When to Use Which?

- Choose a **symbolic link** when you want a flexible alias path, pointing to a directory, or switching targets by name (for example, a name `current` leading to a release directory). Consider relative vs. absolute targets and the risk of broken links.
- Choose a **hard link** when you need multiple names for the same **file object** within one filesystem and want data to remain accessible through the remaining name after deleting one name. Remember that in-place content updates affect the same underlying data.
- Choose an **independent copy** when you need two pieces of data with separate lifecycles; hard links and symbolic links **do not replace** independent backups.

## 9. System Limitations, Common Errors, and Safety

1. **Cross-filesystem:** hard links usually cannot span volumes/filesystems. On Windows, hard links are common for files on NTFS within the same volume; behavior depends on the filesystem.
2. **Symbolic link permissions:** Windows may require appropriate privileges/system mode (such as Developer Mode), while Unix requires permissions on the relevant directory. Do not assume a link example will run on every machine.
3. **Link already exists:** `createLink` / `createSymbolicLink` do not automatically overwrite an existing name; they may throw `FileAlreadyExistsException`. Do not delete an existing name just to retry without checking data ownership.
4. **Target does not exist:** hard links require an existing target object; symlinks can point to a non-existent path and then become dangling links. Reading content through a broken link usually causes an I/O error.
5. **Path base confusion:** a symlink's relative target is resolved from **the directory containing the link**, not from the current working directory of the application reading it.
6. **Symlink cycles:** a directory link can point back to an ancestor directory, or A → B → A. Following links during tree traversal requires handling cycles to avoid errors/loops.
7. **Race conditions/TOCTOU:** between `Files.exists`, `isSymbolicLink`, and `read/write/delete` operations, another process can replace the link or target. A single existence check **does not guarantee** that the subsequent operation is safe. For untrusted paths, you must control allowed directories, permissions, and appropriate operation APIs.
8. **Exceptions:** `UnsupportedOperationException`, `IOException` (e.g., `AccessDeniedException`, `NoSuchFileException`, or `FileSystemException`), and `SecurityException` can occur depending on the API and environment. Handle them appropriately according to application requirements rather than silently swallowing all errors.

Three easily confused questions: `isSymbolicLink(path)` asks **whether this name itself is a symlink**; `exists(path)` usually asks **whether this path resolves to an existing target**; `isSameFile(a,b)` asks **whether two paths resolve to the same file**. They can produce different results for the same link.

## 10. Thought Exercises and Solutions

**A.** Create a hard link `b.txt` to `a.txt` and then delete `a.txt`. Can `b.txt` be read? **Yes**, once the hard link is created successfully; deleting one name does not delete the object still referenced by the other name.

**B.** Create a symbolic link `b.txt` containing the path `a.txt` and then delete `a.txt`. Why can `Files.exists(b)` be `false` while `Files.exists(b, NOFOLLOW_LINKS)` is `true`? **Because** the first follows the link to the missing target, while the second checks the link entry itself.

**C.** Use a temporary file to **replace the object** at `a.txt`. Will hard link `b.txt`, which shared the same object with `a.txt`, necessarily see the new object? **No**; the hard link remains bound to the old object. A symlink storing the path `a.txt` usually follows to the new object at that path.

**D.** If you want `app/current` to be a symlink to `app/releases/v3` using a relative target, which path should be stored? **`releases/v3`**, because the target is resolved from the directory containing the symlink, which is `app`.

**E.** Is a hard link a backup? **No**, because hard links share the same data object and modifying content through one name can affect all other names. A backup requires a copy/snapshot with an appropriate lifecycle.

## 11. Takeaways

**Hard link = another name for the same file object. Symbolic link = an object containing a path to a target.** In Java NIO.2, distinguish between `createLink`, `createSymbolicLink`, `readSymbolicLink`, `isSymbolicLink`, `isSameFile`, and `NOFOLLOW_LINKS`; always account for permissions, the filesystem, and the possibility of the target changing.
