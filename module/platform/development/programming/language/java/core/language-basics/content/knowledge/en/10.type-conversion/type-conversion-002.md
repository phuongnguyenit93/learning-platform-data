# Widening and Narrowing Primitive Types in Java 17+

## 1. Objective: what is type conversion?

**Primitive type conversion** is the process by which Java converts a value between compatible primitive types, for example from `byte` to `int` or from `double` to `int`.

~~~java
int count = 120;
long widened = count;       // Widening: int -> long
byte narrowed = (byte) count; // Explicit narrowing: int -> byte

System.out.println(widened);  // 120
System.out.println(narrowed); // 120
~~~

There are two important categories:

- **Widening primitive conversion**: follows a relationship that allows Java to convert automatically in a suitable context, usually from a type to one with a broader representation range. **It does not mean arithmetic precision is always preserved.**
- **Narrowing primitive conversion**: goes from a source type to a target type that may not hold the entire source value; usually requires an **explicit cast** `(TargetType)`, and may lose data.

Java checks data type validity **at compile time**; however, a valid cast does not automatically guarantee that the converted value remains business-valid.

## 2. Recall primitive types before converting

| Type | Width | Characteristics |
|---|---:|---|
| `byte` | 8 bits | Signed integer, -128 to 127 |
| `short` | 16 bits | Signed integer, -32768 to 32767 |
| `char` | 16 bits | Unsigned UTF-16 code unit, 0 to 65535 |
| `int` | 32 bits | Signed integer |
| `long` | 64 bits | Signed integer |
| `float` | 32 bits | Binary floating-point, about 24 significant bits |
| `double` | 64 bits | Binary floating-point, about 53 significant bits |
| `boolean` | By true/false semantics | **No** arithmetic conversion to/from the remaining types |

**Note:** `char` and `short` are both 16 bits but do not have the same value range. `char` is non-negative; `short` is signed. Therefore, Java does not allow direct widening conversion from `char` to `short` or vice versa.

`String` is not a primitive type. Operations like `Integer.parseInt("123")` and `String.valueOf(123)` are **text and value conversions**, not a widening/narrowing primitive conversion.

## 3. Valid widening conversion paths

In Java, primitive widening relationships can be remembered using the following table:

| Source type | Valid direct widening target types |
|---|---|
| `byte` | `short`, `int`, `long`, `float`, `double` |
| `short` | `int`, `long`, `float`, `double` |
| `char` | `int`, `long`, `float`, `double` |
| `int` | `long`, `float`, `double` |
| `long` | `float`, `double` |
| `float` | `double` |

There is no widening from `double` to any other type; and `boolean` does not participate in this table.

~~~java
byte small = 100;
short medium = small; // byte -> short
int count = medium;   // short -> int
long total = count;   // int -> long
double reading = total; // long -> double

char letter = 'A';
int codeUnit = letter; // char -> int: 65

System.out.println(reading);  // 100.0
System.out.println(codeUnit); // 65
~~~

For example, `char` is a separate widening branch, not in the `byte -> short -> int -> long` chain.

**No cast is needed** in the widening assignments above. Writing `(long) count` can also be valid, but is usually unnecessary unless clarifying the type before an operation.

## 4. “Widening” does not guarantee absolute precision

This is a commonly misunderstood point. Widening conversions **between integer types** in the table above preserve exact values. However, when widening to a floating-point type, some large values **cannot be represented accurately with a finite significand**.

Consider a `long` with value \(2^{53}+1\):

~~~java
long exact = 9_007_199_254_740_993L;
double approximate = exact; // Widening long -> double

System.out.println(exact);               // 9007199254740993
System.out.println(approximate);         // 9.007199254740992E15
System.out.println((long) approximate);  // 9007199254740992
~~~

`long` holds that integer accurately, but `double` only has 53 effective significand bits: the value is rounded to \(2^{53}\), losing the last unit.

Similarly:

~~~java
float big = 16_777_216f; // 2^24
System.out.println(big + 1f == big); // true
~~~

At this magnitude, `float` can no longer distinguish every increment of 1.

Another example is `float -> double`:

~~~java
float f = 0.1f;
double d = f;
System.out.println(d); // 0.10000000149011612
~~~

Converting `float` to `double` **preserves the exact binary value currently in the float**, without recovering the original decimal `0.1`.

**Practical rule:** when converting large integers to `float`/`double`, examine the required precision. If every count unit must be preserved, keep `long`/`int` or choose a more accurate representation.

## 5. Narrowing integer types: casting and data loss

When converting from an integer type to a smaller integer type, you usually have to write a cast:

~~~java
int value = 130;
// byte invalid = value; // COMPILE ERROR
byte narrowed = (byte) value;
System.out.println(narrowed); // -126
~~~

Because `byte` only represents from -128 to 127, converting 130 to `byte` keeps the **low 8 bits** of the result according to the narrowing rule. The bit pattern `1000_0010` is interpreted as -126 in signed representation.

Similarly:

~~~java
int value = 65_537;
char c = (char) value;
System.out.println((int) c); // 1
~~~

A 16-bit `char` receives the low 16 bits; 65537 equals \(65536+1\), so the code unit after casting has value 1.

| Conversion | Input | Result |
|---|---:|---:|
| `(byte) 127` | 127 | 127 |
| `(byte) 128` | 128 | -128 |
| `(byte) 130` | 130 | -126 |
| `(short) 65535` | 65535 | -1 |
| `(char) -1` | -1 | 65535 |

**A cast does not automatically warn of overflow.** It merely instructs Java to perform a syntactically valid type conversion. If arithmetic value changes are not acceptable, check bounds before casting.

## 6. Exception: assigning an in-range `int` constant to `byte`, `short`, `char`

Assignments `int -> byte`, `short`, or `char` are normally narrowing. However, Java has a **narrowing conversion specifically for compile-time constant expressions** when the value can be represented in the target type.

~~~java
byte b = 127;         // Valid even though literal 127 has type int
short s = 32_000;     // Valid
char c = 65;          // Valid: UTF-16 code 65
// byte wrong = 128;  // ERROR: outside byte range
// char wrong2 = -1;  // ERROR: outside char range
~~~

A regular `int` variable **is not converted automatically**, even when it currently holds 127:

~~~java
int value = 127;
// byte b = value;    // Compile error: int does not narrow automatically
byte b = (byte) value; // Valid, but you take responsibility
~~~

A **`final` constant variable** of type `int` assigned with a constant expression can also be considered by the compiler in an assignment context:

~~~java
final int LIMIT = 100;
byte threshold = LIMIT; // Valid because LIMIT is a constant variable
~~~

But `final int runtime = Integer.parseInt("100");` is not a constant variable in this sense; the value comes from a method call, so the special narrowing assignment cannot be used.

**Rule boundary:** the exception above belongs to the assignment context (which also includes initializers), and does not allow implicit narrowing in every method call or expression. Avoid inferring from `byte b = 127;` that any `int` can be passed to a `byte` parameter everywhere without a cast.

## 7. Narrowing from `float`/`double` to integer

Converting `float` or `double` to an integer type requires a cast in ordinary cases:

~~~java
double positive = 12.9;
double negative = -12.9;

System.out.println((int) positive); // 12
System.out.println((int) negative); // -12
~~~

Java **truncates the fractional part toward 0**, rather than using nearest-integer rounding like `Math.round`.

Remember the special cases according to the specification:

| `double` input | `(int)` | Explanation |
|---|---:|---|
| `12.9` | 12 | Truncates fractional part |
| `-12.9` | -12 | Toward 0 |
| `Double.NaN` | 0 | NaN rule when converting to integer |
| `Double.POSITIVE_INFINITY` | 2147483647 | Saturates at `Integer.MAX_VALUE` |
| `Double.NEGATIVE_INFINITY` | -2147483648 | Saturates at `Integer.MIN_VALUE` |
| `1.0e30` | 2147483647 | Saturates when exceeding int range |

If the target is `byte` or `short`, narrowing from floating-point first converts through `int` and then narrows further, which can produce even harder-to-predict results if you do not validate the input.

Do not use `(int) doubleValue` as “validation”: NaN, Infinity, or out-of-range values **do not necessarily throw an exception**. If you need finite, whole-integer data within a specific interval, check each condition before casting.

## 8. Narrowing `double -> float`: precision loss, overflow, underflow

~~~java
double source = 0.1;
float narrowed = (float) source;

System.out.println(narrowed);        // 0.1
System.out.println((double) narrowed); // 0.10000000149011612
~~~

The displayed string `0.1` is how Java prints a `float` value close to `0.1`, not that `float` stores 1/10 accurately.

A finite `double` value that is too large when converted to `float` can become **Infinity**:

~~~java
double huge = 1.0e40;
float overflow = (float) huge;
System.out.println(overflow); // Infinity
~~~

A value with too small a magnitude can convert to (signed) zero or a subnormal value. When a finite and nonzero `float` result is required, proper validation is needed.

**For `float`/`double`:** do not equate “fewer bits in width” with the low-bit-retention rule like `int -> byte` conversion. Floating-point narrowing uses the rounding/clamping rules of the floating-point model.

## 9. Type conversion in arithmetic expressions

Java performs **numeric promotion** on many arithmetic operators. In particular, `byte`, `short`, and `char` are promoted to `int` in ordinary addition:

~~~java
byte a = 100;
byte b = 20;

// byte sum = a + b; // ERROR: a + b has type int
int sum = a + b;
System.out.println(sum); // 120

char ch = 'A';
// char next = ch + 1; // ERROR: ch + 1 is int
char next = (char) (ch + 1);
System.out.println(next); // B
~~~

With `long`, `float`, or `double` operands, the expression is promoted according to the corresponding rules before computing.

An important pitfall is **overflow occurring before assigning to `long`**:

~~~java
int x = Integer.MAX_VALUE;
long wrong = x + 1;        // int + int overflows before assigning to long
long correct = (long) x + 1; // One operand is already long

System.out.println(wrong);   // -2147483648
System.out.println(correct); // 2147483648
~~~

Merely declaring the **target** variable as `long` does not change an addition that already happened with `int` operands.

### Compound assignment has an implicit cast

~~~java
byte count = 120;
count += 10;
System.out.println(count); // -126
~~~

`count += 10` compiles because compound assignment semantics include converting the result to the type of the receiving variable. However:

~~~java
byte count = 120;
// count = count + 10; // ERROR: count + 10 has type int
~~~

The two forms look similar but have **different compile outcomes**. Do not use `+=` as a way to bypass overflow checks: `count += 10` still loses arithmetic data.

## 10. Safety checks before narrowing

There are multiple approaches depending on the type range.

### Case `long -> int`

Java provides `Math.toIntExact(long)`, returning `int` if in range; if out of range, it throws `ArithmeticException`:

~~~java
long big = 2_147_483_648L;

try {
    int safe = Math.toIntExact(big);
    System.out.println(safe);
} catch (ArithmeticException ex) {
    System.out.println("outside int range");
}
~~~

Output: `outside int range`.

### Case `long -> byte`

There is no corresponding `Math.toByteExact(long)` in Java 17; you can check:

~~~java
static byte checkedByte(long value) {
    if (value < Byte.MIN_VALUE || value > Byte.MAX_VALUE) {
        throw new IllegalArgumentException("outside byte range");
    }
    return (byte) value;
}
~~~

### Case `double -> int` requiring an exact whole integer

~~~java
static int checkedWholeInt(double value) {
    if (!Double.isFinite(value)
            || value < Integer.MIN_VALUE
            || value >= 2147483648.0
            || value != Math.rint(value)) {
        throw new IllegalArgumentException("not a finite int");
    }
    return (int) value;
}
~~~

Here we check **finiteness**, **within `int` range**, and **no fractional part**. The upper bound uses `2147483648.0` (2³¹) and the `>=` condition to avoid representation pitfalls when comparing floating-point numbers with `Integer.MAX_VALUE`.

If exact decimal precision, specific rounding rules, or large numeric ranges are needed, choose an appropriate type/algorithm instead of casting directly.

## 11. `boolean` has no arithmetic type conversion

Java **does not allow** converting `boolean` to `int` or vice versa via widening/narrowing:

~~~java
boolean enabled = true;
// int number = (int) enabled; // COMPILE ERROR

int number = 1;
// boolean flag = (boolean) number; // COMPILE ERROR
~~~

If business logic specifies that `true` corresponds to `1`, you must express that rule explicitly:

~~~java
boolean enabled = true;
int numericFlag = enabled ? 1 : 0;
System.out.println(numericFlag); // 1
~~~

This is a conditional expression producing an integer according to your defined rule, **not** a primitive conversion from boolean.

## 12. Complete, runnable Java 17 example

Create the exact file **`PrimitiveConversionDemo.java`**:

~~~java
public final class PrimitiveConversionDemo {
    private PrimitiveConversionDemo() {}

    static byte checkedByte(long value) {
        if (value < Byte.MIN_VALUE || value > Byte.MAX_VALUE) {
            throw new IllegalArgumentException("outside byte range");
        }
        return (byte) value;
    }

    static int checkedWholeInt(double value) {
        if (!Double.isFinite(value)
                || value < Integer.MIN_VALUE
                || value >= 2147483648.0
                || value != Math.rint(value)) {
            throw new IllegalArgumentException("not a finite int");
        }
        return (int) value;
    }

    public static void main(String[] args) {
        byte small = 100;
        short asShort = small;
        int asInt = small;
        long asLong = asInt;
        double asDouble = asLong;
        System.out.println("widen=" + asShort + "," + asInt
                + "," + asLong + "," + asDouble);

        char letter = 'A';
        int codeUnit = letter;
        System.out.println("char code=" + codeUnit);

        int input = 130;
        byte narrowed = (byte) input;
        System.out.println("int to byte=" + narrowed);
        System.out.println("int to char=" + (int) (char) -1);

        final int limit = 100;
        byte fromConstant = limit;
        System.out.println("constant=" + fromConstant);

        long bigInteger = 9_007_199_254_740_993L;
        double approximate = bigInteger;
        System.out.println("long original=" + bigInteger);
        System.out.println("long through double=" + (long) approximate);

        float decimalFloat = 0.1f;
        double widenedFloat = decimalFloat;
        System.out.println("float as double=" + widenedFloat);

        System.out.println("positive trunc=" + (int) 12.9);
        System.out.println("negative trunc=" + (int) -12.9);
        System.out.println("NaN to int=" + (int) Double.NaN);
        System.out.println("infinity to int="
                + (int) Double.POSITIVE_INFINITY);
        System.out.println("double to float=" + (float) 1.0e40);

        byte a = 100;
        byte b = 20;
        int sum = a + b;
        System.out.println("byte addition=" + sum);

        byte count = 120;
        count += 10;
        System.out.println("compound assignment=" + count);

        int max = Integer.MAX_VALUE;
        long wrong = max + 1;
        long right = (long) max + 1;
        System.out.println("int overflow first=" + wrong);
        System.out.println("long arithmetic=" + right);

        System.out.println("checked byte=" + checkedByte(127));
        try {
            checkedByte(128);
        } catch (IllegalArgumentException ex) {
            System.out.println("checked byte error=" + ex.getMessage());
        }

        System.out.println("checked whole int=" + checkedWholeInt(42.0));
        try {
            checkedWholeInt(42.5);
        } catch (IllegalArgumentException ex) {
            System.out.println("checked whole error=" + ex.getMessage());
        }

        try {
            Math.toIntExact(2_147_483_648L);
        } catch (ArithmeticException ex) {
            System.out.println("toIntExact=overflow");
        }
    }
}
~~~

Requirements: **JDK 17 or later** installed, terminal located in the directory containing the file.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 PrimitiveConversionDemo.java
java -cp . PrimitiveConversionDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\PrimitiveConversionDemo.java
java -cp . PrimitiveConversionDemo
~~~

**Expected output:**

~~~text
widen=100,100,100,100.0
char code=65
int to byte=-126
int to char=65535
constant=100
long original=9007199254740993
long through double=9007199254740992
float as double=0.10000000149011612
positive trunc=12
negative trunc=-12
NaN to int=0
infinity to int=2147483647
double to float=Infinity
byte addition=120
compound assignment=-126
int overflow first=-2147483648
long arithmetic=2147483648
checked byte=127
checked byte error=outside byte range
checked whole int=42
checked whole error=not a finite int
toIntExact=overflow
~~~

**Reading the results by group:**

1. `widen` and `char code` show that widening preserves small values accurately.
2. `int to byte` and `int to char` show that integer narrowing can change values.
3. `constant` illustrates the assignment exception for `int` constant variables within `byte` range.
4. `long through double` and `float as double` prove that widening does not always recover the desired precision.
5. `positive/negative trunc`, `NaN`, and `infinity` show that floating-point-to-integer casting has special rules.
6. `compound assignment` and `int overflow first` remind us that calculations may have already lost values before assignment.
7. The two functions `checkedByte`/`checkedWholeInt` and `Math.toIntExact` demonstrate how to prevent data loss when business logic cannot accept it.

The example requires no libraries outside the JDK, and the output does not depend on the operating system or keyboard input.

## 13. Common mistakes

| Situation | Cause | How to handle |
|---|---|---|
| `byte b = intVariable;` | Narrowing `int -> byte` is not automatic | Check range then cast |
| `byte b = 128;` | Constant `int` does not fit in `byte` range | Use a larger type if 128 is needed |
| `short s = charVariable;` | No widening `char -> short` | Check range then cast, or use `int` |
| `char c = shortVariable;` | `short` can be negative, `char` is unsigned | Check before casting |
| `long x = 3_000_000_000;` | Decimal integer literal defaults to `int`, exceeding limit | `3_000_000_000L` |
| `float f = 0.1;` | Literal `0.1` has type `double` | `0.1f` or intentional cast |
| `long result = intA + intB;` overflows | `int` addition occurs before widening | Convert at least one operand to `long` first |
| `byte s = a + b;` with `a`, `b` as `byte` | Binary numeric promotion to `int` | Receive `int`, or cast with validation |
| `byte count; count += delta;` loses data | Compound assignment narrows implicitly | Compute as `int`, check range, then assign |
| `(int) 12.9` gives 12 | Cast truncates fractional part toward 0 | If rounding is desired, use a separate rule/API |
| `(int) Double.NaN` gives 0 | Special conversion rule | Validate before casting |
| `(int) Double.POSITIVE_INFINITY` gives max int | Saturation value | Check `isFinite`/range |
| `long -> double` loses last digits | 53-bit significand limit | Keep `long` if exact integers are needed |
| Casting `boolean` to `int` | No such primitive conversion exists | Use a conditional expression per business logic |

**Distinguish clearly:** Java may accept a cast syntactically while producing a result that violates requirements. Choosing the representation/validation is the responsibility of program design.

## 14. Exercises with answers

### Exercise A — widening

~~~java
byte b = -10;
int i = b;
long l = i;
System.out.println(l);
~~~

**Answer:** `-10`. Two widening steps between integers preserve negative values accurately.

### Exercise B — narrowing

~~~java
int n = 255;
System.out.println((byte) n);
~~~

**Answer:** `-1`. The low 8-bit pattern `11111111` is -1 when interpreted as a signed `byte`.

### Exercise C — `char` and `short`

~~~java
char c = 65;
int code = c;
System.out.println(code);
~~~

**Answer:** `65`. `char -> int` is widening; however, `char -> short` is not widening even though both are 16 bits.

### Exercise D — `float` and `double`

~~~java
float f = 0.1f;
double d = f;
System.out.println(d);
~~~

**Answer:** `0.10000000149011612`. Widening preserves the exact **approximate value already stored** in `float`.

### Exercise E — `int` addition

~~~java
int max = Integer.MAX_VALUE;
long result = max + 1;
System.out.println(result);
~~~

**Answer:** `-2147483648`, because the addition overflows in `int` first. Fix with `long result = (long) max + 1;`.

### Exercise F — fractional part not allowed

Given `double value = 12.5;` to convert to an integer when business logic **does not allow losing the fractional part**, should you write `(int) value`?

**Answer:** No. The cast yields `12`, losing 0.5. Before casting, verify the data is finite, within the integer type's range, and has a whole-number value; if invalid, reject or handle per business rules.

## 15. Summary checklist

- [ ] Know how to distinguish widening and narrowing primitive conversion.
- [ ] Remember `char` is not a signed `short` and `boolean` does not participate in numeric conversions.
- [ ] Know that widening between integer types preserves exact values, while widening to `float`/`double` may round.
- [ ] Know that integer narrowing via cast keeps low bits and can change numeric values.
- [ ] Understand the assignment exception for `int` constants fitting in `byte`/`short`/`char`.
- [ ] Know that casting `float`/`double` to `int`/`long` usually truncates toward 0 and has special rules for NaN/Infinity.
- [ ] Know that `double -> float` can lose precision, overflow, or underflow.
- [ ] Remember `byte`/`short`/`char` are promoted to `int` in many operations.
- [ ] Know that compound assignments like `+=` can narrow types implicitly.
- [ ] Choose operand types **before** addition might overflow.
- [ ] Check range before casting, using `Math.toIntExact` when appropriate.
- [ ] Run `PrimitiveConversionDemo.java` with JDK 17+ and compare each line of output.

**Conclusion:** **Widening conversions** are usually performed automatically by Java, but precision loss can occur when converting to floating-point. **Narrowing conversions** usually require a cast and can alter values without throwing an exception. Distinguishing operand types, representation limits, and business requirements is the way to write safe primitive conversions in Java 17+.