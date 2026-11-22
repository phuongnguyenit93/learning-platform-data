# Relative Target Paths of Symbolic Links in Java NIO.2

## 1. Objective and Context

A **symbolic link (or symlink)** is a file system entry containing a path that points to another file or directory. When a program opens a symlink to read its content, the operating system usually follows that path to the target object.

A symlink can store an **absolute path** or a **relative path**. This lesson focuses on the question: *If the target is a relative path, what is it relative to, and how does Java NIO.2 create/read/process that path?*

After this lesson, you will be able to:

- Correctly determine the target of a symlink containing `..` or relative path segments.
- Create and inspect symlinks using `java.nio.file.Files` and `Path`.
- Distinguish between the path **stored in the symlink**, the path **combined with the directory containing the symlink**, and the **real** path on the file system.
- Understand why moving a symlink can cause it to lose its target, and handle broken symlink cases.

## 2. Core Rule: Relative to the Directory Containing the Symlink Itself

Suppose we have the following directory tree:

~~~text
workspace/
├── data/
│   └── report.txt
└── links/
    └── latest.txt -> ../data/report.txt
~~~

`latest.txt` is a symlink located in `workspace/links/`. Inside it, it stores the relative path string `../data/report.txt`.

The operating system interprets the target according to this rule:

~~~text
directory_containing_symlink / stored_target_path
= workspace/links/../data/report.txt
= workspace/data/report.txt
~~~

**Decisive point:** A relative target is resolved based on **the parent directory of the symlink** (`workspace/links/`), **not based on the current working directory** (`user.dir`) of the Java program. The target is not interpreted relative to `latest.txt` itself as though the symlink were a directory.

Two independent paths must be distinguished:

| Component | Example | Role |
| --- | --- | --- |
| Path to the symlink | `workspace/links/latest.txt` | Identifies the *link entry* being created or accessed |
| Target path recorded in the symlink | `../data/report.txt` | Identifies the *target object* relative to the directory containing the link |
| Path after combining and normalizing | `workspace/data/report.txt` | Expected location after resolving `..`, not yet synonymous with the file definitely existing |

The path **to the symlink** can be absolute even while the **target path** remains relative. A symlink can also point to a directory instead of a file; the same parent-directory rule applies.

## 3. Creating a Symlink with a Relative Target Path in Java 17+

In Java NIO.2, the main call is:

~~~java
Path link = linksDirectory.resolve("latest.txt");
Path relativeTarget = Path.of("..", "data", "report.txt");
Files.createSymbolicLink(link, relativeTarget);
~~~

- The `link` parameter is where the **symlink entry** is created.
- The `relativeTarget` parameter is the path **stored as the target**. Since `relativeTarget.isAbsolute()` is `false`, the target is interpreted relative to the directory containing `link`.
- `Path.of("..", "data", "report.txt")` uses the separator of the current file system, avoiding hardcoding a separator for a fixed operating system.
- `Files.createSymbolicLink` does not automatically convert a relative path into an absolute one. It can create a link to a non-existent target on supporting systems; successful creation must not be used to conclude that the target exists.

### Complete, Standalone Runnable Example

Save the code under the name `RelativeSymlinkDemo.java`:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.FileSystems;

public class RelativeSymlinkDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("relative-symlink-");
        Path dataDir = root.resolve("data");
        Path linksDir = root.resolve("links");
        Path targetFile = dataDir.resolve("report.txt");
        Path link = linksDir.resolve("latest.txt");

        try {
            Files.createDirectories(dataDir);
            Files.createDirectories(linksDir);
            Files.writeString(targetFile, "Xin chào NIO.2", StandardCharsets.UTF_8);

            // The target path is stored relative to linksDir.
            Path relativeTarget = Path.of("..", "data", "report.txt");
            Files.createSymbolicLink(link, relativeTarget);

            // Read the exact stored target path, without following the symlink.
            Path storedTarget = Files.readSymbolicLink(link);

            // Combine with the symlink's parent directory to deduce the target location.
            Path resolved = link.getParent().resolve(storedTarget).normalize();

            String portableTarget = storedTarget.toString()
                    .replace(FileSystems.getDefault().getSeparator(), "/");

            System.out.println("Stored target: " + portableTarget);
            System.out.println("Target is relative: " + !storedTarget.isAbsolute());
            System.out.println("Resolved matches file: " + resolved.equals(targetFile));
            System.out.println("Content through link: "
                    + Files.readString(link, StandardCharsets.UTF_8));
            System.out.println("Is symbolic link: " + Files.isSymbolicLink(link));
        } finally {
            // Delete the link, then the target file and created directories.
            Files.deleteIfExists(link);
            Files.deleteIfExists(targetFile);
            Files.deleteIfExists(linksDir);
            Files.deleteIfExists(dataDir);
            Files.deleteIfExists(root);
        }
    }
}
~~~

Compile and run in the directory containing the Java file:

~~~bash
javac -encoding UTF-8 RelativeSymlinkDemo.java
java RelativeSymlinkDemo
~~~

With a file system supporting symlinks and an account with permission to create symlinks, stdout is:

~~~text
Stored target: ../data/report.txt
Target is relative: true
Resolved matches file: true
Content through link: Xin chào NIO.2
Is symbolic link: true
~~~

**Result explanation:**

1. `Files.readSymbolicLink(link)` returns a `Path` representing the stored target (`../data/report.txt`); it does not read the content of `report.txt` and does not automatically convert it to an absolute path.
2. `link.getParent().resolve(storedTarget).normalize()` combines the relative target with `linksDir` and simplifies `links/..` to `data/report.txt`. The example uses a known temporary tree, so comparing `equals` with `targetFile` yields `true`.
3. `Files.readString(link, UTF_8)` accesses the content through the symlink; the file system follows the link to `report.txt`.
4. `Files.isSymbolicLink(link)` checks whether the `latest.txt` entry itself is a symlink, regardless of the target file's type.
5. The `finally` block deletes the link separately before deleting the target file. `Files.deleteIfExists(link)` deletes the symlink, **not the content of the target file** the link points to.

The example does not assume a fixed temporary directory name, because `Files.createTempDirectory` generates a different name on each run. Running on some Windows versions requires enabling Developer Mode or appropriate privileges to create symlinks; a file system that does not support this feature can also reject the `createSymbolicLink` call.

## 4. Reading the Target Path and Determining the Referenced Location

There are three easily confused operations:

~~~java
Path stored = Files.readSymbolicLink(link);
Path lexicalDestination = link.getParent().resolve(stored).normalize();
Path realDestination = link.toRealPath();
~~~

| Operation | Result | Does the target need to exist? |
| --- | --- | --- |
| `Files.readSymbolicLink(link)` | The path **stored in the symlink**, which may be relative | Target does not need to exist, but the symlink itself must exist |
| `link.getParent().resolve(stored).normalize()` | Path deduced by combining and lexically simplifying `.`/`..` | No |
| `link.toRealPath()` | Real path resolved via the file system, following symlinks by default | Yes, so a broken link will cause an error |

`normalize()` processes path name components syntactically, **without accessing the file system**; it does not confirm that the object exists, does not resolve intermediate symlinks, and does not prove that two paths point to the same object. When you need to determine whether two paths actually refer to the same existing file, you can use `Files.isSameFile(path1, path2)`; this method accesses the file system and may throw `IOException`.

**Note for a relative `link` path:** `link.getParent()` can return `null`, for example `Path.of("alias.txt")`. In that case, you need to determine the absolute position of the link before getting its parent directory:

~~~java
Path absoluteLink = link.toAbsolutePath().normalize();
Path stored = Files.readSymbolicLink(link);
Path destination = absoluteLink.getParent().resolve(stored).normalize();
~~~

Here `toAbsolutePath()` uses the working directory to determine **the location of the relative symlink itself**. Once that parent directory is determined, **the stored target path** is still interpreted relative to the symlink's parent directory. `toAbsolutePath()` also does not verify that the target exists.

## 5. Broken Symlinks (Dangling/Broken Symlink)

A symlink is broken when the link entry still exists but the referenced target cannot be found (for example, the target file was deleted, renamed, or the link was moved to a different directory).

For example, `workspace/links/latest.txt` still stores `../data/report.txt`, but `workspace/data/report.txt` has been deleted:

- `Files.isSymbolicLink(link)` → `true`: the symlink still exists.
- `Files.readSymbolicLink(link)` → the stored relative path: still readable.
- `Files.exists(link)` → typically `false`: by default, the check follows the symlink to find the target.
- `Files.exists(link, LinkOption.NOFOLLOW_LINKS)` → `true`: checks the symlink entry itself without following to the target.
- `Files.readString(link)` or `link.toRealPath()` → throws `IOException`, typically `NoSuchFileException`, if the target does not exist.

When access permission is denied or the state cannot be determined, `Files.exists` can also return `false`; you should not treat `false` as always meaning "the file does not exist".

When you need to check the link itself, use `LinkOption.NOFOLLOW_LINKS`. For example:

~~~java
import java.nio.file.LinkOption;

// link points to the symlink to be checked.
boolean linkEntryExists = Files.exists(link, LinkOption.NOFOLLOW_LINKS);
boolean destinationAccessible = Files.exists(link);
boolean isLink = Files.isSymbolicLink(link);
~~~

This is a **supplementary illustrative snippet**, using the `link` variable and `Files`, `Path` imports from the full example above; it is not a standalone Java program.

## 6. Moving Directories: Why a Relative Target May Remain Valid or Break

Relative target paths are especially useful when packaging or copying **an entire directory structure** while preserving the relationship between symlinks and targets.

Initial example:

~~~text
app/
├── data/report.txt
└── links/latest.txt -> ../data/report.txt
~~~

If you move the entire `app/` tree elsewhere and **keep the symlink as a link**, the `links/../data` relationship does not change, so the link usually still works without storing an absolute path from the old machine.

Conversely, if you only move `app/links/latest.txt` into `app/links/archive/latest.txt` while keeping the stored target `../data/report.txt`, the deduced location will be:

~~~text
app/links/archive/../data/report.txt
= app/links/data/report.txt
~~~

That is no longer `app/data/report.txt`. Therefore, **moving a symlink on its own** can break the link. For the symlink at `app/links/archive/latest.txt` to point back to `app/data/report.txt`, the appropriate relative path is `../../data/report.txt`.

When copying with Java NIO.2, the behavior must also be specified clearly:

- `Files.copy(sourceLink, destination)` by default **follows the source symlink** and copies the pointed-to object, unless another option is specified.
- `Files.copy(sourceLink, destination, LinkOption.NOFOLLOW_LINKS)` copies **the link itself** via the mechanism supported by the file system provider; the relative target path is preserved with the link, so you must verify the target structure after copying.
- `Files.move(sourceLink, destination)` moves **the link entry**, without automatically rewriting the target path to keep pointing to the object the symlink previously targeted.

Do not assume that copying a directory always preserves symlinks; that depends on the tool, options, and file system.

## 7. Common Mistakes and How to Avoid Them

**Mistake 1 — Interpreting the relative target from `user.dir`.** Which directory the program is run from does not determine how the operating system resolves the stored relative target. Use the directory containing the **symlink** as the origin for computing the target.

**Mistake 2 — Resolving the target against the symlink path itself.** Writing `link.resolve(stored)` treats the symlink name like a directory and usually produces the wrong path. Use `link.getParent().resolve(stored)` (after handling the `getParent() == null` case).

**Mistake 3 — Confusing `normalize()` with real path resolution.** `normalize()` only removes `.`/`..` syntactically; to verify that a path exists and resolve actual symlinks, consider `toRealPath()`, `Files.isSameFile`, and possible I/O errors.

**Mistake 4 — Using `Files.exists(link)` to decide whether a symlink entry is present.** A broken link usually returns `false`. Use `Files.exists(link, LinkOption.NOFOLLOW_LINKS)` to check the link entry and `Files.isSymbolicLink(link)` to identify the entry type.

**Mistake 5 — Assuming creating a symlink means the target exists.** A link can be created before the target file or become broken later. Reading through the symlink can still fail.

**Mistake 6 — Assuming moving a symlink preserves its old target.** A relative target is not automatically recalculated when the symlink changes location. Check the directory relationship and recreate the link with the new relative target if needed.

**Mistake 7 — Ignoring permissions and OS differences.** `Files.createSymbolicLink` can throw `UnsupportedOperationException` if the provider does not support it, `FileAlreadyExistsException` if the symlink name already exists, or `IOException` when permissions/file system disallow it. Some Windows configurations require Developer Mode or appropriate privileges. Check the environment and handle errors instead of assuming every machine permits symlink creation.

**Mistake 8 — Trusting paths from untrusted sources.** A relative target can contain `..` to escape the intended directory; intermediate components can also be symlinks. Lexical checking with `normalize()` alone is **not sufficient** to guarantee the real path resides inside a safe directory. When working with user-controlled data, verify the real object, restrict access permissions, and account for the risk of file system changes between check and use (TOCTOU).

## 8. When Should You Use a Relative Target Path?

Consider a relative target when the link and the target resource belong to the same deployment tree, such as `app/links/latest.txt -> ../data/report.txt`; the structure can be moved to another machine or root path while internal relationships remain intact.

Conversely, if the symlink points to a fixed resource outside the deployment tree, a relative target can make configuration harder to understand or fragile when moving directories. Choose an absolute path or an appropriate configuration mechanism in that case; also keep in mind that absolute paths are often harder to port across environments.

## 9. Self-Check Questions

1. Where does `project/bin/current -> ../config/settings.json` point? **Answer:** `project/config/settings.json`, because the origin is `project/bin/`.
2. If Java is run from `/tmp` while the symlink remains at `project/bin/`, does the relative target change? **No**; only how the symlink itself is located using a relative path in the program can be affected by the working directory.
3. Why can `Files.readSymbolicLink(link)` succeed while `Files.readString(link)` fails? **Because** the first operation reads the path stored in the symlink, whereas the second must access the target object.
4. After moving the symlink from `project/bin/current` to `project/bin/archive/current`, is keeping `../config/settings.json` guaranteed to be valid? **No**; it is now interpreted from `project/bin/archive/` and will look for `project/bin/config/settings.json`, unless a different directory structure makes that path valid.

**Takeaway:** For a relative target, start from **the directory containing the symlink**, combine it with **the stored path**, and distinguish syntactic path calculation from the file system actually following the link.