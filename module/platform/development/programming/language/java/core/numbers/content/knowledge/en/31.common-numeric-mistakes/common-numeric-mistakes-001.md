# Assigning an Overflowed int Result to long Cannot Recover the Value in Java

## 1. The Core Mistake: A Wide Target Type Does Not Change the Source Operation Type

Consider a seemingly safe Java snippet:

~~~java
int a = 2_000_000_000;
int b = 1_500_000_000;

long result = a + b;
System.out.println(result); // -794967296, NOT 3500000000
~~~

Why does the variable `result` hold a negative number even though it is a 64-bit `long`?

**Because `a + b` is evaluated completely in 32-bit `int` first**, exceeding `Integer.MAX_VALUE = 2_147_483_647`. The `int` result overflows according to Java's integer rules. Only after the addition finishes is the **already-wrong** `int` value widened to `long`. Widening preserves the negative numeric value currently held rather than knowing the original mathematical result.

~~~text
int a = 2_000_000_000
int b = 1_500_000_000
       |
       v
a + b   (int addition, 32-bit)
       |
       v
-794_967_296   (int already overflowed)
       |
       v
convert int -> long
       |
       v
long result = -794_967_296
~~~

The true mathematical sum is `3_500_000_000`, which fits within `long` range but not within `int` range.

Correct fix:

~~~java
long result = (long) a + b; // 3500000000
~~~

The cast `(long) a` happens **before the addition**, so `+` selects `long` addition; `b` is also promoted to `long` to perform the operation.

**Rule:** If you want an operation to use a wide type, make **at least one appropriate operand have the wide type before the operation takes place**, or use an overflow-detecting API. Do not rely on the receiving variable's type on the left-hand side to rescue an already-overflowed result.

## 2. Why Does Java Compute in int Before Assigning to long?

Java determines the type of `+`, `-`, `*`, `/`, and `%` expressions via **binary numeric promotion** (numeric type promotion rules for two operands):

- If one operand is `double`, the operation is typically performed in `double`.
- If there is no `double` but one operand is `float`, the operation is typically performed in `float`.
- If neither of those is present and one operand is `long`, integer arithmetic is performed in `long`.
- If only integer types smaller than or equal to `int` remain (`byte`, `short`, `char`, `int`), they are promoted to `int`.

In the example, both `a` and `b` are `int`, so `a + b` is an **int expression**, regardless of whether the destination is `long`, `double`, `BigInteger` (via explicit conversion), or a method accepting `long`.

The conceptual order is:

1. Determine the operand types and the operation type.
2. Evaluate the expression, during which overflow or truncation may occur.
3. Convert the result type according to the assignment/method invocation context.
4. Assign or pass the computed value.

The widening assignment rule `int -> long` **does not alter step 1 or step 2**.

~~~java
int x = 2_000_000_000;
int y = 1_500_000_000;

long late = x + y;           // -794967296
long earlyLeft = (long) x + y; // 3500000000
long earlyRight = x + (long) y; // 3500000000
~~~

You can also use a literal with the `L` suffix:

~~~java
long correct = 2_000_000_000L + 1_500_000_000; // 3500000000
~~~

Conversely, changing only the left-hand type is not enough:

~~~java
long wrong = 2_000_000_000 + 1_500_000_000; // -794967296
~~~

**Note on constant expressions:** Java can evaluate constant expressions at compile time. That does not mean adding two `int`s is automatically promoted to `long`. Always check **the types of the operands**, including in constants and variable-free expressions.

## 3. Another Example: Multiplying Two ints Before Assigning to long

For example, calculating area or total cost:

~~~java
int quantity = 50_000;
int unitPrice = 50_000;

long wrong = quantity * unitPrice;       // -1794967296
long stillWrong = (long) (quantity * unitPrice); // -1794967296
long correct = (long) quantity * unitPrice;      // 2500000000
~~~

The mathematical product is `50_000 × 50_000 = 2_500_000_000`, which exceeds `int` range. When only `int` operands are present, `*` produces an overflowed `int` result.

The difference between these forms is crucial:

| Expression | Order of Evaluation | Result |
| --- | --- | ---: |
| `(long) (a * b)` | Computes `int * int` first, **then** casts | Can be a wrong, overflowed number |
| `(long) a * b` | Casts `a` first, then `long * long` | Preserves the product of any two ints within long range |
| `a * (long) b` | Casts `b` first, then `long * long` | Same |
| `1L * a * b` | Multiplies by `1L` first by associativity | Product is computed as long from the start |

In Java, **the mathematical product of any two `int` values fits within `long` range**, so converting at least one operand to `long` before multiplication is enough to avoid **integer overflow at that multiplication**. However, an expression with multiple multiplications or additions on `long` values can still overflow `long` if it exceeds the 64-bit range.

For example, `a * b * 1L` **can be wrong** because Java associates multiplication from left to right: `a * b` is computed as `int` first, and only then multiplied by `1L`. Write `1L * a * b` or `(long) a * b`.

## 4. Parentheses and Casts: Placement Decides Correctness

Compare:

~~~java
long a = (long) (x + y); // Too late if x+y already overflowed int
long b = (long) x + y;   // x is already long when addition is performed
~~~

The parentheses in the first expression force Java to evaluate `x + y` as an `int` expression before casting; casting outside the parentheses merely preserves the already-computed `int` value.

With multiple operations, you must examine **every intermediate operation**:

~~~java
int a = 1_500_000_000;
int b = 1_500_000_000;
int c = 1;

long wrong = (a + b) + (long) c; // a+b already overflowed int
long correct = (long) a + b + c; // every addition in this chain is long
~~~

Another case:

~~~java
int width = 50_000;
int height = 50_000;

long wrongArea = width * height;          // int overflow
long correctArea = 1L * width * height;   // long right from the first multiplication
~~~

Ask yourself at each **operator node** in the expression tree: what types do the two operands have at that moment? The answer can matter more than the declared type of the result.

## 5. Complete Java 17 Program and Exact Output

Create the file `OverflowBeforeWideningDemo.java`:

~~~java
import java.util.Arrays;

public class OverflowBeforeWideningDemo {
    public static void main(String[] args) {
        int a = 2_000_000_000;
        int b = 1_500_000_000;

        long sumTooLate = a + b;
        long sumCorrect = (long) a + b;
        System.out.println("sum too late = " + sumTooLate);
        System.out.println("sum widened = " + sumCorrect);

        int x = 50_000;
        int y = 50_000;
        long productTooLate = (long) (x * y);
        long productCorrect = (long) x * y;
        System.out.println("product too late = " + productTooLate);
        System.out.println("product widened = " + productCorrect);

        try {
            Math.addExact(a, b);
            System.out.println("Unexpected add success");
        } catch (ArithmeticException ex) {
            System.out.println("addExact = overflow detected");
        }

        try {
            Math.multiplyExact(x, y);
            System.out.println("Unexpected multiply success");
        } catch (ArithmeticException ex) {
            System.out.println("multiplyExact = overflow detected");
        }

        int[] numbers = {1_500_000_000, 1_500_000_000, 1};
        int wrongSum = Arrays.stream(numbers).sum();
        long correctSum = Arrays.stream(numbers).asLongStream().sum();
        System.out.println("int stream sum = " + wrongSum);
        System.out.println("long stream sum = " + correctSum);

        int min = Integer.MIN_VALUE;
        long wrongAbs = Math.abs(min);
        long correctAbs = Math.abs((long) min);
        System.out.println("abs too late = " + wrongAbs);
        System.out.println("abs widened = " + correctAbs);

        long daysWrong = 30 * 24 * 60 * 60 * 1000;
        long daysCorrect = 30L * 24 * 60 * 60 * 1000;
        System.out.println("30 days millis wrong = " + daysWrong);
        System.out.println("30 days millis correct = " + daysCorrect);
    }
}
~~~

Run with JDK 17 or later:

~~~bash
javac OverflowBeforeWideningDemo.java
java OverflowBeforeWideningDemo
~~~

Output:

~~~text
sum too late = -794967296
sum widened = 3500000000
product too late = -1794967296
product widened = 2500000000
addExact = overflow detected
multiplyExact = overflow detected
int stream sum = -1294967295
long stream sum = 3000000001
abs too late = -2147483648
abs widened = 2147483648
30 days millis wrong = -1702967296
30 days millis correct = 2592000000
~~~

**Explanation of output:**

1. Adding `2_000_000_000 + 1_500_000_000` exceeds `Integer.MAX_VALUE`, so the `int` result is `-794_967_296`. Casting before addition preserves `3_500_000_000`.
2. Multiplying `50_000 × 50_000` yields `2_500_000_000`, which also exceeds `int`; the `long` type must participate **before** multiplication.
3. `Math.addExact(int, int)` and `Math.multiplyExact(int, int)` detect overflow by throwing `ArithmeticException`, instead of silently wrapping around.
4. `IntStream.sum()` returns `int`, so the sum can overflow; converting elements to `long` via `asLongStream()` **before accumulating** avoids `int` overflow at the sum step.
5. `Math.abs(Integer.MIN_VALUE)` returns `Integer.MIN_VALUE` itself because `2147483648` does not fit in the positive `int` range. Casting the input to `long` **before** `Math.abs` gives `2147483648`.
6. The product `30 × 24 × 60 × 60 × 1000` (milliseconds in 30 days, ignoring DST and illustrating fixed-length arithmetic only) yields `2_592_000_000`, which exceeds `int`. Using `30L` at the start computes the result in `long`.

The output lines above are deterministic and do not depend on threads, wall-clock time, or external inputs.

## 6. Why Does long Only Preserve the Overflowed Result?

For Java's integer addition, subtraction, and multiplication operators, overflow **does not throw an exception on its own**. In terms of value, `int` operations use 32 bits; when a result exceeds the range, it wraps around modulo the low bits and is reinterpreted as a signed `int`.

Example addition:

~~~text
Mathematical sum:      3,500,000,000
2^32:                  4,294,967,296
Signed int result:      -794,967,296
Widened to long:        -794,967,296
~~~

When converting from a negative `int` to `long`, Java performs *sign extension* to **preserve the negative numeric value**, without attempting to recover bits discarded in an earlier operation. In other words, the `int -> long` conversion itself is exact—the problem lies in the **int calculation before the conversion**.

A subtle point: Many different mathematical sums can produce the exact same `int` value after overflow. For example, `-794_967_296` could be a valid non-overflowed value or the remainder after adding to `3_500_000_000`. Given only a stored `int` result, it is impossible to determine the original exact sum without the operands or additional information.

If the source data is still available, you can **recompute** using `long`. That is recomputing from the source, **not** recovering an overflowed calculation merely by casting the wrong result.

## 7. Prevention: Promote Before Computing or Detect Overflow

There are three common strategies.

### Strategy A — Compute in long When the Result Range Fits

~~~java
int price = 50_000;
int quantity = 50_000;

long total = (long) price * quantity;
~~~

Use this when the true result may exceed `int` but still fits in `long`. When summing multiple `int`s, make the accumulator variable `long` from the start:

~~~java
int[] values = {1_500_000_000, 1_500_000_000, 1};

long total = 0L;
for (int v : values) {
    total += v; // long + int -> long
}
~~~

Do not sum everything in `int` and then convert the total to `long`:

~~~java
int partial = 0;
for (int v : values) {
    partial += v; // May overflow int inside the loop!
}
long wrong = partial;
~~~

### Strategy B — Catch Overflow When the Return Type Must Be int

If the API contract requires an `int` value and out-of-range values must be rejected:

~~~java
int safeSum = Math.addExact(a, b);
int safeProduct = Math.multiplyExact(a, b);
~~~

`Math.addExact`, `subtractExact`, `multiplyExact`, `incrementExact`, `decrementExact`, and `negateExact` provide overloads for the appropriate integer types and throw `ArithmeticException` when the result cannot be represented.

For example:

~~~java
int count = Integer.MAX_VALUE;
int next = Math.incrementExact(count);
// ArithmeticException, instead of wrapping around to Integer.MIN_VALUE.
~~~

If you compute in `long` and then need to convert back to `int`, use:

~~~java
long wide = (long) a + b;
int checked = Math.toIntExact(wide);
~~~

`Math.toIntExact` takes an accurately computed `long` value and allows the conversion only if it fits in `int`. However, `Math.toIntExact(a + b)` is **in the wrong order** if `a + b` has already overflowed `int`: the `long` overload only sees the already-wrong `int` result converted to `long`, so the check may miss the problem.

### Strategy C — Use BigInteger When long Is Also Insufficient

`long` has a finite range: `-9_223_372_036_854_775_808` to `9_223_372_036_854_775_807`. `long` addition and multiplication can still overflow.

When the problem requires integers larger than `long` range:

~~~java
import java.math.BigInteger;

BigInteger left = BigInteger.valueOf(Long.MAX_VALUE);
BigInteger answer = left.add(BigInteger.ONE);
System.out.println(answer); // 9223372036854775808
~~~

This is a **code snippet** and must be placed inside a class/method to run. `BigInteger` provides arbitrary-precision integers, bounded in practice only by memory and system resources.

If the operands are already `long`, convert **before the operation**, not after `long` has overflowed:

~~~java
BigInteger aBig = BigInteger.valueOf(longA);
BigInteger bBig = BigInteger.valueOf(longB);
BigInteger correct = aBig.multiply(bBig);
~~~

`BigInteger.valueOf(longA * longB)` can still receive an **already-overflowed** `long` result, so it does not protect the multiplication.

## 8. Traps of the Same Nature: Math.abs, Division, and Negation

### 8.1. Math.abs(Integer.MIN_VALUE)

`Integer.MIN_VALUE` is `-2147483648`. The mathematical absolute value `2147483648` exceeds `Integer.MAX_VALUE`:

~~~java
int min = Integer.MIN_VALUE;

long wrong = Math.abs(min);         // -2147483648
long correct = Math.abs((long) min); // 2147483648
~~~

`Math.abs(int)` returns `int`, so it cannot produce the positive number 2147483648. Casting the input first makes Java select `Math.abs(long)` before taking the absolute value.

This is also an example of why **overload selection** based on operand type matters: a `long` receiving variable does not turn `Math.abs(int)` into `Math.abs(long)`.

### 8.2. Negating the Smallest int

~~~java
int min = Integer.MIN_VALUE;

long wrong = -min;        // -2147483648: int negation overflowed
long correct = -(long) min; // 2147483648
~~~

The unary `-` operator on an `int` variable also produces an `int` result. Converting after negation cannot fix the result. `Math.negateExact(min)` reports overflow and is suitable when the target type must remain `int`.

### 8.3. Dividing Integer.MIN_VALUE by -1

This is a special case of `int` integer division:

~~~java
int min = Integer.MIN_VALUE;

long wrong = min / -1;          // -2147483648
long correct = (long) min / -1; // 2147483648
~~~

`-2147483648 / -1` has mathematical quotient `2147483648`, which exceeds `int` range. Java specifies that this case yields `Integer.MIN_VALUE` if the division is performed in `int`. Meanwhile, a `long` operand switches the division to `long` and gives the correct quotient.

Ordinary division also carries the risk of **truncating the fractional part before assignment**:

~~~java
int numerator = 5;
int denominator = 2;

double wrong = numerator / denominator;          // 2.0
double correctApprox = (double) numerator / denominator; // 2.5
~~~

This is not overflow; the cause is still that **the operation in the source type completes before the result is assigned**. If rule-governed decimal precision is required, use `BigDecimal.divide` with an appropriate scale and `RoundingMode`.

## 9. Method Call Contexts Do Not Automatically Rescue Expressions Either

The bug does not occur only in assignments:

~~~java
static void report(long value) {
    System.out.println(value);
}
~~~

Given `int a` and `int b`:

~~~java
report(a + b);         // a+b is int, may overflow, then passed to long
report((long) a + b);  // add as long before passing
~~~

These are **code snippets** that need to be placed in a class containing the `report` method and corresponding variables.

Similarly, an API accepting `long` does not automatically promote a subexpression that is already `int`:

~~~java
long millis = 30 * 24 * 60 * 60 * 1000;   // int overflow
long fixedMillis = 30L * 24 * 60 * 60 * 1000; // long
~~~

One way to avoid manual multiplication when converting time units is to choose the appropriate time API (such as `Duration.ofDays(30).toMillis()`) and understand calendar/duration semantics clearly. `Duration` measures elapsed time in fixed units; it is not equivalent to adding 30 **calendar days in a specific time zone** when Daylight Saving Time (DST) transitions occur.

## 10. Accumulation: Check the Types of Both the Sum Variable and Each Addition

A common mistake in statistics and streams:

~~~java
int[] numbers = {1_500_000_000, 1_500_000_000, 1};

int sum = java.util.Arrays.stream(numbers).sum();
// -1294967295 because IntStream.sum() returns int.

long wrong = java.util.Arrays.stream(numbers).sum();
// Still -1294967295: widened after IntStream.sum() completed.

long correct = java.util.Arrays.stream(numbers)
        .asLongStream()
        .sum();
// 3000000001: each element is fed into long addition.
~~~

`mapToLong(value -> value).sum()` is another option to promote each element before summing.

In a loop, you must use a `long` accumulator variable **from the beginning**:

~~~java
long total = 0L;
for (int number : numbers) {
    total += number; // long + int => long
}
~~~

However, `long total` does not guarantee unconditional safety: the sum of a sufficiently long list or very large values can still exceed `long` range. If that case can realistically occur and data loss is unacceptable, use `Math.addExact(long, long)` for each addition or accumulate with `BigInteger`.

## 11. Distinguishing Integer Overflow from float/double Precision Errors

Some people try to fix this by switching to `double`:

~~~java
int a = 2_000_000_000;
int b = 1_500_000_000;

double wrong = a + b;            // -794967296.0
double betterHere = (double) a + b; // 3500000000.0
~~~

Converting one operand to `double` before addition avoids `int` overflow in this case; however, **double does not accurately preserve all large integer values**. `double` only has 53 bits of binary significand, so it should not be used as a general solution for exact integer arithmetic across the `long` range.

For example:

~~~java
long n = 9_007_199_254_740_993L; // 2^53 + 1
double d = (double) n;            // Does not represent n accurately.
~~~

If you need exact integer results for operations on `int`s and the result fits in `long`, the natural choice is **`long`**, not `double`. If `long` is not enough, convert to `BigInteger` before computing.

Also, do not use `(long) (doubleExpression)` to try to "recover" digits already lost in `double`: casting back does not recreate the original information.

## 12. Overflow Detection Conditions vs. Result Type Limits

There are two distinct goals:

### A. Wanting a Wide and Accurate Result

~~~java
int a = Integer.MAX_VALUE;
int b = 1;

long total = (long) a + b; // 2147483648
~~~

### B. Wanting to Keep an int Result and Reject Unrepresentable Values

~~~java
int a = Integer.MAX_VALUE;
int b = 1;

// int total = Math.addExact(a, b); // ArithmeticException
~~~

When the application requires reporting an error instead of automatically switching to `long`, `Math.addExact` is more appropriate.

You can check manually by computing in `long` and then comparing bounds:

~~~java
static int checkedAdd(int a, int b) {
    long exact = (long) a + b;
    if (exact < Integer.MIN_VALUE || exact > Integer.MAX_VALUE) {
        throw new ArithmeticException("int overflow");
    }
    return (int) exact;
}
~~~

For the **sum of two ints**, `long` always holds the mathematical result, so boundary checking in `long` is exact. `Math.addExact(a, b)` is more concise and standardized.

`Math.toIntExact(wide)` is also valid when the variable `wide` truly holds an accurate value from a wide calculation or external input:

~~~java
long wide = (long) a + b;
int value = Math.toIntExact(wide); // Throws ArithmeticException if outside int.
~~~

The key point is that `wide` must be created **before overflow**, not `long wide = a + b`.

## 13. Common Mistakes to Spot Immediately in Code Reviews

| Bug-Prone Code | Reason | Replacement / Condition |
| --- | --- | --- |
| `long s = a + b;` with two ints | `int` sum can overflow before assignment | `long s = (long) a + b;` |
| `long p = a * b;` | `int` product can overflow | `long p = (long) a * b;` |
| `long p = (long)(a * b);` | Cast is too late | `long p = (long)a * b;` |
| `long p = a * b * 1L;` | `a*b` is evaluated first | `long p = 1L*a*b;` |
| `Math.toIntExact(a + b)` | `a+b` already overflowed in `int`, so check misses it | `Math.addExact(a,b)` or `Math.toIntExact((long)a+b)` |
| `long x = Math.abs(intValue);` | `Math.abs(int)` can overflow at MIN_VALUE | `long x = Math.abs((long)intValue);` |
| `long x = -intValue;` | Unary negation still runs in `int` | `long x = -(long)intValue;` |
| `long m = 30*24*60*60*1000;` | All `int` literals; multiplication overflows | `long m = 30L*24*60*60*1000;` |
| `long sum = intStream.sum();` | `IntStream.sum()` returns `int` | `long sum = intStream.asLongStream().sum();` |

In code reviews, do not just ask "is the final variable a `long`?". Trace backward through every expression, method, overload, and intermediate operation, and determine **the type at the moment the operation actually executes**.

## 14. Overflow May Not Produce an Obviously Negative Number

Not every overflow shows up as a suspicious negative number that alerts the programmer. The wrapped result can be a **plausible-looking positive number**, **zero**, or any value in the `int` range.

For example:

~~~java
int value = Integer.MAX_VALUE;
int doubled = value * 2; // -2
~~~

But when adding more values sequentially, the result can wrap all the way around the range and become positive again. Seeing "a positive result", "no exception thrown", or "assignable to `long`" does not guarantee the calculation is correct.

Do not use the sign of the result or arbitrary thresholds as a general overflow detector. For instance, `result < 0` is not a sufficient indicator because operands can legitimately be negative, and overflow can yield a positive number. Use `Math.*Exact` or compute beforehand in a sufficiently wide type and check bounds.

## 15. Exercises with Solutions

### Exercise 1: Fix an Area Multiplication

~~~java
int width = 70_000;
int height = 70_000;
long area = width * height;
~~~

**Answer:** `long area = (long) width * height;`, giving the exact result `4_900_000_000`. The original version performs `int` multiplication first and can produce a wrong number.

### Exercise 2: Predict the Values

~~~java
int a = 2_000_000_000;
int b = 1_500_000_000;

long first = a + b;
long second = (long) a + b;
long third = (long) (a + b);
~~~

**Answer:** `first = -794967296`, `second = 3500000000`, `third = -794967296`. Only `second` converts an operand before computing.

### Exercise 3: Why Can Math.toIntExact Still Miss the Error?

~~~java
int a = 2_000_000_000;
int b = 1_500_000_000;
int result = Math.toIntExact(a + b);
~~~

**Answer:** `a+b` has already overflowed `int` to `-794967296`. When the argument is widened to `long` to pass to `toIntExact`, it still lies within `int` range; `toIntExact` returns that very negative value and **throws no error**. Fix with `Math.addExact(a,b)` (which throws an exception) or `Math.toIntExact((long)a+b)`.

### Exercise 4: Stream Sum

Given `int[] values = {1_500_000_000, 1_500_000_000, 1}`, why is `long sum = Arrays.stream(values).sum();` incorrect?

**Answer:** `IntStream.sum()` completes the summation in `int` before converting the result to `long`. Use `Arrays.stream(values).asLongStream().sum()` to sum in `long` from the start, yielding `3000000001`.

### Exercise 5: Absolute Value

Why is `long magnitude = Math.abs(Integer.MIN_VALUE);` negative?

**Answer:** The `Math.abs(int)` overload returns `int` and cannot represent the mathematical absolute value of `Integer.MIN_VALUE`. Fix with `Math.abs((long) Integer.MIN_VALUE)` to get `2147483648`.

### Exercise 6: Choosing an Error Policy

An API must return `int` and requires that the sum `a+b` lose no data. Should you use `long` and cast back without checking, or call `Math.addExact`?

**Answer:** Call `Math.addExact(a,b)` to reject cases exceeding `int`. If business requirements allow larger sums and the return type can be `long`, use `(long)a+b`. Choose based on **the target data contract**, not casting habits.

## 16. Checklist Before Assigning an Integer Calculation Result

1. **What are the types of the two operands at each addition/multiplication/subtraction/division?** Is there an `int` in an intermediate step?
2. **Does the wide type appear before the risky operation?** `(long)(a*b)` is no substitute for `(long)a*b`.
3. **Do parentheses and associativity create an overflowed `int` subexpression before encountering `long`?**
4. **Is there a method overload returning `int`?** Especially `Math.abs(int)`, `IntStream.sum()`, `Math.max(int,int)`.
5. **Are `int` literals being multiplied/added before assigning to `long`?** Place `L` appropriately or use a dedicated API.
6. **Does the contract want a wide result or overflow detection?** Choose `long`, `Math.*Exact`, or `BigInteger` accordingly.
7. **If the calculation has already happened, do you still have the original operands to recompute accurately?** Casting a wrong result cannot recover lost data.
8. **Have you tested boundary cases?** `Integer.MAX_VALUE + 1`, `Integer.MIN_VALUE`, large multiplications, long accumulations, `MIN_VALUE / -1`.

**Conclusion:** In Java, **the receiving variable's type does not determine the type of the preceding operation**. `long result = a + b` still computes in `int` if `a` and `b` are `int`, and once that expression overflows, converting to `long` only stores **the overflowed value**. To get it right, **promote at least one operand before the operation**, use `Math.*Exact` to detect errors when `int` is required, or use `BigInteger` if `long` is also insufficient.
