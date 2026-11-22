# Exhaustiveness Requirements and Result Type Selection in Java `switch`

> **Java core — language-basics / Switch**  
> **Version:** Java 17+ (preview disabled); standalone program, JDK only.  
> **Goal:** Understand why a `switch expression` must **cover all cases**, when `default` is needed, how `yield`/`throw` affect paths, and why the **result type** must fit where the expression is used.

## 1. Distinguishing `switch statement` from `switch expression`

A `switch statement` controls actions; it is **not required** to have `default`:

~~~java
int code = 9;
switch (code) {
    case 1 -> System.out.println("ONE");
    case 2 -> System.out.println("TWO");
}
// Prints nothing when code = 9: the statement has no matching branch.
~~~

A `switch expression` **computes a value** to return or assign:

~~~java
int code = 9;
String text = switch (code) {
    case 1 -> "ONE";
    case 2 -> "TWO";
    default -> "OTHER";
};
System.out.println(text); // OTHER
~~~

Without `default` for just labels 1 and 2 in a `switch expression` over `int`, the compiler cannot guarantee a value when `code` is 9. Therefore it reports an error like **switch expression does not cover all possible input values** (wording varies by JDK).

**Exhaustiveness** is a **compile-time** check for switch expressions; it does not mean every branch runs or every value must have its own separate label.

## 2. `default` and Covering Numeric or `String` Values

For an `int` or `String` selector in Java 17, the standard way to cover the entire domain is adding **one `default`**:

~~~java
static String classify(int value) {
    return switch (value) {
        case 0 -> "ZERO";
        case 1, 2 -> "SMALL";
        default -> "OTHER";
    };
}
~~~

`case 1, 2` combines **two distinct values** into one branch. `default` handles every `int` value other than 0, 1, and 2. Label order in arrow form does not cause fall-through.

Error example (kept in comments, not in runnable code):

~~~java
// DOES NOT COMPILE: infinitely many int values remain unhandled.
// String label = switch (code) {
//     case 0 -> "ZERO";
//     case 1 -> "ONE";
// };
~~~

With `String`, you also need a branch for unlisted contents:

~~~java
static String command(String input) {
    return switch (input) {
        case "go" -> "MOVE";
        case "stop" -> "HALT";
        default -> "UNKNOWN";
    };
}
~~~

**`default` is not a `null` branch**: non-preview Java 17 throws `NullPointerException` if a `String`/enum/wrapper selector is null. If null is a valid application input, check for it **before `switch`**.

## 3. `enum` Can Be Exhaustive Without `default`

With an `enum` whose constants are all known, every case can be listed:

~~~java
enum State { NEW, RUNNING, DONE }

static String status(State state) {
    return switch (state) {
        case NEW -> "NEW";
        case RUNNING -> "IN_PROGRESS";
        case DONE -> "COMPLETE";
    };
}
~~~

The `switch expression` on `State` above **already covers all** enum constants and needs no `default`.

Benefit of **not** writing `default` for an exhaustively listed enum: if a new constant is added and the code is recompiled, the compiler can point out which switch expressions need updating instead of silently routing the new state into a generic default branch.

If `DONE` is omitted without `default`, the switch expression is **not exhaustive** and will not compile. By contrast, a `switch statement` may handle only some states without being forced to cover all of them.

Covering all enum constants **does not mean covering null**. A separate null guard is still required when data may be missing.

## 4. Every Normal Path Must Produce a Value

In a `switch expression`, a short arrow branch can supply a result directly:

~~~java
int score = 1;
int points = switch (score) {
    case 0 -> 0;
    case 1 -> 10;
    default -> 100;
};
~~~

If a branch needs multiple statements, place them in a block and use `yield value;`:

~~~java
int result = switch (score) {
    case 0 -> 0;
    default -> {
        int computed = score * 10;
        yield computed;
    }
};
~~~

Any path that **completes normally** in a switch expression block must provide a value via `yield`; execution cannot reach the end of the block without a result.

A branch is allowed to **throw an exception** instead of returning a value:

~~~java
static int priority(int value) {
    return switch (value) {
        case 0 -> 0;
        default -> {
            if (value < 0) {
                throw new IllegalArgumentException("negative");
            }
            yield value * 10;
        }
    };
}
~~~

This remains exhaustive: `default` handles all non-zero values, while negative cases terminate by exception rather than normal completion.

Do not confuse `yield` with `break`: `break;` exits a traditional switch statement; `yield expression;` produces a result for a switch expression. `break value;` is not valid Java 17 syntax.

## 5. The Result Type Must Fit Where the Expression Is Used

Java does not only consider which branch runs — it also checks **the types of branch expressions at compile time**.

~~~java
int code = 1;
String label = switch (code) {
    case 1 -> "ONE";
    default -> "OTHER";
};
~~~

Here every result converts to `String`. However, the following **does not compile**:

~~~java
// DOES NOT COMPILE: an int branch cannot be used as String.
// String wrong = switch (code) {
//     case 1 -> "ONE";
//     default -> 2;
// };
~~~

Useful rules:

- If a switch expression appears in an **assignment or method-argument context**, it can be **target-typed** (a *poly* expression): each branch must be compatible with the target type.
- In a context without an applicable target type (*standalone expression*), Java determines the type by its own rules from the branches, including numeric promotion or a common reference supertype when appropriate.
- `yield` inside a block must also produce a value compatible with the required result type.
- Do not infer types from **whichever branch is actually chosen at runtime**; the compiler checks all branches that can yield a result.

For example, when the target is `double`, a branch with an `int` literal still converts:

~~~java
double number = switch (code) {
    case 1 -> 1;
    default -> 2.5;
};
// code=1: number=1.0.
~~~

If the target is `Number`, numeric objects of different subclasses can be chosen:

~~~java
Number boxed = switch (code) {
    case 1 -> Integer.valueOf(10);
    default -> Double.valueOf(2.5);
};
// code=1: boxed has runtime class Integer.
~~~

`Number` is the common superclass; the actual runtime value can still be an `Integer` or a `Double` depending on the branch. This is **not** advice to mix types arbitrarily: in business code, choosing a consistent, clear target type reduces surprises from conversions/boxing.

## 6. Table for Choosing Coverage and Result Types

| Scenario | Valid coverage in Java 17 | Result type |
| --- | --- | --- |
| Switch expression on `int` | Has `default` for values outside `case` | Every branch returns a compatible type |
| Switch expression on `String` | Has `default` for unlisted contents; handle `null` separately | E.g., `String` |
| Switch expression on `enum` | List all constants, or have an appropriate default branch | E.g., `String` |
| Arrow branch with multiple statements | `{ ... yield value; }` or throws an exception | `yield` compatible with target type |
| Branch with only `throw` | Completes abnormally, no value needed on that path | Remaining value-returning branches must still be compatible |
| Switch statement used to log | Can omit `default` | The switch itself has no value type |

The two checks are **independent**: (1) the construct covers all required selector values; (2) the branches return results compatible with the target type. Having `default` can still fail if a branch returns the wrong type; every branch returning `String` can still fail if `default` is missing.

Do not confuse exhaustive with "never fails": a branch can throw an exception, a null selector can cause NPE, and input data still needs business validation.

## 7. Standalone Java 17+ Example

Create file **`ExhaustiveSwitchTypeDemo.java`**:

~~~java
public final class ExhaustiveSwitchTypeDemo {
    enum State { NEW, RUNNING, DONE }

    private static String action(int code) {
        return switch (code) {
            case 0 -> "ZERO";
            case 1, 2 -> "SMALL";
            default -> {
                String label = "OTHER:" + code;
                yield label;
            }
        };
    }

    private static String stateName(State state) {
        return switch (state) {
            case NEW -> "NEW";
            case RUNNING -> "IN_PROGRESS";
            case DONE -> "COMPLETE";
        };
    }

    private static String command(String text) {
        return switch (text) {
            case "go" -> "MOVE";
            case "stop" -> "HALT";
            default -> "UNKNOWN";
        };
    }

    private static double numeric(int code) {
        return switch (code) {
            case 1 -> 1;
            default -> 2.5;
        };
    }

    private static Number boxed(int code) {
        return switch (code) {
            case 1 -> Integer.valueOf(10);
            default -> Double.valueOf(2.5);
        };
    }

    private static int priority(int value) {
        return switch (value) {
            case 0 -> 0;
            default -> {
                if (value < 0) {
                    throw new IllegalArgumentException("negative");
                }
                yield value * 10;
            }
        };
    }

    public static void main(String[] args) {
        System.out.println("action0=" + action(0));
        System.out.println("action1=" + action(1));
        System.out.println("action2=" + action(2));
        System.out.println("action3=" + action(3));
        System.out.println("actionMinus1=" + action(-1));

        System.out.println("enumNew=" + stateName(State.NEW));
        System.out.println("enumRunning=" + stateName(State.RUNNING));
        System.out.println("enumDone=" + stateName(State.DONE));

        System.out.println("commandGo=" + command(new String("go")));
        System.out.println("commandOther=" + command("GO"));

        System.out.println("numeric1=" + numeric(1));
        System.out.println("numeric2=" + numeric(2));

        Number a = boxed(1);
        Number b = boxed(2);
        System.out.println("boxed1=" + a.getClass().getSimpleName() + ":" + a);
        System.out.println("boxed2=" + b.getClass().getSimpleName() + ":" + b);

        System.out.println("priority0=" + priority(0));
        System.out.println("priority3=" + priority(3));
        try {
            priority(-1);
        } catch (IllegalArgumentException ex) {
            System.out.println("priorityNegative=IllegalArgumentException");
        }

        try {
            command(null);
        } catch (NullPointerException ex) {
            System.out.println("nullSelector=NullPointerException");
        }
    }
}
~~~

Compile and run in the directory containing the file (Bash, PowerShell, or Command Prompt):

~~~bash
javac -encoding UTF-8 ExhaustiveSwitchTypeDemo.java
java ExhaustiveSwitchTypeDemo
~~~

**Exact expected stdout:**

~~~text
action0=ZERO
action1=SMALL
action2=SMALL
action3=OTHER:3
actionMinus1=OTHER:-1
enumNew=NEW
enumRunning=IN_PROGRESS
enumDone=COMPLETE
commandGo=MOVE
commandOther=UNKNOWN
numeric1=1.0
numeric2=2.5
boxed1=Integer:10
boxed2=Double:2.5
priority0=0
priority3=30
priorityNegative=IllegalArgumentException
nullSelector=NullPointerException
~~~

`action3`/`actionMinus1` go through `default` and `yield`; the enum needs no `default` because all constants are covered. `numeric1=1.0` shows converting `int` to `double`; `boxed1`/`boxed2` show that target type `Number` can hold different subclasses. Branch `priority(-1)` throws an exception, yet the entire expression remains exhaustive.

## 8. Common Mistakes and Exercises

| Error | Fix |
| --- | --- |
| Switch expression on `int` with only `case 1` | Add `default` to cover other inputs |
| Switch expression on enum missing a constant | Add the missing `case` or an appropriate default branch |
| Block branch missing `yield` on normal completion path | Write `yield value;` or use a direct expression branch |
| Using `break value;` to produce a result | Replace with `yield value;` |
| `String` and `int` results for a `String` target | Change branch to a compatible type |
| Assuming `default` handles `null` | Check for null before standard Java 17 switch |
| Using a switch statement expecting a returned value | Convert to a switch expression |

**Exercise 1.** Write a switch expression classifying `int level`: 0 → `"LOW"`, 1 → `"MEDIUM"`, others → `"OTHER"`. Try removing `default` and explain the error.

**Exercise 2.** Create an enum with three constants and write a switch expression listing all three branches without `default`. Add a fourth constant and try recompiling.

**Exercise 3.** Write a branch `case 2 -> { int x = 20; yield "Value=" + x; }`. Why can you not simply write `x;` at the end of the block?

**Exercise 4.** Compare the result types of `double x = switch (...) { case 1 -> 1; default -> 2.5; };` and `Number x = switch (...) { case 1 -> Integer.valueOf(1); default -> Double.valueOf(2.5); };`.

**Exercise 5.** Write a `default` branch that throws `IllegalArgumentException` if input is negative, and returns a value if positive. Does the compiler require a value from the exception-throwing branch? Why?

### Key Takeaway

**A switch expression must be exhaustive and have a valid result type.** For `int`/`String`, `default` is usually needed; for `enum`, all constants can be covered. Single-expression branches return values directly, multi-statement blocks use **`yield`**, and error branches may `throw`. Java checks type compatibility across **all branches at compile time**, without waiting for a branch to be selected.