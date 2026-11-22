# Arrow Form `->` and Branch Block Scope in Java

> **Java core — language-basics / Switch**  
> **Environment:** JDK 17+, preview disabled, no external libraries.  
> **Goal:** Write `case ... ->` switches correctly, distinguish `switch` **statements** from **expressions**, understand variable scope inside each `{ ... }` block, know when `yield` is needed, and understand why *fall-through* does not occur as in `case ...:`.

## 1. Basic Rules of the Arrow Form

The traditional form uses `case ...:` labels and usually requires `break`. The arrow form `case ... ->` is officially supported in Java 17 and **executes only the selected branch**, without automatically falling into the next branch's code:

~~~java
int code = 2;
switch (code) {
    case 1 -> System.out.println("ONE");
    case 2 -> System.out.println("TWO");
    default -> System.out.println("OTHER");
}
// Prints only TWO.
~~~

This `switch` construct is a **statement**, meaning a control-flow action rather than an expression returning a value.

An arrow branch in a switch statement can be a **statement expression** (such as a method call), a **block `{...}`**, or a `throw` statement. If multiple statements must run in a branch, place them inside a block:

~~~java
switch (code) {
    case 1 -> {
        System.out.println("ONE");
        System.out.println("Audited");
    }
    case 2 -> System.out.println("TWO");
    default -> System.out.println("OTHER");
}
~~~

No `break` is needed after a `->` branch. Adding curly braces groups multiple statements and defines variable scope, **not to prevent fall-through** as in the `:` form.

## 2. Both Statements and Expressions Can Use `->`

`switch (code) { case 1 -> System.out.println("ONE"); default -> System.out.println("OTHER"); }` is a **statement** performing an action. Conversely, `String label = switch (code) { case 1 -> "ONE"; default -> "OTHER"; };` is an **expression** producing a value.

Neither falls through. An expression must also cover all cases and produce a result of the right type; later lessons analyze that separately. Here the focus is on arrow rules and variable scope.

## 3. Local Variable Scope of a Branch Block

Each `{ ... }` block of an arrow branch is a **separate local scope**:

~~~java
int code = 1;
switch (code) {
    case 1 -> {
        int amount = 10;
        System.out.println(amount);
    }
    case 2 -> {
        int amount = 20; // VALID: different variable, in a different block.
        System.out.println(amount);
    }
    default -> System.out.println("OTHER");
}
~~~

Branch 1's `amount` variable is not visible in branch 2 or after `switch`. Branch 2 can declare the **exact same name** because the two variables' scopes do not overlap. A local variable exists only within **the block where it is declared**; it does not automatically become shared across cases.

~~~java
// DOES NOT COMPILE if placed after switch in the example above:
// System.out.println(amount); // Cannot find symbol.
~~~

If data must be used **after `switch`**, choose one of two approaches:

- When the data is **a single value**, prefer `String result = switch (...) { ... };`.
- For a statement that needs to update an existing variable, declare the variable outside the switch and assign it explicitly in each branch; ensure all required paths assign a value.

Do not rely on indentation to create scope: Java relies on `{ }` braces and declaration placement. Reusing the same name across branches helps illustrate scope, though in practice meaningful names should still be used.

## 4. When a Block Needs to Return a Value

In a switch expression, a single-expression branch can be `case 0 -> "ZERO";`. If the branch needs multiple statements, the block returns its result via `yield`:

~~~java
String result = switch (code) {
    case 2 -> {
        int scaled = code * 10;
        yield "GROUP-" + scaled;
    }
    default -> "OTHER";
};
~~~

A switch statement with a block simply executes statements and **does not need** `yield`. The `yield` lesson analyzes paths, `break`, and `throw` in greater detail.

## 5. Grouping Labels, `default`, `throw`, and Unselected Branches

You can group multiple distinct values on a single arrow branch:

~~~java
String group = switch (code) {
    case 1, 2 -> "SMALL";
    case 3 -> "THREE";
    default -> "OTHER";
};
~~~

`case 1, 2` does not run the branch twice; it is **one branch** selected when `code` is 1 **or** 2. Duplicate label values within the same switch are rejected at compile time.

An expression branch can throw an exception instead of producing a value:

~~~java
static String positiveLabel(int value) {
    return switch (value) {
        case -1 -> throw new IllegalArgumentException("negative");
        case 0 -> "ZERO";
        default -> {
            int twice = value * 2;
            yield "DOUBLE=" + twice;
        }
    };
}
~~~

If `value == 0`, the `default` block **does not run**. If `value == -1`, the exception is thrown from the selected branch. In both cases, Java does not run another branch's code just because it appears below.

In Java 17 without preview enabled, a `String`/`enum`/wrapper selector with value `null` can cause `NullPointerException`; `default` does not automatically catch null. Check for null beforehand if data may be absent.

## 6. Comparing Scope and Fall-Through with the Colon Form

A colon-style `switch` uses `case ...:` **statement groups**; if `break` is missing, code can run straight into the next group:

~~~java
static String colonDemo(int code) {
    StringBuilder log = new StringBuilder();
    switch (code) {
        case 1:
            log.append("ONE");
        case 2:
            log.append("+TWO");
            break;
        default:
            log.append("OTHER");
    }
    return log.toString();
}
// colonDemo(1) = "ONE+TWO" (fall-through).
// colonDemo(2) = "+TWO".
~~~

By contrast, `case 1 -> log.append("ONE");` in an arrow switch statement **does not** automatically execute case 2.

| Aspect | `case ...:` form | `case ... ->` form |
| --- | --- | --- |
| Unintended fall-through | Can happen if `break` is missing | None |
| Local block `{...}` | Should be added when separate scope is needed | Explicit per block branch |
| Multiple labels sharing code | Multiple consecutive `case`s | `case 1, 2 ->` |
| Multiple statements in a branch | Statements until `break` or next group | Write `{ statement1; statement2; }` |

With colon-style cases, variables declared directly in the same switch block can cause name collisions or *definite assignment* errors when control jumps to another label. Wrapping each group in `{...}` also helps prevent scope confusion in the traditional form.

**Do not mix** `case ...:` and `case ... ->` in the same `switch`.

## 7. Standalone Java 17+ Example

Create file **`ArrowSwitchScopeDemo.java`**:

~~~java
public final class ArrowSwitchScopeDemo {
    enum State { NEW, RUNNING, DONE }

    private static String statement(int code) {
        StringBuilder log = new StringBuilder();
        switch (code) {
            case 0 -> log.append("ZERO");
            case 1 -> {
                int local = code + 10;
                log.append("ONE=").append(local);
            }
            case 2 -> {
                int local = code + 20; // Valid: separate scope.
                log.append("TWO=").append(local);
            }
            default -> log.append("UNKNOWN");
        }
        return log.toString();
    }

    private static String expression(int code) {
        return switch (code) {
            case 0 -> "ZERO";
            case 1, 2 -> {
                int scaled = code * 10;
                yield "GROUP-" + scaled;
            }
            default -> "OTHER";
        };
    }

    private static String byState(State state) {
        return switch (state) {
            case NEW -> "new";
            case RUNNING -> "running";
            case DONE -> "done";
        };
    }

    private static String colonDemo(int code) {
        StringBuilder log = new StringBuilder();
        switch (code) {
            case 1:
                log.append("ONE");
            case 2:
                log.append("+TWO");
                break;
            default:
                log.append("OTHER");
        }
        return log.toString();
    }

    private static String guarded(int value) {
        return switch (value) {
            case -1 -> throw new IllegalArgumentException("negative");
            case 0 -> "ZERO";
            default -> {
                int twice = value * 2;
                yield "DOUBLE=" + twice;
            }
        };
    }

    public static void main(String[] args) {
        System.out.println("stmt0=" + statement(0));
        System.out.println("stmt1=" + statement(1));
        System.out.println("stmt2=" + statement(2));
        System.out.println("stmt9=" + statement(9));

        System.out.println("expr0=" + expression(0));
        System.out.println("expr1=" + expression(1));
        System.out.println("expr2=" + expression(2));
        System.out.println("expr9=" + expression(9));

        System.out.println("enumNew=" + byState(State.NEW));
        System.out.println("enumDone=" + byState(State.DONE));

        System.out.println("colon1=" + colonDemo(1));
        System.out.println("colon2=" + colonDemo(2));
        System.out.println("colon9=" + colonDemo(9));

        System.out.println("guard0=" + guarded(0));
        System.out.println("guard3=" + guarded(3));
        try {
            guarded(-1);
        } catch (IllegalArgumentException ex) {
            System.out.println("guardNegative=IllegalArgumentException");
        }
    }
}
~~~

Compile/run in the directory containing the file (Bash, PowerShell, or Command Prompt):

~~~bash
javac -encoding UTF-8 ArrowSwitchScopeDemo.java
java ArrowSwitchScopeDemo
~~~

**Exact expected stdout:**

~~~text
stmt0=ZERO
stmt1=ONE=11
stmt2=TWO=22
stmt9=UNKNOWN
expr0=ZERO
expr1=GROUP-10
expr2=GROUP-20
expr9=OTHER
enumNew=new
enumDone=done
colon1=ONE+TWO
colon2=+TWO
colon9=OTHER
guard0=ZERO
guard3=DOUBLE=6
guardNegative=IllegalArgumentException
~~~

The two statement branches for `code=1`/`code=2` both declare a `local` variable without conflict because each has its own scope. The lines `expr1`/`expr2` demonstrate `yield` from a block. `colon1=ONE+TWO` contrasts `:` fall-through with `->` executing only one branch.

## 8. Common Mistakes and Exercises

| Case | How to handle |
| --- | --- |
| Want to run multiple statements after `->` | Place them inside `{ ... }` |
| Reading a branch's local variable outside the block | Declare a shared variable outside or return a value with a switch expression |
| Switch expression block does not return a value | Write `yield value;` on normal completion paths |
| Trying to use `break value;` instead of `yield` | Use `yield value;` |
| Worrying about adding `break` after a `->` branch | Not needed; arrow rules do not fall through |
| Want to group multiple values | `case 1, 2 -> ...` |
| Nullable selector in Java17 | Check for `null` before switch |

**Exercise 1.** Write a `switch` statement using `->` with codes 1, 2, and default. In each branch, add two print statements; determine whether `break` is needed.

**Exercise 2.** In the two blocks `case 1 -> { int x = 1; ... }` and `case 2 -> { int x = 2; ... }`, why does the same name `x` not cause an error? Try using `x` after the switch to observe the scope issue.

**Exercise 3.** Convert a label-computing `switch` statement into a `switch` expression. When a branch needs to create a variable and then return a value, which keyword is used?

**Exercise 4.** Predict the result of `colonDemo(1)` and explain why a `->` switch does not exhibit the same behavior.

**Exercise 5.** Write a switch expression on an enum covering all constants so `default` is not needed. Separately check the `null` selector case in Java 17.

### Key Takeaway

**`case ... ->` does not fall through.** A branch with multiple statements needs `{...}`, which also bounds local variable scope. In a **switch expression**, a single-expression branch can return an expression directly; a multi-statement block branch uses **`yield`** to return its value. A `switch statement` performs actions, whereas a `switch expression` computes a value and must cover all valid cases.