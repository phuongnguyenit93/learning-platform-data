# BigInteger: Signed Two's Complement Byte Representation and Sign-Magnitude Constructors

In Java Core, `java.math.BigInteger` is an **arbitrary-precision signed integer** type. When converting between `BigInteger` and a `byte[]` array, it is essential to distinguish **two completely different decoding schemes**:

- **Signed two's complement**: `new BigInteger(byte[] val)` reads the byte array as *a signed integer*; the highest bit of the first byte is the **sign bit**.
- **Sign–magnitude**: `new BigInteger(int signum, byte[] magnitude)` takes a **separate sign** (`-1`, `0`, `1`) and treats *the entire byte array as an unsigned magnitude*.

The very same byte can produce two opposite results:

```java
byte[] input = {(byte) 0x80};

BigInteger signed = new BigInteger(input);     // -128
BigInteger unsigned = new BigInteger(1, input); // +128
```

**Why?** The 8-bit pattern `1000_0000` has value **-128** when interpreted as an 8-bit signed two's complement integer; the same pattern has value **128** when interpreted as an *unsigned magnitude* with a positive sign supplied externally.

This knowledge is critical when handling **cryptographic keys, binary protocols, hashes, variable-length integers, and serialization**. Missing even a single `00` sign-guard byte is enough to turn a large positive integer negative.

## 1. `BigInteger` Stores Integers, Not Fixed 8/16/32/64-Bit Widths

`BigInteger` stores an integer with a sign and a length proportional to its absolute value, unlike `byte`, `short`, `int`, or `long`, which have fixed widths. With string inputs:

```java
import java.math.BigInteger;

BigInteger p = new BigInteger("255");     // +255
BigInteger n = new BigInteger("-255");    // -255
BigInteger h = new BigInteger("ff", 16);  // +255
```

The declarations above are **code snippets** meant to be placed in an appropriate class/method, not a standalone runnable program. The ability to represent large numbers **does not mean all byte constructors treat data as unsigned**. Different constructors carry **different representation contracts**, even though all produce a `BigInteger`.

| Constructor/API | Meaning | Example value |
| --- | --- | --- |
| `new BigInteger(byte[] bytes)` | Big-endian bytes, **signed two's complement** | `[FF]` → -1 |
| `new BigInteger(1, byte[] magnitude)` | Big-endian bytes, **unsigned magnitude**, forced positive sign | `[FF]` → +255 |
| `new BigInteger(-1, byte[] magnitude)` | Unsigned magnitude, forced negative sign | `[FF]` → -255 |
| `new BigInteger("ff", 16)` | Parses base-16 digit string | +255 |
| `big.toByteArray()` | Big-endian byte array, **minimal signed two's complement** | +255 → `[00 FF]` |
| `big.signum()` | Returns sign of the **constructed value** | -255 → -1 |

`new BigInteger("ff",16)` and `new BigInteger(new byte[]{(byte)0xff})` **do not produce the same result**. The first reads hex digits as a positive value; the second reads a byte with its high bit set as a negative two's complement number.

## 2. Both Formats Put the Most Significant Byte First (Big-Endian)

`BigInteger`'s byte-array constructors use **big-endian**: the **most significant byte is at the start of the array**. For example, the array:

```text
Byte 0   Byte 1
0x01     0x00
```

represents the magnitude `0x0100 = 256`, not `0x0001 = 1`. This byte-ordering rule applies to both **signed two's complement** and **sign–magnitude**; the difference lies in **how the sign bit is interpreted**, not in reversing bytes.

For little-endian binary data (for instance, a custom file format or protocol), **never pass** a little-endian array directly into `BigInteger` expecting the right result. You must reverse byte positions to big-endian per the format contract, while still choosing the proper signed or unsigned interpretation.

Note: Big-endian refers to the **positions of significant bytes**, not how hex characters are printed on screen. Nor does it depend on whether the host CPU runs little-endian or big-endian: the constructor specifies the byte-array order.

## 3. How Signed Two's Complement Works

For an array of `n` bytes, the width is `w = 8n` bits. In **two's complement**:

- If the highest bit is 0, the value is non-negative and read as an ordinary binary integer.
- If the highest bit is 1, the value is **negative**, equal to the unsigned value of the entire bit pattern **minus `2^w`**.

Formula for a fixed-width bit pattern:

```text
U = unsigned value of all w bits

signedValue =
    U            if highest bit = 0
    U - 2^w      if highest bit = 1
```

Single-byte examples (`w=8`, `2^8=256`):

| Byte hex | Binary bits | Unsigned | Signed two's complement |
| --- | --- | ---: | ---: |
| `00` | `0000_0000` | 0 | 0 |
| `01` | `0000_0001` | 1 | 1 |
| `7F` | `0111_1111` | 127 | 127 |
| `80` | `1000_0000` | 128 | **-128** |
| `FF` | `1111_1111` | 255 | **-1** |

With two bytes `FF 7F`, the unsigned value is `65407`; `65407 - 65536 = -129`. Thus:

```java
new BigInteger(new byte[]{(byte) 0xff, 0x7f}); // -129
```

This is a **16-bit signed two's complement** array. Knowing just the first bit and the byte count suffices to determine the array's signed range: one byte `FF` gives -1, while two bytes `00 FF` give +255.

## 4. Constructor `BigInteger(byte[] val)`: Data Is Interpreted as Signed

Signature:

```java
public BigInteger(byte[] val)
```

Accepts a **big-endian signed two's complement** byte array. Examples:

```java
BigInteger a = new BigInteger(new byte[]{0x7f});          // +127
BigInteger b = new BigInteger(new byte[]{(byte) 0x80});   // -128
BigInteger c = new BigInteger(new byte[]{(byte) 0xff});   // -1
BigInteger d = new BigInteger(new byte[]{0, (byte) 0x80}); // +128
```

The two bytes `00 80` differ from array `80`: the prefix `00` makes the **sign bit of the entire array equal 0**, ensuring a positive number. The subsequent byte `80` still contributes 128 to the magnitude.

If `val` is empty (`new byte[0]`), the constructor **throws `NumberFormatException`**: signed two's complement cannot represent a value from zero input bytes under this contract. To construct 0, use `BigInteger.ZERO` or an array containing a single `00` byte.

Java `byte` values themselves are signed when read as standalone integers (`(byte)0xff == -1`). However, when creating a `BigInteger` from an array, Java concatenates the **8-bit patterns** in order and then interprets **the sign of the whole number**. Do not add individual signed `byte` values to simulate a two's complement array result.

## 5. Constructor `BigInteger(int signum, byte[] magnitude)`: Separate Sign, Unsigned Magnitude

Signature:

```java
public BigInteger(int signum, byte[] magnitude)
```

Where:

- **`signum`** can only be `-1` (negative), `0` (zero), or `1` (positive).
- **`magnitude`** is a big-endian byte array holding an **unsigned magnitude**, even if the highest bit of the first byte is 1.
- The constructed value is mathematically **`signum × magnitudeValue`** (with consistency conditions for zero).

```java
byte[] bits = {(byte)0xff};

BigInteger positive = new BigInteger(1, bits);  // +255
BigInteger negative = new BigInteger(-1, bits); // -255
```

This is how you create a **positive** number from a byte array with the leading bit set **without needing to prepend a `00` byte** to the input.

```java
BigInteger p = new BigInteger(1, new byte[]{(byte)0x80}); // +128
BigInteger n = new BigInteger(-1, new byte[]{(byte)0x80}); // -128
```

**Warning:** `signum = -1` **does not mean** the `magnitude` array should also be in negative two's complement form. With magnitude `FF`, sign -1 produces **-255**, not -1. Input data must adhere to the agreed sign–magnitude format.

## 6. Zero and `signum` Consistency Rules

The value zero has magnitude 0, whether represented by `byte[]{0}`, a multi-byte `00` array, or even an empty magnitude array under the sign–magnitude overload.

| `signum` | Magnitude | Result |
| ---: | --- | --- |
| `0` | `[00]` | 0 |
| `0` | `[00, 00]` | 0 |
| `+1` | `[00]` or empty | 0 |
| `-1` | `[00]` | 0 |
| `0` | `[01]` | **`NumberFormatException`** |
| `2` or `-2` | Any magnitude | **`NumberFormatException`** |

Important rule: **you cannot specify sign 0 with a nonzero magnitude**; `new BigInteger(0,new byte[]{1})` is rejected. If the magnitude is actually 0 while signum is -1, the resulting `BigInteger` is still **normalized zero**, with no integer "negative zero".

```java
BigInteger zero = new BigInteger(-1, new byte[]{0, 0});
System.out.println(zero.signum()); // 0
```

This differs from floating-point `-0.0`: the integer `BigInteger` **does not have two differently signed zero values**. When using the sign–magnitude API, check that passing sign 0 is consistent with the magnitude to avoid unexpected exceptions.

Also distinguish: `new BigInteger(new byte[0])` **fails** because the signed constructor requires at least one byte; whereas `new BigInteger(1,new byte[0])` gives the value **0**, as shown in the QA program below.

## 7. Comparison Table from the Same Byte Array

| Byte array (hex) | `new BigInteger(bytes)` | `new BigInteger(1,bytes)` | `new BigInteger(-1,bytes)` |
| --- | ---: | ---: | ---: |
| `00` | 0 | 0 | 0 |
| `01` | 1 | 1 | -1 |
| `7F` | 127 | 127 | -127 |
| `80` | **-128** | **128** | -128 |
| `FF` | **-1** | **255** | **-255** |
| `00 80` | 128 | 128 | -128 |
| `FF 7F` | -129 | 65407 | -65407 |

The `FF 7F` row is an important example: under **16-bit signed** reading it is -129; under **magnitude** reading it is `0xFF7F = 65407`, and the external sign decides +65407 or -65407. The fact that the two constructors produce **the same negative result** for `80` and signum -1 is merely a coincidence of that specific value, not general equivalence.

If input comes from a network or protocol, you must know whether the field uses **signed two's complement** or **unsigned magnitude**. You cannot deduce the proper interpretation solely from a variable name `bytes`, the byte count, or the fact that they are printed as hex digits.

## 8. `BigInteger.toByteArray()`: Minimal Signed Two's Complement

To export a `BigInteger` back to bytes, use:

```java
byte[] encoded = bigInteger.toByteArray();
```

This API returns a **big-endian signed two's complement** array with **the minimum number of bytes needed** to hold both value and sign. It **does not** return a plain unsigned magnitude and **does not** preserve the byte count originally passed to the constructor.

Examples:

| BigInteger value | `HexFormat.of().formatHex(value.toByteArray())` | Explanation |
| ---: | --- | --- |
| 0 | `00` | Zero needs one `00` byte |
| +1 | `01` | Small positive number |
| +127 | `7f` | High bit = 0 |
| **+128** | **`0080`** | Adds `00` so it is not read as -128 |
| **+255** | **`00ff`** | Adds `00` to guard sign |
| -1 | `ff` | Single-byte two's complement |
| -128 | `80` | Valid negative value in one byte |
| **-129** | **`ff7f`** | Needs `ff` byte to keep negative sign |

`toByteArray` guarantees *minimal length*, so do not treat `value.toByteArray().length == 4` or 8 as an invariant just because the value is used in a 32/64-bit protocol.

Important example:

```java
BigInteger positive = new BigInteger(1, new byte[]{(byte)0xff});
byte[] encoded = positive.toByteArray();
// encoded has two bytes [00 FF], not one byte [FF].
```

If you pass `encoded` to `new BigInteger(encoded)`, you get +255 back accurately. If you arbitrarily strip `00` and pass it to the signed constructor, you get -1 again.

## 9. Why Is a Leading `00` Byte Needed for Positive Numbers?

In signed two's complement, the highest bit of the first byte **determines the sign**. Positive 128 has the binary pattern `1000_0000`; with only one byte, that bit pattern is **-128**. To keep the positive sign in signed format, prepend a `00` byte:

```text
Magnitude 128:              80
Signed two's complement: 00 80  => +128
Signed two's complement:    80  => -128

Magnitude 255:              FF
Signed two's complement: 00 FF  => +255
Signed two's complement:    FF  => -1
```

A leading `00` byte is not meaningless padding in signed encoding; it can be **the condition required to read the sign correctly**. However, when the data is actually **unsigned magnitude**, a sign-guard `00` byte may not be expected; hence the same array is encoded under two different contracts.

Do not think `0x80` "defaults to -128 in every context." It is a bit pattern; **its arithmetic meaning depends on the interpretation**. That interpretation must be chosen when constructing `BigInteger`.

## 10. Leading `FF` Bytes for Negative Numbers and Sign Extension

Two's complement has a **sign extension** rule: to increase width while preserving a negative value, pad with `FF` bytes on the left; for non-negative values, pad with `00`.

```text
-1 in 8 bits:          FF
-1 in 16 bits:      FF FF
-1 in 32 bits: FF FF FF FF

+255 in 16 bits:      00 FF
+255 in 32 bits: 00 00 00 FF
```

`BigInteger.toByteArray()` drops **redundant** sign-extension bytes while retaining the minimum bytes sufficient to express the sign. For instance, -1 is represented by one byte `FF`, not an infinite array of `FF` bytes. -129 needs two bytes `FF 7F`, because one signed byte cannot hold -129.

For a system expecting exactly 4 bytes for signed 32-bit, the array `FF` must be **extended to `FF FF FF FF`** to transmit -1. Conversely, if the protocol uses unsigned 32-bit, you generally need **zero-extension**; passing `FF FF FF FF` to the signed `BigInteger` constructor yields -1 instead of unsigned 4294967295.

## 11. `signum` in the Constructor Is Not Necessarily the Result's `signum()`

`new BigInteger(signum,magnitude)` accepts a **requested sign parameter**. After construction, `result.signum()` returns the sign of the **actual value**, always -1, 0, or 1.

Example:

```java
BigInteger zero = new BigInteger(-1, new byte[]{0});
System.out.println(zero.signum()); // 0

BigInteger negative = new BigInteger(-1, new byte[]{1});
System.out.println(negative.signum()); // -1
```

Do not set `signum` from a signed byte such as `(byte)0x80 == -128`, because the constructor accepts strictly -1, 0, 1; -128 is a **byte value**, not a valid `BigInteger` sign.

If you are converting data from a system with a separate `sign` field and a `magnitude` array, map `sign` to -1/0/1 per the format, check zero consistency, and then call the constructor. Do not use the leading bit of the magnitude array to guess the sign when the contract already specifies a separate sign.

## 12. Overloads with Offset and Length

Java 17 has overloads taking **a slice of an array**, avoiding mandatory copies with `Arrays.copyOfRange`:

```java
BigInteger signedPart =
        new BigInteger(byte[] val, int off, int len);

BigInteger magnitudePart =
        new BigInteger(int signum, byte[] magnitude, int off, int len);
```

The two lines above are **conceptual signatures**, not valid variable declaration syntax—they serve to list constructor forms.

Runnable snippet when placed inside a method:

```java
byte[] data = {(byte)0x7e, 0x00, (byte)0x80, 0x7f};

BigInteger signed = new BigInteger(data, 1, 2);
// Reads [00,80] as +128 (signed two's complement).

BigInteger magnitude = new BigInteger(1, data, 2, 1);
// Reads [80] as +128 (positive magnitude).
```

`off` is the **starting index**, and `len` is the **number of bytes to read**, not the ending index. If `off` and `len` exceed array bounds, the API throws an index/range exception. For the signed constructor, an empty slice is invalid because there are no bytes to represent a number; for the magnitude constructor, an empty magnitude can produce zero if the sign is valid.

Just like the principle at the beginning, both overloads still use **big-endian** within the selected slice. Passing a slice does not change signed or magnitude rules, so check the exact record field definitions.

## 13. How Does `BigInteger("ff",16)` Differ from `BigInteger(byte[]{FF})`?

A string of hex digits has **arithmetic semantics**, not a signed byte array:

```java
BigInteger byText = new BigInteger("ff", 16); // +255

byte[] oneByte = {(byte)0xff};
BigInteger bySigned = new BigInteger(oneByte); // -1
BigInteger byMagnitude = new BigInteger(1, oneByte); // +255
```

Because `"ff"` has no `-` sign, the string constructor interprets it as magnitude 255. With the signed array constructor, byte `FF` is -1. With sign–magnitude, sign 1 makes byte `FF` represent +255.

Specifically in systems storing hashes, if you convert a byte array to a **hex string** and call `new BigInteger(hex,16)`, the result will be **positive** (unless the string has a minus sign); if you call `new BigInteger(bytes)` directly, the result can be negative. This is a common reason why the exact same digest ends up with two different integer representations.

If the format is genuinely **unsigned bytes** rather than a signed integer, the clear-intent method is `new BigInteger(1,bytes)`. Even so, hashes/identifiers may need to **preserve exact byte length and leading zeros**, whereas `BigInteger` represents a **numeric value** and can normalize away zero padding upon re-serialization.

## 14. `BigInteger` Is a Numeric Value, Not a Byte Store Preserving Format

Suppose the input is three bytes:

```text
00 00 FF
```

If you call:

```java
BigInteger value =
        new BigInteger(1, new byte[]{0, 0, (byte)0xff});
// value = 255.
```

then `value.toByteArray()` returns **`00 FF`**, not `00 00 FF`. There is no way from the numeric value 255 alone to know how many `00` bytes padded the original input.

Therefore, if a protocol has **fixed 16/32-byte fields**, storing solely as a `BigInteger` is not enough for a *byte-for-byte* round-trip. You must store the **format length** or pad/truncate rules, and reconstruct the exact byte count when writing out. If the format uses 32-byte big-endian unsigned, you must **zero-pad**, not sign-extend with `FF`. If the format uses fixed-width signed two's complement, you must **sign-extend**.

Do not strip leading `00` bytes unconditionally: in signed arrays, that byte can be essential to distinguish +255 from -1. Strip it only when you are intentionally converting from signed representation to **unsigned magnitude** and the consumer expects that contract as well.

## 15. Be Careful When Converting via Primitive `byte`, `int`, `long`

Java `byte` is signed in the range -128..127. Even though a byte `FF` corresponds to 255 when viewed unsigned, a direct read:

```java
byte raw = (byte)0xff;
System.out.println(raw);                    // -1
System.out.println(Byte.toUnsignedInt(raw)); // 255
```

`Byte.toUnsignedInt` only converts **one byte** into a 0..255 value for inspection/processing; it does not turn `new BigInteger(byte[])` into an unsigned constructor.

In addition, `BigInteger.intValue()` and `longValue()` can **lose high-order bits** for large values. Example:

```java
BigInteger big = new BigInteger(1, new byte[]{
        0x01, 0x00, 0x00, 0x00, 0x00
}); // 2^32.
int lossy = big.intValue(); // 0 because only low 32 bits are kept.
```

If you need to convert to a primitive **without accepting data loss**, use `intValueExact()` or `longValueExact()` and handle `ArithmeticException` when out of range. Do not try to "fix" a negative number produced incorrectly by the signed constructor by casting to `long` or masking afterward: first verify whether **the byte interpretation itself matches the format**.

## 16. Fixed-Width Signed Encoding: You Must Check the Range Yourself

`BigInteger.toByteArray()` returns **minimal length**, and cannot on its own guarantee exactly 2, 4, 8, or 32 bytes. For a requirement of **w-byte signed two's complement**, the exact range is:

```text
min = -2^(8*w-1)
max =  2^(8*w-1)-1
```

For example, **one signed byte** holds only -128..127. +128 requires at least **two bytes `00 80`**. You must not truncate `00 80` to `80` and decode as signed, as that becomes -128.

A sample method (placed in a class importing `java.util.Arrays`, `java.math.BigInteger`) to write exactly **w signed bytes**:

```java
static byte[] toFixedSigned(BigInteger value, int width) {
    if (width <= 0 || width > Integer.MAX_VALUE / 8) {
        throw new IllegalArgumentException("invalid width");
    }
    int bits = width * 8;
    BigInteger bound = BigInteger.ONE.shiftLeft(bits - 1);
    if (value.compareTo(bound.negate()) < 0
            || value.compareTo(bound.subtract(BigInteger.ONE)) > 0) {
        throw new ArithmeticException("out of signed range");
    }
    byte[] minimal = value.toByteArray();
    byte[] result = new byte[width];
    Arrays.fill(result, value.signum() < 0 ? (byte) 0xff : (byte) 0x00);
    System.arraycopy(minimal, 0, result,
            width - minimal.length, minimal.length);
    return result;
}
```

Here, checking the range **first** ensures the `minimal` array is never longer than `width` in valid cases; the copy never truncates meaningful bytes. Examples:

```text
toFixedSigned(+128, 2) → 00 80
toFixedSigned(-1,   2) → FF FF
toFixedSigned(0,    2) → 00 00
toFixedSigned(+128, 1) → ArithmeticException
```

This is a **helper function snippet**, not called in the runnable program in the following section; expected examples can be turned into unit tests matching the protocol's fixed-width signed contract. For untrusted input, you should enforce a **reasonable length cap** in addition to rejecting `width <= 0` to avoid huge array allocations.

If the target format is **unsigned**, do not use this signed range check; unsigned `w` bytes have range `0..2^(8*w)-1`, padding must be `00`, and the decoding constructor should be `new BigInteger(1,bytes)`.

## 17. Zero, Sign Byte, and Mistakes When Serializing Unsigned

A common scenario: a protocol states the payload field is an **unsigned 256-bit integer**. When reading:

```java
byte[] payload = {(byte)0x80, 0x00}; // Scaled-down example.
BigInteger value = new BigInteger(1, payload); // +32768.
```

If you mistakenly use `new BigInteger(payload)`, the leading byte `0x80` sets the sign bit to 1 and the result is **-32768** in 16-bit signed. Thus the **signed constructor** does not fit an unsigned contract.

When writing unsigned values to a fixed-width array, there are two important rules:

1. **The value must be non-negative and fit within `w` unsigned bytes.** Non-negativity must be checked via `value.signum() >= 0`, with maximum `2^(8w)-1`.
2. **Do not mistake a leading `00` byte from `toByteArray()` for a mandatory payload data byte.** When a positive value has its high bit set, `toByteArray()` may add `00` to protect the sign. In an unsigned fixed-width payload, you should strip the sign-guard byte **if and only if** the value and byte count have been validated, then zero-pad to the exact length.

Example:

```java
BigInteger v = BigInteger.valueOf(255);
byte[] signed = v.toByteArray(); // [00, FF].
byte[] unsignedOneByte = {(byte)0xff}; // [FF], per unsigned contract.
BigInteger restored = new BigInteger(1, unsignedOneByte); // +255.
```

If `restored` were constructed with the signed constructor, it would turn back into -1. Consistency between **encoder and decoder** is essential; "the same bytes" is not enough to prove "the same value."

## 18. Standalone Java 17+ Program Verifying Key Behaviors

Save as **`BigIntegerBytesDemo.java`**:

```java
import java.math.BigInteger;
import java.util.Arrays;
import java.util.HexFormat;

public class BigIntegerBytesDemo {
    static String hex(byte[] bytes) {
        return HexFormat.of().formatHex(bytes);
    }

    static String typeOfError(Runnable action) {
        try {
            action.run();
            return "NO_ERROR";
        } catch (NumberFormatException | IndexOutOfBoundsException ex) {
            return ex.getClass().getSimpleName();
        }
    }

    public static void main(String[] args) {
        byte[] highBit = {(byte) 0x80};
        byte[] allOnes = {(byte) 0xff};
        System.out.println("signed80=" + new BigInteger(highBit));
        System.out.println("positive80=" + new BigInteger(1, highBit));
        System.out.println("signedFF=" + new BigInteger(allOnes));
        System.out.println("positiveFF=" + new BigInteger(1, allOnes));
        System.out.println("negativeMagnitudeFF=" + new BigInteger(-1, allOnes));
        System.out.println("signed0080=" + new BigInteger(new byte[]{0, (byte) 0x80}));
        System.out.println("signedFF7F=" + new BigInteger(new byte[]{(byte) 0xff, 0x7f}));
        System.out.println("unsignedJavaByte=" + Byte.toUnsignedInt(allOnes[0]));

        System.out.println("int128Bytes=" + hex(BigInteger.valueOf(128).toByteArray()));
        System.out.println("int255Bytes=" + hex(BigInteger.valueOf(255).toByteArray()));
        System.out.println("int127Bytes=" + hex(BigInteger.valueOf(127).toByteArray()));
        System.out.println("intMinus128Bytes=" + hex(BigInteger.valueOf(-128).toByteArray()));
        System.out.println("intMinus129Bytes=" + hex(BigInteger.valueOf(-129).toByteArray()));
        System.out.println("intMinus1Bytes=" + hex(BigInteger.valueOf(-1).toByteArray()));
        System.out.println("intZeroBytes=" + hex(BigInteger.ZERO.toByteArray()));
        System.out.println("positiveInputLeadingZeros="
                + new BigInteger(1, new byte[]{0, 0, (byte) 0xff}));
        System.out.println("normalizedLeadingZeros="
                + hex(new BigInteger(1, new byte[]{0, 0, (byte) 0xff}).toByteArray()));

        System.out.println("signZeroMagnitudeZero="
                + new BigInteger(0, new byte[]{0, 0}));
        System.out.println("signMinusOneMagnitudeZero="
                + new BigInteger(-1, new byte[]{0, 0}));
        System.out.println("signZeroNonzeroError=" + typeOfError(
                () -> new BigInteger(0, new byte[]{1})));
        System.out.println("signOutOfRangeError=" + typeOfError(
                () -> new BigInteger(2, new byte[]{1})));
        System.out.println("signedEmptyError=" + typeOfError(
                () -> new BigInteger(new byte[0])));
        System.out.println("magnitudeEmptyZero=" + new BigInteger(1, new byte[0]));

        byte[] mixed = {(byte) 0x7e, (byte) 0x00, (byte) 0x80, (byte) 0x7f};
        System.out.println("signedSlice=" + new BigInteger(mixed, 1, 2));
        System.out.println("magnitudeSlice=" + new BigInteger(1, mixed, 2, 1));
        System.out.println("hexStringPositive=" + new BigInteger("ff", 16));

        BigInteger[] numbers = {
                BigInteger.ZERO, BigInteger.ONE, BigInteger.valueOf(128),
                BigInteger.valueOf(-129), BigInteger.ONE.shiftLeft(100).negate()
        };
        boolean roundTrip = true;
        for (BigInteger n : numbers) {
            roundTrip &= n.equals(new BigInteger(n.toByteArray()));
        }
        System.out.println("signedRoundTrip=" + roundTrip);
        System.out.println("signumOfNegative="
                + BigInteger.valueOf(-129).signum());
        System.out.println("signumOfZero=" + BigInteger.ZERO.signum());
        System.out.println("sourceArrayUnchanged="
                + Arrays.equals(highBit, new byte[]{(byte)0x80}));
    }
}
```

Run on Java 17:

```bash
javac --release 17 -encoding UTF-8 BigIntegerBytesDemo.java
java BigIntegerBytesDemo
```

Exact stdout:

```text
signed80=-128
positive80=128
signedFF=-1
positiveFF=255
negativeMagnitudeFF=-255
signed0080=128
signedFF7F=-129
unsignedJavaByte=255
int128Bytes=0080
int255Bytes=00ff
int127Bytes=7f
intMinus128Bytes=80
intMinus129Bytes=ff7f
intMinus1Bytes=ff
intZeroBytes=00
positiveInputLeadingZeros=255
normalizedLeadingZeros=00ff
signZeroMagnitudeZero=0
signMinusOneMagnitudeZero=0
signZeroNonzeroError=NumberFormatException
signOutOfRangeError=NumberFormatException
signedEmptyError=NumberFormatException
magnitudeEmptyZero=0
signedSlice=128
magnitudeSlice=128
hexStringPositive=255
signedRoundTrip=true
signumOfNegative=-1
signumOfZero=0
sourceArrayUnchanged=true
```

Key result groups to note:

1. **`signed80=-128` vs `positive80=128`** and **`signedFF=-1` vs `positiveFF=255`** demonstrate the core difference between the two constructors.
2. **`negativeMagnitudeFF=-255`** shows that sign–magnitude with sign -1 **does not** first reinterpret byte `FF` as -1 before negating.
3. **`signed0080=128`, `signedFF7F=-129`** illustrate how the leading byte determines the sign in two's complement.
4. **`int128Bytes=0080`, `int255Bytes=00ff`** show `toByteArray()` prepends `00` to guard the sign; the `intMinus...` lines show negative values and minimal sign extension.
5. **`positiveInputLeadingZeros=255`, `normalizedLeadingZeros=00ff`** show that `BigInteger` does not remember original length/padding.
6. **`signZeroMagnitudeZero=0`, `signMinusOneMagnitudeZero=0`** show that zero is normalized; the `...Error=NumberFormatException` lines illustrate invalid signs or conflicts with magnitude.
7. **`signedEmptyError` vs `magnitudeEmptyZero`** distinguish empty arrays across the two constructors.
8. **`signedSlice` and `magnitudeSlice`** illustrate selecting a slice of data in an array; **`signedRoundTrip=true`** verifies that `toByteArray` → signed constructor preserves the `BigInteger` value for the examples.
9. **`signumOfNegative=-1`**, **`signumOfZero=0`** show `signum()` takes the sign of the actual value rather than simply copying the original signum argument.

The program uses `HexFormat` (available in Java 17) to print bytes in hex, avoiding confusion with negative `byte` values printed in decimal by `println`.

## 19. Two Different Round-Trips: By Value and By Bytes

**Value-preserving round-trip** with the signed constructor:

```java
BigInteger n = new BigInteger("-129");
BigInteger restored = new BigInteger(n.toByteArray());
// n.equals(restored) == true.
```

This is the path aligned with `BigInteger.toByteArray()`'s contract, because both ends use big-endian signed two's complement.

A **byte-for-byte round-trip** is different. For example:

```java
byte[] input = {0, 0, (byte) 0xff};
BigInteger value = new BigInteger(1, input);
byte[] output = value.toByteArray();
// output is [00, FF], shorter than input [00, 00, FF].
```

We still have **the value +255**, yet `input` and `output` differ in length. This is **not a `BigInteger` bug**: the class represents a numeric value and does not store the padding used in the input.

If you need to preserve the exact bytes of a protocol, **store the raw `byte[]` and format metadata** alongside `BigInteger` or apply a dedicated fixed-width encoder. When checking correctness, separate the condition "correct value" from the condition "exact byte string."

## 20. Common Mistakes and Fixes

| Misconception | Consequence | Fix |
| --- | --- | --- |
| Thinking `new BigInteger(bytes)` always reads unsigned | Leading byte `80`/`FF` produces negative numbers | Use `new BigInteger(1,bytes)` when contract is unsigned |
| Thinking `new BigInteger(-1,bytes)` takes negative two's complement bytes | Magnitude `FF` yields -255, not -1 | Pass **unsigned magnitude** and separate sign |
| Stripping leading `00` from signed representation | +255 can be read as -1 | Only strip if converting to unsigned format |
| Using raw `toByteArray()` to send exactly 32 bytes | Output has variable length | Encode fixed-width with range/padding checks |
| Thinking negative Java `byte` makes magnitude negative | Sign–magnitude constructor reads **unsigned bit patterns** | Use right constructor; do not sum signed byte values |
| Not knowing if input is big-endian or little-endian | Every byte can be read in the wrong order | Specify and convert byte order properly |
| Thinking `signum=0` is always accepted | Nonzero magnitude throws `NumberFormatException` | Check sign/magnitude consistency |
| Thinking `signum=-1` with zero magnitude makes -0 | `BigInteger` only has zero, no negative zero | Rely on `result.signum()` after construction |
| Passing `new byte[0]` to signed constructor | `NumberFormatException` | Use `BigInteger.ZERO` or `{0}` |
| Thinking `new BigInteger("ff",16)` equals signed byte `FF` | Hex text is +255, signed byte `FF` is -1 | Distinguish string parsing from binary parsing |
| Narrowing large `BigInteger` with `intValue()` | Can lose high bits, returning wrong number | Use `intValueExact()` when checking is needed |
| Testing only with leading bytes below `80` | Misses sign bugs | Always test `7F`, `80`, `FF`, `00 80`, `FF 7F` |

## 21. Self-Check Questions

1. **What value does `new BigInteger(new byte[]{(byte)0x80})` give?** -128, because a one-byte signed two's complement array has sign bit 1.
2. **How do you correctly read +128 from `{(byte)0x80}`?** Use `new BigInteger(1,bytes)` or pass signed array `{0,(byte)0x80}`.
3. **What does `new BigInteger(new byte[]{(byte)0xff})` give?** -1.
4. **What does `new BigInteger(-1,new byte[]{(byte)0xff})` give?** -255, because the array is read as magnitude 255 and the separate sign is negative.
5. **Why does `BigInteger.valueOf(255).toByteArray()` have two bytes `00 FF`?** The `00` byte keeps sign bit 0 so the signed constructor reads +255.
6. **Why is `BigInteger.valueOf(-129).toByteArray()` equal to `FF 7F`?** One signed byte is not enough to hold -129; a 16-bit two's complement representation is required.
7. **Is `BigInteger.ZERO.toByteArray()` an empty array or `[00]`?** `[00]`; at least one byte is needed to represent zero in signed encoding.
8. **Is `new BigInteger(0,new byte[]{1})` valid?** No. It throws `NumberFormatException` because sign 0 contradicts a nonzero magnitude.
9. **Does `new BigInteger(-1,new byte[]{0})` create negative zero?** No. The value is 0 and `signum()` returns 0.
10. **Do the signed and sign–magnitude constructors use different byte orders?** No, both are big-endian; they differ in how the sign is interpreted.
11. **Is `new BigInteger("ff",16)` the same as `new BigInteger(new byte[]{(byte)0xff})`?** No. The first is +255, the second is -1.
12. **Why does parsing `[00 00 FF]` and calling `toByteArray()` not keep three bytes?** `BigInteger` holds the numeric value; `toByteArray` outputs minimal signed representation.
13. **If a protocol requires 32-byte unsigned, should `toByteArray()` be used directly?** No. You must check that the value is non-negative and fits in 256 bits, strip any guard sign byte if needed, then zero-pad to exactly 32 bytes.
14. **To read an unsigned hash/digest with its leading bit set, which constructor do you choose?** `new BigInteger(1,hashBytes)` when interpreting the hash as an unsigned magnitude, while keeping raw bytes/length separately if byte round-tripping is needed.

**Key takeaway:** `new BigInteger(byte[])` accepts **big-endian signed two's complement**; `new BigInteger(signum,byte[])` accepts **a separate sign and big-endian unsigned magnitude**. `toByteArray()` always returns **minimal signed two's complement**, which may add `00` to preserve positive numbers or drop padding relative to original data. When working with binary protocols, establish **signedness, width, and byte order** up front; choose the right constructor, test boundaries, and use a fixed-width encoder whenever the format requires one.