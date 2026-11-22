# Creating, Reading, and Detecting Symbolic Links in Java NIO.2

## 1. What Is a Symbolic Link?

A **symbolic link (symlink)** is an entry in a file system that contains a path referencing another file or directory. When a program opens the link to read its content, the operating system usually resolves the link and accesses the target object. A link can point to a file, a directory, or another link.

For example, the `docs` directory contains `guide.txt` and `latest.txt`, which is a symlink whose target content is `guide.txt`:

~~~text
docs/
├── guide.txt
└── latest.txt -> guide.txt
~~~

In this example, `latest.txt` is still a separate entry in the file system. It does not contain a copy of `guide.txt`'s content. Deleting `latest.txt` normally deletes only the link; renaming or deleting `guide.txt` can leave the link unable to find its target.

Brief distinction:

| Type | Characteristics |
| --- | --- |
| Regular file | Contains the actual file data. |
| Symbolic link | Contains a path to the target object; can point across directories or to a non-existent target. |
| Hard link | Another name referencing the same file object on a supporting file system; does not store a target path the way a symlink does. |

The modern APIs for working with symbolic links belong to `java.nio.file`, primarily `Path`, `Files`, and `LinkOption`.

## 2. Three Core Operations

| Purpose | API | Result and Key Points |
| --- | --- | --- |
| Create a link | `Files.createSymbolicLink(link, target)` | Creates the `link` entry containing the `target` path. Does not create a copy of the data. |
| Read the stored target path | `Files.readSymbolicLink(link)` | Returns a `Path`; does not read the target file's content and does not automatically convert to an absolute path. |
| Detect if a path is a symlink | `Files.isSymbolicLink(path)` | Returns `true` when the indicated entry itself is a symbolic link, even if the target is missing. |

Both `link` and `target` parameters are `Path` objects. For a relative target path, resolution is interpreted **relative to the parent directory of the link itself**, not necessarily relative to the current working directory.

Example:

~~~java
Path link = Path.of("/app/aliases/current.txt");
Path target = Path.of("../data/report.txt");
Files.createSymbolicLink(link, target);
~~~

The link at `/app/aliases/current.txt` references `/app/data/report.txt` when resolved. This Unix-style path example illustrates the rule; on Windows, use paths appropriate for the running file system.

**Important:** `Files.createSymbolicLink` does not require the target object to exist at creation time. Therefore, successful creation does not guarantee that reading content through the link will succeed.

## 3. Complete Example: Creating, Reading, and Detecting a Link

Save the code below as `SymbolicLinkDemo.java`. The program creates a temporary directory, writes a real file, creates a relative link, checks the status, and then deletes the real file to observe a **dangling/broken symbolic link**. The `finally` block cleans up the entries created by the example.

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;

public class SymbolicLinkDemo {
    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("symbolic-link-demo-");
        Path realFile = dir.resolve("data.txt");
        Path link = dir.resolve("shortcut.txt");

        try {
            Files.writeString(realFile, "Java NIO");

            // "data.txt" is resolved from the directory containing shortcut.txt.
            Files.createSymbolicLink(link, Path.of("data.txt"));

            System.out.println("isSymbolicLink=" + Files.isSymbolicLink(link));
            System.out.println("storedTarget=" + Files.readSymbolicLink(link));
            System.out.println("content=" + Files.readString(link));
            System.out.println("existsFollow=" + Files.exists(link));
            System.out.println("existsNoFollow=" +
                    Files.exists(link, LinkOption.NOFOLLOW_LINKS));

            // Delete the target, while keeping the symbolic link entry.
            Files.delete(realFile);
            System.out.println("afterDeleteIsLink=" + Files.isSymbolicLink(link));
            System.out.println("afterDeleteFollow=" + Files.exists(link));
            System.out.println("afterDeleteNoFollow=" +
                    Files.exists(link, LinkOption.NOFOLLOW_LINKS));
        } finally {
            Files.deleteIfExists(link);
            Files.deleteIfExists(realFile);
            Files.deleteIfExists(dir);
        }
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac SymbolicLinkDemo.java
java SymbolicLinkDemo
~~~

When the file system and user permissions allow creating symbolic links, the output is:

~~~text
isSymbolicLink=true
storedTarget=data.txt
content=Java NIO
existsFollow=true
existsNoFollow=true
afterDeleteIsLink=true
afterDeleteFollow=false
afterDeleteNoFollow=true
~~~

Explanation of each output group:

1. `isSymbolicLink=true`: `shortcut.txt` itself is a symbolic link.
2. `storedTarget=data.txt`: `readSymbolicLink` returns the **stored** relative path. It does not return the content `Java NIO`.
3. `content=Java NIO`: `Files.readString(link)` follows the link by default to read the data of `data.txt`.
4. Before deleting the target, checking `Files.exists` both when following and not following the link returns `true`.
5. After deleting the target, the link still exists, so `isSymbolicLink` and `exists(..., NOFOLLOW_LINKS)` remain `true`. Conversely, `exists(link)` follows the link to the target by default, fails to find it, and returns `false`.

If the environment does not support symbolic links or lacks creation permissions, `createSymbolicLink` may throw an exception; that is an environment limitation, not a variant of the output shown above.

## 4. Relative, Absolute, and Real Paths

`Files.readSymbolicLink(link)` reads **the target path recorded in the link**, which may be relative or absolute. If you need to determine the path that a relative target refers to based on the link's location, handle it explicitly:

~~~java
Path storedTarget = Files.readSymbolicLink(link);
Path referencedPath = storedTarget.isAbsolute()
        ? storedTarget
        : link.getParent().resolve(storedTarget).normalize();
~~~

This is a **syntactic path construction/normalization** operation. `normalize()` handles components such as `.` and `..`; it does not guarantee that the object exists and does not replace actual link or permission checks.

If you want to resolve to an existing object:

~~~java
Path actualPath = link.toRealPath();
~~~

`toRealPath()` resolves symbolic links by default and requires the path to be accessible, so it can throw `IOException` when the link is broken, the target does not exist, or access permissions disallow it. Passing `LinkOption.NOFOLLOW_LINKS` changes link-following behavior; do not use it arbitrarily if the goal is to find the actual target file.

Choose a relative target when a group of files will be moved together while keeping reference relationships intact. An absolute target is convenient when the target location is fixed, but easily breaks when moving the project to another machine.

## 5. Follow the Link or Inspect the Link Itself?

This is the most error-prone distinction in I/O operations.

| Expression | When `link` points to an existing file | When `link` is a symlink whose target is missing |
| --- | --- | --- |
| `Files.isSymbolicLink(link)` | `true` | `true` |
| `Files.exists(link)` | `true` | `false` in the typical case |
| `Files.exists(link, NOFOLLOW_LINKS)` | `true` | `true` if the link itself still exists and can be checked |
| `Files.isRegularFile(link)` | `true` if the target is a regular file | `false` |
| `Files.isRegularFile(link, NOFOLLOW_LINKS)` | `false` because the inspected entry is a link | `false` |
| `Files.readSymbolicLink(link)` | Returns the stored path | Still returns the stored path |
| `Files.readString(link)` | Reads the target content | Usually throws `NoSuchFileException` |

`LinkOption.NOFOLLOW_LINKS` means that an operation supporting this option inspects the link itself instead of automatically following it. It is not a global configuration of `Files`; each method has its own parameter set and behavior.

When you need to read metadata about the link itself:

~~~java
import java.nio.file.attribute.BasicFileAttributes;

BasicFileAttributes attrs = Files.readAttributes(
        link, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
System.out.println(attrs.isSymbolicLink());
~~~

This code snippet is an **illustrative fragment**, using a `link` variable already present in the program; if the link does not exist or metadata cannot be read, `readAttributes` can throw `IOException`.

Note: `Files.exists(path) == false` **does not by itself prove** the entry is completely absent; certain I/O errors or access permissions also prevent the API from determining existence. When accurate error handling is needed, perform the desired operation and catch the appropriate exception rather than relying solely on a prior existence check.

## 6. Common Errors and How to Handle Them

- **Using a relative path with the wrong base:** `Path.of("data.txt")` stores a target relative to the directory containing the link. If the link resides in another directory, you must choose the appropriate number of `..` segments or directory structure.
- **Confusing reading a symlink with reading content:** `Files.readSymbolicLink` returns the stored `Path`; `Files.readString`, `Files.newInputStream`, and standard file-opening operations can follow the link.
- **Using `Files.exists(link)` to assert the link is gone:** a broken link still has a link entry. Check `Files.isSymbolicLink(link)` or `Files.exists(link, NOFOLLOW_LINKS)` when asking about that entry itself.
- **Creating a link at an existing name:** `Files.createSymbolicLink` does not overwrite an existing `link` path; it usually throws `FileAlreadyExistsException`. Choose another name or handle the existing state intentionally.
- **Assuming every environment supports symlinks:** the file system, access permissions, Windows configuration, and security policies can block link creation; `UnsupportedOperationException` or `IOException` (such as `FileSystemException`) can occur. On some Windows configurations, creating symlinks requires appropriate privileges or Developer Mode; check the actual machine policy.
- **Calling `readSymbolicLink` on a regular file:** the method may throw `NotLinkException`. Checking the entry type beforehand makes the interface clearer, but does not eliminate the possibility of concurrent changes between checking and acting.
- **Accidentally deleting or copying the wrong object:** `Files.delete(link)` deletes the symlink entry itself, not the target; `Files.copy(link, destination)` follows the link by default to copy the target object, whereas using `NOFOLLOW_LINKS` requests copying the link itself (if the provider supports it). `Files.move` when the source is a symlink moves the link entry.
- **Forgetting to handle circular links:** when traversing a tree with `Files.walkFileTree`, symlinks are not followed by default; enabling `FileVisitOption.FOLLOW_LINKS` can encounter link cycles and throw `FileSystemLoopException`. Only enable it when you truly need to traverse into targets.

## 7. Security Considerations When Operating on Untrusted Paths

A symbolic link can redirect a read/write operation to a location outside the directory you intend to process. If an application accepts file names from users or works in a directory that can be modified by other processes, you must design clear path rules and access controls. Simply concatenating path strings or calling `normalize()` is not enough to ensure the final path stays within the allowed area, because a symlink can change the actual destination.

In particular, a sequence like "check not a symlink → open/write file" can suffer from a **race condition** if another actor replaces that entry between the two steps (TOCTOU). For sensitive data, consider operations tied to a secure directory such as `SecureDirectoryStream` when supported by the provider, file system permissions, and appropriate file-opening mechanisms. Do not treat a single `isSymbolicLink` call as a complete safeguard.

## 8. Self-Check Knowledge Questions

1. If `docs/current.txt` stores the target `../backup/report.txt`, from which directory is the target interpreted? **From the `docs` directory containing `current.txt`**, so the syntactically corresponding path is `backup/report.txt` at the same level as `docs`.
2. A symlink remains on disk while its target has been deleted: which API detects that the link is still present? **`Files.isSymbolicLink(link)`** or **`Files.exists(link, LinkOption.NOFOLLOW_LINKS)`** when metadata is accessible.
3. Does `Files.readSymbolicLink(link)` read the target file's content? **No.** It returns the target `Path` stored in the link.
4. What do you use to read content through a valid link? **A content-reading operation such as `Files.readString(link)`**; by default, this operation follows the link to the target.
5. Why can `Files.exists(link)` be `false` while `Files.exists(link, NOFOLLOW_LINKS)` is `true` for the same link? **Because the first check follows the link to the missing target, whereas the second check inspects whether the link entry itself still exists.**

**Takeaway:** `createSymbolicLink` creates a reference path, `readSymbolicLink` reads the stored target, and `isSymbolicLink` identifies a link entry. When checking existence or metadata, decide clearly whether you care about **the link itself** or **the target object**.