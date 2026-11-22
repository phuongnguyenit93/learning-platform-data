# Version Milestones of Pattern Matching for instanceof in Java

## 1. Learning Objectives

In the **Java Compatibility** category, the question “Which Java version supports `instanceof` with a pattern variable?” must be answered according to **the exact release milestones**: a feature may appear in *preview* status before officially becoming a stable language feature. Reading code on a Java 11, 14, 15, 16, or 21 project without distinguishing these milestones easily leads to compilation errors or wrong conclusions about upgrade requirements.

After this lesson, you will be able to:

- Recall the exact milestone sequence: **JDK 14 — first preview (JEP 305), JDK 15 — second preview (JEP 375), JDK 16 — final (JEP 394)**.
- Distinguish the traditional `instanceof` operator from **type pattern** syntax such as `obj instanceof String text`.
- Choose the right way to compile and run preview code on **that exact historical JDK**, and know when `--enable-preview` is not needed.
- Understand the meaning of `javac --release` compared to the installed JDK version and the deployed JVM version.
- Avoid conflating **pattern matching for instanceof** with **record patterns** or **pattern matching for switch**, which were finalized in Java 21.
- Diagnose migration errors related to source compatibility, APIs, and the scope of pattern variables.

**Key takeaway:** The `obj instanceof String text` syntax has been a **stable feature since Java 16**. Java 14–15 had preview versions and should not be presented as official releases equivalent to Java 16.

## 2. The Legacy instanceof Operator and Type Patterns Are Two Different Levels

The classic way, usable on very old Java versions:

```java
if (value instanceof String) {
    String text = (String) value;
    System.out.println(text.length());
}
```

The **pattern matching for instanceof** way:

```java
if (value instanceof String text) {
    System.out.println(text.length());
}
```

Both check at runtime whether `value` is non-null and has a type compatible with `String`. What is new in the pattern is **combining the type check and the declaration/binding of the checked variable**, eliminating the manual cast.

In the old form, `instanceof String` has existed for a very long time; in the new form, **`String text` is a type pattern**. Therefore, saying “Java 8 has `instanceof`” **does not mean** “Java 8 has pattern matching for `instanceof`”.

This is a valuable syntactic and type-checking improvement: the author cannot accidentally check one type and cast to another in the same code block, and the compiler knows where `text` is definitely bound (*flow scoping*).

## 3. Standard Timeline: JDK 14 → 15 → 16

| Version | Status of pattern matching for instanceof | JEP | Interpretation |
|---|---|---|---|
| **Java 13 and earlier** | This type pattern syntax does not exist in standard Java | — | Use traditional `instanceof` + cast |
| **Java 14** | **First preview** | **JEP 305** | Must explicitly enable preview when compiling/running on JDK 14 |
| **Java 15** | **Second preview** | **JEP 375** | Continues in preview; essentially unchanged in functionality compared to the Java 14 preview |
| **Java 16** | **Final / permanent** | **JEP 394** | Use `instanceof T t` without enabling preview |
| **Java 17** | Remains an official feature | JEP 394 already finalized earlier | Use normally in Java 17 applications |
| **Java 21** | Remains an official feature; pattern system is further expanded | JEP 394, along with JEP 440/441 in other areas | Type patterns work normally; adds official record patterns and pattern switch |

Easy-to-remember milestones:

**14 → preview, 15 → second preview, 16 → final.**

It does not mean “pattern matching for `instanceof` only arrived in Java 21.” Java 21 is the milestone for stable **record patterns** and **pattern matching for `switch`**, whereas simple type patterns in `instanceof` have been ready since Java 16.

### 3.1. JDK 14 — JEP 305 (First Preview)

JEP 305 introduced a way to test and extract a properly typed variable using a type pattern:

```java
if (obj instanceof String s) {
    System.out.println(s.length());
}
```

At the time of Java 14, this was a **preview language feature**. The syntax was not yet a permanent language commitment; preview had to be enabled and the exact JDK supporting that preview had to be used. This mechanism was released to gather feedback and refine the language before standardization.

### 3.2. JDK 15 — JEP 375 (Second Preview)

JEP 375 placed the feature into a **second preview**, following JDK 14. Oracle documentation confirms that the `instanceof` pattern feature in this preview had **no significant semantic changes compared to Java 14**.

Even though a code snippet may look identical between 14 and 15, running in preview mode requires using tools matching **the corresponding JDK version**. Do not take preview classfiles compiled on JDK 14 and run them on JDK 15/16 expecting compatibility.

### 3.3. JDK 16 — JEP 394 (Final)

JEP 394 standardized the feature. Starting from Java 16, simple code:

```java
if (obj instanceof String s) {
    System.out.println(s.toUpperCase());
}
```

compiles and runs **without `--enable-preview`**. If a project needs this feature, Java 16 is the minimum milestone for **stable type pattern syntax**.

Two notable changes when moving from preview to final:

1. Pattern variables **are no longer treated as implicitly final**. When within a valid scope, a pattern variable can be reassigned just like an ordinary local variable, although overusing this is discouraged because it makes code harder to read.
2. The type-checking rules for `instanceof` patterns in Java 16 reject certain type tests that the compiler considers unnecessary because **the static type of the selector is already a subtype of the pattern type**. Applicability rules continued to evolve in later releases; do not use Java 16's error message to claim that every later version behaves identically (see Section 9).

The first point is verified in the main program: `text = text.trim()` compiles successfully with `--release 16`. Do not confuse “not implicitly final” with a pattern variable existing in any arbitrary scope; **flow scoping still applies**.

## 4. Enable Preview for the Right Version; Do Not Misuse javac

### 4.1. On a Real JDK 14

Suppose you are using **JDK 14** and have a file `PreviewInstanceofDemo.java`:

```java
public class PreviewInstanceofDemo {
    static String describe(Object value) {
        if (value instanceof String text) {
            return "TEXT:" + text.length();
        }
        return "OTHER";
    }

    public static void main(String[] args) {
        System.out.println(describe("Java"));
        System.out.println(describe(null));
    }
}
```

Run the commands **on the JDK 14 toolchain**, inside the directory containing the file:

```bash
javac --enable-preview --release 14 PreviewInstanceofDemo.java
java --enable-preview PreviewInstanceofDemo
```

Or use `--source 14` with `--enable-preview` where appropriate. The `--enable-preview` flag is **mandatory on Java 14** to use preview syntax; if omitted, the compiler rejects the feature when compiling for source release 14.

**This is historical usage**, not a recommendation to use JDK 14 in new applications. The JDK 14 preview commands are not claimed to have been executed on JDK 14 in the verification environment of this lesson.

### 4.2. On a Real JDK 15

With the same demo source code, using the **JDK 15 toolchain**:

```bash
javac --enable-preview --release 15 PreviewInstanceofDemo.java
java --enable-preview PreviewInstanceofDemo
```

On Java 15, the `instanceof` pattern is still a preview feature. Simply changing the number in `--release` while using a different JDK is **not enough** to emulate a historical preview release.

**Important explanation:** A modern `javac` such as JDK 21 only allows enabling preview features of **the exact release that this javac supports**; `javac 21 --enable-preview --release 15` does not mean “JDK 15 preview”. A test with JDK 21 in this lesson recorded the following result:

```text
javac --enable-preview --release 15
error: invalid source release 15 with --enable-preview
```

The message may vary slightly depending on the JDK/IDE, but the essence is that **you cannot use a newer compiler to re-enable preview features of an older release**.

### 4.3. From JDK 16 Onward

When using only type patterns for `instanceof` with the standardized syntax:

```bash
javac --release 16 InstanceofMilestonesDemo.java
java InstanceofMilestonesDemo
```

Do not add `--enable-preview`. The feature is official in Java 16 so preview does not need to be enabled, even when the source code is compiled by a newer JDK that supports targeting Java 16.

Note that **`--release 16` is an option targeting Java 16 APIs and classfiles**; it does not install JVM 16 for you. If you build on a machine using JDK 21 and run on JVM 21, that test confirms source compatibility with Java 16, **not** direct execution on a JDK 16 runtime.

## 5. Java Example Compilable with --release 16

Create the file **`InstanceofMilestonesDemo.java`**:

```java
import java.util.Objects;
import java.util.Locale;

public class InstanceofMilestonesDemo {
    static String legacy(Object input) {
        if (input instanceof String) {
            String text = (String) input;
            return "TEXT:" + text.length();
        }
        return "OTHER";
    }

    static String modern(Object input) {
        if (input instanceof String text) {
            return "TEXT:" + text.length();
        }
        return "OTHER";
    }

    static String nonBlank(Object input) {
        return input instanceof String text && !text.isBlank()
                ? "NONBLANK:" + text.length() : "NO";
    }

    static String guardClause(Object input) {
        if (!(input instanceof String text)) {
            return "NOT_STRING";
        }
        return "UPPER:" + text.toUpperCase(Locale.ROOT);
    }

    static String reassignPatternVariable(Object input) {
        if (input instanceof String text) {
            text = text.trim();
            return "TRIM:" + text;
        }
        return "NOT_STRING";
    }

    static void verify(String label, Object input, String expected,
            String expectedNonBlank, String expectedGuard, String expectedTrim) {
        String before = legacy(input);
        String after = modern(input);
        String predicate = nonBlank(input);
        String guarded = guardClause(input);
        String trimmed = reassignPatternVariable(input);
        if (!Objects.equals(before, expected)
                || !Objects.equals(after, expected)
                || !Objects.equals(predicate, expectedNonBlank)
                || !Objects.equals(guarded, expectedGuard)
                || !Objects.equals(trimmed, expectedTrim)) {
            throw new AssertionError(label + ": " + before + "/" + after
                + "/" + predicate + "/" + guarded + "/" + trimmed);
        }
        System.out.println(label + " => " + after + ", "
                + predicate + ", " + guarded + ", " + trimmed);
    }

    public static void main(String[] args) {
        verify("null", null, "OTHER", "NO", "NOT_STRING", "NOT_STRING");
        verify("integer", Integer.valueOf(4), "OTHER", "NO", "NOT_STRING", "NOT_STRING");
        verify("simple", "Java", "TEXT:4", "NONBLANK:4", "UPPER:JAVA", "TRIM:Java");
        verify("spaced", " Java ", "TEXT:6", "NONBLANK:6", "UPPER: JAVA ", "TRIM:Java");
        verify("empty", "", "TEXT:0", "NO", "UPPER:", "TRIM:");
        verify("blank", "  ", "TEXT:2", "NO", "UPPER:  ", "TRIM:");
    }
}
```

### Compile and Run

With JDK 16+ supporting the `--release 16` option:

```bash
javac --release 16 InstanceofMilestonesDemo.java
java InstanceofMilestonesDemo
```

**Verified stdout:**

```text
null => OTHER, NO, NOT_STRING, NOT_STRING
integer => OTHER, NO, NOT_STRING, NOT_STRING
simple => TEXT:4, NONBLANK:4, UPPER:JAVA, TRIM:Java
spaced => TEXT:6, NONBLANK:6, UPPER: JAVA , TRIM:Java
empty => TEXT:0, NO, UPPER:, TRIM:
blank => TEXT:2, NO, UPPER:  , TRIM:
```

Each call to `verify(...)` compares the results of the legacy cast code, the type pattern code, and its variants against **independent expected values**; if any differ, the program throws an `AssertionError`. It also demonstrates:

- `instanceof` returns false when the input is null or the wrong type: no method is invoked on an unbound variable.
- `&&` ensures `text.isBlank()` only runs after the `String` pattern matches.
- The pattern variable `text` can be used after a negated guard clause because the non-matching branch executes `return`.
- Starting in Java 16+, the pattern variable `text` may be reassigned within its valid scope; after `trim()`, the output can differ in length or original value.
- Empty and whitespace-only strings produce different results from regular strings even though the type pattern matches in all those cases.

### Verified Build Matrix

Using the JDK 21 compiler on the same program, the results are:

| Command | Result | Meaning |
|---|---|---|
| `javac --release 14 InstanceofMilestonesDemo.java` | **Rejected** | Type patterns are preview in 14; moreover, the program intentionally reassigns a pattern variable, which was not allowed in older previews |
| `javac --release 15 InstanceofMilestonesDemo.java` | **Rejected** | Type patterns are still preview in 15 |
| `javac --release 16 InstanceofMilestonesDemo.java` | **PASS** | Syntax is stable starting in Java 16 |
| `javac --release 17 InstanceofMilestonesDemo.java` | **PASS** | Java 17 compatible |
| `javac --release 21 InstanceofMilestonesDemo.java` | **PASS** | Java 21 compatible |

All PASS builds were executed on the same JDK 21 runtime in the verification environment and produced identical stdout. Do not interpret this test as having launched actual JVM 14, 15, 16, or 17 runtimes. To test on the actual target JDK runtime, use the corresponding JDK/container in CI.

**Caution:** You cannot use **this exact program with pattern variable reassignment** to demonstrate the 14/15 preview because some rules changed when JEP 394 was standardized. When testing preview syntax on JDK 14/15, use `PreviewInstanceofDemo.java` from Section 4.

## 6. Before Java 16: Legacy Cast Remains the Compatible Choice

If a project requires **Java 8 or Java 11**, you can keep the traditional syntax:

```java
public class LegacyOnlyDemo {
    static String size(Object value) {
        if (value instanceof String) {
            String s = (String) value;
            return "LENGTH:" + s.length();
        }
        return "OTHER";
    }
    public static void main(String[] args) {
        System.out.println(size("Java"));
        System.out.println(size(null));
    }
}
```

The filename is **`LegacyOnlyDemo.java`**. This code does not use pattern matching for `instanceof`, only the traditional `instanceof` operator:

```bash
javac --release 8 LegacyOnlyDemo.java
java LegacyOnlyDemo
```

**Verified stdout** using the JDK 21 compiler targeting `--release 8` and the JDK 21 runtime:

```text
LENGTH:4
OTHER
```

A modern JDK may warn about overly old source/target options, but the program still compiles. For production projects, choosing a supported version must also consider the maintenance/security patch lifecycle, not just whether the compiler accepts the syntax.

### Should You “Polyfill” Type Patterns for Java 8?

No ordinary Java library can make JDK 8 understand the `instanceof String s` language syntax before compilation. You must **rewrite the source code to the old syntax**, use a code transformation tool with its own build pipeline, or **raise the source level**. Simply adding a dependency does not change the parser of `javac --release 8`.

## 7. Java 21: Distinguish Type Patterns from Other Pattern Features

Not all syntaxes containing the word “pattern” were standardized in the same version.

| Feature | Syntax example | Official milestone |
|---|---|---|
| **Pattern matching for `instanceof` with type patterns** | `obj instanceof String s` | **Java 16** (JEP 394) |
| **Pattern matching for `switch`** | `case String s -> ...` | **Java 21** (JEP 441) |
| **Record patterns** | `obj instanceof Label(String name)` | **Java 21** (JEP 440) |

Before becoming official features, the other constructs had their own preview stages: pattern matching for `switch` began previewing in Java 17, while record patterns began previewing in Java 19. However, **do not transfer those milestones onto `instanceof` type patterns**.

### Java 21 Demonstration for Comparison Only

Create the file **`LaterFeaturesDemo.java`**:

```java
public class LaterFeaturesDemo {
    record Label(String name) {}

    static String describe(Object source) {
        return switch (source) {
            case null -> "NULL";
            case Label(String name) -> "LABEL:" + name;
            case String text -> "STRING:" + text;
            default -> "OTHER";
        };
    }

    public static void main(String[] args) {
        Object item = new Label("Java 21");
        System.out.println("record pattern -> "
                + (item instanceof Label(String name)));
        System.out.println(describe(item));
        System.out.println(describe(new Label(null)));
        System.out.println(describe("text"));
        System.out.println(describe(null));
    }
}
```

Compile and run:

```bash
javac --release 21 LaterFeaturesDemo.java
java LaterFeaturesDemo
```

**Verified stdout:**

```text
record pattern -> true
LABEL:Java 21
LABEL:null
STRING:text
NULL
```

This program **cannot compile with `--release 16`** because it uses record patterns and pattern switch, which only became official in Java 21. Thus, even though `item instanceof Label(String name)` contains `instanceof`, recognizing that a **record pattern** differs from the type pattern `item instanceof Label label` is essential when determining the minimum Java milestone.

The `Label` record must exist and be non-null for the pattern to deconstruct it; however, the `name` component is a nullable `String`, so `Label(String name)` in the context of record deconstruction can bind `null`. This is the semantics of Java 21 record patterns and should not be used to infer the behavior of all Java 16 type patterns.

## 8. Source, javac, Classfile, and JVM: Four Different Concepts

A team often says “the project runs on Java 17,” but you need to separate:

1. **JDK/compiler in use:** the version of the `javac` program actually running. It determines the supported releases and the preview features of that specific JDK.
2. **Source language level:** the syntax version that the source code is allowed to use. With `--release 16`, official type patterns are valid, whereas Java 21 record patterns are invalid.
3. **API and classfile target:** `--release N` simultaneously restricts public APIs and produces classfiles compatible with Java N (when the compiler supports N).
4. **Runtime JVM:** the virtual machine version actually loading and executing the classfiles. A JVM that is too old cannot run classfiles targeting a newer Java version.

Example:

```bash
# JDK 21 compiles source/API/bytecode for Java 16:
javac --release 16 InstanceofMilestonesDemo.java

# Check the Java runtime installed on the machine:
java -version

# Check the compiler version:
javac -version
```

The snippet above generates classfiles targeting Java 16, yet `java -version` may still report Java 21. To test on a real Java 16 runtime, you must run it using Java 16 in that environment.

### Practical Migration Matrix

| Deployment requirement | Chosen source pattern for instanceof | Conclusion |
|---|---|---|
| Java 8/11 runtime, no transpiler | Old syntax with cast | Do not write `instanceof T t` at that source level |
| Matching JDK 14/15 toolchain, testing preview | Type pattern with `--enable-preview` | For historical experimentation only; requires the corresponding preview runtime |
| Source/target from Java 16 | Stable type pattern | No preview needed |
| Source/target Java 17 | Stable type pattern | Use normally; does not imply record patterns are available |
| Source/target Java 21 | Type pattern, record pattern, switch pattern | All three can be used according to their respective JEPs |

Also note: new language features do not automatically make compiled code backward-compatible with older JVMs. Converting classfiles or changing runtime flags will not make a JVM 8 understand bytecode compiled for 16/21.

### Build Tool Configuration Examples

If a Maven project has a compatible Maven Compiler Plugin, a clear source/API/bytecode configuration is:

```xml
<properties>
    <maven.compiler.release>16</maven.compiler.release>
</properties>
```

Or Gradle with Java Toolchains:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(16)
    }
}
```

These two snippets are **illustrative configuration examples**, not runnable Java programs, and are not necessarily suitable for every repository. Maven `release` requires a JDK compiler that supports that target; Gradle Toolchains require the corresponding JDK to be present or provisioned and a sufficiently recent Gradle version. Always run CI on the actual toolchain and runtime that the application supports.

If the project uses Java 17, set `release=17` instead of 16 to accurately reflect the required APIs and language level. Do not bump the version just because of an IDE warning if the application must still be deployed on an older JVM.

## 9. A Subtle Change: Rules Rejecting “Always-True” Patterns Across Releases

When consulting JEP 394 documentation for Java 16, you may encounter the rule: for an `instanceof` pattern, if the expression has a static type `S` that is a subtype of the pattern type `T`, the compiler rejects it because the check is always true for non-null objects.

Example:

```java
class SourceTypingVersionDemo {
    static boolean matches(String value) {
        return value instanceof CharSequence text;
    }
}
```

**Verified results with the JDK 21 compiler at different source releases**:

| Source release passed to `javac --release` | Result |
|---|---|
| `16` | Compile-time error |
| `17` | Compile-time error |
| `18` | Compile-time error |
| `19` | Compile-time error |
| `20` | Compile-time error |
| `21` | **Compiles successfully** |

Why you must read the JLS for the exact release: in Java 21, the pattern model added the concept of an **unconditional type pattern**, and compatibility rules were reformulated within the general pattern system. Therefore, you must not take an “always-true type test causes an error” message from one Java version and assume it applies to all newer versions.

If you only need to check whether `value` is non-null when the variable is already declared as `String`, the clearer expression is usually:

```java
String value = "abc";
boolean present = value != null;
```

That is, regardless of whether a specific pattern is allowed by the Java 21 compiler, **there is no need to use `instanceof` as a substitute for a null check** when the data's type is already known.

**Do not confuse this with an uncastable type mismatch:** for example, `String s; s instanceof Integer i` remains invalid in standard Java versions because the static type is not checked-cast-convertible to `Integer`. Before drawing a conclusion, look at both **the static type of the selector** and **the source release being compiled**.

## 10. Common Mistakes When Upgrading or Downgrading the Java Target

### 10.1. Confusing the First Appearance Version with the Stable Version

The statement “pattern matching for `instanceof` exists since Java 14” needs the word **preview** added. When choosing the minimum milestone for a production product without preview features, the correct milestone is **Java 16**.

### 10.2. Assuming Enabling Preview on JDK 21 Re-enables JDK 14 Preview

Incorrect. Preview features are tied to a specific JDK version. The pair `--enable-preview --release 15` under the JDK 21 compiler was rejected in actual verification. To test historically, use the exact JDK 15 version.

### 10.3. Using Record Deconstruction Syntax While Declaring a Java 16 Project

`obj instanceof Label(String name)` is a **record pattern**, not a basic type pattern; its official milestone is Java 21. For Java 16, only use forms like `obj instanceof Label label` if the `Label` type already exists and is appropriate.

### 10.4. Writing `when` After `instanceof`

`when` is a guard in a `case` label of a Java 21 pattern `switch`. With `instanceof` type patterns, use `&&`:

```java
if (obj instanceof String text && !text.isBlank()) {
    System.out.println(text);
}
```

This snippet is valid from Java 16 if the APIs used are compatible. Do not write `obj instanceof String text when ...`.

### 10.5. Ignoring Flow Scoping When Refactoring

`text` can only be used where the compiler guarantees the pattern has matched. Therefore:

```java
if (obj instanceof String text && text.length() > 3) {
    System.out.println(text);
}
```

is valid, whereas:

```java
// Invalid: the right-hand side of || can be evaluated when
// the pattern on the left does not match, so text is not bound.
if (obj instanceof String text || text.length() > 3) {
    System.out.println("value");
}
```

is rejected by the compiler. This is a **scope** error rather than necessarily a Java version milestone error.

### 10.6. Thinking JVM 16 Alone Makes Java 16 Source Code Compile

No. The toolchain must use a `javac` that supports Java 16 and configure source/target accordingly. With JDK 11, you cannot build pattern code by requesting `--release 16`, because the older compiler does not support future releases. Runtime and compiler are two separate parts.

### 10.7. Increasing `--release` While Production Still Uses an Older JVM

Code compiled successfully with `--release 21` cannot run by default on JVM 17. If there are runtime constraints, keep the proper target or upgrade the runtime in a controlled manner; also pay attention to accompanying libraries and APIs.

### 10.8. Believing Preview Code Is Forever-Stable API/Syntax

Preview features are allowed to change or be removed before becoming official. For new projects, prefer a JDK that supports the final feature rather than relying on historical 14/15 previews or carrying preview classfiles to a different runtime.

### 10.9. Confusing Preview Pattern Variable Assignment Rules with Java 16+

Since JEP 394, pattern variables are no longer implicitly final; they can be reassigned. However, reassigning can cause readers to confuse the initially bound value with the modified value. Use a new variable if the transformation changes the meaning and the original data needs to be preserved.

## 11. Codebase Compatibility Checklist

Before introducing `instanceof T t` into a project, verify:

1. **Minimum supported JDK:** What is the lowest deployed runtime version?
2. **Actual compiler:** Do CI, local, and IDE share the same JDK configuration? Check `javac -version`.
3. **Target source/API/bytecode:** What `--release` milestone or build tool configuration is currently used?
4. **Preview vs. final:** If targeting 14/15, are you using the right JDK and preview flags? If targeting 16+, preview is not needed for type patterns.
5. **Specific features:** Does the code only use type patterns in `instanceof`, or does it also use record patterns, pattern switch, or guarded cases?
6. **Scope and null:** Pattern variables are only used where matched; null input makes the root `instanceof` false.
7. **APIs beyond syntax:** For example, using `String.isBlank()` (an API introduced in Java 11); valid syntax is not enough if the API called exceeds the target.
8. **Binary compatibility:** Services/JARs may be running on different JVMs; avoid deploying newer classfiles on older JVMs.
9. **Run tests against the build target:** Try `javac --release N` or Maven/Gradle configuration; if runtime assurance is needed, also run on a real JVM N in CI.
10. **Classify compiler errors accurately:** Error messages may stem from missing preview, syntax newer than the target, incompatible static types, scope, or non-existent APIs.

Only after all checks pass should you begin refactoring manual casts into type patterns in code sections permitted for modification.

## 12. Self-Check Exercises

**Question 1.** Is `pattern matching for instanceof` in Java 14 or 16?  
**Answer:** It had a **preview in 14**; it became an **official feature in 16**.

**Question 2.** Which JEP corresponds to each milestone?  
**Answer:** **JEP 305 → Java 14 (preview); JEP 375 → Java 15 (second preview); JEP 394 → Java 16 (final)**.

**Question 3.** Why can't `javac 21 --enable-preview --release 15` replace JDK 15?  
**Answer:** The JDK 21 compiler cannot re-enable preview features of an older release; you must use a real JDK 15 toolchain.

**Question 4.** Can Java 17 use `input instanceof String text`?  
**Answer:** Yes. The feature became official in Java 16 and does not require preview on Java 17.

**Question 5.** Can Java 16 use `obj instanceof Label(String text)`?  
**Answer:** No, that is a **record pattern** (official in Java 21), not a basic type pattern.

**Question 6.** Does Java 8 have `instanceof`?  
**Answer:** It has the traditional operator; it does not have the pattern variable binding syntax `instanceof String s`.

**Question 7.** If code uses `instanceof` type patterns and CI fails with `--release 11`, can it be solved simply by adding a dependency?  
**Answer:** No. This is language syntax that does not exist at source level 11; you must raise the target or rewrite using a traditional cast.

**Question 8.** Does `--release 16` on JDK 21 prove the code runs on a real JVM 16?  
**Answer:** Not yet. It proves compilability against the target source/API/bytecode; to confirm runtime behavior, run tests on a real JVM 16.

**Question 9.** What did Java 16 change about pattern variables?  
**Answer:** They are no longer implicitly final; they can be reassigned within a valid scope, unlike during the preview stage.

**Question 10.** Why must the example `String s; s instanceof CharSequence c` be evaluated by `--release`?  
**Answer:** Type pattern checking rules changed as the language evolved; in the verification environment, `--release 16–20` resulted in an error while `--release 21` was valid. Both static types and the JLS for the release matter.

## Conclusion

There are three milestones you must not confuse:

- **Java 14 / JEP 305:** appeared as the **first preview**.
- **Java 15 / JEP 375:** **second preview**.
- **Java 16 / JEP 394:** **final, no preview required**.

Java 17 and Java 21 use type patterns in `instanceof` as a stable feature. Record patterns and pattern switch are separate developments standardized in Java 21. When talking about “minimum Java,” evaluate the exact **feature, source level, compiler, and target runtime**, rather than just looking at the `instanceof` statement in the code.

## Official References

- [JEP 305 — Pattern Matching for instanceof (Preview, JDK 14)](https://openjdk.org/jeps/305)
- [JEP 375 — Pattern Matching for instanceof (Second Preview, JDK 15)](https://openjdk.org/jeps/375)
- [JEP 394 — Pattern Matching for instanceof (JDK 16)](https://openjdk.org/jeps/394)
- [Oracle — Java Language Changes by Release](https://docs.oracle.com/en/java/javase/21/language/java-language-changes-release.html)
- [Oracle Java 21 — Pattern Matching for the instanceof Operator](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-instanceof.html)
- [JLS Java SE 21 — instanceof Operator §15.20.2](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.20.2)
- [Oracle Java 21 — javac Command Options](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html)
- [JEP 440 — Record Patterns (JDK 21)](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch (JDK 21)](https://openjdk.org/jeps/441)
