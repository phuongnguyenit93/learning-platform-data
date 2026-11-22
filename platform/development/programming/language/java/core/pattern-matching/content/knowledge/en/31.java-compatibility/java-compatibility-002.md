# Version Milestones of Pattern Switch in Java: From Preview to Java 21 and Subsequent Extensions

## 1. Key Takeaways First

**Pattern matching for `switch` became final (*final/permanent*) in Java 21 — JEP 441.** This feature was introduced as a **preview** in Java 17 and went through four preview rounds in Java 17, 18, 19, and 20 before stabilizing.

Main milestones:

**Java 17 (JEP 406, preview) → Java 18 (JEP 420, second preview) → Java 19 (JEP 427, third preview) → Java 20 (JEP 433, fourth preview) → Java 21 (JEP 441, final).**

Three related features must be distinguished, as they do **not share the same milestone**:

1. **Switch expressions** with `case ... ->` and `yield` became final in **Java 14** (JEP 361). This is **not yet** pattern matching for `switch`.
2. **Pattern matching for `instanceof`** became final in **Java 16** (JEP 394). Having `obj instanceof String s` does not mean Java 16 already had `case String s`.
3. **Record patterns** such as `case Point(int x, int y)` became final in **Java 21** (JEP 440), after preview rounds in Java 19–20. Record patterns can be combined with Java 21's final pattern switch.

**Choosing a practical baseline:** If a project uses `case String s`, `case Point(int x, int y)`, `when`, and `case null` with current syntax and **does not want to enable preview**, choose **Java 21 or later** as the source level. On JDK 21, compiling stable Java 21 code does not require `--enable-preview`.

This guide uses **Java 21 as the primary compatibility baseline**. The final section separately notes the preview extensions for primitive patterns in Java 23–27, updated according to Java 27 documentation (September 2026); they **do not change** the fact that pattern switch on reference types has been final since Java 21.

## 2. Official Timeline of Pattern Matching for Switch

| Java Version | JEP | Status | Key Highlights |
| --- | --- | --- | --- |
| **Java 17** | **406** | 1st Preview | Introduces type patterns into `switch`, supporting type checks, pattern variables, null labels, and guarded patterns. Initial guard syntax was **inside the pattern**, in the form `case String s && condition`. |
| **Java 18** | **420** | 2nd Preview | Adjusts dominance of constant/guard/type pattern labels; improves exhaustiveness checking, including generic sealed hierarchies. |
| **Java 19** | **427** | 3rd Preview | Guard moves to **`when`**; adjusts null selector handling; cases that are exhaustive at compile time but match nothing at runtime throw `MatchException`. Can be combined with **record patterns preview** (JEP 405). |
| **Java 20** | **433** | 4th Preview | Simplifies `case` label grammar, clarifies `MatchException` when an exhaustive enum switch loses a branch at runtime, and coordinates with record pattern generic type inference (JEP 432). |
| **Java 21** | **441** | **Final** | Pattern matching for `switch` becomes a standard feature; no preview flag required. Removes parenthesized patterns, allows qualified enum constants in case constants. Record patterns also become final (JEP 440). |

**Source:** Oracle Java 21 Language Changes by Release and the corresponding JEPs.

The table above describes **feature milestones**, not a guarantee that a preview source file written in Java 17 can compile unmodified on Java 21. The preview rounds themselves changed syntax and several rules. Therefore, a tutorial written for Java 17/18 may contain `case String s && ...`, while documentation for Java 21 uses `case String s when ...`.

### 2.1. Java 17 — JEP 406 (Preview)

Java 17 allows using type patterns in `switch` as a preview feature. Example **illustrating Java 17 preview syntax**:

```java
// Java 17 preview: not Java 21 guard syntax.
static String oldPreview(Object value) {
    return switch (value) {
        case String s && s.length() > 3 -> "long text";
        case String s -> "text";
        case null -> "null";
        default -> "other";
    };
}
```

The form `String s && condition` is the **guarded pattern syntax** of the initial preview. Do not confuse it with the expression `instanceof String s && condition` (which remains valid in Java 21). In Java 21, a `case` label guard must be written with **`when`**.

Java 17 also finalized **sealed classes** (JEP 409), laying the groundwork for the compiler to analyze subtype sets in exhaustive switches. However, sealed classes becoming final **did not make** pattern switch final in Java 17.

To use the preview feature on **JDK 17 specifically**:

```bash
javac --enable-preview --release 17 PreviewSwitchDemo.java
java --enable-preview PreviewSwitchDemo
```

`PreviewSwitchDemo.java` in this pair of commands is an **illustrative filename** for a complete Java 17 preview program created by the learner. The `oldPreview` snippet above is only a method, **not a standalone program**. Do not run this pair of commands on a newer JDK to try to re-enable JDK 17's preview.

### 2.2. Java 18 — JEP 420 (Second Preview)

Java 18 continues the preview. Notable milestones in compiler behavior:

- **Dominance** checks for constant labels, guarded patterns, and non-guarded type patterns were refined.
- **Exhaustiveness** analysis of `switch` was expanded, especially for generic sealed classes and certain complex type sets.
- "2nd preview" must not be misunderstood as Java 18 allowing pattern switch without a preview flag.

When evaluating legacy code written for Java 18, check both **label ordering** and **cases the compiler considers exhaustive**. Logically equivalent code may receive different compiler diagnostics across previews.

### 2.3. Java 19 — JEP 427 (Third Preview)

This is a particularly easy milestone to confuse:

- The guard became **part of the case label** with the **`when`** keyword, replacing the guarded pattern form `p && e` from Java 17/18.
- Null selector rules became clearer: if the selector is `null` and there is no matching `case null` label, a `NullPointerException` is thrown, even if a type pattern covers the selector's type.
- If a `switch` is considered exhaustive at compile time but no label matches at runtime, a `MatchException` may be thrown.
- **Record patterns** first appeared in preview in Java 19 via **JEP 405**; from here, nested record patterns could be used in corresponding pattern contexts.

Example **illustrating Java 19 preview syntax**:

```java
// Java 19 preview or Java 21 final:
static String lengthClass(Object value) {
    return switch (value) {
        case String s when s.length() > 3 -> "long text";
        case String s -> "text";
        case null -> "null";
        default -> "other";
    };
}
```

This `when` syntax matches Java 21. However, **identical syntax does not guarantee that all rules and preview API versions are completely identical**. When upgrading, read the release notes/JEPs and re-run tests.

### 2.4. Java 20 — JEP 433 (Fourth Preview)

Java 20 continues the preview while moving toward completion:

- Simplified the grammar of `switch` case labels.
- Refined the exception thrown when an exhaustive enum switch has no matching label at runtime: `MatchException` instead of `IncompatibleClassChangeError` in the cases described by the JEP.
- **Record patterns second preview** (JEP 432) added type argument inference for **generic record patterns**, avoiding the need to always write explicit generic arguments in patterns.
- The syntax and availability of record patterns in enhanced `for` loops changed across preview releases; **do not mechanically apply Java 20 preview code to Java 21**.

**Java 20 is still not the final release** of pattern switch; for code using preview features on JDK 20, the preview flag must be enabled for compiling/running and tested when switching Java versions.

### 2.5. Java 21 — JEP 441 (Final)

Java 21 standardizes pattern matching for `switch`:

```java
Object value = "Java";

String label = switch (value) {
    case String text when text.length() > 3 ->
            "long:" + text;
    case String text -> "text:" + text;
    case null -> "null";
    default -> "other";
};
```

The snippet above is **illustrative code inside a method/initializer**, using final Java 21 syntax and returning `long:Java`.

Notable Java 21 standard points:

- The selector can be **any reference type**, along with the previously supported primitive types (`byte`, `short`, `char`, `int`); do not infer that primitive `long`/`double` are also allowed in Java 21.
- `when` is the guard syntax of a case label. `when` only executes when the corresponding pattern matches.
- `case null` allows explicit handling of a null selector; `default` does not automatically accept a null selector in a pattern switch.
- The compiler checks **domination** (covered branches) and **exhaustiveness**. With a sealed hierarchy, `default` may not be needed if all branches are covered; adding a subtype requires updating the corresponding dispatch sites.
- **Parenthesized patterns** that existed in previews were removed in Java 21, and qualified enum constants are allowed in case constants.
- A switch expression can contain a block `-> { ... yield result; }`. `yield` is a switch expression mechanism, not a feature introduced for the first time in Java 21.
- The runtime may throw `MatchException` when a switch that was exhaustive at compile time fails to match at runtime; do not confuse this with `NullPointerException` from a null selector.

**Flag takeaway:** On Java 21, writing code that uses JEP 441 and JEP 440 **does not require** `--enable-preview`. The preview flag is only needed when using another preview feature of that specific JDK version.

## 3. Pre-Java 17 Foundation Milestones: Why Are They Easily Confused?

| Java Version | Related Feature | Preview/Final |
| --- | --- | --- |
| **12** | Switch expressions, JEP 325 | 1st Preview |
| **13** | Switch expressions, JEP 354 | 2nd Preview; switched to using `yield` to return values from a switch expression block |
| **14** | Switch expressions, JEP 361 | **Final**; `case ... ->` and `yield` are stable, but no final pattern switch yet |
| **14** | Pattern matching for `instanceof`, JEP 305 | 1st Preview |
| **15** | Pattern matching for `instanceof`, JEP 375 | 2nd Preview |
| **16** | Pattern matching for `instanceof`, JEP 394 | **Final** |
| **14 → 16** | Record classes, JEP 359 → 384 → 395 | Preview in 14–15, **final in 16** |
| **15 → 17** | Sealed classes, JEP 360 → 397 → 409 | Preview in 15–16, **final in 17** |
| **19 → 21** | Record patterns, JEP 405 → 432 → 440 | Preview in 19–20, **final in 21** |

### 3.1. Having `case ... ->` Does Not Mean Having Pattern Switch

Java 14 and later already have:

```java
int day = 2;
String kind = switch (day) {
    case 1, 7 -> "WEEKEND";
    default -> {
        yield "WEEKDAY";
    }
};
```

This is a **switch expression**: the labels are still **constants**, not type/record patterns. It is valid in Java 14+ without needing Java 21.

Conversely:

```java
// Cannot be treated as final Java 14/16 syntax:
Object value = "hello";
String kind = switch (value) {
    case String s -> "text:" + s;
    default -> "other";
};
```

A `switch` with `case String s` belongs to pattern matching for switch, which was in preview from Java 17 and only became final in Java 21. The difference is not the `->` arrow, but the fact that **the `case` label is a pattern** and the selector can be a reference type such as `Object`.

### 3.2. `instanceof` Patterns from Java 16 Differ from `switch` Patterns

Valid since Java 16:

```java
Object value = "hello";
if (value instanceof String s && !s.isBlank()) {
    System.out.println(s.toUpperCase());
}
```

Using `&&` right after `instanceof` is a **Boolean expression** with flow scoping. It is **not** the `case String s && condition` syntax from the Java 17/18 preview.

If the goal is only to check a single type, an `instanceof` pattern is usually clear enough; there is no need to convert it to a pattern `switch` and raise the runtime baseline to Java 21 just for style.

### 3.3. A Record Class Is Not the Same as a Record Pattern

Records can be declared and used stably since Java 16:

```java
record Point(int x, int y) {}

Point p = new Point(2, 3);
int x = p.x();  // Traditional accessor call.
```

However, the **deconstruction** syntax:

```java
// Final in Java 21; previewed in Java 19/20.
case Point(int x, int y) -> x + y;
```

is a **record pattern**, not just "record syntax". When reviewing code, identify **both** features: the model is a record and the code is **matching a record pattern**.

## 4. Complete Java 21 Example Combining the Milestones

This example brings three generations of features together in one program:

- `dayKind` uses a **switch expression**, final since Java 14.
- `inspect` uses an **`instanceof` type pattern**, final since Java 16.
- `classify` uses **pattern switch**, **`when`**, **nested record patterns**, `sealed`, and `case null`, all with full final syntax in Java 21.

Save the file as **`PatternSwitchTimelineDemo.java`**:

```java
public class PatternSwitchTimelineDemo {
    sealed interface Message permits Text, Count, Position {}

    record Text(String value) implements Message {}
    record Count(int value) implements Message {}
    record Point(int x, int y) {}
    record Position(Point point) implements Message {}

    // Java 14: switch expression (no pattern).
    static String dayKind(int day) {
        return switch (day) {
            case 1, 7 -> "WEEKEND";
            default -> {
                yield "WEEKDAY";
            }
        };
    }

    // Java 16: instanceof type pattern.
    static String inspect(Object value) {
        if (value instanceof String s && !s.isBlank()) {
            return "NONBLANK:" + s;
        }
        return "NOT_TEXT";
    }

    // Java 21: pattern switch + when + nested record patterns.
    static String classify(Object value) {
        return switch (value) {
            case Text(String text)
                    when text != null && !text.isBlank() ->
                    "TEXT:" + text.strip();

            case Text(var text) -> "TEXT_EMPTY";

            case Count(int number) when number > 0 ->
                    "COUNT_POS:" + number;

            case Count(int number) ->
                    "COUNT_NONPOS:" + number;

            case Position(Point(int x, int y))
                    when x == 0 && y == 0 ->
                    "ORIGIN";

            case Position(Point(int x, int y)) ->
                    "POINT:" + x + "," + y;

            case Position(var point) -> "NO_POINT";
            case String text -> "RAW:" + text;
            case null -> "NULL";
            default -> "OTHER";
        };
    }

    public static void main(String[] args) {
        System.out.println("day-1=" + dayKind(1));
        System.out.println("day-2=" + dayKind(2));
        System.out.println("instanceof=" + inspect("Java"));
        System.out.println("instanceof-blank=" + inspect(" "));

        System.out.println(classify(new Text(" hello ")));
        System.out.println(classify(new Text(null)));
        System.out.println(classify(new Count(3)));
        System.out.println(classify(new Count(0)));
        System.out.println(classify(
                new Position(new Point(0, 0))));
        System.out.println(classify(
                new Position(new Point(2, 5))));
        System.out.println(classify(new Position(null)));
        System.out.println(classify("legacy"));
        System.out.println(classify(null));
        System.out.println(classify(3.14));
    }
}
```

Compile/run with JDK 21 or newer, targeting Java 21 syntax explicitly:

```bash
javac --release 21 PatternSwitchTimelineDemo.java
java PatternSwitchTimelineDemo
```

**Stdout:**

```text
day-1=WEEKEND
day-2=WEEKDAY
instanceof=NONBLANK:Java
instanceof-blank=NOT_TEXT
TEXT:hello
TEXT_EMPTY
COUNT_POS:3
COUNT_NONPOS:0
ORIGIN
POINT:2,5
NO_POINT
RAW:legacy
NULL
OTHER
```

**Explanation:**

1. The two `day-...` lines use constant labels and `yield`, illustrating the **switch expression** feature rather than pattern switch.
2. `inspect("Java")` binds `String s` after `instanceof` and uses short-circuit `&&`. For a blank string, the result is `NOT_TEXT`.
3. The two `Text` branches place the `when` branch before the general branch. `new Text(null)` enters `TEXT_EMPTY` because the guard `text != null` evaluates to false.
4. The two `Count` branches distinguish positive numbers from non-positive ones.
5. The two nested record branches `Position(Point(...))` distinguish the origin from other points. `Position(null)` does not match `Point(...)` but is still handled by `Position(var point)`.
6. `case String text` handles raw `String` values outside the sealed `Message` hierarchy; `case null` handles a null selector, and `default` catches other types like `Double`.
7. The output proves that syntaxes stabilized at different times can **coexist in a single Java 21 program**.

This is a standalone program, tested on JDK 24 with Java 21 syntax and producing the 14 corresponding stdout lines. If a module must be deployed on Java 17, **you cannot simply copy all of `classify`** and pass `--release 17`: record patterns and `when` in this form are not part of final Java 17.

## 5. Migrating Code Across Versions: Dangerous Changes

### 5.1. Java 17/18 Preview `&&` Guard vs. `when` from Java 19

**Java 17/18 preview form (historical):**

```java
// Java 17/18 preview, not Java 21 guard syntax.
case String s && s.length() > 3 -> "long";
```

**Java 19/20 preview and Java 21 final form:**

```java
// Stable syntax since Java 21.
case String s when s.length() > 3 -> "long";
```

The two snippets above are only **case fragments**, not standalone programs. They also **do not have the same meaning as `instanceof String s && ...`** placed inside a Boolean condition.

If migrating from JDK 17 preview to 21, you must update the **syntax** and review **dominance, exhaustiveness, and null rules** — not merely replace a sequence of tokens.

### 5.2. Null in Preview and Final

Java 21:

```java
Object input = null;

String result = switch (input) {
    case String text -> "text";
    case null -> "missing";
    default -> "other";
};
```

Returns `missing`. If `case null` is omitted and the selector is null, a `NullPointerException` can be thrown, **even when `default` is present**.

Null rules were adjusted during the preview process in Java 19. When reading a Java 17/18 example about **total patterns** and `null`, check the actual JEP/release; do not assume Java 21 behavior. In addition, a nested record pattern does not match a null record component just because the outer selector is non-null.

### 5.3. Exhaustiveness and Runtime Errors

A pattern `switch` expression must cover all possible types. With a sealed hierarchy, the compiler can verify exhaustiveness:

```java
sealed interface Result permits Ok, Error {}
record Ok(String value) implements Result {}
record Error(int code) implements Result {}

// Illustrative snippet inside a method receiving Result result:
return switch (result) {
    case Ok ok -> ok.value();
    case Error error -> "E:" + error.code();
};
```

This snippet **has no `default`** because the permitted subtypes are already covered.

If a subtype is added later and the switch code **is recompiled**, the compiler can require adding a case. If old bytecode is run against a changed hierarchy at runtime, a `MatchException` may occur. The fact that JEP 433 (Java 20 preview) refined runtime errors on enums and Java 21 final uses `MatchException` is a clear example that **semantics can change across previews**.

**Do not fix every exhaustiveness error with `default -> "OTHER"`** if the domain wants the compiler to remind you to handle new subtypes; adding a fallback can hide a change that needs review.

### 5.4. Record Patterns and Generic Type Inference

Given:

```java
record Box<T>(T value) {}
Box<String> box = new Box<>("A");

// Example in a switch expression on box (Java 21):
case Box(String text) -> text;
```

Generic record pattern inference was improved in the Java 20 preview round (JEP 432), then finalized in Java 21 with record patterns (JEP 440). When reading Java 19 preview examples with explicit type arguments or named record patterns, do not assume that code will keep the exact same syntax in Java 21.

**Do not confuse "records can be declared since Java 16" with "record patterns have existed since Java 16".**

## 6. Enabling Preview Properly: Dos and Don'ts

A preview language feature **depends on the JDK version that released it**; enabling `--enable-preview` does not turn every old preview into a stable API in a newer JDK.

| Target | Command/Setting | Notes |
| --- | --- | --- |
| **Java 21 final** | `javac --release 21 App.java` | Uses Java 21 syntax/API; **no preview needed** for final pattern switch or record patterns. |
| **Java 17 preview** | `javac --enable-preview --release 17 App.java` | Must use **JDK 17**, and run with `java --enable-preview App` on JDK 17. |
| **Java 19 preview** | `javac --enable-preview --release 19 App.java` | Must use **JDK 19**, use the corresponding preview syntax, and enable preview at runtime. |
| **Java 20 preview** | `javac --enable-preview --release 20 App.java` | Must use **JDK 20**, not JDK 21. |
| **Java 27 preview extending primitives** | `javac --enable-preview --release 27 App.java` | Must use **JDK 27**, run with `java --enable-preview App`. This is **preview primitive patterns**, not reference pattern switch which has been final since 21. |

`App.java` is only an **illustrative program name**. Replace it with the actual source file matching the chosen version.

To check your environment, run:

```bash
java -version
javac -version
```

In Maven/Gradle, configure the Java toolchain and release/source target consistently with the JDK in use. Syntax highlighting or IDE support **does not guarantee that the CI build uses the same JDK**.

### 6.1. Why Can't JDK 24 Re-enable the Java 17 Preview?

Previews are tied to a specific release. A newer JDK may **not support** recompiling a preview feature from an older release under `--release 17 --enable-preview`. You need JDK 17 to compile the Java 17 preview, or **upgrade the syntax** to the equivalent final feature in Java 21.

What matters in migration is **moving the source to the new standard semantics**, rather than relying on flags to restore a preview version that has already changed.

### 6.2. `--release` and Running on Older Runtimes

`javac --release 21` sets the source language level, class-file target, and Java SE APIs to Java 21. Classes compiled for Java 21 **cannot be assumed** to run on JVM 17.

For example, if an application is still deployed on JVM 17:

- Use `instanceof String s` (final since Java 16) and constant `switch` (Java 14).
- Or plan to upgrade the **runtime target to Java 21+** before using final pattern switch/record patterns.
- Do not just change the source flag in the IDE and hope a Java 17 server understands Java 21 class files.

If a library must support multiple Java levels, use a deliberate strategy (such as separate source sets/modules or a multi-release JAR where appropriate), rather than stuffing Java 21 features into Java 17 sources.

## 7. After Java 21: Pattern Switch Is Final, but Primitive Patterns Still Have Previews

As of **Java 27 (September 2026)**, a separate line of expansion is **Primitive Types in Patterns, `instanceof`, and `switch`**. It **does not revert reference-type pattern switch back to preview**; it only opens up pattern/selector contexts for primitive types, which were restricted in Java 21.

| Release | JEP | Status of Primitive Pattern Extension |
| --- | --- | --- |
| Java **23** | **455** | 1st Preview |
| Java **24** | **488** | 2nd Preview |
| Java **25** | **507** | 3rd Preview |
| Java **26** | **530** | 4th Preview |
| Java **27** | **532** | 5th Preview; still **not final** |

Example of a primitive `long` selector:

```java
// Illustrates primitive switch extension only on a JDK
// with the corresponding preview; NOT valid under --release 21.
long value = 5L;

String label = switch (value) {
    case long n when n > 0L -> "positive";
    case long n -> "non-positive";
};
```

When running the new primitive example on JDK 27, `--enable-preview` for Java 27 is required. Do not copy this example into Java 21 just because `case String s` became final in 21.

For Java 21, supported primitive `switch` selectors include `byte`, `short`, `char`, `int`; the primitive types `long`, `float`, `double`, `boolean` **are not yet allowed as selectors**. The Java 27 preview expands this scope, but its preview status still requires review before adopting it into a stable baseline.

**Out of scope:** Unnamed patterns/variables and other language syntax changes also have their own timelines. Do not lump them into the JEP 406→441 timeline as if they were all one feature.

## 8. Version Selection Table by Requirement

| What You Want to Write | Minimum Final Milestone | Notes |
| --- | --- | --- |
| `switch (int)` returning a value with `case 1 ->` | **Java 14** | Switch expression final; no type pattern needed. |
| `if (obj instanceof String s)` | **Java 16** | `instanceof` pattern final. |
| `sealed interface` with `permits` | **Java 17** | Sealed types final; independent of final pattern switch. |
| `switch (Object) { case String s -> ... }` | **Java 21** | Pattern switch final; Java 17–20 had previews, not final. |
| `case String s when s.length() > 3` | **Java 21** | `when` syntax appeared in Java 19 preview; final since 21. |
| `case Point(int x, int y)` | **Java 21** | Record patterns final; record *declarations* were final since 16. |
| Pattern switch on sealed types, no `default` if exhaustive | **Java 21** | Pattern switch final; sealed types final since 17. |
| `switch(long)` with primitive type patterns | **No final milestone as of Java 27** | Preview JEP 455/488/507/530/532; use the matching JDK and flag. |

**Implementation takeaway:** If you need pattern switch code to run stably for everyone on the team without depending on preview flags, Java 21 is a straightforward baseline. If you still must support Java 17, use type patterns with `instanceof`, pattern-free switch expressions, or keep Java 21 logic in a component with a compatible runtime.

## 9. Common Pitfalls When Reading Examples from Different Releases

1. **Confusing `case ... ->` with pattern switch.** Arrow switch expressions became final in Java 14; pattern cases only became final in 21.
2. **Confusing Java 16's final `instanceof` pattern with switch patterns.** Java 16 does not have final `case String s`.
3. **Confusing record classes with record patterns.** Record classes are final in 16, record patterns are final in 21.
4. **Bringing `case String s && guard` from the Java 17/18 preview into Java 21.** You must use `case String s when guard`.
5. **Assuming Java 19 is final because it has `when`.** Java 19 is still the 3rd preview.
6. **Assuming Java 20 is final because it is close to Java 21.** Java 20 is still the 4th preview.
7. **Assuming `--enable-preview` on a newer JDK re-enables all old previews.** Previews are tied to their release JDK; older code may need edits.
8. **Using `--release 21` while deploying to a Java 17 runtime.** Class files/APIs/source target are incompatible with the older JVM.
9. **Believing `case null` and `default` are equivalent.** Null selectors have specific rules in pattern switch.
10. **Placing a supertype pattern before a subtype pattern.** The compiler may detect a dominated case; guard/case ordering also affects logic.
11. **Believing no exhaustive switch can fail at runtime.** Changing an enum/sealed hierarchy under separate compilation can cause a `MatchException`.
12. **Confusing Java 27 preview primitive patterns with Java 21 final pattern switch.** These are two different stability levels.
13. **Reading old JEP documents as current recommended syntax.** A preview JEP is a snapshot of the design at that time; new code should reference the target JLS/JDK.
14. **Keeping the preview flag in the build without checking if it is needed.** Only enable it if a preview feature of the active JDK is actually used; avoid making the build unnecessarily preview-dependent.

## 10. Checklist for Upgrading Java 17/19/20 to 21

- [ ] Identify the lowest runtime actually used in production and the CI source/toolchain.
- [ ] Locate `case` type/record patterns along with every place using `--enable-preview`.
- [ ] If Java 17/18 code uses `case T t && condition`, convert it to `case T t when condition`.
- [ ] Cross-check precedence of constant labels, guarded patterns, and unguarded patterns.
- [ ] Check null selectors, nullable record components, `case null`, and exception behavior.
- [ ] For sealed hierarchies, verify exhaustive switches and the impact of adding subtypes.
- [ ] For record patterns, review old preview syntax, generic inference, and nested record nulls.
- [ ] Recompile all sources targeting Java 21; do not assume old preview bytecode can be reused.
- [ ] Run unit, integration, and regression tests and verify artifacts/dependencies at runtime.
- [ ] Remove the preview flag once the code only uses features finalized in Java 21.
- [ ] If using Java 23–27 primitive patterns, isolate them in a separate preview component and document the required JDK/flag.

**Remember:** "`switch` with `->`" is a **Java 14** story; "`switch` with `case Type variable`" started **preview in Java 17** and became **final in Java 21**; "`case Record(component patterns)`" became final in **Java 21**; and "`switch` on all primitive types" is still a **preview in Java 27**. When choosing a source level, base it on the **actual syntax of case labels** and the **final/preview status of the features used**, not just the `switch` keyword.

### References

- Oracle Java 21 — Language Changes by Release: https://docs.oracle.com/en/java/javase/21/language/java-language-changes-release.html
- Oracle Java 21 — Pattern Matching for switch: https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html
- Oracle Java 17 — Pattern Matching (preview syntax): https://docs.oracle.com/en/java/javase/17/language/pattern-matching.html
- Oracle Java 27 — Language Changes Summary: https://docs.oracle.com/en/java/javase/27/language/java-language-changes-summary.html
- Oracle Java 27 — Primitive Types in Patterns, instanceof, and switch (preview): https://docs.oracle.com/en/java/javase/27/language/primitive-types-patterns-instanceof-switch.html
- Oracle — Preview Language and VM Features: https://docs.oracle.com/en/java/javase/23/language/preview-language-and-vm-features.html
- OpenJDK JEP 406, 420, 427, 433, 441 (pattern switch): https://openjdk.org/jeps/441
- OpenJDK JEP 405, 432, 440 (record patterns): https://openjdk.org/jeps/440
- OpenJDK JEP 532 (primitive patterns fifth preview): https://openjdk.org/jeps/532
