# Parentheses and Their Impact on Intermediate Values in Java Integer Arithmetic

## 1. Objectives and Problem Statement

With the exact same operands, a program can return very different results when parentheses are moved. In Java integer arithmetic, this happens because **parentheses determine how operations are grouped**, and **each intermediate operation has its own data type, integer division rules, and representation limits**. An intermediate result that has already been truncated or overflowed will not be "recovered" simply because the final result is assigned to a wider variable.

After this lesson, you will be able to:

- Read how Java groups expressions using **operator precedence**, **associativity**, and parentheses `( ... )`.
- Distinguish between the order of **grouping operations** and the left-to-right order of **evaluating operands**.
- Accurately predict the results of `+`, `-`, `*`, `/`, and `%` when parentheses change.
- Identify where **integer division truncates the fractional part**, where **`int`/`long` can overflow**, and where **numeric promotion** or a **cast** changes the intermediate computation type.
- Choose parenthesization, type conversions, and overflow checks appropriate to the computation requirements; run Java 17+ examples and explain stdout.

**Scope:** Java Core integer arithmetic with `byte`, `short`, `int`, and `long`; floating-point numbers appear where needed to contrast casting effects. Examples use Java SE 17 or later and require no libraries outside the JDK.

## 2. Three Rules That Must Be Separated

### 2.1. Precedence — Which Operator Binds Tighter?

For common arithmetic operators, precedence from highest to lowest is:

| Level | Syntax | Primary meaning |
| --- | --- | --- |
| 1 | `( ... )` | Explicitly specifies a subexpression; evaluates the inner expression according to its grouped structure |
| 2 | `+x`, `-x`, `++x`, `x++` | Unary / increment-decrement operators; prefix and postfix have distinct precedence details |
| 3 | `*`, `/`, `%` | Multiplication, division, remainder |
| 4 | `+`, `-` | Addition, subtraction |

This simplified table serves **arithmetic** only; Java expressions also include shifts, comparisons, logical, conditional, assignment, and other constructs with their own precedence levels. Unary operators do not imply that all prefix/postfix forms share the exact same level in the full table.

For example:

```java
int result = 10 + 2 * 3;      // 16: 10 + (2 * 3)
int changed = (10 + 2) * 3;   // 36: (10 + 2) * 3
```

Parentheses are not a "new operator" that transforms data. They specify computing a **subexpression** under a different grouping, which can thereby change the value or type of intermediate results.

### 2.2. Associativity — How to Group at the Same Precedence Level?

Binary arithmetic operators `+`, `-`, `*`, `/`, and `%` group **from left to right** when no parentheses override them.

```java
int x = 20 / 3 / 2;      // (20 / 3) / 2 = 6 / 2 = 3
int y = 20 / (3 / 2);    // 20 / 1 = 20
```

Both expressions have the same operands in the same order, yet **different division structures**. Division is not algebraically associative, so parentheses are especially critical.

Another example:

```java
int a = 15 - 6 - 2;      // (15 - 6) - 2 = 7
int b = 15 - (6 - 2);    // 15 - 4 = 11
```

Do not interpret "left-associative" to mean Java may arbitrarily reorder operations in all cases. It is a rule for **parsing expression structure**.

### 2.3. Evaluation Order — Which Operand Executes First?

Java guarantees that the operands of a binary operator are **evaluated from left to right**, even when the right-hand operator has higher precedence. For example, `left() + middle() * right()` is grouped as `left() + (middle() * right())`; at runtime, `left()` is still called before `middle()` and `right()`.

Distinguish clearly:

- **Grouping/precedence:** which subexpression feeds its result into which operation.
- **Evaluation order:** which action, method call, or side effect happens first.
- **Integer intermediate:** the result at each arithmetic step carries the type and rules of that specific operation.

Thus, saying "Java always executes multiplication before addition" is imprecise when operands contain method calls or side effects. Java **groups** multiplication tighter; operand evaluation must still respect left-to-right order.

## 3. Parentheses Change Results of Addition, Subtraction, Multiplication, and Division

| Expression | Step-by-step evaluation | `int` result |
| --- | --- | ---: |
| `18 / 3 + 3` | `(18 / 3) + 3 = 6 + 3` | 9 |
| `18 / (3 + 3)` | `18 / 6` | 3 |
| `20 / 3 / 2` | `(20 / 3) / 2 = 6 / 2` | 3 |
| `20 / (3 / 2)` | `20 / 1` | 20 |
| `10 + 2 * 3` | `10 + (2 * 3)` | 16 |
| `(10 + 2) * 3` | `12 * 3` | 36 |
| `15 - 6 - 2` | `(15 - 6) - 2` | 7 |
| `15 - (6 - 2)` | `15 - 4` | 11 |

Parentheses are useful when you want an expression to reflect a business formula, such as:

- Number of groups to process from `items` and `groupSize`.
- Total weighted sum divided by total sample count.
- Order of applying deductions or quantity adjustments.

However, writing a formula that looks like math is **not enough** to guarantee the result: operation types and overflow risk must be analyzed independently.

## 4. Most Important: Integer Division Truncates the Remainder at the Intermediate Step

In Java, if **both operands of `/` are integer types**, integer division produces an integer result and **discards the fractional part toward zero**. Placing parentheses can cause division to happen earlier or later.

```java
int items = 7;
int groups = 2;
int quotient = items / groups;       // 3
int beforeMultiply = (items / groups) * groups; // 6
int afterMultiply = (items * groups) / groups;  // 7
```

Because `7 / 2` already became `3`, `(7 / 2) * 2` becomes `6`, and cannot automatically recover the remainder `1`. The expression `(7 * 2) / 2` yields `7` in this small example because multiplication occurs before division and does not overflow. Do **not** conclude that "multiply before divide" is always safe: the intermediate product can exceed the `int` range.

### 4.1. Dividing Negative Numbers and the Remainder Operator

`-7 / 2` equals `-3`, **not `-4`**; `-7 % 2` equals `-1`. In Java, the remainder takes the sign of the dividend for integer `%`, and when the operation is valid, `a == (a / b) * b + (a % b)` holds under integer semantics.

For example:

```java
int a = -7;
int b = 2;
System.out.println(a / b);   // -3
System.out.println(a % b);   // -1
```

Avoid unconsciously applying the mathematical floor function to `int / int`. If the problem wants floor division for negative numbers, look at `Math.floorDiv` and `Math.floorMod`; verify sign conventions and boundary values. They are **not** simply a matter of adding parentheses around integer division.

### 4.2. Avoiding Unintended Intermediate Calculations

```java
int a = 20;
int b = 3;
int c = 2;

int leftGrouped = (a / b) / c; // 3
int rightGrouped = a / (b / c); // 20
```

In `a / (b / c)`, `b / c` is computed first: `3 / 2 = 1`. If `b / c` equals `0`, the outer division throws `ArithmeticException`, even though left-to-right division might be completely valid.

If the denominator depends on data, validate it **after computing the subexpression properly**, rather than checking only that the initial variables are non-zero.

## 5. Parentheses Do Not Automatically Promote `int` to `long`

This is the most common mistake when performing addition or multiplication on large integer data.

Suppose:

```java
int a = 2_000_000_000;
int b = 1_000_000_000;

long wrong = (long) (a + b);
long correct = (long) a + b;
```

Explanation:

1. In `(a + b)`, both operands are `int`, so the addition occurs **in `int`**. The mathematical sum `3_000_000_000` exceeds `Integer.MAX_VALUE`; the `int` result overflows to `-1_294_967_296`.
2. Casting `(long) (a + b)` only widens the **already-overflowed value**; `wrong` is still `-1_294_967_296L`.
3. In `(long) a + b`, operand `a` is converted to `long` **before adding**. Binary numeric promotion converts `b` to `long`, and the addition returns `3_000_000_000L`.

**Rule:** for an intermediate operation to use a wider type, cast **before the operation that can overflow**. Putting parentheses around the entire operation and casting afterward is too late.

Equivalent example for multiplication:

```java
int quantity = 50_000;
int unit = 50_000;
long wrong = quantity * unit;          // int multiplication overflows
long correct = (long) quantity * unit; // long multiplication
```

`wrong` gets `-1_794_967_296` because `int * int` overflows before widening to `long`; `correct` is `2_500_000_000L`.

However, `long` also has limits: when operands can exceed 64 bits, consider `BigInteger` or overflow checks. No magic cast makes primitive operations infinitely wide.

## 6. Trap: Multiplication Overflows Even When the Final Quotient Would Fit in `int`

The mathematical formula `n(n + 1) / 2` computes the sum from `1` to `n`. With `n = 50_000`:

- The mathematical sum equals `1_250_025_000`, which **fits in `int`**.
- The intermediate product `50_000 × 50_001 = 2_500_050_000` **exceeds `int`**.
- Computing `n * (n + 1) / 2` entirely in `int` overflows before dividing, yielding an incorrect result.

```java
int n = 50_000;
int wrong = n * (n + 1) / 2;
long correct = (long) n * (n + 1) / 2;
```

Output:

```text
wrong   = -897458648
correct = 1250025000
```

The parentheses `(n + 1)` express the formula clearly but **do not** protect the subsequent multiplication. Placing the cast `(long) n` before the multiplication protects the intermediate step. When the problem requires the final result to remain `int` and report an error if out of range, you can validate with `Math.toIntExact(correct)` after computing in `long`.

This is why when reviewing expressions, you must analyze the **range of every node in the operation tree**, rather than only checking the target variable or expected final value.

## 7. Numeric Promotion and the Scope of a Cast

Java applies **binary numeric promotion** to common binary arithmetic operators:

- `byte`, `short`, and `char` are promoted to at least `int` when participating in binary arithmetic operations.
- If a `long` operand is present and no floating-point type is involved, the operation takes type `long`; otherwise, if all operands are `int` or narrower, it takes `int`.
- When a `float`/`double` operand is present, the operation switches to floating-point per the corresponding promotion rules; that is a comparison topic, not a default fix for integer overflow bugs.

### 7.1. Same Parentheses, Different Operation Type

```java
byte left = 100;
byte right = 20;
// byte sum = left + right; // compile error: byte + byte => int
int sum = left + right;
```

Even though `120` fits in `byte`, **the type of expression `left + right` is `int`**. If narrowing is genuinely needed, `byte sum = (byte) (left + right);` compiles, but **can lose data** for other inputs; do not treat a cast as a safety check.

### 7.2. Outer Cast vs. Inner Cast Differ

With `a = 7`, `b = 2`:

| Expression | Intermediate operation | Result |
| --- | --- | --- |
| `(double) (a / b)` | `a / b` is `int` `3`, then converted to `double` | `3.0` |
| `(double) a / b` | Converts `a` to `double` first, then divides | `3.5` |
| `a / (double) b` | Converts `b` to `double` first, then divides | `3.5` |
| `(long) (a * b)` | Multiplies in `int` first, then widens | Result may have already overflowed |
| `(long) a * b` | Multiplies in `long` | Avoids `int` overflow, still subject to `long` limits |

Do not convert an integer arithmetic expression to `double` just to "dodge" overflow when business rules require **exact integer precision**. `double` cannot represent all `long` integers exactly (the contiguous exact integer range only reaches 2⁵³). For large integer calculations, use `long`/`BigInteger` as required.

## 8. Distinguishing Algebraic Associativity from Associativity in Java

This is an area often taught inaccurately. Pure **`int` or `long` integer addition and multiplication** in Java, when of the same type and free of side effects, remain associative modulo 2³²/2⁶⁴ even when operations overflow:

```java
int x = Integer.MAX_VALUE;
int y = 1;
int z = -1;

int first = (x + y) + z;
int second = x + (y + z);
// first == second == Integer.MAX_VALUE
```

In the first grouping, `x + y` overflows to `Integer.MIN_VALUE` first and then adds `-1`; in the second grouping, `y + z` becomes `0`. The **intermediate values differ**, yet the final `int` result is identical. Do not claim that merely changing parentheses in pure `int` addition always changes the final result.

The associativity above **does not allow** arbitrary regrouping when:

- The expression contains **division/remainder**, because they do not share this associativity.
- There are **different intermediate types**, casts, conversion calls, or methods with specific contracts.
- There are **side effects** such as `++`, assignments, I/O, or observable method calls.
- **Overflow-checked** APIs (such as `Math.addExact`) are used instead of plain `+`: where an intermediate failure is detected can differ.
- Switching to **floating-point**: floating-point addition and multiplication are not generally associative due to rounding, overflow, and NaN.

### 8.1. Example with Overflow-Checked Addition

`Math.addExact(a,b)` throws `ArithmeticException` if the addition exceeds the return type's range:

```java
int x = Integer.MAX_VALUE;
int y = 1;
int z = -1;

// Math.addExact(Math.addExact(x, y), z); // throws: inner add overflows
int safeGrouping = Math.addExact(x, Math.addExact(y, z)); // MAX_VALUE
```

Both arithmetic expressions have the same mathematical sum; however, **the per-step overflow detection contract** differs. Do not use wrapping `+` addition to prove that checked addition is safe.

When you need to avoid intermediate overflow failures if only the final sum matters, define the business requirement explicitly: either sum in `long`/`BigInteger` and check the target range afterward, or require every step to be safe via `addExact`. Those are two different contracts.

## 9. Intermediate Arithmetic and Evaluation Order with Side Effects

Parentheses change grouping, but Java still evaluates operands according to language rules. The runnable example below shows `left()` executing before `right()` even though multiplication on the right has higher precedence than addition.

Save as **`EvaluationOrder.java`**:

```java
public class EvaluationOrder {
    static int left() {
        System.out.println("left");
        return 10;
    }

    static int right() {
        System.out.println("right");
        return 3;
    }

    public static void main(String[] args) {
        int result = left() + right() * 2;
        System.out.println(result);
    }
}
```

Run:

```bash
javac --release 17 EvaluationOrder.java
java EvaluationOrder
```

Stdout:

```text
left
right
16
```

`right() * 2` is grouped before the addition, yet `left()` is still evaluated first. Java cannot arbitrarily invert observable behavior simply because multiplication has higher precedence.

### 9.1. Avoid Stuffing `++` or Assignments into Complex Expressions

```java
int value = 4;
int result = value + value++;
```

Java has deterministic rules for the code above: the left operand reads `4` first, the right operand `value++` returns the old value `4` and increments the variable to `5`; `result` is `8`. Nonetheless, this code is **hard to read and easy to misread** in code reviews, especially when combined with nested parentheses, methods, and multiple side effects.

Replace with explicit steps:

```java
int value = 4;
int original = value;
value++;
int result = original + original;
```

The alternative clearly expresses the intent "add twice the pre-increment value". Parentheses do not substitute for separating side effects from arithmetic. Meanwhile, for conditional operators `&&`, `||`, and `?:`, Java uses conditional evaluation rules; do not lump them into "always evaluate every operand".

## 10. Complete Example: Parentheses and Intermediate Value Loss

Save the following content as **`IntegerParentheses.java`**:

```java
public class IntegerParentheses {
    public static void main(String[] args) {
        System.out.println(18 / 3 + 3);
        System.out.println(18 / (3 + 3));

        System.out.println((20 / 3) / 2);
        System.out.println(20 / (3 / 2));

        int seven = 7;
        System.out.println((seven / 2) * 2);
        System.out.println((seven * 2) / 2);

        System.out.println((double) (seven / 2));
        System.out.println((double) seven / 2);

        System.out.println(-7 / 2);
        System.out.println(-7 % 2);
    }
}
```

Compile/run with JDK 17+:

```bash
javac --release 17 IntegerParentheses.java
java IntegerParentheses
```

**Exact stdout:**

```text
9
3
3
20
6
7
3.0
3.5
-3
-1
```

Key observations: parentheses `(3 + 3)` change the divisor; `20 / (3 / 2)` computes the denominator in `int` first; `(seven / 2) * 2` loses the remainder; casting after division cannot recover `0.5`; with negative numbers, integer division truncates toward zero.

## 11. Complete Example: Overflow Before Assigning to a Wider Type

Save as **`IntermediateOverflow.java`**:

```java
public class IntermediateOverflow {
    public static void main(String[] args) {
        int a = 2_000_000_000;
        int b = 1_000_000_000;

        long lateCast = (long) (a + b);
        long earlyCast = (long) a + b;
        System.out.println(lateCast);
        System.out.println(earlyCast);

        int n = 50_000;
        int wrongSum = n * (n + 1) / 2;
        long correctSum = (long) n * (n + 1) / 2;
        System.out.println(wrongSum);
        System.out.println(correctSum);

        try {
            Math.addExact(a, b);
            System.out.println("no overflow");
        } catch (ArithmeticException ex) {
            System.out.println("overflow detected");
        }
    }
}
```

Run:

```bash
javac --release 17 IntermediateOverflow.java
java IntermediateOverflow
```

**Exact stdout:**

```text
-1294967296
3000000000
-897458648
1250025000
overflow detected
```

Each line is explained by the intermediate operation type:

1. `a + b` computes in `int` first before casting, yielding the overflowed value.
2. `(long) a + b` uses `long` addition from the start.
3. `n * (n + 1)` computes in `int` and overflows before dividing by two.
4. `(long) n * (n + 1)` computes in `long` from the multiplication, producing the exact mathematical sum.
5. `Math.addExact(a,b)` detects the out-of-range `int` addition and throws the caught exception.

In production code, when the sum must be `int`, you can perform `long` addition and then use `Math.toIntExact` to validate before converting back to `int`. Avoid using a narrowing `(int)` cast as if it were a check.

## 12. Edge Cases: Minimum Integer, Division by Zero, Casts, and Negation

### 12.1. Integer Division by Zero

Dividing an `int` or `long` by `0` (or taking remainder by `0`) throws `ArithmeticException` at runtime if the division actually executes.

```java
int denominator = 0;
// int invalid = 10 / denominator; // runtime ArithmeticException
```

When the denominator is a **parenthesized expression**, you must check the **evaluated denominator value**:

```java
int a = 10;
int b = 2;
int c = 3;
// int invalid = a / (b / c); // b / c = 0, then 10 / 0
```

Do not check `b != 0` and `c != 0` individually and assume `b / c != 0`.

### 12.2. Minimum Value Divided by `-1`

`Integer.MIN_VALUE` is `-2_147_483_648`. Its opposite, `2_147_483_648`, lies outside the `int` range. Per the Java specification, `Integer.MIN_VALUE / -1` returns `Integer.MIN_VALUE` again (a special overflow case), without throwing an exception.

```java
int min = Integer.MIN_VALUE;
System.out.println(min / -1);         // -2147483648
System.out.println((long) min / -1);   // 2147483648
```

If exact `int` division must report overflow, check this boundary explicitly before dividing; `Math.negateExact(Integer.MIN_VALUE)` also throws `ArithmeticException` when overflow-checked negation is needed. Parentheses do not automatically widen the expression.

### 12.3. Narrowing Casts and Compound Operations

`int result = (int) ((long) Integer.MAX_VALUE + 1);` can receive `Integer.MIN_VALUE` because casting `long` down to `int` drops high bits; casting does not imply a safe operation.

`short` and `byte` are promoted to `int` in regular addition. The operation `s += 1` follows compound assignment rules including an implicit cast, unlike `s = s + 1` when `s` is `short`. This is an easily hidden source of **intermediate data loss**; do not change parentheses to "fix" an unchecked type conversion.

## 13. When Does Moving Parentheses Change the Result, and When Does It Not?

| Scenario | What can moving parentheses change? | How to handle |
| --- | --- | --- |
| `(a / b) / c` ↔ `a / (b / c)` | Quotient, divide-by-zero error | Write the intended formula and check intermediate divisors |
| `(a - b) - c` ↔ `a - (b - c)` | Result value | Check signs and meaning of each subtraction |
| `(a + b) * c` ↔ `a + (b * c)` | Different formula, overflow can occur at different points | Choose grouping per business logic and select types before each operation |
| `(a + b) + c` ↔ `a + (b + c)`, all pure `int` | Intermediates may differ; final `int` result is identical modulo 2³² | Do not claim parentheses always change the result |
| `(long) (a + b)` ↔ `(long) a + b` | **Type of the addition** and overflow risk | Cast before the addition if `long` is needed |
| `(double) (a / b)` ↔ `(double) a / b` | `int` division ↔ `double` division | Convert type before dividing if fractional part is required |
| `Math.addExact(Math.addExact(a,b),c)` ↔ alternative checked grouping | Where overflow is detected | Standardize the step-by-step checking contract |
| Expressions with `++`/methods | Side effects, observable order | Extract intermediate variables and side effects for readability |

An "algebraically equivalent" expression in mathematics is not necessarily equivalent in **value, exceptions, or side effects** in Java. Conversely, do not overstate it: pure integer addition/multiplication of the same type remains associative under modular wraparound, as explained.

## 14. Techniques for Writing Readable and Safe Expressions

**Step 1: write the formula according to business logic.** For example, "sum 1..n" corresponds to `n * (n + 1) / 2`; "divide by the sum of two quantities" is `total / (left + right)` if that is genuinely the denominator.

**Step 2: sketch the intermediate result tree on paper.** Annotate each operation with its type and range:

```text
             /
           /   \
          *     2 (int)
        /   \
 n (int)    +
           /   \
        n(int)  1(int)

n = 50_000
n + 1   -> int = 50_001
n * ... -> int overflow
... / 2 -> int is no longer the mathematical sum
```

**Step 3: convert types before operations that risk exceeding the range.** For example, `(long) n * (n + 1) / 2`. If `long` still risks overflowing, `Math.multiplyExact` or `BigInteger` may be more suitable, depending on the contract.

**Step 4: specify integer division rules.** If ceiling group count is needed, do not blindly use `(items + size - 1) / size` for all inputs because `items + size - 1` can overflow `int`, and negative values have different semantics. Choose a formula proven for the input domain; you can use quotient/remainder or an appropriate wider type.

**Step 5: split long expressions and add named intermediates.** For example:

```java
int n = 50_000;
long next = (long) n + 1;
long product = (long) n * next;
long result = product / 2;
```

Splitting like this helps with debugging, logging, and attaching checks at each step. For simple calculations, parentheses aid readability; for complex business rules, **named intermediate variables** are usually clearer than deeply nested parentheses.

**Step 6: test boundaries.** At minimum include `0`, `1`, negative numbers if allowed, zero divisors, `Integer.MIN_VALUE`/`MAX_VALUE`, inputs causing intermediate overflow, and divisions with remainders.

## 15. Self-Practice Exercises with Answers

### Exercise 1 — Predict the Result

Given `int a = 18, b = 3, c = 3;`, what are the results of `a / b + c` and `a / (b + c)`?

**Answer:** `9` and `3`. The first expression groups as `(a/b)+c`; the second uses `b+c` as the divisor.

### Exercise 2 — Moving Parentheses in Integer Division

Given `a = 20, b = 3, c = 2`, compare `(a/b)/c` and `a/(b/c)`.

**Answer:** `3` and `20`; `20/3` becomes `6`, then `6/2` becomes `3`, whereas `3/2` becomes `1`, then `20/1` becomes `20`.

### Exercise 3 — Late Cast

Why doesn't `long total = (long) (Integer.MAX_VALUE + 1);` yield `2147483648`?

**Answer:** the `int` addition already overflowed to `-2147483648` before casting. Fix by writing `(long) Integer.MAX_VALUE + 1` or use `Math.addExact` if `int` error reporting is required.

### Exercise 4 — Final Result Fits `int` Yet Still Wrong

Given `int n = 50_000;`, explain the bug in `n*(n+1)/2` and fix it.

**Answer:** the product `2_500_050_000` overflows `int` before dividing. `(long)n*(n+1)/2` produces `1_250_025_000`. If the result must be `int`, validate using `Math.toIntExact`.

### Exercise 5 — Distinguishing Promotion and Parentheses

Is `byte x=100, y=20; byte z=(x+y);` valid?

**Answer:** no; `x+y` has type `int`. Parentheses do not change the type. Use `int z=x+y;` or a checked narrowing cast when `byte` data is required.

### Exercise 6 — Pure `int` Addition Case

Given `x=Integer.MAX_VALUE, y=1, z=-1`, does `(x+y)+z` differ from `x+(y+z)`?

**Answer:** no; both final results are `Integer.MAX_VALUE`, even though the intermediates differ. This reflects the associativity of modular `int` addition; it does not apply directly to checked addition, division, floating-point, or side effects.

### Exercise 7 — Hidden Division by Zero Inside Parentheses

With `int x=10, y=2, z=3;`, why does `x/(y/z)` fail at runtime even though both `y` and `z` are non-zero?

**Answer:** `y/z` in integer division equals `0`; the outer division becomes `10/0` and throws `ArithmeticException`.

### Exercise 8 — Method Call Order

In `left() + right() * 2`, which method runs first? Which operands is multiplication grouped with?

**Answer:** `left()` is evaluated before `right()`; the expression structure is `left() + (right() * 2)`. Distinguish evaluation order from operation grouping.

## 16. Checklist and Official References

- [ ] I correctly read precedence, associativity, and grouping when seeing `( ... )`.
- [ ] I distinguish operand **evaluation order** from **execution order of grouped operations**.
- [ ] I accurately predict integer division results, remainder signs, and detect intermediate zero divisors.
- [ ] I do not assume `long result = intA * intB` automatically protects against `int` overflow.
- [ ] I place casts before operations that need a wider type and verify the type of every intermediate result.
- [ ] I know that `(a+b)+c` and `a+(b+c)` on the same pure integer type do not inherently differ in final result; conversely, division and checked operations do differ.
- [ ] I handle negative numbers, `Integer.MIN_VALUE / -1`, and boundary values properly.
- [ ] I separate side effects out of complex arithmetic expressions.
- [ ] I have run at least two complete programs and tested additional boundary cases.

Further reading for Java SE 17:

- [JLS §15.7 — Evaluation Order](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.7): evaluation order and preservation of parentheses/precedence.
- [JLS §15.8.5 — Parenthesized Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.8.5): parenthesized expressions and expression types.
- [JLS §15.17 — Multiplicative Operators](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.17): multiplication/division/remainder.
- [JLS §15.18 — Additive Operators](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.18): addition/subtraction.
- [JLS §5.6 — Numeric Contexts](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.6): promotion and operation types.
- [Java SE 17 Math API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html): `addExact`, `multiplyExact`, `toIntExact`, `floorDiv`.

**Practical takeaway:** parentheses choose the **structure of operations**, while precision and overflow are decided at **each intermediate operation**. Write the formula accurately, verify the type and range of every step, and validate with boundary data.