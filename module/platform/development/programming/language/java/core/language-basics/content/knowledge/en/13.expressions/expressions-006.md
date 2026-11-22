# Left-to-Right Evaluation of Operands and Arguments — Java 17+

In Java, **evaluation order** determines when sub-expressions are executed. For operands of ordinary operations and arguments of method invocations, Java mandates **left-to-right evaluation**. This rule is especially important when a sub-expression invokes a method, mutates a variable, reads an array, or throws an exception.

~~~java
int result = first() + second() * third();
~~~

Even though `*` has higher **precedence** than `+`, the calls are evaluated in the order `first()`, `second()`, `third()`. Multiplication still belongs to the right-hand sub-expression of addition. **Precedence determines grouping; evaluation order determines execution timing.**

> Scope: evaluation rules for Java 17 expressions. Do not infer that **every operand/branch** is forced to run; `&&`, `||`, `?:`, and thrown exceptions can cause the remaining parts to be skipped.

## 1. Distinguishing Three Concepts

| Concept | Question answered | Example |
| --- | --- | --- |
| **Precedence** | Which operator binds more tightly? | `a + b * c` groups as `a + (b * c)` |
| **Associativity** | How are operators at the same level grouped? | `a - b - c` groups as `(a - b) - c` |
| **Evaluation order** | Which sub-expression is evaluated first? | In `f() + g() * h()`, calls `f()`, then `g()`, then `h()` |

For an expression with method calls:

~~~text
                       +
                      / \
                   f()   *
                        / \
                      g() h()

Grouping tree:  f() + (g() * h())
Call evaluation order: f() -> g() -> h()
~~~

The expression tree describes **value dependencies**, not a schedule calling functions in highest-precedence operator order.

## 2. Core Rules and Exceptions

- For **ordinary binary operators**, Java evaluates the left operand before the right operand. The left operand's value is retained for use after evaluating the right operand, even if the right side modifies a related variable.
- For **method invocations**, the receiver selection expression (if any) is evaluated according to invocation rules, then the **arguments** are evaluated from left to right; only then is the method invoked.
- If an operand or argument **completes abruptly**—for example, throws an exception—parts to be evaluated **afterward** do not continue running.
- For `&&` and `||`, the right operand is evaluated only when needed to determine the result; for `?:`, only one of the two result branches is selected.
- For `&` and `|` on `boolean`, **both operands** are evaluated when no exception occurs; they lack the short-circuit behavior of `&&` and `||`.

**Do not write code relying on hidden side effects inside long expressions.** Even though Java specifies the order, splitting steps usually makes code easier for readers to follow.

## 3. Complete Java 17+ Demo

Create a UTF-8 file named **`LeftToRightDemo.java`**:

~~~java
public class LeftToRightDemo {
    static int mark(String label, int value) {
        System.out.println("visit=" + label);
        return value;
    }

    static boolean check(String label, boolean value) {
        System.out.println("visit=" + label);
        return value;
    }

    static int add(int left, int right) {
        return left + right;
    }

    static int digits(int hundreds, int tens, int units) {
        return hundreds * 100 + tens * 10 + units;
    }

    static class Box {
        private final int base;

        Box(int base) {
            this.base = base;
        }

        int addToBase(int first, int second) {
            return base + first + second;
        }
    }

    static Box makeReceiver() {
        System.out.println("visit=receiver");
        return new Box(10);
    }

    static int fail() {
        System.out.println("visit=failure");
        throw new IllegalStateException("stop");
    }

    public static void main(String[] args) {
        System.out.println("== binary ==");
        int binary = mark("left", 2)
                + mark("middle", 3) * mark("right", 4);
        System.out.println("binary=" + binary);

        System.out.println("== arguments ==");
        int arguments = digits(
                mark("arg-1", 1),
                mark("arg-2", 2),
                mark("arg-3", 3));
        System.out.println("arguments=" + arguments);

        System.out.println("== nested ==");
        int nested = add(
                mark("outer", 4),
                add(mark("inner-left", 5), mark("inner-right", 6)));
        System.out.println("nested=" + nested);

        System.out.println("== receiver ==");
        int receiverTotal = makeReceiver().addToBase(
                mark("method-1", 2),
                mark("method-2", 3));
        System.out.println("receiverTotal=" + receiverTotal);

        System.out.println("== snapshot ==");
        int current = 10;
        int snapshot = current + (current = 20);
        System.out.println("snapshot=" + snapshot + ",current=" + current);

        int counter = 1;
        int captured = digits(counter++, counter++, counter++);
        System.out.println("captured=" + captured + ",counter=" + counter);

        System.out.println("== short-circuit ==");
        boolean andResult = false && check("and-skipped", true);
        System.out.println("and=" + andResult);

        boolean orResult = true || check("or-skipped", false);
        System.out.println("or=" + orResult);

        boolean eagerAnd = false & check("and-eager", true);
        System.out.println("eagerAnd=" + eagerAnd);

        int selected = true
                ? mark("selected", 7)
                : mark("not-selected", 8);
        System.out.println("conditional=" + selected);

        System.out.println("== arrays ==");
        int[] values = {10, 20, 30};
        int index = 0;
        int arraySum = values[index++] + values[index++];
        System.out.println("arraySum=" + arraySum + ",index=" + index);

        System.out.println("== strings ==");
        String concat = "" + mark("concat-1", 1) + mark("concat-2", 2);
        System.out.println("concat=" + concat);

        System.out.println("== exception ==");
        try {
            int unreachable = mark("before-failure", 1)
                    + fail() + mark("after-failure", 2);
            System.out.println("unreachable=" + unreachable);
        } catch (IllegalStateException ex) {
            System.out.println("caught=" + ex.getMessage());
        }
    }
}
~~~

Open PowerShell (Windows) or Bash (Linux/macOS) in the folder containing the file. Use **JDK 17 or newer**:

~~~bash
java -version
javac -version
javac -encoding UTF-8 LeftToRightDemo.java
java LeftToRightDemo
~~~

**Exact expected output** of `java LeftToRightDemo`:

~~~text
== binary ==
visit=left
visit=middle
visit=right
binary=14
== arguments ==
visit=arg-1
visit=arg-2
visit=arg-3
arguments=123
== nested ==
visit=outer
visit=inner-left
visit=inner-right
nested=15
== receiver ==
visit=receiver
visit=method-1
visit=method-2
receiverTotal=15
== snapshot ==
snapshot=30,current=20
captured=123,counter=4
== short-circuit ==
and=false
or=true
visit=and-eager
eagerAnd=false
visit=selected
conditional=7
== arrays ==
arraySum=30,index=2
== strings ==
visit=concat-1
visit=concat-2
concat=12
== exception ==
visit=before-failure
visit=failure
caught=stop
~~~

The output of `java -version` and `javac -version` depends on the JDK and is not part of the fixed stdout block above.

## 4. Reading the Demo by Group

### 4.1. Operands: Call Order Differs from Grouping Order

~~~java
int binary = mark("left", 2)
        + mark("middle", 3) * mark("right", 4);
~~~

- Java evaluates `mark("left", 2)` first, recording `visit=left` and obtaining the value 2.
- Next, to evaluate the right operand of `+`, Java evaluates `mark("middle", 3)` and then `mark("right", 4)`.
- The multiplication operator computes `3 * 4 = 12`; then addition computes `2 + 12 = 14`.

**Do not deduce that `mark("middle", ...)` must run before `mark("left", ...)` merely because `*` has higher precedence than `+`.**

### 4.2. Method Arguments: Left to Right

~~~java
int value = digits(
        mark("arg-1", 1),
        mark("arg-2", 2),
        mark("arg-3", 3));
~~~

Argument expressions are evaluated in order **1 → 2 → 3**. Once all three expressions complete normally, Java calls `digits(1, 2, 3)` and returns **123**.

For **nested invocations**:

~~~java
add(mark("outer", 4),
    add(mark("inner-left", 5), mark("inner-right", 6)));
~~~

Java evaluates the first argument of the outer call first (printing `visit=outer`), then enters the second argument expression: the inner arguments are evaluated left to right (printing `inner-left`, `inner-right`). Afterward `add(5, 6)` returns 11 and `add(4, 11)` returns **15**.

### 4.3. Receiver Selection Expression Before Arguments

~~~java
makeReceiver().addToBase(
        mark("method-1", 2),
        mark("method-2", 3));
~~~

`makeReceiver()` is evaluated to determine the target object of the call, so `visit=receiver` appears **before** `visit=method-1` and `visit=method-2`. Then `addToBase(2, 3)` uses `base=10` to return **15**.

This is the rule in the context of invoking an instance method that has a receiver expression. If the object creation/lookup expression itself fails, the invocation may not happen.

### 4.4. Already-Evaluated Values Are Not "Re-read" After Side Effects

~~~java
int current = 10;
int result = current + (current = 20);
~~~

The left operand `current` is read and keeps the value **10**. Next, the right operand assigns `current = 20` and evaluates to 20. The result is `result = 10 + 20 = 30`, while `current` after the expression equals **20**.

Similarly:

~~~java
int counter = 1;
int value = digits(counter++, counter++, counter++);
~~~

Each argument is evaluated from left to right. Postfix `++` takes the **old value** before incrementing, so the arguments are **1, 2, 3** respectively, the variable becomes **4** afterward, and `digits(1, 2, 3)` returns 123.

This example is for **understanding the rule**, not advice to nest multiple variable increments into a single call: such code is hard to review and debug.

### 4.5. Short-Circuiting and Branch Selection

~~~java
boolean a = false && check("unused", true);
boolean b = true || check("also-unused", false);
~~~

With `&&`, if the left operand is false, the right operand **is not evaluated**. With `||`, if the left operand is true, the right operand **is not evaluated**.

Conversely:

~~~java
boolean c = false & check("executed", true);
~~~

The boolean `&` operator still evaluates the right side because it **does not short-circuit**. The value `c` is false, yet the method is still invoked.

With `?:`:

~~~java
int value = true ? mark("selected", 7) : mark("ignored", 8);
~~~

Java evaluates the condition first, then **only the chosen branch**. Because the condition is true, only `visit=selected` appears.

These exceptions do not contradict the left-to-right rule; they define **which expressions actually need to be evaluated**.

### 4.6. Array Access and Strings

~~~java
int index = 0;
int[] values = {10, 20, 30};
int sum = values[index++] + values[index++];
~~~

In the addition, the left operand is evaluated completely first: reading `values[0] = 10` and incrementing `index` to 1. The right operand then reads `values[1] = 20` and increments `index` to 2. The sum is **30**.

With string concatenation:

~~~java
String text = "" + mark("first", 1) + mark("second", 2);
~~~

The two calls are still evaluated in left-to-right order; the `+` operations starting from a `String` perform string concatenation, so the result is `"12"`, not the number 3.

### 4.7. Exceptions Prevent Subsequent Evaluation

~~~java
int result = mark("before", 1) + fail() + mark("after", 2);
~~~

If `fail()` throws an exception, `mark("after", 2)` **does not run**, and there is no normal result value for the addition. A `catch` block can handle the exception, but it does not cause the remaining expressions to automatically resume.

## 5. Writing More Testable Code When Side Effects Exist

Even though Java defines evaluation order, you should still **split statements** in business code so readers do not have to simulate variable increments or side-effecting calls:

~~~java
int first = nextNumber();
int second = nextNumber();
int third = nextNumber();
int result = digits(first, second, third);
~~~

This example shows how to structure code; to run standalone, suitable definitions for `nextNumber()` and `digits(...)` are needed. In the section 3 demo, all methods are already fully declared.

Splitting steps is especially worthwhile when there is I/O, shared state mutation, counter increments, error handling, or when operation order is part of the business contract.

### Do Not Confuse This with Concurrent Execution

The language rule defines evaluation order within **a single thread executing the expression**. It does **not** guarantee the visibility order of side effects across other threads if the program uses concurrency. Coordinating threads requires proper synchronization rules and memory-model guarantees; writing an addition does not replace synchronization.

## 6. Common Misconceptions

| Misconception | What is true in Java |
| --- | --- |
| "The `*` operator has high precedence, so functions inside multiplication are always called first." | Precedence determines **operator grouping**, not reversing left-to-right evaluation order |
| "Arguments can run in any order for optimization." | Java specifies that **invocation arguments are evaluated from left to right** |
| "The left expression can be re-read after the right side assigns a variable." | The already-evaluated left operand value is retained per operator semantics |
| "`counter++` in three arguments all return the same number." | Each argument sees the value already incremented by the previous argument |
| "`&&` and `&` both skip the right side when the left side is false." | Only `&&` short-circuits; boolean `&` evaluates both sides when normal |
| "`?:` evaluates both branches and then picks a result." | Only the selected branch is evaluated |
| "If one argument throws an exception, the remaining arguments still run." | Subsequent arguments are not evaluated |
| "Java picks call order however the compiler prefers." | Observed order must conform to the specified semantics |

## 7. Self-Check Exercises

1. **Precedence:** In `a() + b() * c()`, what is the call order if all three complete normally?  
   *Answer:* `a()`, `b()`, `c()`; the value is still grouped as `a() + (b() * c())`.
2. **Arguments:** Which label does `show(mark("A", 1), mark("B", 2))` print first?  
   *Answer:* `A` before `B`.
3. **Side effects:** What are `x` and `n` in `int n = 10; int x = n + (n = 20);`?  
   *Answer:* `x = 30`, `n = 20`.
4. **Postfix increment:** What three arguments does `int n = 1; digits(n++, n++, n++);` receive, and what is `n` afterward?  
   *Answer:* 1, 2, 3, and `n = 4`.
5. **Short-circuiting:** Does `false && sideEffect()` call `sideEffect()`?  
   *Answer:* No.
6. **Non-short-circuiting:** Does `false & sideEffect()` call `sideEffect()`, assuming the method returns `boolean`?  
   *Answer:* Yes, if no exception occurs.
7. **Exceptions:** If the second argument throws an exception, is the third argument evaluated?  
   *Answer:* No; the method invocation is not executed normally.

## Checklist

- [ ] Separate **precedence/associativity** from **evaluation order**.
- [ ] For ordinary operands and arguments, apply the **left-to-right** rule.
- [ ] On instance method calls, consider the receiver expression before the argument list.
- [ ] Understand that an already-evaluated value is preserved when a later side has side effects.
- [ ] Recognize short-circuit exceptions `&&`, `||`, and branch selection `?:`.
- [ ] Understand that an exception prevents subsequent parts of the expression from being evaluated.
- [ ] Prefer splitting expressions with multiple side effects into clear statements.

**Conclusion:** Java clearly defines left-to-right evaluation order for operands and arguments in their respective contexts. Distinguish that from **operator grouping**, and remember that short-circuiting, branch selection, and exceptions can skip expressions that are unnecessary or cannot continue.
