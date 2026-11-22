# Distinguishing Bitwise Operations from Boolean Conditions in Java

> **Java core — language-basics / Bitwise operators**  
> **Version:** Java 17+; standalone example, no external libraries needed.  
> **Goal:** Distinguish operations on **individual bits of integers** from operations on **true/false values**; use `&`, `|`, `^`, `~`, `!`, `&&`, and `||` correctly; understand short-circuiting and write valid bit-mask check conditions.

## 1. Two Different Data Domains

In Java, integers are represented as 0/1 bits, whereas `boolean` has only the values `true` or `false`. Several operator symbols are used in **both domains**, but their meaning is determined by the **operand types**.

~~~java
int bitsA = 0b1100; // 12
int bitsB = 0b1010; // 10
int bitResult = bitsA & bitsB; // 0b1000 = 8

boolean ready = true;
boolean allowed = false;
boolean logicResult = ready & allowed; // false
~~~

`&` on the first line produces an **integer** from each pair of bits; `&` on the later line produces a **boolean** from two conditions. Java **does not** automatically treat `int 0` as false, or a non-zero number as true.

~~~java
// DOES NOT COMPILE:
// if (1) { }
// boolean b = 1;
// int n = true;
// int mixed = 7 & true;
~~~

## 2. Bitwise Operations on Integers Return Integers

For `byte`, `short`, `char`, `int`, and `long` (and unboxable wrappers), `&`, `|`, and `^` process each bit position; `~` inverts all bits after numeric promotion. Example with `int a = 0b1100` and `b = 0b1010`:

~~~java
int a = 0b1100;
int b = 0b1010;
int and = a & b;       // 0b1000 = 8.
int or = a | b;        // 0b1110 = 14.
int xor = a ^ b;       // 0b0110 = 6.
int not = ~a;          // -13: inverts all 32 bits.
int fourBits = ~a & 0b1111; // 3: keeps only the low 4 bits.
~~~

These expressions return **`int`** and cannot be used directly as an `if` condition. `byte`/`short`/`char` are typically promoted to `int`, and if either operand is `long`, the binary bitwise operation uses `long`. The lesson on AND/OR/XOR/NOT covers the full truth tables; the sections below focus on what changes when **the same symbols** receive `boolean` operands.

## 3. Logical Operators on Booleans

| Operator | Meaning on `boolean` | Is the right-hand side evaluated? |
| --- | --- | --- |
| `!a` | NOT: flips true/false | Single operand |
| `a && b` | Short-circuit AND | **Only when `a` is true** |
| Short-circuit OR: `a \|\| b` | Short-circuit OR | **Only when `a` is false** |
| `a & b` | Non-short-circuit AND | **Always** |
| Non-short-circuit OR: `a \| b` | Non-short-circuit OR | **Always** |
| `a ^ b` | XOR | **Always** |

Example:

~~~java
boolean ready = true;
boolean allowed = false;

System.out.println(ready && allowed); // false
System.out.println(ready || allowed); // true
System.out.println(ready ^ allowed);  // true
System.out.println(!ready);           // false
~~~

For `boolean`, `&` and `&&` have the exact same **truth table**, and so do `|` and `||`. **The difference is whether the right-hand side is guaranteed to be evaluated.** `^` returns true when exactly one of the two values is true; `~` is invalid on booleans—you must use `!` for logical negation.

## 4. Short-Circuiting Determines Side Effects and Exceptions

Java evaluates the left-hand side first. If the left-hand side already determines the outcome, `&&`/`||` skip the right-hand side; `&`/`|` on booleans do not.

~~~java
int divisor = 0;

boolean safe = divisor != 0 && 10 / divisor > 1;
// safe=false, division by 0 is not executed.

// boolean unsafe = divisor != 0 & 10 / divisor > 1;
// If this line runs: ArithmeticException.
~~~

The same applies to null checks:

~~~java
String name = null;
boolean hasText = name != null && !name.isBlank(); // false
boolean missing = name == null || name.isBlank();  // true
~~~

**Do not** swap `&&` for `&` or `||` for `|` merely because their logical outcomes usually match. Whenever the right-hand side contains a method call, variable increment, array access, or unboxing of a nullable `Boolean`, that difference can alter program behavior.

## 5. Bit Masks: Integer Variables Do Not Become Conditions on Their Own

A bit mask is commonly used to store on/off flags inside **a single integer**:

~~~java
final int READ  = 0b0001;
final int WRITE = 0b0010;
final int EXEC  = 0b0100;

int permissions = READ | EXEC; // 0b0101
~~~

To ask whether the user has read permission, `permissions & READ` returns an **int** (1 or 0), not a boolean:

~~~java
boolean canRead = (permissions & READ) != 0;   // true
boolean canWrite = (permissions & WRITE) != 0; // false
boolean hasBoth = (permissions & (READ | EXEC))
        == (READ | EXEC);                      // true
~~~

| Purpose | Correct expression | Result type |
| --- | --- | --- |
| Filter common bits | `permissions & mask` | `int` |
| Has **at least one** selected bit | `(permissions & mask) != 0` | `boolean` |
| Has **all** selected bits | `(permissions & mask) == mask` | `boolean` |
| Set bits | `permissions \| mask` | `int` |
| Clear bits | `permissions & ~mask` | `int` |
| Toggle bits | `permissions ^ mask` | `int` |
| Combine two boolean conditions | `canRead && canWrite` | `boolean` |

Do not write `if (permissions & READ)`: `if` requires a boolean, so Java reports a compile error. Convert the **integer result** into a boolean comparison such as `(permissions & READ) != 0`.

**Watch the parentheses:** Java gives `==` and `!=` **higher** precedence than bitwise `&`. Always write `(permissions & mask) != 0`, never `permissions & mask != 0`.

## 6. Do Not Mix Up Operators and Semantics

| Expression | Valid? | Why? |
| --- | --- | --- |
| `5 & 3` | Yes | `int` result is 1 |
| `true & false` | Yes | `boolean` result false, both sides execute |
| `true && false` | Yes | `boolean` result false, short-circuits |
| `true ^ false` | Yes | Logical XOR is true |
| `~5` | Yes | `int` bitwise complement: -6 |
| `!true` | Yes | Boolean negation: false |
| `5 && 3` | **No** | `&&` accepts only booleans |
| `~true` | **No** | `~` accepts only integers |
| `!5` | **No** | `!` accepts only booleans |
| `5 & true` | **No** | No `&` operator between `int` and `boolean` |

When both sides of `&`/`|`/`^` are booleans, Java applies boolean logic; when both are integers, it applies bitwise operations. There is no "hybrid int-and-boolean" result type, nor any implicit conversion between these two domains.

With the `Boolean` wrapper, remember that logical operators can **unbox**, throwing `NullPointerException` when the reference is null. Use a guard condition like `value != null && value` if needed.

## 7. Runnable Java 17+ Program

Create the file **BitwiseVsBooleanDemo.java**:

~~~java
public final class BitwiseVsBooleanDemo {
    private static boolean mark(
            StringBuilder log, String label, boolean result) {
        log.append(label);
        return result;
    }

    public static void main(String[] args) {
        int a = 0b1100;
        int b = 0b1010;
        System.out.println("bitAnd=" + (a & b));
        System.out.println("bitOr=" + (a | b));
        System.out.println("bitXor=" + (a ^ b));
        System.out.println("bitNot=" + (~a));
        System.out.println("bitNotLow4=" + ((~a) & 0b1111));

        final int READ = 0b0001;
        final int WRITE = 0b0010;
        final int EXEC = 0b0100;
        int flags = READ | EXEC;
        System.out.println("readAllowed=" + ((flags & READ) != 0));
        System.out.println("writeAllowed=" + ((flags & WRITE) != 0));
        System.out.println("hasReadExec="
                + ((flags & (READ | EXEC)) == (READ | EXEC)));
        System.out.println("setWrite=" + Integer.toBinaryString(flags | WRITE));

        boolean ready = true;
        boolean allowed = false;
        System.out.println("boolAnd=" + (ready & allowed));
        System.out.println("boolOr=" + (ready | allowed));
        System.out.println("boolXor=" + (ready ^ allowed));
        System.out.println("boolNot=" + (!ready));
        System.out.println("shortAnd=" + (ready && allowed));
        System.out.println("shortOr=" + (ready || allowed));

        StringBuilder trace = new StringBuilder();
        boolean scAnd = mark(trace, "F", false)
                && mark(trace, "X", true);
        boolean scOr = mark(trace, "T", true)
                || mark(trace, "Y", false);
        boolean eagerAnd = mark(trace, "A", false)
                & mark(trace, "B", true);
        boolean eagerOr = mark(trace, "C", true)
                | mark(trace, "D", false);
        boolean eagerXor = mark(trace, "E", true)
                ^ mark(trace, "G", true);
        System.out.println("scAnd=" + scAnd + ",scOr=" + scOr);
        System.out.println("eagerAnd=" + eagerAnd
                + ",eagerOr=" + eagerOr + ",eagerXor=" + eagerXor);
        System.out.println("trace=" + trace);

        int divisor = 0;
        System.out.println("divideGuard="
                + (divisor != 0 && 10 / divisor > 1));
        try {
            boolean error = divisor != 0 & 10 / divisor > 1;
            System.out.println("error=" + error);
        } catch (ArithmeticException e) {
            System.out.println("eagerDivide=ArithmeticException");
        }
    }
}
~~~

Run from the directory containing the file (Bash, PowerShell, or Command Prompt):

~~~bash
javac -encoding UTF-8 BitwiseVsBooleanDemo.java
java BitwiseVsBooleanDemo
~~~

**Exact expected stdout:**

~~~text
bitAnd=8
bitOr=14
bitXor=6
bitNot=-13
bitNotLow4=3
readAllowed=true
writeAllowed=false
hasReadExec=true
setWrite=111
boolAnd=false
boolOr=true
boolXor=true
boolNot=false
shortAnd=false
shortOr=true
scAnd=false,scOr=true
eagerAnd=false,eagerOr=true,eagerXor=false
trace=FTABCDEG
divideGuard=false
eagerDivide=ArithmeticException
~~~

To understand `trace=FTABCDEG`: `&&` skips X, `||` skips Y; whereas `&`, `|`, and `^` always run both sides. `divideGuard=false` does not execute the division, while `eagerDivide` throws an exception because `&` still evaluates its right-hand side.

## 8. Self-Check Exercises

**Exercise 1.** Given `int a = 0b0110, b = 0b1010;`, compute `a & b`, `a | b`, and `a ^ b` in 4-bit binary.

**Exercise 2.** Given `boolean a = true, b = false;`, predict `a & b`, `a | b`, `a ^ b`, and `!a`; distinguish them from bitwise operators on numbers.

**Exercise 3.** Why does `if (flags & 0b0100)` fail to compile? Rewrite it to test the second bit (counting from bit 0).

**Exercise 4.** Explain the difference between `false && check()` and `false & check()` if `check()` mutates a variable or can throw an exception.

**Exercise 5.** Write a condition to check for both READ **and** WRITE permissions when permissions are stored in `int flags`. Distinguish this from checking **at least one** of the two permissions.

### Key Takeaways

**`&`, `|`, and `^` have two uses depending on type:** bitwise on integers, non-short-circuiting logic on booleans. `~` inverts **integer bits only**, while `!` negates **booleans only**. `&&` and `||` work only on booleans and short-circuit. To turn a bit mask result into an `if` condition, compare it against 0 or against the mask, such as `(flags & mask) != 0`.
