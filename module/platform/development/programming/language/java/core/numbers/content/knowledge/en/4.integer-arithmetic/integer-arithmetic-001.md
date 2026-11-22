# Addition, Subtraction, Multiplication, and Result Types in Java Integer Arithmetic

## 1. The Key Question: Which Type Does the Operation Run As?

For integer expressions in Java, **the type of the result is determined by the operands and numeric promotion rules**. The type of the variable on the **left-hand side of an assignment** does not automatically make an addition, subtraction, or multiplication on the right-hand side run in a wider type.

For example:

```java
int a = 1_500_000_000;
int b = 2;

int wrapped = a * b;        // int multiplication, overflows
long stillWrapped = a * b;  // multiplication is still int, then converted to long
long correct = (long) a * b; // long multiplication, exact result
```

Here, the mathematical value of \(1\,500\,000\,000 \times 2\) is \(3\,000\,000\,000\), which is greater than `Integer.MAX_VALUE`. The first two `a * b` expressions have **type `int`** and both yield `-1_294_967_296` due to overflow; the `long` variable merely holds the sign-extended version of the already-overflowed result. The expression `(long) a * b` is performed using `long` and yields `3_000_000_000`.

This lesson focuses on three binary operators:

- `+`: addition.
- `-`: subtraction.
- `*`: multiplication.

They apply to the integer types `byte`, `short`, `char`, `int`, and `long`. For primitive operands, you must understand **promotion**, **value ranges**, **overflow**, **type conversion**, and **evaluation order** to accurately predict results.

## 2. Type Promotion Rules for Addition, Subtraction, and Multiplication

### 2.1. Binary Numeric Promotion

For two operands of primitive integral types, Java applies these core rules:

1. `byte`, `short`, and `char` are **promoted to `int`** before performing addition, subtraction, or multiplication.
2. If either operand is `long`, the other operand is converted to `long`, and **the result has type `long`**.
3. If neither is `long`, the result has **type `int`**.

Summary table:

| Left operand type | Right operand type | Type of `a + b`, `a - b`, `a * b` |
|---|---|---|
| `byte` | `byte` | `int` |
| `short` | `short` | `int` |
| `byte` | `short` | `int` |
| `char` | `char` | `int` |
| `char` | `int` | `int` |
| `int` | `int` | `int` |
| `int` | `long` | `long` |
| `long` | `long` | `long` |

The rule does not depend on **whether the actual values are currently small or large**. For example, with `byte x = 1; byte y = 2;`, `x + y` has type `int` even though `3` fits completely within the `byte` range.

Within the scope of this lesson, only integral operands are considered. If an operand is `float` or `double`, the broader *binary numeric promotion* rules produce a floating-point result; do not use the table above to reason about expressions mixing integers and floating-point numbers.

### 2.2. Expression Type vs. Receiving Variable Type

```java
byte first = 10;
byte second = 20;

// byte sum = first + second; // ERROR: addition result has type int
int sum = first + second;     // valid, sum = 30
byte narrowed = (byte) (first + second); // valid with explicit cast

long x = 1L + 2;  // 1L is long => addition yields long
long y = 1 + 2;   // addition yields int (3), then widened to long
```

The line `long y = 1 + 2;` works correctly because `3` does not overflow, but you should not conclude that the addition was computed using `long`.

### 2.3. Unary Plus/Minus Also Promotes

The sign operators `+x` and `-x` take only **one operand**. When `x` is `byte`, `short`, or `char`, the unary sign result has type `int`; `long` remains `long`.

```java
byte b = 5;
int negative = -b;   // -b has type int, value -5
char c = 'A';
int code = +c;       // +c has type int, value 65
long n = 10L;
long flipped = -n;   // type long, value -10
```

Do not equate unary `-x` with binary `a - b`; both can overflow if the mathematical result exceeds their respective representable ranges.

## 3. How Addition, Subtraction, and Multiplication Work

### 3.1. Addition (`+`)

The operation `a + b` computes the sum. For example, `7 + 5` is `12`. When both operands are `int`, the operation is performed in the 32-bit integer domain. If either is `long`, the operation is performed in the 64-bit domain.

The `+` sign is also used for **string concatenation**: `"total=" + 5` produces the string `"total=5"`. This is not integer addition; always check the operand types before reasoning about `+`. For example, `"sum=" + 2 + 3` produces `"sum=23"` because operations evaluate from left to right; `"sum=" + (2 + 3)` is needed to produce `"sum=5"`.

### 3.2. Subtraction (`-`)

The operation `a - b` computes the difference; `7 - 5` is `2`. When subtracting a negative number, the mathematical value can increase; for example, `7 - (-5)` equals `12`. Do not only check cases of adding positive numbers when evaluating overflow risk: `Integer.MIN_VALUE - 1` also overflows.

### 3.3. Multiplication (`*`)

The operation `a * b` computes the product; `7 * 5` is `35`. Multiplication easily exceeds the range even when **every operand is valid**. For example, an operand of `1_500_000_000` is a valid `int`, yet its product with `2` no longer fits in `int`.

Zero is the absorbing element of integer multiplication: `x * 0` is always `0`. One is the identity element: `x * 1` has the same value `x`. However, the expression result still follows type promotion rules; multiplying `byte x` by `1` yields an expression of type `int`.

## 4. Precedence, Associativity, and Evaluation Order

Multiplication `*` has **higher precedence** than addition/subtraction `+`, `-`; addition and subtraction share the same level and associate from left to right:

```java
int a = 2 + 3 * 4;   // 14
int b = (2 + 3) * 4; // 20
int c = 10 - 3 - 2;  // (10 - 3) - 2 = 5
int d = 10 - (3 - 2); // 9
```

Java evaluates the operands of a binary operator in **left-to-right order**; in `a() + b()`, `a()` is evaluated before `b()`. This is operand evaluation order and does not alter operator precedence.

In addition, **integer operations can overflow**, so algebraic transformations are only safe if they preserve business meaning. For example, to avoid overflow, `(long) a + b` differs from `(long) (a + b)` when the `int` sum exceeds the range. Both look almost algebraically identical, but the timing of type promotion differs.

## 5. Runnable Java Example: Result Values and Types

Create a file `IntegerArithmeticDemo.java`:

```java
public class IntegerArithmeticDemo {
    private static String typeOf(int value) {
        return "int";
    }

    private static String typeOf(long value) {
        return "long";
    }

    public static void main(String[] args) {
        byte smallA = 120;
        byte smallB = 10;
        short shortA = 30_000;
        short shortB = 1_000;
        char letter = 'A';
        int big = 1_500_000_000;
        int multiplier = 2;

        System.out.println("byte + byte = " + (smallA + smallB));
        System.out.println("type byte + byte = " + typeOf(smallA + smallB));
        System.out.println("short * short = " + (shortA * shortB));
        System.out.println("char + int = " + (letter + 1));
        System.out.println("type char + int = " + typeOf(letter + 1));
        System.out.println("type int + long = " + typeOf(1 + 2L));
        System.out.println("int * int = " + (big * multiplier));
        System.out.println("assigned to long = " + (long) (big * multiplier));
        System.out.println("long * int = " + ((long) big * multiplier));
        System.out.println("max + 1 = " + (Integer.MAX_VALUE + 1));
        System.out.println("min - 1 = " + (Integer.MIN_VALUE - 1));
        System.out.println("2 + 3 * 4 = " + (2 + 3 * 4));
        System.out.println("(2 + 3) * 4 = " + ((2 + 3) * 4));
    }
}
```

Compile and run with Java 17+:

```bash
javac IntegerArithmeticDemo.java
java IntegerArithmeticDemo
```

Exact output:

```text
byte + byte = 130
type byte + byte = int
short * short = 30000000
char + int = 66
type char + int = int
type int + long = long
int * int = -1294967296
assigned to long = -1294967296
long * int = 3000000000
max + 1 = -2147483648
min - 1 = 2147483647
2 + 3 * 4 = 14
(2 + 3) * 4 = 20
```

The two overloaded `typeOf` methods exist solely to **demonstrate the static type chosen by the compiler**: if the argument is `int`, `typeOf(int)` is called; if it is `long`, `typeOf(long)` is called. The numbers `130` and `30_000_000` prove that the results of `byte + byte` and `short * short` are computed in `int`, rather than automatically constrained to the `byte`/`short` range.

## 6. Overflow and Underflow: Wraparound at Fixed Width

### 6.1. Relevant Representable Ranges

| Operation result type | Signed range |
|---|---|
| `int` (32 bit) | -2_147_483_648 to 2_147_483_647 |
| `long` (64 bit) | -9_223_372_036_854_775_808 to 9_223_372_036_854_775_807 |

For integer `+`, `-`, and `*`, Java computes the result according to **the width of the operation's type**. If the mathematical result falls outside the signed type's range, the high bits exceeding the width are discarded and the remaining bit pattern is interpreted in two's complement. You can think of the result as being taken modulo \(2^{32}\) for `int` or \(2^{64}\) for `long`, and then interpreted as signed.

For example:

- `Integer.MAX_VALUE + 1` → `Integer.MIN_VALUE`.
- `Integer.MIN_VALUE - 1` → `Integer.MAX_VALUE`.
- `1_500_000_000 * 2` → `-1_294_967_296` (`int` multiplication).
- `Long.MAX_VALUE + 1L` → `Long.MIN_VALUE`.

Both **overflow** (exceeding the maximum bound) and **negative-side underflow** (falling below the lower bound) can corrupt expected values in integer arithmetic. Standard `+`, `-`, and `*` operations **do not automatically throw an exception** when out of range.

### 6.2. Widening Before vs. After the Operation

For an operation to run in `long`, at least one operand must be `long` **before the operator executes**:

```java
int a = 1_500_000_000;
int b = 2;

long wrong = a * b;             // -1294967296 (int already overflowed)
long alsoWrong = (long) (a * b); // -1294967296
long right = (long) a * b;      // 3000000000
long alsoRight = a * 2L;        // 3000000000
```

Assigning to `long` after the operation does not recover lost bits. Even `long` has limits: if the product is greater than `Long.MAX_VALUE` or less than `Long.MIN_VALUE`, `long` multiplication can still overflow.

### 6.3. Negating the Minimum Value Still Overflows

The signed range is **asymmetric**: `Integer.MIN_VALUE` is `-2_147_483_648`, whereas `Integer.MAX_VALUE` is only `2_147_483_647`. Therefore:

```java
int min = Integer.MIN_VALUE;
System.out.println(-min);              // -2147483648
System.out.println(min * -1);           // -2147483648
System.out.println(Math.abs(min));      // -2147483648
```

None of these produce a positive number as mathematical intuition expects, because `+2_147_483_648` does not exist in the `int` range. `Long.MIN_VALUE` shares the same property for `long`.

## 7. Detecting Overflow with `Math.*Exact` Methods

If overflow is a **business error**, Java provides checked arithmetic operations:

| Method | Purpose |
|---|---|
| `Math.addExact(a, b)` | Adds, throws `ArithmeticException` on overflow |
| `Math.subtractExact(a, b)` | Subtracts, throws exception on overflow |
| `Math.multiplyExact(a, b)` | Multiplies, throws exception on overflow |
| `Math.negateExact(value)` | Negates, throws exception for the minimum value |
| `Math.toIntExact(longValue)` | Narrows `long` to `int`, throws exception if out of range |

`addExact`, `subtractExact`, and `multiplyExact` have overloads for integers of matching widths; the return type of the overload taking two `int`s is `int`, and two `long`s is `long`. `Math.multiplyExact` also has an overload for `long` and `int` in modern Java.

Create a file `CheckedArithmeticDemo.java`:

```java
public class CheckedArithmeticDemo {
    public static void main(String[] args) {
        System.out.println("safe sum = " + Math.addExact(7, 5));
        System.out.println("safe diff = " + Math.subtractExact(7, 5));
        System.out.println("safe product = " + Math.multiplyExact(7, 5));

        try {
            Math.addExact(Integer.MAX_VALUE, 1);
        } catch (ArithmeticException e) {
            System.out.println("addExact: overflow");
        }

        try {
            Math.subtractExact(Integer.MIN_VALUE, 1);
        } catch (ArithmeticException e) {
            System.out.println("subtractExact: overflow");
        }

        try {
            Math.multiplyExact(1_500_000_000, 2);
        } catch (ArithmeticException e) {
            System.out.println("multiplyExact: overflow");
        }

        long exactLong = (long) 1_500_000_000 * 2;
        System.out.println("long product = " + exactLong);

        try {
            Math.toIntExact(exactLong);
        } catch (ArithmeticException e) {
            System.out.println("toIntExact: outside int range");
        }
    }
}
```

Compile and run:

```bash
javac CheckedArithmeticDemo.java
java CheckedArithmeticDemo
```

Output:

```text
safe sum = 12
safe diff = 2
safe product = 35
addExact: overflow
subtractExact: overflow
multiplyExact: overflow
long product = 3000000000
toIntExact: outside int range
```

**Do not catch `ArithmeticException` and then continue using an already-corrupted numeric result.** Define appropriate error handling: report out-of-range input, reject the calculation, or switch to a wider numeric representation.

If business logic requires integers beyond even the `long` range, use `java.math.BigInteger`:

```java
import java.math.BigInteger;

BigInteger a = BigInteger.valueOf(Long.MAX_VALUE);
BigInteger bigger = a.add(BigInteger.ONE);  // 9223372036854775808
BigInteger squared = bigger.multiply(bigger);
```

This `BigInteger` snippet only illustrates **expressions placed inside a method**, not a standalone Java file. `BigInteger` uses methods like `add`, `subtract`, and `multiply` and does not support the `+`/`-`/`*` operators on two objects.

## 8. Assignment, Casting, and Compound Assignment Operators

### 8.1. Regular Assignment Requires Compatible Types

```java
byte x = 10;
byte y = 20;

// byte total = x + y; // COMPILE ERROR: x + y is int
int total = x + y;     // valid
byte narrowed = (byte) (x + y); // explicit cast
```

If the `int` sum is outside the `byte` range, the cast keeps only the lower 8 bits and can **change the value**:

```java
byte x = 120;
byte y = 10;
byte result = (byte) (x + y); // 130 -> -126
```

### 8.2. `+=`, `-=`, and `*=` Perform an Implicit Cast

With compound assignment operators, Java performs the operation on the promoted operands and then **converts the result back to the type of the left-hand variable**, similar to:

```java
// For a variable of type T:
x += y;          // roughly equivalent to: x = (T) (x + y)
x -= y;          // roughly equivalent to: x = (T) (x - y)
x *= y;          // roughly equivalent to: x = (T) (x * y)
```

The letter `T` is just a type placeholder in **illustrative pseudocode**. The two forms are not strictly equivalent when `x` is an expression with side effects: compound assignment **evaluates the left-hand side only once**. The key point to remember here is that the implicit cast can drop bits.

For example:

```java
byte b = 120;
b += 10;  // equivalent in value to (byte) (120 + 10)
System.out.println(b); // -126

short s = 30_000;
s *= 2; // multiplication yields int, then narrowed to short
System.out.println(s); // -5536
```

In the `short` example, `60_000` exceeds the `short` range (`-32_768..32_767`), and keeping the lower 16 bits yields `-5_536`. **`+=` and `*=` do not automatically guard against overflow or type narrowing.**

### 8.3. Compile-Time Constant Expressions Are an Exception to Know

Java allows certain `int` **constant expressions** to be assigned directly to `byte`, `short`, or `char` if the value is representable:

```java
byte a = 100 + 20;       // valid: int constant expression equals 120
short b = 10_000 * 3;    // valid: int constant equals 30000
char c = 'A' + 1;        // valid: int constant equals 66, within char range

// byte bad = 100 + 30;  // compile error: 130 exceeds byte range

int variable = 20;
// byte another = 100 + variable; // error: no longer a representable constant
```

The line `char c = 'A' + 1;` compiles because the result is the **`int` constant `66`**, which is allowed to undergo narrowing conversion at the assignment step. It does **not** prove that the addition operator on `char` returns `char`: the type of the addition expression is still `int`. A regular non-compile-time-constant `char current` that needs to be incremented with `+` and assigned back to `char` will require a cast or `+=`.

## 9. Combining with Literals, Wrappers, and Autoboxing

### 9.1. Literals Determine the Intermediate Type

```java
long a = 2_000_000_000 + 1_000_000_000;  // int addition overflows
long b = 2_000_000_000L + 1_000_000_000; // long addition = 3000000000
```

The `L` suffix makes the first literal a `long`, so the remaining operand is promoted to `long` and the addition result has type `long`. If you want an explicit cast, write `(long) first + second` instead of `(long) (first + second)`.

### 9.2. Wrappers Are Unboxed Before Computing

When using `Integer`, `Long`, or other wrappers in arithmetic expressions, Java can **unbox** them to primitive values and then apply numeric promotion:

```java
Integer a = 10;
Long b = 20L;
long sum = a + b; // unboxes int/long, promotes to long => 30
```

If a wrapper is `null`, unboxing throws a `NullPointerException` **before the operation completes**. Therefore, check for null when wrapper data may be absent.

Do not use `Integer`/`Long` expecting automatic overflow protection: after unboxing, operations are still subject to the `int`/`long` ranges respectively.

## 10. Safe Usage in Programs

There are three main scenarios:

**Scenario A — the operation is guaranteed to fit in `int`:** use `int` normally, based on verifiable input domain constraints. For example, two small counts in the range `0..1000` will have a sum of at most `2000`.

**Scenario B — `int` might overflow, but `long` is wide enough:** proactively widen an operand **before computing**, such as `long total = (long) quantity * unitPrice;` when both source variables are `int`. Check additional business constraints if `long` could also exceed its range.

**Scenario C — overflow must be detected:** use `Math.addExact`, `subtractExact`, `multiplyExact`, or design the data with `BigInteger` when the range is unbounded. Do not treat an overflowed calculation result as valid data if business rules do not specify wraparound semantics.

For requirements involving byte counts, durations, total amounts, or `quantity * unitPrice`, determine the **maximum valid value** before choosing a type. If decimal monetary amounts are needed, currency precision is a separate concern: typically consider `BigDecimal` or storing the smallest currency unit as an integer under an explicit convention.

## 11. Common Mistakes

| Symptom | Cause | Fix |
|---|---|---|
| `byte result = a + b;` fails to compile | `byte + byte` produces type `int` | Use `int` or cast with range checking |
| `long total = a * b;` is still wrong | Two `int`s multiply first, then assign to `long` | Write `(long) a * b` |
| `Integer.MAX_VALUE + 1` becomes negative | 32-bit `int` overflow | Use `long` before addition or `addExact` |
| `Integer.MIN_VALUE - 1` becomes positive | Exceeds negative `int` limit | Use a wider type or `subtractExact` |
| `-Integer.MIN_VALUE` remains negative | Symmetric positive value is outside `int` range | Use `negateExact` or convert to `long` first |
| `b += 10` turns `byte` negative | Compound assignment implicitly narrows the result | Compute in `int`, check range before casting |
| `Math.multiplyExact(a, b)` throws | Product exceeds the overload's type range | Choose `long`/`BigInteger` or handle overflow |
| `"sum=" + 2 + 3` prints `sum=23` | `+` operator concatenates strings left to right | Write `"sum=" + (2 + 3)` |
| Arithmetic on wrappers throws `NullPointerException` | Unboxing a `null` value | Check wrappers for null before the operation |

## 12. Self-Check

**Q1.** With `byte a = 1; byte b = 2;`, what is the type of `a * b`?  
**Answer:** `int`, even though the product is `2` and fits in `byte`.

**Q2.** With `short a = 100; short b = 20;`, what is the type of `a - b`?  
**Answer:** `int`, with value `80`.

**Q3.** What value does `long x = Integer.MAX_VALUE + 1;` hold?  
**Answer:** `-2_147_483_648`, because adding two `int`s overflows before assigning to `long`.

**Q4.** Write an expression that multiplies two `int` variables `price` and `count` using `long` arithmetic.  
**Answer:** `(long) price * count` or `price * (long) count`.

**Q5.** What does `byte b = 120; b += 10;` produce?  
**Answer:** `-126`, because the addition expression in `int` yields `130`, which is then narrowed to `byte`.

**Q6.** When is `Math.multiplyExact` more appropriate than `*`?  
**Answer:** When a product exceeding the integer range must be treated as an error and detected via `ArithmeticException`.

**Q7.** Why is `char c = 'A' + 1;` valid while `charVariable + 1` has type `int`?  
**Answer:** Both additions produce type `int`. In the first case, the result is the `int` constant `66` within the `char` range, so the compiler permits the special narrowing assignment.

**Q8.** How do `10 - 3 - 2` and `10 - (3 - 2)` differ?  
**Answer:** They evaluate to `5` and `9` respectively, because binary `-` is left-associative; parentheses change the order of operations.

**Key Takeaway:** For Java integers, **`byte`/`short`/`char` are promoted to `int` for addition, subtraction, and multiplication; if `long` is present, the result is `long`**. The result is computed in the type of the **expression** before assignment. To avoid overflow, widen the type **before the operation** or use `Math.*Exact` to detect and handle out-of-range results.
