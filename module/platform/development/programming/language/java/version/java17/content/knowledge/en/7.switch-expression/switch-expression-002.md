# Arrow Labels and Colon Labels in Java 17 Switch Expressions

In Java 17, `switch` can be written with **two styles of branch labels**:

- **Arrow labels:** `case ... ->` — each branch has a clear boundary; **does not automatically continue to the next branch** (*fall-through*).
- **Colon labels:** `case ...:` — groups statements in the traditional way; can **continue running** into the following label group if control flow has not ended.

Both forms can appear in a **switch statement** (the `switch` statement) and a **switch expression** (the `switch` expression), but how they **return a value**, **exit a branch**, and **handle fall-through** differ. When learning switch expressions, it is especially important to distinguish:

```java
// Arrow: the expression after -> directly produces the value for the switch expression.
String text = switch (code) {
    case 1 -> "One";
    case 2 -> "Two";
    default -> "Other";
};
```

from:

```java
// Colon: use yield to provide a value for the switch expression.
String text = switch (code) {
    case 1:
        yield "One";
    case 2:
        yield "Two";
    default:
        yield "Other";
};
```

**Both snippets are valid in Java 17**, provided the `code` variable is declared with a compatible type, such as `int`. Switch expressions became a **standard feature in Java 14** and are stable in Java 17 without needing `--enable-preview`. This lesson only uses syntax standardized in Java 17.

## 1. First: how does a switch statement differ from a switch expression?

Both constructs use the `switch` keyword and `case` labels, but they serve different purposes.

### 1.1. Switch statement: performing actions

```java
static void printStatus(int status) {
    switch (status) {
        case 200 -> System.out.println("Success");
        case 404 -> System.out.println("Not found");
        default -> System.out.println("Other status");
    }
}
```

This is a **statement**: the branches perform actions and do not produce a single value to assign to a variable. There is no `;` after the `}` to terminate a `switch` expression, because this is a complete `switch` statement.

### 1.2. Switch expression: computing a value

```java
static String statusText(int status) {
    return switch (status) {
        case 200 -> "Success";
        case 404 -> "Not found";
        default -> "Other status";
    };
}
```

Here, **the entire `switch (...) { ... }` is an expression**. The result of the chosen branch becomes the result of the expression, so it can be used in `return` or on the right-hand side of an assignment:

```java
String message = switch (status) {
    case 200 -> "OK";
    case 404 -> "Not found";
    default -> "Other";
};
```

The `;` after `}` belongs to the assignment or `return` statement containing the switch expression.

| Characteristic | Switch statement | Switch expression |
| --- | --- | --- |
| Primary purpose | Execute statements or side effects. | Produce a value used in another expression. |
| Can use `->`? | Yes. | Yes. |
| Can use `:`? | Yes. | Yes. |
| Must cover all possibilities of the selector? | No, in the general case. | **Yes**: every valid selector value must have a handling branch. |
| Branch ends with `break`? | Can be used, especially with `:` labels. | Does not use `break` to return a value. |
| Multi-statement branch wanting to produce a value | Not applicable; this is a statement. | Use `yield value;` inside a block branch or `:` label group. |

Within a specific `switch`, **do not mix `->` labels with `:` labels**. Choose one consistent label style for the entire switch block.

## 2. Arrow labels: `case ... ->`

The arrow form is usually best when each case leads to **a single value or an independent block of logic**.

### 2.1. Syntax for returning an expression directly

```java
enum AccessLevel {
    GUEST, MEMBER, ADMIN
}

class ArrowLabels {
    static int maxProjects(AccessLevel access) {
        return switch (access) {
            case GUEST -> 1;
            case MEMBER -> 10;
            case ADMIN -> 100;
        };
    }
}
```

Because the three labels cover all constants of the `AccessLevel` enum, the compiler recognizes that the switch expression covers all cases for this enum. In the arrow form:

- After `->` is **an expression** that produces a value, such as `1`, `10`, or `100`.
- **No `yield` is needed** when writing an expression directly after the arrow.
- **No `break` is needed**: one branch does not fall through to the branch below it.
- When a new value is added to the enum and this code is recompiled, the compiler can require handling the new value to restore exhaustiveness.

### 2.2. Grouping multiple values in one label

Java 17 allows placing multiple constants after a single `case`:

```java
enum DayType {
    MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY,
    SATURDAY, SUNDAY
}

class DayLabels {
    static boolean isWeekend(DayType day) {
        return switch (day) {
            case SATURDAY, SUNDAY -> true;
            case MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY -> false;
        };
    }
}
```

Both `SATURDAY` and `SUNDAY` lead to `true`. This is **multiple labels for one branch**, completely different from statements running across multiple branches.

### 2.3. When a branch has multiple statements, use a block and `yield`

If you need multi-step calculations, logging, or condition checks before returning a value, use a **block** after `->`:

```java
enum Plan {
    FREE, STANDARD, PREMIUM
}

class PriceCalculator {
    static int monthlyPrice(Plan plan, int basePrice) {
        return switch (plan) {
            case FREE -> 0;

            case STANDARD -> {
                int discount = 10;
                int amount = basePrice * (100 - discount) / 100;
                yield amount;
            }

            case PREMIUM -> {
                int supportFee = 50_000;
                int amount = basePrice + supportFee;
                yield amount;
            }
        };
    }
}
```

Important rule: **a block after `->` does not automatically turn its last statement into a value**. To return a value from a switch expression block, you must use `yield`.

Incorrect example:

```java
// Does not compile in Java 17:
// int price = switch (plan) {
//     case FREE -> 0;
//     case STANDARD -> {
//         int amount = 90;
//         amount; // Not how a block returns a value.
//     }
//     case PREMIUM -> 150;
// };
```

Fix it with `yield amount;`. You can think of `yield` as the statement that **passes a value out of the enclosing switch expression**. It is not the same as `return` from the method containing the switch.

### 2.4. When a branch throws an exception instead of producing a value

A switch expression branch can use a `throw` statement:

```java
static int parseLevel(String level) {
    return switch (level) {
        case "LOW" -> 1;
        case "MEDIUM" -> 2;
        case "HIGH" -> 3;
        default -> throw new IllegalArgumentException(
                "Unsupported level: " + level
        );
    };
}
```

The `default` branch does not produce a value because it terminates with an exception. This still satisfies the switch expression requirement: every path must **produce a value or complete abruptly** (such as throwing an exception).

## 3. Colon labels: `case ...:`

The colon form creates **statement groups**. Inside a group, Java executes statements sequentially. Without a control-transfer construct leaving the group, execution can continue into subsequent label groups.

### 3.1. The `:` form of a switch statement uses `break`

```java
static void printPlan(String plan) {
    switch (plan) {
        case "FREE":
            System.out.println("Free plan");
            break;

        case "STANDARD":
            System.out.println("Standard plan");
            break;

        case "PREMIUM":
            System.out.println("Premium plan");
            break;

        default:
            System.out.println("Unknown plan");
    }
}
```

Here, `break;` **exits the switch statement**. If you omit `break;` after `case "FREE":`, the program can also print the messages for `STANDARD` and the branches below it.

### 3.2. The `:` form of a switch expression uses `yield`

You can still use colon labels in a switch expression, but you must **provide the result** with `yield`:

```java
static String planDescription(String plan) {
    return switch (plan) {
        case "FREE":
            yield "Free plan";

        case "STANDARD":
            yield "Standard plan";

        case "PREMIUM":
            yield "Premium plan";

        default:
            yield "Unknown plan";
    };
}
```

In a switch expression using `:`:

1. Java jumps to the matching label.
2. Statements execute sequentially.
3. `yield expression;` provides the value for **the entire switch expression** and finishes evaluating that expression.
4. If control flow can reach the end of the switch expression without providing a value or throwing an exception, the program is invalid.

**Do not replace `yield "x";` with `break "x";`**: the `break value` syntax is not a value-returning mechanism in Java 17. `break;` exits the corresponding switch statement or loop, whereas `yield` yields a value out of a switch expression.

## 4. Same problem, written in both label styles for comparison

Save the complete example in **`SwitchLabelsDemo.java`**:

```java
enum ShippingMethod {
    STANDARD, EXPRESS, SAME_DAY
}

public class SwitchLabelsDemo {

    static int feeWithArrow(ShippingMethod method) {
        return switch (method) {
            case STANDARD -> 15_000;
            case EXPRESS -> 30_000;
            case SAME_DAY -> 50_000;
        };
    }

    static int feeWithColon(ShippingMethod method) {
        return switch (method) {
            case STANDARD:
                yield 15_000;
            case EXPRESS:
                yield 30_000;
            case SAME_DAY:
                yield 50_000;
        };
    }

    public static void main(String[] args) {
        for (ShippingMethod method : ShippingMethod.values()) {
            int arrowFee = feeWithArrow(method);
            int colonFee = feeWithColon(method);

            System.out.println(
                    method + " -> arrow=" + arrowFee
                    + ", colon=" + colonFee
            );
        }
    }
}
```

Compile and run with Java 17:

```bash
javac --release 17 SwitchLabelsDemo.java
java SwitchLabelsDemo
```

Output:

```text
STANDARD -> arrow=15000, colon=15000
EXPRESS -> arrow=30000, colon=30000
SAME_DAY -> arrow=50000, colon=50000
```

Both methods produce the same results, but they differ in syntax and control flow:

| Arrow | Colon |
| --- | --- |
| `case STANDARD -> 15_000;` | `case STANDARD: yield 15_000;` |
| Fewer statements when the return value is simple. | Can hold multiple statements in a group before `yield`. |
| No fall-through between branches. | Can fall through if it has not yet called `yield` or terminated abruptly. |
| For multiple statements, use `-> { ... yield ...; }`. | Statements can be written after the label and then `yield` directly. |

For new switch expressions, **prefer arrow labels** if the branches are independent. The colon style remains completely valid and useful when understanding or maintaining code that uses statement groups.

## 5. Fall-through: the most important difference

*Fall-through* is the phenomenon where execution **continues into the next label's statement group** after entering one branch, if no appropriate control-transfer statement such as `break`, `yield`, `return`, or `throw` is encountered.

### 5.1. With arrow labels, there is no fall-through

```java
static String category(int code) {
    return switch (code) {
        case 1 -> "One";
        case 2 -> "Two";
        default -> "Other";
    };
}
```

When `code == 1`, the result is always `"One"`. It cannot accidentally continue into the `"Two"` expression. No `break` is needed to prevent that.

### 5.2. With colon labels, fall-through is possible

```java
static String categoryWithFallThrough(int code) {
    return switch (code) {
        case 0:
            System.out.println("Encountered zero");
            // No yield, so execution falls through to case 1.
        case 1:
            yield "Zero or One";
        default:
            yield "Other";
    };
}
```

If `code == 0`, the program prints `Encountered zero` and then continues to `yield "Zero or One";`. If `code == 1`, it goes straight to `yield "Zero or One";`.

This control flow is valid, though easy to misunderstand. When **multiple values genuinely share one result**, intentional fall-through is unnecessary:

```java
static String categoryClearer(int code) {
    return switch (code) {
        case 0, 1 -> "Zero or One";
        default -> "Other";
    };
}
```

This is an advantage of arrow label syntax in Java 17: the intent to group cases is clear, reducing the risk of forgetting `break` or `yield`.

### 5.3. The colon style can also group labels without duplication

```java
static String categoryWithGroupedColon(int code) {
    return switch (code) {
        case 0:
        case 1:
            yield "Zero or One";
        default:
            yield "Other";
    };
}
```

Because `case 0:` has no statements before `case 1:`, both labels lead to the same `yield` statement. With Java 17, you can also write one label with multiple constants:

```java
static String categoryWithMultiLabelColon(int code) {
    return switch (code) {
        case 0, 1:
            yield "Zero or One";
        default:
            yield "Other";
    };
}
```

Both ways are valid, though if branches only return independent values, the `case 0, 1 -> "Zero or One";` version is more concise.

## 6. How do `yield`, `break`, `return`, and `throw` differ?

These keywords all relate to control flow, but they cannot be swapped arbitrarily.

| Keyword | Meaning in the current context | Appropriate example |
| --- | --- | --- |
| `yield value;` | Terminates the enclosing **switch expression** and provides its value. | `case X: yield 10;` or `case X -> { yield 10; }` |
| `break;` | Exits the matching **switch statement** or loop receiving `break`. | `case X: doWork(); break;` |
| `return value;` | Returns a result and terminates the current **method**. | `return switch (key) { ... };` |
| `throw exception;` | Throws an exception, ending normal flow in that branch. | `default -> throw new IllegalArgumentException();` |

A common mistake is trying to write:

```java
static int wrong(int code) {
    // WRONG: break is not how a switch expression returns a result.
    // return switch (code) {
    //     case 1:
    //         break 10;
    //     default:
    //         break 0;
    // };
    return 0;
}
```

Correct version:

```java
static int correct(int code) {
    return switch (code) {
        case 1:
            yield 10;
        default:
            yield 0;
    };
}
```

Inside an arrow label's block, you also cannot use `return` to **replace** `yield` in a switch expression. If you need to return from the method, put `return` **outside** the expression:

```java
static int amount(int code) {
    return switch (code) {
        case 1 -> {
            int computed = 10 * 2;
            yield computed;
        }
        default -> 0;
    };
}
```

Additionally, a switch statement with arrow labels has no need for `yield` because it does not produce a switch expression value:

```java
static void announce(int code) {
    switch (code) {
        case 1 -> System.out.println("Created");
        case 2 -> System.out.println("Updated");
        default -> System.out.println("Other");
    }
}
```

**Identify by context:** if the entire `switch` sits on the right-hand side of an assignment or after `return` to produce a value, it is a switch expression; if `switch` stands as an independent statement to perform an action, it is a switch statement.

## 7. Value types and exhaustiveness of a switch expression

Because a switch expression is always used as **a value**, the compiler must be able to verify that all possibilities of the selector are handled.

### 7.1. Selectors of type `int` or `String` usually need `default`

```java
static String mapCode(int code) {
    return switch (code) {
        case 1 -> "Created";
        case 2 -> "Updated";
        default -> "Unknown";
    };
}
```

If `default` is omitted, this switch expression over `int` does not cover all possible values. The colon-based version also needs to cover all cases:

```java
static String mapCodeWithColon(int code) {
    return switch (code) {
        case 1:
            yield "Created";
        case 2:
            yield "Updated";
        default:
            yield "Unknown";
    };
}
```

A branch can `throw` instead of yielding a value, as long as all paths are handled.

### 7.2. With an enum, all constants can be listed exhaustively

```java
enum TrafficLight {
    RED, YELLOW, GREEN
}

static String instruction(TrafficLight light) {
    return switch (light) {
        case RED -> "Stop";
        case YELLOW -> "Slow down";
        case GREEN -> "Go";
    };
}
```

`default` is not required if the switch expression already covers all three enum values. This is helpful because when an enum constant is added and code using the switch is recompiled, the compiler can pinpoint where logic needs updating.

If the API publishing the enum changes after the program has already been compiled, binary compatibility and runtime handling must still be considered; **do not substitute dependency upgrade testing simply because the enum appeared exhaustive when the code was written**.

### 7.3. Branches must provide results of compatible types

```java
static double discountRatio(String tier) {
    return switch (tier) {
        case "SILVER" -> 0.05;
        case "GOLD" -> 0.10;
        default -> 0.0;
    };
}
```

The result type of each branch must match how the switch expression is used and Java's type rules. You cannot return an object incompatible with the target type without a valid conversion.

If within a `-> { ... }` branch there are paths continuing past the block without **using `yield` or `throw`**, the compiler will reject the switch expression. The colon style is subject to the same value requirement, even though statements can fall through from one label to another.

## 8. Variable scope and block issues

### 8.1. A block after `->` creates a clear variable scope

```java
static int compute(String mode) {
    return switch (mode) {
        case "A" -> {
            int result = 10;
            yield result;
        }
        case "B" -> {
            int result = 20;
            yield result;
        }
        default -> 0;
    };
}
```

Two local variables with the same name `result` are valid because they reside in **two separate blocks**.

### 8.2. With `:`, blocks can be used to isolate scope

```java
static int computeWithColon(String mode) {
    return switch (mode) {
        case "A": {
            int result = 10;
            yield result;
        }
        case "B": {
            int result = 20;
            yield result;
        }
        default:
            yield 0;
    };
}
```

In a switch using colon statement groups, labels do not automatically create independent blocks. When you need to declare variables with the same name in multiple branches, wrap each branch's statements in `{ ... }` to avoid scope conflicts. This also helps readers clearly see which variables belong to which branch.

## 9. Common syntax and logic errors

### Error 1 — Misplacing `;` after an arrow label's block

```java
static int fee(int code) {
    return switch (code) {
        case 1 -> {
            yield 10;
        }
        default -> 0;
    };
}
```

Do not add a semicolon **right after the `}` of a branch block**. The `;` that ends the whole `return switch (...) { ... };` statement sits **after the final `}`** of the switch expression.

### Error 2 — Writing `case X: expression;` and expecting the expression to return a value automatically

```java
// Wrong: the statement in the colon branch does not yield a value.
// int result = switch (code) {
//     case 1:
//         10;
//     default:
//         0;
// };
```

Fix it to `case 1: yield 10;` and `default: yield 0;`, or convert the whole switch to arrow labels.

### Error 3 — Forgetting `yield` on one path of a block

```java
// Wrong: if amount <= 0, the branch does not produce a value.
// return switch (code) {
//     case 1 -> {
//         if (amount > 0) {
//             yield amount;
//         }
//     }
//     default -> 0;
// };
```

Fix by handling both paths:

```java
static int normalizedAmount(int code, int amount) {
    return switch (code) {
        case 1 -> {
            if (amount > 0) {
                yield amount;
            }
            yield 0;
        }
        default -> 0;
    };
}
```

### Error 4 — Mixing `->` and `:` labels in the same switch

```java
// Wrong: do not mix the two label styles in the same switch block.
// return switch (code) {
//     case 1 -> "One";
//     default:
//         yield "Other";
// };
```

Choose one consistently:

```java
static String describe(int code) {
    return switch (code) {
        case 1 -> "One";
        default -> "Other";
    };
}
```

### Error 5 — Confusing `break` with `yield`

A switch statement using `:` typically needs `break` to prevent falling through branches. A switch expression using `:` needs `yield` to output a result. You cannot blindly copy statement control flow into an expression without accounting for this difference.

### Error 6 — Assuming `default` always handles `null`

```java
static String label(String input) {
    return switch (input) {
        case "A" -> "Alpha";
        default -> "Other";
    };
}
```

With regular switch syntax, **a `null` selector causes `NullPointerException` in Java 17**; it does not automatically enter `default`. If the input can be `null`, handle it beforehand:

```java
static String safeLabel(String input) {
    if (input == null) {
        return "Missing";
    }

    return switch (input) {
        case "A" -> "Alpha";
        default -> "Other";
    };
}
```

Do not rely on pattern matching syntax in `switch` from newer Java versions to write examples expected to run by default on Java 17: **pattern matching for switch is only preview in JDK 17** (JEP 406).

### Error 7 — Using `case` like an arbitrary `if` condition

Java 17 `case` labels work with **constant forms matching the selector type**, enum labels, and corresponding language capabilities. They are not places to arbitrarily substitute runtime conditions like `case value > 10 -> ...` in a regular switch.

If you need to check numeric ranges like `score >= 90`, you can use `if/else` before applying `switch`, or convert them into a clear set of constants/status types suited to the business domain.

## 10. Which label to choose in Java 17 code?

| Scenario | Recommended style |
| --- | --- |
| Each value leads to a single return value. | Switch expression with `-> expression`. |
| A branch has multiple calculation steps before producing a result. | `case X -> { ... yield result; }`. |
| Multiple constants share a single result. | `case A, B, C -> value;`. |
| Want to execute an action per case, with no shared value needed. | Switch statement with `-> statement;` or `-> { ... }`. |
| Reading or maintaining a switch expression that uses statement groups. | Understand `case X: ... yield value;` and fall-through potential. |
| Intentional fall-through between statement groups is needed. | `:` labels can express it, but explain clearly with comments and check whether label grouping can replace it. |
| Input data can be `null`. | Handle `null` before entering a regular Java 17 switch. |

For new code, **arrow labels are usually easier to maintain** because they eliminate unintended fall-through. The colon style remains a supported part of Java 17 and can make sense when logic calls for statement groups. The focus is on choosing the right control flow, not forcing every switch statement into a switch expression.

## 11. Real-world scenario example: classifying order status

Suppose a system has an enum:

```java
enum OrderStatus {
    CREATED,
    PAID,
    PACKED,
    SHIPPED,
    CANCELLED
}
```

Users need to know whether the shipping address can still be modified. With a switch expression:

```java
static boolean canChangeAddress(OrderStatus status) {
    return switch (status) {
        case CREATED, PAID -> true;
        case PACKED, SHIPPED, CANCELLED -> false;
    };
}
```

Arrow labels fit well because each set of statuses returns a boolean with no side effects. If we also need a message explaining why it cannot be modified, we can keep multiple steps inside a block:

```java
static String addressChangeMessage(OrderStatus status) {
    return switch (status) {
        case CREATED, PAID -> "Address can be changed";
        case PACKED, SHIPPED -> {
            String stage = status.name();
            yield "Order is being processed for delivery: " + stage;
        }
        case CANCELLED -> "Order has been cancelled";
    };
}
```

The same logic written in colon style:

```java
static boolean canChangeAddressWithColon(OrderStatus status) {
    return switch (status) {
        case CREATED:
        case PAID:
            yield true;
        case PACKED:
        case SHIPPED:
        case CANCELLED:
            yield false;
    };
}
```

Comparing the two methods shows:

1. **The set of statuses and outcomes do not change.**
2. The arrow form reveals label grouping on a single line and needs no `yield` for a single expression.
3. The colon form uses consecutive labels and a shared `yield` to return the result.
4. If a new `OrderStatus` is added, both switch expressions may need updating to cover the new case upon recompilation.

**Design note:** Whether an order in the `PAID` status allows address editing is a hypothetical example rule, not a universal rule for all e-commerce systems. Authorization logic should be modeled according to actual application requirements.

## 12. Practice exercises

### Exercise 1 — Convert `:` to `->`

Rewrite the following method using arrow labels without changing its output:

```java
static String severityLabel(int level) {
    return switch (level) {
        case 1:
            yield "LOW";
        case 2:
            yield "MEDIUM";
        case 3:
            yield "HIGH";
        default:
            yield "UNKNOWN";
    };
}
```

Hint: for each branch with only a single `yield`, convert directly to `case X -> "VALUE";`.

### Exercise 2 — Grouping multiple labels

Given the enum:

```java
enum MonthGroup {
    JANUARY, FEBRUARY, MARCH, APRIL, MAY, JUNE,
    JULY, AUGUST, SEPTEMBER, OCTOBER, NOVEMBER, DECEMBER
}
```

Write `static boolean isSummer(MonthGroup month)` returning `true` for `JUNE`, `JULY`, `AUGUST`. Use a switch expression with arrow labels and **group constants that share the same result** into appropriate branches.

### Exercise 3 — Multi-statement branches

Write `static int bonus(int level, int baseAmount)`. When `level == 1`, return `0`; when `level == 2`, compute `baseAmount * 5 / 100`; when `level == 3`, compute `baseAmount * 10 / 100`. Use `-> { ... yield ...; }` for branches that require multiple steps.

### Exercise 4 — Analyzing fall-through

Predict the output of:

```java
static String inspect(int code) {
    return switch (code) {
        case 0:
            System.out.println("A");
        case 1:
            System.out.println("B");
            yield "X";
        default:
            yield "Y";
    };
}
```

Consider `inspect(0)`, `inspect(1)`, and `inspect(2)` separately. Rewrite using arrow labels so the **return values** are equivalent; if you want to preserve the printed messages as well, use blocks and explicitly write the required print statements for each case.

### Exercise 5 — Finding and fixing errors

What problems does the following snippet have when compiled with Java 17?

```java
// Snippet demonstrating errors:
// String result = switch (code) {
//     case 1 -> "ONE";
//     case 2:
//         yield "TWO";
// };
```

Hint: review **the rule against mixing labels** and **exhaustiveness for type int**, then fix it using one consistent label style and adding the required case.

## 13. Official Java 17 references

- [JLS Java SE 17, §14.11 — The switch Statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.11): switch statements, statement groups, label rules, and control flow.
- [JLS Java SE 17, §15.28 — switch Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.28): switch expressions, result types, and exhaustiveness.
- [JLS Java SE 17, §14.21 — The yield Statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.21): how `yield` transfers a value out of a switch expression.
- [JEP 361 — Switch Expressions](https://openjdk.org/jeps/361): design motivation, arrow labels, preventing unintended fall-through, and standard status since JDK 14.
- [Java 17 Language Guide — Switch Expressions](https://docs.oracle.com/en/java/javase/17/language/switch-expressions.html): switch expression syntax guide in Java 17 documentation.
- [JEP 406 — Pattern Matching for switch (Preview)](https://openjdk.org/jeps/406): documentation distinguishing preview extensions in JDK 17 from stabilized switch expression syntax.

When writing Java 17 switch expressions, remember: **`->` labels fit independent branches returning values directly; `:` labels use statement groups and must use `yield` to produce a value.** The key point is not the symbol itself, but understanding **fall-through**, **producing a value along every path**, and the difference between a **switch expression** and a **switch statement**.
