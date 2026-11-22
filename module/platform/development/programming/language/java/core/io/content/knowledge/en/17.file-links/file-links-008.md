# Link Cycles and Limits When Traversing File Trees in Java NIO

When traversing a directory tree, every directory appears to lead to subdirectories. However, a **symbolic link** (abbreviated as symlink) can point to a directory already visited, to one of its ancestors, or to a branch outside the starting directory. If a program follows links without control, it can loop, process duplicate data, escape the intended scope, or consume excessive resources.

Java NIO.2 provides two important mechanisms: **choosing whether to follow symbolic links** and **limiting traversal depth**. With the `Files.walkFileTree` API, Java also detects certain link cycles and reports them to `FileVisitor` for handling.

## 1. Understanding Links and Link Cycles

A symbolic link is a file system entry containing a reference to a target path. It can point to a file, a directory, a non-existent target, or a path outside the tree being traversed. For example:

```text
project/
├── docs/
│   ├── guide.txt
│   └── back -> ../        # symlink pointing back to project/
└── output/
```

If we follow `docs/back`, from `project/docs` we return to `project`, and can then enter `docs/back` again. This is a **link cycle**.

Three situations must be distinguished:

- **Link cycle:** The path being traversed leads back to an *ancestor directory on the same current traversal branch*. For example, `docs/back -> ../`. When symlink following is enabled, `walkFileTree` detects this cycle and passes a `FileSystemLoopException` to `visitFileFailed`.
- **Duplicate traversal without forming a cycle on the current branch:** Two different symlinks both point to the same directory. `walkFileTree`'s cycle detection does not promise to eliminate all duplicate visits; a directory can still be processed multiple times via different branches.
- **Link escaping outside the starting tree:** For example, `project/external -> /other/data`. This is not necessarily a cycle, but it can cross business or security boundaries if symlink following is enabled.

A **hard link** is another path name referencing the same file object; it differs from a symlink. On common file systems, hard links to directories are usually forbidden, so the cycle problem during directory traversal primarily involves symbolic links, mount points, and ways the file system re-presents a location. Avoiding symlinks should not be treated as a mechanism to deduplicate all files.

## 2. Default Behavior of Java NIO

`Files.walkFileTree(start, visitor)` traverses from `start` with the default behavior of **not following symbolic links** and an API-level maximum depth of `Integer.MAX_VALUE`. `Files.walk(start)` also does not follow symlinks unless `FileVisitOption.FOLLOW_LINKS` is passed.

| Configuration | When encountering a symlink to a directory | Consequence |
| --- | --- | --- |
| Without `FOLLOW_LINKS` (default) | Treats the symlink as a file entry visited via `visitFile`, without descending into the target | Avoids cycles caused by following that symlink |
| With `FOLLOW_LINKS` | Attempts to read attributes and traverse the target directory | May traverse duplicates or escape the root; cycles on the current branch are reported via `FileSystemLoopException` |
| With or without following links, plus `maxDepth` | Descends only to the specified depth | Limits nesting depth, does not limit the number of entries at each level |

Example of the two corresponding calls:

```java
// Do not follow symbolic links, limit to depth 3.
Files.walkFileTree(root, EnumSet.noneOf(FileVisitOption.class), 3, visitor);

// Follow symbolic links, also descend only to depth 3.
Files.walkFileTree(root, EnumSet.of(FileVisitOption.FOLLOW_LINKS), 3, visitor);
```

These are **illustrative snippets**, which must be placed in a program with `root` of type `Path`, `visitor` of type `FileVisitor<Path>`, and appropriate imports. The full program is in Section 5.

Note: `Files.isSymbolicLink(path)` checks the link entry itself. Meanwhile, `attrs.isSymbolicLink()` reflects the attribute set read by the traversal operation; when `FOLLOW_LINKS` is enabled, the attribute set may belong to **the target object**, so the two checks do not always yield the same result.

## 3. How Does the `maxDepth` Limit Work?

Depth is measured from the `start` path:

- **Depth 0:** `start` itself.
- **Depth 1:** Direct child entries.
- **Depth 2:** Grandchild entries; and so on.

For the tree `project/docs/chapters/intro.md`, if `project` is the root, then `docs` is at depth 1, `chapters` is at depth 2, and `intro.md` is at depth 3. When `maxDepth = 2`, Java does not traverse to `intro.md`.

An easily misunderstood detail of `walkFileTree`: **a directory sitting right at level `maxDepth` is passed to `visitFile`, rather than calling `preVisitDirectory` and opening its child entries**. Similarly, `maxDepth = 0` passes the root itself to `visitFile`, even when the root is a directory. Therefore, code inside `visitFile` should not assume every path it receives is a regular file.

The `maxDepth` parameter must be non-negative. A small value helps avoid going too deep, but does not stop a directory at depth 1 from containing millions of entries. It is also **not** a limit on runtime, total file count, bytes read, or a tool to prevent symlinks from escaping the root.

## 4. How Are Cycles Reported and Handled?

When `FOLLOW_LINKS` is present, `walkFileTree` checks a directory before descending to detect whether it matches an ancestor on the current branch. Java may use `fileKey` from file attributes or compare file identity when needed. If a cycle is detected, the API **does not recurse infinitely through that link**; it calls:

```java
visitFileFailed(Path file, IOException exc)
```

with `exc` of type `FileSystemLoopException`. This is where the program decides whether to log and continue, or stop.

Values of `FileVisitResult`:

| Result | Meaning in `FileVisitor` |
| --- | --- |
| `CONTINUE` | Continue traversal according to current rules |
| `SKIP_SUBTREE` | When returned from `preVisitDirectory`, skip the child entries of that directory |
| `SKIP_SIBLINGS` | Skip remaining sibling entries at the relevant level |
| `TERMINATE` | Terminate the entire traversal |

You should only intentionally ignore `FileSystemLoopException` if application policy permits. Do not write `visitFileFailed(...){ return CONTINUE; }` for **every** `IOException`: permission errors, I/O errors, or disappearing directories must be reported or intentionally handled, otherwise result data may be incomplete without the user knowing.

For broken symbolic links (non-existent target) or inaccessible targets, behavior requires careful handling: when link following is enabled and target attributes cannot be read, the API may attempt to read attributes of **the link itself** and call `visitFile`; do not assume every broken link goes to `visitFileFailed`. If you need to distinguish clearly, check `Files.isSymbolicLink(path)` and the target existence/access policy at processing time.

## 5. Compilable and Runnable Java 17+ Program

The program below lets the runner choose the depth limit and toggle following symbolic links. It prints labels `DIR`, `DIR_LIMIT`, `FILE`, `LINK`, and `LOOP` to make the behavior easy to observe. `FileSystemLoopException` is recorded and the cycle path is skipped; other I/O errors are rethrown so the runner knows the traversal is incomplete.

Create the file **`TreeLinkWalk.java`**:

```java
import java.io.IOException;
import java.nio.file.FileSystemLoopException;
import java.nio.file.FileVisitOption;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.EnumSet;

public final class TreeLinkWalk {
    private TreeLinkWalk() {}

    public static void main(String[] args) throws IOException {
        if (args.length < 1 || args.length > 3) {
            System.out.println("Usage: java TreeLinkWalk <root> [maxDepth] [followLinks]");
            return;
        }

        Path root = Path.of(args[0]).toAbsolutePath().normalize();
        int maxDepth = args.length >= 2 ? Integer.parseInt(args[1]) : 3;
        if (maxDepth < 0) {
            throw new IllegalArgumentException("maxDepth must be >= 0");
        }
        if (args.length == 3
                && !args[2].equalsIgnoreCase("true")
                && !args[2].equalsIgnoreCase("false")) {
            throw new IllegalArgumentException("followLinks must be true or false");
        }

        boolean followLinks = args.length == 3 && Boolean.parseBoolean(args[2]);
        EnumSet<FileVisitOption> options = followLinks
                ? EnumSet.of(FileVisitOption.FOLLOW_LINKS)
                : EnumSet.noneOf(FileVisitOption.class);

        Files.walkFileTree(root, options, maxDepth,
                new SimpleFileVisitor<Path>() {
                    @Override
                    public FileVisitResult preVisitDirectory(
                            Path dir, BasicFileAttributes attrs) {
                        System.out.println("DIR       " + relative(root, dir));
                        return FileVisitResult.CONTINUE;
                    }

                    @Override
                    public FileVisitResult visitFile(
                            Path file, BasicFileAttributes attrs) {
                        String kind = Files.isSymbolicLink(file) ? "LINK"
                                : attrs.isDirectory() ? "DIR_LIMIT" : "FILE";
                        System.out.printf("%-9s %s%n", kind, relative(root, file));
                        return FileVisitResult.CONTINUE;
                    }

                    @Override
                    public FileVisitResult visitFileFailed(
                            Path file, IOException exc) throws IOException {
                        if (exc instanceof FileSystemLoopException) {
                            System.out.println("LOOP      " + relative(root, file));
                            return FileVisitResult.CONTINUE;
                        }
                        throw exc;
                    }
                });
    }

    private static String relative(Path root, Path item) {
        String name = root.relativize(item).toString();
        return name.isEmpty() ? "." : name;
    }
}
```

Compile and run, replacing `project` with an actual directory:

```bash
javac TreeLinkWalk.java
java TreeLinkWalk project 3 false
java TreeLinkWalk project 3 true
java TreeLinkWalk project 1 false
```

On Windows, you can use a full path enclosed in quotes, such as `java TreeLinkWalk "C:\data\project" 3 false`. The code uses Java 17+ APIs and does not create, delete, or write the files being traversed.

With the tree from Section 1, if the system supports symlinks and the `back` link exists, **illustrative** output when the depth limit is deep enough may contain:

```text
# followLinks=false:
DIR       .
DIR       docs
FILE      docs/guide.txt
LINK      docs/back
DIR       output

# followLinks=true:
DIR       .
DIR       docs
FILE      docs/guide.txt
LOOP      docs/back
DIR       output
```

This is an example of the lines you will see, **with no guaranteed ordering**: the file system is not required to return child entries in the order displayed; path separators also differ between Windows and Unix. If a directory sits at the `maxDepth` boundary, the program may print `DIR_LIMIT` instead of `DIR`. If symlinks cannot be created due to system permissions or an unsupported file system, do not assume `LINK` or `LOOP` lines will appear.

In the example, `visitFile` uses `Files.isSymbolicLink(file)` to identify that the *path* is a link even when links are being followed; whether Java invokes `preVisitDirectory`, `visitFile`, or `visitFileFailed` still depends on the target type, depth, and errors encountered.

## 6. Keeping Traversal Within the Permitted Area

A depth limit **does not guarantee** that traversal stays inside the root directory. A symlink at depth 1 can lead directly to an out-of-scope directory. When the application only needs to manage physical files under the root, the simpler and safer choice is **not enabling `FOLLOW_LINKS`**.

If business requirements force following symlinks while wanting to avoid processing entries outside the root, you can check the real path before processing:

```java
Path allowedRoot = root.toRealPath(); // Compute once before walking.
Path realDirectory = dir.toRealPath();
if (!realDirectory.startsWith(allowedRoot)) {
    return FileVisitResult.SKIP_SUBTREE; // Inside preVisitDirectory.
}
```

This is an **illustrative snippet placed inside `preVisitDirectory`**, with `root` and `dir` already declared. For regular files in `visitFile`, a similar check is needed before reading content; blocking only directories will miss symlinks pointing to **files** outside the root. `Path.startsWith(Path)` compares by path components; do not replace it with `path.toString().startsWith(prefix)` because string prefixes such as `/data/root-else` can be misidentified as `/data/root`.

Checking `toRealPath()` can throw `IOException` if the target disappears, access is denied, or it can no longer be resolved; handle it according to your error policy. Moreover, between check time and file-open time, the link can be modified (**TOCTOU**). Therefore, the check above is suitable as a logical guardrail for a relatively stable tree, **not an absolute security sandbox** against an actor capable of modifying the file system concurrently. For untrusted data, prefer not following links, restricting OS access permissions, and designing platform-appropriate file-opening methods resistant to path changes.

## 7. Avoiding Confusion Between Traversal APIs and Resource Limits

`Files.walk` returns a `Stream<Path>` and must be closed:

```java
try (var paths = Files.walk(root, 2)) {
    paths.forEach(System.out::println);
}
```

This is an illustrative snippet inside a method that handles `IOException`. By default, the stream does not follow symlinks. When using the variant with `FOLLOW_LINKS`, I/O errors while retrieving stream elements (including link cycles) may be wrapped in `UncheckedIOException`; the `FileVisitor.visitFileFailed` callback model belongs only to `walkFileTree`. Use `walkFileTree` when you need custom policies per directory and per error.

A real-world tree traversal program may need additional **independent** limits:

- **Number of visited entries:** Increment a counter; return `TERMINATE` when exceeding the threshold.
- **Elapsed runtime:** Compare start time with a deadline, checking inside callbacks; `maxDepth` does not limit runtime.
- **Total size or bytes read:** Check before and during content processing; traversing paths does not mean reading file contents.
- **Duplicate handling:** If the same file/directory must not be processed multiple times, track seen objects by file identity (`fileKey` when reliable, or `Files.isSameFile` comparisons when appropriate). Do not use only the path string as a physical identifier; two different paths can lead to the same object. `fileKey` can also be `null`, and the cost of comparisons must be weighed.

If you want to count or limit entries using callbacks, remember that an entry at the depth boundary can be reported in `visitFile`, even if it is a directory.

## 8. Common Mistakes and How to Verify

| Common mistake | Why it is wrong / how to fix |
| --- | --- |
| Enabling `FOLLOW_LINKS` and thinking every directory is visited only once | Java detects cycles with ancestors of the current branch; other links can still cause duplicate traversal. A separate deduplication policy is needed if required by business logic. |
| Thinking `maxDepth = 2` allows descending through two *sub*directories and reading all files inside them | The root is already depth 0; entries at depth 2 are the boundary and are not opened further. |
| Always treating `attrs` in `visitFile` as a regular file | At maximum depth, the callback may receive a directory path; when not following links, it may receive a symlink. |
| Ignoring all `IOException`s with `CONTINUE` | Traversal may silently miss data due to access denial or I/O errors. Only ignore accepted errors and log thoroughly. |
| Using `maxDepth` to prevent escaping the root | A shallow link can point outside. Do not follow links, or enforce real-path policies and access permissions. |
| Using `Files.walk` without closing the stream | The stream holds file system resources. Use `try-with-resources`. |

You can verify this yourself on a dedicated test directory:

1. Create a tree at least three levels deep, then run with `maxDepth` equal to 0, 1, 2, and 3 in turn to observe `DIR_LIMIT`.
2. If the system allows, create a symlink from a subdirectory back to an ancestor directory; compare `followLinks=false` and `true`.
3. Try a symlink pointing to a directory outside the root and a symlink with a non-existent target; observe the difference between a cycle, escaping the root, and a broken link.
4. Test a directory without access permissions if environmental conditions permit; confirm that errors are not silently ignored.

**Default rule of thumb:** For search, statistics, or ordinary file-processing tasks, start by **not following symbolic links**, set an appropriate `maxDepth`, and handle I/O errors explicitly. Only enable `FOLLOW_LINKS` when you genuinely need to traverse target objects as well, while defining how to handle cycles, duplicate visits, and scope limits.