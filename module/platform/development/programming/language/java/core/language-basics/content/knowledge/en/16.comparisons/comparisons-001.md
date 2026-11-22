# Relational Operators `<`, `<=`, `>`, and `>=` for Numeric Values — Java 17+

Java provides four **relational operators** to check the ordering of two numeric values. Each comparison takes **two operands** and returns a **`boolean`**:

| Operator | Meaning | Example | Result |
| --- | --- | --- | --- |
| `a < b` | `a` is less than `b` | `3 < 5` | `true` |
| `a <= b` | `a` is less than **or equal to** `b` | `5 <= 5` | `true` |
| `a > b` | `a` is greater than `b` | `9 > 5` | `true` |
| `a >= b` | `a` is greater than **or equal to** `b` | `5 >= 9` | `false` |

**Important distinction:** `<` and `>` are **strict** comparisons that do not include equality; `<=` and `>=` include the case where both values are equal. The symbols `<=` and `>=` are written together without a space; `=<` and `=>` are not Java operators.

~~~java
int age = 18;
boolean adult = age >= 18;   // true.
boolean minor = age < 18;    // false.
~~~

The operator does not modify the value of `age`. It only produces a `boolean` result that can be used in `if`, `while`, `&&`, `||`, or a boolean variable.

## 1. Boundary Conditions and Truth Values

For two normal numeric values that do not contain NaN:

| Case | `a < b` | `a <= b` | `a > b` | `a >= b` |
| --- | --- | --- | --- | --- |
| `a = 3`, `b = 5` | true | true | false | false |
| `a = 5`, `b = 5` | false | true | false | true |
| `a = 9`, `b = 5` | false | false | true | true |

An easy way to remember this is that a `<=` or `>=` condition is true **when either the "less/greater than" condition or the "equal to" condition is satisfied**.

Do not confuse them with `==` and `!=`: those check for **equality/inequality**, not ordering. Likewise, `a >= b` does not mean "`a` is different from `b`".

## 2. Standalone Runnable Java 17+ Demo

Create a UTF-8 file named **`NumericRelationalDemo.java`**:

~~~java
public class NumericRelationalDemo {
    public static void main(String[] args) {
        int a = 7;
        int b = 10;

        System.out.println("less=" + (a < b));
        System.out.println("lessOrEqual=" + (a <= b));
        System.out.println("greater=" + (a > b));
        System.out.println("greaterOrEqual=" + (a >= b));

        System.out.println("equalLess=" + (a < a));
        System.out.println("equalLessOrEqual=" + (a <= a));
        System.out.println("equalGreater=" + (a > a));
        System.out.println("equalGreaterOrEqual=" + (a >= a));

        char firstLetter = 'A';
        char secondLetter = 'B';
        System.out.println("charComparison="
                + (firstLetter < secondLetter));

        int whole = 5;
        double fraction = 5.5;
        System.out.println("mixedIntDouble="
                + (whole < fraction));
        System.out.println("mixedLongDouble="
                + (10L > 9.5));

        Integer boxedInt = 7;
        Long boxedLong = 8L;
        System.out.println("wrapperComparison="
                + (boxedInt < boxedLong));

        int preciseInt = 16_777_217;
        float roundedFloat = 16_777_216f;
        System.out.println("intFloatGreater="
                + (preciseInt > roundedFloat));
        System.out.println("intFloatLessOrEqual="
                + (preciseInt <= roundedFloat));

        double nan = Double.NaN;
        System.out.println("nanLess=" + (nan < 5.0));
        System.out.println("nanLessOrEqual=" + (nan <= 5.0));
        System.out.println("nanGreater=" + (nan > 5.0));
        System.out.println("nanGreaterOrEqual=" + (nan >= 5.0));
        System.out.println("notNanGreater="
                + (!(nan > 5.0)));
        System.out.println("isNaN=" + Double.isNaN(nan));

        double positiveZero = 0.0;
        double negativeZero = -0.0;
        System.out.println("zeroLess="
                + (negativeZero < positiveZero));
        System.out.println("zeroLessOrEqual="
                + (negativeZero <= positiveZero));
        System.out.println("zeroGreaterOrEqual="
                + (negativeZero >= positiveZero));

        System.out.println("positiveInfinityGreater="
                + (Double.POSITIVE_INFINITY > Double.MAX_VALUE));
        System.out.println("negativeInfinityLess="
                + (Double.NEGATIVE_INFINITY < -Double.MAX_VALUE));
        System.out.println("infinityGreaterOrEqualSelf="
                + (Double.POSITIVE_INFINITY
                        >= Double.POSITIVE_INFINITY));

        Integer missing = null;
        try {
            boolean unused = missing < 10;
            System.out.println("unexpected=" + unused);
        } catch (NullPointerException ex) {
            System.out.println("nullUnboxing=NullPointerException");
        }

        int overflowed = Integer.MAX_VALUE + 1;
        System.out.println("overflowedValue=" + overflowed);
        System.out.println("overflowedGreaterZero="
                + (overflowed > 0));
        long promotedBeforeAdd = (long) Integer.MAX_VALUE + 1;
        System.out.println("safeGreaterZero="
                + (promotedBeforeAdd > 0));

        boolean inRange = (a >= 0) && (a < b);
        System.out.println("inRange=" + inRange);
    }
}
~~~

Using **JDK 17 or later**, open PowerShell (Windows) or Bash (Linux/macOS) in the directory containing the file:

~~~bash
java -version
javac -version
javac -encoding UTF-8 NumericRelationalDemo.java
java NumericRelationalDemo
~~~

**Exact expected stdout** of the `java NumericRelationalDemo` command alone:

~~~text
less=true
lessOrEqual=true
greater=false
greaterOrEqual=false
equalLess=false
equalLessOrEqual=true
equalGreater=false
equalGreaterOrEqual=true
charComparison=true
mixedIntDouble=true
mixedLongDouble=true
wrapperComparison=true
intFloatGreater=false
intFloatLessOrEqual=true
nanLess=false
nanLessOrEqual=false
nanGreater=false
nanGreaterOrEqual=false
notNanGreater=true
isNaN=true
zeroLess=false
zeroLessOrEqual=true
zeroGreaterOrEqual=true
positiveInfinityGreater=true
negativeInfinityLess=true
infinityGreaterOrEqualSelf=true
nullUnboxing=NullPointerException
overflowedValue=-2147483648
overflowedGreaterZero=false
safeGreaterZero=true
inRange=true
~~~

The output of `java -version` and `javac -version` depends on the installed JDK, so it is not included in the fixed expected stdout block.

## 3. Operand Types and Binary Numeric Promotion

These four relational operators apply to **numeric types**: `byte`, `short`, `char`, `int`, `long`, `float`, `double`, and appropriate numeric wrapper classes that get **unboxed**. When the two operands have different types, Java applies **binary numeric promotion** before comparing.

| Two operand types | Type used during comparison | Example |
| --- | --- | --- |
| `byte` and `short` | `int` | `(byte) 1 < (short) 2` |
| `char` and `int` | `int` | `'A' < 66` |
| `int` and `long` | `long` | `5 < 6L` |
| `int` and `float` | `float` | `5 < 5.5f` |
| `long` and `double` | `double` | `10L > 9.5` |
| `float` and `double` | `double` | `1.5f < 2.0` |
| `Integer` and `Long` | Unboxed then compared as `long` | `Integer.valueOf(7) < Long.valueOf(8)` |

**The type of a comparison expression is always `boolean`**, not `int`/`double`. In `int n = 3; boolean result = n < 5;`, `n` remains an `int` and `result` is a `boolean`.

### Comparing `char`

`char` is an **unsigned UTF-16 code unit**, so Java compares the **numeric value of the code unit**, rather than using natural-language lexicographical order:

~~~java
char a = 'A';
char b = 'B';
System.out.println(a < b); // true: 65 < 66.
~~~

Use `Collator` or appropriate string comparison rules if the problem involves sorting names/strings according to natural language. Do not treat comparing two `char` values as a complete text-comparison engine.

### Wrappers and the `null` Risk

~~~java
Integer number = 7;
System.out.println(number < 10); // true due to unboxing.

Integer missing = null;
// boolean check = missing < 10; // Throws NullPointerException at runtime.
~~~

Because relational operators require primitive numeric values, an eligible wrapper is unboxed. If the wrapper is `null`, unboxing throws a `NullPointerException`. Before comparing potentially missing data, define a null-handling rule, for example:

~~~java
Integer input = null;
boolean valid = input != null && input >= 0;
// false; the right-hand side of && does not run if input is null.
~~~

For reference types such as `String`, `Boolean`, or objects that are not unboxable numeric values, `<`/`<=`/`>`/`>=` are invalid.

## 4. Comparing Integers and Floating-Point Numbers: Rounding During Promotion

Not every comparison between `int`/`long` and `float`/`double` preserves the ability to distinguish every individual integer.

`float` has about **24 bits of significand precision**. Two distinct large integers can become the exact same value when converted to `float`:

~~~java
int preciseInt = 16_777_217;
float roundedFloat = 16_777_216f;

System.out.println(preciseInt > roundedFloat);  // false.
System.out.println(preciseInt <= roundedFloat); // true.
~~~

At the comparison, `preciseInt` is converted to `float` and rounded to **16_777_216f**, which equals `roundedFloat`. This is not Java "comparing incorrectly"; the result follows the **type-conversion rules applied before comparison**.

`double` has about **53 bits of significand precision**, so very large `long` values can run into the same issue when compared against `double`.

If your business logic requires exact comparisons of very large integers, choose an appropriate representation and operand types (for example, both `long`, or `BigInteger.compareTo` when exceeding the `long` range) instead of silently converting to approximate floating-point values.

## 5. Special Floating-Point Cases: NaN, Infinity, and Signed Zero

The relational operators `<`, `<=`, `>`, and `>=` all return `false` when an operand is `NaN`; therefore, negating a relational expression is not necessarily equivalent to the opposite relation:

~~~java
double x = Double.NaN;
System.out.println(x > 5.0);    // false
System.out.println(!(x > 5.0)); // true
System.out.println(x <= 5.0);   // false
~~~

Use `Double.isNaN(x)` to detect NaN; when data must only be finite numbers, use `Double.isFinite(x)` to reject both NaN and infinity.

`Double.POSITIVE_INFINITY` is greater than every finite `double`; `Double.NEGATIVE_INFINITY` is less than every finite `double`. The two values `+0.0` and `-0.0` are neither less than nor greater than each other under primitive relational operators, so both `<=` and `>=` between them are true. APIs such as `Double.compare` and `Double.equals` have their own rules for NaN and signed zeros, which are explained in detail in the lesson **NaN and Counterintuitive Comparison Results**.

## 6. Syntax, Precedence, and Compound Conditions

These four operators have **lower precedence than addition/multiplication**, but **higher precedence than `&&` and `||`**:

~~~java
int price = 8;
int tax = 2;
boolean affordable = price + tax <= 10; // true.

boolean range = (price >= 0) && (price < 10); // true.
~~~

Parentheses help make the meaning of a range condition clear:

~~~java
int value = 7;
boolean inRange = value >= 0 && value < 10; // true.
~~~

Java **does not support chaining three values in mathematical notation like `0 <= x < 10`**:

~~~java
int x = 7;
// boolean invalid = 0 <= x < 10; // Compilation error.
boolean valid = (0 <= x) && (x < 10);
~~~

The expression `0 <= x` already returns a `boolean`, which cannot serve as a numeric operand for the subsequent `< 10` comparison. You must split it into two comparisons joined with `&&`.

Note that relational operators return `boolean`, so you cannot directly add or subtract two relational results as if they were integers.

## 7. Overflow in **Expressions Before** Comparison

Using the right relational operator is not enough if an operand was already computed incorrectly due to overflow:

~~~java
int a = Integer.MAX_VALUE;
int overflowed = a + 1;

System.out.println(overflowed);     // -2147483648.
System.out.println(overflowed > 0); // false.
~~~

`a + 1` is evaluated as an `int` before the comparison takes place. When you need a result larger than `int`, **promote the type before the arithmetic operation**, rather than casting the result afterward:

~~~java
int a = Integer.MAX_VALUE;

long correct = (long) a + 1;
System.out.println(correct > 0); // true.
~~~

If the requirements call for **reporting an error on overflow** instead of widening to `long`, consider `Math.addExact`; for integers beyond the `long` range, use `BigInteger.compareTo`. For decimal calculations requiring exact precision, consider `BigDecimal.compareTo` and explicitly manage the scale/rounding policy.

## 8. Numeric Comparison and String Comparison Are Different Things

~~~java
int number = 12;
System.out.println(number > 9); // true.

// String text = "12";
// boolean invalid = text > "9"; // Compilation error.
~~~

`String` is not a numeric type, even when it contains digits. To compare **numeric values**, you must parse/validate first:

~~~java
int parsed = Integer.parseInt("12");
boolean numericGreater = parsed > 9; // true.
~~~

To compare **lexicographical order of Strings**, use `String.compareTo(...)` or an appropriate comparator instead of the `>` operator. For example, `"12".compareTo("9") < 0` follows character-based lexicographical ordering, which differs from comparing the numbers 12 and 9.

## 9. Common Mistakes

| Misconception | Correct understanding |
| --- | --- |
| "`<`/`<=` return 0 or 1." | They return `boolean` |
| "`a <= b` is only true when `a` is less than `b`." | It is also true when they are equal (except in special cases like NaN) |
| "`0 <= x < 10` is valid in Java." | No; you must write `0 <= x && x < 10` |
| "Comparing two numeric wrappers with `<` compares addresses." | Numeric wrappers are unboxed to compare numeric values |
| "Comparing a null wrapper with a number returns false." | It throws `NullPointerException` due to unboxing |
| "Comparing `int` with `float` is always completely exact." | Numeric promotion can round large integers |
| "`!(x > y)` is always the same as `x <= y`." | False when `x` or `y` is NaN |
| "`+0.0` is less than `-0.0` because their sign bits differ." | They are equal under primitive relational comparisons |
| "Adding `> 0` automatically fixes operand overflow." | Overflow must be handled **before** comparing |

## 10. Self-Check Exercises

1. If `int a = 5, b = 5;`, what are `a < b`, `a <= b`, `a > b`, and `a >= b`?  
   *Answer:* `false`, `true`, `false`, `true`.
2. What does `char a = 'A'; boolean c = a < 'B';` produce?  
   *Answer:* `true`, because it compares UTF-16 code unit values 65 and 66.
3. Is `Integer a = 4; Long b = 5L; boolean c = a < b;` valid?  
   *Answer:* Yes; unboxing and numeric promotion yield `true`.
4. What happens with `Integer x = null; boolean c = x < 10;`?  
   *Answer:* `NullPointerException` upon unboxing.
5. What are `Double.NaN >= 0.0` and `!(Double.NaN < 0.0)` respectively?  
   *Answer:* `false` and `true`.
6. Why can `int x = 16_777_217; float f = 16_777_216f; x > f` evaluate to false?  
   *Answer:* `x` is converted to `float` and rounded to a value equal to `f`.
7. Write the condition `10 <= score <= 20` in Java.  
   *Answer:* `score >= 10 && score <= 20`.
8. What does `(Integer.MAX_VALUE + 1) > 0` evaluate to?  
   *Answer:* `false`, because the `int` addition overflows before the comparison.

## Checklist

- [ ] Distinguish `<`, `<=`, `>`, `>=` and remember that all results are `boolean`.
- [ ] Apply relational comparisons to numeric values, not to `String`/`boolean`.
- [ ] Understand wrapper **unboxing** and **binary numeric promotion**.
- [ ] Watch out for precision loss when comparing large integers with `float`/`double`.
- [ ] With NaN, all four relational comparisons are false; `!(a > b)` is not always the same as `a <= b`.
- [ ] Understand that `+0.0` and `-0.0` compare equal relationally.
- [ ] Write range conditions as two comparisons joined by `&&`.
- [ ] Check operand expressions for overflow before relying on the comparison result.

**Conclusion:** `<`, `<=`, `>`, and `>=` are the **relational operators for numeric values** in Java. Using them properly requires not only remembering the symbols, but also understanding the **numeric types being compared**, **type promotion**, **NaN**, and **any arithmetic operations occurring before the comparison**.
