# How `+` Order of Evaluation Affects Mixing Numbers and Strings in Java

> **Java core — language-basics / Characters and Strings**  
> **Requirements:** JDK 17 or later, no external libraries required.  
> **Goal:** Accurately predict the result when `+` is used for both numeric addition and `String` concatenation; understand left-associativity, operator precedence, evaluation order, and how adding parentheses avoids bugs.

## 1. Same `+` symbol, two meanings

Java uses the `+` sign according to operand types:

- If both operands are suitable for **numeric addition**, `+` computes the arithmetic sum (following Java's numeric promotion rules).
- If **at least one operand is a `String`**, `+` performs **string concatenation**: the other operand is converted into a text representation and concatenated.

~~~java
int sum = 10 + 20;                  // 30
String joined = "10" + 20;          // "1020"
String output = "total=" + sum;     // "total=30"
~~~

This is **not** “Java converts all numbers on the line into Strings”. Each `+` operation is analyzed by the operands of **that specific operation**, taking expression grouping into account.

## 2. Left-associativity changes the result

`+` operations at the same precedence level are grouped **from left to right** (*left-associative*).

| Expression | Grouping | Result |
| --- | --- | --- |
| `1 + 2 + "x"` | `(1 + 2) + "x"` | `"3x"` |
| `"x" + 1 + 2` | `("x" + 1) + 2` | `"x12"` |
| `1 + "2" + 3` | `(1 + "2") + 3` | `"123"` |
| `"sum=" + (1 + 2)` | Add inside parentheses first | `"sum=3"` |
| `"sum=" + 1 + 2` | Concatenates to a string at the first `+` | `"sum=12"` |

Interpreting `1 + 2 + "x"`: the first operation `1 + 2` is **numeric addition** giving `3`, and the next operation `3 + "x"` is **string concatenation** yielding `"3x"`.

Interpreting `"x" + 1 + 2`: the very first operation already has a `String`, producing `"x1"`; the next operation appends `2` to produce `"x12"`. There is no numeric addition `1 + 2` in this expression.

**Quick reading rule:** Walk through the `+` operations from left to right according to grammatical grouping; once an intermediate result is a `String`, subsequent `+` operations chained onto it will perform string concatenation, unless a subexpression is grouped separately to compute a number first.

## 3. Parentheses and operator precedence

The multiplication operator `*` has **higher precedence** than the addition/concatenation operator `+`. Parentheses `(...)` specify which operation must complete first.

~~~java
System.out.println("v=" + 2 * 3 + 4);   // v=64
System.out.println("v=" + (2 * 3 + 4)); // v=10
System.out.println("v=" + 2 + 3 * 4);   // v=212
~~~

Explanation:

- `"v=" + 2 * 3 + 4`: computes `2 * 3 = 6`; then `"v=" + 6 = "v=6"`; then appends `4` → `"v=64"`.
- `"v=" + (2 * 3 + 4)`: inside parentheses computes `6 + 4 = 10`, then concatenates → `"v=10"`.
- `"v=" + 2 + 3 * 4`: computes `3 * 4 = 12`; the remaining two addition/concatenation operations group from left to right → `"v=212"`.

Do not conflate **associativity** with **evaluation order of operands**. Java evaluates the operands of an operation from **left to right**, while still respecting the expression tree determined by precedence and parentheses. The runnable example below illustrates this with printed traces.

## 4. Runnable Java 17+ program

Create the file **PlusOrderDemo.java**:

~~~java
public final class PlusOrderDemo {
    private static int traced(String name, int value) {
        System.out.println("evaluate=" + name);
        return value;
    }

    public static void main(String[] args) {
        int a = 2;
        int b = 3;

        System.out.println("numeric=" + (a + b));
        System.out.println("direct=" + a + b);
        System.out.println("left=" + (1 + 2 + "x"));
        System.out.println("right=" + ("x" + 1 + 2));
        System.out.println("middle=" + (1 + "2" + 3));

        System.out.println("precedence=" + ("v=" + 2 * 3 + 4));
        System.out.println("grouped=" + ("v=" + (2 * 3 + 4)));

        System.out.println("charMath=" + ('A' + 1));
        System.out.println("charText=" + ("A=" + 'A' + 1));

        String label = "sum=";
        label += a + b;
        System.out.println("compound=" + label);

        String nullable = null;
        System.out.println("nullable=" + nullable);

        String result = "S" + traced("first", 2)
                + traced("second", 3);
        System.out.println("traceResult=" + result);
    }
}
~~~

Run in the directory containing the file (Bash, PowerShell, or Command Prompt):

~~~bash
javac -encoding UTF-8 PlusOrderDemo.java
java PlusOrderDemo
~~~

**Exact expected output:**

~~~text
numeric=5
direct=23
left=3x
right=x12
middle=123
precedence=v=64
grouped=v=10
charMath=66
charText=A=A1
compound=sum=5
nullable=null
evaluate=first
evaluate=second
traceResult=S23
~~~

**Explanation of key lines:**

1. `"numeric=" + (a + b)` performs numeric addition inside the parentheses to get 5, then concatenates; `"direct=" + a + b` concatenates each number to produce `"direct=23"`.
2. `char` participating in numeric addition can be **widened to `int`**: `'A' + 1` is `66` because the code of `'A'` is 65. However, `"A=" + 'A' + 1` concatenates sequentially, yielding `"A=A1"`.
3. With `label += a + b`, the right-hand side is the numeric expression `a + b` (value 5); the compound assignment operator concatenates onto the old string, resulting in `"sum=5"`. Compared with `label = label + a + b`, the two numbers would be concatenated one by one instead of added first.
4. Concatenating a `String` reference equal to `null` produces the text `"null"`, not a new `String` with value `null`.
5. The two `traced` calls execute in order `first` then `second`; then the results `2` and `3` are concatenated onto `"S"` to produce `"S23"`.

## 5. Easily confused situations

| Code / statement | Correct result |
| --- | --- |
| `System.out.println(5 + 6);` | Prints `11`, because both operands are numbers |
| `System.out.println("5" + 6);` | Prints `56`, because a `String` is present |
| `System.out.println(5 + 6 + "7");` | Prints `117` |
| `System.out.println("5" + (6 + 7));` | Prints `513` |
| `System.out.println('A' + 'B');` | Prints `131`: two `char`s are widened to numbers |
| `System.out.println("letters=" + 'A' + 'B');` | Prints `letters=AB`: string concatenation |
| `System.out.println("ratio=" + 7 / 2);` | Prints `ratio=3`: integer division runs before concatenation |
| `System.out.println("ratio=" + (7.0 / 2));` | Prints `ratio=3.5` |

### Overflow still happens before string concatenation

~~~java
int side = 50_000;
System.out.println("area=" + side * side);          // area=-1794967296
System.out.println("area=" + ((long) side * side)); // area=2500000000
~~~

The right-hand side `side * side` uses `int` and can overflow **before** being converted to text. String concatenation does not automatically make arithmetic wider or safer; if a calculation can exceed `int`, choose an appropriate operand type.

## 6. Writing to avoid bugs when mixing numbers into messages

- **Have an arithmetic calculation you want the reader to see clearly?** Put it in parentheses: `"total=" + (price * quantity)` or `"sum=" + (a + b)`.
- **Want to list multiple numbers side by side?** Use separators in the string: `"a=" + a + ", b=" + b`; otherwise `"a=" + a + b` easily produces ambiguous output.
- **Avoid overly long expressions** mixing many arithmetic `+` and string `+` operators. Put the sum into a clear numeric variable before formatting:
  
  ~~~java
  int total = a + b;
  System.out.println("total=" + total);
  ~~~
- **Use `String.format` when you need to format** multiple values or floating-point numbers, rather than relying on a long concatenation chain. Number formatting works independently of whether the arithmetic addition is right.
- **Remember the type of subexpressions:** parentheses do not automatically “cast to a number”; `("1" + "2")` is still `"12"` because both operands are strings.
- **Do not rely on compiler optimizations** to guess print order or side effects. Java preserves evaluation semantics in the specified order.

## 7. Quick exercises

**Exercise 1 — Predict the output.** Predict the four results: `1 + 2 + "3"`, `"1" + 2 + 3`, `"1" + (2 + 3)`, `2 * 3 + "4"`. Explain at each `+` why it is numeric addition or string concatenation.

**Exercise 2 — Fix the message.** Given `int a = 10, b = 20;`, why does `System.out.println("Total=" + a + b);` print `Total=1020`? Fix it to print `Total=30` without changing the values of `a` or `b`.

**Exercise 3 — `char` and numbers.** Predict the results of `'A' + 2` and `"A" + 2`, distinguishing character code addition from string concatenation.

**Exercise 4 — Execution trace.** Replace `"S" + traced("first", 2) + traced("second", 3)` with `traced("first", 2) + traced("second", 3) + "S"`. Do the two `evaluate=...` lines change order? Does the result of the addition change?

**Exercise 5 — Practical scenario.** Write a total-amount message from quantity and unit price so that multiplication happens before string concatenation; state the appropriate data type if intermediate values may exceed `int`.

### Key takeaway

**The `+` sign is numeric addition when applied to numeric operands, and string concatenation when a `String` is present.** `+` operators of equal precedence are grouped **from left to right**; parentheses and higher-precedence operators determine which calculations happen before concatenation. When you want a numeric expression computed separately, write `"label=" + (a + b)`, not `"label=" + a + b`.
