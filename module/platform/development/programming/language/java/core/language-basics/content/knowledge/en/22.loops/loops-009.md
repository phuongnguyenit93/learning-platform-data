# Maintaining a simple loop invariant across iterations — Java 17+

## 1. What is a loop invariant?

A **loop invariant** (*loop invariant*) is a statement about program state that holds true **every time the loop condition is about to be checked**, including the final check when the loop terminates normally.

For example, when summing an array from left to right:

~~~java
int[] numbers = {2, -1, 4, 3};
long sum = 0;

for (int i = 0; i < numbers.length; i++) {
    sum += numbers[i];
}

System.out.println(sum);
~~~

**Exact expected stdout:**

~~~text
8
~~~

A useful invariant at the **start of each iteration** is:

> `sum` equals the sum of **exactly the first `i` elements**: `numbers[0]` through `numbers[i-1]`.

For `i = 0`, no elements have been processed so `sum = 0`. For `i = 2`, `2` and `-1` have been processed so `sum = 1`. When the loop finishes with `i = numbers.length`, the invariant tells us `sum` is the sum of the entire array.

An invariant is not a Java keyword or syntax; it is a **logical assertion** defined, reasoned about, and optionally verified during debugging/testing by the author.

## 2. Three steps to prove an invariant

| Step | Question to answer | Prefix sum example |
|---|---|---|
| **Initialization** (*initialization*) | Does the statement hold before the first pass? | `i=0`, `sum=0` is the sum of an empty prefix |
| **Maintenance** (*maintenance*) | If it holds before this pass, does it still hold after running the body and update? | Add `numbers[i]`, then `i++`; sum corresponds to a prefix one element longer |
| **Termination** (*termination*) | When the loop condition becomes false, what result does the invariant imply? | `i=n`, so `sum` is the sum of `n` elements |

~~~mermaid
flowchart TD
    A["Initialization: invariant holds"] --> B{"Loop condition true?"}
    B -- "True" --> C["Execute loop body"]
    C --> D["Update counter variable"]
    D --> E["Invariant still holds"]
    E --> B
    B -- "False" --> F["Invariant + stopping condition"]
    F --> G["Derive postcondition/result"]
~~~

**Important distinction:** The three steps above primarily prove **partial correctness**: if the loop terminates, the result is right. To prove it **definitely terminates**, an additional progress argument is needed, usually using a decreasing quantity (*loop variant*).

## 3. Identifying when the invariant must hold

Consider:

~~~java
for (int i = 0; i < numbers.length; i++) {
    sum += numbers[i];
}
~~~

The invariant is stated at the **top of the loop, before checking the condition**. After the line `sum += numbers[i]` but **before `i++` runs**, `sum` is already the sum of `i+1` elements while `i` still has its old value. Therefore the statement “`sum` is the sum of `i` elements” does not necessarily hold **at every intermediate line**.

After the `i++` update, at the start of the next iteration we again have:

- new `i` = old `i` + 1.
- `sum` = sum of the first new `i` elements.
- The invariant is **restored right at the check point**.

This point helps avoid reasoning mistakes: an invariant must hold at **the designated check points**, not necessarily after every assignment inside the body.

## 4. Tracing the prefix sum invariant

Array `{2, -1, 4, 3}`, initialized `sum = 0`:

| Start of pass / at stop | `i` | Processed prefix | `sum` |
|---|---:|---|---:|
| Before pass 1 | 0 | Empty | 0 |
| Before pass 2 | 1 | `[2]` | 2 |
| Before pass 3 | 2 | `[2, -1]` | 1 |
| Before pass 4 | 3 | `[2, -1, 4]` | 5 |
| When `i < 4` is false | 4 | `[2, -1, 4, 3]` | 8 |

**How it is maintained:**

Assume before a pass that `0 <= i < n` and `sum = numbers[0] + ... + numbers[i-1]`.

1. The loop body executes `sum += numbers[i]`.
2. The `for` update executes `i++`.
3. At the start of the next pass, `sum` is the sum of elements at indices 0 through `i-1` for the new `i`.

**Termination:** the condition `i < n` is false and `i` was incremented by 1 from 0. Without abnormal changes or index overflow, `i=n`. Combined with the invariant, the result equals the sum of the entire array.

**Data assumption:** the example uses `long` for the sum to have a wider range than `int`. For real-world data that could overflow `long`, checked arithmetic or `BigInteger` is needed; you cannot let addition overflow and still claim the result is the exact mathematical sum.

## 5. Choosing an invariant strong enough to imply the result

A statement like “`i >= 0`” is usually true in an array traversal loop, yet **insufficient** to prove that the computed sum is correct.

For a summing algorithm, we should simultaneously maintain:

- **Counter bounds:** `0 <= i <= n`.
- **Relation to processed data:** `sum` is the sum of the prefix of length `i`.

When the stopping condition yields `i == n`, both statements together imply `sum` is the sum of the whole array.

**Design tip:** starting from the **desired postcondition** (“sum of all elements”), replace “all” with “those elements processed so far” and tie it to counter `i`. That is usually a simple, easy-to-prove invariant.

## 6. Second example: finding the maximum element

For a **non-empty** array:

~~~java
int[] data = {-3, 5, 1, 7, 7};
int best = data[0];

for (int i = 1; i < data.length; i++) {
    if (data[i] > best) {
        best = data[i];
    }
}

System.out.println(best);
~~~

**Exact expected stdout:**

~~~text
7
~~~

**Invariant at the start of each pass:** `best` is the **maximum value** in the prefix `data[0..i-1]`, with `1 <= i <= data.length`.

- **Initialization:** before the first pass `i=1`, the prefix has one element `data[0]`; `best=data[0]` is the maximum of that prefix.
- **Maintenance:** on pass `i`, compare `data[i]` with `best`; after updating, `best` is the max of the prefix of length `i+1`. After `i++`, the invariant holds for the new index.
- **Termination:** when `i=data.length`, the prefix is the entire array, so `best` is the maximum value of the array.

**Important boundary:** an empty array has no `data[0]`; empty input must be rejected or an optional-result API defined. Setting `best = 0` for all arrays is **wrong** for arrays containing only negative numbers.

If multiple elements tie for largest, the code above returns the **maximum value**, without promising the index of the first or last occurrence. To return a position, an invariant with an additional index variable is needed.

## 7. Third example: finding the first occurrence

~~~java
static int findFirst(int[] data, int target) {
    for (int i = 0; i < data.length; i++) {
        if (data[i] == target) {
            return i;
        }
    }
    return -1;
}
~~~

**Invariant at the start of pass `i`:** no element in **positions `0..i-1`** equals `target`.

- **Initialization:** for `i=0`, the prefix is empty, so the statement holds.
- **Maintenance:** if `data[i] != target`, advance to `i+1` and the unfound prefix expands by one position.
- **If found:** `data[i] == target`; all positions before `i` have been proven different from target, so `i` is the **first position**.
- **If traversal finishes:** `i=n`, all positions differ from target; returning `-1` is correct.

Example:

~~~java
int[] data = {4, 6, 2, 6};
System.out.println(findFirst(data, 6)); // 1
System.out.println(findFirst(data, 9)); // -1
~~~

The snippet above illustrates the logic; the `findFirst` method needs to reside in the same class or be invoked via the class containing it.

**Note:** a `return` upon finding a match is a **valid early exit**. Correctness reasoning then uses the prefix invariant combined with the found condition, without relying on the loop running all the way to `i=n`.

## 8. Invariant is not synonymous with stopping condition

Two different things:

- **Loop invariant:** what always holds at the chosen check point, used to prove **correctness of the result**.
- **Loop variant** (*progress measure*): a non-negative quantity that decreases with each continuing iteration, usually used to prove **termination**.

Example:

~~~java
for (int remaining = 3; remaining > 0; remaining--) {
    System.out.println("remaining=" + remaining);
}
~~~

**Exact expected stdout:**

~~~text
remaining=3
remaining=2
remaining=1
~~~

Invariant: `0 <= remaining && remaining <= 3` at the start of every pass, including when `remaining=0` and the condition has become false. The variant can be `remaining` itself: while still looping, it is a positive integer and each update decreases it by 1, so it eventually reaches 0.

An invariant **by itself** does not prevent an infinite loop:

~~~java
int i = 0;
// while (i >= 0) {
//     // i does not change, condition is always true, invariant i >= 0 still holds.
// }
~~~

To guarantee stopping, there must be **real progress** and consideration of the effects of `break`, `continue`, updates, and potential overflow.

## 9. `break`, `continue`, and invariants

For a three-part `for`:

- `continue;` skips the rest of the body but **still runs the update** before checking the next iteration. The invariant must be preserved across every path using `continue`.
- `break;` exits the loop immediately, **without running the final update**. If a postcondition is needed for the `break` branch, prove separately that the condition at the break site is sufficient.
- `return` exits the method; the return value's postcondition must be proved along that path.

A common mistake:

~~~java
int[] data = {3, -1, 4};
int sum = 0;

for (int i = 0; i < data.length; i++) {
    if (data[i] < 0) {
        continue;
    }
    sum += data[i];
}
~~~

This code returns **7**, not the array sum **6**. If the actual goal is the **sum of non-negative elements**, the proper invariant must be rewritten: `sum` equals the sum of non-negative values in the processed prefix.

**The invariant must accurately reflect the problem requirements and control branches**, not merely resemble a stock template.

## 10. Value of invariant checks during debugging

You can temporarily create a method that **recomputes the prefix sum** and compare it with the state on each iteration:

~~~java
static long prefixSum(int[] data, int limit) {
    long result = 0;
    for (int k = 0; k < limit; k++) {
        result += data[k];
    }
    return result;
}

static void requireInvariant(boolean condition) {
    if (!condition) {
        throw new IllegalStateException("loop invariant violated");
    }
}
~~~

In the summing algorithm:

~~~java
for (int i = 0; i < data.length; i++) {
    requireInvariant(sum == prefixSum(data, i));
    sum += data[i];
}
requireInvariant(sum == prefixSum(data, data.length));
~~~

- Each check at the start of an iteration confirms the statement is being maintained.
- The check **after the loop** confirms the statement in the terminal state.
- If false, `IllegalStateException` helps detect bugs early.

**Limitation:** this check runs an extra loop to recompute the prefix sum, so total debugging cost can turn from `O(n)` into **`O(n²)`**. Use it only for study, tests, or small data; in production, remove it or enable it only selectively.

You can also use Java's `assert`:

~~~java
assert sum == prefixSum(data, i) : "bad prefix sum";
~~~

However, Java **disables assertions by default**; you must run with `java -ea ...` for them to check. Do not use `assert` as mandatory data validation or as a substitute for correctness reasoning.

## 11. Complete Java 17 program

Create a file with the exact name **`LoopInvariantDemo.java`**:

~~~java
public final class LoopInvariantDemo {
    private LoopInvariantDemo() {}

    static void requireInvariant(boolean condition) {
        if (!condition) {
            throw new IllegalStateException("loop invariant violated");
        }
    }

    static long prefixSum(int[] data, int limit) {
        long total = 0;
        for (int k = 0; k < limit; k++) {
            total += data[k];
        }
        return total;
    }

    static long sum(int[] data) {
        if (data == null) {
            throw new IllegalArgumentException("data must not be null");
        }

        long total = 0;
        for (int i = 0; i < data.length; i++) {
            // Invariant: total == sum of data[0..i-1].
            requireInvariant(total == prefixSum(data, i));
            System.out.println("sum entry i=" + i + " total=" + total);
            total += data[i];
        }

        requireInvariant(total == prefixSum(data, data.length));
        System.out.println("sum final=" + total);
        return total;
    }

    static int prefixMax(int[] data, int limit) {
        int result = data[0];
        for (int k = 1; k < limit; k++) {
            if (data[k] > result) {
                result = data[k];
            }
        }
        return result;
    }

    static int max(int[] data) {
        if (data == null || data.length == 0) {
            throw new IllegalArgumentException("requires nonempty array");
        }

        int best = data[0];
        for (int i = 1; i < data.length; i++) {
            // Invariant: best == max of data[0..i-1].
            requireInvariant(best == prefixMax(data, i));
            System.out.println("max entry i=" + i + " best=" + best);
            if (data[i] > best) {
                best = data[i];
            }
        }

        requireInvariant(best == prefixMax(data, data.length));
        System.out.println("max final=" + best);
        return best;
    }

    static int findFirst(int[] data, int target) {
        if (data == null) {
            throw new IllegalArgumentException("data must not be null");
        }

        for (int i = 0; i < data.length; i++) {
            // Invariant: data[k] != target for all 0 <= k < i.
            for (int k = 0; k < i; k++) {
                requireInvariant(data[k] != target);
            }
            System.out.println("scan i=" + i + " value=" + data[i]);
            if (data[i] == target) {
                return i;
            }
        }
        System.out.println("not found");
        return -1;
    }

    static int countdown() {
        int ticks = 0;
        for (int remaining = 3; remaining > 0; remaining--) {
            // Invariant: 0 <= remaining <= 3.
            requireInvariant(remaining >= 0 && remaining <= 3);
            System.out.println("remaining=" + remaining);
            ticks++;
        }
        return ticks;
    }

    public static void main(String[] args) {
        System.out.println("== sum ==");
        System.out.println("sum result=" + sum(new int[]{2, -1, 4, 3}));

        System.out.println("== max ==");
        System.out.println("max result=" + max(new int[]{-3, 5, 1, 7, 7}));

        try {
            max(new int[]{});
        } catch (IllegalArgumentException ex) {
            System.out.println("max empty=" + ex.getMessage());
        }

        System.out.println("== find first ==");
        int[] input = {4, 6, 2, 6};
        System.out.println("first 6=" + findFirst(input, 6));
        System.out.println("first 9=" + findFirst(input, 9));

        System.out.println("== termination ==");
        System.out.println("ticks=" + countdown());
    }
}
~~~

**Requirements:** JDK 17 or later, terminal in the directory containing `LoopInvariantDemo.java`. Uses only the JDK standard library; no Maven, Gradle, or preview features required.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 LoopInvariantDemo.java
java -cp . LoopInvariantDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\LoopInvariantDemo.java
java -cp . LoopInvariantDemo
~~~

### Exact expected stdout

~~~text
== sum ==
sum entry i=0 total=0
sum entry i=1 total=2
sum entry i=2 total=1
sum entry i=3 total=5
sum final=8
sum result=8
== max ==
max entry i=1 best=-3
max entry i=2 best=5
max entry i=3 best=5
max entry i=4 best=7
max final=7
max result=7
max empty=requires nonempty array
== find first ==
scan i=0 value=4
scan i=1 value=6
first 6=1
scan i=0 value=4
scan i=1 value=6
scan i=2 value=2
scan i=3 value=6
not found
first 9=-1
== termination ==
remaining=3
remaining=2
remaining=1
ticks=3
~~~

**Reading the output:**

1. `sum`: before each iteration, `total` equals the sum of the processed prefix; after the loop, the sum is 8.
2. `max`: `best` is the max of the examined elements; works correctly even with all-negative arrays; empty arrays are rejected.
3. `findFirst`: before each iteration checks that there is no match in the prefix before `i`; finds 6 at index 1 and returns immediately; 9 is absent so returns -1.
4. `countdown`: the bound invariant on `remaining` is preserved; the variant decreases from 3 to 0 so the loop terminates.
5. The `prefixSum`/`prefixMax`/prefix-checking loops serve for **verification in the demo**, increasing runtime cost. When optimizing, keep the invariant reasoning while removing redundant checks.

## 12. Common pitfalls

| Pitfall | Consequence | Fix |
|---|---|---|
| Calling `i < n` an invariant | It becomes false when the loop ends normally | Use `0 <= i <= n` for index bounds |
| Writing the invariant only as `sum >= 0` | False if the array has negatives; does not prove the sum | Use the prefix-sum statement |
| Assuming the invariant holds right after every statement | Can be false between body and update | Clearly designate the start-of-pass check point |
| Skipping the initialization step | Statement is not guaranteed before the first pass | Prove the empty / 1-element prefix case |
| Proving maintenance without connecting to the postcondition | Does not prove the final result yet | Combine the invariant with the stopping condition |
| Having an invariant without progress | Can still loop infinitely | Pick a decreasing variant and verify the update |
| Initializing max to 0 | Wrong for arrays with only negative numbers | Take the first element and handle empty arrays |
| Adding `continue` while keeping an incompatible old invariant | Invariant does not reflect skipped elements | Redefine the processed prefix / requirement |
| Using `break` and concluding as if `i=n` | Early exit has a different condition | Prove the `break`/`return` path separately |
| Checking the invariant with an auxiliary loop on every pass in production | Easily turns an `O(n)` algorithm into `O(n²)` | Use only in tests/debugging |
| Believing `assert` is always active | By default the JVM disables assertions | Use `-ea` in tests, never rely on assert for mandatory checks |
| Ignoring overflow in integer sums | Result can differ from the mathematical sum | Use a wide enough type or check for overflow |

## 13. Exercises with answers

### Exercise A — write the prefix sum invariant

~~~java
long total = 0;
for (int i = 0; i < data.length; i++) {
    total += data[i];
}
~~~

**Answer:** at the start of each pass, `0 <= i <= data.length` and `total` is the sum of `data[0..i-1]`. After the stopping condition `i=data.length`, the sum covers the entire array (assuming addition does not overflow).

### Exercise B — why is initializing max to 0 wrong?

~~~java
int[] data = {-8, -3, -10};
int best = 0; // Wrong if the problem is max of the entire array.
~~~

**Answer:** 0 is not an element of the array and is greater than all its values. Initialize `best=data[0]`, traverse from `i=1`; the right result is `-3`.

### Exercise C — invariant when finding the first element

~~~java
for (int i = 0; i < data.length; i++) {
    if (data[i] == target) return i;
}
return -1;
~~~

**Answer:** before pass `i`, no element in `data[0..i-1]` equals target. When target is encountered, `i` is the first position; when traversal completes, target is not in the array.

### Exercise D — does an invariant guarantee termination?

~~~java
int i = 0;
// while (i == 0) { /* does not change i */ }
~~~

**Answer:** the statement `i == 0` stays true, yet the loop can run forever. To prove termination, there must be a progressing variable and a reachable stopping condition.

### Exercise E — `continue` changes the summing goal

~~~java
int[] data = {3, -1, 4};
int total = 0;
for (int i = 0; i < data.length; i++) {
    if (data[i] < 0) continue;
    total += data[i];
}
System.out.println(total);
~~~

**Answer:** prints `7`. The appropriate invariant is “sum of **non-negative** elements processed so far”, not the sum of all prefix elements.

## 14. Checklist and conclusion

- [ ] Distinguish a loop invariant from the **loop continuation condition**.
- [ ] Clearly identify the **point** where the invariant must hold (start of each iteration).
- [ ] Prove **initialization**, **maintenance**, and **termination**.
- [ ] Write an invariant tied directly to the desired result, such as sum/max of the processed prefix.
- [ ] Combine the stopping condition with the invariant to deduce the result.
- [ ] Distinguish an invariant from a **loop variant** used to prove termination.
- [ ] Inspect `continue`, `break`, and `return` paths so state is not wrongly assumed.
- [ ] Consider empty arrays, boundary indices, negative numbers, and overflow.
- [ ] Know that debugging tools can verify invariants on test suites, but do not replace logical proof.
- [ ] Understand enabling assertions with `-ea`; do not rely on assert for mandatory validation.
- [ ] Run `LoopInvariantDemo.java` with Java 17+ and verify exact stdout.

**Conclusion:** A loop invariant is **the relationship preserved across every iteration** between accumulated state and the portion of data already processed. Designing a strong enough invariant, proving it holds at the start of a pass, maintaining it across body/update, and combining it with the stopping condition explains **why the algorithm is correct**, rather than merely showing an example that happens to run right.