# Integer Narrowing and Discarded Bits — Java 17+

When converting an integer value to a **narrower** integer type in Java, the result is not guaranteed to preserve the value. For `long -> int`, `int/long -> short`, `int/long -> byte`, or `int/long -> char` conversions, Java **discards the higher-order bits** and keeps the low-order bits matching the width of the target type. Then, the value is interpreted according to the **signed or unsigned** rule of the target type.

This is behavior defined by the language, **not an overflow exception**. Writing a `(byte)` or `(short)` cast only requests a type conversion; it does not check whether the value falls within the target range.

## 1. Recall value ranges and bit widths

| Type | Width | Interpretation | Range |
| --- | ---: | --- | --- |
| `byte` | 8 bits | Signed integer, two's complement | −128 to 127 |
| `short` | 16 bits | Signed integer, two's complement | −32,768 to 32,767 |
| `char` | 16 bits | **Unsigned** UTF-16 code unit | 0 to 65,535 |
| `int` | 32 bits | Signed integer, two's complement | −2,147,483,648 to 2,147,483,647 |
| `long` | 64 bits | Signed integer, two's complement | −2⁶³ to 2⁶³−1 |

**Notably:** `short` and `char` both have 16 bits, but their interpretations are **different**. The exact same bit pattern `0xABCD` is `-21555` when viewed as `short`, yet `43981` when viewed as `char`.

## 2. Rule for keeping low bits

When narrowing an integer to `n` bits:

1. Take the binary representation of the source value.
2. **Keep the lowest `n` bits**, discarding all higher bits.
3. Read the remaining bit pattern according to the target type: `byte`/`short`/`int` are signed; `char` is unsigned.

For example, `int 130` has the following low 16 bits:

~~~text
Original value 130:       00000000 10000010
Keep low 8 bits:                   10000010
Discard high 8 bits:      xxxxxxxx
                                     
(byte) 130:                        10000010  →  -126
Unsigned interpretation:           10000010  →   130
~~~

The bit pattern `10000010` has its most significant bit equal to 1, so `byte` interprets it in two's complement as `-126`. Meanwhile, `Byte.toUnsignedInt((byte) 130)` gives `130` because it interprets those eight bits as an **unsigned** number.

Second example, `int 0x1234ABCD` converted to 16 bits:

~~~text
32-bit int:         0x1234 ABCD
Discard high bits:  0x1234 ----
Keep low bits:      0x---- ABCD

(short) 0x1234ABCD → -21555
(char)  0x1234ABCD →  43981
~~~

## 3. Runnable Java 17+ program

Create a UTF-8 file named **`NarrowingBitsDemo.java`**:

~~~java
public class NarrowingBitsDemo {
    private static String bits8(int value) {
        return String.format("%8s",
                Integer.toBinaryString(value & 0xFF))
                .replace(' ', '0');
    }

    private static String bits16(int value) {
        return String.format("%16s",
                Integer.toBinaryString(value & 0xFFFF))
                .replace(' ', '0');
    }

    public static void main(String[] args) {
        int source = 130;
        byte narrowed = (byte) source;

        System.out.println("130.binary16=" + bits16(source));
        System.out.println("130.low8=" + bits8(narrowed));
        System.out.println("130.asByte=" + narrowed);
        System.out.println("130.asUnsignedByte="
                + Byte.toUnsignedInt(narrowed));

        System.out.println("255.asByte=" + (byte) 255);
        System.out.println("256.asByte=" + (byte) 256);
        System.out.println("-129.asByte=" + (byte) -129);

        int hex = 0x1234ABCD;
        System.out.printf("hex.original=0x%08X%n", hex);
        System.out.printf("hex.low16=0x%04X%n", hex & 0xFFFF);
        System.out.println("hex.asShort=" + (short) hex);
        System.out.println("hex.asCharCode=" + (int) (char) hex);

        long large = 0x1_0000_0001L;
        System.out.println("long.asInt=" + (int) large);

        byte counter = 127;
        counter += 1;
        System.out.println("compoundWrap=" + counter);

        try {
            Math.toIntExact(large);
            System.out.println("toIntExact=ok");
        } catch (ArithmeticException ex) {
            System.out.println("toIntExact=overflow");
        }

        boolean fitsByte = source >= Byte.MIN_VALUE
                && source <= Byte.MAX_VALUE;
        System.out.println("fitsByte130=" + fitsByte);
    }
}
~~~

Open **PowerShell** (Windows) or **Bash** (Linux/macOS) in the directory containing the file. JDK 17 or newer is required:

~~~bash
java -version
javac -version
javac -encoding UTF-8 NarrowingBitsDemo.java
java NarrowingBitsDemo
~~~

**Exact expected output of the `java NarrowingBitsDemo` command:**

~~~text
130.binary16=0000000010000010
130.low8=10000010
130.asByte=-126
130.asUnsignedByte=130
255.asByte=-1
256.asByte=0
-129.asByte=127
hex.original=0x1234ABCD
hex.low16=0xABCD
hex.asShort=-21555
hex.asCharCode=43981
long.asInt=1
compoundWrap=-128
toIntExact=overflow
fitsByte130=false
~~~

The `java -version` and `javac -version` commands display environment-dependent information; the block above only describes the program output.

## 4. Explaining each group of results

### From `int` to `byte`

`130` written in 16 bits is `0000000010000010`. Casting to `byte` keeps the low eight bits `10000010`, which Java interprets as signed `-126`.

`Byte.toUnsignedInt(narrowed)` **does not mutate the object or bits inside the byte**. This method produces an `int` value representing those exact eight bits of the `byte` as an unsigned integer from 0 to 255.

| Source value | Low 8 bits | `byte` value after cast |
| ---: | --- | ---: |
| `127` | `01111111` | 127 |
| `128` | `10000000` | −128 |
| `130` | `10000010` | −126 |
| `255` | `11111111` | −1 |
| `256` | `00000000` | 0 |
| `-129` | `01111111` | 127 |

You can think of the unsigned result as the remainder modulo `2^8 = 256`, and then if the sign bit is 1, `byte` interprets the result in the negative range. **Do not** think of a cast as “clamping the value at −128 or 127”: Java does not do that for integer narrowing.

### From `int` to `short` and `char`

The source value `0x1234ABCD` consists of 32 bits. Both target types keep only the **low 16 bits**, `0xABCD`.

- For `short`, `0xABCD` equals 43981 when viewed unsigned, but because the 16-bit sign bit is 1, the signed value is `43981 - 65536 = -21555`.
- For `char`, `0xABCD` is read **unsigned**, so the value is `43981`. This is a UTF-16 code unit, not necessarily a complete printable character by default.

Merely casting to `char` does not turn the value into a `String`. To print the numeric code of a `char`, for example, use `(int) (char) hex` as in the program.

### From `long` to `int`

`0x1_0000_0001L` equals `4294967297` (one more than `2^32`). When cast to `int`, Java keeps the low 32 bits `0x00000001`, so the result is **1**. Losing these high bits can cause identifiers, counters, or calculations to go severely wrong if the programmer does not check ranges.

## 5. Explicit casting does not mean “safe”

~~~java
int source = 130;
byte b = (byte) source; // Syntactically valid, but b = -126.
~~~

The compiler accepts the cast because the programmer requested the conversion. However, the compiler **does not infer that this is a business-correct choice**.

How to check before casting to `byte`:

~~~java
int value = 130;

if (value < Byte.MIN_VALUE || value > Byte.MAX_VALUE) {
    throw new IllegalArgumentException("Out of byte range");
}

byte narrowed = (byte) value;
~~~

A similar approach applies to `short` (`Short.MIN_VALUE`/`Short.MAX_VALUE`), `char` (0 to `Character.MAX_VALUE`), and other integer types. When narrowing `long` to `int`, Java 17 provides:

~~~java
int exact = Math.toIntExact(42L); // 42.

// Math.toIntExact(0x1_0000_0001L) throws ArithmeticException.
~~~

`Math.toIntExact` checks whether the **entire `long` value fits within the `int` range**, not just taking the low bits. There is no equivalent standard `Math.toByteExact` method; to cast `int` to `byte`, check the range as shown above or use an explicitly chosen library.

## 6. Constant assignment and compound assignment operators

Two Java rules easily mislead learners into thinking Java always narrows automatically:

**A. In-range integer constants:**

~~~java
byte ok = 100;          // Valid: int constant 100 is within byte range.
// byte bad = 130;      // Compile error: exceeds byte range.
byte casted = (byte) 130; // Valid, value is -126.
~~~

The compiler allows certain `int` constant expressions to be assigned to `byte`/`short`/`char` if the value is within range. Yet an arbitrary `int` variable **cannot** automatically be assigned to `byte`:

~~~java
int n = 100;
// byte x = n;      // Error: requires cast.
byte x = (byte) n;  // Valid.
~~~

**B. Compound assignment has an implicit cast:**

~~~java
byte count = 127;
count += 1; // Valid: result narrows to byte -> -128.

// count = count + 1; // Compile error: addition is int.
~~~

In the arithmetic expression `count + 1`, `count` is promoted to `int` and the result has type `int`. With `count += 1`, Java applies compound assignment and converts back to the left-hand side's type, equivalent in type effect to casting down to `byte`. Thus, this increment **can also lose bits**.

## 7. Distinguish two commonly confused mechanisms

**Integer → integer narrowing:** keeps the low bits and interprets the target type according to signed/unsigned rules; e.g., `(byte) 130 == -126`.

**Floating-point → integer casting:** does **not** simply take the low bits of the floating-point representation. Java applies floating-point-to-integral conversion rules, including truncating the fractional part toward 0, handling `NaN`, and clamping out-of-range values. For example, `(int) 12.9 == 12`.

This lesson focuses on **discarded bits when narrowing between integer types**. Do not use the “keep low bits” model to explain every cast in Java.

## 8. Self-check exercises

**Exercise 1.** What are the results of `(byte) 128` and `(byte) 256`?

*Answer:* `-128` and `0`, because the low eight bits are `10000000` and `00000000`, respectively.

**Exercise 2.** Why is `(short) 0x1234ABCD` equal to `-21555`?

*Answer:* Only the low 16 bits `0xABCD` are kept; interpreting 16 signed bits yields `43981 - 65536 = -21555`.

**Exercise 3.** With the same source above, what is `(int) (char) 0x1234ABCD`?

*Answer:* `43981`, because `char` keeps the low 16 bits and is unsigned.

**Exercise 4.** What value does `(int) 0x1_0000_0001L` return? Does it throw an exception?

*Answer:* It returns **1**, and does not automatically throw an exception on cast. Only `Math.toIntExact` reports `ArithmeticException` due to exceeding the `int` range.

**Exercise 5.** What result does `byte b = 127; b += 1;` produce? Why?

*Answer:* `-128`. The addition is computed in `int`, but `+=` converts back to `byte`, discarding bits higher than eight bits.

## Memory checklist

- [ ] Determine the **bit width** of the source and target types.
- [ ] **Integer → integer** narrowing keeps low bits and discards high bits.
- [ ] `byte`/`short`/`int` are signed; `char` is 16-bit unsigned.
- [ ] A syntactically valid cast does not mean the value stays unchanged.
- [ ] Check range before casting when data loss is an error.
- [ ] `Math.toIntExact` helps check `long -> int`.
- [ ] Note type conversion in `+=` and arithmetic operations with `byte`, `short`.
- [ ] Do not apply the keep-low-bits rule to explain `double -> int` casting.

**Conclusion:** When narrowing between Java integer types, the key question is **“which bits are discarded, and will the remaining bits be interpreted as signed or unsigned?”** If exact data is needed, do not cast blindly; check the range or choose a wide-enough type from the start.