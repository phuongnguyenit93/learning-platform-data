# `incrementExact`, `decrementExact`, `negateExact`, and `toIntExact` in Java

## 1. The Problem: Integers Are Bounded, Yet Ordinary Operations Do Not Report Overflow

Java has two primitive integer types commonly used for counting and large values: `int` (32-bit signed) and `long` (64-bit signed). Each type can represent only a finite range:

| Type | Minimum Value | Maximum Value |
|---|---:|---:|
| `int` | `-2_147_483_648` | `2_147_483_647` |
| `long` | `-9_223_372_036_854_775_808L` | `9_223_372_036_854_775_807L` |

Suppose an `int` counter has reached `Integer.MAX_VALUE`. The statement `counter++` **does not automatically throw an error**; instead, it wraps the value to `Integer.MIN_VALUE`. Similarly, `Integer.MIN_VALUE - 1` becomes `Integer.MAX_VALUE`, and `-Integer.MIN_VALUE` yields `Integer.MIN_VALUE` again. This is a consequence of fixed-width integer arithmetic under two's complement representation.

For problems that need to **detect overflow or lossy type narrowing**, Java provides methods in `java.lang.Math`:

- `Math.incrementExact`: increments by one, throwing an error on overflow.
- `Math.decrementExact`: decrements by one, throwing an error on overflow.
- `Math.negateExact`: returns the negation, throwing an error if the negated value cannot be represented.
- `Math.toIntExact`: converts `long` to `int`, throwing an error if the value lies outside the `int` range.

All four methods throw **`ArithmeticException`** when they cannot produce an exact result in the return type. They do not silently wrap around or truncate bits like ordinary integer operations.

## 2. API Table and Failure Conditions

| Method | Parameter and Return Type | Meaning | Case That Throws `ArithmeticException` |
|---|---|---|---|
| `Math.incrementExact(int)` | `int → int` | Computes `value + 1` | `value == Integer.MAX_VALUE` |
| `Math.incrementExact(long)` | `long → long` | Computes `value + 1` | `value == Long.MAX_VALUE` |
| `Math.decrementExact(int)` | `int → int` | Computes `value - 1` | `value == Integer.MIN_VALUE` |
| `Math.decrementExact(long)` | `long → long` | Computes `value - 1` | `value == Long.MIN_VALUE` |
| `Math.negateExact(int)` | `int → int` | Computes `-value` | `value == Integer.MIN_VALUE` |
| `Math.negateExact(long)` | `long → long` | Computes `-value` | `value == Long.MIN_VALUE` |
| `Math.toIntExact(long)` | `long → int` | Converts to `int` without losing value | `value < Integer.MIN_VALUE` or `value > Integer.MAX_VALUE` |

**Key point about overloads:** the first three methods have both `int` and `long` versions; `toIntExact` only accepts `long` and returns `int`. Java selects the overload based on the **expression type**. For example, `Math.incrementExact(5)` returns `int`, whereas `Math.incrementExact(5L)` returns `long`.

These methods are `static` in `Math`. You can call them directly like `Math.incrementExact(n)` without creating an object. They return a **new value** and do not mutate the passed-in variable.

## 3. `incrementExact` — Incrementing by One with Checking

### When is it needed?

A transaction counter, internal session ID, logical index, or total processing count may need to guarantee that it **never turns negative due to overflow**. With the `++` operator:

~~~java
int count = Integer.MAX_VALUE;
count++;
// count == Integer.MIN_VALUE
~~~

This is an illustrative snippet; the result follows fixed-width `int` arithmetic. The `++` operator does not report overflow.

Switch to:

~~~java
int count = Integer.MAX_VALUE;
count = Math.incrementExact(count);
// Throws ArithmeticException; assignment does not complete.
~~~

This snippet is also illustrative and **intentionally throws at runtime**. When the operand is already `Integer.MAX_VALUE`, `Math.incrementExact(count)` throws `ArithmeticException` before returning; therefore, the assignment `count = ...` does not complete and `count` retains its old value.

The same applies to `long`: `Math.incrementExact(Long.MAX_VALUE)` throws an error, whereas `Long.MAX_VALUE + 1L` produces `Long.MIN_VALUE`.

Values **that are not at the maximum** increment normally, including `Math.incrementExact(-1) == 0`, `Math.incrementExact(0) == 1`, and `Math.incrementExact(Integer.MAX_VALUE - 1) == Integer.MAX_VALUE`.

### Note on postfix operators

`count++` is a variable-increment expression and has prefix/postfix differences when used inside a larger expression. `Math.incrementExact(count)` **is not entirely equivalent in syntax or side effects**: it only returns the incremented value without modifying `count` itself. When you want to update the variable, you must assign `count = Math.incrementExact(count)`.

## 4. `decrementExact` — Decrementing by One with Checking

`Math.decrementExact(value)` computes `value - 1` and checks the return type's range. It is suitable for remaining counters, seat counts, quotas, or integer unit balances when **integer overflow** must be detected.

~~~java
int remaining = Integer.MIN_VALUE;
remaining--;
// remaining == Integer.MAX_VALUE: overflowed.

int safeRemaining = Math.decrementExact(Integer.MIN_VALUE);
// Throws ArithmeticException.
~~~

The code above illustrates both approaches; the latter line **intentionally throws**, and is not a complete sample program.

Conversely, `Math.decrementExact(0)` returning `-1` is completely valid. **`decrementExact` does not check the business condition** "quantity must not be negative"; it only checks the **technical range of the numeric type**. If your application rule is `remaining >= 0`, you must still check that condition separately.

Similarly, `Math.decrementExact(Long.MIN_VALUE)` throws `ArithmeticException`, whereas `Long.MIN_VALUE - 1L` returns `Long.MAX_VALUE`.

## 5. `negateExact` — Negating with Checking

Mathematically, the negation of `x` is `-x`. However, the `int` and `long` ranges are **not symmetric around 0**:

- `Integer.MIN_VALUE = -2_147_483_648`; the positive number `2_147_483_648` cannot be stored in `int`.
- `Long.MIN_VALUE = -9_223_372_036_854_775_808L`; the positive number `9_223_372_036_854_775_808` cannot be stored in `long`.

Therefore:

~~~java
int wrapped = -Integer.MIN_VALUE;
// wrapped == Integer.MIN_VALUE, does not throw.

int checked = Math.negateExact(Integer.MIN_VALUE);
// Throws ArithmeticException.
~~~

This is illustrative; the `checked` line **intentionally throws**.

For every `int` other than `Integer.MIN_VALUE`, `Math.negateExact` produces the exact negation; for example, `Math.negateExact(-7) == 7`, `Math.negateExact(7) == -7`, and `Math.negateExact(0) == 0`. `Math.negateExact(Long.MIN_VALUE)` also throws an error.

If you need the negation of `Integer.MIN_VALUE` as a `long`, **widen before negating**:

~~~java
long exactPositive = -(long) Integer.MIN_VALUE;  // 2147483648
~~~

Meanwhile, `(long) (-Integer.MIN_VALUE)` converts to `long` **after** the `int` negation has already overflowed. For `Long.MIN_VALUE`, there is no wider primitive type than `long`; you can use `BigInteger.valueOf(Long.MIN_VALUE).negate()` to get the exact result.

`Math.negateExact` is also not an absolute-value function. It **flips the sign** of both positive and negative numbers; if you need an absolute value with overflow checking, choose an appropriate operation for your API/JDK. Calling `Math.abs(Integer.MIN_VALUE)` alone will not solve the boundary case.

## 6. `toIntExact` — Narrowing `long` to `int` Without Losing Data

An ordinary cast from `long` to `int` keeps only the lower 32 bits; a value that is too large or too small can turn into a completely different number **without any exception**:

~~~java
long value = 2_147_483_648L;
int truncated = (int) value;
// truncated == -2147483648
~~~

If the application must guarantee that the converted value still **equals the original integer**, use:

~~~java
long value = 2_147_483_648L;
int checked = Math.toIntExact(value);
// Throws ArithmeticException.
~~~

`Math.toIntExact(2_147_483_647L)` succeeds with `2_147_483_647`; `Math.toIntExact(-2_147_483_648L)` also succeeds with `-2_147_483_648`. Both bounds are **inclusive**. Only values **outside** `[Integer.MIN_VALUE, Integer.MAX_VALUE]` cause an exception.

### Comparing `(int)` and `toIntExact`

| `long` Value | `(int) value` Result | `Math.toIntExact(value)` Result |
|---:|---:|---|
| `42L` | `42` | `42` |
| `Integer.MAX_VALUE` | `2147483647` | `2147483647` |
| `2147483648L` | `-2147483648` | **`ArithmeticException`** |
| `Integer.MIN_VALUE` | `-2147483648` | `-2147483648` |
| `-2147483649L` | `2147483647` | **`ArithmeticException`** |

The table shows that **type narrowing** differs from **arithmetic operations**: `toIntExact` does not add or subtract; it ensures the conversion does not lose the integer value.

**There is no `Math.toIntExact(double)`**. If you start from a `double`, you must separately handle finiteness, fractional parts, value range, and floating-point precision loss. `toIntExact` is strictly a contract between the two **integer** types `long` and `int`.

## 7. Standalone Runnable Java 17+ Example: Valid Results

Create the file `MathExactBasics.java`:

~~~java
public class MathExactBasics {
    public static void main(String[] args) {
        System.out.println("incrementInt="
                + Math.incrementExact(41));
        System.out.println("decrementInt="
                + Math.decrementExact(-41));
        System.out.println("negateInt="
                + Math.negateExact(-41));
        System.out.println("incrementLong="
                + Math.incrementExact(2_147_483_647L));
        System.out.println("negateLong="
                + Math.negateExact(-2_147_483_648L));
        System.out.println("maxAsInt="
                + Math.toIntExact(2_147_483_647L));
        System.out.println("minAsInt="
                + Math.toIntExact(-2_147_483_648L));
    }
}
~~~

Compile and run in the directory containing the file:

~~~bash
javac MathExactBasics.java
java MathExactBasics
~~~

Output:

~~~text
incrementInt=42
decrementInt=-42
negateInt=41
incrementLong=2147483648
negateLong=2147483648
maxAsInt=2147483647
minAsInt=-2147483648
~~~

The `incrementLong` and `negateLong` lines prove that **the operand type determines the result range**: with a `long` operand, the positive number `2147483648` is valid. The two conversions to `int` sit right at the boundaries and do not fail.

## 8. Standalone Runnable Java 17+ Example: Testing Failure Boundaries

Create the file `MathExactFailures.java`:

~~~java
public class MathExactFailures {
    private static void check(String label, Runnable operation) {
        try {
            operation.run();
            System.out.println(label + "=OK");
        } catch (ArithmeticException ex) {
            System.out.println(label + "=OVERFLOW");
        }
    }

    public static void main(String[] args) {
        check("incIntMax",
                () -> Math.incrementExact(Integer.MAX_VALUE));
        check("decIntMin",
                () -> Math.decrementExact(Integer.MIN_VALUE));
        check("negIntMin",
                () -> Math.negateExact(Integer.MIN_VALUE));

        check("incLongMax",
                () -> Math.incrementExact(Long.MAX_VALUE));
        check("decLongMin",
                () -> Math.decrementExact(Long.MIN_VALUE));
        check("negLongMin",
                () -> Math.negateExact(Long.MIN_VALUE));

        check("toIntTooLarge",
                () -> Math.toIntExact(2_147_483_648L));
        check("toIntTooSmall",
                () -> Math.toIntExact(-2_147_483_649L));
        check("toIntAtMin",
                () -> Math.toIntExact((long) Integer.MIN_VALUE));
    }
}
~~~

~~~bash
javac MathExactFailures.java
java MathExactFailures
~~~

Output:

~~~text
incIntMax=OVERFLOW
decIntMin=OVERFLOW
negIntMin=OVERFLOW
incLongMax=OVERFLOW
decLongMin=OVERFLOW
negLongMin=OVERFLOW
toIntTooLarge=OVERFLOW
toIntTooSmall=OVERFLOW
toIntAtMin=OK
~~~

The `check` method accepts a `Runnable` to execute the operations sequentially; when `ArithmeticException` occurs, the program prints `OVERFLOW` rather than relying on the **exception message string** (which should not be assumed to be a fixed API contract). In Java, a lambda `() -> Math.incrementExact(value)` matches `Runnable` because a method call is a *statement expression* and its return value can be discarded.

The last line also confirms that `toIntExact` accepts **the exact negative boundary**. Not every negative number is an error, and not every `long` value lies outside the `int` range.

## 9. Using in Application Code: Controlled Updates and Conversions

### 9.1. Range-safe counter updates

Create the file `CheckedCounterDemo.java`:

~~~java
public class CheckedCounterDemo {
    public static void main(String[] args) {
        int counter = Integer.MAX_VALUE;

        try {
            counter = Math.incrementExact(counter);
        } catch (ArithmeticException ex) {
            System.out.println("counter overflow");
        }

        System.out.println("counter=" + counter);

        long total = (long) Integer.MAX_VALUE;
        total = Math.incrementExact(total);
        System.out.println("total=" + total);

        try {
            int narrowed = Math.toIntExact(total);
            System.out.println("narrowed=" + narrowed);
        } catch (ArithmeticException ex) {
            System.out.println("cannot narrow to int");
        }
    }
}
~~~

~~~bash
javac CheckedCounterDemo.java
java CheckedCounterDemo
~~~

Output:

~~~text
counter overflow
counter=2147483647
total=2147483648
cannot narrow to int
~~~

The assignment to `counter` executes only after `incrementExact` returns successfully; because the method throws an error, `counter` remains `Integer.MAX_VALUE`. Conversely, incrementing on `long` succeeds, yet the result exceeds the `int` range so `toIntExact` refuses to narrow it back to `int`.

The code above illustrates **overflow checking**; it does not automatically guarantee properties such as database transactions or **atomic updates across multiple threads**. For example, `counter = Math.incrementExact(counter)` is a multi-step read-compute-write sequence; when multiple threads modify one variable concurrently, synchronization or an appropriate atomic API is required. Overflow checking and concurrency safety are **two separate requirements**.

### 9.2. Handling exceptions per business contract

You should not always swallow `ArithmeticException` and continue with an undefined default value. When counters, inventory quantities, or interface data risk exceeding range, decide explicitly:

- **Reject the operation:** report that the value cannot be represented, keeping the previous state.
- **Choose a wider range:** use `long` when `int` is insufficient and there is no mandatory narrowing requirement.
- **Use arbitrary-magnitude integers:** use `BigInteger` when even `long` may not be enough.
- **Preserve an API's `int` contract:** use `Math.toIntExact` at the conversion boundary and handle errors with context.

Avoid automatically "saturating" values at `MAX_VALUE` or resetting to 0 unless business requirements call for it. The `Exact` methods provide an error signal so the application can decide the appropriate policy itself.

### 9.3. Other operations: when to use `addExact` or `multiplyExact`?

`incrementExact(x)` is equivalent in checking semantics to `addExact(x, 1)`. `decrementExact(x)` is equivalent to `subtractExact(x, 1)`. `negateExact(x)` is equivalent in purpose to negating with range checking.

If the operation is not ±1, use the appropriate method such as `Math.addExact`, `Math.subtractExact`, or `Math.multiplyExact` instead of chaining multiple `incrementExact`/`decrementExact` calls. For example, adding 100 units: `Math.addExact(total, 100)` is clear and checks a single addition.

These methods check **technical overflow**, not business validation: `Math.incrementExact(-3)` returns `-2`, which is type-valid yet may be invalid if an object must hold non-negative quantities.

## 10. Common Misconceptions and Mistakes

| Misconception | Reality and Fix |
|---|---|
| "`counter++` will throw an error at `MAX_VALUE`." | `++` wraps around silently; use `Math.incrementExact(counter)` when detection is needed. |
| "`decrementExact(0)` must throw an error." | It returns `-1`; checking non-negativity is a business rule. |
| "`-Integer.MIN_VALUE` produces the largest positive number." | The `int` result is still `Integer.MIN_VALUE`; `Math.negateExact` reports overflow. |
| "`toIntExact` rounds numbers." | It only converts `long` → `int` without losing value; it does not accept `double`. |
| "Casting `(int) longValue` throws an error if out of range." | A primitive cast can truncate bits; use `Math.toIntExact`. |
| "`incrementExact` mutates the input variable itself." | The method returns a new value; you must assign or use the return value. |
| "`Exact` methods automatically solve race conditions." | They check arithmetic, not concurrent state access across threads. |
| "A number that fits in `long` surely fits in `int`." | `long` has a wider range; use `toIntExact` when safe narrowing must be guaranteed. |
| "Just catch the exception and continue with 0." | Overflow handling policy must be dictated by business requirements. |

## 11. Project Application Checklist

1. **Choose the base type:** do `int` or `long` have enough range for expected values and intermediate values?
2. **Find boundary operations:** incrementing/decrementing counters, negating, converting `long` → `int`; pick the right `incrementExact`, `decrementExact`, `negateExact`, or `toIntExact`.
3. **Decide what happens on error:** propagate the exception, translate it into a contextual error, reject the operation, or change the data type?
4. **Keep state consistent:** assign the result after the check finishes; if updating multiple steps, consider transactions/synchronization.
5. **Test boundaries:** `MIN_VALUE`, `MIN_VALUE + 1`, `-1`, `0`, `1`, `MAX_VALUE - 1`, `MAX_VALUE`, and the two `long` values immediately outside the `int` range.
6. **Check separate business conditions:** non-negative quantities, limits, data formats, and update permissions are not guaranteed by `Exact` methods alone.

## 12. Self-Check Questions

1. Why does `Math.incrementExact(Integer.MAX_VALUE)` throw an error, while `Integer.MAX_VALUE + 1` returns a negative number?
2. What does `Math.decrementExact(0)` return? Does this guarantee "non-negative inventory"?
3. Why does `Math.negateExact(Integer.MIN_VALUE)` throw an error, while `Math.negateExact(Integer.MIN_VALUE + 1)` succeeds?
4. How do `2_147_483_647L` and `2_147_483_648L` differ in their `Math.toIntExact` results?
5. What is the difference between `(int) value` and `Math.toIntExact(value)` when `value` is a `long` exceeding the `int` range?
6. In `counter = Math.incrementExact(counter)`, if the method throws an exception, is `counter` assigned a new value?
7. Why does the code above still need synchronization if multiple threads increment `counter` concurrently?
8. If total transaction counts can exceed the `long` range, what type should you consider instead of trying to stretch `long`?

**Suggested answers:** (1) `incrementExact` checks for overflow whereas ordinary `+` does not; (2) returns `-1`, inventory rules must be checked separately; (3) only the minimum integer lacks a positive counterpart in the same range, whereas `MIN_VALUE + 1` has one; (4) the first value is valid, the second throws `ArithmeticException`; (5) a cast can lose value, while `toIntExact` detects it; (6) no, the assignment never completes; (7) arithmetic checking does not guarantee read-write atomicity; (8) consider `BigInteger`.

**Remember:** `incrementExact`, `decrementExact`, and `negateExact` keep the same integer type while **reporting errors instead of silently overflowing**. `toIntExact` ensures converting `long` to `int` **without data loss**. Use them at operations and conversion boundaries where exactness is a program requirement.
