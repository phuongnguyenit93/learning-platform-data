# Arrow rules and colon groups in switch patterns (Java 21)

In Java 21, a `switch` has two ways to organize its branches:

- **Switch rule**: `case ... ->`, where each branch executes the right-hand side of the arrow and **does not fall through** to the next branch.
- **Switch labeled statement group**: `case ... :`, where labels are attached to a group of statements; in a `switch statement`, control flow **can continue into the following group** if it does not terminate with `break`, `return`, `throw`, or an appropriate exit mechanism.

Both forms work with **pattern matching for switch**, a standard feature in Java 21 (JEP 441). They also apply to both `switch statements` (statements that perform actions) and `switch expressions` (expressions that produce a value). However, **how a branch terminates** differs between statements and expressions, as well as between `->` and `:`.

A crucial point with patterns is that a **pattern variable only exists on paths where the pattern has matched**. Java 21 imposes additional restrictions on falling through *into* a `case` label that declares a pattern variable to prevent using an uninitialized variable.

## 1. Recognizing the two label styles

### Arrow rule: `case L ->`

```java
static String describe(Object value) {
    return switch (value) {
        case null -> "missing";
        case String text -> "text: " + text;
        case Integer number -> "integer: " + number;
        default -> "other";
    };
}
```

This is an **illustrative method**, placed inside a Java class. When `value` matches `String text`, the branch result is `"text: " + text`. After that branch, the `switch` completes; it does not continue into `case Integer number` or `default`.

The `->` syntax clearly expresses “whichever label matches, execute that branch”. For a `switch expression`, the expression after `->` directly produces the result value.

### Colon group: `case L:`

```java
static String describeWithColon(Object value) {
    return switch (value) {
        case null:
            yield "missing";
        case String text:
            yield "text: " + text;
        case Integer number:
            yield "integer: " + number;
        default:
            yield "other";
    };
}
```

This is also an illustrative method. With a `switch expression`, the statement group after `:` must reach a `yield` (or throw an exception) to produce a value; **`break` does not replace `yield`**. Both methods above return the same result for corresponding inputs.

**Do not mix `->` and `:` in the same `switch` block.** Choose one consistent form for the entire block.

## 2. Key comparison table

| Criterion | Arrow rule `->` | Colon group `:` |
| --- | --- | --- |
| Organization | One label leads to one rule: an expression, block, or `throw` | A label leads to a group of statements |
| Fall-through | No | Can occur in a `switch statement` if the group does not exit |
| `switch statement` | No `break` needed to prevent fall-through; the expression part of a rule must be a *statement expression* | Usually uses `break`, `return`, or `throw` to avoid falling into the next group |
| `switch expression` | `-> expression` produces a value directly; a block requires `yield` or `throw` | Uses `yield expression;` or `throw` on the path producing a result |
| Pattern variable | In the guard and body of the matched rule | In the guard and the corresponding matched statement group |
| New code | Usually preferred for clarity and avoiding accidental fall-through | Useful when maintaining/updating legacy `switch` code or intentionally using groups |

`break` and `yield` are not synonymous: `break` exits a `switch statement`, whereas `yield` provides a result for a `switch expression`. The names **arrow rule** and **colon group** describe branch structure; they do not by themselves determine whether the entire `switch` is a statement or an expression.

## 3. `switch statement` with arrow rules: each branch is independent

```java
static void printValue(Object input) {
    switch (input) {
        case null -> System.out.println("null");
        case String text -> System.out.println(text.toUpperCase());
        case Integer number -> {
            System.out.println("integer");
            System.out.println(number + 1);
        }
        default -> System.out.println("other");
    }
}
```

This is an illustrative method (it must be placed inside a class). When the input is `"abc"`, it only prints `ABC`. If it is an `Integer`, only the `Integer` block runs. **There is no need to add `break` at the end of each rule**.

In a `switch statement`, the `case L -> expression;` form must have a **statement expression**, such as a method call, assignment, increment/decrement, or object creation. A bare computation like `case Integer i -> i + 1;` is **not** a valid rule expression in a `switch statement`: the expression `i + 1` is not a statement expression. If you want to produce a value, use a `switch expression`; if you want to perform an action, use a statement expression or a block.

A rule with multiple statements is placed inside `{ ... }`. Pattern variables like `text` or `number` are only in scope within their own rule; no state “leaks” into other rules.

## 4. `switch statement` with colon groups: watch out for `break`

```java
static void printValueWithColon(Object input) {
    switch (input) {
        case null:
            System.out.println("null");
            break;
        case String text:
            System.out.println(text.toUpperCase());
            break;
        case Integer number:
            System.out.println("integer");
            System.out.println(number + 1);
            break;
        default:
            System.out.println("other");
    }
}
```

Branches are separated by `:`. Each group executes the statements following its label until it encounters an appropriate exit action or reaches the end of the block. Use `break` to avoid accidentally falling into the next group. A trailing `default` group can complete normally upon reaching `}` without needing `break`.

`break` is not the only option. Inside a value-returning method, `return` also exits the method; `throw` throws an exception and does not continue normally. In a `switch statement` inside a loop, `continue` can advance to the next iteration when valid. When reading legacy code, the key is to identify **which groups can complete normally**.

## 5. True fall-through: use only when intentional

A classic example with constant labels (declaring no pattern variables):

```java
static String collect(int level) {
    StringBuilder result = new StringBuilder();

    switch (level) {
        case 1:
            result.append("first/");
            // intentional fall-through
        case 2:
            result.append("second");
            break;
        default:
            result.append("other");
    }
    return result.toString();
}
```

- `collect(1)` returns `"first/second"`: matches `case 1`, runs `append("first/")`, then continues into the statements of `case 2`.
- `collect(2)` returns `"second"`: starts at `case 2`.
- `collect(3)` returns `"other"`.

With arrow rules, `case 1 -> ...` **never** automatically flows into `case 2 -> ...`. If you want multiple labels to share the same behavior, use combined labels:

```java
static String category(int level) {
    return switch (level) {
        case 1, 2 -> "small";
        default -> "other";
    };
}
```

In colon groups, two adjacent constant labels can also share behavior:

```java
static String categoryWithColon(int level) {
    switch (level) {
        case 1:
        case 2:
            return "small";
        default:
            return "other";
    }
}
```

These are two ways of **combining labels for the same handling**, which differs from “executing some code first and then falling through”. Prefer combining labels over intentional fall-through when you do not need cumulative effects across groups.

## 6. Why pattern variables make colon fall-through more sensitive

Consider an example that **does not compile on Java 21**:

```java
// Intentionally invalid example:
static void invalid(Object value) {
    switch (value) {
        case String text:
            System.out.println("text=" + text);
            // Missing break!
        case Integer number:
            System.out.println(number + 1); // can reach here when value is a String
            break;
        default:
            break;
    }
}
```

If fall-through were allowed here, a `String` could cause execution to enter the statements of `case Integer number` **without the `Integer number` pattern ever having matched**. In that case, `number` would have no valid value. Java 21 **forbids** a preceding group from being able to complete normally and fall into a group starting with a pattern label that declares a pattern variable.

Another invalid case:

```java
// DOES NOT COMPILE:
static void invalidSharedBody(Object value) {
    switch (value) {
        case String text:
        case Integer number:
            System.out.println(number); // another label could select this body
            break;
        default:
            break;
    }
}
```

In a **colon statement group**, a statement cannot be associated with **multiple switch labels** when one of the labels is a pattern declaring a variable; Java cannot guarantee that all variables declared by different labels have been initialized.

Both restrictions target **the possibility of entering a pattern label whose binding has not matched**. They do not mean that *all forms of fall-through in every `switch` containing patterns* are forbidden. In practice, however, when using pattern variables you should prefer **independent groups with explicit exits**, or use arrow rules.

How to fix the first example:

```java
static void valid(Object value) {
    switch (value) {
        case String text:
            System.out.println("text=" + text);
            break;
        case Integer number:
            System.out.println(number + 1);
            break;
        default:
            break;
    }
}
```

Or more simply, use `->` so accidental fall-through is impossible.

## 7. `when` and pattern variable scope in both forms

A `when` guard is evaluated **after the pattern matches**. Therefore, the variable declared in the pattern can be used in both the guard and the branch body.

Arrow form:

```java
static String arrowGuard(Object value) {
    return switch (value) {
        case null -> "missing";
        case String text when text.isBlank() -> "blank";
        case String text -> "text:" + text.strip();
        default -> "other";
    };
}
```

Colon form:

```java
static String colonGuard(Object value) {
    return switch (value) {
        case null:
            yield "missing";
        case String text when text.isBlank():
            yield "blank";
        case String text:
            yield "text:" + text.strip();
        default:
            yield "other";
    };
}
```

Both methods are illustrative examples that must be placed in a class. Branch order matters: `String text when text.isBlank()` handles the blank case, and the unguarded `String text` after it handles the remaining strings. Reversing the order can cause a **dominated case**: the unguarded `String text` branch already covers all strings, so the subsequent `String ... when ...` branch can never be selected and Java reports a compile-time error.

Even though the same name `text` is used in two branches, each label introduces a **pattern variable with its own scope**. You cannot use `text` in `default` or outside the entire switch just because one branch declared it.

## 8. `switch expression` with arrows: direct values or `yield` blocks

A `switch expression` must produce **a value** or complete abnormally by throwing an exception. With arrows, it can be written very concisely:

```java
static int length(Object value) {
    return switch (value) {
        case null -> 0;
        case String text -> text.length();
        case Integer number -> number;
        default -> -1;
    };
}
```

Here `case String text -> text.length()` is valid because the `switch` is an **expression** and `text.length()` produces an `int`. Note that this is not the `switch statement` case with an expression `text.length()` after `->`; the context determines which syntax is allowed.

If multiple operations are needed in a rule, use a block and `yield`:

```java
static String normalize(Object value) {
    return switch (value) {
        case null -> "missing";
        case String text -> {
            String normalized = text.strip();
            yield normalized.isEmpty() ? "blank" : normalized;
        }
        default -> "other";
    };
}
```

`yield` sends a value out of the `switch expression`. If you replace `yield` with `break`, the `switch expression` does not receive the required result; if a block has a path that completes normally without `yield` or `throw`, the compiler also rejects it.

## 9. `switch expression` with colons: do not use `break` to return a result

The statement group form can express the same logic:

```java
static String normalizeWithColon(Object value) {
    return switch (value) {
        case null:
            yield "missing";
        case String text:
            String normalized = text.strip();
            yield normalized.isEmpty() ? "blank" : normalized;
        default:
            yield "other";
    };
}
```

In a `switch expression`, **`yield` returns a value**, while `break` cannot be used to return a value from the switch. Do not write:

```java
// DOES NOT COMPILE as a switch expression:
static int wrong(Object value) {
    return switch (value) {
        case null:
            break; // does not produce a result for the expression
        default:
            yield 1;
    };
}
```

A colon group in a `switch expression` can still allow fall-through between appropriate constant labels, provided every execution path eventually `yield`s or `throw`s. When pattern bindings are present, the pattern fall-through restrictions must still be respected.

Unless there is a specific reason to use colon groups, arrow syntax is usually easier to verify: each branch produces its own result, reducing the risk of forgetting `yield`.

## 10. Pattern switches must also satisfy general rules

The difference between `->` and `:` does not replace the rules of *pattern matching for switch*:

1. **Exhaustiveness:** A `switch expression` must cover all valid values. In Java 21, an **enhanced switch statement** that has a pattern label or `case null` must also be exhaustive. With an `Object` selector, use `default` or an appropriate covering pattern.
2. **Dominance:** Labels are checked in order; a broad unguarded pattern placed earlier can completely shadow a narrower pattern placed later. For example, `case CharSequence c` before `case String s` causes the `String` branch to be dominated.
3. **`null`:** Type patterns such as `case String s` do not match `null`. When switching on a reference that may be `null`, add `case null` if you need to handle it; `default` does not handle a `null` selector by default.
4. **Flow scope:** A pattern variable can only be used in the guard and code where the corresponding pattern is guaranteed to have matched; with colon groups, be especially careful about fall-through paths.
5. **`when` guard:** Can only be attached to a pattern label; `case String s when s.isBlank()` is not equivalent to checking any selector before type matching. To reach `s.isBlank()`, the `String s` match has already succeeded.
6. **Single switch block style:** Do not mix arrow rules and colon groups. This is a syntactic choice for the entire block, not a per-branch option.

When a program needs multiple labels for the same behavior without pattern variables, consider `case A, B -> ...` or constant labels in the same colon group instead of creating hard-to-follow fall-through.

## 11. Complete, runnable program on JDK 21

Create the file **`ArrowVsColonPatternDemo.java`**:

```java
public class ArrowVsColonPatternDemo {
    static String arrowExpression(Object value) {
        return switch (value) {
            case null -> "missing";
            case String s when s.isBlank() -> "blank";
            case String s -> "text:" + s.strip();
            case Integer n -> "number:" + n;
            default -> "other";
        };
    }

    static String colonExpression(Object value) {
        return switch (value) {
            case null:
                yield "missing";
            case String s when s.isBlank():
                yield "blank";
            case String s:
                yield "text:" + s.strip();
            case Integer n:
                yield "number:" + n;
            default:
                yield "other";
        };
    }

    static String arrowStatement(Object value) {
        StringBuilder output = new StringBuilder();
        switch (value) {
            case null -> output.append("missing");
            case String s when s.isBlank() -> output.append("blank");
            case String s -> output.append("text:").append(s.strip());
            case Integer n -> output.append("number:").append(n);
            default -> output.append("other");
        }
        return output.toString();
    }

    static String colonStatement(Object value) {
        String output;
        switch (value) {
            case null:
                output = "missing";
                break;
            case String s when s.isBlank():
                output = "blank";
                break;
            case String s:
                output = "text:" + s.strip();
                break;
            case Integer n:
                output = "number:" + n;
                break;
            default:
                output = "other";
        }
        return output;
    }

    static String fallthrough(int level) {
        StringBuilder output = new StringBuilder();
        switch (level) {
            case 1:
                output.append("first/");
                // fall through intentionally
            case 2:
                output.append("second");
                break;
            default:
                output.append("other");
        }
        return output.toString();
    }

    public static void main(String[] args) {
        Object[] values = {"  Java  ", "  ", 7, 4.5, null};

        for (Object value : values) {
            System.out.println(
                    arrowExpression(value) + " | " + colonExpression(value));
        }

        System.out.println("statement-arrow=" + arrowStatement("  A  "));
        System.out.println("statement-colon=" + colonStatement("  A  "));
        System.out.println("fallthrough-1=" + fallthrough(1));
        System.out.println("fallthrough-2=" + fallthrough(2));
    }
}
```

Compile and run:

```bash
javac --release 21 ArrowVsColonPatternDemo.java
java ArrowVsColonPatternDemo
```

`--enable-preview` is not needed for pattern matching for switch on Java 21. **Exact stdout:**

```text
text:Java | text:Java
blank | blank
number:7 | number:7
other | other
missing | missing
statement-arrow=text:A
statement-colon=text:A
fallthrough-1=first/second
fallthrough-2=second
```

Points to compare:

- The two `switch expressions` differ only in branch organization; for the same selector, they produce the same result. Arrow produces a value via an expression; colon uses `yield`.
- The two `switch statements` also produce the same result: arrow executes a statement expression without falling into another rule, whereas colon uses `break` to prevent falling into the next group.
- `"  "` matches `String s` and the `s.isBlank()` guard is true, so it produces `blank`. `"  Java  "` produces `text:Java` after `strip()`.
- `7` is boxed into `Integer` when placed into `Object[]`, matching `case Integer n`; `4.5` is boxed into `Double`, going to `default`.
- `null` is caught by `case null` so it does not cause a `NullPointerException`.
- `fallthrough(1)` intentionally continues into the `case 2` code; `fallthrough(2)` only executes the `case 2` code. This is a `switch` using **constant labels**, so it does not trigger the rule preventing fall-through into an uninitialized pattern variable.

## 12. Checklist when writing or reviewing `switch pattern`

- **Choose statement or expression first:** if you need an action/side effect, use a statement; if you need a value to assign/return, use an expression.
- **Prefer `->` for new code:** avoids unintentional fall-through and makes control flow and pattern scope easier to see.
- **With `:`, check where each group ends:** `break` in a statement, `yield` in an expression, or an appropriate exit statement; do not assume `break` produces a value.
- **Check pattern variables:** do not allow fall-through from a previous group into a `case` that declares a pattern variable; do not combine multiple labels with the same group if one label declares a pattern variable.
- **Check ordering and guards:** place guarded/narrower patterns before unguarded broader branches to avoid dominance.
- **Cover all inputs:** consider `null`, `default`, and the exhaustiveness requirement of enhanced switch.
- **Compile at the right version:** use `javac --release 21` to verify Java 21 syntax; do not confuse it with preview features or changes in newer JDKs.

**Conclusion:** Both `case ... ->` and `case ... :` support pattern switch in Java 21, but they carry **different control-flow models**. Arrow rules are the clear default with no fall-through; colon groups require careful tracking of `break`/`yield` and pattern variable scope. Understanding this difference helps migrate legacy `switch` code to pattern matching without introducing compile errors or subtle control-flow bugs.

### References

- [Oracle Java 21 — Switch Expressions and Statements](https://docs.oracle.com/en/java/javase/21/language/switch-expressions-and-statements.html)
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Java Language Specification 21 — §14.11, Switch Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
