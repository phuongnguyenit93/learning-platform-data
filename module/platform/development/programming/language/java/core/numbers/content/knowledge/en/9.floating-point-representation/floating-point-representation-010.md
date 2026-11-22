# `floatToIntBits`, `doubleToLongBits`, and `raw` Variants in Java

`Float.floatToIntBits`, `Float.floatToRawIntBits`, `Double.doubleToLongBits`, and `Double.doubleToRawLongBits` let you **inspect the bit pattern representing a floating-point value** in Java. This is an operation on the **IEEE 754 encoding**, not an arithmetic conversion of a number to an integer. The difference between the standard and `raw` variants is especially important for **NaN and NaN payloads**.

Example with `float`:

```java
float x = 1.0f;

int bits = Float.floatToIntBits(x);  // 0x3F800000 (1065353216)
int number = (int) x;               // 1: value conversion via cast
```

Both expressions return `int`, yet **they do not have the same meaning**: `bits` holds the 32-bit pattern of `1.0f`; `number` is the arithmetic integer part of the value `1.0f`. To understand and use these four APIs accurately, you must distinguish bit layout, canonicalized NaN, `raw`, bit-pattern reconstruction, and the limits of storing/transmitting data.

## 1. The Four Primary APIs and Two Reverse APIs

| API | Parameter | Result | NaN Handling |
| --- | --- | --- | --- |
| `Float.floatToIntBits(float)` | `float`, 32-bit | `int` containing 32-bit pattern | **Canonicalizes all NaNs** to `0x7FC00000` |
| `Float.floatToRawIntBits(float)` | `float`, 32-bit | `int` containing 32-bit pattern | Returns **raw bit pattern** of the currently represented value |
| `Double.doubleToLongBits(double)` | `double`, 64-bit | `long` containing 64-bit pattern | **Canonicalizes all NaNs** to `0x7FF8000000000000L` |
| `Double.doubleToRawLongBits(double)` | `double`, 64-bit | `long` containing 64-bit pattern | Returns **raw bit pattern** of the currently represented value |

The two corresponding reverse APIs:

- `Float.intBitsToFloat(int bits)`: interprets **the given 32 bits** as a `float` value.
- `Double.longBitsToDouble(long bits)`: interprets **the given 64 bits** as a `double` value.

They are not arithmetic conversions from `int` to `float` or `long` to `double`:

```java
float arithmetic = (float) 0x3F800000;         // Converts large integer to float
float decoded = Float.intBitsToFloat(0x3F800000); // 1.0f

double arithmetic2 = (double) 0x3FF0000000000000L;
double decoded2 = Double.longBitsToDouble(0x3FF0000000000000L); // 1.0
```

With `intBitsToFloat`/`longBitsToDouble`, the **same bit sequence** is interpreted in floating-point format; no division, multiplication, or integer-to-real rounding is performed as in an ordinary cast.

## 2. IEEE 754 Layout of `float` and `double`

Java uses IEEE 754 binary floating-point formats for `float` and `double`. The representation consists of a **sign bit, exponent field, and fraction (significand) field**:

| Component | `float` (binary32) | `double` (binary64) |
| --- | ---: | ---: |
| Total bits | 32 | 64 |
| Sign bit | 1 | 1 |
| Exponent bits | 8 | 11 |
| Fraction bits | 23 | 52 |
| Exponent bias | 127 | 1023 |

Illustration of bit positions, from left to right (most-significant to least-significant bit):

```text
float  (32 bits): S EEEEEEEE FFFFFFFFFFFFFFFFFFFFFFF
                  1    8               23

double (64 bits): S EEEEEEEEEEE FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF
                  1      11                         52
```

- **Sign (`S`):** `0` positive, `1` negative.
- **Exponent:** for finite normal values, the exponent stores a biased exponent; when the exponent is all `1` bits, the pattern denotes infinity or NaN.
- **Fraction:** the fractional significand bits. For normal values with an implicit leading bit, effective precision is 24 bits for `float` and 53 bits for `double`. For subnormals, the significand rule differs (no implicit leading 1 bit).

For example, `float 1.0f` has sign 0, stored exponent 127, and fraction 0. Its full bit pattern is `0x3F800000`. `double 1.0` has pattern `0x3FF0000000000000L`.

Typical patterns:

| Value | `float` Bits | `double` Bits |
| --- | --- | --- |
| `+0.0` | `0x00000000` | `0x0000000000000000` |
| `-0.0` | `0x80000000` | `0x8000000000000000` |
| `+1.0` | `0x3F800000` | `0x3FF0000000000000` |
| `+Infinity` | `0x7F800000` | `0x7FF0000000000000` |
| `-Infinity` | `0xFF800000` | `0xFFF0000000000000` |
| NaN **canonicalized by standard API** | `0x7FC00000` | `0x7FF8000000000000` |

These are hex codes of bit patterns, **not** Java literals of type `float`/`double`. Storing `0x3F800000` in an `int` and casting to `float` produces a large value around one billion, not `1.0f`; to reinterpret the bits, use `Float.intBitsToFloat`.

## 3. How Do `floatToIntBits` and `doubleToLongBits` Work?

`Float.floatToIntBits` and `Double.doubleToLongBits` convert a value into an integer of **the same bit width**:

```java
int floatBits = Float.floatToIntBits(1.0f);    // 0x3F800000
long doubleBits = Double.doubleToLongBits(1.0); // 0x3FF0000000000000L
```

They preserve the bits of **non-NaN** values, including:

- `+0.0` and `-0.0`: compare equal numerically, yet have different sign bits so their bit results differ.
- `+Infinity` and `-Infinity`: exponent all 1s, fraction all 0s, different sign.
- Normal and subnormal finite numbers: their encodings are returned in `int`/`long`.
- Negative numbers: the highest bit is 1; because `int` and `long` are signed, the result when **printed in decimal can be a negative number**. This does not change the bit sequence.

**Specifically for NaN**, the standard APIs return a single canonical pattern: `Float.floatToIntBits(...)` returns `0x7FC00000` and `Double.doubleToLongBits(...)` returns `0x7FF8000000000000L` for every NaN. Thus, if multiple NaNs carry different payloads, using the standard API will **not preserve payload differences**.

The benefit of canonicalization is providing a **deterministic** representation when comparing or hashing based on NaN bits under wrapper semantics. This does not mean primitive `==` comparisons between NaNs become true; Java still follows the rule that `Double.NaN == Double.NaN` is `false`.

## 4. How Do the `raw` Variants Differ from the Standard Ones?

`Float.floatToRawIntBits` and `Double.doubleToRawLongBits` return the bit pattern of the current value **without canonicalizing all NaNs to one canonical pattern**. With NaNs carrying a payload, the difference is observable:

```java
float nanWithPayload = Float.intBitsToFloat(0x7FC01234);
int raw = Float.floatToRawIntBits(nanWithPayload);    // 0x7FC01234 in this example
int normal = Float.floatToIntBits(nanWithPayload);    // 0x7FC00000

double nan64 = Double.longBitsToDouble(0x7FF8000000001234L);
long raw64 = Double.doubleToRawLongBits(nan64);       // 0x7FF8000000001234L in this example
long normal64 = Double.doubleToLongBits(nan64);      // 0x7FF8000000000000L
```

The NaN payload resides in the fraction field when the exponent is all 1s and the fraction is nonzero. Floating-point operations can generate or propagate NaNs; some systems use the payload to encode status information. However, **you should not rely on NaN payloads as a dependable data channel across every execution path**.

**Important limitation with signaling NaN:** On some platforms, passing a *signaling NaN* bit pattern through `Float.intBitsToFloat` or `Double.longBitsToDouble` into a floating-point value can cause it to be **quieted** (*quieting*), altering certain bits. Therefore, you cannot promise that every raw NaN pattern will round-trip bit-perfectly across all operations, parameters, optimizations, or JVMs. In the test example, `0x7FC01234` and `0x7FF8000000001234L` are **quiet NaNs** with payloads; the `raw` API preserves the exact pattern in the illustrated run. If the requirement is to preserve **every input NaN bit pattern** in files/protocols, store and transport them as `int`/`long` or byte arrays, and only interpret them as `float`/`double` when arithmetic computation is actually needed.

For **non-NaN** values, the results of the `raw` API and standard API are identical.

## 5. Why Are `+0.0` and `-0.0` Equal Yet Have Different Bit Codes?

IEEE 754 has **two bit patterns for zero**:

```java
double plus = 0.0;
double minus = -0.0;

boolean numericEqual = (plus == minus);  // true
boolean bitEqual = Double.doubleToLongBits(plus)
                 == Double.doubleToLongBits(minus); // false
```

For `double`, `+0.0` is `0x0000000000000000L`, and `-0.0` is `0x8000000000000000L`. For `float`, they are `0x00000000` and `0x80000000`. The sign bit makes them distinct even though the `==` value comparison evaluates to equal.

This difference sometimes carries mathematical significance: `1.0 / +0.0` produces `+Infinity`, while `1.0 / -0.0` produces `-Infinity`. Bit APIs are helpful when verifying zero's sign in calculations or when decoding binary data.

**Do not mechanically use bit comparison to replace all floating-point comparisons.** Numeric value comparison, `Float.compare`/`Double.compare` comparison, and raw bit comparison are three distinct requirements. For instance, primitive `NaN == NaN` is false, whereas wrapper `Double.equals` is designed around canonical bit comparison; signed zeros are also distinguished by the wrapper. Choose the rule matching your business domain.

## 6. Reconstructing from Bits: `intBitsToFloat` and `longBitsToDouble`

The two “inverse” methods take **integer bits** and produce a floating-point value:

```java
int bits32 = 0x3F800000;
float restored32 = Float.intBitsToFloat(bits32); // 1.0f

long bits64 = 0x3FF0000000000000L;
double restored64 = Double.longBitsToDouble(bits64); // 1.0
```

For **non-NaN** `float`/`double` values, an important bit round-trip relationship holds:

```java
int bits = Float.floatToIntBits(3.5f);
float again = Float.intBitsToFloat(bits); // 3.5f

long longBits = Double.doubleToLongBits(-0.0);
double again64 = Double.longBitsToDouble(longBits); // -0.0
```

If you start from an **arbitrary NaN bit pattern**, going through the standard API canonicalizes the NaN, so the *bit round-trip* can differ. Even with `raw`, the caveats regarding signaling NaNs and intermediate operations still apply.

You should distinguish a **value round-trip** from a **bit-pattern round-trip**:

- For finite numbers, recreating the exact value normally coincides with preserving the bit pattern.
- For `+0.0` and `-0.0`, they compare equal numerically yet have different bits; determine whether preserving zero's sign is required.
- For NaN, ending up with “still a NaN” does not prove the payload or all original bits were preserved.

## 7. Printing Bits Properly: Hex and Unsigned Shifts

Because `Float.floatToIntBits` returns a signed `int`, patterns with the highest bit equal to 1 can print as negative integers. For example, `Float.floatToIntBits(-0.0f)` is `0x80000000`, which corresponds to `Integer.MIN_VALUE` if printed in decimal.

Printing in hex displays the exact width cleanly:

```java
int bits32 = Float.floatToIntBits(-0.0f);
System.out.printf("0x%08X%n", bits32);   // 0x80000000

long bits64 = Double.doubleToLongBits(-0.0);
System.out.printf("0x%016X%n", bits64);  // 0x8000000000000000
```

To extract `float` fields:

```java
int bits = Float.floatToRawIntBits(1.0f);
int sign = (bits >>> 31) & 1;
int exponent = (bits >>> 23) & 0xFF;
int fraction = bits & 0x7FFFFF;
// sign = 0, exponent = 127, fraction = 0
```

For `double`:

```java
long bits = Double.doubleToRawLongBits(1.0);
long sign = (bits >>> 63) & 1L;
long exponent = (bits >>> 52) & 0x7FFL;
long fraction = bits & 0xFFFFFFFFFFFFFL;
// sign = 0, exponent = 1023, fraction = 0
```

Use `>>>` (**unsigned** right shift, filling 0 bits on the left) when dissecting bit fields, especially for patterns with sign bit 1. Use proper `long` literals (`1L`, `0x7FFL`) when manipulating 64-bit values.

Do not confuse **the bits of a floating-point value** with its decimal character string. The number `0.1` has no exact finite binary representation; the API returns the actual `double` bit pattern, not character codes for `"0"`, `"."`, `"1"`.

## 8. Complete Java 17+ Program for Canonical and Raw

Create the file `FloatingBitsDemo.java`:

```java
public class FloatingBitsDemo {
    static String fhex(int bits) {
        return String.format("0x%08X", bits);
    }

    static String dhex(long bits) {
        return String.format("0x%016X", bits);
    }

    public static void main(String[] args) {
        float f = 1.0f;
        System.out.println("float 1.0 bits: " + fhex(Float.floatToIntBits(f)));
        System.out.println("float -0.0 bits: " + fhex(Float.floatToIntBits(-0.0f)));
        System.out.println("float +0.0 bits: " + fhex(Float.floatToIntBits(0.0f)));
        System.out.println("int cast of 1.0f: " + (int) f);
        System.out.println("float NaN canonical: " + fhex(Float.floatToIntBits(Float.NaN)));

        float payloadFloat = Float.intBitsToFloat(0x7FC01234);
        System.out.println("float NaN raw: " + fhex(Float.floatToRawIntBits(payloadFloat)));
        System.out.println("float NaN normalized: " + fhex(Float.floatToIntBits(payloadFloat)));
        System.out.println("float restored 1.0: " + Float.intBitsToFloat(0x3F800000));
        System.out.println("float raw isNaN: " + Float.isNaN(payloadFloat));

        double d = 1.0;
        System.out.println("double 1.0 bits: " + dhex(Double.doubleToLongBits(d)));
        System.out.println("double -0.0 bits: " + dhex(Double.doubleToLongBits(-0.0)));
        System.out.println("double +0.0 bits: " + dhex(Double.doubleToLongBits(0.0)));
        System.out.println("double NaN canonical: " + dhex(Double.doubleToLongBits(Double.NaN)));

        double payloadDouble = Double.longBitsToDouble(0x7FF8000000001234L);
        System.out.println("double NaN raw: " + dhex(Double.doubleToRawLongBits(payloadDouble)));
        System.out.println("double NaN normalized: " + dhex(Double.doubleToLongBits(payloadDouble)));
        System.out.println("double restored 1.0: "
            + Double.longBitsToDouble(0x3FF0000000000000L));
        System.out.println("+0.0 == -0.0: " + (0.0 == -0.0));
        System.out.println("bits equal? "
            + (Double.doubleToLongBits(0.0) == Double.doubleToLongBits(-0.0)));
    }
}
```

Compile and run:

```bash
javac FloatingBitsDemo.java
java FloatingBitsDemo
```

Program stdout (using a quiet NaN payload example):

```text
float 1.0 bits: 0x3F800000
float -0.0 bits: 0x80000000
float +0.0 bits: 0x00000000
int cast of 1.0f: 1
float NaN canonical: 0x7FC00000
float NaN raw: 0x7FC01234
float NaN normalized: 0x7FC00000
float restored 1.0: 1.0
float raw isNaN: true
double 1.0 bits: 0x3FF0000000000000
double -0.0 bits: 0x8000000000000000
double +0.0 bits: 0x0000000000000000
double NaN canonical: 0x7FF8000000000000
double NaN raw: 0x7FF8000000001234
double NaN normalized: 0x7FF8000000000000
double restored 1.0: 1.0
+0.0 == -0.0: true
bits equal? false
```

**Explanation:** The `1.0` lines verify known IEEE 754 codes; `int cast` proves bit conversion is not numeric casting; the `-0.0` lines compare sign bits; the `NaN raw` and `NaN normalized` pairs show payload preservation vs. canonicalization; `intBitsToFloat`/`longBitsToDouble` restore `1.0`. The opposite signs of ±0 do not flip numeric `==` from true to false, yet their `long` patterns differ.

## 9. When Writing Bits to File/Network: Byte Order Is a Separate Step

`floatToIntBits`/`doubleToLongBits` returns **an `int`/`long` value containing the bit pattern**, without turning it into a byte array or deciding the protocol's byte order. When serializing, determine:

1. Do you want to **canonicalize all NaNs** or preserve raw payloads?
2. Does the wire format require **big-endian** or **little-endian**?
3. Will the receiver decode with the exact same 32/64-bit width and NaN rules?
4. Can the data contain `-0.0`, Infinity, or subnormals, and are those values permitted by the data contract?

Example using `ByteBuffer` to produce big-endian or little-endian representations of a **32-bit pattern**:

```java
int bits = Float.floatToIntBits(1.0f); // 0x3F800000

byte[] bigEndian = java.nio.ByteBuffer.allocate(4)
    .order(java.nio.ByteOrder.BIG_ENDIAN)
    .putInt(bits)
    .array(); // 3F 80 00 00

byte[] littleEndian = java.nio.ByteBuffer.allocate(4)
    .order(java.nio.ByteOrder.LITTLE_ENDIAN)
    .putInt(bits)
    .array(); // 00 00 80 3F
```

This is an **illustrative snippet** inside a method. Specify byte order according to the protocol rather than assuming it from CPU architecture. `ByteBuffer.putFloat`/`getFloat` and `putDouble`/`getDouble` also exist for floating-point data; understand their canonical NaN/representation rules if special payload preservation is required.

If the goal is to preserve **every raw byte** of an incoming message, it is best to keep the original byte array or `int`/`long` patterns directly. Converting them into floating-point values, performing arithmetic, and converting back can alter NaN payloads or change the values themselves during calculation.

## 10. What Are These APIs Used For?

| Task | Suitable Approach | Notes |
| --- | --- | --- |
| Debugging sign, exponent, fraction | `floatToRawIntBits`/`doubleToRawLongBits` + bit masks | Remember to print hex and shift with `>>>` |
| Checking `+0.0` vs `-0.0` | `floatToIntBits`/`doubleToLongBits` | Numeric `==` yields true |
| Reconstructing `float`/`double` from 32/64-bit pattern | `intBitsToFloat`/`longBitsToDouble` | This is bit interpretation, not numeric casting |
| Hashing/comparing by canonical NaN | `floatToIntBits`/`doubleToLongBits` | Compatible with NaN canonicalization |
| Inspecting existing NaN payload | `raw` variants | Does not promise every signaling payload survives all operations |
| Storing/transmitting exact bit patterns | `int`/`long` or `byte[]`, explicit byte order | Avoid routing through floating-point arithmetic if bits must stay exact |
| Converting floating-point value to integer | `(int) value`, `(long) value`, or checked conversion | Do not use `floatToIntBits`/`doubleToLongBits` as a substitute |

Distinguishing **numeric representation** from **mathematical value** also helps answer questions such as “why do two numbers both equal to 0 have different hashes or bit codes?” or “why is a NaN read back still NaN yet its payload changed after storage?”.

## 11. Common Mistakes

1. **“`Float.floatToIntBits(x)` is equivalent to `(int) x`.”** False: the method returns the 32-bit IEEE 754 pattern; a cast converts the mathematical value with its own truncation/range rules.
2. **“`Double.doubleToLongBits(x)` always preserves all NaN payloads.”** False: it canonicalizes all NaNs.
3. **“The `raw` variant guarantees bit-perfect round-trips for every signaling NaN across all JVMs.”** False: converting a signaling NaN pattern into a `float`/`double` value can quiet the NaN.
4. **“`+0.0` and `-0.0` have the same bits because `==` returns true.”** False: their sign bits differ.
5. **“Hex `0x80000000` returns a negative `int` so it must have overflowed.”** False: it is a 32-bit pattern, and `int` interprets the top bit as the sign bit.
6. **“`Float.intBitsToFloat(0x3F800000)` is the same as casting `(float) 0x3F800000`.”** False: one decodes IEEE 754 into `1.0f`, while the other converts a large integer to a floating-point number.
7. **“`raw` can recover the NaN payload after `floatToIntBits` has canonicalized it.”** False: payload bits are discarded during canonicalization.
8. **“Converting to `int`/`long` determines byte order automatically.”** False: byte order only arises when serializing to bytes.
9. **“Any NaN pattern can be treated like a finite real number.”** False: NaN does not compare or behave like an ordinary finite value.
10. **“Use bit equality instead of arithmetic comparison everywhere.”** False: bit equality intentionally distinguishes ±0 and handles NaN differently from primitive `==`.

## 12. Self-Check

- What does `Float.floatToIntBits(1.0f)` return? **The pattern `0x3F800000`**, not `1`.
- What does `(int) 1.0f` return? **`1`**, because it is a numeric conversion.
- Are `Float.floatToIntBits(-0.0f)` and `Float.floatToIntBits(0.0f)` equal? **No**, because their sign bits differ.
- Must `Float.floatToIntBits(Float.intBitsToFloat(0x7FC01234))` return `0x7FC01234`? **No**. Because it is NaN, the standard variant returns canonical `0x7FC00000`.
- Which API inspects a NaN payload currently present in a value? **`Float.floatToRawIntBits` or `Double.doubleToRawLongBits`**.
- What does `Double.longBitsToDouble(0x3FF0000000000000L)` yield? **`1.0`**.
- If a NaN bit pattern must be transmitted **with 100% bit exactness** between two systems, what should you do? **Keep `int`/`long` or `byte[]` intact and specify byte order**, avoiding operations that could canonicalize or quiet the NaN.

**Remember:** `floatToIntBits` and `doubleToLongBits` read IEEE 754 patterns while **canonicalizing NaN**; the `raw` variants inspect the currently held NaN bit pattern **without actively canonicalizing**. `intBitsToFloat` and `longBitsToDouble` decode in reverse. These are **bit conversions**, completely distinct from `(int)`/`(long)` or arithmetic casts; to preserve payloads and binary protocols, control where bits are stored, how they are serialized, and the limitations when handling NaN.