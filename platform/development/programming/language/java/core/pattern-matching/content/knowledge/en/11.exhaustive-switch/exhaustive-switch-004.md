# `default` as a Catch-All Option in Exhaustive `switch` (Java 21)

**Topic:** Java Core Pattern Matching → Exhaustive switch  
**Environment:** Java 21 or later. Pattern matching for `switch` became official in JEP 441; this lesson uses stable syntax, no `--enable-preview` needed.

## 1. Why does `switch` need a catch-all option?

A `switch` classifies a selector value through `case` labels. If you only list a few specific values or types, there will be inputs that do not match any label. The **`default`** keyword provides a fallback branch for values **not selected by any other branch**, allowing a `switch` expression to return a result for the entire input domain according to language rules.

Example:

```java
static String describe(Object input) {
    return switch (input) {
        case null -> "NULL";
        case String s -> "TEXT:" + s.length();
        case Integer n -> "INT:" + n;
        default -> "OTHER";
    };
}
```

With `"abc"`, the `String` branch returns `TEXT:3`; with `12`, the `Integer` branch returns `INT:12`; with `2.5`, `true`, or another object, the `default` branch returns `OTHER`. The `null` input is handled **separately** by `case null`.

**Key takeaway:** `default` is a mechanism to cover **the remaining cases according to branch-selection rules**, not a "default object type" and not a tool to replace all business-logic validity checks.

## 2. What is exhaustiveness and how does `default` relate to it?

A `switch` is called *exhaustive* if the compiler can verify that the case labels cover every value that needs to be handled according to the rules for the selector type. For a `switch` **expression**, exhaustiveness is a mandatory requirement: the expression must produce a value when completing normally.

```java
// DOES NOT COMPILE: missing branches for other Object types.
static String incomplete(Object value) {
    return switch (value) {
        case String s -> "STRING";
        case Integer i -> "INTEGER";
    };
}
```

Fix it with a `default`:

```java
static String complete(Object value) {
    return switch (value) {
        case String s -> "STRING";
        case Integer i -> "INTEGER";
        default -> "OTHER";
    };
}
```

At the exhaustiveness-checking level, the compiler sees the `default` fallback branch. However, **do not assume that `null` will enter `default`**: for a `null` selector, Java 21 has separate rules presented in section 4; `complete(null)` still throws `NullPointerException`.

### Must a `switch` statement be exhaustive?

It is necessary to distinguish:

- **Traditional `switch` statement** with selectors such as `int`, `String`, or `enum` does not have to list every label. When there is no match and no `default`, the statement simply finishes without executing any case branch.
- **Enhanced `switch` statement** in Java 21 (for example, using a type pattern in a case) has an exhaustiveness requirement. A statement containing pattern matching is not considered "free to omit cases" just because it does not return a value.
- **`switch` expression** must always be exhaustive; this is why learners see `default` appear frequently when the selector declares a broad type like `Object`.

The purpose of `default` in both statements and expressions is to express the policy for remaining cases. However, merely adding `default` so the code compiles, without specifying which data falls into this branch, can hide business-logic bugs.

## 3. `default` in `switch` with type patterns

A type pattern checks the runtime type and introduces a typed variable. You can use `default` after type patterns:

```java
static String classify(Object value) {
    return switch (value) {
        case null -> "NULL";
        case String text -> "STRING:" + text;
        case Number number -> "NUMBER:" + number;
        default -> "UNKNOWN:" + value.getClass().getSimpleName();
    };
}
```

In this example:

1. `String` matches `case String text`.
2. `Integer`, `Double`, `Long`, and other subtypes of `Number` can match `case Number number`.
3. `Boolean` or an object not belonging to the two types above enters `default`; here it is safe to call `value.getClass()` because `null` was already handled earlier.
4. The variables `text` and `number` are only in scope within their matching branch. The `default` branch does not have its own pattern variable; if you need data, use the selector `value` or construct the result from available context.

To test the fallback branch, do not just test the two types that already have a `case`; pass at least one object that **genuinely does not match** any preceding type pattern.

## 4. `default` does not automatically catch `null`

A common point of confusion: in Java 21, `null` does not match a top-level type pattern. If the `switch` selector is `null` and there is no appropriate label handling `null`, the `switch` normally throws `NullPointerException` — **even if `default` is present**.

```java
static String withoutNullCase(Object input) {
    return switch (input) {
        case String s -> "STRING";
        default -> "OTHER";
    };
}
// withoutNullCase(null) throws NullPointerException.
```

If `null` is a valid value under the method's contract, use a separate branch:

```java
static String withNullCase(Object input) {
    return switch (input) {
        case null -> "NULL";
        case String s -> "STRING";
        default -> "OTHER";
    };
}
```

Java 21 also allows combining `null` with the fallback branch into **a single label**:

```java
static String withCombinedCase(Object input) {
    return switch (input) {
        case String s -> "STRING";
        case null, default -> "NOT_STRING";
    };
}
```

`withCombinedCase(null)` returns `NOT_STRING`; so does `withCombinedCase(123)`. The syntax `case null, default` is a specifically supported label combination, not a rule that any `default` can be arbitrarily combined with other labels.

**Recommended design:** separate `case null` when you need a distinct error or result; use `case null, default` when the business policy treats `null` and all remaining cases identically.

## 5. `default` and `when` guards

A `when` guard subdivides a type pattern by a condition. If the guard is not satisfied, `switch` continues checking other matching branches:

```java
static String numberBucket(Object input) {
    return switch (input) {
        case null -> "NULL";
        case Integer n when n < 0 -> "NEGATIVE";
        case Integer n when n == 0 -> "ZERO";
        case Integer n -> "POSITIVE";
        default -> "NOT_INTEGER";
    };
}
```

With `-1`, the negative branch matches; with `0`, the zero branch matches; with `1`, the general `Integer n` branch matches; with `"1"`, `default` matches.

Important: **`default` does not replace the general branch of the same type when you want to handle that type separately.** If you omit `case Integer n -> "POSITIVE"`, the value `1` will enter `default` and receive `NOT_INTEGER`, even though it is an `Integer`. The compiler may still accept it because `default` makes it exhaustive, but the business result is wrong.

Place guarded branches before unguarded branches of the same type; if you place `case Integer n` before `case Integer n when n < 0`, the compiler may report a **dominance** error because the later branch is shadowed.

Guards should be clear, have minimal side effects, and be easy to construct boundary data for. Minimum tests for the example above: `null`, `-1`, `0`, `1`, and a non-`Integer` value.

## 6. `default` when working with enums

For an enum whose constants are fully known:

```java
enum Direction { LEFT, RIGHT }

static String directionText(Direction direction) {
    return switch (direction) {
        case LEFT -> "L";
        case RIGHT -> "R";
    };
}
```

At compile time, the compiler knows the set of constants in `Direction`, so the `switch` expression above can be exhaustive **without writing `default`**. `direction == null` is still a separate case: without `case null`, calling the method with `null` can throw `NullPointerException`.

If you add `UP` to the enum and recompile the `switch`, the missing branch can be detected by the compiler. If from the start you write:

```java
static String directionTextWithDefault(Direction direction) {
    return switch (direction) {
        case LEFT -> "L";
        case RIGHT -> "R";
        default -> "?";
    };
}
```

then when the enum gains a new constant, `default` may silently absorb it. That may be desirable for a UI with a fallback, but it can also cause you to miss a business requirement to handle `UP` specifically.

**Question before choosing `default`:** should the appearance of a new enum constant cause existing code to **fail to compile until updated**, or can it return a fallback result? Decide based on the business contract, rather than adding `default` out of habit.

## 7. Sealed hierarchy: exhaustive without `default`

A closed set of subtypes can be modeled using a `sealed interface` and implementing records:

```java
sealed interface Outcome permits Ok, Err {}
record Ok(String message) implements Outcome {}
record Err(int code) implements Outcome {}

static String render(Outcome outcome) {
    return switch (outcome) {
        case Ok ok -> "OK:" + ok.message();
        case Err err -> "ERR:" + err.code();
    };
}
```

These are **illustrative** declarations that need to be placed in an appropriate file/class. When `Outcome` has only two permitted subtypes and the cases cover both, the compiler can prove exhaustiveness without needing `default`.

If you add a new permitted subtype `Pending` to the hierarchy and recompile, the `render` method may be required to add `case Pending p` before the code is accepted. This property is very useful for domain models where every new variant **must have its own behavior**.

Comparison:

| Strategy | Benefit | Risk/trade-off |
| --- | --- | --- |
| List all sealed/enum cases, no `default` | Compiler helps detect new cases on recompilation | Must update switch when the type domain expands |
| Add `default` with a safe result | Application has a clear fallback policy | May hide new cases not yet handled specifically |
| `default -> throw ...` | Rejects unexpected states at runtime | When a new variant is added, code may still compile but throw an error when encountering that case |
| Separate `case null` | Explicitly specifies how to handle missing input | Requires an extra branch, and does not replace covering non-null types |

Note: **exhaustiveness over subtypes does not automatically mean "null support"**. The fact that a `switch` compiles without `default` does not eliminate the need to test a `null` selector when the API allows `null`.

## 8. When should you use `default -> throw`?

In some systems, encountering a value outside the expected model is a **programming error or data error**, not a situation where you return an `"UNKNOWN"` string and continue. In that case:

```java
static String strict(Object input) {
    return switch (input) {
        case null -> throw new IllegalArgumentException("input missing");
        case String s -> "TEXT:" + s;
        case Integer n -> "INT:" + n;
        default -> throw new IllegalArgumentException(
                "Unsupported type: " + input.getClass().getName());
    };
}
```

`throw` terminates the branch with an exception and remains a valid way to handle a case that has no normal return value in a `switch` expression. It differs from `yield` in a case block: `yield` returns a value for the expression, whereas `throw` reports an error.

**Choose according to business requirements:**

- Unknown data is valid → return a meaningful fallback, e.g., `UNKNOWN`.
- Unknown data is a disallowed error → throw an intentional exception and test the exception type as well.
- Every permitted subtype needs separate logic → prefer an exhaustive switch via enum/sealed, without using `default` to mask missing branches.

Avoid gratuitous `default -> null`: it can propagate errors far from the source and cause `NullPointerException` at an unrelated location, making diagnosis difficult.

## 9. `default` is also related to dominance

When a type pattern **covers all non-null values** of the selector, `default` may not be needed to satisfy exhaustiveness. For example, a `case Object obj` branch is total for non-null `Object` values; in that case, also combining `default` will run into rules about dominating labels or duplicate match-all labels.

Think of `default` as a branch for **the remaining domain that actually needs coverage**, not a "mandatory last line" after every pattern. If the compiler says a label is dominated or that there are multiple match-all labels, analyze the coverage of the preceding labels instead of moving `default` arbitrarily.

Typically, with `String`, `Integer`, `Number` cases and an `Object` selector, there is a domain of other uncovered objects — so `default` is a natural choice. With an enum/sealed hierarchy where all cases are listed, omitting `default` can provide a better compile-time guardrail.

## 10. Complete Java 21 program: three coverage strategies

Create the file **`DefaultExhaustivenessDemo.java`**. The example includes:

- `classify(Object)`: selects `default` when the value does not match preceding type patterns.
- `traffic(int)`: uses `default` as a fallback for unlisted status codes.
- `outcome(Outcome)`: sealed hierarchy with complete cases, no `default` needed.
- `coalesce(Object)`: demonstrates the combined label `case null, default`.

```java
public class DefaultExhaustivenessDemo {
    sealed interface Outcome permits Ok, Err {}
    record Ok(String message) implements Outcome {}
    record Err(int code) implements Outcome {}

    static String classify(Object value) {
        return switch (value) {
            case null -> "NULL";
            case String text when text.isBlank() -> "BLANK";
            case String text -> "TEXT:" + text.length();
            case Integer n when n < 0 -> "NEGATIVE:" + n;
            case Integer n -> "INTEGER:" + n;
            default -> "OTHER:" + value.getClass().getSimpleName();
        };
    }

    static String traffic(int code) {
        return switch (code) {
            case 0 -> "STOP";
            case 1 -> "GO";
            default -> "UNRECOGNIZED:" + code;
        };
    }

    static String outcome(Outcome value) {
        return switch (value) {
            case null -> "NO_OUTCOME";
            case Ok ok -> "OK:" + ok.message();
            case Err err -> "ERR:" + err.code();
        };
    }

    static String coalesce(Object value) {
        return switch (value) {
            case String text -> "STRING";
            case null, default -> "NOT_STRING";
        };
    }

    public static void main(String[] args) {
        System.out.println(classify(null));
        System.out.println(classify("  "));
        System.out.println(classify("Java"));
        System.out.println(classify(-2));
        System.out.println(classify(7));
        System.out.println(classify(2.5));
        System.out.println(classify(true));

        System.out.println(traffic(0));
        System.out.println(traffic(9));

        System.out.println(outcome(new Ok("saved")));
        System.out.println(outcome(new Err(404)));
        System.out.println(outcome(null));

        System.out.println(coalesce(null));
        System.out.println(coalesce("hi"));
        System.out.println(coalesce(10));
    }
}
```

Compile and run with JDK 21 or newer:

```bash
javac --release 21 DefaultExhaustivenessDemo.java
java DefaultExhaustivenessDemo
```

**Exact standard output:**

```text
NULL
BLANK
TEXT:4
NEGATIVE:-2
INTEGER:7
OTHER:Double
OTHER:Boolean
STOP
UNRECOGNIZED:9
OK:saved
ERR:404
NO_OUTCOME
NOT_STRING
STRING
NOT_STRING
```

Analysis:

1. `classify(null)` uses `case null`; `classify("  ")` enters the `isBlank()` guard; `"Java"` enters the general `String` case.
2. `-2` enters the negative integer branch, `7` enters the remaining `Integer` branch.
3. `2.5` is a `Double` and `true` is a `Boolean`, so `default` prints the corresponding class name. Because `null` was separated earlier, `value.getClass()` in default is safe in this program.
4. `traffic(0)` matches `case 0`; `traffic(9)` enters `default`. The fallback covers unlisted integer values.
5. `outcome(new Ok(...))` and `outcome(new Err(...))` match the subtypes of sealed `Outcome`; `outcome(null)` enters `case null`. No `default` is needed just to satisfy exhaustiveness.
6. `coalesce(null)` and `coalesce(10)` both select `case null, default`; `coalesce("hi")` enters the `String` branch.

The example uses official features from Java 21. If your environment is using JDK 17, you need to upgrade the JDK to compile pattern switch and `when`.

## 11. Designing a test suite for the fallback branch

To ensure `default` does not merely "get past the compiler" but implements the requirements correctly, build a matrix covering **matching a specific case**, **matching no case**, **null input**, and **guard condition not met**.

| Test input | Test call | Expected result | Branch |
| --- | --- | --- | --- |
| `null` | `classify(null)` | `NULL` | `case null` |
| `"  "` | `classify("  ")` | `BLANK` | Guarded `String` |
| `"Java"` | `classify("Java")` | `TEXT:4` | General `String` |
| `-2` | `classify(-2)` | `NEGATIVE:-2` | Guarded `Integer` |
| `7` | `classify(7)` | `INTEGER:7` | General `Integer` |
| `2.5` | `classify(2.5)` | `OTHER:Double` | `default` |
| `true` | `classify(true)` | `OTHER:Boolean` | `default` |
| `9` | `traffic(9)` | `UNRECOGNIZED:9` | `default` |
| `null` | `coalesce(null)` | `NOT_STRING` | `case null, default` |
| `10` | `coalesce(10)` | `NOT_STRING` | `case null, default` |
| `new Ok("saved")` | `outcome(...)` | `OK:saved` | Sealed subtype |
| `new Err(404)` | `outcome(...)` | `ERR:404` | Sealed subtype |

Some boundary tests to add:

- For integers: `-1`, `0`, `1`; pay attention to the `n < 0` guard and the remaining case.
- For strings: `""`, `"\t"`, and `"x"`.
- If `default` throws an error: test that the exact exception type is thrown, rather than only observing the error on the console.
- For enum/sealed: add a new constant/subtype on a development branch to observe whether the compiler requires updating the `switch`.

**Important:** a test that only runs `default` cannot prove that preceding cases are correct, and a test suite that only runs the "happy path" will not notice the fallback accidentally absorbing inputs that should have been handled separately.

## 12. Common mistakes when using `default`

| Misconception/wrong code | Consequence | Right approach |
| --- | --- | --- |
| Assuming `default` also catches `null` | `switch(null)` can throw `NullPointerException` | `case null` or `case null, default` |
| Adding `default` without defining business behavior | Invalid states are silently ignored | Design clear error codes, fallback values, or exceptions |
| Using `default` instead of an `Integer` branch when guard is false | Valid Integer values enter another type's fallback | Add `case Integer n` after guarded branches |
| Always adding `default` to an enum/sealed with all cases listed | Compiler no longer forces reviewing new variants on recompilation | Consider omitting default to gain exhaustiveness benefits |
| Placing a general type pattern before a specific subtype | Specific branch is dominated, fails to compile | Narrower branch first, broader branch after |
| Using `default` alongside a redundant match-all type pattern | May violate dominating-label / duplicate match-all rules | Identify which label actually covers the remaining domain |
| Thinking a pattern `switch` statement does not need exhaustiveness | May be rejected by the compiler for enhanced switch statements | Distinguish traditional statements from enhanced statements |
| Writing `default -> null` unintentionally | Causes errors far from the source and is hard to trace | Return an explicit error result or `throw` |
| Assuming `default` is "the last branch in execution order" | Confused with colon-statement fall-through | Understand it as a fallback label when no other case is selected |
| Only testing specific branches | Unknown whether `default` handles other input types properly | Have dedicated tests for unlisted types/values |

## 13. Practice exercises

1. Write `switch (Object input)` with `case null`, `case String s`, `case Number n`, and `default`. Create tests for `null`, `"abc"`, `1`, `2.5`, `true`, then explain which branch is selected.
2. Try removing `default` in a `switch` expression that takes `Object` and has no catch-all type pattern. Observe the missing-exhaustiveness error; restore the fallback branch.
3. Write an example with `case Integer n when n < 0`, `case Integer n when n == 0`, `case Integer n`, `default`; explain why `1` should not fall into `default`.
4. Try calling a `switch` that has `default` but no `case null` with `null`. Check the exact exception; then add `case null`.
5. Write `enum Status { NEW, DONE }` with a `switch` expression listing both constants and no `default`. Add `CANCELED`, recompile, and update the appropriate branch. Compare with a version that has `default`.
6. Create `sealed interface Message permits Email, Sms` with two implementing records. Write an exhaustive `switch` without `default`; add a new subtype and explain the benefit of the compiler forcing a handling update.
7. Design two fallback policies for a function: `default -> "UNKNOWN"` and `default -> throw new IllegalArgumentException(...)`. Test the difference with unexpected inputs.
8. Use `case null, default` when `null` and unsupported types share the same meaning; split into two separate branches when different error messages are required.
9. Verify all 15 lines of stdout from `DefaultExhaustivenessDemo`. Add assertions or JUnit tests for the `default` branch, failed guards, and `null` selector.

**Completion criteria:** know when `default` is genuinely needed for exhaustiveness, understand the `null` exception, choose fallbacks intentionally, avoid accidentally hiding new enum constants/sealed subtypes, and write tests for both the fallback branch and specific branches.

**Official references:**

- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441).
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
- [Java Language Specification 21, §14.11 — Switch Statements](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11).
- [Java Language Specification 21, §15.28 — Switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28).
