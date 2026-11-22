# Checking Overflow Before and After Type Conversion in Java

When processing numeric data, a calculation can lose data at **two different points**: at the moment addition or multiplication is performed in the current type, or when converting the result to a type with a smaller range. If you only check after data has already been lost, the program may wrongly conclude that the value is still valid. This is an important pitfall when testing and diagnosing Java programs.

This lesson guides you through identifying the **type of each operation**, distinguishing widening and narrowing conversions, detecting overflow at the right moment using `Math.addExact`, `Math.multiplyExact`, and `Math.toIntExact`, and using `BigInteger`/`BigDecimal` when needed. The examples target Java 17+, including counterexamples that commonly cause boundary tests to reach wrong conclusions.

## 1. Three Questions to Check Separately

Suppose an API receives a quantity and unit price, computes a total, and stores it in an integer field. You must clarify:

1. **Are the inputs within valid bounds?** For example, quantity is non-negative and unit price does not exceed contract limits.
2. **Are all intermediate calculations representable in the type being used?** Two valid `int` values do not guarantee that their `int` product or sum is also valid.
3. **Does the final result fit the target type and preserve the required precision?** A valid `long` result may not fit in `int`; a `BigDecimal` may have a fractional part that cannot be converted to an integer without data loss.

The three questions are independent. Checking business rules on the inputs does not guarantee the calculation is safe; seeing a result within the target type's range after a cast **does not prove** that the original data did not overflow.

### Common Integral Type Ranges

| Type | Representable range | Notes |
| --- | --- | --- |
| `byte` | -128 to 127 | Converting from `int` to `byte` can truncate bits |
| `short` | -32,768 to 32,767 | Converting from `int` to `short` can truncate bits |
| `char` | 0 to 65,535 | Unsigned; converting from large or negative integers can truncate bits |
| `int` | -2,147,483,648 to 2,147,483,647 | `int` addition/multiplication can overflow |
| `long` | -9,223,372,036,854,775,808 to 9,223,372,036,854,775,807 | Wider than `int`, yet not infinite |
| `BigInteger` | Variable magnitude | Not limited to 32/64 bits; still subject to resource limits |

Java uses fixed-width signed integers for `byte`, `short`, `int`, and `long`. Ordinary integer addition and multiplication that exceed the range yield the low-order bits of the result; for `int` and `long`, this can be understood as arithmetic modulo \(2^{32}\) or \(2^{64}\) interpreted as signed. Primitive `+`, `-`, and `*` **do not automatically throw** `ArithmeticException` on overflow.

## 2. Overflow Happens **Before** Widening to a Larger Type

In Java, the type of an operation is determined by its **operands**, not by the variable receiving the result:

```java
int max = Integer.MAX_VALUE; // 2147483647
int one = 1;

long tooLate = max + one;       // -2147483648
long alsoTooLate = (long) (max + one); // -2147483648
long inTime = (long) max + one; // 2147483648
```

The first two expressions add as `int`; overflow already occurs before the wrong result is converted to `long`. Placing `(long)` on **one operand before the addition** causes the operation to execute in the `long` domain, so this example preserves the exact sum.

Processing diagram:

```text
Wrong:
(int) MAX_VALUE + (int) 1  → int addition → overflow → cast to long
Right:
(long) MAX_VALUE + (int) 1 → long addition → 2147483648
```

This is also why you should not write a check like:

```java
long total = (long) (left + right);
if (total > Integer.MAX_VALUE) {
    // Cannot detect every int overflow that already occurred.
}
```

If `left + right` has already become negative due to overflow, the condition `total > Integer.MAX_VALUE` can be `false` even though the true mathematical sum exceeded the maximum.

### Multiplication and Compound Expressions

```java
int quantity = 50_000;
int unitPrice = 50_000;

long wrong = quantity * unitPrice;        // -1794967296
long right = (long) quantity * unitPrice; // 2500000000
```

Even when the total is accumulated in a `long`, a term entering the sum may already be wrong:

```java
long total = 0L;
total += quantity * unitPrice;          // Multiply as int first, then add to long: wrong.
total += (long) quantity * unitPrice;   // The second multiplication is exact in long.
```

This snippet illustrates evaluation order; it is not a correct way to compute a total because `total` already holds the wrong result from the first line. In real programs, only use the expression with early widening. You must inspect **each addition/multiplication**, especially inside lambdas, mappers, and collectors.

### `byte` and `short` Also Need Attention

Operations like `byte + byte` or `short + short` are **promoted to `int`** before addition; however, when casting the result back to the smaller type, data can be lost:

```java
byte a = 120;
byte b = 20;
int safeInt = a + b;     // 140
byte wrapped = (byte) (a + b); // -116
```

Here there is no overflow in the `int` addition; the bug occurs at the **narrowing conversion** step from `int` back to `byte`. This is why you must distinguish arithmetic overflow from data loss during type conversion.

## 3. Checking Overflow **Right at the Operation**

When the contract requires errors to be detected at each integer operation, use the **exact** APIs in `java.lang.Math`:

```java
int checkedAdd = Math.addExact(a, b);
int checkedSub = Math.subtractExact(a, b);
int checkedMul = Math.multiplyExact(a, b);

long checkedLong = Math.addExact(longA, longB);
```

The variables above are illustrative and must be declared in application context. `Math.addExact`, `subtractExact`, and `multiplyExact` throw `ArithmeticException` when the result exceeds the range of the corresponding parameter/result type.

Example:

```java
try {
    int sum = Math.addExact(Integer.MAX_VALUE, 1);
    System.out.println(sum);
} catch (ArithmeticException ex) {
    System.out.println("Overflow during int addition");
}
```

Output:

```text
Overflow during int addition
```

`Math.addExact(int, int)` checks `int` addition as it happens. If you already wrote `int bad = a + b;` and only later called `Math.addExact(bad, 0)`, the check **cannot** know that an earlier operation overflowed.

### When You Can Widen First and Check Only the Final Sum

Another contract is “the final result must fit in `int`”, even though intermediate values in evaluation order might exceed `int`. When summing an `int[]` array in `long`, you can check via:

```java
int[] values = {Integer.MAX_VALUE, 1, -1};
long exactSum = Arrays.stream(values).asLongStream().sum();
int result = Math.toIntExact(exactSum); // 2147483647
```

The snippet above requires `import java.util.Arrays;` and placement in a method. `Math.toIntExact` checks **narrowing the final result**. If you used `Math.addExact` left-to-right in `int`, adding `Integer.MAX_VALUE + 1` would throw before `-1` is added.

With a `parallel stream`, the grouping of additions can vary; **step-by-step** overflow checks may or may not fail depending on intermediate sums, even though the final mathematical sum is the same. If the contract only checks the final sum, accumulate in a sufficiently wide domain (`long` when provably sufficient, or `BigInteger`) before converting types.

## 4. Overflow and Data Loss Occur **When Casting to a Smaller Type**

Converting `long` to `int` with a cast is not a check. It retains the low-order bits of the source value and can even flip the sign:

```java
long beyondInt = 2_147_483_648L;

int unsafe = (int) beyondInt; // -2147483648
```

If you want to reject out-of-range cases, use:

```java
int checked = Math.toIntExact(beyondInt);
// Throws ArithmeticException.
```

For valid cases:

```java
int checked = Math.toIntExact(42L); // 42
```

`Math.toIntExact` checks **long → int**. It does not directly provide `int → short` or `int → byte` variants; you must check bounds before casting:

```java
static byte toByteExact(int value) {
    if (value < Byte.MIN_VALUE || value > Byte.MAX_VALUE) {
        throw new ArithmeticException("outside byte range: " + value);
    }
    return (byte) value;
}
```

This is an illustrative method that must be placed inside a class. For `short`, substitute `Short.MIN_VALUE`/`Short.MAX_VALUE`. For `char`, the range is 0 to `Character.MAX_VALUE` and unsigned. Do not use `(byte)`, `(short)`, or `(char)` as a range check.

### The Trap of Checking **After** the Cast

```java
long original = 2_147_483_648L;
int narrowed = (int) original;

// Always true, so it fails to detect that original was outside int:
boolean nowFitsInt = narrowed >= Integer.MIN_VALUE
        && narrowed <= Integer.MAX_VALUE;
```

After the cast, `narrowed` is **by definition** an `int`; comparing it against `Integer.MIN_VALUE` and `Integer.MAX_VALUE` cannot validate the original value. You must check `original` **before** casting or use `Math.toIntExact(original)`.

You can perform a round-trip check when the source **has not already overflowed**:

```java
long original = 2_147_483_648L;
int narrowed = (int) original;
boolean exact = (long) narrowed == original; // false
```

This round-trip pattern works for `long → int` conversion, though `Math.toIntExact` makes the check's intent clearer. **If `original` itself was produced by an `int` addition that overflowed**, a round trip cannot recover the lost mathematical sum either.

## 5. `BigInteger`/`BigDecimal` Conversions: Check Both Range and Fractional Part

`BigInteger` can exceed the `long` limit. Ordinary integer conversion methods can drop high-order bits:

```java
BigInteger large = BigInteger.valueOf(Long.MAX_VALUE)
        .add(BigInteger.ONE);

long wrapped = large.longValue(); // Long.MIN_VALUE
```

When you need to preserve the entire numerical value, use:

```java
long checked = large.longValueExact();
// Throws ArithmeticException because large exceeds the long range.
```

Exact APIs include `BigInteger.intValueExact()`, `longValueExact()`, `shortValueExact()`, and `byteValueExact()`. Do not call `longValue()` and then check the range of the resulting `long` variable; by then most of the value may already be lost.

With `BigDecimal`, there are **two forms of data loss** when converting to an integral type:

1. The value exceeds the target type's range.
2. The value has a nonzero fractional part and conversion truncates the fraction.

Example:

```java
BigDecimal decimal = new BigDecimal("12.5");

int truncated = decimal.intValue(); // 12, the .5 part is dropped.
int exact = decimal.intValueExact(); // ArithmeticException.
```

`BigDecimal.intValueExact()`/`longValueExact()` rejects both out-of-range results and non-integer values. If you want to round before converting, the **rounding rule must be specified beforehand**:

```java
BigDecimal rounded = new BigDecimal("12.5")
        .setScale(0, RoundingMode.HALF_UP);
int value = rounded.intValueExact(); // 13
```

The rounding example requires `import java.math.RoundingMode`. `HALF_UP` is only an example policy; for financial calculations, the result might require `HALF_EVEN` or disallow rounding altogether. Clearly distinguish “value fits target type” from “exact conversion without losing fractional part”.

## 6. Converting `double` to Integer Is Not Like `int` Overflow

Casting from `double` to `int`/`long` behaves completely differently from casting `long` to `int`. In Java, narrowing conversion from `double` to an integral type first rounds toward zero; for `NaN` the result is 0; when magnitude exceeds the target range, the result **saturates at the limits** of the target type.

```java
(int) 12.9;                     // 12: drops fractional part.
(int) Double.NaN;               // 0.
(int) Double.POSITIVE_INFINITY; // Integer.MAX_VALUE.
(int) Double.NEGATIVE_INFINITY; // Integer.MIN_VALUE.
(long) Double.POSITIVE_INFINITY;// Long.MAX_VALUE.
```

Thus, Java does not throw an error when casting an overly large `double` value to `int`. If the contract only allows finite numbers, within range, and with no fractional part, check **before casting**:

```java
static int doubleToIntExact(double value) {
    if (!Double.isFinite(value)
            || value < Integer.MIN_VALUE
            || value > Integer.MAX_VALUE
            || value != Math.rint(value)) {
        throw new IllegalArgumentException("not an exact int: " + value);
    }
    return (int) value;
}
```

This is an illustrative method that needs to be inside a class. `Math.rint(value)` returns the nearest integer as a `double`, and the condition `value != Math.rint(value)` here confirms **there is no fractional part**. It does not itself guarantee that a `double` originating from a decimal source was completely exact.

Converting the other way from `long` to `double` can also lose precision without throwing an error. For example, `2^53 + 1` cannot be represented exactly as a `double`:

```java
long original = 9_007_199_254_740_993L;
double approximate = original; // Rounded to 9007199254740992.0.
```

**Do not use `(long) approximate == original` as a general check** for `long → double`: casting a large `double` back to `long` saturates and another value could give a misleading result. If the contract requires exact integers, stay in `long`/`BigInteger`, or use an appropriate decimal model rather than passing through `double`.

### JSON/JavaScript Scenario

Java `long` integers can exceed the safe integer range of JavaScript `Number` (`2^53 - 1`). If a large `long` is transmitted as a JSON number and parsed by JavaScript, precision may already be lost **before Java receives the data back**. When an API must transmit exact 64-bit integers through JavaScript clients, design the schema accordingly—for instance, representing them as decimal strings and parsing/validating appropriately on both ends. Testing `long` on the backend is not enough to confirm a safe JSON round trip.

## 7. Distinguishing **Input**, **Per-Operation**, and **Output** Checks

The same problem can have three reasonable contracts with very different behaviors.

### Contract A: Validate Inputs, Compute in a Provably Wide-Enough Domain

If each element is an `int` and you are summing all elements of an `int[]` array in `long`, the mathematical sum of such an array fits in `long`. Use:

```java
long sum = Arrays.stream(values).asLongStream().sum();
```

For an `IntStream` that can yield more than the maximum number of elements in an array, you cannot automatically infer that `long` is always enough. You must know the element count limit and per-element magnitude in the contract.

### Contract B: Throw an Error if **Any Intermediate Operation** Overflows

Use a sequential loop with `Math.addExact`/`multiplyExact` in the chosen type. Example:

```java
int total = 0;
for (int value : values) {
    total = Math.addExact(total, value);
}
```

If an intermediate sum exceeds `int`, an error is thrown at that point. This approach fits when the contract itself requires every step to stay within the accumulator type.

### Contract C: Compute Exact Mathematical Sum, Check Only the Output Type

Accumulate in `long` if wide enough, or `BigInteger` if `long` cannot be proven sufficient. Then narrow:

```java
BigInteger total = numbers.stream()
        .map(BigInteger::valueOf)
        .reduce(BigInteger.ZERO, BigInteger::add);

int result = total.intValueExact();
```

This snippet assumes `numbers` is a `Stream<Long>`; it is not a standalone program. Thanks to `BigInteger`, there is no intermediate 32/64-bit overflow. `intValueExact()` only rejects when the **final sum** exceeds the `int` range.

**Important:** Placing `Math.toIntExact` at the end does not fix `int` or `long` operations that already overflowed earlier. It validates the result it actually receives, not the mathematical result that previously existed.

## 8. Complete Java 17+ Program for Observation

Save as **`OverflowCastDemo.java`**. The program logs only deterministic results, catching exceptions in test cases so it does not depend on exact JDK exception messages:

```java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.util.Arrays;

public class OverflowCastDemo {
    public static void main(String[] args) {
        int max = Integer.MAX_VALUE;
        int one = 1;
        long late = (long) (max + one);
        long early = (long) max + one;
        System.out.println("late widen = " + late);
        System.out.println("early widen = " + early);

        try {
            Math.addExact(max, one);
            System.out.println("checked add = valid");
        } catch (ArithmeticException ex) {
            System.out.println("checked add = overflow");
        }

        long beyondInt = (long) max + one;
        System.out.println("narrow cast = " + (int) beyondInt);
        try {
            Math.toIntExact(beyondInt);
            System.out.println("toIntExact = valid");
        } catch (ArithmeticException ex) {
            System.out.println("toIntExact = overflow");
        }

        int left = 50_000;
        int right = 50_000;
        System.out.println("late multiply = " + (long) (left * right));
        System.out.println("early multiply = " + ((long) left * right));

        int[] values = {Integer.MAX_VALUE, 1};
        System.out.println("int sum = " + Arrays.stream(values).sum());
        System.out.println("long sum = "
                + Arrays.stream(values).asLongStream().sum());

        BigInteger beyondLong =
                BigInteger.valueOf(Long.MAX_VALUE).add(BigInteger.ONE);
        System.out.println("BigInteger longValue = " + beyondLong.longValue());
        try {
            beyondLong.longValueExact();
            System.out.println("BigInteger exact = valid");
        } catch (ArithmeticException ex) {
            System.out.println("BigInteger exact = overflow");
        }

        BigDecimal fractional = new BigDecimal("12.5");
        System.out.println("BigDecimal intValue = " + fractional.intValue());
        try {
            fractional.intValueExact();
            System.out.println("BigDecimal exact = valid");
        } catch (ArithmeticException ex) {
            System.out.println("BigDecimal exact = fractional");
        }

        System.out.println("NaN cast = " + (int) Double.NaN);
        System.out.println("infinity cast = "
                + (int) Double.POSITIVE_INFINITY);
    }
}
```

Compile/run in the directory containing the file:

```bash
javac -encoding UTF-8 OverflowCastDemo.java
java OverflowCastDemo
```

Stdout:

```text
late widen = -2147483648
early widen = 2147483648
checked add = overflow
narrow cast = -2147483648
toIntExact = overflow
late multiply = -1794967296
early multiply = 2500000000
int sum = -2147483648
long sum = 2147483648
BigInteger longValue = -9223372036854775808
BigInteger exact = overflow
BigDecimal intValue = 12
BigDecimal exact = fractional
NaN cast = 0
infinity cast = 2147483647
```

Result pairs to compare:

- `late widen` vs `early widen`: addition already overflowed before the cast in the first case.
- `narrow cast` vs `toIntExact`: cast drops high bits, while exact conversion rejects.
- `late multiply` vs `early multiply`: operand types determine the multiplication.
- `int sum` vs `long sum`: accumulator type determines sum safety.
- `BigInteger.longValue` vs `longValueExact`: one can truncate bits, the other checks.
- `BigDecimal.intValue` vs `intValueExact`: one can drop the fractional part, the other rejects.
- Casting `NaN`/infinity to `int` does not raise an exception.

## 9. Boundary Testing at Each Failure Point

To catch real bugs instead of only checking that “the result looks plausible”, design test cases right where data can be lost.

| Scenario | Expression/value | Assertion needed |
| --- | --- | --- |
| Addition at `int` upper bound | `Integer.MAX_VALUE + 1` | `+` wraps; `Math.addExact` throws |
| Subtraction at `int` lower bound | `Integer.MIN_VALUE - 1` | `-` wraps; `Math.subtractExact` throws |
| Multiplication exceeding `int` | `50_000 * 50_000` | `int` is wrong; widen operand to `long` before multiplying |
| Widening too late | `(long) (max + 1)` | Negative overflowed result |
| Widening in time | `(long) max + 1` | 2,147,483,648 |
| Narrowing at upper bound | `(int) 2_147_483_648L` | Negative value; `Math.toIntExact` throws |
| Valid narrowing | `Math.toIntExact(2_147_483_647L)` | Returns `Integer.MAX_VALUE` |
| Narrowing at lower bound | `Math.toIntExact(-2_147_483_649L)` | Throws |
| `BigInteger` exceeding `long` | `Long.MAX_VALUE + 1` as `BigInteger` | `longValueExact()` throws |
| Decimal with fractional part | `new BigDecimal("12.5")` | `intValue()` truncates; `intValueExact()` throws |
| Non-finite `double` | `NaN`, `+Infinity` | Cast has special rules; strict APIs must reject beforehand |
| Large integer to `double` | `9_007_199_254_740_993L` | Can lose precision |

### A Helper Checking `int` to `byte` Conversion

```java
static byte toByteExact(int input) {
    if (input < Byte.MIN_VALUE || input > Byte.MAX_VALUE) {
        throw new ArithmeticException("byte range exceeded");
    }
    return (byte) input;
}
```

Checking `127` succeeds; `128` and `-129` are rejected. If you cast first and then check the `byte` range, the range condition is always true because the variable already has type `byte`.

### A Helper Checking Multiplication and Intentional Narrowing

```java
static int multiplyThenNarrow(int a, int b) {
    long product = (long) a * b;
    return Math.toIntExact(product);
}
```

This method computes the product of two `int` values in `long`, then returns `int` only if the final product fits the type. For two `int` arguments, the mathematical product always fits in `long`, so this is appropriate when **only the final result of the multiplication needs checking**. It does not differ from `Math.multiplyExact(a, b)` in acceptance or rejection for a single `int * int` multiplication, yet clearly expresses the “widen then narrow” idea.

The two helpers above are **illustrative code**, to be placed inside a class to compile.

## 10. Diagnosing Bugs Already Happening in a System

If you encounter unexpected negative numbers, a sum decreasing when adding positive elements, or strange values after type conversion, inspect **every arithmetic boundary**:

1. **Record the actual types of operands:** `int`, `long`, `BigInteger`, `BigDecimal`, `double`? What type does an expression inside a lambda return?
2. **Locate the first operation that loses data:** before the cast or at the cast? Check multiplication, addition, subtraction, bit shifts, and aggregations.
3. **Reproduce with boundary values:** `MAX_VALUE`, `MIN_VALUE`, `MAX_VALUE + 1` in a wider type, negative values, values with fractional parts.
4. **Replace with exact checks at the right point:** `Math.addExact`, `Math.multiplyExact`, `Math.toIntExact`, `BigInteger.longValueExact`, `BigDecimal.intValueExact`.
5. **Re-verify the contract:** should an error occur on intermediate overflow, or only if the final result does not fit the type? Is rounding/truncation of fractional parts allowed?
6. **Check storage/transport layers:** SQL column types, JSON numbers via JavaScript, string parsing, API clients. A value may have already lost precision before entering the method being debugged.

For example, when debugging a DTO mapping containing `(int) order.getTotalCents()`, look up the return type of `getTotalCents()` and its actual value range. If it returns `long`, switching to `Math.toIntExact` surfaces the error right at the boundary instead of feeding a negative value downstream. However, if `getTotalCents()` was already computed by an overflowing `int * int` multiplication, you must first fix the multiplication where the value is produced.

**Useful logs** should include the input values (within security bounds), type and unit, operation name, and target field name; avoid logging only “invalid number” without context. For critical flows, test exact arithmetic results against `BigInteger` or `BigDecimal` as an oracle, rather than using the same overflow-prone primitive calculation as the expected value.

## 11. Common Mistakes

- **“Assigning to `long` makes it safe”**: wrong if the operands of addition/multiplication are both still `int`.
- **“Casting to `int` warns automatically”**: wrong; casting from `long` to `int` can truncate bits.
- **“After casting, the value is within `int` range so there was no overflow”**: a tautology about the variable's type does not prove the range of the value before the cast.
- **“`Math.toIntExact` at the end catches every wrong addition”**: it only checks the `long` argument it receives; it cannot trace earlier overflows.
- **“`BigInteger.longValue()` is the same as `longValueExact()`”**: no; the method without `Exact` can drop high-order bits.
- **“`BigDecimal.intValue()` is always a valid conversion”**: it can drop the fractional part and lose out-of-range values.
- **“`(int) Double.NaN` must throw an exception”**: the cast returns 0 according to Java rules.
- **“Every `long` converts accurately to `double`”**: false for large numbers not representable in binary64.
- **“Testing a few small numbers is enough”**: bugs only show up at `MAX_VALUE`, `MIN_VALUE`, out-of-bounds values, and intermediate calculations.
- **“Corrupted data can be fixed by casting one more time”**: once an earlier operation has wrapped around or rounded, casting cannot recover lost information.

## 12. Practical Rules

When designing or testing integer calculations, determine the range of the mathematical total **before writing the expression**. If a primitive type suffices, use it and guard overflow-prone operations with `Math.*Exact` according to the contract. If the current type is too narrow, widen operands **before the operation**. If you must convert to a smaller type, use an exact conversion or check bounds **before casting**. If the final sum exceeds `long`, use `BigInteger`; if values have fractional parts, clarify whether rounding is allowed or exactness must be preserved before converting to an integer.

A check placed at the right moment ensures errors appear at their source. A check placed too late only inspects an **already-altered value**, and cannot prove the original result was right.

### Official Java Documentation

- [JLS §5.1 — Primitive conversions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.1)
- [JLS §15.18 — Additive operators](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.18)
- [`Math` — `addExact`, `multiplyExact`, `toIntExact`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Math.html)
- [`BigInteger` — exact conversion](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigInteger.html)
- [`BigDecimal` — exact conversion](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html)