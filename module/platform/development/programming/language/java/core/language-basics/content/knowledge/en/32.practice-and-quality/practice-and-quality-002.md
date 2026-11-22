# Writing Pseudocode and Trace Tables Before Programming

## 1. Why design before writing Java?

When solving a problem, jumping straight into `if`, `for`, and `System.out.println` statements can cause you to miss conditions, pick the wrong variables, or lose track of why a result is wrong. **Pseudocode** and a **trace table** (*dry-run table*) help test your idea before committing to the syntax of a programming language.

- **Pseudocode** describes the sequence of an algorithm in structured natural language. It states **what to do and in what order**, without needing to follow Java syntax.
- **A trace table** records how variables change after each important step, especially when the program has loops and conditional branches.
- **A dry run** simulates the algorithm on a concrete data set without running it on a computer yet.
- **Implementation** translates the verified algorithm into Java and compares actual output against expected results.

An effective workflow:

```text
Read the problem
   |
   v
Identify inputs, outputs, rules, edge cases
   |
   v
Write pseudocode in clear steps
   |
   v
Dry run and build a trace table
   |
   v
Fix logic errors if any
   |
   v
Write Java 17+, compile, and test
   |
   v
Compare results with the trace table and requirements
```

Not every small problem needs a long table. The goal is to be **clear enough to prove the solution makes sense and catch bugs early**, not to add formal busywork.

## 2. Defining requirements and the input/output contract

Before writing pseudocode, answer four questions:

1. **What is the input?** An integer, an array, a list, a string, or data read from a file?
2. **What is the output?** A return value, printed content, or updated state?
3. **What are the calculation rules and constraints?** For example, positive numbers mean `x > 0` (excluding `0`), negative numbers may appear, and the array may be empty.
4. **What are the edge cases and invalid cases?** Empty array, no matching elements, single element, large values, `null`, etc.

Running example:

**Problem:** Given an integer array `int[]`. Count the number of **positive** elements, compute the **sum** of the positive numbers, find the **largest positive number**, and calculate the **average** of the positive numbers. If there are no positive numbers, clearly report that there are no positive numbers and **do not divide by 0**.

Sample input:

```text
[4, -2, 7, 0, 3]
```

Expected results to derive:

- Positive numbers: `4`, `7`, `3`.
- Count: `3`.
- Sum: `4 + 7 + 3 = 14`.
- Largest value: `7`.
- Average: `14 / 3`, which displays to two decimal places as `4.67`.

In this example, **`0` is not a positive number**. You also need to decide upfront: if there are no positive numbers, there is no valid maximum or average; do not treat `0` as the maximum business result.

For a reusable API, you must also specify how `null` references are handled: reject with an exception or treat as an empty array. In the sample program below, the method requires a non-`null` array and explicitly reports an error if violated.

## 3. How to write pseudocode that translates easily to code

Pseudocode **does not have a single mandatory syntax**. Use clear variable names and common constructs:

| Algorithmic idea | Pseudocode notation | Java translation hint |
| --- | --- | --- |
| Initialize state | `count ← 0` | `int count = 0;` |
| Branching | `IF value > 0 THEN ...` | `if (value > 0) { ... }` |
| Iterate elements | `FOR EACH value IN numbers` | `for (int value : numbers) { ... }` |
| Update variable | `sum ← sum + value` | `sum += value;` |
| Handle no-data case | `IF count = 0 THEN ...` | `if (count == 0) { ... }` |
| Produce output | `OUTPUT count, sum` | `System.out.println(...)` |

The `←` symbol is the **assignment** notation commonly used in pseudocode, not a Java operator. Pseudocode uses `=` for comparison only when that convention is clear; in Java, **`==`** checks equality for integers while **`=`** is assignment.

Good pseudocode should:

- Clearly state the **starting point**, the data to maintain, and the order of steps.
- Use meaningful variable names, such as `count`, `sum`, and `max`.
- Express boundary conditions with precise expressions instead of vague phrases like "if the value is suitable."
- Make clear that each iteration **processes one element** and which variables are modified.
- Avoid tying itself to screen printing if the main focus is the algorithm; printing is just one way to present results.
- Avoid jumping into complex optimizations before proving the simple algorithm is correct.

## 4. Writing pseudocode for counting and summarizing positive numbers

A sufficiently detailed pseudocode version:

```text
INPUT numbers: integer array, non-null

count ← 0
sum ← 0
max ← 0                  // Not considered a result until count > 0

FOR EACH value IN numbers DO
    IF value > 0 THEN
        IF count = 0 OR value > max THEN
            max ← value
        END IF
        count ← count + 1
        sum ← sum + value
    END IF
END FOR

OUTPUT count
OUTPUT sum

IF count = 0 THEN
    OUTPUT "no positive values"
ELSE
    average ← sum / count  // Floating-point division, not integer division
    OUTPUT max
    OUTPUT average to 2 decimal places
END IF
```

This is **pseudocode, not compiled by `javac`**. Several key design decisions:

1. `count` and `sum` start at `0` because no elements have been processed yet.
2. `value > 0` filters exactly positive numbers; negative numbers and `0` do not change the count, sum, or maximum.
3. `count = 0` inside the `max` update condition means **this is the first positive number seen**. Therefore, the initial value `max ← 0` is never treated as an actual maximum candidate.
4. You must check `count = 0` **before computing the average** to avoid dividing by `0`.
5. The average must use **floating-point division**. Integer division between two integers loses the fractional part.
6. In Java, use `long sum` to widen the sum range compared to `int`, because adding many positive `int` values can exceed `Integer.MAX_VALUE`. `long` still has limits, so extremely large inputs require input constraints or a more suitable calculation approach.

### Loop invariants

One way to verify correctness is to state what must always remain true after processing each element:

- `count` = number of positive elements seen so far in the processed prefix of the array.
- `sum` = sum of the positive elements seen so far.
- When `count > 0`, `max` = largest number among the positive elements seen so far.

Initially, for a prefix of length `0`, `count = 0` and `sum = 0`; the condition on `max` does not apply yet. Each step either skips a non-positive element or updates all three variables properly for a positive element, so these conditions stay true. After the loop, the processed prefix is **the entire array**, so the final results match the definition.

You do not need a lengthy formal proof for every exercise, but identifying invariants helps verify whether a loop misses or double-counts data.

## 5. Building a step-by-step trace table

A trace table should include **input data, current position, branching condition, and variable values after updates**. For `numbers = [4, -2, 7, 0, 3]`, we have:

| Step | Index `i` | `value` | `value > 0` | `count` after step | `sum` after step | Valid `max` after step |
| --- | ---: | ---: | --- | ---: | ---: | --- |
| Init | — | — | — | 0 | 0 | None yet |
| 1 | 0 | 4 | True | 1 | 4 | 4 |
| 2 | 1 | -2 | False | 1 | 4 | 4 |
| 3 | 2 | 7 | True | 2 | 11 | 7 |
| 4 | 3 | 0 | False | 2 | 11 | 7 |
| 5 | 4 | 3 | True | 3 | 14 | 7 |

Calculation walkthrough:

- **Step 1:** encounters `4 > 0`; this is the first positive number, so `max = 4`, `count = 1`, `sum = 4`.
- **Step 2:** `-2` is not positive, state stays unchanged.
- **Step 3:** encounters `7`, increments `count = 2`, `sum = 11`, updates `max = 7`.
- **Step 4:** `0` is not positive, state stays unchanged.
- **Step 5:** encounters `3`, increments `count = 3`, `sum = 14`; `max` remains `7`.
- **After the loop:** since `count = 3`, the average is `(double) 14 / 3 ≈ 4.666...`, printed as `4.67` when formatted to two decimal places with `Locale.US`.

The `max` column shows **"None yet"** at initialization to distinguish a temporary placeholder stored in the variable from **a meaningful result**. Never print `max = 0` as the largest positive number when the array has no positive numbers.

### Choosing what to put in a trace table

A trace table should answer: "Why is `sum = 11` after the third step?" If it only records the final answer, the table will not help find logic bugs. At the same time, you do not need to list every unrelated variable, because the table would become long and hard to read.

A simple rule is **one row per iteration** with columns for changing variables and deciding conditions. For nested loops, you can add outer/inner loop indices; for search algorithms, you can track the stopping condition and whether the target has been "found" yet.

## 6. Testing edge cases directly on pseudocode

Testing only a "nice" data set is not enough. Use pseudocode and the state table to test other cases:

| Input | `count` | `sum` | Conclusion |
| --- | ---: | ---: | --- |
| `[]` | 0 | 0 | No positive numbers; do not compute `max`/`average` |
| `[-1, 0]` | 0 | 0 | No positive numbers |
| `[5]` | 1 | 5 | `max = 5`, `average = 5.00` |
| `[2, 2, 2]` | 3 | 6 | `max = 2`, `average = 2.00` |
| `[0, 3, -4, 8]` | 2 | 11 | `max = 8`, `average = 5.50` |

These cases directly test common mistakes:

- Using `>= 0` instead of `> 0`, causing `0` to be counted as positive.
- Forgetting to check `count == 0` before dividing.
- Initializing `max` incorrectly when the array contains no positive numbers.
- Checking only the first element or skipping the last element.
- Performing integer division when a fractional average is needed.

A `null` array is not the same as an empty array. If a method's contract does not accept `null`, **reject it explicitly** instead of letting a `NullPointerException` happen deep inside the loop.

## 7. Translating pseudocode into runnable Java 17+

Create the file **`PseudocodeTraceDemo.java`**:

```java
import java.util.Locale;
import java.util.Objects;

public class PseudocodeTraceDemo {
    static void report(int[] numbers) {
        Objects.requireNonNull(numbers, "numbers");

        int count = 0;
        long sum = 0;
        int max = 0;

        for (int value : numbers) {
            if (value > 0) {
                if (count == 0 || value > max) {
                    max = value;
                }
                count++;
                sum += value;
            }
        }

        System.out.println("count=" + count);
        System.out.println("sum=" + sum);

        if (count == 0) {
            System.out.println("no positive values");
        } else {
            double average = (double) sum / count;
            System.out.println("max=" + max);
            System.out.printf(Locale.US, "average=%.2f%n", average);
        }
    }

    public static void main(String[] args) {
        System.out.println("Case A");
        report(new int[] {4, -2, 7, 0, 3});

        System.out.println("Case B");
        report(new int[] {-1, 0});

        System.out.println("Case C");
        report(new int[] {5});
    }
}
```

In the directory containing the file, use **JDK 17 or later** on Windows PowerShell/CMD or Linux/macOS:

```bash
javac -encoding UTF-8 PseudocodeTraceDemo.java
java PseudocodeTraceDemo
```

**Exact stdout** (a successful compilation prints nothing):

```text
Case A
count=3
sum=14
max=7
average=4.67
Case B
count=0
sum=0
no positive values
Case C
count=1
sum=5
max=5
average=5.00
```

### Line-by-line comparison with pseudocode

| Pseudocode | Java 17+ | Meaning |
| --- | --- | --- |
| `count ← 0` | `int count = 0;` | Initial state |
| `sum ← 0` | `long sum = 0;` | Sum, using `long` |
| `FOR EACH value IN numbers` | `for (int value : numbers)` | Iterate through each element |
| `IF value > 0` | `if (value > 0)` | Filter positive numbers |
| `count ← count + 1` | `count++;` | Increment counter |
| `sum ← sum + value` | `sum += value;` | Add to sum |
| `IF count = 0` | `if (count == 0)` | Check for no positive numbers |
| `average ← sum / count` | `(double) sum / count` | Floating-point division, keeping the fractional part |

Two points to verify after translating:

1. **Correct order:** in Java, `max` is updated **before** incrementing `count`, so `count == 0` accurately detects the first positive number. If `count++` were moved earlier, this condition would no longer detect the first occurrence.
2. **Correct types:** `sum` is a `long`, with an explicit cast `(double) sum` during division to prevent integer division. `System.out.printf(Locale.US, ...)` guarantees a decimal dot in the example output.

`Objects.requireNonNull` throws a `NullPointerException` with the parameter name as its message when `numbers == null`. Here that is an **API precondition**; the complete code never passes `null`, so stdout is consistent.

## 8. Types of bugs that dry runs help catch

### Off-by-one error (missing the last element)

The pseudocode aims to visit every element of an array with `n` elements, whose valid indices are `0` to `n - 1`.

```java
// Illustration inside a method:
for (int i = 0; i < numbers.length - 1; i++) {
    // The last element is missed if the goal is to iterate over the whole array.
}
```

A trace table forces you to write down the index `i`; if an array has five elements while the table only has four steps, the bug is easy to spot. The standard way to iterate all indices is `i < numbers.length`, or using for-each when the index is not needed.

### Updating variables in the wrong branch

```java
// Logic error illustration:
for (int value : numbers) {
    if (value > 0) {
        sum += value;
    }
    count++; // Wrong: counts negative numbers and 0 too.
}
```

A trace table for `[-2, 4]` shows that after examining `-2`, `count` becomes 1 even though no positive number has been seen yet. `count++` must be placed **inside** the `value > 0` branch.

### Wrong initialization or update for extrema

When finding the largest value among **all numbers**, initializing `max = 0` is wrong for an array containing only negative numbers. The running example finds the largest **positive** number, so it uses `count > 0` and initializes `max` when the first positive number arrives. **Do not apply this initialization rule mechanically to a different problem**.

### Integer division error

```java
int count = 3;
long sum = 14;
double wrong = sum / count;          // 4.0: integer division first, then converted to double.
double correct = (double) sum / count; // 4.6666...
```

The trace table gives `sum = 14`, `count = 3`; when computing the average, if the program prints `4.00`, that is a sign of choosing the wrong division type. `printf("%.2f")` only formats the result; **it does not recover fractional digits already lost** to integer division.

## 9. How is a trace table different from debug printing?

**A pre-run trace table** is a prediction written from the algorithm's logic; **debug print statements** show the actual state when the JVM executes. Comparing them helps narrow down the exact line where the algorithm goes wrong.

For example, you could temporarily add after each iteration inside `report`:

```java
System.out.println("value=" + value
        + " count=" + count
        + " sum=" + sum);
```

This is an **illustrative snippet** to place inside the loop body, not part of the complete program in section 7. When printing for debugging, make sure the print statement sits **after the state updates** if the table also records post-step state. If you print before updates and compare against a post-update table, you may think there is a bug when you are merely observing two different points in time.

In real programs, you can use breakpoints/a debugger or unit tests instead of leaving lots of debug `println` calls in production code.

One trace table does not prove an algorithm works for **all** inputs. To build confidence, combine:
- Dry-run tables for normal cases and edge cases.
- Invariant arguments or reasoning explaining why conditions and loops are right.
- Automated tests with clear expected outputs.
- Checks for behavior on invalid inputs.

## 10. A reusable trace table template

When practicing other problems, prepare a simple table beforehand:

| Step | Current data | Condition | Variables before | Variables after | Notes |
| --- | --- | --- | --- | --- | --- |
| Init | Not yet inspected | — | — | Initial state | Set initial values |
| 1 | First element | True/False | Old state | New state | Record branch taken |
| 2 | Second element | True/False | Old state | New state | Check whether update is right |
| End | Out of data | Stopping condition | Final state | Result | Verify postcondition |

The table above is an **illustrative template**, not the result table for the positive-numbers example. For search problems, replace columns with `index`, `target`, `found`; for counting problems, track `count`; for summation problems, track `sum`. Always prioritize the variables that determine the algorithm's correctness.

### Pre-Java-coding checklist

1. Have I defined the **inputs, outputs**, and the meaning of each result?
2. Do conditions like `>`, `>=`, `==` match the requirements?
3. Have I specified how to handle **empty arrays / no valid data**?
4. Are counter, sum, and extremum variables initialized properly?
5. Does each loop iteration update the right variables in the right branch and **not miss any element**?
6. Does the trace table cover a normal case and at least one **edge case**?
7. Are there any division-by-zero risks, unintended integer divisions, or overflow risks?
8. Once translated to Java, do the actual run results **match the predictions**?

**Remember:** write pseudocode to express the algorithm before syntax; use a trace table to observe variable changes and catch logic errors early; only then implement in Java and test. An algorithm that is thought through, dry-run, and checked against edge inputs is usually easier to understand and maintain than code written by random trial and error.