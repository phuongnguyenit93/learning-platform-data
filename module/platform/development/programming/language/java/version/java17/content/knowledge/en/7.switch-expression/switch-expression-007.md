# No Fall-Through Rule for Arrow Form in Switch Expressions — Java 17

In Java 17, `switch` supports the arrow syntax **`case ... ->`** to select a branch. The standout feature of this syntax is **no fall-through**: when a branch matches, the program executes only the code belonging to that branch and does not automatically continue into the code of subsequent `case` branches below.

This rule applies to both forms:

- **Switch statement**: a statement that executes actions and does not necessarily return a value.
- **Switch expression**: an expression that can be assigned to a variable, returned from a method, or passed as an argument; branches must provide results according to expression rules.

This lesson focuses on the meaning of **arrow no fall-through** in Java 17, how it compares to `case:` labels, grouping branches, `yield` rules, and common errors.

## 1. What does "fall-through" mean?

In the colon syntax of `switch`, a branch can continue executing statements belonging to the next branch if there is no suitable control-transfer statement, such as `break`, `return`, or `throw`.

Example:

```java
public class ColonFallThrough {
    public static void main(String[] args) {
        int level = 1;

        switch (level) {
            case 1:
                System.out.println("Level 1");
            case 2:
                System.out.println("Level 2");
            default:
                System.out.println("Other level");
        }
    }
}
```

Output:

```text
Level 1
Level 2
Other level
```

Why did it print three lines when `level == 1`?

1. `case 1:` matched, so execution started at `println("Level 1")`.
2. There was no statement ending the branch, so flow continued down to the statement in `case 2:`.
3. It continued down into `default:` before exiting the `switch`.

The key point is that **subsequent `case` labels are not re-checked to decide whether to run** once execution has started in a branch. That is the *fall-through* effect.

Colon syntax is still supported by Java 17 and has valid use cases. However, if the goal is "each value enters exactly one branch", arrow syntax expresses that intent more directly.

## 2. Arrow form: executes only the matching branch

Rewrite the program using `->`:

```java
public class ArrowNoFallThrough {
    public static void main(String[] args) {
        int level = 1;

        switch (level) {
            case 1 -> System.out.println("Level 1");
            case 2 -> System.out.println("Level 2");
            default -> System.out.println("Other level");
        }
    }
}
```

Output:

```text
Level 1
```

When `level == 1`:

- `case 1 ->` is selected.
- `println("Level 1")` is executed.
- The switch statement ends; **`case 2` and `default` do not run**.

There is no need to add `break;` at the end of an arrow branch.

You can visualize the two styles as follows:

```text
case: branch                     case -> branch

case 1 matches                   case 1 matches
     |                                |
     v                                v
Handle case 1                    Handle case 1
     |                                |
     v                                v
Missing break? ----- Yes         Exit switch
     |                                |
     v                                v
Fall through to case 2           Statement after switch
     |
     v
May fall through to default
```

**Note:** "No fall-through" only refers to **not continuing into the next `case` branch**. After a switch statement completes, the program still executes subsequent statements following the switch as usual.

## 3. `case ... ->` syntax in a switch expression

In a **switch expression**, each arrow branch can directly supply a value:

```java
public class PriorityLabel {
    static String label(int priority) {
        return switch (priority) {
            case 1 -> "Low";
            case 2 -> "Medium";
            case 3 -> "High";
            default -> "Unknown";
        };
    }

    public static void main(String[] args) {
        System.out.println(label(1));
        System.out.println(label(2));
        System.out.println(label(3));
        System.out.println(label(99));
    }
}
```

Output:

```text
Low
Medium
High
Unknown
```

Analyzing the statement:

```java
return switch (priority) {
    case 1 -> "Low";
    case 2 -> "Medium";
    case 3 -> "High";
    default -> "Unknown";
};
```

- `switch (priority)` is **an expression**.
- Each `case ... -> "..."` defines the result of **one branch**.
- With value `1`, the expression evaluates to `"Low"`; it **does not evaluate** branch `2` or `3`.
- `return` sits **outside the switch expression**, returning the overall expression result to the caller.
- The final `;` terminates the `return switch ...;` statement.

Unlike writing code that reassigns a variable in each branch, a switch expression lets you focus directly on **the result value**.

## 4. Distinguishing arrow switch statements and arrow switch expressions

Both forms use `->` and neither has **fall-through**, yet their result requirements differ.

### 4.1. Switch statement: performing actions

```java
public class ActionDemo {
    static void execute(String action) {
        switch (action) {
            case "SAVE" -> System.out.println("Saving");
            case "DELETE" -> System.out.println("Deleting");
            default -> System.out.println("Unsupported");
        }

        System.out.println("Processing finished");
    }

    public static void main(String[] args) {
        execute("SAVE");
    }
}
```

Output:

```text
Saving
Processing finished
```

The `SAVE` branch completes without falling through to `DELETE` or `default`. Afterward, the program **still executes** `System.out.println("Processing finished")` below the switch.

A switch statement does not require every branch to return a value, and for regular `int`/`String` it can omit `default` if nothing needs to happen when no branch matches.

### 4.2. Switch expression: must produce a result

```java
public class ResultDemo {
    static String message(String action) {
        String result = switch (action) {
            case "SAVE" -> "Save selected";
            case "DELETE" -> "Delete selected";
            default -> "Unsupported";
        };

        return result;
    }

    public static void main(String[] args) {
        System.out.println(message("SAVE"));
    }
}
```

Output:

```text
Save selected
```

In a switch expression, every branch that executes normally must provide a result; you cannot simply print a message and end the branch without producing a value. A branch can also **throw an exception** instead of returning a result, as shown in later sections.

| Criterion | Arrow switch statement (`->`) | Arrow switch expression (`->`) |
| --- | --- | --- |
| Purpose | Execute statements/actions. | Compute a value. |
| Is there fall-through? | No. | No. |
| Must produce a value? | No. | Yes, on every normally completing path. |
| Need `break` to prevent fall-through? | No. | No. |
| Must cover all selector values? | Not necessarily. | Yes, the expression must be exhaustive (cover all cases). |
| Multi-statement arrow branch | Use a `{ ... }` block. | Use a `{ ... }` block and `yield` a value, or throw an exception. |

## 5. Grouping multiple values into one branch with commas

Previously, authors of `switch` might intentionally stack consecutive `case:` labels to run a shared block. With arrow syntax, write **multiple labels in a single `case`**, separated by commas.

Example, classifying days of the week:

```java
public class DayType {
    static String classify(int day) {
        return switch (day) {
            case 2, 3, 4, 5, 6 -> "Workday";
            case 7, 1 -> "Weekend";
            default -> "Invalid day";
        };
    }

    public static void main(String[] args) {
        System.out.println(classify(2));
        System.out.println(classify(7));
        System.out.println(classify(0));
    }
}
```

Output:

```text
Workday
Weekend
Invalid day
```

`case 2, 3, 4, 5, 6 ->` states that **any value in the group** selects the same branch and produces the same result.

### Why not write consecutive arrow labels to "share execution"?

Consider:

```java
return switch (day) {
    case 2 -> "Workday";
    case 3 -> "Workday";
    case 4 -> "Workday";
    default -> "Other";
};
```

This approach is **valid**, but the three branches operate independently; they do not chain together and do not fall through. When sharing behavior, grouping them as `case 2, 3, 4 -> "Workday";` is more concise.

**Wrong in intent** is expecting `case 2 ->` to execute the code in `case 3 ->`. With arrow branches, Java never automatically transitions from branch `2` into branch `3`.

### Comparing the same intent with colon style

The colon style can also group labels:

```java
String type;
switch (day) {
    case 2:
    case 3:
    case 4:
        type = "Workday";
        break;
    default:
        type = "Other";
}
```

With the arrow style, the intent "multiple values, one result" is expressed directly:

```java
String type = switch (day) {
    case 2, 3, 4 -> "Workday";
    default -> "Other";
};
```

The commas in `case 2, 3, 4` **are not fall-through**. That is a single branch with multiple labels.

## 6. Arrow branch with multiple statements: use a block and `yield`

A switch expression sometimes needs to run extra logic before producing a result. In that case, the arrow branch needs a `{ ... }` block and the **`yield`** statement.

```java
public class ShippingFee {
    static int calculateFee(String method, int weightKg) {
        if (weightKg <= 0) {
            throw new IllegalArgumentException("Weight must be positive");
        }

        return switch (method) {
            case "STANDARD" -> 20_000;

            case "EXPRESS" -> {
                int baseFee = 40_000;
                int extraFee = Math.max(0, weightKg - 1) * 5_000;
                yield baseFee + extraFee;
            }

            case "PICKUP" -> 0;

            default -> throw new IllegalArgumentException(
                    "Unsupported shipping method: " + method
            );
        };
    }

    public static void main(String[] args) {
        System.out.println(calculateFee("STANDARD", 3));
        System.out.println(calculateFee("EXPRESS", 3));
        System.out.println(calculateFee("PICKUP", 3));
    }
}
```

Output:

```text
20000
50000
0
```

In the `EXPRESS` branch:

1. Java selects the branch because `method` equals `"EXPRESS"`.
2. Executes the calculations inside the block.
3. `yield baseFee + extraFee;` supplies **the value of the entire switch expression**.
4. The `PICKUP` and `default` branches are not executed.

There are three forms worth remembering when using arrow branches in a switch expression:

```java
// 1. A single expression computing a value:
case "STANDARD" -> 20_000;

// 2. A multi-statement block and yield:
case "EXPRESS" -> {
    int fee = 40_000;
    yield fee;
}

// 3. Throwing an exception instead of a result:
default -> throw new IllegalArgumentException("Invalid method");
```

In the **short expression** form, you do not write `yield`. In the **multi-statement block** form, use `yield` to produce a value when the branch completes normally.

### `yield` ends the active branch without continuing to the next branch

Example:

```java
int score = switch (level) {
    case 1 -> {
        System.out.println("Checking level 1");
        yield 10;
    }
    case 2 -> {
        System.out.println("Checking level 2");
        yield 20;
    }
    default -> 0;
};
```

If `level == 1`, the program only prints `"Checking level 1"` and assigns `score = 10`. `yield` completes the switch expression at that branch.

Do not interpret `yield` as "proceed to the next `case`". It is a mechanism for **returning a value from a switch expression**.

## 7. `throw` branches do not fall through either

A switch expression branch can throw an exception when the input is invalid:

```java
public class Discount {
    static int percent(String category) {
        return switch (category) {
            case "REGULAR" -> 0;
            case "SILVER" -> 5;
            case "GOLD" -> 10;
            default -> throw new IllegalArgumentException(
                    "Invalid category: " + category
            );
        };
    }
}
```

If `category == "UNKNOWN"`, the `default` branch throws `IllegalArgumentException`. Execution does not continue to any other branch, nor does it receive a normal value from the expression.

For a switch expression, a `throw` branch is a helpful choice when no valid fallback result exists. Every branch that **can complete normally** must still supply a value; a branch that **always throws an exception** does not need `yield`.

## 8. No fall-through does not mean "the method has ended"

This is a common point of confusion when transitioning from `switch statement` to `switch expression`.

### Switch statement: statements after the switch still run after the matching branch

```java
static void process(int action) {
    switch (action) {
        case 1 -> System.out.println("Create");
        case 2 -> System.out.println("Edit");
        default -> System.out.println("Other");
    }

    System.out.println("Method finished");
}
```

Calling `process(1)` produces:

```text
Create
Method finished
```

There is no fall-through from `case 1` to `case 2`, **yet the statement after the switch still executes**.

### Switch expression: the expression supplies a value to the enclosing statement

```java
static String process(int action) {
    String message = switch (action) {
        case 1 -> "Create";
        case 2 -> "Edit";
        default -> "Other";
    };

    System.out.println("Action determined");
    return message;
}
```

The switch expression completes with a value; afterward, `println` and `return message` still execute. Unless a branch throws an exception, a switch expression does not itself terminate the enclosing method.

Therefore, distinguish three operations:

| Operation | Meaning |
| --- | --- |
| Ending an arrow branch | Does not run other `case` branches. |
| `yield value;` | Supplies a value and completes the switch expression. |
| `return value;` outside the switch expression | Returns a value from the method containing the switch. |

## 9. Switch expressions must cover all cases

The **no fall-through** rule is independent of another switch expression rule: **exhaustiveness** — the expression must specify how to handle every possible value in the selector's domain.

### 9.1. With `int`, `default` is usually used

**Wrong — missing handling for values other than `1` and `2`:**

```java
static String label(int level) {
    return switch (level) {
        case 1 -> "One";
        case 2 -> "Two";
        // ERROR: switch expression does not cover all int values.
    };
}
```

**Right:**

```java
static String label(int level) {
    return switch (level) {
        case 1 -> "One";
        case 2 -> "Two";
        default -> "Other";
    };
}
```

Exhaustiveness does not mean each branch must use `break`; `default` here simply provides an option for unlisted values.

### 9.2. With `enum`, all constants can be listed

```java
enum TrafficSignal {
    RED, YELLOW, GREEN
}

public class TrafficSignalDemo {
    static String instruction(TrafficSignal signal) {
        return switch (signal) {
            case RED -> "Stop";
            case YELLOW -> "Prepare to stop";
            case GREEN -> "Go";
        };
    }

    public static void main(String[] args) {
        System.out.println(instruction(TrafficSignal.RED));
    }
}
```

This example needs no `default` because the three constants `RED`, `YELLOW`, and `GREEN` are exhaustively covered. This is a useful property when the value domain is clearly modeled by an `enum`.

If a `BLUE` constant is added to the `TrafficSignal` definition and the source code above is recompiled without adding a branch, the compiler can detect that the switch expression is no longer exhaustive.

Note: `enum` exhaustiveness does not turn `null` into an enum constant; handling `null` is a separate concern.

## 10. `null` does not fall into `default`

In Java 17 with standard switch syntax and no preview features enabled, if the selector evaluates to `null`, evaluating the switch on that reference throws `NullPointerException`. The `default` branch **is not** a `null`-handling mechanism.

Example:

```java
static String classify(String code) {
    return switch (code) {
        case "A" -> "Group A";
        case "B" -> "Group B";
        default -> "Other group";
    };
}
```

Calling `classify(null)` throws `NullPointerException`; it does not return `"Other group"`.

If business rules allow `null` and require a fallback result, check before the switch:

```java
static String classify(String code) {
    if (code == null) {
        return "No code";
    }

    return switch (code) {
        case "A" -> "Group A";
        case "B" -> "Group B";
        default -> "Other group";
    };
}
```

This differs from fall-through: `null` concerns **the selector value**, whereas fall-through concerns **control flow across case branches**.

## 11. Common errors when writing arrow branches

### Error 1: Forgetting `yield` in a multi-statement block

**Wrong:**

```java
static int total(int count) {
    return switch (count) {
        case 1 -> {
            int price = 100;
            System.out.println("One product");
            // ERROR: block can complete without supplying a value.
        }
        default -> 0;
    };
}
```

**Right:**

```java
static int total(int count) {
    return switch (count) {
        case 1 -> {
            int price = 100;
            System.out.println("One product");
            yield price;
        }
        default -> 0;
    };
}
```

A switch expression must have a value on every normally completing path. When using a block to run multiple statements, `yield` is how you turn the block's result into the result of the entire expression.

### Error 2: Using `break` as if it returns a switch expression result

**Wrong:**

```java
static int score(int level) {
    return switch (level) {
        case 1 -> {
            break; // ERROR when trying to end a switch expression branch with break.
        }
        default -> 0;
    };
}
```

**Right:**

```java
static int score(int level) {
    return switch (level) {
        case 1 -> {
            yield 10;
        }
        default -> 0;
    };
}
```

`break` is not a mechanism for producing a switch expression result. With a short arrow branch, writing `case 1 -> 10;` is even cleaner.

### Error 3: Using a `void` action as an expression result

**Wrong:**

```java
static String label(int level) {
    return switch (level) {
        case 1 -> System.out.println("One"); // ERROR: println returns void.
        default -> "Other";
    };
}
```

If you only want to print to the screen, use a **switch statement**:

```java
static void printLabel(int level) {
    switch (level) {
        case 1 -> System.out.println("One");
        default -> System.out.println("Other");
    }
}
```

If you want both to print and to produce a result, use a **block and `yield`**:

```java
static String label(int level) {
    return switch (level) {
        case 1 -> {
            System.out.println("One");
            yield "LEVEL_1";
        }
        default -> "Other";
    };
}
```

### Error 4: Mixing colons and arrows in the same switch block

**Wrong:**

```java
static String describe(int value) {
    return switch (value) {
        case 1 -> "One";
        case 2:
            yield "Two";  // ERROR: mixing two label styles in the same switch.
        default -> "Other";
    };
}
```

**Right — consistently use arrows:**

```java
static String describe(int value) {
    return switch (value) {
        case 1 -> "One";
        case 2 -> "Two";
        default -> "Other";
    };
}
```

Java allows **two different switch block styles**, but you cannot mix `case ...:` and `case ... ->` inside **the same switch block**.

### Error 5: Assuming the next branch will finish what is missing

**Wrong in design:**

```java
static String result(int value) {
    return switch (value) {
        case 1 -> "A";
        case 2 -> "B";
        default -> "C";
    };
}
```

The snippet above **compiles**, but if someone expects `value == 1` to yield a combined `"AB"` by running both `case 1` and `case 2`, that is a misconception. The result is only `"A"`.

If multiple values should share the result `"AB"`:

```java
static String result(int value) {
    return switch (value) {
        case 1, 2 -> "AB";
        default -> "C";
    };
}
```

If one branch needs multiple operations before producing a result, put them **inside the same block** and finish with `yield`.

### Error 6: Each branch returning a type incompatible with the call site

**Wrong:**

```java
static int statusCode(int code) {
    return switch (code) {
        case 1 -> 200;
        case 2 -> "400"; // ERROR: String cannot be returned as int.
        default -> 500;
    };
}
```

**Right:**

```java
static int statusCode(int code) {
    return switch (code) {
        case 1 -> 200;
        case 2 -> 400;
        default -> 500;
    };
}
```

A switch expression is a **typed expression**. Branch values must match the type expected where the expression is used in that context. Type errors differ from fall-through errors, though they often arise when converting switch statements into switch expressions.

### Error 7: Having a path that fails to supply `yield`

**Wrong:**

```java
static int calculate(int level, boolean premium) {
    return switch (level) {
        case 1 -> {
            if (premium) {
                yield 100;
            }
            // ERROR: when premium == false the block ends without a value.
        }
        default -> 0;
    };
}
```

**Right:**

```java
static int calculate(int level, boolean premium) {
    return switch (level) {
        case 1 -> {
            if (premium) {
                yield 100;
            }
            yield 50;
        }
        default -> 0;
    };
}
```

When checking how a block branch terminates, examine **every possible path**, not just the common one.

## 12. Real-world example: computing order status with a switch expression

Suppose an application has order statuses:

```java
enum OrderStatus {
    NEW,
    PROCESSING,
    SHIPPED,
    DELIVERED,
    CANCELLED
}
```

We want to map each status to a short message. One status may require multiple calculation statements before returning a result. Below is a complete example using strictly standard Java 17 syntax.

Create file `OrderStatusDemo.java`:

```java
enum OrderStatus {
    NEW,
    PROCESSING,
    SHIPPED,
    DELIVERED,
    CANCELLED
}

public class OrderStatusDemo {

    static String describe(OrderStatus status, int daysInTransit) {
        if (status == null) {
            throw new IllegalArgumentException("status cannot be null");
        }

        return switch (status) {
            case NEW -> "New order";
            case PROCESSING -> "Processing";

            case SHIPPED -> {
                if (daysInTransit < 0) {
                    throw new IllegalArgumentException(
                            "Days in transit cannot be negative"
                    );
                }

                String suffix = daysInTransit == 0
                        ? "just dispatched"
                        : "in transit for " + daysInTransit + " day(s)";

                yield "Shipping - " + suffix;
            }

            case DELIVERED -> "Delivered";
            case CANCELLED -> "Cancelled";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(OrderStatus.NEW, 0));
        System.out.println(describe(OrderStatus.SHIPPED, 2));
        System.out.println(describe(OrderStatus.DELIVERED, 0));
    }
}
```

Compile and run:

```bash
javac --release 17 -encoding UTF-8 OrderStatusDemo.java
java OrderStatusDemo
```

Expected output:

```text
New order
Shipping - in transit for 2 day(s)
Delivered
```

Here:

1. `NEW` and `PROCESSING` use short expression branches.
2. `SHIPPED` uses a multi-statement block and `yield`s the final result.
3. The error path in `SHIPPED` uses `throw`.
4. `DELIVERED` and `CANCELLED` are independent branches; no `break` is needed.
5. All constants of `OrderStatus` are listed, so the switch expression is exhaustive without `default`.

If `status == OrderStatus.NEW`, the expression returns `"New order"`; it **does not execute the `SHIPPED` block** even though that block appears later in the source code.

## 13. When should arrow branches be used instead of colons?

Arrow syntax is especially well suited when **each case has its own behavior or result**:

- Mapping a numeric code or `enum` to a message.
- Selecting configuration, priority, fee tier, or display format.
- Classifying the state of a workflow.
- Invoking a distinct action per command type without risking accidentally running another action.
- Simplifying `switch` code that previously had to assign a temporary variable and add `break` in multiple branches.

Colon syntax remains part of Java 17, including in switch expressions when following `yield` rules. Still, if you simply need to group multiple values for shared handling, `case A, B ->` usually communicates intent better than stacking consecutive `case:` labels.

Syntax choice depends on intent, but **do not mix the two label styles within the same switch block**.

## 14. Self-practice exercises

### Exercise 1 — Predict the execution flow

Read the snippet:

```java
int code = 2;

switch (code) {
    case 1 -> System.out.println("A");
    case 2 -> System.out.println("B");
    case 3 -> System.out.println("C");
    default -> System.out.println("D");
}

System.out.println("END");
```

Write down the printed lines and explain why the program does not print `"C"` or `"D"`.

**Answer check:**

```text
B
END
```

`case 2` matches and terminates the switch statement. The `END` line belongs to the statement after the switch, so it still executes.

### Exercise 2 — Grouping branches

Write the method:

```java
static String rate(int score) {
    // Use a switch expression with arrow style.
}
```

Requirements:

| `score` | Result |
| --- | --- |
| `1` or `2` | `"Needs improvement"` |
| `3` or `4` | `"Pass"` |
| `5` | `"Good"` |
| Other | `"Invalid"` |

**Reference answer:**

```java
static String rate(int score) {
    return switch (score) {
        case 1, 2 -> "Needs improvement";
        case 3, 4 -> "Pass";
        case 5 -> "Good";
        default -> "Invalid";
    };
}
```

### Exercise 3 — Convert a branch into a multi-statement block

Given the code:

```java
static int calculate(int category) {
    return switch (category) {
        case 1 -> 100;
        case 2 -> 200;
        default -> 0;
    };
}
```

Modify `case 2` to:

1. Declare `int base = 150;`.
2. Declare `int extra = 50;`.
3. Return the sum of the two variables using `yield`.

**Reference answer:**

```java
static int calculate(int category) {
    return switch (category) {
        case 1 -> 100;
        case 2 -> {
            int base = 150;
            int extra = 50;
            yield base + extra;
        }
        default -> 0;
    };
}
```

### Exercise 4 — Distinguish errors between switch statement and switch expression

Consider the two ways of writing:

```java
// A: switch statement
switch (value) {
    case 1 -> System.out.println("One");
    default -> System.out.println("Other");
}
```

```java
// B: switch expression
String text = switch (value) {
    case 1 -> System.out.println("One");
    default -> "Other";
};
```

Determine which one is valid and explain **why using `println` in an arrow branch differs between the two forms**. Propose a fix for B using a `yield` block to both print the message and produce the `String` value.

**Reference answer for B:**

```java
String text = switch (value) {
    case 1 -> {
        System.out.println("One");
        yield "One";
    }
    default -> "Other";
};
```

Switch statement A uses `println` as an action, whereas switch expression B requires a `String` result from the selected branch.

### Exercise 5 — Handling null and exhaustiveness

Write `String message(String status)`, with the requirements:

- If `status == null`, return `"Missing status"` before entering the switch.
- If `status` is `"OK"`, return `"Success"`.
- If `status` is `"ERROR"`, return `"Failure"`.
- Any other value returns `"Unknown"`.

**Reference answer:**

```java
static String message(String status) {
    if (status == null) {
        return "Missing status";
    }

    return switch (status) {
        case "OK" -> "Success";
        case "ERROR" -> "Failure";
        default -> "Unknown";
    };
}
```

## 15. Quick cheat sheet

| Scenario | Recommended syntax | Key note |
| --- | --- | --- |
| Branch immediately returns a value | `case 1 -> "One";` | This value is the switch expression's result, no `yield` needed. |
| Multiple values handled the same way | `case 1, 2, 3 -> "Group A";` | Labels in the same branch, no fall-through. |
| Branch needs multiple statements | `case 1 -> { ...; yield value; }` | `yield` supplies the result when the block completes normally. |
| Branch rejects invalid input | `default -> throw new IllegalArgumentException(...);` | Throws an exception; no normal value needs to be produced. |
| Only executing actions | `switch (x) { case 1 -> doWork(); ... }` | This is a switch statement, does not need to produce a value. |
| Assigning a value to a variable | `String s = switch (x) { ... };` | This is a switch expression, must be exhaustive. |
| Handling `null` in standard Java 17 | Check `null` before the switch. | `default` does not catch `null`. |
| Avoiding "fall-through" bugs | Use `case ... ->` and do not expect execution to continue to the next branch. | No `break` needed to prevent fall-through. |

**Core principle:** When writing `case ... ->` in Java 17, **one selection executes only one branch**. In a switch expression, that branch either produces a value directly, runs a block with `yield`, or throws an exception. Thanks to the no-fall-through rule, you can read an arrow switch with the straightforward intent "for this value, do this", without tracing `break` statements to figure out where a branch stops.
