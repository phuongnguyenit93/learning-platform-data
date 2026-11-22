# `Path.relativize()` and compatibility conditions in Java NIO.2

## 1. Purpose and core concept

In Java NIO.2, `java.nio.file.Path` represents a path in a file system. `Path.relativize(Path other)` constructs a **relative path from the location represented by the current Path to the target Path**. It returns a new `Path` object; it does not open, create, move, inspect content, or modify files on disk.

For example, suppose a project has two locations:

```text
workspace/
├── module/                 ← base path
└── assets/
    └── logo.png            ← target path
```

From `workspace/module` to `workspace/assets/logo.png`, the relative path is:

```text
../assets/logo.png
```

Here `..` means moving up one path component; then moving down to `assets/logo.png`. `Path.relativize` uses `Path` components and the rules of the filesystem/provider, **not string splitting by `/`**.

This lesson helps you:

- Understand the result of `base.relativize(target)` and the direction of path calculation (swapping the two arguments changes the result).
- Master the **compatibility conditions**: paths of the same relative/absolute kind, compatible roots, compatible providers/filesystems.
- Use `normalize()`, `toAbsolutePath()`, and `resolve()` in their proper roles to compute and verify paths.
- Distinguish **purely syntactic** operations from real paths on the filesystem, symbolic links, and `toRealPath()`.
- Handle `IllegalArgumentException`/`ProviderMismatchException` instead of manually manipulating strings or assuming the operation always succeeds.
- Apply it to building relative paths for configuration, links between directories, project structures, and file paths without using it in place of a security mechanism.

**Remember right from the start:** In `base.relativize(target)`, the receiver object is **base**, and the argument is **target**. This is neither a command to convert `target` to absolute nor a command to create a file on disk.

## 2. Syntax and path computation mechanism

Declaration:

```java
Path relative = base.relativize(target);
```

The result is typically a path **without a root**, consisting of `..` components to step up from base and the remaining names to step down to target.

Visualize the steps for compatible paths:

1. Examine the common leading components of base and target.
2. For each remaining component in **base**, add one `..` to the result.
3. Then append the remaining components in **target**.
4. Return a relative `Path` using the separator appropriate for the provider.

Component examples (using `/` for illustration):

| Base | Target | Illustrative relative result |
| --- | --- | --- |
| `project` | `project/src/Main.java` | `src/Main.java` |
| `project/src` | `project/test/Test.java` | `../test/Test.java` |
| `a/b/c` | `a/b/c` | Empty path |
| `a/b/c` | `a/b` | `..` |
| `a/b/c` | `a/x.txt` | `../../x.txt` |
| `docs` | `images/logo.png` | `../images/logo.png` |

The table assumes both arguments have the **same provider, same relative kind**, and components in appropriate form. Java operates according to the `Path` provider's rules, so when printed as a string on Windows you may see `\` instead of `/`.

### 2.1. What if it is the same path?

If `base` and `target` represent the same path under the appropriate comparison, `base.relativize(target)` produces an **empty path**, typically with string `""`. It is not `null`, and you should not assume `Path.getNameCount() == 0` across all providers for an empty path. Distinguish:

- `Path.of("")`: a valid Path object representing an empty path string.
- `null`: not a Path; passing it to `relativize` is not a valid operation.
- `"."`: current directory component in path syntax; `Path.of(".")` is not necessarily equal to `Path.of("")` before normalization.

### 2.2. `relativize` is a one-way operation

Do not confuse the direction:

```java
Path a = Path.of("project", "src");
Path b = Path.of("project", "test", "Test.java");

Path fromSrcToTest = a.relativize(b); // ../test/Test.java
Path fromTestToSrc = b.relativize(a); // ../..
```

The two results differ because the base has changed. In the second example, the base is **the path representing the file `Test.java` itself**, not its parent directory `test`. If you want to go **from the directory containing the file** rather than from the file path, use `b.getParent().relativize(a)`; then the result only needs to go up one level (`..`).

This is a key point: `relativize` computes solely from **Path components**; it does not know whether a path points to a file or a directory and does not automatically "strip the last filename".

## 3. Most important compatibility conditions

### 3.1. Both relative or both absolute

A typical compatible pair:

```java
Path base = Path.of("project", "src");
Path target = Path.of("project", "docs", "guide.md");
Path result = base.relativize(target); // ../docs/guide.md
```

Both are **relative** on the same filesystem. Conversely:

```java
Path base = Path.of("project", "src");   // relative
Path target = base.toAbsolutePath();      // absolute

// Invalid: base.relativize(target) throws IllegalArgumentException
```

By the `Path.relativize` contract, when one path is absolute and the other is relative, the method throws **`IllegalArgumentException`**. Java does not guess a root for one side in this calculation.

How to prepare both arguments when the context genuinely permits:

```java
Path relativeBase = Path.of("project", "src");
Path relativeTarget = Path.of("project", "docs", "guide.md");

Path absoluteBase = relativeBase.toAbsolutePath().normalize();
Path absoluteTarget = relativeTarget.toAbsolutePath().normalize();

Path route = absoluteBase.relativize(absoluteTarget);
```

**Note:** both `toAbsolutePath()` calls use the process working directory context; the conversion must reflect the same real frame of reference. Converting everything to absolute **does not automatically solve** differing roots or differing providers.

### 3.2. Roots must be compatible

For absolute paths, both usually need **roots that can be relativized together**. On Linux/Unix, for example, `/home/a` and `/var/data` both have root `/`, so the default provider typically computes a path from one to the other.

On Windows, an absolute path on drive `C:\` and a path on `D:\` have two different roots; it is generally impossible to express the target solely with relative `..` steps from the base. The result may be `IllegalArgumentException`. UNC paths (network shares) also have their own root characteristics.

Descriptive example, **not portable executable code**:

```text
Base:    C:\projects\app
Target:  D:\archive\image.png
Result:  no suitable relative path under standard relativize rules
```

Do not build logic by catching the exception and stripping drive letters with `substring`; doing so loses root semantics and constructs wrong paths. If relativizing is impossible, keep the absolute path or reject the operation per application contract.

### 3.3. Provider and filesystem must be compatible

A `Path` does not necessarily represent the default filesystem on disk. Java can use different **FileSystemProvider** implementations, such as the default filesystem, a ZIP filesystem, or a third-party library provider.

A `Path` from the default filesystem and a `Path` from a ZIP filesystem **cannot be treated as two branches in the same path tree** merely because their `toString()` outputs look similar.

When providers are incompatible, `relativize` may throw **`ProviderMismatchException`** (a subclass of `IllegalArgumentException`), or have other provider-specific compatibility conditions. Do not mix `Path` objects from different providers and hope `normalize()` or `toAbsolutePath()` puts them on the same filesystem.

### 3.4. Quick decision table

| Base | Target | Feasibility |
| --- | --- | --- |
| Relative A | Relative B on the same provider | Usually relativizable |
| Absolute A | Absolute B with compatible root/provider | Usually relativizable |
| Relative A | Absolute B | **Incompatible**, throws `IllegalArgumentException` |
| Absolute A | Relative B | **Incompatible**, throws `IllegalArgumentException` |
| Absolute C: | Absolute D: on Windows | Incompatible roots; generally not relativizable |
| Default filesystem | ZIP filesystem | Different providers/filesystems; do not assume relativizable |
| Same pathname | Same pathname | Empty path |
| Two Paths with unnormalized `.`, `..` | Same kind/root | Computable, though results can be confusing; define a normalization strategy |

There is no universal "force to relative" operation applicable to every pair of `Path`s. You must establish the **frame of reference**: same filesystem, same root, same path semantics.

## 4. Complete cross-platform Java 17+ example

The example below avoids printing strings with OS-dependent separators. Instead, it prints component counts, checks `..`, and demonstrates the `resolve`/`normalize` relationship. The program **does not need to create real files**.

Save as **`PathRelativizeDemo.java`**:

```java
import java.nio.file.Path;

public class PathRelativizeDemo {
    public static void main(String[] args) {
        Path base = Path.of("workspace", "module");
        Path target = Path.of("workspace", "assets", "logo.png");

        Path route = base.relativize(target);

        System.out.println("Base relative: " + !base.isAbsolute());
        System.out.println("Target relative: " + !target.isAbsolute());
        System.out.println("Route relative: " + !route.isAbsolute());
        System.out.println("Route parts: " + route.getNameCount());
        System.out.println("Starts with ..: "
                + route.getName(0).toString().equals(".."));
        System.out.println("Reconstructed: "
                + base.resolve(route).normalize()
                          .equals(target.normalize()));

        Path same = base.relativize(base);
        System.out.println("Same gives empty: "
                + same.toString().isEmpty());

        try {
            base.relativize(target.toAbsolutePath());
            System.out.println("Mixed types accepted");
        } catch (IllegalArgumentException error) {
            System.out.println("Mixed types rejected");
        }
    }
}
```

Compile/run with JDK 17+:

```bash
javac -encoding UTF-8 PathRelativizeDemo.java
java PathRelativizeDemo
```

**Stdout in a typical default filesystem environment:**

```text
Base relative: true
Target relative: true
Route relative: true
Route parts: 3
Starts with ..: true
Reconstructed: true
Same gives empty: true
Mixed types rejected
```

**Step-by-step explanation:**

1. `Path.of("workspace", "module")` and `Path.of("workspace", "assets", "logo.png")` are both relative.
2. The two paths share the common component `workspace`. From `module` it goes up with `..` and then down to `assets/logo.png`, so `route` has three components.
3. `route.getName(0)` is `".."`. Testing relies on **Path components**, not on `/` or `\` separators.
4. `base.resolve(route).normalize()` reconstructs a path lexically equivalent to `target.normalize()` in the example.
5. Calling `base.relativize(base)` produces a result representing the empty path.
6. Calling `base.relativize(target.toAbsolutePath())` mixes one relative and one absolute path; the branch catching `IllegalArgumentException` executes.

The example does not prove that `logo.png` exists. `Path.relativize` and `normalize()` here operate solely on name components. Even if `workspace` does not exist on disk, all syntactic stdout lines remain valid as shown.

### 4.1. Avoid hard-coded separator strings in tests

On Unix, `route.toString()` typically looks like `../assets/logo.png`, whereas on Windows it is `..\assets\logo.png`. To make tests run on both platforms, compare against `Path.of("..", "assets", "logo.png")`:

```java
// Additional illustration (placed after route is created):
boolean equivalent =
        route.equals(Path.of("..", "assets", "logo.png"));
System.out.println(equivalent);
```

This is an **illustrative snippet**; it requires the `route` variable from the full runnable example. The result is `true` under the default provider given the input above.

## 5. `normalize()` and when to apply it

### 5.1. Syntactic normalization before computing

`Path.normalize()` removes redundant components such as `.` and name/`..` pairs where possible. This method **does not access the filesystem** and does not require the file to exist.

Example:

```java
Path base = Path.of("root", "docs", "..", "src");
Path target = Path.of("root", "assets", ".", "icon.svg");

Path normalizedBase = base.normalize();     // root/src
Path normalizedTarget = target.normalize(); // root/assets/icon.svg

Path route = normalizedBase.relativize(normalizedTarget);
// ../assets/icon.svg (displayed using the platform separator)
```

These lines illustrate API syntax, not a complete class. For project structures and purely lexical paths, the strategy of **normalizing both sides before relativizing** makes results easier to read and predict.

Apply the **same strategy** to both base and target. If one side is normalized while the other still has redundant `..` components, the result may mislead readers.

### 5.2. Do not confuse `normalize` with canonical/real path

`normalize()` only cleans up a path syntactically; it does not ask the filesystem whether a `link` component is a symbolic link.

Conceptual example (suppose `link` is a symbolic link pointing to another location):

```text
/data/link/../report.txt
```

`normalize()` may simplify this to `/data/report.txt`, but when the OS actually traverses `link` as a symlink, the semantics of `..` may differ. Therefore, the rule "cancel a name followed by `..`" **does not prove** that the old and new paths point to the same physical file.

- `Path.normalize()`: syntactic processing; does not require existence.
- `Path.toAbsolutePath()`: produces an absolute path; does not resolve symlinks.
- `Path.toRealPath()`: performs a filesystem operation to obtain the real path; requires existence by default and resolves symbolic links; may throw `IOException`.
- `File.getCanonicalPath()`: legacy API with canonical pathname semantics; not completely identical to `toRealPath()`, especially for nonexistent paths.

**Choice:** If the goal is to generate relative path names for source/project files, consider normalize. If you must determine the real path of an **existing file**, consider `toRealPath()` and handle errors/concurrent changes.

## 6. `resolve()` and `relativize()`: two-way relationship

### 6.1. What does `resolve` do?

`base.resolve(other)` appends `other` onto `base` when `other` is relative. If `other` is absolute, under the default provider's `Path.resolve` contract the result is typically `other` itself; on other providers, details may depend on the implementation. Never rely on `resolve` to silently confirm that `other` is safe or inside `base`.

Purely lexical example:

```java
Path base = Path.of("app", "src");
Path other = Path.of("..", "assets", "logo.png");
Path combined = base.resolve(other).normalize();
// app/assets/logo.png
```

`resolve` **does not read/write files**, and joining paths does not automatically create directories.

### 6.2. Checking the reconstruction relationship

For two compatible, normalized paths, you can verify:

```java
Path relative = base.relativize(target);
Path reconstructed = base.resolve(relative).normalize();
boolean matches = reconstructed.equals(target.normalize());
```

In the standard scenario of the example, `matches` is `true`. This is a useful tool to catch **reversed-direction** bugs or incorrect `..` handling.

However, this is an identity check on **lexical paths**. It does not prove the file exists, check permissions, compare inode/file identity, or prevent symlink changes. With complex roots, unnormalized paths, and differing providers, check the provider's contract rather than extrapolating a single formula for every case.

### 6.3. `relativize` is not `resolve` with a minus sign

Do not treat `relativize` as "path subtraction" based on `String.replace`. Paths have root systems, separators, filesystem providers, and potentially special components. `Path.relativize` computes by Path structure, whereas string slicing discards that information.

## 7. Relative and absolute: a safe, maintainable workflow

In an application, before calling `relativize`, establish the **root context of both paths**:

1. If both are relative and interpreted from the **same working directory/anchor**, you can normalize and then relativize.
2. If both are absolute, verify they belong to compatible roots/providers and relativize within that coordinate system.
3. If one is absolute and one is relative, **do not guess**. Determine whether the relative path is actually interpreted from the working directory, a project root, or a specific parent directory, and convert *deliberately*.
4. If a common frame of reference cannot be established, handle it with an error message, retain the absolute path, or adjust the input data.
5. If a Path belongs to a special provider (ZIP, virtual filesystem), ensure both share the appropriate provider/filesystem rather than converting through `toString()` to join manually.

### 7.1. When anchoring to an application root is needed

Suppose a project configuration uses relative paths under a defined root; resolve both **from that same root**:

```java
// Illustration; projectRoot is an absolute Path provided by the application.
Path base = projectRoot.resolve("src").normalize();
Path target = projectRoot.resolve("assets/logo.png").normalize();
Path relative = base.relativize(target);
```

This example **is not a standalone program** because `projectRoot` is not declared. In a real application, `projectRoot` should be clearly determined from configuration/trusted paths. If `projectRoot` is only relative, standardize on converting it to absolute before joining.

### 7.2. Do not infer the working directory from source file location

A common mistake: a program uses `Path.of("src")` and assumes that is the `src` directory in the repository. When run from an IDE, service, script, or container, the working directory can be different. `toAbsolutePath()` only resolves against the process context; it does not know which module the developer "intended to use".

If an application needs paths independent of the working directory, use absolute configuration or explicitly determine the root at application startup.

## 8. Roots and filesystem providers in real systems

### 8.1. Default FileSystem

`Path.of(...)` typically creates paths belonging to the default provider of the current operating system. On Unix systems, absolute paths typically begin with `/`. On Windows, roots can be drive roots or UNC roots.

For two absolute paths with the same root, relative calculation makes sense. For two drives without a shared root, a pure `..` relative path connecting them may not exist.

When checking compatibility, you can inspect:

```java
// Illustration with Paths already existing in code.
boolean sameFileSystem = base.getFileSystem()
        .equals(target.getFileSystem());
boolean sameKind = base.isAbsolute() == target.isAbsolute();
```

These two booleans are **initial indicators**, not a replacement for the `relativize` contract. For instance, on Windows under the same default FileSystem there can still be two different drive roots. When actually computing, call `relativize` and handle `IllegalArgumentException` if inputs are incompatible.

### 8.2. Dedicated providers such as ZIP filesystem

A Path inside a provider-managed ZIP filesystem must not be treated as a child of a default directory Path merely because both paths contain `/docs`. A provider may define different root syntax, comparison behavior, and relativization rules.

Do not use `Path.of(zipPath.toString())` to "coerce" a ZIP path into the default filesystem and assume it still references the same file. That only creates **a new Path with the same or similar string**, without preserving the original filesystem semantics.

If an application needs to copy data between two providers, use the open/read/write APIs on each provider and specify targets separately, rather than expecting `relativize` to bridge two distinct filesystem trees.

### 8.3. Proper exception handling

The `relativize` contract may throw:

- `IllegalArgumentException` when the two paths cannot be relativized, e.g., mixed absolute/relative or incompatible roots.
- `ProviderMismatchException` when the Paths are managed by incompatible providers; this is a subtype of `IllegalArgumentException` in Java.
- `NullPointerException` if `null` is passed to the method.

Note that `Path.relativize` does not declare `throws IOException` because it primarily manipulates Path structure, unlike `toRealPath()` which may access the filesystem.

If you need a specific message for provider mismatch, catch `ProviderMismatchException` **before** `IllegalArgumentException` in multi-catch branches; do not catch them in reverse order where the subclass would already be caught by the superclass.

Do not write `catch (Exception ignored)` and return a fake "relative" string to hide that the two frames of reference are incompatible.

## 9. Common pitfalls and fixes

### 9.1. Reversing base and target

Wrong direction: wanting the path from `src` to `tests` but calling `tests.relativize(src)`. Read the phrase "**from the receiver object to the argument**". In code, name variables clearly as `from`/`to`:

```java
Path from = Path.of("project", "src");
Path to = Path.of("project", "tests");
Path navigation = from.relativize(to); // ../tests
```

### 9.2. Using one absolute and one relative path

Cannot succeed under the default contract. Before converting, you must know where the relative path is anchored. `toAbsolutePath()` is only one approach based on the working directory; it is not the right choice for all data.

### 9.3. Expecting platform-independent string output

`relative.toString()` may use `/` or `\`. Compare `Path`/component names rather than hard-coding separators in cross-platform tests.

### 9.4. Forgetting to handle `..` in the input itself

With paths containing `.` / `..`, results may be hard to read or unexpected. When the goal is a lexical computation, consider `normalize()` before computing. Do not use normalize as proof that paths point to the same file if symlinks may exist.

### 9.5. Treating a relative path as proof the file exists

`relativize` does not call `Files.exists()`, create files, or open handles. The target path may not exist. When using the result to read a file, you must still handle `IOException`.

### 9.6. Comparing paths via string prefix

If an application wants to check whether a file lies under a directory, calling `string.startsWith("/data")` is not equivalent to checking path components because `/database` also has the prefix `/data`. After choosing the same filesystem and normalizing appropriately, `candidate.startsWith(root)` on **Path** is a lexical component check, though it still does not account for symlinks or on-disk changes.

### 9.7. Mistaking `relativize` for a security tool

A program can produce a relative path pointing **outside** the root via `..`. A relative result does not mean "access allowed". For user-supplied paths, enforce allowed components, trusted roots, access permissions, symlink policies, and protections against concurrent filesystem modifications.

### 9.8. Treating all paths as belonging to the same provider

Two `Path` instances that look identical when printed may belong to different filesystems. Compare `getFileSystem()`/provider when needed and design explicitly where data is stored.

## 10. Symlinks, `toRealPath()`, and security issues

### 10.1. Lexical route does not equal physical route

Suppose `/project/assets` is a symlink to `/mnt/shared-assets`. `Path.of("/project/src").relativize(Path.of("/project/assets/logo.png"))` computes using `Path` components without following the symlink to ask where the actual target resides.

If you need the relationship between **two genuinely existing files**, you can obtain real paths:

```java
// Illustration: base and target are Paths to existing resources.
Path realBase = base.toRealPath();
Path realTarget = target.toRealPath();
Path navigation = realBase.relativize(realTarget);
```

This approach requires the files/dirs to exist and share a compatible provider/root that can be relativized, and may throw `IOException`. After resolving symlinks, the resulting path may lie outside the original directory tree. `toRealPath()` also accepts `LinkOption.NOFOLLOW_LINKS` if the requirement is *not* to follow links; choose based on your threat model rather than using it as a default ritual.

### 10.2. Check-then-use can suffer from TOCTOU

If another process has permission to modify symlinks/directories after your check, the real path can change before the file is read (time-of-check-to-time-of-use). Therefore, even `toRealPath()` followed by `relativize` **does not lock** the file object.

For high security requirements, use resource-opening APIs with directory/file handle management supported by the provider, filesystem permissions, and consider `SecureDirectoryStream` where supported. Do not attempt to use a purely lexical string/Path calculation to prove no race can occur.

## 11. Checklist for choosing and using properly

| Question | How to decide |
| --- | --- |
| Want the route from A to B? | `A.relativize(B)` |
| Two Paths differ in absolute/relative kind? | Identify the anchor and convert both to a common coordinate system; otherwise report an error |
| Two absolute paths have different roots? | Do not assume a relative route exists; handle `IllegalArgumentException` |
| Two Paths have different providers? | Do not coerce via strings to mix them; handle per filesystem |
| Paths contain `.`/`..`? | Consider normalizing **both** if the goal is syntactic |
| Need to combine base and relative route? | `base.resolve(route)`; normalize if needed |
| Need to verify result in tests? | Compare `Path` components or `resolve(...).normalize()` against normalized target |
| Need to check existence/real resource? | Use `Files`/`toRealPath()`; handle `IOException` |
| Need to prevent escaping outside root? | Design containment + symlink + race controls; do not rely solely on `relativize` |
| Running cross-platform? | Avoid expecting fixed `/` or `\` strings |

## 12. Self-assessment exercises

1. **Basics:** compute `Path.of("a", "b").relativize(Path.of("a", "c", "d.txt"))` and show the resulting components.
2. **Direction:** compute the reverse route. Why does the number of `..` steps differ when base is a path to a file?
3. **Compatibility:** explain why `Path.of("docs").relativize(Path.of("docs").toAbsolutePath())` throws `IllegalArgumentException`.
4. **Identity:** call `p.relativize(p)`, print `toString()`, and comment on the empty path.
5. **Normalize:** given `base = "a/b/../src"`, `target = "a/docs/./intro.md"`, normalize both and relativize; verify `base.normalize().resolve(route).normalize()`.
6. **Windows roots:** why can `C:\work` and `D:\backup` typically not be relativized? Why is stripping the drive letter with substring wrong?
7. **Provider:** state the issue when mixing a Path from a ZIP filesystem with a Path from the default filesystem.
8. **Symlink:** compare the meaning of `normalize()` and `toRealPath()` when an intermediate directory is a symbolic link.
9. **Practice:** write a function returning `Optional<Path>` for a compatible pair of Paths, and returning `Optional.empty()` or a contextual error for incompatible pairs. Catch only relevant errors; do not silently alter roots.
10. **Secure design:** a user supplies a filename to download; explain why `relativize` is not a validation step granting permission to access a root directory.

## 13. Knowledge summary

- **`base.relativize(target)`** constructs a relative path **from base to target**.
- **Compatibility is mandatory:** both relative or both absolute; absolute paths require compatible roots, and both Paths must belong to compatible filesystem/provider environments.
- **`normalize()`** simplifies syntax, **`toAbsolutePath()`** anchors against working context, **`resolve()`** appends relative paths, and **`toRealPath()`** queries the filesystem when a real path is needed.
- `relativize` **does not open files, does not guarantee file existence, does not inspect symlinks for verification**, and is not by itself a path security tool.
- To avoid bugs, verify the **from → to direction**, align the frame of reference, write assertions comparing `Path` objects, and handle incompatible cases explicitly.

**Practical rule:** Choose two `Path`s in the same coordinate system, decide whether you need a lexical calculation or correlation with real resources, and only then use `relativize`. Never replace filesystem checks and protections with a path transformation alone.