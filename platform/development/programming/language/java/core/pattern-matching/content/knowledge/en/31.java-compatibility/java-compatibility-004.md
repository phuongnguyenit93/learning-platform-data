# Final Features and Preview Features in Java Pattern Matching

In Java, a language feature can first appear in a **preview** state (controlled experimentation), be refined across multiple JDK releases, and then become **final** (an official Java SE feature). This is especially important for **pattern matching**, because the same overarching idea spanned multiple release milestones: type patterns in `instanceof`, record patterns, and pattern matching for `switch` **did not become final in the same version**.

This article helps you distinguish feature states, choose the right JDK, use `--release` and `--enable-preview` correctly, read compile/runtime errors, and plan code migration from preview to final. The focus is on Java Core Pattern Matching, not every Java feature across releases.

**Key takeaway:** For the main features explained here, the `instanceof` type pattern has been final since **Java 16**, while **record patterns** and **pattern matching for `switch` became final in Java 21**. The Java 21 code in the hands-on section runs **without** `--enable-preview`.

## 1. How do preview, final, and incubator differ?

### Preview features

A **preview language feature** already has a complete design and implementation, and is included in a JDK release for the community to try out and provide feedback on, but **is not yet a permanent, official part of the Java SE language in that release**. A preview feature may change its syntax, semantics, or scope of support when moving to the next preview release.

When actually using preview syntax, you must explicitly enable preview at both **compile time** and **runtime**:

```bash
# Illustration for a feature that is in preview in JDK N, using that exact JDK N.
javac --enable-preview --release N Example.java
java --enable-preview Example
```

Here, `N` is a **placeholder for the version number of the exact JDK in use** (for example, `17` when running `javac` from JDK 17), not a literal command to copy with the letter `N`. Concrete commands for Java 17 are in Section 6.

Important point: `--enable-preview` does not mean "enable all future features" or "allow using any preview feature on any older JDK." It only unlocks the preview features of **the exact source version supported by the current compiler**.

### Final features

When a feature becomes **final**, its syntax and semantics are incorporated into the corresponding Java SE specification. Learners and applications can use it with the normal compilation configuration of a supported version, for example:

```bash
# With JDK 21 or a newer compiler that supports --release 21:
javac --release 21 Example.java
java Example
```

You do not need `--enable-preview` if `Example.java` only uses features that are already final in Java 21 or earlier. This does **not** mean that every snippet written with an older preview will automatically compile under the final syntax: preview rounds can change syntax and rules.

### Incubator does not mean preview

Java also has **incubator modules/APIs**. They may require special modules and `--add-modules` configuration. That is a different mechanism from **preview language features** and the `--enable-preview` flag. Do not call an incubator API "pattern matching preview" just because it is also not yet stabilized.

In this article, "preview" refers only to **language grammar/mechanisms** related to pattern matching, not the status of every Java library.

## 2. Standardization Timeline of Pattern Matching Features

Each milestone below indicates the status of a **specific feature** in that Java release, not the overall status of the entire language.

| Feature | Preview releases | Final release | Final JEP |
| --- | --- | --- | --- |
| Pattern matching for `instanceof` | Java 14 (JEP 305), Java 15 (JEP 375) | **Java 16** | [JEP 394](https://openjdk.org/jeps/394) |
| Record patterns / deconstruction | Java 19 (JEP 405), Java 20 (JEP 432) | **Java 21** | [JEP 440](https://openjdk.org/jeps/440) |
| Pattern matching for `switch` | Java 17 (JEP 406), 18 (JEP 420), 19 (JEP 427), 20 (JEP 433) | **Java 21** | [JEP 441](https://openjdk.org/jeps/441) |

### Why are there multiple preview rounds?

A feature may be tested across multiple JDK releases to refine variable naming, variable scope (*flow scoping*), `null` handling, guards, dominance, and `switch` *exhaustiveness*. Therefore, preview code written in one JDK release **is not guaranteed to be source-compatible** with the next preview release or with the final syntax.

One important example: the design iterations of pattern matching for `switch` changed how **guards** are expressed before the `when` syntax became part of the final feature in Java 21. Thus, you should not take `case String s when ...` code from a Java 21 article and assume it compiles as-is in every earlier preview release.

### Foundational features have their own history

Pattern matching is often built on top of `record` and `sealed` domain models, but these two features have their own standardization history:

| Foundational feature | Preview | Final |
| --- | --- | --- |
| `record` | Java 14 (JEP 359), Java 15 (JEP 384) | **Java 16**, JEP 395 |
| `sealed class` / `sealed interface` | Java 15 (JEP 360), Java 16 (JEP 397) | **Java 17**, JEP 409 |

**Do not confuse `record` with `record pattern`:** Java 17 already lets you declare `record Point(int x, int y) {}`, but the **deconstruction** syntax `case Point(int x, int y) -> ...` was not yet a final feature in Java 17. Record patterns became final in Java 21.

## 3. Choosing the Java Version Based on Syntax

Consider the following sample snippets:

### Type pattern in instanceof

```java
Object input = "Java";
if (input instanceof String text) {
    System.out.println(text.length()); // 4
}
```

`String text` is an `instanceof` **type pattern**, which has been final since **Java 16**. In Java 17 or Java 21, this syntax works without any preview flag.

### Record declaration

```java
record Point(int x, int y) {}
```

`record` has been final since **Java 16**. This line by itself does not require record patterns and does not need preview on Java 17+.

### Record pattern in instanceof

```java
Object input = new Point(2, 3);
if (input instanceof Point(int x, int y)) {
    System.out.println(x + y); // 5
}
```

`Point(int x, int y)` is a **record pattern**, directly extracting the two components. This syntax is final from **Java 21**; if a project sets `--release 17`, using a record pattern is invalid at that language level.

### Pattern switch

```java
static String inspect(Object input) {
    return switch (input) {
        case null -> "missing";
        case String text -> "text=" + text;
        case Integer number -> "number=" + number;
        default -> "other";
    };
}
```

This is **pattern matching for switch**, final from **Java 21**. The feature previously existed in preview in Java 17–20. When compiling with `--release 21` on a supported JDK, `--enable-preview` is not needed.

**Minimum selection rules:**

- Only need `instanceof Type variable`: you can choose Java **16+**.
- Using `record` and `sealed`, without record patterns or pattern switch: Java **17+** supports these parts in final form.
- Using record patterns or pattern switch as final features: choose **Java 21+**.
- If a project is pinned to an older JDK and a feature is only in preview in that exact JDK, both appropriate compile and runtime configurations are required; you must accept the risk of changes between preview releases.

The milestones above are **minimums based on language syntax**. A program may also depend on other APIs, libraries, and runtime policies.

## 4. Java 17: Example Using Only Final Features

This example uses only `record` and pattern matching for `instanceof`, **without** pattern switch or record deconstruction. Save it as **`FinalSeventeenDemo.java`**:

```java
public class FinalSeventeenDemo {
    record Account(String code) {}

    static String label(Object input) {
        if (input instanceof Account a && a.code() != null) {
            return "ACCOUNT=" + a.code();
        }
        return "OTHER";
    }

    public static void main(String[] args) {
        System.out.println(label(new Account("A01")));
        System.out.println(label(new Account(null)));
        System.out.println(label(null));
    }
}
```

Compile for Java 17:

```bash
javac --release 17 -encoding UTF-8 FinalSeventeenDemo.java
java FinalSeventeenDemo
```

**Exact stdout:**

```text
ACCOUNT=A01
OTHER
OTHER
```

What is verified here?

1. `Account` is a **final** record feature in Java 17.
2. `input instanceof Account a` is a type pattern that has been **final** since Java 16.
3. `a.code() != null` is evaluated after `instanceof` succeeds thanks to short-circuit `&&`; if `input == null`, the first condition evaluates to false.
4. A record can hold a `null` reference component if the constructor does not forbid it; that is why `a.code() != null` still matters.

This program was compiled with `javac --release 17` and executed successfully on a newer JDK capable of running Java 17 bytecode.

## 5. Java 21: Final Record Patterns and Pattern Switch

Save the following program as **`FinalPatternCompatibilityDemo.java`**. It combines a `sealed interface`, records, record patterns, type/component patterns, `when` guards, `case null`, and an `instanceof` check.

```java
public class FinalPatternCompatibilityDemo {
    sealed interface Event permits Text, Amount, Pair {}
    record Text(String value) implements Event {}
    record Amount(int cents) implements Event {}
    record Pair(Event first, Event second) implements Event {}

    static String describe(Event input) {
        return switch (input) {
            case null -> "NULL_SELECTOR";
            case Text(var value) when value == null -> "TEXT_NULL";
            case Text(var value) when value.isBlank() -> "TEXT_BLANK";
            case Text(String value) -> "TEXT=" + value;
            case Amount(int cents) when cents < 0 -> "NEGATIVE=" + cents;
            case Amount(var cents) -> "AMOUNT=" + cents;
            case Pair(Text(var text), Amount(var cents)) ->
                    "PAIR=" + text + ":" + cents;
            case Pair(var first, var second) -> "OTHER_PAIR";
        };
    }

    static String describeIf(Object input) {
        if (input instanceof Text(var text)
                && text != null
                && !text.isBlank()) {
            return "IF=" + text;
        }
        return "IF_OTHER";
    }

    public static void main(String[] args) {
        System.out.println("null=" + describe(null));
        System.out.println("missing=" + describe(new Text(null)));
        System.out.println("blank=" + describe(new Text("  ")));
        System.out.println("text=" + describe(new Text("Java")));
        System.out.println("negative=" + describe(new Amount(-1)));
        System.out.println("zero=" + describe(new Amount(0)));
        System.out.println("nested=" + describe(
                new Pair(new Text("A"), new Amount(3))));
        System.out.println("other-pair=" + describe(
                new Pair(null, new Amount(3))));
        System.out.println(describeIf(new Text("Ready")));
        System.out.println(describeIf(new Text(null)));
    }
}
```

Run with a JDK that supports Java 21:

```bash
javac --release 21 -encoding UTF-8 FinalPatternCompatibilityDemo.java
java FinalPatternCompatibilityDemo
```

**There is no `--enable-preview` flag in either command.**

**Exact stdout:**

```text
null=NULL_SELECTOR
missing=TEXT_NULL
blank=TEXT_BLANK
text=TEXT=Java
negative=NEGATIVE=-1
zero=AMOUNT=0
nested=PAIR=A:3
other-pair=OTHER_PAIR
IF=Ready
IF_OTHER
```

Explanation in relation to the final status:

- `case Text(var value)` and `case Pair(Text(var text), Amount(var cents))` use **record patterns**, final from Java 21.
- `case ... when ...` uses **pattern switch guards**, part of the final Java 21 feature.
- `case null` is the explicit way to handle a null selector; if a switch only has patterns that do not handle null, a null selector can cause a `NullPointerException`.
- `Text(var value)` can bind a `null` component, because `var` is an unconditional component pattern for the declared type. Therefore, the `value == null` case must come before `value.isBlank()` to avoid an NPE.
- `Pair(Text(...), Amount(...))` only matches when both nested records to be deconstructed exist and have the right types. `Pair(null, new Amount(3))` falls through to `Pair(var first, var second)` and returns `OTHER_PAIR`.
- `sealed Event` together with its three `final` subtypes makes the `switch expression` exhaustive for the defined cases, without needing a `default` that would hide new subtypes.
- `describeIf` shows that `instanceof` and `&&` still apply flow scoping with record patterns in Java 21.

The program above was verified with `javac --release 21` and ran successfully with the exact ten lines of output.

## 6. Historical Illustration: Pattern Switch Still in Preview in Java 17

To see the difference, consider **Java 17**, when pattern matching for `switch` **was not yet final**. The following sample uses only type patterns in `case`, without record patterns. Save it as **`PreviewSwitch17.java`** if you want to run it in an actual **JDK 17** environment:

```java
public class PreviewSwitch17 {
    static String label(Object value) {
        return switch (value) {
            case null -> "missing";
            case String text -> "string=" + text;
            case Integer number -> "integer=" + number;
            default -> "other";
        };
    }

    public static void main(String[] args) {
        System.out.println(label("Java"));
        System.out.println(label(7));
        System.out.println(label(null));
    }
}
```

In **JDK 17**, use:

```bash
javac --enable-preview --release 17 -encoding UTF-8 PreviewSwitch17.java
java --enable-preview PreviewSwitch17
```

**Expected output on a matching JDK 17:**

```text
string=Java
integer=7
missing
```

This is a **historical compatibility example for Java 17 preview syntax**; it was not executed in the current verification run because the environment uses a JDK 24 compiler, not a JDK 17 compiler. The **final** Java 17 example in Section 4 and the **final** Java 21 example in Section 5 are the two programs that were actually compiled and run.

If you forget `--enable-preview` when compiling with JDK 17, the compiler may report that patterns in switch are a preview feature and preview is not enabled. If you compiled code that **actually uses** preview features but forgot the flag at runtime, the JVM may refuse to load the class because preview is not enabled.

**Do not take `PreviewSwitch17.java` and add Java 21 record patterns to it** expecting it to run on JDK 17. Record patterns were not supported in that release, even with preview enabled.

## 7. Why Does Enabling Preview Still Fail?

### --enable-preview is tied to the current source version

The `--enable-preview` flag is not a "backward-compatibility flag for all past previews." For a compiler in a newer Java release, `--enable-preview` only applies the preview features of **the source version that compiler supports for experimentation**.

An example verified with **`javac 24.0.2`**:

```bash
javac --enable-preview --release 21 FinalPatternCompatibilityDemo.java
```

The JDK 24 compiler rejects it with the key message:

```text
error: invalid source release 21 with --enable-preview
  (preview language features are only supported for release 24)
```

Reason: `--release 21` requests the Java 21 source level, whereas `--enable-preview` on that compiler only enables preview for level 24. **This is an invalid flag-combination error**, not an indication that record patterns or pattern switch are still in preview in Java 21.

To compile features that are **already final** in Java 21 using JDK 24, use:

```bash
javac --release 21 FinalPatternCompatibilityDemo.java
```

And if you genuinely need a preview feature of JDK 24, you must use the preview configuration **matching JDK 24**, along with the corresponding runtime environment — you cannot lower `--release` to 21 to try to use new preview syntax.

### Preview class runtimes also have version requirements

For a **class file marked with preview** (using a preview feature), the JVM must have preview enabled and match the corresponding feature version. You should not assume preview bytecode from an older JDK will run on every newer JDK like a normal final class. Preview class files use a **special class-file minor version `65535`** so the JVM can distinguish them.

Therefore, in projects using preview, check **both the actual javac and java being invoked**, not just the Maven/Gradle configuration values.

```bash
java -version
javac -version
```

Make sure both tools belong to the same JDK matching the preview feature in use. Switching machines or upgrading a CI image can make a historical preview command invalid.

## 8. --release, --source, --target, and Runtime: Do Not Equate Them

These options serve different purposes:

| Option / tool | Primary role | Notes |
| --- | --- | --- |
| `javac --release N` | Compiles with the language rules, class-file target, and platform APIs of Java `N` when supported by the compiler | Suitable for building artifacts that run on Java `N` |
| `javac --source N` | Selects the source syntax/semantics level | Used alone, does not guarantee restriction to Java `N` APIs |
| `javac --target N` | Selects the class-file version | Does not downgrade syntax/APIs or replace `--release` |
| `javac --enable-preview` | Enables preview for the permitted compiler/source version | Must match the exact version; does not re-enable all historical previews |
| `java --enable-preview` | Allows the JVM to run classes requiring preview with the matching version | Does not replace the compile-time flag |
| `java -version` | Shows the actual JVM version used at runtime | May differ from `javac -version` if PATH/JAVA_HOME are misaligned |

**Source compatibility example:** JDK 24 can use `javac --release 17` to compile the program in Section 4, and `javac --release 21` to compile the program in Section 5. That does **not** make Java 21 features valid when `--release 17` is set.

**Runtime compatibility example:** a class file built with a normal Java 21 target requires a runtime that supports the Java 21 class-file version or higher. If you try to run it on an older JDK, you will typically get `UnsupportedClassVersionError`. Enabling `--enable-preview` does not solve a runtime that is too old for that class-file version.

**Recommendation:** For a library/app deployed to Java 17, build and test with `--release 17`. If you want to use final pattern switch, a plan to raise the minimum version to Java 21 must be evaluated together with CI/production runtimes and dependencies, not just by changing a single flag.

## 9. Migration: From Preview Code to Final Code

Suppose a project used preview pattern switch on JDK 17, 18, 19, or 20. When upgrading to Java 21, follow this process:

1. **Identify the starting preview release.** Read `pom.xml`/`build.gradle` in the actual project and the JDK toolchain version, while also inspecting the source syntax. The installed JDK is not necessarily the build language level.
2. **Check the JEP of that exact release.** Changes between preview rounds can affect guards, supported pattern types, variable scoping, label ordering, null handling, or exhaustiveness.
3. **Update source code to Java 21 final syntax.** For switch, review `case` branches, `when` guard syntax, `case null`, and narrow → broad case ordering. For record patterns, review deconstruction and null components.
4. **Set the compiler release to 21** and compile **without preview** to ensure no old preview dependencies remain:
   `javac --release 21 ...`.
5. **Fix genuine compilation errors** such as dominated cases or non-exhaustive switch expressions. Do not just add a broad `default` to hide new subtypes in a sealed hierarchy.
6. **Update tests and packaging as well.** If `--enable-preview` was previously configured for compilation, testing, running the app, or the IDE, check each place and remove the flag once preview is no longer used. If the project still uses **another feature that is still in preview** on the target JDK, do not remove it blindly.
7. **Run regression tests** with null selectors, type patterns, subtypes, true/false guards, null record components, and boundary values. New syntax may compile while business branches still change if you reorder cases.
8. **Verify the production runtime.** Do not compile with `--release 21` and deploy to a Java 17 runtime. Ensure CI, containers, servers, and user environments have Java 21 or newer as required by the application.

### When a project cannot yet upgrade from Java 17

You should not force **record patterns** or **final pattern switch** into Java 17 source code. You can still apply **type patterns in `instanceof`** (already final), `record`, and `sealed` (both final in Java 17), and use `if/else if` or the Visitor pattern to dispatch on data. This is a stable design path when deployment constraints require Java 17.

## 10. Common Situations in Build Tools and CI

### Works in the IDE but fails in CI

Check three parameters:

- **JDK used to compile**: `javac -version` in CI.
- **Language level**: `--release`/source compatibility from the build configuration.
- **Runtime used for testing and running**: `java -version`, JVM arguments, IDE/build-tool toolchain.

For example: the developer machine has JDK 24 and the source uses record patterns, while CI builds with `--release 17`. Code valid in Java 21 is still invalid at the Java 17 source level. Dismissing this error as "just missing `--enable-preview`" is a misdiagnosis.

### With Maven/Gradle

If you truly use a JDK's preview features, you must configure preview **both in the compiler and in the JVM of test/run tasks**, and lock the appropriate JDK toolchain. The exact declaration depends on the Maven/Gradle plugin version and pipeline; do not assume setting a source compatibility property alone is enough.

If you use **Java 21 final pattern matching**, the configuration should focus on **a Java 21+ toolchain and `--release 21`**, with no preview flag needed just because the syntax contains patterns.

### Libraries distributed to multiple consumer groups

State the **minimum supported Java version** in the product documentation. Avoid publishing artifacts containing Java 21 bytecode or APIs if the library commits to still running on Java 17. Split modules, provide another version, or defer using new syntax if a lower runtime must be maintained.

Preview features should be tested in a controlled way, not implicitly treated as a stable API/source contract for all library consumers.

## 11. Common Errors and Root Cause Table

| Symptom | Common cause | Appropriate action |
| --- | --- | --- |
| Compiler reports pattern switch is a preview feature | Compiling source with switch patterns on a Java version where it was still preview, without enabling preview | Choose the matching JDK and `--enable-preview` flag for that version, or upgrade to Java 21 final |
| `invalid source release N with --enable-preview` | Trying to enable preview for a release other than the preview release supported by the current compiler | Remove the flag if the feature is already final in `N`; if a real preview is needed, change the toolchain/release accordingly |
| `UnsupportedClassVersionError` at runtime | Runtime is too old to read the compiled class-file version | Run with a sufficiently new JDK or rebuild at a supported target |
| JVM reports preview features are not enabled | Running a class compiled with preview without the runtime flag | Use the matching JDK and `java --enable-preview` |
| `Point(var x, var y)` does not compile under `--release 17` | Record patterns are not a Java 17 feature | Use Java 21+ or write Java 17-compatible accessors/type patterns |
| `when` syntax fails in older preview code | Preview syntax/semantics changed across JDKs | Read the JEP for the source version and update the code when upgrading |
| `this case label is dominated by a preceding case label` | A broad branch shadows a specific branch, violating dominance | Place specific branches/appropriate guards before broad branches |
| Switch expression is not exhaustive | Missing branch covering the selector type (especially when a sealed hierarchy changes) | Add meaningful cases; do not use `default` mechanically to bypass checking |
| `NullPointerException` in switch | Null selector without `case null`, or a component pattern binding null gets dereferenced | Distinguish the two levels of null; place cases/guards properly |
| Code runs in IDE but fails in CI | Different JDK, `--release`, or preview/test arguments across environments | Check the actual toolchain and lock the configuration |

**Note on error messages:** exact diagnostics depend on the JDK and source version. Read the message alongside the source line, compiler version, and flags; do not treat the exact wording of one JDK release as a universal rule.

## 12. Compatibility Testing with a Small Matrix

A useful compatibility check:

| Java source | Compile level | Expectation |
| --- | --- | --- |
| `FinalSeventeenDemo.java` (Section 4) | `--release 17` with a supporting compiler | **Compiles**, no preview |
| `FinalPatternCompatibilityDemo.java` (Section 5) | `--release 21` with a supporting compiler | **Compiles**, no preview |
| Java 21 source using record patterns | `--release 17` | **Invalid** for Java 17 |
| Java 17 preview switch (Section 6) | `--enable-preview --release 17` on JDK 17 | Can compile/run preview with flags in both phases |
| `--enable-preview --release 21` on JDK 24 compiler | JDK 24 | **Flag-combination error** because preview only supports the compiler's level 24 |

The two **final** rows were actually compiled and run with `javac 24.0.2` using `--release 17` and `--release 21` respectively. The `--enable-preview --release 21` mismatch scenario was also verified on that compiler. The JDK 17 preview row is a historical guide based on the feature design and was not executed in the available JDK 24 environment.

When working in a team, you should automate a **compatibility matrix in CI**: at minimum, compile against the committed release, run tests on the minimum runtime, and also test on a newer JDK if the system requires supporting it.

## 13. Common Mistakes

1. **Thinking all pattern matching is in preview.** `instanceof` type patterns became final in Java 16; record patterns and switch patterns became final in Java 21.
2. **Thinking `record` and `record pattern` are one feature.** Declaring a `record` became final in Java 16, while deconstructing a record with a pattern became final in Java 21.
3. **Using `--enable-preview` to "upgrade" Java 17 to Java 21.** This flag does not unlock features that do not exist in JDK 17.
4. **Enabling preview with an older `--release` on a newer compiler.** The preview flag must match the source/release permitted by that compiler; a mismatch is a compilation error.
5. **Only enabling preview at compile time.** Code that actually uses preview features may also need the runtime flag `java --enable-preview` with a matching JDK.
6. **Assuming preview source is stable across releases.** Guard syntax and pattern switch rules went through revisions; review them when upgrading JDKs.
7. **Removing the preview flag without checking other features still in preview.** A project may use multiple different features with separate statuses.
8. **Reading the JDK version from the IDE instead of the CI compiler.** PATH, JAVA_HOME, Maven/Gradle toolchains, and the actual runtime may not match.
9. **Confusing class-file version with source version.** `--source` and `--target` alone are not equivalent to `--release`.
10. **Assuming code that is final in Java 21 is also valid in Java 17.** Final status only takes effect from the release in which that feature was standardized onward.
11. **Assuming `default` covers null.** Pattern switch has its own null-selector policy; `case null` or a guard before the switch is needed if business logic requires it.
12. **Adding `default` to avoid exhaustive cases.** It can hide errors when a new `sealed` subtype is added. Always check the domain meaning.
13. **Putting historical preview code into a production library without locking the toolchain.** That creates compatibility risks when deployment environments change.
14. **Only testing the happy path when migrating preview → final.** Also test null selectors, null record components, true/false guards, subtypes, and dominated cases.

## 14. Self-Check Questions

**Question 1.** A project targets Java 17. Can it use `if (input instanceof String text)`? Is `--enable-preview` required?

*Answer:* Yes, it can be used; type patterns for `instanceof` have been final since Java 16. On Java 17, no preview flag is needed for this feature.

**Question 2.** A project uses Java 17 and has declared `record Point(int x, int y) {}`. Can it use `case Point(int x, int y) -> ...` as a final feature?

*Answer:* No. `record` became final in Java 16, whereas record patterns became final in Java 21. You need to raise the language level to Java 21 or switch to another approach compatible with Java 17.

**Question 3.** Using JDK 24 and running `javac --enable-preview --release 21`. Why does it fail even though pattern switch is final in Java 21?

*Answer:* The preview flag of the JDK 24 compiler cannot be used with `--release 21`. Since pattern switch is already final, if the source only uses final Java 21 features, **remove `--enable-preview`** and compile with `--release 21`.

**Question 4.** When running a class that uses a JDK 17 preview feature, is enabling `--enable-preview` at compile time enough?

*Answer:* No. You must run with the JDK matching that preview and pass `java --enable-preview` so the JVM allows the preview-marked class; otherwise, the class may be rejected.

**Question 5.** Why can't you be sure Java 17 preview code will run as-is on Java 21 after removing the preview flag?

*Answer:* Because preview features can change syntax and semantics across multiple JEPs. You must update the source to match the final Java 21 specification and run the regression test suite.

**Question 6.** If a library API commits to running on Java 17, but you want to use Java 21 record patterns, what must be decided first?

*Answer:* You must choose between raising the **minimum runtime/source version** (and updating the support commitment), or staying on Java 17 and using a compatible implementation; you cannot keep `--release 17` and use final Java 21 record patterns as if they were a Java 17 feature.

## 15. Official Documentation

- [JEP 305 – Pattern Matching for instanceof (Preview, Java 14)](https://openjdk.org/jeps/305)
- [JEP 375 – Pattern Matching for instanceof (Second Preview, Java 15)](https://openjdk.org/jeps/375)
- [JEP 394 – Pattern Matching for instanceof (Final, Java 16)](https://openjdk.org/jeps/394)
- [JEP 405 – Record Patterns (Preview, Java 19)](https://openjdk.org/jeps/405)
- [JEP 432 – Record Patterns (Second Preview, Java 20)](https://openjdk.org/jeps/432)
- [JEP 440 – Record Patterns (Final, Java 21)](https://openjdk.org/jeps/440)
- [JEP 406 – Pattern Matching for switch (Preview, Java 17)](https://openjdk.org/jeps/406)
- [JEP 420 – Pattern Matching for switch (Second Preview, Java 18)](https://openjdk.org/jeps/420)
- [JEP 427 – Pattern Matching for switch (Third Preview, Java 19)](https://openjdk.org/jeps/427)
- [JEP 433 – Pattern Matching for switch (Fourth Preview, Java 20)](https://openjdk.org/jeps/433)
- [JEP 441 – Pattern Matching for switch (Final, Java 21)](https://openjdk.org/jeps/441)
- [JEP 12 – Preview Features (process for enabling and using preview features)](https://openjdk.org/jeps/12)
- [Oracle Java 21 – Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Oracle Java 21 – Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [Java Language Specification 21 – Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30)
