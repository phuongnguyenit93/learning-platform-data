# Migrating from Preview Features to Stable Java: Java Core Pattern Matching

## 1. Why Migration Is Needed, Not Just Removing `--enable-preview`

During the development of pattern matching, Java released several **preview** versions to gather feedback before finalizing the semantics and syntax. Code that compiles and runs well on a preview release **does not necessarily** compile as-is on Java 21: some syntax changed, some pattern forms were removed, and rules for handling `null`, dominance, or exhaustiveness were adjusted.

The goals of a good migration are:

1. Lock in the **target Java version** and classify the features in use: already final or still in preview in that version.
2. Update the source code to match the **final syntax and semantics**, without using raw types, unchecked casts, or overly broad `default` branches to mask issues.
3. Update build/test/runtime configurations to compile and run on the exact target JDK.
4. **Clean-rebuild all class files**, without reusing preview binaries from an older JDK.
5. Run regression tests on pattern branches, guards, subtypes, `null`, nested records, and the deployment process across modules together.

In this article, the primary target is **Java 21** with **finalized** pattern matching features, so the complete examples compile with `javac --release 21` **without enabling preview**. If an application still uses **another** preview feature of Java 21, handle that feature separately before removing all preview flags project-wide.

## 2. Preview → Final Roadmap You Need to Know

| Feature | Key Preview Releases | Final Release | Migration Notes |
| --- | --- | --- | --- |
| Pattern matching for `instanceof` | Java 14 — JEP 305; Java 15 — JEP 375 | **Java 16 — JEP 394** | Pattern variables are no longer implicitly `final`; certain always-true type tests are rejected by the compiler |
| Records | Java 14 — JEP 359; Java 15 — JEP 384 | **Java 16 — JEP 395** | A record is a data carrier; not synonymous with a record pattern |
| Sealed classes/interfaces | Java 15 — JEP 360; Java 16 — JEP 397 | **Java 17 — JEP 409** | `sealed`, `permits`, `final`, `non-sealed` form the foundation for exhaustive `switch` |
| Pattern matching for `switch` | Java 17 — JEP 406; Java 18 — JEP 420; Java 19 — JEP 427; Java 20 — JEP 433 | **Java 21 — JEP 441** | Guards switched to `when`; `null` handling, exhaustiveness, dominance, and syntax continued to be refined across previews |
| Record patterns | Java 19 — JEP 405; Java 20 — JEP 432 | **Java 21 — JEP 440** | Supports deconstruction and nested records; some preview syntax does not exist in final |

**Do not confuse a feature's release version with the version of the entire application.** For example, Java 17 supports `instanceof String text`, records, and sealed classes without preview; however, pattern matching in `switch` was **still in preview** on Java 17. Java 21 is the release that finalized `switch` patterns and record patterns.

A single source file using multiple features can have a **mixed preview status**. Therefore, inspect each construct individually rather than just checking whether the file contains the `switch` keyword.

The authoritative reference is [Oracle Java SE 21 — Java Language Changes by Release](https://docs.oracle.com/en/java/javase/21/language/java-language-changes-release.html) and the JEPs listed at the end of this article.

## 3. Preview Flags Before and After Migration

### While Still Using Preview on the Exact JDK That Released It

For example, **on JDK 20**, with source code that actually uses a Java 20 preview feature:

```bash
javac --enable-preview --release 20 PreviewApp.java
java --enable-preview PreviewApp
```

This is a **historical command example**, valid only when using **JDK 20** and actual Java 20 preview source code. You cannot arbitrarily use a newer JDK and pass `--enable-preview --release 20`: the compiler normally only supports enabling preview for **the current release of that compiler itself**.

### When Moving to Java 21 with Finalized Pattern Features

```bash
javac --release 21 MigrationSwitchDemo.java
java MigrationSwitchDemo
```

`--enable-preview` is not needed for Java 21's finalized type patterns in `instanceof`, sealed types, `switch` patterns, and record patterns.

**Be careful:** adding `--enable-preview` to a Java 21 command is not a "compatibility mode for all previous preview syntax." This flag enables **Java 21's own preview features**, not replaced syntax from Java 17/18/19/20. If the project uses another independent preview feature in Java 21, do not remove the flag without inventorying that feature first.

## 4. Major Risk: Preview Class Files from an Older JDK Do Not Transfer As-Is to a Newer JDK

Every class file has a **major/minor version**. For preview class files from Java 12 onward, **minor version 65535** marks a dependency on that release's preview features. Common examples:

- Standard Java 20 class file: **64.0**.
- Java 20 class file using Java 20 preview: **64.65535**.
- Standard Java 21 class file: **65.0**.

According to the JVMS, a class file that depends on a release's preview features **can only be loaded on that same release with preview enabled**; it **cannot be loaded on a different release**, even if the newer release also has `--enable-preview` enabled.

This means you cannot assume a JAR containing Java 20 preview class files will run on Java 21 simply because the feature became final. **You must recompile from Java 21–compatible source code.** Other class files in the JAR that do not use preview features may still run under normal binary compatibility rules, but you should clean-rebuild the entire project to avoid leaving stale preview files behind.

You can inspect class file metadata with:

```bash
javap -verbose MigrationSwitchDemo
```

In the output, look at the `major version` and `minor version` lines. For a class built normally with `javac --release 21` without preview, expect **major 65, minor 0**.

**Do not manually patch the bytecode minor version** to bypass the check: preview class files may also depend on old syntax/semantics and runtime contracts. The right approach is to rebuild, test, and release a new artifact.

## 5. Common Syntax Migration Table

| Old Preview Code / Context | Java 21 Code / Strategy | Reason |
| --- | --- | --- |
| `case String s && test(s) ->` in Java 17/18 preview `switch` | `case String s when test(s) ->` | Guards switched to `when` in Java 19 preview and stayed in Java 21 |
| `case (String s) ->` with a parenthesized pattern | `case String s ->` | Parenthesized patterns were removed in Java 21 |
| `for (Point(var x, var y) : points)` from Java 20 record-pattern-enhanced-for preview | `for (Point p : points) { ... }`, accessing components or matching in the body | Record patterns in enhanced `for` headers were **not kept** in Java 21 |
| Named record pattern like `Point(int x, int y) point` from Java 19 preview | Use `Point(var x, var y)` if only components are needed; or `Point point` and call accessors if the whole record is needed | Named record patterns were no longer supported starting in Java 20 preview |
| `switch` relying on an old total pattern to accept `null` | Explicitly specify `case null` or a non-null contract | From Java 19 preview onward, null handling changed; Java 21 does not treat `default` as a null-handling branch |
| Exhaustive `switch` with an extra `default` added just to pass the compiler | List cases for the exact subtypes; keep `default` **only when intentional** | Avoids masking new cases or unreviewed behavior |

**Do not perform blind search-and-replace.** For example, `&&` is still completely valid inside a guard expression:

```java
case String text when !text.isBlank() && text.length() < 20 ->
        "short-nonblank";
```

What needs to be replaced is **the connector between the pattern and the guard in the `case` label**, not every `&&` in the program.

## 6. Concrete Migration: Guard Syntax `&&` → `when`

### Historical Java 17/18 Preview Code

```java
// Illustrates old preview syntax only; DOES NOT compile with Java 21.
static String classify(Object input) {
    return switch (input) {
        case String s && s.length() >= 4 -> "long-text";
        case String s -> "short-text";
        default -> "other";
    };
}
```

In older previews, the guard was expressed as part of a combined pattern using `&&`.

### Migrated Java 21 Code

```java
static String classify(Object input) {
    return switch (input) {
        case String s when s.length() >= 4 -> "long-text";
        case String s -> "short-text";
        case null -> "missing";
        default -> "other";
    };
}
```

This is an **illustrative method inside a class**, not a standalone runnable file. The new version does more than change the guard syntax: it **explicitly defines `null` behavior** via `case null`.

**When reviewing**, test both paths of the guard: `"java"` returns `"long-text"` and `"go"` returns `"short-text"`. Wrong types like `Integer` go to `default`, while `null` goes to `case null`.

If a case has `when` without an unguarded branch of the same type or a suitable general pattern, the `switch` may be **non-exhaustive**, even if there is already a case for that subtype. Do not treat a guarded case as covering the entire type.

## 7. Migrating Parenthesized Patterns and Named Record Patterns

### Parenthesized Patterns Removed in Java 21

```java
// Intentionally invalid on Java 21:
static String old(Object input) {
    return switch (input) {
        case (String s) -> s;
        default -> "other";
    };
}
```

The Java 21 version removes the parentheses around the pattern:

```java
static String migrated(Object input) {
    return switch (input) {
        case String s -> s;
        case null -> "missing";
        default -> "other";
    };
}
```

Both snippets are **illustrative methods inside a class**; do not place them in the same production source set before fixing the invalid snippet.

### Named Record Patterns in Java 19 Preview

Java 19 preview allowed declaring an identifier for the entire record pattern:

```java
// Historical form no longer valid in Java 21:
if (input instanceof Point(int x, int y) point) {
    System.out.println(point);
}
```

When you need the two components, use:

```java
if (input instanceof Point(var x, var y)) {
    System.out.println(x + y);
}
```

When you need **the record object itself** (for logging, identity, methods, etc.), use a type pattern and accessors:

```java
if (input instanceof Point point) {
    System.out.println(point);
    System.out.println(point.x() + point.y());
}
```

The examples above assume `record Point(int x, int y) {}` is declared. Java 21 does not have deconstruction pattern syntax that **simultaneously names the whole record** like Java 19 preview did. Do not try to work around it with raw casts or by introducing an out-of-scope `point` variable.

## 8. Easy to Miss: Record Patterns in Enhanced `for` Headers Were Removed

Java 20 preview allowed record patterns to appear in enhanced `for` headers, for example:

```java
// Java 20 preview syntax, INVALID in Java 21:
for (Point(var x, var y) : points) {
    System.out.println(x + y);
}
```

In Java 21 final (JEP 440), support for this construct **was removed**, even though record patterns in `instanceof` and `switch` still work.

Replace it with a standard enhanced `for` loop and explicit component access:

```java
for (Point point : points) {
    System.out.println(point.x() + point.y());
}
```

Or if you want to keep pattern matching inside the loop body:

```java
for (Point point : points) {
    if (point instanceof Point(var x, var y)) {
        System.out.println(x + y);
    }
}
```

For an array that may contain `null`, the second approach **skips `null`** because a record pattern does not match `null`; calling `point.x()` directly will throw a `NullPointerException` on a `null` element. Therefore, migration must **define the null policy and test the behavior**; do not treat the two examples as strictly equivalent across all inputs.

Complete program `EnhancedForMigrationDemo.java`:

```java
public class EnhancedForMigrationDemo {
    record Point(int x, int y) {}

    public static void main(String[] args) {
        Point[] points = {
            new Point(2, 3),
            null,
            new Point(4, 1)
        };

        for (Point point : points) {
            if (point instanceof Point(var x, var y)) {
                System.out.println("sum=" + (x + y));
            }
        }
    }
}
```

```bash
javac --release 21 EnhancedForMigrationDemo.java
java EnhancedForMigrationDemo
```

Output:

```text
sum=5
sum=5
```

This is a clear Java 21 style with an explicit `null` policy. If business rules do not allow `null` elements, validate and report an error explicitly instead of skipping them.

## 9. A Complete Java 21 Program After Migration

This example combines a **sealed hierarchy**, **records**, **record patterns**, `switch` expressions, a `when` guard, and `case null`. No preview flags are used.

Save the file `MigrationSwitchDemo.java`:

```java
public class MigrationSwitchDemo {
    sealed interface Result permits Accepted, Rejected {}

    record Accepted(String id, long cents) implements Result {}
    record Rejected(String id, String reason)
            implements Result {}

    static String describe(Result value) {
        return switch (value) {
            case Accepted(var id, var cents) when cents >= 1000 ->
                    "large:" + id;

            case Accepted(var id, var cents) ->
                    "accepted:" + id + ":" + cents;

            case Rejected(var id, var reason) ->
                    "rejected:" + id + ":" + reason;

            case null ->
                    "null-result";
        };
    }

    static void check(String name, String expected, String actual) {
        if (!expected.equals(actual)) {
            throw new AssertionError(
                    name + " expected=" + expected
                            + " actual=" + actual);
        }

        System.out.println("PASS " + name);
    }

    public static void main(String[] args) {
        check("small", "accepted:A:500",
                describe(new Accepted("A", 500)));

        check("large", "large:B",
                describe(new Accepted("B", 1500)));

        check("rejected", "rejected:C:blocked",
                describe(new Rejected("C", "blocked")));

        check("null", "null-result", describe(null));
    }
}
```

Compile and run:

```bash
javac --release 21 MigrationSwitchDemo.java
java MigrationSwitchDemo
```

**Exact stdout:**

```text
PASS small
PASS large
PASS rejected
PASS null
```

### Points to Verify in Migration

- `Result` is a sealed interface: it only permits two direct subtypes, `Accepted` and `Rejected`.
- Each record is `final`; therefore, the `switch` expression can be **exhaustive without `default`**.
- `Accepted` has a `when cents >= 1000` guard; the second `Accepted` case **has no guard**, so it covers the remaining `Accepted` values.
- `case null` separates the selector `null` policy from type coverage of the sealed hierarchy.
- The tests check both true/false guard cases and both subtypes; the `check` method throws `AssertionError` directly, **without relying on the `-ea` flag**.

If `Pending implements Result` is added later, `permits` must be updated and the `switch` will be flagged for review on the next compile. If you simply add `default` to make the build green, consumers may miss the opportunity to catch unhandled new variants.

## 10. Generic Record Patterns When Migrating from Preview

A notable change in Java 20 preview was the ability to **infer type arguments** for generic record patterns, which was kept and finalized in Java 21.

Suppose:

```java
record Box<T>(T value) {}
record Envelope<T>(T payload) {}
```

When full static type information is available:

```java
Box<Box<String>> typed = new Box<>(new Box<>("hello"));

if (typed instanceof Box(Box(var text))) {
    String s = text; // The compiler infers String.
    System.out.println(s);
}
```

This is an **illustrative snippet with already-declared records**. The type of `text` is inferred from the **static generic type** `Box<Box<String>>`, not because the JVM recovers type arguments lost to type erasure.

When the input only has static type `Object`, check the **actual component** using type patterns:

```java
Object input = new Envelope<>(new Box<>("hello"));

if (input instanceof Envelope(Box(String text))) {
    System.out.println(text);
}
```

Do not refactor this into `input instanceof Envelope<Box<String>>(...)` and then be surprised when the compiler rejects the unchecked conversion; specific type arguments cannot be verified at runtime from an arbitrary `Object` value.

### Complete Example Testing Nested Record Patterns After Migration

Save `NestedRecordMigrationDemo.java`:

```java
public class NestedRecordMigrationDemo {
    record Box<T>(T value) {}
    record Envelope<T>(T payload) {}

    static String unpack(Object input) {
        return switch (input) {
            case Envelope(Box(String value)) ->
                    "text:" + value;

            case Envelope(Box(var value)) ->
                    "box-other:" +
                    (value == null
                            ? "null"
                            : value.getClass().getSimpleName());

            case Envelope(var payload) ->
                    "envelope-other:" +
                    (payload == null
                            ? "null"
                            : payload.getClass().getSimpleName());

            case null ->
                    "null";

            default ->
                    "other";
        };
    }

    public static void main(String[] args) {
        Object[] cases = {
            new Envelope<>(new Box<>("hello")),
            new Envelope<>(new Box<>(42)),
            new Envelope<>(new Box<>(null)),
            new Envelope<>(null),
            null,
            "plain"
        };

        for (Object value : cases) {
            System.out.println(unpack(value));
        }
    }
}
```

```bash
javac --release 21 NestedRecordMigrationDemo.java
java NestedRecordMigrationDemo
```

Stdout:

```text
text:hello
box-other:Integer
box-other:null
envelope-other:null
null
other
```

**Note on `null`:** a nested record pattern `Box(...)` does not match when the `Box` component itself is `null`; the `Envelope(var payload)` branch can receive a `null` payload. Likewise, `Box(String value)` does not match a `null` component; the `Box(var value)` branch in the same structure can bind a `null` component.

This is why a migration should include dedicated tests for **outer null, nested null, and component null**, not just common valid data.

## 11. Null Semantics Changed Across Previews — Retest Required

Across the pattern `switch` previews, rules related to `null` were adjusted. Java 21 final has a clear rule:

```java
static String describe(Object value) {
    return switch (value) {
        case String s -> "text:" + s;
        case null -> "missing";
        default -> "other";
    };
}
```

- `describe("a")` returns `"text:a"`.
- `describe(42)` returns `"other"`.
- `describe(null)` returns `"missing"`.

If you **remove `case null`**, even though `default` is still present, a normal `switch(null)` still throws **`NullPointerException`**.

Therefore, when upgrading from an older preview:

1. Find every `switch` that accepts a reference or nullable selector.
2. Define the `null` handling contract: accept, reject, or report an error.
3. Use `case null` if business logic must handle it directly; if `null` is disallowed, validate at the boundary or test the expected exception.
4. **Do not** replace all missing cases with `default` and assume `null` is handled.
5. Test nested record component `null` separately from selector `null`.

Changes in null-matching can leave a program compiling while **changing which branch is selected**, making regression testing just as important as fixing syntax errors.

## 12. Exhaustiveness and Dominance After Removing Preview

Java 21 requires `switch` expressions and enhanced pattern `switch` statements to satisfy the appropriate exhaustiveness rules; dominance rules also prevent cases from being shadowed by an earlier general pattern.

An example that **intentionally does not compile**:

```java
static String wrong(Object value) {
    return switch (value) {
        case CharSequence seq -> "sequence";
        case String text -> "string"; // Dominated by CharSequence.
        default -> "other";
    };
}
```

`String` implements `CharSequence`; with the `CharSequence` type pattern appearing first, the `String` case can never be selected. In Java 21, the compiler detects a dominance error.

The fix is to **place the more specific subtype before the supertype**:

```java
static String correct(Object value) {
    return switch (value) {
        case String text -> "string";
        case CharSequence seq -> "sequence";
        case null -> "null";
        default -> "other";
    };
}
```

Both snippets are **illustrative methods inside a class**; the `wrong` snippet is only for negative compile testing.

In the sealed hierarchy in `MigrationSwitchDemo`, `Accepted` has both a guarded case and an unguarded case. If you remove the unguarded case, some `Accepted` values that do not satisfy `cents >= 1000` will have no matching path; the `switch` may be rejected by the compiler as non-exhaustive.

**Migration guideline:** **fix the code so the compiler can prove all branches are covered**, rather than mechanically adding `default -> null`. If the domain needs explicit handling for new subtypes, an overly broad `default` hides business bugs and loses safety when the type hierarchy grows.

## 13. Preview Source Compatibility Differs from Binary Compatibility

A Java upgrade has at least three layers to evaluate:

| Layer | Check Question | Risk Example |
| --- | --- | --- |
| **Source compatibility** | Does the old source compile with Java 21 final? | Guard using `&&`, parenthesized pattern, enhanced-for record pattern header |
| **Preview binary compatibility** | Can `.class` artifacts built with an old preview be loaded by Java 21? | A Java 20 preview class file with minor `65535` will not load on Java 21 |
| **Runtime/domain compatibility** | Do already-compiled consumers and existing data still work properly? | A sealed hierarchy adds a subtype; an old consumer with a previously exhaustive `switch` may hit `MatchException` |

Source code that is "fixed to compile" can still change logic when `null` or guards are migrated. Conversely, a rebuilt JAR may load normally while another previously compiled consumer does not recognize a new subtype.

**`MatchException` is not evidence that a preview class file loaded**: it is a separate runtime error thrown when pattern matching fails under certain conditions, such as an old consumer receiving a new subtype after a domain change. Old preview class-loading errors and exhaustive switch errors across versions are two distinct categories.

When deploying multiple modules, build and test all consumers that handle shared sealed hierarchies or message schemas. Checking only one source module is not enough for systems where clients and servers upgrade at different times.

## 14. What If the Product Still Must Run on Java 17?

If the target runtime is still Java 17, **you must not use Java 21's final pattern `switch` and record patterns** in source compiled with `--release 17`. Java 17 only supports pattern matching for `switch` as a preview feature; do not enable preview in production if policy requires stable features.

The Java 17–compatible solution is to use **type patterns for `instanceof`** (final since 16), sealed hierarchies, and record accessors (records final since 16).

Standalone example `Java17FallbackDemo.java`:

```java
public class Java17FallbackDemo {
    sealed interface Result permits Good, Bad {}

    record Good(String value) implements Result {}
    record Bad(int code) implements Result {}

    static String render(Result result) {
        if (result instanceof Good good) {
            return "ok:" + good.value();
        }

        if (result instanceof Bad bad) {
            return "bad:" + bad.code();
        }

        throw new IllegalArgumentException("null or unknown");
    }

    public static void main(String[] args) {
        System.out.println(render(new Good("ready")));
        System.out.println(render(new Bad(3)));
    }
}
```

```bash
javac --release 17 Java17FallbackDemo.java
java Java17FallbackDemo
```

Output:

```text
ok:ready
bad:3
```

The code above does not use pattern `switch` or record deconstruction, so it compiles targeting Java 17. When calling `render(null)`, the method throws `IllegalArgumentException`, and any Java 21 replacement must decide whether to preserve that behavior.

**Trade-off:** Java 17 has no equivalent final exhaustive pattern switch, so unit tests, code reviews, and conventions for checking every subtype are needed to avoid missing branches when adding variants.

## 15. How to Adjust Maven When Targeting Java 21 Final

In a Maven project's `pom.xml`, ensure the compiler target release is 21, for example:

```xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
</properties>
```

This is a **`pom.xml` snippet**, not a complete Maven file. You must use a compatible Maven Compiler Plugin/JDK and verify the project's actual configuration.

If preview was previously enabled, review **every place** where the flags may appear:

- Compiler: `--enable-preview` in `maven-compiler-plugin` / compiler args.
- Unit tests: `--enable-preview` in `maven-surefire-plugin`, `maven-failsafe-plugin`, or JVM argLine.
- Application at runtime: `--enable-preview` in startup scripts, container images, or server flags.
- IDE: language level set to an older JDK's preview mode.

Once all source code uses **Java 21 finalized pattern features** and **no other preview features remain**, remove those flags and run a clean build:

```bash
mvn clean verify
```

**Do not remove preview flags globally if the project still uses another preview feature.** Handle, remove, or isolate that feature according to your policy before deciding the flags for specific tasks.

In multi-module projects, each module's Maven toolchain/compiler release must align with the target contract; do not assume a Java 21 module will run on a Java 17 runtime.

## 16. How to Adjust Gradle and CI Environments

For Gradle projects using the Kotlin DSL, the Java toolchain/release configuration can be written as:

```kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(21)
}
```

This is a **configuration snippet for `build.gradle.kts`** assuming the Java plugin and corresponding types/APIs are available, not a complete script. Confirm that test tasks and `JavaExec` tasks also run on the appropriate JVM if the project uses custom configuration.

For a project that only uses Java 21 final features, review and remove any preview flag previously added:

```text
--enable-preview
```

from `JavaCompile.options.compilerArgs`, `Test.jvmArgs`, `JavaExec.jvmArgs`, IDE run configurations, or actual startup commands.

**CI should verify the JDK running the tests, not just the compiler target.** `--release 21` controls source/standard API/class file target compatibility during compilation, but a test running on a different JDK may behave differently from the production environment. For critical migrations, run at least one lane on an actual JDK 21 with the same JVM flags planned for deployment.

## 17. Migration Testing Strategy: Compile, Behavior, and Integration

A test plan can be divided by layer:

| Layer | Action | Expectation |
| --- | --- | --- |
| **Compile-positive** | `javac --release 21` without preview on migrated source | No removed preview syntax remains |
| **Compile-negative** | Test fixtures with `case String s && ...` or `for (Point(var x, var y) : ...)` | The Java 21 compiler **rejects** the fixture as expected |
| **Runtime branch tests** | Matching types, non-matching types, true/false guards | Corresponding results are correct |
| **Null regression** | Selector `null`, nested record null, component null | Matches the chosen policy |
| **Exhaustiveness test** | Add a subtype to a sealed hierarchy and recompile consumers | The compiler catches missing cases when no suitable catch-all exists |
| **Binary scan** | Run `javap -verbose` on build artifacts | No old-release preview class files remain |
| **Integration/rollout** | Run consumers + shared libraries at target versions | No class loading, schema, or subtype mismatch errors |

**Negative compile tests** intentionally contain non-compiling source code, so they must live in separate fixtures rather than being mixed into `src/main/java` where they would break the production build. If automating error checks, prefer asserting a non-zero `javac` exit code rather than relying strictly on exact diagnostic wording.

Runtime tests should include **guard boundary cases** (`999`, `1000` when the threshold is `>= 1000`) and new subtype cases. Intentionally omitting `default` in a sealed `switch` helps the compiler remind consumers to update when the type hierarchy expands.

## 18. Step-by-Step Rollout to Reduce Risk

**Step 1 — Inventory.** Find all sources/modules with `--enable-preview`, `switch` type/record patterns, `case ... && ...`, named/parenthesized patterns, or record patterns in enhanced `for` headers. Identify which release each feature belongs to.

**Step 2 — Choose the target.** If Java 21 is available, the pattern features in this article are final. If Java 17 must be kept, choose the fallback path with `instanceof` and accessors.

**Step 3 — Fix changed syntax.** Convert guards to `when`, remove parenthesized patterns, replace named record patterns, and rewrite enhanced-for headers. For each change, record the null/guard/exhaustiveness contract to preserve.

**Step 4 — Review the domain.** If the code uses sealed hierarchies, check `permits` and every consumer `switch` when adding subtypes. Do not use `default` to ignore new logic.

**Step 5 — Clean rebuild with the target JDK.** Do not reuse build caches or old preview JARs as a shortcut. Ensure shared internal libraries are also released with the appropriate target.

**Step 6 — Run behavioral and negative compile tests.** Verify final syntax, `null`, nested components, and guard branches with reliable tests. Compare results against intended business behavior, not just how a particular preview release happened to run.

**Step 7 — Finalize build/runtime flags.** When no other preview features remain, remove `--enable-preview` from the compiler, test runner, and startup. Check manifests, Dockerfiles, and IDE settings if needed.

**Step 8 — Integration and rollout.** Test applications, service consumers, deserializers/persistence, and shared domain artifacts in the actual deployed version combinations.

If the project has staggered environment upgrades, roll out in phases with dedicated contract tests; Java 21 source running well in one service **does not guarantee** older clients are ready to understand new subtypes or schemas.

## 19. Pitfalls to Avoid

1. **"`--enable-preview` on JDK 21 enables all preview syntax from JDK 17–20."** False. This flag only enables previews of the current release.
2. **"Pattern matching is final, so old preview `.class` files will run as-is."** False. Preview class files are tied to a single release and must be rebuilt.
3. **"All pattern matching has been final since Java 16."** False. `instanceof` was finalized in 16; `switch` patterns and record patterns were finalized in 21.
4. **"Preview `&&` guards can stay as-is in Java 21."** False at the position connecting a pattern to a guard; use `when`.
5. **"Record patterns in enhanced-for headers still work because record patterns are final in 21."** False. That header syntax was removed.
6. **"Java 19 preview's `Point(int x, int y) point` can be kept."** False. Use a record pattern without an identifier for the whole record, or use the type pattern `Point point`.
7. **"`case null` and `default` are the same."** False. Without `case null`, a `null` selector normally causes a `NullPointerException`.
8. **"Adding `default` is always the right way to fix an exhaustive switch."** False. It can hide missing logic for new subtypes.
9. **"`record Box<T>` recovers its type argument at runtime."** False. Generic type erasure still applies; pattern inference relies on static types or component checks.
10. **"Compiling successfully means migration is done."** False. You must verify runtime behavior, preview binaries, nested nulls, versioning, and deployment.
11. **"You can compile with `--release 21` and run the same bytecode on Java 17."** False. Java 17 does not support Java 21's class-file version 65.
12. **"You should replace all preview code with `instanceof`/casts to avoid changing the build."** Unnecessary. Java 21 final already has pattern `switch` and record patterns; using the official syntax makes the code safer and expresses the domain more clearly.

## 20. Pre-Completion Migration Review Checklist

- Is the target runtime/JDK explicitly documented as Java 21 or another version?
- Have you distinguished Java 16 final `instanceof`, Java 17 final sealed types, and Java 21 final `switch`/record patterns?
- Are any `case ... && ...`, parenthesized patterns, named record patterns, or record patterns in enhanced-for headers left?
- Have `when` guards been tested for both true/false and boundary thresholds?
- Have `null` cases been tested for the selector, nested records, and components?
- Do sealed `switch` statements remain exhaustive when a subtype is added? Does `default` hide unhandled cases?
- Have you done a clean rebuild and verified that artifacts contain no old preview class files?
- Have shared Java 21 modules been built/deployed in sync and tested together?
- Was `--enable-preview` removed **only after** ruling out other preview features in use?
- Do Maven/Gradle/IDE/CI/test runtimes share the same target and valid flags?
- Are runnable tests and negative compile tests separated, without putting invalid source into production?
- Have rollback paths and monitoring for class-loading/`MatchException` errors during rollout been documented?

**Conclusion:** Migrating from Java preview to Java 21 final is a **source + binary + behavioral migration**, not merely deleting a compiler flag. Keeping the benefits of pattern matching, updating changed syntax, verifying `null`/guards/exhaustiveness, **rebuilding all preview artifacts**, and running compatibility tests on the target JDK is the reliable path.

## References

- [Oracle Java SE 21 — Language Changes by Release](https://docs.oracle.com/en/java/javase/21/language/java-language-changes-release.html)
- [Oracle Java SE 21 — Language Changes Summary](https://docs.oracle.com/en/java/javase/21/language/java-language-changes-summary.html)
- [JEP 305 — Pattern Matching for `instanceof` (Preview)](https://openjdk.org/jeps/305)
- [JEP 375 — Pattern Matching for `instanceof` (Second Preview)](https://openjdk.org/jeps/375)
- [JEP 394 — Pattern Matching for `instanceof` (Final)](https://openjdk.org/jeps/394)
- [JEP 409 — Sealed Classes (Final)](https://openjdk.org/jeps/409)
- [JEP 406 — Pattern Matching for `switch` (Preview)](https://openjdk.org/jeps/406)
- [JEP 420 — Pattern Matching for `switch` (Second Preview)](https://openjdk.org/jeps/420)
- [JEP 427 — Pattern Matching for `switch` (Third Preview)](https://openjdk.org/jeps/427)
- [JEP 433 — Pattern Matching for `switch` (Fourth Preview)](https://openjdk.org/jeps/433)
- [JEP 441 — Pattern Matching for `switch` (Final)](https://openjdk.org/jeps/441)
- [JEP 405 — Record Patterns (Preview)](https://openjdk.org/jeps/405)
- [JEP 432 — Record Patterns (Second Preview)](https://openjdk.org/jeps/432)
- [JEP 440 — Record Patterns (Final)](https://openjdk.org/jeps/440)
- [Java SE 21 JVMS §1.5 — Preview Features](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-1.html#jvms-1.5)
- [Java SE 21 JLS §14.11 — `switch` Statements](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
