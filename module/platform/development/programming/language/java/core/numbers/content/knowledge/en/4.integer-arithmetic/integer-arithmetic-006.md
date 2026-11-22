# Precedence, Associativity, and Operand Evaluation Order in Java

> **Java core – numbers · Integer arithmetic**  
> **Goal:** Correctly distinguish *precedence*, *associativity*, and *evaluation order*; read integer arithmetic, bitwise, and conditional expressions; predict results when operands have side effects; know when to add parentheses so programs are unambiguous and safe.

## 1. Three Rules Answering Three Different Questions

When reading a Java expression like:

```java
int result = 2 + 3 * 4;
```

We must distinguish **three concepts**:

| Concept | Question it answers | Example |
| --- | --- | --- |
| **Operator precedence** | Which operator **binds to which operands**, and how is the expression grouped? | `2 + 3 * 4` is grouped as `2 + (3 * 4)`, result `14` |
| **Associativity** | How are operators of the **same precedence level** grouped: left or right? | `20 - 6 - 2` groups as `(20 - 6) - 2`, result `12` |
| **Evaluation order** | In what sequence are **operands/subexpressions executed**, especially if calling methods or modifying variables? | In `a() + b() * c()`, Java evaluates `a()` before `b()` and then `c()`, even though multiplication has higher precedence |

**Key insight:** "`*` has higher precedence than `+`" **does not mean** a method supplying an operand to multiplication runs before a method supplying an operand to addition. *Precedence* decides **operation structure**; *evaluation order* decides **subexpression execution sequence**.

The following example evaluates `left()` first, then `middle()` and `right()`, yet still multiplies the last two results before adding:

```java
int answer = left() + middle() * right();
// Equivalent grouping: left() + (middle() * right())
// Function call order: left(), middle(), right()
```

Although some compilers may optimize computations, the observable behavior of a Java program must obey the specified evaluation order semantics.

## 2. Precedence Table of Common Operators

Read **from top to bottom**: higher rows have higher precedence than lower rows. This is a practical table focusing on arithmetic and operators commonly appearing alongside numeric expressions.

| Level (high → low) | Operators | Example and grouping |
| --- | --- | --- |
| Postfix | `expr++`, `expr--` | `i++` returns old value then increments variable |
| Unary | `++expr`, `--expr`, `+expr`, `-expr`, `~expr`, `!expr` | `-a * b` groups as `(-a) * b` |
| Multiplicative | `*`, `/`, `%` | `a + b * c` groups as `a + (b * c)` |
| Additive | `+`, `-` | `a + b << 2` groups as `(a + b) << 2` |
| Shift | `<<`, `>>`, `>>>` | `1 << 2 + 1` groups as `1 << (2 + 1)` |
| Relational | `<`, `<=`, `>`, `>=`, `instanceof` | `a + b < c` groups as `(a + b) < c` |
| Equality | `==`, `!=` | `a < b == flag` groups as `(a < b) == flag` |
| Bitwise/boolean AND | `&` | `(a & b) == c` requires parentheses to compare the AND result |
| Bitwise/boolean XOR | `^` | `a ^ b & c` groups as `a ^ (b & c)` |
| Bitwise/boolean OR | `\|` | `a \| b ^ c` groups as `a \| (b ^ c)` |
| Short-circuit logical AND | `&&` | `checkA() && checkB()` |
| Short-circuit logical OR | `\|\|` | `checkA() \|\| checkB()` |
| Conditional | `? :` | `a ? x : b ? y : z` is `a ? x : (b ? y : z)` |
| Assignment and compound assignment | `=`, `+=`, `-=`, `*=`, `/=`, `%=`, `&=`, `^=`, `\|=`, `<<=`, `>>=`, `>>>=` | `a = b = c` groups as `a = (b = c)` |

**Note on the table:** parentheses `(...)` explicitly specify grouping; member access, method invocation, array indexing, casts, object creation, and special grammar constructs also have their own rules. The table above covers the key rules when learning expressions, **not the entire Java grammar**.

In production code, parentheses are often worth adding even when not strictly required, especially when combining shifts, bitwise ops, comparisons, and conditionals.

### Quick Examples for Reading the Table

```java
int a = 2 + 3 * 4;         // 14 = 2 + 12
int b = (2 + 3) * 4;       // 20
int c = 1 << 2 + 1;        // 8 = 1 << (2 + 1)
int d = (1 << 2) + 1;      // 5
int e = 17 % 5 * 2;        // 4 = (17 % 5) * 2
int f = 2 | 4 & 3;         // 2 = 2 | (4 & 3)
boolean g = (5 & 3) == 1; // true
```

The expression `5 & 3 == 1` is **not equivalent** to `(5 & 3) == 1`. Because `==` has higher precedence than `&`, Java tries to group `5 & (3 == 1)`. The right-hand side is then `boolean` while the left-hand side is `int`, causing a **compile error**. When testing bits with a mask, explicitly write `(value & mask) == expected` or `(value & mask) != 0`.

## 3. Associativity: Left-Grouping vs. Right-Grouping

**Associativity** only matters when an expression contains operators whose grouping would otherwise be ambiguous at the same precedence level.

### 3.1. Most Binary Operators Associate Left-to-Right

Arithmetic operators such as `+`, `-`, `*`, `/`, and `%` at their respective levels are grouped **from left to right**.

```text
20 - 6 - 2
= (20 - 6) - 2
= 12

20 - (6 - 2)
= 20 - 4
= 16
```

```java
int leftGrouped = 20 - 6 - 2;      // 12
int rightGrouped = 20 - (6 - 2);   // 16

int quotient = 100 / 5 / 2;       // 10 = (100 / 5) / 2
int other = 100 / (5 / 2);        // 50: 5 / 2 = 2, then 100 / 2
```

Because integer division truncates fractional parts toward zero, changing parentheses can drastically alter the result. For example, `7 / 2 * 2 = 6`, even though mathematically on real numbers `(7/2)×2 = 7`. In Java, `/` and `*` share **the same precedence level**; left-grouping and the operand numeric types determine the result.

Similarly, `1 << 2 << 1` groups as `(1 << 2) << 1`, yielding `8`. Shift operators at the same level associate left-to-right.

### 3.2. Assignment Associates Right-to-Left

```java
int a, b, c;
a = b = c = 7;
```

The grouping is:

```text
a = (b = (c = 7))
```

All three variables receive `7`. An assignment expression returns the assigned value, so the result of `c = 7` is used as the value assigned to `b`, and then to `a`.

**Do not infer** from right-associativity that "all operands are executed from right to left". **Evaluating the left-hand side of an assignment** and subexpressions still follows their own evaluation rules. Expression grouping and execution order can differ.

### 3.3. Ternary Conditional Operator Associates Right-to-Left

```java
int value = false ? 10 : true ? 20 : 30;
// Grouping: false ? 10 : (true ? 20 : 30)
// Result: 20
```

For maintainability, place explicit parentheses in nested conditional expressions, or use `if/else` if the logic is complex. Only **one** of the two branches corresponding to the condition outcome is evaluated.

## 4. Java Evaluates Operands Left-to-Right

For most ordinary binary operator expressions, Java **evaluates the left operand first**, then the right operand, and only then performs the operation with the resulting values.

Consider:

```java
int result = first() + second() * third();
```

Operation structure tree:

```text
         (+)
        /   \
   first()   (*)
            /   \
       second() third()
```

Runtime execution sequence:

```text
1. Call first(), keep return value
2. Call second(), keep return value
3. Call third(), keep return value
4. Multiply results of second() and third()
5. Add result of first() to the product
```

This is a classic example proving that **operator precedence** does not mean **function call priority**.

Method calls also evaluate arguments from left to right. For example, `method(first(), second())` calls `first()` before `second()`; if the first argument throws an exception, the second argument is not evaluated.

Java also guarantees consistent observation of side effects in the specified order, even when the compiler or VM optimizes expressions in ways that do not change observable behavior.

## 5. Increment/Decrement: Prefix and Postfix

`++x` and `x++` both increment variable `x` by `1`, but **the expression value** differs.

| Syntax | Expression value | Variable value after operation |
| --- | --- | --- |
| `++x` | **New** value of `x` | Incremented by 1 |
| `x++` | **Old** value of `x` | Incremented by 1 |
| `--x` | **New** value after decrement | Decremented by 1 |
| `x--` | **Old** value before decrement | Decremented by 1 |

```java
int i = 1;
int a = i++; // a = 1, i = 2
int b = ++i; // b = 3, i = 3
```

An expression with multiple side effects still has a **Java-defined** result, though it is error-prone when reading:

```java
int i = 1;
int result = i++ + i++ * 10;
// Left operand of +: i++ returns 1, i becomes 2.
// Left operand of *: i++ returns 2, i becomes 3.
// Multiplication: 2 * 10 = 20.
// Addition: 1 + 20 = 21.
// Finally: result = 21, i = 3.
```

If you mistakenly think "multiplication runs first so the multiplication's `i++` must run first", you will predict the wrong answer. This is precisely the difference between **binding operators to operands** and **executing operands**.

Even though Java defines the result clearly, in business code you should separate side effects so readers do not have to mentally simulate variable state:

```java
int i = 1;
int first = i++;
int second = i++;
int result = first + second * 10; // 21
```

## 6. Short-Circuit Logical Operators vs. Non-Short-Circuit Bitwise/Boolean Operators

For `boolean` operands:

- `a && b`: always evaluates `a`; if `a` is `false`, **skips** `b`.
- `a || b`: always evaluates `a`; if `a` is `true`, **skips** `b`.
- `a & b`, `a | b`, `a ^ b` work with `boolean`, but **evaluate both sides** (unless evaluation of the first side aborts via an exception); there is no short-circuiting like `&&`, `||`.
- For integers, `&`, `|`, `^` are bitwise operators; `&&`/`||` **cannot be used on integers**.

```java
int divisor = 0;
boolean safe = divisor != 0 && 100 / divisor > 10; // false, no division by 0
```

In the expression above, replacing `&&` with `&` causes the right side to run and throw `ArithmeticException: / by zero`. Thus evaluation order and **whether evaluation happens at all** are part of correctness, not merely performance.

```java
boolean accepted = true || expensiveCheck(); // expensiveCheck() is not called
boolean both = true & expensiveCheck();       // expensiveCheck() is called
```

The ternary operator `condition ? whenTrue : whenFalse` also evaluates only one branch after evaluating the condition. In nested expressions, add parentheses or use control statements when branches have side effects.

## 7. Parentheses Change Grouping, Not Automatically Execution Order

Use parentheses to clarify intent:

```java
int defaultValue = 2 + 3 * 4;   // 14
int overridden = (2 + 3) * 4;   // 20
```

However:

```java
int result = first() + (second() * third());
```

still calls `first()` first, then `second()`, then `third()`. Parentheses here clarify **the existing grouping**; they do not instruct Java to "run `second()` before `first()`".

If you truly want to control the order of side effects, write the expression as multiple statements in the desired sequence:

```java
int secondValue = second();
int thirdValue = third();
int firstValue = first();
int result = firstValue + secondValue * thirdValue;
```

Do not arbitrarily alter grouping, because with integer subtraction/division, overflow, or floating-point addition, changing parentheses can change the result.

## 8. Specific to Integer Arithmetic: Operand Types and Division Matter as Much as Precedence

### 8.1. Multiplication, Division, and Remainder Share the Same Level

```java
int a = 7 / 2 * 2;       // (7 / 2) * 2 = 3 * 2 = 6
int b = 7 * 2 / 2;       // (7 * 2) / 2 = 14 / 2 = 7
int c = 20 % 6 * 3;      // (20 % 6) * 3 = 2 * 3 = 6
int d = 20 % (6 * 3);    // 20 % 18 = 2
```

`/`, `*`, and `%` all share the same precedence level; hence left-associativity explains the differences. Java integer division truncates the quotient toward **0**: `-7 / 2 == -3`, `7 / -2 == -3`. Remainder `a % b` satisfies `a == (a / b) * b + (a % b)` in ordinary integer cases (including the special overflow case of `MIN_VALUE / -1` as defined by Java), and a non-zero remainder takes the sign of the dividend.

### 8.2. Operations Execute in the Post-Numeric-Promotion Type

```java
int x = 1_500_000_000;
long wrong = x * 2;           // -1294967296L: int multiplication overflows first
long correct = (long) x * 2; // 3000000000L: convert x to long first
```

This is an effect of **operand types** and **cast timing**, not pure precedence. In `(long) x * 2`, `(long) x` becomes `long` before the multiplication, causing the multiplication to run as `long`. Assigning an `int` multiplication result to a `long` variable after it has already overflowed cannot recover lost bits.

Similarly, `byte`, `short`, and `char` are generally promoted to `int` when participating in binary arithmetic operations:

```java
byte a = 10, b = 20;
int sum = a + b;      // int, value 30
// byte bad = a + b;  // compile error: int expression cannot implicitly assign to byte
```

**Constant exception:** the compiler allows certain `int` constant expressions to be assigned to `byte`/`short`/`char` if within the target range, such as `byte p = 10 + 20;`. This does not turn `byte + byte` into an operation returning `byte`.

### 8.3. Unary Minus and Boundary Values

Unary `-` has higher precedence than binary `*` and `+`:

```java
int a = -2 * 3;      // (-2) * 3 = -6
int b = 2 * -3;      // 2 * (-3) = -6
int c = -(2 + 3);    // -5
```

With `Integer.MIN_VALUE`, negating in `int` produces an overflowed result:

```java
int min = Integer.MIN_VALUE;
int same = -min;                 // still Integer.MIN_VALUE
long positive = -(long) min;     // 2147483648L
```

Type widening must occur **before negation** if you want the true positive mathematical result. Use `Math.negateExact` if overflow must be detected instead of accepting bit wraparound.

## 9. Bit Shifts, Masks, and Comparisons

In integer arithmetic, confusing precedence among addition, bit shifts, and comparisons is very common:

```java
int a = 1 << 3 + 1;       // 16 because 1 << (3 + 1)
int b = (1 << 3) + 1;     // 9

int flags = 0b1010;
boolean hasBit = (flags & 0b0010) != 0; // true
```

To test bits with a mask, always use parentheses:

```java
if ((flags & mask) != 0) {
    // At least one bit in mask is set.
}
```

`flags & mask != 0` does not group as the intended check: `!=` binds tighter than `&`, causing an `int & boolean` type error.

Remember that shift operators execute on `int` or `long` after promotion. `>>` is arithmetic (sign-extending) right shift, while `>>>` is logical (zero-fill) right shift. When the shift distance is an arithmetic expression, both **addition precedence** and **the left operand's type** affect the result.

## 10. Evaluation Order in Assignment and Compound Assignment

Assignment associates right-to-left, but the left-hand side can be a variable, field, or array element with an access expression that must be evaluated. Do not conflate "right-grouping" with "running right-to-left".

For example:

```java
int[] numbers = {10, 20};
int index = 0;
numbers[index++] = 99;
// Element numbers[0] becomes 99, index becomes 1.
```

With **compound assignment** such as `x += expression`, Java saves the existing value of the left-hand side to perform the combined operation before writing the result; for left-hand sides with complex indices/receivers, they are evaluated only once per compound assignment rules.

```java
int x = 1;
x += (x = 5);
System.out.println(x); // 6
```

Trace: the left-hand side of `+=` reads and saves the old value `1`; the right-hand side `(x = 5)` sets `x` to `5` and evaluates to `5`; `+=` uses the saved value `1 + 5` and finally assigns `6` to `x`.

Compound assignment also includes an implicit cast to the left-hand variable's type. For example:

```java
byte count = 127;
count += 1;          // count becomes -128 due to narrowing cast, no error thrown
// count = count + 1; // compile error because count + 1 has type int
```

Conceptually, `E1 op= E2` is close to `E1 = (T)((E1) op (E2))` where `T` is the type of `E1`, **except `E1` is evaluated only once**. Therefore, do not mechanically rewrite it as a regular assignment if `E1` has side effects or involves array/method access.

## 11. When Exceptions Occur, Evaluation Order Determines Which Side Effects Already Happened

Integer division by zero throws `ArithmeticException`. In the expression:

```java
int result = numerator() / denominator();
```

Java evaluates `numerator()` first and then `denominator()`. Next the division is executed; if the divisor is zero, an exception is thrown. If `numerator()` logged output or updated a variable, that side effect has already occurred.

In `left() + right()`, if `left()` throws an exception, `right()` is not called. The same principle applies to method arguments evaluated left-to-right. Meanwhile, in `&&`/`||`, one side may not be evaluated due to short-circuiting even without an exception.

When logic only makes sense if steps succeed, splitting into separate statements makes clearer where exceptions can arise and which state changes have already happened.

## 12. Standalone Runnable Java 17+ Program and Output

Create a file **`OperatorEvaluationDemo.java`**:

```java
public class OperatorEvaluationDemo {
    private static int number(String name, int value) {
        System.out.print(name + " ");
        return value;
    }

    private static boolean condition(String name, boolean value) {
        System.out.print(name + " ");
        return value;
    }

    public static void main(String[] args) {
        System.out.print("precedence: ");
        int p = number("A", 2) + number("B", 3) * number("C", 4);
        System.out.println("=> " + p);

        System.out.print("associativity: ");
        int s = number("X", 20) - number("Y", 6) - number("Z", 2);
        System.out.println("=> " + s);

        int shift = 1 << 2 + 1;
        int mask = 5 & 3;
        System.out.println("shift = " + shift);
        System.out.println("mask = " + mask);

        int i = 1;
        int value = i++ + i++ * 10;
        System.out.println("postfix value = " + value + ", i = " + i);

        int x = 1;
        x += (x = 5);
        System.out.println("compound x = " + x);

        System.out.print("short-circuit AND: ");
        boolean and = condition("left", false)
                && condition("right", true);
        System.out.println("=> " + and);

        System.out.print("short-circuit OR: ");
        boolean or = condition("left", true)
                || condition("right", false);
        System.out.println("=> " + or);

        System.out.print("conditional: ");
        int selected = condition("test", false)
                ? number("then", 10)
                : number("else", 20);
        System.out.println("=> " + selected);

        System.out.print("division: ");
        try {
            int quotient = number("numerator", 10)
                    / number("denominator", 0);
            System.out.println("=> " + quotient);
        } catch (ArithmeticException e) {
            System.out.println("=> / by zero");
        }
    }
}
```

Compile and run in the directory containing the file:

```bash
javac OperatorEvaluationDemo.java
java OperatorEvaluationDemo
```

**Exact output:**

```text
precedence: A B C => 14
associativity: X Y Z => 12
shift = 8
mask = 1
postfix value = 21, i = 3
compound x = 6
short-circuit AND: left => false
short-circuit OR: left => true
conditional: test else => 20
division: numerator denominator => / by zero
```

Key observations:

- Even though multiplication has higher precedence than addition, `A` is still evaluated before `B` and `C`. The computed result is `2 + (3 * 4) = 14`.
- Subtraction associates left-to-right: `(20 − 6) − 2 = 12`.
- `1 << 2 + 1` takes a shift distance of `3`; `&` on `5` and `3` gives `1`.
- The two `i++` calls read `1` and `2` in turn; the result is `21` and final `i` equals `3`.
- `+=` retains the old left-hand value, so final `x` equals `6`.
- `right` is not printed for `&&` when the left side is false, nor for `||` when the left side is true.
- The `?:` operator only invokes `else` when the condition is false.
- The division invoked both `numerator` and `denominator` before detecting the zero divisor.

## 13. Common Real-World Mistakes

| Misconception | Why it is wrong and how to fix it |
| --- | --- |
| "`*` has higher precedence, so the function on the multiplication side is called first" | Java evaluates the left operand first; precedence only determines operation grouping |
| "Left-associative means every function/operation executes immediately from left to right" | Associativity determines the expression tree; an operation executes only once its operands are ready, while function calls follow their own order |
| "`a = b = c` runs everything from right to left" | That is **assignment grouping**; evaluating left-hand expressions follows its own rules |
| "`100 / 5 / 2` = `100 / (5 / 2)`" | Different grouping; integer division also truncates toward zero |
| "`1 << 2 + 1` shifts by 2 bits then adds 1" | `+` has higher precedence than `<<`; it actually shifts by 3 bits |
| "`flags & mask != 0` checks the mask" | `!=` has higher precedence than `&`; write `(flags & mask) != 0` |
| "`&&` and `&` are identical for booleans" | `&&` short-circuits, `&` evaluates both sides |
| "`i++ + i++` is unordered in Java" | Java specifies left-to-right order; still avoid it for maintainability |
| "`long x = intA * intB` avoids `int` overflow" | Overflow can already happen in multiplication before assignment; cast before multiplying |
| "Parentheses make the right-hand function run first" | Parentheses change operation structure, not operand evaluation order |
| "`x += y` is always equivalent to `x = x + y`" | Includes an implicit cast and guarantees the left-hand target is evaluated only once |
| "Changing parentheses always yields the same mathematical result" | Integer division, overflow, binary floating-point, and side effects can all change results |

## 14. Self-Check Exercises

Compute the results according to Java semantics, not solely by mathematical intuition.

**Exercise 1.** What is the result of `int x = 2 + 4 * 3 - 5;`?

**Exercise 2.** How does `int x = 32 / 4 / 2;` differ from `int y = 32 / (4 / 2);`?

**Exercise 3.** What number does `int x = 1 << 1 + 2;` produce?

**Exercise 4.** Given `int flags = 0b1100; int mask = 0b0100;`, write a boolean condition to check whether the bit in `mask` is set in `flags`.

**Exercise 5.** After this snippet, what are the values of `result` and `i`?

```java
int i = 1;
int result = ++i + i++ * 3;
```

**Exercise 6.** Why can the two expressions below give different results?

```java
int a = 7 / 2 * 2;
int b = 7 * 2 / 2;
```

**Exercise 7.** Does `boolean ok = false && (10 / 0 > 1);` throw an exception at runtime? How does that compare to using `&`?

**Exercise 8.** What will `x` equal after `int x = 1; x += (x = 4);`? Why?

### Answer Explanations

1. `2 + 12 - 5 = 9`, because `*` has higher precedence than `+`/`-`.
2. `x = (32/4)/2 = 4`; `y = 32/(4/2) = 16`.
3. `1 << (1 + 2) = 1 << 3 = 8`.
4. `boolean enabled = (flags & mask) != 0;`, result `true`.
5. `++i` returns `2` and sets `i=2`; the next `i++` returns `2` and sets `i=3`; `result = 2 + 2*3 = 8`.
6. In `7 / 2 * 2`, integer division gives `3` first and multiplying gives `6`; in `7 * 2 / 2`, multiplying first gives `14` and dividing by `2` gives `7`.
7. `false && ...` short-circuits so the division is not evaluated; no exception is thrown. With `false & ...`, Java evaluates the right side and dividing by 0 throws `ArithmeticException`. *In this exercise, the literal 0 divisor is inside a runtime expression; the expression compiles and the error occurs only if the division is actually evaluated.*
8. `x += (x = 4)` retains the initial `x` of `1` for the left-hand side; the right-hand side assigns `4`; the addition gives `1+4=5`, so final `x` equals `5`.

## 15. Checklist for Reading or Writing Complex Expressions

1. **Identify the type** of each operand: `int`, `long`, `boolean`, or reference type? Does the operation promote, narrow-cast, or overflow?
2. **Group the expression** using parentheses and precedence; at the same level, determine associativity.
3. **Mark operand evaluation order**, especially method calls, `++`/`--`, assignments, and array accesses.
4. **Check short-circuiting** in `&&`, `||`, and branches of `?:`; which side can be skipped?
5. **Check exceptions** and side effects: which side has already run before a division by 0, invalid access, or throwing call?
6. **Add parentheses and split statements** if readers must juggle multiple rules at once; prioritize clarity in monetary calculations, bit manipulation, and validation conditions.
7. **Do not apply arbitrary algebraic transformations**: integer arithmetic has range limits and integer division; floating-point has rounding and special values.

**Key Takeaway:** **Precedence** chooses which operators bind to which operands; **associativity** decides how operators of equal rank group; **evaluation order** decides which subexpressions actually run first. Distinguishing all three accurately lets you predict the values, side effects, and exceptions of Java expressions.