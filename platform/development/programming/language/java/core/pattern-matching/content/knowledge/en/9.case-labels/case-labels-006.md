# Combining Multiple Case Labels in Java 21

In Java, a `switch` can route **multiple input values to the same handling logic**. With modern syntax, the shortest way is to write multiple constants in a single `case` label, separated by commas:

```java
static String status(int code) {
    return switch (code) {
        case 200, 201, 204 -> "success";
        case 400, 404 -> "client error";
        default -> "other";
    };
}
```

When `code` is `200`, `201`, or `204`, the result is `"success"`. This is **multiple case constants in one case label**, not three consecutive branches executing one after another. This grouping can also be used with `String` constants or compatible enum constants.

However, in **Java 21**, the syntax for combining **patterns** is not the same as combining constants: `case String s, Integer n ->` is **invalid**. With *pattern matching for switch*, it is important to understand the difference between **a label with multiple constants**, **multiple labels sharing a colon group**, and **a pattern label with a binding variable**. This lesson explains the valid cases, compile-time limits, fall-through, scope, and how to redesign when multiple patterns share behavior.

## 1. Distinguishing case label, switch rule, and colon group

A Java 21 `switch` can use two kinds of blocks:

- **Switch rule (`->`)**: a `case` label leads to an expression, a block, or `throw`. After the rule finishes executing, control **does not fall through** to the next rule.
- **Switch labeled statement group (`:`)**: one or more `case` labels lead to a shared group of statements. In a `switch statement`, if a group finishes without exiting, control can **fall through** to the next group.

Example of multiple constants using arrow rules:

```java
switch (code) {
    case 200, 201, 204 -> System.out.println("success");
    case 400, 404 -> System.out.println("client error");
    default -> System.out.println("other");
}
```

Example of multiple labels in the classic colon style:

```java
switch (code) {
    case 200:
    case 201:
    case 204:
        System.out.println("success");
        break;
    case 400:
    case 404:
        System.out.println("client error");
        break;
    default:
        System.out.println("other");
}
```

The two snippets above are **illustrative code placed inside a method with an `int code` variable**. They print the same line for the same input. The colon snippet stacks multiple labels onto one statement group; `break` prevents execution from continuing into the following groups. The arrow form does not need `break`.

The shorthand syntax for a colon group is also valid:

```java
switch (code) {
    case 200, 201, 204:
        System.out.println("success");
        break;
    default:
        System.out.println("other");
}
```

Thus, **commas are not exclusive to arrow rules**: both kinds of switch blocks accept multiple *case constants* in a single label.

## 2. Grouping integer, string, and enum constants

### Integer constants

```java
static String priority(int level) {
    return switch (level) {
        case 1, 2 -> "low";
        case 3, 4 -> "medium";
        case 5 -> "high";
        default -> "unknown";
    };
}
```

`case 1, 2` specifies the same behavior for both values. The compiler checks whether the constants are compatible with the selector type; you cannot write an arbitrary runtime-computed expression like `case someVariable, 2` if `someVariable` is not a valid compile-time constant.

### String constants

```java
static boolean isPositiveAnswer(String answer) {
    if (answer == null) {
        return false;
    }
    return switch (answer) {
        case "yes", "y", "ok" -> true;
        case "no", "n" -> false;
        default -> false;
    };
}
```

Here, the `String` labels are matched by **string value**, not by hand-written `if` branches. This method is **case-sensitive**: `"YES"` does not match `"yes"`. The explicit `null` check prevents the `switch` on `String` from throwing a `NullPointerException` in this example.

### Enum constants

```java
enum Day { MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY, SATURDAY, SUNDAY }

static String plan(Day day) {
    return switch (day) {
        case SATURDAY, SUNDAY -> "rest";
        case MONDAY, FRIDAY -> "focus";
        case TUESDAY, WEDNESDAY, THURSDAY -> "regular";
        case null -> "unknown";
    };
}
```

When the selector is `Day`, the enum names do not need the `Day.` prefix in the `case` labels as shown above. The three groups of enum constants cover all seven values of the enum; the `case null` label handles a null reference separately. Therefore, this is an exhaustive `switch expression` without needing `default`.

The methods and `enum` in these three examples can be placed in the same class; they are not standalone files as presented. A complete runnable program is provided later for hands-on testing.

## 3. Grouping labels is different from intentional fall-through

These two forms are easy to confuse:

```java
switch (value) {
    case 1:
    case 2:
        System.out.println("same action");
        break;
    default:
        break;
}
```

This is **two labels pointing to the same statement group**. If `value=1`, what follows `case 1:` is another label (`case 2:`), and then `println`. There is no separate action for `case 1` that needs to run first.

Contrast that with:

```java
switch (value) {
    case 1:
        System.out.println("first");
        // fall through intentionally
    case 2:
        System.out.println("second");
        break;
    default:
        break;
}
```

With `value=1`, the second snippet prints **two lines**: `first` and `second`. With `value=2`, it only prints `second`. This is **fall-through from one statement group into another**, not merely grouping labels.

For the goal of "multiple values, one behavior," **prefer comma-separated constant labels** and arrow rules; there is no need to rely on fall-through.

## 4. Java 21 does not allow combining multiple case patterns with commas

When the selector is `Object`, the following labels can use *type patterns*:

```java
static String describe(Object value) {
    return switch (value) {
        case String text -> "string:" + text.strip();
        case Integer number -> "integer:" + number;
        case null -> "missing";
        default -> "other";
    };
}
```

Each label `case String text` or `case Integer number` creates a **separate pattern variable**. That variable is only in scope when the corresponding pattern matches, including in its `when` guard if present.

**Invalid Java 21 syntax:**

```java
// DOES NOT COMPILE IN JAVA 21 (illustration only):
// return switch (value) {
//     case String text, Integer number -> "supported";
//     default -> "other";
// };
```

In Java 21, a case label accepts one of these main forms: **a list of case constants**, **a single case pattern (optionally with `when`)**, **`case null` (optionally paired with `default`)**, or **`default`**. It does **not** have a comma-separated list of multiple patterns. Do not extrapolate from `case 1, 2` to `case String s, Integer n`.

Beyond the syntax difference, the two pattern variables `text` and `number` have **different types and matching paths**. A single shared branch could not assume both variables are initialized.

Valid way when a shared result is needed:

```java
static String supported(Object value) {
    return switch (value) {
        case String ignored -> "supported";
        case Integer ignored -> "supported";
        case null, default -> "other";
    };
}
```

Two different rules can return the same string. The name `ignored` is a separate pattern variable in **each rule**, not a single variable shared across branches. When you do not need to access the variable, keep the code clear and avoid duplicating long logic by calling a shared helper method.

## 5. A notable exception: colon groups with patterns that declare NO variables

Java 21 **does** allow multiple pattern labels in **the same colon statement group** when the patterns **do not declare any pattern variables**. For example, record patterns for empty records:

```java
record Ping() {}
record Pong() {}

static String messageType(Object value) {
    switch (value) {
        case Ping():
        case Pong():
            return "signal";
        case null:
            return "missing";
        default:
            return "other";
    }
}
```

This illustrative snippet requires placing the `record` declarations and method in an appropriate class. Both `case Ping():` and `case Pong():` are **record patterns** and neither declares any variables. Because no pattern variable is used when entering the statement group, having both labels point to the same `return "signal"` statement is valid in Java 21.

Important notes:

- The valid syntax here is **two separate colon labels**, **not** `case Ping(), Pong() -> ...`. Comma-separated patterns remain invalid in Java 21, even when the patterns declare no variables.
- Do not generalize this to `case String s: case Integer i:` and then use `s` or `i` in the same group. **Java forbids** a group with multiple switch labels when a pattern label attached to that statement declares a pattern variable.
- If you need to handle patterns with bindings, the clearest approach is usually **independent case rules** that call a shared helper method.

This difference shows that "combining case labels" is not just about commas: you must consider the **label kind** and **how the switch block is structured**.

## 6. Why colon groups cannot combine patterns with bindings

Example that **does not compile**:

```java
// DOES NOT COMPILE IN JAVA 21:
static void bad(Object value) {
    switch (value) {
        case String text:
        case Integer number:
            System.out.println(number);
            break;
        default:
            break;
    }
}
```

Suppose `value` is `"hello"`. If the compiler allowed entering the group from `case String text`, then `System.out.println(number)` would try to read `number` even though the pattern `Integer number` **did not match**. Java does not allow a statement to be associated with multiple switch labels if any pattern label among them declares a variable.

Another error that is also prevented:

```java
// DOES NOT COMPILE:
static void badFallthrough(Object value) {
    switch (value) {
        case String text:
            System.out.println(text);
            // Missing break: could fall through into the Integer case below
        case Integer number:
            System.out.println(number + 1);
            break;
        default:
            break;
    }
}
```

If code from the `String` branch could complete normally and enter the `Integer` branch, the variable `number` would not be guaranteed to be initialized. Java 21 forbids **falling through into a group whose case pattern declares a variable** from a preceding group that can complete normally.

This differs from a switch with only constant labels or certain record patterns that declare no variables. You should not make a blanket statement that "all fall-through is forbidden in pattern switches"; the core restriction is **ensuring pattern variables are properly initialized**.

## 7. `case null, default`: a special combination

In Java 21, `case null, default` is **valid** syntax for reference-type selectors:

```java
static String classify(Object value) {
    return switch (value) {
        case String s when !s.isBlank() -> "text";
        case Integer i -> "integer";
        case null, default -> "other";
    };
}
```

The final branch handles **both `null` and any values not matched by earlier branches**. `case null, default` must be the last label in the switch block, and no other label may follow it. This is a **special combination** in Java 21's grammar, not a general rule allowing `null` to be freely combined with arbitrary constants or patterns.

Compare:

```java
// Two separate labels, with the same meaning as the example above for unmatched paths:
case null -> "other";
default -> "other";
```

These two lines are an **illustrative snippet inside a switch expression**, not standalone code.

When using `default` **without** `case null`, do not assume `default` will handle `null` in a pattern switch. A `null` reference selector generally requires an explicit `case null`; otherwise it can throw a `NullPointerException`.

With a `case null, default` label, avoid placing unguarded catch-all patterns like `case Object anything` before it if they would make the remaining label redundant or dominated. Label ordering and coverage are still subject to Java's compile-time checks.

## 8. `when` guards: they do not make a pattern list valid

To classify the same type under different conditions, write **multiple independent pattern branches**:

```java
static String textKind(Object value) {
    return switch (value) {
        case String s when s.isBlank() -> "blank";
        case String s when s.length() >= 10 -> "long text";
        case String s -> "short text";
        case null, default -> "not text";
    };
}
```

Order matters here: the unguarded `String s` is placed **after** the guarded branches, because an unguarded branch covers all `String` values and would cause subsequent branches to become **dominated cases**.

You cannot write `case String s when s.isBlank(), Integer i -> ...` as a combined form. A `when` guard is attached to **a single case pattern**. If two types need the same result, split the branches and call a shared method.

Another option is to use a **common supertype** when it makes sense for the data model:

```java
static String category(Object value) {
    return switch (value) {
        case Number n -> "number:" + n;
        case CharSequence s -> "characters:" + s.length();
        case null, default -> "other";
    };
}
```

`Number n` covers `Integer`, `Long`, `Double`, and other matching subtypes, while `CharSequence s` covers `String`, `StringBuilder`, and other character sequence types. This is **grouping by subtype relationship** with a single pattern, **not** arbitrarily combining unrelated types. Only use it when the business meaning of the common type matches the desired handling.

## 9. Constraints when combining multiple case constants

The Java compiler checks labels across the **entire switch block**, not just within a single `case` line.

### No duplicate constants

```java
// DOES NOT COMPILE:
switch (code) {
    case 1, 2 -> System.out.println("first");
    case 2, 3 -> System.out.println("second"); // 2 is duplicated
    default -> {}
}
```

`2` appears in both labels, causing a compile-time error. Likewise, two constant expressions written differently that evaluate to the **same value** are also treated as duplicates.

### Constant types must match the selector

```java
// DOES NOT COMPILE with int code:
// switch (code) {
//     case "200", "201" -> System.out.println("ok");
//     default -> {}
// }
```

`String` labels are incompatible with an `int` selector. Distinguish between the integer value `200` and the string `"200"`.

### Cannot attach a `when` guard directly to constant labels

```java
// DOES NOT COMPILE in Java 21:
// case 1, 2 when enabled -> "ok";
```

`when` is part of a **case pattern**. For constants, check the condition inside the rule body or in a controlling expression before the `switch`.

### Cannot mix the two switch block styles

```java
// DOES NOT COMPILE: mixing arrow and colon in the same switch block.
// switch (code) {
//     case 1, 2 -> System.out.println("small");
//     case 3:
//         System.out.println("three");
// }
```

A block must consistently use either **switch rules** or **switch labeled statement groups**.

## 10. Switch statement and switch expression when combining labels

For a **switch statement**, arrows are commonly used to perform actions:

```java
static void logStatus(int code) {
    switch (code) {
        case 200, 201 -> System.out.println("ok");
        case 400, 404 -> System.out.println("client error");
        default -> System.out.println("other");
    }
}
```

For a **switch expression**, each branch must produce a result:

```java
static String codeLabel(int code) {
    return switch (code) {
        case 200, 201 -> "ok";
        case 400, 404 -> "client error";
        default -> "other";
    };
}
```

With **colon groups** in a switch expression, use `yield` to return a value:

```java
static String codeLabelColon(int code) {
    return switch (code) {
        case 200:
        case 201:
            yield "ok";
        case 400:
        case 404:
            yield "client error";
        default:
            yield "other";
    };
}
```

Do not use `break` instead of `yield` in a switch expression; `break` is only for exiting a switch statement or related control-flow construct. For pattern labels with bindings, whether in a statement or an expression, scope and fall-through constraints must still be respected.

A **switch expression** must be exhaustive. In Java 21, an **enhanced switch statement** using patterns or `case null` must also be exhaustive. With an `Object` selector, `default` or `case null, default` is the usual way to cover unhandled inputs. With an enum, covering all enum constants can satisfy exhaustiveness; you still need to decide how to handle a `null` selector separately if it can occur.

## 11. Complete Java 21 example

Create the file **`MultipleCaseLabelsDemo.java`**:

```java
public class MultipleCaseLabelsDemo {
    enum Day {
        MONDAY, TUESDAY, WEDNESDAY, THURSDAY,
        FRIDAY, SATURDAY, SUNDAY
    }

    record Ping() {}
    record Pong() {}

    static String status(int code) {
        return switch (code) {
            case 200, 201, 204 -> "ok";
            case 400, 404 -> "client-error";
            default -> "other";
        };
    }

    static String dayType(Day day) {
        return switch (day) {
            case SATURDAY, SUNDAY -> "weekend";
            case MONDAY, FRIDAY -> "edge-weekday";
            case TUESDAY, WEDNESDAY, THURSDAY -> "weekday";
            case null -> "unknown";
        };
    }

    static String legacyGrouped(int code) {
        String result;
        switch (code) {
            case 200:
            case 201:
            case 204:
                result = "ok";
                break;
            case 400:
            case 404:
                result = "client-error";
                break;
            default:
                result = "other";
        }
        return result;
    }

    static String noBindings(Object value) {
        switch (value) {
            case Ping():
            case Pong():
                return "signal";
            case null:
                return "missing";
            default:
                return "other";
        }
    }

    static String typeAware(Object value) {
        return switch (value) {
            case String s when s.isBlank() -> "blank";
            case String s -> "string:" + s.strip();
            case Integer n -> "integer:" + n;
            case null, default -> "misc";
        };
    }

    public static void main(String[] args) {
        System.out.println(status(200));
        System.out.println(status(404));
        System.out.println(status(999));
        System.out.println(dayType(Day.SUNDAY));
        System.out.println(dayType(Day.WEDNESDAY));
        System.out.println(dayType(null));
        System.out.println(legacyGrouped(201));
        System.out.println(noBindings(new Ping()));
        System.out.println(noBindings(new Pong()));
        System.out.println(noBindings(null));
        System.out.println(typeAware("  Java  "));
        System.out.println(typeAware("  "));
        System.out.println(typeAware(7));
        System.out.println(typeAware(2.5));
        System.out.println(typeAware(null));
    }
}
```

Compile and run on **JDK 21** (no `--enable-preview` needed):

```bash
javac --release 21 MultipleCaseLabelsDemo.java
java MultipleCaseLabelsDemo
```

**Exact stdout:**

```text
ok
client-error
other
weekend
weekday
unknown
ok
signal
signal
missing
string:Java
blank
integer:7
misc
misc
```

Comparing each group:

1. `status` groups status codes using constant lists `200, 201, 204` and `400, 404`. Code `999` goes to `default`.
2. `dayType` groups enum constants without needing `Day.` before each name; `case null` handles a null input.
3. `legacyGrouped` produces the same result as the arrows in `status`, but groups constants using multiple colon labels and requires `break` to prevent fall-through.
4. `noBindings` uses two **record patterns without binding variables** in the same colon group. Both `Ping` and `Pong` produce `signal`.
5. `typeAware` keeps pattern branches **separate**, uses `when` for blank strings, and ends with `case null, default`. The number `7` boxes to `Integer`, while `2.5` boxes to `Double` and goes to `misc`.

When learning by modifying code, try changing `case 200, 201, 204` into stacked colon labels and recompiling. Then try one of the **intentionally invalid** examples from earlier sections to observe the compiler errors for pattern lists or duplicate constants; do not keep invalid examples in the final runnable file.

## 12. Choosing the right way to combine labels

| Need | Recommended approach in Java 21 |
| --- | --- |
| Multiple constants with the same behavior | `case A, B, C -> ...` |
| Maintaining a classic switch with multiple constants | `case A: case B: ... break;` or `case A, B:` |
| Two different reference types needing the same result | Two separate pattern rules returning the same result or calling a shared method |
| Subtypes that genuinely share handling semantics | One pattern using an appropriate supertype such as `case Number n` |
| Multiple record patterns without binding variables sharing behavior | Multiple colon pattern labels in one group |
| Catching both `null` and all unmatched cases | `case null, default -> ...` at the end of the switch block |
| Distinguishing multiple conditions on the same type | Guarded pattern branches with `when` before the unguarded branch |
| Producing a return value | A switch expression with `-> expression` or a colon group with `yield` |

**Pre-compile checklist:** (1) are any constants in labels duplicated or of the wrong type; (2) did you accidentally write a comma-separated list of patterns; (3) does a colon group have a pattern variable used from an unmatched path; (4) is there any unintended fall-through; (5) are `default` and `case null` handling their intended cases; (6) does the order of case patterns cause dominance; and (7) is the switch expression or enhanced switch statement exhaustive.

**Conclusion:** "Combining multiple case labels" in Java 21 involves **several distinct mechanisms**: grouping **case constants** with commas, sharing a **colon statement group** across multiple labels, or using the special **`case null, default`** combination. For patterns with variables, use separate branches or an appropriate supertype; do not apply the constant-grouping syntax to pattern lists. Making this distinction keeps code concise while preserving scope, fall-through, and type safety.

### References

- [Java Language Specification 21, §14.11 — Switch Statements](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
