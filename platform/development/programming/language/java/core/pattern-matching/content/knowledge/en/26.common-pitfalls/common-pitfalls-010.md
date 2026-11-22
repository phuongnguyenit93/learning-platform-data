# Confusing Pattern Switch with Legacy Switch in Java 21: Distinguishing Syntax, Scope, and Behavior

## 1. Problem and Objectives

Many mistakes when learning **Java Core Pattern Matching** come from calling every new `switch` syntax a "pattern switch", or conversely applying assumptions from the classic `switch` to a `switch` with type/record patterns. In reality, modern Java has **three independent conceptual axes** that must be distinguished:

1. **Structural form:** a `switch statement` only controls statement flow; a `switch expression` is an expression that produces a **value**.
2. **Label form:** constant labels such as `case 1`, `case "go"`, `case MONDAY` differ from pattern labels such as `case String s` or `case Point(var x, var y)`.
3. **Branch body form:** the classic syntax uses `case ...:` and can *fall through*; the rule syntax `case ... ->` does not automatically fall through to the next rule.

These three axes are **not synonymous**. For example, a `switch` with `case 1 ->` is **not pattern matching yet**. A `switch expression` can also use only constants without needing patterns. Conversely, a `switch statement` in Java 21 can still use `case String s:`, even though learners often find `->` more convenient and safer.

This lesson focuses on how to **identify and fix common misconceptions**, along with a Java 21 program to verify them in practice.

**Key version milestones:**

- Traditional `switch` with constants and `case:` has existed since the early versions of Java; `enum` support was added in Java 5 and `String` in Java 7.
- `switch expressions` and the `case ... ->` rule form were standardized in Java 14 (JEP 361).
- `instanceof` pattern matching became a standard feature in Java 16 (JEP 394), which **does not mean** pattern matching in `switch` was already standard in Java 16.
- **Pattern matching for `switch`** (JEP 441) and **record patterns** (JEP 440) have been standard since **Java 21**.

For the `case Type variable`, `case Record(...)`, or `when` examples in this lesson, use JDK 21 or later and compile with `javac --release 21`; no preview flags are needed.

## 2. Quick Comparison Table: Legacy, New, and Pattern

| Criterion | Classic `switch` statement | Rule-form `switch` statement | `switch` with patterns in Java 21 |
| --- | --- | --- | --- |
| Purpose | Select and execute statements | Select and execute statements | Select branch by type/structure; can be a statement or expression |
| Label examples | `case 0:`, `case "go":` | `case 0 ->`, `case "go" ->` | `case String s ->`, `case Point(var x,var y) ->` |
| Variables bound from value | No, with constant labels | No, if using only constant labels | Yes, e.g., `s`, `x`, `y` |
| Fall-through | Can occur if not exiting the branch | No between switch rules | Depends on `:`/`->`; patterns also have flow restrictions |
| `when` | Not a guard for traditional constant labels | Constant rules do not have guards on their own | Used after a pattern label: `case String s when ...` |
| `null` | `switch` on a `null` reference usually throws `NullPointerException` | Does not handle `null` automatically if an appropriate case is missing | Can use `case null`; `default` does not replace `null` |
| Coverage checking | Classic switch statement may omit cases | Depends on enhanced/traditional switch | Enhanced switch must be exhaustive; switch expression is always exhaustive |
| Minimum version for examples | Depends on selector (`String` from Java 7) | Java 14 when using rules | Java 21 for standard patterns |

Do not just look at the `->` symbol and conclude "this is a pattern switch". **Pattern matching is in the case label itself**, not in the arrow.

### 2.1. A `switch` Can Be Both an Expression and Use Constant Labels

Java 14+ example:

```java
static String label(int code) {
    return switch (code) {
        case 0 -> "zero";
        case 1, 2 -> "small";
        default -> "other";
    };
}
```

The snippet above returns a `String` from a switch expression, uses `->` rules, but **has no pattern variable**. This is not an example of pattern matching.

### 2.2. A `switch` Can Be a Statement and Still Use Patterns

Java 21 allows:

```java
static String colonPattern(Object value) {
    switch (value) {
        case String s: return "pattern:" + s;
        case Integer i: return "number:" + i;
        case null: return "null";
        default: return "other";
    }
}
```

This is a **switch statement** with pattern labels and the `:` character. Each branch in the example exits with `return`; there is no fall-through. Thus, claiming "a pattern switch must be written with `->`" is incorrect.

## 3. Classic Switch: Constants, `:`, and Fall-Through

In the traditional form, the selector is typically a supported primitive type (such as `int` and smaller integral types), their corresponding wrappers, `String`, or `enum`. Cases compare against **constants** or enum constants, rather than creating variables based on runtime type.

```java
static String classic(int code) {
    String result;
    switch (code) {
        case 0:
            result = "zero";
            break;
        case 1:
        case 2:
            result = "small";
            break;
        default:
            result = "other";
    }
    return result;
}
```

With `code = 2`, the program starts at `case 2:`, assigns `"small"`, and then `break` exits the switch statement.

**Fall-through** is the easiest thing to misunderstand when switching to the newer style. With `:`, if a branch does not have `break`, `return`, `throw`, or an appropriate exit statement, execution can continue into **the statements of the next branch**:

```java
static String fallThrough(int value) {
    StringBuilder result = new StringBuilder();
    switch (value) {
        case 1:
            result.append("one/");
        case 2:
            result.append("two/");
            break;
        default:
            result.append("other/");
    }
    return result.toString();
}
```

Result: `fallThrough(1)` returns `"one/two/"` while `fallThrough(2)` returns `"two/"`. This is **intentional** fall-through, though it is also often a bug caused by forgetting `break`. When reviewing, you need to understand which condition starts at which branch and which statement actually stops the flow.

### 3.1. `String` Labels in Legacy Switch Are Not Type Patterns

```java
static String classicWord(String value) {
    switch (value) {
        case "go": return "go!";
        case "stop": return "stop!";
        default: return "unknown";
    }
}
```

`case "go"` compares against a **constant string value**. It has no variable `s` and does not match any other string. In contrast, Java 21's `case String s` is a **type pattern**, which can match any non-`null` string and bind `s`.

In this classic String switch, `classicWord(null)` throws `NullPointerException` before `default` is selected.

## 4. The `->` Arrow Does Not Automatically Turn a Switch into Pattern Matching

Since Java 14, the rule form helps avoid fall-through between cases:

```java
static String arrowStatement(String command) {
    String result;
    switch (command) {
        case "START" -> result = "started";
        case "STOP" -> result = "stopped";
        default -> result = "other command";
    }
    return result;
}
```

Here:

- It is still a **statement**; `result` is assigned and then returned on the next line.
- All `case` labels are string constants and do not bind any pattern variable.
- No `break` is needed to prevent code from running into the next rule.
- The `->` syntax does not guarantee `null` input is handled; with `switch(String)` as above, `null` still throws `NullPointerException`.

**Difference from a switch expression:**

```java
static String expressionExample(String command) {
    return switch (command) {
        case "START" -> "started";
        case "STOP" -> "stopped";
        default -> "other command";
    };
}
```

This is an **expression**: the entire `switch(...) { ... }` produces a `String` value for `return`. Notice the `;` after `}` and the requirement for branches to provide an appropriate value.

Both snippets use constants and have no pattern matching. You can convert between them as long as you preserve exceptions, return type, and branch precedence.

## 5. Java 21 Pattern Switch: `case Type variable` and `case Record(...)`

Pattern matching in `switch` extends `case` labels into **value-testing patterns**. Example:

```java
record Point(int x, int y) {}

static String kind(Object value) {
    return switch (value) {
        case String s when s.isBlank() -> "blank text";
        case String s -> "text:" + s.strip();
        case Point(var x, var y) when x == y -> "diagonal=" + x;
        case Point(var x, var y) -> "point=" + x + "," + y;
        case Integer n -> "integer=" + n;
        case Number n -> "number=" + n;
        case null -> "null";
        default -> "other";
    };
}
```

The lines with `case String s`, `case Integer n`, `case Number n` are **type patterns**; they check the runtime type and create pattern variables. `Point(var x, var y)` is a **record pattern**, which both checks `Point` and extracts its components via accessors.

With an `Object` selector, this approach can eliminate long `if (value instanceof ...) { ... } else if (...)` chains. However, that does not mean a pattern switch "can accept any selector type that the old switch couldn't": selector type rules were expanded for enhanced switch and still depend on the language version. On **Java 21**, the patterns in the example are valid.

### 5.1. `case String.class` Is Not Equivalent to `case String s`

`String.class` is a value of type `Class<String>`, **not** a pattern checking whether `value` is a `String`. Use the `case String s` label to match objects, not `case String.class` under the assumption of "comparing classes".

If you genuinely want to classify `Class<?>` objects (instead of ordinary objects), that is a different problem.

### 5.2. Variable Names Can Only Be Used Where the Pattern Matches

In the branch:

```java
case String s -> "text:" + s.strip();
```

the variable `s` has valid scope within that branch body. You cannot take `s` from this branch and use it directly in `case Integer n` or outside the entire `switch`. When using a guard, the pattern variable is also in scope in the corresponding `when` expression.

## 6. The `when` Guard Differs from a Nested `if` Condition in a Branch

To handle blank strings before other strings, write:

```java
return switch (value) {
    case String s when s.isBlank() -> "blank";
    case String s -> "nonblank";
    case null -> "null";
    default -> "other";
};
```

Selection process:

1. `case String s` attempts to match the type.
2. Only if that succeeds is `when s.isBlank()` evaluated.
3. If the guard is true, `"blank"` is produced.
4. If the guard is false, evaluation continues to subsequent cases. The unguarded `case String s` will match the remaining strings.

**The Java 21 syntax is `when`**. Do not mix it into the label using `case String s && s.isBlank()` as in some old preview articles, and do not write `value instanceof String s when s.isBlank()`. With `instanceof`, use `value instanceof String s && s.isBlank()`.

### 6.1. Why Not Put the General Pattern First?

The following snippet is **intentionally wrong**:

```java
return switch (value) {
    case String s -> "any string";
    case String s when s.isBlank() -> "blank"; // dominated
    default -> "other";
};
```

The unguarded `String s` branch already accepts all non-null strings. The subsequent branch can never be selected, so the compiler reports a **dominance error**.

In a pattern switch, **case order is part of the logic**, especially when a value can match multiple patterns or multiple guards.

### 6.2. Guards Are Not Arbitrary Business-Rule Solvers

The compiler does not prove arbitrary predicates in `when` to be true or false. A `when true` has special dominance rules, behaving like an unguarded branch, whereas `when s.length() >= 0` is not automatically inferred by the compiler to mean "matches every String" for dominance purposes. Actual branch selection still evaluates guards from top to bottom.

Best for readability: place **specialized guarded branches** before **unguarded branches of the same type**, and then supertypes if any.

## 7. Dominance: An Error Rarely Seen This Way in Legacy Switch

A `String` value is also a `CharSequence`. If you write:

```java
// INTENTIONALLY WRONG: does not compile in Java 21.
return switch (value) {
    case CharSequence seq -> "sequence";
    case String text -> "string"; // dominated by the preceding branch
    default -> "other";
};
```

the compiler reports that the `String` label is **dominated**. Fix it by reordering:

```java
return switch (value) {
    case String text -> "string";
    case CharSequence seq -> "sequence";
    default -> "other";
};
```

This is not merely a readability preference. The language enforces avoiding branches that are guaranteed never to have a chance of being selected because a preceding label covers them.

Common rules:

- **Subtype before supertype**: `Integer` before `Number`, `String` before `CharSequence`.
- **Guarded case before unguarded case of the same type**.
- **Specific constant label before an unguarded pattern that covers that value**, for example in a switch on `Integer`, `case 0` before `case Integer i`.
- **Narrow record pattern before a broader covering pattern**, for example `Holder(Point(var x, var y))` before `Holder(var p)` if both apply.
- Do not add `default` alongside an **unconditional pattern** covering the selector, such as `case Object o` in `switch(Object)`, in a way that creates a conflict; the compiler has specific rules for that case.

### Dominance and Fall-Through Are Two Different Concepts

Fall-through is **statement execution** continuing after a `case:` label without exiting the block. Dominance is a compile-time check of **label coverage**. Adding `break` does not fix a dominated case; switching to `->` also does not fix `CharSequence` dominating `String`.

## 8. Handling `null`: A Common Misconception Causing Runtime Errors

When converting an `if/else if` chain to a pattern switch, it is very easy to miss `null`.

With `instanceof`:

```java
if (value instanceof String s) {
    return "text:" + s;
}
return "other"; // value == null also reaches here
```

If refactored to:

```java
return switch (value) {
    case String s -> "text:" + s;
    default -> "other";
};
```

then **`value == null` does not automatically fall into `default`**; the switch can throw `NullPointerException`. To preserve the original fallback, add:

```java
return switch (value) {
    case String s -> "text:" + s;
    case null -> "other";
    default -> "other";
};
```

Java 21 also supports the combined form:

```java
return switch (value) {
    case String s -> "text:" + s;
    case null, default -> "other";
};
```

This combined form is suitable when handling `null` and unmatched types with **the same result**.

### 8.1. Outer `null` and `null` Inside a Record Are Not the Same

`case Point(var x, var y)` does not match a `null` selector. However, a **non-null record object** whose reference component is `null` can still match a pattern using `var`:

```java
record Started(String id) implements Event {}
// Event is the sealed interface declared in the full example.

// new Started(null) still matches:
case Started(var id) -> "started without id";
```

In this example, `var id` can bind `null`. If replaced with a nested type pattern `Started(String id)`, a `null` component does not match the nested `String` pattern. Do not confuse the `null` rules for the outer selector with record component values.

### 8.2. `default` Does Not Mean "If Null"

In both the old and new forms, `default` is not a special `else` expression for `null`. For switches on references that may be `null`, write a dedicated `null` test and decide whether you need `case null` or want to keep the exception.

## 9. Switch Statement vs. Switch Expression: Different Exhaustiveness Rules

The two forms look similar but have different contracts:

A **classic switch statement** can handle only some values:

```java
static void process(int code) {
    switch (code) {
        case 1:
            System.out.println("one");
            break;
    }
    // If code is not 1, the statement does nothing.
}
```

The snippet above is valid because a traditional statement is not required to list every case.

A **switch expression** must be **exhaustive**: regardless of which valid case the selector falls into according to language analysis, the expression must produce a result or complete abruptly. For example, omitting `default` when the selector is `Object`:

```java
// INTENTIONALLY WRONG: non-exhaustive switch expression.
return switch (value) {
    case String s -> s;
};
```

The compiler reports `the switch expression does not cover all possible input values`.

An **enhanced switch statement** (such as a switch using patterns) in Java 21 also has exhaustiveness requirements. Do not assume from the word "statement" that you can omit all remaining branches as in a classic switch:

```java
// INTENTIONALLY WRONG in Java 21.
switch (value) {
    case String s -> System.out.println(s);
}
// Selector Object has many other types: missing coverage.
```

The example above is not exhaustive and is rejected by the compiler. You can add `default` or cover all subtypes according to JLS rules.

### 9.1. A Sealed Hierarchy Can Be Exhaustive Without `default`

With a restricted set of subtypes:

```java
sealed interface Event permits Started, Stopped {}
record Started(String id) implements Event {}
record Stopped(int code) implements Event {}

static String eventKind(Event event) {
    return switch (event) {
        case Started(var id) when id != null && !id.isBlank() ->
                "started:" + id;
        case Started(var id) -> "started without id";
        case Stopped(var code) -> "stopped:" + code;
        case null -> "null event";
    };
}
```

The compiler knows `Event` only has its permitted subtypes. The unguarded `Started(var id)` branch covers any `Started` skipped by the first guard, while the `Stopped` branch handles the other subtype; no `default` is needed. `case null` is an **explicit null-handling** choice, not a subtype.

This differs from `switch(Object)`: an `Object` can be many unlisted types, so `default` or a construct that truly covers the entire valid domain is normally required.

### 9.2. Dominance and Exhaustiveness Are Independent

- **Dominance:** is a later case completely covered by a preceding case?
- **Exhaustiveness:** does the entire switch cover all cases for the selector's domain?

You can write a switch that is **exhaustive yet has a dominated case** (fails to compile), or has no dominated case yet **lacks coverage** (also fails to compile for expressions/enhanced switches). Both errors require fixing with different checks.

## 10. `return`, `break`, and `yield` Do Not Have the Same Role

In a classic switch statement:

- `break;` terminates the switch statement (but does not exit the method).
- `return value;` exits the method; can be used directly in a branch if the return type matches.
- `throw` throws an exception.

In a **switch expression**, the value of each expression-form rule is produced directly:

```java
return switch (value) {
    case String s -> s.trim();
    case null -> "null";
    default -> "other";
};
```

If a rule uses a block, supplying a value to the switch expression requires **`yield`**, not `return`:

```java
static String computed(Object value) {
    return switch (value) {
        case Point(var x, var y) -> {
            int sum = x + y;
            yield "sum=" + sum;
        }
        case String s -> "len=" + s.length();
        case null -> "null";
        default -> "other";
    };
}
```

With `new Point(2, 3)`, the result is `"sum=5"`.

**Intentionally wrong** snippet:

```java
// ERROR: cannot return from inside a switch expression.
return switch (value) {
    case String s -> { return s; }
    default -> "other";
};
```

Java reports an error equivalent to `attempt to return out of a switch expression`. Fix it with `yield s;` inside the block, or write `case String s -> s;` directly.

### 10.1. Switch Expressions Can Still Use `:`

Another misconception: "a switch expression must use `->`". Java allows the colon form with `yield`:

```java
static int colonExpression(int x) {
    return switch (x) {
        case 0: yield 10;
        default: yield 20;
    };
}
```

This is a valid switch expression in Java 21 without patterns. However, to avoid confusion around fall-through and control flow, the `->` rule form is usually clearer for new code. Within a single switch block, do not arbitrarily mix `:` and `->` labels of the two different forms.

## 11. Complete Java 21 Program: Comparing Actual Behavior

Create the file **`LegacyAndPatternSwitchDemo.java`**. The program includes classic switch, fall-through, rule-form switch statement, type/record patterns, `when`, sealed hierarchy, `yield`, and a pattern switch statement using `:`. It demonstrates differences **that cannot be inferred merely by looking at the arrow**.

```java
import java.util.function.Supplier;

public class LegacyAndPatternSwitchDemo {
    record Point(int x, int y) {}
    sealed interface Event permits Started, Stopped {}
    record Started(String id) implements Event {}
    record Stopped(int code) implements Event {}

    static String classic(int code) {
        String result;
        switch (code) {
            case 0:
                result = "zero";
                break;
            case 1:
            case 2:
                result = "small";
                break;
            default:
                result = "other";
        }
        return result;
    }

    static String fallThrough(int value) {
        StringBuilder result = new StringBuilder();
        switch (value) {
            case 1:
                result.append("one/");
            case 2:
                result.append("two/");
                break;
            default:
                result.append("other/");
        }
        return result.toString();
    }

    static String classicWord(String value) {
        switch (value) {
            case "go": return "go!";
            case "stop": return "stop!";
            default: return "unknown";
        }
    }

    static String arrowStatement(String command) {
        String result;
        switch (command) {
            case "START" -> result = "started";
            case "STOP" -> result = "stopped";
            default -> result = "other command";
        }
        return result;
    }

    static String kind(Object value) {
        return switch (value) {
            case String s when s.isBlank() -> "blank text";
            case String s -> "text:" + s.strip();
            case Point(var x, var y) when x == y -> "diagonal=" + x;
            case Point(var x, var y) -> "point=" + x + "," + y;
            case Integer n -> "integer=" + n;
            case Number n -> "number=" + n;
            case null -> "null";
            default -> "other";
        };
    }

    static String eventKind(Event event) {
        return switch (event) {
            case Started(var id) when id != null && !id.isBlank() ->
                    "started:" + id;
            case Started(var id) -> "started without id";
            case Stopped(var code) -> "stopped:" + code;
            case null -> "null event";
        };
    }

    static String computed(Object value) {
        return switch (value) {
            case Point(var x, var y) -> {
                int sum = x + y;
                yield "sum=" + sum;
            }
            case String s -> "len=" + s.length();
            case null -> "null";
            default -> "other";
        };
    }

    static String colonPattern(Object value) {
        switch (value) {
            case String s: return "pattern:" + s;
            case Integer i: return "number:" + i;
            case null: return "null";
            default: return "other";
        }
    }

    static String safe(Supplier<String> action) {
        try {
            return action.get();
        } catch (RuntimeException error) {
            return error.getClass().getSimpleName();
        }
    }

    public static void main(String[] args) {
        System.out.println("legacy 0: " + classic(0));
        System.out.println("legacy 2: " + classic(2));
        System.out.println("legacy 7: " + classic(7));
        System.out.println("fallthrough 1: " + fallThrough(1));
        System.out.println("fallthrough 2: " + fallThrough(2));
        System.out.println("old String: " + classicWord("go"));
        System.out.println("old null: " + safe(() -> classicWord(null)));
        System.out.println("arrow statement: " + arrowStatement("START"));
        System.out.println("type string: " + kind(" Java "));
        System.out.println("type blank: " + kind("   "));
        System.out.println("record diag: " + kind(new Point(3, 3)));
        System.out.println("record off: " + kind(new Point(2, 3)));
        System.out.println("int: " + kind(9));
        System.out.println("double: " + kind(2.5));
        System.out.println("null: " + kind(null));
        System.out.println("other: " + kind(new Object()));
        System.out.println("sealed: " + eventKind(new Started("A1")));
        System.out.println("sealed null component: " + eventKind(new Started(null)));
        System.out.println("sealed stopped: " + eventKind(new Stopped(7)));
        System.out.println("sealed null selector: " + eventKind(null));
        System.out.println("yield: " + computed(new Point(2, 3)));
        System.out.println("colon pattern: " + colonPattern("hi"));
    }
}
```

**Compile/run:** use JDK 21+ in the directory containing the file.

```bash
javac --release 21 LegacyAndPatternSwitchDemo.java
java LegacyAndPatternSwitchDemo
```

**Verified stdout output:**

```text
legacy 0: zero
legacy 2: small
legacy 7: other
fallthrough 1: one/two/
fallthrough 2: two/
old String: go!
old null: NullPointerException
arrow statement: started
type string: text:Java
type blank: blank text
record diag: diagonal=3
record off: point=2,3
int: integer=9
double: number=2.5
null: null
other: other
sealed: started:A1
sealed null component: started without id
sealed stopped: stopped:7
sealed null selector: null event
yield: sum=5
colon pattern: pattern:hi
```

### 11.1. Analysis of Key Results to Remember

- **`classic`:** `case 1:` and `case 2:` share code; `break` prevents unintended fall-through.
- **`fallThrough`:** input `1` runs through both `one/` and `two/` because there is no `break` in the first branch.
- **`classicWord(null)`:** string constant labels + `default` do not prevent `NullPointerException`; `safe` only catches the exception so the program continues running.
- **`arrowStatement`:** has `->` but the cases are still only string constants, not patterns.
- **`kind`:** guarded `String` comes before general `String`, `Integer` comes before `Number`; record `Point` demonstrates component extraction.
- **`kind(null)`:** the `case null` branch runs, not `default`.
- **`eventKind`:** switch on a sealed type is exhaustive without `default`; record `Started(null)` matches `Started(var id)` and falls back according to the guard.
- **`computed`:** a block in a switch expression uses `yield` to produce a value.
- **`colonPattern`:** a type pattern with `:` is still valid when each branch's flow exits properly.

The output is sufficient to distinguish the three axes: statement/expression, constant/pattern labels, and colon/arrow. A large program may combine multiple forms, but should use a consistent and easy-to-review structure.

## 12. Common Compilation Errors and How to Fix Them

The snippets below **intentionally do not compile**; do not merge them into the runnable program file in Section 11.

### 12.1. Using Java 17 for Java 21 Pattern Switch

```java
// INTENTIONALLY WRONG when compiled with javac --release 17.
return switch (value) {
    case String s -> s;
    default -> "other";
};
```

The compiler reports `patterns in switch statements are not supported in -source 17` (diagnostics may vary across JDKs). This **does not contradict** Java 17 having `instanceof String s`: `instanceof` patterns and `switch` patterns had different standardization timelines.

**Fix:** upgrade the source/release target to Java 21 and ensure the target runtime is compatible, or keep `if (value instanceof String s)` if the project mandates Java 17.

### 12.2. Broad Pattern Before Narrow Pattern

```java
// INTENTIONALLY WRONG.
return switch (value) {
    case CharSequence seq -> "wide";
    case String text -> "narrow";
    default -> "other";
};
```

The compiler reports `this case label is dominated by a preceding case label`. **Fix:** place `String` before `CharSequence`.

### 12.3. Unguarded Pattern Shadowing a Guarded Branch

```java
// INTENTIONALLY WRONG.
return switch (value) {
    case String text -> "all";
    case String text when text.isBlank() -> "blank";
    default -> "other";
};
```

The later branch is dominated. **Fix:** place the `when` branch above and the general branch below.

### 12.4. Non-Exhaustive Enhanced Switch

```java
// INTENTIONALLY WRONG: Object has many other types besides String.
return switch (value) {
    case String s -> s;
};
```

The compiler reports that the switch expression does not cover all possible selector values. An enhanced switch **statement** with patterns that omits other cases can also be rejected:

```java
// INTENTIONALLY WRONG: non-exhaustive enhanced switch statement.
switch (value) {
    case String s -> System.out.println(s);
}
```

**Fix:** add `default` or cover all cases according to the selector type (e.g., a sealed hierarchy). When `null` behavior must be preserved, consider `case null` separately.

### 12.5. Adding `default` Alongside an Unconditional Pattern

```java
// INTENTIONALLY WRONG:
return switch (value) {
    case Object obj -> "all objects";
    default -> "other";
};
```

Java 21 reports an error equivalent to `switch has both an unconditional pattern and a default label`. **Fix:** choose an appropriate general structure rather than declaring two covering labels side by side in a forbidden way.

### 12.6. `return` Instead of `yield` Inside a Switch Expression

```java
// INTENTIONALLY WRONG:
return switch (value) {
    case String text -> { return text; }
    default -> "other";
};
```

**Fix:** `case String text -> text;` or inside a block use `yield text;`. Do not confuse `return` from a method with `yield` from a switch expression.

### 12.7. Treating `case null` as a Normal Constant Label of Legacy Switch

In Java 21, `case null` is the explicit `null`-selector handling mechanism of enhanced switch; do not assume classic `String` switch since Java 7 has always supported `case null`. When reading code across multiple source levels, check the target Java level rather than relying on the JDK installed on your machine.

### 12.8. Assuming Switching to `->` Fixes Every Bug

`->` eliminates fall-through between rules, but **does not** solve dominance, missing `null` branches, wrong guards, exceptions in accessors, or the risk of changing contracts when refactoring legacy logic. Evaluate each class of issue separately.

## 13. Testing Matrix When Migrating Legacy Switch to Pattern Switch

If the goal is refactoring rather than changing business logic, verify **behavior preservation**.

| Input / Case Group | Check in Legacy Switch | Check in New Switch |
| --- | --- | --- |
| Declared constant | Selects corresponding case | Does it still match the same value / return the same result? |
| Undeclared constant | `default` or does nothing | Did it change to a different return/exception? |
| Intentional fall-through | One input runs multiple `case:` blocks | Did the `->` form lose an old side effect? |
| Non-null String | Matches exact string literal | Does a type pattern accidentally match **every** String? |
| `null` | May throw NPE with legacy switch(String) | Did `case null` turn an exception into an unintended fallback? |
| Subtype/implements interface | Old if/else branches prioritized by order | Is the narrow type pattern kept before the broad pattern? |
| Normal record | Cast + accessor | Does the record pattern produce equivalent results and side effects? |
| `null` record component | How did old logic check the accessor and null? | Does nested pattern/`var` change behavior? |
| Guard `true`/`false` | Which `if`/`else` condition runs? | Are the `when` branch and fallback in the right order? |
| Switch expression | Does every path have a valid return/yield? | Are all branches complete and result types valid? |
| Sealed hierarchy | Actual set of subtypes | Are all permitted subtypes handled when a new subtype is added? |

For code with side effects (logging, mutating objects, I/O calls, or payments), you must also check **execution order and invocation count**, not just compare result strings. A more concise `switch` expression does not automatically prove it has the same semantics as multiple nested `if`/`switch` blocks.

### 13.1. Recommended Migration Process

1. **Lock down the Java target:** determine which source/release the build uses and how compatible the production runtime is.
2. **Capture a baseline:** record inputs, outputs, exceptions, and important fall-through behavior.
3. **Classify the old structure:** constant labels or runtime type checks via `if/instanceof`? Statement or intended as an expression?
4. **Choose the new form deliberately:** if you only want to remove fall-through, use `->` rules; if you want to check types/records, use pattern labels.
5. **Order branches:** subtype before supertype; guarded case before unguarded case of the same type; specific constants before general patterns if applicable.
6. **Preserve null behavior:** explicitly decide on `case null`, keeping NPE, or an approved fallback per contract.
7. **Check exhaustiveness:** an `Object` selector differs from a sealed type; expressions and enhanced statements must both follow coverage rules.
8. **Compare semantics:** regression tests, boundary tests, exception tests, and side-effect tests.
9. **Review diff and CI:** ensure unapproved business logic changes are not mixed into syntax refactoring.

## 14. Code Review Checklist

- [ ] Clearly distinguished **statement/expression**, **constant/pattern labels**, and **colon/arrow**.
- [ ] Build uses a Java version supporting the actual syntax; `--release 21` for standard pattern `switch`/record patterns.
- [ ] `case "value"` and `case String s` are not confused: one compares a constant, the other matches a type.
- [ ] `case ->` is not equated with pattern matching.
- [ ] Intentional fall-through is not lost when converting `case:` to `->`.
- [ ] For String or reference switches, `null` produces the result required by the contract; `default` is not assumed to handle `null`.
- [ ] Guards use `when` syntax and pattern variables within valid scope.
- [ ] No dominated cases: narrow types/specific guards precede broad types/unguarded cases.
- [ ] Switch expressions return a value in all branches and use `yield` properly when using blocks.
- [ ] Enhanced switch statements and switch expressions satisfy exhaustiveness; sealed hierarchies are covered by subtype.
- [ ] Colon and arrow are not mixed inconsistently within the same switch block; pattern cases using `:` do not fall through into branches with bound variables against the rules.
- [ ] Tested `null` selector, `null` components, subtypes, and boundary values.
- [ ] Ran regression/CI on the reviewed commit; did not silently alter side-effect/exception ordering.
- [ ] If there is an intentional behavior change, it is clearly documented and has dedicated tests.

**Completion criteria:** A reader looking at a `switch` can immediately tell whether it is a statement or an expression, whether cases check constants or patterns, which case takes precedence, how each path produces a result or exits, and how `null` is handled. The code compiles against the project's target Java version and tests prove the critical scenarios.

## 15. Self-Check Questions

**1. Is `case 1 -> "one"` pattern matching?**  
No. This is a rule with constant label `1`. The `->` symbol is a branch body form, not an indicator of a pattern.

**2. Is `return switch(code) { case 0 -> "zero"; default -> "other"; };` a switch expression even without patterns?**  
Yes. A switch expression produces a value; it is independent of whether there is a pattern variable or not.

**3. Can `case String s:` be used in a Java 21 switch statement?**  
Yes, as long as flow and branch rules are followed. Patterns do not strictly require the `->` symbol.

**4. Why is `case String s` not the same as `case "go"`?**  
`case String s` matches qualifying String objects and binds `s`; `case "go"` only compares against one specific string value.

**5. When can an old-style switch statement fall through?**  
When a `case:` branch does not exit via `break`, `return`, `throw`, or equivalent control flow before continuing to subsequent statements.

**6. Why does `case CharSequence cs` before `case String s` fail in Java 21?**  
Because every String is a CharSequence; placing the broad branch first causes the String branch to be dominated.

**7. Does `default` automatically handle a `null` selector in a pattern switch?**  
No. You usually need `case null` or intentionally accept `NullPointerException`, depending on the contract.

**8. In `case Point(var x,var y) when x==y`, when is `when` evaluated?**  
After the record pattern has matched and the variables `x`, `y` have been bound.

**9. Why is using `return` inside a switch expression block wrong?**  
A switch expression needs its own value: blocks use `yield`; `return` from a method is not allowed to exit a switch expression that way.

**10. Is a switch statement with patterns that omits `default` always valid because a statement does not need a result?**  
No. Enhanced switch statements have exhaustiveness requirements; a sealed hierarchy can satisfy this by covering all subtypes without `default`.

**11. Can `case null, default -> ...` be used in Java 21 when you want to handle both groups the same way?**  
Yes. This is valid syntax for a shared branch covering a `null` selector and all remaining values.

**12. If you convert a classic switch to a pattern switch and the output tests still pass, is all behavior guaranteed to be preserved?**  
Not yet. You must also consider exceptions, fall-through with side effects, accessor/guard side effects, `null` cases, subtypes, and untested inputs.

## References

- [JEP 361 — Switch Expressions (Java 14)](https://openjdk.org/jeps/361)
- [JEP 394 — Pattern Matching for instanceof (Java 16)](https://openjdk.org/jeps/394)
- [JEP 440 — Record Patterns (Java 21)](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch (Java 21)](https://openjdk.org/jeps/441)
- [Oracle Java SE 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [JLS Java SE 21 §14.11 — The switch Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
- [JLS Java SE 21 §15.28 — switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28)
