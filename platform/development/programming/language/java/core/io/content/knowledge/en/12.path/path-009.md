# Windows and Unix paths, separators, and case sensitivity in Java `Path`

`java.nio.file.Path` represents a **path according to a specific file system (`FileSystem`)**. A string that looks like a valid path on Windows can mean something completely different on Unix/Linux, and vice versa. To write Java I/O that runs across multiple platforms, you must distinguish:

1. **Directory separators** (`/` or `\`) from **path-list entry separators** (`:` or `;`).
2. **Root rules and absolute paths**: `/home/...` on Unix, `C:\...` and `\\server\share\...` on Windows, along with Windows *drive-relative* forms.
3. **Case sensitivity**: depends on the filesystem, volume, directory, and sometimes provider configuration; it cannot be decided solely from `System.getProperty("os.name")`.
4. **Path string versus actual file object**: `Path.equals()` differs in purpose from `Files.isSameFile()`, and `normalize()` does not access the file system.
5. **Safety when joining paths**: handling `..`, symbolic links, filenames from external input, and changes occurring between check and use.

Foundational rule: **join components using `Path.of(...)`/`resolve(...)` instead of manually concatenating `/` or `\` strings**. When working with a path from an OS *other* than the machine running Java, do not hand that raw string to the default filesystem and assume it will be parsed under the source OS's syntax.

## 1. `Path` belongs to a `FileSystem`, not just a `String`

A path can be represented by:

```java
Path path = Path.of("data", "reports", "summary.txt");
```

This is an illustrative snippet requiring `import java.nio.file.Path;`. `Path.of(...)` creates a path on the JVM's **default filesystem**. It does not automatically create a file, does not require the file to exist, and does not open any data streams. The string form returned by `path.toString()` is determined by the filesystem/provider.

The parts of a `Path` typically include:

| Component | Example | Meaning |
| --- | --- | --- |
| Root | `/` on Unix; `C:\` on a Windows drive; `\\server\share\` for UNC | Origin point per filesystem rules |
| Name elements | `data`, `reports`, `summary.txt` | Path components |
| Parent | `data/reports` (written Unix-style) | The path portion before the last name |
| File name | `summary.txt` | The last component, not a filename verified to exist |
| Absolute path | `/home/ana/data/...` or `C:\Users\Ana\data\...` | Has a root per the corresponding filesystem |
| Relative path | `data/reports/summary.txt` | Interpreted relative to the working context |

`getRoot()`, `getParent()`, `getFileName()`, `getNameCount()`, and `isAbsolute()` are path analysis operations, **not queries checking whether a file exists**. For instance, `getFileName()` may return `null` for some root-only paths. A `Path` can also be created by a non-default filesystem, such as a provider-supported ZIP file system; therefore do not assume every `Path` carries local disk naming rules.

### Example 1 — joining paths by component, independent of separator

```java
// PathComponentsDemo.java
import java.io.File;
import java.nio.file.Path;

public class PathComponentsDemo {
    public static void main(String[] args) {
        Path path = Path.of("data", "logs", "app.log");
        Path messy = Path.of("data", ".", "cache", "..", "report.txt");
        Path cleaned = messy.normalize();

        System.out.println("relative=" + !path.isAbsolute());
        System.out.println("nameCount=" + path.getNameCount());
        System.out.println("fileName=" + path.getFileName());
        System.out.println("parentName=" + path.getParent().getFileName());
        System.out.println("joinedCorrectly=" + path.toString().equals(
                "data" + File.separator + "logs"
                        + File.separator + "app.log"));
        System.out.println("cleanedNames=" + cleaned.getNameCount());
        System.out.println("cleanedFileName=" + cleaned.getFileName());
    }
}
```

Compile/run with Java 17+:

```bash
javac PathComponentsDemo.java
java PathComponentsDemo
```

Output on typical Windows or Unix default filesystems:

```text
relative=true
nameCount=3
fileName=app.log
parentName=logs
joinedCorrectly=true
cleanedNames=2
cleanedFileName=report.txt
```

On Windows, `path.toString()` typically uses `data\logs\app.log`; on Unix, it typically uses `data/logs/app.log`. The `joinedCorrectly` check relies on `File.separator` of the current platform itself, so it still yields the same result. `normalize()` simplifies `.` and the `cache/..` component pair using **pure path semantics**, without checking whether `data` or `cache` exists.

### Relative paths do not automatically anchor to the source-code directory

`Path.of("data", "file.txt")` is relative. When an API needs to resolve it into an absolute path, the context is typically **the working directory of the Java process**. Do not assume Java automatically uses the folder holding `.java` files, the IDE project folder, or the `.class` location. IDEs, CI runners, containers, and system services may launch the application with different working directories.

Use `toAbsolutePath()` if you want to inspect the absolute path under the default filesystem; if you want to explicitly fix the application's data root, pass a chosen `Path base` and call `base.resolve(...)`.

## 2. Directory separators on Windows and Unix

### Unix/Linux and many POSIX systems

Typical Unix paths use **`/`**:

```text
/etc/hosts
/home/ana/projects/report.txt
var/log/app.log
```

- Leading `/` usually indicates the **root**.
- `var/log/app.log` without a leading `/` is a **relative** path.
- The backslash `\` **is not** a directory separator on typical Unix filesystems; it can be a character inside a filename (even though shells often use backslash as an escape character when entering commands).
- Filenames on Unix generally cannot contain `/` or the NUL character. Other rules (Unicode, name length, normalization) depend on the file system/provider.

### Windows

Windows typically displays **`\`**:

```text
C:\Users\Ana\report.txt
D:\data\log.txt
\\server\share\reports\summary.txt
```

- `C:\Users\Ana\report.txt` has drive `C:` with root `\`, which is **absolute** in Windows syntax.
- `\\server\share\reports\summary.txt` is a **UNC path** (network path) consisting of server, share, and subsequent components.
- On Java's default Windows filesystem, `/` is generally also accepted as an input separator: `C:/Users/Ana/report.txt`. However, do not generalize this capability to every Windows API, extended-length path, or other providers.
- Windows has path forms that do not carry equivalent meaning: `C:notes.txt` and `C:\notes.txt` **are not the same**.

### Three Windows path forms easily confused

| Form | Interpretation on Windows |
| --- | --- |
| `C:\data\file.txt` | Absolute with root on drive `C:` |
| `C:data\file.txt` | **Drive-relative**: relative to the current working directory associated with drive `C:`, not automatically `C:\data\file.txt` |
| `\data\file.txt` | Root-relative on the **current drive** in Windows context; does not specify an independent drive |
| `data\file.txt` | Purely relative |
| `\\server\share\file.txt` | UNC, root determined by server/share |

Do not handle a `C:folder` path by checking whether it "starts with `C:`" and concluding it is absolute. To know whether it is absolute under the current provider, use `path.isAbsolute()`. Note: if Java runs on Linux, the default provider **does not parse `C:` as a Windows drive**, so `Path.of("C:\\data\\file.txt").isAbsolute()` cannot substitute for checking Windows syntax on another OS.

## 3. Two very different kinds of separators

`java.io.File` provides two groups of constants:

| Constant | Purpose | Common value on Unix | Common value on Windows |
| --- | --- | --- | --- |
| `File.separator` | Separates **directories** within a single path | `/` | `\` |
| `File.separatorChar` | `char` version of `separator` | `/` | `\` |
| `File.pathSeparator` | Separates **multiple paths** in a list, such as classpath | `:` | `;` |
| `File.pathSeparatorChar` | `char` version of `pathSeparator` | `:` | `;` |

Example:

```text
Unix PATH:    /usr/local/bin:/usr/bin:/bin
Windows PATH: C:\Windows\System32;C:\Tools
```

Never use `File.pathSeparator` to join two directories. It is for **lists of multiple path entries**. Conversely, never use `File.separator` to join classpath entries. The values above are **common across platforms**, not a promise that every virtual provider uses the exact rules of the default filesystem.

The preferred API when constructing a path:

```java
Path file = Path.of("documents", "2026", "report.txt");
// Instead of "documents/" + "2026/" + "report.txt".
```

For classpaths handled by the Java launcher, list-separator structure is dictated by the platform. Avoid manipulating classpaths as raw strings if an API exists for that purpose.

### Example 2 — observing separators and path strings

```java
// PathSeparatorsDemo.java
import java.io.File;
import java.nio.file.FileSystems;
import java.nio.file.Path;

public class PathSeparatorsDemo {
    public static void main(String[] args) {
        Path path = Path.of("src", "main", "App.java");

        System.out.println("directorySeparator=" + File.separator);
        System.out.println("pathListSeparator=" + File.pathSeparator);
        System.out.println("defaultFsSeparator="
                + FileSystems.getDefault().getSeparator());
        System.out.println("constructed=" + path);
        System.out.println("nameCount=" + path.getNameCount());
    }
}
```

```bash
javac PathSeparatorsDemo.java
java PathSeparatorsDemo
```

Sample output **on Unix/Linux**:

```text
directorySeparator=/
pathListSeparator=:
defaultFsSeparator=/
constructed=src/main/App.java
nameCount=3
```

Sample output **on Windows**:

```text
directorySeparator=\
pathListSeparator=;
defaultFsSeparator=\
constructed=src\main\App.java
nameCount=3
```

This example illustrates two typical environments. Read values from the actual machine at runtime; do not infer from `os.name` and hard-code logic. `FileSystems.getDefault()` pertains to the default filesystem; a `Path` from another provider may have its own rules, inspectable via `path.getFileSystem().getSeparator()`.

## 4. `\` in Java source code is also an escape character

A common trap: **Java string literal syntax** differs from filesystem syntax.

Valid Java examples when you want to construct strings containing literal `\` characters:

```java
String windowsAbsolute = "C:\\Users\\Ana\\report.txt";
String windowsUnc = "\\\\server\\share\\report.txt";
String unixAbsolute = "/home/ana/report.txt";
```

These are **illustrative snippets**; they must be placed inside a Java class/method to compile. Inside a Java string literal:

- `\\` in **source code** represents **one** backslash in the runtime string.
- `\n` is newline, `\t` is tab, `\r` is carriage return; writing `"C:\new\test.txt"` can accidentally insert real control characters into the string instead of directory segments `new` and `test`.
- `"C:\Users\Ana\report.txt"` does not escape `\U` or `\A` properly and may **fail to compile**.

**Distinguish three different layers:** the string produced by Java compilation, how the filesystem provider interprets those characters, and how a shell (PowerShell/bash) interprets command-line arguments. A backslash can be an escape at one layer while being an ordinary character at another.

### On Unix, backslash does not automatically become a directory separator

If Java code runs on Linux/Unix:

```java
Path foreign = Path.of("C:\\Users\\Ana\\report.txt");
```

This is an **illustrative snippet** with `Path` imported. The default Unix provider does not parse that string as drive `C:` and directories `Users`, `Ana`. It may treat most of the string as **a relative name containing backslashes**.

If an application must process *Windows path text* while running on Unix (for instance, reading a manifest file from a Windows machine), you need an explicit source-syntax model/parser. You cannot assume `Path.of(rawWindowsText)` on Unix performs that task. If you want to operate on real files on the **current machine**, a more resilient approach is to accept **logical path components** and join them with `Path.of(base, segments...)` using the current provider.

Conversely, a Unix path `/var/log/...` has meaning on a Unix filesystem; running it through the Windows default provider does not automatically create a Linux root `/var`.

## 5. Should you manually call `replace("\\", "/")`?

Do not use this replacement as a generic "cross-platform path converter".

- On Unix, `\` can be a **valid filename character**, so replacing it with `/` can turn a filename into multiple directories.
- On Windows, a backslash may belong to a UNC/root prefix or extended syntax; changing it arbitrarily can corrupt semantics in a specific API.
- A file path may appear inside a **URI**, **URL**, **JSON**, **shell command**, or regex. Each layer has its own escape rules; you cannot apply `replace()` across all layers.
- Virtual filesystems such as ZIP and custom providers may have structures different from the default filesystem.

If accepting a *logical path name defined by the application*, structure the input as independent parts, such as `["users", "ana", "report.txt"]`, and then join them. If receiving a path string **from another system**, you need a parser/metadata stating which system it came from, rather than guessing from a separator character.

### Avoid `String.split(File.separator)`

`String.split()` takes a **regex**, not a literal separator. On Windows, `File.separator` is typically `\`, which is an escape character in regex; calling `text.split(File.separator)` directly can throw `PatternSyntaxException`.

For text with a controlled delimiter, `Pattern.quote(delimiter)` solves the **regex escaping** part. However, it does not handle path roots, UNC, strings with multiple separators, or filesystem differences:

```java
// Illustrative snippet for a known data string, not
// a replacement for a real path parser.
String[] tokens = text.split(
        java.util.regex.Pattern.quote(File.separator), -1);
```

When the goal is manipulating real paths on the current provider, use `Path`:

```java
Path parent = path.getParent();
Path leaf = path.getFileName();
```

`Path` parses components according to filesystem rules far better than manually splitting strings by a delimiter.

## 6. Case sensitivity belongs to the filesystem, not just the OS

Two behaviors are commonly encountered:

- **Case-sensitive:** `README.md` and `readme.md` can be **two distinct files**.
- **Case-insensitive, case-preserving:** when a user creates `README.md`, the filesystem may store that casing while looking up `readme.md` still resolves to the same file.

**Common** real-world examples, not universal laws:

| System | Common behavior | Caution required |
| --- | --- | --- |
| Linux + typical ext4 setup | Case-sensitive | Some filesystems/directories are configured differently, e.g., casefolding mechanisms |
| Windows + typical NTFS setup | Usually case-insensitive, case-preserving | Windows/NTFS has cases where behavior varies by directory or configuration; do not assume all volumes behave identically |
| macOS + APFS | May be case-insensitive or case-sensitive depending on volume | Do not infer from `os.name` that it is always one mode |
| Network filesystems, archives, ZIP, virtual providers | Determined by server, provider, and configuration | Do not assume the same rules as the machine running the program |

This affects resource names, build configurations, paths in Git repositories, pathname-keyed caches, filename matching, and security logic. A project creating both `config.json` and `Config.json` may work on a case-sensitive filesystem yet collide when deployed to a case-insensitive filesystem.

### Do not use `equalsIgnoreCase()` to identify the same file

Comparing two strings with `equalsIgnoreCase()` does not accurately model all of a provider's filename mapping rules. Filesystems may also apply Unicode normalization/case-folding rules or special namespaces. On the other hand, two paths with different strings can still point to the same physical object due to symbolic links, hard links, or multiple names for one resource.

There are three distinct questions:

1. **Are two strings identical?** `text1.equals(text2)` answers in terms of Java characters.
2. **Are two `Path` objects equal per provider logic?** `path1.equals(path2)` answers per the `Path`/provider contract; it usually does not access the filesystem and is not a file-identity test.
3. **Do two paths currently point to the same file?** `Files.isSameFile(path1, path2)` checks the file entity through the provider and may throw `IOException`.

Even when `Path.equals(...)` returns `true`, do not treat it as access authorization or proof that the file exists. Two equal `Path`s do not resolve symbolic links, filesystem changes, or access issues.

### Example 3 — observe the runtime environment instead of assuming case sensitivity

```java
// PathCaseDemo.java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class PathCaseDemo {
    public static void main(String[] args) throws Exception {
        Path directory = Files.createTempDirectory("path-case-");
        Path original = directory.resolve("Report.txt");
        Path alternate = directory.resolve("report.txt");
        Path dotted = directory.resolve(".").resolve("Report.txt");

        try {
            Files.writeString(original, "data", StandardCharsets.UTF_8);

            System.out.println("originalExists=" + Files.exists(original));
            System.out.println("sameThroughDot="
                    + Files.isSameFile(original, dotted));

            boolean alternateExists = Files.exists(alternate);
            System.out.println("alternateExists=" + alternateExists);

            if (alternateExists) {
                System.out.println("alternateSameFile="
                        + Files.isSameFile(original, alternate));
            } else {
                System.out.println("alternateSameFile=not-checked");
            }
        } finally {
            Files.deleteIfExists(original);
            Files.deleteIfExists(directory);
        }
    }
}
```

Run with Java 17+:

```bash
javac PathCaseDemo.java
java PathCaseDemo
```

First two lines when file creation operations succeed:

```text
originalExists=true
sameThroughDot=true
```

The `alternateExists` and `alternateSameFile` lines **depend on the filesystem**. On a typical case-sensitive filesystem, you may see:

```text
alternateExists=false
alternateSameFile=not-checked
```

On a typical case-insensitive filesystem, you may see:

```text
alternateExists=true
alternateSameFile=true
```

The results above are **illustrative cases**, not fixed stdout for every Windows/macOS/Linux setup. The test creates **a single file** and queries two spellings; it avoids attempting to create two names simultaneously that might collide on a case-insensitive system.

`Files.isSameFile()` operates on existing objects and may throw `IOException` if a file disappears or cannot be queried. It provides identity information at check time, rather than locking the file to guarantee identity will not change later.

## 7. `Path` operations: `resolve`, `normalize`, `toAbsolutePath`, `toRealPath`

### `resolve(...)`

```java
Path base = Path.of("data");
Path output = base.resolve("reports").resolve("summary.txt");
```

This is an illustrative snippet: `output` is a path joined according to the current provider. **If the argument to `resolve` is absolute**, in many cases the result becomes that absolute path itself instead of remaining under `base`; exact contracts for rooted/drive-relative paths depend on the provider. Never call `base.resolve(userProvidedPath)` and assume the result always stays under base.

### `normalize()`

`normalize()` removes `.` components and `name/..` pairs that can be simplified **syntactically**, without accessing the filesystem. It does not open/inspect symbolic links and does not verify whether files exist.

```text
data/logs/../report.txt
  -> after normalize(): data/report.txt
```

In a path containing symbolic links, dropping `name/..` syntactically can **differ** from traversing the real filesystem. Therefore `normalize()` is neither a complete security check nor a way to find the "true target" of a link.

### `toAbsolutePath()`

Produces an absolute path based on the current filesystem context. It does not automatically resolve targets, open files, or guarantee existence.

### `toRealPath(...)`

Typically requires the path to actually exist and be accessible; the method can throw `IOException` and processes `.`/`..` components and symbolic links according to options. If `LinkOption.NOFOLLOW_LINKS` is passed, link semantics change per contract. `toRealPath()` is useful when you need the actual location supplied by the provider, **but it does not lock that state across subsequent operations**.

| Method | Accesses filesystem? | Can confirm target exists? | Remember |
| --- | --- | --- | --- |
| `normalize()` | No | No | Syntactic transformation; does not resolve symbolic links |
| `toAbsolutePath()` | Not used as an existence check | No | Adds root/working directory context |
| `toRealPath(...)` | Yes | Usually requires target to exist to succeed | May throw IOException; link option matters |
| `Files.exists(path)` | Checks state | Returns boolean when provider can determine it | `false` does not always prove nonexistence |
| `Files.isSameFile(a, b)` | May need to query file identity | Checks identity; may throw IOException | Does not replace permission policies and anti-race controls |

## 8. `startsWith()` and separators: checking component boundaries

A common bug when checking whether a path lies under a root:

```java
String candidate = "/srv/app-data/file.txt";
boolean inside = candidate.startsWith("/srv/app");
```

This is an **illustrative snippet of broken logic**: string comparison can return `true` even though `/srv/app-data` is not a child of `/srv/app`.

`Path.startsWith(Path)` compares by **the provider's path components**, rather than blind character prefixes. For paths of the same kind on the same filesystem, it avoids `app`/`app-data` boundary bugs. However, this step **only checks path relationships under `Path` semantics**; it does not guarantee security against symbolic links, junctions, or races.

### Example 4 — checking *lexical* relationships explicitly

```java
// PathLexicalBoundaryDemo.java
import java.nio.file.Path;

public class PathLexicalBoundaryDemo {
    public static void main(String[] args) {
        Path base = Path.of("workspace", "allowed")
                .toAbsolutePath().normalize();

        Path inside = base.resolve("docs")
                .resolve("..").resolve("readme.txt").normalize();

        Path outside = base.resolve("..")
                .resolve("allowed-backup").resolve("readme.txt").normalize();

        System.out.println("insideLexically=" + inside.startsWith(base));
        System.out.println("outsideLexically=" + outside.startsWith(base));
    }
}
```

Run:

```bash
javac PathLexicalBoundaryDemo.java
java PathLexicalBoundaryDemo
```

Output on typical default Windows/Unix filesystems:

```text
insideLexically=true
outsideLexically=false
```

This is **not** a safety check for untrusted paths in an environment with symbolic links or adversaries modifying the filesystem. It only demonstrates that `Path.startsWith` observes **component boundaries** more accurately than `String.startsWith`.

If an application must restrict access within a directory:

- Decide policy on whether symbolic links/junctions are permitted.
- Establish a trusted root and avoid allowing user-supplied filenames to create out-of-scope absolute paths.
- Do not treat `normalize().startsWith(root)` as sufficient validation in a contended environment.
- Consider APIs operating relative to directory handles, `SecureDirectoryStream` when supported by the provider, options not to follow symbolic links, and OS permission policies.
- Handle errors on actual open/read/write calls, rather than checking and trusting state won't change (**TOCTOU: time-of-check to time-of-use**).

## 9. Filename rules can also differ

Beyond separators and letter case, filesystems also differ on naming rules:

- Windows typically restricts certain characters in filename components (such as `<>:"/\|?*`), along with reserved device names or special rules; configuration/APIs may alter some restrictions.
- Unix/Linux typically disallows `/` and NUL in element names; characters like `:` or `\` may be valid filename characters.
- Length limits, trailing spaces, trailing dots, Unicode normalization, and equivalent names may be handled differently by providers and platforms.
- A name accepted when creating a `Path` does not guarantee the file **can be created**: `Files.createFile(...)` may still fail due to permissions, policy, or filesystem limits.

If filenames come from users or external systems, do not write a generic "character replacement table" assuming it will be valid on every filesystem. Define application scope, normalize **logical names** at the application layer, restrict empty/`..` components when needed, and let actual operations report errors via exceptions. `InvalidPathException` may appear immediately when parsing a string into a `Path`; `IOException` appears when I/O operations fail.

A relatively portable application convention is simple naming with ASCII letters/digits, hyphens, and underscores, though that is merely an **application-chosen convention**, not the sole valid character set of every filesystem. You must also handle name collisions if deploying onto a case-insensitive system.

## 10. Scenarios in development and deployment

### 10.1. Project runs on a personal machine but fails in CI

A developer machine may have a case-insensitive filesystem, whereas a Linux runner typically uses a case-sensitive filesystem. The line of code:

```java
Path config = Path.of("config", "Settings.json");
```

May work locally when the actual file is named `settings.json`, yet fail when deployed to a case-sensitive environment. The fix is to **align the exact spelling of filenames in code/config and packaged data**, rather than using `equalsIgnoreCase()` to hunt for look-alike files.

### 10.2. Builds or scripts manually concatenating separators

```java
// Approach to avoid:
String location = root + "\\" + "data" + "\\" + "result.txt";
```

The snippet above assumes a `root` variable exists. It bakes in a Windows assumption and can create filenames containing `\` on Unix. Use `Path base = Path.of(root); Path location = base.resolve("data").resolve("result.txt");`, then pass the `Path` to `Files`/the corresponding API.

### 10.3. File paths in URLs differ from OS file paths

URLs and URIs use their own syntax. Do not take a Windows path `C:\data\a.txt` and manually prepend `"file://" + path`: backslashes, spaces, and special characters must obey URI syntax. Once you have a `Path`, use `path.toUri()` if you need a `file:` URI; in the reverse direction, use the provider-appropriate URI-to-`Path` API. **Do not** use a URI path string directly as a local path without converting through the API.

### 10.4. Symbolic links and case sensitivity in caches

A cache keyed on `Path.toString()` can create multiple keys for the same file or erroneously merge different files when compared improperly. If a cache depends on actual object identity, consider file attributes, `Files.isSameFile`, `fileKey()` when supported by the provider, and cache lifecycle boundaries. Do not claim a single string normalization method always maps 1:1 to physical files across all systems.

### 10.5. Comparing roots across different filesystems

Two `Path`s originating from different providers do not necessarily compare/resolve like paths from the same provider. Some operations may throw `ProviderMismatchException`. Use the `Path`'s own provider (`path.getFileSystem()`) when compatible operations are required; do not try to mix a ZIP `Path` with a default `Path` assuming a single global separator.

## 11. Common mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Always manually concatenating `"/"` or `"\\"` | Path incompatible with provider/OS | `Path.of(segments...)`, `resolve(...)` |
| Confusing `File.pathSeparator` with `File.separator` | Using `;`/`:` between directories or `\`/`/` to join classpath | Clearly distinguish directory separator from path-list separator |
| Passing `"C:\\foo\\bar"` to `Path.of` on Unix expecting a Windows path | Wrong root, wrong components | Use provider/syntax matching the data source |
| Treating `C:foo` as an absolute Windows path | Current directory of that drive can affect the result | Distinguish drive-relative from drive-rooted |
| Writing `String.split(File.separator)` | Can fail regex parsing on Windows | Prefer `Path`, or `Pattern.quote` for simple text |
| Relying on `os.name` to infer case-sensitivity | Wrong for volumes/directories with different settings | Check per filesystem and handle actual existence/operations |
| Using `equalsIgnoreCase()` to identify the same file | Wrongly merges or still misses aliases/symlinks | Understand `Path.equals`; use `Files.isSameFile` if identity is needed |
| Thinking `normalize()` resolves symbolic links | May target the wrong file entity | Distinguish lexical normalization from `toRealPath()` |
| Using `String.startsWith(base)` to check child paths | A name like `app-data` looks like a child of `app` | `Path.startsWith` for components, plus additional security measures |
| Forgetting to check absolute RHS when calling `resolve` | Input may override the intended root | Constrain input and validate path semantics |
| Only calling `Files.exists()` before opening | File/permissions may change while waiting | Catch `IOException` on actual operations; avoid TOCTOU |
| Assuming the real path always stays constant | Symbolic links, mounts, or renames can change it | Consider handles and appropriate protective mechanisms |

## 12. Self-check questions

**Question 1.** How do `File.separator` and `File.pathSeparator` differ?

**Answer:** `separator` separates **directories within a single path**; `pathSeparator` separates **multiple paths in a list** such as PATH/classpath. Typically `/` and `:` on Unix; `\` and `;` on Windows.

**Question 2.** Does `Path.of("data", "logs", "app.log")` require choosing `/` or `\` manually?

**Answer:** No. The default filesystem/provider handles the components and path formatting.

**Question 3.** On Windows, is `C:notes.txt` the same as `C:\notes.txt`?

**Answer:** No. The first form is **drive-relative**; the second has a root on drive `C:`.

**Question 4.** Running on Unix, does `Path.of("C:\\work\\note.txt")` automatically parse as a Windows root?

**Answer:** No. The default Unix provider does not interpret Windows drive syntax in the native Windows filesystem sense.

**Question 5.** Are `Readme.txt` and `README.txt` always two different files?

**Answer:** No. It depends on the filesystem, volume/directory, and case-sensitivity configuration. You also cannot guess reliably from `os.name` alone.

**Question 6.** Why is `Path.equals()` not a check for whether two paths point to the same file?

**Answer:** It compares path objects according to provider rules without necessarily accessing the filesystem. `Files.isSameFile()` is designed for the current file-identity question and may throw `IOException`.

**Question 7.** What is the fundamental difference between `normalize()` and `toRealPath()`?

**Answer:** `normalize()` only transforms syntax; `toRealPath()` queries the filesystem, resolves the real path according to options, and may throw `IOException`.

**Question 8.** Is `normalizedCandidate.startsWith(normalizedRoot)` enough to guarantee a user cannot access outside the root directory?

**Answer:** No. It is useful for **lexical** checks, but does not fully handle symbolic links, junctions, concurrent changes, and access policies. You need source control and appropriate I/O/security mechanisms.

**Question 9.** Why can `String.split(File.separator)` fail on Windows?

**Answer:** `split` uses **regex**, where `\` is an escape character; the `\` separator cannot be used as a regex literal without proper quoting. For real Paths, use the `Path` API instead of splitting strings.

**Question 10.** When you need to create a `file:` URI from a `Path`, should you manually concatenate `"file://"` with `Path.toString()`?

**Answer:** No. Use `path.toUri()` to convert via the API, avoiding escaping and URI syntax bugs.

**Remember:** `Path` is an **object belonging to a filesystem/provider**, not an arbitrary delimiter-separated string. Join names with `Path.of(...)`/`resolve(...)`, distinguish `/`, `\`, `:`, and `;`, do not confuse Windows drive-relative with absolute, and do not assume every filesystem shares the same case sensitivity. Distinguish **string comparison**, **Path comparison**, and **real file identity**, and remember that path normalization does not replace filesystem access protection.