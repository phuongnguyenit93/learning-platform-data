# Path.normalize() only handles path syntax

## 1. Why is it necessary to understand normalize() properly?

In Java NIO.2, `java.nio.file.Path` represents a **path** to a location in a file system. A path may contain normal name parts along with special components such as `.` (current directory) and `..` (parent directory). The `Path.normalize()` method helps eliminate redundant components according to **path syntax rules**.

Most important point:

> **`Path.normalize()` is a syntactic transformation from one Path object to another Path object; it does not open files, query file existence, check permissions, or verify where symbolic links point.**

Relative path example:

```text
Input:      data/reports/../images/./logo.png
            └───────┬──────┘       │
                  reports/..        .
                   removed       removed
Result:     data/images/logo.png
```

If we only need to clean up the path representation for syntactic operations, `normalize()` is very useful. However, if we want to know whether two paths actually point to the **same file**, where the real target directory is, or whether a path lies safely inside an allowed directory, other APIs and measures must be used.

Within the same Java I/O module, distinguish three tasks:

1. **Lexical normalization:** normalizing name components in `Path` with `normalize()`.
2. **Absolute path conversion:** creating an absolute representation with `toAbsolutePath()`.
3. **Filesystem resolution:** accessing the file system to determine the real path, existence, and links, such as `toRealPath()` or `Files.isSameFile()`.

These are three different meanings even though they often appear close together in code.

## 2. Path is a path representation

`Path` is an interface in `java.nio.file`, commonly created with `Path.of(...)`. A `Path` can:

- Be **relative**: `docs/manual.txt`.
- Be **absolute**: e.g., `/var/data/manual.txt` on Unix systems or a path with an appropriate drive designator on Windows.
- Have separators and characteristics determined by the **filesystem provider**.
- Contain name elements such as `docs`, `.`, `..`, `manual.txt`.

Pure `Path` operations such as `resolve()`, `getFileName()`, `getParent()`, `startsWith()`, `endsWith()`, `relativize()`, and `normalize()` can be performed on the path representation. No corresponding file needs to exist in order to call `normalize()`.

Example:

```java
Path path = Path.of("data", "reports", "..", "images", ".", "logo.png");
Path normalized = path.normalize();
```

The snippet needs `import java.nio.file.Path;`. `normalized` has name elements `data`, `images`, `logo.png`. The string form when printed may use `/` or `\\` depending on the provider and operating system, so tests should compare **`Path` with `Path`** rather than expecting a Unix path literal on Windows.

## 3. What exactly does normalize() handle?

According to the `Path.normalize()` contract in Java, the result removes redundant name elements such as `.` and `name/..` pairs that can cancel out syntactically. A few rules:

- A `.` component is generally removed.
- A normal name component immediately preceding `..` can be cancelled out together with `..`.
- A `..` at the beginning of a relative path with no preceding name to cancel is generally **retained**.
- The root portion of an absolute path is preserved according to provider rules; encountering `..` right next to the root does not mean you can go up infinitely.
- The result remains a `Path` under the same filesystem provider; the method is not required to return the exact same object instance.
- Calling `normalize()` on the result again does not change the already-normalized representation (idempotent in value).

A few **syntactic** examples with `/` for readability, not a claim that every OS prints the same separator:

| Input path | After normalize | Meaning |
| --- | --- | --- |
| `a/./b` | `a/b` | Drop `.` |
| `a/x/../b` | `a/b` | Cancel `x/..` pair |
| `a/b/../../c` | `c` | Cancel two name levels |
| `../a/./b` | `../a/b` | Keep leading `..` on relative path |
| `a/../../b` | `../b` | Only one `a/..` pair can cancel |
| `a/b` | `a/b` | Already clean, no change needed |

**Do not equate syntactic simplification with the real traversal on disk.** When encountering symbolic links or special filesystem characteristics, removing a `name/..` pair can change the **physical file** the path resolves to.

### What normalize() does NOT do

`normalize()` does **not**:

- Check `Files.exists(path)`.
- Open files or read file contents.
- Check read/write permissions.
- Follow symbolic links to find the real target.
- Automatically turn a relative path into an absolute one.
- Prove that two different `Path`s point to the same inode/file.
- Reliably detect traversal attacks or certify user input as safe.
- Guarantee that data is "canonicalized" against the current filesystem state.
- Create directories, delete files, or change the working directory.

Only certain `Path` methods such as `toRealPath()` need to access the file system and may throw `IOException`.

## 4. Runnable Java 17 example: purely syntactic normalize

This program does not create or read any files. The output intentionally relies on `Path.equals` and name element counts to avoid depending on separators across Windows/Unix.

**File `NormalizeBasics.java`:**

```java
import java.nio.file.Path;

public class NormalizeBasics {
    public static void main(String[] args) {
        Path original = Path.of(
                "data", "reports", "..", "images", ".", "logo.png");
        Path expected = Path.of("data", "images", "logo.png");
        Path normalized = original.normalize();

        System.out.println("Original names: " + original.getNameCount());
        System.out.println("Normalized names: " + normalized.getNameCount());
        System.out.println("Expected path: " + normalized.equals(expected));
        System.out.println("Still relative: " + !normalized.isAbsolute());
        System.out.println("Idempotent: "
                + normalized.normalize().equals(normalized));

        Path leadingParent = Path.of("a", "..", "..", "b").normalize();
        System.out.println("Leading .. retained: "
                + leadingParent.equals(Path.of("..", "b")));
    }
}
```

Compile/run with JDK 17+:

```bash
javac NormalizeBasics.java
java NormalizeBasics
```

**Exact stdout:**

```text
Original names: 6
Normalized names: 3
Expected path: true
Still relative: true
Idempotent: true
Leading .. retained: true
```

The code does not call `Files.exists`, `Files.readString`, or `Files.newInputStream`. Even if `data/images/logo.png` does not exist at all, `normalize()` is still valid. This demonstrates that **the transformation relies solely on path components**, without needing to check the target on disk.

### Two points to remember in the example

1. `original.getNameCount()` counts the elements present in the Path, including `..` and `.`, so it differs from the element count of `normalized`.
2. `Path.equals` compares Path representations according to the filesystem provider and its rules; it does not guarantee conclusions about **two physical files** when links or multiple naming forms exist.

## 5. Path.normalize(), toAbsolutePath(), and toRealPath() differ

These three methods are very easy to conflate:

| Method | Reads filesystem info? | Result/meaning |
| --- | --- | --- |
| `path.normalize()` | Not needed | Simplifies syntactic components such as `.`, `name/..` |
| `path.toAbsolutePath()` | Converts to an absolute representation per provider; does not mean checking file existence | An absolute `Path`, which may still contain components needing normalization |
| `path.toRealPath()` | Yes, queries the filesystem | An absolute, real path resolved against filesystem state (following links by default) and may throw `IOException` |

Read the provider's contract; on the default filesystem, `toAbsolutePath()` typically uses the working directory to convert relative paths. However, this method is **not synonymous** with `toRealPath()`, and does not guarantee the file exists.

Two common expressions:

```java
Path absoluteAndLexical = path.toAbsolutePath().normalize();
Path real = path.toRealPath();
```

This is an **illustrative snippet** with `Path path` and `IOException` handling. The first expression produces an absolute path with redundant components removed syntactically; the second accesses the filesystem to find the real path.

**Do not replace `toRealPath()` with `toAbsolutePath().normalize()`** if the algorithm depends on symbolic links, file identity, or a resolved target location. The two expressions can return different Paths even when starting from the same input.

### toRealPath and LinkOption.NOFOLLOW_LINKS

Normally `toRealPath()` resolves symbolic links and requires the path to actually exist. A variant:

```java
Path result = path.toRealPath(LinkOption.NOFOLLOW_LINKS);
```

This is an illustrative snippet requiring `java.nio.file.LinkOption`, `Path`, and `IOException` handling. When passing `NOFOLLOW_LINKS`, symbolic link handling changes per the API contract, so `result` should not be interpreted as having the same meaning as default `path.toRealPath()`. Even with the option not to follow links, the call remains a **filesystem operation**, unlike `normalize()`.

## 6. Practical example: file existence is only required for toRealPath

A short program can create a temporary file and then compare the syntactic representation with the actual result:

**File `RealPathDemo.java`:**

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class RealPathDemo {
    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("normalize-demo-");
        Path child = directory.resolve("child");
        Path file = directory.resolve("sample.txt");

        try {
            Files.createDirectory(child);
            Files.writeString(file, "ok", StandardCharsets.UTF_8);

            Path withDots = child.resolve("..").resolve("sample.txt");
            Path lexical = withDots.normalize();

            System.out.println("Lexical equals file path: "
                    + lexical.equals(file));
            System.out.println("Real paths equal: "
                    + withDots.toRealPath().equals(file.toRealPath()));
            System.out.println("Same file: "
                    + Files.isSameFile(withDots, file));
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(child);
            Files.deleteIfExists(directory);
        }
    }
}
```

Compile/run:

```bash
javac RealPathDemo.java
java RealPathDemo
```

**Stdout when temp files are created/deleted successfully with no concurrent modifications:**

```text
Lexical equals file path: true
Real paths equal: true
Same file: true
```

In the example, `child` is a real directory, and `..` normally points back to `directory`, so all three comparisons are true. However, these are conditions **created and controlled by the program**. With a symbolic link component, the results can differ, and `normalize()` may not preserve path meaning for actual access.

Do not use `Files.exists()` and treat it as proof the file will continue to exist until read: the filesystem can be modified between check time and use time (**TOCTOU** — time of check to time of use).

## 7. Biggest risk: symbolic links make lexical normalize differ from reality

Suppose the file structure is:

```text
/work/
├── data/
│   ├── notes.txt
│   └── alias  -> /shared/reports   (symbolic link)
└── ...
/shared/
├── notes.txt
└── reports/
```

Consider the path:

```text
/work/data/alias/../notes.txt
```

**Purely syntactic simplification** with `normalize()` removes the `alias/..` pair, producing:

```text
/work/data/notes.txt
```

However, **physical resolution** when the operating system traverses `alias` (pointing to `/shared/reports`) can cause `..` to move up to the parent directory of the symlink target and point to:

```text
/shared/notes.txt
```

Thus, depending on filesystem state and how path resolution executes, the path before and after `normalize()` can **point to two different files**.

This is why the `Path.normalize()` documentation warns: eliminating `name/..` can change the file located if `name` is a symbolic link. **Do not use `normalize()` as proof that the intended file was accessed.**

### Another issue: symbolic links are not static data

Even right after calling `toRealPath()` and checking the result, another actor with permission to modify the directory tree can **swap the symbolic link** before the subsequent open-file call. That is a race condition. For high-security systems, the design must enforce access permissions at the filesystem level, use directory-handle-bound operations, or use an equivalent mechanism rather than only checking a Path string and reopening by name.

## 8. normalize does not mean the path is safe

A common mistake in file-serving systems:

```java
Path candidate = base.resolve(userInput).normalize();
return Files.readAllBytes(candidate);
```

This is an illustrative snippet **without safety checks**, requiring `Path base`, `Path userInput`, `Files`, and `IOException` handling. If `userInput` contains `..` or is an absolute path, `candidate` can point **outside the permitted directory**. `normalize()` merely clarifies that representation rather than blocking access.

Example:

```text
base:        /srv/app/public
userInput:   ../private/secret.txt
resolve:     /srv/app/public/../private/secret.txt
normalize:   /srv/app/private/secret.txt
```

The result has removed `..`, yet it is still **outside** `/srv/app/public`.

**Important:** with `Path.resolve(other)`, if `other` is an absolute path per the provider, the result may ignore `base` and use `other` directly. You cannot assume `base.resolve(userInput)` always remains under base.

### A syntactic check (use only in appropriate situations)

```java
Path normalizedBase = base.toAbsolutePath().normalize();
Path candidate = normalizedBase.resolve(userInput).normalize();

if (!candidate.startsWith(normalizedBase)) {
    throw new SecurityException("Path escapes permitted directory");
}
```

This is a snippet **illustrating lexical containment**. It checks whether `candidate` lies under `base` at the Path-component level after syntactic simplification. However, **it does not prevent a symbolic link inside base from pointing outside**, and it does not defend against races when directories/files are modified between checking and opening.

Depending on the application, you also need:

- Validating the type/properties of acceptable user input.
- Verifying real root and real candidate via the filesystem when the target already exists.
- Taking care if the new target **does not yet exist** because `toRealPath()` on the target cannot be used yet; you may need to verify the real parent and apply a safe file-creation mechanism.
- Using strict filesystem permissions, sandboxes/containers, and directory-handle-based operations when race protection is required.
- Designing an explicit symbolic link policy (allow, forbid, or allow only within a specific directory tree).

**`normalize()` is a useful step for handling syntax, not an access control system.**

## 9. startsWith(Path) differs from String.startsWith

A common security bug is using:

```java
candidate.toString().startsWith(base.toString())
```

This is a **character prefix** comparison, so `/data/public2` also starts with `/data/public` even though it is a different directory.

`Path.startsWith(Path)` compares **the path's name elements** according to the provider; it avoids equating a text prefix with an actual Path ancestor. However, as noted, it still examines only the Path representation and **does not resolve symbolic links**.

### Runnable Java 17 example: misleading string prefixes

**File `PathPrefixDemo.java`:**

```java
import java.nio.file.Path;

public class PathPrefixDemo {
    public static void main(String[] args) {
        Path base = Path.of("public").toAbsolutePath().normalize();
        Path sibling = base.resolveSibling("public-backup")
                .resolve("config.txt").normalize();

        System.out.println("String prefix: "
                + sibling.toString().startsWith(base.toString()));
        System.out.println("Path prefix: " + sibling.startsWith(base));

        Path escape = base.resolve("..").resolve("outside.txt").normalize();
        System.out.println("Escaping .. rejected lexically: "
                + !escape.startsWith(base));
    }
}
```

Run:

```bash
javac PathPrefixDemo.java
java PathPrefixDemo
```

**Exact stdout on a typical default filesystem:**

```text
String prefix: true
Path prefix: false
Escaping .. rejected lexically: true
```

The goal is to illustrate two comparison layers: string prefix sees the same prefix `public`, whereas Path prefix recognizes `public-backup` as a different name. Although `Path.startsWith` is more accurate with respect to paths, it does not replace checking **real path and filesystem policy** in security scenarios.

## 10. Comparing paths: equals, normalize, isSameFile, toRealPath

Different APIs answer different questions:

| API | Answers the question |
| --- | --- |
| `a.equals(b)` | Are the two Path objects considered equal in representation per the provider? |
| `a.normalize().equals(b.normalize())` | Are the two representations identical after syntactic simplification? |
| `a.toAbsolutePath().normalize()` | What does the syntactically simplified absolute path look like? |
| `a.toRealPath()` | What is the real path to the currently existing entry according to the filesystem? |
| `Files.isSameFile(a, b)` | Do the two Paths identify the same file at check time according to the filesystem? |

`Files.isSameFile` may throw `IOException`; depending on the filesystem, it can account for symbolic links, hard links, and provider file identity. `Path.equals` alone must not be used to assert that two differently spelled paths are two different files.

Example:

```text
/var/data/current.txt -> /var/data/releases/v2.txt  (symlink)
```

`Path.of("/var/data/current.txt")` and `Path.of("/var/data/releases/v2.txt")` clearly have different name elements, so lexical equality can be `false`. Yet if the symlink currently points to that file, `Files.isSameFile` can be `true`. Choose the API matching the actual question you need answered.

A `Path` can change its physical meaning over time even though the Java object itself does not change, because the filesystem is external state. A check today is not a permanent guarantee.

## 11. resolve, relativize, and normalize: order matters

Path operations can be combined, but the order of transformation must match the goal.

### resolve: joining paths

```java
Path base = Path.of("docs");
Path child = base.resolve("chapters").resolve("..").resolve("intro.md");
Path result = child.normalize(); // docs/intro.md syntactically.
```

`resolve()` joins paths at the provider level. It **does not read the filesystem**. A `..` component remaining after resolve still needs normalize if you want a compact representation.

### relativize: finding the relative path between two Paths

```java
Path a = Path.of("docs", "java");
Path b = Path.of("docs", "images", "logo.png");
Path relative = a.relativize(b);
```

This snippet creates a relative Path from the name parts. On common providers, it can take the form `../images/logo.png`. `relativize` typically requires Paths of compatible form (e.g., both absolute or both relative and on the same provider); otherwise it may throw `IllegalArgumentException`.

**`relativize` also has syntactic semantics**; it does not inspect symlinks or find the "shortest" physical route between two real locations.

### Ordering with toAbsolutePath

In typical applications, `base.toAbsolutePath().normalize().resolve(relative).normalize()` yields a predictable absolute representation. However, if the goal is to identify the real file, `toRealPath()` or a filesystem-aware strategy is what addresses that part.

Do not infer `resolve`, `relativize`, or `normalize` results from raw strings on another OS without accounting for roots, drives, UNC paths, or providers.

## 12. normalize and relative paths with ..

If a relative path begins with `..`, `normalize()` cannot know which parent directory is "right" without context:

```java
Path p = Path.of("..", "data", ".", "info.txt");
Path n = p.normalize();
System.out.println(n.equals(Path.of("..", "data", "info.txt")));
```

The snippet above illustrates the value `true`. The leading `..` is preserved because no normal name component precedes it to cancel out. Attempting to manually strip every `..` from a path can create a path with a **different meaning**, which is not normalization.

Do not address traversal by deleting `..` segments as strings. That approach is error-prone with separators, encodings, providers, and symbolic links. Define clear rules for valid input and access boundaries.

## 13. normalize is unrelated to Unicode normalization

The name `normalize` in `Path.normalize()` can easily be confused with Unicode normalization such as NFC or NFD. These are two **completely different** concepts:

- `Path.normalize()`: simplifies **path structure**, e.g. `a/./b` to `a/b`.
- `java.text.Normalizer.normalize(text, form)`: normalizes **Unicode representations**, e.g. code point sequences with canonical equivalence.

`Path.normalize()` does not convert a name like `café.txt` from one Unicode form to another just because the name contains accents. Filename comparison behavior with Unicode, case sensitivity, and physical normalization also depends on the filesystem/provider.

If you need to manage multilingual filenames, understand the target filesystem characteristics and application conventions; `Path.normalize()` is not a tool to solve all Unicode filename issues.

## 14. normalize does not guarantee safety when operating on files

Real-world situations to watch out for:

### 14.1 File does not exist

`Path.of("missing/../a.txt").normalize()` still produces a simplified Path without throwing `NoSuchFileException` merely because the directories do not exist. Only if `Files.newInputStream` is called later can a filesystem error arise.

### 14.2 Access permissions

`normalize()` does not check permissions. A syntactically valid path may be unreadable due to parent directory permissions, ACLs, sandboxes, or file locks.

### 14.3 Symbolic links and hard links

`normalize()` does not resolve links. Two paths with different representations may point to the same file; or a path may change meaning after a symlink is updated.

### 14.4 Race conditions

Even `toRealPath()`, `Files.exists()`, or `Files.isSameFile()` only reflect state at query time; the filesystem can change afterward. For untrusted input, do not rely solely on a "check then open" pattern to defend against concurrent directory-tree modifications.

### 14.5 Provider and platform differences

`Path` depends on the filesystem provider. Roots, separators, drive letters, UNC paths, case folding, and symbolic link capabilities differ across systems. Code meant to run across platforms should use the Path API rather than manually joining `/` or `\\`. When testing, compare Path objects or properties instead of assuming every machine prints the exact same path string.

### 14.6 Moving and creating new files

If the target does not yet exist, `toRealPath()` may fail. In upload or file-creation workflows, distinguish the already-existing directory portion, write-permission rules, and the possibility of an adversary replacing parents/symlinks. `normalize()` and `startsWith()` alone do not suffice to prevent traversal/races in an adversarial environment.

## 15. One way to check an existing file's location (and its limits)

For an **existing** file, a basic filesystem-aware validation approach:

```java
static Path validateExistingFile(Path permittedRoot, Path request)
        throws IOException {
    Path realRoot = permittedRoot.toRealPath();
    Path realTarget = realRoot.resolve(request).toRealPath();

    if (!realTarget.startsWith(realRoot)) {
        throw new SecurityException("Outside permitted root");
    }
    return realTarget;
}
```

This is an **illustrative method**, requiring `Path` and `IOException`; it is not a complete security protocol. Calling `toRealPath()` resolves the real location and requires the target to exist. `realTarget.startsWith(realRoot)` then compares name elements **on the real path determined at check time**.

However:

- If the resource lies outside root, the method rejects it; if it does not exist or access is denied, `toRealPath()` throws an error.
- If an attacker can swap a symlink between validation and the subsequent open operation, **TOCTOU** can occur.
- If a new file must be created, a nonexistent target cannot be handled directly as-is by this approach.
- If multiple filesystem providers exist, incompatible `Path`s can cause errors during `resolve` or comparison.
- Policies on whether symlinks, mount points, or hard links are allowed must be defined separately according to application requirements.

For high-security tasks, consider operations relative to a directory handle, such as `SecureDirectoryStream` when supported by the provider, and restrict process privileges. **No single `normalize()` call creates a security boundary.**

## 16. Self-check questions

1. Why does `Path.of("a","..","b").normalize()` return a valid Path even when directory `a` does not exist?
2. State the differences between `normalize()`, `toAbsolutePath()`, `toRealPath()`, and `Files.isSameFile()`.
3. Run `NormalizeBasics` on Java 17. Replace `"reports", ".."` with `"reports", "2026", "..", ".."` and predict the name element counts before and after.
4. Write a test proving that `Path.of("..","a").normalize()` still has `..` at the beginning.
5. Sketch a filesystem structure containing a symlink `alias` and explain why the path `alias/../x` might not be equivalent to removing those two components.
6. Run `PathPrefixDemo`, replacing `public-backup` with `public2`; explain why string checking is still misleading.
7. Given input `../private/secret.txt` and root `/srv/app/public`, compute the result of `resolve` and `normalize`. Why cannot that result be called a "safe path"?
8. Create a temporary file, call `toRealPath()`, then try `toRealPath()` on a nonexistent file. Contrast the result with `normalize()`.
9. Design a function accepting a user-supplied path that only permits reading existing files inside root. List the validation steps along with TOCTOU limitations.
10. Explain why `Path.normalize()` is not synonymous with Unicode NFC/NFD and does not fix all multilingual filename issues.
11. Given a relative Path and an absolute Path belonging to the same filesystem, what can happen when calling `relativize` directly?
12. Present a case where `Files.isSameFile(a,b)` returns true while `a.normalize().equals(b.normalize())` is false.

## 17. Common mistakes to avoid

| Mistake | Consequence | Correct approach |
| --- | --- | --- |
| Calling `normalize()` and assuming the file definitely exists | Errors when opening the file | Use appropriate Files APIs and handle `IOException` |
| Treating `normalize()` as a permission check | Access can still be denied | Check at actual operation time; manage exceptions |
| Treating `normalize()` as physical canonical path | Wrong when symlinks exist | Use `toRealPath` when the real path is needed |
| Using `Path.equals` to assert two paths are the same file | May miss symlinks/hard links | Use `Files.isSameFile` when needed |
| Comparing `candidate.toString().startsWith(base.toString())` | `public2` matches prefix `public` | Use `Path.startsWith` for component comparison |
| Using `normalize().startsWith(root)` as absolute access control | Symlinks/races can escape root | Filesystem-aware policy and anti-race mechanisms |
| Treating `toAbsolutePath()` as `toRealPath()` | Does not resolve symlinks and does not prove existence | Choose the right API for the goal |
| Removing all `..` segments via string manipulation | Can alter path meaning and create security bugs | Work with Path and explicit input policies |
| Using `File.separator` to concatenate strings everywhere | Easy to break across providers/platforms | `Path.of`, `resolve`, `getParent` |
| Assuming normalize is like Unicode normalization | Fails to address Unicode issues in filenames | Use dedicated Unicode APIs when genuinely needed |
| Checking a file and assuming state cannot change | TOCTOU | Design safe operations at the filesystem level |
| Normalizing then overwriting a user-supplied file without verifying root | Risk of out-of-scope access | Real validation and access-permission restrictions |

## 18. Key takeaways

**`Path.normalize()` only handles the syntactic structure of a path.** It is useful for eliminating `.`, cancelling `name/..` pairs where possible, and producing a cleaner Path for other operations.

However, normalize **does not** guarantee that the file exists, that access permissions are valid, that the physical path matches intent, or that user input cannot escape an allowed directory. When you need file identity, use `Files.isSameFile` or `toRealPath` per contract; when protecting a storage boundary, account for symbolic links and concurrent modification risks.

**Mental model:** `normalize` answers "how does this path simplify symbolically?", whereas accessing the filesystem is what can answer "where is the actual file and can it be read/written?".

### References

- [Java SE 17: `Path.normalize()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html#normalize()) and [`Path.toRealPath()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html#toRealPath(java.nio.file.LinkOption...)).
- [Java SE 17: `Files.isSameFile()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#isSameFile(java.nio.file.Path,java.nio.file.Path)).
- [Java SE 17: `SecureDirectoryStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/SecureDirectoryStream.html) — an appropriate mechanism for certain directory-handle-based operations when supported by the provider.