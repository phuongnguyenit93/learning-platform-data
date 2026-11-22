# Completing an Integrated Java I/O Example and Testing Failure Branches

## 1. Objectives and Completion Criteria

This exercise integrates the Java I/O/NIO.2 components covered so far into a runnable, testable pipeline: **read bytes → decode UTF-8 → read line by line → validate data → compute → write temp file → move result to target location**. Alongside the happy path, every potential failure point must have a test showing that the error is caught, resources are closed, and any previous valid output remains intact before the commit step.

After this lesson, you should be able to explain the difference between data-format errors and I/O errors, the role of `try-with-resources`, why you should never overwrite an old report directly, how to inject controlled faults, and how to test **both the exception and post-exception file state**.

**Sample problem:** Read a UTF-8 `orders.csv` file with two columns `id,quantity`, compute record count and total quantity, and write `report.txt` containing `records=...` and `totalQuantity=...`. This exercise uses **simple CSV with exactly one comma per line**, without supporting quoted fields or commas inside values; production CSV systems require a dedicated parser.

Data rules: the first line must strictly be `id,quantity` (no BOM); each subsequent line must have an ID matching `[A-Za-z][A-Za-z0-9_-]{0,31}`, no duplicate IDs, and `quantity` as a positive `long` integer. Blank lines, invalid numbers, negative/zero numbers, duplicate IDs, malformed UTF-8 data, or sum overflow all fail the operation. A header-only file is valid and produces a report with 0 records and total 0.

Example input:

```csv
id,quantity
apple,2
banana,7
```

Resulting `report.txt` content:

```text
records=2
totalQuantity=9
```

## 2. Pipeline Design and Responsibility Boundaries

1. `generate` accepts input/output `Path`s, forbids using the same file for both, and orchestrates two phases.
2. `parse` uses `Files.newInputStream`, `InputStreamReader` with a UTF-8 decoder in `REPORT` mode, and `BufferedReader` for sequential processing. All parsing and validation happen **before creating any new report**.
3. `writeSafely` writes the result to a temp file in the **same directory** as the target, closing the writer before moving; it calls `Files.move(..., ATOMIC_MOVE, REPLACE_EXISTING)` to request atomic rename when supported by the filesystem. If atomic move is unsupported, it throws a clear error rather than silently downgrading to a weaker operation.
4. `finally` deletes the temp file if it still exists. `BeforeCommit` is a test-only fault-injection hook allowing failure right after writing the temp file without depending on OS or file permissions.
5. The test suite uses an isolated temporary directory per test case and cleans up afterward. Assertions verify output values, **expected exception types**, and side effects on old/temp files.

In this single-threaded example, "safely" means **avoiding intentionally replacing the old report before new data is read, validated, and fully written**; rename atomicity must be provided by the filesystem. This is not a multi-file transaction mechanism, concurrent-write defense, or guarantee that data has been physically synced to storage hardware.

## 3. Complete Code: Java 17 or Newer

Save the entire program below in **`IntegratedIoDemo.java`** (single file, no third-party libraries). `Summary` uses a `record`, and test methods live in the same class so it runs directly with the JDK.

```java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.MalformedInputException;
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.stream.Stream;

public class IntegratedIoDemo {
    record Summary(int records, long totalQuantity) {}

    static final class DataFormatException extends IOException {
        DataFormatException(String message) { super(message); }
        DataFormatException(String message, Throwable cause) { super(message, cause); }
    }

    @FunctionalInterface
    interface BeforeCommit {
        void run(Path temporaryFile) throws IOException;
    }

    static void generate(Path input, Path output) throws IOException {
        generate(input, output, temporaryFile -> {});
    }

    static void generate(Path input, Path output, BeforeCommit beforeCommit)
            throws IOException {
        Path target = output.toAbsolutePath().normalize();
        if (Files.exists(input) && Files.exists(target)
                && Files.isSameFile(input, target)) {
            throw new IOException("Input and output must be different files");
        }
        Summary summary = parse(input);
        writeSafely(target, summary, beforeCommit);
    }

    private static Summary parse(Path input) throws IOException {
        Set<String> seenIds = new HashSet<>();
        int records = 0;
        long total = 0;

        // Stream bytes -> strict UTF-8 decoding -> buffered text lines.
        try (BufferedReader reader = new BufferedReader(new InputStreamReader(
                Files.newInputStream(input),
                StandardCharsets.UTF_8.newDecoder()
                        .onMalformedInput(CodingErrorAction.REPORT)
                        .onUnmappableCharacter(CodingErrorAction.REPORT)))) {
            if (!"id,quantity".equals(reader.readLine())) {
                throw new DataFormatException("Line 1: expected id,quantity header");
            }
            String line;
            int lineNumber = 1;
            while ((line = reader.readLine()) != null) {
                lineNumber++;
                String[] fields = line.split(",", -1);
                if (fields.length != 2
                        || !fields[0].matches("[A-Za-z][A-Za-z0-9_-]{0,31}")) {
                    throw new DataFormatException("Line " + lineNumber + ": invalid CSV row");
                }
                long quantity;
                try {
                    quantity = Long.parseLong(fields[1]);
                } catch (NumberFormatException error) {
                    throw new DataFormatException(
                            "Line " + lineNumber + ": quantity is not a long", error);
                }
                if (quantity <= 0) {
                    throw new DataFormatException(
                            "Line " + lineNumber + ": quantity must be positive");
                }
                if (!seenIds.add(fields[0])) {
                    throw new DataFormatException(
                            "Line " + lineNumber + ": duplicate id " + fields[0]);
                }
                try {
                    total = Math.addExact(total, quantity);
                    records = Math.incrementExact(records);
                } catch (ArithmeticException error) {
                    throw new DataFormatException(
                            "Line " + lineNumber + ": aggregate overflow", error);
                }
            }
        }
        return new Summary(records, total);
    }

    private static void writeSafely(Path output, Summary result,
                                    BeforeCommit beforeCommit) throws IOException {
        Path parent = output.getParent();
        if (!Files.isDirectory(parent)) {
            throw new IOException("Output parent directory does not exist: " + parent);
        }
        if (Files.isDirectory(output)) {
            throw new IOException("Output is a directory: " + output);
        }

        // A temp file in the same directory enables an atomic rename where supported.
        Path temporary = Files.createTempFile(parent, ".report-", ".tmp");
        try {
            try (BufferedWriter writer = Files.newBufferedWriter(temporary,
                    StandardCharsets.UTF_8,
                    StandardOpenOption.WRITE, StandardOpenOption.TRUNCATE_EXISTING)) {
                writer.write("records=" + result.records());
                writer.newLine();
                writer.write("totalQuantity=" + result.totalQuantity());
                writer.newLine();
            }
            beforeCommit.run(temporary); // Inject a failure here in a test.
            try {
                Files.move(temporary, output,
                        StandardCopyOption.ATOMIC_MOVE,
                        StandardCopyOption.REPLACE_EXISTING);
            } catch (AtomicMoveNotSupportedException error) {
                throw new IOException("Atomic move unsupported; output not replaced", error);
            }
        } finally {
            Files.deleteIfExists(temporary);
        }
    }

    @FunctionalInterface
    interface TestCase { void run(Path directory) throws Exception; }

    @FunctionalInterface
    interface ThrowingAction { void run() throws Exception; }

    static <T extends Throwable> T expect(Class<T> expected, ThrowingAction action)
            throws Exception {
        try {
            action.run();
        } catch (Throwable actual) {
            if (expected.isInstance(actual)) return expected.cast(actual);
            throw new AssertionError("Expected " + expected.getSimpleName()
                    + ", got " + actual, actual);
        }
        throw new AssertionError("Expected " + expected.getSimpleName());
    }

    static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    static void test(String name, TestCase body) throws Exception {
        Path directory = Files.createTempDirectory("io-lab-");
        try {
            body.run(directory);
            System.out.println("PASS " + name);
        } finally {
            try (Stream<Path> paths = Files.walk(directory)) {
                for (Path path : paths.sorted(Comparator.reverseOrder()).toList()) {
                    Files.deleteIfExists(path);
                }
            }
        }
    }

    static Path input(Path directory, String contents) throws IOException {
        Path path = directory.resolve("orders.csv");
        Files.writeString(path, contents, StandardCharsets.UTF_8);
        return path;
    }

    static void runTests() throws Exception {
        test("success", dir -> {
            Path source = input(dir, "id,quantity\napple,2\nbanana,7\n");
            Path result = dir.resolve("report.txt");
            generate(source, result);
            check(Files.readAllLines(result, StandardCharsets.UTF_8)
                    .equals(List.of("records=2", "totalQuantity=9")), "wrong report");
        });
        test("missing-input", dir -> {
            expect(NoSuchFileException.class,
                    () -> generate(dir.resolve("missing.csv"), dir.resolve("out.txt")));
        });
        test("bad-header", dir -> {
            Path source = input(dir, "wrong,header\na,1\n");
            expect(DataFormatException.class,
                    () -> generate(source, dir.resolve("out.txt")));
        });
        test("bad-row", dir -> {
            Path source = input(dir, "id,quantity\na,nope\n");
            expect(DataFormatException.class,
                    () -> generate(source, dir.resolve("out.txt")));
        });
        test("duplicate-id", dir -> {
            Path source = input(dir, "id,quantity\na,1\na,2\n");
            expect(DataFormatException.class,
                    () -> generate(source, dir.resolve("out.txt")));
        });
        test("sum-overflow", dir -> {
            Path source = input(dir,
                    "id,quantity\na,9223372036854775807\nb,1\n");
            expect(DataFormatException.class,
                    () -> generate(source, dir.resolve("out.txt")));
        });
        test("malformed-utf8", dir -> {
            Path source = dir.resolve("orders.csv");
            Files.write(source, new byte[] {(byte) 0xC3, (byte) 0x28});
            expect(MalformedInputException.class,
                    () -> generate(source, dir.resolve("out.txt")));
        });
        test("output-is-directory", dir -> {
            Path source = input(dir, "id,quantity\na,1\n");
            Path result = Files.createDirectory(dir.resolve("out.txt"));
            expect(IOException.class, () -> generate(source, result));
            check(Files.isDirectory(result), "directory changed");
        });
        test("old-report-survives-bad-input", dir -> {
            Path source = input(dir, "id,quantity\na,0\n");
            Path result = dir.resolve("out.txt");
            Files.writeString(result, "KEEP", StandardCharsets.UTF_8);
            expect(DataFormatException.class, () -> generate(source, result));
            check("KEEP".equals(Files.readString(result)), "old output changed");
        });
        test("failure-before-commit", dir -> {
            Path source = input(dir, "id,quantity\na,1\n");
            Path result = dir.resolve("out.txt");
            Files.writeString(result, "KEEP", StandardCharsets.UTF_8);
            expect(IOException.class, () -> generate(source, result,
                    temporary -> { throw new IOException("injected failure"); }));
            check("KEEP".equals(Files.readString(result)), "old output changed");
            try (Stream<Path> files = Files.list(dir)) {
                check(files.noneMatch(p -> p.getFileName().toString()
                        .startsWith(".report-")), "temporary file leaked");
            }
        });
        test("same-input-and-output", dir -> {
            Path source = input(dir, "id,quantity\na,1\n");
            expect(IOException.class, () -> generate(source, source));
            check(Files.readString(source).contains("a,1"), "input changed");
        });
    }

    public static void main(String[] args) throws Exception {
        if (args.length == 0) {
            runTests();
        } else if (args.length == 2) {
            generate(Path.of(args[0]), Path.of(args[1]));
            System.out.println("Created report: " + args[1]);
        } else {
            throw new IllegalArgumentException(
                    "Usage: java IntegratedIoDemo [input.csv output.txt]");
        }
    }
}
```

## 4. Compile, Run, and Observe Results

In the directory containing the Java file, run:

```bash
javac -encoding UTF-8 IntegratedIoDemo.java
java IntegratedIoDemo
```

On a filesystem supporting atomic rename, the program prints these exact 11 lines (verified on JDK 21 with Java 17-compatible source):

```text
PASS success
PASS missing-input
PASS bad-header
PASS bad-row
PASS duplicate-id
PASS sum-overflow
PASS malformed-utf8
PASS output-is-directory
PASS old-report-survives-bad-input
PASS failure-before-commit
PASS same-input-and-output
```

To run as an actual CLI tool, create `orders.csv` from section 1, then execute:

```bash
java IntegratedIoDemo orders.csv report.txt
```

This prints `Created report: report.txt` on success. The report file's content matches the example; file line endings depend on the platform, while `Files.readAllLines` verifies content line by line so tests avoid coupling to CRLF/LF.

## 5. Success and Failure Test Matrix

| Test Case | Trigger | Outcome to Prove |
|---|---|---|
| `success` | Valid data, two records | Produces report `records=2`, `totalQuantity=9` |
| `missing-input` | Source path has no file | `NoSuchFileException`; no output created |
| `bad-header` | Incorrect header | `DataFormatException` citing line 1 |
| `bad-row` | Quantity `nope` | `DataFormatException` instead of skipping the row |
| `duplicate-id` | ID `a` appears twice | Detects duplicate ID and stops |
| `sum-overflow` | Total exceeds `Long.MAX_VALUE` | `Math.addExact` catches overflow, prevents wrong report |
| `malformed-utf8` | Bytes `C3 28` do not form valid UTF-8 | `MalformedInputException` from decoder in `REPORT` mode |
| `output-is-directory` | Target path is a directory | Throws `IOException`; directory remains intact |
| `old-report-survives-bad-input` | Old report is `KEEP`, new input invalid | Old report remains character-for-character intact |
| `failure-before-commit` | Hook throws `IOException` after writer closes | Old report remains `KEEP`; zero `.report-*.tmp` files left |
| `same-input-and-output` | Source and target point to the same file | Rejects processing; source is not overwritten |

**Why verify post-error state?** Checking `expect(IOException.class, ...)` alone is insufficient: a program can still throw an exception *after already corrupting the output*. Both `old-report-survives-bad-input` and `failure-before-commit` directly verify immutability of the old data; the latter additionally verifies cleanup. Creating a dedicated temporary directory per test prevents results from depending on leftover state from prior runs.

## 6. Error Handling Mechanics and Resource Lifecycle

**Read path:** `Files.newInputStream` can throw `NoSuchFileException`, `AccessDeniedException`, or other `IOException`s. `InputStreamReader` converts bytes to characters using the specified decoder; `REPORT` mode ensures invalid UTF-8 bytes are reported rather than silently replaced with `�`. `BufferedReader.readLine()` is convenient for line-oriented data, though unsuitable when exact line endings must be preserved or multi-line records parsed. Closing `BufferedReader` in `try-with-resources` also closes the underlying reader and input stream, even when the parser throws.

**Validation path:** `DataFormatException extends IOException` represents input content failing the contract, with line numbers for diagnostics. `Long.parseLong` catches non-numeric text and out-of-range numbers; `Math.addExact` and `Math.incrementExact` prevent overflow during accumulation. `Set` catches duplicate IDs. This exercise chooses a **fail-fast** policy: a single invalid row fails the entire run without generating a partial report. If business logic requires collecting multiple errors to return together, design a separate validation-result model.

**Write path:** writing directly to `output` with `TRUNCATE_EXISTING` can wipe old content before an error strikes. A temp file in the same directory reduces the risk of cross-filesystem renames. The writer closes before `move`; if the hook throws, `finally` cleans up the temp file. If atomic rename is unsupported, the method throws an `IOException` wrapping `AtomicMoveNotSupportedException`. Under `ATOMIC_MOVE`, existing-target handling varies by provider; verify on your deployment filesystem, and never swallow access/write-permission errors as if they succeeded.

**Practical limitations note:** The example does not track disk space/quotas, does not call `FileChannel.force` to strengthen power-loss durability, does not solve concurrent updates to the report by multiple processes, and does not guard against path/symlink swaps between check and write. In a real service, add file-size limits, path/permission policies, contextual logging, and locking/coordination where required. Never write `catch (Exception) { }`, and never lose the underlying cause when wrapping into `DataFormatException`.

## 7. Self-Evaluating Results and Controlled Extensions

A complete submission must pass all of these together: the valid case runs green; each failure branch fails with the right exception type/group; existing valid content remains intact when validation or hooks fail; zero temp files leak; input and output are distinct; file handles close cleanly; and output is never published prior to the commit step.

To test deeper understanding, deliberately alter a test case to quantity `0` or `-1`, a row missing a comma, add a second comma, an empty header, an invalid ID, and a non-existent output parent: identify whether the failure occurs in the parse phase or write phase, and why. Try switching the decoder to `REPLACE` mode to see why strict mode is vital when data quality matters. When moving to CI, convert the tests into JUnit 5 using `@TempDir`, `assertThrows`, and `assertEquals`, keeping all data and cleanup assertions intact.

The core lesson of this exercise is **proving behavior under failure**, not merely proving one happy path works.
