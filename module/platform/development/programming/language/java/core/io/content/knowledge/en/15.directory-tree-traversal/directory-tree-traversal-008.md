# `FOLLOW_LINKS`, Link Cycles, and `FileSystemLoopException` in Java

When traversing a directory tree with Java NIO.2, a **symbolic link** can point to a file, another directory, a directory outside the traversal root, or back to an ancestor. If you follow links without understanding this mechanism, a program can read duplicate data, escape its intended scope, hit a *cycle*, or receive a `FileSystemLoopException`.

The primary APIs involved are:

- `Files.walkFileTree(...)`: traverses a tree and invokes `FileVisitor` callbacks; supports the `FileVisitOption.FOLLOW_LINKS` option.
- `Files.walk(...)` and `Files.find(...)`: create a `Stream<Path>` and can also follow links if `FileVisitOption.FOLLOW_LINKS` is passed.
- `FileSystemLoopException`: exception raised when traversal detects a link cycle while attempting to follow symbolic links; how the error is received or propagated differs between visitors and streams.
- `Files.isSymbolicLink(...)` and `LinkOption.NOFOLLOW_LINKS`: inspect **the link itself** rather than reading the target's attributes by default.

**By default, Java does not follow symbolic links when traversing trees with these APIs.** Enable `FOLLOW_LINKS` only when business requirements explicitly call for exploring linked directories, and establish policies for permissions, depth limits, link cycles, and out-of-bounds paths.

## 1. What Is a Symbolic Link? Why Do Cycles Occur?

A symbolic link is a filesystem entry pointing to another path. It is not like “copying a folder”: following a symlink takes the program to the link's current target. A symlink can point to a file, a directory, or a nonexistent path (*dangling link*).

Example:

```text
workspace/
└── project/
    ├── README.md
    └── back -> workspace/      (symbolic link pointing back to ancestor)

Traversing workspace/ with FOLLOW_LINKS:
workspace/
  -> project/
      -> back (points back to workspace/)
          -> project/
              -> back
                  -> ...
```

On a real tree without link cycles, descending through `project` and finishing its child files is finite. However, when `back` sends traversal back to `workspace`, the path becomes **structurally infinite** unless cycles are checked.

Another example that is not a direct cycle:

```text
safe-root/
└── shortcut -> /other/location/
```

With `FOLLOW_LINKS` enabled, the program can traverse the contents of `/other/location`, even though that location **lies outside the initial root directory**. The absence of `FileSystemLoopException` does not mean data boundaries were respected.

## 2. How Does Default (No Link Following) Differ from Enabling `FOLLOW_LINKS`?

With `Files.walkFileTree`:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;

// Illustrative: root is a defined Path; handle IOException.
Files.walkFileTree(root, new SimpleFileVisitor<Path>() {});
```

This overload **does not follow symbolic links**. Upon encountering a symlink, the visitor normally receives it in `visitFile(...)` as a file/leaf entry, even when it points to a directory. The target directory is not automatically opened or traversed through the link.

To request following symbolic links, use the overload taking an options set:

```java
import java.nio.file.FileVisitOption;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.util.EnumSet;

// Illustrative: root is a defined Path; handle IOException.
Files.walkFileTree(
        root,
        EnumSet.of(FileVisitOption.FOLLOW_LINKS),
        Integer.MAX_VALUE,
        new SimpleFileVisitor<Path>() {}
);
```

Two key points:

1. `FileVisitOption.FOLLOW_LINKS` means **when encountering a link to a directory, attempt to descend into the target directory** instead of treating the link entry alone. If the target is inaccessible, the program must handle the corresponding error.
2. `Integer.MAX_VALUE` here is `maxDepth`: the maximum number of levels from root, **not** a file-count limit or memory limit. Use a very deep limit only when you understand the data scale. If following links is unnecessary, keep the default.

### Comparison Table

| Aspect | Default (no `FOLLOW_LINKS`) | With `FOLLOW_LINKS` |
| --- | --- | --- |
| Symlink to a file | Processes the link itself as an entry | Attempts to access the target file, if possible |
| Symlink to a directory | Treated as a leaf entry; does **not** traverse target directory | Attempts to traverse target directory |
| Symlink back to an ancestor | Not followed, so no link-induced traversal loop | Can detect the loop and report `FileSystemLoopException` |
| Symlink pointing outside root | Does not access external tree via link | **Can** escape outside root |
| Dangling symlink | Still handled as a link entry | Attempts to follow target; if unfollowable, callback/element behavior reflects the link or an API error |
| Risk of duplicate entry visits | Limits symlink-induced duplicates | Can visit the same data via multiple link paths |
| Risk when used for tree deletion | Easier to bound, still requires permission/checks | **Should not be enabled casually**; may affect targets out of scope |

**Do not confuse `FileVisitOption.FOLLOW_LINKS` with `LinkOption.NOFOLLOW_LINKS`.** One is a **tree-traversal** option; the other is an option passed to **attribute and path inspection methods** to avoid following links when reading metadata.

## 3. What Does `FileSystemLoopException` Indicate?

`java.nio.file.FileSystemLoopException` is a subclass of `FileSystemException` and `IOException`, reporting that an operation involving a path encountered a **cycle in the filesystem structure**.

When `walkFileTree` runs with `FOLLOW_LINKS`, Java must check whether a directory it is about to enter matches an **ancestor directory on the current branch**. Cycle detection typically uses file keys from filesystem attributes and may use checks equivalent to `Files.isSameFile(...)` when needed.

Never infer that “two paths with different strings” are definitely two distinct directories. Symlinks, hard links (where supported), mounts, or provider name representations can make multiple names refer to the same resource.

In `walkFileTree`, when a cycle is detected while following a symlink, the error is delivered to the callback:

```java
@Override
public FileVisitResult visitFileFailed(
        Path file, IOException exc) throws IOException {
    if (exc instanceof FileSystemLoopException) {
        System.err.println("Đã phát hiện vòng tại: " + file);
        return FileVisitResult.CONTINUE;
    }
    throw exc;
}
```

This is an **illustrative overridden method** that must reside inside a `FileVisitor` or `SimpleFileVisitor`, importing `Path`, `IOException`, `FileVisitResult`, and `FileSystemLoopException`. Returning `CONTINUE` means **not descending further into the cyclic branch**, while continuing to traverse remaining branches.

If you use `new SimpleFileVisitor<Path>() {}` without overriding `visitFileFailed`, the default implementation rethrows the received `IOException`. Then the entire `walkFileTree` call normally terminates with an exception as soon as it hits the cycle.

### `FileSystemLoopException` Does Not Cover All Errors

An error on another entry may be:

- `AccessDeniedException` if permission is denied;
- `NoSuchFileException` if the path vanished or is inaccessible per filesystem state;
- Another `FileSystemException` if reported by the provider;
- General `IOException` for I/O failures.

**Not every `IOException` is a link cycle.** If you only want to skip a detected cycle, handle `FileSystemLoopException` specifically and let other errors propagate (or handle them per policy).

## 4. Standalone Java 17+ Program

The example below creates a temporary directory with a file and tries to create a symlink from a subdirectory back to the root directory. If the environment allows creating symbolic links, this forms a genuine **link cycle**. The example traverses first **without** following links, then a second time with `FOLLOW_LINKS` enabled, counting `FileSystemLoopException` callbacks.

Some operating systems or accounts (especially Windows without symbolic-link privileges) may **disallow** creating links. The program still runs and prints results without a link, as that behavior depends on the environment. Only in this demo do we ignore symlink-creation failure so the non-link traversal path can still be observed; real applications must distinguish and handle errors properly.

Save as file **`FollowLinksLoopDemo.java`**:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileSystemLoopException;
import java.nio.file.FileVisitOption;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.EnumSet;

public class FollowLinksLoopDemo {

    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("java-follow-links-");
        Path child = Files.createDirectory(root.resolve("child"));
        Path file = child.resolve("note.txt");
        Path link = child.resolve("back-to-root");

        boolean linkCreated = false;

        try {
            Files.writeString(file, "Java", StandardCharsets.UTF_8);

            try {
                // Create cycle: child/back-to-root -> root.
                Files.createSymbolicLink(link, root);
                linkCreated = true;
            } catch (UnsupportedOperationException
                     | SecurityException | IOException unsupported) {
                // This demo still runs if the link cannot be created.
            }

            final int[] linkLeaves = {0};
            Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
                @Override
                public FileVisitResult visitFile(
                        Path path, BasicFileAttributes attrs) {
                    if (Files.isSymbolicLink(path)) {
                        linkLeaves[0]++;
                    }
                    return FileVisitResult.CONTINUE;
                }
            });

            final int[] loopErrors = {0};
            Files.walkFileTree(
                    root,
                    EnumSet.of(FileVisitOption.FOLLOW_LINKS),
                    16,
                    new SimpleFileVisitor<Path>() {
                        @Override
                        public FileVisitResult visitFileFailed(
                                Path path, IOException exc)
                                throws IOException {
                            if (exc instanceof FileSystemLoopException) {
                                loopErrors[0]++;
                                return FileVisitResult.CONTINUE;
                            }
                            throw exc;
                        }
                    });

            System.out.println("Symlink created: " + linkCreated);
            System.out.println("No-follow link leaves: "
                    + linkLeaves[0]);
            System.out.println("Detected link loops: "
                    + loopErrors[0]);
            System.out.println("Traversal completed: true");
        } finally {
            // Delete only entries created by this example itself.
            Files.deleteIfExists(link);
            Files.deleteIfExists(file);
            Files.deleteIfExists(child);
            Files.deleteIfExists(root);
        }
    }
}
```

Run with JDK 17+:

```bash
javac -encoding UTF-8 FollowLinksLoopDemo.java
java FollowLinksLoopDemo
```

**Stdout when the environment allows creating symlinks and the cycle callback is detected:**

```text
Symlink created: true
No-follow link leaves: 1
Detected link loops: 1
Traversal completed: true
```

**Stdout when creating symlinks is not permitted:**

```text
Symlink created: false
No-follow link leaves: 0
Detected link loops: 0
Traversal completed: true
```

Explanation:

1. `Files.createTempDirectory` creates an isolated test area, avoiding user data. `root.resolve(...)` only computes paths; `Files.createDirectory`, `Files.writeString`, and `Files.createSymbolicLink` perform actual I/O.
2. If the link is created, `child/back-to-root` points back to `root` — forming a cycle along `root → child → back-to-root → root`.
3. The default `walkFileTree(root, visitor)` **does not follow links**; the symlink is passed to `visitFile`, so `linkLeaves=1`.
4. The second `walkFileTree` enables `FOLLOW_LINKS`. When attempting to enter the link pointing back to an ancestor, `visitFileFailed` receives `FileSystemLoopException` and increments `loopErrors`.
5. Returning `FileVisitResult.CONTINUE` completes traversal instead of aborting with an exception. Without a cycle, that callback does not increment the counter.
6. `finally` cleans up **the link entry** first, then the file, subdirectory, and root. Deleting a symlink **does not delete the target directory** `root`. If external processes interfere in practice, cleanup can still throw `IOException`; using a dedicated temporary directory minimizes that risk.

**Do not run this program against production directories.** It creates its own isolated directory and never recursively deletes arbitrary user-supplied directories.

## 5. Comparing `Files.walkFileTree`, `Files.walk`, and `Files.find` on Cycles

### `walkFileTree`: Errors Go Through `FileVisitor`

With `Files.walkFileTree`, the key callback is:

```java
Files.walkFileTree(
        root,
        EnumSet.of(FileVisitOption.FOLLOW_LINKS),
        20,
        new SimpleFileVisitor<Path>() {
            @Override
            public FileVisitResult visitFileFailed(
                    Path file, IOException exc)
                    throws IOException {
                if (exc instanceof FileSystemLoopException) {
                    return FileVisitResult.CONTINUE;
                }
                throw exc;
            }
        });
```

This is illustrative code inside a class/method with matching imports and an existing `root` variable. If you want to record errors rather than ignore them, you can store paths in a diagnostic list, though storing too many entries increases RAM usage.

The advantage of `walkFileTree` is separate callbacks:

- `preVisitDirectory(dir, attrs)`: called before processing directory contents;
- `visitFile(file, attrs)`: processes a file/leaf entry;
- `visitFileFailed(file, exc)`: handles failures visiting an entry, including loop errors when following links;
- `postVisitDirectory(dir, exc)`: called after processing a directory; `exc` can reflect directory-iteration errors.

Callbacks return `FileVisitResult` to decide whether to continue, skip a branch/siblings, or terminate. When you want to **follow links while still handling cycles and specific errors**, `walkFileTree` usually expresses the policy more cleanly.

### `Files.walk`: Returns `Stream<Path>`

`Files.walk(root)` does not follow symbolic links by default. To follow links:

```java
import java.nio.file.FileVisitOption;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

try (Stream<Path> paths =
        Files.walk(root, 20, FileVisitOption.FOLLOW_LINKS)) {
    paths.forEach(System.out::println);
}
```

This is an illustrative snippet requiring a defined `root` and proper exception handling. `Files.walk` creates a **lazy** stream: directory-reading errors can surface during stream consumption, not only when calling `walk(...)`. On I/O errors during traversal, the API may wrap `IOException` into **`UncheckedIOException`**; for a link cycle, `FileSystemLoopException` can be found in **`getCause()`**.

```java
try (Stream<Path> paths =
        Files.walk(root, 20, FileVisitOption.FOLLOW_LINKS)) {
    paths.forEach(System.out::println);
} catch (java.io.UncheckedIOException e) {
    if (e.getCause() instanceof FileSystemLoopException) {
        System.err.println("Đã gặp vòng liên kết");
    } else {
        throw e;
    }
}
```

This is an illustrative snippet requiring imports for `Path`, `Files`, `FileVisitOption`, and `Stream`, plus handling `IOException` that may happen immediately on stream creation. With a stream, there is no `visitFileFailed` to continue past a single cycle; once the iterator/stream throws, the consuming pipeline has no visitor-style mechanism to skip only that branch and continue.

**Always close `Stream<Path>`** from `Files.walk` or `Files.find` using `try-with-resources`; the stream can hold open directory resources.

### `Files.find`: Searches by Attributes Yet Carries Similar Risks

`Files.find(root, maxDepth, matcher, options...)` can use `FOLLOW_LINKS`. It passes `BasicFileAttributes` to the predicate, which is handy for metadata filtering, yet **does not automatically eliminate link cycles or prevent escaping outside root** when following links. On a lazy stream, I/O exceptions can occur during consumption and the stream must be closed.

Do not write `Files.find(... FOLLOW_LINKS)` assuming you are immune to cycles merely because the predicate selects `.txt` files: the walker still has to **traverse** directories to find matching files.

## 6. Maximum Depth and Branch-Skipping Policies

`maxDepth` is a scope-limiting tool, but **does not replace cycle detection or security checks**.

```java
Files.walkFileTree(
        root,
        EnumSet.of(FileVisitOption.FOLLOW_LINKS),
        3,
        visitor);
```

This is an illustrative snippet assuming `root`, `visitor`, and appropriate imports. `maxDepth=0` visits only the root entry; once depth reaches the limit, the API descends no further (entries at the final depth are handled as leaves per the visitor contract). `maxDepth=3` inspects up to three levels from root.

However:

- A directory at depth 1 can contain millions of entries; **a depth limit does not limit total entry count**.
- A symlink at shallow depth can lead outside the root tree without creating a cycle.
- If you only traverse shallowly enough not to hit the cyclic link, you may **never observe `FileSystemLoopException`**, even though the cyclic link still exists.
- For large trees, you still need bounds on time, entry count, permissions, and I/O error handling.

Inside `FileVisitor`, you can return:

| Value | Meaning When Supported by Callback |
| --- | --- |
| `CONTINUE` | Continue normal traversal |
| `SKIP_SUBTREE` | Skip subdirectories/entries inside the current directory, suitable in `preVisitDirectory` |
| `SKIP_SIBLINGS` | Skip remaining sibling entries in the callback's context |
| `TERMINATE` | Stop the entire traversal |

For instance, if you only care about directories containing documents, you can skip large unused branches right in `preVisitDirectory`. Do not enable `FOLLOW_LINKS` unless entering symlinks is actually required.

## 7. Where Is `NOFOLLOW_LINKS` Used?

`LinkOption.NOFOLLOW_LINKS` **differs** from `FileVisitOption.FOLLOW_LINKS`. It is passed to metadata-querying APIs:

```java
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;

boolean entryExists = Files.exists(
        path, LinkOption.NOFOLLOW_LINKS);

BasicFileAttributes attrs = Files.readAttributes(
        path, BasicFileAttributes.class,
        LinkOption.NOFOLLOW_LINKS);

System.out.println("Is symbolic link: " + attrs.isSymbolicLink());
```

This is an illustrative snippet inside a method handling `IOException`, with `path` already declared. Passing `NOFOLLOW_LINKS` lets metadata reflect **the link entry itself**, rather than the target's attributes.

For a quick check:

```java
boolean link = Files.isSymbolicLink(path);
```

`Files.isSymbolicLink(path)` checks whether an entry is a symbolic link without requiring you to open or traverse the target directory.

**Dangling links:** `Files.exists(link)` by default follows the link and thus may return `false` when the target is gone, whereas `Files.exists(link, NOFOLLOW_LINKS)` can still be `true` because the link entry itself remains present. Do not use default `exists` to verify whether a symlink itself was deleted.

## 8. Link Cycles vs. Duplicate Visits Without a Cycle

Two scenarios must be distinguished:

**Cycle:**

```text
A/child/back -> A
Following the link from A/child/back leads back to ancestor A.
```

**Duplicate visit that is not a cycle on the current branch:**

```text
root/
├── original/
│   └── x.txt
└── alias -> original/
```

When following `alias`, the same file `x.txt` can be visited again through another path. Because `original` is not an **ancestor of `alias` on the current branch**, this does **not necessarily** trigger `FileSystemLoopException`.

If business logic must process **each physical object at most once**, cycle detection is not enough: you need a deduplication strategy using filesystem identifiers or `Files.isSameFile` where appropriate. Comparing `Path.toString()` does not prove two files differ; conversely, indicators like `BasicFileAttributes.fileKey()` may be `null` or have filesystem/provider-specific behavior.

A `Set<Path>` holding distinct path strings **is not enough** to guarantee no duplicate content when symlinks or hard links exist. Clarify whether you want to “traverse every **path**” or “process each **distinct physical file**.”

## 9. Security: Do Not Follow Links Casually on Untrusted Data

The biggest hazard is not merely a link cycle slowing down a program. With `FOLLOW_LINKS`, a link can point to a directory tree the application **never intended** to access.

Example layout:

```text
uploads/
└── external -> /private-data/
```

If code scans all of `uploads` with `FOLLOW_LINKS` enabled, the process can read metadata or contents of `/private-data` if OS permissions permit. For a **directory-deletion** program, enabling `FOLLOW_LINKS` can cause out-of-scope operations leading to severe data loss.

Recommendations:

1. **Do not follow symlinks by default** unless there is an explicit business requirement.
2. Define allowed root boundaries, ownership, and symbolic-link policies.
3. For user-supplied paths, validate `..` components, absolute paths, and symlink effects; `normalize()` is purely syntactic and **does not establish a complete security boundary**.
4. Enforce bounds on depth, entry count, time, and memory; `maxDepth` alone is insufficient.
5. If links must be followed, consider canonical/real paths, `Files.isSameFile`, tracking visited objects, and error policies, while accounting for filesystem changes between check and use (TOCTOU).
6. Never use a scanner with `FOLLOW_LINKS` as a recursive deletion tool inside user-designated directories without strict safety design.

Even without `FOLLOW_LINKS`, filenames and filesystem contents can change concurrently. Never treat `Files.exists`, `normalize`, or a single scan as proof a file cannot change afterward.

## 10. Error Handling in Real Traversal

A visitor with a clear policy handles **cycles** separately from unexpected failures:

```java
import java.io.IOException;
import java.nio.file.FileSystemLoopException;
import java.nio.file.FileVisitResult;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;

class LoopAwareVisitor extends SimpleFileVisitor<Path> {
    @Override
    public FileVisitResult visitFileFailed(
            Path file, IOException exc) throws IOException {

        if (exc instanceof FileSystemLoopException) {
            System.err.println("Bỏ qua vòng tại: " + file);
            return FileVisitResult.CONTINUE;
        }

        // Do not hide permission errors or other I/O errors.
        throw exc;
    }
}
```

This is an **illustrative class that can be placed in its own file or an enclosing class**. To use it, pass an instance to `Files.walkFileTree(root, EnumSet.of(FOLLOW_LINKS), maxDepth, new LoopAwareVisitor())`. In a real application, you can replace console printing with structured logging, counting cycles, or terminating traversal as required.

### With `postVisitDirectory`

`postVisitDirectory(Path dir, IOException exc)` receives a non-null `exc` if an error occurred while iterating that directory's contents. A general-purpose visitor must decide whether to rethrow, record, or skip errors based on requirements; do not assume all errors arrive via `visitFileFailed`.

### With `Files.walk`

Because this returns `Stream<Path>`, you must close the stream and prepare to handle `UncheckedIOException` during consumption. If the goal is **continuing past a specific `FileSystemLoopException`**, `walkFileTree` with a properly designed visitor is usually clearer than a stream pipeline that aborts when its iterator throws.

## 11. Common Mistakes

| Mistake | Consequence | Solution |
| --- | --- | --- |
| “Java always follows symlinks in `Files.walkFileTree`” | Misunderstands which tree is traversed | **Does not follow by default**; add `FOLLOW_LINKS` only intentionally |
| “`FOLLOW_LINKS` just finds files faster” | Can read duplicates, escape root, and hit cycles | Clarify business requirements before enabling |
| “A link cycle will definitely hang the visitor forever” | Java detects cycles and typically reports `FileSystemLoopException` | Handle `visitFileFailed` or appropriate exceptions |
| “`FileSystemLoopException` arrives in regular `visitFile`” | Misses the error callback | Check `visitFileFailed(file, exc)` in `walkFileTree` |
| “`Files.walk` throws the checked error right at stream creation” | Lazy errors can surface during iteration | Handle `UncheckedIOException` and `getCause()`, and close the stream |
| “`CONTINUE` after a loop re-enters the link” | It skips the failing branch and keeps going | Do not manually invoke traversal again on the same link |
| “A `maxDepth` limit prevents all risks” | Can still hit huge entry counts or external data | Add entry/time/ownership limits |
| “No `FileSystemLoopException` means no duplicate visits” | An alias to the same target that isn't an ancestor still duplicates | Deduplicate if the domain requires it |
| “`Files.exists(link)` definitely inspects the link entry” | Follows the symlink to its target | Use `NOFOLLOW_LINKS` when inspecting the link entry itself |
| “`Path.normalize()` blocks all access outside root” | Symlinks and races change path meaning | Validate real paths and enforce security policies |
| “Traversing with `FOLLOW_LINKS` and deleting everything is safe” | Can delete outside root | Avoid following links in sensitive deletion programs |
| “Returning `CONTINUE` for every `IOException`” | Hides permission and severe I/O failures | Handle loops specifically; report other errors |
| “Forgetting to close a `Files.walk` stream is harmless” | Can leave resources open | Use `try-with-resources` |
| “Every Windows machine can create symlinks” | Depends on privileges/mode and filesystem | Test in a temp directory with fallback handling |

## 12. Self-Check Exercises

1. **If you call `Files.walkFileTree(root, visitor)` without `FOLLOW_LINKS`, is a symlink to a directory traversed deeply?** No; the link is treated as a leaf entry.
2. **Where is `FileVisitOption.FOLLOW_LINKS` passed?** To the `walkFileTree` overload or the varargs of `Files.walk` / `Files.find`.
3. **What error can following `A/child/back -> A` trigger?** `FileSystemLoopException`, because the link leads back to an ancestor.
4. **In `walkFileTree`, where should you catch a cycle?** `visitFileFailed(Path, IOException)`, then check `exc instanceof FileSystemLoopException`.
5. **Does returning `FileVisitResult.CONTINUE` after catching a cycle re-enter the cyclic branch?** No; it skips the failing entry and traverses the rest.
6. **If there are no cycles, is it guaranteed traversal stays inside root?** No; a link can point to an external directory.
7. **Does `maxDepth=3` guarantee visiting at most 100 files?** No; it limits depth, not entry count.
8. **How can `Files.walk` report a cycle during consumption?** As an `UncheckedIOException` whose cause is `FileSystemLoopException`.
9. **Can a dangling symlink with a missing target still appear as an entry?** Yes; use `Files.exists(link, LinkOption.NOFOLLOW_LINKS)` or `Files.isSymbolicLink` to inspect the entry.
10. **Does `FileSystemLoopException` prevent duplicate processing?** No; the same target referenced from another branch may not form an ancestor cycle.
11. **Should you enable `FOLLOW_LINKS` when writing a tool to delete an entire user upload directory?** No, not without strict safeguards; normally links should not be followed.
12. **When a demo cannot create a symlink, does that prove `FOLLOW_LINKS` doesn't work?** No; link creation depends on permissions and provider, whereas `FOLLOW_LINKS` governs traversal when links exist.

**Takeaway:** By default, Java traverses trees **without following symbolic links**. `FOLLOW_LINKS` lets traversal descend into linked directories, but introduces risks of **cycles, duplicate visits, and escaping root**. With `Files.walkFileTree`, use `visitFileFailed` to catch `FileSystemLoopException` and choose `CONTINUE` or error reporting; with `Files.walk`/`find`, watch for I/O exceptions surfacing during stream consumption.
