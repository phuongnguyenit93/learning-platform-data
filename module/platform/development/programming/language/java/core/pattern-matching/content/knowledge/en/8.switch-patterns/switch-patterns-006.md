# Enum constants in Java pattern switch

## 1. What is an enum constant and why does it appear in pattern switch?

`enum` defines a finite set of named values known at compile time. For example:

```java
enum Status {
    NEW, RUNNING, DONE
}
```

`Status.NEW`, `Status.RUNNING`, and `Status.DONE` are **enum constants**. Each constant is a unique object of type `Status`. When using `switch`, we can branch on enum constants:

```java
static String describe(Status status) {
    return switch (status) {
        case NEW     -> "Mới";
        case RUNNING -> "Đang chạy";
        case DONE    -> "Hoàn thành";
    };
}
```

This is a **traditional enum switch**, without needing pattern matching. If the expression `status` has static type `Status`, the compiler knows which enum `NEW`, `RUNNING`, and `DONE` belong to. The branches are **constant** comparisons, not patterns that declare variables.

**Pattern matching for switch** (standardized in **Java 21**, JEP 441) extends `switch` to test object types with branches such as `case String text`, `case Integer number`. Along with that, Java 21 allows using a **qualified enum constant** such as `case Status.NEW`, even when the static type of the `switch` expression is **not** `Status`, as long as the constant value `Status.NEW` is assignable to the selector type.

This new capability is very useful when an interface has multiple implementing enums, or when `switch` receives a supertype such as `Object`.

**Do not confuse the two kinds of `case`:**

- `case Status.NEW` is a **case constant**: it matches a specific enum value exactly and **does not declare a pattern variable**.
- `case Status status` is a **case type pattern**: it matches non-`null` values of type `Status` and introduces the variable `status`.
- `case Status status when status == Status.NEW` is a **guarded type pattern**: it matches type `Status` and then checks an additional condition. When comparing against a single enum constant, it is usually better to use the more concise `case Status.NEW`.

This lesson uses **Java 21 syntax without enabling preview**. Java 17 already had classic `switch` on enums, but did not yet have **stable pattern switch** or the qualified enum constant syntax standardized with JEP 441. Complete examples use `javac --release 21`.

## 2. From `case NEW` to `case Status.NEW`

Suppose:

```java
enum Status { NEW, RUNNING, DONE }
```

When the selector is a concrete enum, both of the following forms are valid in Java 21:

**Approach 1 — short name (characteristic of switch on enum):**

```java
static String shortName(Status value) {
    return switch (value) {
        case NEW     -> "NEW";
        case RUNNING -> "RUNNING";
        case DONE    -> "DONE";
    };
}
```

**Approach 2 — qualified name:**

```java
static String qualifiedName(Status value) {
    return switch (value) {
        case Status.NEW     -> "NEW";
        case Status.RUNNING -> "RUNNING";
        case Status.DONE    -> "DONE";
    };
}
```

`Status.NEW` is an existing enum constant, **not** a new variable name. The two `switch` expressions above are equivalent in branch selection for non-`null` `Status` values.

In simple examples with a single enum type, short names are usually easier to read. When the selector is an interface/supertype and multiple enums are involved, qualified names become necessary to identify the exact constant being matched.

### Grouping multiple enum constants into one branch

A branch can list multiple **constants**:

```java
static boolean notFinished(Status value) {
    return switch (value) {
        case NEW, RUNNING -> true;
        case DONE         -> false;
    };
}
```

In Java 21, you can write the qualified-name version:

```java
static boolean notFinishedQualified(Status value) {
    return switch (value) {
        case Status.NEW, Status.RUNNING -> true;
        case Status.DONE                -> false;
    };
}
```

`case Status.NEW, Status.RUNNING` is a list of **two case constants**, not two type patterns. It introduces no pattern variables for the branch body.

## 3. Important case: selector is an interface, enums implement the interface

Suppose a system has two groups of events:

```java
sealed interface Event permits State, Level {}

enum State implements Event {
    CREATED, PROCESSED, FAILED
}

enum Level implements Event {
    INFO, WARN
}
```

These are illustrative declarations that can be placed together in a single Java 21 file as non-`public` top-level types. `Event` is a **sealed interface** and only permits `State` and `Level` to implement it directly. Enums implementing an interface are accepted as final subtypes (*final* by the nature of enums).

A method with parameter `Event event` can receive **any** constant of `State` or `Level`. The static type of the selector is `Event`, not the enum `State` or `Level`.

**Java 21 syntax:**

```java
static String nameOf(Event event) {
    return switch (event) {
        case State.CREATED   -> "state-created";
        case State.PROCESSED -> "state-processed";
        case State.FAILED    -> "state-failed";
        case Level.INFO      -> "level-info";
        case Level.WARN      -> "level-warn";
        case null            -> "missing";
    };
}
```

With `event = State.FAILED`, `switch` selects `case State.FAILED`; with `event = Level.INFO`, it selects `case Level.INFO`. There is **no need** to cast `Event` to a specific enum, nor is there any need for a chain of `if (event instanceof ...)`.

**Why must you write `State.CREATED`, and not just `CREATED`?** Because the selector has type `Event` — an interface rather than a single enum type. Java cannot infer which enum type to look up for the unqualified name `CREATED`. In this case, the enum constant case label must be qualified with its type name, and its value must be *assignment-compatible* with the selector type.

In the example above, both `State` and `Level` implement `Event`; therefore, their constants are assignable to `Event`, satisfying the requirement.

### What if two enums have constants with the same name?

```java
sealed interface Action permits NetworkAction, FileAction {}

enum NetworkAction implements Action {
    OPEN, CLOSE
}

enum FileAction implements Action {
    OPEN, CLOSE
}
```

From `Action action`, you can write:

```java
static String label(Action action) {
    return switch (action) {
        case NetworkAction.OPEN  -> "network-open";
        case NetworkAction.CLOSE -> "network-close";
        case FileAction.OPEN     -> "file-open";
        case FileAction.CLOSE    -> "file-close";
    };
}
```

`NetworkAction.OPEN` and `FileAction.OPEN` are **two different constants** even though both are named `OPEN`. Qualifying with the enum class avoids ambiguity, and the case constants can directly express the distinct business logic of each enum.

This is a clear advantage of qualified enum constants over having to write multiple type patterns with `when` just to compare against a single constant.

## 4. Comparing qualified enum constants and guarded type patterns

Before qualified enum constant syntax was standardized, checking a constant inside an interface-typed selector in preview versions was often illustrated using a type pattern combined with a condition:

```java
static String oldStyle(Event event) {
    return switch (event) {
        case State s when s == State.CREATED -> "created";
        case State s when s == State.FAILED  -> "failed";
        case State s                        -> "other-state";
        case Level l                        -> "level-" + l.name();
    };
}
```

This is an **illustrative snippet of type pattern + guard syntax in Java 21**; it is not a standalone program. `case State s` checks whether the object belongs to the `State` enum and binds variable `s`; the `when` clause then compares `s` against a specific constant.

If the goal is only to identify an enum constant, Java 21 provides a shorter way:

```java
static String newStyle(Event event) {
    return switch (event) {
        case State.CREATED -> "created";
        case State.FAILED  -> "failed";
        case State s       -> "other-state";
        case Level l       -> "level-" + l.name();
    };
}
```

Key differences:

| Syntax | Meaning | New variable? | When appropriate |
| --- | --- | --- | --- |
| `case State.CREATED` | Matches the exact constant `State.CREATED` | No | A specific enum value |
| `case State.CREATED, State.FAILED` | Matches either of the two constants | No | Grouping multiple constants with shared handling |
| `case State s` | Matches any constant of enum `State` | Yes: `s` | Handling an entire enum uniformly |
| `case State s when s == State.CREATED` | Matches enum `State` and checks an extra condition | Yes: `s` | When a guard structure is genuinely needed |
| `case Level l when l.name().startsWith("W")` | Checks type, then checks a property | Yes: `l` | Dynamic/more complex conditions than constant equality |

`case State.CREATED` **is not a type pattern** and does not create a variable `CREATED`. Pattern variable rules apply only to branches that declare a pattern variable such as `case State s`.

### The `when` clause does not apply directly to a case constant

The following is **invalid**:

```java
// DOES NOT COMPILE:
// return switch (event) {
//     case State.CREATED when someCondition -> "created";
//     default -> "other";
// };
```

In Java 21, `when` attaches to a **case pattern**, such as `case State s when ...`, not directly to a `case` containing an enum constant. When you want conditional handling after matching `State.CREATED`, you can check with `if` inside the branch body, or use an appropriate guarded type pattern.

## 5. Branch ordering and the dominance rule

With pattern switch, the order of cases affects more than how readers understand the code. **Dominance** is a compile-time rule that prevents a later case from being completely covered by an earlier pattern.

The following example is **valid**:

```java
static String inspect(Event event) {
    return switch (event) {
        case State.FAILED -> "failed-special";
        case State s      -> "state:" + s.name();
        case Level l      -> "level:" + l.name();
    };
}
```

When `event == State.FAILED`, the specific constant is handled in the first branch; the remaining `State` constants go to `case State s`. `Level` constants go to `case Level l`.

**Swapping the order of the first two branches is invalid:**

```java
// DOES NOT COMPILE: case State.FAILED is dominated.
// return switch (event) {
//     case State s      -> "state:" + s.name();
//     case State.FAILED -> "failed-special";
//     case Level l      -> "level:" + l.name();
// };
```

Because `case State s` matches **all constants of `State`**, the subsequent `case State.FAILED` can never be selected. Java 21 reports a *dominated case label* error.

**Ordering principle:** place specific enum constants **before** a type pattern that covers that enum; place general branches after priority exceptions.

### Cannot mix constants and type patterns in the same case list

```java
// DOES NOT COMPILE:
// case State.FAILED, State s -> "value";
```

A list-form case label can consist of **case constants**, whereas a branch with a **case pattern** is a different form. When you need to distinguish `State.FAILED` from the remaining `State` constants, write two separate cases as in the valid example above.

### The same constant appearing twice

```java
// DOES NOT COMPILE: duplicate case constant.
// switch (event) {
//     case State.FAILED -> System.out.println("A");
//     case State.FAILED -> System.out.println("B");
//     default -> System.out.println("Other");
// }
```

Two branches with the same enum constant cause a compile-time error due to a duplicate case label. Instead of repeating the constant in two places, combine the handling or place a sub-condition inside the appropriate branch body.

## 6. Exhaustiveness with enum constants

A **switch expression** must be able to return a result for every valid value it is required to cover. For enums, Java can verify that all constants are covered at compile time:

```java
enum Traffic { RED, YELLOW, GREEN }

static String action(Traffic traffic) {
    return switch (traffic) {
        case RED    -> "Stop";
        case YELLOW -> "Wait";
        case GREEN  -> "Go";
    };
}
```

No `default` is needed because all three `Traffic` constants are listed. If `case GREEN` is omitted without another catch-all branch, the `switch` expression is no longer exhaustive and will be rejected at compile time.

### Selector is a sealed interface with multiple enums

In the `Event permits State, Level` example, **the set of case constants from both enums** can also form an exhaustive switch expression:

```java
static int code(Event event) {
    return switch (event) {
        case State.CREATED   -> 1;
        case State.PROCESSED -> 2;
        case State.FAILED    -> 3;
        case Level.INFO      -> 4;
        case Level.WARN      -> 5;
    };
}
```

This is valid in Java 21: the branches cover every constant of `State` and `Level`, which are the two types permitted by `Event`. The compiler can determine exhaustiveness via **enum coverage** combined with **sealed hierarchy coverage**.

Another option is to use type patterns to cover the enum types:

```java
static String generic(Event event) {
    return switch (event) {
        case State s -> "State: " + s;
        case Level l -> "Level: " + l;
    };
}
```

This approach is also exhaustive because `Event` permits only those two enums. However, it **does not distinguish individual constants**. Use individual enum constants when different values have different behaviors; use a type pattern when values of the same enum can be handled uniformly.

### Exhaustive does not mean `null` is handled automatically

This is a very important point:

```java
static String statusName(State state) {
    return switch (state) {
        case CREATED   -> "created";
        case PROCESSED -> "processed";
        case FAILED    -> "failed";
    };
}
```

The code **compiles**, because all `State` constants are listed. However, calling `statusName(null)` enters no constant branch and **throws `NullPointerException`**. Exhaustiveness over enum constants does not automatically turn `null` into an enum constant.

In Java 21, you can handle `null` explicitly:

```java
static String statusNameOrMissing(State state) {
    return switch (state) {
        case null      -> "missing";
        case CREATED   -> "created";
        case PROCESSED -> "processed";
        case FAILED    -> "failed";
    };
}
```

`case null` is a dedicated label that handles the `null` value, not a `State` constant.

**`default` does not automatically catch `null`** in a Java 21 pattern switch. For instance, `case State s` and `default` still will not handle `null` as desired without a `case null` branch. You can use the combined syntax `case null, default -> ...` when you want the same handling for `null` and all remaining values.

## 7. Non-enum selector: using with `Object` and broader classification

Thanks to Java 21, `switch` can use a general reference type. For example, a method taking `Object`:

```java
static String classifyAny(Object value) {
    return switch (value) {
        case null         -> "null";
        case State.FAILED -> "failed";
        case State s      -> "state:" + s.name();
        case Level.WARN   -> "warning";
        case Level l      -> "level:" + l.name();
        default           -> "other";
    };
}
```

The branches are evaluated for matching as follows:

- `State.FAILED` matches that exact value.
- `State s` handles `State` constants other than `FAILED`.
- `Level.WARN` matches the warning level exactly.
- `Level l` handles `Level` constants other than `WARN`.
- `case null` handles `null`.
- `default` handles other types not belonging to the listed branches.

Because `Object` can hold many types, listing every value of just two enums **does not make** a switch on `Object` exhaustive. Use `default` or an appropriate catch-all pattern to handle the remaining possibilities.

### Why is `case State.FAILED` valid on `Object`?

The constant `State.FAILED` is an object; any `State` object can be assigned to an `Object` variable. According to Java 21's switch compatibility rules, an enum case constant must have a type that is *assignment-compatible* with the selector. `State` is compatible with `Object`, so the constant branch is valid.

Conversely, if the selector has type `Level`, you cannot use `case State.FAILED` because a `State` constant cannot be assigned to a `Level` variable. **That is a compile-time type compatibility error**, not a valid branch that merely evaluates to `false`.

## 8. Complete Java 21 program, compilable and runnable

Create the file **`EnumConstantPatternSwitchDemo.java`** matching the public class name:

```java
import java.util.Locale;

public class EnumConstantPatternSwitchDemo {

    sealed interface Event permits State, Level {}

    enum State implements Event {
        CREATED, PROCESSED, FAILED
    }

    enum Level implements Event {
        INFO, WARN
    }

    // Selector is the Event interface, but cases can be
    // constants of the enums implementing that interface.
    static String describe(Event event) {
        return switch (event) {
            case State.CREATED   -> "state-created";
            case State.PROCESSED -> "state-processed";
            case State.FAILED    -> "state-failed";
            case Level.INFO      -> "level-info";
            case Level.WARN      -> "level-warn";
            case null            -> "missing";
        };
    }

    // Switch on a specific enum, using short constant names.
    static String grouped(State state) {
        return switch (state) {
            case CREATED, PROCESSED -> "IN_PROGRESS";
            case FAILED             -> "STOPPED";
        };
    }

    // Specific enum constants must precede the type pattern
    // covering that enum to avoid a dominated case.
    static String mixed(Event event) {
        return switch (event) {
            case null        -> "UNKNOWN";
            case State.FAILED -> "STOP";
            case State s      -> "STATE:" +
                    s.name().toLowerCase(Locale.ROOT);
            case Level.WARN   -> "ALERT";
            case Level l      -> "LEVEL:" +
                    l.name().toLowerCase(Locale.ROOT);
        };
    }

    // Object-typed selector: includes qualified enum
    // constants, type patterns, and a default branch.
    static String fromObject(Object value) {
        return switch (value) {
            case null         -> "EMPTY";
            case State.CREATED -> "new state";
            case State s       -> "state:" + s.name();
            case Level.WARN    -> "warning";
            case Level l       -> "level:" + l.name();
            default            -> "other";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(State.CREATED));
        System.out.println(describe(Level.WARN));
        System.out.println(describe(null));

        System.out.println(grouped(State.PROCESSED));
        System.out.println(grouped(State.FAILED));

        System.out.println(mixed(State.FAILED));
        System.out.println(mixed(State.PROCESSED));
        System.out.println(mixed(Level.INFO));
        System.out.println(mixed(Level.WARN));

        System.out.println(fromObject(State.CREATED));
        System.out.println(fromObject(Level.INFO));
        System.out.println(fromObject(17));
        System.out.println(fromObject(null));
    }
}
```

Use **JDK 21 or later**:

```bash
javac --release 21 EnumConstantPatternSwitchDemo.java
java EnumConstantPatternSwitchDemo
```

Expected output:

```text
state-created
level-warn
missing
IN_PROGRESS
STOPPED
STOP
STATE:processed
LEVEL:info
ALERT
new state
level:INFO
other
EMPTY
```

**Explanation of the main branches:**

1. `describe` takes `Event`, yet compares each enum constant of `State` and `Level` directly. Because both enums are fully covered, the `switch` expression is exhaustive; `case null` handles null input separately.
2. `grouped` demonstrates a traditional enum switch: multiple constants can share a branch without declaring a pattern variable.
3. `mixed` places `State.FAILED` before `State s` and `Level.WARN` before `Level l`. `State.PROCESSED` goes to the type pattern `State s` and prints `STATE:processed`; `Level.WARN` is handled by the specific constant branch and yields `ALERT`.
4. `fromObject` also receives `17` (boxed into `Integer`). No enum branch matches, so `default` is selected and prints `other`.
5. `null` is checked upfront with `case null` in switches taking a reference type, avoiding the default `NullPointerException`.

The program uses **Java 21 finalized features**; there is no `--enable-preview` in the compile command. If an IDE or build tool is set to language level 17, it may report errors on `case State.CREATED` with selector `Event` and on type patterns in switch — select JDK/language level 21 for this example.

## 9. Common compile errors and how to fix them

### Error 1: using an unqualified enum constant when the selector is an interface

```java
// INVALID if event has type Event:
// switch (event) {
//     case CREATED -> System.out.println("created");
//     default -> System.out.println("other");
// }
```

`Event` is not a concrete enum type for Java to associate the short name `CREATED` with an enum class.

**Fix:**

```java
switch (event) {
    case State.CREATED -> System.out.println("created");
    default            -> System.out.println("other");
}
```

The fix shows a statement inside a method where `Event event` is already declared; if `event == null`, you must add `case null` if you do not want a `NullPointerException` to be thrown.

### Error 2: using an enum constant not assignable to the selector type

```java
// DOES NOT COMPILE if level has type Level:
// switch (level) {
//     case State.CREATED -> System.out.println("bad");
//     default -> System.out.println("other");
// }
```

`State.CREATED` has type `State`, which cannot be assigned to a `Level` variable. Only use constants of an enum type compatible with the selector, or widen the selector to a common interface if the business logic genuinely accepts both enums.

### Error 3: placing a general type pattern before a specific constant

```java
// DOES NOT COMPILE due to dominated case:
// switch (event) {
//     case State s       -> System.out.println("any-state");
//     case State.CREATED -> System.out.println("created");
//     case Level l       -> System.out.println("level");
// }
```

**Fix:** move `case State.CREATED` above `case State s` so the specific exception is handled first and the rest by the general branch.

### Error 4: assuming an enum constant case has a pattern variable

```java
// INVALID:
// switch (event) {
//     case State.CREATED -> System.out.println(CREATED.name());
//     default -> System.out.println("other");
// }
```

`case State.CREATED` does not declare a variable named `CREATED`. If you need to use the constant value, call `State.CREATED.name()` directly; if you need the actual matched object of type `State`, use `case State s` and access `s`.

### Error 5: attaching `when` directly after an enum constant

```java
// DOES NOT COMPILE:
// case State.CREATED when flag -> "created";
```

`when` is only used after a case pattern. For a specific constant, use `case State.CREATED -> { ... }` to check the condition in the branch body, or switch to `case State s when s == State.CREATED && flag` if you want to express a guard.

### Error 6: assuming `default` handles all `null` values

```java
// Still throws NullPointerException if event is null:
static String wrongNullHandling(Event event) {
    return switch (event) {
        case State s -> "state";
        case Level l -> "level";
        default      -> "other";
    };
}
```

**Fix:** add `case null -> "missing"` or the combined label `case null, default -> "other"` depending on business intent. `null` is not an enum constant.

### Error 7: switch expression missing a covering branch

```java
// DOES NOT COMPILE if status has type State:
// return switch (status) {
//     case CREATED   -> "created";
//     case PROCESSED -> "processed";
// };
```

`FAILED` is missing. Add `case FAILED`, or provide an appropriate catch-all branch. One advantage of an exhaustive enum switch is that the compiler helps detect missed cases when the source is recompiled.

## 10. When to choose enum constant, type pattern, or `when`?

| Scenario | Preferred approach | Reason |
| --- | --- | --- |
| Selector is a concrete enum, each constant has its own behavior | `case CREATED`, `case FAILED` | Concise, easy to verify all constants are covered |
| Selector is an interface implemented by multiple enums | `case State.CREATED`, `case Level.WARN` | Clearly indicates the origin of each constant |
| Multiple enum constants share the same behavior | `case State.CREATED, State.PROCESSED` | Intentional grouping of constant branches |
| Need uniform handling for all values of an enum | `case State s` | Provides a `State`-typed variable to use |
| Need an exception for one constant before general handling | Specific constant first, type pattern after | Avoids domination, easy to read |
| Check condition depends on properties or dynamic state | `case State s when ...` | Additional guard on a pattern |
| Selector can be `null` | `case null` | Explicit null handling |
| Input can have many types beyond known enums | `default` or a catch-all pattern | Ensures a branch handles remaining values |

**Design note:** A very long chain of branches for individual enum constants can be reasonable if the constants correspond to fixed business states. However, if all constants share the same behavior, using `case State s` or a polymorphic method on the interface reduces duplication. There is no need to force every switch into a pattern switch.

## 11. Practice exercises and answers

### Exercise 1 — identify case constant vs. case pattern

Given three branches:

```java
case State.CREATED -> "a";
case State s -> "b";
case State s when s == State.FAILED -> "c";
```

**Question:** Which branches declare a pattern variable?

**Answer:** The two branches with `State s` declare the variable `s`; `State.CREATED` is only a case constant. Note that the three lines above are **syntax fragments** for identification; if all three were placed in that exact order in the same switch, the third branch would be dominated by the preceding `case State s` and cause a compile error. When a special `case` is needed, place the guard or specific constant before the general branch.

### Exercise 2 — why is the following example rejected?

```java
// DOES NOT COMPILE:
// static String task(Event event) {
//     return switch (event) {
//         case State s      -> "any state";
//         case State.FAILED -> "failed";
//         case Level l      -> "level";
//     };
// }
```

**Answer:** `case State s` already matches all `State` values, including `State.FAILED`, so the subsequent `case State.FAILED` is unreachable (*dominated*). Move the `State.FAILED` branch earlier.

### Exercise 3 — complete the switch expression

Suppose:

```java
enum Result { OK, RETRY, ERROR }
```

Write a method that converts every non-`null` `Result` value into the three corresponding strings `"success"`, `"again"`, `"failure"`. Do not use `default`, so the compiler checks that all enum constants are covered.

**Suggested answer:**

```java
static String message(Result result) {
    return switch (result) {
        case OK    -> "success";
        case RETRY -> "again";
        case ERROR -> "failure";
    };
}
```

With `null` input, this method throws `NullPointerException`; if you want to return `"missing"`, add `case null -> "missing"` when compiling with Java 21.

### Exercise 4 — classify two enums with the same constant names

Assume the `Action` interface is implemented by `NetworkAction` and `FileAction` from section 3. Write `switch (Action action)` to return `"net-open"` for `NetworkAction.OPEN`, `"file-open"` for `FileAction.OPEN`, and `"close"` for both `CLOSE` constants.

**Answer:**

```java
static String classify(Action action) {
    return switch (action) {
        case NetworkAction.OPEN  -> "net-open";
        case FileAction.OPEN     -> "file-open";
        case NetworkAction.CLOSE, FileAction.CLOSE -> "close";
    };
}
```

**Qualified enum names** are required because the selector is the `Action` interface. The third branch contains **two enum constants** with the same result. All constants of both enums are covered, so the switch expression is exhaustive in Java 21.

### Exercise 5 — predict the output

For the complete program in section 8:

- `describe(State.FAILED)` → `"state-failed"`.
- `mixed(State.FAILED)` → `"STOP"`, because the specific constant precedes the type pattern `State s`.
- `mixed(State.CREATED)` → `"STATE:created"`, because it does not match `State.FAILED` but matches `State s`.
- `fromObject(42)` → `"other"`, because `Integer` does not belong to either enum.
- `fromObject(null)` → `"EMPTY"`, because `case null` is present.

Explaining why each branch is selected is more important than memorizing the output.

## 12. Key takeaways

1. **An enum constant** like `State.CREATED` is a specific enum value. `case State.CREATED` is a **case constant** and does not declare a pattern variable.
2. **Java 21** allows qualified enum constants in switch even when the selector is an interface or a broader reference type, provided the constant is assignable to the selector type.
3. For a concrete enum-typed selector, `case CREATED` remains valid shorthand. For an interface-typed selector with multiple implementing enums, write `case State.CREATED`, `case Level.WARN` to specify the constant to match.
4. Enum constants and type patterns can be mixed in the same switch, but place **specific constants before broader patterns** to avoid dominance errors.
5. **`when` only accompanies a case pattern**, never directly after an enum case constant.
6. Switch expressions must be exhaustive; for an enum or an appropriate sealed hierarchy, listing all constants can satisfy this requirement without `default`.
7. **`null` is not an enum constant**. Constant-based exhaustiveness does not automatically handle `null`; to handle `null`, use `case null` in Java 21.

**Bottom line:** In a pattern switch, an enum constant is a tool for identifying **one exact value**, while a type pattern identifies **an entire kind of object**. Understanding the difference helps you write shorter switches, verify exhaustiveness better, and avoid type-compatibility or dominated-branch errors.

## Official references

- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Oracle Java 21 — Java Language Changes](https://docs.oracle.com/en/java/javase/21/language/java-language-changes-release.html)
- [Java SE 21 Language Specification, §14.11 — The switch Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
- [Java SE 21 Language Specification, §15.28 — switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28)
