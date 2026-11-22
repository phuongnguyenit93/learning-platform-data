# Exhaustively Testing `case` Patterns in Java

## 1. Goal: "exhaustive" does not mean sufficiently tested

Since **Java 21**, pattern matching for `switch` (JEP 441) has been a standard feature. A `switch` can use type patterns (`case String s`), record patterns (`case Point(int x, int y)`), guards (`when ...`), `null` labels, constant labels, and `default`.

**Exhaustiveness (coverage of the `switch`)** and **test coverage** are two distinct concepts:

- **Compile-time exhaustiveness:** the compiler determines whether the switch has enough labels to handle all non-`null` values that can occur according to the selector's static type. A `switch expression` and an **enhanced switch statement** must be exhaustive.
- **Runtime test coverage:** the test suite actively runs representative inputs to verify **which branch is actually selected**, guard conditions, label ordering, boundaries, and outputs/exceptions.
- **Business correctness:** even if a switch is valid and tests pass through every case, the logic in a guard or the ordering between cases can still violate business requirements.

For example, the compiler can accept:

```java
return switch (value) {
    case String s when s.length() < 5 -> "short";
    case String s when s.isBlank() -> "blank";
    case String s -> "text";
    case null -> "null";
    default -> "other";
};
```

However, for `" "`, both of the first two guards can be true and Java picks the **first matching case**. If the business requirement treats `" "` as a blank string, tests must catch that the ordering needs to change. The compiler does not solve the full logical relationship between `when` expressions.

**Lesson goal:** build a test matrix covering each pattern, each guard value set, boundaries, `null` values, mismatched types, and compile-time error scenarios; and understand the limits of claiming "exhaustive testing" when the input domain can be infinite.

## 2. How does Java check exhaustiveness?

### 2.1. Switch expressions and enhanced switch statements

According to the **Java Language Specification (JLS) 21, §14.11**, a **switch expression** must be exhaustive. An **enhanced switch statement** (for example, one with pattern labels or `case null`, or a selector using a type outside the traditional switch types) must also be exhaustive.

Example that **does not compile** (illustrative method snippet to be placed inside a class):

```java
static String incomplete(Object value) {
    return switch (value) {
        case String s -> "string";
        case Integer n -> "integer";
        // ERROR: missing the remaining Object types.
    };
}
```

Fix it by adding the missing branch:

```java
static String complete(Object value) {
    return switch (value) {
        case null -> "null";
        case String s -> "string";
        case Integer n -> "integer";
        default -> "other";
    };
}
```

Here `default` covers non-`null` values that do not match `String` or `Integer`. `case null` is a **separate** `null`-handling policy: in Java 21, without a label handling `null`, a `null` selector normally throws `NullPointerException`, even when `default` is present.

**Note:** a legacy switch statement with only constants that does not qualify as enhanced may not be required to be exhaustive for backward-compatibility reasons. Do not generalize that "every switch statement must have `default`".

### 2.2. Exhaustiveness via a sealed hierarchy

A `sealed` type restricts the set of direct subclasses/subtypes permitted to implement it. If a switch has cases covering every permitted subtype, the compiler can consider the switch exhaustive **without `default`**.

Example:

```java
sealed interface Event permits Started, Finished {}

record Started(String id) implements Event {}
record Finished(String id) implements Event {}

static String eventKind(Event event) {
    return switch (event) {
        case Started s -> "started";
        case Finished f -> "finished";
    };
}
```

This is an **illustrative code snippet**: place the declarations in a valid scope within a Java 21 file. It covers every non-`null` `Event` object in the declared subtype set. If you want a specific response for `null`, add `case null`.

If a new subtype is added, such as `record Cancelled(...) implements Event`, and the existing switch source code is recompiled, the compiler can require a new case. However, in systems with **separate compilation/distribution of components**, a previously compiled switch can encounter the new subtype at runtime and throw **`MatchException`**. Therefore, testing and the build process must also account for changes to the sealed hierarchy, not just the current test suite.

### 2.3. Guards do not automatically prove full-domain coverage

Example that is **non-exhaustive** when the selector is `Integer` and there are only arbitrary guards:

```java
static String sign(Integer value) {
    return switch (value) {
        case Integer n when n < 0 -> "negative";
        case Integer n when n == 0 -> "zero";
        case Integer n when n > 0 -> "positive";
        // ERROR: the compiler does not prove that arbitrary guards cover every Integer.
    };
}
```

Mathematically, the three ranges `< 0`, `== 0`, and `> 0` cover every integer. However, Java's exhaustiveness check is not a general-purpose logic solver for guard expressions.

A clearer way to write it:

```java
static String sign(Integer value) {
    return switch (value) {
        case null -> "null";
        case Integer n when n < 0 -> "negative";
        case Integer n when n == 0 -> "zero";
        case Integer n -> "positive";
    };
}
```

The **unguarded** `case Integer n` rule covers the remaining `Integer` values, making the switch exhaustive for an `Integer` selector (while also handling `null` explicitly).

## 3. What layers of checks does "exhaustive testing" require?

They can be divided into four groups:

| Group | What to verify | Failure signal |
| --- | --- | --- |
| **Compile-time** | Switch expression/enhanced statement is exhaustive; no dominated cases; valid syntax | `javac` reports an error |
| **Type partition** | Every subtype of a sealed hierarchy, each type pattern, unexpected types hitting `default` | A class does not reach the expected case |
| **Guard partition** | Each `when` branch true/false, overlapping cases, numeric/string boundaries | Two guards are both true, but the wrong case takes precedence |
| **Exceptional/null** | `null`, guard throwing an exception, `MatchException` due to binary evolution, anomalous data | Null causes an unexpected NPE; unhandled errors slip through |

**You cannot assume a test suite has checked all infinite `String` or `int` values or every external input.** In practice, "exhaustive" usually means the test suite covers **syntactic branches, equivalence classes, boundaries, and well-defined business invariants**, combined with build checks that catch missing cases.

### 3.1. Type pattern matrix

For `Object`, which can hold many runtime types, you should have at least one input per type pattern and one input that matches none of the specialized type patterns.

Example:

```java
return switch (value) {
    case null -> "NULL";
    case String s -> "TEXT";
    case Integer n -> "INT";
    case Number n -> "OTHER_NUMBER";
    default -> "OTHER";
};
```

Sample matrix:

| Value | Runtime type | Expected label |
| --- | --- | --- |
| `null` | no object | `case null` |
| `"Hi"` | `String` | `case String s` |
| `Integer.valueOf(7)` | `Integer` | `case Integer n` |
| `Double.valueOf(2.5)` | `Double` (a `Number`) | `case Number n` |
| `Boolean.TRUE` | `Boolean` | `default` |

**Case order matters:** `Integer` must come before `Number` so it is not shadowed by the supertype case. If `case Number n` is moved first, the following `case Integer n` can cause a **dominance** compile-time error.

### 3.2. Boundary-based guard matrix

For a percentage progress `int percent`, suppose:

1. If `percent < 0 || percent > 100` → `INVALID`.
2. If `percent == 100` → `DONE`.
3. If `percent >= 80` → `HIGH`.
4. Otherwise → `NORMAL`.

Choose values around the transition points:

| Input `percent` | Expected | Reason |
| ---: | --- | --- |
| `-1` | `INVALID` | Just below the lower bound |
| `0` | `NORMAL` | At the lower bound |
| `79` | `NORMAL` | Just before the high threshold |
| `80` | `HIGH` | At the high threshold |
| `99` | `HIGH` | Just before completion |
| `100` | `DONE` | At the special point that must take precedence over `>= 80` |
| `101` | `INVALID` | Just above the upper bound |

In particular, `100` **simultaneously satisfies** `percent == 100` and `percent >= 80`; the `== 100` guard must come **before** the `>= 80` guard if the `DONE` label is desired. A test using only `80` will **not detect a precedence bug at 100**.

### 3.3. Compile-time negative tests

In addition to runtime tests, intentionally write erroneous patterns in **separate test files** and confirm that `javac` rejects them:

- Missing a case for a subtype in a sealed hierarchy;
- Only guarded patterns without a general case that proves exhaustiveness;
- An unguarded supertype pattern placed before a subtype pattern (dominance);
- Duplicate constant labels;
- Accessing a pattern variable outside the scope of the branch declaring it.

A file **expected to fail compilation** should not be mixed into the main demo program, because otherwise normal tests cannot run either. When automating, check only for a non-zero exit code and appropriate diagnostics, without assuming exact error text across `javac` versions.

## 4. A Java 21+ program with assertions covering every pattern case

The following example uses **two switches**:

1. `classifyEvent(Event)` is a switch expression over a **sealed hierarchy**, covering every subtype via patterns; there is no `default`.
2. `classifyAny(Object)` tests `null`, `String`, `Integer`, `Event`, **record patterns**, and `default`; it includes blank/length guards, negative numbers, and points on the diagonal.

The `check` method throws `AssertionError` whenever the result differs from expected: having the program print `PASS` is therefore more meaningful than examples that only print output without verifying it.

### 4.1. Complete source code

Save the file **`ExhaustiveCaseTestDemo.java`**:

```java
public class ExhaustiveCaseTestDemo {
    sealed interface Event permits Started, Progress, Completed, Failed {}

    record Started(String id) implements Event {}
    record Progress(int percent) implements Event {}
    record Completed(String result) implements Event {}
    record Failed(String reason) implements Event {}
    record Point(int x, int y) {}

    static String classifyEvent(Event event) {
        return switch (event) {
            case null -> "EVENT_NULL";
            case Started started -> "STARTED:" + started.id();

            case Progress p when p.percent() < 0 || p.percent() > 100 ->
                    "INVALID_PROGRESS:" + p.percent();
            case Progress p when p.percent() == 100 ->
                    "PROGRESS_DONE";
            case Progress p when p.percent() >= 80 ->
                    "HIGH_PROGRESS:" + p.percent();
            case Progress p -> "PROGRESS:" + p.percent();

            case Completed c -> "COMPLETED:" + c.result();
            case Failed f -> "FAILED:" + f.reason();
        };
    }

    static String classifyAny(Object value) {
        return switch (value) {
            case null -> "NULL";
            case String s when s.isBlank() -> "BLANK";
            case String s when s.length() >= 5 -> "LONG_TEXT:" + s;
            case String s -> "SHORT_TEXT:" + s;

            case Integer n when n < 0 -> "NEGATIVE:" + n;
            case Integer n -> "INTEGER:" + n;

            case Event e -> "EVENT/" + classifyEvent(e);

            case Point(int x, int y) when x == y -> "DIAGONAL:" + x;
            case Point(int x, int y) -> "POINT:" + x + "," + y;

            default -> "OTHER";
        };
    }

    static int passed = 0;

    static void check(String testName, String actual, String expected) {
        if (!expected.equals(actual)) {
            throw new AssertionError(testName + ": expected [" + expected
                    + "] but got [" + actual + "]");
        }
        passed++;
        System.out.println("PASS " + testName + " -> " + actual);
    }

    public static void main(String[] args) {
        check("event-null", classifyEvent(null), "EVENT_NULL");
        check("started", classifyEvent(new Started("A")), "STARTED:A");

        check("progress-under", classifyEvent(new Progress(-1)),
                "INVALID_PROGRESS:-1");
        check("progress-zero", classifyEvent(new Progress(0)), "PROGRESS:0");
        check("progress-79", classifyEvent(new Progress(79)), "PROGRESS:79");
        check("progress-80", classifyEvent(new Progress(80)), "HIGH_PROGRESS:80");
        check("progress-99", classifyEvent(new Progress(99)), "HIGH_PROGRESS:99");
        check("progress-100", classifyEvent(new Progress(100)), "PROGRESS_DONE");
        check("progress-over", classifyEvent(new Progress(101)),
                "INVALID_PROGRESS:101");

        check("completed", classifyEvent(new Completed("ok")), "COMPLETED:ok");
        check("failed", classifyEvent(new Failed("timeout")), "FAILED:timeout");

        check("any-null", classifyAny(null), "NULL");
        check("any-blank", classifyAny("  "), "BLANK");
        check("any-short", classifyAny("Hi"), "SHORT_TEXT:Hi");
        check("any-long", classifyAny("Java21"), "LONG_TEXT:Java21");
        check("any-negative", classifyAny(-3), "NEGATIVE:-3");
        check("any-zero", classifyAny(0), "INTEGER:0");
        check("any-event", classifyAny(new Progress(100)),
                "EVENT/PROGRESS_DONE");
        check("any-diagonal", classifyAny(new Point(2, 2)), "DIAGONAL:2");
        check("any-point", classifyAny(new Point(2, 3)), "POINT:2,3");
        check("any-other", classifyAny(2.5), "OTHER");

        System.out.println("ALL PASSED: " + passed);
    }
}
```

Compile and run with **JDK 21 or later**:

```bash
javac ExhaustiveCaseTestDemo.java
java ExhaustiveCaseTestDemo
```

**Expected standard output (when all 21 assertions succeed):**

```text
PASS event-null -> EVENT_NULL
PASS started -> STARTED:A
PASS progress-under -> INVALID_PROGRESS:-1
PASS progress-zero -> PROGRESS:0
PASS progress-79 -> PROGRESS:79
PASS progress-80 -> HIGH_PROGRESS:80
PASS progress-99 -> HIGH_PROGRESS:99
PASS progress-100 -> PROGRESS_DONE
PASS progress-over -> INVALID_PROGRESS:101
PASS completed -> COMPLETED:ok
PASS failed -> FAILED:timeout
PASS any-null -> NULL
PASS any-blank -> BLANK
PASS any-short -> SHORT_TEXT:Hi
PASS any-long -> LONG_TEXT:Java21
PASS any-negative -> NEGATIVE:-3
PASS any-zero -> INTEGER:0
PASS any-event -> EVENT/PROGRESS_DONE
PASS any-diagonal -> DIAGONAL:2
PASS any-point -> POINT:2,3
PASS any-other -> OTHER
ALL PASSED: 21
```

### 4.2. Why are these tests meaningful?

- **Sealed type:** there are tests for all four subtypes `Started`, `Progress`, `Completed`, and `Failed`. `Progress` in particular is split into guards and an unguarded pattern.
- **Guard boundary:** `-1`, `0`, `79`, `80`, `99`, `100`, and `101` test the boundaries that transition branches from normal to prioritized and invalid. If `>=80` were placed before `==100`, the test at `100` would fail.
- **Null:** both methods have a dedicated `case null`, so the tests verify the null policy rather than relying on `default`.
- **Object pattern:** blank strings, short strings, long strings, negative numbers, non-negative numbers, `Event` subtypes, `Point`, and the unexpected type `Double` hit different rules.
- **Record pattern:** `Point(2,2)` exercises the `x == y` guard, while `Point(2,3)` exercises the unguarded record branch. Since the components are `int`, there is no `null` reference component pattern-matching issue here.
- **Assertion:** the program stops with an error as soon as a result is wrong. The `PASS` lines and total check count are printed only when each check receives the expected result.

### 4.3. Limitations of this demo

Despite having 21 assertions, the demo does not automatically prove that every `int` value or every real-world string is handled correctly. For example, a guard that mistakenly uses `> 80` instead of `>= 80` can be caught by the test at 80, but a bug that occurs only for `Integer.MIN_VALUE` still needs an extra test if a business rule depends on it.

When the input domain is large, add **property-based testing**, controlled fuzzing, or boundary-driven data generation. Crucially, define an *oracle* (expected correct result) independently of the `switch` code: if you write tests by copying the production logic verbatim, both can share the same bug.

## 5. Testing non-exhaustive switches yourself

### 5.1. Missing a `sealed` subtype

The following method snippet uses the nested types in `ExhaustiveCaseTestDemo` above. It is meant for **testing compilation errors** and should not be added to the main runnable program if you want passing tests to run.

```java
static String missingSubtype(Event event) {
    return switch (event) {
        case Started s -> "started";
        case Progress p -> "progress";
        case Completed c -> "completed";
        // Missing Failed: non-exhaustive switch error.
    };
}
```

**Expected:** `javac` returns a non-zero exit code because the label set does not cover the `Failed` subtype. Add `case Failed f -> "failed";` to fix it. With `default`, the switch would compile even if `Failed` were forgotten, but you would **lose the compiler's reminder to update** when the sealed hierarchy evolves.

### 5.2. Guards are insufficient to prove coverage

```java
static String incompleteProgress(Event event) {
    return switch (event) {
        case Started s -> "started";
        case Progress p when p.percent() < 0 -> "invalid";
        case Completed c -> "completed";
        case Failed f -> "failed";
        // No unguarded Progress case.
    };
}
```

**Expected:** non-exhaustive error. A `Progress` with value 50 does not satisfy the sole guard. To fix it, add `case Progress p -> "progress";` **after** the guarded branch.

### 5.3. Dominated patterns and branch ordering

```java
static String invalidOrder(Object value) {
    return switch (value) {
        case Number n -> "number";
        case Integer n -> "integer"; // ERROR: dominated by the Number case.
        default -> "other";
    };
}
```

**Expected:** dominated case label error. Java detects this because every `Integer` is a `Number`. Fix it by placing `Integer` before `Number`.

**Contrast with dominance errors:** two arbitrary guards like `p.percent() == 100` and `p.percent() >= 80` can **both be true**, yet the compiler does not solve the full mathematical relationship between them. Swapping their order usually still compiles; only a test at 100 catches the wrong precedence.

### 5.4. Running compile-negative tests safely

You can save each erroneous variant in a **separate Java file** while practicing and run:

```bash
javac MissingSubtype.java
```

Expect compilation to fail. For CI automation, organize **negative compilation tests** separately from the main source set so intentionally broken files do not break the production build. Depending on the compiler and JDK version, the diagnostic wording may vary; the general criterion is that compilation fails for the expected reason.

## 6. `null`, `default`, `MatchException`, and exceptional cases

### 6.1. Do not equate `default` with `case null`

With a reference selector:

```java
static String label(Object value) {
    return switch (value) {
        case String s -> "string";
        default -> "other";
    };
}
```

The program handles non-`null` objects; however, calling `label(null)` throws **`NullPointerException`** because `default` does not automatically match `null`. If you want to test a null policy that returns a value, add `case null -> "null"` or use the special combined label `case null, default -> ...` when you genuinely want shared handling.

How to write an exception test in plain Java:

```java
boolean thrown = false;
try {
    label(null);
} catch (NullPointerException expected) {
    thrown = true;
}
if (!thrown) {
    throw new AssertionError("Expected NullPointerException");
}
```

This is a **snippet to place in an appropriate method**; it explicitly verifies a "null not supported" policy. Do not use this test form if the API is expected to **handle `null` normally**: in that case, write `case null` and assert the result as in the complete program in section 4.

### 6.2. Why can an exhaustive switch still encounter `MatchException`?

Oracle Java 21 notes the **binary evolution** scenario: a switch was compiled to cover every branch in a sealed hierarchy, but the library declaring the hierarchy is modified, recompiled, and gains a new subtype, while the old switch code is not recompiled.

In that situation, the switch can encounter an object that no longer matches the cases known to the old switch binary, and **`java.lang.MatchException`** can be thrown at runtime.

This does **not** mean every exhaustive switch needs a `default`. For a sealed hierarchy, omitting `default` is often beneficial because the compiler forces developers to handle new subtypes when rebuilding the codebase. You should:

- Recompile dependent modules when changing a sealed hierarchy;
- Run integration tests against the exact set of distributed artifacts;
- Avoid running incompatible versions of runtime components together;
- Monitor `MatchException` as a compatibility/branch-coverage error signal, not as a normal business case.

### 6.3. Guards can throw exceptions

If a guard calls a method that throws an exception, the switch does not simply fall through to the next case as it does when a guard returns `false`. For instance, a guard on data that may contain `null` values needs a safety check first:

```java
case String s when s.length() > 3 -> ...
```

The type pattern `String s` already proves `s` is non-null, so `s.length()` is null-safe. However, reference-typed record components or other business methods can still be `null` or throw exceptions. Test failure paths according to the API contract as well.

## 7. Testing `switch statement` vs. `switch expression`

### Switch expression

- **Always must be exhaustive** in type/structure per the JLS.
- Every normal branch produces a value; in a block-style RHS, use `yield` to produce the value.
- Tests should assert the **return value** of each branch or the exception type.

### Enhanced switch statement

- When it has patterns or `case null`, it typically belongs to the **enhanced** category and must also be exhaustive.
- Executes statements rather than producing a value from the `switch` expression itself.
- Tests should verify **observable side effects**: invoking a callback, appending an object to a list, mutating state, or calling a mocked method. If it only prints to `System.out`, you can check output by capturing the print stream, though production code is usually easier to test when it returns a value or delegates actions to a dependency.

Illustrative `switch statement` with type patterns:

```java
static void printEvent(Event event) {
    switch (event) {
        case Started s -> System.out.println("started " + s.id());
        case Progress p -> System.out.println("progress " + p.percent());
        case Completed c -> System.out.println("completed " + c.result());
        case Failed f -> System.out.println("failed " + f.reason());
    }
}
```

This illustrative method belongs to the same class defining `Event`; it covers all **non-`null`** subtypes of the sealed hierarchy. Calling it with `null` throws NPE; add `case null` if handling is needed. When using **arrow rules `->`**, there is no fall-through; if using `case ...:` statement groups, you must manage `break` and the rules forbidding falling through into an uninitialized pattern variable.

## 8. Advanced testing strategy for real-world projects

### 8.1. Build a coverage matrix before writing code

For each `case` label, document:

| Required column | Sample content |
| --- | --- |
| Label | `case Progress p when p.percent() >= 80` |
| Input type | `Progress` |
| Selection condition | `80 <= percent < 100`, after the 100-check branch |
| Positive value | `Progress(80)` |
| Near-boundary negative value | `Progress(79)` |
| Overlapping value | `Progress(100)` |
| Expected | `"HIGH_PROGRESS:80"`, or the done branch if 100 |
| Actual result | Compared via assertion |

Each test should prove something **distinguishable** between branches. Writing a single arbitrary test per type is not enough if the same type has multiple guards.

### 8.2. Minimal structured test set

A solid test suite typically includes:

1. **Every permitted subtype** of a sealed hierarchy (one positive test per subtype).
2. **Every guard** has at least one true test and one false test.
3. **Every boundary**: just before, right at, and just after the threshold (`79`, `80`, `81` for threshold 80).
4. **Every precedence conflict**: a value satisfying multiple guards, such as `100` satisfying `==100` and `>=80`.
5. **`null`**: returns a value or throws NPE per contract.
6. **Final unguarded branch** of the same type, and `default` if present.
7. **Nested patterns**: record patterns with matching/non-matching components and guards.
8. **Compile-negative**: missing subtype, guard-only, dominated label.
9. **API changes**: adding an enum constant or permitted subtype to verify the build/tests catch it.
10. **Anomalous inputs**: min/max values, empty strings, blank strings, invalid states that can still be constructed.

Not every problem needs all ten groups, but **do not skip any group that directly affects business requirements**.

### 8.3. Mutation testing: intentionally breaking code

One way to verify test quality is to make a small change that introduces wrong behavior:

- Change `p.percent() == 100` to `>= 100`;
- Change `p.percent() >= 80` to `> 80`;
- Swap the order of the `== 100` and `>= 80` guards;
- Change `s.isBlank()` to `s.isEmpty()` (whitespace-only strings differ from empty strings);
- Remove the branch handling a subtype.

If the test suite still passes despite broken logic, add discriminating tests. For example, changing `>= 80` to `> 80` must be caught by a test at `Progress(80)`. Swapping `==100` and `>=80` must be caught by `Progress(100)`.

### 8.4. Do not use "we already have default" as a substitute for thorough testing

A `default` for `Object` is useful for receiving unexpected types, but it can sometimes hide that a new business subtype lacks its own branch. For sealed hierarchies controlled by the project itself, consider **omitting `default`** when the compiler can verify all subtypes: every new subtype will force a review of its handling branch at build time.

Conversely, for open `Object` inputs that can be any reference type, `default` is usually the right way to cover the remaining types; test a value that actually enters that branch.

## 9. Common mistakes when testing pattern cases

1. **Equating compiler exhaustiveness with test branch coverage.** The compiler checks type coverage under language rules; it does not guarantee the logic in every branch is right.
2. **Testing only the "happy path".** With conditional guards, missing boundaries and negative/blank/empty values often let bugs slip through.
3. **Not testing `null`.** `default` does not handle null automatically, so decide explicitly whether to return a value or throw an exception.
4. **Forgetting to test overlapping guards.** Java picks the first matching label, not automatically the "most specific" one.
5. **Writing test assertions using the production switch itself.** Expected values should be determined independently from business rules.
6. **Assuming guarded-only patterns are exhaustive.** Arbitrary guards do not prove every value matches; an unguarded pattern or another covering branch is needed.
7. **Adding `default` to every sealed switch without thinking.** It can suppress the compile-time signal when a subtype is added.
8. **Not testing `record` values with null components or boundary values.** Type/record patterns have specific component-matching rules; do not assume every structure matches.
9. **Only checking printed output without assertions.** Running without crashing does not mean correct; tests must fail when output differs from expected.
10. **Not testing distributed artifacts after a sealed hierarchy change.** Separate compilation can lead to `MatchException` even though an older build was exhaustive.
11. **Placing a supertype case before a subtype case.** This is dominance that the compiler can reject; use compile-negative tests or rely on the build.
12. **Using the wrong JDK version.** Pattern matching for `switch` has been a standard feature since Java 21; run these examples with JDK 21+.

## 10. Practice exercises

1. **Add a subtype:** add `record Cancelled(String reason) implements Event` to the permits list of the program in section 4. Predict the error in `classifyEvent`, then add `case Cancelled c`; create a test for `"CANCELLED:..."`.
2. **Try changing guard order:** move `case Progress p when p.percent() >= 80` before `case Progress p when p.percent() == 100`. Re-run the 21 tests and identify which assertion fails and why.
3. **Try changing the operator:** change `>= 80` to `> 80`; explain why the test at 80 catches the bug.
4. **Try overlapping string guards:** place `case String s when s.length() <= 4` before `case String s when s.isBlank()` and classify `" "`; write an assertion to catch the precedence bug.
5. **Null policy:** remove `case null` from `classifyAny`, call it with `null`, and write a test expecting `NullPointerException` instead of `NULL`.
6. **Type partitions:** add `case Number n` in `classifyAny` **after** the `Integer` cases; write tests with `Double`, `Long`, and `Integer` and distinguish the outputs.
7. **Record pattern:** add `Point(0,0)` and `Point(0,1)` to the tests; explain which branches must execute. Add a prioritized guard for the origin before the diagonal guard if the business requirement asks for `"ORIGIN"`.
8. **Negative compile:** create separate test files intentionally omitting `Failed`, placing `Number` before `Integer`, and having only guarded patterns; verify each error through the compilation result.
9. **Property test:** randomly generate 1,000 progress values between -100 and 200, compare `classifyEvent(new Progress(p))` against a reference function written from the rule table; record the seed if any case fails.
10. **CI:** propose a check pipeline including JDK 21 compilation, unit tests, negative compilation tests, sealed hierarchy change checks, and integration tests against the exact artifacts to be deployed.

**Key takeaway:** *Exhaustive switch* is a guarantee about the **type coverage** of a `switch` construct; *exhaustively testing pattern cases* is the work of verifying **every meaningful path** and **expected output**. With Java 21, combining compiler checks, a type/guard/boundary/null matrix, real assertions, intentional failure tests, and hierarchy-change testing provides far stronger assurance than just having `default` or a single test per type.

## References

- [Oracle Java 21 — Pattern Matching for switch Expressions and Statements](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
- [Java Language Specification 21, §14.11 — switch Statements (exhaustiveness, dominance, labels)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11).
- [Java Language Specification 21, §15.28 — switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28).
- [Java Language Specification 21, §6.3.3 — Pattern variable scope in case labels](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3.3).
- [OpenJDK JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441).
- [OpenJDK JEP 440 — Record Patterns](https://openjdk.org/jeps/440).
