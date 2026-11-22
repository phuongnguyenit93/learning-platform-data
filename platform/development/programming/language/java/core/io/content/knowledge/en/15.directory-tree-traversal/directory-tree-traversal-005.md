# `walkFileTree`, `FileVisitor`, and `SimpleFileVisitor` in Java

> **Topic:** Java Core → I/O → **Directory Tree Traversal**. This lesson explains how to traverse an entire directory tree depth-first using `Files.walkFileTree`, how the four callbacks of `FileVisitor` coordinate, the default behavior of `SimpleFileVisitor`, `FileVisitResult` values, depth limits, symbolic links, error handling, and application patterns such as file search, branch exclusion, statistics, and tree deletion. Standalone examples run on Java 17; the core NIO.2 APIs have existed since Java 7.

## 1. When Do You Need to Walk an Entire Directory Tree?

Suppose an application receives a `project` directory:

~~~text
project/
├── README.md
└── docs/
    ├── a.txt
    └── b.txt
~~~

You want to inspect every entry inside `project`, distinguish files from directories, possibly skip `build` or `target`, sum total bytes, or perform cleanup after processing child files. Calling `Files.list(project)` alone **is not enough**: it lists direct child entries without automatically descending deeper.

`Files.walkFileTree(...)` is the API for cases where you need **control over the traversal lifecycle**: performing actions before/after entering a directory, handling errors per entry, stopping early, or skipping an entire branch. The algorithm proceeds **depth-first**, while making no guarantee that sibling directories are visited in name order.

**Distinguish creating a path from reading the filesystem:** `Path` merely represents a location; `walkFileTree` actually accesses the provider, reads `BasicFileAttributes`, and opens/closes the directories being traversed. It can throw `IOException` or other runtime errors. Never treat a file tree as an immutable snapshot: files may be modified or deleted while traversal is in progress.

## 2. Two Main Overloads of `Files.walkFileTree`

~~~java
// Walk the entire tree, without following symbolic links by default:
Files.walkFileTree(start, visitor);

// Specify options, maxDepth, and visitor:
Files.walkFileTree(start, options, maxDepth, visitor);
~~~

This is a **fragment**. `start` has type `Path`, `visitor` is `FileVisitor<? super Path>`, `options` is `Set<FileVisitOption>`, and the method declares `throws IOException`.

| Parameter / Return | Meaning |
| --- | --- |
| `start` | Starting root `Path`; **`start` itself is also visited** according to depth rules. May be a regular file, directory, or symbolic link. |
| `visitor` | Object providing callbacks for directories/files/errors. The method invokes callbacks during traversal rather than returning a `Stream<Path>`. |
| `options` | Option set, commonly `FileVisitOption.FOLLOW_LINKS` to request following symbolic links. Empty set = do not follow links. |
| `maxDepth` | Maximum number of directory levels from `start`. `0` means visit only `start`; `Integer.MAX_VALUE` is typically used for full depth. Negative values are invalid. |
| Return type | The **`start` `Path`** when traversal finishes or a callback returns `TERMINATE`; not the number of files visited. |
| Exceptions | `IOException` from a callback propagates to the caller; a callback returning `null` causes a `NullPointerException`. |

The two-parameter overload is equivalent in behavior to:

~~~java
Files.walkFileTree(
    start,
    java.util.EnumSet.noneOf(FileVisitOption.class),
    Integer.MAX_VALUE,
    visitor);
~~~

Therefore, **symbolic links are not followed by default**, depth is bounded only by practical provider limits, and callbacks execute sequentially within the same call. `FileVisitOption.FOLLOW_LINKS` must be chosen **deliberately**, never assumed merely because a name looks like a directory.

### 2.1. Resource Lifecycle

`walkFileTree` manages its internal directory streams throughout the call. The caller **does not receive an open `Stream`** that it must `close()` afterward. However, any resource **you open inside a callback** (file channel, input stream, output stream, network connection) still needs its owner to close it.

This differs from `Files.walk(...)` or `Files.find(...)`, which return a lazily executed `Stream<Path>` that may hold directory handles and therefore **must** be closed with `try-with-resources`.

## 3. `FileVisitor`: Four Required Callbacks

`FileVisitor<T>` is a generic interface. With Java NIO filesystems, `FileVisitor<Path>` is normally used. It requires four methods:

| Callback | When Called | Parameter Meaning |
| --- | --- | --- |
| `preVisitDirectory(Path dir, BasicFileAttributes attrs)` | Before iterating entries of a successfully opened directory | `dir` is the directory; `attrs` holds basic attributes of that directory. |
| `visitFile(Path file, BasicFileAttributes attrs)` | When encountering a visited file (including non-directory entries after link rules); at `maxDepth`, a **directory may be visited here as a file** | `attrs` is the attributes the provider already read for the entry, avoiding a mandatory second `Files.readAttributes` call. |
| `visitFileFailed(Path file, IOException exc)` | When attributes cannot be read or the file/directory cannot be opened under walker rules; also used to report symlink cycles | `exc` is the I/O cause associated with that entry. |
| `postVisitDirectory(Path dir, IOException exc)` | After visiting entries/descendants of an opened directory and finishing directory iteration | `exc == null` if directory iteration had no I/O error; non-null if an error occurred during iteration. |

Each callback returns `FileVisitResult` and may declare `throws IOException`.

**Typical depth-first order** when no errors or skips occur:

~~~text
preVisitDirectory(root)
  visitFile(root/README.md)         [actual position among siblings is not fixed]
  preVisitDirectory(root/docs)
    visitFile(root/docs/a.txt)
    visitFile(root/docs/b.txt)
  postVisitDirectory(root/docs)
postVisitDirectory(root)
~~~

This is **one possible order**; never write tests assuming `README.md` comes before `docs` or `a.txt` comes before `b.txt` on every filesystem. If deterministic output is required, collect results and sort by an application-defined rule.

### 3.1. Details About `pre` and `post`

`preVisitDirectory` is invoked only for directories the walker **successfully opens** to descend into within the depth bound. If it returns `SKIP_SUBTREE` or `SKIP_SIBLINGS`, the walker does not visit that directory's contents and **does not invoke `postVisitDirectory` for the skipped directory**.

`postVisitDirectory` is well suited for operations **after children have been processed**, such as deleting an empty directory, aggregating child statistics, or applying directory attributes after copying. If directory listing hits an I/O error, the `exc` parameter reports the error; the callback must decide whether to rethrow or continue. Do not confuse `exc` in `postVisitDirectory` with every child failure: failures accessing individual entries may already have been routed separately to `visitFileFailed`.

### 3.2. Direct Interface Implementation

If you implement `FileVisitor<Path>` directly, you must provide **all four methods**, even if you only care about files:

~~~java
// Class fragment; requires importing Path, FileVisitor, FileVisitResult,
// BasicFileAttributes, IOException.
final class CountingVisitor implements FileVisitor<Path> {
    long files;

    @Override
    public FileVisitResult preVisitDirectory(
            Path dir, BasicFileAttributes attrs) {
        return FileVisitResult.CONTINUE;
    }

    @Override
    public FileVisitResult visitFile(
            Path file, BasicFileAttributes attrs) {
        if (attrs.isRegularFile()) {
            files++;
        }
        return FileVisitResult.CONTINUE;
    }

    @Override
    public FileVisitResult visitFileFailed(
            Path file, IOException exc) throws IOException {
        throw exc;
    }

    @Override
    public FileVisitResult postVisitDirectory(
            Path dir, IOException exc) throws IOException {
        if (exc != null) {
            throw exc;
        }
        return FileVisitResult.CONTINUE;
    }
}
~~~

This is a **fragment containing all interface methods**, without `main`. The key point is that every method returns a valid result; an `IOException` thrown by a callback stops traversal and propagates to the caller if unhandled.

## 4. `SimpleFileVisitor`: A More Concise Approach

`SimpleFileVisitor<T>` **pre-implements** `FileVisitor<T>`, letting you override only the callbacks you need:

- `preVisitDirectory` returns `CONTINUE` by default.
- `visitFile` returns `CONTINUE` by default.
- `visitFileFailed` **rethrows the received `IOException`** by default.
- `postVisitDirectory` returns `CONTINUE` by default if `exc == null`; if a directory-iteration error occurred, it **rethrows `exc`**.

Therefore, “Simple” **does not mean swallowing all errors**. If you want to handle an unreadable file and keep going, you must explicitly override `visitFileFailed` and define how errors are logged/counted. If you want to observe `postVisitDirectory` while keeping default error propagation, you can call `super.postVisitDirectory(dir, exc)`.

Fragment example counting regular files:

~~~java
final java.util.concurrent.atomic.AtomicLong count =
        new java.util.concurrent.atomic.AtomicLong();

Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
    @Override
    public FileVisitResult visitFile(
            Path file, BasicFileAttributes attrs) {
        if (attrs.isRegularFile()) {
            count.incrementAndGet();
        }
        return FileVisitResult.CONTINUE;
    }
});
~~~

This fragment sits inside a method handling `IOException` and requires importing the relevant classes. `AtomicLong` is **not required** for a standard walker that invokes callbacks sequentially; it is used here to allow updating a mutable counter from an anonymous class. In simpler code, a field on a visitor class can hold the count.

## 5. `FileVisitResult` Precisely Controls Traversal Direction

`FileVisitResult` has four constants:

| Value | Behavior |
| --- | --- |
| `CONTINUE` | Continue traversing remaining entries depth-first. |
| `TERMINATE` | Stop the **entire** traversal immediately; no further file-walk callbacks are invoked afterward. |
| `SKIP_SUBTREE` | When returned by **`preVisitDirectory`**: do not traverse children of the current directory; other siblings can still be visited. |
| `SKIP_SIBLINGS` | Skip **unvisited** siblings in the parent directory; if returned from `preVisitDirectory`, the current directory's subtree is also skipped. |

Interpret “sibling” relative to the entry's **same parent directory** at callback time, not “every other entry across the whole filesystem.”

### 5.1. Commonly Misunderstood Contexts

- `preVisitDirectory(dir) -> SKIP_SUBTREE`: does **not** visit child entries and does **not** call `postVisitDirectory(dir)`. Sibling directories can still continue afterward.
- `preVisitDirectory(dir) -> SKIP_SIBLINGS`: skips this directory and remaining siblings, without calling `postVisitDirectory` for the skipped directory.
- `visitFile(file) -> SKIP_SIBLINGS`: stops visiting further siblings of the file in its parent directory; the current directory iterator finishes early.
- `postVisitDirectory(dir) -> SKIP_SIBLINGS`: after finishing the current directory, skips unvisited siblings at the same level.
- `visitFile(file) -> SKIP_SUBTREE`: since a file has no subtree, this is treated the same as `CONTINUE` per contract.
- `TERMINATE` from a callback: exits the entire tree traversal; do not expect `postVisitDirectory` to be invoked for every ancestor like a `finally` block. If you need to release custom resources, use `try/finally` or `try-with-resources` outside the callbacks.
- Callbacks **must never return `null`**: the walker throws `NullPointerException`.

Example finding the first file matching a condition:

~~~java
// Fragment: target variable defined by caller, callback invoked in a method
// handling IOException.
Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
    @Override
    public FileVisitResult visitFile(
            Path file, BasicFileAttributes attrs) {
        if (attrs.isRegularFile()
                && file.getFileName().toString().equals(target)) {
            System.out.println("Found: " + file);
            return FileVisitResult.TERMINATE;
        }
        return FileVisitResult.CONTINUE;
    }
});
~~~

Because sibling traversal order is **unspecified**, if multiple files share the same name in different branches, the “first” match **does not mean** the shortest path, closest path, or alphabetically smallest path. If deterministic selection is required, define a rule up front and consider collecting/sorting.

## 6. Runnable Example 1: Traversing and Listing a Directory Tree

Create **`TreeWalkDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class TreeWalkDemo {
    // Only cleans up the temporary tree created by the demo itself.
    static void deleteTree(Path root) throws IOException {
        Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
            @Override
            public FileVisitResult visitFile(
                    Path file, BasicFileAttributes attrs) throws IOException {
                Files.delete(file);
                return FileVisitResult.CONTINUE;
            }

            @Override
            public FileVisitResult postVisitDirectory(
                    Path dir, IOException exc) throws IOException {
                if (exc != null) {
                    throw exc;
                }
                Files.delete(dir);
                return FileVisitResult.CONTINUE;
            }
        });
    }

    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("tree-demo-");
        try {
            Files.createDirectory(root.resolve("docs"));
            Files.writeString(root.resolve("README.md"),
                    "root", StandardCharsets.UTF_8);
            Files.writeString(root.resolve("docs/a.txt"),
                    "a", StandardCharsets.UTF_8);
            Files.writeString(root.resolve("docs/b.txt"),
                    "b", StandardCharsets.UTF_8);

            List<String> found = new ArrayList<>();

            Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
                @Override
                public FileVisitResult preVisitDirectory(
                        Path dir, BasicFileAttributes attrs) {
                    if (!dir.equals(root)) {
                        found.add("D:" + dir.getFileName());
                    }
                    return FileVisitResult.CONTINUE;
                }

                @Override
                public FileVisitResult visitFile(
                        Path file, BasicFileAttributes attrs) {
                    found.add("F:" + file.getFileName());
                    return FileVisitResult.CONTINUE;
                }
            });

            // Filesystems are not required to return siblings by name:
            // sort after collecting for deterministic stdout.
            Collections.sort(found);
            found.forEach(System.out::println);
        } finally {
            deleteTree(root);
        }
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 TreeWalkDemo.java
java TreeWalkDemo
~~~

**JDK-verified stdout:**

~~~text
D:docs
F:README.md
F:a.txt
F:b.txt
~~~

**Explanation:** `root` is a freshly created temporary directory containing `docs` and three files. `preVisitDirectory` records directories other than `root`; `visitFile` records files; `postVisitDirectory` needs no override during the listing pass because `SimpleFileVisitor`'s default already continues and reports errors if needed. Afterward, the `finally` block invokes **another** visitor to delete the entire temporary tree in safe order: files first, directories afterward.

The example records `dir.getFileName()` and `file.getFileName()` with distinct names, then sorts so output does not depend on Windows/Unix separators or directory enumeration order. In a real problem where two files in different branches share the same basename, recording only filenames would collide; use `root.relativize(file)` or store full `Path` objects.

**Safety warning:** `deleteTree` in the demo genuinely deletes data. Call it only on **the temporary tree just created by the demo**. Do not pass user-supplied paths to this method without adding scope validation, permissions checks, symlink handling, and deletion policies.

## 7. Runnable Example 2: Skipping a Directory Branch

A crawler should avoid opening unnecessary directories such as `node_modules`, `build`, or sensitive areas. To prune an entire subtree, return `SKIP_SUBTREE` from `preVisitDirectory`.

Create **`SkipTreeDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.concurrent.atomic.AtomicInteger;

public class SkipTreeDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("skip-demo-");
        try {
            Files.createDirectory(root.resolve("public"));
            Files.createDirectory(root.resolve("private"));
            Files.writeString(root.resolve("public/hello.txt"), "ok");
            Files.writeString(root.resolve("private/secret.txt"), "skip");
            Files.writeString(root.resolve("root.txt"), "ok");

            AtomicInteger files = new AtomicInteger();
            AtomicInteger skipped = new AtomicInteger();

            Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
                @Override
                public FileVisitResult preVisitDirectory(
                        Path dir, BasicFileAttributes attrs) {
                    if (dir.getFileName().toString().equals("private")) {
                        skipped.incrementAndGet();
                        return FileVisitResult.SKIP_SUBTREE;
                    }
                    return FileVisitResult.CONTINUE;
                }

                @Override
                public FileVisitResult visitFile(
                        Path file, BasicFileAttributes attrs) {
                    files.incrementAndGet();
                    return FileVisitResult.CONTINUE;
                }
            });

            System.out.println("files=" + files.get());
            System.out.println("skipped=" + skipped.get());
        } finally {
            TreeWalkDemo.deleteTree(root);
        }
    }
}
~~~

To run **this example**, place both `TreeWalkDemo.java` from the previous section and `SkipTreeDemo.java` in the **same directory** to reuse the tree-deletion helper:

~~~bash
javac --release 17 TreeWalkDemo.java SkipTreeDemo.java
java SkipTreeDemo
~~~

Stdout:

~~~text
files=2
skipped=1
~~~

`private/secret.txt` **is never visited** because the callback for `private` itself returned `SKIP_SUBTREE`. `public/hello.txt` and `root.txt` are counted: two files. `skipped=1` because there is exactly one directory named `private` in the mock tree.

**Compilation note:** `SkipTreeDemo.java` intentionally uses the package-private static helper `TreeWalkDemo.deleteTree` from the previous example. If you want a completely standalone file, copy that helper into the same class or replace it with an appropriate cleanup method. Both examples are provided in full in this lesson and the compile command above includes both source files.

Production patterns usually compare **relative paths** or allowed subtrees rather than comparing bare names: two directories named `private` at different locations may need different policies. Once a directory is skipped, the walker does not read files under it; do not call `Files.walkFileTree` on that directory a second time and defeat the skip.

## 8. `maxDepth`: Level 0, Level 1, and Directories at the Boundary

With the overload:

~~~java
Files.walkFileTree(
    root,
    EnumSet.noneOf(FileVisitOption.class),
    1,
    visitor);
~~~

`maxDepth=0` visits only `root`; `maxDepth=1` processes `root` and its direct entries beneath it, **without descending deeper**. One surprising detail from the Javadoc: an entry that is a **directory right at `maxDepth` is passed to `visitFile`**, without being opened further and without calling `preVisitDirectory/postVisitDirectory` for that directory.

Example tree:

~~~text
root/                  depth 0
└── child/             depth 1
    └── note.txt       depth 2
~~~

When walking with `maxDepth=1`, `preVisitDirectory(root)` can be invoked, while `child` is reported through `visitFile(child, attrs)`; `note.txt` is not visited. This explains why `visitFile` code should check `attrs.isRegularFile()` rather than assuming every `file` received there is a regular file.

### 8.1. Runnable Example 3: Observing a Directory at `maxDepth`

Create **`DepthDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.file.FileVisitOption;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.ArrayList;
import java.util.Collections;
import java.util.EnumSet;
import java.util.List;

public class DepthDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("depth-");
        try {
            Files.createDirectory(root.resolve("child"));
            Files.writeString(root.resolve("child/note.txt"), "x");

            List<String> found = new ArrayList<>();
            Files.walkFileTree(
                    root, EnumSet.noneOf(FileVisitOption.class), 1,
                    new SimpleFileVisitor<Path>() {
                        @Override
                        public FileVisitResult preVisitDirectory(
                                Path dir, BasicFileAttributes attrs) {
                            found.add("D:" + dir.getFileName());
                            return FileVisitResult.CONTINUE;
                        }

                        @Override
                        public FileVisitResult visitFile(
                                Path file, BasicFileAttributes attrs) {
                            found.add("F:" + file.getFileName());
                            return FileVisitResult.CONTINUE;
                        }
                    });

            Collections.sort(found);
            System.out.println("depthOneEntries=" + found.size());
            System.out.println("childAsFile="
                    + found.stream().anyMatch(s -> s.equals("F:child")));
        } finally {
            TreeWalkDemo.deleteTree(root);
        }
    }
}
~~~

Compile together with the helper:

~~~bash
javac --release 17 TreeWalkDemo.java DepthDemo.java
java DepthDemo
~~~

Stdout:

~~~text
depthOneEntries=2
childAsFile=true
~~~

At `maxDepth=1`, the callbacks receive one entry for `root` (`preVisitDirectory`) and one entry for `child` (`visitFile`), totaling 2; `child/note.txt` is at depth 2 and is not visited. `Collections.sort` is unnecessary for counting, yet illustrates how to normalize the list when testing event names.

If `maxDepth` is negative, `Files.walkFileTree` throws `IllegalArgumentException`. In applications accepting depth from users, validate it first and enforce a reasonable cap to prevent unintended massive traversals.

## 9. Symbolic Links: Not Followed by Default

By default, `Files.walkFileTree(start, visitor)` **does not follow symbolic links**. If an entry inside the tree is a symbolic link pointing to another directory, it is typically passed to `visitFile` with the attributes of the link itself. This is helpful when walking files so traversal does not unintentionally escape `root`.

To follow links:

~~~java
// Fragment: root is defined, method throws IOException.
Files.walkFileTree(
        root,
        java.util.EnumSet.of(FileVisitOption.FOLLOW_LINKS),
        Integer.MAX_VALUE,
        visitor);
~~~

However, **`FOLLOW_LINKS` requires a safety policy**:

- A symbolic link can lead **outside** the original path tree; `root.relativize(path)` alone does not prove the real data resides under `root`.
- Multiple links can point to the same file or directory, causing duplicate processing. When summing sizes, statistics can be inflated.
- When following links, the walker detects cycles pointing back to an ancestor using file keys or `Files.isSameFile` per provider. When a loop is detected, `visitFileFailed` receives `FileSystemLoopException`.
- Not every symbolic link points to a valid target. If target attributes cannot be read, the walker may fall back to the link's own attributes and pass the link to `visitFile`; thus `attrs` does not necessarily describe the target in all cases.
- Setting `maxDepth` still bounds the number of levels, yet **does not** limit the number of entries at each level. Add time/file-count/byte bounds when input is untrusted.

### 9.1. Handling Cycles Deliberately

~~~java
// Fragment: visitor used in walkFileTree(... FOLLOW_LINKS ...).
@Override
public FileVisitResult visitFileFailed(
        Path file, IOException exc) throws IOException {
    if (exc instanceof java.nio.file.FileSystemLoopException) {
        // Report or count symlink cycles without swallowing other errors.
        System.err.println("Cycle at: " + file);
        return FileVisitResult.CONTINUE;
    }
    throw exc;
}
~~~

This is a **method fragment** inside a `SimpleFileVisitor<Path>` subclass, not a standalone program. Returning `CONTINUE` here means your policy accepts skipping cyclic entries and does not guarantee complete traversal results. If the task requires a complete snapshot/traversal, rethrow or report so the caller knows results are incomplete.

## 10. Controlled Error Handling in a Visitor

### 10.1. `visitFileFailed` Is Not `postVisitDirectory`

If the walker **cannot read attributes** for a path, or cannot **open** that directory, it typically invokes `visitFileFailed(path, exc)`. If it **opened** the directory successfully but encountered an error while **iterating its entries**, the walker closes the directory and invokes `postVisitDirectory(dir, exc)`.

Do not conflate these two cases into one callback: they happen at different stages and imply different recovery options.

The default behavior of `SimpleFileVisitor` is to **rethrow** the I/O error, so traversal stops immediately when hitting an unreadable directory. If your domain allows “best effort,” you can record the error and continue:

~~~java
// Method fragment inside SimpleFileVisitor<Path>.
@Override
public FileVisitResult visitFileFailed(
        Path path, IOException exc) {
    errors.add(path); // errors is a collection managed by the caller.
    return FileVisitResult.CONTINUE;
}
~~~

To avoid losing the cause, store both `Path` and `IOException` or log errors per policy. The `errors.add(path)` line is a **fragment** without defining `errors`; in production, choose a collection aligned with security and memory limits.

### 10.2. Iteration Errors in `postVisitDirectory`

~~~java
@Override
public FileVisitResult postVisitDirectory(
        Path dir, IOException exc) throws IOException {
    if (exc != null) {
        throw exc;   // Fail fast, do not report success when data is incomplete.
    }
    return FileVisitResult.CONTINUE;
}
~~~

This is a method fragment. If you want to keep going on certain directory errors, you can log into an application report and `return CONTINUE`. However, when **deleting/copying** a tree, swallowing errors and assuming the directory is fully processed is dangerous: unseen child files may remain, causing directory deletion afterward to fail.

### 10.3. Exceptions Thrown Inside a Callback

If `visitFile` throws `IOException` directly, `walkFileTree` terminates and propagates the exception to the caller; it **does not automatically** catch that exception and call `visitFileFailed` for the callback that threw. `visitFileFailed` is primarily for errors the walker hits when accessing an entry per its contract. If your code opens/reads file contents inside `visitFile`, decide **whether to catch/continue locally or propagate**.

Runtime exceptions or `Error`s raised in a callback are likewise never converted into `FileVisitResult.CONTINUE`. And if a callback returns `TERMINATE`, external code must not treat that like a rolled-back exception: side effects already performed remain.

## 11. Deleting a Tree with `walkFileTree`: Why Is `postVisitDirectory` Needed?

Normally a directory can only be deleted after all entries inside it are gone. Because the walker proceeds depth-first, the matching callback pairing is:

- `visitFile`: delete the file (including symbolic links when not following links by default).
- `postVisitDirectory`: after children have been visited/deleted, delete that directory.
- `visitFileFailed`: report the error rather than silently skipping an entry that could not be inspected.
- `preVisitDirectory`: usually keep the default `CONTINUE`, unless policy rejects a branch.

This is the exact order used by `deleteTree` in `TreeWalkDemo`. If you reversed it to delete directories in `preVisitDirectory`, `Files.delete(dir)` would risk `DirectoryNotEmptyException`.

**Production usage must be more cautious than a demo**, because deletion is destructive:

1. Accept only an explicit root chosen by an **authorized** caller; normalize and validate scope before acting.
2. Do not follow links during routine deletion, so you delete **the link itself** rather than descending into targets outside root.
3. Record per-entry errors; never treat a failing traversal as “cleanly deleted.”
4. If the directory tree can be altered concurrently by another actor, `Files.delete` by `Path` can suffer from **races**; some providers support `SecureDirectoryStream` for handle-relative operations that mitigate certain risks, though not all providers have it.
5. If you need a trash bin, backup, or recovery capability, **do not** expose a demo snippet calling `Files.delete` directly as a business API.
6. Never run deletion traversal against a filesystem root, home directory, real project directory, or raw untrusted user input.

### 11.1. Why Is the Post-Directory Callback Especially Valuable?

Not just for deletion: when **copying a directory tree**, you typically create the destination directory in `preVisitDirectory`, copy files in `visitFile`, and then apply final directory metadata/permissions in `postVisitDirectory` so copying child contents does not alter the directory's modification timestamp. This is a **parent/child dependency ordering** pattern that simple `Files.walk(...)` + `forEach` does not express as naturally as structured callbacks.

## 12. Counting Sizes, Finding Files, and Reliability of `attrs`

`BasicFileAttributes` provides several useful methods:

| Attribute | Usage |
| --- | --- |
| `isRegularFile()` | Count/process regular files; avoid mistakenly adding sizes of directories or links. |
| `isDirectory()` | Check whether an entry has directory attributes; useful at `maxDepth` when directories pass through `visitFile`. |
| `isSymbolicLink()` | Distinguish symlinks when not following links or reading the link's own attributes. |
| `size()` | Entry size in **bytes** reported by the provider; not text character count or allocated disk blocks. |
| `lastModifiedTime()` | Filter by timestamp when needed; may change concurrently. |
| `fileKey()` | Provider-supplied identifier for recognizing files; not guaranteed non-null or stable across all providers. |

Inside callbacks, reuse the `attrs` already supplied by the walker instead of calling `Files.readAttributes` again for the same entry unless there is a fresh validation reason. Re-reading adds I/O and can return different state due to concurrent modifications.

Fragment example summing regular-file bytes:

~~~java
// Fragment: code inside a class extending SimpleFileVisitor<Path>.
private long totalBytes;

@Override
public FileVisitResult visitFile(
        Path file, BasicFileAttributes attrs) {
    if (attrs.isRegularFile()) {
        totalBytes += attrs.size();
    }
    return FileVisitResult.CONTINUE;
}
~~~

`totalBytes` is the sum of **logical file sizes** across visited entries, **not** allocated disk blocks or deduplicated storage bytes. Hard links, symlink-following, sparse files, and concurrently modified data complicate interpreting “directory size.” With huge file counts, `long` can theoretically overflow; if strict auditing is needed, plan overflow handling and appropriate filesystem-level snapshots/locks.

## 13. Comparing with `Files.walk`, `Files.find`, and `Files.list`

| API | Depth / Direction | Style | Cleanup |
| --- | --- | --- | --- |
| `Files.list(dir)` | One direct level | `Stream<Path>` from a single directory | **Close `Stream`** with `try-with-resources` |
| `Files.walk(start)` | Recursive depth-first | Lazy `Stream<Path>` | **Close `Stream`**; I/O errors during consumption may become `UncheckedIOException` |
| `Files.walk(start, maxDepth)` | Depth-bounded recursion | Lazy `Stream<Path>` | **Close `Stream`** |
| `Files.find(start, maxDepth, matcher, options...)` | Recursive, with predicate receiving `Path` + `attrs` | Lazy `Stream<Path>` | **Close `Stream`** |
| `Files.walkFileTree(start, visitor)` | Depth-first recursion, does not follow links by default | **Callbacks** pre/visit/fail/post; supports skip/terminate control | Walker closes internal directory handles itself |
| `Files.walkFileTree(start, options, depth, visitor)` | Supports `FOLLOW_LINKS` and depth limit | Callbacks can report errors per entry | No returned `Stream` to close |

If you only need a filtered list of files, `Files.walk(...)` + `filter` can be concise. If you need to **skip an entire subtree based on directory details**, you need `preVisitDirectory`. If you need to **delete a directory after deleting all its children**, `walkFileTree` is usually more direct and clearer. When using `Files.walk(...)`, remember the `Stream` is lazy and release resources via:

~~~java
// Fragment: caller handles IOException from Files.walk.
try (java.util.stream.Stream<Path> paths = Files.walk(root)) {
    paths.filter(Files::isRegularFile).forEach(System.out::println);
}
~~~

This is a fragment: in the right context and on a concurrently modified filesystem, errors can still occur while the stream is consumed. A `Files.walk` stream closes only when `close()` or `try-with-resources` finishes—it does **not** close automatically when terminal operations like `count()` or `forEach()` complete.

## 14. Ordering and Consistency Issues

`walkFileTree` is **depth-first**, yet **does not guarantee sibling order**. Different filesystems, directory states, or concurrent file creation/deletion can produce different orders.

**If deterministic output is required:**

- Collect `Path`s or summary records, then sort at the end.
- Use `root.relativize(path)` for relative positions; keep in mind `toString()` uses provider-specific separators, so define a canonical format when serializing for other systems.
- Do not rely on the first item visited to pick the “smallest,” “newest,” or “alphabetically first” file unless you traverse completely and compare intentionally.
- If there are too many entries to hold in RAM, use a dedicated directory enumeration/sorting strategy or external sort; `walkFileTree` provides no built-in sibling sorting option.
- `Path`, `BasicFileAttributes`, and file contents do not form an atomic snapshot; counts or selections can be affected by files being modified mid-walk.

## 15. Performance and Limits When Traversing Large Trees

A tree with millions of files can consume significant time reading metadata and opening directories. Avoid these common mistakes:

1. **Not bounding depth when only a few levels are needed**: use the `maxDepth` overload to save I/O.
2. **Entering irrelevant directories only to discard files inside**: return `SKIP_SUBTREE` early in `preVisitDirectory`.
3. **Opening files to inspect contents when names/metadata suffice**: avoid redundant I/O.
4. **Calling `Files.size(path)` for every file when `attrs.size()` is already available**: adds unnecessary metadata lookups.
5. **Collecting every `Path` into an unbounded `List`**: process incrementally in callbacks and keep only aggregated state when possible.
6. **Ignoring errors and reporting “fully traversed”**: distinguish successful counts, errors, and skipped branches.
7. **Running multiple concurrent walkers over the same directory**: increases I/O pressure and complicates mutation races; only do this if the workload demands it.
8. **Uncontrolled `FOLLOW_LINKS`**: easily escapes boundaries or double-counts files, increasing depth and file volume.
9. **Holding custom resources open across multiple callbacks**: can exhaust file descriptors; open only when needed and close inside the callback.
10. **Expecting callbacks to run on separate threads**: `walkFileTree` is synchronous; any parallelism must be orchestrated and synchronized by the application itself.

If you need to cap **entry count**, a callback can increment a counter and `return TERMINATE` upon reaching the threshold; however, stopping early means incomplete data. Clearly report truncation by policy rather than returning a “complete traversal” result.

## 16. Safety When Traversing User-Provided Paths

Backup or search tools may accept `root` from a CLI or API. Traversing a tree is not a vulnerability by itself, but if callbacks **read confidential data, copy files outward, delete files, or alter permissions**, boundary enforcement is critical.

- Accept only roots permitted by access controls and policy.
- Do not treat `normalize()` or `startsWith(root)` as the sole barrier when symlinks and concurrent modifications may be involved.
- With `FOLLOW_LINKS`, define how to handle symlinks pointing outside `root`; symlink cycle detection does not replace a security policy.
- Do not log sensitive user paths or filenames unnecessarily.
- Even without following links, the directory tree can change **between** reading `attrs` and running `Files.read`/`delete`. Account for TOCTOU and filesystem permissions.
- For deletion/copying, provide dry-run, backups, root validation, and user confirmation where possible; avoid turning traversal demos into accidental real-data deletion.
- If the caller expects a complete result, do not report “success” when `visitFileFailed` records errors and returns `CONTINUE`; return statistics including error counts and an explicit policy status.

## 17. Typical Mistakes

1. **Using `Files.list` while expecting recursive traversal.** `list` returns direct children only.
2. **Assuming siblings are visited alphabetically.** No such guarantee exists.
3. **Using `SimpleFileVisitor` and thinking I/O errors are ignored automatically.** `visitFileFailed` rethrows exceptions by default.
4. **Overriding `visitFileFailed` to always return `CONTINUE` without recording errors.** Results silently omit missing data.
5. **Assuming every directory goes through `preVisitDirectory`.** At `maxDepth`, a directory can pass through `visitFile`.
6. **Counting every `visitFile` callback as a regular file.** Check `attrs.isRegularFile()`.
7. **Returning `SKIP_SUBTREE` from `visitFile` to skip the parent directory.** Subtree pruning only takes effect when returned from `preVisitDirectory`.
8. **Returning `TERMINATE` and expecting `postVisitDirectory` to run for every ancestor.** There is no `finally`-style cleanup callback contract.
9. **Forgetting to check `postVisitDirectory(exc)`.** Directory-iteration errors may be missed or misreported.
10. **Using `postVisitDirectory` to assume all child files succeeded.** Errors may have been bypassed earlier by callbacks.
11. **Enabling `FOLLOW_LINKS` on untrusted trees without bounds or checks.** Can escape root, hit cycles, or visit duplicate files.
12. **Deleting a directory inside `preVisitDirectory`.** Children have not been removed yet, so the directory is usually non-empty.
13. **Collecting all files into RAM when only a count is needed.** Keeping summary state is far more efficient for large trees.
14. **Keeping input/output streams open across callbacks.** Poor resource management causes leaks.
15. **Assuming the walker locks the filesystem so nobody can modify the tree.** Concurrent filesystem changes must always be anticipated.
16. **Trying to close the walker's internal handles by closing `Path`.** `Path` has no `close()`; the walker manages directory handles internally.
17. **Using `Files.walk` and forgetting to close the `Stream`.** That is a different API from `walkFileTree`.
18. **Calling `Files.walkFileTree` with `maxDepth=-1`.** Throws `IllegalArgumentException`.
19. **Returning `null` from a callback.** Causes `NullPointerException` instead of continuing.
20. **Testing against real files and deleting data by mistake.** Deletion examples must operate strictly on temporary trees created in tests.

## 18. Self-Check Questions

1. Does `Files.walkFileTree(root, visitor)` follow symbolic links automatically?
2. What are the four methods of `FileVisitor<Path>`? Which method runs after a directory's children have been processed?
3. What does `SimpleFileVisitor` do by default when a file cannot be opened?
4. How do `SKIP_SUBTREE` and `SKIP_SIBLINGS` differ when returned from `preVisitDirectory`?
5. Does `TERMINATE` guarantee calling `postVisitDirectory` for all ancestor directories for cleanup?
6. With `maxDepth=1`, through which callback is a direct child directory reported?
7. When does `visitFileFailed` receive `FileSystemLoopException`?
8. If you only want to count regular files, which method on `attrs` should you check?
9. Why should directory deletion be placed in `postVisitDirectory`?
10. What does `Files.walk(root)` return, and does it need to be closed?
11. Can you rely on `visitFile` order to pick the alphabetically smallest file?
12. When `postVisitDirectory(dir, exc)` has `exc != null`, what does that indicate?
13. Inside a walker, if a callback opens `Files.newInputStream(file)`, who closes the input stream?
14. If a callback returns `CONTINUE` after a file read error, should summary statistics record the error?
15. When using `FOLLOW_LINKS` with a user-supplied root, is `normalize()` alone safe enough?

**Suggested Answers:**

1. No, by default it does not follow links.
2. `preVisitDirectory`, `visitFile`, `visitFileFailed`, `postVisitDirectory`; the method after children are processed is `postVisitDirectory` when the directory was opened/traversed.
3. It rethrows the `IOException`.
4. `SKIP_SUBTREE` skips the current subtree while still visiting siblings; `SKIP_SIBLINGS` also skips unvisited siblings.
5. No; use `finally`/`try-with-resources` for any resources you manage yourself.
6. Typically `visitFile` at the `maxDepth` boundary.
7. When `FOLLOW_LINKS` causes the walker to detect a link cycle back to an ancestor.
8. `attrs.isRegularFile()`.
9. Child files and subdirectories must be processed/deleted first so the parent directory becomes empty before deletion.
10. It returns a lazy `Stream<Path>` that must be closed.
11. No; sibling order is not guaranteed.
12. An I/O error occurred while iterating the directory (which does not necessarily include every child file error).
13. The callback itself or the application owner, via `try-with-resources`.
14. Yes, so the caller knows traversal was best-effort and results may be incomplete.
15. No; symlinks, permissions, traversal outside root, and TOCTOU still remain concerns.

## 19. Official References

- [Oracle Java SE 21 — Files.walkFileTree](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html): overloads, depth, `FOLLOW_LINKS`, lifecycle, error handling, and callback rules.
- [Oracle Java SE 21 — FileVisitor](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/FileVisitor.html): the four callbacks and `FileVisitResult` contract.
- [Oracle Java SE 21 — SimpleFileVisitor](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/SimpleFileVisitor.html): default behavior and exception propagation.
- [Oracle Java SE 21 — FileVisitResult](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/FileVisitResult.html): `CONTINUE`, `TERMINATE`, `SKIP_SUBTREE`, `SKIP_SIBLINGS`.
- [Oracle Java SE 21 — FileVisitOption](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/FileVisitOption.html): the `FOLLOW_LINKS` option.
- [Oracle Java SE 21 — BasicFileAttributes](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/attribute/BasicFileAttributes.html): size and entry types.
- [Oracle Java SE 21 — FileSystemLoopException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/FileSystemLoopException.html): symbolic link cycles during traversal.
- [Oracle Java Tutorial — Walking the File Tree](https://docs.oracle.com/javase/tutorial/essential/io/walk.html): practical examples of traversal and flow control.

**Takeaway:** `Files.walkFileTree` walks a tree depth-first and hands decision-making control to `FileVisitor`. Use `SimpleFileVisitor` when you only need to override a few callbacks; `preVisitDirectory` helps prune branches, `visitFile` processes entries, `visitFileFailed` reports entry access errors, and `postVisitDirectory` suits cleanup or aggregation after children. Pay close attention to `maxDepth`, symbolic links, unspecified ordering, and resource lifecycles before applying this to real files.
