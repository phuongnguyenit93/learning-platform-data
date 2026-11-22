# `final` Can Be Assigned in Mutually Exclusive Branches — Java 17+

> **Java core — language-basics / Scope and Initialization**  
> **Requirements:** JDK 17+; single-file example, run with `javac` and `java`.  
> **Objective:** Understand why an uninitialized `final` variable can be assigned **once per execution path**, such as in two `if/else` branches; distinguish *definite assignment* from *definite unassignment*, avoid missing assignments or double assignments, and apply this to `final` fields in constructors.

## 1. `final` restricts reassignment, not immediate assignment

For a *local variable*, there are two ways to declare `final`:

~~~java
final int fixed = 10; // Has a value immediately at declaration.

// Inside a method:
final int selected;   // Blank final: no initializer yet.
if (true) {
    selected = 20;    // First assignment.
}
System.out.println(selected); // 20.
~~~

A *blank final* is a `final` variable declared **without an initializer**. It can receive a value later, provided the assignment obeys Java's control-flow checking rules.

- `final` does not mean "each branch is allowed to assign once and combine them"; during **each execution**, a `final` variable may only receive a value in cases where the language can prove it was **not yet assigned** prior to that assignment.
- To **read** a local variable, the compiler must determine that it is **definitely assigned** (DA) on every path leading to the read location.
- To **assign** to a `final` variable without an initializer, the compiler must determine that it is **definitely unassigned** (DU) immediately before the assignment.

DA and DU checks are performed at **compile time**, based on program structure, without waiting until runtime to see which branch executes.

## 2. Two mutually exclusive `if/else` branches: standard style

~~~java
static int select(boolean flag) {
    final int result;

    if (flag) {
        result = 11;
    } else {
        result = 22;
    }

    return result;
}
~~~

The two branches of an `if/else` statement **do not execute simultaneously in the same call**. Upon reaching `return result`, regardless of whether `flag` is `true` or `false`, **exactly one branch** has assigned `result`. Therefore:

~~~java
System.out.println(select(true));  // 11
System.out.println(select(false)); // 22
~~~

**Path analysis:**

| `flag` value | Executed branch | Value assigned to `result` | Assigned before `return`? |
| --- | --- | --- | --- |
| `true` | `if` | `11` | Yes |
| `false` | `else` | `22` | Yes |

The key point is not that the variable `result` appears in **two assignment statements in source code**, but that **no valid execution path passes through both of those assignments**. Java verifies mutual exclusion via the `if/else` structure.

An equivalent, shorter way when each branch simply selects one value:

~~~java
final int result = flag ? 11 : 22;
~~~

The conditional operator `?:` returns a chosen value to initialize `result` exactly once; use it when the expression is simple enough to read.

## 3. Missing an assignment branch: *might not have been initialized* error

The following snippet **does not compile** if uncommented:

~~~java
// DOES NOT COMPILE:
// static int missing(boolean flag) {
//     final int result;
//     if (flag) {
//         result = 11;
//     }
//     return result; // flag=false: result has never been assigned.
// }
~~~

A branch may choose not to assign anything, but **you cannot read the variable when a path reaches the read location without assigning it**. If a value is needed in both cases, use `else`:

~~~java
static int withElse(boolean flag) {
    final int result;
    if (flag) {
        result = 11;
    } else {
        result = 0;
    }
    return result;
}
~~~

Or structure control flow so that the unassigned path **terminates before the read**:

~~~java
static int withEarlyReturn(boolean enabled) {
    final int code;
    if (!enabled) {
        return -1; // This path never reaches return code.
    }
    code = 42;
    return code;
}
~~~

With `enabled == false`, the method returns `-1` immediately, so `code` is never read. With `enabled == true`, `code` is assigned `42` before returning. The compiler can prove `code` is assigned on every path that actually reaches `return code`.

Similarly, a branch can `throw` instead of assigning if it **does not continue** to where the variable is used. Having a `return` or `throw` branch does not grant extra permission to assign a `final` variable multiple times.

## 4. Second assignment: still an error even with the same value

A `final` variable that already has a value cannot be reassigned:

~~~java
// DOES NOT COMPILE:
// final int limit = 10;
// limit = 10; // Error: reassigning even though the value does not change.
~~~

The same happens when assigning through one of two branches and then assigning again afterward:

~~~java
// DOES NOT COMPILE:
// static int assignedTwice(boolean flag) {
//     final int result;
//     if (flag) {
//         result = 1;
//     } else {
//         result = 2;
//     }
//     result = 3; // Error: result is definitely already assigned.
//     return result;
// }
~~~

Do not write two independent `if` statements to replace an `if/else` when choosing a single value. The compiler checks DA/DU using specific control-flow rules; it is **not an arbitrary theorem prover for logical relationships** between conditions. The `if/else` structure communicates the "exactly one branch" intent clearly and is easier to verify.

For a `final` variable, `++`, `--`, and compound assignments like `+=` are also reassignment operations and cannot be used after the variable has been initialized. `final` protects **the value held in the variable**; it does not by itself guarantee that a computed result or object is immutable.

## 5. Multiple `else if` branches and `switch`

When there are three or more choices, all paths reaching the read must be covered:

~~~java
static String classify(int number) {
    final String category;

    if (number < 0) {
        category = "NEG";
    } else if (number == 0) {
        category = "ZERO";
    } else {
        category = "POS";
    }

    return category;
}
~~~

Branches in the same `if/else if/else` chain are mutually exclusive. The `else` branch ensures that when neither of the previous two conditions holds, the variable is still initialized.

In Java 17, `switch` with **arrow cases** (`->`) prevents *fall-through* bugs into the next case:

~~~java
static String fromSwitch(int code) {
    final String label;

    switch (code) {
        case 0 -> label = "ZERO";
        case 1 -> label = "ONE";
        default -> label = "OTHER";
    }

    return label;
}
~~~

Here each `switch` branch executes only one assignment and `default` covers the remaining values. If you remove `default` from this example, a path exists where `label` is unassigned when `code` is not 0 or 1.

Another concise approach is a **switch expression** returning the initialization value directly:

~~~java
static String fromExpression(int code) {
    final String label = switch (code) {
        case 0 -> "ZERO";
        case 1 -> "ONE";
        default -> "OTHER";
    };
    return label;
}
~~~

In a `switch expression`, all branches of the expression must satisfy the rules for producing a result or completing normally. Both `fromSwitch` and `fromExpression` yield `"ZERO"` for `code=0`, `"ONE"` for `code=1`, and `"OTHER"` for other values.

## 6. `final` fields without an initializer in constructors

The same rule is also very important for a **blank final instance field**:

~~~java
class Plan {
    private final String tier;
    private final int quota;

    Plan(boolean premium) {
        if (premium) {
            tier = "PREMIUM";
            quota = 100;
        } else {
            tier = "BASIC";
            quota = 10;
        }
    }

    String summary() {
        return tier + ":" + quota;
    }
}
~~~

Each `Plan` object has its own `tier` and `quota` fields; the constructor assigns each field exactly once on every normal completion path. You can create two objects with different final values:

~~~java
Plan first = new Plan(true);
Plan second = new Plan(false);
// first.summary()  -> "PREMIUM:100"
// second.summary() -> "BASIC:10"
~~~

Points to distinguish:

- **Blank final local variable:** to **read** it, DA must hold; even if unread, DU rules must still be obeyed when assigning.
- **Blank final instance field:** must be initialized according to Java rules before the constructor completes normally; if there are multiple constructors, all corresponding initialization paths must be valid.
- **Blank static final field:** initialized within a valid static initialization scope of the class, not per object creation.
- You cannot grant extra permission to assign a `final` field after initialization by using a regular setter.

`final` on a field does not mean every object with that field is a "compile-time constant". Only cases satisfying *constant variable* rules (for example, certain primitive/`String` fields initialized with constant expressions) have that property.

## 7. `final` references: forbids changing the reference, not modifying an array

Case where branches select one of two **arrays**:

~~~java
static int[] chooseArray(boolean shortArray) {
    final int[] values;

    if (shortArray) {
        values = new int[] {1, 2};
    } else {
        values = new int[] {3, 4, 5};
    }

    values[0] = 9; // VALID: modifies array contents.
    return values;
}
~~~

After either branch, `values` holds a single reference assigned exactly once. `values[0] = 9` **does not reassign the reference variable**; it modifies an element of the array object:

~~~java
// DOES NOT COMPILE if placed after the if/else:
// values = new int[] {8}; // Reassigning an already initialized final variable.
~~~

Similarly, a `final StringBuilder` can still call `append(...)` to mutate the object's state, whereas `builder = new StringBuilder()` is forbidden after initial assignment. Therefore, **`final` does not mean the object is *immutable***.

With each method call, new local variables are created for that call context. If you declare `final` inside a loop body and initialize it properly, each iteration also has its own local variable within its scope; you must not infer that a single `final` variable declared **outside the loop** can continuously receive new values.

## 8. Standalone Java 17+ example

Create the file **FinalExclusiveBranchesDemo.java**:

~~~java
import java.util.Arrays;

public final class FinalExclusiveBranchesDemo {
    private final String tier;
    private final int quota;

    public FinalExclusiveBranchesDemo(boolean premium) {
        if (premium) {
            tier = "PREMIUM";
            quota = 100;
        } else {
            tier = "BASIC";
            quota = 10;
        }
    }

    public String summary() {
        return tier + ":" + quota;
    }

    private static int select(boolean flag) {
        final int result;
        if (flag) {
            result = 11;
        } else {
            result = 22;
        }
        return result;
    }

    private static int withEarlyReturn(boolean enabled) {
        final int code;
        if (!enabled) {
            return -1;
        }
        code = 42;
        return code;
    }

    private static String classify(int number) {
        final String category;
        if (number < 0) {
            category = "NEG";
        } else if (number == 0) {
            category = "ZERO";
        } else {
            category = "POS";
        }
        return category;
    }

    private static String fromSwitch(int code) {
        final String label;
        switch (code) {
            case 0 -> label = "ZERO";
            case 1 -> label = "ONE";
            default -> label = "OTHER";
        }
        return label;
    }

    private static String fromExpression(int code) {
        final String label = switch (code) {
            case 0 -> "ZERO";
            case 1 -> "ONE";
            default -> "OTHER";
        };
        return label;
    }

    private static int throwOrAssign(boolean valid) {
        final int value;
        if (!valid) {
            throw new IllegalArgumentException("invalid");
        }
        value = 7;
        return value;
    }

    private static int[] chooseArray(boolean shortArray) {
        final int[] values;
        if (shortArray) {
            values = new int[] {1, 2};
        } else {
            values = new int[] {3, 4, 5};
        }
        values[0] = 9;
        return values;
    }

    private static int loopSum() {
        int sum = 0;
        for (int i = 0; i < 3; i++) {
            final int increment;
            if (i % 2 == 0) {
                increment = i * 10;
            } else {
                increment = i;
            }
            sum += increment;
        }
        return sum;
    }

    public static void main(String[] args) {
        System.out.println("trueBranch=" + select(true));
        System.out.println("falseBranch=" + select(false));
        System.out.println("guardOff=" + withEarlyReturn(false));
        System.out.println("guardOn=" + withEarlyReturn(true));

        System.out.println("negative=" + classify(-2));
        System.out.println("zero=" + classify(0));
        System.out.println("positive=" + classify(5));
        System.out.println("switchZero=" + fromSwitch(0));
        System.out.println("switchOne=" + fromSwitch(1));
        System.out.println("switchOther=" + fromSwitch(8));
        System.out.println("expression=" + fromExpression(1));

        FinalExclusiveBranchesDemo premium =
                new FinalExclusiveBranchesDemo(true);
        FinalExclusiveBranchesDemo basic =
                new FinalExclusiveBranchesDemo(false);
        System.out.println("premium=" + premium.summary());
        System.out.println("basic=" + basic.summary());

        System.out.println("shortArray=" + Arrays.toString(chooseArray(true)));
        System.out.println("longArray=" + Arrays.toString(chooseArray(false)));
        System.out.println("loopSum=" + loopSum());

        System.out.println("throwValid=" + throwOrAssign(true));
        try {
            System.out.println("throwInvalid=" + throwOrAssign(false));
        } catch (IllegalArgumentException ex) {
            System.out.println("throwInvalid=IllegalArgumentException");
        }
    }
}
~~~

Compile and run in the directory containing the file in Bash, PowerShell, or Command Prompt:

~~~bash
javac -encoding UTF-8 FinalExclusiveBranchesDemo.java
java FinalExclusiveBranchesDemo
~~~

**Exact expected stdout:**

~~~text
trueBranch=11
falseBranch=22
guardOff=-1
guardOn=42
negative=NEG
zero=ZERO
positive=POS
switchZero=ZERO
switchOne=ONE
switchOther=OTHER
expression=ONE
premium=PREMIUM:100
basic=BASIC:10
shortArray=[9, 2]
longArray=[9, 4, 5]
loopSum=21
throwValid=7
throwInvalid=IllegalArgumentException
~~~

`trueBranch` and `falseBranch` demonstrate that two branches can assign to the same blank final; `guardOff` demonstrates that an early-terminating branch does not need to assign a value to proceed; `switchZero/One/Other` demonstrate mutually exclusive cases. The constructor's two `final` fields are assigned in each branch; `shortArray` and `longArray` show that `final` does not forbid modifying array elements.

## 9. Common errors and exercises

| Misconception / issue | How to check or fix |
| --- | --- |
| A `final` variable must be assigned at its declaration site | Not required for a *blank final*; it can validly be assigned in branches |
| Two assignments appearing in `if/else` count as assigning twice | False if each execution path runs only one branch |
| Only `if(flag) value=1;` then using `value` | Missing assignment when `flag=false`, fails DA |
| Already assigned in `if/else` and then `value=3` | Second assignment, violating `final` rules |
| Omitting `default` in `switch` and still reading the variable | An unassigned path may remain |
| `final int[] values` prevents modifying `values[0]` | False; forbids reassigning the reference, not mutating the array |
| A blank `final` field can be left unassigned when the constructor ends | No; must be validly initialized on every normal completion path |
| Multiple independent `if` statements are always analyzed like one `if/else` | Do not assume this; use an explicit branching structure |
| `final` makes an object completely immutable | No; object immutability also depends on the type's design |

**Exercise 1.** Write `static int pick(boolean flag)` with `final int n;`, assigning `5` in the `if` branch and `8` in the `else` branch. Predict the result for both values of `flag`.

**Exercise 2.** Remove the `else` branch from Exercise 1 while keeping `return n;`. Explain the DA error; fix it via early return or covering all branches.

**Exercise 3.** After a valid `if/else`, add `n = 100;`. Explain why the statement is rejected regardless of whether the assigned value is the same as the old value or different.

**Exercise 4.** Declare a class with field `private final String category;` and a constructor taking a number. In `if/else if/else`, assign appropriate labels; verify all constructor exit paths.

**Exercise 5.** Replace `if/else` with a `switch` having `default` or a `switch expression` on Java 17. Compare branch coverage and clarity.

**Exercise 6.** Use `final int[] selected;`, pick one of two arrays based on a `boolean`, then modify `selected[0]`. Why is modifying an element valid while `selected = new int[2]` is not?

### Key Takeaway

**A blank `final` can appear in multiple assignments across mutually exclusive branches**, provided the compiler can prove it is **definitely unassigned before each assignment** and **definitely assigned before every read**. Exhaustive `if/else` and `switch` constructs express this rule most clearly; `return`/`throw` can terminate a path early. `final` forbids changing a variable's value after initialization, but does not by itself make the referenced object immutable.
