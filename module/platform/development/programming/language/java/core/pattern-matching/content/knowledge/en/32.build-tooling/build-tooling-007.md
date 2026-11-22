# Static Analysis for Switch Exhaustiveness in Java 21

## 1. Goal: Detecting Missing Branches Before Running the Program

A `switch` that does not handle all valid input values can introduce hard-to-find bugs. For example, today a system has two result types, `Success` and `Failure`; tomorrow `Retry` is added, but the handling logic is forgotten. Without a checking mechanism, the new branch can be skipped or routed into an overly broad `default`.

**Switch exhaustiveness** is determining whether the `case` labels are sufficient to handle **the entire set of values permitted by the type system**. In Java 21, the compiler performs part of this analysis **at compile time**. This is the foundation of **static analysis for switch exhaustiveness** in the *Build and tooling* topic.

This article helps you:

- Understand when `javac` requires a `switch` to be exhaustive, and when it does not.
- Use `enum`, `sealed interface/class`, type patterns, and record patterns so the compiler checks branches.
- Recognize that `when` only filters a branch and does not by itself prove that all values of the same type are handled.
- Understand the difference between `case null`, `default`, and a catch-all pattern.
- Distinguish a **non-exhaustive switch** error from a **dominated case label** error.
- Integrate checks into `javac`, Maven, Gradle, and CI commands, while writing regression tests for per-branch behavior.
- Understand the boundary between static build-time checks and runtime errors when data or binaries change.

**Version:** The main examples use **Java 21**: pattern matching for `switch` was standardized in **JEP 441**, and record patterns in **JEP 440**. These features do not require `--enable-preview` in Java 21. `switch expression` was already a standard feature before Java 21, while pattern cases/`when` have their own evolution history.

## 2. What Is Exhaustiveness and What Is the Compiler Proving?

Consider an enum type:

```java
enum Stage { NEW, RUNNING, DONE }
```

A `switch expression` like the following covers all three enum constants:

```java
static int stageWeight(Stage stage) {
    return switch (stage) {
        case NEW -> 1;
        case RUNNING -> 2;
        case DONE -> 3;
    };
}
```

The compiler confirms that, for a **non-null** `Stage` value matching the enum definition at compile time, there is a corresponding handling branch. Therefore, `default` is not needed.

However, if `case DONE` is removed:

```java
// DOES NOT COMPILE: switch expression does not cover Stage.DONE.
static int incomplete(Stage stage) {
    return switch (stage) {
        case NEW -> 1;
        case RUNNING -> 2;
    };
}
```

The Java compiler reports an error equivalent to **“the switch expression does not cover all possible input values”**.

This checks **coverage by static type**; it does not prove that the expression in each branch is business-correct. For example, `case DONE -> -999` still makes the `switch` exhaustive even though the returned value may be wrong.

### 2.1. Sources of Exhaustiveness

In Java 21, the compiler can determine coverage based on:

- **Enum constants:** all enum constants in unguarded `case` labels.
- **Sealed hierarchy:** branches covering all permitted subtypes of the selector type.
- **Unconditional (catch-all) type pattern:** for example, an unguarded pattern matching all non-null values of the selector.
- **Record patterns:** in cases where the compiler can prove that a set of record patterns covers the selector type, including nested components.
- **`default`:** a fallback branch for values not handled by preceding branches.

Not every `when` expression contributes to coverage. If you have `case Success(var v) when v != null`, it **does not cover all `Success` values**, because `v` can be null.

### 2.2. Exhaustive Does Not Mean Null-Safe

A `switch` can be type-exhaustive yet **still throw `NullPointerException` when the selector is null**, if there is no null-handling policy. For example, `stageWeight` above has no `case null`. If the contract requires returning a dedicated value for null, add a branch:

```java
static int stageWeightOrZero(Stage stage) {
    return switch (stage) {
        case null -> 0;
        case NEW -> 1;
        case RUNNING -> 2;
        case DONE -> 3;
    };
}
```

The enum set is still covered by `NEW/RUNNING/DONE`; `case null` makes **the behavior for null** explicit. Do not treat `default` as an automatic way to catch null in every pattern switch: without `case null`, a null selector typically causes `NullPointerException`.

## 3. Using Sealed Hierarchies So the Compiler Reminds You to Handle New Subtypes

This is where static exhaustiveness is especially useful. Given:

```java
sealed interface Result permits Success, Retry, Failure {}

record Success(String value) implements Result {}
record Retry(int seconds) implements Result {}
record Failure(String reason) implements Result {}
```

A `sealed interface` only permits the implementations declared according to the rules of `permits`. The records above are `final` by record semantics, so the set of valid subtypes at compile time is clearly bounded.

Write a `switch expression`:

```java
static String describe(Result result) {
    return switch (result) {
        case null -> "no-result";
        case Success(var value) when value != null && !value.isBlank()
                -> "success:" + value;
        case Success(var value) -> "invalid-success";
        case Retry(var seconds) when seconds > 0 -> "retry:" + seconds;
        case Retry(var seconds) -> "invalid-retry";
        case Failure(var reason) -> "failure:" + reason;
    };
}
```

**No `default` needed:** every `Success`, `Retry`, and `Failure` has a corresponding unguarded branch, while the two branches with `when` only handle narrower cases. `case null` makes null input explicit.

With this style, if you modify the hierarchy to permit a new subtype, such as `Cancelled`, and forget to update `describe`, **when recompiling dependent source code against the new hierarchy**, the compiler can report missing coverage. This mechanism fits CI very well: a change to the data model forces the development team to review every classification site.

### 3.1. Why Shouldn't You Add `default` Unconditionally?

You could write:

```java
// Idea: this fallback prevents the compiler from catching a missing subtype.
return switch (result) {
    case Success(var v) -> "success";
    case Retry(var seconds) -> "retry";
    case Failure(var reason) -> "failure";
    default -> "other";
};
```

This is a snippet inside a method that has a `result` variable of type `Result`. It may still compile cleanly, but if a subtype is later added to the hierarchy, `default` will cover that subtype. **The compiler no longer forces you to write dedicated logic for the new subtype.**

That does not mean `default` is always bad. If the selector is an open type like `Object` or an API that intentionally provides a fallback for future types, `default` is a reasonable choice. For a closed domain hierarchy where you want to **fail at compile time** when a new subtype appears, it is usually better to list all branches without `default`.

### 3.2. Notes on Sealed Type Hierarchies

If a `sealed class/interface` permits a `non-sealed` subtype, that subtype is open for further subclasses. For coverage, an unguarded `case NonSealedSubtype x` can typically handle all of its subclasses. Do not assume the compiler can enumerate every leaf subclass as it can with `final` records.

If the selector type is `Object` instead of `Result`, the compiler cannot rely solely on the `permits` list of `Result` to prove that the entire `Object` space is handled. **The static type of the selector matters greatly.**

## 4. `when` Guards: Conditional Branches Do Not Prove Full Type Coverage

Suppose you write:

```java
// DOES NOT COMPILE: a Success with a null or blank value has no case.
static String guardOnly(Result result) {
    return switch (result) {
        case Success(var value) when value != null && !value.isBlank()
                -> "ok:" + value;
        case Retry(var seconds) -> "retry";
        case Failure(var reason) -> "failure";
    };
}
```

This is a **non-exhaustive** error, even though all three subtypes are named. Because `when` is false for some `Success` instances, no other branch accepts those cases.

Fix it with an unguarded `Success` case placed **after** the specific case:

```java
static String guarded(Result result) {
    return switch (result) {
        case Success(var value) when value != null && !value.isBlank()
                -> "ok:" + value;
        case Success(var value) -> "bad-success";
        case Retry(var seconds) -> "retry";
        case Failure(var reason) -> "failure";
    };
}
```

The `guarded` snippet is logically complete when placed in a class that defines `Result` and the three records. It will still throw NPE if the input is null and there is no `case null`; compiler acceptance of exhaustiveness **does not automatically guard against null**.

**Order also matters:** if you put the unguarded `case Success(var value)` first, the subsequent `when` case can be reported as **dominated** because the broader branch already covers all `Success` values.

You should test boundary values:

| Input | Guard `value != null && !value.isBlank()` | Branch |
| --- | --- | --- |
| `new Success("A")` | true | `Success` branch with `when` |
| `new Success(" ")` | false | Unguarded `Success` branch |
| `new Success(null)` | false | Unguarded `Success` branch |

A switch with enough cases to satisfy the compiler still needs regression tests for the handling logic inside each branch.

## 5. Enums: Differences Between `switch` Expressions and Traditional `switch` Statements

Do not make a blanket claim that “every Java 21 switch must be exhaustive”. That is **not true** for traditional `switch` statements kept for backward compatibility.

### 5.1. `switch` Expressions Must Be Exhaustive

```java
enum State { STARTED, PAUSED, STOPPED }

static String label(State state) {
    return switch (state) {
        case STARTED -> "started";
        case PAUSED -> "paused";
        case STOPPED -> "stopped";
    };
}
```

If you omit `STOPPED` without adding a fallback, the compiler reports an error.

### 5.2. Traditional `switch` Statements Can Omit Cases

```java
static void logState(State state) {
    switch (state) {
        case STARTED -> System.out.println("started");
        case PAUSED -> System.out.println("paused");
        // Missing STOPPED, still a valid traditional switch statement.
    }
}
```

This code does not automatically produce a compile-time error just for omitting `STOPPED`. When receiving `STOPPED`, the statement may do nothing; that is why code review and tests are needed even when the build succeeds.

### 5.3. Enhanced `switch` Statements in Java 21 Must Be Exhaustive

An **enhanced switch statement** (for example, a statement with a type/record pattern case or `case null`, or a selector of a reference type outside the traditional selector group) **must be exhaustive**. For example:

```java
// DOES NOT COMPILE: enhanced switch statement is missing a fallback.
static void logObject(Object input) {
    switch (input) {
        case String text -> System.out.println(text);
    }
}
```

Fix with a catch-all branch:

```java
static void logObject(Object input) {
    switch (input) {
        case null -> System.out.println("missing");
        case String text -> System.out.println(text);
        default -> System.out.println("other");
    }
}
```

Thus, during review, distinguish **switch expression**, **enhanced switch statement**, and **traditional switch statement**. Having `->` in a `switch` is not enough to conclude it is an expression: `switch (x) { case ... -> System.out.println(...); }` is still a statement.

## 6. Open World: `Object` Selector and the Role of `default`

A `sealed` hierarchy helps bound the set of subtypes. In contrast, with an `Object` selector, the set of runtime types is too broad for a few specific branches to cover completely.

For example:

```java
static String openWorld(Object value) {
    return switch (value) {
        case null -> "null-object";
        case String text -> "text:" + text;
        case Integer number -> "int:" + number;
        default -> "other:" + value.getClass().getSimpleName();
    };
}
```

Here `default` is intentional: values like `Long`, `Double`, `Boolean`, or any record that does not match `String`/`Integer` should be handled in the fallback.

If `default` is removed:

```java
// DOES NOT COMPILE: Object has countless types other than String/Integer.
static String incompleteOpen(Object value) {
    return switch (value) {
        case String text -> text;
        case Integer number -> number.toString();
    };
}
```

The compiler reports non-exhaustive. Adding more cases is not always better: if the domain intentionally accepts types outside the list, you need an explicit fallback rather than an endless enumeration.

An unconditional type pattern can be used for non-null values when appropriate, but avoid letting a broad branch **shadow** specific branches that need dedicated handling.

### 6.1. `default` Does Not Mean Swallowing Errors

A `default -> null` or `default -> ""` can let new data pass through silently. If receiving an unexpected type is a **contract violation**, consider:

```java
default -> throw new IllegalArgumentException(
        "Unexpected type: " + value.getClass().getName()
);
```

This snippet belongs after the `case` labels in a `switch expression` with a non-null `value` on the default branch. If the selector is null without `case null`, the typical behavior is an NPE before reaching `default`. Choose an error policy, not just syntax to stop the compiler from complaining.

## 7. Domination Is a Different Kind of Error, Not Non-Exhaustiveness

The following example **does not compile**:

```java
static String dominated(Object input) {
    return switch (input) {
        case CharSequence cs -> "characters";
        case String s -> "string";
        default -> "other";
    };
}
```

Because every `String` is a `CharSequence`, the preceding `case CharSequence cs` already covers the non-null `String` case. The compiler reports an error equivalent to **“this case label is dominated by a preceding case label”**.

Fix the order:

```java
static String ordered(Object input) {
    return switch (input) {
        case String s -> "string";
        case CharSequence cs -> "characters";
        default -> "other";
    };
}
```

Two different issues need to be addressed separately:

- **Non-exhaustiveness:** there are still valid input values not covered. The solution is to add cases or an appropriate fallback.
- **Domination:** a case is subsumed by a preceding case. The solution is usually to place the narrower case before the broader case, or remove the redundant case.

A codebase can encounter both errors in different places. Do not add `default` to fix a dominated branch; `default` does not make an already-shadowed branch valid.

## 8. Complete Java 21 Example: 11 Behavior Checks

Create the file **`ExhaustiveSwitchAnalysisDemo.java`**:

```java
public class ExhaustiveSwitchAnalysisDemo {
    sealed interface Result permits Success, Retry, Failure {}
    record Success(String value) implements Result {}
    record Retry(int seconds) implements Result {}
    record Failure(String reason) implements Result {}

    enum Stage { NEW, RUNNING, DONE }

    static String describe(Result result) {
        return switch (result) {
            case null -> "no-result";
            case Success(var value) when value != null && !value.isBlank() -> "success:" + value;
            case Success(var value) -> "invalid-success";
            case Retry(var seconds) when seconds > 0 -> "retry:" + seconds;
            case Retry(var seconds) -> "invalid-retry";
            case Failure(var reason) -> "failure:" + reason;
        };
    }

    static int stageWeight(Stage stage) {
        return switch (stage) {
            case null -> 0;
            case NEW -> 1;
            case RUNNING -> 2;
            case DONE -> 3;
        };
    }

    static String openWorld(Object value) {
        return switch (value) {
            case null -> "null-object";
            case String text -> "text:" + text;
            case Integer number -> "int:" + number;
            default -> "other:" + value.getClass().getSimpleName();
        };
    }

    static int checked;
    static void check(String label, String expected, String actual) {
        if (!expected.equals(actual)) {
            throw new AssertionError(label + " expected=" + expected + " actual=" + actual);
        }
        ++checked;
        System.out.println("PASS " + label + " => " + actual);
    }

    public static void main(String[] args) {
        check("success", "success:A", describe(new Success("A")));
        check("blank", "invalid-success", describe(new Success(" ")));
        check("null-value", "invalid-success", describe(new Success(null)));
        check("retry", "retry:5", describe(new Retry(5)));
        check("zero", "invalid-retry", describe(new Retry(0)));
        check("failure", "failure:timeout", describe(new Failure("timeout")));
        check("null-result", "no-result", describe(null));
        check("enum", "2", Integer.toString(stageWeight(Stage.RUNNING)));
        check("enum-null", "0", Integer.toString(stageWeight(null)));
        check("object-string", "text:hey", openWorld("hey"));
        check("object-long", "other:Long", openWorld(3L));
        System.out.println("checks=" + checked);
    }
}
```

Compile/run with **JDK 21 or later** (no preview needed):

```bash
javac --release 21 ExhaustiveSwitchAnalysisDemo.java
java ExhaustiveSwitchAnalysisDemo
```

**Exact stdout:**

```text
PASS success => success:A
PASS blank => invalid-success
PASS null-value => invalid-success
PASS retry => retry:5
PASS zero => invalid-retry
PASS failure => failure:timeout
PASS null-result => no-result
PASS enum => 2
PASS enum-null => 0
PASS object-string => text:hey
PASS object-long => other:Long
checks=11
```

Key points to note:

1. `describe` takes a sealed `Result`: the compiler covers all subtypes without needing `default`.
2. `case Success ... when ...` accepts non-null, non-blank strings; the next `Success` branch handles both blank and null strings.
3. `Retry(0)` does not satisfy the `seconds > 0` guard, yet it is still handled by the unguarded `Retry` branch.
4. A null **selector** enters `case null`; unlike `Success(null)`, which is still a `Success` object and enters the general `Success` branch.
5. `stageWeight` lists all enum constants and handles null separately.
6. `openWorld` has a fallback for the open type `Object`; `3L` is boxed to `Long`, so it does not match `Integer` and enters `default`.
7. `check` only prints PASS if `expected` equals `actual`; any mismatch throws `AssertionError` so the program fails.

This example both demonstrates that the `switch` expressions are **coverage-valid at compile time** and tests the actual behavior of several branches. The two forms of evidence serve different roles: the compiler does not prove that `"invalid-success"` is the business-correct result; the test only compares the selected inputs.

## 9. Examples That Intentionally Fail Compilation to Verify Static Analysis

The snippets below are for **observing compiler messages**. They are not part of the runnable file in Section 8. Place each example in a class/context with the corresponding type declarations, then compile with Java 21 source.

### 9.1. Forgetting a Subtype in a Sealed Hierarchy

```java
// DOES NOT COMPILE: Failure is not handled.
static String missingSubtype(Result result) {
    return switch (result) {
        case Success(var value) -> "success";
        case Retry(var seconds) -> "retry";
    };
}
```

Even though two branches are present, `Result` permits `Failure`, so the `switch expression` is non-exhaustive.

### 9.2. Naming Every Subtype, But the Guard Does Not Cover Everything

```java
// DOES NOT COMPILE: Success with null/blank value is not handled.
static String guardOnly(Result result) {
    return switch (result) {
        case Success(var value) when value != null && !value.isBlank()
                -> "success";
        case Retry(var seconds) -> "retry";
        case Failure(var reason) -> "failure";
    };
}
```

Solution: add an unguarded `case Success(var value) -> ...` **after** the specific `Success` branch.

### 9.3. `Object` Selector Without a Catch-All Case

```java
// DOES NOT COMPILE: Boolean, Long, Object... have no branch.
static String openWithoutDefault(Object value) {
    return switch (value) {
        case String s -> s;
        case Integer n -> n.toString();
    };
}
```

Solution: use `default` or an appropriate catch-all type pattern if the contract needs to handle any `Object`.

### 9.4. Narrower Case After Broader Case

```java
// DOES NOT COMPILE: case String is dominated by the preceding case CharSequence.
static String dominated(Object value) {
    return switch (value) {
        case CharSequence cs -> "characters";
        case String s -> "string";
        default -> "other";
    };
}
```

This is a domination error, not a missing branch. Move `case String` before `case CharSequence`.

**Note on build tests:** A compilation-negative test can place intentionally invalid code in separate fixtures and verify that `javac` returns a non-zero exit code with the expected message group. Do not put `DOES NOT COMPILE` snippets into the production source directory built by CI, otherwise normal builds will fail permanently.

## 10. Integrating Exhaustiveness Checks into Build and CI

### 10.1. The Compiler Is the First Line of Defense

Analyses such as exhaustive/non-exhaustive and dominated cases are checked by **`javac`**. No external tool needs to be installed to catch those fundamental language errors.

For example:

```bash
javac --release 21 ExhaustiveSwitchAnalysisDemo.java
java ExhaustiveSwitchAnalysisDemo
```

If a `switch expression` is non-exhaustive, the compiler reports an error and halts the build for that file. `-Xlint:all` can enable additional warnings, but it **is not a prerequisite for detecting exhaustiveness errors**. `-Werror` turns warnings into errors where applicable; it does not turn a non-exhaustive `switch` into a new error because the code is already a compile-time error.

**Do not automatically fix with `default`** just to make the build green: before adding a fallback, check whether a new subtype needs dedicated business logic.

### 10.2. Maven

For projects using the Maven Compiler Plugin and JDK 21:

```xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
</properties>
```

This configuration snippet is part of `pom.xml`, not a standalone XML file. Verify that Maven runs on a JDK/toolchain capable of compiling target 21, then run:

```bash
mvn test
```

The test build compiles the code first. If there is a non-exhaustive `switch expression`, the compiler error must fail the build before running the corresponding tests. You do not necessarily need to install a separate static analysis plugin to catch errors already enforced by the language.

### 10.3. Gradle Groovy DSL

Example toolchain configuration in a Java project's `build.gradle`:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
tasks.withType(JavaCompile).configureEach {
    options.release = 21
}
```

Run:

```bash
gradle test
```

In a project with the Gradle Wrapper, use `./gradlew test` on Unix-like environments or `gradlew.bat test` on Windows to pin the project's Gradle version. Do not assume that `java -version` in a terminal always matches the toolchain actually used by Gradle or Maven.

### 10.4. Combining CI and Code Review

A useful pipeline:

1. **Compile at the right release level** (Java 21 when using JEP 440/441), without disabling the compilation step.
2. **Run unit tests** for every meaningful branch, especially `when` true/false, null, and fallback.
3. **Run additional static analysis** if the team already uses tools such as IDE inspections, Error Prone, PMD, Checkstyle, or SpotBugs; pattern-switch analysis support depends on each tool's version and configuration.
4. **Review hierarchy/enum changes**: when adding a subtype/constant, inspect places with `switch` on that type and check whether `default` is hiding a branch that needs dedicated handling.
5. **Track code coverage** to spot untested branches; combine boundary values and assertions instead of assuming 100% branch coverage is sufficient.

Do not claim that an external tool can **replace** the compiler's standard exhaustiveness check. External tools can help with additional style rules and bug patterns; `javac` remains the authoritative source for syntax/type rules for the chosen Java target.

## 11. Limitations: Compile-Time Proof Does Not Guarantee Runtime Safety Everywhere

### 11.1. When a Hierarchy Changes Without Synchronized Compilation

A `switch` compiled when a sealed hierarchy had three subtypes may have been considered exhaustive by the compiler. If deployed modules/binaries change out of sync or runtime and binary versions mismatch, a runtime value not anticipated by the compiled branches can appear.

Under Java 21 semantics, a `switch` designed to be exhaustive that executes without a matching label **can throw `java.lang.MatchException`** in such a scenario. This is an exceptional error related to binary/deployment compatibility, not an alternative branch that a switch author should rely on for business control flow.

Good practices: check module version compatibility, rebuild code consuming the hierarchy after type changes, maintain integration tests for supported version combinations, and avoid unintentionally deploying out-of-sync binaries.

### 11.2. A Null Selector Is Not a `MatchException`

When the selector is null and not handled by `case null` (or a valid equivalent), the program typically throws `NullPointerException`. Do not confuse an NPE from a null selector with `MatchException` caused by no pattern applying at runtime.

### 11.3. The Compiler Does Not Validate Record Contents

A record like `Success(String value)` can still hold `value == null` or a blank string, unless the constructor/contract performs validation. Exhaustiveness only guarantees there is a branch for the `Success` type; it does not assert that component data is valid.

Therefore, `case Success(var value) when value != null && !value.isBlank()` needs an unguarded `Success` branch if you want to cover all `Success` instances. This is a classic example of why **static exhaustiveness** must be combined with **negative tests**.

## 12. Static-Analysis-Oriented Switch Review Checklist

| Question | Recommended Action |
| --- | --- |
| Is this a `switch expression` or a statement? | Expressions must be exhaustive; Java 21 enhanced statements as well; traditional statements have a backward-compatibility exception. |
| What is the static type of the selector? | With `Object`, a catch-all fallback is needed; with `sealed`/`enum`, cases can be enumerated exhaustively. |
| Is there a `default`? | Check whether it is necessary or hiding a new subtype. |
| Are there `when` cases? | Check whether an unguarded branch or remaining cases cover when the guard is false. |
| Is the case order valid? | Place narrower patterns before broader patterns to avoid domination. |
| Can `null` occur? | Decide whether to return a fallback, accept null, or intentionally throw NPE; test separately. |
| Are there nested record patterns? | Check whether components can be null/wrong type and whether the case set truly covers the data tree. |
| Was a new enum constant or sealed subtype added? | Recompile, inspect missing-case locations, and check whether `default` hides the new branch. |
| Which release level are Maven/Gradle/IDE using? | Confirm compiler, toolchain, source level, and CI are consistent. |
| Is there additional static analysis? | Use as a second layer of checks; do not rely on it in place of the compiler. |
| Do tests cover guard true/false and boundary values? | Use assertions and expected results matching the contract. |
| Are deployed binaries in sync? | Check compatibility to reduce `MatchException` in isolated scenarios. |

## 13. Practice Exercises

### Exercise A — Find the Non-Exhaustive Error

Given:

```java
sealed interface Command permits Add, Remove, Update {}
record Add(int id) implements Command {}
record Remove(int id) implements Command {}
record Update(int id) implements Command {}
```

Method:

```java
// DOES NOT COMPILE.
static String label(Command command) {
    return switch (command) {
        case Add(var id) -> "add:" + id;
        case Remove(var id) -> "remove:" + id;
    };
}
```

**Question:** Why does it not compile? Should you add `default` or a specific branch?

**Answer:** `Update` is missing. Add `case Update(var id) -> "update:" + id;` when business requirements need explicit handling of every subtype. Do not use `default` merely to mask a missing branch if you want the compiler to prompt updates when subtypes are added.

### Exercise B — A Guard Does Not Make a Type Fully Covered

Given:

```java
record Payment(int amount) {}

// Snippet inside a method taking Object raw:
return switch (raw) {
    case Payment(var amount) when amount > 0 -> "valid";
    default -> "other";
};
```

**Question:** For `Payment(0)`, what does the code return? If the requirement is to distinguish invalid `Payment` from other objects, how should you fix it?

**Answer:** For `Payment(0)`, the guard is false, so it enters `default -> "other"`. To distinguish it, add `case Payment(var amount) -> "invalid-payment"` immediately **after** the guarded case. Because the selector is `Object`, keep `default` to handle the remaining types.

### Exercise C — Error Masked by `default`

A `sealed interface State permits Idle, Active` is handled by a switch with `case Idle`, `case Active`, and `default`. Later, the project adds `Paused`; the build still succeeds.

**Explanation:** `default` already covers `Paused`, so the compiler does not need to force writing a new case. If the intent is to handle each state explicitly, remove `default` from the exhaustive switch on the sealed hierarchy and add cases when the compiler requests them. If you want a fallback for future subtypes, keep `default`, but treat that as an explicit contract choice and test it separately.

### Exercise D — Traditional Statement vs. Enhanced Statement

In Java 21, the snippet:

```java
enum Phase { A, B, C }

static void log(Phase phase) {
    switch (phase) {
        case A -> System.out.println("A");
        case B -> System.out.println("B");
    }
}
```

is a **traditional switch statement** that is non-exhaustive yet syntactically valid. When encountering `Phase.C`, it prints nothing. To enforce handling all enum constants at compile time, you can replace it with a **switch expression** that produces a value, or apply project analysis/testing policies to detect statements that omit cases.

The exercises in this section are illustrative or intentionally invalid snippets for practicing compiler analysis; the complete runnable Java 21 file with exact stdout is in Section 8.

## 14. Conclusion

**Static analysis for switch exhaustiveness** shifts part of the risk of “forgetting to handle a new data kind” from runtime to **compile time**. In Java 21, `switch` expressions and enhanced `switch` statements are checked for completeness by the compiler. Types with a closed value space such as `enum` and `sealed` hierarchies are well suited to explicit case enumeration, often **without needing `default`**.

However, static checks do not verify the logic of each case, do not automatically handle null, do not replace testing `when` false or invalid data states, and do not guarantee compatibility across different deployed binary versions. A reliable build workflow should combine **Java 21 `javac` + branch testing + `default`/guard review + CI/toolchain checks**.

**Official Documentation:**

- [JEP 441 — Pattern Matching for switch (Java 21)](https://openjdk.org/jeps/441)
- [JEP 440 — Record Patterns (Java 21)](https://openjdk.org/jeps/440)
- [Java SE 21 Language Specification, §14.11.1.1 — Exhaustive Switch Blocks](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1.1)
- [Java SE 21 Language Specification, §14.11.2 — Enhanced Switch Statements](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.2)
- [Oracle Java 21 — Pattern Matching with switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
