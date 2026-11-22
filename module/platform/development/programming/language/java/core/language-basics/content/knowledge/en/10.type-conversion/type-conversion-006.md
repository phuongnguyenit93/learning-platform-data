# Unary Numeric Promotion and Binary Numeric Promotion — Java 17+

In Java, **numeric promotion** refers to implicit conversions that the language applies to determine the type used when evaluating a numeric expression. Two mechanisms need to be distinguished:

- **Unary numeric promotion**: promotes the type of **a single numeric operand** in specified contexts, such as unary operators `+`, `-`, `~`.
- **Binary numeric promotion**: brings **two numeric operands** to a common type before certain binary operations, such as numeric addition `+`, multiplication `*`, numeric comparison `<`.

Both are decided by the compiler from the **type of the expression**, not from the actual runtime value. Therefore, two `byte` variables added together have a result type of `int`, even when the sum is small and fits within the `byte` range.

## 1. Unary numeric promotion: one operand

For an expression subject to *unary numeric promotion*:

| Initial type | Type after promotion |
| --- | --- |
| `byte` | `int` |
| `short` | `int` |
| `char` | `int` |
| `int` | `int` |
| `long` | `long` |
| `float` | `float` |
| `double` | `double` |

For suitable numeric wrappers such as `Byte`, `Short`, `Character`, or `Integer`, Java can **unbox** first and then apply promotion; a `null` wrapper can cause a `NullPointerException`.

Example:

~~~java
byte b = 100;
int a = +b; // Unary +: byte -> int.
int c = -b; // Unary -: byte -> int, result -100.

short min = Short.MIN_VALUE; // -32768.
int positive = -min;        // int 32768, not short.

byte zero = 0;
int inverted = ~zero;       // int -1, because ~ applies to 32-bit int.
~~~

**Common pitfall:** `-Short.MIN_VALUE` does not overflow `short`, because the operand has already been promoted to `int`. However, `-Integer.MIN_VALUE` remains an `int` operation; the result overflows and wraps back to `Integer.MIN_VALUE`. Promotion **does not automatically detect overflow**.

With `char`, the 16-bit unsigned value is promoted to `int`. For example, `'A' + 1` gives the numeric value `66` of type `int`, **not** `char 'B'`.

## 2. Binary numeric promotion: two operands

When a context requires *binary numeric promotion*, Java converts operands to a common type in order of precedence:

1. If either is `double`, the other operand is converted to `double`.
2. Otherwise, if either is `float`, the other operand is converted to `float`.
3. Otherwise, if either is `long`, the other operand is converted to `long`.
4. Otherwise, **both become `int`** (including `byte`, `short`, `char`).

| Expression | Type used for evaluation | Why |
| --- | --- | --- |
| `byte + byte` | `int` | Small integer types are promoted to `int` |
| `short + char` | `int` | Both are promoted to `int` |
| `int + long` | `long` | `long` takes precedence over `int` |
| `long + float` | `float` | `float` takes precedence over `long` |
| `float + double` | `double` | `double` has the highest precedence |
| `int < double` | Both operands convert to `double` | Comparison result is **`boolean`** |
| `int == long` | Both operands convert to `long` | Comparison result is **`boolean`** |

The precedence order above is a **type rule**, not a guarantee of value preservation: converting a very large `long` to `float` or `double` can **lose precision**.

### Not every binary operator uses binary numeric promotion

- `"n=" + 1 + 2` is **string concatenation** once the first operand is `String`; the result is `"n=12"`. `"n=" + (1 + 2)` yields `"n=3"`.
- `boolean && boolean` or `boolean || boolean` are logical operations, **not** numeric operations.
- Bitwise shift operators `<<`, `>>`, `>>>` **do not apply binary numeric promotion to the two operands**: *each* operand receives **unary numeric promotion** separately. The result type is the promoted type of the **left-hand operand**.

## 3. Runnable Java 17+ program

Create the file **`NumericPromotionDemo.java`** with the following content:

~~~java
public class NumericPromotionDemo {
    private static void show(String label, Object value) {
        System.out.println(label + "=" + value
                + " (boxedType=" + value.getClass().getSimpleName() + ")");
    }

    public static void main(String[] args) {
        byte first = 100;
        byte second = 27;
        short minimum = Short.MIN_VALUE;
        byte zero = 0;
        char letter = 'A';

        show("bytePlusByte", first + second);
        show("unaryPlusByte", +first);
        show("unaryMinusShort", -minimum);
        show("unaryComplementByte", ~zero);
        show("charPlusOne", letter + 1);
        show("shortPlusChar", (short) 300 + letter);

        show("intPlusLong", 2 + 3L);
        show("floatPlusLong", 0.5f + 2L);
        show("doublePlusFloat", 1.25d + 0.5f);

        short count = 3;
        show("shiftShort", count << 2);
        show("shiftIntByLong", 1 << 2L);
        show("shiftLongByInt", 1L << 2);

        show("intDivision", 5 / 2);
        show("divisionWithDouble", 5 / 2.0);

        byte compound = 100;
        compound += 200;
        show("compoundByte", compound);

        Integer wrapper = 4;
        show("unboxPlusLong", wrapper + 2L);

        System.out.println("numericComparison=" + (first < 200L));
        System.out.println("stringConcat=" + "n=" + 1 + 2);
        System.out.println("stringGrouped=" + "n=" + (1 + 2));

        Integer missing = null;
        try {
            show("missingPlusOne", missing + 1);
        } catch (NullPointerException ex) {
            System.out.println("unboxNull=NullPointerException");
        }
    }
}
~~~

Open PowerShell (Windows) or Bash (Linux/macOS) in the directory containing the file and use **JDK 17+**:

~~~bash
java -version
javac -version
javac -encoding UTF-8 NumericPromotionDemo.java
java NumericPromotionDemo
~~~

**Exact expected output** of the `java NumericPromotionDemo` command (excluding the JDK version lines):

~~~text
bytePlusByte=127 (boxedType=Integer)
unaryPlusByte=100 (boxedType=Integer)
unaryMinusShort=32768 (boxedType=Integer)
unaryComplementByte=-1 (boxedType=Integer)
charPlusOne=66 (boxedType=Integer)
shortPlusChar=365 (boxedType=Integer)
intPlusLong=5 (boxedType=Long)
floatPlusLong=2.5 (boxedType=Float)
doublePlusFloat=1.75 (boxedType=Double)
shiftShort=12 (boxedType=Integer)
shiftIntByLong=4 (boxedType=Integer)
shiftLongByInt=4 (boxedType=Long)
intDivision=2 (boxedType=Integer)
divisionWithDouble=2.5 (boxedType=Double)
compoundByte=44 (boxedType=Byte)
unboxPlusLong=6 (boxedType=Long)
numericComparison=true
stringConcat=n=12
stringGrouped=n=3
unboxNull=NullPointerException
~~~

**How to read `boxedType` in the output:** Numeric expressions are passed to the `Object value` parameter of `show`, so Java performs **autoboxing** of the primitive result into a wrapper (`int -> Integer`, `long -> Long`, etc.). Thus, `value.getClass().getSimpleName()` lets us observe the primitive type of the **expression result prior to boxing**. This does not mean all numeric values in Java are natively objects.

### Analyzing the result groups

**Unary operations:** `+first`, `-minimum`, and `~zero` all produce `int`. In particular, `~zero` is the bitwise complement of **32-bit `int` 0**, yielding `-1`.

**Binary operations:** `first + second` is `int 127`; `(short) 300 + letter` is `int 365`. `2 + 3L` has type `long`, `0.5f + 2L` has type `float`, `1.25d + 0.5f` has type `double`.

**Bitwise shifts:** `count << 2` produces `int` because `count` is a `short` promoted to `int`. With `1 << 2L`, the right operand is `long`, yet the result is **still `int`**. Meanwhile, `1L << 2` returns `long` because the left operand is `long`.

**Integer division:** `5 / 2` is performed on `int`, yielding `2`. `5 / 2.0` applies binary numeric promotion to `double` before division, yielding `2.5`.

**Compound assignment:** `compound += 200` allows writing the result back to `byte` even though the intermediate addition is `int 300`. After narrowing to 8 bits, the result is `44`.

**Wrapper:** `wrapper + 2L` unboxes `Integer` to `int` and promotes to `long`; the result is `long 6`. If the wrapper is null, the unboxing step throws `NullPointerException`.

## 4. Why can't `byte` + `byte` be assigned directly to `byte`?

~~~java
byte x = 10;
byte y = 20;

int correct = x + y;       // Valid: result type is int.
// byte invalid = x + y;   // Compile error, because x+y is int.
byte narrowed = (byte) (x + y); // With explicit cast.
~~~

If you try to assign `x + y` to a `byte` variable without a cast, the compiler reports an error because **the expression type is `int`**, even if you know the specific sum fits within the `byte` range.

**Exception for constant expressions:** `byte b = 10 + 20;` compiles because `10 + 20` is an `int` constant expression with a value within the `byte` range. The constant narrowing rule in assignment context **does not change** the fact that `x + y` between two `byte` variables has type `int`.

Casting back to `byte` does not automatically guarantee preserving the value either; for example, `(byte) (100 + 100)` yields `-56` because 200 exceeds the `byte` range.

## 5. Binary promotion in comparisons and calculations

The same binary numeric promotion rules apply to arithmetic expressions and numeric comparisons:

~~~java
short left = 10;
long right = 20L;

long total = left + right; // long 30.
boolean smaller = left < right; // true.
~~~

With addition, the result type is the numeric type selected after promotion. With comparisons `<`, `<=`, `>`, `>=`, or equality comparisons between two numeric expressions, **the operands** are promoted per the appropriate rules, but **the result of the comparison is `boolean`**, not a numeric type.

Because converting to a floating-point type can lose precision, be careful when comparing a very large `long` with `float`/`double`. Do not treat “Java promotes types automatically” as proof that every comparison preserves exact integer units.

## 6. Bitwise shifts: the two operands are promoted separately

This is a case very frequently confused with binary numeric promotion:

~~~java
short s = 3;
int result = s << 2; // left short -> int; result int.

int x = 1 << 2L;     // long RHS is accepted; result is still int.
long y = 1L << 2;    // Left is long; result is long.
~~~

In bitwise shift operations, Java applies **unary numeric promotion** to *each operand*, and then takes the **type of the promoted left operand** as the result type. The right operand supplies the shift distance; it does not turn the result into `long` just because it has type `long`.

Additionally, when the left operand is `int`, Java uses only the **low 5 bits** of the shift distance (equivalent to modulo 32); for `long`, Java uses the **low 6 bits** (equivalent to modulo 64). This is a bitwise shift rule itself, not a type-selection rule of binary numeric promotion.

## 7. Promotion, casting, and compound assignment differ

| Mechanism | Example | Key takeaway |
| --- | --- | --- |
| Unary numeric promotion | `+((byte) 5)` | Result type is `int` |
| Binary numeric promotion | `2 + 3L` | Result type is `long` |
| Explicit cast | `(byte) 200` | Can lose data |
| Compound assignment | `byte b = 100; b += 200;` | Implicitly converts operation result to left-hand type |
| Autoboxing | `Object o = 2 + 3L;` | `long` result is boxed to `Long` |
| String concatenation | `"n=" + 1 + 2` | Not numeric addition once `String` participates |

When the result can exceed the target type's range, check the range before casting or use a wide-enough type. If you need to check `int`/`long` overflow in addition or multiplication, you can use `Math.addExact` and `Math.multiplyExact` as needed.

## 8. Self-check exercises

1. **Unary promotion:** Given `byte b = 5;`, what type is `+b`?  
   *Answer:* `int`, value 5.
2. **Binary promotion:** Given `short s = 10; char c = 'A';`, what type and value does `s + c` have?  
   *Answer:* `int`, value 75.
3. **Precedence:** What type is `1L + 0.5f`?  
   *Answer:* `float`, value 1.5f in this case.
4. **Bitwise shift:** Does `1 << 2L` have result type `long`?  
   *Answer:* No, the result is `int 4`, because this operator promotes each operand separately.
5. **Division:** What value does `double result = 5 / 2;` have?  
   *Answer:* `2.0` because `int` division happens before assignment to `double`.
6. **Compound assignment:** What does `byte b = 100; b += 200;` give?  
   *Answer:* `44` after intermediate `int 300` addition and narrowing conversion to `byte`.
7. **Null wrapper:** Where does `Integer x = null; int y = x + 1;` fail?  
   *Answer:* When unboxing `x` to perform the addition, throwing `NullPointerException`.

## Memory checklist

- [ ] Unary promotion: `byte`/`short`/`char` promote to `int`; larger numeric types stay unchanged.
- [ ] Binary promotion: precedence `double > float > long > int` in appropriate numeric contexts.
- [ ] Promotion is an **expression type** rule, not a guarantee against losing values.
- [ ] `byte + byte` has type `int`; constant assignments may have a separate exception.
- [ ] Bitwise shift operators promote **each operand separately**, result type is based on the left side.
- [ ] `+=` includes a conversion step to the target variable's type; can lose data.
- [ ] Distinguish numeric addition, string concatenation, and boxing/unboxing.

**Conclusion:** Before writing a Java calculation, determine **whether the operator uses unary or binary numeric promotion**, **the type of each operand after promotion**, and **the result type**. Be especially careful with `byte`/`short`/`char`, bitwise shifts, compound assignments, and conversions that may lose precision.