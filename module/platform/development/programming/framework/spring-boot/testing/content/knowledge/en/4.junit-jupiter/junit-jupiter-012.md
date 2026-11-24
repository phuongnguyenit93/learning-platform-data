# @TempDir for Temporary Resources and Cleaning Up Data After Tests

## 1. Why do tests need a temporary directory?

A Java/Spring Boot application frequently reads or writes files: exporting CSV reports, generating PDFs, handling file uploads, extracting ZIP archives, saving intermediate images, writing logs, generating config files, or testing import/export mechanisms. If a test writes directly into the project directory, a developer's disk, or a production path, it can:

- Leave files behind after each run and make subsequent runs depend on stale state.
- Overwrite real data or files belonging to concurrently running tests.
- Fail on CI machines due to different absolute paths or missing permissions.
- Require manual cleanup code that is easily skipped when an assertion throws.

JUnit Jupiter provides **`@TempDir`** (package `org.junit.jupiter.api.io`). This built-in extension creates a **temporary directory** for the test, supplies its path, and **automatically cleans up its contents when out of scope** according to the cleanup configuration.

Right mindset: tests only write data within the scope provided by `@TempDir`; assert **file contents and behavior while the test is running**; let JUnit handle directory lifecycle when the test finishes.

### When is @TempDir useful?

| Scenario | Using a temporary directory |
| --- | --- |
| Exporting a report file | Write to `tempDir.resolve("report.csv")` then assert contents |
| Importing from a file | Create sample data file in the temp directory, then invoke the reader service |
| Extracting or generating multiple files | Create subdirectories in `tempDir`, assert structure and contents |
| Testing invalid input handling | Verify no file is created when input is invalid |
| Testing real filesystem interaction | Use `java.nio.file.Files` on a managed directory, avoiding mocking all file operations |

`@TempDir` **does not create report files automatically** and does not perform assertions for you: it only provisions and manages the **temporary root directory**. The test or code under test must create files/subdirectories inside it.

## 2. How does @TempDir work?

When `@TempDir` is detected on a supported location, JUnit Jupiter uses the `TempDirectory` extension to create a temporary directory and inject an object pointing to it. Two types are supported:

- **`java.nio.file.Path`** — usually the preferred choice with Java 17+ and `Files` APIs.
- **`java.io.File`** — useful when legacy code needs `File`; convertible via `file.toPath()`.

Example placing the annotation directly on a test parameter:

~~~java
@Test
void writesText(@TempDir Path tempDir) throws IOException {
    Path file = tempDir.resolve("note.txt");
    Files.writeString(file, "Hello test", StandardCharsets.UTF_8);

    assertTrue(Files.exists(file));
    assertEquals("Hello test", Files.readString(file, StandardCharsets.UTF_8));
}
~~~

This is an **illustrative method inside a test class**, requiring imports for `org.junit.jupiter.api.Test`, `org.junit.jupiter.api.io.TempDir`, `java.nio.file.Path`, `Files`, `IOException`, `StandardCharsets`, and JUnit assertions. JUnit supplies `tempDir` when invoking the test.

The actual directory may have a random name and live in the OS temp area or configured filesystem. **Do not hard-code paths** like `/tmp/report-test` or `C:\temp\my-test`, and do not assert the physical directory name. Work solely through the `Path` provided by JUnit.

### Normal lifecycle of a test

~~~text
JUnit creates temporary directory
        ↓
Injects @TempDir Path/File
        ↓
@BeforeEach and test setup steps
        ↓
@Test writes/reads files and runs assertions
        ↓
@AfterEach and test teardown steps
        ↓
@TempDir exits scope → JUnit cleans recursively (by default)
~~~

This is an overview diagram; internal callback order also involves other extensions. The key point is **JUnit cleans up at the end of the scope**, so the test can read files right after creating them to verify contents. Do not write `assertFalse(Files.exists(tempDir))` inside the `@Test` body to test cleanup: at that moment the directory is still serving the test.

## 3. Three ways to inject the directory: parameter, instance field, static field

### Approach A — Test parameter: makes per-case need explicit

~~~java
@Test
void createsInputFile(@TempDir Path tempDir) throws IOException {
    Path input = tempDir.resolve("input.txt");
    Files.writeString(input, "sample", StandardCharsets.UTF_8);
    assertEquals("sample", Files.readString(input, StandardCharsets.UTF_8));
}
~~~

Strength: looking at the method signature immediately shows the test works with files. Great if only a few tests in the class need a temp directory. With multiple `@TempDir` parameters, separate declarations may receive distinct directories; do not assume they point to the same location.

### Approach B — Instance field: share the same directory across setup, test, and teardown

~~~java
@TempDir
Path tempDir;

@BeforeEach
void prepare() throws IOException {
    Files.writeString(tempDir.resolve("config.txt"), "mode=test");
}

@Test
void readsPreparedFile() throws IOException {
    assertEquals("mode=test", Files.readString(tempDir.resolve("config.txt")));
}
~~~

This is a **snippet inside a test class**, requiring JUnit and Java NIO imports. Under the default `PER_METHOD` test instance lifecycle, each regular test receives its own instance, so this instance field serves that test invocation's fixture. This is also handy if `@AfterEach` needs to inspect or close file resources tied to the same directory.

A field annotated with `@TempDir` must be injectable by JUnit (not `final`, not pre-assigned an arbitrary path). Do not instantiate a `Path` yourself expecting JUnit to clean up that directory.

### Approach C — Static field: directory shared at class level

~~~java
@TempDir
static Path sharedTempDir;
~~~

With a `static` field, the directory belongs to the shared scope of the test class. You can prepare shared fixtures in `@BeforeAll` and let JUnit clean up at the end of class scope instead of after each method.

This should only be used for data **not mutated by tests in ways that affect one another**. If two tests both create `sharedTempDir.resolve("result.txt")`, they can overwrite each other or fail during parallel execution. For tests that write files, prefer parameters or instance fields for isolation.

**Be careful with `@TestInstance(PER_CLASS)`:** tests may share a single instance and its state. Do not assume that merely because a field is non-`static`, every test always gets completely isolated data once the test instance lifecycle has been changed. When strict per-invocation scope is needed, use a `@TempDir` parameter directly on each test.

## 4. Complete example: testing a file-export service with Java 17 + JUnit Jupiter

Let's build a simple service: given valid data, it creates `report.txt` under the provided directory; given blank content, it rejects without generating a file. We want to test the export logic **on a real filesystem**, without writing outside temporary space.

**File `src/main/java/com/example/testing/ReportWriter.java`:**

~~~java
package com.example.testing;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Objects;

public final class ReportWriter {
    public Path write(Path outputDirectory, String content) throws IOException {
        Objects.requireNonNull(outputDirectory, "outputDirectory");

        if (content == null || content.isBlank()) {
            throw new IllegalArgumentException("Report content must not be blank");
        }

        Path output = outputDirectory.resolve("report.txt");
        Files.writeString(output, content, StandardCharsets.UTF_8);
        return output;
    }
}
~~~

`ReportWriter` accepts a `Path` externally instead of picking a fixed system folder. This makes the code easily testable and also helps in real applications where storage location comes from configuration.

**File `src/test/java/com/example/testing/ReportWriterTest.java`:**

~~~java
package com.example.testing;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ReportWriterTest {
    @TempDir
    Path tempDir;

    private ReportWriter writer;

    @BeforeEach
    void setUp() {
        writer = new ReportWriter();
    }

    @Test
    void write_whenContentIsValid_createsFileInsideTempDir() throws IOException {
        // Arrange: tempDir is the directory JUnit created;
        // writer is prepared by @BeforeEach.
        String content = "Test report\n";

        // Act
        Path generated = writer.write(tempDir, content);

        // Assert
        assertEquals(tempDir.resolve("report.txt"), generated);
        assertTrue(Files.exists(generated));
        assertEquals(content, Files.readString(generated, StandardCharsets.UTF_8));
    }

    @Test
    void write_whenContentIsBlank_throwsWithoutCreatingFile() {
        // Act + Assert: service rejects blank input.
        assertThrows(
                IllegalArgumentException.class,
                () -> writer.write(tempDir, "   ")
        );

        // Must not create a file after rejecting.
        assertFalse(Files.exists(tempDir.resolve("report.txt")));
    }

    @Test
    void write_whenNestedDirectoryExists_createsFileThere() throws IOException {
        Path nested = Files.createDirectories(
                tempDir.resolve("exports").resolve("daily")
        );

        Path generated = writer.write(nested, "Daily\n");

        assertEquals(nested.resolve("report.txt"), generated);
        assertEquals("Daily\n", Files.readString(generated, StandardCharsets.UTF_8));
    }
}
~~~

### Explanation

- `@TempDir Path tempDir`: each invocation gets its own directory scope under default JUnit settings; tests do not guess directory names.
- `@BeforeEach`: creates `ReportWriter` for each test; `@SpringBootTest` is unnecessary because the service has no Spring container dependencies.
- Valid case verifies **path**, **file existence**, and **UTF-8 content**.
- Error case verifies `IllegalArgumentException` and **no output file created**.
- Nested directory case creates `exports/daily` inside the temp directory; default cleanup recursively deletes subdirectories and files when out of scope.

**Do not write `@AfterEach` solely to call `Files.delete(...)` or `deleteOnExit()` for files created inside `tempDir`.** The JUnit extension handles that according to the cleanup mode.

### Configuration and running in a Spring Boot project

Example for Spring Boot 3.x/Java 17+ using Gradle Groovy DSL. In `build.gradle`, the relevant section can look like:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Assumes the project already has the Spring Boot plugin, repositories, and suitable Java/Gradle configuration. This is an **added configuration snippet**, not a standalone build file. `spring-boot-starter-test` supplies the required test libraries in standard Spring Boot 3.x setups.

From the directory with the Gradle Wrapper:

~~~bash
./gradlew test --tests "com.example.testing.ReportWriterTest"
~~~

On Windows:

~~~powershell
.\gradlew.bat test --tests "com.example.testing.ReportWriterTest"
~~~

When all assertions hold, all three tests are marked successful by JUnit/Gradle. The example **does not call `System.out.println`**, so there is no fixed program stdout string to copy. Report/log formatting depends on Gradle and JUnit settings.

**Runnability:** the two Java classes above use Java 17 and JUnit Jupiter APIs, placed in matching packages and source directories. They can run inside a Spring Boot project configured as described; `ReportWriterTest.java` cannot be compiled standalone with `javac` without JUnit on the classpath.

## 5. Automatic cleanup on completion: understanding cleanup properly

By default, `@TempDir` uses **`CleanupMode.ALWAYS`**. When the scope ends (usually one test invocation, or one class if using a class-level directory), JUnit **attempts recursive deletion**:

1. Files created directly inside the temp directory.
2. Subdirectories and files inside them.
3. Finally, the temp directory itself.

This mechanism typically runs even when a test assertion fails. It prevents subsequent runs from accidentally reading stale files and limits clutter in temp storage. However, it cannot guarantee every case: killed processes, JVM crashes, filesystem errors, locked files, or insufficient permissions can prevent cleanup. Certain file-deletion errors can also cause JUnit to report the test/class as failed.

### Cleanup modes

| `TempDir.CleanupMode` value | Behavior | When to consider |
| --- | --- | --- |
| `ALWAYS` (default) | Attempts deletion at scope end, even if the test fails | Most standard tests |
| `ON_SUCCESS` | Cleans up only if the test finishes successfully | Temporarily keeping data to investigate failing cases |
| `NEVER` | Never cleans up automatically at scope end | Only intentionally for debugging; must manage retained data manually |

Example keeping the temp directory only when a test fails:

~~~java
@TempDir(cleanup = TempDir.CleanupMode.ON_SUCCESS)
Path tempDir;
~~~

This is a **field snippet inside a test class**, requiring `org.junit.jupiter.api.io.TempDir`. The syntax `TempDir.CleanupMode.ON_SUCCESS` explicitly references the enum on the annotation.

To always keep data (rarely used in CI):

~~~java
@TempDir(cleanup = TempDir.CleanupMode.NEVER)
Path tempDir;
~~~

Do not enable `NEVER` indiscriminately across the whole test suite: temp files can hold sensitive data, consume disk space, and accumulate across runs. Keep the default `ALWAYS`, and adjust temporarily only when diagnosing a specific case. JUnit also provides `junit.jupiter.tempdir.cleanup.mode.default` to override the default for a global policy, though local settings must still match test intent.

**Important:** Do not write a second test asserting the old directory was deleted to "prove JUnit cleanup works". That tests the framework's lifecycle and typically requires a separate test harness outside test scope, not an application business condition.

## 6. Closing streams or other resources properly when opened by tests

`@TempDir` manages **the directory and files inside that directory**. It does not substitute for closing streams, sockets, processes, database connections, or resources opened by application code.

Example using `try-with-resources` to ensure streams close before JUnit cleans the directory:

~~~java
@Test
void readsFileUsingStream(@TempDir Path tempDir) throws IOException {
    Path file = tempDir.resolve("data.bin");
    Files.write(file, new byte[] { 1, 2, 3 });

    try (var input = Files.newInputStream(file)) {
        assertEquals(1, input.read());
        assertEquals(2, input.read());
        assertEquals(3, input.read());
        assertEquals(-1, input.read());
    }
}
~~~

This is an **illustrative method**, requiring imports for `IOException`, `Path`, `Files`, `Test`, `TempDir`, and `assertEquals`. On Windows, files still held open by a stream/process are much harder to delete, making stream lifecycle management a practical issue, not just code style.

`@AfterEach` is only needed when there are **other per-test resources** to clean up outside `@TempDir`'s automatic scope. For example, if a test launches a child process or creates data in an external service, you must close or roll back through its proper management mechanism. Do not use `@AfterEach` to manually delete every file inside the temp directory again when JUnit is already responsible.

For files located **outside** the temporary directory (such as a hardcoded config path), JUnit will not clean them up simply because `@TempDir` exists in the same test. Direct file-writing code toward a test-specified directory, or separate an explicit cleanup routine for out-of-scope resources.

## 7. Testing multiple directories, nested files, and isolation

A safe way to create nested test data:

~~~java
@Test
void exportsMultipleFiles(@TempDir Path tempDir) throws IOException {
    Path archive = Files.createDirectories(tempDir.resolve("archive"));
    Path first = Files.writeString(archive.resolve("a.txt"), "A");
    Path second = Files.writeString(archive.resolve("b.txt"), "B");

    assertTrue(Files.isDirectory(archive));
    assertEquals("A", Files.readString(first));
    assertEquals("B", Files.readString(second));
}
~~~

This is an **illustrative snippet** inside a test class; `Files.writeString` returns the `Path` of the written file. All paths are descendants of `tempDir`, so default recursive cleanup covers them.

Do not create files under `src/test/resources` or the working directory just to supply input if that data is generated dynamically on each test run. **Immutable** fixtures can live in `src/test/resources`; data written/modified during test execution belongs in `@TempDir`. Never commit test-generated files to Git or rely on leftover files in a dev environment.

If filenames or subpaths come from untrusted input, never blindly call `tempDir.resolve(userInput)`: absolute paths or `..` segments can escape the temporary directory. Application code must validate filenames or normalize and verify that the target path stays inside the allowed directory, while also accounting for symbolic links in security scenarios.

## 8. Distinguishing @TempDir from other techniques

| Approach | Good fit when | Limitations to remember |
| --- | --- | --- |
| `@TempDir` | Testing real file/directory operations, wanting isolation and automatic cleanup | Does not manage databases, networks, or files outside the directory |
| `Files.createTempDirectory(...)` | Code outside JUnit or needing manual lifecycle control | Author must delete recursively; no automatic JUnit lifecycle |
| `Files.createTempFile(...)` | Needing a single temp file | Only creates the file; deletion responsibility depends on management scope |
| `@BeforeEach` / `@AfterEach` | Preparing or cleaning up per-test resources | Redundant if solely deleting files inside `@TempDir` |
| `@BeforeAll` / `@AfterAll` | Class-level shared resources | Easy to leak mutable state; does not replace integration cleanup |
| Mocking filesystem/file service | Testing pure logic without real I/O | Mocks can miss bugs in paths, encoding, permissions, and real file read/write |

They can be combined: `@BeforeEach` creates data fixtures **inside** `@TempDir`, the test uses them, and JUnit cleans the directory at scope end. Do not confuse condition preparation with data lifecycle management.

### Using alongside Spring Boot Test

Tests using `@SpringBootTest`, `@WebMvcTest`, or test slices can still use `@TempDir` because it is a **JUnit Jupiter** mechanism. For example, a test checking a report-exporting service with real Spring beans can pass `tempDir` into an `@Autowired` service method. For plain Java logic like `ReportWriter`, a JUnit unit test without booting a Spring context is faster and more direct.

If a service reads a path from `application.yml` or `@ConfigurationProperties`, configure the output path in the **test context** so it points to an appropriate temp location. If the path is bound when the Spring context starts, do not simply mutate a variable afterward assuming the bean picks up the new path. Inject `Path` via method/constructor or set the test property before beans are created; ensure no real production file path is touched inadvertently.

If a test uses Spring transactions/rollback to clean database data, rollback **does not delete files on disk**. Conversely, `@TempDir` does not roll back databases. Each resource type has its own management mechanism.

## 9. Common mistakes with @TempDir

1. **Pre-assigning a path to a `@TempDir` field:** JUnit needs to allocate the field itself. **Fix:** leave the field uninitialized, e.g., `@TempDir Path tempDir;`.
2. **Hardcoded absolute paths in tests:** writing directly to `/tmp/demo.txt` or project directories. **Fix:** write under `tempDir.resolve("demo.txt")`.
3. **Putting the annotation on an arbitrary local variable inside a method:** `@TempDir` works on supported fields or parameters, not arbitrary local variables. **Fix:** place it on a `@Test` parameter or test class field.
4. **Confusing per-test and per-class scope:** using `static @TempDir` and letting multiple tests write to the same `output.txt`. **Fix:** use an instance field by default or separate parameters per test.
5. **Expecting the directory to already be deleted while the test is still running:** JUnit only cleans up at scope end. **Fix:** assert files while the test runs, and let the framework clean up afterward.
6. **Opening file streams without closing them:** some OSes cannot delete locked files. **Fix:** close resources with `try-with-resources` or owner-scoped cleanup.
7. **Unsafe manual cleanup:** running recursive deletes on the wrong path or deleting JUnit's managed directory early so other hooks expecting it fail. **Fix:** rely on `@TempDir`'s default cleanup and only manually clean resources outside its scope.
8. **Enabling `CleanupMode.NEVER` and forgetting to delete debug data:** test clutter and sensitive files can linger. **Fix:** enable intentionally, manage retained artifact lifecycles, and revert to `ALWAYS`.
9. **Assuming shared directories are always empty across tests:** `static` fields or changed instance lifecycles let tests affect one another. **Fix:** design tests not to share mutable files.
10. **Confusing filesystem cleanup with database rollback:** two independent mechanisms. **Fix:** explicitly identify what resources a test creates and who cleans up each type.
11. **Naming files from unvalidated input:** path traversal or files outside temporary storage get affected. **Fix:** validate inputs, normalize paths, and enforce allowed boundaries.

## 10. Practice checklist

Before finishing a test involving file I/O:

- [ ] Use `@TempDir` on `Path` or `File` in a JUnit-supported position.
- [ ] Data generated by the test stays **inside** the temporary directory.
- [ ] If each case needs its own directory, use parameters or per-test fixtures, avoiding shared state.
- [ ] Code under test accepts configurable paths; production paths are never hardcoded.
- [ ] Assertions verify exact file contents, filenames, structure, or error states per business requirements.
- [ ] File streams, readers, writers, or processes are closed before leaving scope.
- [ ] Use default `ALWAYS` cleanup unless debugging requires otherwise.
- [ ] Do not expect the directory to be deleted while the test is still executing.
- [ ] Files outside `tempDir`, databases, or network resources have their own cleanup strategies.
- [ ] Tests run independently without relying on files from previous runs.

**Remember:** `@TempDir` gives tests a **safe, isolated filesystem space with a deterministic lifecycle**. Create files via `Files` inside that space, assert results while the test executes, and let JUnit recursively clean up according to the chosen scope and cleanup mode.

### References

- [JUnit 5 User Guide — Built-in Extensions / @TempDir](https://docs.junit.org/5.12.0/user-guide/)
- [JUnit 5 API — TempDir](https://docs.junit.org/5.13.3/api/org.junit.jupiter.api/org/junit/jupiter/api/io/TempDir.html)
