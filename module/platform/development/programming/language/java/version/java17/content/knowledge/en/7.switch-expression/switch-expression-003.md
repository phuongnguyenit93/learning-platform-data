# Multiple Constants in a Single `case` Label of a `switch expression` — Java 17

## 1. Lesson objective

When multiple input values need to produce **the same result**, writing a separate `case` branch for each value makes code repetitive and harder to follow. In Java 17, a single `case` label can **list multiple constants, separated by commas**. All constants in the same label lead to **a single expression or a shared processing block**.

Example:

```java
int numberOfDays = switch (month) {
    case 4, 6, 9, 11 -> 30;
    case 2 -> 28;
    default -> 31;
};
```

Here, if `month` is `4`, `6`, `9`, or `11`, the `switch` expression returns `30`. The author states the rule "these four months have the same number of days" once, instead of duplicating four identical branches.

The example above only illustrates **the multi-constant grouping syntax**; a real calendar problem must handle February in leap years and validate that the month is within `1..12`. For calendar domain logic, `java.time` APIs like `Month` or `YearMonth` are usually more suitable than a self-managed constant table.

After this lesson, learners should be able to:

1. Write `case A, B, C -> value` in a `switch expression`.
2. Explain why the listed values share one branch without *fall-through*.
3. Distinguish constant grouping in a `switch expression` from stacking multiple `case` labels in a `switch statement`.
4. Use constant grouping with `int`, `String`, `enum`, and other selector types supported by Java 17.
5. Combine multi-constant labels with expressions, `yield` blocks, `throw`, and `default`, while recognizing duplicate label errors and invalid constants.

**Version scope:** `switch expression` has been a standard feature since Java 14 (JEP 361). Multi-constant syntax in a single `case` label is used directly in Java 17 without enabling preview features.

## 2. Core syntax: `case A, B, C -> ...`

Common structure:

```java
ResultType result = switch (selector) {
    case CONSTANT_1, CONSTANT_2, CONSTANT_3 -> resultExpression;
    case CONSTANT_4 -> anotherExpression;
    default -> fallbackExpression;
};
```

Meaning of each component:

| Component | Role |
|---|---|
| `selector` | Value tested to choose a `switch` branch. |
| `case CONSTANT_1, CONSTANT_2, CONSTANT_3` | A single label containing multiple **alternative constants**; matching any constant selects the same branch. |
| Comma `,` | Separates constants in a label, meaning an **or** choice among the values. |
| `->` | Introduces the branch rule; does not automatically fall through to another branch. |
| `resultExpression` | Value that this branch provides to the `switch expression`. |
| `default` | Fallback branch when no constant label matches; usually required for `int` or `String`. |
| `;` after `}` | Terminates the assignment or declaration statement using the `switch expression`. |

The comma only groups **constants sharing the same behavior**. It does not create an array, does not create a collection, and does not mean a condition must simultaneously match all values.

Example:

```java
static String classify(int code) {
    return switch (code) {
        case 200, 201, 204 -> "Success";
        case 400, 401, 403, 404 -> "Request error";
        case 500, 502, 503 -> "Server error";
        default -> "Other code";
    };
}
```

The method above returns a `String` for any `int` input. With `code == 201`, Java immediately selects the `case 200, 201, 204` branch and evaluates `"Success"`.

## 3. Semantics: multiple values, one rule

A `case` group often expresses a **behavioral equivalence class**. Input values differ, yet they are handled by a single policy.

Priority level example:

```java
enum Priority {
    CRITICAL, HIGH, MEDIUM, LOW, INFO
}

static int responseHours(Priority priority) {
    return switch (priority) {
        case CRITICAL, HIGH -> 2;
        case MEDIUM -> 8;
        case LOW, INFO -> 24;
    };
}
```

The business groupings are clear:

- `CRITICAL` and `HIGH` belong to the group requiring a response within 2 hours.
- `MEDIUM` has an 8-hour SLA.
- `LOW` and `INFO` have a 24-hour SLA.

With this `enum`, every constant is handled, so the `switch expression` is already **exhaustive** without needing `default`. If the priority set later changes, the compiler can help detect unhandled cases when the code is recompiled.

### 3.1. The comma means "or", not a compound condition

In:

```java
case CRITICAL, HIGH -> 2;
```

`CRITICAL` and `HIGH` are two **alternative values**: the selector only needs to equal one of them. It is impossible for an enum variable to simultaneously equal both `CRITICAL` and `HIGH`.

If you want to combine **another condition** such as workdays, quantity, or a runtime threshold, put that logic inside the branch or before the `switch`:

```java
static int responseHours(Priority priority, boolean weekend) {
    return switch (priority) {
        case CRITICAL, HIGH -> weekend ? 4 : 2;
        case MEDIUM -> 8;
        case LOW, INFO -> 24;
    };
}
```

Elements in the `case` list must still be valid constants, not arbitrary boolean expressions.

### 3.2. No fall-through when using `->`

Consider the following:

```java
String kind = switch (letter) {
    case 'a', 'e', 'i', 'o', 'u' -> "Lowercase vowel";
    default -> "Other";
};
```

When `letter == 'a'`, the result is `"Lowercase vowel"`. Java **does not continue** into the `default` branch; no `break` is needed at the end of an arrow branch.

This makes grouping multiple constants in a `case` label clearer than stacking consecutive labels with colons. It directly expresses that a set of values shares the same behavior.

## 4. Grouping constants with common selector types

Java 17 supports traditional `switch` with `byte`, `short`, `char`, `int` and their corresponding wrappers, `String`, and `enum`. Every `case` label must match the selector type and Java's constant rules.

### 4.1. Integer values

```java
static String ticketCategory(int priorityCode) {
    return switch (priorityCode) {
        case 1, 2 -> "High priority";
        case 3, 4 -> "Normal priority";
        case 5 -> "Low priority";
        default -> throw new IllegalArgumentException(
                "Unknown priority code: " + priorityCode);
    };
}
```

This is an example of **discrete values**. The list `1, 2` does not automatically generalize into a numeric range.

When checking **a dynamic or wide range**, `if`/`else if` can be easier to read than listing dozens of constants:

```java
static String temperatureBand(int celsius) {
    if (celsius < 10) {
        return "Cold";
    }
    if (celsius < 30) {
        return "Moderate";
    }
    return "Hot";
}
```

Java 17 does not have syntax like `case 1..10 ->` for numeric ranges in a `switch expression`.

### 4.2. `String` values

```java
static String commandGroup(String command) {
    return switch (command) {
        case "START", "RUN", "RESUME" -> "Execute";
        case "STOP", "QUIT", "EXIT" -> "Stop";
        case "STATUS", "INFO" -> "Check status";
        default -> "Unsupported command";
    };
}
```

Strings must match **exactly** in content and letter case. For instance, `"run"` does not automatically match `"RUN"`.

When the problem requires case-insensitivity, normalize once before the `switch`:

```java
static String commandGroupIgnoreCase(String command) {
    String normalized = java.util.Objects.requireNonNull(command, "command")
            .strip()
            .toUpperCase(java.util.Locale.ROOT);

    return switch (normalized) {
        case "START", "RUN", "RESUME" -> "Execute";
        case "STOP", "QUIT", "EXIT" -> "Stop";
        case "STATUS", "INFO" -> "Check status";
        default -> "Unsupported command";
    };
}
```

Normalization should match the system contract. `Locale.ROOT` is suitable for technical command codes independent of the user's locale.

**Note on null:** with a standard Java 17 `switch` using `String`, a `null` selector throws `NullPointerException`; the `default` branch does not automatically treat `null` as an unknown command. You can explicitly require non-null, such as via `Objects.requireNonNull`, or handle `null` before the `switch`.

### 4.3. `enum` constants

```java
enum OrderStatus {
    CREATED, CONFIRMED, PACKING, SHIPPING, DELIVERED, CANCELED
}

static String statusGroup(OrderStatus status) {
    return switch (status) {
        case CREATED, CONFIRMED -> "Pending";
        case PACKING, SHIPPING -> "In progress";
        case DELIVERED -> "Completed";
        case CANCELED -> "Canceled";
    };
}
```

In a `switch` with a selector of type `OrderStatus`, constants in `case` are written using **unqualified simple names** like `CREATED`, `CONFIRMED`. In Java 17, you do not write `case OrderStatus.CREATED, OrderStatus.CONFIRMED ->` in an `enum switch` context like the one above.

If `status` is `null`, it matches no enum constant, and `switch` throws `NullPointerException` in standard Java 17.

### 4.4. `char` constants

```java
static boolean isVowel(char c) {
    return switch (c) {
        case 'a', 'e', 'i', 'o', 'u',
             'A', 'E', 'I', 'O', 'U' -> true;
        default -> false;
    };
}
```

You can wrap lines between constants for readability. A trailing comma on a line still indicates they belong to **the same `case` label** and lead to `true`.

This example only recognizes the five basic vowels in the Latin alphabet; it is not an algorithm for classifying all Unicode vowel characters.

## 5. Constants in `case` must be valid at compile time

Multiple constants do not mean you can write any variable or runtime-evaluated expression in a `case` list. For `int`, `char`, and `String`, normal `case` labels must be compatible **constant expressions**. For an `enum` selector, labels must be corresponding enum constants.

Example:

```java
public class Codes {
    static final int ACCEPTED = 202;
    static final int NO_CONTENT = 204;

    static String describe(int code) {
        return switch (code) {
            case ACCEPTED, NO_CONTENT -> "Valid";
            default -> "Other";
        };
    }
}
```

`ACCEPTED` and `NO_CONTENT` are **constant variables** whose integer values are determined at compile time, so they can be used as case constants.

Conversely:

```java
static int calculateCode() {
    return 202;
}

static String invalid(int code) {
    int runtimeCode = calculateCode();
    return switch (code) {
        // case runtimeCode, 204 -> "Valid"; // Error: runtimeCode is not a constant expression.
        case 204 -> "Valid";
        default -> "Other";
    };
}
```

Even though at runtime `runtimeCode` holds `202`, the `case` label rule requires **a compile-time constant**, not a variable whose value happens not to change during a single execution.

For strings, constant expressions formed by concatenating literals can be valid:

```java
static final String CMD_PREFIX = "RE";
static final String RESTART = CMD_PREFIX + "START";

static String action(String cmd) {
    return switch (cmd) {
        case RESTART, "RUN" -> "Start";
        default -> "Other";
    };
}
```

`RESTART` is a `String` constant computed at compile time. It cannot be replaced by a string read from a configuration file or a regular method call to create labels that vary at runtime.

## 6. Avoiding duplicate constant labels

Within the same `switch` block, **a constant value must not appear in multiple labels**, even across different groups.

**Invalid** example:

```java
static String bad(int code) {
    return switch (code) {
        case 1, 2 -> "Group A";
        // case 2, 3 -> "Group B"; // Duplicate value 2 error.
        case 3 -> "Group B";
        default -> "Other";
    };
}
```

Putting the same value in two branches does not mean Java will pick the earlier branch. It is a design error that the compiler catches.

Even within a single label, constants should not be repeated:

```java
// case 1, 1 -> "Duplicate"; // Error: duplicate label.
```

Two constants with different names but **the same compile-time value** also cause a duplicate error:

```java
static final int OK = 200;
static final int SUCCESS = 200;

static String badStatus(int code) {
    return switch (code) {
        // case OK, SUCCESS -> "Success"; // Error: both have value 200.
        case OK -> "Success";
        default -> "Other";
    };
}
```

Therefore, before grouping constants, clearly determine that **each input value belongs to exactly one processing group**.

## 7. Result of a case group: expressions, `yield`, and `throw`

A multi-constant label is not restricted to returning literals. The right-hand side of `->` in a `switch expression` can be an **expression**, a **block**, or a **`throw`** according to Java syntax.

### 7.1. Branch returning an expression

```java
static int retryCount(int status) {
    return switch (status) {
        case 429, 502, 503, 504 -> 3;
        case 400, 401, 403 -> 0;
        default -> 1;
    };
}
```

This style works well when multiple constants lead to **a simple result value**. Real retry policies also depend on request safety, timeouts, and system retry budgets; the example above merely illustrates branch grouping syntax.

### 7.2. Branch needing multiple statements: use a block with `yield`

When calculations are needed before producing a value:

```java
static String deliveryMessage(String option, int distanceKm) {
    if (distanceKm < 0) {
        throw new IllegalArgumentException("distanceKm must be non-negative");
    }

    return switch (option) {
        case "EXPRESS", "PRIORITY" -> {
            int estimatedDays = distanceKm <= 30 ? 1 : 2;
            yield "Express delivery: " + estimatedDays + " day(s)";
        }
        case "STANDARD", "ECONOMY" -> {
            int estimatedDays = distanceKm <= 30 ? 3 : 5;
            yield "Standard delivery: " + estimatedDays + " day(s)";
        }
        default -> throw new IllegalArgumentException("Unknown option: " + option);
    };
}
```

With a block branch, `yield` provides the value for **the enclosing `switch expression`**. `yield` is neither `break` nor a method `return`.

Comparison:

- `return` terminates the currently executing method.
- `yield` terminates a branch of the `switch expression` and provides the result for that expression itself.
- `break` is mainly used to exit a colon-style `switch statement`, not to return a value for a `switch expression`.

Branches can use different ways of producing results as long as the overall expression has a compatible result type. Do not add `yield` when the right-hand side of `->` is already a single expression like `-> 3`.

### 7.3. Branch throwing an exception

If a group of input values is invalid in the business domain, an exception can be thrown:

```java
static String route(int kind) {
    return switch (kind) {
        case 1, 2 -> "Priority route";
        case 3 -> "Standard route";
        case -1, 0 -> throw new IllegalArgumentException(
                "kind must be positive");
        default -> "Fallback route";
    };
}
```

A `throw` branch does not produce a normal value because execution ends abruptly. It is still a valid branch of a `switch expression`.

## 8. `switch expression` vs. `switch statement`: how does case grouping differ?

Java 17 supports both `switch expression` and `switch statement`.

- An **expression** produces **a value** to assign, pass as an argument, or `return`.
- A **statement** performs actions by branch; it does not itself produce a value for an enclosing expression.

In both forms, arrow rules can group multiple constants with commas.

### 8.1. Switch expression: returning a value

```java
static String dayType(java.time.DayOfWeek day) {
    return switch (day) {
        case SATURDAY, SUNDAY -> "Weekend";
        case MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY -> "Workday";
    };
}
```

The `case SATURDAY, SUNDAY` branch produces the same string for both days. Because it uses `return switch (...)`, this is a **switch expression**.

### 8.2. Switch statement: performing actions

```java
static void printDayType(java.time.DayOfWeek day) {
    switch (day) {
        case SATURDAY, SUNDAY -> System.out.println("Weekend");
        case MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY ->
                System.out.println("Workday");
    }
}
```

This is a **switch statement**. Even though it uses `->`, it does not need to return a value, because the entire `switch` is used as a statement.

Do not infer that "having `->` definitely means a switch expression". The usage context and result requirement determine whether `switch` is a statement or an expression.

### 8.3. Colon syntax of the traditional switch

In a switch statement, the older style uses stacked labels and `break` to share handling:

```java
static String olderStyle(int code) {
    String label;
    switch (code) {
        case 1:
        case 2:
            label = "Group A";
            break;
        case 3:
        case 4:
            label = "Group B";
            break;
        default:
            label = "Other";
    }
    return label;
}
```

In this style, multiple labels `case 1:` and `case 2:` share handling because the labels are placed before the same statement block. If `break` is forgotten in required places, code can **fall through** into the next branch.

Equivalent switch expression using arrows:

```java
static String expressionStyle(int code) {
    return switch (code) {
        case 1, 2 -> "Group A";
        case 3, 4 -> "Group B";
        default -> "Other";
    };
}
```

The arrow version directly shows the relationship **same output value → same branch** with no fall-through. When writing a new value-to-value mapping, this style is generally preferable.

Java 17 also allows using `:` together with `yield` inside a switch expression, though that is a different syntax style. Within a single `switch`, you cannot arbitrarily mix colon (`:`) and arrow (`->`) label styles.

## 9. Exhaustiveness of a `switch expression`

A `switch expression` must handle every possible case according to Java's coverage rules (*exhaustiveness*).

### 9.1. With `int` and `String`

You cannot finitely list every `int` value or every string, so `default` is usually needed:

```java
static String classify(int code) {
    return switch (code) {
        case 1, 2 -> "Group A";
        case 3, 4 -> "Group B";
        default -> "Unclassified";
    };
}
```

`default` runs only when no constant matches. Do not use `default` to hide data errors if business rules require rejecting invalid inputs; in that case write `default -> throw new IllegalArgumentException(...)`.

### 9.2. With `enum`

If all enum constants are listed, `default` can be omitted:

```java
enum Stage { NEW, QUEUED, RUNNING, FINISHED, FAILED }

static String stageGroup(Stage stage) {
    return switch (stage) {
        case NEW, QUEUED -> "Pending";
        case RUNNING -> "Running";
        case FINISHED, FAILED -> "Ended";
    };
}
```

If a new enum constant is added and the code using the enum is recompiled, the compiler can require updating the `switch expression` to remain exhaustive. This is a benefit of **explicitly listing groups** instead of always adding `default` when the value domain is closed.

Each enum constant must appear **at most once**. A group can contain one or more constants, but it cannot include a constant already used in another group.

### 9.3. `default` does not mean handling `null`

With `String`, a wrapper, or an `enum` as selector, a standard Java 17 `switch` does not route `null` into `default`.

```java
static String classifyNullable(String value) {
    if (value == null) {
        return "No data";
    }
    return switch (value) {
        case "A", "B" -> "First group";
        default -> "Other group";
    };
}
```

This code handles `null` **before** calling `switch`. The `case null` syntax belongs to pattern matching for switch extensions in later versions, and **is not default stable switch expression syntax in Java 17**. Do not rely on it in exercises targeting Java 17.

## 10. Complete integrated example running on Java 17

The small application below groups order types into handling groups and maps shipping codes to fee tiers. The groups use both `enum` and `String`, demonstrating real-world scenarios where multiple constants lead to a single result.

Create file `Main.java`:

```java
import java.util.Locale;
import java.util.Objects;

public class Main {
    enum OrderStatus {
        CREATED, CONFIRMED, PACKING, SHIPPING, DELIVERED, CANCELED
    }

    static String statusGroup(OrderStatus status) {
        return switch (Objects.requireNonNull(status, "status")) {
            case CREATED, CONFIRMED -> "Pending";
            case PACKING, SHIPPING -> "In progress";
            case DELIVERED -> "Completed";
            case CANCELED -> "Canceled";
        };
    }

    static int shippingFeeCents(String service) {
        String normalized = Objects.requireNonNull(service, "service")
                .strip()
                .toUpperCase(Locale.ROOT);

        return switch (normalized) {
            case "EXPRESS", "PRIORITY" -> 1500;
            case "STANDARD" -> 500;
            case "ECONOMY", "FREE" -> 0;
            default -> throw new IllegalArgumentException(
                    "Unknown service: " + service);
        };
    }

    static String message(int count) {
        return switch (count) {
            case 0 -> "No orders";
            case 1, 2, 3 -> "Few orders";
            default -> {
                if (count < 0) {
                    throw new IllegalArgumentException("count must be non-negative");
                }
                yield count + " orders";
            }
        };
    }

    public static void main(String[] args) {
        System.out.println(statusGroup(OrderStatus.CREATED));
        System.out.println(statusGroup(OrderStatus.SHIPPING));
        System.out.println(shippingFeeCents(" priority "));
        System.out.println(shippingFeeCents("FREE"));
        System.out.println(message(2));
        System.out.println(message(5));
    }
}
```

Compile and run:

```bash
javac --release 17 -encoding UTF-8 Main.java
java Main
```

Output:

```text
Pending
In progress
1500
0
Few orders
5 orders
```

Key takeaways to read in the code:

1. `case CREATED, CONFIRMED ->` selects one result for two enum constants.
2. `case "EXPRESS", "PRIORITY" ->` groups two string service codes; input normalization happens before `switch`.
3. `case "ECONOMY", "FREE" -> 0` avoids writing two branches returning the same value.
4. `case 1, 2, 3 ->` groups multiple `int` constants into one branch.
5. The `default` branch in `message` is a block using `yield` to produce a result, while also able to throw an exception for `count < 0`.
6. Every `switch` in the example returns a value for valid cases; no `break` is needed in arrow branches.

This is an example of syntax and code structure; in a real system, fee tables and status groups should come from verified business rules, with proper tests and change management.

## 11. Common errors

### 11.1. Forgetting commas between constants

Wrong:

```java
// case 1 2 3 -> "One group"; // Missing commas.
```

Right:

```java
case 1, 2, 3 -> "One group";
```

The right snippet is **one label** with three constants.

### 11.2. Using the `||` operator in a label

Wrong:

```java
// case 1 || 2 -> "One group"; // Not how a list of case constants is written.
```

Right:

```java
case 1, 2 -> "One group";
```

Inside a `case`, constants are listed with commas, not joined with boolean operators.

### 11.3. Using runtime variables instead of constants

Wrong:

```java
int target = readCode();
// case target, 2 -> ... // target is not a constant expression.
```

When codes are predefined, use literals or valid constant variables. If the list of values is loaded **dynamically** from configuration, you can use `Set.contains`, `Map.get`, or regular conditions instead of trying to turn runtime data into `case` constants.

### 11.4. Duplicate values across multiple groups

Wrong:

```java
// case 1, 2 -> "A";
// case 2, 3 -> "B"; // 2 is duplicated.
```

Design disjoint groups, clearly determine the policy for each value, and assign each constant to a unique label.

### 11.5. Using `break` instead of `yield` in a switch expression block

Wrong in intent:

```java
// return switch (code) {
//     case 1, 2 -> {
//         int value = code * 10;
//         break; // Does not provide a result for the switch expression.
//     }
//     default -> 0;
// };
```

Right:

```java
return switch (code) {
    case 1, 2 -> {
        int value = code * 10;
        yield value;
    }
    default -> 0;
};
```

### 11.6. Forgetting a fallback branch for a switch expression

If the selector is `int` and only `case 1, 2` is present, the expression does not handle remaining values. Add a valid `default` branch or redesign the value domain so the compiler verifies complete branch coverage.

### 11.7. Confusing multi-constant grouping with pattern matching for switch

`case 1, 2 ->` only groups **specific constants**. It is not a type check, has no guard, and does not destructure data from a record. Pattern matching for `switch` is not a default stabilized feature in Java 17; examples like `case String s` or `case Point(int x, int y)` in newer Java documentation are not part of this lesson's standard syntax.

## 12. Practice exercises

### Exercise 1 — Group months by quarter

Write a method `quarter(int month)` returning `"Q1"`, `"Q2"`, `"Q3"`, `"Q4"` for months 1 through 12. If the month is invalid, throw `IllegalArgumentException`.

One solution:

```java
static String quarter(int month) {
    return switch (month) {
        case 1, 2, 3 -> "Q1";
        case 4, 5, 6 -> "Q2";
        case 7, 8, 9 -> "Q3";
        case 10, 11, 12 -> "Q4";
        default -> throw new IllegalArgumentException(
                "Invalid month: " + month);
    };
}
```

In each label, three months share the same result; there are no duplicate labels and all other `int` values are rejected.

### Exercise 2 — Group job states

Suppose there is an enum:

```java
enum JobState { WAITING, RETRYING, RUNNING, SUCCESS, FAILED, CANCELED }
```

Write `group(JobState state)` such that `WAITING` and `RETRYING` return `"Waiting"`; `RUNNING` returns `"Running"`; `SUCCESS`, `FAILED`, `CANCELED` return `"Ended"`.

Solution:

```java
static String group(JobState state) {
    return switch (state) {
        case WAITING, RETRYING -> "Waiting";
        case RUNNING -> "Running";
        case SUCCESS, FAILED, CANCELED -> "Ended";
    };
}
```

No `default` is needed because all six enum constants are covered. If the application does not allow `null`, clarify the parameter contract or add a non-null check before the switch.

### Exercise 3 — Predict the output

```java
static int points(String grade) {
    return switch (grade) {
        case "A+", "A" -> 4;
        case "B+", "B" -> 3;
        case "C+", "C" -> 2;
        default -> 0;
    };
}
```

Predict `points("A")`, `points("B+")`, `points("c")`, and `points("D")`.

Corresponding answers: `4`, `3`, `0`, `0`. `"c"` does not match `"C"` because `String` comparison in `switch` is case-sensitive.

### Exercise 4 — Fix the `break` error

Consider a version wanting to return a string after handling two codes:

```java
// return switch (code) {
//     case 10, 11 -> {
//         String label = "Accepted";
//         break;
//     }
//     default -> "Other";
// };
```

Fix by replacing `break` with `yield label;` inside the block. Explanation: this is a switch **expression** and must provide a value for the expression.

### Exercise 5 — Handling dynamic input

Suppose `Set<Integer> blockedCodes` is loaded from configuration at runtime. Can you write `case blockedCodes -> ...` or list the elements of the set as case constants?

No: runtime values do not satisfy constant case label rules. A suitable approach:

```java
static String decide(int code, java.util.Set<Integer> blockedCodes) {
    if (blockedCodes.contains(code)) {
        return "Blocked";
    }
    return switch (code) {
        case 200, 201 -> "Accepted";
        case 404 -> "Not found";
        default -> "Other";
    };
}
```

The example demonstrates using `switch` with **fixed constants** and using a collection when the condition set **varies at runtime**.

## 13. Completion criteria

Learners have mastered "multiple constants in a single `case` label" when they can independently accomplish these tasks:

1. Write `case A, B, C -> expression` and accurately explain that matching **any one of the three constants** enters the same branch.
2. Convert a `switch statement` with repeated stacked colon labels into a `switch expression` with constant grouping and equivalent results.
3. Use constant grouping with `int`, `String`, and `enum` selectors; state the compile-time constant requirement and the difference between enum constants and string literals.
4. Explain why `->` branches do not fall through and do not need `break`.
5. Correctly write a block branch with multiple statements and `yield`, or a `throw` branch when input is invalid.
6. Spot duplicate labels, runtime variables used as case labels, and missing `default` branches in expressions over open value types.
7. Proactively handle `null` for `String`/`enum` according to Java 17 semantics.
8. Compile programs using `javac --release 17` without using preview syntax or syntax available only in newer Java versions.

## 14. Official documentation

- [OpenJDK JEP 361 — Switch Expressions](https://openjdk.org/jeps/361): design rationale, arrow rules, grouping case constants, and `yield`.
- [Java Language Specification SE 17 — Switch Statements (§14.11)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.11): grammar and behavior of switch statements.
- [Java Language Specification SE 17 — Switch Expressions (§15.28)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.28): how a switch expression selects a branch and produces a result.
- [Java SE 17 API — `java.time.Month`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Month.html): standard enum example usable with switch, helpful when working with calendar months.

**Remember:** `case A, B, C -> result` is **one label with multiple input choices** and **one shared handling rule**. It is a concise, clear, and stable way in Java 17 to express discrete values that share the same outcome.
