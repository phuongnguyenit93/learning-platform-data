# Designing Must-Compile and Must-Reject Cases in Java

## 1. Learning objectives

A compile-time test verifies whether **the Java compiler accepts or rejects a piece of code according to language rules**. Both expectations carry equal weight:

- **Positive/acceptance case:** valid code must compile successfully. If the compiler rejects it, that is a bug in the test case, configuration, or compiler.
- **Negative/rejection case:** code intentionally violating a rule must be rejected by the compiler. If it compiles, the test case fails; if it is rejected for an entirely different error, that case must be investigated and should not be automatically treated as proving the rule under test.

After this lesson, learners can design a valid/invalid pair of cases for the same rule, run them with **javac** or the **JavaCompiler API**, inspect compilation results and error diagnostics, and organize test data to avoid depending on previously compiled classes.

**Scope limitation:** this tests *whether source code is accepted at compile time*. It is different from testing output, business logic, performance, or exceptions thrown when the program runs.

## 2. Contract of a compilation test case

For a test case to be repeatable and meaningful, clearly specify:

| Component | Question to Answer | Example |
| --- | --- | --- |
| Rule | Which language constraint is being tested? | Do not assign a String value to an int variable |
| Input source | What are the file/class and full source code? | InvalidType.java |
| Environment | Which JDK, language version, classpath/module path, options? | JDK 17+, --release 17, UTF-8 |
| Expectation | Accept or reject? | REJECT |
| Observable criteria | javac status, error count, output artifacts? | javac fails and has an ERROR diagnostic |
| Expected cause | Why must it be rejected? | Type incompatibility |
| Isolation | How to ensure no reuse of previously compiled code? | Fresh output directory for each case |

With the **javac** command, successful exit normally has code **0**; failure has a non-**0** exit code. In the **JavaCompiler API**, the compilation task's return value is **true** or **false**, and **DiagnosticCollector** allows distinguishing diagnostics of kind **ERROR**, **WARNING**, and others. A warning by itself does not mean compilation failure, unless a policy turning warnings into errors such as **-Werror** is explicitly enabled.

A good negative case does **not merely** assert “any error occurred”: you must ensure the base code is valid, the injected error is intentional, and inspect the diagnostic kind or review the message to be sure the error matches the intended cause. English/Vietnamese message strings, line numbers, and diagnostic ordering may differ across JDK versions, locales, and compilers.

## 3. Designing control pairs before writing automation

The simplest approach is to start from an example that must compile, then change **a single point** to create the example that must be rejected. For example:

**ValidAssignment.java — accept**

~~~java
public class ValidAssignment {
    int count = 5;
}
~~~

**InvalidAssignment.java — reject**

~~~java
public class InvalidAssignment {
    int count = "five";
}
~~~

The two snippets differ only in the assignment expression. The compiler must accept the integer **5**, yet cannot assign a **String** to an **int**. If multiple things are changed at once (class name, braces, imports, and types), when a negative case fails it will be hard to determine which error was the cause.

Run manually into two **separate** output directories (after saving each example into a file with the matching name):

~~~text
javac --release 17 -encoding UTF-8 -d out-valid ValidAssignment.java
javac --release 17 -encoding UTF-8 -d out-invalid InvalidAssignment.java
~~~

The first command must succeed; the second command must fail with a data type error. **Check the exit status** of each command immediately after running it. Do not draw conclusions merely from whether messages appear on screen; successful compilation typically prints nothing. There is no need to run **java ValidAssignment** because this example has no **main**: the goal is compilation, not execution.

The **-d** output must be a fresh directory or cleaned before each attempt. The presence of an old **.class** file does not prove the current compilation succeeded. Conversely, a failed compilation pass with multiple source files does not guarantee no **.class** files at all were emitted; do not treat “empty output directory” as a general rejection criterion.

## 4. Matrix of case categories to include

| ID | Scenario | Expectation | Key Observation Point |
| --- | --- | --- | --- |
| P01 | Valid Java class, properly typed method declarations | Accept | Compilation task succeeds, no ERROR |
| P02 | Using generics with valid type arguments | Accept | List<String> holds String values |
| N01 | Syntax error (missing expression after =) | Reject | Syntax parsing error |
| N02 | Assigning String to int | Reject | Type checking error |
| N03 | Accessing a private method from another class | Reject | Access control checking error |
| N04 | Calling a method declaring a checked exception without catching/declaring | Reject | Checked exception checking error |
| N05 | Assigning List<Integer> to List<String> | Reject | Generic type constraint error |

Depending on module goals, you can add cases for **non-existent symbol names**, overload ambiguity, variable scope limits, **sealed class** rules, or code invalid under the chosen **--release** level. Each branch needs a positive control and its own failure reason; there is no need to put all Java features into one case.

**Important note:** dividing by 0 with a runtime variable denominator, accessing an array element with an out-of-bounds index at runtime, or logic bugs returning wrong results are not automatically compile-time negative cases. In certain constant expressions, Java has specific compile-time rules; whichever rule you want to test, identify it precisely before writing expectations.

## 5. Runnable automated test suite for Java 17+

The following runner uses **javax.tools.JavaCompiler** from the JDK to compile source code strings directly. It does not place intentionally invalid code into **src/main/java** or **src/test/java**, which would be compiled by the build system before tests run.

Save the entire program below to **CompilationCases.java** using UTF-8 encoding. The program creates a **separate** temporary compilation directory for each case, constrains the language with **--release 17**, disables annotation processing because the lesson focuses on plain Java rules, counts **ERROR** diagnostics, and deletes the temporary directory after finishing.

~~~java
import java.io.IOException;
import java.net.URI;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.List;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.ToolProvider;

public class CompilationCases {
    record Case(String name, String className, String code, boolean shouldCompile) {}

    static final class Source extends SimpleJavaFileObject {
        private final String code;

        Source(String className, String code) {
            super(URI.create("string:///" + className + Kind.SOURCE.extension), Kind.SOURCE);
            this.code = code;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return code;
        }
    }

    public static void main(String[] args) throws IOException {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("Cần chạy bằng JDK 17+ (có javac).");
        }

        List<Case> cases = List.of(
            new Case("valid-basic", "ValidBasic", """
                public class ValidBasic {
                    public static int square(int x) { return x * x; }
                }
                """, true),
            new Case("valid-generic", "ValidGeneric", """
                import java.util.List;
                public class ValidGeneric {
                    List<String> names = List.of("A", "B");
                }
                """, true),
            new Case("invalid-syntax", "InvalidSyntax", """
                public class InvalidSyntax { int count = ; }
                """, false),
            new Case("invalid-type", "InvalidType", """
                public class InvalidType { int count = "five"; }
                """, false),
            new Case("invalid-access", "InvalidAccess", """
                class Vault { private static void close() {} }
                public class InvalidAccess { void run() { Vault.close(); } }
                """, false),
            new Case("invalid-checked-exception", "InvalidCheckedException", """
                import java.io.IOException;
                public class InvalidCheckedException {
                    static void risky() throws IOException {}
                    void run() { risky(); }
                }
                """, false),
            new Case("invalid-generic", "InvalidGeneric", """
                import java.util.List;
                public class InvalidGeneric {
                    List<String> names = List.of(1, 2);
                }
                """, false)
        );

        Path root = Files.createTempDirectory("compile-tests-");
        try {
            for (Case c : cases) {
                Path output = Files.createDirectory(root.resolve(c.name()));
                DiagnosticCollector<JavaFileObject> diagnostics = new DiagnosticCollector<>();
                try (var files = compiler.getStandardFileManager(diagnostics, null, null)) {
                    List<String> options = List.of(
                        "--release", "17", "-encoding", "UTF-8", "-proc:none",
                        "-classpath", output.toString(), "-d", output.toString()
                    );
                    boolean success = Boolean.TRUE.equals(compiler.getTask(
                        null, files, diagnostics, options, null,
                        List.of(new Source(c.className(), c.code()))
                    ).call());
                    long errorCount = diagnostics.getDiagnostics().stream()
                        .filter(d -> d.getKind() == Diagnostic.Kind.ERROR).count();
                    if (success != c.shouldCompile() || (!success && errorCount == 0)) {
                        throw new AssertionError(c.name() + ": unexpected result; errors=" + errorCount);
                    }
                    System.out.println(c.name() + ": PASS (" + (success ? "compiled" : "rejected") + ")");
                }
            }
        } finally {
            try (var paths = Files.walk(root)) {
                for (Path path : paths.sorted(Comparator.reverseOrder()).toList()) {
                    Files.deleteIfExists(path);
                }
            }
        }
    }
}
~~~

Run from the directory containing **CompilationCases.java**:

~~~text
javac -encoding UTF-8 CompilationCases.java
java CompilationCases
~~~

On JDK 17 or newer supporting **--release 17**, the expected output (verified on JDK 21) is:

~~~text
valid-basic: PASS (compiled)
valid-generic: PASS (compiled)
invalid-syntax: PASS (rejected)
invalid-type: PASS (rejected)
invalid-access: PASS (rejected)
invalid-checked-exception: PASS (rejected)
invalid-generic: PASS (rejected)
~~~

**Mechanism explanation:**

1. **Source** is a **SimpleJavaFileObject** representing a source file in memory; virtual paths like **string:///InvalidType.java** must match the **public** class name in the source.
2. **getTask(...).call()** executes exactly one compilation pass; each pass has its own file manager and output directory so it does not pick up results from another case.
3. **shouldCompile=true** requires the task to succeed. **shouldCompile=false** requires the task to fail **and** have at least one **Diagnostic.Kind.ERROR**; a fatal error throwing an exception fails the entire runner and is not treated as a valid rejection.
4. Four negative cases covering syntax, types, access control, and checked exceptions plus a generic case verify different constraints. The runner verifies the compilation result; to verify the exact *cause* of rejection, add diagnostic-group checking as shown in the next section.
5. The **finally** block cleans up all temporarily created files even when an assertion fails.

## 6. Diagnosing error causes and avoiding “false-pass” negative cases

A negative case can be rejected due to **a missing import**, **wrong file/class name**, **missing classpath**, **wrong source encoding**, or **other broken syntax before the compiler reaches the rule under test**. In that situation, the test appears to PASS on the surface yet fails to prove what needed to be proven.

For high-confidence testing:

1. **Keep a valid version as a control.** For example, change only the declaration **int count = 5;** to **int count = "five";**; keep every other element unchanged.
2. **Confirm the diagnostic is an ERROR,** not just a warning or note. With **DiagnosticCollector**, retrieve **Diagnostic.getKind()**, **getCode()**, **getSource()**, **getLineNumber()**, and **getMessage(locale)** for investigation.
3. **Match causes at an appropriate level.** You can classify by **javac** diagnostic code if the compiler version is pinned; this is a compiler implementation detail, not a stable diagnostic API across all JDKs/vendors. For tests running across multiple JDKs, prefer checking error category/semantic expectations and reviewing messages rather than matching full English wording, line/column numbers, or error order verbatim.
4. **Distinguish “source rejected” from “broken test infrastructure”.** Do not treat **compiler==null**, I/O exceptions, invalid options, directory creation failures, or killed processes as a negative pass. Those situations must report an infrastructure failure.
5. **Cross-check against the target release.** Source valid on JDK 21 may be invalid when using **--release 17** if it uses syntax/APIs introduced after Java 17; that is a target-compatibility rejection and must be explicitly documented in the case rather than called an unexpected syntax error.

Example pattern to inspect the diagnostic *group*, added inside the runner's loop (the snippet below is an excerpt, not a standalone Java program):

~~~java
var errors = diagnostics.getDiagnostics().stream()
    .filter(d -> d.getKind() == Diagnostic.Kind.ERROR)
    .toList();

for (var error : errors) {
    System.err.println(c.name() + ": " + error.getCode()
        + " at line " + error.getLineNumber()
        + " — " + error.getMessage(java.util.Locale.ROOT));
}
~~~

This snippet **prints** evidence for analysis, and does not by itself prove the diagnostic matches the rule. If requiring automated verification of diagnostic codes, declare the accepted codes **per tested javac version**, and create a control case capable of making the diagnostic-code check fail. Avoid testing an unspecific message substring such as “error” because it does not distinguish causes.

## 7. Organizing test datasets and regression testing

When turning the example above into a larger test suite, manage each case via a manifest/metadata with **ID**, source file, rule, **ACCEPT/REJECT**, Java version, compiler options, diagnostic expectations, and a control case. Java files that are *intentionally invalid* should be stored under **resources/compile-fixtures**, outside any source set that Gradle/Maven compiles automatically. The test harness reads them as data, then explicitly invokes the compiler.

A practical regression workflow:

1. **Lock environment configuration:** record the actual JDK vendor/version running; set **--release** to specify the target language and API level, **-encoding UTF-8**, required classpath/module path, and enable annotation processors only if that is what is being tested.
2. **Design the positive control case first:** verify the baseline code is accepted with those exact options; do not build a negative case by editing a program that already has errors.
3. **Introduce one intentional deviation:** specify the violated semantics and expected diagnostic kind. If the problem requires multiple rules at once, split them into multiple cases.
4. **Run in isolation:** each case has minimal sources, declared dependencies, a clean output directory, and a suitable timeout if running the compiler in an external process.
5. **Evaluate both directions:** positive cases must succeed, negative cases must fail for the right cause; ambiguous results or infrastructure errors must be reported separately without swallowing exceptions.
6. **Retain useful evidence:** case ID, compiler version, options, status, diagnostic kind/code, and related source; when changing JDKs, review diagnostics before updating expectations.
7. **Self-test the validity of the harness:** intentionally turn a negative case into valid code; the test suite **must fail**. Turn a positive case into invalid code; the test suite **must also fail**. This checks whether the oracle truly detects wrong results.

Do not hard-code full **javac** logs as strict “snapshots” unnecessarily: temporary file paths, line numbers, localized text, and diagnostic phrasing easily change while Java rules remain the same.

## 8. Common design mistakes and how to fix them

| Mistake | Consequence | How to Fix |
| --- | --- | --- |
| Testing only valid cases | Fails to detect compiler/policy allowing forbidden code | Add negative pairs with minimal differences |
| Negative case broken by multiple unrelated errors | Test “passes” for the wrong target | Start from a valid version, change one element, check ERROR category |
| Using **java** execution results to judge compilation tests | Mixes runtime errors with compile-time checks | Determine pass/fail at the compiler step |
| Putting invalid fixtures under the default source set | Entire project fails to compile, tests never run | Store fixtures as data and load via the harness |
| Uncontrolled reuse of output/classpath | Easily picks up stale files or external dependencies | Fresh output directory, explicitly declared classpath |
| Treating any non-zero exit code as a “valid rejection” | Compiler crash, I/O error, or bad options count as passes | Separate infrastructure errors and verify source ERRORs |
| Matching error messages verbatim | Fragile tests across JDKs/locales | Use diagnostic kind, compiler-pinned codes, or semantic classification |
| Forgetting filename must match the **public** class | Rejected due to wrong name instead of target rule | Check fixture path and class name first |
| Expecting all negative cases to emit zero **.class** files | Reports false results on multi-source compilation | Evaluate compilation status and diagnostics; always use clean output |

## 9. Practice exercise and completion criteria

**Exercise:** add two pairs of cases to the test suite:

- **Non-existent name:** starting from a declaration using a valid class, change only the type name to an undefined name. The positive case must be accepted; the negative case must fail with the corresponding symbol-not-found error.
- **Checked exception:** starting from a method calling **risky() throws IOException** with **throws IOException** or a proper **try/catch**, remove only the exception handling/declaration part. The positive case is accepted; the negative case is rejected because the exception is unhandled/undeclared.

**Result is accepted when:** (1) each case explicitly states ACCEPT or REJECT and its cause; (2) all positive cases compile successfully; (3) all negative cases are rejected by the expected rule with an ERROR diagnostic; (4) flipping expectations or turning a negative case into valid code causes the harness to fail; (5) rerunning from a clean output directory yields the same results; (6) everything is executed with the explicitly declared Java level.

A good compilation test suite proves the **boundary** of a rule: the closest still-valid example **is accepted**, and an example just crossing that boundary **is rejected for the right reason**.