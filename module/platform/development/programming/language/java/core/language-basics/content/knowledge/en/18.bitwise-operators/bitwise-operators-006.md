# Numeric Promotion When Operating on `byte`, `short`, or `char` — Java 17+

In Java, many arithmetic and bitwise operators **do not compute directly at 8-bit or 16-bit widths**, even when the operands are `byte`, `short`, or `char`. Before computing, Java applies **numeric promotion**, typically turning these operands into **32-bit `int`**.

~~~java
byte b = 5;
int shifted = b << 1; // 10, int type.
int inverted = ~b;    // -6, int type.
~~~

**Key point:** Distinguish three steps:

1. **Operand promotion** from `byte`/`short`/`char` to `int`.
2. **Computation** on the promoted type, such as bitwise AND, bitwise XOR, or bit shifting.
3. **Conversion upon assignment** (if the destination variable has a narrower type): a cast may be required, or `op=` will perform an implicit narrowing conversion.

Do not assume that `b << 1` or `~b` has type `byte` simply because `b` is a `byte`.

## 1. Overview Table

| Source type | Width | Value range | When widened to `int` |
| --- | ---: | --- | --- |
| `byte` | 8 bits | −128 to 127 | **Sign extension** |
| `short` | 16 bits | −32,768 to 32,767 | **Sign extension** |
| `char` | 16 bits | 0 to 65,535 | **Zero extension** |

`char` is an **unsigned UTF-16 code unit**, not a "signed character" type. For example, `char c = (char) 0xFFFF;` becomes **65535** when converted to `int`, whereas `short s = -1;` becomes **-1**, even though both have all 16 bits set to 1 at their original width.

### Related Operators

| Operator | Promotion rule | Result type |
| --- | --- | --- |
| `+x`, `-x`, `~x` | **Unary numeric promotion** | `int` if `x` is `byte`/`short`/`char` |
| `x << n`, `x >> n`, `x >>> n` | **Separate unary numeric promotion on each operand** | Type of the **promoted left operand** |
| `x & y`, `x \| y`, `x ^ y` when **bitwise on integers** | **Binary numeric promotion** | Usually `int`; `long` if either operand is `long` |
| `x + y`, `x - y`, `x * y` | **Binary numeric promotion** | Usually `int` for small types |
| `x &= y`, `x <<= n` (compound assignment) | Computed in promoted type, then **cast back to the type of `x`** | Type of the left-hand variable |

The same symbols `&`, `|`, and `^` also have boolean logical meanings when both operands are `boolean`. This lesson covers the **integer cases**, not boolean logic.

## 2. Self-Contained Java 17+ CLI Demo

Create a UTF-8 file **`BitPromotionDemo.java`**:

~~~java
public class BitPromotionDemo {
    static String kind(int unused) {
        return "int";
    }

    static String kind(long unused) {
        return "long";
    }

    static String bits8(int value) {
        String bits = Integer.toBinaryString(value & 0xFF);
        return "0".repeat(8 - bits.length()) + bits;
    }

    static String bits16(int value) {
        String bits = Integer.toBinaryString(value & 0xFFFF);
        return "0".repeat(16 - bits.length()) + bits;
    }

    public static void main(String[] args) {
        byte b = 5;
        short s = 9;
        char c = 'A';

        System.out.println("== int promotion ==");
        System.out.println("byteShiftType=" + kind(b << 1));
        System.out.println("byteShift=" + (b << 1));
        System.out.println("shortShiftType=" + kind(s << 2));
        System.out.println("shortShift=" + (s << 2));
        System.out.println("charShiftType=" + kind(c << 1));
        System.out.println("charShift=" + (c << 1));
        System.out.println("byteAndShortType=" + kind(b & s));
        System.out.println("byteAndShort=" + (b & s));
        System.out.println("charXorByteType=" + kind(c ^ b));
        System.out.println("charXorByte=" + (c ^ b));
        System.out.println("plusByteType=" + kind(+b));
        System.out.println("minusByte=" + (-b));
        System.out.println("notByte=" + (~b));
        System.out.println("notChar=" + (~c));

        System.out.println("== sign vs zero extension ==");
        byte signedByte = -1;
        short signedShort = -2;
        char unsignedChar = (char) 0xFFFF;
        System.out.println("byteAsInt=" + (int) signedByte);
        System.out.println("byteHex="
                + Integer.toHexString(signedByte));
        System.out.println("byteBits8=" + bits8(signedByte));
        System.out.println("unsignedByte=" + (signedByte & 0xFF));
        System.out.println("shortAsInt=" + (int) signedShort);
        System.out.println("shortBits16=" + bits16(signedShort));
        System.out.println("unsignedShort="
                + Short.toUnsignedInt(signedShort));
        System.out.println("charAsInt=" + (int) unsignedChar);
        System.out.println("charRight15=" + (unsignedChar >> 15));
        System.out.println("shortRight15=" + (signedShort >> 15));
        System.out.println("charShiftLeft=" + (unsignedChar << 1));

        System.out.println("== shift semantics ==");
        System.out.println("byteLogicalRight="
                + (signedByte >>> 1));
        System.out.println("shortArithmeticRight="
                + (signedShort >> 1));
        long distance = 33L;
        System.out.println("byteLongDistanceType="
                + kind(b << distance));
        System.out.println("byteLongDistance="
                + (b << distance));
        System.out.println("intShiftToSignBit="
                + (b << 31));

        System.out.println("== compound assignments ==");
        byte narrow = 100;
        int promoted = narrow << 1;
        narrow <<= 1;
        System.out.println("promotedValue=" + promoted);
        System.out.println("compoundByteValue=" + narrow);
        System.out.println("compoundByteBits=" + bits8(narrow));

        byte masked = -1;
        masked &= 0x0F;
        System.out.println("compoundAndByte=" + masked);

        char movedChar = 'A';
        movedChar <<= 1;
        System.out.println("compoundCharCode=" + (int) movedChar);

        short medium = 30_000;
        int promotedShort = medium << 1;
        medium <<= 1;
        System.out.println("promotedShort=" + promotedShort);
        System.out.println("compoundShort=" + medium);

        System.out.println("== long promotion and wrappers ==");
        System.out.println("byteAndLongType="
                + kind(signedByte & 0xFFL));
        System.out.println("byteAndLongValue="
                + (signedByte & 0xFFL));

        Byte boxed = null;
        try {
            int unused = boxed & 0xFF;
            System.out.println("unexpected=" + unused);
        } catch (NullPointerException ex) {
            System.out.println("boxedNull=NullPointerException");
        }
    }
}
~~~

Using **JDK 17+**, open PowerShell or Bash in the directory containing the file:

~~~bash
java -version
javac -version
javac -encoding UTF-8 BitPromotionDemo.java
java BitPromotionDemo
~~~

**Exact expected stdout** of the `java BitPromotionDemo` command alone:

~~~text
== int promotion ==
byteShiftType=int
byteShift=10
shortShiftType=int
shortShift=36
charShiftType=int
charShift=130
byteAndShortType=int
byteAndShort=1
charXorByteType=int
charXorByte=68
plusByteType=int
minusByte=-5
notByte=-6
notChar=-66
== sign vs zero extension ==
byteAsInt=-1
byteHex=ffffffff
byteBits8=11111111
unsignedByte=255
shortAsInt=-2
shortBits16=1111111111111110
unsignedShort=65534
charAsInt=65535
charRight15=1
shortRight15=-1
charShiftLeft=131070
== shift semantics ==
byteLogicalRight=2147483647
shortArithmeticRight=-1
byteLongDistanceType=int
byteLongDistance=10
intShiftToSignBit=-2147483648
== compound assignments ==
promotedValue=200
compoundByteValue=-56
compoundByteBits=11001000
compoundAndByte=15
compoundCharCode=130
promotedShort=60000
compoundShort=-5536
== long promotion and wrappers ==
byteAndLongType=long
byteAndLongValue=255
boxedNull=NullPointerException
~~~

The output of `java -version` and `javac -version` is environment-dependent and not part of the fixed stdout block. The program uses only standard Java APIs and requires no external libraries.

## 3. Unary Numeric Promotion in Shifts and `~`

For the shift operators `<<`, `>>`, and `>>>`, Java promotes **each operand separately** via *unary numeric promotion*. A `byte`, `short`, or `char` on the left becomes `int`, so the result type is **`int`**.

~~~java
byte b = 5;
int result = b << 2; // 20, int.
// byte wrong = b << 2; // Error: cannot assign int to byte.
~~~

**The shift distance is determined by the promoted left operand type:**

- For `int`: only the **low 5 bits** of the shift distance are used (`n & 31`).
- For `long`: only the **low 6 bits** are used (`n & 63`).

~~~java
byte b = 5;
long count = 33L;
int shifted = b << count; // 10, because left type is int and 33 & 31 = 1.
~~~

`count` being `long` **does not make the result `long`**. This is an important contrast with binary addition, where both operands can be promoted together to the wider type.

**The `~` operator also performs unary numeric promotion:**

~~~java
byte b = 5;
int inverted = ~b; // -6 (inverts all 32 bits of int 5).
~~~

`~b` does not invert just the original 8 bits. When `b == 5`, after promoting to `int` you have the 32-bit pattern `...00000101`, and inverting all 32 bits produces the two's complement pattern for **-6**.

## 4. Binary Numeric Promotion with Numeric `&`, `|`, `^`

With integer operands, `&`, `|`, and `^` apply **binary numeric promotion** before computing.

~~~java
byte a = 5;      // 00000101
short b = 9;     // 0000000000001001

int andResult = a & b; // 1.
int orResult = a | b;  // 13.
int xorResult = a ^ b; // 12.
~~~

The result has type **`int`** because both narrow operands are promoted to `int`.

| Operands | Result type | Example |
| --- | --- | --- |
| `byte & short` | `int` | `5 & 9` = 1 |
| `char ^ byte` | `int` | `65 ^ 5` = 68 |
| `short \| int` | `int` | Promotes `short` to `int` |
| `byte & long` | `long` | Promotes `byte` to `long` |
| `char & long` | `long` | Promotes `char` to `long` |

When `long` is present, the bitwise operation runs on **64 bits**. For example, `byte b = -1; long x = b & 0xFFL;` yields 255 because `b` is sign-extended to `long -1` and then ANDed with the mask `255L`.

### Do Not Confuse Bitwise Operators with Logical Operators

`&`, `|`, and `^` also apply to two `boolean` operands. On integers, they operate **bit by bit**; on booleans, the result is boolean. `&&` and `||` are only for booleans and **short-circuit**; they cannot be used on `int`.

## 5. Sign Extension and Zero Extension

### Negative `byte` and `short`: Sign Extension

~~~java
byte b = -1;
int x = b; // -1.
~~~

Bit pattern illustration:

~~~text
byte -1:    11111111
int  -1:    11111111111111111111111111111111
~~~

Java pads with **1 bits** because the source value is negative. Consequently, `Integer.toHexString(b)` prints `ffffffff` rather than `ff`.

To inspect only the unsigned low 8 bits, apply a mask:

~~~java
int unsigned = b & 0xFF; // 255.
int same = Byte.toUnsignedInt(b); // 255.
~~~

For `short`, use `s & 0xFFFF` or `Short.toUnsignedInt(s)` to read the low 16 bits as unsigned.

### `char`: Zero Extension

~~~java
char c = (char) 0xFFFF;
int x = c; // 65535.
~~~

Bit pattern:

~~~text
char:        1111111111111111
int:         00000000000000001111111111111111
~~~

`char` is not a negative integer, even when the highest bit of the 16-bit pattern is 1. Therefore:

~~~java
char c = (char) 0xFFFF;
short s = -2;

System.out.println(c >> 15); // 1.
System.out.println(s >> 15); // -1.
~~~

`c` widens to a non-negative `int`, so `>>` inserts 0 bits on the left. `s` widens to `int -2`, so `>>` fills with 1 bits on the left to preserve the sign.

### Why Does `byte >>> 1` Sometimes Produce a Huge Value?

~~~java
byte b = -1;
int x = b >>> 1; // 2147483647.
~~~

`b` is sign-extended to **`int -1`**, consisting of 32 `1` bits. `>>> 1` inserts a 0 bit on the left and leaves 31 `1` bits, producing **2147483647**, not 127.

If you want a logical right shift on the **original 8 bits**:

~~~java
int unsignedShift = (b & 0xFF) >>> 1; // 127.
~~~

Here, the `0xFF` mask **clears the sign-extension bits before shifting**. Masking after the shift can yield a different result in some expressions; choose the order based on the exact data width you intend.

## 6. Compound Assignment Can Narrow the Result Back to the Original Type

Regular expressions can yield `int`, whereas compound assignment `op=` performs an **implicit narrowing conversion back to the left variable's type**:

~~~java
byte b = 100;
int result = b << 1; // 200.
b <<= 1;             // valid, b becomes -56.

// b = b << 1;       // Compile error without cast.
b = (byte) (b << 1); // Explicit cast if using the expanded form.
~~~

Because the `byte` range is -128..127, narrowing `int 200` to the low 8 bits gives `11001000`, which reads as **-56** when signed.

The same happens with `short` and `char`:

~~~java
short s = 30_000;
int promoted = s << 1; // 60000.
s <<= 1;               // short -5536.

char c = 'A';
c <<= 1; // char with code unit 130.
~~~

With bitwise operators, `byte b = -1; b &= 0x0F;` is also valid and leaves **15**, because the result is cast back to `byte`.

**Do not treat successful compilation as proof of no data loss.** Compound assignment operators like `<<=`, `&=`, `|=`, and `^=` implicitly cast back to the original variable's type. If you need the full result, store it in `int` or `long` before narrowing.

## 7. Wrappers, `null`, and Result Types

If a number is boxed in `Byte`, `Short`, or `Character`, numeric operators will **unbox** it before applying numeric promotion.

~~~java
Byte boxed = 5;
int shifted = boxed << 1; // 10.
~~~

A `null` wrapper holds no numeric value to unbox:

~~~java
Byte missing = null;
// int value = missing & 0xFF; // Throws NullPointerException.
~~~

A `Byte` variable does not turn `&` into a reference-object operator. It remains an integer operation once unboxed normally.

`var` also takes the **type of the initializer expression**:

~~~java
byte b = 5;
var x = b << 1; // x has type int.
var y = ~b;     // y has type int.
~~~

`x` will not be inferred as `byte` merely because the input is a `byte`.

## 8. Common Pitfalls

| Misconception | Correct rule |
| --- | --- |
| "`byte << 1` returns `byte`." | Left operand promotes to `int`; result is `int` |
| "`~byte` inverts only 8 bits." | Promotes to `int` first; `~` inverts **32 bits** |
| "`short & char` returns `short`." | Both operands promote to `int`; result is `int` |
| "A `long` shift distance makes the shift result `long`." | Result type depends on the **left operand** |
| "`char` with high bit 1 means a negative number." | `char` is unsigned and zero-extends |
| "`byte -1 >>> 1` returns 127." | Returns **2147483647** due to sign extension to `int` |
| "`byteValue <<= 1` always preserves the exact mathematical value." | It can narrow, drop bits, and flip sign |
| "A `null` `Byte` is automatically treated as 0." | Unboxing `null` throws `NullPointerException` |
| "`var x = b << 1` infers the type of `b`." | It infers the type of the **expression**, which is `int` |

## 9. Self-Check Exercises

1. `byte b = 7; var x = b << 1;` — what are the type and value of `x`?  
   *Answer:* `int`, value **14**.
2. `byte b = 5; int n = ~b;` — what is `n`?  
   *Answer:* **-6**, because all bits of `int 5` are inverted.
3. `byte a = 5; short b = 9; var n = a & b;` — what are the type and value?  
   *Answer:* `int`, value **1**.
4. `char c = (char) 0xFFFF; int x = c;` — what is `x`?  
   *Answer:* **65535**, because `char` zero-extends.
5. `short s = -2; int x = s >> 15;` — what is `x`?  
   *Answer:* **-1**, due to sign extension.
6. `byte b = -1; int x = b >>> 1;` — what is `x`?  
   *Answer:* **2147483647**.
7. `byte b = 100; b <<= 1;` — what is `b`?  
   *Answer:* **-56**, due to narrowing `int 200` to `byte`.
8. `char c = 'A'; c <<= 1;` — what is the numeric code of `c`?  
   *Answer:* **130**.
9. `byte b = 5; long n = 33L; var x = b << n;` — what are the type and value of `x`?  
   *Answer:* `int` and **10**; the shift distance is `33 & 31 = 1`.

## Checklist

- [ ] Remember that `byte`/`short`/`char` normally promote to `int` before bitwise operations.
- [ ] Distinguish **unary numeric promotion** of `~` and shifts from **binary numeric promotion** of `&`/`|`/`^`.
- [ ] Know that `byte`/`short` **sign-extend**, while `char` **zero-extends**.
- [ ] Understand that a shift's result type depends on the **left operand**, not the shift distance's type.
- [ ] Recognize that `byte >>> 1` actually executes on 32-bit `int` after sign extension.
- [ ] Evaluate potential data loss when using `<<=`, `&=`, and other compound assignments on narrow types.
- [ ] Check for `null` before unboxing wrappers.
- [ ] Use `0xFF`/`0xFFFF` masks or unsigned APIs when viewing raw unsigned data.

**Conclusion:** In Java bitwise operations, `byte`, `short`, and `char` usually act as **8/16-bit data sources**, whereas **the actual computation takes place on 32-bit `int`**. Tracking **promotion**, **sign/zero extension**, and **narrowing upon reassignment** prevents seemingly surprising results.
