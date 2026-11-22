# Comparing `boolean` Values and Relational Operator Limits in Java

> **Java core — language-basics / Comparisons**  
> **Version:** Java 17+; standalone example, JDK only.  
> **Goal:** Know how to use `==` and `!=` to compare two `boolean` values; understand why `<`, `<=`, `>`, and `>=` cannot be used with `boolean`; distinguish comparison operators from logical operators and handle nullable `Boolean` properly.

## 1. `boolean` Has Only Two Values

The primitive type `boolean` represents a logical condition, with exactly two values: `true` and `false`:

~~~java
boolean isReady = true;
boolean isDone = false;
~~~

`boolean` **is not an integer type** in Java: you cannot implicitly convert `true` to 1, `false` to 0, or vice versa. Therefore:

~~~java
// DOES NOT COMPILE:
// boolean flag = 1;
// int number = true;
// boolean equal = (true == 1);
~~~

There is no need to write `if (isReady == true)` for ordinary condition checks; `if (isReady)` is more readable. For negation, use `!isReady`.

## 2. `==` and `!=` Are Valid for `boolean`

The equality and inequality operators apply to **two `boolean` expressions**:

~~~java
boolean a = true;
boolean b = false;

boolean same = (a == b);      // false
boolean different = (a != b); // true
boolean sameAsTrue = (a == true); // true, though usually unnecessary to write out.
~~~

| Left-hand side | Right-hand side | `a == b` | `a != b` |
| --- | --- | --- | --- |
| `true` | `true` | `true` | `false` |
| `true` | `false` | `false` | `true` |
| `false` | `true` | `false` | `true` |
| `false` | `false` | `true` | `false` |

**Meaning:** `==` returns `true` if both logical values are the same; `!=` returns `true` if they differ. The result of the comparison also has type `boolean`, and can be used in `if`, `while`, or another logical expression.

## 3. Why Can't `<`, `<=`, `>`, `>=` Be Used with `boolean`?

**Relational operators** are used to compare the ordering of **numeric values** in Java and do not accept `boolean` operands.

~~~java
// The following lines are INVALID examples, intentionally commented out so the program does not fail:
// boolean smaller = false < true;
// boolean greater = true > false;
// boolean atLeast = true >= false;
// boolean atMost = false <= true;
~~~

Java does not define primitive rules such as `false < true` or `true > false`, even though some other languages treat false/true as 0/1.

Valid comparisons with numeric types and `char`:

~~~java
int minimum = 3, maximum = 7;
boolean less = minimum < maximum; // true
boolean range = minimum >= 0 && maximum <= 10; // true
boolean charOrder = 'A' < 'B'; // true: char participates in comparison by character code value.
~~~

| Operator | `int`, `long`, `float`, `double`, `char` | `boolean` |
| --- | --- | --- |
| `==`, `!=` | Valid | Valid |
| `<`, `<=` | Valid | **Invalid** |
| `>`, `>=` | Valid | **Invalid** |

Note: this table covers **primitive types**. `String` also cannot be ordered using `<`/`>`; use `compareTo` or an appropriate `Comparator` when sorting strings.

## 4. Comparison Operators vs. Logical Operators

Once you have `boolean` values, you can combine or negate conditions using logical operators:

| Operator | Meaning for `boolean` | Skips right-hand side? |
| --- | --- | --- |
| `!a` | NOT: flips `true`/`false` | Unary operator |
| `a && b` | Short-circuit AND | Yes, if `a` is `false` |
| `a \|\| b` | Short-circuit OR | Yes, if `a` is `true` |
| `a & b` | Non-short-circuit AND | No |
| `a \| b` | Non-short-circuit OR | No |
| `a ^ b` | XOR, true only when values differ | No |

~~~java
boolean ready = true;
boolean finished = false;

boolean allowed = ready && !finished; // true
boolean any = ready || finished;      // true
boolean exactlyOne = ready ^ finished; // true
~~~

On two `boolean` values, `^` produces the same **logical result** as `!=`, but they should not be swapped arbitrarily because their intent can differ: `!=` emphasizes **inequality comparison**, whereas `^` emphasizes **XOR**. For booleans, both sides of `^` are always evaluated.

**Short-circuiting is critical when `null` or error-prone operations are involved:**

~~~java
String name = null;
boolean hasName = name != null && !name.isBlank(); // false, no NPE.
~~~

The right-hand side is skipped because the left condition is `false`. Reversing it to `!name.isBlank() && name != null` would fail before the guard is applied.

## 5. When You Need Ordering Between Two Boolean Values, Specify It Explicitly

Sometimes business logic needs to sort `false` **before** `true`, such as sorting a list of statuses. Do **not** write `false < true`.

Java provides a method for this:

~~~java
int order = Boolean.compare(false, true); // -1
int equal = Boolean.compare(true, true);  // 0
int reverse = Boolean.compare(true, false); // 1
~~~

`Boolean.compare(a, b)` returns negative/0/positive when `a` comes before/equals/comes after `b` in **false-before-true** order. This is an **API-defined ordering**, not `<` becoming a valid operator for `boolean`.

If business logic needs the reverse order, you can swap the two arguments or use a `Comparator` as needed; avoid arbitrarily encoding booleans as numbers just to compare them when unnecessary.

## 6. Distinguishing `boolean` and `Boolean`

`boolean` is a primitive type that **cannot be `null`**. `Boolean` is a reference wrapper class; a `Boolean` variable can hold `true`, `false`, or `null`:

~~~java
boolean primitive = true;
Boolean boxed = Boolean.TRUE;
Boolean unknown = null;
~~~

There are three pitfalls to keep in mind:

**(1) Comparing two `Boolean` objects with `==` compares references.**

When both operands are of reference type `Boolean`, `==` checks **object identity**; do not rely on it to compare **values** in general. Use `equals` or `Objects.equals` when comparing values, including nullable ones:

~~~java
import java.util.Objects;

// Inside a method:
Boolean first = Boolean.TRUE;
Boolean second = Boolean.TRUE;
boolean sameValue = Objects.equals(first, second); // true
~~~

Do not rely on `first == second` coincidentally returning true when objects are cached/interned or created from different sources.

**(2) Comparing a `Boolean` with literal `true` or `false` triggers unboxing.**

~~~java
Boolean unknown = null;
// boolean result = (unknown == true); // If executed: NullPointerException.
~~~

In the expression `unknown == true`, Java must unbox `unknown` to `boolean`. If it is `null`, a `NullPointerException` is thrown.

**(3) Safe nullable checks:**

~~~java
Boolean unknown = null;
boolean enabled = Boolean.TRUE.equals(unknown); // false, no NPE.
boolean known = unknown != null;                 // false.
~~~

`Boolean.TRUE.equals(unknown)` returns true **only when** the value is `Boolean.TRUE`; both `false` and `null` return false. If the application needs to distinguish three states (*true / false / unknown*), check for null separately instead of treating unknown as false.

## 7. Standalone Runnable Java 17+ Example

Create the file **BooleanComparisonDemo.java**:

~~~java
import java.util.Objects;

public final class BooleanComparisonDemo {
    private static boolean logged(
            StringBuilder order, String name, boolean value) {
        order.append(name);
        return value;
    }

    public static void main(String[] args) {
        boolean ready = true;
        boolean done = false;

        System.out.println("primitiveEqual=" + (ready == done));
        System.out.println("primitiveNotEqual=" + (ready != done));
        System.out.println("negation=" + !done);
        System.out.println("logicalAnd=" + (ready && done));
        System.out.println("logicalOr=" + (ready || done));
        System.out.println("logicalXor=" + (ready ^ done));

        int low = 3;
        int high = 7;
        System.out.println("numericLess=" + (low < high));
        System.out.println("charLess=" + ('A' < 'B'));

        Boolean boxedTrue = Boolean.TRUE;
        Boolean boxedNull = null;
        System.out.println("boxedValue="
                + Boolean.TRUE.equals(boxedTrue));
        System.out.println("nullSafe="
                + Boolean.TRUE.equals(boxedNull));
        System.out.println("bothNull="
                + Objects.equals(boxedNull, null));

        boolean guarded = boxedNull != null && boxedNull;
        System.out.println("nullGuard=" + guarded);

        try {
            boolean unboxed = boxedNull == true;
            System.out.println("unboxed=" + unboxed);
        } catch (NullPointerException ex) {
            System.out.println("unboxNull=NullPointerException");
        }

        System.out.println("booleanOrdering="
                + Boolean.compare(false, true));

        String a = new String("Java");
        String b = new String("Java");
        System.out.println("stringValue=" + a.equals(b));
        System.out.println("stringReference=" + (a == b));

        StringBuilder order = new StringBuilder();
        boolean shortAnd = logged(order, "F", false)
                && logged(order, "X", true);
        boolean eagerAnd = logged(order, "A", false)
                & logged(order, "B", true);
        System.out.println("shortAnd=" + shortAnd);
        System.out.println("eagerAnd=" + eagerAnd);
        System.out.println("evaluationOrder=" + order);
    }
}
~~~

Compile and run in the directory containing the file (Bash, PowerShell, or Command Prompt):

~~~bash
javac -encoding UTF-8 BooleanComparisonDemo.java
java BooleanComparisonDemo
~~~

**Exact expected stdout:**

~~~text
primitiveEqual=false
primitiveNotEqual=true
negation=true
logicalAnd=false
logicalOr=true
logicalXor=true
numericLess=true
charLess=true
boxedValue=true
nullSafe=false
bothNull=true
nullGuard=false
unboxNull=NullPointerException
booleanOrdering=-1
stringValue=true
stringReference=false
shortAnd=false
eagerAnd=false
evaluationOrder=FAB
~~~

Explanation of the last line: F returns false so `&&` skips X; the boolean `&` operator still evaluates both A and B, so the trace is `FAB`. The `unboxNull` line demonstrates the exception when comparing a nullable `Boolean` with primitive `true`, not a limitation of `==` on two primitive `boolean` values.

## 8. Self-Check Exercises

**Exercise 1.** Given `boolean a = true, b = false;`, evaluate `a == b`, `a != b`, `!a`, `a && b`, `a || b`, and `a ^ b`.

**Exercise 2.** Explain why `true < false`, `false >= true`, and `true == 1` do not compile in Java. Can `'A' < 'B'` be used? Why?

**Exercise 3.** When you need to sort statuses with false before true, which API should you use instead of `a < b`? Give an example.

**Exercise 4.** Given `Boolean flag = null;`, what happens with `flag == true`? Compare the result with `Boolean.TRUE.equals(flag)`.

**Exercise 5.** Explain the difference between `boolean` and `Boolean`, and between `Objects.equals(a, b)` and `a == b` when `a` and `b` are `Boolean` references.

### Remember

**Two `boolean` values can be compared with `==` and `!=`, but cannot be used with `<`, `<=`, `>`, or `>=`.** A boolean is not an integer. Use `!`, `&&`, `||`, and logical operators when working with conditions; use `Boolean.compare` if you genuinely need false/true ordering. With reference `Boolean`, watch out for object identity comparison and `null` during unboxing.
