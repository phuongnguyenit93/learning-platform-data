# Compound Assignment `+=`, `-=`, `*=`, `/=`, and `%=` — Java 17+

**Compound assignment** both performs an operation and **assigns the result back to the variable or storage location on the left-hand side**. The five common arithmetic operators are:

| Operator | Meaning | Example with `x = 10` | Value of `x` after assignment |
| --- | --- | --- | ---: |
| `+=` | Add then assign | `x += 5;` | 15 |
| `-=` | Subtract then assign | `x -= 3;` | 7 |
| `*=` | Multiply then assign | `x *= 2;` | 20 |
| `/=` | Divide then assign | `x /= 4;` | 2 if `x` is `int` |
| `%=` | Remainder then assign | `x %= 3;` | 1 |

**Note:** each row in the table is meant as an independent example, each starting from `x = 10`. These operators do not create a new kind of variable: after the assignment, **the variable's declared type remains unchanged**.

~~~java
int score = 10;
score += 5;        // score = 15.
score *= 2;        // score = 30.
score -= 4;        // score = 26.
~~~

## 1. A More Accurate Way to Think About It Than “Assignment Shorthand”

Semantically, for a left-hand side of type `T`, `E1 op= E2` corresponds to performing the operation and then **converting the result to `T`**, with two important differences from manually expanding the syntax: **`E1` is evaluated only once**, and **compound assignment performs type conversion to the left-hand side's type**.

~~~text
E1 op= E2

Roughly equivalent in value to:
E1 = (T) ((E1) op (E2))

Important exception: E1 is evaluated ONLY ONCE in op=.
~~~

Example:

~~~java
int total = 10;
total += 4; // 14.
~~~

For a simple `int`, the result is the same as `total = total + 4`. However, you should not treat this as a mechanical text substitution for every type and every left-hand side expression.

**A compound assignment is still an expression with a value**; however, when you do not need the assignment's value, writing a standalone statement is usually easier to read:

~~~java
int count = 3;
count += 2; // Prefer this when you only want to update the variable.
~~~

## 2. Standalone Java 17+ Program

Create a UTF-8 file named **`CompoundAssignmentDemo.java`**:

~~~java
import java.util.Arrays;

public class CompoundAssignmentDemo {
    public static void main(String[] args) {
        int value = 10;
        value += 5;
        System.out.println("plus=" + value);
        value -= 3;
        System.out.println("minus=" + value);
        value *= 2;
        System.out.println("multiply=" + value);
        value /= 5;
        System.out.println("divide=" + value);
        value %= 3;
        System.out.println("remainder=" + value);

        byte small = 120;
        small += 10;
        System.out.println("byteOverflow=" + small);

        short medium = 30_000;
        medium *= 2;
        System.out.println("shortOverflow=" + medium);

        char letter = 'A';
        letter += 1;
        System.out.println("charNext=" + letter);

        int fractional = 3;
        fractional += 2.5;
        System.out.println("fractionalNarrowing=" + fractional);

        int negative = -10;
        negative %= 3;
        System.out.println("negativeRemainder=" + negative);

        int captured = 5;
        captured += (captured = 10);
        System.out.println("capturedOldValue=" + captured);

        int[] data = {10, 20};
        int index = 0;
        data[index++] += 7;
        System.out.println("array=" + Arrays.toString(data)
                + ",index=" + index);

        String message = "Java";
        message += " 17";
        message += ": " + (1 + 2);
        System.out.println("message=" + message);

        int numerator = 12;
        int zero = 0;
        try {
            numerator /= zero;
        } catch (ArithmeticException ex) {
            System.out.println("integerZero=ArithmeticException");
        }
        System.out.println("unchangedAfterException=" + numerator);

        double floating = 1.0;
        floating /= 0.0;
        System.out.println("floatingDivision=" + floating);

        double floatRemainder = 0.0;
        floatRemainder %= 0.0;
        System.out.println("floatingRemainderNaN="
                + Double.isNaN(floatRemainder));

        int overflowing = Integer.MAX_VALUE;
        overflowing += 1;
        System.out.println("intOverflow=" + overflowing);
    }
}
~~~

In the directory containing the file, open PowerShell (Windows) or Bash (Linux/macOS), using **JDK 17 or later**:

~~~bash
java -version
javac -version
javac -encoding UTF-8 CompoundAssignmentDemo.java
java CompoundAssignmentDemo
~~~

**Exact expected stdout** of `java CompoundAssignmentDemo`:

~~~text
plus=15
minus=12
multiply=24
divide=4
remainder=1
byteOverflow=-126
shortOverflow=-5536
charNext=B
fractionalNarrowing=5
negativeRemainder=-1
capturedOldValue=15
array=[17, 20],index=1
message=Java 17: 3
integerZero=ArithmeticException
unchangedAfterException=12
floatingDivision=Infinity
floatingRemainderNaN=true
intOverflow=-2147483648
~~~

`java -version` and `javac -version` have machine-dependent output and are not part of the expected stdout block above.

## 3. Difference from Ordinary Assignment: Implicit Type Conversion

When performing a compound assignment, Java uses the operand types to compute the operation, then **converts the result to the type of the left-hand side variable** according to compound assignment rules.

~~~java
byte b = 120;
b += 10; // Valid, b becomes -126 because the result 130 is narrowed to byte.
~~~

Meanwhile:

~~~java
byte b = 120;
// b = b + 10; // Compile error: b + 10 has type int, does not auto-assign to byte.
b = (byte) (b + 10); // Valid with an explicit cast.
~~~

In the example above, `byte` has a range from `-128` to `127`. The mathematical result 130 cannot be represented by a `byte`; narrowing type conversion keeps the appropriate low-order bits, making the value **-126**. `+=` **does not automatically check for overflow**.

With `short` and `char`, you also need to pay attention to the fact that arithmetic operations normally undergo numeric promotion:

~~~java
short amount = 30_000;
amount *= 2; // 60000 narrowed to short: -5536.

char ch = 'A';
ch += 1; // 'B'.
~~~

An even more subtle case:

~~~java
int count = 3;
count += 2.5; // Valid, the int result is 5.
// count = count + 2.5; // Error: double cannot auto-assign to int.
~~~

In `count += 2.5`, the addition produces `double 5.5`, and then the result is converted to `int`, becoming **5**. Floating-point to integer narrowing in Java **truncates the fractional part toward 0** within the representable value range. Therefore, avoid compound assignment across types that may cause data loss if the problem requires precision.

| Expression | Does It Compile? | Explanation |
| --- | --- | --- |
| `byte b = 1; b += 1;` | Yes | `byte` is updated after type conversion |
| `byte b = 1; b = b + 1;` | No | `b + 1` has type `int` |
| `char c = 'A'; c += 1;` | Yes | Next character by `char` code unit |
| `int x = 3; x += 2.5;` | Yes | `double 5.5` is narrowed to `int 5` |
| `int x = 3; x = x + 2.5;` | No | `double` does not auto-assign to `int` |

**Practical rule:** When operands have different types, do not just look at whether it compiles; check **the intermediate operation type and the final type conversion**.

## 4. The Left-Hand Side Is Evaluated Only Once

This is why **`a[i++] += 7` is not equivalent** to the textual substitution `a[i++] = a[i++] + 7`.

~~~java
int[] numbers = {10, 20};
int i = 0;
numbers[i++] += 7;
// numbers = [17, 20]; i = 1.
~~~

Compound assignment first determines the location `numbers[i++]` exactly once, saves the element's old value, evaluates the right-hand side expression, and assigns the result back to **that same location**. `i++` increments `i` only once.

If manually replaced with `numbers[i++] = numbers[i++] + 7`, `i++` appears twice: the read/write locations and post-assignment state can differ. Therefore, **do not manually expand `op=` when the left-hand side has side effects**.

Even for a simple variable, the evaluation order can be observed:

~~~java
int n = 5;
n += (n = 10);
System.out.println(n); // 15.
~~~

The old value of `n`, **5**, is retained for the addition, then the right-hand side assigns `n = 10` and returns 10; finally `+=` writes the result **15**. This expression is valid, but **hard to read** and should not be imitated when the code can be written across multiple steps.

## 5. `/=`: Distinguishing Integer Division from Floating-Point Division

~~~java
int count = 10;
count /= 4;   // 2, because int division truncates the fractional part.

double rate = 10.0;
rate /= 4;    // 2.5.
~~~

- `int /= int` performs integer division; the fractional remainder is discarded.
- `double /= int` applies numeric promotion and produces a `double` result.

**Division by zero** behaves differently:

~~~java
int x = 12;
int zero = 0;
try {
    x /= zero;
} catch (ArithmeticException ex) {
    System.out.println("division failed");
}
// x remains 12, because the assignment did not complete normally.

double y = 1.0;
y /= 0.0; // Infinity, does not throw ArithmeticException.
~~~

For integers, `/= 0` throws `ArithmeticException` and the compound assignment **does not write a result**. For floating-point numbers, `Infinity`/`NaN` follow IEEE 754 rules; if a finite value is required, check using `Double.isFinite` or `Float.isFinite`.

## 6. `%=`: Remainder Is Not Always Non-Negative

~~~java
int n = -10;
n %= 3; // -1.
~~~

The `%` operator on integers uses a quotient **truncated toward 0**. A non-zero remainder has the **same sign as the dividend** (the left operand). Changing the sign of the divisor does not necessarily change the sign of the remainder.

~~~java
int a = 10;
a %= -3; // 1.

int b = -10;
b %= -3; // -1.
~~~

If you need a **non-negative wrap-around index** with a positive modulus, `Math.floorMod(value, positiveModulus)` usually matches the intent better than `value % positiveModulus` when `value` can be negative. That is a separate method call; there is no dedicated `floorMod=` compound assignment operator.

With `double`, `0.0 % 0.0` produces `NaN` rather than throwing `ArithmeticException` like `int % 0`. You must distinguish operand types before reasoning about the result.

## 7. `+=` Also Works for `String`

`+=` can **concatenate strings**, not just add numbers:

~~~java
String label = "Java";
label += " 17";
label += ": " + (1 + 2);
System.out.println(label); // Java 17: 3.
~~~

`String` is immutable: each concatenation creates a resulting string value and reassigns the variable `label`; it does not mutate the contents of the old `String`. For repeated concatenation inside a large loop, `StringBuilder` is usually more appropriate.

In `label += ": " + (1 + 2)`, parentheses ensure `1 + 2` is added numerically before string concatenation. If written `label += ": " + 1 + 2`, the part concatenated with the string can produce `": 12"` due to the associativity of `+`.

**`-=`, `*=`, `/=`, and `%=` are not valid operators for manipulating `String` with arithmetic operations.**

## 8. Overflow, Type Conversion, and Safety Limits

~~~java
int count = Integer.MAX_VALUE;
count += 1; // -2147483648: int overflow, does not throw an exception.
~~~

Integer compound assignment **does not automatically detect overflow**. If throwing an error is required instead of allowing an overflowed result, use checked arithmetic:

~~~java
int count = Integer.MAX_VALUE;
// count = Math.addExact(count, 1);
// Throws ArithmeticException if it exceeds the int range.
~~~

For more exact arithmetic, choose a solution based on your needs:

- `Math.addExact`, `subtractExact`, `multiplyExact` are for checking overflow within the corresponding primitive range.
- `BigInteger` is used for integers exceeding the `long` range.
- `BigDecimal` can be used when decimal arithmetic with explicit scale/rounding policies is needed.

`BigInteger` and `BigDecimal` do not allow using `+=` directly between two objects like primitives; you must call the appropriate method and reassign the variable:

~~~java
java.math.BigDecimal total = new java.math.BigDecimal("1.25");
total = total.add(new java.math.BigDecimal("2.50"));
~~~

## 9. Common Mistakes

| Misconception | Correct Understanding |
| --- | --- |
| “`b += 1` is identical to `b = b + 1` for `byte`.” | `b += 1` allows narrowing type conversion; `b = b + 1` does not compile |
| “`+=` always preserves the full fractional part.” | `int += double` can truncate the fractional part |
| “The left-hand side is evaluated twice.” | Compound assignment evaluates **the left-hand side location only once** |
| “`x /= 4` is always floating-point division.” | If `x` and `4` are `int`, it is integer division |
| “`%` always produces a non-negative remainder.” | A negative dividend can produce a negative remainder |
| “`+=` on `String` adds numeric values.” | When participating in string concatenation, `+` can produce text |
| “`x += 1` throws an error when `int` overflows.” | No; use `Math.addExact` when checking is required |
| “If `x /= 0` throws an error, `x` is set to 0.” | The assignment does not complete; the old value is preserved |
| “`/ 0.0` and `/ 0` always behave the same.” | Floating-point division can yield `Infinity`/`NaN` |

## 10. Self-Check Exercises

1. What does `int x = 10; x += 3; x *= 2;` set `x` to?  
   *Answer:* **26**.
2. What does `byte b = 120; b += 10;` produce?  
   *Answer:* **-126**, because the result 130 is converted to type `byte`.
3. What does `int n = 3; n += 2.5;` set `n` to?  
   *Answer:* **5**, because `double 5.5` is narrowed to `int`.
4. What does `int n = 10; n /= 4;` produce?  
   *Answer:* **2**, integer division.
5. What does `int n = -10; n %= 3;` produce?  
   *Answer:* **-1**, taking the sign of the dividend.
6. How does `int[] a = {10, 20}; int i = 0; a[i++] += 7;` change the array and `i`?  
   *Answer:* The array becomes **`[17, 20]`**, `i = 1`; the left-hand side location is evaluated only once.
7. What does `int x = 5; x += (x = 10);` set `x` to?  
   *Answer:* **15**, because the left operand already saved the value 5.
8. What string does `String s = "A"; s += 1 + 2;` produce?  
   *Answer:* **`"A3"`** because the entire right-hand expression evaluates `1 + 2` before concatenating onto `s`.

## Checklist

- [ ] Distinguish `+=`, `-=`, `*=`, `/=`, `%=` by the operations for each operand type.
- [ ] Understand that compound assignment **assigns back to the same left-hand side type** and can implicitly narrow.
- [ ] Remember that the left-hand side `E1` is evaluated **only once**.
- [ ] For integers, watch out for division truncating fractional parts and the sign of `%`.
- [ ] Distinguish division/remainder by zero for integers vs. floating-point numbers.
- [ ] Recognize overflow and truncated values when converting to `byte`/`short`/`int`.
- [ ] Know that `String +=` is string concatenation, not numeric addition.
- [ ] Choose `Math.*Exact` or big/exact numeric classes if requirements exceed primitive capabilities.

**Conclusion:** Compound assignment in Java performs an operation **and reassigns**, with two rules you cannot overlook: **the left-hand side is evaluated only once**, and **the result can be narrowed to the left-hand side's type**. Understanding these rules helps avoid bugs with `byte`/`short`, floating-point numbers, array indices, overflow, and string concatenation.