# Recursion, Base Cases, and the Risk of `StackOverflowError` — Java 17+

## 1. What Is Recursion?

**Recursion** is a technique in which a method calls **itself** (directly), or calls another method that leads back to the original call (indirectly), in order to solve a problem via smaller subproblems.

Example: computing the factorial of a non-negative integer `n`:

~~~java
static long factorial(int n) {
    if (n == 0) {
        return 1L;                  // Base case.
    }
    return n * factorial(n - 1);    // Recursive case.
}
~~~

For `n = 4`, we have `4! = 4 × 3 × 2 × 1 = 24`. The call sequence can be visualized as:

~~~text
factorial(4)
  4 * factorial(3)
        3 * factorial(2)
              2 * factorial(1)
                    1 * factorial(0)
                          return 1
                    return 1
              return 2
        return 6
  return 24
~~~

The method above is **illustrative only** for inputs `n >= 0`. If called with a negative number, `n - 1` will not move toward `0` as intended. The complete program below adds input-domain validation and safe bounds for the `long` type.

Recursion is not a special kind of loop: each call is genuinely **a method invocation** with its own parameters and execution state.

## 2. Two Important Conditions for Recursion to Terminate

A correct recursive algorithm normally needs both factors:

1. **Base case:** the condition under which the method returns a result or finishes without **making further recursive calls**. For example, `n == 0` when computing factorial.
2. **Progress toward base case:** each recursive call must bring the problem **closer to the base case**. For example, `n - 1` when `n > 0`.

~~~java
static int sumToZero(int n) {
    if (n < 0) {
        throw new IllegalArgumentException("n must be non-negative");
    }
    if (n == 0) {
        return 0;
    }
    return n + sumToZero(n - 1);
}
~~~

~~~text
sumToZero(3)
= 3 + sumToZero(2)
= 3 + 2 + sumToZero(1)
= 3 + 2 + 1 + sumToZero(0)
= 3 + 2 + 1 + 0
= 6
~~~

Having a base case without **making progress toward it** is also a bug:

~~~java
// DO NOT RUN: illustrates an error.
// static int wrong(int n) {
//     if (n == 0) return 0;
//     return n + wrong(n); // n does not change.
// }
~~~

Similarly, calling `wrong(-1)` in a version that only decreases `n - 1` while stopping at `n == 0` fails to progress properly on the input domain. Identify the **valid domain**, **base case**, and **decreasing quantity** before writing the method.

## 3. Stack Frames and the Two Phases: Call and Return

The JVM manages method invocations using the **call stack**. Each recursive call gets a **stack frame** containing execution info such as local variables, parameters, and the continuation point after the call.

When calling `factorial(3)`:

~~~text
Going deeper (call):
factorial(3) -> factorial(2) -> factorial(1) -> factorial(0)

At maximum depth:
+--------------------+
| factorial(0)       | <- current call; hits base case
+--------------------+
| factorial(1)       |
+--------------------+
| factorial(2)       |
+--------------------+
| factorial(3)       |
+--------------------+

Unwinding (return):
factorial(0) -> factorial(1) -> factorial(2) -> factorial(3)
~~~

`factorial(3)` must wait for the result of `factorial(2)`, which waits for `factorial(1)`, and so on. After the base case, results are returned in **reverse order of calls**, and completed frames are popped off the stack one by one.

Each call has its own copy of parameter `n`. Modifying `n` in one call does not automatically alter `n` in another frame.

## 4. Tracing Execution Order

To observe the calls, print info **before** and **after** the recursive step:

~~~java
static void trace(int n) {
    System.out.println("enter " + n);
    if (n == 0) {
        System.out.println("base " + n);
        return;
    }
    trace(n - 1);
    System.out.println("leave " + n);
}
~~~

When `trace(3)` runs with a non-negative input:

~~~text
enter 3
enter 2
enter 1
enter 0
base 0
leave 1
leave 2
leave 3
~~~

- The `enter` lines appear while **descending** the call chain.
- `base 0` is the stopping point, making no further calls.
- The `leave` lines appear as the calls **return**.
- The `n == 0` branch uses `return;` to end the `void` method, so it does not print `leave 0`.

When reading a recursive method, track simultaneously the **stopping condition**, the **arguments to the next call**, and **work happening after the call returns**.

## 5. What Is `StackOverflowError`?

Every recursive call adds another stack frame, consuming thread stack resources. If the program keeps calling deeply until no more frames can be created, the JVM can throw **`java.lang.StackOverflowError`**.

Typical causes:

- **Missing base case**, such as a method calling itself unconditionally.
- Having a base case, yet **parameters make no progress toward it**, such as `f(n)` calling `f(n)`.
- Base case does not cover the **input domain**: counting down to `0` while starting from a negative number.
- A **correct** algorithm requiring too many nested calls, such as traversing an overly deep data structure or linear recursion on a very large input.
- **Indirectly recursive** methods calling each other back and forth with no termination condition.

~~~java
// DO NOT RUN this snippet:
// static void endless() {
//     endless(); // No base case.
// }
~~~

**Do not run buggy examples just to watch the stack overflow.** `StackOverflowError` is an `Error`, not an `Exception`. Catching it with `catch (StackOverflowError e)` is not a normal way to control business logic: the stack may be short on resources, and handling it may be unsafe.

There is no **fixed maximum call count** across every JVM. Depth is affected by thread stack limits, JVM, operating system, JIT compilation, and frame size; you should not rely on a threshold measured on a specific machine.

## 6. Correct Recursion Still Risks Stack Overflow

Consider:

~~~java
static long sumRecursively(int n) {
    if (n == 0) return 0;
    return n + sumRecursively(n - 1);
}
~~~

Logically, for `n >= 0`, `n` decreases steadily and eventually reaches `0`. However, for very large `n`, the method requires roughly `n + 1` nested calls, which can overflow the stack **before reaching the base case**.

Iterative version:

~~~java
static long sumIteratively(int n) {
    if (n < 0) throw new IllegalArgumentException("negative n");
    long total = 0;
    for (long i = 1; i <= n; i++) {
        total += i;
    }
    return total;
}
~~~

Use a `long` counter so `i++` does not overflow when `n == Integer.MAX_VALUE`; with an `int` counter, `i <= n` can remain true after `i` overflows into negative numbers. A loop also avoids **growing call stack depth with `n`**. For non-negative `int` inputs `n`, the sum from 1 to `n` always fits in `long`; if expanding the input range or changing the calculation, check for numeric overflow separately. The formula `n(n+1)/2` also needs care to avoid overflow in intermediate multiplications.

## 7. Complexity: Time and Stack Space

| Problem / approach | Approximate time | Extra stack | Notes |
|---|---|---|---|
| Recursive factorial `factorial(n)` | `O(n)` | `O(n)` | Reduces `n` by one each step |
| Factorial with a `for` loop | `O(n)` | `O(1)` | Easily avoids deep stacks |
| Recursive binary search in sorted array | `O(log n)` | `O(log n)` | Eliminates roughly half each step |
| Binary search with `while` | `O(log n)` | `O(1)` | Also requires sorted data |
| Naive recursive Fibonacci `fib(n-1)+fib(n-2)` | `O(2^n)` (upper bound) | `O(n)` | Recomputes many subproblems repeatedly |

**Note:** “Recursive” does not automatically mean slow. Cost depends on the number of subproblems and depth. For divide-and-conquer problems, recursion often expresses the problem structure cleanly. For a long linear chain, a loop can be more practical.

Naive recursive Fibonacci has base cases at `0` and `1` yet still runs slowly because of repeated computations. Use **memoization** or a loop to avoid redundant work; fixing the stopping condition alone is not enough.

## 8. Recursion on Index Ranges: Binary Search

The base case is not always `n == 0`. For binary search on an **ascending sorted** array, the subproblem is an **index range** `low..high`.

~~~java
static int search(int[] a, int target, int low, int high) {
    if (low > high) return -1;                 // Empty range.
    int mid = low + (high - low) / 2;
    if (a[mid] == target) return mid;          // Found.
    if (target < a[mid]) {
        return search(a, target, low, mid - 1);
    }
    return search(a, target, mid + 1, high);
}
~~~

At each step, the new range is **smaller** than the old one; depth grows as `O(log n)`. The base case `low > high` expresses “no positions left to check”; `a[mid] == target` expresses “found”.

Example `a = {1,3,5,7,9}`:

~~~text
search target=7 in [0..4], mid=2 -> a[2]=5
continue searching [3..4], mid=3 -> a[3]=7
return 3
~~~

**Precondition:** the array must be sorted in the exact order used for comparison. If the input is unsorted, the result is no longer guaranteed.

## 9. When to Use Recursion vs. Loops?

Choose **recursion** when a problem is naturally described in terms of subproblems, such as:

- Traversing directory trees, expression trees, nested structures.
- Binary search, divide-and-conquer over data ranges.
- *Backtracking* algorithms with clear state, stopping condition, and undo steps.

Consider **loops** when:

- Steps are simple and linear.
- Inputs can cause depths of hundreds of thousands or millions of calls.
- Stack resources or practical performance must be controlled.
- Results can be computed in `O(1)` memory without making the code harder to read.

Java **does not guarantee tail-call optimization**. Placing a recursive call at the very end of a method **does not mean** the stack frame will definitely be reused on the JVM. For problems requiring very large depth, use a loop or an explicit stack structure when appropriate.

The `-Xss` flag can adjust stack size in some JVM configurations, yet it **does not fix a logic bug missing a base case** and is not the primary solution for algorithms with uncontrolled depth growth.

## 10. Standalone Runnable Java 17+ Program

Create the file with the exact name **`RecursionBaseCaseDemo.java`**:

~~~java
import java.util.Arrays;

public final class RecursionBaseCaseDemo {
    private RecursionBaseCaseDemo() {}

    // Validate at the call boundary; 20! still fits in long.
    static long factorial(int n) {
        if (n < 0 || n > 20) {
            throw new IllegalArgumentException("factorial n must be 0..20");
        }
        return factorialRecursive(n);
    }

    private static long factorialRecursive(int n) {
        if (n == 0) return 1L;             // Base case: 0! = 1.
        return n * factorialRecursive(n - 1);
    }

    static long factorialIterative(int n) {
        if (n < 0 || n > 20) {
            throw new IllegalArgumentException("factorial n must be 0..20");
        }
        long value = 1L;
        for (int i = 2; i <= n; i++) {
            value *= i;
        }
        return value;
    }

    static void trace(int n) {
        if (n < 0) {
            throw new IllegalArgumentException("trace n must be >= 0");
        }
        System.out.println("enter " + n);
        if (n == 0) {
            System.out.println("base " + n);
            return;
        }
        trace(n - 1);
        System.out.println("leave " + n);
    }

    static int digitSum(int n) {
        if (n < 0) {
            throw new IllegalArgumentException("digits n must be >= 0");
        }
        if (n < 10) return n;
        return (n % 10) + digitSum(n / 10);
    }

    // Use only with an int[] array sorted in ascending order.
    static int binarySearch(int[] sorted, int target) {
        if (sorted == null) {
            throw new IllegalArgumentException("array must not be null");
        }
        return search(sorted, target, 0, sorted.length - 1);
    }

    private static int search(int[] a, int target, int low, int high) {
        if (low > high) return -1;
        int mid = low + (high - low) / 2;
        if (a[mid] == target) return mid;
        if (target < a[mid]) {
            return search(a, target, low, mid - 1);
        }
        return search(a, target, mid + 1, high);
    }

    public static void main(String[] args) {
        System.out.println("factorial 0=" + factorial(0));
        System.out.println("factorial 5=" + factorial(5));
        System.out.println("factorial 10=" + factorial(10));
        System.out.println("factorial 20=" + factorial(20));
        System.out.println("factorial loop 5=" + factorialIterative(5));
        System.out.println("digit sum 405=" + digitSum(405));
        System.out.println("digit sum 0=" + digitSum(0));

        trace(3);

        int[] sorted = {1, 3, 5, 7, 9};
        System.out.println("sorted=" + Arrays.toString(sorted));
        System.out.println("search 7=" + binarySearch(sorted, 7));
        System.out.println("search 2=" + binarySearch(sorted, 2));
        System.out.println("search empty="
                + binarySearch(new int[0], 7));

        try {
            factorial(-1);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid factorial=" + ex.getMessage());
        }
    }
}
~~~

**Requirements:** JDK 17 or later, standard Java only; no external libraries or preview features needed. The example code **does not intentionally trigger `StackOverflowError`**.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 RecursionBaseCaseDemo.java
java -cp . RecursionBaseCaseDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\RecursionBaseCaseDemo.java
java -cp . RecursionBaseCaseDemo
~~~

### Exact expected stdout

~~~text
factorial 0=1
factorial 5=120
factorial 10=3628800
factorial 20=2432902008176640000
factorial loop 5=120
digit sum 405=9
digit sum 0=0
enter 3
enter 2
enter 1
enter 0
base 0
leave 1
leave 2
leave 3
sorted=[1, 3, 5, 7, 9]
search 7=3
search 2=-1
search empty=-1
invalid factorial=factorial n must be 0..20
~~~

**Comparison:** `factorial(0)` finishes immediately; `factorial(5)` descends and multiplies results while returning. `digitSum(405)` computes `5 + 0 + 4 = 9` via `n % 10` and `n / 10`. `trace(3)` shows frame entry/exit order. Binary search has two stopping kinds: finding the target or exhausting the search range. Negative input to `factorial` is rejected before starting the recursive chain.

## 11. Common Mistakes and How to Fix Them

| Mistake | Consequence | How to fix |
|---|---|---|
| Omitting a base case | Calls can grow without bound | Write `if (base) return ...;` |
| Having a base case without changing parameters | Does not progress toward base case | Prove each call makes the problem smaller |
| Checking only `n == 0`, ignoring `n < 0` | Negative inputs may not terminate properly | Validate the input domain |
| Writing `return n * factorial(n)` | Calls itself with the same problem | Usually need `factorial(n - 1)` |
| Calling `factorial(21)` with `long` unchecked | **Arithmetic overflow**, not necessarily stack overflow | Limit to 0..20 or use `BigInteger` |
| Linear recursion with huge input | Stack frames grow linearly | Switch to a loop/explicit stack |
| Assuming Java always optimizes tail recursion | JVM does not guarantee it | Design independently of this optimization |
| Catching `StackOverflowError` to fix recursion bugs | Can lack resources, hides bugs | Fix the logic and bound depth |
| Binary search when the array is unsorted | Search results can be wrong | Ensure the sorted precondition |
| Caring only about `O(n)` time | Overlooks `O(n)` stack space | Check stack memory as well |

**Distinguish two risks:** `StackOverflowError` concerns the call stack; **integer overflow** happens when a result exceeds the numeric type's range, and normally does not throw `StackOverflowError`. Recursive factorial with `long` must control both depth and result value range.

## 12. Exercises and Answers

**A — Where is the base case?**

~~~java
static int countDown(int n) {
    if (n == 0) return 0;
    return 1 + countDown(n - 1);
}
~~~

**Answer:** base case `n == 0`. For `n = 3`, the result is `3`, though it is not safe for `n < 0`. Add a guard for negative numbers.

**B — Why might the following fail to terminate?**

~~~java
// Do not run:
static void loopForever(int n) {
    if (n == 0) return;
    loopForever(n);
}
~~~

**Answer:** parameter `n` does not change; for `n != 0`, it cannot progress to the base case.

**C — What does `trace(2)` print?**

~~~text
enter 2
enter 1
enter 0
base 0
leave 1
leave 2
~~~

**D — When does stack usage grow as `O(n)`?**  
**Answer:** when nested calls decrement `n` by one step down to the base case, such as `factorial(n)`, requiring roughly `n + 1` frames at maximum depth.

**E — What does `binarySearch(new int[]{1,3,5,7,9}, 7)` produce?**  
**Answer:** `3` (0-based index); for target 2 it returns `-1`.

**F — Can recursive factorial be replaced with a loop to avoid deep stacks?**  
**Answer:** yes; a loop uses `O(1)` extra stack space in the standard implementation. However, you still need to watch out for large factorials overflowing `long`.

## 13. Checklist and Conclusion

- [ ] Understand recursion as repeated method calls on subproblems.
- [ ] Identify a **base case** that makes no recursive call.
- [ ] Prove calls progress toward the base case over the valid input domain.
- [ ] Understand the “descend” and “return results back up” sequence on the call stack.
- [ ] Recognize `StackOverflowError` caused by missing termination or excessive depth.
- [ ] Do not intentionally run infinite recursion or rely on `catch StackOverflowError`.
- [ ] Distinguish stack overflow errors from arithmetic overflow errors.
- [ ] Know how to compare time and memory costs of recursion and loops.
- [ ] Do not assume Java performs tail-call optimization.
- [ ] Read range-based base cases like `low > high` in binary search.
- [ ] Run `RecursionBaseCaseDemo.java` on JDK 17+ and verify exact stdout.

**Conclusion:** A safe recursive algorithm requires a **correct base case**, **progress that shrinks the problem**, and **execution depth suited to the stack**. A logically sound base case alone does not guarantee safety on very large inputs. Validate the input domain, account for stack space, and choose a loop whenever depth risks exceeding the JVM's capacity.