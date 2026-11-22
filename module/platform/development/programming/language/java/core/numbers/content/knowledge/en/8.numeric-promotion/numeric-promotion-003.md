# Why does `byte` plus `byte` usually produce an `int` in Java?

In Java, an expression adding two `byte` variables is **promoted to `int` before calculation**. Thus, even though both operands have type `byte`, **the type of the expression `a + b` is `int`**, not `byte`. This is the **binary numeric promotion** rule applied by the language at compile time.

```java
byte a = 10;
byte b = 20;
int sum = a + b;  // valid, sum == 30
// byte wrong = a + b; // compile error: incompatible types / possible lossy conversion
```

The fact that `30` fits in the `byte` range does not cause the compiler to change the result type of `a + b`. The compiler relies on the **expression type**, rather than inferring all possible runtime values of variables. There is an important exception for **compile-time constant expressions** such as `byte c = 10 + 20;`, presented below.

## 1. What can `byte` store, and why does Java not keep the `byte` type when adding?

`byte` is an **8-bit signed** integer primitive with a range from `-128` to `127`. Two completely valid `byte` values can have a sum that cannot be represented in 8 bits:

```java
byte a = 100;
byte b = 50;
int sum = a + b; // 150: valid in int, exceeds byte
```

If the result were automatically restricted to `byte`, `150` would become `-106` when cast down to 8 bits. Java avoids implicitly narrowing the result of normal addition by choosing `int` for the expression.

However, the **precise language-level reason** is the binary numeric promotion rule: operands of types `byte`, `short`, and `char` are promoted to `int` for arithmetic operators such as `+`, `-`, `*`, `/`, and `%`. Choosing `int` does not depend on whether the specific sum is 30, 150, or negative. For two `byte` values, `int` is always sufficient to hold the mathematical sum of that single addition: the sum range is `-256` to `254`.

Quick reference table:

| Operands | Expression | Expression type | Example result |
| --- | --- | --- | --- |
| `byte` and `byte` | `a + b` | `int` | `10 + 20 = 30` |
| `short` and `short` | `s1 + s2` | `int` | `100 + 200 = 300` |
| `char` and `char` | `c1 + c2` | `int` | `'A' + 'B' = 131` |
| `byte` and `int` | `b + i` | `int` | Depends on values |
| `byte` and `long` | `b + l` | `long` | Depends on values |
| `byte` and `float` | `b + f` | `float` | May round |
| `byte` and `double` | `b + d` | `double` | May round |

When `+` has a `String` operand, it can become **string concatenation**, and this arithmetic table no longer applies to that concatenation operation.

## 2. Binary numeric promotion rules

For binary arithmetic operators that require promotion, Java examines both operands and chooses a common type in priority order:

1. If either operand is `double`, convert the other operand to `double`; result is `double`.
2. Otherwise, if either operand is `float`, convert the other operand to `float`; result is `float`.
3. Otherwise, if either operand is `long`, convert the other operand to `long`; result is `long`.
4. If none of the three cases above apply, convert both operands to `int`; result is `int`.

Since `byte` is not `double`, `float`, or `long`, the addition `byte + byte` falls into the final step:

```text
byte a ──widening──> int ──┐
                            ├── int addition ──> int
byte b ──widening──> int ──┘
```

Widening `byte` → `int` preserves the exact value of each operand; this is why the sum of two `byte` values does not overflow `byte` before another cast or narrowing assignment occurs.

```java
byte a = 120;
byte b = 120;

int result = a + b;        // 240
long widened = a + b;      // int 240 is widened after addition
float asFloat = a + b;     // int 240 is widened after addition
```

Note: `widened` has type `long`, yet `a + b` is still an **`int` expression**. In an example with only two `byte` values, the sum always fits in `int`; however, with large `int` operands, widening **after** addition can be too late to prevent overflow.

### Not every operator returns `int`

`a < b` with two `byte` values also promotes both operands for comparison, but **the result of a relational operator is `boolean`**, not `int`. The string concatenation operator has its own rules. This lesson discusses the type of **arithmetic operation results** and does not claim that every expression containing `byte` returns `int`.

## 3. Why does `byte c = a + b;` fail even when the result is small?

Suppose:

```java
byte a = 10;
byte b = 20;
// byte c = a + b; // compile error
```

The compiler knows `a + b` has type `int`. Assigning directly from an ordinary **`int` variable or expression** to `byte` is a **narrowing primitive conversion**, which is not allowed automatically here.

Regardless of whether you mentally calculated `10 + 20 = 30`, the two variables can change at runtime. More importantly, assignment rules operate on type information and defined constant exceptions, rather than executing the program to predict values.

Ways to fix depending on requirements:

```java
byte a = 10;
byte b = 20;

int exactSum = a + b;           // preferred when you want to keep the sum value
byte castSum = (byte) (a + b);   // valid, but may lose data if sum is outside byte
```

If you need to guarantee it stays within the `byte` range, check **before casting**:

```java
int candidate = a + b;
if (candidate < Byte.MIN_VALUE || candidate > Byte.MAX_VALUE) {
    throw new ArithmeticException("Sum outside byte range");
}
byte safeSum = (byte) candidate;
```

This snippet belongs inside a method/class where `a` and `b` are already declared, not as a standalone program. In applications, it is usually clearer to keep the result as `int` unless constrained by an API, memory, or data format that requires `byte`.

## 4. Important exception: constant `int` expressions can be assigned to `byte`

Because `10` and `20` are `int` literals, `10 + 20` is also an `int` expression. However, Java allows an **implicit narrowing conversion in an assignment context** for certain compile-time constant expressions, provided the value fits within the target type's range.

```java
byte direct = 10 + 20;     // valid: int constant expression = 30, fits in byte
byte maximum = 100 + 27;   // valid: 127
// byte tooLarge = 100 + 28; // error: 128 is outside byte

short smallShort = 20_000 + 10_000; // valid: 30000
char letter = 60 + 5;      // valid: code 65, i.e. 'A'
```

**This is not proof that `10 + 20` has type `byte`.** It still has type `int`. The compiler permits narrowing a **constant value known at compile time** because it knows for certain the result fits in the target range.

### `final` can create a *constant variable*

A primitive variable declared `final` and initialized with a constant expression can participate in a new constant expression:

```java
final byte left = 10;
final byte right = 20;
byte result = left + right; // valid: left + right is an int constant expression = 30
```

However:

```java
byte left = 10;
byte right = 20;
// byte result = left + right; // error: left/right are not constant variables
```

If a `final` variable is only assigned a value determined **at runtime** (for example, a method parameter), it is not automatically a constant variable in the sense the compiler uses here.

This is why we say "`byte` plus `byte` **usually** produces an `int`": in fact, **the addition expression always has type `int`** when both operands are `byte`; assigning the expression to a `byte` variable may be permitted due to the **constant expression exception**, not because the result type changed.

## 5. Casting to `byte`: keeps the low 8 bits and can change the sign

`byte narrowed = (byte) (a + b);` requests narrowing from `int` to `byte`. Java keeps the **lowest 8 bits** of the `int` value, then interprets them as a two's complement signed integer.

| Mathematical sum | `int` from `a + b` | Cast to `byte` | Notes |
| --- | ---: | ---: | --- |
| `10 + 20` | 30 | 30 | Within range |
| `100 + 50` | 150 | -106 | 150 - 256 = -106 |
| `120 + 120` | 240 | -16 | 240 - 256 = -16 |
| `-100 + (-50)` | -150 | 106 | Keeps low bits, flips sign |
| `127 + 1` | 128 | -128 | Crosses positive boundary |

```java
byte a = 100;
byte b = 50;
int trueSum = a + b;            // 150
byte narrowed = (byte) (a + b); // -106
```

This is not `int` overflowing when adding two `byte` values. **The `int` addition produces 150 accurately**, while the **cast** loses information because the target type only has 8 bits. Distinguishing where data loss occurs helps debug the true cause.

If you want to interpret a `byte` as an unsigned number from 0 to 255, you can use `Byte.toUnsignedInt(value)`. For example, `Byte.toUnsignedInt((byte) 0xFF)` returns 255; `byte` itself remains signed, and Java has no primitive type named `unsigned byte`.

## 6. Why do `b += n` and `b++` still compile?

**Compound assignment** operators such as `+=` have their own rule: evaluate the expression and convert the result back to the target variable's type. Therefore:

```java
byte b = 120;
b += 10;             // valid: 130 is narrowed to -126
// b = b + 10;        // error: b + 10 has type int, cannot auto-assign to byte
b = (byte) (b + 10); // valid if intentionally cast
```

An approximate way to understand the typing of `E1 op= E2` is `E1 = (T) ((E1) op (E2))`, where `T` is the type of variable `E1`; the key difference is that the left-hand side `E1` **is evaluated only once**. This is Java's compound assignment semantics, not because `b + 10` has type `byte`.

### Prefix/postfix `++` and `--`

`++` and `--` also have special rules for updating a variable, so they work with `byte`:

```java
byte b = 127;
byte old = b++; // old = 127; b = -128
byte now = ++b; // now = -127; b = -127
```

Unlike `+b` (whose result is `int` due to *unary numeric promotion*), the value of expressions `b++` and `++b` has **type `byte`** when `b` is `byte`. They automatically write back into the variable and can overflow when exceeding the range.

Although `b += 1` and `b++` may look similar to `b = b + 1`, they do not share the same assignment conversion rules. To avoid data-losing casts, keep calculations in `int` or validate the range before writing back to `byte`.

## 7. Does `Math.addExact` change the result back to `byte`?

No. `Math.addExact(int, int)` returns `int`, and Java automatically widens the two `byte` arguments to `int` when passing parameters:

```java
byte a = 100;
byte b = 50;
int sum = Math.addExact(a, b); // 150, still int
```

`Math.addExact` protects addition from overflow **in `int`** (or in `long` if the `long` overload is selected). It **does not** check whether the sum `150` still fits in the `byte` range. To ensure the value is within `byte` bounds, you still need to check `Byte.MIN_VALUE`/`Byte.MAX_VALUE` before casting.

You can write a helper with clear business intent:

```java
static byte addByteExactly(byte a, byte b) {
    int sum = a + b; // exact int addition for two bytes
    if (sum < Byte.MIN_VALUE || sum > Byte.MAX_VALUE) {
        throw new ArithmeticException("Byte overflow");
    }
    return (byte) sum;
}
```

This is **an illustrative method placed inside a class**, not a standalone program. It rejects sums outside the `byte` range instead of allowing wrap-around.

Because `byte` bounds are far smaller than `int`, two `byte` values can be safely added in `int` without needing `Math.addExact` for that addition itself. Checking the `byte` range is the decisive step if an API requires a `byte` result.

## 8. Numeric promotion in expression chains and method overloads

After the first addition, **the expression value already has type `int`**, so subsequent operations use that new type (unless an operand with a higher-ranking type appears under binary numeric promotion rules):

```java
byte a = 10, b = 20, c = 30;
int total = a + b + c;    // (int)(a+b) + c -> int 60
long longer = a + b + 1L; // final addition has long, result long
```

When `long` or floating-point numbers are present, the result type differs:

```java
byte a = 10;
byte b = 20;
long resultLong = a + 20L;      // long addition
float resultFloat = a + 20.0f; // float addition
double resultDouble = a + 20.0; // double addition
```

When combining large `int` values, pay attention to where widening happens:

```java
int max = Integer.MAX_VALUE;
long overflowed = max + 1;        // int addition overflows first, then widens
long correct = (long) max + 1;    // long addition, result 2147483648
```

Even though **adding two `byte` values cannot overflow `int`**, the principle regarding intermediate types still matters when an expression already has `int` or contains larger operands.

### `int` result affects method overloading

```java
static String classify(byte n) {
    return "byte";
}

static String classify(int n) {
    return "int";
}
```

If `a` and `b` have type `byte`:

- `classify(a)` selects the overload taking `byte`.
- `classify(a + b)` selects the overload taking `int`.
- `classify((byte) (a + b))` selects the overload taking `byte`.

These are illustrative methods to be placed inside a class. When Java picks an overload for `a+b`, it looks at the **compile-time `int` type of the expression**, rather than choosing the `byte` method just because the final value happens to fit in `byte`.

### `var` also infers from the expression type

```java
byte a = 10, b = 20;
var result = a + b; // result is inferred as int, not byte
```

`var` does not infer the "smallest type capable of holding the value"; it uses the initializer expression type already determined by the language.

## 9. Wrapper `Byte` and unboxing

`Byte` is a reference type (wrapper) distinct from primitive `byte`. If two `Byte` references are added, Java can **unbox** them to `byte` and then apply binary numeric promotion:

```java
Byte boxedA = Byte.valueOf((byte) 10);
Byte boxedB = Byte.valueOf((byte) 20);
int sum = boxedA + boxedB; // 30; unbox -> byte -> int -> add
```

You cannot automatically assign the `int` result to `Byte` via boxing alone:

```java
Byte boxedA = Byte.valueOf((byte) 10);
Byte boxedB = Byte.valueOf((byte) 20);
// Byte wrong = boxedA + boxedB; // error: int result does not auto-narrow then box
Byte ok = (byte) (boxedA + boxedB); // explicit narrowing then boxing
```

If either wrapper is `null`, the unboxing step can throw `NullPointerException` before the addition takes place. This is a runtime error, distinct from the compile-time error when trying to assign `int` to `byte`.

## 10. Distinguishing numeric addition from string concatenation when printing

Numeric addition produces an `int`, but the `+` operator is also used for string concatenation:

```java
byte a = 10, b = 20;
System.out.println("sum=" + a + b);   // sum=1020
System.out.println("sum=" + (a + b)); // sum=30
```

`+` associates left to right: the first statement starts with a `String`, producing `"sum=10"` and then concatenating `20`. The parentheses in the second statement force numeric addition `a + b` to run first, producing `int` `30`, which is then converted to a string.

This is not an issue of `byte` or `int` overflowing; it is a matter of **expression grouping and `+` operator overloading**.

## 11. Complete Java 17+ example verifying types and values

Create the file **`ByteAdditionDemo.java`**:

```java
public class ByteAdditionDemo {
    static String classify(byte value) {
        return "byte";
    }

    static String classify(int value) {
        return "int";
    }

    static byte addByteExactly(byte a, byte b) {
        int sum = a + b;
        if (sum < Byte.MIN_VALUE || sum > Byte.MAX_VALUE) {
            throw new ArithmeticException("Byte overflow");
        }
        return (byte) sum;
    }

    public static void main(String[] args) {
        byte a = 10;
        byte b = 20;
        int sum = a + b;
        System.out.println("sum=" + sum);
        System.out.println("firstType=" + classify(a));
        System.out.println("sumType=" + classify(a + b));
        System.out.println("castType=" + classify((byte) (a + b)));

        byte constant = 10 + 20;
        final byte f1 = 10;
        final byte f2 = 20;
        byte fromFinals = f1 + f2;
        System.out.println("constant=" + constant);
        System.out.println("fromFinals=" + fromFinals);

        byte largeA = 100;
        byte largeB = 50;
        System.out.println("wideSum=" + (largeA + largeB));
        System.out.println("narrowSum=" + (byte) (largeA + largeB));

        byte compound = 120;
        compound += 10;
        System.out.println("compound=" + compound);

        byte counter = 127;
        byte old = counter++;
        System.out.println("postOld=" + old);
        System.out.println("postCurrent=" + counter);

        var inferred = a + b;
        System.out.println("varType=" + classify(inferred));
        System.out.println("exactSmall=" + addByteExactly(a, b));

        try {
            addByteExactly(largeA, largeB);
            System.out.println("byteOverflow=missed");
        } catch (ArithmeticException ex) {
            System.out.println("byteOverflow=detected");
        }

        System.out.println("concatNoParen=" + a + b);
        System.out.println("concatWithParen=" + (a + b));

        Byte boxedA = Byte.valueOf((byte) 10);
        Byte boxedB = Byte.valueOf((byte) 20);
        System.out.println("boxedSum=" + (boxedA + boxedB));
    }
}
```

From the directory containing the file, run:

```bash
javac ByteAdditionDemo.java
java ByteAdditionDemo
```

Exact output:

```text
sum=30
firstType=byte
sumType=int
castType=byte
constant=30
fromFinals=30
wideSum=150
narrowSum=-106
compound=-126
postOld=127
postCurrent=-128
varType=int
exactSmall=30
byteOverflow=detected
concatNoParen=1020
concatWithParen=30
boxedSum=30
```

Through `sumType=int`, we observe the `int` type of `a + b` directly from the compiler's overload resolution. `constant` and `fromFinals` demonstrate the constant expression assignment exception. `wideSum` and `narrowSum` show that data loss happens when casting down to `byte`. `compound` and `postCurrent` show that update operators can narrow the result and wrap around.

## 12. Common pitfalls and takeaways

| Statement or code | Assessment | Reason |
| --- | --- | --- |
| "Two `byte` variables added together return `byte`." | False | Binary numeric promotion produces `int` |
| `byte r = a + b;` with ordinary variables `a`, `b` | Invalid | No automatic narrowing `int` → `byte` |
| `byte r = 10 + 20;` | Valid | Constant `int` expression equals 30, fits in `byte` |
| `final byte a=10,b=20; byte r=a+b;` | Valid | Two `final` variables initialized with constants form a constant expression |
| `int r = a + b;` | Valid | Matches the expression type, holds any sum of two `byte` values |
| `byte r = (byte)(a+b);` | Compiles | May lose data if sum is outside -128..127 |
| `byte b=120; b+=10;` | Compiles | Compound assignment narrows implicitly; b becomes -126 |
| `byte b=127; b++;` | Compiles | Update can wrap around to -128 |
| "`Math.addExact(a,b)` automatically returns `byte`." | False | For two `byte` arguments, the `int,int` overload returns `int` |
| "`var x = a+b` infers `byte`." | False | `var` infers the expression type: `int` |
| "`Byte + Byte` returns `Byte`." | False | Unboxing and numeric promotion make the result `int` |

When encountering addition on small integral types, ask yourself:

1. **What types are the operands?** `byte`, `short`, and `char` are promoted to `int` when using normal arithmetic `+`.
2. **What is the expression type?** Two `byte` values → `int`, even when the sum is small.
3. **Is the expression a compile-time constant?** If so and the result fits in `byte`, the special narrowing assignment may be valid.
4. **Where is the result assigned?** `int` preserves the value; casting to `byte` risks losing bits; `+=` and `++` have different write-back rules.
5. **Does the problem require rejecting `byte` range overflow?** Check the interval `[-128,127]` before casting, or keep the result as `int`.

**Conclusion:** `byte + byte` in Java has an **expression type of `int`** under *binary numeric promotion* rules. The constant expression exception only relaxes the condition for **assigning down to `byte`**, without changing the type of the addition itself. Knowing this distinction clearly helps prevent both compile errors and unintended bit truncation when casting or using compound assignment.