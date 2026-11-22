# Broken Links and the Difference Between Following / Not Following Links in Java NIO.2

## 1. Objective and Scope

In Java Core I/O, a path (`Path`) can point directly to a file/directory or to a **symbolic link (symlink)**. A symlink is an entry in the file system that stores a path to another entry (the target). When an API **follows a link**, it accesses the target entry; when using `LinkOption.NOFOLLOW_LINKS`, APIs that support this option operate on or read the attributes of the symlink entry itself.

After this lesson, you should be able to distinguish three independent questions: (1) does the symlink entry exist, (2) is the symlink's target accessible, and (3) does a command act on the symlink or on the target. Understanding these three questions helps avoid falsely reporting "file does not exist", copying the wrong data, or mishandling file cleanup.

## 2. Valid Symlinks, Broken Symlinks, and Regular Paths

Example on a file system that supports symbolic links:

```text
project/
├── data.txt                (real file)
├── alias.txt -> data.txt   (valid symlink, target exists)
└── stale.txt -> gone.txt   (broken symlink, target does not exist)
```

- **Valid symlink**: the link entry itself exists, and the target chain it points to resolves to an accessible entry.
- **Broken/dangling symlink**: the link entry itself still exists, but the target path does not resolve to an existing entry; for example, the target was deleted, moved, or a link in the chain points to a missing target.
- **Non-existent path**: no entry exists at that location; different from a broken symlink because a broken symlink still has a link entry to read, move, or delete.
- **Hard link** differs from a symlink: a hard link is another name for the same file object on a supporting file system; deleting one name does not turn the remaining hard link names into broken symlinks.

A `Path` merely represents a path; merely calling `Path.of(...)` or `resolve(...)` does not automatically check existence and does not guarantee that the path is a real file.

## 3. What Do "Follow" and "NOFOLLOW" Actually Change?

Java NIO.2 uses `java.nio.file.LinkOption.NOFOLLOW_LINKS` for **the methods that support this option**. There is no global setting that applies to all `Files` operations. Each API has its own rules.

Consider `alias.txt -> data.txt`:

- `Files.exists(alias)`: by default **follows the link**, asking whether the path resolves to an existing target.
- `Files.exists(alias, LinkOption.NOFOLLOW_LINKS)`: **does not follow the link at the inspected entry**, asking whether the symlink entry exists.
- `Files.readAttributes(alias, BasicFileAttributes.class)`: by default reads attributes of the target.
- `Files.readAttributes(alias, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS)`: reads attributes of the symlink itself, such as `isSymbolicLink() == true`.
- `Files.isSymbolicLink(alias)`: identifies the link entry itself; still returns `true` for a broken symlink if that entry still exists and can be identified.

**Note:** `NOFOLLOW_LINKS` on a single check does not mean all parent components along the entire path cannot be resolved through links, nor does it guarantee safety against the path being modified concurrently.

## 4. Most Important Comparison Table: `exists`, `notExists`, `isSymbolicLink`

Under conditions of having access permissions, a stable file system, and no I/O errors:

| State at `p` | `Files.exists(p)` | `Files.exists(p, NOFOLLOW_LINKS)` | `Files.isSymbolicLink(p)` |
| --- | --- | --- | --- |
| Existing regular file | `true` | `true` | `false` |
| Symlink to an existing target | `true` | `true` | `true` |
| Broken symlink (missing target) | `false` | `true` | `true` |
| Entry at `p` does not exist at all | `false` | `false` | `false` |

The check pair `exists(p) == false` and `exists(p, NOFOLLOW_LINKS) == true` is a **useful indicator** of an unresolvable link. However, never definitively conclude "the target was deleted": missing permissions, file system errors, link cycles, or concurrent modifications can also cause a check to fail.

`Files.notExists(p)` is **not** the logical negation of `Files.exists(p)`. If Java cannot determine existence, both `exists` and `notExists` can return `false`. `Files.notExists(p, NOFOLLOW_LINKS)` checks the absence of the link entry itself, not just the target.

For a broken symlink whose target is definitively determined not to exist, typically:

```java
Files.exists(link);                            // false
Files.notExists(link);                         // true
Files.exists(link, LinkOption.NOFOLLOW_LINKS);  // true
Files.notExists(link, LinkOption.NOFOLLOW_LINKS);// false
Files.isSymbolicLink(link);                    // true
```

The lines above are **illustrative expressions**, assuming the `link` variable is already declared and holds an appropriate path; they are not a standalone Java program.

## 5. Java 17+ Example: Creating a Valid Link, Breaking It, Then Inspecting It

Create the file `DanglingLinkDemo.java`:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;

public class DanglingLinkDemo {
    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("java-link-");
        Path target = dir.resolve("data.txt");
        Path link = dir.resolve("shortcut.txt");

        try {
            Files.writeString(target, "Java NIO");
            // Store target relative to the directory containing the symlink:
            Files.createSymbolicLink(link, target.getFileName());

            System.out.println("target before = " + Files.exists(target));
            System.out.println("follow before = " + Files.exists(link));
            System.out.println("nofollow before = "
                    + Files.exists(link, LinkOption.NOFOLLOW_LINKS));

            Files.delete(target); // Delete only the target; symlink remains

            System.out.println("target after = " + Files.exists(target));
            System.out.println("follow after = " + Files.exists(link));
            System.out.println("nofollow after = "
                    + Files.exists(link, LinkOption.NOFOLLOW_LINKS));
            System.out.println("is symlink = " + Files.isSymbolicLink(link));
            System.out.println("stored target = " + Files.readSymbolicLink(link));
        } finally {
            // Delete the link without following it to delete the target.
            Files.deleteIfExists(link);
            Files.deleteIfExists(target);
            Files.deleteIfExists(dir);
        }
    }
}
```

Run in the directory containing the source file, using JDK 17+:

```bash
javac DanglingLinkDemo.java
java DanglingLinkDemo
```

Output when the file system supports symlinks and symlink creation is permitted:

```text
target before = true
follow before = true
nofollow before = true
target after = false
follow after = false
nofollow after = true
is symlink = true
stored target = data.txt
```

**Explanation:** `Files.createSymbolicLink(link, target.getFileName())` stores the string `data.txt` in the link entry. Initially both the link and the target exist. After `Files.delete(target)`, the `shortcut.txt` entry still exists, but checking by following the link can no longer find the target file. `readSymbolicLink` can still read the stored target path.

This program requires a file system that supports symlinks and permission to create them. On some Windows configurations, creating symlinks may require appropriate privileges or Developer Mode; on other file systems/providers, `UnsupportedOperationException` or `IOException` may occur. If link creation fails, do not expect the stdout above.

## 6. Reading Attributes Accurately: Target or Link Entry?

`BasicFileAttributes` supports `isRegularFile()`, `isDirectory()`, `isSymbolicLink()`, `size()`, and many other attributes. The same symlink path can return different attributes depending on whether the link is followed.

```java
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;

// The lines below are inside a method that may throw IOException.
// Assume link is a symlink to an existing regular file.
Path link = Path.of("shortcut.txt");

BasicFileAttributes ofTarget =
        Files.readAttributes(link, BasicFileAttributes.class);
BasicFileAttributes ofLink =
        Files.readAttributes(link, BasicFileAttributes.class,
                LinkOption.NOFOLLOW_LINKS);

System.out.println(ofTarget.isRegularFile()); // true if the target is a regular file
System.out.println(ofTarget.isSymbolicLink()); // false when reading target attributes
System.out.println(ofLink.isSymbolicLink());   // true when reading the symlink itself
```

This is an **illustrative snippet placed inside a method**, not a standalone Java file. If the symlink is broken, the call reading **target** attributes usually throws `NoSuchFileException`; reading **link** attributes with `NOFOLLOW_LINKS` can still succeed. Do not deduce the content length of the real file from `size()` obtained on the link itself: the link size and how it is reported depend on the file system provider.

The checks `Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS)` and `Files.isDirectory(path, LinkOption.NOFOLLOW_LINKS)` are typically `false` for a symlink, even when its target is a file or directory respectively. By default, these checks usually follow the link.

## 7. Reading the Link Value and Resolving Relative Targets

`Files.readSymbolicLink(link)` returns **the path stored inside the symlink**, does not automatically open the target, does not guarantee the target exists, and does not force returning an absolute path.

For example, the entry `/work/reports/latest.txt` contains the target `../archive/report.txt`. The stored path is `../archive/report.txt`, which must be interpreted relative to **the directory containing the link**, not the current working directory.

```java
Path link = Path.of("/work/reports/latest.txt");
Path storedTarget = Files.readSymbolicLink(link);
Path candidate = link.toAbsolutePath().getParent()
        .resolve(storedTarget)
        .normalize();
```

The snippet above illustrates resolving from the link's parent directory; it needs to be inside a method that handles `IOException` (and only runs against a symlink that actually exists). `normalize()` only processes lexical components such as `..`, does not prove the target actually exists, does not follow additional links, and does not guarantee the path lies inside a trusted directory. If the stored value is an absolute path, `resolve` according to provider rules will use that absolute path on the default file system.

`link.toRealPath()` normally requires the target to be accessible and resolves links. `link.toRealPath(LinkOption.NOFOLLOW_LINKS)` handles links according to the API's non-following mode, with existence requirements and differences by provider; do not substitute it for `readSymbolicLink` when you need to read **the original target string**.

## 8. Copy, Move, Delete: Each Operation Has Its Own Rules

| Operation | With a valid symlink | When the symlink is broken |
| --- | --- | --- |
| `Files.copy(link, dst)` | Follows the source link by default, copying the **target** (if target is a file: file content) | Usually fails because the target cannot be read |
| `Files.copy(link, dst, LinkOption.NOFOLLOW_LINKS)` | Copies **the symlink itself** if supported | Can copy a broken link as a link; the target string may still be invalid at the new location |
| `Files.move(link, dst)` | Moves/renames **the symlink itself**, does not move target data | Can still move the broken symlink entry |
| `Files.delete(link)` / `Files.deleteIfExists(link)` | Deletes **the symlink entry**, does not delete the target file/directory | Deletes the broken symlink entry if permissions and conditions allow |
| `Files.readSymbolicLink(link)` | Returns the stored target path | Can still read the stored link value |

Note when moving or copying a symlink with a **relative target** to a new directory: the stored target value does not necessarily change accordingly, so the new link may break even if the original link was valid. Do not mechanically add `NOFOLLOW_LINKS` to every operation: `move` and `delete` already have rules for operating on the symlink itself; some APIs do not accept this option.

For `Files.copy`, the option **at the source** determines whether to follow or not follow the link; if the destination location already exists as a symlink, `REPLACE_EXISTING` affects **the destination link entry**, without automatically deleting the file it points to. Copying is not necessarily an atomic operation; when `IOException` occurs, the new destination may be incomplete.

## 9. Directory Tree Traversal: Do Not Follow by Default, Follow Only When Explicitly Requested

- `Files.walk(root)` and `Files.walkFileTree(root, visitor)` **do not follow symbolic links** by default when traversing a tree.
- `Files.walk(root, FileVisitOption.FOLLOW_LINKS)` or `Files.walkFileTree(root, Set.of(FileVisitOption.FOLLOW_LINKS), maxDepth, visitor)` explicitly follows directory links.
- Following links can lead the program outside the intended directory branch, loop over the same data region, or encounter cycles. In `walkFileTree`, cycles may be reported via `FileSystemLoopException` in `visitFileFailed`.
- When allowing link following, you must define policies for targets outside the tree, broken targets, access permissions, maximum depth, and I/O errors; for scanners or deletion operations, `FOLLOW_LINKS` should not be enabled unconditionally.

Specifically, `LinkOption.NOFOLLOW_LINKS` (in attribute checks, copy, etc.) is a **different enum** from `FileVisitOption.FOLLOW_LINKS` (in tree traversal). The two option types are designed for distinct methods and behaviors.

## 10. Diagnosing a Path Suspected of Being a Broken Link

A controlled investigation procedure:

1. Read **entry** attributes with `Files.readAttributes(path, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS)`. If it throws `NoSuchFileException`, at check time the entry could not be found; if it throws `AccessDeniedException` or another I/O error, preserve the error information rather than turning it into a "does not exist" conclusion.
2. If `attrs.isSymbolicLink()` is `false`, this is not a symbolic link at the final position of the path; continue handling according to the corresponding file type.
3. If it is indeed a symlink, read the target string using `Files.readSymbolicLink(path)` for diagnostic purposes.
4. Read **target** attributes with `Files.readAttributes(path, BasicFileAttributes.class)`. Success indicates the path was resolvable at read time. `NoSuchFileException` is evidence of a missing target/resolution chain at that moment; `AccessDeniedException`, `FileSystemLoopException`, or other `IOException` require separate handling.
5. Decide the action according to business requirements: keep the link, report an error, update the link via a controlled operation, or delete **the link itself** if policy allows.

Example of the core handling snippet, placed inside a method declaring `throws IOException`:

```java
import java.io.IOException;
import java.nio.file.AccessDeniedException;
import java.nio.file.FileSystemLoopException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;

Path path = Path.of("shortcut.txt");
BasicFileAttributes linkAttrs = Files.readAttributes(
        path, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);

if (linkAttrs.isSymbolicLink()) {
    System.out.println("Stored: " + Files.readSymbolicLink(path));
    try {
        BasicFileAttributes targetAttrs =
                Files.readAttributes(path, BasicFileAttributes.class);
        System.out.println("Resolved target; directory = "
                + targetAttrs.isDirectory());
    } catch (NoSuchFileException e) {
        System.out.println("Target path missing at inspection time");
    } catch (AccessDeniedException e) {
        System.out.println("Cannot read target due to access restrictions");
    } catch (FileSystemLoopException e) {
        System.out.println("Detected symbolic-link cycle");
    } catch (IOException e) {
        System.out.println("Other resolution/I-O error: " + e.getMessage());
    }
}
```

**Limitations:** specific exceptions depend on the OS/provider, `FileSystemLoopException` is not guaranteed to appear for every cycle, and the entry may be modified between two calls. Catch appropriate errors directly at the actual operation. This example does not automatically delete or "fix" the link.

## 11. Common Mistakes and How to Fix Them

| Mistake | Why it is wrong | How to handle |
| --- | --- | --- |
| `!Files.exists(link)` means the link itself disappeared | Follows to the target by default; a broken link still exists | Add the check `Files.exists(link, NOFOLLOW_LINKS)`; read link attributes to confirm |
| `!Files.exists(path)` is equivalent to `Files.notExists(path)` | Undetermined state can make both return `false` | Distinguish "does not exist" from "undetermined"; check errors during operation |
| `Files.isRegularFile(link, NOFOLLOW_LINKS)` must be `true` if the link points to a file | NOFOLLOW inspects the symlink itself, not the target's type | Use the default attribute check if you truly need the target's type |
| `readSymbolicLink` returns an absolute canonical path or confirms the target is valid | The API returns the stored path string, which may be relative or broken | Resolve against the directory containing the link and attempt to access the target separately |
| Adding `NOFOLLOW_LINKS` to every `Files.*` call | Not every API accepts this option | Check each API's signature and contract |
| `Files.move(link, dst)` will move the real file behind it | Move operates on the symlink entry itself | Move the real file via the target path if that is the intent |
| Deleting a link deletes the target data | `Files.delete(link)` deletes the link entry | Only delete the target when explicitly specified and controlled |
| Copying or moving a relative link always preserves the right target | The new link has a different relative base directory | Re-verify the target after copying/moving |
| Checking `exists` and trusting the result forever | There is a race between check and use (TOCTOU) | Perform the required operation and handle `IOException`; use safer APIs when security is required |

## 12. Security and Portability Issues

- **TOCTOU (time of check to time of use):** the symlink or target can change between `exists` and `readAttributes`, `copy`, `open`, or `delete`. The read state is only true at the moment of observation; do not use `exists` as the sole security condition.
- **Do not treat `normalize()` alone as safe:** it only normalizes syntax; it does not prevent a symlink from taking a path outside an allowed directory. For user-controlled file areas, verify access boundaries and consider race-resistant APIs such as `SecureDirectoryStream` if supported by the provider.
- **OS/provider:** creating or copying symlinks may be unsupported or permission-restricted; various file systems have their own rules. On Windows, symbolic links, junctions, and `.lnk` shortcuts are not three identical concepts. Check with NIO.2 rather than inferring from file extensions.
- **Proper error handling:** distinguish `NoSuchFileException`, `AccessDeniedException`, link cycles, and other I/O errors; a boolean check is usually insufficient to identify the cause.
- **Do not follow links when traversing/deleting untrusted data** unless required by specification and clear boundaries are in place.

## 13. Application Scenarios and Self-Check

**Scenario A — cleaning up broken shortcuts.** Read the link entry itself using `NOFOLLOW_LINKS`, verify `isSymbolicLink()`, attempt to resolve the target, and distinguish a missing target from access errors. When cleanup is permitted, call `Files.delete(link)`; do not accidentally delete the target file.

**Scenario B — backing up a directory tree while preserving link structure.** Traverse the tree without following links, and where a symlink must be copied, use `Files.copy(source, destination, LinkOption.NOFOLLOW_LINKS)` if supported by the provider. After copying, note that relative links may change meaning at the new location.

**Scenario C — summarizing directory contents by real targets.** If you intentionally want to follow links to directories, use `FOLLOW_LINKS` when traversing, limit depth, and handle cycles and access errors; accept that a single file may be seen through multiple paths.

Answer for yourself:

1. Can `Files.exists(brokenLink)` be `false` even though `Files.isSymbolicLink(brokenLink)` is `true`? **Yes**, because one asks about the target while the other asks about the link entry.
2. Is `Files.notExists(path)` always equal to `!Files.exists(path)`? **No**, because of the undetermined state.
3. Want to get metadata of a broken link? **Read `BasicFileAttributes` with `NOFOLLOW_LINKS`**.
4. Want to know verbatim what a symlink points to? **`Files.readSymbolicLink(path)`**, then resolve relatively if needed; do not treat it as confirmation that the target exists.
5. What does `Files.delete(symlink)` delete? **The symlink entry**, not the content it points to.

## References

- Java SE 17 `java.nio.file.Files`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html
- Java SE 17 `java.nio.file.LinkOption`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/LinkOption.html
- Java SE 21 `java.nio.file.FileVisitOption`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/FileVisitOption.html
- Oracle/dev.java, Walking the File Tree: https://dev.java/learn/api/io/java-io/file-system/walking-tree/
