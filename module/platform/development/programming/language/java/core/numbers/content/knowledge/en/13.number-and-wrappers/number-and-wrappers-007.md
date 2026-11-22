# MIN_VALUE, MAX_VALUE, TYPE, and Per-Class Constants in Java

## 1. Concept

Java has six numeric primitive types: `byte`, `short`, `int`, `long`, `float`, `double`. Their corresponding wrappers are **Byte**, **Short**, **Integer**, **Long**, **Float**, and **Double**, all extending the abstract class **Number**. These classes provide **public static final** constants to look up representation bounds, bit width, byte size, and the associated primitive type.

**Character** and **Boolean** are also wrappers, yet do not extend `Number`. **Void** has `TYPE` representing `void`, even though `void` holds no value for arithmetic.

~~~java
int smallest = Integer.MIN_VALUE;
int largest = Integer.MAX_VALUE;
Class<Integer> primitiveType = Integer.TYPE;
~~~

The fields above belong to the **class**, requiring no `Integer` object instantiation. The most important point: the meaning of **MIN_VALUE** on integer wrappers **differs** from that on `Float` and `Double`.

## 2. Basic Constants Table

| Class | MIN_VALUE | MAX_VALUE | Represented TYPE | SIZE (bits) | BYTES |
| --- | --- | --- | --- | ---: | ---: |
| Byte | −128 | 127 | byte.class | 8 | 1 |
| Short | −32768 | 32767 | short.class | 16 | 2 |
| Integer | −2147483648 | 2147483647 | int.class | 32 | 4 |
| Long | −9223372036854775808 | 9223372036854775807 | long.class | 64 | 8 |
| Float | 2^−149, **positive** | about 3.4028235 × 10^38, finite positive | float.class | 32 | 4 |
| Double | 2^−1074, **positive** | about 1.7976931348623157 × 10^308, finite positive | double.class | 64 | 8 |

n-bit signed integers use the range **−2^(n−1)** to **2^(n−1)−1**. Thus `Integer.MIN_VALUE` is one unit more negative than the negation of `Integer.MAX_VALUE`.

Conversely, **Float.MIN_VALUE/Double.MIN_VALUE** is the **smallest** nonzero positive value in IEEE 754 format, not the lowest finite negative value. Always read the meaning of a field according to the class that declares it.

## 3. Byte, Short, Integer, Long, and Arithmetic Overflow

`Byte` and `Short` have `MIN_VALUE`/`MAX_VALUE` of **−128/127** and **−32768/32767**, respectively. Those fields have type **byte/short**, yet addition normally promotes operands to `int`:

~~~java
byte b = Byte.MAX_VALUE;
int next = b + 1;                   // 128, type int
byte wrapped = (byte) (b + 1);     // -128
// byte invalid = b + 1;           // compile error: int does not auto-narrow to byte
~~~

For `Integer`, addition stays within 32 bits if there is no `long` operand:

~~~java
int overflowed = Integer.MAX_VALUE + 1;       // -2147483648
long stillWrong = Integer.MAX_VALUE + 1;      // -2147483648L
long correct = (long) Integer.MAX_VALUE + 1;  // 2147483648L
~~~

Assigning to `long` **after the computation** does not prevent `int` overflow. If an error must be reported on overflow, use **Math.addExact**, **Math.subtractExact**, **Math.multiplyExact**, or **Math.negateExact**, depending on the operation.

Two boundary cases of signed integers:

~~~java
int min = Integer.MIN_VALUE;
int negated = -min;               // still -2147483648
int absolute = Math.abs(min);     // still -2147483648
long positive = -(long) min;      // 2147483648L
~~~

**−Integer.MIN_VALUE** does not fit in the `int` range. Similarly, **−Long.MIN_VALUE** does not fit in the `long` range. If you need values larger than `Long.MAX_VALUE`, use **BigInteger** to compute accurately.

**Unsigned:** `Integer.MAX_VALUE` is the **signed** maximum. The same 32-bit all-ones pattern has signed `int` value **−1**, yet **Integer.toUnsignedString(-1)** returns the string **4294967295**. Similarly, **Long.toUnsignedString(-1L)** returns **18446744073709551615**. Java has no separate `unsigned int`/`unsigned long` primitive types; these are APIs interpreting bit patterns under unsigned conventions.

## 4. Float and Double: Normal, Subnormal, and Infinity

| Constant | Float (binary32) | Double (binary64) |
| --- | --- | --- |
| MIN_VALUE | 2^−149 ≈ 1.4 × 10^−45 | 2^−1074 ≈ 4.9 × 10^−324 |
| MIN_NORMAL | 2^−126 ≈ 1.17549435 × 10^−38 | 2^−1022 ≈ 2.2250738585072014 × 10^−308 |
| MAX_VALUE | ≈ 3.4028235 × 10^38 | ≈ 1.7976931348623157 × 10^308 |
| POSITIVE_INFINITY | +Infinity | +Infinity |
| NEGATIVE_INFINITY | −Infinity | −Infinity |
| NaN | Not a Number | Not a Number |
| MIN_EXPONENT | −126 | −1022 |
| MAX_EXPONENT | 127 | 1023 |

**MIN_NORMAL** is the smallest positive normal number. **MIN_VALUE** is the **smallest positive subnormal number**, smaller than `MIN_NORMAL`. This gives Java gradual underflow: a result smaller than the smallest normal need not immediately round to 0.

To obtain the **lowest finite negative number**, use **−Float.MAX_VALUE** or **−Double.MAX_VALUE**. **NEGATIVE_INFINITY** is smaller than every finite number, though it is not itself finite.

~~~java
float minPositive = Float.MIN_VALUE;       // nonzero positive
float mostNegativeFinite = -Float.MAX_VALUE;
boolean a = Float.MIN_VALUE > 0.0f;        // true
boolean b = Float.POSITIVE_INFINITY > Float.MAX_VALUE; // true
~~~

Results that are too large can overflow to Infinity; an undefined operation can produce NaN. **NaN == NaN** returns false, so check with **Float.isNaN/Double.isNaN**; use **isFinite** when only finite values are allowed.

**MIN_EXPONENT/MAX_EXPONENT** describe exponents of the finite normal range; they do not mean subnormals cannot reach as small as 2^−149 or 2^−1074.

Normal significand precision is **24 bits** for `float` and **53 bits** for `double`. The two fields **Float.PRECISION** and **Double.PRECISION** were added in **Java 19**; they **do not exist in Java 17**, even though the numbers 24 and 53 were already part of the specification. Examples compiled with **javac --release 17** must not access those two fields.

## 5. TYPE Differs from the Wrapper Class

**Integer.TYPE** points to the `Class` object representing the primitive **int**, which is **int.class**. **Integer.class** points to the class **java.lang.Integer**:

~~~java
boolean same = Integer.TYPE == int.class;        // true
boolean different = Integer.TYPE == Integer.class; // false
boolean primitive = Integer.TYPE.isPrimitive();  // true
boolean wrapper = Integer.class.isPrimitive();    // false
~~~

Corresponding `TYPE` fields:

| Wrapper | TYPE |
| --- | --- |
| Byte | byte.class |
| Short | short.class |
| Integer | int.class |
| Long | long.class |
| Float | float.class |
| Double | double.class |
| Character | char.class |
| Boolean | boolean.class |
| Void | void.class |

Example in reflection: **Math.class.getMethod("abs", Integer.TYPE)** looks up the overload taking primitive `int`; using `Integer.class` does not match the primitive signature. This snippet must handle **NoSuchMethodException** when placed in runnable code.

**Integer.TYPE** does not hold an integer; it holds a `Class` object. By contrast, **Integer.valueOf(42)** creates/obtains a wrapper holding the value 42. If you call **getClass()** on an `Integer` object, the result is `Integer.class`, not `Integer.TYPE`.

## 6. SIZE and BYTES

~~~java
int a = Byte.SIZE;        // 8 bits
int b = Short.BYTES;      // 2 bytes
int c = Integer.SIZE;     // 32 bits
int d = Long.BYTES;       // 8 bytes
int e = Double.SIZE;      // 64 bits
~~~

**SIZE/BYTES describe primitive data widths**. Do not infer that a `Long` object on the heap only consumes `Long.BYTES = 8` bytes: objects also carry headers, alignment, and other storage overhead depending on the JVM.

## 7. Character, Boolean, and Void

**Character.MIN_VALUE = '\u0000'**, **Character.MAX_VALUE = '\uFFFF'**. Numerically, the `char` range is **0..65535**, unsigned, with **SIZE = 16**, **BYTES = 2**.

~~~java
char first = Character.MIN_VALUE;
char last = Character.MAX_VALUE;
int lastCodeUnit = (int) last; // 65535
~~~

`char` is **one UTF-16 code unit**, not every Unicode code point. **Character.MAX_CODE_POINT = 0x10FFFF** is larger than `Character.MAX_VALUE`; code points outside the BMP are represented by surrogate pairs. `Character` also has **MIN_RADIX = 2**, **MAX_RADIX = 36**, and constants supporting radix/Unicode operations.

**Boolean.TRUE** and **Boolean.FALSE** are `Boolean` object constants; **Boolean.TYPE == boolean.class**. `Boolean` **does not have** `MIN_VALUE`, `MAX_VALUE`, `SIZE`, or `BYTES`, because `boolean` is not an integer.

**Void.TYPE == void.class** is used in reflection and describes the return type that holds no value. `Void` also **does not have** `MIN_VALUE`/`MAX_VALUE` or `SIZE`/`BYTES`.

## 8. Number, BigInteger, and BigDecimal

**Number** is an abstract class with numeric conversion methods such as `intValue()`, `longValue()`, and `doubleValue()`; it does not prescribe a numeric range or shared `MIN_VALUE`/`MAX_VALUE`/`TYPE` fields for all subclasses.

Two other important numeric classes in `java.math`:

- **BigInteger**: arbitrary-precision integers, with constants **ZERO**, **ONE**, **TWO** (Java 9+), and **TEN**.
- **BigDecimal**: decimal numbers represented by unscaled value and scale, with constants **ZERO**, **ONE**, and **TEN**. **BigDecimal.TWO** does not exist in Java 17; use `BigDecimal.valueOf(2)`.

~~~java
java.math.BigInteger beyondLong =
        java.math.BigInteger.valueOf(Long.MAX_VALUE)
            .add(java.math.BigInteger.ONE);
java.math.BigDecimal zero = java.math.BigDecimal.ZERO;
~~~

Do not refer to `BigInteger.MAX_VALUE` or `BigDecimal.MIN_VALUE`: they have no fixed value range like primitives. `BigDecimal` computations may need **MathContext/RoundingMode** to express precision and business rounding rules.

## 9. Standalone Runnable Java 17+ Example

Save as **WrapperConstantsDemo.java**:

~~~java
public class WrapperConstantsDemo {
    public static void main(String[] args) {
        System.out.println("Byte range: " + Byte.MIN_VALUE + " .. " + Byte.MAX_VALUE);
        System.out.println("Short range: " + Short.MIN_VALUE + " .. " + Short.MAX_VALUE);
        System.out.println("Integer range: " + Integer.MIN_VALUE + " .. " + Integer.MAX_VALUE);
        System.out.println("Long range: " + Long.MIN_VALUE + " .. " + Long.MAX_VALUE);

        System.out.println("Integer bits/bytes: " + Integer.SIZE + "/" + Integer.BYTES);
        System.out.println("Float exponents: " + Float.MIN_EXPONENT
                + " .. " + Float.MAX_EXPONENT);
        System.out.println("Double exponents: " + Double.MIN_EXPONENT
                + " .. " + Double.MAX_EXPONENT);

        System.out.println("Integer.TYPE == int.class: "
                + (Integer.TYPE == int.class));
        System.out.println("Integer.TYPE == Integer.class: "
                + (Integer.TYPE == Integer.class));
        System.out.println("Integer.TYPE name: " + Integer.TYPE.getName());
        System.out.println("Integer.class name: " + Integer.class.getName());
        System.out.println("Void.TYPE == void.class: "
                + (Void.TYPE == void.class));

        System.out.println("Character range: " + (int) Character.MIN_VALUE
                + " .. " + (int) Character.MAX_VALUE);
        System.out.println("Character bits/bytes: "
                + Character.SIZE + "/" + Character.BYTES);
        System.out.println("Boolean constants: "
                + Boolean.TRUE + "/" + Boolean.FALSE);

        System.out.println("Integer MAX + 1: " + (Integer.MAX_VALUE + 1));
        System.out.println("Byte MAX + 1: " + (Byte.MAX_VALUE + 1));
        System.out.println("Math.abs(Integer.MIN_VALUE): "
                + Math.abs(Integer.MIN_VALUE));
        System.out.println("Unsigned int max: "
                + Integer.toUnsignedString(-1));

        System.out.println("Float.MIN_VALUE: "
                + Float.toHexString(Float.MIN_VALUE));
        System.out.println("Float.MIN_NORMAL: "
                + Float.toHexString(Float.MIN_NORMAL));
        System.out.println("Double.MIN_VALUE: "
                + Double.toHexString(Double.MIN_VALUE));
        System.out.println("Double.MIN_NORMAL: "
                + Double.toHexString(Double.MIN_NORMAL));
        System.out.println("Float.MIN_VALUE > 0: "
                + (Float.MIN_VALUE > 0.0f));
        System.out.println("-Float.MAX_VALUE < Float.MIN_VALUE: "
                + (-Float.MAX_VALUE < Float.MIN_VALUE));
        System.out.println("Float infinity > MAX: "
                + (Float.POSITIVE_INFINITY > Float.MAX_VALUE));
        System.out.println("Float.isNaN: " + Float.isNaN(Float.NaN));
        System.out.println("NaN == NaN: " + (Float.NaN == Float.NaN));

        System.out.println("Integer extends Number: "
                + Number.class.isAssignableFrom(Integer.class));
        System.out.println("Character extends Number: "
                + Number.class.isAssignableFrom(Character.class));
    }
}
~~~

Compile/run:

~~~bash
javac --release 17 WrapperConstantsDemo.java
java WrapperConstantsDemo
~~~

Stdout:

~~~text
Byte range: -128 .. 127
Short range: -32768 .. 32767
Integer range: -2147483648 .. 2147483647
Long range: -9223372036854775808 .. 9223372036854775807
Integer bits/bytes: 32/4
Float exponents: -126 .. 127
Double exponents: -1022 .. 1023
Integer.TYPE == int.class: true
Integer.TYPE == Integer.class: false
Integer.TYPE name: int
Integer.class name: java.lang.Integer
Void.TYPE == void.class: true
Character range: 0 .. 65535
Character bits/bytes: 16/2
Boolean constants: true/false
Integer MAX + 1: -2147483648
Byte MAX + 1: 128
Math.abs(Integer.MIN_VALUE): -2147483648
Unsigned int max: 4294967295
Float.MIN_VALUE: 0x0.000002p-126
Float.MIN_NORMAL: 0x1.0p-126
Double.MIN_VALUE: 0x0.0000000000001p-1022
Double.MIN_NORMAL: 0x1.0p-1022
Float.MIN_VALUE > 0: true
-Float.MAX_VALUE < Float.MIN_VALUE: true
Float infinity > MAX: true
Float.isNaN: true
NaN == NaN: false
Integer extends Number: true
Character extends Number: false
~~~

Explanation: `Byte.MAX_VALUE + 1` is promoted to `int` so it equals 128; `Integer.MAX_VALUE + 1` overflows `int`; `Integer.TYPE` is `int.class`; `Float.MIN_VALUE` is still positive and smaller than `Float.MIN_NORMAL`. Hex representations of `float`/`double` display binary significand patterns with exponents via **toHexString**, convenient for inspecting very small numbers.

## 10. Proper Usage in Applications

| Goal | Appropriate constant/API |
| --- | --- |
| Check signed byte range before casting | `Byte.MIN_VALUE` / `Byte.MAX_VALUE` |
| Check `int` addition overflow | `Math.addExact`, combined with `Integer.MIN_VALUE`/`MAX_VALUE` range |
| Find smallest nonzero positive `double` | `Double.MIN_VALUE` |
| Find smallest positive normal `double` | `Double.MIN_NORMAL` |
| Find lowest finite negative `double` | `−Double.MAX_VALUE` |
| Distinguish NaN and infinity | `Double.isNaN` / `Double.isFinite` / `Double.isInfinite` |
| Obtain primitive `Class` for reflection | `Integer.TYPE`, `Long.TYPE`, or `primitive.class` |
| Get byte size of primitive `long` | `Long.BYTES` |
| Represent integers larger than `Long.MAX_VALUE` | `BigInteger` |
| Obtain exact decimal zero | `BigDecimal.ZERO` |

Carefully verify the problem's **input domain**. For example, monetary amounts need decimal rules; an 8-bit network protocol field may be an unsigned byte `0..255`, distinct from signed `Byte.MIN_VALUE..MAX_VALUE`. Choose constants based on data semantics rather than similar constant names.

## 11. Mistakes to Avoid

| Mistake | Correct explanation |
| --- | --- |
| `Float.MIN_VALUE` is the most negative `float` | It is the **smallest nonzero positive subnormal** number |
| `Double.MIN_VALUE` is the smallest normal | The smallest normal is **Double.MIN_NORMAL** |
| `Integer.MAX_VALUE` is the maximum unsigned `int` | It is the maximum signed `int` |
| `Integer.TYPE` equals `Integer.class` | `TYPE` is **int.class**; wrapper `Class` differs from primitive `Class` |
| `SIZE`/`BYTES` measure object size | They measure primitive data width |
| `Character.MAX_VALUE` is the maximum Unicode code point | It is the maximum UTF-16 code unit, `0xFFFF` |
| `Boolean` has `MIN_VALUE`/`MAX_VALUE` | `Boolean` only has topic-related constants `TRUE`/`FALSE`/`TYPE` |
| `Number` declares a shared `MAX_VALUE` | The `Number` class declares no such range constant |
| `BigInteger` has `MAX_VALUE` | `BigInteger` has no fixed maximum like `long` |
| `Float.PRECISION` is available in Java 17 | The `PRECISION` field was added in Java 19 |
| Assigning an `int` expression to `long` prevents `int` overflow | Widen before computing or use exact APIs |
| `Math.abs(Integer.MIN_VALUE)` is always non-negative | It stays `Integer.MIN_VALUE` because its negation cannot be represented |

## 12. Self-Check Exercises

**Exercise 1.** What value and expression type does `Byte.MAX_VALUE + 1` have?

**Answer:** **128**, type `int`, due to numeric promotion.

**Exercise 2.** How do `Integer.MAX_VALUE + 1` and `(long) Integer.MAX_VALUE + 1` differ?

**Answer:** The first overflows to `−2147483648`; the second evaluates to `2147483648L`.

**Exercise 3.** Which constant expression gives the lowest finite negative `float`?

**Answer:** **−Float.MAX_VALUE**, not `Float.MIN_VALUE`.

**Exercise 4.** What do `Integer.TYPE == int.class` and `Integer.TYPE == Integer.class` return respectively?

**Answer:** **true** and **false**.

**Exercise 5.** Why is `Character.MAX_VALUE` not equal to `Character.MAX_CODE_POINT`?

**Answer:** `char` is a 16-bit UTF-16 code unit, whereas Unicode code points can exceed `0xFFFF`.

**Exercise 6.** Can you directly access `Float.PRECISION` when compiling with Java 17?

**Answer:** No; that field was added in Java 19. The `float` significand width is still 24 bits per the specification.

**Exercise 7.** Does `BigInteger` have `MIN_VALUE` and `MAX_VALUE` like `Integer`?

**Answer:** No; it uses an arbitrary-precision integer representation whose practical limits depend on resources/implementation.

## 13. Reference Documentation

- [Byte API Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Byte.html), [Short API Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Short.html), [Integer API Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html), [Long API Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Long.html).
- [Float API Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Float.html), [Double API Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html).
- [Character API Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html), [Boolean API Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Boolean.html), [Void API Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Void.html).
- [Number API Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Number.html), [BigInteger API Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigInteger.html), [BigDecimal API Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html).
- [Java Language Specification SE 17 — Primitive Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.2) and [Conversions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html).