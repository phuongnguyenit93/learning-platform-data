# `for` with initialization, condition, and update — Java 17+

## 1. What is the traditional `for` loop?

In Java, the traditional `for` (*basic for statement*) is suitable when you need to **initialize state**, **check a condition before each iteration**, and then **update state after the iteration**. Syntax:

~~~java
for (initialization; condition; update) {
    // loop body
}
~~~

Example counting from 0 to 2:

~~~java
for (int i = 0; i < 3; i++) {
    System.out.println("i=" + i);
}
~~~

**Exact expected stdout:**

~~~text
i=0
i=1
i=2
~~~

| Component | Example | Role |
|---|---|---|
| **Initialization** (*initialization*) | `int i = 0` | Runs **once** before the first iteration |
| **Condition** (*condition*) | `i < 3` | Checked **before each iteration**; must be `boolean` or an unboxable `Boolean` |
| **Update** (*update*) | `i++` | Runs **after the loop body**, before checking the next condition |
| **Loop body** (*body*) | `System.out.println(...)` | Runs when the condition is true |

The semicolons between the three parts in parentheses are **mandatory** even if a part is left empty. Do not confuse it with `for (Type item : collection)` (*enhanced for*), which has different syntax and purpose.

## 2. Exact execution order

For `for (int i = 0; i < 2; i++)`, the order is:

~~~text
Initialize i = 0 (once)
    ↓
Check i < 2
    ├── false → exit for
    └── true
          ↓
       Loop body
          ↓
       Update i++
          ↓
       Go back to check i < 2
~~~

~~~mermaid
flowchart TD
    A["Run initialization once"] --> B{"condition true?"}
    B -- "No" --> E["Exit for loop"]
    B -- "Yes" --> C["Run body"]
    C --> D["Run update"]
    D --> B
~~~

You can observe each step using logging methods:

~~~java
static int init() {
    System.out.println("init");
    return 0;
}

static boolean check(int i) {
    System.out.println("check " + i);
    return i < 2;
}

static int next(int i) {
    System.out.println("update " + i);
    return i + 1;
}

// In main:
for (int i = init(); check(i); i = next(i)) {
    System.out.println("body " + i);
}
~~~

**Exact expected stdout:**

~~~text
init
check 0
body 0
update 0
check 1
body 1
update 1
check 2
~~~

**Key point to remember:** After the last pass there is still an **update** step, and then **condition** is checked and returns false. When the condition is initially false, body and update **do not run**.

## 3. Initialization part: runs only once

The `initialization` part typically declares and initializes a counter variable:

~~~java
for (int index = 0; index < 4; index++) {
    System.out.println(index);
}
~~~

The counter variable can also be **declared beforehand**:

~~~java
int index = 0;
for (; index < 3; index++) {
    // Use the existing index variable.
}
System.out.println(index); // 3
~~~

In that case initialization is omitted, but **the first `;` must still be present**.

Java also allows declaring **multiple variables of the same type** in the initialization part:

~~~java
for (int left = 0, right = 6; left < right; left++, right--) {
    System.out.println(left + ":" + right);
}
~~~

**Exact expected stdout:**

~~~text
0:6
1:5
2:4
~~~

You cannot declare two different types in **the same declaration list**:

~~~java
// Invalid:
// for (int i = 0, long j = 3; i < 3; i++) { }
~~~

If variables of different types are needed, declare them before the `for`.

## 4. Condition part: boolean type, checked before each iteration

Example:

~~~java
int count = 0;
for (int i = 5; i < 5; i++) {
    count++;
}
System.out.println(count); // 0
~~~

Because `5 < 5` is false right at the start, there are no loop iterations.

Java has no “truthy” concept where non-zero numbers automatically become true:

~~~java
// Wrong: int cannot be used directly as a condition.
// for (int i = 3; i; i--) { }
~~~

Fix with an explicit boolean condition:

~~~java
for (int i = 3; i != 0; i--) {
    System.out.println(i);
}
~~~

**Exact expected stdout:**

~~~text
3
2
1
~~~

If the condition is a potentially null `Boolean`, Java will need **unboxing** during evaluation; null causes a `NullPointerException`. In basic loops, use primitive `boolean` or handle null intentionally.

## 5. Update part: runs after the body, not before the body

The update is usually `i++`, `i--`, `i += 2`, or a list of update expressions:

~~~java
for (int i = 0; i <= 6; i += 2) {
    System.out.println(i);
}
~~~

**Exact expected stdout:**

~~~text
0
2
4
6
~~~

If the update list has two expressions:

~~~java
for (int a = 0, b = 4; a < b; a++, b--) {
    System.out.println(a + "/" + b);
}
~~~

**Exact expected stdout:**

~~~text
0/4
1/3
~~~

Update expressions are executed **in order from left to right**. In the update position, `i++` and `++i` have the same effect on `i` when the expression result is unused, although in other contexts postfix and prefix can return different values.

**Not** every Java expression can be used arbitrarily in initializer/update: this list must consist of valid *statement expressions*, such as assignment, increment/decrement, method invocation, or object creation; you cannot put a bare `i + 1` instead of `i++`.

## 6. All three parts can be omitted, but termination must be controlled

One or more parts of `for` can be left empty:

~~~java
int cursor = 0;
for (; cursor < 3;) {
    System.out.println(cursor);
    cursor++; // Update inside the body.
}
~~~

**Exact expected stdout:**

~~~text
0
1
2
~~~

If the condition is omitted completely, it is treated as **always true**:

~~~java
int attempts = 0;
for (;;) {
    attempts++;
    if (attempts == 3) {
        break;
    }
}
System.out.println(attempts); // 3
~~~

`for (;;)` is a syntactic infinite loop; to have an exit point, you must design a `break`, `return`, `throw`, or other stopping mechanism.

**Risk:** `for (int i = 0; i < 3; )` where the body does not increment `i` may never terminate if there is no other exit path. Leaving the update empty should only be done when the mechanism changing the condition is in a clear location.

## 7. How do `break` and `continue` affect update?

In **basic for**:

- `break;` immediately exits the loop; the update part of the interrupted iteration does not run.
- `continue;` skips the rest of the body, but **still runs the `for` update**, and then checks the condition for the next iteration.
- `return` exits the method; it does not continue the update of that loop.
- If an exception causes the loop to exit, the update also does not run automatically like a `finally` block.

~~~java
for (int i = 0; i < 5; i++) {
    if (i == 2) {
        System.out.println("continue=" + i);
        continue;
    }
    if (i == 4) {
        System.out.println("break=" + i);
        break;
    }
    System.out.println("visit=" + i);
}
~~~

**Exact expected stdout:**

~~~text
visit=0
visit=1
continue=2
visit=3
break=4
~~~

After `continue=2`, the `i++` update still happens, so the next pass is 3. After `break=4`, the loop terminates immediately.

**Distinction from `while`:** when manually placing `i++` at the end of a `while` body, an earlier `continue` can skip the increment and cause an infinite loop. With traditional `for`, the update in the third part still executes after a normal `continue`.

## 8. Counter variable scope: declare inside or outside `for`?

A variable declared in `ForInit` can be used in the condition, update part, and body of **that** loop itself; it is no longer in scope after the loop:

~~~java
for (int i = 0; i < 3; i++) {
    System.out.println(i);
}
// System.out.println(i); // Does not compile: i is out of scope.
~~~

If the application needs to know the final value after the loop, declare the variable **before** `for`:

~~~java
int index = 0;
for (; index < 3; index++) {
    // Can use index here.
}
System.out.println(index); // 3.
~~~

Do not redeclare a local variable with the same name while scopes overlap. A counter variable being modified in `update` is also not **effectively final** to be captured directly by a lambda; you can copy its value into a local variable on each iteration if needed.

In this lesson, scope is what you need to remember to use the three `for` parts properly. The **counter variable lifecycle** lesson goes deeper into re-initialization timing, `continue`/`break`, nested scopes, and tracing variables iteration by iteration.


## 9. Iterating arrays with proper bounds

An array of length `n` only has valid indices `0..n-1`:

~~~java
int[] values = {4, 7, 9};
int total = 0;
for (int i = 0; i < values.length; i++) {
    total += values[i];
}
System.out.println(total); // 20.
~~~

The right condition for **reading elements** is `i < values.length`, not `i <= values.length`: on the `i == length` pass, accessing `values[i]` will throw `ArrayIndexOutOfBoundsException`. Conversely, when a problem genuinely needs to **include** the endpoint, `<=` can be completely right.

Reverse iteration from the end of an array is commonly written `for (int i = values.length - 1; i >= 0; i--)`; an empty array will run 0 iterations. The initial condition, update step, and ending bound must always be compatible. The **off-by-one errors** lesson analyzes half-open intervals `[start,end)`, empty array access, and boundary testing in depth.


## 10. Nested `for`: the inner loop's initializer runs again

~~~java
int cells = 0;
for (int row = 0; row < 2; row++) {
    for (int col = 0; col < 3; col++) {
        cells++;
    }
}
System.out.println(cells); // 6.
~~~

Here the outer loop has 2 iterations; each iteration **re-initializes `col = 0`**, and then the inner loop runs 3 iterations. The total is `2 × 3 = 6`. If the inner loop bound depends on `row`, you cannot always multiply two fixed sizes: you must sum the inner iterations of each outer iteration.

With a constant-cost body and independent bounds `n`, `m`, the complexity is `O(nm)`. The **nested loops** lesson will trace each pair of counters, traverse jagged 2D arrays, and distinguish labeled `break`/`continue`.


## 11. Choosing syntax for clear intent

| Task | Usually readable choice |
| --- | --- |
| Need an index or explicit counter changes | Basic `for (init; condition; update)` |
| Only need to retrieve each element value in sequence | Enhanced `for (Type value : array)` |
| Iteration count depends on external events/state | `while` |
| Must try the body at least once before checking | `do-while` |

~~~java
int[] numbers = {4, 7, 9};
for (int i = 0; i < numbers.length; i++) {
    System.out.println("index=" + i + ",value=" + numbers[i]);
}
for (int value : numbers) {
    System.out.println("value=" + value);
}
~~~

Enhanced `for` does not expose the three parts of basic `for`; if you need access by index, use basic `for`. For collections, modifying structure while iterating also involves the iterator's contract. No loop type is universally faster than the others. The **choosing a loop type** lesson will compare condition-check points and practical scenarios.


## 12. Complete Java 17 program

Create a file **`BasicForThreePartsDemo.java`** with the exact contents:

~~~java
public final class BasicForThreePartsDemo {
    private BasicForThreePartsDemo() {}

    static int init() {
        System.out.println("init");
        return 0;
    }

    static boolean check(int i) {
        System.out.println("check " + i);
        return i < 2;
    }

    static int update(int i) {
        System.out.println("update " + i);
        return i + 1;
    }

    public static void main(String[] args) {
        System.out.println("== order ==");
        for (int i = init(); check(i); i = update(i)) {
            System.out.println("body " + i);
        }

        System.out.println("== basic ==");
        for (int i = 0; i < 3; i++) {
            System.out.println("i=" + i);
        }

        System.out.println("== zero iterations ==");
        int count = 0;
        for (int i = 4; i < 4; i++) {
            count++;
        }
        System.out.println("count=" + count);

        System.out.println("== two variables ==");
        for (int left = 0, right = 6;
                left < right; left++, right--) {
            System.out.println("pair=" + left + ":" + right);
        }

        System.out.println("== continue and break ==");
        for (int i = 0; i < 5; i++) {
            if (i == 2) {
                System.out.println("continue=" + i);
                continue;
            }
            if (i == 4) {
                System.out.println("break=" + i);
                break;
            }
            System.out.println("visit=" + i);
        }

        System.out.println("== array ==");
        int[] numbers = {4, 7, 9};
        int total = 0;
        for (int i = 0; i < numbers.length; i++) {
            total += numbers[i];
        }
        System.out.println("sum=" + total);

        System.out.println("== nested ==");
        int cells = 0;
        for (int r = 0; r < 2; r++) {
            for (int c = 0; c < 3; c++) {
                cells++;
            }
        }
        System.out.println("cells=" + cells);

        System.out.println("== omitted parts ==");
        int cursor = 0;
        for (; cursor < 3;) {
            System.out.println("cursor=" + cursor);
            cursor++;
        }

        int attempts = 0;
        for (;;) {
            attempts++;
            if (attempts == 3) {
                break;
            }
        }
        System.out.println("infinite break=" + attempts);

        System.out.println("== outer variable ==");
        int index = 0;
        for (; index < 3; index++) {
            // Body can be empty.
        }
        System.out.println("after i=" + index);
    }
}
~~~

**Requirements:** JDK 17 or later, terminal in the directory containing the file; no libraries outside the JDK, Maven, or Gradle.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 BasicForThreePartsDemo.java
java -cp . BasicForThreePartsDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\BasicForThreePartsDemo.java
java -cp . BasicForThreePartsDemo
~~~

### Exact expected stdout

~~~text
== order ==
init
check 0
body 0
update 0
check 1
body 1
update 1
check 2
== basic ==
i=0
i=1
i=2
== zero iterations ==
count=0
== two variables ==
pair=0:6
pair=1:5
pair=2:4
== continue and break ==
visit=0
visit=1
continue=2
visit=3
break=4
== array ==
sum=20
== nested ==
cells=6
== omitted parts ==
cursor=0
cursor=1
cursor=2
infinite break=3
== outer variable ==
after i=3
~~~

Verification: `init` once; `check` runs before every body and also on the final failed check; `update` runs after normal/continue body; the two-variable pair ends when `left == right`; array sums `4+7+9=20`; nested loops have `2×3=6`; the `for (;;)` loop exits via `break`.

## 13. Common mistakes and fixes

| Mistake | Consequence | Fix |
|---|---|---|
| Confusing init as running every pass | Misunderstanding order or cost | Init runs only **once** |
| Confusing update as running before body | Displayed values are off | Order: init → condition → body → update |
| `i <= array.length` when reading `array[i]` | Out-of-bounds access past end of array | `i < array.length` |
| `for (int i=0; i; i++)` | Fails to compile, `int` condition | Use a boolean expression |
| Omitting update while body also leaves variable unchanged | Risk of infinite loop | Add an update or exit path |
| Using `i++` when intending to count down | Wrong iteration direction | Use `i--` with an appropriate condition |
| Thinking `continue` skips update in `for` | Wrong control flow | Basic `for` still executes update |
| Thinking `break` still runs update before exiting | Wrong final value | `break` skips update |
| Using `i` after the loop when declared in init | Out of scope | Declare `i` outside the loop if needed |
| `for(int i=0, long j=0;...)` | Invalid syntax in declaration part | Use the same type or declare beforehand |
| Writing `i + 1` in update | Not a valid statement expression | Write `i++`, `i += 1`, or `i = i + 1` |
| Incrementing an `int` variable up to `Integer.MAX_VALUE` without considering overflow | Can overflow and loop wrongly | Choose suitable condition/type, check bounds |
| Forcing a three-part `for` when only reading elements | Verbose code, prone to index bugs | Consider enhanced `for` |
| Creating `for (...); { ... }` accidentally | `;` ends the loop with an empty body | Remove the stray `;` before the block |

## 14. Exercises with answers

### Exercise A — print even numbers from 0 to 8

~~~java
for (int i = 0; i <= 8; i += 2) {
    System.out.println(i);
}
~~~

**Expected stdout:**

~~~text
0
2
4
6
8
~~~

### Exercise B — count down from 3 to 1

~~~java
for (int i = 3; i >= 1; i--) {
    System.out.println(i);
}
~~~

**Expected stdout:**

~~~text
3
2
1
~~~

### Exercise C — how many iterations?

~~~java
int count = 0;
for (int i = 10; i < 10; i++) {
    count++;
}
System.out.println(count);
~~~

**Answer:** `0`. The condition is false before the first body.

### Exercise D — find the bug when iterating an array

~~~java
int[] data = {1, 2, 3};
// for (int i = 0; i <= data.length; i++) {
//     System.out.println(data[i]);
// }
~~~

**Answer:** change `i <= data.length` to `i < data.length`. The last index is 2, not 3.

### Exercise E — does `continue` increment `i`?

~~~java
for (int i = 0; i < 4; i++) {
    if (i == 1) continue;
    System.out.println(i);
}
~~~

**Expected stdout:**

~~~text
0
2
3
~~~

For `i == 1`, `continue` transfers to the **update `i++`** step, and then the condition is re-evaluated. It does not get stuck at 1.

### Exercise F — two variables in the same `for`

~~~java
for (int a = 0, b = 5; a < b; a++, b--) {
    System.out.println(a + ":" + b);
}
~~~

**Expected stdout:**

~~~text
0:5
1:4
2:3
~~~

At the next update step, `a == 3`, `b == 2`, and the condition `a < b` is false.

## 15. Checklist and conclusion

- [ ] Can write the `for (init; condition; update) { body }` construct.
- [ ] Remember init runs **once**, condition **before each iteration**, update **after body**.
- [ ] Understand the loop can run **0 iterations** when the initial condition is false.
- [ ] Know the condition must be `boolean`/`Boolean`, not truthy/falsy integers.
- [ ] Can use multiple variables of the same type in init and multiple update expressions.
- [ ] Know how to omit a part while keeping both `;` semicolons.
- [ ] Recognize `for (;;)` requires designing an exit mechanism.
- [ ] Distinguish `continue` still running update from `break` exiting immediately.
- [ ] Understand the scope of a counter variable declared inside init.
- [ ] Avoid off-by-one errors with `i < array.length`.
- [ ] Know when to use basic `for`, enhanced `for`, or `while`.
- [ ] Run `BasicForThreePartsDemo.java` with `javac`/`java` on JDK 17+ and verify exact stdout.

**Conclusion:** In Java 17+, the three parts of basic `for` clearly express **initial setup**, **continuation condition**, and **post-iteration change**. To avoid bugs, verify the `init → condition → body → update` order, ensure the condition can terminate, and pay attention to variable scope and boundary values.