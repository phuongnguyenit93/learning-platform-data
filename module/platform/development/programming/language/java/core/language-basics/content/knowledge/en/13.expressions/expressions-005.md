# Distinguishing Expression Grouping Order from Evaluation Order in Java

> **Java core — language-basics / Expressions**  
> **Requirements:** Java 17+, a single standalone Java file; standard library only.  
> **Objective:** Distinguish **expression grouping** by precedence/associativity from **execution order of evaluations** (*evaluation order*); independently predict both the **result** and the **order of side effects** in Java expressions.

## 1. Two Questions That Must Be Answered Separately

Given the expression:

~~~java
int result = 2 + 3 * 4;
~~~

- **How is it grouped?** The `*` operator has higher precedence than `+`, so the expression is grouped as `2 + (3 * 4)`; the result is **14**.
- **In what order are operands evaluated?** Java has a separate evaluation rule: for ordinary binary operations, **the left operand is evaluated before the right operand**. With literals like the example above, no difference in side effects is observed; with method calls, it is clearly visible.

**Common mistake:** "`*` has high precedence, so every method call around `*` runs before a call on the left side of `+`." That is **false**. Precedence determines **expression structure**, not reversing function call order.

## 2. Precedence and Associativity Determine Grouping

| Expression | Grouping | `int` value |
| --- | --- | ---: |
| `2 + 3 * 4` | `2 + (3 * 4)` | 14 |
| `(2 + 3) * 4` | `(2 + 3) * 4` | 20 |
| `10 - 3 - 2` | `(10 - 3) - 2` | 5 |
| `10 - (3 - 2)` | `10 - (3 - 2)` | 9 |
| `24 / 4 / 2` | `(24 / 4) / 2` | 3 |
| `24 / (4 / 2)` | `24 / (4 / 2)` | 12 |

**Precedence** explains why `*` binds more tightly to operands than `+`. **Associativity** explains why operators at the same level, such as `-` and `/`, group from **left to right**. Assignment operators such as `a = b = 5` group from **right to left**: `a = (b = 5)`.

Parentheses change **grouping**, which can change the result. They do not automatically turn every expression into "evaluate operands inside parentheses before everything outside parentheses."

## 3. Java Evaluates Operands: A Tracing Example

Imagine a `step` helper that records its label each time it is called:

~~~java
static int step(StringBuilder log, String label, int value) {
    log.append(label);
    return value;
}
~~~

The expression:

~~~java
var log = new StringBuilder();
int value = step(log, "A", 2)
        + step(log, "B", 3) * step(log, "C", 4);
~~~

is **grouped** as:

~~~text
A + (B * C)
~~~

Yet the `step` calls actually execute in order **A, B, C**, because Java evaluates the left operand of `+` before evaluating the right operand, which is the multiplication expression. Once at the right side, Java evaluates B before C. The result is `2 + 3 * 4 = 14`.

Change the grouping:

~~~java
log.setLength(0);
int changed = (step(log, "A", 2) + step(log, "B", 3))
        * step(log, "C", 4);
~~~

The trace order is still **A, B, C**, while the result changes to **20** because parentheses changed which operation is grouped.

**Distinguish clearly:**

| Property | `A() + B() * C()` | `(A() + B()) * C()` |
| --- | --- | --- |
| Grouping | `A() + (B() * C())` | `(A() + B()) * C()` |
| Call order (normal evaluation) | A → B → C | A → B → C |
| Result if A=2, B=3, C=4 | 14 | 20 |

The left-to-right rule also applies to evaluating method arguments: `print(computeA(), computeB())` evaluates `computeA()` before `computeB()`. However, each sub-expression can contain its own operators and conditional evaluation branches.

## 4. Side Effects Make Execution Order Visible

The postfix operator `i++` **returns the old value and then increments the variable**. Therefore:

~~~java
int i = 1;
int result = i++ + i++ * i++;
~~~

Java evaluates the three operands from left → right:

1. The first `i++` returns **1**, `i` becomes 2.
2. The second `i++` returns **2**, `i` becomes 3.
3. The third `i++` returns **3**, `i` becomes 4.

**Grouping:** `1 + (2 * 3)`, so `result = 7`; afterward `i = 4`. Multiplication never causes the two increments on the right to run before the leftmost increment.

This is an **order-recognition exercise**, not recommended coding style. Avoid packing multiple `++` operations or side-effecting calls into a single long expression; split them into separate statements for readability and maintainability.

## 5. Operators with Conditional Evaluation

The **left-to-right** rule does not mean **every operand or branch is evaluated**.

| Expression | Order/branches actually evaluated |
| --- | --- |
| `left && right` | Evaluates left; evaluates right only if left is `true` |
| `left \|\| right` | Evaluates left; evaluates right only if left is `false` |
| `condition ? yes : no` | Evaluates condition, then **only one** of the two branches yes/no |
| `left & right` with boolean | Evaluates **both** sides, no short-circuit |
| `left \| right` with boolean | Evaluates **both** sides, no short-circuit |

Example:

~~~java
String name = null;
boolean valid = name != null && !name.isBlank();
~~~

The result is **false**, because `name != null` is false and the side calling `isBlank()` is skipped. Reversing the order to `!name.isBlank() && name != null` would throw a `NullPointerException`.

Use `&&`, `||`, or `?:` when conditional evaluation is needed, and do not use `&`/`|` in place of `&&`/`||` if skipping the right side is required.

## 6. Runnable Java 17+ Program

Create the file **GroupingVsEvaluationDemo.java**:

~~~java
public final class GroupingVsEvaluationDemo {
    private static int step(StringBuilder log, String label, int value) {
        log.append(label);
        return value;
    }

    private static boolean test(
            StringBuilder log, String label, boolean value) {
        log.append(label);
        return value;
    }

    public static void main(String[] args) {
        System.out.println("precedence=" + (2 + 3 * 4));
        System.out.println("parentheses=" + ((2 + 3) * 4));
        System.out.println("subtractLeft=" + (10 - 3 - 2));
        System.out.println("subtractRight=" + (10 - (3 - 2)));

        StringBuilder log = new StringBuilder();
        int first = step(log, "A", 2)
                + step(log, "B", 3) * step(log, "C", 4);
        System.out.println("firstValue=" + first);
        System.out.println("firstOrder=" + log);

        log.setLength(0);
        int second = (step(log, "A", 2) + step(log, "B", 3))
                * step(log, "C", 4);
        System.out.println("secondValue=" + second);
        System.out.println("secondOrder=" + log);

        log.setLength(0);
        int left = step(log, "A", 24) / step(log, "B", 4)
                / step(log, "C", 2);
        System.out.println("divisionLeft=" + left + ":" + log);

        log.setLength(0);
        int right = step(log, "A", 24)
                / (step(log, "B", 4) / step(log, "C", 2));
        System.out.println("divisionRight=" + right + ":" + log);

        int i = 1;
        int increments = i++ + i++ * i++;
        System.out.println("increments=" + increments);
        System.out.println("afterIncrements=" + i);

        StringBuilder checks = new StringBuilder();
        boolean and = test(checks, "F", false)
                && test(checks, "X", true);
        boolean or = test(checks, "T", true)
                || test(checks, "Y", false);
        int selected = test(checks, "Q", false)
                ? step(checks, "L", 100)
                : step(checks, "R", 200);
        boolean eager = test(checks, "E", false)
                & test(checks, "G", true);

        System.out.println("shortAnd=" + and);
        System.out.println("shortOr=" + or);
        System.out.println("selected=" + selected);
        System.out.println("eagerAnd=" + eager);
        System.out.println("conditionalTrace=" + checks);
    }
}
~~~

In the folder containing the file, run with Bash, PowerShell, or Command Prompt:

~~~bash
javac -encoding UTF-8 GroupingVsEvaluationDemo.java
java GroupingVsEvaluationDemo
~~~

**Exact expected output:**

~~~text
precedence=14
parentheses=20
subtractLeft=5
subtractRight=9
firstValue=14
firstOrder=ABC
secondValue=20
secondOrder=ABC
divisionLeft=3:ABC
divisionRight=12:ABC
increments=7
afterIncrements=4
shortAnd=false
shortOr=true
selected=200
eagerAnd=false
conditionalTrace=FTQREG
~~~

**Matching against the code:**

- Both `firstOrder` and `secondOrder` lines are `ABC`; however, different grouping yields `firstValue=14` and `secondValue=20`.
- `divisionLeft` and `divisionRight` both call A, B, C in that order; the results 3 and 12 differ because division grouping differs.
- `increments=7`, `afterIncrements=4` confirm the `i++` evaluations proceed left → right.
- The trace `FTQREG`: F=false so X is skipped; T=true so Y is skipped; Q=false so only branch R runs; finally both E and G run because boolean `&` does not short-circuit.

## 7. Common Mistakes and How to Read Expressions

| Misconception | Correct understanding |
| --- | --- |
| "Multiplication has high precedence, so `B()`/`C()` run before `A()` in `A() + B() * C()`." | False: multiplication is **grouped** together, while calls normally run A → B → C |
| "Left → right associativity means every calculation simply runs left to right." | False: associativity describes the **expression tree**; evaluation order has its own rules |
| "With parentheses, calls inside parentheses always run first." | False: in `A() + (B() * C())`, A is still evaluated before B and C |
| "`&&` always evaluates both sides." | False: the right side may be skipped |
| "`&` and `&&` are equivalent for all booleans." | False when there is an error or side effect on the right side |
| "You can freely write multiple `i++` in an expression because Java defines the order clearly." | Valid but hard to read; split operations with side effects |

**Self-check procedure:** (1) rewrite the grouping with parentheses; (2) locate operands with side effects; (3) apply evaluation order and branch-skipping rules; (4) compute the value; (5) verify the final variable state.

## 8. Exercises

**Exercise 1.** Evaluate `3 + 4 * 5` and `(3 + 4) * 5`. Explain the grouping order without substituting an "which operator runs first" argument.

**Exercise 2.** A function `mark("X")` logs X and returns a value. Predict the log string of `mark("A") + mark("B") * mark("C")` when the functions just return integers, along with the grouping of the calculation.

**Exercise 3.** Given `int i = 1; int result = i++ + i++ * i++;`. Predict `result` and the final value of `i`; propose how to split the code to avoid overlapping side effects.

**Exercise 4.** Given `boolean a = false;` and a logging function, compare `a && logCall()` with `a & logCall()`. Which case executes `logCall()`?

**Exercise 5.** Write the two expressions `24 / 4 / 2` and `24 / (4 / 2)` using `step` calls and prove the log stays `ABC` even though the two results differ.

### Takeaways

**Expression grouping** answers "which sub-expressions does an operator apply to?", whereas **evaluation order** answers "which operand/call/side effect happens first?". In Java, operands of ordinary operations are evaluated left to right; `&&`, `||`, and `?:` can skip a side or branch. Analyze **both** rules when reading expressions containing both calculations and side effects; use parentheses and extract intermediate variables to keep code understandable.
