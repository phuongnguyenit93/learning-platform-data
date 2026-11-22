# Syntax Differences Across Java Versions: Pattern Matching and Related Syntax

## 1. Why does the same pattern code compile on one machine and fail on another?

Java evolves incrementally: some syntax appears in **preview** status for several versions before becoming a **final feature**. Therefore, tutorial code containing `switch`, `instanceof`, `record`, or `when` may require **different language versions**, even though it all looks like “modern Java”.

In **Java Core Pattern Matching**, the most important changes are:

- Type checking: traditional `instanceof` with casting → **type pattern** declaring a variable directly in the check.
- Branching: traditional `switch statement` → `switch expression` returning a value → **pattern matching for switch**.
- Data organization: regular classes → `record` and `sealed` hierarchies → **record patterns** to deconstruct components.
- Ignoring unused data: declaring a variable and not using it → **unnamed patterns** with the `_` symbol starting in Java 22.

**This lesson focuses on syntax differences, version requirements, common errors, and migration strategies.** You should not assume that every feature with the word “pattern” appeared at the same time or that all Java 21 features require enabling preview.

## 2. Timeline of Key Syntax

| Java Version | Related Syntax/Feature | Status in That Version | Notes |
| --- | --- | --- | --- |
| Java 8/11 | `instanceof Type` and cast, `switch` statement with `case:` | Previously stable | **No** `instanceof String s` type pattern or official pattern cases |
| Java 12–13 | `switch expression` | Preview | Experimental syntax changed across versions; do not copy old preview examples into new code |
| **Java 14** | `switch expression`, `case ... ->`, and `yield` | **Final** | JEP 361; arrow rules can also be used in `switch statement` |
| Java 14–15 | Type patterns in `instanceof` | Preview | JEP 305/JEP 375; should only be treated as version-specific reference |
| **Java 16** | `instanceof String s` and `record` | **Final** | JEP 394, JEP 395; `record` does **not** mean record patterns are available |
| **Java 17** | `sealed` types; pattern `instanceof` | **Final** | JEP 409; pattern matching for `switch` is still **preview** |
| Java 17–20 | Pattern matching for `switch` | Preview across multiple rounds | Guards and rules changed; not standard syntax to copy for Java 21 |
| Java 19–20 | Record patterns | Preview | Standardized in Java 21 |
| **Java 21** | Pattern matching for `switch`; record patterns, `when` | **Final** | JEP 441 and 440; main examples in this lesson run here |
| **Java 22** | Unnamed patterns and variables with `_` | **Final** | JEP 456; Java 21 had a separate preview (JEP 443), not enabled by default |

**Important:** `var` for **local variables** has been final since **Java 10**; do not confuse it with `var` inside a record pattern `Point(var x, var y)`, which is only valid record pattern syntax when supported by the language version. The underscore `_` is yet another case with its own rules.

The table above lists **the essential milestones when reading and migrating pattern code**, and is not intended to list every feature of each Java release.

## 3. Java 8/11: checking the type then casting manually

Before pattern matching for `instanceof`, code was typically written as:

```java
static String oldStyle(Object value) {
    if (value instanceof String) {
        String text = (String) value;
        return text.toUpperCase(java.util.Locale.ROOT);
    }
    return "other";
}
```

This is an **illustrative method** and must be placed inside a class to compile. The syntax `value instanceof String` only returns a Boolean; it **does not create the `text` variable**. The developer has to repeat the cast even though the `if` branch already knows the type.

With multiple subtypes, legacy code easily leads to:

```java
if (value instanceof String) {
    String s = (String) value;
    // ...
} else if (value instanceof Integer) {
    Integer n = (Integer) value;
    // ...
}
```

**This works in Java 8/11**, but has the drawback of repetitive syntax and being prone to copying the wrong cast type. When a codebase must build with `--release 8` or `--release 11`, this remains a valid approach. You cannot simply change `String text` into a type pattern and expect Java 8 source code to compile.

## 4. Java 14: switch expression, arrow rules, and yield

### 4.1. From `switch statement` to `switch expression`

Classic statement form:

```java
static String oldSwitch(String state) {
    String result;
    switch (state) {
        case "ON":
            result = "on";
            break;
        case "OFF":
            result = "off";
            break;
        default:
            result = "unknown";
    }
    return result;
}
```

Expression form finalized in Java 14:

```java
static String newSwitch(String state) {
    return switch (state) {
        case "ON" -> "on";
        case "OFF" -> "off";
        default -> "unknown";
    };
}
```

Both methods are illustrative snippets inside a class, and both assume `state` is **non-`null`**. For `null`, this kind of `switch` on `String` does not automatically have a null branch; to handle it, use `if (state == null)` outside. Do not put Java 21's pattern switch `case null` into examples that need to run on Java 14.

Differences in purpose:
- A `switch statement` controls statements and can `break;` out of the switch.
- A `switch expression` **produces a value**, so every path must yield a value appropriately; arrow rules return the result directly.
- In arrow rules, there is no automatic fall-through between cases. With traditional colon groups, you must be especially careful with `break` to avoid falling through into another case group.

### 4.2. Block rules and `yield`

```java
static String withBlock(String state) {
    return switch (state) {
        case "ON" -> {
            String message = "enabled";
            yield message;
        }
        default -> "other";
    };
}
```

Here, `yield message;` produces the value of the **switch expression**, rather than returning from the entire method. Do not use `break message;` in Java 14+; some articles about the Java 12 preview may use the historical `break value` syntax, but **that is not the final syntax**.

Key takeaway: **`case ... ->` does not mean pattern matching**. Arrow rules and switch expressions have been final since Java 14; however, `case String s -> ...` in a pattern switch did not become final until **Java 21**.

## 5. Java 16: type patterns with instanceof and record declarations

### 5.1. Finalized type patterns

```java
static String newStyle(Object value) {
    if (value instanceof String text) {
        return text.toUpperCase(java.util.Locale.ROOT);
    }
    return "other";
}
```

`String text` is a **type pattern**. When `instanceof` matches, the variable `text` is bound to the checked value with type `String`. No additional cast is needed.

With short-circuiting conditions:

```java
if (value instanceof String text && !text.isEmpty()) {
    System.out.println(text);
}
```

The right-hand side of `&&` only executes if the pattern on the left-hand side succeeds; this guarantees `text` is available. This is **flow scoping**, which differs from simple block scope. When `value == null`, `instanceof` returns `false` without throwing `NullPointerException`.

**Common mistake:**

```java
// Wrong: the right-hand side of || can run when the pattern does not match.
if (value instanceof String text || text.isEmpty()) {
    System.out.println("...");
}
```

You need to change the logic (usually to `&&`) or move the condition inside the branch where `text` is known to be valid; you cannot assume the pattern variable exists outside.

### 5.2. Record declarations are not record patterns

Java 16 already allowed declaring:

```java
record Point(int x, int y) {}
```

A record defines a data-carrier class; it does not automatically enable deconstruction syntax:

```java
// Java 16/17: use a type pattern + accessors.
if (value instanceof Point p) {
    System.out.println(p.x() + p.y());
}
```

Whereas:

```java
// Only stable from Java 21, NOT Java 16/17 syntax.
if (value instanceof Point(var x, var y)) {
    System.out.println(x + y);
}
```

**Distinction to remember:** `record Point(...)` is a **record declaration**; `Point(var x, var y)` inside `instanceof`/`case` is a **record pattern**, which has a different language evolution timeline.

## 6. Java 17: sealed types and limitations of pattern switch

`sealed` allows modeling a permitted set of subtypes:

```java
sealed interface Signal permits Text, Metric {}
record Text(String content) implements Signal {}
record Metric(int count) implements Signal {}
```

These are illustrative declarations. Since records are implicitly final and implement `Signal`, the subtypes above are suitable as a closed set of variants.

**Final Java 17 supports:**
- `sealed interface` with `permits`.
- `record`.
- `instanceof String s`.
- `switch expression` with regular constant cases.

**However, Java 17 does not have pattern matching for `switch` as a final feature.** An example like:

```java
// Final in Java 21; on Java 17 this is not yet stable syntax.
return switch (signal) {
    case Text t -> t.content();
    case Metric m -> Integer.toString(m.count());
};
```

cannot be compiled under `--release 17` in stable language mode. When targeting Java 17, you can handle this with an `if (signal instanceof Text t) ... else if ...` chain or use polymorphism; or if you want preview for experimentation, you must use JDK 17's own preview mechanism, understanding that the syntax may have changed afterward.

**Do not use preview features in production code just because a blog example works.** Check the exact version and JEP, and verify your build target, runtime target, and project preview policy.

## 7. Java 21: switch patterns, record patterns, and when guards are all final

This is the milestone that allows writing a `switch expression` over objects with **type patterns**, **record patterns**, and **`when` guards**:

```java
return switch (signal) {
    case null -> "signal:missing";
    case Text(var content) when content != null && !content.isBlank() ->
            "text:" + content.toUpperCase(java.util.Locale.ROOT);
    case Text(var content) -> "text:empty";
    case Metric(var n) when n < 0 -> "metric:negative:" + n;
    case Metric(var n) -> "metric:" + n;
};
```

This snippet is the **body of a method returning `String`**, assuming `Signal`, `Text`, and `Metric` are declared as in section 6. The complete program is in section 9.

### 7.1. Record patterns extract components

`case Text(var content)` matches a `Text` and extracts the `content` component. `var content` is inferred as `String` from the record component type. `case Metric(var n)` extracts an `int`.

Record patterns enforce rules on the count, order, and types of subpatterns corresponding to the record components. For example, `Text(var a, var b)` is invalid because `Text` has only one component.

**`null` must be considered at the right level:**
- `case null` handles the **selector `signal == null`**.
- `case Text(var content)` can still match a `Text` whose `content == null`.
- A nested pattern like `Outer(Inner(...))` **does not match** if the component matched against `Inner` is `null`, even if `Outer` exists.

### 7.2. Guards use `when`, not `&&` directly after the pattern

In Java 17/18 pattern switch previews, older examples could be written like:

```java
// OLD PREVIEW SYNTAX ILLUSTRATION — DO NOT use in final Java 21.
case String text && !text.isEmpty() -> "non-empty";
```

In later preview rounds, guard syntax switched to `when`; in **final Java 21**:

```java
// Used in switch over Object or a compatible selector type.
case String text when !text.isEmpty() -> "non-empty";
```

Compare with how it is written in `instanceof`:

```java
// Valid: && is a Boolean operator outside the instanceof pattern.
if (value instanceof String text && !text.isEmpty()) {
    System.out.println(text);
}
```

**Exact distinction:** `when` is the **guard clause in a `case` label** of a pattern switch; `&&` remains a valid Boolean operator **inside conditional expressions**, and can be used inside `when` such as `when content != null && !content.isBlank()`.

### 7.3. Dominance and exhaustiveness

With a sealed hierarchy, the compiler checks that the `switch expression` covers all permitted subtypes. In the sample program, `Text` and `Metric` are sufficient, plus `case null` per our null-handling requirement; no `default` is needed.

Case order also matters:

```java
// Valid: specialized branch before general branch.
case Metric(var n) when n < 0 -> "negative";
case Metric(var n) -> "non-negative";
```

If you place the unguarded `case Metric(var n)` above, the guarded case below is **dominated** and can be rejected by the compiler. An arbitrary `default` in a switch over a sealed hierarchy can also hide warnings when new subtypes are added later.

### 7.4. `switch` on null differs from `instanceof` on null

`null instanceof String s` is `false`. However, `switch (signal)` with a null selector does not automatically enter `default`; if `null` is not handled according to the appropriate rules, it can throw `NullPointerException`. Final pattern switch allows writing `case null -> ...` to choose an explicit policy.

## 8. Java 22: unnamed patterns with the underscore symbol

Java 22 standardized **unnamed patterns and variables** (JEP 456). An `_` in an unnamed pattern position means the value at that position **does not need to be bound to a usable variable**.

The example below is a **Java 22+ snippet**, placed inside a class where `Text`/`Metric` types are already defined:

```java
static String kind22(Signal signal) {
    return switch (signal) {
        case Text(_) -> "text";
        case Metric(_) -> "metric";
        case null -> "missing";
    };
}
```

Here `Text(_)` and `Metric(_)` only care about the record variant, not the component. There is no variable named `_` to read afterward, and `_` cannot be used as a value in a guard.

**Do not confuse:**
- `Text(var content)`: binds the component to `content` for further use.
- `Text(_)`: matches but **ignores** the component, available as final from Java 22.
- `var` in local variable declarations has existed since Java 10, and is **not** the `_` syntax.
- In Java 21, unnamed patterns existed as a **preview (JEP 443)**; the final Java 21 example in this lesson **does not use `_`**, so preview does not need to be enabled.

**Tested on JDK 24:** `kind22(new Text("x"))`, `kind22(new Metric(3))`, and `kind22(null)` produce `text/metric/missing` (if joined with `/`). This is a Java 22+ extension—**do not insert** it into the Java 21 file in section 9.

To compile the snippet using `_` separately with a Java 22 or later target:

```bash
javac --release 22 SomeJava22File.java
```

Use the actual filename you create for the Java 22 snippet; the example above only illustrates the **compiler option**, not an instruction to compile a file provided in this lesson.

## 9. A Java 21 program demonstrating the syntax milestones

Create the file **`PatternSyntaxTimelineDemo.java`**:

```java
public class PatternSyntaxTimelineDemo {
    sealed interface Signal permits Text, Metric {}
    record Text(String value) implements Signal {}
    record Metric(int value) implements Signal {}

    // Legacy instanceof + cast syntax, still accepted in Java 21.
    static String legacy(Object input) {
        if (input instanceof String) {
            String text = (String) input;
            return "legacy:" + text.toUpperCase(java.util.Locale.ROOT);
        }
        return "legacy:other";
    }

    // Type pattern finalized in Java 16.
    static String typePattern(Object input) {
        if (input instanceof String text && !text.isBlank()) {
            return "typed:" + text.toUpperCase(java.util.Locale.ROOT);
        }
        return "typed:other";
    }

    // Switch expression finalized in Java 14, without pattern cases.
    static String status(String value) {
        if (value == null) return "status:missing";
        return switch (value) {
            case "ON" -> "status:on";
            case "OFF" -> "status:off";
            default -> "status:unknown";
        };
    }

    // Sealed hierarchy from Java 17; record + switch patterns from Java 21.
    static String classify(Signal signal) {
        return switch (signal) {
            case null -> "signal:missing";
            case Text(var content) when content != null && !content.isBlank() ->
                    "text:" + content.toUpperCase(java.util.Locale.ROOT);
            case Text(var content) -> "text:empty";
            case Metric(var n) when n < 0 -> "metric:negative:" + n;
            case Metric(var n) -> "metric:" + n;
        };
    }

    public static void main(String[] args) {
        System.out.println(legacy("java"));
        System.out.println(legacy(7));
        System.out.println(typePattern("java"));
        System.out.println(typePattern(" "));
        System.out.println(status("ON"));
        System.out.println(status(null));
        System.out.println(classify(new Text("hello")));
        System.out.println(classify(new Text(null)));
        System.out.println(classify(new Metric(-2)));
        System.out.println(classify(new Metric(4)));
        System.out.println(classify(null));
    }
}
```

**Requires JDK 21+**, compile and run:

```bash
javac --release 21 PatternSyntaxTimelineDemo.java
java PatternSyntaxTimelineDemo
```

**Exact stdout:**

```text
legacy:JAVA
legacy:other
typed:JAVA
typed:other
status:on
status:missing
text:HELLO
text:empty
metric:negative:-2
metric:4
signal:missing
```

This program was run in **JDK 24** JShell and returned the exact 11 lines above. Using `java.util.Locale.ROOT` keeps uppercase conversion consistent, avoiding dependence on the host machine's locale.

**Note on “runs on Java 14/16/17”:** This complete file **cannot** compile with a target lower than Java 21, because it contains both record patterns and final pattern switch. The comment labels in the file only indicate **when each individual syntax became final**. To build an example that truly targets Java 14/16/17, you must **remove or replace** all syntax introduced after that version, not just change the number in `--release`.

### 9.1. How to check compiler/runtime versions yourself

```bash
javac -version
java -version
```

If a codebase must release for Java 17, only checking `java -version` locally **is not enough** to guarantee compatibility. Build with an appropriate JDK and `javac --release 17` (or the equivalent Maven/Gradle toolchain configuration), and run tests on a Java 17 runtime.

`--release` controls the target source/API/class file version, but **does not automatically convert Java 21 syntax into Java 17 syntax**. The Java 21 file above must be refactored before lowering the target.

## 10. Common compilation errors when copying syntax from the wrong version

| Symptom | Common Cause | How to Fix |
| --- | --- | --- |
| `instanceof String text` fails under `--release 11` | Type patterns are not final in Java 11 | Use `instanceof String` + cast or raise target to Java 16+ |
| `record Point(...)` is not recognized under `--release 11` | Records became final in Java 16 | Use a regular class, or raise target |
| `Point(var x, var y)` fails under `--release 17` | Record patterns became final in Java 21 | Use `instanceof Point p` then `p.x()`/`p.y()` |
| `switch` with `case Text t ->` fails on target 17 without preview | Pattern switch is not final in Java 17 | Use an `instanceof` chain/polymorphism, or target 21+ |
| `case String s && test(s)` does not compile on Java 21 | Guard syntax is from an older preview | Change to `case String s when test(s) ->` |
| `case ... when ...` fails in a Java 14 switch | Pattern switch is not final | Move condition into a block or raise target to 21 |
| `yield` in a switch expression fails with Java 11 source | Switch expressions are not final | Use a switch statement + result variable, or raise target to 14 |
| `case null` in a pattern switch fails on older source | No corresponding final pattern switch mechanism | Guard null before switch; on Java 21 use `case null` when appropriate |
| `case Text(_)` fails under `--release 21` in final mode | Unnamed patterns became final in Java 22 | Use `case Text(var ignored)` or raise target to 22+ |
| `var` used for fields, parameters, or record patterns on unsupported versions | Confusing local `var` with types/patterns and version | Use explicit type declarations or the right syntax/version |
| `Class file version ... is newer`, `UnsupportedClassVersionError` | Running classes compiled for a newer Java on an older runtime | Build with the right `--release`, or upgrade the runtime accordingly |
| Build only succeeds when preview is enabled | Code uses a preview feature of that version | Decide on preview policy; do not treat as final/portable syntax |

### 10.1. Testing compile errors instead of guessing

The following two snippets are **intentionally invalid** and must not be placed in the runnable example file:

```java
// Wrong component count: record Text has only one component.
static boolean badArity(Object value) {
    return value instanceof Text(var first, var second);
}
```

```java
// Flow scoping error: text may not be assigned after the if branch.
static void badScope(Object value) {
    if (value instanceof String text) {
        System.out.println(text);
    }
    System.out.println(text); // Invalid.
}
```

In a JDK 24 environment, the wrong-arity case is rejected with `incorrect number of nested patterns`. The variable-scoping case is also rejected because the compiler cannot see `text` as definitely assigned on the following line. These snippets are designed to verify compile-time knowledge, not to produce runtime stdout.

The old preview guard snippet:

```java
// INTENTIONALLY INVALID in final Java 21 (and JDK 24).
case String s && !s.isEmpty() -> "text";
```

was also tested and rejected by the JDK 24 compiler. `case String s when !s.isEmpty() -> "text";` is required inside a compatible pattern switch.

## 11. Understanding preview features when reading older source code

Java features typically go through a lifecycle: proposed via a JEP, potentially **previewed for one or more rounds**, gathering feedback, changing syntax/semantics, and then becoming **final**. Preview does **not** mean “available since that version and safe to use forever”.

For a project that intentionally uses a preview feature in its exact JDK version, preview flags are usually required at compile/run time, as illustrated below:

```bash
# Only when code actually uses a Java 20 preview feature:
javac --enable-preview --release 20 PreviewExample.java
java --enable-preview PreviewExample
```

`PreviewExample.java` is a **hypothetical** name for a separate preview example, not a file provided in this lesson. The preview flag does not “unlock” all future final Java syntax on an older compiler. Preview class files have their own version/runtime rules and may not run on a different JDK version; do not use a test result on JDK 24 to claim that Java 17 preview code will still be valid.

How to read online tutorials:

1. Identify the **Java version** the article uses.
2. Distinguish between **preview** and **final** in that version.
3. Cross-check guard syntax, record patterns, `case null`, `yield`, and `_` against your **project's source level**.
4. Choose a migration path: stay on a supported version with matching syntax, or upgrade the JDK/toolchain with testing.
5. Read the **final JEP** to confirm semantics instead of copying outdated preview code.

## 12. Upgrading source code across Java levels

**Target Java 8/11:** Use `instanceof Type` + cast and traditional `switch statement`. Do not use record declarations, sealed hierarchies, record patterns, or switch patterns.

**Target Java 14:** Switch expressions and `yield` are final. You still need to cast after `instanceof`; do not assume type patterns are final. `case ... ->` here can only use constant cases, not pattern matching.

**Target Java 16:** Replace `instanceof` + repetitive casts with `instanceof Type variable`. You can use record declarations, but extracting record components still goes through accessors.

**Target Java 17:** Sealed types are final, convenient for closed domain models; use type patterns in `instanceof`, and do not use final pattern switch yet. If downgrading Java 21 code to 17, convert pattern `switch` into `if/else instanceof` or polymorphism.

**Target Java 21:** Use final record patterns and switch patterns, nested deconstruction, `when` guards, `case null`, and exhaustiveness with sealed hierarchies. No preview flags are needed for these features.

**Target Java 22+:** If you want to ignore unused components with `_`, you can use final unnamed patterns. Verify that your formatter, IDE, and build pipeline support the corresponding source level.

### Syntax selection table by task

| Task | Java 8/11 | Java 16/17 | Java 21 | Java 22+ |
| --- | --- | --- | --- | --- |
| Check if Object is String | `v instanceof String` then cast | `v instanceof String s` | Same as Java 16 | Same |
| Create a small data type | Regular class | `record Point(...)` | Record | Record |
| Extract two Point components | `Point p = ...; p.x()/p.y()` | `instanceof Point p` then accessors | `instanceof Point(var x, var y)` | Same; can use `_` for ignored components |
| Branch on multiple subtypes | `if` + cast, virtual dispatch | `if` + type pattern | `switch(object)` + pattern cases | Pattern cases, optionally with unnamed patterns |
| Guard in pattern switch | Not available | Not final syntax in 17 | `case T t when condition ->` | Same |
| Switch returning a value | `switch statement` + variable | `switch expression` | Switch expression with patterns | Like Java 21, plus post-21 features if desired |

Note on the “Java 16/17” column: this group only describes syntax that is **commonly final in both Java 16 and 17**. `sealed` specifically became final in Java 17. The “Java 22+” group only states that the mentioned syntax has existed since Java 22, without claiming that all other preview features in newer JDKs are final.

## 13. Exercises: identify the minimum version and fix code

**Exercise 1.** Given:

```java
if (obj instanceof String text && text.length() > 2) {
    System.out.println(text);
}
```

The `String text` pattern syntax has been final since **Java 16**. Java 11 version: check `obj instanceof String` then cast inside the branch.

**Exercise 2.** Given:

```java
return switch (state) {
    case "OK" -> "success";
    default -> "error";
};
```

If `state` is a `String`, switch expressions with arrow rules have been final since **Java 14**. Pattern matching for `switch` is not needed for this form. For Java 11, write a `switch` statement + `result` variable or corresponding `return` statements.

**Exercise 3.** Given:

```java
return switch (point) {
    case Point(var x, var y) when x > 0 -> "right";
    case Point(var x, var y) -> "other";
    case null -> "missing";
};
```

Assuming `Point` is a record and the selector has an appropriate type, the combination of record pattern + pattern switch + `when` in final form requires **Java 21**. If it must run on Java 17, replace with:

```java
// Inside a method with variable point of type Point.
if (point == null) {
    return "missing";
}
if (point.x() > 0) {
    return "right";
}
return "other";
```

**Exercise 4.** Given `case Point(var x, _) -> ...`. Explain that `_` is an unnamed pattern finalized in **Java 22**; on Java 21 in non-preview mode, replace it with `case Point(var x, var ignored) -> ...` without using `ignored`, or avoid deconstructing the unneeded component.

**Exercise 5.** Set up two CI jobs for a project supporting Java 17 and 21: one job builds/tests with `--release 17`, and the other builds/tests Java 21. If a file contains `case Text(var content)`, move it to the 21 job or rewrite it for the 17 job. Do not “ignore” compiler errors by enabling JDK 17 preview without controlling syntax differences.

## 14. Summary

- **Java 14:** switch expressions, arrow rules, and `yield` are final.
- **Java 16:** type patterns for `instanceof` and record declarations are final.
- **Java 17:** sealed types are final, but pattern switch is not yet final.
- **Java 21:** record patterns and pattern matching for `switch` are final; guards use `when`.
- **Java 22:** unnamed patterns/variables `_` are final.
- **Preview** is an experimental capability of a **specific version**, not a guarantee of stable syntax in later releases.
- **Compatibility must be verified across source level, compiler/toolchain, and runtime**. Do not rely on a snippet compiling on a newer JDK to claim it runs on an older target.

### Official Documentation

- [JEP 361 — Switch Expressions (Java 14)](https://openjdk.org/jeps/361)
- [JEP 394 — Pattern Matching for instanceof (Java 16)](https://openjdk.org/jeps/394)
- [JEP 395 — Records (Java 16)](https://openjdk.org/jeps/395)
- [JEP 409 — Sealed Classes (Java 17)](https://openjdk.org/jeps/409)
- [JEP 440 — Record Patterns (Java 21)](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch (Java 21)](https://openjdk.org/jeps/441)
- [JEP 443 — Unnamed Patterns and Variables, Preview (Java 21)](https://openjdk.org/jeps/443)
- [JEP 456 — Unnamed Patterns and Variables (Java 22)](https://openjdk.org/jeps/456)
- [Oracle Java 21 Language Guide — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Oracle Java 21 Language Guide — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
