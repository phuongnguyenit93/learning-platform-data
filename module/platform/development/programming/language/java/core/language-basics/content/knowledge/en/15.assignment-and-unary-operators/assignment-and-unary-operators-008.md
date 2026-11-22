# Avoiding Multiple Increments or Decrements on the Same Variable in One Expression — Java 17+

## 1. Objective

In Java, the `++` operator increases a numeric variable by 1, and `--` decreases it by 1. Both **return an expression value and modify the variable**. When the same variable is incremented/decremented and read multiple times in a single expression, the program can produce a valid result yet become very hard to read and easy to modify incorrectly.

~~~java
int i = 1;
int result = i++ + ++i;
System.out.println(result); // 4
System.out.println(i);      // 3
~~~

**Java 17 clearly defines this result**; it is not “undefined behavior”. However, the reader must track multiple intermediate states of `i` within a single line; therefore, **this style of expression should not be used in business code**.

After this lesson, you should be able to: distinguish postfix/prefix; predict evaluation order in Java; recognize pitfalls with assignment, method calls, arrays, and conditions; and rewrite expressions with multiple side effects into easy-to-inspect steps.

## 2. Quick Recap of Semantics Needed to Spot Hard-to-Read Code

Postfix `i++`/`i--` supplies the **old value** and updates the variable; prefix `++i`/`--i` supplies the **new value** after updating. All of this happens during the current evaluation. This is the foundational material from the lesson “Prefix and Postfix Increment and Decrement in Java”; the skill of tracking both values separately was also practiced in the immediately preceding lesson.

This lesson focuses on **problems that arise when one variable is updated multiple times in the same expression**: evaluation order, method arguments, array access, short-circuiting, exceptions, and how to refactor without changing behavior. Simple `i++` in a `for` loop update or a standalone `i++;` statement remains clear and does not need to be avoided.

## 3. Why Does `i++ + ++i` Produce 4?

~~~java
int i = 1;
int result = i++ + ++i;
~~~

Java evaluates the operands of `+` **from left to right**:

| Step | Operation | Operand Value | `i` After Step |
|---|---|---:|---:|
| 1 | `i++` | 1 (old value) | 2 |
| 2 | `++i` | 3 (new value) | 3 |
| 3 | Add `1 + 3` | 4 | 3 |

Thus `result == 4` and `i == 3`.

Another easily confused example:

~~~java
int j = 1;
int sum = j++ + j++;
System.out.println(sum); // 3 = 1 + 2
System.out.println(j);   // 3
~~~

**Do not conclude this result is undefined.** Java specifies the evaluation order; the real risk is that calculations with multiple side effects are **hard to predict by eye, hard to review, and hard to maintain**. In particular, do not apply intuition from other languages to explain Java.

### Precedence Does Not Mean Everything Evaluates Out of Order

For example, in `a++ + b++ * c++`: multiplication is **grouped** before addition by precedence, yet Java still evaluates operands according to its deterministic left-to-right rules. To avoid lengthy reasoning, **separate the increments into clear statements**.

## 4. The `i = i++` Trap: Increment Then Overwrite with the Old Value

~~~java
int i = 5;
i = i++;
System.out.println(i); // 5
~~~

Execution flow:

1. The postfix expression `i++` returns **5**, while incrementing `i` to **6**.
2. The outer assignment `i = ...` writes **5** back into `i`.
3. Finally `i` remains **5**.

Compare:

~~~java
int a = 5;
a++;           // a=6

int b = 5;
b = ++b;       // b=6, though redundant
~~~

**Correct approach:** if the intent is to increment, write `i++;` or `i += 1;`. If the intent is to assign, compute the desired value first and then `i = value;`. Do not unnecessarily combine both actions on the same variable.

## 5. Re-Reading a Variable After Incrementing in the Same Expression

~~~java
int i = 3;
int value = i++ + i;

System.out.println(value); // 7 = 3 + 4
System.out.println(i);     // 4
~~~

The left operand supplies the old value `3` and `i` becomes `4`; the right operand reads `4`.

Although the code follows clear rules, it can be written as:

~~~java
int i = 3;
int oldValue = i;
i++;
int currentValue = i;
int value = oldValue + currentValue;
~~~

The step-by-step version is slightly longer, yet **explicitly shows which variable holds the old value and which holds the new value**. If the business logic does not require both, simplify further.

## 6. Multiple `++` Operators in Method Arguments

Java evaluates **method call arguments from left to right**, before executing the method body:

~~~java
static void show(int left, int right) {
    System.out.println(left + "," + right);
}

// Inside main:
int i = 1;
show(i++, ++i); // Prints "1,3"; i ends at 3
~~~

Order:

1. First argument `i++`: passes `1`, `i` becomes 2.
2. Second argument `++i`: `i` becomes 3, passes `3`.
3. The method receives `(1, 3)`.

**Better written as:**

~~~java
int i = 1;
int first = i;
i++;
i++;
int second = i;
show(first, second);
~~~

This preserves the passed values and state update order in the example, while sparing the reader from mentally tracing argument order.

If a method takes multiple complex expressions involving I/O or state mutations, separating them into temporary variables also makes it explicit **which operation happens first**.

## 7. Where Are Array Indices Being Modified?

~~~java
int[] items = {10, 20, 30};
int index = 0;
int total = items[index++] + items[index++];

System.out.println(total); // 30 = items[0] + items[1]
System.out.println(index); // 2
~~~

With two `index++` operations, Java uses index **0** and then **1**. Do not mislead the reader into thinking the expression reads the same element twice.

Maintainable version:

~~~java
int first = items[index];
index++;
int second = items[index];
index++;
int total = first + second;
~~~

A single `array[index++]` may fit cleanly in a straightforward sequential algorithm; **the risk rises sharply when the same index variable is used multiple times in one expression**.

Notably:

~~~java
int[] values = {10, 20};
int index = 0;
values[index++]++;  // values[0] becomes 11, index becomes 1
~~~

Here there are **two distinct side effects**: incrementing `index` to select an element and incrementing the **array element** itself. If you need to explain the logic to teammates, separating the steps is usually much clearer:

~~~java
int selectedIndex = index;
index++;
values[selectedIndex]++;
~~~

## 8. Short-Circuiting Can Prevent an Increment from Running

With `&&`, when the left-hand side is `false`, Java **does not evaluate** the right-hand side. With `||`, when the left-hand side is `true`, Java likewise skips the right-hand side:

~~~java
int i = 0;
boolean result = false && (i++ > 0);

System.out.println(result); // false
System.out.println(i);      // 0: i++ does not run
~~~

If the first condition is true:

~~~java
int i = 0;
boolean result = true && (i++ == 0);

System.out.println(result); // true
System.out.println(i);      // 1
~~~

Contrast with `&` on `boolean`: `&` **evaluates both operands**, so:

~~~java
int i = 0;
boolean result = false & (i++ > 0);

System.out.println(result); // false
System.out.println(i);      // 1
~~~

| Operator | Can Right-Hand Side Be Skipped? | Effect on `i++` on the Right-Hand Side |
|---|---|---|
| `&&` | Yes, when left-hand side is false | May not increment |
| `||` | Yes, when left-hand side is true | May not increment |
| `&` on boolean | No | Always evaluates right-hand side when reached |
| `|` on boolean | No | Always evaluates right-hand side when reached |

**Recommendation:** boolean conditions should express **conditions**, while state updates belong in separate statements, except in algorithmic cases that genuinely require the side effect and are clearly explained.

## 9. Exceptions Can Leave Partially Modified State

~~~java
int count = 0;
int divisor = 0;

try {
    int answer = count++ + 10 / divisor;
    System.out.println(answer);
} catch (ArithmeticException ex) {
    System.out.println(count); // 1
}
~~~

`count++` has already been evaluated, so `count` increments from 0 to 1 **before** integer division by 0 throws `ArithmeticException`. Catching the exception does not automatically undo the increment.

If the entire operation must either **all succeed or all fail**, **validate before mutating state** or use an appropriate transaction/rollback mechanism; parentheses and `try/catch` do not provide atomicity.

## 10. Use `++`/`--` in the Right Places; Do Not Over-Avoid Them

**Appropriate to use** when the update intent is obvious:

~~~java
int count = 0;
count++;
count--;
~~~

Simple loops:

~~~java
for (int i = 0; i < 3; i++) {
    System.out.println(i);
}
~~~

However, avoid:

~~~java
// Hard to read: multiple operations on the same variable in one expression
// int result = i++ + ++i - i--;

// Hard to audit: mutating variable while building arguments
// send(i++, ++i);
~~~

Parentheses like `(i++) + (++i)` can clarify **grouping** but **do not eliminate side effects**. Adding parentheses does not solve the problem of “too many state mutations in one expression”.

## 11. How to Refactor Without Changing Behavior

Before:

~~~java
int i = 1;
int result = i++ + ++i;
~~~

After:

~~~java
int i = 1;

int left = i;  // Capture the value that i++ would return
i++;          // Perform postfix increment

i++;          // Perform the increment of ++i
int right = i; // Capture the new value

int result = left + right;
~~~

Both versions yield `result = 4`, `i = 3`. The second version allows setting breakpoints between updates.

When changing real code, preserve these invariants:

1. **Preserve the evaluation order** of methods/operands with side effects.
2. **Preserve the number of updates** unless intentionally changing the algorithm.
3. Distinguish the **old value** and **new value** of prefix/postfix.
4. Do not arbitrarily move statements across `&&`, `||`, `?:`, `if` branches, or locations that may throw exceptions.
5. Write tests verifying **both the expression result and the post-expression variable state**.

If multiple increments/decrements are not truly necessary, the best approach is to **reduce the number of side effects** rather than merely copying them across multiple lines.

## 12. Related Technical Pitfalls

| Case | Risk | How to Handle |
|---|---|---|
| `i++ + ++i` | Hard to track old/new values | Separate reads and increments |
| `i++ + i++` | Reads and updates the same variable twice | Use intermediate variables |
| `i = i++` | Overwrites the post-increment value | Use `i++;` alone if you want to increment |
| `show(i++, ++i)` | Second argument reads updated state | Compute arguments step by step |
| `array[i++] + array[i++]` | Hard to track indices/array bounds | Separate indices and check bounds |
| `false && (i++ > 0)` | `i++` does not run | Do not rely on conditionally skipped side effects |
| `false & (i++ > 0)` | `i++` still runs | Understand `&` does not short-circuit |
| `byte b = 127; b++;` | Overflow/narrowing turns `b` into -128 | Choose a wider type or check range |
| `Integer n = null; n++;` | Null unboxing causes `NullPointerException` | Check for null or use primitive |
| `final int n = 1; n++;` | Cannot reassign a `final` variable | Design a separate mutable variable |
| `sharedCount++` across threads | Read-compute-write is not atomic | Synchronize or use `AtomicInteger` |

**Overflow:** `int i = Integer.MAX_VALUE; i++;` produces `Integer.MIN_VALUE` per Java rules, without throwing an exception by default. If business logic cannot accept overflow, use `Math.incrementExact(i)` to check.

**Wrappers:** `Integer n = 1; n++;` performs unboxing, addition, then boxing/reference reassignment; it does not mutate the contents of the immutable `Integer` object.

**Multithreading:** Java has a well-defined evaluation order within a single thread, but `i++` is **not atomic** when multiple threads update concurrently. This is a synchronization concern independent of whether the expression is long or short.

## 13. Standalone Runnable Java 17 Program

Create a file named **`IncrementDecrementClarityDemo.java`**:

~~~java
public final class IncrementDecrementClarityDemo {
    private IncrementDecrementClarityDemo() {}

    static void show(int left, int right) {
        System.out.println("show=" + left + "," + right);
    }

    public static void main(String[] args) {
        int x = 4;
        int post = x++;
        int pre = ++x;
        System.out.println("basic: post=" + post
                + ", pre=" + pre + ", x=" + x);

        int a = 1;
        int mixed = a++ + ++a;
        System.out.println("mixed: value=" + mixed + ", a=" + a);

        int b = 1;
        int twicePost = b++ + b++;
        System.out.println("twice post: value=" + twicePost + ", b=" + b);

        int c = 5;
        c = c++;
        System.out.println("self assign: c=" + c);

        int d = 5;
        d = ++d;
        System.out.println("prefix assign: d=" + d);

        int e = 3;
        int readAfterPost = e++ + e;
        System.out.println("read after post: value=" + readAfterPost
                + ", e=" + e);

        int[] items = {10, 20, 30};
        int index = 0;
        int sum = items[index++] + items[index++];
        System.out.println("array: sum=" + sum + ", index=" + index);

        int[] values = {10, 20};
        int nextIndex = 0;
        values[nextIndex++]++;
        System.out.println("array update: first=" + values[0]
                + ", index=" + nextIndex);

        int m = 1;
        show(m++, ++m);
        System.out.println("after args: m=" + m);

        int j = 0;
        boolean skipped = false && (j++ > 0);
        System.out.println("short circuit: result=" + skipped
                + ", j=" + j);

        boolean evaluated = true && (j++ == 0);
        System.out.println("evaluated: result=" + evaluated
                + ", j=" + j);

        boolean eager = false & (j++ == 1);
        System.out.println("eager &: result=" + eager + ", j=" + j);

        int k = 0;
        int zero = 0;
        try {
            int result = k++ + 10 / zero;
            System.out.println(result);
        } catch (ArithmeticException ex) {
            System.out.println("exception: k=" + k);
        }

        int overflow = Integer.MAX_VALUE;
        overflow++;
        System.out.println("overflow: " + overflow);

        int clear = 1;
        int left = clear;
        clear++;
        clear++;
        int right = clear;
        int separated = left + right;
        System.out.println("separated: value=" + separated
                + ", final=" + clear);
    }
}
~~~

**Requirements:** JDK 17 or later; terminal opened in the directory containing the file. No libraries outside the JDK.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 IncrementDecrementClarityDemo.java
java -cp . IncrementDecrementClarityDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\IncrementDecrementClarityDemo.java
java -cp . IncrementDecrementClarityDemo
~~~

**Exact expected stdout:**

~~~text
basic: post=4, pre=6, x=6
mixed: value=4, a=3
twice post: value=3, b=3
self assign: c=5
prefix assign: d=6
read after post: value=7, e=4
array: sum=30, index=2
array update: first=11, index=1
show=1,3
after args: m=3
short circuit: result=false, j=0
evaluated: result=true, j=1
eager &: result=false, j=2
exception: k=1
overflow: -2147483648
separated: value=4, final=3
~~~

### Key Result Takeaways

- `post=4` and `pre=6` prove postfix uses the old value and prefix uses the new value.
- `mixed=4`, `a=3`: Java evaluates left-to-right, with no undefined behavior.
- `twice post=3`: two consecutive postfix increments yield 1 and 2.
- `c = c++` overwrites the increment; `d = ++d` yields 6 but is redundant.
- `array` and `show`: later array indices/arguments see the already-updated state.
- `false && ...` skips `j++`; `false & ...` still executes `j++`.
- Division by 0 happens after `k++`; catching the exception does not roll back `k`.
- The `separated` lines provide a readable step-by-step alternative that preserves the exact same result and state as `a++ + ++a`.

## 14. Exercises with Answers

### Exercise A — Two Postfix Increments

~~~java
int i = 2;
int sum = i++ + i++;
System.out.println(sum);
System.out.println(i);
~~~

**Answer:**

~~~text
5
4
~~~

The operands return 2 and 3 respectively, while `i` increments to 4.

### Exercise B — Mixing Postfix and Prefix Decrements

~~~java
int n = 5;
int value = n-- + --n;
System.out.println(value);
System.out.println(n);
~~~

**Answer:**

~~~text
8
3
~~~

`n--` returns 5 then `n` becomes 4; `--n` decrements `n` to 3 and returns 3.

### Exercise C — Assignment Overwriting Increment

~~~java
int x = 9;
x = x++;
System.out.println(x);
~~~

**Answer:** `9`. The outer assignment overwrites the new value with the old value returned by `x++`.

### Exercise D — Array Indices

~~~java
int[] a = {4, 8, 12};
int i = 0;
int sum = a[i++] + a[i++];
System.out.println(sum);
System.out.println(i);
~~~

**Answer:**

~~~text
12
2
~~~

### Exercise E — Short-Circuiting

~~~java
int n = 0;
boolean result = true || (n++ > 0);
System.out.println(result);
System.out.println(n);
~~~

**Answer:**

~~~text
true
0
~~~

The left-hand side `true` causes `||` to skip the entire right-hand side.

### Exercise F — Rewriting to Avoid Multiple Side Effects

Given:

~~~java
int i = 1;
int result = i++ + ++i;
~~~

**One semantics-preserving answer:**

~~~java
int i = 1;
int left = i;
i++;
i++;
int right = i;
int result = left + right;
~~~

In the end `result = 4` and `i = 3`. If incrementing twice is not actually needed, redesign the formula rather than preserving a pointless chain of side effects.

## 15. Checklist and Conclusion

- [ ] Know that `i++` returns the old value and `++i` returns the new value; `--` follows the same rule.
- [ ] Distinguish **expression value** from **post-side-effect state**.
- [ ] Know that Java 17 has deterministic evaluation order within a thread.
- [ ] Can explain `i++ + ++i` and `i++ + i++` without calling them undefined.
- [ ] Recognize `i = i++` as an overwrite trap.
- [ ] Avoid nesting multiple updates to the same variable inside arithmetic, arguments, or array accesses unnecessarily.
- [ ] Know that `&&` and `||` can skip increments on the right-hand side.
- [ ] Know that side effects that already occurred are not automatically rolled back when an exception is thrown.
- [ ] Know that `++` can overflow or cause an NPE with nullable wrappers.
- [ ] Do not treat `++` as atomic when multiple threads write concurrently.
- [ ] Know how to extract temporary variables, preserve operation order, and test both the result and the state.
- [ ] Run `IncrementDecrementClarityDemo.java` with `javac`/`java` on JDK 17+, matching stdout exactly.

**Conclusion:** Multiple `++`/`--` operations on the same variable in one expression **do not make Java non-deterministic**, yet they force readers to mentally simulate multiple intermediate states, easily leading to bugs and faulty refactoring. Reserve `++`/`--` for clear update operations, **separate side effects out of calculations** when a variable is read/written multiple times, and use tests to verify both the computed value and the final state.