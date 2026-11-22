# `while` checks the condition before each iteration — Java 17+

The `while` loop executes a block of statements **as long as the condition remains true**. The most important point: Java **checks the condition before each run of the body**, including the first one. Therefore, if the condition is false right from the start, the loop body runs **0 times**.

~~~java
int n = 1;
while (n <= 3) {
    System.out.println(n);
    n++;
}
// Prints: 1, 2, 3; after the loop n == 4.
~~~

## 1. Syntax and execution order

~~~java
while (booleanCondition) {
    // Statements executed when the condition is true.
}
~~~

Process:

1. **Evaluate** the condition expression `booleanCondition`.
2. If `false`: exit the `while` loop and continue to the statement immediately following it.
3. If `true`: run the loop body, except in cases of flow control such as `break`, `return`, or an exception.
4. After the body completes normally (or encounters `continue`), **return to step 1**; the previous condition result is not retained.

~~~mermaid
flowchart TD
    A["Start"] --> B{"Condition true?"}
    B -- "No" --> D["Statement after while"]
    B -- "Yes" --> C["Run while body"]
    C --> B
~~~

**The condition must have type `boolean`** (or unboxed `Boolean`). Java does not accept `while (1)` or `while (number)` like some other languages; use an expression such as `number > 0`.

## 2. Runnable Java 17+ CLI example

Create a UTF-8 file named **`WhilePrecheckDemo.java`**:

~~~java
public class WhilePrecheckDemo {
    static boolean check(int value) {
        System.out.println("check=" + value);
        return value < 2;
    }

    static void precheckTrace() {
        int n = 0;
        while (check(n)) {
            System.out.println("body=" + n);
            n++;
        }
        System.out.println("after=" + n);
    }

    static void zeroIterations() {
        int stock = 0;
        int visits = 0;
        while (stock > 0) {
            visits++;
            stock--;
        }
        System.out.println("visits=" + visits);
    }

    static void skipEvenNumbers() {
        int n = 0;
        while (n < 5) {
            n++; // Progress before the continue branch.
            if (n % 2 == 0) {
                continue;
            }
            System.out.println("odd=" + n);
        }
        System.out.println("last=" + n);
    }

    static void stopOnSentinel() {
        String[] inputs = {"2", "bad", "4", "stop", "99"};
        int index = 0;
        int sum = 0;
        while (index < inputs.length) {
            String token = inputs[index++];
            if (token.equals("stop")) {
                System.out.println("found=stop");
                break;
            }
            try {
                sum += Integer.parseInt(token);
            } catch (NumberFormatException ex) {
                System.out.println("invalid=" + token);
            }
        }
        System.out.println("sum=" + sum);
        System.out.println("consumed=" + index);
    }

    static void exitInfiniteLoop() {
        int attempts = 0;
        while (true) {
            attempts++;
            if (attempts == 3) {
                System.out.println("breakAt=" + attempts);
                break;
            }
        }
        System.out.println("afterBreak=" + attempts);
    }

    public static void main(String[] args) {
        System.out.println("== count ==");
        int count = 1;
        while (count <= 3) {
            System.out.println("count=" + count);
            count++;
        }
        System.out.println("countAfter=" + count);

        System.out.println("== zero iterations ==");
        zeroIterations();

        System.out.println("== check before every body ==");
        precheckTrace();

        System.out.println("== continue ==");
        skipEvenNumbers();

        System.out.println("== sentinel and break ==");
        stopOnSentinel();

        System.out.println("== while true with exit ==");
        exitInfiniteLoop();
        System.out.println("done");
    }
}
~~~

Requires **JDK 17 or later**. Open PowerShell (Windows) or Bash (Linux/macOS) in the directory containing the file and run:

~~~bash
java -version
javac -version
javac -encoding UTF-8 WhilePrecheckDemo.java
java WhilePrecheckDemo
~~~

**Exact expected stdout** of the `java WhilePrecheckDemo` command alone:

~~~text
== count ==
count=1
count=2
count=3
countAfter=4
== zero iterations ==
visits=0
== check before every body ==
check=0
body=0
check=1
body=1
check=2
after=2
== continue ==
odd=1
odd=3
odd=5
last=5
== sentinel and break ==
invalid=bad
found=stop
sum=6
consumed=4
== while true with exit ==
breakAt=3
afterBreak=3
done
~~~

`java -version` and `javac -version` display information depending on the JDK version and are not part of the fixed stdout.

## 3. Why can `while` loop 0 times?

~~~java
int available = 0;
while (available > 0) {
    System.out.println("processing");
    available--;
}
System.out.println("finished");
~~~

The condition `available > 0` is false on the very first check. Therefore **`processing` is not printed**, only `finished` is printed. There is no “mandatory first pass” in `while`.

If the business requirement is *to execute the body at least once before checking*, consider `do ... while`:

~~~java
int n = 0;
do {
    System.out.println("run once");
} while (n > 0);
~~~

This snippet prints `run once` once even though the condition is false. This is a difference in **when the condition is checked**, not two equivalent syntax names.

| Construct | Check timing | Minimum iterations |
| --- | --- | ---: |
| `while (condition) { ... }` | Before each iteration, including the first | 0 |
| `do { ... } while (condition);` | After each iteration | 1 |
| `for (init; condition; update) { ... }` | Checked before each iteration after init | 0 |

## 4. The condition is re-evaluated, not checked just once

In `precheckTrace()`, the `check(n)` method prints the value when **called**:

~~~text
check=0
body=0
check=1
body=1
check=2
after=2
~~~

The line `check=2` appears, yet **there is no `body=2`**: the condition became false and the loop stopped immediately.

If the condition expression reads variables or calls methods, the value may change on each evaluation. Therefore avoid placing **hard-to-observe side effects** in the condition; if you must use them, make the order and stopping point clear.

Also do not confuse `while (flag = true)` with `while (flag == true)`: if `flag` has type `boolean`, **the `=` assignment is valid** and makes `flag` always true, easily creating an infinite loop. Usually just `while (flag)` is enough when checking a flag.

## 5. A progression mechanism and stopping point are needed

Buggy example:

~~~java
int n = 1;
// while (n <= 3) {
//     System.out.println(n);
//     // Forgot n++: the condition stays true forever if there is no intervention.
// }
~~~

A reasonable `while` loop typically needs **a changing control variable**, consumed input data, or an exit statement guaranteed to occur under business assumptions.

Safe example based on array size:

~~~java
String[] items = {"A", "B", "C"};
int index = 0;
while (index < items.length) {
    System.out.println(items[index]);
    index++;
}
~~~

The variable `index` increases from 0 up to `items.length`; right before accessing the array, the condition confirms that the index is within valid bounds. Do not modify the array/external data in a way that invalidates the stopping assumption.

**Be careful with `continue`:** it skips the rest of the body and jumps back to **checking the condition**. If the increment statement is placed after `continue`, the loop may fail to make progress:

~~~java
int n = 0;
// while (n < 5) {
//     if (n == 0) continue; // Wrong: n remains 0.
//     n++;
// }
~~~

In `skipEvenNumbers()`, the `n++` statement is placed **before** `continue`, so the loop still terminates.

## 6. `break`, `continue`, `return`, and exceptions

| Case | Effect |
| --- | --- |
| Normal end of body | Returns to evaluating the `while` condition |
| `continue;` | Skips the remaining statements of the current iteration and returns to checking the loop condition |
| `break;` | Exits the innermost loop and moves to the statement after the loop |
| `return;` / `return value;` | Exits the current **method** |
| `throw ...;` | Throws an exception and does not continue normal flow |

Use `while (true)` when **intentionally** controlling termination via `break`/`return` or an exception. In the demo, the condition is always true, but when `attempts == 3`, `break` causes the loop to finish.

For loops that read data until a terminating marker (*sentinel*) such as `"stop"`, `break` helps stop immediately when the marker is encountered. In the example, `"99"` after `"stop"` is **not processed**, so the sum is only 2 + 4 = 6.

## 7. Avoid common mistakes

| Misconception | Truth |
| --- | --- |
| “The `while` body runs first and then the condition is checked.” | `while` **checks first**, and can run 0 times |
| “The condition is evaluated only once.” | Re-evaluated before **each iteration** |
| “`while (1)` works like in C.” | Java requires a condition of type `boolean` |
| “`continue` goes straight to the end of the loop without rechecking the condition.” | `while` still re-evaluates the condition |
| “`break` exits the entire method.” | `break` only exits the innermost loop (or switch) |
| “The body doesn't need to change anything because the condition updates itself.” | An appropriate progression/exit mechanism is required |
| “`while (flag = true)` only checks the flag.” | This is **assigning true**, which can cause an infinite loop |
| “Adding `;` after `while (condition)` is harmless.” | Creates an **empty body**, and the following block may not belong to the loop |

If the condition is a `Boolean` wrapper with value `null`, unboxing it to evaluate `while` will throw a `NullPointerException`. For potentially null inputs, check explicitly before looping or use a safe condition like `Boolean.TRUE.equals(flag)`.

## 8. Exercises and checklist

1. `int n = 5; while (n < 5) { n++; }` — how many iterations does it run? **0 iterations**.
2. `int n = 0; while (n < 2) { n++; }` — how many times is the condition evaluated if there is no abnormal exit? **3 times** (true twice, false on the last check).
3. Why can `continue` before `n++` cause an infinite loop? **The control variable does not change**.
4. Can `while (true) { break; }` exit? **Yes**, it exits immediately at `break`.
5. When should you consider `do ... while`? **When the body must run at least once**.

**Self-check:** Have I clearly identified the `boolean` condition, when the condition is evaluated, the progression mechanism, the exit path, and the behavior when the condition is false from the start?

**Conclusion:** `while` is a **pre-test loop**. Every iteration must pass through the condition; the body may not run at all. Write safe loops by keeping conditions clear, ensuring progression or a stopping point, and understanding `break`/`continue` accurately.
