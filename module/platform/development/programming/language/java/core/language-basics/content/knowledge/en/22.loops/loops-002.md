# `do-while` executes the body at least once in Java

> **Java core — language-basics / Loops**  
> **Environment:** JDK 17+, a single standalone Java file, no external libraries needed.  
> **Goal:** Understand why `do-while` checks the condition **after** the body, choose correctly between `while` and `do-while`, use the loop to retry operations, and avoid mistakes related to `;`, `break`, and `continue`.

## 1. Syntax and execution order

~~~java
do {
    // Work to be performed.
} while (condition);
~~~

**Order when execution reaches the loop:**

1. Execute the `do { ... }` body **before checking the condition for the first time**.
2. After the body completes normally, evaluate `condition`, which must have type `boolean` or an unboxable `Boolean`.
3. If the condition is `true`, go back and execute the body again; if `false`, exit the loop and run the next statement.

Once execution reaches `do`, the body **starts at least once**, even if the condition will be false on the very first check. That does not mean every statement in the body is guaranteed to finish: `break`, `return`, an exception, or an interrupted flow can end it early.

~~~java
int count = 0;

do {
    count++;
    System.out.println("count=" + count);
} while (count < 3);

// Prints count=1, count=2, count=3.
~~~

The **`;` after `while (condition)` is mandatory** in `do-while` syntax. This is an easily forgotten difference compared to a regular `while (condition) { ... }`.

## 2. Comparing `while` and `do-while` when the condition is initially false

~~~java
int a = 0;
while (a < 0) {
    a++;
}

int b = 0;
do {
    b++;
} while (b < 0);

System.out.println(a); // 0
System.out.println(b); // 1
~~~

| Criterion | `while` | `do-while` |
| --- | --- | --- |
| First condition check | **Before** the body | **After** the body |
| Initially false condition | Body runs **0 times** | Body runs **1 time** |
| Suitable for | Work that is only allowed to run if the condition is currently true | Work that must try/run once before deciding whether to repeat |
| `;` at the end of the construct | Not placed after `while { ... }` block | **Must be present** after `while (condition)` |

Do not choose `do-while` merely for short syntax. Ask: **does the first operation need to happen before knowing whether to repeat?** If you need to check a condition before allowing an operation, `while` or `for` is usually more appropriate.

## 3. Execution trace table for a concrete loop

Suppose `n = 0` and the condition is `n < 3`:

| Body pass | `n` before body | `n` after `n++` | Check `n < 3` | Continue? |
| ---: | ---: | ---: | --- | --- |
| 1 | 0 | 1 | true | Yes |
| 2 | 1 | 2 | true | Yes |
| 3 | 2 | 3 | false | No |

This table helps check for off-by-one errors (*off-by-one*). In `do-while`, the condition is evaluated **after** `n` has been incremented, so the program prints three passes, not four.

A simple case where you only want to execute exactly once:

~~~java
int executions = 0;
do {
    executions++;
} while (false);
// executions == 1.
~~~

This syntax is valid, but if something **always runs only once**, a regular statement block is usually easier to read; there is no need to force a one-time task into a loop.

## 4. Usage example: retrying until input is valid

For an input-reading program, it may be necessary to **read the first attempt**, validate the result, and prompt again when invalid. The example below uses a simulated input array so it can run from the CLI without manual typing:

~~~java
int[] candidates = {-2, 0, 7};
int index = 0;
int selected;

do {
    selected = candidates[index++];
    System.out.println("candidate=" + selected);
} while (selected <= 0 && index < candidates.length);

System.out.println("selected=" + selected);
~~~

The output is `candidate=-2`, `candidate=0`, `candidate=7`, and `selected=7`.

**Safety note:** The example has at least one element. If the array could be empty, you must check its length **before entering `do`** because the body still attempts to access the array once. The condition `index < candidates.length` prevents further iterations beyond the bound, but **does not protect the first access**.

Additionally, if the test data runs out without any valid element, the loop also ends because the data is exhausted; real applications must distinguish between **running out of attempts** and **having a valid result**, for example by checking `selected > 0` after the loop.

## 5. `break` and `continue` in `do-while`

- `break;` immediately terminates the innermost loop; the condition at the end of the loop is **not** evaluated for the iteration interrupted by `break`.
- `continue;` skips the remaining body of the current iteration and jumps to **evaluating the `while (...)` condition** before deciding whether to enter a new iteration.
- `return` terminates the method, which can simultaneously exit the loop; an unhandled exception can also interrupt flow.

Example with `break`:

~~~java
int tries = 0;
do {
    tries++;
    if (tries == 2) {
        System.out.println("breakAt=" + tries);
        break;
    }
} while (tries < 4);
// Prints: breakAt=2; tries == 2.
~~~

Example with `continue`:

~~~java
int i = 0;
do {
    i++;                         // Always update i before continue.
    if (i % 2 == 0) {
        continue;
    }
    System.out.println("odd=" + i);
} while (i < 4);
// Prints odd=1, odd=3; i == 4.
~~~

On the `i == 2` pass, `continue` does not jump straight back to the top of the body: Java **checks `i < 4`** first. If you forget to update the control variable before `continue`, the loop may never terminate.

## 6. Common mistakes

| Mistake | Why it is dangerous | Fix |
| --- | --- | --- |
| Forgetting `;` after `while (condition)` | Invalid `do-while` syntax | Write `} while (condition);` |
| Thinking the condition is checked before the body | May run once unintentionally | Use `while` if pre-checking is required |
| Condition never becomes false | Infinite loop, wastes resources | Update state and define a stopping point |
| `continue` before the update operation | Can get stuck on the same state | Update before `continue` or redesign |
| Using `do` to access a possibly empty array | Out-of-bounds access on the first pass | Guard with an emptiness check before the loop |
| Assuming loop exit means valid data | May have stopped due to exhausting attempts | Check the success status separately |
| Using `int` instead of boolean as the condition | Does not compile in Java | Use an explicit comparison like `count < limit` |

Example of a loop prone to becoming infinite, **do not run**:

~~~java
// int x = 0;
// do {
//     System.out.println(x);
// } while (x < 3); // x does not change, condition is always true.
~~~

A `Boolean` wrapper with value `null` is also not a valid runtime condition value: Java will attempt to unbox it and may throw `NullPointerException`. Use a primitive `boolean` variable or ensure the wrapper is non-null.

## 7. Standalone runnable Java 17+ program

Create the file **DoWhileDemo.java**:

~~~java
public final class DoWhileDemo {
    public static void main(String[] args) {
        int whileCount = 0;
        while (whileCount < 0) {
            whileCount++;
        }
        System.out.println("whileInitiallyFalse=" + whileCount);

        int doCount = 0;
        do {
            doCount++;
        } while (doCount < 0);
        System.out.println("doInitiallyFalse=" + doCount);

        int rounds = 0;
        do {
            rounds++;
            System.out.println("round=" + rounds);
        } while (rounds < 3);

        int[] candidates = {-2, 0, 7};
        int index = 0;
        int selected;
        do {
            selected = candidates[index++];
            System.out.println("candidate=" + selected);
        } while (selected <= 0 && index < candidates.length);
        System.out.println("selected=" + selected);
        System.out.println("valid=" + (selected > 0));

        int tries = 0;
        do {
            tries++;
            if (tries == 2) {
                System.out.println("breakAt=" + tries);
                break;
            }
        } while (tries < 4);
        System.out.println("breakCount=" + tries);

        int i = 0;
        do {
            i++;
            if (i % 2 == 0) {
                continue;
            }
            System.out.println("odd=" + i);
        } while (i < 4);
        System.out.println("continueCount=" + i);

        int once = 0;
        do {
            once++;
        } while (false);
        System.out.println("once=" + once);
    }
}
~~~

Compile and run in the directory containing the file (PowerShell, Command Prompt, or Bash):

~~~bash
javac -encoding UTF-8 DoWhileDemo.java
java DoWhileDemo
~~~

**Exact expected stdout:**

~~~text
whileInitiallyFalse=0
doInitiallyFalse=1
round=1
round=2
round=3
candidate=-2
candidate=0
candidate=7
selected=7
valid=true
breakAt=2
breakCount=2
odd=1
odd=3
continueCount=4
once=1
~~~

Verification: `doInitiallyFalse=1` confirms the body runs once when the condition is initially false; `round=1..3` demonstrates post-body condition checking; `breakCount=2` and `continueCount=4` illustrate the two control statements. `valid=true` proves the final value is valid, rather than merely inferring it from the fact that the loop stopped.

## 8. Exercises and checklist

**Exercise 1.** Given `int n = 5;`, compare how many times the body runs for `while (n < 3)` and `do { n++; } while (n < 3);`. Explain why.

**Exercise 2.** Write a `do-while` loop that increments `i` from 0 and prints `i` until `i == 4`. Create a state table showing values before the body, after the body, and after the condition check.

**Exercise 3.** Given a list of numbers that might be empty: add a guard before `do` to avoid invalid access to the first element, and return an error status if the list ends without encountering a positive number.

**Exercise 4.** Insert `continue` when `i` is even, printing only odd numbers from 1 to 5. Where should the update operation be placed to guarantee the loop terminates?

**Exercise 5.** Use `break` when encountering the target value and explain whether the loop-end condition is still evaluated on the iteration that executes `break`.

**Checklist:** Is the boolean condition valid? Does the control variable change on every necessary path? Is the first pass safe? Do you distinguish stopping due to success, limits, or errors? Did you write the `;` terminating the `do-while` syntax?

### Key takeaway

**`do { ... } while (condition);` always starts executing the body before the first condition check.** It is suitable for tasks that **must be attempted once before deciding to repeat**. Unlike `while`, an initially false condition does not prevent the first pass; check input safety, stopping points, and variable update placement, especially when using `continue`.
