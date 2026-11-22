# Identifying Unreachable Statements and Their Impact on Compilation — Java 17+

## 1. What Is an `Unreachable statement`?

Java checks the **reachability** of statements at compile time. If the language rules prove that no valid control path can lead to a statement, `javac` reports an **`unreachable statement`** error and fails to produce a valid program.

Incorrect example:

~~~java
static int answer() {
    return 42;
    // System.out.println("after return");
    // If the line above is uncommented: unreachable statement error.
}
~~~

After `return 42;`, the method has already finished. The statement immediately after it in the same block has no chance of being executed.

**Distinguish two situations:**

- **Unreachable according to compiler rules:** a *compile-time* error, such as a statement placed directly after an unconditional `return`.
- **Syntactically reachable, yet practically never executed for the given data:** usually **not a compile error**, such as an `if (false)` branch or a data-dependent condition that always evaluates to false in the problem domain.

Do not rely merely on observing "I ran it and never saw this line printed" to conclude the compiler will report unreachable.

## 2. Quick Identification Table

| Code Pattern | Is the Following Statement Reachable? | Result |
|---|---|---|
| `return; statement;` same block | No | **Compile error** |
| `throw ex; statement;` same block | No | **Compile error** |
| `break; statement;` in same loop branch | No | **Compile error** |
| `continue; statement;` in same loop branch | No | **Compile error** |
| `while (true) { ... }` with no `break` exit path | No, for statements following the loop | **Compile error** |
| `for (;;) { ... }` with no `break` exit | No, for statements following the loop | **Compile error** |
| `while (false) { statement; }` | Body is unreachable | **Compile error** |
| `if (false) { statement; }` | `if` rules permit this form | **Valid**, branch does not run |
| `if (flag) return; statement;` | Has path `flag == false` | **Valid** |
| `while (true) { if (stop) break; }` then a statement | Has `break` exit path | **Can be valid** |
| `do { statement; } while (false);` | Body runs one iteration | **Valid** |

The abbreviated pattern rows are not standalone runnable programs; the end of the lesson provides a standalone Java 17+ program with exact stdout.

## 3. After `return`: No Remaining Path in the Method

~~~java
static String getLabel() {
    return "READY";
    // System.out.println("unreachable"); // Must not enable this line.
}
~~~

`return` terminates the method immediately; any statement placed directly afterward in the same block is unreachable.

**Conditional `return`, however, is different:**

~~~java
static String status(boolean active) {
    if (active) {
        return "ACTIVE";
    }
    return "INACTIVE"; // Valid when active == false.
}
~~~

`status(true)` returns `"ACTIVE"`, `status(false)` returns `"INACTIVE"`; the final `return` statement still has a path to reach it.

**If both branches terminate the method:**

~~~java
// Example that fails to compile if the last line is enabled:
static int choose(boolean flag) {
    if (flag) {
        return 1;
    } else {
        return 2;
    }
    // System.out.println("after if/else"); // Unreachable.
}
~~~

When analyzing, examine **all paths** across branches, not just the branch taken in one specific call.

## 4. After `throw`: Normal Flow Does Not Continue

~~~java
static int requirePositive(int n) {
    if (n <= 0) {
        throw new IllegalArgumentException("n must be positive");
        // System.out.println("never"); // Unreachable.
    }
    return n;
}
~~~

A `throw` ends the normal control path at that point. The exception can be **caught in the caller or an appropriate enclosing `catch`**, but Java does not return to execute the statement directly after `throw` in the same block.

An invalid example if written sequentially:

~~~java
// throw new IllegalStateException("fail");
// System.out.println("after throw"); // Unreachable.
~~~

Do not confuse unreachable errors with messages about **checked exceptions**: that is a separate check involving exception declaration and handling.

## 5. After `break` and `continue` in the Same Block

`break` exits the corresponding loop or `switch`; `continue` moves to the next iteration of the loop.

~~~java
for (int i = 0; i < 3; i++) {
    if (i == 1) {
        continue;
        // System.out.println("after continue"); // Unreachable.
    }
    System.out.println("i=" + i);
}
~~~

**Exact stdout:**

~~~text
i=0
i=2
~~~

With `break`:

~~~java
for (int i = 0; i < 3; i++) {
    if (i == 1) {
        break;
        // System.out.println("after break"); // Unreachable.
    }
    System.out.println("visit=" + i);
}
System.out.println("loop finished");
~~~

**Exact stdout:**

~~~text
visit=0
loop finished
~~~

Important: it is **the statement directly after `break`/`continue` in the same branch** that causes an error. A statement **after the entire loop** is not necessarily unreachable: with `break`, execution can reach it.

## 6. Infinite Loops and Normal Completion

A `while (true)` or `for (;;)` loop without a `break` path to leave the loop **cannot complete normally** under Java's reachability checks.

~~~java
// static void bad() {
//     while (true) {
//         System.out.println("repeat");
//     }
//     System.out.println("after loop"); // Unreachable statement error.
// }
~~~

The print line after the loop cannot be reached via normal execution. If the intent is an infinite loop with an exit condition, provide a valid `break` path:

~~~java
static int countTo(int limit) {
    int count = 0;
    while (true) {
        if (count >= limit) {
            break;
        }
        count++;
    }
    return count; // Valid: there is a break path out of while.
}
~~~

If `limit=3`, `countTo` returns 3.

**Note:** Only a **syntactically reachable** `break` targeting the right loop counts toward normal completion rules. A `break` placed inside a **different** loop or inside a `switch` does not automatically prove the outer `while(true)` loop can terminate.

An infinite loop is valid if there is no subsequent statement that needs to be reached; the error lies in the unreachable code per compiler rules, not in `while(true)` itself.

## 7. Important Exception: `if (false)` Differs from `while (false)`

Java intentionally allows the body of an `if` even when the condition is a **constant expression `false`**. This supports compile-time configuration toggles:

~~~java
if (false) {
    System.out.println("disabled");
}
System.out.println("after disabled branch");
~~~

**Exact stdout:**

~~~text
after disabled branch
~~~

By contrast, the body of a `while` with a constant `false` condition is considered unreachable:

~~~java
// DOES NOT COMPILE if this snippet is enabled:
// while (false) {
//     System.out.println("unreachable body");
// }
~~~

A basic `for` with a constant `false` condition has a similar issue:

~~~java
// DOES NOT COMPILE:
// for (int i = 0; false; i++) {
//     System.out.println(i);
// }
~~~

**With `do-while`:**

~~~java
int count = 0;
do {
    count++;
} while (false);
System.out.println("count=" + count);
~~~

**Exact stdout:**

~~~text
count=1
~~~

Because `do-while` executes its body **before the first condition check**, the body remains reachable even when the condition is `false`.

**Attention:** `final boolean OFF = false;` is a constant variable; `while (OFF)` is also analyzed as a constant false condition. A boolean variable read at runtime (not a constant expression) is generally not inferred this way simply because it currently holds `false`.

## 8. Compile-Time Reachability Is Not a Solver for Every Logic Condition

For example:

~~~java
static void check(int value) {
    if (value > 100 && value < 0) {
        System.out.println("impossible for int");
    }
    System.out.println("checked=" + value);
}
~~~

The condition inside `if` cannot be true for any single `int` value, yet the Java 17 compiler **is not required to prove every mathematical contradiction** to forbid the branch body. Therefore, this code **compiles validly**, even though `"impossible for int"` will never appear.

Conversely, an unreachable error after `return` is determined from explicit control structure, without analyzing actual runtime data.

For example, `if (flag) return;` still has a path where `flag == false`. Java does not forbid the following statement simply because in one run you always pass `true`.

**Practical rule:** the difference between "unreachable **according to the reachability specification**" and "impossible **according to business requirements**" must be verified separately.

## 9. `finally` Can Run During Control Transfers

With `try/finally`, statements in `finally` generally still execute when `try` runs `return`, `break`, or `continue`:

~~~java
static int readValue() {
    try {
        System.out.println("inside try");
        return 5;
    } finally {
        System.out.println("inside finally");
    }
}
~~~

**Exact stdout when calling `System.out.println("result=" + readValue());`:**

~~~text
inside try
inside finally
result=5
~~~

Therefore, you must not infer that "any code running after a `return` expression is evaluated is unreachable": `finally` belongs to the `try`'s completion flow and has special rules.

Avoid placing a new `return` or `throw` arbitrarily inside `finally` because it can **alter the result or mask the original exception**.

## 10. Distinguishing Unreachable from Other Compile-Time Errors

| Issue | Example | Diagnosis / Nature |
|---|---|---|
| Unreachable statement | `return 1; println();` | `unreachable statement` |
| Variable not definitely assigned | `int x; if (flag) x=1; println(x);` | `variable x might not have been initialized` |
| Missing return path | Method returning `int` has a path completing without `return` | `missing return statement` |
| Non-boolean condition | `if (1) { ... }` | Type error, not reachability |
| Invalid `break` target label | `break unknown;` | Label resolution error |
| Branch always false by business logic | `if (n>100 && n<0)` | Still compiles, yet logic needs fixing |

These errors can appear together in a project, yet **should not be fixed with the same trick**. Reachability errors are usually resolved by reordering statements or fixing exit paths; definite assignment errors require ensuring a variable has a value on every path where it is used.

## 11. Refactoring Patterns When Encountering Unreachable Statements

**Wrong — logging after `return`:**

~~~java
// static int compute(int x) {
//     return x * 2;
//     System.out.println("finished"); // Unreachable.
// }
~~~

**Right — logging before `return`:**

~~~java
static int compute(int x) {
    int result = x * 2;
    System.out.println("finished");
    return result;
}
~~~

**Wrong — statement after `continue` in the same block:**

~~~java
// if (skip) {
//     continue;
//     total++; // Unreachable.
// }
~~~

**Right — placing processing in the non-skip branch:**

~~~java
for (int i = 0; i < 4; i++) {
    if (i % 2 == 0) {
        continue;
    }
    System.out.println("process " + i);
}
~~~

**Exact stdout:**

~~~text
process 1
process 3
~~~

If an update step truly needs to run on both branches, determine whether it belongs in the loop body, the `for` update clause, or `finally` according to your goal. **Do not delete a line just to silence the compiler** when it holds an important business side effect; move it to the right path.

## 12. Standalone Java 17+ Program

Save with the exact name **`ReachabilityDemo.java`**:

~~~java
public final class ReachabilityDemo {
    private ReachabilityDemo() {}

    static String branch(boolean active) {
        if (active) {
            return "ACTIVE";
        }
        return "INACTIVE";
    }

    static int firstPositive(int[] data) {
        for (int i = 0; i < data.length; i++) {
            if (data[i] > 0) {
                return i;
            }
        }
        return -1;
    }

    static int countTo(int limit) {
        int count = 0;
        while (true) {
            if (count >= limit) {
                break;
            }
            count++;
        }
        return count;
    }

    static int requirePositive(int n) {
        if (n <= 0) {
            throw new IllegalArgumentException("n must be positive");
        }
        return n;
    }

    static void testContinue() {
        for (int i = 0; i < 3; i++) {
            if (i == 1) {
                continue;
            }
            System.out.println("continue:visit=" + i);
        }
    }

    static void testBreak() {
        for (int i = 0; i < 3; i++) {
            if (i == 1) {
                break;
            }
            System.out.println("break:visit=" + i);
        }
        System.out.println("break:after loop");
    }

    static void constantIf() {
        if (false) {
            System.out.println("disabled");
        }
        System.out.println("after if(false)");
    }

    static void doOnce() {
        int count = 0;
        do {
            count++;
        } while (false);
        System.out.println("do-while count=" + count);
    }

    static void check(int value) {
        if (value > 100 && value < 0) {
            System.out.println("impossible for int");
        }
        System.out.println("checked=" + value);
    }

    static int withFinally() {
        try {
            System.out.println("inside try");
            return 5;
        } finally {
            System.out.println("inside finally");
        }
    }

    public static void main(String[] args) {
        System.out.println("branch true=" + branch(true));
        System.out.println("branch false=" + branch(false));
        System.out.println("first positive=" + firstPositive(new int[]{-2, 0, 7, 9}));
        System.out.println("first missing=" + firstPositive(new int[]{-2, 0}));
        System.out.println("countTo 3=" + countTo(3));

        try {
            requirePositive(0);
        } catch (IllegalArgumentException ex) {
            System.out.println("throw caught=" + ex.getMessage());
        }
        System.out.println("require 4=" + requirePositive(4));

        testContinue();
        testBreak();
        constantIf();
        doOnce();
        check(5);
        System.out.println("finally result=" + withFinally());
    }
}
~~~

**Requirements:** JDK 17 or higher, open a terminal in the directory containing the file. The program uses only standard JDK APIs; no preview features, Maven, or Gradle.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 ReachabilityDemo.java
java -cp . ReachabilityDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\ReachabilityDemo.java
java -cp . ReachabilityDemo
~~~

### Exact expected stdout

~~~text
branch true=ACTIVE
branch false=INACTIVE
first positive=2
first missing=-1
countTo 3=3
throw caught=n must be positive
require 4=4
continue:visit=0
continue:visit=2
break:visit=0
break:after loop
after if(false)
do-while count=1
checked=5
inside try
inside finally
finally result=5
~~~

**Reading the output:**

1. The two branches of `branch` show that a conditional `return` does not make lines after `if` unreachable.
2. `firstPositive` has an early `return` when found and a `return -1` path after scanning to the end.
3. `countTo` has a `while(true)` loop yet completes normally thanks to `break`.
4. `requirePositive` throws an exception on the error path and returns a result on the valid path.
5. `continue` skips `i=1`, `break` stops at `i=1` and still prints the line after the loop.
6. `if(false)` does not execute the branch yet the program still compiles; `do-while(false)` runs one iteration.
7. The condition `value > 100 && value < 0` cannot be true for `int`, yet the compiler does not necessarily forbid the branch; only `checked=5` appears.
8. `finally` is executed before the caller prints the returned result.

## 13. Exercises and Answers

### Exercise A — which statement is unreachable?

~~~java
static int f() {
    return 10;
    // System.out.println("X"); // If uncommented?
}
~~~

**Answer:** `System.out.println("X")` is an **unreachable statement**, causing a compile error. To log, place it **before** `return`.

### Exercise B — `if(false)` or `while(false)`?

~~~java
if (false) {
    System.out.println("A");
}
// while (false) {
//     System.out.println("B");
// }
System.out.println("C");
~~~

**Answer:** the enabled example compiles and prints `C`. If `while(false)` is uncommented, the Java 17 compiler reports unreachable on the **body of while**.

### Exercise C — with `break`, is the statement after the loop reachable?

~~~java
int count = 0;
while (true) {
    if (count == 2) break;
    count++;
}
System.out.println(count);
~~~

**Answer:** reachable because there is a `break` path; stdout `2`.

### Exercise D — `continue` inside a branch

~~~java
for (int i = 0; i < 3; i++) {
    if (i == 1) {
        continue;
        // System.out.println("X");
    }
}
~~~

**Answer:** if the line printing `X` is enabled, it is unreachable; move the desired processing **before** `continue` or to the appropriate branch.

### Exercise E — is an uninitialized variable error reachability?

~~~java
// static void f(boolean flag) {
//     int x;
//     if (flag) x = 1;
//     System.out.println(x);
// }
~~~

**Answer:** no. The `println` statement is still reachable, yet `x` is not guaranteed to be assigned on the `flag == false` path. This is a **definite assignment** error, not a reachability error.

## 14. Checklist and Conclusion

- [ ] Distinguish **statements unreachable per the compiler** from code not run due to actual data.
- [ ] Recognize statements placed directly after an unconditional `return` or `throw`.
- [ ] Recognize statements placed directly after `break`/`continue` in the same branch.
- [ ] Know that `while(true)`/`for(;;)` without a `break` path makes following code unreachable.
- [ ] Understand that a valid `break` path allows code after the loop to be reachable.
- [ ] Remember Java allows `if(false)` validly, whereas `while(false)` has an invalid body.
- [ ] Understand `do ... while(false)` still executes its body for one iteration.
- [ ] Do not confuse logical contradictions in `if` with unreachable errors detected by the compiler.
- [ ] Know that `finally` can execute during `return` or other control transfers.
- [ ] Distinguish unreachable from `missing return` and `variable might not have been initialized`.
- [ ] When fixing code, preserve business meaning and side-effect paths.
- [ ] Run `ReachabilityDemo.java` with Java 17+ `javac`/`java`, verifying exact stdout.

**Conclusion:** Java 17 checks reachability using **static control-flow rules**, not by testing every possible input. Placing code directly after an unconditional control transfer generally causes a **compile error**, whereas a branch unexecuted at runtime can still be valid (especially `if(false)`). Analyzing each `return`, `throw`, `break`, `continue` path and loop termination mechanism helps fix errors **with the right control flow**, rather than just deleting compiler messages.