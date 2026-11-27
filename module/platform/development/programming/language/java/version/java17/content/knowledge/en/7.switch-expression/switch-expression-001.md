# Distinguishing `switch statement` and `switch expression` in Java 17

**Topic:** Java 17  
**Chapter:** Switch expression  
**Lesson:** Distinguishing switch statement and switch expression

In Java 17, the `switch` keyword can create either **a control-flow statement** (*switch statement*) or **an expression that produces a value** (*switch expression*). Both forms share many syntactic parts such as `case`, `default`, the colon `:`, and the arrow `->`, but they differ in purpose, result, how branches terminate, and case coverage requirements.

Key points to grasp from the start:

- **`switch statement`:** Selects and executes statements. The `switch` itself has no return value.
- **`switch expression`:** Selects a branch and **produces a value** to assign to a variable, return from a method, or use inside a larger expression.
- **The `->` arrow does not automatically mean a switch expression.** Both switch statements and switch expressions in Java 17 can write branches using `->`.
- **`yield` is neither `break` nor `return`.** `yield` provides a value for a switch expression; `break` is used for statement control flow; `return` returns from a method.
- **Switch expressions have been standard syntax since Java 14 (JEP 361)**, inherited by Java 17. Pattern matching for `switch` in Java 17 is still **preview**, and is not part of the standard syntax used in this lesson.

## 1. One problem, two ways to write it

Suppose a system has order statuses:

```java
enum OrderStatus {
    NEW, PAID, CANCELLED
}
```

We want to turn a status into a display string.

### 1.1. `switch statement`: executing statements

```java
static String labelWithStatement(OrderStatus status) {
    String label;

    switch (status) {
        case NEW:
            label = "Newly created";
            break;
        case PAID:
            label = "Paid";
            break;
        case CANCELLED:
            label = "Cancelled";
            break;
        default:
            throw new IllegalStateException("Unsupported status");
    }

    return label;
}
```

This is a **switch statement** because the entire construct stands in the position of an **independent statement**. Each branch assigns to the variable `label`; the `switch` construct does not directly produce a `String` value.

The colon syntax `case ...:` can continue into the next branch (*fall-through*), so `break` is used to stop processing after each branch. The variable `label` must be proven by Java to have been assigned before the `return label` statement uses it.

### 1.2. `switch expression`: producing a value

```java
static String labelWithExpression(OrderStatus status) {
    return switch (status) {
        case NEW -> "Newly created";
        case PAID -> "Paid";
        case CANCELLED -> "Cancelled";
    };
}
```

This is a **switch expression** because `switch (status) { ... }` itself is an expression of type `String`; that value is used as the argument to the method's `return`.

Notable differences:

- No need to declare an intermediate variable.
- Each `->` branch returns an expression value.
- No `break` needed.
- When `status` is `enum OrderStatus`, the compiler sees all enum constants are covered, so `default` is not required.

It can also be used on the right-hand side of an assignment:

```java
String label = switch (status) {
    case NEW -> "Newly created";
    case PAID -> "Paid";
    case CANCELLED -> "Cancelled";
};
```

**Note on the semicolon:** The final `;` in the variable assignment example terminates **the outer declaration/assignment statement**, not a `break`, and it does not belong to the body of any branch.

## 2. Overview comparison table

| Criterion | `switch statement` | `switch expression` |
|---|---|---|
| Role | Control-flow statement | Expression that produces a value |
| Does `switch` itself have a value? | No | Yes |
| Common position | Standalone to perform actions | In assignments, `return`, method calls, or other expressions |
| `case:` syntax | Yes | Yes |
| `case ->` syntax | Yes | Yes |
| Can fall through? | Yes with `case:` style | Possible with `case:` style; `case ->` does not fall through |
| `break` | Commonly used in `case:` branches to exit the statement | Not used to provide a value |
| `yield` | Not used to provide a result for the statement itself | Used in a block or branch group to produce a value |
| Case coverage | A regular statement may have no matching branch | Must be **exhaustive**: every valid input value must have a path that produces a value or throws an exception |
| Result type checking | No result type for `switch` | The compiler determines the type of the switch expression |
| Typical scenarios | Logging, executing side effects, dispatching tasks | Mapping states to values, computing results |

**A simple code-reading rule:** Look at **the full position** of `switch` in the Java statement. If it is `String text = switch (...) { ... };` or `return switch (...) { ... };`, it is an expression. If it stands alone as `switch (...) { ... }` to call methods or assign variables, it is a statement. You cannot tell them apart solely by looking at `->`.

## 3. Two branch styles: `case:` and `case ->`

In Java 17 there are two ways to write the body of a `switch`.

### 3.1. Traditional style with a colon

```java
static void showLevel(int level) {
    switch (level) {
        case 1:
            System.out.println("Basic");
            break;
        case 2:
            System.out.println("Intermediate");
            break;
        default:
            System.out.println("Other");
    }
}
```

Each `case ...:` is a label in the switch block; when the program enters a label, it continues executing subsequent statements until it hits `break`, `return`, `throw`, or the end of the block. Therefore, this syntax has **fall-through capability**.

### 3.2. Arrow style in a switch statement

```java
static void showLevel(int level) {
    switch (level) {
        case 1 -> System.out.println("Basic");
        case 2 -> System.out.println("Intermediate");
        default -> System.out.println("Other");
    }
}
```

This is still a **statement**. The arrow simply creates a **switch rule** with an independent execution branch:

- Only executes the right-hand side of the arrow for the selected branch.
- Does not automatically continue into the next branch.
- Does not need `break` for each branch.
- The right-hand side in a **switch statement** can be a *statement expression* such as a method call, a block, or `throw`.

When multiple statements are needed:

```java
switch (level) {
    case 1 -> {
        System.out.println("Start");
        System.out.println("Learn the basic concepts");
    }
    case 2 -> {
        System.out.println("Continue");
        System.out.println("Practice advanced exercises");
    }
    default -> System.out.println("Unknown");
}
```

There is no `yield` because the goal is only to perform actions, not to produce a switch value.

### 3.3. Arrow style in a switch expression

```java
static String levelName(int level) {
    return switch (level) {
        case 1 -> "Basic";
        case 2 -> "Intermediate";
        default -> "Unknown";
    };
}
```

The right-hand side of `->` is now an expression value, a block using `yield` to produce a value, or a `throw` statement. The `switch` itself produces a result used by `return`.

### 3.4. The arrow is not proof of the switch kind

The following two snippets are very easy to misread:

```java
// SWITCH STATEMENT
switch (status) {
    case NEW -> System.out.println("Created");
    case PAID -> System.out.println("Paid");
    case CANCELLED -> System.out.println("Cancelled");
}
```

```java
// SWITCH EXPRESSION
String label = switch (status) {
    case NEW -> "Created";
    case PAID -> "Paid";
    case CANCELLED -> "Cancelled";
};
```

Both use `->` and neither falls through. **The distinguishing point is whether the switch is used as a value or not**, along with each branch's value rules.

## 4. `break` and `yield` solve two different needs

### 4.1. `break`: exiting a switch statement

```java
int day = 1;

switch (day) {
    case 1:
        System.out.println("Monday");
        break;
    case 2:
        System.out.println("Tuesday");
        break;
    default:
        System.out.println("Other");
}
```

Here, `break` terminates the switch statement. It **does not** return a `String` or any computed value from `switch`.

### 4.2. `yield`: handing a value to a switch expression

When a branch of an expression must perform multiple steps, use a block and `yield`:

```java
static int shippingFee(String mode, int distanceKm) {
    return switch (mode) {
        case "STANDARD" -> {
            int base = 10_000;
            int extra = Math.max(0, distanceKm - 5) * 1_000;
            yield base + extra;
        }
        case "EXPRESS" -> {
            int base = 20_000;
            int extra = Math.max(0, distanceKm - 3) * 2_000;
            yield base + extra;
        }
        default -> throw new IllegalArgumentException(
                "Invalid shipping method: " + mode);
    };
}
```

Execution flow in the `STANDARD` branch:

1. Compute the base fee.
2. Compute the extra fee.
3. `yield base + extra;` produces the value of the **switch expression**.
4. The `shippingFee` method receives the expression's value via `return switch ...`.

You cannot replace `yield base + extra;` with `break;` to provide the shipping fee. `break` has no result value.

### 4.3. `yield` differs from `return`

```java
static String outcome(boolean valid) {
    return switch (valid ? 1 : 0) {
        case 1 -> {
            String message = "Valid";
            yield message;          // Returns value to the switch expression
        }
        default -> "Invalid";
    };
}
```

`yield` ends the expression branch; the outer `return` returns a value from **the method**. When a branch requires intermediate processing steps, `yield` keeps the structure clear.

`yield` is not a new version of `break value`. The old preview syntax `break value` is not standard switch expression syntax in Java 17.

### 4.4. `throw` is a valid branch of an expression

```java
static String roleLabel(int code) {
    return switch (code) {
        case 1 -> "ADMIN";
        case 2 -> "USER";
        default -> throw new IllegalArgumentException("Unknown role: " + code);
    };
}
```

The `default` branch does not produce a string, but **throws an exception**, so it cannot complete normally without a value. This is valid for a switch expression.

### 4.5. `case:` can still be used in a switch expression

```java
static String scoreLabel(int score) {
    return switch (score) {
        case 0:
            yield "No score yet";
        case 1:
        case 2:
            yield "Low score";
        default:
            yield "Other score";
    };
}
```

In this example, the body is a switch expression even though it uses `case:`. `yield` provides the value for the expression. The labels `case 1:` and `case 2:` both lead to the shared handling branch.

With arrow syntax, it can be written more concisely:

```java
static String scoreLabel(int score) {
    return switch (score) {
        case 0 -> "No score yet";
        case 1, 2 -> "Low score";
        default -> "Other score";
    };
}
```

When fall-through behavior is not needed, the `->` style is usually easier to read and less error-prone.

## 5. Fall-through: a trait of the colon, not of statements in general

**Fall-through** means that after selecting a branch, the program continues executing the statements in subsequent branches if there is no suitable control-flow terminator.

### 5.1. Fall-through can cause bugs

```java
int priority = 1;

switch (priority) {
    case 1:
        System.out.println("High");
        // Forgot break!
    case 2:
        System.out.println("Medium");
        break;
    default:
        System.out.println("Low");
}
```

Output:

```text
High
Medium
```

If the author intended to print only `"High"`, forgetting `break` is a bug. However, there are also cases where labels are intentionally grouped:

```java
switch (priority) {
    case 1:
    case 2:
        System.out.println("Needs processing");
        break;
    default:
        System.out.println("Defer");
}
```

### 5.2. Using the arrow to prevent fall-through

```java
switch (priority) {
    case 1, 2 -> System.out.println("Needs processing");
    default -> System.out.println("Defer");
}
```

Similarly, in a switch expression:

```java
String action = switch (priority) {
    case 1, 2 -> "PROCESS_NOW";
    default -> "PROCESS_LATER";
};
```

There is no fall-through here. **Do not phrase it as "statements have fall-through, expressions do not"**. What is accurate is:

- The **`case:`** style allows execution to continue across branch groups when unblocked; this exists in both switch statements and switch expressions.
- The **`case ->`** style does not fall through, whether the overall `switch` is a statement or an expression.

## 6. Exhaustiveness: switch expressions must cover every input value

A switch expression must be **exhaustive**: a valid selector value must not cause the expression to complete normally without producing a value.

### 6.1. A switch statement can omit `default`

```java
static void printKnownCode(int code) {
    switch (code) {
        case 100 -> System.out.println("OK");
        case 404 -> System.out.println("NOT_FOUND");
    }
}
```

With `code = 500`, no branch matches. The switch statement completes without printing anything. This is valid statement behavior in this example.

### 6.2. A switch expression on `int` needs a fallback branch

The following snippet is **invalid**:

```java
// DOES NOT COMPILE: switch expression is not exhaustive.
static String httpLabel(int code) {
    return switch (code) {
        case 200 -> "OK";
        case 404 -> "Not Found";
    };
}
```

`int` has too many values for two branches to cover them all. You need to add `default`:

```java
static String httpLabel(int code) {
    return switch (code) {
        case 200 -> "OK";
        case 404 -> "Not Found";
        default -> "Other";
    };
}
```

The `default` branch can produce a value or throw an exception, depending on the method's contract.

### 6.3. A fully covered `enum` does not require `default`

```java
enum PaymentState {
    CREATED, APPROVED, DECLINED
}

static String describe(PaymentState state) {
    return switch (state) {
        case CREATED -> "Created";
        case APPROVED -> "Approved";
        case DECLINED -> "Declined";
    };
}
```

The compiler knows the declared `enum` constants, so three branches are enough to prove the expression is exhaustive. `default` is not required.

If a constant `REFUNDED` is later added to `PaymentState`, recompiling the code above can report that the switch expression is missing a branch. This is useful for catching places where logic has not yet been updated. However, when changing an enum independently of previously compiled classes, runtime compatibility still needs to be considered; compile-time exhaustiveness does not guarantee that all separately deployed versions are in sync.

### 6.4. A statement may still require definite variable assignment

Do not confuse "a statement is not required to be exhaustive" with "the compiler ignores definite assignment".

```java
static String statusText(int code) {
    String result;

    switch (code) {
        case 1:
            result = "ONE";
            break;
        // No default.
    }

    return result; // COMPILE ERROR: result might not have been initialized.
}
```

The switch statement itself is not disallowed for lacking `default`. But the local variable `result` might not be assigned before `return` uses it. That is a separate Java check.

You can fix it with `default`, an appropriate initial value, or a switch expression with complete branches.

## 7. Selector data types in Java 17

With Java 17's **standard** switch syntax, the selector is typically:

- `byte`, `short`, `char`, or `int`.
- Their corresponding wrappers: `Byte`, `Short`, `Character`, `Integer`.
- `String`.
- An `enum` type.

Example with strings:

```java
static int retryCount(String mode) {
    return switch (mode) {
        case "FAST" -> 1;
        case "NORMAL" -> 3;
        case "SAFE" -> 5;
        default -> throw new IllegalArgumentException("Unknown mode");
    };
}
```

Example with an enum:

```java
enum Environment { DEV, TEST, PROD }

static boolean allowDebug(Environment environment) {
    return switch (environment) {
        case DEV, TEST -> true;
        case PROD -> false;
    };
}
```

**Version note:** Do not use standard Java 17 `switch` with `long`, `float`, `double`, or `boolean` as a selector. Some syntax may be expanded or previewed in other Java versions, but this lesson describes standard Java 17.

### 7.1. `null` is not a standard case branch in Java 17

If a reference-type selector is `null`, a regular switch statement or expression in Java 17 throws a `NullPointerException`.

```java
String level = null;

// Throws NullPointerException when evaluating switch:
String label = switch (level) {
    case "HIGH" -> "High";
    default -> "Other";
};
```

The `default` branch **does not catch `null`**. Check beforehand:

```java
static String safeLabel(String level) {
    if (level == null) {
        return "Unspecified";
    }
    return switch (level) {
        case "HIGH" -> "High";
        case "LOW" -> "Low";
        default -> "Other";
    };
}
```

The `case null` syntax belongs to the evolution of pattern matching for switch and **is not yet standard switch syntax in Java 17**. Do not include it in default-compiled examples.

### 7.2. `case` labels do not accept arbitrary conditions

```java
int value = 20;

// NOT STANDARD JAVA 17 SWITCH SYNTAX:
switch (value) {
    // case value > 10 -> System.out.println("Large");
}
```

Cases in a traditional switch require valid constant labels (or corresponding enum constants), not arbitrary conditional expressions like `value > 10`. For range conditions, logical combinations, or complex comparisons, `if/else` can be clearer:

```java
static String classify(int value) {
    if (value > 10) {
        return "Large";
    }
    return "Not large";
}
```

Do not try to force-replace every `if` with a `switch expression`.

## 8. Result type of a switch expression

Because a switch expression produces a value, the compiler must determine **the result type** from its branches and usage context.

### 8.1. Branches of the same type

```java
int score = switch (grade) {
    case "A" -> 100;
    case "B" -> 80;
    default -> 0;
};
```

All branches produce `int`, so the overall value can be assigned to `int score`.

### 8.2. Returning directly from a method

```java
static boolean canShip(OrderStatus status) {
    return switch (status) {
        case NEW -> false;
        case PAID -> true;
        case CANCELLED -> false;
    };
}
```

The expression's type matches the method's `boolean` return type. Consolidating logic into an expression often allows the result to be type-checked right at the point of use.

### 8.3. Result types must be compatible

The example below is invalid if an `int` result is required while one branch returns a `String`:

```java
// INVALID: one branch is String, cannot assign the whole expression to int.
int result = switch (code) {
    case 1 -> 100;
    default -> "unknown";
};
```

A unified result type can be chosen:

```java
String result = switch (code) {
    case 1 -> "100";
    default -> "unknown";
};
```

Do not think that every branch of a switch expression must literally write **the exact same literal type** in source code. Java has valid type inference and conversion rules depending on context. The practical rule is: **the expression's value must be compatible with the type required by the call site**.

### 8.4. A block with `yield` must produce a compatible value

```java
static int discountPercent(String customerTier) {
    return switch (customerTier) {
        case "GOLD" -> {
            int base = 10;
            int promotion = 5;
            yield base + promotion;
        }
        case "SILVER" -> 5;
        default -> 0;
    };
}
```

The value produced in a block branch is the result of the expression after `yield`, not the value of any arbitrary last statement in the block.

## 9. A switch statement can be written concisely without becoming an expression

Beginners often use `->` in a statement and then think they can assign the entire switch to a variable. Look at two versions with the same meaning.

**Statement with assignment in each branch:**

```java
static String categoryStatement(int code) {
    String category;

    switch (code) {
        case 1 -> category = "A";
        case 2 -> category = "B";
        default -> category = "OTHER";
    }

    return category;
}
```

Because the branches use the assignment `category = ...` which is a statement expression, this is still a **switch statement**. The variable receives its value via each branch's side effect.

**Expression producing a value directly:**

```java
static String categoryExpression(int code) {
    return switch (code) {
        case 1 -> "A";
        case 2 -> "B";
        default -> "OTHER";
    };
}
```

In the expression example, there is no intermediate variable and no assignments inside each branch. `switch` is a value that can be passed directly into another method:

```java
System.out.println(
    switch (code) {
        case 1 -> "A";
        case 2 -> "B";
        default -> "OTHER";
    }
);
```

This style fits when branches represent **multiple possibilities of a single computation**. If each branch performs a series of independent operations like sending an email, writing to a database, or coordinating tasks, a statement may express the intent more clearly.

## 10. Applied example: computing ticket price by type

Suppose a program needs to select a ticket price by type:

```java
enum TicketType {
    STANDARD, STUDENT, VIP
}
```

### 10.1. Using a switch statement with colons

```java
static int priceWithStatement(TicketType type) {
    int price;

    switch (type) {
        case STANDARD:
            price = 100_000;
            break;
        case STUDENT:
            price = 70_000;
            break;
        case VIP:
            price = 200_000;
            break;
        default:
            throw new IllegalArgumentException("Unsupported ticket type");
    }

    return price;
}
```

Semantically correct, but requires updating a variable and stopping each branch with `break`.

### 10.2. Using a switch statement with arrows

```java
static int priceWithArrowStatement(TicketType type) {
    int price;

    switch (type) {
        case STANDARD -> price = 100_000;
        case STUDENT -> price = 70_000;
        case VIP -> price = 200_000;
    }

    return price;
}
```

**Be careful with this example:** With a regular switch statement, even though the code lists all current enum constants, the compiler does not necessarily treat assigning `price` in the branches as guaranteeing definite assignment the way a switch expression does. When you need to ensure all paths assign a value, add `default` or use a switch expression.

Safe, clear statement version:

```java
static int priceWithArrowStatement(TicketType type) {
    int price;

    switch (type) {
        case STANDARD -> price = 100_000;
        case STUDENT -> price = 70_000;
        case VIP -> price = 200_000;
        default -> throw new IllegalArgumentException("Unsupported ticket type");
    }

    return price;
}
```

### 10.3. Using a switch expression

```java
static int priceWithExpression(TicketType type) {
    return switch (type) {
        case STANDARD -> 100_000;
        case STUDENT -> 70_000;
        case VIP -> 200_000;
    };
}
```

This directly reflects the meaning: **ticket type determines the price**, and Java checks that the expression covers all current enum branches.

When branches simply return values, a switch expression is usually shorter and involves fewer control-flow steps.

## 11. Complete runnable example on Java 17

To observe both forms without external libraries, save the code below as **`SwitchStatementVsExpression.java`**:

```java
public class SwitchStatementVsExpression {

    enum State {
        CREATED, PAID, CANCELLED
    }

    // Traditional statement: assign variable then break.
    static String viaColonStatement(State state) {
        String label;

        switch (state) {
            case CREATED:
                label = "Created";
                break;
            case PAID:
                label = "Paid";
                break;
            case CANCELLED:
                label = "Cancelled";
                break;
            default:
                throw new IllegalArgumentException("Unsupported state");
        }

        return label;
    }

    // Arrow statement: performs action, produces no switch value.
    static void printAction(State state) {
        switch (state) {
            case CREATED -> System.out.println("Allow editing order");
            case PAID -> System.out.println("Prepare shipment");
            case CANCELLED -> System.out.println("Do not ship");
        }
    }

    // Arrow expression: returns value directly.
    static String viaExpression(State state) {
        return switch (state) {
            case CREATED -> "Created";
            case PAID -> "Paid";
            case CANCELLED -> "Cancelled";
        };
    }

    // Expression with block: uses yield.
    static int rewardPoints(State state, int amount) {
        return switch (state) {
            case CREATED, CANCELLED -> 0;
            case PAID -> {
                int basePoints = amount / 10_000;
                int bonus = amount >= 100_000 ? 5 : 0;
                yield basePoints + bonus;
            }
        };
    }

    public static void main(String[] args) {
        State state = State.PAID;

        System.out.println(viaColonStatement(state));
        printAction(state);
        System.out.println(viaExpression(state));
        System.out.println("Reward points: " + rewardPoints(state, 120_000));
    }
}
```

Compile and run with JDK 17:

```bash
javac --release 17 SwitchStatementVsExpression.java
java SwitchStatementVsExpression
```

Expected output:

```text
Paid
Prepare shipment
Paid
Reward points: 17
```

Explanation of `17`: `120_000 / 10_000 = 12` base points, plus `5` bonus points because the order amount is `100_000` or more.

In the same program, three different forms coexist:

- Statement with `case:` and `break`.
- Statement with `case ->` to perform an action.
- Expression with `case ->` and `yield` when calculations are needed inside a block.

All are **standard syntax in Java 17**.

## 12. When to choose a statement vs. when to choose an expression?

### 12.1. Prefer an expression when every branch produces a single result

Example of selecting configuration:

```java
static int timeoutSeconds(String environment) {
    return switch (environment) {
        case "DEV" -> 5;
        case "TEST" -> 10;
        case "PROD" -> 30;
        default -> throw new IllegalArgumentException(
                "Unknown environment: " + environment);
    };
}
```

Here, every branch returns a **timeout duration**, so an expression represents the idea concisely and clearly.

### 12.2. Prefer a statement when the goal is performing actions

```java
static void dispatch(String command) {
    switch (command) {
        case "START" -> System.out.println("Starting service");
        case "STOP" -> System.out.println("Stopping service");
        case "RELOAD" -> {
            System.out.println("Reloading configuration");
            System.out.println("Reinitializing required components");
        }
        default -> System.out.println("Unsupported command");
    }
}
```

This construct does not need to produce a value. Forcing it into an expression just to use new syntax can make code harder to understand.

### 12.3. For complex conditions, consider `if/else`

```java
static String deliveryBand(int distanceKm) {
    if (distanceKm < 0) {
        throw new IllegalArgumentException("distanceKm must be non-negative");
    }
    if (distanceKm <= 3) {
        return "Near";
    }
    if (distanceKm <= 15) {
        return "Medium";
    }
    return "Far";
}
```

This is a numeric range comparison problem rather than selecting from a list of constant labels. In Java 17, `if/else` is a better fit.

### 12.4. Do not mix unnecessary side effects into an expression

A switch expression can still contain method calls, logging, or data validation inside a block. However, if most of the code only performs side effects, a statement usually conveys the intent better. Use an expression when a **computed value** is the primary result of selecting a branch.

## 13. Common mistakes when moving from statement to expression

### Mistake 1. Forgetting `break` in a colon-style statement

```java
switch (code) {
    case 1:
        System.out.println("A");
        // Forgot break, will continue into case 2.
    case 2:
        System.out.println("B");
        break;
}
```

**How to handle:** Put `break` in the right place or switch to `case ->` if fall-through is not intended.

### Mistake 2. Seeing `->` and calling it an expression

```java
switch (code) {
    case 1 -> System.out.println("A");
    default -> System.out.println("B");
}
```

This is a **switch statement**, because it stands alone and only prints messages.

### Mistake 3. Trying to use `break` to return a value

```java
// INVALID in standard Java 17 switch expression:
int size = switch (kind) {
    case 1 -> {
        break 10;
    }
    default -> 0;
};
```

Use `yield`:

```java
int size = switch (kind) {
    case 1 -> {
        yield 10;
    }
    default -> 0;
};
```

### Mistake 4. Writing a block and forgetting `yield`

```java
// INVALID: block branch can finish without producing a value.
String text = switch (code) {
    case 1 -> {
        System.out.println("Selected 1");
    }
    default -> "Other";
};
```

Fix:

```java
String text = switch (code) {
    case 1 -> {
        System.out.println("Selected 1");
        yield "One";
    }
    default -> "Other";
};
```

### Mistake 5. Missing `default` in an expression over `int` or `String`

```java
// INVALID: does not cover all possible strings.
String description = switch (mode) {
    case "A" -> "Mode A";
    case "B" -> "Mode B";
};
```

Fix with a `default` branch that returns a value or throws an exception.

### Mistake 6. Treating `default` as handling `null`

```java
String mode = null;

String result = switch (mode) {
    case "A" -> "Mode A";
    default -> "Other";
};
```

In standard Java 17, a `null` selector throws `NullPointerException`. Check for `null` before the switch if the input can be null.

### Mistake 7. Using pattern matching syntax from newer Java for default Java 17

```java
// Example of syntax that is not part of standard default Java 17:
// return switch (obj) {
//     case String s -> s.length();
//     case Integer i -> i;
//     default -> 0;
// };
```

Pattern matching for switch in Java 17 is preview (JEP 406). If a project requires **standard Java 17 without preview**, use `instanceof` or the stably supported selectors and `case` labels.

### Mistake 8. Assuming a switch expression automatically coerces every branch to the target type

Java has type inference/conversion rules, but it cannot turn an arbitrary `String` into an `int` just because the target variable is `int`. When branches do not agree on a type, you must clearly decide on the returned data model.

## 14. Practice exercises

### Exercise 1. Identify the switch kind

Look at the snippet:

```java
switch (level) {
    case 1 -> System.out.println("Basic");
    default -> System.out.println("Other");
}
```

**Question:** Is this a statement or an expression? Is there fall-through?

**Answer:** This is a **statement**, because `switch` stands alone and only prints messages. There is no fall-through because it uses `case ->`.

### Exercise 2. Rewrite from statement to expression

Given:

```java
static String season(int month) {
    String result;
    switch (month) {
        case 12:
        case 1:
        case 2:
            result = "WINTER";
            break;
        case 3:
        case 4:
        case 5:
            result = "SPRING";
            break;
        case 6:
        case 7:
        case 8:
            result = "SUMMER";
            break;
        case 9:
        case 10:
        case 11:
            result = "AUTUMN";
            break;
        default:
            throw new IllegalArgumentException("Invalid month");
    }
    return result;
}
```

**Requirement:** Rewrite to return a switch expression without using the `result` variable.

**One solution:**

```java
static String season(int month) {
    return switch (month) {
        case 12, 1, 2 -> "WINTER";
        case 3, 4, 5 -> "SPRING";
        case 6, 7, 8 -> "SUMMER";
        case 9, 10, 11 -> "AUTUMN";
        default -> throw new IllegalArgumentException("Invalid month");
    };
}
```

### Exercise 3. Choosing the right `yield`

```java
static int compute(int kind, int base) {
    return switch (kind) {
        case 1 -> base;
        case 2 -> {
            int extra = base / 2;
            // Fill in one statement here.
        }
        default -> 0;
    };
}
```

**Requirement:** When `kind == 2`, return `base + extra` from the switch expression.

**Answer:** Fill in `yield base + extra;`. `break;` does not provide a value.

### Exercise 4. Distinguish exhaustiveness requirements

```java
enum Direction { NORTH, SOUTH, EAST, WEST }

static String directionName(Direction direction) {
    return switch (direction) {
        case NORTH -> "North";
        case SOUTH -> "South";
        case EAST -> "East";
        case WEST -> "West";
    };
}
```

**Question:** Why is this expression valid even without `default`?

**Answer:** Because it covers all constants of `Direction` at compile time. Java can prove the switch expression is exhaustive for this enum.

### Exercise 5. Find the output with fall-through

```java
int x = 2;

switch (x) {
    case 1:
        System.out.print("A");
    case 2:
        System.out.print("B");
    case 3:
        System.out.print("C");
        break;
    default:
        System.out.print("D");
}
```

**Question:** What is printed?

**Answer:** `BC`. Execution starts at `case 2`, continues into `case 3`, and then hits `break`.

### Exercise 6. Choose the construct for a real-world scenario

One function takes a service plan type and needs to **return the fee**. Another function receives an event and needs to **call the right handler, update state, and write logs**.

**Hint:** The fee-selection function usually fits a switch expression. The task-dispatching function usually fits a switch statement, optionally using `->` to eliminate fall-through.

### Exercise 7. Why does the example not compile?

```java
static String classify(int value) {
    return switch (value) {
        case 1 -> "ONE";
        case 2 -> "TWO";
    };
}
```

**Answer:** The switch expression is not exhaustive because `value` can be any `int` other than 1 or 2. A `default` branch must be added to produce a value or throw an exception.

## 15. Takeaways and references

**Distinguishing by the role of `switch`:**

1. A `switch statement` executes statements; it can be written with `case:` or `case ->`.
2. A `switch expression` produces a value; it can also use both case styles, but every normally completing path must produce a result.
3. `case ->` prevents fall-through for **both** forms of `switch`.
4. `break` exits a switch statement; `yield` provides a value to a switch expression; `return` returns from a method.
5. A switch expression must be exhaustive. With `int` or `String`, `default` is usually required; with `enum`, all constants can be listed exhaustively.
6. Switch expressions have been stable since **Java 14**, inherited by Java 17. Pattern matching for switch is still **preview in Java 17**.

### Official documentation

- [OpenJDK JEP 361 — Switch Expressions](https://openjdk.org/jeps/361): design and standardization process of switch expressions in Java 14.
- [Oracle Java 17 — Switch Expressions](https://docs.oracle.com/en/java/javase/17/language/switch-expressions.html): guide distinguishing switch statements and switch expressions, `->` syntax, `yield`, and exhaustiveness.
- [Java Language Specification 17 — `14.11 The switch Statement`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.11): switch statement rules.
- [Java Language Specification 17 — `15.28 switch Expressions`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.28): switch expression rules, result types, and case coverage.
- [OpenJDK JEP 406 — Pattern Matching for switch (Preview)](https://openjdk.org/jeps/406): preview feature in Java 17, to be distinguished from stabilized switch expressions.

**Practical conclusion:** If the purpose of `switch` is to **produce a value**, consider a switch expression. If the purpose is to **perform an action**, use a switch statement. The `->` arrow is useful in both; the most important thing is how branches terminate and how Java ensures the result fits its call site.
