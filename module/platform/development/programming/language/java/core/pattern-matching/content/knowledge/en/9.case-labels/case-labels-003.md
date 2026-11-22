# The `default` Case and Fallback Branches in Java Pattern Matching

In Java, `default` is the **fallback label** of a `switch`: when the selector is not handled by any applicable `case` label and a valid `default` is present, Java selects this branch. It helps define the behavior for remaining values, but it is **not a type pattern**, does not declare a pattern variable, does not automatically catch exceptions, and **does not automatically handle a `null` selector**.

Starting in Java 21, `switch` officially supports **type patterns**, **record patterns**, `when` guards, and `case null`. Because of this, `default` is used in more situations than in Java 17's constant-only `switch`: it can handle an **unsupported type**, a **value that fails a guard**, or a **data combination that matches no record pattern**. At the same time, the compiler can prove that the labels already cover all valid types and **not require `default`** in some cases.

This article covers the meaning, syntax, branch selection process, *exhaustiveness*, `null` handling, and fallback branch design strategies. Examples with type patterns/`when`/`case null` use **Java 21+**; the traditional `switch` section also includes a **Java 17+** example.

## 1. What Is `default`, and When Does It Run?

An example of a `switch expression` with an `Object` input:

```java
static String describe(Object value) {
    return switch (value) {
        case String text -> "String: " + text;
        case Integer number -> "Integer: " + number;
        case null -> "Missing";
        default -> "Unsupported";
    };
}
```

- `describe("Java")` selects `case String text`.
- `describe(42)` selects `case Integer number`.
- `describe(null)` selects `case null`.
- `describe(3.5)` selects `default`, because the runtime value is `Double`, which does not match the labels for `String` or `Integer`.
- `default` does not give us the variable `text` or `number`: those pattern variables are only in scope within their respective matched branches.

### Roles in the Syntax

| Component | Example | Meaning |
| --- | --- | --- |
| Selector expression | `value` in `switch (value)` | Evaluated to obtain the value to branch on |
| Constant case | `case 404 -> ...` | Matches against an allowed constant |
| Type pattern case | `case String text -> ...` | Tests the type and binds `text` when matched |
| Guarded pattern | `case String text when text.isBlank() -> ...` | The pattern must match, and then the guard must be true |
| Null case label | `case null -> ...` | Explicitly handles a `null` selector |
| Default label | `default -> ...` | Fallback branch when no other label applies according to `switch` rules |

You can read `default` as "everything remaining after the valid checks", rather than "whatever happens". If evaluating the selector or a guard throws an exception, the exception is **not automatically routed** to `default`.

## 2. Branch Selection Process with Patterns and Guards

When evaluating a `switch`, Java first **evaluates the selector expression**, then checks the applicable `case` labels. For a pattern case, applicability can depend on the runtime type, record component contents, and `when` guard.

```text
Evaluate selector expression
            |
            +-- throws exception -------------------> exception propagates
            |
            v
      selector value
            |
            +-- null, has case null ----------------> case null branch
            |
            +-- null, missing case null ------------> NullPointerException
            |
            +-- non-null
                    |
                    v
            Check valid cases
                    |
              pattern/constant/guard
                    |
              +-----+------+
              |            |
           matches     no label applies
              |            |
         case branch   default branch if present
```

With patterns evaluated in order, if a type pattern matches but its guard returns `false`, branch selection continues with the next eligible label. Only after no applicable label is found does `default` act as the fallback.

**Not every failed `case` means `default` runs immediately**: there may still be another pattern afterward, such as an unguarded `case String text` to handle all remaining strings.

## 3. Complete Java 21+ Example: `default` Handling Unknown Types and Failed Guards

Save as **`DefaultFallbackDemo.java`**:

```java
public class DefaultFallbackDemo {
    static String classify(Object value) {
        return switch (value) {
            case null -> "missing";
            case String text when text.isBlank() -> "blank";
            case String text -> "text:" + text;
            case Integer number when number >= 0 -> "nonnegative:" + number;
            case Integer number -> "negative:" + number;
            default -> "unsupported:" + value.getClass().getSimpleName();
        };
    }

    static String onlyGuard(Object value) {
        return switch (value) {
            case null -> "null";
            case String text when text.length() > 3 -> "long:" + text;
            default -> "fallback";
        };
    }

    public static void main(String[] args) {
        System.out.println(classify(null));
        System.out.println(classify(" "));
        System.out.println(classify("Java"));
        System.out.println(classify(3));
        System.out.println(classify(-2));
        System.out.println(classify(3.5));
        System.out.println(onlyGuard("Go"));
        System.out.println(onlyGuard("Java"));
        System.out.println(onlyGuard(42));
    }
}
```

Compile and run with JDK 21 or later:

```bash
javac DefaultFallbackDemo.java
java DefaultFallbackDemo
```

Exact output:

```text
missing
blank
text:Java
nonnegative:3
negative:-2
unsupported:Double
fallback
long:Java
fallback
```

How to read the output:

1. `null` is handled by `case null`; it does not reach `default`.
2. `" "` matches `String` and `isBlank()` is `true`; the `blank` branch is selected.
3. `"Java"` matches the `String` pattern, the `isBlank()` guard is `false`, but the next `case String text` branch still matches. Therefore `default` does not run.
4. `3` matches `Integer` and the non-negative guard; `-2` fails the guard but is handled by the next `case Integer number`.
5. `3.5` is a `Double`, matching neither `String` nor `Integer` type patterns, so `default` is selected. Calling `value.getClass()` in the fallback branch is safe in this example because a `null` selector has already been handled separately.
6. In `onlyGuard`, `"Go"` is a `String` but `text.length() > 3` is false; there is no other `String` branch, so `default` is selected. `"Java"` passes the guard so it selects `long:Java`, while `42` does not match the type pattern so it also uses `default`.

Thus `default` is the **fallback for the entire branch selection process**, not a "per-pattern else".

## 4. `default` Does Not Catch `null`

A particularly important detail in Java 21:

```java
static String classify(Object value) {
    return switch (value) {
        case String text -> "text";
        default -> "other";
    };
}
```

With `classify(null)`, the `switch` **throws `NullPointerException`**. `default` does not accept `null` in place of `case null`. The type pattern `String text` does not match `null` either.

To handle `null` as a valid business state:

```java
static String classify(Object value) {
    return switch (value) {
        case null -> "missing";
        case String text -> "text";
        default -> "other";
    };
}
```

You can use a combined label when the policy for `null` and unsupported values is the same:

```java
static String classify(Object value) {
    return switch (value) {
        case String text -> "text:" + text;
        case null, default -> "other-or-null";
    };
}
```

`case null, default` is supported starting in Java 21. A `case null` label **cannot be arbitrarily combined with a type pattern** such as `case null, String text`, because the pattern variable `text` has no binding when the selector is `null`.

**Key takeaway:** the presence of `default` helps cover unmatched types at compile time, but it **does not guarantee that every runtime value, especially `null`, will reach `default`**.

## 5. How `switch expression` and `switch statement` Use `default` Differently

### 5.1. `switch expression`: Must Produce a Value or Throw an Exception

A `switch expression` produces a value:

```java
int score = switch (status) {
    case "OK" -> 100;
    case "RETRY" -> 50;
    default -> 0;
};
```

*This is an illustrative snippet with a `status` variable of type `String`, not a complete class.*

Every selected branch must complete according to `switch expression` rules, such as yielding a compatible value or throwing an exception. If using a multi-statement block, use `yield`:

```java
int score = switch (status) {
    case "OK" -> 100;
    default -> {
        System.out.println("Unknown status: " + status);
        yield 0;
    }
};
```

A `switch expression` **must be exhaustive**: the compiler must prove that all cases within the valid value domain are covered. With an `Object` selector and only `String`/`Integer` patterns, omitting `default` or other covering branches typically causes a compile-time error:

```java
// DOES NOT COMPILE in Java 21:
// static String invalid(Object input) {
//     return switch (input) {
//         case String text -> text;
//     };
// }
```

Reason: `input` could receive an `Integer`, `Double`, or many other types; the compiler sees no label covering those values. Adding `default` can make the `switch expression` exhaustive.

### 5.2. `switch statement`: Performs Actions, Does Not Necessarily Produce a Value

Arrow-style `switch statement`:

```java
switch (status) {
    case "OK" -> System.out.println("success");
    case "RETRY" -> System.out.println("try again");
    default -> System.out.println("unrecognized");
}
```

With arrow `->` branches, there is no fall-through to subsequent branches.

With traditional colon syntax, `default:` is a label in a statement group, and **fall-through can occur if `break` is omitted**. When using labels with pattern variables, Java also enforces restrictions to prevent execution paths where a pattern variable is uninitialized. For readable, less error-prone code, prefer arrow `->` when intentional fall-through is not needed.

**Exhaustiveness distinction:** a traditional `switch statement` with only constant labels can omit `default` and do nothing if no label matches. In contrast, an **enhanced switch statement** in Java 21 with patterns or a `null` label must satisfy exhaustiveness; `default` is a common way to satisfy that requirement.

### 5.3. Complete Java 17+ Example

Save as **`ClassicDefaultDemo.java`**:

```java
public class ClassicDefaultDemo {
    static String byCode(int code) {
        return switch (code) {
            case 200 -> "OK";
            case 404 -> "NOT_FOUND";
            default -> "UNMAPPED";
        };
    }

    static void withoutDefault(int code) {
        switch (code) {
            case 200:
                System.out.println("statement: OK");
                break;
            case 404:
                System.out.println("statement: NOT_FOUND");
                break;
        }
        System.out.println("statement: done");
    }

    public static void main(String[] args) {
        System.out.println(byCode(200));
        System.out.println(byCode(503));
        withoutDefault(503);
    }
}
```

```bash
javac ClassicDefaultDemo.java
java ClassicDefaultDemo
```

```text
OK
UNMAPPED
statement: done
```

In `byCode(503)`, `default` produces `UNMAPPED` for the `switch expression`. In `withoutDefault(503)`, the traditional `switch statement` has no matching label, so it prints nothing inside the `switch` block; execution continues and prints `statement: done`. This is a common difference encountered when transitioning from legacy `switch` constructs to pattern matching.

## 6. When `default` Is Not Needed: Exhaustiveness with `sealed` and `enum`

`default` is very useful when the input has an open domain, such as `Object` or data from an external API. However, with a bounded set of types where the compiler can prove full coverage, `default` **may not be needed**.

### 6.1. Sealed Hierarchy

Suppose in Java 21 we have a `sealed interface` with two permitted cases:

```java
sealed interface Response permits Success, Failure {}
record Success(String data) implements Response {}
record Failure(int code) implements Response {}
```

The following `switch expression` is exhaustive without `default`:

```java
static String show(Response response) {
    return switch (response) {
        case Success success -> "success:" + success.data();
        case Failure failure -> "failure:" + failure.code();
    };
}
```

The compiler knows `Response` can only be implemented by `Success` and `Failure` in this hierarchy. If another permitted branch is added later and the relevant sources are recompiled, the `switch` will typically need to be updated. Omitting `default` lets the compiler point out where handling is incomplete. If an older binary was compiled assuming exhaustiveness and the hierarchy changes incompatibly, Java may throw `MatchException` when no runtime branch applies; the affected classes should be recompiled.

Complete example, save as **`ExhaustiveDemo.java`**:

```java
sealed interface Response permits Success, Failure {}
record Success(String data) implements Response {}
record Failure(int code) implements Response {}

public class ExhaustiveDemo {
    static String show(Response value) {
        return switch (value) {
            case Success success -> "success:" + success.data();
            case Failure failure -> "failure:" + failure.code();
        };
    }

    public static void main(String[] args) {
        System.out.println(show(new Success("ok")));
        System.out.println(show(new Failure(403)));
        try {
            System.out.println(show(null));
        } catch (NullPointerException ex) {
            System.out.println("null: NullPointerException");
        }
    }
}
```

```bash
javac ExhaustiveDemo.java
java ExhaustiveDemo
```

```text
success:ok
failure:403
null: NullPointerException
```

**Exhaustiveness does not mean `null` is handled:** without `case null`, `show(null)` still throws an NPE. This does not contradict the fact that all non-`null` types are covered by the compiler.

### 6.2. Enum

With an `enum`, if a `switch expression` has a case for **every enum constant**, the compiler does not require `default`. This often helps surface places that need updating when a new enum constant is added.

Still, consider the design trade-off: a generic `default` branch can silently alter business behavior when an enum or sealed hierarchy grows. For closed type domains where **each case requires dedicated handling**, omitting `default` helps catch missing cases at recompile time. For unsupported external data, an explicit `default` remains appropriate.

## 7. You Cannot Always Add `default` Next to an Unconditional Pattern

In Java 21, a pattern can cover all non-`null` values of the selector, for example:

```java
static String describe(Object value) {
    return switch (value) {
        case Object obj -> "object";
    };
}
```

Here `case Object obj` is an **unconditional pattern** for an `Object` selector: every non-`null` object is an `Object`. Attempting to add a separate `default` in the same `switch` causes a compile-time error:

```java
// DOES NOT COMPILE:
// static String describe(Object value) {
//     return switch (value) {
//         case Object obj -> "object";
//         default -> "unreachable";
//     };
// }
```

The compiler reports that the `switch` has both an unconditional pattern and `default`. So you cannot always "add `default` just to be safe". If you only need a catch-all branch for any object, use an unconditional pattern matching that scope and handle `null` separately if `null` should be supported.

Additionally, the compiler applies **dominance checking** to type patterns to prevent specific branches from being shadowed by an overly broad preceding pattern:

```java
// DOES NOT COMPILE: the String branch is dominated by the preceding CharSequence.
// switch (value) {
//     case CharSequence seq -> ...;
//     case String text -> ...;
//     default -> ...;
// }
```

Place specific patterns before broader patterns; use `default` for remaining values and avoid confusing a pattern branch with a patternless fallback branch.

## 8. `default` Does Not Share Pattern Variables from Previous Branches

Example:

```java
switch (value) {
    case String text -> System.out.println(text.toUpperCase());
    case Integer number -> System.out.println(number + 1);
    case null -> System.out.println("missing");
    default -> System.out.println("unsupported");
}
```

The `default` branch cannot access `text` or `number`, because when it is selected, there is no guarantee that either preceding pattern matched. `default` declares no bindings of its own. If you need information about the unsupported value, use the **previously declared selector variable**, for example:

```java
default -> System.out.println("unsupported: " + value.getClass().getName());
```

In this example, `getClass()` can be called when a `case null` branch has already separated out `null` and no other error occurred earlier. Without `case null`, a `null` value causes the `switch` to throw an NPE before `default` runs.

If you need to handle a new type, declare a separate type pattern:

```java
case java.time.LocalDate date -> System.out.println(date.getYear());
```

This is a new case with the binding `date`; it is not reusing a pattern variable from a previous case.

## 9. What Should the Fallback Branch Return?

`default` is where you **define the policy when input is not supported by specialized branches**. There are three common choices:

1. **A valid fallback value** — suitable for UI/display or reporting: `default -> "UNKNOWN"`. Clarify whether this value is acceptable to users or downstream processing.
2. **Explicitly reject the input** — suitable for strict invariants/domains: `default -> throw new IllegalArgumentException(...)`.
3. **Log information and return a fallback** — useful when you want observability into unsupported input types: use a block `default -> { log(...); yield value; }` in a `switch expression`.

Do not use `default` to hide anomalous data when the application needs to detect unsupported input types. Avoid arbitrarily returning `null` as a fallback if downstream callers will dereference it.

### Example: Default Fallback, Fail-Fast, and Combining `null`

Save as **`FallbackPolicyDemo.java`** (Java 21+):

```java
public class FallbackPolicyDemo {
    static String strict(Object input) {
        return switch (input) {
            case null -> "missing";
            case String text -> "text:" + text;
            case Integer number -> "integer:" + number;
            default -> throw new IllegalArgumentException(
                    "Unsupported: " + input.getClass().getSimpleName());
        };
    }

    static String combined(Object input) {
        return switch (input) {
            case String text -> "text:" + text;
            case null, default -> "other-or-null";
        };
    }

    public static void main(String[] args) {
        System.out.println(strict("hello"));
        System.out.println(strict(null));
        try {
            System.out.println(strict(2.5));
        } catch (IllegalArgumentException ex) {
            System.out.println(ex.getMessage());
        }
        System.out.println(combined(null));
        System.out.println(combined(2.5));
    }
}
```

```bash
javac FallbackPolicyDemo.java
java FallbackPolicyDemo
```

```text
text:hello
missing
Unsupported: Double
other-or-null
other-or-null
```

`strict` treats unsupported types as errors and throws an `IllegalArgumentException` with a clear message. `combined` intentionally merges `null` and unsupported types into the same fallback. These are two different policies; choose according to the actual data contract.

## 10. Notes on Guards and Exceptions

In the example:

```java
return switch (value) {
    case String text when text.length() >= 4 -> "long text";
    default -> "other";
};
```

If `value` is a short string, the `String text` pattern matches but the guard returns `false`, so `default` can be selected. However, if the expression in the guard or evaluating the selector throws an exception, `default` **does not automatically catch** that exception. Handle exceptions with an appropriate error policy, such as `try/catch` at the boundary where recovery is actually needed.

With record patterns, some patterns only apply when components have the right type or matching structure. When a component pattern does not match and there is no subsequent pattern, `default` is a valid fallback branch for non-`null` objects — but it is not a mechanism for turning a data-access error into a failed match.

**Do not attach a guard to `default`** as if `default when ...` were a guarded pattern: `when` belongs to a **pattern case** and checks a condition after the pattern matches, not to the `default` label. If you want conditional fallback behavior, put that condition inside the `default` body or write appropriate patterns/guards in preceding branches.

## 11. Syntax Rules and Common Mistakes

| Mistake | Correct Explanation |
| --- | --- |
| Thinking `default` catches `null` too | In Java 21, a `null` selector without `case null` throws `NullPointerException` |
| Thinking `default` is a type pattern | `default` is a fallback label; it does not check types or create a pattern variable |
| Thinking a failed guard always jumps straight to `default` | Another `case` may still apply, such as an unguarded `case String text` |
| Putting `default` in a `switch expression` and forgetting to return a value | The branch must produce a value via an expression/`yield` or end with `throw` |
| Omitting `default` in a `switch expression` over `Object` without exhaustiveness | The compiler rejects it if the labels do not cover all possible types |
| Omitting `default` in a traditional `switch statement` | Can be valid; when no case matches, the statement continues without executing any group |
| Assuming a `switch statement` with patterns can always omit `default` | An enhanced switch using patterns/`null` must be exhaustive |
| Assuming missing `default` is always an error | `enum`/`sealed` or an unconditional pattern can cover the type without `default` |
| Combining an unconditional pattern with `default` | Java rejects it when a pattern already covers the entire selector type |
| Referencing `case String text`'s pattern variable inside `default` | That variable is not in scope inside `default` |
| Using `default` as a replacement for `catch` | Exceptions thrown while evaluating the selector, guard, or branch body do not route to `default` |
| Using `default:` with legacy syntax and forgetting `break` | Can cause fall-through; `->` syntax is clearer when fall-through is not needed |

A rule of thumb for **placement**: usually put `default` at the end of the block so readers recognize it as the fallback behavior. For pattern cases, always pay attention to **order, dominance, and exhaustiveness** per compiler rules; the order of cases can change which branch is selected when broad patterns and guards are involved.

## 12. Design and Testing Checklist

When writing or reviewing a `switch` with `default`:

1. **Identify the static type and value domain of the selector.** Is it `Object`, `String`, an `enum`, or a sealed hierarchy?
2. **Check the kind of `switch`.** Expressions require exhaustiveness; traditional statements and enhanced statements have different rules.
3. **Check `null` handling.** If `null` is valid, is there a `case null` or `case null, default` in Java 21+? If `null` is disallowed, is there a clear contract for rejecting it?
4. **Walk through each case with patterns and `when`.** When a guard is false, is there another case that handles the same type, or should it go to `default`?
5. **Evaluate the fallback policy.** Return a representative value, throw a domain error, or log and return a fallback?
6. **Check exhaustiveness cases.** With `sealed`/`enum`, is it better to let the compiler enforce updating every case rather than masking new branches with `default`?
7. **Do not rely on pattern variables in `default`.** Use the selector, validated data, or declare a new pattern.
8. **Test tricky cases:** pattern-matching values, different types, true/false guards, `null`, new `enum`/`sealed` branches, and exceptions from related expressions.
9. **Compile with the right Java version.** Pattern matching for `switch` and `case null` were standardized in Java 21. Java 17 has `switch expression` with constants but does not support the patterns/`when` in the Java 21 examples.
10. **Verify outputs and side effects.** Pay special attention to `yield` in `switch expression` blocks, `break` in traditional statements, and ensuring fallback branches do not mask real bugs.

### Summary of Scenarios

```text
switch (value) {
  case String text -> ...;
  case Integer number -> ...;
  case null -> ...;
  default -> ...;
}

value == "Java"  -> String case
value == 42      -> Integer case
value == 3.14    -> default
value == null    -> case null

If case null is omitted: null -> NullPointerException, does not enter default.
If case labels are already exhaustive: default may not be needed.
If an unconditional pattern is already present: do not add a separate default.
```

**Remember:** `default` defines the policy when no `case` label applies; it does not perform type checks, does not provide pattern variables, and does not replace `case null`. Use `default` when values outside the classified cases genuinely exist; for closed exhaustive domains, consider letting the compiler verify completeness.

## References

- [Oracle Java 21 — Pattern Matching for switch Expressions and Statements](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html): pattern labels, `when`, dominance, type coverage, `case null`, and `case null, default`.
- [Oracle Java 21 — Switch Expressions](https://docs.oracle.com/en/java/javase/21/language/switch-expressions.html): `switch expression` syntax, `yield`, and return values.
- [Java Language Specification 21 — `14.11 switch Statements](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11) and [`15.28 switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28): exhaustiveness and execution rules.
