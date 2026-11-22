# The int type used for many operations on byte, short, char, and boolean

## 1. Lesson Objectives

Java has the primitive types **byte**, **short**, **char**, **boolean**, and **int**. They differ in valid values, type rules in source code, and method signatures. However, in the instruction set of the Java Virtual Machine (JVM), most operations on the first four types are performed through the **int computational type**.

After studying this, you can:

- Explain why bytecode uses instructions such as **iload**, **istore**, **iadd**, **ifeq**, and **ireturn** for values originating from **byte**, **short**, **char**, and sometimes **boolean**.
- Distinguish between **Java source-level types**, **declared/storage types in the class file**, and **computational types on the operand stack**.
- Distinguish **sign extension** of **byte/short** from **zero extension** of **char/boolean**.
- Understand numeric promotion, narrowing casts via **i2b/i2s/i2c**, and why an expression adding two **byte** variables produces an **int** result.
- Explain why using **int** to represent boolean values in the JVM does not allow addition or casting between **boolean** and **int** in Java.
- Inspect bytecode with **javap** and accurately predict the output of Java 17+ programs.

This lesson discusses the model defined by the **JVM specification**; do not infer that the JVM is required to use four bytes of physical memory for each boolean/byte/short/char variable at runtime.

## 2. Two Type Layers That Must Be Distinguished

**Layer 1 — Java language (source-level types):**

| Type | Value range | Characteristics |
| --- | --- | --- |
| **byte** | -128 to 127 | 8-bit signed integer |
| **short** | -32768 to 32767 | 16-bit signed integer |
| **char** | 0 to 65535 | 16-bit unsigned UTF-16 code unit; a **char** is not necessarily a complete Unicode character |
| **boolean** | **false**, **true** | Logical value, not a numeric type in Java |
| **int** | -2147483648 to 2147483647 | 32-bit signed integer |

At the Java layer, these types are **not arbitrarily interchangeable**. For example, addition between two **byte** variables follows numeric promotion rules; and **boolean** is not converted to a number just because the JVM can use an **int** computational value to process it.

**Layer 2 — JVM instruction set and frame:**

A frame upon method invocation has **local variables** and an **operand stack**. The JVM defines an intentional instruction set: directly supporting the main computational operand groups, rather than creating a separate version of addition or load/store for every source type.

According to the computational type mapping table in the JVM:

| Actual type | Computational type in JVM | Category |
| --- | --- | --- |
| **boolean** | **int** | 1 |
| **byte** | **int** | 1 |
| **short** | **int** | 1 |
| **char** | **int** | 1 |
| **int** | **int** | 1 |
| **long** | **long** | 2 |
| **float** | **float** | 1 |
| **double** | **double** | 2 |

**Category 1** uses one slot unit in the JVM model for instructions that manipulate the operand stack; **long/double** belong to **category 2**. This is a concept of the virtual machine and verifier, **not** a guarantee that every category 1 value always occupies four bytes of RAM in an object or a physical machine register.

Conceptual diagram:

~~~text
Java source:
    byte a, b;
    byte c = (byte) (a + b);
               |
               v
      javac checks Java types
               |
               v
JVM operand stack:
    iload a     -> an int computational value
    iload b     -> an int computational value
    iadd        -> int result
    i2b         -> narrow to byte and sign-extend back to int
    istore c    -> store computational value into local slot
~~~

When code accesses a **field**, array, or passes/receives in a method, the actual type descriptor still exists; it does not mean everything everywhere has been renamed to **int**.

## 3. Why Does the JVM Use int Instructions for Many Types?

Each JVM opcode has a basic instruction code length of one byte. If all addition, subtraction, multiplication, load, store, comparison, return, etc. required separate opcodes for each primitive type, the instruction set would bloat. The JVM uses an instruction set that is not completely symmetric across types, and the compiler inserts conversions where needed to preserve Java semantics.

Examples of common instructions:

| Task | Instruction operating via **int** | Meaning |
| --- | --- | --- |
| Push local variable onto stack | **iload**, **iload_0**...**iload_3** | Read an **int** computational value from slot |
| Write local variable from stack | **istore**, **istore_0**...**istore_3** | Write an **int** computational value into slot |
| Add, subtract, multiply | **iadd**, **isub**, **imul** | **int** arithmetic |
| Divide, remainder | **idiv**, **irem** | **int** arithmetic; division by 0 throws **ArithmeticException** |
| Bitwise AND, OR, XOR | **iand**, **ior**, **ixor** | Operate on **int** computational operands |
| Bit shifts | **ishl**, **ishr**, **iushr** | Shift operations on **int** |
| Branch | **ifeq**, **ifne**, **if_icmpeq**... | Check **int** value, sometimes originating from boolean |
| Return | **ireturn** | Used for methods declared to return **boolean**, **byte**, **short**, **char**, or **int** |
| Narrow to smaller type | **i2b**, **i2s**, **i2c** | Convert **int** result into a value with byte/short/char semantics |

There are no **badd**, **sadd**, **cadd**, or **zadd** instructions to add those types directly. There is no **i2z** to turn a number into a boolean. This is a clear sign of the difference between the JVM computational model and the Java type system.

When viewing bytecode with **javap -c**, the letter **i** in **iadd** or **iload** indicates the **computational type of the instruction**, not proof that the variable declared in source code is necessarily **int**.

## 4. Sign Extension and Zero Extension

When a small value is pushed onto the operand stack, it is typically in computational **int** form, but must preserve the correct sign semantics:

- Signed 8-bit **byte** and signed 16-bit **short**: use **sign extension**, copying the sign bit when expanding to 32 bits.
- Unsigned 16-bit **char**: use **zero extension**, adding 0 bits on the high side.
- **boolean**: logical value represented via computational **int**; the Java compiler uses the encoding **false = 0**, **true = 1** and a zero-extension model. Do not infer that a boolean value is a number in the Java language.

Bit representation examples:

~~~text
byte -1:
    11111111             (8 bits)
          |
          v sign extension
    11111111 11111111 11111111 11111111   -> int -1

short -1:
    11111111 11111111    (16 bits)
          |
          v sign extension
    11111111 11111111 11111111 11111111   -> int -1

char '\uFFFF':
    11111111 11111111    (16 bits)
          |
          v zero extension
    00000000 00000000 11111111 11111111   -> int 65535
~~~

This explains why with the same low bit pattern **FFFF**, **short** is interpreted as **-1** while **char** is interpreted as **65535**. Operations using **int** opcodes are only correct when the input value has been appropriately extended.

### 4.1. Array Load Instructions Clearly Show the Difference

Arrays still retain their element type; the JVM has dedicated element load instructions:

| Array type | Load instruction | Value pushed onto operand stack |
| --- | --- | --- |
| **byte[]** | **baload** | **int** computational type value, sign-extended from byte |
| **short[]** | **saload** | **int** computational type value, sign-extended from short |
| **char[]** | **caload** | **int** computational type value, zero-extended from char |
| **boolean[]** | **baload** | Logical value in computational **int** form; the JVM reuses this instruction for boolean arrays |
| **int[]** | **iaload** | **int** value |

When writing back to an array, the corresponding instructions are **bastore** (byte/boolean), **sastore**, **castore**, and **iastore**. Sharing the **baload/bastore** opcodes does not make **boolean[]** and **byte[]** the same type; Java still checks types at compile time and runtime.

**Do not infer memory layout:** The JVM specification allows implementation details for the representation of boolean; the opcode table does not prove that a boolean field or boolean array element must occupy one physical byte or one physical int on every JVM.

## 5. Numeric Promotion: Why Does byte + byte Yield int?

The rule of the **Java language** is called **binary numeric promotion**: for many arithmetic operators such as **+**, **-**, **\***, **/**, **%**, operands smaller than **int** (byte, short, char) are promoted to at least **int** before performing the operation.

Example:

~~~java
// Illustrative code inside a method:
byte a = 10;
byte b = 20;

int sum = a + b;             // Valid: the expression a + b has type int
byte narrow = (byte) (a + b); // Valid: cast the result to byte
~~~

The line below **does not compile**:

~~~java
byte a = 10;
byte b = 20;
byte invalid = a + b; // Compile-time error: int does not implicitly narrow to byte
~~~

The compiler does not rely on two values happening to be small to accept this assignment, because **a** and **b** are variables and runtime values can exceed the **byte** type limit. The JVM uses **iadd** for the addition; source type checking is performed beforehand by **javac**.

Similarly:

~~~java
short s = 300;
char c = 'A';

int x = s + 1; // 301
int y = c + 1; // 66, because 'A' has UTF-16 code value 65
~~~

**short + short**, **char + char**, and **byte + char** also produce **int** in cases using only these small operands. If **long**, **float**, or **double** is present, promotion rules continue in their respective order; one should not say every arithmetic operation in the JVM becomes **int**.

The unary **+** or **-** operators, **~**, and bit shift operators also have their own promotion rules. For example, **~(byte) 0** produces an **int** result with value **-1**; **(byte) 1 << 8** has type **int** with value **256**.

### 5.1. Controlled Exception: Constant Expressions

Java allows assigning certain **constant expressions of type int** to **byte/short/char** if the value is known at compile time and fits within the target range.

~~~java
byte a = 10 + 20;       // Valid: int constant 30 fits in byte
short s = 1000 + 2000;  // Valid: int constant 3000 fits in short
char c = 65;            // Valid: int constant 65 fits in char
final int code = 66;
char letter = code;     // Valid: code is an int constant variable, value fits in char
~~~

Conversely:

~~~java
byte tooLarge = 120 + 10; // Compile-time error: constant 130 exceeds byte limit
int runtimeValue = 30;
byte cannotAssign = runtimeValue; // Compile-time error: int variable cannot be implicitly narrowed
~~~

This is Java's **constant assignment** rule, which does not contradict the fact that addition produces an expression of type **int**. Do not misunderstand that javac always automatically casts every **int** expression to **byte** when the result looks small.

### 5.2. Compound Assignment and ++ Have Implicit Narrowing

Compare the two snippets:

~~~java
byte b = 127;
// b = b + 1; // Does not compile: b + 1 is int
b += 1;       // Valid: compound assignment includes a narrowing step to byte
~~~

**b += 1** has the same value effect as **b = (byte) (b + 1)** when the left-hand side is a simple variable, and the left-hand side of the compound assignment is evaluated only once. Afterward, **b** has value **-128** because the result **128** is narrowed to an 8-bit signed number.

With the **b++** or **b--** operators, Java also ensures the final result is stored back in the variable's exact type; they do not require the programmer to add an explicit cast.

**Note:** Compound assignment and **++/--** rules are for numeric types; **boolean++**, **boolean += 1**, or **boolean + boolean** are all invalid in Java.

## 6. Narrowing int Results: i2b, i2s, i2c

When computing via **int** and needing to return the result to a smaller type, the compiler can generate conversion instructions:

| Instruction | General behavior | Example **int** input | Result according to target type semantics |
| --- | --- | --- | --- |
| **i2b** | Keep low 8 bits then interpret as signed byte; computational value on stack is sign-extended back to int | 130 | -126 |
| **i2s** | Keep low 16 bits then interpret as signed short; sign-extended back to int | 32768 | -32768 |
| **i2c** | Keep low 16 bits and interpret as unsigned char; zero-extended back to int | -1 | 65535 |

Therefore, **i2b** is not an instruction that turns the operand stack into a "stack containing 8-bit byte slots". The operand stack continues working with computational **int**, but the value has been normalized to the small type.

Example:

~~~text
130 as int
    |
    v i2b
Low 8 bits: 10000010
    |
    v interpret as signed byte then sign-extend
-126 (an int computational value)

-1 as int
    |
    v i2c
Low 16 bits: 11111111 11111111
    |
    v zero-extend
65535 (an int computational value)
~~~

When there is no requirement to narrow from **int** back to a small type, the compiler does not necessarily insert **i2b/i2s/i2c** into every expression. Nor does the presence of a cast in a Java expression mean the bytecode of every compiler must contain a separate conversion instruction; constant expression optimization can happen at compile time.

## 7. Boolean Is an Important Special Case

The JVM does not have a complete dedicated opcode set for **boolean**. In code generated by the Java compiler, **boolean** typically goes through **int** to use load, store, branch check, or return instructions.

Source code example:

~~~java
// Illustrative code inside a method:
boolean ready = true;
boolean active = false;
boolean allowed = ready && active;
~~~

The compiler can use branch instructions on computational **int** such as **ifeq/ifne** to implement **&&** in a short-circuit manner. For **&**, **|**, **^** applied to two **boolean** operands, non-short-circuit logical operations are still valid; instructions like **iand/ior/ixor** can be used when the compiler generates appropriate code.

**Two statements must be distinguished:**

1. **True at the JVM layer:** logical values can be processed using computational **int**; for valid Java code, boolean values are normally encoded as 0 or 1.
2. **False at the Java layer:** boolean is an integer and can be added, multiplied, compared with greater-than, or cast to int. Java does not allow **boolean value = 1**, **int x = true**, **(int) true**, **true + false**, or **true < false**.

**boolean** does not participate in Java language binary numeric promotion. The numeric widening rules for **byte/short/char** and how the JVM represents boolean at runtime are **two different mechanisms**.

In addition:

- **boolean** is allowed to use **!**, **&&**, **||**, **&**, **|**, **^**, **==**, **!=**, and conditions of **if/while**.
- **&&/||** always preserve short-circuit semantics in Java. The JVM's use of **int** branches does not allow skipping this rule.
- A method declared to return **boolean** typically uses **ireturn** like other small types, but its signature still marks it with descriptor **Z**, not **I**.
- The JVM has **boolean[]** as a distinct array type; element access operations share instructions with **byte[]** but are not synonymous with type conversion between the two arrays.
- **boolean** is a logical type with two values according to Java; the behavior of arbitrarily handcrafted bytecode and code violating compiler conventions must not be used as a reason to infer a boolean ↔ int conversion in Java source.

## 8. Runnable Java 17+ Example and Exact Output

Create file **IntComputationalTypeDemo.java**:

~~~java
public class IntComputationalTypeDemo {
    static byte addBytes(byte a, byte b) {
        return (byte) (a + b);
    }

    static short addShorts(short a, short b) {
        return (short) (a + b);
    }

    static char nextChar(char value) {
        return (char) (value + 1);
    }

    static boolean both(boolean left, boolean right) {
        return left && right;
    }

    static int doubleByte(byte value) {
        return value * 2;
    }

    public static void main(String[] args) {
        byte first = 120;
        byte second = 10;

        System.out.println("sumAsInt=" + (first + second));
        System.out.println("sumAsByte=" + addBytes(first, second));

        short maxShort = 32767;
        System.out.println("shortWrap=" + addShorts(maxShort, (short) 1));

        System.out.println("nextChar=" + nextChar('A'));
        System.out.println("charPlusOneAsInt=" + ('A' + 1));

        System.out.println("both=" + both(true, false));
        System.out.println("doubleByte=" + doubleByte((byte) -2));
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac -encoding UTF-8 IntComputationalTypeDemo.java
java IntComputationalTypeDemo
~~~

**Stdout:**

~~~text
sumAsInt=130
sumAsByte=-126
shortWrap=-32768
nextChar=B
charPlusOneAsInt=66
both=false
doubleByte=-4
~~~

Analysis of each case:

1. **first + second** performs **int** addition: 120 + 10 = **130**.
2. **addBytes** also adds via **int**, but casting the result to **byte** keeps the low 8 bits. The value 130 becomes **-126** when interpreted as a signed byte.
3. **32767 + 1** evaluates to **32768** as **int**; casting to **short** yields **-32768**.
4. **'A' + 1** has type **int**, equivalent to 65 + 1 = **66**. In **nextChar**, the cast converts the result to **char**, and **System.out.println** receives a **char** value so it prints the character **B**.
5. **both(true, false)** returns **false** according to Java logical operations; there is no boolean addition.
6. **doubleByte((byte) -2)** widens the byte value **-2** to computational **int**, multiplies by 2 to get **-4**, and returns **int** without needing narrowing.

The example uses deterministic operations, independent of timezone, locale, or filesystem. The **Stdout** above is the output of the program, not the full output of the compiler or bytecode tool.

## 9. Verifying with javap: Explanations Seen in Bytecode

After compiling, run:

~~~bash
javap -c -p IntComputationalTypeDemo
javap -s -p IntComputationalTypeDemo
~~~

The **javap -c** command disassembles instructions, while **javap -s** shows method descriptors. These two commands are for structural observation, not a substitute for running the program to verify output.

### 9.1. Tracing addBytes

With standard **javac**, the bytecode body of the method **addBytes(byte, byte)** has the form:

~~~text
iload_0
iload_1
iadd
i2b
ireturn
~~~

There may be offset prefixes such as **0:**, **1:** or other display details; this mnemonic sequence is the point to observe.

Explanation:

- **iload_0** pushes parameter **a** from local slot 0 onto the stack as a computational **int**.
- **iload_1** does the same for parameter **b**.
- **iadd** consumes two **int** operands and pushes the **int** sum onto the stack.
- **i2b** narrows the sum according to byte rules and puts the sign-extended result back into computational **int** form.
- **ireturn** returns the value for the method declared with type **byte**.

With the sample program, the compiler cannot replace the entire method with a fixed constant because the parameters vary per call. The presence of **iadd** and **i2b** explicitly shows the two phases of computation and narrowing.

### 9.2. Tracing short, char, and boolean

In **addShorts(short, short)**, note the **iadd**, **i2s**, **ireturn** instructions. In **nextChar(char)**, note **iadd**, **i2c**, **ireturn**. In **doubleByte(byte)**, note **imul** and **ireturn**; the return type is **int** so no conversion to **byte** is needed.

In **both(boolean, boolean)**, the compiler can organize an **ifeq** branch or equivalent check to preserve **&&** semantics: if **left** is false, skip evaluating **right** at the language level. With two pure parameter variables as in the example, the output shows no difference in side effects; the short-circuit rule must still be preserved when operands are expressions with side effects.

### 9.3. Signatures Still Preserve Java Types

**javap -s -p** will show the descriptors of the example methods:

| Method | JVM Descriptor | Interpretation |
| --- | --- | --- |
| **addBytes(byte, byte)** | **(BB)B** | Two bytes in, one byte out |
| **addShorts(short, short)** | **(SS)S** | Two shorts in, one short out |
| **nextChar(char)** | **(C)C** | One char in, one char out |
| **both(boolean, boolean)** | **(ZZ)Z** | Two booleans in, one boolean out |
| **doubleByte(byte)** | **(B)I** | One byte in, one int out |

These descriptor symbols are **B** (byte), **S** (short), **C** (char), **Z** (boolean), **I** (int). The existence of **(BB)B** alongside **iadd/ireturn** instructions is clear evidence: **computing via int does not erase the method's type identity**.

When viewing **LocalVariableTable** in a class with debug info, you can also see the declared descriptors of variables. However, this debug table may not exist; **javap -c** does not need debug info to display instructions.

## 10. Array Example: byte/short Sign-Extend, char Zero-Extends

Create a standalone program **ArrayLoadDemo.java**:

~~~java
public class ArrayLoadDemo {
    public static void main(String[] args) {
        byte[] bytes = {(byte) 0xFF};
        short[] shorts = {(short) 0xFFFF};
        char[] chars = {(char) 0xFFFF};
        boolean[] flags = {true};

        int fromByte = bytes[0];
        int fromShort = shorts[0];
        int fromChar = chars[0];

        System.out.println("byte=" + fromByte);
        System.out.println("short=" + fromShort);
        System.out.println("char=" + fromChar);
        System.out.println("boolean=" + flags[0]);
    }
}
~~~

Run commands:

~~~bash
javac -encoding UTF-8 ArrayLoadDemo.java
java ArrayLoadDemo
~~~

**Stdout:**

~~~text
byte=-1
short=-1
char=65535
boolean=true
~~~

The numbers **0xFF** and **0xFFFF** are hexadecimal integer literals. Casts help initialize the target arrays properly:

- **(byte) 0xFF** becomes **-1**; **baload** reads and sign-extends to int.
- **(short) 0xFFFF** becomes **-1**; **saload** reads and sign-extends.
- **(char) 0xFFFF** represents **65535**; **caload** reads and zero-extends.
- **flags[0]** has Java type **boolean**; when printed, Java displays the text **true**, not the number 1, even though bytecode may use computational int to handle logic.

Use **javap -c ArrayLoadDemo** to find the **baload**, **saload**, **caload** instructions. If you see **baload** for a boolean array, remember that this opcode is defined by the JVM to work for both byte arrays and boolean arrays, not proof that the two arrays have the same type in Java.

## 11. Common Mistakes and Layer-Accurate Explanations

### Mistake 1: “Since iadd is used, byte turns completely into int”

Incorrect. The addition expression in Java is promoted to **int**, but the **byte** declaration of parameters, fields, arrays, or return types remains meaningful. The compiler must insert conversions at small-type assignment/return points when needed. The class file stores the corresponding descriptors and the JVM enforces type constraints.

### Mistake 2: “The JVM stores every byte/char/boolean as four bytes”

Cannot be concluded from the instruction set. **int** is the computational type on the operand stack; fields, arrays, object layout, and JIT optimizations are different matters. For example, boolean arrays, object field padding, or CPU registers are decided by the JVM implementation within specification limits. Use profiling tools and specific JVM documentation if concerned about actual memory size.

### Mistake 3: “byte + byte has type byte, because both operands are small”

False for Java expressions using **byte** variables: the addition has type **int**. Only cases of in-range constant assignment or appropriate cast/compound assignment bring the result back to **byte** without a compile error.

### Mistake 4: “boolean is the number 0 or 1 so it can be added”

Invalid in Java source code. Boolean has its own operator system; using computational int to implement conditions is a JVM detail. There is no valid Java conversion **boolean ↔ int** via normal casting.

### Mistake 5: “char is signed like short”

False. **char** is an **unsigned** UTF-16 code unit; **short** is a signed number. With the same low 16 bits **FFFF**, casting to **char** gives 65535 in numeric expressions, while casting to **short** gives -1.

### Mistake 6: “i2b just takes 8 bits and leaves a positive number as-is”

Incorrect when the highest bit of the remaining 8 bits is 1. The signed byte result will be **sign-extended** when returning to computational int, e.g., 130 → -126.

### Mistake 7: “Every operation with small types must always have i2b/i2s/i2c”

Not required. Only when needed to preserve target type semantics or as chosen by the compiler; an operation yielding an **int** result can stop at **iadd**. Constant expressions can even be computed at compile time.

### Mistake 8: “Just reading source code tells you every exact opcode javac generates”

You must inspect the actual class file. The compiler, JDK version, and optimizations can change equivalent bytecode sequences. **javap** is the tool for reading evidence, while the JVM specification explains instruction semantics.

## 12. Prediction and Self-Check Exercises

**Exercise 1.** Why does this snippet have a compile error?

~~~java
byte x = 100;
byte y = 20;
byte z = x + y;
~~~

**Answer:** **x + y** has type **int**, which is not automatically assigned back to **byte** even though a specific run might produce 120. Fix it to **int z = x + y;**, or cast explicitly if intentionally accepting narrowing.

**Exercise 2.** What is the output of this snippet?

~~~java
short s = 32767;
s++;
System.out.println(s);
~~~

**Answer:** **-32768**. The increment uses arithmetic semantics, then stores the result back within the **short** range, wrapping around to the smallest negative value.

**Exercise 3.** What numeric value does the expression **(char) -1** carry when participating in an int operation?

**Answer:** **65535**. **i2c** keeps the low 16 bits and zero-extends. Printing this value with **println(char)** may display a hard-to-observe character; cast to **int** when wanting to see the numeric value.

**Exercise 4.** Can you write **int n = true + false;** if the JVM uses int for boolean?

**Answer:** No. Java source does not treat boolean as a numeric operand and has no boolean addition.

**Exercise 5.** Why does **javap** show **iload** for a method taking **byte** while **javap -s** still reports **(BB)B**?

**Answer:** **iload** indicates the computational type of the instruction inside the frame; **B** in the method descriptor indicates the actual type at the method boundary. The two pieces of information belong to two different layers and are consistent with each other.

**Exercise 6.** Given **byte a = 120; byte b = 10;**, what are the results of **a + b** and **(byte) (a + b)** respectively?

**Answer:** **130** of type **int** and **-126** of type **byte**. Remember that casting does not change the initial addition into a byte addition opcode.

## 13. When Do You Need to Understand This Detail?

This knowledge is useful when:

- **Reading bytecode**: not mistaking **iload/iadd/ireturn** for the original Java variable having type **int**.
- **Investigating overflow results**: distinguishing the **int** addition step from the narrowing step to **byte/short**.
- **Understanding character-processing programs**: not confusing unsigned **char** with signed **short** or with a complete Unicode code point.
- **Analyzing conditions**: understanding why code handling **boolean** has branches on computational int yet must still obey Java logic.
- **Writing bytecode tools, compilers, instrumentation**: having to follow descriptors, stack typing, conversions, and verifier constraints, rather than just looking at the letter **i** in opcodes.
- **Evaluating performance/memory**: avoiding inferring object layout or RAM byte counts from the JVM instruction model; measuring on the specific runtime instead.

### Reference Specification Documents

- Java Virtual Machine Specification, Java SE 17, chapter **2.11.1 — Types and the Java Virtual Machine**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.11.1
- Java Virtual Machine Specification, Java SE 17, chapter **2.11.4 — Type Conversion Instructions**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.11.4
- Java Language Specification, Java SE 17, chapter **5 — Conversions and Contexts**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html
- Java Language Specification, Java SE 17, chapter **15 — Expressions**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html

**Key takeaway:** In the JVM, **byte**, **short**, **char**, and **boolean** commonly use **int** as the **computational type** on the operand stack and in load/store, comparison, and return instructions. **byte/short** sign-extend, **char/boolean** are handled with unsigned representation when pushed onto the stack; converting back to small numeric types uses **i2b/i2s/i2c** as needed. However, **Java still maintains distinct source types**: byte/short/char addition follows numeric promotion to yield **int**, and **boolean never becomes a numeric type** just because of the bytecode implementation.