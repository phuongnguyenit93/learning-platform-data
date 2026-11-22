# Bitwise AND, OR, XOR, and NOT in Java

> **Java core — language-basics / Bitwise operators**  
> **Environment:** JDK 17+; standard Java library only.  
> **Goal:** Understand `&`, `|`, `^`, and `~` on integer bits; read truth tables, manipulate bit masks, and handle negative numbers and numeric promotion rules properly.

## 1. How Do Bitwise Operators Work?

Every integer is stored as a sequence of 0/1 bits. Bitwise operations process **each corresponding bit position** of the operands:

| Operator | Name | Rule for each bit position |
| --- | --- | --- |
| `&` | AND | Result is 1 **only when both bits are 1** |
| `\|` | OR | Result is 1 when **at least one bit is 1** |
| `^` | XOR | Result is 1 when **the two bits are different** |
| `~` | NOT (bitwise complement) | **Inverts each bit:** 0 → 1; 1 → 0 |

Example with two `int` values:

~~~java
int a = 0b1100; // 12
int b = 0b1010; // 10

int and = a & b; // 0b1000 = 8
int or  = a | b; // 0b1110 = 14
int xor = a ^ b; // 0b0110 = 6
~~~

`0b` is the binary literal prefix in Java. Underscores can help make bit groups easier to read, such as `0b1100_1010`.

## 2. Truth Table for AND, OR, XOR, NOT

Treat `A` and `B` as **a single bit**:

| A | B | A AND B | A OR B | A XOR B | NOT A |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 0 | 0 | 0 | 0 | 1 |
| 0 | 1 | 0 | 1 | 1 | 1 |
| 1 | 0 | 0 | 1 | 1 | 0 |
| 1 | 1 | 1 | 1 | 0 | 0 |

`NOT A` depends only on `A`, not on `B`.

You can visualize the operations column by column:

~~~text
   a  = 1100  (12)
   b  = 1010  (10)
a & b = 1000  ( 8)
a | b = 1110  (14)
a ^ b = 0110  ( 6)
~~~

From the truth table, it follows that:

- `x & 0` is always 0; `x | 0` equals `x`.
- `x ^ 0` equals `x`; `x ^ x` equals 0.
- `x & x` and `x | x` both equal `x`.

These properties are useful for setting, clearing, toggling, and checking flags.

## 3. `~` Inverts **All** Bits, Not Just the Visible Ones

For `int`, Java uses **32 signed bits**. Thus `~a` inverts **all 32 bits**, not just the four bits `1100` written in the literal:

~~~java
int a = 0b1100; // 12
System.out.println(~a); // -13, not 3.
~~~

Signed integers use **two's complement** representation. For `int`/`long`, the following identity holds:

~~~text
~n == -n - 1
~12 == -13
~~~

If you only want to examine the low four bits, use a **mask**:

~~~java
int lowFour = (~a) & 0b1111; // 0b0011 = 3.
~~~

This is the difference between `~a` (inverting every bit of an `int` value) and `(~a) & 0b1111` (keeping the **low 4 bits** after inversion).

`int` is 32 bits wide and `long` is 64 bits wide. `~` cannot be applied to `boolean`; boolean logical negation uses `!`.

## 4. Short Application: Reading, Setting, Clearing, and Toggling a Bit

A *bit mask* places a 1 bit at the position to manipulate. From the truth tables of AND, OR, and XOR, four rules are enough to try on integers:

```java
int flags = 0b0101;             // Bit 0 and bit 2 are set.
int mask = 0b0010;              // Select bit 1.
boolean hasBit = (flags & mask) != 0; // false.
int set = flags | mask;         // 0b0111, set bit 1.
int cleared = flags & ~0b0100; // 0b0001, clear bit 2.
int toggled = flags ^ 0b0001;  // 0b0100, toggle bit 0.
```

**AND filters bits**, **OR sets bits**, **AND with NOT clears bits**, **XOR toggles bits**. Both `flags & mask` and `flags | mask` produce an **integer** result, not a `boolean`: to test in an `if`, compare `(flags & mask) != 0` (at least one bit is set) or `(flags & mask) == mask` (all bits in the mask are set).

This is only a **direct application of the truth table**. When managing multiple flags in practice, you also have to consider whether the mask is 0, whether flags fall within a valid range, how *any/all* checks are written, and concurrency concerns; these operations must not be assumed to constitute a secure authorization system purely from bitwise math.

## 5. Data Types and Integer Numeric Promotion

Bitwise operators apply to **integral** types (`byte`, `short`, `char`, `int`, `long`). When using `&`, `|`, `^` with integers, Java applies *binary numeric promotion*:

- Operands of type `byte`, `short`, and `char` are promoted to at least `int`.
- If either operand has type `long`, the integer operation is performed in `long`.
- `~` on `byte`, `short`, or `char` also produces an `int` result after unary numeric promotion.
- `float` and `double` cannot be used with these bitwise operators.

~~~java
byte small = 0b0000_1111; // 15
int inverse = ~small;    // -16 (int), not byte.
int lowEight = inverse & 0xFF; // 240: keep the low 8 bits.

// byte invalid = ~small; // Compile error: int cannot be implicitly assigned to byte.
~~~

With negative bytes, Java converts them to `int` with sign extension before performing many operations. When you want to treat a byte as an **unsigned number in the range 0..255**, use `value & 0xFF` or `Byte.toUnsignedInt(value)`.

`long` example:

~~~java
long bits = 0x1_0000_0005L;
long mask = 0x1_0000_0000L;
long highFlag = bits & mask; // 4294967296.
~~~

The `L` suffix and `long` type are crucial when flags sit at high bit positions beyond the range of `int`.

## 6. Do Not Confuse Bitwise Operators with Logical Operators

On `boolean`, Java also allows `&`, `|`, and `^`, but they perform **boolean logical operations**, not bit manipulation on numbers:

~~~java
boolean a = true;
boolean b = false;
boolean both = a & b;  // false.
boolean either = a | b; // true.
boolean one = a ^ b;    // true.
boolean not = !a;      // false.
~~~

| Operator | On integers | On booleans |
| --- | --- | --- |
| `&`, `\|`, `^` | Bitwise AND/OR/XOR | Logical AND/OR/XOR, **evaluates both sides** |
| `~` | Bitwise inversion of an integer | **Invalid** |
| `!` | **Invalid** | Logical negation |
| `&&`, `\|\|` | **Invalid** | **Short-circuiting** logical AND/OR |

Important difference: `false & check()` **still calls** `check()`; `false && check()` **skips** the call. Similarly, `true | check()` still calls `check()`, whereas `true || check()` does not.

The precedence of binary bitwise operators is **`&` higher than `^`, higher than `|`**. Use parentheses when mixing multiple operators, especially mask expressions with comparison operators.

## 7. Standalone Runnable Java 17+ Example

Create the file **BitwiseOperatorsDemo.java**:

~~~java
public final class BitwiseOperatorsDemo {
    private static String bits4(int value) {
        String raw = Integer.toBinaryString(value & 0b1111);
        return "0".repeat(4 - raw.length()) + raw;
    }

    public static void main(String[] args) {
        int a = 0b1100; // 12
        int b = 0b1010; // 10

        System.out.println("a=" + bits4(a) + ",b=" + bits4(b));
        System.out.println("and=" + (a & b)
                + ",bits=" + bits4(a & b));
        System.out.println("or=" + (a | b)
                + ",bits=" + bits4(a | b));
        System.out.println("xor=" + (a ^ b)
                + ",bits=" + bits4(a ^ b));
        System.out.println("not=" + (~a)
                + ",low4=" + bits4(~a));
        System.out.println("notMasked=" + ((~a) & 0b1111));

        int flags = 0b0101;
        int mask = 0b0010;
        System.out.println("flags=" + bits4(flags));
        System.out.println("set=" + bits4(flags | mask));
        System.out.println("clear=" + bits4(flags & ~0b0100));
        System.out.println("toggle=" + bits4(flags ^ 0b0001));
        System.out.println("hasBit2=" + ((flags & 0b0100) != 0));
        System.out.println("allSelected=" + ((flags & 0b0101) == 0b0101));

        byte small = 0b0000_1111;
        int inverted = ~small;
        System.out.println("byteNot=" + inverted
                + ",low8=" + (inverted & 0xFF));

        long big = 0x1_0000_0005L;
        long highMask = 0x1_0000_0000L;
        System.out.println("longMask=" + (big & highMask));

        boolean yes = true, no = false;
        System.out.println("booleanAnd=" + (yes & no)
                + ",booleanOr=" + (yes | no)
                + ",booleanXor=" + (yes ^ no));
    }
}
~~~

Run in the directory containing the file (Bash, PowerShell, or Command Prompt):

~~~bash
javac -encoding UTF-8 BitwiseOperatorsDemo.java
java BitwiseOperatorsDemo
~~~

**Exact expected stdout:**

~~~text
a=1100,b=1010
and=8,bits=1000
or=14,bits=1110
xor=6,bits=0110
not=-13,low4=0011
notMasked=3
flags=0101
set=0111
clear=0001
toggle=0100
hasBit2=true
allSelected=true
byteNot=-16,low8=240
longMask=4294967296
booleanAnd=false,booleanOr=true,booleanXor=true
~~~

`not=-13` because `~` inverts all 32 bits of `int`; `low4=0011` displays only the low four bits. `byteNot=-16` because `byte` is promoted to `int`; `low8=240` is the low eight bits. The mask results show how to manipulate individual flags without altering unselected bits.

## 8. Common Pitfalls and Exercises

| Misconception | Correct conclusion |
| --- | --- |
| Thinking `~0b1100` yields just `0b0011` | `~` inverts **all 32 bits of `int`**; a mask is needed to keep the low four bits |
| Writing `if (flags & mask)` | Java requires a boolean; write `if ((flags & mask) != 0)` |
| Using `~true` or `!12` | `~` is only for integers, `!` is for booleans |
| Assuming `&`/`\|` on booleans short-circuit | No: both sides are evaluated |
| Assigning `~byteValue` directly to a `byte` | The result is promoted to `int` |
| Thinking XOR is the same as OR | XOR produces 0 when both bits are 1 |

**Exercise 1.** Compute `0b0110 & 0b1010`, `0b0110 | 0b1010`, and `0b0110 ^ 0b1010`. Write each result in four bits.

**Exercise 2.** Given `int flags = 0b0011;`, write statements to set the third bit (counting the lowest bit as bit 0), clear bit 0, and toggle bit 1.

**Exercise 3.** Explain why `~12 == -13` in Java, whereas `(~12) & 0b1111 == 3`.

**Exercise 4.** Given `byte b = 15;`, predict the type and value of `~b`. To inspect the low eight bits as a number in 0..255, what mask should you use?

**Exercise 5.** Compare `false & check()` with `false && check()` if `check()` increments a counter or can throw an exception.

### Key Takeaways

**`&` (AND), `|` (OR), and `^` (XOR) combine bits; `~` (NOT) inverts every bit of an integer type.** For signed `int`/`long`, `~n = -n - 1`; to examine specific bits, apply a mask. For `byte`/`short`/`char`, watch out for promotion to `int`. Use masks and parentheses clearly, and distinguish bitwise operators from short-circuiting boolean logic.
