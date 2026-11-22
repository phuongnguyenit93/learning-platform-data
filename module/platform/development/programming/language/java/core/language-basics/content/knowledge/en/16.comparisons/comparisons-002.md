# `==` and `!=` on Primitive Types — Java 17+

## 1. Purpose and Core Rules

In Java, the two equality operators on **primitive types** are:

- `a == b`: returns `true` if the two values are equal according to the rules of the data type.
- `a != b`: returns `true` if the two values are not equal according to the same rules.

**The result of both operators always has type `boolean`.** `!=` is the negation of `==` when evaluating the same two operands in the same state.

~~~java
int x = 7;
int y = 7;
int z = 9;

System.out.println(x == y); // true
System.out.println(x != z); // true
System.out.println(x == z); // false
~~~

For integers, Java compares **numeric values**, not memory addresses. For `boolean`, it compares true/false. For `float` and `double`, it compares according to floating-point rules, which have special cases such as `NaN`, `+0.0`, and `-0.0`.

This lesson covers **comparing primitive values**. The `==` operator between two object reference variables follows different rules; do not mechanically apply primitive reasoning to `String` or wrappers.

## 2. How Are Primitive Types Compared?

Java has eight primitive types:

| Category | Type | How do `==`/`!=` work? |
|---|---|---|
| Signed integers | `byte`, `short`, `int`, `long` | Compare numeric values after arithmetic conversion if needed |
| Unsigned UTF-16 code unit | `char` | Compare the numeric value of the code unit; can be compared with other numeric types |
| Floating-point | `float`, `double` | Compare floating-point values, with `NaN` and signed zero rules |
| Boolean logic | `boolean` | `true == true` and `false == false` are true; differing values are false |

Numeric types can be compared with one another arithmetically, such as `int == long` or `char == int`. However, **`boolean` cannot be mixed with numeric types**:

~~~java
boolean ready = true;
System.out.println(ready == true);  // true
System.out.println(ready != false); // true

// boolean invalid = ready == 1; // COMPILE ERROR: boolean cannot be compared with int
~~~

Java does not treat `true` as the integer 1 or `false` as the integer 0.

## 3. Comparing `int`, `long`, `byte`, `short`, and `char`

For numeric operands, Java applies **binary numeric promotion** before comparing:

1. If either operand is `double`, convert the other operand to `double`.
2. Otherwise, if either is `float`, convert to `float`.
3. Otherwise, if either is `long`, convert to `long`.
4. Otherwise, compare as `int`; `byte`, `short`, and `char` are promoted to `int`.

Examples:

~~~java
byte small = 10;
short medium = 10;
int count = 10;
long wide = 10L;

System.out.println(small == medium); // true
System.out.println(count == wide);   // true
System.out.println('A' == 65);       // true
System.out.println(10 != 11L);       // true
~~~

In `'A' == 65`, `char` holds the UTF-16 value 65 and is converted to `int` for comparison; this **does not mean** Java is comparing the `String` `"A"` with a number.

When comparing only **integer types** within their representable ranges, widening from `int` to `long` does not lose precision. However, when `float` or `double` is involved, converting very large integers **can introduce rounding**, which requires attention as shown later.

### Value and Type of a Comparison Expression

~~~java
int left = 4;
long right = 4L;

var same = left == right; // same has type boolean, value true
System.out.println(same); // true
~~~

`var` infers `boolean` from the `==` expression; it does not turn the comparison result into a number or a string.

## 4. `==` Is Not `=`

| Syntax | Meaning | Example |
|---|---|---|
| `=` | Assign a value to a variable | `x = 7;` |
| `==` | Check whether two values are equal | `x == 7` |
| `!=` | Check whether two values are different | `x != 7` |

An easy mistake to make:

~~~java
boolean allowed = false;
if (allowed = true) { // Valid, but ASSIGNS true instead of comparing
    System.out.println("entered");
}
~~~

**Expected output:**

~~~text
entered
~~~

In Java, the assignment `allowed = true` is an expression whose boolean value is `true`. The compiler accepts it, yet the program logic may be wrong.

To check a boolean, prefer:

~~~java
if (allowed) {
    // Only runs if allowed is already true
}
if (!allowed) {
    // Only runs if allowed is false
}
~~~

With an `int` variable, `if (x = 1)` is **invalid** because an `if` condition cannot be `int`; do not assume that same safeguard prevents accidental `boolean` assignment.

## 5. `float`/`double`: Exact Comparison of Represented Values, No Implicit Tolerance

The most common pitfall when using `==` with floating-point numbers:

~~~java
double calculated = 0.1 + 0.2;

System.out.println(calculated);        // 0.30000000000000004
System.out.println(calculated == 0.3); // false
System.out.println(calculated != 0.3); // true
~~~

`0.1`, `0.2`, and `0.3` cannot be represented exactly in finite binary. The expression `0.1 + 0.2` is rounded and produces a `double` value different from the represented value of the literal `0.3`.

**`==` does not automatically check "nearly equal".** Two numbers that both format as `0.30` to two decimal places do not necessarily share the exact same binary value.

~~~java
double difference = (0.1 + 0.2) - 0.3;
System.out.println(difference); // 5.551115123125783E-17
~~~

However, you should not conclude that `==` on `double` is **always wrong**: if the problem intentionally tests equality of the **represented floating-point values**, `==` is the valid operator. The issue is using it as a substitute for **equality within an error margin** without explicitly defining that tolerance.

## 6. `float` vs `double` Can Differ Despite Identical Decimal Literals

~~~java
float f = 0.1f;
double d = 0.1;

System.out.println((double) f); // 0.10000000149011612
System.out.println(f == d);     // false
~~~

`0.1f` is rounded to **binary32**, whereas `0.1` is a **binary64** literal. During comparison, `float f` is promoted to `double`, but **the precision already lost in float rounding is not recovered**.

General rule: identical decimal spelling **does not guarantee** that a `float` and a `double` hold the same value after type conversion.

## 7. Comparing Large Integers with Floating-Point Numbers: Rounding Trap

When an integer operand is converted to `float` or `double`, sufficiently large integers can **lose single-unit precision**.

~~~java
int exactInt = 16_777_217;          // 2^24 + 1
float roundedFloat = 16_777_216f;   // 2^24

System.out.println(exactInt == roundedFloat); // true
~~~

Seemingly paradoxical, yet valid: Java converts `int` to `float` via numeric promotion. At magnitude `2^24`, binary32 cannot represent every consecutive integer; `16_777_217` is rounded to `16_777_216f`, so the two operands end up equal.

Similarly:

~~~java
long exactLong = 9_007_199_254_740_993L;   // 2^53 + 1
double roundedDouble = 9_007_199_254_740_992d; // 2^53

System.out.println(exactLong == roundedDouble); // true
~~~

This **does not** mean the `long` has the same mathematical value as the original `double`; the `long` was converted to `double` for the comparison and lost one unit.

**Recommendation:** when business logic needs to compare IDs, counts, or monetary amounts as large integers, **stay within integer types** (`long`, or `BigInteger` if needed) instead of mixing with floating-point types.

## 8. `NaN`: The Exception to Equality and Inequality

~~~java
double nan = Double.NaN;
System.out.println(nan == nan); // false
System.out.println(nan != nan); // true
~~~

For primitive `float`/`double`, NaN is not equal to any value, including itself; `!=` returns `true` when NaN is involved. Use `Double.isNaN` or `Float.isNaN` to detect it, rather than comparing against the NaN constant. `Double.equals` and `Double.compare` follow different rules for wrappers and sort ordering; the dedicated lesson on **NaN** presents detailed examples.

## 9. `+0.0` and `-0.0` Are Equal Under `==`

~~~java
System.out.println(0.0 == -0.0); // true
System.out.println(0.0 != -0.0); // false
System.out.println(1.0 / -0.0);  // -Infinity
~~~

Signed zeros differ in their bit representations and can affect operations like reciprocals, but primitive `==` does not distinguish them. When requirements demand distinguishing zero signs or bit patterns, choose an API like `Double.compare` or `Double.doubleToRawLongBits` according to the contract.

## 10. Infinity and Finite Data

~~~java
System.out.println(Double.POSITIVE_INFINITY == Double.POSITIVE_INFINITY); // true
System.out.println(Double.POSITIVE_INFINITY != Double.NEGATIVE_INFINITY); // true
~~~

Infinities with the same sign are equal, and infinities with opposite signs differ under primitive `==`/`!=`. However, being equal to itself does not prove a number is finite: use `Double.isFinite` when inputs must be finite floating-point numbers.

## 11. When Is Approximate Equality Needed?

The value `0.1 + 0.2` differs from `0.3` in binary64 representation, so `==` returns `false`. If a problem needs to compare measured or computed results within **an allowed margin of error**, you must define the tolerance in terms of units and scale rather than substituting an arbitrary epsilon.

In the demo at the end of this lesson, `nearlyEqual(a, b, tolerance)` illustrates comparing with an absolute tolerance when **both inputs and the tolerance are finite**. The lesson **Comparing Floating-Point Numbers with Requirement-Appropriate Tolerance** analyzes absolute tolerance, relative tolerance, combined approaches, regions near 0, and overflow limits in full.

## 12. Distinguishing Primitive vs. Reference `==`

For primitives:

~~~java
int a = 1000;
int b = 1000;
System.out.println(a == b); // true
~~~

For two separately created `String` objects:

~~~java
String first = new String("Java");
String second = new String("Java");

System.out.println(first == second);      // false: two different references
System.out.println(first.equals(second)); // true: equal contents
~~~

**Do not treat `==` as a content comparison operator for objects.** It compares values for primitives, but between two compatible references it checks whether they refer to the same or different objects. `!=` distinguishes them accordingly.

An important detail involving wrappers:

~~~java
int primitive = 10;
Integer boxed = 10;

System.out.println(primitive == boxed); // true: Integer is unboxed for numeric comparison
~~~

However, `Integer` can be `null`:

~~~java
Integer nullable = null;
// System.out.println(primitive == nullable);
// Can throw NullPointerException when unboxing null.
~~~

Comparing **two wrapper references** without unboxing is not the same as comparing two primitives. When the goal is to compare **object values**, choose an appropriate comparison API such as `equals` or `Objects.equals`, based on your application's null-handling policy.

## 13. Common Compilation Errors and Logic Traps

| Wrong code or assumption | Problem | Correct approach |
|---|---|---|
| `if (x = 1)` with `x` as `int` | Assignment expression yields `int`, not `boolean` | `if (x == 1)` |
| `if (flag = true)` to compare boolean | Accidentally assigns `true`; code still compiles | `if (flag)` |
| `true == 1` | `boolean` does not convert to numbers | Compare `boolean` only with `boolean` |
| `'A' == 65` must be false due to different types | Numeric promotion compares numeric values | Result is `true` |
| `0.1 + 0.2 == 0.3` must be true | Binary64 representation error | Purposeful tolerance or exact decimal |
| `0.1f == 0.1` must be true | `float`/`double` store different approximations | Understand conversion before comparing |
| `nan == nan` must be true | NaN is not equal to any number, including itself | `Double.isNaN(nan)` |
| `0.0 != -0.0` must be true | Signed zeros compare equal | Compare bits if distinction is needed |
| `intLarge == floatValue` is always exact | `int` converted to `float` can round | Keep integer types when comparing large integers |
| `Integer a == Integer b` always compares numbers | If both are references, it can compare object identity | Use `equals` or unbox with null checks |
| `wrapper == primitive` never fails | A `null` wrapper throws NPE on unboxing | Check for `null` |
| `a != b` means "not nearly equal" | `!=` negates exact equality | Define tolerance for measured data |

## 14. Standalone Runnable Java 17 Example

Save the file as **`PrimitiveEqualityDemo.java`**:

~~~java
public final class PrimitiveEqualityDemo {
    private PrimitiveEqualityDemo() {}

    static boolean nearlyEqual(double a, double b, double tolerance) {
        if (!Double.isFinite(tolerance) || tolerance < 0) {
            throw new IllegalArgumentException("invalid tolerance");
        }
        if (!Double.isFinite(a) || !Double.isFinite(b)) {
            return false;
        }
        return Math.abs(a - b) <= tolerance;
    }

    public static void main(String[] args) {
        int a = 7;
        int b = 7;
        int c = 9;
        System.out.println("int equal=" + (a == b));
        System.out.println("int not equal=" + (a != c));

        byte small = 10;
        short medium = 10;
        System.out.println("byte short=" + (small == medium));

        int number = 10;
        long wide = 10L;
        System.out.println("int long=" + (number == wide));
        System.out.println("char numeric=" + ('A' == 65));

        boolean ready = true;
        boolean enabled = false;
        System.out.println("boolean equal=" + (ready == enabled));
        System.out.println("boolean not equal=" + (ready != enabled));

        double calculated = 0.1 + 0.2;
        System.out.println("decimal sum=" + calculated);
        System.out.println("decimal equal=" + (calculated == 0.3));
        System.out.println("decimal not equal=" + (calculated != 0.3));
        System.out.println("decimal near="
                + nearlyEqual(calculated, 0.3, 1e-12));

        float f = 0.1f;
        double d = 0.1;
        System.out.println("float double equal=" + (f == d));

        int exactInt = 16_777_217;
        float roundedFloat = 16_777_216f;
        System.out.println("int float equal=" + (exactInt == roundedFloat));

        long exactLong = 9_007_199_254_740_993L;
        double roundedDouble = 9_007_199_254_740_992d;
        System.out.println("long double equal=" + (exactLong == roundedDouble));

        double nan = Double.NaN;
        System.out.println("NaN equal=" + (nan == nan));
        System.out.println("NaN not equal=" + (nan != nan));
        System.out.println("isNaN=" + Double.isNaN(nan));

        System.out.println("signed zero equal=" + (0.0 == -0.0));
        System.out.println("signed zero not equal=" + (0.0 != -0.0));
        System.out.println("positive zero reciprocal=" + (1.0 / 0.0));
        System.out.println("negative zero reciprocal=" + (1.0 / -0.0));

        System.out.println("same infinity="
                + (Double.POSITIVE_INFINITY == (1.0 / 0.0)));
        System.out.println("opposite infinity="
                + (Double.POSITIVE_INFINITY != Double.NEGATIVE_INFINITY));

        Integer boxed = 10;
        System.out.println("boxed primitive=" + (boxed == number));
        Integer missing = null;
        try {
            System.out.println(number == missing);
        } catch (NullPointerException ex) {
            System.out.println("boxed null=NullPointerException");
        }

        String first = new String("Java");
        String second = new String("Java");
        System.out.println("reference equal=" + (first == second));
        System.out.println("content equal=" + first.equals(second));
    }
}
~~~

**Requirements:** JDK 17 or later, terminal in the directory containing `PrimitiveEqualityDemo.java`; no Maven/Gradle or external libraries beyond the JDK needed.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 PrimitiveEqualityDemo.java
java -cp . PrimitiveEqualityDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\PrimitiveEqualityDemo.java
java -cp . PrimitiveEqualityDemo
~~~

**Exact expected stdout:**

~~~text
int equal=true
int not equal=true
byte short=true
int long=true
char numeric=true
boolean equal=false
boolean not equal=true
decimal sum=0.30000000000000004
decimal equal=false
decimal not equal=true
decimal near=true
float double equal=false
int float equal=true
long double equal=true
NaN equal=false
NaN not equal=true
isNaN=true
signed zero equal=true
signed zero not equal=false
positive zero reciprocal=Infinity
negative zero reciprocal=-Infinity
same infinity=true
opposite infinity=true
boxed primitive=true
boxed null=NullPointerException
reference equal=false
content equal=true
~~~

### Surprising Lines Explained

- `int long=true`: the integer value 10 remains exact when widened from `int` to `long`.
- `char numeric=true`: `'A'` has numeric value 65.
- `decimal equal=false`: `0.1 + 0.2` and `0.3` do not have the same binary64 value.
- `float double equal=false`: `0.1f` and `0.1` are rounded at different precisions.
- `int float equal=true` / `long double equal=true`: **converting types for comparison can lose precision**, not that the original integers were mathematically equal.
- `NaN equal=false`, `NaN not equal=true`: special NaN rules.
- `signed zero equal=true`: `+0.0` and `-0.0` are equal under `==`, even though their reciprocals produce infinities with opposite signs.
- `boxed primitive=true`: unboxing enables numeric comparison, while a null wrapper causes an NPE.
- `reference equal=false`: `==` between two `String` references does not compare content; `equals` returns true.

## 15. Exercises with Answers

### Exercise A — Primitives of Different Types

~~~java
byte a = 65;
char b = 'A';
System.out.println(a == b);
~~~

**Answer:** `true`, because numeric promotion converts both operands to `int` with the same value 65.

### Exercise B — Boolean and Number

~~~java
boolean active = true;
// System.out.println(active == 1);
~~~

**Answer:** uncommenting the commented line causes a **compile error**. Java does not compare `boolean` with `int`.

### Exercise C — NaN

~~~java
double x = Double.NaN;
System.out.println(x == x);
System.out.println(x != x);
~~~

**Answer:**

~~~text
false
true
~~~

Use `Double.isNaN(x)` when you want to detect NaN.

### Exercise D — Floating-Point Precision Error

~~~java
double sum = 0.1 + 0.2;
System.out.println(sum == 0.3);
~~~

**Answer:** `false`. If the goal is approximate equality within an allowed tolerance, define a tolerance rule; if the business logic requires exact decimal arithmetic, consider `BigDecimal` constructed from a string.

### Exercise E — Large Integer and Float

~~~java
int n = 16_777_217;
float f = 16_777_216f;
System.out.println(n == f);
~~~

**Answer:** `true`, because `n` is rounded when converted to `float` before comparison.

### Exercise F — `=` vs `==`

~~~java
boolean ok = false;
if (ok = true) {
    System.out.println("entered");
}
~~~

**Answer:** prints `entered`. This **assigns** `true` to `ok` instead of checking its previous value.

### Exercise G — Reference or Primitive?

~~~java
int a = 5, b = 5;
String x = new String("5");
String y = new String("5");
System.out.println(a == b);
System.out.println(x == y);
System.out.println(x.equals(y));
~~~

**Answer:**

~~~text
true
false
true
~~~

`int` is compared by value; `String` requires `equals` to compare content.

## 16. Checklist and Conclusion

- [ ] Know that `==` tests equality, `!=` tests inequality, and both return `boolean`.
- [ ] Distinguish `=` (assignment) from `==` (comparison).
- [ ] Understand that `boolean` can only be compared with compatible boolean expressions.
- [ ] Know that `byte`, `short`, and `char` can be promoted to `int` during comparison.
- [ ] Know that `int` and `long` can be compared accurately when widening `int` -> `long`.
- [ ] Recognize that numeric promotion to `float`/`double` can lose precision on large integers.
- [ ] Never treat `==` on floating-point numbers as "nearly equal".
- [ ] Know that `NaN == NaN` is false and `NaN != NaN` is true.
- [ ] Know that `+0.0 == -0.0` is true, even though their bit patterns and some operations distinguish them.
- [ ] Know that infinities of the same sign compare equal; finite data requires separate validation.
- [ ] Know how to define tolerance based on domain/units when approximate equality is needed.
- [ ] Distinguish primitive comparison from reference identity; wrappers can unbox and encounter `null`.
- [ ] Compile/run `PrimitiveEqualityDemo.java` with `javac`/`java` and verify the exact stdout.

**Conclusion:** For Java 17+ primitives, `==`/`!=` check **values**, not references. Numeric types apply numeric promotion before comparing; floating-point types require special attention to representation error, NaN, signed zeros, and conversions from large integers to `float`/`double`. Use exact operators when you want **exact value equality**, and define tolerance rules when you want **approximate equality** as required by the problem.
