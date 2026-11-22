# Practical Exercise: Building a Tree Traversal and File Filtering Tool with Java NIO.2

## 1. Problem and Objectives

You need a command-line tool to traverse a root directory along with its subdirectories and print only the **regular files** that satisfy filter conditions. The tool must be useful on large directory trees, produce easily verifiable output, and tolerate individual access errors without losing all results already found.

In this exercise, we will write the `TreeFilter` program in Java 17+ with the following features:

- Accept the **root directory** from a command-line argument.
- Traverse recursively using `Files.walkFileTree` and `SimpleFileVisitor`.
- Filter by **filename glob**, minimum/maximum size (bytes), **depth limit**, and an option to include or exclude hidden entries.
- **Do not follow symbolic links by default**; follow links only when the user enables `--follow-links`.
- Display relative paths and byte sizes on stdout, and statistics and warnings on stderr.
- Continue after per-branch access errors when possible, record the error count, and return an appropriate exit code.
- Create small test data to verify output, then discuss practical limits with large files and deep/wide trees.

This tool **only reads file-structure metadata during traversal**; it does not delete, edit, move, or rename files. The program inspects metadata (file type, size, hidden attribute) and filenames; it **does not open/read full file contents** to search for keywords. If filtering by content is desired, a separate streaming step must be added.

## 2. Designing the CLI Interface

Proposed syntax:

~~~text
java TreeFilter <root> [options]

Options:
  --glob <pattern>     Glob applied to FILENAME (default: *)
  --min-bytes <number> Minimum size in bytes (default: 0)
  --max-bytes <number> Maximum size in bytes (default: Long.MAX_VALUE)
  --max-depth <number> Traversal depth limit, integer >= 1
  --include-hidden     Allow files/directories recognized as hidden by the OS
  --follow-links       Allow following symbolic links; disabled by default
~~~

Options are combined with **AND**. Example command:

~~~bash
java TreeFilter project --glob "*.java" --min-bytes 100 --max-bytes 200000 --max-depth 10
~~~

The program finds Java files matching `*.java`, from 100 to 200,000 bytes, within the tree starting at `project` up to a maximum depth of 10. The glob pattern is applied to **`file.getFileName()`** (only the final name component). Therefore `*.java` can match `src/App.java`, whereas `src/*.java` will **not** match the name `App.java`; to filter by relative path, you must change how `PathMatcher` is applied.

**Depth convention:** root has depth 0, direct children have depth 1, files in a subdirectory have depth 2, and so on. `--max-depth 1` only considers entries directly under the root. Directories at the depth limit are not descended further. This is the tree-traversal limit of `walkFileTree`, not the number of directory levels **printed**.

**Output format:** each result line contains `relative_path<TAB>size_bytes`, formatted using the operating system's `Path.toString()`. Directory separators can be `/` on Unix or `\` on Windows. Simple TSV output is suitable for learning and quick manipulation; filenames containing TAB or newlines need escaping or JSON formatting when building machine-to-machine tools.

## 3. Choosing a Tree Traversal API

Java NIO.2 in `java.nio.file` supports several traversal approaches:

| API | Scope | Key Characteristics |
| --- | --- | --- |
| `Files.list(dir)` | One level | Returns `Stream<Path>`; must close the stream after use |
| `Files.walk(root, depth)` | Multiple levels | Lazy `Stream<Path>`; requires `try-with-resources` to close |
| `Files.find(root, depth, matcher)` | Multiple levels | Predicate receives `Path` and `BasicFileAttributes`; must close the stream |
| `Files.walkFileTree(root, visitor)` | Multiple levels | Event-driven callbacks; controls `SKIP_SUBTREE`, `TERMINATE`, access errors, and links |

`Files.walkFileTree` fits when you want explicit traversal control without holding the entire file list in RAM. `SimpleFileVisitor<Path>` provides default methods for four main hooks:

1. `preVisitDirectory(dir, attrs)`: before entering a directory; can return `SKIP_SUBTREE` to skip the entire branch.
2. `visitFile(file, attrs)`: when encountering an entry visited as a file; `attrs.isRegularFile()` indicates whether it is a regular file.
3. `visitFileFailed(file, exception)`: error reading attributes or unable to visit an entry, including cases where symbolic links form a cycle.
4. `postVisitDirectory(dir, exception)`: after processing a directory; `exception` is non-null if traversal of the directory encountered an error.

Common `FileVisitResult` values are `CONTINUE`, `SKIP_SUBTREE`, `SKIP_SIBLINGS`, and `TERMINATE`. In this exercise we use `CONTINUE` and `SKIP_SUBTREE`; unless aborting the whole traversal is required, do not return `TERMINATE` just because one file fails the filter.

## 4. Full `TreeFilter.java` Implementation

Save the following code verbatim into **`TreeFilter.java`**. The program uses standard JDK APIs and needs no Maven, Gradle, or third-party libraries.

~~~java
import java.io.IOException;
import java.nio.file.FileSystems;
import java.nio.file.FileVisitOption;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.PathMatcher;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.EnumSet;
import java.util.Locale;

import static java.nio.file.FileVisitResult.CONTINUE;
import static java.nio.file.FileVisitResult.SKIP_SUBTREE;

public class TreeFilter {
    private record Config(
            Path root,
            PathMatcher nameMatcher,
            long minBytes,
            long maxBytes,
            int maxDepth,
            boolean includeHidden,
            boolean followLinks) {}

    private static final class Stats {
        long directories;
        long regularFiles;
        long matches;
        long errors;
    }

    public static void main(String[] args) {
        try {
            Config config = parseArgs(args);
            Stats stats = new Stats();

            EnumSet<FileVisitOption> options = config.followLinks()
                    ? EnumSet.of(FileVisitOption.FOLLOW_LINKS)
                    : EnumSet.noneOf(FileVisitOption.class);

            Files.walkFileTree(
                    config.root(),
                    options,
                    config.maxDepth(),
                    new SimpleFileVisitor<Path>() {
                        @Override
                        public FileVisitResult preVisitDirectory(
                                Path dir, BasicFileAttributes attrs) {
                            // Keep permission to traverse root; hidden subdirectories
                            // are excluded along with their entire subtree.
                            if (!dir.equals(config.root())
                                    && !config.includeHidden()) {
                                try {
                                    if (Files.isHidden(dir)) {
                                        return SKIP_SUBTREE;
                                    }
                                } catch (IOException e) {
                                    stats.errors++;
                                    reportError(dir, e);
                                    return SKIP_SUBTREE;
                                }
                            }
                            stats.directories++;
                            return CONTINUE;
                        }

                        @Override
                        public FileVisitResult visitFile(
                                Path file, BasicFileAttributes attrs) {
                            if (!attrs.isRegularFile()) {
                                return CONTINUE;
                            }
                            stats.regularFiles++;

                            if (!config.includeHidden()) {
                                try {
                                    if (Files.isHidden(file)) {
                                        return CONTINUE;
                                    }
                                } catch (IOException e) {
                                    stats.errors++;
                                    reportError(file, e);
                                    return CONTINUE;
                                }
                            }

                            if (!config.nameMatcher().matches(file.getFileName())) {
                                return CONTINUE;
                            }

                            long size = attrs.size();
                            if (size < config.minBytes()
                                    || size > config.maxBytes()) {
                                return CONTINUE;
                            }

                            Path relative = config.root().relativize(file);
                            System.out.printf(Locale.ROOT, "%s\t%d%n",
                                    relative, size);
                            stats.matches++;
                            return CONTINUE;
                        }

                        @Override
                        public FileVisitResult visitFileFailed(
                                Path file, IOException error) {
                            stats.errors++;
                            reportError(file, error);
                            return CONTINUE;
                        }

                        @Override
                        public FileVisitResult postVisitDirectory(
                                Path dir, IOException error) {
                            if (error != null) {
                                stats.errors++;
                                reportError(dir, error);
                            }
                            return CONTINUE;
                        }
                    });

            System.err.printf(Locale.ROOT,
                    "Visited directories=%d, regular files=%d, matches=%d, errors=%d%n",
                    stats.directories, stats.regularFiles,
                    stats.matches, stats.errors);

            if (stats.errors != 0) {
                System.exit(2); // Partial results with access errors.
            }
        } catch (IllegalArgumentException e) {
            System.err.println("Invalid arguments: " + e.getMessage());
            printUsage();
            System.exit(1);
        } catch (IOException e) {
            System.err.println("Traversal failed: " + e);
            System.exit(2);
        }
    }

    private static Config parseArgs(String[] args) {
        if (args.length == 0 || args[0].startsWith("--")) {
            throw new IllegalArgumentException("Root directory is required");
        }

        Path root = Path.of(args[0]).toAbsolutePath().normalize();
        // This exercise requires root to be a real directory, not a symlink.
        if (!Files.isDirectory(root, LinkOption.NOFOLLOW_LINKS)) {
            throw new IllegalArgumentException(
                    "Not a directory: " + root);
        }

        String glob = "*";
        long minBytes = 0L;
        long maxBytes = Long.MAX_VALUE;
        int maxDepth = Integer.MAX_VALUE;
        boolean includeHidden = false;
        boolean followLinks = false;

        for (int i = 1; i < args.length; i++) {
            switch (args[i]) {
                case "--glob" ->
                    glob = nextValue(args, ++i, "--glob");
                case "--min-bytes" ->
                    minBytes = Long.parseLong(
                            nextValue(args, ++i, "--min-bytes"));
                case "--max-bytes" ->
                    maxBytes = Long.parseLong(
                            nextValue(args, ++i, "--max-bytes"));
                case "--max-depth" ->
                    maxDepth = Integer.parseInt(
                            nextValue(args, ++i, "--max-depth"));
                case "--include-hidden" -> includeHidden = true;
                case "--follow-links" -> followLinks = true;
                default -> throw new IllegalArgumentException(
                        "Unknown option: " + args[i]);
            }
        }

        if (minBytes < 0 || maxBytes < 0 || maxBytes < minBytes) {
            throw new IllegalArgumentException("Invalid size range");
        }
        if (maxDepth < 1) {
            throw new IllegalArgumentException(
                    "max-depth must be >= 1");
        }

        // Glob matches on file name, not the entire relative path.
        PathMatcher matcher = FileSystems.getDefault()
                .getPathMatcher("glob:" + glob);
        return new Config(root, matcher, minBytes, maxBytes,
                maxDepth, includeHidden, followLinks);
    }

    private static String nextValue(
            String[] args, int index, String option) {
        if (index >= args.length) {
            throw new IllegalArgumentException(
                    "Missing value for " + option);
        }
        return args[index];
    }

    private static void reportError(Path path, IOException error) {
        System.err.println("WARN " + path + ": " + error);
    }

    private static void printUsage() {
        System.err.println(
                "Usage: java TreeFilter <root> "
                + "[--glob <pattern>] "
                + "[--min-bytes <n>] [--max-bytes <n>] "
                + "[--max-depth <n>] "
                + "[--include-hidden] [--follow-links]");
    }
}
~~~

Compile and run with Java 17 or newer:

~~~bash
javac TreeFilter.java
java TreeFilter . --glob "*.java" --max-depth 5
~~~

Run in any directory containing Java code to see real output; file counts and sizes depend on that directory. Put quotes around the glob so Unix shells do not expand `*.java` into a file list before Java receives the arguments.

### 4.1. Key Mechanics Explained

**`Path` and `PathMatcher`.** `Path.of(args[0])` creates a path object using the default filesystem provider. `toAbsolutePath().normalize()` converts to an absolute path and simplifies `.` and `..` segments; it **does not** verify the real path or prevent links from escaping root. `PathMatcher` accepts `glob:...` syntax, supporting wildcards such as `*`, `?`, and `{java,kt}` depending on the provider's glob syntax. We intentionally match `file.getFileName()` so the option has a consistent meaning: filtering by *name* at any depth.

**Event-driven traversal.** The visitor does not collect every `Path` into a `List` and filter afterward; when it finds a matching file, it prints immediately. Memory grows mainly with traversal depth and provider state, not with the number of printed results. Output **does not guarantee lexicographical order** because traversal order is decided by the filesystem provider.

**Metadata.** `BasicFileAttributes attrs` is supplied when the visitor encounters a file; `attrs.isRegularFile()` filters out directories and non-regular entries; `attrs.size()` reads size from metadata. If a file is modified during traversal, its actual size and content may change after attributes were read.

**Hidden.** When `includeHidden` is false, `preVisitDirectory` uses `Files.isHidden(dir)` to skip entire hidden directory branches and `visitFile` skips hidden files. Hidden rules differ across operating systems/providers: Unix typically relies on dot-prefixed names, while Windows has a hidden attribute. Thus "hidden" is an environment attribute, not a Unicode/filename rule guessed by the tool. The root directory is traversed even if the root itself is marked hidden; the skip-hidden rule applies to entries beneath root.

**Size and name filtering.** We apply name matching and then check `attrs.size()` within an inclusive range on both ends: `minBytes <= size <= maxBytes`. Zero-byte files are valid if not excluded by the min condition. In this basic CLI, size arguments are decimal integers representing bytes; KB/MiB suffixes are not supported yet.

**Error handling.** If permission is denied for a branch, a filesystem disconnects, or symbolic links form a cycle, the visitor prints a warning to stderr, increments `errors`, and generally continues traversing other parts. Exit code `2` indicates I/O errors occurred, even when some results were printed; `1` indicates invalid arguments, and `0` indicates completion with no recorded errors. Some unchecked errors, process errors, or filesystem provider side effects can terminate the program outside the handled `IOException` branches.

## 5. Creating a Small Fixture for Self-Testing

To avoid depending on the contents of an existing directory, create a standalone Java program **`CreateDemoTree.java`**. It creates a small file tree in the `demo-tree` directory relative to the current working directory.

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public class CreateDemoTree {
    public static void main(String[] args) throws IOException {
        Path root = Path.of("demo-tree");

        Files.createDirectories(root.resolve("logs/nested"));
        Files.createDirectories(root.resolve("docs"));

        Files.writeString(root.resolve("logs/a.log"), "ERROR");
        Files.writeString(root.resolve("logs/c.log"), "INFO\n");
        Files.writeString(root.resolve("logs/nested/b.log"), "WARN");
        Files.writeString(root.resolve("docs/readme.txt"), "Hello");

        System.out.println("Created demo-tree");
    }
}
~~~

The files `a.log` and `c.log` are exactly **5 bytes** with the ASCII/UTF-8 content in the example, `b.log` is 4 bytes, and `readme.txt` is 5 bytes. Run in a **clean working directory with no pre-existing `demo-tree` or other files in the tree** so the counts are exact:

~~~bash
javac TreeFilter.java CreateDemoTree.java
java CreateDemoTree
java TreeFilter demo-tree --glob "*.log" --min-bytes 5 --max-bytes 5 --max-depth 4
~~~

Stdout of `CreateDemoTree`:

~~~text
Created demo-tree
~~~

Stdout of `TreeFilter` consists of **these two lines**, though order may swap because traversal is unsorted:

~~~text
logs/a.log	5
logs/c.log	5
~~~

On Windows, the separator in both paths is `\` instead of `/`. The stderr summary line on a typical filesystem, when the fixture is intact and there are no access errors, is:

~~~text
Visited directories=4, regular files=4, matches=2, errors=0
~~~

Breakdown: the four directories are root, `logs`, `logs/nested`, and `docs`. There are four regular files; only `a.log` and `c.log` simultaneously satisfy glob `*.log` and size range `[5,5]`. `b.log` is excluded for being 4 bytes, and `readme.txt` for not matching the glob. All are at depth at most 4.

### 5.1. Testing Each Filter Individually

**Inspect only logs without size limits:**

~~~bash
java TreeFilter demo-tree --glob "*.log"
~~~

Expected `matches=3`; `a.log`, `b.log`, and `c.log` are all printed (order is not fixed).

**Depth limit:**

~~~bash
java TreeFilter demo-tree --glob "*.log" --max-depth 2
~~~

Expected `matches=2`: excludes `logs/nested/b.log` because it sits at depth 3. Per `walkFileTree` semantics with `maxDepth=2`, a directory at depth 2 is not descended to visit depth-3 files.

**Size limit:**

~~~bash
java TreeFilter demo-tree --glob "*.log" --min-bytes 4 --max-bytes 4
~~~

Expected `matches=1`, leaving only `logs/nested/b.log` (4 bytes).

**Non-existent root path:**

~~~bash
java TreeFilter does-not-exist
~~~

Expected to print `Invalid arguments: Not a directory: ...` with usage on stderr and exit with code `1`. The absolute path portion depends on the machine. To check exit code yourself, use `echo $?` in Bash or `$LASTEXITCODE` in PowerShell.

### 5.2. Notes About the Fixture

`Files.writeString` creates new files or overwrites/truncates existing ones by default. Only run the fixture inside a practice directory you control; if `demo-tree` already exists with extra files, file and directory counts will differ. The demo code intentionally does not auto-delete old data to avoid an unexpected destructive operation.

`TreeFilter` itself only reads metadata. Running it with a source code or real data directory as root does not modify files, though the user still needs permissions to view and traverse those directories.

## 6. Symbolic Links, Cycles, and Root Boundaries

### 6.1. Not Following Symbolic Links by Default

`Files.walkFileTree` without `FileVisitOption.FOLLOW_LINKS` does not descend into directory links. For symlinks to files, attributes are read under the traversal's no-follow policy, so `attrs.isRegularFile()` usually does not treat them as regular files to print.

When enabled:

~~~bash
java TreeFilter demo-tree --glob "*.log" --follow-links
~~~

Java is allowed to traverse through symbolic links. This has two consequences:

1. **Cycles can occur**: `A/link -> A` or indirect links between directories. The visitor can receive `FileSystemLoopException` via `visitFileFailed`, report an error, and continue.
2. **Traversal can physically leave the root tree**: for example `root/external -> /data/shared`. `Path.relativize` still constructs a formal path `external/...` because the walker followed the link from a path under root, even though the physical file actually resides outside root.

Do not treat `toAbsolutePath().normalize()` as a sandbox. If you must guarantee never leaving root when following links, carefully design a policy and check real/canonical paths while accounting for **race conditions** where a symlink is swapped between check and use. A tool traversing untrusted data should generally keep `--follow-links` off and restrict scope using OS permissions.

### 6.2. Hard Links and Result Counts

Hard links are multiple names in a filesystem pointing to the same file identity. The current tool lists **paths**, and does not deduplicate by file identity. Therefore, two hard links matching the filter are printed twice; this matches the task of finding paths.

If the goal is counting **unique physical files**, a different policy is needed: rely on `BasicFileAttributes.fileKey()` where the provider supports it, understand key and filesystem limitations, and track seen identities. This increases memory usage. Do not use path names as proof that content is unique.

## 7. Why Not Use `File.listFiles()` and Manual Recursion?

`java.io.File.listFiles()` remains useful for simple cases, but its return value can be `null` on directory read errors, and you must manually manage stack/depth, symbolic links, metadata, and error handling when writing recursive traversal. `Files.walkFileTree` provides callbacks built specifically for those cases.

Commonly seen code:

~~~java
for (File child : directory.listFiles()) {
    visit(child);
}
~~~

This is an **incomplete/faulty illustration**, not a standalone runnable example: `listFiles()` can return `null` and cause `NullPointerException`; deep recursion can cause `StackOverflowError`; and following symbolic links without control can hit cycles. Using a visitor expresses intent more clearly, though it does not exempt you from diagnosing I/O errors.

A more concise Java NIO.2 option when you only need a stream of results:

~~~java
try (var paths = Files.walk(root)) {
    paths.filter(Files::isRegularFile)
         .forEach(System.out::println);
}
~~~

This is an **illustrative snippet** inside a method that has `Path root` and handles `IOException`. `Files.walk` creates a closeable stream so `try-with-resources` is required; if iteration encounters an I/O error, it may be wrapped in `UncheckedIOException`. In addition, skipping an entire hidden subtree or collecting errors and continuing other branches is not as convenient as with a visitor.

## 8. Performance and Limits on Large File Trees

### 8.1. Memory and Complexity

If there are `N` entries in the traversed portion of the tree, one traversal pass generally takes `O(N)` time **in the number of visited entries**; however, real latency is dominated by metadata I/O, directory enumeration, network mounts, filesystem behavior, and permissions. Checking glob/size per file is usually far cheaper than reading full file contents.

The program prints results immediately, so it **does not hold all `N` paths in a collection**. Traversal state depends on tree depth and provider implementation, while counters use only a few `long` variables. If sorted results are required, you usually have to store them or run an external sort, which changes the memory/I/O trade-off.

### 8.2. How to Improve When Requirements Grow

- **Early directory pruning:** if you only want to traverse `src` branches or skip `node_modules`/`build`, add a rule in `preVisitDirectory` returning `SKIP_SUBTREE` before descending; more efficient than visiting every file and discarding it.
- **Multi-condition filtering:** extend `Config` and separate clear predicates; for instance excluding other extensions, timestamps via `attrs.lastModifiedTime()`, or files above a threshold.
- **Content searching:** after a file passes metadata filtering, stream chunk by chunk to search for patterns. Define encoding, byte/size limits, and whether binary files are supported; do not use `Files.readAllBytes` on arbitrary large files.
- **Machine-readable output:** replace raw TSV with JSON Lines with proper escaping or write to a database, especially when names contain special characters.
- **Deterministic sorting:** for lexicographical output, use a memory-bounded sorting mechanism, or collect only when the result set is small. Never assume traversal yields sorted paths.
- **Early termination:** add a result-limit option and return `TERMINATE` when reached; make clear the output is partial rather than a full tree scan.
- **Parallelism:** do not assume multiple threads are faster, especially on spinning disks or network shares due to metadata I/O and contention. When parallelism is truly needed, control queues, worker count, errors, ordering, and resource quotas.

### 8.3. Risks When the Filesystem Changes During Traversal

Directory traversal does not create a transactional snapshot. Things that can happen:

- A file is deleted/renamed after its parent directory was listed.
- Size metadata changes while the program prints output.
- Access permissions are revoked, causing `visitFileFailed` mid-scan.
- A symbolic link is modified, changing results within the same run.

Therefore, describe the output as **paths observed during a single scan**, rather than claiming it proves the state of the entire filesystem at a single point in time. For security, backup, or deletion tasks, design dedicated verification and consistency mechanisms instead of relying solely on a single `walkFileTree` pass.

## 9. Deliberate Testing

Beyond the basic fixture, test the following groups:

| Case | Expected Behavior |
| --- | --- |
| Empty root directory | No result lines; statistics count root as one directory |
| `--min-bytes 0 --max-bytes 0` | Accepts only empty regular files if names match |
| `--glob "*.TXT"` | Depends on filesystem/provider case-sensitivity rules; do not assume `.txt` matches everywhere |
| `--max-depth 1` | Does not enter files inside deeper subdirectories |
| Hidden subdirectory | Skips entire subtree without `--include-hidden` per `Files.isHidden` |
| Symlink to directory | Not followed by default; when follow is enabled, target can be traversed |
| Circular symlink | Reports error/warning and finishes finitely without infinite recursion |
| Unreadable directory | Records error when provider reports it, attempts to continue other branches, non-zero exit code |
| Root is not a directory | Reports invalid arguments, does not traverse |
| `--min-bytes` greater than `--max-bytes` | Reports argument error before traversal |
| Malformed glob syntax | `IllegalArgumentException`/pattern error; displays usage |
| Filenames with Unicode/spaces | Handled via `Path`, never splitting paths on spaces |
| File deleted mid-scan | Records corresponding error if detected by provider; does not claim snapshot |

Testing symlink/hidden behavior requires platform-specific fixtures and symlink creation permissions; Windows machines may require specific privileges or configuration modes. Do not run permission or circular-link tests on a shared working tree unless you control the consequences.

If you need to verify a filter function independently, extract the predicate taking `Path` and `BasicFileAttributes` into a pure method for unit testing. Integration tests should use temporary directories (`Files.createTempDirectory`) and `try/finally` to clean up **only the fixture created by the test**, avoiding deleting user-supplied paths. For CLI tools, verify **stdout, stderr, and exit code**, because a scan can produce valid results while simultaneously hitting errors in another branch.

## 10. Common Mistakes When Submitting Practical Exercises

**Mistake 1 — Treating every entry as a file.** In `visitFile`, when max depth is reached, the visitor can be invoked with a directory that is not descended. Therefore check `attrs.isRegularFile()` instead of assuming every entry in that callback is a regular file.

**Mistake 2 — Using `Files.walk` and forgetting to close the stream.** The stream holds open resources to enumerate directories; wrap it in `try-with-resources` if you choose that API.

**Mistake 3 — Filtering paths at the wrong level.** `PathMatcher.matches(file.getFileName())` only filters filenames. Path patterns like `src/**/*.java` need matching against the relative path and verifying glob semantics per provider.

**Mistake 4 — Confusing `Files.isHidden` with dot-prefixed names.** Operating systems have distinct policies, especially on Windows; do not force Unix assumptions onto other environments.

**Mistake 5 — Following symbolic links by default.** Doing so can expand scanning outside root and create cycles. Keep the option explicit, test loops, and handle `FileSystemLoopException`.

**Mistake 6 — Stopping on a non-matching file.** Non-matching files should return `CONTINUE`; only use `SKIP_SUBTREE` when intentionally excluding **an entire subdirectory**.

**Mistake 7 — Collecting all files into RAM before filtering.** With millions of entries, a huge list causes memory pressure. Prefer streaming callbacks and only accumulate if sorting or aggregating is required.

**Mistake 8 — Assuming counts are a consistent snapshot.** File trees can change during traversal; cleanup or destructive actions require thorough extra checks.

**Mistake 9 — Printing warnings to the same stdout as data.** Downstream parsing pipelines become hard to handle; reserve stdout for results and stderr for warnings/statistics.

**Mistake 10 — Returning exit code 0 after access errors occurred.** Exit codes matter to scripts; the program above returns 2 when one or more I/O errors were recorded even if matching results were printed.

## 11. Guided Extension Exercises

1. **Add modified-date filtering:** accept `--modified-after 2026-01-01`, parse with `LocalDate` in a user-defined timezone, and compare against `attrs.lastModifiedTime()`. Document whether the boundary is UTC or local time.
2. **Exclude unnecessary directories:** add `--exclude-dir target` so `preVisitDirectory` skips any `target` branch at any depth; decide whether matching uses name or relative path.
3. **Safe CSV export:** include a header, escape quotes, newlines, and delimiters per RFC 4180; pay attention to Windows path separators and UTF-8 encoding.
4. **Find largest files:** maintain the top K using a priority queue of size K instead of collecting all N files; requires only O(K) memory for the result set.
5. **Filter by content:** for files under an allowed size threshold, use `BufferedReader` and an explicit `Charset` to find lines containing a keyword; distinguish text from binary and cap file size.
6. **Write integration tests:** create temporary files and directories, run `TreeFilter` under that root, verify result count; simulate/set platform-specific errors if needed without depending on traversal order.

## 12. Self-Assessment Questions

**Question 1.** Why is `Files.walkFileTree` better suited than `File.listFiles()` recursion for a tool that can skip subtrees?

**Answer:** The visitor provides `preVisitDirectory` and `SKIP_SUBTREE`, explicit error hooks, and depth/link options, allowing traversal control without hand-writing recursion.

**Question 2.** Does running `java TreeFilter root --glob "*.java"` match `root/src/Main.java`?

**Answer:** Yes, if that entry is a valid regular file and not excluded by other filters; the matcher applies to the name `Main.java`, independent of the `src` folder.

**Question 3.** Can `root.toAbsolutePath().normalize()` be considered a safe isolation layer preventing symlinks from escaping root?

**Answer:** No. That only normalizes **path syntax**, and does not constrain the physical target of a symbolic link. Keep `--follow-links` disabled when unneeded and use safer policies for untrusted trees.

**Question 4.** Does a 5-byte file satisfy `--min-bytes 5 --max-bytes 5`?

**Answer:** Yes. The program's range is inclusive on both ends.

**Question 5.** A program scans 100 directories, finds 50 matches, yet one branch fails to read. What should the exit code express?

**Answer:** It may keep the 50 observed results, but it must report the error and return a non-zero code so calling scripts know the scan was **incomplete**. In the example, the exit code is `2`.

**Question 6.** If output must always be sorted by path without holding millions of paths in RAM, what is a reasonable approach?

**Answer:** Emit results in a format suitable for external sort (or an appropriate database/streaming sorted pipeline); account for the extra I/O cost, and never assume filesystem iterators have a fixed order.

## 13. Official References

- [Java 17 Files.walkFileTree](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#walkFileTree(java.nio.file.Path,java.util.Set,int,java.nio.file.FileVisitor)): traversal protocol, `maxDepth`, links, and visitor.
- [Java 17 SimpleFileVisitor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/SimpleFileVisitor.html): callbacks and default behavior.
- [Java 17 FileVisitResult](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileVisitResult.html): `CONTINUE`, `SKIP_SUBTREE`, `SKIP_SIBLINGS`, `TERMINATE`.
- [Java 17 FileSystem.getPathMatcher](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileSystem.html#getPathMatcher(java.lang.String)): glob/regex and provider-dependent scope.
- [Java 17 BasicFileAttributes](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/BasicFileAttributes.html): file types, size, and timestamps.

A reliable file-filtering tool must clearly define **what entries are traversed**, **at what level filter rules apply**, **behavior on symbolic links/errors**, and **what results mean when the tree is changing**. Built on `Files.walkFileTree` and clear metadata filters, you can grow a simple exercise into a file-scanning utility usable in practice.