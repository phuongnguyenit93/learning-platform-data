# Infinite loops and termination guarantees in Java

> **Java core — language-basics / Loops**  
> **Environment:** Java 17+, self-contained single-file examples, JDK only.  
> **Goal:** Distinguish buggy infinite loops from intentional long-running loops; identify stopping conditions, progression state, iteration limits, and how to avoid traps with `continue`, `break`, and integer overflow.

## 1. What is an infinite loop?

A loop continues while its loop condition remains `true` (or when intentionally using `for (;;)`/`while (true)`). It becomes an **infinite loop** when there is no realistic execution path that causes flow to exit the loop.

~~~java
// Buggy example: DO NOT RUN this snippet.
// int count = 0;
// while (count < 3) {
//     System.out.println(count);
//     // Forgot count++: count stays 0 forever.
// }
~~~

There are two situations to distinguish:

- **Unintentional infinite loop:** Variable is not updated, condition can never become false, update is skipped by `continue`, or overflow wraps the loop back to a previous state.
- **Intentional infinite loop:** Event processors, servers, or workers that run until receiving a stop signal. This kind still needs a clear **cancellation, interruption, exit, or resource-closing** mechanism.

Do not equate “runs very long” with “infinite”. A loop bounded by millions of iterations is still finite, though it can consume CPU or make the application unresponsive. Conversely, merely having an exit condition in code **does not guarantee** that the condition will necessarily occur when external data does not cooperate.

## 2. Three questions to evaluate termination

For every loop, determine:

1. **Continuation / stopping condition:** When does the check become false, or when is `break`/`return` executed?
2. **Progression state:** Along every continuing path, which variable or data is updated to move closer to the stopping point?
3. **Bounds:** Is there a finite domain, retry limit, deadline, or reliable cancellation signal?

A useful proof technique is finding a *loop variant* (a progress measure): a **non-negative** integer that **strictly decreases on every iteration** when the loop continues and is never reset or overflowed. Then it cannot decrease forever, so the loop must stop if every iteration completes.

Example:

~~~java
int remaining = 4;

while (remaining > 0) {
    System.out.println("remaining=" + remaining);
    remaining--; // 4 -> 3 -> 2 -> 1 -> 0
}
~~~

Useful invariant: at the start of each iteration, `remaining >= 0`. Variant: `remaining`. Each pass decreases by exactly 1, and at 0 `remaining > 0` is false. Starting with 4, the body runs four times.

**Condition to state explicitly:** The argument above assumes the loop body always reaches the update step (is not hung waiting externally) and arithmetic does not violate numeric type domains/limits.

## 3. Examples with termination guarantees using `for` and `while`

~~~java
static int countUp(int limit) {
    int count = 0;
    for (int i = 0; i < limit; i++) {
        count++;
    }
    return count;
}
~~~

For `limit = 4`, `i` steps through 0, 1, 2, 3 and stops when `i == 4`. For `limit <= 0`, the body runs 0 times. Boundary condition and update sit close together, making verification easy.

Countdown example:

~~~java
static int countdown(int start) {
    int remaining = Math.max(start, 0);
    int rounds = 0;
    while (remaining > 0) {
        rounds++;
        remaining--;
    }
    return rounds;
}
~~~

For `start = 3`, the variant is `remaining`: 3 → 2 → 1 → 0. For `start <= 0`, the loop does not run.

Example of progression without decrementing by exactly 1 each time:

~~~java
int n = 15;
int rounds = 0;
while (n > 0) {
    n /= 2;    // 15 -> 7 -> 3 -> 1 -> 0.
    rounds++;
}
// rounds == 4
~~~

When `n` is a positive integer, `n / 2 < n` and the result is non-negative, so the number of iterations is finite. A good variant must demonstrate **progress along every branch that can loop back to the top**.

## 4. Mistakes that prevent state from progressing

| Mistake | Example | Fix |
| --- | --- | --- |
| Forgetting to update variable | `while (i < 5) { print(i); }` | Increment `i` or ensure state changes on every path |
| Updating in the wrong direction | `while (i < 5) { i--; }` when `i=0` | Update toward the stopping threshold |
| `continue` skips update | `while (i < 5) { if (i==2) continue; i++; }` | Move update before `continue` or use an appropriate `for` |
| Always-true condition | `while (true)` with no exit mechanism | Design `break`, `return`, or cancellation signal |
| Condition depends solely on external input | Waiting for a value that never arrives | Limit retries, set timeouts, and handle expiration |
| Overflow on control variable | `i++` after `Integer.MAX_VALUE` | Use appropriate bounds and do not rely on overflow to stop |

Correct `continue` example with a `while` loop:

~~~java
int i = 0;
int oddCount = 0;

while (i < 6) {
    i++; // Update BEFORE every continue.
    if (i % 2 == 0) {
        continue;
    }
    oddCount++;
}
// i == 6; oddCount == 3 (1, 3, 5).
~~~

In `while`, `continue` jumps straight to the condition check. In `for (init; condition; update)`, `continue` transfers to the **update expression** before checking the condition, provided there is no abnormal exit.

**`int` overflow:** `Integer.MAX_VALUE + 1` becomes `Integer.MIN_VALUE`. A loop like the following can run forever because every `int` value satisfies `i <= Integer.MAX_VALUE`:

~~~java
// DO NOT RUN: condition is always true for type int.
// for (int i = 0; i <= Integer.MAX_VALUE; i++) {
//     // ...
// }
~~~

Use a bounding condition that can actually become false, avoid comparing against the type's maximum value, and consider `long` or a different loop design if the counting range is large.

## 5. `while (true)` can be correct if it has finite exits

Use an intentional infinite loop when **the stopping point is decided inside the body**. For example, reading a sequence until seeing a positive number or reaching the end of data:

~~~java
static String firstPositive(int[] values) {
    int index = 0;
    while (true) {
        if (index >= values.length) {
            return "NOT_FOUND"; // Out of data -> terminate.
        }

        int candidate = values[index++]; // Progress before continue.
        if (candidate <= 0) {
            continue;
        }
        return "FOUND:" + candidate;
    }
}
~~~

Even though the loop condition is the constant `true`, the function is still **guaranteed to terminate** for finite arrays: `index` increases every pass, either finding a positive number to `return`, or reaching `values.length` to `return`. There is no out-of-bounds access, even for an empty array, because it checks before reading an element.

This is a termination proof based on the quantity `values.length - index` (non-negative and decreasing on each repeatable pass).

**If the data source is network/keyboard** rather than a finite array, assuming “valid data will arrive sooner or later” is only an assumption. You must account for end-of-stream, timeouts, I/O errors, and cancellation signals.

## 6. Capping attempts, handling `break`, and task cancellation

An explicit cap causes the loop to stop even when no result has been found:

~~~java
static String tryGuess(int[] guesses, int target, int maxAttempts) {
    int bound = Math.min(guesses.length, Math.max(maxAttempts, 0));
    int attempts = 0;

    while (attempts < bound) {
        int guess = guesses[attempts++];
        if (guess == target) {
            return "FOUND:" + attempts;
        }
    }
    return "STOP:" + attempts;
}
~~~

Because `attempts` increases each pass and `bound` is fixed, non-negative, and does not exceed array length, the loop stops in at most `bound` passes. The function distinguishes success from exhausting attempts rather than assuming stopping means a match was found.

A short example for `break`:

~~~java
int attempts = 0;
while (true) {
    attempts++;
    if (attempts == 2) {
        break;
    }
}
// attempts == 2.
~~~

`break` exits the innermost loop; `return` exits the method. However, **merely putting `break` in the body is not a termination proof**: you must show why the condition leading to `break` will ultimately become true.

For long-running workers/services, add an appropriate cancellation mechanism (such as `Thread.interrupt()` and handling interruption at wait points), avoiding a busy-spinning `while (true)` loop that wastes CPU. If using a stop flag shared across threads, proper update visibility is required such as `volatile` or an appropriate synchronization class; a plain boolean variable does not guarantee sufficient cross-thread visibility.

## 7. Runnable Java 17+ program

Create the file **LoopTerminationDemo.java**:

~~~java
public final class LoopTerminationDemo {
    private static int countUp(int limit) {
        int count = 0;
        for (int i = 0; i < limit; i++) {
            count++;
        }
        return count;
    }

    private static int countdown(int start) {
        int remaining = Math.max(start, 0);
        int rounds = 0;
        while (remaining > 0) {
            rounds++;
            remaining--;
        }
        return rounds;
    }

    private static int halveUntilZero(int start) {
        int n = Math.max(start, 0);
        int rounds = 0;
        while (n > 0) {
            n /= 2;
            rounds++;
        }
        return rounds;
    }

    private static String firstPositive(int[] values) {
        int index = 0;
        while (true) {
            if (index >= values.length) {
                return "NOT_FOUND";
            }

            int candidate = values[index++];
            if (candidate <= 0) {
                continue;
            }
            return "FOUND:" + candidate;
        }
    }

    private static int countOdds(int limit) {
        int i = 0;
        int oddCount = 0;
        while (i < limit) {
            i++;
            if (i % 2 == 0) {
                continue;
            }
            oddCount++;
        }
        return oddCount;
    }

    private static String tryGuess(
            int[] guesses, int target, int maxAttempts) {
        int bound = Math.min(guesses.length, Math.max(maxAttempts, 0));
        int attempts = 0;

        while (attempts < bound) {
            int guess = guesses[attempts++];
            if (guess == target) {
                return "FOUND:" + attempts;
            }
        }
        return "STOP:" + attempts;
    }

    public static void main(String[] args) {
        System.out.println("forCount4=" + countUp(4));
        System.out.println("forCount0=" + countUp(0));
        System.out.println("countdown3=" + countdown(3));
        System.out.println("countdown0=" + countdown(0));
        System.out.println("halve15=" + halveUntilZero(15));
        System.out.println("halve1=" + halveUntilZero(1));

        System.out.println("positiveFound="
                + firstPositive(new int[] {-2, 0, 5, 9}));
        System.out.println("positiveMissing="
                + firstPositive(new int[] {-3, 0}));
        System.out.println("positiveEmpty="
                + firstPositive(new int[] {}));

        System.out.println("oddsUpTo6=" + countOdds(6));

        int[] guesses = {2, 7, 9};
        System.out.println("guessFound=" + tryGuess(guesses, 7, 3));
        System.out.println("guessStop=" + tryGuess(guesses, 9, 2));
        System.out.println("guessZero=" + tryGuess(guesses, 9, 0));

        int attempts = 0;
        while (true) {
            attempts++;
            if (attempts == 2) {
                break;
            }
        }
        System.out.println("breakAfter=" + attempts);

        int max = Integer.MAX_VALUE;
        System.out.println("intOverflow=" + (max + 1));
    }
}
~~~

Compile and run in the directory containing the file (Bash, PowerShell, or Command Prompt):

~~~bash
javac -encoding UTF-8 LoopTerminationDemo.java
java LoopTerminationDemo
~~~

**Exact expected stdout:**

~~~text
forCount4=4
forCount0=0
countdown3=3
countdown0=0
halve15=4
halve1=1
positiveFound=FOUND:5
positiveMissing=NOT_FOUND
positiveEmpty=NOT_FOUND
oddsUpTo6=3
guessFound=FOUND:2
guessStop=STOP:2
guessZero=STOP:0
breakAfter=2
intOverflow=-2147483648
~~~

The lines `positiveMissing`, `positiveEmpty`, and `guessStop` show the exit path when unsuccessful. `oddsUpTo6=3` proves `continue` does not block updating the control variable. `intOverflow` illustrates why you should not use `Integer.MAX_VALUE` as a bound in a way that keeps the condition always true.

## 8. Checklist and exercises

| Question before accepting a loop | Requirement |
| --- | --- |
| What is the stopping condition? | There is a condition that becomes false or a guaranteed reachable exit |
| What quantity measures progress? | Non-negative, moving toward the bound on every continuing path |
| Is there an un-updated `continue` path? | Update before `continue` or have a guaranteed update |
| Can the counter overflow? | Check numeric range and condition structure |
| Does it depend on external input/sources? | Have limits, timeouts, EOF, or cancellation |
| When attempts run out without success? | Return a distinct failure status; do not infer success |

**Exercise 1.** Identify why `int i=0; while(i<5){ if(i==2)continue; i++; }` gets stuck at `i == 2`, then fix it by ensuring `i` is incremented on every path.

**Exercise 2.** Use a variant to explain why `while (remaining > 0) { remaining--; }` terminates when `remaining` is initially a non-negative integer.

**Exercise 3.** Change `n /= 2` to `n = n - 2` for `n=15`. Write a stopping condition so that negative values do not cause unintended behavior.

**Exercise 4.** Write `while(true)` to find a matching element in a finite array. What termination cases must be present when the array is empty or no match is found?

**Exercise 5.** Design a login attempt function allowing at most 3 attempts: if correct, return success; if 3 attempts are exhausted, return failure. Explain why merely waiting for the user to enter the right input is not a termination guarantee.

### Key takeaway

**Termination guarantee = a stopping point + reliable progress + not losing the stopping point due to overflow, branching paths, or external data.** For finite loops, use a bound or a strictly decreasing non-negative variant. For `while(true)`, a provable exit and appropriate cancellation mechanism are needed; avoid pointless CPU-spinning loops.
