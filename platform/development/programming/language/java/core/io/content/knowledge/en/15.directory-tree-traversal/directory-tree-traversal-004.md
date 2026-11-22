# `Files.find` Combining `Path` with `BasicFileAttributes` in Java

When you need to **find entries in a directory tree based on conditions**, Java NIO.2 provides `Files.find(...)`. The key strength of this API is that the predicate receives **both `Path` and `BasicFileAttributes` together**: you can inspect **file name/location** as well as **type, size, and timestamps** without manually re-reading attributes inside every filter.

A practical example: find all files ending in `.txt`, with size 4 bytes or greater, located within at most 3 levels from the root directory. `Files.find` returns a `Stream<Path>` so you can continue with `map`, `filter`, `sorted`, or `forEach`.

However, this stream is tied to filesystem traversal resources and can throw errors while being consumed; it **must be closed with `try-with-resources`**. You also need to understand `maxDepth`, symbolic link rules, traversal order, and the limitations of attribute snapshots.

## 1. Signature and Meaning of Each Parameter

In `java.nio.file.Files` (Java 17+), the core overload has the form:

~~~java
public static Stream<Path> find(
        Path start,
        int maxDepth,
        BiPredicate<Path, BasicFileAttributes> matcher,
        FileVisitOption... options) throws IOException
~~~

Types to import:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.FileVisitOption;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.function.BiPredicate;
import java.util.stream.Stream;
~~~

These are two **snippets illustrating the API signature and imports**, not a runnable Java file.

| Component | Meaning |
|---|---|
| `start` | Starting path for traversal; can be a directory or a single file |
| `maxDepth` | Maximum depth: `0` means only the starting entry, `1` adds direct children |
| `matcher` | Two-argument predicate `(Path path, BasicFileAttributes attrs)` returning `true` when the path should be included in results |
| `options` | Traversal options, commonly `FileVisitOption.FOLLOW_LINKS` if you want to follow symbolic links |
| `Stream<Path>` | Stream of **matching** paths produced during traversal |

Short example:

~~~java
// Illustrative snippet: root is an already defined Path.
try (Stream<Path> matches = Files.find(
        root,
        2,
        (path, attrs) -> attrs.isRegularFile())) {
    matches.forEach(System.out::println);
}
~~~

`Files.find` includes only `Path` entries for which `matcher.test(path, attrs) == true` in the result stream. If the predicate is `(path, attrs) -> true`, all traversed entries can appear in the results, including the `start` path itself.

**Do not confuse** `Files.find` with pure string name matching such as `String.contains(...)`. `Files.find` **actually traverses the filesystem**; it requires permissions and can encounter I/O errors.

## 2. `Path` and `BasicFileAttributes` Serve Two Different Roles

### `Path`: Address and Name Components

`Path` answers “where is the entry located and how is it named?”:

- `path.getFileName()`: final name of the path (can be `null` for a root-only path).
- `path.getParent()`: parent directory, if any.
- `path.startsWith(base)`: checks prefix by **path components**, not raw string characters.
- `path.endsWith(otherPath)`: checks suffix by path components; **not** for checking extensions like `.txt`.
- `root.relativize(path)`: computes a relative path from `root` to `path`, if the two `Path`s are compatible per provider.

### `BasicFileAttributes`: Basic Metadata About a Filesystem Entry

`BasicFileAttributes` is an interface holding information retrieved from the filesystem:

| `BasicFileAttributes` API | Meaning |
|---|---|
| `isRegularFile()` | Entry is identified as a regular file per the attribute-reading rules |
| `isDirectory()` | Entry is a directory |
| `isSymbolicLink()` | Entry is identified as a symbolic link when reading attributes does not follow it |
| `isOther()` | Entry type not belonging to the three groups above |
| `size()` | Reported size in bytes; has provider-specific semantics for non-regular files |
| `creationTime()` | Creation time reported by the provider |
| `lastModifiedTime()` | Last modification time |
| `lastAccessTime()` | Last access time |
| `fileKey()` | File identifier key if supported by the provider, may be `null` |

Do not infer that `size()` on a **directory** means “sum of bytes of child files”; for entries that are not regular files, size can mean something else or not be meaningfully defined. To compute the total size of a directory tree, you must traverse and sum **the sizes of matching regular files**, while handling hard links/symbolic links if you want to avoid double counting.

For creation time, some filesystems do not store true creation timestamps; the provider may supply a fallback value. Timestamps are returned as `FileTime`, and you should not assume a fixed timezone or precision.

## 3. Writing Clear and Correct Matchers

A `matcher` typically combines conditions on `Path` and `BasicFileAttributes`:

~~~java
// Illustrative snippet: passed as the matcher argument of Files.find.
(path, attrs) ->
        attrs.isRegularFile()
        && path.getFileName() != null
        && path.getFileName().toString().endsWith(".txt")
        && attrs.size() >= 4
~~~

Meaning of each condition:

1. Accept **regular files** only, excluding directories.
2. Guard against `getFileName() == null` before calling `toString()`.
3. Check the extension on the **filename string**, not with `Path.endsWith(".txt")`.
4. Check the size already supplied in attributes, avoiding an extra `Files.size(path)` call inside the predicate for the same data.

You can extract a predicate for reuse:

~~~java
BiPredicate<Path, BasicFileAttributes> isNonEmptyText =
        (path, attrs) ->
                attrs.isRegularFile()
                && path.getFileName() != null
                && path.getFileName().toString().endsWith(".txt")
                && attrs.size() > 0;
~~~

This is an **illustrative snippet**: requires importing `BiPredicate`, `Path`, and `BasicFileAttributes`. The name `isNonEmptyText` only asserts that the file **has a name ending in `.txt` and non-zero size**, **not** that its content is valid text. A file extension is not proof of content format or safety.

Remember that the predicate may be invoked for the **root directory** or **intermediate directories**, not only for files. Never assume `path.getFileName()` is always non-null or that every `attrs` represents a regular file.

## 4. `maxDepth`: Depth 0, Depth 1, Depth 2...

Suppose we have the following tree:

~~~text
root/                       ← depth 0
├── note.txt                ← depth 1
├── app.log                 ← depth 1
└── docs/                   ← depth 1
    ├── guide.txt           ← depth 2
    ├── empty.txt           ← depth 2
    └── nested/             ← depth 2
        └── deep.txt        ← depth 3
~~~

If the matcher accepts every entry:

| `maxDepth` | Entries That Can Be Evaluated |
|---:|---|
| `0` | Only `root` |
| `1` | `root` and direct children `note.txt`, `app.log`, `docs` |
| `2` | Adds `guide.txt`, `empty.txt`, `nested` |
| `3` | Adds `deep.txt` |
| `Integer.MAX_VALUE` | Traverses without a practical depth cap at parameter level (still subject to resources/accessibility) |

If the matcher only accepts `attrs.isRegularFile()`, directory paths are still **traversed** to discover child files, but will **not appear in the result stream**.

Negative `maxDepth` is invalid and throws `IllegalArgumentException`. For large trees, set a depth bound appropriate for your domain rather than defaulting unconditionally to `Integer.MAX_VALUE`.

Important: **returning `false` from the matcher for a directory does not stop traversal into that directory's children**. `Files.find` is an entry selection mechanism; if you need to actively **prune an entire branch** (`skip subtree`) during traversal, use `Files.walkFileTree` with `FileVisitor`/`SimpleFileVisitor` and return `FileVisitResult.SKIP_SUBTREE` from `preVisitDirectory`.

## 5. Complete Example: Finding Files by Name, Size, and Depth

File **`FilesFindDemo.java`**, compatible with Java 17+:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public class FilesFindDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("find-demo-");
        Path docs = root.resolve("docs");
        Path nested = docs.resolve("nested");

        try {
            Files.createDirectories(nested);
            Files.writeString(root.resolve("note.txt"), "abc",
                    StandardCharsets.UTF_8);
            Files.writeString(root.resolve("app.log"), "1234567",
                    StandardCharsets.UTF_8);
            Files.writeString(docs.resolve("guide.txt"), "hello",
                    StandardCharsets.UTF_8);
            Files.writeString(docs.resolve("empty.txt"), "",
                    StandardCharsets.UTF_8);
            Files.writeString(nested.resolve("deep.txt"), "four",
                    StandardCharsets.UTF_8);

            System.out.println("maxDepth=2:");
            printMatches(root, 2);

            System.out.println("maxDepth=3:");
            printMatches(root, 3);
        } finally {
            Files.deleteIfExists(nested.resolve("deep.txt"));
            Files.deleteIfExists(docs.resolve("empty.txt"));
            Files.deleteIfExists(docs.resolve("guide.txt"));
            Files.deleteIfExists(root.resolve("app.log"));
            Files.deleteIfExists(root.resolve("note.txt"));
            Files.deleteIfExists(nested);
            Files.deleteIfExists(docs);
            Files.deleteIfExists(root);
        }
    }

    private static void printMatches(Path root, int maxDepth)
            throws IOException {
        try (Stream<Path> matches = Files.find(
                root,
                maxDepth,
                (path, attrs) ->
                        attrs.isRegularFile()
                        && path.getFileName() != null
                        && path.getFileName().toString().endsWith(".txt")
                        && attrs.size() >= 3)) {

            matches.map(root::relativize)
                    .map(Path::toString)
                    .map(name -> name.replace('\\', '/'))
                    .sorted()
                    .forEach(System.out::println);
        }
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 FilesFindDemo.java
java FilesFindDemo
~~~

Stdout on a standard default filesystem when file creation succeeds:

~~~text
maxDepth=2:
docs/guide.txt
note.txt
maxDepth=3:
docs/guide.txt
docs/nested/deep.txt
note.txt
~~~

Explanation:

- `note.txt` has 3 bytes, `guide.txt` has 5 bytes, and `deep.txt` has 4 bytes; all satisfy `attrs.size() >= 3` and names ending in `.txt`.
- `empty.txt` has size 0 so it does not match. `app.log` does not have the `.txt` extension.
- `deep.txt` sits 3 levels deep, so it is excluded when `maxDepth == 2` and appears when `maxDepth == 3`.
- `map(root::relativize)` converts random temporary absolute paths into readable relative paths.
- `replace('\\', '/')` normalizes only **the printed string** between Windows/Unix; it does not alter how `Path` objects are traversed.
- `sorted()` makes output order predictable. Without `sorted()`, there is no general guarantee that entry traversal order will match across filesystems.

The program operates only inside the temporary directory it creates. `finally` deletes files first and then directories from deepest upward, because `Files.deleteIfExists(dir)` does not recursively delete a non-empty directory.

## 6. Searching by Time, Size, and File Type

`BasicFileAttributes` supports building many kinds of filters.

### Finding Files Modified After a Point in Time

~~~java
// Illustrative snippet: root and cutoff are already defined,
// cutoff has type java.nio.file.attribute.FileTime.
try (Stream<Path> found = Files.find(
        root,
        4,
        (path, attrs) ->
                attrs.isRegularFile()
                && attrs.lastModifiedTime().compareTo(cutoff) >= 0)) {
    found.forEach(System.out::println);
}
~~~

`lastModifiedTime()` returns a `FileTime`, which can be compared via `compareTo(...)` or converted to `Instant` when needed, depending on the processing goal. If a system needs to filter by “day” in a local timezone, define the timezone and exact cutoff instant explicitly; file timestamps do not inherently carry a user's notion of “today.”

### Finding Directories

~~~java
try (Stream<Path> directories =
             Files.find(root, 2, (p, attrs) -> attrs.isDirectory())) {
    directories.forEach(System.out::println);
}
~~~

This is an **illustrative snippet**. Note that `root` itself can also be returned if `root` is a directory; to receive only subdirectories, add `!p.equals(root)` or inspect depth via `root.relativize(p).getNameCount()` with appropriate guards.

### Combining Conditions and Avoiding Re-reading Attributes

~~~java
try (Stream<Path> matches = Files.find(
        root,
        3,
        (p, a) -> a.isRegularFile()
                && a.size() > 1_024
                && p.getFileName() != null
                && p.getFileName().toString().endsWith(".log"))) {
    matches.forEach(System.out::println);
}
~~~

These snippets illustrate **placing conditions inside the matcher**. When `Files.find` visits an entry, it reads `BasicFileAttributes` and passes them to the predicate. Using `a.size()` and `a.isRegularFile()` directly often avoids a separate attribute query that you might end up writing with `Files.walk(...).filter(p -> Files.size(p) > ...)`.

However, actual efficiency depends on the provider, depth, file count, storage device, and predicate cost. Never claim `find` is always faster than every other traversal approach in all environments.

## 7. How Is `Stream<Path>` Consumed?

`Files.find(...)` returns a **lazy traversal stream**: creating the stream does not mean all entries have already been visited or read. Most work occurs when a terminal operation such as `forEach`, `count`, `collect`, or `toList` is called.

~~~java
// Illustrative snippet: root is a valid Path.
try (Stream<Path> found = Files.find(
        root, 2, (p, attrs) -> attrs.isRegularFile())) {
    long total = found.count();
    System.out.println(total);
}
~~~

**Always close the stream**: traversal can hold open resources such as directory handles. The `Stream<Path>` from `Files.find` must be closed with `try-with-resources` when no longer needed, even if the terminal operation throws an exception.

Key points to remember:

1. A stream can typically be consumed **only once**. After `count()`, do not call `forEach()` on the same stream expecting to traverse again.
2. Intermediate operations like `filter`/`map` usually do not perform I/O immediately on their own; the terminal operation triggers the pipeline.
3. Using `sorted()` or `toList()` holds the corresponding elements in memory; a huge result set can consume significant RAM. If you only need sequential processing without stable ordering, `forEach` can be more suitable.
4. Operations like `findFirst()`/`limit(...)` can stop consumption early. You still must close the stream, and you should not treat `limit` as an absolute cap on all underlying resource access cost.
5. A `Stream` backed by filesystem resources should not be returned from a method after being closed inside a `try` block. If you want to return a list, collect and close the stream inside; if you must return a stream, clearly define that the caller owns the closing responsibility.

**Incorrect lifecycle** example:

~~~java
// Illustrative snippet: DO NOT do this when returning a stream to the caller.
Stream<Path> leaked() throws IOException {
    return Files.find(root, 10, (p, a) -> a.isRegularFile());
}
// The caller may forget to close the stream.
~~~

One solution is handling within scope:

~~~java
// Illustrative snippet: the result is a List<Path> in RAM.
try (Stream<Path> stream = Files.find(
        root, 10, (p, a) -> a.isRegularFile())) {
    return stream.toList(); // Java 16+, closes the stream after collecting.
}
~~~

However, if the results can be very large, that approach trades an open-stream risk for **accumulating a large list in RAM**. Consider streaming processing, result limits, or batched APIs depending on requirements.

## 8. Following Symbolic Links: Default Behavior and `FOLLOW_LINKS`

By default, `Files.find` **does not follow symbolic links** while traversing. If you want to process directories pointed to by symbolic links, pass `FileVisitOption.FOLLOW_LINKS`:

~~~java
// Illustrative snippet, requires importing FileVisitOption.
try (Stream<Path> found = Files.find(
        root,
        5,
        (p, attrs) -> attrs.isRegularFile(),
        FileVisitOption.FOLLOW_LINKS)) {
    found.forEach(System.out::println);
}
~~~

Distinguish two things:

- **Traversal rule:** whether to descend into directories targeted by symbolic links.
- **Attributes seen by the matcher:** depending on how attributes are read during traversal, following links can expose attributes of the **target**, whereas not following links exposes attributes of the **link itself**. Therefore, `attrs.isRegularFile()`, `attrs.isDirectory()`, and `attrs.isSymbolicLink()` must be interpreted under the selected traversal mode.

Risks with `FOLLOW_LINKS`:

1. Traversal can move to unexpected locations, including physically outside `root`.
2. A symbolic link path can point back to an ancestor, creating a **cycle**. When a loop is detected, traversal can raise `FileSystemLoopException`, wrapped in `UncheckedIOException` during stream consumption.
3. The same underlying file object may be encountered through multiple aliases; search results do not automatically deduplicate by file identity.
4. Symbolic links and contents can change during traversal, causing races or I/O errors.

For scanning or file-deletion tools, **do not enable `FOLLOW_LINKS` merely to find more results**. Establish clear policies for permissions, data boundaries, depth limits, and link-handling behavior.

## 9. How Does `Files.find` Differ from `Files.walk` and `walkFileTree`?

| API | Output / Mechanism | When to Use |
|---|---|---|
| `Files.find(start, depth, matcher, options...)` | `Stream<Path>` of matching entries; matcher receives `Path` **and** `BasicFileAttributes` | Need to filter directly by type/size/time together with path name |
| `Files.walk(start, depth, options...)` | `Stream<Path>` of visited entries | Want to traverse and apply other Stream ops; fetch attributes yourself if needed |
| `Files.walkFileTree(start, visitor)` | Callbacks `preVisitDirectory`, `visitFile`, `visitFileFailed`, `postVisitDirectory` | Need branch control, subtree skipping, per-entry error handling, and custom workflows |

An advantage of `Files.find` over writing `Files.walk(...).filter(path -> Files.readAttributes(...))` is that attributes are already available in the predicate. Conversely, when you need to **traverse only certain branches** or **continue/abort based on per-entry errors** in custom ways, `walkFileTree` with `FileVisitor` expresses that intent much better.

Important: `find` does not support `SKIP_SUBTREE` from the matcher. Even when the predicate returns `false` for a directory, descending into that directory's children can still occur. Do not return `false` from a matcher expecting it to skip traversing an entire branch.

## 10. I/O Exceptions When Creating and Consuming the Stream

`Files.find(...)` can throw `IOException` **right when creating the stream** if the starting source cannot be opened. During lazy traversal, an I/O error occurring later may be surfaced as `UncheckedIOException`, whose `getCause()` holds a concrete `IOException`.

~~~java
// Illustrative snippet, requires importing IOException and UncheckedIOException.
try (Stream<Path> found = Files.find(
        root, 5, (p, a) -> a.isRegularFile())) {
    found.forEach(this::processFile);
} catch (java.io.UncheckedIOException ex) {
    // Error occurred while the stream was being consumed.
    java.io.IOException cause = ex.getCause();
    // Record and handle the I/O cause.
} catch (java.io.IOException ex) {
    // Error opening source / creating stream.
}
~~~

This is an **illustrative snippet inside a method of a class having `processFile`**, not a standalone program. If used inside a `static` method, replace `this::processFile` with an appropriate method reference.

Not every error inside `matcher` turns into `UncheckedIOException`: if your predicate throws another `RuntimeException`, it propagates under normal Stream rules. Avoid catching everything in a generic handler and ignoring it, because search results may be **partial**.

Additionally, directories and files can change between reading attributes and opening the path for processing. `BasicFileAttributes` is a snapshot of attributes at read time; it **does not lock the file**, does not provide a single transaction, and does not guarantee contents will not change afterward. If business logic demands stronger consistency, use appropriate synchronization or file operations.

## 11. Java 17+ Example: Using Attributes Without Printing Machine-Dependent Timestamps

The following example creates a structure with deterministic contents and illustrates multi-attribute filtering while keeping stdout deterministic.

Create file **`FilesFindAttributesDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public class FilesFindAttributesDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("find-attrs-");
        Path sub = root.resolve("sub");

        try {
            Files.createDirectory(sub);
            Files.writeString(root.resolve("small.txt"), "a",
                    StandardCharsets.UTF_8);
            Files.writeString(root.resolve("large.txt"), "12345",
                    StandardCharsets.UTF_8);
            Files.writeString(sub.resolve("deep.txt"), "1234",
                    StandardCharsets.UTF_8);

            try (Stream<Path> found = Files.find(
                    root, 1,
                    (p, a) -> a.isRegularFile() && a.size() >= 4)) {
                System.out.println("level1Count=" + found.count());
            }

            try (Stream<Path> found = Files.find(
                    root, 2,
                    (p, a) -> a.isRegularFile()
                            && a.size() >= 4
                            && a.lastModifiedTime() != null)) {
                System.out.println("level2Count=" + found.count());
            }

            try (Stream<Path> found = Files.find(
                    root, 0, (p, a) -> a.isDirectory())) {
                System.out.println("rootOnly=" + found.count());
            }
        } finally {
            Files.deleteIfExists(sub.resolve("deep.txt"));
            Files.deleteIfExists(root.resolve("large.txt"));
            Files.deleteIfExists(root.resolve("small.txt"));
            Files.deleteIfExists(sub);
            Files.deleteIfExists(root);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 FilesFindAttributesDemo.java
java FilesFindAttributesDemo
~~~

Stdout:

~~~text
level1Count=1
level2Count=2
rootOnly=1
~~~

Explanation:

- `level1Count=1` because only `large.txt` lies directly under root with 5 bytes and matches the condition; `small.txt` has 1 byte, and `deep.txt` is at depth 2.
- `level2Count=2` because when expanding to depth 2, `deep.txt` with 4 bytes is also accepted. `lastModifiedTime()` is a `FileTime` attribute supplied by the provider; the example checks for the object's presence rather than printing a machine-varying timestamp.
- `rootOnly=1` illustrates that `maxDepth=0` evaluates only the starting directory itself, and the matcher accepts it via `isDirectory()`.

Although the example produces fixed stdout in a normal environment, file permissions, deletion by another process, or special filesystems can still raise I/O errors that the program must handle.

## 12. Relative Paths, Absolute Paths, and Root Comparison

When handling results from `Files.find`, each returned `Path` carries context relative to `start`; display code often uses:

~~~java
// Illustrative snippet: path comes from search results under root.
Path relative = root.relativize(path);
System.out.println(relative);
~~~

`Path.relativize(...)` requires paths that can be relativized under the provider's rules (on the default filesystem, do not arbitrarily mix absolute and relative paths). For testable logic, normalize how `root` is resolved before calling `find` and avoid string-concatenating paths across incompatible filesystems.

To compare paths by **components**, use `startsWith(Path)`/`endsWith(Path)` rather than string prefix checks on `toString()`. However, lexical checks like `candidate.normalize().startsWith(root.normalize())` **are not a complete security boundary** when symbolic links and concurrent filesystem mutations exist.

### Several Useful Matchers

~~~java
// Illustrative snippet (must be placed inside a method).
(path, attrs) ->
        attrs.isRegularFile()
        && path.getFileName() != null
        && path.getFileName().toString().startsWith("report-")
~~~

~~~java
// Illustrative snippet.
(path, attrs) -> attrs.isDirectory() && !path.equals(root)
~~~

~~~java
// Illustrative snippet: checks filename only, not parent directory names.
(path, attrs) -> attrs.isRegularFile()
        && path.getFileName() != null
        && path.getFileName().toString().endsWith(".json")
~~~

These predicates inspect **name or entry type** only; they do not read or validate the contents of JSON/report files. If content parsing is needed, do it after finding the path using appropriate reading and security validation mechanisms.

## 13. Performance and Resources When Searching Large Trees

`Files.find` is concise, but its costs must be considered:

- **Total directories/entries traversed:** a simple matcher does not mean only matching items are visited; a large tree may still require scanning many directories.
- **Depth limit:** `maxDepth` prevents descending into overly deep regions, but does not cap the number of entries within those levels.
- **Attribute cost:** `Files.find` retrieves `BasicFileAttributes` for each evaluated entry. On network drives or remote providers, attribute queries can be significant.
- **Memory threshold:** a lazy `Stream` reduces accumulation when consumed sequentially, but `sorted()`, `toList()`, and `collect(...)` can retain thousands or millions of results in RAM.
- **No contractually stable traversal order:** if exact ordering is required, sort intentionally while accepting the memory cost.
- **No custom per-branch error policy:** if you need to skip a failing directory while continuing other branches, `walkFileTree` with `visitFileFailed` may be a better fit.
- **Do not infer file contents from attributes:** `attrs.size()` helps filter by size, but does not guarantee valid file format or prevent contents from changing afterward.
- **No built-in traversal timeout:** when a tree or filesystem is slow, consider running within a resource-managed component with task bounds and cancellation policies compatible with the API/OS.

If you only need to inspect one known file, calling `Files.readAttributes(path, BasicFileAttributes.class)` or a dedicated helper directly can be simpler than traversing an entire tree.

## 14. Common Mistakes

| Mistake | Consequence | Right Way |
|---|---|---|
| Calling `Files.find` and not closing the stream | Leaks directory traversal handles, especially in long-running programs | Use `try-with-resources` |
| Thinking `maxDepth=1` traverses only root | Root is depth 0; depth 1 also includes direct children | Map out the tree and levels clearly |
| Thinking a matcher returning `false` for a directory skips its entire subtree | `Files.find` selects results; it does not support `SKIP_SUBTREE` from the matcher | Use `walkFileTree` when pruning is needed |
| Using `Path.endsWith(".txt")` to check extension | `Path.endsWith` compares whole path components | Use `getFileName().toString().endsWith(".txt")` |
| Not checking `getFileName() == null` | A root path may have no final name element | Check for `null` |
| Calling `Files.size(path)` for every result | Redundant I/O query and potential race | Reuse `attrs.size()` when appropriate |
| Enabling `FOLLOW_LINKS` blindly without considering cycles | May traverse outside intended scope or hit loops | Choose an explicit link policy |
| Assuming `Files.find` returns an already-completed list | Lazy stream; errors can happen at terminal operation time | Handle both `IOException` and `UncheckedIOException` |
| Assuming results are in alphabetical order | Not guaranteed | Use `sorted()` if needed and memory permits |
| Calling `count()` then `forEach` on the same stream | A stream can be consumed only once | Create a new stream or design a single-pass pipeline |
| Assuming timestamps/sizes never change | Filesystem can mutate during traversal | Handle live state when opening/using files |
| Using a found path as proof of safe access | Symlinks/TOCTOU can change the physical target | Combine filesystem policies with safe open operations |

## 15. Checklist Before Using in Real Applications

1. Define `start` and `maxDepth`; avoid scanning an entire drive when only one subtree is needed.
2. Write predicates combining `Path` and `BasicFileAttributes`; check `attrs.isRegularFile()` before interpreting size as regular-file size.
3. Check `path.getFileName() != null` before processing filenames.
4. Decide **whether to follow symbolic links**, understanding loop and boundary-escape risks.
5. Place `Files.find(...)` inside `try-with-resources`, even when only calling `count()` or `findFirst()`.
6. Handle both stream-creation exceptions and `UncheckedIOException`-wrapped errors during traversal.
7. If deterministic result ordering is required, use `sorted()`; if data is very large, weigh memory cost.
8. If you need branch skipping or per-file error control, switch to `walkFileTree`.
9. Do not treat `BasicFileAttributes` as immutable state; re-verify as needed when actually accessing the file.
10. Test with empty directories, zero-byte files, boundary depths, symlinks, and files disappearing mid-search.

## 16. Summary

`Files.find(start, maxDepth, matcher, options...)` traverses a path tree and returns a `Stream<Path>` of entries matching a **`BiPredicate<Path, BasicFileAttributes>`**. `Path` describes name and location, while `BasicFileAttributes` supplies entry type, size, and timestamps. Use `maxDepth` to bound depth, choose `FOLLOW_LINKS` deliberately, and **always close the stream**.

Compared with `Files.walk(...)`, `Files.find(...)` is particularly convenient when the matcher needs pre-fetched file attributes. However, if you need to prune subtrees or control errors per branch, `Files.walkFileTree(...)` is a better fit. Never confuse attribute filtering with content validation or filesystem access control.

### Official References

- [Java SE 17 — Files.find](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#find(java.nio.file.Path,int,java.util.function.BiPredicate,java.nio.file.FileVisitOption...))
- [Java SE 17 — BasicFileAttributes](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/BasicFileAttributes.html)
- [Java SE 17 — FileVisitOption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileVisitOption.html)
- [Java SE 17 — Path](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html)
