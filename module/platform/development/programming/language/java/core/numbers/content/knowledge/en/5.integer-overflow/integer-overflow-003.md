# Operation Type Is Determined Before Assigning the Result in Java

## 1. The Most Important Rule

In Java, **the type of an expression and its operations is determined by the operands and language rules before the result is assigned to the target variable**. A wider target variable cannot make an operation that already happened in a narrower type accurate again.

Example:

```java
int a = 50_000;
int b = 50_000;

long wrong = a * b;          // -1794967296, multiplication is performed in int.
long correct = (long) a * b; // 2500000000, multiplication is performed in long.
```

Mathematically, `50_000 × 50_000 = 2_500_000_000`. This value exceeds `Integer.MAX_VALUE = 2_147_483_647` yet fits within the `long` range. In `wrong`, multiplying **two `int` variables** produces an overflowed `int` result, and only then is that result converted to `long` for assignment. In `correct`, one operand is converted to `long` **before** multiplying, so the entire multiplication uses `long`.

Do not confuse two separate questions:

1. **What type does the operation run in?** Depends on the operand types, the operator, and *numeric promotion* rules.
2. **What variable type stores the result?** Depends on the receiving variable's type and conversion rules in an assignment context.

The type of the receiving variable is considered only after the right-hand expression produces a result; it **does not implicitly propagate backward into a binary operation that has already been typed**.

## 2. Step-by-Step: How Java Evaluates a Numeric Assignment

Consider:

```java
int x = 50_000;
int y = 50_000;
long result = x * y;
```

You can trace it sequentially:

1. The compiler sees that `x` and `y` both have type `int`.
2. The `*` operator applies *binary numeric promotion*: both operands remain `int`, so **the type of the expression `x * y` is `int`**.
3. At runtime, the `int` multiplication exceeds the limit and keeps the result under Java's 32-bit integer arithmetic: `-1_794_967_296`.
4. Upon assigning to `result`, Java performs a widening conversion `int → long`, preserving the existing negative value.
5. The final value of `result` is `-1_794_967_296L`.

In the expression `(long) x * y`, the left operand is converted to `long` from the start. *Binary numeric promotion* converts operand `y` to `long`, so the multiplication expression has type `long` and yields the exact `2_500_000_000L`.

**Type adjustment must happen before the operation that risks losing data.**

## 3. Binary Numeric Promotion: Rules for Choosing the Operation Type

Binary numeric operators such as `+`, `-`, `*`, `/`, and `%` apply *binary numeric promotion*. For operands of primitive integer and floating-point types, you can read it in order of precedence:

| Types Appearing in the Two Operands | Type Normally Used to Execute the Operation |
| --- | --- |
| Has `double` | `double` |
| No `double`, has `float` | `float` |
| No `double`/`float`, has `long` | `long` |
| Remaining: `byte`, `short`, `char`, `int` | `int` |

Examples:

```java
byte small = 10;
short other = 20;
int sum = small + other;  // int, because byte and short are promoted to int.

int units = 7;
long multiplier = 3L;
long product = units * multiplier; // long.

float f = 1.5F;
int n = 2;
float floatingResult = f * n; // float.

double d = 1.25;
float another = 2.0F;
double wideFloating = d + another; // double.
```

**Two details to remember:**

- `char` also belongs to the *integral* group and is promoted to `int` when participating in most ordinary arithmetic operations, even though its values are unsigned.
- `boolean` is not a numeric type and does not participate in *numeric promotion*. `"total=" + 42` is **string concatenation** with `+`, which has different semantics from adding two numbers.

This table describes common arithmetic operations. Do not apply it mechanically to every operator: bit-shift operators `<<`, `>>`, and `>>>` use **unary numeric promotion** on each operand individually, and the result type depends on the promoted type of the **left** operand; numeric comparison operators return `boolean`; the conditional operator `?:` has its own typing rules. The common principle is that each expression must be analyzed according to its own operator, rather than relying on the final receiving variable's type.

## 4. Overflow Happens Before Widening the Result Type

### 4.1. Adding `int` into `long`

```java
int max = Integer.MAX_VALUE;

long tooLate = max + 1;        // -2147483648
long onTime = (long) max + 1;  // 2147483648
long withLongLiteral = max + 1L; // 2147483648
```

On the right-hand side, `max + 1` is an `int + int` addition; it overflows at `2_147_483_647 + 1`. Afterward, converting to `long` merely keeps the overflowed negative value. Adding `(long)` **to an operand** or using `1L` makes the addition happen in `long` from the start.

### 4.2. Multiplication with a misplaced cast

Compare:

```java
int width = 50_000;
int height = 50_000;

long a = (long) (width * height); // Defeats the purpose: int multiplies first, then casts.
long b = ((long) width) * height; // Correct: long multiplication from the start.
```

The parentheses in `(long) (width * height)` cause the multiplication to happen before the cast. To widen the operation's range, cast **an operand**, not just **the already-computed expression result**.

### 4.3. Promoting to `long` still has limits

If the result truly exceeds the `long` range, using `long` alone can still overflow:

```java
long max = Long.MAX_VALUE;
long overflowed = max + 1L; // Long.MIN_VALUE.
```

Do not use `double` as a default substitute for large integers that require exact calculation: although `double`'s magnitude range is larger than `long`, it has finite precision and can round large integers. When exact integers beyond 64 bits are needed, use `BigInteger` and **convert each operand before performing the large operation**.

## 5. Expression Type Also Determines Integer Division and Truncation

Not only overflow: the same evaluation-before-assignment principle causes different results in division as well.

```java
int numerator = 1;
int denominator = 2;

double wrong = numerator / denominator;           // 0.0
double correct = (double) numerator / denominator; // 0.5
double alsoCorrect = numerator / 2.0;             // 0.5
```

In `numerator / denominator`, both operands are `int`, so Java performs **integer division**, discards the fractional part to get `0`, and only then widens that value to `0.0` when assigning to `double`.

With `(double) numerator / denominator`, the division is promoted to `double` before executing, so the result is `0.5`. This is completely different from writing `(double) (numerator / denominator)`, because casting after dividing merely turns `0` into `0.0`.

Similarly, if you write `float result = 1 / 2;`, the result is `0.0F`, not `0.5F`.

**Note:** integer division with a zero divisor causes `ArithmeticException`. Assigning the result to `double` cannot turn an exception that already occurred in `int / int` division into `Infinity`.

## 6. Narrow Types Are Promoted to `int` Even When the Target Variable Is `byte` or `short`

Many people think adding two `byte` values produces a `byte`. In reality, when using the ordinary addition operator, Java promotes them to `int`:

```java
byte x = 10;
byte y = 20;
int sum = x + y; // Valid: expression type is int.

// byte invalid = x + y; // Compile error: int does not implicitly narrow to byte.
byte narrowed = (byte) (x + y); // Explicit cast.
```

Casting can lose data when the value exceeds the `byte` range ([-128, 127]):

```java
byte x = 100;
byte y = 30;
int exact = x + y;             // 130
byte narrowed = (byte) (x + y); // -126
```

The value `130` is outside the `byte` range; casting to `byte` keeps the low bits and interprets the signed result as `-126`. Storing the result in `int` preserves the exact `130`.

### Exception: assigning a compile-time constant expression

Java allows certain assignments from an `int` **constant expression** (and in specified cases, other constant types) to `byte`/`short`/`char` without a cast if the constant value is representable in the target type:

```java
byte a = 10 + 20;      // Valid: constant int expression has value 30.
byte b = 127;          // Valid: constant value within byte range.
// byte c = 100 + 30; // Error: constant value 130 exceeds byte range.

int external = 20;
// byte d = 10 + external; // Error: int result, not a constant expression.
```

This is an **assignment conversion rule for in-range constant expressions**; it does not mean `byte` addition suddenly executes in `byte`. When operands are ordinary variables and results depend on runtime, do not rely on this exception.

## 7. Compound Assignment and Increment/Decrement Operators: Cases Requiring Special Care

Operators `+=`, `-=`, `*=`, `/=`, and `%=` follow their own rules, including an **implicit cast to the left-hand type**. For example, `E1 += E2` is essentially equivalent to `E1 = (T) ((E1) + (E2))`, where `T` is the type of `E1`; however, `E1` is evaluated only once.

```java
byte count = 100;

// count = count + 30; // Compile error: count + 30 has type int.
count += 30;           // Valid: adds as int, then narrows back to byte.
System.out.println(count); // -126
```

Therefore, `count += 30` is **no safer than** `count = (byte) (count + 30)` regarding data loss. The shorter syntax can hide a narrowing cast happening silently.

The `++` and `--` operators also have their own typing rules and can be applied to `byte`/`short`/`char` variables. For example, when `byte value = 127; value++;`, `value` becomes `-128` due to exceeding the limit. Do not infer from the fact that `value++` compiles that `byte next = value + 1;` must also compile.

## 8. Subexpressions and Evaluation Order: One Cast Cannot Save an Entire Expression

Java types and evaluates subexpressions according to syntactic structure. If one subexpression has already overflowed in `int`, converting *another* expression to `long` later does not restore the data.

```java
int a = 50_000, b = 50_000;
long factor = 2L;

long wrong = (a * b) * factor; // -3589934592
long correct = ((long) a * b) * factor; // 5000000000
```

In `(a * b) * factor`, `a * b` already yielded `-1_794_967_296` in `int`. Only when multiplying next by `factor` does Java convert this negative result to `long`. In `correct`, the first multiplication uses `long`, so the result is kept accurately before the next multiplication.

Similarly, `(long) (a * b)` is also too late; you need `(long) a * b` or `a * (long) b` to widen **before the first multiplication**.

For complex expressions, split steps into intermediate variables with explicit types:

```java
long area = (long) width * height;
long volume = area * depth;
```

The two lines above assume `width`, `height`, and `depth` are already declared; this is an illustrative snippet, not a standalone program. Splitting like this helps identify which operation could exceed `long` and needs extra checks.

## 9. How to Detect Overflow and Preserve Exact Integers

### 9.1. Use an appropriately wide type at the time of the operation

If the result is provably within the `long` range, **widen one operand** or use a `long` literal before addition/multiplication:

```java
int quantity = 1_000_000;
int unitPrice = 25_000;
long total = (long) quantity * unitPrice; // 25000000000
```

Every `int` value converts accurately to `long`, yet **each operation** still needs range control on its result. In particular, `long` is not an unbounded integer type.

### 9.2. Use overflow-checking operations when overflow is an error

The methods `Math.addExact`, `Math.subtractExact`, `Math.multiplyExact`, `Math.negateExact`, and `Math.toIntExact` detect when the operations/conversions they support cannot represent the result. When overflowing, they throw `ArithmeticException`.

```java
int a = 50_000, b = 50_000;

try {
    int product = Math.multiplyExact(a, b);
    System.out.println(product);
} catch (ArithmeticException ex) {
    System.out.println("int multiplication exceeded value range");
}
```

Not every integer expression automatically throws an exception on overflow. For example, ordinary `a * b` merely *wraps around*; to detect it, you must use checked APIs or check bounds beforehand.

Note that `Math.multiplyExact((long) a, b)` returns `long` and also checks for overflow relative to `long`. If the calculation fits within the `long` range, using `long` from the start is sufficient.

### 9.3. Use `BigInteger` when 64 bits are not enough

`BigInteger` represents arbitrary-precision integers within memory/resource limits, with operations performed via methods:

```java
import java.math.BigInteger;

BigInteger x = BigInteger.valueOf(Long.MAX_VALUE);
BigInteger y = x.add(BigInteger.ONE);
System.out.println(y); // 9223372036854775808
```

Importantly, convert the **operands** before computing:

```java
long max = Long.MAX_VALUE;
BigInteger correct = BigInteger.valueOf(max).add(BigInteger.ONE);
// BigInteger tooLate = BigInteger.valueOf(max + 1); // max + 1 already overflowed long.
```

`BigInteger` is an immutable class: `add`/`multiply` return a new result object. Do not use the `+` or `*` operators to add or multiply two `BigInteger` objects.

## 10. Standalone Runnable Java 17+ Example

Create the file **`ExpressionTypeBeforeAssignment.java`**:

```java
import java.math.BigInteger;

public class ExpressionTypeBeforeAssignment {
    public static void main(String[] args) {
        int a = 50_000;
        int b = 50_000;

        long tooLate = a * b;
        long widenedBeforeMultiply = (long) a * b;
        long castAfterMultiply = (long) (a * b);

        System.out.println("int product then long = " + tooLate);
        System.out.println("long before multiply = " + widenedBeforeMultiply);
        System.out.println("cast after multiply = " + castAfterMultiply);

        int max = Integer.MAX_VALUE;
        long sumTooLate = max + 1;
        long sumCorrect = max + 1L;
        System.out.println("int sum then long = " + sumTooLate);
        System.out.println("long sum = " + sumCorrect);

        double dividedAsInt = 1 / 2;
        double dividedAsDouble = 1 / 2.0;
        System.out.println("int division then double = " + dividedAsInt);
        System.out.println("double division = " + dividedAsDouble);

        byte count = 100;
        count += 30;
        System.out.println("byte compound assignment = " + count);

        try {
            Math.multiplyExact(a, b);
        } catch (ArithmeticException ex) {
            System.out.println("checked int multiplication overflow");
        }

        BigInteger precise = BigInteger.valueOf(a)
                .multiply(BigInteger.valueOf(b));
        System.out.println("BigInteger product = " + precise);
    }
}
```

Compile and run:

```bash
javac ExpressionTypeBeforeAssignment.java
java ExpressionTypeBeforeAssignment
```

Output:

```text
int product then long = -1794967296
long before multiply = 2500000000
cast after multiply = -1794967296
int sum then long = -2147483648
long sum = 2147483648
int division then double = 0.0
double division = 0.5
byte compound assignment = -126
checked int multiplication overflow
BigInteger product = 2500000000
```

This is a complete program requiring no external libraries outside the JDK. `tooLate`/`castAfterMultiply` differ from `widenedBeforeMultiply` only in where the type conversion is placed, yet the results are completely different. The two divisions also clearly prove: a `double` target type does not turn `int / int` division into floating-point division.

## 11. Common Mistakes and How to Self-Check

| Common Claim | Why It Is Wrong | Correct Approach |
| --- | --- | --- |
| "Assigning `int * int` to `long` won't overflow." | `int` multiplication occurs before assignment. | `(long) a * b`. |
| "Casting the whole expression at the end still preserves the result." | Casting cannot recover lost bits. | Cast an operand before the overflowing operation. |
| "A `double` target variable turns `1 / 2` into `0.5`." | `1 / 2` is integer division yielding `0` before converting to `double`. | `1.0 / 2` or `(double) 1 / 2`. |
| "Adding two `byte`s always yields `byte`." | Addition promotes operands to `int`. | Store in `int`, or cast with range checks. |
| "The `+=` operator never loses data because it needs no cast." | Compound assignment includes an implicit narrowing cast. | Check the value range explicitly or use a wider type. |
| "Passing an already-overflowed operation to `BigInteger` fixes it." | `BigInteger.valueOf(a * b)` receives the already-overflowed primitive value. | `BigInteger.valueOf(a).multiply(BigInteger.valueOf(b))`. |
| "Whenever you see `+`, the numeric promotion table applies." | `+` can also be string concatenation; other operators have their own rules. | Identify the operator and the type of each operand/subexpression. |

When reading a long expression, determine **the type of each operand**, **the type of each operation**, **where conversions occur**, and **the limits of the active computation type** before looking at **the receiving variable's type**. Pay special attention to `int × int` assigned to `long`, `int / int` assigned to `double`, and compound assignments on `byte`/`short`.

**Remember:** *The receiving variable's type determines how the computed result is stored; the expression's type determines how the calculation takes place.* If you need to keep exact results, choose and convert types **before an operation that risks overflow or truncation**, or use overflow-checking methods / large integer types.

**References:** [Java Language Specification §5.6 — Numeric Contexts](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.6), [§5.2 — Assignment Contexts](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.2), [§15.17 — Multiplicative Operators](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.17), [§15.18 — Additive Operators](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.18), [§15.26.2 — Compound Assignment Operators](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.26.2).
