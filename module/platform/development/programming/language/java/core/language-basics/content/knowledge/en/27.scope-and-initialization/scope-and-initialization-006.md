# Checking That Variables Are Assigned on All Branches Before Use — Java 17+

## 1. The definite assignment rule

In Java, **a local variable must be definitely assigned a value before it is read** (*definite assignment*). The compiler analyzes all control-flow paths that can reach a read, rather than testing just a single sample run.

~~~java
static int choose(boolean flag) {
    int result;                 // Valid: declaration only.
    if (flag) {
        result = 10;
    } else {
        result = 20;
    }
    return result;              // Valid: both branches assign it.
}
~~~

With `choose(true)`, the result is 10; with `choose(false)`, the result is 20. Conversely:

~~~java
// Does not compile if uncommented:
static int wrong(boolean flag) {
    int result;
    if (flag) {
        result = 10;
    }
    // return result; // variable result might not have been initialized
    return -1; // This line is only so the example still compiles while the erroneous line is commented out.
}
~~~

**Core point:** it is permitted to **declare first, assign later**; however, on every path reaching the **read**, the variable must be definitely assigned.

## 2. Local variables have no default value

~~~java
int[] values = new int[2]; // Both elements default to 0.
int local;                 // Does not automatically get the value 0.
// System.out.println(local); // Compile error: not yet assigned.
local = 5;
System.out.println(local); // 5.
~~~

Distinction:

| Storage location | Has a default value? |
|---|---|
| Local variable `int x;` | **No**; must be assigned before reading |
| Method parameter | Has the value passed by the caller when the invocation starts |
| Instance field `int count;` | **Yes**: defaults to 0 |
| Static field `boolean ready;` | **Yes**: defaults to false |
| Elements of `new int[3]` | **Yes**: elements default to 0 |
| Reference-type local variable `String s;` | **No**; does not automatically receive null |
| Reference-type field `String s;` | **Yes**: defaults to null |

**Scope** (the variable is within scope) does not mean **definite assignment** (the variable has been definitely assigned).

## 3. `if/else`: every branch reaching a read must be considered

**Wrong:**

~~~java
// static int bad(boolean active) {
//     int score;
//     if (active) score = 90;
//     return score; // Error: active == false leaves it unassigned.
// }
~~~

**Right — both branches assign:**

~~~java
static int score(boolean active) {
    int value;
    if (active) value = 90;
    else value = 0;
    return value;
}
~~~

**Right — initialize beforehand, then conditionally update:**

~~~java
int value = 0;
if (active) {
    value = 90;
}
System.out.println(value);
~~~

In the latter snippet, `value = 0` provides a value for all paths; `if` only **overwrites** it when the condition is true. Choose a way that expresses the data's true meaning—do not assign 0 just to silence the compiler if domain logic does not permit 0.

**Right — the unassigned branch terminates the method:**

~~~java
static int doublePositive(int input) {
    int result;
    if (input < 0) return -1;
    result = input * 2;
    return result;
}
~~~

When `input < 0`, there is no path reaching `return result`. Therefore, that branch does not need to assign `result`.

## 4. Multiple branches and expression-based assignment

If you have an `if / else if` chain, do not forget the case where **none of the branches match**.

~~~java
static String band(int n) {
    String result;
    if (n < 0) {
        result = "NEGATIVE";
    } else if (n == 0) {
        result = "ZERO";
    } else {
        result = "POSITIVE";
    }
    return result; // All paths to here have assigned it.
}
~~~

If you omit the `else` branch, the compiler cannot confirm that `n > 0` is also assigned.

You can also produce a value directly with the ternary operator:

~~~java
int result = active ? 90 : 0;
~~~

Both result operands provide a value for the expression; there is no need to create an uninitialized local and prove each branch manually.

## 5. `switch`: use `default` or a valid switch expression

With a `switch` statement, the `case` labels may not cover every possible value:

~~~java
// static int badSwitch(int code) {
//     int result;
//     switch (code) {
//         case 1 -> result = 100;
//         case 2 -> result = 200;
//     }
//     return result; // Not guaranteed assigned when code is not 1 or 2.
// }
~~~

**Fix with `default`:**

~~~java
static int statusCode(int code) {
    int result;
    switch (code) {
        case 1 -> result = 100;
        case 2 -> result = 200;
        default -> result = -1;
    }
    return result;
}
~~~

Or use a **switch expression** supported in Java 17:

~~~java
static int statusCodeExpression(int code) {
    return switch (code) {
        case 1 -> 100;
        case 2 -> 200;
        default -> -1;
    };
}
~~~

A switch expression is required to provide a value according to exhaustiveness rules; with an `int` selector, using `default` in the example covers the remaining values. Do not confuse a **switch statement** with a **switch expression**.

## 6. Loops: do not assume the body is guaranteed to execute

~~~java
// static int brokenLoop(boolean run) {
//     int result;
//     while (run) {
//         result = 7;
//         break;
//     }
//     return result; // Error: while can execute 0 iterations.
// }
~~~

If the loop condition is false right away, the body does not execute and `result` remains unassigned.

**Clearer approach when a default value is needed:**

~~~java
static int loopWithDefault(boolean run) {
    int result = -1;
    while (run) {
        result = 7;
        break;
    }
    return result;
}
~~~

A `while (true)` loop where **every exit path through `break` has already assigned the variable** can also satisfy definite assignment:

~~~java
static int fromLoop() {
    int result;
    while (true) {
        result = 7;
        break;
    }
    return result;
}
~~~

In this example, the normal completion path of the loop passes through `result = 7` before hitting `break`. Do not generalize this to every `while(true)` loop, especially when there are multiple `break` branches or exceptions.

## 7. `try/catch`: every path continuing after the block must assign

~~~java
static int parseOrDefault(boolean fail) {
    int result;
    try {
        if (fail) {
            throw new IllegalArgumentException("simulated");
        }
        result = 40;
    } catch (IllegalArgumentException ex) {
        result = -40;
    }
    return result;
}
~~~

If `fail == false`, the `try` branch assigns 40; if `fail == true`, the exception is caught and `catch` assigns -40. Both normal completion paths to `return` have assigned the variable.

**Note:** a `catch` block is not guaranteed to run; you should not assume an assignment **only inside catch** suffices for all paths. `finally` has its own control-flow rules; when code gets complex, reduce branches or initialize the result in a clear place.

## 8. `final` variables: assign exactly once on each execution path

An unassigned `final` local variable can be assigned after declaration, but cannot be **reassigned** once assigned:

~~~java
static int finalResult(boolean flag) {
    final int result;
    if (flag) {
        result = 1;
    } else {
        result = 2;
    }
    return result;
}
~~~

The branches are mutually exclusive, so each execution performs only one assignment. Conversely, the snippet below does not compile:

~~~java
// final int x = 1;
// x = 2; // Error: cannot reassign final.
~~~

The *definite assignment* check ensures a local has been assigned before being read; the *definite unassignment* check for `final` prevents invalid reassignment. The two checks are related but not identical.

## 9. Standalone Java 17+ program

Create the exact file **`DefiniteAssignmentDemo.java`**:

~~~java
public final class DefiniteAssignmentDemo {
    private static int field; // Default value is 0.

    private DefiniteAssignmentDemo() {}

    static int ifElse(boolean flag) {
        int result;
        if (flag) result = 10;
        else result = 20;
        return result;
    }

    static int earlyExit(int input) {
        int value;
        if (input < 0) return -1;
        if (input == 0) {
            throw new IllegalArgumentException("zero not allowed");
        }
        value = input * 2;
        return value;
    }

    static int switchValue(String mode) {
        int result = switch (mode) {
            case "FAST" -> 100;
            case "SLOW" -> 20;
            default -> 0;
        };
        return result;
    }

    static int loopValue() {
        int result;
        while (true) {
            result = 7;
            break;
        }
        return result;
    }

    static int tryCatch(boolean fail) {
        int result;
        try {
            if (fail) {
                throw new IllegalArgumentException("simulated");
            }
            result = 40;
        } catch (IllegalArgumentException ex) {
            result = -40;
        }
        return result;
    }

    static int finalOnce(boolean flag) {
        final int result;
        if (flag) result = 1;
        else result = 2;
        return result;
    }

    public static void main(String[] args) {
        System.out.println("field=" + field);
        System.out.println("if true=" + ifElse(true));
        System.out.println("if false=" + ifElse(false));

        System.out.println("early positive=" + earlyExit(3));
        System.out.println("early negative=" + earlyExit(-3));
        try {
            earlyExit(0);
        } catch (IllegalArgumentException ex) {
            System.out.println("early zero=" + ex.getMessage());
        }

        System.out.println("switch FAST=" + switchValue("FAST"));
        System.out.println("switch SLOW=" + switchValue("SLOW"));
        System.out.println("switch OTHER=" + switchValue("OTHER"));
        System.out.println("loop=" + loopValue());
        System.out.println("try normal=" + tryCatch(false));
        System.out.println("try catch=" + tryCatch(true));
        System.out.println("final true=" + finalOnce(true));
        System.out.println("final false=" + finalOnce(false));
    }
}
~~~

**Requirements:** JDK 17 or later; no external libraries or preview features needed.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 DefiniteAssignmentDemo.java
java -cp . DefiniteAssignmentDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\DefiniteAssignmentDemo.java
java -cp . DefiniteAssignmentDemo
~~~

### Exact expected stdout

~~~text
field=0
if true=10
if false=20
early positive=6
early negative=-1
early zero=zero not allowed
switch FAST=100
switch SLOW=20
switch OTHER=0
loop=7
try normal=40
try catch=-40
final true=1
final false=2
~~~

The output shows that a local variable can be declared and then assigned in branches, a `return`/`throw` branch does not need to assign for subsequent code it cannot reach, and a field defaulting to 0 does not mean a local also equals 0.

## 10. Common errors and exercises

| Mistake | Why is it an error? | Fix |
|---|---|---|
| `int x; println(x);` | Local has not been assigned | Assign before reading |
| Assigning `x` only in `if(flag)` | The false branch is unassigned | Add `else` or a default |
| `if/else if` not covering all branches | A path skips all assignments | Add `else` or change structure |
| `switch statement` missing a covering branch | Some selector value matches no `case` | Add `default` when appropriate |
| Assigning only inside `while` | The loop may execute 0 times | Assign a default or prove the exit path |
| Assigning only inside `catch` | `catch` may not run | Handle the normal `try` path as well |
| Thinking a local automatically gets 0/null like a field | Locals have no default value | Assign explicitly |
| Assigning twice to a `final` variable | Violates the final rule | Ensure once per path |

**Exercise A:** Is `int n; if (flag) n=1; else n=2; System.out.println(n);` valid? **Yes**, because the two branches cover all paths.

**Exercise B:** Is `int n; if (flag) n=1; System.out.println(n);` valid? **No**, because flag can be false.

**Exercise C:** Is `int n; if (flag) return; n=3; System.out.println(n);` inside a `void` method valid? **Yes**, because every path reaching `println` has assigned `n=3`.

**Exercise D:** Can an object's `private int count;` be read before explicit assignment? **Yes**, the default value of an `int` field is 0.

**Exercise E:** If `final int result;` is assigned in both mutually exclusive branches, is that allowed? **Yes**, provided the variable is definitely assigned before reading and not reassigned on the same execution path.

## 11. Checklist and conclusion

- [ ] Distinguish **variable name scope** from **definite assignment**.
- [ ] Know that locals have no default value, unlike fields and array elements.
- [ ] Check all `if/else` paths that can reach a read.
- [ ] Know that `return` or `throw` can terminate an unassigned branch.
- [ ] Understand how `switch statement` and `switch expression` differ.
- [ ] Do not assume a loop body or `catch` block always executes.
- [ ] With `final`, ensure both assignment before reading and no reassignment.
- [ ] Run `DefiniteAssignmentDemo.java` with JDK 17+, comparing against exact stdout.

**Conclusion:** Java 17 requires a local variable to be **definitely assigned on every execution path that can lead to a read**. To keep code clear and safe, cover all branches, use guard clauses where appropriate, and distinguish *definite assignment* from variable scope as well as field default values.
