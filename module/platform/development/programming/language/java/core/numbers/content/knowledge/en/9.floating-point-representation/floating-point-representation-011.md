# Converting Bit Patterns Back to `float` or `double` Values in Java

## 1. Two Different Tasks: Numeric Value Conversion vs. Bit Reinterpretation

A floating-point value can be stored as an IEEE 754 bit pattern. To recover **the `float` or `double` value from that exact bit pattern**, Java provides two methods:

- `Float.intBitsToFloat(int bits)`: treats the 32 bits of an `int` as the binary representation of a `float`.
- `Double.longBitsToDouble(long bits)`: treats the 64 bits of a `long` as the binary representation of a `double`.

The most important point: **reinterpreting a bit pattern is completely different from numeric casting**.

```java
int bits = 0x3F80_0000; // 1065353216 if interpreted as a signed int
float reconstructed = Float.intBitsToFloat(bits); // 1.0f
float converted = (float) bits; // numeric value 1065353216 converted to float
```

`Float.intBitsToFloat` takes the raw 32-bit pattern `0x3F800000` and interprets it according to IEEE 754, producing **1.0**. By contrast, `(float) bits` converts the **integer value** 1_065_353_216 to `float`. The two operations have different meanings even though both start from the same `int` variable.

For 64 bits, `Double.longBitsToDouble(bits)` differs from `(double) bits` in the same way. When handling binary files, network protocols, hex logs, tests, or bit analysis, determine whether your data is a **bit pattern** or an **integer value to convert**.

## 2. APIs to Know

| Purpose | Java API | Input Type | Return Type |
|---|---|---|---|
| Bit pattern → `float` | `Float.intBitsToFloat(bits)` | `int`, 32-bit | `float` |
| Bit pattern → `double` | `Double.longBitsToDouble(bits)` | `long`, 64-bit | `double` |
| `float` → raw bit pattern | `Float.floatToRawIntBits(value)` | `float` | `int` |
| `double` → raw bit pattern | `Double.doubleToRawLongBits(value)` | `double` | `long` |
| `float` → NaN-canonicalized bit pattern | `Float.floatToIntBits(value)` | `float` | `int` |
| `double` → NaN-canonicalized bit pattern | `Double.doubleToLongBits(value)` | `double` | `long` |

`intBitsToFloat` and `longBitsToDouble` are `static` methods and can be called directly on the wrapper class name without creating `Float`/`Double` objects.

**Distinguishing the two value-to-bits method families:** methods with `Raw` attempt to return the actual bit pattern of the value, including NaN payload information when representation permits. Methods without `Raw` canonicalize all NaNs to a standard NaN pattern:

- `Float.floatToIntBits(Float.NaN)` returns `0x7FC00000`.
- `Double.doubleToLongBits(Double.NaN)` returns `0x7FF8000000000000L`.

Because NaN has multiple bit representations, do not assume a round-trip will preserve **all NaN bits** in every situation; this is explained further in section 7.

## 3. IEEE 754 binary32 and binary64 Representation Structure

Java `float` uses IEEE 754 **binary32**, and `double` uses **binary64**:

| Component | `float` (32-bit) | `double` (64-bit) |
|---|---:|---:|
| Sign bit (*sign*) | 1 | 1 |
| Exponent bits (*exponent*) | 8 | 11 |
| Fraction bits (*fraction/significand field*) | 23 | 52 |
| Exponent offset (*bias*) | 127 | 1023 |
| Total | 32 | 64 |

Layout from highest bit to lowest bit:

```text
float (32 bits):
S | EEEEEEEE | FFFFFFFFFFFFFFFFFFFFFFF
1 |    8     |           23

double (64 bits):
S | EEEEEEEEEEE | FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF
1 |     11      |                         52
```

Here:

- **S**: sign, 0 when non-negative and 1 when negative.
- **E**: stored exponent field with bias (*biased exponent*).
- **F**: fraction field, storing the bits after the binary point of the significand; normal numbers have an **implicit 1 bit** preceding the fraction.

For a **normal** number whose exponent field lies between 0 and all 1-bits, the mathematical value is:

\[
(-1)^S \times \left(1+\frac{F}{2^p}\right) \times 2^{E-\text{bias}}
\]

Where `p = 23` for `float`, `p = 52` for `double`, and `F` is the unsigned integer represented by the fraction bits.

When the exponent field is **0**, the formula changes to **subnormal** when `F != 0`:

\[
(-1)^S \times \frac{F}{2^p} \times 2^{1-\text{bias}}
\]

If `E = 0` and `F = 0`, the result is **+0.0 or -0.0**, depending on the sign bit. If `E` consists of all 1-bits, the special interpretations described in section 6 apply: **infinity** or **NaN**.

**Note:** not every 32/64-bit pattern represents a finite real number. Every pattern can be interpreted by the API, though the result may be a finite number, ±0.0, ±Infinity, or NaN.

## 4. Analyzing a Concrete `float` Bit Pattern

Consider `0x40400000`, consisting of 32 bits:

```text
Hex:     0x40400000
Binary:  01000000 01000000 00000000 00000000
Fields:  0 | 10000000 | 10000000000000000000000
         S |     E    |           F
```

Compute field by field:

1. Sign bit `S = 0`, so the result is positive.
2. Binary exponent field `10000000` equals 128, so actual exponent is \(128 - 127 = 1\).
3. The fraction has leading bit 1 and the rest 0, so \(F/2^{23} = 1/2\).
4. Normalized significand is \(1 + 1/2 = 1.5\).
5. Final value: \(1.5 \times 2^1 = 3.0\).

In Java:

```java
float value = Float.intBitsToFloat(0x4040_0000);
System.out.println(value); // 3.0
```

Flipping the sign bit to 1 while keeping the same exponent and fraction gives `0xC0400000`, yielding **-3.0**:

```java
float negative = Float.intBitsToFloat(0xC040_0000);
System.out.println(negative); // -3.0
```

For `double`, pattern `0x4008000000000000L` also represents 3.0, though the bit allocation and exponent bias differ:

```java
double d = Double.longBitsToDouble(0x4008_0000_0000_0000L);
System.out.println(d); // 3.0
```

As shown, **the numeric value 3.0 has different bit patterns** in `float` and `double`. You cannot pass a 32-bit pattern intended for `float` directly into `Double.longBitsToDouble` and expect the same value.

## 5. Java 17+ Example: Reconstructing Values from Bit Patterns

Create the file `BitsToFloatingDemo.java`:

```java
public class BitsToFloatingDemo {
    public static void main(String[] args) {
        int oneBits = 0x3F80_0000;
        int threeBits = 0x4040_0000;
        int minusThreeBits = 0xC040_0000;
        long doubleThreeBits = 0x4008_0000_0000_0000L;

        System.out.println("float 1 = "
                + Float.intBitsToFloat(oneBits));
        System.out.println("float 3 = "
                + Float.intBitsToFloat(threeBits));
        System.out.println("float -3 = "
                + Float.intBitsToFloat(minusThreeBits));
        System.out.println("double 3 = "
                + Double.longBitsToDouble(doubleThreeBits));

        float reconstructed = Float.intBitsToFloat(oneBits);
        float numericCast = (float) oneBits;
        System.out.println("same as numeric cast? "
                + (reconstructed == numericCast));

        int recovered = Float.floatToRawIntBits(reconstructed);
        System.out.printf("recovered float bits = %08X%n", recovered);

        double pi = Double.longBitsToDouble(
                0x4009_21FB_5444_2D18L);
        System.out.println("double pi = " + pi);
        System.out.printf("double pi bits = %016X%n",
                Double.doubleToRawLongBits(pi));
    }
}
```

Compile and run:

```bash
javac BitsToFloatingDemo.java
java BitsToFloatingDemo
```

Output:

```text
float 1 = 1.0
float 3 = 3.0
float -3 = -3.0
double 3 = 3.0
same as numeric cast? false
recovered float bits = 3F800000
double pi = 3.141592653589793
double pi bits = 400921FB54442D18
```

The π value here is the **nearest binary64 approximation**, not infinite-digit mathematical π. The bit printout shows that the binary64 pattern was recovered from an ordinary finite value.

## 6. Special Patterns: ±0.0, Subnormals, ±Infinity, and NaN

Decoding exponent and fraction fields:

| Exponent Field E | Fraction F | Value |
|---|---|---|
| 0 | 0 | +0.0 or -0.0 depending on sign bit |
| 0 | nonzero | Subnormal (*subnormal*) |
| From 1 to one below all-1s | Any | Finite normal number |
| All-1s | 0 | +Infinity or -Infinity |
| All-1s | nonzero | NaN (*Not a Number*) |

### 6.1. Familiar `float` Patterns

| 32-Bit Pattern | Meaning |
|---|---|
| `0x00000000` | +0.0f |
| `0x80000000` | -0.0f |
| `0x00000001` | Smallest positive subnormal |
| `0x00800000` | Smallest positive normal |
| `0x3F800000` | 1.0f |
| `0x7F800000` | +Infinity |
| `0xFF800000` | -Infinity |
| `0x7FC00000` | Canonical NaN |

### 6.2. Corresponding `double` Patterns

| 64-Bit Pattern | Meaning |
|---|---|
| `0x0000000000000000L` | +0.0 |
| `0x8000000000000000L` | -0.0 |
| `0x0000000000000001L` | Smallest positive subnormal |
| `0x0010000000000000L` | Smallest positive normal |
| `0x3FF0000000000000L` | 1.0 |
| `0x7FF0000000000000L` | +Infinity |
| `0xFFF0000000000000L` | -Infinity |
| `0x7FF8000000000000L` | Canonical NaN |

Hex forms with suffix `L` are `long` literals, even when the top bit is 1 making the `long` value carry a negative sign. `Double.longBitsToDouble` **examines all 64 bits purely as bits**, rather than treating a negative `long` value as a request to return a negative `double`. The `double`'s sign is determined by the sign bit of the IEEE 754 pattern itself.

### 6.3. Two Zeros Compare Equal Numerically Yet Differ in Bit Pattern

```java
float plusZero = Float.intBitsToFloat(0x0000_0000);
float minusZero = Float.intBitsToFloat(0x8000_0000);

System.out.println(plusZero == minusZero); // true
System.out.println(1.0f / plusZero);       // Infinity
System.out.println(1.0f / minusZero);      // -Infinity
```

Although `+0.0f == -0.0f` is `true` under arithmetic comparison, their bit patterns **are not identical**. This matters for exact serialization, byte-level signing/hashing, numeric debugging, or inspecting the sign of zero.

### 6.4. Identifying NaN via Predicate Checks

`NaN` represents a non-numeric result, such as `0.0 / 0.0` in floating-point arithmetic. Java provides:

- `Float.isNaN(value)` or `Double.isNaN(value)`.
- `Float.isInfinite(value)` or `Double.isInfinite(value)`.
- `Float.isFinite(value)` or `Double.isFinite(value)`.

A pattern with an all-1s exponent and a nonzero fraction is NaN, regardless of whether the sign bit is 0 or 1. The fraction bits can contain a *NaN payload*, though this should not be treated as ordinary numeric data.

## 7. Round-Trip and the NaN Payload Issue

For finite values, ±0.0, and ±Infinity, the pair of conversions normally supports exact raw-bit checking:

```java
int bits = 0xBF80_0000; // float pattern for -1.0
float value = Float.intBitsToFloat(bits);
int back = Float.floatToRawIntBits(value);

System.out.println(back == bits); // true
```

For NaN, you must separate **whether the value is classified as NaN** from **whether all payload bits are preserved**:

1. `Float.intBitsToFloat(bits)` and `Double.longBitsToDouble(bits)` interpret the bit pattern under IEEE 754.
2. `Float.floatToIntBits(value)` and `Double.doubleToLongBits(value)` **canonicalize NaN** to a canonical NaN pattern; they do not preserve the original payload.
3. `floatToRawIntBits` and `doubleToRawLongBits` read the raw bits currently present. However, some hardware architectures or operations can **quiet** a *signaling NaN* when a bit pattern is converted into a floating-point value. A bit-perfect round-trip cannot be guaranteed for **every signaling NaN pattern** across all runtime environments.

Therefore, if the goal is **exact bit-level storage/transmission of payloads**, such as storing a binary file with a specific NaN payload, the safest approach is to **keep the original pattern in `int`/`long` or a byte array** throughout transport; call `intBitsToFloat` or `longBitsToDouble` only when numeric calculation is truly required.

If the goal is simply checking whether data is NaN, use `isNaN`; do not compare bits directly against a single NaN pattern. The comparison `NaN == NaN` evaluates to `false` under floating-point rules.

### Runnable Example for NaN and Zero

Save the file `SpecialFloatingBitsDemo.java`:

```java
public class SpecialFloatingBitsDemo {
    public static void main(String[] args) {
        float plusZero = Float.intBitsToFloat(0x0000_0000);
        float minusZero = Float.intBitsToFloat(0x8000_0000);
        float plusInfinity = Float.intBitsToFloat(0x7F80_0000);
        float minusInfinity = Float.intBitsToFloat(0xFF80_0000);
        float nan = Float.intBitsToFloat(0x7FC0_0000);

        System.out.println("zeros equal = " + (plusZero == minusZero));
        System.out.printf("plus zero bits = %08X%n",
                Float.floatToRawIntBits(plusZero));
        System.out.printf("minus zero bits = %08X%n",
                Float.floatToRawIntBits(minusZero));
        System.out.println("1 / +0 = " + (1.0f / plusZero));
        System.out.println("1 / -0 = " + (1.0f / minusZero));
        System.out.println("positive infinity = " + plusInfinity);
        System.out.println("negative infinity = " + minusInfinity);
        System.out.println("is NaN = " + Float.isNaN(nan));
        System.out.println("NaN == NaN = " + (nan == nan));
        System.out.printf("canonical NaN bits = %08X%n",
                Float.floatToIntBits(nan));

        double tiny = Double.longBitsToDouble(1L);
        System.out.println("double smallest positive = " + tiny);
    }
}
```

Compile and run:

```bash
javac SpecialFloatingBitsDemo.java
java SpecialFloatingBitsDemo
```

Output:

```text
zeros equal = true
plus zero bits = 00000000
minus zero bits = 80000000
1 / +0 = Infinity
1 / -0 = -Infinity
positive infinity = Infinity
negative infinity = -Infinity
is NaN = true
NaN == NaN = false
canonical NaN bits = 7FC00000
double smallest positive = 4.9E-324
```

The `0x7FC00000` pattern used in the example is a canonical NaN, so `floatToIntBits`'s output is deterministic. The example **does not claim** that an arbitrary signaling NaN payload will remain unchanged when passed through a `float` value.

## 8. Converting Input Hex/Binary Strings to Bit Patterns

Debugging tools often display IEEE 754 patterns as strings, such as `"40400000"` or `"4008000000000000"`. You must **parse the string into an `int`/`long` holding the corresponding bits** before calling the bit-interpretation API.

Example:

```java
int floatBits = Integer.parseUnsignedInt("40400000", 16);
float a = Float.intBitsToFloat(floatBits); // 3.0f

long doubleBits = Long.parseUnsignedLong("4008000000000000", 16);
double b = Double.longBitsToDouble(doubleBits); // 3.0
```

Why use `parseUnsignedInt`/`parseUnsignedLong`?

- 32-bit or 64-bit patterns can have the highest bit set.
- `Integer.parseInt("FF800000", 16)` cannot parse as a positive signed `int` value, whereas `Integer.parseUnsignedInt("FF800000", 16)` stores the exact **32-bit pattern** in `int` (the `int` value itself may appear negative).
- Similarly, `Long.parseUnsignedLong("FFF0000000000000", 16)` retains the exact **64 bits**, even though the `long` value is negative when viewed as a signed number.

```java
int negativeInfinityBits =
        Integer.parseUnsignedInt("FF800000", 16);
float negativeInfinity =
        Float.intBitsToFloat(negativeInfinityBits); // -Infinity
```

The parse APIs do not arbitrarily strip prefixes: for example, `Integer.parseUnsignedInt("0x40400000", 16)` is invalid syntax because it contains `0x`. If incoming data includes a prefix, validate the input and strip the prefix per your format rules before parsing.

If the source is a 32-bit binary string, use `Integer.parseUnsignedInt(text, 2)`; for 64-bit, use `Long.parseUnsignedLong(text, 2)`. Always validate length, radix, and format when reading untrusted sources to avoid silently accepting malformed character counts or widths outside the protocol.

### Runnable Example: Parsing 32/64-Bit Patterns

Create the file `ParseFloatingBitsDemo.java`:

```java
public class ParseFloatingBitsDemo {
    public static void main(String[] args) {
        int floatBits = Integer.parseUnsignedInt("40400000", 16);
        long doubleBits = Long.parseUnsignedLong(
                "4008000000000000", 16);

        System.out.println("float: "
                + Float.intBitsToFloat(floatBits));
        System.out.println("double: "
                + Double.longBitsToDouble(doubleBits));

        int negativeInfBits =
                Integer.parseUnsignedInt("FF800000", 16);
        System.out.println("negative infinity: "
                + Float.intBitsToFloat(negativeInfBits));

        System.out.printf("roundtrip float: %08X%n",
                Float.floatToRawIntBits(
                        Float.intBitsToFloat(floatBits)));
        System.out.printf("roundtrip double: %016X%n",
                Double.doubleToRawLongBits(
                        Double.longBitsToDouble(doubleBits)));
    }
}
```

Run:

```bash
javac ParseFloatingBitsDemo.java
java ParseFloatingBitsDemo
```

Output:

```text
float: 3.0
double: 3.0
negative infinity: -Infinity
roundtrip float: 40400000
roundtrip double: 4008000000000000
```

## 9. Byte Order: When Bit Patterns Reside in Files or Network Packets

`Float.intBitsToFloat` and `Double.longBitsToDouble` accept **an already-assembled `int`/`long`**, without reading bytes or deciding byte order. When bit patterns arrive as 4 or 8 bytes, you must assemble them according to **endianness**:

- **Big-endian**: most-significant byte comes first. Pattern `0x3F800000` has bytes `3F 80 00 00`.
- **Little-endian**: least-significant byte comes first. Pattern `0x3F800000` has bytes `00 00 80 3F`.

Java NIO `ByteBuffer` supports `ByteOrder.BIG_ENDIAN` and `ByteOrder.LITTLE_ENDIAN`. When calling `getFloat()`/`getDouble()`, the library reads bytes in the configured order and interprets them as floating-point.

Runnable example, file `FloatingByteOrderDemo.java`:

```java
import java.nio.ByteBuffer;
import java.nio.ByteOrder;

public class FloatingByteOrderDemo {
    public static void main(String[] args) {
        byte[] bigEndian = {
                0x3F, (byte) 0x80, 0x00, 0x00
        };
        byte[] littleEndian = {
                0x00, 0x00, (byte) 0x80, 0x3F
        };

        float a = ByteBuffer.wrap(bigEndian)
                .order(ByteOrder.BIG_ENDIAN)
                .getFloat();
        float b = ByteBuffer.wrap(littleEndian)
                .order(ByteOrder.LITTLE_ENDIAN)
                .getFloat();

        System.out.println("big endian: " + a);
        System.out.println("little endian: " + b);
        System.out.println("same value: " + (a == b));
    }
}
```

Compile and run:

```bash
javac FloatingByteOrderDemo.java
java FloatingByteOrderDemo
```

Output:

```text
big endian: 1.0
little endian: 1.0
same value: true
```

Configuring the wrong byte order causes the exact same four bytes to produce a drastically different value without raising an error. For `double`, 8 bytes and the corresponding byte order are needed. Additionally, check remaining byte count, packet structure, and format version, because `getFloat()`/`getDouble()` does not automatically know whether you are reading at the right offset.

## 10. Manually Extracting the Three Bit Fields for Inspection

When analyzing why a bit pattern produces a particular value, you can use logical right shift `>>>` and bitwise AND `&` to isolate sign, exponent, and fraction.

### 32-Bit Float

```java
int bits = 0x4040_0000;

int sign = (bits >>> 31) & 1;
int exponent = (bits >>> 23) & 0xFF;
int fraction = bits & 0x7F_FFFF;

// sign=0, exponent=128, fraction=0x400000
```

### 64-Bit Double

```java
long bits = 0x4008_0000_0000_0000L;

long sign = (bits >>> 63) & 1L;
long exponent = (bits >>> 52) & 0x7FFL;
long fraction = bits & 0x000F_FFFF_FFFF_FFFFL;

// sign=0, exponent=1024, fraction=0x8000000000000
```

These are **illustrative snippets** that must be placed inside a method or Java program to run. They are useful when debugging representation, yet in normal code prefer `Float.intBitsToFloat`/`Double.longBitsToDouble` because those APIs handle subnormals and special values properly.

**Common pitfall when computing the formula manually:** subnormals lack the implicit 1 bit, their exponent is interpreted differently from normals, and all patterns with all-1s `E` require dedicated Infinity/NaN handling. Blindly applying the normal formula to every pattern yields wrong results.

## 11. Common Confusions and Errors

| Symptom | Cause | Solution |
|---|---|---|
| `(float) bits` does not produce the IEEE 754 value | Cast converts the numeric value, not reinterpret bits | Use `Float.intBitsToFloat(bits)` |
| `(double) bits` does not decode the 64-bit pattern | Cast `long → double` is a numeric conversion | Use `Double.longBitsToDouble(bits)` |
| Pattern with sign bit 1 displays as negative `int/long` | Integer primitives are signed, though the bit pattern is intact | Keep the bits and use the IEEE 754 decoding API |
| Parsing `"FF800000"` with `parseInt` fails | Exceeds positive signed `int` range | Use `parseUnsignedInt(..., 16)` |
| `parseUnsignedInt("0x...",16)` throws an error | Parse API does not accept `0x` literal prefix | Strip the prefix after validation |
| `+0.0 == -0.0` yet bits differ | IEEE 754 has two signed zeros | Compare patterns via `floatToRawIntBits` if exact bits matter |
| NaN round-trip loses payload | Non-Raw API canonicalizes NaN; signaling NaN may be quieted | Keep raw `int/long` pattern if bit-perfect preservation is required |
| Decoding bytes produces wrong value | Wrong endianness, offset, or width | Check protocol, `ByteOrder`, and data length |
| Thinking `float` is 64-bit | `float` uses 32 bits, `double` uses 64 bits | Choose the matching API and width |
| Decoding Infinity bits like a normal number | All-1s `E` follows special rules | Handle Infinity/NaN before the normal formula |
| Result loses precision even with exact bits | Binary32/binary64 represent only finite precision | Keep the source format or choose an appropriate representation |

## 12. Validating Values After Reconstruction

If a bit pattern comes from external data, you may **recover the exact bits** yet obtain NaN or Infinity disallowed by business rules. Validate after decoding:

```java
static float requireFiniteFloat(int bits) {
    float value = Float.intBitsToFloat(bits);
    if (!Float.isFinite(value)) {
        throw new IllegalArgumentException("non-finite float");
    }
    return value;
}
```

This is an **illustrative method** to place in a Java class for use. Analogously, use `Double.isFinite(Double.longBitsToDouble(bits))` for `double`.

`isFinite` accepts subnormals and ±0.0; it only rejects NaN and ±Infinity. If business logic prohibits additional cases (such as negative numbers, subnormals, or values too large/small for the application), enforce those specific constraints as well.

When the requirement is checking **raw** data without losing NaN payloads, inspect the bit structure directly on `int/long` before converting to `float/double`. For example, check for an all-1s exponent and nonzero fraction to detect NaN on the raw pattern; this avoids depending on the payload surviving floating-point operations.

## 13. Self-Check Exercises

**Q1.** What does `Float.intBitsToFloat(0x3F800000)` equal?  
**Answer:** 1.0f, because that is the binary32 pattern for 1.

**Q2.** Does `(float) 0x3F800000` equal `Float.intBitsToFloat(0x3F800000)`?  
**Answer:** No. The cast converts the **integer** 1_065_353_216 to `float`; the method reinterprets **32 bits** into 1.0f.

**Q3.** What does `Double.longBitsToDouble(0x4008000000000000L)` equal?  
**Answer:** 3.0.

**Q4.** What do `0x7F800000` and `0xFF800000` represent when converted with `Float.intBitsToFloat`?  
**Answer:** +Infinity and -Infinity.

**Q5.** Which `float` pattern is `0x00000001`?  
**Answer:** The smallest positive subnormal, approximately 1.4E-45.

**Q6.** Are `+0.0f` and `-0.0f` equal under `==`? Are their bit patterns identical?  
**Answer:** `==` is true, yet their bits differ: `0x00000000` and `0x80000000`, respectively.

**Q7.** Why is `Float.floatToIntBits` insufficient for accurately storing an arbitrary NaN payload?  
**Answer:** Because that method canonicalizes all NaNs to a canonical NaN pattern. To preserve payloads, work with raw data and note that signaling NaNs can be quieted.

**Q8.** How should the hex string `"FF800000"` be parsed to recover `float` -Infinity?  
**Answer:** `int bits = Integer.parseUnsignedInt("FF800000", 16); float value = Float.intBitsToFloat(bits);`.

**Q9.** If a file contains bytes `00 00 80 3F` representing 1.0f, which byte order is that?  
**Answer:** Little-endian. Use `ByteBuffer.order(ByteOrder.LITTLE_ENDIAN)` when reading.

**Q10.** Why can't the normal-number formula be used for a bit pattern with an all-1s exponent?  
**Answer:** An all-1s exponent is reserved for Infinity (zero fraction) and NaN (nonzero fraction), not finite normal numbers.

**Q11.** To retrieve the raw bit pattern from `double value`, what should you use?  
**Answer:** `Double.doubleToRawLongBits(value)`. To canonicalize all NaNs to a single pattern, use `Double.doubleToLongBits(value)`.

**Q12.** If the goal is verifying that a bit pattern transmitted over a network stays 100% intact including signaling NaNs, should you pass it through `float` first before comparing?  
**Answer:** No. Keep and compare the original bytes or `int/long` directly, because in some environments a signaling NaN can be quieted when passed through a floating-point value.

## 14. Key Takeaways

- **`Float.intBitsToFloat(int)`** interprets 32 bits as binary32; **`Double.longBitsToDouble(long)`** interprets 64 bits as binary64.
- **Casting `(float)`/`(double)` converts a numeric value**, unlike reinterpreting a bit pattern.
- IEEE 754 patterns contain **sign, exponent, fraction**; distinguish normal, subnormal, ±0.0, ±Infinity, and NaN values.
- For data requiring **all bits** preserved, store raw patterns in `int/long` or bytes; watch out for NaN canonicalization or quieting.
- When reading bytes from files/networks, **endianness and width** must be right before calling the APIs.
- For external inputs, reconstructing a value from a bit pattern is one technical step; **checking finiteness and domain bounds** is a separate step.

Official documentation: [Float.intBitsToFloat — Java API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Float.html#intBitsToFloat(int)) and [Double.longBitsToDouble — Java API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Double.html#longBitsToDouble(long)).