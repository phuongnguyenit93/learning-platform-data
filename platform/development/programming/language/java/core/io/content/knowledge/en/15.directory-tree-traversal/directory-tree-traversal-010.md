# Copying or Deleting a Directory Tree in the Proper Processing Order in Java

## 1. Lesson Objectives

When operating on a **directory tree**, the processing order of entries is a key part of correctness. Unlike a single file, a tree consists of parent directories, subdirectories, and files across multiple levels:

- **Copying a tree:** you must prepare each **parent** directory **before** creating child files or subdirectories at the destination.
- **Deleting a tree:** you must delete **files and subdirectories before** deleting their parent directory.

Java NIO.2 provides `Files.walkFileTree()` combined with `FileVisitor` / `SimpleFileVisitor` to solve this problem using *depth-first traversal*. This lesson focuses on those two operations rather than equating them with `Files.copy(sourceDirectory, targetDirectory)` or `Files.delete(root)`, which apply only to a single path object.

You will learn:

1. The meaning of **pre-order** and **post-order** when traversing a tree.
2. How to use `preVisitDirectory`, `visitFile`, `postVisitDirectory`, and `visitFileFailed`.
3. A Java 17+ example copying an entire tree, then deleting a tree in the right order.
4. How to handle source/destination validation, symlinks, attributes, I/O errors, depth limits, and deletion safety.
5. When to use `Files.walk()`, and why completing traversal does not automatically imply safe deletion order.

## 2. Directory Trees and Ordering Constraints

Suppose we have this data:

```text
source/
├── config.txt
└── reports/
    ├── january.csv
    └── history/
        └── old.csv
```

To **copy** to `backup/`, the application must produce an equivalent structure:

```text
backup/
├── config.txt
└── reports/
    ├── january.csv
    └── history/
        └── old.csv
```

If you attempt to create `backup/reports/history/old.csv` when `backup/reports/history` does not yet exist, a standard copy operation fails because the parent directory is missing. Therefore, the destination preparation sequence is typically:

```text
Create backup/
Create backup/reports/
Create backup/reports/history/
Copy files into the created directories
```

The relative order **among sibling files at the same level** does not matter for independent copies: `config.txt` can be copied before or after the files inside `reports/`, as long as each file's parent directory already exists.

When **deleting** `backup/`, the order reverses:

```text
Delete file backup/reports/history/old.csv
Delete directory backup/reports/history/
Delete file backup/reports/january.csv
Delete directory backup/reports/
Delete file backup/config.txt
Delete directory backup/
```

The sequences above illustrate just one valid order; **traversal order among sibling subdirectories at the same level is not guaranteed** by `walkFileTree`. What must always hold is the parent–child relationship, not filename order.

### Why Is `Files.delete(root)` Not Enough?

`Files.delete(path)` deletes **a single entry**. If `path` is a directory that still contains child entries, it normally throws `DirectoryNotEmptyException`. `Files.deleteIfExists(path)` does not delete recursively either.

Similarly, `Files.copy(sourceDirectory, targetDirectory)` creates only a single corresponding destination directory without **automatically copying the entries inside the source directory**. To copy completely, you must traverse every entry and process it in the proper order.

## 3. `walkFileTree()` and the Four Key Callbacks

`Files.walkFileTree(start, visitor)` traverses the tree *depth-first*. By default, it **does not follow symbolic links**. The `SimpleFileVisitor<Path>` callbacks are invoked by phase:

| Callback | When Called | Application in This Task |
| --- | --- | --- |
| `preVisitDirectory(dir, attrs)` | **Before** iterating the entries of a directory | Create destination directory when **copying** a tree |
| `visitFile(file, attrs)` | Upon encountering a file, or an entry not entered as a directory | Copy file or delete file/symlink |
| `postVisitDirectory(dir, exc)` | **After** finishing traversal of a directory or after an internal iteration error | Delete directory when **deleting**; optionally apply metadata after copying |
| `visitFileFailed(file, exc)` | Cannot retrieve attributes or access an entry/directory for traversal | Report error or handle according to explicit policy |

Callback diagram for a tree with a single branch:

```text
enter root                  -> preVisitDirectory(root)
  enter docs                -> preVisitDirectory(docs)
    visit hello.txt         -> visitFile(hello.txt)
  leave docs                -> postVisitDirectory(docs)
leave root                  -> postVisitDirectory(root)
```

**Pre-order**: act on a directory **before** its contents.

**Post-order**: act on a directory **after** its child entries have been processed.

With `SimpleFileVisitor`, the default behavior of `visitFileFailed` is to **rethrow `IOException`**. In `postVisitDirectory`, the `exc` argument can be non-null if iterating directory entries encountered an error; never blindly ignore this error and delete the parent.

Common `FileVisitResult` values:

- `CONTINUE`: continue traversal.
- `SKIP_SUBTREE`: from `preVisitDirectory`, skip children of the current directory.
- `SKIP_SIBLINGS`: skip remaining sibling entries at the same level per visitor contract.
- `TERMINATE`: stop the traversal.

**Warning:** In a full tree-deletion program, if you return `SKIP_SUBTREE` and still attempt to delete the parent directory later, the directory may not be empty. Define skipping and failure-handling policies clearly rather than ignoring exceptions.

## 4. Java 17+: Observing the Exact Callback Sequence

The program below creates a temporary `root` directory containing one `docs` subdirectory and one `note.txt` file. To keep stdout deterministic, there is only **one directory branch** and only entry names are printed, not absolute paths.

Save as **`TreeOrderDemo.java`**:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;

public class TreeOrderDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("tree-order-");

        try {
            Path docs = Files.createDirectory(root.resolve("docs"));
            Files.writeString(docs.resolve("note.txt"),
                    "content", StandardCharsets.UTF_8);

            Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
                private String name(Path path) {
                    return path.equals(root)
                            ? "root" : path.getFileName().toString();
                }

                @Override
                public FileVisitResult preVisitDirectory(
                        Path dir, BasicFileAttributes attrs) {
                    System.out.println("enter " + name(dir));
                    return FileVisitResult.CONTINUE;
                }

                @Override
                public FileVisitResult visitFile(
                        Path file, BasicFileAttributes attrs) {
                    System.out.println("file " + name(file));
                    return FileVisitResult.CONTINUE;
                }

                @Override
                public FileVisitResult postVisitDirectory(
                        Path dir, IOException exc) throws IOException {
                    if (exc != null) throw exc;
                    System.out.println("leave " + name(dir));
                    return FileVisitResult.CONTINUE;
                }
            });
        } finally {
            // Clean up data created by the program: files first, directories afterward.
            Files.deleteIfExists(root.resolve("docs").resolve("note.txt"));
            Files.deleteIfExists(root.resolve("docs"));
            Files.deleteIfExists(root);
        }
    }
}
```

Compile and run:

```bash
javac TreeOrderDemo.java
java TreeOrderDemo
```

Stdout on a normally functioning temporary filesystem:

```text
enter root
enter docs
file note.txt
leave docs
leave root
```

This sequence shows:

1. `preVisitDirectory(root)` runs before `preVisitDirectory(docs)`.
2. `visitFile(note.txt)` occurs while inside `docs`.
3. `postVisitDirectory(docs)` runs before `postVisitDirectory(root)`.
4. `postVisitDirectory` is the proper place to delete a directory **after** its children have been processed.

This illustrates the callback lifecycle; cleanup in `finally` intentionally calls `deleteIfExists` from deepest to shallowest because we already know the structure. For an arbitrary unknown tree, you must traverse to discover all entries.

## 5. Recipe for Copying a Directory Tree

Given:

- `source`: source root directory, e.g., `/data/project`.
- `target`: new destination directory, e.g., `/backup/project`.
- For each `dir` in the source tree, its corresponding destination path is `target.resolve(source.relativize(dir))`.
- For each `file`, use the same mapping.

Example:

```text
source = /data/project
target = /backup/project

file:        /data/project/docs/help.txt
relative:    docs/help.txt
destination: /backup/project/docs/help.txt
```

`source.relativize(path)` yields the **relative path within the source tree**, and `target.resolve(...)` places it inside the destination tree. When `source` and `path` share the same filesystem, this mapping is straightforward and avoids brittle string replacements like `replace("project", "backup")` that can accidentally alter filenames.

### Two Key Callbacks When Copying

```java
// Illustrative snippet; source and target are defined Paths.
// These are callbacks inside a SimpleFileVisitor<Path>.
@Override
public FileVisitResult preVisitDirectory(
        Path dir, BasicFileAttributes attrs) throws IOException {
    Path destination = target.resolve(source.relativize(dir));
    Files.createDirectory(destination);
    return FileVisitResult.CONTINUE;
}

@Override
public FileVisitResult visitFile(
        Path file, BasicFileAttributes attrs) throws IOException {
    Path destination = target.resolve(source.relativize(file));
    Files.copy(file, destination, LinkOption.NOFOLLOW_LINKS);
    return FileVisitResult.CONTINUE;
}
```

This is **not a standalone program**, as `source`, `target`, and imports come from outside. The first callback creates parent directories; the second copies each entry once its parent already exists. The full program in the next section implements this exact principle.

`Files.copy(file, destination, LinkOption.NOFOLLOW_LINKS)` avoids **following symbolic links on the source file**. On providers supporting links, this attempts to copy the link itself; if the destination provider does not support it, `IOException` or an unsupported-operation exception may occur. Do not assume copying symbolic links works universally across systems.

### Does Copy Preserve All Metadata?

No. `Files.copy` does not preserve all permissions, owner, ACLs, timestamps, or attributes by default. `StandardCopyOption.COPY_ATTRIBUTES` requests a best-effort attribute copy, yet what gets preserved depends on the provider and filesystem. If you need to preserve directory attributes, applying them **after copying all children** can be better, because creating files inside a directory can update the directory's modification timestamp.

This lesson prioritizes **structure and contents**; it does not promise preserving all metadata.

## 6. Recipe for Deleting a Directory Tree

The reverse of copying:

```java
// Illustrative snippet of SimpleFileVisitor<Path> callbacks.
@Override
public FileVisitResult visitFile(
        Path file, BasicFileAttributes attrs) throws IOException {
    Files.delete(file);
    return FileVisitResult.CONTINUE;
}

@Override
public FileVisitResult postVisitDirectory(
        Path dir, IOException exc) throws IOException {
    if (exc != null) throw exc;
    Files.delete(dir);
    return FileVisitResult.CONTINUE;
}
```

This is **not a standalone program**. Key points:

- `visitFile`: deletes each file and each entry not traversed deeply as a directory.
- `postVisitDirectory`: deletes the directory **after** its entries have been processed.
- `if (exc != null) throw exc;`: if traversal did not complete cleanly, **do not pretend the directory was fully processed**.
- `visitFileFailed`: leave `SimpleFileVisitor`'s default error propagation, or override to report failure per policy. Never just `return CONTINUE` and mark the operation successful.

A concurrently modified tree, locked entry, or missing permissions can cause `Files.delete` to fail. Tree deletion **is not atomic**: if an error happens mid-way, part of the tree may already be deleted while the rest remains.

## 7. Complete Java 17+ Example: Copying Then Deleting a Tree

The **`TreeCopyDeleteDemo.java`** program below:

1. Creates a sandbox inside an isolated temporary directory.
2. Builds a source tree with a subdirectory and two files.
3. Copies the tree to a **nonexistent** target directory using `preVisitDirectory` and `visitFile`.
4. Verifies contents and file presence by reading the destination.
5. Deletes the target tree in `visitFile → postVisitDirectory` order.
6. Cleans up the source tree and temporary sandbox in `finally`.

The program operates only on data it creates itself and **never deletes paths supplied externally by a user**.

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;

public class TreeCopyDeleteDemo {
    static void copyTree(Path source, Path target) throws IOException {
        final Path src = source.toAbsolutePath().normalize();
        final Path dst = target.toAbsolutePath().normalize();

        // Lexical guard only; for untrusted input additional safeguards are needed.
        if (src.equals(dst) || dst.startsWith(src)) {
            throw new IllegalArgumentException("target is inside source");
        }
        if (!Files.isDirectory(src, LinkOption.NOFOLLOW_LINKS)) {
            throw new IOException("source must be a directory");
        }
        if (Files.exists(dst, LinkOption.NOFOLLOW_LINKS)) {
            throw new FileAlreadyExistsException(dst.toString());
        }

        Files.walkFileTree(src, new SimpleFileVisitor<Path>() {
            @Override
            public FileVisitResult preVisitDirectory(
                    Path dir, BasicFileAttributes attrs) throws IOException {
                Path destination = dst.resolve(src.relativize(dir));
                Files.createDirectory(destination);
                return FileVisitResult.CONTINUE;
            }

            @Override
            public FileVisitResult visitFile(
                    Path file, BasicFileAttributes attrs) throws IOException {
                Path destination = dst.resolve(src.relativize(file));
                Files.copy(file, destination, LinkOption.NOFOLLOW_LINKS);
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
                if (exc != null) throw exc;
                return FileVisitResult.CONTINUE;
            }
        });
    }

    static void deleteTree(Path root) throws IOException {
        // By default, walkFileTree DOES NOT follow symbolic links.
        Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
            @Override
            public FileVisitResult visitFile(
                    Path file, BasicFileAttributes attrs) throws IOException {
                Files.delete(file);
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
                if (exc != null) throw exc;
                Files.delete(dir);
                return FileVisitResult.CONTINUE;
            }
        });
    }

    public static void main(String[] args) throws IOException {
        Path sandbox = Files.createTempDirectory("tree-demo-");
        Path source = sandbox.resolve("source");
        Path target = sandbox.resolve("copy");

        try {
            Files.createDirectory(source);
            Files.createDirectory(source.resolve("docs"));
            Files.writeString(source.resolve("note.txt"),
                    "hello", StandardCharsets.UTF_8);
            Files.writeString(source.resolve("docs").resolve("guide.txt"),
                    "guide", StandardCharsets.UTF_8);

            copyTree(source, target);

            System.out.println("root copied = "
                    + Files.isDirectory(target));
            System.out.println("nested file copied = "
                    + Files.isRegularFile(target.resolve("docs")
                            .resolve("guide.txt")));
            System.out.println("copied content = "
                    + Files.readString(target.resolve("note.txt"),
                            StandardCharsets.UTF_8));
            System.out.println("source remains = "
                    + Files.exists(source));

            deleteTree(target);
            System.out.println("copy deleted = "
                    + Files.notExists(target));
        } finally {
            // Clean up data created by the example itself, even after a copy error.
            if (Files.exists(target, LinkOption.NOFOLLOW_LINKS)) {
                deleteTree(target);
            }
            if (Files.exists(source, LinkOption.NOFOLLOW_LINKS)) {
                deleteTree(source);
            }
            Files.deleteIfExists(sandbox);
        }
    }
}
```

Run:

```bash
javac TreeCopyDeleteDemo.java
java TreeCopyDeleteDemo
```

Stdout when temporary file operations succeed:

```text
root copied = true
nested file copied = true
copied content = hello
source remains = true
copy deleted = true
```

### Why Is This Code in the Right Order?

**In `copyTree`:**

- The first `preVisitDirectory(src)` creates `dst`, the root directory of the destination tree.
- For every subdirectory, the callback creates the corresponding directory before the visitor descends into its entries.
- `visitFile` performs the copy after the parent directory has already been created.
- `src.relativize(...)` and `dst.resolve(...)` preserve the relative structure of every entry.
- `Files.copy` acts only on each individual file/symlink; the algorithm never assumes copying a directory copies its contents recursively.

**In `deleteTree`:**

- `visitFile` deletes each file/symlink when encountered.
- Only after a directory's children have been processed does `postVisitDirectory` delete that directory.
- The root directory `target` is also deleted in the final callback, after all contents inside it.

### Intentional Limitations of the Example

To keep the example easy to run, it assumes **regular files and directories on a writable temporary filesystem**. It is not a general-purpose production copy/delete library:

- It rejects targets inside the source only using a **lexical path check**; it does not guard against symlinks/junctions, mounts, concurrent modifications, or entries renamed mid-operation.
- It does not overwrite existing destinations or merge directory contents.
- It does not fully copy ACLs, owners, all timestamps, hard links, or provider-specific features.
- It does not guarantee atomicity; if copying fails mid-way, the destination may be left partially created.
- It imposes no limits on total file count, bytes, depth, or duration against external data.
- `finally` demonstrates cleanup in a private sandbox. For important data, deleting source/target after a failure must follow a **recovery policy**, never unconditional deletion as in test data.

## 8. Why Should You Not Copy a Tree Inside the Source Itself?

Suppose you copy `source/` to `source/backup/`. As the visitor walks `source`, it may see the newly created `backup` directory during traversal. Depending on timing and enumeration order, the program could accidentally copy the destination directory into itself, loop uncontrollably, or generate an expanding tree.

Therefore, a tree-copy algorithm should:

1. Reject `source == target`.
2. Reject targets that are subpaths of source according to an explicit policy.
3. Explicitly resolve cases where symlinks or mounts make real paths differ from logical path names.
4. Avoid copying a tree being concurrently modified if the output requires a consistent snapshot.

`dst.startsWith(src)` after normalization is only a **syntactic** check, not a security guarantee. With user-supplied paths, the application also needs permission controls, symlink handling, real-directory verification, and race defenses where possible.

Likewise, never let target **enclose** source and accidentally overwrite source files through an ill-designed mapping. When source/target relationships are complex, separate storage/staging areas cleanly.

## 9. Symbolic Links, Symlink Loops, and Special Files

By default:

```java
Files.walkFileTree(start, visitor);
```

is equivalent to traversing without `FileVisitOption.FOLLOW_LINKS` across all depths. Therefore:

- A symlink pointing to another directory **is not descended into** during default traversal.
- `visitFile` can receive symlink entries even though they are not regular files.
- When deleting, `Files.delete(linkPath)` deletes **the symlink entry itself**, not the tree it points to (under standard providers supporting symbolic links).
- When copying with `LinkOption.NOFOLLOW_LINKS`, we request copying **the symbolic link itself**, not the data at its target. Verify the destination supports that entry type.
- If `FOLLOW_LINKS` is enabled, traversal can leave the initial scope via links. Java detects cycles and reports `FileSystemLoopException` via `visitFileFailed`, yet that **does not replace path-protection policies**.

**Why should tree deletion normally not follow symbolic links?** Because a link inside the directory you intend to delete could point to another tree outside the allowed scope. Accidentally recursing into the link could delete data **not belonging** to the intended target tree.

Also consider:

- Special files, FIFOs/socket nodes, or virtual filesystems with special semantics.
- Permissions and open/locked files.
- Limits on filename length, path length, quota, and max depth.
- Providers lacking support for symlinks, owner metadata, or special operations.

For untrusted inputs or high security assurances, a simple `walkFileTree` does not lock the tree against concurrent modifications. Design permissions, scope boundaries, symlink policies, and—when supported by the provider—consider directory-handle-relative APIs such as `SecureDirectoryStream`.

## 10. How Should Errors Be Handled in Callbacks?

### Cannot Read a File or Open a Directory

`visitFileFailed(file, exc)` receives the error that prevented accessing an entry. If the goal is **complete copy** or **complete deletion**, the safe default is to **rethrow the exception**, not ignore it silently.

```java
// Callback snippet, not a standalone program.
@Override
public FileVisitResult visitFileFailed(
        Path file, IOException exc) throws IOException {
    throw exc;
}
```

If business logic permits **best-effort** (process as much as possible), collect errors per path. However, report the result as **partially completed**—never describe it as “copied/deleted the entire tree” when errors occurred.

### Cannot Finish Iterating a Directory

`postVisitDirectory(dir, exc)` receives `exc != null` when directory traversal failed—for instance, failing to complete listing entries. When deleting, you cannot assume the directory is empty and valid to delete.

```java
// Callback snippet.
@Override
public FileVisitResult postVisitDirectory(
        Path dir, IOException exc) throws IOException {
    if (exc != null) throw exc;
    Files.delete(dir);
    return FileVisitResult.CONTINUE;
}
```

### `DirectoryNotEmptyException` and Races

If another process creates a new file inside a directory after the visitor finished listing it but before `Files.delete(dir)`, deleting the directory can fail. `DirectoryNotEmptyException` does not mean Java got the order wrong: the tree may have changed.

Similarly, a file can be deleted by another process right before `Files.delete(file)` runs, throwing `NoSuchFileException`. You can choose `deleteIfExists` if missing files are acceptable to business logic; do not blindly replace every `delete` with `deleteIfExists` if existence is an important invariant.

### Why `try/catch` Does Not Make Operations Atomic

Wrapping the entire traversal in `try/catch(IOException)` helps report errors, yet **does not undo** files already copied or deleted. Entries created or deleted before a callback failed remain in their new state. Staging, rollback, or reconciliation mechanisms are needed if the domain requires consistent state.

## 11. `Files.walk()` vs. `Files.walkFileTree()`

`Files.walk(root)` returns a `Stream<Path>` over paths in the tree. It is convenient when you just want to filter or aggregate a list of files. Yet for copy/delete with parent–child dependencies, `walkFileTree` expresses callback semantics much more clearly.

| Criterion | `Files.walk(root)` | `Files.walkFileTree(root, visitor)` |
| --- | --- | --- |
| Return type | `Stream<Path>`, must be closed | Returns starting `Path` after traversal |
| Pre/post control | No separate pre/post callbacks | Provides `preVisitDirectory` and `postVisitDirectory` |
| Error distinction | Stream traversal errors can become `UncheckedIOException` | Provides `visitFileFailed` and `exc` parameter |
| Path filtering/counting | Convenient with Stream API | Handled via visitor/state |
| Copying tree parent-first | Requires organizing ordering constraints manually | `preVisitDirectory` fits naturally |
| Deleting tree children-first | Requires explicit sorting | `postVisitDirectory` fits naturally |
| Symlinks | Does not follow by default; optional | Does not follow by default; optional |

Some online examples use:

```java
// Snippet, not a standalone program:
try (Stream<Path> stream = Files.walk(root)) {
    stream.sorted(Comparator.reverseOrder())
          .forEach(path -> {
              // Delete each path...
          });
}
```

This approach **does not automatically solve** I/O exceptions, deletion scope boundaries, or mutating paths. Using a Stream requires closing it and handling `IOException` during deletion (lambdas may force wrapping into unchecked exceptions). Path comparison order also depends on provider semantics: never treat raw `Path.toString()` lexicographical order as universal proof of parent–child ordering. For copy/delete, a visitor with pre-parent and post-parent callbacks expresses intent far better.

### Does `FileVisitor` Guarantee Filename Order?

No. Entry order inside a directory usually depends on the filesystem/provider and data state. If business requirements demand ascending filename order, design a separate listing/sorting mechanism and manage resources properly. **Never make copy/delete correctness depend on alphabetical sibling order.**

## 12. Metadata and When to Copy Attributes

A “copy tree” task sometimes needs to preserve permissions, modification times, owner, or ACLs. However, `COPY_ATTRIBUTES` does not guarantee all metadata is preserved and can behave differently across POSIX, Windows, ZIP, or cloud providers.

Especially for **directories**, if you copy timestamps too early in `preVisitDirectory`, creating files and subdirectories inside afterward can update the directory's `lastModifiedTime`. One design approach is:

1. `preVisitDirectory`: create the destination directory and set needed write permissions.
2. `visitFile`: copy files and whichever attributes are actually supported.
3. `postVisitDirectory`: after all children complete, set directory metadata per contract (if required and supported by the provider).
4. If mandatory metadata cannot be copied, report failure rather than treating the copy as “succeeded” without verification.

Algorithm illustration, **not a standalone program**:

```java
// Assumes source/destinationDirectory are valid Paths;
// policies and error handling are decided by the caller.
FileTime stamp = Files.getLastModifiedTime(sourceDirectory);
Files.setLastModifiedTime(destinationDirectory, stamp);
```

This snippet requires importing `java.nio.file.attribute.FileTime` and declaring the variables. There is no guarantee every provider allows setting exact timestamps or preserving owners/ACLs.

## 13. Copying/Deleting Real Data: Safety and Recovery

Copying or deleting a large tree has many failure points: disk space, network errors, permissions, symlinks, excessive entry counts, depth limits, concurrent file edits, or process termination.

A production workflow should define:

1. **Source and target:** canonical/real locations where appropriate; reject copying target inside source; never mix paths from incompatible providers in `relativize`.
2. **Entry types:** regular files, directories, symlinks, special files, and a strategy for each.
3. **Quotas:** limits on file count, total bytes, depth, and execution time; never copy unbounded external data blindly.
4. **Overwrite rules:** no overwrite, verified overwrite, or versioning; resolve name/permission conflicts.
5. **Staging:** optionally copy into a staging directory at the destination and publish after verification. Staging does not automatically make an entire cross-filesystem tree copy atomic.
6. **Verification:** verify file completeness, sizes, hashes where needed, and mandatory attributes; do not treat `Files.copy` returning as sufficient for all business checks.
7. **Mid-way failures:** report succeeded and failed paths, and decide cleanup based on data ownership; never auto-delete the only copy of source data.
8. **Deletion:** validate the exact target directory, keep backups/confirmations when required by domain rules, and never follow symlinks out of scope.
9. **Concurrency:** consider locking, snapshots, or pausing writers if consistency is mandatory; `walkFileTree` does not snapshot the entire tree.
10. **Providers:** ZIP, network, and cloud filesystems have different limits and exceptions; test on the real target provider.

For **deletion**, never call `deleteTree` on an empty path, a filesystem root, or an unverified request path in a production application. A demo deleting a temporary directory it created itself is safe within a lesson; that does not grant permission to delete arbitrary user data.

## 14. Ordering Summary Table

| Task | Right Timing | Callback |
| --- | --- | --- |
| Copy parent directory | Before entering child entries | `preVisitDirectory` |
| Copy file | After destination parent directory exists | `visitFile` |
| Set directory metadata after copy | After copying all children (when needed) | `postVisitDirectory` |
| Delete file/symlink | When encountering the entry | `visitFile` |
| Delete directory | After deleting all children | `postVisitDirectory` |
| Handle inaccessible file | On access failure | `visitFileFailed` |
| Detect directory iteration error | In post-visit callback | Check `exc` in `postVisitDirectory` |

## 15. Common Mistakes

1. **Calling `Files.copy(sourceDir, targetDir)` and expecting all children to be copied.** This API does not copy recursively.
2. **Calling `Files.delete(root)` while `root` still has children.** You must delete child entries before deleting `root`.
3. **Creating a destination file before its parent directory exists.** Use `preVisitDirectory` to create target directories level by level.
4. **Deleting a directory inside `preVisitDirectory`.** Children have not been deleted yet, usually causing `DirectoryNotEmptyException`.
5. **Copying to a target inside source.** Can cause the copy tree to walk into itself; block according to trust policies.
6. **Using `Files.walk` and forgetting to close the `Stream`.** Can hold descriptors/directory handles; use `try-with-resources`.
7. **Following symbolic links by default when deleting.** Can escape scope and destroy unrelated data; `walkFileTree` does not follow links by default.
8. **Swallowing `IOException` in a visitor and reporting completion.** Leads to missing copied files or half-deleted trees.
9. **Ignoring `exc` in `postVisitDirectory`.** You cannot conclude the directory was traversed completely.
10. **Assuming recursive copy/delete is a transaction.** Partial success is possible; define retry/cleanup policies.
11. **Assuming every provider supports symlinks, ACLs, owners, and timestamps identically.** Capabilities vary; test on target environments.
12. **Trying to “finish deleting” a tree while a writer keeps creating new files.** Can fail repeatedly or delete unexpected entries.
13. **Comparing only path strings to protect critical data.** Symlinks and races can make real locations differ from expectations.
14. **Using `FileVisitResult.SKIP_SUBTREE` yet counting the tree as fully processed.** Skipped entries remain untouched.
15. **Relying on alphabetical order of sibling files for algorithm correctness.** `walkFileTree` makes no such promise; rely on parent–child relationships.

## 16. Self-Check

**Question 1.** Why must destination directories be created in `preVisitDirectory` rather than `postVisitDirectory`?

**Answer:** Because child files and subdirectories need their parent to exist before copying. `postVisitDirectory` runs after children are processed, which is too late to create the parent.

**Question 2.** Why must a directory be deleted in `postVisitDirectory` rather than `preVisitDirectory`?

**Answer:** Because a directory containing child entries cannot be deleted as an empty directory. The post-visit callback runs after children have been processed.

**Question 3.** A file fails with a read permission error while copying a tree. Should you `return CONTINUE` and report “full copy”?

**Answer:** No. Rethrow/report the error, or mark the result as partially completed if business logic allows skipping.

**Question 4.** While walking to delete a tree, there is a symbolic link pointing to another directory; should you automatically enable `FOLLOW_LINKS`?

**Answer:** Not by default. Protect the deletion scope; not following links by default removes the link entry instead of descending into its target.

**Question 5.** Why is `target.resolve(source.relativize(file))` useful when copying a tree?

**Answer:** It preserves the file's relative path within `source` and appends it to `target`, preserving directory structure.

**Question 6.** If copying fails after creating some files at `target`, is automatic rollback guaranteed?

**Answer:** No. You must build cleanup, staging, and result verification strategies if required by your domain.

**Question 7.** Can you rely on `Files.walkFileTree` to visit `a.txt` before `b.txt`?

**Answer:** No. The API does not guarantee name order among same-level entries; it only guarantees callback ordering before/after child elements.

**Question 8.** Does `DirectoryNotEmptyException` when deleting a finished directory always mean an ordering bug?

**Answer:** No. Another process may have just created a new file, or the visitor may have skipped or errored on an entry. Investigate the root cause.

## 17. Java 17 Documentation

- [`Files.walkFileTree`, `Files.copy`, `Files.delete`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
- [`FileVisitor` — traversal callbacks](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileVisitor.html)
- [`SimpleFileVisitor` — default behavior and how to override](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/SimpleFileVisitor.html)
- [`FileVisitResult` — `CONTINUE`, `SKIP_SUBTREE`, `SKIP_SIBLINGS`, `TERMINATE`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileVisitResult.html)

**Takeaway:** To **copy a tree**, create each destination directory when entering it (`preVisitDirectory`), then copy individual files (`visitFile`). To **delete a tree**, delete files in `visitFile` and delete directories only after all children are processed (`postVisitDirectory`). `Files.walkFileTree` expresses parent–child rules cleanly; final outcomes still depend on error handling, symlinks, permissions, and filesystem state.
