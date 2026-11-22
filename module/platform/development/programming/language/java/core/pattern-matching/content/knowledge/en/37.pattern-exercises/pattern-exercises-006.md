# Fixing Dominated Case Errors in Java Pattern Matching (Java 21+)

## 1. Practice Objective

When applying type patterns, record patterns, and `when` guards to `switch`, **the order of `case` labels matters**. If a preceding branch already covers every value that a subsequent branch could match, the subsequent branch is called a **dominated case**. Java refuses to compile many such cases because the shadowed branch **can never be selected** under the matching rules.

Typical compiler message:

```text
this case label is dominated by a preceding case label
```

Example that **intentionally does not compile**:

```java
static String label(Object value) {
    return switch (value) {
        case CharSequence sequence -> "SEQUENCE";
        case String text -> "STRING"; // DOMINATED
        case null -> "NULL";
        default -> "OTHER";
    };
}
```

`String` implements `CharSequence`, so every `String` value already matches the `CharSequence` branch. The compiler can never select the `String` branch.

**Fix when `String` needs separate handling:**

```java
static String label(Object value) {
    return switch (value) {
        case String text -> "STRING";
        case CharSequence sequence -> "SEQUENCE";
        case null -> "NULL";
        default -> "OTHER";
    };
}
```

Starting principles:

- For parent/child type relationships: **specific type first, general type after**.
- For the same pattern: **business-meaningful guarded branch first, unguarded branch after**.
- For constant labels and a pattern that covers those constants: place **constants before the general branch** if the selector type permits constants.
- For nested record patterns: examine **both the structure and the type of each component**, not just the outer record name.
- For a `sealed` hierarchy: preserve exhaustive coverage and add tests when adding subtypes.
- Most importantly: **do not just fix to silence the compiler error, preserve the intended business behavior**.

**Version:** Pattern matching for `switch` (JEP 441) and record patterns (JEP 440) became standard features in **Java 21**. This lab uses JDK 21+ and does not require `--enable-preview`. Pattern matching for `instanceof` has been standard since Java 16 (JEP 394).

## 2. Value-Set Model: Understanding Why a Case Is Shadowed

Think of each `case` label as a set of values it can match:

| Case label | Intuitive value set |
| --- | --- |
| `case String s` | Non-null `String` values |
| `case CharSequence cs` | `CharSequence` values, including `String`/`StringBuilder` |
| `case Integer n` | Non-null `Integer` values |
| `case Integer n when n > 0` | Positive `Integer` values |
| `case 0` | The constant value `0`, if the selector type is compatible |
| `case Parcel(var id, int grams)` | `Parcel` records with the matching structure |
| `case Parcel(var id, int grams) when grams > 100` | Subset of `Parcel` with `grams` greater than 100 |
| `case null` | The `null` selector itself; **not** any null record component |

If branch A comes first and the compiler proves that every value matched by branch B is already accepted by A, then B is dominated.

**Important distinction:** The compiler uses the language's static dominance rules; it **cannot solve arbitrary `when` boolean expressions**. There are cases the compiler accepts, yet a reviewer can still see that a later branch is unreachable because an earlier guard shadows it.

Example:

```java
case Integer n when n >= 0 -> "NON_NEGATIVE";
case Integer n when n > 0 -> "POSITIVE";
case Integer n -> "NEGATIVE";
```

For any positive `n`, the first branch evaluates to true first, so the `POSITIVE` branch is never selected. Java 21 **does not necessarily report this as dominated** because it does not prove logical implication between two dynamic guards. This is **semantic shadowing** — a business-logic correctness issue, distinct from compile-time domination.

Hence there are two review layers: **does the compiler accept the switch?** and **do real inputs route to the intended branch?**

## 3. Quick Diagnostic Table

| Case | Java 21 Compiler | How to handle |
| --- | --- | --- |
| `case CharSequence cs` before `case String s` | Dominated | Move `String` before `CharSequence` |
| `case Number n` before `case Integer i` | Dominated | Move `Integer` before `Number` |
| `case String s` before `case String s when s.isBlank()` | Dominated | Move the guarded branch first |
| `case String s when true` before `case String s` | Dominated | Remove the `true` guard or redesign the branches |
| `case Integer i` before `case 0`, selector `Integer` | Dominated | Handle `0` first |
| `case Parcel(var id, int grams)` before `case Parcel(String id, int grams) when grams > 100` | Dominated | Specific/guarded record pattern first |
| `case Integer n when n >= 0` before `case Integer n when n > 0` | May be valid | Fix priority and test the overlap |
| `case 0` in `switch(Object)` | **Incompatible label type** | Use an `Integer` selector or an `Integer` pattern |
| A `switch` expression on `Object` with only `case Integer` | **Non-exhaustive** | Define a fallback or the missing types |
| Two duplicate `case 1` labels | **Duplicate case** | Remove/avoid duplicate constant labels |

Key takeaway from the table: **not every `case`-related compiler error is domination**. Read the exact error location and compiler message before changing code.

## 4. Exercise 1 — Parent Type Pattern Dominates Subtype

### Faulty Code

Save `BadType.java`:

```java
class BadType {
    static String classify(Object value) {
        return switch (value) {
            case CharSequence seq -> "sequence";
            case String s -> "string"; // Dominated
            case null -> "null";
            default -> "other";
        };
    }
}
```

Try compiling on JDK 21:

```bash
javac --release 21 BadType.java
```

A `String` is a `CharSequence`, whereas a `StringBuilder` is not a `String`. Therefore, placing the broader branch first dominates the narrower branch.

### Correct Fix

```java
static String classify(Object value) {
    return switch (value) {
        case String s -> "string";
        case CharSequence seq -> "sequence";
        case null -> "null";
        default -> "other";
    };
}
```

Test matrix:

- `"abc"` → `string`.
- `new StringBuilder("abc")` → `sequence`.
- `42` → `other`.
- `null` → `null`.

**Do not fix by deleting the `String` branch** if business requirements need special handling for `String`. Conversely, if both branches truly have the same behavior, merging them can be a clean refactor.

General case: `Number` can dominate `Integer`, `Long`, `Double`; a parent interface dominates subtypes implementing that interface. Direct class inheritance is not required for a dominance relationship to exist.

## 5. Exercise 2 — Unguarded Branch Dominates Guarded Branch

### Faulty Code

```java
static String classify(Object value) {
    return switch (value) {
        case String s -> "TEXT";
        case String s when s.isBlank() -> "BLANK"; // Dominated
        case null -> "NULL";
        default -> "OTHER";
    };
}
```

The first `String` branch accepts all strings, including empty and blank strings. The `when` condition on the subsequent branch never gets evaluated.

### Fix

```java
static String classify(Object value) {
    return switch (value) {
        case String s when s.isBlank() -> "BLANK";
        case String s -> "TEXT";
        case null -> "NULL";
        default -> "OTHER";
    };
}
```

Test `""` and `"  "` → `BLANK`; `"abc"` → `TEXT`.

**Note:** A guard is evaluated only after the pattern itself matches, and a guard returning `false` lets the `switch` try subsequent labels. If a guard throws an exception, the exception propagates outward; **it is not treated as `false`**.

### Special Case: `when true`

```java
// Does not compile:
case String s when true -> "ANY_STRING";
case String s -> "OTHER_STRING"; // Dominated
```

The Java 21 JLS treats `when true` as **unguarded** for dominance purposes. Do not add `when true` to "work around" the compiler, and do not treat it as a placeholder for a guard to be written later.

If the guard is a method call, the compiler does not prove that the method always returns `true`. Therefore, "the compiler didn't complain" does not mean the later branch is reachable.

## 6. Exercise 3 — Constant Label Covered by Pattern

Example that intentionally does not compile:

```java
class BadConstant {
    static String classify(Integer value) {
        return switch (value) {
            case Integer n -> "INTEGER";
            case 0 -> "ZERO"; // Dominated
        };
    }
}
```

The type pattern `case Integer n` already accepts `Integer` equal to `0`, so the `case 0` label is dominated.

### Fix

```java
static String classify(Integer value) {
    return switch (value) {
        case 0 -> "ZERO";
        case Integer n when n < 0 -> "NEGATIVE:" + n;
        case Integer n -> "POSITIVE:" + n;
        case null -> "NO_NUMBER";
    };
}
```

The value `0` is matched first, then negative numbers, and the rest are positive numbers. `case null` returns a separate result for a `null` selector.

**Watch the selector type:** `case 0` is **invalid** in `switch(Object)` in Java 21. In that case the compiler reports an incompatible constant label type, not dominance:

```java
// Does not compile in Java 21:
Object value = Integer.valueOf(0);
String result = switch (value) {
    case 0 -> "ZERO"; // Constant label incompatible with Object
    default -> "OTHER";
};
```

To classify `0` from an `Object`, you can write:

```java
static String classify(Object value) {
    return switch (value) {
        case Integer n when n == 0 -> "ZERO";
        case Integer n -> "INTEGER:" + n;
        case null -> "NULL";
        default -> "OTHER";
    };
}
```

Do not just change the selector type to make the compiler happy if the business logic also receives `String`, `Number`, or other record types.

### Guarded Pattern Before a Constant: Valid Syntax, Wrong Priority

```java
// Case fragment in a switch over Integer:
case Integer n when n > 0 -> "POSITIVE";
case 1 -> "ONE";
case Integer n -> "OTHER";
```

The compiler may accept this because a guarded pattern `n > 0` is not treated as an unguarded pattern that dominates a constant. However, for `value=1`, the first branch already returns `POSITIVE`, so the `ONE` branch never runs.

If `ONE` needs priority:

```java
case 1 -> "ONE";
case Integer n when n > 0 -> "POSITIVE";
case Integer n -> "OTHER";
```

**Conclusion:** Compile-time domination and runtime rule priority are two different checks. You must test values that can match multiple branches.

## 7. Exercise 4 — General Record Pattern Dominates Narrower Record Pattern

Suppose:

```java
record Parcel(String id, int grams) {}
```

**Incorrect** snippet:

```java
static String group(Object value) {
    return switch (value) {
        case Parcel(var id, int grams) -> "PARCEL";
        case Parcel(String id, int grams)
                when grams > 100 -> "HEAVY"; // Dominated
        case null -> "MISSING";
        default -> "OTHER";
    };
}
```

`case Parcel(var id, int grams)` already accepts `Parcel` instances with `grams` of 101, 1000, etc.; the remaining branch can never be selected. The compiler diagnoses dominance much like a type pattern.

Fix:

```java
static String group(Object value) {
    return switch (value) {
        case Parcel(var id, int grams) when grams > 100 ->
                "HEAVY";
        case Parcel(var id, int grams) -> "PARCEL";
        case null -> "MISSING";
        default -> "OTHER";
    };
}
```

Test: `Parcel("A",100)` → `PARCEL`; `Parcel("A",101)` → `HEAVY`. `Parcel("A",-1)` still returns `PARCEL` in the code above; **this is not weight validation**. If the business rules forbid negative numbers, add a rejection condition rather than assuming pattern matching enforces every invariant.

**With nested record patterns:** the matching order of components affects whether one pattern covers another. The pattern `Delivery(Address(...))` will not match if the `Address` component itself is `null`; reviewers need to consider nullable components and write tests rather than just counting nesting depth. The dominance specification for record patterns is based on the types and structure of the pattern, not on whether variable names match.

## 8. Exercise 5 — General Case in a Sealed Hierarchy

`sealed` restricts the permitted subtypes, allowing the compiler to verify switch exhaustiveness.

```java
sealed interface Event permits TextEvent, CountEvent {}
record TextEvent(String text) implements Event {}
record CountEvent(int value) implements Event {}
```

Incorrect:

```java
// Does not compile:
return switch (event) {
    case Event e -> "EVENT";
    case TextEvent t -> "TEXT";  // Dominated
    case CountEvent c -> "COUNT"; // Dominated
    case null -> "NULL";
};
```

Every `TextEvent` and `CountEvent` is an `Event`. The `Event` branch placed first accepts them all.

Fix:

```java
return switch (event) {
    case TextEvent t -> "TEXT";
    case CountEvent c -> "COUNT";
    case null -> "NULL";
};
```

There is no need to add a `default` when the compiler can verify that all permitted subtypes are handled. If a new subtype is added later, any `switch` missing a branch for the new type will require updating at recompile time.

**Do not confuse these concepts:**

| Property | Question |
| --- | --- |
| **Dominance** | Is a later branch completely covered by an earlier branch? |
| **Exhaustiveness** | Is there a handling path for every selector value in the valid domain? |
| **Runtime matching** | For a specific input, which branch is selected? |
| **Business completeness** | Are the business rules accurate and complete? |

An exhaustive `switch` can still have guards in the wrong priority order; a `switch` without dominated cases can still have wrong business logic. If a class hierarchy or enum changes across separate compilation, runtime can also throw `MatchException` when an older exhaustive `switch` encounters a value with no matching label. That error is different from a compile-time dominated case.

## 9. Complete Java 21 Program: Fix and Test

This lab combines four exercises into a single standalone program:

- `classifyEvent` uses sealed records and record patterns, placing guards before the fallback.
- `classifyObject` places `String` before `CharSequence`, and `Integer` before `Number`.
- `classifyInteger` places constant `0` before the `Integer` pattern.
- `referenceEvent` and `referenceObject` are written with `if/instanceof` as reference oracles.
- `overlapping` intentionally contains semantic shadowing (which compiles) to illustrate compiler limits.
- Verifies **25 specific test cases**, plus **48 regression checks** without throwing errors.

Save **`DominatedCaseRepairLab.java`**:

```java
public class DominatedCaseRepairLab {
    sealed interface Event permits Text, Metric, Heartbeat {}

    record Text(String value) implements Event {}
    record Metric(int value) implements Event {}
    record Heartbeat() implements Event {}

    static String classifyEvent(Event event) {
        return switch (event) {
            case Text(String text)
                    when text != null && text.isBlank() ->
                    "TEXT_BLANK";

            case Text(String text)
                    when text != null && text.length() >= 5 ->
                    "TEXT_LONG:" + text.length();

            case Text(var text) ->
                    "TEXT:" + text;

            case Metric(int n) when n == 0 ->
                    "METRIC_ZERO";

            case Metric(int n) when n < 0 ->
                    "METRIC_NEGATIVE";

            case Metric(int n) ->
                    "METRIC:" + n;

            case Heartbeat() ->
                    "HEARTBEAT";

            case null ->
                    "MISSING_EVENT";
        };
    }

    static String referenceEvent(Event event) {
        if (event == null) return "MISSING_EVENT";

        if (event instanceof Text t) {
            String text = t.value();

            if (text != null && text.isBlank())
                return "TEXT_BLANK";

            if (text != null && text.length() >= 5)
                return "TEXT_LONG:" + text.length();

            return "TEXT:" + text;
        }

        if (event instanceof Metric m) {
            int n = m.value();

            if (n == 0) return "METRIC_ZERO";
            if (n < 0) return "METRIC_NEGATIVE";

            return "METRIC:" + n;
        }

        if (event instanceof Heartbeat)
            return "HEARTBEAT";

        throw new AssertionError("unknown event");
    }

    static String classifyObject(Object value) {
        return switch (value) {
            case String text when text.isBlank() ->
                    "RAW_BLANK";

            case String text ->
                    "RAW:" + text;

            case CharSequence other ->
                    "SEQUENCE:" + other.length();

            case Integer n when n == 0 ->
                    "INT_ZERO";

            case Integer n ->
                    "INT:" + n;

            case Number n ->
                    "NUMBER:" + n;

            case null ->
                    "NULL";

            default ->
                    "OTHER";
        };
    }

    static String referenceObject(Object value) {
        if (value == null)
            return "NULL";

        if (value instanceof String text)
            return text.isBlank() ? "RAW_BLANK" : "RAW:" + text;

        if (value instanceof CharSequence other)
            return "SEQUENCE:" + other.length();

        if (value instanceof Integer n)
            return n == 0 ? "INT_ZERO" : "INT:" + n;

        if (value instanceof Number n)
            return "NUMBER:" + n;

        return "OTHER";
    }

    static String classifyInteger(Integer value) {
        return switch (value) {
            case 0 -> "ZERO";

            case Integer n when n < 0 ->
                    "NEGATIVE:" + n;

            case Integer n ->
                    "POSITIVE:" + n;

            case null ->
                    "NO_NUMBER";
        };
    }

    // Compiles, but the n>0 branch is logically shadowed by n>=0
    // for all positive numbers.
    static String overlapping(Integer value) {
        return switch (value) {
            case Integer n when n >= 0 ->
                    "NON_NEGATIVE";

            case Integer n when n > 0 ->
                    "POSITIVE";

            case Integer n ->
                    "NEGATIVE";

            case null ->
                    "NULL";
        };
    }

    static void assertEqual(
            String expected, String actual, String context) {
        if (!java.util.Objects.equals(expected, actual)) {
            throw new AssertionError(
                    context + " expected=" + expected
                            + " actual=" + actual);
        }
    }

    static void checkEvent(
            String label, Event event, String expected) {
        String actual = classifyEvent(event);

        assertEqual(expected, actual, label);
        assertEqual(
                referenceEvent(event), actual,
                label + " oracle");

        System.out.println(label + " => " + actual);
    }

    static void checkObject(
            String label, Object value, String expected) {
        String actual = classifyObject(value);

        assertEqual(expected, actual, label);
        assertEqual(
                referenceObject(value), actual,
                label + " oracle");

        System.out.println(label + " => " + actual);
    }

    static void checkInteger(
            String label, Integer value, String expected) {
        String actual = classifyInteger(value);

        assertEqual(expected, actual, label);
        System.out.println(label + " => " + actual);
    }

    public static void main(String[] args) {
        checkEvent(
                "event-empty", new Text(""), "TEXT_BLANK");
        checkEvent(
                "event-blank", new Text("  "), "TEXT_BLANK");
        checkEvent(
                "event-short", new Text("hey"), "TEXT:hey");
        checkEvent(
                "event-boundary",
                new Text("abcde"), "TEXT_LONG:5");
        checkEvent(
                "event-long",
                new Text("abcdef"), "TEXT_LONG:6");
        checkEvent(
                "event-null-component",
                new Text(null), "TEXT:null");
        checkEvent(
                "event-zero", new Metric(0), "METRIC_ZERO");
        checkEvent(
                "event-negative",
                new Metric(-2), "METRIC_NEGATIVE");
        checkEvent(
                "event-positive",
                new Metric(7), "METRIC:7");
        checkEvent(
                "event-heartbeat",
                new Heartbeat(), "HEARTBEAT");
        checkEvent(
                "event-null-selector",
                null, "MISSING_EVENT");

        checkObject(
                "raw-blank", "  ", "RAW_BLANK");
        checkObject(
                "raw-string", "hello", "RAW:hello");
        checkObject(
                "raw-builder",
                new StringBuilder("xy"), "SEQUENCE:2");
        checkObject(
                "raw-int-zero", 0, "INT_ZERO");
        checkObject(
                "raw-int-negative", -3, "INT:-3");
        checkObject(
                "raw-int", 42, "INT:42");
        checkObject(
                "raw-long", 42L, "NUMBER:42");
        checkObject(
                "raw-double", 2.5, "NUMBER:2.5");
        checkObject(
                "raw-null", null, "NULL");
        checkObject(
                "raw-other", true, "OTHER");

        checkInteger(
                "int-zero", 0, "ZERO");
        checkInteger(
                "int-negative", -5, "NEGATIVE:-5");
        checkInteger(
                "int-positive", 8, "POSITIVE:8");
        checkInteger(
                "int-null", null, "NO_NUMBER");

        int checks = 0;
        for (int n = -20; n <= 20; n++) {
            Event event = new Metric(n);

            assertEqual(
                    referenceEvent(event),
                    classifyEvent(event),
                    "metric sweep " + n);

            checks++;
        }

        for (String s : new String[] {
                null, "", " ", "a", "abcd", "abcde", "abcdef"
        }) {
            Event event = new Text(s);

            assertEqual(
                    referenceEvent(event),
                    classifyEvent(event),
                    "text sweep " + s);

            checks++;
        }

        System.out.println(
                "regression=" + checks + " PASS");
        System.out.println(
                "overlap-positive=" + overlapping(3));
    }
}
```

Compile and run with JDK 21+:

```bash
javac --release 21 DominatedCaseRepairLab.java
java DominatedCaseRepairLab
```

**Exact stdout:**

```text
event-empty => TEXT_BLANK
event-blank => TEXT_BLANK
event-short => TEXT:hey
event-boundary => TEXT_LONG:5
event-long => TEXT_LONG:6
event-null-component => TEXT:null
event-zero => METRIC_ZERO
event-negative => METRIC_NEGATIVE
event-positive => METRIC:7
event-heartbeat => HEARTBEAT
event-null-selector => MISSING_EVENT
raw-blank => RAW_BLANK
raw-string => RAW:hello
raw-builder => SEQUENCE:2
raw-int-zero => INT_ZERO
raw-int-negative => INT:-3
raw-int => INT:42
raw-long => NUMBER:42
raw-double => NUMBER:2.5
raw-null => NULL
raw-other => OTHER
int-zero => ZERO
int-negative => NEGATIVE:-5
int-positive => POSITIVE:8
int-null => NO_NUMBER
regression=48 PASS
overlap-positive=NON_NEGATIVE
```

The program was executed using **JDK 24 JShell** with Java 21 syntax, producing the **26 stdout lines** above (plus the regression summary). The `assertEqual` methods compare outputs against expected values and an independent baseline, throwing `AssertionError` on mismatch. The regression loop checks 41 `int` values from -20 to 20 and 7 strings, totaling **48 checks**. Use `javac --release 21` to compile the code when saving the file in a compatible project.

**Intentional:** the `overlapping` method is an **unfixed logic bug example**, and the line `overlap-positive=NON_NEGATIVE` illustrates that `when n >= 0` captures input `3` before `when n > 0`. Do not use this function as a real classifier if you expect it to return `POSITIVE`.

## 10. Analysis of the Three Pattern Groups in the Lab

### 10.1. Text: Priority Guards Before Fallback

```java
case Text(String text)
        when text != null && text.isBlank() -> "TEXT_BLANK";

case Text(String text)
        when text != null && text.length() >= 5 ->
        "TEXT_LONG:" + text.length();

case Text(var text) -> "TEXT:" + text;
```

- Blank and empty strings → first branch.
- Non-blank strings of length 5 or more → second branch.
- Shorter strings or component `text == null` → fallback branch.

Here `String.length()` counts UTF-16 code units, not user-perceived characters. If business logic requires grapheme cluster length, you must change the contract and implementation rather than just fixing a dominated case.

`text != null && ...` avoids an NPE via short-circuiting. With `new Text(null)`, the selector is a **non-null** `Text` record; `case null` does not handle a null record component.

### 10.2. Metric: Boundary Values Before General Pattern

```java
case Metric(int n) when n == 0 -> "METRIC_ZERO";
case Metric(int n) when n < 0 -> "METRIC_NEGATIVE";
case Metric(int n) -> "METRIC:" + n;
```

Zero, negative, and positive values are clearly separated. The final unguarded branch acts as a fallback for `Metric`. Placing it first would dominate the specialized branches below it.

### 10.3. Object: Two Independent Overlapping Type Hierarchies

```java
case String text when text.isBlank() -> "RAW_BLANK";
case String text -> "RAW:" + text;
case CharSequence other -> "SEQUENCE:" + other.length();

case Integer n when n == 0 -> "INT_ZERO";
case Integer n -> "INT:" + n;
case Number n -> "NUMBER:" + n;
```

In the first group, `String` must precede `CharSequence`. In the second group, `Integer` must precede `Number`. `StringBuilder` and `Long` in the tests demonstrate that the general branches **still receive their own inputs** and are not dead code.

For `String`, the blank guard precedes unguarded `String`. For `Integer`, the zero guard precedes unguarded `Integer`. The `->` arrow guarantees no fall-through to subsequent branches once a rule is selected.

## 11. Overlapping Guards Not Always Detected by `javac`

Consider:

```java
case Integer n when n >= 10 -> "AT_LEAST_TEN";
case Integer n when n > 100 -> "VERY_LARGE";
case Integer n -> "SMALL";
```

If `n=101`, both of the first two guards evaluate to true; the first case returns `AT_LEAST_TEN`. The compiler may allow this to compile because it does not generally prove logical implication between guard conditions.

If `VERY_LARGE` should take priority:

```java
case Integer n when n > 100 -> "VERY_LARGE";
case Integer n when n >= 10 -> "AT_LEAST_TEN";
case Integer n -> "SMALL";
```

Tests must cover **9, 10, 100, 101**. This is **business-overlap analysis**, not just a compiler fix. Guards can invoke arbitrary methods; for methods with side effects, changing branch order can also alter call counts and state, so tests must account for that.

### A Pattern to Avoid: Side Effects in Guards

```java
// Illustrative anti-pattern; not a standalone program:
// case Transfer t when chargeCard(t) -> "PAID";
// case Transfer t -> "REJECTED";
```

If `chargeCard(t)` deducts money before returning `false`, the `switch` may proceed to the next branch while the side effect has already occurred. Use pure guards for condition checks, and perform actions inside the selected handler protected by appropriate transactions/idempotency. A `switch` free of dominated cases **does not automatically mean** it is safe with respect to side effects.

## 12. Null, Default, and Exhaustiveness Are Not Interchangeable

- **`case null`** checks whether the selector itself is `null`.
- **`default`** is the fallback branch for values with no other applicable `case` under `switch` semantics; in a Java 21 pattern `switch`, it **does not implicitly cover a `null` selector**.
- A **nested record pattern** may fail to match when a nested record component is `null`, even if the outer record is non-null.
- **Exhaustiveness** is the requirement that a `switch` expression or enhanced `switch` has a handling path for every selector value under the compile-time model.
- **Dominance** is the error where a `case` is shadowed by a preceding `case`. These are two distinct concepts.

If you delete a general branch to fix dominance, the compiler may report **switch not exhaustive** because another type now lacks a handling path. That is not a reason to slap on `default -> null`; determine how the remaining cases should be handled according to the business contract.

With a `sealed` hierarchy, omitting `default` is often an advantage: adding a new subtype forces the compiler to flag `switch` statements that need updating upon recompilation. However, separate compilation can cause runtime mismatches; if a `MatchException` occurs, investigate class/hierarchy versions or null components at the appropriate layer.

## 13. Repair Workflow in Code Review

**Step 1 — Identify the selector type.** `switch(Object)`, `switch(Integer)`, and `switch(SealedInterface)` have different valid labels and exhaustiveness requirements.

**Step 2 — Find the covering branch.** Scan upward from the failing `case` and check parent/child types, record shapes, unguarded patterns, constants, and `when true`. Do not inspect only the two adjacent lines; the dominating branch may be at the top of the `switch`.

**Step 3 — Confirm business priority.** For example, "`Integer` needs special handling" differs from "`Integer` can share `Number` handling". Only reorder branches if that matches the intended behavior.

**Step 4 — Choose a fix.** Move the specific `case` earlier, narrow a guard, merge branches with identical behavior, or extract long logic into a clear helper. Do not replace a compiler error with manual casts that risk a runtime `ClassCastException`.

**Step 5 — Recompile.** Use JDK 21+ with the appropriate source level; if the tooling reports a preview feature error due to source level 17–20, that is a JDK configuration issue rather than dominance.

**Step 6 — Test the overlap region.** Focus on values that can match multiple branches: `String` and `CharSequence` subtypes, `Integer` and `Number`, `0`, guard boundary values, `null` selector, `null` components, and nested records.

**Step 7 — Verify exceptions and side effects.** When reordering cases whose handlers affect system state, compare not only return values but also database changes, emitted events, exception types, and invocation counts.

**Step 8 — Review exhaustive coverage.** If adding a subtype to a `sealed` model or removing a general branch, add the proper `case` branches rather than hiding gaps behind an unconditional `default`.

## 14. Quick-Fix Mistakes to Avoid

1. Deleting the flagged branch without understanding the business contract.
2. Adding a `default` to "fix" a dominated pattern; this can trigger other errors or hide domain gaps.
3. Using `when true` to bypass the compiler, when it is treated as an unguarded branch for dominance.
4. Putting a supertype at the top of a `switch` and expecting subtype cases below it to still run.
5. Calling impure methods in guards just to avoid dominance.
6. Assuming the compiler will catch every pair of overlapping guards.
7. Failing to test overlap/boundary values because only the happy path was run.
8. Confusing an incompatible constant error with a dominated case.
9. Confusing duplicate constant labels with a dominated case.
10. Confusing non-exhaustiveness with a dominated case.
11. Forgetting that a `null` selector and a `null` nested record component behave differently.
12. Ignoring the order and types of record components in nested record patterns.
13. Rewriting to manual `instanceof`/cast chains without preserving exceptions and side effects.
14. Reordering branches and altering business priority without regression tests.
15. Putting an overly broad pattern (`case Object o`, `case Event e`) at the top while keeping specific cases below it.
16. Assuming a green compilation means all types and guards are thoroughly tested.
17. Overlooking Java versions: pattern `switch` and record patterns require Java 21 final.
18. Using `String.length()` and assuming UTF-16 code units equal user-perceived Unicode characters in every domain.

## 15. Practice Exercises (with Fix Hints)

### Exercise 1 — `Number` and `Integer`

```java
// Wrong:
case Number n -> "NUMBER";
case Integer i -> "INTEGER";

// Fix:
case Integer i -> "INTEGER";
case Number n -> "NUMBER";
```

Run tests with `Integer.valueOf(5)` and `Double.valueOf(2.5)`. Remember that the snippets above are **switch label fragments**; place them inside a `switch` with an appropriate selector to run.

### Exercise 2 — Guard on a Record

```java
// Wrong:
case Parcel(var id, int grams) -> "NORMAL";
case Parcel(var id, int grams) when grams > 100 -> "HEAVY";

// Fix:
case Parcel(var id, int grams) when grams > 100 -> "HEAVY";
case Parcel(var id, int grams) -> "NORMAL";
```

Test `grams` 100 and 101; if the domain forbids negative values, add a validation branch.

### Exercise 3 — Guard Logic Without a Compile Error

```java
// Wrong number classification intent:
case Integer n when n >= 10 -> "TEN_PLUS";
case Integer n when n > 100 -> "VERY_LARGE";
case Integer n -> "SMALL";
```

Move `n > 100` before `n >= 10`; write tests for 9/10/100/101. Focus on **priority order**, not merely whether the compiler accepts the code.

### Exercise 4 — Adding a Sealed Subtype

Given `sealed interface Message permits TextMessage, ImageMessage` with an existing exhaustive `switch`, add `VideoMessage` and recompile. Add the handling branch and tests rather than using `default` to avoid designing the new behavior.

### Exercise 5 — Before/After Comparison

Write an `if/instanceof` oracle for a `switch` you are refactoring. Create a decision table for `String`/`CharSequence`, `Integer`/`Number`, and `null`. Verify before/after results across the corresponding inputs, including overlapping values.

## 16. Pre-Approval Checklist

- [ ] Are the selector type and JDK source level set to Java 21+?
- [ ] Have you identified the exact preceding `case` that covers the failing `case`?
- [ ] Does the subtype precede the supertype when it has distinct handling?
- [ ] Does the guarded case precede the same unguarded pattern?
- [ ] Do special constant labels precede the type pattern covering them when the selector allows?
- [ ] Have you avoided `when true` or artificial guards just to get past the compiler?
- [ ] For record patterns, have you checked component type order and nullability?
- [ ] For `sealed` switches, have you preserved exhaustiveness checks and tested new subtypes?
- [ ] Did you test both guard overlaps and boundaries, not just a single random input?
- [ ] Did you distinguish dominated, duplicate, non-exhaustive, and incompatible constant errors?
- [ ] Does the refactor preserve outputs, exceptions, side effects, and business priority?
- [ ] Are helpers/fallbacks clearly named and free of silently masking invalid data?
- [ ] Are guards pure enough to be safe when evaluated even if the branch is not selected?

**Conclusion:** Fixing a dominated case is not simply swapping two lines. You must find **which branch covers which**, determine **which policy takes priority**, reorder from specific/guarded to general, and test inputs that can match multiple labels. The Java 21 compiler catches many dominated patterns, but **logically overlapping guards can still slip through**, making tests and code review decisive.

### References

- Oracle Java 21 — Pattern Matching for switch, section Pattern Label Dominance: https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html
- Java Language Specification SE 21 — `14.11.1 Switch Blocks` and `14.30.3 Pattern Dominance`: https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html
- OpenJDK JEP 441 — Pattern Matching for switch: https://openjdk.org/jeps/441
- OpenJDK JEP 440 — Record Patterns: https://openjdk.org/jeps/440
- OpenJDK JEP 394 — Pattern Matching for instanceof: https://openjdk.org/jeps/394
- Oracle Java 21 — Record Patterns: https://docs.oracle.com/en/java/javase/21/language/record-patterns.html
