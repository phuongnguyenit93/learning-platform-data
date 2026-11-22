# Distinguishing Expression Value from Variable Value After `++` or `--`

## 1. Always Track Two Quantities

Whenever you encounter prefix/postfix operators, separately record **the value the expression supplies to the enclosing calculation** and **the variable's state after the update**. The four foundational rules are: `x++`/`x--` supplies the **old** value and then updates the variable; `++x`/`--x` updates the variable and supplies the **new** value. The update happens immediately during this evaluation.

With two independent examples:

~~~java
int x = 5;
int a = x++; // a=5, x=6

int y = 5;
int b = ++y; // b=6, y=6
~~~

| Expression | Value Passed to Outer Assignment | Variable State Afterward |
|---|---:|---:|
| `x++` with `x=5` | 5 | `x=6` |
| `++x` with `x=5` | 6 | `x=6` |
| `x--` with `x=5` | 5 | `x=4` |
| `--x` with `x=5` | 4 | `x=4` |

These are **two different pieces of information**, even though some examples have the same number in both columns. The lesson “Prefix and Postfix Increment and Decrement in Java” explains the syntax and loop usage; this lesson focuses on **the method for tracing results when the expression is used**.

## 2. Trace Table: Reading Values at the Right Moment

For any Java line, you can follow this sequence:

1. Write down the variable state **before the expression**.
2. Locate `++`/`--` and record **the value that the operator supplies**.
3. Update the variable state immediately when the operator is evaluated.
4. Read subsequent operands according to Java's evaluation order and compute the outer result.
5. Record **both the result and the final state**; never substitute one value for the other.

Example with **one** postfix operation and one subsequent state read:

~~~java
int x = 5;
int result = x++ * 10 + x;
~~~

| Step | Value Used in Calculation | Value Currently Held by `x` |
|---|---:|---:|
| Initial | — | 5 |
| `x++` | 5 | 6 |
| `5 * 10` | 50 | 6 |
| Read `x` in the last operand | 6 | 6 |
| Addition | `result = 56` | 6 |

With prefix:

~~~java
int y = 5;
int result = ++y * 10 + y;
// result=66, y=6
~~~

`++y` supplies 6 and the variable is already 6 when the later operand reads it. The final result **cannot be deduced solely from how many times the `++` symbol appears**; you must track the timing of each read.

## 3. The Receiving Variable and the Updated Variable Can Differ

~~~java
int score = 10;
int snapshot = score++;
int current = score;
System.out.println(snapshot); // 10
System.out.println(current);  // 11
~~~

`snapshot` stores **the postfix expression value**; `current` reads **the state after postfix**. If you log “`score++` returns 11” just because a later log shows `score=11`, you have conflated two different points in time.

A trap when the receiving variable and the updated variable are the same variable:

~~~java
int n = 5;
n = n++;
System.out.println(n); // 5
~~~

`n++` first sets `n` to 6, yet **returns 5**; the outer assignment stores 5 back. Therefore, this line does not increment the variable. When you only want to update state, write `n++;` on its own. Chains with **multiple** increments/decrements in one expression are analyzed and rewritten in the final lesson of this chapter.

## 4. Distinguishing Incrementing an Index from Incrementing an Array Element

The two lines below place the operator in **two different positions**:

~~~java
int[] items = {7, 9};
int index = 0;
int picked = items[index++];
// picked=7, index=1, items remains {7,9}
~~~

`index++` returns the old index 0, then increments **index**; it does not change the value of `items[0]`.

~~~java
int[] items = {7, 9};
int previous = items[0]++;
// previous=7, items[0]=8, items[1]=9
~~~

Here `++` is attached to **the array element variable `items[0]`**, not the index. When debugging, explicitly record “which variable was modified” alongside “what the expression returned”.

## 5. Old Values at Numeric Boundaries and with Wrappers

~~~java
int max = Integer.MAX_VALUE;
int old = max++;
// old=2147483647, max=-2147483648
~~~

Postfix supplies the old value even when the update causes `int` overflow. Java does not automatically throw an overflow exception for this `++` operation. If overflow detection is needed, consider `Math.incrementExact` and design a separate way to return the old value.

With a `nullable Integer`, `++` requires unboxing; `Integer absent = null; absent++;` will throw `NullPointerException`. A trace table only completes normally when every evaluation step succeeds.

## 6. Java 17+ Program to Cross-Check the Table

Save as `IncrementExpressionValueDemo.java`:

~~~java
public final class IncrementExpressionValueDemo {
    public static void main(String[] args) {
        int post = 5;
        int postValue = post++;
        System.out.println("post=" + postValue + "," + post);

        int pre = 5;
        int preValue = ++pre;
        System.out.println("pre=" + preValue + "," + pre);

        int x = 5;
        int withPost = x++ * 10 + x;
        System.out.println("tracePost=" + withPost + "," + x);

        int y = 5;
        int withPre = ++y * 10 + y;
        System.out.println("tracePre=" + withPre + "," + y);

        int overwritten = 5;
        overwritten = overwritten++;
        System.out.println("overwritten=" + overwritten);

        int[] items = {7, 9};
        int index = 0;
        int picked = items[index++];
        System.out.println("index=" + picked + "," + index + "," + items[0]);

        int previous = items[0]++;
        System.out.println("element=" + previous + "," + items[0]);

        int max = Integer.MAX_VALUE;
        int old = max++;
        System.out.println("overflow=" + old + "," + max);
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 IncrementExpressionValueDemo.java
java IncrementExpressionValueDemo
~~~

**Expected stdout:**

~~~text
post=5,6
pre=6,6
tracePost=56,6
tracePre=66,6
overwritten=5
index=7,1,7
element=7,8
overflow=2147483647,-2147483648
~~~

The `tracePost`/`tracePre` lines verify when the final operand reads the variable; `index`/`element` show the different increment targets; `overwritten` distinguishes a temporary side effect from the final state after the outer assignment.

## 7. Exercises with Answers

**Exercise A.** `int x = 3; int y = x-- * 10 + x;`. **Answer:** `y=32`, `x=2` because `x--` supplies 3 and then the new `x` is 2.

**Exercise B.** `int x = 3; int y = --x * 10 + x;`. **Answer:** `y=22`, `x=2` because `--x` supplies 2 and the later read is also 2.

**Exercise C.** `int[] data = {4,5}; int i=0; int a=data[i++];`. **Answer:** `a=4`, `i=1`, and the array is unchanged.

**Exercise D.** `int[] data = {4,5}; int a=data[0]++;`. **Answer:** `a=4` and `data[0]=5`.

**Exercise E.** Explain `int n=9; n=n++;`. **Answer:** `n` ends up still 9 because the old result of postfix is written back by the outer assignment.

## 8. Self-Check Before Moving On

- [ ] Can distinguish **expression value** from **currently stored value**.
- [ ] Know that postfix updates immediately, without waiting for the next statement.
- [ ] Can draw a trace table for an increment/decrement inside an arithmetic expression.
- [ ] Identify which variable changes when `++` is on an index vs. an array element.
- [ ] Can explain how an outer assignment overwrites `x++` without calling Java undefined.
- [ ] Know that the old value is still returned when the update overflows.

**Key Takeaway:** To understand `++`/`--` inside an expression, answer **two separate questions**: *what value did the operator just supply* and *which variable is currently holding what value*. For expressions with multiple updates to the same variable, add an evaluation-order table and consider separating side effects into individual statements.