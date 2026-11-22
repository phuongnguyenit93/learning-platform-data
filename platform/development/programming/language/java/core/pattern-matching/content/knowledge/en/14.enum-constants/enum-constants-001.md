# Switch with Enum Constants in Java

## 1. Why Are Enums Particularly Well-Suited for Switch?

In Java, an `enum` type defines a finite set of named values. Each value is an **enum constant** of that enum type:

```java
enum Stage {
    QUEUED, RUNNING, DONE, FAILED
}
```

Here `Stage.QUEUED`, `Stage.RUNNING`, `Stage.DONE`, and `Stage.FAILED` are four enum constants. They are defined when writing the program, with explicit names and types; they are not arbitrary strings like `"RUNNING"`.

A `switch` can use enum constants as **case labels** to choose how to handle them:

```java
static String label(Stage stage) {
    return switch (stage) {
        case QUEUED  -> "Chờ";
        case RUNNING -> "Đang chạy";
        case DONE    -> "Hoàn thành";
        case FAILED  -> "Thất bại";
    };
}
```

**`switch (stage)`** is the expression being tested (the selector). The static type of `stage` is `Stage`, so Java knows that the labels `QUEUED`, `RUNNING`, `DONE`, and `FAILED` belong to that enum. When `stage == Stage.DONE`, the result of the expression is `"Hoàn thành"`.

An **enum constant case** selects **one exact named constant**, not an object type, and **does not declare a pattern variable**. This differs from **`case Stage s`** in a Java 21 pattern switch, which matches objects of type `Stage` and introduces the variable `s`.

### Java Version Scope

- **Before Java 14:** `switch` statements using `case NAME:` have supported enums since Java 5.
- **Java 14 and later:** `switch` expressions and arrow branches `case NAME -> ...` were standardized (JEP 361).
- **Java 21 and later:** Pattern Matching for `switch` (JEP 441) was standardized; it allows **qualified enum constants** such as `case Stage.DONE` in a `switch` whose selector has an interface/supertype such as `Object`, alongside type pattern cases and `case null`.

This lesson uses **Java 21** to fully demonstrate both traditional enum switches and modern extensions. The classic syntax parts alone can be used with Java 17 without preview features.

## 2. Core Syntax: `case QUEUED` in a Switch with an Enum Selector

Given the declaration:

```java
enum Stage { QUEUED, RUNNING, DONE, FAILED }
```

You can write:

```java
static String shortLabel(Stage value) {
    return switch (value) {
        case QUEUED  -> "Q";
        case RUNNING -> "R";
        case DONE    -> "D";
        case FAILED  -> "F";
    };
}
```

This is a **switch expression**: the entire `switch` produces a value of type `String` and is used as the method's return value. If `value == Stage.RUNNING`, the `case RUNNING` branch is selected and the result is `"R"`.

When the selector has a concrete enum type, the short constant name `case RUNNING` is resolved against the `Stage` type itself. There is no need to write `case "RUNNING"`: that is a **string**, not an enum constant.

### 2.1. Why Don't Cases Need to Call `name()`?

```java
Stage value = Stage.RUNNING;
System.out.println(value.name()); // RUNNING
```

`value.name()` returns a `String` for display or text-processing purposes. However, `value` itself is a `Stage` object. When you write `switch (value)`, Java compares the enum value against the enum constants in the `case` labels; it does not require converting to a string.

This is an important distinction regarding **type safety**:

```java
// Correct: switch on an enum, using enum constants.
switch (value) {
    case DONE -> System.out.println("done");
    default   -> System.out.println("other");
}
```

```java
// A different problem: switch on the String returned by name().
switch (value.name()) {
    case "DONE" -> System.out.println("done");
    default     -> System.out.println("other");
}
```

The second snippet is valid because the selector has been converted to `String`; however, it is no longer a **direct switch on an enum**. When you already have an enum value, prefer the first approach to avoid repeating string literals and losing the benefits of enum type checking.

### 2.2. Is a Case Constant a New Variable?

No:

```java
case DONE -> "Completed";
```

`DONE` is the name of a constant already declared in the enum. That branch **does not create a variable named `DONE`**. If you need to inspect the `value` object in detail, the selector variable `value` is already available in the method's scope.

Do not confuse this with the Java 21 syntax:

```java
case Stage s -> "State is " + s.name();
```

This is a **type pattern case**: the variable `s` is declared and bound to the matched `Stage` object. An enum constant case and a type pattern serve two different levels of checking: **matching a specific value** versus **belonging to a specific type**.

## 3. Classic Switch Statement: `case NAME:`, `break`, and Fall-Through

Before switch expressions existed, Java typically used switch statements:

```java
static void printStage(Stage stage) {
    switch (stage) {
        case QUEUED:
            System.out.println("Queued");
            break;
        case RUNNING:
            System.out.println("Running");
            break;
        case DONE:
            System.out.println("Done");
            break;
        case FAILED:
            System.out.println("Failed");
            break;
    }
}
```

Here, the **`:`** introduces the statement group for a case. The **`break`** statement exits the switch statement after executing the corresponding group of statements.

### 3.1. Fall-Through: Without `break`, Execution Can Continue into the Next Branch

```java
static void demonstrateFallThrough(Stage stage) {
    switch (stage) {
        case QUEUED:
            System.out.println("A");
            // No break here.
        case RUNNING:
            System.out.println("B");
            break;
        default:
            System.out.println("C");
    }
}
```

For `Stage.QUEUED`, the code above prints:

```text
A
B
```

Reason: after executing the `QUEUED` group, the program **falls through** into the `RUNNING` statement group because there is no `break`. This is a characteristic of colon-style switch statements, not because `Stage.QUEUED` equals `Stage.RUNNING`.

For `Stage.RUNNING`, only `B` is printed; for `Stage.FAILED`, `C` is printed.

**Avoid unintended fall-through** using `break`, `return`, `throw`, or by using switch rules with `->` as shown in the next section. If fall-through is intentional, document it clearly with a comment.

### 3.2. Grouping Multiple Constants with Multiple `case` Labels

A common classic pattern:

```java
static String phase(Stage stage) {
    switch (stage) {
        case QUEUED:
        case RUNNING:
            return "IN_PROGRESS";
        case DONE:
            return "SUCCESS";
        case FAILED:
            return "ERROR";
        default:
            return "UNKNOWN";
    }
}
```

The labels `QUEUED` and `RUNNING` both lead to the same statement group returning `IN_PROGRESS`. This is **constant grouping**, and it does not declare any pattern variable.

The `default` branch in the example ensures every execution path returns a value. It also serves as a fallback if a new enum value is added before the method is updated; however, using `default` always requires care because it can hide the need to handle a newly added constant.

## 4. Switch Rules with `->`: No Fall-Through

Since Java 14, the arrow syntax is usually more concise:

```java
static String stageText(Stage stage) {
    return switch (stage) {
        case QUEUED  -> "Waiting";
        case RUNNING -> "Working";
        case DONE    -> "Complete";
        case FAILED  -> "Failure";
    };
}
```

Each **rule** executes only the handling logic after its own `->`. There is no fall-through behavior into the next rule as with the `:` syntax.

For a switch statement, you can write:

```java
static void printArrow(Stage stage) {
    switch (stage) {
        case QUEUED  -> System.out.println("Waiting");
        case RUNNING -> System.out.println("Working");
        case DONE    -> System.out.println("Complete");
        case FAILED  -> System.out.println("Failure");
    }
}
```

A `System.out.println` call is a valid **statement expression** after `->` in a switch statement.

### 4.1. When a Branch Needs Multiple Statements

For a switch expression, use a block and `yield`:

```java
static String loggable(Stage stage) {
    return switch (stage) {
        case QUEUED, RUNNING -> {
            String info = "PENDING:" + stage.name();
            yield info;
        }
        case DONE   -> "OK";
        case FAILED -> "ERROR";
    };
}
```

`yield info;` returns the value of the **switch expression**; it does not exit the entire enclosing method like `return` does in a regular method.

For a switch statement, a block can contain statements with side effects:

```java
static void logStage(Stage stage) {
    switch (stage) {
        case QUEUED, RUNNING -> {
            System.out.println("Current: " + stage);
            System.out.println("Not final yet");
        }
        case DONE   -> System.out.println("Success");
        case FAILED -> System.out.println("Failure");
    }
}
```

### 4.2. Do You Use `break` with the Arrow Syntax?

No `break` is needed to prevent fall-through when using `->`. The arrow syntax already guarantees that a rule does not fall through to another rule. `break` is mainly useful with colon-style statement groups; writing `break` out of habit inside a switch expression can cause a syntax error or a control-flow error.

## 5. A Single Case Accepting Multiple Enum Constants

When multiple constants share the same outcome, you can write a comma-separated list:

```java
static boolean terminal(Stage stage) {
    return switch (stage) {
        case DONE, FAILED    -> true;
        case QUEUED, RUNNING -> false;
    };
}
```

Both `Stage.DONE` and `Stage.FAILED` return `true`, while the other two values return `false`.

**Each constant in the list is matched independently.** `case DONE, FAILED` does not declare a new variable, does not require writing an expression like `DONE || FAILED`, and does not require a `break` statement.

This is a good choice when multiple states share the same business behavior. When each constant has distinct behavior, keep separate cases so the code remains easy to read and extend.

### 5.1. Grouping Does Not Mean Ignoring Other Enum Constants

```java
// DOES NOT COMPILE: missing two constants for the switch expression.
// static boolean terminal(Stage stage) {
//     return switch (stage) {
//         case DONE, FAILED -> true;
//     };
// }
```

The `DONE, FAILED` group only covers **two** of the four constants in `Stage`. To make the switch expression exhaustive, you must handle `QUEUED` and `RUNNING` or provide an appropriate catch-all branch.

## 6. Exhaustiveness: Listing All Enum Constants

An **exhaustive switch** is a switch for which the compiler can prove that the branches cover all required cases of the selector type.

For enums, this is usually straightforward to check because the compiler knows the complete list of enum constants at compile time:

```java
enum Color { RED, YELLOW, GREEN }

static String signal(Color color) {
    return switch (color) {
        case RED    -> "STOP";
        case YELLOW -> "WAIT";
        case GREEN  -> "GO";
    };
}
```

This code is valid even without `default`, because all three enum constants are handled.

### 6.1. Switch Expressions Always Require Exhaustiveness

```java
// DOES NOT COMPILE: switch expression is missing GREEN.
// static String signal(Color color) {
//     return switch (color) {
//         case RED    -> "STOP";
//         case YELLOW -> "WAIT";
//     };
// }
```

This is a **compile-time error**, not a runtime default that returns `null`. Java requires a switch expression to be able to produce a value for every enum value of the selector type.

### 6.2. Classic Switch Statements Are Not Required to Be Exhaustive

```java
static void incomplete(Color color) {
    switch (color) {
        case RED -> System.out.println("STOP");
    }
}
```

This snippet **compiles**: a classic switch statement (with an enum selector, and no pattern cases or `case null`) is not required to be exhaustive. For `YELLOW` or `GREEN`, no case applies, so the statement simply finishes without printing anything.

Note the distinction: starting in Java 21, an **enhanced switch statement** (for example, with an interface selector or containing a pattern/`null` label) **must be exhaustive**; the rules for classic switch statements cannot be applied to all new switch forms.

### 6.3. Adding a New Constant and the Role of `default`

Suppose one day `Stage` is extended with `CANCELLED`:

```java
// Hypothetical version of the enum after the change:
// enum Stage { QUEUED, RUNNING, DONE, FAILED, CANCELLED }
```

With a switch expression that listed all four old constants and **had no `default`**, recompiling against the updated enum will cause the compiler to report that `CANCELLED` is missing. This acts as a reminder to update the business logic.

If `default -> "OTHER"` had been written earlier, the compiler would still consider the switch exhaustive and would not force adding a case for `CANCELLED`. Both approaches have valid use cases:

- **Closed domain requiring explicit handling for every state:** prefer listing all constants and omitting `default` if the compiler can prove exhaustiveness.
- **Broad input or a sensible fallback behavior:** use `default` to catch other values.

**Recompilation** is a crucial condition. For previously compiled code that loads an updated enum at runtime from another library, compile-time checks cannot automatically re-verify changes across separate binaries. In Java 21, an exhaustive switch that loses exhaustiveness at runtime can throw `MatchException`; managing binary compatibility and integration testing remains necessary.

## 7. `null` in a Switch with Enum Constants

An enum is a **reference type**, so a `Stage` variable can still be `null`:

```java
Stage stage = null;
```

Enum constants such as `QUEUED` and `DONE` are all non-null objects. Therefore, if you use a switch without null handling:

```java
static String label(Stage stage) {
    return switch (stage) {
        case QUEUED  -> "Q";
        case RUNNING -> "R";
        case DONE    -> "D";
        case FAILED  -> "F";
    };
}
```

`label(null)` **throws `NullPointerException`**. Even though every enum constant is listed, none of the constants is `null`. Enum exhaustiveness does not mean the expression handles `null` automatically.

### 7.1. Java 21: `case null` as a Dedicated Label

```java
static String safeLabel(Stage stage) {
    return switch (stage) {
        case null    -> "MISSING";
        case QUEUED  -> "Q";
        case RUNNING -> "R";
        case DONE    -> "D";
        case FAILED  -> "F";
    };
}
```

For `null`, it returns `"MISSING"`; for any non-null `Stage` value, it returns the corresponding string. `case null` was standardized alongside Pattern Matching for `switch` in Java 21.

For Java 17 code, you can handle `null` **before entering the switch**:

```java
static String safeLabelJava17(Stage stage) {
    if (stage == null) {
        return "MISSING";
    }

    return switch (stage) {
        case QUEUED  -> "Q";
        case RUNNING -> "R";
        case DONE    -> "D";
        case FAILED  -> "F";
    };
}
```

### 7.2. A Standalone `default` Does Not Catch `null`

```java
static String withDefault(Stage stage) {
    return switch (stage) {
        case DONE -> "SUCCESS";
        default   -> "NOT_DONE";
    };
}
```

For `Stage.QUEUED`, it returns `"NOT_DONE"`; for `Stage.DONE`, it returns `"SUCCESS"`. However, **`withDefault(null)` still throws `NullPointerException`**, even with `default`.

In Java 21, when you want to handle `null` and unmatched values the same way, use `case null, default`:

```java
static String doneOrOther(Stage stage) {
    return switch (stage) {
        case DONE          -> "SUCCESS";
        case null, default -> "OTHER_OR_NULL";
    };
}
```

The combined label `case null, default` must be the last label in the switch block. It does not declare a pattern variable.

## 8. Java 21: Qualified Enum Constants `case Stage.DONE`

When the selector has static type `Stage`, we usually write `case DONE`. Starting in Java 21, you can write constants with **qualified enum names**:

```java
static String qualified(Stage value) {
    return switch (value) {
        case Stage.QUEUED  -> "Q";
        case Stage.RUNNING -> "R";
        case Stage.DONE    -> "D";
        case Stage.FAILED  -> "F";
    };
}
```

This still matches each constant exact-by-value. The bigger advantage of qualified enum constants is that **the selector is no longer required to have that exact enum as its static type**. It can be an interface implemented by the enum, or `Object`, as long as **the type of the enum constant is assignable to the selector type**.

### 8.1. Interface Selector Implemented by Two Enums

```java
sealed interface WorkflowEvent permits Stage, Priority {}

enum Stage implements WorkflowEvent {
    QUEUED, RUNNING, DONE, FAILED
}

enum Priority implements WorkflowEvent {
    LOW, HIGH
}
```

These are top-level declarations illustrating Java 21 compatibility: `WorkflowEvent` only permits the two enums above to implement it directly. A `WorkflowEvent` variable can hold a constant of `Stage` or `Priority`.

```java
static String eventName(WorkflowEvent event) {
    return switch (event) {
        case Stage.QUEUED   -> "stage-queued";
        case Stage.RUNNING  -> "stage-running";
        case Stage.DONE     -> "stage-done";
        case Stage.FAILED   -> "stage-failed";
        case Priority.LOW   -> "priority-low";
        case Priority.HIGH  -> "priority-high";
        case null           -> "missing";
    };
}
```

This is Java 21: **qualified enum case constants** from enums implementing an interface can appear together in a single switch. These branches list all values of both enums, so they satisfy exhaustiveness over this sealed hierarchy. With an **open** (non-sealed) interface, listing only a few enum constants is generally not enough to make a switch expression exhaustive; an appropriate catch-all branch is required.

### 8.2. When the Selector Is Not an Enum, a Qualified Constant Name Is Required

```java
// DOES NOT COMPILE in a switch on WorkflowEvent:
// return switch (event) {
//     case DONE -> "done"; // Cannot determine which enum defines the constant.
//     default   -> "other";
// };
```

With a `WorkflowEvent` or `Object` selector, you must write `case Stage.DONE` to specify which enum defines `DONE`. When multiple enums define a constant with the same name, the qualified name also prevents ambiguity.

**Type compatibility rule:** the constant `Stage.DONE` has type `Stage`, which is assignable to `WorkflowEvent` and `Object`, so it is valid. However, if the selector has static type `Priority`, `case Stage.DONE` is incompatible and causes a compile-time error.

### 8.3. With `Object`, a Branch for Non-Enum Types Is Required

```java
static String any(Object value) {
    return switch (value) {
        case null          -> "null";
        case Stage.DONE    -> "done";
        case Priority.HIGH -> "high-priority";
        default            -> "other";
    };
}
```

A `switch` on `Object` may encounter an `Integer`, `String`, record, list, and so on. Listing a couple of enum constants is still **not enough** to cover all objects. `default` catches unmatched non-null values; `case null` catches `null`.

### 8.4. Java 17 vs. Java 21

| Capability | Java 17 (no preview) | Java 21 |
| --- | --- | --- |
| `switch (Stage s)` and `case DONE` | Yes | Yes |
| Switch expression with enum constants | Yes | Yes |
| `case DONE, FAILED -> ...` | Yes | Yes |
| `case null` in switch | No | Yes |
| `case Stage.DONE` on a `WorkflowEvent` selector | No | Yes |
| `case Stage state` type pattern in switch | Not finalized / not available without preview | Yes |
| `case Stage s when ...` | No | Yes |

The runnable examples later in this lesson specifically target **Java 21**. Do not use `--release 17` for a file containing `case null`, pattern switches, or qualified enum case constants on an interface.

## 9. Enum Constant Case vs. Type Pattern

This is a very common point of confusion within the same pattern switch:

```java
static String classifyEvent(WorkflowEvent event) {
    return switch (event) {
        case Stage.FAILED  -> "ALERT";
        case Stage stage   -> "STAGE:" + stage.name();
        case Priority.HIGH -> "URGENT";
        case Priority p    -> "PRIORITY:" + p.name();
        case null          -> "MISSING";
    };
}
```

**Two kinds of branches appear together:**

- `case Stage.FAILED`: **constant case** that matches **only the exact constant** `FAILED` of enum `Stage`; introduces no variable.
- `case Stage stage`: **type pattern** that matches **any non-null `Stage` value** not already handled by an earlier branch; declares variable `stage` of type `Stage`.
- `case Priority.HIGH`: specifically handles the high-priority constant.
- `case Priority p`: handles the remaining `Priority` values; declares variable `p`.
- `case null`: handles `null`, introduces no variable.

**Why must constants be placed before the type pattern?** Because `case Stage stage` matches every `Stage` constant. If it is placed before `case Stage.FAILED`, the `Stage.FAILED` constant is shadowed (**dominated case**) and the compiler reports an error.

```java
// DOES NOT COMPILE: enum constant case is dominated by the type pattern.
// return switch (event) {
//     case Stage stage  -> "ALL_STAGES";
//     case Stage.FAILED -> "ALERT";
//     case Priority p   -> "PRIORITY";
// };
```

A constant case **selects a specific value**; a type pattern **selects an entire type**. That is why they have an ordering requirement when appearing in the same switch.

### 9.1. The `when` Guard Only Applies to Pattern Cases

The following syntax is **invalid**:

```java
// DOES NOT COMPILE:
// case Stage.DONE when authorized -> "DONE";
```

`when` follows a **pattern case**, and cannot be attached directly to a **constant case**. If you need an extra condition, there are two options:

**Option A — check after matching the constant:**

```java
case Stage.DONE -> {
    if (authorized) {
        yield "DONE";
    }
    yield "DENIED";
}
```

This is a **switch expression rule** fragment inside a method that has a boolean variable `authorized`; use `yield` when returning a value from a block.

**Option B — use a guarded type pattern:**

```java
case Stage s when s == Stage.DONE && authorized -> "DONE";
case Stage s -> "OTHER_STAGE";
```

The two lines above are illustrative rules; they must be placed inside a compatible switch with appropriate remaining branches. The guard is evaluated only after `Stage s` has matched.

### 9.2. When Should You Not Use a Type Pattern?

If you only want to distinguish `Stage.DONE` from `Stage.FAILED`, writing `case DONE` (when the selector is `Stage`) or `case Stage.DONE` (when the selector is an interface/supertype) is shorter and clearer than `case Stage s when s == Stage.DONE`. A pattern is useful when you need a `Stage`-typed variable for a **group of values**.

## 10. Common Compile-Time Issues

### 10.1. Duplicate Constant in Two Cases

```java
// DOES NOT COMPILE:
// return switch (stage) {
//     case DONE -> "DONE_A";
//     case DONE -> "DONE_B"; // Duplicate case constant.
//     default   -> "OTHER";
// };
```

An enum constant cannot appear twice as duplicate case constants in the same switch block. Adding `default` does not fix this error.

### 10.2. Case Constant Not Belonging to the Selector Enum

```java
// Assuming Stage stage has been declared.
// DOES NOT COMPILE:
// return switch (stage) {
//     case Priority.HIGH -> "HIGH";
//     default            -> "OTHER";
// };
```

`Priority.HIGH` is not assignable to type `Stage`; the case label type is incompatible with the selector. Use a `Stage` constant, or change the selector to a common supertype if you genuinely need to handle multiple enums.

### 10.3. Using a String Instead of an Enum Constant

```java
// DOES NOT COMPILE if stage has type Stage:
// return switch (stage) {
//     case "DONE" -> "DONE";
//     default     -> "OTHER";
// };
```

`"DONE"` is a `String`, not `Stage.DONE`. You can switch on `stage.name()` if you need string-based branching, but when the input is already an enum, keep the switch expression typed on the enum.

### 10.4. Using an Ordinal Value as an Enum Constant

```java
// NOT a valid case for an enum switch:
// switch (stage) {
//     case 2 -> System.out.println("DONE");
// }
```

`ordinal()` is the positional index in the list of enum constants, not the constant's identity. Do not use position `2` instead of `DONE`; changing the declaration order of enum constants changes their ordinals. In an enum switch, use the actual constant name.

### 10.5. Using an Alias Variable in a Case Label

```java
static final Stage FINAL_ALIAS = Stage.DONE;

// DOES NOT COMPILE in an enum switch if using an alias as a case constant:
// switch (stage) {
//     case FINAL_ALIAS -> System.out.println("Done");
//     default -> {}
// }
```

A `static final Stage` alias is not a **directly declared enum constant name**. Java allows enum constants in case labels, but does not treat arbitrary enum-typed fields as valid *constant expressions*. Use `case DONE` or `case Stage.DONE` instead of an alias.

### 10.6. Forgetting `break` in Colon Syntax

```java
switch (stage) {
    case QUEUED:
        System.out.println("Queued");
        // Without break, execution still falls through to RUNNING.
    case RUNNING:
        System.out.println("Running");
        break;
    default:
        System.out.println("Other");
}
```

This is **not a compile-time error**, but it can cause a logic bug due to fall-through. Unless you intentionally want to group branches, add `break` or use `->`.

### 10.7. Switch Expression Missing an Enum Constant

```java
// DOES NOT COMPILE: missing FAILED.
// return switch (stage) {
//     case QUEUED, RUNNING -> "IN_PROGRESS";
//     case DONE            -> "DONE";
// };
```

This is a **non-exhaustive switch expression** error, not a dominated case. Add `case FAILED` or an appropriate catch-all branch.

### 10.8. Placing a Broad Type Pattern Before a Constant

```java
// DOES NOT COMPILE:
// return switch (event) {
//     case Stage s       -> "ANY_STAGE";
//     case Stage.RUNNING -> "RUNNING";
//     case Priority p    -> "PRIORITY";
// };
```

`Stage.RUNNING` comes after the `Stage s` pattern that covers the entire `Stage` enum, so it is dominated. Swap the order of the first two branches.

### 10.9. Attaching `when` Directly to an Enum Constant

```java
// INVALID:
// case DONE when enabled -> "DONE";
```

To add a boolean check inside a branch, use `if` in the rule body; if you want a guard on the case label, declare a type pattern with a variable before `when`.

### 10.10. Assuming `default` Catches `null`

```java
static String statusOrFallback(Stage stage) {
    return switch (stage) {
        case DONE -> "DONE";
        default   -> "OTHER";
    };
}
```

When `stage == null`, this method **throws `NullPointerException`**. If you need `"OTHER"` for `null` as well, use Java 21's `case null, default -> "OTHER";` or check for `null` before the switch.

## 11. Complete Java 21 Program: Enum Constants, Grouping, and Pattern Switch

Create a file named **`EnumSwitchConstantDemo.java`** with the contents below. All types are declared inside the public class, so only **one Java file** is needed:

```java
public class EnumSwitchConstantDemo {

    sealed interface WorkflowEvent permits Stage, Priority {}

    enum Stage implements WorkflowEvent {
        QUEUED, RUNNING, DONE, FAILED
    }

    enum Priority implements WorkflowEvent {
        LOW, HIGH
    }

    // Direct switch expression on an enum:
    // cases are constant names, with no pattern variables.
    static String label(Stage stage) {
        return switch (stage) {
            case QUEUED  -> "Q";
            case RUNNING -> "R";
            case DONE    -> "D";
            case FAILED  -> "F";
        };
    }

    // Classic switch statement using ':', break, and case grouping.
    static String legacy(Stage stage) {
        switch (stage) {
            case QUEUED:
            case RUNNING:
                return "IN_PROGRESS";
            case DONE:
                return "COMPLETE";
            default:
                return "FAILED";
        }
    }

    // Multiple constants in a single branch.
    static boolean isTerminal(Stage stage) {
        return switch (stage) {
            case DONE, FAILED    -> true;
            case QUEUED, RUNNING -> false;
        };
    }

    // Java 21: case null in an enum switch.
    static String nullableStage(Stage stage) {
        return switch (stage) {
            case null            -> "MISSING";
            case QUEUED, RUNNING -> "PENDING";
            case DONE            -> "SUCCESS";
            case FAILED          -> "FAILURE";
        };
    }

    // Java 21: selector is a sealed interface; constants require
    // type qualification such as Stage.FAILED, Priority.HIGH.
    // Specific constants come before broad type patterns.
    static String fromEvent(WorkflowEvent value) {
        return switch (value) {
            case Stage.FAILED  -> "ALERT";
            case Stage stage   -> "STAGE:" + stage.name();
            case Priority.HIGH -> "URGENT";
            case Priority p    -> "PRIORITY:" + p.name();
            case null          -> "MISSING";
        };
    }

    // Java 21: selector is Object, using qualified constants.
    // default handles other types, case null handles null.
    static String fromAny(Object value) {
        return switch (value) {
            case null          -> "NULL";
            case Stage.DONE    -> "DONE";
            case Stage stage   -> "STAGE:" + stage.name();
            case Priority.HIGH -> "URGENT";
            case Priority p    -> "PRIORITY:" + p.name();
            default            -> "OTHER";
        };
    }

    // Java 21: final label combining null with default.
    static String runningOrElse(Object value) {
        return switch (value) {
            case Stage.RUNNING -> "ACTIVE";
            case null, default -> "NOT_RUNNING";
        };
    }

    public static void main(String[] args) {
        System.out.println(label(Stage.QUEUED));
        System.out.println(label(Stage.RUNNING));
        System.out.println(label(Stage.DONE));
        System.out.println(label(Stage.FAILED));

        System.out.println(legacy(Stage.RUNNING));
        System.out.println(legacy(Stage.FAILED));

        System.out.println(isTerminal(Stage.DONE));
        System.out.println(isTerminal(Stage.QUEUED));

        System.out.println(nullableStage(null));
        System.out.println(nullableStage(Stage.RUNNING));

        System.out.println(fromEvent(Stage.FAILED));
        System.out.println(fromEvent(Stage.QUEUED));
        System.out.println(fromEvent(Priority.HIGH));
        System.out.println(fromEvent(Priority.LOW));
        System.out.println(fromEvent(null));

        System.out.println(fromAny(Stage.DONE));
        System.out.println(fromAny(Stage.RUNNING));
        System.out.println(fromAny(Priority.HIGH));
        System.out.println(fromAny(5));
        System.out.println(fromAny(null));

        System.out.println(runningOrElse(Stage.RUNNING));
        System.out.println(runningOrElse(Stage.DONE));
        System.out.println(runningOrElse(null));
    }
}
```

Compile and run with **JDK 21 or later**:

```bash
javac --release 21 EnumSwitchConstantDemo.java
java EnumSwitchConstantDemo
```

The `--enable-preview` flag is not needed because all syntax used here has been finalized since Java 21.

**Exact stdout output:**

```text
Q
R
D
F
IN_PROGRESS
FAILED
true
false
MISSING
PENDING
ALERT
STAGE:QUEUED
URGENT
PRIORITY:LOW
MISSING
DONE
STAGE:RUNNING
URGENT
OTHER
NULL
ACTIVE
NOT_RUNNING
NOT_RUNNING
```

### 11.1. Explaining Each Output Group

**First four lines — switch expression on an enum:**

- `Stage.QUEUED` selects `case QUEUED`, printing `Q`.
- `Stage.RUNNING` selects `case RUNNING`, printing `R`.
- `Stage.DONE` selects `case DONE`, printing `D`.
- `Stage.FAILED` selects `case FAILED`, printing `F`.

**Next two lines — colon-style `:` statement:** `legacy(Stage.RUNNING)` matches the grouped `QUEUED`/`RUNNING` labels and executes `return "IN_PROGRESS"`. `legacy(Stage.FAILED)` does not match `QUEUED`, `RUNNING`, or `DONE`, so it selects `default` and returns `FAILED`.

**Two boolean lines:** `Stage.DONE` belongs to the terminal constant group, so `isTerminal` returns `true`; `Stage.QUEUED` belongs to the non-terminal group, so it returns `false`.

**Two null/grouped-handling lines:** `nullableStage(null)` matches `case null` and prints `MISSING`; `nullableStage(Stage.RUNNING)` matches the grouped label `QUEUED, RUNNING` and prints `PENDING`.

**Five interface lines:** `fromEvent(Stage.FAILED)` matches the specific enum constant before the type pattern, printing `ALERT`; `Stage.QUEUED` enters `case Stage stage` and prints `STAGE:QUEUED`. Similarly, `Priority.HIGH` is handled by the constant branch, while `Priority.LOW` is handled by the `Priority p` type pattern. `null` is caught by its dedicated label.

**Five Object lines:** `Stage.DONE` prints `DONE`, `Stage.RUNNING` prints `STAGE:RUNNING`, and `Priority.HIGH` prints `URGENT`. The value `5` is autoboxed to `Integer` when passed as `Object`, matches neither enum, and enters `default`. `null` enters `case null`.

**Last three lines — combined label:** `Stage.RUNNING` returns `ACTIVE`; both `Stage.DONE` and `null` return `NOT_RUNNING` via `case null, default`.

### 11.2. Why Doesn't `fromEvent` Need `default`?

`WorkflowEvent` is a **sealed interface** that only permits `Stage` and `Priority` to implement it directly. The `case Stage stage` branch matches all non-null `Stage` constants not already caught by `Stage.FAILED`; the `case Priority p` branch matches all remaining non-null `Priority` constants. Therefore, the set of cases is **exhaustive** for `WorkflowEvent` without needing `default`. `case null` simply provides a result for the `null` value.

### 11.3. Why Must `fromAny` Have `default`?

The selector type of `fromAny` is `Object`; it can receive `Integer`, `String`, `Boolean`, and so on. `case Stage stage` and `case Priority p` cannot cover these object types. `default` provides a handling path for them.

## 12. Decision Flow for Choosing an Enum Switch in Real Code

### 12.1. Is the Input Already a Concrete Enum?

If you have `Stage stage` and behavior depends on the constant value, use a **direct switch on the enum**:

```java
static int progress(Stage stage) {
    return switch (stage) {
        case QUEUED  -> 0;
        case RUNNING -> 50;
        case DONE    -> 100;
        case FAILED  -> -1;
    };
}
```

This is simple, type-safe, and lets the compiler verify that all constants are covered. Pattern Matching for `switch` is not needed if you are only distinguishing states of a single enum.

### 12.2. Do Some Constants Share the Same Handling?

Group them:

```java
case DONE, FAILED -> true;
```

When using a colon-style `:` statement, you can stack multiple labels to run shared statements. With `->`, use a comma-separated list of constants. Remember to include all enum constants if using a switch expression without `default`.

### 12.3. Can the Input Belong to Multiple Different Enums?

Design a common interface, then use **Java 21 qualified enum constants**:

```java
case Stage.FAILED -> "stage failed";
case Priority.HIGH -> "priority high";
```

Condition: those constants must have types assignable to the selector type. If you want to handle all remaining values of an enum, place `case Stage s` after the specific constants.

### 12.4. Can the Input Be `null`?

- **Reject `null`:** validate early with `Objects.requireNonNull(stage)` or document a clear API contract, depending on your application.
- **Accept `null` with a dedicated value:** Java 21 provides `case null`.
- **Treat `null` the same as the fallback:** Java 21 provides `case null, default`.
- **Java 17:** use `if (stage == null)` before the switch.

Never rely on a standalone `default` to catch `null`.

### 12.5. When Should You Omit `default`?

When the enum represents a **closed domain** and you want the compiler to remind you to update every switch site after adding a new constant, a switch expression listing all constants **without `default`** is usually beneficial. For open inputs or when a genuine fallback policy exists, `default` may be the right choice.

## 13. Comparison Table and Easily Confused Boundaries

| Concept | `case DONE` (Stage selector) | `case Stage.DONE` (Java 21) | `case Stage s` (Java 21) |
| --- | --- | --- | --- |
| Is it an enum constant? | Yes | Yes | No |
| Is it a type pattern? | No | No | Yes |
| What values does it match? | Exact `Stage.DONE` | Exact `Stage.DONE` | Any non-null `Stage` value |
| Has a pattern variable? | No | No | Yes: `s` |
| Usable with an interface selector? | Not in this short form | Yes, if the constant's type is assignable to the interface | Yes, if the pattern applies to the selector |
| Supports `when` directly? | No | No | Yes, with a valid guard |
| Ordering when mixed | Specific constant before broad pattern | Specific constant before broad pattern | After specific constants of the same enum |

Some practical takeaways:

- `enum Stage` defines **values**, not just strings; `case DONE` is the proper way to match an enum value.
- The arrow syntax `->` prevents fall-through; the `:` syntax requires explicit control flow.
- Comma-separated constant grouping is a clean way for multiple values to share one behavior.
- A switch expression on an enum without `default` must list all constants to be exhaustive.
- `null` and enum constants are distinct cases; never assume an enum constant can be `null`.
- Java 21's qualified enum constants extend switch capabilities when the selector is an interface or supertype.

## 14. Practice Exercises with Answers

### Exercise 1 — Predict the Switch Expression Result

Given:

```java
enum Status { NEW, SENT, RECEIVED, FAILED }

static String category(Status status) {
    return switch (status) {
        case NEW, SENT -> "PENDING";
        case RECEIVED  -> "SUCCESS";
        case FAILED    -> "ERROR";
    };
}
```

**Question:** What are the results of `category(Status.SENT)`, `category(Status.RECEIVED)`, and `category(Status.FAILED)`?

**Answer:** `"PENDING"`, `"SUCCESS"`, and `"ERROR"`, respectively. The first branch groups two enum constants; each value selects only one rule.

### Exercise 2 — Find the Compile-Time Error

```java
// DOES NOT COMPILE:
// static String category(Status status) {
//     return switch (status) {
//         case NEW      -> "NEW";
//         case SENT     -> "SENT";
//         case RECEIVED -> "RECEIVED";
//     };
// }
```

**Answer:** The switch expression is not exhaustive because it is missing `Status.FAILED`. Add `case FAILED -> "FAILED";` or a valid `default` branch.

### Exercise 3 — How Does Fall-Through Occur?

```java
static void show(Status status) {
    switch (status) {
        case NEW:
            System.out.println("A");
        case SENT:
            System.out.println("B");
            break;
        default:
            System.out.println("C");
    }
}
```

**Answer:** `show(Status.NEW)` prints `A` then `B`, because there is no `break` in the `NEW` group. `show(Status.SENT)` prints only `B`. `show(Status.FAILED)` prints `C`. If you do not want `B` printed when the input is `NEW`, add `break` or switch to `->`.

### Exercise 4 — Fix the Dominated Branch

Suppose the selector is `Object event`, and `Stage` has been declared:

```java
// DOES NOT COMPILE:
// return switch (event) {
//     case Stage s       -> "ANY_STAGE";
//     case Stage.DONE    -> "DONE";
//     default            -> "OTHER";
// };
```

**Answer:** Move `case Stage.DONE` before `case Stage s`. `case Stage s` is a type pattern covering all constants of `Stage`; if it comes first, the `DONE` constant branch can never be selected.

### Exercise 5 — Write a Method Returning a Status Code

Requirement: accept `Status status` with constants `NEW`, `SENT`, `RECEIVED`, `FAILED`. Return 0 for `NEW`, 1 for `SENT`, 2 for `RECEIVED`, and -1 for `FAILED`. Do not use `default` so the compiler catches missing constants.

**One solution:**

```java
static int code(Status status) {
    return switch (status) {
        case NEW      -> 0;
        case SENT     -> 1;
        case RECEIVED -> 2;
        case FAILED   -> -1;
    };
}
```

This is an exhaustive switch expression because all enum constants are covered.

### Exercise 6 — Handle `null` in Java 21

Rewrite `code(Status status)` so that `null` returns -99 while the enum constants keep their original results.

**Answer:**

```java
static int codeNullable(Status status) {
    return switch (status) {
        case null     -> -99;
        case NEW      -> 0;
        case SENT     -> 1;
        case RECEIVED -> 2;
        case FAILED   -> -1;
    };
}
```

`case null` does not invalidate the enum branches; it simply adds handling for a null reference value.

### Exercise 7 — Why Is an Alias Invalid?

```java
static final Status COMPLETE_ALIAS = Status.RECEIVED;

// DOES NOT COMPILE when used as an enum case:
// return switch (status) {
//     case COMPLETE_ALIAS -> "RECEIVED";
//     default -> "OTHER";
// };
```

**Answer:** `COMPLETE_ALIAS` is a `static final` variable referencing an enum constant, but it is not the **name of an enum constant** itself as required by case constant syntax. Use `case RECEIVED` (for a `Status` selector) or `case Status.RECEIVED` (Java 21, when compatible with the selector type).

### Exercise 8 — Choose a Solution for a Multi-Enum System

A system has a `sealed interface Event` implemented by `NetworkEvent` and `FileEvent` (both enums). Both enums have a constant named `OPEN`. How do you distinguish them in a Java 21 switch?

**Answer:** Give the selector type `Event` and use **qualified enum constants**:

```java
// Both enums must be declared as permitted subtypes of Event.
// Illustrative switch expression fragment:
return switch (event) {
    case NetworkEvent.OPEN -> "NETWORK_OPEN";
    case FileEvent.OPEN    -> "FILE_OPEN";
    default                -> "OTHER";
};
```

`NetworkEvent.OPEN` and `FileEvent.OPEN` are two constants of **different types**, so there is no ambiguity despite having the same name `OPEN`.

## 15. Checklist for Using Switch with Enum Constants

When reviewing Java code, check:

1. **What is the selector's type?** For a concrete enum, `case DONE` is usually sufficient. For an interface or `Object` in Java 21, use the qualified name `case Stage.DONE`.
2. **Is the case actually an enum constant?** Do not use strings like `"DONE"`, `ordinal()` numbers, or aliases as enum labels when the selector is an enum.
3. **Statement or expression?** A switch expression always requires exhaustiveness; a classic switch statement on an enum may omit cases, though this risks missing behavior.
4. **Using `:` or `->`?** With `:`, check for unintended fall-through. With `->`, each rule is independent.
5. **Are constants grouped for shared handling?** Use `case DONE, FAILED` or stacked `:` labels when appropriate.
6. **Is exhaustiveness satisfied?** If omitting `default` in a switch expression, all enum constants must be covered; when the enum grows, recompile to catch missing-case errors.
7. **Is `null` handling explicitly decided?** In Java 21, use `case null` or `case null, default`; in Java 17, check before the switch. Do not rely on a standalone `default`.
8. **Is it mixed with type patterns?** Place specific enum constants **before** a type pattern covering the enum; otherwise, you get a dominated case error.
9. **Is `when` used?** A guard only attaches to a pattern case, never directly after an enum constant case.
10. **Do two enums share the same constant name?** Use qualified names when the selector is not a single concrete enum.
11. **Does business logic depend on enum order or string names?** Avoid tying critical logic to `ordinal()`; if persisting externally, design stable identifiers and an upgrade strategy.
12. **Which Java version does the project use?** Switch expressions with enums require Java 14+; `case null` and qualified enum labels on supertype selectors as shown here require Java 21.

## 16. Summary

**Switch with enum constants** uses named constants to select behavior based on an enum value, making state-dispatch code more strongly typed than handling arbitrary strings.

- **`case DONE`** matches the enum constant `DONE` when the selector has a concrete enum type.
- **`case Stage.DONE`** (Java 21) matches a qualified constant and supports compatible interface/supertype selectors.
- **`case Stage s`** is not a constant case; it is a **type pattern** that matches the entire `Stage` type and declares variable `s`.
- **The `->` arrow** prevents fall-through; **the `:` colon** requires explicit control flow via `break`/`return`/`throw`.
- **Switch expressions** must be exhaustive; enums allow the compiler to verify all constants without `default`.
- **`null`** is not an enum constant; to handle `null`, use a dedicated label in Java 21 or an early check.
- When mixing enum constants with type patterns, **specific constant cases must come before broader patterns** to avoid dominance.

Mastering these rules helps you write enum switches that are readable, testable, and easy to extend as your application's state model evolves.

## Official References

- [Java SE 21 Language Specification §14.11 — The switch Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
- [Java SE 21 Language Specification §14.11.1 — Switch Blocks, Labels, Constants, Dominance](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1)
- [Java SE 21 Language Specification §14.11.1.1 — Exhaustive Switch Blocks](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1.1)
- [Java SE 21 Language Specification §15.28 — Switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28)
- [OpenJDK JEP 361 — Switch Expressions](https://openjdk.org/jeps/361)
- [OpenJDK JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
