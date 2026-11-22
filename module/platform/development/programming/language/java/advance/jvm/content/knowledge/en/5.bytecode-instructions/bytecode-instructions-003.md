# JVM Bytecode Instruction Groups: Arithmetic, Bitwise, Comparison, and Type Conversion

## Objectives

The Java Virtual Machine (JVM) bytecode is the instruction set defined in the *Java Virtual Machine Specification (JVMS)*. Programmers typically write Java operators such as `+`, `&`, `<`, or casts like `(int) x`; the compiler can translate them into corresponding JVM instructions that operate on the **operand stack** and **local variables**. A single source operator does not always correspond to an exact single opcode because there are also type promotions, data loads/stores, branches, library calls, and optimizations.

After this lesson, you will be able to:

- Read the names and type rules of arithmetic, bitwise, shift, comparison, and primitive conversion opcodes on the JVM.
- Explain how opcodes pop operands from the operand stack, push results, and use local variables.
- Distinguish between integer and floating-point overflow, signed and unsigned right shifts, comparison operators and branching instructions, and how NaN is handled.
- Understand type widening/narrowing, precision loss, truncation, and NaN/infinity cases during casting.
- Compile Java 17+ yourself, inspect bytecode via `javap -c -p`, and compare execution results against JVM rules.

## 1. Reading Instruction Naming Conventions and the Stack Model

Many opcodes have a **data type prefix** and an **operation suffix**:

| Prefix | Value type on the operand stack | Example |
| --- | --- | --- |
| `i` | `int` (also used as the representation for `boolean`, `byte`, `short`, `char` in many operations) | `iadd`, `iand`, `ishl`, `i2d` |
| `l` | `long` | `ladd`, `lcmp`, `lushr` |
| `f` | `float` | `fadd`, `fcmpl`, `f2i` |
| `d` | `double` | `ddiv`, `dcmpg`, `d2l` |

Beyond those prefixes, there are opcodes such as `iinc`, `if_icmplt`, or `if_acmpeq` with specialized roles. The JVM **does not have a separate full set of arithmetic opcodes for `byte`/`short`/`char`/`boolean`**; when needed, the compiler performs operations according to the Java language's **numeric promotion** and uses `int` or conversion opcodes to preserve semantics.

### The operand stack operates on the LIFO principle

For example, assume the operand stack currently holds two integers:

~~~text
Before iadd:    ..., value1, value2  (value2 at the top)
Execute iadd:   pop value2, pop value1; compute value1 + value2
After iadd:     ..., result
~~~

For non-commutative operations, order matters greatly: `isub` computes **value1 − value2**, and `idiv` computes **value1 / value2**, without reversing the two operands.

In the JVMS opcode descriptions, the pattern `..., value1, value2 → ..., result` is a **stack model**, not compilable Java syntax. The `long` and `double` types belong to **category 2** (occupying two units of stack depth), whereas `int` and `float` belong to **category 1**. The bytecode verifier checks types and stack shapes across valid control-flow paths.

### Local variables and arithmetic bytecode

A complete Java method example:

~~~java
public static int add(int left, int right) {
    return left + right;
}
~~~

This is **a method**, not a standalone runnable class. With standard `javac`, the corresponding bytecode has the form:

~~~text
0: iload_0
1: iload_1
2: iadd
3: ireturn
~~~

The two `iload` instructions load local variables onto the stack, `iadd` computes the sum, and `ireturn` returns the value to the caller. Do not confuse `iadd` with operating directly on two local variable slots; addition takes two values **on the operand stack**. Different compilers may generate equivalent sequences, and bytecode indices/offsets are not part of Java program semantics.

## 2. Arithmetic Group: `add`, `sub`, `mul`, `div`, `rem`, and `neg`

Each row has corresponding variants for `int`, `long`, `float`, and `double`:

| Operation | `int` | `long` | `float` | `double` |
| --- | --- | --- | --- | --- |
| Addition | `iadd` | `ladd` | `fadd` | `dadd` |
| Subtraction | `isub` | `lsub` | `fsub` | `dsub` |
| Multiplication | `imul` | `lmul` | `fmul` | `dmul` |
| Division | `idiv` | `ldiv` | `fdiv` | `ddiv` |
| Remainder | `irem` | `lrem` | `frem` | `drem` |
| Negation | `ineg` | `lneg` | `fneg` | `dneg` |

Binary instructions pop two operands of the corresponding type and push one result. Negation opcodes are unary: `..., value → ..., result`. There are no direct opcodes to add or multiply two `BigInteger` or `BigDecimal` objects; those operations are performed via library method calls.

### Integer overflow: modulo by bit width

`int` is 32-bit signed and `long` is 64-bit signed. Integer addition/subtraction/multiplication instructions use fixed bit-widths; if the mathematical result exceeds the representable range, the high-order bits are discarded. The result corresponds to two's complement representation; **it does not automatically throw `ArithmeticException` on overflow**.

~~~java
int a = Integer.MAX_VALUE;
System.out.println(a + 1); // -2147483648
System.out.println(-Integer.MIN_VALUE); // -2147483648
~~~

This is a snippet inside a Java method. The second example shows that negating the smallest integer still yields itself because its positive counterpart cannot be represented in 32 bits.

If business logic requires **overflow detection**, use APIs such as `Math.addExact`, `Math.subtractExact`, `Math.multiplyExact`, `Math.negateExact`, or design with larger number types. In bytecode, these are typically **method calls** (for example, `invokestatic`), not an "`iaddExact`" variant in the JVMS.

### Integer division and remainder

- `idiv`/`ldiv` perform signed integer division; the quotient is rounded **toward 0**.
- `irem`/`lrem` compute the remainder under the same division rule; when the remainder is non-zero, **the sign of the remainder follows the dividend**.
- If **the divisor is 0**, `idiv`, `ldiv`, `irem`, and `lrem` throw `ArithmeticException`.
- Special case: `Integer.MIN_VALUE / -1` returns `Integer.MIN_VALUE` due to overflow; `Integer.MIN_VALUE % -1` returns `0`. The `long` version behaves similarly.

~~~java
System.out.println(-7 / 3); // -2
System.out.println(-7 % 3); // -1
System.out.println(7 % -3); // 1
~~~

If you want division toward negative infinity or mathematical modulo used in certain algorithms, see `Math.floorDiv` and `Math.floorMod`, because the sign of the result can differ from the `/` and `%` operators.

### Floating-point numbers differ from integers

For `float`/`double`, the JVM executes according to the IEEE 754 floating-point semantics specified by Java:

- `1.0 / 0.0` yields `+Infinity`; `-1.0 / 0.0` yields `-Infinity`.
- `0.0 / 0.0` yields `NaN`, without throwing `ArithmeticException` simply because the denominator is 0.
- Operations exceeding the finite range can produce infinity; operations that are too small can produce subnormals and then approach `±0.0`.
- `frem`/`drem` perform floating-point remainder according to **Java's remainder rule, not the IEEE remainder definition that uses the nearest integer quotient**. When you want IEEE remainder, use `Math.IEEEremainder`.
- `fneg`/`dneg` flip the sign of a floating-point value; for `+0.0` and `-0.0`, the sign bits differ.

Since **Java 17**, JEP 306 restored **always-strict floating-point semantics**: Java's floating-point operations follow strict rules, eliminating semantic differences caused by optional extended intermediate exponents as before. Even so, floating-point addition still involves rounding and is not necessarily associative; different evaluation orders can produce different final results.

## 3. The Local Variable Increment Instruction `iinc`

`iinc` is a special opcode: it **increments a local variable of type `int` by a signed constant encoded in the instruction**, rather than popping two operands from the operand stack.

~~~text
iinc <local_index>, <signed_constant>
~~~

For example, the compiler can use `iinc 1, 1` for `i++` or `++i` when `i` is a local variable of type `int` and the expression's value does not need to be kept on the stack. The increment behavior also follows 32-bit overflow just like normal integer addition.

- `iinc` is not used to directly increment a `long` local or an object field.
- The compiler is not forced to emit `iinc` for every `i++` syntax. If the pre/post-increment value is needed, the compiler may use additional load/store instructions or choose another sequence.
- The standard form of `iinc` contains a local index operand and a signed 8-bit constant; the `wide` prefix allows larger operands.

Do not call `iinc` an instruction that computes on the operand stack: it acts **directly on a local variable** in the current frame.

## 4. Bitwise Group: AND, OR, XOR

The JVM supports bitwise operations on **`int` and `long`**:

| Source operator | Opcode on `int` | Opcode on `long` | Bitwise meaning |
| --- | --- | --- | --- |
| `&` | `iand` | `land` | Result bit is 1 when both corresponding bits are 1. |
| `|` | `ior` | `lor` | Result bit is 1 when at least one bit is 1. |
| `^` | `ixor` | `lxor` | Result bit is 1 when the two corresponding bits differ. |

Small 4-bit number example:

~~~text
a = 10  = 1010
b = 12  = 1100

a & b  = 1000 = 8
a | b  = 1110 = 14
a ^ b  = 0110 = 6
~~~

This is an illustration on the lowest four bits, not an `int` size limit. In practice, all operations on `int` act on the full 32 bits; on `long`, 64 bits.

**There is no `fand`, `dand`, or `inot` opcode.** The source operator `~x` inverts each bit on `int`/`long` and can be implemented by the compiler via XOR with an all-1s bit pattern (`-1`), for example `iconst_m1` followed by `ixor`. There is no dedicated JVM instruction named `inot` for integer bitwise inversion.

### Bitwise with boolean differs from short-circuit

In the Java language, `&`, `|`, and `^` can also be applied to `boolean`, but those boolean expressions are usually translated by the compiler into appropriate int/branch operations. Distinguish:

- `a && b` and `a || b`: **short-circuit**, the right-hand side may not be evaluated.
- `a & b` and `a | b` with boolean: **always evaluate both sides**.
- boolean `^`: true when the two operands differ.

The bytecode system has no separate arithmetic opcode set for boolean; compiler details may use int instructions, branches, or combinations depending on context.

### Checking bit flags

~~~java
int permissions = 0b1010;
int writeFlag = 0b0010;

boolean canWrite = (permissions & writeFlag) != 0;
System.out.println(canWrite); // true
~~~

This is an illustrative snippet inside a method. With bit masks, pay attention to signedness when shifting bits and when serializing to types of a different width.

## 5. Shift Group: `shl`, `shr`, and `ushr`

Only `int` and `long` support direct bit shifting; the shift count on the operand stack is **`int`** in both cases:

| Java | `int` | `long` | Description |
| --- | --- | --- | --- |
| `value << distance` | `ishl` | `lshl` | Shift left, filling low bits with 0; discarding high bits that overflow the width. |
| `value >> distance` | `ishr` | `lshr` | **Arithmetic** right shift, filling high bits with the old sign bit. |
| `value >>> distance` | `iushr` | `lushr` | **Logical** right shift, filling high bits with 0. |

For negative operands, `>>` and `>>>` differ markedly:

~~~java
int x = -8;
System.out.println(x >> 1);  // -4
System.out.println(x >>> 1); // 2147483644
~~~

In two's complement representation, `-8` is a 32-bit sequence starting with many 1 bits. Arithmetic right shift preserves the sign bit 1 so it remains negative; logical right shift fills with 0 so it becomes a large positive value.

### Shift count is masked

The JVM uses the **lowest 5 bits** of the shift distance for `int`, meaning the actual distance is `distance & 0x1F` (modulo 32). For `long`, the JVM uses the **lowest 6 bits**, meaning `distance & 0x3F` (modulo 64).

~~~java
System.out.println(1 << 32);  // 1, because 32 & 31 = 0
System.out.println(1L << 64); // 1, because 64 & 63 = 0
System.out.println(1 << -1);  // -2147483648, because -1 & 31 = 31
~~~

A negative shift distance **does not automatically throw an exception**; the bit-masking rule still applies. This is a common source of bugs if you assume shifting by more than the bit width always returns 0.

Note: left-shifting bits out does not automatically throw an exception; `x << n` is only equivalent to multiplying by a power of 2 within the non-overflow range and under appropriate value conditions. When using shifts to compute buffer sizes, bit masks, or encodings, clearly determine the data width and handle overflow.

## 6. Comparison Group: Result-Producing Instructions and Branching Instructions

In bytecode there are **two mechanisms that are often conflated into one**:

1. Instructions that compare large/float values and **push an `int` result** onto the stack.
2. Conditional branch instructions (**`if...`**) that test one or two values on the stack and decide whether to transfer execution to another offset.

For example, Java code §a < b§ does not necessarily emit an instruction named §icmp§ and return a boolean; for two §int§ values, the JVM has the direct branch instruction §if_icmplt§.

### Comparing two `int` values and branching

| Opcode | Branches when |
| --- | --- |
| `if_icmpeq` | value1 == value2 |
| `if_icmpne` | value1 != value2 |
| `if_icmplt` | value1 < value2 |
| `if_icmple` | value1 <= value2 |
| `if_icmpgt` | value1 > value2 |
| `if_icmpge` | value1 >= value2 |

These instructions **pop two int values**; if the condition is true, control flow jumps to the target label/offset, without automatically pushing a Java §boolean§ value 1 or 0. To return a boolean from a comparison expression, the compiler can generate branching code and put §iconst_0§/§iconst_1§ onto the stack, then use §ireturn§.

The `ifeq`, `ifne`, `iflt`, `ifle`, `ifgt`, `ifge` group instead tests **a single int value against 0**. They are commonly used after `lcmp`, `fcmp*`, `dcmp*`, or for conditions already encoded as an int.

Besides numeric comparisons, there are `if_acmpeq`/`if_acmpne` to compare **two object references** by identity, and `ifnull`/`ifnonnull` to check for null; these instructions do not invoke `Object.equals`.

### Comparing two `long` values: `lcmp`

`lcmp` pops two `long` values from the stack, performs a **signed** comparison, and pushes an `int` result:

~~~text
value1 > value2  →  1
value1 = value2  →  0
value1 < value2  → -1
~~~

Illustrative method example:

~~~java
static boolean isEarlier(long a, long b) {
    return a < b;
}
~~~

A typical Java compiler may use `lcmp` followed by `ifge` (or an equivalent branch form) to construct the boolean. **There is no set of six `if_lcmpeq`... opcodes** corresponding to `if_icmp*` for int.

### Comparing `float`/`double` and NaN

The opcodes:

- `fcmpl`, `fcmpg` for `float`.
- `dcmpl`, `dcmpg` for `double`.

All four instructions pop two floating-point values and push an `int`:

| Comparison condition | `fcmpl/dcmpl` | `fcmpg/dcmpg` |
| --- | --- | --- |
| value1 < value2 | -1 | -1 |
| value1 == value2 | 0 | 0 |
| value1 > value2 | 1 | 1 |
| At least one operand is **NaN** | **-1** | **1** |

The difference between the `l` (*less*) and `g` (*greater*) suffixes appears only when **NaN** is involved. This matters because Java's numeric comparison operators require all `<`, `<=`, `>`, `>=` conditions to be false if either operand is NaN.

For example, a compiler implementing **`a < b`** typically chooses `dcmpg` and then `ifge`: if NaN is encountered, `dcmpg` returns 1 and §ifge§ jumps to the false branch. For **`a > b`**, it can use `dcmpl` and then `ifle` so that NaN goes to the false branch. A compiler may choose a different sequence, but it must preserve semantics.

**Two differently signed zeros:** `+0.0 == -0.0` is true in numeric comparison; the `fcmp*`/`dcmp*` opcodes treat the two forms of zero as equal. However, `Double.compare(-0.0, +0.0) < 0` is true, because the library method applies a **total ordering** that differs from the semantics of the operators/JVM compare instructions. Do not use `Double.compare` to directly predict the result of `dcmpl` or `dcmpg` when NaN or signed zero is present.

### Why is there no opcode that returns a "boolean on the stack"?

At the JVM level, conditional results are usually represented via control-flow paths and int constants. A Java §boolean§ in source expressions can correspond to an int value 0/1 in many bytecode operations. This is why you should not infer "§if_icmplt§ pushes true/false" — this instruction only **branches**.

## 7. Numeric Type Conversion Group: `x2y` Instructions

The opcode name `i2l` means **convert int to long**, `d2i` means **double to int**. The conversion instruction set is designed for JVM types, so it differs from how full casts are written in Java code.

### Widening primitive conversions

| Opcode | Conversion | Notes |
| --- | --- | --- |
| `i2l` | int → long | Preserves every int exactly. |
| `i2f` | int → float | May round and lose precision because there are only 24 significand bits. |
| `i2d` | int → double | Preserves every 32-bit int exactly. |
| `l2f` | long → float | May round many low-order bits. |
| `l2d` | long → double | May lose precision for large longs. |
| `f2d` | float → double | Preserves the exact finite numeric value of float in double (does not make the original decimal "exact"). |

There are no `b2i`, `s2i`, `c2i` opcodes in the JVM for converting `byte`/`short`/`char` to int: those types are generally represented by the JVM as int in related operations.

**Widening does not mean lossless in every case.** For example, a `long` larger than 2^53 can lose low-order bits when converted to `double`; an `int` is not necessarily represented exactly when converted to `float`.

### Narrowing conversions

| Opcode | Conversion | Key points to remember |
| --- | --- | --- |
| `i2b` | int → byte | Keeps the lowest 8 bits and sign-extends to int on the stack. |
| `i2c` | int → char | Keeps the lowest 16 bits, unsigned, and represents as int on the stack. |
| `i2s` | int → short | Keeps the lowest 16 bits and sign-extends to int on the stack. |
| `l2i` | long → int | Keeps the lowest 32 bits; sign may change. |
| `f2i`, `f2l` | float → int/long | Truncates fractional part toward 0; handles NaN/infinity by special rules. |
| `d2i`, `d2l` | double → int/long | Similar for double; may round/truncate information. |
| `d2f` | double → float | Rounds to binary32; may become infinity, zero, or subnormal. |

Integer/numeric cast examples:

~~~java
System.out.println((byte) 130);  // -126
System.out.println((short) 65535); // -1
System.out.println((char) 65535 == '\uFFFF'); // true
System.out.println((int) 3.9); // 3
System.out.println((int) -3.9); // -3
~~~

With `i2b`, 130 in binary keeps the lowest 8 bits `10000010`, interpreted as signed -126. With `i2c`, 16 bits are treated as unsigned in the `char` code unit range 0..65535. There is no automatic "overflow exception" when casting primitives under these rules.

### Float/double to int/long: NaN, infinity, and bounds

For opcodes such as `d2i`:

1. If the input is **NaN**, the result is `0`.
2. If it is a finite number in range after truncating the fractional part toward 0, the result is that integer.
3. If the value exceeds the positive int range or is `+Infinity`, the result is `Integer.MAX_VALUE`.
4. If it is below the negative int range or is `-Infinity`, the result is `Integer.MIN_VALUE`.

For `d2l`/`f2l`, the same applies to the `long` range and `Long.MAX_VALUE/MIN_VALUE`.

~~~java
System.out.println((int) Double.NaN);               // 0
System.out.println((int) Double.POSITIVE_INFINITY); // 2147483647
System.out.println((int) Double.NEGATIVE_INFINITY); // -2147483648
System.out.println((int) 3.99);                     // 3
System.out.println((int) -3.99);                    // -3
~~~

Do not assume that casting a floating-point number to an integer will **throw an exception** when the input is NaN or infinity. If business logic needs to reject these values, check `Double.isFinite(x)` or `Float.isFinite(x)` before casting, and explicitly validate the valid range.

### Distinguishing primitive casts and reference casts

- `i2d`, `d2i`, and the like: **primitive value conversion**.
- `checkcast`: **reference type check/cast** and can throw `ClassCastException`.
- `instanceof`: checks the runtime type relationship of a reference.

All three are called "cast" in casual phrasing, but they use different bytecode mechanisms. `int` to `Integer` can also compile to **boxing** via a library call such as `Integer.valueOf`, not `checkcast`.

## 8. Runnable Java 17+ Program: Comparing Each Group

Create the file **`BytecodeOpsDemo.java`** matching the `public class` name:

~~~java
public class BytecodeOpsDemo {
    static int add(int a, int b) {
        return a + b;
    }

    static int bits(int a, int b) {
        return (a & b) ^ (a << 1);
    }

    static int unsignedShift(int value) {
        return value >>> 1;
    }

    static boolean lessThanLong(long a, long b) {
        return a < b;
    }

    static boolean lessThanDouble(double a, double b) {
        return a < b;
    }

    static int toInt(double value) {
        return (int) value;
    }

    static byte toByte(int value) {
        return (byte) value;
    }

    public static void main(String[] args) {
        System.out.println("add=" + add(7, 5));
        System.out.println("overflow=" + (Integer.MAX_VALUE + 1));
        System.out.println("remainder=" + (-7 % 3));
        System.out.println("and=" + (10 & 12));
        System.out.println("or=" + (10 | 12));
        System.out.println("xor=" + (10 ^ 12));
        System.out.println("not=" + (~10));
        System.out.println("bitMethod=" + bits(10, 12));
        System.out.println("signedShift=" + (-8 >> 1));
        System.out.println("unsignedShift=" + unsignedShift(-8));
        System.out.println("longLess=" + lessThanLong(4L, 9L));
        System.out.println("nanLess=" + lessThanDouble(Double.NaN, 1.0));
        System.out.println("cast=" + toInt(3.9));
        System.out.println("nanCast=" + toInt(Double.NaN));
        System.out.println("infinityCast=" + toInt(Double.POSITIVE_INFINITY));
        System.out.println("byteCast=" + toByte(130));
        System.out.println("floatDivide=" + (1.0 / 0.0));
    }
}
~~~

Compile and run with **JDK 17+**:

~~~bash
javac --release 17 BytecodeOpsDemo.java
java BytecodeOpsDemo
~~~

**Exact stdout:**

~~~text
add=12
overflow=-2147483648
remainder=-1
and=8
or=14
xor=6
not=-11
bitMethod=28
signedShift=-4
unsignedShift=2147483644
longLess=true
nanLess=false
cast=3
nanCast=0
infinityCast=2147483647
byteCast=-126
floatDivide=Infinity
~~~

Double-check `bitMethod=28`: `(10 & 12) = 8`, and `(10 << 1) = 20`; `8 ^ 20 = 28`. Do not arithmetically add these two results; `^` is bitwise XOR.

### Inspecting bytecode with javap

~~~bash
javap -c -p BytecodeOpsDemo
~~~

You can look for the signatures in the separated methods:

| Method | Expected primary instructions when compiled with standard `javac` |
| --- | --- |
| `add` | `iload_0`, `iload_1`, `iadd`, `ireturn` |
| `bits` | `iand`, `ishl`, `ixor` |
| `unsignedShift` | `iushr` |
| `lessThanLong` | `lcmp` and an `if...` opcode |
| `lessThanDouble` | `dcmpg` and a branch opcode to ensure NaN yields false |
| `toInt` | `d2i`, `ireturn` |
| `toByte` | `i2b`, `ireturn` |

These are **expectations for a typical Java compiler**, not a mandatory exact dump with fixed offsets or constant pool indices. Compilers are allowed to generate different bytecode sequences as long as they preserve Java semantics. In `main`, string concatenation when printing may involve §invokedynamic§ or library calls; do not confuse those string-building instructions with the arithmetic opcodes under study.

### Illustrating the stack process for `add(7, 5)`

~~~text
Local variables: [0]=7, [1]=5
Initial stack: []

iload_0  → Stack [7]
iload_1  → Stack [7, 5]
iadd     → Stack [12]
ireturn  → Return 12 to caller
~~~

For `lessThanLong(4L, 9L)`, `lcmp` can push the int result `-1` and then a conditional branch turns it into boolean true. For `lessThanDouble(Double.NaN, 1.0)`, `dcmpg` can push `1`, so the `<` condition is treated as false as required by Java.

## 9. Important Differences Between Java Operators and JVM Opcodes

### The compiler can perform constant folding

For pure constant expressions such as `2 + 3` or `10 & 12`, the compiler can precompute the value and emit a constant-loading instruction instead of generating `iadd` or `iand`. To **observe specific opcodes**, use methods that take dynamic parameters like `add(int,int)` and `bits(int,int)` in the example.

### String concatenation is not numeric addition

In source code, `"total=" + value` is **string concatenation**, not `iadd` or `dadd`. With JDK 17, `javac` typically uses the `invokedynamic` mechanism for string concatenation. Do not look for an opcode like `sadd`: the JVM has no dedicated primitive string-addition instruction.

### Numeric promotion before executing operations

Syntax:

~~~java
byte a = 100;
byte b = 20;
// byte result = a + b; // Does not compile: a + b has type int.
int result = a + b;
~~~

Even though both operands are §byte§, Java performs **binary numeric promotion** and the expression has type §int§. The JVM typically uses `iadd`. To store back into a §byte§, an explicit cast or compound assignment per Java semantics is required:

~~~java
byte resultByte = (byte) (a + b); // 120
~~~

This is an illustrative method snippet; the cast can also emit `i2b`. Using `byte`/`short`/`char` does not cause bytecode to switch to a separate 8/16-bit arithmetic instruction set.

### Library methods are not dedicated opcodes

`Math.abs`, `Math.addExact`, `Integer.compareUnsigned`, `BigDecimal.add`, `Double.compare` are not instruction names in the JVMS. The compiler may emit method calls; the JVM/JIT may optimize or use intrinsics in a specific runtime, but **the bytecode format of the calling method** still adheres to the JVM instruction set rather than automatically having an opcode with the API's name.

### Overflow of `int` differs from `float` and `double`

- With `iadd`, the result is a fixed bit-width value modulo 2^32 (signed interpretation), without automatically producing Infinity or NaN.
- With `fadd`/`dadd`, the result can be rounded, overflow to infinity, or carry NaN.
- With `idiv`, a divisor of 0 throws `ArithmeticException`; with `ddiv`, `1.0 / 0.0` is Infinity, and `0.0 / 0.0` is NaN.

You cannot apply a single rule "the `/` operation always throws on division by 0" to both families of types.

## 10. Common Pitfalls and How to Investigate

| Symptom | Cause | Investigation / Resolution |
| --- | --- | --- |
| Adding large `int` values turns negative | 32-bit overflow without exception | Use `Math.addExact` when detection is needed; `long`/`BigInteger` when a larger range is needed. |
| `Integer.MIN_VALUE / -1` does not become positive | Mathematical quotient is not representable in int | Check boundary cases explicitly, choose a larger type if needed. |
| §byte + byte§ cannot be assigned directly back to §byte§ | Binary numeric promotion to int | Use an int variable or a range-checked cast. |
| `-7 % 3` produces `-1` | Java remainder takes the sign of the dividend | Use `Math.floorMod` if modulo under another convention is needed. |
| `>>>` on negative numbers gives a large positive result | High bits are filled with 0, sign bit is not preserved | Distinguish `ishr` from `iushr` and 32/64-bit widths. |
| `1 << 32` produces 1 | int shift count uses only the lowest 5 bits | Mask the shift distance and validate expected bit count. |
| Comparing NaN with `<` or `>` is always false | NaN is unordered; compiler uses `fcmpg/fcmpl` or `dcmpg/dcmpl` per semantics | Check `Double.isNaN`/`Double.isFinite` when needed. |
| Casting `Double.NaN` to `int` produces 0 | Narrowing floating-point → integer rule | Validate data before casting. |
| Casting infinity to `int` throws no exception | Narrowing saturates at the int/long range boundaries | Check finiteness and value range. |
| No `iadd` seen in `2 + 3` | Compiler performed constant folding | Observe methods receiving dynamic parameters. |
| `javap -c` does not look like "one opcode per operator" | Stack loads/stores, branches, calls, and optimizations | Read the entire stack flow, do not match symbols mechanically. |
| Bytecode with type/stack errors fails to run | Does not satisfy verifier conditions | Check `VerifyError`, class format, and stack maps; do not emit invalid bytecode yourself. |

### How to read §javap§ systematically

1. Identify the method signature (parameters, return type), noting that a `long`/`double` parameter uses two slots in the local variable array per JVM rules.
2. Track local variables loaded via `iload`, `lload`, `fload`, `dload`.
3. Trace the operand stack after each instruction. For binary instructions, the operand at the top is the second value.
4. Identify computation, conversion, comparison, and branch opcodes; separate them from `invoke*` calls.
5. Follow the paths on true/false branches; ensure the stack shape is valid at merge points.
6. For additional details, use `javap -v -p ClassName` to inspect the constant pool, descriptors, StackMapTable, and other attributes.

**Do not try to reconstruct the entire original Java source from just a few instructions**: many ways of writing source code can compile to equivalent bytecode, especially with constant folding or compiler optimizations.

## 11. Self-Check Questions

**Question 1.** Where does `iadd` get its two numbers from? Is `iinc` the same?

**Answer:** `iadd` pops two int values from the operand stack and pushes their sum. `iinc` increments an int local variable by an encoded constant, without popping two operands from the stack.

**Question 2.** How do `idiv` and `ddiv` differ when the divisor is 0?

**Answer:** `idiv` throws `ArithmeticException`, whereas `ddiv` follows IEEE 754: depending on the numerator and sign, it can produce infinity or NaN.

**Question 3.** When both operands are `byte`, why is `iadd` commonly seen?

**Answer:** Java binary numeric promotion turns the addition expression into int; the JVM has no separate `badd` opcode.

**Question 4.** With `int x = -8`, how do `x >> 1` and `x >>> 1` differ?

**Answer:** `>>` preserves the sign, producing -4; `>>>` shifts 0 into the high bits, producing 2147483644.

**Question 5.** What is `1 << 32` equal to and why?

**Answer:** Equal to 1, because the shift count for int uses only the lowest 5 bits: 32 becomes a shift distance of 0.

**Question 6.** What does `lcmp` return when value1 is less than value2? Does it directly return a `boolean`?

**Answer:** It pushes the integer -1 onto the stack, not directly a Java boolean. The compiler uses additional branches to build a boolean result if needed.

**Question 7.** Why do `dcmpg` and `dcmpl` differ when encountering NaN?

**Answer:** NaN is unordered; `dcmpg` chooses the int result +1 and `dcmpl` chooses -1. Having both variants allows the compiler to generate branches with the exact semantics of all Java comparisons.

**Question 8.** What do `(int) Double.NaN`, `(int) Double.POSITIVE_INFINITY`, and `(int) -3.9` produce?

**Answer:** 0, 2147483647, and -3, respectively. The NaN and Infinity cases follow special narrowing rules, and finite numbers have their fractional part truncated toward 0.

**Question 9.** Does `i2d` lose precision for any `int`? What about `l2d`?

**Answer:** `i2d` preserves every 32-bit int value exactly; `l2d` can lose low-order bits of a very large long because double has only 53 effective significand bits.

**Question 10.** Why might Java code `2 + 3` have no `iadd` in the disassembly?

**Answer:** The compiler can compute the constant at compile time as 5 and emit an instruction to load 5; it is not that the JVM skipped addition incorrectly.

## 12. Cheat Sheet

~~~text
Java Operator                    Typical JVM Opcode
--------------------------------------------------------
int a+b, a-b, a*b                iadd / isub / imul
long a/b, a%b                    ldiv / lrem
float/double arithmetic          fadd..frem / dadd..drem
int/long bitwise &, |, ^         iand/ior/ixor, land/lor/lxor
int/long <<, >>, >>>             ishl/ishr/iushr, lshl/lshr/lushr
int local++                      may use iinc
int a < b                        typically if_icmplt
long a < b                       lcmp then branch
float/double a < b               fcmpg/dcmpg then branch
(int) someDouble                 d2i
(byte) someInt                   i2b

Operand stack: ... value1, value2 → ... result
Branch instruction: pops operands, changes control flow, does not push boolean
~~~

**Key takeaway:** learn bytecode by **operand types, stack rules, and instruction semantics**, not by assuming "each Java operator equals exactly one instruction." For integers, watch bit width, overflow, and bit shifts; for floating-point, watch NaN/infinity and rounding; for comparisons, distinguish result-producing opcodes from branches; for type conversions, identify where data is lost.

## References

- [JVMS Java SE 21 — §2.11 Instruction Set Summary](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-2.html#jvms-2.11).
- [JVMS Java SE 21 — §6.5 Instructions](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-6.html#jvms-6.5).
- [JLS Java SE 21 — §5 Conversions and Contexts](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html).
- [JLS Java SE 21 — §15 Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html).
- [JDK 21 — javap documentation](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javap.html).
- [JEP 306 — Restore Always-Strict Floating-Point Semantics](https://openjdk.org/jeps/306).
