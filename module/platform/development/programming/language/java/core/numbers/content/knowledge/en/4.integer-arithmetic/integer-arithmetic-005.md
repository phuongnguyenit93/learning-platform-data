# Unary Operations and Prefix/Postfix `++`, `--` in Java

A **unary operator** operates on a single operand, such as `-x` or `~mask`. The **increment `++`** and **decrement `--`** operators have two forms: placed **before** the variable (`++i`, `--i`) or **after** the variable (`i++`, `i--`). The most important point is that both forms modify the variable, but **the value returned by the expression is different**.

Within integer arithmetic, you must understand result types, value ranges, overflow, evaluation order, and what makes an operand modifiable. This lesson uses Java 17+ and distinguishes standalone runnable examples from lines used solely to illustrate compile errors.

## 1. Relevant Unary Operators

| Syntax | Name | Meaning | Operand types |
| --- | --- | --- | --- |
| `+x` | Unary plus | Takes the numeric value after *unary numeric promotion*; does not change sign | Integer or floating-point types |
| `-x` | Unary minus | Negates the numeric value after *unary numeric promotion* | Integer or floating-point types |
| `~x` | Bitwise complement | Inverts every bit of the promoted value | Integer types only |
| `!flag` | Logical negation | `true` becomes `false` and vice versa | `boolean` or `Boolean` (unboxing) |
| `++x` / `x++` | Prefix / postfix increment | Modifies the variable by adding 1; differs in returned value | Variable of integer/floating-point type or corresponding numeric wrapper |
| `--x` / `x--` | Prefix / postfix decrement | Modifies the variable by subtracting 1; differs in returned value | Variable of integer/floating-point type or corresponding numeric wrapper |

`+` and `-` also exist in **binary form**: `a + b` adds two numbers, `a - b` subtracts two numbers. Java determines which form is used from the expression structure:

```java
int a = 5;
int positive = +a; // 5: unary plus
int negative = -a; // -5: unary minus
int sum = a + 2;   // 7: binary addition
int difference = a - 2; // 3: binary subtraction
```

Unary `+` is **not a string concatenation operator**: `+"abc"` is invalid. The logical operator `!` applies only to booleans; there is no C/C++-style rule treating `0` as `false`:

```java
boolean enabled = true;
boolean disabled = !enabled; // false
// boolean invalid = !0;      // error: int is not boolean
// int invalidBits = ~true;    // error: ~ does not accept boolean
```

## 2. Unary Numeric Promotion

For `+x`, `-x`, and `~x`, Java performs *unary numeric promotion* before producing a result. This is an easily overlooked distinction when the operand is `byte`, `short`, or `char`.

| Operand type | Result type of `+x`, `-x` | Result type of `~x` |
| --- | --- | --- |
| `byte`, `short`, `char` | `int` | `int` |
| `int` | `int` | `int` |
| `long` | `long` | `long` |
| `float` | `float` | Invalid |
| `double` | `double` | Invalid |

Numeric wrappers such as `Byte` can be *unboxed* and then promoted; if the wrapper value is `null`, unboxing throws a `NullPointerException`.

For example:

```java
byte b = 5;
int x = +b;  // +b has type int
int y = -b;  // -b has type int
int z = ~b;  // ~b has type int, value -6

// byte wrong = -b; // error: int result cannot be assigned directly to byte
byte converted = (byte) -b; // -5, explicit cast
```

Key distinction: **`b++` still updates the variable `b` as `byte`**, even though `+b` and `-b` produce an `int` result. The special rules for `++`/`--` are explained below.

### Bitwise Complement `~` and Two's Complement Representation

For `int`, `~` inverts all 32 bits; for `long`, it inverts all 64 bits. We have the mathematical identity in two's complement representation:

```text
~x == -x - 1
```

For example:

```java
int mask = 0b1010; // 10
int oppositeBits = ~mask; // -11
```

`~10` does not produce `0b0101` (`5`), because `int` has **32 bits**, including the leading zero bits to the left of the lowest four bits. Inverting all 32 bits yields the negative value `-11`. To **invert only the lowest four bits**, apply a mask:

```java
int lowFourFlipped = (~0b1010) & 0b1111; // 0b0101 = 5
```

Do not confuse `~` with `!`: `~` operates on integer bits, whereas `!` operates on logical boolean values.

## 3. `++` and `--`: Side Effects and Expression Values

Each increment/decrement operator both **reads the old value** and **writes the new value** back into the variable. Regarding the value used in a larger expression:

- **Prefix `++i`:** increments variable `i` first; the expression value is the **new value**.
- **Postfix `i++`:** increments variable `i`; the expression value is the **old value**.
- **Prefix `--i`:** decrements variable first; the expression value is the **new value**.
- **Postfix `i--`:** decrements variable; the expression value is the **old value**.

Assume initially `i = 5`. Each row in the following table is an **independent run** starting from `5`:

| Expression | Expression value | Value of `i` after expression |
| --- | ---: | ---: |
| `++i` | 6 | 6 |
| `i++` | 5 | 6 |
| `--i` | 4 | 4 |
| `i--` | 5 | 4 |

Postfix example:

```java
int i = 5;
int old = i++; // old = 5; i = 6
```

Prefix example:

```java
int i = 5;
int current = ++i; // current = 6; i = 6
```

When **used as a standalone statement**, both `i++` and `++i` increment `i` by one. The difference matters when the expression's value is used, such as `int a = i++;` or `System.out.println(++i);`.

Similarly, `i--` and `--i` both decrement by one when standing alone, while still differing in returning the old vs. new value.

### Reading Output from Top to Bottom

A complete Java file is provided in section 9. Given these two statements:

```java
int n = 3;
System.out.println(n++); // prints 3; then n becomes 4
System.out.println(++n); // n becomes 5; prints 5
```

The output in exact order is `3` then `5`. Do not interpret postfix as "incrementing lazily at some arbitrary later time"; the write to the variable happens during evaluation of that expression. Only the **return value of the postfix expression** is the pre-increment/decrement value.

## 4. Types of `++`/`--` and Why `byte` Can Still Be Incremented

For `++`/`--`, the operand must be a **variable** of numeric type. Java reads the variable's value, performs the increment/decrement under numeric arithmetic rules, and then **converts the result back to the variable's type** before storing it. The value of the increment/decrement expression also has the variable's type.

Therefore:

```java
byte count = 127;
count++;  // valid: byte overflows from 127 to -128
byte result = count++; // valid: postfix result also has type byte
```

Contrast with:

```java
byte count = 5;
// byte invalid = count + 1; // error: count + 1 has type int
// byte invalid2 = +count;   // error: +count has type int
count++;                   // valid: ++ has a special conversion rule
```

The statement `count++` is **not type-equivalent** to writing an assignment `count = count + 1;`, because the expression `count + 1` is `int`. `count += 1;` is also valid in many cases, but it is a compound assignment operator with its own rules whose casting implications must be understood.

A point to watch with wrappers:

```java
Integer boxed = 3;
boxed++;  // unbox Integer -> int, increment, rebox to Integer
// Integer missing = null;
// missing++; // compiles, but throws NullPointerException at runtime
```

The `Integer` wrapper is an object reference; this operation **reassigns the reference variable to a newly boxed value**, rather than mutating an immutable `Integer` object's internals.

`char` is also a 16-bit unsigned integer type and can be incremented:

```java
char letter = 'A';
letter++;                // 'B'
int code = letter;       // 66
```

Do not use `++` on `boolean`, `String`, or `BigInteger`. For `BigInteger`, call `add(BigInteger.ONE)` to produce a new value.

## 5. Which Variables Are Valid Operands for `++` and `--`?

Increment/decrement operators must act on an **assignable variable** of numeric type. For example:

```java
int local = 1;
local++;                 // local variable
int[] items = {4};
items[0]++;              // array element
Counter counter = new Counter();
counter.value++;         // assignable field
```

`Counter` above is an illustrative class, for example:

```java
class Counter {
    int value;
}
```

The cases below are invalid if uncommented:

```java
// 5++;                 // literal is not a variable
// (2 + 3)++;           // addition result is not a variable
// getNumber()++;       // method return value is not a variable
final int limit = 10;
// limit++;             // final variable cannot be reassigned
```

A local variable must be **definitely assigned before incrementing/decrementing**, because `++` and `--` always need to read the old value:

```java
void example() {
    int number;
    // number++; // compile error: number is not initialized
    number = 0;
    number++;    // valid
}
```

The `example()` snippet is only an illustrative method inside a class; without a `main` method, it is not standalone runnable.

## 6. Evaluation Order in Expressions with Multiple Increments

Java evaluates operands in a deterministic order from **left to right**. Thus Java defines a deterministic result for expressions like:

```java
int i = 1;
int sum = i++ + ++i;
```

Trace:

1. Evaluate the left operand `i++`: yields expression value `1`, then updates `i = 2`.
2. Evaluate the right operand `++i`: updates `i = 3`, then yields expression value `3`.
3. Add `1 + 3` to get `4`; after the statement, `i = 3`.

Thus `sum == 4` and `i == 3`. This is well-defined Java behavior, but code like this is **hard to read and error-prone to maintain**. In application code, prefer splitting it up:

```java
int i = 1;
int left = i;
i++;
i++;
int right = i;
int sum = left + right; // 4; i = 3
```

Always read `i++` and `++i` by their old/new value semantics; do not rely on vague mnemonics like "before means before, after means after" while forgetting to track when the variable is updated.

### Trap: `i = i++`

```java
int i = 1;
i = i++;
```

`i++` produces the expression value **`1`**, while updating the variable to `2`. Then the outer assignment writes **`1`** back into `i`. The final result remains **`i == 1`**.

This is a classic example showing that postfix has two distinct effects: the *side effect* on the variable and the *expression value used*. If you only want to increment, write `i++;` by itself. Never combine it with assigning back to the same variable.

### Evaluation Order with Array Elements

```java
int[] values = {3};
int index = 0;
int previous = values[index++]++;
```

Java evaluates the array and index first, selecting `values[0]`, while `index` increments to `1`. The postfix operator on the element returns the old value `3` and writes `4` into `values[0]`. Result: `previous == 3`, `values[0] == 4`, and `index == 1`.

When you only need to increment an element, `values[index]++;` is usually clearer; incrementing both `index` and the element in the same expression can cause confusion.

## 7. Overflow and Boundary Values

`++` and `--` do not automatically throw exceptions when primitive integers go out of range. Java integers have fixed width; operations can **overflow**.

```java
int max = Integer.MAX_VALUE; // 2147483647
max++;                      // -2147483648

int min = Integer.MIN_VALUE; // -2147483648
min--;                      // 2147483647

byte b = Byte.MAX_VALUE;     // 127
b++;                        // -128
```

Also pay attention to unary minus at boundaries:

```java
int min = Integer.MIN_VALUE;
int negated = -min; // still -2147483648 because int cannot represent +2147483648
long exact = -(long) min; // 2147483648: widen first, then negate
```

If the problem requires detecting overflow rather than accepting wraparound, use `Math.addExact(x, 1)`, `Math.subtractExact(x, 1)`, or `Math.negateExact(x)` where appropriate for `int`/`long`. For instance, `Math.incrementExact(Integer.MAX_VALUE)` throws `ArithmeticException` instead of returning a negative number. These methods are **not called implicitly** by `++`/`--`.

For `float`/`double` floating-point types, `++`/`--` are still valid; however, due to finite precision, adding `1` may **leave the value unchanged** at sufficiently large magnitudes. Avoid binary floating-point for currency; that is a numeric precision issue, not specific to `++`.

## 8. Common Mistakes and Fixes

| Misconception / bug | Correct explanation |
| --- | --- |
| "`i++` and `++i` always return the same value" | Both increment the variable, but postfix returns the old value; prefix returns the new value |
| "`System.out.println(i++)` will print the new value" | `println` receives the old value of the postfix expression |
| "`-b` has type `byte` if `b` is byte" | Unary numeric promotion makes the result type `int` |
| "`~0b1010` equals `0b0101`" | `~` flips all 32 bits of `int`, giving `-11`; to flip only 4 bits, apply a mask |
| "`byte b = 127; b++;` is a compile error" | Valid; incrementing wraps around to `-128` |
| "`i = i++;` increments `i`" | The final assignment overwrites the increment, leaving `i` with its old value |
| "You can write `5++` or `getNumber()++`" | The operand must be an assignable variable, not a literal or method return value |
| "`final int n = 1; n++;` is valid" | A `final` variable cannot be reassigned |
| "`Integer n = null; n++;` initializes `n` to 1" | Unboxing `null` throws `NullPointerException` |
| "`i++` is always thread-safe across multiple threads" | Read, add, and write are separate steps; `++` does not guarantee atomic updates across threads |

### Note on Multithreading

`counter++` on a shared variable is **not an atomic operation**. Two threads can read the same value and overwrite each other's updates, causing lost increments. If a shared counter is needed, one option is `AtomicInteger`:

```java
java.util.concurrent.atomic.AtomicInteger counter =
        new java.util.concurrent.atomic.AtomicInteger(0);
int old = counter.getAndIncrement(); // returns old value
int current = counter.incrementAndGet(); // returns new value
```

This is a small example contrasting postfix/prefix semantics; thread synchronization design is a separate topic.

## 9. Standalone Runnable Program on Java 17+

Create a file **`UnaryOperatorsDemo.java`**:

```java
public class UnaryOperatorsDemo {
    public static void main(String[] args) {
        int i = 5;
        System.out.println("postIncValue=" + i++);
        System.out.println("afterPostInc=" + i);
        System.out.println("preIncValue=" + ++i);
        System.out.println("afterPreInc=" + i);
        System.out.println("postDecValue=" + i--);
        System.out.println("afterPostDec=" + i);
        System.out.println("preDecValue=" + --i);
        System.out.println("afterPreDec=" + i);

        byte b = 127;
        b++;
        System.out.println("byteWrap=" + b);

        int mask = 0b1010;
        System.out.println("unaryPlus=" + (+mask));
        System.out.println("unaryMinus=" + (-mask));
        System.out.println("bitwiseNot=" + (~mask));
        System.out.println("lowFourNot=" + ((~mask) & 0b1111));
        System.out.println("logicalNot=" + (!true));

        int j = 1;
        int sum = j++ + ++j;
        System.out.println("combinedSum=" + sum);
        System.out.println("combinedJ=" + j);

        int assigned = 1;
        assigned = assigned++;
        System.out.println("assignedPost=" + assigned);

        int[] values = {3};
        int index = 0;
        int previous = values[index++]++;
        System.out.println("arrayOld=" + previous);
        System.out.println("arrayCurrent=" + values[0]);
        System.out.println("arrayIndex=" + index);

        int min = Integer.MIN_VALUE;
        System.out.println("negMinInt=" + (-min));
        System.out.println("negMinLong=" + (-(long) min));
    }
}
```

Compile and run from the directory containing the file:

```bash
javac UnaryOperatorsDemo.java
java UnaryOperatorsDemo
```

Exact output:

```text
postIncValue=5
afterPostInc=6
preIncValue=7
afterPreInc=7
postDecValue=7
afterPostDec=6
preDecValue=5
afterPreDec=5
byteWrap=-128
unaryPlus=10
unaryMinus=-10
bitwiseNot=-11
lowFourNot=5
logicalNot=false
combinedSum=4
combinedJ=3
assignedPost=1
arrayOld=3
arrayCurrent=4
arrayIndex=1
negMinInt=-2147483648
negMinLong=2147483648
```

Read each line by asking two questions: **what did the variable change to?** and **what expression value was passed to `println`?** For example, `postIncValue=5` followed by `afterPostInc=6` clearly proves that postfix returns the old value while already updating the variable.

## 10. Step-by-Step Process for Solving `++`/`--` Expressions

When analyzing an expression, follow this order:

1. **Check the operand:** `++`/`--` requires an assignable numeric variable, definitely assigned before reading, and not an unmodifiable `final` variable.
2. **Identify operator position:** prefix returns the value after modification; postfix returns the value before modification.
3. **Track the side effect:** update the variable's value by exactly one increment/decrement step (subject to overflow or floating-point rules).
4. **Track evaluation order:** Java evaluates operands from left to right; if a variable appears multiple times, record both the returned value and the variable's value at each step.
5. **Check types:** `+`, `-`, `~` apply numeric promotion; `++`, `--` store the result back into the variable's type and can narrow/overflow.
6. **Prefer clear code:** in production code, avoid mixing multiple increments/decrements or combining assignment with postfix on the same variable. Split into separate statements when logic does not need complex expressions.

**Key Takeaway:** `++i` returns the **new** value and `i++` returns the **old** value, but both increment the variable. Unary `+`/`-` and `~` follow numeric promotion rules; clearly understanding types, evaluation order, and boundary values helps avoid hard-to-spot bugs.