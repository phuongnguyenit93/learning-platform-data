# Exhaustiveness, `default`, and `switch` on `enum` in Java 17

## 1. Why does exhaustiveness matter for `switch expression`?

In Java 17, a **switch expression** is an expression that produces a value. You can use it on the right-hand side of an assignment, return it directly from a method, or pass it into another expression. Unlike a regular `switch` statement that only directs execution flow, a `switch expression` must determine a result for **every valid value** of the selector expression (*selector*).

A simple example with an order status `enum`:

~~~java
enum OrderStatus {
    CREATED, PAID, SHIPPED, DELIVERED, CANCELLED
}

static String displayName(OrderStatus status) {
    return switch (status) {
        case CREATED -> "Created";
        case PAID -> "Paid";
        case SHIPPED -> "Shipped";
        case DELIVERED -> "Delivered";
        case CANCELLED -> "Cancelled";
    };
}
~~~

This snippet **has no `default`** yet is still valid in Java 17. The reason: the five `case` branches cover **all five constants of `OrderStatus`** known to the compiler. Java calls this property **exhaustiveness** — *completeness of branch coverage*.

Conversely, if `CANCELLED` is missing, the compiler cannot guarantee that `switch` produces a string for that value:

~~~java
// Intentionally DOES NOT compile: missing CANCELLED
static String incomplete(OrderStatus status) {
    return switch (status) {
        case CREATED -> "Created";
        case PAID -> "Paid";
        case SHIPPED -> "Shipped";
        case DELIVERED -> "Delivered";
    };
}
~~~

This is a **compile error** because the `switch expression` does not cover all constants of the `enum` and has no `default` to handle the rest. This is a very useful safeguard when business states are modeled with `enum`.

> **Core rule in Java 17:** A `switch expression` must be exhaustive. For a selector of type `enum`, you can achieve exhaustiveness by listing all `enum` constants, or by adding a `default` branch to handle unlisted values.

### Learning objectives

After this lesson, you will be able to:

- Recognize when a `switch expression` is considered exhaustive and why missing branches cause compile errors.
- Understand the role of `default` and why **you should not always write `default`** when handling all `enum` constants.
- Use `switch` with `enum`, group multiple constants into one branch, and return values with `->` and `yield`.
- Predict the impact when a new constant is added to an `enum`.
- Distinguish `default` from handling `null`; know how to define a policy when the selector may be `null`.
- Structure practical Java 17 examples and run them with `javac` and `java` without needing preview features.

## 2. Distinguishing `switch statement` and `switch expression`

The two forms of `switch` are easy to confuse because they look similar:

### 2.1. `switch statement`: executing actions

~~~java
static void logStatus(OrderStatus status) {
    switch (status) {
        case CREATED:
            System.out.println("Order created");
            break;
        case PAID:
            System.out.println("Payment received");
            break;
        default:
            System.out.println("Other status");
    }
}
~~~

Traditional `switch` here is a **statement** and does not return a value. When no branch matches, the program can simply continue past the `switch` statement. Branches use `:`, and `break` prevents unintended *fall-through*.

### 2.2. `switch expression`: computing a value

~~~java
static String statusCategory(OrderStatus status) {
    return switch (status) {
        case CREATED, PAID -> "OPEN";
        case SHIPPED, DELIVERED -> "FULFILLMENT";
        case CANCELLED -> "CLOSED";
    };
}
~~~

Here:

1. The `switch` keyword starts an **expression** after `return`.
2. The `->` arrow routes execution to the right branch without falling through to other branches.
3. The value of the branch becomes the overall value of the entire expression.
4. Each `enum` constant appears exactly once, which suffices to omit `default`.

| Criterion | Traditional `switch statement` | `switch expression` |
|---|---|---|
| Purpose | Select statements to execute. | Produce a value or throw an exception. |
| Must be exhaustive? | Not required for traditional `switch` statements. | **Yes**, the compiler checks exhaustiveness. |
| Branch syntax | Typically uses `case X:` and `break`; Java 17 also supports switch rules with `->`. | Typically uses `case X -> value` or a block with `yield`. |
| Return value | The statement itself has no value. | Has a value whose type matches the context. |
| Omit `default` when covering all `enum` values | Possible; though the statement still returns no value. | **Possible** and often beneficial for tracking new constants. |

Do not confuse `break` from traditional `switch` statements with `yield` from `switch expression`: `break` exits a statement; `yield` provides a value to an expression.

## 3. Exhaustiveness rules when the selector is an `enum`

Given a variable of static type `OrderStatus`:

~~~java
OrderStatus status = OrderStatus.PAID;
~~~

Java knows the enum constants declared in the source code or class file it compiles against:

~~~text
OrderStatus
├── CREATED
├── PAID
├── SHIPPED
├── DELIVERED
└── CANCELLED
~~~

Therefore, there are at least two strategies for making an exhaustive `switch expression`:

**Approach A — List all constants:**

~~~java
return switch (status) {
    case CREATED -> "New";
    case PAID -> "Paid";
    case SHIPPED -> "On the way";
    case DELIVERED -> "Finished";
    case CANCELLED -> "Stopped";
};
~~~

**Approach B — List some constants, let `default` handle the rest:**

~~~java
return switch (status) {
    case CREATED, PAID -> "ACTIVE";
    default -> "OTHER";
};
~~~

Both satisfy exhaustiveness, but their **maintenance semantics differ**. Approach A makes explicit how each constant is handled; approach B lets unnamed constants fall into a single branch.

### Grouping multiple constants in a single `case`

Every constant does not need a different result expression:

~~~java
static boolean canCancel(OrderStatus status) {
    return switch (status) {
        case CREATED, PAID -> true;
        case SHIPPED, DELIVERED, CANCELLED -> false;
    };
}
~~~

Grouping `CREATED, PAID` and `SHIPPED, DELIVERED, CANCELLED` still exhaustively covers all five constants. This is convenient when multiple values share the same behavior while still **explicitly listing** which constants belong to each group.

### Conditions that do not substitute for exhaustiveness

- A very complex `case` branch does not automatically make a `switch` exhaustive.
- Knowing that in **reality** data "only contains CREATED or PAID" is not enough to compile a `switch expression` missing other constants of the same `enum`. The compiler relies on the selector type and the branches in code, not external business assumptions.
- A `default` branch makes the expression syntactically exhaustive, but **does not prove business correctness** for every constant lumped into it.
- Constants present in the `enum` without any handling branch, in the absence of `default`, will cause the `switch expression` to be rejected at compile time.

## 4. `default`: when is it needed and when should you consider avoiding it?

### 4.1. `default` helps handle unlisted cases

In many scenarios, you only care about a few special values while all other values share the same behavior. Example:

~~~java
static boolean requiresPayment(OrderStatus status) {
    return switch (status) {
        case CREATED -> true;
        default -> false;
    };
}
~~~

If the business policy is **only CREATED requires payment, all other statuses do not**, `default` expresses the rule concisely and clearly. It covers `PAID`, `SHIPPED`, `DELIVERED`, and `CANCELLED`.

Similarly, when the selector is `int` or `String`, the set of possible values is not a small finite set like an `enum`; you will normally need `default` to make the `switch expression` exhaustive:

~~~java
static String categoryForCode(int code) {
    return switch (code) {
        case 200 -> "SUCCESS";
        case 404 -> "NOT_FOUND";
        default -> "OTHER";
    };
}
~~~

### 4.2. `default` can hide a new state

Suppose initially you have:

~~~java
enum OrderStatus {
    CREATED, PAID, SHIPPED, DELIVERED, CANCELLED
}
~~~

A classification function is written:

~~~java
static String lifecycleGroup(OrderStatus status) {
    return switch (status) {
        case CREATED, PAID -> "BEFORE_SHIPMENT";
        case SHIPPED, DELIVERED -> "AFTER_SHIPMENT";
        default -> "STOPPED";
    };
}
~~~

With only those five constants, `default` catches `CANCELLED`. Later, the development team adds `RETURNED`:

~~~java
enum OrderStatus {
    CREATED, PAID, SHIPPED, DELIVERED, CANCELLED, RETURNED
}
~~~

`lifecycleGroup` **still compiles** because `default` already handles all unnamed values, including `RETURNED`. Whether `"STOPPED"` is appropriate for `RETURNED` is a business question requiring review. The compiler cannot make that decision for you.

If all constants had been written out explicitly from the beginning:

~~~java
static String lifecycleGroup(OrderStatus status) {
    return switch (status) {
        case CREATED, PAID -> "BEFORE_SHIPMENT";
        case SHIPPED, DELIVERED -> "AFTER_SHIPMENT";
        case CANCELLED -> "STOPPED";
    };
}
~~~

then after adding `RETURNED` and **recompiling code using the updated enum**, the expression missing a `RETURNED` branch will **trigger a compile error**. Developers must explicitly decide which group the new constant belongs to.

This is one of the biggest advantages of omitting `default` when you want strict control over every `enum` constant.

### 4.3. Choosing `default` based on the real meaning of the problem

| Context | Usually appropriate style | Why? |
|---|---|---|
| Mapping **each** enum state to distinct business behavior | List all constants, omit `default`. | When a state is added, recompiling forces reviewing the new branch. |
| One or a few special states, while **all** others truly share the same behavior | Use `default` intentionally. | Expresses an explicit "all remaining cases" policy. |
| Selector is `int`/`String`, unable to list all values | Usually needs `default`. | Makes the expression exhaustive. |
| Wanting to reject unexpected values | `default -> throw ...` may make sense. | Avoids silently returning a default value, though enum growth still requires proactive review. |

When designing long-lived APIs, prioritize clarifying **business invariants** before choosing `default` merely to save lines.

## 5. `default -> throw`: error handling instead of returning a value

In a `switch expression`, a branch can **throw an exception** rather than produce a value. Example:

~~~java
static String shippingCode(OrderStatus status) {
    return switch (status) {
        case SHIPPED -> "IN_TRANSIT";
        case DELIVERED -> "RECEIVED";
        default -> throw new IllegalStateException(
                "Order is not in shipping phase: " + status);
    };
}
~~~

When `status == OrderStatus.PAID`, the `default` branch throws `IllegalStateException`. The function call does not return a string; that is **intentional behavior** because this method is only valid for shipping states.

However, distinguish carefully:

1. `default -> throw` makes the `switch expression` syntactically exhaustive.
2. It **does not produce a compile warning** when a new constant is added to the enum; the new constant will hit `default` at runtime.
3. It is a way to express a precondition or defensive branch, not a substitute for updating logic if the new constant needs dedicated behavior.

In domains where **every** constant must be handled at the business level, listing all constants without `default` usually makes changes easier to track.

## 6. `->`, blocks, and `yield` in `switch expression`

For simple branches, the `->` syntax is very concise:

~~~java
String name = switch (status) {
    case CREATED -> "Created";
    case PAID -> "Paid";
    case SHIPPED -> "Shipped";
    case DELIVERED -> "Delivered";
    case CANCELLED -> "Cancelled";
};
~~~

If a branch must execute multiple statements before computing the result, use a `{ ... }` block and **`yield`**:

~~~java
static int priority(OrderStatus status) {
    return switch (status) {
        case CREATED -> 10;
        case PAID -> 20;
        case SHIPPED -> {
            int shippingPriority = 30;
            int trackingBonus = 5;
            yield shippingPriority + trackingBonus;
        }
        case DELIVERED, CANCELLED -> 0;
    };
}
~~~

In the `SHIPPED` branch, `yield shippingPriority + trackingBonus;` returns `35` for the entire expression. The remaining branches use the short `-> 10`, `-> 20`, and `-> 0` syntax.

Points to remember:

- `yield` provides a value to the enclosing **switch expression**.
- `yield` does not play the same role as `break` in a `switch` statement.
- A branch like `case X -> { ... }` must not leave any normally completing path without `yield` or throwing an exception; the expression's outcome must be determined.
- Values from all branches must be compatible so the expression has a usable result type at the call site.
- `->` branches do not suffer from *fall-through* as happens when forgetting `break` in traditional colon syntax.

### Colon syntax combined with `yield`

A `switch expression` can also use `case X:` label syntax together with `yield`:

~~~java
static String labelWithColon(OrderStatus status) {
    return switch (status) {
        case CREATED:
            yield "Created";
        case PAID:
            yield "Paid";
        case SHIPPED:
            yield "Shipped";
        case DELIVERED:
            yield "Delivered";
        case CANCELLED:
            yield "Cancelled";
    };
}
~~~

This snippet is still exhaustive, though usually longer than `->` branches. Without a special reason, `case X -> value` makes enum-mapping expressions easier to read.

## 7. `null`: the case `default` does not automatically catch

A common question: *"I already have `default`, so if the enum is `null`, does it enter `default`?"*

**No.** With a standard `switch` in Java 17, if the selector expression evaluates to a `null` reference, the program throws **`NullPointerException`**. It does not jump to `default`. For example:

~~~java
static String labelWithDefault(OrderStatus status) {
    return switch (status) {
        case CREATED -> "Created";
        default -> "Other";
    };
}

// labelWithDefault(null) -> NullPointerException
~~~

`default` is a branch for **enum values not listed** in preceding `case` labels, not a replacement for a `null` reference check.

This is the behavior in Java 17 when using standard `switch`. Pattern matching for `switch` has extended syntax in other Java versions, but in Java 17 it is a preview feature; this lesson does not use `case null` or require enabling preview.

### 7.1. Policy A: reject `null` explicitly

If `null` is invalid input, validate it right at the method boundary:

~~~java
import java.util.Objects;

static String requireLabel(OrderStatus status) {
    Objects.requireNonNull(status, "status");

    return switch (status) {
        case CREATED -> "Created";
        case PAID -> "Paid";
        case SHIPPED -> "Shipped";
        case DELIVERED -> "Delivered";
        case CANCELLED -> "Cancelled";
    };
}
~~~

`Objects.requireNonNull(status, "status")` still throws `NullPointerException` if the argument is missing, but the message identifies the parameter name. It also makes the method's contract immediately recognizable when reading the code.

### 7.2. Policy B: handle `null` before `switch`

If missing status truly needs to be treated as an acceptable data case:

~~~java
static String optionalLabel(OrderStatus status) {
    if (status == null) {
        return "Missing status";
    }

    return switch (status) {
        case CREATED -> "Created";
        case PAID -> "Paid";
        case SHIPPED -> "Shipped";
        case DELIVERED -> "Delivered";
        case CANCELLED -> "Cancelled";
    };
}
~~~

This handles `null` separately, then uses `switch` to exhaustively handle **actual enum constants**. It draws a clean boundary between an absent reference and a business state.

### 7.3. Should you add an `UNKNOWN` constant to the enum?

If the business domain has a valid "undetermined" state, you can model it with an `UNKNOWN` constant:

~~~java
enum State {
    UNKNOWN, READY, DONE
}
~~~

Then `UNKNOWN` is **an actual enum value**, which can appear in `case UNKNOWN`. However, `null` is still a reference pointing to no enum object; adding `UNKNOWN` **does not make `switch(null)` automatically become `switch(UNKNOWN)`**. Decide whether to convert `null` to `UNKNOWN` (if appropriate) at the input-handling layer.

## 8. When an enum adds a new constant: recompilation and binary compatibility

Suppose a method was compiled against an initial enum:

~~~java
enum Status {
    NEW, ACTIVE, CLOSED
}

static String title(Status status) {
    return switch (status) {
        case NEW -> "New";
        case ACTIVE -> "Active";
        case CLOSED -> "Closed";
    };
}
~~~

Later, `SUSPENDED` is added to the enum:

~~~java
enum Status {
    NEW, ACTIVE, CLOSED, SUSPENDED
}
~~~

Two scenarios must be distinguished:

### 8.1. Recompiling all code with the new enum

If you recompile `title` against the version of `Status` that includes `SUSPENDED`, the switch expression **missing a branch** and having no `default` will fail to compile. This early feedback is very valuable: developers are forced to decide how `SUSPENDED` should be handled.

### 8.2. Replacing only the enum bytecode while running previously compiled code

In shared-library environments, code calling a `switch expression` may have been compiled before the enum added a constant. If the program runs with **the new enum class** while keeping **the old compiled switch**, a new value like `SUSPENDED` can hit the synthetic guard branch generated by the compiler for an enum switch expression deemed exhaustive at compile time. In Java 17, this scenario can result in **`IncompatibleClassChangeError`**.

Do not assume that "omitting `default` means the runtime will always gracefully handle new values". **The strongest guarantee happens at recompilation time**; when distributing modules/libraries that can evolve independently, manage versions, binary compatibility, and run integration tests against actual deployed versions.

### 8.3. What if `default` is present when adding a new constant?

When the new enum adds `SUSPENDED`, a switch with `default` will still normally compile and run:

~~~java
static String title(Status status) {
    return switch (status) {
        case NEW -> "New";
        case ACTIVE -> "Active";
        case CLOSED -> "Closed";
        default -> "Other";
    };
}
~~~

If `"Other"` is the desired policy for new statuses, this can be a sensible choice. If every status must have its own dedicated label/calculation, `default` makes omitting `SUSPENDED` harder to spot at compile time.

## 9. Complete Java 17 example: converting order statuses

Create `OrderStatusDemo.java` in an empty directory:

~~~java
import java.util.Objects;

public final class OrderStatusDemo {
    private OrderStatusDemo() {
    }

    enum Status {
        CREATED, PAID, SHIPPED, DELIVERED, CANCELLED
    }

    static String label(Status status) {
        Objects.requireNonNull(status, "status");

        return switch (status) {
            case CREATED -> "Created";
            case PAID -> "Paid";
            case SHIPPED -> "Shipped";
            case DELIVERED -> "Delivered";
            case CANCELLED -> "Cancelled";
        };
    }

    static boolean canCancel(Status status) {
        Objects.requireNonNull(status, "status");

        return switch (status) {
            case CREATED, PAID -> true;
            case SHIPPED, DELIVERED, CANCELLED -> false;
        };
    }

    static int priority(Status status) {
        Objects.requireNonNull(status, "status");

        return switch (status) {
            case CREATED -> 10;
            case PAID -> 20;
            case SHIPPED -> {
                int base = 30;
                int trackingBonus = 5;
                yield base + trackingBonus;
            }
            case DELIVERED, CANCELLED -> 0;
        };
    }

    static String labelOrMissing(Status status) {
        if (status == null) {
            return "Missing status";
        }
        return label(status);
    }

    public static void main(String[] args) {
        for (Status status : Status.values()) {
            System.out.printf(
                    "%s -> %s, canCancel=%s, priority=%d%n",
                    status,
                    label(status),
                    canCancel(status),
                    priority(status));
        }

        System.out.println("Null input -> " + labelOrMissing(null));
    }
}
~~~

The example code demonstrates four key points:

1. `label` exhaustively maps all five enum values **without `default`**.
2. `canCancel` groups multiple constants sharing the same business meaning into one branch, while still naming every constant.
3. `priority` uses a block with `yield` to compute a value from multiple statements.
4. `labelOrMissing` illustrates a policy handling a `null` reference **before** calling a switch that is already exhaustive over enum constants.

To compile and run with JDK 17 from the directory containing the file:

~~~bash
javac --release 17 -encoding UTF-8 OrderStatusDemo.java
java OrderStatusDemo
~~~

Expected output:

~~~text
CREATED -> Created, canCancel=true, priority=10
PAID -> Paid, canCancel=true, priority=20
SHIPPED -> Shipped, canCancel=false, priority=35
DELIVERED -> Delivered, canCancel=false, priority=0
CANCELLED -> Cancelled, canCancel=false, priority=0
Null input -> Missing status
~~~

`Status.values()` iterates over all enum constants declared in the current version. When adding a new constant, you can edit `Status` and recompile to observe compiler errors caused by switch expressions missing the corresponding branch.

### Practicing enum evolution

Try adding `RETURNED`:

~~~java
enum Status {
    CREATED, PAID, SHIPPED, DELIVERED, CANCELLED, RETURNED
}
~~~

Then recompile `OrderStatusDemo.java`. The methods `label`, `canCancel`, and `priority` must now all have `RETURNED` added to an appropriate branch to become exhaustive again. This turns a compile error into a reminder to update business behavior.

If you merely add `default -> "Other"` to `label` to bypass the error without deciding the meaning of `RETURNED`, the program may run yet fail to satisfy requirements for displaying the new status. Choose branches according to actual semantics before deciding to add `default`.

## 10. Common errors when using `switch` on enums

### 10.1. Missing a constant without `default`

~~~java
// Suppose Status has CREATED, PAID, SHIPPED, DELIVERED, CANCELLED.
String text = switch (status) {
    case CREATED -> "Created";
    case PAID -> "Paid";
    case SHIPPED -> "Shipped";
    case DELIVERED -> "Delivered";
}; // Error: missing CANCELLED
~~~

**Cause:** the switch expression is not exhaustive. **Fix:** add `case CANCELLED -> ...` or add `default` if the policy groups remaining values.

### 10.2. Assuming `default` catches `null`

~~~java
// status == null
String text = switch (status) {
    case PAID -> "Paid";
    default -> "Other";
};
~~~

**Result:** `NullPointerException` in Java 17. **Fix:** choose an explicit policy for `null` before the switch, such as `Objects.requireNonNull(status)` or `if (status == null) return ...;`.

### 10.3. Using qualified enum constant names in `case` labels

For a switch selector of type `Status`, standard syntax in Java 17 is:

~~~java
case PAID -> "Paid";
~~~

Do not write enum constant labels as `case Status.PAID -> ...` in a regular Java 17 `switch`. Constant names in branches must follow proper enum label syntax; the compiler already knows the selector type from `status`.

### 10.4. Forgetting `yield` with a multi-statement block

~~~java
// Invalid: block branch does not produce a value.
int value = switch (status) {
    case PAID -> {
        int base = 10;
        int bonus = 5;
        // Missing yield base + bonus;
    }
    default -> 0;
};
~~~

**Fix:** write `yield base + bonus;` in the block branch, or `throw` if that is an error path. A switch expression cannot complete without resolving its value.

### 10.5. Using `break` to return a value

With switch expressions in Java 17, **do not use `break someValue;`** as in older experimental designs. Use:

~~~java
int value = switch (status) {
    case PAID -> 1;
    default -> {
        int fallback = 0;
        yield fallback;
    }
};
~~~

`yield` is the standard syntax for yielding a value out of a switch expression block branch.

### 10.6. Using `default` to ignore unknown states

~~~java
return switch (status) {
    case CREATED -> "new";
    default -> "done";
};
~~~

If `"done"` is wrong for `PAID`, `SHIPPED`, `CANCELLED`, or future states, `default` hides a business bug. Verify whether **all remaining values** truly share the exact same behavior before choosing this style.

### 10.7. Relying on constant order instead of names and meaning

Every `enum` has `ordinal()`, but you should not rely on `ordinal` ordering for long-term business mappings: inserting or reordering constants changes ordinals. Switching by **constant name** is clearer and far more resilient in classifications like `label` or `canCancel`.

## 11. Building a test matrix for exhaustiveness

The compiler checks that a switch expression on an enum has branches covering the entire type at compile time, but **does not check the business correctness** of each branch's result. A function can cover all five constants and still return the wrong string for `SHIPPED`.

For the example in section 9, we can construct an expectation table:

| `Status` | `label` | `canCancel` | `priority` |
|---|---|---|---:|
| `CREATED` | `Created` | `true` | 10 |
| `PAID` | `Paid` | `true` | 20 |
| `SHIPPED` | `Shipped` | `false` | 35 |
| `DELIVERED` | `Delivered` | `false` | 0 |
| `CANCELLED` | `Cancelled` | `false` | 0 |

You can use JUnit or your project's testing framework to verify each row. In particular, place `null` cases in their own test group: the contract of `label(null)` (throws an exception) and `labelOrMissing(null)` (returns `Missing status`) are two distinct contracts.

A simple Java test without external libraries might look like:

~~~java
static void checkLabels() {
    for (Status status : Status.values()) {
        String actual = label(status);
        if (actual == null || actual.isBlank()) {
            throw new AssertionError("Missing label for " + status);
        }
    }
}
~~~

This loop catches `null` or blank results for a constant, but **does not by itself prove** that the string `"Shipped"` is business-correct. To verify exact content, compare against the expected value for each constant.

If a new constant is added to the enum and all switch expressions list the old constants without `default`, compile errors can surface **before tests even run**. If `default` is used, behavioral tests become even more important for catching unintended mappings.

## 12. Practice exercises

### Exercise 1 — Complete the switch expression

Given:

~~~java
enum Priority {
    LOW, MEDIUM, HIGH, CRITICAL
}
~~~

Complete the following method so that it compiles on Java 17 **without `default`**:

~~~java
static int score(Priority priority) {
    return switch (priority) {
        case LOW -> 1;
        case MEDIUM -> 2;
        case HIGH -> 3;
        // What is missing?
    };
}
~~~

Explain why the compiler rejects the version with a missing branch.

### Exercise 2 — Predict the impact of adding a constant

Suppose `BLOCKER` is added to `Priority`. Compare the two methods:

~~~java
static String categoryA(Priority priority) {
    return switch (priority) {
        case LOW -> "slow";
        case MEDIUM -> "normal";
        case HIGH -> "fast";
        case CRITICAL -> "urgent";
    };
}

static String categoryB(Priority priority) {
    return switch (priority) {
        case LOW -> "slow";
        default -> "other";
    };
}
~~~

When recompiling against the enum with `BLOCKER`, which method gets a compile error? Which method still runs, yet needs its grouping rule reviewed?

### Exercise 3 — Handle `null` under two policies

Write two versions of `describe(Priority priority)`:

1. A version rejecting `null` using `Objects.requireNonNull`.
2. A version returning `"Missing priority"` when `priority == null`.

Both must still exhaustively handle `LOW`, `MEDIUM`, `HIGH`, and `CRITICAL` using a switch expression. Try calling each version with `null` and with a valid constant.

### Exercise 4 — Use `yield` for a calculation branch

Write `int estimateMinutes(Priority priority)` returning `240` for `LOW`, `120` for `MEDIUM`, `60` for `HIGH`, and `15` for `CRITICAL`. For the `HIGH` branch specifically, use a block calculating `baseMinutes - savedMinutes` and return the result via `yield`.

### Exercise 5 — Deciding on `default` by business requirements

An application has an enum:

~~~java
enum PaymentState {
    CREATED, AUTHORIZED, CAPTURED, REFUNDED, FAILED
}
~~~

The requirement is to display **a dedicated message for each state**. Decide whether to use or omit `default`, then explain what happens when `PARTIALLY_REFUNDED` is added in a later release.

### Answer hints

1. Add `case CRITICAL -> 4;`; when a constant is missing, the switch expression is not exhaustive.
2. `categoryA` fails to compile on rebuild because `BLOCKER` is missing. `categoryB` still has `default`, so you need to review whether `"other"` makes sense.
3. `requireNonNull` throws `NullPointerException`; checking `null` before the switch can return a message string. `default` inside the switch cannot substitute for either mechanism.
4. Use `case HIGH -> { int baseMinutes = 90; int savedMinutes = 30; yield baseMinutes - savedMinutes; }`.
5. List all constants and omit `default` if every state requires its own message. When `PARTIALLY_REFUNDED` is added, recompiling will prompt updating the branch.

## 13. Principles to remember

1. **`switch expression` always requires exhaustiveness.** Every selector value in the domain Java checks must lead to a branch that produces a value or throws an exception.
2. With **`enum`**, listing all constants allows **omitting `default`**. This is usually good practice when every state must be handled intentionally.
3. **`default`** is a tool for handling remaining values, not a mandatory requirement on every enum switch. Use it when that genuinely matches business policy.
4. **Adding an enum constant and recompiling** will make switch expressions that listed all old constants without `default` fail to compile, forcing the author to review the new branch.
5. **`default` does not catch `null`** in standard Java 17 switches. Choose a `null` policy before entering the switch.
6. Use **`->`** for short branches, and **`yield`** when a branch needs a block to compute a value. Avoid relying on preview syntax or obsolete behaviors.
7. Compiler-checked exhaustiveness **does not replace result testing**. A branch can exist syntactically and still be wrong for business logic.

From these principles, you can write `switch expression` on `enum` that is both concise and easy to track as state models evolve. Java 17 protects you against missing constants at compile time, while how you organize `case` labels and use `default` determines long-term design quality.

### References

- [Oracle Java 17 — Switch Expressions](https://docs.oracle.com/en/java/javase/17/language/switch-expressions.html).
- [Java SE 17 Language Specification — Section 14.11: The switch Statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.11).
- [Java SE 17 Language Specification — Section 15.28: Switch Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.28).
