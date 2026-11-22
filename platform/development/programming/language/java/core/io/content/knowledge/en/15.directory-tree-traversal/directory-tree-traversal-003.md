# `Files.walk` and Maximum Depth When Traversing a Directory Tree in Java

In real-world applications, you sometimes need to find files inside a directory, but **only descend to a specific number of levels**: scanning the current directory, direct subdirectories, or a few layers deeper. Java NIO.2 provides `Files.walk(...)` for tree traversal and a `maxDepth` parameter to **limit how deep traversal descends into subdirectories**.

For example, if a directory contains branches hundreds of levels deep, `Files.walk(root, 2)` traverses only items at most **two edges** away from `root`. This differs from traversing the entire tree and filtering results by depth afterward: the `maxDepth` parameter lets traversal **avoid descending** into branches beyond the allowed limit.

This lesson focuses on understanding depth, the `Files.walk` overloads, `Stream<Path>` lifecycles, filtering files and directories, symbolic links, I/O errors, and a verifiable Java 17 example.

## 1. What Does `Files.walk` Return?

Two important signatures of `java.nio.file.Files`:

~~~java
Stream<Path> paths = Files.walk(start);
Stream<Path> limited = Files.walk(start, maxDepth);
~~~

There is also a more general overload accepting traversal options:

~~~java
Stream<Path> paths = Files.walk(
        start, maxDepth, FileVisitOption.FOLLOW_LINKS);
~~~

Where:

- `start`: a `Path` object indicating the starting point; typically a directory.
- `maxDepth`: a non-negative `int` specifying the maximum depth of entries included in the results.
- `FileVisitOption...`: options such as `FOLLOW_LINKS` to alter how symbolic links are handled.
- **Return value:** a `Stream<Path>` traversing the discovered paths, in which **`start` itself is also an element**.
- `Files.walk(start)` is equivalent to descending with a practical unlimited bound of `Integer.MAX_VALUE`, not just one level.

**Special condition:** `maxDepth < 0` is an invalid argument and can throw `IllegalArgumentException`; do not use negative numbers to mean “unlimited.” To omit an explicit depth cap, call the `Files.walk(start)` overload.

`Files.walk` traverses the tree **depth-first**: starting at `start` and visiting entries underneath before moving to another branch. **The order of entries within the same directory is not guaranteed** by the API, so do not expect files to be returned automatically in ascending name order.

The result is a **lazy stream**: do not assume calling `Files.walk` loads the entire tree into memory. Terminal operations such as `forEach`, `count`, and `toList` trigger consumption of the stream.

## 2. Understanding `maxDepth` Precisely: Level 0 Is the Starting Point

Consider this example tree:

~~~text
root/                       (depth 0)
├── root.txt                (depth 1)
├── docs/                   (depth 1)
│   ├── readme.txt          (depth 2)
│   └── archive/            (depth 2)
│       └── old.txt         (depth 3)
└── images/                 (depth 1)
    └── logo.bin            (depth 2)
~~~

`maxDepth` counts **the number of path edges from `start` to each entry**, not the number of `/` separators in an absolute path.

| Call | Entries Within Scope | Path Count on Example Tree |
|---|---|---:|
| `Files.walk(root, 0)` | Only `root` | 1 |
| `Files.walk(root, 1)` | `root` and direct children | 4 |
| `Files.walk(root, 2)` | Adds `docs/readme.txt`, `docs/archive`, `images/logo.bin` | 7 |
| `Files.walk(root, 3)` | Adds `docs/archive/old.txt` | 8 |
| `Files.walk(root)` | All levels, barring errors or other restrictions | 8 |

From this we can conclude:

1. **`maxDepth = 0`:** still yields **one item (`start`)**, if the starting point is valid; it is not an empty stream.
2. **`maxDepth = 1`:** includes `start` **and** its direct child files and directories. This is not identical to `Files.list(root)`, because `Files.list` does not include `root` itself.
3. **`maxDepth = 2`:** includes entries at most two levels away from `root`. The directory `docs/archive` appears in the results at depth 2, but traversal **does not descend** to pick up `old.txt` at depth 3.
4. If `start` is a regular file, traversal has no subtree to descend into; when `maxDepth` is valid and the file is accessible, the result normally contains only that file's path.
5. Depth is always calculated **relative to the `start` argument**. If you call `Files.walk(root.resolve("docs"), 1)`, then `docs` becomes depth 0, not depth 1.

Easy rule to remember: **`maxDepth` is the maximum depth that can *appear* in the stream**, and a directory right at that depth **is not traversed any deeper**.

## 3. Standalone Java 17 Example: Depth-Limited Traversal

This program builds the tree above in a temporary directory, counts the number of `Path` entries at each depth, and prints a **sorted** list so the output does not depend on filesystem traversal order.

Save the complete code as **`FilesWalkDepthDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.List;
import java.util.stream.Stream;

public class FilesWalkDepthDemo {
    static long countAtDepth(Path root, int maxDepth)
            throws IOException {
        try (Stream<Path> paths = Files.walk(root, maxDepth)) {
            return paths.count();
        }
    }

    static List<String> listAtDepth(Path root, int maxDepth)
            throws IOException {
        try (Stream<Path> paths = Files.walk(root, maxDepth)) {
            return paths
                    .map(root::relativize)
                    .map(path -> path.toString().isEmpty()
                            ? "."
                            : path.toString().replace('\\', '/'))
                    .sorted()
                    .toList();
        }
    }

    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("files-walk-demo-");

        try {
            Files.createDirectories(root.resolve("docs/archive"));
            Files.createDirectory(root.resolve("images"));
            Files.writeString(root.resolve("root.txt"), "ROOT",
                    StandardCharsets.UTF_8);
            Files.writeString(root.resolve("docs/readme.txt"), "README",
                    StandardCharsets.UTF_8);
            Files.writeString(root.resolve("docs/archive/old.txt"), "OLD",
                    StandardCharsets.UTF_8);
            Files.write(root.resolve("images/logo.bin"),
                    new byte[] {1, 2, 3});

            for (int depth = 0; depth <= 3; depth++) {
                System.out.println("Depth " + depth + ": "
                        + countAtDepth(root, depth));
            }

            System.out.println("Depth 2 paths: "
                    + listAtDepth(root, 2));
            System.out.println("All paths: "
                    + countAtDepth(root, Integer.MAX_VALUE));
        } finally {
            try (Stream<Path> paths = Files.walk(root)) {
                List<Path> reverse = paths
                        .sorted(Comparator.reverseOrder())
                        .toList();
                for (Path path : reverse) {
                    Files.deleteIfExists(path);
                }
            }
        }
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 -encoding UTF-8 FilesWalkDepthDemo.java
java FilesWalkDepthDemo
~~~

On a normal filesystem where the program has permission to create/delete temporary data, the output is:

~~~text
Depth 0: 1
Depth 1: 4
Depth 2: 7
Depth 3: 8
Depth 2 paths: [., docs, docs/archive, docs/readme.txt, images, images/logo.bin, root.txt]
All paths: 8
~~~

**Why the output is reliable:**

- The total number of entries in the tree is **8**: one root, three depth-1 paths, three depth-2 paths, and one depth-3 path.
- `Files.walk(root, 2)` returns `root` and all entries up to depth 2; it does not need to return `old.txt`.
- `countAtDepth` closes the stream in `try-with-resources` immediately after counting.
- `listAtDepth` calls `root.relativize(path)` to produce relative paths, normalizes displayed separators to `/`, and calls `sorted()`. Thus it **does not depend on the OS enumeration order**.
- `root.relativize(root)` produces an empty path per the default provider's rules; the example intentionally displays it as the `.` symbol. This is merely a **display label**.
- The `finally` block traverses the tree again, sorts in reverse order, and deletes child entries before parent directories. Because the tree created here is small, `toList()` simplifies cleanup; for large trees, use `Files.walkFileTree` or a dedicated cleanup strategy rather than collecting all paths into RAM.
- The `Files.writeString` calls specify an explicit charset for text files; `Files.write` writes three binary bytes. Charsets **do not affect how depth is counted**.

Note: the program uses relative paths against a root created by the application itself. If an external actor modifies the temporary tree concurrently or the provider has special behavior, operations can throw errors. The example demonstrates API rules under normal conditions, not an arbitrary directory-deletion utility.

## 4. `try-with-resources` Is Needed Because the Stream Holds System Resources

This is a common mistake:

~~~java
// Do not leave Stream<Path> open without a bounded lifecycle.
Stream<Path> paths = Files.walk(root);
paths.forEach(System.out::println);
// Forgot paths.close().
~~~

Unlike purely in-memory computation streams, `Files.walk` can hold **directory streams / handles** while traversing. The documentation requires closing the returned stream to release resources promptly. The standard pattern is:

~~~java
try (Stream<Path> paths = Files.walk(root, 2)) {
    paths.forEach(System.out::println);
}
~~~

These are two **illustrative snippets**; `root` is an already-declared `Path`, requiring imports from `java.nio.file.*` and `java.util.stream.Stream`, along with `IOException` handling.

Do not assume that calling `count()`, `forEach()`, or `toList()` automatically calls `close()`. Terminal operations **do not replace closing the stream**. `try-with-resources` guarantees closing even if the block body throws an error.

### Why Not Keep One Stream for Multiple Queries?

A Java `Stream` can generally be consumed **only once**:

~~~java
try (Stream<Path> paths = Files.walk(root, 2)) {
    long count = paths.count();
    // Do not reuse paths to call paths.forEach(...).
}
~~~

If you need both counting and listing separately, open **two traversal passes** (as in the Java example above), or collect the results once into a `List` when the item count is small enough and storing it in memory is acceptable. Running two passes may observe **two different filesystem states** if files change between passes.

## 5. `maxDepth` Limits Exploration; `filter` Only Filters What Was Already Traversed

Compare these two approaches:

~~~java
// Limits the portion of the tree traversal descends into.
try (Stream<Path> paths = Files.walk(root, 2)) {
    long count = paths.count();
}
~~~

and:

~~~java
// Still traverses the entire tree; the filter only selects elements at depth <= 2.
try (Stream<Path> paths = Files.walk(root)) {
    long count = paths
            .filter(p -> root.relativize(p).getNameCount() <= 2)
            .count();
}
~~~

These are **illustrative snippets**. Filtering via `getNameCount()` also has to account for `root` relativized against itself and provider rules; do not treat it as a general equivalent of `maxDepth`.

**Crucial point:** the second approach can still **enter deeper directories** before the filter discards the results, potentially reading far more metadata, hitting errors in branches you never wanted to traverse, or taking significantly longer. If the business logic only needs two levels, use **`Files.walk(root, 2)` at the source**.

Use `filter` to select **entry types** after bounding depth, for instance keeping only regular files:

~~~java
try (Stream<Path> paths = Files.walk(root, 2)) {
    paths.filter(Files::isRegularFile)
         .forEach(System.out::println);
}
~~~

`Files.isRegularFile(path)` inspects filesystem metadata and follows symbolic links per that method's default contract. If you need not to follow links during the file-type check, use:

~~~java
paths.filter(p -> Files.isRegularFile(
        p, LinkOption.NOFOLLOW_LINKS))
~~~

This line is an **illustrative pipeline expression**, requiring the corresponding `LinkOption` import. Do not attach a second `filter` to a stream already consumed by `forEach` in the previous snippet; create a new stream instead.

**Choose the right tool for the job:** `maxDepth` limits **descent**, whereas `filter` limits **which results are retained**.

## 6. Maximum Depth Does **Not** Mean Maximum Number of Files

A root directory can have millions of direct child files. `Files.walk(root, 1)` may still have to list all of them: a depth limit **does not automatically bound item count** or bytes of metadata read.

Therefore, when optimizing:

- Choose an appropriate `maxDepth` to avoid traversing unnecessary branches.
- If you only need a few matches, you can use short-circuiting operations such as `findFirst()` or `limit(n)`, though you should not assume every filesystem stops all underlying I/O at the exact same moment.
- Avoid `toList()` or `collect(toList())` on trees with a huge number of entries unless all results are needed in RAM.
- Prefer `forEach` or streaming entry-by-entry processing when output can be processed incrementally.
- For branch control, aborting traversal, or `SKIP_SUBTREE` decisions, consider `Files.walkFileTree` and `FileVisitor` instead of forcing everything into a stream filter.

`Files.walk` is well suited for traversal and relatively straightforward pipelines; it is not a guarantee that every operation on a large tree will be fast or lightweight solely by setting `maxDepth`.

## 7. Symbolic Links and the `FOLLOW_LINKS` Option

By default, `Files.walk` **does not follow symbolic links**. Suppose there is a symlink `root/linked-docs` pointing to another directory:

~~~text
root/
├── linked-docs -> /elsewhere/docs
└── local.txt
~~~

With the call:

~~~java
Files.walk(root, 2);
~~~

the symlink may appear as a listed `Path`, yet traversal **does not follow it to traverse the entire target directory's contents**.

To request following symbolic links, pass `FileVisitOption.FOLLOW_LINKS`:

~~~java
try (Stream<Path> paths = Files.walk(
        root, 2, FileVisitOption.FOLLOW_LINKS)) {
    paths.forEach(System.out::println);
}
~~~

**Depth is still counted along the traversal path starting from `root`**, including traversal through a link if followed. Do not assume depth equals the number of components in the symlink target's real path; the logical path through the link and the real path can differ.

When following symlinks, a tree can contain **link cycles** such as A → B → A. `Files.walk` detects cycles during traversal per its contract and may report `FileSystemLoopException` (a subclass of `IOException`; during stream consumption, it may surface as `UncheckedIOException`). Remote filesystems or rapidly changing trees can also produce I/O errors.

**Key distinction:** `Files.walk(root, 2)` limits the maximum number of levels traversed, but it is not a security mechanism to prevent symlinks from pointing outside the root directory. If untrusted content must be processed, define an explicit link policy and access controls separately.

### Example When `maxDepth` Is 0 or 1 with `FOLLOW_LINKS`

`FOLLOW_LINKS` does not mean the API always traverses the directory a symlink points to regardless of depth limits. With `maxDepth = 0`, only `start` is in scope. With `maxDepth = 1`, only direct children appear; the API does not descend further inside a linked entry at level 1.

In summary, **`FOLLOW_LINKS` changes whether links may be followed**, while **`maxDepth` still governs how deep traversal goes**.

## 8. `IOException` When Opening the Stream and `UncheckedIOException` During Traversal

This is an important detail in the stream API:

~~~java
try (Stream<Path> paths = Files.walk(root, 3)) {
    paths.forEach(path -> System.out.println(path));
}
~~~

`Files.walk(...)` declares `throws IOException`. Failures can occur immediately when calling the method, for example when attributes of the starting point cannot be read or the input target does not exist according to the provider.

However, traversal is **lazy**. After obtaining `Stream<Path>`, errors occurring while processing subsequent directories can be thrown as **`UncheckedIOException`**, because `Stream` pipeline methods like `forEach`, `count`, etc. do not declare checked exceptions.

Error-distinction pattern:

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public class WalkErrors {
    static void printTree(Path root, int maxDepth)
            throws IOException {
        try (Stream<Path> paths = Files.walk(root, maxDepth)) {
            paths.forEach(System.out::println);
        } catch (UncheckedIOException ex) {
            throw ex.getCause(); // Propagate the original IOException to the caller.
        }
    }
}
~~~

This is a **compilable Java 17 utility class**, without a `main` method. It illustrates how to convert an unchecked traversal-time error back to checked `IOException` so callers can apply a single handling policy. In real systems, you might choose to report the error, perform bounded retries, or record failed branches according to policy; never swallow exceptions silently and claim the entire tree was traversed.

Do not assume every exception inside a pipeline comes from the filesystem: code inside `map`, `filter`, or `forEach` can also throw its own runtime exceptions. Error handling should preserve the cause for accurate diagnosis.

## 9. Combining `maxDepth` with Several Common Tasks

### Listing Regular Files Up to Two Levels

~~~java
try (Stream<Path> paths = Files.walk(root, 2)) {
    paths.filter(Files::isRegularFile)
         .forEach(System.out::println);
}
~~~

`Files::isRegularFile` may access metadata and follows links by default when checking file type; if a consistent no-follow policy is needed throughout, pass `NOFOLLOW_LINKS` to the corresponding check.

### Listing Directories (Including Root) Up to Three Levels

~~~java
try (Stream<Path> paths = Files.walk(root, 3)) {
    paths.filter(Files::isDirectory)
         .forEach(System.out::println);
}
~~~

If you want to **exclude root** from the output:

~~~java
try (Stream<Path> paths = Files.walk(root, 3)) {
    paths.filter(Files::isDirectory)
         .filter(path -> !path.equals(root))
         .forEach(System.out::println);
}
~~~

Even when root is filtered out of the results, it remains the **starting point** and is visited by traversal at depth 0.

### Counting Files Up to a Depth Limit

~~~java
long files;
try (Stream<Path> paths = Files.walk(root, 2)) {
    files = paths.filter(Files::isRegularFile).count();
}
~~~

Note that `count()` on a stream of paths is not file byte size, line count, or storage size; it is solely **the count of `Path` elements matching the condition**.

### Producing Relative Paths for Reporting

~~~java
try (Stream<Path> paths = Files.walk(root, 2)) {
    paths.map(root::relativize)
         .map(Path::toString)
         .sorted()
         .forEach(System.out::println);
}
~~~

When `root` and the elements belong to the same filesystem/provider, `relativize` is suitable for producing relative labels. If the goal is outputting a report with deterministic order, `sorted()` is helpful, though it may need to **hold many elements in memory** to sort.

## 10. `Files.walk`, `Files.list`, `Files.find`, and `Files.walkFileTree`

| API | Scope | Key Points to Remember |
|---|---|---|
| `Files.list(dir)` | Lists **one level of direct children**; excludes `dir` itself | Returns `Stream<Path>` that must also be closed |
| `Files.walk(start)` | Traverses from `start` down through descendant levels | Includes `start`; no finite depth bound |
| `Files.walk(start, maxDepth)` | Traverses and stops at the allowed depth | Includes `start` at depth 0 |
| `Files.find(start, maxDepth, matcher, options...)` | Finds entries matching a predicate based on `Path` and `BasicFileAttributes` | Can avoid reading attributes twice compared to some `walk().filter(...)` patterns; also returns a stream that must be closed |
| `Files.walkFileTree(start, visitor)` | Traverses with a `FileVisitor`, offering control at every directory/entry | Suitable when `SKIP_SUBTREE`, per-node error handling, or tree cleanup/copying is needed |

`Files.walkFileTree` also has an overload accepting `maxDepth` and `FileVisitOption`. When custom branch-stopping policies are needed, it is often clearer than a `Files.walk` pipeline. However, when you simply need to “list files up to two levels deep and filter,” `Files.walk(root, 2)` is a concise built-in tool in Java NIO.2.

## 11. Common Mistakes

| Misconception | Consequence | Right Approach |
|---|---|---|
| Thinking `maxDepth = 0` yields no results | Misses `start` itself | Remember root is at **depth 0** |
| Thinking `maxDepth = 1` returns only root's children | Overcounts/miscounts due to root | Filter root out separately if unwanted |
| Calling `Files.walk(root)` and filtering by depth afterward | Still descends into unnecessary deep branches | Use the `Files.walk(root, maxDepth)` overload |
| Assuming `maxDepth` caps the number of returned items | A single-level directory can still hold huge numbers of files | Bound result counts / design processing separately |
| Forgetting to close `Stream<Path>` | May hold directory handles or I/O resources | Use `try-with-resources` |
| Using the same stream for two terminal operations | `IllegalStateException` or consumed-stream error | Open a new pass or store a controlled list |
| Assuming file order within each directory is deterministic | Output differs across filesystems | Use `sorted()` if ordering is required |
| Assuming symbolic links are always followed | Links are not followed by default | Pass `FOLLOW_LINKS` intentionally |
| Following symlinks without handling cycles | Can encounter `FileSystemLoopException` | Handle errors and set appropriate bounds |
| Catching only `IOException` around `Files.walk` and ignoring lazy errors | Misses `UncheckedIOException` during stream consumption | Distinguish open phase and iteration phase |
| Calling `toList()` on a massive tree | High RAM consumption | Process as a stream or use `walkFileTree` |
| Confusing depth at `maxDepth` with a fixed number of `/` characters | Wrong scope when `root` has multiple path segments | Count depth relative to `start` |

## 12. Self-Check

**Question 1.** Given a tree containing `root/a/file.txt`, does calling `Files.walk(root, 1)` see `file.txt`?

> **No.** `root` is at depth 0, `a` is at depth 1, and `file.txt` is at depth 2. `maxDepth = 1` does not reach depth 2.

**Question 2.** To count direct child files without counting root, should you use `Files.list(root)` or `Files.walk(root, 1)`?

> Either can work if filtered properly, but `Files.list(root)` is a more direct fit because it lists only the directory's children, **excluding root**. `Files.walk(root, 1)` includes both root and its children; you would need to filter root out.

**Question 3.** Why can `Files.walk(root).filter(p -> depth(p) <= 2)` perform worse than `Files.walk(root, 2)`?

> The first approach may still traverse very deep branches before discarding elements in the filter. `maxDepth` limits **descending the tree** at the API level, rather than merely dropping results.

**Question 4.** A directory at depth 2 contains many files inside it. Does `Files.walk(root, 2)` enter that directory to read depth-3 files?

> **No.** The directory at maximum depth is returned as an entry, but traversal does not descend deeper than allowed.

**Question 5.** Must you close a `Files.walk` stream after `count()` finishes?

> **Yes.** A terminal operation does not replace `close()`; use `try-with-resources` to release directory resources.

**Question 6.** If you enable `FOLLOW_LINKS` and encounter a symlink cycle, what exception may occur?

> **`FileSystemLoopException`**, which may be wrapped in `UncheckedIOException` when the error occurs during stream consumption. The caller must handle it per its I/O error policy.

**Question 7.** Does `Files.walk(root, 2)` guarantee producing at most two results?

> **No.** The number 2 is **depth**, not the number of files/directories. The number of elements depends on the tree's breadth across the permitted levels.

## Key Takeaways

- `Files.walk(start, maxDepth)` traverses starting from **`start` at depth 0** down to the maximum depth.
- `0` yields root, `1` yields root + direct children, `2` adds grandchildren; every path depth is measured relative to `start`.
- Unlike filtering after traversal, `maxDepth` avoids **descending deeper** than the threshold.
- `Files.walk` returns a **`Stream<Path>` backed by I/O resources**, which must be closed with `try-with-resources`.
- By default, it **does not follow symbolic links**; `FOLLOW_LINKS` changes that behavior, at the risk of link cycles and I/O errors.
- Results can depend on the filesystem for order and live state; **sort when needed**, handle `IOException` / `UncheckedIOException`, and never confuse a depth limit with a count limit.

**References:** [Java SE 17 — `Files.walk`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html), [`FileVisitOption`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileVisitOption.html), [`Stream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html).
