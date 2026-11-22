# `FileVisitResult`: Continue, Skip Branch, or Terminate When Traversing a Directory Tree

## 1. The Problem: Controlling Directory Tree Traversal

When Java traverses a multi-level directory, an application often does not want to treat every file the same way. We may need to:

- Traverse the whole tree to gather file statistics.
- **Skip an entire branch** such as `.git`, `node_modules`, or a directory outside the processing scope.
- **Skip remaining entries at the same level** after finding a suitable match.
- **Stop the entire traversal** immediately once a result is found or a critical condition occurs.
- Continue after an individual read error, or halt when integrity can no longer be guaranteed.

Java NIO.2 provides `Files.walkFileTree(...)` to traverse the tree and `FileVisitor`/`SimpleFileVisitor` to receive events. After each callback, we return a **`FileVisitResult`**, which instructs the traversal mechanism: continue, skip the subtree, skip siblings at the same level, or terminate.

```text
root/
├── src/
│   ├── Main.java
│   └── App.java
├── build/
│   └── generated.bin
└── README.md

preVisitDirectory(root) → CONTINUE
  preVisitDirectory(src) → CONTINUE
    visitFile(Main.java) → CONTINUE
    visitFile(App.java) → CONTINUE
  postVisitDirectory(src) → CONTINUE
  preVisitDirectory(build) → SKIP_SUBTREE
    generated.bin IS NOT visited
  visitFile(README.md) → CONTINUE
postVisitDirectory(root) → CONTINUE
```

This is an **illustrative diagram**, not a guaranteed traversal order. Entry order within a directory depends on the filesystem/provider; if sorted order is needed, design an explicit sorting step instead of assuming the walker visits alphabetically.

Core takeaway of this lesson: **a `FileVisitResult` value takes effect according to which callback returns it**, and “skip subtree” differs fundamentally from “skip siblings” or “terminate.”

## 2. Starting a Traversal with `Files.walkFileTree`

Basic API:

```java
Files.walkFileTree(start, visitor);
```

`start` is a `Path`; `visitor` implements `FileVisitor<? super Path>`. `Files.walkFileTree` traverses **depth-first**: for a directory, it invokes a callback before entering its entries; after entries are processed, it invokes the post-visit callback (excluding skipped subtrees, early termination, and contractual exceptions).

An overload allows configuring link-following and depth bounds:

```java
Files.walkFileTree(
        start,
        EnumSet.noneOf(FileVisitOption.class),
        4,
        visitor);
```

This is an **illustrative snippet**, requiring imports from `java.nio.file` and `java.util.EnumSet`, plus declared `start` and `visitor` variables. `maxDepth = 4` sets the maximum depth. Choosing `EnumSet.noneOf(FileVisitOption.class)` means **`FOLLOW_LINKS` is not enabled**; by default, symbolic links are not automatically followed like regular directories.

`Files.walkFileTree` normally returns `start` itself when traversal completes per contract, while flow control is driven by callbacks. It can throw `IOException` (for example, if a callback throws), not just return enum values.

### When Should You Use `FileVisitor` Instead of `Files.walk`?

`Files.walk(start)` returns a lazy `Stream<Path>`, suitable for straightforward filtering and listing. However, `FileVisitor` lets you **decide at each directory whether to enter that branch**, as well as receive dedicated before/after directory callbacks and failure callbacks.

If you need to **prune** a branch before the walker descends into it, `preVisitDirectory` combined with `SKIP_SUBTREE` is the direct tool. `Stream.filter(path -> ...)` on `Files.walk` only filters elements **emitted into the pipeline**, without promising that the walker avoids opening or entering filtered-out branches.

## 3. `FileVisitor` Has Four Callbacks

`FileVisitor<Path>` defines four methods:

| Callback | When Called? | Important Parameters |
| --- | --- | --- |
| `preVisitDirectory(Path dir, BasicFileAttributes attrs)` | Before entering the entries of a directory | `dir`, directory attributes |
| `visitFile(Path file, BasicFileAttributes attrs)` | When visiting a file/entry not entered as a directory; depending on depth limits, a directory may also pass here | `file`, attributes |
| `visitFileFailed(Path file, IOException exc)` | When an entry cannot be visited, e.g., error reading attributes/opening directory | `file`, failure cause |
| `postVisitDirectory(Path dir, IOException exc)` | After finishing visiting the directory's entries/descendants, or when traversal ends early where permitted | `dir`, iteration error if any |

`preVisitDirectory` and `postVisitDirectory` are not merely informational. They also return `FileVisitResult` to guide the next step. For example, pre/post directory callbacks are essential for a tree-deletion algorithm: deleting the directory after visiting its children is crucial.

`BasicFileAttributes` belongs to `java.nio.file.attribute` and offers methods such as `isDirectory()`, `isRegularFile()`, `isSymbolicLink()`, `size()`, and timestamps, helping avoid extra filesystem calls.

### Why Extend `SimpleFileVisitor`?

Implementing `FileVisitor<Path>` directly requires writing all four callbacks. In many tasks, you only need to override one or two methods and let `SimpleFileVisitor<Path>` supply the rest.

`SimpleFileVisitor` defaults basically behave as:

- `preVisitDirectory`: `CONTINUE`.
- `visitFile`: `CONTINUE`.
- `visitFileFailed`: rethrows the passed-in `IOException`.
- `postVisitDirectory`: `CONTINUE` if `exc == null`, otherwise rethrows the error.

Therefore, if you want to **ignore errors for inaccessible files** instead of letting an exception abort traversal, you must explicitly override `visitFileFailed`. And if you want to avoid entering a directory, overriding `preVisitDirectory` is sufficient.

## 4. The Four Values of `FileVisitResult`

The `java.nio.file.FileVisitResult` enum has exactly four constants:

| Value | Main Effect | Scope |
| --- | --- | --- |
| `CONTINUE` | Continue traversal | Normal progression along the traversal schedule |
| `SKIP_SUBTREE` | Do not traverse entries inside the **current directory** | Has special effect only in `preVisitDirectory` |
| `SKIP_SIBLINGS` | Do not traverse **remaining sibling entries** at the same level as the current entry | Does not mean stopping the entire tree |
| `TERMINATE` | Stop the entire traversal | Entire walker |

Remember: `FileVisitResult` is a **control value**, not an exception, and does not mean “file read succeeded.” Any callback can also throw `IOException` per its signature; that exception terminates the walker unless handled appropriately in the visitor.

### 4.1 `CONTINUE`: Keep Going

`CONTINUE` is the common default case. When returned from `preVisitDirectory(dir)`, the walker attempts to traverse entries inside `dir`. When returned from `visitFile(file)`, the walker proceeds to the next eligible element.

```java
@Override
public FileVisitResult visitFile(Path file, BasicFileAttributes attrs) {
    System.out.println(file.getFileName());
    return FileVisitResult.CONTINUE;
}
```

This is a **method inside a visitor**, not a standalone program. Returning `CONTINUE` does not guarantee every file is visited successfully; I/O errors, unreadable directories, depth bounds, or other skipped branches can still occur.

### 4.2 `SKIP_SUBTREE`: Skip a Branch

`SKIP_SUBTREE` has special meaning when returned from **`preVisitDirectory(dir)`**. The walker **does not enter that directory's entries**. For a directory skipped this way, `postVisitDirectory(dir)` **is not called**.

```java
@Override
public FileVisitResult preVisitDirectory(
        Path dir, BasicFileAttributes attrs) {
    if (dir.getFileName() != null
            && dir.getFileName().toString().equals("build")) {
        return FileVisitResult.SKIP_SUBTREE;
    }
    return FileVisitResult.CONTINUE;
}
```

This is an **illustrative snippet**, requiring imports for `Path`, `BasicFileAttributes`, and `FileVisitResult`. Upon encountering `build`, the `build` branch is not expanded, while sibling items at the same level can still be traversed.

**Subtlety:** if `SKIP_SUBTREE` is returned from `visitFile`, `visitFileFailed`, or `postVisitDirectory`, the enum Javadoc states it behaves **the same as `CONTINUE`**. Do not return `SKIP_SUBTREE` from `visitFile` hoping to skip the remaining files in the same directory.

### 4.3 `SKIP_SIBLINGS`: Skip Same-Level Siblings

`SKIP_SIBLINGS` tells the walker not to visit **unvisited sibling entries** of the current file or directory.

There are two prominent cases:

1. Returned from **`visitFile(file)`**: stops visiting remaining entries in the same parent directory; the walker can then continue processing at higher ancestor levels.
2. Returned from **`preVisitDirectory(dir)`**: **does not enter `dir` itself**, does not call `postVisitDirectory(dir)`, and skips unvisited siblings of `dir`.

When returned from `postVisitDirectory(dir)`, it means skipping remaining siblings of `dir` in the parent directory. When returned from `visitFileFailed`, it can likewise skip unvisited siblings of the failing entry.

```java
@Override
public FileVisitResult visitFile(Path file, BasicFileAttributes attrs) {
    if (file.getFileName().toString().equals("stop-here.flag")) {
        return FileVisitResult.SKIP_SIBLINGS;
    }
    return FileVisitResult.CONTINUE;
}
```

**Do not confuse `SKIP_SIBLINGS` with `TERMINATE`.** The former only omits **unvisited entries at the same level**, so the walker can still climb back up the tree and traverse other branches. The latter halts the entire traversal.

**No guaranteed ordering:** if a target file is found among siblings, `SKIP_SIBLINGS` does not rewind to “undo already-visited entries,” nor does it guarantee which file in the directory is visited first. Do not use it to pick “the alphabetically smallest file” without explicit sorting.

### 4.4 `TERMINATE`: Stop Immediately

`TERMINATE` is the deliberate way to stop **the entire traversal**. For example:

```java
@Override
public FileVisitResult visitFile(Path file, BasicFileAttributes attrs) {
    if (file.getFileName().toString().equals("found.txt")) {
        found = file;
        return FileVisitResult.TERMINATE;
    }
    return FileVisitResult.CONTINUE;
}
```

This is an **illustrative snippet** inside a visitor having a `Path found` field. Once the callback returns `TERMINATE`, the walker stops calling further visit methods. Do not expect `postVisitDirectory` to run for directories still on the stack. If business resources were opened inside the visitor, manage closing them yourself instead of assuming post-visit acts like `finally`.

**Defining “successful completion”:** `TERMINATE` itself is not an error. `Files.walkFileTree` can return normally after the visitor requests stopping; if the caller needs to know what was found, store state or expose results explicitly (such as the `found` variable).

## 5. Matrix: Which Value Returned From Which Callback?

| Callback | `CONTINUE` | `SKIP_SUBTREE` | `SKIP_SIBLINGS` | `TERMINATE` |
| --- | --- | --- | --- | --- |
| `preVisitDirectory` | Enter directory | Do not enter subtree; do not call post for this dir | Do not enter dir, do not call post; skip dir's siblings | Stop everything |
| `visitFile` | Proceed to next entry | Equivalent to `CONTINUE` | Skip file's unvisited siblings | Stop everything |
| `visitFileFailed` | Ignore entry error and keep going | Equivalent to `CONTINUE` | Skip failing entry's unvisited siblings | Stop everything |
| `postVisitDirectory` | Continue after directory | Equivalent to `CONTINUE` | Skip directory's unvisited siblings | Stop everything |

Two facts worth memorizing:

- **Only `preVisitDirectory` uses `SKIP_SUBTREE` to block descending into a directory**. Do not return it from `postVisitDirectory` thinking it alters already-visited entries.
- **`SKIP_SIBLINGS` from `preVisitDirectory` skips both that directory's own subtree and its unvisited siblings**. It is stronger than `SKIP_SUBTREE`.

When a callback returns `SKIP_SIBLINGS` for a visited file inside a directory, iteration of that directory ends early; the `FileVisitor` documentation notes that `postVisitDirectory` for that directory may still be invoked after that early termination of iteration.

## 6. Runnable Java 17 Example: Using `SKIP_SUBTREE` While Traversing Other Branches

This example creates a small tree in a temporary directory with only two subdirectories, `keep` and `ignored`. The visitor skips the `ignored` branch regardless of the filesystem's enumeration order. Output uses counts rather than relying on event order.

**File `SkipSubtreeDemo.java`:**

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;

public class SkipSubtreeDemo {
    static final class Visitor extends SimpleFileVisitor<Path> {
        int seenFiles;
        int enteredDirectories;
        boolean ignoredPostCalled;

        @Override
        public FileVisitResult preVisitDirectory(
                Path dir, BasicFileAttributes attrs) {
            if (dir.getFileName() != null
                    && dir.getFileName().toString().equals("ignored")) {
                return FileVisitResult.SKIP_SUBTREE;
            }
            enteredDirectories++;
            return FileVisitResult.CONTINUE;
        }

        @Override
        public FileVisitResult visitFile(
                Path file, BasicFileAttributes attrs) {
            seenFiles++;
            return FileVisitResult.CONTINUE;
        }

        @Override
        public FileVisitResult postVisitDirectory(
                Path dir, IOException exc) throws IOException {
            if (dir.getFileName() != null
                    && dir.getFileName().toString().equals("ignored")) {
                ignoredPostCalled = true;
            }
            if (exc != null) {
                throw exc;
            }
            return FileVisitResult.CONTINUE;
        }
    }

    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("walk-result-");
        Path keep = root.resolve("keep");
        Path ignored = root.resolve("ignored");

        try {
            Files.createDirectory(keep);
            Files.createDirectory(ignored);
            Files.writeString(keep.resolve("a.txt"), "ok",
                    StandardCharsets.UTF_8);
            Files.writeString(ignored.resolve("hidden.txt"), "secret",
                    StandardCharsets.UTF_8);

            Visitor visitor = new Visitor();
            Files.walkFileTree(root, visitor);

            System.out.println("Entered dirs: "
                    + visitor.enteredDirectories);
            System.out.println("Visited files: " + visitor.seenFiles);
            System.out.println("Ignored post called: "
                    + visitor.ignoredPostCalled);
        } finally {
            Files.deleteIfExists(keep.resolve("a.txt"));
            Files.deleteIfExists(ignored.resolve("hidden.txt"));
            Files.deleteIfExists(keep);
            Files.deleteIfExists(ignored);
            Files.deleteIfExists(root);
        }
    }
}
```

Compile and run:

```bash
javac SkipSubtreeDemo.java
java SkipSubtreeDemo
```

**Exact stdout when I/O operations succeed:**

```text
Entered dirs: 2
Visited files: 1
Ignored post called: false
```

Explanation: `preVisitDirectory` for `root` and `keep` returns `CONTINUE`, so `enteredDirectories = 2`. The `ignored` branch is recognized in pre-visit and returns `SKIP_SUBTREE`, so `hidden.txt` is not visited and `postVisitDirectory(ignored)` does not happen. The file `a.txt` in `keep` is still visited.

This is a **self-controlled tree structure example**. In real environments, the filesystem may change concurrently or permissions may differ from expectations, so when errors or cleanup issues happen, the program may throw `IOException` instead of printing those lines.

## 7. Java 17 Example: `SKIP_SIBLINGS` Is Not `TERMINATE`

Create a tree where the `group` directory contains two files; after visiting the first file (which comes first is unspecified), the visitor returns `SKIP_SIBLINGS`. Not both files are visited, yet the parent directory can still complete its post callback. The example uses counts so it does not depend on ordering:

**File `SkipSiblingsDemo.java`:**

```java
import java.io.IOException;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;

public class SkipSiblingsDemo {
    static class Visitor extends SimpleFileVisitor<Path> {
        int filesVisited;
        boolean groupPost;

        @Override
        public FileVisitResult visitFile(
                Path file, BasicFileAttributes attrs) {
            filesVisited++;
            return FileVisitResult.SKIP_SIBLINGS;
        }

        @Override
        public FileVisitResult postVisitDirectory(
                Path dir, IOException exc) throws IOException {
            if (dir.getFileName() != null
                    && dir.getFileName().toString().equals("group")) {
                groupPost = true;
            }
            if (exc != null) {
                throw exc;
            }
            return FileVisitResult.CONTINUE;
        }
    }

    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("siblings-");
        Path group = root.resolve("group");

        try {
            Files.createDirectory(group);
            Files.writeString(group.resolve("first.txt"), "1");
            Files.writeString(group.resolve("second.txt"), "2");

            Visitor visitor = new Visitor();
            Files.walkFileTree(root, visitor);

            System.out.println("Files visited: " + visitor.filesVisited);
            System.out.println("Group post called: " + visitor.groupPost);
        } finally {
            Files.deleteIfExists(group.resolve("first.txt"));
            Files.deleteIfExists(group.resolve("second.txt"));
            Files.deleteIfExists(group);
            Files.deleteIfExists(root);
        }
    }
}
```

Run:

```bash
javac SkipSiblingsDemo.java
java SkipSiblingsDemo
```

**Exact stdout when I/O succeeds:**

```text
Files visited: 1
Group post called: true
```

Note: `SKIP_SIBLINGS` from **`visitFile`** ends iteration of remaining entries in `group` early, yet `postVisitDirectory(group)` is still called. This **differs** from returning `SKIP_SIBLINGS` from **`preVisitDirectory(group)`**, where `group` has not been entered, entries are skipped, and `postVisitDirectory(group)` is not called.

In a real tree with multiple directories across branches, `SKIP_SIBLINGS` inside `group` does not automatically stop other higher-level branches.

## 8. Java 17 Example: `TERMINATE` Stops the Entire Tree

The program places exactly one file in a temporary directory to produce output independent of filesystem order. The `visitFile` callback returns `TERMINATE`, preventing `postVisitDirectory(root)` from being called.

**File `TerminateWalkDemo.java`:**

```java
import java.io.IOException;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;

public class TerminateWalkDemo {
    static class Visitor extends SimpleFileVisitor<Path> {
        int seen;
        boolean rootPost;

        @Override
        public FileVisitResult visitFile(
                Path file, BasicFileAttributes attrs) {
            seen++;
            return FileVisitResult.TERMINATE;
        }

        @Override
        public FileVisitResult postVisitDirectory(
                Path dir, IOException exc) throws IOException {
            rootPost = true;
            if (exc != null) {
                throw exc;
            }
            return FileVisitResult.CONTINUE;
        }
    }

    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("terminate-");

        try {
            Files.writeString(root.resolve("item.txt"), "x");
            Visitor visitor = new Visitor();

            Path returned = Files.walkFileTree(root, visitor);

            System.out.println("Visited files: " + visitor.seen);
            System.out.println("Root post called: " + visitor.rootPost);
            System.out.println("Returned start: " + returned.equals(root));
        } finally {
            Files.deleteIfExists(root.resolve("item.txt"));
            Files.deleteIfExists(root);
        }
    }
}
```

Compile and run:

```bash
javac TerminateWalkDemo.java
java TerminateWalkDemo
```

**Exact stdout when temporary file creation/deletion succeeds:**

```text
Visited files: 1
Root post called: false
Returned start: true
```

If `visitFile` threw an `IOException` instead of returning `TERMINATE`, `Files.walkFileTree` would propagate an error to the caller. These two control flows carry different meanings: `TERMINATE` is an **intentional decision to stop**, while throwing an exception normally represents a **failure that must propagate outward**.

## 9. Confusing Case: `SKIP_SUBTREE` Returned From `visitFile`

Because `SKIP_SUBTREE` only has special meaning in `preVisitDirectory`, returning it from `visitFile` neither skips siblings nor has any subtree to prune at the time of a file callback.

**File `SkipSubtreeFromFileDemo.java`:**

```java
import java.io.IOException;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;

public class SkipSubtreeFromFileDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("skip-file-");
        try {
            Files.writeString(root.resolve("one.txt"), "1");
            Files.writeString(root.resolve("two.txt"), "2");

            final int[] seen = {0};
            Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
                @Override
                public FileVisitResult visitFile(
                        Path file, BasicFileAttributes attrs) {
                    seen[0]++;
                    return FileVisitResult.SKIP_SUBTREE;
                }
            });

            System.out.println("Files visited: " + seen[0]);
        } finally {
            Files.deleteIfExists(root.resolve("one.txt"));
            Files.deleteIfExists(root.resolve("two.txt"));
            Files.deleteIfExists(root);
        }
    }
}
```

Compile and run:

```bash
javac SkipSubtreeFromFileDemo.java
java SkipSubtreeFromFileDemo
```

**Exact stdout when operations succeed:**

```text
Files visited: 2
```

This illustrates the enum rule: from `visitFile`, `SKIP_SUBTREE` acts like `CONTINUE`. To skip the remaining items **at the same level**, use `SKIP_SIBLINGS`; to skip a **directory branch** before entering it, use `SKIP_SUBTREE` in `preVisitDirectory`.

## 10. Handling `visitFileFailed`: Continue or Stop?

A file or directory may fail to be visited due to permissions, a vanished path, attribute-reading errors, link cycles (with `FOLLOW_LINKS`), or other I/O causes. `visitFileFailed(path, exception)` lets the visitor decide how to react.

Example **ignoring an individual error and continuing**:

```java
@Override
public FileVisitResult visitFileFailed(
        Path file, IOException exc) {
    System.err.println("Cannot visit " + file + ": " + exc);
    return FileVisitResult.CONTINUE;
}
```

This is an illustrative method inside a `SimpleFileVisitor<Path>`; not a standalone class. Use this policy only when the domain accepts **incomplete results**. For instance, scanning files to display accessible items may make sense, whereas a backup integrity check must record all errors clearly or refuse to claim “fully scanned.”

When encountering an error **that cannot be ignored**, it is usually better to rethrow `exc`:

```java
@Override
public FileVisitResult visitFileFailed(
        Path file, IOException exc) throws IOException {
    throw exc;
}
```

That informs the caller that traversal failed with `IOException`. Returning `TERMINATE` also stops traversal, yet **does not automatically preserve the exception in the return value**; if you need to convey the reason, store state or throw the error deliberately.

### Should You Return `SKIP_SIBLINGS` When a File Fails?

Possibly: if the system wants to skip entries sharing the same parent as an inaccessible entry, the visitor can return `SKIP_SIBLINGS` from `visitFileFailed`. However, this is a fairly strong policy that can easily miss healthy data in the same directory. Use it only when your traversal protocol defines a clear reason.

### Does an Unreadable File Always Trigger `visitFileFailed`?

Do not assume a single cause. `visitFileFailed` can receive metadata-reading errors, directory-opening errors, and other causes preventing an entry from being visited. Meanwhile, **errors while iterating entries of an already-opened directory** can be reported through the `exc` parameter of `postVisitDirectory`, not always directly via `visitFileFailed`.

## 11. `postVisitDirectory`: What Does Non-Null `exc` Mean?

`postVisitDirectory(dir, exc)` runs after the walker finishes traversing a directory's entries or when directory iteration ends early in permitted cases.

- `exc == null`: no I/O error occurred during directory iteration itself; however, earlier per-entry errors may have been handled separately via `visitFileFailed`.
- `exc != null`: an I/O error caused directory iteration to terminate abnormally, requiring a decision to propagate the error or continue.
- `postVisitDirectory` can still be called when a `visitFile` returns `SKIP_SIBLINGS` and directory iteration finishes early.
- `postVisitDirectory(dir)` **is not called** for a directory skipped directly because `preVisitDirectory(dir)` returned `SKIP_SUBTREE` or `SKIP_SIBLINGS`.
- If the walker has been `TERMINATE`d, do not rely on remaining post-callbacks as a guaranteed cleanup mechanism.

Common error-preserving pattern:

```java
@Override
public FileVisitResult postVisitDirectory(
        Path dir, IOException exc) throws IOException {
    if (exc != null) {
        throw exc;
    }
    return FileVisitResult.CONTINUE;
}
```

This is an illustrative snippet. If you need to record a report for a directory after completing its children, do it here, but do not rely on this callback to **always** run when skipping branches or terminating.

## 12. Return Values vs. Exceptions: Two Separate Mechanisms

| Scenario | Suitable Mechanism |
| --- | --- |
| Sufficient data found, deliberately stop searching | `TERMINATE` |
| Directory is out of processing scope | `SKIP_SUBTREE` from pre-visit |
| Do not need remaining same-level entries | `SKIP_SIBLINGS` |
| Read error where business logic cannot continue validly | Throw `IOException` |
| Read error where a partial list is acceptable | Record error, return `CONTINUE` |
| Need to exit carrying a result | Store result in the visitor, read state after the walk |

**Do not use `TERMINATE` as a way to “swallow errors”** in tasks where the caller needs to know results are incomplete. Conversely, do not use exceptions as ordinary control flow when a file is found with no error: `TERMINATE` expresses intent much more clearly.

In complex frameworks, a visitor may collect a `List<IOException>` to tally errors and keep going; however, bound memory usage and avoid logging sensitive paths or filenames inappropriately.

## 13. Does `maxDepth` Affect Callbacks?

Yes. The overload:

```java
Files.walkFileTree(start, options, maxDepth, visitor);
```

lets you set a maximum depth. Root starts at depth 0. If `maxDepth = 0`, the walker visits only the start entry itself (as `visitFile` at the depth limit, even if it is a directory). At the maximum depth, **directories are no longer expanded into their child entries**.

When a directory sits at `maxDepth`, it may be visited through **`visitFile`** rather than `preVisitDirectory`, because the walker will not descend into that branch. Consequently:

- Do not assume every `Path` representing a directory always passes through `preVisitDirectory`.
- If you need to count all directories, define clear rules for entries at `maxDepth`.
- Returning `SKIP_SUBTREE` from `visitFile` still behaves like `CONTINUE`.

Choose `maxDepth` deliberately to avoid over-deep traversal when business logic does not need it; this complements a `SKIP_SUBTREE` policy rather than replacing it.

## 14. Symbolic Links and `FOLLOW_LINKS`

By default, `Files.walkFileTree` **does not follow symbolic links**. A symbolic link is normally treated as a non-traversed entry and passed to `visitFile`.

When `FileVisitOption.FOLLOW_LINKS` is enabled, the walker can follow links to directories, allowing the tree to point backward or form cycles. The API has built-in cycle detection; errors like `FileSystemLoopException` can be delivered to `visitFileFailed`.

```java
Files.walkFileTree(
        start,
        EnumSet.of(FileVisitOption.FOLLOW_LINKS),
        Integer.MAX_VALUE,
        visitor);
```

This is an illustrative snippet. Understand the security implications: a symlink inside the traversed tree can point to data **outside the original root**. If you only want to scan inside a real filesystem boundary, neither `SKIP_SUBTREE` nor `Path.normalize()` string checks form a complete security barrier.

Depending on requirements, you can disable link following, cap `maxDepth`, validate real paths, and enforce filesystem permissions; still account for race conditions when directories mutate mid-traversal.

### If a Directory Appears as a Symbolic Link, Is the Directory Name the Same?

When the walker follows links, callbacks may receive a `Path` reflecting the traversed link location without automatically rewriting every `Path` to its canonical real path. Do not use `dir.getFileName().toString()` as a security boundary if a directory can be renamed or a symlink redirected. Examples skipping `ignored` by name are only for simple filtering policies inside a controlled tree.

## 15. Is Sibling Order Guaranteed to Be Stable?

**No.** `Files.walkFileTree` does not promise to visit entries inside each directory in name order. Different filesystems, directory states, and concurrent modifications can produce different orders.

Therefore, with code like:

```java
@Override
public FileVisitResult visitFile(Path file, BasicFileAttributes attrs) {
    return FileVisitResult.SKIP_SIBLINGS;
}
```

“Skip siblings” means **unvisited siblings**, not “all files whose names come later alphabetically.” If business logic must find the **lexicographically smallest filename**, list and sort intentionally before selecting; do not rely on an implicit traversal order.

A stable testing strategy is:
- Create a test tree with exactly one item when testing `TERMINATE`.
- When testing `SKIP_SIBLINGS`, assert only **the number of visited entries** rather than which filename came first.
- When testing `SKIP_SUBTREE`, assert that one branch was never entered while other branches were still processed.
- Never write unit tests requiring callbacks to fire alphabetically unless your own code enforces that ordering.

## 16. Pitfalls When Using `FileVisitResult` to Delete a Directory Tree

A recursive deletion utility typically:

1. Deletes files in `visitFile`.
2. Deletes directories in `postVisitDirectory` (after deleting their entries).

However, if `preVisitDirectory` returns `SKIP_SUBTREE` for a directory, **that directory's `postVisitDirectory` does not run**. That can leave the folder intact, causing later attempts to delete its parent to fail because it is non-empty.

Similarly, when `TERMINATE` happens, many post-visit callbacks never execute. Do not place mandatory cleanup work (closing resources or deleting separate temp files) **exclusively in `postVisitDirectory`** assuming it acts like `finally`.

For recursive deletion, define policies for unremovable branches and access errors. When part of a subtree is skipped, you may need to keep the parent directory or report an error rather than treating the job as finished.

**Safety:** lesson examples never automatically delete arbitrary user trees. Demos only create and delete temporary files/directories they created themselves within a controlled scope.

## 17. Traversing to Find a File: Use `TERMINATE` or `SKIP_SIBLINGS`?

Suppose you are searching for a file named `config.json` anywhere in the tree:

```java
@Override
public FileVisitResult visitFile(Path file, BasicFileAttributes attrs) {
    if ("config.json".equals(file.getFileName().toString())) {
        found = file;
        return FileVisitResult.TERMINATE;
    }
    return FileVisitResult.CONTINUE;
}
```

Once you have the first match and only need one file, `TERMINATE` fits the intent: **stop the entire tree**. If you returned `SKIP_SIBLINGS`, the walker could return upward to traverse other branches and discover additional matching files, which is not the desired behavior.

Conversely, if the requirement is “for each directory, take at most one matching file and then continue to other directories,” `SKIP_SIBLINGS` on a file can make sense, provided you understand the tree layout and where the callback stands. It drops remaining siblings at that level without creating a magical “one file per directory” rule across arbitrary nested trees.

## 18. A Configurable Rule-Based Visitor

In real applications, you can build a visitor class responsible for:

- A list of directory names to skip.
- File counters and size statistics.
- A search condition to stop on.
- An error policy (fail-fast vs. best-effort).
- Depth limits and symbolic links.

**Illustrative skeleton**:

```java
static class SelectiveVisitor extends SimpleFileVisitor<Path> {
    private final Set<String> omittedNames;
    private final String targetName;
    private Path found;

    SelectiveVisitor(Set<String> omittedNames, String targetName) {
        this.omittedNames = omittedNames;
        this.targetName = targetName;
    }

    @Override
    public FileVisitResult preVisitDirectory(
            Path dir, BasicFileAttributes attrs) {
        Path name = dir.getFileName();
        if (name != null
                && omittedNames.contains(name.toString())) {
            return FileVisitResult.SKIP_SUBTREE;
        }
        return FileVisitResult.CONTINUE;
    }

    @Override
    public FileVisitResult visitFile(
            Path file, BasicFileAttributes attrs) {
        if (file.getFileName().toString().equals(targetName)) {
            found = file;
            return FileVisitResult.TERMINATE;
        }
        return FileVisitResult.CONTINUE;
    }

    Path found() {
        return found;
    }
}
```

This is an **illustrative class**, requiring imports for `Set`, `Path`, `SimpleFileVisitor`, `BasicFileAttributes`, and `FileVisitResult`; not a standalone program. It can be used to find the first matching file in permitted branches without expanding directories in `omittedNames`.

Watch out for **duplicate names in multiple locations**: matching by `dir.getFileName()` skips every directory with that name, not just one specific path. If you need to exclude one exact subtree, compare resolved `Path`s or use a predicate with a clear contract.

## 19. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Returning `SKIP_SUBTREE` from `visitFile` to skip siblings | Does not skip siblings; acts like `CONTINUE` | Use `SKIP_SIBLINGS` if that is the goal |
| Returning `SKIP_SIBLINGS` while expecting to stop the whole tree | Higher-level branches can still be visited | Use `TERMINATE` |
| Returning `SKIP_SIBLINGS` in `preVisitDirectory` while expecting to enter the current dir | The directory itself is not entered either | Use `CONTINUE` or `SKIP_SUBTREE` as intended |
| Relying on `postVisitDirectory` always running | Does not run when pre-visit skips or terminates | Manage resources with `try-with-resources`/`finally` |
| Assuming alphabetical name traversal | Picking “first file” is unstable | List and sort intentionally |
| Treating `TERMINATE` as a Java error | Caller does not know why if no state is stored | Use result state or throw an appropriate exception |
| Ignoring all `visitFileFailed` without reporting | Incomplete results look complete | Record errors or fail fast |
| Ignoring `exc` in `postVisitDirectory` | Directory iteration errors can be lost | Inspect or rethrow `exc` per policy |
| Assuming `maxDepth` affects only file count, not callbacks | Directories at `maxDepth` may be visited as files | Design counting and logic properly |
| Enabling `FOLLOW_LINKS` without controls | Can escape root or hit cycles | Define link, error, and depth policies |
| Filtering `Files.walk(...).filter(...)` and thinking subtrees are pruned | Walker may still enter filtered-out branches | Use `walkFileTree` and pre-visit |
| Reading attribute values across different times and assuming strict consistency | Files can mutate during scanning | Define tolerance/snapshot strategy |
| Traversing/deleting untrusted paths using only `normalize` | Symlinks/traversal/races are not blocked | Enforce permissions and filesystem-aware mechanisms |

## 20. Pre-Implementation Checklist

When writing a visitor, answer clearly:

1. Is the **starting point** a file or directory? Could it be a symlink?
2. Do we need to follow symbolic links? How does `FOLLOW_LINKS` affect access boundaries?
3. What is `maxDepth`, and how should directories at the boundary be counted?
4. Do we want to skip one exact directory or every directory with that name?
5. Is a complete traversal required, or are missing branches acceptable?
6. Are we returning `SKIP_SUBTREE` from **pre-visit** or from the wrong callback?
7. Does `SKIP_SIBLINGS` match our per-directory goal?
8. Once a file is found, do we need to return `TERMINATE` and save `found`?
9. How are metadata/directory read errors handled in `visitFileFailed`/`postVisitDirectory`?
10. Are we making any sibling-ordering assumptions not guaranteed by the API?
11. Is there post-processing in post-visit that would be bypassed by skip/terminate?
12. If the filesystem changes concurrently, is the scan result documented as a snapshot or best-effort?

## 21. Practice Exercises

1. Run `SkipSubtreeDemo`; rename `ignored` to `cache` in both the tree and visitor, and verify the file count stays 1.
2. Add a second file into `keep`; explain why `SKIP_SUBTREE` skips only `ignored` and does not affect `keep`.
3. In `SkipSiblingsDemo`, change `visitFile`'s return value from `SKIP_SIBLINGS` to `CONTINUE`; predict that visited files becomes 2 and `groupPost` remains true.
4. Change `SKIP_SIBLINGS` to `SKIP_SUBTREE` inside `visitFile`, and explain why 2 files are still visited.
5. In `TerminateWalkDemo`, change `TERMINATE` to `CONTINUE`, and verify `rootPost` becomes true.
6. Try returning `SKIP_SUBTREE` from `preVisitDirectory(root)` and record whether `visitFile`/`postVisitDirectory(root)` are called.
7. Write a visitor whose `visitFileFailed` logs and returns `CONTINUE`, then compare it with a version that rethrows `exc`. Discuss concurrent permission changes.
8. Build a visitor counting directories and files with `maxDepth=0`, `1`, and `2`. Note which callback receives a directory when the depth limit is reached.
9. Use `FileVisitOption.FOLLOW_LINKS` on a test tree containing a cyclic symbolic link (on a filesystem supporting links); check what exception type `visitFileFailed` receives.
10. Write a visitor searching for a specific filename, storing it in `found`, and returning `TERMINATE`. Ensure the caller distinguishes “not found” from “error during traversal.”
11. Return `SKIP_SIBLINGS` in `preVisitDirectory` in a tree with two sibling directories; explain why only some branches are traversed and order is not guaranteed.
12. Simulate post-visit tree deletion logic while deliberately skipping a directory; explain why the parent may still be non-empty when its turn comes.
13. Compare `Files.walkFileTree` with `Files.walk`: when is filtering sufficient and when is subtree pruning essential?
14. Write a test independent of filesystem ordering that verifies all four `FileVisitResult` values.

## 22. Summary

`FileVisitResult` is the flow-control language for directory tree traversal in `Files.walkFileTree`:

- **`CONTINUE`:** proceed with traversal normally.
- **`SKIP_SUBTREE`:** skip entries inside a directory **when returned from `preVisitDirectory`**. From other callbacks, it acts like `CONTINUE`.
- **`SKIP_SIBLINGS`:** skip **unvisited entries at the same level**. When returned from pre-visit, that directory itself is not entered and gets no post-visit callback.
- **`TERMINATE`:** stop the entire traversal without waiting for remaining post-visit callbacks.

Do not confuse control-flow values with exceptions: when an I/O error must propagate to the caller, throw `IOException` or record error state explicitly. Never assume sibling order or assume `postVisitDirectory` is always invoked. For security-sensitive traversal or deletion, especially when symbolic links are involved, account for the provider, permissions, concurrent modifications, and depth limits.

### References

- [Java SE 17: `FileVisitResult`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileVisitResult.html) — the four values and their semantic scopes.
- [Java SE 17: `FileVisitor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileVisitor.html) — the four callbacks and when they are invoked.
- [Java SE 17: `SimpleFileVisitor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/SimpleFileVisitor.html) — default behavior and error handling.
- [Java SE 17: `Files.walkFileTree`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#walkFileTree(java.nio.file.Path,java.nio.file.FileVisitor)) — walking a tree with a visitor.
- [Dev.java: Walking the File Tree](https://dev.java/learn/api/io/java-io/file-system/walking-tree/) — traversal/branch-skipping examples and flow control.
