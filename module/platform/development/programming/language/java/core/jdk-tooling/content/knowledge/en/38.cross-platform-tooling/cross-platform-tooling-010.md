# Cross-Platform Testing for Java

## 1. Testing Objectives

Cross-platform testing verifies that Java applications, build scripts, and tools work properly across the operating systems, JDKs, and filesystems supported by the product.

Java has portable bytecode, yet runtime environments still differ:

- Windows, Linux, and macOS use different path rules, shells, file permissions, and process behaviors.
- Filesystems may be case-sensitive or case-insensitive.
- Line endings may be LF or CRLF.
- POSIX permissions, symbolic links, and file locking depend on the operating system/filesystem.
- Default locale, timezone, charset, and environment variables may differ.
- Executables, working directories, and command quoting rules may differ.
- JDK vendor, JDK version, and CPU architecture can affect the compiler, runtime, and native integration.

The goal is to run the same test suite across representative environments while accurately recognizing intentional platform differences. Do not force system values to be identical: directory separators, for example, differ between Windows and Unix-like systems.

## 2. Building an Environment Matrix

A testing matrix typically consists of three axes:

| Axis | Examples | Risks to Detect |
|---|---|---|
| OS | Windows, Ubuntu/Linux, macOS | Paths, shells, filesystems, processes, permissions. |
| JDK | 17, 21, 25 | APIs, compiler, runtime behavior, deprecations. |
| Architecture | x64, ARM64 | Native libraries, JNI, binary compatibility. |

A suitable starter matrix for a Java 17+ application:

- Windows, Ubuntu, and macOS.
- JDK 17, 21, and 25.
- Compile sources with --release 17 if Java 17 is the baseline.
- Run unit tests on each selected JDK.
- Run integration tests separately for databases, networks, native code, or external services.

The JDK used to run tests and the Java release that the source targets are two separate pieces of information. JDK 25 can compile sources with --release 17 and run tests on JDK 25. If you need to guarantee Java 17 runtime compatibility, you must still have a job that actually runs on JDK 17.

It is not necessary to run every combination for every pull request. You can use the full matrix for releases/nightly builds and a smaller subset for pull requests.

## 3. Portability Tests and Platform-Specific Tests

Portability tests verify behavior through standard APIs without depending on a specific operating system. For example, creating directories with Files.createDirectories, writing UTF-8, and reading the content back.

Platform-specific tests verify behavior that only exists on a particular platform or filesystem, such as POSIX permissions or symbolic links.

Principles:

- Assert that business results must be identical.
- Check filesystem capabilities before using optional features.
- Use JUnit assumptions to skip tests only when a capability is genuinely unavailable.
- Clearly record which tests are skipped and why.
- Do not skip tests simply because the code is failing on a platform.

You should not assert that a filesystem is always case-sensitive. Create a file and check whether a lowercase name points to the same file. This is an environmental characteristic, not a fixed pass/fail condition.

## 4. Paths and File Separators

Do not construct paths by concatenating strings with slashes or backslashes:

~~~java
String path = root + "\\reports\\result.txt";
~~~

This approach easily fails on Linux/macOS and when paths contain spaces or Unicode. Use Path, Paths, and Files:

~~~java
Path report = Path.of("build")
        .resolve("reports")
        .resolve("result.txt");

Files.createDirectories(report.getParent());
Files.writeString(report, "build completed", StandardCharsets.UTF_8);
~~~

Path.resolve automatically uses the rules of the current filesystem. For Java 17+, Path.of is the appropriate API for creating paths from components.

Do not hard-code directory separators, classpath separators, a user's home directory, or absolute paths that only exist on a developer's machine. Use File.pathSeparator when constructing a classpath. Obtain temporary directories via Files.createTempDirectory or JUnit @TempDir.

## 5. Filenames and Case Sensitivity

Windows typically uses a case-insensitive filesystem by default; Linux is typically case-sensitive; macOS depends on the filesystem and volume configuration. Two files Config.properties and config.properties may be separate files in one environment but collide in another.

Principles:

- Maintain consistent casing between filenames, resources, and imports.
- Do not create two files that differ only in case.
- Avoid Windows reserved names such as CON, NUL, PRN, AUX, COM1, and LPT1.
- Avoid filenames ending with a period or space when Windows support is required.
- Avoid invalid characters in Windows filenames such as <, >, :, double quotes, slash, backslash, |, ?, and *.
- Do not assume all filesystems support the same path length or Unicode normalization rules.

You can detect case sensitivity with a probe in a temporary directory:

~~~java
Path upper = tempDir.resolve("CaseProbe.txt");
Path lower = tempDir.resolve("caseprobe.txt");
Files.writeString(upper, "probe", StandardCharsets.UTF_8);

boolean caseSensitive = !Files.exists(lower);
System.out.println("filesystem.caseSensitive=" + caseSensitive);
~~~

Do not assert that the result is always true or always false. Record the result for diagnostics and design safe filenames.

## 6. Encoding and Unicode

Do not rely on the default charset when reading/writing files. The default charset can vary by JDK and environment. Since JDK 18, UTF-8 is the default charset per JEP 400, but projects should still specify the encoding explicitly for compatibility with JDK 17 and external non-JVM tools.

Use:

~~~java
Files.writeString(path, text, StandardCharsets.UTF_8);
String content = Files.readString(path, StandardCharsets.UTF_8);
~~~

In Maven:

~~~xml
<properties>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
~~~

In Gradle:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
~~~

Test with real Unicode content, such as accented Vietnamese text, CJK, or emoji if the application supports them. Do not test only ASCII because encoding bugs often do not surface with ASCII.

For protocols or file formats, follow the encoding defined by that format. Do not automatically convert all content to UTF-8 if the input specification mandates a different encoding.

## 7. Line Endings and Git

Common line endings:

| Form | Characters | Common On |
|---|---|---|
| LF | \n | Linux and modern macOS |
| CRLF | \r\n | Windows |
| CR | \r | Some legacy files/formats |

When generating text files for the current operating system, you can use System.lineSeparator(). When reading files originating from multiple operating systems, String.lines() or BufferedReader.readLine() handles common line terminators:

~~~java
List<String> lines = Files.readString(path, StandardCharsets.UTF_8)
        .lines()
        .toList();
~~~

If exact byte preservation is required, such as signature files or binary fixtures, do not normalize line endings. Normalize only when the format and business logic permit it.

Use .gitattributes to standardize line endings in the repository:

~~~gitattributes
* text=auto
*.java text eol=lf
*.gradle text eol=lf
*.xml text eol=lf
*.yml text eol=lf
*.yaml text eol=lf
*.sh text eol=lf
gradlew text eol=lf
*.bat text eol=crlf
mvnw text eol=lf
mvnw.cmd text eol=crlf
~~~

Do not rely on a global core.autocrlf setting as a fix for all projects. Line ending rules should be explicitly declared in the repository.

## 8. Locale, Timezone, and Date/Number Formatting

Formatting results can change depending on the default locale. Decimal separators, month names, and day/month ordering vary across regions.

When formatting machine-readable data, specify the locale explicitly:

~~~java
NumberFormat format = NumberFormat.getNumberInstance(Locale.ROOT);
DateTimeFormatter formatter = DateTimeFormatter
        .ofPattern("uuuu-MM-dd", Locale.ROOT)
        .withZone(ZoneOffset.UTC);
~~~

When handling points in time, store an Instant or epoch and convert to a specific timezone at the interface boundary. Do not rely on the CI machine's default timezone.

Example:

~~~java
String date = DateTimeFormatter.ofPattern("uuuu-MM-dd", Locale.ROOT)
        .withZone(ZoneOffset.UTC)
        .format(Instant.parse("2025-03-08T23:30:00-05:00"));
~~~

Exact output:

~~~text
2025-03-09
~~~

If a test modifies the default locale/timezone, it must restore the original value in a finally block so it does not affect other tests.

## 9. Invoking Processes Without Relying on a Shell

Avoid concatenating a command into a single string and passing it to a shell:

~~~java
Runtime.getRuntime().exec("cmd /c java -version");
~~~

cmd, PowerShell, Bash, and Zsh have different quoting/escaping rules. A command that works on Windows may not run on Linux/macOS.

Use ProcessBuilder with separate arguments:

~~~java
boolean windows = System.getProperty("os.name")
        .toLowerCase(Locale.ROOT).contains("win");

Path java = Path.of(System.getProperty("java.home"), "bin",
        windows ? "java.exe" : "java");

Process process = new ProcessBuilder(java.toString(), "-version")
        .redirectErrorStream(true)
        .start();
~~~

Add a timeout and check the exit code:

~~~java
if (!process.waitFor(10, TimeUnit.SECONDS)) {
    process.destroyForcibly();
    throw new IllegalStateException("Child process timed out");
}

String output = new String(process.getInputStream().readAllBytes(),
        StandardCharsets.UTF_8);

if (process.exitValue() != 0) {
    throw new IllegalStateException(output);
}
~~~

Do not assume an executable always has a .exe suffix, is always on PATH, or can be invoked through a shell. Derive the path from java.home when you need to run the same JDK under test.

When invoking external tools, pass an argument list, set the working directory explicitly, check the exit code, and avoid shell-dependent commands unless a shell is genuinely required.

## 10. Environment Variables and System Properties

Environment variables have different rules across operating systems. Windows is typically case-insensitive for environment variable names; Unix-like systems are case-sensitive. Do not create two variables that differ only in casing.

Useful system properties for diagnostics:

| Property | Meaning |
|---|---|
| os.name | Operating system name. |
| os.arch | CPU architecture. |
| os.version | Operating system version. |
| java.version | Java runtime version. |
| java.vendor | JDK vendor. |
| java.home | Java runtime directory. |
| file.separator | Directory separator. |
| path.separator | Path list separator. |
| line.separator | Default line separator. |
| user.dir | Current working directory. |
| user.home | User's home directory. |
| file.encoding | Default runtime encoding. |

Use Locale.ROOT when normalizing os.name:

~~~java
String os = System.getProperty("os.name").toLowerCase(Locale.ROOT);
boolean windows = os.contains("win");
boolean mac = os.contains("mac");
boolean linux = os.contains("linux");
~~~

Only use OS detection when you genuinely need to select an executable or platform-specific behavior. For filesystems, networking, and processes, prefer checking actual capabilities over inferring from os.name.

Do not log secrets from environment variables in CI. Only print necessary properties; do not print tokens, credentials, or unrelated private paths.

## 11. Filesystem Capabilities: Permissions and Symbolic Links

Not all filesystems support the same file attribute views. POSIX permissions are common on Linux/macOS, whereas Windows uses a different permission model.

Check before using:

~~~java
FileStore store = Files.getFileStore(tempDir);
boolean supportsPosix = store.supportsFileAttributeView("posix");
~~~

If unsupported, POSIX-specific tests can be skipped using a JUnit assumption:

~~~java
assumeTrue(store.supportsFileAttributeView("posix"),
        "This filesystem does not expose POSIX permissions");
~~~

Symbolic links can also be restricted by user privileges or Windows policy. When testing symlinks:

- Attempt to create the link in a temporary directory.
- Skip only if the operating system/filesystem genuinely disallows it.
- If the link is created, assert that it points to the right target and its content is readable.
- Do not ignore read/write errors on the target after the link has been created successfully.

File locking, renaming, deleting open files, and permission inheritance can also differ. Test these capabilities according to your application contract rather than assuming all filesystems share identical semantics.

## 12. Temporary Directories and Test Isolation

Do not share a fixed test directory across multiple tests or processes. Doing so causes race conditions when CI runs tests in parallel.

JUnit 5 provides @TempDir:

~~~java
class FileTest {
    @TempDir
    Path tempDir;

    @Test
    void writesAFile() throws Exception {
        Path file = tempDir.resolve("result.txt");
        Files.writeString(file, "hello", StandardCharsets.UTF_8);

        assertEquals("hello",
                Files.readString(file, StandardCharsets.UTF_8));
    }
}
~~~

JUnit manages the lifecycle of the temporary directory. Each test gets its own isolated area, reducing working directory dependencies and aiding cleanup after execution.

If tests need shared data, create immutable fixtures or create copies inside each test's own temp directory. Do not let tests depend on execution order.

## 13. Networking, Ports, and Timing

Do not hard-code ports like 8080 in integration tests when dynamic ports can be used:

~~~java
try (ServerSocket server = new ServerSocket(0)) {
    int port = server.getLocalPort();
    // Start the test client with the newly assigned port.
}
~~~

Port 0 asks the operating system to allocate an available ephemeral port. Close the socket when finished.

Considerations:

- Do not use Thread.sleep to synchronize tests if a condition-waiting mechanism is available.
- Set reasonable timeouts for processes, sockets, and asynchronous operations.
- Read/close child process streams to prevent deadlocks.
- Do not assume disk or network speeds are identical across runners.
- Retry only on well-defined transient errors; retries must not mask logic bugs.
- Do not depend on DNS or public services in unit tests.

Integration tests using databases or services should run service containers or dedicated services in CI, pin versions, and wait for health checks rather than sleeping for a fixed duration.

## 14. Cross-Platform Java Test Suite with JUnit 5

A test suite should cover common risks using standard APIs. The example below runs on Java 17+ and requires no native libraries.

Utility class src/main/java/com/example/PortablePaths.java:

~~~java
package com.example;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public final class PortablePaths {
    private PortablePaths() {
    }

    public static Path reportFile(Path root) {
        return root.resolve("dữ liệu").resolve("reports").resolve("result.txt");
    }

    public static String stableDate(Instant instant) {
        return DateTimeFormatter.ofPattern("uuuu-MM-dd", Locale.ROOT)
                .withZone(ZoneOffset.UTC)
                .format(instant);
    }

    public static void writeUtf8(Path file, String content) throws Exception {
        Files.createDirectories(file.getParent());
        Files.writeString(file, content, StandardCharsets.UTF_8);
    }
}
~~~

Test src/test/java/com/example/CrossPlatformTest.java:

~~~java
package com.example;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileStore;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermission;
import java.time.Instant;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.*;
import static org.junit.jupiter.api.Assumptions.assumeTrue;

class CrossPlatformTest {
    @TempDir
    Path tempDir;

    @Test
    void buildsPathsWithoutHardCodedSeparatorsAndSupportsUnicode() throws Exception {
        Path file = PortablePaths.reportFile(tempDir.resolve("folder with spaces"));
        PortablePaths.writeUtf8(file, "Xin chào, đa nền tảng");

        assertTrue(Files.isRegularFile(file));
        assertEquals("Xin chào, đa nền tảng",
                Files.readString(file, StandardCharsets.UTF_8));
        assertTrue(file.toString().contains("folder with spaces"));
    }

    @Test
    void readsCommonLineEndingsWithoutAssumingThePlatformSeparator() throws Exception {
        Path file = tempDir.resolve("line-endings.txt");
        Files.writeString(file, "first\r\nsecond\nthird\r", StandardCharsets.UTF_8);

        List<String> lines = Files.readString(file, StandardCharsets.UTF_8)
                .lines()
                .toList();

        assertEquals(List.of("first", "second", "third"), lines);
    }

    @Test
    void formatsDatesWithAnExplicitLocaleAndTimeZone() {
        assertEquals("2025-03-09",
                PortablePaths.stableDate(
                        Instant.parse("2025-03-08T23:30:00-05:00")));
    }

    @Test
    void launchesJavaWithoutInvokingAnOperatingSystemShell() throws Exception {
        boolean windows = System.getProperty("os.name")
                .toLowerCase(Locale.ROOT).contains("win");
        Path java = Path.of(System.getProperty("java.home"), "bin",
                windows ? "java.exe" : "java");

        assertTrue(Files.isRegularFile(java), "Java executable should exist: " + java);

        Process process = new ProcessBuilder(java.toString(), "-version")
                .redirectErrorStream(true)
                .start();

        if (!process.waitFor(10, TimeUnit.SECONDS)) {
            process.destroyForcibly();
            fail("Child JVM did not finish within 10 seconds");
        }

        String output = new String(process.getInputStream().readAllBytes(),
                StandardCharsets.UTF_8);
        assertEquals(0, process.exitValue(), output);
        assertTrue(output.toLowerCase(Locale.ROOT).contains("version"), output);
    }

    @Test
    void detectsFilesystemCaseSensitivityInsteadOfAssumingIt() throws Exception {
        Path upper = tempDir.resolve("CaseProbe.txt");
        Path lower = tempDir.resolve("caseprobe.txt");
        Files.writeString(upper, "probe", StandardCharsets.UTF_8);

        assertTrue(Files.exists(upper));
        boolean caseSensitive = !Files.exists(lower);
        System.out.println("filesystem.caseSensitive=" + caseSensitive);
    }

    @Test
    void reportsPlatformDetailsForDiagnostics() throws Exception {
        FileStore store = Files.getFileStore(tempDir);
        System.out.println("os.name=" + System.getProperty("os.name"));
        System.out.println("file.separator=" + File.separator);
        System.out.println("path.separator=" + System.getProperty("path.separator"));
        System.out.println("line.separator=" + System.lineSeparator()
                .replace("\r", "\\r").replace("\n", "\\n"));
        System.out.println("default.charset="
                + java.nio.charset.Charset.defaultCharset());
        System.out.println("filesystem.posix="
                + store.supportsFileAttributeView("posix"));
    }

    @Test
    void checksPosixPermissionsOnlyWhenTheFilesystemSupportsThem() throws Exception {
        FileStore store = Files.getFileStore(tempDir);
        assumeTrue(store.supportsFileAttributeView("posix"),
                "This filesystem does not expose POSIX permissions");

        Path file = tempDir.resolve("permissions.txt");
        Files.writeString(file, "permission probe", StandardCharsets.UTF_8);
        Set<PosixFilePermission> permissions = Files.getPosixFilePermissions(file);
        assertTrue(permissions.contains(PosixFilePermission.OWNER_READ));
    }

    @Test
    void followsSymbolicLinksWhenThePlatformAllowsCreation() throws Exception {
        Path target = tempDir.resolve("target.txt");
        Path link = tempDir.resolve("target-link.txt");
        Files.writeString(target, "linked content", StandardCharsets.UTF_8);

        try {
            Files.createSymbolicLink(link, target.getFileName());
        } catch (UnsupportedOperationException | java.io.IOException
                 | SecurityException ex) {
            assumeTrue(false, "Symbolic link creation is unavailable: " + ex);
        }

        assertTrue(Files.isSymbolicLink(link));
        assertEquals("linked content", Files.readString(link, StandardCharsets.UTF_8));
    }
}
~~~

The test suite checks paths with spaces and Unicode, UTF-8, line endings, locale/timezone, process execution, case sensitivity, POSIX capabilities, and symbolic links.

The two POSIX/symlink tests are conditionally skipped if the filesystem or user permissions do not support them. When run on Linux/macOS, those tests can execute normally.

## 15. Configuring Gradle for JUnit 5

Example build.gradle:

~~~groovy
plugins {
    id 'java'
}

group = 'com.example'
version = '1.0.0'

repositories {
    mavenCentral()
}

dependencies {
    testImplementation platform('org.junit:junit-bom:5.12.2')
    testImplementation 'org.junit.jupiter:junit-jupiter'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.12.2'
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
    options.encoding = 'UTF-8'
}

tasks.test {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'skipped', 'failed'
    }
}
~~~

Run locally:

~~~bash
./gradlew clean test
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat clean test
~~~

Use the Gradle Wrapper and commit gradlew, gradlew.bat, and gradle/wrapper/ to the repository. You can generate the wrapper with:

~~~bash
gradle wrapper --gradle-version 9.2.1
~~~

The wrapper ensures all runners use the same Gradle version. The JDK is selected separately via the CI matrix; options.release = 17 keeps the source/API target consistent.

## 16. Configuring Maven for JUnit 5

Example key sections in pom.xml:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <junit.version>5.12.2</junit.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <version>5.12.2</version>
        <scope>test</scope>
    </dependency>
</dependencies>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
            <configuration>
                <release>17</release>
                <encoding>UTF-8</encoding>
            </configuration>
        </plugin>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-surefire-plugin</artifactId>
            <version>3.5.2</version>
        </plugin>
    </plugins>
</build>
~~~

Surefire 3.5.2 runs JUnit Platform tests.

Run locally:

~~~bash
./mvnw -B clean verify
~~~

On Windows PowerShell:

~~~powershell
.\mvnw.cmd -B clean verify
~~~

Use the Maven Wrapper and commit mvnw, mvnw.cmd, and .mvn/wrapper/ to standardize the Maven version.

## 17. CI Matrix with GitHub Actions

An OS × JDK matrix can run the same test suite on Windows, Ubuntu, and macOS.

Example .github/workflows/cross-platform.yml for the Gradle Wrapper:

~~~yaml
name: Cross-platform Java tests

on:
  push:
  pull_request:
  workflow_dispatch:

jobs:
  test:
    name: ${{ matrix.os }} / Java ${{ matrix.java }}
    runs-on: ${{ matrix.os }}
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, windows-latest, macos-latest]
        java: ['17', '21', '25']

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: ${{ matrix.java }}
          cache: gradle

      - name: Run tests (Linux and macOS)
        if: runner.os != 'Windows'
        run: ./gradlew --no-daemon clean test

      - name: Run tests (Windows)
        if: runner.os == 'Windows'
        shell: pwsh
        run: .\gradlew.bat --no-daemon clean test

      - name: Upload test reports
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: test-reports-${{ matrix.os }}-java-${{ matrix.java }}
          path: build/reports/tests/test/
          if-no-files-found: ignore
~~~

The matrix above creates nine jobs: three OSes times three JDKs. fail-fast: false allows the remaining jobs to continue so you get a complete report when one combination fails.

If using Maven, change cache to maven and run ./mvnw -B clean verify on Linux/macOS; on Windows run .\mvnw.cmd -B clean verify.

Do not use OS-specific shell commands in steps shared across all runners. Split steps by runner.os when command syntax actually differs.

## 18. Testing Across Multiple JDKs

The OS matrix and the JDK matrix answer two different questions:

- The OS matrix detects differences in filesystems, processes, paths, permissions, and native binaries.
- The JDK matrix detects changes in the compiler, runtime APIs, garbage collectors, TLS, default behaviors, and deprecations.

If the project supports Java 17 and above:

1. Compile with --release 17.
2. Run unit tests on JDK 17 to verify the baseline.
3. Run on JDK 21 and JDK 25 to detect runtime changes.
4. Record java.version, java.vendor, and os.arch in CI reports.
5. Test native/JNI dependencies on the exact OS and architecture that the product distributes.

Do not simply change JAVA_HOME and assume all build steps use the new JDK. Check the version that the Maven/Gradle daemon actually uses; configure toolchains if the compiler JDK needs to differ from the build tool's runtime.

## 19. Categorizing Tests and Choosing Where to Run Them

| Test Type | Examples | Where to Run |
|---|---|---|
| Unit test | Path helpers, parsers, date formatting | Every OS/JDK in the main matrix. |
| Filesystem integration | Permissions, symlinks, file locks | OSes/filesystems supporting the capability. |
| Process integration | Running external executables | Corresponding OSes. |
| Network integration | HTTP client/server, sockets | Main matrix or dedicated service job. |
| Database integration | JDBC drivers, migrations | Service container/version matrix. |
| Native/JNI test | Loading native libraries | Exact target OS and CPU architecture. |
| Packaging test | JAR, ZIP, installers | Every artifact distribution platform. |
| End-to-end test | Installing and running the application | Release pipeline or nightly. |

Unit tests should be fast and independent. Integration tests can use service containers or version-pinned test environments. End-to-end tests should run less frequently if they are time-consuming, but must cover the actual release platforms.

Docker containers on Windows/macOS typically run Linux containers; those results do not replace native Windows/macOS testing.

## 20. Diagnosing Failures That Occur on Only One OS

When a job fails, record the following information:

~~~text
os.name
os.version
os.arch
java.version
java.vendor
java.home
file.separator
path.separator
line.separator
file.encoding
user.dir
user.home
default locale
default time zone
filesystem capability
~~~

Then compare with a passing job:

1. Identify the first failing test, rather than looking only at the final summary error.
2. Check paths and filename casing.
3. Check input encoding and line endings.
4. Check read/write/execute permissions and symbolic links.
5. Check the process executable, argument list, and working directory.
6. Check timezone/locale and default values.
7. Check JDK vendor/version and native dependencies.
8. Reproduce the failure in an environment with the same OS/JDK before changing code.

Do not fix issues by adding sleep or skipping tests on the failing OS without identifying the root cause. Logging capabilities and environment data makes reproducing failures much more accurate.

## 21. Common Pitfalls in Cross-Platform Testing

| Symptom | Cause | Solution |
|---|---|---|
| Tests pass on Windows, fail on Linux | Hard-coded backslashes in paths or wrong filename casing. | Use Path.resolve and verify resource casing. |
| Files with Vietnamese characters are corrupted | Using default charset or inconsistent encoding. | Specify UTF-8 when reading/writing and configure the compiler. |
| Parser misses lines | Assuming only CRLF or only LF. | Use String.lines()/BufferedReader or a format-compliant parser. |
| Date/number output differs | Different default locale/timezone. | Use Locale.ROOT, ZoneOffset.UTC, or an explicit business locale. |
| Child process fails to run | Invoking shell/executable with another OS's syntax. | Use ProcessBuilder argument lists and resolve the executable properly. |
| AccessDeniedException | File permissions, open file handles, or filesystem policy. | Check capabilities and close resources promptly. |
| Symlink test fails on Windows | Missing privileges or Developer Mode. | Perform capability checks and properly skip symlink tests when unsupported. |
| POSIX permission test fails | Filesystem does not support the POSIX attribute view. | Check supportsFileAttributeView("posix"). |
| Flaky tests in CI | Using shared temp files, fixed ports, or sleep. | Use @TempDir, port 0, timeouts, and condition-based waits. |
| Builds differ across JDKs | Unpinned JDK/toolchain or different compile targets. | Pin the JDK matrix and set --release. |
| Maven/Gradle uses the wrong JDK | Build daemon running on a different JDK than expected JAVA_HOME. | Print the build JVM version and configure toolchains. |
| Too many tests skipped | Overly broad assumptions or masking real bugs. | Skip only when a capability is unsupported and state the reason clearly. |
| Native library fails to load | Missing binary for the OS/architecture or wrong library path. | Build/package native binaries for each platform. |
| Git checkout alters line endings | Missing .gitattributes. | Declare the eol policy in the repository. |

## 22. Cross-Platform Testing Implementation Workflow

1. Identify the OSes, JDKs, and architectures the application commits to supporting.
2. Choose a baseline JDK and set --release accordingly.
3. Standardize source encoding and line endings with UTF-8 and .gitattributes.
4. Remove hard-coded paths, shell commands, and environment assumptions.
5. Use JUnit @TempDir to isolate each test's files.
6. Use capability checks for POSIX permissions, symlinks, and filesystem-specific behavior.
7. Create a CI matrix for Windows, Ubuntu, macOS, and supported JDKs.
8. Store test reports separately per OS/JDK.
9. Run integration tests for databases, networking, packaging, and native libraries where appropriate.
10. Investigate failures using environment logs; do not skip unexplained errors.
11. Re-run the release matrix before shipping.
12. Keep wrappers, toolchains, dependencies, and build plugins at pinned versions.

## 23. Verified Lab Results

The sample test suite above was run on Windows 11 using Gradle 9.2.1 and JUnit 5.12.2 with three installed JDKs:

| JDK | Result |
|---|---|
| Amazon Corretto 17.0.15 | BUILD SUCCESSFUL |
| Microsoft OpenJDK 21.0.9 | BUILD SUCCESSFUL |
| OpenJDK 25.0.1 | BUILD SUCCESSFUL |

Each run had six passing tests and two skipped tests. The two tests were skipped with specific reasons on the current Windows environment: the filesystem does not provide a POSIX permission view, and the current user does not have permission to create symbolic links. The remaining tests verified paths with Unicode/spaces, UTF-8, mixed line endings, fixed UTC/locale, child JVM processes, and case sensitivity detection.

These are actual test results on Windows across three JDKs. The workflow matrix above is configured to continue running the same test suite on Ubuntu and macOS in CI; results from those runners should be reviewed before concluding that the entire matrix passes.

## 24. References

- [Java NIO File API — JDK 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/package-summary.html)
- [ProcessBuilder — JDK 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ProcessBuilder.html)
- [JEP 400: UTF-8 by Default](https://openjdk.org/jeps/400)
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/)
- [Gradle Java Plugin](https://docs.gradle.org/current/userguide/java_plugin.html)
- [GitHub Actions Matrix Builds](https://docs.github.com/en/actions/using-jobs/using-a-matrix-for-your-jobs)
- [Git Attributes and Line Endings](https://git-scm.com/docs/gitattributes)

Cross-platform testing is effective when the same test suite runs across supported OSes/JDKs while platform-specific tests only run when the corresponding capability exists. Use standard Java APIs for paths, encoding, processes, and filesystems; pin build tools/JDKs; and store reports per runner so that platform-specific failures can be reproduced and fixed at their root cause.
