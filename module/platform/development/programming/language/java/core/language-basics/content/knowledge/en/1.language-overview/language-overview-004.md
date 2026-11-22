# Data, Expressions, Statements, and Control Flow

## 1. Four Concepts That Form a Java Program

A Java program takes **data**, uses **expressions** to compute or compare, uses **statements** to perform actions, and follows **execution flow** to determine which parts of the code run and how many times.

For example:

~~~java
int price = 80;
int quantity = 2;
int total = price * quantity;

if (total >= 100) {
    System.out.println("Đơn hàng lớn");
}
~~~

- `80` and `2` are **literal values**; `price`, `quantity`, and `total` are variables of type `int`.
- `price * quantity` is an **expression**: when evaluated, it produces the value `160`.
- `int total = price * quantity;` is a **local variable declaration statement** with an initializer expression.
- `total >= 100` is an expression of type `boolean`, used by `if` to decide whether to run the block that prints the message.
- The `{ }` braces delimit a **block**; the statements inside the block execute only when the condition applies.

The main relationship can be visualized as:

~~~mermaid
flowchart TD
    DATA["Data and variables"] --> EXP["Evaluate expressions"]
    EXP --> STMT["Execute statements"]
    STMT --> DEC{"Condition / loop?"}
    DEC -->|"True or continue looping"| STMT
    DEC -->|"False / finished"| END["Next statement<br/>or end of method"]
~~~

This diagram is a simplified conceptual model; a statement can contain **multiple** expressions, an expression can have side effects, and constructs such as `return`, `break`, `continue`, or exceptions can transfer control elsewhere.

## 2. Data: Values, Types, and Variables

### Basic Data Types

Java is a **statically typed** language: every variable and expression has a type checked by the compiler. The eight primitive types include:

| Type | Meaning and Example | Notes |
|---|---|---|
| `byte`, `short`, `int`, `long` | Integers: `int age = 20;`, `long id = 123L;` | Bounded value ranges; integers are not infinite |
| `float`, `double` | Floating-point numbers: `double rate = 0.15;` | Subject to representation error and special values |
| `char` | A **UTF-16 code unit**: `char mark = 'A';` | Not identical to every complete Unicode character |
| `boolean` | `true` or `false` | Does not implicitly convert to `0`/`1` as in some other languages |

`String`, arrays such as `int[]`, and other objects are **reference types**. A reference variable can hold a reference to an object or `null`, rather than containing the entire object directly the way a primitive variable holds its value:

~~~java
int count = 3;
String label = "Java";
int[] points = {10, 20, 30};
String missing = null;
~~~

`label.length()` works when `label` is non-null, whereas `missing.length()` throws `NullPointerException` at runtime. The static type `String` does not guarantee that the reference is never null.

### Literals, Inferred Types, and Assignment

~~~java
int units = 10;
long population = 8_000_000_000L;
double ratio = 0.25;
boolean active = true;
char grade = 'A';
String city = "Ha Noi";

units = units + 5;
final int MAX_ITEMS = 20;
~~~

Integer literals like `10` normally have type `int`, except in certain contexts or with an appropriate literal suffix; `L` marks a `long` literal. Underscores in `8_000_000_000L` improve readability without changing the value. `final` on a variable forbids **reassigning the variable** after it has been assigned, though if it holds a reference to a mutable object, that does not mean the object's internal state is immutable.

In Java 10+, local variables can use `var` when a suitable initializer is present:

~~~java
var score = 10;     // Inferred as int at compile time
var message = "Hi"; // Inferred as String
~~~

`var` does not turn Java into a dynamically typed language: the inferred type remains fixed. You cannot write `var unknown = null;` as a local variable because the compiler cannot infer a suitable type from a standalone `null` literal.

### Assignment Is Not Comparison

- `=` **assigns** the value on the right-hand side to a valid variable/storage location on the left-hand side.
- `==` **compares** two operands; for primitives it generally compares values; for two object references it compares whether they are the **same reference**.
- `"abc".equals(other)` checks contents according to `String`'s contract; you should not use `==` to check whether two strings have the same characters.

~~~java
String a = new String("Java");
String b = new String("Java");
System.out.println(a == b);      // false: two different objects
System.out.println(a.equals(b)); // true: identical contents
~~~

## 3. What Is an Expression?

An **expression** is evaluated to produce **a value or result** and has a type. An expression can be a literal, a variable name, an arithmetic operation, a method call with a return type, a comparison, an assignment, or a conditional expression.

| Expression | Type/Result (assuming valid variables) | Purpose |
|---|---|---|
| `42` | `int` / 42 | Literal |
| `price * quantity` | Number computed from two operands | Arithmetic |
| `score >= 60` | `boolean` | Condition |
| `ready && hasTicket` | `boolean` | Combining conditions |
| `isMember ? 90 : 100` | Number chosen based on condition | Conditional expression |
| `"Hi".length()` | `int` / 2 | Method call |
| `x += 2` | Assignment yielding a result value | Updating a variable |

Not every expression is allowed to stand alone as an **expression statement** in Java. Valid ones include, for example:

~~~java
int x = 3;
x++;                     // increment statement
x = x + 2;               // assignment statement
System.out.println(x);   // method invocation statement
new StringBuilder();     // class instance creation statement
~~~

However, a bare calculation `x + 2;` **is not a valid statement**: the computed value is unused, and Java does not allow arbitrary expressions to stand alone as statements.

A method call returning `void`, such as `System.out.println("Hi")`, is used in a method invocation statement, but does not produce a `void` value that can be assigned to a variable.

## 4. Operators, Precedence, and Evaluation Order

Important operator groups:

| Group (from higher to lower precedence, simplified) | Examples |
|---|---|
| Postfix, invocation, and access | `x++`, `arr[i]`, `obj.method()` |
| Unary | `++x`, `-x`, `!valid` |
| Multiplication/division/remainder | `*`, `/`, `%` |
| Addition/subtraction | `+`, `-` |
| Relational ordering | `<`, `<=`, `>`, `>=` |
| Equality/inequality | `==`, `!=` |
| Short-circuit logical AND | `&&` |
| Short-circuit logical OR | `||` |
| Ternary conditional | `condition ? a : b` |
| Assignment | `=`, `+=`, `-=`, ... |

This table intentionally omits shift, bitwise, and several intermediate groups. **Use parentheses** when you want to make intent clear, instead of trying to memorize the entire precedence table.

~~~java
int a = 2 + 3 * 4;      // 14
int b = (2 + 3) * 4;    // 20
boolean ok = a > 10 && b == 20; // true
~~~

**Three rules that must not be confused:**

1. **Precedence** determines how operators are grouped: `2 + 3 * 4` is `2 + (3 * 4)`.
2. Java's **operand evaluation order** is generally **left to right** across an expression, except when an operand is skipped due to short-circuit rules or conditional branches. Do not use the precedence table to assume a method call on the right always happens before one on the left.
3. **Short-circuiting**: `&&` does not evaluate the right-hand side when the left-hand side is `false`; `||` does not evaluate the right-hand side when the left-hand side is `true`.

A safe example:

~~~java
String input = null;
boolean valid = input != null && !input.isBlank();
System.out.println(valid); // false; does not call input.isBlank()
~~~

If you change `&&` to `&` with two boolean expressions, both sides are evaluated and the example above will throw `NullPointerException`. The two operators **have the same logical truth table in many cases, yet differ in evaluation behavior**.

### Side Effects in Expressions

~~~java
int x = 5;
int old = x++; // old = 5, then x = 6
int now = ++x; // increment x to 7, now = 7
~~~

`x++` returns the value **before incrementing**, whereas `++x` returns the value **after incrementing**. Avoid mixing multiple increments or side-effecting method calls inside a single hard-to-read expression; split them into simple statements for easier verification.

Left-to-right evaluation example:

~~~java
static int logAndReturn(String label, int value) {
    System.out.println(label);
    return value;
}

// Place the following call inside a method:
int sum = logAndReturn("trai", 2) + logAndReturn("phai", 3);
// Prints "trai", then "phai"; sum = 5
~~~

## 5. Arithmetic: Edge Cases That Easily Cause Bugs

### Integer Division and Remainder

~~~java
System.out.println(7 / 2);   // 3, because both are int
System.out.println(7.0 / 2); // 3.5
System.out.println(7 % 2);   // 1
System.out.println(-7 / 2);  // -3: truncated toward 0
System.out.println(-7 % 2);  // -1
~~~

If you want a fractional part, you must have a `double`/`float` operand or an appropriate cast. Casting **after** integer division is too late: `(double) (7 / 2)` is `3.0`, whereas `(double) 7 / 2` is `3.5`.

### Integer Overflow

~~~java
int max = Integer.MAX_VALUE;
System.out.println(max + 1); // -2147483648 (int overflow)
~~~

Normal `int` addition can overflow according to Java arithmetic rules. If business rules **forbid overflow**, use `Math.addExact(a, b)` to get an `ArithmeticException` when the result exceeds the range, or choose a suitable representation for large numbers.

### Division by Zero and Floating-Point Numbers

~~~java
// int broken = 10 / 0; // Integer division by 0 causes ArithmeticException when executed
System.out.println(1.0 / 0.0); // Infinity
System.out.println(0.0 / 0.0); // NaN
System.out.println(0.1 + 0.2); // Typically displays 0.30000000000000004
~~~

Floating-point `double` numbers follow IEEE 754 binary representation with precision limitations. Do not carelessly use `==` comparison on decimal calculation results; when working with money, consider **integers in the smallest unit** or `BigDecimal` with defined rounding rules.

## 6. Statements and Blocks: What Does the Program Actually Do?

A **statement** instructs Java to perform an action, potentially using expression results to control the next step. Common kinds include:

- Local variable declaration: `int total = 0;`.
- Expression statement: `total += price;`, `printResult();`.
- Block: `{ ... }`.
- Branching: `if / else`, `switch`.
- Looping: `for`, `while`, `do-while`.
- Flow control transfer: `break`, `continue`, `return`, `throw`.

Block and variable scope example:

~~~java
int outside = 10;
if (outside > 0) {
    int inside = outside * 2;
    System.out.println(inside); // 20
}
// System.out.println(inside); // Compile error: outside scope
~~~

A local variable must be **definitely assigned before being read** according to the compiler's analysis (*definite assignment*). For example:

~~~java
boolean passed = true;
String status;
if (passed) {
    status = "PASS";
} else {
    status = "FAIL";
}
System.out.println(status); // valid: both branches assign
~~~

If you remove the `else` branch so that `status` might remain unassigned, the compiler will refuse to let you read it. Unlike **instance fields**, which receive default values when an object is created, local variables are not automatically given a default value to be read arbitrarily.

## 7. Branching: `if`, `else`, and `switch`

### `if / else if / else`

~~~java
int score = 75;
if (score >= 90) {
    System.out.println("Xuat sac");
} else if (score >= 60) {
    System.out.println("Dat");
} else {
    System.out.println("Chua dat");
}
// Prints "Dat"
~~~

The `if` condition must be `boolean` or a compatible unboxed type; Java **does not** automatically treat `0`, `1`, or an empty string as `false`/`true`. Always use curly braces even for a single statement to avoid bugs when adding branches or editing code.

### `switch` Statement and `switch` Expression

Java 17 supports `switch` syntax with arrow labels:

~~~java
String mode = "FAST";
int timeout = switch (mode) {
    case "FAST" -> 3;
    case "NORMAL" -> 10;
    default -> 20;
};
System.out.println(timeout); // 3
~~~

This is a **switch expression** because the entire `switch` produces a value assigned to `timeout`. With a `switch` statement, the main goal is choosing and executing a branch of statements rather than necessarily producing a value.

Compared to the traditional `case ...:` form, arrow `->` branches do not automatically **fall through** to the next branch. A switch expression must cover all valid cases; `default` in the example makes it clear when the string has a value outside the two listed cases.

`switch` does not replace every `if`: use it when the “choose among multiple cases” model makes more sense than arbitrary conditions.

## 8. Loops: `for`, `while`, `do-while`

### `for` When Stepping by Index

~~~java
int total = 0;
for (int i = 1; i <= 3; i++) {
    total += i;
}
System.out.println(total); // 6
~~~

Sequence: run the initialization `i = 1` once → check `i <= 3` → run loop body → run update `i++` → check again. If the initial condition is false, the body may **not run at all**.

### Enhanced `for` for Iterating Over Elements

~~~java
int[] values = {2, 4, 6};
int sum = 0;
for (int value : values) {
    sum += value;
}
System.out.println(sum); // 12
~~~

Enhanced `for` is simple when you only need each element, though it does not automatically give you the index. Changing the local variable `value` is not a way to modify an `int` element directly inside the array.

### `while` and `do-while`

~~~java
int n = 3;
while (n > 0) {
    System.out.print(n + " ");
    n--;
}
// Prints "3 2 1 "
~~~

`while` checks **before** each iteration, whereas `do-while` checks **after** the body, so the `do` body always executes at least once if execution reaches that statement:

~~~java
int attempts = 0;
do {
    attempts++;
} while (attempts < 1);
System.out.println(attempts); // 1
~~~

### `break` and `continue`

~~~java
for (int i = 1; i <= 5; i++) {
    if (i == 2) continue; // skip the rest of iteration i=2
    if (i == 4) break;    // exit the loop
    System.out.print(i + " ");
}
// Prints "1 3 "
~~~

`continue` advances to the next iteration of its enclosing loop; `break` exits the corresponding enclosing loop or switch statement. For nested loops, the unlabeled form affects the innermost enclosing structure according to language rules. When nesting multiple levels, keep code readable instead of overusing labeled `break`.

## 9. `return`, Exceptions, and Early Exit Flow

`return` ends the **current method invocation**, and returns a value if the method has a non-`void` return type:

~~~java
static int safePercent(int value, int max) {
    if (max <= 0) {
        throw new IllegalArgumentException("max phai duong");
    }
    return value * 100 / max;
}
~~~

Here, `throw` creates an exceptional execution flow. When `max <= 0`, the division does not occur; the exception transfers control to an appropriate handler or causes the call to fail.

**Technical limitation to remember:** `value * 100` can still overflow `int`, even when `max` is positive. For large data, you can promote the calculation to `long` first and then check the result range. One defensive branch does not automatically make the entire calculation safe.

The `try/catch/finally` mechanism allows handling errors and cleaning up resources, though exceptions should not replace all ordinary conditional checks. In terms of ordering, when `return` or an exception occurs, statements after it on the current path do not execute normally. If `finally` is present, Java normally executes it when leaving `try`/`catch` before transferring control outward.

~~~java
static int example() {
    try {
        System.out.println("try");
        return 10;
    } finally {
        System.out.println("finally");
    }
}
// When calling example(): prints "try", then "finally", then the method returns 10.
~~~

Avoid putting `return` inside `finally`, as it can mask an active return value or exception; for `AutoCloseable` resources, `try-with-resources` usually makes responsibilities clearer.

## 10. Runnable Combined Example: From Data to Execution Flow

Create a file named exactly **`FlowWalkthrough.java`** and save it as UTF-8:

~~~java
public final class FlowWalkthrough {
    private FlowWalkthrough() {}

    static int payable(int total, boolean member) {
        if (total < 0) {
            throw new IllegalArgumentException("Tong phai khong am");
        }
        int discount = member && total >= 100 ? 15 : 0;
        return total - discount;
    }

    public static void main(String[] args) {
        int[] prices = {40, 70, 20};
        int total = 0;
        int processed = 0;

        for (int i = 0; i < prices.length; i++) {
            int price = prices[i];
            if (price <= 0) {
                continue;
            }
            total += price;
            processed++;
        }

        boolean member = args.length > 0
                && "member".equalsIgnoreCase(args[0]);

        int amount = payable(total, member);
        String group = switch (amount) {
            case 0 -> "MIEN_PHI";
            default -> amount >= 100 ? "LON" : "NHO";
        };

        System.out.println("So mon: " + processed);
        System.out.println("Tong: " + total);
        System.out.println("Thanh vien: " + member);
        System.out.println("Can tra: " + amount);
        System.out.println("Nhom: " + group);
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac --release 17 -encoding UTF-8 FlowWalkthrough.java
java FlowWalkthrough
java FlowWalkthrough member
~~~

**Run with no arguments**:

~~~text
So mon: 3
Tong: 130
Thanh vien: false
Can tra: 130
Nhom: LON
~~~

**Run with argument `member`**:

~~~text
So mon: 3
Tong: 130
Thanh vien: true
Can tra: 115
Nhom: LON
~~~

### Trace of the Run with Argument `member`

| Step | Statement/Expression | State After Step |
|---|---|---|
| 1 | `prices = {40,70,20}` | Array has 3 elements |
| 2 | `total=0; processed=0` | Total 0; processed 0 |
| 3 | Iteration `i=0`, price 40 | Total 40; processed 1 |
| 4 | Iteration `i=1`, price 70 | Total 110; processed 2 |
| 5 | Iteration `i=2`, price 20 | Total 130; processed 3 |
| 6 | `args.length > 0 && ...` | `member=true` |
| 7 | `member && total >= 100 ? 15 : 0` | `discount=15` |
| 8 | `return total - discount` | `amount=115` |
| 9 | `switch(amount)` | `group="LON"` |
| 10 | The `println` statements | Prints 5 lines as shown above |

**Notable details:**

- `prices.length` bounds the index, preventing access past the last element.
- `continue` skips non-positive prices; the current example has all positive prices. If `-5` were added to the array, the loop would stay safe and exclude that item.
- `"member".equalsIgnoreCase(args[0])` is called on a non-null literal. When no argument is provided, `&&` short-circuits so `args[0]` is not read.
- `payable` separates the calculation and input check from printing; it can be tested independently with different total values.
- `switch` here produces a `String` based on the amount, whereas the `for` loop and `if` are control-flow statements.

## 11. Predicting the Execution Path Before Clicking Run

Consider:

~~~java
int x = 1;
if (x > 1) {
    x += 10;
} else {
    x += 2;
}
while (x < 5) {
    x++;
}
System.out.println(x);
~~~

Use a trace table:

| Checkpoint | `x` | Reason |
|---|---:|---|
| After declaration | 1 | Initializer |
| After `if/else` | 3 | `x > 1` is false, runs `else` |
| After `while` iteration 1 | 4 | `4 < 5` will still be true on next check |
| After `while` iteration 2 | 5 | `x < 5` becomes false |
| When printing | 5 | Loop terminates |

Good habit: write down **before/after values** of variables, the condition being tested, and the branch chosen. If there is no progress making the loop condition false or no `break`, check for the risk of an infinite loop.

## 12. Common Errors and How to Classify Them

| Code/Incident | Symptom | Cause |
|---|---|---|
| `if (x = 1)` where `x` is `int` | Compile error | Assignment result has type `int`, not `boolean` |
| `int z = 7 / 2;` then expecting `3.5` | Wrong expected result | Integer division returns `3` |
| `input.length()` when `input == null` | `NullPointerException` | Calling a method through a null reference |
| `values[values.length]` | `ArrayIndexOutOfBoundsException` | Last valid index is `length - 1` for a non-empty array |
| `while (n > 0)` without changing `n` | Loop never ends | No progress or exit branch |
| Using `if (a && b)` and `b` is not called | Correct language behavior | Short-circuiting when `a=false` |
| Writing `total + price;` alone | Compile error | Not a valid expression statement |
| Accessing a variable declared inside a block from outside | Compile error | Wrong variable scope |
| `String s = null; s.equals("x")` | `NullPointerException` | Missing null check |
| `int x = Integer.MAX_VALUE + 1;` | Negative number due to overflow | Result exceeds `int` range |

Read errors by **stage**: syntax/type/scope errors are typically caught by `javac`; exceptions tied to real data or indices appear at runtime; infinite loops may throw no exception and instead make the program hang for a long time. Successful compilation does not prove all execution paths are right.

## 13. Exercises with Answers

### Exercise 1 — Identify Expressions and Statements

In `int n = 4; n += 3; System.out.println(n > 5);`, point out two expressions and three statements.

**Answer:** the expressions `4`, `n += 3`, and `n > 5` are all valid (there are also sub-expressions); all three lines ending with `;` are statements or declaration statements. `n > 5` has type `boolean` and prints `true`.

### Exercise 2 — Predict the Output

~~~java
int a = 8;
int b = 3;
System.out.println(a / b);
System.out.println((double) a / b);
~~~

**Answer:** `2` then `2.6666666666666665` (the actual decimal display of the `double` value). Integer division happens when both operands are `int`; casting before division changes the kind of operation.

### Exercise 3 — Short-Circuiting Protects Data

~~~java
String text = null;
boolean canRead = text != null && text.length() > 2;
System.out.println(canRead);
~~~

**Answer:** prints `false` without throwing an exception because the right-hand side of `&&` is not evaluated. If boolean `&` were used instead of `&&`, the right-hand side would be evaluated and could throw `NullPointerException`.

### Exercise 4 — `continue` and `break`

~~~java
int sum = 0;
for (int i = 1; i <= 6; i++) {
    if (i == 2) continue;
    if (i == 5) break;
    sum += i;
}
System.out.println(sum);
~~~

**Answer:** `8` (`1 + 3 + 4`). Skips iteration 2; at iteration 5, exits the loop before adding.

### Exercise 5 — Fix Definite Assignment Error

~~~java
boolean paid = false;
String result;
if (paid) {
    result = "OK";
}
// System.out.println(result);
~~~

**Requirement:** allow printing the result on every execution path. **Answer:** add `else { result = "PENDING"; }` before the print statement; or intentionally assign an initial value to `result`.

### Exercise 6 — Extend the Main Program

Modify `FlowWalkthrough` to add `0` and `-10` at the end of the `prices` array. Predict `processed`, `total`, and `amount`.

**Answer:** `processed=3`, `total=130`, `amount=130` with no arguments; `amount=115` when the argument is `member`. The two non-positive elements are skipped by `continue` before updating the total or count.

### Exercise 7 — Distinguish Compile Errors and Runtime Errors

Consider two cases: (A) `int count = "three";`; (B) `int divisor = 0; int value = 12 / divisor;`. At which stage does each error occur?

**Answer:** (A) `javac` rejects it because the types are incompatible; (B) integer division with divisor 0 throws `ArithmeticException` when the expression is evaluated at runtime.

## 14. Self-Assessment Checklist

- [ ] Explain the relationship **data → expressions → statements → execution flow** using a Java snippet.
- [ ] Distinguish `=` from `==`, primitive types from reference types, and `null` from a valid object value.
- [ ] Determine the type/result of arithmetic operations and `boolean` expressions; recognize integer division, overflow, and floating-point precision error.
- [ ] Understand operator precedence, operand evaluation order, and `&&`/`||` short-circuiting.
- [ ] Know that an arbitrary expression is not always a valid Java statement.
- [ ] Write `if`, `switch`, `for`, `while`, `break`, and `continue` accurately.
- [ ] Predict when `return` exits a method and how `throw` alters execution flow.
- [ ] Compile and run `FlowWalkthrough.java`; output matches the examples.
- [ ] Build a variable trace table to explain output and spot faulty loops.
- [ ] Classify compile-time errors, runtime exceptions, and logic errors that run without throwing.

**Conclusion:** Data is what a program processes; expressions produce values (sometimes with side effects); statements organize actions; control flow constructs determine which actions run and in what order. Mastering these four layers helps you read code, predict output, and debug Java methodically before building larger programs.
