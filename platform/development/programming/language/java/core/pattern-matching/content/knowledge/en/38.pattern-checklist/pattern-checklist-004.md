# Checklist for Ordering `case` Labels in Java Pattern Matching

## 1. Purpose of the checklist

When writing pattern matching for `switch`, **the order of `case` labels is part of program behavior**, not merely a matter of clean formatting. The same selector can match multiple patterns or guards; Java selects the branch that satisfies the matching rules in the order they appear in the `switch`. Some incorrect orders are blocked by the compiler with a **dominance** error, but other orders still compile while producing wrong business results.

This article is a practical checklist for **ordering, reviewing, and testing `case` branches** in Java 21, covering scenarios with:

- Specific constants, type patterns, parent–child types, and interfaces.
- True/false `when` guards and unguarded fallback branches.
- Nested record patterns and null component data.
- `case null`, `default`, and values outside the current set of patterns.
- `sealed` hierarchies, enums, and generic collections.
- Risks of changing behavior when refactoring order, and differences from classic `switch` with fall-through.

**Version:** type patterns in `switch` and record patterns have both been standard features since **Java 21** (JEP 441, JEP 440), requiring no `--enable-preview`. Complete examples use `javac --release 21`.

## 2. Core principle: the first matching case wins

Consider a string object `"hello"`. It is simultaneously a `String`, a `CharSequence`, and an `Object`. Therefore, a `switch(Object)` with multiple type patterns can have labels with **overlapping value domains**.

Java evaluates switch labels in order of appearance to select the appropriate branch; the compiler also checks **dominance** and rejects many cases where a later label cannot match because a preceding label already covers all corresponding values.

Key distinctions to keep in mind:

1. **Static dominance error:** the compiler proves that a later label is completely shadowed by an earlier label. The source **does not compile**.
2. **Business priority bug:** the compiler cannot or does not have to prove overlapping guard conditions; the source may compile, but the intended branch is not selected.
3. **Non-exhaustiveness error:** after reordering, a `switch` expression or enhanced switch statement may lack a path for a valid subtype/value.
4. **Runtime logic bug:** branches may be type-complete yet return wrong results, handle `null` incorrectly, or throw unexpected errors.

A `switch` is not a "rule engine that automatically picks the most specific case". **Design the order explicitly.**

## 3. Quick checklist before reviewing individual branches

When you need an easy-to-understand order for a pattern `switch`, a generally useful priority is:

1. **Special constants/enum constants before** patterns that accept many values of the same type, if the selector and label kinds allow it.
2. **Specific patterns with guards** before unguarded patterns of the same type.
3. **Specific subtypes** before general supertypes/interfaces.
4. **Nested record patterns and specific structural conditions** before broader patterns of the same record type.
5. **General unguarded patterns** to handle the rest of the type, when that is the intended contract.
6. **`case null`** in a clearly visible position (usually at the beginning or near the end); it has its own semantics.
7. **`default` last** when a fallback for remaining values is truly needed.

These are **design guidelines, not mandatory syntax rules for every `switch`**. For example, `case null` can be valid after `case Object o`, because the type pattern `Object o` at the outer selector does not match `null`. However, `default` cannot arbitrarily precede new patterns, and `case null, default` should be placed last.

**The number-one priority is preserving business semantics** and satisfying the compiler, not mechanically sorting by a frequency table.

## 4. Dominance: place specialized types before general types

### Incorrect snippet — intentionally does not compile

```java
static String wrong(Object value) {
    return switch (value) {
        case CharSequence sequence -> "sequence";
        case String text -> "string";
        default -> "other";
    };
}
```

`String implements CharSequence`, so any non-null string that matches `String` has already matched `CharSequence` earlier. The Java 21 compiler reports that **case `String` is dominated**.

### Fixed order

```java
static String correct(Object value) {
    return switch (value) {
        case String text -> "string";
        case CharSequence sequence -> "sequence";
        case null -> "null";
        default -> "other";
    };
}
```

The methods above are **illustrative snippets inside a class**, not standalone programs. With the correct version:

- `"hi"` → `"string"`.
- `new StringBuilder("hi")` → `"sequence"`.
- `null` → `"null"`.
- `42` → `"other"`.

**Review:** inspect all `extends`/`implements` relationships, not just direct class inheritance. For example, `ArrayList<?>` is also a `List<?>`, and multiple distinct interfaces can still be implemented by the same class.

## 5. Constants before broad type patterns: the compiler can block shadowed labels

An unguarded type pattern can match **every value corresponding to that type**; it can shadow constants of the same type as well.

The snippet below **intentionally does not compile**:

```java
static String wrong(String command) {
    return switch (command) {
        case String value -> "any-string";
        case "START" -> "start";
        case null -> "null";
    };
}
```

The `"START"` case is swallowed by the preceding `String value` pattern. The compiler reports dominance; you cannot "just leave it because `START` is rare".

The right way to write it with special cases:

```java
static String correct(String command) {
    return switch (command) {
        case "START", "BEGIN" -> "start";
        case String value when value.isBlank() -> "blank";
        case String value -> "text:" + value;
        case null -> "null";
    };
}
```

Here, the constants `"START"` and `"BEGIN"` come before the guard and the general string pattern; the `when` keyword only adds a condition to its corresponding type pattern. There is no `default` because `String value` handles all non-null strings and `case null` handles null.

## 6. Runnable example: constants, guards, type patterns, and null

Save `ConstantCaseDemo.java`:

```java
public class ConstantCaseDemo {
    static String label(String value) {
        return switch (value) {
            case "START", "BEGIN" ->
                    "start";

            case String text when text.isBlank() ->
                    "blank";

            case String text ->
                    "text:" + text;

            case null ->
                    "null";
        };
    }

    public static void main(String[] args) {
        String[] inputs = {
            "START", "BEGIN", " ", "hello", null
        };

        for (String input : inputs) {
            System.out.println(label(input));
        }
    }
}
```

```bash
javac --release 21 ConstantCaseDemo.java
java ConstantCaseDemo
```

Exact stdout:

```text
start
start
blank
text:hello
null
```

From this example, we can derive a practical rule: **special values → special guards → general patterns → null policy**. This rule should be turned into tests, especially whenever the constant list changes or multiple guards share the same type.

## 7. `when` guards: the compiler does not always catch priority mistakes

Labels with `when` are not necessarily treated by the compiler as completely covering a constant that follows, even when the guard is in fact true for that constant. Therefore, the following code **can compile** yet produce unexpected results if business logic requires prioritizing the number `1`:

```java
static String surprising(Integer value) {
    return switch (value) {
        case Integer number when number > 0 -> "positive";
        case 1 -> "one";
        case Integer number -> "other";
        case null -> "null";
    };
}
```

When `value = 1`, the preceding guarded branch matches and returns `"positive"`, so the `case 1` branch is never chosen. This is a **business priority bug**, not a static dominance error in this situation.

### A clearer intent-revealing order

```java
static String classify(Integer value) {
    return switch (value) {
        case 1 -> "one";
        case Integer number when number > 0 -> "positive";
        case Integer number -> "other";
        case null -> "null";
    };
}
```

- `classify(1)` → `"one"`.
- `classify(2)` → `"positive"`.
- `classify(-1)` → `"other"`.
- `classify(null)` → `"null"`.

**Checklist:** when a guarded case and a constant case have overlapping conditions, place **important constants first**, unless business logic intentionally gives priority to the guard. Do not conclude that the order is right merely because the code compiles.

## 8. Complete example: classifying `Object` with guards and hierarchy

Save `CaseOrderingDemo.java`:

```java
public class CaseOrderingDemo {
    static String describe(Object input) {
        return switch (input) {
            case String text when text.isBlank() ->
                    "blank";

            case String text ->
                    "text:" + text;

            case CharSequence sequence ->
                    "sequence:" + sequence.length();

            case Number number
                    when number.doubleValue() >= 0 ->
                    "nonnegative:" + number;

            case Number number ->
                    "negative:" + number;

            case null ->
                    "null";

            default ->
                    "other";
        };
    }

    public static void main(String[] args) {
        Object[] inputs = {
            "",
            "java",
            new StringBuilder("xy"),
            2,
            -3,
            null,
            new Object()
        };

        for (Object value : inputs) {
            System.out.println(describe(value));
        }
    }
}
```

```bash
javac --release 21 CaseOrderingDemo.java
java CaseOrderingDemo
```

Stdout:

```text
blank
text:java
sequence:2
nonnegative:2
negative:-3
null
other
```

**Order analysis:**

- `case String ... when ...` precedes `case String ...` to handle blank strings.
- Both `String` cases precede `CharSequence`, because `String` is a subtype of `CharSequence`.
- For `Number`, the guard for non-negative numbers precedes the unguarded `Number` branch.
- `case null` handles a null selector; `default` handles all remaining non-null types not belonging to the groups above.

In the example, `number.doubleValue()` is used for simple numeric grouping. For extremely large numbers, `NaN`, `BigDecimal`, or monetary precision requirements, a different domain-appropriate comparison rule is needed. This article tests **case ordering**, not asserting that this numeric comparison is standard for all business domains.

## 9. Record patterns: specific structure before general fallback

Record patterns allow matching on the components of a record. If one branch has a nested record pattern and another branch only matches the outer record, prioritize the more specific classifying branch first.

Model example:

```java
record Payload(int code) {}
record Packet(String id, Payload payload) {}
```

A reasonable order:

```java
static String describe(Object value) {
    return switch (value) {
        case Packet(var id, Payload(var code))
                when code >= 400 ->
                "error:" + id + ":" + code;

        case Packet(var id, Payload(var code)) ->
                "ok:" + id + ":" + code;

        case Packet(var id, var payload) ->
                "missing-payload:" + id;

        case null -> "null";
        default -> "other";
    };
}
```

This is an **illustrative snippet placed in the same scope as the two records**, not a standalone file. The guarded branch checking error codes precedes the unguarded nested record pattern; the broad branch `Packet(var id, var payload)` catches unhandled `Packet` instances, including the case where `payload == null`.

The nested record pattern `Payload(...)` **does not match** if the `Payload` reference itself is null. However, a type pattern in a component position may have its own null-matching rules when it is unconditional for the component type; therefore, do not assume "every subpattern excludes null". When handling a required payload, validate it in the constructor/factory and write corresponding tests.

## 10. Runnable example: ordering nested record patterns

Save `RecordCaseOrderDemo.java`:

```java
public class RecordCaseOrderDemo {
    record Payload(int code) {}
    record Packet(String id, Payload payload) {}

    static String label(Object value) {
        return switch (value) {
            case Packet(var id, Payload(var code))
                    when code >= 400 ->
                    "error:" + id + ":" + code;

            case Packet(var id, Payload(var code)) ->
                    "ok:" + id + ":" + code;

            case Packet(var id, var payload) ->
                    "missing-payload:" + id;

            case null ->
                    "null";

            default ->
                    "other";
        };
    }

    public static void main(String[] args) {
        Object[] inputs = {
            new Packet("A", new Payload(503)),
            new Packet("B", new Payload(200)),
            new Packet("C", null),
            null,
            "plain"
        };

        for (Object input : inputs) {
            System.out.println(label(input));
        }
    }
}
```

```bash
javac --release 21 RecordCaseOrderDemo.java
java RecordCaseOrderDemo
```

Stdout:

```text
error:A:503
ok:B:200
missing-payload:C
null
other
```

The `Packet` record tests verify **true/false guards, present/missing nested records, a null selector, and a non-Packet value**. If you reverse the order so that `case Packet(var id, var payload)` comes first, the specific patterns below it will be shadowed or rejected by the compiler due to dominance.

## 11. `sealed` hierarchies: when adding a subtype, do not use `default` to evade responsibility

With a sealed root, a `switch` expression can be exhaustive when it handles all applicable permitted subtypes, without needing `default`.

Example:

```java
sealed interface Event permits Created, Confirmed, Cancelled {}
record Created(String id) implements Event {}
record Confirmed(String id, int units) implements Event {}
record Cancelled(String id) implements Event {}
```

When `Confirmed` has a guard, **there must still be a path for `Confirmed` that does not satisfy the guard** if exhaustiveness is required:

```java
return switch (event) {
    case Confirmed(var id, var units)
            when units >= 10 -> "bulk:" + id;

    case Confirmed(var id, var units) ->
            "confirmed:" + id + ":" + units;

    case Created(var id) -> "created:" + id;
    case Cancelled(var id) -> "cancelled:" + id;
    case null -> "null";
};
```

The broad `Confirmed` branch sits immediately after the guarded branch. The order among record subtypes **that have no direct inheritance relationship** can be changed without altering type coverage, though you should group them by domain and preserve tests.

If a new subtype `Refunded` is added and the compiler reports a missing exhaustive case, **add explicit handling logic** rather than hastily adding `default -> "unknown"`. A `default` can hide the fact that a new domain variant has appeared and needs review.

## 12. Complete program: testing ordering on a sealed hierarchy

Save `SealedCaseOrderDemo.java`:

```java
public class SealedCaseOrderDemo {
    sealed interface Event
            permits Created, Confirmed, Cancelled {}

    record Created(String id) implements Event {}
    record Confirmed(String id, int units) implements Event {}
    record Cancelled(String id) implements Event {}

    static String label(Event event) {
        return switch (event) {
            case Confirmed(var id, var units)
                    when units >= 10 ->
                    "bulk:" + id;

            case Confirmed(var id, var units) ->
                    "confirmed:" + id + ":" + units;

            case Created(var id) ->
                    "created:" + id;

            case Cancelled(var id) ->
                    "cancelled:" + id;

            case null ->
                    "null";
        };
    }

    public static void main(String[] args) {
        Event[] events = {
            new Created("C"),
            new Confirmed("A", 20),
            new Confirmed("B", 3),
            new Cancelled("X"),
            null
        };

        for (Event event : events) {
            System.out.println(label(event));
        }
    }
}
```

```bash
javac --release 21 SealedCaseOrderDemo.java
java SealedCaseOrderDemo
```

Stdout:

```text
created:C
bulk:A
confirmed:B:3
cancelled:X
null
```

The guarded `Confirmed` case and the unguarded `Confirmed` case form a mandatory pair for complete routing of this subtype. If you delete the unguarded branch in a `switch` expression, the compiler may report non-exhaustiveness. That is a **compile-time** check complementing runtime tests.

## 13. Where should `case null` be placed?

`case null` is a distinct label; do not treat it as equivalent to `default`. With a reference selector, without an appropriate `case null`, `switch(null)` normally throws `NullPointerException`.

Example:

```java
static String classify(Object value) {
    return switch (value) {
        case null -> "missing";
        case String text -> "text:" + text;
        default -> "other";
    };
}
```

This is an **illustrative method**. You can place `case null` near the end before `default` if that suits readability. Under Java 21 rules, the following example **is also valid**:

```java
static String classify(Object value) {
    return switch (value) {
        case Object any -> "non-null";
        case null -> "missing";
    };
}
```

`case Object any` matches every **non-null** object while `case null` matches null. Therefore, the checklist rule "`case null` must be first" is **false**; a good rule is to **place it in a clearly visible spot and verify it with tests**.

You can also use:

```java
case null, default -> "missing-or-other";
```

when you **intentionally combine null and all remaining values** into one branch; this label form is permitted in Java 21 and should be placed **last**. However, this combined form is unsuitable if business logic needs to distinguish null from unsupported values.

## 14. Place `default` after patterns; do not let it shadow other cases

When `default` is present, the consistent style is to place it **at the end of the switch block**. This makes the fallback scope clear and avoids dominance issues.

Avoid these mistakes:

- Placing a general pattern before a specialized pattern.
- Placing `default` before patterns or `null` labels.
- Using `case null, default` and then adding new cases after it.
- Using `default` to ignore a new subtype in a sealed hierarchy.
- Confusing `default` with a null-handling policy.

Some traditional `switch` forms allow unusual label placement for historical compatibility reasons, but that is **not good style** for new pattern `switch` code.

If an unconditional pattern already covers the entire selector type, adding `default` may be considered invalid or redundant by the compiler under dominance rules. Only use a fallback when it has real meaning.

## 15. Generic collections: subtype before interface and wildcard for type arguments

Suppose the selector is `Object`, and you want to distinguish `ArrayList` from other `List` implementations. A reasonable pattern is:

```java
static String kind(Object value) {
    return switch (value) {
        case java.util.ArrayList<?> list ->
                "arraylist:" + list.size();

        case java.util.List<?> list ->
                "list:" + list.size();

        case null -> "null";
        default -> "other";
    };
}
```

Putting `List<?>` before `ArrayList<?>` causes the `ArrayList` branch to be shadowed by the general branch. The code uses the wildcard `<?>` instead of raw `List`; the Java runtime **does not guarantee generic element types** from a collection type pattern alone.

`kind(new ArrayList<>(List.of(1, 2)))` returns `"arraylist:2"`, while `kind(List.of(1))` returns `"list:1"` according to the concrete implementations of `List.of` and `ArrayList`.

If business logic requires `List<String>`, check each element or use a generic API with a static contract. Do not use raw types or unchecked casts to get past the compiler when ordering patterns.

## 16. Enum constants: specific cases before an enum pattern covering the whole type

An enum can use constant `case` labels and a general type pattern in a pattern `switch`, for example:

```java
enum State { NEW, RUNNING, DONE }

static String describe(State state) {
    return switch (state) {
        case DONE -> "done";
        case NEW -> "new";
        case State any -> "other-state";
        case null -> "null";
    };
}
```

This is an **illustrative snippet inside a class containing the `State` enum**, not a standalone file. If `case State any` precedes `case DONE`, the `DONE` constant below is dominated and the compiler may report an error.

If an enum has a fixed set of values and each constant has distinct logic, you can list **every enum constant without `default`** so the compiler detects when a new constant is added (for a `switch` expression and appropriate exhaustiveness rules).

**Do not use `State any` merely to avoid writing the other cases** if the business requirement is to handle each enum constant individually.

## 17. `switch` statements with `:` have fall-through risks distinct from matching order

In new code, `case ... ->` does not fall through into the body of the next branch. In a legacy `switch` statement using `:`, a missing `break` can cause execution to continue into the statements of the following case:

```java
int n = 1;
switch (n) {
    case 1:
        System.out.println("one");
    case 2:
        System.out.println("two");
        break;
    default:
        System.out.println("other");
}
```

The snippet above **consists of statements inside a method**, not a standalone file. Stdout:

```text
one
two
```

This is **fall-through**, not `case 2` matching the selector `1`. When refactoring traditional statements to `switch` rules with `->`, check whether the old program relied on fall-through; switching to `->` can change behavior.

For pattern variables in colon-style switch statements, there are also scope/definite-assignment rules restricting control flow. Prefer `->` for new pattern `switch` code to avoid unnecessary risks.

## 18. Compile-negative cases worth keeping as learning examples

To let the compiler verify boundaries, keep the following **intentionally non-compiling** fixtures in a separate source set.

**A. Supertype before subtype:**

```java
static String wrong(Object value) {
    return switch (value) {
        case CharSequence s -> "sequence";
        case String s -> "string";
        default -> "other";
    };
}
```

**B. Unguarded case before the same type with a guard:**

```java
static String wrong(Object value) {
    return switch (value) {
        case String s -> "all-strings";
        case String s when s.length() > 3 -> "long";
        default -> "other";
    };
}
```

**C. Guard on a sealed subtype without a fallback:**

```java
sealed interface Action permits Go, Stop {}
record Go(int level) implements Action {}
record Stop() implements Action {}

static int wrong(Action action) {
    return switch (action) {
        case Go(var level) when level > 0 -> 1;
        case Stop stop -> 0;
    };
}
```

Snippets A and B are rejected by the compiler due to dominance; snippet C is rejected for **non-exhaustiveness** when `Go.level <= 0`. These are **illustrative snippets placed inside a class** (with type declarations in an appropriate shared scope), not three standalone runnable programs.

Negative tests should verify that `javac` returns a non-zero exit code and the right category of cause; you do not need to match the exact error text, as diagnostics can vary across JDK versions.

## 19. Testing checklist after changing order

Even when code compiles, your test suite should prove that branch priorities are correct.

| Case to test | Sample input | Reference output |
| --- | --- | --- |
| Prioritized constant | `"START"` | `start` in ConstantCaseDemo |
| Alias constant | `"BEGIN"` | `start` |
| String guard true | `" "` | `blank` |
| String guard false | `"hello"` | `text:hello` |
| `String` vs `CharSequence` | `"java"` | `text:java` in CaseOrderingDemo |
| Parent–child interface | `new StringBuilder("xy")` | `sequence:2` |
| Numeric guard true | `2` | `nonnegative:2` |
| Numeric guard false | `-3` | `negative:-3` |
| Nested record guard true | `Packet("A", Payload(503))` | `error:A:503` |
| Nested record guard false | `Packet("B", Payload(200))` | `ok:B:200` |
| Nested payload null | `Packet("C", null)` | `missing-payload:C` |
| New sealed subtype | Add permitted subtype | Build must be reviewed/updated |
| `null` selector | `null` | `case null` branch per contract |
| No pattern match | `new Object()` | `default` branch if present |

Also test guard boundaries, such as `code = 399` and `400`, or `units = 9` and `10`; inputs far from the threshold can miss `>` vs `>=` bugs.

**One especially important test:** when `case Integer i when i > 0` precedes `case 1`, assert that input `1` is handled according to the business goal. The compiler allows this code, but cannot guess whether you want `"one"` or `"positive"`.

## 20. Step-by-step review process

When reviewing a new `switch` or a diff that reorders `case` labels, follow these steps in order:

1. **Note the selector's static type:** enum, sealed root, `Object`, generic interface, or record?
2. **Map subtype relationships:** which `case` labels can match the same object?
3. **Mark special constants:** do constants/enum values need priority before a general type pattern?
4. **Mark all guards:** which guards have value domains overlapping constants or other guards?
5. **Place specific record structures before broad ones:** nested patterns and guards before outer record fallbacks.
6. **Check exhaustiveness:** for sealed/enum types, is there an unguarded case covering values where a guard evaluates to false?
7. **Finalize the `null` policy:** return a result, throw an error, or handle at a boundary layer?
8. **Move `default` to the end if used:** is it genuinely needed, or is it just hiding missing branches?
9. **Distinguish `->` from `:`:** are there fall-through risks when refactoring legacy code?
10. **Compile with the right Java target:** e.g., `javac --release 21`, without adding preview flags.
11. **Test every branch and guard boundary:** verify priority, results, and side effects.
12. **Review against the domain:** the compiler proves type coverage, not business logic correctness.

Steps 2 and 4 are especially critical: **a change in order can break compilation immediately or silently alter runtime results**, depending on the pattern structure.

## 21. Common misconceptions

| Misconception | Reality |
| --- | --- |
| "Java always picks the most specific pattern even if it is last" | Labels are evaluated in order; dominated labels can be rejected |
| "If the build succeeds, the order is right" | A guard can shadow a constant without the compiler warning |
| "A `when` guard always dominates a constant below it" | Guards are generally not used to infer dominance over every constant |
| "Constant cases can be placed anywhere" | A constant can be shadowed by an unguarded pattern of the same type |
| "Having `case T t` means no other cases are needed" | It can shadow special branches and lose business-specific handling |
| "Nested record patterns are always null-safe" | A null nested record reference causes the nested pattern not to match |
| "`case null` must be the first case" | Not required; place it clearly and test it |
| "`default` also catches `null`" | `default` alone is not a null-handling policy |
| "Adding `default` is the best way to fix sealed exhaustiveness" | It can hide a new subtype that needs explicit handling |
| "`List<String>` can be checked with a runtime pattern" | Type erasure still applies; use wildcards and inspect components |
| "Cases with `->` automatically fall through to the next branch" | Switch rule `->` does not fall through like old colon statements |
| "Putting the most frequent branch first always speeds things up" | Semantics must be preserved; benchmarking is required for performance claims |

## 22. Final ready-to-use checklist

**Before merging a pattern `switch`:**

- [ ] The selector type and set of runtime types are clear.
- [ ] Special constants/enum cases precede patterns that cover them.
- [ ] Specific subtypes precede broader supertypes/interfaces.
- [ ] For the same type, prioritized `when` cases precede unguarded cases.
- [ ] Guards with overlapping conditions have been tested for **priority**, even when the compiler does not report an issue.
- [ ] Nested record patterns have proper fallbacks for null components or missing values.
- [ ] Sealed/enum switches remain exhaustive; no `default` was added just to silence errors.
- [ ] `case null` has the right policy; `default` is last if present.
- [ ] There are no dominated labels or duplicate constants.
- [ ] Behavior does not change when converting `:` to `->`.
- [ ] Tests cover special constants, subtypes, guard true/false, boundaries, null, and fallback.
- [ ] The build targets Java 21 final and does not rely on old preview syntax.

**Conclusion:** A `case` ordering checklist must examine **the kinds and value ranges each branch accepts**, not just whether the lines look neatly arranged. A generally useful pattern is **specific constants/exceptions → guarded patterns → unguarded patterns → fallback**, combined with **subtype before supertype** ordering and an explicit `null` policy. Most importantly, test for bugs that **the compiler cannot detect because guards carry business meaning**.

## Official references

- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [Oracle Java SE 21 — Pattern Matching for switch (dominance, when, null)](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Java SE 21 Language Specification §14.11 — Switch Statements](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
- [Java SE 21 Language Specification §14.30 — Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30)
- [Java SE 21 Language Specification §15.28 — Switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28)
