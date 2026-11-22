# Differences Between Windows and Linux in Java Development

Java applications run across multiple operating systems thanks to the JVM, yet filesystems, processes, shells, and native libraries still behave differently. Because of this, the same build can run on Windows but fail on Linux due to case mismatches, line endings, permissions, paths, or command-line differences. Cross-platform development requires using standard APIs, explicitly defining project conventions, and testing on every supported OS.

## 1. Key Differences

| Area | Common on Windows | Common on Linux | Impact |
| --- | --- | --- | --- |
| File separator | `\` | `/` | Use `Path` instead of string concatenation |
| Path-list separator | `;` | `:` | Differs in classpath and PATH |
| Case sensitivity | Typically case-insensitive by default | Typically case-sensitive | Wrong case may fail only on Linux |
| Absolute path | Drive letter or UNC | Starts with `/` | Do not hardcode the root |
| Line ending | CRLF | LF | Scripts and text files may fail |
| Permission | Windows ACL | POSIX owner/group/other | Do not assume POSIX APIs are available |
| Shell | PowerShell/cmd.exe | Bash/dash or other shells | Command syntax differs |
| Script wrapper | `.bat`/`.cmd` | `./script` | Invoke the right wrapper per OS |
| Native library | `.dll` | `.so` | Binaries depend on OS/CPU |
| Process stop | Windows process/control events | POSIX signals | Shutdown behavior differs |

These are common defaults, not absolute rules. Filesystems, mount options, WSL, containers, and custom configurations can change behavior. Check actual capabilities instead of inferring solely from `os.name`.

## 2. Paths: Use Path Instead of String Concatenation

Java provides `java.nio.file.Path` and `Files` for working with the filesystem. `Path` uses the JVM's default filesystem provider, so the provider handles platform path syntax.

The two separators have different meanings:

| Java API | Windows | Linux | Meaning |
| --- | --- | --- | --- |
| `File.separator` | `\` | `/` | Separates components within a single path |
| `File.pathSeparator` | `;` | `:` | Separates multiple paths in a classpath/path list |

Do not write hardcoded paths like `"build\\reports\\daily\\test.txt"`. Use:

```java
Path report = Path.of("build", "reports", "daily", "test.txt");
Path output = Path.of("build").resolve("reports").resolve("daily");
Path absolute = report.toAbsolutePath().normalize();
```

`Path.of(String, String...)` joins components according to the current filesystem. `resolve` appends a child path to a parent path. `normalize` removes redundant syntactic elements such as `.` and `..`, but does not access the filesystem or resolve symbolic links.

When you need the actual path of an existing file, use `toRealPath()`. This method performs I/O and may resolve symbolic links. Do not use `normalize()` as a security measure for user-supplied paths; validate the path after resolving and consider symlinks/path traversal.

### Home, Temporary, and Working Directories

Do not hardcode `C:\\Users\\name\\...` or `/home/name/...`. Use Java properties:

```java
Path home = Path.of(System.getProperty("user.home"));
Path temp = Path.of(System.getProperty("java.io.tmpdir"));
Path working = Path.of(System.getProperty("user.dir"));
Path config = home.resolve(".myapp").resolve("config.json");
```

`user.home` is the home directory. `java.io.tmpdir` is the temporary directory. `user.dir` is usually the working directory when the JVM starts; it is not necessarily the directory containing the JAR or source code.

If a process needs to run in the project directory, set it explicitly with `ProcessBuilder.directory(...)`. Do not assume the runner always starts at the repository root.

### Drive Letters and UNC

Windows supports drive paths such as `C:\\work\\app` and UNC paths such as `\\\\server\\share\\folder`. `C:temp.txt` is a path relative to the current directory on drive C, unlike `C:\\temp.txt`, which is a path from the root of the drive.

Linux typically uses a single filesystem tree starting from `/` and has no drive letters. Do not convert paths by manually replacing `\\` with `/`; use `Path` and the appropriate URI APIs.

## 3. Case Sensitivity and Filenames

Windows filesystems typically preserve case but compare names case-insensitively by default. Common Linux filesystems such as ext4 are typically case-sensitive:

- `Config.java` and `config.java` may refer to the same file on Windows.
- On Linux, these two names can be two separate files.
- An import or resource path with the wrong case may still run on Windows but fail on Linux.

Not every Windows volume is case-insensitive; NTFS can enable case sensitivity per directory. WSL and mount configurations can also alter behavior.

Practices:

1. Filenames must match the exact case of public class names, packages, and resources.
2. Use a consistent naming convention.
3. Do not create two files that differ only in letter case in the same repository.
4. If you only change letter case, check `git diff` and verify that the rename is recorded.
5. Use `Files.isSameFile(pathA, pathB)` when you need to determine whether two paths point to the same file.

### Portable Filenames

Windows reserves the characters `< > : " / \\ | ? *` in filenames. Certain device names such as `CON`, `PRN`, `AUX`, `NUL`, `COM1`, and `LPT1` remain reserved even with an extension, for example `NUL.txt`. Names ending with a period or space also cause issues with many Windows APIs.

Linux allows more characters; `/` and the NUL byte cannot appear in a name component. A name valid on Linux is not guaranteed to work on Windows.

Prefer names consisting of ASCII letters, digits, hyphens, underscores, and dots in the middle of the name. Avoid reserved names, trailing dots/spaces, and overly long paths.

## 4. Line Endings and Encoding

### CRLF and LF

Windows typically uses CRLF (`\\r\\n`); Linux typically uses LF (`\\n`). Java provides `System.lineSeparator()` to obtain the native line separator:

```java
String report = "first line" + System.lineSeparator()
              + "second line" + System.lineSeparator();
```

Use the native line separator only when the format allows it. JSON, protocols, shell scripts, or version-controlled files may require a specific line ending. When a format requires LF, write LF explicitly. When reading text, use `BufferedReader.readLine()` or an appropriate API rather than splitting manually on `\\n` alone.

### Normalizing with Git

Use `.gitattributes` to unify line endings:

```gitattributes
* text=auto
*.java       text eol=lf
*.gradle     text eol=lf
*.properties text eol=lf
*.yml        text eol=lf
*.yaml       text eol=lf
*.sh         text eol=lf
*.bat        text eol=crlf
*.cmd        text eol=crlf
*.ps1        text eol=crlf
*.jar        binary
*.class      binary
```

Git can normalize text to LF in the repository and convert to CRLF on checkout according to configuration. `*.sh` should stay LF so Linux reads the shebang properly; batch files can use CRLF. Binaries should be marked so Git does not alter their bytes.

If a project already has mixed line endings, inspect the diff before running `git add --renormalize .`. Do not change `core.autocrlf` globally just to fix one repository; define the policy in `.gitattributes`.

### Charset and UTF-8

Since JDK 18, UTF-8 has been the default charset for Java SE APIs across operating systems. On JDK 17 and earlier, the default charset depends on the runtime, locale, and environment; Windows may use a code page other than UTF-8.

Even though newer JDKs default to UTF-8, you should explicitly specify the charset for stored data or external communication:

```java
Path file = Path.of("data", "customers.txt");
Files.writeString(file, "Nguyễn An", StandardCharsets.UTF_8);
String value = Files.readString(file, StandardCharsets.UTF_8);
```

For source code, set the encoding for the compiler:

```bash
javac --release 17 -encoding UTF-8 -d out src/main/java/com/example/App.java
```

Gradle:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
    options.release = 17
}
```

Maven:

```xml
<properties>
  <maven.compiler.release>17</maven.compiler.release>
  <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
```

File encoding, the default charset of Java APIs, and terminal/stdout encoding are not identical. JEP 400 does not mean every Windows console renders Unicode the same way. When communicating with another process, specify the charset that process uses.


## 5. File Permissions and Symbolic Links

### POSIX Permissions and Windows ACLs

Linux typically uses owner/group/other permissions with read, write, and execute bits. Windows primarily uses Access Control Lists (ACLs), along with file attributes and per-user/group access rights.

Java provides attribute views:

| API | Purpose |
| --- | --- |
| `BasicFileAttributeView` | Basic attributes such as type, size, and timestamps |
| `PosixFileAttributeView` | POSIX owner, group, and permission bits |
| `AclFileAttributeView` | Access Control List if supported by the provider |
| `DosFileAttributeView` | DOS attributes such as hidden, read-only, and archive |

Do not call `Files.setPosixFilePermissions()` unconditionally on Windows. A provider that does not support the POSIX view may return `null` from `Files.getFileAttributeView(...)` or throw `UnsupportedOperationException` when an operation is unsupported.

Example of checking capability:

```java
Path file = Path.of("run.sh");
PosixFileAttributeView posix =
    Files.getFileAttributeView(file, PosixFileAttributeView.class);

if (posix != null) {
    System.out.println(posix.readAttributes().permissions());
} else {
    System.out.println("POSIX permissions are not supported here");
}
```

`Files.isReadable()`, `isWritable()`, and `isExecutable()` are useful for general accessibility checks. They do not replace handling `IOException` when performing actual I/O and are not a security check against race conditions.

On Linux, shell scripts typically require the executable bit:

```bash
chmod +x gradlew mvnw
```

Git needs to record the executable mode so checkouts on Linux preserve the ability to run the script. Windows does not have POSIX executable bits in the same way; wrappers are typically invoked via `.bat` or `.cmd`.

### Symbolic Links

Linux supports symbolic links as a standard part of the filesystem. Windows also supports links, but creating them may depend on user privileges, Developer Mode, policies, and the filesystem.

`Files.createSymbolicLink()` or `Files.readSymbolicLink()` may fail if the provider does not support them or the user lacks permissions. If an application needs links, check capabilities and handle exceptions rather than assuming creation always succeeds.

### Open Files, Renaming, and Deleting

Behavior with open files can differ across OSes and filesystems. On Windows, renaming or deleting may fail if another process holds a handle with an incompatible sharing mode. On Linux, a file can be unlinked from a directory while a process still holds an open file descriptor; the data is only freed when the last handle closes.

Therefore:

- Close streams before renaming or deleting a file.
- Use try-with-resources for streams, channels, and file locks.
- Do not write tests that assume every OS allows deleting an open file.
- For file locks, handle `OverlappingFileLockException` and `IOException`; do not use file locks as a substitute for thread synchronization within the same JVM.

## 6. ProcessBuilder, Shell, and Command Line

### ProcessBuilder Does Not Invoke a Shell Automatically

`ProcessBuilder` creates a process with a command and a list of arguments. It does not interpret shell syntax such as pipes, redirects, environment variables, or `&&`.

Recommended approach:

```java
Process process = new ProcessBuilder(
    "java",
    "-version"
).redirectErrorStream(true).start();

int exitCode = process.waitFor();
```

Pass each argument as a separate element. Do not concatenate the entire command into a string and quote it manually; the tokenization rules of the Windows command interpreter differ from Linux shells.

If you truly need shell syntax, invoke the shell explicitly:

```java
// Windows
new ProcessBuilder("cmd.exe", "/c", "dir").start();

// Linux
new ProcessBuilder("sh", "-c", "ls -la").start();
```

Only use a shell when you need pipes, globs, redirects, or shell built-ins. If user input is involved, avoid concatenating it into a shell command; prefer invoking the executable directly with an argument list to reduce command injection risks.

### Environment Variables

| Purpose | Common on Windows | Common on Linux |
| --- | --- | --- |
| Home directory | `USERPROFILE` | `HOME` |
| Temporary directory | `TEMP`, `TMP` | `TMPDIR` |
| Executable search path | `Path` or `PATH` | `PATH` |
| Shell | `ComSpec` | `SHELL` |

Use `System.getProperty("user.home")` and `System.getProperty("java.io.tmpdir")` for the corresponding Java needs. Do not assume environment variable names are the same. `ProcessBuilder.environment()` provides a system-dependent map and is typically case-sensitive in the Java API, even when the OS handles variable names differently.

Example of passing an environment variable to a child process:

```java
ProcessBuilder builder = new ProcessBuilder("java", "-version");
builder.environment().put("APP_MODE", "test");
builder.directory(Path.of(System.getProperty("user.dir")).toFile());

Process process = builder.start();
```

The `APP_MODE` variable will be present in the child process's environment. Shell expansions like `$HOME` or `%USERPROFILE%` do not happen automatically when using `ProcessBuilder` directly.

### Finding Executables and Script Wrappers

Executables may have different names or extensions. Java on Windows is typically `java.exe`, whereas on Linux it is `java`. For build tools, using the project's wrapper is more reliable than depending on a globally installed Gradle/Maven.

```bash
# Linux/macOS
./gradlew clean test
./mvnw --batch-mode verify
```

```powershell
# Windows PowerShell
.\gradlew.bat clean test
.\mvnw.cmd --batch-mode verify
```

If spawning a process from Java, choose the wrapper appropriate for the OS or invoke the Java executable via the path from `java.home`. Set the working directory explicitly. Do not hardcode `C:\\Program Files\\...` or `/usr/bin/...` if the tool can be found via PATH or a wrapper.

## 7. Locale, Timezone, and OS Name

An application can run on both OSes yet produce different results due to default locale or timezone settings.

- Use `Locale.ROOT` when normalizing identifiers, keys, or language-independent technical strings.
- Choose an explicit locale when formatting currency, dates, and numbers for users.
- Use `Instant` to store absolute points in time; use an explicit `ZoneId` when displaying regionally.
- Do not assume the timezone of a Windows runner and a Linux container are the same.
- Do not use locale-formatted date/time strings as keys or machine-readable data.

If you must branch by OS, you can check `System.getProperty("os.name")` and `os.arch`. Use `Locale.ROOT` when converting to lowercase. Avoid overly broad string checks such as `contains("win")`, because `Darwin` also contains `win`.

Only branch by OS when you genuinely need to invoke a script/native tool or use an OS-specific feature. For files, paths, and permissions, prefer querying whether the filesystem provider supports the corresponding capability.

## 8. Native Libraries and CPU Architecture

Java bytecode is portable, but JNI/JNA or native libraries depend on the OS and architecture:

| Platform | Common Native Library |
| --- | --- |
| Windows | `.dll` |
| Linux | `.so` |
| macOS | `.dylib` |

Beyond the OS, the CPU architecture must match, such as `amd64`/`x86_64` or `aarch64`/`arm64`. A native binary for the wrong OS or wrong architecture can cause `UnsatisfiedLinkError` even if the Java source compiles successfully.

Practices:

1. Distribute separate native binaries for each OS/architecture.
2. Organize resources using a clear convention, such as `native/windows-x86_64/`.
3. Check `os.name` and `os.arch` before selecting a binary.
4. Handle missing matching binaries with a clear error message.
5. Do not overwrite a native library currently in use by a process.
6. Check transitive native dependencies, not just the main JNI file.

## 9. Process Termination and Shutdown

On Linux, processes typically receive signals such as SIGTERM when a service manager requests a stop; SIGKILL forcibly terminates the process without allowing the application to clean up. Windows has process termination mechanisms and console control events that differ from POSIX signals.

Java provides `Process.destroy()`, `destroyForcibly()`, and shutdown hooks, though the details of signal delivery and waiting for process exit depend on the implementation/platform. Shutdown hooks only run when the JVM goes through an orderly shutdown; you cannot rely on hooks when a process is forcibly killed, power is lost, or the runtime crashes.

For services:

- Stop accepting new requests when starting graceful shutdown.
- Complete or time out in-flight requests.
- Flush and close resources.
- Set an overall timeout so the service manager does not wait indefinitely.
- Persist critical data safely during normal processing, not only in shutdown hooks.

## 10. Java 17+ Practical Example: Probing the Environment and Running a Child Process

This example inspects filesystem properties, charset, and line endings, then uses `ProcessBuilder` to run a child Java class. An argument containing a space is passed as a single argument; an environment variable is passed to the child process.

File `src/PlatformProbe.java`:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.io.InputStreamReader;
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFileAttributeView;
import java.util.Comparator;
import java.util.Locale;
import java.util.stream.Stream;

public final class PlatformProbe {
    private PlatformProbe() {
    }

    public static void main(String[] args) throws IOException, InterruptedException {
        String osName = System.getProperty("os.name");
        boolean windows = osName.toLowerCase(Locale.ROOT).startsWith("windows");

        System.out.println("os.name=" + osName);
        System.out.println("os.arch=" + System.getProperty("os.arch"));
        System.out.println("file.separator=" + java.io.File.separator);
        System.out.println("path.separator=" + java.io.File.pathSeparator);
        System.out.println("default.charset=" + Charset.defaultCharset().name());
        System.out.println("line.separator=" +
            System.lineSeparator().replace("\r", "CR").replace("\n", "LF"));

        Path report = Path.of("build", "reports", "daily", "test report.txt");
        System.out.println("portable.path=" + report);
        System.out.println("absolute.path.isAbsolute=" +
            report.toAbsolutePath().isAbsolute());

        Path tempDir = Files.createTempDirectory("platform-probe-");
        try {
            Path text = tempDir.resolve("Readme.txt");
            Files.writeString(
                text,
                "Tiếng Việt — café — 東京",
                StandardCharsets.UTF_8
            );

            System.out.println("utf8.roundtrip=" +
                Files.readString(text, StandardCharsets.UTF_8));
            System.out.println("case.variant.exists=" +
                Files.exists(tempDir.resolve("README.txt")));
            System.out.println("posix.attributes.available=" +
                (Files.getFileAttributeView(
                    text, PosixFileAttributeView.class) != null));
            System.out.println("file.executable=" + Files.isExecutable(text));
        } finally {
            try (Stream<Path> paths = Files.walk(tempDir)) {
                paths.sorted(Comparator.reverseOrder()).forEach(path -> {
                    try {
                        Files.deleteIfExists(path);
                    } catch (IOException error) {
                        throw new UncheckedIOException(error);
                    }
                });
            }
        }

        Path java = Path.of(
            System.getProperty("java.home"),
            "bin",
            windows ? "java.exe" : "java"
        );

        ProcessBuilder builder = new ProcessBuilder(
            java.toString(),
            "-cp",
            System.getProperty("java.class.path"),
            "EchoArgs",
            "two words"
        );
        builder.directory(Path.of(System.getProperty("user.dir")).toFile());
        builder.environment().put("APP_MODE", "test");
        builder.redirectErrorStream(true);

        Process process = builder.start();
        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(
                    process.getInputStream(), StandardCharsets.UTF_8))) {
            reader.lines().forEach(line ->
                System.out.println("child=" + line));
        }
        System.out.println("child.exit=" + process.waitFor());
    }
}

final class EchoArgs {
    public static void main(String[] args) {
        System.out.println("argument.count=" + args.length);
        System.out.println("argument.0=" + args[0]);
        System.out.println("env.APP_MODE=" + System.getenv("APP_MODE"));
    }
}
```

Compile with JDK 17 or later:

```bash
javac --release 17 -encoding UTF-8 -g -d out src/PlatformProbe.java
java -cp out PlatformProbe
```

`--release 17` controls API/source compatibility; the class can run on newer JDKs. `-encoding UTF-8` specifies the source encoding. The example uses Java APIs instead of path concatenation, specifies charsets explicitly, and passes process arguments as a list.

### Verified Output on Windows 11, JDK 24.0.2

```text
os.name=Windows 11
os.arch=amd64
file.separator=\
path.separator=;
default.charset=UTF-8
line.separator=CRLF
portable.path=build\reports\daily\test report.txt
absolute.path.isAbsolute=true
utf8.roundtrip=Tiếng Việt — café — 東京
case.variant.exists=true
posix.attributes.available=false
file.executable=true
child=argument.count=1
child=argument.0=two words
child=env.APP_MODE=test
child.exit=0
```

Several lines will differ on Linux:

- `file.separator` is typically `/`; `path.separator` is typically `:`.
- `line.separator` is typically `LF`.
- Common Linux filesystems are case-sensitive, so `case.variant.exists` is typically `false` when only `Readme.txt` is created.
- The POSIX attribute view is usually available on Linux filesystems; still check because a provider or mount may not support it.
- `file.executable` depends on permissions and the filesystem; do not infer POSIX execute bits from this value alone.

The program was compiled with `javac --release 17 -encoding UTF-8` and ran successfully on Windows 11/JDK 24.0.2. This test environment does not have an active Linux shell, so the Linux values above are described according to API/OS documentation rather than direct execution results on Linux during this test run.

## 11. Cross-platform CI: Testing Both Windows and Linux

A build that only runs on a developer's machine is not enough to catch case mismatches, permissions, script line endings, or path issues. You should have a CI matrix for the OSes the product supports.

GitHub Actions example for Gradle, file `.github/workflows/cross-platform.yml`:

```yaml
name: Java Cross-platform CI

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  test:
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, windows-latest]
        java: ['17', '21', '25']

    runs-on: ${{ matrix.os }}

    steps:
      - name: Checkout
        uses: actions/checkout@v7

      - name: Set up JDK
        uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: ${{ matrix.java }}
          cache: gradle

      - name: Test on Linux
        if: runner.os == 'Linux'
        run: ./gradlew --no-daemon clean check

      - name: Test on Windows
        if: runner.os == 'Windows'
        run: .\gradlew.bat --no-daemon clean check

      - name: Upload test reports
        if: ${{ always() }}
        uses: actions/upload-artifact@v7
        with:
          name: test-reports-${{ matrix.os }}-jdk-${{ matrix.java }}
          path: |
            **/build/test-results/**
            **/build/reports/tests/**
          if-no-files-found: ignore
```

For Maven, keep the same matrix but change the cache to `maven` and invoke the corresponding wrapper:

```yaml
- name: Test on Linux
  if: runner.os == 'Linux'
  run: ./mvnw --batch-mode --no-transfer-progress clean verify

- name: Test on Windows
  if: runner.os == 'Windows'
  run: .\mvnw.cmd --batch-mode --no-transfer-progress clean verify
```

The matrix creates six jobs: two OSes times three JDKs. Adjust according to your support policy; you do not need to test every combination if the cost is too high. You can run a baseline JDK on both OSes for every pull request and run a broader matrix on a schedule or before releases.

When a build runs in a Linux container on a Windows host, the container still uses Linux semantics for the filesystem and processes inside the container. A Docker job on Windows does not replace testing directly on a Windows runner if the product supports Windows.

## 12. Common Errors When Switching Between Windows and Linux

| Symptom | Cause | Resolution |
| --- | --- | --- |
| `FileNotFoundException` only on Linux | Case mismatch in path or resource | Verify exact filenames, packages, and resources |
| Script reports `bad interpreter` | Shell script has CRLF or shebang points to a nonexistent shell | Set `*.sh text eol=lf`, check the shebang |
| `gradlew: Permission denied` | Missing executable bit in Linux checkout | `chmod +x gradlew`; commit the executable mode |
| Windows cannot create file | Name contains reserved characters or device names | Use portable names; avoid `CON`, `NUL`, `COM1`, etc. |
| Classpath does not work | Using `:` on Windows or `;` on Linux | Use a build tool or `File.pathSeparator` |
| Vietnamese text is garbled | Mismatched source/file/terminal encoding | Use UTF-8 explicitly; check console charset |
| Tests fail due to line endings | Tests assume only LF or CRLF | Normalize with Git and read text line by line |
| Cannot set POSIX permissions on Windows | Filesystem provider does not support POSIX view | Check attribute view and use appropriate APIs |
| Process fails to start | Wrong executable, extension, or working directory | Use the OS-specific wrapper; check PATH and working directory |
| Argument with spaces is split | Manually concatenating command into a string and quoting incorrectly | Use an argument list in `ProcessBuilder` |
| File deletion test fails on Windows | Another stream/process still holds a handle | Close resources before renaming/deleting |
| Native library fails to load | Wrong extension, OS, or CPU architecture | Distribute separate binaries per platform |
| Build differs due to locale/timezone | Using default locale/timezone | Use `Locale.ROOT`, `ZoneId`, and `Instant` |
| Wrapper runs locally but fails in CI | Calling wrong wrapper or checkout lost file mode | Use `gradlew.bat`/`gradlew`, `mvnw.cmd`/`mvnw` per OS |

## 13. Pre-release Cross-platform Checklist

1. All paths are constructed using `Path`, `resolve`, or filesystem APIs.
2. No hardcoded drive letters, `/home/...`, or separators.
3. Filenames, packages, classes, and resources match case.
4. No Windows reserved filenames or overly long paths outside the supported policy.
5. Source and text resources use a defined encoding.
6. `.gitattributes` specifies line endings for shell, batch, and text files.
7. Wrappers have the executable bit on Linux, and Windows wrappers are kept in Git.
8. Shell syntax is not passed to `ProcessBuilder` unless a shell is explicitly chosen.
9. Process arguments, working directory, and environment are configured explicitly.
10. Code checks POSIX/ACL/symlink capabilities instead of assuming them.
11. Native libraries have artifacts matching the OS and CPU architecture.
12. Locale, timezone, and console encoding are not assumed.
13. CI runs on both Windows and Linux with JDKs per the support matrix.
14. Test reports are retained when jobs fail.
15. Integration tests do not depend on shared services, files, or ports across jobs.

## 14. Key Takeaways

- A portable JVM does not make all OS APIs identical; filesystems, processes, shells, and native code still differ.
- `File.separator` separates path components; `File.pathSeparator` is the path-list delimiter.
- Use `Path.of`, `resolve`, and `Files` instead of string path concatenation.
- Windows is typically case-insensitive by default; common Linux filesystems are case-sensitive, though filesystem configuration can change behavior.
- Windows has reserved filenames and invalid characters; use portable names.
- Git `.gitattributes` helps keep LF/CRLF consistent across contributors.
- JDK 18+ defaults to UTF-8 for Java SE APIs; for JDK 17 and cross-system data, specify the charset explicitly.
- The POSIX permission view is not available on every filesystem; Windows primarily uses ACLs.
- `ProcessBuilder` does not invoke a shell automatically; pass arguments as a list and call the right wrapper per OS.
- Home, temp, and working directories should be retrieved from Java system properties.
- Native libraries must match the OS and CPU architecture.
- Testing on both Windows and Linux in CI helps catch portability bugs early.

Effective cross-platform Java development comes from clearly defining contracts for files, encoding, processes, and builds; using standard APIs to handle differences; and verifying behavior on each OS in CI. When assumptions are checked automatically, applications become easier to build, debug, and release on both Windows and Linux.

## References

- [Java SE 24: Path API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/nio/file/Path.html)
- [Java SE 24: Files API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/nio/file/Files.html)
- [Java SE 24: ProcessBuilder](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/ProcessBuilder.html)
- [Java SE 24: PosixFileAttributeView](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/nio/file/attribute/PosixFileAttributeView.html)
- [Oracle JDK 24 Migration Guide: Default Charset and JEP 400](https://docs.oracle.com/en/java/javase/24/migrate/migrating-jdk-8-later-jdk-releases.html)
- [Microsoft: Naming Files, Paths, and Namespaces](https://learn.microsoft.com/en-us/windows/win32/fileio/naming-a-file)
- [Microsoft: Case Sensitivity in Windows and WSL](https://learn.microsoft.com/en-us/windows/wsl/case-sensitivity)
- [Debian Reference: GNU/Linux File Basics](https://www.debian.org/doc/manuals/debian-reference/ch01.en.html)
- [Git: gitattributes and End-of-line Conversion](https://git-scm.com/docs/gitattributes)
