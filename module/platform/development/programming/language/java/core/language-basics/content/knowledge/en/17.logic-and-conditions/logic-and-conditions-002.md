# Short-Circuit Evaluation and Unexecuted Expressions in Java

> **Java core — language-basics / Logic and conditions**  
> **Requirements:** JDK 17+, a standalone Java file, standard library only.  
> **Goal:** Predict when Java **does not evaluate the right side** of `&&`, `||`, and the **unselected branch** of `?:`; distinguish them from `&`, `|`, `^` on booleans; write guards to prevent errors and control side effects.

## 1. What Is Short-Circuit Evaluation?

**Short-circuit evaluation** means Java **does not need to execute a subexpression** when the already evaluated side is enough to determine the result of the entire logical operation.

- `left && right`: if `left` is **false**, the result is guaranteed to be false, so **`right` is not evaluated**.
- `left || right`: if `left` is **true**, the result is guaranteed to be true, so **`right` is not evaluated**.
- If the right side is needed to decide the result, Java **does evaluate** the right side.

Example:

~~~java
boolean andResult = false && expensiveCheck(); // false, method is not called.
boolean orResult = true || expensiveCheck();   // true, method is not called.
~~~

`expensiveCheck()` here is just an illustrative name; see the runnable program below for concrete methods.

**Distinction:** "The right side is not executed" is a **runtime** behavior. Java still must parse and type-check the entire expression at **compile time**, even if a branch will be skipped during a specific run.

## 2. Decision Table: Is the Right Side Evaluated?

| Operator | Left side | Runs right side? | Result |
| --- | --- | --- | --- |
| `&&` | false | **No** | false |
| `&&` | true | **Yes** | Per right-side value |
| Short-circuit OR (`\|\|`) | true | **No** | true |
| Short-circuit OR (`\|\|`) | false | **Yes** | Per right-side value |

Java evaluates the **left side before the right side**. If the left side itself throws an exception, the expression terminates abnormally and the right side is not evaluated either, but that is **not** a normal short-circuit returning a boolean value.

For instance:

~~~java
boolean first = true && check();  // Must evaluate check().
boolean second = false || check(); // Must evaluate check().
~~~

Therefore, you cannot claim "`&&` never runs the right side" or "`||` never runs the right side" in all cases. The exact condition is **whether the left side suffices to determine the result**.

## 3. Skipped Expressions Cause No Side Effects or Exceptions

When a branch is skipped, operations **inside that branch do not happen**: no method calls, no variable increments, no array accesses, no object unboxing, and no exceptions thrown from the skipped expression.

~~~java
int counter = 0;
boolean a = false && (++counter > 0); // a=false, counter=0.
boolean b = true || (++counter > 0);  // b=true, counter remains 0.
~~~

Example with a zero divisor:

~~~java
int divisor = 0;
boolean valid = divisor != 0 && (10 / divisor > 2);
// valid=false, division is not executed, no ArithmeticException.
~~~

**Do not reverse the guard:** `10 / divisor > 2 && divisor != 0` performs the division first and throws an exception when `divisor == 0`.

Conditions inside short-circuit expressions are `boolean` expressions; Java does **not** implicitly convert integers 0/1 to false/true.

## 4. Safe Guards for Nulls, Arrays, and Dependent Conditions

Short-circuiting is especially useful when an expression is only valid **after a preceding condition has been checked**.

~~~java
String text = null;
boolean hasText = text != null && !text.isBlank(); // false, no NPE.

int[] numbers = {5, 10, 15};
int index = -1;
boolean validIndex = index >= 0
        && index < numbers.length
        && numbers[index] > 0; // false, does not access numbers[-1].
~~~

With multiple chained `&&` operators, Java evaluates from left to right and **stops at the first false condition**; all remaining conditions do not run.

With `||`, conditions can be written in a default-value / missing-value style:

~~~java
String name = null;
boolean missingOrBlank = name == null || name.isBlank();
// true, does not call name.isBlank().
~~~

The guard condition must sit on the **left** of the corresponding logical operator. If `name` is null and you write `name.isBlank() || name == null`, the exception occurs before reaching the null check.

## 5. `&`, `|`, and `^` on Booleans Are Not Short-Circuiting

`&`, `|`, and `^` can be used on booleans, but unlike `&&`/`||`, they **still evaluate both sides**:

| Boolean operator | Meaning | Evaluates right side |
| --- | --- | --- |
| `&&` | Short-circuit AND | Only when left side is true |
| `\|\|` | Short-circuit OR | Only when left side is false |
| `&` | Non-short-circuit AND | **Always** |
| `\|` | Non-short-circuit OR | **Always** |
| `^` | XOR | **Always** |

~~~java
int counter = 0;
boolean result = false & (++counter > 0);
// result=false, but counter=1 because the right side still runs.
~~~

If the right side throws an exception, `false & right` **still throws**, whereas `false && right` skips the right side.

**Data type reminder:** `&`, `|`, and `^` also have *bitwise* usage with integers; `&&` and `||` are not bitwise operators and work only with booleans. Do not casually replace two-character short-circuit operators with single-character ones when the right side contains expensive or potentially failing operations.

## 6. The Conditional Operator `?:` Also Skips the Unselected Branch

The expression `condition ? whenTrue : whenFalse` evaluates `condition` first and **evaluates only one of the two branches**:

~~~java
int x = 5;
int result = x > 0 ? computePositive() : computeNonPositive();
// If x > 0: calls only computePositive().
// If x <= 0: calls only computeNonPositive().
~~~

This is **conditional evaluation**, similar to executing only the chosen branch in `if/else`. Do not equate `?:` with running both computations and then picking one result.

Logging example:

~~~java
StringBuilder log = new StringBuilder();
int result = false
        ? markInt(log, "X", 10)
        : markInt(log, "R", 20);
// result=20, log="R"; markInt(...,"X",...) is not called.
~~~

When both branches have significant side effects, `if/else` usually expresses intent more readably and is easier to debug than nested ternary operators.

## 7. Runnable Java 17+ Code: Observing Skipped Branches

Create the file **`ShortCircuitDemo.java`**:

~~~java
public final class ShortCircuitDemo {
    private static boolean mark(
            StringBuilder log, String label, boolean value) {
        log.append(label);
        return value;
    }

    private static int markInt(
            StringBuilder log, String label, int value) {
        log.append(label);
        return value;
    }

    private static boolean fail() {
        throw new IllegalStateException("executed");
    }

    public static void main(String[] args) {
        StringBuilder trace = new StringBuilder();

        boolean and = mark(trace, "F", false)
                && mark(trace, "X", true);
        boolean or = mark(trace, "T", true)
                || mark(trace, "Y", false);
        boolean eagerAnd = mark(trace, "A", false)
                & mark(trace, "B", true);
        boolean eagerOr = mark(trace, "C", true)
                | mark(trace, "D", false);
        boolean xor = mark(trace, "E", true)
                ^ mark(trace, "G", false);

        System.out.println("and=" + and);
        System.out.println("or=" + or);
        System.out.println("eagerAnd=" + eagerAnd);
        System.out.println("eagerOr=" + eagerOr);
        System.out.println("xor=" + xor);
        System.out.println("trace=" + trace);

        String name = null;
        System.out.println("nullGuard="
                + (name != null && !name.isBlank()));
        System.out.println("nullOr="
                + (name == null || name.isBlank()));

        int[] numbers = {5, 10, 15};
        int index = -1;
        System.out.println("indexGuard="
                + (index >= 0 && index < numbers.length
                    && numbers[index] > 0));

        int zero = 0;
        System.out.println("divideGuard="
                + (zero != 0 && 10 / zero > 2));

        boolean skippedAnd = false && fail();
        boolean skippedOr = true || fail();
        System.out.println("skippedAnd=" + skippedAnd);
        System.out.println("skippedOr=" + skippedOr);

        try {
            boolean eager = false & fail();
            System.out.println("eager=" + eager);
        } catch (IllegalStateException ex) {
            System.out.println("eagerThrows=IllegalStateException");
        }

        StringBuilder branches = new StringBuilder();
        int selected = false
                ? markInt(branches, "X", 10)
                : markInt(branches, "R", 20);
        int other = true
                ? markInt(branches, "L", 30)
                : markInt(branches, "Y", 40);
        System.out.println("conditional=" + selected + "," + other);
        System.out.println("branchTrace=" + branches);

        int[] visits = {0};
        boolean short1 = false && (++visits[0] > 0);
        boolean short2 = true || (++visits[0] > 0);
        System.out.println("shortCount=" + visits[0]);
        boolean eager = false & (++visits[0] > 0);
        System.out.println("eagerCount=" + visits[0]);

        Boolean unknown = null;
        boolean boxedGuard = unknown != null && unknown;
        System.out.println("boxedGuard=" + boxedGuard);
        try {
            boolean unsafe = true && unknown;
            System.out.println("unsafe=" + unsafe);
        } catch (NullPointerException ex) {
            System.out.println("boxedNull=NullPointerException");
        }
    }
}
~~~

Compile/run in the directory containing the file (Bash, PowerShell, or Command Prompt):

~~~bash
javac -encoding UTF-8 ShortCircuitDemo.java
java ShortCircuitDemo
~~~

**Exact expected stdout:**

~~~text
and=false
or=true
eagerAnd=false
eagerOr=true
xor=true
trace=FTABCDEG
nullGuard=false
nullOr=true
indexGuard=false
divideGuard=false
skippedAnd=false
skippedOr=true
eagerThrows=IllegalStateException
conditional=20,30
branchTrace=RL
shortCount=0
eagerCount=1
boxedGuard=false
boxedNull=NullPointerException
~~~

The trace `FTABCDEG`: `&&` skips X, `||` skips Y, while `&`, `|`, and `^` all run both sides. `branchTrace=RL` contains only the selected branches; `shortCount=0` confirms the two `++` operations were skipped, whereas `eagerCount=1` demonstrates the side effect of `&`.

## 8. Common Mistakes and Exercises

| Mistake | Why is it dangerous? | How to fix |
| --- | --- | --- |
| `obj.method() && obj != null` | May call method on null before the guard | `obj != null && obj.method()` |
| `array[i] > 0 && i >= 0` | May access an invalid index | `i >= 0 && i < array.length && array[i] > 0` |
| `divisor != 0 & 10 / divisor > 1` | `&` still evaluates the division when divisor=0 | Use `&&` |
| `true \|\| validate()` expecting validate to always run | `validate()` is not called | Call `validate()` separately if its side effect is mandatory |
| `flag = cond && updateState()` always wanting updateState | Function is skipped when cond=false | Separate the update into its own statement |
| Using `?:` with two long side-effect branches | Hard to read which branch runs | Use `if/else` |

**Exercise 1.** Predict how many times `check()` is called in `false && check()`, `true && check()`, `true || check()`, `false || check()`.

**Exercise 2.** Given `int x = 0;`, compare `false && (++x > 0)` with `false & (++x > 0)`. What is the final value of `x` in each case?

**Exercise 3.** With `String s = null;`, what happens in `s != null && s.length() > 0` and `s.length() > 0 && s != null`?

**Exercise 4.** Create a ternary expression with two tracing methods. Determine which branch runs for each condition value.

**Exercise 5.** Distinguish `false && fail()` from `false & fail()` if `fail()` throws an exception.

### Key Takeaways

**`&&` skips the right side when the left side is false; `||` skips the right side when the left side is true.** `?:` runs only the selected branch. A skipped expression **does not execute its own side effects, calls, or exceptions**, though it still must be valid at compile time. `&`, `|`, and `^` on booleans evaluate both sides. Place guards on the proper side and do not rely on short-circuiting if an operation **must run**.
