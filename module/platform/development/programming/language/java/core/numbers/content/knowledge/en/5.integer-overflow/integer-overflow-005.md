# `Math.addExact`, `subtractExact`, and `multiplyExact`: Detecting Integer Overflow in Java

In Java, addition `+`, subtraction `-`, and multiplication `*` on `int`/`long` **do not automatically report an error when the result exceeds the range**. The result overflows according to fixed-width integer representation. This is dangerous when calculating monetary totals in smallest units, inventory counts, memory sizes, counters, scores, or transaction limits.

`java.lang.Math` provides three **overflow-checking** (*exact arithmetic*) methods:

- `Math.addExact(a, b)`: computes `a + b` and reports an error if the result cannot be represented in the return type.
- `Math.subtractExact(a, b)`: computes `a - b`, with overflow checking.
- `Math.multiplyExact(a, b)`: computes `a * b`, with overflow checking.

On overflow, all three **throw `ArithmeticException`** instead of returning a wrapped-around value. They do not automatically widen the operation's type and do not create arbitrary-length integers.

## 1. Why Are Overflow-Checking Operations Needed?

`int` has 32 signed bits, representing from `-2_147_483_648` to `2_147_483_647`. `long` has 64 signed bits, from `-9_223_372_036_854_775_808L` to `9_223_372_036_854_775_807L`.

Example of an ordinary operation:

```java
int a = Integer.MAX_VALUE;
int unchecked = a + 1; // -2147483648: overflowed int
```

`Integer.MAX_VALUE` is 2,147,483,647, so adding 1 mathematically produces 2,147,483,648, which does not fit in `int`. `+` does not report an error; the `int` result becomes the smallest negative value.

Using a checked operation:

```java
int a = Integer.MAX_VALUE;
int checked = Math.addExact(a, 1); // ArithmeticException at runtime
```

If the result is within the return type's range, `addExact` returns **the exact arithmetic result**. If it is out of range, the method throws an exception; there is no normal return value.

| Operation | Ordinary Operator on `int` | `Math.*Exact` on `int` |
| --- | --- | --- |
| `40 + 2` | 42 | 42 |
| `Integer.MAX_VALUE + 1` | -2147483648 (overflow) | `ArithmeticException` |
| `Integer.MIN_VALUE - 1` | 2147483647 (overflow) | `ArithmeticException` |
| `100_000 * 100_000` | 1410065408 (overflow) | `ArithmeticException` |

**Limitation of checking:** these methods detect overflow **in the operation performed by the method itself**; they cannot retroactively infer errors that occurred before they were called.

## 2. Syntax, Overloads, and Return Types

All three methods are `static` in `java.lang.Math`, so they can be called as `Math.addExact(...)` without an `import`.

| Operation | Commonly Used Signature | Return Type |
| --- | --- | --- |
| Exact addition | `Math.addExact(int x, int y)` | `int` |
| Exact addition | `Math.addExact(long x, long y)` | `long` |
| Exact subtraction | `Math.subtractExact(int x, int y)` | `int` |
| Exact subtraction | `Math.subtractExact(long x, long y)` | `long` |
| Exact multiplication | `Math.multiplyExact(int x, int y)` | `int` |
| Exact multiplication | `Math.multiplyExact(long x, long y)` | `long` |
| Exact multiplication | `Math.multiplyExact(long x, int y)` | `long` |

The `multiplyExact(long, int)` overload exists in modern Java (including Java 17). When an `int` is passed to a `long` parameter, Java widens the type as in a normal method call.

Examples:

```java
int sum = Math.addExact(15, 27);        // 42, int overload
long sumLong = Math.addExact(15L, 27);  // 42L, long overload
int product = Math.multiplyExact(6, 7); // 42
long big = Math.multiplyExact(100_000L, 100_000); // 10000000000L
```

Important note: **the receiving variable's type does not determine which overload is chosen**.

```java
// Still calls multiplyExact(int, int), so overflowing multiplication throws an exception:
long wrong = Math.multiplyExact(100_000, 100_000);

// Selects the long-returning multiplication right at the call site:
long correct = Math.multiplyExact(100_000L, 100_000);
```

This is an illustrative snippet: the `wrong` line compiles but throws an exception at runtime if executed. The `L` suffix or cast must appear **on an argument before the call**; assigning the result to `long` after the call cannot save an `int` calculation.

## 3. `Math.addExact`: Adding and Detecting Boundary Crossings

`addExact(x, y)` returns `x + y` when the result fits in the chosen `int`/`long` range; otherwise it throws `ArithmeticException`.

### Normal and boundary-adjacent examples

```java
int score = Math.addExact(80, 20); // 100
int max = Math.addExact(Integer.MAX_VALUE - 1, 1); // Integer.MAX_VALUE
int min = Math.addExact(Integer.MIN_VALUE, 0); // Integer.MIN_VALUE
```

Here, hitting the exact maximum or minimum value is **valid**. The method reports an error only when the calculation exceeds the range.

### Exceeding positive and negative boundaries

```java
// ArithmeticException: 2147483647 + 1 is outside int
Math.addExact(Integer.MAX_VALUE, 1);

// ArithmeticException: -2147483648 + (-1) is outside int
Math.addExact(Integer.MIN_VALUE, -1);
```

These two statements are **exception-throwing illustrations**, not examples meant to run without error handling.

If the requirement is to **compute a result larger than the `int` range**, choose the `long` overload from the start:

```java
long expanded = Math.addExact((long) Integer.MAX_VALUE, 1);
// 2147483648L
```

However, `long` still has limits. `Math.addExact(Long.MAX_VALUE, 1L)` also throws `ArithmeticException`.

## 4. `Math.subtractExact`: Subtracting Two Numbers and Boundary Cases

`subtractExact(x, y)` checks the mathematical result of `x - y`. Subtraction can overflow in both directions:

```java
int remaining = Math.subtractExact(100, 35); // 65
int min = Math.subtractExact(Integer.MIN_VALUE + 1, 1); // MIN_VALUE
```

These cases throw `ArithmeticException`:

```java
// Negative overflow: MIN_VALUE - 1 < MIN_VALUE
Math.subtractExact(Integer.MIN_VALUE, 1);

// Positive overflow: MAX_VALUE - (-1) > MAX_VALUE
Math.subtractExact(Integer.MAX_VALUE, -1);
```

The sign of the second operand easily trips learners up: **subtracting a negative number is mathematically equivalent to adding a positive number**, so `MAX_VALUE - (-1)` exceeds the `int` ceiling.

With `long`:

```java
long safe = Math.subtractExact((long) Integer.MIN_VALUE, 1L);
// -2147483649L, valid because it still fits in long
```

`Math.subtractExact(Long.MIN_VALUE, 1L)` throws `ArithmeticException`. Boundary checking always corresponds to the chosen type, not a fixed `int` range.

## 5. `Math.multiplyExact`: Multiplying and Detecting Overflow

Multiplication can exceed the range even when each individual operand is smaller than the limit. For example, `100_000` is a valid `int`, yet the product `100_000 * 100_000 = 10_000_000_000` exceeds `int`.

```java
int normal = Math.multiplyExact(6, 7); // 42
int square = Math.multiplyExact(46_340, 46_340); // 2147395600

// Throws ArithmeticException:
Math.multiplyExact(100_000, 100_000);
```

`46_340 * 46_340 = 2_147_395_600` still fits in `int`, so the method returns normally. `46_341 * 46_341 = 2_147_488_281` exceeds `Integer.MAX_VALUE`, so `Math.multiplyExact(46_341, 46_341)` throws an exception.

### Negative products and special value pairs

For `int`, `Integer.MIN_VALUE * (-1)` does not fit in `int`: the mathematical result is `2_147_483_648`.

```java
// Throws ArithmeticException:
Math.multiplyExact(Integer.MIN_VALUE, -1);
```

Similarly, `Math.multiplyExact(Long.MIN_VALUE, -1L)` throws an exception because the positive result exceeds `Long.MAX_VALUE`.

Cases involving `0` always yield product `0` and never overflow, regardless of where the other operand lies in the corresponding type's range:

```java
int zero = Math.multiplyExact(Integer.MAX_VALUE, 0); // 0
```

### Choosing `long` and understanding the goal

```java
long largeProduct = Math.multiplyExact(100_000L, 100_000);
// 10000000000
```

Promote to `long` only when the expected value range truly fits in `long`. If the product can exceed 64 bits, consider `BigInteger`; there is no `Math.multiplyExact(BigInteger, BigInteger)` overload.

## 6. Subtle Bug: An Operation Already Overflowed Before Reaching `Exact`

Suppose you write:

```java
int alreadyOverflowed = Integer.MAX_VALUE + 1; // -2147483648
int undetected = Math.addExact(alreadyOverflowed, 0);
// -2147483648: no new overflow in this addExact call
```

`Math.addExact` receives actual inputs `-2147483648` and `0`; that addition itself is valid. The method does not know the negative value came from an earlier overflowed calculation.

Another wrong case:

```java
long wrong = Math.addExact(Integer.MAX_VALUE + 1, 0L);
// (-2147483648) + 0L -> -2147483648L: does not report an error
```

The expression `Integer.MAX_VALUE + 1` is evaluated in `int` **before** converting to a `long` argument, so it already overflowed. Correct approach:

```java
long correct = Math.addExact((long) Integer.MAX_VALUE + 1, 0L);
// 2147483648L
```

Or more concisely `Math.addExact((long) Integer.MAX_VALUE, 1L)`.

Similarly, **do not wrap an already-added/multiplied expression inside an `Exact` method and expect it to check the whole calculation chain**:

```java
int a = 2_000_000_000;
int b = 2_000_000_000;
int result = Math.addExact(a + b, 0); // a + b already overflowed!
```

If you need to check the addition of `a` and `b`, you must write `Math.addExact(a, b)`. If multiple steps need checking, use the corresponding method **at each step**.

## 7. Handling `ArithmeticException` and Business Design

### Catching errors at an appropriate boundary

`ArithmeticException` is an *unchecked exception* (a subclass of `RuntimeException`); Java does not require declaring `throws` or `catch`. However, for critical calculations, an application should define how to handle it:

```java
try {
    int updated = Math.addExact(Integer.MAX_VALUE, 1);
    System.out.println(updated);
} catch (ArithmeticException ex) {
    System.out.println("overflow detected");
}
```

The output is a single line `overflow detected`. Do not rely on the **detailed exception message string** to make business decisions; rely only on the exception type and context.

If overflow stems from invalid input data, the business layer can translate it into an appropriate message or reject the request. If the error indicates an internal invariant violation, you can let it propagate to a centralized error handler and log it at an appropriate level.

### Do not turn an overflow error into a fake valid value

Handling like `catch (ArithmeticException ex) { return 0; }` is very dangerous if `0` is also a valid result: you can no longer distinguish "nothing" from "out-of-range calculation."

Choose an explicit overflow policy:

| Policy | How to Implement | When Appropriate |
| --- | --- | --- |
| Reject the operation | Call an `Exact` method, translate the error at the input boundary | Data domain has strict limits |
| Widen the representation range | Choose `long` arithmetic right before computing | Inputs are `int` but results can exceed `int` |
| Use integers without fixed-width limits | `BigInteger` and its `add`, `subtract`, `multiply` methods | Magnitudes can exceed even `long` |
| Saturate at boundary values (*saturating*) | Build an explicit policy with clear handling | Only when business specs require clamping at min/max |
| Allow wraparound | Ordinary integer operators | Only when modulo/bit-pattern arithmetic is intended |

The three `Exact` methods do not perform *clamping*, do not return `Optional`, and do not support `float`/`double` operations under the same API family.

## 8. Comparing `Exact` with `long` and `BigInteger`

The three strategies address **three different needs**:

- **`Math.*Exact`:** keeps `int`/`long` types, while detecting when the result exceeds that type's own limit.
- **`long`:** gives a larger representation range than `int`; it can still overflow and still needs `Math.*Exact` if you want to detect `long` overflow.
- **`BigInteger`:** represents arbitrary-magnitude integers within memory limits; `add`, `subtract`, and `multiply` methods are not bounded by 32/64 bits. `BigInteger` is immutable, so operations return a new object.

Example:

```java
long product = Math.multiplyExact(100_000L, 100_000); // 10000000000L

java.math.BigInteger huge = java.math.BigInteger.valueOf(Long.MAX_VALUE)
        .multiply(java.math.BigInteger.TWO); // exceeds long range
```

`BigInteger.TWO` is available in modern Java, including Java 17. In a real payment system, you must choose **units, numeric types, and rounding policies** together; `Math.*Exact` protects against one class of integer overflow bugs but does not verify all business rules.

Distinguish `Math.toIntExact(long)`: this method checks **converting a `long` value to `int`**; it does not perform addition, subtraction, or multiplication. It is useful after choosing to compute in `long` when you want to reject results that do not fit in `int`.

## 9. Runnable Java 17+ Program: Verifying Each Operation

Create the file **`ExactArithmeticDemo.java`**:

```java
public class ExactArithmeticDemo {
    public static void main(String[] args) {
        System.out.println("add=" + Math.addExact(20, 22));
        System.out.println("subtract=" + Math.subtractExact(70, 28));
        System.out.println("multiply=" + Math.multiplyExact(6, 7));
        System.out.println("addMax=" + Math.addExact(Integer.MAX_VALUE - 1, 1));
        System.out.println("subtractMin=" + Math.subtractExact(Integer.MIN_VALUE + 1, 1));
        System.out.println("square=" + Math.multiplyExact(46_340, 46_340));

        System.out.println("uncheckedAdd=" + (Integer.MAX_VALUE + 1));
        System.out.println("uncheckedMultiply=" + (100_000 * 100_000));

        try {
            Math.addExact(Integer.MAX_VALUE, 1);
            System.out.println("checkedAdd=not-detected");
        } catch (ArithmeticException ex) {
            System.out.println("checkedAdd=detected");
        }

        try {
            Math.subtractExact(Integer.MIN_VALUE, 1);
            System.out.println("checkedSubtract=not-detected");
        } catch (ArithmeticException ex) {
            System.out.println("checkedSubtract=detected");
        }

        try {
            Math.multiplyExact(100_000, 100_000);
            System.out.println("checkedMultiply=not-detected");
        } catch (ArithmeticException ex) {
            System.out.println("checkedMultiply=detected");
        }

        long longAdd = Math.addExact((long) Integer.MAX_VALUE, 1L);
        long longMultiply = Math.multiplyExact(100_000L, 100_000);
        System.out.println("longAdd=" + longAdd);
        System.out.println("longMultiply=" + longMultiply);

        int wrapped = Integer.MAX_VALUE + 1;
        System.out.println("priorOverflow=" + Math.addExact(wrapped, 0));

        try {
            Math.multiplyExact(Long.MIN_VALUE, -1L);
            System.out.println("longOverflow=not-detected");
        } catch (ArithmeticException ex) {
            System.out.println("longOverflow=detected");
        }
    }
}
```

Compile and run with JDK 17 or newer:

```bash
javac ExactArithmeticDemo.java
java ExactArithmeticDemo
```

**Expected output** (the program deliberately catches exceptions so it runs to completion):

```text
add=42
subtract=42
multiply=42
addMax=2147483647
subtractMin=-2147483648
square=2147395600
uncheckedAdd=-2147483648
uncheckedMultiply=1410065408
checkedAdd=detected
checkedSubtract=detected
checkedMultiply=detected
longAdd=2147483648
longMultiply=10000000000
priorOverflow=-2147483648
longOverflow=detected
```

The `checked*=detected` lines come from the `catch` blocks, not arbitrary JVM messages. The `priorOverflow` line confirms an important distinction: if overflow already occurred before calling `addExact`, the subsequent checked call cannot detect the old error.

## 10. Practical Application Scenarios

### Controlled quantity updates

If a warehouse currently holds `stock` units and receives `received`, use:

```java
int newStock = Math.addExact(stock, received);
```

This snippet assumes variables `stock` and `received` are already declared; it is not a standalone program. On `int` overflow, the method throws `ArithmeticException`. If business logic forbids negative quantities, you must **additionally check the constraint `newStock >= 0`**; `addExact` does not enforce this constraint automatically.

### Calculating total price in integer units

If `unitPrice` and `quantity` have type `int`, yet the expected product can exceed `int`:

```java
long total = Math.multiplyExact((long) unitPrice, quantity);
```

This is a **`long` overflow-checked** multiplication, because one argument was widened before the call. If the result range can exceed even `long`, choose an appropriate numeric model (such as `BigInteger`) from the beginning.

### Multi-step calculation chains

For example, computing `(price * quantity) - discount` within the `long` range:

```java
long subtotal = Math.multiplyExact(price, quantity);
long total = Math.subtractExact(subtotal, discount);
```

This assumes all three parameters `price`, `quantity`, and `discount` are already declared with type `long`; the illustrative snippet resides in an existing method. Each operation must be checked individually. If `subtotal` exceeds the range, the exception occurs right at the multiplication step.

**Overflow checking does not replace business-domain validation**: non-negative quantities, order limits, authorization, data consistency, or currency rules still require independent checks.

## 11. Common Mistakes and Checklist

| Misconception | Reality |
| --- | --- |
| "`long result = Math.addExact(intA, intB);` adds in `long`." | If both arguments are `int`, the `int` overload is chosen; it can throw before assigning to `long`. |
| "Wrapping an already-computed operation inside `addExact` detects prior overflow." | No; call the checked method right at the step that needs computing. |
| "`multiplyExact` always returns `long`." | `(int, int)` returns `int`; `long` overloads return `long`. |
| "Throwing an exception means the JVM crashes immediately." | Exceptions can be caught/handled; if unhandled, the thread/program terminates per exception rules. |
| "Overflow only happens when adding positive numbers." | Overflow can happen in addition, subtraction, and multiplication; with positive and negative numbers and at both boundaries. |
| "`Math.addExact` checks whether negative numbers are business-valid." | No; it only checks whether the mathematical result lies within the type's range. |
| "Switching to `long` makes overflow impossible." | `long` is still limited to 64 bits; `Exact` overloads exist for `long`. |
| "`Math.multiplyExact` handles `double` and `float`." | This overload family is for `int`/`long` integers, not floating-point numbers. |
| "You can pass `BigInteger` directly to `Math.multiplyExact`." | No; use `BigInteger`'s `multiply` method. |

When reviewing code, answer in order:

1. **What are the operand types?** Look at the actual arguments, not just the target variable. If `long` arithmetic is needed, ensure one or more appropriate arguments already have type `long` before computing.
2. **Which operations need protection?** Replace `a + b` with `Math.addExact(a, b)` at the exact step; likewise for subtraction/multiplication.
3. **Which results sit at the boundary?** Hitting `MAX_VALUE` or `MIN_VALUE` is still valid; crossing the boundary throws `ArithmeticException`.
4. **If an exception occurs, who handles it?** Choose an explicit business policy; do not silently substitute a fake value that could be mistaken for valid.
5. **What if the representation range is insufficient?** Use `long` or `BigInteger` as needed, while continuing to enforce business rules.

**Remember:** `Math.addExact`, `Math.subtractExact`, and `Math.multiplyExact` enable integer arithmetic **with overflow checking at that exact operation**. They help catch bugs easily hidden by wrap-around results, but staying safe requires picking the right overload, protecting every intermediate step, and handling `ArithmeticException` according to the program's purpose.
