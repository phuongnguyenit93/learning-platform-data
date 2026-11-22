# Promote Operands Before Multiplication Instead of Casting Afterward in Java

A common mistake when working with Java integers is computing the product of two `int` values and then **assigning the result to a `long`**, expecting Java to preserve the full result automatically:

```java
int quantity = 50_000;
int unit = 50_000;
long total = quantity * unit;       // Wrong value: -1794967296
```

The mathematical product is **2,500,000,000**, which is larger than `Integer.MAX_VALUE` (2,147,483,647) yet still within the `long` range. However, **the type of a multiplication expression is determined from its operands before the multiplication takes place**. Both operands are `int`, so Java multiplies in `int`, overflows, and only then widens the *wrong result* to `long`.

The solution is to **promote at least one operand to `long` before the multiplication**:

```java
long correct = (long) quantity * unit; // 2500000000
```

The difference does not lie in whether the `total` variable is wide enough, but in the **timing of the type conversion** relative to the **timing of the multiplication**.

## 1. How Does Java Decide the Type of a Multiplication?

For the arithmetic expression `a * b`, Java applies **binary numeric promotion**:

| Types of the Two Operands | Computation/Result Type of `*` | Example |
| --- | --- | --- |
| `byte` and `byte` | `int` | `byte` is promoted to `int` |
| `short` and `short` | `int` | `short` is promoted to `int` |
| `byte` and `int` | `int` | At least `int` |
| `int` and `int` | `int` | Can overflow when the product exceeds `int` range |
| `int` and `long` | `long` | The `int` operand is promoted to `long` |
| `long` and `long` | `long` | Can still overflow if the product exceeds `long` range |
| Has a `float` or `double` operand | Per floating-point promotion rules | Larger range may come with precision loss |

This lesson focuses on **signed integer** multiplication. The widths of the relevant types are 8 bits for `byte`, 16 bits for `short`, 32 bits for `int`, and 64 bits for `long`; `byte * byte` and `short * short` are computed in at least `int`.

The mathematical result of `int * int` can require up to 64 bits to be represented completely. Java **does not automatically promote `int * int` to `long` just because the result is too large**. With ordinary primitive integer operators, overflowing multiplication **does not automatically throw an exception**: high bits beyond the width are discarded and the remaining bit pattern is interpreted as a signed number.

For example:

- `50_000 * 50_000` equals **2,500,000,000** mathematically.
- That value exceeds `Integer.MAX_VALUE`, so `int` multiplication produces **-1,794,967,296** in 32-bit width.
- `long total = ...` merely converts **-1,794,967,296** to `long`. The lost bits cannot be recovered after the multiplication.

At the bit level, `int` multiplication essentially keeps the lower 32 bits of the product, while `long` multiplication keeps the lower 64 bits. Both behaviors must be considered if the problem requires exact arithmetic.

## 2. Direct Comparison of Three Ways to Write It

```java
int a = 50_000;
int b = 50_000;

long wrong1 = a * b;           // -1794967296: multiplies in int then assigns to long
long wrong2 = (long) (a * b);  // -1794967296: casts after int multiplication
long right1 = (long) a * b;    // 2500000000: a becomes long before multiplying
long right2 = a * (long) b;    // 2500000000: b becomes long before multiplying
long right3 = 1L * a * b;      // 2500000000: 1L makes the first multiplication long
```

**Why is the second approach still wrong?** Writing `(long) (a * b)` forces Java to evaluate the entire parenthesized expression `a * b` as `int` first, and only afterward cast to `long`. A widening cast **preserves the already-overflowed `int` value**; it does not recompute the multiplication. With `(long) a * b`, the cast applies to `a` first, so `long * int` is computed in `long`.

You can visualize the sequence:

```text
Wrong: (long) (a * b)
        a:int × b:int  → overflowed int product → cast to long → wrong value as long

Right: (long) a * b
        a:int → cast to long → a:long × b:int → long product (if within long range)
```

An easy-to-remember practical rule: **if you want an integer multiplication result computed in `long`, ensure `long` already appears on an operand of the multiplication you need to protect**.

## 3. Left-Associative `*` Operator: Promote Early Enough

In a chain of multiplications, `*` is left-associative. A `long` operand appearing **too late** cannot save an `int` multiplication that already happened.

```java
int a = 50_000;
int b = 50_000;

long late = a * b * 1L;      // -1794967296
long early = a * 1L * b;     // 2500000000
long grouped = a * (b * 1L); // 2500000000
```

Because `a * b * 1L` is grouped as `(a * b) * 1L`, the product `a * b` overflows `int` **before** the `1L` operand comes into play. Conversely, in `a * 1L * b`, the first multiplication is already in `long`; the intermediate `long` result then participates in the next multiplication.

With three or more `int` operands:

```java
int x = 20_000, y = 20_000, z = 20;
long unsafe = x * y * z;        // The second multiplication can overflow int
long safer = (long) x * y * z; // Every multiplication in the chain runs in long
```

The word "safer" here only means **avoiding intermediate `int` overflow**. If the final product or an intermediate product exceeds `Long.MAX_VALUE`/`Long.MIN_VALUE`, `long` will also overflow. Check the actual data range.

This applies beyond multiplication: `long answer = (long) (x * y + z);` also **casts after the entire `int` expression**. If `x * y` already overflowed, converting to `long` cannot fix it. Move an operand to `long` before the step that risks overflowing, such as `long answer = (long) x * y + z;`.

## 4. Multiplication in Method Calls and Return Values

Promotion rules also apply in arguments and return values: a signature accepting or returning `long` does not automatically turn `int * int` into `long`. For instance, `static long wrongTotal(int a, int b) { return a * b; }` can still return an overflowed product, whereas `return (long) a * b;` computes the product in `long` before returning.

Therefore, check the cast position right at the **first multiplication expression** inside a call, operator chain, or `return` statement, instead of inferring from an outer variable or parameter type.

## 5. Ways to Write a `long` Multiplication Correctly

Choose one of the following depending on readability and intent:

| Expression | Multiplication Type | When to Use |
| --- | --- | --- |
| `(long) a * b` | `long` | Readable, clearly shows promoting `a` before multiplying |
| `a * (long) b` | `long` | Equivalent, promotes `b` first |
| `1L * a * b` | `long` from the start of the chain | Convenient with many `int` operands, though an explicit cast is often clearer |
| `a * b * 1L` | First `a * b` is `int` | **Unsafe** if `a * b` can overflow |
| `(long) (a * b)` | `int` then widened | **Cannot fix** an overflowed `int` product |
| `Math.multiplyFull(a, b)`, with two `int`s | Exact `long` result | No cast needed; Java 9+ |
| `Math.multiplyExact((long) a, b)` | `long`, detects overflow | Computes product in `long` with bounds checking |

When source data is already `long`, plain `long * long` multiplication is not enough to guarantee an exact result for large products. Use `Math.multiplyExact(long, long)` to detect overflow or `BigInteger` when exceeding 64 bits is required.

Do not casually switch to `double` just because `double` represents very large numbers. `double` has 53 bits of effective significand precision, so many large integers (and many products) get rounded. For counting, money in smallest integer units, or integer IDs, maintain exact integer precision.

## 6. Using `Math.multiplyExact`, `Math.multiplyFull`, and `BigInteger`

### `Math.multiplyExact`: detecting overflow

`Math.multiplyExact(int, int)` returns `int` if the product fits in `int`; otherwise, it throws `ArithmeticException`. `Math.multiplyExact(long, long)` returns `long` if the product fits in `long`; otherwise, it also throws `ArithmeticException`.

```java
int a = 50_000, b = 50_000;

// Math.multiplyExact(a, b) throws ArithmeticException because the product exceeds int.
long result = Math.multiplyExact((long) a, b); // 2500000000
```

Here, casting **before the call** causes the overload with a `long` parameter to be selected. If you write `long result = Math.multiplyExact(a, b);`, the `(int, int)` overload is still selected and will throw when the product exceeds `int`. The receiving variable's type does not change which overload is selected from the arguments.

Be careful with passed-in expressions:

```java
int a = 50_000, b = 50_000;
long c = 2;

// Defeats the goal: a * b already overflowed before the method is called.
long wrong = Math.multiplyExact(a * b, c);

// Correct evaluation timing: a is widened before multiplying.
// Math.multiplyExact also checks whether the long product exceeds the range.
long right = Math.multiplyExact(Math.multiplyExact((long) a, b), c);
```

`Math.multiplyExact` **cannot detect an operation that already overflowed before the value reached it**.

### `Math.multiplyFull`: getting the exact product of two `int`s

Because the product of **two signed `int` values** always fits within `long` (even `Integer.MIN_VALUE * Integer.MIN_VALUE`), Java provides `Math.multiplyFull(int, int)`, which returns **`long`** as the exact product.

```java
int a = 50_000, b = 50_000;
long exact = Math.multiplyFull(a, b); // 2500000000
```

This is a useful API when both operands are clearly `int` and you want a 64-bit result. With multiple `int` factors, check step by step or use the next bounds-checking strategy.

### `BigInteger`: when even `long` is not enough

For example, `3_100_000_000L * 3_100_000_000L` has mathematical product **9,610,000,000,000,000,000**, exceeding `Long.MAX_VALUE`. Casting `(long)` does nothing because both operands are already `long`.

```java
import java.math.BigInteger;

// Illustrative code inside a method:
long a = 3_100_000_000L;
long b = 3_100_000_000L;

BigInteger exact = BigInteger.valueOf(a).multiply(BigInteger.valueOf(b));
// 9610000000000000000
```

`BigInteger` computes integers of arbitrary magnitude within resource limits. Convert inputs using `BigInteger.valueOf(...)` **before multiplying**; do not write `BigInteger.valueOf(a * b)` if `a * b` could already overflow `long`.

## 7. Java 17+ Program Verifying Both Wrong and Right Multiplication

Create the file `MultiplyPromotionDemo.java`:

```java
public class MultiplyPromotionDemo {
    public static void main(String[] args) {
        int a = 50_000;
        int b = 50_000;

        System.out.println("int product: " + (a * b));
        System.out.println("cast after: " + ((long) (a * b)));
        System.out.println("cast before: " + ((long) a * b));
        System.out.println("long operand: " + (1L * a * b));
        System.out.println("cast late in chain: " + (a * b * 1L));
        System.out.println("cast early in chain: " + (a * 1L * b));

        try {
            Math.multiplyExact(a, b);
        } catch (ArithmeticException ex) {
            System.out.println("multiplyExact int: overflow");
        }

        System.out.println("multiplyExact long: " + Math.multiplyExact((long) a, b));
        System.out.println("multiplyFull: " + Math.multiplyFull(a, b));

        long large = 3_100_000_000L;
        System.out.println("long product overflow: " + (large * large));
        try {
            Math.multiplyExact(large, large);
        } catch (ArithmeticException ex) {
            System.out.println("multiplyExact long: overflow");
        }

        System.out.println("BigInteger product: "
            + java.math.BigInteger.valueOf(large)
                .multiply(java.math.BigInteger.valueOf(large)));
    }
}
```

Compile/run:

```bash
javac MultiplyPromotionDemo.java
java MultiplyPromotionDemo
```

Stdout output:

```text
int product: -1794967296
cast after: -1794967296
cast before: 2500000000
long operand: 2500000000
cast late in chain: -1794967296
cast early in chain: 2500000000
multiplyExact int: overflow
multiplyExact long: 2500000000
multiplyFull: 2500000000
long product overflow: -8836744073709551616
multiplyExact long: overflow
BigInteger product: 9610000000000000000
```

The program proves three things:

1. **Casting after multiplication only widens an already-overflowed value:** the first two lines and `cast late in chain` all print `-1794967296`.
2. **Promoting before multiplication resolves intermediate `int` overflow when the product fits in `long`:** `cast before`, `long operand`, and `cast early in chain` all print `2500000000`.
3. **Widening to `long` still has limits:** `large * large` overflows `long`; `Math.multiplyExact` detects it, and `BigInteger` preserves the exact mathematical result.

## 8. Checking Boundaries Before Choosing `int`, `long`, or `BigInteger`

A practical way to design multiplication:

1. **Determine the input domain**: what are the minimum/maximum possible values, and can they be negative?
2. **Determine the mathematical product range**, not just each operand's range. Two numbers that both fit in `int` can still yield a product larger than `int`.
3. **Choose a sufficiently wide computation type from the start**: `int * int` needs at most `long` to hold the exact product; `long * long` may need `BigInteger`.
4. **If the result type must remain bounded**, use `Math.multiplyExact` and handle `ArithmeticException` according to business rules.
5. **Inspect intermediate expressions** in multi-factor products, interleaved additions/multiplications, method calls, and cast expressions.

For example, with `quantity * unitPriceInCents`, storing both quantity and unit price as `int` does not guarantee the **total amount** fits in `int`. If the result should be `long`:

```java
int quantity = 50_000;
int unitPriceInCents = 50_000;

long totalCents = (long) quantity * unitPriceInCents; // 2500000000
```

If results larger than `long` can occur due to unbounded inputs, design explicit bounds or compute with `BigInteger`. If using `long` and wanting checks instead of silent overflow, `Math.multiplyExact((long) quantity, unitPriceInCents)` is an appropriate choice.

**Note on speed and width:** It is not necessary to turn every small multiplication into `long`; choose the type based on value ranges and data requirements. What to avoid is picking a sufficiently wide target variable while letting an **intermediate expression** compute in a narrower range.

## 9. Common Misconceptions

1. **"`long result = intA * intB` is guaranteed to be right."** False: `intA * intB` is evaluated in `int` before converting to `long`.
2. **"`(long) (intA * intB)` recovers the product."** False: the cast applies **after** the multiplication inside the parentheses.
3. **"Just put `1L` at the end of the multiplication chain."** False: `a * b * 1L` already computed `a * b` in `int`.
4. **"If both operands fit in `int`, the product also fits in `int`."** False: `50_000 * 50_000` exceeds `Integer.MAX_VALUE`.
5. **"`int` overflow always throws an exception."** False: primitive `*` wraps around; only checked APIs such as `Math.multiplyExact` report an error.
6. **"Converting an operand to `double` is always better than `long`."** False for exact integer arithmetic: `double` can round large integers.
7. **"`Math.multiplyExact(intA, intB)` can return `long` because the target variable is `long`."** False: the `(int, int)` overload is chosen from the **argument types**.
8. **"`Math.multiplyExact(intA * intB, longC)` checks the first multiplication too."** False: the argument `intA * intB` can overflow before the method is called.
9. **"`long * long` never overflows."** False: `long` only has 64 bits; the product of two `long`s may need more width.
10. **"`BigInteger.valueOf(longA * longB)` avoids data loss."** False: `long` multiplication runs before creating the `BigInteger`.

## 10. Self-Check

- **Does `int a = 70_000, b = 70_000; long x = a * b;` produce the exact `4_900_000_000`?** No, because `int * int` overflows. Fix it to `long x = (long) a * b;`.
- **Is `long x = (long) (a * b);` any better?** No: it still multiplies in `int` first.
- **How do `long x = a * b * 1L;` and `long y = 1L * a * b;` differ?** `x` executes its first multiplication in `int`; `y` executes its multiplications in `long`.
- **What type does `Math.multiplyFull(a, b)` return when `a` and `b` are `int`?** `long`, and the product of two `int`s always fits within `long`.
- **If both operands are already `long` and the product can exceed `long`, what should you do?** Use `Math.multiplyExact(long,long)` to detect overflow; use `BigInteger` to represent exact integer results beyond 64 bits.
- **Why can't an outer `(long)` cast save an already-overflowed number?** Because computing in `int` already discarded the out-of-range bits **before the cast**.

**Remember:** Java determines a multiplication's type from the **operand types**, and only then computes and assigns. For `int * int` that can exceed 32 bits, **promote an operand to `long` before the `*` operator**: `(long) a * b`. Casting afterward with `(long) (a * b)` only widens an `int` result that may already be wrong. When `long` is not enough, detect overflow or use `BigInteger`.
