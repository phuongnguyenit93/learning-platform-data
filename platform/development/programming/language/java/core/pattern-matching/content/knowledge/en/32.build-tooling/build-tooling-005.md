# Pattern-Related Compiler Warnings: Classification, Reproduction, and Handling in Java Builds

When adding **pattern matching** to a Java project, you may encounter messages from `javac` about *preview features*, *unchecked casts*, *raw types*, or *redundant casts*. At the same time, errors such as **dominated cases** and **non-exhaustive switch expressions** are sometimes mistakenly called "warnings" even though they are actually **compile-time errors**. Reading the diagnostic category accurately helps you choose the right fix: updating the code, configuring the toolchain, bumping the Java level, or intentionally enabling a lint check.

This article belongs to the **Build and tooling** topic. The goal is to use the compiler to understand warnings related to code containing patterns, rather than just learning `instanceof`/`switch` syntax.

**Version scope:**
- Type patterns in `instanceof` have been **final since Java 16** (JEP 394).
- Record patterns and pattern matching for `switch` have been **final since Java 21** (JEP 440, JEP 441).
- The main examples in this article are verified with **`javac 24.0.2 --release 21`**, meaning compilation follows Java 21 language rules and **does not require `--enable-preview`**.
- The section demonstrating **primitive patterns preview on JDK 24** uses its own `--enable-preview --release 24` flags. This is an example of a preview warning **specifically on JDK 24**, not a claim that primitive patterns remain in preview in all future Java releases.

## 1. Distinguishing warnings, errors, and runtime behavior

| Category | When does it appear? | Build impact | Examples |
| --- | --- | --- | --- |
| **Warning** | `javac` recognizes valid code that has a noteworthy aspect | Usually still produces `.class` files unless `-Werror` is enabled | `[unchecked]`, `[rawtypes]`, `[cast]`, `[preview]` |
| **Error** | Code violates syntax, type, dominance, or exhaustiveness rules | Cannot compile the failing part | `this case label is dominated ...` |
| **Runtime exception** | Code compiled, but encounters invalid data or state at runtime | Occurs during execution | `NullPointerException` due to a `null` component |

**Key principle:** the fact that pattern matching is a **final** feature does not mean the compiler will stop warning about unsafe operations **around** patterns. For example:

```java
if (value instanceof java.util.List<?> list) {
    return (java.util.List<String>) list; // Still an unchecked cast.
}
```

The pattern checks that the object is a `List`, but it does not prove that all elements are `String`. Therefore, the compiler still has reason to emit a warning about the generic cast, even though `instanceof List<?> list` is valid and stable.

Conversely, using final syntax properly:

```java
if (value instanceof String text) {
    return text.length();
}
```

does not produce a warning just because the `instanceof` keyword is present.

## 2. Useful javac flags

Basic commands:

```bash
javac -version
javac --help-lint
javac --release 21 -Xlint:all PatternWarningDemo.java
javac --release 21 -Xlint:all -Werror PatternWarningDemo.java
```

In practice, only run commands whose target source files already exist. The list from `--help-lint` depends on the compiler being used.

| Flag | Purpose | Relevance to patterns |
| --- | --- | --- |
| `-Xlint:all` | Enables all supported lint warning categories | Helps catch issues around code refactored to use patterns |
| `-Xlint:cast` | Reports unnecessary casts | Redundant cast after `instanceof Type variable` |
| `-Xlint:unchecked` | Reports generic operations not proven safe by the compiler | Casting from `List<?>` to `List<String>` |
| `-Xlint:rawtypes` | Reports usage of generic types in raw form | `List raw` in legacy code |
| `-Xlint:preview` | Reports usage of language features currently in preview | Preview features on the specific JDK where enabled |
| `-Xlint:fallthrough` | Reports certain cases of falling through from one branch to another in legacy `switch` | Mainly relevant to colon-style switch, not a default warning for `->` cases |
| `-Werror` | Treats detected warnings as **build failures** | Used in CI to prevent new warnings from slipping through |
| `--release N` | Selects the language level, class file target, and platform APIs of Java `N` | Prevents accidentally using Java 21 syntax when a project targets Java 17 |
| `--enable-preview` | Enables preview features for a **source level valid for that compiler** | Only use when a non-final feature on the corresponding JDK is actually needed |

**Distinguishing `-Xlint:all` and `-Werror`:** the first flag determines which warning categories are emitted; the second determines whether those warnings cause **compilation to fail**. `-Werror` does not turn invalid code into valid code, nor does it turn all runtime bugs into diagnostics.

`javac` may print a message like `Note: ... uses unchecked or unsafe operations` when detailed lint is not enabled. To find the root cause, recompile with `-Xlint:unchecked` instead of relying on the brief "Note" line.

## 3. Final Java 21 example: valid patterns do not inherently trigger warnings

Below is a complete Java 21 program that **compiles with `-Xlint:all -Werror` with zero warnings**.

Save as **`PatternWarningDemo.java`**:

```java
import java.util.List;

public class PatternWarningDemo {
    sealed interface Entry permits Text, Count {}
    record Text(String value) implements Entry {}
    record Count(int value) implements Entry {}

    static String classify(Entry entry) {
        return switch (entry) {
            case null -> "null";
            case Text(var value) when value == null -> "missing";
            case Text(var value) -> "text=" + value;
            case Count(int n) when n < 0 -> "negative=" + n;
            case Count(var n) -> "count=" + n;
        };
    }

    static String checkList(Object value) {
        if (!(value instanceof List<?> elements)) {
            return "not-a-list";
        }
        for (Object element : elements) {
            if (!(element instanceof String)) {
                return "mixed-list";
            }
        }
        return "string-list-size=" + elements.size();
    }

    public static void main(String[] args) {
        System.out.println(classify(new Text("Java")));
        System.out.println(classify(new Text(null)));
        System.out.println(classify(new Count(-1)));
        System.out.println(classify(new Count(2)));
        System.out.println(classify(null));
        System.out.println(checkList(List.of("A", "B")));
        System.out.println(checkList(List.of("A", 1)));
        System.out.println(checkList(null));
    }
}
```

Compile and run:

```bash
javac --release 21 -encoding UTF-8 -Xlint:all -Werror PatternWarningDemo.java
java PatternWarningDemo
```

**Exact stdout:**

```text
text=Java
missing
negative=-1
count=2
null
string-list-size=2
mixed-list
not-a-list
```

Explanation:

1. `Text` and `Count` are the two `final` subtypes of `sealed interface Entry`. The switch handles both subtypes and the `null` selector.
2. `Text(var value)` deconstructs the record component. The `value` component can be `null`, so the `value == null` guard is placed before the general branch.
3. `Count(int n) when n < 0` is a guarded branch; the remaining `Count(var n)` catches non-negative integer values.
4. `value instanceof List<?> elements` is a valid type pattern because `List<?>` is a **reifiable** type for runtime checks; it does not claim that `elements` is a `List<String>`.
5. `for (Object element : elements)` checks **each element individually** instead of performing an unsafe generic cast.
6. Passing `null` to `checkList` causes `instanceof` to evaluate to `false`, so the method returns `not-a-list` without throwing an NPE.

Compiler `javac 24.0.2` with `--release 21 -Xlint:all -Werror` accepted the entire example and returned **exit code 0**. From this, we can confirm that **the final pattern syntax in this example produces no lint warnings** under the tested configuration, not that all code containing patterns is guaranteed to be warning-free.

## 4. [cast]: redundant cast after a type pattern

A common refactoring step converts:

```java
if (value instanceof String) {
    String text = (String) value;
    return text;
}
```

into:

```java
if (value instanceof String text) {
    return text; // No need for (String) text.
}
```

Sometimes developers leave the cast in place even though `text` already has type `String`. Full sample to reproduce the warning:

```java
public class RedundantCastDemo {
    static String read(Object value) {
        if (value instanceof String text) {
            return (String) text;
        }
        return "other";
    }
}
```

Compile:

```bash
javac --release 21 -Xlint:cast RedundantCastDemo.java
```

**Verified main diagnostic:**

```text
warning: [cast] redundant cast to String
            return (String) text;
                   ^
1 warning
```

The command does **not** fail by default: this warning advises removing the unnecessary cast, not that the cast changes the runtime type. The proper fix is `return text;`.

**Note:** Do not automatically remove **every cast** in Java code. A cast may affect overload resolution, expression typing, runtime type checks, or generic APIs. Only remove one when the compiler confirms it is a redundant cast or when type analysis shows behavioral equivalence.

## 5. [unchecked] and [rawtypes] around legacy generic casts

Pattern matching does not replace Java generics' type erasure mechanism. The following snippet is a complete program for **reproducing the warnings**, not a safe list-handling approach.

Save **`LegacyWarnings.java`**:

```java
import java.util.List;

public class LegacyWarnings {
    static List<String> uncheckedList(Object value) {
        if (value instanceof List<?> list) {
            return (List<String>) list; // unchecked cast despite the pattern
        }
        return List.of();
    }

    static int rawSize(Object value) {
        if (value instanceof List<?> list) {
            List raw = list; // rawtypes warning
            return raw.size();
        }
        return 0;
    }
}
```

Compile with both lint categories:

```bash
javac --release 21 -Xlint:unchecked,rawtypes LegacyWarnings.java
```

Two verified warnings (file paths and line numbers omitted):

```text
warning: [unchecked] unchecked cast
  required: List<String>
  found:    List<CAP#1>

warning: [rawtypes] found raw type: List
  missing type arguments for generic class List<E>

2 warnings
```

Exact explanation:

- **`List<?> list`:** the compiler only knows this is a `List` containing elements of an unknown type. Checking `instanceof List<?>` cannot inspect generic type arguments due to type erasure.
- **`(List<String>) list`:** this cast has no runtime proof that every element is a `String`. For a mixed list, returning `List<String>` can cause downstream callers to hit a `ClassCastException` when reading elements.
- **`List raw`:** using a raw type discards generic type information. It can bypass type system guarantees and defer type errors until later.
- **Warnings do not disappear when wrapped in a pattern:** `instanceof List<?>` is valid, but any concrete cast afterward must still be scrutinized.

If you only need to iterate over the list and check each element, the approach in `PatternWarningDemo.checkList` is clearer:

```java
static boolean allStrings(Object input) {
    if (!(input instanceof List<?> list)) {
        return false;
    }
    for (Object item : list) {
        if (!(item instanceof String)) {
            return false;
        }
    }
    return true;
}
```

This is an illustrative method and requires `import java.util.List;` in its enclosing class. Iteration can verify contents **at the time of the check**, but it does not make a list that could be mutated externally afterward permanently type-safe. If an API requires `List<String>`, consider copying the type-verified elements into a new list to preserve the invariant.

### Should you use @SuppressWarnings("unchecked")?

Only consider it when there is a **specific type-safety justification** established outside the compiler, such as the contract of a controlled legacy API. Limit the suppression to the smallest possible variable or method and document the invariant clearly. Do not use suppression to hide an unproven cast.

Preferred solutions: **fix the types**, use `List<?>` when the element type is unnecessary, check elements explicitly, or replace raw APIs with generic APIs.

## 6. [preview]: warnings when using preview features

Preview features are enabled per **JDK version**. Historical example: pattern matching for `switch` was in preview from Java 17 through Java 20, but became final in Java 21. Therefore, **`case String s -> ...` on `--release 21` is no longer a preview feature**.

To reproduce a real preview warning, the verification environment used **JDK 24.0.2** and a feature **still in preview in Java 24**: *primitive types in patterns, instanceof, and switch* (JEP 488, second preview in Java 24).

Save **`PreviewPrimitiveDemo.java`**:

```java
public class PreviewPrimitiveDemo {
    static String explain(long value) {
        return switch (value) {
            case 0L -> "zero";
            case long n when n > 0 -> "positive";
            case long n -> "negative";
        };
    }
    public static void main(String[] args) {
        System.out.println(explain(0));
        System.out.println(explain(7));
        System.out.println(explain(-2));
    }
}
```

**Run this preview example only with JDK 24** and the corresponding flags:

```bash
javac --enable-preview --release 24 -Xlint:preview PreviewPrimitiveDemo.java
java --enable-preview PreviewPrimitiveDemo
```

**Observed diagnostic (abbreviated):**

```text
warning: [preview] primitive patterns are a preview feature and may be removed in a future release.
3 warnings
```

The compiler emits three preview warnings in the example, while compilation still succeeds when `-Werror` is not enabled. Running with `java --enable-preview` outputs:

```text
zero
positive
negative
```

This example illustrates the exact purpose of `-Xlint:preview`: **warning about using non-final semantics in the selected Java release**, not claiming that all `switch` statements or all record patterns are in preview.

### Which preview configurations are valid?

A few rules:

1. If using a feature that is in preview on **JDK N**, enable preview with the **current source level N** supported by the compiler, and enable preview on the runtime when executing code that uses preview features.
2. Do not expect a newer JDK's `javac` to support `--enable-preview --release` for an arbitrary older release. For example, `javac 24` with `--enable-preview --release 21` reports `invalid source release 21 with --enable-preview`.
3. Do not use the preview flag to "upgrade" `--release 17` into Java 21. Java 21 record patterns do not exist in Java 17's final language specification.
4. Once a feature becomes **final** in the target build version, remove the preview flag if no **other** preview features are in use. Unnecessary configuration can cause option-combination errors or make pipelines harder to maintain.
5. Preview status may change in releases after JDK 24. When upgrading the JDK, check the JEP and specification for that **exact version** rather than copying an old build command verbatim.

**Using preview features by default in widely distributed libraries is not recommended** without aligning toolchains, runtimes, and JDK syntax-change policies.

## 7. -Werror: why do warnings turn CI red?

For `LegacyWarnings.java` in section 5, compilation normally emits two warnings and still returns exit code 0. When `-Werror` is added:

```bash
javac --release 21 -Xlint:unchecked,rawtypes -Werror LegacyWarnings.java
```

The compiler still prints the same two warnings and then terminates with an error:

```text
error: warnings found and -Werror specified
1 error
2 warnings
```

In this verification run, the code produced **exit code 1**. The role of `-Werror` is to turn the presence of warnings into a **reason to fail the build**; it does not change the nature of an `unchecked` or `rawtypes` warning into an independent type error.

Therefore, when CI fails while a developer's local build passes:

- Check whether CI passes `-Werror`.
- Compare the lint categories enabled in both environments.
- Check the actual compiler version, `--release`, and build tool configuration.
- Read the **original warnings printed before** `warnings found and -Werror specified`; fix the root warnings first.
- Avoid resolving it by disabling all lint checks if the warnings reflect type-safety risks that need fixing.

Some organizations enable `-Werror` only for specific modules or after clearing existing warnings so legacy backlogs do not block the entire system. Whichever policy you choose, understand which warnings are treated as build errors.

## 8. Dominated cases and non-exhaustive switches are compiler errors, not lint warnings

In Java 21 pattern matching for `switch`, two common mistakes are often mislabeled as warnings:

### A broader case placed before a specific case

```java
// Intentionally WRONG example: for diagnostic illustration only, not for running.
static String bad(Object value) {
    return switch (value) {
        case CharSequence chars -> "chars";
        case String text -> "text";
        default -> "other";
    };
}
```

Every `String` is a `CharSequence`. The later `String text` case is shadowed by the first case. With `javac --release 21`, the verified diagnostic is:

```text
error: this case label is dominated by a preceding case label
```

This is an **error even without `-Xlint` or `-Werror`**. Fix it by placing `case String text` before `case CharSequence chars`.

### A switch expression missing a variant

Suppose we have this model:

```java
sealed interface Item permits Text, Count {}
record Text(String value) implements Item {}
record Count(int value) implements Item {}
```

This method is **intentionally wrong**:

```java
static String classify(Item input) {
    return switch (input) {
        case Text(var value) -> "text";
        // Missing Count.
    };
}
```

Because a `switch expression` must be **exhaustive**, the Java 21 compiler rejects it with the verified message:

```text
error: the switch expression does not cover all possible input values
```

Fix it by adding `case Count(var value) -> ...` with the proper business logic, rather than adding `default` just to hide the error when a `sealed` domain should be maintained per subtype.

### No warnings does not mean no bugs

A `switch` over a `sealed` hierarchy can be exhaustive over its subtypes and **still throw an NPE if the selector is `null`** and there is no `case null`. This is a **semantics/runtime** concern, not automatically a lint warning about a missing `null` case.

Similarly, a record pattern can deconstruct a `null` reference component, and code that invokes a method on it will throw an NPE. `-Xlint:all` is not a tool for proving that all business data is non-null. You still need guards, constructor invariants, and boundary-data tests.

## 9. Common diagnostics during refactoring

| Diagnostic or symptom | Classification | How to handle |
| --- | --- | --- |
| `[cast] redundant cast to String` | Warning when `-Xlint:cast` is enabled | Remove the redundant cast already guaranteed by the pattern variable's type |
| `[unchecked] unchecked cast` | Warning when `-Xlint:unchecked` is enabled | Do not assume `List<?>` is `List<String>`; verify elements or fix the API |
| `[rawtypes] found raw type` | Warning when `-Xlint:rawtypes` is enabled | Avoid `List raw`; use an appropriate generic type |
| `[preview] ... may be removed in a future release` | Warning for a preview feature on that JDK | Check JDK/preview flags/JEP; prefer final features when stability is required |
| `warnings found and -Werror specified` | Error because warnings were promoted to build failure | Fix the underlying warnings or adjust the build policy intentionally |
| `this case label is dominated...` | **Compiler error** | Place specific/guarded cases before general cases |
| `switch expression does not cover all possible input values` | **Compiler error** | Add the missing cases; check the `sealed` hierarchy |
| `invalid source release N with --enable-preview` | **Compiler option error** | Use the current preview source level or remove the flag for final features |
| `UnsupportedClassVersionError` at runtime | **Runtime/linkage error** | Run with a Java version supporting the class-file target or rebuild with the right release |
| `NullPointerException` in a case body | **Runtime error** | Check for null selectors and components; do not rely blindly on lint |

**Note:** diagnostic wording can vary across `javac` versions. Reason using the lint category, line number, relevant code, and compiler version rather than writing tool parsers that depend strictly on an exact English message.

## 10. Step-by-step workflow for investigating compiler warnings

1. **Record the exact toolchain.** Run `javac -version`, `java -version`, and check the actual `--release` configured in Maven/Gradle/IDE. Having a newer JDK locally does not mean CI uses that same JDK.
2. **Classify warning vs. error.** Look for the `warning:` or `error:` prefix, the category inside `[...]`, and the exit code. With `-Werror`, the final message may be an error even though the root cause is a warning.
3. **Reproduce with targeted lint.** Run `javac --release 21 -Xlint:cast,unchecked,rawtypes ...` or `-Xlint:all`. Use `javac --help-lint` to see which categories the compiler supports.
4. **Locate the expression causing the warning.** `unchecked` warnings usually come from generic casts, not from the `List<?> list` type pattern itself. `cast` warnings usually come from re-casting an already typed pattern variable.
5. **Check feature status by JDK.** Syntax that is final in Java 21 does not need preview enabled. For a feature that is in preview in a specific version, check its JEP and the flags for that exact version.
6. **Fix type safety before suppressing.** Remove redundant casts; replace raw lists; validate each element before transferring into a concretely typed collection.
7. **If it is a compiler error, fix the structure.** For dominance, order narrow cases before broad ones; for exhaustiveness, update cases to match the domain. `-Xlint` does not resolve these errors.
8. **Recompile under the target release.** Using `--release 21` helps detect source code using features beyond the selected level.
9. **Run runtime tests.** Focus on null selectors, null record components, boundary values, and true/false guards. Clean warnings do not guarantee correct business outcomes.
10. **Integrate checks into CI.** Use a stable, consistent set of flags between local and CI, with a plan to clear legacy warnings before enabling `-Werror` across all modules.

### Short checklist before closing a warning

- Do you know **whether the warning was emitted by the compiler or another plugin** (annotation processor, static analyzer, IDE)?
- Have you identified the **warning category** and the exact source line causing it?
- Does the warning belong to a **final pattern**, a **preview feature**, or **generic/legacy code surrounding the pattern**?
- After fixing, did you recheck both the **compiler exit code** and **runtime behavior**?
- If using `@SuppressWarnings`, is there a safety proof and is the suppression scope as small as possible?

Avoid solving warnings by adding `@SuppressWarnings("all")` or disabling all checks: that hides compiler signals for new issues.

## 11. Integrating into Maven, Gradle, and CI

Depending on your build tool, align on the following decisions:

- A fixed **JDK toolchain** (e.g., Java 21 for source using final record patterns).
- **Release level** using `--release 21` or the build tool's equivalent setting.
- **Lint** enabled with a clear policy: `-Xlint:all` or specific categories like `cast,unchecked,rawtypes` as needed.
- **`-Werror`** if the organization wants zero new warnings, while preparing to address existing warning backlogs.
- **Preview flags** only when code genuinely uses preview features on that JDK, configured across all required compile, test, and run tasks.

Conceptual **Maven Compiler Plugin** configuration: set `release` to `21` and add compiler arguments `-Xlint:all` and `-Werror` to the project's plugin configuration. Check the documentation of your project's plugin version for exact XML syntax and plugin version details; do not assume `maven.compiler.release=21` alone enables lint.

With **Gradle**, you can configure a Java toolchain at `21`, set `options.release = 21` on `JavaCompile`, and pass `-Xlint:all`/`-Werror` via `compilerArgs`. Ensure `Test`/`JavaExec` also run on the appropriate runtime if preview features or Java 21 classes are used.

**Do not automatically add `--enable-preview` just because a module uses `switch` with patterns** when compiling as Java 21: this is already a final feature. Misplaced preview flags can cause CI to fail.

## 12. Verification and scope of conclusions

The practical tests below were run on **javac 24.0.2**:

| Test | Options | Observation |
| --- | --- | --- |
| PatternWarningDemo | `--release 21 -Xlint:all -Werror` | Compiled successfully, **0 warnings**, ran 8 lines of stdout accurately |
| RedundantCastDemo | `--release 21 -Xlint:cast` | **1 `[cast]` warning**, still compiled successfully |
| LegacyWarnings | `--release 21 -Xlint:unchecked,rawtypes` | **2 warnings** (`[unchecked]`, `[rawtypes]`), exit code 0 |
| LegacyWarnings with Werror | Same as above, plus `-Werror` | **2 warnings + 1 error**, exit code 1 |
| PreviewPrimitiveDemo (JDK 24) | `--enable-preview --release 24 -Xlint:preview` | **3 `[preview]` warnings**, still compiled, ran 3 lines accurately |
| String case shadowed by CharSequence | `--release 21` | Compiler **error** `dominated by a preceding case label` |
| Sealed switch missing subtype | `--release 21` | Compiler **error** `does not cover all possible input values` |

Because the `--release 21` tests were executed with the **JDK 24** compiler (compiling at the Java 21 source level), this is **not** proof of running a standalone JDK 21 distribution's `javac` directly. The results are sufficient to confirm the examples and compiler messages observed. When a project targets a Java 21 runtime, also test with the JDK 21 used in the production pipeline.

### When is additional static analysis needed?

`javac -Xlint` is a starting point, not a replacement for all static analysis tools. Nullness analysis, API-misuse checkers, or IDE style rules can catch situations the compiler does not report. Be explicit about which tool produced a warning; do not attribute every IDE diagnostic to `javac`.

For generic collections and nullable data, **tests and domain invariant checks** remain indispensable even when the compiler reports zero warnings.

## 13. Self-practice exercises

**Exercise 1.** Does the following code contain a redundant cast?

```java
if (input instanceof String text) {
    System.out.println(((String) text).length());
}
```

*Answer:* `(String)` can be removed because `text` already has type `String`. With `-Xlint:cast`, the compiler can warn about a redundant cast.

**Exercise 2.** Why does `if (value instanceof List<?> list)` not guarantee that casting to `List<String>` is safe?

*Answer:* Java generics use type erasure; `instanceof List<?>` checks the list type at runtime, not the type of each element. Casting to `List<String>` is unchecked unless the compiler has other proof.

**Exercise 3.** Does placing `case CharSequence cs -> ...` before `case String s -> ...` cause a warning or an error?

*Answer:* **Compiler error** because the `String` case is dominated. No `-Xlint` toggle can make that ordering valid.

**Exercise 4.** On JDK 24, why is `javac --enable-preview --release 21` invalid even though record patterns became final in Java 21?

*Answer:* The preview flag only applies to the preview source level permitted by the current compiler. If the source only uses final Java 21 features, omit `--enable-preview` and use `--release 21`.

**Exercise 5.** CI has `-Werror` enabled and `warning: [unchecked]` appears. How should you fix it?

*Answer:* Identify the generic cast, understand the data invariants, fix the API, or validate each element before constructing a properly typed collection. Only use a narrowly scoped suppression if safety is proven; do not blindly disable all lint checks.

**Exercise 6.** A Java 21 program using record patterns passed `-Xlint:all -Werror`. Can you conclude it has no bugs with `null` data?

*Answer:* No. Syntax and types may be valid, yet dereferencing a nullable record component or omitting `case null` in a `switch` can still throw an NPE. Those scenarios must be tested.

**Exercise 7.** Should `fallthrough` be considered a typical warning for pattern matching `switch` with `->` branches?

*Answer:* No. `-Xlint:fallthrough` is primarily for colon-labeled switch statements that allow control to fall from one statement group into the next. Arrow-style `->` pattern switches do not use that traditional fall-through mechanism.

## 14. References

- [Oracle javac tool guide – JDK 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html): `--release`, `-Xlint`, `-Werror`, and `--enable-preview` options.
- [JEP 394 – Pattern Matching for instanceof](https://openjdk.org/jeps/394): type patterns finalized in Java 16.
- [JEP 440 – Record Patterns](https://openjdk.org/jeps/440): record patterns finalized in Java 21.
- [JEP 441 – Pattern Matching for switch](https://openjdk.org/jeps/441): pattern switch finalized in Java 21.
- [JEP 488 – Primitive Types in Patterns, instanceof, and switch (Second Preview)](https://openjdk.org/jeps/488): preview example in Java 24.
- [JEP 12 – Preview Features](https://openjdk.org/jeps/12): preview mechanism and opt-in requirements.
- [Oracle Java 21 – Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html): case patterns, guards, exhaustiveness, null.
- [Oracle Java 21 – Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html): deconstruction and component patterns.
- [JLS Java 21 – `14.11](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11): switch, case, and dominance rules.
