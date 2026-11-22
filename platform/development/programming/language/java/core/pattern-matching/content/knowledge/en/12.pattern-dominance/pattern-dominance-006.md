# The default Case and Dominance in Java Pattern Matching for switch

## 1. Goal: Understanding the Exact Relationship Between `default` and Other `case` Labels

In Java, `switch` selects a branch based on the value of the selector expression. With **Pattern Matching for switch** (standardized in **Java 21**, JEP 441), a `case` can test an object's type using a type pattern, such as `case String s`, or test an additional condition using `when`.

When combining constant cases, pattern cases, and the `default` label, you must understand two distinct concepts:

- **Dominance:** an earlier case label already covers all values that a later case label could match. The compiler rejects many such cases because the later branch becomes unreachable for selection.
- **Default:** the fallback label when no other applicable case label matches the value (for a non-`null` selector); it **does not declare a pattern variable** and **does not handle `null` on its own**.

A **valid** Java 21 example:

```java
static String describe(Object value) {
    return switch (value) {
        case String text -> "TEXT:" + text;
        case Integer n   -> "INTEGER:" + n;
        case null        -> "NULL";
        default          -> "OTHER";
    };
}
```

A `String` value is handled by the `case String text` branch; `Integer` enters the `case Integer n` branch; `null` has its own label; and any value that does not match the remaining cases goes to `default`.

**Foundational rule:** `default` is not an escape hatch from pattern switch rules. Adding `default` can make a switch exhaustive, but it cannot fix a **dominated case**, misordered case labels, or invalid pattern variable declarations.

This article analyzes both the **common rule** and the **backward-compatibility exception** in Java 21: `default` should be placed last, though the specification still allows `default` before cases that **contain only constants** in certain constructs. Conversely, placing `default` before a pattern case or `case null` causes a compile-time error.

Complete examples in this article use **Java 21 or later, without preview features enabled**. Snippets marked “DOES NOT COMPILE” are only meant to explain errors and should not be included in a standalone runnable program.

## 2. What Is Dominance?

Consider two pattern cases on the same `Object value` selector:

```java
// DOES NOT COMPILE on Java 21:
// return switch (value) {
//     case Number number -> "NUMBER";
//     case Integer n     -> "INTEGER"; // Dominated by Number.
//     default            -> "OTHER";
// };
```

`Integer` is a subclass of `Number`. Every `Integer` object matches `case Number number`. Because the general case comes first, the subsequent `case Integer n` never has a chance to be selected. This is a **dominated case label** error at compile time.

**Fix: place the specialized case first:**

```java
static String numberKind(Object value) {
    return switch (value) {
        case Integer n    -> "INTEGER:" + n;
        case Number other -> "NUMBER:" + other;
        default           -> "OTHER";
    };
}
```

When given `Integer.valueOf(5)`, the first branch is selected; when given `Double.valueOf(2.5)`, the `Number other` branch is selected. `default` only handles types that do not match the two patterns above.

Notably: **`default` at the end does not make `case Integer n` after `case Number number` valid**. The error is caused by the **coverage relationship between the two case patterns**, not by a missing fallback branch.

### 2.1. “Coverage” Can Occur Between a Pattern and a Constant

```java
// DOES NOT COMPILE:
// return switch (value) {
//     case Integer n -> "INTEGER";
//     case 42        -> "FORTY_TWO"; // 42 always matches Integer.
//     default        -> "OTHER";
// };
```

With an `Object` selector, the constant `42` is a valid constant case comparison. However, the unguarded `case Integer n` before it already matches every `Integer` value, including `42`, so the subsequent constant branch is dominated.

**Place the constant case before the general pattern:**

```java
static String classifyInteger(Object value) {
    return switch (value) {
        case 42        -> "FORTY_TWO";
        case Integer n -> "INTEGER:" + n;
        default        -> "OTHER";
    };
}
```

The same applies to enums: if `case State state` already matches every constant of `State`, then `case State.FAILED` after it will be dominated. To handle a specific enum constant separately, place `case State.FAILED` before `case State state`.

### 2.2. Dominance Differs from Exhaustiveness

These two compiler checks answer different questions:

| Concept | Question | Typical Error |
| --- | --- | --- |
| **Dominance** | Is a later branch covered by an earlier branch? | `Number` placed before `Integer` |
| **Exhaustiveness** | Do all possible values of the selector type have a handling branch? | A switch expression on `Object` with only `case String`, missing the remaining cases |

A switch can be **exhaustive thanks to `default` and still have a dominance error**, and a switch with no dominated branches can still **lack exhaustiveness**.

## 3. How Does `default` Work?

The `default` label is the final fallback when a non-`null` selector value does not match any of the other case labels.

```java
static String category(Object value) {
    return switch (value) {
        case String s  -> "STRING";
        case Number n  -> "NUMBER";
        default        -> "OTHER";
    };
}
```

- `category("hi")` returns `"STRING"`.
- `category(10)` returns `"NUMBER"` because `Integer` is a `Number`.
- `category(true)` returns `"OTHER"` because `Boolean` matches neither `String` nor `Number`.

**`default` does not declare a variable**. There is no syntax like `case default Object x`; if you need an `Object`-typed variable in a branch, use an appropriate **type pattern** such as `case Object x` (but see the conflict rules in Section 5).

### 3.1. It Is Not “Executed Immediately Because It Appears First”

In Java 21 branch selection logic, `default` is applied when no other case label matches the selector, not simply because it is “the first label present in the file”. However, **placement in code** is constrained by syntax and dominance rules, so the best practice remains **placing `default` at the end of the switch**.

With the `case ... ->` syntax, each rule handles its own block; there is no fall-through like with `:` switch-labeled statement groups. With `case ... :` statement groups, in addition to label selection, you must also manage `break`, `return`, or `throw` to avoid falling through into the next statement group.

### 3.2. `default` Makes a Switch Expression Exhaustive

```java
static String safeKind(Object value) {
    return switch (value) {
        case String s -> "TEXT:" + s.length();
        default       -> "OTHER";
    };
}
```

`Object` is an open type: values can belong to countless types other than `String`. The `default` label covers the remaining values, so the switch expression is considered **type-exhaustive**. However, when `value == null`, Java still throws `NullPointerException` if there is no `case null` label. Do not confuse exhaustiveness with safely handling all `null` values.

## 4. Placement Rules: `default` Usually Goes Last, but Understand the Exception

According to **Java Language Specification 21, §14.11.1**, the following rules apply:

1. **Compile-time error** if a `default` label precedes a `case` label that contains a **case pattern**.
2. **Compile-time error** if a `default` label precedes a `case null` label.
3. **Compile-time error** if a combined `case null, default` label precedes **any other switch label**.
4. **For backward compatibility**, a `default` preceding labels that **contain only case constants, with no `null` or pattern**, can still be valid.
5. **Recommended style:** always place `default` or `case null, default` last so readers do not have to guess the order.

### 4.1. Invalid: `default` Before a Type Pattern

```java
// DOES NOT COMPILE:
// static String bad(Object value) {
//     return switch (value) {
//         default       -> "OTHER";
//         case String s -> "STRING";  // Pattern appears after default.
//     };
// }
```

Even if you think of `case String s` as a specialized exception to `default`, this ordering is invalid for **case patterns**.

**Fix:**

```java
static String fixed(Object value) {
    return switch (value) {
        case String s -> "STRING:" + s;
        default       -> "OTHER";
    };
}
```

### 4.2. Invalid: `default` Before `case null`

```java
// DOES NOT COMPILE:
// return switch (value) {
//     default   -> "OTHER";
//     case null -> "NULL";
// };
```

The valid form to use:

```java
return switch (value) {
    case null -> "NULL";
    default   -> "OTHER";
};
```

The snippet above only illustrates a `return switch` expression inside a method where `value` is declared and the return type is `String`.

### 4.3. Exception: `default` Before a Constant Case Can Be Valid

For compatibility with earlier switches, the Java 21 specification permits the following form:

```java
static String legacyOrder(int number) {
    return switch (number) {
        default -> "OTHER";
        case 42 -> "FORTY_TWO";
    };
}
```

This snippet **compiles**. `legacyOrder(42)` still evaluates to `"FORTY_TWO"`, not `"OTHER"`, even though `default` is written first. `legacyOrder(7)` returns `"OTHER"`.

**However, write it in a more readable order:**

```java
static String recommendedOrder(int number) {
    return switch (number) {
        case 42 -> "FORTY_TWO";
        default -> "OTHER";
    };
}
```

This is an exception for **constant** labels, not a license to place `default` before `case String s` or `case null`. A project using pattern switches should consistently place `default` last.

## 5. Conflict: `default` and Unconditional Patterns

An **unconditional pattern** for a selector type is a pattern that matches every value of the selector type (according to Java's definition), so it acts as a **catch-all for the type**, much like a fallback branch.

Example with an `Object value` selector:

```java
static String withoutDefault(Object value) {
    return switch (value) {
        case null     -> "NULL";
        case String s -> "TEXT:" + s;
        case Object o -> "OBJECT:" + o.getClass().getSimpleName();
    };
}
```

In `case Object o`, `Object` is a type pattern that covers every remaining **non-`null`** value of the `Object` selector. The compiler considers the switch expression exhaustive even **without `default`**. `case null` is used to handle null values separately.

### 5.1. Invalid: Unconditional Pattern Followed by `default`

```java
// DOES NOT COMPILE:
// return switch (value) {
//     case String s -> "STRING";
//     case Object o -> "OBJECT";
//     default       -> "OTHER"; // Default is dominated.
// };
```

When `case Object o` is an unguarded pattern that is **unconditional for the selector type**, it already covers all objects under consideration. The `default` that follows is **dominated**.

### 5.2. Reversing the Order Does Not Fix It Either

```java
// DOES NOT COMPILE:
// return switch (value) {
//     case String s -> "STRING";
//     default       -> "OTHER";
//     case Object o -> "OBJECT"; // Pattern appears after default.
// };
```

Now the error violates the rule that **`default` must not precede a case pattern**. Therefore, in a switch with the same selector type, you cannot keep both an **unconditional pattern** and `default` by swapping their positions.

**Two alternative designs:**

- **Use `default`:** `case String s -> ...; default -> ...;`. No pattern variable for the fallback branch.
- **Use an unconditional type pattern:** `case String s -> ...; case Object o -> ...;`. The variable `o` lets you process the object in the catch-all branch. Add `case null` if you want to handle `null`.

When you do not need to access object details in the final branch, `default` is usually simpler. When you need the runtime type or to call common APIs on the matched object, an unconditional type pattern can be useful.

### 5.3. Do Not Confuse a “Union of Multiple Cases” with an Unconditional Pattern

Example of a sealed interface with two subtypes:

```java
sealed interface Event permits Started, Finished {}
record Started(String name) implements Event {}
record Finished(int code) implements Event {}
```

The two patterns `case Started s` and `case Finished f` together can be **exhaustive** for the `Event` type. However, they are **two separate patterns**, not a single unconditional `case Event e`.

To keep the compiler reminding you when a new subtype is added, you typically **do not need to write `default`**:

```java
static String render(Event event) {
    return switch (event) {
        case Started s  -> "START:" + s.name();
        case Finished f -> "END:" + f.code();
    };
}
```

Distinguish the two concepts: “cases combined cover the entire type” (exhaustiveness) and “a single pattern covers every value of the selector type” (unconditional pattern).

## 6. `case null`, `default`, and `case null, default`

These are three **different** constructs:

| Label | Applies to `null`? | Applies to remaining values? | Declares a variable? |
| --- | --- | --- | --- |
| `case null` | Yes | No | No |
| `default` | No: `null` normally throws `NullPointerException` if no null label is present | Yes, when no other case matches | No |
| `case null, default` | Yes | Yes, as the fallback branch | No |
| `case Object o` on selector `Object` | Does not match `null` | Yes, for non-`null` objects | Yes: `o` |

### 6.1. Separating Null Handling

```java
static String separated(Object value) {
    return switch (value) {
        case null      -> "NO_VALUE";
        case String s  -> "TEXT:" + s;
        default        -> "OTHER";
    };
}
```

For `null`, it returns `NO_VALUE`. For `"a"`, it returns `TEXT:a`. For `Integer.valueOf(7)`, it returns `OTHER`.

### 6.2. Combining Null with Default

```java
static String combined(Object value) {
    return switch (value) {
        case String s     -> "TEXT:" + s;
        case null, default -> "OTHER_OR_NULL";
    };
}
```

This is valid Java 21 syntax. `case null, default` handles both `null` and any other value that does not match `String` in the same way. It **must be at the end of the switch**, because Java 21 rules forbid any switch label after it.

**Invalid:**

```java
// DOES NOT COMPILE:
// return switch (value) {
//     case null, default -> "OTHER";
//     case String s      -> "STRING"; // Any label after is forbidden.
// };
```

### 6.3. You Cannot Declare Two `default` Labels

```java
// DOES NOT COMPILE:
// switch (value) {
//     case String s -> System.out.println("TEXT");
//     default       -> System.out.println("OTHER_A");
//     default       -> System.out.println("OTHER_B");
// }
```

A switch cannot have more than one `default` label. A `case null, default` already includes `default`, so you cannot add a second `default`.

### 6.4. `null` Is Not a Type Pattern

`case null` does not introduce a variable like `case String s`. It is a dedicated label for the null value.

```java
static String nullAware(Object value) {
    return switch (value) {
        case null -> "NULL";
        case String text when text.isBlank() -> "BLANK";
        case String text -> "TEXT:" + text;
        default -> "OTHER";
    };
}
```

Because `null` is handled first, the guard `text.isBlank()` is only evaluated once the selector has matched `String`; `isBlank()` is never invoked on an unmatched null reference.

## 7. The `when` Guard: Why Not Every Earlier Case Dominates a Later Case

A **guarded pattern** only matches when:

1. The selector value matches the pattern.
2. The `when` expression evaluates to `true`.

Example:

```java
static String textKind(Object value) {
    return switch (value) {
        case String s when s.isBlank() -> "BLANK";
        case String s                  -> "TEXT:" + s.strip();
        default                        -> "OTHER";
    };
}
```

The first branch only accepts whitespace-only strings (including the empty string); it **does not dominate** the subsequent `case String s` branch, because many strings do not satisfy `isBlank()`. `default` handles non-`String` types.

Conversely:

```java
// DOES NOT COMPILE:
// return switch (value) {
//     case String s                  -> "ANY_STRING";
//     case String s when s.isBlank() -> "BLANK"; // Dominated.
//     default                        -> "OTHER";
// };
```

The unguarded `case String s` branch already accepts all non-`null` `String` objects; the guarded branch after it never has a chance to run.

### 7.1. A Guard Does Not Cause `default` to Be Dominated

```java
static String longStringOrOther(Object value) {
    return switch (value) {
        case String s when s.length() > 3 -> "LONG";
        default                           -> "NOT_LONG";
    };
}
```

Even though some `String` values are matched by the first branch, strings of length less than or equal to 3 and other object types still need a handling path. Therefore, `default` is valid and required for the switch expression to be exhaustive.

### 7.2. How Should Guards and `true` Conditions Be Written?

Do not use `when` just to compare an enum constant if you can write a constant case directly:

```java
// Can be expressed more simply with an enum constant:
case Status.FAILED -> "FAILED";
```

When an extra condition genuinely needs to access the matched data, `case String s when s.length() > 3` is valuable. Place specialized guarded cases before general cases to avoid dominance.

### 7.3. `default` Cannot Be Used with `when`

```java
// INVALID:
// default when flag -> "OTHER";
```

`when` belongs to **case patterns**, not as a modifier for the `default` label. If you want an additional condition inside the default branch, write an `if` inside the rule body/block, or redesign the specialized cases.

## 8. Constant Cases, Enums, and `default`

**Case constants** include integer constants, string constants, and enum constants (when the selector type is compatible). Dominance also occurs when a broader pattern precedes a constant.

Suppose:

```java
enum State { CREATED, DONE, FAILED }
```

A switch on `Object` can be written as:

```java
static String stateKind(Object value) {
    return switch (value) {
        case State.FAILED -> "FAILED";
        case State state  -> "STATE:" + state;
        default           -> "OTHER";
    };
}
```

`State.FAILED` is a **case constant**: it matches that exact constant. `case State state` is a **type pattern**: it matches the remaining `State` constants and binds the variable `state`. Placing the specific constant before the general pattern is valid.

**Reversing the order causes an error:**

```java
// DOES NOT COMPILE:
// return switch (value) {
//     case State state  -> "STATE:" + state;
//     case State.FAILED -> "FAILED"; // Dominated by the State pattern.
//     default           -> "OTHER";
// };
```

Here, adding `default` does not resolve the dominated `State.FAILED` branch.

### An Exhaustive Enum Switch Does Not Necessarily Need `default`

```java
static String directState(State state) {
    return switch (state) {
        case CREATED -> "CREATED";
        case DONE    -> "DONE";
        case FAILED  -> "FAILED";
    };
}
```

The switch expression is already exhaustive because it lists all three constants of `State`. No `default` is needed.

If a new enum constant is added later and the code is **recompiled**, omitting `default` is beneficial: the compiler can require updating the switch for the new domain value. If you use `default` to catch any unfamiliar constant, you might overlook a new business state.

However, omitting `case null` means passing `null` to the enum switch can still throw `NullPointerException`; exhaustiveness over enum constants does not handle null automatically.

## 9. Is `default` Always the Best Solution for Exhaustiveness?

No. In Java 21, **switch expressions** and **enhanced switch statements** must be exhaustive, but some input types have a closed set of options that the compiler can verify completely.

Compare:

**Approach 1 — catch all remaining types with `default`:**

```java
static String openInput(Object value) {
    return switch (value) {
        case String s -> "TEXT";
        case Integer n -> "NUMBER";
        default -> "OTHER";
    };
}
```

For `Object`, `default` makes sense because the object can belong to many other types.

**Approach 2 — sealed hierarchy without `default`:**

```java
sealed interface Result permits Ok, Error {}
record Ok(String data) implements Result {}
record Error(int code) implements Result {}

static String render(Result result) {
    return switch (result) {
        case Ok ok       -> "OK:" + ok.data();
        case Error error -> "ERR:" + error.code();
    };
}
```

Because `Result` only permits the two record types above, the compiler can prove exhaustiveness. Without `default`, when you **update and recompile** the sealed hierarchy to add a new subtype, the compiler can remind you to update the relevant switches.

### 9.1. Exhaustiveness Differs from Dominance

A switch on a sealed interface with both `case Ok` and `case Error` is exhaustive; that does not mean one pattern dominates the other. If you instead put `case Result result` first, it is an unconditional/catch-all pattern and the subsequent `Ok`/`Error` cases will be dominated.

**Invalid:**

```java
// DOES NOT COMPILE:
// return switch (result) {
//     case Result any -> "RESULT";
//     case Ok ok      -> "OK"; // Already covered by Result.
//     case Error err  -> "ERROR";
// };
```

**Fix:** place the specialized `Ok` and `Error` cases first. If they are already exhaustive, you can omit the general branch.

### 9.2. Runtime Exceptions Can Still Occur

Do not treat `default` or exhaustiveness as a guarantee that the program will never fail. A case body can still throw an exception; omitting `case null` can cause an NPE; and un-recompiled library changes can create mismatches between compile-time assumptions and runtime reality.

The purpose of dominance and exhaustiveness is **language-level control-flow checking**, not replacing business-logic testing.

## 10. Standalone Java 21 Code: Observing `default` and Patterns

Create the file **`DefaultDominanceDemo.java`**:

```java
public class DefaultDominanceDemo {

    enum State { CREATED, DONE, FAILED }

    sealed interface Event permits Started, Finished {}

    record Started(String name) implements Event {}

    record Finished(int code) implements Event {}

    // Specialized pattern before broader pattern;
    // default catches unmatched values.
    static String classify(Object value) {
        return switch (value) {
            case null                  -> "NULL";
            case Integer n when n < 0  -> "NEG:" + n;
            case Integer n             -> "INT:" + n;
            case CharSequence text     -> "TEXT:" + text;
            default                    -> "OTHER";
        };
    }

    // An unconditional pattern instead of default.
    static String catchAll(Object value) {
        return switch (value) {
            case null     -> "NO_VALUE";
            case String s -> "S:" + s;
            case Object o -> "O:" + o.getClass().getSimpleName();
        };
    }

    // Combining null label with default: must be placed last.
    static String longOrOther(Object value) {
        return switch (value) {
            case String s when s.length() > 3 -> "LONG:" + s.length();
            case null, default               -> "NOT_LONG_STRING";
        };
    }

    // Specific constant before general enum type pattern.
    static String state(Object value) {
        return switch (value) {
            case State.FAILED -> "FAILED";
            case State s      -> "STATE:" + s.name();
            default           -> "OTHER";
        };
    }

    // Exhaustive sealed hierarchy, no default needed.
    static String event(Event event) {
        return switch (event) {
            case Started s  -> "START:" + s.name();
            case Finished f -> "END:" + f.code();
        };
    }

    // Backward-compatibility exception: default before constant case
    // is allowed, though this style should not be used regularly.
    static String legacyOrder(int number) {
        return switch (number) {
            default -> "OTHER";
            case 42 -> "FORTY_TWO";
        };
    }

    public static void main(String[] args) {
        System.out.println(classify(-2));
        System.out.println(classify(0));
        System.out.println(classify("Java"));
        System.out.println(classify(new StringBuilder("Hi")));
        System.out.println(classify(1.5));
        System.out.println(classify(null));

        System.out.println(catchAll("A"));
        System.out.println(catchAll(7));
        System.out.println(catchAll(null));

        System.out.println(longOrOther("Java"));
        System.out.println(longOrOther("Go"));
        System.out.println(longOrOther(null));

        System.out.println(state(State.FAILED));
        System.out.println(state(State.DONE));
        System.out.println(state(100));

        System.out.println(event(new Started("Job")));
        System.out.println(event(new Finished(0)));

        System.out.println(legacyOrder(42));
        System.out.println(legacyOrder(7));
    }
}
```

Compile and run with **JDK 21 or later**, no preview required:

```bash
javac --release 21 DefaultDominanceDemo.java
java DefaultDominanceDemo
```

**Expected output, in exact order:**

```text
NEG:-2
INT:0
TEXT:Java
TEXT:Hi
OTHER
NULL
S:A
O:Integer
NO_VALUE
LONG:4
NOT_LONG_STRING
NOT_LONG_STRING
FAILED
STATE:DONE
OTHER
START:Job
END:0
FORTY_TWO
OTHER
```

### Explanation of Key Results

1. `classify(-2)`: `Integer` matches, the guard `n < 0` is true, returning `NEG:-2`. `classify(0)` proceeds to the general `case Integer n` and returns `INT:0`.
2. `classify("Java")` and `classify(new StringBuilder("Hi"))`: both `String` and `StringBuilder` implement `CharSequence`, so they return `TEXT:Java` and `TEXT:Hi`.
3. `classify(1.5)` receives a `Double`; it is neither `Integer` nor `CharSequence`, so it enters `default`.
4. `catchAll("A")` enters the narrower `String` branch; `catchAll(7)` enters `case Object o` and retrieves the class name `Integer`. `catchAll(null)` is handled first by `case null`.
5. `longOrOther("Java")` matches the guard length greater than 3; `"Go"` fails the guard so it goes to `case null, default`. For `null`, the combined label is also selected.
6. `state(State.FAILED)` is handled by the enum constant branch before the `State s` pattern; `state(State.DONE)` enters the type pattern; `state(100)` selects `default`.
7. `event` covers all subtypes of `Event` (sealed), so no `default` is needed.
8. `legacyOrder(42)` still selects `case 42` even though the `default` label is written first; `legacyOrder(7)` returns `OTHER`. This is a **backward-compatibility exception**, not an ordering to apply to pattern switches.

The examples intentionally **omit** invalid snippets (dominated cases, `default` before pattern/null, `case null, default` not placed last) from the runnable file. To observe `javac` errors, test each invalid snippet individually in an experimental file.

## 11. Common `default` and Dominance Error Table

| Construct | Compiles on Java 21? | Reason / Fix |
| --- | --- | --- |
| `case Integer i` then `case Number n` on selector `Object` | Yes | Narrower case before broader case |
| `case Number n` then `case Integer i` | No | `Integer` is dominated by `Number` |
| `case Integer i` then `case 42` | No | Constant `42` is already matched by the `Integer` pattern |
| `case 42` then `case Integer i` | Yes | Specific constant before pattern |
| `case String s when s.isBlank()` then `case String s` | Yes | First guard matches only a subset of strings |
| `case String s` then `case String s when s.isBlank()` | No | Second branch is dominated |
| `case String s` then `default` | Yes | `default` covers other types |
| `default` then `case String s` | No | `default` must not precede a case pattern |
| `default` then `case null` | No | `default` must not precede a `null` label |
| `case null` then `default` | Yes | `null` handled separately, `default` handles other values |
| `case null, default` then any other label | No | Combined label must be last |
| `case String s` then `case null, default` | Yes | Final label covers `null` and remaining cases |
| `case Object o` then `default` on selector `Object` | No | Unconditional pattern dominates `default` |
| `default` then `case Object o` on selector `Object` | No | `default` precedes a case pattern |
| `default` then `case 42` on selector `int` | Yes | Backward-compatibility exception, should be avoided |
| Two `default` labels in one switch | No | The `default` label may appear only once |

This table assumes the snippets are placed in a switch with a compatible selector type and enough rules to satisfy exhaustiveness. Each row evaluates the **relationship between labels**, rather than asserting that two cases in isolation always form a complete Java program.

## 12. How to Fix Compiler Errors

### 12.1. `dominated case label`

If you see a dominated case message:

- Identify which earlier case precedes the reported branch.
- Check whether the earlier branch has a broader type pattern, such as `Number` covering `Integer`, `CharSequence` covering `String`, or `Object` covering all objects.
- Check whether a **case constant** is already matched by an earlier type pattern, such as the constant `42` after `Integer`, or an enum constant after the enum's type pattern.
- Fix by placing the narrower case/specific constant first, or removing the redundant branch.

Do not add `default` to fix a dominated case error, because this is an error of **ordering and coverage**.

### 12.2. Misplaced `default`

If `default` precedes `case String s`, `case Point(...)`, or `case null`, move `default` to the **end of the switch**. For `case null, default`, ensure no label follows it. Do not rely on the legacy exception of `default` before constant cases unless you genuinely need to preserve legacy code.

### 12.3. `switch expression does not cover all possible input values`

This is an **exhaustiveness** error, not a dominated case. For an `Object` selector, you typically need `default` or an unconditional pattern. For enums, verify all constants are covered. For sealed interfaces, verify all permitted subtypes are covered.

If you just removed `default` to avoid conflicting with `case Object o`, make sure that catch-all pattern is truly unconditional for the selector type so the switch remains exhaustive.

### 12.4. `NullPointerException` Despite Having `default`

This is a runtime error caused by missing `case null`, not a dominance error. Add `case null`, use `case null, default`, or reject null before entering the switch with `Objects.requireNonNull` if your business logic does not accept null data.

## 13. Exercises and Solutions

### Exercise 1 — Choose the Correct Rule

Suppose `Object value` is already declared:

**A:**

```java
return switch (value) {
    case Number n  -> "NUMBER";
    case Integer i -> "INTEGER";
    default        -> "OTHER";
};
```

**B:**

```java
return switch (value) {
    case Integer i -> "INTEGER";
    case Number n  -> "NUMBER";
    default        -> "OTHER";
};
```

**Solution:** A fails with a dominated case error because `Integer` is a `Number`. B is valid: the specific case precedes the broader case. Both `return switch` snippets are method-body fragments with a `String` return type.

### Exercise 2 — Is `default` First Always Invalid?

Consider:

```java
static String test(int n) {
    return switch (n) {
        default -> "OTHER";
        case 1  -> "ONE";
    };
}
```

**Solution:** This **compiles in Java 21** due to the backward-compatibility exception for `default` before a constant case. `test(1)` returns `ONE`, and `test(2)` returns `OTHER`. However, the clearer style is still to place `case 1` first and `default` last.

### Exercise 3 — Does an Unconditional Pattern Need `default`?

```java
static String test(Object value) {
    return switch (value) {
        case null     -> "NULL";
        case String s -> "STRING";
        case Object o -> "OTHER_OBJECT";
    };
}
```

**Solution:** No `default` is needed. `case Object o` matches every non-`null` object not already matched by `String`; `case null` handles null. Adding `default` after `Object o` would cause an error because `default` is dominated by the unconditional pattern.

### Exercise 4 — Fix Misplaced `case null, default`

```java
// DOES NOT COMPILE:
// return switch (value) {
//     case null, default -> "OTHER";
//     case String s      -> s;
// };
```

**Fixed version:**

```java
return switch (value) {
    case String s       -> s;
    case null, default  -> "OTHER";
};
```

The combined label is the final branch, handling both null and any non-`String` type.

### Exercise 5 — Does a Guard Block `default`?

```java
static String classify(Object value) {
    return switch (value) {
        case String s when s.length() >= 3 -> "LONG";
        default                           -> "OTHER";
    };
}
```

Predict:

- `classify("Java")` → `"LONG"`.
- `classify("Go")` → `"OTHER"`.
- `classify(100)` → `"OTHER"`.
- `classify(null)` → throws `NullPointerException` because there is no `case null`.

The guard only covers strings that satisfy the condition; therefore, `default` is not dominated and is still required for the remaining values.

### Exercise 6 — Enum Constant or Type Pattern First?

Suppose you have `enum State { CREATED, DONE, FAILED }` and `Object value`. You want `State.FAILED` to return `"ALERT"`, the remaining `State` constants to return `"STATE"`, and other objects to return `"OTHER"`.

**Solution:**

```java
static String classify(Object value) {
    return switch (value) {
        case State.FAILED -> "ALERT";
        case State state  -> "STATE";
        default           -> "OTHER";
    };
}
```

If you swap the first two cases, `State.FAILED` will be dominated. If you want to handle `null` without throwing an NPE, add `case null`.

## 14. Checklist When Reviewing `default` and Dominance

When reading a Java 21 pattern switch, check in order:

1. **Static type of the selector:** `Object`, interface, enum, sealed class, or another type? Dominance and exhaustiveness rely on the type seen by the compiler.
2. **Is each case a constant or a pattern?** `case State.FAILED` is an enum constant; `case State s` is a type pattern; `default` is not a pattern.
3. **Coverage relationship:** does any general case precede a specialized case? Is any constant covered by an earlier pattern?
4. **Guards:** `case T t when condition` may match fewer values than `case T t`; place guarded/specialized cases before the general branch.
5. **Is there an unconditional pattern?** If a pattern already covers the selector type, such as `case Object o` for an `Object` selector, do not add a redundant `default`.
6. **Placement of `default`:** place it last, especially never before a case pattern or `case null`. If you see `default` before constant cases, recognize it as a legacy exception rather than a style to adopt broadly.
7. **If using `case null, default`:** it must be the last label, with no other labels after it.
8. **Exhaustiveness:** does the switch expression/enhanced statement cover all possibilities for the selector type? Does it have `default`, an unconditional pattern, all enum constants, or all sealed subtypes?
9. **Null:** `default` alone does not handle `null`; if you need control over it, use `case null` or `case null, default`.
10. **Control flow and pattern variables:** a pattern case only declares its variable for the matching branch; do not use that variable in `default` or unrelated branches.

## 15. Conclusion

In Java 21, **dominance** prevents later `case` branches from becoming unselectable because an earlier branch already covers them. `default` is a fallback branch, but it **does not override dominance rules**.

- Place **specialized cases, specific constants, and guarded cases** before the corresponding general case.
- If there is an **unconditional pattern** for the selector type, **do not also use `default`**: placing it before or after creates a conflict under Java 21 rules.
- **`default` should be placed last**. The specification has a backward-compatibility exception for `default` before **constant cases**, but **forbids** it before pattern cases and `case null`.
- `case null, default` is a combined label covering null and the fallback branch, and **must be the last label**.
- **Exhaustiveness** answers “are all cases covered?”, whereas **dominance** answers “is any branch shadowed?”. Both conditions must be checked separately.
- `default` does not handle `null` on its own, does not declare a pattern variable, and does not guarantee that the logic inside the branch will not throw an exception.

**Rule of thumb:** When you need a default branch in a pattern switch, handle cases **narrower first, broader later**, and place `default` last **if no unconditional pattern already serves as the catch-all**.

## Official References

- [Java SE 21 Language Specification §14.11.1 — Switch Blocks, Dominance, and Default](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1)
- [Java SE 21 Language Specification §14.11.1.1 — Exhaustive Switch Blocks](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1.1)
- [Java SE 21 Language Specification §14.11.1.2 — Determining Which Switch Label Applies](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1.2)
- [Java SE 21 Language Specification §14.30.3 — Properties of Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30.3)
- [OpenJDK JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
