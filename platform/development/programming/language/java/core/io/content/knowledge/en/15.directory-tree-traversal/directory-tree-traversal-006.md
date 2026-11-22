# `preVisitDirectory`, `visitFile`, `visitFileFailed`, and `postVisitDirectory` in Java NIO

## 1. Why Do We Need Callbacks When Traversing a Directory Tree?

A directory can contain files, subdirectories, and many nested levels. When you want to inventory files, compute sizes, filter extensions, copy, or delete a directory tree, an application typically needs **different handling before entering a directory, upon encountering a file, when access fails, and after finishing a directory**.

Java NIO.2 provides `Files.walkFileTree(...)` paired with the `FileVisitor<Path>` interface. The four core callbacks are:

1. `preVisitDirectory` — called **before iterating the entries inside a directory**.
2. `visitFile` — called when encountering an entry treated as a **file** at the current traversal level.
3. `visitFileFailed` — called when the system **cannot access an entry** under the traversal rules.
4. `postVisitDirectory` — called **after finishing a directory**, or when an error occurs while iterating that directory's entries.

By separating these into callbacks, an algorithm can act both **on the way down** and **on the way up** the tree, instead of manually writing recursion logic, opening each directory stream, and managing every error case.

**Core point:** These are methods of a **visitor used during tree traversal**, not background events that automatically fire whenever a filesystem receives a new file. They are invoked only when the application actually executes `Files.walkFileTree`.

## 2. APIs and Class Structure

The primary components live in `java.nio.file`:

```java
Files.walkFileTree(start, visitor);
Files.walkFileTree(start, options, maxDepth, visitor);
```

Where:

- `start` is a `Path` indicating where traversal begins.
- `options` is a `Set` of `FileVisitOption`, such as `FOLLOW_LINKS`.
- `maxDepth` limits the visited depth, counting the starting directory at depth 0.
- `visitor` is an object implementing `FileVisitor<? super Path>`.
- Operations may throw `IOException`.

To avoid implementing all four methods from scratch, you normally extend **`SimpleFileVisitor<Path>`** and override only the callbacks you need.

Declaration form of `FileVisitor<T>`:

```java
FileVisitResult preVisitDirectory(
        T dir, BasicFileAttributes attrs) throws IOException;

FileVisitResult visitFile(
        T file, BasicFileAttributes attrs) throws IOException;

FileVisitResult visitFileFailed(
        T file, IOException exc) throws IOException;

FileVisitResult postVisitDirectory(
        T dir, IOException exc) throws IOException;
```

These are **API signatures for reference**, not a standalone Java file. `BasicFileAttributes` comes from `java.nio.file.attribute`. `FileVisitResult` tells the walker whether to continue, skip a subtree, skip siblings, or terminate.

The `SimpleFileVisitor` class has important default behavior:

- `preVisitDirectory(...)` and `visitFile(...)` return `CONTINUE` by default.
- `visitFileFailed(..., exc)` **rethrows** `exc` by default.
- `postVisitDirectory(..., exc)` continues by default if `exc == null`, yet **rethrows** `exc` if a directory-iteration error occurred.

Therefore, “not overriding the error callbacks” usually means **stopping and letting `IOException` propagate**, not silently ignoring failing files.

## 3. Callback Order on Successful Traversal

Consider a simple tree:

```text
root/
└── docs/
    └── note.txt
```

When no branch is skipped, the callback order can be visualized as:

```text
preVisitDirectory(root)
  preVisitDirectory(root/docs)
    visitFile(root/docs/note.txt)
  postVisitDirectory(root/docs, null)
postVisitDirectory(root, null)
```

This is **depth-first traversal**: enter the parent directory, enter the subdirectory, process the file inside, exit the subdirectory, and then exit the parent directory.

If a directory contains multiple child entries, **the order among sibling entries is not guaranteed by name, date, or size**. Programs should not write tests assuming `a.txt` is always visited before `b.txt`. When deterministic processing order is required, use a separate listing/sorting strategy rather than relying on `walkFileTree` alone.

Not every element in the tree goes through `visitFile`: normally traversed directories receive **`preVisitDirectory` and `postVisitDirectory`**, whereas files normally go through **`visitFile`**. Exceptions such as entries at `maxDepth` or unfollowed symbolic links are explained in later sections.

## 4. `preVisitDirectory` — Before Entering a Directory

Signature:

```java
@Override
public FileVisitResult preVisitDirectory(
        Path dir, BasicFileAttributes attrs) throws IOException
```

This is an **illustrative signature**, which must be placed inside a class extending `SimpleFileVisitor<Path>` with proper imports.

The callback runs when the walker recognizes a directory and **before traversing the entries inside it**. Its two arguments are:

- `dir`: `Path` of the directory about to be traversed.
- `attrs`: basic attributes read for that entry, such as `isDirectory()`, `size()`, `creationTime()`, and `lastModifiedTime()`.

Suitable tasks here:

- Logging “entering directory” and tracking depth.
- Creating a destination directory before copying child contents.
- Deciding whether to enter a branch.
- Excluding directories such as `build`, `node_modules`, or cache folders according to application policy.

Example **snippet placed inside a visitor**:

```java
@Override
public FileVisitResult preVisitDirectory(
        Path dir, BasicFileAttributes attrs) {
    if (dir.getFileName() != null
            && dir.getFileName().toString().equals("cache")) {
        return FileVisitResult.SKIP_SUBTREE;
    }
    return FileVisitResult.CONTINUE;
}
```

Here `SKIP_SUBTREE` tells the walker **not to enter the `cache` directory**. Files and subdirectories inside it do not receive their callbacks; `postVisitDirectory` is **also not called for the skipped directory itself**. Other branches can still be traversed.

Note: `preVisitDirectory` does not guarantee “opening every child entry will succeed” — as traversal continues, directory-reading or attribute-reading errors can still occur.

## 5. `visitFile` — Processing an Entry Visited as a File

Signature:

```java
@Override
public FileVisitResult visitFile(
        Path file, BasicFileAttributes attrs) throws IOException
```

This is an **illustrative signature**, not a standalone program.

Normally `visitFile` is called for **non-directory entries**. It receives `Path` and `BasicFileAttributes` so the application can decide what to do:

- Count files and sum sizes (according to `attrs.size()` semantics).
- Check file extensions or names.
- Copy the file elsewhere.
- Read contents, compute hashes, or validate formats.
- Delete the file when executing an authorized task.

File-counting example:

```java
@Override
public FileVisitResult visitFile(
        Path file, BasicFileAttributes attrs) {
    if (attrs.isRegularFile()) {
        count++;
    }
    return FileVisitResult.CONTINUE;
}
```

This **illustrative** snippet lives inside a visitor with a `long count` field. Use `attrs.isRegularFile()` if you only want to count regular files; do not assume every entry passed to `visitFile` is a regular file under all traversal options.

Specifically:

- When **not following symbolic links**, a link is normally visited as a single entry without traversing the link target's tree.
- When **`maxDepth`** is reached, a directory entry may also be passed to `visitFile` instead of descending further and calling `preVisitDirectory` for it.
- If reading basic attributes for an entry fails, the walker may invoke **`visitFileFailed`** instead of `visitFile`.

`visitFile` does not mean file contents have been opened or read. It only signals that traversal reached that entry according to visitor rules.

## 6. `postVisitDirectory` — After Visiting Child Entries

Signature:

```java
@Override
public FileVisitResult postVisitDirectory(
        Path dir, IOException exc) throws IOException
```

This is an **illustrative signature**, placed inside a visitor.

The callback is invoked after iterating the entries inside a directory, or when iterating its entries fails. Unlike `preVisitDirectory`, the second argument is **not attributes**, but instead:

- `null` when directory iteration completed normally.
- `IOException exc` when an error occurred during directory iteration, terminating iteration abnormally.

Common handling pattern:

```java
@Override
public FileVisitResult postVisitDirectory(
        Path dir, IOException exc) throws IOException {
    if (exc != null) {
        throw exc;
    }
    System.out.println("Xong thư mục: " + dir);
    return FileVisitResult.CONTINUE;
}
```

This spot is ideal for **post-order** work:

- Finalizing summaries aggregated from subdirectories.
- Completing or closing an application structure corresponding to the directory.
- Deleting the directory **after** deleting its child files and subdirectories in a controlled tree-deletion workflow.
- Recording “exited directory” to balance state in an algorithm.

**Do not assume `postVisitDirectory` always runs for every directory.** If `preVisitDirectory` returns `SKIP_SUBTREE`/`SKIP_SIBLINGS` for a directory, the walker does not enter it and does not call the post-visit callback for the skipped directory. If the visitor throws an exception or returns `TERMINATE` midway, post-visit callbacks for unfinished ancestors are **not guaranteed**. When resource release is strictly required, use `try/finally` or `try-with-resources` in the owning scope rather than relying solely on post-visit callbacks.

Also, errors thrown **inside `visitFile`** by business logic are not automatically turned into `exc` in `postVisitDirectory`; in many cases, exceptions propagate directly out of `walkFileTree`.

## 7. `visitFileFailed` — When an Entry Cannot Be Accessed

Signature:

```java
@Override
public FileVisitResult visitFileFailed(
        Path file, IOException exc) throws IOException
```

This is an **illustrative signature**, not a standalone program.

This callback may be invoked when:

- Basic attributes of an entry cannot be read.
- A directory cannot be opened for traversal.
- An I/O error occurs while following symbolic links, such as a link cycle with `FOLLOW_LINKS`.
- The path was deleted or changed before the system accessed it.

`exc` holds the I/O cause. Example:

```java
@Override
public FileVisitResult visitFileFailed(
        Path file, IOException exc) throws IOException {
    System.err.println("Không thể thăm " + file
            + ": " + exc.getClass().getSimpleName());
    return FileVisitResult.CONTINUE;
}
```

If it returns `CONTINUE`, the walker **skips the failing entry and tries to continue with remaining entries** where possible. This is useful for “best effort” inventory tasks, yet **is not equivalent to successfully traversing the whole tree**. Programs should record failed entries and avoid reporting “100% complete” when data was skipped.

To **fail fast**, simply write:

```java
@Override
public FileVisitResult visitFileFailed(
        Path file, IOException exc) throws IOException {
    throw exc;
}
```

`SimpleFileVisitor` also rethrows the exception here by default.

**Distinguishing from `postVisitDirectory(dir, exc)`:**

| Scenario | Appropriate Callback |
| --- | --- |
| Cannot read attributes of an entry | `visitFileFailed` |
| Cannot open a directory for listing | `visitFileFailed` |
| Opened directory, then hit an error iterating its entries | `postVisitDirectory` with `exc != null` |
| Application throws `IOException` inside `visitFile` | Normally propagates out of traversal; **not** automatically routed to `visitFileFailed` |

This helps distinguish **traversal system errors** from **errors in the visitor's own business processing**.

## 8. `FileVisitResult` — Four Flow-Control Decisions

The four callbacks return a value from the `FileVisitResult` enum:

| Value | Effect |
| --- | --- |
| `CONTINUE` | Continue normal traversal |
| `TERMINATE` | Stop the entire traversal; visit nothing further |
| `SKIP_SUBTREE` | When returned from `preVisitDirectory`, do not traverse that directory's subtree |
| `SKIP_SIBLINGS` | Skip unvisited sibling entries at the same level and their descendants |

Contextual details matter greatly:

- `SKIP_SUBTREE` has real effect only in **`preVisitDirectory`**; if returned from `visitFile`, where there is no subtree to traverse, it behaves like `CONTINUE`.
- `SKIP_SIBLINGS` can prevent visiting remaining entries under the same parent directory, so do not use it merely to “skip the current file.”
- When you want to skip **one directory and all its contents while still visiting other directories at the same level**, return `SKIP_SUBTREE` from `preVisitDirectory`.
- `TERMINATE` exits early; it is not automatically an error signal. The caller must decide whether an early-stopped walk is a valid or incomplete result.
- Never return `null`: callbacks must return a valid `FileVisitResult` value.

Policy examples:

```text
Detect cache directory                  → SKIP_SUBTREE in preVisitDirectory
Process normal file successfully        → CONTINUE in visitFile
Cannot read entry but skipping allowed  → CONTINUE in visitFileFailed
Found target result and want to stop    → TERMINATE
Finish directory without error          → CONTINUE in postVisitDirectory
```

**Be cautious with `SKIP_SIBLINGS`:** “which siblings have not been visited yet” depends on filesystem enumeration order; never assume filenames follow alphabetical order.

## 9. Runnable Java 17+ Program: Observing Exact Callback Order

Create file **`TreeCallbacksDemo.java`**:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;

public class TreeCallbacksDemo {
    private static String label(Path root, Path path) {
        String relative = root.relativize(path).toString()
                .replace('\\', '/');
        return relative.isEmpty() ? "." : relative;
    }

    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("callback-demo-");
        Path sub = root.resolve("docs");
        Path note = sub.resolve("note.txt");

        try {
            Files.createDirectory(sub);
            Files.writeString(note, "Hello", StandardCharsets.UTF_8);

            FileVisitor<Path> visitor = new SimpleFileVisitor<>() {
                @Override
                public FileVisitResult preVisitDirectory(
                        Path dir, BasicFileAttributes attrs) {
                    System.out.println("PRE " + label(root, dir));
                    return FileVisitResult.CONTINUE;
                }

                @Override
                public FileVisitResult visitFile(
                        Path file, BasicFileAttributes attrs) {
                    System.out.println("FILE " + label(root, file));
                    return FileVisitResult.CONTINUE;
                }

                @Override
                public FileVisitResult visitFileFailed(
                        Path file, IOException exc) throws IOException {
                    System.out.println("FAIL " + label(root, file));
                    throw exc;
                }

                @Override
                public FileVisitResult postVisitDirectory(
                        Path dir, IOException exc) throws IOException {
                    if (exc != null) {
                        throw exc;
                    }
                    System.out.println("POST " + label(root, dir));
                    return FileVisitResult.CONTINUE;
                }
            };

            Files.walkFileTree(root, visitor);
        } finally {
            Files.deleteIfExists(note);
            Files.deleteIfExists(sub);
            Files.deleteIfExists(root);
        }
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac -encoding UTF-8 TreeCallbacksDemo.java
java TreeCallbacksDemo
```

Output when temporary file creation and traversal succeed:

```text
PRE .
PRE docs
FILE docs/note.txt
POST docs
POST .
```

The example intentionally uses **one** subdirectory and **one** file so the order does not depend on sibling sorting. The temporary directory has a random name, yet `label` converts paths to relative form so stdout is consistent on Windows and `/` separator operating systems.

In this program:

- `PRE .` is the callback before listing the root directory.
- `PRE docs` is the callback before entering `docs`.
- `FILE docs/note.txt` is the file visit.
- `POST docs` followed by `POST .` reflects unwinding from leaves back up to the root.
- There is no `FAIL` because every entry is accessible.
- The `finally` block deletes only paths **created by the program itself**. If cleanup fails, `IOException` can still be thrown; do not apply this deletion logic verbatim to user data.

## 10. Runnable Program: Skipping an Entire Branch While Visiting Others

`SKIP_SUBTREE` shows its behavior most clearly when the skipped directory contains files inside it. To avoid depending on sibling order, this example records visited entries and prints conclusions **after traversal**.

Create file **`SkipSubtreeDemo.java`**:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.HashSet;
import java.util.Set;

public class SkipSubtreeDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("skip-demo-");
        Path keep = root.resolve("keep");
        Path skip = root.resolve("skip");
        Path visible = keep.resolve("visible.txt");
        Path hidden = skip.resolve("hidden.txt");

        try {
            Files.createDirectory(keep);
            Files.createDirectory(skip);
            Files.writeString(visible, "ok", StandardCharsets.UTF_8);
            Files.writeString(hidden, "ignored", StandardCharsets.UTF_8);

            Set<Path> entered = new HashSet<>();
            Set<Path> files = new HashSet<>();
            Set<Path> exited = new HashSet<>();

            Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
                @Override
                public FileVisitResult preVisitDirectory(
                        Path dir, BasicFileAttributes attrs) {
                    entered.add(dir);
                    return dir.equals(skip)
                            ? FileVisitResult.SKIP_SUBTREE
                            : FileVisitResult.CONTINUE;
                }

                @Override
                public FileVisitResult visitFile(
                        Path file, BasicFileAttributes attrs) {
                    files.add(file);
                    return FileVisitResult.CONTINUE;
                }

                @Override
                public FileVisitResult postVisitDirectory(
                        Path dir, IOException exc) throws IOException {
                    if (exc != null) {
                        throw exc;
                    }
                    exited.add(dir);
                    return FileVisitResult.CONTINUE;
                }
            });

            System.out.println("entered skip=" + entered.contains(skip));
            System.out.println("visited hidden=" + files.contains(hidden));
            System.out.println("post skip=" + exited.contains(skip));
            System.out.println("visited visible=" + files.contains(visible));
            System.out.println("post root=" + exited.contains(root));
        } finally {
            Files.deleteIfExists(visible);
            Files.deleteIfExists(hidden);
            Files.deleteIfExists(keep);
            Files.deleteIfExists(skip);
            Files.deleteIfExists(root);
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 SkipSubtreeDemo.java
java SkipSubtreeDemo
```

Output:

```text
entered skip=true
visited hidden=false
post skip=false
visited visible=true
post root=true
```

Entries inside `skip` are not traversed, while `keep/visible.txt` is still visited. Because `skip` was excluded from `preVisitDirectory`, the program does not receive `postVisitDirectory(skip, ...)`.

Do not write tests assuming `keep` or `skip` appears first: enumeration order can differ across operating systems and filesystems.

## 11. Runnable Program: `visitFileFailed` and Error-Skipping Strategy

This example uses a **nonexistent path inside a newly created temporary directory** to simulate failure to retrieve attributes. That avoids altering permissions or mocking a broken filesystem.

Create file **`FileVisitFailureDemo.java`**:

```java
import java.io.IOException;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;

public class FileVisitFailureDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("failure-demo-");
        Path missing = root.resolve("missing.txt");

        try {
            Files.walkFileTree(missing, new SimpleFileVisitor<Path>() {
                @Override
                public FileVisitResult visitFileFailed(
                        Path file, IOException exc) {
                    System.out.println("Failed: "
                            + file.getFileName());
                    return FileVisitResult.CONTINUE;
                }
            });
            System.out.println("Traversal returned");
        } finally {
            Files.deleteIfExists(root);
        }
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 FileVisitFailureDemo.java
java FileVisitFailureDemo
```

Output on a default filesystem supporting standard temporary directory operations:

```text
Failed: missing.txt
Traversal returned
```

Because `missing.txt` does not exist, the walker cannot read its attributes and invokes `visitFileFailed`. The callback returns `CONTINUE`, so `walkFileTree` finishes without **rethrowing the error**. That does not mean the file was visited successfully; the application is responsible for accurately reporting skipped entries.

If the callback executed `throw exc;`, the program would report the exception to the caller. In production systems, the concrete error type may be `NoSuchFileException`, `AccessDeniedException`, `FileSystemLoopException`, or another `IOException` depending on the scenario and provider.

## 12. Directory Iteration Errors vs. Errors in Visitor Code

A trickier case: a directory **opens successfully**, but reading its entry list fails mid-way. Then `postVisitDirectory(dir, exc)` can receive `exc != null`.

Example fail-fast policy snippet:

```java
@Override
public FileVisitResult postVisitDirectory(
        Path dir, IOException exc) throws IOException {
    if (exc != null) {
        throw new IOException(
                "Lỗi khi duyệt các mục trong " + dir, exc);
    }
    return FileVisitResult.CONTINUE;
}
```

This is an **illustrative snippet** to place inside a visitor. Because simulating a reliable directory-iterator error across all filesystems is difficult, no fixed stdout is shown.

Conversely, if `visitFile` contains code like:

```java
@Override
public FileVisitResult visitFile(
        Path file, BasicFileAttributes attrs) throws IOException {
    processFile(file);  // may throw IOException
    return FileVisitResult.CONTINUE;
}
```

This is an **illustrative snippet**: `processFile` is an application method, not a standard Java API. An `IOException` thrown by `processFile` normally **exits `walkFileTree`** rather than automatically routing to `visitFileFailed`. Do not treat the two error callbacks as a “catch-all” replacement for application exception management.

If the application wants to continue when reading **a single file's** contents fails, explicitly use `try/catch` inside `visitFile`, record the failure state, and return `CONTINUE` according to a defined policy.

## 13. `maxDepth`, Symbolic Links, and Cycles

### Depth Limits

The `Files.walkFileTree(start, options, maxDepth, visitor)` overload lets you set a maximum depth. `start` is at depth 0. For instance, `maxDepth = 1` will not descend into the contents of directories at depth 1.

Subtle detail: **directories encountered at maximum depth may be passed to `visitFile`**, because traversal does not open them as directories to descend into further. Therefore, if you only want to count regular files, check `attrs.isRegularFile()` inside `visitFile`.

`maxDepth < 0` is invalid. When practically unbounded traversal is needed, the simpler overload uses the corresponding default traversal depth.

### Symbolic Links

By default, `walkFileTree` **does not follow symbolic links**. Thus a symbolic link to a directory does not automatically become a traversed subtree. You can configure:

```java
Files.walkFileTree(
        root,
        java.util.EnumSet.of(FileVisitOption.FOLLOW_LINKS),
        10,
        visitor);
```

This is an **illustrative snippet**, requiring `Path root`, `FileVisitor<Path> visitor`, imports for `Files` and `FileVisitOption`, and `IOException` handling.

Following links can lead to **cycles**, such as A pointing to B and B pointing to A, or a subdirectory pointing back to an ancestor. Java includes loop detection in follow-links mode; errors such as `FileSystemLoopException` can be delivered to `visitFileFailed`. Never enable `FOLLOW_LINKS` thoughtlessly when deleting or copying important data; decide explicitly whether to act on the link itself or its target.

### The Tree Can Change Mid-Traversal

The filesystem is not an immutable snapshot: files may be renamed, deleted, have permissions changed, or have contents altered while traversal runs. The `attrs` object is captured during visitation and **may already be stale** by the time you process file contents. If you must process data with strict consistency requirements, apply snapshots, write-access coordination, or application-level verification.

## 14. Choosing the Right Callback for Each Task

| Task | Usually Best Callback | Reason |
| --- | --- | --- |
| Log “entering directory” | `preVisitDirectory` | Runs before seeing children |
| Exclude an entire cache branch | `preVisitDirectory` with `SKIP_SUBTREE` | Avoids entering the branch |
| Create target directory structure when copying | `preVisitDirectory` | Parent directory must exist before children |
| Count regular files, sum total size | `visitFile` | Provides the entry's `BasicFileAttributes` |
| Read or copy a file's contents | `visitFile` | Provides the file `Path` to process |
| Record inaccessible files | `visitFileFailed` | Receives the failure cause |
| Handle directory listing iteration errors | `postVisitDirectory` with `exc != null` | Error happened while iterating child entries |
| Aggregate results from a sub-branch | `postVisitDirectory` | All children in the branch have been visited |
| Delete a directory after deleting all children | `postVisitDirectory` | Post-order |
| Stop searching once the desired item is found | `visitFile` returning `TERMINATE` | No need to continue scanning the rest of the tree |

### Post-Order Deletion Example — Illustrative Snippet Only

```java
Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
    @Override
    public FileVisitResult visitFile(
            Path file, BasicFileAttributes attrs)
            throws IOException {
        Files.delete(file);
        return FileVisitResult.CONTINUE;
    }

    @Override
    public FileVisitResult postVisitDirectory(
            Path dir, IOException exc)
            throws IOException {
        if (exc != null) {
            throw exc;
        }
        Files.delete(dir);
        return FileVisitResult.CONTINUE;
    }
});
```

**This is not a standalone program**: it requires `Path root`, imports, and `IOException` handling. The snippet **genuinely deletes** every file/directory under `root` that the application has permission to remove; use it only on test data you created yourself or with explicit confirmation. Unlike deleting top-down (which readily hits `DirectoryNotEmptyException`), post-order lets you delete files and subdirectories before deleting the parent.

For directories holding important data, you must evaluate symbolic links, permissions, concurrent changes, error handling, and recovery options. `walkFileTree` does not turn the whole deletion into a transaction.

## 15. Comparing `Files.walkFileTree` with `Files.walk`

Both help traverse a directory tree, yet differ in interface and error handling:

| Feature | `Files.walkFileTree` | `Files.walk` |
| --- | --- | --- |
| Processing API | Visitor with explicit callbacks | `Stream<Path>`, combined with `filter`/`map`/`forEach` |
| Before/after directory | Has `preVisitDirectory` and `postVisitDirectory` | No direct equivalent callbacks |
| Errors during traversal | `visitFileFailed`, `postVisitDirectory(exc)`, `IOException` | Some traversal errors may surface as `UncheckedIOException` |
| Skip entire branch via visitor logic | `SKIP_SUBTREE` | No corresponding `preVisitDirectory` callback for pruning |
| Resource closing | API manages traversal internally | `Stream<Path>` requires `try-with-resources` to close |
| When suitable | Copying/deleting/sizing trees, logging enter–exit directories, contextual error handling | Path filtering/listing pipelines |

Do not use `Files.walk(root).filter(...)` expecting filtering out a directory to automatically stop the system from entering its children; Stream filters decide on **elements after they are emitted**, not like a visitor's `SKIP_SUBTREE`.

If a task needs to know exact before/after directory boundaries or needs fine-grained control when access fails, `walkFileTree` is usually clearer to express.

## 16. Common Mistakes and How to Avoid Them

| Mistake | Consequence | Right Approach |
| --- | --- | --- |
| Thinking `preVisitDirectory` runs after visiting children | Creating targets or tracking state at the wrong time | Remember it is a **pre-**visit callback |
| Counting every `visitFile` entry as a regular file | Counts symlinks or directories at `maxDepth` | Check `attrs.isRegularFile()` |
| Thinking `postVisitDirectory` always runs | Incomplete cleanup when skipped/terminated/thrown | Use `try/finally` for mandatory cleanup |
| Ignoring `exc` in `postVisitDirectory` | Reports complete traversal despite directory errors | Check, record, or rethrow the error |
| Returning `CONTINUE` in `visitFileFailed` yet reporting total success | Hides unreadable files/directories | Collect an error list and mark “incomplete” |
| Assuming `processFile` errors automatically route to `visitFileFailed` | Misses catching exceptions in the right place | Handle checked exceptions in the visitor or around `walkFileTree` |
| Using `SKIP_SIBLINGS` to skip one directory while still wanting its siblings | Skips remaining unvisited siblings too | Return `SKIP_SUBTREE` from `preVisitDirectory` |
| Assuming siblings always follow name order | Output varies across machines or filesystems | Do not depend on order, or sort explicitly |
| Following symlinks without handling cycles | Can hit `FileSystemLoopException` or process wrong targets | Define link and error policies |
| Using `Files.walk` and forgetting to close the `Stream` | System resource leak | `try-with-resources` |
| Using a deletion visitor without checking real root | Can accidentally delete an entire directory tree | Act only on verified, authorized roots |
| Treating every `IOException` as “file does not exist” | Misses permission, device, and link errors | Inspect the concrete error type and cause |

## 17. Visitor Design Checklist and Self-Practice Exercises

**Before traversing a tree:**

- [ ] Choose the right `start`; avoid acting on the wrong data tree.
- [ ] Clarify the goal: listing, filtering, copying, aggregating, or deleting.
- [ ] Pick symbolic-link rules and `maxDepth`.
- [ ] Decide which callbacks to override and which can use defaults.
- [ ] Return `CONTINUE`, `SKIP_SUBTREE`, `SKIP_SIBLINGS`, or `TERMINATE` according to required semantics.
- [ ] Define handling when accessing an entry fails and when directory iteration errors occur.
- [ ] Avoid relying on sibling order.
- [ ] Ensure application resource cleanup does not rely solely on `postVisitDirectory`.

**Exercise 1 — Callback order:** Create a tree `root/a/x.txt` and `root/a/b/y.txt`, where each directory has a single child entry, and print `PRE`, `FILE`, `POST`. Trace the exact depth-first callback sequence and explain why `POST a/b` appears before `POST a`.

**Exercise 2 — Exclusion:** Add a branch `root/cache/temp.txt` and have `preVisitDirectory` return `SKIP_SUBTREE` when encountering `cache`. Verify that `temp.txt` never passes through `visitFile` and `postVisitDirectory(cache, ...)` is not called, while other branches are still traversed.

**Exercise 3 — Errors:** Inside a temporary directory, call `Files.walkFileTree` on a nonexistent path. Try two versions of `visitFileFailed`: returning `CONTINUE` and `throw exc`. Compare normal method completion with throwing `IOException`.

**Exercise 4 — Post-order:** On a temporary tree with two directory levels, use `visitFile` to delete files and `postVisitDirectory` to delete directories. Why can deleting the parent directory before removing its contents cause `DirectoryNotEmptyException`?

**Takeaway:** `preVisitDirectory` runs **before** directory contents; `visitFile` handles entries visited as files; `visitFileFailed` reports **inaccessible entries**; `postVisitDirectory` runs **after** directory contents or receives directory-iteration errors. `FileVisitResult` controls continuing, skipping a branch, skipping siblings, or terminating altogether. Understanding exact ordering and exceptions enables safe, accurate, and testable tree traversal on Java 17+.
