# Operands, Operators, and Nested Expressions — Java 17+

An **expression** in Java is a construct that can be evaluated to produce a **value** or variable (in certain cases), perform an assignment, or cause side effects. To read complex expressions accurately, three concepts must be distinguished:

- **Operand**: the piece of data an operator acts upon, such as the literal `5`, variable `price`, call `getPrice()`, or **a sub-expression**.
- **Operator**: the symbol or construct performing an operation, such as `+`, `*`, `!`, `&&`, `?:`, `=`.
- **Nested expression**: an expression used as an operand inside a larger expression, optionally grouped with parentheses to make intent clear.

~~~java
int total = 8 + 3 * 2;
~~~

In the expression `8 + 3 * 2`, `8`, `3`, and `2` are simple operands; `+` and `*` are operators. Because `*` has higher precedence than `+`, the expression is **grouped** as `8 + (3 * 2)` and evaluates to **14**.

**Key point:** *precedence determines how operands are grouped*, whereas *evaluation order* determines when the parts are executed. These are two distinct concepts in Java.

## 1. Forms of Operands and Operators

| Form | Example expression | Explanation |
| --- | --- | --- |
| Literal | `42`, `true`, `"Java"` | Value written directly |
| Variable | `quantity` | Reads the variable's value |
| Method invocation | `name.length()` | Result of a method with an appropriate return type |
| Element access | `scores[0]` | Value at an array index |
| Unary operator | `-x`, `!enabled`, `++n` | One operand |
| Binary operator | `a + b`, `a * b`, `x > y` | Two operands |
| Ternary conditional operator | `condition ? a : b` | Three parts: condition and two branches |
| Assignment | `x = 10`, `x += 2` | Has an expression value and performs assignment |
| Cast | `(double) sum` | Converts an expression's type |
| Nested | `(a + b) * (c - d)` | Sub-expressions acting as operands |

A **literal** like `7` is already a simple expression; not every expression needs an operator. Conversely, a **statement** such as `if (...) { ... }` is a control-flow construct, not a value-bearing operand that can be substituted directly into an addition.

## 2. Grouping Expressions and Parentheses

Read two expressions with the same numbers but different grouping:

~~~java
int a = 8 + 3 * 2;     // 14.
int b = (8 + 3) * 2;   // 22.
~~~

You can visualize the expression trees:

~~~text
8 + 3 * 2             (8 + 3) * 2

       +                     *
      / \                   / \
     8   *                 +   2
        / \               / \
       3   2             8   3
~~~

Grouped according to the tree on the left: `3 * 2` is an operand of `+`. Grouped according to the tree on the right: `8 + 3` is an operand of `*`.

Parentheses can **change the grouping** or simply make the existing grouping **easier to read**:

~~~java
int a = 8 + 3 * 2;          // 14.
int b = 8 + (3 * 2);        // 14: clearer grouping, value unchanged.
int c = (8 + 3) * 2;        // 22: changes the grouping.
~~~

However, parentheses do **not** change data type rules. For instance, `(5 / 2)` still performs integer division and returns `2`; to get `2.5` you must have a floating-point operand, such as `5 / 2.0`.

## 3. Read the Grouping Tree First, Trace Evaluation Second

Precedence and associativity determine which sub-expression is an operand of a larger operator. For example, `20 - 5 - 3` groups as `(20 - 5) - 3` and evaluates to 12; `a = b = 7` groups as `a = (b = 7)`.

Do not confuse that structure with **method call order**. In `first() + second() * third()`, multiplication is the right branch of addition, yet the calls (when all complete normally) run in order `first`, `second`, `third`. In `left && right`, Java can even skip `right`. Therefore, when reading nested expressions, draw the **operator grouping** tree first and only then trace the evaluation order of each branch's operands.

## 4. Runnable Java 17+ Program

Create a UTF-8 file named **`NestedExpressionsDemo.java`**:

~~~java
public class NestedExpressionsDemo {
    static int mark(String label, int value) {
        System.out.println("visit=" + label);
        return value;
    }

    static boolean check(String label, boolean value) {
        System.out.println("check=" + label);
        return value;
    }

    public static void main(String[] args) {
        int x = 8;
        int y = 3;

        System.out.println("precedence=" + (x + y * 2));
        System.out.println("parentheses=" + ((x + y) * 2));
        System.out.println("nested=" + ((x + (y * 2)) - (x / y)));
        System.out.println("remainder=" + (x % y));
        System.out.println("unary=" + (-x + y));
        System.out.println("leftAssociative=" + (20 - 5 - 3));

        boolean comparison = (x + y * 2) > 10;
        System.out.println("comparison=" + comparison);
        System.out.println("logical=" + ((x > y) && (y > 0)));
        System.out.println("ternary=" + (x > y ? x - y : y - x));

        System.out.println("stringUngrouped=" + 1 + 2);
        System.out.println("stringGrouped=" + (1 + 2));
        System.out.println("integerDivision=" + ((x + y) / 4));
        System.out.println("decimalDivision=" + ((x + y) / 4.0));

        int order = mark("left", 2)
                + mark("middle", 3) * mark("right", 4);
        System.out.println("orderResult=" + order);

        boolean shortcut = check("first", true)
                || check("skipped", false);
        System.out.println("orResult=" + shortcut);

        int divisor = 0;
        boolean safe = (divisor != 0) && (x / divisor > 1);
        System.out.println("safeDivision=" + safe);

        int count = 4;
        int assigned = (count += 3) * 2;
        System.out.println("assignmentValue=" + assigned);
        System.out.println("countAfterAssignment=" + count);

        int n = 5;
        int post = n++ + 2;
        System.out.println("postResult=" + post);
        System.out.println("nAfterPost=" + n);

        int a;
        int b;
        a = b = 7;
        System.out.println("chainedAssignment=" + a + "," + b);
    }
}
~~~

Open PowerShell (Windows) or Bash (Linux/macOS) in the folder containing the file, using **JDK 17+**:

~~~bash
java -version
javac -version
javac -encoding UTF-8 NestedExpressionsDemo.java
java NestedExpressionsDemo
~~~

**Exact expected output** of `java NestedExpressionsDemo`:

~~~text
precedence=14
parentheses=22
nested=12
remainder=2
unary=-5
leftAssociative=12
comparison=true
logical=true
ternary=5
stringUngrouped=12
stringGrouped=3
integerDivision=2
decimalDivision=2.75
visit=left
visit=middle
visit=right
orderResult=14
check=first
orResult=true
safeDivision=false
assignmentValue=14
countAfterAssignment=7
postResult=7
nAfterPost=6
chainedAssignment=7,7
~~~

The two commands `java -version` and `javac -version` display the version on the machine being used and are not part of the fixed stdout block above.

### Reading the Output by Group

**Arithmetic group:** `x + y * 2` equals `8 + 6 = 14`, whereas `(x + y) * 2` equals `11 * 2 = 22`. The nested expression `(x + (y * 2)) - (x / y)` equals `14 - 2 = 12` because `8 / 3` is `int` division.

**Comparison and logical group:** the `>` operator yields a `boolean` result; `&&` combines two boolean values; `?:` evaluates only the selected branch. Since `x > y` is true, the ternary result is `x - y = 5`.

**String group:** `"stringUngrouped=" + 1 + 2` is evaluated via left-to-right concatenations, producing `"stringUngrouped=12"`. `"stringGrouped=" + (1 + 2)` forces numeric addition first, producing `"stringGrouped=3"`. The `+` operator can be numeric addition **or string concatenation**, depending on operand types.

**Evaluation order group:** even though multiplication has higher precedence than addition, `mark("left", 2)` runs first, then `mark("middle", 3)`, and then `mark("right", 4)`. The `visit=...` lines in the output demonstrate the evaluation sequence of operands in `a() + b() * c()`.

**Short-circuit group:** with `||`, once the left operand is true, `check("skipped", false)` is **not called**; thus only `check=first` appears. With `&&`, when `divisor != 0` is false, Java does not evaluate `x / divisor > 1`, avoiding division by zero. Do not rely on this trick if a variable may be mutated concurrently without proper synchronization.

**Side-effect group:** `count += 3` both updates `count` from 4 to 7 and evaluates to 7; multiplying by 2 gives `assigned = 14`. `n++` uses the old value 5 in the expression and then increments the variable to 6; `post = 5 + 2 = 7`.

## 5. Analyzing an Expression in Three Steps

When encountering a long expression, follow this process:

1. **Identify the operands**: literals, variables, method calls, element accesses, or nested expressions.
2. **Group by parentheses, precedence, and associativity**: determine the expression tree and the result type of each part.
3. **Trace runtime evaluation**: check operand order, short-circuiting, chosen conditional branch, and side effects.

Example `(price + tax) * quantity >= minimum && active`:

~~~text
                     &&
                    /  \
                  >=   active
                 /  \
                *  minimum
               / \
              + quantity
             / \
          price tax
~~~

For valid Java typing, assume `price`, `tax`, `quantity`, and `minimum` have compatible numeric types and `active` is `boolean`. The sub-expression on the left of `>=` has type `boolean`; the entire `&&` also has type `boolean`. If the left side of `&&` is false, `active` does not need to be evaluated.

The diagram shows only **grouping**, not a schedule of individual calls or side effects inside the expression.

## 6. Types of Individual Sub-Expressions

Nesting does not bypass type rules: every node of the expression tree still requires operands of the proper type. For example:

~~~java
int a = 5, b = 2;
boolean ok = (a + b) > 6 && b != 0; // true
~~~

`a + b` has type `int`; `> 6` and `b != 0` both have type `boolean`; the result of `&&` is also `boolean`. Parentheses around `(a + b)` only group the operation, not turn it into `double`; Java does not implicitly convert `0` to `false` as some other languages do.

## 7. Grouping Does Not Replace Type and Range Checks

~~~java
int price = 50_000, units = 50_000;
long overflowed = (long) (price * units); // Multiplies ints first, already overflowed
long safeSize = (long) price * units;      // Multiplies as long, result 2500000000
~~~

The grouping tree shows where multiplication sits, but it does not automatically widen numeric types or check for overflow. To avoid data loss, convert the type **before** the operation or use an appropriate overflow check. For calls with side effects, consider extracting operands into named variables for easier inspection.

## 8. Common Mistakes and How to Spot Them

| Misconception | Reality |
| --- | --- |
| "The `*` operator has high precedence, so calls in the multiplication side always run first." | Precedence determines **grouping**, not reversing Java's operand evaluation order |
| "`(5 / 2)` gives a floating-point result because it has parentheses." | Parentheses do not turn `int` into `double` |
| "`"x=" + 1 + 2` gives `x=3`." | Concatenates strings left to right, giving `x=12` |
| "`(a && b)` always evaluates both sides." | `&&` short-circuits when the left side is false |
| "`a || b` always calls `b`." | `||` skips `b` if `a` is already true |
| "`(n += 1)` is not a value-producing expression." | Assignment has a value and updates the variable |
| "`n++` and `++n` always give the same value inside an expression." | Postfix uses the old value; prefix uses the new value |
| "Adding parentheses always prevents arithmetic overflow." | Parentheses do not widen numeric ranges or check overflow |

## 9. Self-Check Exercises

1. **Precedence:** What are `2 + 3 * 4` and `(2 + 3) * 4`, respectively?  
   *Answer:* 14 and 20.
2. **Associativity:** What is `20 - 5 - 3`?  
   *Answer:* 12, grouped as `(20 - 5) - 3`.
3. **String concatenation:** How does `"n=" + 1 + 2` differ from `"n=" + (1 + 2)`?  
   *Answer:* `"n=12"` and `"n=3"`.
4. **Short-circuiting:** Does `int d = 0; boolean ok = d != 0 && 10 / d > 1;` divide by 0?  
   *Answer:* No, the right side of `&&` is skipped when the first condition is false.
5. **Postfix increment:** In `int n = 4; int r = n++ + 2;`, what are `r` and `n` at the end?  
   *Answer:* `r = 6` and `n = 5`.
6. **Result type:** What value does `double x = 5 / 2;` have?  
   *Answer:* `2.0`; to get `2.5`, use `5 / 2.0` or an appropriate cast.
7. **Evaluation order:** In `first() + second() * third()`, if all functions return numbers and print a trace, in what order do the calls occur?  
   *Answer:* `first()`, then `second()`, then `third()`.

## Checklist

- [ ] Identify **operands**, **operators**, and **sub-expressions**.
- [ ] Separate **grouping from precedence/associativity** from **operand evaluation order**.
- [ ] Use parentheses to clarify intent, without assuming parentheses change data types.
- [ ] Understand that `&&`/`||`/`?:` can skip evaluating a branch.
- [ ] Track intermediate types and values, especially integer division and numbers that may overflow.
- [ ] Be careful with side effects from `=`, `+=`, `++`, and method calls inside expressions.
- [ ] When an expression gets too long, consider naming intermediate steps for easier inspection.

**Conclusion:** Read Java expressions by identifying **the operands**, **the operators connecting them**, **the grouping tree of nested expressions**, and **the actual evaluation order**. This approach helps avoid precedence mistakes, wrong result types, and hard-to-spot side effects.
