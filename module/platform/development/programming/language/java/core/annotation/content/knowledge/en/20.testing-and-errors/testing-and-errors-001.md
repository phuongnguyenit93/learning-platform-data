# Testing Successful Compilation and Annotation Samples That Must Be Rejected

## 1. Why Are Both Positive and Negative Compile Tests Needed?

For Java annotations, testing that “valid code compiles successfully” verifies only half of the contract. An annotation library or annotation processor must also **reject invalid code**. If, after modifying the processor, code with a rule-violating `path` is suddenly accepted by the compiler, that is a bug, even if the positive tests are still green.

Two types of tests are needed:

- **Positive compile test:** valid code samples **must be accepted**; `javac` or the `JavaCompiler` API returns a success status.
- **Negative compile test:** code samples that violate the contract **must be rejected**; more importantly, you must check **the exact reason for rejection**, not merely that the compiler failed due to just any error.

Distinguish between two groups of errors:

1. **Language rules of `javac`:** wrong `@Target`, missing required element, wrong element type, non-compile-time constant value, using multiple annotations of the same type when not `@Repeatable`, declaring an annotation element with an invalid type.
2. **Custom business rules:** the `path` string must start with `/`, the `retries` count must be within a range, or the annotated method must have a specific signature. These conditions **are rejected at compile-time only when a processor/tool enforcing the rule is present**.

When designing the test suite, explicitly state which rules are enforced by the compiler and which rules are enforced by the processor. This helps catch cases where **the processor was not activated**, even though the source still compiles normally.

## 2. An Example Annotation Contract

Suppose the project defines:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.METHOD)
@interface Route {
    String path();
    int retries() default 1;
}
```

This code snippet illustrates the contract; the standalone runnable example below will redeclare `Route` within each fixture.

According to the Java language:

- `@Target(METHOD)` only allows the annotation to be attached directly to method declarations.
- `path()` is a **required** `String` element because it has no `default`.
- `retries()` has `default 1`, so users can omit that element.
- `@Retention(SOURCE)` means the annotation usages only need to exist during the source/compilation phase. An annotation processor can still read it at compile-time.

Add the **business** contract for the processor: `path` must start with `/`; `retries` must be within the range **0 to 3**, inclusive of 0 and 3. These conditions do not appear automatically in the default behavior of `javac`.

### Positive examples

```java
class GoodService {
    @Route(path = "/health")
    void health() {}

    @Route(path = "/orders", retries = 3)
    void orders() {}

    static final String BASE = "/find";

    @Route(path = BASE)
    void find() {}
}
```

The methods are in valid positions. `BASE` is a `static final String` initialized with a constant expression, so it can be used as an annotation element value. `health` uses the default `retries=1`, while `orders` uses the upper boundary value 3. The test suite should verify that **all three usages compile successfully**.

## 3. Code Samples That `javac` Must Reject Even Without a Processor

Each of the following snippets is **intentionally invalid**. They must not be combined into a positive test program expecting the compilation command to succeed.

### 3.1 Invalid `@Target` Position

```java
class WrongTarget {
    @Route(path = "/user")
    String user;
}
```

`Route` only allows `METHOD`, not `FIELD`. This is a Java language error checked by the compiler. If `@Target` is later updated to add `FIELD`, the test expectation must change to match the new contract.

### 3.2 Missing Required Element

```java
class MissingPath {
    @Route
    void serve() {}
}
```

`path()` has no default value. The compiler must reject omitting `path`, whereas omitting `retries` is valid.

### 3.3 Wrong Value Type

```java
class WrongType {
    @Route(path = 42)
    void serve() {}
}
```

The number `42` cannot serve as a value for the element `String path()`. There is no need to build a business validator to check this error.

### 3.4 Non-Compile-Time Constant Value

```java
class NonConstantPath {
    static String runtimeValue = "/service";

    @Route(path = runtimeValue)
    void serve() {}
}
```

Although `runtimeValue` has type `String`, it is not a constant variable; the compiler must reject it. Conversely, a `static final String` variable initialized with an appropriate constant expression can be accepted.

### 3.5 Invalid Repeated Annotation

```java
class Duplicated {
    @Route(path = "/a")
    @Route(path = "/b")
    void serve() {}
}
```

`Route` is not declared `@Repeatable`. The compiler must reject two annotations of the same type on a single declaration. If the library supports repeatable annotations, the container type and multi-value semantics should be tested separately.

### 3.6 Disallowed Annotation Element Return Type

```java
@interface InvalidAnnotation {
    java.util.List<String> names();
}
```

`List<String>` is not among the element types supported by the Java language. Annotation elements may only use permitted types (primitive types, `String`, `Class`, enums, annotation types, and one-dimensional arrays of eligible types). This case is invalid **right at the annotation type declaration**, even before any usage site exists.

## 4. Samples That Require a Custom Processor to Be Rejected

The examples below have valid types and valid positions in Java, but **violate business rules**:

```java
class BusinessErrors {
    @Route(path = "orders")
    void noLeadingSlash() {}

    @Route(path = "/orders", retries = 4)
    void tooManyRetries() {}
}
```

If you only run the compiler without enabling the processor, these two methods are essentially still valid with respect to the `Route` definition. To catch the errors during compilation, the processor must read the metadata through the language model and emit `Diagnostic.Kind.ERROR`.

In the complete example:

- `ROUTE001`: `path` does not start with `/`.
- `ROUTE002`: `retries` is not within the range `0..3`.

The processor should use `Elements.getElementValuesWithDefaults(...)` to obtain the effective values of elements, because `retries` may be omitted at the usage site while still having a default of 1. `AnnotationMirror.getElementValues()` simply describes the explicitly declared pairs, which is insufficient if the rule also needs to evaluate defaults.

`@Retention(SOURCE)` **does not hinder an annotation processor**: it analyzes the source/Language Model during compilation without needing runtime Reflection.

## 5. Test Matrix to Implement

| Case name | Test sample | Expectation |
| --- | --- | --- |
| `valid-default` | `@Route(path="/ok")` on method | ACCEPT |
| `valid-boundary` | `retries=3` | ACCEPT |
| `valid-constant` | `path` uses constant `static final String` | ACCEPT |
| `wrong-target` | `@Route` attached to field | REJECT by `javac` |
| `missing-required` | Missing `path` | REJECT by `javac` |
| `wrong-value-type` | `path=42` | REJECT by `javac` |
| `nonconstant` | `path` uses non-constant variable | REJECT by `javac` |
| `not-repeatable` | Two `@Route` on the same method | REJECT by `javac` |
| `processor-path` | `path="orders"` | REJECT by `ROUTE001` |
| `processor-retries` | `retries=4` | REJECT by `ROUTE002` |

By having both pass and fail cases, tests can detect both **overly strict** behavior (rejecting valid code) and **overly permissive** behavior (accepting invalid code).

For the `0..3` range, a production test suite should also add `retries=0` as ACCEPT and `retries=-1` as REJECT to test the lower boundary; the two cases in the table test the default and the upper boundary. When changing a policy, you must update the tests to match the published rules rather than “editing expectations to make them pass” while ignoring the reason for the change.

## 6. Standalone Java 17+: Testing In-Memory Source Code with `JavaCompiler`

The program below uses the **JDK JavaCompiler API** to actually compile standalone fixtures, explicitly register the annotation processor, collect diagnostics, and compare results against expectations.

Create the file **`AnnotationCompileTests.java`**:

```java
import java.io.IOException;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.stream.Stream;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.AnnotationMirror;
import javax.lang.model.element.Element;
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public class AnnotationCompileTests {
    private record Case(String name, String body, boolean accept) {}

    private static final String DECLARATIONS = """
            import java.lang.annotation.*;
            @Retention(RetentionPolicy.SOURCE)
            @Target(ElementType.METHOD)
            @interface Route {
                String path();
                int retries() default 1;
            }
            """;

    private static final class Source extends SimpleJavaFileObject {
        private final String code;

        Source(String code) {
            super(URI.create("string:///Sample.java"), Kind.SOURCE);
            this.code = code;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return code;
        }
    }

    public static final class RouteProcessor extends AbstractProcessor {
        @Override
        public Set<String> getSupportedAnnotationTypes() {
            return Set.of("Route");
        }

        @Override
        public SourceVersion getSupportedSourceVersion() {
            return SourceVersion.RELEASE_17;
        }

        @Override
        public boolean process(
                Set<? extends TypeElement> annotations,
                RoundEnvironment round) {
            if (round.processingOver()) {
                return true;
            }

            for (TypeElement routeType : annotations) {
                for (Element element :
                        round.getElementsAnnotatedWith(routeType)) {
                    for (AnnotationMirror mirror :
                            element.getAnnotationMirrors()) {
                        if (!mirror.getAnnotationType()
                                .asElement().equals(routeType)) {
                            continue;
                        }

                        String path = null;
                        Integer retries = null;
                        var values = processingEnv.getElementUtils()
                                .getElementValuesWithDefaults(mirror);

                        for (var entry : values.entrySet()) {
                            String name = entry.getKey()
                                    .getSimpleName().toString();
                            Object value = entry.getValue().getValue();
                            if ("path".equals(name)
                                    && value instanceof String s) {
                                path = s;
                            }
                            if ("retries".equals(name)
                                    && value instanceof Integer n) {
                                retries = n;
                            }
                        }

                        if (path == null || !path.startsWith("/")) {
                            processingEnv.getMessager().printMessage(
                                    Diagnostic.Kind.ERROR,
                                    "ROUTE001: path must start with /",
                                    element);
                        }
                        if (retries == null || retries < 0
                                || retries > 3) {
                            processingEnv.getMessager().printMessage(
                                    Diagnostic.Kind.ERROR,
                                    "ROUTE002: retries must be 0..3",
                                    element);
                        }
                    }
                }
            }
            return true;
        }
    }

    private static boolean compileCase(
            JavaCompiler compiler, Case test) throws IOException {
        Path output = Files.createTempDirectory("route-compile-");
        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        try (StandardJavaFileManager files =
                     compiler.getStandardFileManager(
                             diagnostics, Locale.ROOT,
                             StandardCharsets.UTF_8)) {
            String sourceCode = DECLARATIONS + "\n" + test.body();
            JavaFileObject unit = new Source(sourceCode);

            List<String> options = List.of(
                    "--release", "17", "-encoding", "UTF-8",
                    "-d", output.toString());

            JavaCompiler.CompilationTask task = compiler.getTask(
                    null, files, diagnostics,
                    options, null, List.of(unit));
            task.setProcessors(List.of(new RouteProcessor()));

            boolean actual = Boolean.TRUE.equals(task.call());
            boolean passed = (actual == test.accept());
            System.out.println((passed ? "PASS " : "FAIL ")
                    + test.name() + " -> "
                    + (actual ? "ACCEPT" : "REJECT"));

            if (!passed) {
                for (Diagnostic<? extends JavaFileObject> diagnostic :
                        diagnostics.getDiagnostics()) {
                    if (diagnostic.getKind() == Diagnostic.Kind.ERROR) {
                        System.out.println("  ERROR: "
                                + diagnostic.getMessage(Locale.ROOT));
                    }
                }
            }
            return passed;
        } finally {
            try (Stream<Path> paths = Files.walk(output)) {
                for (Path path : paths.sorted(
                        Comparator.reverseOrder()).toList()) {
                    Files.deleteIfExists(path);
                }
            }
        }
    }

    public static void main(String[] args) throws IOException {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException(
                    "JDK compiler is required");
        }

        List<Case> cases = List.of(
            new Case("valid-default",
                "class Sample { @Route(path=\"/ok\") void run() {} }",
                true),

            new Case("valid-boundary",
                "class Sample { @Route(path=\"/ok\", retries=3)"
                + " void run() {} }",
                true),

            new Case("valid-constant",
                "class Sample { static final String P=\"/ok\";"
                + " @Route(path=P) void run() {} }",
                true),

            new Case("wrong-target",
                "class Sample { @Route(path=\"/x\") String field; }",
                false),

            new Case("missing-required",
                "class Sample { @Route void run() {} }",
                false),

            new Case("wrong-value-type",
                "class Sample { @Route(path=42) void run() {} }",
                false),

            new Case("nonconstant",
                "class Sample { static String P=\"/x\";"
                + " @Route(path=P) void run() {} }",
                false),

            new Case("not-repeatable",
                "class Sample { @Route(path=\"/a\")"
                + " @Route(path=\"/b\") void run() {} }",
                false),

            new Case("processor-path",
                "class Sample { @Route(path=\"orders\") void run() {} }",
                false),

            new Case("processor-retries",
                "class Sample { @Route(path=\"/orders\", retries=4)"
                + " void run() {} }",
                false)
        );

        boolean allPassed = true;
        for (Case test : cases) {
            boolean passed = compileCase(compiler, test);
            allPassed &= passed;
        }

        System.out.println(allPassed
                ? "ALL TESTS PASSED" : "SOME TESTS FAILED");
        if (!allPassed) {
            throw new IllegalStateException("Compilation contract failed");
        }
    }
}
```

**Run commands** in the directory containing the file, requiring **JDK 17 or higher** and the system Java compiler:

```bash
javac --release 17 -encoding UTF-8 AnnotationCompileTests.java
java AnnotationCompileTests
```

**Stdout when the entire test suite passes:**

```text
PASS valid-default -> ACCEPT
PASS valid-boundary -> ACCEPT
PASS valid-constant -> ACCEPT
PASS wrong-target -> REJECT
PASS missing-required -> REJECT
PASS wrong-value-type -> REJECT
PASS nonconstant -> REJECT
PASS not-repeatable -> REJECT
PASS processor-path -> REJECT
PASS processor-retries -> REJECT
ALL TESTS PASSED
```

### How the Program Works

**`Source`** extends `SimpleJavaFileObject` and holds source code in memory. Each fixture combines the `Route` definition into a new source using the synthetic URI `string:///Sample.java`. `JavaCompiler.getTask(...)` takes the source, the `--release 17` option, the file manager, and the diagnostics receiver.

**`task.setProcessors(List.of(new RouteProcessor()))`** is the core part: the processor is explicitly enabled. If this line is omitted, language errors must still fail, but `path="orders"` and `retries=4` could compile successfully because `javac` does not know the business rules.

**`RouteProcessor`** retrieves annotation mirrors and reads elements using `getElementValuesWithDefaults`. This way it also sees `retries` with default 1, not only explicitly written elements. The processor emits `Diagnostic.Kind.ERROR` with code `ROUTE001` or `ROUTE002` when a value violates the rule.

**`compileCase`** creates a **separate** temporary output directory **for each fixture**, invokes the compiler, and compares the actual boolean against the expectation. It then cleans up the generated `.class` files via `finally`. Cases do not interfere with one another via leftover classes or duplicate `Sample` names.

**`ALL TESTS PASSED`** appears only when every case has the exact defined ACCEPT/REJECT status. The program does not execute the `run()` method of the fixtures; it is **testing the compiler**, not runtime behavior.

The example was verified using the JDK compiler with `--release 17`; three positive cases were accepted and seven negative cases were rejected. When running on another JDK or environment, you should also inspect the error/diagnostic type if results differ to tell whether it is due to the compiler, processor, or configuration.

## 7. Improving Negative Tests: Rejection Must Have **the Right Cause**

The test suite above focuses on the correctness of the compilation status. However, real-world production code needs one more step to avoid **false positives**: a negative case that fails because of a missing classpath or a compiler failure should not be considered a successful test.

For the two business rules, check the **diagnostic code**:

```java
// Extended snippet; uses the diagnostics variable in compileCase.
boolean hasRoute001 = diagnostics.getDiagnostics().stream()
        .anyMatch(d ->
                d.getKind() == Diagnostic.Kind.ERROR
                && d.getMessage(Locale.ROOT).contains("ROUTE001:"));
```

For the `processor-path` case, expect **compilation to fail and contain `ROUTE001`**. The `processor-retries` case must contain `ROUTE002`. If the compiler fails because it cannot find the `Route` type, that is a setup/infrastructure error, not confirmation that the validator is working.

For language-level errors, check that the diagnostic relates to the right rule and avoid relying completely on the **exact wording** of `javac` messages, because messages can differ across JDK versions or locales. Each fixture should intentionally violate only **one underlying condition** to make analysis easy.

If using a shell instead of the API, you need to check the exit code:

- Bash: `$?` is the exit code of the previous command.
- PowerShell: `$LASTEXITCODE` holds the exit code of the native command that just ran.

Do not write tests that “catch any exception and treat it as a pass”; that can hide an improperly configured compiler or processor.

## 8. Testing Boundaries, Defaults, Warnings, and Generated Code

**Value range boundaries:** for `0..3`, `0` and `3` should be valid, while `-1` and `4` should be invalid. A test omitting `retries` should use the default `1`. If the default changes, the test must reflect the new contract.

**Warnings differ from errors:** `Diagnostic.Kind.WARNING` does not necessarily cause the compiler to fail. Mandatory rules that must block the build should use `ERROR`; advisory rules should use `WARNING` and assert the corresponding warning. `-Werror` can turn warnings into errors according to build policy, but you must not assume every environment enables `-Werror`.

**Repeated annotations:** if `@Repeatable` is supported, you must test the container, multiple annotations of the same type, direct/indirect lookup methods, and processing order according to library conventions.

**Type-use annotations:** `ElementType.TYPE_USE` allows markers to appear inside type trees, such as generic type arguments. You should not treat every type-use annotation as a declaration annotation returned by `RoundEnvironment.getElementsAnnotatedWith` like a method/field; it may be necessary to inspect `TypeMirror` or the appropriate AST.

**Code generation by a processor:** beyond compilation pass/fail, verify that resources/sources created by `Filer` have the right names and contents, are not created redundantly across processing rounds, and that the generated source compiles with the target `--release`.

**Runtime validation:** if the annotation also drives a framework at runtime, write separate runtime tests. Compile-time acceptance does not guarantee that registry, transaction, validation, or routing work correctly.

## 9. Designing a Reliable Test Suite in a Project

A practical test matrix should include the following criteria:

| Factor | Requirement |
| --- | --- |
| Fixture set | Positive + negative for each rule, including boundary-value cases |
| Environment | Pin JDK/compiler, release target, classpath, processor path |
| Processor registration | Explicit; do not rely on uncontrolled discovery |
| Isolation | Separate source/output, no accidental reuse of leftover `.class` files |
| Expectations | ACCEPT/REJECT status, error kind, diagnostic code if emitted by processor |
| Reproducibility | Do not depend on diagnostic ordering or unstable error text |
| Generated output | Verify generated files and compilability if code generation is used |
| Regression | Re-run in CI when modifying annotation types, processors, or upgrading JDK |

You should check the processor's **`@SupportedSourceVersion`** configuration when upgrading the application's source level. A processor declaring `RELEASE_17` does not automatically guarantee understanding of all syntax added in newer releases; and `javac --release 17` is what controls the source/API/bytecode target, not the processor's configuration annotation.

## 10. Common Pitfalls

1. **Testing only valid code.** Fails to catch cases where the processor is disabled or a rule becomes too permissive.
2. **Accepting any compile error as a pass for a negative test.** Can produce false “passes” due to missing dependencies or missing configuration.
3. **Confusing compiler errors with business errors.** `path=42` is a Java type error; `path="orders"` violates a custom policy written in the processor.
4. **Not enabling the processor in tests.** Business rules will go unchecked; tests missing negative cases make this even harder to detect.
5. **Not reading default values.** `AnnotationMirror.getElementValues()` may omit `retries` if the usage site does not specify it explicitly.
6. **Combining all invalid code into a single file.** Earlier errors can mask later ones; it is hard to prove which case was actually tested.
7. **Using regex instead of `javac`.** Does not fully model type semantics, `@Target`, constant values, and annotation processing.
8. **Forgetting boundary points.** The `0..3` rule is prone to greater-than vs. greater-than-or-equal comparison bugs.
9. **Treating compile success as runtime success.** A processor validates metadata but does not itself execute application behavior.
10. **Running on a newer JDK without testing the minimum JDK.** `--release 17` is useful, but testing on a real JDK 17 is still valuable for the support matrix.

## 11. Self-Check Exercises

**Question 1.** Why must `@Route(path=42)` fail even when no processor is enabled?

**Answer:** `path()` returns `String`, whereas `42` has type `int`; the compiler itself checks the types of annotation elements.

**Question 2.** Would `@Route(path="orders")` necessarily be rejected by `javac` if the processor does not run?

**Answer:** No. The value has the valid type `String`; the `/` prefix is a custom business rule implemented by the processor.

**Question 3.** Why is `@Route(path="/ok")` still valid even though `retries` is omitted?

**Answer:** `retries()` has `default 1`, so it is not required to be provided explicitly.

**Question 4.** A negative fixture returns REJECT because of a wrong classpath. Should the test PASS?

**Answer:** No. The test needs to verify the expected contract failure reason, especially a processor error code such as `ROUTE001`.

**Question 5.** Why can `static final String P="/ok"` be used as the `path` value while `static String P="/ok"` cannot?

**Answer:** The first is a constant variable initialized with a constant expression; the second is not a valid compile-time constant.

**Question 6.** What do the cases `retries=0` and `retries=3` test?

**Answer:** The two valid boundaries of the `0..3` range; this helps catch off-by-one errors.

**Question 7.** When using `JavaCompiler`, why is `task.setProcessors(...)` needed?

**Answer:** To explicitly activate the processor that enforces business rules and avoid depending on environment-based processor discovery mechanisms.

**Question 8.** Can an annotation with `SOURCE` retention be tested with an annotation processor at compile-time?

**Answer:** Yes. An annotation processor reads the compiler model while the source is being processed, without needing runtime Reflection.

**Question 9.** If a processor also generates a registry class, is checking only that `task.call()` returns true sufficient?

**Answer:** No. You also need to verify the generated artifact's name/contents, verify its compilability, and avoid creating duplicate files across rounds.

**Question 10.** When changing from `@Target(METHOD)` to `@Target({METHOD, FIELD})`, is the negative test for an invalid position on a field still valid?

**Answer:** No. The target contract has changed; you must update the test to reflect the new intent or add an explicit processor rule if the business logic still forbids fields.

## 12. Conclusion

A good annotation test suite must prove that **valid code is accepted**, **invalid code is rejected**, and **the rejection happens for the right reason**. Use `javac` to check language constraints, an annotation processor for business rules, `JavaCompiler` or build scripts to organize isolated fixtures, and add checks for diagnostics, value boundaries, default values, and code generation/runtime behavior when needed. This provides the foundation for modifying processors or upgrading the JDK while preserving the annotation contract.
