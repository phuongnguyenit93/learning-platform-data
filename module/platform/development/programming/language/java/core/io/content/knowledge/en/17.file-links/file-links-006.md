# `Files.isSameFile` vs. `Path.equals` in Java NIO.2

## 1. Two Different Questions

When working with files in Java, **a path** and **the actual file** are not the same concept:

- `path1.equals(path2)` asks: **Do two `Path` objects represent equal paths according to the `FileSystem`'s rules?**
- `Files.isSameFile(path1, path2)` asks: **Do two paths point to the same file/entity on the file system?**

A single file can be accessed through multiple different paths: paths containing `.`/`..`, relative and absolute paths, symbolic links, or hard links. Therefore, `Path.equals` can be `false` while `Files.isSameFile` is `true`.

These are two checks with **different purposes, costs, and error-handling behavior**. Do not substitute one for the other merely because both return `boolean`.

## 2. `Path.equals(Object)`: Comparing Path Representations

`Path` belongs to `java.nio.file`. The call:

~~~java
boolean equalPaths = path1.equals(path2);
~~~

has the following characteristics:

1. **Does not access the file system** to look up the file; the path does not need to exist.
2. Comparison depends on the `FileSystem` implementation: some systems are case-sensitive, others are case-insensitive. Do not assume every operating system follows the same rules.
3. Objects of a type other than `Path` or a `Path` belonging to a different `FileSystem` return `false`.
4. Components such as `.` and `..` **are not implicitly normalized** by `equals`; absolute and relative paths are also not automatically converted to match each other.
5. Because it obeys the `equals`/`hashCode` contract, this comparison is suitable when using `Path` as a `HashMap` key, a `HashSet` element, or comparing path structures that have already been processed under a uniform convention.

Illustrative example:

~~~java
Path a = Path.of("docs", "notes.txt");
Path b = Path.of("docs", ".", "notes.txt");

System.out.println(a.equals(b));             // usually false
System.out.println(a.equals(b.normalize())); // usually true
~~~

`normalize()` only removes redundant components **syntactically**, without needing to know which files exist. When symbolic links are present, removing `..` can change the actual target file; therefore `normalize()` must not be treated as a verification that two paths point to the same file.

## 3. `Files.isSameFile(Path, Path)`: Comparing File Identity

API signature:

~~~java
public static boolean isSameFile(Path path, Path path2) throws IOException
~~~

`Files.isSameFile` determines whether two paths locate the same file. Depending on the file system provider, this may require accessing the file system and reading file-related information. It can recognize **the same file under two different path names**, including when supported via symbolic links or hard links.

Key rules from the Java 17 API contract:

- **If `path.equals(path2)` is already `true`**, `isSameFile` returns `true` immediately, **without checking whether the file exists**.
- If the two `Path` objects belong to **two different file-system providers**, it returns `false`.
- In all remaining cases, the API checks whether the two paths locate the same file; it may throw `IOException` when the check fails.
- When the file system does not change during the call, the "same file" relation is reflexive, symmetric, and transitive. If the file system changes concurrently, those guarantees do not hold.
- The method has no `LinkOption.NOFOLLOW_LINKS` parameter and typically identifies the target of a symbolic link when the link resolves normally.

**Common pitfall:** `Files.isSameFile(missing, missing)` returns `true` even though `missing` does not exist, due to the short-circuit optimization for equal `Path` objects. Conversely, two *different* paths that cannot be accessed to identify the file may throw `NoSuchFileException` or another `IOException`. Do not use `isSameFile` as a way to check file existence; use `Files.exists`, `Files.notExists`, or an appropriate open/read operation, while keeping in mind that file state can change immediately after checking.

## 4. Comparison Table

| Criterion | `Path.equals` | `Files.isSameFile` |
|---|---|---|
| What does it compare? | `Path` representation per `FileSystem` rules | The file located by the two `Path` objects |
| Disk / I/O access? | No | Potentially yes |
| Does the path need to exist? | No | Typically must be inspectable; exception when both `Path` objects are already equal |
| `.`, `..`, different path spellings | Not normalized automatically before comparing | Can be the same file if both paths resolve to the same target |
| Symbolic links, hard links | Does not check link relationships | Can identify the same file |
| `IOException`? | No checked `IOException` | Yes, must be declared or handled |
| Primary use | Comparing structure / `Path` keys | Checking file identity |

**Do not infer** "two files have identical content ⇒ `isSameFile` returns `true`". Two independent files containing the exact same bytes still have distinct identities.

## 5. Runnable Java 17+ Example

The program below uses a temporary directory and creates a real subdirectory so that `sub/../data.txt` can be resolved by the file system. It does not depend on permissions to create symbolic links or hard links.

**File: `SameFileVsPathEquals.java`**

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class SameFileVsPathEquals {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("same-file-demo-");

        try {
            Files.createDirectory(root.resolve("sub"));

            Path first = Files.writeString(
                    root.resolve("data.txt"), "hello", StandardCharsets.UTF_8);
            Path alias = root.resolve("sub").resolve("..").resolve("data.txt");
            Path other = Files.writeString(
                    root.resolve("other.txt"), "hello", StandardCharsets.UTF_8);
            Path missing = root.resolve("missing.txt");

            System.out.println(first.equals(alias));
            System.out.println(Files.isSameFile(first, alias));
            System.out.println(first.equals(alias.normalize()));
            System.out.println(Files.isSameFile(first, other));
            System.out.println(Files.isSameFile(missing, missing));
        } finally {
            Files.deleteIfExists(root.resolve("other.txt"));
            Files.deleteIfExists(root.resolve("data.txt"));
            Files.deleteIfExists(root.resolve("sub"));
            Files.deleteIfExists(root);
        }
    }
}
~~~

Compile and run in the directory containing the source file:

~~~bash
javac SameFileVsPathEquals.java
java SameFileVsPathEquals
~~~

**Output:**

~~~text
false
true
true
false
true
~~~

Step-by-step explanation:

1. `first.equals(alias)` → `false`: the two `Path` objects have different sequences of components.
2. `Files.isSameFile(first, alias)` → `true`: because the `sub` directory exists, traversing `sub/..` returns to the parent directory and leads to `data.txt` itself.
3. `first.equals(alias.normalize())` → `true`: syntactic normalization removes the `sub/..` pair in this specific example.
4. `Files.isSameFile(first, other)` → `false`: two independent files even though both contain `hello`.
5. `Files.isSameFile(missing, missing)` → `true`: both `Path` arguments are equal, so existence is not checked.

The program uses `finally` to delete temporary resources; a file deletion failure can still throw `IOException` on systems that lock files. The program does not rely on a specific temporary directory path, so it does not print random paths.

## 6. Same File via Symbolic Link and Hard Link

Imagine the following paths (illustrative, depending on file system support):

~~~text
/work/report.csv          ← original file
/work/latest.csv          ← symbolic link to report.csv
/work/report-copy-name    ← hard link to the same file
~~~

- `Path.of("/work/report.csv").equals(Path.of("/work/latest.csv"))` is typically `false` due to different path representations.
- `Files.isSameFile(original, symbolicLink)` is typically `true` when the symbolic link is valid and resolves to the original file.
- `Files.isSameFile(original, hardLink)` is `true` when the hard link actually points to the same file.
- Copying `report.csv` to a new file with identical content does not make them "the same file"; `isSameFile`, when the check succeeds, returns `false`.

Creating links via `Files.createSymbolicLink` or `Files.createLink` depends on provider support and OS permissions, and may throw exceptions. Do not write unit tests that *require* an arbitrary Windows/Linux system to succeed at creating symbolic links unless the CI environment is prepared for it.

## 7. Distinction from `normalize()`, `toAbsolutePath()`, `toRealPath()`

- **`path.normalize()`**: normalizes syntax (`.` and `..` segments may be collapsed), without verifying that a real file exists. Does not guarantee preservation of the target file when symbolic links are present.
- **`path.toAbsolutePath()`**: converts a path to absolute form according to the file system context; **does not** confirm that it exists or that it is the unique path to the file.
- **`path.toRealPath()`**: accesses the file system by default, producing a real/canonical path according to the provider, typically resolving symbolic links and requiring the target to exist; may throw `IOException`. `NOFOLLOW_LINKS` changes how links are handled.
- **`Files.isSameFile(a, b)`**: directly answers whether two paths locate the same file. Does not require manually converting both to strings or comparing `toString()`.

For example, when you need to check file identity, `Files.isSameFile` expresses intent more clearly than comparing `toRealPath().equals(...)`. Conversely, if you need to build `Path` keys under an application-specific normalization convention, `equals` may be more appropriate. The two approaches solve two different problems.

## 8. Choosing the API in Real-World Scenarios

**Use `Path.equals` when:**

- You want to know whether two stored path values are equal according to `FileSystem` rules.
- You want to look up data structures based on `equals`/`hashCode` without performing I/O.
- You are processing paths that do not exist yet (for example, planning new file creation).

**Use `Files.isSameFile` when:**

- You want to know whether two differently named file inputs point to the same existing file.
- You want to detect aliases via symbolic links/hard links in file-processing logic.
- You need to avoid performing duplicate operations on the same file when two paths are written differently.

Example of exception handling when a requirement only operates on two files verified to exist:

~~~java
try {
    if (Files.isSameFile(source, destination)) {
        throw new IllegalArgumentException(
                "Source và destination cùng trỏ tới một tệp");
    }
    // Continue with logic appropriate for the application.
} catch (IOException ex) {
    // Cannot conclude file identity: report error or handle per application policy.
    throw new IllegalStateException("Không kiểm tra được danh tính tệp", ex);
}
~~~

The snippet above is **illustrative code inside a method** where two variables `Path source` and `Path destination` are already declared; it is not a standalone runnable Java program.

Note: even right after `isSameFile` returns a result, another task can delete/rename/replace a file link before the next operation (**race/TOCTOU**). Do not treat a check result at a single point in time as a safety guarantee for a sensitive sequence of operations. If atomicity or protection against concurrent modification is needed, prefer appropriate file/handle operation APIs and access control mechanisms for the problem.

## 9. Common Mistakes and How to Remember

1. **Using `equals` to identify a physical file:** misses symbolic links, hard links, and different paths pointing to the same file.
2. **Using `isSameFile` like `Files.exists`:** two equal `Path` objects return `true` even when the file does not exist.
3. **Assuming `isSameFile` never throws exceptions:** you must account for `IOException`, missing permissions, and changing file state.
4. **Treating `normalize()` as file system canonicalization:** it only processes syntax, and can be wrong about file identity when symbolic links are present.
5. **Comparing `path.toString()` strings:** error-prone due to syntactic differences, file system rules, and case sensitivity.
6. **Equating content with identity:** two copies with identical checksums are still two distinct files.

Quick summary to remember:

~~~text
Path.equals(a, b)       → Are the two Path representations equal?
Files.isSameFile(a, b)  → Are the two Paths pointing to the same file?
~~~

### Official Documentation

- [Java 17: Path.equals](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html#equals(java.lang.Object))
- [Java 17: Files.isSameFile](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#isSameFile(java.nio.file.Path,java.nio.file.Path))
- [Java 17: Path.toRealPath](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html#toRealPath(java.nio.file.LinkOption...))