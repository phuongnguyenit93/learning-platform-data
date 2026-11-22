# Comparing with `==` and Using Enums in `switch` — Java 17+

In Java, an `enum` describes **a predefined, explicitly typed set of named constants**. When a variable has type `OrderStatus`, it can only reference one of the constants of that enum itself or hold the value `null`. Each enum constant is an **object** created by Java according to the enum definition, and the same constant always points to the same object within the scope of a single runtime definition of the enum. Therefore, **`==` is the natural and safe way to compare** when you want to know whether two variables represent **the same enum constant**.

Another benefit: enum is a selector type directly supported by `switch`. Instead of `if/else` comparing strings like `"NEW"`, `"PAID"`, you can branch on `OrderStatus.NEW`, `OrderStatus.PAID` with the compiler checking the type and `case` labels. With Java 17, there is the traditional **switch statement**, the `case ... ->` form, and the **switch expression** that returns a value.

This lesson belongs to the **Java core – class-object** module, **Enum** group, **Comparing with == and using enums in switch** section. The examples use Java **17+**, specifying the file, run command, and corresponding stdout. Intentionally incorrect snippets are clearly marked as **compilation error illustrations** and must not be understood as runnable programs.

## 1. The Object Nature of Enum Constants

Declaration:

~~~java
enum OrderStatus {
    NEW, PROCESSING, PAID, CANCELLED
}
~~~

This is a valid type declaration. `NEW`, `PROCESSING`, `PAID`, `CANCELLED` are **enum constants** of **type OrderStatus**. They are not character strings and not integers automatically replaced with `0`, `1`, `2` by the compiler.

You can write:

~~~java
OrderStatus a = OrderStatus.NEW;
OrderStatus b = OrderStatus.NEW;
OrderStatus c = OrderStatus.PAID;
~~~

This is a valid snippet following the enum declaration, placed inside an appropriate method or initializer. `a` and `b` reference **the same constant**; `c` references a different constant. All three variables have type OrderStatus.

Java does not allow a program to arbitrarily use `new OrderStatus()` to create an additional constant outside the declaration. The enum contract keeps the set of constants defined in the source, except for the possibility of a reference variable having the value `null`.

## 2. Why Use `==` with Enums?

The `==` operator on references means **the same object reference**. For enums, each constant has a stable identity in its corresponding runtime enum class, so:

- `OrderStatus.NEW == OrderStatus.NEW` is `true`.
- `OrderStatus.NEW == OrderStatus.PAID` is `false`.
- Two variables pointing to `OrderStatus.NEW` yield `true` even when assigned in two different places.
- `status == null` is valid and does not invoke any method on `status`.
- Comparing a constant with a `null` variable, such as `status == OrderStatus.NEW`, returns `false` and **does not throw NullPointerException**.

Unlike String, you **do not need to consider string content or string interning** to decide whether two enum constants are the same.

**Suggested convention:** write `if (status == OrderStatus.PAID)` when you need to check an enum value. The form `OrderStatus.PAID == status` is also valid, even when status is null; choose one style consistently across the project.

## 3. Complete Program 1 — Identity and `==`

File **`EnumIdentityDemo.java`**:

~~~java
enum OrderStatus {
    NEW, PROCESSING, PAID, CANCELLED
}

public class EnumIdentityDemo {
    public static void main(String[] args) {
        OrderStatus first = OrderStatus.NEW;
        OrderStatus second = OrderStatus.NEW;
        OrderStatus paid = OrderStatus.PAID;

        System.out.println("first=" + first);
        System.out.println("same=" + (first == second));
        System.out.println("different=" + (first == paid));
        System.out.println("same type="
                + (first.getClass() == paid.getClass()));

        OrderStatus unknown = null;
        System.out.println("null is NEW="
                + (unknown == OrderStatus.NEW));
        System.out.println("null is null=" + (unknown == null));
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 EnumIdentityDemo.java
java EnumIdentityDemo
~~~

**Exact stdout:**

~~~text
first=NEW
same=true
different=false
same type=true
null is NEW=false
null is null=true
~~~

`first` and `second` both reference OrderStatus.NEW; `paid` references a different constant. `getClass()` returns the same runtime class because this enum has no constant-specific class bodies. The null comparison line illustrates the advantage of `==`: there is no need to invoke a method on a possibly null reference.

**Limitation of the identity statement:** each enum class loaded by a class loader has a corresponding set of enum constants. In systems with multiple class loaders, do not assume that merely sharing matching *textual names* means two constants belong to the same runtime type. In normal Java code with the same enum type, `==` is the right choice.

## 4. `equals` with Enums: Same Result When Reference Is Non-Null

`java.lang.Enum` already has an `equals(Object)` implementation based on **reference identity**, and this method is `final`: your enum cannot override it to change the meaning of equality.

Therefore, when `a` is non-null:

~~~java
a == b
a.equals(b)
~~~

usually produce the same boolean result for enum references of the same type. But **`a.equals(b)` invokes a method on a**, so if `a == null` it throws `NullPointerException`, whereas `a == b` remains a valid reference comparison.

These kinds of comparisons answer the question **"is it the same enum constant?"**. They do not compare business attributes that you might attach to an enum, such as display code, description, or fee level.

Why do you not need to write `Enum.valueOf(...)` or `name().equals(...)` to compare? Because those operations convert or read **names**, whereas you already have enum objects of the same type to compare directly.

## 5. Complete Program 2 — `==`, `equals`, and `null`

File **`EnumEqualsNullDemo.java`**:

~~~java
enum Level {
    LOW, MEDIUM, HIGH
}

public class EnumEqualsNullDemo {
    public static void main(String[] args) {
        Level a = Level.HIGH;
        Level b = Level.HIGH;
        Level c = Level.LOW;

        System.out.println("a==b=" + (a == b));
        System.out.println("a.equals(b)=" + a.equals(b));
        System.out.println("a==c=" + (a == c));
        System.out.println("a.equals(c)=" + a.equals(c));

        Level missing = null;
        System.out.println("missing==HIGH="
                + (missing == Level.HIGH));
        System.out.println("HIGH.equals(missing)="
                + Level.HIGH.equals(missing));

        try {
            System.out.println(missing.equals(Level.HIGH));
        } catch (NullPointerException ex) {
            System.out.println("missing.equals throws="
                    + ex.getClass().getSimpleName());
        }
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 EnumEqualsNullDemo.java
java EnumEqualsNullDemo
~~~

**Stdout:**

~~~text
a==b=true
a.equals(b)=true
a==c=false
a.equals(c)=false
missing==HIGH=false
HIGH.equals(missing)=false
missing.equals throws=NullPointerException
~~~

`Level.HIGH.equals(missing)` is safe because the receiver is a non-null enum constant. However, when both variables are already enums, `==` is shorter and creates no risk of calling a method on a null variable.

## 6. Do Not Confuse Comparing Enums with Comparing Strings

Consider two design options:

~~~java
String statusText = "PAID";
OrderStatus status = OrderStatus.PAID;
~~~

This is a snippet within the scope that has the OrderStatus enum. The two variables do not have the same type: one variable is String, the other is OrderStatus.

- String describes **text**; compare String contents with `equals` or `Objects.equals`.
- Enum describes a **typed constant**; compare for the same constant with `==`.
- `OrderStatus.PAID.name()` returns the String `"PAID"`, but that String is not the OrderStatus.PAID object.
- Do not convert an enum to String just to write `if ("PAID".equals(status.name()))` when you already have an enum reference; that approach is longer and can cause NullPointerException if status is null.
- If the **input data is text** from JSON, a file, or a request, convert it once according to the input policy and then work with the enum in domain code.

For example: `OrderStatus.valueOf("PAID")` returns OrderStatus.PAID; `valueOf("paid")` does not automatically ignore uppercase/lowercase, and an input that does not match the name will throw `IllegalArgumentException`. Input normalization is the responsibility of the data-receiving API, not of enum comparison.

## 7. Complete Program 3 — Parse Text and Then Compare Constants

File **`EnumParsingComparisonDemo.java`**:

~~~java
import java.util.Locale;

enum Access {
    GUEST, MEMBER, ADMIN
}

public class EnumParsingComparisonDemo {
    static Access parse(String raw) {
        if (raw == null) {
            throw new IllegalArgumentException("missing access");
        }
        return Access.valueOf(
                raw.trim().toUpperCase(Locale.ROOT));
    }

    public static void main(String[] args) {
        Access fromText = parse(" admin ");
        System.out.println("parsed=" + fromText);
        System.out.println("is admin="
                + (fromText == Access.ADMIN));

        try {
            parse("owner");
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid="
                    + ex.getClass().getSimpleName());
        }
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 EnumParsingComparisonDemo.java
java EnumParsingComparisonDemo
~~~

**Stdout:**

~~~text
parsed=ADMIN
is admin=true
invalid=IllegalArgumentException
~~~

The parse function explicitly decides how to handle whitespace/case. After obtaining Access.ADMIN, the program compares the constant with `==` rather than continuing to compare strings. For real systems, consider versioning of external codes: `name()` is suitable for internal identity but is not always a stable external integration code.

## 8. `switch` on Enums Helps Type-Check Branches

Java allows using an enum expression as a selector:

~~~java
switch (status) {
    case NEW:
        System.out.println("New");
        break;
    case PAID:
        System.out.println("Paid");
        break;
    default:
        System.out.println("Other");
}
~~~

This is a valid snippet when status is a variable of type OrderStatus. In `case NEW:`, the enum constant name is written **without `OrderStatus.`** according to standard Java 17 enum case label syntax. Java knows the selector has type OrderStatus, so it resolves `NEW` as the corresponding constant.

**Unlike comparing with `==`:** `switch` uses a selector to choose **a control path**, which is convenient when there are multiple branches. You can still use `if (status == OrderStatus.NEW)` for one or two simple conditions.

Do not write `case "NEW":` if the selector is OrderStatus; a String literal is not an enum constant. Also do not put `case OrderStatus.NEW:` directly in an enum switch under standard Java 17 case label rules.

## 9. Traditional Switch Statement: Understanding `break`

The colon syntax `case X:` of a **switch statement** supports **fall-through**: if a branch is selected and does not have a `break`, `return`, `throw`, or other exit mechanism, execution can continue into the statements of the next case label.

Example:

~~~java
switch (status) {
    case NEW:
        System.out.println("Create");
        break;
    case PROCESSING:
        System.out.println("In progress");
        break;
    case PAID:
        System.out.println("Completed");
        break;
    case CANCELLED:
        System.out.println("Stopped");
        break;
}
~~~

This is a valid illustrative switch statement inside a method with an OrderStatus selector. A `default` is not strictly required if you intentionally list all cases and do not need a default behavior. However, with a **switch statement**, the compiler does not require every enum constant to have a case label as it does when using a **switch expression**.

A switch statement may execute no branch at all when a matching case is missing and there is no default. Therefore, if the branching represents mandatory behavior, you should consider an explicit handling path for every constant.

## 10. Complete Program 4 — Switch Statement and `break`

File **`EnumSwitchStatementDemo.java`**:

~~~java
enum Ticket {
    OPEN, ASSIGNED, RESOLVED, CLOSED
}

public class EnumSwitchStatementDemo {
    static void printAction(Ticket ticket) {
        switch (ticket) {
            case OPEN:
                System.out.println("create task");
                break;
            case ASSIGNED:
                System.out.println("work on task");
                break;
            case RESOLVED:
                System.out.println("verify result");
                break;
            case CLOSED:
                System.out.println("archive");
                break;
        }
    }

    public static void main(String[] args) {
        printAction(Ticket.OPEN);
        printAction(Ticket.RESOLVED);
        printAction(Ticket.CLOSED);
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 EnumSwitchStatementDemo.java
java EnumSwitchStatementDemo
~~~

**Stdout:**

~~~text
create task
verify result
archive
~~~

The `printAction` method is `void`: it performs a side action of printing the result and does not return a value. Each case has `break`, so it only prints the selected branch without falling through into the next branch.

## 11. Grouping Multiple Enum Constants into the Same Branch

When multiple states need the same behavior, you can group labels in a colon-style switch statement:

~~~java
switch (status) {
    case NEW:
    case PROCESSING:
        System.out.println("Not finished");
        break;
    case PAID:
    case CANCELLED:
        System.out.println("Finalized");
        break;
}
~~~

This is a valid snippet for OrderStatus. Multiple consecutive case labels **with no statements in between** express an intentional sharing of code, not a missing `break` bug.

With Java 17, the arrow form is usually more concise:

~~~java
switch (status) {
    case NEW, PROCESSING -> System.out.println("Not finished");
    case PAID, CANCELLED -> System.out.println("Finalized");
}
~~~

The `case NEW, PROCESSING ->` syntax lists multiple enum constants in a single label; it does not cause fall-through between arrow branches.

**Remember:** intentionally grouping labels is different from forgetting `break` between two branches that have different behaviors.

## 12. Complete Program 5 — Arrow-Style Grouped Cases

File **`EnumGroupedCasesDemo.java`**:

~~~java
enum Shipment {
    CREATED, PACKED, SHIPPED, DELIVERED, RETURNED
}

public class EnumGroupedCasesDemo {
    static String phase(Shipment shipment) {
        return switch (shipment) {
            case CREATED, PACKED -> "Preparing";
            case SHIPPED -> "In transit";
            case DELIVERED, RETURNED -> "Finished";
        };
    }

    public static void main(String[] args) {
        System.out.println("CREATED="
                + phase(Shipment.CREATED));
        System.out.println("SHIPPED="
                + phase(Shipment.SHIPPED));
        System.out.println("RETURNED="
                + phase(Shipment.RETURNED));
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 EnumGroupedCasesDemo.java
java EnumGroupedCasesDemo
~~~

**Stdout:**

~~~text
CREATED=Preparing
SHIPPED=In transit
RETURNED=Finished
~~~

This is a **switch expression**, not a statement: the method immediately returns the String computed by the expression. All five Shipment constants are covered, so no `default` branch is needed.

## 13. Arrow Form of the Switch Statement: No Fall-Through

Java 17 allows writing a **switch statement** using switch rules of the form `case CONSTANT -> statement`. Example:

~~~java
switch (status) {
    case NEW -> System.out.println("Created");
    case PROCESSING -> System.out.println("Working");
    case PAID -> System.out.println("Finished");
    case CANCELLED -> System.out.println("Cancelled");
}
~~~

This is a **statement** because the result is used to execute print statements, not an expression that assigns or returns a value. The arrow `->` ensures that a selected rule does not automatically execute the body of the next rule.

If a rule needs multiple statements, use a block:

~~~java
switch (status) {
    case NEW -> {
        System.out.println("validate");
        System.out.println("accept");
    }
    case PROCESSING, PAID, CANCELLED ->
            System.out.println("already recorded");
}
~~~

This snippet is also a valid switch statement. **Do not use `yield` arbitrarily to return a value from a statement**; `yield` is the mechanism for supplying a value from a block inside a switch expression. If the method needs a result, switch to a switch expression or use a return according to normal method rules.

## 14. Switch Expression: Obtaining a Value from an Enum

When the requirement is **mapping an enum to a value**, a switch expression is usually short, clear, and helps the compiler verify exhaustiveness:

~~~java
int fee = switch (tier) {
    case BASIC -> 0;
    case PLUS -> 20;
    case PREMIUM -> 50;
};
~~~

This is a valid Java 17 snippet if `tier` has an enum type with exactly the three constants BASIC, PLUS, PREMIUM.

Differences from a traditional switch statement:

- An **expression** produces a typed value, here `int`.
- Each branch can be an expression, a block with `yield`, or a `throw`.
- The expression must be **exhaustive**: all valid selector values must be covered; with enums, cases for all constants satisfy this requirement without needing default.
- The `->` form has no fall-through.
- `break` from a switch statement is not used to supply a value instead of `yield` in a switch expression.

With `default`, the compiler has a catch-all branch; however, adding default unconditionally can hide the opportunity for the compiler to remind you to update the expression when a new constant is added to the enum.

## 15. Complete Program 6 — Mapping an Enum to a Value

File **`EnumSwitchExpressionDemo.java`**:

~~~java
enum Subscription {
    FREE, STANDARD, BUSINESS
}

public class EnumSwitchExpressionDemo {
    static int monthlyFee(Subscription subscription) {
        return switch (subscription) {
            case FREE -> 0;
            case STANDARD -> 99;
            case BUSINESS -> 249;
        };
    }

    static String description(Subscription subscription) {
        return switch (subscription) {
            case FREE -> "Starter";
            case STANDARD -> "Personal";
            case BUSINESS -> "Team";
        };
    }

    public static void main(String[] args) {
        System.out.println("FREE="
                + monthlyFee(Subscription.FREE));
        System.out.println("STANDARD="
                + monthlyFee(Subscription.STANDARD));
        System.out.println("BUSINESS="
                + monthlyFee(Subscription.BUSINESS));
        System.out.println("description="
                + description(Subscription.BUSINESS));
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 EnumSwitchExpressionDemo.java
java EnumSwitchExpressionDemo
~~~

**Stdout:**

~~~text
FREE=0
STANDARD=99
BUSINESS=249
description=Team
~~~

The values 99 and 249 are only example data, not real-world pricing. For a commercial system, pricing policies may require a separate model or a configuration data source; switch mapping is best suited for small, fixed rules tied to an enum.

## 16. Multiple Statements in a Rule: Using a Block and `yield`

A switch expression can compute a result across multiple lines using `yield`:

~~~java
String text = switch (level) {
    case LOW -> "low";
    case MEDIUM -> {
        String prefix = "middle";
        yield prefix + " priority";
    }
    case HIGH -> "high";
};
~~~

This is a valid snippet inside a method that has `Level` as in the previous example.

`yield expression;` **returns a value for the switch expression**, not a `return` from the enclosing method containing the switch. For example, if the method is computing a string for multiple items, `yield` only completes that switch expression; statements after the expression can still run.

Block branches must ensure every normal path supplies an appropriate value via `yield` or ends with `throw` when an error condition occurs. Execution cannot reach the end of the block without supplying a value for the switch expression.

## 17. Complete Program 7 — Using `yield` in a Switch Expression

File **`EnumSwitchYieldDemo.java`**:

~~~java
enum Risk {
    LOW, MEDIUM, HIGH
}

public class EnumSwitchYieldDemo {
    static String explain(Risk risk) {
        return switch (risk) {
            case LOW -> "No review";
            case MEDIUM -> {
                int checks = 2;
                yield "Review " + checks + " checks";
            }
            case HIGH -> {
                String action = "Escalate";
                yield action + " now";
            }
        };
    }

    public static void main(String[] args) {
        System.out.println("LOW=" + explain(Risk.LOW));
        System.out.println("MEDIUM=" + explain(Risk.MEDIUM));
        System.out.println("HIGH=" + explain(Risk.HIGH));
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 EnumSwitchYieldDemo.java
java EnumSwitchYieldDemo
~~~

**Stdout:**

~~~text
LOW=No review
MEDIUM=Review 2 checks
HIGH=Escalate now
~~~

`MEDIUM` and `HIGH` use blocks because they need to declare local variables and then build the result. `LOW` only needs a single expression, so a direct arrow rule is sufficient.

## 18. The Fall-Through Trap in Colon Form

Suppose a programmer forgets `break`:

~~~java
switch (step) {
    case STARTED:
        System.out.println("start");
    case VERIFIED:
        System.out.println("verify");
        break;
    case FINISHED:
        System.out.println("finish");
        break;
}
~~~

This is a valid Java 17 snippet, but if `step == STARTED`, it prints **two lines**, `start` and `verify`, because there is no `break` after STARTED. If you want to execute only one branch, add `break` or use arrow rules.

Sometimes fall-through is used intentionally to group branches, but readers new to the code can easily assume that every `case:` automatically stops at the end of its statements. That is **not true** for the traditional colon form.

## 19. Complete Program 8 — Comparing Fall-Through and Arrow

File **`EnumFallThroughDemo.java`**:

~~~java
enum Phase {
    STARTED, VERIFIED, FINISHED
}

public class EnumFallThroughDemo {
    static void colon(Phase phase) {
        switch (phase) {
            case STARTED:
                System.out.println("colon:start");
            case VERIFIED:
                System.out.println("colon:verify");
                break;
            case FINISHED:
                System.out.println("colon:finish");
                break;
        }
    }

    static void arrow(Phase phase) {
        switch (phase) {
            case STARTED ->
                    System.out.println("arrow:start");
            case VERIFIED ->
                    System.out.println("arrow:verify");
            case FINISHED ->
                    System.out.println("arrow:finish");
        }
    }

    public static void main(String[] args) {
        colon(Phase.STARTED);
        arrow(Phase.STARTED);
        colon(Phase.FINISHED);
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 EnumFallThroughDemo.java
java EnumFallThroughDemo
~~~

**Stdout:**

~~~text
colon:start
colon:verify
arrow:start
colon:finish
~~~

The example intentionally exposes fall-through in the STARTED branch of the `colon` method. In business code, do not accidentally turn a `case:` with `break` into a branch without `break`, or vice versa, without verifying the expected behavior.

## 20. `null` and Enum Switch in Java 17

This is a very common point of confusion once you are used to `==`:

~~~java
OrderStatus status = null;

boolean isNew = (status == OrderStatus.NEW);
~~~

The two lines above are valid; `isNew` is false. **However, a normal switch on a null selector throws `NullPointerException`** in Java 17 when not using special preview features.

That means:

- `status == OrderStatus.NEW` is a null-safe reference comparison.
- `OrderStatus.NEW.equals(status)` is a valid method call that returns false.
- `status.equals(OrderStatus.NEW)` throws NPE if status is null.
- `switch (status) { ... }` does not automatically select `default` for null in standard Java 17.
- `switch (status)` as an expression also does not automatically return a fallback value when status is null.

**How to handle it:** establish a "status is non-null" invariant through validation or `Objects.requireNonNull`, or normalize null to a constant such as `UNKNOWN` according to an explicit policy. Do not unconditionally turn null into UNKNOWN if business logic must distinguish "missing data" from "truly unknown state".

## 21. Complete Program 9 — Handling Null Before Switch

File **`EnumNullSwitchDemo.java`**:

~~~java
import java.util.Objects;

enum State {
    READY, STOPPED, UNKNOWN
}

public class EnumNullSwitchDemo {
    static String message(State state) {
        State safe = Objects.requireNonNullElse(
                state, State.UNKNOWN);
        return switch (safe) {
            case READY -> "ready";
            case STOPPED -> "stopped";
            case UNKNOWN -> "unknown";
        };
    }

    static String strict(State state) {
        return switch (state) {
            case READY -> "ready";
            case STOPPED -> "stopped";
            case UNKNOWN -> "unknown";
        };
    }

    public static void main(String[] args) {
        State missing = null;

        System.out.println("null==READY="
                + (missing == State.READY));
        System.out.println("safe=" + message(missing));
        System.out.println("ready=" + message(State.READY));

        try {
            strict(missing);
        } catch (NullPointerException ex) {
            System.out.println("strict="
                    + ex.getClass().getSimpleName());
        }
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 EnumNullSwitchDemo.java
java EnumNullSwitchDemo
~~~

**Exact stdout:**

~~~text
null==READY=false
safe=unknown
ready=ready
strict=NullPointerException
~~~

The `message` method explicitly enforces a null → UNKNOWN policy; the `strict` method does not and will throw NPE on null. These are two different API decisions, rather than one right way and one wrong way for every project.

## 22. Exhaustiveness When Writing a Switch Expression

Suppose an enum has three constants:

~~~java
enum Direction {
    NORTH, SOUTH, EAST
}
~~~

A switch expression must cover all of them. Example:

~~~java
String code = switch (direction) {
    case NORTH -> "N";
    case SOUTH -> "S";
    case EAST -> "E";
};
~~~

This is a valid snippet when `direction` has type Direction. `default` is not required because every constant is listed.

If you remove `case EAST` and still have no `default`, **the switch expression is not exhaustive and the compiler reports an error**. Conversely, a switch statement missing a case may still compile, but executes no behavior for the omitted constants.

**When adding a new enum constant:** if you recompile source containing a switch expression without a default that has not yet handled the new constant, the compiler can force you to update the switch, which is very helpful when refactoring domain states. Mixing binary class files compiled at different times has different runtime rules; you should build and test modules together rather than assuming safety when an enum changes and a consumer has not been rebuilt.

## 23. Complete Program 10 — Exhaustive Expression, Statement with Default

File **`EnumExhaustivenessDemo.java`**:

~~~java
enum Direction {
    NORTH, SOUTH, EAST, WEST
}

public class EnumExhaustivenessDemo {
    static String code(Direction direction) {
        return switch (direction) {
            case NORTH -> "N";
            case SOUTH -> "S";
            case EAST -> "E";
            case WEST -> "W";
        };
    }

    static void describe(Direction direction) {
        switch (direction) {
            case NORTH, SOUTH ->
                    System.out.println("vertical");
            case EAST, WEST ->
                    System.out.println("horizontal");
        }
    }

    public static void main(String[] args) {
        System.out.println("code=" + code(Direction.WEST));
        describe(Direction.NORTH);
        describe(Direction.EAST);
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 EnumExhaustivenessDemo.java
java EnumExhaustivenessDemo
~~~

**Stdout:**

~~~text
code=W
vertical
horizontal
~~~

The switch expression `code` lists all four constants and produces a String. The switch statement `describe` uses grouped arrow cases to perform the side effect of printing to the screen; both avoid fall-through.

## 24. Should You Always Add `default`?

There is no rule that "a switch on an enum must always have default". The decision depends on the goal:

**Wanting the compiler to force considering all states when the enum changes:** for small, domain-closed switch expressions, consider **listing each constant without default**. Adding a new constant will break exhaustiveness upon recompilation.

**Wanting a fallback genuinely specified by business logic:** using `default` is reasonable, for example a policy that treats every ungrouped state as "other", provided that behavior is accepted and tested.

**When using a switch statement for a mandatory side effect:** consider an explicit `default` branch (possibly `throw new IllegalStateException(...)`) if failing to handle a constant should be treated as an error. Do not add `default -> null` just to silence the compiler if null will cause an error in a later step.

Similarly, when needing to accept invalid external data, **`Enum.valueOf` fails before the switch**; a switch default does not replace validation of text input.

## 25. Enum `case` Labels: Common Compile-Time Errors

With selector `OrderStatus status`, standard Java 17 writes:

~~~java
switch (status) {
    case NEW -> System.out.println("new");
    case PROCESSING -> System.out.println("processing");
    case PAID -> System.out.println("paid");
    case CANCELLED -> System.out.println("cancelled");
}
~~~

The code above is a **valid switch statement snippet** inside a method.

Cases that are **intentionally invalid if uncommented**:

~~~java
// case OrderStatus.NEW -> System.out.println("new");
// For a Java 17 enum case label, use the unqualified constant name.

// case "NEW" -> System.out.println("new");
// String literal is incompatible with type OrderStatus.

// case STARTED -> System.out.println("new");
// If OrderStatus does not declare STARTED, there is no valid enum constant.

// case NEW -> System.out.println("A");
// case NEW -> System.out.println("B");
// One constant appears in two case labels of the same switch.
~~~

In Java 17, `case null` is typically tied to pattern switch **preview** features if enabled; this lesson focuses on standard Java 17 switches and does not use preview features. Do not copy `case null` from documentation for a newer Java release and assume it runs on Java 17 without enabling special features.

## 26. Enums with Fields/Methods Still Use `==` and Switch Normally

An enum is not just a list of names. You can attach a constructor, fields, and instance methods:

~~~java
enum Priority {
    LOW(1), MEDIUM(2), HIGH(3);

    private final int weight;

    Priority(int weight) {
        this.weight = weight;
    }

    int weight() {
        return weight;
    }
}
~~~

This is a valid declaration. `Priority.HIGH.weight()` returns 3, but the **identity** of the constant is still Priority.HIGH. `==` checks for **the same constant**, not comparing the weight field.

You can write:

~~~java
Priority first = Priority.HIGH;
Priority second = Priority.HIGH;
boolean same = first == second;
int score = first.weight() + second.weight();
~~~

This is a valid snippet inside a method; `same` is true and `score` equals 6.

If two different constants have the same weight, they are still **not equal under `==`**, because weight is only an attribute, not identity.

## 27. Complete Program 11 — Combining Enum Properties, `==`, and Switch

File **`EnumWithPropertiesDemo.java`**:

~~~java
enum Priority {
    LOW(1), MEDIUM(2), HIGH(3);

    private final int weight;

    Priority(int weight) {
        this.weight = weight;
    }

    int weight() {
        return weight;
    }
}

public class EnumWithPropertiesDemo {
    static String action(Priority priority) {
        return switch (priority) {
            case LOW -> "Queue";
            case MEDIUM -> "Review";
            case HIGH -> "Escalate";
        };
    }

    public static void main(String[] args) {
        Priority first = Priority.HIGH;
        Priority second = Priority.HIGH;

        System.out.println("same=" + (first == second));
        System.out.println("weight=" + first.weight());
        System.out.println("action=" + action(first));
        System.out.println("low action=" + action(Priority.LOW));
    }
}
~~~

Command:

~~~bash
javac -encoding UTF-8 EnumWithPropertiesDemo.java
java EnumWithPropertiesDemo
~~~

**Stdout:**

~~~text
same=true
weight=3
action=Escalate
low action=Queue
~~~

Enum constants can have data and behavior, but adding instance fields does not turn `equals` into field-based equality. In this program, state is identified by the constant; the switch decides the action.

## 28. When to Use Switch, and When to Put Behavior Directly on the Enum?

Both designs have their place.

**Switch outside the enum:** suitable when behavior depends on the caller's context, for example a screen displaying messages differently from a billing policy. It keeps the enum's responsibility small and lets the compiler check the mapping.

**Method inside the enum:** suitable when each constant has behavior intrinsically tied to that value itself, for example `direction.opposite()`. You can write a normal method using switch or constant-specific class bodies; not every enum needs per-constant method overrides.

If dozens of identical switches appear scattered around, that may be a sign of shared logic that should be consolidated. However, **do not force every switch into the enum** if it belongs to an independent policy service, has dependencies, or varies by feature.

## 29. Complete Program 12 — Enum Method Using a Switch Expression

File **`EnumBehaviorDemo.java`**:

~~~java
enum TrafficLight {
    RED, YELLOW, GREEN;

    String instruction() {
        return switch (this) {
            case RED -> "Stop";
            case YELLOW -> "Slow down";
            case GREEN -> "Go";
        };
    }

    TrafficLight next() {
        return switch (this) {
            case RED -> GREEN;
            case GREEN -> YELLOW;
            case YELLOW -> RED;
        };
    }
}

public class EnumBehaviorDemo {
    public static void main(String[] args) {
        TrafficLight current = TrafficLight.RED;

        System.out.println("start=" + current);
        System.out.println("instruction="
                + current.instruction());

        current = current.next();
        System.out.println("next=" + current);
        System.out.println("instruction="
                + current.instruction());

        System.out.println("is GREEN="
                + (current == TrafficLight.GREEN));
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 EnumBehaviorDemo.java
java EnumBehaviorDemo
~~~

**Stdout:**

~~~text
start=RED
instruction=Stop
next=GREEN
instruction=Go
is GREEN=true
~~~

In an enum's instance method, `this` is the enum constant itself invoking the method; the switch expression uses `this` as its selector. The assignment `current = current.next()` only **changes the reference in the current variable**, without modifying the identity or order of the enum constants.

## 30. Do Not Use `ordinal()` Instead of `==` or Switch

Each enum constant has an **ordinal** corresponding to its declaration position, starting from 0. However:

- `status.ordinal()` is **a positional index**, not a stable business code.
- Inserting or reordering enum constants can change ordinals.
- `if (status.ordinal() == 2)` is harder to read than `status == OrderStatus.PAID` and is fragile during refactoring.
- `switch (status.ordinal())` turns an enum-typed branch into an int branch, losing the benefit of enum-based case label checking.
- Do not serialize/persist ordinals to represent long-term state unless a specific protocol tightly controls mapping and versioning.

Similarly, an enum's `compareTo` is based on declaration order; it does not necessarily describe business priority or workflow order. Use an explicit field such as `priority.weight()` when you need a clearly defined number.

## 31. Complete Program 13 — Distinguishing Name, Ordinal, and Identity

File **`EnumOrdinalVsIdentityDemo.java`**:

~~~java
enum Size {
    SMALL, MEDIUM, LARGE
}

public class EnumOrdinalVsIdentityDemo {
    public static void main(String[] args) {
        Size a = Size.MEDIUM;
        Size b = Size.valueOf("MEDIUM");

        System.out.println("name=" + a.name());
        System.out.println("ordinal=" + a.ordinal());
        System.out.println("same=" + (a == b));
        System.out.println("compare=" + a.compareTo(b));
        System.out.println("large ordinal="
                + Size.LARGE.ordinal());
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 EnumOrdinalVsIdentityDemo.java
java EnumOrdinalVsIdentityDemo
~~~

**Stdout:**

~~~text
name=MEDIUM
ordinal=1
same=true
compare=0
large ordinal=2
~~~

`Size.valueOf("MEDIUM")` returns the MEDIUM constant itself, without creating a new Size object. The result of `ordinal()` here depends on the declaration order SMALL, MEDIUM, LARGE; do not use those numbers as stable IDs for a database.

## 32. Enum Sets and Lookup Maps: `EnumSet`, `EnumMap`

When a program needs to check **a group of constants** or map constants to data, `switch` is not the only option.

- `EnumSet<OrderStatus>` stores a set of constants; `contains(status)` expresses membership.
- `EnumMap<OrderStatus, String>` maps each enum constant to data; suitable if the mapping is a table that can be built from configuration or updated.
- `switch` is suitable if you need **behavior control**, per-case logic, or a small, fixed mapping.
- `==` is suitable if you need to compare against **one specific constant**.

Using `EnumSet.of(...)` is often clearer than a chain `if (s == A || s == B || s == C)` when the group of constants has a name and is reused.

Note: `EnumMap.get` returns null if there is no mapping (or if null values are allowed); therefore, if an invariant requires every constant to have a mapping, verify completeness during construction/testing. A switch expression listing all constants has the advantage of compiler-checked exhaustiveness.

## 33. Complete Program 14 — Grouping with `EnumSet`, Mapping with `EnumMap`

File **`EnumCollectionsDemo.java`**:

~~~java
import java.util.EnumMap;
import java.util.EnumSet;
import java.util.Map;
import java.util.Set;

enum Workflow {
    CREATED, REVIEWING, APPROVED, REJECTED
}

public class EnumCollectionsDemo {
    public static void main(String[] args) {
        Set<Workflow> finalStates =
                EnumSet.of(Workflow.APPROVED, Workflow.REJECTED);

        Map<Workflow, String> labels =
                new EnumMap<>(Workflow.class);
        labels.put(Workflow.CREATED, "Created");
        labels.put(Workflow.REVIEWING, "In review");
        labels.put(Workflow.APPROVED, "Approved");
        labels.put(Workflow.REJECTED, "Rejected");

        Workflow current = Workflow.APPROVED;

        System.out.println("is final="
                + finalStates.contains(current));
        System.out.println("is approved="
                + (current == Workflow.APPROVED));
        System.out.println("label=" + labels.get(current));
        System.out.println("size=" + labels.size());
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 EnumCollectionsDemo.java
java EnumCollectionsDemo
~~~

**Stdout:**

~~~text
is final=true
is approved=true
label=Approved
size=4
~~~

The example does not directly print the iteration order of Map or Set, so it does not depend on the text representation of collections. Data is verified using `contains`, `get`, and `size`.

## 34. Different Enum Types: Do Not Arbitrarily Share a Switch or `==`

Suppose:

~~~java
enum PaymentState {
    PAID
}

enum ShippingState {
    PAID
}
~~~

The two enums have constants with the same **textual name**, but `PaymentState.PAID` and `ShippingState.PAID` have two different types. In normal Java code, the direct comparison:

~~~java
// boolean same = PaymentState.PAID == ShippingState.PAID;
~~~

is **an intentionally invalid snippet if uncommented**, because the two operands have reference types that cannot be converted compatibly under the rules of `==`.

You should not do:

~~~java
// PaymentState.PAID.name().equals(ShippingState.PAID.name())
~~~

and then conclude that the two **business states** are the same. The expression comparing the name strings evaluates to true, but that is merely a text match, not type identity.

If you need to map between two domain enums, define an **explicit mapping function** with appropriate cases so readers understand the meaning of each conversion.

## 35. Complete Program 15 — Explicit Mapping Between Two Enum Domains

File **`EnumDomainMappingDemo.java`**:

~~~java
enum PaymentStatus {
    PENDING, PAID, FAILED
}

enum UiBadge {
    NEUTRAL, SUCCESS, ERROR
}

public class EnumDomainMappingDemo {
    static UiBadge badge(PaymentStatus status) {
        return switch (status) {
            case PENDING -> UiBadge.NEUTRAL;
            case PAID -> UiBadge.SUCCESS;
            case FAILED -> UiBadge.ERROR;
        };
    }

    public static void main(String[] args) {
        PaymentStatus state = PaymentStatus.PAID;
        UiBadge badge = badge(state);

        System.out.println("payment=" + state);
        System.out.println("badge=" + badge);
        System.out.println("is success="
                + (badge == UiBadge.SUCCESS));
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 EnumDomainMappingDemo.java
java EnumDomainMappingDemo
~~~

**Stdout:**

~~~text
payment=PAID
badge=SUCCESS
is success=true
~~~

This is a **policy-driven** conversion from a payment status to a display badge, not a type cast between two enums. An enum switch expression helps represent every case exhaustively and keeps the domain types independent.

## 36. What to Check When Replacing `if/else` with `switch`?

You should not replace every if with a switch without reviewing the existing logic.

**Suitable for an enum switch:** expressions that need to select a branch based on **a single enum value**, where each branch has its own behavior/result.

**Possibly better kept as if/else:** conditions combining multiple variables (`amount > limit && status == PAID`), numeric range checks, null policies, or access permissions depending on multiple pieces of data. In Java 17, standard enum switches do not have arbitrary condition guards on individual labels.

Example:

~~~java
if (status == OrderStatus.PAID && amount > 1_000) {
    System.out.println("manual verification");
}
~~~

This is an illustrative snippet; a plain switch on OrderStatus cannot replace the `amount > 1_000` condition directly without writing an additional if inside the branch.

When data can be null, you should validate or normalize it beforehand so that the switch clearly expresses the actual list of states.

## 37. Design Guidelines for Maintainable `switch`

1. **Enum names accurately reflect the domain:** `OrderStatus`, `PaymentStatus`, `TrafficLight` instead of a generic `Type`.
2. **Do not use String magic constants** when the code already has a typed enum.
3. **Compare a single constant with `==`**, without going through `name()` or `ordinal()`.
4. **Use a switch expression** when you need to map an enum to a typed value.
5. **Use arrow rules** to avoid unintended fall-through.
6. **Only use colon fall-through with a clear purpose**, such as grouping multiple case labels.
7. **Choose an explicit null policy**: reject null or map it to UNKNOWN.
8. **Consider omitting default in an exhaustive expression** if you want the compiler to remind you to update it when the enum changes.
9. **Add default if it represents real behavior**, not merely to hide missing branches.
10. **Do not rely on ordinal** as a stable domain code.
11. **Consider the scope of the policy:** does the mapping belong to the enum or to an external service?
12. **Test all constants** and pay attention when adding new constants.
13. **Keep per-case code short**; complex logic can be extracted into separate methods.
14. **Do not mix business state with display text**; use mapping/behavior according to the contract.

## 38. Common Mistakes

| Misconception | What Is True in Java 17 | How to Handle It |
| --- | --- | --- |
| An enum is a String, so `equals` must be used for text comparison | An enum constant is an object with its own enum type | `status == Status.PAID` |
| An enum reference is never null | An enum-typed variable can still hold null | Validate or apply a null policy |
| `status.equals(PAID)` is always safe | Throws NPE if status is null | `status == Status.PAID` |
| `switch(null)` goes to default | A standard enum switch throws NPE | Normalize/check beforehand |
| `case Status.PAID` inside an enum switch | Standard enum case labels use the unqualified name | `case PAID` |
| `case "PAID"` with an enum selector | A String is not an enum constant | `case PAID` |
| `case:` stops automatically | The colon form has fall-through | `break` or arrow |
| An arrow rule still falls through to the next case | Arrow has no fall-through | Rely on `->` syntax |
| A switch expression can omit cases arbitrarily | Must be exhaustive | Add enum cases/default |
| A switch statement must always be exhaustive | Not required like an expression | Review behavior when cases are missing |
| `yield` and `return` are the same | `yield` returns a value for a switch expression | Use the proper construct |
| Every switch must have default | Not required if all enum constants are covered | Decide based on policy |
| `ordinal()` is a business ID | Ordinal is the declaration position | Use a stable domain name/code |
| Two enums with constants of the same name are the same value | They have different typed identities | Explicit mapping |
| Enum `equals` compares fields | Enum.equals uses reference identity | Compare fields separately if truly needed |
| An enum switch handles text input validation | Parsing happens before the switch | Validate input/versioning |

## 39. Self-Practice Exercises

**Question 1.** Why is `Status.READY == Status.READY` always true within the same runtime enum class?

**Question 2.** If two variables of the same enum type point to the same constant, do `equals` and `==` return different results?

**Question 3.** An enum variable has `status = null`. What does `status == Status.READY` return?

**Question 4.** With status being null, what happens with `status.equals(Status.READY)`?

**Question 5.** With status being null, does a standard Java 17 enum switch enter default?

**Question 6.** When the selector has type `Status`, write the case label for the constant READY in Java 17.

**Question 7.** How do the `case READY:` and `case READY ->` forms differ regarding fall-through?

**Question 8.** Can a `switch` be written with multiple enum constants in the same arrow label?

**Question 9.** If a switch expression on an enum omits a constant without having a default, how does the compiler handle it?

**Question 10.** If a switch statement on an enum omits a constant without having a default, does it necessarily cause a compile-time error?

**Question 11.** When is `yield` required in a switch expression?

**Question 12.** Must a switch expression that lists all enum constants include default?

**Question 13.** Why can adding default unconditionally cause you to forget to update the switch when a constant is added to the enum?

**Question 14.** How does `name()` differ from enum identity?

**Question 15.** Why should `ordinal()` not be used as a code stored in a database?

**Question 16.** If an enum has its own constructor and fields, is `==` still valid?

**Question 17.** Do two different constants with the same numeric weight evaluate `==` to true?

**Question 18.** Distinguish between `EnumSet.contains(status)` and `status == ONE_CONSTANT`.

**Question 19.** When should EnumMap be used instead of switch mapping?

**Question 20.** Two different enum domains share the same name `PAID`; is direct `==` between them valid?

**Question 21.** With input `" paid "`, how should it be processed before using an enum switch?

**Question 22.** What does `valueOf("UNKNOWN")` throw on an enum that does not have an UNKNOWN constant?

**Question 23.** If an enum receives a new constant, what kinds of tests should be run?

**Question 24.** If logic depends on both an enum and an amount, is it mandatory to remove if/else completely?

### Reference Answers

1. Because each constant is a unique object for that runtime enum class; both references point to the same object.
2. No, when the receiver is non-null: Enum.equals is based on identity; `==` also compares references.
3. False, without throwing NPE.
4. Throws `NullPointerException`.
5. No: a standard enum switch on null throws NPE before selecting a branch.
6. `case READY:` or `case READY ->` depending on the switch form.
7. Colon allows fall-through if not exited; arrow has no fall-through.
8. Yes: `case READY, PAUSED -> ...` if the enum has those two constants.
9. Reports an error because the expression is not exhaustive.
10. No; however, behavior may be omitted.
11. Inside a block rule that needs to compute/return a value for the expression after multiple statements.
12. No, if all constants are covered.
13. Default accepts the new constant, so the compiler does not force updating individual cases of the exhaustive expression.
14. `name()` is the String of the constant's name, whereas enum identity is a typed object.
15. Ordinal depends on declaration order and can change during refactoring.
16. Yes; fields do not change the constant's identity.
17. No; two different constants are still two objects.
18. EnumSet checks membership in a group, whereas `==` checks for one exact constant.
19. When you need a table-based mapping that can be prepared, configured, or updated, rather than only controlling code flow.
20. No, under direct reference comparison between two incompatible enum types; a domain mapping is needed.
21. Normalize input according to policy (`trim`, uppercase Locale.ROOT if appropriate), parse with `valueOf`, and then compare/switch on the enum.
22. `IllegalArgumentException`.
23. Rebuild consumer switch expressions, and unit tests for all constants, null, and mappings.
24. No; `if` remains suitable for logical expressions combining multiple conditions.

## 40. Core Knowledge Checklist

- Have you used a real enum instead of String constants simulating states?
- Do you understand that the same enum constant has a stable identity?
- For a single constant, have you preferred `==`?
- Is there a null status case, and has it been handled explicitly?
- Do you distinguish `status == CONST`, `status.equals(CONST)`, and `switch(status)` when null?
- In an enum switch, do case labels use unqualified constant names compatible with Java 17?
- Do you distinguish between a **switch statement** and a **switch expression**?
- For a colon statement, have you placed `break` when fall-through is not wanted?
- For arrow rules, do you understand that `break` is not needed to prevent branch fall-through?
- For an expression, have you covered all constants or included a policy-compliant default?
- For a block rule in an expression, have you used `yield` with the right value?
- When adding a new enum constant, have you updated mappings and tests?
- Have you avoided using `ordinal()` as an external code?
- If an enum has fields, have you kept the concepts of identity and attribute value separate?
- If you need to group states, have you considered EnumSet?
- If you need an enum → value lookup table, have you considered EnumMap?
- Have you avoided comparing two enum domains merely because they share the same name?
- Have you ensured example stdout does not depend on hash iteration, class-loader, or runtime implementation names?

## 41. Official Java 17 Documentation

- [JLS 17 §8.9 — Enum Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.9): enum constants, class structure, and rules specific to enums.
- [JLS 17 §15.21 — Equality Operators](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.21): `==` on references.
- [JLS 17 §14.11 — The switch Statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.11): switch statements, labels, rules, and fall-through.
- [JLS 17 §15.28 — Switch Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.28): expressions, exhaustiveness, and results.
- [JLS 17 §14.21 — The yield Statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.21): `yield` in switch expressions.
- [Java SE 17 API — Enum](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Enum.html): equality, `name`, `ordinal`, `compareTo`, `valueOf`.
- [Java SE 17 API — EnumSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/EnumSet.html): optimized set for enum constants.
- [Java SE 17 API — EnumMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/EnumMap.html): mapping keyed by enum.
- [Java SE 17 API — Objects.requireNonNullElse](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html#requireNonNullElse(T,T)): selecting a non-null fallback when required by policy.

## 42. Summary

**Compare for the same enum constant using `==`** because enum constants are objects whose identity is controlled by Java, not strings. `Enum.equals` is also based on identity, but calling `equals` on a null variable throws an exception; `==` does not. Do not use `name()` or `ordinal()` to simulate identity when you already have enum references.

For multiple branches, **`switch` on an enum** expresses intent clearly and is type-checked by the compiler. In Java 17, `case CONSTANT ->` avoids fall-through, a **switch expression** returns a value and requires **exhaustiveness**, while traditional `case CONSTANT:` must be written carefully with `break`. **Null does not automatically enter default** in a standard enum switch: validate or define a fallback before the switch.

During maintenance, prefer constructs that clearly express intent: `==` for a single constant, `EnumSet` for a group, `EnumMap` for a mapping table, and a switch expression for fixed multi-branch logic based on an enum type. Keep policies for input parsing, null handling, and enum constant changes explicit so the code is both type-safe and easy to update.
