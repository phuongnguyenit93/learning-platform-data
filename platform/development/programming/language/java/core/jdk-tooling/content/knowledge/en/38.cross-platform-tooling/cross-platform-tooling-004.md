# Path separator in Java and cross-platform tooling

In Java, the term “path separator” is often used for two different characters. One character separates the components of a file path, such as `\` on Windows and `/` on Linux/macOS. The other character separates multiple paths in a list such as a classpath or the `PATH` environment variable, such as `;` on Windows and `:` on Linux/macOS.

These two values serve different purposes:

- `File.separator`: the character that separates the components of a single file path.
- `File.pathSeparator`: the character that separates multiple paths in a list.

When writing code to run across multiple operating systems, use `Path`/`Files` to construct and manipulate paths; use `File.pathSeparator` when you must build or parse a path-list string. Do not concatenate strings with hardcoded `\`, `/`, `;`, or `:`.

The Java examples in this article are compatible with Java 17+. The demo was compiled with `javac --release 17 -Xlint:all -Werror` and run on Zulu/OpenJDK 24.0.2 on Windows 11.

## 1. Two types of separators to distinguish

| API | Windows | Linux/macOS | Purpose |
|---|---:|---:|---|
| `File.separator` | `\` | `/` | Separates directories and file names within a path |
| `File.separatorChar` | `\` | `/` | `char` version of the file separator |
| `File.pathSeparator` | `;` | `:` | Separates multiple paths in a list |
| `File.pathSeparatorChar` | `;` | `:` | `char` version of the path-list separator |
| `FileSystems.getDefault().getSeparator()` | `\` | `/` | Separator of the default file system |

Example of a single path:

~~~text
Windows: C:\work\app\config\settings.json
Linux:   /work/app/config/settings.json
macOS:   /Users/dev/work/app/config/settings.json
~~~

Each example above is **a single path**. The separator between directory elements is `File.separator`.

Example of a classpath with two entries:

~~~text
Windows: build\classes;lib\example.jar
Linux:   build/classes:lib/example.jar
macOS:   build/classes:lib/example.jar
~~~

This is **a path list**. The separator between entries is `File.pathSeparator`. Each entry inside the list is still a path with its own file separator.

Do not confuse these two levels. Using `File.separator` to join classpath entries will produce an invalid classpath; using `File.pathSeparator` to join directory names will produce an invalid path.

## 2. `File.separator` and `File.pathSeparator`

Both constants are defined in `java.io.File`:

~~~java
import java.io.File;

public class SeparatorValues {
    public static void main(String[] args) {
        System.out.println("FILE_SEPARATOR=" + File.separator);
        System.out.println("FILE_PATH_SEPARATOR=" + File.pathSeparator);
    }
}
~~~

On Windows, output:

~~~text
FILE_SEPARATOR=\
FILE_PATH_SEPARATOR=;
~~~

On Linux/macOS, output:

~~~text
FILE_SEPARATOR=/
FILE_PATH_SEPARATOR=:
~~~

`File.separator` and `File.pathSeparator` are the values for the default file system that the JVM is running on. They do not represent every filesystem provider that an application might open. For a specific `Path`, you can obtain its provider's separator with:

~~~java
String separator = path.getFileSystem().getSeparator();
~~~

When working with the default filesystem, `File.separator` and `FileSystems.getDefault().getSeparator()` reflect the same type of separator. `File.separatorChar` and `File.pathSeparatorChar` are useful when an API requires a `char` instead of a `String`.

## 3. Use `Path` instead of manual string concatenation

Since Java 11, `Path.of(...)` is the concise way to create a path. Java 7+ has `Paths.get(...)`; both create a `Path` from the default filesystem when using the string-accepting overloads.

~~~java
import java.nio.file.Path;

public class BuildPath {
    public static void main(String[] args) {
        Path source = Path.of("src", "main", "java");
        Path config = Path.of("config").resolve("app.properties");

        System.out.println("SOURCE=" + source);
        System.out.println("CONFIG=" + config);
    }
}
~~~

`Path.of("src", "main", "java")` takes each component separately. The provider will use the appropriate separator for the operating system. On Windows, `toString()` typically prints `src\main\java`; on Linux/macOS, it prints `src/main/java`.

Error-prone approach:

~~~java
String config = "config" + File.separator + "app.properties";
~~~

Recommended approach:

~~~java
Path config = Path.of("config", "app.properties");
~~~

`Path` represents the path structure and provides specialized operations. Only convert to a string at the boundary where you need to pass the path to an API or display it to the user.

## 4. Combine paths using `resolve`, not `+`

`resolve` appends a path or component to the base path:

~~~java
Path project = Path.of("build", "reports");
Path javadoc = project.resolve("javadoc").resolve("index.html");
~~~

The result depends on the filesystem:

~~~text
Windows: build\reports\javadoc\index.html
POSIX:   build/reports/javadoc/index.html
~~~

You can resolve a multi-component path:

~~~java
Path classes = Path.of("build").resolve(Path.of("classes", "java", "main"));
~~~

`resolveSibling` creates a new path in the same parent directory:

~~~java
Path report = Path.of("build", "reports", "summary.html");
Path csv = report.resolveSibling("summary.csv");
~~~

An important caveat: if the argument passed to `resolve` is an absolute path, the result is that absolute path. If a child path comes from external input, never assume it always stays under the root directory.

Example of lexically constraining a child path:

~~~java
Path root = Path.of("data").toAbsolutePath().normalize();
Path candidate = root.resolve(userSuppliedName).normalize();

if (!candidate.startsWith(root)) {
    throw new IllegalArgumentException("Path escapes the data directory");
}
~~~

For sensitive data, lexical checks using `normalize`/`startsWith` are not sufficient if the filesystem has symbolic links. When the file already exists, consider `toRealPath()` and control symlinks according to your application's threat model.

## 5. Relative paths, absolute paths, and normalize

A `Path` can be relative or absolute:

~~~java
Path relative = Path.of("logs", "application.log");
Path absolute = relative.toAbsolutePath();
Path normalized = Path.of("build", "reports", "..", "classes").normalize();

System.out.println(relative);
System.out.println(absolute);
System.out.println(normalized);
~~~

- `toAbsolutePath()` converts a path to an absolute path based on the current working directory.
- `normalize()` removes redundant elements such as `.` and certain `name/..` pairs according to lexical rules.
- `toRealPath()` returns the real path of an existing file, typically resolving symbolic links and filesystem elements.

`normalize()` does not access the filesystem, does not check whether the file exists, and does not resolve symbolic links on its own. `toRealPath()` requires the file or directory to exist; if the path does not exist, the operation may throw an `IOException`.

Example:

~~~java
Path p = Path.of("build", "reports", "..", "classes");
System.out.println(p.normalize());
~~~

Corresponding results:

~~~text
Windows: build\classes
POSIX:   build/classes
~~~

Do not use `normalize()` as the sole defense against path traversal or symlink escape.

## 6. Reading components of a `Path`

A `Path` can be inspected without splitting strings on slashes:

~~~java
Path path = Path.of("src", "main", "java", "com", "example", "Main.java");

System.out.println("FILE_NAME=" + path.getFileName());
System.out.println("PARENT=" + path.getParent());
System.out.println("ROOT=" + path.getRoot());
System.out.println("NAME_COUNT=" + path.getNameCount());
System.out.println("FIRST_NAME=" + path.getName(0));
~~~

For the relative path above, `getRoot()` returns `null`; `getFileName()` returns `Main.java`. For an absolute path, the root depends on the operating system and filesystem, such as `/` on POSIX or `C:\` on Windows.

`getNameCount()` and `getName(i)` access the path components. There is no need to call `split("/")` or `split("\\\\")`, because those approaches depend on path syntax and can mishandle roots, UNC paths, or names with special characters.

You can also compare and compute relative paths:

~~~java
Path base = Path.of("project", "src");
Path file = Path.of("project", "src", "Main.java");

System.out.println(base.relativize(file));
~~~

`relativize` requires both paths to belong to the same filesystem and have compatible roots. On Windows, two paths on different drives generally cannot be relativized against each other.

## 7. Use `Files` to work with files and directories

Once you have a `Path`, use `Files` to read/write and create directories:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class FileOperations {
    public static void main(String[] args) throws IOException {
        Path output = Path.of("build", "reports", "summary.txt");
        Files.createDirectories(output.getParent());
        Files.writeString(output, "BUILD_OK", StandardCharsets.UTF_8);

        String content = Files.readString(output, StandardCharsets.UTF_8);
        System.out.println(content);
    }
}
~~~

Compile and run commands:

~~~text
javac --release 17 -encoding UTF-8 -d out FileOperations.java
java -cp out FileOperations
~~~

Stdout:

~~~text
BUILD_OK
~~~

`Files.createDirectories` also creates any missing parent directories. Use `Path.resolve` to construct the target file and `Files` to perform operations; do not build strings manually with separators. In real-world applications, handle `IOException`, permissions, race conditions, and overwrite policies according to business requirements.

Useful APIs:

| API | Purpose |
|---|---|
| `Files.exists(path)` | Checks whether the path exists at the time of the call |
| `Files.isDirectory(path)` | Checks whether it is a directory |
| `Files.isRegularFile(path)` | Checks whether it is a regular file |
| `Files.createDirectories(path)` | Creates the directory and parent directories |
| `Files.copy(source, target, ...)` | Copies a file |
| `Files.move(source, target, ...)` | Moves/renames |
| `Files.deleteIfExists(path)` | Deletes if it exists |
| `Files.readString(path, charset)` | Reads text |
| `Files.writeString(path, text, charset)` | Writes text |

Existence/status checks only reflect the state at the time of the call; the file may change immediately afterward. If an operation must be atomic or safe against concurrent modifications, design file operations around exceptions and `Files` options rather than relying on check-then-act.

## 8. Building path lists and classpaths properly

When an API requires a string containing multiple paths, use `File.pathSeparator`:

~~~java
import java.io.File;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Collectors;

public class ClassPathBuilder {
    public static void main(String[] args) {
        List<Path> entries = List.of(
                Path.of("build", "classes"),
                Path.of("lib", "example.jar"),
                Path.of("lib", "logging.jar"));

        String classPath = entries.stream()
                .map(Path::toString)
                .collect(Collectors.joining(File.pathSeparator));

        System.out.println(classPath);
    }
}
~~~

Result on Windows:

~~~text
build\classes;lib\example.jar;lib\logging.jar
~~~

Result on Linux/macOS:

~~~text
build/classes:lib/example.jar:lib/logging.jar
~~~

`File.pathSeparator` is used between entries; each entry is created with `Path` so its contents already use the correct separator. Do not hardcode `;` or `:` in Java code if the list needs to run across multiple operating systems.

If there are only two entries, `String.join` also works well:

~~~java
String classPath = String.join(
        File.pathSeparator,
        Path.of("build", "classes").toString(),
        Path.of("lib", "example.jar").toString());
~~~

## 9. Parsing a path list

If you need to read `PATH` or `java.class.path`, use `File.pathSeparator` as the delimiter. Because `String.split` takes a regular expression, use `Pattern.quote` to make it explicit that the delimiter is a literal string:

~~~java
import java.io.File;
import java.util.regex.Pattern;

public class PathListReader {
    public static void main(String[] args) {
        String classPath = System.getProperty("java.class.path", "");
        String[] entries = classPath.split(
                Pattern.quote(File.pathSeparator), -1);

        for (String entry : entries) {
            System.out.println(entry);
        }
    }
}
~~~

For the `PATH` environment variable:

~~~java
String pathValue = System.getenv("PATH");
if (pathValue != null) {
    String[] directories = pathValue.split(
            Pattern.quote(File.pathSeparator), -1);
}
~~~

Do not use `File.separator` to split a classpath. A Windows classpath can contain many `\` characters inside each entry, but only `;` separates the entries. On POSIX, `/` appears inside each entry and `:` separates the list.

A path list may contain empty entries or special characters depending on OS/launcher conventions. Do not write a general-purpose parser with `split` if the input format has its own quoting or escaping; follow the contract of the API you are reading.

## 10. `PATH`, `CLASSPATH`, and the Java classpath are different

Three concepts are often mixed up:

- `PATH`: an operating system environment variable that helps the shell locate executables such as `java`, `javac`, and `git`.
- `CLASSPATH`: a legacy Java environment variable used to specify where to find classes/JARs if the launcher is not given another explicit classpath.
- `-cp`/`-classpath`: an option of the Java launcher or compiler to specify the classpath for a single run/compilation.

Both `PATH` and classpaths are typically path lists, so the delimiter depends on the OS: `;` on Windows and `:` on POSIX. However, each element in them is a path to a directory or file, so the file separator within each element depends on the filesystem.

Example:

~~~text
Windows PATH:
C:\Program Files\Java\jdk-24\bin;C:\Tools\Git\bin

POSIX PATH:
/usr/lib/jvm/jdk-24/bin:/usr/local/bin:/usr/bin
~~~

Prefer passing the classpath explicitly with `-cp` or letting a build tool manage dependencies. Do not rely on a global `CLASSPATH` on a developer's machine, as this value can make local builds behave differently from CI.

## 11. Running `java -cp` on Windows and POSIX

The same program may require different command-line syntax because the classpath delimiter and file path separator differ.

Windows PowerShell or CMD:

~~~powershell
java -cp "build\classes;lib\example.jar" com.example.Main
~~~

Linux/macOS shell:

~~~sh
java -cp "build/classes:lib/example.jar" com.example.Main
~~~

If a path contains spaces, quote the entire classpath argument:

~~~powershell
java -cp "build\classes;lib\example library.jar" com.example.Main
~~~

~~~sh
java -cp "build/classes:lib/example library.jar" com.example.Main
~~~

Quoting ensures the shell passes the classpath as a single argument. It does not change the delimiter that the Java launcher uses to separate entries. Avoid copying a Windows command verbatim to Linux/macOS or vice versa.

When writing cross-platform scripts, you can use separate scripts for each shell, or let Maven/Gradle/your IDE generate the classpath instead of concatenating strings manually.

## 12. Windows, POSIX, and UNC paths

Common path forms:

| Form | Example | Meaning |
|---|---|---|
| Windows absolute | `C:\work\app` | Path on drive C |
| Windows relative | `src\main\java` | Relative to the working directory |
| Windows UNC | `\\server\share\folder` | Network resource |
| POSIX absolute | `/opt/app/config` | Starts from root `/` |
| POSIX relative | `src/main/java` | Relative to the working directory |
| Home-relative shell | `~/project` | Shell expansion, not Java Path syntax |

Do not hardcode the `C:` drive letter in a portable application. Obtain the base directory from a config, system property, or defined environment variable, then resolve the remaining components.

`~` is an expansion syntax of certain shells; `Path.of("~/project")` does not automatically expand to the home directory. In Java, use:

~~~java
Path home = Path.of(System.getProperty("user.home"));
Path project = home.resolve("project");
~~~

To get the working directory:

~~~java
Path workingDirectory = Path.of("").toAbsolutePath().normalize();
~~~

Do not assume the working directory is the directory containing the JAR or source code. Service managers, IDEs, containers, and CI can launch processes from different directories.

## 13. Distinguishing filesystem paths from URIs and URLs

URIs have their own syntax and typically use `/` in the path component, even when the resource resides on Windows. This is not a reason to use slashes as file separators in all strings.

Example URIs:

~~~text
file:///C:/work/app/config/settings.json
https://example.com/api/v1/items
~~~

Use `Path.toUri()` to convert a file path to a URI:

~~~java
Path file = Path.of("config", "settings.json");
java.net.URI uri = file.toAbsolutePath().toUri();
~~~

`Path.toUri()` creates a URI appropriate for the filesystem provider. Do not manually replace `\` with `/` and prepend `file://`; doing so can break drive letters, UNC paths, spaces, or Unicode characters.

To create a path from a `file:` URI, use `Path.of(uri)` when the URI belongs to an appropriate provider. An `https:` URI is not a file path and cannot be arbitrarily passed to `Path.of(URI)`. Use `URI`/an HTTP client for network resources.

When storing paths in JSON, YAML, or properties files, pay attention to the escaping rules of that format. For example, in JSON, backslashes must be escaped according to JSON string syntax. It is best to use a serialization library instead of manually replacing characters with `replace`.

## 14. Java running in Docker, WSL, and CI

The separator is determined by the filesystem/provider that the JVM is using, not necessarily the host machine's operating system.

For example:

- A JVM running directly on Windows typically uses `\` and `;`.
- A JVM running in a Linux container uses `/` and `:`, even when the Docker host is Windows.
- A JVM running in WSL uses the Linux filesystem for processes inside WSL.
- Windows and Linux CI runners can produce the same artifact, but paths in logs and classpaths will differ.

Do not infer separators from CI variables like `RUNNER_OS` when the JVM already provides `File.separator` and `File.pathSeparator`. If you need diagnostic logging:

~~~java
System.out.println("os.name=" + System.getProperty("os.name"));
System.out.println("file.separator=" + File.separator);
System.out.println("path.separator=" + File.pathSeparator);
System.out.println("user.dir=" + System.getProperty("user.dir"));
~~~

With Docker volumes, mount paths inside the container must follow the container's OS. A Windows path on the host is not automatically a valid path inside a Linux container.

## 15. Build tools and cross-platform classpaths

With Maven, Gradle, or Ant, declare source sets and dependencies using the build tool's configuration. The build tool will generate a classpath appropriate for the platform.

Maven example:

~~~xml
<dependency>
  <groupId>com.example</groupId>
  <artifactId>example-library</artifactId>
  <version>1.2.0</version>
</dependency>
~~~

Gradle example:

~~~groovy
dependencies {
    implementation 'com.example:example-library:1.2.0'
}
~~~

Avoid manually concatenating classpath strings in `pom.xml`, `build.gradle`, or CI scripts when the build tool already has a dependency model. Use wrapper scripts to pin the build tool version:

~~~text
Windows: mvnw.cmd verify
POSIX:   ./mvnw verify
~~~

~~~text
Windows: gradlew.bat check
POSIX:   ./gradlew check
~~~

With Ant, use nested `<classpath>` and `<pathelement>` instead of manually constructing OS-specific strings:

~~~xml
<path id="compile.classpath">
  <pathelement location="lib/example.jar"/>
  <pathelement location="build/classes"/>
</path>

<javac srcdir="src/main/java"
       destdir="build/classes"
       includeantruntime="false"
       classpathref="compile.classpath"/>
~~~

These build tools automatically choose the right separator for the classpath; the build author's job is to declare the dependencies and file locations properly.

## 16. Common mistakes

### Using `File.separator` to join a classpath

**Symptom:** Java cannot find the second class/JAR in the classpath.

**Cause:** `File.separator` separates directories within a single path, not entries in a path list.

**Fix:** Use `File.pathSeparator` between entries and `Path` to construct each entry.

### Using `File.pathSeparator` to join directories

**Symptom:** The path contains `;` on Windows or `:` on POSIX and the file does not exist.

**Cause:** The path-list delimiter was used as a filesystem separator.

**Fix:** Use `Path.of("dir", "subdir", "file.txt")` or `resolve`.

### Hardcoding slashes or backslashes

**Symptom:** The program works on a developer's machine but fails on CI on a different OS.

**Cause:** The path string depends on the syntax of a single filesystem.

**Fix:** Construct paths using the `Path` API; only use literal paths when the format is explicitly specified and tied to a specific platform.

### Splitting a classpath on `/` or `\`

**Symptom:** A classpath entry is split into multiple pieces or a JAR cannot be found.

**Cause:** The code splits on the separator inside a path instead of the delimiter between entries.

**Fix:** `split(Pattern.quote(File.pathSeparator))`.

### Using `replace("\\", "/")` for portability

**Symptom:** Valid file names on POSIX are altered or the URI/path is incorrect.

**Cause:** Character string replacement does not understand filesystem semantics.

**Fix:** Keep paths as `Path` objects; convert to a URI with `toUri()` when needed.

### Assuming `~` expands automatically

**Symptom:** The application looks for a directory literally named `~`.

**Cause:** Shell expansion is not performed when Java receives arguments.

**Fix:** Use `System.getProperty("user.home")`.

### Using `normalize()` to check if a file exists

**Symptom:** The code assumes the path is valid, but file operations still fail.

**Cause:** `normalize()` only processes lexical components and does not access the filesystem.

**Fix:** Use `Files.exists`, `Files.isRegularFile`, `toRealPath`, or perform the operation directly and handle exceptions appropriately.

### Assuming a fixed working directory

**Symptom:** Relative paths work in the IDE but fail in a service or CI.

**Cause:** `user.dir` differs across launchers.

**Fix:** Determine the base directory explicitly and resolve paths from that base.

### Using host paths inside a container

**Symptom:** An application in a Linux container cannot open `C:\...`.

**Cause:** The JVM sees the container's filesystem.

**Fix:** Mount volumes and configure paths inside the container according to the container's OS.

## 17. Java 17+ example: inspecting separators and file operations

Create `PathSeparatorDemo.java`:

~~~java
import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileSystems;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.regex.Pattern;

public final class PathSeparatorDemo {
    private PathSeparatorDemo() {
    }

    public static void main(String[] args) throws Exception {
        System.out.println("FILE_SEPARATOR=" + File.separator);
        System.out.println("FILE_PATH_SEPARATOR=" + File.pathSeparator);
        System.out.println("FILESYSTEM_SEPARATOR="
                + FileSystems.getDefault().getSeparator());

        Path javadoc = Path.of("build", "reports")
                .resolve("javadoc")
                .resolve("index.html");
        Path normalized = Path.of("build", "reports", "..", "classes")
                .normalize();
        System.out.println("JAVADOC_PATH=" + javadoc);
        System.out.println("NORMALIZED_PATH=" + normalized);

        String classPath = String.join(
                File.pathSeparator,
                Path.of("build", "classes").toString(),
                Path.of("lib", "example.jar").toString());
        String[] entries = classPath.split(
                Pattern.quote(File.pathSeparator), -1);
        System.out.println("CLASSPATH=" + classPath);
        System.out.println("CLASSPATH_ENTRIES=" + entries.length);

        Path tempDir = Files.createTempDirectory("path-separator-demo-");
        Path output = tempDir.resolve("nested").resolve("result.txt");
        Files.createDirectories(output.getParent());
        Files.writeString(output, "PATH_SEPARATOR_OK",
                StandardCharsets.UTF_8);
        String content = Files.readString(output, StandardCharsets.UTF_8);
        System.out.println("FILE_ROUND_TRIP="
                + ("PATH_SEPARATOR_OK".equals(content) ? "PASS" : "FAIL"));

        Files.deleteIfExists(output);
        Files.deleteIfExists(output.getParent());
        Files.deleteIfExists(tempDir);
    }
}
~~~

Compile:

~~~text
javac --release 17 -encoding UTF-8 -Xlint:all -Werror PathSeparatorDemo.java
~~~

Run:

~~~text
java PathSeparatorDemo
~~~

Stdout on Windows:

~~~text
FILE_SEPARATOR=\
FILE_PATH_SEPARATOR=;
FILESYSTEM_SEPARATOR=\
JAVADOC_PATH=build\reports\javadoc\index.html
NORMALIZED_PATH=build\classes
CLASSPATH=build\classes;lib\example.jar
CLASSPATH_ENTRIES=2
FILE_ROUND_TRIP=PASS
~~~

Stdout on Linux/macOS has the corresponding separators:

~~~text
FILE_SEPARATOR=/
FILE_PATH_SEPARATOR=:
FILESYSTEM_SEPARATOR=/
JAVADOC_PATH=build/reports/javadoc/index.html
NORMALIZED_PATH=build/classes
CLASSPATH=build/classes:lib/example.jar
CLASSPATH_ENTRIES=2
FILE_ROUND_TRIP=PASS
~~~

The result on Windows 11 with Zulu/OpenJDK 24.0.2 matches the Windows block exactly. The demo was compiled with `--release 17`, `-Xlint:all`, and `-Werror`; file reading/writing uses a temporary directory and deletes the files after verification.

## 18. Cross-platform testing in CI

A program using `Path` should still be tested on the operating systems the product supports. A minimal GitHub Actions matrix:

~~~yaml
name: Cross-platform path test

on:
  pull_request:
  push:
    branches: [main]

jobs:
  path-demo:
    strategy:
      fail-fast: false
      matrix:
        os: [windows-latest, ubuntu-latest, macos-latest]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'

      - name: Compile
        run: javac --release 17 -encoding UTF-8 -Xlint:all -Werror PathSeparatorDemo.java

      - name: Run
        run: java PathSeparatorDemo
~~~

Do not compare stdout verbatim between Windows and POSIX because the separators differ by design. Tests should verify invariants such as:

- `File.separator` equals the default filesystem's separator.
- `File.pathSeparator` splits the classpath into the expected number of entries.
- `Path.resolve` produces a path with the expected components.
- `Files.createDirectories`, write/read, and delete work.
- No path strings are hardcoded for an inappropriate OS.

If a CI matrix runs the same tests, verify behavior and file contents rather than requiring identical path text across operating systems.

## 19. Checklist for writing portable Java paths

- [ ] Use `Path.of`/`Paths.get` to create paths.
- [ ] Use `resolve`/`resolveSibling` to combine paths.
- [ ] Use `Files` to create, read, write, copy, move, and delete.
- [ ] Only use `File.separator` when you genuinely need the path-component separator character.
- [ ] Only use `File.pathSeparator` when building/parsing a path list or classpath.
- [ ] Use `Pattern.quote(File.pathSeparator)` when splitting a path-list string.
- [ ] Do not hardcode `\`, `/`, `;`, or `:` in portable code.
- [ ] Do not use string replace to turn a Windows path into a POSIX path or vice versa.
- [ ] Do not treat a URI/URL as a filesystem path.
- [ ] Determine the base directory explicitly; do not assume the working directory.
- [ ] Distinguish lexical normalization from real paths and symbolic links.
- [ ] Validate child paths if the input comes from users.
- [ ] Use the dependency model of Maven/Gradle/Ant instead of manually concatenating classpaths.
- [ ] Run tests on Windows, Linux, and macOS if the product supports those platforms.
- [ ] Verify paths inside containers against the container's filesystem.

## 20. References

- Java SE 24 — `java.io.File`, `separator`, and `pathSeparator`: https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/io/File.html
- Java SE 24 — `java.nio.file.Path`: https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/nio/file/Path.html
- Java SE 24 — `java.nio.file.FileSystem`: https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/nio/file/FileSystem.html
- Java SE 24 — `java.nio.file.Files`: https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/nio/file/Files.html
- Oracle JDK 24 — `java` launcher and classpath: https://docs.oracle.com/en/java/javase/24/docs/specs/man/java.html
- Oracle JDK 24 — `javac` command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/javac.html
- Java SE 24 — `java.net.URI`: https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/net/URI.html
- Gradle — Java Plugin and dependency configurations: https://docs.gradle.org/current/userguide/java_plugin.html
- Apache Maven — Introduction to the Dependency Mechanism: https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html

Remember the two separator levels: `File.separator` separates components of a single file path; `File.pathSeparator` separates multiple paths in a classpath or path list. Use `Path`/`Files` for the filesystem and only join path lists with the platform-provided delimiter. When supporting multiple OSes, test on each runner and verify behavior rather than assuming path strings must be identical.