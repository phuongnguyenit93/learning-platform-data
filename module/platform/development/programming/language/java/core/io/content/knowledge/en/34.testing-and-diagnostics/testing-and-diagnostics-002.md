# Creating Separate Temporary Directories for Each Test Scenario in Java 17+

## 1. Why Isolate I/O Data for Each Scenario?

When testing file processing, an application often needs to create input files, write output files, build directory trees, or simulate error paths. If multiple scenarios share a fixed location such as `./test-data/output.txt`, test runs can interfere with one another:

- A previous test leaves files behind, causing the next run to pass or fail falsely.
- Two tests running in parallel write to the same file name and cause a **race condition**.
- A test depends on data present on a developer's machine but missing on CI.
- When testing error paths, partially written data remains and affects the next scenario.
- Cleanup commands using hardcoded paths may accidentally delete real data.

A good default solution is **giving each scenario its own temporary directory**, created when the scenario starts and cleaned up when it finishes:

~~~text
Operating system temporary directory
├── test-import-48297.../
│   ├── input/
│   │   └── data.csv
│   └── output/
│       └── result.json
└── test-export-12058.../
    ├── input/
    │   └── data.csv
    └── output/
        └── result.json
~~~

The names with random parts above are only illustrative. Both scenarios can use the relative path `input/data.csv` without colliding because **their root directories are completely different**.

After this lesson, you will know how to create temporary directories using `Files.createTempDirectory`, define ownership boundaries, handle cleanup when tests fail, verify portability on CI, and integrate with testing frameworks like JUnit Jupiter `@TempDir`.

## 2. Core API: `Files.createTempDirectory`

Java NIO.2 defines two common forms:

~~~java
Path root = Files.createTempDirectory("case-import-");

Path rootUnderParent = Files.createTempDirectory(
        parentDirectory, "case-import-");
~~~

This is an **illustrative snippet**, requiring imports for `java.nio.file.Files` and `java.nio.file.Path`; `parentDirectory` must be an appropriate parent directory that exists and allows creating entries.

- `Files.createTempDirectory(String prefix, FileAttribute<?>... attrs)` creates a new directory in the default temporary area determined by the environment/provider.
- `Files.createTempDirectory(Path dir, String prefix, FileAttribute<?>... attrs)` creates a new directory **directly under `dir`**, suitable when you want all test artifacts located inside a temporary workspace dedicated to the run.
- The method returns the `Path` of the **newly created directory**; `Path` is only a path representation, **not an `AutoCloseable` resource**, and is not automatically deleted when leaving scope.
- Each call is designed to generate a name that does not yet exist at the target location. You do not need to construct names using timestamps or risk collisions with shared sequential counters.
- `prefix` makes logs/traces easier to read; do not put sensitive data such as tokens, passwords, or customer names in the prefix.
- If write permission is missing, the path is invalid, or the provider does not support the attribute configuration, the call may fail; the test should report the error rather than silently switching to deleting or replacing another directory.

Example of creating a file inside the isolated area:

~~~java
Path root = Files.createTempDirectory("scenario-");
Path inputDir = Files.createDirectories(root.resolve("input"));
Path input = inputDir.resolve("data.txt");

Files.writeString(input, "sample", StandardCharsets.UTF_8,
        StandardOpenOption.CREATE_NEW);
~~~

This is a standalone snippet requiring imports for `Files`, `Path`, `StandardCharsets`, `StandardOpenOption`, and cleanup upon completion. `CREATE_NEW` refuses to overwrite an existing file path; combined with a fresh root, it serves as a good check that the test does not depend on leftover files.

**Do not confuse `Files.createTempFile(...)` with `createTempDirectory(...)`.** The former creates a new file, whereas the latter creates a new directory. For a scenario needing multiple inputs and outputs, creating one root directory and using `resolve` to organize files inside it is usually more convenient.

## 3. Ownership Scope: Who Creates, Who Cleans Up?

A simple rule:

> The component that creates the temporary root owns that root and is responsible for cleaning up the contents inside it—and **only** the contents inside that root.

Example of a test method owning its area:

~~~text
testScenario():
  root = createTempDirectory()
  try:
      prepare input inside root
      run code under test on paths inside root
      assert output
  finally:
      delete root tree
~~~

If a helper receives `Path root` from a caller, the helper **should not delete the entire root** unless the contract explicitly grants it ownership. The helper should only create or modify entries permitted by the caller.

Appropriate scope depends on the problem:

| Scope | Usage | When Appropriate |
| --- | --- | --- |
| One scenario/test method | Each call creates a new root | Default choice to keep tests independent |
| A test group sharing immutable fixtures | Can create one root for the group, split into subdirectories | When setup is expensive and data is **truly never modified** |
| One test-suite run | Create one parent, then create child roots per scenario | Easy to collect artifacts and clean up the whole run |
| One concurrent task | Separate root per request/task | When multiple tasks may write the same file name |
| Production job | Separate staging root per job | When incomplete data must not be published; usually has its own cleanup and monitoring policy |

**Isolating the root does not automatically isolate everything.** Two tests with different roots can still contend on a fixed TCP port, database, environment variable, static state, files outside the root, or native resources. When such issues arise, isolate or coordinate each corresponding resource.

## 4. Do Not Use Fixed Paths or Timestamp-Derived Names

A collision-prone pattern:

~~~java
Path root = Path.of("build/tmp/my-test");
Files.createDirectories(root);
~~~

This is an **anti-pattern** if multiple scenarios share `root` without coordination. `createDirectories` allows an existing directory, so one test may accidentally reuse files or data from an earlier test.

A better pattern:

~~~java
Path base = Path.of("build", "test-scratch");
Files.createDirectories(base);

Path scenarioRoot = Files.createTempDirectory(base, "import-");
~~~

This snippet is illustrative only. The parent directory `build/test-scratch` can be a shared workspace, while `scenarioRoot` is always a newly created subdirectory. In CI or parallel runs, ensure `base` sits on a partition with sufficient space and write permissions. If your project uses a different build system, you do not have to use the name `build`.

**Do not rely on `System.currentTimeMillis()` timestamps for absolute uniqueness.** Two tasks can start within the same millisecond. `UUID` or a safe naming helper can be used in special cases, but `Files.createTempDirectory` directly solves the need to create a new directory without rolling your own algorithm.

## 5. Complete Java 17+ Example: Two Scenarios, Identical File Names

The standalone program below runs two scenarios sharing the same relative file names `input/data.txt` and `output/result.txt`. Each scenario creates its own fresh root, prepares distinct content, copies the data, and verifies it. `finally` ensures cleanup runs even if an assertion or I/O operation fails.

Save the file **`ScenarioTempDirectoryDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.nio.file.attribute.BasicFileAttributes;

public class ScenarioTempDirectoryDemo {

    public static void main(String[] args) throws IOException {
        runScenario("alpha", "NORTH");
        runScenario("beta", "SOUTH");
        System.out.println("All scenarios passed");
    }

    private static void runScenario(String name, String content)
            throws IOException {
        Path root = Files.createTempDirectory("io-" + name + "-");

        try {
            Path inputDirectory =
                    Files.createDirectory(root.resolve("input"));
            Path outputDirectory =
                    Files.createDirectory(root.resolve("output"));

            Path input = inputDirectory.resolve("data.txt");
            Path output = outputDirectory.resolve("result.txt");

            Files.writeString(
                    input, content, StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE_NEW);

            // Simulate an I/O operation that the test wants to verify.
            Files.copy(input, output, StandardCopyOption.COPY_ATTRIBUTES);

            String actual =
                    Files.readString(output, StandardCharsets.UTF_8);
            if (!content.equals(actual)) {
                throw new AssertionError("Unexpected file content");
            }

            System.out.println(name + " output: " + actual);
        } finally {
            deleteTree(root);
        }
    }

    private static void deleteTree(Path root) throws IOException {
        Files.walkFileTree(root, new SimpleFileVisitor<Path>() {

            @Override
            public FileVisitResult visitFile(
                    Path file, BasicFileAttributes attributes)
                    throws IOException {
                Files.delete(file);
                return FileVisitResult.CONTINUE;
            }

            @Override
            public FileVisitResult postVisitDirectory(
                    Path directory, IOException error)
                    throws IOException {
                if (error != null) {
                    throw error;
                }
                Files.delete(directory);
                return FileVisitResult.CONTINUE;
            }
        });
    }
}
~~~

Compile and run with **JDK 17 or higher**:

~~~bash
javac -encoding UTF-8 ScenarioTempDirectoryDemo.java
java ScenarioTempDirectoryDemo
~~~

**Expected stdout when the environment allows creating, copying, and deleting temporary files:**

~~~text
alpha output: NORTH
beta output: SOUTH
All scenarios passed
~~~

### Code Explanation

1. `runScenario` calls `Files.createTempDirectory(...)` for **each** scenario, so the root of `alpha` and the root of `beta` are different. The prefix only aids tracing; the rest of the name is generated by the provider.
2. Inside each root, the program creates two subdirectories with `Files.createDirectory`, then uses the same names `data.txt` and `result.txt`. Sharing a root could cause the two scenarios to collide; using two roots avoids that dependency.
3. `Files.writeString(..., CREATE_NEW)` creates a new input file without overwriting an existing one. `Files.copy` copies to the non-existent output path.
4. `Files.readString` reads the tiny output file. Reading the entire file is reasonable here; for large files in performance lessons, choose chunked reading.
5. Checking `content.equals(actual)` verifies each scenario receives its exact data. `AssertionError` is used to signal a test failure without external libraries.
6. `finally` runs whether the operations succeed or fail. `deleteTree` removes files first and directories afterward, which is required because deleting a non-empty directory fails.
7. `Files.walkFileTree` **does not follow symbolic links by default**; the code does not pass `FileVisitOption.FOLLOW_LINKS`. Thus a symlink encountered in the tree is deleted as a link entry rather than traversing into the symlink's target tree.
8. Stdout does not print the random root names, so when I/O succeeds, the output is always identical to the above. If the environment denies write or delete permissions, the program throws an error instead of pretending it succeeded.

**Note:** `COPY_ATTRIBUTES` attempts to copy certain basic attributes, though support depends on the filesystem. When the goal is only testing byte content, simpler `Files.copy(input, output)` can be used. If `COPY_ATTRIBUTES` is unsupported, the example may fail instead of printing results; that is why unnecessary options should be omitted in portable tests.

## 6. Cleaning Up Directory Trees Properly: Why Not Just Call `Files.delete(root)`?

`Files.delete(path)` deletes a single file or **an empty directory**. If the temporary root still contains input files, output files, or subdirectories, deleting the root directly can fail with `DirectoryNotEmptyException`.

Incorrect example when `root` is non-empty:

~~~java
Files.delete(root); // Fails if root still contains files or subdirectories.
~~~

The standard approach in Core Java is traversing the entire tree and deleting **children before parents**, such as `Files.walkFileTree` with `SimpleFileVisitor` as shown in the complete example in section 5.

Another pattern can use `Files.walk(root)`, sort in reverse order, and delete:

~~~java
try (var paths = Files.walk(root)) {
    for (Path p : paths.sorted(
            java.util.Comparator.reverseOrder()).toList()) {
        Files.deleteIfExists(p);
    }
}
~~~

This is an **illustrative snippet**, requiring `root` to be an authorized deletion target and importing `Files` and `Path`. `Files.walk` creates a stream that must be closed via `try-with-resources`. `toList()` collects all paths into RAM; for very large trees, `walkFileTree` is usually preferable because it processes entries incrementally.

**Never run recursive deletion on an uncontrolled path.** Especially avoid "cleaning up" by directly deleting the OS's shared temp directory or a shared workspace. The cleanup helper must only accept the exact root created and owned by the scenario.

### Handling Errors During Cleanup

If the test body throws an exception and cleanup also throws an exception from `finally`, the cleanup exception can **mask the original test failure**. That is standard `finally` behavior when a new exception is thrown.

For strict frameworks or helpers, you can preserve the original failure and attach the cleanup error using `Throwable.addSuppressed(...)`. If cleanup fails, log the temporary root and remaining state for investigation; never silently swallow errors or delete files outside scope to "fix" it.

Example pattern preserving both errors (structural illustration, not standalone):

~~~java
Throwable primary = null;
try {
    runTestBody(root);
} catch (Throwable failure) {
    primary = failure;
    throw failure;
} finally {
    try {
        deleteTree(root);
    } catch (IOException cleanupFailure) {
        if (primary != null) {
            primary.addSuppressed(cleanupFailure);
        } else {
            throw cleanupFailure;
        }
    }
}
~~~

In practice, the `Throwable` type and rethrowing must match the method signature and checked exception handling; the snippet only illustrates preserving failure information. `try-with-resources` provides automatic suppressed-exception handling for `AutoCloseable` resources, which **does not apply directly to `Path`** because `Path` has no `close()`.

## 7. Do Not Delete Files While Streams or Channels Are Still Open

A scenario may open `InputStream`, `OutputStream`, `FileChannel`, `RandomAccessFile`, or `DirectoryStream`. Those resources must be closed **before** deleting the root.

On some operating systems, especially Windows, an open file may not allow deletion or renaming. On other systems, deleting an open file behaves differently; never treat your current machine's behavior as a portable contract.

Structured pattern:

~~~java
Path root = Files.createTempDirectory("channel-test-");
try {
    Path file = root.resolve("payload.bin");

    try (var output = Files.newOutputStream(
            file, StandardOpenOption.CREATE_NEW)) {
        output.write(new byte[] { 1, 2, 3 });
    }

    try (var input = Files.newInputStream(file)) {
        int firstByte = input.read();
        if (firstByte != 1) {
            throw new AssertionError("Unexpected byte");
        }
    }
} finally {
    deleteTree(root);
}
~~~

This is an illustrative snippet; `deleteTree` was defined in the standalone example. `try-with-resources` ensures streams are closed before cleanup executes. If asynchronous callbacks or workers are still writing files, the scenario must also wait for or cancel them and confirm they have finished before deleting.

## 8. Temporary Root vs. Working Directory: Do Not Confuse Them

Three locations can have distinct meanings:

- **Current working directory:** usually tied to `System.getProperty("user.dir")`, such as the directory where Maven/Gradle was launched. Do not write test files here if tests need independence.
- **Default temporary directory:** usually tied to the JVM/provider environment configuration (such as the `java.io.tmpdir` property on the default provider).
- **Test-selected parent directory:** for example, a temporary workspace assigned by the runner/CI for the test job; call `createTempDirectory(parent, prefix)` to place the scenario root there.

Do not assume that changing `System.setProperty("java.io.tmpdir", ...)` while the JVM is running will redirect all subsequent `Files.createTempDirectory` calls elsewhere. The filesystem provider or JVM may cache configuration beforehand; to choose a location explicitly, **pass `Path parent` directly**.

Example:

~~~java
Path parent = Path.of("/workspace/test-scratch");
Files.createDirectories(parent);
Path scenario = Files.createTempDirectory(parent, "parse-");
~~~

This path example only applies on systems that have `/workspace/test-scratch`. For cross-platform execution, obtain `parent` from build/test configuration or construct an appropriate `Path`; do not hardcode POSIX paths into programs meant for Windows.

### Which Temporary Location Should You Choose?

If a scenario tests ordinary file I/O, the default temporary area is usually fine. However, when testing filesystem-dependent behaviors, the root location matters:

- **`Files.move(..., ATOMIC_MOVE)`:** may require paths on the same filesystem and provider support; not every filesystem guarantees this operation.
- **File locks, file permissions, symlinks:** depend on the OS, mount options, and process privileges.
- **Testing network filesystems:** to actually test NFS/SMB, choose a parent located on an NFS/SMB mount rather than defaulting to local temp storage and extrapolating remote behavior.
- **Size/quota:** a temporary area may have a small quota or live on RAM-backed `tmpfs`; do not assume unlimited space.

## 9. How Do Temporary Directories Support Parallel Tests?

Suppose a test runner executes two tests concurrently:

~~~text
Thread A:
  rootA = createTempDirectory("case-A-")
  write rootA/input.txt
  assert rootA/output.txt
  cleanup rootA

Thread B:
  rootB = createTempDirectory("case-B-")
  write rootB/input.txt
  assert rootB/output.txt
  cleanup rootB
~~~

Because `rootA` and `rootB` differ, both threads can use the same relative file names without writing to the same path.

However, to be **truly independent**, tests must also not depend on execution order. For example, test B must not assume test A already ran and produced certain data. If shared fixtures are unavoidable, declare setup/teardown and synchronization explicitly via the framework.

Limitations still to account for:

1. Disk space in the shared temporary directory can be exhausted by multiple tests running together.
2. Two tests can collide on resources outside the root such as ports, databases, or static state.
3. A failing test may leave files behind if the process is killed before `finally`.
4. Running too many I/O tasks in parallel can cause contention and make benchmarks fluctuate.
5. Antivirus, file indexers, or other scanners can delay file operations, especially on Windows CI.

Creating separate roots is **an isolation layer**, not a security sandbox between untrusted processes.

## 10. Using JUnit Jupiter `@TempDir` When a Framework Is Present

In projects using **JUnit Jupiter (JUnit 5)**, the `@TempDir` extension provides a temporary directory for tests so you do not have to write create/delete boilerplate in every test.

Illustrative example, **not part of the standard JDK**; requires the appropriate JUnit Jupiter dependency:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class FileProcessingTest {

    @Test
    void readsGeneratedFile(@TempDir Path tempDir) throws Exception {
        Path file = tempDir.resolve("input.txt");
        Files.writeString(file, "hello", StandardCharsets.UTF_8);

        assertTrue(Files.exists(file));
        assertEquals("hello",
                Files.readString(file, StandardCharsets.UTF_8));
    }
}
~~~

When the test runner/extension manages the root, **do not manually delete the framework's root while another test may still have access to it**. Scope and cleanup policies can depend on the framework version and configuration; check the documentation for your exact version. The `@TempDir Path tempDir` parameter pattern prevents tests from relying on hardcoded names or the working directory.

For **JUnit 4**, some projects use the `TemporaryFolder` rule; that is a different framework API with different lifecycle rules. Do not mix it up with JUnit Jupiter just because the names look similar.

### When to Use a Manual Helper Instead of `@TempDir`?

- The code runs as a standalone Java application with no test library dependencies.
- You need multiple temporary roots with different lifecycles within a single test.
- You need to choose a specific parent or mount to test a filesystem or network share.
- You need to retain artifacts on test failure under a custom debugging policy.
- You need fine-grained control over publish/cleanup steps in multi-process integration tests.

In standard JUnit Jupiter usage, `@TempDir` is usually more concise and reduces boilerplate.

## 11. Small, Clear, and Deterministic Test Data

Temporary directories isolate paths, but reliable tests also need **deterministic** fixtures:

- Specify UTF-8 explicitly for text: `Files.writeString(path, text, StandardCharsets.UTF_8)`.
- When byte-level protocols matter, write explicit `byte[]` instead of relying on the platform default charset.
- Avoid relying on OS timestamps or clocks to verify a file was processed; `lastModifiedTime` resolution can vary.
- Do not print random root names to stdout if you need to assert fixed output; write the root path to a separate debug log instead.
- If a scenario needs large data, generate it in chunks rather than allocating one giant array the size of the file.
- When testing how existing files are handled, create the file in **that scenario's own setup** rather than relying on leftover data from a prior test.
- Separate `expected` and `actual` files into subdirectories so the test cannot accidentally overwrite its own expected answer.

Example layout:

~~~text
scenario-root/
  fixtures/
    input.csv
    expected.json
  actual/
    result.json
  diagnostics/
    process.log
~~~

`expected.json` can be generated from a verified literal or copied from a **read-only** test resource, then placed into the scenario root before running. What matters is that each test has its complete input set and never mutates shared source resources.

## 12. Handling Tests That Deliberately Trigger Errors

Some scenarios must verify behavior when:

- The input file is missing.
- The output file already exists.
- The file name is invalid.
- File content has invalid encoding.
- Permissions are missing or the disk is full.
- A processing thread is interrupted or a channel closes mid-operation.

In these scenarios, **a dedicated root prevents corrupting other tests' environments**, though not every filesystem error can be simulated simply by creating a temporary directory.

Example verifying a method rejects overwriting:

~~~java
Path root = Files.createTempDirectory("collision-");
try {
    Path file = root.resolve("output.txt");
    Files.writeString(file, "already exists");

    boolean rejected = false;
    try {
        Files.newOutputStream(file, StandardOpenOption.CREATE_NEW).close();
    } catch (java.nio.file.FileAlreadyExistsException expected) {
        rejected = true;
    }

    if (!rejected) {
        throw new AssertionError("Expected overwrite protection");
    }
} finally {
    deleteTree(root);
}
~~~

This is an illustrative snippet; `deleteTree` was defined in section 5 and requires importing `Files`, `Path`, and `StandardOpenOption`. If you want to test missing permissions, do not assume `setReadable(false)`/`setWritable(false)` works identically across Windows, POSIX, containers/root user, and network shares. Use an appropriate environment or file I/O abstraction when you need a portable check.

## 13. Temporary Files and Security: Logic Isolation Is Not a Sandbox

`Files.createTempDirectory` helps prevent path collisions, but **it does not grant permission to process arbitrary user data as if it were safe**. Distinguish two situations:

**Testing test-generated data:** the default temporary root is usually sufficient to prevent cross-scenario interference, provided cleanup only operates within that root.

**Untrusted extraction/uploads/data:** you must also enforce size limits, file counts, path traversal checks, symbolic link checks, file permissions, and output validation. A random temporary name does not prevent every attack targeting the containing directory.

Considerations:

- **Never use an externally supplied path as a recursive deletion root.** Ensure `root` was created by the component itself and cannot be replaced with an untrusted value.
- **Do not follow symlinks** during cleanup unless explicitly required. `walkFileTree` does not follow symlinks by default, reducing the risk of escaping the cleanup area.
- **Do not share a root with untrusted processes.** If another process can swap entries inside the root during cleanup, race/TOCTOU risks still exist.
- **Never put secrets in the prefix name.** Temporary directory names can appear in logs, file listings, or error reports.
- **Access permissions:** when sensitive data is involved, evaluate permissions on the root, parent, and underlying storage; pass provider-appropriate `FileAttribute` values when needed while handling platforms that do not support those attributes.
- **Do not use `deleteOnExit()` as the primary management mechanism** for a large test suite: the path list stays in memory until JVM exit, and cleanup is not guaranteed if the process is killed.

### Root Directories and Symlinks

If the root is `/tmp/case-abc` and contains a symlink `external -> /home/user/documents`, `Files.walkFileTree(root, visitor)` **does not traverse through the symlink by default**; the symlink is typically visited as a file entry so only the link itself is deleted. However, in an environment where another actor modifies the tree concurrently, you must still control permissions and avoid opening files by untrusted paths after the check.

## 14. Retaining Artifacts for Debugging Without Polluting Other Tests

Sometimes deleting everything immediately upon failure makes investigation hard. A practical policy:

1. **Clean up by default**, even when a test fails.
2. When an explicit debug mode is enabled, retain **only the root of the failed scenario** and log its path.
3. Enforce retention limits, disk quotas, and periodic cleanup controlled by the runner/administrator.
4. Keep root names and log contents free of unnecessary sensitive data.
5. In CI, when artifacts must be inspected, copy selected outputs/logs to the official artifact area and then clean up the temporary root; do not rely on temporary directories surviving after the job.

A configuration variable like `KEEP_TEST_ARTIFACTS` can control this policy in a helper, retaining files only when an operator explicitly enables it. **Do not enable it by default just for convenience**, because leftover large files can fill CI disks.

### Measuring Resource Limits

Giving each scenario its own root also makes it easier to measure and bound resource usage: counting files created, total bytes written, open handles, and cleanup duration. However, counting after a test finishes does not protect against disk-full conditions while writing; for untrusted inputs, quotas must be enforced **inside the read/write loop**.

## 15. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Every test writes to the same `./output.txt` | Overwritten files, order-dependent tests | Separate temporary root per scenario |
| Using timestamps as names without collision checks | Parallel tests collide on names | `Files.createTempDirectory` |
| Calling `Files.createDirectories(sharedRoot)` and treating it as isolated | Reuses stale data | Create a **new subdirectory** with `createTempDirectory` |
| Directly deleting a non-empty root | `DirectoryNotEmptyException` | Delete children before parents with `walkFileTree` |
| Cleanup deletes the shared temporary area | Loses data belonging to other tasks | Only delete roots **you created and own** |
| Forgetting `finally` when a test fails | Leftover temporary files | Clean up on all execution paths |
| Failing to close streams before cleanup | Deletion fails, especially on Windows | `try-with-resources` before cleanup |
| Using `deleteOnExit()` for every file | Leaks path list until JVM exit, not guaranteed if killed | Active, managed cleanup |
| Uncontrolled symlink-following tree walk | May escape the temporary root | Do not enable `FOLLOW_LINKS` unnecessarily |
| Printing the temp folder name and asserting exact stdout | Non-deterministic tests | Assert only stable content/results |
| Assuming every OS/filesystem supports all permissions and atomic moves | Cross-platform CI fails | Test real environments, handle unsupported cases |
| Sharing a root across parallel tests that write data | Races and non-determinism | Per-test root or explicit locking |
| Cleanup exception hides the original test error | Hard to diagnose root cause | Suppress/record cleanup errors as well |
| Tests mutate global `java.io.tmpdir` at runtime | Not portable, affects other tests | Pass `Path parent` to the API |
| Creating a temp directory yet still writing files outside the root | Isolation is broken | Pass the root into every I/O component |

## 16. Self-Check Questions

**Q1.** Two parallel tests both write `output/result.json`. How do you avoid conflicts while keeping the same relative name?

**Answer:** Each test calls `Files.createTempDirectory(...)` to obtain its own root, then uses `root.resolve("output/result.json")`. The relative names are identical, but the full paths are distinct.

**Q2.** `Files.createTempDirectory` returns a `Path`. When the `root` variable leaves scope, is the directory automatically deleted?

**Answer:** No. `Path` is not `AutoCloseable` and does not delete itself. Use `finally`, a helper, or a framework such as JUnit Jupiter `@TempDir` to manage cleanup.

**Q3.** Why can `Files.delete(root)` fail even when the test created `root`?

**Answer:** Because `root` still contains files or subdirectories. You must traverse and delete child entries before deleting `root`.

**Q4.** Can multiple tests share a common parent directory?

**Answer:** Yes, if each test creates **a new child root** using `createTempDirectory(parent, prefix)` rather than writing/deleting indiscriminately inside the parent itself.

**Q5.** How does closing a `FileChannel` relate to cleanup?

**Answer:** An open channel can hold a handle or lock that prevents file deletion on some operating systems. Close it with `try-with-resources` before deleting the tree.

**Q6.** A scenario intentionally causes a parse error and throws an exception. Should the temporary directory still be cleaned up?

**Answer:** Yes, by default policy. `finally` runs when a method exits via a normal exception; if you want to retain it for debugging, use a separate mode with quotas and later cleanup.

**Q7.** Is `@TempDir` an annotation from Java SE 17?

**Answer:** No. It is a feature provided by **JUnit Jupiter** and requires the corresponding framework/dependency. `Files.createTempDirectory` is the one in Java SE.

**Q8.** Does creating a new temporary root guarantee protection against all path traversal attacks from a user-supplied ZIP?

**Answer:** No. You still must validate entry paths, handle symlinks, permissions, size limits, concurrency, and apply safe extraction policies.

## 17. Takeaways

- **Giving each I/O scenario its own temporary root** reduces data contamination, order-dependent tests, and parallel execution conflicts.
- **`Files.createTempDirectory` creates a new directory; `Path` does not auto-clean.** Whoever creates the root is responsible for deleting it.
- **Delete children before parents** using `Files.walkFileTree`, without following symlinks unless needed; close streams/channels before cleanup.
- **Pass the root into the code under test** instead of writing to the working directory or mutating JVM-wide temp settings.
- **Framework `@TempDir`** automates lifecycle management in JUnit Jupiter; in standalone Java programs, use a helper and `try/finally`.
- **Root isolation is the foundation of reliable tests**, but it does not replace quotas, path security, coordination of non-filesystem resources, and testing in real environments.
