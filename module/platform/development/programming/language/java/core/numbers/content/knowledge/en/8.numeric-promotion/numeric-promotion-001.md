# Unary numeric promotion in Java

## 1. Concept and goal

**Unary numeric promotion** is the numeric type conversion rule that Java applies to **one operand at a time** in contexts specified by the Java Language Specification (JLS). Its goal is to produce an appropriate data type so that the operator or expression can perform the operation.

Key point to remember: **byte, short, and char are promoted to int** in unary numeric promotion. This often causes the result of **+b**, **-s**, **~c**, or **b << 1** to have type **int**, even if the original variable is only a byte, short, or char. The rule can also **unbox** wrapper types such as **Byte** or **Long**.

Example:

~~~java
byte b = 5;
int x = +b;       // Valid: +b has type int and value 5
int y = -b;       // Valid: -b has type int and value -5
int z = ~b;       // Valid: ~b is computed over 32-bit int
// byte bad = +b; // Compile error: int result is not automatically narrowed to byte
~~~

In the context above, the **+** sign is the unary plus operator, not binary addition. All examples in this lesson use **Java 17+** rules.

## 2. Type conversion rules

The table below applies when an operand is actually in a **unary numeric promotion context**:

| Original operand type | Conversion | Type after promotion |
| --- | --- | --- |
| **byte** | Widening primitive conversion | **int** |
| **short** | Widening primitive conversion | **int** |
| **char** | Widening primitive conversion | **int** |
| **int** | Unchanged | **int** |
| **long** | Unchanged | **long** |
| **float** | Unchanged | **float** |
| **double** | Unchanged | **double** |
| **Byte**, **Short**, **Character**, **Integer** | Unboxing, then widening to int if needed | **int** |
| **Long** | Unboxing | **long** |
| **Float** | Unboxing | **float** |
| **Double** | Unboxing | **double** |

**boolean**, **Boolean**, and **String** are not valid numeric operands for unary numeric promotion. Operators also have their own constraints: for example, **~** only accepts integral types after promotion (**int** or **long**), so **~1.5f** is invalid even though **float** is a numeric type.

Not every value is converted to **int**. **long**, **float**, and **double** keep their types unless another rule from the surrounding context applies. Unary numeric promotion also **does not automatically widen int to long just because the receiving variable is long**.

### Order of application

1. Inspect the compile-time type of the operand expression.
2. If it is a numeric wrapper, perform **unboxing**. When the wrapper value is **null**, unboxing throws a **NullPointerException** at runtime.
3. If the result has type **byte**, **short**, or **char**, widen it to **int**; if it is already **int**, **long**, **float**, or **double**, leave it unchanged.
4. Execute the operator or use the expression according to the context's semantics.
5. Afterward, if the result is assigned to a variable, apply the separate **assignment conversion rules**; the promotion step is not automatically reversed.

Diagram:

~~~text
byte / short / char -------------> int
int -----------------------------> int
long ----------------------------> long
float ---------------------------> float
double --------------------------> double

Byte / Short / Character / Integer --unboxing--> int
Long ------------------------------unboxing--> long
Float -----------------------------unboxing--> float
Double ----------------------------unboxing--> double
~~~

**Widening** in this step does not lose the integer value of byte/short/char. However, if a subsequent calculation overflows the limits of **int** or **long**, that is an arithmetic issue after promotion, not data loss during the widening step itself.

## 3. Applicable contexts

According to the JLS, unary numeric promotion occurs in the following cases:

| Context | Example | Key point |
| --- | --- | --- |
| Unary plus operator **+** | **+someByte** | Result has the promoted type |
| Unary minus operator **-** | **-someShort** | Negates after promotion |
| Bitwise complement operator **~** | **~someByte** | Operand must be int/long after promotion |
| Bitwise shift operators **<<**, **>>**, **>>>** | **someByte << distance** | **Each operand is promoted independently** |
| Array creation size expression | **new int[someByte]** | Size must have type **int** after promotion |
| Array index expression | **array[someChar]** | Index must have type **int** after promotion |

Array creation/access cases have an additional check: **new int[1L]** and **array[1L]** are invalid because **long** is not automatically converted to **int** just to serve as a size or index.

Note that an operator that looks "unary" **does not necessarily** use the same rules. **++** and **--** are operators with their own variable-update semantics; their result types must not be equated with **+**, **-**, or **~**. Section 8 explains this case.

## 4. Unary plus operator: +x

**+x** computes the value after promotion and preserves its sign and magnitude. It can **change the static type** of the expression:

~~~java
byte b = 12;
short s = 300;
char c = 'A';

int a = +b;  // 12
int q = +s;  // 300
int r = +c;  // 65 (UTF-16 code of 'A')
~~~

**+b** and **b** have the same value but different expression types: **b** is byte, **+b** is int. This affects assignments, method overloading, type inference with **var**, and subsequent operations.

~~~java
byte b = 12;
var raw = b;        // raw has type byte
var promoted = +b;  // promoted has type int
~~~

The binary addition operator **a + b** follows **binary numeric promotion** rules, which differ from **+a** here. When strings are involved, **"x" + a** can instead be string concatenation, not unary numeric promotion.

## 5. Unary minus operator: -x

With **-x**, Java promotes the operand first and then takes its negation. This is why the smallest byte value can be negated without overflowing the byte type:

~~~java
byte b = -128;
int opposite = -b;  // 128, type int
~~~

The negation above takes place in int, so the result **128** is valid. **char** is a 16-bit unsigned integer type with values from **0** to **65535**, yet it is still promoted to a signed int:

~~~java
char c = '\uFFFF';   // numeric value 65535
int value = +c;      // 65535
int negative = -c;   // -65535
~~~

There is no "negative char code" here: **-c** is a negative **int** after the operation. The original char value is unchanged.

### Overflow when negating the smallest int/long

The width of int or long is finite. The negation of **Integer.MIN_VALUE** (−2³¹) cannot be represented in int. Java produces the overflow result using two's complement arithmetic:

~~~java
int x = Integer.MIN_VALUE;
System.out.println(-x); // -2147483648
~~~

**-x** is still int and still equals **Integer.MIN_VALUE**; no ArithmeticException is thrown. **-Long.MIN_VALUE** exhibits the same behavior for long. If you genuinely need the positive value of the smallest int, you can widen **before** negating:

~~~java
long positive = -(long) Integer.MIN_VALUE; // 2147483648L
~~~

Whereas **long wide = -Integer.MIN_VALUE;** already performs the negation in int before assigning to long, so it receives a negative value and does not prevent overflow.

For **float/double**, unary minus follows floating-point sign semantics, including **+0.0** and **-0.0**. For example, **1.0 / -0.0** is **-Infinity**, unlike integer division by 0.

## 6. Bitwise complement operator: ~x

**~** inverts every bit of the operand **after** promotion. The result has type **int** or **long**; **~byte**, **~short**, and **~char** all produce a 32-bit int.

For **byte b = -5**, promoting from byte to int sign-extends the value:

~~~text
byte -5 (8 bits):         1111 1011
int -5  (32 bits): 11111111 11111111 11111111 11111011
~int -5:           00000000 00000000 00000000 00000100
Final value:       4
~~~

Therefore **~b** produces **4**, not a negative byte or an 8-bit preserved value. For any int, the arithmetic identity **~x == -x - 1** holds under 32-bit int semantics.

If you want to compute the complement within **8 unsigned bits**, **mask** the result back to 8 bits:

~~~java
byte b = 5;
int complement32 = ~b;           // -6
int complement8 = (~b) & 0xFF;  // 250 (0xFA)
~~~

The **& 0xFF** operation here uses the bitwise AND operator; it limits the resulting bit pattern to 8 bits. Do not treat this as converting to a signed byte type, because **250** is outside Java's **byte** range.

~~~java
// Valid
int result = ~((short) 0x00FF);

// Invalid: ~ requires an integral type after promotion
// float f = ~1.5f;
~~~

## 7. Bitwise shifts: each operand is promoted independently

Java supports three shift operators: **<<** (left shift), **>>** (signed right shift), and **>>>** (unsigned right shift). For each expression **left << distance**, **left >> distance**, and **left >>> distance**, Java applies unary numeric promotion **separately to left and distance**.

- If the left operand is **byte**, **short**, **char**, or **int**, the shift result has type **int**.
- If the left operand is **long**, the result has type **long**.
- The right operand specifies the shift distance and can be int/long after promotion. **A long on the right does not turn the left side into long**.
- Both operands, after promotion, must be integral types; **float** or **double** are invalid for bitwise shifts.
- With an **int** left operand, only the lowest 5 bits of the shift distance are used: the effective distance is 0 to 31 (**distance & 31**).
- With a **long** left operand, only the lowest 6 bits of the shift distance are used: the effective distance is 0 to 63 (**distance & 63**).

Example:

~~~java
byte b = 1;
int a = b << 1;         // 2, type int
int c = b << 33L;       // 2, because 33 & 31 == 1
long d = 1L << 33L;     // 8589934592L, type long
long e = b << 33L;      // value 2, int is widened to long AFTER the shift
~~~

Do not infer the type of the shift expression from the **long e** variable on the left side of the equals sign: **b << 33L** itself is still **int**.

### Right-shifting a negative byte: the sign extension trap

~~~java
byte b = -5;
int x = b >>> 1;           // 2147483645
int y = (b & 0xFF) >>> 1;  // 125
~~~

In the first operation, **b** is sign-extended from **0xFB** to int **0xFFFFFFFB** before the 1-bit logical right shift, yielding **0x7FFFFFFD** = **2147483645**. In the second operation, **b & 0xFF** produces int **251** (0x000000FB), which right-shifts to **125**. The intent to process an unsigned byte value should be explicit and masked before applying the shift.

**Note**: the **&** in the example is a binary operator with its own numeric promotion mechanism; it produces an int value for further manipulation. Meanwhile, the shift operator applies unary numeric promotion to each operand.

## 8. Array sizes and indices

The size in **new T[size]** and the index in **array[index]** are contexts that use unary numeric promotion. Thus byte, short, char, and their corresponding wrappers can be used as an index or size after being promoted to int:

~~~java
byte size = 3;
char index = 1;
int[] data = new int[size]; // size is promoted to int
data[index] = 42;           // index is promoted to int
~~~

Do not assume that Java allows arbitrary floating-point or unrestricted integer types here:

~~~java
// Does not compile:
// int[] data = new int[3L];
// int value = data[1L];
// int[] other = new int[2.0];
// int element = data[1.5f];
~~~

The index must be **int** after promotion. For values less than 0 or exceeding the array length, the code may still compile but will fail at runtime (**NegativeArraySizeException** when creating an array with a negative size; **ArrayIndexOutOfBoundsException** when accessing an out-of-bounds index).

## 9. Unary promotion differs from binary promotion, assignment, and ++/--

These three mechanisms are related but not interchangeable.

### Unary and binary numeric promotion

~~~java
byte a = 10;
short b = 20;

int first = +a;    // unary promotion: byte -> int
int second = a + b; // binary promotion: byte + short -> int
~~~

With binary numeric promotion, Java inspects both operands to determine a common operation type; it can be **double**, **float**, or **long** depending on the operands. With unary numeric promotion, Java converts **one operand at a time**; there is no common type resolution between the two sides of a bitwise shift.

### Assignment does not automatically narrow an int result

~~~java
byte b = 10;
int ok = +b;         // Valid

// Does not compile:
// byte invalid1 = +b;
// byte invalid2 = -b;
// byte invalid3 = b << 1;

byte explicit = (byte) (+b); // With explicit cast
~~~

Casting an int result to byte can discard high bits or turn a positive number negative when it exceeds the range −128..127. Only cast when the range rules have been verified.

**Constant-related exception:** an **int** **constant expression** whose value falls within the byte/short/char range can be assigned thanks to **constant narrowing**:

~~~java
byte a = +12;             // Valid: int constant 12 is within byte range
final byte b = 12;
byte c = +b;              // Valid: +b is a constant expression with value 12
byte d = 12;
// byte e = +d;           // Error: d is not a final constant variable
// byte f = +128;         // Error: constant 128 exceeds byte range
~~~

Do not conclude that "unary plus preserves the byte type" from the example **byte a = +12**: the expression **+12** still has type int, and narrowing is only permitted in a constant assignment context.

### ++, --, and compound assignment

The **++** and **--** operators mutate a **variable** and have a result type equal to that variable's type. They use update semantics and convert the result back to the variable's type, unlike **+b** or **-b** which simply produce a new value.

~~~java
byte b = 127;
b++;                     // Valid; b becomes -128 due to narrowing and overflow
byte after = b;          // Valid
b += 1;                  // Valid; compound assignment automatically converts result to byte
// b = b + 1;            // Error: b + 1 has type int
~~~

**b++** is not "unary numeric promotion keeping byte as byte"; update operators have their own specification, involving an intermediate addition and a narrowing step when storing back into the variable. Be sure to distinguish the **old value** of postfix **b++** from the **new value** of prefix **++b**.

## 10. Wrappers and NullPointerException

Unary numeric promotion can perform **unboxing**:

~~~java
Byte b = (byte) 12;
Short s = (short) 3;
Character c = 'A';
Integer i = 20;
Long l = 40L;
Float f = 2.5f;
Double d = 3.5;

int a = +b;  // 12: Byte -> byte -> int
int n = -s;  // -3: Short -> short -> int
int m = +c;  // 65: Character -> char -> int
int p = +i;  // 20: Integer -> int
long q = +l; // 40L: Long -> long
float r = -f;   // -2.5f
double t = -d;  // -3.5
~~~

If the wrapper is null, unboxing occurs before the operator can compute a value:

~~~java
Byte missing = null;
// int x = +missing; // Compiles, throws NullPointerException at runtime
~~~

Clarify the distinction between a **compile-time error due to incompatible types** and a **runtime error when unboxing null**. If data is nullable, check conditions or use a business-appropriate default value before the operation. Never implicitly assume a value of 0.

## 11. Comprehensive Java 17+ example with verified output

Save the exact code below as **UnaryPromotionDemo.java**:

~~~java
public class UnaryPromotionDemo {
    static String type(int value) { return "int"; }
    static String type(long value) { return "long"; }
    static String type(float value) { return "float"; }
    static String type(double value) { return "double"; }

    public static void main(String[] args) {
        byte b = -5;
        short s = 300;
        char c = 'A';
        long l = 8L;
        float f = 1.5f;
        double d = 2.25;

        System.out.println("+byte: " + (+b) + " / " + type(+b));
        System.out.println("-short: " + (-s) + " / " + type(-s));
        System.out.println("-char: " + (-c) + " / " + type(-c));
        System.out.println("~byte: " + (~b) + " / " + type(~b));
        System.out.println("+long: " + (+l) + " / " + type(+l));
        System.out.println("-float: " + (-f) + " / " + type(-f));
        System.out.println("+double: " + (+d) + " / " + type(+d));

        int shifted = b >>> 1;
        int masked = (b & 0xFF) >>> 1;
        int left = ((byte) 1) << 33L;
        long wideLeft = 1L << 33L;
        System.out.println("negative byte >>> 1: " + shifted);
        System.out.println("(byte & 0xFF) >>> 1: " + masked);
        System.out.println("byte << 33L: " + left + " / " + type(left));
        System.out.println("1L << 33L: " + wideLeft + " / " + type(wideLeft));

        byte length = 2;
        char index = 1;
        int[] numbers = new int[length];
        numbers[index] = 99;
        System.out.println("array: length=" + numbers.length + ", a[1]=" + numbers[1]);

        Byte boxed = (byte) 12;
        Long boxedLong = 13L;
        System.out.println("+Byte: " + (+boxed) + " / " + type(+boxed));
        System.out.println("-Long: " + (-boxedLong) + " / " + type(-boxedLong));

        byte edge = 127;
        edge++;
        System.out.println("byte after ++: " + edge);
        System.out.println("-Integer.MIN_VALUE: " + (-Integer.MIN_VALUE));
        System.out.println("1.0 / (-0.0): " + (1.0 / -0.0));
    }
}
~~~

Compile with JDK 17 or higher:

~~~bash
javac UnaryPromotionDemo.java
java UnaryPromotionDemo
~~~

Stdout output:

~~~text
+byte: -5 / int
-short: -300 / int
-char: -65 / int
~byte: 4 / int
+long: 8 / long
-float: -1.5 / float
+double: 2.25 / double
negative byte >>> 1: 2147483645
(byte & 0xFF) >>> 1: 125
byte << 33L: 2 / int
1L << 33L: 8589934592 / long
array: length=2, a[1]=99
+Byte: 12 / int
-Long: -13 / long
byte after ++: -128
-Integer.MIN_VALUE: -2147483648
1.0 / (-0.0): -Infinity
~~~

In the example, the **type(int)**, **type(long)**, **type(float)**, and **type(double)** methods are overloaded to reveal the **static type** that the compiler chooses for the result; this is not a type-checking technique to use in regular applications. The printed string containing **+byte** is just a label, while the actual promotion happens inside **(+b)**.

Points to explain to yourself after running:

- **-char** produces **-65 / int**, because char 'A' is promoted to int 65 before negation.
- **~byte** produces **4 / int**, because byte -5 is sign-extended to int before inverting all 32 bits.
- **byte << 33L** produces **2 / int**; the long type of the shift distance does not make the left side long.
- **byte after ++** produces **-128**, because the increment stores a narrowed result back into the byte variable.
- **-Integer.MIN_VALUE** remains the smallest negative int; the operation does not automatically widen to long.

## 12. Common pitfalls and fixes

| Common mistake | Cause | Resolution |
| --- | --- | --- |
| Assigning **+byte**, **-short**, or **~char** to a variable of the same small type | The expression result has been promoted to **int** | Use an int variable or cast with range checking |
| Thinking **+x** always preserves the type of **x** | Unary plus performs numeric promotion | Check the operand type before guessing the expression type |
| Seeing **byte b = +12** compile and concluding **+b** returns byte | An int constant is narrowed via constant narrowing | Distinguish expression type from assignment conversion |
| Thinking **byte << long** has a long result | Both shift operands are promoted independently | Inspect the **left** operand's type |
| Right-shifting **>>>** a negative byte and getting a very large positive number | Sign extension before the 32-bit shift | For unsigned bytes, consider **b & 0xFF** |
| Using **~byte** and expecting only 8 bits | Complement operator applies to **32-bit int** | Mask with **& 0xFF** when an 8-bit pattern is needed |
| Passing long as an array size or index | Rules require int after promotion | Convert with bounds checking before access |
| Using a null wrapper with unary + or - | Unboxing throws **NullPointerException** | Handle null before numeric operations |
| Thinking **++byte** always returns int like **+byte** | **++** has its own variable-update rules | Distinguish value-reading operations from update operations |
| Thinking **-Integer.MIN_VALUE** is a positive number | Overflow within the int range | Widen to long **before** negating |

When reading a numeric expression, follow this order: **original type of each operand → whether unboxing or promotion occurs → operation type → operation value → conversion in assignment**. This analysis is especially helpful when encountering errors like "possible lossy conversion from int to byte" or unexpected shift results.

## 13. Self-check exercises (with answers)

**Exercise 1.** Given **byte b = 100;**. What are the types and values of **+b**, **-b**, and **~b** respectively?

Answer: all have type **int**; values are **100**, **-100**, and **-101** respectively. For int, **~100 == -101**.

**Exercise 2.** Does **byte a = 5; byte x = +a;** compile? What about **byte x = +5;**?

Answer: the first **does not**, because **+a** is an int and not a constant expression; the second **does**, because **+5** is an int constant within the byte range and is narrowed upon assignment.

**Exercise 3.** What value does **short s = 1; long result = s << 32L;** produce?

Answer: **1**. The promoted left type is int, so the effective shift distance is **32 & 31 = 0**; the expression returns int 1 before being widened to long for assignment.

**Exercise 4.** What value does **char c = '\uFFFF'; int x = -c;** produce?

Answer: **-65535**. The char is converted to int 65535 and then negated; there is no step interpreting char as a signed short.

**Exercise 5.** Does **Byte x = null; int y = +x;** fail at compile time or at runtime?

Answer: it compiles **validly**, and throws **NullPointerException** at runtime when unboxing x.

**Exercise 6.** Why is **byte b = 127; b++;** valid, whereas **b = b + 1;** is not?

Answer: **++** updates and converts the result back to byte according to its own rules; **b + 1** has type int due to binary numeric promotion, so a normal assignment to byte is rejected.

## 14. References

- [Java Language Specification, Java SE 17 — §5.6 Numeric Contexts](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.6): defines unary numeric promotion, unboxing, widening, and applicable contexts.
- [JLS Java SE 17 — §15.15 Unary Operators](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.15): semantics of unary +, -, ~ and how ++/-- differ.
- [JLS Java SE 17 — §15.19 Shift Operators](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.19): result types, independent promotion of both operands, and shift distance masking.
- [JLS Java SE 17 — §5.2 Assignment Contexts](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.2): assigning constant int expressions to byte/short/char.