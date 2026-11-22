# Testing Dominance with Compile Failure in Java Pattern Matching

**Dominance** in a pattern `switch` is a relationship between `case` branches: if an earlier branch already covers every case that a later branch can match, the later branch is **dominated**. For cases specified by Java, the compiler **refuses to compile** rather than leaving a redundant branch silently sitting in the program. We can turn this property into an intentional test: **give the compiler a deliberately invalid snippet and assert that it must be rejected for the exact dominance reason**. That is a **negative compilation test** or **compile-failure test**.

This lesson belongs to **Java Core Pattern Matching → Testing**, focusing on how to write negative tests for *dominated case labels*, re-verifying when refactoring `case` ordering or `when` guards, using `javac` and the Java Compiler API to automate tests, and distinguishing dominance errors from other kinds of compilation errors.

**Version requirements:** Uses syntax finalized since **Java 21**: pattern matching for `switch` (JEP 441) and record patterns (JEP 440). The examples run on JDK 21+ with `--release 21`, without needing `--enable-preview`.

## 1. What Is Dominance and Why Test It?

Consider a `switch expression` over a variable of type `Object`:

~~~java
// INTENTIONALLY INVALID — excerpt inside a method, input has type Object.
String result = switch (input) {
    case CharSequence text -> "Any CharSequence";
    case String text -> "A String";
    case null -> "Null";
    default -> "Other";
};
~~~

`String` implements `CharSequence`. Therefore, every `String` already matches the preceding `case CharSequence text`; the `case String text` branch has no chance of being selected. The compiler may report a message such as **"this case label is dominated by a preceding case label"** (exact wording varies by JDK).

Fixing the order:

~~~java
// VALID in Java 21+.
String result = switch (input) {
    case String text -> "A String";
    case CharSequence text -> "Any CharSequence";
    case null -> "Null";
    default -> "Other";
};
~~~

The **more specific branch comes first, the more general branch comes later**. Values of type `String` enter the first branch; other `CharSequence` types go to the second branch.

Dominance is not merely a code style warning. In cases specified by the language, it is a **compile-time error**. If you accidentally change the case order during refactoring, the compiler helps prevent unreachable branches. Compile-failure tests help *capture* important invalid examples as part of the project's documentation and language test suite.

### Distinguishing Three Types of Checks

| Check Type | Question | Expected Result |
| --- | --- | --- |
| **Compile-success test** | Does a valid pattern compile? | The compiler accepts it |
| **Compile-failure test** | Is an invalid pattern rejected by the compiler for the right reason? | The compiler returns a failure status with an appropriate diagnostic |
| **Runtime behavior test** | Does the compiled pattern classify values correctly? | Run the code and verify output/exceptions |

You should not consider a "compile fail" test sufficient just because it happens to fail somewhere else. If a snippet has a misspelled class name and fails to compile, that **does not prove** the compiler detected dominance. Negative tests need to verify the **reason for rejection**.

## 2. Testing Dominance Between Supertype and Subtype

This is the most basic and easiest-to-explain example for those new to pattern matching:

~~~java
// File: DominanceCase.java
// INTENTIONALLY INVALID: this program must be rejected by the compiler.
public class DominanceCase {
    static String classify(Object input) {
        return switch (input) {
            case CharSequence text -> "text-like";
            case String text -> "string";
            case null -> "null";
            default -> "other";
        };
    }
}
~~~

Run with JDK 21+:

~~~bash
javac --release 21 DominanceCase.java
~~~

**Expected result:** `javac` returns a **non-zero exit code**, with a dominance error at the `case String text` branch; **no valid build is produced** for this example. Depending on the version and configuration, the displayed message may differ. You should not hard-code the entire verbatim English error message if you do not control the compiler version.

Because `String` is a subtype of `CharSequence`, the second branch is shadowed. This issue is **different** from reusing the pattern variable name `text`: the name can be declared separately in different cases; the error lies in the **type coverage relationship**.

### An `Object` Case Can Also Be Too Broad

~~~java
// INTENTIONALLY INVALID, excerpt.
String kind = switch (input) {
    case Object any -> "some object";
    case Integer n -> "integer"; // The Integer branch is dominated.
};
~~~

With a selector of type `Object`, the general pattern `Object any` covers every non-null `Integer`. Do not put a broad type pattern first and expect subsequent subtypes to be selected. For `null`, specific rules apply; a type pattern does not replace arbitrary null handling.

**Testing tip:** choose a pair with a clear subtype relationship, such as `CharSequence`/`String`, so that the negative test checks only one rule. Do not simultaneously introduce missing variables, wrong return types, or lack of exhaustiveness, as those can mask the reason the test needs to verify.

## 3. Testing Dominance Between Guarded and Unguarded Cases

With `when`, a pattern can be augmented with a Boolean condition. A preceding **unguarded** case generally covers a guarded case with the same pattern:

~~~java
// INTENTIONALLY INVALID — input is Object.
String label = switch (input) {
    case String value -> "some string";
    case String value when value.isBlank() -> "blank";
    case null -> "null";
    default -> "other";
};
~~~

Every blank `String` is still a `String`; the first branch already accepts all `String` values. The trailing branch with `when` is dominated, and the example must **fail to compile**.

Fix by placing the special case first:

~~~java
// VALID in Java 21+.
String label = switch (input) {
    case String value when value.isBlank() -> "blank";
    case String value -> "some string";
    case null -> "null";
    default -> "other";
};
~~~

This reads equivalently to:

~~~java
// Equivalent excerpt in terms of type/blank checking logic, input is Object.
if (input instanceof String value && value.isBlank()) {
    return "blank";
}
if (input instanceof String value) {
    return "some string";
}
if (input == null) {
    return "null";
}
return "other";
~~~

The `if` snippet above is only an illustration inside a **method returning `String`**. In `switch`, the compiler checks the relationship between case patterns; here you do not need to manually prove whether the second branch can execute.

### A Guard Returning `false` Is Not Dominance

If `value` is the string `"Java"`, the guard `value.isBlank()` is false, so the first case is not selected. Java continues to `case String value` and returns `"some string"`. This is a valid execution path. Dominance only occurs if **a preceding branch completely covers a following branch** according to the applicable language rules.

## 4. Testing Dominance with Record Patterns

Record patterns allow deconstructing the components of a record. When a case matches all values of a record, a specialized guarded branch for the same record placed after it is also dominated:

~~~java
// INTENTIONALLY INVALID — declarations are within a valid class/scope.
record Point(int x, int y) {}

String label = switch (input) {
    case Point(var x, var y) -> "any point";
    case Point(var x, var y) when x == 0 -> "on vertical axis";
    case null -> "null";
    default -> "other";
};
~~~

For type `Point`, both `int` components match the corresponding `var`; the first branch is a catch-all branch for all `Point` instances. The `when x == 0` branch can never be selected. This is a dominance test worth having in a module teaching **record patterns + switch**.

Fix:

~~~java
// VALID; input is Object, Point is already declared.
String label = switch (input) {
    case Point(var x, var y) when x == 0 -> "on vertical axis";
    case Point(var x, var y) -> "other point";
    case null -> "null";
    default -> "other";
};
~~~

**Caution when extending the example:** a record pattern with reference-type components may have different `null`-matching rules than `var`. When testing dominance between complex record patterns, separate tests for types/components so you do not confuse a dominance error with an invalid record shape or type constraint.

## 5. The Compiler Does Not Prove Every Logical Relationship Between Guards

A common misconception is: "If a guard has a broader condition than a later guard, the compiler will definitely detect dominance." This is **not true in general** for arbitrary Boolean expressions.

For example:

~~~java
// Java 21+: excerpt VALID AT COMPILE TIME.
String bucket = switch (input) {
    case String s when s.length() > 3 -> "more than 3";
    case String s when s.length() > 5 -> "more than 5";
    case String s -> "short";
    case null -> "null";
    default -> "other";
};
~~~

Mathematically, `s.length() > 5` implies `s.length() > 3`. For a string of length 6, the first branch already returns `"more than 3"`, so the second branch is never chosen. However, the Java compiler **does not solve arbitrary logical implications between guards**; the snippet above can still **compile successfully** even though in business logic, the `"more than 5"` branch will never receive a matching string.

To classify as intended, reverse the order:

~~~java
String bucket = switch (input) {
    case String s when s.length() > 5 -> "more than 5";
    case String s when s.length() > 3 -> "more than 3";
    case String s -> "short";
    case null -> "null";
    default -> "other";
};
~~~

**Testing takeaway:** A compile-failure test should only expect an error when Java **specifies that the compiler must report a dominance error**. Guards with complex business relationships, overlapping conditions, or mutual implications require **runtime tests, boundary tests**, and logic reviews; the compiler does not replace those tools.

## 6. How to Test Manually with `javac`

Minimal workflow to verify a negative example:

1. Create a source file **containing only one intentional dominance error**, such as `DominanceCase.java` in section 2.
2. Use the exact `javac` binary and `--release 21` flag.
3. Run compilation and observe a **failure exit code**; do not call this failure a "red test" if it is a negative test expecting an error.
4. Verify that the diagnostic mentions a dominated case (or the appropriate diagnostic code of the compiler in use), rather than a syntax error or missing class error.
5. Reorder the cases to create a **positive control**, recompile, and confirm success.

On a POSIX shell (Bash, zsh), you can use:

~~~bash
javac --release 21 DominanceCase.java
status=$?
if [ "$status" -eq 0 ]; then
  echo "FAIL: expected javac to reject the source"
  exit 1
fi
echo "javac rejected the source; inspect diagnostics for dominance"
~~~

The shell snippet above only checks `exit code`; the last line intentionally reminds you to **inspect the error reason**. This is an illustrative example, not a complete test suite.

On PowerShell:

~~~powershell
javac --release 21 DominanceCase.java
if ($LASTEXITCODE -eq 0) {
    throw "FAIL: expected compilation to be rejected"
}
Write-Output "javac rejected the source; check dominance diagnostics"
~~~

Similarly, `$LASTEXITCODE` only indicates compilation failed, not that it was dominance. To automate checks and avoid depending on temporary file paths, you can use the **Java Compiler API (`javax.tools`)**.

### Do Not Break the Main Build with Intentionally Invalid Examples

A `DominanceCase.java` file that intentionally contains an error must **not** be placed in the application's main compiled source set. Otherwise, the build always fails and CI cannot distinguish an expected negative test from a real error. Place negative examples in separate test resources and use a test harness that explicitly specifies **which compiler** must run on each snippet.

## 7. Automating Negative Tests with the Java Compiler API (Without Creating Source Files)

Java provides `ToolProvider.getSystemJavaCompiler()` and `DiagnosticCollector` to invoke the compiler from Java code. You can write a harness that takes a source string, compiles it in memory, and inspects the result:

- For a **negative case**: `compiled == false` and there is a dominance diagnostic.
- For a **positive control**: `compiled == true`.
- For another case with an intentional syntax error: `compiled == false` alone is **not enough** to claim the dominance test passed.

The complete example below uses the Java Compiler API, `SimpleJavaFileObject`, and a `ForwardingJavaFileManager` that keeps both **input and output in memory**. As a result, positive snippets can be compiled without creating `Sample.class` in the project directory.

### Automated Program: `DominanceCompileTest.java`

~~~java
public class DominanceCompileTest {
    private record Outcome(boolean compiled, boolean dominated, String errors) {}

    private static Outcome compile(String source) {
        javax.tools.JavaCompiler compiler = javax.tools.ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("A full JDK is required");
        }

        var diagnostics = new javax.tools.DiagnosticCollector<
                javax.tools.JavaFileObject>();

        var file = new javax.tools.SimpleJavaFileObject(
                java.net.URI.create("string:///Sample.java"),
                javax.tools.JavaFileObject.Kind.SOURCE) {
            @Override
            public CharSequence getCharContent(boolean ignoreEncodingErrors) {
                return source;
            }
        };

        try (var standard = compiler.getStandardFileManager(
                diagnostics, java.util.Locale.ROOT,
                java.nio.charset.StandardCharsets.UTF_8)) {
            var memory = new javax.tools.ForwardingJavaFileManager<
                    javax.tools.StandardJavaFileManager>(standard) {
                @Override
                public javax.tools.JavaFileObject getJavaFileForOutput(
                        Location location, String className,
                        javax.tools.JavaFileObject.Kind kind,
                        javax.tools.FileObject sibling) {
                    return new javax.tools.SimpleJavaFileObject(
                            java.net.URI.create("mem:///"
                                    + className.replace('.', '/') + kind.extension),
                            kind) {
                        @Override
                        public java.io.OutputStream openOutputStream() {
                            return new java.io.ByteArrayOutputStream();
                        }
                    };
                }
            };

            boolean compiled = Boolean.TRUE.equals(compiler.getTask(
                    null, memory, diagnostics,
                    java.util.List.of("--release", "21", "-proc:none"),
                    null, java.util.List.of(file)).call());

            boolean dominated = diagnostics.getDiagnostics().stream()
                    .anyMatch(d ->
                            d.getKind() == javax.tools.Diagnostic.Kind.ERROR
                            && d.getCode().contains("dominated"));

            String errors = diagnostics.getDiagnostics().stream()
                    .filter(d -> d.getKind() == javax.tools.Diagnostic.Kind.ERROR)
                    .map(d -> d.getCode()).distinct()
                    .reduce((a, b) -> a + "," + b).orElse("none");

            return new Outcome(compiled, dominated, errors);
        } catch (java.io.IOException e) {
            throw new java.io.UncheckedIOException(e);
        }
    }

    static void mustBeDominated(String name, String source) {
        Outcome out = compile(source);
        if (out.compiled() || !out.dominated()) {
            throw new AssertionError(
                    name + ": expected dominance, found " + out);
        }
        System.out.println(name + ": rejected for dominance");
    }

    static void mustCompile(String name, String source) {
        Outcome out = compile(source);
        if (!out.compiled()) {
            throw new AssertionError(
                    name + ": expected success, found " + out);
        }
        System.out.println(name + ": compiled");
    }

    public static void main(String[] args) {
        mustBeDominated("type hierarchy", """
                public class Sample {
                    static String classify(Object input) {
                        return switch (input) {
                            case CharSequence cs -> "char sequence";
                            case String s -> "string";
                            case null -> "null";
                            default -> "other";
                        };
                    }
                }
                """);

        mustBeDominated("guard order", """
                public class Sample {
                    static String classify(Object input) {
                        return switch (input) {
                            case String s -> "any string";
                            case String s when s.isBlank() -> "blank";
                            case null -> "null";
                            default -> "other";
                        };
                    }
                }
                """);

        mustBeDominated("record pattern", """
                public class Sample {
                    record Point(int x, int y) {}
                    static String classify(Object input) {
                        return switch (input) {
                            case Point(var x, var y) -> "point";
                            case Point(var x, var y) when x == 0 -> "x zero";
                            case null -> "null";
                            default -> "other";
                        };
                    }
                }
                """);

        mustCompile("valid specificity", """
                public class Sample {
                    static String classify(Object input) {
                        return switch (input) {
                            case String s when s.isBlank() -> "blank";
                            case String s -> "string";
                            case CharSequence cs -> "other text";
                            case null -> "null";
                            default -> "other";
                        };
                    }
                }
                """);

        mustCompile("overlapping guards", """
                public class Sample {
                    static String classify(Object input) {
                        return switch (input) {
                            case String s when s.length() > 3 -> "length > 3";
                            case String s when s.length() > 5 -> "length > 5";
                            case String s -> "short";
                            case null -> "null";
                            default -> "other";
                        };
                    }
                }
                """);
    }
}
~~~

Compile and run the harness with **JDK 21+**, without JUnit:

~~~bash
javac --release 21 -encoding UTF-8 DominanceCompileTest.java
java DominanceCompileTest
~~~

Expected output:

~~~text
type hierarchy: rejected for dominance
guard order: rejected for dominance
record pattern: rejected for dominance
valid specificity: compiled
overlapping guards: compiled
~~~

**Note:** the two lines `overlapping guards: compiled` and `valid specificity: compiled` only indicate that the compiler accepts the source snippets; they **do not verify correct runtime classification logic**. The overlapping guards case is intentionally kept to demonstrate the limits of compile-time dominance checking.

### Step-by-Step Explanation of the Harness

**Step 1 — Represent source as strings.** Java text blocks `""" ... """` contain a `Sample` class for each test. Each compiler invocation receives **an independent string**, so the same class name `Sample` can be reused without conflicts between tests.

**Step 2 — Use the current JDK's compiler.** `ToolProvider.getSystemJavaCompiler()` is only available when the environment provides a compiler, typically a full JDK. `--release 21` requests compilation against the language version and APIs supported for Java 21. You must run the harness with a JDK 21+ that supports the corresponding release.

**Step 3 — Collect diagnostics.** `DiagnosticCollector` captures diagnostics without needing to parse text printed to the console. On the `javac` versions tested in this lesson, the dominance diagnostic code contains the substring `dominated`.

**Step 4 — Avoid writing test class files to disk.** `ForwardingJavaFileManager` returns a `JavaFileObject` whose `OutputStream` writes to a `ByteArrayOutputStream`. This is a minimal way to check compilability without creating output artifacts on the filesystem.

**Step 5 — Assert outcomes.** `mustBeDominated` requires both **compilation failure** and a diagnostic carrying a dominance code. `mustCompile` requires the compiler to accept the source. If the condition is not met, an `AssertionError` is thrown so the test run fails.

### Limitations and How to Make a Real Test Suite More Robust

- **Diagnostic codes are not a stable API contract of the Java Language Specification.** `getCode().contains("dominated")` is suitable for illustration with the tested `javac`, but when upgrading the JDK or switching compilers, you must verify the new diagnostic codes. A production test suite can define a set of accepted codes per JDK version supported by CI.
- **A single source snippet can have multiple errors simultaneously.** The illustrative harness looks for at least one dominance error. If you want stricter checks, verify all diagnostics match the expected kind, constrain the error location, or ensure the source contains no secondary errors via positive controls and fixture reviews.
- **Positive controls are important.** They help detect situations where every compilation fails due to configuration, classpath, release options, or common source errors. Without a positive control, a naive `!compiled` negative test can easily produce false positives.
- **Do not use preview features unintentionally.** This lesson uses `--release 21` and finalized Java 21 syntax. For preview features in other JDKs, configure preview separately and state the test target explicitly; do not mix them into the stable Java 21 test suite.
- **Do not execute bytecode from invalid fixtures.** Negative tests only need the compiler to reject the source; positive tests check compilation. If you also want to verify runtime behavior, use dedicated tests on valid source code.

## 8. Testing Strategy for Projects and CI

A Java module that heavily uses pattern switches should combine these layers:

| Layer | Example | Verification |
| --- | --- | --- |
| Compile-failure test | `CharSequence` before `String` | Rejected due to dominance |
| Compile-failure test | `case String s` before `case String s when ...` | Rejected due to dominance |
| Compile-failure test | General record pattern before guarded pattern for the same record | Rejected due to dominance |
| Compile-success test | Narrow → broad ordering | Compiles successfully |
| Compile-success test | Two guards with overlapping conditions not proven by the compiler | Compiles successfully, reminding that no compile error does not mean correct business logic |
| Runtime test | `"   "`, `"hello"`, numbers, `null` | Selects the right branch |
| Runtime test | Thresholds `length == 3, 4, 5, 6` | Guard branches behave per specification |
| Refactoring regression test | Reordering cases or adding new types | Does not accidentally shadow branches or alter behavior |

Implementation steps:

1. **Pin the JDK version in CI**; use a consistent toolchain and `--release` option.
2. **Keep rejected source fixtures in a separate location**; do not place them in `src/main/java` or the main module's automatically compiled source set.
3. **Name tests after the failure reason**: `rejectBroadTypeBeforeSubtype`, `rejectUnguardedBeforeGuarded`, `rejectBroadRecordPatternBeforeGuarded`.
4. **Each fixture contains one intentional failure cause** so diagnostics are easy to assert.
5. **Pair negative/positive tests**: invalid code must be rejected, fixed code must compile. If a negative test unexpectedly succeeds after a JDK upgrade, check the JLS rules and that compiler version's behavior before changing expectations.
6. **Include runtime tests** for Boolean conditions that the compiler cannot fully reason about.

You do not need to cram all these tests into a single class. For larger projects, you can use JUnit calling the Java Compiler API or a suitable compile-testing library; the standalone harness in section 7 makes the mechanism clear without depending on external frameworks beyond the JDK.

## 9. Distinguishing Dominance from Exhaustiveness and Other Errors

### Dominance: a later branch is shadowed by an earlier one

~~~java
// INTENTIONALLY INVALID.
case CharSequence cs -> "text";
case String s -> "string";
~~~

The compiler checks the ordering/coverage relationship of case patterns. **Fix:** move the `String` branch earlier.

### Exhaustiveness: unhandled values remain

~~~java
// INTENTIONALLY INVALID: Object can hold many other types.
String label = switch (input) {
    case String s -> "string";
    case null -> "null";
    // No branch for Integer, Boolean, ...
};
~~~

For a `switch expression` over `Object`, the code is missing branches covering other types; this is a **non-exhaustive** error, not dominance. **Fix:** add `default` or a type pattern covering the remainder, depending on design. Do not confuse error types when recording test outcomes.

### Type incompatibility: a branch returns the wrong type

~~~java
// INTENTIONALLY INVALID in a context requiring int.
int n = switch (input) {
    case String s -> "not an integer";
    case null -> 0;
    default -> 1;
};
~~~

A branch returning `String` in an `int` context causes a type error. If a negative test expecting dominance only detects this error, the test has missed its target.

### Pattern variable scope

~~~java
// INTENTIONALLY INVALID: text may not be bound.
if (input instanceof String text) {
    System.out.println(text);
}
System.out.println(text);
~~~

Variable scoping errors are a different pattern matching rule; they should also be tested separately if relevant to the module, rather than combined into a dominance fixture.

**Result naming:** `REJECTED_FOR_DOMINANCE`, `REJECTED_NOT_EXHAUSTIVE`, `REJECTED_FOR_TYPE_ERROR` are clearer than a generic Boolean `shouldNotCompile`.

## 10. Quality Checklist for Compile-Failure Tests

Before adding tests to CI, check:

- Is the fixture **valid Java syntax aside from the dominance error** you intentionally introduced?
- Are the JDK, `--release`, and whether preview is needed explicitly specified?
- Is there a paired **positive control** to catch environment errors and general source errors?
- Does the assertion distinguish a **dominance error** from "any compilation error"?
- Is each test small in scope, clearly named, and independent of other tests?
- Do record patterns have the expected component count/types and null semantics?
- Are diagnostics captured from the compiler with a note about diagnostic code changes across JDKs?
- Are there runtime tests for guards whose logical relationships the compiler cannot infer?
- Are intentionally invalid fixtures prevented from leaking into the production build?
- After reordering cases or adding subtypes, were all negative, positive, and behavioral tests recompiled and rerun?

## 11. Practice Exercises with Answers

### Exercise 1 — Recognizing type-based dominance

Given `Object input`, is the following snippet valid?

~~~java
String result = switch (input) {
    case Number n -> "number";
    case Integer i -> "integer";
    case null -> "null";
    default -> "other";
};
~~~

**Answer:** No. `Integer` is a subtype of `Number`, so `case Number n` covers all `Integer` values that the later case wants to match. Move `Integer` before `Number`.

### Exercise 2 — Placing specific guards first

Given:

~~~java
// INTENTIONALLY INVALID.
String category = switch (input) {
    case String s -> "string";
    case String s when s.length() == 0 -> "empty";
    case null -> "null";
    default -> "other";
};
~~~

**Answer:** `case String s when s.length() == 0` is dominated by the preceding `case String s`. Fix by placing the guarded case before the unguarded `String` case. You can also use `s.isEmpty()` instead of `s.length() == 0` if it fits the requirements.

### Exercise 3 — Record pattern

Given `record Box(int size) {}` and selector `Object input`:

~~~java
String result = switch (input) {
    case Box(var size) -> "box";
    case Box(var size) when size > 10 -> "big";
    case null -> "null";
    default -> "other";
};
~~~

**Answer:** The first `Box(var size)` branch covers all non-null `Box` instances, so the guarded branch after it is dominated. Place `case Box(var size) when size > 10` first.

### Exercise 4 — Does the compiler detect overlapping conditions?

Given:

~~~java
String result = switch (input) {
    case Integer n when n > 10 -> "above 10";
    case Integer n when n > 20 -> "above 20";
    case Integer n -> "other integer";
    case null -> "null";
    default -> "other";
};
~~~

**Answer:** You should not expect the compiler to prove every arithmetic relationship between two guards to report dominance. A pattern like this can compile, but the number `25` is matched first by `n > 10` and never reaches the `n > 20` branch. You need to put `n > 20` before `n > 10` and write runtime tests for boundary values like `10`, `11`, `20`, `21`.

### Exercise 5 — Which negative test is unreliable?

A test only writes:

~~~java
boolean success = compiler.getTask(/* ... */).call();
if (success) {
    throw new AssertionError("Should fail");
}
~~~

**Answer:** This test can "PASS" due to any error: a missing import, a mismatched public class name/filename, a non-exhaustive `switch`, or a completely unrelated syntax error. Add an assertion for the dominance diagnostic and a positive control, while keeping the fixture as small as possible.

## 12. Key Takeaways and Official References

- **Dominance** is a coverage relationship between case patterns according to rules specified by Java; a shadowed branch can become a **compilation error**.
- A **compile-failure test** intentionally supplies invalid source code and expects the compiler to reject it **for the right reason**, not merely reject it.
- Three useful negative cases: **supertype before subtype**, **unguarded pattern before specialized guard**, **general record pattern before guarded record pattern**.
- Include a **positive control** to distinguish dominance errors from configuration/syntax errors; do not put intentionally invalid fixtures into the main source build.
- **The compiler does not solve all relationships between arbitrary guards**. Overlapping conditions and business priorities still require runtime testing.
- With `javax.tools.JavaCompiler`, you can automatically compile source from strings and inspect diagnostics without creating temporary files for each negative test.
- Maintain the test suite per compiler version and do not depend strictly on diagnostic wording or codes that are not stably specified.

**References:** [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441); [JEP 440 — Record Patterns](https://openjdk.org/jeps/440); [Java Language Specification SE 21 — `switch` labels, pattern dominance](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1); [Java 21 — JavaCompiler API](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/JavaCompiler.html); [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
