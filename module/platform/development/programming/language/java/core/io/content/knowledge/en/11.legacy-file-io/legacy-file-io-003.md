# Absolute Paths, Relative Paths, and Working Directory in Java

## Objectives

In Java I/O, a path such as `data/report.txt` only identifies a real location when the **working directory** or an explicitly specified base directory is known. That is why the same program sometimes reads a file successfully in an IDE but reports file-not-found when run from a terminal, JAR, Gradle, or container.

After this lesson, you will know how to:

- Distinguish **absolute** and **relative** paths, and interpret relative paths based on the working directory.
- Understand `System.getProperty("user.dir")` and why the directory containing `.java`, `.class`, or `.jar` files is not automatically the working directory.
- Use `java.io.File`: `getPath()`, `isAbsolute()`, `getAbsolutePath()`, `getCanonicalPath()`, and existence checks.
- Use `java.nio.file.Path` and `Files` to join paths, normalize, open files, and handle errors.
- Know when to use `toAbsolutePath()`, `normalize()`, `toRealPath()`; avoid confusion with symbolic links and security checks.
- Run Java 17+ examples across multiple operating systems without depending on a specific machine's absolute path.

## 1. Absolute and Relative Paths

A *path* describes the location of a file or directory in a filesystem. **Creating a path object does not mean the file already exists or has been opened.**

- **Absolute path:** carries complete location information from a root defined by the operating system/filesystem. For example, `/opt/demo/data/report.txt` on Linux or `C:\projects\demo\data\report.txt` on Windows.
- **Relative path:** requires a base directory. For example, `data/report.txt`, `reports/2026.txt`, `../config/app.properties`.
- **Working directory:** the directory that the Java process typically uses to interpret relative paths on the default filesystem.

Suppose the working directory is `/home/learner/demo`:

```text
Working directory: /home/learner/demo

Relative path: data/report.txt
Resolved path: /home/learner/demo/data/report.txt

Relative path: ../config/app.properties
After resolving and normalizing:
               /home/learner/config/app.properties
```

A relative file can point to a different place when the program is launched from a different directory. Conversely, an absolute path does not depend on the working directory when determining the address on the corresponding filesystem.

**Absolute does not mean existing:** `Path.of("/opt/demo/missing.txt").isAbsolute()` can be `true` even when the file does not exist. Reading may still encounter `NoSuchFileException` or a permission error.

### Syntactic Differences Across Operating Systems

| Platform/type | Example | Notes |
| --- | --- | --- |
| Unix/Linux/macOS | `/var/log/app.log` | Starts from the root `/`. |
| Unix relative | `./data/input.txt` | The `.` denotes the current directory. |
| Windows with drive letter | `C:\apps\demo\input.txt` | Has a drive and the drive's root. |
| Windows UNC | `\\server\share\input.txt` | Can point to a network share. |
| Windows special | `C:notes.txt` | A relative path in the current context of drive C:, **different** from `C:\notes.txt`. |

Do not conclude absoluteness yourself via `path.startsWith("/")` or by looking for a colon. `C:\data` on Linux may simply be a relative path name containing ordinary characters. Use `File.isAbsolute()` or `Path.isAbsolute()` according to the runtime environment's filesystem.

## 2. Where Does the Working Directory Come From?

The working directory is the context set for the process by the launch environment:

- **Terminal:** the directory you are currently in when invoking `java`, unless the launch method changes it.
- **IDE:** the *Working directory* setting in the Run/Debug Configuration.
- **Gradle/Maven:** depends on the task, plugin, and working directory configured for the running process.
- **Container:** the `WORKDIR` value or working directory defined by the runtime/container.
- **System service / scheduler:** service configuration, not necessarily the directory containing the JAR.

Java commonly exposes the property:

```java
String cwd = System.getProperty("user.dir");
System.out.println(cwd);
```

This is a **snippet** inside a Java method. The result is the path of the runtime environment, so there is no single universal stdout across all machines.

For example, when executing `java -jar /opt/tools/app.jar` from `/home/learner`, the program may have the working directory `/home/learner` even though the JAR resides in `/opt/tools`. In that case:

```text
new File("config/app.properties")
    -> /home/learner/config/app.properties
    (if the working directory is /home/learner)
```

The source code directory, class file directory, classpath, and JAR location are **different concepts from the working directory**.

**Do not change the working directory using `System.setProperty("user.dir", "...")`.** Changing this Java property is not a general, reliable way to change the OS process's current directory and can cause different parts of an application to interpret paths inconsistently. When you want to work relative to a specific directory, store `Path base` and call `base.resolve(...)` explicitly.

## 3. Legacy API: `java.io.File`

`File` represents a pathname to a file or directory; its constructor does not automatically create files or open streams. Important methods:

| Method | Behavior |
| --- | --- |
| `new File("data", "report.txt")` | Creates a path object as a child of the `data` directory. |
| `getPath()` | Returns the current path representation; may be relative. |
| `isAbsolute()` | Checks whether the path is absolute on the current platform. |
| `getAbsolutePath()` | Returns the absolute path form; does not require the file to exist. |
| `getAbsoluteFile()` | Returns a `File` object containing the absolute path. |
| `getCanonicalPath()` | Returns the canonical path per the filesystem; may access the filesystem and throw `IOException`. |
| `getName()` | Name of the last component of the path. |
| `getParentFile()` | Parent directory path represented in the object; may be `null`. |
| `exists()` | Checks existence at the time of the call; does not guarantee subsequent operations will succeed. |
| `isFile()` / `isDirectory()` | Checks the object type, rather than inferring from the file extension. |
| `toPath()` | Converts to the `Path` API. |

### Java 17+ Example: Relative Paths Without a Real File

Save as **`FilePathDemo.java`**:

```java
import java.io.File;
import java.nio.file.Path;

public class FilePathDemo {
    public static void main(String[] args) {
        File relative = new File("data", "report.txt");
        File absolute = relative.getAbsoluteFile();

        System.out.println("relative.isAbsolute = " + relative.isAbsolute());
        System.out.println("absolute.isAbsolute = " + absolute.isAbsolute());
        System.out.println("file name = " + relative.getName());
        System.out.println("parent name = " + relative.getParentFile().getName());

        Path cleaned = Path.of("output", "..", "data", "report.txt")
                .normalize();
        System.out.println("normalized first = " + cleaned.getName(0));
        System.out.println("normalized last = " + cleaned.getFileName());
        System.out.println("normalized absolute = "
                + cleaned.toAbsolutePath().isAbsolute());
    }
}
```

Run:

```bash
javac FilePathDemo.java
java FilePathDemo
```

Result on a typical default file system:

```text
relative.isAbsolute = false
absolute.isAbsolute = true
file name = report.txt
parent name = data
normalized first = data
normalized last = report.txt
normalized absolute = true
```

The values above do not print the full root address, so they do not depend on each machine's working directory name. Creating `File` and `Path` does not require `data/report.txt` or `output` to exist. The `..` segment in `Path` is simplified **lexically** when calling `normalize()`.

## 4. From `File` to `Path` and `Files`

Java NIO.2 provides `java.nio.file.Path` to express paths and `java.nio.file.Files` to perform I/O. In modern Java, prefer this approach for new functionality while still understanding `File` when working with legacy APIs.

| Need | `File` | `Path` / `Files` |
| --- | --- | --- |
| Build path | `new File("a", "b.txt")` | `Path.of("a", "b.txt")` |
| Check absoluteness | `isAbsolute()` | `isAbsolute()` |
| Get absolute path | `getAbsolutePath()` | `toAbsolutePath()` |
| Syntactically normalize `.`, `..` | Use canonical when appropriate | `normalize()` without I/O |
| Resolve path against base | `new File(parent, child)` | `base.resolve(child)` |
| Find relative path from base to target | No direct equivalent API | `base.relativize(target)` if compatible |
| Real path of an existing file | Check existence + canonical as needed | `toRealPath()` |
| Check existence | `exists()` | `Files.exists(path)` |
| Create parent directories | `mkdir()` / `mkdirs()` | `Files.createDirectories(path)` |
| Read/write text | Combined Stream/Reader/Writer | `Files.readString` / `Files.writeString` |
| I/O errors | Many methods return boolean | Most I/O operations throw `IOException` |

### `resolve` and `relativize`

`base.resolve(child)` normally appends a relative `child` onto `base`. If `child` is an **absolute path**, it is not forced to lie beneath `base`; do not use `resolve` as an access-control safeguard.

`base.relativize(target)` finds a relative path from `base` to `target` when the two paths have compatible types/roots. Do not expect this method to access the filesystem or verify that the target exists.

Example:

```java
// Snippet illustrating Path, performing no I/O:
Path base = Path.of("workspace");
Path child = base.resolve("notes").resolve("today.txt");
Path relative = base.relativize(child); // notes/today.txt
```

The displayed separator depends on the operating system; `relativize` and `resolve` work at the path-component level, avoiding manual string concatenation.

### `toAbsolutePath()`, `normalize()`, and `toRealPath()` Are Not the Same

- `toAbsolutePath()`: converts to an absolute path based on the filesystem context; **does not require a real file**.
- `normalize()`: syntactically collapses `.` and `..` components; **does not read the filesystem**.
- `toRealPath()`: by default requires an existing target, verifies and resolves symbolic links according to the provider, and may throw `IOException`.
- `toRealPath(LinkOption.NOFOLLOW_LINKS)`: applies different rules for symbolic links, not following them by default when determining the real path.
- `File.getCanonicalPath()`: normalizes the pathname per file system rules, can resolve symlinks, and can return a canonical path even when the target does not exist yet; **not completely synonymous** with `Path.toRealPath()`.

A path containing `someLink/..` can mean something different after the filesystem resolves symbolic links. `normalize()` simplifies lexically, so it is **not sufficient to verify the actual target that I/O will affect**.

## 5. Java 17+ Example: Creating a File in a Temporary Directory

The example below creates a separate temporary directory, writes a UTF-8 file, verifies `normalize` and `toRealPath`, and then deletes the created items. It does not need to hardcode absolute paths like `C:\temp` or `/tmp`.

Save as **`TemporaryFilePathDemo.java`**:

```java
import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class TemporaryFilePathDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("path-lesson-");
        Path reports = root.resolve("reports");
        Path file = reports.resolve("daily.txt");

        try {
            Files.createDirectories(reports);
            Files.writeString(file, "Xin chao", StandardCharsets.UTF_8);

            Path withDots = root.resolve("reports")
                    .resolve(".")
                    .resolve("..")
                    .resolve("reports")
                    .resolve("daily.txt");

            System.out.println("file exists = " + Files.exists(file));
            System.out.println("regular file = " + Files.isRegularFile(file));
            System.out.println("same normalized path = "
                    + withDots.normalize().equals(file.normalize()));
            System.out.println("real path matches = "
                    + file.toRealPath().equals(withDots.toRealPath()));
            System.out.println("read text = "
                    + Files.readString(file, StandardCharsets.UTF_8));

            File legacy = file.toFile();
            System.out.println("File name = " + legacy.getName());
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(reports);
            Files.deleteIfExists(root);
        }
    }
}
```

Compile and run:

```bash
javac TemporaryFilePathDemo.java
java TemporaryFilePathDemo
```

Expected stdout on a default filesystem that supports creating/deleting files and directories:

```text
file exists = true
regular file = true
same normalized path = true
real path matches = true
read text = Xin chao
File name = daily.txt
```

**Explanation:**

1. `Files.createTempDirectory` returns a temporary directory created by Java according to the runtime configuration.
2. `root.resolve("reports").resolve("daily.txt")` explicitly identifies the file under the base, independent of the working directory once `root` is obtained.
3. `Files.createDirectories` creates parent directories before writing; `Files.writeString` does not automatically create all parent directories.
4. `withDots.normalize()` simplifies the path string, whereas `toRealPath()` accesses the filesystem to verify the real path of the existing file.
5. `Files.deleteIfExists` cleans up created data from the file up to the parent directory. If unexpected data is created concurrently in the directory, deleting the directory may fail; the program does not delete recursively unconditionally.
6. `Path.toFile()` is useful for interacting with legacy APIs on the default filesystem; for some special filesystem providers it may not be supported.

If run in an environment that disallows creating temporary files or encounters permission errors, the operation will throw `IOException`. That is a real-world I/O environment limitation; success should not be faked.

## 6. Why Does the Same Code Produce Different Results from an IDE vs. a Terminal?

Suppose the application writes:

```java
Path config = Path.of("config", "app.properties");
String content = Files.readString(config);
```

This is a **snippet**: it requires importing `Path`/`Files`, handling `IOException`, and having a real file. With the same relative path:

| Working directory | Actual file that will be looked up |
| --- | --- |
| `/home/alice/project` | `/home/alice/project/config/app.properties` |
| `/home/alice` | `/home/alice/config/app.properties` |
| `/srv/app` | `/srv/app/config/app.properties` |

How to diagnose:

1. Print or log `System.getProperty("user.dir")`.
2. Log `config.toAbsolutePath().normalize()` to identify the location being looked up.
3. Verify the working directory configuration in your IDE, build tool, container, or service.
4. Check access permissions and perform the actual file-open operation. `Files.exists` can return `false` if an I/O error occurs or the state cannot be determined; it does not guarantee the next read will succeed.
5. If the application needs a fixed root directory, obtain that value via explicit configuration (CLI argument, environment variable, trusted config file), then `base.resolve(...)`.

### Resources Inside a JAR Are Not Files Next to the JAR

If `defaults.properties` is packaged inside the classpath/JAR, instead of assuming it still exists under `src/main/resources` after building, use a classpath resource:

```java
// Snippet; MyApp is a real class in the application.
try (java.io.InputStream in =
        MyApp.class.getResourceAsStream("/config/defaults.properties")) {
    if (in == null) {
        throw new java.io.FileNotFoundException("resource not found");
    }
    // Read content from in.
}
```

The snippet above is not a standalone program because `MyApp` is just an illustrative class name. In a real application, replace it with an existing class and handle/declare `IOException`. Resources inside a JAR are read through the class loader; source code paths do not automatically become runtime file paths.

## 7. Do Not Concatenate Paths with Hardcoded Separators

Windows-style string concatenation:

```java
// Example that should not be applied cross-platform.
String filePath = base + "\\" + folder + "\\" + filename;
```

is a snippet assuming variables `base`, `folder`, and `filename` already exist. It easily breaks on operating systems using a different separator, easily introduces redundant characters, and handles special path forms poorly.

Instead use:

```java
// Snippet; requires import java.nio.file.Path
Path file = Path.of(base).resolve(folder).resolve(filename);
```

Or use the legacy API:

```java
// Snippet; base and filename are strings provided by the application.
File file = new File(new File(base), filename);
```

Distinguish:

- `File.separator`: separator between **path components**, e.g. forward slash on Unix or backslash on Windows.
- `File.pathSeparator`: separator between **multiple paths in a list**, typically `:` on Unix and `;` on Windows (e.g., classpath).

For files in subdirectories, `Path.of("data", "report.txt")` is usually simpler and less error-prone than string manipulation.

## 8. User-Supplied Paths and Path Traversal

When a path comes from an uploaded filename, URL, archive entry, or CLI input, an external party may supply a path containing `..` or an absolute path. If concatenated without checking, the application may access outside the intended directory:

```text
Allowed directory: /srv/app/uploads
Input:             ../../etc/secret
After lexical resolution:
                   /srv/etc/secret
```

From `/srv/app/uploads`, two upward steps bring the path to `/srv`, then `etc/secret` is appended. The danger is that the path has escaped the `uploads` zone.

To illustrate an **initial syntactic check**, `Path.startsWith(Path)` can be used instead of string comparison. Save as **`LexicalPathGuard.java`**:

```java
import java.nio.file.Path;

public class LexicalPathGuard {
    static Path resolveUnder(Path base, String input) {
        Path supplied = Path.of(input);
        if (supplied.isAbsolute()) {
            throw new IllegalArgumentException("absolute input rejected");
        }

        Path root = base.toAbsolutePath().normalize();
        Path target = root.resolve(supplied).normalize();
        if (!target.startsWith(root)) {
            throw new IllegalArgumentException("outside allowed directory");
        }
        return target;
    }

    public static void main(String[] args) {
        Path base = Path.of("uploads");
        System.out.println(resolveUnder(base, "2026/report.txt")
                .getFileName());

        try {
            resolveUnder(base, "../secret.txt");
        } catch (IllegalArgumentException e) {
            System.out.println("traversal rejected");
        }
    }
}
```

Run:

```bash
javac LexicalPathGuard.java
java LexicalPathGuard
```

Output:

```text
report.txt
traversal rejected
```

**Warning about the example's limitations:** the function above only checks **pathname components** and does not provide sufficient protection if the directory contains symbolic links, junctions/reparse points, mounts, hard links, or entries that change between check time and open time. For sensitive operations, you need to design proper access permissions; check the real path of existing files/parents per policy, handle concurrent modification possibilities, and consider directory-anchored file opening APIs such as `SecureDirectoryStream` where the filesystem provider supports them. Do not promote `normalize().startsWith(root)` as complete path traversal protection.

`Path.startsWith(Path)` checks **path components**, not string prefixes. For example, `/safe/app2` is not a child of `/safe/app` even though the literal strings start the same way.

## 9. Common Misconceptions

1. **Assuming a relative path is measured from the directory containing the `.java` file.** It typically depends on the process's working directory or the base passed to the API.
2. **Assuming `getAbsolutePath()` checks that the file already exists.** It only returns an absolute address; it does not open the file.
3. **Assuming `normalize()` is equivalent to `toRealPath()`.** One simplifies syntax; the other by default verifies an existing file and resolves symlinks.
4. **Assuming `getCanonicalPath()` always requires the file to exist.** It can produce a canonical path even when the target file does not exist, depending on the filesystem.
5. **Assuming `Files.exists() == false` always means the file definitely does not exist.** Permissions may be missing or an error may have occurred; when you need to read, open it and handle exceptions.
6. **Assuming changing `user.dir` changes the cwd for all APIs.** Store and pass a base directory explicitly.
7. **Assuming slash/backslash mean the same thing on all platforms.** Use `Path.of` and `resolve`.
8. **Assuming the path of a resource packaged in a JAR is the path of a file on disk.** Use classpath resource APIs when appropriate.
9. **Assuming checking existence first guarantees the subsequent operation will succeed.** The file may be modified or permissions revoked; you still must handle `IOException`.
10. **Assuming `resolve(userInput)` keeps input within base.** Absolute paths, `..`, and symlinks can break the intended boundary; validation and safe filesystem mechanisms are required.
11. **Assuming a name ending in `.txt` means a regular file.** You must check the entry type rather than relying on the extension.
12. **Not checking ownership and cleanup of temporary files.** For tests/temporary applications, create files in a dedicated temporary directory, handle errors, and delete the files you created.

## 10. Quick Selection Table

| Purpose | API / handling approach |
| --- | --- |
| Check if path is absolute | `File.isAbsolute()` / `Path.isAbsolute()` |
| Display working directory | `System.getProperty("user.dir")` |
| Display expected file read location | `path.toAbsolutePath().normalize()` |
| Locate file under a configured directory | `base.resolve("sub").resolve("file.txt")` |
| Simplify `.` and `..` without I/O | `Path.normalize()` |
| Verify real path of an existing file | `Path.toRealPath()` and handle `IOException` |
| Interoperate with library accepting only `File` | `path.toFile()` if provider supports it |
| Create parent directories before writing | `Files.createDirectories(path.getParent())` when parent is valid |
| Resources bundled with a JAR | Classpath stream instead of paths based on source directory |
| External configuration files | Path/base passed through runtime configuration |
| Untrusted path data | Validation policy + symlink/race controls and filesystem permissions |
| File operation tests | `Files.createTempDirectory` and clean up data in `finally` |

## 11. Self-Check Questions

**Q1.** Running a JAR located at `/opt/apps/app.jar` from `/home/alice`. Where does `new File("data.txt")` usually point?

**Answer:** `/home/alice/data.txt` when the process's working directory is `/home/alice`. The JAR's location does not determine relative paths by default.

**Q2.** Does calling `new File("missing.txt").getAbsolutePath()` create a file?

**Answer:** No. It only gives an absolute address representation.

**Q3.** Does `Path.of("a", "..", "b.txt").normalize()` require file `a` to exist?

**Answer:** No. This is a syntactic pathname transformation and does not access the filesystem.

**Q4.** How does `Path.toRealPath()` differ from `toAbsolutePath()`?

**Answer:** `toAbsolutePath()` builds an absolute path without needing a real file; `toRealPath()` by default checks existence and resolves the real path, and may throw `IOException`.

**Q5.** Can `File.pathSeparator` be used to join directory `data` and file `report.txt`?

**Answer:** No. `pathSeparator` separates a list of multiple paths; use `Path.of("data", "report.txt")` or `File.separator` when a string is truly needed.

**Q6.** Why is `root.resolve(input).normalize().startsWith(root)` not a complete security check?

**Answer:** It only checks path names lexically. Symlinks and concurrent file modifications can still cause the actual I/O operation to point outside the intended area.

**Q7.** From where should a configuration file packaged as a resource inside a JAR be opened?

**Answer:** From a classpath resource API like `getResourceAsStream`, not by default via a `src/main/resources` path relative to the working directory.

## Conclusion

**Relative path + base directory = location the program will look up.** For programs run from an IDE, Gradle, Docker, or a JAR, determine the working directory before diagnosing "file not found" errors. `File` helps understand the legacy API family; `Path`/`Files` makes joining, converting, checking, and manipulating files more transparent.

When you need stable paths, configure an **explicit base path**, use `resolve` to construct child paths, clearly distinguish `toAbsolutePath()`, `normalize()`, and `toRealPath()`, and handle I/O exceptions instead of guessing file existence from path names.