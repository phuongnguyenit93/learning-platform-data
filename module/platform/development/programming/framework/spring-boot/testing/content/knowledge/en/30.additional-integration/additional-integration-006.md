# Files, Paths, Charsets, and Resources in @TempDir

## 1. Learning objectives and knowledge placement

Tests that perform file I/O often fail randomly when moved from a laptop to Windows, Linux CI, or a packaged Spring Boot JAR environment. The bug is not always in business logic: a hardcoded path, an unclosed `InputStream`, differing OS default charsets, or two tests writing to the same shared directory can all cause flakiness.

JUnit Jupiter's **`@TempDir`** provides a temporary directory created and cleaned up by the test framework. Combined with `java.nio.file.Path`, `java.nio.file.Files`, `StandardCharsets.UTF_8`, and Spring's `ResourceLoader`, you can test real file logic without modifying repository files, hardcoding root paths, or depending on the current working directory.

This lesson belongs to the **Additional integration** section of the **Spring Boot – testing** module, focusing on **Files, paths, charsets, and resources in @TempDir**.

By the end of this lesson, you will be able to:

1. Use `@TempDir` with `Path` or `File` on fields and test method parameters.
2. Distinguish instance-level, static, and parameter-scoped `@TempDir`.
3. Understand default cleanup, `ON_SUCCESS`, `NEVER`, and open-resource cleanup failures.
4. Write portable test code using `Path.resolve`, `Files.createDirectories`, `Files.readString`, and `Files.writeString`.
5. Explain why `normalize` is a lexical transformation whereas `toRealPath` queries the actual filesystem.
6. Test **explicit UTF-8** charsets, Vietnamese text, emoji, raw bytes, newlines, BOM, and malformed byte sequences.
7. Distinguish classpath resources inside a JAR from real files on the filesystem.
8. Read fixtures via `ClassPathResource.getInputStream()` and read outputs via `FileSystemResource`.
9. Test input filenames, path traversal, absolute paths, Windows reserved names, existing files, and symlinks.
10. Use `@SpringBootTest` to test a real Spring service while keeping output roots isolated per `@TempDir`.
11. Understand the limitations of local temp filesystem tests relative to production volumes, cloud storage, NFS, and security races.
12. Run a complete **Java 17 + Spring Boot 3.3.5 + Gradle + JUnit Jupiter** example.

**Key takeaway:** A thorough filesystem test does not merely assert `Files.exists`; it verifies **the exact path, exact bytes, exact encoding, overwrite policy, and cleanup boundary**.

## 2. Why not hardcode file paths in JUnit tests?

A fragile example:

~~~java
@Test
void writesOutput() throws IOException {
    Path file = Path.of("C:\\temp\\report.txt");
    Files.writeString(file, "finished");
    assertTrue(Files.exists(file));
}
~~~

This is only an **illustrative snippet**, not a runnable class. It carries several risks:

- Linux machines have no `C:` drive.
- CI runners may lack write permissions at that path.
- A leftover file from an earlier run causes a **false positive**.
- Two tests running in parallel writing the same file produce nondeterministic contents.
- The test never cleans up its artifacts.
- If the app expects UTF-8, code reading with a different charset can still be broken.
- Changing the project working directory alters where relative paths write.

Better approach:

~~~java
@Test
void writesOutput(@TempDir Path tempDir)
        throws IOException {
    Path file = tempDir.resolve("report.txt");
    Files.writeString(
            file, "Completed",
            StandardCharsets.UTF_8);

    assertEquals("Completed",
            Files.readString(
                    file, StandardCharsets.UTF_8));
}
~~~

JUnit creates a fresh root scoped to the declaration; tests never need to know about `/tmp` or `%TEMP%`. All files are written beneath that root and cleaned up according to the default `@TempDir` lifecycle.

### Never write into `src/test/resources`

`src/test/resources` holds **read-only original fixtures**. Modifying a file there during tests dirties the Git workspace, affects other tests, or fails due to permissions inside a JAR/classpath. Read the fixture from the classpath, copy it into `@TempDir`, and mutate only the copy.

## 3. Lifecycle of JUnit Jupiter `@TempDir`

Exact import:

~~~java
import org.junit.jupiter.api.io.TempDir;
~~~

JUnit Jupiter provides a built-in `TempDirectory` extension. In JUnit 5.10.x managed by Spring Boot 3.3.5, common usages are test/lifecycle method parameters and fields of type `Path` or `java.io.File`.

### 3.1. Method parameter

~~~java
@Test
void writes(@TempDir Path directory)
        throws IOException {
    Files.writeString(
            directory.resolve("a.txt"), "a",
            StandardCharsets.UTF_8);
}
~~~

Ideal when a test needs a root only for a single method. It makes clear that resources are allocated per test invocation.

### 3.2. Instance field

~~~java
class ExportTest {
    @TempDir
    Path root;

    @BeforeEach
    void prepare() throws IOException {
        Files.writeString(
                root.resolve("seed.txt"), "seed",
                StandardCharsets.UTF_8);
    }

    @Test
    void usesSeed() throws IOException {
        assertEquals("seed",
                Files.readString(
                    root.resolve("seed.txt"),
                    StandardCharsets.UTF_8));
    }
}
~~~

This is an illustrative snippet omitting imports. An instance-level `@TempDir` field is shared between `@BeforeEach` and `@Test` for the **same invocation**.

### 3.3. Static field

~~~java
class SharedTempTest {
    @TempDir
    static Path sharedRoot;

    @Test
    void testA() { /* uses sharedRoot */ }

    @Test
    void testB() { /* uses sharedRoot */ }
}
~~~

A static `@TempDir` has class-level scope. It can save setup overhead, yet if tests reuse filenames or delete/mutate shared files, order dependencies and concurrency bugs arise. For integration tests without shared-fixture requirements, prefer **non-static**.

### 3.4. Invalid declarations

- `@TempDir String` is not a supported target type.
- `@TempDir final Path` fails because JUnit must inject the field.
- Never manually assign a value to a `@TempDir` field expecting JUnit to overwrite it.
- Do not use `@TempDir` on constructor parameters under **JUnit 5.10.x**; newer JUnit releases may add constructor support, but projects on Boot 3.3.5 must follow the BOM's API.
- `@TempDir` is **not a Spring bean annotation** and does not automatically wire into production `@Service` beans.

### 3.5. Cleanup policy

JUnit defaults to cleanup mode `ALWAYS`: when the scope ends, JUnit attempts to recursively delete the root and everything inside it. For debugging you can use:

~~~java
@Test
void preservesOnFailure(
        @TempDir(cleanup = CleanupMode.ON_SUCCESS)
                Path directory) {
    // If the test fails, JUnit can preserve the directory.
}
~~~

Illustrative snippet requiring `CleanupMode` import. Main options:

| Mode | Behavior | When to use |
| --- | --- | --- |
| `ALWAYS` | Attempts cleanup at scope end, even on failure | Default for CI |
| `ON_SUCCESS` | Cleans up only when the test passes | Controlled failure investigation |
| `NEVER` | Never cleans up automatically | Special debugging; must manage disk usage |

Never leave all temporary directories behind on CI just "in case"; it can fill up disk space. When cleanup fails, inspect unclosed resources and permissions before disabling cleanup.

### 3.6. Temp paths have no fixed names

JUnit/JDK may create the root under the OS temp directory (related to `java.io.tmpdir`) with a generated name. Never assert `tempDir.toString().startsWith("/tmp")`. More meaningful assertions are `Files.isDirectory(tempDir)` and `output.startsWith(tempDir)` within the same filesystem.

## 4. How `Path`, `File`, `URI`, and `Resource` differ

| Component | API | Purpose |
| --- | --- | --- |
| `Path` | `java.nio.file` | Represents a path according to a filesystem provider |
| `Files` | `java.nio.file` | Creates/reads/writes/copies/moves/deletes files |
| `File` | `java.io` | Traditional Java IO pathname |
| `URI` | `java.net` | Identifies a resource using URI syntax |
| `Resource` | Spring Core | Interface for reading resources from diverse sources |
| `ResourceLoader` | Spring Core | Resolves a resource by location string |
| `ClassPathResource` | Spring Core | Resource inside the classpath/JAR |
| `FileSystemResource` | Spring Core | Resource on the filesystem |
| `InputStream` | `java.io` | Reads raw bytes |
| `Reader` | `java.io` | Decodes bytes into characters |

For file tests, start with `Path` and `Files`. Convert to `File` only when a legacy API demands `File`:

~~~java
Path path = tempDir.resolve("data.txt");
File oldFile = path.toFile();
URI uri = path.toUri();
Resource resource = new FileSystemResource(path);
~~~

This is an illustrative snippet, not a standalone program. `toFile()` has limitations with custom filesystem providers; it is not a universal conversion for every `Path`.

### 4.1. `resolve` constructs a path; it does not create a file

~~~java
Path candidate = tempDir.resolve("reports/output.txt");
~~~

After this statement, no file exists yet. If the parent `reports` directory does not exist:

~~~java
Files.createDirectories(candidate.getParent());
Files.writeString(
        candidate, "hello", StandardCharsets.UTF_8);
~~~

`Files.createDirectories` creates any missing parent directories in the hierarchy and returns normally if they already exist as directories.

### 4.2. `normalize` only cleans up syntax

~~~java
Path path = tempDir.resolve("drafts/../ready.txt")
        .normalize();
~~~

The lexical result is `tempDir/ready.txt`. **The file does not need to exist**, and **symlinks are not resolved**. Calling `normalize` before checking paths is good practice, though insufficient as a security boundary against an attacker who can manipulate the filesystem.

### 4.3. `toAbsolutePath` vs. `toRealPath`

`toAbsolutePath` resolves a relative path against the current working directory without requiring the file to exist. `toRealPath` requires the path to exist, queries the filesystem, and typically resolves symbolic links.

~~~java
Path absolute = tempDir.toAbsolutePath().normalize();
Path real = tempDir.toRealPath();
~~~

Do not treat these two APIs as synonyms. For a root created by `@TempDir`, `toRealPath()` is well-suited for containment checks and eliminating path alias differences in tests.

### 4.4. `Path.startsWith` operates on path segments

~~~java
Path base = tempDir.toRealPath();
Path target = base.resolve("report.txt").normalize();

assertTrue(target.startsWith(base));
~~~

Use **`Path.startsWith`**, not `target.toString().startsWith(base.toString())`. As strings, `/work/outside` starts with `/work/out`, even though it is not a child of `/work/out`. Comparing path segments is far safer. Even so, symlinks and TOCTOU races require dedicated security design.

## 5. Cross-platform paths

| Way to build a path | Outcome |
| --- | --- |
| `Path.of("C:\\temp\\file.txt")` | Windows-specific syntax, non-portable |
| `Path.of("/tmp/file.txt")` | Assumes POSIX and write permissions |
| `Path.of("reports", "file.txt")` | Uses the filesystem provider's separator |
| `tempDir.resolve("reports").resolve("file.txt")` | Portable and confined inside temp root if input is trusted |
| `tempDir.toUri()` | Standard URI for the path per provider |
| `Files.createTempFile(tempDir,"part-",".txt")` | Temporary file inside the allocated root |

Never write `root.toString() + "\\\\" + name`. On Linux, `\` is a valid filename character rather than a separator; on Windows, `C:` and reserved names carry special meaning. Always use `resolve`.

### Windows reserved names

A filename can be invalid on Windows even when Linux allows it—such as `CON.txt`, `PRN.txt`, `AUX.txt`, `NUL.txt`, `COM1.txt`, and `LPT1.txt`. In the demo code below, the validator rejects these names so tests remain portable. This covers only part of a real-world filename policy; Unicode normalization, case-insensitive collisions, and long-path support must also be considered.

### Unicode filenames vs. Unicode file contents

This lesson puts **Unicode in file contents** (Vietnamese diacritics and emoji) while intentionally restricting filenames to single-component ASCII to keep path-traversal checks clear. If a product must accept accented Unicode filenames, define Unicode normalization and collision policies per target filesystem rather than loosening a regex casually.

## 6. Charsets and byte-level assertions

A Java `String` holds Unicode text; a file holds bytes. UTF-8 encodes characters into variable-length byte sequences:

~~~java
String value = "Xin chào 🌱";
byte[] bytes = value.getBytes(StandardCharsets.UTF_8);

Files.write(file, bytes);

assertArrayEquals(
        bytes, Files.readAllBytes(file));

assertEquals(
        value, Files.readString(
            file, StandardCharsets.UTF_8));
~~~

With Vietnamese diacritics and emoji, `value.length()` (UTF-16 code units) usually **differs** from `bytes.length` (UTF-8 bytes). Never use `String.length()` as the expected file size.

### 6.1. Explicit charset reads and writes

~~~java
Files.writeString(
    file, "Tiếng Việt có dấu",
    StandardCharsets.UTF_8);

String read = Files.readString(
    file, StandardCharsets.UTF_8);
~~~

In Java 17, the `Files.writeString/readString` overloads without a charset default to UTF-8 per API, yet passing `StandardCharsets.UTF_8` explicitly makes the file contract clear and avoids confusion with other APIs/versions that use the platform default charset.

### 6.2. Avoid blind default charsets

~~~java
String text = new String(byteArray);
~~~

If the file contract is UTF-8, write:

~~~java
String text = new String(
    byteArray, StandardCharsets.UTF_8);
~~~

Java 17 does not guarantee every process/locale shares the same platform default charset, and legacy files may specify another encoding. Tests should encode/decode using the **file's contract**, never guessing from the OS.

### 6.3. Wrong-charset corruption

`Café` in UTF-8 encodes `é` as bytes `C3 A9`. Decoded as ISO-8859-1, those two bytes become two characters `Ã©`, yielding `CafÃ©`. A test that deliberately reads with the wrong charset and asserts the difference shows why **getting a String back** does not mean **decoding succeeded**.

### 6.4. Malformed UTF-8

Bytes `C3 28` do not form a valid UTF-8 sequence:

~~~java
Files.write(file, new byte[]{
    (byte) 0xC3, (byte) 0x28
});

assertThrows(
    MalformedInputException.class,
    () -> Files.readString(
        file, StandardCharsets.UTF_8));
~~~

`Files.readString` throws `MalformedInputException` under strict decoding. Other decoders/readers may substitute replacement characters when configured to do so. When the contract forbids invalid byte sequences, enforce strict decoding intentionally.

### 6.5. Text vs. binary

PDF/ZIP/JPEG/binary payloads must never be routed arbitrarily through `String`. Use `Files.readAllBytes`/`write`, stream I/O, and byte/checksum assertions. Never "fix" binary data by forcing UTF-8 or ISO-8859-1.

## 7. Newlines, BOM, and file formatting

### LF vs. CRLF

- `\n` = LF, a single byte `0A` in UTF-8.
- `\r\n` = CRLF, two bytes `0D 0A`.
- `System.lineSeparator()` depends on the runtime platform.

If a JSONL or text export contract specifies LF, write `"\n"` explicitly. If the format requires native line endings, tests should use `System.lineSeparator()` instead of hardcoding Linux or Windows endings.

### UTF-8 BOM

A file can begin with bytes `EF BB BF`, corresponding to `U+FEFF`. Java's `Files.readString(..., UTF_8)` does not treat a BOM as an automatic instruction to strip it, so the resulting string starts with `\uFEFF`. Example:

~~~java
Files.write(file, new byte[]{
    (byte) 0xEF, (byte) 0xBB,
    (byte) 0xBF, (byte) 'A'
});

String text = Files.readString(
    file, StandardCharsets.UTF_8);

assertEquals("\uFEFFA", text);
~~~

When the contract specifies "UTF-8 without BOM," tests should inspect leading bytes to confirm no BOM signature is present. When BOM is allowed, handle it intentionally. Never rely on `strip()` to remove `U+FEFF`, as Unicode whitespace rules do not handle BOM consistently.

### Line readers can strip newline styles

`Files.readAllLines` and `Files.lines` return lines without preserving each line terminator. To verify CRLF vs. LF, use `Files.readAllBytes` and compare expected bytes rather than comparing split `List<String>` lines.

### Streaming vs. in-memory

`readAllBytes`/`readString` load the entire file into memory, suitable for small fixtures. For large files, use `Files.newBufferedReader`, `Files.newInputStream`, or `Files.lines`, and close every resource promptly:

~~~java
try (BufferedReader reader =
        Files.newBufferedReader(
            file, StandardCharsets.UTF_8)) {
    String first = reader.readLine();
    assertEquals("header", first);
}
~~~

On Windows, leaving streams open can cause test cleanup to fail because of file locks. Never use `Thread.sleep` to "wait for the OS to release the file" instead of closing resources properly.

## 8. Spring `Resource`: classpath does not mean a filesystem file

Spring Boot provides several resource implementations:

- `ClassPathResource`: data on the classpath, inside a directory or a JAR.
- `FileSystemResource`: data on the filesystem.
- `UrlResource`: data accessed via a URL/URI.
- `PathResource`: backed by an NIO `Path`.
- `ByteArrayResource`: in-memory byte array used in tests/libraries.

A classpath fixture at `src/main/resources/reports/header.txt` in the source tree appears as a file under `build/resources/main` during tests. However, once packaged into an executable JAR, the fixture resides **inside the JAR**.

### 8.1. Portable pattern

~~~java
Resource header =
    new ClassPathResource("reports/header.txt");

try (InputStream input = header.getInputStream()) {
    String text = new String(
        input.readAllBytes(),
        StandardCharsets.UTF_8);
}
~~~

`getInputStream()` works properly for packaged classpath resources.

### 8.2. Non-portable pattern

~~~java
File file = new ClassPathResource(
        "reports/header.txt").getFile();
~~~

When the resource lives inside a JAR, `getFile()` throws `FileNotFoundException` because there is no standalone filesystem file. Passing in an IDE or exploded classpath does not prove the packaged app works.

### 8.3. `ResourceLoader`

~~~java
Resource resource = resourceLoader.getResource(
        "classpath:reports/header.txt");
~~~

`ResourceLoader` takes a resource location and returns the corresponding implementation. With a `file:` URI, it accesses the filesystem. **Never let untrusted user input dictate resource URLs or schemes**, as that opens local-file disclosure or SSRF risks; when locations involve external input, enforce strict scheme/path allowlists.

### 8.4. Copying a fixture into `@TempDir`

~~~java
Resource source =
    new ClassPathResource("reports/header.txt");

Path copied = tempDir.resolve("header.txt");

try (InputStream in = source.getInputStream()) {
    Files.copy(in, copied);
}

assertEquals(
    "BÁO CÁO",
    Files.readString(
        copied, StandardCharsets.UTF_8).strip());
~~~

You can modify the copy inside the temp root without touching the original fixture. This pattern works great for CSV inputs, JSON fixtures, templates, XML configs, PDFs, and sample archives.

## 9. Path traversal and overwrites: designing negative tests

When a service accepts a filename from a request/user, never build output paths directly like this:

~~~java
Path output = root.resolve(userFileName);
Files.writeString(output, body);
~~~

A filename like `../secrets.txt` escapes the root; Windows adds drive letters, UNC paths, backslashes, and reserved names. Even when `normalize().startsWith(root)` passes lexically, a **symbolic link inside the directory tree** can point outside.

### Control principles

1. If business logic only needs a filename, **accept only a basename**, never a full path.
2. Enforce a strict allowlist of characters, extensions, and length.
3. Reject `..`, path separators, absolute paths, reserved names, and control characters.
4. Use a trusted root, `resolve`, `normalize`, and containment checks.
5. Never use String prefix checks for paths.
6. Use `CREATE_NEW` when the contract **forbids overwriting** existing outputs.
7. Separate server-generated storage names from user-supplied display names where appropriate.
8. Evaluate symlink/path races under your threat model; lexical checks cannot completely prevent TOCTOU races.
9. Never let test processes touch paths outside `@TempDir`.
10. When an app uses multi-tenant storage, enforce ownership/tenant boundaries in addition to filename validation.

### How does `CREATE_NEW` help?

~~~java
Files.writeString(
        target,
        body,
        StandardCharsets.UTF_8,
        StandardOpenOption.CREATE_NEW,
        StandardOpenOption.WRITE);
~~~

If a file or symbolic link already exists at `target`, this throws `FileAlreadyExistsException` rather than truncating or replacing existing data. New-file creation semantics are enforced at the filesystem provider level; this operation **does not automatically make writing the content atomic**. If writing fails midway, the target may contain partial content.

### Symlinks and trusted roots

In the runnable example, filenames are restricted to an ASCII allowlist with no separators, the root is trusted from the caller, and files are created with `CREATE_NEW`. If an attacker can alter the root or create symlinks in parent directories, this is still **not a general-purpose filesystem security sandbox**. Production handling of untrusted archives/uploads needs directories with strict ownership, descriptor-based safe traversal where available, and race-aware file APIs.

## 10. Complete project: Java 17 + Spring Boot 3.3.5 + Gradle

The project demonstrates a real Spring service: reading a header from classpath resource `reports/header.txt`, combining it with a Unicode body, and exporting a `.txt` file into a `Path root` supplied by the test. Tests are split into:

- **JUnit NIO tests** for `Path`, `Files`, charsets, binary data, copy/move, and streams.
- **Service unit integration tests** using a real `DefaultResourceLoader` without starting an `ApplicationContext`.
- **Resource boundary tests** checking classpath and file resources.
- **Spring Boot integration tests** with `@Autowired ReportExportService` and a fresh `@TempDir` per method.

### 10.1. File tree

~~~text
tempdir-resource-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/
│   ├── gradle-wrapper.jar
│   └── gradle-wrapper.properties
└── src/
    ├── main/
    │   ├── java/com/example/tempfiles/
    │   │   ├── TempFileApplication.java
    │   │   └── ReportExportService.java
    │   └── resources/reports/
    │       └── header.txt
    └── test/java/com/example/tempfiles/
        ├── NioTempDirTest.java
        ├── ReportExportServiceTest.java
        ├── ResourceBoundaryTest.java
        └── ReportExportServiceSpringBootTest.java
~~~

Gradle Wrapper scripts/JAR should be generated with a compatible Gradle version or copied from a repo. `gradle-wrapper.jar` is a binary and cannot be copied out of Markdown text.

### 10.2. settings.gradle

~~~groovy
rootProject.name = 'tempdir-resource-lab'
~~~

### 10.3. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

`spring-boot-starter` supplies Spring Core, DI, and `ResourceLoader`. `spring-boot-starter-test` supplies JUnit Jupiter, Spring Boot Test, and assertions. NIO is part of the JDK, so no extra dependency is needed. No database, HTTP server, Testcontainers, or Docker is required.

### 10.4. `src/main/java/com/example/tempfiles/TempFileApplication.java`

~~~java
package com.example.tempfiles;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TempFileApplication {

    public static void main(String[] args) {
        SpringApplication.run(TempFileApplication.class, args);
    }
}
~~~

The application root sits in the same package as the service so component scanning finds `@Service`. `@SpringBootTest(webEnvironment=NONE)` loads only the Spring context without opening an HTTP port.

### 10.5. `src/main/resources/reports/header.txt`

~~~text
BÁO CÁO
~~~

This file must be saved as UTF-8. Editors may append a trailing newline; the service calls `stripTrailing()` on the header so concatenated output stays consistent. When production templates must preserve trailing whitespace, **do not** strip arbitrarily.

### 10.6. `src/main/java/com/example/tempfiles/ReportExportService.java`

~~~java
package com.example.tempfiles;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Locale;
import java.util.Objects;
import java.util.Set;
import java.util.regex.Pattern;

import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;
import org.springframework.stereotype.Service;

@Service
public class ReportExportService {

    private static final Pattern SAFE_NAME =
            Pattern.compile(
                "[A-Za-z0-9][A-Za-z0-9._-]{0,79}\\.txt");

    private static final Set<String> RESERVED =
            Set.of("CON", "PRN", "AUX", "NUL");

    private static final String HEADER_LOCATION =
            "classpath:reports/header.txt";

    private final ResourceLoader resourceLoader;

    public ReportExportService(ResourceLoader resourceLoader) {
        this.resourceLoader =
                Objects.requireNonNull(resourceLoader);
    }

    public Path export(
            Path root, String fileName, String body)
            throws IOException {

        Objects.requireNonNull(root, "root");
        Objects.requireNonNull(body, "body");
        validateFileName(fileName);

        Path base = root.toAbsolutePath().normalize();
        Files.createDirectories(base);

        // Root in the demo is provided and trusted by the caller.
        base = base.toRealPath();

        Path target = base.resolve(fileName).normalize();
        if (!target.startsWith(base)) {
            throw new IllegalArgumentException(
                    "Output escapes export root");
        }

        Resource headerResource =
                resourceLoader.getResource(HEADER_LOCATION);

        String header;
        try (InputStream stream =
                headerResource.getInputStream()) {
            header = new String(
                    stream.readAllBytes(),
                    StandardCharsets.UTF_8).stripTrailing();
        }

        String contents = header + "\n" + body + "\n";

        // CREATE_NEW: do not overwrite an existing file or link.
        return Files.writeString(
                target,
                contents,
                StandardCharsets.UTF_8,
                StandardOpenOption.CREATE_NEW,
                StandardOpenOption.WRITE);
    }

    private static void validateFileName(
            String fileName) {

        if (fileName == null
                || !SAFE_NAME.matcher(fileName).matches()
                || fileName.contains("..")) {
            throw new IllegalArgumentException(
                    "Invalid report filename");
        }

        String stem = fileName.substring(
                0, fileName.length() - ".txt".length());

        String firstPart = stem.split("\\.", 2)[0]
                .toUpperCase(Locale.ROOT);

        if (RESERVED.contains(firstPart)
                || firstPart.matches("COM[1-9]|LPT[1-9]")) {
            throw new IllegalArgumentException(
                    "Reserved report filename");
        }
    }
}
~~~

### 10.7. Service walkthrough

**Do not store a mutable root in a singleton.** `ReportExportService` is a Spring singleton, yet `Path root` is an argument to `export`. Each test can pass a fresh `@TempDir` without restarting the Spring context.

**Read the header from classpath via `InputStream`.** Never call `resource.getFile()`, so the app still reads the resource when packaged as a JAR.

**Explicit UTF-8 and LF.** The service constructs `header + "\n" + body + "\n"` and writes with `UTF_8`. Tests can assert exact bytes on both Windows and Linux.

**Clear filename policy.** The sample permits only an ASCII basename ending in `.txt`, free of `..` and Windows device names. It rejects `../escape.txt`, `C:\\temp\\...`, `sub/report.txt`, `report.csv`, and invalid names.

**The output root is assumed trusted.** The code creates the root if missing, normalizes it, calls `toRealPath`, and resolves the file. With roots provided by `@TempDir`, this contract fits cleanly. An attacker-controlled root requires deeper security design.

**`CREATE_NEW` prevents overwrites.** Existing files are never truncated. If I/O fails mid-write, a partial output file could remain; when atomic export is required, add a temp-write + atomic-move pattern.

## 11. NIO `@TempDir` tests: Java 17, JUnit Jupiter

**`src/test/java/com/example/tempfiles/NioTempDirTest.java`**

~~~java
package com.example.tempfiles;

import java.io.IOException;
import java.nio.charset.MalformedInputException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import static org.junit.jupiter.api.Assertions.*;

class NioTempDirTest {

    @TempDir
    Path workDir;

    @Test
    void injectedRootExistsAndIsDirectory() {
        assertTrue(Files.isDirectory(workDir));
        assertTrue(Files.isWritable(workDir));
    }

    @Test
    void methodParameterCanUseItsOwnTempDir(
            @TempDir Path separate) throws IOException {

        Path file = separate.resolve("note.txt");
        Files.writeString(file, "isolated",
                StandardCharsets.UTF_8);

        assertTrue(Files.isDirectory(separate));
        assertEquals("isolated",
                Files.readString(file,
                        StandardCharsets.UTF_8));
    }

    @Test
    void utf8RoundTripPreservesVietnameseAndEmoji()
            throws IOException {

        String text = "Tiếng Việt: Hà Nội, Cần Thơ 🌱\n";
        Path file = workDir.resolve("viet.txt");

        Files.writeString(file, text,
                StandardCharsets.UTF_8);

        assertEquals(text,
                Files.readString(file,
                        StandardCharsets.UTF_8));

        assertArrayEquals(
                text.getBytes(StandardCharsets.UTF_8),
                Files.readAllBytes(file));

        assertEquals(
                text.getBytes(StandardCharsets.UTF_8).length,
                Files.size(file));
    }

    @Test
    void nestedDirectoriesAndNormalizeWork()
            throws IOException {

        Path directory =
                workDir.resolve("reports/2026");
        Files.createDirectories(directory);

        Path target =
                directory.resolve("../final.txt")
                    .normalize();

        assertEquals(
                workDir.resolve("reports/final.txt"),
                target);
        assertTrue(target.startsWith(workDir));

        Files.writeString(target, "ready",
                StandardCharsets.UTF_8);

        assertEquals("ready",
                Files.readString(target,
                        StandardCharsets.UTF_8));
    }

    @Test
    void createTempFileIsInsideInjectedRoot()
            throws IOException {

        Path file = Files.createTempFile(
                workDir, "part-", ".csv");

        assertTrue(Files.exists(file));
        assertTrue(file.startsWith(workDir));

        Files.writeString(file,
                "id,name\n1,A\n",
                StandardCharsets.UTF_8);

        assertEquals(
                "id,name\n1,A\n",
                Files.readString(file,
                        StandardCharsets.UTF_8));
    }

    @Test
    void wrongCharsetCorruptsText()
            throws IOException {

        Path file = workDir.resolve("encoding.txt");
        Files.writeString(file, "Café",
                StandardCharsets.UTF_8);

        String wrong = Files.readString(
                file, StandardCharsets.ISO_8859_1);

        assertEquals("CafÃ©", wrong);
        assertNotEquals("Café", wrong);

        assertEquals("Café",
                Files.readString(file,
                        StandardCharsets.UTF_8));
    }

    @Test
    void malformedUtf8MustNotBeSilentlyAccepted()
            throws IOException {

        Path file = workDir.resolve("bad.txt");
        Files.write(file, new byte[]{
                (byte) 0xC3, (byte) 0x28
        });

        assertThrows(MalformedInputException.class,
                () -> Files.readString(
                    file, StandardCharsets.UTF_8));
    }

    @Test
    void binaryFileRoundTripUsesBytes()
            throws IOException {

        Path file = workDir.resolve("payload.bin");
        byte[] payload = {
                0x00, 0x01, (byte) 0xFF, 0x7F
        };

        Files.write(file, payload);

        assertArrayEquals(
                payload, Files.readAllBytes(file));
    }

    @Test
    void copyAndMovePreserveFileContents()
            throws IOException {

        Path source = workDir.resolve("source.txt");
        Path copy = workDir.resolve("copy.txt");
        Path moved = workDir.resolve("moved.txt");

        Files.writeString(source, "bản gốc",
                StandardCharsets.UTF_8);

        Files.copy(source, copy);
        Files.move(copy, moved);

        assertTrue(Files.exists(source));
        assertFalse(Files.exists(copy));
        assertTrue(Files.exists(moved));
        assertArrayEquals(
                Files.readAllBytes(source),
                Files.readAllBytes(moved));
    }

    @Test
    void filesLinesStreamIsAlwaysClosed()
            throws IOException {

        Path file = workDir.resolve("rows.txt");
        Files.writeString(file,
                "one\ntwo\nthree\n",
                StandardCharsets.UTF_8);

        List<String> lines;
        try (Stream<String> source =
                Files.lines(file, StandardCharsets.UTF_8)) {
            lines = source.toList();
        }

        assertEquals(
                List.of("one", "two", "three"), lines);
    }
}
~~~

### Why are these assertions meaningful?

- Never relies on the random temp root name; only verifies it is a directory.
- Unicode text is checked in both **String and raw bytes**.
- `Files.size` is compared against UTF-8 byte length, not `text.length()`.
- Nested directories are created before writing; `normalize` is checked lexically.
- `Files.createTempFile(workDir,...)` creates the file inside the injected root, not outside.
- The wrong-charset test uses `Café` to prove silent corruption can happen without an exception.
- The malformed UTF-8 test confirms strict decoding policy.
- The binary test never decodes bytes into Strings.
- The copy/move test asserts old/new paths and byte contents.
- `Files.lines` is closed via try-with-resources before `@TempDir` cleanup runs.

### Do not assume `ATOMIC_MOVE` on every filesystem

In the test above, `Files.move(copy, moved)` does not require atomic semantics because the goal is simply **content/relocation**. If a business contract requires atomic moves, use `StandardCopyOption.ATOMIC_MOVE` in a dedicated test and handle `AtomicMoveNotSupportedException` on unsupported providers. Do not turn a filesystem-dependent feature into a blanket portability assumption for the entire suite.

## 12. Testing the service: UTF-8 data, traversal, duplicates, and symlinks

**`src/test/java/com/example/tempfiles/ReportExportServiceTest.java`**

~~~java
package com.example.tempfiles;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import org.junit.jupiter.api.Assumptions;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.core.io.DefaultResourceLoader;

import static org.junit.jupiter.api.Assertions.*;

class ReportExportServiceTest {

    private final ReportExportService service =
            new ReportExportService(
                    new DefaultResourceLoader());

    @Test
    void writesHeaderAndBodyAsUtf8(
            @TempDir Path root) throws IOException {

        Path output = service.export(
                root, "report-01.txt",
                "Khách hàng: Đặng");

        assertTrue(output.startsWith(root.toRealPath()));
        String expected =
                "BÁO CÁO\nKhách hàng: Đặng\n";

        assertEquals(expected,
                Files.readString(
                    output, StandardCharsets.UTF_8));

        assertArrayEquals(
                expected.getBytes(StandardCharsets.UTF_8),
                Files.readAllBytes(output));
    }

    @Test
    void duplicateWriteFailsWithoutChangingOldContent(
            @TempDir Path root) throws IOException {

        Path output = service.export(
                root, "report.txt", "first");

        assertThrows(
            FileAlreadyExistsException.class,
            () -> service.export(
                root, "report.txt", "second"));

        assertEquals(
                "BÁO CÁO\nfirst\n",
                Files.readString(
                    output, StandardCharsets.UTF_8));
    }

    @Test
    void rejectsParentTraversalAndSeparators(
            @TempDir Path root) {

        List<String> badNames = List.of(
                "../outside.txt",
                "sub/report.txt",
                "..\\windows.txt",
                "report..txt");

        for (String name : badNames) {
            assertThrows(
                IllegalArgumentException.class,
                () -> service.export(
                    root, name, "data"),
                "Should reject: " + name);
        }
    }

    @Test
    void rejectsAbsolutePath(
            @TempDir Path root) {

        String absolute = root
                .resolve("outside.txt")
                .toAbsolutePath()
                .toString();

        assertThrows(
            IllegalArgumentException.class,
            () -> service.export(
                root, absolute, "data"));
    }

    @Test
    void rejectsInvalidNamesAndWindowsDeviceNames(
            @TempDir Path root) {

        assertThrows(
            IllegalArgumentException.class,
            () -> service.export(
                root, null, "x"));

        for (String name : List.of(
                "", "bad name.txt",
                "CON.txt", "COM1.txt",
                "report.csv",
                ".hidden.txt",
                "report.txt/child")) {

            assertThrows(
                IllegalArgumentException.class,
                () -> service.export(
                    root, name, "x"),
                "Should reject: " + name);
        }
    }

    @Test
    void createsTrustedNestedRoot(
            @TempDir Path root) throws IOException {

        Path nested = root.resolve("reports/daily");
        Path output = service.export(
                nested, "daily.txt", "Đã xử lý");

        assertTrue(Files.isDirectory(nested));
        assertTrue(output.startsWith(
                nested.toRealPath()));

        assertEquals(
                "BÁO CÁO\nĐã xử lý\n",
                Files.readString(
                    output, StandardCharsets.UTF_8));
    }

    @Test
    void doesNotReplaceExistingSymbolicLink(
            @TempDir Path root) throws IOException {

        Path original = root.resolve("original.txt");
        Files.writeString(
                original, "untouched",
                StandardCharsets.UTF_8);

        Path link = root.resolve("alias.txt");

        try {
            Files.createSymbolicLink(link, original);
        } catch (IOException
                 | UnsupportedOperationException
                 | SecurityException unavailable) {

            Assumptions.assumeTrue(
                false,
                "OS or filesystem does not permit symlink");
        }

        assertThrows(
            FileAlreadyExistsException.class,
            () -> service.export(
                root, "alias.txt", "hijack"));

        assertEquals(
                "untouched",
                Files.readString(
                    original, StandardCharsets.UTF_8));
    }

    @Test
    void rejectsNullBodyWithoutCreatingOutput(
            @TempDir Path root) {

        assertThrows(
            NullPointerException.class,
            () -> service.export(
                root, "null.txt", null));

        assertFalse(Files.exists(
                root.resolve("null.txt")));
    }
}
~~~

### What do the negative cases catch?

**Traversal and absolute paths:** Without filename validation, inputs like `../outside.txt` or `sub/report.txt` could write to unintended paths. In this lab, both POSIX and Windows separators are rejected by policy on every OS.

**Duplicates:** `CREATE_NEW` ensures existing files are not overwritten. If a developer switches to default `Files.writeString(target, contents)`, `duplicateWriteFailsWithoutChangingOldContent` fails immediately.

**Device names:** A filename valid on Linux can break on Windows. The test rejects `CON.txt` and `COM1.txt` at the application layer instead of waiting for the Windows filesystem to fail.

**Symbolic links:** When the OS permits creating a symlink in `@TempDir`, the target link path already exists, so `CREATE_NEW` refuses to overwrite it. If Windows policy or the filesystem disallows symlinks, JUnit marks the test **SKIPPED** rather than falsely claiming the security policy was fully exercised.

**Null body:** Programming errors on inputs must fail before creating the output file, preventing unexpected empty files from being written.

### Why not mock `ResourceLoader`?

The service unit test uses `new DefaultResourceLoader()`, so it genuinely reads `classpath:reports/header.txt`. A mock hardcoded to return a test header string would pass even if the resource path in source disappeared or moved. Since this lesson verifies the **classpath resource boundary**, using the real Spring Core implementation is appropriate.

## 13. Testing Spring `ClassPathResource`, `FileSystemResource`, and `ResourceLoader`

**`src/test/java/com/example/tempfiles/ResourceBoundaryTest.java`**

~~~java
package com.example.tempfiles;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.DefaultResourceLoader;
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;

import static org.junit.jupiter.api.Assertions.*;

class ResourceBoundaryTest {

    @Test
    void copiesClasspathResourceIntoTempRoot(
            @TempDir Path root) throws IOException {

        Resource fixture = new ClassPathResource(
                "reports/header.txt");
        assertTrue(fixture.exists());

        Path copy = root.resolve("copy.txt");
        try (InputStream input = fixture.getInputStream()) {
            Files.copy(input, copy);
        }

        assertEquals("BÁO CÁO",
                Files.readString(
                    copy, StandardCharsets.UTF_8).strip());
    }

    @Test
    void filesystemResourceReadsTempFile(
            @TempDir Path root) throws IOException {

        Path file = root.resolve("note.txt");
        Files.writeString(
                file, "Tiếng Việt",
                StandardCharsets.UTF_8);

        Resource resource = new FileSystemResource(file);

        try (InputStream input = resource.getInputStream()) {
            assertEquals(
                "Tiếng Việt",
                new String(
                    input.readAllBytes(),
                    StandardCharsets.UTF_8));
        }
    }

    @Test
    void resourceLoaderResolvesClasspathAndFileUri(
            @TempDir Path root) throws IOException {

        ResourceLoader loader = new DefaultResourceLoader();

        Resource classpath = loader.getResource(
                "classpath:reports/header.txt");

        try (InputStream input = classpath.getInputStream()) {
            assertEquals(
                "BÁO CÁO",
                new String(
                    input.readAllBytes(),
                    StandardCharsets.UTF_8).strip());
        }

        Path target = root.resolve("from-uri.txt");
        Files.writeString(
                target, "file uri",
                StandardCharsets.UTF_8);

        Resource fromFileUri = loader.getResource(
                target.toUri().toString());

        try (InputStream input = fromFileUri.getInputStream()) {
            assertEquals(
                "file uri",
                new String(
                    input.readAllBytes(),
                    StandardCharsets.UTF_8));
        }
    }
}
~~~

### Why not test `getFile()` on the classpath fixture?

The classpath fixture happens to be a file on disk during a Gradle test run, so `getFile()` would pass. Once packaged as an executable JAR, it is no longer a standalone file. Testing the true contract means **opening `InputStream`** and reading contents. When packaged-JAR behavior must be verified, add a smoke test launching the artifact itself.

### `ResourceLoader` is not a security sandbox

If a resource location comes from an HTTP request, never call `getResource(userLocation)` blindly. An input such as `file:///etc/passwd` or `https://unknown.example/...` can allow unauthorized reads depending on implementation and runtime permissions. Lock down prefixes/schemes/paths per business contract or choose resource types directly from trusted sources.

## 14. Testing Spring Boot bean wiring with `@TempDir`

**`src/test/java/com/example/tempfiles/ReportExportServiceSpringBootTest.java`**

~~~java
package com.example.tempfiles;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(
    classes = TempFileApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE)
class ReportExportServiceSpringBootTest {

    @Autowired
    private ReportExportService service;

    @Test
    void bootInjectsRealResourceLoaderAndExports(
            @TempDir Path root) throws IOException {

        assertNotNull(service);

        Path file = service.export(
                root, "boot.txt", "Đơn hàng: 42");

        assertEquals(
                "BÁO CÁO\nĐơn hàng: 42\n",
                Files.readString(
                    file, StandardCharsets.UTF_8));

        assertTrue(file.startsWith(root.toRealPath()));
    }

    @Test
    void singletonServiceDoesNotReusePathAcrossTests(
            @TempDir Path root) throws IOException {

        Path file = service.export(
                root, "same.txt", "one");

        assertThrows(
            FileAlreadyExistsException.class,
            () -> service.export(
                root, "same.txt", "two"));

        assertEquals(
                "BÁO CÁO\none\n",
                Files.readString(
                    file, StandardCharsets.UTF_8));
    }
}
~~~

### Why do `@SpringBootTest` and `@TempDir` work cleanly together?

`@SpringBootTest` creates the Spring `ApplicationContext` and injects `ReportExportService` via component scanning. JUnit creates a fresh `@TempDir` per test method. Because the singleton service **holds no `Path` field**, the exact same bean can write into root A in method 1 and root B in method 2 with zero order dependency.

Contrast that with designs binding a root property into a constructor once: changing `demo.export.root` between test methods **does not update** the singleton's field when the Spring context is cached. When an output root must come from configuration, use a stable class-scoped root aligned with context lifetime, or use test-specific bean configurations.

### Is this an end-to-end filesystem test?

It genuinely reads a classpath resource through a Spring bean and writes to the local filesystem inside JUnit's temp root. It does **not** test network filesystems, production volume mounts, Docker overlay permissions, or S3. Claims should match what the assertions actually verify.

## 15. Summary of test cases and expected results

The source suite contains **23 `@Test` methods**:

| Class | Test count | Scope |
| --- | ---: | --- |
| `NioTempDirTest` | 10 | Directories, paths, charsets, binary, copy/move, streams |
| `ReportExportServiceTest` | 8 | UTF-8 export, filenames, duplicates, symlinks |
| `ResourceBoundaryTest` | 3 | `ClassPathResource` / `FileSystemResource` / `ResourceLoader` |
| `ReportExportServiceSpringBootTest` | 2 | Spring DI and file I/O per `@TempDir` |
| **Total** | **23** | Focus on I/O correctness and isolation |

These examples are authored source code, **not executed with Gradle/JUnit in this environment**. When run, all 23 tests are expected to pass on standard filesystems; the symlink test may be marked skipped by JUnit if the OS disallows creating symlinks.

### Run commands

Requires JDK 17, Gradle Wrapper, and initial access to download Maven dependencies. No Docker needed.

Linux/macOS:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Run a single class:

~~~bash
./gradlew test --tests 'com.example.tempfiles.NioTempDirTest'
./gradlew test --tests 'com.example.tempfiles.ReportExportServiceTest'
./gradlew test --tests 'com.example.tempfiles.ResourceBoundaryTest'
./gradlew test --tests 'com.example.tempfiles.ReportExportServiceSpringBootTest'
~~~

On Windows, replace `./gradlew` with `.\gradlew.bat`.

Typical reports:

~~~text
build/
├── reports/tests/test/index.html
└── test-results/test/
    ├── TEST-com.example.tempfiles.NioTempDirTest.xml
    ├── TEST-com.example.tempfiles.ReportExportServiceTest.xml
    ├── TEST-com.example.tempfiles.ResourceBoundaryTest.xml
    └── TEST-com.example.tempfiles.ReportExportServiceSpringBootTest.xml
~~~

If Gradle reports `UP-TO-DATE` or `FROM-CACHE`, do not assume the tests just executed. When diagnosing:

~~~bash
./gradlew test --rerun-tasks
~~~

If no wrapper exists yet and a compatible Gradle version is installed:

~~~bash
gradle wrapper --gradle-version 8.8 --distribution-type bin
~~~

Commit the generated Wrapper files per repository policy. The test code has no `System.out.println` calls, so there is no fixed business stdout; paths and Gradle logs depend on the environment.

## 16. Change one line—which test fails?

Manual mutation checks help evaluate test strength:

| Intentional mutation on scratch branch | Test expected to catch it |
| --- | --- |
| Change UTF-8 to ISO-8859-1 when writing report | `writesHeaderAndBodyAsUtf8` |
| Drop classpath header, write body only | Service/Boot content assertions |
| Remove `CREATE_NEW` and allow overwrites | `duplicateWriteFailsWithoutChangingOldContent` |
| Remove filename policy | Traversal/absolute/reserved-name tests |
| Allow `COM1.txt` | Device-name negative test |
| Replace `"\n"` with `System.lineSeparator()` | Exact content test on CRLF environments |
| Change resource path to nonexistent location | Service/resource tests |
| Remove `@Service` | Spring Boot injection test |
| Use `ClassPathResource.getFile` instead of `InputStream` | Might fail only in packaged-JAR smoke test |
| Write output file to working directory | Path containment assertions |
| Leave `Files.lines` unclosed | May cause cleanup failure, especially on Windows |

After confirming the test turns red, **revert** the change. Never merge intentional path-traversal bugs into production or CI against real directories.

## 17. Common errors and troubleshooting

| Symptom | Possible cause | Fix |
| --- | --- | --- |
| `NoSuchFileException` | Parent directory not created | `Files.createDirectories` |
| `FileAlreadyExistsException` | `CREATE_NEW` hit existing file/link | Use a new filename or assert overwrite policy |
| `AccessDeniedException` | Missing permissions or locked file | Check permissions, open handles, and volume |
| `InvalidPathException` | OS rejects filename | Validate input portably |
| `MalformedInputException` | Bytes invalid for charset | Check encoding, BOM, and fixture |
| Vietnamese becomes `Ã©`/garbled chars | Decoded with wrong charset | Explicit UTF-8 |
| `ClassPathResource.getFile()` fails in JAR | Resource lives inside archive | Use `getInputStream()` |
| Test passes in IDE, fails in Gradle | Different working directory | `@TempDir` + classpath resources |
| Test passes alone, fails in suite | Shared root/static state/files | Per-method `@TempDir` |
| Cleanup fails on Windows | Unclosed `InputStream`/`Reader`/`Files.lines` | Try-with-resources |
| Output filename contains backslash on Linux | Concatenated path with Windows separator | `Path.resolve` |
| File has CRLF instead of LF | Used `System.lineSeparator` | Pin newline contract |
| `Files.size` differs from `text.length` | UTF-8 byte length differs from UTF-16 chars | Compare raw UTF-8 bytes |
| File exists with stale content | Shared filename or write never ran | Assert contents, `CREATE_NEW` |
| Symlink test skipped | OS lacks symlink privilege | Dedicated runner for security coverage |
| `normalize` still allows escaping via symlink | Lexical validation is insufficient | Trusted root / secure directory ops |
| Atomic move unsupported | Provider does not guarantee it | Test capability and explicit fallback policy |
| Tests leak files after failure | `Cleanup=NEVER`/`ON_SUCCESS` | Enable only for debugging; close resources |
| Spring singleton holds deleted root | Config bound once, context cached | Pass root per invocation or manage context |
| Large file causes test OOM | `readAllBytes`/`readString` not streaming | Stream/chunk and bound size |
| NFS/volume behaves differently from local `@TempDir` | Different lock/atomic/case semantics | Integration tests on deployment-like FS |
| Fixture unreadable after packaging | Wrong resource path/packaging | Inspect JAR contents + `InputStream` |
| Test accidentally deletes user files | Hardcoded path / recursive delete outside root | Confine all deletions inside `@TempDir` |
| User-supplied resource URL poses risk | `ResourceLoader` accepts arbitrary schemes | Allowlist schemes/paths; never trust client |

### Debugging workflow

1. Identify the temp root allocated by JUnit and the actual output path.
2. Verify the root exists and has read/write permissions.
3. Verify filename validation and parent creation.
4. Ensure paths are joined via `resolve`, never string concatenation.
5. Verify the charset on **both** reads and writes.
6. Inspect BOM/newlines if body bytes differ from expected.
7. Verify classpath resources use `getInputStream()` and the right resource name.
8. Confirm all readers/streams are closed.
9. Check for shared roots or parallel test execution.
10. Check Spring context caching if roots are injected into singletons.
11. Check filesystem semantics (symlinks, atomic move, case sensitivity, permissions).
12. Never use `Thread.sleep` to paper over I/O or cleanup bugs.
13. Never delete files outside the test sandbox to "retry."
14. If packaged JAR behavior differs from dev classpaths, add a packaged smoke test.

## 18. Advanced scenarios in real projects

### 18.1. Atomic file export

`CREATE_NEW` prevents overwrites but does not guarantee all-or-nothing writes. For all-or-nothing files, a standard pattern is:

1. Create a temp file **in the same target directory**.
2. Write bytes and close `OutputStream`.
3. When durability is required, use `FileChannel.force` per filesystem contract.
4. Move the temp file to target with `ATOMIC_MOVE` where supported by the provider.
5. Define overwrite/no-overwrite rules explicitly; avoid silent replacement.
6. Clean up the temp file on exceptions, strictly bounded to the trusted root.
7. Test fault injection before and after `move`, verifying the target never contains partial data.

Do not assume `ATOMIC_MOVE` is supported on every NFS or container overlay filesystem.

### 18.2. Zip Slip

When extracting a ZIP onto the filesystem, an entry may be named `../../secrets.txt`. Tests should use an isolated ZIP fixture, extract under `@TempDir`, normalize/verify targets, and enforce limits on total uncompressed size, file count, and symlinks. Never extract untrusted archives into the source tree or home directory just to test.

### 18.3. Permissions / ACLs

POSIX attributes are not supported on all filesystems. To test `chmod 600`, first check `FileStore.supportsFileAttributeView("posix")` and run only on compatible runners. Never treat a skipped test on Windows as proof that the permission policy works.

### 18.4. Large file sizes

Never call `readAllBytes` on multi-GB files in tests. Use streams with hashes/checksums, `Files.newBufferedReader`, or `FileChannel`, and bound size, duration, and disk usage. When testing malformed input parsing, use small representative fixtures.

### 18.5. Unicode filename normalization

Two visually identical filenames can consist of different Unicode codepoint sequences, especially on macOS filesystems. If an app lets users choose Unicode filenames, decide on NFC/NFD normalization, case folding, and collision policies. This lab does not claim an ASCII filename validator solves every i18n problem.

### 18.6. Server-generated storage names

For untrusted uploads, the safer approach is **server-generated storage IDs/filenames**, treating the original name purely as sanitized display metadata. Never let clients supply full local paths. Add tests proving tenant A cannot access tenant B's files even if IDs are guessed.

### 18.7. Resources inside packaged Spring Boot JARs

Unit/Gradle tests read `build/resources/main/...` without JAR nesting. For production readiness, build `bootJar` and run a smoke path using `Resource.getInputStream()` to prove the file is truly packaged and readable. Never rely on `ClassPathResource.getFile()` just because exploded-classpath tests pass.

### 18.8. Spring MVC multipart

`MockMultipartFile`/`MockMvc.multipart(...)` tests the HTTP binding boundary; file-saving services should be tested separately with `@TempDir`. Do not treat controller upload acceptance as proof of storage path validation. Test filename rules, size limits, MIME sniffing per policy, empty files, overwrites, and filesystem errors.

### 18.9. Cloud object storage

`@TempDir` does not emulate S3/GCS/blob stores: storage keys, ACLs, eventual consistency, versioning, and multipart semantics differ from NIO. Use a storage abstraction with unit mocks, plus integration tests against an emulator or authorized sandbox. Never claim cloud storage passes end-to-end based solely on local file tests.

### 18.10. Caching and timestamps

Filesystem modification time granularity varies across OSes and providers. Avoid asserting exact nanoseconds or using `Thread.sleep` to force distinct `mtime` values. When business logic relies on timestamps, inject a `Clock` for business metadata; test filesystem `mtime` only on compatible runners when part of the contract.

## 19. Comparing testing options

| Tool | Best for | Does not guarantee |
| --- | --- | --- |
| `@TempDir` | Real local file I/O with auto-cleanup | Cloud storage or NFS semantics |
| `Files.createTempDirectory` | Code that creates temp dirs directly | Tests must clean up manually |
| `Files.createTempFile` | Single temp file inside a root | Does not replace a fixture root |
| `Path`/`Files` | Testing bytes, paths, metadata | Does not sanitize untrusted user paths |
| `ClassPathResource` | Read-only fixtures from classpath/JAR | Not a writable test output root |
| `FileSystemResource` | Existing files on the filesystem | Does not auto-sanitize filenames |
| `ResourceLoader` | Resolving multiple resource schemes | Does not enforce security allowlists |
| Mockito storage mock | Fast business-rule unit tests | Does not test encoding, locks, or permissions |
| `@SpringBootTest` + `@TempDir` | Bean DI + local file I/O | Does not prove Docker volumes or S3 |
| Testcontainers filesystem | Mounted container volumes | Carries Docker/lifecycle setup |

Do not force every unit test to boot a Spring context. Path, charset, and byte handling should be verified with plain JUnit first; add `@SpringBootTest` only when bean wiring, configuration, or resource integration is part of the contract.

## 20. Practice exercises

**Exercise A — field vs. parameter:** Write two tests using `@TempDir Path` as a field and as a method parameter. Explain setup/cleanup scope without asserting exact path names.

**Exercise B — UTF-8:** Create a file containing `Tôi học Spring Boot 🌱`, read it as UTF-8, and compare bytes. Explain why `String.length` differs from `Files.size`.

**Exercise C — wrong encoding:** Write `Café` in UTF-8, read as ISO-8859-1, and assert they differ. Then fix the read charset.

**Exercise D — malformed bytes:** Write `C3 28` and assert `MalformedInputException` when reading as UTF-8.

**Exercise E — BOM:** Write `EF BB BF 41`, read as UTF-8, and verify `U+FEFF` is present. Design a policy to reject or strip it per contract.

**Exercise F — newlines:** Test exact LF bytes, then switch code to `System.lineSeparator()` across two OSes; define the expected contract.

**Exercise G — path normalization:** Use `root.resolve("a/../b.txt").normalize()`. Explain lexical vs. real paths and symlink limitations.

**Exercise H — traversal:** Pass `../escape.txt` and `..\\windows.txt` to the service; ensure exceptions are thrown before creating any file.

**Exercise I — Windows names:** Pass `CON.txt`, `COM1.txt`, and `LPT1.txt` and confirm the policy rejects them even on Linux.

**Exercise J — duplicates:** Call `export` twice with the same filename. The second call must throw, and the first file must remain untruncated.

**Exercise K — symlinks:** When supported by the OS, create a symlink and attempt exporting to the same name. When unsupported, skip with a clear reason without claiming full security coverage.

**Exercise L — classpath:** Copy `reports/header.txt` via `getInputStream()` into `@TempDir`. Never use `getFile()`.

**Exercise M — packaged JAR:** Run a smoke test from the fat JAR to confirm the resource remains readable, not only on Gradle's expanded classpath.

**Exercise N — `ResourceLoader`:** Test `classpath:` and `file:` URIs from an isolated root without allowing untrusted input to select schemes.

**Exercise O — file streams:** Use `Files.lines` in try-with-resources and observe what happens on Windows runners when you forget to close it.

**Exercise P — static shared root:** Create a static `@TempDir` and two tests sharing a filename; observe the conflict. Switch back to instance/method scope.

**Exercise Q — Spring singleton:** Have the service accept `Path` per method; verify each `@SpringBootTest` method uses a fresh root without mutating singleton state.

**Exercise R — atomic export:** Design temp-write + move, test behavior when writes fail mid-stream; do not assume every provider supports `ATOMIC_MOVE`.

**Exercise S — permissions:** On a compatible POSIX runner, test read-only directories, file attributes, and cleanup after denial. Do not force Windows to pass it.

**Exercise T — Zip Slip:** Test an archive containing a `../` entry inside an isolated `@TempDir`, ensuring the extractor never writes outside the trusted root.

**Exercise U — Unicode filenames:** Design a validator supporting NFC/NFD and filesystem collisions; add OS matrix tests.

**Exercise V — CI:** Run the full suite on Windows and Linux, compare tests skipped for symlinks against passing tests; never treat skipped tests as security guarantees.

## 21. Pre-merge checklist for file tests

- [ ] Test roots come from `@TempDir`, never hardcoded global paths?
- [ ] Never writes back into `src/main/resources` or `src/test/resources`?
- [ ] Uses JUnit Jupiter `@TempDir` on valid `Path`/`File` targets?
- [ ] Instance/method scope avoids shared state under parallel runs?
- [ ] Parent directories are created when needed?
- [ ] Paths are joined via `resolve` instead of manual separators?
- [ ] `normalize` and containment checks are applied when filenames come from input?
- [ ] Lexical path checks are not mistaken for a complete security sandbox?
- [ ] Both positive and negative filename/path tests exist (traversal, absolute, Windows separators, reserved names)?
- [ ] Overwrite policy (`CREATE_NEW`/replace/truncate) is explicit and tested?
- [ ] UTF-8 is specified at every text read/write boundary?
- [ ] Vietnamese/emoji fixtures are included to catch encoding bugs?
- [ ] Raw bytes are asserted when contracts cover newlines, BOM, or binary data?
- [ ] Does not assume `String.length` equals file size?
- [ ] Malformed bytes and wrong-charset cases are tested?
- [ ] Classpath resources are read via `getInputStream()`, avoiding `getFile()` for packaged JARs?
- [ ] `ResourceLoader` locations do not let users pick arbitrary schemes or paths?
- [ ] Every `InputStream`/`Reader`/`Files.lines`/`Files.walk` is closed?
- [ ] Symlink/permissions/atomic-move tests have appropriate OS/provider strategies?
- [ ] Spring context caching does not retain roots already deleted by JUnit?
- [ ] Never mutates JVM-wide `System.setProperty` across test methods to swap roots?
- [ ] Test outputs never touch user directories or the source tree?
- [ ] Disk cleanup never recursively deletes outside the allocated root?
- [ ] Production cloud/NFS setups have integration tests against the actual backend?
- [ ] Packaged JARs have smoke tests verifying resource packaging?
- [ ] Test reports confirm tests actually ran rather than relying solely on cached Gradle tasks?

## 22. References

- [JUnit 5.10 — TempDirectory Extension](https://docs.junit.org/5.10.0/user-guide/index.html): scope, fields, method parameter injection, cleanup modes.
- [JUnit Jupiter 5.10 — TempDir API](https://junit.org/junit5/docs/5.10.0/api/org.junit.jupiter.api/org/junit/jupiter/api/io/TempDir.html): supported targets, lifecycle, and cleanup.
- [Java 17 — `java.nio.file.Path`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html): `resolve`/`normalize`/`startsWith`/`toRealPath`.
- [Java 17 — `java.nio.file.Files`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): `readString`/`writeString`, `createTempFile`, copy/move, streaming.
- [Java 17 — `StandardCharsets`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html): UTF-8, ISO-8859-1.
- [Java 17 — `StandardOpenOption`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardOpenOption.html): `CREATE_NEW`, `WRITE`, and overwrite semantics.
- [Spring Framework — Resources](https://docs.spring.io/spring-framework/reference/core/resources.html): `ResourceLoader`, `ClassPathResource`, `FileSystemResource`, and JARs.
- [Spring Boot 3.5 — Testing](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@SpringBootTest` and test context lifecycle.
- [JUnit Jupiter 5.10 — Assertions/Assumptions](https://docs.junit.org/5.10.0/user-guide/index.html): `assertThrows`, `Assumptions`, and OS-specific tests.

**Remember:** In Spring Boot testing, `@TempDir` keeps file I/O inside a test-owned root; `Path`/`Files` enable portable code; explicit `UTF_8` protects Vietnamese diacritics and raw bytes; `Resource.getInputStream()` handles classpath/JAR fixtures; and negative assertions enforce path and overwrite security policies. Pick the right temp root scope, close all streams, and distinguish local filesystem test results from production storage guarantees.