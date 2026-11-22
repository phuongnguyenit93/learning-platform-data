# Writing Code Samples That Must Compile and Code Samples That Must Be Rejected — Testing Java Generics Contracts

## 1. Objectives

A good generic API not only runs correctly with valid input, but also **prevents callers from writing ill-typed calls at compile time**. Therefore, when testing generics, you need to build **two paired control groups of code samples**:

- **Positive compilation test:** Code that follows the contract must be accepted by `javac`; if there is a `main` method or assertions, run it as well to verify the actual result.
- **Negative compilation test:** Code that intentionally violates a generic rule must be **rejected** by `javac`. This is not a test that throws an exception at runtime: invalid source code does not become a valid program.
- **Warning/policy test:** Some raw/unchecked operations only emit a **warning** and still compile when `-Werror` is not enabled. These must be separated from rules prohibited by the language.
- **Runtime test:** Issues such as validating data from a legacy API, `Class.cast`, or heap pollution may only surface at runtime; separate tests must be written for them.

This lesson belongs to **Java Core – Generics / Testing and Diagnostics**. The complete programs below have been verified with **Java 17**, `javac --release 17 -Xlint:all -Werror`, and `java`. The harness using `javax.tools.JavaCompiler` confirmed **2 accepted samples and 6 rejected samples**; the raw type examples were also checked separately with and without `-Werror`.

After completing this lesson, you will know how to choose the right test type; create pairs of code that must compile / must not compile for invariance, wildcards, bounds, generic arrays, erasure, and type variables; check exit codes/diagnostics; automate with the Compiler API; and avoid false positives in CI.

## 2. Four Types of Outcomes to Distinguish

| Example | Compilation Result | At Runtime | Test Type |
| --- | --- | --- | --- |
| `List<String>` adding a string | Succeeds | Normal | Positive compilation + runtime |
| `List<String>` assigned to `List<Object>` | **Compilation error** | Does not run | Negative compilation |
| Adding a string through `List<?>` | **Compilation error** | Does not run | Negative compilation |
| `new List<String>[2]` | **Compilation error** | Does not run | Negative compilation |
| Raw `List` then `raw.add(42)` | May succeed **with warnings** | May cause heap pollution | Warning + runtime |
| Raw `List` with `-Werror` enabled | Build fails **due to warnings** | Does not run new build binary | Policy test |
| `String.class.cast(42)` | Succeeds | `ClassCastException` | Runtime rejection |
| Adapter accepting `List<?>` and checking elements | Succeeds | May report business validation error | Runtime validation |

**Do not mix terminology:** `javac` rejecting code due to type-checking is different from Java code being accepted and then throwing `ClassCastException` at runtime. Furthermore, `-Werror` is a **build policy**, not something that turns raw types into strictly forbidden syntax.

## 3. PASS/FAIL Criteria for a Compilation Test

**Code that is allowed to compile** must satisfy:

1. Correct file/class name, imports, classpath, target Java version, and required dependencies.
2. `javac` returns **exit code 0**.
3. If the project requires zero warnings, compile with `-Xlint:all -Werror` and still succeed.
4. For a runnable program, `java` returns 0 and the output/assertions match expectations.
5. Does not rely on leftover class files from a previous compilation.

**Code that must be rejected** must satisfy:

1. A fixture intentionally contains only **one core generic error** (or a clearly described set of errors).
2. Even when the correct imports, classpath, and Java baseline are provided, `javac` returns a **non-zero exit code**.
3. Diagnostics at level **ERROR** are present.
4. The error is related to the **intended generic rule under test**, not a filename error, package error, or missing dependency.
5. Do not attempt to run the fixture after compilation fails.

With the JavaCompiler API, `task.call()` returns `true` when compilation succeeds and `false` when it fails. A negative test should also verify `Diagnostic.Kind.ERROR`, rather than only searching for the string "error" in the console.

## 4. Pair 1 — Invariance of Generic Containers

**Must be accepted:**

```java
import java.util.List;

class ValidWildcard {
    static Object first(List<?> items) {
        return items.get(0);
    }

    static void run() {
        List<String> words = List.of("Java");
        List<?> values = words;
        Object item = first(values);
    }
}
```

**Must be rejected:**

```java
import java.util.List;

class InvalidInvariant {
    void run() {
        List<String> words = List.of("Java");
        List<Object> objects = words;
    }
}
```

A `String` is an `Object`, but `List<String>` is **not** a subtype of `List<Object>`. If the assignment were allowed, a caller could add an `Integer` through `objects`, corrupting a list expected to contain only strings. `List<?>` is the appropriate choice when you only need to read elements without naming a specific element type.

This is an example of a **negative language rule**, not a warning or runtime exception.

## 5. Pair 2 — Cannot Write Arbitrary Values into `List<?>`

**Must compile:**

```java
import java.util.List;

class ValidRead {
    static int count(List<?> items) {
        return items.size();
    }
}
```

**Must be rejected:**

```java
import java.util.List;

class InvalidWildcardWrite {
    static void add(List<?> items) {
        items.add("abc");
    }
}
```

Here, the compiler does not know whether `?` is `String`. It could be `List<Integer>` or `List<Number>`, so adding `"abc"` cannot be proven safe. The `javac` diagnostic may mention **capture of ?** / `CAP#1`.

Do not misunderstand `List<?>` as strictly immutable: methods like `clear` can compile; if the list is mutable, they can still modify the list. The wildcard restricts **the kind of elements allowed to be written through that reference**, not all mutations automatically.

## 6. Pair 3 — Type Bound `T extends Number`

**Must compile:**

```java
class ValidBound {
    static <T extends Number> double number(T value) {
        return value.doubleValue();
    }

    static void run() {
        double x = number(Integer.valueOf(7));
    }
}
```

**Must be rejected:**

```java
class InvalidBound {
    static <T extends Number> void take(T value) {}

    void run() {
        take("x");
    }
}
```

`Integer` satisfies the `Number` bound; `String` does not. Errors here arise when solving type inference constraints. There is no need to run the method to know that a `String` does not match a type parameter bounded by `Number`.

## 7. Pair 4 — Generic Array Creation and Reifiability

**Must compile:**

```java
import java.util.List;

class ValidWildcardArray {
    List<?>[] groups = new List<?>[2];
}
```

**Must be rejected:**

```java
import java.util.List;

class InvalidGenericArray {
    List<String>[] groups = new List<String>[2];
}
```

Java arrays have a runtime component type; `List<String>` is non-reifiable due to type erasure and therefore cannot be used as the component type when creating an array with this syntax. `List<?>[]` is a valid form, though it **does not assert** that every list in the array contains strings.

If a generic varargs array appears in Java source, the compiler may warn about **possible heap pollution** instead of immediately rejecting the entire method; that is a separate warning scenario and should not be conflated with the `new List<String>[2]` rule.

## 8. Pair 5 — Erasure Causing Two Overloads to Clash

**Must compile:**

```java
import java.util.List;

class ValidNames {
    void showStrings(List<String> items) {}
    void showNumbers(List<Integer> items) {}
}
```

**Must be rejected:**

```java
import java.util.List;

class InvalidErasureOverload {
    void show(List<String> items) {}
    void show(List<Integer> items) {}
}
```

Generic arguments are erased in the method descriptor. Two overloads named `show` whose erased parameters are both `List` cannot produce two distinct signatures in the JVM; `javac` rejects them due to a name clash. Rename the methods or use parameters that actually differ in their erased types instead of expecting the runtime to distinguish `List<String>` and `List<Integer>`.

## 9. Pair 6 — `T.class` Is Not Allowed on a Generic Type Variable

**Must compile:**

```java
class ValidTypeToken {
    static <T> boolean matches(Object value, Class<T> type) {
        return type.isInstance(value);
    }
}
```

**Must be rejected:**

```java
class InvalidTypeVariableClass<T> {
    Class<?> token() {
        return T.class;
    }
}
```

`T` in a generic class is not a runtime class literal. To check a class at runtime, **pass a `Class<T>` token** into the API instead of assuming the compiler always retains the actual type arguments of every object.

## 10. Positive Runnable Demo — Multiple Generic Contracts in One Program

Create the file **`GenericsContractDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Function;

public class GenericsContractDemo {
    static <T> void copy(
            List<? extends T> source,
            List<? super T> target) {
        for (T item : source) target.add(item);
    }

    static double sum(List<? extends Number> numbers) {
        double result = 0;
        for (Number n : numbers) result += n.doubleValue();
        return result;
    }

    static void swapAny(List<?> items, int i, int j) {
        swapCaptured(items, i, j);
    }

    private static <T> void swapCaptured(
            List<T> items, int i, int j) {
        T old = items.get(i);
        items.set(i, items.get(j));
        items.set(j, old);
    }

    static <T extends Comparable<? super T>> T maximum(
            List<? extends T> items) {
        if (items.isEmpty())
            throw new IllegalArgumentException("empty");
        T result = items.get(0);
        for (T item : items)
            if (item.compareTo(result) > 0) result = item;
        return result;
    }

    static <T, R> List<R> map(
            List<? extends T> items,
            Function<? super T, ? extends R> mapper) {
        List<R> result = new ArrayList<>();
        for (T item : items) result.add(mapper.apply(item));
        return List.copyOf(result);
    }

    public static void main(String[] args) {
        List<Integer> numbers = List.of(5, 8);
        List<Number> output = new ArrayList<>();
        copy(numbers, output);
        System.out.println("copied: " + output);
        System.out.println("sum: " + sum(numbers));

        List<String> words =
                new ArrayList<>(List.of("left", "right"));
        swapAny(words, 0, 1);
        System.out.println("swapped: " + words);
        System.out.println("maximum: "
                + maximum(List.of("apple", "pear")));

        Function<CharSequence, StringBuilder> upper =
                s -> new StringBuilder(
                        s.toString().toUpperCase(java.util.Locale.ROOT));
        List<CharSequence> result = GenericsContractDemo
                .<CharSequence, CharSequence>map(
                        List.of("java", "type"), upper);
        System.out.println("mapped: " + result);
    }
}
```

Run:

```bash
javac --release 17 -Xlint:all -Werror GenericsContractDemo.java
java GenericsContractDemo
```

**Verified stdout:**

```text
copied: [5, 8]
sum: 13.0
swapped: [right, left]
maximum: pear
mapped: [JAVA, TYPE]
```

Aspects covered:

- `copy(List<? extends T>, List<? super T>)`: source produces `T`, destination consumes `T` (**PECS**).
- `sum(List<? extends Number>)`: accepts `List<Integer>` when only reading elements as `Number` is needed.
- `swapAny(List<?>)` + private `swapCaptured(List<T>)`: the compiler captures an unknown yet uniform element type to swap elements within the **same list**.
- `maximum`: the bound `T extends Comparable<? super T>` enables comparison and preserves the element type in the return type.
- `map`: the callback accepts a supertype of `T` and produces a subtype of `R`; for example, a function taking `CharSequence` and returning `StringBuilder` in a call expecting a `CharSequence` result.

This is a useful **positive compile test** because it exercises subtype/supertype relationships and wildcard capture rather than only accepting a simple `List<String>` case.

Do not conclude from this that all lists are mutable. `swapAny` was tested on an `ArrayList`; if an unmodifiable list from `List.of(...)` is used, `set` may throw `UnsupportedOperationException` even though type checking succeeds.

## 11. Runtime Demo — Validating Data Outside the Compiler's Visibility

Create the file **`CheckedBoundaryDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class CheckedBoundaryDemo {
    static <T> List<T> checkedCopy(
            List<?> source, Class<T> token) {
        Objects.requireNonNull(source, "source");
        Objects.requireNonNull(token, "token");

        List<T> result = new ArrayList<>();
        for (int i = 0; i < source.size(); i++) {
            Object value = source.get(i);
            if (!token.isInstance(value)) {
                throw new IllegalArgumentException(
                        "index=" + i);
            }
            result.add(token.cast(value));
        }
        return List.copyOf(result);
    }

    public static void main(String[] args) {
        System.out.println("accepted: "
                + checkedCopy(
                        List.of("An", "Binh"), String.class));
        try {
            checkedCopy(List.of("An", 42), String.class);
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected at runtime: "
                    + ex.getMessage());
        }
        System.out.println("list token not enough: "
                + List.class.isInstance(List.of(42)));
    }
}
```

Commands:

```bash
javac --release 17 -Xlint:all -Werror CheckedBoundaryDemo.java
java CheckedBoundaryDemo
```

**Verified stdout:**

```text
accepted: [An, Binh]
rejected at runtime: index=1
list token not enough: true
```

This is an example that **compiles successfully**, then **actively rejects invalid data at runtime** with `IllegalArgumentException`. It is not a negative compilation test.

`List.class` does not retain the `String` type argument at runtime. A `List<Integer>` still satisfies `List.class.isInstance(...)`. To return a trustworthy `List<String>` from a `List<?>` received at a data boundary, you must iterate and validate each element and construct a new typed list as shown.

## 12. Writing Negative Samples as Standalone Fixtures

A sensible organization:

```text
project/
  src/main/java/                   # Production code: must compile
  src/test/java/                   # Harness, JUnit tests: must compile
  src/test/resources/
    compile-positive/
      ValidWildcard.java
      ValidBound.java
    compile-negative/
      InvalidInvariant.java
      InvalidWildcardWrite.java
      InvalidBound.java
      InvalidGenericArray.java
      InvalidErasureOverload.java
      InvalidTypeVariableClass.java
```

The directory names are suggestions, not Gradle/Maven mandates. Most importantly: **do not place files that intentionally fail to compile inside a source set that the main build compiler always processes**. Instead, a compiler harness reads the fixtures and compiles each fixture separately.

When naming fixtures, choose the name of the rule being violated rather than `Bad1`, `Bad2`. Each negative fixture should have a **positive counterpart** to prove the compilation environment itself is not broken before testing the rule.

## 13. Java Compiler API — One Harness Running Both Positive and Negative Samples

The JDK provides `javax.tools.JavaCompiler`. This API can compile in-memory source strings, return success/failure results, and provide diagnostics. The example below is **a standalone program**, verified on Java 17.

Create the file **`CompileContractHarness.java`**:

```java
import java.io.IOException;
import java.net.URI;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public class CompileContractHarness {
    record Case(String name, String source, boolean shouldCompile) {}

    static final class Source extends SimpleJavaFileObject {
        private final String code;

        Source(String className, String code) {
            super(URI.create("string:///" + className
                    + Kind.SOURCE.extension), Kind.SOURCE);
            this.code = code;
        }

        @Override
        public CharSequence getCharContent(
                boolean ignoreEncodingErrors) {
            return code;
        }
    }

    static void check(Case test, Path output) throws IOException {
        JavaCompiler compiler =
                ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("A JDK is required");
        }

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        try (StandardJavaFileManager manager =
                compiler.getStandardFileManager(
                        diagnostics, null, null)) {

            List<String> options = List.of(
                    "--release", "17",
                    "-Xlint:all", "-Werror", "-proc:none",
                    "-d", output.toString());

            JavaCompiler.CompilationTask task =
                    compiler.getTask(null, manager, diagnostics,
                            options, null,
                            List.of(new Source(
                                    test.name(), test.source())));

            boolean actual = Boolean.TRUE.equals(task.call());
            long errors = diagnostics.getDiagnostics().stream()
                    .filter(d ->
                            d.getKind() == Diagnostic.Kind.ERROR)
                    .count();

            if (actual != test.shouldCompile()
                    || (!test.shouldCompile() && errors == 0)) {
                throw new AssertionError(
                        "Unexpected compile result: " + test.name());
            }

            System.out.println(
                    (actual ? "COMPILES: " : "REJECTED: ")
                    + test.name());
        }
    }

    public static void main(String[] args) throws IOException {
        Path classes = Files.createTempDirectory(
                "generic-compile-contracts");
        List<Case> cases = List.of(
            new Case("ValidWildcard",
                    "class ValidWildcard {"
                    + " static int size(java.util.List<?> x)"
                    + " { return x.size(); } }",
                    true),
            new Case("ValidBound",
                    "class ValidBound {"
                    + " static <T extends Number> double x(T n)"
                    + " { return n.doubleValue(); } }",
                    true),
            new Case("InvalidInvariant",
                    "class InvalidInvariant { void f() {"
                    + " java.util.List<String> a="
                    + "java.util.List.of(\"x\");"
                    + " java.util.List<Object> b=a; } }",
                    false),
            new Case("InvalidWildcardWrite",
                    "class InvalidWildcardWrite {"
                    + " void f(java.util.List<?> a)"
                    + " { a.add(\"x\"); } }",
                    false),
            new Case("InvalidBound",
                    "class InvalidBound {"
                    + " static <T extends Number> void take(T x) {}"
                    + " void f() { take(\"x\"); } }",
                    false),
            new Case("InvalidGenericArray",
                    "class InvalidGenericArray {"
                    + " java.util.List<String>[] xs ="
                    + " new java.util.List<String>[2]; }",
                    false),
            new Case("InvalidErasureOverload",
                    "class InvalidErasureOverload {"
                    + " void f(java.util.List<String> x) {}"
                    + " void f(java.util.List<Integer> x) {} }",
                    false),
            new Case("InvalidTypeVariableClass",
                    "class InvalidTypeVariableClass<T> {"
                    + " Class<?> token() { return T.class; } }",
                    false)
        );

        for (Case test : cases) check(test, classes);
        System.out.println(
                "ALL COMPILE CONTRACTS PASSED: " + cases.size());
    }
}
```

Run:

```bash
javac --release 17 -Xlint:all -Werror CompileContractHarness.java
java CompileContractHarness
```

**Verified stdout:**

```text
COMPILES: ValidWildcard
COMPILES: ValidBound
REJECTED: InvalidInvariant
REJECTED: InvalidWildcardWrite
REJECTED: InvalidBound
REJECTED: InvalidGenericArray
REJECTED: InvalidErasureOverload
REJECTED: InvalidTypeVariableClass
ALL COMPILE CONTRACTS PASSED: 8
```

Explanation of each component:

- `Source extends SimpleJavaFileObject` creates an in-memory Java source with URI `string:///ClassName.java`. The source name and class name are consistent so that filename errors do not cause a negative test to pass falsely.
- `JavaCompiler.getTask` performs a separate compilation for each case. Each case uses its own `DiagnosticCollector` so previous errors do not leak across cases.
- `--release 17` locks the Java source level and platform APIs used by the compiler to the Java 17 baseline.
- `-Xlint:all -Werror` enforces a zero-warning policy for positive samples; for negative samples, you still need to inspect the cause of failure.
- `-proc:none` disables annotation processing to avoid unintended dependencies. If the project requires processors, configure an appropriate compile-testing task instead of disabling it mechanically.
- `-d` places output classes into a temporary directory rather than overwriting production/test classes. The demo does not clean up the temp directory; in a real test framework, manage its lifecycle with cleanup.
- `getSystemJavaCompiler()` can return `null` when not running on a JDK with a compiler; the harness reports a clear error in that case.

**Harness limitations:** a negative compile test having `ERROR` is **not sufficient to confirm the target rule** if the code also contains other errors. The fixtures used here are very small, self-contained, and tested, but in strict CI you should also verify that the diagnostic is attached to the expression under test (appropriate file/line/error code) and always have a positive counterpart. You should not hard-match **the exact English text** of the error message because it can vary across JDKs/locales.

## 14. Raw Type Warnings Are Not Mandatory Compilation Errors

Create the file **`RawWarningDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class RawWarningDemo {
    public static void main(String[] args) {
        List<String> typed = new ArrayList<>();
        List raw = typed;
        raw.add(123);

        System.out.println("stored: " + typed);
        try {
            String value = typed.get(0);
            System.out.println(value);
        } catch (ClassCastException ex) {
            System.out.println("runtime: "
                    + ex.getClass().getSimpleName());
        }
    }
}
```

**Without `-Werror`:**

```bash
javac -Xlint:rawtypes -Xlint:unchecked RawWarningDemo.java
java RawWarningDemo
```

`javac` was verified to return exit code **0** while emitting **two warnings**: `[rawtypes]` on `List raw` and `[unchecked]` on `raw.add(123)`.

Program stdout:

```text
stored: [123]
runtime: ClassCastException
```

The raw alias and typed alias refer to the same `ArrayList`, but the raw alias inserts an `Integer`; when read as a `String`, the runtime cast fails. This is evidence of **heap pollution and its runtime consequences**, not evidence that the Java compiler forbids raw types.

**With `-Werror` enabled:**

```bash
javac -Xlint:rawtypes -Xlint:unchecked -Werror RawWarningDemo.java
```

In the verified run, the command returned exit code **1** with the message:

```text
error: warnings found and -Werror specified
```

This is a **policy rejection**. To test properly, record the compiler flags explicitly and separate raw warning cases from negative tests for invariance/generic arrays/bounds.

## 15. Checking Exit Codes Properly in the Terminal

### Bash

```bash
# Valid program: want javac to succeed.
if ! javac --release 17 -Xlint:all -Werror GenericsContractDemo.java; then
  echo "FAIL: valid code did not compile"
  exit 1
fi
java GenericsContractDemo || exit 1

# Intentionally invalid program: want javac to fail.
if javac --release 17 InvalidInvariant.java; then
  echo "FAIL: invalid code unexpectedly compiled"
  exit 1
else
  echo "PASS: invalid code was rejected"
fi
```

### Windows PowerShell

```powershell
javac --release 17 -Xlint:all -Werror GenericsContractDemo.java
if ($LASTEXITCODE -ne 0) {
    throw "Valid code unexpectedly failed"
}
java GenericsContractDemo
if ($LASTEXITCODE -ne 0) {
    throw "Valid program unexpectedly failed"
}

javac --release 17 InvalidInvariant.java
if ($LASTEXITCODE -eq 0) {
    throw "Invalid code unexpectedly compiled"
}
Write-Output "PASS: invalid source rejected"
```

In PowerShell 5.1, an external command returning a nonzero exit code **does not always** stop the whole script automatically; you need to check `$LASTEXITCODE` immediately after the command. Do not proceed to run `java` after a failed compilation, as an old class file might still remain.

In a real pipeline, it is best to use a separate/clean output folder for each case, manage the classpath per fixture, and delete artifacts after testing. Whether testing manually or automatically, **a shell script's success** is meaningless if it accidentally ignores `javac`'s exit code.

## 16. Distinguishing Warnings and Diagnostics in the Compiler API

The compiler returns different kinds of diagnostics, for example:

- `Diagnostic.Kind.ERROR` — an error causing the source to be rejected under the applied rules.
- `Diagnostic.Kind.WARNING` / `MANDATORY_WARNING` — warnings about risks/policies.
- `Diagnostic.Kind.NOTE` — additional explanatory information.

In a negative test, check for `ERROR`; however, if `-Werror` is enabled, you may receive a general error due to the warning policy. If the goal is to prove a **Java language type rule**, you can run that fixture **without `-Werror`** to separate policy from type-system rejection.

Options such as `-Xdiags:verbose` and `-Xlint` are helpful during error investigation, though text strings may vary across compilers/versions. For educational tests, describing the **nature** and showing an excerpt is sufficient. For real compiler regression tests, lock the toolchain and choose an appropriate diagnostic granularity.

## 17. How to Prevent False-Positive Negative Tests

**Pitfall 1 — Failure due to missing import or filename:** `javac` returns nonzero but proves nothing about generics. Use fully qualified names for in-memory fixtures or proper imports; keep file/class names consistent.

**Pitfall 2 — One file containing multiple unrelated errors:** even a single incidental error causes the case to be rejected. Split into small standalone sources, each corresponding to one rule.

**Pitfall 3 — No positive control:** if a valid file with the same dependencies also fails to compile, the cause may be JDK/classpath configuration rather than a generic rule.

**Pitfall 4 — Exact character-by-character matching of stdout or messages:** compiler diagnostics vary in paths, locales, line numbers, and phrasing. Prefer `Kind.ERROR` and normalized location/content conditions.

**Pitfall 5 — Confusing warning-as-error with language errors:** raw types can compile when `-Werror` is off. Policy tests need different names and flags from negative compilation tests.

**Pitfall 6 — Running stale classes after a failed compilation:** use a separate temporary output folder and only run the positive binary if the current compilation succeeded.

**Pitfall 7 — Using unchecked casts to force a positive example to compile:** doing so can mask bugs that should be caught, pushing `ClassCastException` to runtime. Positive samples should be clean of raw/unchecked warnings whenever possible.

**Pitfall 8 — Testing source against only one JDK version:** language features and error messages can change. Use `--release`/toolchains and explicitly document the baseline.

**Pitfall 9 — Treating a runtime `ClassCastException` as compile-time rejection:** these belong to two different testing layers; you need a separate negative fixture for the type checker rule.

**Pitfall 10 — Not testing subtypes/supertypes:** a generic API can reject valid callers due to an overly strict signature. Positive tests with `List<Integer>` → `List<Number>` and `Function<CharSequence,StringBuilder>` are useful checks for flexibility.

**Pitfall 11 — Valid negative test placed in the production source set:** breaks the entire project build. Use test/resources or in-memory compiler fixtures.

**Pitfall 12 — Test fails with `-Werror` without reading diagnostics:** the failure might stem from an unrelated warning. For serious regression tests, record the specific cause.

## 18. Observing the Effect of Erasure with `javap`

After compiling the positive program, run:

```bash
javap -p -s GenericsContractDemo
```

Verified excerpt:

```text
static <T> void copy(
    java.util.List<? extends T>, java.util.List<? super T>);
  descriptor: (Ljava/util/List;Ljava/util/List;)V

static double sum(java.util.List<? extends java.lang.Number>);
  descriptor: (Ljava/util/List;)D

static <T extends java.lang.Comparable<? super T>>
    T maximum(java.util.List<? extends T>);
  descriptor: (Ljava/util/List;)Ljava/lang/Comparable;

static <T, R> java.util.List<R> map(
    java.util.List<? extends T>,
    java.util.function.Function<? super T, ? extends R>);
  descriptor: (Ljava/util/List;Ljava/util/function/Function;)Ljava/util/List;
```

`javap` displays the generic signature when metadata is available, while the JVM descriptor uses erased types: `List`, `Function`, `Comparable`. This explains why two overloads differing only in `List<String>` and `List<Integer>` share the same erased signature.

**Do not infer that identical JVM descriptors mean identical generic contracts:** the compiler still checks wildcards/bounds at the source level before generating bytecode. `javap -v` can show the `Signature` attribute when deeper inspection is needed.

## 19. Adding Regression Tests When Modifying Public APIs

If you change a signature:

```java
// Original:
static <T> void copy(List<T> source, List<T> target)

// More flexible:
static <T> void copy(
        List<? extends T> source,
        List<? super T> target)
```

test **both the positive and negative directions**:

1. Do newly valid callers (for example, `List<Integer>` → `List<Number>`) compile?
2. Are genuinely ill-typed callers (for example, a string source to a number destination) still blocked?
3. Do method references, overloaded calls, and inference with lambdas still compile when using the public API?
4. For a published ABI, do erased descriptors/bridge methods change?
5. Do frameworks reading the generic `Signature` via reflection depend on the previous signature?

Sometimes a refactoring preserves the erased descriptor while **changing the source-level contract**, so you should not rely solely on binary linking or runtime unit tests. A suite of compiler contracts lets you see invalid calls suddenly being accepted, or valid calls being rejected after adjusting wildcards/bounds.

## 20. When to Use the Compiler API vs. `javac` CLI

| Situation | Appropriate Tool | Reason |
| --- | --- | --- |
| Learning a rule, only 1–2 snippets | `javac` CLI | Easy to observe errors immediately |
| Many positive/negative fixtures in CI | `JavaCompiler` or a compile-testing framework | Automated, captures structured diagnostics |
| Checking program execution and stdout | `javac` + `java` or a test framework | Compilation alone does not measure behavior |
| Enforcing zero warnings | `-Xlint:all -Werror` by policy | Distinguishes lint policy from language constraints |
| Checking API baseline | `--release` and toolchain | Avoids depending on features from a newer JDK |
| Checking overloads and erasure | `javac` + `javap` | Inspects both type-checking and erased descriptors |
| Checking runtime data from legacy code | Unit/integration tests + validation | The compiler does not know actual runtime data |

For positive test programs, you can use JUnit if the project already includes it. Snippets showing `@Test` require JUnit imports and dependencies, so they should not be presented as standalone sources runnable with only the JDK. The `CompileContractHarness` above **does not require JUnit**.

## 21. Exercises and Answers

### Exercise 1 — Classifying Errors

What type of test is `List<String> names = List.of("a"); List<Object> target = names;`?

**Answer:** A negative compilation test due to invariance. It must be rejected by `javac` before runtime.

### Exercise 2 — Wildcards

Why can `List<?>` be read as an `Object` while `list.add("x")` is rejected?

**Answer:** The element type is unnamed; when reading, `Object` can be used, whereas when adding `"x"`, it is not guaranteed to match the actual element type.

### Exercise 3 — Bounded Generics

`take(Integer.valueOf(5))` is valid while `take("5")` is rejected when `take` is declared as `<T extends Number>`, right?

**Answer:** Right. `Integer` is a subtype of `Number`, whereas `String` is not.

### Exercise 4 — Generic Arrays

Do `new List<String>[1]` and `new List<?>[1]` have the same compilation result?

**Answer:** No. The first is rejected due to generic array creation; the unbounded wildcard array type is valid.

### Exercise 5 — Running a Negative Fixture?

A fixture fails to compile. Should you run `java Fixture` and check that it throws an exception?

**Answer:** No. The test checks the compiler result and diagnostics; do not run an invalid program. Any leftover class file not produced by that compilation is also meaningless.

### Exercise 6 — Raw Warnings

`List raw = ...; raw.add(42);` emits warnings with `-Xlint` yet compiles successfully. Should this be called a "sample that must be rejected by the language"?

**Answer:** No. With `-Werror`, that is a policy rejection; without the flag, the compiler can generate bytecode. Runtime consequences can be tested separately.

### Exercise 7 — Failing for the Wrong Reason

A test that "must fail due to invariance" fails because of a missing classpath. Does the test PASS?

**Answer:** No; you must fix the setup and verify the intended error. This is why minimal negative fixtures and positive counterparts are needed.

### Exercise 8 — JavaCompiler Diagnostics

`CompilationTask.call()` returns `false`. Is that enough to prove a generic bound test is right?

**Answer:** Not yet. You must verify at least one `ERROR` diagnostic and confirm the cause relates to the bound, not another error.

### Exercise 9 — Type Erasure

Can two overloads `f(List<String>)` and `f(List<Integer>)` coexist?

**Answer:** No, because erasure causes their parameter signatures to clash.

### Exercise 10 — Runtime List Validation

What does `List.class.isInstance(List.of(42))` return? Does it prove the input is a `List<String>`?

**Answer:** It returns `true`; it does not prove the element type is `String`. Each element must be checked if the data is untrusted.

### Exercise 11 — Testing a PECS API

A method has `List<? extends T> source` and `List<? super T> destination`. Is using `List<Integer>` as the source and `List<Number>` as the destination valid?

**Answer:** Valid. The source provides `Integer` as `T`, and the destination accepts `T` or a supertype.

### Exercise 12 — The Goal of `-Werror`

If you want zero warnings on JDK 17, which command should you use?

**Answer:** `javac --release 17 -Xlint:all -Werror File.java` and check for exit code 0. Only add `-Werror` when that is the appropriate policy; do not treat all warnings as Java syntax errors.

## 22. End-of-Lesson Checklist

- [ ] Each rule has a **positive fixture** and a related **negative fixture**.
- [ ] Negative samples fail for the **right rule**; not due to missing imports, class/file names, or classpath issues.
- [ ] Positive samples compile with the baseline JDK and have no unintended unchecked/raw warnings.
- [ ] Every `javac`/`java` command has its exit code checked.
- [ ] A stale `.class` file is never executed after a failed compilation.
- [ ] Warning-as-error is distinguished from language rejection.
- [ ] Runtime validation is tested separately from compile-time constraints.
- [ ] If using `JavaCompiler`, check `Diagnostic.Kind.ERROR` for negative cases.
- [ ] Intentionally invalid fixtures do not appear in the production source set.
- [ ] Generic signatures are evaluated with appropriate subtypes/supertypes, wildcards, and bounds.
- [ ] Program outputs are verified directly and not guessed.
- [ ] When changing a generic API, rerun both positive and negative cases to catch regressions.

## Conclusion

**Writing code samples that must compile and code samples that must be rejected** is the most faithful way to test the essence of Java Generics: calls that satisfy the contract are accepted, while non-type-safe calls are blocked at compile time. Create paired control cases, inspect exit codes and diagnostics, isolate the exact reason the compiler rejects a case, and state the JDK baseline clearly.

Combine compile tests with runtime tests for data that the compiler cannot verify due to type erasure or raw/unchecked APIs. Then, any change to `<T>`, wildcards, bounds, or generic overloads is evaluated by the **actual type contract that callers can or cannot compile**, not just by a few runtime tests that happen to pass.
