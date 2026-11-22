# Prefix and Postfix Increment and Decrement in Java

> **Java core — language-basics / Assignment and Unary Operators**  
> **Version:** Java 17+; standalone examples, only JDK required.  
> **Objective:** Distinguish `++x`, `x++`, `--x`, `x--`; determine **the expression's value** and **the variable's value after updating**; use them properly in loops and avoid expressions containing multiple hard-to-understand side effects.

## 1. Four Ways to Increment or Decrement by One

`++` increases a variable's value by 1, while `--` decreases it by 1. These two operators can be written in two positions:

| Syntax | Name | Variable Change | Expression Value |
| --- | --- | --- | --- |
| `++x` | **Prefix** increment | `x` increases by 1 | **New** value |
| `x++` | **Postfix** increment | `x` increases by 1 | **Old** value |
| `--x` | **Prefix** decrement | `x` decreases by 1 | **New** value |
| `x--` | **Postfix** decrement | `x` decreases by 1 | **Old** value |

Initial example with `x = 5`:

~~~java
int x = 5;
int before = x++; // before = 5, x = 6.
int after  = ++x; // x = 7, after = 7.
~~~

Both prefix and postfix change the variable by **one unit**. The difference only becomes apparent when you **use the value returned by the expression** in an assignment, arithmetic operation, condition, or method call.

## 2. Expression Value Differs from Variable State After the Statement

Consider two independent snippets:

~~~java
int a = 10;
int first = a++; // first = 10, a = 11.

int b = 10;
int second = ++b; // second = 11, b = 11.
~~~

- With `a++`: takes the **old value** 10 as the expression result, while incrementing `a` to 11.
- With `++b`: increments `b` to 11 and then gives the expression the **new value** 11.

Prefix/postfix decrement behaves similarly:

~~~java
int a = 10;
int old = a--;  // old = 10, a = 9.

int b = 10;
int now = --b;  // now = 9, b = 9.
~~~

If you only need to increment/decrement a variable **without using the expression result**, both forms are equivalent in terms of the post-statement value:

~~~java
int count = 0;
count++; // count = 1.
++count; // count = 2.
count--; // count = 1.
--count; // count = 0.
~~~

Do not misunderstand “postfix happens later” as meaning the variable only changes in the **next statement**: the increment/decrement effect already happens during the evaluation of the current expression.

## 3. What Can They Be Applied To?

The operand of `++` and `--` must be an **updatable variable** of an appropriate numeric type (including `char` and numeric wrapper classes via unboxing/boxing). Valid examples:

~~~java
int counter = 2;
counter++;

int[] scores = {5, 8};
scores[0]++;

class Box {
    int size = 1;
}
Box box = new Box();
++box.size;

char letter = 'A';
letter++; // 'B'.
~~~

You cannot increment a literal, a computed non-variable value, a `final` variable, or a `boolean`:

~~~java
// DOES NOT COMPILE:
// 5++;
// (counter + 1)++;
// final int fixed = 2;
// fixed++;
// boolean enabled = true;
// enabled++;
~~~

For wrappers, watch out for `null`:

~~~java
Integer boxed = 4;
boxed++; // Valid: unbox, increment, then box back to Integer 5.

// Integer absent = null;
// absent++; // At runtime: NullPointerException on unboxing.
~~~

Operations on `byte`, `short`, or `char` still yield a result of the variable's type; incrementing or decrementing can exceed the range and wrap/flip the value without automatically throwing an overflow exception.

## 4. Use in Expressions and Evaluation Order

Java evaluates operands according to well-defined rules. Example:

~~~java
int n = 1;
int result = n++ + ++n;
// n++ returns 1, n becomes 2.
// ++n increments n to 3 and returns 3.
// result = 1 + 3 = 4; n = 3.
~~~

This result is **specified by Java**, yet expressing multiple updates to the same variable in a single expression like this is very hard to read and easy to modify incorrectly. Prefer splitting it up:

~~~java
int n = 1;
int oldValue = n;
n++;
n++;
int newValue = n;
int result = oldValue + newValue; // result = 4.
~~~

A common, easier-to-understand case is **using an array index and then incrementing the index**:

~~~java
int[] numbers = {10, 20, 30};
int i = 0;
int selected = numbers[i++]; // selected = 10, i = 1.
~~~

`i++` returns **0** to access the first element, and then `i` becomes 1. Equivalent in intent to:

~~~java
int selected = numbers[i];
i++;
~~~

**Recommendation:** Only use prefix/postfix inside an expression when the reader can immediately understand both the **expression value** and the **side effect**. When multiple variables are modified, use standalone statements or intermediate variables.

## 5. `for` and `while` Loops

In a `for` loop, the update section usually does not need the value returned by `i++` or `++i`:

~~~java
for (int i = 0; i < 3; i++) {
    System.out.println("index=" + i);
}
~~~

Here changing `i++` to `++i` **does not change the sequence of printed values**, because the increment expression's result is unused. Both increment `i` by one at the end of each iteration.

The same applies to `while` loops:

~~~java
int remaining = 3;
while (remaining > 0) {
    System.out.println(remaining);
    remaining--;
}
~~~

Do not choose prefix over postfix merely thinking it is “always faster”. For primitive integer types in Java 17, choose the syntax that **expresses intent clearly**; actual performance depends on the compiler/JIT and context, not on this trick.

## 6. Overflow and Other Pitfalls

These operators do not automatically check for overflow on standard integer increments/decrements:

~~~java
int maximum = Integer.MAX_VALUE;
maximum++; // -2147483648, does not automatically throw ArithmeticException.

byte tiny = 127;
tiny++; // -128 because byte has range -128..127.
~~~

If you require **overflow detection** instead of accepting wrap-around results, use:

~~~java
int next = Math.incrementExact(Integer.MAX_VALUE); // Throws ArithmeticException.
int prev = Math.decrementExact(Integer.MIN_VALUE); // Throws ArithmeticException.
~~~

Another pitfall is combining assignment with postfix:

~~~java
int n = 5;
int previous = n++; // Easy to understand: previous=5, n=6.

// Avoid writing hard-to-read statements like: n = n++;
// The outer assignment can overwrite the newly updated value.
~~~

Writing `n = n++` does not increase the final value of `n`: `n++` returns the **old value**, and then the outer assignment writes that old value back. If you want to increment, simply write `n++;` or `n += 1;`.

## 7. Runnable Java 17+ Example

Create the file **`PrefixPostfixDemo.java`**:

~~~java
public final class PrefixPostfixDemo {
    public static void main(String[] args) {
        int a = 5;
        int postIncrement = a++;
        System.out.println("postIncrement=" + postIncrement + ",a=" + a);

        int b = 5;
        int preIncrement = ++b;
        System.out.println("preIncrement=" + preIncrement + ",b=" + b);

        int c = 5;
        int postDecrement = c--;
        System.out.println("postDecrement=" + postDecrement + ",c=" + c);

        int d = 5;
        int preDecrement = --d;
        System.out.println("preDecrement=" + preDecrement + ",d=" + d);

        int count = 0;
        count++;
        ++count;
        count--;
        --count;
        System.out.println("standaloneCount=" + count);

        int[] numbers = {10, 20, 30};
        int index = 0;
        int selected = numbers[index++];
        System.out.println("arraySelection=" + selected + ",index=" + index);

        int n = 1;
        int combined = n++ + ++n;
        System.out.println("combined=" + combined + ",n=" + n);

        int overwritten = 5;
        overwritten = overwritten++;
        System.out.println("assignmentTrap=" + overwritten);

        byte tiny = 127;
        tiny++;
        System.out.println("byteOverflow=" + tiny);

        int maximum = Integer.MAX_VALUE;
        maximum++;
        System.out.println("intOverflow=" + maximum);

        try {
            Math.incrementExact(Integer.MAX_VALUE);
        } catch (ArithmeticException ex) {
            System.out.println("incrementExact=ArithmeticException");
        }

        Integer boxed = 4;
        boxed++;
        System.out.println("boxed=" + boxed);

        for (int i = 0; i < 3; i++) {
            System.out.println("loop=" + i);
        }
    }
}
~~~

Run in the directory containing the file (Bash, PowerShell, or Command Prompt):

~~~bash
javac -encoding UTF-8 PrefixPostfixDemo.java
java PrefixPostfixDemo
~~~

**Exact expected stdout:**

~~~text
postIncrement=5,a=6
preIncrement=6,b=6
postDecrement=5,c=4
preDecrement=4,d=4
standaloneCount=0
arraySelection=10,index=1
combined=4,n=3
assignmentTrap=5
byteOverflow=-128
intOverflow=-2147483648
incrementExact=ArithmeticException
boxed=5
loop=0
loop=1
loop=2
~~~

The `postIncrement` and `preIncrement` lines show that the variable increments in both cases, but **the returned value** differs; `combined` confirms the update order, `assignmentTrap` warns against combining postfix with outer assignment, and `byteOverflow` and `intOverflow` illustrate overflow without throwing an exception automatically.

## 8. Practice Exercises

**Exercise 1.** Given `int x = 8; int y = x++;`, determine `x` and `y`. Compare with `int x = 8; int y = ++x;`.

**Exercise 2.** Given `int x = 8; int y = x--;` and `int x = 8; int y = --x;`, which value differs between the two cases?

**Exercise 3.** Predict `int i = 1; int result = i++ + ++i;`. Rewrite it as multiple statements without changing the result.

**Exercise 4.** Given `int[] arr = {4, 5, 6}; int i = 0;`, explain which element `arr[i++]` returns and what `i` equals afterward.

**Exercise 5.** Why does `int x = 5; x = x++;` still leave `x` equal to 5? Write a simpler way to increment it.

**Exercise 6.** Check `byte x = 127; x++;` and explain how to use `Math.incrementExact` when a program needs to detect `int` overflow.

### Key Takeaway

**Prefix `++x`/`--x` returns the value after updating; postfix `x++`/`x--` returns the value before updating.** Both modify the variable during the current expression. If you do not use the expression value, pick the readable form. Avoid mixing multiple increments/decrements with assignment and other side effects; consider `Math.incrementExact`/`decrementExact` when overflow detection is required.