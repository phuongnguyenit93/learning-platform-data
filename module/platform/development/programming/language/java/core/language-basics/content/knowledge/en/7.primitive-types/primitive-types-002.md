# `byte`, `short`, `int`, and `long`: Bit Width and Value Range in Java 17+

## 1. The Four Signed Integer Types

Java has four **signed integral primitive types** commonly used to store counts, indices, status codes, and integer quantities: `byte`, `short`, `int`, `long`.

Their bit widths and value ranges are **fixed by the Java language specification**; they do not change across Windows/Linux or 32-bit/64-bit JVMs.

| Type | Value width | Minimum | Maximum | Limit constants |
|---|---:|---:|---:|---|
| `byte` | 8 bits | -128 | 127 | `Byte.MIN_VALUE`, `Byte.MAX_VALUE` |
| `short` | 16 bits | -32,768 | 32,767 | `Short.MIN_VALUE`, `Short.MAX_VALUE` |
| `int` | 32 bits | -2,147,483,648 | 2,147,483,647 | `Integer.MIN_VALUE`, `Integer.MAX_VALUE` |
| `long` | 64 bits | -9,223,372,036,854,775,808 | 9,223,372,036,854,775,807 | `Long.MIN_VALUE`, `Long.MAX_VALUE` |

Each type has `n` bits and represents signed integers in **two's complement**, so the value range is:

\[
-2^{n-1} \;\leq\; x \;\leq\; 2^{n-1}-1.
\]

For example, `byte` has 8 bits: the minimum value is \(-2^7=-128\), and the maximum is \(2^7-1=127\). The negative side has **one** more value than the positive side; this is why `Math.abs(Integer.MIN_VALUE)` does not produce a positive number in `int`.

**Note:** "8 bits" describes the **value width of the type**, not a guarantee that every `byte` variable in every object occupies exactly 1 byte of actual memory after JVM alignment, object packing, or optimization.

## 2. Declarations and Reading the Limits

~~~java
byte temperature = -20;
short altitudeMeters = 2_500;
int population = 1_000_000;
long distanceMeters = 12_000_000_000L;
~~~

Points to note:

- The `_` between digits is purely for readability: `1_000_000` equals `1000000`.
- Decimal literals like `1_000_000` **default to `int`**, provided they are within the valid range.
- For decimal values larger than `Integer.MAX_VALUE`, you must use the `L` suffix to create a **`long` literal**: `12_000_000_000L`. You should use an uppercase **`L`**, because lowercase `l` is easily mistaken for the digit 1.
- A `long` variable **cannot fix** an `int` literal that is already out of range. For example, `long x = 3_000_000_000;` does not compile, whereas `long x = 3_000_000_000L;` is valid.

The wrapper classes `Byte`, `Short`, `Integer`, and `Long` provide built-in `MIN_VALUE` and `MAX_VALUE` constants to avoid mistyping long numbers.


## 3. Signedness in Binary Data

With the same bit pattern, the result read can differ depending on how it is interpreted. The four integer types under discussion are **signed**. For example, a `byte` storing the 8 bits `11111111` is interpreted as `-1` in two's complement, whereas protocol data might treat the same eight bits as `255`:

~~~java
byte payload = (byte) 0xFF;
System.out.println(payload);                    // -1
System.out.println(Byte.toUnsignedInt(payload)); // 255
~~~

`Byte.toUnsignedInt` returns an `int`; it does not turn `byte` into an unsigned primitive type. The next lesson, **Signed Integers and Two's Complement Representation**, goes deeper into bit reading, sign extension, and bit shifting; here the focus is on the **storable range** so you declare and convert types correctly.

## 4. Widening Conversions: From Smaller to Larger

Java allows **widening primitive conversions** among the four integer types in the direction:

~~~text
byte → short → int → long
~~~

And you can go directly from a smaller type to any larger type to its right:

~~~java
byte count = 100;
short asShort = count;
int asInt = count;
long asLong = count;

System.out.println(asShort); // 100
System.out.println(asInt);   // 100
System.out.println(asLong);  // 100
~~~

In this chain, every `byte` value is represented exactly by `short`, `int`, and `long`. Widening **does not require an explicit cast**.

Distinguish the **type of the source value/variable** from the **target type**: `long result = 42;` is valid, but the literal `42` is still an `int` and is then widened to `long`.

## 5. Narrowing Conversions: Possible Data Loss

The reverse direction **is not automatic for all values**:

~~~java
int input = 130;
// byte narrowed = input; // COMPILE ERROR: int does not automatically narrow to byte
byte narrowed = (byte) input;
System.out.println(narrowed); // -126
~~~

`130` exceeds the `byte` range of -128 to 127. Casting `(byte)` keeps the low 8 bits; `130` has low bits `1000_0010`, which when interpreted as a signed `byte` becomes **-126**.

**A cast is not a safety check.** If a value can exceed the range, check it beforehand:

~~~java
static byte checkedByte(int value) {
    if (value < Byte.MIN_VALUE || value > Byte.MAX_VALUE) {
        throw new IllegalArgumentException("Out of byte range: " + value);
    }
    return (byte) value;
}
~~~

When exact values are required and data loss is unacceptable, keep the type as `int`/`long` instead of casting.

### Important Exception: Assigning an In-Range `int` Constant

Even though `127` is an `int` literal, Java allows **narrowing conversion of certain constant expressions** in assignment/initialization contexts if the value fits in the smaller type:

~~~java
byte maxByte = 127;      // Valid
short maxShort = 32767;  // Valid
// byte wrong = 128;     // ERROR: outside byte range
// short wrong2 = 40000; // ERROR: outside short range
~~~

However, when the expression is a regular `int` variable, the compiler cannot assume the runtime value is safe:

~~~java
int source = 127;
// byte b = source; // ERROR
byte b = (byte) source; // Explicit cast; the programmer is responsible for the range
~~~

This special case **does not mean** the literal `127` has type `byte`; the default literal type is still `int`.

## 6. Operations with `byte`/`short` Are Typically Promoted to `int`

An important trap: Java **promotes** `byte` and `short` to `int` in many arithmetic operations (*binary numeric promotion*).

~~~java
byte a = 100;
byte b = 20;

// byte sum = a + b; // ERROR: the expression a + b has type int
int sum = a + b;
System.out.println(sum); // 120
~~~

Similarly:

~~~java
short x = 10;
short y = 20;
int product = x * y;
System.out.println(product); // 200
~~~

If you are certain the result stays within the needed range, you can cast:

~~~java
byte a = 100;
byte b = 20;
byte sum = (byte) (a + b); // 120, still within byte range
~~~

However, casting can produce unexpected values:

~~~java
byte a = 120;
byte b = 20;
byte wrong = (byte) (a + b);
System.out.println(wrong); // -116, because 140 exceeds the byte range
~~~

A `short` variable does not make `short + short` compute in `short`. Conversely, an operation with a `long` operand is typically performed in `long` according to numeric promotion rules.


## 7. Overflow Happens Before Assigning the Result

Because value widths are fixed, ordinary integer addition/multiplication can exceed the range. An `int` operation does not automatically switch to `long` or throw an exception:

~~~java
long tooLate = 2_000_000_000 + 2_000_000_000;   // -294967296
long inTime = 2_000_000_000L + 2_000_000_000;   // 4000000000
~~~

In `tooLate`, the addition already ran in `int`; the assignment merely widened the **overflowed result**. When you want to report an error if the result does not fit the range, use `Math.addExact`, `Math.subtractExact`, or `Math.multiplyExact` with the appropriate `int`/`long` overload. These APIs throw `ArithmeticException` on overflow. How to read bits on overflow, the `MIN_VALUE` boundary, and bit shifting are explained in the next lesson.

## 8. Runnable Java 17 Program and Expected Output

Create a file named **`IntegerTypesDemo.java`**:

~~~java
public final class IntegerTypesDemo {
    private IntegerTypesDemo() {}

    static byte checkedByte(int value) {
        if (value < Byte.MIN_VALUE || value > Byte.MAX_VALUE) {
            throw new IllegalArgumentException("byte overflow: " + value);
        }
        return (byte) value;
    }

    public static void main(String[] args) {
        System.out.println("byte: " + Byte.MIN_VALUE + ".." + Byte.MAX_VALUE);
        System.out.println("short: " + Short.MIN_VALUE + ".." + Short.MAX_VALUE);
        System.out.println("int: " + Integer.MIN_VALUE + ".." + Integer.MAX_VALUE);
        System.out.println("long: " + Long.MIN_VALUE + ".." + Long.MAX_VALUE);

        byte small = 100;
        short widenedShort = small;
        int widenedInt = small;
        long widenedLong = small;
        System.out.println("widen: " + widenedShort + ","
                + widenedInt + "," + widenedLong);

        byte a = 100;
        byte b = 20;
        int promotedSum = a + b;
        System.out.println("byte + byte -> int: " + promotedSum);

        byte castValue = (byte) 130;
        System.out.println("cast 130 to byte: " + castValue);

        byte signedBits = (byte) 0xFF;
        System.out.println("signed byte: " + signedBits);
        System.out.println("unsigned view: "
                + Byte.toUnsignedInt(signedBits));

        int wrapped = Integer.MAX_VALUE + 1;
        System.out.println("int wrap: " + wrapped);

        long wrong = 2_000_000_000 + 2_000_000_000;
        long correct = 2_000_000_000L + 2_000_000_000;
        System.out.println("int overflow first: " + wrong);
        System.out.println("long addition: " + correct);

        System.out.println("checked byte: " + checkedByte(127));
        try {
            checkedByte(128);
        } catch (IllegalArgumentException ex) {
            System.out.println("range check: " + ex.getMessage());
        }

        try {
            Math.addExact(Integer.MAX_VALUE, 1);
        } catch (ArithmeticException ex) {
            System.out.println("Math.addExact: overflow detected");
        }

        System.out.println("abs int min: " + Math.abs(Integer.MIN_VALUE));
    }
}
~~~

Compile and run with **JDK 17+** in the directory containing the file.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 IntegerTypesDemo.java
java -cp . IntegerTypesDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\IntegerTypesDemo.java
java -cp . IntegerTypesDemo
~~~

**Expected output:**

~~~text
byte: -128..127
short: -32768..32767
int: -2147483648..2147483647
long: -9223372036854775808..9223372036854775807
widen: 100,100,100
byte + byte -> int: 120
cast 130 to byte: -126
signed byte: -1
unsigned view: 255
int wrap: -2147483648
int overflow first: -294967296
long addition: 4000000000
checked byte: 127
range check: byte overflow: 128
Math.addExact: overflow detected
abs int min: -2147483648
~~~

Important lines:

- The first four lines read value ranges from **wrapper constants**; you do not have to manually enter numbers to guess the type limits.
- `byte + byte -> int` shows the expression type after numeric promotion.
- `cast 130 to byte` illustrates narrowed data; `unsigned view` is simply a way of interpreting the bits.
- `int overflow first` and `long addition` distinguish **computing in int** from **computing in long**.
- `Math.addExact` reports an error instead of silently using the overflowed value.

The example is self-contained and requires no libraries outside the JDK.


## 9. Type Width Is a Data Constraint

Choose `byte` when exchanging **a binary octet**, but remember to handle signed/unsigned interpretation according to the protocol. Choose `short` if a format specification actually requires a 16-bit signed integer; do not use `short` merely because a current count is small. `int` usually matches common Java indices and APIs; `long` is suitable when the data domain or intermediate calculations may exceed `int`. When **even `long` is not enough** and exact integers are needed, `BigInteger` is the appropriate reference type.

A wide type does not replace business validation: `-5` fits within the `int` range, yet it is not necessarily valid for a product quantity. The lesson **Choosing Types Based on Data Range and Computational Requirements** combines width, data units, and precision into a single design decision.

## 10. Common Mistakes

| Situation | Cause | How to fix |
|---|---|---|
| `byte n = 128;` | 128 exceeds byte range | Choose `short`/`int` if the value 128 is needed |
| `short n = 40000;` | 40000 exceeds short range | Use `int` |
| `long n = 3000000000;` | Default decimal literal is int and too large | `3000000000L` |
| `byte sum = a + b;` | `a + b` is promoted to int | Store in `int` or cast with range checking |
| `byte n = (byte) 130;` | Cast truncates bits, yielding -126 | Check range before casting |
| `long n = 2_000_000_000 + 2_000_000_000;` | int overflow before assignment | Put `L` on an operand before addition |
| `Integer.MAX_VALUE + 1` | Wraps around to `Integer.MIN_VALUE` | `Math.addExact` or change type range |
| `Math.abs(Integer.MIN_VALUE)` | Positive absolute value cannot be represented in int | Check boundary values, handle with an appropriate type |

Note a practical limitation: `Math.addExact` detects overflow of the type being used; if an expression has **already overflowed before being passed** into `Math.addExact`, the API cannot know the original intent. Choose the right operands/types before computing.

## 11. Exercises with Answers

### Exercise A — Value Range

Can an 8-bit `byte` store `127`, `128`, `-128`, `-129`?

**Answer:** `127` and `-128` are within range; `128` and `-129` are outside the `byte` range.

### Exercise B — Widening Conversion

~~~java
short s = 32000;
int n = s;
long m = n;
System.out.println(m);
~~~

**Answer:** prints `32000`. The value fits in `short` and is widened accurately to `int`, then `long`.

### Exercise C — Byte Addition

~~~java
byte a = 120;
byte b = 20;
// byte sum = a + b;
int sum = a + b;
System.out.println(sum);
~~~

**Answer:** `140`. The expression `a+b` has type `int`; declaring `byte sum` causes a compile error even if you know `byte` syntax.

### Exercise D — `int` Overflow Before Assigning to `long`

~~~java
long a = Integer.MAX_VALUE + 1;
long b = (long) Integer.MAX_VALUE + 1;
System.out.println(a);
System.out.println(b);
~~~

**Answer:**

~~~text
-2147483648
2147483648
~~~

In `a`, the addition uses `int` and overflows; in `b`, the cast to `long` happens before the addition.

### Exercise E — Signed `byte` and Unsigned View

~~~java
byte b = (byte) 255;
System.out.println(b);
System.out.println(Byte.toUnsignedInt(b));
~~~

**Answer:** `-1` and `255` respectively; the 8-bit pattern is still `11111111`, only the interpretation differs.

## 12. Self-Assessment Checklist

- [ ] Remember the fixed widths: `byte` 8, `short` 16, `int` 32, `long` 64 bits.
- [ ] Look up `MIN_VALUE`/`MAX_VALUE` accurately instead of guessing boundary values.
- [ ] Understand the signed two's complement range: \(-2^{n-1}\) to \(2^{n-1}-1\).
- [ ] Know that widening `byte → short → int → long` requires no cast.
- [ ] Know that narrowing casts can lose data; `(byte)130 == -126`.
- [ ] Distinguish the in-range `int` constant expression assignment exception from casting a runtime `int` variable.
- [ ] Understand that `byte`/`short` arithmetic typically uses `int`.
- [ ] Know that `int`/`long` can overflow without throwing an error.
- [ ] Use the `L` suffix when an integer literal needs type `long`.
- [ ] Compile/run `IntegerTypesDemo.java` yourself and verify the output.

**Conclusion:** The bit widths and value ranges of Java's four signed integer types are **fixed**. Choose a type according to actual requirements, understand that operations can be promoted to `int` or `long`, and validate conversions/overflows at points where data could be corrupted.
