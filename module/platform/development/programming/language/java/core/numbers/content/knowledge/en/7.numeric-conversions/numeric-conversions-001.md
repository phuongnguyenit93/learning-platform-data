# Widening and Narrowing Between Numeric Types in Java

**Numeric conversion** is changing a value between Java's numeric primitive types: `byte`, `short`, `char`, `int`, `long`, `float`, `double`. Two important groups:

- **Widening primitive conversion**: converting to a type that Java allows expanding to **automatically**, such as `int` → `long` or `int` → `double`.
- **Narrowing primitive conversion**: converting in a direction where Java requires an **explicit cast** in most contexts, such as `long` → `int`, `double` → `int`, or `int` → `byte`.

Three independent questions should be distinguished: **whether the conversion is syntactically allowed**, **whether the mathematical value is preserved exactly**, and **whether the target type's range is sufficient to hold the result**. Widening being allowed automatically does not mean every digit is preserved unconditionally; narrowing is not simply "truncating the fractional part" for all pairs of types.

## 1. Numeric primitive types and limits

| Type | Width | Value range or meaning |
| --- | ---: | --- |
| `byte` | 8 bits | -128 to 127 |
| `short` | 16 bits | -32,768 to 32,767 |
| `char` | 16 bits | 0 to 65,535 (unsigned UTF-16 code unit) |
| `int` | 32 bits | -2,147,483,648 to 2,147,483,647 |
| `long` | 64 bits | -9,223,372,036,854,775,808 to 9,223,372,036,854,775,807 |
| `float` | 32 bits | IEEE 754 floating-point number, ~6–9 significant decimal digits of precision |
| `double` | 64 bits | IEEE 754 floating-point number, ~15–17 significant decimal digits of precision |

`char` is an **unsigned integer type** in Java numeric conversions, even though it is commonly used for characters. `boolean` **does not belong to the numeric types**: there is no automatic conversion or primitive cast between `boolean` and `int`.

`float` and `double` have a very wide magnitude range, but they do not represent every integer or every decimal fraction exactly. Floating-point bit width consists of a sign bit, exponent, and *significand*; precision cannot be inferred from the 32/64-bit width alone.

## 2. Valid widening paths

Java allows the following widening primitive conversions:

| Source type | Widening target types |
| --- | --- |
| `byte` | `short`, `int`, `long`, `float`, `double` |
| `short` | `int`, `long`, `float`, `double` |
| `char` | `int`, `long`, `float`, `double` |
| `int` | `long`, `float`, `double` |
| `long` | `float`, `double` |
| `float` | `double` |
| `double` | No wider numeric primitive type |

Example:

```java
byte b = -12;
short s = b;      // byte -> short
int i = s;        // short -> int
long l = i;       // int -> long
float f = l;      // long -> float
double d = f;     // float -> double

char letter = 'A';
int codePointUnit = letter; // 65: char -> int
long codeAsLong = letter;   // char -> long
```

Both branches require **no cast**. Note that `char` does not widen to `short`, because signed `short` cannot hold the entire 0..65535 range of `char`; `byte` also does not widen to `char` because `byte` has negative values.

```java
char c = 'A';
// short invalid = c; // error: char -> short does not widen
byte b = 65;
// char invalid2 = b; // error: byte -> char does not widen
```

These are illustrative snippets meant to be placed inside a class, not standalone programs. The commented lines will cause compilation errors if uncommented.

### Widening that can lose precision

The following conversions **always preserve the value exactly**:

- `byte` → `short`/`int`/`long`/`float`/`double`.
- `short` and `char` → `int`/`long`/`float`/`double`.
- `int` → `long` or `double`.
- `float` → `double` preserves the exact binary floating-point value stored, including `NaN` and infinities.

However, `int` → `float`, `long` → `float`, and `long` → `double` **can round**. Specifically, `float` has 24 bits of significand precision and `double` has 53 bits; consecutive integers that are too large can no longer be represented distinctly.

```java
int preciseAsInt = 16_777_217;    // 2^24 + 1
float roundedAsFloat = preciseAsInt; // rounded to 16777216.0f

long preciseAsLong = 9_007_199_254_740_993L; // 2^53 + 1
double roundedAsDouble = preciseAsLong; // rounded to 9007199254740992.0
```

Both assignments above are **valid widenings**, causing neither compilation errors nor exceptions. However, data loses one unit because the target type lacks sufficient precision. When comparing IDs, integer monetary amounts, or large counters, this is why you should not accidentally convert a `long` to a `double`.

## 3. Narrowing: when must you write a cast?

A narrowing primitive conversion is usually written with a cast operator `(TargetType) value`:

```java
long large = 1_000;
int number = (int) large;        // long -> int
double decimal = 42.75;
int truncated = (int) decimal;   // double -> int: 42
int value = 260;
byte small = (byte) value;       // int -> byte: 4
```

If the cast is omitted in an ordinary assignment context, the compiler rejects it:

```java
long large = 1_000;
// int wrong = large;    // error: possible lossy conversion from long to int
double price = 42.75;
// int wrong2 = price;   // error: double -> int requires a cast
```

A cast **permits the conversion under the language rules**; it does not verify that the value falls within the target type's range. Java does not automatically detect overflow when casting primitive integers; code that compiles can still lose information.

Common narrowing examples include `int` → `byte`/`short`/`char`, `long` → `int`, `double` → `float`, and `float`/`double` → an integer type.

## 4. Narrowing from integer to integer: keeping the low bits

When converting an integer to a narrower integer type, Java discards the high bits and keeps as many low bits as the width of the target type. Then:

- `byte` and `short` are interpreted as signed two's complement.
- `char` is a 16-bit unsigned value from 0 to 65,535.

Examples:

| Expression | Result | Explanation |
| --- | ---: | --- |
| `(byte) 127` | 127 | Within byte range |
| `(byte) 128` | -128 | Low 8 bits are `0x80`, with the sign bit set |
| `(byte) 255` | -1 | Low 8 bits are `0xFF` |
| `(byte) 256` | 0 | Low 8 bits are all 0 |
| `(byte) 260` | 4 | 260 mod 256 equals 4 |
| `(short) 65_535` | -1 | Low 16 bits are all 1 |
| `(char) -1` | 65,535 | Low 16 bits are `0xFFFF` |
| `(int) Long.MAX_VALUE` | -1 | Keeps the low 32 bits of `long` |

```java
int source = 260;
byte byteValue = (byte) source; // 4
short shortValue = (short) 65_535; // -1
char charValue = (char) -1; // char code 65535
int lowerBits = (int) Long.MAX_VALUE; // -1
```

**Do not use a cast to check the value range.** If you need to reject any `long` that does not fit in an `int`, use `Math.toIntExact(longValue)`: this method throws `ArithmeticException` when outside the `int` range.

```java
long valid = 123;
int exact = Math.toIntExact(valid); // 123

// Math.toIntExact(Long.MAX_VALUE) throws ArithmeticException
```

`Math.toIntExact` has no corresponding variant for every smaller pair of types: to reject values when narrowing to `byte`/`short`/`char`, check the range explicitly before casting.

## 5. Narrowing from floating-point to integer: truncating fractions, clamping at bounds

For `float`/`double` → `int` or `long`, Java uses a conversion defined by these steps:

1. If the operand is `NaN`, the integer result is `0`.
2. If the value is finite and within the representable range, **discard the fractional part toward zero** (*truncate toward zero*), rather than rounding to the nearest integer.
3. If the value is too large or too small, the result **is clamped at the corresponding bound** (`MIN_VALUE` or `MAX_VALUE`).
4. `+Infinity` and `-Infinity` convert to the positive bound and negative bound, respectively.

Examples:

```java
int positive = (int) 12.99;          // 12
int negative = (int) -12.99;         // -12
int nan = (int) Double.NaN;         // 0
int positiveInf = (int) Double.POSITIVE_INFINITY; // 2147483647
int negativeInf = (int) Double.NEGATIVE_INFINITY; // -2147483648
long huge = (long) 1e100;           // Long.MAX_VALUE
```

**Truncation is not the same as `Math.floor`**: `(int)-12.99` equals `-12`, whereas `Math.floor(-12.99)` equals `-13.0`.

### Targets smaller than `int`: a subsequent bit-truncation step applies

For `float`/`double` → `byte`, `short`, or `char`, Java **converts the floating-point value to `int` first**, then narrows further from `int` to the smaller integer type:

```java
byte a = (byte) 257.8;          // 1: 257 -> byte
byte b = (byte) Double.NaN;     // 0
char c = (char) -1.9;           // 65535: -1 -> char
byte saturatedThenNarrowed = (byte) 1e100; // -1: int MAX -> low 8 bits
```

Therefore, "clamping at the bound" when a floating-point value exceeds the `int` range **does not mean** that casting further down to `byte` will clamp it at 127 or -128. Bit truncation still occurs after the conversion step to `int`.

If you need to round a floating-point number according to a specific policy, casting is only one very specific choice. For example, `Math.round` has its own rules and `BigDecimal` has different rounding modes; do not substitute them mechanically for one another.

## 6. Narrowing between `double` and `float`

`double` → `float` requires a cast in an assignment context:

```java
double d = 1.25;
float f = (float) d;   // 1.25f, represented exactly in this example
```

During narrowing, a finite value may:

- **Be rounded** because `float`'s 24-bit precision is lower than `double`'s 53-bit precision.
- Become `Float.POSITIVE_INFINITY` or `Float.NEGATIVE_INFINITY` if its magnitude exceeds the maximum finite `float` value.
- Become `+0.0f` or `-0.0f` (or a *subnormal* number) if its magnitude is too small.
- Preserve `NaN` or infinity according to the nature of the source value.

```java
double large = 1e100;
float infinity = (float) large; // Infinity

double tiny = 1e-100;
float underflow = (float) tiny; // +0.0f
```

The reverse widening `float` → `double` is automatic and preserves the existing `float` value exactly; it **cannot recover** digits that were lost when creating the `float`.

For example, `double widenedBack = (double) ((float) 0.1);` does not equal the `double` literal `0.1`: the initial value was already rounded during the conversion down to `float` before being widened back.

## 7. Exception: assigning an `int` constant expression to `byte`, `short`, and `char`

Although `int` → `byte`/`short`/`char` is narrowing, Java allows a **narrowing conversion in an assignment context** for compile-time constant expressions that satisfy the conditions.

```java
byte a = 100;      // valid: int literal 100 fits in byte
short b = 30_000;  // valid: int literal fits in short
char c = 65;       // valid: int literal fits in char

final int LIMIT = 120; // constant variable: initializer is a constant expression
byte value = LIMIT;    // valid because the value fits in byte

// byte invalid = 128;    // error: exceeds byte
// short invalid2 = 40000; // error: exceeds short
// char invalid3 = -1;    // error: char is non-negative
```

**A value that happens to look small at runtime is not enough**; for a regular `int` variable, the compiler does not narrow automatically:

```java
int count = 100;
// byte no = count; // error: count is a regular int variable
byte yes = (byte) count;
```

The constant case is a language rule applied in specific contexts; it **does not replace** casting in general situations. A `long` literal such as `100L` also does not automatically assign to `byte` just because the value 100 fits in range.

## 8. Arithmetic operations can change types before assignment

Java applies **binary numeric promotion** with standard arithmetic operators. `byte`, `short`, and `char` are typically promoted to `int` in addition, subtraction, and multiplication. If a `long` is present and there is no floating-point operand, the expression is evaluated as `long`; if `float` or `double` is present, the corresponding promotion rule applies.

```java
byte left = 10;
byte right = 20;
// byte sum = left + right; // error: left + right has type int
int sum = left + right;   // 30
byte smallSum = (byte) (left + right); // 30, though data could be lost for other values
```

Dangerous consequence: casting **after** an operation has overflowed cannot recover the mathematical result:

```java
int quantity = 100_000;
long wrong = (long) (quantity * quantity); // int overflow -> 1410065408L
long correct = (long) quantity * quantity; // long multiplication -> 10000000000L
```

Even though `wrong` has type `long`, the multiplication inside the parentheses is still `int`. Casting one operand **before the multiplication** changes the computation type, because the `long` operand forces the remaining `int` operand to be promoted to `long`.

Another case with `float`:

```java
long veryLarge = 9_007_199_254_740_993L;
double rounded = veryLarge;      // rounded
long convertedBack = (long) rounded; // 9007199254740992L
```

Values lost during widening cannot be retrieved by narrowing back.

### Compound assignment can perform implicit narrowing

`+=`, `-=`, `*=` have type semantics equivalent to performing the operation and then converting the result back to the type of the left-hand variable (noting that the left-hand side is evaluated only once):

```java
byte b = 127;
b += 1;     // valid, but b becomes -128 due to narrowing after addition
// b = b + 1; // error: b + 1 has type int, cannot assign back to byte automatically
```

The `b++` form also updates the value back to the variable's type and can overflow; short syntax does not imply a guarantee against data loss.

## 9. Boxing, unboxing, and primitive conversions: do not conflate them

Wrapper types like `Integer`, `Long`, and `Double` are **reference types**, distinct from the primitive types `int`, `long`, and `double`. Java has boxing/unboxing in certain contexts, but not every pair of wrappers converts automatically to one another.

```java
Integer boxed = 42;
long widenedAfterUnboxing = boxed; // Integer -> int (unbox) -> long
Long boxedLong = 42L;              // long -> Long (boxing)

// Long invalid = boxed;          // cannot automatically convert Integer -> Long via unbox/widen/box
Long explicit = boxed.longValue();  // get long then box
```

Unboxing `null` can throw `NullPointerException`:

```java
Integer missing = null;
// long n = missing; // compiles, but throws NullPointerException at runtime
```

Topics such as parsing the string `"42"` with `Integer.parseInt`, storing money as `BigDecimal`, or representing unbounded integers with `BigInteger` are separate mechanisms, not primitive widening/narrowing rules.

## 10. Runnable Java 17+ program and verified output

Create the file **`PrimitiveConversionsOverviewDemo.java`**:

```java
public class PrimitiveConversionsOverviewDemo {
    public static void main(String[] args) {
        byte b = -10;
        long widened = b;
        System.out.println("widenByteToLong=" + widened);

        char letter = 'A';
        int charCode = letter;
        System.out.println("widenCharToInt=" + charCode);

        int intBeyondFloatPrecision = 16_777_217;
        float roundedFloat = intBeyondFloatPrecision;
        System.out.println("floatRoundedToInt=" + (int) roundedFloat);

        long longBeyondDoublePrecision = 9_007_199_254_740_993L;
        double roundedDouble = longBeyondDoublePrecision;
        System.out.println("doubleRoundedToLong=" + (long) roundedDouble);

        System.out.println("narrowIntToByte=" + (byte) 257);
        System.out.println("narrowNegativeToChar=" + (int) (char) -1);
        System.out.println("floatToIntTrunc=" + (int) 9.99);
        System.out.println("negativeFloatToIntTrunc=" + (int) -9.99);
        System.out.println("positiveInfinityToInt=" +
                (int) Double.POSITIVE_INFINITY);
        System.out.println("nanToInt=" + (int) Double.NaN);
        System.out.println("longToInt=" + (int) Long.MAX_VALUE);
        System.out.println("doubleToLongClamped=" + (long) 1e100);

        byte compound = 127;
        compound += 1;
        System.out.println("compoundByte=" + compound);

        int quantity = 100_000;
        long earlyWide = (long) quantity * quantity;
        long lateWide = (long) (quantity * quantity);
        System.out.println("earlyWide=" + earlyWide);
        System.out.println("lateWide=" + lateWide);

        byte constantByte = 127;
        System.out.println("constByte=" + constantByte);

        long roundTrip = (long) roundedDouble;
        System.out.println("roundTripLoss=" +
                (roundTrip == longBeyondDoublePrecision));
    }
}
```

Run with JDK 17 or later:

```bash
javac PrimitiveConversionsOverviewDemo.java
java PrimitiveConversionsOverviewDemo
```

Expected output:

```text
widenByteToLong=-10
widenCharToInt=65
floatRoundedToInt=16777216
doubleRoundedToLong=9007199254740992
narrowIntToByte=1
narrowNegativeToChar=65535
floatToIntTrunc=9
negativeFloatToIntTrunc=-9
positiveInfinityToInt=2147483647
nanToInt=0
longToInt=-1
doubleToLongClamped=9223372036854775807
compoundByte=-128
earlyWide=10000000000
lateWide=1410065408
constByte=127
roundTripLoss=false
```

Pay particular attention to `earlyWide` differing from `lateWide`: the position of the cast changes the type **when the multiplication is performed**. The two floating-point lines illustrate that widening can round large integers; casting back only reads the already-rounded value.

## 11. Choosing a conversion approach based on data requirements

| Requirement | Appropriate approach | Things to note |
| --- | --- | --- |
| Convert `int` to `long` | `long n = intValue;` | Value is preserved exactly |
| Convert `long` to `int` without allowing data loss | `Math.toIntExact(longValue)` | Throws `ArithmeticException` if out of range |
| Convert `int` to `byte` and accept low bits | `(byte) intValue` | Can yield negative numbers due to two's complement |
| Convert `int` to `byte` but must be within -128..127 | Check `Byte.MIN_VALUE <= n && n <= Byte.MAX_VALUE` before casting | Handle out-of-range cases yourself |
| Convert `double` to `int` | `(int) doubleValue` if truncate-toward-zero policy matches | `NaN` becomes 0; infinity/out-of-range is clamped |
| Store very large `long` integers accurately | Keep `long` or use `BigInteger` | Converting through `double` can lose units |
| Compute product of two `int` values that may exceed 32 bits | `(long) a * b` | Cast occurs before multiplication |
| Require overflowing arithmetic to report an error | `Math.addExact`, `subtractExact`, `multiplyExact` | Must choose the right overload and guard at the computation step |

### Checklist to avoid conversion bugs

1. Identify the **source type and target type**; check widening paths to know whether a cast is needed.
2. Check **precision**, especially `int`/`long` to `float`/`double`; widening is not guaranteed to be completely exact.
3. For integer → integer narrowing, look at **truncated bits**; for floating-point → integer, check the rules for **truncating fractions, `NaN`, and clamping at bounds**.
4. Distinguish **constant expressions** from regular variables when assigning to `byte`/`short`/`char`.
5. If there are intermediate operations, determine the **type used during computation** first, then consider the target variable's type; the cast must be in the right place.
6. If data loss is not permitted, check the value range yourself or use exact-checking APIs instead of casting blindly.

**Conclusion:** *Widening* is primarily an automatic conversion permission in Java's type system; *narrowing* usually must be requested explicitly because of the risk of losing information. Every conversion choice should be based on **value range, precision, and the intent of the calculation**, not merely on whether the line of code compiles.
