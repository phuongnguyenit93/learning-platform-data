# ArithmeticException with Integer Operations and Exact Operations in Java

`ArithmeticException` is an **unchecked exception** under the `RuntimeException` branch. In Java Core, it is especially important in two groups of situations: **integer division/remainder with a divisor of 0**, and **operations that require an exact result but exceed the range of an integer type**, such as `Math.addExact`, `Math.multiplyExact`, or `Math.toIntExact`.

A common misconception is that **not every arithmetic error or every overflow case automatically creates an `ArithmeticException`**. Ordinary `+`, `-`, and `*` operations on `int` and `long` can overflow and produce a *wraparound* result without throwing an error. Conversely, the `Math.*Exact` family of functions proactively detects overflow and throws `ArithmeticException`. Floating-point division of `double` by `0.0` also behaves differently from integer division by `0`.

This lesson belongs to Java Core – Exception, in the **Runtime Exceptions** context, and focuses on operation semantics, quotient/remainder signs, integer overflow, `Math.*Exact`, related arithmetic exceptions, and safe handling in Java 17+.

## 1. Position of `ArithmeticException` in the Exception Hierarchy

Hierarchy:

~~~text
java.lang.Object
    |
    +-- java.lang.Throwable
          |
          +-- java.lang.Exception
                |
                +-- java.lang.RuntimeException
                      |
                      +-- java.lang.ArithmeticException
~~~

Because it is a subtype of `RuntimeException`:

- Java **does not require** methods to declare `throws ArithmeticException`.
- Callers **are not forced** to write `catch (ArithmeticException e)`.
- The exception can still propagate and cause the task to fail if left unhandled.
- A `catch (ArithmeticException)` catches it; a `catch (RuntimeException)` or `catch (Exception)` also catches it if placed appropriately.
- When catching multiple branches, place **narrower** handlers before superclass handlers to avoid unreachable handlers.

Example:

~~~java
static int divide(int a, int b) {
    return a / b;
}
~~~

The method above compiles even without declaring `throws`. If `b == 0`, the `a / b` operation with `int` will throw `ArithmeticException` at runtime.

Do not use `Error` to represent division by 0 in an application. `ArithmeticException` is a normal runtime error within the semantics of Java operations, not evidence that the JVM has broken down.

## 2. Integer Division `/` and Remainder `%` When the Divisor Is 0

For operands of integer types, both **division `/`** and **remainder `%`** are undefined when the denominator is `0`. Java reflects this with `ArithmeticException`.

~~~java
int a = 10;
int zero = 0;

System.out.println(a / zero); // Throws ArithmeticException.
~~~

This snippet **intentionally triggers a runtime error**, not an example to be run verbatim without a handler.

Similarly:

~~~java
int remainder = 10 % 0; // ArithmeticException at runtime.
~~~

With `long`:

~~~java
long value = 10L;
long divisor = 0L;

long result = value / divisor; // ArithmeticException.
~~~

With `byte` and `short`, Java performs **binary numeric promotion**, so many expressions are evaluated as `int` operations. The integer division/remainder by 0 rule still applies.

Example:

~~~java
byte left = 7;
byte right = 0;
int result = left / right; // ArithmeticException.
~~~

**Do not confuse:** `%` is the remainder operator, not division returning a quotient. Even though the desired result is the remainder, a denominator of 0 still causes an exception.

### What is checked at runtime?

The nature of `/` or `%` using integer operands: if the divisor is 0, the operation does not produce a valid integer value. When that operation is executed, Java throws `ArithmeticException`.

Do not write tests that depend on the literal `getMessage()` text such as `"/ by zero"`: message representations and environments may differ. Check the **exception type**, error condition, and necessary data instead of parsing strings.

## 3. Integer Division Truncates Toward 0, Not Floor

Java divides two integers by **discarding the fractional part and rounding toward 0** (*truncate toward zero*):

~~~java
System.out.println(7 / 3);     // 2
System.out.println(-7 / 3);    // -2
System.out.println(7 / -3);    // -2
System.out.println(-7 / -3);   // 2
~~~

For example, `-7 / 3` is `-2`, not `-3`. This differs from `Math.floorDiv(-7, 3)`, which returns `-3`.

Comparison table:

| Expression | Result |
| --- | ---: |
| `7 / 3` | `2` |
| `-7 / 3` | `-2` |
| `7 / -3` | `-2` |
| `-7 / -3` | `2` |
| `Math.floorDiv(-7, 3)` | `-3` |
| `Math.floorDiv(7, -3)` | `-3` |

Do not rely on the intuition that "dividing negative numbers always rounds down" when working with the Java integer `/` operator.

### The `%` operator takes the sign of the dividend

In Java integer remainder, the result (if non-zero) has the same sign as the **dividend**:

~~~java
System.out.println(7 % 3);     // 1
System.out.println(-7 % 3);    // -1
System.out.println(7 % -3);    // 1
System.out.println(-7 % -3);   // -1
~~~

This is not a modulo operation that always produces a non-negative number. If you need *floor division* and the remainder following the same convention, use `Math.floorDiv` and `Math.floorMod` where appropriate.

For `a` and `b != 0`, the mathematical relationship for ordinary integer division/remainder is:

~~~text
a = (a / b) * b + (a % b)
~~~

However, when represented with fixed-width integer types, be careful of overflow in intermediate expressions and the **special case `MIN_VALUE / -1`** described later.

## 4. How `Math.floorDiv` and `Math.floorMod` Differ from `/` and `%`

Java provides methods in `Math`:

~~~java
Math.floorDiv(int x, int y)
Math.floorDiv(long x, long y)
Math.floorMod(int x, int y)
Math.floorMod(long x, long y)
~~~

There are also suitable overloads for `long` and `int` operands in some APIs. The key points:

- `/` rounds the quotient **toward 0**.
- `floorDiv` selects the quotient by **floor** — toward negative infinity.
- `%` pairs with division that truncates toward 0.
- `floorMod` is the remainder paired with `floorDiv`, so when non-zero, its sign generally follows the **divisor**.

~~~java
System.out.println(-7 / 3);                 // -2
System.out.println(-7 % 3);                 // -1
System.out.println(Math.floorDiv(-7, 3));   // -3
System.out.println(Math.floorMod(-7, 3));   // 2
~~~

Table:

| Dividend | Divisor | `/` | `%` | `floorDiv` | `floorMod` |
| ---: | ---: | ---: | ---: | ---: | ---: |
| `7` | `3` | `2` | `1` | `2` | `1` |
| `-7` | `3` | `-2` | `-1` | `-3` | `2` |
| `7` | `-3` | `-2` | `1` | `-3` | `-2` |
| `-7` | `-3` | `2` | `-1` | `2` | `-1` |

**Important:** `Math.floorDiv(x, 0)` and `Math.floorMod(x, 0)` with integers **still throw `ArithmeticException`**. They change the rounding/remainder rule, not make division by 0 valid.

Also do not confuse `floorDiv` with "overflow-checked division." It is not an `Exact` function that guarantees detection of all overflows.

## 5. Special Case: `MIN_VALUE / -1` Does Not Throw `ArithmeticException`

This is a very important edge case of signed integers.

`int` uses 32 bits, with the range:

~~~text
Integer.MIN_VALUE = -2147483648
Integer.MAX_VALUE =  2147483647
~~~

The mathematical value of:

~~~text
-2147483648 / -1 = 2147483648
~~~

is greater than `Integer.MAX_VALUE`. **However, the Java integer division operator does not throw `ArithmeticException` in this special case.** The result is `Integer.MIN_VALUE`.

~~~java
int result = Integer.MIN_VALUE / -1;
System.out.println(result);
// -2147483648
~~~

The same holds for `long`:

~~~java
long result = Long.MIN_VALUE / -1L;
System.out.println(result);
// -9223372036854775808
~~~

This is **language-defined behavior**, not random hardware behavior.

### Why do learners often guess wrong?

They reason that "division producing a value outside the `int` range must throw `ArithmeticException`." This is **not true for the ordinary `/` operator**: only a divisor of 0 directly causes an exception for integer division; `MIN_VALUE / -1` specifically has a defined overflow result.

For `Integer.MIN_VALUE % -1`, the remainder is `0`.

~~~java
System.out.println(Integer.MIN_VALUE % -1); // 0
~~~

If an application requires accurately detecting every overflow case, **it cannot rely solely on `ArithmeticException` from the `/` operator**. You need to check the special case before dividing:

~~~java
static int divideSafely(int a, int b) {
    if (b == 0) {
        throw new ArithmeticException("division by zero");
    }
    if (a == Integer.MIN_VALUE && b == -1) {
        throw new ArithmeticException("integer division overflow");
    }
    return a / b;
}
~~~

This is a valid Java method. It provides an **overflow-checked application contract** that is clearer than the default `/` operator. For `long`, replace with `Long.MIN_VALUE` and `-1L`.

Do not confuse this application method with a Java 17 `Math.divideExact` API: this lesson does not assume JDK 17 provides such an overload. Use the check shown above if you need that guarantee on Java 17.

## 6. `+`, `-`, and `*` on `int`, `long` Do Not Automatically Report Overflow

By default, Java's fixed-width integer arithmetic **does not throw `ArithmeticException` on overflow** when adding, subtracting, or multiplying.

~~~java
int a = Integer.MAX_VALUE;
System.out.println(a + 1);
// -2147483648
~~~

~~~java
int b = Integer.MIN_VALUE;
System.out.println(b - 1);
// 2147483647
~~~

~~~java
int c = 50_000 * 50_000;
System.out.println(c);
// -1794967296
~~~

The mathematical value of `50_000 × 50_000` is `2_500_000_000`, which is greater than `Integer.MAX_VALUE`. With 32-bit representation, the result wraps around to `-1794967296`.

For `long`:

~~~java
long value = Long.MAX_VALUE;
System.out.println(value + 1L);
// -9223372036854775808
~~~

These results can cause very hard-to-detect business logic bugs if used for money, counters, deadlines, capacity, or element counts.

**Do not assume Java automatically protects you with `ArithmeticException` when an ordinary integer operation exceeds the type's range.**

## 7. `Math.addExact`: Overflow-Checked Addition

`Math.addExact` has overloads for `int` and `long`:

~~~java
int x = Math.addExact(20, 22); // 42
~~~

If the mathematical result does not fit in the return type's range, it throws `ArithmeticException`:

~~~java
int x = Math.addExact(Integer.MAX_VALUE, 1);
// Throws ArithmeticException.
~~~

With `long`:

~~~java
long x = Math.addExact(Long.MAX_VALUE, 1L);
// Throws ArithmeticException.
~~~

Comparison:

| Operation | When not overflowing | When overflowing |
| --- | --- | --- |
| `a + b` | Returns sum | Wraparound result, does not throw automatically |
| `Math.addExact(a, b)` | Returns sum | Throws `ArithmeticException` |

`addExact` is suitable when **counts must not wrap around**, such as total processed elements, controlled byte counts, or indices with strict invariants.

For monetary amounts, only use `Math.addExact` after you have clearly defined the **storage unit**, range limits, exchange rates, rounding, and accounting requirements. `addExact` only checks integer type overflow; it does not solve monetary precision/scale on its own.

## 8. `Math.subtractExact`: Overflow-Checked Subtraction

~~~java
int remaining = Math.subtractExact(100, 35); // 65
~~~

Overflow:

~~~java
int value = Math.subtractExact(Integer.MIN_VALUE, 1);
// ArithmeticException.
~~~

Comparison:

~~~java
int wrapped = Integer.MIN_VALUE - 1;
System.out.println(wrapped);
// 2147483647
~~~

`Math.subtractExact` also has a corresponding `long` overload.

**Watch the signs:** subtracting a positive number from the smallest negative number can underflow the bottom of the type's range. These bugs often do not show up through a simple `result < 0` check because the result wraps around to a positive number.

## 9. `Math.multiplyExact`: Overflow-Checked Multiplication

~~~java
int area = Math.multiplyExact(200, 300);
// 60000
~~~

Overflow:

~~~java
int huge = Math.multiplyExact(50_000, 50_000);
// ArithmeticException.
~~~

With `long`:

~~~java
long tooLarge = Math.multiplyExact(Long.MAX_VALUE, 2L);
// ArithmeticException.
~~~

This is a useful tool in size calculations:

~~~java
static int requiredBytes(int elements, int bytesPerElement) {
    if (elements < 0 || bytesPerElement < 0) {
        throw new IllegalArgumentException("negative size");
    }
    return Math.multiplyExact(elements, bytesPerElement);
}
~~~

This method validates non-negative inputs and then uses exact multiplication so it does not silently produce an incorrect size. Note: `requiredBytes` still only describes multiplying two integers; memory allocation requires additional practical checks for array limits, available memory, and other API rules.

### Multiplying before casting to `long` is a common mistake

Wrong:

~~~java
int a = 50_000;
int b = 50_000;
long product = a * b;  // Overflows int first, then widens.
~~~

The resulting `product` is `-1794967296L` rather than `2_500_000_000L`.

If you want to compute in the `long` range:

~~~java
long product = (long) a * b;
// 2500000000
~~~

Or:

~~~java
long product = Math.multiplyExact((long) a, (long) b);
// 2500000000
~~~

If the final operation must stay within `int`, use `Math.multiplyExact(a, b)` to **report overflow**, rather than silently widening and truncating.

## 10. `Math.incrementExact` and `Math.decrementExact`

For incrementing/decrementing by exactly one unit:

~~~java
int next = Math.incrementExact(9);      // 10
int previous = Math.decrementExact(9);  // 8
~~~

At the boundaries:

~~~java
Math.incrementExact(Integer.MAX_VALUE);
// ArithmeticException.

Math.decrementExact(Integer.MIN_VALUE);
// ArithmeticException.
~~~

Both have overloads for `long`.

Conversely:

~~~java
int x = Integer.MAX_VALUE;
x++;  // Value wraps around to Integer.MIN_VALUE.
~~~

Do not write `x++` on a counter that **must not overflow** and expect `ArithmeticException` to be thrown automatically. Use `Math.incrementExact` and decide the policy when the limit is reached.

### Example of a counter with a contract

~~~java
static int countOneMore(int current) {
    if (current < 0) {
        throw new IllegalArgumentException("negative count");
    }
    return Math.incrementExact(current);
}
~~~

This method distinguishes two kinds of issues:

- A negative current value violates the precondition → `IllegalArgumentException`.
- A value that has already reached `Integer.MAX_VALUE` → `ArithmeticException` from exact increment.

In an application, `ArithmeticException` can be wrapped into a domain error type if the caller needs a specific message/context. Do not conflate it with "all counting errors are caused by invalid input data."

## 11. `Math.negateExact` and `Math.absExact`

Normally:

~~~java
int x = -12;
System.out.println(-x);             // 12
System.out.println(Math.abs(x));    // 12
~~~

However, signed integers have **one more negative value than positive values**. There is no positive `int` corresponding to the magnitude of `Integer.MIN_VALUE`.

Therefore:

~~~java
int a = -Integer.MIN_VALUE;
System.out.println(a);
// -2147483648
~~~

And:

~~~java
System.out.println(Math.abs(Integer.MIN_VALUE));
// -2147483648
~~~

This is the default behavior: `-MIN_VALUE` and `Math.abs(MIN_VALUE)` for integers can wrap, **without throwing an exception automatically**.

To check:

~~~java
Math.negateExact(Integer.MIN_VALUE);
// ArithmeticException.
~~~

Since Java 17, `Math.absExact` can be used similarly:

~~~java
Math.absExact(Integer.MIN_VALUE);
// ArithmeticException.
~~~

With `long`, `Long.MIN_VALUE` is the corresponding boundary case.

### Why can `Math.abs(value)` be dangerous?

An algorithm computing an array index or hash bucket via:

~~~java
int index = Math.abs(hash) % capacity;
~~~

can return a negative result if `hash == Integer.MIN_VALUE`, even when `capacity > 0`. For choosing a bucket with a positive size, consider:

~~~java
int index = Math.floorMod(hash, capacity);
~~~

When `capacity > 0`, `floorMod` returns a remainder in the range `0` to `capacity - 1`. If `capacity == 0`, it still throws `ArithmeticException`; therefore, check the `capacity > 0` invariant beforehand.

## 12. `Math.toIntExact`: Checked Narrowing from `long` to `int`

An ordinary cast from `long` to `int` **does not report an error when high bits are lost**:

~~~java
long value = (long) Integer.MAX_VALUE + 1L;
int narrowed = (int) value;
System.out.println(narrowed);
// -2147483648
~~~

`Math.toIntExact(long)` checks whether the `long` value can be represented as an `int`.

~~~java
int ok = Math.toIntExact(42L); // 42
~~~

~~~java
int failed = Math.toIntExact(
        (long) Integer.MAX_VALUE + 1L);
// ArithmeticException.
~~~

This is especially useful when a newer API uses `long` while a legacy system accepts `int`; without exact conversion, bit truncation can lead to negative indices or wrong sizes.

**Note:** `Math.toIntExact` does not check application conditions such as "the result must be non-negative" or "must not exceed array size"; it only ensures the value fits within the `int` range.

## 13. Summary: Which Integer Operations Throw `ArithmeticException`?

| Expression / API | When dividing by 0 | When overflowing |
| --- | --- | --- |
| `int/long /` | Throws `ArithmeticException` | `MIN_VALUE / -1` specifically does not throw, returns `MIN_VALUE` |
| `int/long %` | Throws `ArithmeticException` | `MIN_VALUE % -1` returns `0` |
| `int/long +`, `-`, `*` | Not applicable | Wraps, does not throw automatically |
| `++`, `--` | Not applicable | Wraps, does not throw automatically |
| Unary `-` | Not applicable | `-MIN_VALUE` wraps |
| `Math.floorDiv`/`floorMod` | Throws `ArithmeticException` | Does not guarantee overflow checking |
| `Math.addExact` | Not applicable | Throws `ArithmeticException` |
| `Math.subtractExact` | Not applicable | Throws `ArithmeticException` |
| `Math.multiplyExact` | Not applicable | Throws `ArithmeticException` |
| `Math.incrementExact`/`decrementExact` | Not applicable | Throws `ArithmeticException` |
| `Math.negateExact`/`absExact` | Not applicable | Throws `ArithmeticException` for `MIN_VALUE` |
| `Math.toIntExact` | Not applicable | Throws when `long` is outside `int` range |

Do not assume "exact" means every arbitrary algorithm has an `Exact`-named version in JDK 17. The APIs above have specific purposes; check the documentation of your target JDK before using a method name just because it shares a similar suffix.

## 14. Floating-Point `float` and `double` Division by 0 Differs from Integers

`ArithmeticException` for a `0` denominator is tied to **integer** division and `%` operations. For `float`/`double`, Java uses special values according to IEEE 754 semantics and does not automatically throw an error just for dividing by `0.0`:

~~~java
System.out.println(1.0 / 0.0);                // Infinity
System.out.println(-1.0 / 0.0);               // -Infinity
System.out.println(0.0 / 0.0);                // NaN
System.out.println(Double.isNaN(1.0 % 0.0)); // true
~~~

Operand types matter: `5 / 2` returns `2`, whereas `5.0 / 2` returns `2.5`. `Double.isFinite(value)` helps verify a finite result before passing it into business logic that requires a valid floating-point number.

**Do not cast to `double` just to avoid an integer division-by-zero exception**: doing so can silently turn the error into `Infinity`/`NaN` and corrupt downstream calculations. The lesson on *distinguishing floating-point division by 0 from integer division by 0* analyzes numeric promotion, `-0.0` sign, `%`, and testing special values in depth; the focus of this lesson remains integer operations and `Math.*Exact`.

## 15. How Do `BigInteger` and `BigDecimal` Relate?

`ArithmeticException` is not caused only by integer operators or `Math.*Exact`. Some other arithmetic APIs also use it when a calculation is invalid or cannot be represented as requested.

### `BigInteger`: no `int`/`long` range overflow, still cannot divide by 0

~~~java
java.math.BigInteger a =
        new java.math.BigInteger("999999999999999999999");

java.math.BigInteger b = a.multiply(a);
System.out.println(b.signum() > 0);
// true
~~~

`BigInteger` has arbitrary integer precision as needed instead of being limited to 32/64 bits, within memory resources and execution limits. However:

~~~java
java.math.BigInteger.TEN.divide(java.math.BigInteger.ZERO);
// ArithmeticException.
~~~

Just because `BigInteger` is large does not mean every operation is valid.

### `BigDecimal`: exact division may have no finite representation

~~~java
java.math.BigDecimal result =
        java.math.BigDecimal.ONE.divide(
                new java.math.BigDecimal("2"));

System.out.println(result); // 0.5
~~~

However:

~~~java
java.math.BigDecimal.ONE.divide(
        new java.math.BigDecimal("3"));
// ArithmeticException if an exact result is requested
// when the quotient has a non-terminating decimal expansion.
~~~

This is completely different from integer overflow: `1 / 3` has a non-terminating decimal expansion. The `BigDecimal.divide(BigDecimal)` form is not given a rounding strategy, so it throws `ArithmeticException` instead of silently producing an approximation.

If the contract accepts rounding:

~~~java
java.math.BigDecimal rounded =
        java.math.BigDecimal.ONE.divide(
                new java.math.BigDecimal("3"),
                2,
                java.math.RoundingMode.HALF_UP);

System.out.println(rounded);
// 0.33
~~~

Scale and rounding mode must be specified according to business rules; do not choose `HALF_UP` unconditionally for all monetary problems. Dividing by `BigDecimal.ZERO` is still invalid.

## 16. Standalone Java 17+ Program

The **`ArithmeticExactDemo.java`** file below clearly demonstrates:

1. Integer division/remainder and sign rules.
2. The `MIN_VALUE / -1` case not throwing an error.
3. Default overflow of `+` and `*`.
4. Division by 0 throwing `ArithmeticException`.
5. `Math.*Exact` methods throwing exceptions when out of range.
6. Narrowing cast vs. `Math.toIntExact`.
7. Floating-point and `BigDecimal` having their own behavior.

The program catches **only `ArithmeticException`** in the cases that intentionally trigger errors, without using `catch (Throwable)`.

~~~java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.RoundingMode;

public class ArithmeticExactDemo {

    public static void main(String[] args) {
        System.out.println("== integer division ==");
        System.out.println("7 / 3=" + (7 / 3));
        System.out.println("-7 / 3=" + (-7 / 3));
        System.out.println("-7 % 3=" + (-7 % 3));
        System.out.println("floorDiv=" + Math.floorDiv(-7, 3));
        System.out.println("floorMod=" + Math.floorMod(-7, 3));
        System.out.println("int MIN / -1="
                + (Integer.MIN_VALUE / -1));
        System.out.println("long MIN / -1="
                + (Long.MIN_VALUE / -1L));

        System.out.println("== ordinary overflow ==");
        System.out.println("add wraps="
                + (Integer.MAX_VALUE + 1));
        System.out.println("multiply wraps="
                + (50_000 * 50_000));
        System.out.println("abs MIN="
                + Math.abs(Integer.MIN_VALUE));

        System.out.println("== division by zero ==");
        attempt("int / zero", () -> {
            int zero = 0;
            System.out.println(10 / zero);
        });
        attempt("int % zero", () -> {
            int zero = 0;
            System.out.println(10 % zero);
        });
        attempt("long / zero", () -> {
            long zero = 0L;
            System.out.println(10L / zero);
        });
        attempt("floorDiv zero", () -> Math.floorDiv(7, 0));

        System.out.println("== exact operations ==");
        System.out.println("addExact valid="
                + Math.addExact(20, 22));
        attempt("addExact", () ->
                Math.addExact(Integer.MAX_VALUE, 1));
        attempt("subtractExact", () ->
                Math.subtractExact(Integer.MIN_VALUE, 1));
        attempt("multiplyExact", () ->
                Math.multiplyExact(50_000, 50_000));
        attempt("long multiplyExact", () ->
                Math.multiplyExact(Long.MAX_VALUE, 2L));
        attempt("incrementExact", () ->
                Math.incrementExact(Integer.MAX_VALUE));
        attempt("decrementExact", () ->
                Math.decrementExact(Integer.MIN_VALUE));
        attempt("negateExact", () ->
                Math.negateExact(Integer.MIN_VALUE));
        attempt("absExact", () ->
                Math.absExact(Integer.MIN_VALUE));

        System.out.println("== long to int ==");
        long outsideInt = (long) Integer.MAX_VALUE + 1L;
        System.out.println("cast wraps=" + (int) outsideInt);
        System.out.println("toIntExact valid="
                + Math.toIntExact(42L));
        attempt("toIntExact", () ->
                Math.toIntExact(outsideInt));

        System.out.println("== floating point ==");
        System.out.println("double / zero=" + (1.0 / 0.0));
        System.out.println("double 0/0 NaN="
                + Double.isNaN(0.0 / 0.0));
        System.out.println("double % zero NaN="
                + Double.isNaN(1.0 % 0.0));

        System.out.println("== big numbers ==");
        attempt("BigInteger divide zero", () ->
                BigInteger.TEN.divide(BigInteger.ZERO));
        attempt("BigDecimal exact 1/3", () ->
                BigDecimal.ONE.divide(new BigDecimal("3")));
        System.out.println("BigDecimal rounded="
                + BigDecimal.ONE.divide(
                        new BigDecimal("3"),
                        2,
                        RoundingMode.HALF_UP));
    }

    static void attempt(String label, Runnable operation) {
        try {
            operation.run();
            System.out.println(label + " => OK");
        } catch (ArithmeticException e) {
            System.out.println(
                    label + " => ArithmeticException");
        }
    }
}
~~~

Compile and run:

~~~bash
javac ArithmeticExactDemo.java
java ArithmeticExactDemo
~~~

**Deterministic stdout for Java 17+:**

~~~text
== integer division ==
7 / 3=2
-7 / 3=-2
-7 % 3=-1
floorDiv=-3
floorMod=2
int MIN / -1=-2147483648
long MIN / -1=-9223372036854775808
== ordinary overflow ==
add wraps=-2147483648
multiply wraps=-1794967296
abs MIN=-2147483648
== division by zero ==
int / zero => ArithmeticException
int % zero => ArithmeticException
long / zero => ArithmeticException
floorDiv zero => ArithmeticException
== exact operations ==
addExact valid=42
addExact => ArithmeticException
subtractExact => ArithmeticException
multiplyExact => ArithmeticException
long multiplyExact => ArithmeticException
incrementExact => ArithmeticException
decrementExact => ArithmeticException
negateExact => ArithmeticException
absExact => ArithmeticException
== long to int ==
cast wraps=-2147483648
toIntExact valid=42
toIntExact => ArithmeticException
== floating point ==
double / zero=Infinity
double 0/0 NaN=true
double % zero NaN=true
== big numbers ==
BigInteger divide zero => ArithmeticException
BigDecimal exact 1/3 => ArithmeticException
BigDecimal rounded=0.33
~~~

### Why does the `attempt` helper only catch `ArithmeticException`?

`attempt(String, Runnable)` uses a `Runnable` callback, and `Runnable.run()` does not declare any checked exceptions. The operations in the lambdas above can throw unchecked `ArithmeticException`, so they remain valid.

The helper prints the **exception type name** instead of `e.getMessage()`, keeping the example independent of wording differences in runtime messages.

Do not change it to `catch (Exception e)` and treat every caught error as an arithmetic error: a `NullPointerException`, `IllegalArgumentException`, or another bug in callback code also falls under `Exception` but requires a different policy.

### Why does `Math.absExact` work in Java 17?

`Math.absExact` is provided in modern JDKs, including Java 17, and allows detecting the case where the absolute value of `Integer.MIN_VALUE`/`Long.MIN_VALUE` cannot be represented in the corresponding type.

Unlike `Math.abs`, it throws `ArithmeticException` for that boundary case. Therefore, the example includes both `Math.abs(Integer.MIN_VALUE)` and `Math.absExact(Integer.MIN_VALUE)` to highlight the difference.

### Why does `BigDecimal.ONE.divide(new BigDecimal("3"))` fail?

This API requires an exact result, but `1/3` has no finite decimal representation. You must choose a division overload with a suitable scale/rounding mode or `MathContext` if the application accepts a rounded result. This error is **not an `int` overflow**.

## 17. How to Check Before Integer Division

If the divisor comes from external input, you can validate early:

~~~java
static int safeQuotient(int dividend, int divisor) {
    if (divisor == 0) {
        throw new IllegalArgumentException(
                "divisor must not be zero");
    }
    return dividend / divisor;
}
~~~

This method turns an `ArithmeticException` operation error into an **`IllegalArgumentException` precondition error**, which has clearer semantics when the denominator is an API argument.

However, `safeQuotient(Integer.MIN_VALUE, -1)` still returns `Integer.MIN_VALUE`. If you also need **exactness regarding division overflow**, add a check for that case (like `divideSafely` in section 5).

### Precondition or catch exception?

There is no single rule, but typically:

- If `divisor == 0` is **invalid input known in advance**, checking beforehand reports the error cleanly per contract.
- If you are building an API that performs arithmetic and intentionally wants to preserve Java semantics, letting `ArithmeticException` propagate is reasonable.
- If a business fallback is needed, only perform it when the fallback is **designed and meaningful**.
- If the calculation involves transactions or state updates, avoid mutating data and only catching an error at the end without proper rollback/recovery.

Do not catch the exception and arbitrarily return `0`, because `0` can be a valid result and masking the error can lead to data inaccuracy.

## 18. Designing Exact Arithmetic APIs with Clear Errors

A helper that validates quantities before allocation:

~~~java
static int checkedArrayLength(
        int records, int elementsPerRecord) {
    if (records < 0 || elementsPerRecord < 0) {
        throw new IllegalArgumentException("negative quantity");
    }
    int total = Math.multiplyExact(records, elementsPerRecord);
    if (total > 1_000_000) {
        throw new IllegalArgumentException(
                "too many elements");
    }
    return total;
}
~~~

This is a valid Java method. It handles three cases:

1. Negative values → `IllegalArgumentException` precondition error.
2. Multiplication overflow → `ArithmeticException` from `Math.multiplyExact`.
3. Arithmetically valid result exceeding the application quota → `IllegalArgumentException` with a limit message.

This is an important example of distinguishing **arithmetic correctness** from **business rule validity**. `Math.multiplyExact` cannot decide on its own whether a request exceeds the program's resource quota.

### Wrapping errors at a business boundary when helpful

~~~java
static int calculateRequiredSlots(
        int groups, int slotsPerGroup) {
    try {
        return Math.multiplyExact(groups, slotsPerGroup);
    } catch (ArithmeticException cause) {
        throw new IllegalArgumentException(
                "requested slot count is too large", cause);
    }
}
~~~

This code translates overflow into an input error at a specific boundary and **preserves `cause`** for investigation. Only choose this wrapping when overflow genuinely means "request too large" in the contract, rather than a programming bug that the application expects to detect with another handler.

If the caller expects to receive `ArithmeticException` directly, letting it propagate can also be an appropriate choice.

## 19. Common Mistakes When Using Exact Arithmetic

### 19.1. Thinking `int` overflow always throws `ArithmeticException`

Wrong. `Integer.MAX_VALUE + 1`, `Integer.MIN_VALUE - 1`, and `50_000 * 50_000` wrap by default.

### 19.2. Thinking `MIN_VALUE / -1` throws overflow

Wrong for the Java integer division operator. This is a defined special case that returns `MIN_VALUE`. If you need an error reported, check this condition yourself in Java 17.

### 19.3. Seeing `Math.floorDiv` and assuming it detects all overflows

Wrong. `floorDiv` is for floor rounding rules, not an exact overflow-checking API family.

### 19.4. Using `Math.abs` to guarantee a non-negative number

Wrong when the input is `Integer.MIN_VALUE` or `Long.MIN_VALUE`. Use `Math.absExact` when you need to detect the unrepresentable case.

### 19.5. Thinking `Math.toIntExact` is the same as casting `(int)`

Wrong. Casting can lose bits and return a completely different value; `toIntExact` throws `ArithmeticException` when out of range.

### 19.6. Casting to `long` after already multiplying `int`s

Wrong. `long total = a * b;` performs `int` multiplication first if both operands are `int`. Cast one operand **before** multiplying or use `Math.multiplyExact` with the desired type.

### 19.7. Using floating-point numbers to dodge division by 0

`double` divided by `0.0` produces `Infinity`/`NaN` rather than throwing. That does not guarantee a valid business result.

### 19.8. Using `%` as an always-non-negative modulo

Wrong for negative dividends. Use `Math.floorMod` with a positive divisor if you need a non-negative remainder under the floor convention.

### 19.9. Assuming every `ArithmeticException` is caused by division by 0

Wrong. Exact arithmetic, type narrowing, `BigInteger`, and `BigDecimal` can all throw `ArithmeticException` for other conditions.

### 19.10. Catching the error and returning `0` in all situations

This can mask data errors, turning an undefined calculation into a seemingly valid result. Any fallback must be part of the contract.

### 19.11. Using the message to identify the error type

Do not write `if (e.getMessage().equals("/ by zero"))`. Messages are not stable error codes and can be null. If precise classification is needed, check preconditions or use structured domain error types/codes.

### 19.12. Catching `Exception` instead of `ArithmeticException` without reason

A broad handler can swallow unrelated errors and make diagnostics less accurate.

### 19.13. Forgetting to check for negative numbers before calculating size

`Math.multiplyExact(-2, 10)` returns `-20` because the operation **does not overflow**. It does not automatically consider negative quantities invalid. Application invariants must be checked separately.

### 19.14. Forgetting resource limits even when exact multiplication succeeds

A result may fit in `int` and still be too large to allocate an array or process safely. Exactness only guarantees the arithmetic range, not memory availability.

### 19.15. Thinking `BigInteger` or `BigDecimal` never throw arithmetic errors

Wrong. Division by 0 and `BigDecimal` division without a finite decimal result when lacking a rounding policy can both throw `ArithmeticException`.

## 20. Edge Cases to Include in Tests

A good test suite should include:

| Case | What to verify |
| --- | --- |
| `10 / 2` | Returns `5` |
| `10 / 0` | `ArithmeticException` |
| `10 % 0` | `ArithmeticException` |
| `10L / 0L` | `ArithmeticException` |
| `Integer.MIN_VALUE / -1` | Does not throw, returns `MIN_VALUE` |
| `-7 / 3` | `-2`, truncate toward zero |
| `-7 % 3` | `-1` |
| `Math.floorDiv(-7,3)` | `-3` |
| `Math.floorMod(-7,3)` | `2` |
| `Integer.MAX_VALUE + 1` | Wraps to `MIN_VALUE` |
| `Math.addExact(MAX,1)` | `ArithmeticException` |
| `Math.subtractExact(MIN,1)` | `ArithmeticException` |
| `Math.multiplyExact(50000,50000)` | `ArithmeticException` |
| `Math.negateExact(MIN)` | `ArithmeticException` |
| `Math.absExact(MIN)` | `ArithmeticException` |
| `Math.toIntExact(MAX+1L)` | `ArithmeticException` |
| `1.0 / 0.0` | `Infinity`, does not throw `ArithmeticException` |
| `0.0 / 0.0` | `NaN` |
| `BigInteger.TEN.divide(ZERO)` | `ArithmeticException` |
| `BigDecimal.ONE.divide(3)` | `ArithmeticException` if infinite exact result is required |
| `BigDecimal.ONE.divide(3,2,HALF_UP)` | `0.33` |

When writing unit tests, assert exceptions **by type and condition**, without requiring fixed JDK messages. For example, with JUnit 5:

~~~java
assertThrows(ArithmeticException.class,
        () -> Math.addExact(Integer.MAX_VALUE, 1));
~~~

This is an **illustrative snippet depending on the JUnit 5 library**, not part of the standalone `ArithmeticExactDemo.java` program; use it only if the project already has JUnit configured.

## 21. Self-Check Questions

1. Is `ArithmeticException` checked or unchecked? Which class does it extend?
2. Why can `int a = 10 / 0` cause `ArithmeticException`?
3. Is `10 % 0` valid?
4. Is dividing a `long` by `0L` the same as dividing an `int` by `0`?
5. What do `7 / 3` and `-7 / 3` return respectively?
6. Why does `-7 % 3` return `-1`?
7. How does `Math.floorDiv(-7,3)` differ from `-7/3`?
8. What does `Math.floorMod(-7,3)` return?
9. Does `Integer.MIN_VALUE / -1` throw an error or return a value?
10. Does `Long.MIN_VALUE / -1L` have the same boundary behavior?
11. Does `Integer.MAX_VALUE + 1` throw an error by default?
12. What is the behavior of `Math.addExact(Integer.MAX_VALUE,1)`?
13. When does `Math.subtractExact` throw an error?
14. Why does `50_000 * 50_000` produce a negative `int` value?
15. Does `Math.multiplyExact(50_000,50_000)` return that same negative value?
16. What does `Math.incrementExact(Integer.MAX_VALUE)` do?
17. Why does `-Integer.MIN_VALUE` not return a positive integer mathematically?
18. What does `Math.absExact(Integer.MIN_VALUE)` do?
19. If `long x = Integer.MAX_VALUE + 1L`, does casting `(int)x` report an error?
20. How does `Math.toIntExact(x)` differ from casting?
21. Does `1.0 / 0.0` throw `ArithmeticException`? What is the result?
22. What special floating-point value does `0.0 / 0.0` return?
23. Can `BigInteger` still throw `ArithmeticException`? Give an example.
24. Why can `BigDecimal.ONE.divide(new BigDecimal("3"))` throw an error?
25. When designing an integer division API, should you check `divisor == 0` before computing?
26. Does `Math.multiplyExact(-2,10)` automatically reject negative quantities?
27. Why does a successful exact multiplication not guarantee safe array allocation?
28. Should you default to `catch (ArithmeticException)` and return `0`?
29. Does `Math.floorDiv(x,0)` differ from the integer operator `x/0` in terms of errors?
30. When testing, why should you not rely strictly on `getMessage()` of `ArithmeticException`?

### Suggested Answers

1. Unchecked, extends `RuntimeException`.
2. A divisor of 0 in integer division is an invalid condition.
3. No; it throws `ArithmeticException`.
4. Yes, for integer operands.
5. `2` and `-2`.
6. The remainder from Java's `%` operator takes the sign of the dividend.
7. `floorDiv` rounds down to `-3`, whereas `/` truncates toward 0 to `-2`.
8. `2`.
9. Returns `Integer.MIN_VALUE`, does not throw.
10. Yes; returns `Long.MIN_VALUE`.
11. No; it wraps.
12. Throws `ArithmeticException` due to overflow.
13. When the difference exceeds the range of the result type.
14. The mathematical product exceeds `Integer.MAX_VALUE`, so it wraps in 32 bits.
15. No; it throws `ArithmeticException`.
16. Throws `ArithmeticException`.
17. The corresponding positive value exceeds `Integer.MAX_VALUE`.
18. Throws `ArithmeticException`.
19. No; casting can truncate high bits.
20. `toIntExact` checks the `int` range and throws when out of range.
21. No; the result is `Infinity`.
22. `NaN`.
23. Yes, for example `BigInteger.TEN.divide(BigInteger.ZERO)`.
24. `1/3` has no finite decimal representation when exact division without rounding is requested.
25. Yes, if you want a clear precondition error message; otherwise Java's operation throws automatically if the denominator is 0.
26. No; `-20` does not overflow. Data invariants must be checked separately.
27. The result may exceed memory quotas or API constraints.
28. No, only when a `0` fallback is permitted by the contract.
29. Both throw `ArithmeticException` for an integer divisor of 0.
30. Because the message is not a stable error contract for programmatic handling; check the exception type and condition instead.

## 22. Key Takeaways

**`ArithmeticException` in Java Core primarily occurs on integer division/remainder by 0 and when exact APIs detect an operation that cannot be represented accurately within the integer range.** Ordinary `+`, `-`, `*`, `++`, and `--` operators do not automatically report overflow; `Integer.MIN_VALUE / -1` also does not throw and returns `MIN_VALUE`. Use `Math.addExact`, `subtractExact`, `multiplyExact`, `incrementExact`, `decrementExact`, `negateExact`, `absExact`, and `toIntExact` when overflow detection is required. Understand the differences between `/`, `%`, `floorDiv`, and `floorMod` with negative numbers, as well as the `Infinity`/`NaN` behavior of `float`/`double`. When designing APIs, combine precondition checks with business invariants; do not catch arithmetic errors and return an arbitrary value without a clear policy.
