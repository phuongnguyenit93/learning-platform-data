# Do Not Write Mathematical Chained Comparisons Like `0 < x < 10` in Java

> **Java core — language-basics / Comparisons**  
> **Version:** Java 17+, single runnable file with no external libraries.  
> **Goal:** Explain the compilation error of `0 < x < 10`; rewrite it into independent comparisons joined by `&&`, choose the right open/closed bounds, and avoid side effects when evaluating expressions.

## 1. Why Does `0 < x < 10` Fail to Compile?

In mathematics, `0 < x < 10` means `x` is **simultaneously** greater than 0 and less than 10. In Java, the relational operator `<` returns a **`boolean`**, not a number.

~~~java
int x = 5;
// boolean valid = 0 < x < 10; // COMPILATION ERROR.
~~~

The two `<` operators share the same precedence and group from left to right, so the syntactic grouping is:

~~~text
(0 < x) < 10
 \___/
 boolean
~~~

`0 < x` returns true/false, and then the program tries to compare `boolean < int` — which is invalid. This is a **compile-time type error**, not a range check returning false.

The same error occurs with `0 <= x <= 10`, `a < b < c`, or `a > b >= c`. Java does not automatically convert chained relational comparisons into an AND operation.

## 2. Write It Correctly Using `&&`

~~~java
int x = 5;
boolean inside = 0 < x && x < 10; // true.
~~~

Equivalent to:

~~~java
boolean inside = (0 < x) && (x < 10);
~~~

These are **two** independent comparisons, each producing a `boolean` value. `&&` combines the results: the overall expression is true only when **both are true**.

Relational operators have higher precedence than `&&`, so parentheses are optional in simple expressions. For long conditions or mixed operators, parentheses help clarify intent.

**Do not substitute OR:** `0 < x || x < 10` is an "or" condition; when `x = -5`, the second side is true; when `x = 20`, the first side is true. It does not mean "`x` is between 0 and 10".

## 3. Choosing the Right Operators at the Boundaries

| Range to check | Java expression | For `x=0` | For `x=10` |
| --- | --- | --- | --- |
| Open: greater than 0, less than 10 | `0 < x && x < 10` | false | false |
| Closed: from 0 to 10 | `0 <= x && x <= 10` | true | true |
| Include 0, exclude 10 | `0 <= x && x < 10` | true | false |
| Exclude 0, include 10 | `0 < x && x <= 10` | false | true |

For the open interval `(0, 10)`, values 1 through 9 (if `x` is an integer) are valid; 0, 10, and everything outside are invalid. For array indices, the range is typically **`0 <= index && index < array.length`**, because the last valid index is `length - 1`.

To check for being **outside the open interval**, use `x <= 0 || x >= 10`. De Morgan's law allows writing the negation of `0 < x && x < 10` as `!(0 < x && x < 10)`; note that for floating-point `NaN`, the two negated forms must be evaluated according to their exact semantics.

## 4. Short-Circuiting and Safe Checks

`&&` evaluates the left-hand side first. If the left-hand side is false, Java **skips the right-hand side**. Example of guarding an array index:

~~~java
int[] values = {10, 20, 30};
int index = -1;

boolean safe = index >= 0
        && index < values.length
        && values[index] > 0;
// safe=false; values[-1] is never accessed.
~~~

If you place `values[index] > 0` before checking `index >= 0`, the program can throw `ArrayIndexOutOfBoundsException`. With boolean `&`, Java evaluates both sides without short-circuiting, making it unsuitable for guarding the right-hand side in this situation.

`&&` does not make every error vanish; it only skips an **unevaluated right-hand side**. Guard conditions must still be written in the proper order, including `null` checks before calling methods on objects.

## 5. Do Not Re-read or Recompute a Value with Side Effects

The following pattern can end up checking **two different values**, not one single `x`:

~~~java
// Avoid this if readValue() can return a different result each time:
boolean result = 0 < readValue() && readValue() < 10;
~~~

If the first call returns 5 and the second returns 50, the entire condition evaluates to false, even though 5 is indeed within the open interval. Short-circuiting also causes the second call **not to execute** when the first fails the lower bound.

When you want to check **a single read**, store the result in a variable:

~~~java
int x = readValue();
boolean inside = 0 < x && x < 10;
~~~

This is especially critical when reading input, measuring time, fetching mutable data, using randomness, or calling functions with side effects.

## 6. Two Traps: `==` Between Booleans and `NaN`

Do not try to replace `&&` with an equality check between two conditions:

~~~java
// Compiles, but is NOT equivalent to a range check:
boolean wrong = (0 < x) == (x < 10);
~~~

The `==` operator only asks **whether two boolean values are the same**. If both are false, the result is still true, whereas AND must return false.

This can be demonstrated using floating-point `Double.NaN`:

~~~java
double x = Double.NaN;
boolean valid = 0.0 < x && x < 10.0; // false.
boolean wrong = (0.0 < x) == (x < 10.0); // true.
~~~

Because all ordering comparisons (`<`/`>`) with `NaN` return false, `false == false` becomes true. When a `double` input must be **finite**, add `Double.isFinite(x)`:

~~~java
boolean inside = Double.isFinite(x) && 0.0 < x && x < 10.0;
~~~

Do not try to convert `boolean` to a number to write chained comparisons: Java does not support casting `boolean` to `int`. Use logical operators directly.

## 7. Standalone Runnable Java 17+ Program

Create the file **RangeComparisonDemo.java**:

~~~java
public final class RangeComparisonDemo {
    private static int reads;

    private static int readValue() {
        reads++;
        return reads == 1 ? 5 : 50;
    }

    private static boolean open(int x) {
        return 0 < x && x < 10;
    }

    private static boolean closed(int x) {
        return 0 <= x && x <= 10;
    }

    public static void main(String[] args) {
        for (int x : new int[] {-1, 0, 1, 9, 10, 11}) {
            System.out.println("x=" + x
                    + ",open=" + open(x)
                    + ",closed=" + closed(x));
        }

        int[] values = {10, 20, 30};
        int index = -1;
        boolean safe = index >= 0
                && index < values.length
                && values[index] > 0;
        System.out.println("guardedIndex=" + safe);

        double nan = Double.NaN;
        System.out.println("nanInRange="
                + (Double.isFinite(nan) && 0.0 < nan && nan < 10.0));
        System.out.println("nanEqualityTrap="
                + ((0.0 < nan) == (nan < 10.0)));

        reads = 0;
        boolean repeated = 0 < readValue() && readValue() < 10;
        System.out.println("repeated=" + repeated + ",reads=" + reads);

        reads = 0;
        int x = readValue();
        boolean sampled = 0 < x && x < 10;
        System.out.println("sampled=" + sampled + ",reads=" + reads);

        reads = 0;
        boolean skipped = readValue() < 0 && readValue() < 10;
        System.out.println("shortCircuit=" + skipped + ",reads=" + reads);
    }
}
~~~

Compile and run in the directory containing the file (Bash, PowerShell, or Command Prompt):

~~~bash
javac -encoding UTF-8 RangeComparisonDemo.java
java RangeComparisonDemo
~~~

**Exact expected stdout:**

~~~text
x=-1,open=false,closed=false
x=0,open=false,closed=true
x=1,open=true,closed=true
x=9,open=true,closed=true
x=10,open=false,closed=true
x=11,open=false,closed=false
guardedIndex=false
nanInRange=false
nanEqualityTrap=true
repeated=false,reads=2
sampled=true,reads=1
shortCircuit=false,reads=1
~~~

In the example, `readValue()` returns 5 on the first call and 50 on the second. `repeated` uses **both values** so it yields false, while `sampled` reads only one value (5) so it yields true. For `shortCircuit`, the left-hand side `5 < 0` is false, so Java calls `readValue()` only once. `nanEqualityTrap=true` proves that comparing two booleans for **equality** cannot substitute for `&&`.

## 8. Practical Rules and Exercises

| Case | How to write it? |
| --- | --- |
| Check value strictly between two open bounds | `min < x && x < max` |
| Check value within both inclusive bounds | `min <= x && x <= max` |
| Check valid array index | `0 <= i && i < array.length` |
| Right-hand condition may throw an error | Place the guard on the left of `&&` |
| Value comes from a function with side effects | Call once and store in a variable before comparing |
| Floating-point value must be finite | Combine `Double.isFinite(x)` with the range check |

**Exercise 1.** Write valid Java conditions for `-5 < x < 5` and `0 ≤ x ≤ 100`. Do not use chained comparisons.

**Exercise 2.** Explain why `1 < x < 10` fails at compile time; what is the type of `1 < x`?

**Exercise 3.** Evaluate `0 <= index && index < length` for the three values `index=-1`, `index=0`, and `index=length`.

**Exercise 4.** Why does `0 < getValue() && getValue() < 10` not necessarily check a single value? Rewrite it to call `getValue()` only once.

**Exercise 5.** Demonstrate why `(0.0 < Double.NaN) == (Double.NaN < 10.0)` is true while the AND condition returns false.

### Remember

**Java does not support `0 < x < 10`.** You must write **`0 < x && x < 10`** — two independent comparisons joined with AND. Choose `<` or `<=` to match the bounds, leverage short-circuiting for guards, and avoid calling side-effecting functions twice when checking **one** consistent value.
