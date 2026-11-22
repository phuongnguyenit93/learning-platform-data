# Chained Assignment and Why It Should Be Limited in Java

> **Java core — language-basics / Assignment and Unary Operators**  
> **Version:** Java 17+; single-file examples, no external libraries required.  
> **Objective:** Understand how `a = b = c = value` is grouped, why an assignment expression has a value and must be type-compatible; recognize issues with readability, evaluation order, side effects, and multiple references pointing to the same object.

## 1. What Is Chained Assignment?

An assignment `left = right` stores the value of the right-hand side into the variable specified on the left-hand side. Java allows an **assignment expression** to appear on the right-hand side of another assignment:

~~~java
int a, b, c;
a = b = c = 7;
System.out.println(a + "," + b + "," + c); // 7,7,7
~~~

The assignment operator `=` is **right-associative**. The grouping of the line above is:

~~~text
a = (b = (c = 7))
~~~

Walkthrough for simple variables:

1. `c = 7` assigns 7 to `c`; this entire expression has value 7.
2. `b = (c = 7)` receives 7 and assigns it to `b`.
3. `a = (b = (c = 7))` receives 7 and assigns it to `a`.

At the end, all three variables equal 7. **Chained assignment does not declare new variables**: `a`, `b`, and `c` must already exist and their types must be compatible.

## 2. An Assignment Expression Has a Value and a Type

For a simple assignment, the expression `variable = expression` carries **the assigned value** and has the type of the variable on the left. Therefore, it can be used inside another assignment:

~~~java
int left, right;
left = right = 12; // Both receive 12.
~~~

Not every chained assignment requires all variables to have the exact same type. Each assignment step must be valid under Java's type conversion rules:

~~~java
int whole;
double decimal;
decimal = whole = 3; // Valid: whole receives int 3, decimal receives double 3.0.
~~~

Conversely:

~~~java
int whole;
double decimal;
// whole = decimal = 3.5; // Compile error: cannot assign double to int.
~~~

**Key takeaway:** Java does not arbitrarily infer a single common type just because the assignments are on the same line. Parentheses show the **grouping**, while type-compatibility rules still apply to each individual assignment.

A chained assignment can contain other expressions:

~~~java
int a, b, c = 2;
a = b = c + 5; // a = 7, b = 7, c remains 2.
~~~

Here `c + 5` **does not reassign** `c`. Distinguish `c + 5` from `c += 5`: the latter modifies `c`.

## 3. Reference Variables: Assigning the Same Object, Not Cloning the Object

With reference types, chained assignment can cause multiple variables to point to **the same object**:

~~~java
int[] first, second;
first = second = new int[] {10, 20};

first[0] = 99;
System.out.println(second[0]); // 99
~~~

The expression `new int[] {10, 20}` creates **a single array**. The two assignments only copy the **reference** value; they do not create two independent arrays. Therefore, modifying an element through `first` is also visible through `second`.

If you need two separate objects, create or copy them intentionally, for example:

~~~java
int[] first = {10, 20};
int[] second = first.clone(); // New array with copied elements.
~~~

With mutable objects, using chained assignment without noticing shared references can create hard-to-trace bugs. With immutable types like `String`, sharing references is generally lower risk, but you must still understand assignment semantics.

## 4. Why Should Chained Assignment Be Limited?

| Issue | Example or Consequence | Clearer Expression |
| --- | --- | --- |
| Hard to read how data flows through variables | `a = b = c = compute();` | Create a named intermediate value, then assign each variable explicitly |
| Easy to overlook incompatible types | `int x; double y; x = y = 1.5;` | Convert types intentionally, separating each assignment |
| Obscures that multiple variables share a reference | `x = y = new int[3];` | Name variables to show sharing, or clone/create separately |
| Mixes side effects | `array[i++] = array[i++] = 8;` | Separate index selection from assignment |
| Hard to set step-by-step breakpoints/logs | One line modifies multiple variables | One statement modifies one variable when business logic is complex |
| Easy to confuse grouping with evaluation order | Right-associative assignment does not mean every subexpression runs right-to-left | Split steps or use parentheses with intermediate variables |

Chained assignment is **not technically wrong**. For a short example like `a = b = 0;`, the intent may be very clear. But when state, objects, method calls, or array indices are involved, **prioritize readability and testability over minimizing line count**.

### One Call Does Not Run Three Times

~~~java
int a, b, c;
a = b = c = calculate();
~~~

`calculate()` is called **once**; its result is used for all three assignments. If you want three **independently** computed values, you must call the method separately for each variable:

~~~java
a = calculate();
b = calculate();
c = calculate();
~~~

This is a critical business difference when `calculate()` reads the current time, generates random numbers, or mutates state.

## 5. Associativity Is Not the Evaluation Order of Side Effects

`a = b = c = value` groups **from right to left**, yet with a **complex left-hand side** such as an array access, Java still follows its rules for **expression evaluation order**.

~~~java
int[] values = {1, 2, 3};
int i = 0;

values[i++] = values[i++] = 8;
~~~

In the outer array assignment, Java evaluates the array reference and **the left-hand index** before evaluating the assignment expression on the right. The first `i++` selects `values[0]`; the second selects `values[1]`; then both positions receive 8. The result is `values = {8, 8, 3}` and `i = 2`.

Do not infer from “assignment is right-associative” that the `i++` on the right **always** runs first. Associativity determines the **expression tree**, while evaluation order follows a different rule.

**Clearer way to write it:**

~~~java
int firstIndex = i++;
int secondIndex = i++;
values[secondIndex] = 8;
values[firstIndex] = 8;
~~~

The step-by-step version may be longer, but it lets you inspect, edit, and set breakpoints at each step. In practice, if you do not need the side effect of `i++`, choose explicit indices and avoid nested assignments.

## 6. Runnable Java 17+ Program

Create the file **ChainedAssignmentDemo.java**:

~~~java
public final class ChainedAssignmentDemo {
    private static int callCount;

    private static int calculate() {
        callCount++;
        return 42;
    }

    public static void main(String[] args) {
        int a, b, c;
        a = b = c = 7;
        System.out.println("basic=" + a + "," + b + "," + c);

        a = b = c + 5;
        System.out.println("expression=" + a + "," + b + "," + c);

        a = b = c = calculate();
        System.out.println("calculated=" + a + "," + b + "," + c);
        System.out.println("calls=" + callCount);

        int whole;
        double decimal;
        decimal = whole = 3;
        System.out.println("mixedTypes=" + whole + "," + decimal);

        boolean active, visible;
        active = visible = true;
        System.out.println("booleans=" + active + "," + visible);

        String left, right;
        left = right = new String("ready");
        System.out.println("sameStringReference=" + (left == right));

        int[] first, second;
        first = second = new int[] {10, 20};
        first[0] = 99;
        System.out.println("sharedArray=" + first[0] + "," + second[0]);

        int[] indexed = {1, 2, 3};
        int i = 0;
        indexed[i++] = indexed[i++] = 8;
        System.out.println("indexed=" + indexed[0] + ","
                + indexed[1] + "," + indexed[2]);
        System.out.println("indexAfter=" + i);
    }
}
~~~

Run in the directory containing the file (Bash, PowerShell, or Command Prompt):

~~~bash
javac -encoding UTF-8 ChainedAssignmentDemo.java
java ChainedAssignmentDemo
~~~

**Exact expected stdout:**

~~~text
basic=7,7,7
expression=12,12,7
calculated=42,42,42
calls=1
mixedTypes=3,3.0
booleans=true,true
sameStringReference=true
sharedArray=99,99
indexed=8,8,3
indexAfter=2
~~~

Cross-check: `expression=12,12,7` shows that `c` does not change when only `c + 5` is used; `calls=1` confirms the method was called once; `sameStringReference=true` and `sharedArray=99,99` show that assignment shares references. `indexed` illustrates why, when there are side effects on the left-hand side, you must not rely solely on right-to-left grouping.

## 7. More Readable Alternatives

If a result is used multiple times, consider a meaningful variable name:

~~~java
int defaultLimit = 100;
int readLimit = defaultLimit;
int writeLimit = defaultLimit;
~~~

To initialize variables to the same starting value in a simple way:

~~~java
int x = 0;
int y = 0;
~~~

When calling a method with side effects, decide explicitly between **one shared result** or **separately computed results**. When working with objects/arrays, decide explicitly between **sharing a reference** or **creating a copy**.

You do not have to eliminate every `a = b = 0;`; avoid chained assignment when `=` appears too many times, when variables have different business meanings, or when assignment affects state that needs to be traced individually.

## 8. Self-Check Exercises

**Exercise 1.** Rewrite `a = b = c = 5;` with parentheses showing its grouping. What is the value of each variable after the statement?

**Exercise 2.** Given `int c = 2; int a, b; a = b = c + 5;`, what are the values of `a`, `b`, and `c`? What changes if you write `a = b = (c += 5);`?

**Exercise 3.** Why is `double d; int i; d = i = 3;` valid while `i = d = 3.5;` is invalid?

**Exercise 4.** Given two array variables `x` and `y` assigned from the same `new int[2]`, does modifying `x[0]` change `y[0]`? Write how to create separate arrays if sharing is not wanted.

**Exercise 5.** Explain why the expression `array[i++] = array[i++] = 8;` is hard to maintain even though Java clearly specifies its grouping and evaluation order.

### Key Takeaway

**Chained assignment uses the right-associativity of `=`: `a = b = c = value` groups as `a = (b = (c = value))`.** Each assignment must be type-compatible; reference values are **copied**, not cloned as objects. **Limit chained assignment** when there is complex state, side effects, arrays, or shared objects, because separate statements usually make intent clearer and testing easier.