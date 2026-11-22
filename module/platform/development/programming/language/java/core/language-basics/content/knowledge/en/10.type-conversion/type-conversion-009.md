# Constant Assignment Within the Range of `byte`, `short`, or `char` — Java 17+

In Java, ordinary integer literals like `100` have type `int`, yet **`byte b = 100;` still compiles**. The reason is that Java permits a **special narrowing conversion in assignment context** for a **compile-time constant expression**, when its value fits completely within the representable range of target type `byte`, `short`, or `char`.

This is a specific rule in Java, **not** an implicit conversion from every `int` variable to `byte`.

~~~java
byte age = 100;        // Valid: int constant 100 is within byte range.
short count = 30_000;  // Valid: int constant is within short range.
char code = 65;        // Valid: int constant 65 is within char range ('A').

// byte bad = 128;     // ERROR: 128 exceeds Byte.MAX_VALUE.
// byte bad2 = -129;   // ERROR: smaller than Byte.MIN_VALUE.
// short bad3 = 32768; // ERROR: exceeds Short.MAX_VALUE.
// char bad4 = -1;     // ERROR: char is unsigned.
~~~

## 1. Exact rule

In an **assignment**, if the source expression is a *constant expression* of type `byte`, `short`, `char`, or `int` and has a **value representable** by the target type `byte`, `short`, or `char`, Java can perform the narrowing conversion **without an explicit cast**.

| Target type | Value range | Valid `int` constant assignment | Out-of-range constant assignment |
| --- | --- | --- | --- |
| `byte` | −128 to 127 | `byte b = 127;` | `byte b = 128;` |
| `short` | −32,768 to 32,767 | `short s = 32_767;` | `short s = 32_768;` |
| `char` | 0 to 65,535 | `char c = 65_535;` | `char c = 65_536;` or `char c = -1;` |

**Both conditions must hold together:** the expression must be a **compile-time constant**, and **the constant value must fall within the target type's range**.

A regular `int` variable holding the value 100 **does not** qualify for this exception:

~~~java
int value = 100;
// byte b = value;     // COMPILE ERROR: int -> byte requires cast.
byte b = (byte) value; // Valid; since 100 is in range, b = 100.
~~~

Having a cast does not make the compiler or JVM ensure the value stays in range; if `value` becomes 130, `(byte) value` yields `-126` due to losing the high bits.

## 2. Runnable Java 17+ program

Create the UTF-8 file **`ConstantAssignmentDemo.java`**:

~~~java
public class ConstantAssignmentDemo {
    static final int CLASS_LIMIT = 127;

    public static void main(String[] args) {
        byte maxByte = 127;
        byte minByte = -128;
        short maxShort = 32_767;
        short minShort = -32_768;
        char maxChar = 65_535;

        System.out.println("byteMax=" + maxByte);
        System.out.println("byteMin=" + minByte);
        System.out.println("shortMax=" + maxShort);
        System.out.println("shortMin=" + minShort);
        System.out.println("charMaxCode=" + (int) maxChar);

        byte foldedByte = 40 + 60;
        short foldedShort = 30_000 + 2_767;
        char nextLetter = 'A' + 1;
        System.out.println("foldedByte=" + foldedByte);
        System.out.println("foldedShort=" + foldedShort);
        System.out.println("letter=" + nextLetter);

        final int localConstant = 120;
        byte fromLocalFinal = localConstant;

        final int foldedConstant = 60 + 67;
        byte fromFoldedFinal = foldedConstant;
        byte fromClassFinal = CLASS_LIMIT;

        System.out.println("localFinal=" + fromLocalFinal);
        System.out.println("foldedFinal=" + fromFoldedFinal);
        System.out.println("classFinal=" + fromClassFinal);

        int variable = 120;
        byte castVariable = (byte) variable;

        final int runtimeFinal = Integer.parseInt("12");
        byte castRuntimeFinal = (byte) runtimeFinal;
        System.out.println("castVariable=" + castVariable);
        System.out.println("runtimeFinal=" + castRuntimeFinal);

        byte castOverflow = (byte) 128;
        short castShortOverflow = (short) 32_768;
        char castCharOverflow = (char) 65_536;
        System.out.println("castByteOverflow=" + castOverflow);
        System.out.println("castShortOverflow=" + castShortOverflow);
        System.out.println("castCharOverflow=" + (int) castCharOverflow);

        byte compounded = 100;
        compounded += 30;
        System.out.println("compoundAssignment=" + compounded);
    }
}
~~~

In the directory containing the file, use **JDK 17 or later** in PowerShell (Windows) or Bash (Linux/macOS):

~~~bash
java -version
javac -version
javac -encoding UTF-8 ConstantAssignmentDemo.java
java ConstantAssignmentDemo
~~~

**Exact expected output of the `java ConstantAssignmentDemo` command:**

~~~text
byteMax=127
byteMin=-128
shortMax=32767
shortMin=-32768
charMaxCode=65535
foldedByte=100
foldedShort=32767
letter=B
localFinal=120
foldedFinal=127
classFinal=127
castVariable=120
runtimeFinal=12
castByteOverflow=-128
castShortOverflow=-32768
castCharOverflow=0
compoundAssignment=-126
~~~

The version-check commands `java -version` and `javac -version` have output that varies by environment and are not included in the expected output block.

## 3. Why can the expression `40 + 60` still be assigned to `byte`?

When evaluating `40 + 60`, both literals carry type `int`, so the expression has **type `int`**. Even so, `40 + 60` is a **constant expression**: the compiler computes the value **100** at compile time. Because 100 falls within the `byte` range, the following statement is valid:

~~~java
byte result = 40 + 60; // 100: constant int within byte range.
~~~

Conversely, if regular variables are used:

~~~java
int left = 40;
int right = 60;

// byte result = left + right; // ERROR: result is int, not constant.
int result = left + right;     // Valid: int 100.
~~~

Even regular `byte + byte` has result type `int` (by *binary numeric promotion*):

~~~java
byte a = 40;
byte b = 60;
// byte sum = a + b; // ERROR: int does not narrow automatically to byte.
int sum = a + b;    // 100.
~~~

**Do not assume** that whenever the compiler sees a small value it will automatically assign it to a narrow type. It applies the exception strictly to **qualifying constant expressions**.

## 4. `final int` can be a *constant variable* — but not always

A **constant variable** in Java is a `final` variable of primitive type or `String` initialized with a *constant expression*. For integer constant assignment problems, the typical case is `final int`:

~~~java
final int FIXED = 120;
byte b = FIXED; // Valid: FIXED is a constant variable, value fits in byte.

final int CALCULATED = 60 + 67;
byte max = CALCULATED; // Valid: 127 fits in byte.
~~~

`static final int` can also be a constant variable if its initializer is a constant expression:

~~~java
static final int BYTE_MAX = 127;

// Inside a method:
// byte b = BYTE_MAX; // Valid.
~~~

However, **the `final` keyword alone is not enough**:

~~~java
final int parsed = Integer.parseInt("12");
// byte b = parsed;        // ERROR: parsed is NOT a constant variable.
byte b = (byte) parsed;    // Valid, but you must consider the value range.
~~~

`Integer.parseInt` executes at runtime, so the initializer above is **not a constant expression**, regardless of the returned value being 12. In contrast, expressions with arithmetic operators on suitable literals/constants like `60 + 67` can be precomputed by the compiler.

Similarly, `final Integer boxed = 100;` is not a primitive constant variable, because `Integer` is a **reference type**, not a primitive type or `String`. Do not use `final` and a value “happening to fit in range” as proof that a variable qualifies for the constant assignment exception.

## 5. Range boundaries: `byte`, `short`, and `char`

### `byte` is an 8-bit signed integer

~~~java
byte smallest = -128;
byte largest = 127;

// byte under = -129; // Out of range.
// byte over = 128;   // Out of range.
~~~

A cast is still allowed, yet **does not preserve the value** when a number exceeds the range:

~~~java
byte wrapped = (byte) 128; // -128.
~~~

Integer-to-integer narrowing keeps the **low bits** matching the target type; for `byte`, the 8-bit pattern is interpreted as signed. Java does not “clamp” the value at 127 and does not automatically throw `ArithmeticException` on cast.

### `short` is a 16-bit signed integer

~~~java
short min = -32_768;
short max = 32_767;
// short bad = 32_768; // Out of range.
short wrapped = (short) 32_768; // -32768.
~~~

### `char` is a 16-bit unsigned UTF-16 code unit

~~~java
char zero = 0;
char letter = 65;      // 'A'.
char max = 65_535;

// char negative = -1; // Out of char range.
// char tooBig = 65_536; // Out of char range.
char wrapped = (char) 65_536; // Numeric value 0.
~~~

`char` differs from `short`: both have 16 bits, but `char` has range 0–65535. When printing `char` directly, the terminal displays the **corresponding character** rather than its numeric code. To inspect the numeric value, use `(int) letter` or `(int) max`.

## 6. Why don't `long` literals and `double` literals qualify for the exception?

Constant narrowing in an assignment context targeting `byte`, `short`, or `char` only allows the **type of the source constant expression** to be `byte`, `short`, `char`, or `int`. Therefore:

~~~java
byte a = 100;          // Valid: constant int.
// byte b = 100L;       // ERROR: constant long, even though value is 100.
// byte c = 100.0;      // ERROR: double literal.
byte b = (byte) 100L;   // Explicit cast.
byte c = (byte) 100.0;  // Explicit cast.
~~~

Even if a `long` value is actually small, that does **not** make `long -> byte` qualify for the constant assignment exception. A cast lets the snippet run, but you yourself must check for data loss.

When data comes from input, APIs, variables, or runtime calculations, the practical approach is to choose a wide-enough type, check bounds before converting, or use appropriate overflow-checking methods such as `Math.toIntExact` when narrowing `long -> int`.

## 7. Distinguish direct assignment from `+=`

~~~java
byte b = 100;
// b = b + 30;  // ERROR: b + 30 is int, not a constant expression.
b += 30;        // Valid; result is -126.
~~~

`b += 30` is valid **not because of the constant assignment exception**. Compound assignment operators have their own rule: add first, then **convert to the type of the left-hand side**. With `byte b = 100`, the addition produces `int 130`, which converts to `byte` as `-126`.

If a value lies outside the target range, do not use casts or `+=` as a way to “bypass compiler errors” when business logic requires exact numbers.

## 8. Table distinguishing valid vs. compile error

| Java code | Valid? | Reason |
| --- | --- | --- |
| `byte b = 127;` | Yes | Constant `int` fits in `byte` |
| `byte b = 128;` | No | Constant `int` exceeds `byte` range |
| `short s = 30_000 + 2_767;` | Yes | Constant expression `int 32767` fits in `short` |
| `char c = 'A' + 1;` | Yes | Constant expression `int 66` fits in `char` |
| `char c = -1;` | No | `char` has no negative numbers |
| `byte b = 100L;` | No | Source is `long`, excluded from the exception |
| `int x = 100; byte b = x;` | No | `x` is not a constant variable |
| `final int X = 100; byte b = X;` | Yes | `X` is a primitive constant variable |
| `final int X = Integer.parseInt("100"); byte b = X;` | No | Initializer is not a constant expression |
| `byte b = (byte) 128;` | Yes | Explicit cast, though the result is −128 |

If you see a compiler message like *possible lossy conversion from int to byte*, ask: is the expression a constant? Is the value within the target range? Or are you using an ordinary variable and actually need to keep a wider type?

## 9. Self-check exercises

1. **`byte` bounds:** Are `byte a = -128; byte b = 127;` valid? What about `byte c = 128;`?  
   *Answer:* The first two are valid; the last is a compile error.
2. **Constant expression:** Does `short s = 10_000 + 20_000;` require a cast?  
   *Answer:* No. The `int` constant expression 30000 fits within the `short` range.
3. **Regular variable:** Is `int x = 100; byte b = x;` valid?  
   *Answer:* No; `x` is not a constant variable, even though its test value is 100.
4. **`final` constant:** Is `final int X = 127; byte b = X;` valid? What if `X = 128`?  
   *Answer:* 127 is valid; 128 exceeds the `byte` range and is rejected by the compiler.
5. **`char`:** What about `char c = 65_535;` and `char d = 65_536;`?  
   *Answer:* `c` is valid, `d` is not; `char` is 16-bit unsigned.
6. **`long` literal:** Why is `byte b = 100L;` invalid while `byte b = 100;` is valid?  
   *Answer:* Constant narrowing in assignment context does not apply to a `long` source.
7. **Out-of-range cast:** What does `(byte) 128` yield?  
   *Answer:* `-128` due to keeping the low eight bits and interpreting as signed.

## Checklist

- [ ] Identify the **source type of the constant expression**, not just the value.
- [ ] Verify the value lies within `byte`/`short`/`char` range.
- [ ] Distinguish constant literals from regular `int` variables.
- [ ] `final int` only participates as a constant variable if its initializer is a constant expression.
- [ ] Constant expressions such as `'A' + 1` and `40 + 60` can be precomputed by the compiler.
- [ ] `100L` and `100.0` do not qualify for the `int` constant assignment exception.
- [ ] Casting or `+=` assignment can **lose data** and does not check bounds automatically.
- [ ] If unsure whether the result fits in range, prefer a wider type or check bounds before converting.

**Conclusion:** `byte b = 100;` is valid due to the **constant expression narrowing exception in assignment context**, not because every `int` converts to `byte` automatically. The compiler must know the **value at compile time**, and that value must **lie within the target type's range**.