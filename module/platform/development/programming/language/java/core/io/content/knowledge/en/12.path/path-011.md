# `PathMatcher` with glob and regex

## Lesson objectives

In Java NIO.2, `java.nio.file.Path` describes a path, whereas `java.nio.file.PathMatcher` answers the question **"does this path match the defined pattern or not?"**. `PathMatcher` supports two major syntax families through `FileSystem.getPathMatcher(...)`: **`glob:`** (readable for selecting filenames) and **`regex:`** (more powerful when regular expressions are needed).

After this lesson, you will be able to:

- Create a `PathMatcher` using `FileSystems.getDefault().getPathMatcher("glob:...")` and `"regex:..."`.
- Understand that `matches(Path)` matches **the `Path` object passed in**, without searching for files on disk.
- Distinguish `path`, `path.getFileName()`, `root.relativize(path)`, and `path.toAbsolutePath()` when filtering names versus full paths.
- Use glob symbols `*`, `**`, `?`, `[]`, `{}` and appropriate escaping; distinguish glob from Java regular expressions.
- Understand why a pattern can yield different results across filesystems/OSes due to separators, case sensitivity, and provider rules.
- Apply a matcher to filter `Files.list` or `Files.walk`, manage streams with try-with-resources, and handle errors and security.
- Write and run Java 17+ examples with deterministic output.

## 1. What is `PathMatcher`, and what does it NOT do?

`PathMatcher` is a **functional interface** in `java.nio.file`:

```java
public interface PathMatcher {
    boolean matches(Path path);
}
```

This is an **illustrative signature**, not a standalone Java file to redeclare in your project.

`matches(path)` decides whether the pattern matches the passed `Path`. It does **not**:

- Open or create files or directories.
- Automatically call `Files.list()` or traverse directory trees.
- Verify that the file actually exists or is readable.
- Check MIME type or content format.
- Guarantee that the name/path is safe to open, delete, or execute.
- Automatically switch to matching `getFileName()` if you pass an entire path.

Logical diagram:

```text
Rule string                       Candidate path
"glob:*.java"                     Path.of("src", "App.java")
       │                                   │
       ▼                                   ▼
FileSystem.getPathMatcher(...)     Path chosen by caller
       │                                   │
       └───────── matcher.matches(path) ───┘
                          │
                     true / false
```

The decisive factor is **which `Path` is passed to the matcher**. In the example above, the pattern `glob:*.java` is designed to match a single name component, whereas `Path.of("src", "App.java")` has multiple components; the usual result is `false`. If you want to filter by the final name, pass `path.getFileName()` instead of the whole `path`.

## 2. Creating a matcher via `FileSystem`

Core API:

```java
FileSystem fs = FileSystems.getDefault();

PathMatcher javaNames = fs.getPathMatcher("glob:*.java");
PathMatcher numberedReports =
    fs.getPathMatcher("regex:report-\\d{4}\\.csv");
```

This is an **illustrative snippet**, requiring imports for `java.nio.file.FileSystem`, `FileSystems`, and `PathMatcher`. Note: in **Java source**, `\\d` and `\\.` use two backslashes in the literal to produce the actual regex `\d` and `\.`. `PathMatcher` is not directly a `java.util.regex.Pattern`; the matcher is created by the filesystem provider according to the specified syntax.

String syntax:

```text
syntax:pattern
```

- `syntax`: with the default provider, options are **`glob`** or **`regex`**.
- `pattern`: matching rule interpreted according to the chosen syntax.
- `getPathMatcher(...)` belongs to **a `FileSystem`**, because paths and semantics can depend on the provider.
- An invalid pattern may throw `PatternSyntaxException` (unchecked); an unsupported syntax for the provider is also an error to handle per contract.

`FileSystems.getDefault()` is the JVM's default filesystem. For specialized filesystems such as ZipFS or third-party providers, create the matcher from `path.getFileSystem()` itself or the filesystem being processed rather than assuming the default filesystem.

### A matcher can be reused

```java
PathMatcher matcher =
    FileSystems.getDefault().getPathMatcher("glob:*.txt");

boolean ok1 = matcher.matches(Path.of("note.txt"));
boolean ok2 = matcher.matches(Path.of("photo.png"));
```

This is an **illustrative snippet** with `import java.nio.file.*`. `ok1` is `true`; `ok2` is `false` for ASCII names on a typical default filesystem. Create a matcher **once** for a rule and reuse it inside loops instead of compiling the pattern for every entry.

## 3. `glob:`: filename-friendly syntax

Glob differs from regex. Common glob rules in Java's default filesystem:

| Glob | Meaning | Example |
|---|---|---|
| `*.java` | Any name part ending in `.java`; `*` does not cross directory separators | `Main.java` |
| `file?.txt` | One non-separator character at the `?` position | `file1.txt`, not `file12.txt` |
| `img[0-9].png` | One character in the character range listed in `[]` | `img7.png` |
| `report[abc].csv` | One of `a`, `b`, `c` | `reporta.csv` |
| `report[!0-9].csv` | One character not in the range `0..9` | `reportx.csv` |
| `*.{java,kt}` | Selects one of the two extension branches | `Main.java`, `Main.kt` |
| `**` | Matches zero or more characters, **may** cross separators | Usable in multi-level patterns |
| `\\*` | Escapes `*` to treat it as a literal name character (glob rule) | Names containing `*` on filesystems that allow it |

The syntax above describes glob; when writing a **Java string literal** you need extra `\\` escaping, and across different filesystems separators, valid names, and case sensitivity may vary. Do not assume filenames with `*` are valid on every operating system.

### How does `*` differ from `**`?

- `*` matches **zero or more** characters **within a single path component**, without crossing directory separators.
- `**` matches **zero or more** characters **including separators**, making it suitable for expressing multi-level path patterns.
- `?` matches **exactly one** non-separator character; it is not equivalent to `*`.
- `[]` is a **character class** and `{}` is a **subpattern group** in glob. These are not identical to `[]`/`{}` in every regex context.

Conceptual example:

```text
glob:*.java
  ├─ Main.java        ✓
  ├─ Test.java        ✓
  └─ src/Main.java    ✗  (because of separator)

glob:**/*.java
  ├─ src/Main.java         ✓
  └─ src/test/Test.java    ✓
```

**Very easy-to-miss note:** `glob:**/*.java` should not be assumed to also match `Main.java` sitting directly at the root on every provider, because the pattern still includes a separator segment before the final name. To handle files both at the root and under subdirectories uniformly, a clean approach is walking the tree with `Files.walk` and matching `path.getFileName()` against `glob:*.java`. That way the extension rule does not depend on file depth.

### `{}` in glob is not a regex quantifier

`glob:*.{java,kt}` selects `.java` or `.kt`.

In Java regex, `{4}` can mean **repeat exactly four times**, whereas in glob, curly braces denote an alternation group like `{java,kt}`. To match exactly four characters in glob, use `????` or a more specific pattern; to match four digits, regex `\\d{4}` is explicit.

Glob can use `\\` to escape special characters such as `*`, `?`, `[`, and `{`. In Java source, you must also escape `\\` for the Java string. When logic handles `\\` on Windows, be especially careful because it is also the system separator in many path forms; test directly on supported operating systems.

## 4. `regex:`: the power of regular expressions

With `regex:`, the pattern portion uses **Java `Pattern` syntax**. Example:

```java
PathMatcher report =
    FileSystems.getDefault().getPathMatcher(
        "regex:report-\\d{4}\\.csv"
    );
```

This is an **illustrative snippet**, with `import java.nio.file.*`. The pattern accepts `report-2026.csv` and rejects `report-ABCD.csv`.

Some commonly used regex components:

| Regex | Meaning |
|---|---|
| `.` | Any single character, excluding certain line terminators in default mode |
| `.*` | Zero or more arbitrary characters per `.` rules |
| `\\.` | Literal dot in the **regex expression** |
| `\\d` | One digit per Java regex rules |
| `[0-9]` | One ASCII character in the range 0–9 |
| `[A-Za-z]` | One character in the listed ASCII letter ranges |
| `(?:csv|tsv)` | Selects `csv` or `tsv` without creating a capturing group |
| `{4}` | Repeats the preceding element exactly four times |
| `+` | One or more times |
| `?` | Zero or one time |
| `^`, `$` | Start/end string anchors per Java regex semantics |

**Important distinction:** `PathMatcher.matches(Path)` **checks whether the entire Path representation matches**, not whether an arbitrary substring is found. Therefore you do not need to automatically add `.*` at the start/end just to turn a matcher into a filename search within a path. If you want to match a specific part, pass `path.getFileName()` or an appropriate relative `Path` to the matcher.

When writing a regex expression as a Java `String`, there are **two syntax layers**:

1. The Java string literal decodes Java escapes: `"\\d"` produces the two-character string `` and `d`.
2. The regex engine receives that string and interprets `\d` as the digit class.

Therefore:

| Intent | Java source literal |
|---|---|
| Regex for 4 digits | `"regex:\\d{4}"` |
| Regex for a literal dot | `"regex:\\."` |
| Regex for `.java` suffix | `"regex:.*\\.java"` |
| Regex for file `report-2026.csv` | `"regex:report-\\d{4}\\.csv"` |

Do not confuse `glob:*.java` with `regex:*.java`: in regex, `*` cannot start an expression like a glob wildcard because it is a quantifier for the **preceding** element. To express "any characters followed by `.java`" in regex, use `regex:.*\\.java` in Java source.

### Glob or regex?

- Use **glob** when describing extensions, prefixes, simple names, or readable filename patterns.
- Use **regex** when you need groups, repetition counts, positions, complex naming rules, valid character sets, or token formats.
- Do not pick regex just because it looks more powerful: when filtering `*.txt` or `*.java`, glob is usually easier to read and maintain.

## 5. Example 1: distinguishing matching a name vs matching an entire path

Save **`PathMatcherBasicsDemo.java`**:

```java
import java.nio.file.FileSystems;
import java.nio.file.Path;
import java.nio.file.PathMatcher;

public class PathMatcherBasicsDemo {
    public static void main(String[] args) {
        PathMatcher glob = FileSystems.getDefault()
            .getPathMatcher("glob:*.java");
        PathMatcher regex = FileSystems.getDefault()
            .getPathMatcher("regex:.*\\.java");

        Path plain = Path.of("Demo.java");
        Path nested = Path.of("src", "Demo.java");
        Path text = Path.of("Demo.txt");

        System.out.println("glob plain: " + glob.matches(plain));
        System.out.println("glob nested full: " +
            glob.matches(nested));
        System.out.println("glob nested filename: " +
            glob.matches(nested.getFileName()));
        System.out.println("regex filename: " +
            regex.matches(plain.getFileName()));
        System.out.println("glob text: " + glob.matches(text));
    }
}
```

Compile/run with Java 17+:

```bash
javac PathMatcherBasicsDemo.java
java PathMatcherBasicsDemo
```

Stdout on a typical default filesystem:

```text
glob plain: true
glob nested full: false
glob nested filename: true
regex filename: true
glob text: false
```

Explanation:

1. `glob:*.java` matches `Path.of("Demo.java")`.
2. `nested` has two components `src` and `Demo.java`, with a separator. `*` does not cross separators, so `glob.matches(nested)` is `false`.
3. `nested.getFileName()` contains only `Demo.java`; the matcher now receives the exact name portion to filter.
4. `regex:.*\\.java` corresponds to `.*\.java` at the regex layer, matching `Demo.java`.
5. The `.txt` extension is rejected.

The example uses simple ASCII names and does not depend on physical files existing. It demonstrates that **PathMatcher is not a filesystem scanner**: all three `Path`s are just objects holding paths.

## 6. Example 2: comparing glob `?` with regex `\\d{4}`

Although both can check "four characters", they are not identical.

Save **`GlobRegexComparisonDemo.java`**:

```java
import java.nio.file.FileSystems;
import java.nio.file.Path;
import java.nio.file.PathMatcher;

public class GlobRegexComparisonDemo {
    public static void main(String[] args) {
        PathMatcher glob = FileSystems.getDefault()
            .getPathMatcher("glob:report-????.csv");
        PathMatcher regex = FileSystems.getDefault()
            .getPathMatcher("regex:report-\\d{4}\\.csv");

        String[] names = {
            "report-2026.csv",
            "report-ABCD.csv",
            "report-26.csv",
            "other-2026.csv"
        };

        for (String name : names) {
            Path path = Path.of(name);
            System.out.println(name
                + " | glob=" + glob.matches(path)
                + " | regex=" + regex.matches(path));
        }
    }
}
```

Run:

```bash
javac GlobRegexComparisonDemo.java
java GlobRegexComparisonDemo
```

Stdout:

```text
report-2026.csv | glob=true | regex=true
report-ABCD.csv | glob=true | regex=false
report-26.csv | glob=false | regex=false
other-2026.csv | glob=false | regex=false
```

Why is `report-ABCD.csv` accepted by glob? Because `????` only requires **exactly four non-separator characters**, not necessarily digits. Regex `\\d{4}` (whose regex string after Java decoding is `\d{4}`) requires **four digits**, so it rejects four letters.

When you need to match a strict naming grammar, choose regex or add logic checks rather than assuming glob wildcards validate content format.

## 7. Which part of `Path` should be matched?

Decide the **pattern scope** clearly before creating a matcher. Four common cases exist:

| Value passed to `matches` | Interpretation | Example usage |
|---|---|---|
| `path` | The entire current `Path`, which may be relative or absolute | When the pattern describes the full structure of `path` |
| `path.getFileName()` | The last component (file/dir name) | Filtering all `*.java` regardless of depth |
| `root.relativize(path)` | Relative path **with respect to a defined root** | Filtering paths by position within a tree |
| `path.toAbsolutePath()` | Absolute path per current working directory | Match rules genuinely defined at the absolute path level |

Example:

```java
Path root = Path.of("project");
Path file = root.resolve(Path.of("src", "App.java"));

Path name = file.getFileName();   // App.java
Path relative = root.relativize(file); // src/App.java per system
```

This is an **illustrative snippet**; the display string of `relative` may be `src\\App.java` on Windows. `Path.getFileName()` may return `null` for some path types such as root-only; check for null before calling the matcher in arbitrary path-handling code.

**Important with `relativize`:** The two `Path`s should belong to the same filesystem/provider and be compatible in relative/absolute kind per the provider contract; otherwise `IllegalArgumentException` may be thrown. Standardize how `root` and `path` are represented before calling `relativize` if inputs come from multiple sources.

Do not use `root.relativize(path)` as an anti-path-traversal mechanism: creating a relative path only transforms representation; it does not prove `path` is safe or still stays inside root after resolving symbolic links.

### "Matching a name" and "matching directory structure" are two distinct tasks

- Requirement: "Every `.java` file in the tree" → `matcher.matches(path.getFileName())` during tree traversal.
- Requirement: "Only `.java` inside the `src` directory" → rule on the **relative path** and directory structure; or combine a parent check with a name matcher.
- Requirement: "Filter absolute paths under a root" → process with `Path`, validate scope and symlinks safely separately; pattern matching is only a name-selection step.

When designing filters, specify **depth**, **root set**, **whether symlinks are followed**, and **whether matching is case-sensitive** to avoid surprises when moving from local development to CI or production.

## 8. Example 3: `Files.list` and `Files.walk` + `PathMatcher`

`PathMatcher` does not traverse directories by itself. To filter actual files, you need listing APIs such as:

- `Files.list(dir)`: stream of **direct** entries in the directory.
- `Files.walk(root)`: stream of paths from **recursive** tree traversal, with optional depth limit.
- `Files.walkFileTree(root, ...)`: visitor for finer-grained control over state and traversal errors.

Both `Files.list` and `Files.walk` return a `Stream<Path>` that **must be closed** using try-with-resources to release system resources. While consuming the stream, I/O errors may be thrown as `UncheckedIOException`. The `matcher.matches(path)` filter does not turn the stream into an immutable snapshot.

Save **`PathMatcherDirectoryDemo.java`**:

```java
import java.io.IOException;
import java.nio.file.FileSystems;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.PathMatcher;
import java.util.List;
import java.util.stream.Stream;

public class PathMatcherDirectoryDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("pathmatch-");
        Path sub = root.resolve("sub");

        try {
            Files.createDirectory(sub);
            Files.createFile(root.resolve("a.java"));
            Files.createFile(root.resolve("b.java"));
            Files.createFile(root.resolve("readme.md"));
            Files.createFile(sub.resolve("nested.java"));

            PathMatcher matcher = FileSystems.getDefault()
                .getPathMatcher("glob:*.java");

            List<String> direct;
            try (Stream<Path> entries = Files.list(root)) {
                direct = entries
                    .filter(Files::isRegularFile)
                    .filter(p -> matcher.matches(p.getFileName()))
                    .map(p -> p.getFileName().toString())
                    .sorted()
                    .toList();
            }

            List<String> recursive;
            try (Stream<Path> entries = Files.walk(root)) {
                recursive = entries
                    .filter(Files::isRegularFile)
                    .filter(p -> matcher.matches(p.getFileName()))
                    .map(p -> p.getFileName().toString())
                    .sorted()
                    .toList();
            }

            System.out.println("direct: " + direct);
            System.out.println("recursive: " + recursive);
        } finally {
            Files.deleteIfExists(sub.resolve("nested.java"));
            Files.deleteIfExists(root.resolve("a.java"));
            Files.deleteIfExists(root.resolve("b.java"));
            Files.deleteIfExists(root.resolve("readme.md"));
            Files.deleteIfExists(sub);
            Files.deleteIfExists(root);
        }
    }
}
```

Run with Java 17+:

```bash
javac PathMatcherDirectoryDemo.java
java PathMatcherDirectoryDemo
```

Stdout when the fixture is created and listed successfully:

```text
direct: [a.java, b.java]
recursive: [a.java, b.java, nested.java]
```

Analysis:

1. The program creates a temporary directory with two `.java` files directly inside it and one `.java` file inside `sub`.
2. `Files.list(root)` only sees top-level entries; after filtering for regular files and `.java` names, it gets `a.java` and `b.java`.
3. `Files.walk(root)` traverses deeply, so `nested.java` is also included. Matching **`getFileName()`** lets the same `*.java` glob accept names at any depth.
4. `sorted()` makes the output order deterministic; the traversal APIs themselves **do not promise** stable ordering across all systems.
5. Both Streams are closed in TWR; `finally` cleans up the fixture.
6. `Files.isRegularFile` uses the API's default symlink policy; if symlinks must not be followed, specify `LinkOption.NOFOLLOW_LINKS` and explicit traversal options rather than assuming all links are allowed.

**Limits:** `Files.walk` traverses the real filesystem; in this example there are only four entries created by the program. For very large trees, bound depth, I/O cost, and error-handling strategy. Temporary-file cleanup code in `finally` can also throw errors; in production, use a cleanup mechanism with a policy that avoids masking the primary exception.

## 9. Distinguishing `PathMatcher` and `java.util.regex.Pattern`

A regex can certainly be used in two ways:

**Approach A — `PathMatcher` from the filesystem:**

```java
PathMatcher matcher = FileSystems.getDefault()
    .getPathMatcher("regex:report-\\d{4}\\.csv");

boolean ok = matcher.matches(Path.of("report-2026.csv"));
```

**Approach B — `Pattern` on a string:**

```java
Pattern pattern = Pattern.compile("report-\\d{4}\\.csv");

boolean ok = pattern.matcher("report-2026.csv").matches();
```

Both snippets are **illustrative**, requiring `import java.nio.file.*` or `java.util.regex.Pattern` respectively. In both simple ASCII-name examples, `ok == true`.

Differences:

| Aspect | `PathMatcher` | `Pattern` |
|---|---|---|
| Input | `Path` | `CharSequence` (usually `String`) |
| Obtained via | `FileSystem.getPathMatcher` | `Pattern.compile` |
| Syntax | `glob:`, `regex:` | Java regex |
| Filesystem relation | Matcher bound to provider | Not bound to a provider |
| Full match | `matcher.matches(path)` | `pattern.matcher(s).matches()` |
| Find a small substring | Select the appropriate Path part | `Matcher.find()` |
| Application | Path/filename matching policies | General text pattern validation/extraction |

Do not confuse `PathMatcher.matches` with `Matcher.find()`. `Matcher.find()` can locate a substring; `matches()` requires matching the entire input. In many programs, a user enters a "search keyword" yet the developer calls `PathMatcher.matches` with a wildcard-free pattern; the result is false even when the name contains the keyword.

For example, to match any name containing `invoice`, the glob pattern is `glob:*invoice*` (on a single name), not `glob:invoice`.

## 10. Operating systems, separators, and case sensitivity

A `PathMatcher` created by a filesystem provider may **not produce the same results** across all operating systems if the pattern depends on:

- **Directory separators:** Unix systems typically use `/`; Windows typically represents paths with `\\`. Java `Path` abstracts many operations, yet hard-coding separators into glob/regex can cause porting bugs.
- **Case sensitivity:** `App.JAVA` may be treated differently from `App.java` by the filesystem/provider. Do not assume identical policies across Linux, Windows, macOS, and ZipFS.
- **Valid naming rules:** names containing `:`, `*`, `?`, or control characters may be forbidden or mean something different on one filesystem versus another.
- **Unicode/canonical equivalence:** two visually identical strings may consist of different code points; do not assume every filesystem/provider normalizes name strings the same way.
- **Absolute vs relative:** absolute paths include roots, drive letters, or other components; a glob designed for simple names will not automatically match that entire form.

### A portable way to filter extensions

If the requirement is solely **the filename**, retrieve `path.getFileName()` and use a separator-free pattern:

```java
PathMatcher javaName = path.getFileSystem()
    .getPathMatcher("glob:*.java");

Path filename = path.getFileName();
boolean accepted =
    filename != null && javaName.matches(filename);
```

This is an **illustrative snippet**, requiring `path` non-null and importing `Path`/`PathMatcher`. It avoids hard-coding separators in the pattern, though it **does not automatically enforce the same case-sensitivity policy** across all systems; if the application requires uniform case-insensitive behavior, design and test an explicit policy.

### Regex with multi-level paths

If you want regex to check names in a directory tree:

1. Define the root and convert candidates into `root.relativize(path)`.
2. Define the separator form used in the regex and how it is recognized by the provider.
3. Avoid assuming `regex:src/.+\\.java` is always portable for every `Path` on every OS.
4. If you only need to inspect a single component, extract `relative.getName(index)` or use `getFileName()`.
5. Write integration tests on target platforms if the pattern has a multi-level structure.

Do not blindly run `path.toString().replace('\\', '/')` and pass it back to a provider's `PathMatcher` without clarifying the new `Path` type and intended semantics. If an **OS-independent path syntax** is required (e.g. URL/ZIP entry keys using `/`), consider defining a canonical application representation model and applying `Pattern` to that string, or using the appropriate provider.

## 11. Validation, pattern errors, and untrusted data

### A malformed pattern can crash the program when creating the matcher

Example of an invalid regex:

```java
String syntaxAndPattern = "regex:[";
PathMatcher bad = FileSystems.getDefault()
    .getPathMatcher(syntaxAndPattern);
```

This is an **anti-example**: on a standard regex provider, the pattern has an unclosed character class and creating the matcher throws `PatternSyntaxException`. In production, if patterns come from configuration/users, catch `PatternSyntaxException`, report a clear error, and do not store the invalid pattern into the active filter.

Unsupported syntax or one the provider does not understand is a configuration error. Do not automatically convert arbitrary prefixless strings to regex; always specify `glob:` or `regex:` explicitly.

### A matcher is not a path security validation tool

`matcher.matches(path)` only returns true/false against a pattern. If paths come from user input:

- **Path traversal:** `../secret.txt` can slip into a pipeline if you only inspect `getFileName()` (`secret.txt`) and ignore where it points.
- **Symlink:** a path appearing to sit inside root may link out to another filesystem. `normalize()` only processes syntactic components such as `.`/`..` and does not resolve symlinks in all cases.
- **TOCTOU:** the path/metadata can change between matching, `Files.isRegularFile`, and actual opening.
- **Overly complex user-supplied regex:** can consume abnormal CPU on long paths (regex backtracking); bound pattern length and complexity.
- **Resource exhaustion:** `Files.walk` over huge trees, symlinks/permissions, and unbounded entry counts can exhaust resources.

Mitigation must rely on **root rules, access permissions, opening methods, file descriptors, validation, and appropriate symlink policies**, not patterns alone. When processing untrusted directories, you may need `SecureDirectoryStream` (if supported by the provider) or OS access-restriction mechanisms.

### `matches` does not require the file to exist

```java
PathMatcher p = FileSystems.getDefault()
    .getPathMatcher("glob:*.txt");
boolean matched = p.matches(Path.of("not-created.txt"));
```

This is an **illustrative snippet**: `matched` can be `true` even though `not-created.txt` does not exist yet. If the requirement is "the file must exist and be a regular file", you must check with `Files.isRegularFile` or an appropriate open operation in the workflow, while accounting for race-condition risks.

## 12. Performance and filter design

A matcher generally processes only the **path representation**, without accessing the filesystem to read content. However, listing trees, querying metadata, and reading actual files can incur significant I/O.

Recommended practices:

1. **Create the matcher once** outside the loop and reuse it across many `Path`s.
2. **Choose scope first**: name only, relative path, or full path.
3. **Reduce metadata queries**: if filtering solely by name, do not call `Files.isRegularFile` for every entry unless regular files are genuinely required.
4. **Bound traversal**: choose `Files.list` for one level or `Files.walk(root, maxDepth)` when depth is bounded.
5. **Close streams**: `Files.list`/`Files.walk` are I/O resources; use try-with-resources.
6. **Define ordering**: use `sorted()` if deterministic output is needed, keeping in mind sorting many paths consumes memory.
7. **Do not put write/delete operations inside the match predicate**: filters should be pure checks; if acting on files, separate the processing stage and ensure permissions/recoverability.
8. **Log errors with context**: missing permissions, deleted directories, broken symbolic links, and bad patterns require different handling.
9. **Test on target OSes/providers**: especially when patterns contain separators or uppercase/lowercase letters.
10. **Prefer relative paths with an explicitly defined root** when rules tie to project structure; avoid rules that implicitly depend on the process working directory.

If you only need a simple fixed pattern like `*.java`, a `glob` on `getFileName()` is usually a good starting point. If you need to validate "names of the form `report-YYYY.csv`", regex is clearer. When listing and processing tens of thousands of files, choosing the right traversal API has a far greater performance impact than choosing between glob and regex.

## 13. Self-check questions

**Question 1.** How is a `PathMatcher` obtained?

**Answer:** From `FileSystem.getPathMatcher("glob:...")` or `getPathMatcher("regex:...")`, usually starting from `FileSystems.getDefault()`.

**Question 2.** Does `glob:*.java` match `Path.of("src", "Main.java")`? If not, how do you filter by name?

**Answer:** On a typical default provider, no, because `*` does not cross separators. Use `matcher.matches(path.getFileName())` to match `Main.java`.

**Question 3.** Does `glob:report-????.csv` require the four characters to be digits?

**Answer:** No, `?` matches any non-separator character. Use regex `report-\\d{4}\\.csv` if four digits are required.

**Question 4.** In a Java string literal, why does `"regex:.*\\.java"` have two backslashes?

**Answer:** One `\\` escapes at the Java string layer; the actual regex needs `\.` to match a literal dot instead of the wildcard `.`.

**Question 5.** Does calling `matcher.matches(path)` scan directories or check `Files.exists(path)`?

**Answer:** No. It only matches the supplied `Path`. To filter existing files, use separate filesystem traversal/inspection APIs.

**Question 6.** When using `Files.walk(root)` to find all `.java` files at any depth, how can you avoid a separator-dependent multi-level glob?

**Answer:** Filter with `p -> matcher.matches(p.getFileName())` using `glob:*.java`, then apply file-type, permission, and symlink requirements separately.

**Question 7.** How do `Files.list(root)` and `Files.walk(root)` differ?

**Answer:** `Files.list` lists one level; `Files.walk` traverses the tree according to depth configuration. Both return a `Stream<Path>` that must be closed.

**Question 8.** Does `PathMatcher` guarantee identical behavior on Windows and Linux for patterns containing separators and uppercase letters?

**Answer:** No. The matcher is tied to the filesystem/provider; you must account for separators, case sensitivity, and Path representation.

**Question 9.** If `glob:*.txt` matches a `Path`, does that prove the file is safe to read or inside an allowed root?

**Answer:** No. It is a name/path pattern check, not traversal/symlink validation, permission checking, or safe file opening.

**Question 10.** If you want to find a substring in a string rather than match an entire path, what should you use?

**Answer:** You can use `java.util.regex.Pattern` and `Matcher.find()` on an explicit string, or design a glob with wildcards surrounding the name as required.

## Summary

- `PathMatcher` is created from `FileSystem.getPathMatcher("glob:...")` or `"regex:..."`.
- `glob` is concise for filenames (`*`, `?`, `[]`, `{}`, `**`), whereas `regex` suits structured/quantified rules.
- `matches(Path)` matches **the exact Path object passed by the caller**; when filtering only by filename, use `getFileName()`.
- Both glob and regex can be sensitive to filesystem/provider, separators, and case sensitivity; do not assume identical behavior across all platforms.
- `PathMatcher` does not traverse directories, verify existence, or solve security. Combine it with `Files.list`/`Files.walk`, try-with-resources, and appropriate validation steps.
- With Java 17, keep **match scope**, **filter order**, **root boundaries**, and **filesystem contracts** explicit to avoid subtle bugs.