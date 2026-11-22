# Practice: Building a Directory Tree Traversal and File Filter Tool with Java NIO.2

## 1. Problem Statement and Goals

You need a command-line tool that traverses a root directory and its subdirectories, printing only **regular files** that match filter criteria. The tool should be useful on large directory trees, easy to verify, and tolerant of localized access errors without losing all results found so far.

In this exercise, we will write `TreeFilter` in Java 17+ with the following features:

- Accepts a **root directory** from command-line arguments.
- Traverses recursively using `Files.walkFileTree` and `SimpleFileVisitor`.
- Filters by **filename glob**, minimum/maximum size (bytes), **depth limit**, and an option to include/exclude hidden items.
- **Does not follow symbolic links by default**; follows links only when the user passes `--follow-links`.
- Prints relative paths and byte sizes to stdout, and statistics and warnings to stderr.
- Continues after branch access errors when possible, counts errors, and returns an appropriate exit code.
- Creates small test data to verify output, then discusses practical limits with large files and deep trees.

This tool **only reads file metadata/structure during traversal**; it never deletes, modifies, moves, or renames files. The program inspects metadata (file type, size, hidden attribute) and filenames; it **does not open/read full file contents** to search for keywords. Filtering by content requires adding a separate streaming step.

## 2. Designing the CLI Interface

Proposed syntax:

~~~text
java TreeFilter <root> [options]

Options:
  --glob <pattern>     Glob applied to FILENAME (default: *)
  --min-bytes <number> Minimum size in bytes (default: 0)
  --max-bytes <number> Maximum size in bytes (default: Long.MAX_VALUE)
  --max-depth <number> Traversal depth limit, integer >= 1
  --include-hidden     Include files/directories marked hidden by the OS
  --follow-links       Allow following symbolic links; disabled by default
~~~

Options are **ANDed** together. Example command:

~~~bash
java TreeFilter project --glob "*.java" --min-bytes 100 --max-bytes 200000 --max-depth 10
~~~

The program finds Java files matching `*.java`, from 100 to 200,000 bytes, within the tree rooted at `project` up to depth 10. The glob pattern is applied to **`file.getFileName()`** (only the final name component). Thus `*.java` can match `src/App.java`, whereas `src/*.java` will **not** match the filename `App.java`; filtering by relative path requires changing how `PathMatcher` is applied.

**Depth convention:** the root is at depth 0, direct children are at depth 1, files in subdirectories are at depth 2, and so on. `--max-depth 1` visits only direct entries under the root. Directories at the depth limit are not descended further. This is `walkFileTree`'s traversal limit, not the number of directory levels **printed**.

**Output format:** each result line contains `relative_path<TAB>byte_size`, formatted via the OS `Path.toString()`. The path separator may be `/` on Unix or `\` on Windows. Simple TSV output is handy for learning and quick scripting; filenames containing TABs or newlines need escaping or JSON formatting when building machine-to-machine integrations.

## 3. Choosing a Tree Traversal API

Java NIO.2 in `java.nio.file` supports several ways to traverse:

| API | Scope | Key Characteristics |
| --- | --- | --- |
| `Files.list(dir)` | One level | Returns `Stream<Path>`; stream must be closed after use |
| `Files.walk(root, depth)` | Multi-level | Lazy `Stream<Path>`; requires `try-with-resources` to close |
| `Files.find(root, depth, matcher)` | Multi-level | Predicate receives `Path` and `BasicFileAttributes`; stream must be closed |
| `Files.walkFileTree(root, visitor)` | Multi-level | Event-based callbacks; controls `SKIP_SUBTREE`, `TERMINATE`, access errors, and links |

`Files.walkFileTree` fits well when you want explicit traversal control without holding the entire file list in RAM. `SimpleFileVisitor<Path>` provides default methods for four main hooks:

1. `preVisitDirectory(dir, attrs)`: before entering a directory; can return `SKIP_SUBTREE` to skip the entire branch.
2. `visitFile(file, attrs)`: when encountering an entry visited as a file; `attrs.isRegularFile()` indicates whether it is a regular file.
3. `visitFileFailed(file, exception)`: failed attribute lookup or inability to visit an entry, including cyclic symbolic links.
4. `postVisitDirectory(dir, exception)`: after processing a directory; `exception` is non-null if directory traversal encountered an error.

Common `FileVisitResult` values are `CONTINUE`, `SKIP_SUBTREE`, `SKIP_SIBLINGS`, and `TERMINATE`. Here we use `CONTINUE` and `SKIP_SUBTREE`; unless aborting the whole walk, never return `TERMINATE` simply because one file fails a filter.

## 4. Complete `TreeFilter.java` Implementation

Save the following code verbatim into **`TreeFilter.java`**. The program uses standard JDK APIs with no Maven, Gradle, or third-party libraries.

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
                            // Allow visiting the root; hidden subdirectories
                            // are skipped along with their entire subtree.
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

        // Glob matches on the filename only, not the full relative path.
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

Run in any directory containing Java source to see real output; file counts and sizes depend on that directory. Quote the glob pattern so Unix shells do not expand `*.java` into a file list before Java receives the arguments.

### 4.1. Explaining the Key Mechanics

**`Path` and `PathMatcher`.** `Path.of(args[0])` creates a path object using the default filesystem provider. `toAbsolutePath().normalize()` converts to an absolute path and simplifies `.` and `..` segments; it **does not** verify real paths or prevent links from escaping the root. `PathMatcher` accepts `glob:...` syntax, supporting wildcards like `*`, `?`, and `{java,kt}` depending on the provider's glob implementation. We deliberately match `file.getFileName()` so the option has consistent semantics: filtering by *name* at any depth.

**Event-driven traversal.** The visitor does not collect every `Path` into a `List` and filter afterward; when it finds a matching file, it prints immediately. Memory grows primarily with traversal depth and provider state, not with the number of printed results. Output **does not guarantee lexicographical order** because traversal order is determined by the filesystem provider.

**Metadata.** `BasicFileAttributes attrs` is supplied when the visitor meets a file; `attrs.isRegularFile()` excludes directories and non-regular entries; `attrs.size()` reads size from metadata. If a file is modified during traversal, actual size and content can change after the attributes are read.

**Hidden entries.** When `includeHidden` is false, `preVisitDirectory` uses `Files.isHidden(dir)` to skip the entire hidden directory branch and `visitFile` skips hidden files. Hidden rules vary across OSes/providers: Unix typically checks for a leading dot, whereas Windows uses a hidden attribute. Thus "hidden" is an environment attribute, not a Unicode/filename rule guessed by the tool. The root directory itself is visited even if the root is marked hidden; hidden filtering applies to entries beneath the root.

**Size and name filtering.** We apply name matching first and then check `attrs.size()` against an inclusive range: `minBytes <= size <= maxBytes`. Zero-byte files are valid unless excluded by a minimum bound. In this basic CLI, size arguments are decimal integers representing bytes without KB/MiB suffixes.

**Error handling.** If permission to traverse a branch is denied, a filesystem disconnects, or a symbolic link forms a cycle, the visitor prints a warning to stderr, increments `errors`, and usually continues traversing other branches. Exit code `2` signals I/O errors occurred, even when some results were printed; `1` signals invalid arguments; `0` signals completion with no recorded errors. Some unchecked errors, process errors, or filesystem provider side effects can terminate the program outside the handled `IOException` paths.

## 5. Creating a Small Fixture for Self-Testing

To avoid depending on existing directory contents, create a standalone Java program **`CreateDemoTree.java`**. It creates a small file tree in `demo-tree` relative to the current working directory.

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

`a.log` and `c.log` are exactly **5 bytes** with ASCII/UTF-8 content in the example, `b.log` is 4 bytes, and `readme.txt` is 5 bytes. Run inside a **clean working directory with no pre-existing `demo-tree` or extra files** so the statistics match exactly:

~~~bash
javac TreeFilter.java CreateDemoTree.java
java CreateDemoTree
java TreeFilter demo-tree --glob "*.log" --min-bytes 5 --max-bytes 5 --max-depth 4
~~~

Stdout of `CreateDemoTree`:

~~~text
Created demo-tree
~~~

Stdout of `TreeFilter` consists of the **following two lines**, though order may swap because traversal is unsorted:

~~~text
logs/a.log	5
logs/c.log	5
~~~

On Windows, the path separator in both paths is `\` instead of `/`. The stderr summary line on a typical filesystem, when the fixture is complete and error-free, is:

~~~text
Visited directories=4, regular files=4, matches=2, errors=0
~~~

Breakdown: the four directories are the root, `logs`, `logs/nested`, and `docs`. There are four regular files; only `a.log` and `c.log` simultaneously satisfy glob `*.log` and size range `[5,5]`. `b.log` is excluded for being 4 bytes, and `readme.txt` for not matching the glob. All lie within depth 4.

### 5.1. Testing Individual Filters

**Logs only with no size limit:**

~~~bash
java TreeFilter demo-tree --glob "*.log"
~~~

Expected `matches=3`; `a.log`, `b.log`, and `c.log` are all printed (order unspecified).

**Depth limit:**

~~~bash
java TreeFilter demo-tree --glob "*.log" --max-depth 2
~~~

Expected `matches=2`: excludes `logs/nested/b.log` because it sits at depth 3. Under `walkFileTree` semantics with `maxDepth=2`, directories at depth 2 are not descended to visit files at depth 3.

**Size limit:**

~~~bash
java TreeFilter demo-tree --glob "*.log" --min-bytes 4 --max-bytes 4
~~~

Expected `matches=1`, leaving only `logs/nested/b.log` (4 bytes).

**Non-existent root path:**

~~~bash
java TreeFilter does-not-exist
~~~

Expected to print `Invalid arguments: Not a directory: ...` with usage on stderr and exit with code `1`. The absolute path portion varies by machine. To check exit codes yourself, use `echo $?` in Bash or `$LASTEXITCODE` in PowerShell.

### 5.2. Notes on the Fixture

`Files.writeString` creates or overwrites/truncates existing files by default. Run the fixture only in a practice directory you control; if `demo-tree` already exists with extra files, file and directory counts will differ. The demo code intentionally does not auto-delete old data to avoid unexpected destructive actions.

`TreeFilter` itself only reads metadata. Running it on a source-code or real data directory modifies no files, though the user still needs read/traverse permissions on those directories.

## 6. Symbolic Links, Cycles, and Root Boundaries

### 6.1. Not Following Symbolic Links by Default

`Files.walkFileTree` without `FileVisitOption.FOLLOW_LINKS` does not descend into directory links. For a symlink to a file, attributes are read under the non-following traversal policy, so `attrs.isRegularFile()` usually does not classify it as a regular file to print.

When enabled:

~~~bash
java TreeFilter demo-tree --glob "*.log" --follow-links
~~~

Java is allowed to traverse through symbolic links. This has two consequences:

1. **Cycles can occur**: `A/link -> A` or indirect links between directories. The visitor can receive `FileSystemLoopException` via `visitFileFailed`, report the error, and continue.
2. **Traversal can physically leave the root tree**: e.g., `root/external -> /data/shared`. `Path.relativize` still constructs a formal path `external/...` because the walker followed the link from under the root, even though the physical target resides outside the root.

You cannot treat `toAbsolutePath().normalize()` as a sandbox. If guaranteeing traversal stays inside the root when following links is required, carefully design policies and verify real/canonical paths, while accounting for **race conditions** if symlinks change between check and use. A tool scanning untrusted data should generally keep `--follow-links` disabled and restrict scope via OS permissions.

### 6.2. Hard Links and Result Counts

Hard links are multiple names in the filesystem pointing to the same file identity. The current tool lists **paths**, without deduplicating by file identity. Thus two hard links matching the filter are printed twice; this matches the task of finding paths.

If the goal is counting **unique physical files**, a different policy is needed: rely on `BasicFileAttributes.fileKey()` when supported by the provider, recognize key/filesystem limitations, and track seen identities. This increases memory usage. Never use path names as proof that file content is unique.

## 7. Why Not Use `File.listFiles()` and Manual Recursion?

`java.io.File.listFiles()` remains handy for simple cases, but its return value can be `null` on directory read errors, and you must manually manage stack/depth, symbolic links, metadata, and error handling when writing recursive traversal. `Files.walkFileTree` provides dedicated callbacks for those scenarios.

Commonly seen snippet:

~~~java
for (File child : directory.listFiles()) {
    visit(child);
}
~~~

This is a **flawed/incomplete illustration**, not a standalone runnable example: `listFiles()` can return `null` and trigger `NullPointerException`; deep recursion can cause `StackOverflowError`; following symbolic links without guards can enter infinite loops. Using a visitor expresses intent more clearly, though it still does not absolve you from diagnosing I/O errors.

A more concise Java NIO.2 option when you only need a stream of results:

~~~java
try (var paths = Files.walk(root)) {
    paths.filter(Files::isRegularFile)
         .forEach(System.out::println);
}
~~~

This is an **illustrative snippet** inside a method that has `Path root` and handles `IOException`. `Files.walk` returns a closeable stream requiring `try-with-resources`; if iteration hits an I/O error, it may be wrapped in `UncheckedIOException`. In addition, skipping entire hidden subtrees or recording errors while continuing other branches is less convenient than with a visitor.

## 8. Performance and Limits on Large File Trees

### 8.1. Memory and Complexity

If there are `N` entries in the traversed subtree, a walk generally takes roughly `O(N)` time **in visited entries**; actual latency is dominated by metadata I/O, directory enumeration, network mounts, filesystem behavior, and permissions. Checking globs/sizes per file is usually far cheaper than reading full file contents.

The program prints matches immediately, so it **does not hold all `N` paths in a collection**. Traversal state depends on tree depth and provider implementation, while counters use just a few `long` variables. If sorted output is required, you typically must buffer results or external-sort, changing the memory/I/O trade-off.

### 8.2. How to Improve as Requirements Grow

- **Early directory pruning:** if you only want `src` branches or want to skip `node_modules`/`build`, add rules in `preVisitDirectory` returning `SKIP_SUBTREE` before descending; far more efficient than visiting every file and discarding it.
- **Multi-condition filtering:** extend `Config` and separate clear predicates; e.g., excluding extensions, filtering timestamps via `attrs.lastModifiedTime()`, or skipping files above a threshold.
- **Content searching:** once a file passes metadata filters, stream chunks to search for patterns. Define encoding, byte/size limits, and whether binary files are supported; never call `Files.readAllBytes` on arbitrary large files.
- **Machine-readable output:** replace raw TSV with properly escaped JSON Lines or write to a database, especially when names contain special characters.
- **Deterministic sorting:** for lexicographical output, use a RAM-bounded sort, or collect into memory only when the result set is known to be small. Never assume filesystem traversal returns sorted paths.
- **Early cancellation:** add a max-results option and return `TERMINATE` once reached; make clear the output is partial rather than a full tree scan.
- **Parallelism:** never assume multiple threads are faster, especially on spinning disks or network shares where metadata I/O and contention dominate. When parallelism is genuinely needed, control queues, worker counts, errors, ordering, and resource quotas.

### 8.3. Risks When the Filesystem Changes During Traversal

Directory traversal does not create a transactional snapshot. Things that can happen:

- A file is deleted/renamed after its parent directory was listed.
- Size metadata changes while the program prints output.
- Permissions are revoked mid-scan, triggering `visitFileFailed`.
- Symbolic links are altered during the same run, changing results.

Therefore, describe the output as **paths observed during a single scan**, rather than claiming to prove the entire filesystem state at a single instant. For security, backup, or deletion tasks, design dedicated checks and consistency guarantees instead of relying solely on a `walkFileTree` pass.

## 9. Deliberate Testing

Beyond the basic fixture, test the following groups:

| Case | Expected Behavior |
| --- | --- |
| Empty root directory | No result lines, root counted as one directory |
| `--min-bytes 0 --max-bytes 0` | Accepts only empty regular files whose name matches |
| `--glob "*.TXT"` | Depends on filesystem/provider case-sensitivity rules; do not assume `.txt` matches everywhere |
| `--max-depth 1` | Does not visit files inside deeper subdirectories |
| Hidden subdirectory | Skips entire subtree without `--include-hidden` per `Files.isHidden` |
| Symlink to directory | Skipped by default; when follow is enabled, traverses target |
| Cyclic symlink | Reports error/warning and terminates finitely, no infinite recursion |
| Unreadable directory | Records error when reported by provider, attempts to continue other branches, non-zero exit code |
| Root is not a directory | Invalid-argument message, no traversal |
| `--min-bytes` greater than `--max-bytes` | Argument error before traversal |
| Malformed glob syntax | `IllegalArgumentException`/pattern error; prints usage |
| Filenames with Unicode/spaces | Handled via `Path`, never split paths on spaces |
| File deleted mid-scan | Records error if detected by provider; no snapshot claim |

Testing symbolic link/hidden behavior requires platform-specific fixtures and symlink creation privileges; Windows machines may require specific privileges or configuration modes. Do not run permission or cyclic-link tests on shared working trees without controlling side effects.

To verify filtering logic independently, extract a pure predicate taking `Path` and `BasicFileAttributes` for unit testing. Integration tests should use temporary directories (`Files.createTempDirectory`) and `try/finally` to clean up **only test-created fixtures**, avoiding deleting user-supplied paths. For CLI tools, assert **stdout, stderr, and exit code**, because a scan can return valid matches while simultaneously hitting errors on another branch.

## 10. Common Mistakes When Submitting Exercises

**Mistake 1 — assuming every entry is a file.** In `visitFile`, when max depth is reached, the visitor can be invoked on a directory that was not descended into. Always check `attrs.isRegularFile()` rather than assuming every callback target is a regular file.

**Mistake 2 — using `Files.walk` and forgetting to close the stream.** The stream holds open directory resources; wrap it in `try-with-resources` if you choose that API.

**Mistake 3 — filtering paths at the wrong level.** `PathMatcher.matches(file.getFileName())` filters filenames only. Patterns like `src/**/*.java` must match against relative paths and be verified for provider-specific glob semantics.

**Mistake 4 — confusing `Files.isHidden` with dot-prefixed names.** Operating systems have their own policies, especially on Windows; do not force Unix assumptions onto other environments.

**Mistake 5 — following symbolic links by default.** This can expand the scan outside the root and introduce cycles. Keep it opt-in, test cycles, and handle `FileSystemLoopException`.

**Mistake 6 — stopping on a non-matching file.** Non-matching files should return `CONTINUE`; use `SKIP_SUBTREE` only when intentionally skipping **an entire subdirectory**.

**Mistake 7 — loading all files into RAM before filtering.** With millions of entries, a huge list causes memory pressure. Prefer streaming callbacks and accumulate only when sorting or aggregating is required.

**Mistake 8 — treating output metrics as a consistent snapshot.** The file tree can change during traversal; cleanup or destructive actions demand extra verification.

**Mistake 9 — printing warnings to stdout alongside data.** Parsing pipelines will break; reserve stdout for results and stderr for warnings/statistics.

**Mistake 10 — returning exit code 0 despite access errors.** Exit codes matter to scripts; the program above returns 2 whenever one or more I/O errors were recorded even if matches were printed.

## 11. Guided Extension Exercises

1. **Add modified-date filtering:** accept `--modified-after 2026-01-01`, parse with `LocalDate` in a user-specified timezone, and compare against `attrs.lastModifiedTime()`. Document whether boundaries are UTC or local time.
2. **Exclude unnecessary directories:** add `--exclude-dir target` so `preVisitDirectory` skips `target` subtrees at any depth; specify whether matching uses directory name or relative path.
3. **Safe CSV export:** include a header and escape quotes, newlines, and delimiters per RFC 4180; pay attention to Windows path separators and UTF-8 encoding.
4. **Find largest files:** maintain the top K using a bounded priority queue of size K instead of collecting all N files; uses only O(K) memory for the result set.
5. **Filter by content:** for files under a size threshold, use `BufferedReader` and an explicit `Charset` to find lines containing keywords; distinguish text from binary and cap sizes.
6. **Write integration tests:** create temporary files and directories, run `TreeFilter` under that root, and assert match counts without relying on traversal order; simulate/set up platform errors if needed.

## 12. Self-Assessment Questions

**Question 1.** Why is `Files.walkFileTree` better suited than manual `File.listFiles()` recursion for a tool that can prune subtrees?

**Answer:** A visitor provides `preVisitDirectory` and `SKIP_SUBTREE`, explicit error callbacks, and depth/link options, giving traversal control without hand-rolling recursion.

**Question 2.** Does running `java TreeFilter root --glob "*.java"` match `root/src/Main.java`?

**Answer:** Yes, if the entry is a valid regular file and not excluded by other filters; the matcher applies to the filename `Main.java`, independent of the `src` folder.

**Question 3.** Can `root.toAbsolutePath().normalize()` be called a security sandbox preventing symlinks from escaping the root?

**Answer:** No. That only normalizes **path syntax** and does not constrain the physical target of a symbolic link. Keep `--follow-links` off when unneeded and apply stronger policies for untrusted trees.

**Question 4.** Does a 5-byte file satisfy `--min-bytes 5 --max-bytes 5`?

**Answer:** Yes. The program's size range is inclusive at both ends.

**Question 5.** The program scans 100 directories, finds 50 matches, yet one branch suffers a read error. What should the exit code convey?

**Answer:** It may keep the 50 observed matches, but must report the error and return a non-zero exit code so calling scripts know the scan was **incomplete**. In the example, the exit code is `2`.

**Question 6.** If output must always be sorted by path without holding millions of paths in RAM, what approach makes sense?

**Answer:** Write results in a format suitable for external sort (or a database/streaming sorted pipeline); account for the extra I/O cost and never assume filesystem iterators have a fixed order.

## 13. Official Documentation

- [Java 17 Files.walkFileTree](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#walkFileTree(java.nio.file.Path,java.util.Set,int,java.nio.file.FileVisitor)): traversal contract, `maxDepth`, links, and visitor.
- [Java 17 SimpleFileVisitor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/SimpleFileVisitor.html): callbacks and default behaviors.
- [Java 17 FileVisitResult](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileVisitResult.html): `CONTINUE`, `SKIP_SUBTREE`, `SKIP_SIBLINGS`, `TERMINATE`.
- [Java 17 FileSystem.getPathMatcher](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileSystem.html#getPathMatcher(java.lang.String)): glob/regex and provider-dependent scope.
- [Java 17 BasicFileAttributes](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/BasicFileAttributes.html): file types, size, and timestamps.

A reliable file-filtering tool must clearly define **what entries are visited**, **at what level filter rules apply**, **behavior on symbolic links and errors**, and **what results mean while a tree is changing**. Building on `Files.walkFileTree` with explicit metadata filters lets you scale from a simple exercise into a practical file-scanning utility.
