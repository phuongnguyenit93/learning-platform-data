# Checking Error Status Instead of Only Comparing Message Strings in Java Compilation Testing

## 1. Problem: error messages are not a stable compiler contract

Suppose a test case creates a Java snippet with a type error and expects the compiler to reject the source code. An easy-to-write yet fragile way to test this is to assert that the printed message must contain an exact English sentence such as `incompatible types: String cannot be converted to int`.

The true goal of that test is not “the compiler printed the right English sentence”, but **the source code fails to compile due to an error**. The wording is how the tool *presents* the result; whereas the status and diagnostics are evidence of the compilation *behavior*.

This is the core distinction:

- **Compilation status:** success or failure (`JavaCompiler.CompilationTask.call()`, `javac` exit code, build task status).
- **Structured diagnostics:** severity (`ERROR`, `WARNING`…), source position, diagnostic code if supplied by the compiler, and explanatory message.
- **Display message:** text formatted by the formatter, locale, and implementation for human reading. This part can change even while compiler behavior remains correct.

A good test should clearly state **the invariant it wants to guarantee**, then assert at the appropriate level. For a case where Java code must be rejected, the primary condition is that the compilation task fails, typically accompanied by an `ERROR` diagnostic for the prepared source error.

## 2. Why matching the full message easily causes false failures?

Error messages depend on many variables:

| Source of Change | Example Impact | Effect on Verbatim String Matching |
|---|---|---|
| JDK/`javac` version | Explanatory sentence, hint position, diagnostic format change | Test fails even though code is still properly rejected |
| Locale/language | Message is localized or processed by a wrapper | English test no longer matches |
| Compiler flags | `-Xlint`, `-Werror`, `-XDrawDiagnostics` change result kind/format | Text snapshots easily drift |
| File path and environment | Absolute/relative paths, OS separators, working directory | Full stderr matching is unstable |
| Diagnostic order and count | One syntax error can trigger subsequent diagnostics | Line-count-dependent tests break easily |
| Different compiler/tooling | ECJ, `javac`, IDE/build-tool wrappers phrase things differently | Test gets locked to a formatter |
| Annotation processor/plugin | Can emit custom errors, add prefixes or locations | Message changes outside the lesson's intent |

For example, for the same error of failing to assign `String` to `int`, two compilers or two versions can emit different messages. Even matching `stderr.contains("incompatible types")` remains fragile if the text is translated or rephrased.

However, that does not mean **all** message assertions are wrong. If the product's goal is a **user-facing notification interface** (for instance, a compiler wrapper must print a filename or an error code defined by the project itself), you can test the message portion belonging to the product contract, with a pinned environment and appropriate tests. Keep those interface tests separate from tests of Java language validity.

## 3. Levels of checking, from stable to specific

Choose assertions in order based on the test goal:

1. **Compile outcome:** the command or task succeeds/fails as expected.
2. **Diagnostic severity:** at least one `Diagnostic.Kind.ERROR` for invalid-source tests; or no `ERROR` for valid sources.
3. **Source and location when needed:** the error pertains to the unit under test, and line/column fall within the expected range; do not require exact positions if the specification does not promise them.
4. **Diagnostic code** (`Diagnostic.getCode()`) only when provided by the tool/version and the test contract is narrow enough. Per the Java API, codes are **implementation-dependent** and may be `null`; they are not standardized error identifiers across all compilers.
5. **Text message** when literal wording is genuinely a requirement to verify, preferring segments owned by the **application itself** or a snapshot guarded by version, locale, OS, and compiler controls.

Do not assert `getDiagnostics().size() == 1` by default. One root error can emit multiple diagnostics depending on version or compiler flags. If what needs proving is that an error occurred, `anyMatch(kind == ERROR)` expresses this better than hardcoding the total diagnostic count.

**Important point:** `Diagnostic.Kind.ERROR` describes the diagnostic category. The overall outcome must still be checked independently: for example, a “warnings as errors” configuration can cause the compiler to fail under a warning policy even when the prominent diagnostics are warnings. Thus, a negative compile test relying solely on “has ERROR” can miss another failure path; conversely, relying solely on `call() == false` does not prove the exact reason for failure.

## 4. Java 17+: example testing compilation errors with structured APIs

Java provides the Java Compiler API in the standard `java.compiler` module, package `javax.tools`. `JavaCompiler` enables compiling from a Java program, while `DiagnosticCollector` captures diagnostics without parsing terminal output.

Below is **a complete Java program, runnable standalone with JDK 17+**. The program creates an in-memory source file with an invalid type assignment and asserts that the compiler must reject that source.

**File: `CompilerDiagnosticsTest.java`**

```java
import java.net.URI;
import java.util.List;

import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.ToolProvider;

public class CompilerDiagnosticsTest {
    public static void main(String[] args) {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("A full JDK compiler is required");
        }

        String invalidSource =
                "class Broken { int number = \"text\"; }";

        JavaFileObject sourceFile =
                new InMemorySource("Broken", invalidSource);

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        Boolean success = compiler.getTask(
                null,                    // output writer: default
                null,                    // file manager: standard
                diagnostics,             // structured diagnostics
                List.of("-proc:none"),   // no annotation processors
                null,                    // classes: none
                List.of(sourceFile)       // compilation units
        ).call();

        boolean compilationFailed = Boolean.FALSE.equals(success);
        boolean hasErrorDiagnostic = diagnostics.getDiagnostics()
                .stream()
                .anyMatch(d -> d.getKind() == Diagnostic.Kind.ERROR);

        if (!compilationFailed || !hasErrorDiagnostic) {
            throw new AssertionError(
                    "Expected compilation failure with ERROR diagnostic");
        }

        System.out.println("Compilation failed: " + compilationFailed);
        System.out.println("ERROR diagnostic found: " + hasErrorDiagnostic);
    }

    private static final class InMemorySource extends SimpleJavaFileObject {
        private final String source;

        private InMemorySource(String className, String source) {
            super(
                    URI.create("string:///" + className
                            + JavaFileObject.Kind.SOURCE.extension),
                    JavaFileObject.Kind.SOURCE
            );
            this.source = source;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return source;
        }
    }
}
```

Run in the directory containing the file:

```bash
javac CompilerDiagnosticsTest.java
java CompilerDiagnosticsTest
```

Expected stdout output:

```text
Compilation failed: true
ERROR diagnostic found: true
```

The example uses an **intentionally invalid** source snippet, so the compilation call inside the program returns `false`. However, *the test program itself* compiles and runs successfully; if the assertion fails, the test program throws `AssertionError`. Because the faulty source is created in memory and compilation fails, there is no valid `Broken.class` to execute.

Explanation of key parts:

- `ToolProvider.getSystemJavaCompiler()`: finds the current environment's compiler. May return `null` if the runtime does not supply a system compiler; run the example with a **JDK**, not just a minimal runtime.
- `SimpleJavaFileObject`: wraps the source string as a compilation unit with a URI and kind `SOURCE`.
- `DiagnosticCollector<JavaFileObject>`: receives individual diagnostic records instead of parsing console-printed errors.
- `compiler.getTask(...).call()`: runs the compilation task; the `Boolean` result indicates success or failure.
- `List.of("-proc:none")`: disables annotation processing so the fixture tests only the type-assignment error, reducing interference from external processors.
- `anyMatch(d -> d.getKind() == Diagnostic.Kind.ERROR)`: confirms at least one compiler error; does not depend on an English sentence or secondary error count.

We do not need to assert the messages `incompatible types`, `cannot be converted`, or exact caret positions to prove the expected behavior.

### 4.1. Why is this a more reliable test than string matching?

Consider the brittle assertion:

```java
// Illustrative anti-pattern; not a standalone program.
assertTrue(stderr.contains(
        "incompatible types: java.lang.String cannot be converted to int"));
```

It mixes two different contracts: “type-mismatched source is rejected” and “the compiler phrases the error with a specific sentence”. The API test above asserts only the first contract; a JDK update that changes phrasing while still rejecting invalid code will not break the test.

### 4.2. When error positions need to be verified

`javax.tools.Diagnostic` also supports:

```java
// Illustrative fragment to place after diagnostics have been collected.
for (Diagnostic<? extends JavaFileObject> d
        : diagnostics.getDiagnostics()) {
    if (d.getKind() == Diagnostic.Kind.ERROR) {
        long line = d.getLineNumber();
        long column = d.getColumnNumber();
        JavaFileObject source = d.getSource();
        String code = d.getCode();

        // Only assert position when required by behavior/compiler;
        // handle Diagnostic.NOPOS and potentially null source/code.
    }
}
```

Line/column positions are metadata assisting testing and debugging. The API has `Diagnostic.NOPOS` when no suitable position exists. `getSource()` can also be `null`. An assertion `line == 1` will be unstable if a blank line is added to the fixture or the compiler attributes the error to a different token; when the specification only requires reporting the error on the right file, checking the source URI or a meaningful position range is more reasonable.

## 5. Testing via CLI: exit code matters more than stderr

Not every test uses the Compiler API. In CI scripts or integration tests, `javac` often runs as a subprocess:

```text
Test fixture Java source
          |
          v
    javac subprocess
          |
          +-- exit code ----> primary assertion
          |
          +-- stdout/stderr -> log for diagnostics
```

For example, create **`BadExample.java`**:

```java
class BadExample {
    int age = "not a number";
}
```

On POSIX shells (bash/zsh), you can verify the result without string matching:

```bash
if javac BadExample.java; then
    echo "Unexpected success"
    exit 1
else
    echo "Compilation failed as expected"
fi
```

When using a normal JDK compiler, the script output is:

```text
Compilation failed as expected
```

Note: `javac` can still print diagnostics to stderr in addition to the echo line above. The line shown here is **stdout produced by the script**, not a claim that the entire terminal output is only one line.

With **PowerShell**, you can check `$LASTEXITCODE` immediately after running the native `javac` application:

```powershell
javac BadExample.java
if ($LASTEXITCODE -eq 0) {
    throw "Unexpected compilation success"
}
Write-Output "Compilation failed as expected"
```

The `$LASTEXITCODE` variable indicates the exit code of the most recent native process; check it right after `javac` so it is not overwritten by another command. A script using a negative fixture definitely catches failure, yet **a non-zero exit code alone is not enough to prove it was the expected kind of error**: for instance, `javac` not found, missing file, permission denied, or an invalid invocation can also make the test fail. Therefore, in integration tests, verify that the process launched properly, the source fixture exists, and appropriate diagnostic signals are present.

### 5.1. Do not confuse compile status with printed error counts

The `javac` CLI provides an exit code, but by default does not emit standardized JSON diagnostics. If you only have stdout/stderr:

1. Assert the exit code per the positive/negative goal.
2. Keep stderr as **troubleshooting** data when a test fails.
3. If verifying the **error kind** is mandatory, consider using the Java Compiler API or a project-defined adapter with a stable schema.
4. If using compiler-specific options like `-XDrawDiagnostics` to aid parsing, remember that codes and formats are **tied to the implementation** and are not guaranteed stable across vendors/versions by Java SE.

Do not use `stderr.isBlank()` as the sole condition to infer compilation success: a tool can print warnings to stderr while still returning code 0; conversely, a tool can fail due to configuration errors before emitting source diagnostics.

## 6. Designing test suites with positive, negative, and warning outcomes

A compilation test suite should express each contract independently:

| Case | What to Check | What Not to Assume |
|---|---|---|
| Valid Java source | Compilation succeeds; no `ERROR` diagnostic | Zero messages of any kind |
| Type-mismatched source | Compilation fails; has `ERROR` | Specific text phrasing and exact count of one error |
| Source missing a symbol | Compilation fails; diagnostic matches the fixture | Exact line wording `cannot find symbol` stays unchanged |
| Warning present when policy permits | Compilation succeeds; warning captured if test requires it | Warning is always on stderr or always a single record |
| `-Werror` enabled | Compilation may fail because warnings are treated as errors | Every diagnostic changes its kind to `ERROR` |
| Processor actively reports an error | Compilation fails and has appropriate diagnostic | Source line or message matches plain `javac` errors |
| Tool fails to launch | Test fails due to infrastructure/configuration | Counted as a passing “source rejected” test |

**Negative tests must eliminate false positives caused by infrastructure.** When running a `javac` process, log the executable, working directory, classpath/module-path, JDK version, and actual source units. A non-zero exit code does not confirm the compiler read the right fixture.

**Positive tests must verify the right success condition.** When warnings occur, do not require “zero diagnostics” if the goal is merely accepting valid source. When policy mandates zero warnings, that is a separate contract requiring explicit flags and assertions.

## 7. Using JUnit 5: separating assertions from message data

In projects with JUnit Jupiter, the Compiler API example logic can be extracted into a helper returning a result:

```java
// The following snippets illustrate the test API, not standalone classes.
record CompileResult(
        boolean succeeded,
        List<Diagnostic<? extends JavaFileObject>> diagnostics) {

    boolean containsError() {
        return diagnostics.stream()
                .anyMatch(d -> d.getKind() == Diagnostic.Kind.ERROR);
    }
}
```

Once a `compile(source)` helper is implemented using the Java Compiler API and returns `CompileResult`, contract-based assertions can be written as:

```java
// JUnit 5 fragment, requiring helper compile(...) and appropriate imports.
@Test
void invalidAssignmentMustBeRejected() {
    CompileResult result = compile(
            "class Bad { int count = \"oops\"; }");

    assertFalse(result.succeeded());
    assertTrue(result.containsError());
}

@Test
void validAssignmentMustCompile() {
    CompileResult result = compile(
            "class Good { int count = 7; }");

    assertTrue(result.succeeded());
    assertFalse(result.containsError());
}
```

Both fragments are clearly noted as **illustrations depending on a helper**; the standalone program in section 4 is a complete example requiring no JUnit.

Diagnostic details can be attached to assertions to aid readability on test failure, such as using `assertAll(...)` and a message lambda containing the diagnostic list. Distinguish **failure context messages** (useful for diagnostics) from **strings asserted as expected content** (which easily make tests brittle).

If the build policy requires diagnostics to belong to a specific source file, check `getSource()` before comparing URIs; if the exercise only needs to prove code does not compile, asserting detailed source/line/column adds fragility without increasing confidence.

## 8. Asserting compiler diagnostic codes: when is it valuable?

The `Diagnostic.getCode()` API returns a diagnostic kind code, yet Java SE documentation states the code **is implementation-dependent and may be null**. Codes emitted by `javac` in certain contexts can be very useful for regression analysis when a team **pins the exact JDK and compiler**.

Contract classification:

- **Java language / compiler integration contract:** compile pass/fail, `Kind.ERROR`, source and position at the needed granularity. Do not lock down full messages.
- **Fixed javac version contract:** specific diagnostic codes can be checked if the testing team owns the baseline/version and plans updates when upgrading the JDK.
- **Product-built-on-compiler contract:** translate compiler diagnostics into **stable internal product error codes** before public APIs or tests depend on them.

For example, a learning platform can map classified diagnostics to `JAVA_TYPE_MISMATCH` in its own domain. Internal API tests can then assert `JAVA_TYPE_MISMATCH` even if `javac`'s English sentence changes. However, **that mapping is application-authored code**, not a standardized domain code list provided by default by the Java Compiler API.

If the product does not yet have a reason to check individual error classifications, keep tests simple and verify `ERROR` alongside compile status.

## 9. Special cases: warnings, tool errors, and annotation processors

### 9.1. Warnings are not identical to errors

`Diagnostic.Kind` has the values `ERROR`, `WARNING`, `MANDATORY_WARNING`, `NOTE`, and `OTHER`. Not every emitted diagnostic causes compilation to fail. The `-Xlint` flag enables warnings; `-Werror` causes `javac` to fail when warnings appear.

For fixtures intentionally triggering warnings, two testing approaches are:

- When policy permits warnings: assert compilation succeeds, then inspect for a warning *if* the test intentionally verifies that warning.
- When policy forbids warnings: enable `-Werror`, assert compilation fails, and verify the appropriate warning signal. Do not assume every warning turns into `Kind.ERROR`.

A test using only `hasErrorDiagnostic` as a “compile failed” flag will not fully cover warnings-as-errors policies. Evaluate both the **task result** and the **diagnostic kind** according to each goal.

### 9.2. Invocation errors and compilation errors must remain distinct

In the Java Compiler API, `ToolProvider.getSystemJavaCompiler()` can return `null` in environments lacking a compiler. Misusing the API, passing invalid options, or I/O errors can also lead to exceptions or failures unrelated to type errors in Java source.

A trustworthy test suite treats build-system failures as **test infrastructure failures**; do not “pass” a negative source test merely because everything failed. For process tests, verify the compiler executable exists and launches; for API tests, verify the compiler is non-`null` and handle exceptions separately.

### 9.3. Annotation processors emit their own diagnostics

A processor can use `Messager.printMessage(Diagnostic.Kind.ERROR, ...)` to fail a build when an annotation is invalid. These are messages from the processor, not necessarily having the same wording, position, or code as `javac`'s type-checking errors.

If the test target is a processor:

- Provide small, fixed annotations/inputs.
- Verify compilation failure and `ERROR` diagnostics from the invocation using the processor.
- Verify the source/element or **domain code owned by the processor** if such a contract exists.
- Verify accepted cases produce no errors and emit the right artifacts.
- Do not enable `-proc:none` in processor tests; that flag was only used in section 4's example to exclude processors from test scope.

## 10. Integrating with Gradle and Maven without confusing layers

With Gradle or Maven, compile testing can occur at multiple layers:

```text
Java source (possibly intentionally invalid)
         |
         v
javac / compiler provider
  |          |
  |          +-- structured diagnostics / stdout / stderr
  v
compiler success/failure
         |
         v
Gradle task or Maven plugin goal
         |
         v
build success/failure + test report
```

A build task's status is not a `Diagnostic.Kind`. For example, `:compileJava` can also fail due to dependency resolution, missing toolchain, annotation processor exceptions, or configuration errors, not only Java syntax. Similarly, a build marked `UP-TO-DATE` did not necessarily re-run the negative fixture in that run.

To test an intentionally invalid fixture while keeping the main build healthy, place it as a **separate test input** sent to the Compiler API or compiler invocation inside the test harness, **not** inside the production `src/main/java` source set where every build fails.

When using the Gradle Test task or Maven Surefire to run compiler-integrated JUnit tests, ensure tests are not accidentally skipped by up-to-date/cache checks when verifying new fixtures. Use forced reruns only when genuinely needed for diagnosis. Compiler and classpath configuration for test fixtures must be tightly controlled, especially in multi-module projects.

## 11. Anti-patterns and alternatives

| Anti-pattern | Why Unreliable | Alternative |
|---|---|---|
| `assertEquals("...full compiler error...", stderr)` | Depends on formatter, locale, paths, version | Assert fail status + `ERROR` diagnostic |
| `assertTrue(stderr.contains("cannot find symbol"))` | Implementation-dependent wording | Assert error on source fixture with compiler API |
| `assertEquals(1, diagnostics.size())` | Diagnostics may add warnings/notes or multiple errors | `anyMatch(kind == ERROR)` or filter precisely as needed |
| `assertFalse(success)` without checking cause | Broken tooling can also report failure | Verify compiler launched, valid fixture, appropriate diagnostic |
| `assertNotNull(d.getCode())` for every compiler | `getCode()` may be null per the API | Check code only when guaranteed by compiler contract |
| Asserting exact line/column in every test | Formatting/diagnostic span changes cause breakage | Check position only when required |
| Treating `WARNING` as `ERROR` | Misclassifies `-Werror` policies | Check `Kind` and task result independently |
| Putting intentionally invalid sources into main source set | Fails the entire project before tests run | Use in-memory fixtures or separate test resource directories |
| Catching every exception as “expected compile failure” | Hides infrastructure/compiler invocation failures | Distinguish infrastructure exceptions from source diagnostics |

### When are message snapshots a reasonable choice?

Snapshots are useful when testing **the UX of an editor, linter, or project-owned CLI**, where message formatting is a user-facing feature. In that case:

1. Pin the JDK, compiler, locale, timezone, and relative fixture paths appropriately.
2. Separate layers: semantic compile unit tests use status/diagnostics; snapshot tests check only the formatter layer.
3. Normalize non-contract details (temporary directories, path separators, ANSI colors) before comparing snapshots.
4. Review snapshot diffs when upgrading toolchains rather than blindly updating golden files.

For tests whose goal is “this Java source must be rejected”, message snapshots are usually unnecessary maintenance overhead.

## 12. Process for designing a reliable compilation test

**Step 1 — Write the requirement in behavioral terms.** “Code assigning a string to an int variable must be rejected” or “a valid declaration snippet must compile successfully”. Avoid putting compiler wording into requirements upfront.

**Step 2 — Choose the test layer.** Verify Java semantics inside the JVM via `JavaCompiler`, CLI via `javac`, or end-to-end results via Gradle/Maven. Higher layers demand greater care distinguishing toolchain/dependency errors from source errors.

**Step 3 — Prepare a minimal fixture.** Use a small compilation unit with matching file/class names, requiring no external libraries unless the test intentionally checks classpath behavior. Avoid putting multiple independent errors in one source since the compiler may emit order-dependent diagnostics.

**Step 4 — Check the primary outcome.** Assert `call() == false` or non-zero compiler process exit for negative tests; conversely assert success for positive tests.

**Step 5 — Add cause-verifying signals.** For negative type errors, check for `Kind.ERROR` and that the compiler received the right source. For annotation processor tests, you may also use markers or processor-owned codes.

**Step 6 — Put text into debug info.** When an assertion fails, log diagnostics with `kind`, `source`, `line`, `column`, `code`, and `message` for maintainers to read, without comparing non-contract fields verbatim.

**Step 7 — Test compiler upgrades/locale changes (when practically needed).** A good semantic test remains valid when diagnostic phrasing changes; otherwise, revisit whether the assertion accidentally coupled to the formatter.

## 13. Knowledge-check exercises

**Exercise 1.** A test for `int quantity = "3";` currently asserts `stderr.contains("incompatible types")`. On another JDK, the text changes yet compilation still fails. Should the test fail?

*Suggested answer:* If the goal is testing Java validity, no. Update it to assert compilation failure and `Diagnostic.Kind.ERROR`, while ensuring the fixture is properly delivered to the compiler.

**Exercise 2.** Running `javac` returns a non-zero exit code because the source file is missing. Is this a passing negative compilation test?

*Suggested answer:* No. That is a setup/invocation error; the source was never evaluated against language rules. You must verify the fixture exists and check diagnostics for the intended test case.

**Exercise 3.** A `WARNING` diagnostic is emitted and the compiler returns success. What should you check?

*Suggested answer:* Check the test's policy. If warnings are allowed, the result is a pass; if the test guarantees zero warnings, inspect warnings directly or configure `-Werror`. Do not manually reclassify a warning as an error.

**Exercise 4.** A team-authored plugin emits a JDK-independent code `VALIDATION_DUPLICATE_NAME`. Should you assert that code?

*Suggested answer:* Yes, if it is a stable contract of the plugin. Distinguish project-owned domain codes from the compiler's implementation-dependent `Diagnostic.getCode()`.

**Exercise 5.** A test asserts `getLineNumber() == 1`; after adding a comment line at the top of the file, the test fails even though the error is still properly detected. How do you fix it?

*Suggested answer:* If the exact line position is not part of the goal, remove the line assertion or replace it with checking that the error belongs to the right source. If line position is the behavior under test, update the fixture and expectations deliberately, accounting for `Diagnostic.NOPOS`.

## 14. Implementation checklist

- [ ] Test clearly states pass/fail compilation behavior or warning policy.
- [ ] Compiler/JDK is located and launched properly; environment failures are not counted as expected source errors.
- [ ] Fixture source code is managed independently of the main source set.
- [ ] Primary assertion relies on compilation result/exit code.
- [ ] Error assertions use structured diagnostics when needed, not full message comparison by default.
- [ ] Diagnostic counts, line/column numbers, and `getCode()` are not locked down unless part of the contract.
- [ ] Stderr and messages are still logged for debugging when tests fail.
- [ ] Warnings, `-Werror`, annotation processors, and tool invocations are handled per separate goal.
- [ ] If formatter snapshots are genuinely needed, an explicit toolchain/locale baseline exists.
- [ ] Tests include both valid sources and intentionally invalid sources when bidirectional verification is required.

## Official documentation

- [Java SE 17 — `javax.tools` package](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/package-summary.html)
- [Java SE 17 — `JavaCompiler`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html)
- [Java SE 17 — `Diagnostic`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/Diagnostic.html)
- [Java SE 17 — `Diagnostic.Kind`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/Diagnostic.Kind.html)
- [Java SE 17 — `DiagnosticCollector`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/DiagnosticCollector.html)
- [JUnit 5 User Guide — Assertions](https://docs.junit.org/5.11.3/user-guide/index.html#writing-tests-assertions)

Overarching principle: when testing **compilation**, assert **status and meaningful diagnostic signals**. Message text serves humans and failure investigation; turn it into an assertion expectation only when text formatting itself is a product requirement.