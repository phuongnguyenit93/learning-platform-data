# Operator Precedence and Associativity in Java

> **Java core — language-basics / Expressions**  
> **Environment:** JDK 17+, Java standard library only.  
> **Objective:** Correctly read how Java groups expressions based on **precedence** and **associativity**, distinguish them from **evaluation order**, and use parentheses to make code intent clear.

## 1. Three Distinct Concepts

Given the expression:

~~~java
int result = 2 + 3 * 4;
~~~

The result is **14**, not 20, because `*` has higher precedence than `+`: the expression is interpreted as `2 + (3 * 4)`.

Distinguish three rules:

- **Precedence:** Without parentheses, an operator at a higher precedence level binds to its operands first. For example, `a + b * c` is grouped as `a + (b * c)`.
- **Associativity:** When multiple operators are at the same precedence level, associativity rules determine **grouping**. For example, `a - b - c` groups from the left: `(a - b) - c`; whereas `a = b = c` groups from the right: `a = (b = c)`.
- **Evaluation order:** Java evaluates operands from **left to right** (with special rules for conditional-evaluation operators). This **does not mean** Java always computes the leftmost operator first.

Example with parentheses:

~~~java
int first = 2 + 3 * 4;   // 14
int second = (2 + 3) * 4; // 20
~~~

Parentheses change **grouping**, saving the reader from having to memorize the entire precedence table.

## 2. Precedence Table of Common Operators

Table ordered from **highest → lowest**. This is a learning reference for common expressions in Java 17; certain special syntactic constructs (such as lambdas) are not treated as arithmetic operations in the table.

| Level | Group/operator | Associativity or notes |
| --- | --- | --- |
| 1 (highest) | Access `.`, `[]`, invocation `()`, postfix `x++`, `x--` | Binds to receiver expression/operand |
| 2 | Prefix `++x`, `--x`, `+x`, `-x`, `!`, `~`, cast `(Type) x` | Unary operators, right-associative |
| 3 | `*`, `/`, `%` | Left → right |
| 4 | `+`, `-` | Left → right; `+` can also concatenate strings |
| 5 | `<<`, `>>`, `>>>` | Left → right |
| 6 | `<`, `<=`, `>`, `>=`, `instanceof` | Comparison/type test |
| 7 | `==`, `!=` | Equality/inequality |
| 8 | `&` | Bitwise AND or non-short-circuit boolean AND |
| 9 | `^` | Bitwise XOR or boolean XOR |
| 10 | `\|` | Bitwise OR or non-short-circuit boolean OR |
| 11 | `&&` | Logical AND, short-circuit |
| 12 | `\|\|` | Logical OR, short-circuit |
| 13 | `? :` | Conditional operator, right-associative |
| 14 (lowest) | `=`, `+=`, `-=`, `*=`, `/=`, etc. | Assignment operators, right-associative |

**Quick-reference example:**

~~~java
boolean ok = 3 + 2 > 4 && 2 * 3 == 6;
// Equivalent grouping:
// boolean ok = ((3 + 2) > 4) && ((2 * 3) == 6);
// ok = true.
~~~

`==` has **higher** precedence than boolean `&` and `&&`. In turn, `&&` has **higher** precedence than `||`. For complex expressions, add parentheses to match business intent instead of relying on intuition.

**Note on `<<`:** `1 + 2 << 2` groups as `(1 + 2) << 2`, so the result is **12**, not `1 + (2 << 2)` (9).

## 3. Associativity: Which Way Do Same-Level Operators Group?

Common binary arithmetic operators such as `+`, `-`, `*`, `/` group **left → right** when at the same level:

~~~java
int a = 20 / 5 * 2;     // (20 / 5) * 2 = 8.
int b = 20 / (5 * 2);   // 20 / 10 = 2.
int c = 10 - 3 - 2;     // (10 - 3) - 2 = 5.
~~~

Associativity matters especially when operators are **not mathematically commutative or associative in the relevant sense**, such as subtraction, division, string concatenation, and operations that can overflow.

Conversely, **assignment is right-associative**:

~~~java
int x, y;
x = y = 7; // x = (y = 7), finally x == 7 and y == 7.
~~~

Nested conditional expressions also group from the right:

~~~java
int selected = false ? 10 : true ? 20 : 30;
// Grouped as: false ? 10 : (true ? 20 : 30)
// selected = 20.
~~~

**Be careful:** Associativity determines **syntactic structure**, not which method call runs first if operands have side effects. Java's evaluation order rules must still be considered separately.

## 4. Operator Grouping Does Not Reverse Method Call Order

In `left() + middle() * right()`, multiplication is grouped inside the right operand of addition; however, Java evaluates `left()`, then `middle()`, then `right()` when no exception occurs. Not all sides necessarily run: `&&`, `||`, and `?:` have rules that skip branches.

~~~java
static int mark(StringBuilder log, String name, int value) {
    log.append(name);
    return value;
}
// Inside a method:
StringBuilder log = new StringBuilder();
int result = mark(log, "A", 1) + mark(log, "B", 2) * mark(log, "C", 3);
// result = 7; log.toString() = "ABC"
~~~

The precedence table above determines the **grouping tree**; an execution trace determines **evaluation order**. These two checks are independent.

## 5. Logical Operators: Precedence and Short-Circuiting

`&&` has higher precedence than `||`, so:

~~~java
boolean value = true || false && false;
// Grouped as: true || (false && false)
// value = true.
~~~

With `&&`, if the left side is false, Java **does not run the right side**. With `||`, if the left side is true, Java **does not run the right side**:

~~~java
int zero = 0;
boolean noDivide = false && (10 / zero > 1); // false, no division by 0.
boolean noDivideEither = true || (10 / zero > 1); // true.
~~~

In contrast, boolean `&` and `|` **do not short-circuit**: they evaluate both sides. For example, `false & (10 / zero > 1)` throws `ArithmeticException` due to division by zero.

**Choose the operator according to intent:**

| Intent | Operator | Evaluates right side? |
| --- | --- | --- |
| Logical AND, skip second side when false | `&&` | Only if left side is true |
| Logical OR, skip second side when true | `\|\|` | Only if left side is false |
| Boolean AND requiring both to be evaluated | `&` | Always |
| Boolean OR requiring both to be evaluated | `\|` | Always |

When checking for `null`, the guard order must be right:

~~~java
String name = null;
boolean valid = name != null && !name.isBlank(); // false, safe.
// boolean bad = !name.isBlank() && name != null; // NPE.
~~~

## 6. Common Expression Traps

| Expression | Correct interpretation |
| --- | --- |
| `1 + 2 << 2` | `(1 + 2) << 2` = 12 |
| `10 - 3 - 2` | `(10 - 3) - 2` = 5 |
| `20 / 5 * 2` | `(20 / 5) * 2` = 8 |
| `true \|\| false && false` | `true \|\| (false && false)` = true |
| `1 \| 2 & 3` | `1 \| (2 & 3)` = 3 |
| `"sum=" + 1 + 2` | Left → right string concatenation = `"sum=12"` |
| `"sum=" + (1 + 2)` | Add numbers in parentheses first = `"sum=3"` |
| `false ? 10 : true ? 20 : 30` | `false ? 10 : (true ? 20 : 30)` = 20 |

Parentheses both prevent bugs and document the programmer's intent. However, do not sprinkle parentheses indiscriminately into expressions with many side effects assuming it will reverse function call evaluation order.

## 7. Runnable Java 17+ Program

Create the file **OperatorPrecedenceDemo.java**:

~~~java
public final class OperatorPrecedenceDemo {
    private static int mark(StringBuilder order, String label, int value) {
        order.append(label);
        return value;
    }

    public static void main(String[] args) {
        System.out.println("precedence=" + (2 + 3 * 4));
        System.out.println("parentheses=" + ((2 + 3) * 4));
        System.out.println("leftAssociative=" + (20 / 5 * 2));
        System.out.println("rightGrouped=" + (20 / (5 * 2)));
        System.out.println("subtraction=" + (10 - 3 - 2));
        System.out.println("shift=" + (1 + 2 << 2));
        System.out.println("relational="
                + (3 + 2 > 4 && 2 * 3 == 6));
        System.out.println("andOr=" + (true || false && false));
        System.out.println("bitwise=" + (1 | 2 & 3));

        StringBuilder order = new StringBuilder();
        int evaluated = mark(order, "A", 1)
                + mark(order, "B", 2) * mark(order, "C", 3);
        System.out.println("operandOrder=" + order);
        System.out.println("operandValue=" + evaluated);

        int zero = 0;
        boolean shortAnd = false && (10 / zero > 1);
        boolean shortOr = true || (10 / zero > 1);
        System.out.println("shortCircuit=" + shortAnd + "," + shortOr);

        try {
            boolean evaluatedBoth = false & (10 / zero > 1);
            System.out.println("eagerResult=" + evaluatedBoth);
        } catch (ArithmeticException ex) {
            System.out.println("eagerAndThrows=true");
        }

        int x, y;
        x = y = 7;
        System.out.println("assignment=" + x + "," + y);

        int selected = false ? 10 : true ? 20 : 30;
        System.out.println("conditional=" + selected);

        System.out.println("concat=" + ("" + 1 + 2)
                + "," + (1 + 2));
    }
}
~~~

Compile/run in the folder containing the file (Bash, PowerShell, or Command Prompt):

~~~bash
javac -encoding UTF-8 OperatorPrecedenceDemo.java
java OperatorPrecedenceDemo
~~~

**Exact expected output:**

~~~text
precedence=14
parentheses=20
leftAssociative=8
rightGrouped=2
subtraction=5
shift=12
relational=true
andOr=true
bitwise=3
operandOrder=ABC
operandValue=7
shortCircuit=false,true
eagerAndThrows=true
assignment=7,7
conditional=20
concat=12,3
~~~

The line `operandOrder=ABC` illustrates **left-to-right call execution order**, even though `*` has higher precedence than `+`. `eagerAndThrows=true` shows the difference between `&` and `&&` for boolean operands. `assignment=7,7` and `conditional=20` illustrate **right-associative grouping**.

## 8. Exercises and Readability Guidelines

**Exercise 1.** Evaluate `5 + 2 * 3` and `(5 + 2) * 3`. Explain why the results differ.

**Exercise 2.** Evaluate `24 / 4 / 2` and `24 / (4 / 2)`. Which direction does the `/` operator associate?

**Exercise 3.** Predict `1 + 2 << 2`. Rewrite it with parentheses so no precedence table lookup is needed.

**Exercise 4.** Given `int z = 0;`. Predict the behavior of `false && (10 / z > 0)`, `true || (10 / z > 0)`, and `false & (10 / z > 0)`.

**Exercise 5.** Write `int a, b; a = b = 5;` and explain why right-associative assignment does not mean all operands in general are executed from right to left.

**Exercise 6.** Use a logging or name-printing helper in three operands to prove that `methodA() + methodB() * methodC()` calls the methods in order A, B, C.

**Guideline:** In long mathematical or logical formulas, place parentheses wherever **the intended grouping of an expression should be made explicit**. Do not rely on "reading left to right" to determine precedence; also avoid confusing precedence/associativity with the execution order of calls that have side effects.

### Takeaways

**Precedence** determines how operators of different levels group; **associativity** determines how operators of the same level group; Java's **evaluation order** is a separate rule, normally evaluating operands from left to right. `&&`/`||` and `?:` can skip branches that do not need evaluation. Use parentheses to make intent clear, especially when mixing arithmetic, bit shifts, comparisons, logic, and assignments.
