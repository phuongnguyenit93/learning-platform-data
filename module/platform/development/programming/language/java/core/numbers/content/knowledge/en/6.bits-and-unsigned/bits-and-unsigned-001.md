# The `&`, `|`, `^`, and `~` Operators in Java — Bits and Unsigned Numbers

## 1. Lesson Objectives

In Java, **bitwise operators** act on the individual bits of integer values. They are very useful when working with status flags, bit-encoded permissions, binary protocols, device data, RGB color channels, and bit-level transformations.

This lesson focuses on four operators:

- `&` — bitwise AND;
- `|` — bitwise OR;
- `^` — bitwise XOR;
- `~` — NOT (inverts all bits).

After this lesson, you should be able to compute binary results by hand, understand why `~12` produces `-13`, know how `byte`/`short`/`char` are promoted to `int`, use bitmasks, and recognize the difference between bit manipulation and **signed/unsigned** integer interpretation.

**Prerequisites:** familiarity with `int`, `long`, binary literals `0b...`, hex literals `0x...`, and basic operators. The examples run standalone with JDK 17 or later. Java does not have primitive `unsigned int` or `unsigned long` types; the topic of "unsigned" here mainly refers to **how bits are interpreted** and the APIs that support unsigned operations.

## 2. Bits and Java Integer Representation

Each bit can only be `0` or `1`. Java uses integer types with fixed widths:

| Type | Width | Signed? | Notes |
| --- | ---: | --- | --- |
| `byte` | 8 bits | Signed | −128 to 127 |
| `short` | 16 bits | Signed | −32,768 to 32,767 |
| `char` | 16 bits | Unsigned | UTF-16 code unit, not a general-purpose numeric count type |
| `int` | 32 bits | Signed | −2³¹ to 2³¹ − 1 |
| `long` | 64 bits | Signed | −2⁶³ to 2⁶³ − 1 |

Values of `byte`, `short`, `int`, and `long` are interpreted using **two's complement** representation. The highest bit of an `int` or `long` carries the sign meaning when interpreted as a signed integer.

We can use eight or four bits to **illustrate on paper**, but remember: a Java operation on an `int` variable actually operates on **32 bits**; a `long` variable is **64 bits**. That is especially important with `~`.

For example, taking the low four bits:

```text
x = 12 = 1100
y = 10 = 1010
```

`12` in binary is `1100`, and `10` is `1010`. When representing two `int` values, the higher bits in this example are `0`.

## 3. Truth Tables: How the Four Operators Process One Bit

The three operators `&`, `|`, and `^` compare **two corresponding bits**:

| Bit A | Bit B | A `&` B | A `|` B | A `^` B |
| ---: | ---: | ---: | ---: | ---: |
| 0 | 0 | 0 | 0 | 0 |
| 0 | 1 | 0 | 1 | 1 |
| 1 | 0 | 0 | 1 | 1 |
| 1 | 1 | 1 | 1 | 0 |

For NOT `~`, there is only **one operand**:

| Bit A | `~`A |
| ---: | ---: |
| 0 | 1 |
| 1 | 0 |

You can remember them as:

- AND sets a bit only when **both** bits are set.
- OR sets a bit when **at least one** bit is set.
- XOR sets a bit when the **two** bits differ.
- NOT flips each bit, turning `0` into `1` and vice versa.

Do not apply the truth table to a single position and forget the remaining bits. Bitwise operators process all bits of the operands after Java applies its type promotion rules.

## 4. The `&` Operator: Bitwise AND

Consider `12` and `10`:

```text
     1100    (12)
   & 1010    (10)
   ------
     1000     (8)
```

The result is `8` because only the corresponding bit at position `2³` is `1` in both.

Java example:

```java
int x = 0b1100;
int y = 0b1010;
int both = x & y;      // 0b1000 = 8
```

### 4.1. Common Use Case: Checking a Bit

Each bit can represent a capability or flag. Suppose bit `2` indicates execute permission:

```java
int flags = 0b0101;
int execute = 0b0100;

boolean enabled = (flags & execute) != 0; // true
```

`flags & execute` keeps exactly the bits that are `1` in **both** `flags` and `execute`. If you only need to check **a single flag represented by one bit**, the `!= 0` condition is sufficient.

With a **multi-bit** mask, there are two different questions:

```java
int state = 0b0101;
int mask = 0b0110;

boolean any = (state & mask) != 0;    // true: at least one bit in mask is set
boolean all = (state & mask) == mask; // false: not all bits in mask are set
```

In particular, when `mask == 0`, the expression `(state & mask) == mask` is always true. If business logic requires the mask to contain at least one bit, validate `mask != 0` separately.

### 4.2. Use Case: Keeping a Subset of Bits

`value & 0xFF` keeps the **low 8 bits** and clears all higher bits. It is commonly used when interpreting a `byte` as a number from `0` to `255`:

```java
byte signed = (byte) 0xF0; // bit pattern 11110000, signed byte = -16
int unsigned = signed & 0xFF; // 240
```

This is a bitwise AND operation combined with Java's promotion rules, not turning `byte` into a new unsigned primitive type. See the section on unsigned numbers below.

## 5. The `|` Operator: Bitwise OR

```text
     1100    (12)
   | 1010    (10)
   ------
     1110    (14)
```

Example:

```java
int x = 0b1100;
int y = 0b1010;
int either = x | y;    // 0b1110 = 14
```

`|` is commonly used to **set bits** or **combine independent flags**:

```java
int flags = 0b0001;
int writeFlag = 0b0010;

flags = flags | writeFlag; // 0b0011
// Shorthand:
flags |= writeFlag;        // still 0b0011
```

If the bit is already set, ORing with `1` keeps that bit at `1`. Therefore, `flags |= mask` is **idempotent with respect to bit values**: repeating it multiple times will not accidentally clear the flag. However, the OR operation does not guarantee atomic updates to a shared variable across threads.

**Do not use arithmetic addition instead of OR to set a flag.** If the bit is already set, `flags + mask` can carry into another bit; `flags | mask` clearly expresses setting bits.

## 6. The `^` Operator: Bitwise XOR

```text
     1100    (12)
   ^ 1010    (10)
   ------
     0110     (6)
```

Example:

```java
int x = 0b1100;
int y = 0b1010;
int different = x ^ y; // 0b0110 = 6
```

XOR is useful when you need to **toggle selected bits**:

```java
int flags = 0b0101;
int mask = 0b0100;

flags ^= mask; // 0b0001: turns bit 2 off
flags ^= mask; // 0b0101: turns bit 2 back on
```

Important properties for integer bits:

- `x ^ 0 == x`.
- `x ^ x == 0`.
- `(x ^ mask) ^ mask == x`: applying the same XOR twice restores the original bits.
- `a ^ b == b ^ a` for integer operands of the same type.

**XOR is not exponentiation.** In Java, `2 ^ 3` equals `1` because `010 ^ 011 = 001`, **not** `8`. To compute powers, consider `Math.pow` for floating-point numbers or an integer multiplication algorithm with overflow checking depending on your requirements.

Another application is detecting bits that differ between two states: `changed = oldState ^ newState` produces a mask with `1` bits at the exact positions where they differ.

## 7. The `~` Operator: NOT Across *All* Bits of the Operand

`~` is a **unary** operator:

```java
int x = 12;
int flipped = ~x; // -13
```

Why is `~12` equal to `-13` instead of `3`?

If you only **draw four bits**, NOT gives:

```text
x = 1100
~   ----
    0011   (3, if inverted only within a 4-bit mask)
```

But `x` is a 32-bit `int`. Java inverts all **32 bits**:

```text
x:  00000000 00000000 00000000 00001100
~x: 11111111 11111111 11111111 11110011
```

The highest bit becomes `1`, so when interpreted in two's complement, the value is `-13`. For `int`/`long`, the exact identity in Java arithmetic is:

```text
~x == -x - 1
```

For example, `~0 == -1`, `~(-1) == 0`, and `~12 == -13`.

### 7.1. To Invert Within N Bits, You Must Use a Mask

Suppose you only care about the low four bits:

```java
int x = 0b1100;            // 12
int lowFourInverted = ~x & 0b1111;
System.out.println(lowFourInverted); // 3
```

The mask `0b1111` clears the high bits after NOT, keeping `0011`. Similarly, `~x & 0xFF` keeps the low eight bits of the inverted value.

### 7.2. `~` Is Not the Same as `!`

- `~` operates on **integer types** (after unary numeric promotion), inverting all bits.
- `!` operates on **`boolean`** (or unboxed `Boolean`), inverting the logical value.

`~true` is invalid; `!12` is also invalid. Correct usage:

```java
int invertedBits = ~12;       // -13
boolean invertedFlag = !true; // false
```

## 8. Data Types, Binary Numeric Promotion, and Intermediate Results

The operators `&`, `|`, and `^` with **integer operands** use **binary numeric promotion**. The `~` operator uses **unary numeric promotion**.

- `byte`, `short`, and `char` are promoted to `int` before the operation.
- `int` with `int` produces an `int` result.
- `long` combined with a smaller integer type produces a `long` result.
- `~byteValue`, `~shortValue`, or `~charValue` produces an `int`, not the narrower type automatically.
- There is no direct bitwise `&`/`|`/`^`/`~` on `float` or `double`.

Example:

```java
byte a = 0b0101;
byte b = 0b0011;
int andResult = a & b;     // 1, type int
int notResult = ~a;        // -6, type int

// byte invalid = a & b;  // error: expression is int, does not automatically narrow to byte
byte narrowed = (byte) (a & b); // explicit cast, value 1 in this example
```

**Note on compound assignment:** `a &= b` compiles when `a` is `byte`, because compound assignment includes an implicit cast to the target variable's type. However, `a = a & b` causes a type error because the right-hand side is `int`. Narrowing casts can discard high bits, so you should explicitly verify the value range.

### 8.1. Sign Extension When Promoting a Negative `byte`

Consider the eight-bit pattern `1111_0000`:

```java
byte raw = (byte) 0xF0;  // raw == -16
int promoted = raw;      // 0xFFFFFFF0, sign-extended
int unsigned = raw & 0xFF; // 0x000000F0 = 240
int inverse = ~raw;      // 0x0000000F = 15
```

Because `raw` is signed, when converted to `int`, the high bits are **sign-extended**. In `raw & 0xFF`, the mask clears the high 24 bits and preserves the low eight bits.

Java also provides `Byte.toUnsignedInt(raw)` to obtain `240` with clearer intent. For `short`, there is `Short.toUnsignedInt`. Do not write `Math.abs(raw)` as a substitute for interpreting an unsigned 8-bit value; the negative value of a signed type and an unsigned representation are two different things.

### 8.2. `char` Does Not Sign-Extend

`char` is an unsigned 16-bit value. When promoted to `int`, the high bits are `0`. For example, `char ch = 0xFF00; int n = ch;` yields `n = 65280`, not a negative number. Still, `~ch` has type `int` and can be negative because all 32 bits are inverted.

In text processing, `char` represents a **UTF-16 code unit**, which is not equivalent to a Unicode code point in all cases; do not use bitwise operators merely to manipulate character strings.

## 9. Distinguishing Integer Bitwise Operators from Boolean `&`, `|`, `^`

Java also defines `&`, `|`, and `^` for two **`boolean`** operands. In that case, they return `boolean`:

| Boolean operator | Rule |
| --- | --- |
| `a & b` | `true` when both `a` and `b` are `true` |
| `a | b` | `true` when at least one side is `true` |
| `a ^ b` | `true` when the two sides differ |

The key difference compared to `&&` and `||` is that **`&`/`|` on booleans evaluate both operands**, whereas `&&`/`||` **short-circuit**:

- `false && method()` does not call `method()`.
- `true || method()` does not call `method()`.
- `false & method()` still calls `method()`.
- `true | method()` still calls `method()`.
- `a ^ b` also evaluates both sides.

You cannot apply `&` between an `int` and a `boolean`; the expression `flags & true` is a compile-time error. Java does not treat the integer `0` as `false` or nonzero integers as `true`.

### Runnable example: comparing short-circuiting

Save the file **`BooleanBitwise.java`**:

```java
public class BooleanBitwise {
    static boolean check(String name) {
        System.out.println(name);
        return true;
    }

    public static void main(String[] args) {
        System.out.println(false & check("AND evaluated"));
        System.out.println(true | check("OR evaluated"));
        System.out.println(false && check("AND skipped"));
        System.out.println(true || check("OR skipped"));
        System.out.println(true ^ true);
    }
}
```

Run:

```bash
javac --release 17 BooleanBitwise.java
java BooleanBitwise
```

Stdout:

```text
AND evaluated
false
OR evaluated
true
false
true
false
```

The two labels "AND skipped" and "OR skipped" **do not appear**, because their corresponding methods are not called. In ordinary boolean expressions, prefer `&&`/`||` when you want short-circuiting; use `&`/`|` when you genuinely need both expressions evaluated and that intent is clear in the requirements.

## 10. Precedence: `~`, `&`, `^`, `|`

Among the operators covered here, the precedence order is:

1. `~` (unary bitwise complement).
2. `&`.
3. `^`.
4. `|`.

Example:

```java
int a = 0b1100;
int b = 0b1010;
int c = 0b0011;

int first = a | b & c;       // a | (b & c)
int second = (a | b) & c;    // (a | b) & c
```

Computing by hand:

- `b & c = 0010`; `a | 0010 = 1110` so `first == 14`.
- `a | b = 1110`; `1110 & 0011 = 0010` so `second == 2`.

With XOR:

```java
int ungrouped = a ^ b & c;   // a ^ (b & c) => 1100 ^ 0010 = 1110
int grouped = (a ^ b) & c;   // 0110 & 0011 = 0010
```

The two expressions yield `14` and `2`, respectively.

**Common trap with comparisons:** In Java, `==` has **higher** precedence than bitwise `&`. Therefore:

```java
// boolean invalid = flags & MASK == MASK;
// Java groups this as flags & (MASK == MASK): int & boolean -> compile error.

boolean correct = (flags & MASK) == MASK;
```

The snippet above is just a **syntax illustration**; you need to declare `flags` and `MASK` if placing it in a runnable class. Always wrap the bitwise part in parentheses inside conditions, such as `(flags & mask) != 0`, both to avoid errors and to make your intent clear.

The shift operators `<<`, `>>`, and `>>>` have higher precedence than `&`/`^`/`|`. They are used to position bits, but belong to a different group of operators; this lesson only uses shifts when creating masks and extracting data.

## 11. A Complete Program for All Four Operators

Save as **`BitwiseBasics.java`**:

```java
public class BitwiseBasics {
    public static void main(String[] args) {
        int x = 0b1100;
        int y = 0b1010;

        System.out.println(x & y);
        System.out.println(x | y);
        System.out.println(x ^ y);
        System.out.println(~x);
        System.out.println(~x & 0b1111);

        System.out.println(~0);
        System.out.println(~(-1));
    }
}
```

Run:

```bash
javac --release 17 BitwiseBasics.java
java BitwiseBasics
```

**Exact stdout:**

```text
8
14
6
-13
3
-1
0
```

Explanation: the first three lines match the bit tables for `1100`/`1010`; `~x` inverts all 32 bits of the `int` and becomes `-13`; `& 0b1111` keeps the low four bits, giving `3`. Inverting all bits of `0` produces `-1`, and inverting `-1` produces `0`.

**Do not call `Integer.toBinaryString(~x)` expecting only four characters**, because a negative `int` result is displayed in full as a 32-bit two's complement string. To inspect only the low bits, apply a mask before converting to a string.

## 12. Using Bitmasks to Set, Clear, Check, and Toggle Flags

A single-bit flag can be created with `1 << bit_position`. This gives four key idioms:

| Purpose | Idiom | Meaning |
| --- | --- | --- |
| Check **one** flag | `(flags & FLAG) != 0` | The bit representing the flag is on |
| Set a flag | `flags |= FLAG` | Set the bit to 1 |
| Clear a flag | `flags &= ~FLAG` | Reset the bit to 0 |
| Toggle a flag | `flags ^= FLAG` | Flip 0↔1 |
| Check all of **multiple** flags | `(flags & MASK) == MASK` | Every bit in the mask is on |

### Runnable example: bit-based permission states

Save as **`FlagDemo.java`**:

```java
public class FlagDemo {
    private static final int READ = 1 << 0;    // 001
    private static final int WRITE = 1 << 1;   // 010
    private static final int EXECUTE = 1 << 2; // 100

    public static void main(String[] args) {
        int permissions = READ | EXECUTE; // 101
        System.out.println(permissions);
        System.out.println((permissions & WRITE) != 0);

        permissions |= WRITE;   // 111
        System.out.println(permissions);

        permissions ^= EXECUTE; // 011
        System.out.println(permissions);

        permissions &= ~READ;   // 010
        System.out.println(permissions);
    }
}
```

Run:

```bash
javac --release 17 FlagDemo.java
java FlagDemo
```

**Stdout:**

```text
5
false
7
3
2
```

Sequence:

- `READ | EXECUTE` sets bit `0` and bit `2`, giving `101₂ = 5`.
- `WRITE` is not set yet, so the check returns `false`.
- `|= WRITE` also sets bit `1` → `111₂ = 7`.
- `^= EXECUTE` toggles bit `2` from `1` to `0` → `011₂ = 3`.
- `&= ~READ` clears bit `0` → `010₂ = 2`.

**Choosing the right operation:** when you want to **ensure a bit is on**, use `|`; when you want to **ensure a bit is off**, use `& ~`; only use `^` when you truly want to **toggle** the state. Using masks by itself does not replace application authorization rules or per-user/per-resource permission checks.

### 12.1. When the Bit Position Exceeds 31

`int` has 32 bits; `1 << 31` is valid but yields the negative value `Integer.MIN_VALUE` because it sets the sign bit. If you need a flag at position `40`, you must use `long`:

```java
long flag40 = 1L << 40;
```

Writing `1 << 40` **does not** produce bit 40 of an `int`: Java uses only the low 5 bits of the shift distance for `int`, so the effect is equivalent to shifting `1 << 8`. For `long`, the shift distance uses only the low 6 bits. Always choose the width before creating a mask and validate the bit index range.

## 13. `&` with Unsigned Numbers: Same Bits, Different Interpretation

Java has no primitive `unsigned int` or `unsigned long` types. `int` and `long` still use their respective bits for AND/OR/XOR/NOT even when interpreted as negative numbers. The difference between signed and unsigned lies in **how the value is interpreted and in certain other operations** (comparison, division, right shift), not in the truth tables of the four bitwise operators.

### 13.1. Reading a `byte` as 0..255

Save as **`UnsignedBits.java`**:

```java
public class UnsignedBits {
    public static void main(String[] args) {
        byte raw = (byte) 0xF0;

        System.out.println(raw);
        System.out.println(raw & 0xFF);
        System.out.println(Byte.toUnsignedInt(raw));
        System.out.println(~raw);
        System.out.println((byte) ~raw);
        System.out.println(Integer.toUnsignedString(-1));
    }
}
```

Run:

```bash
javac --release 17 UnsignedBits.java
java UnsignedBits
```

**Stdout:**

```text
-16
240
240
15
15
4294967295
```

Explanation:

1. `0xF0` has low 8 bits `11110000`; when cast to a signed `byte`, that is `-16`.
2. `raw & 0xFF` clears the sign-extended high bits → `240`.
3. `Byte.toUnsignedInt(raw)` returns the same value `240` with explicit unsigned intent.
4. `~raw` is computed as `int` after unary promotion: `~(-16) = 15`.
5. Casting `(byte) ~raw` in this example is still `15` because it fits within the `byte` range; with other data, a narrowing cast can truncate bits.
6. `Integer.toUnsignedString(-1)` interprets 32 all-`1` bits as `4294967295`. The bit representation does not change; only the way the value is read changes.

To compare or divide integers as unsigned values, Java also provides `Integer.compareUnsigned`, `Integer.divideUnsigned`, `Integer.remainderUnsigned`, along with the corresponding `Long` APIs. `char` is a 16-bit unsigned primitive case, though it primarily serves UTF-16.

### 13.2. Extracting Multiple Fields from One Number

A practical scenario is extracting three RGB color channels packed into 24 bits:

```java
int rgb = 0x12AB34;
int red   = (rgb >>> 16) & 0xFF;
int green = (rgb >>> 8)  & 0xFF;
int blue  = rgb & 0xFF;
```

Here `>>>` is **zero-fill right shift**, moving the group of bits to read into the low position; `& 0xFF` keeps only the corresponding eight bits. The three resulting values are: `red = 18`, `green = 171`, `blue = 52`. Using `&` to mask is central; you should study `>>`, `>>>`, and `<<` separately to understand full bit-packing algorithms.

## 14. Useful Algebraic Properties and Limits of Applicability

For integer operands of the same type and pure bitwise operations, the following laws hold across all bits of the type:

| Property | Expression |
| --- | --- |
| AND with 0 | `x & 0 == 0` |
| AND with all 1 bits | `x & -1 == x` |
| OR with 0 | `x | 0 == x` |
| OR with all 1 bits | `x | -1 == -1` |
| XOR with 0 | `x ^ 0 == x` |
| XOR with itself | `x ^ x == 0` |
| Double inversion | `~~x == x` (when `x` is already `int`/`long`) |
| De Morgan | `~(x & y) == (~x | ~y)` |
| De Morgan | `~(x | y) == (~x & ~y)` |

These laws are very helpful when simplifying masks. However, keep **the same bit width**, account for promotion, and do not arbitrarily rewrite expressions containing method calls or side effects into another form.

### 14.1. XOR Does Not Guarantee Safe Variable Swapping

The trick `a ^= b; b ^= a; a ^= b;` is often used to swap two numbers. It is hard to read, can fail when two references/locations actually point to the same element, and offers no default advantage in modern Java. Use an explicit temporary variable to swap values. The goal of learning XOR is to understand bits, not to replace every data operation with "tricks".

### 14.2. Bit Manipulation Does Not Mean Atomic Updates

`flags |= mask` is a read, OR, and write-back under normal semantics. If multiple threads modify the same variable concurrently, updates can be lost without synchronization. For concurrency requirements, use synchronization mechanisms or appropriate atomic update methods; the `|` operator itself does not provide thread safety.

## 15. Common Mistakes and How to Spot Them

1. **Confusing `^` with exponentiation:** `2 ^ 3` = `1`, not 8.
2. **Thinking `~12` is 3:** that is only the NOT result on the **low four bits**; `~12` as a 32-bit `int` equals `-13`. To get 3, use `(~12) & 0xF`.
3. **Forgetting `byte` promotion:** `~byteValue` yields `int`, not `byte`; `byteA & byteB` also yields `int`.
4. **Not masking after sign extension:** `byte raw = (byte) 0xF0` is `-16`; `raw & 0xFF` or `Byte.toUnsignedInt(raw)` returns 240.
5. **Using `^` to "turn a flag on":** XOR turns off a flag that is already on. Use `|` when you need to guarantee it is on.
6. **Using `|` to "turn a flag off":** to turn off a bit, you must use `flags &= ~FLAG`.
7. **Wrong precedence:** `flags & MASK == MASK` does not group as intended; write `(flags & MASK) == MASK`.
8. **Confusing `&` with `&&`:** for `boolean`, `&` always evaluates both sides, so the second method call still runs.
9. **Forgetting that `~` is NOT over the full width:** a narrower mask is only applied when you explicitly write `& mask` afterward.
10. **Creating a high-bit mask with `int`:** `1 << 40` is not a flag at bit position 40; use `1L << 40`.
11. **Confusing an unsigned bit pattern with a signed value:** the same `0xFFFFFFFF` is all 1 bits; read as `int` it is `-1`, read as unsigned 32-bit it is `4294967295`.
12. **Mixing floating-point/boolean with integer bitwise operators:** `1.5 & 2`, `~1.0`, or `3 & true` do not have valid operand types in Java.

## 16. Practice Exercises with Explanations

### Exercise 1 — Hand-compute the bit tables

Given `a = 0b1100` and `b = 0b1010`, compute `a & b`, `a | b`, and `a ^ b`.

**Answer:** `1000₂ = 8`, `1110₂ = 14`, `0110₂ = 6`. AND keeps bits that are 1 in both, OR keeps bits where at least one is 1, and XOR keeps only bits that differ.

### Exercise 2 — Why does NOT produce a negative number?

Compute `~0`, `~12`, and `~(-1)` with `int` operands.

**Answer:** `-1`, `-13`, and `0`. `~` inverts all 32 bits; the formula `~x = -x - 1` can help verify.

### Exercise 3 — Set, clear, toggle

Initially `flags = 0b0101`; you need to (a) set bit `1`, (b) clear bit `2`, and (c) toggle bit `0`.

**Answer:** (a) `flags |= 0b0010` → `0111`; (b) `flags &= ~0b0100` → `0011`; (c) `flags ^= 0b0001` → `0010`. The three steps are performed **sequentially**.

### Exercise 4 — One bit vs. multiple bits

`flags = 0b0101`, `mask = 0b0110`. What are the results of `(flags & mask) != 0` and `(flags & mask) == mask`?

**Answer:** `true` and `false`. The mask requires bits 1 and 2, but `flags` only has bit 2 set among those two bits.

### Exercise 5 — Promotion and unsigned byte

`byte raw = (byte) 0xF0;`. Compute `raw`, `raw & 0xFF`, and `~raw`.

**Answer:** `-16`, `240`, `15`. `raw` sign-extends to `int` in the two bitwise operations, while the `0xFF` mask keeps the low eight bits.

### Exercise 6 — Choosing the operator by intent

Why is `flags ^= FLAG` not the default choice to ensure a flag is enabled?

**Answer:** XOR **toggles** the bit. If the flag is already on, XOR turns it off. OR with `FLAG` ensures the bit is on, i.e., `flags |= FLAG`.

### Exercise 7 — Boolean with side effects

Suppose `probe()` prints a message and returns `true`. Compare `false & probe()` with `false && probe()`.

**Answer:** the first expression still calls `probe()` and returns `false`; the second expression skips `probe()` due to short-circuiting and also returns `false`.

### Exercise 8 — Mask at bit 40

Why is `1 << 40` wrong if the goal is to create a flag at bit position 40? Rewrite it correctly.

**Answer:** `1` is a 32-bit `int`; the effective shift distance only considers the low five bits, so `40` is treated as `8`. Write `1L << 40` to use `long` and shift to the right position.

### Exercise 9 — Extracting RGB colors

Given `rgb = 0x12AB34`. Use `& 0xFF` and right shifts to extract red, green, and blue.

**Answer:**

```java
int red   = (rgb >>> 16) & 0xFF; // 18
int green = (rgb >>> 8)  & 0xFF; // 171
int blue  = rgb & 0xFF;          // 52
```

This is a **code snippet**; place it inside a method with `int rgb = 0x12AB34;` before running.

## 17. Mastery Checklist

- [ ] I can construct the truth tables for AND, OR, XOR, and NOT on my own.
- [ ] I can explain `12 & 10 = 8`, `12 | 10 = 14`, and `12 ^ 10 = 6`.
- [ ] I do not confuse `~12` with inverting only four bits.
- [ ] I know `&`/`|`/`^` and `~` apply to integer types after promotion; `~byte` yields `int`.
- [ ] I can distinguish `&`/`|` on `boolean` from `&&`/`||` and short-circuit evaluation.
- [ ] I can choose a mask to set, clear, check, or toggle flags.
- [ ] I know to wrap check expressions in parentheses: `(flags & mask) != 0` and `(flags & mask) == mask`.
- [ ] I understand sign meaning when reading `byte`/`int` and how to mask out the unsigned low bits.
- [ ] I know flags at high bit positions require `long` and a `1L` literal before shifting.
- [ ] I have run the Java 17+ examples and checked negative numbers, high bits, and multi-bit masks.

**Official references:**

- [JLS 17 §15.22 — Bitwise and Logical Operators](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.22): rules for `&`, `^`, `|` with integers/booleans.
- [JLS 17 §15.15.5 — Bitwise Complement Operator](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.15.5): rules for the `~` operator.
- [JLS 17 §5.6 — Numeric Contexts](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.6): unary/binary numeric promotion.
- [JLS 17 §15.19 — Shift Operators](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.19): bit shifting and effective shift distance.
- [Java SE 17 Integer API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html): `toBinaryString`, `toUnsignedString`, and unsigned methods.
- [Java SE 17 Byte API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Byte.html): `toUnsignedInt`.

Always read bitwise expressions by **bit width, post-promotion type, mask, and operation intent**. The four operators have simple truth tables, but effectiveness and correctness depend on how you interpret those bits as values in Java.